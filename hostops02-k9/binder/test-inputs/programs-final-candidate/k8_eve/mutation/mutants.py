"""The mutants of K8's own part. Each row: (name, target, exact anchor, replacement); target 'op' is the built source
build/k8_eve.py, in which the anchor must occur exactly once (mutate.py check). The rule of the family: one mutant per
member of effects_of(), one per refusal of validate_plan and of the precheck; here also the constants of the epoch, of
the capacity tree and of the K9 tree, the order of the precheck, what the run does with each failure of an effect, what
the receipt withholds, and the core's own mutants of create_file ported to K8's copy of it (k8copy.port).
EFFECTS and REFUSALS name, for each member and each code, the mutant that answers for it; coverage() compares both
tables with the source itself (the members effects_of() returns, the codes the operation part can raise outside the
copy), so a new member or a new refusal without a mutant is an error of `mutate.py check`. Modelled on K4-E0's list."""
import ast
import base64
import hashlib
import importlib.util
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

# ---------------------------------------------------------------- constants of the epoch, the days and the eve
add('C01_another_epoch',"K8_EPOCH='R2D2-V2-SHADOW-2026-10-05'","K8_EPOCH='R2D2-V2-SHADOW-2026-09-28'",effect='epoch')
add('C02_monday_has_an_eve',"K8_EVES={'2026-10-06':'2026-10-05',","K8_EVES={'2026-10-05':'2026-10-04','2026-10-06':'2026-10-05',")
add('C03_thursday_has_no_eve',"'2026-10-08':'2026-10-07','2026-10-09':'2026-10-08'}","'2026-10-08':'2026-10-07'}")
add('C04_the_eve_of_tuesday_is_tuesday',"K8_EVES={'2026-10-06':'2026-10-05',","K8_EVES={'2026-10-06':'2026-10-06',",effect='eve.not_before')
add('C05_eve_from_one_hour_earlier',"K8_EVE_FROM='T20:00:00+00:00'","K8_EVE_FROM='T19:00:00+00:00'")
add('C06_eve_until_the_first_window',"K8_EVE_UNTIL='T09:00:00+00:00'","K8_EVE_UNTIL='T10:38:00+00:00'",effect='eve.not_after')
add('C07_another_package',"K8_PACKAGE='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'","K8_PACKAGE='a9305a11544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'")
add('C08_another_revision',"K8_REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'","K8_REVISION='4de7095b8dab4d8b0372b0f9eabc90bf6443e858'")
add('C09_another_var_lib',"K8_VAR_LIB='/var/lib'","K8_VAR_LIB='/var/cache'",effect='capacity_tree.parent')
add('C10_capacity_tree_of_the_reader',"K8_CAPACITY_NAME='c3po-capacity'","K8_CAPACITY_NAME='c3po-reader'",effect='capacity_tree.path')
add('C11_config_root_not_held',"K8_CAPACITY_ROOTS=('config','documents','go','payload')","K8_CAPACITY_ROOTS=('documents','go','payload')",effect='capacity_tree.roots')
add('C12_go_root_not_compared',"K8_IDENTITY_ROOTS=('documents','go','payload')","K8_IDENTITY_ROOTS=('documents','payload')")
add('C13_container_path_of_the_host',"K8_CONTAINER_CAPACITY='/c3po-capacity'","K8_CONTAINER_CAPACITY='/var/lib/c3po-capacity'",effect='capacity_tree.container_path')
add('C14_k9_root_of_another_epoch',"K8_K9_ROOT='/var/lib/c3po/r2d2-v2-k9-20261005'","K8_K9_ROOT='/var/lib/c3po/r2d2-v2-k9-20260928'",effect='k9_inputs.day_directory')
add('C15_k9_days_under_another_name',"K8_K9_DAYS=K8_K9_ROOT+'/days'","K8_K9_DAYS=K8_K9_ROOT+'/day'")
add('C16_causal_directory_name',"K8_CAUSAL='causal'","K8_CAUSAL='causal_list'",effect='k9_inputs.commitment')
add('C17_receipts_directory_name',"K8_RECEIPTS='receipts'","K8_RECEIPTS='receipt'",effect='k9_inputs.commit_receipt')
add('C18_commitment_file_name',"K8_COMMITMENT='commitment.private.json'","K8_COMMITMENT='commitment.json'")
add('C19_audit_file_name',"K8_AUDIT='build_audit_receipt.json'","K8_AUDIT='audit_receipt.json'",effect='k9_inputs.audit_receipt')
add('C20_receipt_of_the_publish_step',"K8_COMMIT_RECEIPT='commit_launch.RECEIPT.json'","K8_COMMIT_RECEIPT='publish_launch.RECEIPT.json'")
add('C21_receipt_outputs_named_from_the_source_root',"K8_COMMIT_OUTPUTS=('day/causal/'+K8_COMMITMENT,'day/causal/'+K8_AUDIT)","K8_COMMIT_OUTPUTS=('source/causal/'+K8_COMMITMENT,'day/causal/'+K8_AUDIT)")
add('C22_receipt_member_set_without_aggregates',"'completed_at','package_sha256','build_sha','outputs','aggregates','counts'))","'completed_at','package_sha256','build_sha','outputs','counts'))")
add('C23_commitment_schema',"K8_COMMITMENT_SCHEMA='V2_CAUSAL_LIST_COMMITMENT_V1'","K8_COMMITMENT_SCHEMA='V2_CAUSAL_LIST_COMMITMENT_V2'")
add('C24_audit_event_of_the_publication',"K8_BUILT_EVENT='r2d2.v2.causal_list_built'","K8_BUILT_EVENT='r2d2.v2.causal_list_published'")
add('C25_audit_member_set',"K8_AUDIT_KEYS=frozenset(('event_id','event_type','occurred_at','payload'))","K8_AUDIT_KEYS=frozenset(('event_type','occurred_at','payload'))")
add('C26_capacity_one_less',"K8_CAPACITY=550","K8_CAPACITY=549")
add('C27_capacity_one_more',"K8_CAPACITY=550","K8_CAPACITY=551")
add('C28_symbol_grammar_lowercase',"K8_SYMBOL='[A-Z0-9][A-Z0-9.-]{0,19}'","K8_SYMBOL='[A-Za-z0-9][A-Za-z0-9.-]{0,19}'")
add('C29_one_chain_role_not_read',"K8_CHAIN_ROLES=('CODEX','FABLE','DUDU','ACT_B','B_CODEX','B_FABLE','B_DUDU')","K8_CHAIN_ROLES=('CODEX','FABLE','DUDU','ACT_B','B_CODEX','B_FABLE')")
add('C30_template_pin_of_the_publication',"K8_RECORD_PINS=(('template','TEMPLATE'),","K8_RECORD_PINS=(('template','PUBLICATION:bar_manifest'),")
add('C31_go_files_phases_swapped',"K8_GO_FILES=(('go_admission','admission'),('go_bar_manifest','bar_manifest'))","K8_GO_FILES=(('go_admission','bar_manifest'),('go_bar_manifest','admission'))")
add('C32_contract_keys_without_the_policy',"K8_CONTRACT_KEYS=frozenset(('assembler_plan','policy','order',","K8_CONTRACT_KEYS=frozenset(('assembler_plan','order',")
add('C33_window_names_with_a_dot',"K8_WINDOW_NAME='[a-z][a-z0-9_]{0,31}'","K8_WINDOW_NAME='[a-z][a-z0-9_.]{0,31}'")
add('C34_four_windows',"K8_MAX_WINDOWS=3 ","K8_MAX_WINDOWS=4 ")
add('C35_two_windows',"K8_MAX_WINDOWS=3 ","K8_MAX_WINDOWS=2 ")
add('C36_file_names_of_monday',"K8_FILE_NAME='session=2026-10-0[6-9][.][a-z][A-Za-z0-9._-]{0,99}'","K8_FILE_NAME='session=2026-10-0[5-9][.][a-z][A-Za-z0-9._-]{0,99}'")
add('C37_file_names_without_the_session_prefix',"K8_FILE_NAME='session=2026-10-0[6-9][.][a-z][A-Za-z0-9._-]{0,99}'","K8_FILE_NAME='[A-Za-z0-9=][A-Za-z0-9._=-]{0,127}'")
add('C38_chain_names_with_an_equal_sign',"K8_CHAIN_FILE_NAME='[A-Za-z0-9][A-Za-z0-9._-]{0,127}'","K8_CHAIN_FILE_NAME='[A-Za-z0-9][A-Za-z0-9._=-]{0,127}'")
add('C38b_chain_names_with_a_slash',"K8_CHAIN_FILE_NAME='[A-Za-z0-9][A-Za-z0-9._-]{0,127}'","K8_CHAIN_FILE_NAME='[A-Za-z0-9][A-Za-z0-9._/-]{0,127}'")
add('C39_identity_rule_with_a_third_value',"K8_IDENTITY_RULES=('REFUSE_ON_MISMATCH','REPORT_ONLY')","K8_IDENTITY_RULES=('REFUSE_ON_MISMATCH','REPORT_ONLY','REFUSE')")
add('C40_delivery_limit_one_byte_less',"K8_DELIVERY_MAX_BYTES=40960 ","K8_DELIVERY_MAX_BYTES=40959 ")
add('C41_delivery_limit_one_byte_more',"K8_DELIVERY_MAX_BYTES=40960 ","K8_DELIVERY_MAX_BYTES=40961 ")
add('C42_receipt_limit_small',"K8_RECEIPT_MAX_BYTES=262144 ","K8_RECEIPT_MAX_BYTES=512 ")
add('C43_commitment_limit_small',"K8_COMMITMENT_MAX_BYTES=67108864 ","K8_COMMITMENT_MAX_BYTES=4096 ")
add('C44_audit_limit_small',"K8_AUDIT_MAX_BYTES=65536","K8_AUDIT_MAX_BYTES=256")
add('C45_chain_limit_small',"K8_CHAIN_MAX_BYTES=1048576","K8_CHAIN_MAX_BYTES=1024")
add('C46_free_floor_one_block_more',"K8_FREE_BYTES_FLOOR=4194304 ","K8_FREE_BYTES_FLOOR=4198400 ")
add('C47_free_floor_one_block_less',"K8_FREE_BYTES_FLOOR=4194304 ","K8_FREE_BYTES_FLOOR=4190208 ")
add('C48_allowance_one_second_less',"K8_WRITE_ALLOWANCE_SECONDS=15 ","K8_WRITE_ALLOWANCE_SECONDS=14 ")
add('C49_allowance_one_second_more',"K8_WRITE_ALLOWANCE_SECONDS=15 ","K8_WRITE_ALLOWANCE_SECONDS=16 ")
add('C50_files_readable_by_the_group',"K8_FILE_MODE=0o600","K8_FILE_MODE=0o640")
add('C51_directories_open_to_the_group',"K8_DIRECTORY_MODE=0o700","K8_DIRECTORY_MODE=0o750")
add('C52_date_class_of_the_first_session',"DATE_CLASS='WRITE_SESSIONS'","DATE_CLASS='WRITE_FIRST_SESSION'")
add('C53_date_class_of_the_whole_epoch',"DATE_CLASS='WRITE_SESSIONS'","DATE_CLASS='WRITE_EPOCH'")
add('C54_evidence_of_the_precheck',"EVIDENCE_OPERATIONS=('GO_READONLY_HOSTOPS02_K9_PHASE_READ_01',)","EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,)")
add('C55_no_evidence_operation',"EVIDENCE_OPERATIONS=('GO_READONLY_HOSTOPS02_K9_PHASE_READ_01',)","EVIDENCE_OPERATIONS=()")
add('C56_gate_span_of_a_read',"MAX_GATE_SPAN_SECONDS=900","MAX_GATE_SPAN_SECONDS=3600")
add('C57_activation_allowed',"ACTIVATION_ALLOWED=False","ACTIVATION_ALLOWED=True")
add('C58_scope_says_a_process_is_started',"       'processes_started':0,","       'processes_started':1,")
add('C59_scope_never_list_loses_the_payload_hash',"'a symbol in the receipt',\n                'the hash or the size of the payload file in the receipt'],","'a symbol in the receipt'],")
add('C60_scope_loses_the_delivery_limit',"                 'delivery_bytes':K8_DELIVERY_MAX_BYTES,","                 ")
add('C61_plan_has_one_more_member',"PLAN_KEYS=frozenset(('day','windows','contract','files','days_parent','identity_rule','evidence_boot_id_sha256'))",
    "PLAN_KEYS=frozenset(('day','windows','contract','files','days_parent','identity_rule','evidence_boot_id_sha256','payload'))")
