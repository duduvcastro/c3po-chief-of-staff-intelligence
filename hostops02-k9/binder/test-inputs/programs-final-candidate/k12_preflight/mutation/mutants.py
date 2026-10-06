"""The mutants of K12p's own part. Each row: (name, target, exact anchor, replacement); target 'op' is the built source
build/k12_preflight.py, in which the anchor must occur exactly once (mutate.py check).

Two kinds of rows:
  generated  one per check of the operation part, read from op.py's syntax tree: every need(<condition>,'<CODE>') is
             replaced by need(True,'<CODE>') (the check removed), every raise of Refused('<CODE>') and every constant
             fallback of code_of() gets another code. The functions of the K12 common block are generated in the family
             that is their home (HOME below; the block is the same bytes in the three families and common_block.py
             check pins it): none here; this list is K12p's own part.
  written    the constants, the fixed words, every member of effects_of() (EFFECTS names the mutant of each), the
             settlement of every effect, the order of the checks and the outcome of each mode.
coverage() compares both with the source itself: a check, a code or an effects member without a mutant is an error of
`mutate.py check`."""
import ast
import hashlib
from pathlib import Path
import re
import sys

FAMILY='k12_preflight'
HOME=()
COMMON=('k12_compact','k12_container_name','k12_preflight_name','k12_persisted_name','k12_writer_name','k12_at','k12_instant','k12_journal',
        'k12_capacity_request','k12_mount_word','k12_container_words','k12_expected_mounts','k12_inspect','k12_ours','k12_writer_line',
        'k12_line_public','k12_persisted','k12_entry','k12_file','k12_private','k12_line_of','k12_ended','k12_terminal',
        'k12_data','k12_root_chain','k12_stopped','k12_receipt_line','k12_data_chain','k12_release')
FALLBACKS_NOT_ASSERTED=()

M=[]
EFFECTS={}
def add(name,old,new,effect=None):
    M.append((name,'op',old,new))
    for key in ([effect] if type(effect) is str else effect or []):EFFECTS.setdefault(key,name)

# ---------------------------------------------------------------- generated from the syntax tree
def checks(text,lines=False):
    """[(function, kind, code, segment)] for every need(), Refused() and code_of() with a constant code in op.py
    (with lines=True also the first and last line of the call)."""
    tree=ast.parse(text);out=[]
    def visit(node,function):
        for child in ast.iter_child_nodes(node):
            name=child.name if isinstance(child,ast.FunctionDef) else function
            if isinstance(child,ast.Call) and isinstance(child.func,ast.Name) and child.func.id in ('need','Refused','code_of'):
                arguments=child.args;code=arguments[-1] if arguments else None
                if isinstance(code,ast.Constant) and type(code.value) is str and re.fullmatch('[A-Z][A-Z0-9_]{2,79}',code.value):
                    out.append((function,child.func.id,code.value,ast.get_source_segment(text,child))+((child.lineno,child.end_lineno) if lines else ()))
            visit(child,name)
    visit(tree,None);return out

def anchored(text,built,segment,line,end):
    """The segment when it is unique in op.py and in the built source; otherwise its whole lines, widened upwards
    until they are."""
    if text.count(segment)==1 and built.count(segment)==1:return segment
    lines=text.split('\n');first=line-1
    while first>=0:
        block='\n'.join(lines[first:end])
        if text.count(block)==1 and built.count(block)==1:return block
        first-=1
    return segment

def generated(text,built):
    rows=[];seen={}
    for function,kind,code,segment,line,end in checks(text,True):
        if function in COMMON and function not in HOME:continue
        key='%s_%s_%s'%(function,kind,code);seen[key]=seen.get(key,0)+1;name='G_%s_%d'%(key,seen[key])
        anchor=anchored(text,built,segment,line,end)
        if kind=='need':
            condition=segment[len('need('):segment.rindex(',')]
            replaced=anchor.replace(segment,'need(True,%r)'%code if condition.strip()!='True' else segment)
        else:replaced=anchor.replace(segment,segment.replace("'%s'"%code,"'%s_MUTANT'"%code))
        rows.append((name,'op',anchor,replaced))
    return rows

def _op_text():return (Path(__file__).resolve().parent.parent/'op.py').read_text()
def _built_text():return (Path(__file__).resolve().parent.parent/'build'/(FAMILY+'.py')).read_text()
GENERATED=generated(_op_text(),_built_text())

