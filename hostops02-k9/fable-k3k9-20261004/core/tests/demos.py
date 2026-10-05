"""Fixtures of the two demonstration operations of the core (tests/demo_read, tests/demo_write): request plans built
from the emulated host exactly as a binder would copy them from a read-only receipt, and what the emulated containers do.
An operation built on the core writes the same kind of module for itself; nothing here is needed outside the core."""
import base64
from pathlib import Path

import family as f
import hostemu

HERE=Path(__file__).resolve().parent
READ=HERE/'demo_read'
WRITE=HERE/'demo_write'
DIRECTORIES={'selftest_read':READ,'selftest_write':WRITE}
TARGET='/selftest'
LEAF='selftest-20261005'
MARKER='marker.json'
KEYS={'C3PO_R2D2_V2_LIVE_POLICY_FILE':'/app/day-d-data/'+LEAF+'/policy.json','C3PO_R2D2_V2_LIVE_POLICY_SHA':'5'*64}
# What the pinned snippets "are": bytes that travel on standard input. The emulated container never executes them; the
# function a test installs as docker.on_run stands for what they do inside the container.
WRITE_SCRIPT=b'# selftest: create marker.json in the bound directory and print one line\n'
READ_SCRIPT=b'# selftest: list the bound directory and print one line\n'
POLICY=b'{"schema":"SYNTHETIC_POLICY"}'
def b64(raw):return base64.b64encode(raw).decode('ascii')
def override(keys=KEYS):return f.canonical({'services':{'r2d2-worker':{'environment':dict(keys)}}})

def writing_container(call):
    """The demonstration script of demo_write: it creates marker.json (0600) in the directory bound read-write."""
    assert call.stdin==WRITE_SCRIPT and call.network=='none' and call.read_only_root and call.command[:4]==['python','-I','-B','-']
    call.write(call.command[4]+'/'+MARKER,b'{}');return 0,f.canonical({'created':MARKER,'status':'DONE'})+b'\n'
def reading_container(call):
    """The demonstration script of demo_read: it lists the directory bound read-only."""
    assert call.stdin==READ_SCRIPT and call.network=='none' and all(mount['read_only'] for mount in call.mounts)
    return 0,f.canonical({'entries':call.listdir(TARGET),'status':'LISTED'})+b'\n'

def write_fields(host,*,container=True,recreate=True,parent=hostemu.DATA,open_root=hostemu.DATA,leaf=LEAF,files=None):
    files=[('POLICY','policy.json',POLICY,0o600),('OVERRIDE','compose.override.json',override(),0o600)] if files is None else files
    plan={'parent':hostemu.rows(host,parent),'open_root':open_root,'directory_name':leaf,
          'files':[{'key':key,'name':name,'content_b64':b64(raw),'sha256':f.sha(raw),'bytes':len(raw),'mode':mode} for key,name,raw,mode in files],
          'container':None,'recreate':None,'evidence_boot_id_sha256':f.BOOT_SHA}
    if container:
        plan['container']={'image_id':hostemu.BACKEND,'script_b64':b64(WRITE_SCRIPT),'script_sha256':f.sha(WRITE_SCRIPT),'target':TARGET,
                           'arguments':[TARGET],'creates':MARKER}
    if recreate:
        plan['recreate']={'project':hostemu.PROJECT,'env_file':hostemu.ENV_FILE,'files':[hostemu.COMPOSE_FILE],'override_key':'OVERRIDE',
                          'service':'r2d2-worker','container':hostemu.WORKER,'build_sha':hostemu.REVISION,'environment':dict(KEYS),
                          'lock_directory':hostemu.rows(host,hostemu.LOCK_DIRECTORY),'lock_open_root':hostemu.DEPLOY,'lock_name':hostemu.LOCK_NAME,'lock_wait_seconds':20}
    return plan

def read_fields(host,*,docker=True,verify=True,render=True,environment=None):
    directories=[('DEPLOY',hostemu.DEPLOY,hostemu.DEPLOY),('LOCKS',hostemu.LOCK_DIRECTORY,hostemu.DEPLOY),('DATA',hostemu.DATA,hostemu.DATA),('ETC','/etc',None)]
    plan={'directories':[{'key':key,'rows':hostemu.rows(host,path),'open_root':open_root} for key,path,open_root in directories],
          'image':None,'containers':None,'environment':None,'verify':None,'render':None,
          'file':{'directory_key':'DEPLOY','name':'.deploy-version','sha256':f.sha((hostemu.REVISION+'\n').encode()),'bytes':41},
          'lock':{'directory_key':'LOCKS','name':hostemu.LOCK_NAME},'evidence_boot_id_sha256':f.BOOT_SHA}
    if docker:
        plan['image']={'reference':'c3po/backend:production','image_id':hostemu.BACKEND,'revision':hostemu.REVISION}
        plan['containers']=['%s-%s-1'%(hostemu.PROJECT,service) for service in hostemu.SERVICES]
        plan['environment']={'container':hostemu.WORKER,'expected':{'C3PO_BUILD_SHA':hostemu.REVISION,'C3PO_SERVICE_NAME':'r2d2-worker'} if environment is None else environment}
    if docker and verify:
        plan['verify']={'script_b64':b64(READ_SCRIPT),'script_sha256':f.sha(READ_SCRIPT),'directory_key':'DATA','target':TARGET,
                        'expect':{'entries':sorted(host.tree.get(hostemu.DATA).children),'status':'LISTED'}}
    if docker and render:
        plan['render']={'project':hostemu.PROJECT,'env_file':hostemu.ENV_FILE,'files':[hostemu.COMPOSE_FILE],'override_b64':b64(override()),
                        'override_sha256':f.sha(override()),'service':'r2d2-worker','build_sha':hostemu.REVISION,'environment':dict(KEYS)}
    return plan

def case(name,now=None,**options):
    """(docs, host): a bound fixture of one demonstration operation that completes on a fresh emulated host."""
    k=f.load(DIRECTORIES[name]);host=f.world(k)
    if name=='selftest_write':
        host.docker.on_run=writing_container;return f.Docs(k,write_fields(host,**options),now=now),host
    host.docker.on_run=reading_container;return f.Docs(k,read_fields(host,**options),now=now),host
