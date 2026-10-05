"""K12w with the real system calls of its own Native on a private temporary tree that stands in for '/' (tests/oslevel.py
of the frozen core; the data volume on a device of its own by tests/native_support.py). The process runner alone is
answered by the emulated engine (tests/native_k12.py): no docker exists on the workstation. Proves the walks by dir_fd
without following a link, secret.env never opened, the reads of the writer, config and pins bytes, and PERSIST's one
exclusive creation with its readback, with macOS errno values as an ordinary user reported as root; the kernel's
O_NOATIME, Linux errno values and real uid 0 only on the Linux-root job (NOT RUN)."""
import os
from pathlib import Path
import stat

import pytest

import family as f
import k12emu as e
import k12w
import native_k12 as n
import native_support

K=k12w.K()
WRITE=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND|os.O_EXCL

@pytest.fixture
def tree(tmp_path):return n.build_tree(tmp_path)

def snapshot(root):
    out={}
    for path in sorted([root]+list(root.rglob('*'))):
        info=os.lstat(path);out[str(path.relative_to(root))]=(stat.S_IFMT(info.st_mode),stat.S_IMODE(info.st_mode),info.st_nlink,info.st_ino,info.st_mtime_ns,
                                                              info.st_size if stat.S_ISREG(info.st_mode) else None)
    return out

def run(root,mode,host,**options):
    docs=f.Docs(K,dict(k12w.fields(host,mode,**options),parent_rows=n.chains(root,k12w.CHAINS[mode])),now=e.at(k12w.MOMENTS[mode]))
    old=os.umask(0o027)
    try:
        with native_support.Volume(root) as record:receipt=docs.run(n.with_engine(K.m.Native,host))
    finally:os.umask(old)
    return receipt,record

def common(receipt,record):
    assert e.SECRET_URL not in str(receipt)
    opens=[entry for entry in record.calls if entry['call']=='open'];assert opens and all(entry['flags']&os.O_NOFOLLOW for entry in opens)
    assert all(entry['by_dir_fd'] or entry['path']=='/' for entry in opens),'only "/" is opened by absolute path'
    assert not [entry for entry in opens if entry['path'].endswith('secret.env')],'secret.env is never opened'
    stats=[entry for entry in record.calls if entry['call']=='stat'];assert all(entry['follow_symlinks'] is False and entry['by_dir_fd'] for entry in stats)
    assert [entry['mask'] for entry in record.calls if entry['call']=='umask']==[0o077]

def test_native_launch_reads_only_and_creates_the_container(tree):
    host=e.world(K);before=snapshot(tree);receipt,record=run(tree,'LAUNCH',host)
    assert (receipt['status'],receipt['code'])==('METADATA_ONLY_REQUIRES_REVIEW',None),(receipt['code'],receipt.get('detail'))
    common(receipt,record);assert snapshot(tree)==before
    assert not [entry for entry in record.calls if entry['call'] in ('mkdir','link','unlink') or (entry['call']=='open' and entry['flags']&WRITE)]
    reads=[entry['path'] for entry in record.calls if entry['call']=='open' and not entry['flags']&os.O_DIRECTORY]
    for path in ('/var/lib/c3po-capacity/config/manifest_writer-%s.py'%e.sha(e.WRITER),'/var/lib/c3po-capacity/config/session=2026-10-06.primary.capacity.json',
                 '/etc/c3po-reader/pins.env'):assert path in reads,path
    assert host.docker.container('c3po-k12-20261006-w1')['State']['Running'] is True

def test_native_launch_refuses_a_link_where_the_writer_should_be(tree):
    name='var/lib/c3po-capacity/config/manifest_writer-%s.py'%e.sha(e.WRITER);(tree/name).unlink();os.symlink('/etc/passwd',str(tree/name))
    host=e.world(K);receipt,record=run(tree,'LAUNCH',host);assert (receipt['status'],receipt['code'])==('REFUSED','PRECHECK_OS_ERROR')
    assert host.docker.created==[] and not [entry for entry in record.calls if entry['call']=='open' and 'passwd' in entry['path']]

