"""The mutants of K12r's own part. Each row: (name, target, exact anchor, replacement); target 'op' is the built source
build/k12_collect.py, in which the anchor must occur exactly once (mutate.py check).

Two kinds of rows:
  generated  one per check of the operation part, read from op.py's syntax tree: every need(<condition>,'<CODE>') is
             replaced by need(True,'<CODE>') (the check removed), every raise of Refused('<CODE>') and every constant
             fallback of code_of() gets another code. The functions of the K12 common block are generated in the family
             that is their home (HOME below; the block is the same bytes in the three families and common_block.py
             check pins it): here the inspect line, the writer's line, the persisted receipt and the file reads.
  written    the constants, the fixed words, every member of effects_of() (EFFECTS names the mutant of each), the
             settlement of every effect, the order of the checks and the outcome of each mode.
coverage() compares both with the source itself: a check, a code or an effects member without a mutant is an error of
`mutate.py check`."""
import ast
import hashlib
from pathlib import Path
import re
import sys

FAMILY='k12_collect'
HOME=('k12_inspect','k12_writer_line','k12_line_public','k12_persisted','k12_entry','k12_file','k12_private','k12_line_of','k12_terminal')
COMMON=('k12_compact','k12_container_name','k12_preflight_name','k12_persisted_name','k12_writer_name','k12_at','k12_instant','k12_journal',
        'k12_capacity_request','k12_mount_word','k12_container_words','k12_expected_mounts','k12_inspect','k12_ours','k12_writer_line',
        'k12_line_public','k12_persisted','k12_entry','k12_file','k12_private','k12_line_of','k12_ended','k12_terminal',
        'k12_data','k12_root_chain','k12_stopped','k12_receipt_line','k12_data_chain','k12_release')
# Constant fallbacks of code_of() that no input can reach: the call is in an `except Refused` whose every Refused carries
# a constant code (code_of returns it), so the fallback is never printed. Recorded, not generated.
FALLBACKS_NOT_ASSERTED=(('c_tree','CHAIN_ROW_UNSAFE'),('c_persisted','PERSISTED_RECEIPT_INVALID'),('k12_line_of','WRITER_LINE_INVALID'),('perform','RUN_STOPPED'))

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
        if kind=='code_of' and (function,code) in FALLBACKS_NOT_ASSERTED:continue
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

# ---------------------------------------------------------------- constants of the common block read here
add('C01_writer_schema',"K12_WRITER_SCHEMA='R2D2_V2_BAR_MANIFEST_WRITER_RECEIPT_V1'","K12_WRITER_SCHEMA='R2D2_V2_BAR_MANIFEST_WRITER_RECEIPT_V2'")
add('C02_published_exit_three',"K12_WRITER_STATUSES={'PUBLISHED_VERIFIED':(0,),","K12_WRITER_STATUSES={'PUBLISHED_VERIFIED':(0,3),")
add('C03_refused_exit_zero',"'ABSENT':(3,),'REFUSED':(3,),","'ABSENT':(3,),'REFUSED':(0,3),")
add('C04_unverified_exit_three',"'UNVERIFIED':(1,),'PUBLISHED_UNVERIFIED':(1,3)}","'UNVERIFIED':(1,3),'PUBLISHED_UNVERIFIED':(1,3)}")
add('C06_published_set_without_already',"K12_WRITER_PUBLISHED=('PUBLISHED_VERIFIED','ALREADY_PUBLISHED_VERIFIED')","K12_WRITER_PUBLISHED=('PUBLISHED_VERIFIED',)")
add('C07_committed_with_attempted',"K12_COMMITTED=('COMMITTED','ALREADY_COMMITTED','PRECOMMITTED')","K12_COMMITTED=('ATTEMPTED','COMMITTED','ALREADY_COMMITTED','PRECOMMITTED')")
add('C08_committed_without_precommitted',"K12_COMMITTED=('COMMITTED','ALREADY_COMMITTED','PRECOMMITTED')","K12_COMMITTED=('COMMITTED','ALREADY_COMMITTED')")
add('C09_writer_code_without_underscore',"K12_WRITER_CODE='[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+'","K12_WRITER_CODE='[A-Z][A-Z0-9_]*'")
add('C10_collect_after_view',"C_COLLECT_AFTER_VIEW_SECONDS=60 ","C_COLLECT_AFTER_VIEW_SECONDS=59 ")
add('C11_tree_without_the_capacity_root',"C_TREE=('capacity_root','config',","C_TREE=('config',")
add('C12_collect_chains',"C_COLLECT_CHAINS=('manifests','receipts','data')","C_COLLECT_CHAINS=('manifests','receipts')")
add('C13_manifest_limit',"K12_MANIFEST_MAX_BYTES=65536","K12_MANIFEST_MAX_BYTES=65537")
add('C14_persisted_limit',"K12_PERSISTED_MAX_BYTES=32768","K12_PERSISTED_MAX_BYTES=64")
add('C15_inspect_reads_another_exit',"'\"running\":{{json .State.Running}},\"exit_code\":{{json .State.ExitCode}},\"oom_killed\":{{json .State.OOMKilled}},'",
    "'\"running\":{{json .State.Running}},\"exit_code\":{{json .State.Pid}},\"oom_killed\":{{json .State.OOMKilled}},'")
