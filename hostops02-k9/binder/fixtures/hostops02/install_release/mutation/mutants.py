"""The mutants of K10's own part. Each row: (name, target, exact anchor, replacement); target 'op' is the built source
build/install_release.py, in which the anchor must occur exactly once (mutate.py check). The rule of the family:
one mutant per member of effects_of(), one per refusal of validate_plan and of the precheck; here also the constants
of the epoch, the order of the precheck, and what the run does with each failure of an effect.
EFFECTS and REFUSALS name, for each member and each code, the mutant that answers for it; coverage() compares both
tables with the source itself (the members effects_of() returns, the codes the operation part can raise), so a new
member or a new refusal without a mutant is an error of `mutate.py check`."""
import ast
import base64
import hashlib
from pathlib import Path
import re
import sys

M=[]
EFFECTS={}
REFUSALS={}
def add(name,old,new,effect=None,refusal=None):
    M.append((name,'op',old,new))
    for table,keys in ((EFFECTS,effect),(REFUSALS,refusal)):
        for key in ([keys] if type(keys) is str else keys or []):table.setdefault(key,name)

# ---------------------------------------------------------------- the constants of the epoch
add('C01_another_epoch',"RELEASE_EPOCH='R2D2-V2-SHADOW-2026-10-05'","RELEASE_EPOCH='R2D2-V2-SHADOW-2026-09-28'")
add('C02_another_first_session',"FIRST_SESSION='2026-10-05'","FIRST_SESSION='2026-10-06'")
add('C03_another_release_schema',"RELEASE_SCHEMA_NAME='R2D2_V2_RELEASE_V3'","RELEASE_SCHEMA_NAME='R2D2_V2_RELEASE_V2'")
add('C04_diagnostic_mode',"RELEASE_MODE='CERTIFIED'","RELEASE_MODE='DIAGNOSTIC'")
add('C05_new_york_day_begins_at_utc_midnight',"NEW_YORK_DAY_UTC=('2026-10-05T04:00:00+00:00',","NEW_YORK_DAY_UTC=('2026-10-05T00:00:00+00:00',")
add('C06_new_york_day_begins_on_standard_time',"NEW_YORK_DAY_UTC=('2026-10-05T04:00:00+00:00',","NEW_YORK_DAY_UTC=('2026-10-05T05:00:00+00:00',")
add('C07_new_york_day_ends_on_standard_time',"'2026-10-06T04:00:00+00:00')","'2026-10-06T05:00:00+00:00')")
add('C08_new_york_day_ends_an_hour_early',"'2026-10-06T04:00:00+00:00')","'2026-10-06T03:00:00+00:00')")
add('C09_another_volume',"DATA_VOLUME='/mnt/day-d-data'","DATA_VOLUME='/mnt/day-d'")
add('C10_release_directory_named_as_a_json_entry_of_the_guard',"RELEASE_DIRECTORY_NAME='r2d2-v2-release-20261005'","RELEASE_DIRECTORY_NAME='r2d2-v2-release-20261005.json'")
add('C11_release_directory_of_the_last_epoch',"RELEASE_DIRECTORY_NAME='r2d2-v2-release-20261005'","RELEASE_DIRECTORY_NAME='r2d2-v2-release-20260928'")
add('C12_another_file_name',"RELEASE_FILE_NAME='release.CERTIFIED.json'","RELEASE_FILE_NAME='release.json'")
add('C13_another_container_path',"CONTAINER_DATA_VOLUME='/app/day-d-data'","CONTAINER_DATA_VOLUME='/app/data'")
add('C14_another_pin_name',"MAINTENANCE_PIN_NAME='.r2d2-v2-pinned'","MAINTENANCE_PIN_NAME='.r2d2-v2-pin'")
add('C15_release_limit_is_the_document_limit',"MAX_RELEASE_BYTES=32768 ","MAX_RELEASE_BYTES=65536 ")
add('C16_release_limit_one_byte_less',"MAX_RELEASE_BYTES=32768 ","MAX_RELEASE_BYTES=32767 ")
add('C17_free_floor_one_byte_more',"FREE_BYTES_FLOOR=1048576 ","FREE_BYTES_FLOOR=1048577 ")
add('C18_free_floor_one_block_less',"FREE_BYTES_FLOOR=1048576 ","FREE_BYTES_FLOOR=1044480 ")
add('C19_allowance_one_second_less',"WRITE_ALLOWANCE_SECONDS=15 ","WRITE_ALLOWANCE_SECONDS=14 ")
add('C20_allowance_one_second_more',"WRITE_ALLOWANCE_SECONDS=15 ","WRITE_ALLOWANCE_SECONDS=16 ")
add('C21_date_class_of_every_session',"DATE_CLASS='WRITE_FIRST_SESSION'","DATE_CLASS='WRITE_SESSIONS'")
add('C22_date_class_of_the_whole_epoch',"DATE_CLASS='WRITE_FIRST_SESSION'","DATE_CLASS='WRITE_EPOCH'")
add('C23_no_evidence_operation_required',"EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,)","EVIDENCE_OPERATIONS=()")
add('C24_evidence_not_required',"EVIDENCE_REQUIRED=True","EVIDENCE_REQUIRED=False")
add('C25_gate_span_of_a_read',"MAX_GATE_SPAN_SECONDS=900","MAX_GATE_SPAN_SECONDS=3600")
add('C26_activation_allowed',"ACTIVATION_ALLOWED=False","ACTIVATION_ALLOWED=True")
add('C27_scope_says_a_process_is_started',"'processes_started':0,","'processes_started':1,")
add('C28_scope_never_list_loses_the_second_attempt',",'a second attempt'],","],")
add('C29_scope_loses_the_release_limit',"'release_bytes':MAX_RELEASE_BYTES,'free_bytes_floor'","'free_bytes_floor'")
add('C30_plan_has_one_more_member',"PLAN_KEYS=frozenset(('parent','release','evidence_boot_id_sha256'))","PLAN_KEYS=frozenset(('parent','release','evidence_boot_id_sha256','pin'))")

