"""The mutants of K6a (activate). Each row: (name, target, exact anchor, replacement); the anchor must occur exactly
once in the file the target is applied to (mutate.py check). Three origins, recorded per mutant in ORIGIN:

  GENERATED  one mutant per condition of every need(...) of the operation's own part: each operand of a conjunction
             dropped in turn, a single condition replaced by True. They are literal replacements like every other row;
             they are computed from op.py by its syntax tree so that no refusal of validate_plan, of the policy checks
             or of the precheck can be added without its mutants (the rule of the family: one per refusal).
  OWN        written by hand: one per member of effects_of() (the rule of the family), each constant the operation
             adds, each row of its command table, each criterion read after the recreate, each settlement of the
             recreate call, each outcome, the order of the precheck, the budget.
  INHERITED  the rows of the frozen core's own list whose target this operation carries or generates (the shared
             parts as they stand in build/activate.py, the dispatcher, the launcher) and whose anchor occurs exactly
             once there. Their kill by the CORE's suite is the core's record; here they are run against THIS
             operation's suite, to show which guarantees of the core this operation's own tests also hold.
             A survivor of this origin is not a survivor of this list (mutate.py reports them apart): it is listed in
             INHERITED_NOT_EXERCISED with the reason, or it is a finding.
"""
import ast
import importlib.util
import os
from pathlib import Path

HERE=Path(__file__).resolve().parent
OPERATION=HERE.parent
FROZEN=Path(os.environ.get('HOSTOPS02_CORE_DIRECTORY') or OPERATION.parent/'core').resolve()
OP=(OPERATION/'op.py').read_text(encoding='ascii')
BUILT=(OPERATION/'build'/'activate.py').read_text(encoding='ascii')
M=[];ORIGIN={}
def add(name,old,new,origin='OWN',target='op'):
    M.append((name,target,old,new));ORIGIN[name]=origin

# ---------------------------------------------------------------- GENERATED: every condition of every need()
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
for name,old,new in generated():
    # a need() whose text occurs twice (the same check made before and under the lock) is mutated at each place by hand below
    if OP.count(old)==1:add(name,old,new,'GENERATED')

# ---------------------------------------------------------------- OWN: identity, dates, flags
add('A01_date_class_is_every_session_day',"DATE_CLASS='WRITE_FIRST_SESSION'","DATE_CLASS='WRITE_SESSIONS'")
add('A02_date_class_is_the_weekend',"DATE_CLASS='WRITE_FIRST_SESSION'","DATE_CLASS='WRITE_WEEKEND'")
add('A03_evidence_not_required',"EVIDENCE_REQUIRED=True","EVIDENCE_REQUIRED=False")
add('A04_gate_may_span_an_hour',"MAX_GATE_SPAN_SECONDS=900","MAX_GATE_SPAN_SECONDS=3600")
add('A05_success_outcome_renamed',"COMPLETE_OUTCOME='ACTIVATE_WORKER_RECREATED_AND_VERIFIED'","COMPLETE_OUTCOME='ACTIVATE_DONE'")
add('A06_objects_only_outcome_is_the_generic_one',"OBJECTS_ONLY_OUTCOME='PARTIAL_OBJECTS_LEFT_WORKER_NOT_RECREATED'","OBJECTS_ONLY_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'")
add('A07_not_verified_outcome_is_the_generic_one',"NOT_VERIFIED_OUTCOME='PARTIAL_WORKER_RECREATED_NOT_FULLY_VERIFIED'","NOT_VERIFIED_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'")
add('A08_uncertain_outcome_is_the_generic_one',"UNCERTAIN_OUTCOME='PARTIAL_RECREATE_UNCERTAIN_REQUIRES_READBACK'","UNCERTAIN_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'")
add('A09_refused_outcome_renamed',"REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'","REFUSED_OUTCOME='REFUSED'")
# the epoch
add('B01_another_epoch',"EPOCH_NAME='R2D2-V2-SHADOW-2026-10-05'","EPOCH_NAME='R2D2-V2-SHADOW-2026-09-28'")
add('B02_another_revision',"EPOCH_REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'","EPOCH_REVISION='4de7095ad51bce19ea4b685d5c708d0a72986d76'")
add('B03_another_package',"EPOCH_PACKAGE_SHA256='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'","EPOCH_PACKAGE_SHA256='a9305a1196c1a37c12a6c8cb7525c89dc3a445225efed1cc10b7f11f5d831e1a'")
add('B04_another_runtime_order',"RUNTIME_ORDER_SHA256='1ad8b90cfab651823eb677b830a0078d10c17447575c8d813c3883a718579d8e'","RUNTIME_ORDER_SHA256='1a5253bf23f5006224b79527da06697646c34c6f5a3a4f820af5da2b13d7a118'")
add('B05_first_open_one_second_later',"EPOCH_FIRST_OPEN='2026-10-05T13:30:00+00:00'","EPOCH_FIRST_OPEN='2026-10-05T13:30:01+00:00'")
add('B06_last_close_one_second_earlier',"EPOCH_LAST_CLOSE='2026-10-09T20:00:00+00:00'","EPOCH_LAST_CLOSE='2026-10-09T19:59:59+00:00'")
add('B07_policy_schema_renamed',"LIVE_POLICY_SCHEMA='R2D2_V2_LIVE_POLICY_V1'","LIVE_POLICY_SCHEMA='R2D2_V2_LIVE_POLICY_V2'")
add('B08_policy_window_one_second_longer',"MAX_POLICY_WINDOW_SECONDS=90*86400","MAX_POLICY_WINDOW_SECONDS=90*86400+1")
add('B09_policy_size_limit_doubled',"MAX_POLICY_BYTES=16384","MAX_POLICY_BYTES=32768")
add('B10_release_size_limit_one_byte_more',"MAX_RELEASE_BYTES=65536   ","MAX_RELEASE_BYTES=65537   ")
add('B11_environment_file_limit_smaller',"MAX_ENV_FILE_BYTES=1048576","MAX_ENV_FILE_BYTES=16")
add('B12_environment_file_limit_larger',"MAX_ENV_FILE_BYTES=1048576","MAX_ENV_FILE_BYTES=2097152")
add('B13_another_service',"WORKER_SERVICE='r2d2-worker'","WORKER_SERVICE='api'")
add('B14_build_name_renamed',"BUILD_KEY='C3PO_BUILD_SHA'","BUILD_KEY='C3PO_BUILD'")
add('B15_policy_file_name_renamed',"KEY_POLICY_FILE='C3PO_R2D2_V2_LIVE_POLICY_FILE'","KEY_POLICY_FILE='C3PO_R2D2_V2_LIVE_POLICY_PATH'")
add('B16_policy_sha_name_renamed',"KEY_POLICY_SHA='C3PO_R2D2_V2_LIVE_POLICY_SHA'","KEY_POLICY_SHA='C3PO_R2D2_V2_LIVE_POLICY_SHA256'")
add('B17_release_file_name_renamed',"KEY_RELEASE_FILE='C3PO_R2D2_V2_SHADOW_RELEASE_FILE'","KEY_RELEASE_FILE='C3PO_R2D2_V2_RELEASE_FILE'")
add('B18_release_sha_name_renamed',"KEY_RELEASE_SHA='C3PO_R2D2_V2_SHADOW_RELEASE_SHA'","KEY_RELEASE_SHA='C3PO_R2D2_V2_RELEASE_SHA'")
add('B19_only_three_names_must_be_absent_before',"ACTIVATION_KEYS=(KEY_POLICY_FILE,KEY_POLICY_SHA,KEY_RELEASE_FILE,KEY_RELEASE_SHA)","ACTIVATION_KEYS=(KEY_POLICY_FILE,KEY_POLICY_SHA,KEY_RELEASE_FILE)")
add('B20_environment_file_renamed',"ENV_FILE_NAME='.env'","ENV_FILE_NAME='env'")
add('B21_compose_file_renamed',"COMPOSE_FILE_NAME='compose.yml'","COMPOSE_FILE_NAME='docker-compose.yml'")
add('B22_deploy_version_renamed',"DEPLOY_VERSION_NAME='.deploy-version'","DEPLOY_VERSION_NAME='.deploy-revision'")
add('B23_lock_directory_elsewhere',"LOCK_RELATIVE_DIRECTORY='runtime/security'","LOCK_RELATIVE_DIRECTORY='runtime'")
add('B24_lock_file_renamed',"LOCK_FILE_NAME='deployment.lock'","LOCK_FILE_NAME='deploy.lock'")
add('B25_reboot_marker_elsewhere',"REBOOT_PENDING_PATH='/run/c3po-security/reboot.pending'","REBOOT_PENDING_PATH='/run/c3po-security/reboot.requested'")
add('B26_pin_renamed',"PIN_NAME='.r2d2-v2-pinned'  ","PIN_NAME='.r2d2-v2-pin'  ")
add('B27_status_suffix_renamed',"STATUS_SUFFIX='.status.json'  ","STATUS_SUFFIX='.status'  ")
# the budget
add('C01_no_pause_between_the_two_readings',"SETTLE_SECONDS=3   ","SETTLE_SECONDS=0   ")
add('C02_pause_of_one_second',"SETTLE_SECONDS=3   ","SETTLE_SECONDS=1   ")
add('C03_pause_taken_with_nothing_left_for_the_second_reading',"SECOND_CHECK_RESERVE_SECONDS=2   ","SECOND_CHECK_RESERVE_SECONDS=0   ")
add('C04_no_allowance_for_the_files',"FILES_ALLOWANCE_SECONDS=1   ","FILES_ALLOWANCE_SECONDS=0   ")
add('C05_no_allowance_for_the_reads_under_the_lock',"UNDER_LOCK_ALLOWANCE_SECONDS=2   ","UNDER_LOCK_ALLOWANCE_SECONDS=0   ")
add('C06_render_allowance_floor_removed',"RENDER_ALLOWANCE_FLOOR_SECONDS=3   ","RENDER_ALLOWANCE_FLOOR_SECONDS=0   ")
ALLOWANCE="            allowance=min(COMMAND_CLASSES['RENDER']['seconds'],max(RENDER_ALLOWANCE_FLOOR_SECONDS,int(2*measured)+1))\n"
add('C07_render_allowance_is_once_what_the_first_took',ALLOWANCE,ALLOWANCE.replace("int(2*measured)+1","int(measured)+1"))
add('C08_render_allowance_not_capped_by_the_class',ALLOWANCE,ALLOWANCE.replace("min(COMMAND_CLASSES['RENDER']['seconds'],max(RENDER_ALLOWANCE_FLOOR_SECONDS,int(2*measured)+1))","max(RENDER_ALLOWANCE_FLOOR_SECONDS,int(2*measured)+1)"))
add('C09_render_allowance_is_the_floor_whatever_was_measured',ALLOWANCE,ALLOWANCE.replace("max(RENDER_ALLOWANCE_FLOOR_SECONDS,int(2*measured)+1)","RENDER_ALLOWANCE_FLOOR_SECONDS"))
NEEDED="            needed=effects_budget('recreate')+allowance+FILES_ALLOWANCE_SECONDS+SETTLE_SECONDS\n"
add('C10_budget_leaves_the_render_out',NEEDED,NEEDED.replace("+allowance",""))
add('C11_budget_leaves_the_pause_out',NEEDED,NEEDED.replace("+SETTLE_SECONDS",""))
add('C12_budget_leaves_the_recreate_out',NEEDED,NEEDED.replace("effects_budget('recreate')+",""))
LOCKED="            detail['precheck']['lock_attempts']=acquire_lock(host,lock[0],gate,plan['lock']['wait_seconds'],needed+UNDER_LOCK_ALLOWANCE_SECONDS)\n"
add('C13_lock_waited_for_without_keeping_anything',LOCKED,LOCKED.replace("needed+UNDER_LOCK_ALLOWANCE_SECONDS","0"))
add('C14_lock_waited_for_the_maximum_whatever_was_signed',LOCKED,LOCKED.replace("plan['lock']['wait_seconds']","MAX_LOCK_WAIT_SECONDS"))
add('C15_lock_not_waited_for',LOCKED,LOCKED.replace("plan['lock']['wait_seconds']","0"))
add('C16_lock_not_taken',LOCKED,"            detail['precheck']['lock_attempts']=0\n")
MEASURE="            measured=monotonic()-began\n"
add('C17_first_render_not_timed',MEASURE,"            measured=0\n")
PAUSE="        if 'first' in seen and gate()>=SETTLE_SECONDS+SECOND_CHECK_RESERVE_SECONDS:\n            host.pause(SETTLE_SECONDS);facts['settle_pause_taken']=True\n"
add('C18_pause_claimed_without_pausing',PAUSE,PAUSE.replace("host.pause(SETTLE_SECONDS);",""))
add('C19_pause_taken_whatever_is_left',PAUSE,PAUSE.replace(" and gate()>=SETTLE_SECONDS+SECOND_CHECK_RESERVE_SECONDS",""))
add('C20_pause_never_taken',PAUSE,PAUSE.replace("gate()>=SETTLE_SECONDS+SECOND_CHECK_RESERVE_SECONDS","False"))
# the command table
RENDER="'render':command_row('docker',['compose'],'--project-name, --env-file, the compose file of the deploy, then the override on standard input as the last file','RENDER','READ',tail=COMPOSE_CONFIG_TAIL,stdin=True)"
add('D01_render_in_the_quick_class',RENDER,RENDER.replace("'RENDER','READ'","'QUICK','READ'"))
FILES_ROW="'render_files':command_row('docker',['compose'],'--project-name, --env-file, the compose file of the deploy and the delivered override file','RENDER','READ',tail=COMPOSE_CONFIG_TAIL)"
add('D02_render_from_files_in_the_quick_class',FILES_ROW,FILES_ROW.replace("'RENDER','READ'","'QUICK','READ'"))
UP="'recreate':command_row('docker',['compose'],'--project-name, --env-file, the compose file of the deploy and the delivered override file','RECREATE','EFFECT',tail=compose_up_tail(WORKER_SERVICE))"
add('D03_recreate_in_the_forty_second_class',UP,UP.replace("'RECREATE','EFFECT'","'RUN','EFFECT'"))
add('D04_recreate_of_another_service',UP,UP.replace("compose_up_tail(WORKER_SERVICE)","compose_up_tail('api')"))
add('D05_recreate_of_every_service',UP,UP.replace("tail=compose_up_tail(WORKER_SERVICE)","tail=compose_up_tail(WORKER_SERVICE)[:-1]"))
add('D06_recreate_may_pull',UP,UP.replace("tail=compose_up_tail(WORKER_SERVICE)","tail=[word for word in compose_up_tail(WORKER_SERVICE) if word not in ('--pull','never')]"))
add('D07_recreate_with_dependencies',UP,UP.replace("tail=compose_up_tail(WORKER_SERVICE)","tail=[word for word in compose_up_tail(WORKER_SERVICE) if word!='--no-deps']"))
add('D08_recreate_not_forced',UP,UP.replace("tail=compose_up_tail(WORKER_SERVICE)","tail=[word for word in compose_up_tail(WORKER_SERVICE) if word!='--force-recreate']"))
add('D09_docker_from_a_user_writable_place',"BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}","BINARIES={'docker':['/opt/chief-of-staff-digital/docker','/usr/bin/docker','/usr/local/bin/docker']}")