add('C62_evidence_not_required',"EVIDENCE_REQUIRED=True","EVIDENCE_REQUIRED=False")

# ---------------------------------------------------------------- the layout of the day's files
add('L01_template_into_the_go_root',"    table=[('template','documents',stem+'.template.md'),","    table=[('template','go',stem+'.template.md'),")
add('L02_admission_record_named_as_the_go_file',"('go_admission_record','documents',stem+'.go-admission.md'),","('go_admission_record','documents',stem+'.admission.md'),")
add('L03_bar_manifest_record_named_with_an_underscore',"('go_bar_manifest_record','documents',stem+'.go-bar_manifest.md'),","('go_bar_manifest_record','documents',stem+'.go_bar_manifest.md'),")
add('L04_publication_record_name',"stem+'.publication-bar_manifest.md')]","stem+'.publication-bar-manifest.md')]")
add('L05_views_into_the_emitter_root',"    table+=[('veto_view:'+window,'documents',stem+'.view-'+window+'.md') for window in windows]","    table+=[('veto_view:'+window,'config',stem+'.view-'+window+'.md') for window in windows]")
add('L06_go_files_into_the_documents_root',"    table+=[('go_admission','go',stem+'.admission.json'),","    table+=[('go_admission','documents',stem+'.admission.json'),")
add('L07_bar_manifest_go_name',"('go_bar_manifest','go',stem+'.bar_manifest.json')]","('go_bar_manifest','go',stem+'.bar-manifest.json')]")
add('L08_configs_into_the_documents_root',"    table+=[('capacity_config:'+window,'config',stem+'.'+window+'.capacity.json') for window in windows]","    table+=[('capacity_config:'+window,'documents',stem+'.'+window+'.capacity.json') for window in windows]")
add('L09_config_name_without_the_window',"stem+'.'+window+'.capacity.json') for window in windows]","stem+'.capacity.json') for window in windows]")
add('L10_payload_name',"def k8_payload_name(day):return 'session='+day+'.json'","def k8_payload_name(day):return 'session='+day+'.payload.json'",effect='payload.path')
add('L11_paths_outside_the_capacity_tree',"def k8_path(root,name):return K8_CAPACITY_ROOT+'/'+root+'/'+name","def k8_path(root,name):return K8_CAPACITY_ROOT+'/'+name",effect=['files','contract.carried_whole_into'])
add('L12_commit_key_of_the_publish_step',"    return sha(canonical([K8_EPOCH,day,'causal_list','commit_launch']))","    return sha(canonical([K8_EPOCH,day,'causal_list','publish_launch']))",effect='k9_inputs.commit_attempt_key')
add('L13_views_created_after_the_go_files',"    table+=[('veto_view:'+window,'documents',stem+'.view-'+window+'.md') for window in windows]\n    table+=[('go_admission','go',stem+'.admission.json'),('go_bar_manifest','go',stem+'.bar_manifest.json')]\n",
    "    table+=[('go_admission','go',stem+'.admission.json'),('go_bar_manifest','go',stem+'.bar_manifest.json')]\n    table+=[('veto_view:'+window,'documents',stem+'.view-'+window+'.md') for window in windows]\n")
add('L14_name_rule_accepts_any_directory',"            and (directory.rows is None or str(PurePosixPath(path).parent)==directory.rows[-1]['path']))","            and True)")
add('L16_name_rule_accepts_an_unclean_path',"    return (type(path) is str and clean_path(path) and text(PurePosixPath(path).name,K8_FILE_NAME)","    return (type(path) is str and text(PurePosixPath(path).name,K8_FILE_NAME)")