# ---------------------------------------------------------------- release_of: the bytes and their signed hash and size
KEYS="    need(type(item) is dict and set(item)==set(RELEASE_KEYS),'RELEASE_PLAN_INVALID')\n"
add('R01_release_member_keys_not_exact',KEYS,KEYS.replace("set(item)==set(RELEASE_KEYS)","set(item)>=set(RELEASE_KEYS)"),refusal='RELEASE_PLAN_INVALID')
add('R02_release_member_type_unchecked',KEYS,KEYS.replace("type(item) is dict and ",""))
PATH="    need(item['path']==RELEASE_PATH,'RELEASE_PATH_NOT_THE_SIGNED_CONSTANT')\n"
add('R03_release_path_unchecked',PATH,"",refusal='RELEASE_PATH_NOT_THE_SIGNED_CONSTANT')
add('R04_release_path_only_inside_the_volume',PATH,"    need(type(item['path']) is str and item['path'].startswith(DATA_VOLUME+'/'),'RELEASE_PATH_NOT_THE_SIGNED_CONSTANT')\n")
REQUEST="    need(file_request(RELEASE_FILE_NAME,item['sha256'],item['bytes'],PRIVATE_FILE_MODE) and item['bytes']<=MAX_RELEASE_BYTES,'RELEASE_PLAN_INVALID')\n"
add('R05_hash_and_size_grammar_unchecked',REQUEST,REQUEST.replace("file_request(RELEASE_FILE_NAME,item['sha256'],item['bytes'],PRIVATE_FILE_MODE) and ",""))
add('R06_release_size_limit_dropped',REQUEST,REQUEST.replace(" and item['bytes']<=MAX_RELEASE_BYTES",""))
TYPE="    need(type(item['content_b64']) is str,'RELEASE_BYTES_NOT_THE_SIGNED_HASH')\n"
add('R07_content_type_unchecked',TYPE,"")
add('R08_base64_decoded_leniently',"base64.b64decode(item['content_b64'].encode('ascii'),validate=True)","base64.b64decode(item['content_b64'].encode('ascii'),validate=False)")
BYTES="    need(len(raw)==item['bytes'] and sha(raw)==item['sha256'],'RELEASE_BYTES_NOT_THE_SIGNED_HASH')\n"
add('R09_size_of_the_bytes_not_compared',BYTES,BYTES.replace("len(raw)==item['bytes'] and ",""))
add('R10_hash_of_the_bytes_not_compared',BYTES,BYTES.replace(" and sha(raw)==item['sha256']",""),refusal='RELEASE_BYTES_NOT_THE_SIGNED_HASH')
add('R11_bytes_not_compared_at_all',BYTES,"")

