"""The mutants of K6b (capacity switch). Each row: (name, target, exact anchor, replacement); the anchor must occur
exactly once in build/capacity_switch.py (mutate.py check). Two origins, recorded per mutant in ORIGIN:

  GENERATED  one mutant per condition of every need(...) of the operation's own part: each operand of a conjunction
             dropped in turn, a single condition replaced by True (computed from op.py by its syntax tree, as K6a's).
  OWN        written by hand: identity, dates, flags; each constant; the editor's prefix and its script; each row of
             the command table; each member of effects_of(); each rule of the edit; each read of the host; the
             settlement of the editor and of the recreate; each criterion; each outcome; the budget.
One row removed as equivalent is named where it stood (K05). The core's own list (INHERITED in K6a) is not run against this suite: its kill is the core's record (CORE.md 9).
"""
import ast
import os
from pathlib import Path

HERE=Path(__file__).resolve().parent
OPERATION=HERE.parent
OP=(OPERATION/'op.py').read_text(encoding='ascii')
BUILT=(OPERATION/'build'/'capacity_switch.py').read_text(encoding='ascii')
M=[];ORIGIN={}
def add(name,old,new,origin='OWN',target='op'):
    M.append((name,target,old,new));ORIGIN[name]=origin

def generated():
    tree=ast.parse(OP);rows=[];count=0
    for node in ast.walk(tree):
        if not (isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='need' and len(node.args)==2):continue
        call=ast.get_source_segment(OP,node);condition=node.args[0];code=ast.get_source_segment(OP,node.args[1])
        label=code.strip("'") if code.startswith("'") else 'DYNAMIC_CODE'
        if isinstance(condition,ast.BoolOp) and isinstance(condition.op,ast.And):
            operands=[ast.get_source_segment(OP,value) for value in condition.values]
            for index in range(len(operands)):
                rest=operands[:index]+operands[index+1:];count+=1
                rows.append(('G%03d_%s_without_operand_%d'%(count,label,index+1),call,'need(%s,%s)'%(' and '.join(rest),code)))
        else:
            count+=1;rows.append(('G%03d_%s_always_true'%(count,label),call,'need(True,%s)'%code))
    return rows
GENERATED_SKIPPED=[]
for name,old,new in generated():
    if BUILT.count(old)==1:add(name,old,new,'GENERATED')
    else:GENERATED_SKIPPED.append(name)

# ---------------------------------------------------------------- identity, dates, flags, outcomes
add('A01_date_class_is_the_first_session_only',"DATE_CLASS='WRITE_SESSIONS'","DATE_CLASS='WRITE_FIRST_SESSION'")
add('A02_date_class_is_the_epoch',"DATE_CLASS='WRITE_SESSIONS'","DATE_CLASS='WRITE_EPOCH'")
add('A03_evidence_not_required',"EVIDENCE_REQUIRED=True","EVIDENCE_REQUIRED=False")
add('A04_no_evidence_operation',"EVIDENCE_OPERATIONS=('GO_WRITE_HOSTOPS02_ACTIVATE_01',)","EVIDENCE_OPERATIONS=()")
add('A05_gate_may_span_an_hour',"MAX_GATE_SPAN_SECONDS=900","MAX_GATE_SPAN_SECONDS=3600")
add('A06_success_outcome_renamed',"COMPLETE_OUTCOME='CAPACITY_SWITCH_APPLIED_WORKER_RECREATED_AND_VERIFIED'","COMPLETE_OUTCOME='CAPACITY_SWITCH_DONE'")
add('A09_not_verified_is_the_generic_partial',"NOT_VERIFIED_OUTCOME='PARTIAL_WORKER_RECREATED_NOT_FULLY_VERIFIED'","NOT_VERIFIED_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'")
add('A10_uncertain_is_the_generic_partial',"UNCERTAIN_OUTCOME='PARTIAL_UNCERTAIN_REQUIRES_READBACK'","UNCERTAIN_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'")
add('A11_refused_outcome_renamed',"REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'","REFUSED_OUTCOME='REFUSED'")
# ---------------------------------------------------------------- constants
add('B01_another_revision',"EPOCH_REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'","EPOCH_REVISION='4de7095ad51bce19ea4b685d5c708d0a72986d76'")
add('B02_another_service',"WORKER_SERVICE='r2d2-worker'","WORKER_SERVICE='api'")
add('B03_build_name_renamed',"BUILD_KEY='C3PO_BUILD_SHA'","BUILD_KEY='C3PO_BUILD'")
add('B04_three_activation_names',"ACTIVATION_KEYS=('C3PO_R2D2_V2_LIVE_POLICY_FILE','C3PO_R2D2_V2_LIVE_POLICY_SHA','C3PO_R2D2_V2_SHADOW_RELEASE_FILE','C3PO_R2D2_V2_SHADOW_RELEASE_SHA')",
    "ACTIVATION_KEYS=('C3PO_R2D2_V2_LIVE_POLICY_FILE','C3PO_R2D2_V2_LIVE_POLICY_SHA','C3PO_R2D2_V2_SHADOW_RELEASE_FILE')")
