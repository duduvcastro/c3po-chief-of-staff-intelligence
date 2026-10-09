"""Fixed DATA-only process entrypoint, usable by the finite approved outer runner.

Invoke through a source-pinned isolated Python in the outer worker's own group.
There is no stdin JSON callback protocol, environment mutation, generic command,
installer, daemon or fallback. Files/bridge/registry must be actual elected
originals. FIXTURE is explicit and never yields an ISSUED image view.
"""
from __future__ import annotations
import base64
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from types import ModuleType,CodeType,FunctionType

LIMIT=1024*1024
def need(ok,code):
    if not ok:raise ValueError(code)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def canonical(row):return json.dumps(row,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
def strict(raw):
    def pairs(items):
        out={}
        for k,v in items:need(k not in out,'HOT_BOOT_DUPLICATE');out[k]=v
        return out
    need(type(raw)is bytes and 0<len(raw)<=LIMIT,'HOT_BOOT_BYTES')
    body=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in()).throw(ValueError()))
    need(type(body)is dict and canonical(body)==raw,'HOT_BOOT_CANONICAL');return body
def identity(info):return (info.st_dev,info.st_ino,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))

def bootstrap_read(record,mode):
    """Minimal fixed loader before the measured runtime module can be compiled."""
    need(type(record)is dict and set(record)=={'path','sha256','ancestors'},'HOT_BOOT_RECORD')
    p=record['path'];need(type(p)is str and Path(p).is_absolute() and str(Path(p))==p and '..'not in Path(p).parts,'HOT_BOOT_PATH')
    names=['/']+[str(Path(*Path(p).parent.parts[:i]))for i in range(2,len(Path(p).parent.parts)+1)]
    rows=record['ancestors'];need(type(rows)is list and len(rows)==len(names),'HOT_BOOT_ROOTS')
    fds=[];fd=None
    try:
        for index,(name,row)in enumerate(rows):
            need(name==names[index]and type(row)is list and len(row)==5 and all(type(x)is int for x in row),'HOT_BOOT_ROOTS')
            opened=os.open('/'if index==0 else Path(name).name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,**({}if index==0 else{'dir_fd':fds[-1]}));fds.append(opened)
            named=os.lstat(name);need(stat.S_ISDIR(named.st_mode)and not stat.S_ISLNK(named.st_mode)and identity(named)==identity(os.fstat(opened))==tuple(row),'HOT_BOOT_ROOT_CHANGED')
        need(rows[-1][1][4]==0o700 and(mode=='FIXTURE'or rows[-1][1][2]==os.geteuid()==0),'HOT_BOOT_ROOT_POLICY')
        fd=os.open(Path(p).name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fds[-1]);before=os.fstat(fd)
        need(stat.S_ISREG(before.st_mode)and before.st_nlink==1 and 0<before.st_size<=LIMIT and not(stat.S_IMODE(before.st_mode)&0o022)and(mode=='FIXTURE'or before.st_uid==0),'HOT_BOOT_FILE_POLICY')
        raw=os.read(fd,LIMIT+1);after=os.fstat(fd);named=os.stat(Path(p).name,dir_fd=fds[-1],follow_symlinks=False)
        stable=lambda x:identity(x)+(x.st_nlink,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
        need(stable(before)==stable(after)==stable(named)and len(raw)==before.st_size and digest(raw)==record['sha256'],'HOT_BOOT_FILE_HASH')
        return raw
    finally:
        if fd is not None:os.close(fd)
        for fd in reversed(fds):os.close(fd)

def verify_running_code(raw):
    """Check the source-pinned stdin entrypoint against every own function code."""
    compiled=compile(raw,main.__code__.co_filename,'exec');codes={c.co_name:c for c in compiled.co_consts if type(c)is CodeType}
    for name,fn in list(globals().items()):
        if type(fn)is FunctionType and fn.__globals__ is globals():
            # Code equality compares recursive constants/bytecode. Marshal's
            # reference interning varies even when two code objects are equal.
            need(name in codes and fn.__code__==codes[name],'HOT_RUNNING_SOURCE_CHANGED')

def run_loaded(loaded):
    """Same child performs warmup, actual T, emission, config and original writer."""
    import hot_runtime as hot
    batch,j=loaded.modules['finite_batch'],loaded.modules['j_slot'];r=loaded.spec;inputs=loaded.inputs
    q=batch.validate_plan(inputs.get('request'));bundle=batch.Bundle(inputs.get('request'),inputs.get('bound'),tuple((n,inputs.get(n))for n in ('owner','authority','runtime')));bundle.validate(q)
    task=next((t for t in q['tasks']if t['operation']=='admission_manifest'),None)
    need(task is not None and q['lane']=='DOWNSTREAM_AFTER_E6' and q['authority_sha256']==r['authority_sha256'],'HOT_PLAN_BINDING')
    need(r['not_before']==task['not_before']and r['not_after']==task['not_after'],'HOT_TASK_WINDOW')
    need(type(r['outer_scope'])is list and all(type(x)is str for x in r['outer_scope'])
         and tuple(r['outer_scope'])==batch.context(q)+('admission_manifest',),'HOT_OUTER_OPERATION_SCOPE')
    ledger_record=r['ledger'];need(type(ledger_record)is dict and set(ledger_record)=={'root','pins'},'HOT_LEDGER_RECORD')
    pins=ledger_record['pins'];need(type(pins)is list and len(pins)==2,'HOT_LEDGER_PINS')
    native_pins=(tuple((row[0],tuple(row[1]))for row in pins[0]),tuple(pins[1]))
    ledger=batch.DurableLedger(ledger_record['root'],native_pins)
    outer=j.OuterReservation(tuple(r['outer_scope']),batch.sha(bundle.request),batch.sha(bundle.bound),batch.sha(batch.canonical(r['outer_scope'])))
    # Exact outer marker/commit exists before any warmup/bridge/factual callback.
    ledger.observe_reservation(outer.scope,outer.request_sha256,outer.bound_sha256,outer.attempt_key)
    if r['mode']=='REAL':observe_outer_dispatch(ledger,outer,batch)
    family=None;session=None;out=None
    try:
        family=j.claim_family(ledger,outer.request_sha256,outer.bound_sha256)
        session=hot.HotSession(loaded,fixture_scope=r['mode']=='FIXTURE')
        runtime=session.warm()
        need(type(runtime.image)is j.ImageBinding and runtime.image.mode==r['mode'],'HOT_IMAGE_BINDING')
        if r['mode']=='REAL':
            # Approved bootstrap must have loaded the exact image package and
            # all context dependencies. This does not call prepare early.
            j.check_image(runtime.image)
            need(getattr(runtime.image.module,'_APP',None)is not None,'HOT_IMAGE_NOT_PREWARMED')
        out=j.run_slot(inputs.get('rule'),rule_sha256=digest(inputs.get('rule')),ledger=ledger,
            authority=runtime.authority,folder_spec_raw=inputs.get('folder_spec'),folder_authority_raw=inputs.get('folder_authority'),
            decision_raw=inputs.get('decision'),owner_raw=inputs.get('folder_owner'),folder_binding=runtime.folder_binding,
            config_base_raw=inputs.get('config_base'),template_raw=inputs.get('template'),veto_base_raw=inputs.get('veto_base'),
            config_authority_raw=inputs.get('config_authority'),act_b_raw=inputs.get('act_b'),machine_order_raw=inputs.get('machine_order'),
            config_verifier=runtime.config_verifier,image=runtime.image,base_settings=runtime.base_settings,
            clock=loaded.modules['veto_emitter'].real_clock,monotonic=__import__('time').monotonic,
            config_loaded=runtime.config_loaded,outer_reservation=outer,hot_session=session,family_reservation=family)
        return {'schema':'R2D2_HOT_IMAGE10_PROCESS_RECEIPT_CANDIDATE_V1','mode':r['mode'],'protocol':r['protocol'],
            'registry_sha256':digest(loaded.raw),'request_sha256':batch.sha(bundle.request),'bound_sha256':batch.sha(bundle.bound),
            'outer_attempt_key':outer.attempt_key,'pid':os.getpid(),'parent_pid':os.getppid(),'process_group':os.getpgrp(),
            'warm_at':hot.iso(session.warm_at),'image_observed_at':hot.iso(session.image_at)if session.image_at is not None else None,
            'image_valid_until':hot.iso(session.image_until)if session.image_until is not None else None,
            'general_observation_base64':base64.b64encode(session.general_raw).decode('ascii')if session.general_raw is not None else None,
            'slot_result':j.private_result(out),'actual_installation_certified':False,'operational_GO':False}
    except batch.ReservationFailure:raise
    except BaseException:
        if family is not None and out is None:
            try:j.finish_family(family,j.SlotResult('REFUSED','HOT_WARMUP_OR_AUTHORITY_REFUSED',family.key,mode=r['mode']))
            except Exception:pass # Missing terminal remains consumed/UNCERTAIN; never retry.
        raise
    finally:
        if session is not None:session.close()
        ledger.close()


def observe_outer_dispatch(ledger,outer,batch):
    """Read the existing native dispatch; never nonce, reservation or permission."""
    with ledger._lock(reason='HOT_OUTER_DISPATCH_LOCK_DEADLINE'):
        claim,reserved_sha=ledger._reservation(outer.scope,outer.request_sha256,outer.bound_sha256,outer.attempt_key)
        dispatch,_=ledger._file('dispatch-'+outer.attempt_key)
        need(set(dispatch)=={'schema','attempt_key','claim_sha256','reserved_sha256','worker_nonce_sha256','worker_pid','at'}
             and dispatch['schema']=='L12_WORKER_DISPATCH_CANDIDATE_V1'and dispatch['attempt_key']==outer.attempt_key
             and dispatch['claim_sha256']==batch.sha(batch.canonical(claim)) and dispatch['reserved_sha256']==reserved_sha
             and batch.pin(dispatch['worker_nonce_sha256'])and dispatch['worker_nonce_sha256']==claim['data'].get('worker_nonce_sha256')
             and dispatch['worker_pid']==os.getpgrp()==os.getsid(0)and os.getpid()!=os.getpgrp(),
             'HOT_OUTER_DISPATCH_NOT_CURRENT')
        need(batch.instant(claim['data']['at'])<=batch.instant(dispatch['at'])<=batch.native_utc_now(),'HOT_OUTER_DISPATCH_TIME')

def main(argv=None):
    args=sys.argv[1:]if argv is None else argv;loaded=None
    try:
        need(type(args)is list and len(args)==4 and args[0]=='--registry-record-base64'and args[2]=='--mode'and args[3]in{'REAL','FIXTURE'},'HOT_FIXED_ARGV')
        record_raw=base64.b64decode(args[1],validate=True);record=strict(record_raw);mode=args[3]
        registry_raw=bootstrap_read(record,mode);registry=strict(registry_raw);need(registry.get('mode')==mode,'HOT_REGISTRY_MODE')
        raw=bootstrap_read(registry['programs']['hot_runtime'],mode);module=ModuleType('hot_runtime');module.__file__=registry['programs']['hot_runtime']['path'];sys.modules['hot_runtime']=module
        exec(compile(raw,module.__file__,'exec'),module.__dict__)
        loaded=module.LoadedSet(registry_raw)
        verify_running_code(loaded.files[('programs','hot_worker')].raw)
        result=run_loaded(loaded);print(canonical(result).decode('ascii'),flush=True)
        return 0 if result['slot_result']['status']=='COMPLETE'else 3
    except BaseException as e:
        code=e.args[0]if len(e.args)==1 and type(e.args[0])is str and e.args[0].isupper()and len(e.args[0])<=96 else'HOT_PROCESS_UNVERIFIED'
        print(canonical({'schema':'R2D2_HOT_IMAGE10_PROCESS_FAILURE_CANDIDATE_V1','status':'HOLD','code':code,
              'automatic_retry':False,'actual_installation_certified':False,'operational_GO':False}).decode('ascii'),flush=True)
        return 3
    finally:
        if loaded is not None:loaded.close()

if __name__=='__main__':raise SystemExit(main())
