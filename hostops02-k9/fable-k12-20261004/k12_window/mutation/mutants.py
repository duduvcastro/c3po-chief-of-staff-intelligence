"""The mutants of K12w's own part. Each row: (name, target, exact anchor, replacement); target 'op' is the built source
build/k12_window.py, in which the anchor must occur exactly once (mutate.py check).

Two kinds of rows:
  generated  one per check of the operation part, read from op.py's syntax tree: every need(<condition>,'<CODE>') is
             replaced by need(True,'<CODE>') (the check removed), every raise of Refused('<CODE>') and every constant
             fallback of code_of() gets another code. The functions of the K12 common block are generated in the family
             that is their home (HOME below; the block is the same bytes in the three families and common_block.py
             check pins it): here the REQUEST, the journal, the argv builder and the identification of a container.
  written    the constants, the fixed words, every member of effects_of() (EFFECTS names the mutant of each), the
             settlement of every effect, the order of the checks and the outcome of each mode.
coverage() compares both with the source itself: a check, a code or an effects member without a mutant is an error of
`mutate.py check`."""
import ast
import hashlib
from pathlib import Path
import re
import sys

FAMILY='k12_window'
HOME=('k12_ended','k12_instant','k12_journal','k12_capacity_request','k12_mount_word','k12_container_words','k12_expected_mounts','k12_ours',
      'k12_data','k12_root_chain','k12_stopped','k12_receipt_line','k12_data_chain','k12_release')
COMMON=('k12_compact','k12_container_name','k12_preflight_name','k12_persisted_name','k12_writer_name','k12_at','k12_instant','k12_journal',
        'k12_capacity_request','k12_mount_word','k12_container_words','k12_expected_mounts','k12_inspect','k12_ours','k12_writer_line',
        'k12_line_public','k12_persisted','k12_entry','k12_file','k12_private','k12_line_of','k12_ended','k12_terminal',
        'k12_data','k12_root_chain','k12_stopped','k12_receipt_line','k12_data_chain','k12_release')
# code_of() fallbacks that no test can reach: k12_receipt_line raises Refused with a code always.
FALLBACKS_NOT_ASSERTED=(('k12_ended','WRITER_LINE_INVALID'),)

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

# ---------------------------------------------------------------- the constants and the clock (common block: home here)
add('C01_another_epoch',"K12_EPOCH='R2D2-V2-SHADOW-2026-10-05'","K12_EPOCH='R2D2-V2-SHADOW-2026-09-28'",['epoch'])
add('C02_monday_is_a_capacity_day',"K12_DAYS=('2026-10-06',","K12_DAYS=('2026-10-05','2026-10-06',")
add('C03_friday_is_not',"'2026-10-08','2026-10-09')\nK12_VIEW_UTC","'2026-10-08')\nK12_VIEW_UTC")
add('C04_primary_view_at_the_cap_default',"K12_VIEW_UTC={1:'10:45:00',","K12_VIEW_UTC={1:'10:30:00',",['view_opens_at'])
add('C05_second_view',"2:'11:45:00',","2:'11:30:00',")
add('C06_third_view',"3:'12:45:00'}","3:'12:30:00'}")
add('C07_cutoff',"K12_CUTOFF_UTC='13:20:00'","K12_CUTOFF_UTC='13:30:00'",['cutoff_at'])
add('C08_view_life',"K12_VIEW_SECONDS=10\n","K12_VIEW_SECONDS=11\n")
add('C09_wait',"K12_MAX_WAIT_SECONDS=900\n","K12_MAX_WAIT_SECONDS=899\n")
add('C11_capacity_root',"K12_CAPACITY_ROOT='/var/lib/c3po-capacity'","K12_CAPACITY_ROOT='/var/lib/c3po-capacity-tree'")
add('C12_config_root',"K12_CONFIG_ROOT=K12_CAPACITY_ROOT+'/config'","K12_CONFIG_ROOT=K12_CAPACITY_ROOT+'/documents'")
add('C13_capacity_target',"K12_CAPACITY_TARGET='/c3po-capacity'","K12_CAPACITY_TARGET='/c3po-capacity-tree'")
add('C14_config_target',"K12_CONFIG_TARGET=K12_CAPACITY_TARGET+'/config'","K12_CONFIG_TARGET=K12_CONFIG_ROOT")
add('C15_data_volume',"K12_DATA_VOLUME='/mnt/day-d-data'","K12_DATA_VOLUME='/mnt/day-d'")
add('C16_data_target',"K12_DATA_TARGET='/app/day-d-data'","K12_DATA_TARGET='/day-d-data'")
add('C17_bar_config',"K12_BAR_CONFIG='/etc/c3po-bar'\n","K12_BAR_CONFIG='/etc/c3po'\n")
add('C18_manifests',"K12_MANIFESTS=K12_BAR_CONFIG+'/manifests'","K12_MANIFESTS=K12_BAR_CONFIG")
add('C19_reader_config',"K12_READER_CONFIG='/etc/c3po-reader'","K12_READER_CONFIG='/etc/c3po-reader-config'")
add('C20_secret_env',"K12_SECRET_ENV=K12_READER_CONFIG+'/secret.env'","K12_SECRET_ENV=K12_READER_CONFIG+'/pins.env'")
add('C21_pins_env',"K12_PINS_ENV=K12_READER_CONFIG+'/pins.env'","K12_PINS_ENV=K12_READER_CONFIG+'/pins'")
add('C22_docker_cli',"K12_DOCKER_CLI=K12_READER_CONFIG+'/docker-cli'","K12_DOCKER_CLI='/root/.docker'",['docker_config'])
add('C23_receipts',"K12_RECEIPTS=K12_READER_STATE+'/capacity-receipts'","K12_RECEIPTS=K12_CAPACITY_ROOT+'/receipts'")
add('C24_journal_may_be_in_the_data_volume',"K12_JOURNAL_FORBIDDEN=(K12_DATA_VOLUME,","K12_JOURNAL_FORBIDDEN=(")
add('C25_journal_may_be_in_the_reader_state',",K12_READER_CONFIG,K12_READER_STATE,K12_SOURCE_ROOT)",",K12_READER_CONFIG,K12_SOURCE_ROOT)")
add('C25b_binds_may_be_in_the_source_root',",K12_READER_STATE,K12_SOURCE_ROOT)",",K12_READER_STATE)")
add('C25c_another_source_root',"K12_SOURCE_ROOT='/var/lib/c3po/r2d2-v2-source-20261005'","K12_SOURCE_ROOT='/var/lib/c3po/r2d2-v2-source-20261006'")
add('C26_writer_stem',"K12_WRITER_STEM='manifest_writer-'","K12_WRITER_STEM='manifest_writer_'")
add('C27_writer_limit',"K12_WRITER_MAX_BYTES=131072","K12_WRITER_MAX_BYTES=4096")
add('C28_request_limit',"K12_REQUEST_MAX_BYTES=16384","K12_REQUEST_MAX_BYTES=65536")
add('C29_stdout_limit',"K12_STDOUT_MAX_BYTES=16384","K12_STDOUT_MAX_BYTES=16385")
add('C30_request_schema',"K12_CAPACITY_REQUEST_SCHEMA='R2D2_CAPACITY_DAY_ONCE_REQUEST_V1'","K12_CAPACITY_REQUEST_SCHEMA='R2D2_CAPACITY_DAY_ONCE_REQUEST_V2'")
add('C31_request_operation',"K12_CAPACITY_OPERATION='GO_CAPACITY_DAY_03'","K12_CAPACITY_OPERATION='GO_CAPACITY_DAY_02'")
add('C32_label_request',"K12_LABEL_REQUEST='c3po.k12.request_sha256'","K12_LABEL_REQUEST='c3po.k12.request'")
add('C33_label_capacity',"K12_LABEL_CAPACITY='c3po.k12.capacity_request_sha256'","K12_LABEL_CAPACITY='c3po.k12.capacity'")
add('C34_persisted_schema',"K12_PERSISTED_SCHEMA='K12_PERSISTED_WRITER_RECEIPT_V1'","K12_PERSISTED_SCHEMA='K12_PERSISTED_WRITER_RECEIPT_V0'")
add('C35_never_started',"K12_NEVER_STARTED='0001-01-01T00:00:00Z'","K12_NEVER_STARTED='0001-01-01T00:00:00.000Z'")
add('C36_container_name',"def k12_container_name(day,index):return 'c3po-k12-%s-w%d'%(k12_compact(day),index)",
    "def k12_container_name(day,index):return 'c3po-k12-%s-%d'%(k12_compact(day),index)",['container_name'])