# ---------------------------------------------------------------- OWN: what the plan says
add('E01_container_path_is_the_host_path',"    return plan['worker']['mount_target']+path[len(plan['data_root']):]\n","    return path\n")
add('E02_container_path_keeps_the_data_root',"    return plan['worker']['mount_target']+path[len(plan['data_root']):]\n","    return plan['worker']['mount_target']+path\n")
ENVIRONMENT="""    return {KEY_POLICY_FILE:container_path(plan,policy_path(plan)),KEY_POLICY_SHA:plan['policy']['sha256'],
            KEY_RELEASE_FILE:container_path(plan,release_path(plan)),KEY_RELEASE_SHA:plan['release']['sha256']}
"""
add('E03_policy_file_value_is_the_release',ENVIRONMENT,ENVIRONMENT.replace("container_path(plan,policy_path(plan))","container_path(plan,release_path(plan))"))
add('E04_policy_sha_value_is_the_release_sha',ENVIRONMENT,ENVIRONMENT.replace("KEY_POLICY_SHA:plan['policy']['sha256']","KEY_POLICY_SHA:plan['release']['sha256']"))
add('E05_release_file_value_is_the_policy',ENVIRONMENT,ENVIRONMENT.replace("container_path(plan,release_path(plan))","container_path(plan,policy_path(plan))"))
add('E06_release_sha_value_is_the_policy_sha',ENVIRONMENT,ENVIRONMENT.replace("KEY_RELEASE_SHA:plan['release']['sha256']","KEY_RELEASE_SHA:plan['policy']['sha256']"))
add('E07_release_file_value_is_the_directory',ENVIRONMENT,ENVIRONMENT.replace("container_path(plan,release_path(plan))","container_path(plan,release_directory_path(plan))"))
OVERRIDE="    return json.dumps({'services':{WORKER_SERVICE:{'environment':environment_of(plan)}}},sort_keys=True).encode('ascii')\n"
add('E08_override_in_compact_json',OVERRIDE,OVERRIDE.replace("sort_keys=True)","sort_keys=True,separators=(',',':'))"))
add('E09_override_sets_another_service',OVERRIDE,OVERRIDE.replace("{WORKER_SERVICE:","{'r2d2-shadow-candidate-worker':"))
add('E10_override_also_sets_the_command',OVERRIDE,OVERRIDE.replace("{'environment':environment_of(plan)}","{'environment':environment_of(plan),'command':['sleep','1']}"))
add('E11_override_keys_not_sorted',OVERRIDE,OVERRIDE.replace("sort_keys=True","sort_keys=False").replace("environment_of(plan)","dict(reversed(sorted(environment_of(plan).items())))"))
add('E12_worker_container_number_two',"def worker_name(plan):return '%s-%s-1'%(plan['compose']['project'],WORKER_SERVICE)","def worker_name(plan):return '%s-%s-2'%(plan['compose']['project'],WORKER_SERVICE)")
add('E13_pin_in_the_live_parent',"def pin_path(plan):return plan['data_root']+'/'+PIN_NAME","def pin_path(plan):return plan['live_parent'][-1]['path']+'/'+PIN_NAME")
add('E14_live_parent_may_be_setgid',"    signed_chain(plan['live_parent'],root,receives_entry=True)\n","    signed_chain(plan['live_parent'],root)\n")
add('E15_live_parent_judged_without_the_open_root',"    signed_chain(plan['live_parent'],root,receives_entry=True)\n","    signed_chain(plan['live_parent'],None,receives_entry=True)\n")
add('E16_release_parent_chain_not_validated',"    signed_chain(release['parent'],root)\n","    chain_path(release['parent'])\n")
add('E17_deploy_chain_not_validated',"    deploy=chain_path(plan['deploy_directory']);signed_chain(plan['deploy_directory'],deploy)","    deploy=chain_path(plan['deploy_directory'])")
add('E18_lock_chain_not_validated',"    signed_chain(lock['directory'],deploy)\n","    chain_path(lock['directory'])\n")
add('E19_policy_content_not_validated',"    raw,policy=policy_of(plan);validate_policy(policy,plan)\n","    raw,policy=policy_of(plan)\n")
add('E20_policy_bytes_not_decoded_at_validation',"    raw,policy=policy_of(plan);validate_policy(policy,plan)\n","    pass\n")
add('E21_compose_arguments_without_the_override_not_validated',"    compose_arguments(compose['project'],compose['env_file'],compose['files'])                       # the signed list alone, then with the override\n","")
add('E22_compose_arguments_with_the_override_not_validated',"    compose_arguments(compose['project'],compose['env_file'],compose['files']+[override_path(plan)])\n","")
add('E23_values_not_checked_against_the_template_grammar',"    environment_format(dict(environment_of(plan),**{BUILD_KEY:EPOCH_REVISION}))","    pass")
add('E24_policy_window_error_keeps_the_core_code',"    try:return instant(value)\n    except Refused:raise Refused('POLICY_WINDOW') from None\n","    return instant(value)\n")
add('E25_policy_json_error_keeps_the_core_code',"    try:policy=strict(raw)\n    except Refused:raise Refused('POLICY_JSON_INVALID') from None\n","    policy=strict(raw)\n")
add('E26_policy_base64_not_validated',"base64.b64decode(item['content_b64'].encode('ascii'),validate=True)","base64.b64decode(item['content_b64'].encode('ascii'))")
# one per member of effects_of()
EFFECTS=[('F01_operation',"return {'operation':OPERATION,'epoch':EPOCH_NAME,","return {'operation':None,'epoch':EPOCH_NAME,"),
    ('F02_epoch',"return {'operation':OPERATION,'epoch':EPOCH_NAME,","return {'operation':OPERATION,'epoch':None,"),
    ('F03_revision',"'revision':EPOCH_REVISION,'data_root':plan['data_root'],","'revision':None,'data_root':plan['data_root'],"),
    ('F04_data_root',"'revision':EPOCH_REVISION,'data_root':plan['data_root'],","'revision':EPOCH_REVISION,'data_root':None,"),
    ('F05_live_parent',"            'live_parent':chain_effects(plan['live_parent']),\n","            'live_parent':plan['live_parent'][-1]['path'],\n"),
    ('F06_directory_path',"'directory':{'path':live_path(plan),","'directory':{'path':plan['directory_name'],"),
    ('F07_directory_mode',"'directory':{'path':live_path(plan),'mode_octal':'%04o'%PRIVATE_DIRECTORY_MODE,","'directory':{'path':live_path(plan),'mode_octal':None,"),
    ('F08_directory_expectation',"'mode_octal':'%04o'%PRIVATE_DIRECTORY_MODE,'expect':'ABSENT'},","'mode_octal':'%04o'%PRIVATE_DIRECTORY_MODE,'expect':None},"),
    ('F09_policy_file_path',"{'key':'POLICY','path':policy_path(plan),","{'key':'POLICY','path':plan['policy']['name'],"),
    ('F10_policy_file_hash',"'sha256':plan['policy']['sha256'],'bytes':plan['policy']['bytes'],'mode_octal':'%04o'%PRIVATE_FILE_MODE},","'sha256':None,'bytes':plan['policy']['bytes'],'mode_octal':'%04o'%PRIVATE_FILE_MODE},"),
    ('F11_policy_file_size',"'sha256':plan['policy']['sha256'],'bytes':plan['policy']['bytes'],'mode_octal':'%04o'%PRIVATE_FILE_MODE},","'sha256':plan['policy']['sha256'],'bytes':None,'mode_octal':'%04o'%PRIVATE_FILE_MODE},"),
    ('F12_policy_file_mode',"'sha256':plan['policy']['sha256'],'bytes':plan['policy']['bytes'],'mode_octal':'%04o'%PRIVATE_FILE_MODE},","'sha256':plan['policy']['sha256'],'bytes':plan['policy']['bytes'],'mode_octal':None},"),
    ('F13_override_file_path',"{'key':'OVERRIDE','path':override_path(plan),","{'key':'OVERRIDE','path':plan['override_name'],"),
    ('F14_override_file_hash',"'sha256':sha(override),'bytes':len(override),'mode_octal':'%04o'%PRIVATE_FILE_MODE}],","'sha256':None,'bytes':len(override),'mode_octal':'%04o'%PRIVATE_FILE_MODE}],"),
    ('F15_override_file_size',"'sha256':sha(override),'bytes':len(override),'mode_octal':'%04o'%PRIVATE_FILE_MODE}],","'sha256':sha(override),'bytes':None,'mode_octal':'%04o'%PRIVATE_FILE_MODE}],"),
    ('F16_override_file_mode',"'sha256':sha(override),'bytes':len(override),'mode_octal':'%04o'%PRIVATE_FILE_MODE}],","'sha256':sha(override),'bytes':len(override),'mode_octal':None}],"),
    ('F17_policy_content_digest',"'policy':{'content_digest_sha256':policy_digest(policy),","'policy':{'content_digest_sha256':plan['policy']['sha256'],"),
    ('F48_policy_digest_of_the_family_canonical_form',"'policy':{'content_digest_sha256':policy_digest(policy),","'policy':{'content_digest_sha256':sha(canonical(policy)),"),
    ('F18_policy_valid_from',"'valid_from':policy.get('valid_from'),'valid_until':policy.get('valid_until'),","'valid_from':None,'valid_until':policy.get('valid_until'),"),
    ('F19_policy_valid_until',"'valid_from':policy.get('valid_from'),'valid_until':policy.get('valid_until'),","'valid_from':policy.get('valid_from'),'valid_until':None,"),
    ('F20_policy_capacity',"                      'capacity':policy.get('capacity'),'release_sha':policy.get('release_sha')},","                      'capacity':None,'release_sha':policy.get('release_sha')},"),
    ('F21_policy_release_sha',"                      'capacity':policy.get('capacity'),'release_sha':policy.get('release_sha')},","                      'capacity':policy.get('capacity'),'release_sha':None},"),
    ('F22_release_parent',"'release':{'parent':chain_effects(plan['release']['parent']),","'release':{'parent':None,"),
    ('F23_release_path',"'path':release_path(plan),'sha256':plan['release']['sha256'],","'path':release_directory_path(plan),'sha256':plan['release']['sha256'],"),
    ('F24_release_hash',"'path':release_path(plan),'sha256':plan['release']['sha256'],","'path':release_path(plan),'sha256':None,"),
    ('F25_release_size',"                       'bytes':plan['release']['bytes'],'expect':","                       'bytes':None,'expect':"),
    ('F26_release_expectation',"'expect':'INSTALLED_BY_AN_EARLIER_OPERATION_READ_AND_COMPARED_NEVER_WRITTEN'},","'expect':None},"),
    ('F27_recreate_project',"'recreate':{'project':compose['project'],'env_file':compose['env_file'],","'recreate':{'project':None,'env_file':compose['env_file'],"),
    ('F28_recreate_env_file',"'recreate':{'project':compose['project'],'env_file':compose['env_file'],","'recreate':{'project':compose['project'],'env_file':None,"),
    ('F29_recreate_files_without_the_override',"'files':compose['files']+[override_path(plan)],'service':WORKER_SERVICE,","'files':compose['files'],'service':WORKER_SERVICE,"),
    ('F30_recreate_service',"'files':compose['files']+[override_path(plan)],'service':WORKER_SERVICE,","'files':compose['files']+[override_path(plan)],'service':None,"),
    ('F31_recreate_container',"                        'container':worker_name(plan),'image_id':plan['worker']['image_id'],","                        'container':None,'image_id':plan['worker']['image_id'],"),
    ('F32_recreate_image',"                        'container':worker_name(plan),'image_id':plan['worker']['image_id'],","                        'container':worker_name(plan),'image_id':None,"),
    ('F33_recreate_build',"'build_sha':EPOCH_REVISION,'environment':environment_of(plan),","'build_sha':None,'environment':environment_of(plan),"),
    ('F34_recreate_environment_names_only',"'build_sha':EPOCH_REVISION,'environment':environment_of(plan),","'build_sha':EPOCH_REVISION,'environment':sorted(environment_of(plan)),"),
    ('F35_worker_mount_source',"'worker_mount':{'source':plan['data_root'],'target':plan['worker']['mount_target']},","'worker_mount':{'source':None,'target':plan['worker']['mount_target']},"),
    ('F36_worker_mount_target',"'worker_mount':{'source':plan['data_root'],'target':plan['worker']['mount_target']},","'worker_mount':{'source':plan['data_root'],'target':None},"),
    ('F37_lock_path',"                        'lock':lock_path(plan),'lock_wait_seconds':plan['lock']['wait_seconds'],","                        'lock':None,'lock_wait_seconds':plan['lock']['wait_seconds'],"),
    ('F38_lock_wait',"                        'lock':lock_path(plan),'lock_wait_seconds':plan['lock']['wait_seconds'],","                        'lock':lock_path(plan),'lock_wait_seconds':MAX_LOCK_WAIT_SECONDS,"),
    ('F39_lock_chain',"'lock_chain_sha256':sha(canonical(plan['lock']['directory'])),","'lock_chain_sha256':None,"),
    ('F40_deploy_directory',"                        'deploy_directory':chain_effects(plan['deploy_directory'])},","                        'deploy_directory':deploy_path(plan)},"),
    ('F41_required_pin',"'required':{'maintenance_pin':pin_path(plan),","'required':{'maintenance_pin':None,"),
    ('F42_required_reboot_marker',"'reboot_pending_marker_absent':REBOOT_PENDING_PATH,'deploy_version':EPOCH_REVISION},","'reboot_pending_marker_absent':None,'deploy_version':EPOCH_REVISION},"),
    ('F43_required_deploy_version',"'reboot_pending_marker_absent':REBOOT_PENDING_PATH,'deploy_version':EPOCH_REVISION},","'reboot_pending_marker_absent':REBOOT_PENDING_PATH,'deploy_version':None},"),
    ('F44_evidence_boot',"            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],'pre_existing_objects_modified':","            'evidence_boot_id_sha256':None,'pre_existing_objects_modified':"),
    ('F45_says_nothing_existing_is_modified',"'pre_existing_objects_modified':'THE_WORKER_CONTAINER_IS_REPLACED','activation':False}","'pre_existing_objects_modified':False,'activation':False}"),
    ('F46_activation_flag',"'pre_existing_objects_modified':'THE_WORKER_CONTAINER_IS_REPLACED','activation':False}","'pre_existing_objects_modified':'THE_WORKER_CONTAINER_IS_REPLACED','activation':None}")]
