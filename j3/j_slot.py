"""Finite image-native admission slot candidate; no CLI, installer or host call.

Runtime uses the exact installed manifest_writer.context/run in one process.
REAL currently refuses until the separate installed process protocol and
documentary authority are reconciled. Explicit fixtures remain DRAFT.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import math
import os
from pathlib import Path
import stat
import time
import sys
import base64
import json
from types import ModuleType
from typing import Callable
import folder_veto as folder
import veto_emitter as v
import config_finalizer as config
import finite_batch as batch

SCHEMA='R2D2_EPOCH04_JSLOT_RULE_V3'
MANIFEST_SHA='aeda5b12d34a406b0d61e1e4696e3c535e89fa3dc680ce0d3b14bb4d60b1d387'
CORE_SHA='879d3abba179b18df6c0d497fc7bce45f4d86e52fa8992c7b9161735969bbb52'
HISTORICAL_PROTOCOL='HISTORICAL_IMAGE10_FIXTURE_ONLY'
PROCESS_PROTOCOL='ISOLATED_MONDAY5_UNSIGNED_CANDIDATE'
PROCESS_PINS={
    'veto_emitter.py':'91b70a91f550f432ffdad173d5bcb3e37e5cd6fde46ae413b20d0c461cbbb795',
    'config_finalizer.py':'b9cc2c86156ee468b7386def5f43387c8a916cc3693b4ccf57fbd4ec2a6ea94a',
    'process_receipt.py':'a044d504c8d25c786c146d7e5ca2f7a0fd3a6a7c9d8c9107f30c99dcc84fdd4a',
    'veto_worker.py':'4d58fb6998443e5000cc8a885df05cedfb2003a85982b63efd02b0777ee09598',
    'consumer_codec.py':'57933d7cf4d79b62ab1c7b291b8c460a743864c78d5ad5a3111c9b2c0b76f2b6',
    'finite_batch.py':'311c2eaa47a223697324f7386b027b2e83c00926c00e7269fd4cfb9fe1c4fa25',
}
_IMAGES={}


class Refused(ValueError):pass
def need(ok,code):
    if not ok:raise Refused(code)


@dataclass(frozen=True)
class SlotAuthority:
    identity:str
    implementation_sha256:str
    mode:str
    verify_current:Callable
    loaded:object=None


@dataclass(frozen=True)
class ImageBinding:
    mode:str
    module:object
    implementation_sha256:str
    path:str|None=None
    ancestors:tuple=()
    file_identity:tuple=()


def load_image(path,*,ancestors,mode):
    """Load exact deployment-writer bytes; packaged app dependencies remain external pins."""
    need(mode in {'REAL','FIXTURE'},'J_IMAGE_MODE')
    raw,info=v._read_program(path,ancestors,mode)
    need(v.digest(raw)==MANIFEST_SHA,'J_IMAGE_SOURCE_PIN')
    name='_pinned_epoch04_manifest_writer_'+v.digest(raw)[:16]
    module=ModuleType(name);module.__file__=path;sys.modules[name]=module
    try:exec(compile(raw,path,'exec'),module.__dict__)
    except Exception:raise Refused('J_IMAGE_LOAD_FAILED')from None
    raw2,info2=v._read_program(path,ancestors,mode)
    need(raw2==raw and info2==info,'J_IMAGE_SOURCE_CHANGED')
    binding=ImageBinding(mode,module,MANIFEST_SHA,path,ancestors,info)
    _IMAGES[id(binding)]=(binding,module.context,module.run,module.execute)
    return binding


def check_image(image):
    if image.mode!='REAL':return
    row=_IMAGES.get(id(image))
    need(row is not None and row[0]is image and row[1]is image.module.context and row[2]is image.module.run
         and row[3]is image.module.execute,
         'J_IMAGE_NOT_LOADED')
    raw,info=v._read_program(image.path,image.ancestors,image.mode)
    need(v.digest(raw)==MANIFEST_SHA and info==image.file_identity,'J_IMAGE_SOURCE_CHANGED')


@dataclass(frozen=True)
class SlotResult:
    status:str
    code:str
    attempt_key:str
    observation_sha256:str|None=None
    veto_sha256:str|None=None
    config_sha256:str|None=None
    manifest_sha256:str|None=None
    operational_GO:bool=False
    writer_receipt_raw:bytes|None=None
    writer_receipt_sha256:str|None=None
    writer_exit_code:int|None=None
    mode:str='UNVERIFIED'


def private_result(result):
    """Original receipt bytes preserved as base64, never a synthesized COMPLETE receipt."""
    need(type(result)is SlotResult,'J_RESULT_TYPE')
    row=dict(result.__dict__);raw=row.pop('writer_receipt_raw')
    row['writer_receipt_base64']=base64.b64encode(raw).decode('ascii')if raw is not None else None
    return row


def writer_bytes(receipt):
    need(type(receipt)is dict,'J_WRITER_RECEIPT_TYPE')
    try:return json.dumps(receipt,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')+b'\n'
    except Exception:raise Refused('J_WRITER_RECEIPT_BYTES')from None


@dataclass(frozen=True)
class OuterReservation:
    scope:tuple
    request_sha256:str
    bound_sha256:str
    attempt_key:str


class Overlay:
    def __init__(self,base,fields):self._base=base;self._fields=dict(fields)
    def __getattr__(self,name):
        if name in self._fields:return self._fields[name]
        return getattr(self._base,name)


def module_pin(name):
    if name=='j_slot':return v.digest(Path(__file__).read_bytes())
    module={'folder_veto':folder,'veto_emitter':v,'config_finalizer':config,'finite_batch':batch}[name]
    return v.digest(Path(module.__file__).read_bytes())


def check_candidate_protocol(pins):
    """Separate namespace: candidate FIXTURE worker never becomes J REAL."""
    need(type(pins)is dict and pins==PROCESS_PINS,'J_PROCESS_CANDIDATE_PINS')
    root=Path(__file__).resolve().parent/'candidate_process'
    for name,pin in PROCESS_PINS.items():
        need(v.digest((root/name).read_bytes())==pin,'J_PROCESS_CANDIDATE_SOURCE_CHANGED')


def runtime_specs(config_base_raw,template_raw,veto_base_raw,source,observation):
    """Approved rule: only actual observation time and actual derived hashes are added."""
    base=config.parse(config_base_raw,'J_CONFIG_BASE');vb=config.parse(veto_base_raw,'J_VETO_BASE')
    need(set(base)=={'schema','mode','template_sha256','emitter_implementation_sha256','authority_sha256','verifier',
        'build_sha','runtime_authority_sha256','settings_file','veto_file','day','required_pins','act_b_order_sha',
        'act_b_original_sha256','machine_order_original_sha256'},'J_CONFIG_BASE_FIELDS')
    need(base['schema']==config.SPEC_SCHEMA and base['mode']==source.spec['mode']
         and base['template_sha256']==v.digest(template_raw),'J_CONFIG_BASE_BINDING')
    need(set(vb)=={'schema','mode','context','source','verifier','authority_sha256','maximum_age_seconds','required_pins',
                  'consumer_config_template_sha256','consumer_document_pins'},'J_VETO_BASE_FIELDS')
    need(vb['context']==source.spec['context']and vb['mode']==source.spec['mode']
         and vb['required_pins']==source.spec['required_pins'],'J_VETO_BASE_BINDING')
    need(observation==source.original,'J_OBSERVATION_ORIGINAL')
    vs=dict(vb,view_opens_at=source.original_body['observed_at'],required_pins=sorted(set(vb['required_pins'])|{source.sha}))
    vr=v.canonical(vs)+b'\n'
    cs=dict(base,veto_spec_sha256=v.digest(vr),required_pins=sorted(set(base['required_pins'])|set(vs['required_pins'])|{v.digest(vr)}))
    cr=v.canonical(cs)+b'\n'
    v.read_spec(vr);config.check_spec(cs,config.parse(template_raw,'J_TEMPLATE'),vs)
    return cr,vr


def stage_file(path,raw,expected_parent,*,owner_uid):
    """Exclusive private file only in a preinstalled/elected root; never overwrite/delete."""
    need(type(path)is str and Path(path).is_absolute()and str(Path(path))==path and '..'not in Path(path).parts,'J_OUTPUT_PATH')
    parent=str(Path(path).parent);need(folder.measure_folder(parent)==expected_parent,'J_OUTPUT_ROOT_CHANGED')
    need(expected_parent[-1][1][2]==owner_uid and expected_parent[-1][1][4]==0o700,'J_OUTPUT_ROOT_POLICY')
    fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    out=None
    try:
        need(folder.directory_identity(os.fstat(fd))==expected_parent[-1][1],'J_OUTPUT_ROOT_CHANGED')
        out=os.open(Path(path).name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
        os.fchmod(out,0o600);written=0
        while written<len(raw):
            n=os.write(out,raw[written:]);need(n>0,'J_OUTPUT_WRITE');written+=n
        os.fsync(out);os.fsync(fd);info=os.fstat(out)
        need(stat.S_ISREG(info.st_mode)and info.st_uid==owner_uid and stat.S_IMODE(info.st_mode)==0o600
             and info.st_nlink==1 and info.st_size==len(raw),'J_OUTPUT_POLICY')
        os.lseek(out,0,os.SEEK_SET);need(os.read(out,len(raw)+1)==raw,'J_OUTPUT_READBACK')
        named=os.stat(Path(path).name,dir_fd=fd,follow_symlinks=False)
        need((named.st_dev,named.st_ino,named.st_uid,named.st_mode,named.st_nlink,named.st_size)==
             (info.st_dev,info.st_ino,info.st_uid,info.st_mode,info.st_nlink,info.st_size),'J_OUTPUT_CHANGED')
        need(folder.measure_folder(parent)==expected_parent,'J_OUTPUT_ROOT_CHANGED')
    finally:
        if out is not None:os.close(out)
        os.close(fd)


def run_slot(rule_raw,*,rule_sha256,ledger,authority,folder_spec_raw,folder_authority_raw,decision_raw,owner_raw,
             folder_binding,config_base_raw,template_raw,veto_base_raw,config_authority_raw,act_b_raw,machine_order_raw,
             config_verifier,image,base_settings,clock,monotonic,config_loaded=None,outer_reservation=None):
    """One shared day claim precedes all current gates/observations and all effects.

    No J2/J3 retry after J1 refusal/uncertainty/COMPLETE. Caller may do a separate
    authorized read of a terminal receipt, never call this method again to repair.
    The parent bounded runner must enforce hard runtime deadlines for ALL code.
    """
    need(type(ledger)is batch.DurableLedger,'J_LEDGER_UNBOUND')
    # Shared claim excludes slot name and request hash: reissuing J2 cannot reset this day.
    # This is an internal family guard under the external L12 invocation claim,
    # deliberately a separate namespace, shared by J1/J2/J3 regardless of slot.
    # Consume known epoch/day/family before parsing or checking the candidate rule.
    # Use the existing real outer reservation pins; fixture-only calls record the
    # hash of actually supplied bytes as diagnostic evidence, not invented authority.
    if type(outer_reservation)is OuterReservation:
        request_pin,bound_pin=outer_reservation.request_sha256,outer_reservation.bound_sha256
    else:
        request_pin=v.digest(rule_raw)if type(rule_raw)is bytes else None;bound_pin=request_pin
    try:key=ledger.claim((config.EPOCH,config.FIRST,'J_ADMISSION_FAMILY_V1'),request_pin,bound_pin,None)
    except batch.ReservationFailure as error:
        return SlotResult('UNCERTAIN'if error.consumed or error.recovery_required else'REFUSED',error.args[0],error.key)
    source=None;may_effect=False;receipt={};out=None;receipt_raw=None;execution_code=None;run_mode='UNVERIFIED'
    try:
        need(type(rule_raw)is bytes and v.digest(rule_raw)==rule_sha256,'J_RULE_HASH')
        rule=config.parse(rule_raw,'J_RULE')
        need(rule.get('schema')==SCHEMA and rule.get('epoch')==config.EPOCH and rule.get('day')==config.FIRST,'J_RULE_CONTEXT')
        run_mode=rule.get('mode')if rule.get('mode')in{'REAL','FIXTURE'}else'UNVERIFIED'
        fields={'schema','mode','epoch','day','folder_spec_sha256','config_base_sha256','template_sha256','veto_base_sha256',
                'manifest_writer_sha256','implementations','authority_verifier','manifest_directory',
                'output_roots','observe_not_before','observe_not_after','process_settings',
                'veto_protocol','process_candidate_pins'}
        need(set(rule)==fields and rule['mode']in{'REAL','FIXTURE'},'J_RULE_FIELDS')
        process=rule['process_settings']
        need(type(process)is dict and set(process)=={'r2d2_v2_shadow_enabled','r2d2_v2_capacity_required'}
             and all(type(value)is bool and value is True for value in process.values()),'J_PROCESS_SETTINGS')
        def observe_outer():
            if rule['mode']!='REAL' and outer_reservation is None:return
            need(type(outer_reservation)is OuterReservation and type(outer_reservation.scope)is tuple
                 and outer_reservation.scope!=(config.EPOCH,config.FIRST,'J_ADMISSION_FAMILY_V1')
                 and all(config.is_sha(x)for x in (outer_reservation.request_sha256,outer_reservation.bound_sha256,outer_reservation.attempt_key)),
                 'J_OUTER_RESERVATION_REQUIRED')
            observed=ledger.observe_reservation(outer_reservation.scope,outer_reservation.request_sha256,
                                               outer_reservation.bound_sha256,outer_reservation.attempt_key)
            need(observed is None,'J_RESERVATION_OBSERVATION_RESULT')
        observe_outer()
        need(module_pin('finite_batch')==CORE_SHA,'J_CORE_SOURCE_PIN')
        need(rule['veto_protocol']in{HISTORICAL_PROTOCOL,PROCESS_PROTOCOL},'J_VETO_PROTOCOL')
        check_candidate_protocol(rule['process_candidate_pins'])
        # No forged object, mutable in-process verifier, fixture subprocess or
        # raw nonce/PID is accepted as installed REAL process provenance.
        need(rule['mode']=='FIXTURE','J_REAL_PROCESS_AUTHORITY_UNAVAILABLE')
        # <=5s is an unsigned new rule; it cannot replace image10 implicitly.
        need(rule['veto_protocol']==HISTORICAL_PROTOCOL,'J_PROCESS_PROTOCOL_NOT_OPERATIONAL')
        for name,raw in [('folder_spec',folder_spec_raw),('config_base',config_base_raw),('template',template_raw),('veto_base',veto_base_raw)]:
            need(type(raw)is bytes and v.digest(raw)==rule[name+'_sha256'],'J_INPUT_PIN')
        impl=rule['implementations'];need(type(impl)is dict and set(impl)=={'folder_veto','veto_emitter','config_finalizer','finite_batch','j_slot'}
             and all(module_pin(name)==pin for name,pin in impl.items()),'J_IMPLEMENTATION_PIN')
        binding=rule['authority_verifier'];need(type(binding)is dict and set(binding)=={'identity','implementation_sha256'}
            and type(authority)is SlotAuthority and authority.mode==rule['mode']
            and authority.identity==binding['identity']and authority.implementation_sha256==binding['implementation_sha256']
            and callable(authority.verify_current),'J_AUTHORITY_UNBOUND')
        def authorize():
            observe_outer()
            if rule['mode']=='REAL':
                v._check_loaded(authority.loaded)
                need(authority.loaded.mode=='REAL' and authority.loaded.identity==authority.identity
                     and authority.loaded.implementation_sha256==authority.implementation_sha256
                     and authority.verify_current is authority.loaded.verify_original,'J_AUTHORITY_NOT_LOADED')
            now=v.now_utc(clock)
            try:accepted=authority.verify_current(rule_raw,folder_spec_raw,config_base_raw,template_raw,veto_base_raw,
                folder_authority_raw,config_authority_raw,act_b_raw,machine_order_raw,decision_raw,owner_raw,now)
            except Exception:raise Refused('J_AUTHORITY_REJECTED')from None
            need(accepted is None,'J_AUTHORITY_BOOLEAN_IS_NOT_ATTESTATION')
            observe_outer()
            if rule['mode']=='REAL':v._check_loaded(authority.loaded)
        authorize()
        need(type(image)is ImageBinding and image.mode==rule['mode']and image.implementation_sha256==MANIFEST_SHA
             and rule['manifest_writer_sha256']==MANIFEST_SHA,'J_IMAGE_BINDING')
        check_image(image)
        need(callable(image.module.context)and callable(image.module.run)and callable(image.module.execute),'J_IMAGE_ABI')
        observe_outer()
        source=folder.FolderSource(folder_spec_raw,folder_authority_raw,decision_raw,owner_raw,
            spec_sha256=rule['folder_spec_sha256'],binding=folder_binding,clock=clock)
        need(source.spec['mode']==rule['mode']and source.spec['observe_not_before']==rule['observe_not_before']
             and source.spec['observe_not_after']==rule['observe_not_after'],'J_OBSERVATION_WINDOW_BINDING')
        now=v.now_utc(clock);need(v.instant(rule['observe_not_before'])<=now<v.instant(rule['observe_not_after']),'J_WINDOW_NOT_OPEN_OR_MISSED')
        observe_outer()
        observed=source.observe();observe_outer()
        observed_at=v.instant(source.original_body['observed_at']);until=v.instant(source.original_body['valid_until'])
        mark=monotonic();need(type(mark)in(int,float)and math.isfinite(mark),'J_MONOTONIC');last=mark
        def budget():
            nonlocal last
            observe_outer()
            now=v.now_utc(clock);tick=monotonic()
            need(type(tick)in(int,float)and math.isfinite(tick)and tick>=last>=mark,'J_MONOTONIC_ROLLBACK')
            last=tick
            need(observed_at<=now<until and tick-mark<(until-observed_at).total_seconds()
                 and abs((now-observed_at).total_seconds()-(tick-mark))<=0.25,'J_VETO_BUDGET_EXHAUSTED')
            return now
        cr,vr=runtime_specs(config_base_raw,template_raw,veto_base_raw,source,observed)
        vb=source.veto_verifier(vr,folder_authority_raw)
        emission=v.emit_view(vr,observed,folder_authority_raw,v.digest(observed),spec_sha256=v.digest(vr),verifier=vb,
                             clock=clock,consumer_template_raw=template_raw)
        def finalize():
            budget();authorize();source.current()
            if rule['mode']=='REAL':
                v._check_loaded(config_loaded)
                need(config_loaded.mode=='REAL' and config_loaded.identity==config_verifier.identity
                     and config_loaded.implementation_sha256==config_verifier.implementation_sha256
                     and config_verifier.verify_current is config_loaded.verify_original,'J_CONFIG_AUTHORITY_NOT_LOADED')
            result=config.finalize_config(cr,template_raw,config_authority_raw,spec_sha256=v.digest(cr),emission=emission,
                veto_spec_raw=vr,veto_authority_raw=folder_authority_raw,observation_raw=observed,
                act_b_raw=act_b_raw,machine_order_raw=machine_order_raw,veto_verifier=vb,config_verifier=config_verifier,clock=clock)
            if rule['mode']=='REAL':v._check_loaded(config_loaded)
            budget();return result
        finalized=finalize();template=config.parse(template_raw,'J_TEMPLATE');roots=rule['output_roots']
        need(type(roots)is dict and set(roots)=={'documents','config_run'},'J_OUTPUT_ROOTS')
        spec=config.parse(cr,'J_CONFIG_SPEC');vp=str(Path(template['roots']['documents']['path'])/finalized.veto_file)
        need(roots['documents']==folder.measure_folder(str(Path(vp).parent))
             and roots['config_run']==folder.measure_folder(str(Path(spec['settings_file']).parent)),'J_OUTPUT_ROOT_PIN')
        owner_uid=source.spec['root']['owner_uid'];budget();source.current();may_effect=True
        observe_outer();stage_file(vp,finalized.veto_raw,roots['documents'],owner_uid=owner_uid)
        budget();source.current();stage_file(spec['settings_file'],finalized.config_raw,roots['config_run'],owner_uid=owner_uid)
        need(finalize()==finalized,'J_FINALIZER_CHANGED');budget()
        # These authorized flags apply only to this new J process's settings object.
        # Neither the base settings nor the active worker environment is mutated.
        settings=Overlay(base_settings,dict(finalized.settings,**process))
        ctx=image.module.context(settings,now=budget(),prepare_first=True,clock=clock)
        budget();need(getattr(ctx,'prepare',None)is not None,'J_CONTEXT_PREPARE_MISSING')
        prepare,verify_go=ctx.prepare,ctx.verify_go
        def current_gate():
            observe_outer()
            check_image(image);need(finalize()==finalized,'J_FINALIZER_CHANGED');source.current();budget()
        def checked_prepare(day):
            need(day==config.FIRST,'J_PREPARE_DAY');current_gate()
            value=prepare(day);budget();source.current();return value
        def checked_go(go,plan):
            current_gate();value=verify_go(go,plan);budget();source.current();return value
        ctx.prepare=checked_prepare;ctx.verify_go=checked_go
        observe_outer()
        receipt,execution_code=image.module.execute(lambda:ctx,day=config.FIRST,directory=Path(rule['manifest_directory']),
            prepare_first=True,verify_only=False,preflight=False,view_opens_at=observed_at,max_wait=0,
            require_go_mode='INDIVIDUAL',clock=clock,monotonic=monotonic)
        receipt_raw=writer_bytes(receipt)
        budget();source.current();authorize();budget()
        need(type(execution_code)is int and execution_code==0 and receipt.get('schema')=='R2D2_V2_BAR_MANIFEST_WRITER_RECEIPT_V1'
             and receipt.get('status')=='PUBLISHED_VERIFIED' and receipt.get('mode')=='PUBLISH'and receipt.get('code')is None
             and receipt.get('epoch')==config.EPOCH and receipt.get('session')==config.FIRST
             and receipt.get('capacity_config_sha256')==finalized.config_sha256
             and config.is_sha(receipt.get('binding_sha256'))and config.is_sha(receipt.get('manifest_sha256')),'J_MANIFEST_UNVERIFIED')
        need(receipt.get('go_mode')=='INDIVIDUAL'and config.is_sha(receipt.get('go_sha256'))
             and config.is_sha(receipt.get('template_sha256')),'J_WRITER_GO_UNVERIFIED')
        view=receipt.get('view');window=receipt.get('window')
        need(type(view)is dict and set(view)=={'observed_at','valid_until'}
             and v.instant(view['observed_at'])==observed_at and v.instant(view['valid_until'])==until,
             'J_WRITER_VIEW_UNVERIFIED')
        need(type(window)is dict and set(window)=={'not_before','not_after'}
             and v.instant(window['not_before'])<=observed_at<until<=v.instant(window['not_after'])
             and observed_at<=v.instant(receipt.get('published_at'))<until,'J_WRITER_WINDOW_UNVERIFIED')
        need(writer_bytes(receipt)==receipt_raw,'J_WRITER_RECEIPT_CHANGED')
        out=SlotResult('COMPLETE','J_IMAGE_MANIFEST_COMPLETE',key,v.digest(observed),finalized.veto_sha256,
                       finalized.config_sha256,receipt['manifest_sha256'],False,receipt_raw,v.digest(receipt_raw),execution_code,run_mode)
    except Exception as e:
        code=e.args[0]if isinstance(e,(Refused,folder.Refused,v.Refused,config.Refused,batch.Hold))and len(e.args)==1 and type(e.args[0])is str else'J_UNVERIFIED'
        out=SlotResult('UNCERTAIN'if may_effect else'REFUSED',code,key,writer_receipt_raw=receipt_raw,
                       writer_receipt_sha256=v.digest(receipt_raw)if receipt_raw is not None else None,
                       writer_exit_code=execution_code,mode=run_mode)
    finally:
        if source is not None:source.close()
    try:ledger.finish(key,private_result(out))
    except Exception:return SlotResult('UNCERTAIN','J_TERMINAL_LEDGER_UNVERIFIED',key,out.observation_sha256,
        out.veto_sha256,out.config_sha256,out.manifest_sha256,False,out.writer_receipt_raw,out.writer_receipt_sha256,out.writer_exit_code,out.mode)
    return out