add('C37_compact_keeps_the_dashes',"def k12_compact(day):return day.replace('-','')","def k12_compact(day):return day")
add('C38_persisted_name',"def k12_persisted_name(day,index):return 'k12-%s-w%d.writer.json'%(day,index)",
    "def k12_persisted_name(day,index):return 'k12-%s-w%d.json'%(day,index)",['creates'])
add('C39_writer_name',"def k12_writer_name(digest):return K12_WRITER_STEM+digest+'.py'","def k12_writer_name(digest):return K12_WRITER_STEM+digest",['writer'])
add('C40_instant_grammar',"K12_INSTANT='[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}[+]00:00'","K12_INSTANT='[0-9T:.Z+-]{19,40}'")
add('C41_launch_lead',"W_LAUNCH_LEAD_SECONDS=45 ","W_LAUNCH_LEAD_SECONDS=44 ")
add('C42_stop_lead',"W_STOP_LEAD_SECONDS=25 ","W_STOP_LEAD_SECONDS=24 ",['not_later_than_seconds_before_the_view'])
add('C43_persist_after_view',"W_PERSIST_AFTER_VIEW_SECONDS=60 ","W_PERSIST_AFTER_VIEW_SECONDS=59 ")
add('C44_remove_day',"W_REMOVE_DAY='2026-10-09'","W_REMOVE_DAY='2026-10-08'")
add('C45_remove_hour',"W_REMOVE_NOT_BEFORE='20:00:00'","W_REMOVE_NOT_BEFORE='19:59:59'")
add('C46_allowance',"W_ALLOWANCE_SECONDS=4 ","W_ALLOWANCE_SECONDS=3 ")
add('C48_stop_grace',"W_STOP_SECONDS='5'","W_STOP_SECONDS='10'",['stop'])
add('C49_launch_chains_lose_the_journal',"W_CHAINS={'LAUNCH':('config','manifests','reader_config','docker_cli','journal','data','receipts'),",
    "W_CHAINS={'LAUNCH':('config','manifests','reader_config','docker_cli','data','receipts'),",['chains'])
add('C49b_launch_chains_lose_the_data',"W_CHAINS={'LAUNCH':('config','manifests','reader_config','docker_cli','journal','data','receipts'),",
    "W_CHAINS={'LAUNCH':('config','manifests','reader_config','docker_cli','journal','receipts'),")
for index,member in enumerate(('config','manifests','reader_config','docker_cli','journal','receipts')):
    rest=[name for name in ('config','manifests','reader_config','docker_cli','journal','receipts') if name!=member]
    add('C49p%d_%s_leaf_not_private'%(index,member),"W_PRIVATE=('config','manifests','reader_config','docker_cli','journal','receipts')","W_PRIVATE=(%s)"%','.join(repr(name) for name in rest))