# ---------------------------------------------------------------- the signed bytes (k8_blob, k8_json, k8_pin, k8_delivery)
add('B01_blob_with_an_extra_member',"    need(type(item) is dict and set(item)=={'sha256','bytes','content_b64'},code)","    need(type(item) is dict and set(item)>={'sha256','bytes','content_b64'},code)",refusal='DELIVERY_FILE_INVALID')
add('B02_blob_hash_unchecked',"    need(len(raw)==item['bytes'] and sha(raw)==item['sha256'],code)","    need(len(raw)==item['bytes'],code)")
add('B03_blob_size_unchecked',"    need(len(raw)==item['bytes'] and sha(raw)==item['sha256'],code)","    need(sha(raw)==item['sha256'],code)")
add('B04_blob_not_strict_base64',"    try:raw=base64.b64decode(item['content_b64'].encode('ascii'),validate=True)","    try:raw=base64.b64decode(item['content_b64'].encode('ascii'),validate=False)")
add('B05_blob_size_unbounded',"integer(item['bytes'],1,MAX_FILE_BYTES)","integer(item['bytes'],1)")
add('B07_json_not_canonical',"    need(type(value) is dict and canonical(value)==raw,code)","    need(type(value) is dict,code)",refusal=['CONTRACT_INVALID','CONFIG_INVALID','COMMITMENT_INVALID'])
add('B08_json_of_any_type',"    need(type(value) is dict and canonical(value)==raw,code)","    need(canonical(value)==raw,code)")
add('B09_json_refusal_with_the_parser_code',"    except Refused:raise Refused(code) from None\n    need(type(value) is dict and","    except Refused:raise\n    need(type(value) is dict and")
add('B10_pin_with_an_extra_member',"    need(type(value) is dict and set(value)=={'file','sha256'} and text(","    need(type(value) is dict and set(value)>={'file','sha256'} and text(",refusal='CONFIG_PINS_INVALID')
add('B11_pin_hash_unchecked',"text(value['file'],K8_CHAIN_FILE_NAME) and hexpin(value['sha256']),code)","text(value['file'],K8_CHAIN_FILE_NAME),code)")
add('D01_day_of_the_epoch_accepted',"    need(day in K8_EVES,'DAY_INVALID')","    need(day in DATES,'DAY_INVALID')",refusal='DAY_INVALID')
add('D02_no_window',"    need(type(windows) is list and 1<=len(windows)<=K8_MAX_WINDOWS","    need(type(windows) is list and 0<=len(windows)<=K8_MAX_WINDOWS",refusal='WINDOWS_INVALID')
add('D03_window_names_unchecked',"and all(text(name,K8_WINDOW_NAME) for name in windows)\n","\n")
add('D04_window_twice',"         and len(set(windows))==len(windows),'WINDOWS_INVALID')","         ,'WINDOWS_INVALID')")
add('D05_window_list_of_any_type',"    need(type(windows) is list and 1<=len(windows)","    need(1<=len(windows)")
add('D06_files_beyond_the_layout',"    need(type(plan['files']) is dict and set(plan['files'])==set(names),'DELIVERY_FILES_NOT_THE_LAYOUT')","    need(type(plan['files']) is dict and set(plan['files'])>=set(names),'DELIVERY_FILES_NOT_THE_LAYOUT')",refusal='DELIVERY_FILES_NOT_THE_LAYOUT')
add('D07_delivery_size_without_the_contract',"    need(len(contract_raw)+sum(len(raw) for raw in raws.values())<=K8_DELIVERY_MAX_BYTES,'DELIVERY_TOO_LARGE')","    need(sum(len(raw) for raw in raws.values())<=K8_DELIVERY_MAX_BYTES,'DELIVERY_TOO_LARGE')",refusal='DELIVERY_TOO_LARGE')
add('D08_delivery_size_unchecked',"    need(len(contract_raw)+sum(len(raw) for raw in raws.values())<=K8_DELIVERY_MAX_BYTES,'DELIVERY_TOO_LARGE')\n","")
add('D09_contract_keys_unchecked',"    need(set(contract)==K8_CONTRACT_KEYS,'CONTRACT_INVALID')\n","")
add('D10_scope_session_unchecked',"         and scope['session']==day and hexpin(scope['commitment_sha256'])","         and hexpin(scope['commitment_sha256'])",refusal='CONTRACT_NOT_OF_THIS_DAY')
add('D11_scope_epoch_unchecked',"set(scope)=={'epoch','session','commitment_sha256','list_sha256'} and scope['epoch']==K8_EPOCH\n","set(scope)=={'epoch','session','commitment_sha256','list_sha256'}\n")
add('D12_scope_with_more_members',"    need(type(scope) is dict and set(scope)=={'epoch','session','commitment_sha256','list_sha256'}","    need(type(scope) is dict and set(scope)>={'epoch','session','commitment_sha256','list_sha256'}")
add('D13_scope_list_hash_unchecked',"and hexpin(scope['commitment_sha256']) and hexpin(scope['list_sha256']),'CONTRACT_NOT_OF_THIS_DAY')","and hexpin(scope['commitment_sha256']),'CONTRACT_NOT_OF_THIS_DAY')")
add('D14_scope_of_any_type',"    need(type(scope) is dict and set(scope)==","    need(set(scope)==")
add('D15_config_refused_with_the_contract_code',"        config=k8_json(raws['capacity_config:'+window],MAX_FILE_BYTES,'CONFIG_INVALID')","        config=k8_json(raws['capacity_config:'+window],MAX_FILE_BYTES,'CONTRACT_INVALID')")
add('D16_pins_beyond_the_eleven',"        need(type(pins) is dict and set(pins)==set(K8_CHAIN_ROLES)|{label for _,label in K8_RECORD_PINS},'CONFIG_PINS_INVALID')",
    "        need(type(pins) is dict and set(pins)>=set(K8_CHAIN_ROLES)|{label for _,label in K8_RECORD_PINS},'CONFIG_PINS_INVALID')")
add('D17_windows_may_pin_other_chains',"        need(chain is None or this==chain,'CONFIG_PINS_INVALID');chain=this","        chain=this")
add('D18_record_pins_not_compared',"            need(pins[label]=={'file':names[key],'sha256':sha(raws[key])},'DELIVERY_NOT_CONSISTENT')","            need(pins[label]['file']==names[key],'DELIVERY_NOT_CONSISTENT')",refusal='DELIVERY_NOT_CONSISTENT')
add('D19_record_names_not_compared',"            need(pins[label]=={'file':names[key],'sha256':sha(raws[key])},'DELIVERY_NOT_CONSISTENT')","            need(pins[label]['sha256']==sha(raws[key]),'DELIVERY_NOT_CONSISTENT')")
add('D20_view_not_compared',"        need(views=={day:{'file':names['veto_view:'+window],'sha256':sha(raws['veto_view:'+window])}},'DELIVERY_NOT_CONSISTENT')\n","")
add('D21_view_of_the_first_window_for_all',"'sha256':sha(raws['veto_view:'+window])}},'DELIVERY_NOT_CONSISTENT')","'sha256':sha(raws['veto_view:'+windows[0]])}},'DELIVERY_NOT_CONSISTENT')")
add('D22_root_path_unchecked',"and found[root]['path']==K8_CONTAINER_CAPACITY+'/'+root\n","\n",refusal='CONFIG_ROOTS_INVALID')
add('D23_root_identity_unchecked',"            and hexpin(found[root]['identity']) for root in K8_IDENTITY_ROOTS),'CONFIG_ROOTS_INVALID')","            and True for root in K8_IDENTITY_ROOTS),'CONFIG_ROOTS_INVALID')")
add('D24_windows_may_pin_other_roots',"        need(roots is None or found==roots,'CONFIG_ROOTS_INVALID');roots=found","        roots=found")
add('D25_roots_with_more_members',"type(found[root]) is dict and set(found[root])=={'path','identity'}","type(found[root]) is dict and set(found[root])>={'path','identity'}")
add('D26_roots_beyond_the_three',"        need(type(found) is dict and set(found)==set(K8_IDENTITY_ROOTS) and all(","        need(type(found) is dict and set(found)>=set(K8_IDENTITY_ROOTS) and all(")
add('D27_go_file_with_more_members',"        need(set(go)=={'go'} and type(go['go']) is dict,'GO_FILE_INVALID')","        need('go' in go and type(go['go']) is dict,'GO_FILE_INVALID')",refusal='GO_FILE_INVALID')
add('D28_go_file_day_unchecked',"        need((go['go'].get('epoch'),go['go'].get('day'),go['go'].get('phase'))==(K8_EPOCH,day,phase),'GO_FILE_NOT_OF_THIS_DAY')",
    "        need((go['go'].get('epoch'),go['go'].get('phase'))==(K8_EPOCH,phase),'GO_FILE_NOT_OF_THIS_DAY')",refusal='GO_FILE_NOT_OF_THIS_DAY')
add('D29_go_file_phase_unchecked',"        need((go['go'].get('epoch'),go['go'].get('day'),go['go'].get('phase'))==(K8_EPOCH,day,phase),'GO_FILE_NOT_OF_THIS_DAY')",
    "        need((go['go'].get('epoch'),go['go'].get('day'))==(K8_EPOCH,day),'GO_FILE_NOT_OF_THIS_DAY')")
add('D30_go_file_epoch_unchecked',"        need((go['go'].get('epoch'),go['go'].get('day'),go['go'].get('phase'))==(K8_EPOCH,day,phase),'GO_FILE_NOT_OF_THIS_DAY')",
    "        need((go['go'].get('day'),go['go'].get('phase'))==(day,phase),'GO_FILE_NOT_OF_THIS_DAY')")
add('D31_go_files_unchecked',"    for key,phase in K8_GO_FILES:\n        go=k8_json(","    for key,phase in ():\n        go=k8_json(")
add('V01_identity_rule_unchecked',"    need(plan['identity_rule'] in K8_IDENTITY_RULES,'IDENTITY_RULE_INVALID')\n","",refusal='IDENTITY_RULE_INVALID')
add('V02_days_chain_with_an_open_root',"    validate_chain(plan['days_parent'],K8_K9_DAYS,open_root=None,receives_entry=False)","    validate_chain(plan['days_parent'],K8_K9_DAYS,open_root='/var/lib',receives_entry=False)")
add('V03_days_chain_unchecked',"    validate_chain(plan['days_parent'],K8_K9_DAYS,open_root=None,receives_entry=False)\n","")
add('V04_k9_chain_group_unchecked',"    return row['gid']==0 and not row['mode']&stat.S_ISGID","    return not row['mode']&stat.S_ISGID",refusal='K9_CHAIN_NOT_ROOT_CONTROLLED')
add('V05_k9_chain_setgid_unchecked',"    return row['gid']==0 and not row['mode']&stat.S_ISGID","    return row['gid']==0")
add('V06_k9_chain_root_control_judged_on_the_last_row_only',"    need(all(k8_root_controlled(row) for row in plan['days_parent']),'K9_CHAIN_NOT_ROOT_CONTROLLED')","    need(k8_root_controlled(plan['days_parent'][-1]),'K9_CHAIN_NOT_ROOT_CONTROLLED')")
add('V07_boot_unbound',"    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')","    need(True,'EVIDENCE_BOOT_UNBOUND')",refusal='EVIDENCE_BOOT_UNBOUND')
add('V08_delivery_not_judged_by_validate_plan',"def validate_plan(plan):\n    k8_delivery(plan)\n","def validate_plan(plan):\n    pass\n")