add('C16_inspect_format_finished',"'\"started_at\":{{json .State.StartedAt}},\"finished_at\":{{json .State.FinishedAt}},'","'\"started_at\":{{json .State.StartedAt}},\"finished_at\":{{json .State.StartedAt}},'")
add('C17_mount_keys_without_mode',"K12_MOUNT_KEYS=frozenset(('Type','Name','Source','Destination','Driver','Mode','RW','Propagation'))","K12_MOUNT_KEYS=frozenset(('Type','Name','Source','Destination','Driver','RW','Propagation'))")
add('C18_persisted_keys_lose_one',"'finished_at','stdout_b64','stdout_sha256','stdout_bytes'))\nK12_FORMAT","'finished_at','stdout_b64','stdout_sha256'))\nK12_FORMAT")
add('C19_never_started',"K12_NEVER_STARTED='0001-01-01T00:00:00Z'","K12_NEVER_STARTED='0001-01-01T00:00:00.000Z'")

# ---------------------------------------------------------------- the line, the persisted receipt, the inspect (home here)
add('L01_line_two_lines',"raw.endswith(b'\\n') and raw.count(b'\\n')==1,'WRITER_LINE_NOT_ONE_LINE')","raw.endswith(b'\\n'),'WRITER_LINE_NOT_ONE_LINE')")
add('L02_line_without_newline',"0<len(raw)<=K12_STDOUT_MAX_BYTES and raw.endswith(b'\\n') and raw.count","0<len(raw)<=K12_STDOUT_MAX_BYTES and raw.count")
add('L03_line_unknown_keys',"need(type(line) is dict and set(line)<=K12_WRITER_KEYS and","need(type(line) is dict and")
add('L04_line_code_on_success',"    need((line['code'] is None)==(line['status'] in ('PUBLISHED_VERIFIED','ALREADY_PUBLISHED_VERIFIED','MATCH_VERIFIED','PREFLIGHT_OK'))\n         and (line['code'] is None or text(line['code'],K12_WRITER_CODE)),'WRITER_LINE_INVALID')",
    "    need((line['code'] is None or text(line['code'],K12_WRITER_CODE)),'WRITER_LINE_INVALID')")
add('L05_line_session_any',"    need(line['session'] in (day,None) and line['mode'] in","    need(line['mode'] in")
add('L06_line_hash_member_unchecked',"for key in ('release_sha256','capacity_config_sha256','package_sha256','go_sha256','template_sha256','binding_sha256','manifest_sha256'):",
    "for key in ('release_sha256',):")