for name,old,new in EFFECTS:add(name,old,new)
add('F47_success_criterion_is_another_outcome',"def success_of(plan):return COMPLETE_OUTCOME","def success_of(plan):return PARTIAL_OUTCOME")

# ---------------------------------------------------------------- OWN: what is read on the host before the first effect
add('H01_descriptor_not_closed_when_it_cannot_be_pinned',"    except BaseException:\n        host.close(fd);raise\n    pinned.append(holder);return holder\n","    except BaseException:\n        raise\n    pinned.append(holder);return holder\n")
add('H02_release_directory_followed_through_a_link',"    need(stat.S_ISDIR(named.st_mode),'RELEASE_DIRECTORY_NOT_AS_INSTALLED')\n    gate();fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=parent.fd)",
    "    gate();fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=parent.fd)")
add('H03_release_absence_is_an_os_error',"    try:named=host.lstat(name,parent.fd)\n    except FileNotFoundError:raise Refused('RELEASE_NOT_INSTALLED') from None\n    need(stat.S_ISDIR(named.st_mode)","    named=host.lstat(name,parent.fd)\n    need(stat.S_ISDIR(named.st_mode)")
add('H04_release_file_absence_is_an_os_error',"    try:named=host.lstat(release['file_name'],directory.fd)\n    except FileNotFoundError:raise Refused('RELEASE_NOT_INSTALLED') from None\n","    named=host.lstat(release['file_name'],directory.fd)\n")
add('H05_release_signature_is_constant',"    need(len(raw)==release['bytes'] and sha(raw)==release['sha256'],'RELEASE_HASH_MISMATCH')\n    return stat_signature(info)\n","    need(len(raw)==release['bytes'] and sha(raw)==release['sha256'],'RELEASE_HASH_MISMATCH')\n    return None\n")
add('H06_release_read_limit_removed',"raw,info=read_regular(host,release['file_name'],directory.fd,gate,MAX_RELEASE_BYTES)","raw,info=read_regular(host,release['file_name'],directory.fd,gate,1<<30)")
add('H07_deploy_version_absence_is_an_os_error',"    try:named=host.lstat(DEPLOY_VERSION_NAME,directory.fd)\n    except FileNotFoundError:raise Refused('DEPLOY_VERSION_ABSENT') from None\n","    named=host.lstat(DEPLOY_VERSION_NAME,directory.fd)\n")
add('H08_deploy_version_compared_by_prefix',"    need(raw.strip()==EPOCH_REVISION.encode('ascii'),'DEPLOY_VERSION_MISMATCH')","    need(raw.strip().startswith(EPOCH_REVISION.encode('ascii')),'DEPLOY_VERSION_MISMATCH')")
add('H09_deploy_version_read_limit_removed',"raw,_=read_regular(host,DEPLOY_VERSION_NAME,directory.fd,gate,128)","raw,_=read_regular(host,DEPLOY_VERSION_NAME,directory.fd,gate,1<<20)")
add('H10_environment_file_absence_is_an_os_error',"    try:named=host.lstat(ENV_FILE_NAME,directory.fd)\n    except FileNotFoundError:raise Refused('ENV_FILE_ABSENT') from None\n","    named=host.lstat(ENV_FILE_NAME,directory.fd)\n")
STATE="    raw,info=read_regular(host,ENV_FILE_NAME,directory.fd,gate,MAX_ENV_FILE_BYTES)\n    return stat_signature(info),sha(raw)\n"
add('H11_environment_file_compared_by_signature_only',STATE,STATE.replace("return stat_signature(info),sha(raw)","return stat_signature(info),None"))
add('H12_environment_file_compared_by_bytes_only',STATE,STATE.replace("return stat_signature(info),sha(raw)","return None,sha(raw)"))
add('H13_environment_file_never_compared',STATE,STATE.replace("return stat_signature(info),sha(raw)","return None,None"))
MOUNT="""        need(len(covering)==1 and covering[0][0]==plan['worker']['mount_target'] and covering[0][1].get('type')=='bind'
             and plain(covering[0][1].get('source'))==plan['data_root'] and covering[0][1].get('read_only') in (None,False),'WORKER_MOUNT_NOT_AS_SIGNED')
"""
add('H14_mount_checked_for_the_policy_only',"    for path in (expected[KEY_POLICY_FILE],expected[KEY_RELEASE_FILE]):\n","    for path in (expected[KEY_POLICY_FILE],):\n")
add('H15_mount_checked_for_the_release_only',"    for path in (expected[KEY_POLICY_FILE],expected[KEY_RELEASE_FILE]):\n","    for path in (expected[KEY_RELEASE_FILE],):\n")
add('H16_any_covering_volume_is_enough',MOUNT,MOUNT.replace("len(covering)==1","len(covering)>=1"))
add('H17_read_only_bind_accepted',MOUNT,MOUNT.replace(" and covering[0][1].get('read_only') in (None,False)",""))
add('H18_explicit_read_only_true_accepted',MOUNT,MOUNT.replace("in (None,False)","in (None,False,True)"))
add('H19_volumes_looked_up_by_exact_target',"        covering=[pair for pair in binds if inside(path,pair[0])]\n","        covering=[pair for pair in binds if pair[0]==plan['worker']['mount_target']]\n")
add('H25_bind_source_compared_as_printed',MOUNT,MOUNT.replace("plain(covering[0][1].get('source'))","covering[0][1].get('source')"))
add('H26_bind_target_compared_as_printed',"    binds=[(plain(item['target']),item) for item in volumes]\n","    binds=[(item['target'],item) for item in volumes]\n")
PLAIN="    return str(PurePosixPath(path)) if type(path) is str else path\n"
add('H27_plain_of_what_is_not_text_raises',PLAIN,"    return str(PurePosixPath(path))\n")
add('H28_plain_strips_nothing',PLAIN,"    return path\n")
WATCH="""    try:start=monotonic()
    except Exception:start=None
    def read():
        try:return int(round((monotonic()-start)*1000))
        except Exception:return None
    return read
"""
add('H29_stopwatch_raises_when_the_clock_fails_at_the_start',WATCH,WATCH.replace("    try:start=monotonic()\n    except Exception:start=None\n","    start=monotonic()\n"))
add('H30_stopwatch_raises_when_the_clock_fails_at_the_reading',WATCH,WATCH.replace("        try:return int(round((monotonic()-start)*1000))\n        except Exception:return None\n","        return int(round((monotonic()-start)*1000))\n"))
add('H31_stopwatch_in_seconds',WATCH,WATCH.replace("*1000))","*1))"))
add('Q19_render_from_the_files_not_timed',"            detail['budget']['render_from_the_files_milliseconds']=taken()\n","            detail['budget']['render_from_the_files_milliseconds']=None\n")
add('Q20_recreate_not_timed',"returncode=result['returncode'],code=result['code'],milliseconds=taken())","returncode=result['returncode'],code=result['code'],milliseconds=None)")
add('H20_render_values_not_all_compared',"    need(all(environment.get(key)==value for key,value in expected.items()),'RENDER_ENVIRONMENT_MISMATCH')","    need(any(environment.get(key)==value for key,value in expected.items()),'RENDER_ENVIRONMENT_MISMATCH')")
add('H21_status_file_read_through_a_link',"        if not stat.S_ISREG(named.st_mode):return {'present':None,'status':None,'readiness':None}\n","")
add('H22_status_codes_not_filtered',"    def code(value):return value if text(value,'[A-Z0-9_]{1,100}') else None\n","    def code(value):return value\n")
add('H23_status_failure_escapes',"    except Exception:return {'present':None,'status':None,'readiness':None}\n\nAFTER_FACTS","    except KeyError:return {'present':None,'status':None,'readiness':None}\n\nAFTER_FACTS")
add('H24_status_absence_reported_as_unknown',"        except FileNotFoundError:return {'present':False,'status':None,'readiness':None}","        except FileNotFoundError:return {'present':None,'status':None,'readiness':None}")
# the precheck of perform: order, and what the generated mutants cannot say
add('P01_identity_not_first',"            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n            host.umask(0o077)\n            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')\n",
    "            host.umask(0o077)\n            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')\n            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n")