# ---------------------------------------------------------------- effects_of: one per member
add('E01_effects_operation',"    return {'operation':OPERATION,'epoch':K8_EPOCH,'day':day,","    return {'operation':PHASE,'epoch':K8_EPOCH,'day':day,",effect='operation')
add('E02_effects_day',"    return {'operation':OPERATION,'epoch':K8_EPOCH,'day':day,","    return {'operation':OPERATION,'epoch':K8_EPOCH,'day':K8_EVES[day],",effect='day')
add('E03_effects_windows',"            'windows':list(plan['windows']),\n","            'windows':sorted(plan['windows']),\n",effect='windows')
add('E04_effects_tree_roots',"'roots':{root:K8_CAPACITY_ROOT+'/'+root for root in K8_CAPACITY_ROOTS},","'roots':{root:K8_CONTAINER_CAPACITY+'/'+root for root in K8_CAPACITY_ROOTS},")
add('E05_effects_tree_required',"'required':'EXISTING_DIRECTORY_NOT_A_LINK_UID_0_GID_0_MODE_0700_HELD_UNCHANGED',","'required':'EXISTING_DIRECTORY',",effect='capacity_tree.required')
add('E06_effects_file_hash_of_the_contract',"'sha256':sha(delivery['raws'][key]),'bytes':len(delivery['raws'][key]),","'sha256':sha(delivery['contract_raw']),'bytes':len(delivery['raws'][key]),")
add('E07_effects_file_size',"'sha256':sha(delivery['raws'][key]),'bytes':len(delivery['raws'][key]),","'sha256':sha(delivery['raws'][key]),'bytes':len(delivery['contract_raw']),")
add('E08_effects_file_mode',"                      'mode_octal':'%04o'%K8_FILE_MODE,'uid':0,'gid':0,'links':1,'expect':'ABSENT'}","                      'mode_octal':'0644','uid':0,'gid':0,'links':1,'expect':'ABSENT'}")
add('E09_effects_file_expectation',"                      'mode_octal':'%04o'%K8_FILE_MODE,'uid':0,'gid':0,'links':1,'expect':'ABSENT'}","                      'mode_octal':'%04o'%K8_FILE_MODE,'uid':0,'gid':0,'links':1,'expect':'ANY'}")
add('E10_effects_contract_hash',"            'contract':{'sha256':sha(delivery['contract_raw']),'bytes':len(delivery['contract_raw']),","            'contract':{'sha256':sha(delivery['raws']['template']),'bytes':len(delivery['contract_raw']),",effect='contract.sha256')
add('E11_effects_contract_size',"            'contract':{'sha256':sha(delivery['contract_raw']),'bytes':len(delivery['contract_raw']),","            'contract':{'sha256':sha(delivery['contract_raw']),'bytes':0,",effect='contract.bytes')
add('E12_effects_contract_written',"'written_as_its_own_file':False,","'written_as_its_own_file':True,",effect='contract.written_as_its_own_file')
add('E13_effects_payload_mode',"            'payload':{'path':k8_path('payload',k8_payload_name(day)),'mode_octal':'%04o'%K8_FILE_MODE,","            'payload':{'path':k8_path('payload',k8_payload_name(day)),'mode_octal':'0644',",effect='payload.mode_octal')
add('E14_effects_payload_owner',"'mode_octal':'%04o'%K8_FILE_MODE,'uid':0,'gid':0,'links':1,'expect':'ABSENT',\n","'mode_octal':'%04o'%K8_FILE_MODE,'uid':0,'gid':1000,'links':1,'expect':'ABSENT',\n",effect=['payload.uid','payload.gid','payload.links','payload.expect'])
add('E15_effects_payload_bytes',"                       'bytes':'CANONICAL_JSON_OF_CONTRACT_AND_CAUSAL_ASSEMBLED_ON_THE_HOST',","                       'bytes':'ASSEMBLED_ON_THE_HOST',",effect='payload.bytes')
add('E16_effects_payload_causal_members',"'causal_members':['commitment_sha256','epoch','list_sha256','session','status','symbols'],","'causal_members':['commitment_sha256','epoch','list_sha256','session','symbols'],",effect='payload.causal_members')
add('E17_effects_payload_hash_reported',"'hash_and_size':'NOT_SIGNED_NOT_REPORTED_A_COMMITMENT_TO_THE_LIST'},","'hash_and_size':'REPORTED'},",effect='payload.hash_and_size')
add('E18_effects_causal_scope_commitment',"            'causal_scope':{'commitment_sha256':scope['commitment_sha256'],'list_sha256':scope['list_sha256']},","            'causal_scope':{'commitment_sha256':scope['list_sha256'],'list_sha256':scope['list_sha256']},",effect='causal_scope.commitment_sha256')
add('E19_effects_causal_scope_list',"            'causal_scope':{'commitment_sha256':scope['commitment_sha256'],'list_sha256':scope['list_sha256']},","            'causal_scope':{'commitment_sha256':scope['commitment_sha256'],'list_sha256':scope['commitment_sha256']},",effect='causal_scope.list_sha256')
add('E20_effects_days_parent',"            'k9_inputs':{'days_parent':chain_effects(plan['days_parent']),","            'k9_inputs':{'days_parent':chain_effects(plan['days_parent'][:3]),",effect='k9_inputs.days_parent')
add('E21_effects_k9_required',"'required':'COMPLETE_RECEIPT_OF_THIS_STEP_NAMING_BOTH_FILES_BY_SHA256'},","'required':'COMPLETE_RECEIPT'},",effect='k9_inputs.required')
add('E22_effects_chain_path',"            'chain_documents':{role:{'path':k8_path('documents',pin['file']),","            'chain_documents':{role:{'path':pin['file'],",effect='chain_documents')
add('E23_effects_chain_required',"'required':'PRESENT_ROOT_0600_THESE_BYTES'}","'required':'PRESENT'}")
add('E24_effects_identity_rule',"            'root_identities':{'rule':plan['identity_rule'],","            'root_identities':{'rule':'REFUSE_ON_MISMATCH',",effect='root_identities.rule')
add('E25_effects_pinned_identities',"'pinned':{root:delivery['roots'][root]['identity'] for root in K8_IDENTITY_ROOTS}},","'pinned':{root:delivery['roots'][root]['path'] for root in K8_IDENTITY_ROOTS}},",effect='root_identities.pinned')
add('E26_effects_boot',"            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],\n            'pre_existing_objects_modified':False,'secret_written':False,","            'evidence_boot_id_sha256':None,\n            'pre_existing_objects_modified':False,'secret_written':False,",effect='evidence_boot_id_sha256')
add('E27_effects_modified',"            'pre_existing_objects_modified':False,'secret_written':False,'activation':False,'container_touched':False,'process_started':False,",
    "            'pre_existing_objects_modified':True,'secret_written':True,'activation':True,'container_touched':True,'process_started':True,",
    effect=['pre_existing_objects_modified','secret_written','activation','container_touched','process_started'])
add('E28_effects_symbols',"            'symbols_in_receipt':False}","            'symbols_in_receipt':None}",effect='symbols_in_receipt')
add('E29_effects_eve',"'eve':{'not_before':K8_EVES[day]+K8_EVE_FROM,'not_after':day+K8_EVE_UNTIL},","'eve':{'not_before':K8_EVES[day]+K8_EVE_FROM,'not_after':day+K8_EVE_FROM},")
add('E30_effects_tree_parent_and_path',"            'capacity_tree':{'path':K8_CAPACITY_ROOT,'parent':K8_VAR_LIB,","            'capacity_tree':{'path':K8_CAPACITY_ROOT,'parent':'/',")
add('E31_effects_k9_paths_of_another_day',"                         'commit_receipt':K8_K9_DAYS+'/'+day+'/'+K8_RECEIPTS+'/'+K8_COMMIT_RECEIPT,","                         'commit_receipt':K8_K9_DAYS+'/'+K8_RECEIPTS+'/'+K8_COMMIT_RECEIPT,")
add('E32_effects_payload_carried_into',"'carried_whole_into':k8_path('payload',k8_payload_name(day))},","'carried_whole_into':None},")
add('E33_success_criterion_is_the_partial_outcome',"def success_of(plan):return COMPLETE_OUTCOME\n","def success_of(plan):return PARTIAL_OUTCOME\n")

# ---------------------------------------------------------------- the precheck: every refusal, and the order
add('P01_identity_unchecked',"            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n","",refusal='EXECUTOR_IDENTITY')
add('P02_eve_start_unchecked',"            need(instant(K8_EVES[day]+K8_EVE_FROM)<=start and end<=instant(day+K8_EVE_UNTIL),'WINDOW_NOT_IN_THE_EVE_OF_THE_DAY')",
    "            need(end<=instant(day+K8_EVE_UNTIL),'WINDOW_NOT_IN_THE_EVE_OF_THE_DAY')",refusal='WINDOW_NOT_IN_THE_EVE_OF_THE_DAY')
add('P03_eve_end_unchecked',"            need(instant(K8_EVES[day]+K8_EVE_FROM)<=start and end<=instant(day+K8_EVE_UNTIL),'WINDOW_NOT_IN_THE_EVE_OF_THE_DAY')",
    "            need(instant(K8_EVES[day]+K8_EVE_FROM)<=start,'WINDOW_NOT_IN_THE_EVE_OF_THE_DAY')")