add('L07_line_symbol_count_unbounded',"('symbol_count' not in line or integer(line['symbol_count'],0,550))","('symbol_count' not in line or integer(line['symbol_count']))")
add('L08_public_keeps_the_manifest_hash',"'stale_temporaries','repaired_temporaries','waited_seconds','published_at','cutoff_at')\n    public=",
    "'stale_temporaries','repaired_temporaries','waited_seconds','published_at','cutoff_at','manifest_sha256')\n    public=")
add('L09_public_keeps_the_count',"'stale_temporaries','repaired_temporaries','waited_seconds','published_at','cutoff_at')\n    public=",
    "'stale_temporaries','repaired_temporaries','waited_seconds','published_at','cutoff_at','symbol_count')\n    public=")
add('L10_public_presence_flags',"    public.update(manifest_sha256_present='manifest_sha256' in line,symbol_count_present='symbol_count' in line)","    public.update(manifest_sha256_present=True,symbol_count_present=True)")
add('L11_public_drops_the_binding',"    keep=('status','code','session','mode','owner_uid','prepare_status','binding_sha256',","    keep=('status','code','session','mode','owner_uid','prepare_status',")
add('L13_terminal_empty_without_commit',"    if line['code']=='MANIFEST_SYMBOLS_EMPTY' and line.get('prepare_status') in K12_COMMITTED:return 'EMPTY_LIST'",
    "    if line['code']=='MANIFEST_SYMBOLS_EMPTY':return 'EMPTY_LIST'")
add('L15_persisted_ignores_expected',"         and all(value[key]==expected[key] for key in expected),'PERSISTED_RECEIPT_INVALID')","         ,'PERSISTED_RECEIPT_INVALID')")
add('L16_persisted_stdout_size',"    need(len(stdout)==value['stdout_bytes'] and sha(stdout)==value['stdout_sha256'],'PERSISTED_RECEIPT_INVALID')","    need(sha(stdout)==value['stdout_sha256'],'PERSISTED_RECEIPT_INVALID')")
add('L17_persisted_stdout_hash',"    need(len(stdout)==value['stdout_bytes'] and sha(stdout)==value['stdout_sha256'],'PERSISTED_RECEIPT_INVALID')","    need(len(stdout)==value['stdout_bytes'],'PERSISTED_RECEIPT_INVALID')")
add('L18_private_any_mode',"(facts['uid'],facts['gid'],facts['mode_octal'],facts['links'])==(0,0,'0600',1)","(facts['uid'],facts['gid'],facts['links'])==(0,0,1)")
add('L19_private_any_links',"(facts['uid'],facts['gid'],facts['mode_octal'],facts['links'])==(0,0,'0600',1)","(facts['uid'],facts['gid'],facts['mode_octal'])==(0,0,'0600')")
add('L20_private_any_type',"    return facts is not None and facts['type']=='file' and (facts['uid']","    return facts is not None and (facts['uid']")
add('L21_inspect_mounts_unsorted',"    row['mounts']=sorted(mounts,key=lambda item:item['destination']);return row","    row['mounts']=mounts;return row")
add('L22_inspect_mount_rw_from_type',"mounts.append({'source':item['Source'],'destination':item['Destination'],'rw':item['RW']})","mounts.append({'source':item['Source'],'destination':item['Destination'],'rw':False})")

# (Not mutants, equivalent and recorded: C05 adding MATCH_VERIFIED to the published set, since every use of that set
# comes after the line's mode was required to be PUBLISH and MATCH_VERIFIED is a VERIFY_ONLY status; T03 the data
# volume as open root of every TREE chain, which is now the code: no other chain lies in the data volume. L12 and L14
# of k12_terminal moved to k12_window's list, where LAUNCH and PERSIST reach them.)
add('L23_line_with_text_after_its_newline_ok',"raw.endswith(b'\\n') and raw.count(b'\\n')==1,'WRITER_LINE_NOT_ONE_LINE')","raw.count(b'\\n')==1,'WRITER_LINE_NOT_ONE_LINE')")

