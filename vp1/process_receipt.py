"""Candidate receipt codec. Raw hashes are integrity, never process authentication.

This implementation accepts FIXTURE transcripts only. REAL needs an installed,
independently measured supervisor/anchor; none is supplied or fabricated here.
"""
import base64
import json
from dataclasses import dataclass
from pathlib import Path
import veto_emitter as v
import finite_batch as batch

SCHEMA='R2D2_ISOLATED_VETO_EMISSION_RECEIPT_CANDIDATE_V1'
FIELDS={'schema','mode','nonce','worker_sha256','worker_pid','derivation_rule_sha256',
        'spec_sha256','consumer_template_sha256','observation_sha256','authority_sha256',
        'view_base64','view_sha256','operational_GO'}

class Refused(ValueError):pass
def need(ok,code):
    if not ok:raise Refused(code)

def parse(raw):
    need(type(raw)is bytes and 0<len(raw)<=v.MAX_ORIGINAL_BYTES,'PROCESS_RECEIPT_BYTES')
    def pairs(items):
        out={}
        for k,x in items:need(k not in out,'PROCESS_RECEIPT_DUPLICATE');out[k]=x
        return out
    try:row=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in()).throw(ValueError()))
    except Exception:raise Refused('PROCESS_RECEIPT_JSON')from None
    need(type(row)is dict and set(row)==FIELDS and v.canonical(row)+b'\n'==raw
         and row['schema']==SCHEMA,'PROCESS_RECEIPT_FIELDS')
    need(row['mode']=='FIXTURE','PROCESS_REAL_ORIGIN_UNVERIFIED')
    need(type(row['nonce'])is str and len(row['nonce'])==32 and all(c in'0123456789abcdef'for c in row['nonce']),
         'PROCESS_RECEIPT_NONCE')
    need(type(row['worker_pid'])is int and row['worker_pid']>0 and row['operational_GO']is False,
         'PROCESS_RECEIPT_METADATA')
    need(all(type(row[k])is str and v.SHA.fullmatch(row[k])for k in FIELDS if k.endswith('_sha256')),
         'PROCESS_RECEIPT_PIN')
    try:view=base64.b64decode(row['view_base64'],validate=True)
    except Exception:raise Refused('PROCESS_RECEIPT_VIEW_BASE64')from None
    need(v.digest(view)==row['view_sha256'],'PROCESS_RECEIPT_VIEW_HASH')
    return row,view

def make(emission,*,nonce,worker_sha256,worker_pid,rule_sha256,template_sha256):
    need(type(emission)is v.Emission and emission.mode=='FIXTURE'and emission.operational_GO is False,
         'PROCESS_EMISSION_FIXTURE_ONLY')
    row={'schema':SCHEMA,'mode':'FIXTURE','nonce':nonce,'worker_sha256':worker_sha256,'worker_pid':worker_pid,
         'derivation_rule_sha256':rule_sha256,'spec_sha256':emission.spec_sha256,
         'consumer_template_sha256':template_sha256,'observation_sha256':emission.observation_sha256,
         'authority_sha256':emission.authority_sha256,'view_base64':base64.b64encode(emission.view_raw).decode(),
         'view_sha256':emission.view_sha256,'operational_GO':False}
    raw=v.canonical(row)+b'\n';parse(raw);return raw

def validate(raw,emission,*,spec,rule_sha256,worker_sha256,nonce):
    row,view=parse(raw)
    need(type(emission)is v.Emission and emission.mode=='FIXTURE'
         and view==emission.view_raw and row['view_sha256']==emission.view_sha256
         and row['spec_sha256']==emission.spec_sha256==v.digest(v.canonical(spec)+b'\n')
         and row['authority_sha256']==emission.authority_sha256==spec['authority_sha256']
         and row['observation_sha256']==emission.observation_sha256
         and row['consumer_template_sha256']==spec['consumer_config_template_sha256']
         and row['derivation_rule_sha256']==rule_sha256 and row['worker_sha256']==worker_sha256
         and row['nonce']==nonce,'PROCESS_RECEIPT_BINDING')
    return row

def l12_view(raw,*,spec_raw,rule_raw,rule_sha256,worker_sha256,nonce,now):
    """Monday subset: reject a 10s view; never shorten or renew one to make 5s.

    Metadata/transcript fields remain FIXTURE. A REAL receiver must authenticate
    the actual supervised pipe/receipt before this pure conversion; unavailable.
    Sunday target12 factual11 observations use the separate Sunday codec.
    """
    row,view=parse(raw);spec=v.read_spec(spec_raw);v.check_derivation_rule(rule_raw,rule_sha256,spec)
    emission=v.Emission(row['mode'],view,row['view_sha256'],row['observation_sha256'],row['authority_sha256'],row['spec_sha256'])
    validate(raw,emission,spec=spec,rule_sha256=rule_sha256,worker_sha256=worker_sha256,nonce=nonce)
    try:
        doc=json.loads(view.decode().split('```json\n',1)[1].split('\n```',1)[0]);body=doc['body']
        need(doc['schema']==v.DOCUMENT_SCHEMA and doc['kind']=='VETO_VIEW'and doc['state']=='DRAFT',
             'PROCESS_VIEW_NOT_FIXTURE')
        c=spec['context'];need(body['epoch']==c['epoch']and body['day']==c['day']=='2026-10-12'
             and body['order_sha']==c['order_sha']and body['evidence_sha']==row['observation_sha256']
             and body['role']=='FABLE'and body['status']=='VERIFIED'and body['owner_veto']is False,
             'PROCESS_VIEW_CONTEXT')
        observed,until=map(v.instant,(body['observed_at'],body['valid_until']))
        need(observed==v.instant(spec['view_opens_at'])and observed<=now<until
             and 0<(until-observed).total_seconds()<=5,'PROCESS_VIEW_UNIFIED_TTL')
        need(not set(body['revoked_shas']).intersection(set(spec['required_pins'])|{rule_sha256}),
             'PROCESS_VIEW_REVOKED')
    except (Refused,v.Refused):raise
    except Exception:raise Refused('PROCESS_VIEW_INVALID')from None
    return batch.VetoView(view,row['authority_sha256'],'ALLOW',observed,until)
