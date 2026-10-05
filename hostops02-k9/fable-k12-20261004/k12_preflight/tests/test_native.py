"""K12p with the real system calls of its own Native on a private temporary tree that stands in for '/' (tests/oslevel.py;
the data volume by tests/native_support.py); the one attached run is answered by the emulated engine (tests/native_k12.py).
Proves that this process reads by dir_fd without following a link (secret.env never opened) and creates one file, its
claim, by the files part's exclusive creation, and changes nothing else.
Linux, O_NOATIME and real uid 0 only on the Linux-root job (NOT RUN)."""
import json
import os
import stat

import pytest

import family as f
import k12emu as e
import k12p
import native_k12 as n
import native_support

K=k12p.K()
WRITE=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND|os.O_EXCL

@pytest.fixture
def tree(tmp_path):return n.build_tree(tmp_path)

def snapshot(root):
    out={}
    for path in sorted([root]+list(root.rglob('*'))):
        info=os.lstat(path);out[str(path.relative_to(root))]=(stat.S_IFMT(info.st_mode),stat.S_IMODE(info.st_mode),info.st_nlink,info.st_ino,info.st_mtime_ns,
                                                              info.st_size if stat.S_ISREG(info.st_mode) else None)
    return out

CLAIM='var/lib/c3po-reader/capacity-receipts/k12-2026-10-06-preflight.claim.json'

def run(root,host):
    """One run; every file but the claim unchanged, and the claim created only by the files part's one exclusive creation
    (temporary, link, unlink) when the run got that far."""
    docs=f.Docs(K,dict(k12p.fields(host),parent_rows=n.chains(root,k12p.CHAINS)),now=e.at(k12p.MOMENT));before=snapshot(root)
    old=os.umask(0o027)
    try:
        with native_support.Volume(root) as record:receipt=docs.run(n.with_engine(K.m.Native,host))
    finally:os.umask(old)
    after=snapshot(root);assert e.SECRET_URL not in json.dumps(receipt)
    assert {key:value for key,value in after.items() if not key.startswith('var/lib/c3po-reader')}=={key:value for key,value in before.items() if not key.startswith('var/lib/c3po-reader')}
    assert set(after)-set(before)<={CLAIM} and not set(before)-set(after)
    opens=[entry for entry in record.calls if entry['call']=='open']
    assert opens and all(entry['flags']&os.O_NOFOLLOW for entry in opens) and all(entry['by_dir_fd'] or entry['path']=='/' for entry in opens)
    writing=[entry for entry in opens if entry['flags']&WRITE]
    assert all(entry['flags']&(os.O_CREAT|os.O_EXCL)==os.O_CREAT|os.O_EXCL and entry['mode']==0o600 and '/capacity-receipts/.hostops-' in entry['path'] for entry in writing)
    assert not [entry for entry in opens if entry['path'].endswith('secret.env')] and not record.of('mkdir')
    assert [entry['mask'] for entry in record.calls if entry['call']=='umask']==[0o077],'umask 077 before anything is created'
    return receipt,record

def test_native_preflight_reads_only(tree):
    host=k12p.world(K);receipt,record=run(tree,host)
    assert (receipt['status'],receipt['code'])==('METADATA_ONLY_REQUIRES_REVIEW',None),(receipt['code'],receipt.get('detail'))
    assert len(host.preflight_calls)==1 and host.preflight_calls[0]['command'][-1]=='--preflight'
    info=os.lstat(tree/CLAIM);assert (stat.S_IMODE(info.st_mode),info.st_nlink,stat.S_ISREG(info.st_mode))==(0o600,1,True)
    assert json.loads((tree/CLAIM).read_bytes())['preflight_request_sha256']==receipt['request_sha256']
    changing=[(entry['call'],entry['path']) for entry in record.calls if entry['call'] in ('link','unlink') or (entry['call']=='open' and entry['flags']&os.O_CREAT)]
    temporary='/var/lib/c3po-reader/capacity-receipts/.hostops-%s-0.partial'%receipt['go_sha256'][:16]
    assert changing==[('open',temporary),('link','/'+CLAIM),('unlink',temporary)]
    host2=k12p.world(K);again,_=run(tree,host2);assert (again['status'],again['code'])==('REFUSED','PREFLIGHT_ALREADY_CLAIMED') and host2.preflight_calls==[]

def test_native_preflight_refuses_wrong_pins_bytes(tree):
    n.write(tree/'etc/c3po-reader/pins.env',e.PINS+b'X=1\n');host=k12p.world(K);receipt,_=run(tree,host)
    assert (receipt['status'],receipt['code'])==('REFUSED','PINS_ENV_NOT_THE_SIGNED_BYTES') and host.preflight_calls==[]

def test_native_preflight_refuses_a_docker_cli_directory_that_holds_something(tree):
    n.write(tree/'etc/c3po-reader/docker-cli/config.json',b'{}');host=k12p.world(K);receipt,_=run(tree,host)
    assert (receipt['status'],receipt['code'])==('REFUSED','DOCKER_CLI_DIRECTORY_NOT_EMPTY')
