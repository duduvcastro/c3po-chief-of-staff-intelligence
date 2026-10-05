"""The mutants of K4-E0's own part. Each row: (name, target, exact anchor, replacement); target 'op' is the built source
build/k4_e0.py, in which the anchor must occur exactly once (mutate.py check). The rule of the family: one mutant per
member of effects_of(), one per refusal of validate_plan and of the precheck; here also the constants of the epoch and
of the placement, the order of the precheck, and what the run does with each failure of an effect.
EFFECTS and REFUSALS name, for each member and each code, the mutant that answers for it; coverage() compares both
tables with the source itself (the members effects_of() returns, the codes the operation part can raise), so a new
member or a new refusal without a mutant is an error of `mutate.py check`. Modelled on install_release's list."""
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

# ---------------------------------------------------------------- the constants of the epoch and of the placement
add('C01_another_epoch',"E0_EPOCH='R2D2-V2-SHADOW-2026-10-05'","E0_EPOCH='R2D2-V2-SHADOW-2026-09-28'")
add('C02_another_var_lib',"VAR_LIB='/var/lib'","VAR_LIB='/var/cache'")
add('C03_source_root_of_the_last_epoch',"SOURCE_ROOT_NAME='r2d2-v2-source-20261005'","SOURCE_ROOT_NAME='r2d2-v2-source'")
add('C04_source_root_named_as_a_json_entry_of_the_guard',"SOURCE_ROOT_NAME='r2d2-v2-source-20261005'","SOURCE_ROOT_NAME='r2d2-v2-release-20261005.json'")
add('C05_k9_root_is_the_source_root',"K9_ROOT_NAME='r2d2-v2-k9-20261005'","K9_ROOT_NAME='r2d2-v2-source-20261005'")
add('C06_k9_root_of_another_day',"K9_ROOT_NAME='r2d2-v2-k9-20261005'","K9_ROOT_NAME='r2d2-v2-k9-20261006'")
add('C07_tools_under_another_name',"TOOLS_DIRECTORY=K9_ROOT+'/tools'","TOOLS_DIRECTORY=K9_ROOT+'/tool'")
add('C08_k9_root_expects_three_entries',"                ('K9_ROOT',K9_ROOT,'VAR_LIB_C3PO',4),","                ('K9_ROOT',K9_ROOT,'VAR_LIB_C3PO',3),")
add('C09_tools_expects_no_entry',"                ('K9_TOOLS',TOOLS_DIRECTORY,'K9_ROOT',1),","                ('K9_TOOLS',TOOLS_DIRECTORY,'K9_ROOT',0),")
add('C10_days_created_in_the_c3po_directory',"                ('K9_DAYS',K9_ROOT+'/days','K9_ROOT',0),","                ('K9_DAYS',C3PO_DIRECTORY+'/days','VAR_LIB_C3PO',0),")
add('C11_claims_not_created',"                ('K9_CLAIMS',K9_ROOT+'/claims','K9_ROOT',0),\n","")
add('C12_secrets_named_secret',"                ('K9_SECRETS',K9_ROOT+'/secrets','K9_ROOT',0))","                ('K9_SECRETS',K9_ROOT+'/secret','K9_ROOT',0))")
add('C13_source_root_created_in_var_lib',"E0_DIRECTORIES=(('SOURCE_ROOT',SOURCE_ROOT,'VAR_LIB_C3PO',0),","E0_DIRECTORIES=(('SOURCE_ROOT',VAR_LIB+'/'+SOURCE_ROOT_NAME,'VAR_LIB',0),")
add('C14_source_root_expects_an_entry',"E0_DIRECTORIES=(('SOURCE_ROOT',SOURCE_ROOT,'VAR_LIB_C3PO',0),","E0_DIRECTORIES=(('SOURCE_ROOT',SOURCE_ROOT,'VAR_LIB_C3PO',1),")
add('C14b_source_root_inside_the_k9_root',"SOURCE_ROOT=C3PO_DIRECTORY+'/'+SOURCE_ROOT_NAME","SOURCE_ROOT=C3PO_DIRECTORY+'/'+K9_ROOT_NAME+'/'+SOURCE_ROOT_NAME")
add('C15_runner_name_not_content_addressed',"def runner_name(digest):return RUNNER_STEM+digest+RUNNER_EXTENSION","def runner_name(digest):return RUNNER_STEM[:-1]+RUNNER_EXTENSION")
add('C16_runner_stem_without_the_dash',"RUNNER_STEM='k9_runner-'","RUNNER_STEM='k9_runner_'")
add('C17_runner_extension',"RUNNER_EXTENSION='.py'","RUNNER_EXTENSION='.pyc'")
add('C18_container_tools_directory',"CONTAINER_TOOLS_DIRECTORY='/c3po-k9-tools'","CONTAINER_TOOLS_DIRECTORY='/c3po-k9-tool'")
add('C20_runner_limit_is_the_document_limit',"MAX_RUNNER_BYTES=40960 ","MAX_RUNNER_BYTES=65536 ")
add('C21_runner_limit_one_byte_less',"MAX_RUNNER_BYTES=40960 ","MAX_RUNNER_BYTES=40959 ")
add('C23b_floor_one_byte_more',"FREE_BYTES_FLOOR=214748364800\n","FREE_BYTES_FLOOR=214748364801\n")
add('C23c_floor_one_block_less',"FREE_BYTES_FLOOR=214748364800\n","FREE_BYTES_FLOOR=214748360704\n")
add('C23d_floor_of_one_mib',"FREE_BYTES_FLOOR=214748364800\n","FREE_BYTES_FLOOR=1048576\n")
add('C23e_floor_in_gb_not_gib',"FREE_BYTES_FLOOR=214748364800\n","FREE_BYTES_FLOOR=200000000000\n")
add('C24_allowance_one_second_less',"WRITE_ALLOWANCE_SECONDS=15 ","WRITE_ALLOWANCE_SECONDS=14 ")
add('C25_allowance_one_second_more',"WRITE_ALLOWANCE_SECONDS=15 ","WRITE_ALLOWANCE_SECONDS=16 ")
add('C26_date_class_of_the_first_session_only',"DATE_CLASS='WRITE_SESSIONS'","DATE_CLASS='WRITE_FIRST_SESSION'")
add('C27_date_class_of_the_whole_epoch',"DATE_CLASS='WRITE_SESSIONS'","DATE_CLASS='WRITE_EPOCH'")
add('C28_no_evidence_operation_required',"EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,)","EVIDENCE_OPERATIONS=()")
add('C29_evidence_not_required',"EVIDENCE_REQUIRED=True","EVIDENCE_REQUIRED=False")
add('C30_gate_span_of_a_read',"MAX_GATE_SPAN_SECONDS=900","MAX_GATE_SPAN_SECONDS=3600")
add('C31_activation_allowed',"ACTIVATION_ALLOWED=False","ACTIVATION_ALLOWED=True")
add('C32_scope_says_a_process_is_started',"'processes_started':0,","'processes_started':1,")
add('C33_scope_never_list_loses_the_second_attempt',",'a container','a second attempt'],",",'a container'],")
add('C34_scope_loses_the_runner_limit',"'runner_bytes':MAX_RUNNER_BYTES,'free_bytes_floor'","'free_bytes_floor'")
add('C34b_scope_loses_the_floor',"'free_bytes_floor':FREE_BYTES_FLOOR,'write_allowance_seconds'","'write_allowance_seconds'")
add('C35_scope_placement_with_an_open_root',"'k9_root':K9_ROOT,'open_root':None},","'k9_root':K9_ROOT,'open_root':VAR_LIB},")
add('C36_plan_has_one_more_member',"PLAN_KEYS=frozenset(('parent','runner','evidence_boot_id_sha256'))","PLAN_KEYS=frozenset(('parent','runner','evidence_boot_id_sha256','c3po'))")
add('C38_c3po_directory_under_another_name',"C3PO_NAME='c3po'","C3PO_NAME='c3po-k9'")
add('C39_c3po_created_expects_one_entry',"C3PO_ENTRIES_IF_CREATED=2","C3PO_ENTRIES_IF_CREATED=1")
add('C40_scope_never_list_loses_a_secret',"'a network connection','a secret','activation',","'a network connection','activation',")
add('C41_scope_space_measured_on_var_lib_only',"'space':{'free_bytes_floor':FREE_BYTES_FLOOR,'measured_on':SPACE_MEASURED_ON},\n       'files'","'space':{'free_bytes_floor':FREE_BYTES_FLOOR,'measured_on':VAR_LIB},\n       'files'")