# ---------------------------------------------------------------- release_facts: the scope of the release
JSON="    try:body=strict(raw)\n    except Refused:raise Refused('RELEASE_NOT_JSON') from None\n"
add('F01_release_decoded_with_duplicate_keys_and_nan',JSON,"    try:body=json.loads(raw)\n    except ValueError:raise Refused('RELEASE_NOT_JSON') from None\n",refusal='RELEASE_NOT_JSON')
add('F02_release_object_type_unchecked',"    need(type(body) is dict,'RELEASE_NOT_JSON')\n","")
SCHEMA="    need(body.get('schema')==RELEASE_SCHEMA_NAME and body.get('mode')==RELEASE_MODE,'RELEASE_NOT_A_CERTIFIED_V3_RELEASE')\n"
add('F03_release_schema_unchecked',SCHEMA,SCHEMA.replace("body.get('schema')==RELEASE_SCHEMA_NAME and ",""),refusal='RELEASE_NOT_A_CERTIFIED_V3_RELEASE')
add('F04_release_mode_unchecked',SCHEMA,SCHEMA.replace(" and body.get('mode')==RELEASE_MODE",""))
EPOCH="    need(body.get('epoch')==RELEASE_EPOCH,'RELEASE_EPOCH_NOT_THIS_EPOCH')\n"
add('F05_release_epoch_unchecked',EPOCH,"    need(type(body.get('epoch')) is str,'RELEASE_EPOCH_NOT_THIS_EPOCH')\n",refusal='RELEASE_EPOCH_NOT_THIS_EPOCH')
add('F06_release_epoch_by_namespace_only',EPOCH,"    need(type(body.get('epoch')) is str and body['epoch'].startswith('R2D2-V2-SHADOW-'),'RELEASE_EPOCH_NOT_THIS_EPOCH')\n")
add('F07_release_epoch_by_prefix',EPOCH,"    need(type(body.get('epoch')) is str and body['epoch'].startswith(RELEASE_EPOCH),'RELEASE_EPOCH_NOT_THIS_EPOCH')\n")
FIRST="    need(body.get('first_session')==FIRST_SESSION,'RELEASE_FIRST_SESSION_NOT_THIS_EPOCH')\n"
add('F08_release_first_session_unchecked',FIRST,"    need(type(body.get('first_session')) is str,'RELEASE_FIRST_SESSION_NOT_THIS_EPOCH')\n",refusal='RELEASE_FIRST_SESSION_NOT_THIS_EPOCH')
add('F09_release_revision_grammar_unchecked',"    need(text(body.get('code_revision'),'[0-9a-f]{40}') and hexpin(","    need(type(body.get('code_revision')) is str and hexpin(",refusal='RELEASE_FIELDS_INVALID')
add('F10_release_package_grammar_unchecked',"hexpin(body.get('implementation_package_sha'))\n","type(body.get('implementation_package_sha')) is str\n")
add('F12_release_revision_may_be_upper_case',"text(body.get('code_revision'),'[0-9a-f]{40}')","text(body.get('code_revision'),'[0-9a-fA-F]{40}')")
add('F13_release_revision_of_any_length',"text(body.get('code_revision'),'[0-9a-f]{40}')","text(body.get('code_revision'),'[0-9a-f]{1,64}')")
add('F14_release_approval_instant_of_any_length',"'[0-9T:.+Z-]{1,40}'","'[0-9T:.+Z-]{0,400}'")
add('F15_release_approval_instant_of_any_text',"'[0-9T:.+Z-]{1,40}'","'.{1,40}'")
add('F11_release_approval_instant_unchecked',"\n         and text(body.get('approved_at'),'[0-9T:.+Z-]{1,40}'),'RELEASE_FIELDS_INVALID')",",'RELEASE_FIELDS_INVALID')")

# ---------------------------------------------------------------- validate_plan
CHAIN="    validate_chain(plan['parent'],DATA_VOLUME,open_root=DATA_VOLUME,receives_entry=True)\n"
add('V01_parent_rows_not_validated',CHAIN,"")
add('V02_parent_rows_of_any_path',CHAIN,CHAIN.replace("plan['parent'],DATA_VOLUME,","plan['parent'],plan['parent'][-1]['path'],"))
add('V03_no_open_root',CHAIN,CHAIN.replace("open_root=DATA_VOLUME","open_root=None"))
add('V04_open_root_is_the_whole_host',CHAIN,CHAIN.replace("open_root=DATA_VOLUME","open_root='/mnt'"))
add('V05_setgid_parent_accepted',CHAIN,CHAIN.replace("receives_entry=True","receives_entry=False"))
MOUNT="    need(mount_point_of(plan['parent'])==DATA_VOLUME,'DATA_VOLUME_NOT_A_MOUNT_POINT')\n"
add('V06_volume_need_not_be_a_mount_point',MOUNT,"",refusal='DATA_VOLUME_NOT_A_MOUNT_POINT')
BOOT="    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')\n"
add('V07_evidence_boot_unbound_accepted',BOOT,"",refusal='EVIDENCE_BOOT_UNBOUND')
add('V08_release_not_judged_by_validate_plan',"    release_facts(release_of(plan))\n    need(instant(NEW_YORK_DAY_UTC[0])<=instant(plan['window']['not_before'])","    need(instant(NEW_YORK_DAY_UTC[0])<=instant(plan['window']['not_before'])")
WINDOW="    need(instant(NEW_YORK_DAY_UTC[0])<=instant(plan['window']['not_before']) and instant(plan['window']['expires_at'])<=instant(NEW_YORK_DAY_UTC[1]),\n"
add('V09_window_may_begin_before_the_new_york_day',WINDOW,WINDOW.replace("instant(NEW_YORK_DAY_UTC[0])<=instant(plan['window']['not_before']) and ",""),
    refusal='WINDOW_NOT_ON_THE_FIRST_SESSION_DAY_IN_NEW_YORK')
add('V10_window_may_end_after_the_new_york_day',WINDOW,WINDOW.replace(" and instant(plan['window']['expires_at'])<=instant(NEW_YORK_DAY_UTC[1])",""))
add('V11_window_begin_is_exclusive',WINDOW,WINDOW.replace("instant(NEW_YORK_DAY_UTC[0])<=instant(plan['window']['not_before'])","instant(NEW_YORK_DAY_UTC[0])<instant(plan['window']['not_before'])"))
add('V12_window_end_is_exclusive',WINDOW,WINDOW.replace("instant(plan['window']['expires_at'])<=instant(NEW_YORK_DAY_UTC[1])","instant(plan['window']['expires_at'])<instant(NEW_YORK_DAY_UTC[1])"))

