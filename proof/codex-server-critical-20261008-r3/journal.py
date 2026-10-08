"""Durable one-attempt journal and a separate append-only witness.

No reset, truncate, restart election or retry API. A torn write or a witness
disagreement blocks effects and requires independent investigation; it never
creates a new attempt. In production the two protected roots must be on distinct
devices, with their rollback independence documented in installation acceptance.
"""
import fcntl
import os
import stat
from contextlib import contextmanager
from common import PinnedDirectory, canonical, digest, need, strict
from runtime import identity


def write_all(fd,raw):
    view=memoryview(raw)
    while view:
        n=os.write(fd,view);need(n>0,'JOURNAL_WRITE_UNCERTAIN');view=view[n:]


class Store:
    def __init__(self,directory,file_identity,lock_identity):
        self.root=directory;self.file_identity=file_identity;self.lock_identity=lock_identity

    def opened(self,name,expected):
        self.root.recheck();fd=os.open(name,os.O_RDWR|os.O_NOFOLLOW,dir_fd=self.root.fd)
        try:
            st=os.fstat(fd);named=os.stat(name,dir_fd=self.root.fd,follow_symlinks=False)
            need(stat.S_ISREG(st.st_mode) and st.st_nlink==1 and identity(st)==expected==identity(named)
                 and st.st_uid==os.geteuid() and stat.S_IMODE(st.st_mode)==0o600,'JOURNAL_FILE_IDENTITY')
            return fd
        except BaseException:os.close(fd);raise

    def read(self,fd,*,limit=16*1024*1024):
        before=os.fstat(fd);os.lseek(fd,0,os.SEEK_SET);parts=[];total=0
        while True:
            chunk=os.read(fd,65536)
            if not chunk:break
            total+=len(chunk);need(total<=limit,'JOURNAL_LIMIT');parts.append(chunk)
        after=os.fstat(fd)
        need((before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_size,after.st_mtime_ns,after.st_ctime_ns),'JOURNAL_CHANGED')
        raw=b''.join(parts);need(raw and raw.endswith(b'\n'),'JOURNAL_TORN')
        rows=[];previous='0'*64
        for seq,line in enumerate(raw.splitlines(keepends=True)):
            row=strict(line);need(canonical(row)==line and row['sequence']==seq and row['previous']==previous,'JOURNAL_CHAIN')
            rows.append(row);previous=digest(line)
        return rows,{'sequence':len(rows)-1,'digest':previous}

    def append(self,fd,rows,anchor,fields):
        data=canonical(dict(fields,sequence=len(rows),previous=anchor['digest']))
        os.lseek(fd,0,os.SEEK_END);write_all(fd,data);os.fsync(fd);os.fsync(self.root.fd)
        rows.append(strict(data));anchor.clear();anchor.update(sequence=len(rows)-1,digest=digest(data))


class IndependentWitness(Store):
    def __init__(self,directory,file_identity,lock_identity,*,election,ledger_root,independence,mode):
        super().__init__(directory,file_identity,lock_identity)
        need(mode in ('REAL','FIXTURE'),'WITNESS_MODE')
        if mode=='REAL':
            need(directory.identity['device']!=ledger_root['device'] and independence['rollback_independent'] is True
                 and independence['reviewed'] is True and independence['review_sha256'],'WITNESS_NOT_INDEPENDENT')
        self.election,self.ledger_root=election,ledger_root

    @contextmanager
    def locked(self):
        lock=self.opened('lock',self.lock_identity)
        try:
            fcntl.flock(lock,fcntl.LOCK_EX);fd=self.opened('events.jsonl',self.file_identity)
            try:
                rows,anchor=self.read(fd)
                need(rows[0]['kind']=='WITNESS_GENESIS' and rows[0]['election']==self.election
                     and rows[0]['ledger_root']==self.ledger_root,'WITNESS_GENESIS')
                yield fd,rows,anchor
            finally:os.close(fd)
        finally:os.close(lock)

    def read_anchor(self):
        with self.locked() as (_,rows,_):return rows[-1]['ledger_anchor']

    def advance(self,expected,new):
        with self.locked() as (fd,rows,anchor):
            need(rows[-1]['ledger_anchor']==expected,'WITNESS_CAS')
            self.append(fd,rows,anchor,{'kind':'ADVANCE','ledger_anchor':dict(new)})
            return rows[-1]['ledger_anchor']


class Journal(Store):
    def __init__(self,directory,file_identity,lock_identity,*,election,witness):
        super().__init__(directory,file_identity,lock_identity);self.election,self.witness=election,witness

    @contextmanager
    def locked(self):
        lock=self.opened('lock',self.lock_identity)
        try:
            fcntl.flock(lock,fcntl.LOCK_EX);self.root.recheck()
            fd=self.opened('events.jsonl',self.file_identity)
            try:
                rows,anchor=self.read(fd)
                need(rows[0]['kind']=='GENESIS' and rows[0]['election']==self.election
                     and rows[0]['root_identity']==self.root.identity,'JOURNAL_GENESIS')
                need(self.witness.read_anchor()==anchor,'JOURNAL_WITNESS_MISMATCH')
                yield fd,rows,anchor
            finally:os.close(fd)
        finally:os.close(lock)

    def append_witnessed(self,fd,rows,anchor,fields):
        previous=dict(anchor);self.root.recheck()
        self.append(fd,rows,anchor,fields)
        need(self.witness.advance(previous,dict(anchor))==anchor,'WITNESS_ADVANCE_UNCERTAIN')
        self.root.recheck()


def bootstrap_fixture(root,witness_root,election):
    """Only isolated fixtures. Real installation must supply its own reviewed
    genesis and fixed identities; the service cannot bootstrap on missing files.
    """
    need(election['mode']=='FIXTURE','JOURNAL_NO_AUTOMATIC_PRODUCTION_BOOTSTRAP')
    a=PinnedDirectory(root);b=PinnedDirectory(witness_root)
    try:
        row={'sequence':0,'previous':'0'*64,'kind':'GENESIS','election':election,'root_identity':a.identity}
        data=canonical(row);a.create('events.jsonl',data);a.create('lock',b'FIXTURE_LOCK\n')
        anchor={'sequence':0,'digest':digest(data)}
        b.create('events.jsonl',canonical({'sequence':0,'previous':'0'*64,'kind':'WITNESS_GENESIS',
                 'election':election,'ledger_root':a.identity,'ledger_anchor':anchor}));b.create('lock',b'FIXTURE_LOCK\n')
        def pins(directory):return {n:identity(os.stat(n,dir_fd=directory.fd,follow_symlinks=False)) for n in ('events.jsonl','lock')}
        return {'ledger':pins(a),'witness':pins(b),'root':a.identity,'witness_root':b.identity}
    finally:a.close();b.close()