# ---------------------------------------------------------------- runner_of: the bytes, their signed hash and size, their name
KEYS="    need(type(item) is dict and set(item)==set(RUNNER_KEYS),'RUNNER_PLAN_INVALID')\n"
add('R01_runner_member_keys_not_exact',KEYS,KEYS.replace("set(item)==set(RUNNER_KEYS)","set(item)>=set(RUNNER_KEYS)"),refusal='RUNNER_PLAN_INVALID')
add('R02_runner_member_type_unchecked',KEYS,KEYS.replace("type(item) is dict and ",""))
REQUEST="    need(file_request(RUNNER_STEM+'x'+RUNNER_EXTENSION,item['sha256'],item['bytes'],PRIVATE_FILE_MODE) and item['bytes']<=MAX_RUNNER_BYTES,'RUNNER_PLAN_INVALID')\n"
add('R03_hash_and_size_grammar_unchecked',REQUEST,REQUEST.replace("file_request(RUNNER_STEM+'x'+RUNNER_EXTENSION,item['sha256'],item['bytes'],PRIVATE_FILE_MODE) and ","type(item['bytes']) is int and "))
add('R04_runner_size_limit_dropped',REQUEST,REQUEST.replace(" and item['bytes']<=MAX_RUNNER_BYTES",""))
PATH="    need(item['path']==TOOLS_DIRECTORY+'/'+runner_name(item['sha256']),'RUNNER_PATH_NOT_CONTENT_ADDRESSED')\n"
add('R05_runner_path_unchecked',PATH,"",refusal='RUNNER_PATH_NOT_CONTENT_ADDRESSED')
add('R06_runner_path_only_inside_the_tools_directory',PATH,"    need(type(item['path']) is str and item['path'].startswith(TOOLS_DIRECTORY+'/'),'RUNNER_PATH_NOT_CONTENT_ADDRESSED')\n")
add('R07_runner_path_only_by_its_name',PATH,"    need(type(item['path']) is str and item['path'].endswith('/'+runner_name(item['sha256'])),'RUNNER_PATH_NOT_CONTENT_ADDRESSED')\n")
TYPE="    need(type(item['content_b64']) is str,'RUNNER_BYTES_NOT_THE_SIGNED_HASH')\n"
add('R08_content_type_unchecked',TYPE,"")
add('R09_base64_decoded_leniently',"base64.b64decode(item['content_b64'].encode('ascii'),validate=True)","base64.b64decode(item['content_b64'].encode('ascii'),validate=False)")
BYTES="    need(len(raw)==item['bytes'] and sha(raw)==item['sha256'],'RUNNER_BYTES_NOT_THE_SIGNED_HASH')\n"
add('R10_size_of_the_bytes_not_compared',BYTES,BYTES.replace("len(raw)==item['bytes'] and ",""))
add('R11_hash_of_the_bytes_not_compared',BYTES,BYTES.replace(" and sha(raw)==item['sha256']",""),refusal='RUNNER_BYTES_NOT_THE_SIGNED_HASH')
add('R12_bytes_not_compared_at_all',BYTES,"")

