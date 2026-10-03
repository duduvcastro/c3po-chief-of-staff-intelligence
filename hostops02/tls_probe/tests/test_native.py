"""The real system calls and processes of C3, made by the source's own unmodified Native on a private temporary tree
that stands in for '/', with a real program behind the docker binary. Nothing of Native is overridden but the path of
that binary (moved into the temporary tree): the substitution of '/' and of the uid is made on the os module (the
core's tests/oslevel.py), and every system call is recorded with the arguments it received.

What stands for docker is a program at <tree>/usr/bin/docker. It answers the two image reads and the listing as the
CLI would, logs every argv, the hash of its standard input, its environment and its working directory, and for `run`
executes the bytes it got on standard input with a real `python -I -B -`: the pinned script, against a local TLS server
on 127.0.0.1 with a throwaway authority. Only that stand-in writes the test-only prelude in front of the bytes it
received (tests/c3.py): the source gives the pinned bytes alone, which the log proves by their hash. No docker, no
container, no host, no network."""
import json
import os
from pathlib import Path

import pytest

import c3
import family as f
import oslevel

BOOT=b'0f8fad5b-d9cb-469f-a165-70867728950e\n'
IMAGE='sha256:'+'fb'*32
FAKE_DOCKER='''#!%(python)s -B
import hashlib,json,os,subprocess,sys
TREE=%(tree)r;IMAGE=%(image)r;TAG=%(tag)r;REVISION=%(revision)r;PRELUDE=%(prelude)r;LISTED=%(listed)r
arguments=sys.argv[1:];data=sys.stdin.buffer.read()
with open(TREE+'.docker.log','a') as log:
    log.write(json.dumps({'argv':arguments,'stdin_sha256':hashlib.sha256(data).hexdigest() if data else None,'cwd':os.getcwd(),
                          'environment':{key:value for key,value in os.environ.items() if not key.startswith('__CF')}},sort_keys=True)+'\\n')
if arguments[:3]==['image','inspect','--format'] and len(arguments)==5:
    if arguments[4] not in (IMAGE,TAG):raise SystemExit(1)
    print(json.dumps({'id':IMAGE,'repo_tags':['c3po/backend:production',TAG],'revision':REVISION}))
elif arguments[:4]==['ps','-a','--no-trunc','--format'] and len(arguments)==5:
    for row in LISTED:print(json.dumps(row))
elif arguments[:1]==['run']:
    assert arguments[arguments.index(IMAGE)+1:]==['python','-I','-B','-']
    done=subprocess.run([sys.executable,'-I','-B','-'],input=PRELUDE.encode()+data,stdout=subprocess.PIPE,env={'PATH':'/usr/bin:/bin'})
    sys.stdout.buffer.write(done.stdout);sys.stdout.flush();raise SystemExit(done.returncode)
else:raise SystemExit(64)
'''
ANOTHER={'id':'7'*64,'name':'c3po-api-1','state':'running'}

@pytest.fixture(scope='module')
def certs(tmp_path_factory):
    if c3.openssl() is None:pytest.skip('no openssl program')
    return c3.certificates(tmp_path_factory.mktemp('authority'))

@pytest.fixture
def tree(tmp_path):
    root=Path(str(tmp_path)).resolve()/'root';root.mkdir(mode=0o755)
    for path in ('proc/sys/kernel/random','usr/bin'):(root/path).mkdir(parents=True,mode=0o755)
    for path in list(root.rglob('*'))+[root]:os.chmod(str(path),0o755)
    (root/'proc/sys/kernel/random/boot_id').write_bytes(BOOT)
    return root

def engine(tree,prelude,listed=(ANOTHER,)):
    path=tree/'usr/bin/docker'
    path.write_text(FAKE_DOCKER%{'python':__import__('sys').executable,'tree':str(tree),'image':IMAGE,'tag':c3.TAG,'revision':c3.RELEASE,
                                 'prelude':prelude.decode(),'listed':list(listed)})
    os.chmod(str(path),0o755)

