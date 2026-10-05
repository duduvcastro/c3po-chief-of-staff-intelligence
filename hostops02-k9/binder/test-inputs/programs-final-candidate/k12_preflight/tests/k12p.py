"""Fixtures of K12p: the bound request of D0 for the primary window of Tuesday 06/10 (tests/k12emu.py). Synthetic only."""
from pathlib import Path

import family as f
import k12emu as e

HERE=Path(__file__).resolve().parent
DIRECTORY=HERE.parent
MOMENT=e.utc(e.DAY,'10:30:00')
CHAINS=('config','manifests','reader_config','docker_cli','journal','data','receipts')
CLAIM=e.RECEIPTS+'/k12-2026-10-06-preflight.claim.json'
CHECKS={'release_verified':True,'capacity_config_loaded':True,'journal_catalog_opened':True,'epoch_row_read':True,'chains_verified':True,
        'payload_contract_valid':True,'go_files':2,'directory_checked':True,'directory_writable':True,'day_is_today':True,'before_cutoff':True}

def K():return f.load(DIRECTORY)

def preflight_line(**changes):
    values=dict(status='PREFLIGHT_OK',code=None,mode='PREFLIGHT',checks=dict(CHECKS),windows={'admission':{'not_before':'a'},'bar_manifest':{'not_before':'b'}})
    values.update(changes)
    for key in ('prepare_status','stale_temporaries','repaired_temporaries'):values.setdefault(key,None)
    line=e.writer_line(**{key:value for key,value in values.items() if key not in ('prepare_status','stale_temporaries','repaired_temporaries')})
    import json
    body=json.loads(line)
    for key in ('stale_temporaries','repaired_temporaries'):body.pop(key,None)
    for key,value in values.items():
        if key in ('prepare_status','stale_temporaries','repaired_temporaries') and value is not None:body[key]=value
    return (json.dumps(body,sort_keys=True,separators=(',',':'))+'\n').encode()

def fields(host,body=None):
    return {'capacity_request':e.member(body or e.capacity_request()),'parent_rows':e.chains(host,CHAINS),'evidence_boot_id_sha256':f.BOOT_SHA}

def world(k,code=0,line=None):
    host=e.world(k);calls=[]
    def behave(call):
        calls.append(call);return code,(preflight_line() if line is None else line)
    host.docker.on_preflight=behave;host.preflight_calls=calls;return host

def case(now=None,**options):
    k=K();host=world(k);return f.Docs(k,fields(host,**options),now=now or e.at(MOMENT)),host