# ---------------------------------------------------------------- validate_plan
CHAIN="    validate_chain(plan['parent'],VAR_LIB,open_root=None,receives_entry=True)\n"
add('V01_rows_not_validated',CHAIN,"")
add('V02_rows_of_any_path',CHAIN,CHAIN.replace("plan['parent'],VAR_LIB,","plan['parent'],plan['parent'][-1]['path'],"))
add('V03_chain_with_an_open_root',CHAIN,CHAIN.replace("open_root=None","open_root=VAR_LIB"))
add('V04_chain_open_from_var',CHAIN,CHAIN.replace("open_root=None","open_root='/var'"))
add('V05_setgid_var_lib_accepted_by_the_chain_rule',CHAIN+"    need(all(root_controlled(row) for row in plan['parent']),'CHAIN_NOT_ROOT_CONTROLLED')\n",CHAIN.replace("receives_entry=True","receives_entry=False"))
ROOTED="    need(all(root_controlled(row) for row in plan['parent']),'CHAIN_NOT_ROOT_CONTROLLED')\n"
add('V12_chain_not_judged_beyond_the_chain_rule',ROOTED,"",refusal='CHAIN_NOT_ROOT_CONTROLLED')
add('V13_only_the_last_row_judged',ROOTED,ROOTED.replace("for row in plan['parent']","for row in plan['parent'][-1:]"))
add('V13b_the_root_row_not_judged',ROOTED,ROOTED.replace("for row in plan['parent']","for row in plan['parent'][1:]"))
RC="    return row['gid']==0 and not row['mode']&stat.S_ISGID\n"
add('V14_root_controlled_without_the_group',RC,RC.replace("row['gid']==0 and ",""))
add('V17_root_controlled_accepts_setgid',RC,RC.replace(" and not row['mode']&stat.S_ISGID",""))
# (Not mutants: uid 0 and no group/other write in root_controlled; validate_chain(open_root=None) refuses both first.)
BOOT="    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')\n"
add('V18_evidence_boot_unbound_accepted',BOOT,"",refusal='EVIDENCE_BOOT_UNBOUND')
add('V19_runner_not_judged_by_validate_plan',"    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')\n    runner_of(plan)\n",
    "    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')\n")

# ---------------------------------------------------------------- effects_of: one per member
HEAD="    return {'operation':OPERATION,'epoch':E0_EPOCH,\n"
add('E01_effects_operation',HEAD,HEAD.replace("'operation':OPERATION","'operation':PHASE"),effect='operation')
add('E02_effects_epoch',HEAD,HEAD.replace("'epoch':E0_EPOCH","'epoch':None"),effect='epoch')
PAR="            'parent':chain_effects(plan['parent']),'open_root':None,\n"
add('E03_effects_parent_is_the_row_above',PAR,PAR.replace("chain_effects(plan['parent'])","chain_effects(plan['parent'][:-1])"),effect='parent')
add('E04_effects_open_root',PAR,PAR.replace("'open_root':None","'open_root':VAR_LIB"),effect='open_root')
C3E="            'c3po_directory':{'path':C3PO_DIRECTORY,'if_absent':C3PO_IF_ABSENT,'if_present':C3PO_IF_PRESENT},\n"
add('E05c_effects_c3po_path',C3E,C3E.replace("'path':C3PO_DIRECTORY","'path':VAR_LIB"),effect='c3po_directory.path')
ABS="C3PO_IF_ABSENT={'action':'CREATE','mode_octal':'%04o'%PRIVATE_DIRECTORY_MODE,'uid':0,'gid':0,'entries_after':C3PO_ENTRIES_IF_CREATED}"
add('E05d_effects_c3po_if_absent_action',ABS,ABS.replace("'action':'CREATE'","'action':'NONE'"),effect='c3po_directory.if_absent.action')
add('E05e_effects_c3po_if_absent_mode',ABS,ABS.replace("'%04o'%PRIVATE_DIRECTORY_MODE","'0755'"),effect='c3po_directory.if_absent.mode_octal')
add('E05f_effects_c3po_if_absent_uid',ABS,ABS.replace("'uid':0","'uid':1000"),effect='c3po_directory.if_absent.uid')
add('E05g_effects_c3po_if_absent_gid',ABS,ABS.replace("'gid':0","'gid':1000"),effect='c3po_directory.if_absent.gid')
add('E05h_effects_c3po_if_absent_entries',ABS,ABS.replace("'entries_after':C3PO_ENTRIES_IF_CREATED","'entries_after':0"),effect='c3po_directory.if_absent.entries_after')
add('E05i_effects_c3po_if_present_action',"C3PO_IF_PRESENT={'action':'USE_UNCHANGED',","C3PO_IF_PRESENT={'action':'USE',",effect='c3po_directory.if_present.action')
add('E05j_effects_c3po_if_present_requirement',"'require':'DIRECTORY_NOT_A_LINK_UID_0_GID_0_NOT_GROUP_OR_OTHER_WRITABLE_NOT_SETGID_SAME_DEVICE_AS_VAR_LIB',","'require':'DIRECTORY_NOT_A_LINK_UID_0_GID_0_NOT_GROUP_OR_OTHER_WRITABLE_NOT_SETGID',",
    effect='c3po_directory.if_present.require')
