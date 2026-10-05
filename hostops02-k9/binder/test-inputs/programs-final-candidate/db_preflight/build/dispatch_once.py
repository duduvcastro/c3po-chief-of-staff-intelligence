"""Explicitly bound, one-shot SSH dispatcher. No execution on import.
The independently supplied config SHA is the authority trust anchor.
"""
import argparse
from datetime import datetime,timezone,timedelta
import hashlib
import json
import os
from pathlib import PurePosixPath,Path
import re
import stat
import time
import launcher_stdin
import transport_once
import db_preflight
from db_preflight import canonical,decode,need,instant,sha


def parent(path):
    need(type(path) is str and path.startswith('/') and str(PurePosixPath(path))==path and '..' not in PurePosixPath(path).parts,'LOCAL_PATH')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in PurePosixPath(path).parts[1:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=child
        return fd,PurePosixPath(path).name
    except BaseException:os.close(fd);raise


class AnchoredDirectory:
    """Keep every ancestor open; verify every name still resolves to that fd."""
    def __init__(self,path,expected):
        need(type(path) is str and path.startswith('/') and str(PurePosixPath(path))==path
             and '..' not in PurePosixPath(path).parts,'LOCAL_ROOT_PATH')
        need(type(expected) is dict and set(expected)=={'path','device','inode'} and expected['path']==path
             and type(expected['device']) is int and type(expected['inode']) is int,'LOCAL_ROOT_UNBOUND')
        self.fds=[];self.names=[];self.identities=[]
        try:
            fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);self.fds.append(fd)
            for name in PurePosixPath(path).parts[1:]:
                child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                self.names.append(name);self.fds.append(child);fd=child
            self.identities=[self.identity(os.fstat(fd)) for fd in self.fds]
            need(self.identities[-1]==(expected['device'],expected['inode']),'LOCAL_ROOT_IDENTITY')
            meta=os.fstat(fd)
            need(meta.st_uid==os.geteuid() and stat.S_IMODE(meta.st_mode)==0o700,'ATTEMPT_PARENT_PRIVATE')
            self.check()
        except BaseException:self.close();raise
    @staticmethod
    def identity(info):return info.st_dev,info.st_ino
    @property
    def fd(self):return self.fds[-1]
    def check(self):
        for index,fd in enumerate(self.fds):
            held=os.fstat(fd)
            need(stat.S_ISDIR(held.st_mode) and self.identity(held)==self.identities[index],'LOCAL_ANCESTOR_CHANGED')
            if index:
                named=os.stat(self.names[index-1],dir_fd=self.fds[index-1],follow_symlinks=False)
                need(stat.S_ISDIR(named.st_mode) and self.identity(named)==self.identities[index],'LOCAL_ANCESTOR_CHANGED')
        final=os.fstat(self.fd)
        need(final.st_uid==os.geteuid() and stat.S_IMODE(final.st_mode)==0o700,'ATTEMPT_PARENT_PRIVATE')
    def close(self):
        while self.fds:os.close(self.fds.pop())


def read(path,pin,limit=2*1024*1024,private=True):
    need(type(pin) is str and re.fullmatch('[0-9a-f]{64}',pin) and pin!='0'*64,'LOCAL_PIN_UNBOUND')
    directory,name=parent(path)
    try:
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        try:
            before=os.fstat(fd)
            need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and 0<before.st_size<=limit,'LOCAL_FILE')
            need(not before.st_mode&0o022 and (not private or (before.st_uid==os.geteuid() and stat.S_IMODE(before.st_mode)==0o600)),'LOCAL_PERMISSIONS')
            chunks=[];size=0
            while size<=limit:
                block=os.read(fd,min(65536,limit+1-size))
                if not block:break
                chunks.append(block);size+=len(block)
            after=os.fstat(fd);named=os.stat(name,dir_fd=directory,follow_symlinks=False)
            def signature(s):return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns
            need(signature(before)==signature(after)==signature(named),'LOCAL_CHANGED')
            raw=b''.join(chunks);need(len(raw)==before.st_size and sha(raw)==pin,'LOCAL_PIN')
            return raw
        finally:os.close(fd)
    finally:os.close(directory)


def command(config):
    target=config['target'];need(type(target) is str and re.fullmatch('[a-z_][a-z0-9_-]*@[A-Za-z0-9.-]+',target),'SSH_TARGET')
    need(config['remote_command']=='sudo -n /usr/bin/python3 -I -B -','REMOTE_COMMAND')
    for key in ('ssh_key','known_hosts'):need(type(config[key]) is dict and set(config[key])=={'path','sha256'},'SSH_REFERENCE')
    return ['/usr/bin/ssh','-F','/dev/null','-T','-o','ForwardAgent=no','-o','ClearAllForwardings=yes',
            '-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
            '-o','GlobalKnownHostsFile=/dev/null','-o','UserKnownHostsFile='+config['known_hosts']['path'],
            '-o','ConnectTimeout=10','-o','ConnectionAttempts=1','-i',config['ssh_key']['path'],target,config['remote_command']]