def run(tree,monkeypatch):
    """One run in this process with the module's own Native; only the path of the docker binary is moved into the tree."""
    k=c3.K();m=k.m
    class Moved(m.Native):
        def run(self,argv,*arguments):return m.Native.run(self,[str(tree)+argv[0]]+list(argv[1:]),*arguments)
    docs=f.Docs(k,c3.fields(image_id=IMAGE,image_revision=c3.RELEASE,evidence_boot_id_sha256=f.sha(BOOT.strip())),now=c3.NOW)
    with oslevel.Substitute(tree) as record:receipt=docs.run(Moved())
    log=Path(str(tree)+'.docker.log');calls=[json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return docs,receipt,record.calls,calls

WRITING=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND|os.O_EXCL
def assert_read_only(calls):
    null=[entry for entry in calls if entry['call']=='open' and entry['path']=='ABSOLUTE:'+os.devnull]
    opens=[entry for entry in calls if entry['call']=='open' and entry not in null]
    assert opens and all(entry['flags']&os.O_NOFOLLOW and not entry['flags']&WRITING for entry in opens),'every open is O_NOFOLLOW and carries no write or create flag'
    assert all(entry['by_dir_fd'] or entry['path']=='/' for entry in opens),'only "/" is opened by absolute path'
    assert not [entry for entry in calls if entry['call'] in ('mkdir','link','unlink','fsync','flock','umask','readlink')],'nothing that changes the tree'

def test_native_run_with_a_real_engine_stand_in_and_the_real_script_verifies_tls(tree,certs,monkeypatch):
    server=c3.Server(certs,'good')
    try:
        engine(tree,c3.prelude([('127.0.0.1',server.port)],certs['ca']));docs,receipt,calls,docker=run(tree,monkeypatch)
    finally:server.close()
    m=c3.K().m
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('METADATA_ONLY_REQUIRES_REVIEW','TLS_VERIFIED_TO_THE_PROVIDER_HOST',None),receipt
    assert receipt['probe']['tls']['leaf_sha256']==certs['leaf_sha256'] and receipt['tls_verified'] is True and receipt['container_removed'] is True
    assert receipt['containers_after']=={'status':'COMPLETE','code':None,'before':1,'after':1,'not_there_before':0,'name_present':False,'rows':[]}
    assert [call['argv'][:2] for call in docker]==[['image','inspect'],['image','inspect'],['ps','-a'],['run','--rm'],['ps','-a']]
    assert [call['argv'][-1] for call in docker[:2]]==[IMAGE,c3.TAG]
    run_call=docker[3]
    assert run_call['argv']==m.PROBE_PREFIX+['--name','hostops02-tls-'+docs.go16(),IMAGE,'python','-I','-B','-']
    assert run_call['stdin_sha256']==m.PROBE_SCRIPT_SHA256,'the engine got the pinned bytes and nothing else'
    for call in docker:
        assert call['cwd']=='/' and call['environment']=={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'},call['environment']
        assert call['stdin_sha256'] is None or call is run_call
    assert server.connections==[{'server_name':'socket.massive.com','handshake':True,'application_bytes':0}]
    assert_read_only(calls)

def test_native_run_reports_what_the_real_script_says_when_tls_is_not_verified(tree,certs,monkeypatch):
    server=c3.Server(certs,'other_name')
    try:
        engine(tree,c3.prelude([('127.0.0.1',server.port)],certs['ca']));docs,receipt,calls,docker=run(tree,monkeypatch)
    finally:server.close()
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('PARTIAL_METADATA_REQUIRES_REVIEW','PROBE_RAN_TLS_NOT_VERIFIED','TLS_CERTIFICATE_NOT_VERIFIED')
    assert receipt['probe']['tls']['verify_code']==62 and receipt['tls_verified'] is False and receipt['container_removed'] is True
    assert_read_only(calls)

def test_native_run_finds_the_name_of_this_go_taken_and_starts_nothing(tree,certs,monkeypatch):
    k=c3.K();docs=f.Docs(k,c3.fields(image_id=IMAGE,image_revision=c3.RELEASE,evidence_boot_id_sha256=f.sha(BOOT.strip())),now=c3.NOW)
    engine(tree,b'',listed=(ANOTHER,{'id':'8'*64,'name':'hostops02-tls-'+docs.go16(),'state':'created'}))
    docs,receipt,calls,docker=run(tree,monkeypatch)
    assert (receipt['status'],receipt['code'])==('REFUSED','CONTAINER_NAME_TAKEN') and [call['argv'][:1] for call in docker]==[['image'],['image'],['ps']]
    assert_read_only(calls)