add('E05k_effects_c3po_if_present_identity',"'identity':'RECORDED_IN_THE_RECEIPT_AND_HELD_UNCHANGED_TO_THE_END'}","'identity':'NOT_RECORDED'}",effect='c3po_directory.if_present.identity')
DIRECTORY="            'directories':{key:{'path':path,'mode_octal':'%04o'%PRIVATE_DIRECTORY_MODE,'uid':0,'gid':0,'expect':'ABSENT','entries_after':entries}\n"
add('E06_effects_directory_path',DIRECTORY,DIRECTORY.replace("'path':path","'path':VAR_LIB"),effect='directories.*.path')
add('E07_effects_directory_mode',DIRECTORY,DIRECTORY.replace("'%04o'%PRIVATE_DIRECTORY_MODE","'0755'"),effect='directories.*.mode_octal')
add('E08_effects_directory_uid',DIRECTORY,DIRECTORY.replace("'uid':0","'uid':1000"),effect='directories.*.uid')
add('E09_effects_directory_gid',DIRECTORY,DIRECTORY.replace("'gid':0","'gid':1000"),effect='directories.*.gid')
add('E10_effects_directory_expectation',DIRECTORY,DIRECTORY.replace("'expect':'ABSENT'","'expect':'ANY'"),effect='directories.*.expect')
add('E11_effects_directory_entries',DIRECTORY,DIRECTORY.replace("'entries_after':entries","'entries_after':0"),effect='directories.*.entries_after')
add('E12_effects_directory_keys',"                           for key,path,_,entries in E0_DIRECTORIES},","                           for key,path,_,entries in E0_DIRECTORIES[:5]},",
    effect=['directories.SOURCE_ROOT','directories.K9_ROOT','directories.K9_TOOLS','directories.K9_DAYS','directories.K9_CLAIMS','directories.K9_SECRETS'])
RUNNER1="            'runner':{'path':TOOLS_DIRECTORY+'/'+runner_name(digest),'sha256':digest,'bytes':plan['runner']['bytes'],\n"
add('E13_effects_runner_path',RUNNER1,RUNNER1.replace("'path':TOOLS_DIRECTORY+'/'+runner_name(digest)","'path':K9_ROOT+'/'+runner_name(digest)"),effect='runner.path')
add('E14_effects_runner_hash',RUNNER1,RUNNER1.replace("'sha256':digest","'sha256':plan['evidence_boot_id_sha256']"),effect='runner.sha256')
add('E15_effects_runner_size',RUNNER1,RUNNER1.replace("'bytes':plan['runner']['bytes']","'bytes':MAX_RUNNER_BYTES"),effect='runner.bytes')
RUNNER2="                      'mode_octal':'%04o'%PRIVATE_FILE_MODE,'uid':0,'gid':0,'links':1,\n"
add('E16_effects_runner_mode',RUNNER2,RUNNER2.replace("'%04o'%PRIVATE_FILE_MODE","'0644'"),effect='runner.mode_octal')
add('E17_effects_runner_uid',RUNNER2,RUNNER2.replace("'uid':0","'uid':1000"),effect='runner.uid')
add('E18_effects_runner_gid',RUNNER2,RUNNER2.replace("'gid':0","'gid':1000"),effect='runner.gid')
add('E19_effects_runner_links',RUNNER2,RUNNER2.replace("'links':1","'links':2"),effect='runner.links')
add('E20_effects_runner_path_in_containers',"                      'path_in_k9_containers':CONTAINER_TOOLS_DIRECTORY+'/'+runner_name(digest)},\n",
    "                      'path_in_k9_containers':TOOLS_DIRECTORY+'/'+runner_name(digest)},\n",effect='runner.path_in_k9_containers')
SPACE="            'space':{'free_bytes_floor':FREE_BYTES_FLOOR,'measured_on':SPACE_MEASURED_ON},\n            'evidence_boot_id_sha256'"
add('E21_effects_space_floor',SPACE,SPACE.replace("'free_bytes_floor':FREE_BYTES_FLOOR","'free_bytes_floor':1048576"),effect='space.free_bytes_floor')
add('E22_effects_space_measured_on',SPACE,SPACE.replace("'measured_on':SPACE_MEASURED_ON","'measured_on':VAR_LIB"),effect='space.measured_on')
add('E23_effects_evidence_boot',"            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],\n            'pre_existing_objects_modified'",
    "            'evidence_boot_id_sha256':None,\n            'pre_existing_objects_modified'",effect='evidence_boot_id_sha256')
TAIL="            'pre_existing_objects_modified':False,'secret_written':False,'activation':False,'container_touched':False,'process_started':False}\n"
add('E24_effects_pre_existing_objects',TAIL,TAIL.replace("'pre_existing_objects_modified':False","'pre_existing_objects_modified':True"),effect='pre_existing_objects_modified')
add('E25_effects_secret_written',TAIL,TAIL.replace("'secret_written':False","'secret_written':True"),effect='secret_written')
add('E26_effects_activation',TAIL,TAIL.replace("'activation':False","'activation':True"),effect='activation')
add('E27_effects_container_touched',TAIL,TAIL.replace("'container_touched':False","'container_touched':True"),effect='container_touched')
add('E28_effects_process_started',TAIL,TAIL.replace("'process_started':False","'process_started':True"),effect='process_started')