add('P02_umask_not_set',"            host.umask(0o077)\n","")
add('P03_umask_022',"            host.umask(0o077)\n","            host.umask(0o022)\n")
add('P04_gate_not_called_before_the_first_observation',"    gate()                                                    # first gate call: before anything is observed\n","")
add('P05_run_not_marked_started',"    state.started=True\n    detail={'chains':{}","    detail={'chains':{}")
add('P06_destination_probe_unavailable_accepted',"need(found.get('exists') is False,'DESTINATION_PRESENT')","need(found.get('exists') is not True,'DESTINATION_PRESENT')")
add('P07_pin_of_any_type',"need(probe(host,pin_path(plan),gate).get('type')=='file','MAINTENANCE_PIN_ABSENT')","need(probe(host,pin_path(plan),gate).get('exists') is True,'MAINTENANCE_PIN_ABSENT')")
add('P08_image_failure_keeps_the_generic_code',"            try:image=image_facts(commands,plan['worker']['image_id'])\n            except CommandFailed:raise Refused('IMAGE_ABSENT_OR_UNREADABLE') from None\n","            image=image_facts(commands,plan['worker']['image_id'])\n")
add('P09_render_image_failure_keeps_the_generic_code',"            try:resolved=image_facts(commands,service['image'])\n            except CommandFailed:raise Refused('RENDER_IMAGE_UNRESOLVED') from None\n","            resolved=image_facts(commands,service['image'])\n")
add('P10_keys_must_be_absent_only_when_all_are_present',"need(not any(values[key]['present'] for key in ACTIVATION_KEYS),'WORKER_ALREADY_CARRIES_THE_KEYS')","need(not all(values[key]['present'] for key in ACTIVATION_KEYS),'WORKER_ALREADY_CARRIES_THE_KEYS')")
add('P11_keys_judged_by_equality_not_presence',"need(not any(values[key]['present'] for key in ACTIVATION_KEYS),'WORKER_ALREADY_CARRIES_THE_KEYS')","need(not any(values[key]['equal'] for key in ACTIVATION_KEYS),'WORKER_ALREADY_CARRIES_THE_KEYS')")
add('P12_render_without_the_override',"compose_render(commands,'render',compose['project'],compose['env_file'],compose['files'],EPOCH_REVISION,override=override)","compose_render(commands,'render_files',compose['project'],compose['env_file'],compose['files'],EPOCH_REVISION)")
add('P13_reboot_marker_unavailable_accepted',"            need(pending.get('status')=='COMPLETE','REBOOT_STATE_UNAVAILABLE');need(pending.get('exists') is False,'SECURITY_REBOOT_PENDING')\n","            need(pending.get('exists') is not True,'SECURITY_REBOOT_PENDING')\n")
add('P14_reboot_marker_not_looked_at',"            need(pending.get('status')=='COMPLETE','REBOOT_STATE_UNAVAILABLE');need(pending.get('exists') is False,'SECURITY_REBOOT_PENDING')\n","")
UNDER="""            deploy_version(host,deploy,gate)
            need(env_file_state(host,deploy,gate)==env_before,'ENV_FILE_CHANGED_BEFORE_THE_LOCK')
            need(compose_file_state(host,project,gate)==compose_before,'COMPOSE_FILE_CHANGED_BEFORE_THE_LOCK')
            need(release_state(host,plan,release_directory,gate)==release_before,'RELEASE_CHANGED_BEFORE_THE_LOCK')
            again=container_facts(commands,container)
"""
add('P29_compose_file_not_read_again_under_the_lock',UNDER,UNDER.replace("            need(compose_file_state(host,project,gate)==compose_before,'COMPOSE_FILE_CHANGED_BEFORE_THE_LOCK')\n",""))
add('P30_compose_file_reread_without_comparing',UNDER,UNDER.replace("need(compose_file_state(host,project,gate)==compose_before,'COMPOSE_FILE_CHANGED_BEFORE_THE_LOCK')","compose_file_state(host,project,gate)"))
add('P15_deploy_version_not_read_again_under_the_lock',UNDER,UNDER.replace("            deploy_version(host,deploy,gate)\n",""))
add('P16_release_not_read_again_under_the_lock',UNDER,UNDER.replace("            need(release_state(host,plan,release_directory,gate)==release_before,'RELEASE_CHANGED_BEFORE_THE_LOCK')\n",""))
add('P17_release_reread_without_comparing',UNDER,UNDER.replace("need(release_state(host,plan,release_directory,gate)==release_before,'RELEASE_CHANGED_BEFORE_THE_LOCK')","release_state(host,plan,release_directory,gate)"))
AGAIN="need(all(again[key]==before[key] for key in ('id','started_at','restarts')) and alive(again),'WORKER_CHANGED_BEFORE_THE_LOCK')"
add('P18_worker_id_not_compared_under_the_lock',AGAIN,AGAIN.replace("('id','started_at','restarts')","('started_at','restarts')"))
add('P19_worker_started_at_not_compared_under_the_lock',AGAIN,AGAIN.replace("('id','started_at','restarts')","('id','restarts')"))
add('P20_worker_restarts_not_compared_under_the_lock',AGAIN,AGAIN.replace("('id','started_at','restarts')","('id','started_at')"))
LISTED="            need([row['id'] for row in listing if row['name']==container]==[before['id']],'CONTAINER_LIST_INCONSISTENT')\n"
add('P23_listing_checked_for_the_name_only',LISTED,"            need(len([row['id'] for row in listing if row['name']==container])==1,'CONTAINER_LIST_INCONSISTENT')\n")
ALIVE="    return row['running'] is True and row['state']=='running'\n"
add('P21_alive_by_the_state_alone',ALIVE,"    return row['state']=='running'\n")
add('P22_alive_by_the_flag_alone',ALIVE,"    return row['running'] is True\n")
add('P24_lock_asked_for_after_the_reads_under_it',"            detail['precheck']['lock_attempts']=acquire_lock(host,lock[0],gate,plan['lock']['wait_seconds'],needed+UNDER_LOCK_ALLOWANCE_SECONDS)\n            need(lock_still_named(host,LOCK_FILE_NAME,lock_directory,lock[0]),'LOCK_FILE_REPLACED')\n            pending=probe(host,REBOOT_PENDING_PATH,gate)\n",
    "            pending=probe(host,REBOOT_PENDING_PATH,gate)\n")