# ---------------------------------------------------------------- effects_of: one per member
HEAD="    return {'operation':OPERATION,'parent':chain_effects(plan['parent']),'open_root':DATA_VOLUME,\n"
add('E01_effects_operation',HEAD,HEAD.replace("'operation':OPERATION","'operation':PHASE"),effect='operation')
add('E02_effects_parent_is_the_row_above',HEAD,HEAD.replace("chain_effects(plan['parent'])","chain_effects(plan['parent'][:-1])"),effect='parent')
add('E03_effects_open_root',HEAD,HEAD.replace("'open_root':DATA_VOLUME","'open_root':None"),effect='open_root')
DIRECTORY="            'directory':{'path':RELEASE_DIRECTORY,'mode_octal':'%04o'%PRIVATE_DIRECTORY_MODE,'uid':0,'gid':0,'expect':'ABSENT'},\n"
add('E04_effects_directory_path',DIRECTORY,DIRECTORY.replace("'path':RELEASE_DIRECTORY","'path':DATA_VOLUME"),effect='directory.path')
add('E05_effects_directory_mode',DIRECTORY,DIRECTORY.replace("'%04o'%PRIVATE_DIRECTORY_MODE","'0755'"),effect='directory.mode_octal')
add('E06_effects_directory_uid',DIRECTORY,DIRECTORY.replace("'uid':0","'uid':1000"),effect='directory.uid')
add('E07_effects_directory_gid',DIRECTORY,DIRECTORY.replace("'gid':0","'gid':1000"),effect='directory.gid')
add('E08_effects_directory_expectation',DIRECTORY,DIRECTORY.replace("'expect':'ABSENT'","'expect':'ANY'"),effect='directory.expect')
FILE1="            'file':{'path':RELEASE_PATH,'sha256':plan['release']['sha256'],'bytes':plan['release']['bytes'],\n"
add('E09_effects_file_path',FILE1,FILE1.replace("'path':RELEASE_PATH","'path':CONTAINER_RELEASE_PATH"),effect='file.path')
add('E10_effects_file_hash',FILE1,FILE1.replace("'sha256':plan['release']['sha256']","'sha256':plan['evidence_boot_id_sha256']"),effect='file.sha256')
add('E11_effects_file_size',FILE1,FILE1.replace("'bytes':plan['release']['bytes']","'bytes':MAX_RELEASE_BYTES"),effect='file.bytes')
FILE2="                    'mode_octal':'%04o'%PRIVATE_FILE_MODE,'uid':0,'gid':0,'links':1},\n"
add('E12_effects_file_mode',FILE2,FILE2.replace("'%04o'%PRIVATE_FILE_MODE","'0644'"),effect='file.mode_octal')
add('E13_effects_file_uid',FILE2,FILE2.replace("'uid':0","'uid':1000"),effect='file.uid')
add('E14_effects_file_gid',FILE2,FILE2.replace("'gid':0","'gid':1000"),effect='file.gid')
add('E15_effects_file_links',FILE2,FILE2.replace("'links':1","'links':2"),effect='file.links')
add('E16_effects_release_dropped',"            'release':release_facts(release_of(plan)),\n","            'release':None,\n")
FACTS1="    return {'schema':body['schema'],'mode':body['mode'],'epoch':body['epoch'],'first_session':body['first_session'],\n"
add('E17_effects_release_schema',FACTS1,FACTS1.replace("'schema':body['schema']","'schema':None"),effect='release.schema')
add('E18_effects_release_mode',FACTS1,FACTS1.replace("'mode':body['mode']","'mode':None"),effect='release.mode')
add('E19_effects_release_epoch',FACTS1,FACTS1.replace("'epoch':body['epoch']","'epoch':None"),effect='release.epoch')
add('E20_effects_release_first_session',FACTS1,FACTS1.replace("'first_session':body['first_session']","'first_session':None"),effect='release.first_session')
FACTS2="            'code_revision':body['code_revision'],'implementation_package_sha':body['implementation_package_sha'],'approved_at':body['approved_at']}\n"
add('E21_effects_release_revision',FACTS2,FACTS2.replace("'code_revision':body['code_revision']","'code_revision':None"),effect='release.code_revision')
add('E22_effects_release_package',FACTS2,FACTS2.replace("'implementation_package_sha':body['implementation_package_sha']","'implementation_package_sha':None"),effect='release.implementation_package_sha')
add('E23_effects_release_approval',FACTS2,FACTS2.replace("'approved_at':body['approved_at']","'approved_at':None"),effect='release.approved_at')
add('E24_effects_worker_path',"            'release_file_in_the_worker':CONTAINER_RELEASE_PATH,\n            'maintenance_pin'","            'release_file_in_the_worker':RELEASE_PATH,\n            'maintenance_pin'",effect='release_file_in_the_worker')
PIN="            'maintenance_pin':{'path':MAINTENANCE_PIN,'required':'PRESENT_REGULAR_ROOT_OWNED'},\n"
add('E25_effects_pin_path',PIN,PIN.replace("'path':MAINTENANCE_PIN","'path':DATA_VOLUME"),effect='maintenance_pin.path')
add('E26_effects_pin_requirement',PIN,PIN.replace("'PRESENT_REGULAR_ROOT_OWNED'","'PRESENT'"),effect='maintenance_pin.required')
add('E27_effects_new_york_day',"            'new_york_day_utc':list(NEW_YORK_DAY_UTC),\n            'evidence_boot_id_sha256'","            'new_york_day_utc':[],\n            'evidence_boot_id_sha256'",effect='new_york_day_utc')
add('E28_effects_evidence_boot',"            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],\n            'pre_existing_objects_modified'","            'evidence_boot_id_sha256':None,\n            'pre_existing_objects_modified'",effect='evidence_boot_id_sha256')
TAIL="            'pre_existing_objects_modified':False,'activation':False,'container_recreated':False,'process_started':False}\n"
add('E29_effects_pre_existing_objects',TAIL,TAIL.replace("'pre_existing_objects_modified':False","'pre_existing_objects_modified':True"),effect='pre_existing_objects_modified')
add('E30_effects_activation',TAIL,TAIL.replace("'activation':False","'activation':True"),effect='activation')
add('E31_effects_container_recreated',TAIL,TAIL.replace("'container_recreated':False","'container_recreated':True"),effect='container_recreated')
add('E32_effects_process_started',TAIL,TAIL.replace("'process_started':False","'process_started':True"),effect='process_started')