# ---------------------------------------------------------------- constants and fixed words
add('C01_chains_without_the_journal',"P_CHAINS=('config','manifests','reader_config','docker_cli','journal','data','receipts')","P_CHAINS=('config','manifests','reader_config','docker_cli','data','receipts')",['chains'])
add('C01b_chains_without_the_data',"P_CHAINS=('config','manifests','reader_config','docker_cli','journal','data','receipts')","P_CHAINS=('config','manifests','reader_config','docker_cli','journal','receipts')")
add('C01c_chains_without_the_receipts',"P_CHAINS=('config','manifests','reader_config','docker_cli','journal','data','receipts')","P_CHAINS=('config','manifests','reader_config','docker_cli','journal','data')")
add('C02_allowance',"P_ALLOWANCE_SECONDS=8 ","P_ALLOWANCE_SECONDS=7 ")
add('C13_claim_name',"def p_claim_name(day):return 'k12-%s-preflight.claim.json'%day","def p_claim_name(day):return 'k12-%s-preflight.json'%day",['creates'])
add('C14_claim_schema',"P_CLAIM_SCHEMA='K12_PREFLIGHT_CLAIM_V1'","P_CLAIM_SCHEMA='K12_PREFLIGHT_CLAIM_V0'")
add('C15_data_chain_as_root_chain',"        if name=='data':k12_data_chain(rows[name]);continue","        if False:k12_data_chain(rows[name]);continue")
add('C16_chains_not_root_controlled',"        k12_root_chain(rows[name],p_path(name,derived))","        validate_chain(rows[name],p_path(name,derived))")
add('C03_run_may_pull',"P_RUN_PREFIX=['run','--rm','--pull','never',","P_RUN_PREFIX=['run','--rm','--pull','missing',",['run'])
add('C04_run_without_init',"'--pull','never','--init','--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges']\nBINARIES",
    "'--pull','never','--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges']\nBINARIES")
add('C05_run_writable_root',"'--init','--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges']\nBINARIES",
    "'--init','--user','0:0','--cap-drop','ALL','--security-opt','no-new-privileges']\nBINARIES")
add('C06_run_class',"'writer argv and --preflight','RUN','EFFECT')}","'writer argv and --preflight','RUN_SHORT','EFFECT')}")
add('C07_date_class',"DATE_CLASS='WRITE_SESSIONS'","DATE_CLASS='WRITE_EPOCH'")
add('C08_evidence_operation',"EVIDENCE_OPERATIONS=('GO_READONLY_HOSTOPS02_K12_COLLECT_01',)","EVIDENCE_OPERATIONS=()")
add('C09_preflight_name',"def k12_preflight_name(day):return 'c3po-k12-%s-preflight'%k12_compact(day)","def k12_preflight_name(day):return 'c3po-k12-%s-w0'%k12_compact(day)",['container_name'])
add('C10_without_the_preflight_argument',"labels)+['--preflight']","labels)")
add('C11_labels_swapped',"    labels=[(K12_LABEL_REQUEST,request_sha256),(K12_LABEL_CAPACITY,derived['sha256'])]","    labels=[(K12_LABEL_REQUEST,derived['sha256']),(K12_LABEL_CAPACITY,request_sha256)]")
add('C12_primary_only',"    need(derived['index']==1,'NOT_THE_PRIMARY_WINDOW')","    need(derived['index']<=2,'NOT_THE_PRIMARY_WINDOW')")