add('P25_budget_checked_against_zero',"            need(left>=needed,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')","            need(left>=0,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')")
add('P26_precheck_failure_is_not_a_refusal',"        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})","        if code is not None:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,code,{'phase_reached':'PRECHECK'})")
add('P27_precheck_failure_goes_on',"        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})\n","")
add('P28_os_error_in_the_precheck_escapes',"        except Exception as error:\n            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')","        except Refused as error:\n            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')")

# ---------------------------------------------------------------- OWN: the effects and their readback
add('Q01_directory_mode_0755',"        entry=create_directory('DIRECTORY',live,PRIVATE_DIRECTORY_MODE,parent,host,gate,state,handles)","        entry=create_directory('DIRECTORY',live,0o755,parent,host,gate,state,handles)")
add('Q02_directory_state_not_checked',"        if entry['state']!='CREATED_DURABLE':stop=entry['code'] or 'CREATION_FAILED'\n","")
add('Q03_files_delivered_after_a_failed_directory',"            if stop is not None:\n                ledger.append({'key':key,'path':path,'state':'NOT_ATTEMPTED','code':None});continue\n","")
add('Q04_file_state_not_checked',"            if row['state']!='INSTALLED_DURABLE':stop=row['code'] or 'INSTALL_FAILED'\n","")
add('Q05_files_share_one_temporary_index',"            row=create_file(index,key,path,raw,PRIVATE_FILE_MODE,handles['DIRECTORY'],host,gate,state,go16)","            row=create_file(0,key,path,raw,PRIVATE_FILE_MODE,handles['DIRECTORY'],host,gate,state,go16)")
add('Q06_override_delivered_before_the_policy',"enumerate((('POLICY',policy_path(plan),content),('OVERRIDE',override_path(plan),override)))","enumerate((('OVERRIDE',override_path(plan),override),('POLICY',policy_path(plan),content)))")
add('Q07_override_bytes_delivered_as_the_policy',"enumerate((('POLICY',policy_path(plan),content),('OVERRIDE',override_path(plan),override)))","enumerate((('POLICY',policy_path(plan),override),('OVERRIDE',override_path(plan),override)))")
add('Q08_files_not_read_back',"            for row,raw in zip(ledger,contents):stop=stop or readback_file(row,raw,PRIVATE_FILE_MODE,handles['DIRECTORY'],host,gate)\n","            pass\n")
add('Q09_only_the_first_file_read_back',"            for row,raw in zip(ledger,contents):stop=stop or readback_file(row,raw,PRIVATE_FILE_MODE,handles['DIRECTORY'],host,gate)\n","            for row,raw in list(zip(ledger,contents))[:1]:stop=stop or readback_file(row,raw,PRIVATE_FILE_MODE,handles['DIRECTORY'],host,gate)\n")
add('Q10_directory_not_read_back',"        if stop is None:stop=readback_directory(live,PRIVATE_DIRECTORY_MODE,handles['DIRECTORY'],host,gate,len(contents))\n","")
add('Q11_directory_read_back_for_three_entries',"readback_directory(live,PRIVATE_DIRECTORY_MODE,handles['DIRECTORY'],host,gate,len(contents))","readback_directory(live,PRIVATE_DIRECTORY_MODE,handles['DIRECTORY'],host,gate,len(contents)+1)")
BEFORE_UP="""                need(lock_still_named(host,LOCK_FILE_NAME,lock_directory,lock[0]),'LOCK_FILE_REPLACED')
                need(service_of(compose_render(commands,'render_files',compose['project'],compose['env_file'],listed,EPOCH_REVISION),plan)['image']==service['image'],
                     'RENDER_IMAGE_CHANGED')
"""
add('Q13_no_render_from_the_files',BEFORE_UP,BEFORE_UP.replace("                need(service_of(compose_render(commands,'render_files',compose['project'],compose['env_file'],listed,EPOCH_REVISION),plan)['image']==service['image'],\n                     'RENDER_IMAGE_CHANGED')\n",""))
add('Q14_render_from_the_files_without_the_override',BEFORE_UP,BEFORE_UP.replace("compose['env_file'],listed,EPOCH_REVISION)","compose['env_file'],compose['files'],EPOCH_REVISION)"))
add('Q15_render_from_the_files_not_judged',BEFORE_UP,BEFORE_UP.replace("need(service_of(compose_render(commands,'render_files',compose['project'],compose['env_file'],listed,EPOCH_REVISION),plan)['image']==service['image'],\n                     'RENDER_IMAGE_CHANGED')","compose_render(commands,'render_files',compose['project'],compose['env_file'],listed,EPOCH_REVISION)"))
add('Q16_failure_before_the_recreate_is_ignored',"            except Exception as error:stop=code_of(error,'RECREATE_PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'RECREATE_PRECHECK_FAILED')","            except Exception as error:pass")
add('Q17_recreate_without_the_override',"            result=compose_up(state,commands,'recreate',compose['project'],compose['env_file'],listed,EPOCH_REVISION)","            result=compose_up(state,commands,'recreate',compose['project'],compose['env_file'],compose['files'],EPOCH_REVISION)")
add('Q18_recreate_that_did_not_start_is_ignored',"            if not result['started']:stop=result['code'] or 'COMMAND_NOT_STARTED'\n            else:","            if not result['started']:stop=None\n            else:")
# the facts after the recreate
add('R01_first_reading_by_the_old_id',"        row=container_facts(commands,container);seen['first']=row;seen['at']=c['monotonic']()","        row=container_facts(commands,before['id']);seen['first']=row;seen['at']=c['monotonic']()")
add('R02_new_means_any_container',"        facts.update(worker_is_new=row['id']!=before['id'],running=","        facts.update(worker_is_new=True,running=")
add('R03_first_reading_always_says_running',"running=alive(row),restarts=row['restarts'],","running=True,restarts=row['restarts'],")
add('R05_restart_count_reported_as_zero',"running=alive(row),restarts=row['restarts'],","running=alive(row),restarts=0,")
add('R06_image_not_compared',"                     image_is_the_signed_one=row['image_id']==plan['worker']['image_id'])","                     image_is_the_signed_one=True)")
add('R07_environment_of_the_old_container',"            values=container_environment(commands,seen['first']['id'],c['signed'])","            values=container_environment(commands,before['id'],c['signed'])")
add('R08_environment_any_name_is_enough',"            facts['environment_as_signed']=all(item=={'present':True,'equal':True} for item in values.values())","            facts['environment_as_signed']=any(item=={'present':True,'equal':True} for item in values.values())")
add('R09_environment_presence_is_enough',"            facts['environment_as_signed']=all(item=={'present':True,'equal':True} for item in values.values())","            facts['environment_as_signed']=all(item['present'] for item in values.values())")
add('R10_environment_without_the_build_revision',"'listing':listing,'signed':signed,'deploy':deploy,","'listing':listing,'signed':expected,'deploy':deploy,")
LISTING="""        facts.update(worker_listed_once=len(named)==1 and ('first' not in seen or named==[seen['first']['id']]),
                     old_container_gone=before['id'] not in [row['id'] for row in rows],
                     others_unchanged=others(rows,False)==others(c['listing'],False),others_states_unchanged=others(rows,True)==others(c['listing'],True))
"""
add('R11_worker_listed_any_number_of_times',LISTING,LISTING.replace("len(named)==1 and","len(named)>=1 and"))
add('R12_listed_id_not_compared_with_the_inspected_one',LISTING,LISTING.replace("len(named)==1 and ('first' not in seen or named==[seen['first']['id']])","len(named)==1"))
add('R13_old_container_looked_for_by_name_only',LISTING,LISTING.replace("before['id'] not in [row['id'] for row in rows]","before['id'] not in named"))
add('R14_others_not_compared',LISTING,LISTING.replace("others_unchanged=others(rows,False)==others(c['listing'],False)","others_unchanged=True"))
add('R15_others_compared_with_their_states',LISTING,LISTING.replace("others_unchanged=others(rows,False)==others(c['listing'],False)","others_unchanged=others(rows,True)==others(c['listing'],True)"))
OTHERS="        def others(source,states):return sorted((row['id'],row['name'])+((row['state'],) if states else ()) for row in source if row['name']!=container)\n"
add('R16_others_compared_by_name_only',OTHERS,OTHERS.replace("(row['id'],row['name'])+","(row['name'],)+"))
add('R17_others_compared_by_id_only',OTHERS,OTHERS.replace("(row['id'],row['name'])+","(row['id'],)+"))
add('R18_listing_does_not_stand_in_for_a_failed_inspect',"        if 'first' not in seen and len(named)==1:facts['worker_is_new']=named[0]!=before['id']","        pass")
ENV_AFTER="    def environment_file():facts['env_file_unchanged']=reached_by_name(c['deploy'],gate) and env_file_state(host,c['deploy'],gate)==c['env_before']\n"
add('R19_environment_file_not_compared_after',ENV_AFTER,"    def environment_file():facts['env_file_unchanged']=True\n")
add('R43_environment_file_after_on_the_word_of_the_descriptor',ENV_AFTER,ENV_AFTER.replace("reached_by_name(c['deploy'],gate) and ",""))
COMPOSE_AFTER="    def compose_file():facts['compose_file_unchanged']=reached_by_name(c['project'],gate) and compose_file_state(host,c['project'],gate)==c['compose_before']\n"
add('R45_compose_file_not_compared_after',COMPOSE_AFTER,"    def compose_file():facts['compose_file_unchanged']=True\n")
add('R46_compose_file_after_on_the_word_of_the_descriptor',COMPOSE_AFTER,COMPOSE_AFTER.replace("reached_by_name(c['project'],gate) and ",""))
add('R56_compose_file_after_by_the_name_alone',COMPOSE_AFTER,COMPOSE_AFTER.replace(" and compose_file_state(host,c['project'],gate)==c['compose_before']",""))
RELEASE_AFTER="    def release():facts['release_unchanged']=reached_by_name(c['release_directory'],gate) and release_state(host,plan,c['release_directory'],gate)==c['release_before']\n"
add('R47_release_not_compared_after',RELEASE_AFTER,"    def release():facts['release_unchanged']=True\n")
add('R48_release_after_on_the_word_of_the_descriptor',RELEASE_AFTER,RELEASE_AFTER.replace("reached_by_name(c['release_directory'],gate) and ",""))
add('R57_release_after_by_the_name_alone',RELEASE_AFTER,RELEASE_AFTER.replace(" and release_state(host,plan,c['release_directory'],gate)==c['release_before']",""))
COUNTS="""        was={row['name']:row['id'] for row in c['listing'] if row['name']!=container};now={row['name']:row['id'] for row in rows if row['name']!=container}
        facts.update(others_appeared=len([name for name in now if name not in was]),others_gone=len([name for name in was if name not in now]),
                     others_same_name_new_id=len([name for name in now if name in was and now[name]!=was[name]]),service_leftovers=len(leftovers(rows,container)))
"""
add('R50_others_that_appeared_not_counted',COUNTS,COUNTS.replace("others_appeared=len([name for name in now if name not in was])","others_appeared=0"))
add('R51_others_that_went_not_counted',COUNTS,COUNTS.replace("others_gone=len([name for name in was if name not in now])","others_gone=0"))
add('R52_others_recreated_not_counted',COUNTS,COUNTS.replace("others_same_name_new_id=len([name for name in now if name in was and now[name]!=was[name]])","others_same_name_new_id=0"))
add('R53_leftovers_of_the_service_not_counted',COUNTS,COUNTS.replace("service_leftovers=len(leftovers(rows,container))","service_leftovers=0"))
add('R54_the_worker_counted_among_the_others',COUNTS,COUNTS.replace("now={row['name']:row['id'] for row in rows if row['name']!=container}","now={row['name']:row['id'] for row in rows}").replace("was={row['name']:row['id'] for row in c['listing'] if row['name']!=container}","was={row['name']:row['id'] for row in c['listing']}"))
DELIVERED="        facts['files_as_delivered']=codes==[None,None]\n"
add('R20_files_not_judged_after',DELIVERED,"        facts['files_as_delivered']=True\n")
add('R21_only_the_policy_judged_after',DELIVERED,"        facts['files_as_delivered']=codes[:1]==[None]\n")
add('R22_only_the_override_judged_after',DELIVERED,"        facts['files_as_delivered']=codes[1:]==[None]\n")
LOCK_AFTER="    def locked():facts['lock_still_named']=reached_by_name(c['lock_directory'],gate) and lock_still_named(host,LOCK_FILE_NAME,c['lock_directory'],c['lock'])\n"
add('R26_lock_not_judged_after',LOCK_AFTER,"    def locked():facts['lock_still_named']=True\n")
add('R44_lock_after_on_the_word_of_the_descriptor_of_its_directory',LOCK_AFTER,LOCK_AFTER.replace("reached_by_name(c['lock_directory'],gate) and ",""))
add('R58_lock_after_by_the_name_of_its_directory_alone',LOCK_AFTER,LOCK_AFTER.replace(" and lock_still_named(host,LOCK_FILE_NAME,c['lock_directory'],c['lock'])",""))
SECOND="            facts['second_check_passed']=row['started_at']==first['started_at'] and alive(row) and row['restarts']==0\n"
add('R27_second_reading_ignores_the_start_instant',SECOND,SECOND.replace("row['started_at']==first['started_at'] and ",""))
add('R28_second_reading_ignores_whether_it_runs',SECOND,SECOND.replace("alive(row) and ",""))
add('R30_second_reading_ignores_the_restart_count',SECOND,SECOND.replace(" and row['restarts']==0",""))
add('R31_second_reading_by_name',"row=container_facts(commands,first['id'],expected_name=container)","row=container_facts(commands,container)")
add('R42_second_reading_without_the_name',"row=container_facts(commands,first['id'],expected_name=container)","row=container_facts(commands,first['id'])")
STEPS="    for label,action in (('WORKER',worker),('ENVIRONMENT',environment),('CONTAINERS',containers),('ENV_FILE',environment_file),('COMPOSE_FILE',compose_file),\n                         ('RELEASE',release),('FILES',delivered),('LOCK',locked),('SETTLE',settle),('SECOND_CHECK',second),('WORKER_STATUS',status)):step(label,action)"
add('R32_second_reading_not_made',STEPS,STEPS.replace("('SECOND_CHECK',second),","")+"\n    facts['second_check_passed']=True")
add('R55_compose_file_not_read_after',STEPS,STEPS.replace("('COMPOSE_FILE',compose_file),",""))
add('R59_release_not_read_after',STEPS,STEPS.replace("('RELEASE',release),",""))
add('R33_second_reading_before_the_pause',"('LOCK',locked),('SETTLE',settle),('SECOND_CHECK',second),('WORKER_STATUS',status)):step(label,action)","('LOCK',locked),('SECOND_CHECK',second),('SETTLE',settle),('WORKER_STATUS',status)):step(label,action)")
add('R34_a_failed_step_stops_the_others',"        try:action()\n        except Exception as error:failed[label]=code_of(error,'OS_ERROR' if isinstance(error,OSError) else 'READBACK_FAILED')\n    def worker():","        action()\n    def worker():")
UNCHANGED="""    unchanged=bool(first is not None and seen.get('listing_unchanged') is True and alive(first)
                   and all(first[key]==before[key] for key in ('started_at','restarts')))
"""
add('R35_unchanged_without_the_listing',UNCHANGED,UNCHANGED.replace(" and seen.get('listing_unchanged') is True",""))
add('R36_unchanged_without_the_start_instant',UNCHANGED,UNCHANGED.replace("('started_at','restarts')","('restarts',)"))
add('R37_unchanged_without_whether_it_runs',UNCHANGED,UNCHANGED.replace(" and alive(first)",""))
add('R39_unchanged_whenever_the_inspect_answered',UNCHANGED,"    unchanged=first is not None\n")
add('R41_unchanged_without_the_restart_count',UNCHANGED,UNCHANGED.replace("('started_at','restarts')","('started_at',)"))
# the criteria and the settlement of the recreate call
CRITERIA=[('S01','returned_0',"(result['code'] or 'RECREATE_RETURNED_NONZERO',bool(result['returned'] and result['returncode']==0)),","(result['code'] or 'RECREATE_RETURNED_NONZERO',True),"),
    ('S02','return_code_ignored',"bool(result['returned'] and result['returncode']==0)","bool(result['returned'])"),
    ('S03','worker_found',"('WORKER_NOT_FOUND_AFTER_RECREATE',facts['worker_listed_once']),",""),
    ('S04','worker_new',"('WORKER_NOT_RECREATED',facts['worker_is_new']),",""),
    ('S05','old_gone',"('OLD_CONTAINER_STILL_PRESENT',facts['old_container_gone']),",""),
    ('S06','running',"('WORKER_NOT_RUNNING_AFTER_RECREATE',facts['running']),",""),
    ('S07','restarts',"                          ('WORKER_RESTARTED_AFTER_RECREATE',None if facts['restarts'] is None else facts['restarts']==0),\n",""),
    ('S08','restarts_at_most_one',"facts['restarts']==0),","facts['restarts']<=1),"),
    ('S09','image',"('WORKER_IMAGE_CHANGED',facts['image_is_the_signed_one']),",""),
    ('S10','environment',"('ENVIRONMENT_NOT_AS_SIGNED',facts['environment_as_signed']),",""),
    ('S11','others',"('OTHER_CONTAINERS_CHANGED',facts['others_unchanged']),",""),
    ('S12','env_file',"('ENV_FILE_CHANGED',facts['env_file_unchanged']),",""),
    ('S13','files',"('FILES_NOT_AS_DELIVERED',facts['files_as_delivered']),",""),
    ('S14','lock',"('LOCK_FILE_REPLACED',facts['lock_still_named']),\n","\n"),
    ('S42','compose_file',"('COMPOSE_FILE_CHANGED',facts['compose_file_unchanged']),",""),
    ('S43','release',"('RELEASE_CHANGED',facts['release_unchanged']),\n","\n"),
    ('S15','pause',"('SECOND_CHECK_NOT_APART',facts['settle_pause_taken']),",""),
    ('S16','second_reading',",('WORKER_CHANGED_BETWEEN_THE_TWO_CHECKS',facts['second_check_passed'])]","]")]