def execute(config_path,config_sha256,*,phase='prepare',publication_path=None,publication_sha256=None,clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic,transport=transport_once.once):
    need(phase in ('prepare','resume'),'DISPATCH_PHASE')
    raw=read(config_path,config_sha256,65536);config=decode(raw)
    need(config.get('schema')=='HOSTOPS02_DB_PREFLIGHT_DISPATCH_AUTHORIZATION_V1' and config.get('status')=='BOUND'
         and config.get('decision')=='GO' and config.get('operation')=='GO_READONLY_HOSTOPS02_DB_PREFLIGHT_01'
         and config.get('single_use') is True and config.get('retry') is False,'DISPATCH_UNBOUND')
    need(type(config.get('owner')) is str and config['owner'] not in ('','UNBOUND')
         and type(config.get('authorization_ref')) is str and config['authorization_ref'] not in ('','UNBOUND'),'DISPATCH_AUTHORITY')
    need(config.get('executor_uid')==0 and type(config['executor_uid']) is int,'REMOTE_UID')
    start,end=instant(config['not_before']),instant(config['not_after'])
    need(start.date().isoformat() in ('2026-10-02','2026-10-03','2026-10-04','2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09','2026-10-10') and end.date()==start.date(),'DISPATCH_DATE')
    seconds=config['watchdog_seconds'];need(type(seconds) is int and 1<=seconds<=90,'WATCHDOG_LIMIT')
    latest_start=instant(config['latest_start'])
    need(start<=latest_start==end-timedelta(seconds=seconds),'LATEST_START_BINDING')
    deadline=monotonic()+seconds
    def gate():
        now=clock();need(start<=now<end and monotonic()<deadline,'DISPATCH_WINDOW')
    gate()
    need(config.get('finalize_local_receipts_after_window') is True,'LOCAL_FINALIZATION_AUTHORITY')
    modules=('dispatch_once.py','transport_once.py','launcher_stdin.py','db_preflight.py')
    need(type(config.get('runtime_sha256')) is dict and set(config['runtime_sha256'])==set(modules),'RUNTIME_PINS_UNBOUND')
    for name in modules:read(str(Path(__file__).resolve().with_name(name)),config['runtime_sha256'][name],private=False);gate()
    blobs={}
    for name in ('source','request','authority','go','payload'):
        item=config[name];blobs[name]=read(item['path'],item['sha256']);gate()
    request,authority,go=map(decode,(blobs['request'],blobs['authority'],blobs['go']))
    need('status' not in go or go['status']=='SIGNED','GO_UNSIGNED')
    need('status' not in authority or authority['status']=='SIGNED','AUTHORITY_UNSIGNED')
    need(request.get('schema')=='READONLY_HOSTOPS02_DB_PREFLIGHT_REQUEST_V1' and authority.get('schema')=='READONLY_HOSTOPS02_DB_PREFLIGHT_AUTHORITY_V1'
         and go.get('schema')=='READONLY_HOSTOPS02_DB_PREFLIGHT_GO_V1' and request.get('operation')==authority.get('operation')=='GO_READONLY_HOSTOPS02_DB_PREFLIGHT_01'
         and request.get('status')=='BOUND' and request.get('executor_uid')==0 and request.get('date')==start.date().isoformat()
         and go.get('action')=='GO' and go.get('owner')==authority.get('owner')==config['owner'],'INNER_AUTHORITY')
    need(type(go.get('claim_root_identity')) is dict and canonical(go['claim_root_identity'])==canonical(config.get('local_root_identity')),'GO_CLAIM_ROOT_BINDING')
    need(start>=instant(request['not_before']) and end<=instant(request['not_after'])
         and start>=instant(go['not_before']) and end<=instant(go['not_after']),'INNER_WINDOW')
    need(authority.get('request_sha256')==sha(blobs['request']) and go.get('request_sha256')==sha(blobs['request'])
         and go.get('authority_sha256')==sha(blobs['authority']) and go.get('payload_sha256')==sha(blobs['source'])
         and request.get('payload_sha256')==sha(blobs['source']),'INNER_BINDINGS')
    need(config['watchdog_seconds']==80 and request.get('max_seconds')==60,'PREFLIGHT_BUDGET')
    need(request.get('host_binding_sha256')==authority.get('host_binding_sha256')==go.get('host_binding_sha256')==config.get('host_binding_sha256'),'HOST_BINDING')
    expected_transport={key:config[key] for key in ('target','remote_command','command_sha256','runtime_sha256')}
    need(go.get('transport_binding')==expected_transport,'GO_TRANSPORT_BINDING')
    need(go.get('phase')=='READONLY_DB_PREFLIGHT_THREE_QUERIES' and go.get('writes_allowed') is False
         and authority.get('writes_allowed') is False and request.get('writes_allowed') is False,'READONLY_SCOPE')
    # Validate the complete new inner authority before any claim or SSH launch.
    # UID0 here checks the requested target actor, not this local process; the
    # remote caller independently checks its actual effective uid again.
    db_preflight.authenticate(blobs['request'],blobs['authority'],blobs['go'],
        pins=db_preflight.Pins(payload=sha(blobs['source']),request=sha(blobs['request']),
            authority=sha(blobs['authority']),go=sha(blobs['go'])),payload_bytes=blobs['source'],
        clock=clock,monotonic=monotonic,executor_uid=lambda:config['executor_uid'])
    expected=launcher_stdin.build(blobs['source'],blobs['request'],blobs['authority'],blobs['go'],
        expected_payload_sha256=sha(blobs['source']),expected_request_sha256=sha(blobs['request']),
        expected_authority_sha256=sha(blobs['authority']),expected_go_sha256=sha(blobs['go']))
    need(expected==blobs['payload'],'FINAL_BUNDLE_BYTES')
    argv=command(config);need(transport_once.command_pin(argv)==config['command_sha256'],'COMMAND_PIN')
    for name in ('ssh_key','known_hosts'):read(config[name]['path'],config[name]['sha256'],65536);gate()
    attempt_path=PurePosixPath(config['attempt_directory'])
    need(str(attempt_path)==config['attempt_directory'] and attempt_path.name not in ('','..'), 'ATTEMPT_PATH')
    anchor=AnchoredDirectory(str(attempt_path.parent),config.get('local_root_identity'))
    output,name=anchor.fd,attempt_path.name
    attempt=None;claim=None
    claim_name='.go-'+sha(blobs['go'])+'.claim'
    claim_raw=canonical({'schema':'HOSTOPS02_DB_PREFLIGHT_GO_CLAIM_V1','go_sha256':sha(blobs['go']),'config_sha256':config_sha256})
    base_gate=gate
    def location_gate():
        anchor.check()
        if claim is not None:
            held_claim=os.fstat(claim);named_claim=os.stat(claim_name,dir_fd=output,follow_symlinks=False)
            need(stat.S_ISREG(named_claim.st_mode) and AnchoredDirectory.identity(held_claim)==AnchoredDirectory.identity(named_claim)
                 and held_claim.st_nlink==1 and held_claim.st_uid==os.geteuid() and stat.S_IMODE(held_claim.st_mode)==0o600,'GO_CLAIM_CHANGED')
        if attempt is not None:
            held=os.fstat(attempt);named=os.stat(name,dir_fd=output,follow_symlinks=False)
            need(stat.S_ISDIR(named.st_mode) and AnchoredDirectory.identity(held)==AnchoredDirectory.identity(named), 'ATTEMPT_REBOUND')
            need(held.st_uid==os.geteuid() and stat.S_IMODE(held.st_mode)==0o700,'ATTEMPT_PRIVATE')
    def anchored_gate():
        base_gate();location_gate();base_gate()
    gate=anchored_gate
    try:
        meta=os.fstat(output);need(meta.st_uid==os.geteuid() and stat.S_IMODE(meta.st_mode)==0o700,'ATTEMPT_PARENT_PRIVATE')
        gate();need(clock()<=latest_start,'WINDOW_WITH_WATCHDOG')
        if phase=='prepare':
            gate();claim=os.open(claim_name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=output)
            gate();need(os.write(claim,claim_raw)==len(claim_raw),'GO_CLAIM_SHORT_WRITE');os.fsync(claim);os.fsync(output);gate()
            os.mkdir(name,0o700,dir_fd=output);os.fsync(output);gate()
        else:
            need(type(publication_path) is str and type(publication_sha256) is str,'PUBLICATION_UNBOUND')
            need(read(str(attempt_path.parent/claim_name),sha(claim_raw))==claim_raw,'GO_CLAIM_CHANGED')
            claim=os.open(claim_name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=output);gate()
        attempt=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=output)
        def write(name,raw,authorize=True):
            location_gate()
            if authorize:gate()
            fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=attempt)
            try:
                offset=0
                while offset<len(raw):
                    # Receipt finalization is separately authorized below, even after remote timeout.
                    location_gate()
                    if authorize:gate()
                    offset+=os.write(fd,raw[offset:]);
                os.fsync(fd)
            finally:os.close(fd)
            os.fsync(attempt);location_gate()
        need(config.get('finalize_local_receipts_after_window') is True,'LOCAL_FINALIZATION_AUTHORITY')
        if phase=='prepare':
            intent=canonical({'schema':'HOSTOPS02_DB_PREFLIGHT_DISPATCH_INTENT_V1','config_sha256':config_sha256,
                'payload_sha256':sha(blobs['payload']),'request_sha256':sha(blobs['request']),
                'go_sha256':sha(blobs['go']),'started_at':clock().isoformat(),'attempts':1,'retry':False})
            write('intent.json',intent)
            return {'status':'AWAITING_PUBLICATION_NO_SPAWN','intent_sha256':sha(intent),
                    'go_sha256':sha(blobs['go']),'config_sha256':config_sha256,'retry':False}
        proof_raw=read(publication_path,publication_sha256,65536);gate()
        proof=decode(proof_raw)
        need(proof.get('schema')=='HOSTOPS02_DB_PREFLIGHT_INTENT_PUBLICATION_V1' and proof.get('status')=='PUBLISHED'
             and proof.get('owner')==config['owner'] and type(proof.get('publication_ref')) is str
             and proof['publication_ref'] not in ('','UNBOUND') and proof.get('go_sha256')==sha(blobs['go'])
             and proof.get('config_sha256')==config_sha256,'PUBLICATION_BINDINGS')
        intent_raw=read(str(attempt_path/'intent.json'),proof.get('intent_sha256'),65536);gate()
        intent=decode(intent_raw)
        expected_intent={'schema':'HOSTOPS02_DB_PREFLIGHT_DISPATCH_INTENT_V1','config_sha256':config_sha256,
            'payload_sha256':sha(blobs['payload']),'request_sha256':sha(blobs['request']),
            'go_sha256':sha(blobs['go']),'started_at':intent.get('started_at'),'attempts':1,'retry':False}
        need(intent==expected_intent and start<=instant(intent['started_at'])<=instant(proof['published_at'])<=clock(), 'INTENT_PUBLICATION_ORDER')
        # No retry: this marker is persisted before final authorization or transport.
        write('spawn.claim',canonical({'publication_sha256':publication_sha256,'intent_sha256':sha(intent_raw)}))
        def authorize(payload_pin,command_pin):
            gate()
            need(payload_pin==sha(blobs['payload']) and command_pin==config['command_sha256'],'SPAWN_BINDINGS')
            need(read(publication_path,publication_sha256,65536)==proof_raw,'PUBLICATION_CHANGED');gate()
            need(read(str(attempt_path/'intent.json'),sha(intent_raw),65536)==intent_raw,'INTENT_CHANGED');gate()
            for name in ('ssh_key','known_hosts'):read(config[name]['path'],config[name]['sha256'],65536);gate()
            gate();need(clock()<=latest_start,'WINDOW_WITH_WATCHDOG')
            return True
        out=b'';err=b''
        try:
            result,out,err=transport(blobs['payload'],payload_sha256=sha(blobs['payload']),command=argv,
                command_sha256=config['command_sha256'],authorize=authorize,seconds=seconds,monotonic=monotonic)
            if result['status'] in ('KNOWN_COMPLETE','KNOWN_PARTIAL'):
                receipt=decode(out)
                need(receipt.get('schema')=='READONLY_HOSTOPS02_DB_PREFLIGHT_RECEIPT_V1' and receipt.get('request_sha256')==sha(blobs['request'])
                     and receipt.get('go_sha256')==sha(blobs['go']) and receipt.get('payload_sha256')==sha(blobs['source']),'REMOTE_RECEIPT_BINDINGS')
        except Exception:
            result={'status':'UNCERTAIN','code':'TRANSPORT_OR_RECEIPT_REFUSED','retry_allowed':False}
        write('stdout.private.json',out,False);write('stderr.private',err,False)
        result.update(config_sha256=config_sha256,request_sha256=sha(blobs['request']),go_sha256=sha(blobs['go']),
                      stdout_sha256=sha(out),stderr_sha256=sha(err),finished_at=clock().isoformat())
        write('exit.json',canonical(result),False)
        return result
    finally:
        if attempt is not None:os.close(attempt)
        if claim is not None:os.close(claim)
        anchor.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--config-sha256',required=True)
    parser.add_argument('--phase',choices=('prepare','resume'),default='prepare')
    parser.add_argument('--publication-proof');parser.add_argument('--publication-proof-sha256')
    args=parser.parse_args()
    try:
        result=execute(args.config,args.config_sha256,phase=args.phase,publication_path=args.publication_proof,publication_sha256=args.publication_proof_sha256)
        print(json.dumps(result,sort_keys=True))
        return 0 if result['status']=='KNOWN_COMPLETE' else 2
    except Exception:
        print('{"status":"REFUSED_OR_UNCERTAIN","code":"DISPATCH_REFUSED","retry":false}')
        return 2

if __name__=='__main__':raise SystemExit(main())