add('P04_window_judged_after_the_boot',"            need(instant(K8_EVES[day]+K8_EVE_FROM)<=start and end<=instant(day+K8_EVE_UNTIL),'WINDOW_NOT_IN_THE_EVE_OF_THE_DAY')\n            host.umask(0o077)\n            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')\n",
    "            host.umask(0o077)\n            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')\n            need(instant(K8_EVES[day]+K8_EVE_FROM)<=start and end<=instant(day+K8_EVE_UNTIL),'WINDOW_NOT_IN_THE_EVE_OF_THE_DAY')\n")
add('P05_umask_not_set',"            host.umask(0o077)\n","")
add('P06_boot_unchecked',"            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')\n","",refusal='EVIDENCE_FROM_EARLIER_BOOT')
add('P07_days_chain_not_walked',"            days=Pinned(host,walk_pinned(host,plan['days_parent'],gate,detail['parent']),rows=plan['days_parent']);pinned.append(days)",
    "            days=Pinned(host,descend(host,K8_K9_DAYS,gate),rows=plan['days_parent']);pinned.append(days)")
add('P08_var_lib_reached_without_its_rows',"            var_lib=Pinned(host,walk_pinned(host,plan['days_parent'][:3],gate,[]),rows=plan['days_parent'][:3]);pinned.append(var_lib)",
    "            var_lib=Pinned(host,descend(host,K8_VAR_LIB,gate),rows=None,parent=None,name=None);pinned.append(var_lib)")
add('P09_capacity_root_absence_reported_as_not_private',"            capacity=k8_hold(host,K8_CAPACITY_NAME,var_lib,gate,('CAPACITY_DIRECTORY_ABSENT','CAPACITY_DIRECTORY_NOT_PRIVATE',",
    "            capacity=k8_hold(host,K8_CAPACITY_NAME,var_lib,gate,('CAPACITY_DIRECTORY_NOT_PRIVATE','CAPACITY_DIRECTORY_NOT_PRIVATE',",refusal='CAPACITY_DIRECTORY_ABSENT')
add('P10_capacity_roots_not_held',"            for root in K8_CAPACITY_ROOTS:\n                held[root]=k8_hold(","            for root in K8_CAPACITY_ROOTS:\n                held[root]=capacity;k8_hold(")
add('P11_hold_absent_not_refused',"    need(found is not None,codes[0])\n    need(found['type']=='dir'","    need(found['type']=='dir'")
add('P12_hold_mode_unchecked',"    need(found['type']=='dir' and (found['uid'],found['gid'],found['mode_octal'])==(0,0,'%04o'%K8_DIRECTORY_MODE),codes[1])",
    "    need(found['type']=='dir' and (found['uid'],found['gid'])==(0,0),codes[1])",refusal=['CAPACITY_DIRECTORY_NOT_PRIVATE','K9_DIRECTORY_NOT_PRIVATE'])
add('P13_hold_owner_unchecked',"    need(found['type']=='dir' and (found['uid'],found['gid'],found['mode_octal'])==(0,0,'%04o'%K8_DIRECTORY_MODE),codes[1])",
    "    need(found['type']=='dir' and found['mode_octal']=='%04o'%K8_DIRECTORY_MODE,codes[1])")
add('P14_hold_type_unchecked',"    need(found['type']=='dir' and (found['uid'],found['gid'],found['mode_octal'])==","    need((found['uid'],found['gid'],found['mode_octal'])==")
add('P15_hold_open_follows_a_link',"    try:fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=parent.fd)","    try:fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|host.noatime(),dir_fd=parent.fd)")
add('P16_hold_identity_not_compared',"    if held.identity!=(found['device'],found['inode'],0,0,K8_DIRECTORY_MODE):\n        held.close();raise Refused(codes[2])\n","",
    refusal=['CAPACITY_DIRECTORY_CHANGED_DURING_PRECHECK','K9_DIRECTORY_CHANGED_DURING_PRECHECK'])
add('P17_hold_open_failure_reported_as_absent',"    except OSError:raise Refused(codes[2]) from None","    except OSError:raise Refused(codes[0]) from None")
add('P18_hold_no_gate_before_the_open',"    gate()\n    try:fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW","    try:fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW")
add('P19_k9_codes_of_the_capacity_tree',"            k9=('K9_DIRECTORY_ABSENT','K9_DIRECTORY_NOT_PRIVATE','K9_DIRECTORY_CHANGED_DURING_PRECHECK')",
    "            k9=('CAPACITY_DIRECTORY_ABSENT','K9_DIRECTORY_NOT_PRIVATE','K9_DIRECTORY_CHANGED_DURING_PRECHECK')",refusal='K9_DIRECTORY_ABSENT')
add('P20_day_directory_of_the_eve',"            held['day']=k8_hold(host,day,days,gate,k9,detail['precheck']['k9'])","            held['day']=k8_hold(host,K8_EVES[day],days,gate,k9,detail['precheck']['k9'])")
add('P21_receipts_from_the_causal_directory',"            held['receipts']=k8_hold(host,K8_RECEIPTS,held['day'],gate,k9,detail['precheck']['k9'])","            held['receipts']=k8_hold(host,K8_CAUSAL,held['day'],gate,k9,detail['precheck']['k9'])")
add('P22_causal_held_after_the_receipt_is_read',"            held['causal']=k8_hold(host,K8_CAUSAL,held['day'],gate,k9,detail['precheck']['k9'])\n            outputs=k8_commit_outputs(k8_read(host,K8_COMMIT_RECEIPT,held['receipts'],gate,K8_RECEIPT_MAX_BYTES,\n                                              ('COMMIT_RECEIPT_ABSENT','K9_FILE_NOT_PRIVATE'),detail['precheck']['k9']),day)\n",
    "            outputs=k8_commit_outputs(k8_read(host,K8_COMMIT_RECEIPT,held['receipts'],gate,K8_RECEIPT_MAX_BYTES,\n                                              ('COMMIT_RECEIPT_ABSENT','K9_FILE_NOT_PRIVATE'),detail['precheck']['k9']),day)\n            held['causal']=k8_hold(host,K8_CAUSAL,held['day'],gate,k9,detail['precheck']['k9'])\n")
add('P23_receipt_absence_reported_as_not_private',"                                              ('COMMIT_RECEIPT_ABSENT','K9_FILE_NOT_PRIVATE'),detail['precheck']['k9']),day)",
    "                                              ('K9_FILE_NOT_PRIVATE','K9_FILE_NOT_PRIVATE'),detail['precheck']['k9']),day)",refusal='COMMIT_RECEIPT_ABSENT')
add('P24_read_absent_not_refused',"    need(found is not None,codes[0])\n    need(found['type']=='file'","    need(found['type']=='file'")
add('P25_read_mode_unchecked',"(found['uid'],found['gid'],found['mode_octal'],found['links'])==(0,0,'%04o'%K8_FILE_MODE,1),codes[1])","(found['uid'],found['gid'],found['links'])==(0,0,1),codes[1])",
    refusal=['K9_FILE_NOT_PRIVATE','CHAIN_DOCUMENT_NOT_PRIVATE'])
add('P26_read_links_unchecked',"(found['uid'],found['gid'],found['mode_octal'],found['links'])==(0,0,'%04o'%K8_FILE_MODE,1),codes[1])","(found['uid'],found['gid'],found['mode_octal'])==(0,0,'%04o'%K8_FILE_MODE),codes[1])")
add('P27_read_owner_unchecked',"(found['uid'],found['gid'],found['mode_octal'],found['links'])==(0,0,'%04o'%K8_FILE_MODE,1),codes[1])","(found['mode_octal'],found['links'])==('%04o'%K8_FILE_MODE,1),codes[1])")
add('P28_read_type_unchecked',"    need(found['type']=='file' and (found['uid'],","    need((found['uid'],")
add('P29_read_object_not_compared',"    need((info.st_dev,info.st_ino)==(found['device'],found['inode']) and info.st_uid==0 and info.st_gid==0\n","    need(info.st_uid==0 and info.st_gid==0\n")
add('P30_read_mode_after_open_unchecked',"         and stat.S_IMODE(info.st_mode)==K8_FILE_MODE and info.st_nlink==1,codes[1])","         and info.st_nlink==1,codes[1])")
add('P31_receipt_parser_code',"    except Refused:raise Refused('COMMIT_RECEIPT_INVALID') from None","    except Refused:raise",refusal='COMMIT_RECEIPT_INVALID')
add('P32_receipt_member_set_unchecked',"    need(type(receipt) is dict and set(receipt)==K8_STEP_RECEIPT_KEYS and receipt['schema']=='K9_STEP_RECEIPT_V1','COMMIT_RECEIPT_INVALID')",
    "    need(type(receipt) is dict and receipt.get('schema')=='K9_STEP_RECEIPT_V1','COMMIT_RECEIPT_INVALID')")