add('K05_unknown_code_for_no_output',"    return 'UNKNOWN','ENDED_WITHOUT_A_LINE' if stdout==b'' else code","    return 'UNKNOWN',code")

# ---------------------------------------------------------------- effects_of(): one mutant per member
add('E01_operation',"    out={'operation':OPERATION,'mode':mode,'epoch':K12_EPOCH,'writes':0,","    out={'operation':PHASE,'mode':mode,'epoch':K12_EPOCH,'writes':0,",['operation'])
add('E02_mode',"'mode':mode,'epoch':K12_EPOCH,'writes':0,","'mode':'COLLECT','epoch':K12_EPOCH,'writes':0,",['mode'])
add('E03_epoch',"'epoch':K12_EPOCH,'writes':0,","'epoch':None,'writes':0,",['epoch'])
add('E04_writes',"'writes':0,'containers_started_stopped_or_removed':0,","'writes':1,'containers_started_stopped_or_removed':0,",['writes'])
add('E05_containers',"'containers_started_stopped_or_removed':0,'secret_files_opened':0,","'containers_started_stopped_or_removed':1,'secret_files_opened':0,",['containers_started_stopped_or_removed'])
add('E06_secret_files',"'secret_files_opened':0,\n         'activation':False}","'secret_files_opened':1,\n         'activation':False}",['secret_files_opened'])
add('E07_activation',"\n         'activation':False}","\n         'activation':None}",['activation'])
add('E08_tree_reads_metadata',"'metadata_only':[K12_SECRET_ENV,K12_PINS_ENV,","'metadata_only':[K12_PINS_ENV,",['reads'])
add('E09_boot',"out.update(evidence_boot_id_sha256=plan['evidence_boot_id_sha256'],","out.update(evidence_boot_id_sha256=None,",['evidence_boot_id_sha256'])
add('E10_capacity_sha',"capacity_request_sha256=derived['sha256'],day=derived['day'],","capacity_request_sha256=None,day=derived['day'],",['capacity_request_sha256'])
add('E11_day',"capacity_request_sha256=derived['sha256'],day=derived['day'],\n","capacity_request_sha256=derived['sha256'],day=None,\n",['day'])
add('E12_window',"               window=derived['window'],window_slot=derived['index'],","               window=None,window_slot=derived['index'],",['window'])
add('E13_window_slot',"window_slot=derived['index'],launch_request_sha256=plan['launch_request_sha256'],","window_slot=None,launch_request_sha256=plan['launch_request_sha256'],",['window_slot'])
add('E14_launch_sha',"launch_request_sha256=plan['launch_request_sha256'],\n","launch_request_sha256=None,\n",['launch_request_sha256'])
add('E15_chains',"               chains={key:chain_effects(plan['parent_rows'][key]) for key in C_COLLECT_CHAINS},","               chains={},",['chains'])
add('E16_reads_container',"reads={'container':['container','inspect','--format','<K12_FORMAT>',name],","reads={'container':['container','inspect',name],")
add('E17_not_before',"not_before=k12_at(derived['day'],K12_VIEW_UTC[derived['index']])+' + %d s'%C_COLLECT_AFTER_VIEW_SECONDS)","not_before=k12_at(derived['day'],K12_VIEW_UTC[derived['index']]))",['not_before'])
add('E18_reads_manifest',"'manifest':K12_MANIFESTS+'/'+derived['day']+'.json'},","'manifest':K12_MANIFESTS},")
add('E19_tree_directories',"out['reads']={'directories':{name:c_path(name,plan) for name in C_TREE},","out['reads']={'directories':{},")
add('E19b_tree_chain_rule',"                      'chain_rule':'ROOT_CONTROLLED_UID0_GID0_NO_GROUP_OR_OTHER_WRITE_NO_SETGID_NO_LINK',\n                      'metadata_only'",
    "                      'chain_rule':'ROOT',\n                      'metadata_only'")