# ---------------------------------------------------------------- effects_of(): one mutant per member
add('E01_operation',"    return {'operation':OPERATION,'epoch':K12_EPOCH,","    return {'operation':PHASE,'epoch':K12_EPOCH,",['operation'])
add('E02_epoch',"'epoch':K12_EPOCH,'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],","'epoch':None,'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],",['epoch'])
add('E03_boot',"'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],\n            'capacity_request_sha256'","'evidence_boot_id_sha256':None,\n            'capacity_request_sha256'",['evidence_boot_id_sha256'])
add('E04_capacity_sha',"            'capacity_request_sha256':derived['sha256'],'day':derived['day'],","            'capacity_request_sha256':None,'day':derived['day'],",['capacity_request_sha256'])
add('E05_day',"'capacity_request_sha256':derived['sha256'],'day':derived['day'],'window':derived['window'],","'capacity_request_sha256':derived['sha256'],'day':None,'window':derived['window'],",['day'])
add('E06_window',"'day':derived['day'],'window':derived['window'],'window_slot':1,","'day':derived['day'],'window':None,'window_slot':1,",['window'])
add('E07_window_slot',"'window':derived['window'],'window_slot':1,","'window':derived['window'],'window_slot':2,",['window_slot'])
add('E08_docker_config',"'docker_config':K12_DOCKER_CLI,\n            'container_name'","'docker_config':None,\n            'container_name'",['docker_config'])
add('E09_before',"'before':derived['not_before'],","'before':derived['view_opens_at'],",['before'])
add('E10_writer',"'writer':{'path':K12_CONFIG_ROOT+'/'+k12_writer_name(derived['writer_sha256']),","'writer':{'path':K12_CONFIG_TARGET+'/'+k12_writer_name(derived['writer_sha256']),",['writer'])
add('E11_capacity_config',"'capacity_config':{'path':K12_CONFIG_ROOT+'/'+derived['config_name'],'sha256':derived['config_sha256'],","'capacity_config':{'path':K12_CONFIG_ROOT+'/'+derived['config_name'],'sha256':None,",['capacity_config'])
add('E12_pins_env',"'pins_env':{'path':K12_PINS_ENV,'sha256':derived['pins_sha256'],","'pins_env':{'path':K12_PINS_ENV,'sha256':None,",['pins_env'])
add('E13_secret_env',"'secret_env':{'path':K12_SECRET_ENV,'require':'ROOT_0600_ONE_LINK','read':'METADATA_ONLY'},","'secret_env':{'path':K12_SECRET_ENV,'require':'ROOT_0600_ONE_LINK','read':'BYTES'},",['secret_env'])
add('E14_after',"'after':{'container':'ABSENT','manifests_directory':'UNCHANGED'},","'after':{'container':'ABSENT'},",['after'])
add('E15_files_created',"'files_created_by_this_process':1,'activation':False}","'files_created_by_this_process':0,'activation':False}",['files_created_by_this_process'])
add('E16_activation',"'files_created_by_this_process':1,'activation':False}","'files_created_by_this_process':1,'activation':None}",['activation'])
add('E18_journal',"'target':derived['journal']['target'],'require':'ROOT_0700_CATALOG_ROOT_0600'},","'target':derived['journal']['target'],'require':None},",['journal'])
add('E19_data',"            'data':{'path':K12_DATA_VOLUME,'target':K12_DATA_TARGET,'read_only':True,","            'data':{'path':K12_DATA_VOLUME,'target':K12_DATA_TARGET,'read_only':False,",['data'])
add('P_r1_release_not_checked_before',"            k12_release(host,handles['data'],gate,derived)\n","")
add('P_r2_release_not_checked_after',"        try:k12_release(host,handles['data'],gate,derived)        # the bytes","        try:pass        # the bytes")
add('E20_chain_rule',"            'chain_rule':'ROOT_CONTROLLED_UID0_GID0_NO_GROUP_OR_OTHER_WRITE_NO_SETGID_NO_LINK',\n            'creates'","            'chain_rule':'ROOT',\n            'creates'",['chain_rule'])
add('E21_creates',"'expect':'ABSENT','before':'THE_RUN'},","'expect':'ABSENT','before':'AFTER'},")
add('E22_manifests',"'bound':'READ_WRITE_AS_IN_THE_DISPATCH','effects':'CLOSED',","'bound':'READ_WRITE_AS_IN_THE_DISPATCH','effects':'OPEN',",['manifests'])
add('E17_label_placeholder',"'run':P_RUN_PREFIX+p_words(derived,'<this request\\'s sha256>'),","'run':P_RUN_PREFIX+p_words(derived,'<request>'),")