add('P33_receipt_schema_unchecked',"set(receipt)==K8_STEP_RECEIPT_KEYS and receipt['schema']=='K9_STEP_RECEIPT_V1','COMMIT_RECEIPT_INVALID')","set(receipt)==K8_STEP_RECEIPT_KEYS,'COMMIT_RECEIPT_INVALID')")
add('P34_receipt_status_unchecked',"    need(receipt['status']=='COMPLETE' and receipt['code'] is None,'COMMIT_RECEIPT_NOT_COMPLETE')","    need(receipt['code'] is None,'COMMIT_RECEIPT_NOT_COMPLETE')",refusal='COMMIT_RECEIPT_NOT_COMPLETE')
add('P35_receipt_code_unchecked',"    need(receipt['status']=='COMPLETE' and receipt['code'] is None,'COMMIT_RECEIPT_NOT_COMPLETE')","    need(receipt['status']=='COMPLETE','COMMIT_RECEIPT_NOT_COMPLETE')")
add('P36_receipt_day_unchecked',"    need((receipt['epoch'],receipt['day'],receipt['phase'],receipt['operation'],receipt['attempt_key'])==\n         (K8_EPOCH,day,'causal_list','commit_launch',k8_commit_key(day)),'COMMIT_RECEIPT_NOT_OF_THIS_STEP')",
    "    need((receipt['epoch'],receipt['phase'],receipt['operation'])==\n         (K8_EPOCH,'causal_list','commit_launch'),'COMMIT_RECEIPT_NOT_OF_THIS_STEP')",refusal='COMMIT_RECEIPT_NOT_OF_THIS_STEP')
add('P37_receipt_of_any_step',"         (K8_EPOCH,day,'causal_list','commit_launch',k8_commit_key(day)),'COMMIT_RECEIPT_NOT_OF_THIS_STEP')","         (K8_EPOCH,day,receipt['phase'],receipt['operation'],k8_commit_key(day)),'COMMIT_RECEIPT_NOT_OF_THIS_STEP')")
add('P38_receipt_package_unchecked',"    need((receipt['package_sha256'],receipt['build_sha'])==(K8_PACKAGE,K8_REVISION),'COMMIT_RECEIPT_NOT_OF_THIS_PACKAGE')\n","",refusal='COMMIT_RECEIPT_NOT_OF_THIS_PACKAGE')
add('P39_receipt_outputs_one_file_enough',"all(hexpin(outputs.get(key)) for key in K8_COMMIT_OUTPUTS),'COMMIT_RECEIPT_WITHOUT_THE_COMMITMENT')","any(hexpin(outputs.get(key)) for key in K8_COMMIT_OUTPUTS),'COMMIT_RECEIPT_WITHOUT_THE_COMMITMENT')",refusal='COMMIT_RECEIPT_WITHOUT_THE_COMMITMENT')
add('P40_receipt_outputs_of_any_type',"    need(type(outputs) is dict and all(","    need(outputs and all(")
add('P41_commitment_absence_reported_as_not_private',"            commitment_raw=k8_read(host,K8_COMMITMENT,held['causal'],gate,K8_COMMITMENT_MAX_BYTES,('COMMITMENT_ABSENT','K9_FILE_NOT_PRIVATE'),",
    "            commitment_raw=k8_read(host,K8_COMMITMENT,held['causal'],gate,K8_COMMITMENT_MAX_BYTES,('K9_FILE_NOT_PRIVATE','K9_FILE_NOT_PRIVATE'),",refusal='COMMITMENT_ABSENT')
add('P42_commitment_hash_not_the_receipts',"    need(sha(commitment_raw)==outputs[K8_COMMIT_OUTPUTS[0]] and sha(audit_raw)==outputs[K8_COMMIT_OUTPUTS[1]],'COMMITMENT_NOT_THE_COMMIT_RECEIPT_OUTPUT')",
    "    need(sha(audit_raw)==outputs[K8_COMMIT_OUTPUTS[1]],'COMMITMENT_NOT_THE_COMMIT_RECEIPT_OUTPUT')",refusal='COMMITMENT_NOT_THE_COMMIT_RECEIPT_OUTPUT')
add('P43_audit_hash_not_the_receipts',"    need(sha(commitment_raw)==outputs[K8_COMMIT_OUTPUTS[0]] and sha(audit_raw)==outputs[K8_COMMIT_OUTPUTS[1]],'COMMITMENT_NOT_THE_COMMIT_RECEIPT_OUTPUT')",
    "    need(sha(commitment_raw)==outputs[K8_COMMIT_OUTPUTS[0]],'COMMITMENT_NOT_THE_COMMIT_RECEIPT_OUTPUT')")
add('P44_commitment_schema_unchecked',"    need(commitment.get('schema')==K8_COMMITMENT_SCHEMA,'COMMITMENT_INVALID')\n","")
add('P45_commitment_day_unchecked',"    need(commitment.get('epoch')==K8_EPOCH and commitment.get('session')==day,'COMMITMENT_NOT_OF_THIS_DAY')","    need(commitment.get('epoch')==K8_EPOCH,'COMMITMENT_NOT_OF_THIS_DAY')",refusal='COMMITMENT_NOT_OF_THIS_DAY')
add('P46_commitment_epoch_unchecked',"    need(commitment.get('epoch')==K8_EPOCH and commitment.get('session')==day,'COMMITMENT_NOT_OF_THIS_DAY')","    need(commitment.get('session')==day,'COMMITMENT_NOT_OF_THIS_DAY')")
add('P47_list_grammar_unchecked',"and all(text(name,K8_SYMBOL) for name in names) and len(set(names))==len(names),","and len(set(names))==len(names),",refusal='COMMITMENT_LIST_INVALID')
add('P48_list_duplicates_accepted',"and all(text(name,K8_SYMBOL) for name in names) and len(set(names))==len(names),","and all(text(name,K8_SYMBOL) for name in names),")
add('P49_list_beyond_the_capacity',"    need(type(names) is list and len(names)<=K8_CAPACITY and all(","    need(type(names) is list and all(")
add('P50_list_of_any_type',"    need(type(names) is list and len(names)<=K8_CAPACITY","    need(len(names)<=K8_CAPACITY")
add('P51_list_hash_field_unchecked',"    need(commitment.get('list_sha256')==list_sha,'COMMITMENT_LIST_INVALID')\n","")
add('P52_commitment_not_the_contract_scope',"    need(commitment_sha==scope['commitment_sha256'],'COMMITMENT_NOT_THE_CONTRACT_SCOPE')\n","",refusal='COMMITMENT_NOT_THE_CONTRACT_SCOPE')
add('P53_list_not_the_contract_scope',"    need(list_sha==scope['list_sha256'],'LIST_NOT_THE_CONTRACT_SCOPE')\n","",refusal='LIST_NOT_THE_CONTRACT_SCOPE')
add('P54_list_hash_of_the_raw_list',"    list_sha=sha(canonical(names));commitment_sha=sha(commitment_raw)","    list_sha=commitment.get('list_sha256');commitment_sha=sha(commitment_raw)")
add('P55_audit_event_unchecked',"    need(set(audit)==K8_AUDIT_KEYS and audit['event_type']==K8_BUILT_EVENT and audit['occurred_at']==commitment.get('built_at')",
    "    need(set(audit)==K8_AUDIT_KEYS and audit['occurred_at']==commitment.get('built_at')",refusal='AUDIT_RECEIPT_NOT_BOUND')
add('P56_audit_instant_unchecked',"and audit['event_type']==K8_BUILT_EVENT and audit['occurred_at']==commitment.get('built_at')\n","and audit['event_type']==K8_BUILT_EVENT\n")
add('P57_audit_commitment_unchecked',"         and type(payload) is dict and payload.get('commitment_sha256')==commitment_sha and payload.get('list_sha256')==list_sha","         and type(payload) is dict and payload.get('list_sha256')==list_sha")
add('P58_audit_list_unchecked',"and payload.get('commitment_sha256')==commitment_sha and payload.get('list_sha256')==list_sha\n","and payload.get('commitment_sha256')==commitment_sha\n")
add('P59_audit_day_unchecked',"         and payload.get('epoch')==K8_EPOCH and payload.get('session')==day,'AUDIT_RECEIPT_NOT_BOUND')","         and payload.get('epoch')==K8_EPOCH,'AUDIT_RECEIPT_NOT_BOUND')")
add('P60_audit_epoch_unchecked',"         and payload.get('epoch')==K8_EPOCH and payload.get('session')==day,'AUDIT_RECEIPT_NOT_BOUND')","         and payload.get('session')==day,'AUDIT_RECEIPT_NOT_BOUND')")
add('P61_audit_member_set_unchecked',"    need(set(audit)==K8_AUDIT_KEYS and audit['event_type']","    need(audit.get('event_type')")
add('P62_causal_status',"    return {'epoch':K8_EPOCH,'session':day,'status':'AVAILABLE','symbols':names,","    return {'epoch':K8_EPOCH,'session':day,'status':'COMMITTED','symbols':names,")
add('P63_causal_without_the_commitment',"'list_sha256':list_sha,'commitment_sha256':commitment_sha}","'list_sha256':list_sha,'commitment_sha256':scope['list_sha256']}")
add('P64_payload_without_the_contract',"            payload=canonical({'contract':delivery['contract'],'causal':causal})","            payload=canonical({'contract':delivery['scope'],'causal':causal})")
add('P65_list_empty_inverted',"            summary['list_empty']=not causal['symbols']","            summary['list_empty']=bool(causal['symbols'])")
add('P66_chain_absence_reported_as_not_private',"('CHAIN_DOCUMENT_ABSENT','CHAIN_DOCUMENT_NOT_PRIVATE'),","('CHAIN_DOCUMENT_NOT_PRIVATE','CHAIN_DOCUMENT_NOT_PRIVATE'),",refusal='CHAIN_DOCUMENT_ABSENT')
add('P67_chain_bytes_not_compared',"                need(sha(raw)==pin['sha256'],'CHAIN_DOCUMENT_NOT_AS_PINNED')\n","",refusal='CHAIN_DOCUMENT_NOT_AS_PINNED')
add('P68_chain_read_from_the_config_root',"                raw=k8_read(host,pin['file'],held['documents'],gate,","                raw=k8_read(host,pin['file'],held['config'],gate,")
add('P69_destination_payload_not_looked_at',"            for key,root,name in layout+[('payload','payload',payload_name)]:","            for key,root,name in layout:")
add('P70_destinations_present_not_refused',"            need(not detail['precheck']['destinations_present'],'DESTINATION_PRESENT')\n","",refusal='DESTINATION_PRESENT')
add('P71_identity_rule_ignored',"            need(plan['identity_rule']=='REPORT_ONLY' or all(detail['precheck']['identities_equal'].values()),'CAPACITY_ROOT_IDENTITY_NOT_THE_CONFIG')",
    "            need(True or all(detail['precheck']['identities_equal'].values()),'CAPACITY_ROOT_IDENTITY_NOT_THE_CONFIG')",refusal='CAPACITY_ROOT_IDENTITY_NOT_THE_CONFIG')