add('B05_env_file_renamed',"ENV_FILE_NAME='.env'","ENV_FILE_NAME='env'")
add('B06_compose_file_renamed',"COMPOSE_FILE_NAME='compose.yml'","COMPOSE_FILE_NAME='docker-compose.yml'")
add('B07_deploy_version_renamed',"DEPLOY_VERSION_NAME='.deploy-version'","DEPLOY_VERSION_NAME='.deploy-revision'")
add('B08_lock_directory_elsewhere',"LOCK_RELATIVE_DIRECTORY='runtime/security'","LOCK_RELATIVE_DIRECTORY='runtime'")
add('B09_reboot_marker_elsewhere',"REBOOT_PENDING_PATH='/run/c3po-security/reboot.pending'","REBOOT_PENDING_PATH='/run/c3po-security/reboot.requested'")
add('B10_env_limit_tiny',"MAX_ENV_FILE_BYTES=1048576","MAX_ENV_FILE_BYTES=16")
add('B11_override_limit_tiny',"MAX_OVERRIDE_BYTES=4096","MAX_OVERRIDE_BYTES=16")
add('B12_config_limit_tiny',"MAX_CONFIG_BYTES=1048576","MAX_CONFIG_BYTES=16")
add('B13_compose_limit_tiny',"MAX_COMPOSE_FILE_BYTES=1048576","MAX_COMPOSE_FILE_BYTES=4")
add('B14_mount_name_renamed',"KEY_MOUNT_SOURCE='C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE'","KEY_MOUNT_SOURCE='C3PO_R2D2_V2_CAPACITY_MOUNT'")
add('B15_config_file_name_renamed',"KEY_CONFIG_FILE='C3PO_R2D2_V2_CAPACITY_CONFIG_FILE'","KEY_CONFIG_FILE='C3PO_R2D2_V2_CAPACITY_CONFIG_PATH'")
add('B16_config_sha_name_renamed',"KEY_CONFIG_SHA='C3PO_R2D2_V2_CAPACITY_CONFIG_SHA'","KEY_CONFIG_SHA='C3PO_R2D2_V2_CAPACITY_CONFIG_SHA256'")
add('B17_veto_name_renamed',"KEY_VETO_MODE='C3PO_R2D2_V2_CAPACITY_VETO_MODE'","KEY_VETO_MODE='C3PO_R2D2_V2_CAPACITY_VETO'")
add('B18_required_name_renamed',"KEY_REQUIRED='C3PO_R2D2_V2_CAPACITY_REQUIRED'","KEY_REQUIRED='C3PO_R2D2_V2_CAPACITY_ENABLED'")
add('B19_required_not_last',"CAPACITY_KEYS=(KEY_MOUNT_SOURCE,KEY_CONFIG_FILE,KEY_CONFIG_SHA,KEY_VETO_MODE,KEY_REQUIRED)","CAPACITY_KEYS=(KEY_MOUNT_SOURCE,KEY_REQUIRED,KEY_CONFIG_FILE,KEY_CONFIG_SHA,KEY_VETO_MODE)")
add('B20_veto_mode_continuous',"VETO_MODE_VALUE='DISPATCH_AND_DERIVATION_ONLY'","VETO_MODE_VALUE='CONTINUOUS'")
add('B21_required_capitalised',"REQUIRED_VALUE='true'","REQUIRED_VALUE='True'")
add('B22_capacity_target_elsewhere',"CAPACITY_TARGET='/c3po-capacity'","CAPACITY_TARGET='/app/c3po-capacity'")
add('B23_go_not_among_the_subdirectories',"CAPACITY_SUBDIRECTORIES=('config','documents','go','payload')","CAPACITY_SUBDIRECTORIES=('config','documents','payload')")
add('B24_placeholder_renamed',"PLACEHOLDER_VOLUME='c3po_capacity_unprovisioned'","PLACEHOLDER_VOLUME='c3po_capacity'")
add('B25_data_target_elsewhere',"DATA_TARGET='/app/day-d-data'","DATA_TARGET='/app/data'")
add('B26_two_worker_targets',"WORKER_TARGETS=('/app/day-d-data','/c3po-capacity','/run/c3po-maintenance')","WORKER_TARGETS=('/app/day-d-data','/c3po-capacity')")
add('B27_capacity_line_without_export',"CAPACITY_LINE=re.compile(b'[ \\t]*(?:export[ \\t]+)?C3PO_R2D2_V2_CAPACITY_')","CAPACITY_LINE=re.compile(b'C3PO_R2D2_V2_CAPACITY_')")
add('B28_capacity_line_any_prefix',"CAPACITY_LINE=re.compile(b'[ \\t]*(?:export[ \\t]+)?C3PO_R2D2_V2_CAPACITY_')","CAPACITY_LINE=re.compile(b'C3PO_R2D2_V2_CAPACITY_MOUNT')")
add('B29_full_disable_not_from_the_mount_alone',"'DISABLE_FULL':{'before':(1,4,5),'after':0}","'DISABLE_FULL':{'before':(4,5),'after':0}")
add('B30_fast_disable_cuts_two_lines',"'DISABLE_FAST':{'before':(5,),'after':4}","'DISABLE_FAST':{'before':(5,),'after':3}")
add('B31_enable_without_the_flag',"'ENABLE':{'before':(1,),'after':5}","'ENABLE':{'before':(1,),'after':4}")
add('B32_mount_from_any_state',"MODES={'MOUNT':{'before':(0,),'after':1}","MODES={'MOUNT':{'before':(0,1),'after':1}")
add('B33_editor_owner_root',"ENV_OWNER=(1000,1000)","ENV_OWNER=(0,0)")
add('B34_editor_mode_0640',"ENV_MODE=0o600","ENV_MODE=0o640")
add('B35_editor_target_elsewhere',"ENV_EDITOR_TARGET='/c3po-env/.env'","ENV_EDITOR_TARGET='/c3po-env/env'")
add('B36_editor_on_the_bridge',"'--init','--user','%d:%d'%ENV_OWNER,'--network','none'","'--init','--user','%d:%d'%ENV_OWNER,'--network','bridge'")
add('B37_editor_root_writable',"'--network','none','--read-only','--cap-drop','ALL',\n                   '--security-opt','no-new-privileges']","'--network','none','--cap-drop','ALL',\n                   '--security-opt','no-new-privileges']")
add('B38_editor_without_init',"ENV_EDITOR_PREFIX=['run','--rm','-i','--pull','never','--init',","ENV_EDITOR_PREFIX=['run','--rm','-i','--pull','never',")
add('B39_editor_command_without_isolation',"ENV_EDITOR_COMMAND=['python','-I','-B','-']","ENV_EDITOR_COMMAND=['python','-B','-']")
add('B40_mounts_format_names_the_binds',"MOUNTS_FORMAT='{{json .Mounts}}'","MOUNTS_FORMAT='{{json .HostConfig.Binds}}'")
add('B41_no_mount_may_be_listed',"MAX_MOUNTS_LISTED=32","MAX_MOUNTS_LISTED=0")
add('B42_edit_row_class_run',"'QUICK','EFFECT',stdin=True)","'RUN','EFFECT',stdin=True)")
add('B43_editor_statuses_without_done',"ENV_EDIT_STATUSES=('ENV_EDIT_DONE','ENV_EDIT_REFUSED','ENV_EDIT_FAILED')","ENV_EDIT_STATUSES=('ENV_EDIT_REFUSED','ENV_EDIT_FAILED')")
# ---------------------------------------------------------------- the editor's script (killed by the real interpreter, test_editor_native.py)
add('S01_script_never_truncates',"                wrote=True;os.ftruncate(fd,len(new))\n","                wrote=True\n")
add('S02_script_ignores_the_links',"if not (stat.S_ISREG(info.st_mode) and info.st_nlink==1 and [info.st_uid,info.st_gid]==spec['owner']","if not (stat.S_ISREG(info.st_mode) and [info.st_uid,info.st_gid]==spec['owner']")
add('S03_script_ignores_the_owner',"and info.st_nlink==1 and [info.st_uid,info.st_gid]==spec['owner']\n","and info.st_nlink==1\n")
add('S04_script_ignores_the_mode',"                    and stat.S_IMODE(info.st_mode)==spec['mode'] and info.st_size<=LIMIT):","                    and info.st_size<=LIMIT):")
add('S05_script_follows_links',"try:fd=os.open(TARGET,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)","try:fd=os.open(TARGET,os.O_RDWR|os.O_CLOEXEC|os.O_NONBLOCK)")
add('S06_script_accepts_a_middle_block',"    if marks!=list(range(len(lines)-count,len(lines))):raise Stop('ENV_CAPACITY_LINES_NOT_TRAILING')\n","")
add('S07_script_accepts_any_block',"    if [line.decode('latin-1') for line in lines[len(lines)-count:]] not in spec['before']:raise Stop('ENV_CAPACITY_BLOCK_NOT_AS_SIGNED')\n","")
add('S08_script_accepts_a_last_line_without_newline',"    if raw!=b'' and not raw.endswith(b'\\\\n'):raise Stop('ENV_FILE_NOT_NEWLINE_TERMINATED')\n","")
add('S09_script_capacity_without_export',"CAPACITY=re.compile(b'[ \\\\t]*(?:export[ \\\\t]+)?C3PO_R2D2_V2_CAPACITY_')","CAPACITY=re.compile(b'C3PO_R2D2_V2_CAPACITY_')")
add('S11_script_writes_at_the_start',"written=os.pwrite(fd,data,len(raw))","written=os.pwrite(fd,data,0)")
add('S13_script_no_size_limit',"and info.st_size<=LIMIT):raise Stop('ENV_FILE_NOT_AS_EXPECTED')","):raise Stop('ENV_FILE_NOT_AS_EXPECTED')")
add('S16_script_read_misses_the_end',"    while offset<=size:\n        block=os.pread(fd,65536,offset)","    while offset<size-1:\n        block=os.pread(fd,65536,offset)")
# ---------------------------------------------------------------- what the plan says
add('D01_config_elsewhere_in_the_tree',"def config_container_path(plan):return CAPACITY_TARGET+'/config/'+plan['capacity']['config_name']","def config_container_path(plan):return CAPACITY_TARGET+'/'+plan['capacity']['config_name']")
add('D02_block_values_in_another_order',"    values=capacity_values(plan);return ['%s=%s'%(key,values[key]) for key in CAPACITY_KEYS[:count]]","    values=capacity_values(plan);return ['%s=%s'%(key,values[key]) for key in sorted(CAPACITY_KEYS[:count])]")
add('D03_block_with_spaces',"    values=capacity_values(plan);return ['%s=%s'%(key,values[key]) for key in CAPACITY_KEYS[:count]]","    values=capacity_values(plan);return ['%s = %s'%(key,values[key]) for key in CAPACITY_KEYS[:count]]")
add('D04_spec_owner_root',"'after':block_lines(plan,after),'owner':list(ENV_OWNER),'mode':ENV_MODE}","'after':block_lines(plan,after),'owner':[0,0],'mode':ENV_MODE}")
add('D05_spec_before_is_the_after',"    return {'before':[block_lines(plan,count) for count in before],","    return {'before':[block_lines(plan,mode['after'])],")
add('D06_editor_mount_read_only',"def editor_mounts(plan):return [{'source':plan['compose']['env_file'],'target':ENV_EDITOR_TARGET,'read_only':False}]","def editor_mounts(plan):return [{'source':plan['compose']['env_file'],'target':ENV_EDITOR_TARGET,'read_only':True}]")
add('D07_editor_mounts_the_deploy_tree',"def editor_mounts(plan):return [{'source':plan['compose']['env_file'],","def editor_mounts(plan):return [{'source':deploy_path(plan),")
add('D08_override_with_compact_separators',"    return json.dumps({'services':{WORKER_SERVICE:{'environment':dict(plan['override']['environment'])}}},sort_keys=True).encode('ascii')",
    "    return json.dumps({'services':{WORKER_SERVICE:{'environment':dict(plan['override']['environment'])}}},sort_keys=True,separators=(',',':')).encode('ascii')")