# ---------------------------------------------------------------- the precheck: every refusal, and the order
IDENTITY="            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n"
UMASK="            host.umask(0o077)\n"
BOOTED="            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')\n"
add('P01_executor_identity_unchecked',IDENTITY+UMASK,UMASK,refusal='EXECUTOR_IDENTITY')
add('P02_executor_uid_only',IDENTITY+UMASK,IDENTITY.replace("tuple(host.identity())==(0,0)","host.identity()[0]==0")+UMASK)
add('P03_executor_gid_only',IDENTITY+UMASK,IDENTITY.replace("tuple(host.identity())==(0,0)","host.identity()[1]==0")+UMASK)
add('P04_umask_set_before_the_identity_is_known',IDENTITY+UMASK,UMASK+IDENTITY)
add('P05_umask_not_set',IDENTITY+UMASK+BOOTED,IDENTITY+BOOTED)
add('P06_umask_of_a_public_file',IDENTITY+UMASK+BOOTED,IDENTITY+UMASK.replace("0o077","0o022")+BOOTED)
WALK="            var_lib=Pinned(host,walk_pinned(host,plan['parent'],gate,detail['parent']),rows=plan['parent']);pinned.append(var_lib)\n"
add('P07_boot_of_the_evidence_unchecked',UMASK+BOOTED+WALK,UMASK+WALK,refusal='EVIDENCE_FROM_EARLIER_BOOT')
add('P08_boot_checked_after_the_walk',UMASK+BOOTED+WALK,UMASK+WALK+BOOTED)
add('P09_walk_does_not_compare_the_device',WALK,WALK.replace("gate,detail['parent'])","gate,detail['parent'],False)"))
add('P10_observed_rows_not_in_the_receipt',WALK,WALK.replace("gate,detail['parent'])","gate,[])"))
add('P10e_parent_not_verified_at_the_end',WALK,WALK.replace(";pinned.append(var_lib)",""))
C3LOOK="            found=entry_named(host,C3PO_NAME,var_lib,gate);c3po['found']=found;c3po['state']='ABSENT' if found is None else 'PRESENT'\n"
add('P24_c3po_looked_up_under_another_name',C3LOOK,C3LOOK.replace("entry_named(host,C3PO_NAME,","entry_named(host,'docker',"))
add('P24b_c3po_presence_ignored',"            if found is not None:\n                need(found['type']=='dir'","            if False:\n                need(found['type']=='dir'")
C3DIR="                need(found['type']=='dir','C3PO_DIRECTORY_NOT_A_DIRECTORY')\n"
add('P24c_c3po_type_unchecked',C3DIR,"",refusal='C3PO_DIRECTORY_NOT_A_DIRECTORY')
add('P24d_c3po_may_be_a_link',C3DIR,C3DIR.replace("found['type']=='dir'","found['type'] in ('dir','symlink')"))
C3OWN="                need((found['uid'],found['gid'])==(0,0),'C3PO_DIRECTORY_NOT_ROOT_OWNED')\n"
add('P24e_c3po_owner_unchecked',C3OWN,"",refusal='C3PO_DIRECTORY_NOT_ROOT_OWNED')
add('P24f_c3po_uid_only',C3OWN,C3OWN.replace("(found['uid'],found['gid'])==(0,0)","found['uid']==0"))
add('P24g_c3po_gid_only',C3OWN,C3OWN.replace("(found['uid'],found['gid'])==(0,0)","found['gid']==0"))
C3W="                need(not int(found['mode_octal'],8)&0o022,'C3PO_DIRECTORY_WRITABLE_BY_GROUP_OR_OTHER')\n"
add('P24h_c3po_writability_unchecked',C3W,"",refusal='C3PO_DIRECTORY_WRITABLE_BY_GROUP_OR_OTHER')
add('P24i_c3po_group_write_accepted',C3W,C3W.replace("0o022","0o002"))
add('P24j_c3po_other_write_accepted',C3W,C3W.replace("0o022","0o020"))
C3G="                need(not int(found['mode_octal'],8)&stat.S_ISGID,'C3PO_DIRECTORY_SETGID')\n"
add('P24k_c3po_setgid_accepted',C3G,"",refusal='C3PO_DIRECTORY_SETGID')
C3DEV="                need(found['device']==var_lib.identity[0],'C3PO_DIRECTORY_ON_ANOTHER_FILESYSTEM')\n"
add('P24t_c3po_device_unchecked',C3DEV,"",refusal='C3PO_DIRECTORY_ON_ANOTHER_FILESYSTEM')
add('P24u_c3po_device_compared_with_its_own',C3DEV,C3DEV.replace("var_lib.identity[0]","found['device']"))
HOLD="                handles['VAR_LIB_C3PO']=hold_existing(host,C3PO_NAME,var_lib,found,gate)\n"
add('P24l_c3po_held_under_another_key',HOLD,HOLD.replace("handles['VAR_LIB_C3PO']=","handles['C3PO']=")+"                handles['VAR_LIB_C3PO']=var_lib\n")
HOLD2="    if held.identity[:2]!=(found['device'],found['inode']) or held.identity[2:]!=(found['uid'],found['gid'],int(found['mode_octal'],8)):\n"
add('P24m_held_c3po_identity_not_compared',HOLD2,"    if False:\n",refusal='C3PO_DIRECTORY_CHANGED_DURING_PRECHECK')
add('P24n_held_c3po_owner_and_mode_not_compared',HOLD2,HOLD2.replace(" or held.identity[2:]!=(found['uid'],found['gid'],int(found['mode_octal'],8))",""))
add('P24o_held_c3po_opened_following_links',"    try:fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=parent.fd)\n",
    "    try:fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|host.noatime(),dir_fd=parent.fd)\n")