# (rev 3: C49q, the data leaf made private in w_chains, is equivalent: the data chain never reaches that check.)
add('C49r_root_chain_without_the_gid',"    need(all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows),'CHAIN_NOT_ROOT_CONTROLLED')",
    "    need(all(not row['mode']&stat.S_ISGID for row in rows),'CHAIN_NOT_ROOT_CONTROLLED')")
add('C49s_root_chain_without_setgid',"    need(all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows),'CHAIN_NOT_ROOT_CONTROLLED')",
    "    need(all(row['gid']==0 for row in rows),'CHAIN_NOT_ROOT_CONTROLLED')")
add('C49t_root_chain_only_the_leaf',"    need(all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows),'CHAIN_NOT_ROOT_CONTROLLED')",
    "    need(all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows[-1:]),'CHAIN_NOT_ROOT_CONTROLLED')")
add('C49u_root_chain_open_root',"    validate_chain(rows,path)\n    need(all(","    validate_chain(rows,path,open_root=path)\n    need(all(")
add('C50_persist_walks_the_manifests',"'PERSIST':('receipts',),","'PERSIST':('receipts','manifests'),")
add('C51_stop_walks_the_receipts',"'STOP':('manifests',),","'STOP':('receipts',),")
add('C52_date_class',"DATE_CLASS='WRITE_SESSIONS'","DATE_CLASS='WRITE_EPOCH'")
add('C53_evidence_operation',"EVIDENCE_OPERATIONS=('GO_READONLY_HOSTOPS02_K12_COLLECT_01',)","EVIDENCE_OPERATIONS=()")
add('C54_gate_span',"MAX_GATE_SPAN_SECONDS=900","MAX_GATE_SPAN_SECONDS=3600")
add('C55_modes',"W_MODES=('LAUNCH','PERSIST','STOP','REMOVE')","W_MODES=('LAUNCH','PERSIST','STOP','REMOVE','RUN')")

# ---------------------------------------------------------------- the fixed words of the rows
add('R01_create_may_pull',"K12_CREATE_PREFIX=['create','--pull','never',","K12_CREATE_PREFIX=['create','--pull','missing',",['create'])
add('R02_create_without_init',"'--pull','never','--init','--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',\n                   '--restart','no']",
    "'--pull','never','--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',\n                   '--restart','no']")
add('R03_create_writable_root',"'--init','--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',\n                   '--restart','no']",
    "'--init','--user','0:0','--cap-drop','ALL','--security-opt','no-new-privileges',\n                   '--restart','no']")
add('R04_create_restarts',"\n                   '--restart','no']","\n                   '--restart','on-failure']")
add('R05_create_with_rm',"K12_CREATE_PREFIX=['create',","K12_CREATE_PREFIX=['create','--rm',")
add('R06_start_class',"'start':command_row('docker',['start'],'exactly the 64-hex ID that create printed','RUN_SHORT','EFFECT'),",
    "'start':command_row('docker',['start'],'exactly the 64-hex ID that create printed','QUICK','EFFECT'),",['start'])
add('R07_stop_class',"identified',\n                             'RUN_SHORT','EFFECT'),","identified',\n                             'QUICK','EFFECT'),")
add('R08_logs_verb',"'logs':command_row('docker',['logs'],","'logs':command_row('docker',['logs','--tail','1'],",['read'])
add('R09_remove_forces',"'remove':command_row('docker',['rm'],","'remove':command_row('docker',['rm','-f'],",['command','force'])
add('R10_remove_volumes',"'remove':command_row('docker',['rm'],","'remove':command_row('docker',['rm','-v'],",['volumes'])
add('R11_inspect_format_reads_a_label_wrong',"'\"request_label\":{{json (index .Config.Labels \"'+K12_LABEL_REQUEST+'\")}},'",
    "'\"request_label\":{{json (index .Config.Labels \"'+K12_LABEL_CAPACITY+'\")}},'")
add('R12_inspect_format_reads_the_mounts_of_the_config',"'\"auto_remove\":{{json .HostConfig.AutoRemove}},\"restart_policy\":{{json .HostConfig.RestartPolicy.Name}},\"mounts\":{{json .Mounts}}}')",
    "'\"auto_remove\":{{json .HostConfig.AutoRemove}},\"restart_policy\":{{json .HostConfig.RestartPolicy.Name}},\"mounts\":[]}')")
add('R13_create_class',"'signed REQUEST, the signed image ID, python -I -B <the writer in the config root> and the REQUEST\\'s writer argv',\n                               'QUICK','EFFECT'),",
    "'signed REQUEST, the signed image ID, python -I -B <the writer in the config root> and the REQUEST\\'s writer argv',\n                               'RUN','EFFECT'),")

# ---------------------------------------------------------------- the argv builder (common block: home here)
add('A01_no_name',"    words=['--name',name]\n","    words=[]\n")
add('A02_labels_dropped',"    for key,value in labels:words+=['--label','%s=%s'%(key,value)]\n","")
add('A03_env_files_swapped',"'--env-file',K12_SECRET_ENV,'--env-file',K12_PINS_ENV,","'--env-file',K12_PINS_ENV,'--env-file',K12_SECRET_ENV,")
add('A04_shadow_flag',"            '--env','C3PO_R2D2_V2_SHADOW_ENABLED=true','--env','C3PO_R2D2_V2_MASSIVE_BARS_ENABLED=true',",
    "            '--env','C3PO_R2D2_V2_SHADOW_ENABLED=false','--env','C3PO_R2D2_V2_MASSIVE_BARS_ENABLED=true',")
add('A05_bars_flag',"'--env','C3PO_R2D2_V2_MASSIVE_BARS_ENABLED=true',\n            '--env','C3PO_R2D2_V2_CAPACITY_CONFIG_FILE='",
    "\n            '--env','C3PO_R2D2_V2_CAPACITY_CONFIG_FILE='")
