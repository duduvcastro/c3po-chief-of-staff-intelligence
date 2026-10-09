"""Synthetic bridge only. This file cannot authorize REAL."""
from datetime import datetime,timedelta,timezone
import json
from hot_runtime import RuntimeBindings,GENERAL,canonical,sha,iso
BRIDGE_MODE='FIXTURE'
GENERAL_CASE='normal'
CALLS=[]
def authorize_hot(registry_raw,inputs,phase,now):
    CALLS.append(phase)
    if GENERAL_CASE=='authority_boolean':return True
def bootstrap_hot(registry_raw,inputs,modules):
    return RuntimeBindings(None,None,None,None,None,None)
def general_read(registry_raw,inputs,before):
    r=json.loads(registry_raw);now=datetime.now(timezone.utc)
    if GENERAL_CASE=='old':now-=timedelta(seconds=6)
    if GENERAL_CASE=='future':now+=timedelta(seconds=1)
    until=now+timedelta(seconds=20)
    if GENERAL_CASE=='expired':until=now-timedelta(seconds=1)
    required=sorted({sha(registry_raw),r['authority_sha256'],r['general_authority_sha256']}|
        {v['sha256']for group in ('programs','originals')for v in r[group].values()})
    if GENERAL_CASE=='missing_pin':required.pop()
    raw={'schema':GENERAL,'mode':'FIXTURE','epoch':r['epoch'],'day':r['day'],'purpose':'J_ADMISSION_WARM_IMAGE10',
         'source_identity':r['general_source_identity'],'authority_sha256':r['general_authority_sha256'],
         'registry_sha256':sha(registry_raw),'observed_at':iso(now),'valid_until':iso(until),'status':'ALLOW',
         'owner_veto':GENERAL_CASE=='veto','required_pins':required,'revoked_shas':[required[0]]if GENERAL_CASE=='revoked'else[]}
    if GENERAL_CASE=='wrong_day':raw['day']='2026-10-11'
    return canonical(raw)
def general_verify(registry_raw,inputs,original,now):
    if GENERAL_CASE=='verify_boolean':return True