# ---------------------------------------------------------------- the run
# (Not a mutant: removing `if result['returned']:state.unknown()` before the readback's refusal. A returned effect that
# is never settled counts as uncertain by itself (Effects.uncertain = issued - succeeded - failed): the line states the
# settlement, the count is the same. Run on 2026-10-04 as S03 and recorded here as equivalent.)
add('S01_clean_ignores_a_container_left',"            clean=not left and after==kept['before']","            clean=after==kept['before']")
add('S02_clean_ignores_the_manifests',"            clean=not left and after==kept['before']","            clean=not left")
add('S04_left_something_settled_as_nothing',"            state.unknown();return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,'PREFLIGHT_LEFT_SOMETHING',extra)",
    "            state.fail();return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,'PREFLIGHT_LEFT_SOMETHING',extra)")
add('S05_ran_settled_as_done',"        state.fail()          # the container ran and is gone","        state.done()          # the container ran and is gone")
add('S06_engine_failure_parsed',"        if result['returncode'] in RUN_ENGINE_STATUSES:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,'PREFLIGHT_ENGINE_FAILURE',extra)\n","")
add('S07_not_ok_complete',"        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,'PREFLIGHT_NOT_OK',extra)","        return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,'PREFLIGHT_NOT_OK',extra)")
add('S08_ok_any_exit',"    return (returncode==0 and line['status']=='PREFLIGHT_OK'","    return (line['status']=='PREFLIGHT_OK'")
add('S09_ok_any_status',"line['status']=='PREFLIGHT_OK' and line['mode']=='PREFLIGHT'","line['mode']=='PREFLIGHT'")
add('S10_ok_any_mode',"and line['mode']=='PREFLIGHT' and line['session']==derived['day']","and line['session']==derived['day']")
add('S11_ok_any_session',"and line['session']==derived['day']\n","\n")
add('S12_ok_any_owner',"            and line.get('owner_uid')==0 and line.get('capacity_config_sha256')","            and line.get('capacity_config_sha256')")
add('S13_ok_any_config',"and line.get('capacity_config_sha256')==derived['config_sha256']\n","\n")
add('S14_ok_any_release',"            and line.get('release_sha256')==derived['release_sha256'] and line.get('package_sha256')","            and line.get('package_sha256')")
add('S15_ok_any_package',"and line.get('package_sha256')==derived['package_sha256']\n","\n")
add('S16_ok_any_build',"            and line.get('build_sha')==derived['build_sha'] and line.get('massive_bars_enabled')","            and line.get('massive_bars_enabled')")
add('S17_ok_bars_off',"and line.get('massive_bars_enabled') is True and checks.get('directory_checked')","and checks.get('directory_checked')")
add('S18_ok_without_the_directory',"and checks.get('directory_checked') is True)","and True)")
add('S19_checks_copy_everything',"if text(key,'[a-z][a-z0-9_]{0,63}') and (type(value) is bool or integer(value,0,1000000))}","}")
add('S21_manifest_state_without_entry_signatures',"        gate();rows.append([name,list(stat_signature(host.lstat(name,held.fd)))])","        gate();rows.append([name,[]])")
add('S21b_manifest_state_without_the_directory',"    rows.append(['.',list(stat_signature(host.fstat(held.fd)))])\n","")
add('S21c_manifest_entries_count_the_directory',"    return {'entries':len(rows)-1,","    return {'entries':len(rows),")
add('S21d_manifest_present_any_name',"        if name==day+'.json':present+=1\n    rows.append","        if name.endswith('.json'):present+=1\n    rows.append")
add('S27_unchanged_flag_constant',"manifests_unchanged=after==kept['before'])","manifests_unchanged=True)")
add('S28_signature_leaks',"def p_public(state):return {key:value for key,value in state.items() if not key.startswith('_')}","def p_public(state):return dict(state)")
add('S31_claim_failure_ignored',"        if entry['state']!='INSTALLED_DURABLE':\n            stop=entry['code'] or 'CLAIM_FAILED'","        if False:\n            stop=entry['code'] or 'CLAIM_FAILED'")
add('S32_claim_not_read_back',"        stop=readback_file(entry,claim,PRIVATE_FILE_MODE,handles['receipts'],host,gate)\n","        stop=None\n")
add('S33_claim_failure_always_refused',"            return finish(REFUSED_STATUS if state.clean() else PARTIAL_STATUS,","            return finish(REFUSED_STATUS,")
add('S34_claim_without_the_request',"'preflight_request_sha256':bound['request_sha256'],'container_name':name})","'container_name':name})")
add('S35_umask_not_set',"            host.umask(0o077)\n","")
add('S36_not_started_after_the_claim_refused',"        if not result['started']:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,result['code'] or 'PREFLIGHT_NOT_STARTED',extra)",
    "        if not result['started']:return finish(REFUSED_STATUS,REFUSED_OUTCOME,result['code'] or 'PREFLIGHT_NOT_STARTED',extra)")