for name,label,old,new in CRITERIA:add('%s_criterion_%s_dropped'%(name,label),old,new)
add('S17_unread_criterion_counts_as_met',"                missing=[name if value is False else 'READBACK_UNAVAILABLE' for name,value in criteria if value is not True]","                missing=[name for name,value in criteria if value is False]")
add('S18_unread_criterion_named_as_if_false',"                missing=[name if value is False else 'READBACK_UNAVAILABLE' for name,value in criteria if value is not True]","                missing=[name for name,value in criteria if value is not True]")
add('S19_complete_run_not_settled_as_done',"                    state.done();run.update(state='RECREATED_VERIFIED',replaced=True)","                    state.unknown();run.update(state='RECREATED_VERIFIED',replaced=True)")
add('S20_unchanged_accepted_without_a_return',"                elif result['returned'] and unchanged:","                elif unchanged:")
add('S21_any_returned_failure_is_called_unchanged',"                elif result['returned'] and unchanged:","                elif result['returned']:")
add('S22_unchanged_settled_as_unknown',"                    state.fail();run.update(state='NOT_RECREATED',replaced=False)","                    state.unknown();run.update(state='NOT_RECREATED',replaced=False)")
add('S23_unchanged_never_recognised',"                elif result['returned'] and unchanged:","                elif False:")
add('S24_returned_and_not_verified_settled_as_done',"                    if result['returned']:state.unknown()\n","                    if result['returned']:state.done()\n")
add('S25_returned_and_not_verified_settled_as_failed',"                    if result['returned']:state.unknown()\n","                    if result['returned']:state.fail()\n")
add('S26_returned_and_not_verified_not_settled',"                    if result['returned']:state.unknown()\n","")
ONCE="                        once=not [name for name,value in criteria[:-2] if value is not True] and facts['second_check_passed'] is not False\n"
add('S27_verified_once_whatever_the_first_reading_said',ONCE,"                        once=facts['second_check_passed'] is not False\n")
add('S28_verified_once_although_the_second_reading_failed',ONCE,ONCE.replace(" and facts['second_check_passed'] is not False",""))
add('S29_not_recreated_called_replaced',"                    else:run.update(state='UNCERTAIN',replaced=None)","                    else:run.update(state='UNCERTAIN',replaced=False)")
add('S30_zero_and_nonzero_share_one_code',"                    stop='RECREATE_FAILED_CONTAINER_UNCHANGED' if result['returncode'] else 'RECREATE_RETURNED_ZERO_CONTAINER_UNCHANGED'","                    stop='RECREATE_FAILED_CONTAINER_UNCHANGED'")
add('S31_partial_reported_complete',"        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)","        if stop is None or run['state']=='RECREATED_VERIFIED_ONCE':return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)")
add('S32_partial_reported_refused_whatever_changed',"        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)","        if True:return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)")
add('S33_clean_failure_reported_partial',"        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n","")
OUTCOME="        outcome={'RECREATED_VERIFIED_ONCE':NOT_VERIFIED_OUTCOME,'RECREATED_NOT_VERIFIED':NOT_VERIFIED_OUTCOME,'UNCERTAIN':UNCERTAIN_OUTCOME}.get(run['state'],OBJECTS_ONLY_OUTCOME)\n"
add('S34_uncertain_recreate_reported_as_objects_only',OUTCOME,OUTCOME.replace(",'UNCERTAIN':UNCERTAIN_OUTCOME",""))
add('S35_verified_once_reported_as_objects_only',OUTCOME,OUTCOME.replace("'RECREATED_VERIFIED_ONCE':NOT_VERIFIED_OUTCOME,",""))
add('S36_not_verified_reported_as_objects_only',OUTCOME,OUTCOME.replace("'RECREATED_NOT_VERIFIED':NOT_VERIFIED_OUTCOME,",""))
add('S37_lock_not_released',"        if lock[0] is not None:release_lock(host,lock[0])\n","")
add('S38_handles_not_closed',"        for handle in list(handles.values())+pinned:\n            try:handle.close()\n            except Exception:pass\n","        pass\n")
add('S39_replaced_flag_true_from_the_start',"'started':False,'returned':False,'milliseconds':None,'replaced':False,'facts':None,'unavailable':None}","'started':False,'returned':False,'milliseconds':None,'replaced':True,'facts':None,'unavailable':None}")
add('S40_modified_flag_follows_only_a_proved_replacement',"pre_existing_objects_modified=run['replaced'] is not False,","pre_existing_objects_modified=run['replaced'] is True,")
add('S41_reduction_keeps_the_precheck',"REDUCTIONS=[('PRECHECK_DROPPED',_reduce_precheck),('CHAINS_REDUCED_TO_COUNTS',_reduce_chains)]","REDUCTIONS=[('CHAINS_REDUCED_TO_COUNTS',_reduce_chains)]")