add('P24p_no_gate_before_the_open_of_c3po',"    gate()\n    try:fd=host.open(name,","    try:fd=host.open(name,")
add('P24q_c3po_identity_not_recorded',C3LOOK,C3LOOK.replace("c3po['found']=found;",""))
add('P24r_c3po_state_not_recorded',C3LOOK,C3LOOK.replace(";c3po['state']='ABSENT' if found is None else 'PRESENT'",""))
add('P24s_c3po_state_inverted',C3LOOK,C3LOOK.replace("'ABSENT' if found is None else 'PRESENT'","'PRESENT' if found is None else 'ABSENT'"))
SOURCE_LOOK="                found=entry_named(host,SOURCE_ROOT_NAME,handles['VAR_LIB_C3PO'],gate);detail['precheck']['source_root']={'exists':found is not None,'found':found}\n"
SOURCE_NEED="                need(found is None,'SOURCE_ROOT_PRESENT')\n"
K9_LOOK="                found=entry_named(host,K9_ROOT_NAME,handles['VAR_LIB_C3PO'],gate);detail['precheck']['k9_root']={'exists':found is not None,'found':found}\n"
K9_NEED="                need(found is None,'K9_ROOT_PRESENT')\n"
add('P19_source_root_presence_not_refused',SOURCE_NEED,"",refusal='SOURCE_ROOT_PRESENT')
add('P20_k9_root_presence_not_refused',K9_NEED,"",refusal='K9_ROOT_PRESENT')
add('P21_source_root_looked_up_under_the_k9_name',SOURCE_LOOK,SOURCE_LOOK.replace("entry_named(host,SOURCE_ROOT_NAME,","entry_named(host,K9_ROOT_NAME,"))
add('P22_k9_root_looked_up_under_the_source_name',K9_LOOK,K9_LOOK.replace("entry_named(host,K9_ROOT_NAME,","entry_named(host,SOURCE_ROOT_NAME,"))
add('P22b_roots_looked_up_in_var_lib',SOURCE_LOOK+SOURCE_NEED+K9_LOOK,
    SOURCE_LOOK.replace("handles['VAR_LIB_C3PO']","var_lib")+SOURCE_NEED+K9_LOOK.replace("handles['VAR_LIB_C3PO']","var_lib"))