add('S22_line_public_lost',"        extra['preflight']=dict(k12_line_public(line),checks=p_checks(line),returncode=result['returncode'],ok=ok)","        extra['preflight']=dict(checks=p_checks(line),returncode=result['returncode'],ok=ok)")
add('S23_day_containers_ignored',"            need(not listed,'CAPACITY_CONTAINER_OF_THE_DAY_PRESENT')\n","")
add('S24_listing_of_every_day',"            prefix='c3po-k12-%s-'%k12_compact(derived['day'])","            prefix='c3po-k12-'")
add('S25_boot_after_the_walks',"            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')\n            for key in P_CHAINS:",
    "            for key in P_CHAINS:")
add('S26_after_left_lost',"            detail.update(container_left=bool(left),manifests_after=p_public(after),","            detail.update(manifests_after=p_public(after),")

# ---------------------------------------------------------------- the dispatcher generated for this operation (WRITE_SESSIONS)
LITERAL="('2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09','2026-10-10')"
DISPATCHER=[
    ('D71k_dispatcher_date_set_dropped','dispatcher',"need(start.date().isoformat() in "+LITERAL+" and end.date()==start.date(),'DISPATCH_DATE')","need(end.date()==start.date(),'DISPATCH_DATE')"),
    ('D72k_dispatcher_accepts_the_sunday_before','dispatcher',"start.date().isoformat() in ('2026-10-05',","start.date().isoformat() in ('2026-10-04','2026-10-05',"),
    ('D73k_dispatcher_accepts_the_day_after_the_epoch','dispatcher',"'2026-10-09','2026-10-10') and end.date()==start.date()","'2026-10-09','2026-10-10','2026-10-11') and end.date()==start.date()"),
]
CORE_ROWS_REPLACED=('D71_write_dispatcher_date_set_dropped','D72_write_dispatcher_accepts_friday_the_second')

MUTANTS=GENERATED+M+DISPATCHER
COMBOS={}
REDUNDANT={}


# ---------------------------------------------------------------- the tables against the source itself
def _load(path):
    raw=Path(path).read_bytes();name='_hostops02_%s_mutation_%s'%(FAMILY,hashlib.sha256(raw).hexdigest()[:12])
    module=type(sys)(name);module.__dict__['__file__']='<assembled %s.py>'%FAMILY;sys.modules[name]=module
    exec(compile(raw,module.__dict__['__file__'],'exec'),module.__dict__);return module

def _members(value,prefix=''):
    out=[]
    for key in sorted(value):out.append(prefix+key)
    return out

def plans(module):
    """One plan per mode, from the fixtures' own builder (tests/k12p.py), so that every member of every mode is named."""
    here=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(here/'tests'));sys.path.insert(0,str(here.parent/'core'/'tests'))
    try:
        import k12p
        docs,_=k12p.case();return [docs.plan]
    finally:
        sys.path.remove(str(here/'tests'));sys.path.remove(str(here.parent/'core'/'tests'))

def coverage(here):
    here=Path(here);errors=[];names={row[0] for row in M}|{row[0] for row in GENERATED};module=_load(here/'build'/(FAMILY+'.py'))
    wanted=set()
    for plan in plans(module):wanted|=set(_members(module.effects_of(plan)))
    for member in sorted(wanted):
        if EFFECTS.get(member) not in names:errors.append('effects member without a mutant: '+member)
    for member in EFFECTS:
        if member not in wanted:errors.append('mutant table names an effects member that does not exist: '+member)
    built=(here/'build'/(FAMILY+'.py')).read_text()
    for name,_,anchor,new in GENERATED:
        if built.count(anchor)!=1:errors.append('generated anchor not unique in the source: '+name)
        if anchor==new:errors.append('generated mutant changes nothing: '+name)
    eligible=[row for row in checks((here/'op.py').read_text()) if row[0] not in COMMON or row[0] in HOME]
    if len(GENERATED)!=len(eligible):errors.append('generated rows do not match the checks of the source')
    return errors