add('D09_file_list_without_the_override',"def file_list(plan):return plan['compose']['files']+[override_path(plan)]","def file_list(plan):return plan['compose']['files']")
add('D10_worker_container_two',"def worker_name(plan):return '%s-%s-1'%(plan['compose']['project'],WORKER_SERVICE)","def worker_name(plan):return '%s-%s-2'%(plan['compose']['project'],WORKER_SERVICE)")
add('D11_present_names_without_the_block',"def present_names(plan,count):return set(ACTIVATION_KEYS)|{BUILD_KEY}|set(CAPACITY_KEYS[:count])","def present_names(plan,count):return set(ACTIVATION_KEYS)|{BUILD_KEY}")
add('D12_present_names_without_the_activation',"def present_names(plan,count):return set(ACTIVATION_KEYS)|{BUILD_KEY}|set(CAPACITY_KEYS[:count])","def present_names(plan,count):return {BUILD_KEY}|set(CAPACITY_KEYS[:count])")
add('D13_placeholder_without_the_project',"def placeholder_name(plan):return plan['compose']['project']+'_'+PLACEHOLDER_VOLUME","def placeholder_name(plan):return PLACEHOLDER_VOLUME")
add('D14_capacity_tree_may_be_group_writable',"    tree=chain_path(capacity['root']);signed_chain(capacity['root'],None)","    tree=chain_path(capacity['root']);signed_chain(capacity['root'],tree)")
add('D15_override_chain_not_checked',"    signed_chain(override['directory'],root)\n","")
add('D16_lock_chain_not_checked',"    signed_chain(lock['directory'],deploy)\n","")
add('D17_deploy_chain_not_checked',"    deploy=chain_path(plan['deploy_directory']);signed_chain(plan['deploy_directory'],deploy)\n","    deploy=chain_path(plan['deploy_directory'])\n")
add('D18_editor_arguments_not_checked',"    run_arguments('edit_env',worker['image_id'],editor_mounts(plan),ENV_EDITOR_COMMAND)\n","")
add('D19_environment_grammar_not_checked',"    environment_format(expected_environment(plan,5))                         # every value fits the grammar of the template\n","")
add('D20_compose_arguments_not_checked',"    compose_arguments(compose['project'],compose['env_file'],file_list(plan))\n","")
# ---------------------------------------------------------------- effects_of: one per member
EFFECTS=[('F01_operation',"    return {'operation':OPERATION,'mode':plan['mode'],","    return {'operation':None,'mode':plan['mode'],"),
         ('F02_mode',"    return {'operation':OPERATION,'mode':plan['mode'],","    return {'operation':OPERATION,'mode':'MOUNT',"),
         ('F03_epoch',"'epoch':EPOCH_NAME,'revision':EPOCH_REVISION,\n            'environment_file'","'epoch':None,'revision':EPOCH_REVISION,\n            'environment_file'"),
         ('F04_revision',"'epoch':EPOCH_NAME,'revision':EPOCH_REVISION,\n            'environment_file'","'epoch':EPOCH_NAME,'revision':None,\n            'environment_file'"),
         ('F05_env_path',"'environment_file':{'path':compose['env_file'],'owner':list(ENV_OWNER)","'environment_file':{'path':None,'owner':list(ENV_OWNER)"),
         ('F06_env_owner',"'environment_file':{'path':compose['env_file'],'owner':list(ENV_OWNER)","'environment_file':{'path':compose['env_file'],'owner':[0,0]"),
         ('F07_env_mode',"'mode_octal':'%04o'%ENV_MODE,","'mode_octal':'0644',"),
         ('F08_block_before',"'trailing_capacity_block_before_one_of':[block_lines(plan,count) for count in mode['before']],","'trailing_capacity_block_before_one_of':[],"),
         ('F09_block_after',"'trailing_capacity_block_after':block_lines(plan,after),","'trailing_capacity_block_after':[],"),
         ('F10_editor_row',"'editor':{'row':'edit_env','argv_prefix':ENV_EDITOR_PREFIX,","'editor':{'row':None,'argv_prefix':ENV_EDITOR_PREFIX,"),
         ('F11_editor_prefix',"'editor':{'row':'edit_env','argv_prefix':ENV_EDITOR_PREFIX,","'editor':{'row':'edit_env','argv_prefix':RUN_PREFIX,"),
         ('F12_editor_image',"'image_id':plan['worker']['image_id'],'mounts':editor_mounts(plan),","'image_id':None,'mounts':editor_mounts(plan),"),
         ('F13_editor_mounts',"'image_id':plan['worker']['image_id'],'mounts':editor_mounts(plan),","'image_id':plan['worker']['image_id'],'mounts':[],"),
         ('F14_editor_command',"'command':ENV_EDITOR_COMMAND,'script_sha256':ENV_EDIT_SCRIPT_SHA256,'stdin_sha256'","'command':None,'script_sha256':ENV_EDIT_SCRIPT_SHA256,'stdin_sha256'"),
         ('F15_editor_script',"'command':ENV_EDITOR_COMMAND,'script_sha256':ENV_EDIT_SCRIPT_SHA256,'stdin_sha256'","'command':ENV_EDITOR_COMMAND,'script_sha256':None,'stdin_sha256'"),
         ('F16_editor_stdin_hash',"'stdin_sha256':sha(stdin),'stdin_bytes':len(stdin),","'stdin_sha256':None,'stdin_bytes':len(stdin),"),
         ('F17_editor_stdin_size',"'stdin_sha256':sha(stdin),'stdin_bytes':len(stdin),","'stdin_sha256':sha(stdin),'stdin_bytes':None,"),
         ('F56_editor_name',"                      'container_name':'hostops02-k6b-<first 16 hex of the GO hash>[-withdraw]'},","                      'container_name':None},"),
         ('F18_override_path',"'override':{'path':override_path(plan),'sha256':sha(overrides),","'override':{'path':None,'sha256':sha(overrides),"),
         ('F19_override_hash',"'override':{'path':override_path(plan),'sha256':sha(overrides),","'override':{'path':override_path(plan),'sha256':None,"),
         ('F20_override_size',"'bytes':len(overrides),'directory':chain_effects(plan['override']['directory']),","'bytes':None,'directory':chain_effects(plan['override']['directory']),"),
         ('F21_override_directory',"'bytes':len(overrides),'directory':chain_effects(plan['override']['directory']),","'bytes':len(overrides),'directory':None,"),
         ('F22_override_environment',"                        'environment':dict(plan['override']['environment']),'expect':'DELIVERED_BY_THE_ACTIVATION_READ_AND_COMPARED_NEVER_WRITTEN'}",
          "                        'environment':None,'expect':'DELIVERED_BY_THE_ACTIVATION_READ_AND_COMPARED_NEVER_WRITTEN'}"),
         ('F23_override_expect',"'expect':'DELIVERED_BY_THE_ACTIVATION_READ_AND_COMPARED_NEVER_WRITTEN'}","'expect':None}"),
         ('F24_tree_path',"'capacity_tree':{'host_path':capacity_root_path(plan),","'capacity_tree':{'host_path':None,"),
         ('F25_tree_root',"'root':chain_effects(plan['capacity']['root']),'container_target':CAPACITY_TARGET,","'root':None,'container_target':CAPACITY_TARGET,"),
         ('F26_tree_target',"'root':chain_effects(plan['capacity']['root']),'container_target':CAPACITY_TARGET,","'root':chain_effects(plan['capacity']['root']),'container_target':None,"),
         ('F27_tree_config',"'config_file':config_container_path(plan),'config_sha256':plan['capacity']['config_sha256'],","'config_file':None,'config_sha256':plan['capacity']['config_sha256'],"),
         ('F28_tree_config_hash',"'config_file':config_container_path(plan),'config_sha256':plan['capacity']['config_sha256'],","'config_file':config_container_path(plan),'config_sha256':None,"),
         ('F29_tree_read',"                             'read':plan['mode'] in ('MOUNT','ENABLE'),'expect':'READ_NEVER_WRITTEN'},","                             'read':True,'expect':'READ_NEVER_WRITTEN'},"),
         ('F30_tree_expect',"'expect':'READ_NEVER_WRITTEN'},","'expect':None},"),
         ('F31_recreate_project',"'recreate':{'project':compose['project'],'env_file':compose['env_file'],'files':file_list(plan),","'recreate':{'project':None,'env_file':compose['env_file'],'files':file_list(plan),"),
         ('F32_recreate_env_file',"'recreate':{'project':compose['project'],'env_file':compose['env_file'],'files':file_list(plan),","'recreate':{'project':compose['project'],'env_file':None,'files':file_list(plan),"),
         ('F33_recreate_files',"'recreate':{'project':compose['project'],'env_file':compose['env_file'],'files':file_list(plan),","'recreate':{'project':compose['project'],'env_file':compose['env_file'],'files':compose['files'],"),
         ('F34_recreate_service',"'service':WORKER_SERVICE,\n                        'container':worker_name(plan)","'service':None,\n                        'container':worker_name(plan)"),
         ('F35_recreate_container',"'service':WORKER_SERVICE,\n                        'container':worker_name(plan)","'service':WORKER_SERVICE,\n                        'container':None"),
         ('F36_recreate_image',"'image_id':plan['worker']['image_id'],'build_sha':EPOCH_REVISION,","'image_id':None,'build_sha':EPOCH_REVISION,"),
         ('F37_recreate_build',"'image_id':plan['worker']['image_id'],'build_sha':EPOCH_REVISION,","'image_id':plan['worker']['image_id'],'build_sha':None,"),
         ('F38_recreate_lock',"'lock':lock_path(plan),'lock_wait_seconds':plan['lock']['wait_seconds'],","'lock':None,'lock_wait_seconds':plan['lock']['wait_seconds'],"),
         ('F39_recreate_wait',"'lock':lock_path(plan),'lock_wait_seconds':plan['lock']['wait_seconds'],","'lock':lock_path(plan),'lock_wait_seconds':None,"),
         ('F40_recreate_lock_chain',"'lock_chain_sha256':sha(canonical(plan['lock']['directory'])),","'lock_chain_sha256':None,"),
         ('F41_recreate_deploy',"                        'deploy_directory':chain_effects(plan['deploy_directory'])},","                        'deploy_directory':None},"),
         ('F42_after_present',"'worker_after':{'environment_present':{key:values[key] for key in CAPACITY_KEYS[:after]},","'worker_after':{'environment_present':{},"),
         ('F43_after_absent',"'environment_absent':list(CAPACITY_KEYS[after:]),","'environment_absent':[],"),
         ('F44_after_activation',"                            'activation_environment':dict(plan['override']['environment']),","                            'activation_environment':None,"),
         ('F45_after_bind',"'capacity_mount':({'type':'bind','source':capacity_root_path(plan),'target':CAPACITY_TARGET,'read_only':True} if after","'capacity_mount':({'type':'bind','source':None,'target':CAPACITY_TARGET,'read_only':True} if after"),
         ('F46_after_placeholder',"else {'type':'volume','name':placeholder_name(plan),'target':CAPACITY_TARGET,'read_only':True}),","else {'type':'volume','name':None,'target':CAPACITY_TARGET,'read_only':True}),"),
         ('F47_after_data',"'data_mount':{'type':'bind','source':plan['data_root'],'target':DATA_TARGET}},","'data_mount':None},"),
         ('F48_required_marker',"'required':{'reboot_pending_marker_absent':REBOOT_PENDING_PATH,'deploy_version':EPOCH_REVISION,","'required':{'reboot_pending_marker_absent':None,'deploy_version':EPOCH_REVISION,"),
         ('F49_required_version',"'required':{'reboot_pending_marker_absent':REBOOT_PENDING_PATH,'deploy_version':EPOCH_REVISION,","'required':{'reboot_pending_marker_absent':REBOOT_PENDING_PATH,'deploy_version':None,"),
         ('F50_required_load',"                        'probe_load_receipt_sha256':plan['probe_load_receipt_sha256'],","                        'probe_load_receipt_sha256':None,"),
         ('F51_required_running',"                        'worker_running_before':plan['mode'] in ('MOUNT','ENABLE')},","                        'worker_running_before':True},"),
         ('F52_boot',"            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],\n            'pre_existing_objects_modified'","            'evidence_boot_id_sha256':None,\n            'pre_existing_objects_modified'"),
         ('F53_modified',"'pre_existing_objects_modified':'THE_ENVIRONMENT_FILE_IS_EDITED_IN_PLACE_AND_THE_WORKER_CONTAINER_IS_REPLACED','activation':False}","'pre_existing_objects_modified':None,'activation':False}"),
         ('F54_activation',"'pre_existing_objects_modified':'THE_ENVIRONMENT_FILE_IS_EDITED_IN_PLACE_AND_THE_WORKER_CONTAINER_IS_REPLACED','activation':False}","'pre_existing_objects_modified':'THE_ENVIRONMENT_FILE_IS_EDITED_IN_PLACE_AND_THE_WORKER_CONTAINER_IS_REPLACED','activation':None}"),
         ('F55_success_criterion',"def success_of(plan):return COMPLETE_OUTCOME","def success_of(plan):return PARTIAL_OUTCOME")]
