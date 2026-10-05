"""Fixtures of K12r: one bound request per mode, built from the emulated host (tests/k12emu.py). Synthetic only."""
from pathlib import Path

import family as f
import k12emu as e

HERE=Path(__file__).resolve().parent
DIRECTORY=HERE.parent
LAUNCH_SHA='5e'*32
MOMENTS={'COLLECT':e.utc(e.DAY,'10:46:30'),'TREE':'2026-10-05T20:40:00+00:00'}

def K():return f.load(DIRECTORY)

def fields(host,mode,body=None,launch=LAUNCH_SHA,journal=e.JOURNAL):
    if mode=='TREE':
        return {'mode':'TREE','capacity_request':None,'launch_request_sha256':None,'tree_journal':journal,'parent_rows':None,'evidence_boot_id_sha256':None}
    return {'mode':mode,'capacity_request':e.member(body or e.capacity_request()),'launch_request_sha256':launch,'tree_journal':None,
            'parent_rows':e.chains(host,['manifests','receipts','data']),'evidence_boot_id_sha256':f.BOOT_SHA}

def published(k,host,index=1,line=None,code=0,publish=True,persist=True,two_links=False):
    """The window as K12w LAUNCH, the writer at the view and K12w PERSIST leave it."""
    item=e.launched(host,k,index=index,request_sha=LAUNCH_SHA,body=e.capacity_request(index=index))
    e.at_view(host,item['Name'][1:],line=e.writer_line(index=index) if line is None else line,code=code,publish=publish,two_links=two_links)
    if persist:e.persisted(host,k,item,index=index)
    return item

def case(mode='COLLECT',now=None,**options):
    k=K();host=e.world(k);now=now or e.at(MOMENTS[mode])
    if mode=='COLLECT':published(k,host)
    return f.Docs(k,fields(host,mode,**options),now=now),host