add('A06_config_file_host_path',"'--env','C3PO_R2D2_V2_CAPACITY_CONFIG_FILE='+K12_CONFIG_TARGET+'/'+derived['config_name'],",
    "'--env','C3PO_R2D2_V2_CAPACITY_CONFIG_FILE='+K12_CONFIG_ROOT+'/'+derived['config_name'],")
add('A07_config_sha_dropped',"\n            '--env','C3PO_R2D2_V2_CAPACITY_CONFIG_SHA='+derived['config_sha256']]","]")
add('A08_one_mount_dropped',"    for item in derived['mounts']:words+=['--mount',k12_mount_word(item)]","    for item in derived['mounts'][1:]:words+=['--mount',k12_mount_word(item)]")
add('A09_python_without_isolation',"derived['image_id'],'python','-I','-B',K12_CONFIG_TARGET","derived['image_id'],'python','-B',K12_CONFIG_TARGET")
add('A10_writer_on_the_host_path',"'-I','-B',K12_CONFIG_TARGET+'/'+k12_writer_name(derived['writer_sha256'])]+list(derived['writer_argv'])",
    "'-I','-B',K12_CONFIG_ROOT+'/'+k12_writer_name(derived['writer_sha256'])]+list(derived['writer_argv'])")
add('A11_argv_dropped',"+list(derived['writer_argv'])\n\ndef k12_expected_mounts","\n\ndef k12_expected_mounts")
add('A12_mount_word_flips_readonly',"return mount_argument({'source':item['source'],'target':item['target'],'read_only':item['readonly']})",
    "return mount_argument({'source':item['source'],'target':item['target'],'read_only':True})")
add('A13_expected_mount_rw',"'rw':not item['readonly']} for item in derived['mounts']]","'rw':item['readonly']} for item in derived['mounts']]")
add('A14_ours_ignores_the_name',"    return (row['name']=='/'+name and row['image_id']==derived['image_id']","    return (row['image_id']==derived['image_id']")
add('A15_ours_ignores_the_image',"row['name']=='/'+name and row['image_id']==derived['image_id'] and row['request_label']","row['name']=='/'+name and row['request_label']")
add('A16_ours_ignores_the_request_label',"and row['request_label']==request_sha256\n","\n")
add('A17_ours_ignores_the_capacity_label',"            and row['capacity_label']==derived['sha256'] and row['network_mode']","            and row['network_mode']")
add('A18_ours_ignores_the_network',"and row['network_mode']==derived['network'] and row['read_only_root'] is True","and row['read_only_root'] is True")
add('A19_ours_ignores_the_root',"and row['read_only_root'] is True\n","\n")
add('A20_ours_ignores_auto_remove',"            and row['auto_remove'] is False and row['restart_policy']","            and row['restart_policy']")
add('A21_ours_ignores_restart',"and row['restart_policy'] in ('no','') and row['mounts']==","and row['mounts']==")
add('A22_ours_ignores_the_mounts',"and row['mounts']==k12_expected_mounts(derived)\n","\n")
add('A23_ours_ignores_the_argv',"            and row['cmd']==['python','-I','-B',K12_CONFIG_TARGET+'/'+k12_writer_name(derived['writer_sha256'])]+derived['writer_argv'])",
    "            )")
add('A24_journal_allows_a_nested_target',"text(target,'/[a-z0-9][a-z0-9._-]{0,62}')","text(target,'/[a-z0-9][a-z0-9._/-]{0,62}')")
add('A25_journal_allows_the_app_target',"target not in (K12_DATA_TARGET,K12_CAPACITY_TARGET,K12_MANIFESTS,'/app','/etc')","target not in (K12_DATA_TARGET,K12_CAPACITY_TARGET,K12_MANIFESTS)")
add('A26_journal_allows_a_root_that_contains_another',"not any(inside(source,root) or inside(root,source) for root in K12_JOURNAL_FORBIDDEN)\n         and text(target",
    "not any(inside(source,root) for root in K12_JOURNAL_FORBIDDEN)\n         and text(target")
add('A27_request_argv_wait_from_the_constant',"'--view-opens-at',view,'--max-wait-seconds',str(wait)]","'--view-opens-at',view,'--max-wait-seconds',str(K12_MAX_WAIT_SECONDS)]")
add('A28_request_argv_individual_go_mode',"need(given==argv and mode in (None,'DELEGATED_ACT_B'),","need(given==argv and mode in (None,'DELEGATED_ACT_B','INDIVIDUAL'),")
add('A29_request_view_from_the_request',"    view=k12_at(day,K12_VIEW_UTC[index]);","    view=request['view_opens_at'];")
add('A30_request_window_index_one_more',"integer(position,0,2) and integer(count,1,3) and position<count","integer(position,0,3) and integer(count,1,4) and position<count")
add('A31_request_network_bridge',"request['network'] not in ('host','none','bridge','default')","request['network'] not in ('host','none')")