# ---------------------------------------------------------------- the verdict, its order, its facts
add('V01_unavailable_container_absent',"    if container.get('status')!='COMPLETE':return 'UNCERTAIN','CONTAINER_UNAVAILABLE'","    if container.get('status')!='COMPLETE':return 'NOT_VERIFIED','CONTAINER_ABSENT'")
add('V02_absent_not_a_window',"    if not container['present']:return c_unless_published(manifest,'CONTAINER_ABSENT')","    if not container['present']:return 'NOT_VERIFIED','CONTAINER_ABSENT'")
add('V03_not_ours_accepted',"    if not container['ours']:return 'UNCERTAIN','CONTAINER_NOT_OF_THIS_WINDOW'\n","")
add('V04_running_accepted',"    if container['running'] or container['state'] not in ('exited','created'):return 'UNCERTAIN','CONTAINER_NOT_SETTLED'","    if container['state'] not in ('exited','created'):return 'UNCERTAIN','CONTAINER_NOT_SETTLED'")
add('V05_created_started',"return c_unless_published(manifest,'NEVER_STARTED') if not container['started'] else ('UNCERTAIN','CONTAINER_NOT_SETTLED')","return c_unless_published(manifest,'NEVER_STARTED')")
add('V06_persisted_unavailable',"    if persisted.get('status')!='COMPLETE':return 'UNCERTAIN','PERSISTED_RECEIPT_UNAVAILABLE'\n","")
add('V07_pending_as_not_verified',"    if not persisted['present']:return 'PENDING_PERSIST','LINE_NOT_YET_PERSISTED'","    if not persisted['present']:return 'NOT_VERIFIED','LINE_NOT_YET_PERSISTED'")
add('V08_invalid_accepted',"    if not persisted['valid']:return 'UNCERTAIN','PERSISTED_RECEIPT_INVALID'\n","")
add('V09_not_private_accepted',"    if not persisted['private']:return 'UNCERTAIN','PERSISTED_RECEIPT_NOT_PRIVATE'\n","")
add('V10_other_container_accepted',"    if not persisted['of_this_container']:return 'UNCERTAIN','PERSISTED_RECEIPT_NOT_OF_THIS_CONTAINER'\n","")
add('V11_unknown_end_as_not_verified',"    if persisted['ended']!='LINE':return 'UNCERTAIN',persisted['line_code']","    if persisted['ended']!='LINE':return 'NOT_VERIFIED',persisted['line_code']")
add('V46_stopped_as_not_verified',"    if persisted['ended']=='STOPPED':return 'STOPPED_BEFORE_THE_VIEW','STOPPED_WITHOUT_A_LINE'","    if persisted['ended']=='STOPPED':return 'NOT_VERIFIED','STOPPED_WITHOUT_A_LINE'")
add('V47_published_without_this_window',"    if manifest['present']:return 'UNCERTAIN','MANIFEST_PRESENT_WITHOUT_THIS_WINDOW'\n","")
add('V48_unpublished_manifest_unavailable',"    \"\"\"A window that did not run allows the next one, unless the day's manifest is on the host (or cannot be read).\"\"\"\n    if manifest.get('status')!='COMPLETE':return 'UNCERTAIN','MANIFEST_UNAVAILABLE'\n","    \"\"\"A window that did not run allows the next one, unless the day's manifest is on the host (or cannot be read).\"\"\"\n")
add('V49_empty_list_with_a_manifest',"('TERMINAL_EMPTY_LIST','MANIFEST_SYMBOLS_EMPTY') if not manifest['present'] else ('UNCERTAIN','MANIFEST_PRESENT_WITH_AN_EMPTY_LIST')","('TERMINAL_EMPTY_LIST','MANIFEST_SYMBOLS_EMPTY')")
add('V50_early_pins_ignored',"    if line.get('capacity_config_sha256',derived['config_sha256'])!=derived['config_sha256']","    if False and line.get('capacity_config_sha256',derived['config_sha256'])!=derived['config_sha256']")
add('V51_early_owner_ignored',"       or line.get('owner_uid',0)!=0:","       or False:")
add('V52_listing_not_asked',"        need(name not in [item['name'] for item in container_list(commands,docker_config=K12_DOCKER_CLI)],'CONTAINER_UNREADABLE')\n","")
add('V53_ended_detail_lost',"    out['ended']=ended;out['line_valid']=ended=='LINE';","    out['ended']='LINE';out['line_valid']=ended=='LINE';")
add('V54_stdout_bytes_fact',"out['stdout_bytes']=value['stdout_bytes']","out['stdout_bytes']=0")
add('V47_stop_from_the_container_ignored',"    if not persisted['present'] and k12_stopped(container['exit_code'],container['oom_killed'],container['finished_at'],derived['view_opens_at']):\n",
    "    if False:\n")
