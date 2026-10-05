"""The real system calls of DBR, made by the source's own unmodified Native on a private temporary tree that stands in
for '/', with a real process behind the docker binary. Nothing of Native is overridden but the path of that binary
(moved into the temporary tree); '/' and the uid are substituted on the os module (the core's tests/oslevel.py).

What stands for docker is a program at <tree>/usr/bin/docker. For `run` it executes the bytes it receives on standard
input (the pinned snippet) with a real interpreter, the two bind targets of the argv mapped to the bind sources in the
tree, and stub modules in place of psycopg and of the application (there is no database here). As an ordinary user the
snippet's own private-file check refuses the two credential files (their owner is not uid 0 outside the
substitution), so the line it prints says so: this proves the process, the argv, the standard input, the line and its
check, and the host side's lstat of the credentials; the queries themselves are proved by tests/test_dbr.py."""
import json
import os
from pathlib import Path
import stat
import sys
import time

import pytest

import dbr
import family as f
import oslevel

BOOT=b'0f8fad5b-d9cb-469f-a165-70867728950e\n'
IMAGE='sha256:'+'fb'*32
rows=oslevel.rows
FAKE_DOCKER='''#!%(python)s -B
import hashlib,json,os,subprocess,sys
TREE=%(tree)r;IMAGE=%(image)r;REVISION=%(revision)r;STUBS=%(stubs)r
arguments=sys.argv[1:];data=sys.stdin.buffer.read()
with open(TREE+'.docker.log','a') as log:
    log.write(json.dumps({'argv':arguments,'stdin_sha256':hashlib.sha256(data).hexdigest() if data else None,'cwd':os.getcwd(),
                          'environment':{key:value for key,value in os.environ.items() if not key.startswith('__CF')}},sort_keys=True)+'\\n')
if arguments[:3]==['image','inspect','--format'] and len(arguments)==5:
    if arguments[4]!=IMAGE:raise SystemExit(1)
    print(json.dumps({'id':IMAGE,'repo_tags':['c3po/backend:production'],'revision':REVISION}))
elif arguments[:4]==['ps','-a','--no-trunc','--format'] and len(arguments)==5:pass
elif arguments[:1]==['run']:
    binds={}
    for word in arguments:
        if word.startswith('type=bind,'):
            fields=dict(item.split('=',1) for item in word.split(',') if '=' in item);binds[fields['target']]=TREE+fields['source']
    command=arguments[arguments.index(IMAGE)+1:];assert command[:4]==['python','-I','-B','-']
    words=[]
    for word in command[4:]:
        mapped=[binds[target]+word[len(target):] for target in binds if word==target or word.startswith(target+'/')]
        words.append(mapped[0] if mapped else word)
    done=subprocess.run([sys.executable,'-B','-']+words,input=data,stdout=subprocess.PIPE,env={'PYTHONPATH':STUBS,'PATH':'/usr/bin:/bin'})
    sys.stdout.buffer.write(done.stdout);sys.stdout.flush();raise SystemExit(done.returncode)
else:raise SystemExit(64)
'''

@pytest.fixture
def tree(tmp_path):
    root=Path(str(tmp_path)).resolve()/'root';root.mkdir(mode=0o755)
    for path in ('var/lib/c3po','proc/sys/kernel/random','usr/bin'):(root/path).mkdir(parents=True,mode=0o755)
    for path in list(root.rglob('*'))+[root]:os.chmod(path,0o755)
    for path in ('var/lib/c3po/r2d2-v2-k9-20261005','var/lib/c3po/r2d2-v2-k9-20261005/secrets','var/lib/c3po/r2d2-v2-k9-20261005/secrets/emitter'):
        (root/path).mkdir();os.chmod(root/path,0o700)
    secrets=root/'var/lib/c3po/r2d2-v2-k9-20261005/secrets'
    for path,content in ((secrets/'provider.env',dbr.PROVIDER_FILE),(secrets/'risk-db.env',dbr.RISK_FILE),(secrets/'emitter/password',dbr.PASSWORD_CANARY.encode())):
        path.write_bytes(content);os.chmod(path,0o600)
    (root/'proc/sys/kernel/random/boot_id').write_bytes(BOOT)
    stubs=Path(str(tmp_path)).resolve()/'stubs';(stubs/'app').mkdir(parents=True)
    (stubs/'psycopg.py').write_text('def connect(*a,**k):raise AssertionError("no database here")\n')
    (stubs/'app'/'__init__.py').write_text('');(stubs/'app'/'r2d2_v2_causal_emitter.py').write_text('def _authority(connection):raise AssertionError("no database")\n')
    path=root/'usr/bin/docker'
    path.write_text(FAKE_DOCKER%{'python':sys.executable,'tree':str(root),'image':IMAGE,'revision':dbr.hostemu.REVISION,'stubs':str(stubs)});os.chmod(path,0o755)
    return root