add('K01_stopped_any_exit',"    return (exit_code in (137,143) and oom_killed is False and text(","    return (oom_killed is False and text(")
add('K01b_stopped_exit_137_only',"    return (exit_code in (137,143) and oom_killed","    return (exit_code in (137,) and oom_killed")
add('K02_stopped_when_oom',"exit_code in (137,143) and oom_killed is False and text(","exit_code in (137,143) and text(")
add('K03_stopped_after_the_view',"            and finished[:19]<view[:19])","            and finished[:19]<=view[:19])")
add('K03b_stopped_any_instant',"and text(finished[:19],'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}')\n","and True\n")
add('K03c_finished_not_typed',"    finished=finished if type(finished) is str else ''\n","")
add('K04_stopped_with_output',"    if stdout==b'' and k12_stopped(","    if k12_stopped(")
add('K04b_stopped_not_a_stop',"value['finished_at'],view):return 'STOPPED',None","value['finished_at'],view):return 'UNKNOWN','ENDED_WITHOUT_A_LINE'")
add('K04c_line_without_its_exit',"    try:return 'LINE',k12_receipt_line(stdout,day,value['exit_code'])","    try:return 'LINE',k12_writer_line(stdout,day)")
add('K04d_receipt_any_exit',"and exit_code in K12_WRITER_STATUSES[line['status']] and line['session']==day","and line['session']==day")
add('K04e_receipt_any_session',"and line['session']==day and line['mode']=='PUBLISH',","and line['mode']=='PUBLISH',")
add('K04f_receipt_any_mode',"and line['session']==day and line['mode']=='PUBLISH',","and line['session']==day,")
# (rev 2: k12_terminal lost its "line is None" and "mode PUBLISH" clauses, dead once only complete receipts of a publish
# run reach it; rev 2's first run had K10/K11 on them survive, recorded here.)
add('K10_terminal_never_published',"    if line['status'] in K12_WRITER_PUBLISHED:return 'PUBLISHED'","    if False:return 'PUBLISHED'")
add('K11_terminal_published_status_set',"    if line['status'] in K12_WRITER_PUBLISHED:return 'PUBLISHED'","    if line['status']=='PUBLISHED_VERIFIED':return 'PUBLISHED'")
add('K06_wait_from_the_constant',"    wait=int(given[8])\n","    wait=K12_MAX_WAIT_SECONDS\n")
add('K07_wait_unbounded',"and int(given[8])<=K12_MAX_WAIT_SECONDS,'CAPACITY_REQUEST_WRITER_ARGV')","and True,'CAPACITY_REQUEST_WRITER_ARGV')")
add('K08_start_not_bound_by_the_wait',"<=min(wait,K12_MAX_START_SECONDS),'CAPACITY_REQUEST_CLOCK')","<=K12_MAX_START_SECONDS,'CAPACITY_REQUEST_CLOCK')")
add('K09_slot_is_the_position',"    index=position+1\n","    index=position\n")

# ---------------------------------------------------------------- effects_of(): one mutant per member
add('E01_operation',"    out={'operation':OPERATION,'mode':mode,","    out={'operation':PHASE,'mode':mode,",['operation'])
add('E02_mode',"'mode':mode,'epoch':K12_EPOCH,'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],","'mode':'LAUNCH','epoch':K12_EPOCH,'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],",['mode'])
add('E03_boot',"'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],\n         'chains'","'evidence_boot_id_sha256':None,\n         'chains'",['evidence_boot_id_sha256'])
add('E04_writes_into',"'writes_into_manifests_capacity_journal_or_data':False,","'writes_into_manifests_capacity_journal_or_data':None,",['writes_into_manifests_capacity_journal_or_data'])
add('E04b_chain_rule',"'writes_into_manifests_capacity_journal_or_data':False,'chain_rule':'ROOT_CONTROLLED_UID0_GID0_NO_GROUP_OR_OTHER_WRITE_NO_SETGID_NO_LINK',",
    "'writes_into_manifests_capacity_journal_or_data':False,'chain_rule':'ROOT',",['chain_rule'])
add('E04c_data',"        out['data']={'path':K12_DATA_VOLUME,'target':K12_DATA_TARGET,'read_only':True,","        out['data']={'path':K12_DATA_VOLUME,'target':K12_DATA_TARGET,'read_only':False,",['data'])
add('E04c2_data_release_hash',"                     'release':{'path':K12_RELEASE_DIR+'/'+K12_RELEASE_FILE,'sha256':derived['release_sha256'],",
    "                     'release':{'path':K12_RELEASE_DIR+'/'+K12_RELEASE_FILE,'sha256':None,")
add('D01_data_open_root_widened',"    validate_chain(rows,K12_RELEASE_DIR,open_root=K12_DATA_VOLUME)","    validate_chain(rows,K12_RELEASE_DIR,open_root='/mnt')")
add('D03_data_rule_on_the_volume_too',"for row in rows if not inside(row['path'],K12_DATA_VOLUME)),","for row in rows),")
add('D04_data_chain_setgid_allowed',"    need(all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows if not inside(","    need(all(row['gid']==0 for row in rows if not inside(")
add('D05_data_chain_any_gid',"    need(all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows if not inside(","    need(all(not row['mode']&stat.S_ISGID for row in rows if not inside(")
add('D06_data_bind_read_write',"need(mount=={'source':K12_DATA_VOLUME,'target':K12_DATA_TARGET,'readonly':True},","need(mount in ({'source':K12_DATA_VOLUME,'target':K12_DATA_TARGET,'readonly':True},{'source':K12_DATA_VOLUME,'target':K12_DATA_TARGET,'readonly':False}),")
add('D07_release_limit',"K12_RELEASE_MAX_BYTES=1048576","K12_RELEASE_MAX_BYTES=1048577")
add('D08_release_directory',"K12_RELEASE_DIR=K12_DATA_VOLUME+'/r2d2-v2-release-20261005'","K12_RELEASE_DIR=K12_DATA_VOLUME+'/r2d2-v2-release-20261004'")
add('D09_release_file',"K12_RELEASE_FILE='release.CERTIFIED.json'","K12_RELEASE_FILE='release.json'")
add('W1_release_not_checked_before_the_create',"    k12_release(host,handles['data'],gate,derived)\n","")
add('W2_release_not_checked_after_the_start',"    try:k12_release(ctx['host'],ctx['handles']['data'],ctx['gate'],derived)","    try:pass")
add('W3_data_chain_as_root_chain',"        if name=='data':k12_data_chain(rows[name]);continue           # the named","        if False:k12_data_chain(rows[name]);continue           # the named")
add('E04d_earlier_stopped',"        out['earlier_window_stopped_before_its_view']='REFUSED_DAY_STOPPED'","        out['earlier_window_stopped_before_its_view']='ALLOWED'",
    ['earlier_window_stopped_before_its_view'])