add('P73_one_identity_enough',"            need(plan['identity_rule']=='REPORT_ONLY' or all(detail","            need(plan['identity_rule']=='REPORT_ONLY' or any(detail")
add('P74_identity_without_the_capacity_root',"    return sha(canonical([[K8_CAPACITY_NAME,capacity.identity[0],capacity.identity[1]],[held.name,held.identity[0],held.identity[1]]]))",
    "    return sha(canonical([[held.name,held.identity[0],held.identity[1]]]))")
add('P75_identity_with_the_host_name',"    return sha(canonical([[K8_CAPACITY_NAME,capacity.identity[0]","    return sha(canonical([[K8_VAR_LIB,capacity.identity[0]")
add('P76_identity_without_the_device',"[held.name,held.identity[0],held.identity[1]]]))","[held.name,held.identity[1]]]))")
add('P77_free_space_unchecked',"            need(free>=K8_FREE_BYTES_FLOOR,'CAPACITY_FREE_SPACE_BELOW_FLOOR')\n","",refusal='CAPACITY_FREE_SPACE_BELOW_FLOOR')
add('P78_free_space_exclusive',"            need(free>=K8_FREE_BYTES_FLOOR,","            need(free>K8_FREE_BYTES_FLOOR,")
BUDGET="            need(left>=K8_WRITE_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')\n"
add('P79_budget_unchecked',BUDGET,"",refusal='BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
add('P80_budget_exclusive',BUDGET,BUDGET.replace("left>=K8_WRITE_ALLOWANCE_SECONDS","left>K8_WRITE_ALLOWANCE_SECONDS"))
add('P81_no_gate_before_the_lookups',"    gate()\n    try:info=host.lstat(name,parent.fd)\n","    try:info=host.lstat(name,parent.fd)\n")
add('P82_any_failed_lookup_is_an_absence',"    try:info=host.lstat(name,parent.fd)\n    except FileNotFoundError:return None\n","    try:info=host.lstat(name,parent.fd)\n    except OSError:return None\n",refusal='PRECHECK_OS_ERROR')
add('P83_no_gate_before_the_first_observation',"    gate()                                                    # first gate call: before anything is observed\n","")
add('P84_run_never_marked_started',"    state.started=True\n    detail=","    detail=")
CAUGHT="            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')\n"
add('P85_precheck_failure_has_one_code',CAUGHT,"            code=code_of(error,'PRECHECK_OS_ERROR')\n",refusal='PRECHECK_FAILED')
REFUSE="        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK','delivered':None})\n"
add('P86_precheck_refusal_reported_as_effects_phase',REFUSE,REFUSE.replace("'phase_reached':'PRECHECK'","'phase_reached':'EFFECTS'"))
add('P87_precheck_failure_goes_on_to_the_effects',REFUSE,"")
add('P88_precheck_refusal_reported_as_a_partial',REFUSE,REFUSE.replace("finish(REFUSED_STATUS,REFUSED_OUTCOME,","finish(PARTIAL_STATUS,PARTIAL_OUTCOME,"))
add('P90_chain_before_the_commitment',"            # the seven chain documents every config pins: present in documents, private, with the pinned bytes\n            for role,pin in sorted(delivery['chain'].items()):",
    "            # the seven chain documents every config pins: present in documents, private, with the pinned bytes\n            for role,pin in sorted(delivery['chain'].items())[:0]:")
add('P91_capacity_identity_recorded_from_the_go_root',"detail['precheck']['identities_equal'][root]=k8_identity(capacity,held[root])==","detail['precheck']['identities_equal'][root]=k8_identity(capacity,held['go'])==")

# ---------------------------------------------------------------- the effects and what the run does with each failure
add('W01_files_created_in_the_documents_root',"row=k8_create_file(index,key,k8_path(root,name),content,K8_FILE_MODE,held[root],host,gate,state,go16)","row=k8_create_file(index,key,k8_path(root,name),content,K8_FILE_MODE,held['documents'],host,gate,state,go16)")
add('W02_files_created_with_the_core_name_rule',"row=k8_create_file(index,key,","row=create_file(index,key,")
add('W03_files_created_with_one_temporary_index',"row=k8_create_file(index,key,k8_path(root,name)","row=k8_create_file(0,key,k8_path(root,name)")
add('W04_payload_not_created',"[('payload','payload',payload_name,payload)]\n        for index","[]\n        for index")
add('W05_payload_created_first',"        stop=None;table=[(key,root,name,delivery['raws'][key]) for key,root,name in layout]+[('payload','payload',payload_name,payload)]",
    "        stop=None;table=[('payload','payload',payload_name,payload)]+[(key,root,name,delivery['raws'][key]) for key,root,name in layout]")
STOP="            if row['state']!='INSTALLED_DURABLE':stop=row['code'] or 'INSTALL_FAILED'\n"
add('W06_a_failed_file_does_not_stop_the_run',STOP,"")
add('W07_a_file_not_durable_is_success',STOP,STOP.replace("row['state']!='INSTALLED_DURABLE'","row['state'] not in ('INSTALLED_DURABLE','INSTALLED_NOT_DURABLE')"))
add('W08_not_attempted_rows_dropped',"                ledger.append({'key':key,'path':k8_path(root,name),'state':'NOT_ATTEMPTED','code':None});continue","                continue")
add('W09_readback_skipped',"            if stop is None:stop=readback_file(row,content,K8_FILE_MODE,held[root],host,gate)\n","            if False:stop=readback_file(row,content,K8_FILE_MODE,held[root],host,gate)\n")
add('W10_readback_against_the_wrong_mode',"            if stop is None:stop=readback_file(row,content,K8_FILE_MODE,held[root],host,gate)","            if stop is None:stop=readback_file(row,content,0o644,held[root],host,gate)")
add('W11_held_directories_not_verified',"        for key in ('capacity',)+K8_CAPACITY_ROOTS+('day','causal','receipts'):\n            if stop is None:","        for key in ():\n            if stop is None:",refusal='READBACK_UNAVAILABLE')
add('W13_delivered_hash_of_the_signed_bytes_of_another_file',"            files={row['key']:{'path':row['path'],'sha256':row['sha256_observed'],","            files={row['key']:{'path':row['path'],'sha256':ledger[0]['sha256_observed'],")
add('W14_delivered_includes_the_payload_row',"'gid':row['gid'],'links':row['links']} for row in ledger[:-1]}","'gid':row['gid'],'links':row['links']} for row in ledger}")
add('W15_delivered_payload_of_the_first_row',"            last=ledger[-1]\n","            last=ledger[0]\n")
add('W16_delivered_says_the_list_is_empty',"                                 'list_empty':summary['list_empty']},","                                 'list_empty':True},")
add('W17_delivered_identities_of_the_rule',"                       'root_identities_equal_the_config':dict(detail['precheck']['identities_equal']),'identity_rule':plan['identity_rule']}",
    "                       'root_identities_equal_the_config':{root:True for root in K8_IDENTITY_ROOTS},'identity_rule':plan['identity_rule']}")
add('W18_delivered_summary_given_for_a_run_that_stopped',"        delivered=None\n        if stop is None:\n","        delivered=None\n        if stop is None or state.succeeded>=13:\n")
add('W19_readback_reported_complete_when_it_stopped',"'readback':'COMPLETE' if stop is None else None,","'readback':'COMPLETE',")
add('W20_a_run_that_changed_the_host_is_a_refusal',"        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n","        if True:return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n")
add('W21_a_run_that_changed_nothing_is_a_partial',"        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n","")
add('W22_a_partial_reported_with_the_complete_status',"        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)\n","        return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,stop,extra)\n")
add('W23_effects_phase_reported_as_the_precheck',"        extra={'phase_reached':'EFFECTS',","        extra={'phase_reached':'PRECHECK',")
add('W24_payload_row_not_withheld',"        rows=[k8_withheld(row) if row['key']=='payload' else row for row in ledger]","        rows=list(ledger)")
add('W25_withheld_row_keeps_the_size',"    return dict(row,bytes=None,sha256_signed=None,sha256_observed=None,hash_and_size_withheld=True)","    return dict(row,sha256_signed=None,sha256_observed=None,hash_and_size_withheld=True)")
add('W26_withheld_row_keeps_the_observed_hash',"    return dict(row,bytes=None,sha256_signed=None,sha256_observed=None,hash_and_size_withheld=True)","    return dict(row,bytes=None,sha256_signed=None,hash_and_size_withheld=True)")
add('W27_withheld_row_keeps_the_signed_hash',"    return dict(row,bytes=None,sha256_signed=None,sha256_observed=None,hash_and_size_withheld=True)","    return dict(row,bytes=None,sha256_observed=None,hash_and_size_withheld=True)")
add('W28_objects_left_not_counted',"ledger=rows,objects_left_by_this_run=objects_left([],ledger),","ledger=rows,objects_left_by_this_run=0,")
add('W29_receipt_says_existing_objects_were_modified',"objects_left_by_this_run=objects_left([],ledger),pre_existing_objects_modified=False,**extra)))","objects_left_by_this_run=objects_left([],ledger),pre_existing_objects_modified=True,**extra)))")
add('W30_held_directories_left_open',"            if key in held:\n                try:held[key].close()","            if False:\n                try:held[key].close()")
add('W31_parents_left_open',"        for handle in pinned:\n            try:handle.close()","        for handle in []:\n            try:handle.close()")
add('W32_receipt_reductions_lose_the_first_step',"REDUCTIONS=[('PRECHECK_DROPPED',_reduce_precheck),('PARENT_REDUCED_TO_COUNT',_reduce_parent)]","REDUCTIONS=[('PARENT_REDUCED_TO_COUNT',_reduce_parent)]")
add('W33_receipt_reductions_lose_the_second_step',"REDUCTIONS=[('PRECHECK_DROPPED',_reduce_precheck),('PARENT_REDUCED_TO_COUNT',_reduce_parent)]","REDUCTIONS=[('PRECHECK_DROPPED',_reduce_precheck)]")
add('W34_delivered_contract_hash_of_the_payload',"                       'contract':{'sha256':sha(delivery['contract_raw']),'carried_whole_into_the_payload_file':True},","                       'contract':{'sha256':sha(payload),'carried_whole_into_the_payload_file':True},")
add('W35_payload_assembled_from_the_scope_list',"            payload=canonical({'contract':delivery['contract'],'causal':causal})\n","            payload=canonical({'contract':delivery['contract'],'causal':dict(causal,symbols=[])})\n")

# Not mutants, recorded as equivalent (each was in the first list of 2026-10-04 and was removed together with the code
# it named, or because no input can tell it apart):
#  - k8_named_in's 'not LEFTOVER' clause: no name of the grammar session=2026-10-0[6-9]... is a leftover name; the clause
#    was removed from op.py.
#  - k8_blob without hexpin(item['sha256']): the bytes' own SHA-256 is compared with it next, and no SHA-256 is zero or
#    upper case, so the same requests are refused with the same code.
#  - the identity rule test written as != 'REFUSE_ON_MISMATCH': the rule is one of exactly two values (validate_plan).
#  - a gate() before k8_causal(): the next host call (the first chain document's lstat) asks the gate; removed from op.py.
#  - a final verify of the two pinned chains (/var/lib and the K9 days): the capacity root's and the day directory's
#    verify walk the same rows; removed from op.py.

# ---------------------------------------------------------------- the core's create_file mutants, ported to K8's copy
HERE=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(HERE/'tests'))
import k8copy                                      # noqa: E402
def _core_mutants():
    spec=importlib.util.spec_from_file_location('_k8_core_mutants',HERE.parent/'core'/'mutation'/'mutants.py');module=importlib.util.module_from_spec(spec)
    sys.path.insert(0,str(HERE.parent/'core'/'mutation'))
    try:spec.loader.exec_module(module)
    finally:sys.path.remove(str(HERE.parent/'core'/'mutation'))
    return module