for name,old,new in EFFECTS:add(name,old,new)
# ---------------------------------------------------------------- the edit in memory
add('E01_no_newline_rule',"    need(raw==b'' or raw.endswith(b'\\n'),'ENV_FILE_NOT_NEWLINE_TERMINATED')\n","")
add('E02_lines_without_the_last',"    return raw[:-1].split(b'\\n') if raw else []\n","    return raw[:-1].split(b'\\n')[:-1] if raw else []\n")
add('E04_identity_without_the_links',"    return (info.st_dev,info.st_ino,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)","    return (info.st_dev,info.st_ino,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),1)")
add('E05_identity_without_the_inode',"    return (info.st_dev,info.st_ino,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)","    return (info.st_dev,0,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)")
add('E06_identity_without_the_owner',"    return (info.st_dev,info.st_ino,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)","    return (info.st_dev,info.st_ino,1000,1000,stat.S_IMODE(info.st_mode),info.st_nlink)")
add('E07_withdrawal_restores_nothing',"            withdrawn_spec=edit_spec(plan,(after,),len(block))","            withdrawn_spec=edit_spec(plan,(after,),after)")
# ---------------------------------------------------------------- the reads of the host
add('H03_tree_not_read_for_mount',"    active=mode in ('MOUNT','ENABLE')","    active=mode=='ENABLE'")
add('H04_tree_read_for_every_mode',"    active=mode in ('MOUNT','ENABLE')","    active=True")
add('H05_mounts_any_source',"    if count:right=mount['Type']=='bind' and plain(mount.get('Source'))==capacity_root_path(plan) and mount['RW'] is False","    if count:right=mount['Type']=='bind' and mount['RW'] is False")
add('H06_mounts_bind_may_be_writable',"    if count:right=mount['Type']=='bind' and plain(mount.get('Source'))==capacity_root_path(plan) and mount['RW'] is False","    if count:right=mount['Type']=='bind' and plain(mount.get('Source'))==capacity_root_path(plan)")
add('H07_mounts_placeholder_any_name',"    else:right=mount['Type']=='volume' and mount.get('Name')==placeholder_name(plan) and mount['RW'] is False","    else:right=mount['Type']=='volume' and mount['RW'] is False")
add('H08_mounts_data_not_judged',"    return right and data[0]['Type']=='bind' and plain(data[0].get('Source'))==plan['data_root'] and data[0]['RW'] is True","    return right")
add('H09_mounts_two_capacity_mounts_accepted',"    if len(capacity)!=1 or len(data)!=1:return False","    if not capacity or not data:return False")
add('H10_environment_absent_not_judged',"    return all(item=={'present':True,'equal':True} if name in present else item['present'] is False for name,item in values.items())","    return all(item=={'present':True,'equal':True} for name,item in values.items() if name in present)")
add('H11_environment_presence_only',"    return all(item=={'present':True,'equal':True} if name in present else item['present'] is False for name,item in values.items())","    return all(item['present'] if name in present else item['present'] is False for name,item in values.items())")
add('H12_render_errors_ignore_other_services',"    if [name for name,_ in found]!=[WORKER_SERVICE]:return errors+['ONCE_ON_THE_WORKER_ONLY']","    if WORKER_SERVICE not in [name for name,_ in found]:return errors+['ONCE_ON_THE_WORKER_ONLY']")
add('H13_render_capacity_may_be_writable',"    if mount.get('read_only') is not True:errors.append('READ_ONLY')\n","")
add('H14_render_targets_not_judged',"    if sorted(map(str,targets))!=sorted(WORKER_TARGETS):errors.append('WORKER_TARGETS')\n","")
add('H15_render_project_not_judged',"    if rendered.get('name')!=plan['compose']['project']:errors.append('PROJECT')\n","")
add('H16_render_bind_any_source',"        if (mount.get('type'),mount.get('source'))!=('bind',capacity_root_path(plan)):errors.append('BIND')\n","        if mount.get('type')!='bind':errors.append('BIND')\n")
add('H17_render_placeholder_any_source',"        if (mount.get('type'),mount.get('source'))!=('volume',PLACEHOLDER_VOLUME):errors.append('PLACEHOLDER')\n","        if mount.get('type')!='volume':errors.append('PLACEHOLDER')\n")
add('H18_render_placeholder_name_not_judged',"        if not named:errors.append('PLACEHOLDER_NAME')\n","")
add('H19_render_capacity_check_skipped',"    need(not render_errors(rendered,plan,count),'RENDER_CAPACITY_MOUNT_NOT_AS_SIGNED')\n","")
add('H20_render_long_form_not_judged',"            if type(volume) is not dict:errors.append('LONG_FORM')\n","            if type(volume) is not dict:pass\n")
add('H21_editor_line_any_status',"        if set(line)=={'status','code'} and line['status'] in ENV_EDIT_STATUSES and (line['code'] is None or text(line['code'],CODE)):","        if set(line)=={'status','code'}:")
add('H22_editor_line_code_not_filtered',"        if set(line)=={'status','code'} and line['status'] in ENV_EDIT_STATUSES and (line['code'] is None or text(line['code'],CODE)):","        if set(line)=={'status','code'} and line['status'] in ENV_EDIT_STATUSES:")
add('H23_mounts_any_document',"    need(type(rows) is list and len(rows)<=MAX_MOUNTS_LISTED and all(type(row) is dict and type(row.get('Destination')) is str","    need(type(rows) is list and all(type(row) is dict and type(row.get('Destination')) is str")
# ---------------------------------------------------------------- settlement of the editor, the stop, the outcome
add('K01_edited_without_a_done_line_is_done',"    if found=='EDITED' and result['returncode']==0 and status=='ENV_EDIT_DONE':state.done()","    if found=='EDITED':state.done()")
add('K04_identity_not_compared_after_the_edit',"        raw,info=env_file_read(host,deploy,gate);same=identity_of(info)==identity","        raw,info=env_file_read(host,deploy,gate);same=True")
# V06 (the withdrawal after an editor that did not return) was removed with its operand (a returncode of 0 implies it returned).
# K05 (the early return for an editor that did not return) was removed from this list after the run of 2026-10-04 23:17Z:
# it is equivalent (effect() has already settled the call as unknown; settling it unknown again changes no count and no state).
add('K06_env_after_ignores_a_hanging_editor',"    if edit['started'] and not edit['returned']:return 'UNKNOWN'\n","")
add('K07_env_after_ignores_a_hanging_withdrawal',"    if withdraw['started'] and not withdraw['returned']:return 'UNKNOWN'          # the editor may still be running\n","")
add('K08_env_after_restored_is_edited',"    if withdraw['state']=='EDITED':return 'RESTORED'\n","")
add('K09_stop_when_edited_without_done',"        if edit['state']!='EDITED' or not result['returned'] or result['returncode']!=0 or edit['status']!='ENV_EDIT_DONE':","        if edit['state']!='EDITED':")
add('K11_withdrawn_outcome_is_env_only',"        elif withdraw['state']=='EDITED':outcome=WITHDRAWN_OUTCOME\n","")
add('K12_uncertain_file_is_env_only',"        elif run['state']=='UNCERTAIN' or env_file_after(edit,withdraw)=='UNKNOWN':outcome=UNCERTAIN_OUTCOME","        elif run['state']=='UNCERTAIN':outcome=UNCERTAIN_OUTCOME")
add('K15_lock_not_proved_after_the_edit',"                need(lock_still_named(host,LOCK_FILE_NAME,lock_directory,lock[0]),'LOCK_FILE_REPLACED')\n                need(service_of(","                need(service_of(")
add('K16_names_not_proved_before_the_recreate',"            try:\n                need(reached_by_name(project,gate),'DEPLOY_TREE_REPLACED')\n                need(reached_by_name(override_directory,gate),'OVERRIDE_DIRECTORY_REPLACED')\n                need(reached_by_name(lock_directory,gate),'LOCK_DIRECTORY_REPLACED')\n            except",
    "            try:\n                pass\n            except")