add('E04e_logs_bounds',"'stdout_bytes':K12_STDOUT_MAX_BYTES,'follow':False,'tail':False}","'stdout_bytes':K12_STDOUT_MAX_BYTES,'follow':False,'tail':None}",['logs_bounds'])
add('E04f_requires',"        out['requires']='EXACTLY_ONE_COMPLETE_WRITER_RECEIPT_CONSISTENT_WITH_THE_EXIT_CODE_NOT_OOM'","        out['requires']='A_LINE'",['requires'])
add('E05_environment_printed',"'environment_printed':False,'activation':False}","'environment_printed':None,'activation':False}",['environment_printed'])
add('E06_activation',"'environment_printed':False,'activation':False}","'environment_printed':False,'activation':None}",['activation'])
add('E07_removals_name',"out['removals']=[{'container_name':k12_container_name(item['day'],item['window_slot']),","out['removals']=[{'container_name':k12_container_name(item['day'],1),",['removals'])
add('E08_removals_require',"'require':'EXITED_WITH_ITS_PRIVATE_RECEIPT_OR_STOPPED_BEFORE_ITS_VIEW_OR_NEVER_STARTED'}","'require':'EXITED'}")
add('E09_command_order',"out['command']=['rm']+[item['container_id'] for item in plan['removals']]","out['command']=['rm']+sorted(item['container_id'] for item in plan['removals'])")
add('E10_capacity_request_sha',"out.update(capacity_request_sha256=derived['sha256'],day=derived['day'],","out.update(capacity_request_sha256=None,day=derived['day'],",['capacity_request_sha256'])
add('E11_day',"capacity_request_sha256=derived['sha256'],day=derived['day'],window=derived['window'],","capacity_request_sha256=derived['sha256'],day=None,window=derived['window'],",['day'])
add('E12_window',"day=derived['day'],window=derived['window'],window_slot=derived['index'],","day=derived['day'],window=None,window_slot=derived['index'],",['window'])
add('E13_window_slot',"window=derived['window'],window_slot=derived['index'],\n","window=derived['window'],window_slot=None,\n",['window_slot'])
add('E14_label_placeholder',"out['create']=K12_CREATE_PREFIX+k12_container_words(derived,name,w_labels(derived,'<this request\\'s sha256>'))",
    "out['create']=K12_CREATE_PREFIX+k12_container_words(derived,name,w_labels(derived,'<request>'))")
add('E15_start',"out['start']=['start','<the 64-hex ID create printed>']","out['start']=['start']")
add('E16_writer_path',"out['writer']={'path':K12_CONFIG_ROOT+'/'+k12_writer_name(derived['writer_sha256']),","out['writer']={'path':K12_CONFIG_TARGET+'/'+k12_writer_name(derived['writer_sha256']),")
add('E17_capacity_config',"out['capacity_config']={'path':K12_CONFIG_ROOT+'/'+derived['config_name'],'sha256':derived['config_sha256'],",
    "out['capacity_config']={'path':K12_CONFIG_ROOT+'/'+derived['config_name'],'sha256':derived['pins_sha256'],",['capacity_config'])
add('E18_pins_env',"out['pins_env']={'path':K12_PINS_ENV,'sha256':derived['pins_sha256'],","out['pins_env']={'path':K12_PINS_ENV,'sha256':derived['config_sha256'],",['pins_env'])
add('E19_secret_env',"'read':'METADATA_ONLY'}","'read':'BYTES'}",['secret_env'])
add('E20_journal',"out['journal']={'path':derived['journal']['source'],'target':derived['journal']['target'],","out['journal']={'path':derived['journal']['target'],'target':derived['journal']['target'],",['journal'])
add('E21_container_removed',"out['container']={'removed_on_exit':False,","out['container']={'removed_on_exit':True,",['container'])
add('E22_earlier_windows',"out['earlier_windows']='EXITED_WITH_PRIVATE_RECEIPT_AND_ONE_VALID_LINE_NOT_TERMINAL_OR_NEVER_STARTED_OR_ABSENT'","out['earlier_windows']='ANY'",['earlier_windows'])
add('E35_manifest_of_the_day',"out['manifest_of_the_day']='ABSENT_OR_TWO_LINKS_OR_AFTER_AN_EARLIER_WINDOW_WITH_A_LINE'","out['manifest_of_the_day']='ANY'",['manifest_of_the_day'])
add('E23_persist_launch_sha',"        out['launch_request_sha256']=plan['launch_request_sha256']\n        out['read']","        out['launch_request_sha256']=None\n        out['read']",['launch_request_sha256'])
add('E24_creates_mode',"out['creates']={'path':K12_RECEIPTS+'/'+k12_persisted_name(derived['day'],derived['index']),'mode_octal':'0600',",
    "out['creates']={'path':K12_RECEIPTS+'/'+k12_persisted_name(derived['day'],derived['index']),'mode_octal':'0644',")