# the one need() whose text occurs twice in the operation part (the lock file, right after the lock is taken and again
# right before the recreate): one mutant per place
add('T01_lock_file_not_looked_at_after_it_is_taken',"needed+UNDER_LOCK_ALLOWANCE_SECONDS)\n            need(lock_still_named(host,LOCK_FILE_NAME,lock_directory,lock[0]),'LOCK_FILE_REPLACED')\n",
    "needed+UNDER_LOCK_ALLOWANCE_SECONDS)\n")
add('T02_lock_file_not_looked_at_before_the_recreate',"            try:\n                need(lock_still_named(host,LOCK_FILE_NAME,lock_directory,lock[0]),'LOCK_FILE_REPLACED')\n",
    "            try:\n")

# the three need() whose text occurs twice (the three directories reached by their names: under the lock, and right
# before the recreate): one mutant per place
NAMED="""            need(reached_by_name(release_directory,gate),'RELEASE_DIRECTORY_REPLACED')
            need(reached_by_name(project,gate),'DEPLOY_TREE_REPLACED')                # proves the deploy tree first, then the project directory in it
            need(reached_by_name(lock_directory,gate),'LOCK_DIRECTORY_REPLACED')
"""
add('T03_release_directory_not_proved_by_name_under_the_lock',NAMED,NAMED.replace("            need(reached_by_name(release_directory,gate),'RELEASE_DIRECTORY_REPLACED')\n",""))
add('T04_deploy_tree_not_proved_by_name_under_the_lock',NAMED,NAMED.replace("            need(reached_by_name(project,gate),'DEPLOY_TREE_REPLACED')                # proves the deploy tree first, then the project directory in it\n",""))
add('T05_lock_directory_not_proved_by_name_under_the_lock',NAMED,NAMED.replace("            need(reached_by_name(lock_directory,gate),'LOCK_DIRECTORY_REPLACED')\n",""))
LAST="""                need(reached_by_name(release_directory,gate),'RELEASE_DIRECTORY_REPLACED')
                need(reached_by_name(project,gate),'DEPLOY_TREE_REPLACED')
                need(reached_by_name(lock_directory,gate),'LOCK_DIRECTORY_REPLACED')
"""
add('T06_release_directory_not_proved_by_name_before_the_recreate',LAST,LAST.replace("                need(reached_by_name(release_directory,gate),'RELEASE_DIRECTORY_REPLACED')\n",""))
add('T07_deploy_tree_not_proved_by_name_before_the_recreate',LAST,LAST.replace("                need(reached_by_name(project,gate),'DEPLOY_TREE_REPLACED')\n",""))
add('T08_lock_directory_not_proved_by_name_before_the_recreate',LAST,LAST.replace("                need(reached_by_name(lock_directory,gate),'LOCK_DIRECTORY_REPLACED')\n",""))
add('T09_project_directory_proved_as_if_it_were_the_deploy_tree',NAMED,NAMED.replace("need(reached_by_name(project,gate),'DEPLOY_TREE_REPLACED')    ","need(reached_by_name(deploy,gate),'DEPLOY_TREE_REPLACED')     "))