add('V48_stop_from_the_container_over_a_receipt',"    if not persisted['present'] and k12_stopped(container['exit_code']","    if k12_stopped(container['exit_code']")
add('V49_stop_from_the_container_not_verified',"        return 'STOPPED_BEFORE_THE_VIEW','STOPPED_BEFORE_ITS_VIEW'","        return 'NOT_VERIFIED','STOPPED_BEFORE_ITS_VIEW'")
add('V50_stop_judged_at_the_primary_view',"container['finished_at'],derived['view_opens_at']):","container['finished_at'],k12_at(derived['day'],K12_VIEW_UTC[1])):")
add('V52_collect_chains_not_root_controlled',"        k12_root_chain(rows[name],C_PATHS[name])","        validate_chain(rows[name],C_PATHS[name])")
add('V15_empty_list_not_terminal',"    if k12_terminal(line)=='EMPTY_LIST':\n","    if False:\n")
add('V16_any_status_published',"    if line['status'] not in K12_WRITER_PUBLISHED:return 'NOT_VERIFIED','WRITER_'+line['status']\n","")
add('V17_manifest_unavailable_ignored',"        return 'UNCERTAIN','LINE_PINS_NOT_THE_SIGNED_ONES'\n    if manifest.get('status')!='COMPLETE':return 'UNCERTAIN','MANIFEST_UNAVAILABLE'\n","        return 'UNCERTAIN','LINE_PINS_NOT_THE_SIGNED_ONES'\n")
add('V18_manifest_hash_ignored',"manifest['_sha256'] is not None and manifest['_sha256']==line.get('manifest_sha256')):","manifest['_sha256'] is not None):")
add('V19_manifest_privacy_ignored',"    if not (manifest['present'] and manifest['private'] and manifest['_sha256']","    if not (manifest['present'] and manifest['_sha256']")
add('V20_owner_ignored',"    if line.get('owner_uid')!=0 or line.get('capacity_config_sha256')","    if line.get('capacity_config_sha256')")
add('V21_config_ignored',"or line.get('capacity_config_sha256')!=derived['config_sha256'] or line.get('release_sha256')","or line.get('release_sha256')")
add('V22_release_ignored',"or line.get('release_sha256')!=derived['release_sha256'] \\\n","\\\n")
add('V23_package_ignored',"       or line.get('package_sha256')!=derived['package_sha256'] or line.get('build_sha')","       or line.get('build_sha')")
add('V24_build_ignored',"or line.get('build_sha')!=derived['build_sha']:","or False:")
add('V25_go_mode_ignored',"    if line['status']=='PUBLISHED_VERIFIED' and derived['require_go_mode'] is not None and line.get('go_mode')!=derived['require_go_mode']:",
    "    if False:")