_CORE=_core_mutants()
_FILES=(HERE.parent/'core'/'parts'/'files.py').read_text(encoding='ascii')
_CREATE=k8copy.source_of(_FILES,'create_file')
PORTED=[]
for _name,_target,_old,_new in _CORE.MUTANTS:
    if _target=='files' and _old in _CREATE and _FILES.count(_old)==1:
        PORTED.append(('K'+_name,'op',k8copy.port(_old),k8copy.port(_new)))
PORTED.append(('K_N01_copy_admits_any_name','op',"            and k8_named_in(path,directory) and text(go16,'[0-9a-f]{16}')","            and True and text(go16,'[0-9a-f]{16}')"))

# ---------------------------------------------------------------- the dispatcher generated for this operation
LITERAL="('2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09','2026-10-10')"
DISPATCHER=[
    ('D71k_dispatcher_date_set_dropped','dispatcher',"need(start.date().isoformat() in "+LITERAL+" and end.date()==start.date(),'DISPATCH_DATE')","need(end.date()==start.date(),'DISPATCH_DATE')"),
    ('D72k_dispatcher_accepts_the_sunday_before','dispatcher',"start.date().isoformat() in ('2026-10-05',","start.date().isoformat() in ('2026-10-04','2026-10-05',"),
    ('D73k_dispatcher_accepts_the_day_after_the_epoch','dispatcher',"'2026-10-09','2026-10-10') and end.date()==start.date()","'2026-10-09','2026-10-10','2026-10-11') and end.date()==start.date()"),
]
CORE_ROWS_REPLACED=('D71_write_dispatcher_date_set_dropped','D72_write_dispatcher_accepts_friday_the_second')

MUTANTS=M+PORTED+DISPATCHER
COMBOS={}
REDUNDANT={}


# ---------------------------------------------------------------- the two tables against the source itself
def _load(path):
    raw=Path(path).read_bytes();name='_hostops02_k8_mutation_'+hashlib.sha256(raw).hexdigest()[:12]
    module=type(sys)(name);module.__dict__['__file__']='<assembled k8_eve.py>';sys.modules[name]=module
    exec(compile(raw,module.__dict__['__file__'],'exec'),module.__dict__);return module

def _members(value,prefix=''):
    out=[]
    for key in sorted(value):
        if type(value[key]) is dict and key not in ('days_parent','roots','pinned','chain_documents'):out+=_members(value[key],prefix+key+'.')
        else:out.append(prefix+key)
    return out

CALLERS=('need','Refused','code_of','k8_hold','k8_read','k8_blob','k8_json','k8_pin')
def codes_of(text):
    """Every constant code the operation part can raise outside its copy of create_file: the code of each need(),
    Refused() and code_of() fallback, every code handed to k8_hold, k8_read, k8_blob, k8_json and k8_pin, and the codes
    of the tuple named k9."""
    text=text.replace(k8copy.source_of(text,'k8_create_file'),'')
    found=set()
    for node in ast.walk(ast.parse(text)):
        values=[]
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in CALLERS:values=node.args
        if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='k9' for target in node.targets):values=[node.value]
        for argument in values:
            for item in ast.walk(argument):
                if isinstance(item,ast.Constant) and type(item.value) is str and re.fullmatch('[A-Z][A-Z0-9_]{2,79}',item.value):found.add(item.value)
    return found-{'REPORT_ONLY','COMPLETE','K9_STEP_RECEIPT_V1'}          # compared values, not codes

def coverage(here):
    """Errors when a member of effects_of() or a refusal of the operation part has no mutant named for it. The members
    of one file row ('files') and of the chain documents ('chain_documents') are answered by the mutant of the list."""
    here=Path(here);errors=[];names={row[0] for row in M};module=_load(here/'build'/'k8_eve.py')
    sys.path.insert(0,str(here/'tests'))
    try:
        import json as _json
        fixtures=_json.loads((here/'tests'/'fixtures'/'DAY_SETS.json').read_bytes());day='2026-10-06';files=fixtures['days'][day]['files']
        def blob(value):
            raw=base64.b64decode(value);return {'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'content_b64':value}
        rows=[{'path':path,'device':1,'inode':index+2,'uid':0,'gid':0,'mode':0o755 if index<4 else 0o700} for index,path in enumerate(
            ['/','/var','/var/lib','/var/lib/c3po','/var/lib/c3po/r2d2-v2-k9-20261005','/var/lib/c3po/r2d2-v2-k9-20261005/days'])]
        plan={'day':day,'windows':list(fixtures['windows']),'contract':blob(files['contract']),'files':{key:blob(value) for key,value in files.items() if key!='contract'},
              'days_parent':rows,'identity_rule':'REFUSE_ON_MISMATCH','evidence_boot_id_sha256':'a'*64}
        effects=module.effects_of(plan)
    finally:sys.path.remove(str(here/'tests'))
    wanted=set(_members(effects))
    for member in sorted(wanted):
        if EFFECTS.get(member) not in names:errors.append('effects member without a mutant: '+member)
    for member in EFFECTS:
        if member not in wanted:errors.append('mutant table names an effects member that does not exist: '+member)
    codes=codes_of((here/'op.py').read_text())
    for code in sorted(codes):
        if REFUSALS.get(code) not in names:errors.append('refusal without a mutant: '+code)
    for code in REFUSALS:
        if code not in codes:errors.append('mutant table names a refusal that does not exist: '+code)
    return errors