def fields(tree,mode='QUERIES'):
    plan={'mode':mode,'secrets_chain':rows(tree,dbr.SECRETS),'image_id':IMAGE,'image_revision':dbr.hostemu.REVISION,'session':None,
          'release_receipt_sha256':None,'expected':None,'priv_receipt':None,'evidence_boot_id_sha256':f.sha(BOOT.strip())}
    if mode=='QUERIES':
        plan.update(session='2026-10-05',release_receipt_sha256=dbr.RELEASE,expected={'epoch_rows':None,'binding_committed':None},
                    priv_receipt=dbr.priv_receipt(boot_id_sha256=f.sha(BOOT.strip())))
    return plan

def run(tree,plan=None):
    k=dbr.K();m=k.m
    class Moved(m.Native):
        def run(self,argv,*arguments):return m.Native.run(self,[str(tree)+argv[0]]+list(argv[1:]),*arguments)
    docs=f.Docs(k,plan or fields(tree),now=dbr.NOW)
    with oslevel.Substitute(tree) as record:receipt=docs.run(Moved(),clock=lambda:dbr.NOW,monotonic=time.monotonic)
    log=Path(str(tree)+'.docker.log');calls=[json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return docs,receipt,record.calls,calls

WRITING=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND|os.O_EXCL
def test_native_run_with_a_real_process_behind_docker_and_the_real_snippet(tree):
    docs,receipt,calls,docker=run(tree);m=docs.k.m
    assert [entry['argv'][:2] for entry in docker]==[['image','inspect'],['ps','-a'],['run','--rm'],['ps','-a']]
    assert docker[2]['stdin_sha256']==m.DBR_SNIPPET_SHA256 and docker[2]['argv'][-6:]==['QUERIES','/c3po-dbr-risk-db.env','/c3po-dbr-emitter/password',dbr.EPOCH,'2026-10-05',dbr.RELEASE]
    assert all(entry['environment']=={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'} and entry['cwd']=='/' for entry in docker)
    query=receipt['items']['query'];assert query['status']=='COMPLETE' and query['returncode']==0,query
    line=query['line']
    if os.geteuid()!=0:
        assert line['risk_url']=={'status':'UNAVAILABLE','code':'FILE_NOT_PRIVATE'} and line['emitter_password']=={'status':'UNAVAILABLE','code':'FILE_NOT_PRIVATE'}
        assert line['epoch_row']==line['binding']=={'status':'UNAVAILABLE','code':'RISK_URL_UNAVAILABLE'} and line['emitter']=={'status':'UNAVAILABLE','code':'EMITTER_PASSWORD_UNAVAILABLE'}
        assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and 'QUERY_UNAVAILABLE_RISK_URL' in receipt['findings']
    assert receipt['items']['secrets']['findings']==[] and receipt['items']['secrets']['entries']==3 and receipt['items']['secrets']['emitter_entries']==1
    opens=[entry for entry in calls if entry['call']=='open' and entry['path']!='ABSOLUTE:'+os.devnull]
    assert all(entry['flags']&os.O_NOFOLLOW and not entry['flags']&WRITING for entry in opens)
    assert not [entry for entry in opens if entry['path'].endswith(('risk-db.env','password','provider.env'))],'no credential is opened by this process'
    assert not [entry for entry in calls if entry['call'] in ('mkdir','link','unlink','fsync','umask','flock')]
    assert dbr.clean(receipt)

def test_native_credential_not_private_holds_the_container_back(tree):
    plan=fields(tree);os.chmod(tree/'var/lib/c3po/r2d2-v2-k9-20261005/secrets/risk-db.env',0o640)
    docs,receipt,calls,docker=run(tree,plan)
    assert 'CREDENTIAL_NOT_PRIVATE' in receipt['findings'] and [entry['argv'][:2] for entry in docker]==[['image','inspect'],['ps','-a']]
    os.chmod(tree/'var/lib/c3po/r2d2-v2-k9-20261005/secrets/risk-db.env',0o600);os.symlink('/nowhere',tree/'var/lib/c3po/r2d2-v2-k9-20261005/secrets/emitter/extra')
    docs,receipt,calls,docker=run(tree,plan)
    assert 'EMITTER_DIRECTORY_NOT_AS_PLACED' in receipt['findings'] and not [entry for entry in docker if entry['argv'][:1]==['run']]


def test_native_priv_with_a_real_process_binds_only_the_reader_file(tree):
    docs,receipt,calls,docker=run(tree,fields(tree,'PRIV'))
    assert [entry['argv'][:2] for entry in docker]==[['image','inspect'],['ps','-a'],['run','--rm'],['ps','-a']]
    run_argv=docker[2]['argv'];assert run_argv[-2:]==['PRIV','/c3po-dbr-risk-db.env']
    assert [word for word in run_argv if word.startswith('type=bind,')]==['type=bind,source=%s/risk-db.env,target=/c3po-dbr-risk-db.env,readonly'%dbr.SECRETS]
    line=receipt['items']['query']['line'];assert sorted(line)==['mode','reader_privileges','risk_url']
    if os.geteuid()!=0:assert line['reader_privileges']=={'status':'UNAVAILABLE','code':'RISK_URL_UNAVAILABLE'}
    assert dbr.clean(receipt)