add('V26_go_mode_checked_on_already',"    if line['status']=='PUBLISHED_VERIFIED' and derived['require_go_mode'] is not None","    if derived['require_go_mode'] is not None")
add('V27_contingency_flag',"'contingency_allowed':verdict=='NOT_VERIFIED',","'contingency_allowed':verdict in ('NOT_VERIFIED','PENDING_PERSIST'),")
add('V28_day_decided',"'day_decided':verdict in ('VERIFIED','TERMINAL_EMPTY_LIST','STOPPED_BEFORE_THE_VIEW'),","'day_decided':verdict in ('VERIFIED','TERMINAL_EMPTY_LIST'),")
add('V29_equal_flag',"if line is not None and manifest.get('status')=='COMPLETE' and manifest.get('_sha256') is not None:equal=manifest['_sha256']==line.get('manifest_sha256')",
    "if line is not None and manifest.get('status')=='COMPLETE' and manifest.get('_sha256') is not None:equal=True")
add('V30_binding_flag',"'binding_may_be_committed':None if line is None else line.get('prepare_status') in ('ATTEMPTED',)+K12_COMMITTED,",
    "'binding_may_be_committed':None if line is None else line.get('prepare_status') in K12_COMMITTED,")
add('V31_complete_without_stability',"    complete=verdict=='VERIFIED' and not findings and all(item.get('status')=='COMPLETE' for item in items.values())\n    return complete,top,findings",
    "    complete=verdict=='VERIFIED'\n    return complete,top,findings")
add('V32_stable_not_checked',"    if items['directories_stable']['status']!='COMPLETE':findings.append('DIRECTORIES_NOT_STABLE')\n","")
add('V33_public_keeps_private_keys',"def c_public(item):return {key:value for key,value in item.items() if not key.startswith('_')}","def c_public(item):return dict(item)")
add('V34_of_this_container_ignores_the_finish',"value['started_at'],\n                                                                  value['finished_at'])==","value['started_at'],\n                                                                  container.get('finished_at'))==")
add('V35_of_this_container_ignores_the_exit',"(value['container_id'],value['exit_code'],value['oom_killed'],","(value['container_id'],container.get('exit_code'),value['oom_killed'],")
add('V36_manifest_temporary_pattern',"pattern=r'\\.'+re.escape(day+'.json')+r'\\.[0-9a-f]{16}\\.tmp'\n    for name in host.names(held.fd):","pattern=r'\\..*\\.tmp'\n    for name in host.names(held.fd):")
add('V37_manifest_read_through_a_link',"    if found['type']=='file':\n        raw,_=read_regular(","    if found['type'] in ('file','symlink'):\n        raw,_=read_regular(")
add('V38_exit_code_fact',"'exit_code':container.get('exit_code'),\n","'exit_code':None,\n")
add('V39_manifest_fact',"{'present':manifest['present'],'private_one_link':bool(manifest.get('private'))}}","{'present':manifest['present'],'private_one_link':True}}")
add('V40_window_before_the_view',"    need((begun-view).total_seconds()>=C_COLLECT_AFTER_VIEW_SECONDS,'COLLECT_BEFORE_THE_VIEW_AND_A_MINUTE')","    need((begun-view).total_seconds()>=0,'COLLECT_BEFORE_THE_VIEW_AND_A_MINUTE')")
add('V41_boot_not_compared',"            if plan['mode']=='COLLECT':need(boot==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')","            pass")
add('V42_run_stopped_complete',"            return finish(PARTIAL_STATUS,ESCAPED_OUTCOME,code_of(error,'RUN_STOPPED'),","            return finish(COMPLETE_STATUS,ESCAPED_OUTCOME,code_of(error,'RUN_STOPPED'),")
add('V43_container_absent_any_failure',"    except CommandFailed:\n        # absent only","    except Refused:\n        # absent only")
add('V44_observe_swallows_expiry',"        if str(error) in ('GO_EXPIRED','CLOCK_REVERSED'):raise\n","")
add('V45_tree_boot_not_reported',"top['boot_id_sha256']=boot","top['boot_id_sha256']=None")