def test_native_launch_secret_env_metadata(tree):
    os.chmod(tree/'etc/c3po-reader/secret.env',0o640);host=e.world(K);receipt,_=run(tree,'LAUNCH',host)
    assert (receipt['status'],receipt['code'])==('REFUSED','SECRET_ENV_NOT_PRIVATE')

def test_native_persist_creates_exactly_one_private_file(tree):
    host=e.world(K);item=e.launched(host,K,request_sha=k12w.LAUNCH_SHA);e.at_view(host,item['Name'][1:])
    before=snapshot(tree);receipt,record=run(tree,'PERSIST',host)
    assert (receipt['status'],receipt['code'])==('METADATA_ONLY_REQUIRES_REVIEW',None),(receipt['code'],receipt.get('detail'))
    common(receipt,record);final=tree/'var/lib/c3po-reader/capacity-receipts/k12-2026-10-06-w1.writer.json'
    raw=final.read_bytes();value=__import__('json').loads(raw);assert value['container_id']==item['Id'] and value['stdout_sha256']==e.sha(e.writer_line())
    info=os.lstat(final);assert (stat.S_IMODE(info.st_mode),info.st_nlink,stat.S_ISREG(info.st_mode))==(0o600,1,True)
    after=snapshot(tree);assert sorted(set(after)-set(before))==['var/lib/c3po-reader/capacity-receipts/k12-2026-10-06-w1.writer.json']
    assert {key:value for key,value in after.items() if not key.startswith('var/lib/c3po-reader')}=={key:value for key,value in before.items() if not key.startswith('var/lib/c3po-reader')}
    changing=[(entry['call'],entry['path']) for entry in record.calls if entry['call'] in ('mkdir','link','unlink') or (entry['call']=='open' and entry['flags']&os.O_CREAT)]
    temporary='/var/lib/c3po-reader/capacity-receipts/.hostops-%s-0.partial'%receipt['go_sha256'][:16]
    assert changing==[('open',temporary),('link','/var/lib/c3po-reader/capacity-receipts/k12-2026-10-06-w1.writer.json'),('unlink',temporary)]
    created=[entry for entry in record.calls if entry['call']=='open' and entry['flags']&os.O_CREAT][0]
    assert created['flags']&(os.O_EXCL|os.O_NOFOLLOW)==os.O_EXCL|os.O_NOFOLLOW and created['mode']==0o600

def test_native_persist_never_replaces_an_existing_receipt(tree):
    host=e.world(K);item=e.launched(host,K,request_sha=k12w.LAUNCH_SHA);e.at_view(host,item['Name'][1:])
    n.write(tree/'var/lib/c3po-reader/capacity-receipts/k12-2026-10-06-w1.writer.json',b'{}');before=snapshot(tree)
    receipt,_=run(tree,'PERSIST',host);assert (receipt['status'],receipt['code'])==('REFUSED','PERSISTED_RECEIPT_PRESENT') and snapshot(tree)==before

def test_native_stop_and_remove_change_no_file(tree):
    host=e.world(K);e.launched(host,K,request_sha=k12w.LAUNCH_SHA);before=snapshot(tree);receipt,record=run(tree,'STOP',host)
    assert receipt['code'] is None and snapshot(tree)==before and not [entry for entry in record.calls if entry['call']=='open' and entry['flags']&WRITE]
    host,items=k12w.remove_world(K)
    for name,node in host.tree.get(e.RECEIPTS).children.items():n.write(tree/('var/lib/c3po-reader/capacity-receipts/'+name),bytes(node.content))
    docs=f.Docs(K,dict(k12w.fields(host,'REMOVE',removals=items),parent_rows=n.chains(tree,['receipts'])),now=e.at(k12w.MOMENTS['REMOVE']))
    before=snapshot(tree);old=os.umask(0o027)
    try:
        with native_support.Volume(tree) as record:receipt=docs.run(n.with_engine(K.m.Native,host))
    finally:os.umask(old)
    assert receipt['code'] is None and snapshot(tree)==before and receipt['detail']['removed']==3