add('E25_stop_launch_sha',"        out['launch_request_sha256']=plan['launch_request_sha256']\n        out['stop']","        out['launch_request_sha256']=None\n        out['stop']")
add('E26_force',"out['force']=False;out['volumes']=False","out['force']=None;out['volumes']=False")
add('E27_volumes',"out['force']=False;out['volumes']=False","out['force']=False;out['volumes']=None")
add('E28_chains_of_another_mode',"         'chains':{name:chain_effects(plan['parent_rows'][name]) for name in W_CHAINS[mode]},","         'chains':{},")
add('E29_view_opens_at',"container_name=name,view_opens_at=derived['view_opens_at'],cutoff_at=derived['cutoff_at'])","container_name=name,view_opens_at=derived['not_before'],cutoff_at=derived['cutoff_at'])")
add('E30_cutoff',"view_opens_at=derived['view_opens_at'],cutoff_at=derived['cutoff_at'])","view_opens_at=derived['view_opens_at'],cutoff_at=None)")
add('E31_docker_config',"        out['docker_config']=K12_DOCKER_CLI\n","        out['docker_config']=None\n")
add('E32_read_target',"out['read']=['logs','<the 64-hex ID of that exited container>']","out['read']=['logs']")
add('E33_stop_target',"out['stop']=['stop','-t',W_STOP_SECONDS,'<the 64-hex ID of that running container>']","out['stop']=['stop','<the 64-hex ID of that running container>']")
add('E34_container_name',"               container_name=name,view_opens_at","               container_name=None,view_opens_at")

# ---------------------------------------------------------------- the run: settlement, order, outcome
# (Not mutants, equivalent and recorded after the run of 2026-10-04: C10 K12_MAX_START_SECONDS 901, since the window's
# start is also bounded by the REQUEST's wait, at most 900; C47 W_MAX_REMOVALS 13, since four days of three slots give
# twelve distinct rows (the bound is now the distinctness); S03 `len(output)>=65`, since a longer output never ends in
# exactly one newline after 64 characters; S19 and S21 an unknown() before a stop code, since a returned effect left
# unsettled counts as uncertain by itself; S25 the window's own slot among the "earlier" names, since its own name is
# refused just before as CONTAINER_NAME_TAKEN.)
add('S01_create_absent_settled_as_unknown',"        if row is None and w_listed_without(commands,name):state.fail();return 'CREATE_FAILED'","        if row is None and w_listed_without(commands,name):state.unknown();return 'CREATE_FAILED'")
add('S35_create_absent_without_a_listing',"        if row is None and w_listed_without(commands,name):state.fail();return 'CREATE_FAILED'","        if row is None:state.fail();return 'CREATE_FAILED'")
add('S36_listing_that_fails_proves_absence',"    try:return name not in [row['name'] for row in container_list(commands,docker_config=K12_DOCKER_CLI)]\n    except Exception:return False","    try:return name not in [row['name'] for row in container_list(commands,docker_config=K12_DOCKER_CLI)]\n    except Exception:return True")
add('S37_manifest_rule_dropped',"    need(not (present is not None and present['links']==1 and not ctx.get('earlier_line')),'MANIFEST_PRESENT_WITHOUT_AN_EARLIER_WINDOW')","    pass")
add('S38_manifest_rule_two_links',"    need(not (present is not None and present['links']==1 and not ctx.get('earlier_line')),","    need(not (present is not None and not ctx.get('earlier_line')),")
add('S39_earlier_line_not_recorded',"        terminal=k12_terminal(line);ctx['earlier_line']=True","        terminal=k12_terminal(line)")
add('S45_earlier_stop_not_from_the_container',"            need(not (row is not None and k12_stopped(","            need(not (False and k12_stopped(")
add('S46_earlier_stop_with_a_failed_inspect',"            need(not (row is not None and k12_stopped(","            need(not (row is None or k12_stopped(")
add('S47_earlier_stop_judged_at_the_launched_view',"row['finished_at'],k12_at(day,K12_VIEW_UTC[index]))),\n                 'DAY_STOPPED_BEFORE_A_VIEW')",
    "row['finished_at'],derived['view_opens_at'])),\n                 'DAY_STOPPED_BEFORE_A_VIEW')")
add('P01_persist_lenient_line',"    try:line=k12_receipt_line(stdout,derived['day'],row['exit_code'])","    try:line=k12_writer_line(stdout,derived['day'])")
add('P02_persist_refusal_not_reported',"        detail['writer_line']={'valid':False,'code':str(error),'stdout_bytes':len(stdout)};raise","        raise")
add('P03_persist_oom_accepted',"    need(row['oom_killed'] is False and integer(row['exit_code'],0,255) and","    need(integer(row['exit_code'],0,255) and")
add('P04_persist_any_exit',"row['oom_killed'] is False and integer(row['exit_code'],0,255) and row['started_at']","row['oom_killed'] is False and row['started_at']")
add('P05_persist_exit_upper_bound',"integer(row['exit_code'],0,255)","integer(row['exit_code'],0,256)")
add('P06_persist_never_started_accepted',"and row['started_at']!=K12_NEVER_STARTED,'CONTAINER_EXIT_NOT_KNOWN')","and True,'CONTAINER_EXIT_NOT_KNOWN')")
add('R04_remove_stopped_needs_a_receipt',"                rows.append(w_summary(row));continue        # ended by D4's stop","                pass        # ended by D4's stop")
add('R05_remove_stopped_skips_a_present_receipt',"            if raw is None and k12_stopped(row['exit_code']","            if k12_stopped(row['exit_code']")
add('R06_remove_stopped_judged_at_the_primary_view',"k12_at(item['day'],K12_VIEW_UTC[item['window_slot']])):","k12_at(item['day'],K12_VIEW_UTC[1])):")
add('S40_stop_counts_as_a_line',"        need(ended!='STOPPED','DAY_STOPPED_BEFORE_A_VIEW')","        need(True,'DAY_STOPPED_BEFORE_A_VIEW')")
add('S41_earlier_view_of_this_window',"        ended,line=k12_ended(value,stdout,day,k12_at(day,K12_VIEW_UTC[index]))","        ended,line=k12_ended(value,stdout,day,derived['view_opens_at'])")
add('S42_launch_allowance',"W_ALLOWANCE_LAUNCH_SECONDS=10 ","W_ALLOWANCE_LAUNCH_SECONDS=9 ")
add('S43_persist_allowance',"W_ALLOWANCE_PERSIST_SECONDS=12 ","W_ALLOWANCE_PERSIST_SECONDS=11 ")
add('S02_create_settled_before_the_check',"    if row['state']!='created' or row['started_at']!=K12_NEVER_STARTED:state.unknown();return 'CREATED_CONTAINER_NOT_AS_SIGNED'\n",
    "    if row['state']!='created' and row['started_at']!=K12_NEVER_STARTED:state.unknown();return 'CREATED_CONTAINER_NOT_AS_SIGNED'\n")
