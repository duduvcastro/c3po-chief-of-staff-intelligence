"""Isolated FIXTURE worker candidate: bytes in, view+receipt+config bytes out.

No installer, actual authority anchor or REAL supervisor is present. REAL is
refused before loading any verifier. Do not use returned fixture transcripts as
process attestation or an operational input. No caller callable is deserialized.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import types
from datetime import datetime

DEPENDENCY_PINS={'veto_emitter': '91b70a91f550f432ffdad173d5bcb3e37e5cd6fde46ae413b20d0c461cbbb795', 'finite_batch': '311c2eaa47a223697324f7386b027b2e83c00926c00e7269fd4cfb9fe1c4fa25', 'process_receipt': 'a044d504c8d25c786c146d7e5ca2f7a0fd3a6a7c9d8c9107f30c99dcc84fdd4a', 'consumer_codec': '57933d7cf4d79b62ab1c7b291b8c460a743864c78d5ad5a3111c9b2c0b76f2b6', 'config_finalizer': 'b9cc2c86156ee468b7386def5f43387c8a916cc3693b4ccf57fbd4ec2a6ea94a'}
MAX_REQUEST_BYTES=12*1024*1024
SCHEMA='R2D2_ISOLATED_VETO_WORKER_REQUEST_CANDIDATE_V1'

def need(ok,code):
    if not ok:raise ValueError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(row):return json.dumps(row,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()+b'\n'
def strict(raw):
    def pairs(items):
        out={}
        for k,x in items:need(k not in out,'WORKER_DUPLICATE');out[k]=x
        return out
    row=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in()).throw(ValueError('WORKER_NONFINITE')))
    need(type(row)is dict and canonical(row)==raw,'WORKER_CANONICAL');return row

def read_source(name):
    path=Path(__file__).resolve().parent/(name+'.py');fd=os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd);need(stat.S_ISREG(before.st_mode)and before.st_nlink==1 and 0<before.st_size<=1024*1024,'WORKER_SOURCE_FILE')
        raw=os.read(fd,1024*1024+1);after=os.fstat(fd);named=os.stat(str(path),follow_symlinks=False)
        need((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==
             (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)==
             (named.st_dev,named.st_ino,named.st_size,named.st_mtime_ns,named.st_ctime_ns),'WORKER_SOURCE_CHANGED')
        need(sha(raw)==DEPENDENCY_PINS[name],'WORKER_SOURCE_HASH');return raw,str(path)
    finally:os.close(fd)

def load(name):
    raw,path=read_source(name);module=types.ModuleType(name);module.__file__=path;sys.modules[name]=module
    exec(compile(raw,path,'exec'),module.__dict__);read_source(name);return module

def run(row):
    need(set(row)=={'schema','mode','nonce','fixture_now','originals'}and row['schema']==SCHEMA,'WORKER_REQUEST_FIELDS')
    need(row['mode']=='FIXTURE','PROCESS_AUTHORITY_UNAVAILABLE')
    need(sys.flags.isolated==1 and sys.flags.dont_write_bytecode==1,'WORKER_NOT_ISOLATED')
    need(type(row['originals'])is dict and set(row['originals'])=={'veto_spec','derivation_rule','template','observation',
         'veto_authority','config_spec','config_authority','act_b','machine_order','fixture_verified_observation'},'WORKER_ORIGINALS')
    raws={}
    for name,encoded in row['originals'].items():
        need(type(encoded)is str,'WORKER_ORIGINAL_TYPE');raws[name]=base64.b64decode(encoded,validate=True)
        need(0<len(raws[name])<=1024*1024,'WORKER_ORIGINAL_SIZE')
    # Fixed exact source package only; no program path/code/object comes from stdin.
    v=load('veto_emitter');batch=load('finite_batch');receipt=load('process_receipt');codec=load('consumer_codec');c=load('config_finalizer')
    need(v.read_spec(raws['veto_spec'])['mode']=='FIXTURE'and c.parse(raws['config_spec'],'WORKER_CONFIG')['mode']=='FIXTURE',
         'WORKER_REAL_INPUT_REFUSED')
    now=v.instant(row['fixture_now']);clock=lambda:now
    obsrow=strict(raws['fixture_verified_observation'])
    for name in ('authority_required_pins','revoked_shas'):obsrow[name]=tuple(obsrow[name])
    need(obsrow['mode']=='FIXTURE','WORKER_REAL_INPUT_REFUSED')
    verified=v.VerifiedObservation(**obsrow);vs=v.read_spec(raws['veto_spec'])
    vb=v.VerifierBinding(vs['verifier']['identity'],vs['verifier']['implementation_sha256'],'FIXTURE',lambda *args:verified)
    rule_sha=sha(raws['derivation_rule'])
    emission=v.emit_view(raws['veto_spec'],raws['observation'],raws['veto_authority'],sha(raws['observation']),
        spec_sha256=sha(raws['veto_spec']),verifier=vb,clock=clock,consumer_template_raw=raws['template'],
        derivation_rule_raw=raws['derivation_rule'],derivation_rule_sha=rule_sha)
    worker_sha=sha(Path(__file__).read_bytes());cs=c.parse(raws['config_spec'],'WORKER_CONFIG')
    need(cs['process_worker_sha256']==worker_sha and cs['process_nonce']==row['nonce'],'WORKER_REQUEST_BINDING')
    er=receipt.make(emission,nonce=row['nonce'],worker_sha256=worker_sha,worker_pid=os.getpid(),rule_sha256=rule_sha,
                    template_sha256=sha(raws['template']))
    def config_fixture(*args):
        spec=c.parse(args[0],'WORKER_CONFIG_AUTHORITY');at=args[-1]
        return c.VerifiedConfigAuthority(mode='FIXTURE',spec_sha256=sha(args[0]),template_sha256=spec['template_sha256'],
            authority_sha256=spec['authority_sha256'],build_sha=spec['build_sha'],runtime_authority_sha256=spec['runtime_authority_sha256'],
            act_b_order_sha=spec['act_b_order_sha'],act_b_original_sha256=spec['act_b_original_sha256'],
            machine_order_original_sha256=spec['machine_order_original_sha256'],required_pins=tuple(spec['required_pins']),
            checked_at=at.isoformat(),valid_from='2026-10-12T12:59:00Z',valid_until='2026-10-12T13:01:00Z',
            permitted_settings_file=spec['settings_file'],permitted_veto_file=spec['veto_file'],identity_verified=True,
            static_pins_verified=True,document_authority_verified=True,act_b_machine_order_verified=True,
            runtime_snapshot_verified=True,output_rule_authorized=True,revocation_checked=True,revoked_shas=())
    cb=c.ConfigVerifierBinding(cs['verifier']['identity'],cs['verifier']['implementation_sha256'],'FIXTURE',config_fixture)
    final=c.finalize_config(raws['config_spec'],raws['template'],raws['config_authority'],spec_sha256=sha(raws['config_spec']),
        emission=emission,veto_spec_raw=raws['veto_spec'],veto_authority_raw=raws['veto_authority'],observation_raw=raws['observation'],
        act_b_raw=raws['act_b'],machine_order_raw=raws['machine_order'],veto_verifier=vb,config_verifier=cb,clock=clock,
        derivation_rule_raw=raws['derivation_rule'],emission_receipt_raw=er)
    lv=receipt.l12_view(er,spec_raw=raws['veto_spec'],rule_raw=raws['derivation_rule'],rule_sha256=rule_sha,
                        worker_sha256=worker_sha,nonce=row['nonce'],now=now)
    for name in DEPENDENCY_PINS:read_source(name)
    return {'schema':'R2D2_ISOLATED_VETO_WORKER_RESULT_CANDIDATE_V1','mode':'FIXTURE','status':'FIXTURE_COMPLETE',
        'operational_GO':False,'installed':False,'actual_process_attestation':False,'worker_pid':os.getpid(),
        'emission_receipt_base64':base64.b64encode(er).decode(),'config_base64':base64.b64encode(final.config_raw).decode(),
        'config_sha256':final.config_sha256,'view_base64':base64.b64encode(final.veto_raw).decode(),
        'view_sha256':final.veto_sha256,'l12_authority_sha256':lv.authority_sha256,'l12_verdict':lv.verdict,
        'l12_observed_at':lv.observed_at.isoformat(),'l12_valid_until':lv.valid_until.isoformat()}

def main():
    try:
        raw=sys.stdin.buffer.read(MAX_REQUEST_BYTES+1);need(0<len(raw)<=MAX_REQUEST_BYTES,'WORKER_REQUEST_SIZE')
        out=run(strict(raw));code=0
    except BaseException as error:
        candidate=error.args[0]if len(error.args)==1 and type(error.args[0])is str else'WORKER_REFUSED'
        safe=candidate if candidate.replace('_','').isalnum()and candidate.isupper()and len(candidate)<90 else'WORKER_REFUSED'
        out={'schema':'R2D2_ISOLATED_VETO_WORKER_RESULT_CANDIDATE_V1','mode':'UNVERIFIED','status':'REFUSED','code':safe,
             'operational_GO':False,'actual_process_attestation':False};code=3
    sys.stdout.buffer.write(canonical(out));return code

if __name__=='__main__':raise SystemExit(main())