# ---------------------------------------------------------------- the precheck
add('P01_identity_after_the_umask',"            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n            host.umask(0o077)\n","            host.umask(0o077)\n            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n")
add('P02_worker_running_not_required',"                need(alive(before),'WORKER_NOT_RUNNING')\n","")
add('P03_worker_env_judged_against_the_block_after',"detail['precheck'].update(worker_running=alive(before),worker_environment_as_found=environment_as(values,plan,len(block)),","detail['precheck'].update(worker_running=alive(before),worker_environment_as_found=environment_as(values,plan,after),")
add('P04_worker_mounts_judged_against_the_block_after',"                                      worker_mounts_as_found=mounts_as(plan,mounts,len(block)))","                                      worker_mounts_as_found=mounts_as(plan,mounts,after))")
add('P06_disable_judges_the_whole_worker_under_the_lock',"            keys=('id','started_at','restarts') if active else ('id',)","            keys=('id','started_at','restarts')")
add('P07_mount_judges_only_the_id_under_the_lock',"            keys=('id','started_at','restarts') if active else ('id',)","            keys=('id',)")
add('P08_render_from_the_deploy_file_only',"signed=expected_environment(plan,5);compose=plan['compose'];container=worker_name(plan);listed=file_list(plan)","signed=expected_environment(plan,5);compose=plan['compose'];container=worker_name(plan);listed=plan['compose']['files']")
add('P09_env_compared_by_bytes_only_under_the_lock',"            need(again_raw==env_before and stat_signature(again_info)==stat_signature(env_info),'ENV_FILE_CHANGED_BEFORE_THE_LOCK')","            need(again_raw==env_before,'ENV_FILE_CHANGED_BEFORE_THE_LOCK')")
UNDER="            need(lock_still_named(host,LOCK_FILE_NAME,lock_directory,lock[0]),'LOCK_FILE_REPLACED')\n            pending=probe(host,REBOOT_PENDING_PATH,gate)\n"
add('P10_lock_not_proved_once_taken',UNDER,"            pending=probe(host,REBOOT_PENDING_PATH,gate)\n")
NAMES="            need(reached_by_name(override_directory,gate),'OVERRIDE_DIRECTORY_REPLACED')\n            need(reached_by_name(lock_directory,gate),'LOCK_DIRECTORY_REPLACED')\n            if tree is not None:"
add('P12_override_directory_not_proved_under_the_lock',NAMES,NAMES.replace("            need(reached_by_name(override_directory,gate),'OVERRIDE_DIRECTORY_REPLACED')\n",""))
add('P13_lock_directory_not_proved_under_the_lock',NAMES,NAMES.replace("            need(reached_by_name(lock_directory,gate),'LOCK_DIRECTORY_REPLACED')\n",""))
AFTER="                need(reached_by_name(project,gate),'DEPLOY_TREE_REPLACED')\n                need(reached_by_name(override_directory,gate),'OVERRIDE_DIRECTORY_REPLACED')\n                need(reached_by_name(lock_directory,gate),'LOCK_DIRECTORY_REPLACED')\n            except"
add('P14_project_not_proved_before_the_recreate',AFTER,AFTER.replace("                need(reached_by_name(project,gate),'DEPLOY_TREE_REPLACED')\n",""))
add('P15_override_directory_not_proved_before_the_recreate',AFTER,AFTER.replace("                need(reached_by_name(override_directory,gate),'OVERRIDE_DIRECTORY_REPLACED')\n",""))
add('P16_lock_directory_not_proved_before_the_recreate',AFTER,AFTER.replace("                need(reached_by_name(lock_directory,gate),'LOCK_DIRECTORY_REPLACED')\n",""))
# ---------------------------------------------------------------- after the review (2026-10-04)
add('R01_script_no_recheck_before_the_write',"            if (again.st_size,again.st_mtime_ns,again.st_ino)!=(info.st_size,info.st_mtime_ns,info.st_ino) or read_all(fd,info.st_size)!=raw:","            if False:")
add('R02_script_recheck_by_size_only',"            if (again.st_size,again.st_mtime_ns,again.st_ino)!=(info.st_size,info.st_mtime_ns,info.st_ino) or read_all(fd,info.st_size)!=raw:","            if again.st_size!=info.st_size:")
add('R03_override_metadata_not_judged',"    need(info.st_nlink==1 and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(0,0,0o600) and raw==override_bytes(plan),'OVERRIDE_NOT_AS_DELIVERED')","    need(raw==override_bytes(plan),'OVERRIDE_NOT_AS_DELIVERED')")
add('R04_override_compared_by_size',"    need(info.st_nlink==1 and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(0,0,0o600) and raw==override_bytes(plan),'OVERRIDE_NOT_AS_DELIVERED')","    need(info.st_nlink==1 and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(0,0,0o600) and len(raw)==len(override_bytes(plan)),'OVERRIDE_NOT_AS_DELIVERED')")
add('R05_config_hash_not_compared',"    need(sha(raw)==plan['capacity']['config_sha256'],'CAPACITY_CONFIG_HASH_MISMATCH')","    need(True,'CAPACITY_CONFIG_HASH_MISMATCH')")
add('R06_config_not_read_again_under_the_lock',"                capacity_tree(host,plan,tree,gate,pinned)                 # the static config again, under the lock\n","")
add('R07_image_not_resolved_again_under_the_lock',"            need(again_image['id']==resolved['id'],'RENDER_IMAGE_CHANGED_BEFORE_THE_LOCK')","            need(True,'RENDER_IMAGE_CHANGED_BEFORE_THE_LOCK')")
add('R08_editor_name_not_free_checked',"            need(not [row for row in listing if row['name'] in (editor_name(bound),editor_name(bound)+'-withdraw')],'EDITOR_NAME_TAKEN')\n","")
add('R09_tree_not_proved_before_the_editor',"            need(reached_by_name(project,gate),'DEPLOY_TREE_REPLACED')         # last, right before the editor binds .env by its path\n","")
add('R10_settle_without_the_path',"        if not reached_by_name(deploy,gate):raise Refused('DEPLOY_TREE_REPLACED')\n","")
add('R11_unchanged_is_a_failure_whatever_the_editor_said',"    elif found=='UNCHANGED' and status=='ENV_EDIT_REFUSED':state.fail()","    elif found=='UNCHANGED':state.fail()")
add('R12_env_after_unchanged_whatever_the_editor_said',"    if edit['state']=='NOT_STARTED' or (edit['state']=='UNCHANGED' and edit['status']=='ENV_EDIT_REFUSED'):return 'UNCHANGED'","    if edit['state'] in ('NOT_STARTED','UNCHANGED'):return 'UNCHANGED'")
add('R13_no_withdrawal_at_all',"            if held:\n                back=container_effect(","            if False:\n                back=container_effect(")
add('R18_withdrawal_without_the_lock',"            try:held=lock_still_named(host,LOCK_FILE_NAME,lock_directory,lock[0])\n            except Exception:held=False\n","            held=True\n")
add('R19_over_its_allowance_not_judged',"            if stop is None and (detail['budget']['render_after_the_edit_milliseconds'] is None or detail['budget']['render_after_the_edit_milliseconds']>allowance*1000):","            if False:")
add('R20_over_twice_its_allowance',"detail['budget']['render_after_the_edit_milliseconds']>allowance*1000):","detail['budget']['render_after_the_edit_milliseconds']>2*allowance*1000):")
add('R21_disables_refuse_like_the_others',"        if active:need(ok,code)\n        elif not ok:findings.append(code)","        need(ok,code)")
add('R22_disables_refuse_on_what_they_look_at',"            if active or str(error) in ('GO_EXPIRED','CLOCK_REVERSED'):raise\n            findings.append(code_of(error,'FINDING'));return None","            raise")
add('R23_mounts_refuse_nothing',"        if active:need(ok,code)\n        elif not ok:findings.append(code)","        if not ok:findings.append(code)")
add('R24_render_before_judged_against_the_block_after',"listed,EPOCH_REVISION),plan,len(block),","listed,EPOCH_REVISION),plan,after,")
add('R25_render_after_judged_as_before',"listed,EPOCH_REVISION),plan,after,\n","listed,EPOCH_REVISION),plan,len(block),\n")
add('R26_render_after_not_judged',"                                None if active else [])['image']==service['image'],'RENDER_IMAGE_CHANGED')","                                [])['image']==service['image'],'RENDER_IMAGE_CHANGED')")
add('R27_editor_left_not_said',"        if result['started'] and not result['returned']:edit['container_left']=still_listed(commands,editor_name(bound))\n","")
add('R28_still_listed_always_false',"    try:return name in [row['name'] for row in container_list(commands)]","    try:return False")
add('R29_editor_unnamed',"ENV_EDITOR_COMMAND,stdin,container_name=editor_name(bound))","ENV_EDITOR_COMMAND,stdin)")
# ---------------------------------------------------------------- rev 2 (Codex decisions 1 and 6, #429 5985748037)
add('V01_env_only_is_the_generic_partial',"ENV_ONLY_OUTCOME='PARTIAL_ENV_FILE_EDITED_RECREATE_NOT_STARTED'","ENV_ONLY_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'")
add('V02_withdrawn_is_the_generic_partial',"WITHDRAWN_OUTCOME='PARTIAL_ENV_EDIT_WITHDRAWN_RECREATE_NOT_STARTED'","WITHDRAWN_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'")
add('V03_recreate_failed_is_the_env_only_state',"RECREATE_FAILED_OUTCOME='PARTIAL_ENV_FILE_EDITED_RECREATE_FAILED_WORKER_UNCHANGED'","RECREATE_FAILED_OUTCOME='PARTIAL_ENV_FILE_EDITED_RECREATE_NOT_STARTED'")
add('V04_recreate_failed_outcome_never_chosen',"        elif run['state']=='NOT_RECREATED':outcome=RECREATE_FAILED_OUTCOME\n","")
add('V05_withdrawal_whatever_was_authorized',"        if (stop is not None and plan['withdrawal_authorized'] and edit['state']=='EDITED'","        if (stop is not None and edit['state']=='EDITED'")
add('V07_withdrawal_after_a_non_zero_editor',"and edit['state']=='EDITED' and edit['returncode']==0 and edit['status']=='ENV_EDIT_DONE'","and edit['state']=='EDITED' and edit['status']=='ENV_EDIT_DONE'")
add('V08_withdrawal_after_an_unconfirmed_edit',"edit['returncode']==0 and edit['status']=='ENV_EDIT_DONE'      # exit 0: it returned","edit['returncode']==0      # exit 0: it returned")
add('V09_withdrawal_after_a_recreate_that_ran',"                and not run['started']):","                and run['state'] in ('NOT_STARTED','NOT_RECREATED')):")
add('V10_withdrawal_request_unchecked',"    need(type(plan['withdrawal_authorized']) is bool,'WITHDRAWAL_REQUEST_INVALID')\n","")
add('V11_effects_withdrawal_always_authorized',"            'withdrawal':{'authorized':plan['withdrawal_authorized'],","            'withdrawal':{'authorized':True,")
add('V12_effects_withdrawal_hashes_even_unauthorized',"                                                         if plan['withdrawal_authorized'] else {}),","                                                         if True else {}),")
add('V13_effects_withdrawal_hashes_dropped',"                          'stdin_sha256_by_block_found':({str(count):sha(editor_stdin(edit_spec(plan,(after,),count))) for count in mode['before']}","                          'stdin_sha256_by_block_found':({}")
add('V14_effects_rule_4_claimed',"            'core_exception':{'rule_4_preserved':False,","            'core_exception':{'rule_4_preserved':True,")
add('V15_effects_chain_said_root_controlled',"                                 'all_root_controlled':all(row['uid']==0 for row in plan['deploy_directory']) and ENV_OWNER[0]==0,","                                 'all_root_controlled':True,")
add('V16_effects_chain_without_the_file',"                                        [{'path':compose['env_file'],'uid':ENV_OWNER[0],'gid':ENV_OWNER[1],'mode':ENV_MODE}],","                                        [],")
add('V17_receipt_chain_said_root_controlled',"            detail['precheck']['bind_source_root_controlled']=bool(all(row.get('uid')==0 for row in detail['chains']['DEPLOY_DIRECTORY']) and identity[2]==0)","            detail['precheck']['bind_source_root_controlled']=True")
add('V18_failure_phase_always_before_the_recreate',"failure_phase=None if code is None else ('AFTER_THE_RECREATE_STARTED' if run['started'] else","failure_phase=None if code is None else ('BEFORE_THE_RECREATE' if run['started'] else")
add('V19_failure_phase_before_the_edit_unknown',"                                                     'BEFORE_THE_RECREATE' if edit['started'] else 'BEFORE_THE_EDIT'),**extra))","                                                     'BEFORE_THE_RECREATE'),**extra))")
# ---------------------------------------------------------------- rev 2: the processes made non-dumpable (A2 amendment 1 rev 3, #429 5986005646)
add('W01_editor_never_made_non_dumpable',"        if not not_dumpable():raise Stop('EDITOR_DUMPABLE_NOT_DISABLED')\n","")
add('W02_editor_dumpable_after_the_open',"        if not not_dumpable():raise Stop('EDITOR_DUMPABLE_NOT_DISABLED')\n        try:fd=os.open(TARGET,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)\n        except OSError:raise Stop('ENV_FILE_OPEN')\n",
    "        try:fd=os.open(TARGET,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)\n        except OSError:raise Stop('ENV_FILE_OPEN')\n        if not not_dumpable():raise Stop('EDITOR_DUMPABLE_NOT_DISABLED')\n")