# ---------------------------------------------------------------- TREE
add('T01_tree_private_not_checked',"        if not item['private']:findings.append('DIRECTORY_NOT_ROOT_PRIVATE:'+key)\n","")
add('T02_tree_rows_not_validated',"        except Refused as error:findings.append(code_of(error,'CHAIN_ROW_UNSAFE')+':'+key)","        except Refused as error:pass")
add('T02b_tree_rows_not_root_controlled',"            else:k12_root_chain(item['rows'],c_path(key,plan))","            else:validate_chain(item['rows'],c_path(key,plan))")
add('T02c_tree_data_as_root_chain',"            if key=='data':k12_data_chain(item['rows'])","            if False:k12_data_chain(item['rows'])")
add('T02d_tree_release_file_privacy_not_judged',"'maintenance.lock',K12_RELEASE_FILE):","'maintenance.lock'):")
add('R01_collect_data_as_root_chain',"        if name=='data':k12_data_chain(rows[name]);continue","        if False:k12_data_chain(rows[name]);continue")
add('R02_release_unavailable_ignored',"    if release.get('status')!='COMPLETE':return 'UNCERTAIN','RELEASE_UNAVAILABLE'\n","")
add('R03_release_change_ignored',"    if not release['as_signed']:return 'UNCERTAIN','RELEASE_NOT_THE_SIGNED_BYTES'","    pass")
add('R04_release_failure_as_signed',"    except Refused as error:return {'as_signed':False,'code':str(error)}","    except Refused as error:return {'as_signed':True,'code':str(error)}")
add('T05_tree_file_privacy_not_checked',"            if not items['files'][name]['private']:findings.append('FILE_NOT_ROOT_PRIVATE:'+name)","            pass")
add('T06_tree_docker_cli_not_checked',"        if items['files']['docker_cli_entries']!=0:findings.append('DOCKER_CLI_DIRECTORY_NOT_EMPTY')\n","")
add('T07_tree_private_mode',"'private':(leaf['uid'],leaf['gid'],leaf['mode'])==(0,0,0o700),","'private':(leaf['uid'],leaf['gid'])==(0,0),")
add('T08_tree_rows_reported',"    return complete,{'observed_rows':{key:items['directory:'+key].get('rows') for key in C_TREE}},findings","    return complete,{'observed_rows':{}},findings")
add('T09_tree_complete_with_findings',"    complete=not findings and all(item.get('status')=='COMPLETE' for item in items.values())\n    return complete,{'observed_rows'","    complete=True\n    return complete,{'observed_rows'")
add('T10_tree_secret_name',"            for key,name in (('reader_config','secret.env'),","            for key,name in (('reader_config','secret'),")

# ---------------------------------------------------------------- the dispatcher generated for this operation (READ): the core's own rows apply
DISPATCHER=[]
CORE_ROWS_REPLACED=()

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
    """One plan per mode, from the fixtures' own builder (tests/k12r.py), so that every member of every mode is named."""
    here=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(here/'tests'));sys.path.insert(0,str(here.parent/'core'/'tests'))
    try:
        import k12r
        out=[]
        for mode in ('COLLECT','TREE'):
            docs,_=k12r.case(mode);out.append(docs.plan)
        return out
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
    eligible=[row for row in checks((here/'op.py').read_text()) if (row[0] not in COMMON or row[0] in HOME)
              and not (row[1]=='code_of' and (row[0],row[2]) in FALLBACKS_NOT_ASSERTED)]
    if len(GENERATED)!=len(eligible):errors.append('generated rows do not match the checks of the source')
    return errors