add('S04_start_failure_settled_as_done',"    if row['started_at']==K12_NEVER_STARTED and row['state']=='created':state.fail();return 'START_FAILED'",
    "    if row['started_at']==K12_NEVER_STARTED and row['state']=='created':state.done();return 'START_FAILED'")
add('S05_start_nonzero_complete',"    if result['returncode']!=0:return 'START_RETURNED_NONZERO'\n","")
add('S06_logs_settled_as_done',"    state.fail()                    # docker logs reads","    state.done()                    # docker logs reads")
add('S07_logs_nonzero_accepted',"    if result['returncode']!=0:return 'LOGS_FAILED'\n","")
add('S08_stdout_unbounded',"    if len(stdout)>K12_STDOUT_MAX_BYTES:return 'STDOUT_TOO_LARGE'\n","")
add('S09_change_check_without_the_finish',"(again['id'],again['state'],again['finished_at'],again['exit_code'])!=(row['id'],row['state'],row['finished_at'],row['exit_code'])",
    "(again['id'],again['state'],again['exit_code'])!=(row['id'],row['state'],row['exit_code'])")
add('S10_no_readback_of_the_persisted_file',"    return readback_file(entry,content,PRIVATE_FILE_MODE,ctx['handles']['receipts'],ctx['host'],ctx['gate'])","    return None")
add('S11_persisted_without_the_exit_code',"'exit_code':row['exit_code'],'oom_killed':row['oom_killed'],'started_at'","'exit_code':0,'oom_killed':row['oom_killed'],'started_at'")
add('S12_persisted_with_the_launch_request_as_persist',"'persist_request_sha256':ctx['bound']['request_sha256'],","'persist_request_sha256':ctx['plan']['launch_request_sha256'],")
add('S13_stop_failure_as_done',"        state.fail();return 'STOP_FAILED'","        state.done();return 'STOP_FAILED'")
add('S14_stop_manifest_change_ignored',"    if detail['manifest_names_after']!=detail['manifest_names_before']:return 'MANIFEST_DIRECTORY_CHANGED_DURING_STOP'\n","")
add('S15_stop_nonzero_complete',"    if result['returncode']!=0:return 'STOP_RETURNED_NONZERO'\n    return None","    return None")
add('S16_remove_nothing_as_done',"    if removed:state.done()\n    else:state.fail()","    state.done()")
add('S17_remove_incomplete_ignored',"    if len(removed)!=len(identifiers):return 'REMOVE_INCOMPLETE'\n","")
add('S18_remove_nonzero_complete',"    if result['returncode']!=0:return 'REMOVE_RETURNED_NONZERO'\n","")
add('S20_refusal_after_an_effect',"        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)","        if stop:return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)")
add('S22_umask_not_set',"            host.umask(0o077)\n","")
add('S23_clock_after_the_boot',"            w_clock(plan,derived,begun)\n            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')",
    "            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')")
add('S24_stop_lead_uses_the_launch_lead',"    lead=W_LAUNCH_LEAD_SECONDS if mode=='LAUNCH' else W_STOP_LEAD_SECONDS","    lead=W_LAUNCH_LEAD_SECONDS")
add('S26_earlier_created_needs_a_receipt',"        if not found or found[0]['state']=='created':continue","        if not found:continue")
add('S27_earlier_receipt_of_another_container',"'day':day,'window_slot':index,'container_id':found[0]['id'],'container_name':name})","'day':day,'window_slot':index,'container_name':name})")
add('S28_launch_detail_lost',"    detail['launched']={'container_id':identifier,","    detail['launched_']={'container_id':identifier,")
add('S29_container_id_not_reported',"        extra={'phase_reached':'EFFECTS','container_id':ctx.get('container_id')}","        extra={'phase_reached':'EFFECTS','container_id':None}")
add('S30_remove_checks_only_the_first',"    for item in ctx['plan']['removals']:\n        name=k12_container_name","    for item in ctx['plan']['removals'][:1]:\n        name=k12_container_name")
add('S31_remove_persisted_without_identity',"'window_slot':item['window_slot'],'container_id':item['container_id'],","'window_slot':item['window_slot'],")
add('S32_manifest_state_counts_other_days',"        if name==day+'.json':present+=1","        if name.endswith('.json'):present+=1")
add('S33_start_unsettled_on_a_failure',"    if row['started_at']==K12_NEVER_STARTED:state.unknown();return 'STARTED_CONTAINER_NOT_READ_BACK'\n    state.done()",
    "    if row['started_at']==K12_NEVER_STARTED:state.unknown();return 'STARTED_CONTAINER_NOT_READ_BACK'\n    state.unknown()")
add('S34_line_public_detail_lost',"    detail['writer_line']={'valid':True,'code':None,'public':k12_line_public(line),","    detail['writer_line']={'valid':True,'code':None,'public':None,")

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
    """One plan per mode, from the fixtures' own builder (tests/k12w.py), so that every member of every mode is named."""
    here=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(here/'tests'));sys.path.insert(0,str(here.parent/'core'/'tests'))
    try:
        import k12w
        out=[]
        for mode in ('LAUNCH','PERSIST','STOP','REMOVE'):
            docs,_=k12w.case(mode);out.append(docs.plan)
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
