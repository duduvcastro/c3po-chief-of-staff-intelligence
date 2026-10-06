"""Fixtures of K12w: one bound request per mode, built from the emulated host as a binder would copy the rows from a
TREE read of k12_collect. Synthetic only (tests/k12emu.py)."""
from pathlib import Path

import family as f
import k12emu as e

HERE=Path(__file__).resolve().parent
DIRECTORY=HERE.parent
LAUNCH_SHA='5e'*32
MOMENTS={'LAUNCH':e.utc(e.DAY,'10:40:00'),'PERSIST':e.utc(e.DAY,'10:46:30'),'STOP':e.utc(e.DAY,'10:41:00'),'REMOVE':'2026-10-09T20:40:00+00:00'}
CHAINS={'LAUNCH':('config','manifests','reader_config','docker_cli','journal','data','receipts'),'PERSIST':('receipts',),'STOP':('manifests',),
        'REMOVE':('receipts',)}

def K():return f.load(DIRECTORY)

def fields(host,mode,body=None,launch=LAUNCH_SHA,removals=None):
    return {'mode':mode,'capacity_request':None if mode=='REMOVE' else e.member(body or e.capacity_request()),
            'launch_request_sha256':launch if mode in ('PERSIST','STOP') else None,'removals':removals if mode=='REMOVE' else None,
            'parent_rows':e.chains(host,CHAINS[mode]),'evidence_boot_id_sha256':f.BOOT_SHA}

def removal(item,day,index,launch=LAUNCH_SHA):
    return {'day':day,'window_slot':index,'container_id':item['Id'],'image_id':item['Image'],'launch_request_sha256':launch,
            'capacity_request_sha256':e.sha(f.canonical(e.capacity_request(day,index)))}

def remove_world(k):
    """Three containers of the week: Tuesday's primary (published, its private receipt on the host), Wednesday's primary
    (stopped by a veto before its view: no line, no receipt) and Wednesday's contingency 1 that never started."""
    host=e.world(k,windows=(1,2,3))
    one=e.launched(host,k,'2026-10-06',1);e.at_view(host,one['Name'][1:],day='2026-10-06');e.persisted(host,k,one,'2026-10-06',1)
    host.docker.stop_finished='2026-10-07T10:41:30.000000000Z'
    two=e.launched(host,k,'2026-10-07',1);host.docker.do_stop(['-t','5',two['Id']])      # rev 2: PERSIST keeps no receipt of a stop
    three=e.launched(host,k,'2026-10-07',2,state='created')
    return host,[removal(one,'2026-10-06',1),removal(two,'2026-10-07',1),removal(three,'2026-10-07',2)]

def case(mode='LAUNCH',now=None,**options):
    k=K();now=now or e.at(MOMENTS[mode])
    if mode=='REMOVE':
        host,items=remove_world(k);return f.Docs(k,fields(host,mode,removals=items),now=now),host
    host=e.world(k)
    if mode in ('PERSIST','STOP'):
        item=e.launched(host,k,request_sha=LAUNCH_SHA)
        if mode=='PERSIST':e.at_view(host,item['Name'][1:])
    return f.Docs(k,fields(host,mode,**options),now=now),host