# ---------------------------------------------------------------- OWN: the repair after the two reviews of 2026-10-02
add('A10_evidence_operation_not_named',"EVIDENCE_OPERATIONS=('GO_READONLY_HOSTOPS02_EPOCH_READBACK_01',)  ","EVIDENCE_OPERATIONS=()  ")
add('A11_evidence_names_the_precheck_of_the_earlier_family',"EVIDENCE_OPERATIONS=('GO_READONLY_HOSTOPS02_EPOCH_READBACK_01',)  ","EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,)  ")
add('A12_scope_statement_says_no_value_of_any_environment',"No value read from a container, from the render or from the environment '\n                 'file is printed, stored or put in an argv.","No value of any environment '\n                 'file is printed, stored or put in an argv.")
add('B28_compose_file_limit_smaller',"MAX_COMPOSE_FILE_BYTES=1048576\n","MAX_COMPOSE_FILE_BYTES=8\n")
add('B29_compose_file_limit_larger',"MAX_COMPOSE_FILE_BYTES=1048576\n","MAX_COMPOSE_FILE_BYTES=2097152\n")
add('B30_no_floor_of_free_bytes',"FREE_BYTES_FLOOR=1048576   ","FREE_BYTES_FLOOR=0   ")
add('B31_floor_of_free_bytes_one_byte_higher',"FREE_BYTES_FLOOR=1048576   ","FREE_BYTES_FLOOR=1048577   ")
add('B32_floor_of_free_inodes_seven',"FREE_INODES_FLOOR=8   ","FREE_INODES_FLOOR=7   ")
add('B33_floor_of_free_inodes_nine',"FREE_INODES_FLOOR=8   ","FREE_INODES_FLOOR=9   ")
DIGEST="    try:return sha(json.dumps(policy,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8'))\n    except ValueError:raise Refused('POLICY_JSON_INVALID') from None\n"
add('F49_policy_digest_with_ascii_escapes',DIGEST,DIGEST.replace("ensure_ascii=False,",""))
add('F50_policy_digest_with_keys_as_written',DIGEST,DIGEST.replace("sort_keys=True,",""))
add('F51_policy_digest_with_default_separators',DIGEST,DIGEST.replace("separators=(',',':'),",""))
add('F52_policy_text_that_cannot_be_encoded_escapes_as_an_error',DIGEST,"    return sha(json.dumps(policy,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8'))\n")
add('H32_reached_by_name_always_yes',"    try:holder.verify(gate);return True\n    except Refused as error:\n        if str(error)!='PARENT_REPLACED':raise\n        return False\n","    return True\n")
add('H33_window_that_ended_read_as_a_replaced_directory',"        if str(error)!='PARENT_REPLACED':raise\n        return False\n","        return False\n")
add('H34_project_directory_absence_is_an_os_error',"    try:named=host.lstat(name,deploy.fd)\n    except FileNotFoundError:raise Refused('COMPOSE_FILE_ABSENT') from None\n","    named=host.lstat(name,deploy.fd)\n")
add('H35_project_directory_followed_through_a_link',"    need(stat.S_ISDIR(named.st_mode),'COMPOSE_DIRECTORY_NOT_A_DIRECTORY')\n    gate();fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=deploy.fd)",
    "    gate();fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=deploy.fd)")
add('H36_compose_file_absence_is_an_os_error',"    try:named=host.lstat(COMPOSE_FILE_NAME,directory.fd)\n    except FileNotFoundError:raise Refused('COMPOSE_FILE_ABSENT') from None\n","    named=host.lstat(COMPOSE_FILE_NAME,directory.fd)\n")
COMPOSE_STATE="    raw,info=read_regular(host,COMPOSE_FILE_NAME,directory.fd,gate,MAX_COMPOSE_FILE_BYTES)\n    return stat_signature(info),sha(raw)\n"
add('H37_compose_file_compared_by_signature_only',COMPOSE_STATE,COMPOSE_STATE.replace("return stat_signature(info),sha(raw)","return stat_signature(info),None"))
add('H38_compose_file_compared_by_bytes_only',COMPOSE_STATE,COMPOSE_STATE.replace("return stat_signature(info),sha(raw)","return None,sha(raw)"))
add('H39_compose_file_never_compared',COMPOSE_STATE,COMPOSE_STATE.replace("return stat_signature(info),sha(raw)","return None,None"))
add('H40_compose_file_read_limit_removed',COMPOSE_STATE,COMPOSE_STATE.replace("MAX_COMPOSE_FILE_BYTES","1<<30"))
INODES="    numbers=host.fstatvfs(fd);total,free=getattr(numbers,'f_files',0),getattr(numbers,'f_favail',None)\n    return free if integer(total,1) and integer(free) else None\n"
add('H41_inodes_judged_where_the_filesystem_counts_none',INODES,INODES.replace("integer(total,1) and ","integer(total) and "))
add('H42_inodes_free_for_root_counted',INODES,INODES.replace("'f_favail'","'f_ffree'"))
add('H43_free_inodes_that_are_not_a_number_judged',INODES,INODES.replace(" and integer(free)",""))
add('H44_inodes_never_judged',INODES,INODES.replace("    return free if integer(total,1) and integer(free) else None\n","    return None\n"))
LEFTOVERS="    return [row for row in rows if row['name'].endswith('_'+container)]\n"
add('H45_leftovers_never_found',LEFTOVERS,"    return []\n")
add('H46_every_container_named_like_the_worker_is_a_leftover',LEFTOVERS,LEFTOVERS.replace("endswith('_'+container)","endswith(container)"))
add('H47_leftovers_only_by_a_prefix_of_the_name',LEFTOVERS,LEFTOVERS.replace("row['name'].endswith('_'+container)","('_'+container) in row['name']"))
add('H48_release_directory_held_without_its_name_under_the_parent',"    directory=hold(host,fd,pinned,parent=parent,name=name)\n    need(directory.identity==(named.st_dev","    directory=hold(host,fd,pinned,rows=None,parent=parent,name=parent.name)\n    need(directory.identity==(named.st_dev")
add('H49_project_directory_held_under_another_name',"    directory=hold(host,fd,pinned,parent=deploy,name=name)\n","    directory=hold(host,fd,pinned,parent=deploy,name=ENV_FILE_NAME)\n")
add('P31_free_space_asked_of_the_deploy_tree',"            free,inodes=free_bytes(host,parent.fd),free_inodes(host,parent.fd)\n","            free,inodes=free_bytes(host,deploy.fd),free_inodes(host,deploy.fd)\n")
add('P32_free_bytes_for_root_counted',"            free,inodes=free_bytes(host,parent.fd),free_inodes(host,parent.fd)\n","            free,inodes=host.fstatvfs(parent.fd).f_bfree*host.fstatvfs(parent.fd).f_frsize,free_inodes(host,parent.fd)\n")
add('P33_identity_checked_after_the_umask',"            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n            host.umask(0o077)\n","            host.umask(0o077)\n            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n")
add('P34_free_space_not_in_the_receipt',"detail['precheck'].update(reboot_pending=False,containers_listed=len(listing),free_bytes=free,free_inodes=inodes)","detail['precheck'].update(reboot_pending=False,containers_listed=len(listing))")
add('Q21_file_installed_and_not_durable_accepted',"            if row['state']!='INSTALLED_DURABLE':stop=row['code'] or 'INSTALL_FAILED'\n","            if row['state'] not in ('INSTALLED_DURABLE','INSTALLED_NOT_DURABLE'):stop=row['code'] or 'INSTALL_FAILED'\n")
add('Q22_directory_created_and_not_durable_accepted',"        if entry['state']!='CREATED_DURABLE':stop=entry['code'] or 'CREATION_FAILED'\n","        if entry['state'] not in ('CREATED_DURABLE','CREATED_NOT_DURABLE'):stop=entry['code'] or 'CREATION_FAILED'\n")

# ---------------------------------------------------------------- INHERITED: the core's own rows, against this operation's suite
def inherited():
    spec=importlib.util.spec_from_file_location('_hostops02_core_mutants',FROZEN/'mutation'/'mutants.py')
    import sys
    sys.path.insert(0,str(FROZEN/'mutation'))
    try:
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    finally:sys.path.remove(str(FROZEN/'mutation'))
    files={'dispatcher':(OPERATION/'build'/'dispatch_once.py').read_text(),'launcher':(OPERATION/'build'/'launcher_stdin.py').read_text()}
    rows=[];skipped=[]
    for name,target,old,new in module.MUTANTS:
        mine={'dispatcher_write':'dispatcher'}.get(target,target)
        if mine in ('core','runner','docker','parents','files','lock'):text=BUILT
        elif mine in files:text=files[mine]
        else:
            skipped.append(name);continue                       # the rules of assemble.py, the reading dispatcher
        if text.count(old)!=1:
            skipped.append(name);continue                       # a literal of a demonstration operation
        rows.append(('I_'+name,mine,old,new))
    return rows,skipped,module
INHERITED,INHERITED_SKIPPED,_CORE=inherited()
if os.environ.get('HOSTOPS_MUTATION_INHERITED')=='yes':
    for name,target,old,new in INHERITED:
        M.append((name,target,old,new));ORIGIN[name]='INHERITED'

MUTANTS=M
COMBOS={}
REDUNDANT={}