add('W03_editor_set_not_read_back',"        return library.prctl(4,0,0,0,0)==0 and library.prctl(3,0,0,0,0)==0","        return library.prctl(4,0,0,0,0)==0")
add('W04_editor_any_prctl_answer',"        return library.prctl(4,0,0,0,0)==0 and library.prctl(3,0,0,0,0)==0","        library.prctl(4,0,0,0,0);return True")
add('W05_editor_prctl_failure_tolerated',"    except Exception:return False\ndef say(","    except Exception:return True\ndef say(")
add('W06_source_never_made_non_dumpable',"            need(host.not_dumpable() is True,'PROCESS_DUMPABLE_NOT_DISABLED');detail['process']['dumpable_disabled']=True\n","            detail['process']['dumpable_disabled']=True\n")
add('W07_source_dumpable_after_the_identity',"            need(host.not_dumpable() is True,'PROCESS_DUMPABLE_NOT_DISABLED');detail['process']['dumpable_disabled']=True\n            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n            host.umask(0o077)\n            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')\n            deploy=chain(",
    "            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n            host.umask(0o077)\n            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')\n            need(host.not_dumpable() is True,'PROCESS_DUMPABLE_NOT_DISABLED');detail['process']['dumpable_disabled']=True\n            deploy=chain(")
