"""Fixtures of K13r (the reader liveness readback): the emulated host with the reader running as the activation leaves
it (the units loaded, the timer enabled and waiting, the service active, one container c3po-reader of the pinned image
with its four read-only binds and the launcher command), or stopped as the deactivation leaves it, and the request
plan. The container's inspect members that the core's emulation does not model (Args, HostConfig.Init and
ReadonlyRootfs, Mounts) are set on the emulated objects here; the core is never edited. Every value is synthetic."""
import json
from pathlib import Path

import family as f
import hostemu

HERE=Path(__file__).resolve().parent
DIRECTORY=HERE.parent
SERVICE='c3po-reader.service'
TIMER='c3po-reader.timer'
BINDS=[('/mnt/day-d-data','/app/day-d-data'),('/var/lib/c3po-bar/journal','/c3po-bar-journal'),('/var/lib/c3po-capacity','/c3po-capacity'),
       ('/etc/c3po-reader/launcher','/c3po-reader'),('/var/lib/c3po/r2d2-v2-source-20261005','/c3po-source')]
COMMANDS={'api':['uvicorn','app.main:app'],'investor-relations-worker':['-m','app.ir_worker'],'valuation-worker':['-m','app.valuation_worker'],
          'server-usage-worker':['-m','app.server_usage_worker'],'r2d2-shadow-candidate-worker':['-m','app.r2d2_shadow_candidate_worker'],
          'r2d2-worker':['-m','app.r2d2_worker'],'web':['server.js'],'db':['postgres']}

def K():return f.load(DIRECTORY)

def mount(source,target,rw=False):
    return {'Type':'bind','Source':source,'Destination':target,'Mode':'','RW':rw,'Propagation':'rprivate'}
def reader_container(image=hostemu.BACKEND,running=True,name='c3po-reader',args=None,binds=None):
    item=hostemu.container(name,image,image,['C3PO_DATABASE_URL=postgresql://c3po:'+hostemu.SECRET+'@db/c3po'],running=running)
    item['Path']='python';item['Args']=['-I','-B','/c3po-reader/reader_launcher.py'] if args is None else list(args)
    item['HostConfig'].update(Init=True,ReadonlyRootfs=True,NetworkMode='c3po_internal');item['Config']['User']='0:0'
    item['Mounts']=[mount(source,target) for source,target in (BINDS if binds is None else binds)]
    return item

def prepare(host,live=True):
    for item in host.docker.containers:
        service=item['Config']['Labels'].get('com.docker.compose.service')
        item['Path']='python';item['Args']=list(COMMANDS.get(service,['-m','app.unknown']))
        item['HostConfig'].update(Init=False,ReadonlyRootfs=False);item['Mounts']=[mount('/opt/x','/x',True)]
    # a timer has no NRestarts: the emulated timer has none, as systemd prints none for it
    common={'LoadState':'loaded','DropInPaths':'','Result':'success'}
    if live:
        host.units[SERVICE]=dict(common,Id=SERVICE,ActiveState='active',SubState='running',UnitFileState='static',FragmentPath='/etc/systemd/system/'+SERVICE,NRestarts='0')
        host.units[TIMER]=dict(common,Id=TIMER,ActiveState='active',SubState='waiting',UnitFileState='enabled',FragmentPath='/etc/systemd/system/'+TIMER)
        host.is_enabled[TIMER]='enabled';host.docker.containers.append(reader_container())
    else:
        host.units[SERVICE]=dict(common,Id=SERVICE,ActiveState='inactive',SubState='dead',UnitFileState='static',FragmentPath='/etc/systemd/system/'+SERVICE,NRestarts='0')
        host.units[TIMER]=dict(common,Id=TIMER,ActiveState='inactive',SubState='dead',UnitFileState='disabled',FragmentPath='/etc/systemd/system/'+TIMER)
        host.is_enabled[TIMER]='disabled'
    return host

def fields(mode='LIVE'):return {'mode':mode,'image_id':hostemu.BACKEND,'evidence_boot_id_sha256':f.BOOT_SHA,'source_target':'/c3po-source'}
def case(now=None,mode='LIVE',setup=None):
    k=K();host=prepare(f.world(k),live=mode=='LIVE')
    if setup is not None:setup(host)
    return f.Docs(k,fields(mode),now=now),host

def state_of(host):
    return host.tree.snapshot(),json.dumps(host.docker.containers,sort_keys=True),json.dumps(host.docker.images,sort_keys=True),json.dumps(host.units,sort_keys=True)