# ---------------------------------------------------------------- the precheck: every refusal, and the order
IDENTITY="            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n"
UMASK="            host.umask(0o077)\n"
DAY="            need(instant(NEW_YORK_DAY_UTC[0])<=clock()<instant(NEW_YORK_DAY_UTC[1]),'NOT_THE_FIRST_SESSION_DAY_IN_NEW_YORK')\n"
BOOTED="            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')\n"
add('P01_executor_identity_unchecked',IDENTITY+UMASK,UMASK,refusal='EXECUTOR_IDENTITY')
add('P02_executor_uid_only',IDENTITY+UMASK,IDENTITY.replace("tuple(host.identity())==(0,0)","host.identity()[0]==0")+UMASK)
add('P03_executor_gid_only',IDENTITY+UMASK,IDENTITY.replace("tuple(host.identity())==(0,0)","host.identity()[1]==0")+UMASK)
add('P04_umask_set_before_the_identity_is_known',IDENTITY+UMASK,UMASK+IDENTITY)
add('P05_umask_not_set',IDENTITY+UMASK+DAY,IDENTITY+DAY)
add('P06_umask_of_a_public_file',IDENTITY+UMASK+DAY,IDENTITY+UMASK.replace("0o077","0o022")+DAY)
add('P07_new_york_day_not_checked_by_the_run',UMASK+DAY+BOOTED,UMASK+BOOTED,refusal='NOT_THE_FIRST_SESSION_DAY_IN_NEW_YORK')
add('P08_new_york_day_begin_exclusive',UMASK+DAY+BOOTED,UMASK+DAY.replace("<=clock()<","<clock()<")+BOOTED)
add('P09_new_york_day_end_inclusive',UMASK+DAY+BOOTED,UMASK+DAY.replace("<=clock()<","<=clock()<=")+BOOTED)
add('P10_new_york_day_checked_after_the_host_is_read',UMASK+DAY+BOOTED,UMASK+BOOTED+DAY)
WALK="            parent=Pinned(host,walk_pinned(host,plan['parent'],gate,detail['parent']),rows=plan['parent']);pinned.append(parent)\n"
add('P11_boot_of_the_evidence_unchecked',DAY+BOOTED+WALK,DAY+WALK,refusal='EVIDENCE_FROM_EARLIER_BOOT')
add('P12_boot_checked_after_the_walk',DAY+BOOTED+WALK,DAY+WALK+BOOTED)
add('P13_walk_does_not_compare_the_device',WALK,WALK.replace("gate,detail['parent'])","gate,detail['parent'],False)"))
ABSENT="            need(pin is not None,'MAINTENANCE_PIN_ABSENT')\n"
REGULAR="            need(pin['type']=='file','MAINTENANCE_PIN_NOT_A_REGULAR_FILE')\n"
OWNED="            need((pin['uid'],pin['gid'])==(0,0),'MAINTENANCE_PIN_NOT_ROOT_OWNED')\n"
add('P14_pin_absence_not_refused',ABSENT+REGULAR,"            if pin is None:pin={'type':'file','uid':0,'gid':0}\n"+REGULAR,refusal='MAINTENANCE_PIN_ABSENT')
add('P15_pin_type_unchecked',ABSENT+REGULAR+OWNED,ABSENT+OWNED,refusal='MAINTENANCE_PIN_NOT_A_REGULAR_FILE')
add('P16_pin_may_be_a_symbolic_link',ABSENT+REGULAR+OWNED,ABSENT+REGULAR.replace("pin['type']=='file'","pin['type'] in ('file','symlink')")+OWNED)
add('P17_pin_may_be_anything_but_a_link',ABSENT+REGULAR+OWNED,ABSENT+REGULAR.replace("pin['type']=='file'","pin['type']!='symlink'")+OWNED)
add('P18_pin_owner_unchecked',REGULAR+OWNED,REGULAR,refusal='MAINTENANCE_PIN_NOT_ROOT_OWNED')
add('P19_pin_uid_only',REGULAR+OWNED,REGULAR+OWNED.replace("(pin['uid'],pin['gid'])==(0,0)","pin['uid']==0"))
add('P20_pin_gid_only',REGULAR+OWNED,REGULAR+OWNED.replace("(pin['uid'],pin['gid'])==(0,0)","pin['gid']==0"))
add('P21_pin_looked_up_under_the_release_name',"pin=entry_named(host,MAINTENANCE_PIN_NAME,parent,gate)","pin=entry_named(host,RELEASE_FILE_NAME,parent,gate)")
PRESENT="            need(found is None,'DESTINATION_PRESENT')\n"
add('P22_destination_presence_not_refused',PRESENT,"",refusal='DESTINATION_PRESENT')
add('P23_destination_looked_up_under_another_name',"found=entry_named(host,RELEASE_DIRECTORY_NAME,parent,gate)","found=entry_named(host,RELEASE_FILE_NAME,parent,gate)")
add('P24_destination_checked_before_the_pin',"            pin=entry_named(host,MAINTENANCE_PIN_NAME,parent,gate);detail['precheck']['maintenance_pin']=pin\n"+ABSENT+REGULAR+OWNED
    +"            found=entry_named(host,RELEASE_DIRECTORY_NAME,parent,gate);detail['precheck']['destination']={'exists':found is not None,'found':found}\n"+PRESENT,
    "            found=entry_named(host,RELEASE_DIRECTORY_NAME,parent,gate);detail['precheck']['destination']={'exists':found is not None,'found':found}\n"+PRESENT
    +"            pin=entry_named(host,MAINTENANCE_PIN_NAME,parent,gate);detail['precheck']['maintenance_pin']=pin\n"+ABSENT+REGULAR+OWNED)