add('W08_receipt_says_disabled_whatever',"            detail['process']['dumpable_disabled']=False\n","            detail['process']['dumpable_disabled']=True\n")
# ---------------------------------------------------------------- the budget
add('C01_no_pause',"SETTLE_SECONDS=3                          # the one fixed pause","SETTLE_SECONDS=0                          # the one fixed pause")
add('C02_no_reserve_for_the_second_reading',"SECOND_CHECK_RESERVE_SECONDS=2\n","SECOND_CHECK_RESERVE_SECONDS=0\n")
add('C03_no_files_allowance',"FILES_ALLOWANCE_SECONDS=1                 # the readbacks","FILES_ALLOWANCE_SECONDS=0                 # the readbacks")
add('C04_no_under_lock_allowance',"UNDER_LOCK_ALLOWANCE_SECONDS=2\n","UNDER_LOCK_ALLOWANCE_SECONDS=0\n")
add('C05_no_render_floor',"RENDER_ALLOWANCE_FLOOR_SECONDS=3\n","RENDER_ALLOWANCE_FLOOR_SECONDS=0\n")
ALLOWANCE="            allowance=min(COMMAND_CLASSES['RENDER']['seconds'],max(RENDER_ALLOWANCE_FLOOR_SECONDS,int(2*measured)+1))\n"
add('C06_allowance_once_the_render',ALLOWANCE,ALLOWANCE.replace("int(2*measured)+1","int(measured)+1"))
add('C08_allowance_is_the_floor',ALLOWANCE,ALLOWANCE.replace("max(RENDER_ALLOWANCE_FLOOR_SECONDS,int(2*measured)+1)","RENDER_ALLOWANCE_FLOOR_SECONDS"))
NEEDED="            needed=effects_budget('edit_env','recreate')+allowance+FILES_ALLOWANCE_SECONDS+SETTLE_SECONDS\n"
add('C09_needed_without_the_editor',NEEDED,NEEDED.replace("effects_budget('edit_env','recreate')","effects_budget('recreate')"))
add('C10_needed_without_the_render',NEEDED,NEEDED.replace("+allowance",""))
add('C11_needed_without_the_pause',NEEDED,NEEDED.replace("+SETTLE_SECONDS",""))
add('C12_lock_keeps_only_what_is_needed',"acquire_lock(host,lock[0],gate,plan['lock']['wait_seconds'],needed+UNDER_LOCK_ALLOWANCE_SECONDS)","acquire_lock(host,lock[0],gate,plan['lock']['wait_seconds'],needed)")
add('C13_lock_waits_twenty_seconds',"acquire_lock(host,lock[0],gate,plan['lock']['wait_seconds'],needed+UNDER_LOCK_ALLOWANCE_SECONDS)","acquire_lock(host,lock[0],gate,20,needed+UNDER_LOCK_ALLOWANCE_SECONDS)")
add('C14_pause_without_its_reserve',"        if 'first' in seen and gate()>=SETTLE_SECONDS+SECOND_CHECK_RESERVE_SECONDS:","        if 'first' in seen:")
MEASURE="            measured=monotonic()-began\n"
add('C15_render_not_timed',MEASURE,"            measured=0\n")

MUTANTS=M
COMBOS={}
REDUNDANT={}