add('P23_k9_root_checked_before_the_source_root',SOURCE_LOOK+SOURCE_NEED+K9_LOOK+K9_NEED,K9_LOOK+K9_NEED+SOURCE_LOOK+SOURCE_NEED)
FREE="            need(free>=FREE_BYTES_FLOOR,'FREE_SPACE_BELOW_FLOOR')\n"
add('P25_free_space_unchecked',FREE,"",refusal='FREE_SPACE_BELOW_FLOOR')
add('P26_free_space_floor_exclusive',FREE,FREE.replace("free>=FREE_BYTES_FLOOR","free>FREE_BYTES_FLOOR"))
add('P26d_free_space_always_measured_on_var_lib',"            space=handles.get('VAR_LIB_C3PO',var_lib)\n","            space=var_lib\n")
add('P26e_measured_on_not_recorded',"            detail['precheck']['free_bytes_measured_on']=C3PO_DIRECTORY if 'VAR_LIB_C3PO' in handles else VAR_LIB\n","")
BUDGET="            need(left>=WRITE_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')\n"
add('P27_budget_unchecked',BUDGET,"",refusal='BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
add('P28_budget_exclusive',BUDGET,BUDGET.replace("left>=WRITE_ALLOWANCE_SECONDS","left>WRITE_ALLOWANCE_SECONDS"))
add('P29_no_gate_before_the_lookups',"    gate()\n    try:info=host.lstat(name,parent.fd)\n","    try:info=host.lstat(name,parent.fd)\n")
add('P30_any_failed_lookup_is_an_absence',"    except FileNotFoundError:return None\n","    except OSError:return None\n",refusal='PRECHECK_OS_ERROR')
add('P31_no_gate_before_the_first_observation',"    gate()                                                    # first gate call: before anything is observed\n","")
add('P32_run_never_marked_started',"    state.started=True\n    detail=","    detail=")
CAUGHT="            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')\n"
add('P33_precheck_failure_has_one_code',CAUGHT,"            code=code_of(error,'PRECHECK_OS_ERROR')\n",refusal='PRECHECK_FAILED')
REFUSE="        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK','delivered':None})\n"
add('P34_precheck_refusal_reported_as_effects_phase',REFUSE,REFUSE.replace("'phase_reached':'PRECHECK'","'phase_reached':'EFFECTS'"))
add('P35_precheck_failure_goes_on_to_the_effects',REFUSE,"")
add('P36_precheck_refusal_reported_as_a_partial',REFUSE,REFUSE.replace("finish(REFUSED_STATUS,REFUSED_OUTCOME,","finish(PARTIAL_STATUS,PARTIAL_OUTCOME,"))

# ---------------------------------------------------------------- the effects and what the run does with each failure
add('W01_every_directory_created_in_c3po',"PRIVATE_DIRECTORY_MODE,handles[holder],host,gate,state,handles)",
    "PRIVATE_DIRECTORY_MODE,handles.get('VAR_LIB_C3PO',handles.get('VAR_LIB')),host,gate,state,handles)")
INSERT="        if 'VAR_LIB_C3PO' not in handles:\n            table.insert(0,('VAR_LIB_C3PO',C3PO_DIRECTORY,'VAR_LIB',C3PO_ENTRIES_IF_CREATED));handles['VAR_LIB']=var_lib\n"
add('W01b_c3po_never_created',INSERT,"        handles['VAR_LIB_C3PO']=var_lib\n")
add('W01c_c3po_created_after_the_source_root',INSERT,INSERT.replace("table.insert(0,","table.insert(1,"))
add('W01d_c3po_created_even_when_present',"        if 'VAR_LIB_C3PO' not in handles:\n","        if True:\n")
add('W01e_created_flag_never_set',"            elif key=='VAR_LIB_C3PO':c3po['created']=True\n","")
STOP1="            if entry['state']!='CREATED_DURABLE':stop=entry['code'] or 'CREATION_FAILED'\n"
add('W02_a_directory_that_is_not_durable_is_used',STOP1,"            if entry['state'] not in ('CREATED_DURABLE','CREATED_NOT_DURABLE'):stop=entry['code'] or 'CREATION_FAILED'\n")
add('W03_a_directory_with_other_metadata_is_used',STOP1,"            if entry['state'] not in ('CREATED_DURABLE','CREATED_METADATA_MISMATCH'):stop=entry['code'] or 'CREATION_FAILED'\n")
add('W04_a_directory_that_is_not_empty_is_used',STOP1,"            if entry['state'] not in ('CREATED_DURABLE','CREATED_NOT_EMPTY'):stop=entry['code'] or 'CREATION_FAILED'\n")
add('W05_a_failed_directory_does_not_stop_the_next',STOP1,"            if False:pass\n")
SKIP="            if stop is not None:\n                directories.append({'key':key,'path':path,'state':'NOT_ATTEMPTED','code':None});continue\n"
add('W06_directories_after_a_stop_are_not_listed',SKIP,"            if stop is not None:continue\n")
CREATE="            row=create_file(0,'K9_RUNNER',runner_path,content,PRIVATE_FILE_MODE,handles['K9_TOOLS'],host,gate,state,go16);ledger.append(row)\n"
add('W07_runner_written_without_its_last_byte',CREATE,CREATE.replace("runner_path,content,","runner_path,content[:-1],"))
add('W08_runner_written_public',CREATE,CREATE.replace("content,PRIVATE_FILE_MODE,","content,0o644,"))
add('W09_temporary_of_another_index',CREATE,CREATE.replace("create_file(0,","create_file(1,"))
add('W10_runner_written_into_the_k9_root',CREATE,CREATE.replace("handles['K9_TOOLS'],host,gate,state,go16)","handles['K9_ROOT'],host,gate,state,go16)"))
add('W11_temporary_keyed_by_the_request',"    go16=bound['go_sha256'][:16]\n","    go16=bound['request_sha256'][:16]\n")
add('W12_runner_path_not_content_addressed',"    runner_path=TOOLS_DIRECTORY+'/'+runner_name(plan['runner']['sha256'])\n","    runner_path=TOOLS_DIRECTORY+'/k9_runner.py'\n")
STOP2="            if row['state']!='INSTALLED_DURABLE':stop=row['code'] or 'INSTALL_FAILED'\n"
add('W13_a_runner_that_is_not_durable_counts_as_delivered',STOP2,"            if row['state'] not in ('INSTALLED_DURABLE','INSTALLED_NOT_DURABLE'):stop=row['code'] or 'INSTALL_FAILED'\n")
add('W14_a_runner_whose_temporary_remains_counts_as_delivered',STOP2,"            if row['state'] not in ('INSTALLED_DURABLE','LINKED_TEMPORARY_PRESENT'):stop=row['code'] or 'INSTALL_FAILED'\n")
add('W15_a_failed_delivery_goes_on_to_the_readback',STOP2,"")
add('W16_runner_written_even_when_a_directory_failed',"        if stop is None:\n            row=create_file(0,","        if True:\n            row=create_file(0,")
READ1="        if stop is None:stop=readback_file(row,content,PRIVATE_FILE_MODE,handles['K9_TOOLS'],host,gate)\n"
add('W17_bytes_not_read_back',READ1,"        if stop is None:row['sha256_observed']=row['sha256_signed']\n")
READ2="            if stop is None:stop=readback_directory(path,PRIVATE_DIRECTORY_MODE,handles[key],host,gate,entries)\n"
add('W18_directories_not_read_back',READ2,"            pass\n")
add('W19_directories_may_hold_one_more_entry',READ2,READ2.replace("host,gate,entries)","host,gate,entries+1)"))
add('W20_only_the_first_directory_read_back',"        for key,path,_,entries in table:\n            if stop is None:stop=readback_directory(",
    "        for key,path,_,entries in table[:1]:\n            if stop is None:stop=readback_directory(")
READ3="        for held in pinned:\n            if stop is None:\n                try:held.verify(gate)\n"
add('W21_parents_not_verified_at_the_end',READ3,"        for held in []:\n            if stop is None:\n                try:held.verify(gate)\n")
READ4="        if stop is None and not c3po['created']:\n            try:handles['VAR_LIB_C3PO'].verify(gate)\n"
add('W21b_existing_c3po_not_verified_at_the_end',READ4,"        if False:\n            try:handles['VAR_LIB_C3PO'].verify(gate)\n")
add('W22_complete_whatever_the_readback_says',"        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)\n","        if True:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)\n")
CLEAN="        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n"
add('W23_a_run_that_changed_the_host_is_a_refusal',CLEAN,"        if True:return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n")
add('W24_a_run_that_changed_nothing_is_a_partial',CLEAN,"")
add('W25_created_directories_left_open',"            if key!='VAR_LIB':\n                try:handle.close()","            if False:\n                try:handle.close()")
add('W26_parents_left_open',"        for handle in pinned:\n            try:handle.close()","        for handle in []:\n            try:handle.close()")
add('W26b_delivered_says_c3po_was_created',"'created_by_this_run':c3po['created'],","'created_by_this_run':True,")
add('W27_objects_left_counts_files_only',"objects_left_by_this_run=objects_left(directories,ledger),","objects_left_by_this_run=objects_left([],ledger),")
add('W28_receipt_says_existing_objects_were_modified',"            pre_existing_objects_modified=False,**extra)))\n","            pre_existing_objects_modified=True,**extra)))\n")
add('W29_delivered_summary_given_for_a_run_that_stopped',"        delivered=None\n        if stop is None:\n","        delivered=None\n        if stop is None or state.succeeded>=11:\n")
add('W30_delivered_summary_names_the_host_path_for_containers',"'path_in_k9_containers':CONTAINER_TOOLS_DIRECTORY+'/'+runner_name(row['sha256_observed']),",
    "'path_in_k9_containers':runner_path,")
# (Not a mutant: 'sha256':row['sha256_signed'] in the delivered summary. That summary exists only when readback_file()
# returned None, which it does only when the bytes read equal the signed bytes; the observed and the signed hash are
# then the same string. Run once on 2026-10-04 as W31 and recorded here as equivalent: it survived, as it must.)
add('W32_readback_reported_complete_when_it_stopped',"'readback':'COMPLETE' if stop is None else None,","'readback':'COMPLETE',")
add('W33_receipt_reductions_lose_the_first_step',"REDUCTIONS=[('PRECHECK_DROPPED',_reduce_precheck),('PARENT_REDUCED_TO_COUNT',_reduce_parent)]","REDUCTIONS=[('PARENT_REDUCED_TO_COUNT',_reduce_parent)]")
add('W34_receipt_reductions_lose_the_second_step',"REDUCTIONS=[('PRECHECK_DROPPED',_reduce_precheck),('PARENT_REDUCED_TO_COUNT',_reduce_parent)]","REDUCTIONS=[('PRECHECK_DROPPED',_reduce_precheck)]")
add('W35_effects_phase_reported_as_the_precheck',"        extra={'phase_reached':'EFFECTS',","        extra={'phase_reached':'PRECHECK',")
add('W36_a_partial_reported_with_the_complete_status',"        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)\n","        return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,stop,extra)\n")
add('W37_success_criterion_is_the_partial_outcome',"def success_of(plan):return COMPLETE_OUTCOME\n","def success_of(plan):return PARTIAL_OUTCOME\n")
REFUSALS.setdefault('READBACK_UNAVAILABLE','W21_parents_not_verified_at_the_end')

# ---------------------------------------------------------------- the dispatcher generated for this operation
# Two rows of the core's list are anchored on the date literal of its demonstration write operation (WRITE_EPOCH);
# these are the same two for the literal of this operation (WRITE_SESSIONS), and one more for the day after.
LITERAL="('2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09','2026-10-10')"
DISPATCHER=[
    ('D71k_dispatcher_date_set_dropped','dispatcher',"need(start.date().isoformat() in "+LITERAL+" and end.date()==start.date(),'DISPATCH_DATE')","need(end.date()==start.date(),'DISPATCH_DATE')"),
    ('D72k_dispatcher_accepts_the_sunday_before','dispatcher',"start.date().isoformat() in ('2026-10-05',","start.date().isoformat() in ('2026-10-04','2026-10-05',"),
    ('D73k_dispatcher_accepts_the_day_after_the_epoch','dispatcher',"'2026-10-09','2026-10-10') and end.date()==start.date()","'2026-10-09','2026-10-10','2026-10-11') and end.date()==start.date()"),
]
CORE_ROWS_REPLACED=('D71_write_dispatcher_date_set_dropped','D72_write_dispatcher_accepts_friday_the_second')

MUTANTS=M+DISPATCHER
COMBOS={}
REDUNDANT={}


# ---------------------------------------------------------------- the two tables against the source itself
def _load(path):
    raw=Path(path).read_bytes();name='_hostops02_k4e0_mutation_'+hashlib.sha256(raw).hexdigest()[:12]
    module=type(sys)(name);module.__dict__['__file__']='<assembled k4_e0.py>';sys.modules[name]=module
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
    """Errors when a member of effects_of() or a refusal of the operation part has no mutant named for it. A member of
    one directory row is answered by the mutant of its template ('directories.*.<member>'); the presence of each row by
    the mutant that drops one ('directories.<KEY>')."""
    here=Path(here);errors=[];names={row[0] for row in M};module=_load(here/'build'/'k4_e0.py')
    raw=b'# synthetic\n'
    rows=[{'path':'/','device':1,'inode':2,'uid':0,'gid':0,'mode':0o755},{'path':'/mnt','device':1,'inode':3,'uid':0,'gid':0,'mode':0o755},
          {'path':'/mnt/day-d-data','device':2,'inode':2,'uid':1000,'gid':1000,'mode':0o755}]
    digest=hashlib.sha256(raw).hexdigest()
    k9_rows=[{'path':'/','device':1,'inode':2,'uid':0,'gid':0,'mode':0o755},{'path':'/var','device':1,'inode':4,'uid':0,'gid':0,'mode':0o755},
             {'path':'/var/lib','device':1,'inode':5,'uid':0,'gid':0,'mode':0o755}]
    plan={'parent':k9_rows,'evidence_boot_id_sha256':'a'*64,
          'runner':{'path':module.TOOLS_DIRECTORY+'/'+module.runner_name(digest),'content_b64':base64.b64encode(raw).decode('ascii'),'sha256':digest,'bytes':len(raw)}}
    members=_members(module.effects_of(plan));keys=set(module.effects_of(plan)['directories'])
    wanted=set()
    for member in members:
        parts=member.split('.')
        if parts[0]=='directories':wanted|={'directories.'+parts[1],'directories.*.'+parts[2]}
        else:wanted.add(member)
    for member in sorted(wanted):
        if EFFECTS.get(member) not in names:errors.append('effects member without a mutant: '+member)
    for member in EFFECTS:
        if member not in wanted:errors.append('mutant table names an effects member that does not exist: '+member)
    if keys!={'SOURCE_ROOT','K9_ROOT','K9_TOOLS','K9_DAYS','K9_CLAIMS','K9_SECRETS'}:errors.append('directory keys changed: %s'%sorted(keys))
    codes=codes_of((here/'op.py').read_text())-{'CREATION_FAILED','INSTALL_FAILED'}        # fallbacks for a ledger row without a code: the parts always give one
    for code in sorted(codes):
        if REFUSALS.get(code) not in names:errors.append('refusal without a mutant: '+code)
    for code in REFUSALS:
        if code not in codes:errors.append('mutant table names a refusal that does not exist: '+code)
    return errors