FREE="            need(free>=FREE_BYTES_FLOOR,'DATA_VOLUME_FREE_SPACE_BELOW_FLOOR')\n"
add('P25_free_space_unchecked',FREE,"",refusal='DATA_VOLUME_FREE_SPACE_BELOW_FLOOR')
add('P26_free_space_floor_exclusive',FREE,FREE.replace("free>=FREE_BYTES_FLOOR","free>FREE_BYTES_FLOOR"))
BUDGET="            need(left>=WRITE_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')\n"
add('P27_budget_unchecked',BUDGET,"",refusal='BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
add('P28_budget_exclusive',BUDGET,BUDGET.replace("left>=WRITE_ALLOWANCE_SECONDS","left>WRITE_ALLOWANCE_SECONDS"))
add('P29_no_gate_before_the_two_lookups',"    gate()\n    try:info=host.lstat(name,parent.fd)\n","    try:info=host.lstat(name,parent.fd)\n")
add('P30_any_failed_lookup_is_an_absence',"    except FileNotFoundError:return None\n","    except OSError:return None\n",refusal='PRECHECK_OS_ERROR')
add('P31_no_gate_before_the_first_observation',"    gate()                                                    # first gate call: before anything is observed\n","")
add('P32_run_never_marked_started',"    state.started=True\n    detail={'parent':[],'precheck':{}}","    detail={'parent':[],'precheck':{}}")
CAUGHT="            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')\n"
add('P33_precheck_failure_has_one_code',CAUGHT,"            code=code_of(error,'PRECHECK_OS_ERROR')\n",refusal='PRECHECK_FAILED')
add('P34_precheck_refusal_reported_as_effects_phase',"{'phase_reached':'PRECHECK','installed':None}","{'phase_reached':'EFFECTS','installed':None}")
add('P36_precheck_refusal_reported_as_a_partial',"        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK','installed':None})\n",
    "        if code is not None:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,code,{'phase_reached':'PRECHECK','installed':None})\n")
add('P37_observed_parent_rows_not_in_the_receipt',WALK,WALK.replace("gate,detail['parent'])","gate,[])"))
add('P35_precheck_failure_goes_on_to_the_effects',"        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK','installed':None})\n","")

# ---------------------------------------------------------------- the effects and what the run does with each failure
MKDIR="        entry=create_directory('RELEASE_DIRECTORY',RELEASE_DIRECTORY,PRIVATE_DIRECTORY_MODE,parent,host,gate,state,handles);directories.append(entry)\n"
add('W01_directory_created_under_the_file_name',MKDIR,MKDIR.replace("'RELEASE_DIRECTORY',RELEASE_DIRECTORY,","'RELEASE_DIRECTORY',DATA_VOLUME+'/'+RELEASE_FILE_NAME,"))
STOP1="        if entry['state']!='CREATED_DURABLE':stop=entry['code'] or 'CREATION_FAILED'\n"
add('W02_a_directory_that_is_not_durable_is_used',STOP1,"        if entry['state'] not in ('CREATED_DURABLE','CREATED_NOT_DURABLE'):stop=entry['code'] or 'CREATION_FAILED'\n")
add('W03_a_directory_with_other_metadata_is_used',STOP1,"        if entry['state'] not in ('CREATED_DURABLE','CREATED_METADATA_MISMATCH'):stop=entry['code'] or 'CREATION_FAILED'\n")
add('W04_a_directory_that_is_not_empty_is_used',STOP1,"        if entry['state'] not in ('CREATED_DURABLE','CREATED_NOT_EMPTY'):stop=entry['code'] or 'CREATION_FAILED'\n")
CREATE="            row=create_file(0,'RELEASE',RELEASE_PATH,content,PRIVATE_FILE_MODE,handles['RELEASE_DIRECTORY'],host,gate,state,go16);ledger.append(row)\n"
add('W05_file_written_without_its_last_byte',CREATE,CREATE.replace("RELEASE_PATH,content,","RELEASE_PATH,content[:-1],"))
add('W06_file_written_public',CREATE,CREATE.replace("content,PRIVATE_FILE_MODE,","content,0o644,"))
add('W07_temporary_of_another_index',CREATE,CREATE.replace("create_file(0,","create_file(1,"))
add('W08_temporary_keyed_by_the_request',"    go16=bound['go_sha256'][:16]\n","    go16=bound['request_sha256'][:16]\n")
STOP2="            if row['state']!='INSTALLED_DURABLE':stop=row['code'] or 'INSTALL_FAILED'\n"
add('W09_a_file_that_is_not_durable_counts_as_installed',STOP2,"            if row['state'] not in ('INSTALLED_DURABLE','INSTALLED_NOT_DURABLE'):stop=row['code'] or 'INSTALL_FAILED'\n")
add('W10_a_file_whose_temporary_remains_counts_as_installed',STOP2,"            if row['state'] not in ('INSTALLED_DURABLE','LINKED_TEMPORARY_PRESENT'):stop=row['code'] or 'INSTALL_FAILED'\n")
add('W11_a_failed_install_goes_on_to_the_readback',STOP2,"")
READ1="        if stop is None:stop=readback_file(row,content,PRIVATE_FILE_MODE,handles['RELEASE_DIRECTORY'],host,gate)\n"
add('W12_bytes_not_read_back',READ1,"        if stop is None:row['sha256_observed']=row['sha256_signed']\n")
READ2="        if stop is None:stop=readback_directory(RELEASE_DIRECTORY,PRIVATE_DIRECTORY_MODE,handles['RELEASE_DIRECTORY'],host,gate,1)\n"
add('W13_directory_not_read_back',READ2,"")
add('W14_directory_may_hold_a_second_entry',READ2,READ2.replace("host,gate,1)","host,gate,2)"))
READ3="        if stop is None:\n            try:parent.verify(gate)\n            except Exception as error:stop=code_of(error,'READBACK_UNAVAILABLE')\n"
add('W15_parent_not_verified_at_the_end',READ3,"")
add('W16_complete_whatever_the_readback_says',"        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)\n","        if True:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)\n")
CLEAN="        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n"
add('W17_a_run_that_changed_the_host_is_a_refusal',CLEAN,"        if True:return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n")
add('W18_a_run_that_changed_nothing_is_a_partial',CLEAN,"")
# (Not a mutant: state.clean() replaced by state.succeeded==0. An uncertain call is one whose action raised something
# other than OSError, and that exception leaves perform(); no path returns normally with an uncertain call and nothing
# succeeded, so the two conditions are the same here. The core's run() decides that case, and the core's list covers it.)
CLOSE="        for handle in list(handles.values())+pinned:\n"
add('W20_created_directory_left_open',CLOSE,"        for handle in pinned:\n")
add('W21_parent_left_open',CLOSE,"        for handle in list(handles.values()):\n")
add('W22_objects_left_counts_files_only',"objects_left_by_this_run=objects_left(directories,ledger),","objects_left_by_this_run=objects_left([],ledger),")
add('W23_receipt_says_existing_objects_were_modified',"            pre_existing_objects_modified=False,**extra)))\n","            pre_existing_objects_modified=True,**extra)))\n")
add('W24_installed_summary_given_for_a_run_that_stopped',"        installed=None\n        if stop is None:\n","        installed=None\n        if stop is None or state.succeeded>=5:\n")
add('W25_installed_summary_says_the_application_verified',"'verified_with_the_application':False}","'verified_with_the_application':True}")
add('W26_installed_summary_names_the_host_path_for_the_worker',"installed={'path':RELEASE_PATH,'release_file_in_the_worker':CONTAINER_RELEASE_PATH,","installed={'path':RELEASE_PATH,'release_file_in_the_worker':RELEASE_PATH,")
add('W27_readback_reported_complete_when_it_stopped',"'readback':'COMPLETE' if stop is None else None,","'readback':'COMPLETE',")
add('W28_receipt_reductions_lose_the_first_step',"REDUCTIONS=[('PRECHECK_DROPPED',_reduce_precheck),('PARENT_REDUCED_TO_COUNT',_reduce_parent)]","REDUCTIONS=[('PARENT_REDUCED_TO_COUNT',_reduce_parent)]")
add('W29_receipt_reductions_lose_the_second_step',"REDUCTIONS=[('PRECHECK_DROPPED',_reduce_precheck),('PARENT_REDUCED_TO_COUNT',_reduce_parent)]","REDUCTIONS=[('PRECHECK_DROPPED',_reduce_precheck)]")
add('W31_effects_phase_reported_as_the_precheck',"        extra={'phase_reached':'EFFECTS',","        extra={'phase_reached':'PRECHECK',")
add('W32_a_partial_reported_with_the_complete_status',"        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)\n","        return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,stop,extra)\n")
add('W33_file_written_even_when_the_directory_failed',"        if stop is None:\n            row=create_file(0,","        if True:\n            row=create_file(0,")
add('W30_success_criterion_is_the_partial_outcome',"def success_of(plan):return COMPLETE_OUTCOME\n","def success_of(plan):return PARTIAL_OUTCOME\n")
REFUSALS.setdefault('READBACK_UNAVAILABLE','W15_parent_not_verified_at_the_end')

# ---------------------------------------------------------------- the dispatcher generated for this operation
# Three rows of the core's list are anchored on the date literal of its demonstration operations; these are the same
# three for the literal of this operation, ('2026-10-05',), and one more for the day after.
DISPATCHER=[
    ('D02k_dispatcher_one_day_rule_dropped','dispatcher',"',) and end.date()==start.date(),'DISPATCH_DATE')\n","',),'DISPATCH_DATE')\n"),
    ('D71k_dispatcher_date_set_dropped','dispatcher',"need(start.date().isoformat() in ('2026-10-05',) and end.date()==start.date(),'DISPATCH_DATE')","need(end.date()==start.date(),'DISPATCH_DATE')"),
    ('D72k_dispatcher_accepts_the_sunday_before','dispatcher',"start.date().isoformat() in ('2026-10-05',)","start.date().isoformat() in ('2026-10-04','2026-10-05')"),
    ('D73k_dispatcher_accepts_the_second_session_day','dispatcher',"start.date().isoformat() in ('2026-10-05',)","start.date().isoformat() in ('2026-10-05','2026-10-06')"),
]
CORE_ROWS_REPLACED=('D02_dispatcher_one_day_rule_dropped','D71_write_dispatcher_date_set_dropped','D72_write_dispatcher_accepts_friday_the_second')

MUTANTS=M+DISPATCHER
COMBOS={}
REDUNDANT={}


# ---------------------------------------------------------------- the two tables against the source itself
def _load(path):
    raw=Path(path).read_bytes();name='_hostops02_k10_mutation_'+hashlib.sha256(raw).hexdigest()[:12]
    module=type(sys)(name);module.__dict__['__file__']='<assembled install_release.py>';sys.modules[name]=module
    exec(compile(raw,module.__dict__['__file__'],'exec'),module.__dict__);return module

def _members(value,prefix=''):
    out=[]
    for key in sorted(value):
        if type(value[key]) is dict and key!='parent':out+=_members(value[key],prefix+key+'.')
        else:out.append(prefix+key)
    return out

def codes_of(text):
    """Every constant code the operation part can raise: the code of each need(), each Refused() and each code_of() fallback."""
    found=set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in ('need','Refused','code_of'):
            for argument in node.args:
                for item in ast.walk(argument):
                    if isinstance(item,ast.Constant) and type(item.value) is str and re.fullmatch('[A-Z][A-Z0-9_]{2,79}',item.value):found.add(item.value)
    return found

def coverage(here):
    """Errors when a member of effects_of() or a refusal of the operation part has no mutant named for it."""
    here=Path(here);errors=[];names={row[0] for row in M};module=_load(here/'build'/'install_release.py')
    raw=(here/'tests'/'fixtures'/'release.SYNTHETIC.json').read_bytes()
    rows=[{'path':'/','device':1,'inode':2,'uid':0,'gid':0,'mode':0o755},{'path':'/mnt','device':1,'inode':3,'uid':0,'gid':0,'mode':0o755},
          {'path':'/mnt/day-d-data','device':2,'inode':2,'uid':1000,'gid':1000,'mode':0o755}]
    plan={'parent':rows,'evidence_boot_id_sha256':'a'*64,
          'release':{'path':module.RELEASE_PATH,'content_b64':base64.b64encode(raw).decode('ascii'),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}}
    members=_members(module.effects_of(plan))
    for member in members:
        if EFFECTS.get(member) not in names:errors.append('effects member without a mutant: '+member)
    for member in EFFECTS:
        if member not in members:errors.append('mutant table names an effects member that does not exist: '+member)
    codes=codes_of((here/'op.py').read_text())-{'CREATION_FAILED','INSTALL_FAILED'}        # fallbacks for a ledger row without a code: the parts always give one
    for code in sorted(codes):
        if REFUSALS.get(code) not in names:errors.append('refusal without a mutant: '+code)
    for code in REFUSALS:
        if code not in codes:errors.append('mutant table names a refusal that does not exist: '+code)
    return errors
