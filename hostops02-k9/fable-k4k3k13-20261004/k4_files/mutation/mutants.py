"""The mutants of the K4 files family's own part. Each row: (name, target, exact anchor, replacement); target 'op' is
the built source build/k4_files.py, in which the anchor must occur exactly once (mutate.py check). The rule of the
family: one mutant per member of effects_of() (per mode), one per refusal of validate_plan and of the precheck; here
also the constants of the epoch and of the placement, the order of the precheck, and what the run does with each
failure of an effect. EFFECTS and REFUSALS name, for each member and each code, the mutant that answers for it;
coverage() compares both tables with the source itself, so a new member or a new refusal without a mutant is an error
of `mutate.py check`. Modelled on K4-E0's list."""
import ast
import hashlib
from pathlib import Path
import sys

M=[]
EFFECTS={}
REFUSALS={}
def add(name,old,new,effect=None,refusal=None):
    M.append((name,'op',old,new))
    for table,keys in ((EFFECTS,effect),(REFUSALS,refusal)):
        for key in ([keys] if type(keys) is str else keys or []):table.setdefault(key,name)

# ---------------------------------------------------------------- constants of the epoch, the placement and the files
add('C01_another_epoch',"K4_EPOCH='R2D2-V2-SHADOW-2026-10-05'","K4_EPOCH='R2D2-V2-SHADOW-2026-09-28'")
add('C02_reader_directory',"READER_CONFIG_DIRECTORY='/etc/c3po-reader'","READER_CONFIG_DIRECTORY='/etc/c3po-bar'")
add('C03_capacity_root',"CAPACITY_ROOT='/var/lib/c3po-capacity'","CAPACITY_ROOT='/var/lib/c3po-reader'")
add('C04_unit_directory',"UNIT_DIRECTORY='/etc/systemd/system'","UNIT_DIRECTORY='/usr/lib/systemd/system'")
add('C05_documents_root',"DOCUMENTS_DIRECTORY=CAPACITY_ROOT+'/documents'","DOCUMENTS_DIRECTORY=CAPACITY_ROOT+'/payload'")
add('C06_config_root',"CAPACITY_CONFIG_DIRECTORY=CAPACITY_ROOT+'/config'","CAPACITY_CONFIG_DIRECTORY=CAPACITY_ROOT+'/go'")
add('C07_static_config_name',"STATIC_CONFIG_NAME='week.static.capacity.json'","STATIC_CONFIG_NAME='static.capacity.json'")
add('C08_launcher_directory_name',"LAUNCHER_DIRECTORY_NAME='launcher'","LAUNCHER_DIRECTORY_NAME='launchers'")
add('C09_launcher_name',"LAUNCHER_NAME='reader_launcher.py'","LAUNCHER_NAME='launcher.py'")
add('C10_pins_name',"PINS_NAME='pins.env'","PINS_NAME='pin.env'")
add('C11_producer_unit_name',"PRODUCER_UNIT_NAME='c3po-massive.service'","PRODUCER_UNIT_NAME='c3po-massive.timer'")
add('C12_reader_unit_name',"READER_UNIT_NAME='c3po-reader.service'","READER_UNIT_NAME='c3po-reader-alert.service'")
add('C13_container_data_root',"CONTAINER_DATA_ROOT='/app/day-d-data'","CONTAINER_DATA_ROOT='/mnt/day-d-data'")
add('C14_container_capacity_root',"CONTAINER_CAPACITY_ROOT='/c3po-capacity'","CONTAINER_CAPACITY_ROOT='/app/c3po-capacity'")
add('C15_container_launcher_root',"CONTAINER_LAUNCHER_ROOT='/c3po-reader'","CONTAINER_LAUNCHER_ROOT='/c3po-launcher'")
add('C16_another_release',"K4_RELEASE_SHA='fc2f64ea252f9996ba62cd8bb10411ea0cbc3a351c15b8612de88390ccbdcaa1'",
    "K4_RELEASE_SHA='fc2f64ea252f9996ba62cd8bb10411ea0cbc3a351c15b8612de88390ccbdcaa2'")
add('C17_another_package',"K4_PACKAGE_SHA='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'",
    "K4_PACKAGE_SHA='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb85'")
add('C18_another_revision',"K4_CODE_REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'","K4_CODE_REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e859'")
add('C19_four_sessions',"K4_SESSIONS=('2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09')",
    "K4_SESSIONS=('2026-10-05','2026-10-06','2026-10-07','2026-10-08')")
add('C20_config_schema',"STATIC_CONFIG_SCHEMA='R2D2_CAPACITY_BOOTSTRAP_V3'","STATIC_CONFIG_SCHEMA='R2D2_CAPACITY_BOOTSTRAP_V2'")
add('C21_veto_mode',"K4_VETO_MODE='DISPATCH_AND_DERIVATION_ONLY'","K4_VETO_MODE='DISPATCH_ONLY'")
add('C22_two_capacity_roots',"CAPACITY_ROOT_NAMES=('documents','payload','go')","CAPACITY_ROOT_NAMES=('documents','payload')")
add('C23_document_file_grammar_without_equal',"K4_DOCUMENT_FILE='[A-Za-z0-9][A-Za-z0-9._=-]{0,127}'","K4_DOCUMENT_FILE='[A-Za-z0-9][A-Za-z0-9._-]{0,127}'")
add('C24_static_config_limit_larger',"MAX_STATIC_CONFIG_BYTES=16384","MAX_STATIC_CONFIG_BYTES=65536")
add('C25_launcher_limit_larger',"MAX_LAUNCHER_BYTES=32768","MAX_LAUNCHER_BYTES=65536")
add('C26_launcher_limit_one_byte_less',"MAX_LAUNCHER_BYTES=32768","MAX_LAUNCHER_BYTES=32767")
add('C27_free_floor_one_byte_more',"FREE_BYTES_FLOOR=1048576 ","FREE_BYTES_FLOOR=1048577 ")
add('C28_free_floor_one_block_less',"FREE_BYTES_FLOOR=1048576 ","FREE_BYTES_FLOOR=1044480 ")
add('C29_allowance_one_second_less',"WRITE_ALLOWANCE_SECONDS=15 ","WRITE_ALLOWANCE_SECONDS=14 ")
add('C30_allowance_one_second_more',"WRITE_ALLOWANCE_SECONDS=15 ","WRITE_ALLOWANCE_SECONDS=16 ")
add('C31_date_class_of_the_sessions',"DATE_CLASS='WRITE_EPOCH'","DATE_CLASS='WRITE_SESSIONS'")
add('C32_provisioning_not_required',"EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,PROVISION_OPERATION)","EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,)")
add('C33_precheck_not_required',"EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,PROVISION_OPERATION)","EVIDENCE_OPERATIONS=(PROVISION_OPERATION,)")
add('C34_evidence_not_required',"EVIDENCE_REQUIRED=True","EVIDENCE_REQUIRED=False")
add('C35_gate_span_of_a_read',"MAX_GATE_SPAN_SECONDS=900","MAX_GATE_SPAN_SECONDS=3600")
add('C36_activation_allowed',"ACTIVATION_ALLOWED=False","ACTIVATION_ALLOWED=True")
add('C37_scope_says_a_process_is_started',"'processes_started':0,","'processes_started':1,")
add('C38_plan_has_one_more_member',"PLAN_KEYS=frozenset(('mode','delivery','evidence_boot_id_sha256'))","PLAN_KEYS=frozenset(('mode','delivery','evidence_boot_id_sha256','e0'))")
add('C40_pins_names_out_of_order',"PINS_NAMES=('C3PO_BUILD_SHA','C3PO_R2D2_V2_SHADOW_RELEASE_FILE',","PINS_NAMES=('C3PO_R2D2_V2_SHADOW_RELEASE_FILE','C3PO_BUILD_SHA',")
add('C41_poll_seconds_constant',"                'C3PO_R2D2_V2_SHADOW_POLL_SECONDS':'1.0'}","                'C3PO_R2D2_V2_SHADOW_POLL_SECONDS':'1'}")
add('C42_raw_directory_constant',"CONTAINER_DATA_ROOT+'/provider=eodhd/microstructure/raw'","CONTAINER_DATA_ROOT+'/provider=eodhd/microstructure'")
add('C43_capacity_not_required',"'C3PO_R2D2_V2_CAPACITY_REQUIRED':'true'","'C3PO_R2D2_V2_CAPACITY_REQUIRED':'false'")
add('C45_journal_grammar_admits_any_child',"JOURNAL_TARGET_PATTERN='/c3po-[a-z0-9][a-z0-9-]*'","JOURNAL_TARGET_PATTERN='/[a-z0-9][a-z0-9-]*'")
add('C46_journal_may_be_the_launcher_target',"JOURNAL_TARGETS_TAKEN=(CONTAINER_CAPACITY_ROOT,CONTAINER_LAUNCHER_ROOT)","JOURNAL_TARGETS_TAKEN=(CONTAINER_CAPACITY_ROOT,)")
add('C47_units_expected_private',"UNIT_FILE_MODE=0o644","UNIT_FILE_MODE=0o600")
add('C48_unit_limit_tiny',"MAX_UNIT_BYTES=65536","MAX_UNIT_BYTES=64")
add('C49_scope_never_loses_the_second_attempt',",'a container','a second attempt'],",",'a container'],")

# ---------------------------------------------------------------- the compiled chain and the bytes of the request
add('V01_compiled_size_not_checked',"    need(len(raw)==size and sha(raw)==digest,'CHAIN_DOCUMENT_NOT_THE_COMPILED_HASH')","    need(sha(raw)==digest,'CHAIN_DOCUMENT_NOT_THE_COMPILED_HASH')",
    refusal='CHAIN_DOCUMENT_NOT_THE_COMPILED_HASH')
add('V02_compiled_hash_not_checked',"    need(len(raw)==size and sha(raw)==digest,'CHAIN_DOCUMENT_NOT_THE_COMPILED_HASH')","    need(len(raw)==size,'CHAIN_DOCUMENT_NOT_THE_COMPILED_HASH')")
SIGNED="    need(type(item) is dict and set(item)==set(K4_BYTES_KEYS) and hexpin(item['sha256']) and integer(item['bytes'],1,limit)\n"
add('V03_bytes_member_keys_not_checked',SIGNED,SIGNED.replace(" and set(item)==set(K4_BYTES_KEYS)",""),refusal=['STATIC_CONFIG_BYTES_NOT_THE_SIGNED_HASH','LAUNCHER_BYTES_NOT_THE_SIGNED_HASH'])
add('V04_bytes_limit_not_checked',SIGNED,SIGNED.replace("integer(item['bytes'],1,limit)","integer(item['bytes'],1)"))
add('V05_base64_not_strict',"    try:raw=base64.b64decode(item['content_b64'].encode('ascii'),validate=True)\n    except (ValueError,UnicodeEncodeError):raise Refused(code) from None",
    "    try:raw=base64.b64decode(item['content_b64'].encode('ascii'),validate=False)\n    except (ValueError,UnicodeEncodeError):raise Refused(code) from None")
add('V06_bytes_not_compared',"    need(len(raw)==item['bytes'] and sha(raw)==item['sha256'],code)","    need(len(raw)==item['bytes'],code)")
add('V07_bytes_size_not_compared',"    need(len(raw)==item['bytes'] and sha(raw)==item['sha256'],code)","    need(sha(raw)==item['sha256'],code)")
add('V08_chain_receives_no_entry',"    validate_chain(rows,path,open_root=None,receives_entry=True)\n","    validate_chain(rows,path,open_root=None,receives_entry=False)\n",refusal='PARENT_SETGID')
add('V09_chain_group_not_checked',"    need(all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows),'CHAIN_NOT_ROOT_CONTROLLED')",
    "    need(all(not row['mode']&stat.S_ISGID for row in rows),'CHAIN_NOT_ROOT_CONTROLLED')",refusal='CHAIN_NOT_ROOT_CONTROLLED')
add('V10_chain_setgid_not_checked',"    need(all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows),'CHAIN_NOT_ROOT_CONTROLLED')",
    "    need(all(row['gid']==0 for row in rows),'CHAIN_NOT_ROOT_CONTROLLED')")
add('V11_parent_not_required_0700',"    need((rows[-1]['uid'],rows[-1]['gid'],rows[-1]['mode'])==(0,0,PRIVATE_DIRECTORY_MODE),'PARENT_NOT_ROOT_0700')",
    "    need((rows[-1]['uid'],rows[-1]['gid'])==(0,0),'PARENT_NOT_ROOT_0700')",refusal='PARENT_NOT_ROOT_0700')
add('V12_open_root_at_the_capacity_tree',"    validate_chain(rows,path,open_root=None,receives_entry=True)\n","    validate_chain(rows,path,open_root='/var',receives_entry=True)\n",refusal='CHAIN_ROW_UNSAFE')

# ---------------------------------------------------------------- the static config
add('S01_not_canonical_accepted',"    need(type(config) is dict and canonical(config)==raw and set(config)==set(STATIC_CONFIG_KEYS),'STATIC_CONFIG_INVALID')",
    "    need(type(config) is dict and set(config)==set(STATIC_CONFIG_KEYS),'STATIC_CONFIG_INVALID')",refusal='STATIC_CONFIG_INVALID')
add('S02_keys_not_checked',"    need(type(config) is dict and canonical(config)==raw and set(config)==set(STATIC_CONFIG_KEYS),'STATIC_CONFIG_INVALID')",
    "    need(type(config) is dict and canonical(config)==raw and set(config)>=set(STATIC_CONFIG_KEYS),'STATIC_CONFIG_INVALID')")
add('S03_schema_not_checked',"    need(config['schema']==STATIC_CONFIG_SCHEMA and config['r2d2_v2_capacity_veto_mode']","    need(config['r2d2_v2_capacity_veto_mode']")
add('S04_veto_mode_not_checked',"config['r2d2_v2_capacity_veto_mode']==K4_VETO_MODE and config['restore_revocation'] is None","config['restore_revocation'] is None")
add('S05_revocation_accepted',"and config['restore_revocation'] is None\n         and hexpin(config['calendar_pin_sha'])","\n         and hexpin(config['calendar_pin_sha'])")
add('S06_calendar_pin_not_checked',"         and hexpin(config['calendar_pin_sha']),'STATIC_CONFIG_INVALID')","         and True,'STATIC_CONFIG_INVALID')")
add('S11_release_not_checked',"    need(config['release_sha']==K4_RELEASE_SHA and config['package_sha']==K4_PACKAGE_SHA,'STATIC_CONFIG_RELEASE')",
    "    need(config['package_sha']==K4_PACKAGE_SHA,'STATIC_CONFIG_RELEASE')",refusal='STATIC_CONFIG_RELEASE')
add('S12_package_not_checked',"    need(config['release_sha']==K4_RELEASE_SHA and config['package_sha']==K4_PACKAGE_SHA,'STATIC_CONFIG_RELEASE')",
    "    need(config['release_sha']==K4_RELEASE_SHA,'STATIC_CONFIG_RELEASE')")
add('S13_pin_labels_not_checked',"    need(type(pins) is dict and set(pins)==set(CHAIN_LABELS)|{'TEMPLATE'},'STATIC_CONFIG_CHAIN_PINS')",
    "    need(type(pins) is dict and set(pins)>=set(CHAIN_LABELS)|{'TEMPLATE'},'STATIC_CONFIG_CHAIN_PINS')",refusal='STATIC_CONFIG_CHAIN_PINS')
add('S14_chain_pins_not_compared',"need(pins[label]=={'file':name,'sha256':digest},'STATIC_CONFIG_CHAIN_PINS')","need(pins[label]['file']==name,'STATIC_CONFIG_CHAIN_PINS')")
add('S15_chain_pin_names_not_compared',"need(pins[label]=={'file':name,'sha256':digest},'STATIC_CONFIG_CHAIN_PINS')","need(pins[label]['sha256']==digest,'STATIC_CONFIG_CHAIN_PINS')")
add('S16_template_day_not_checked',"         and template['file'] in ['session='+day+'.template.md' for day in K4_SESSIONS],'STATIC_CONFIG_ANCHOR')",
    "         and template['file'].endswith('.template.md'),'STATIC_CONFIG_ANCHOR')",refusal='STATIC_CONFIG_ANCHOR')
add('S17_template_hash_not_checked',"    need(type(template) is dict and set(template)=={'file','sha256'} and hexpin(template['sha256'])",
    "    need(type(template) is dict and set(template)=={'file','sha256'}")
add('S18_several_views_accepted',"    need(type(views) is dict and len(views)==1 and template['file']","    need(type(views) is dict and len(views)>=1 and template['file']")
add('S19_view_of_another_day',"len(views)==1 and template['file']=='session='+list(views)[0]+'.template.md','STATIC_CONFIG_ANCHOR')","len(views)==1,'STATIC_CONFIG_ANCHOR')")
add('S20_view_file_prefix_not_checked',"         and view['file'].startswith('session='+list(views)[0]+'.view-'),'STATIC_CONFIG_ANCHOR')","         and True,'STATIC_CONFIG_ANCHOR')")
add('S21_view_keys_not_checked',"    need(type(view) is dict and set(view)=={'file','sha256'} and hexpin(view['sha256'])","    need(type(view) is dict and hexpin(view['sha256'])")
add('S23_roots_keys_not_checked',"    need(type(roots) is dict and set(roots)==set(CAPACITY_ROOT_NAMES)\n","    need(type(roots) is dict and set(roots)>=set(CAPACITY_ROOT_NAMES)\n")
add('S24_root_members_not_checked',"all(type(roots[name]) is dict and set(roots[name])=={'path','identity'} and roots","all(type(roots[name]) is dict and roots")
add('S25_static_config_not_judged',"MAX_STATIC_CONFIG_BYTES,'STATIC_CONFIG_BYTES_NOT_THE_SIGNED_HASH');static_config_of(raw)","MAX_STATIC_CONFIG_BYTES,'STATIC_CONFIG_BYTES_NOT_THE_SIGNED_HASH')")

# ---------------------------------------------------------------- pins.env
add('P01_value_names_not_checked',"    need(type(values) is dict and set(values)==set(PINS_NAMES) and all(type(value) is str for value in values.values()),'PINS_VALUES_INVALID')",
    "    need(type(values) is dict and set(values)>=set(PINS_NAMES) and all(type(value) is str for value in values.values()),'PINS_VALUES_INVALID')",refusal='PINS_VALUES_INVALID')
add('P02_value_types_not_checked'," and all(type(value) is str for value in values.values()),'PINS_VALUES_INVALID')",",'PINS_VALUES_INVALID')")
add('P03_constants_not_compared',"    for name,value in PINS_CONSTANTS.items():need(values[name]==value,'PINS_CONSTANT_MISMATCH')",
    "    for name,value in PINS_CONSTANTS.items():need(type(values[name]) is str,'PINS_CONSTANT_MISMATCH')",refusal='PINS_CONSTANT_MISMATCH')
add('P04_release_file_any_depth',"    need(container_path(values['C3PO_R2D2_V2_SHADOW_RELEASE_FILE'],2),'PINS_RELEASE_FILE')","    need(container_path(values['C3PO_R2D2_V2_SHADOW_RELEASE_FILE'],1) or container_path(values['C3PO_R2D2_V2_SHADOW_RELEASE_FILE'],2),'PINS_RELEASE_FILE')",
    refusal='PINS_RELEASE_FILE')
add('P06_container_path_outside_the_data_root',"clean_path(value) and value.startswith(CONTAINER_DATA_ROOT+'/') and len(parts)","clean_path(value) and len(parts)")
add('P09_journal_grammar_not_applied',"    need(text(journal,JOURNAL_TARGET_PATTERN) and journal not in JOURNAL_TARGETS_TAKEN,'PINS_JOURNAL_DIR')",
    "    need(journal not in JOURNAL_TARGETS_TAKEN,'PINS_JOURNAL_DIR')",refusal='PINS_JOURNAL_DIR')
add('P10_journal_taken_targets_accepted',"    need(text(journal,JOURNAL_TARGET_PATTERN) and journal not in JOURNAL_TARGETS_TAKEN,'PINS_JOURNAL_DIR')",
    "    need(text(journal,JOURNAL_TARGET_PATTERN),'PINS_JOURNAL_DIR')")
add('P14_hashes_not_checked',"    need(all(hexpin(value) for value in digests),'PINS_HASH_INVALID')","    need(all(type(value) is str for value in digests),'PINS_HASH_INVALID')",refusal='PINS_HASH_INVALID')
add('P15_reuse_not_checked',"    need(len(set(digests+(K4_RELEASE_SHA,)))==3,'PINS_HASH_REUSED')","    need(len(set(digests+(K4_RELEASE_SHA,)))>=2,'PINS_HASH_REUSED')",refusal='PINS_HASH_REUSED')
add('P16_lines_without_newline',"    return ''.join(name+'='+values[name]+'\\n' for name in PINS_NAMES).encode('ascii')","    return '\\n'.join(name+'='+values[name] for name in PINS_NAMES).encode('ascii')")
add('P17_lines_sorted',"    return ''.join(name+'='+values[name]+'\\n' for name in PINS_NAMES).encode('ascii')","    return ''.join(name+'='+values[name]+'\\n' for name in sorted(PINS_NAMES)).encode('ascii')")

# ---------------------------------------------------------------- delivery_of and validate_plan
add('D01_mode_not_checked',"    mode=plan['mode'];need(type(mode) is str and mode in K4_MODES,'MODE_INVALID')","    mode=plan['mode'];need(type(mode) is str,'MODE_INVALID')",refusal='MODE_INVALID')
add('D02_delivery_keys_not_checked',"    item=plan['delivery'];need(type(item) is dict and set(item)==set(K4_DELIVERY_KEYS[mode]),'DELIVERY_INVALID')",
    "    item=plan['delivery'];need(type(item) is dict and set(item)>=set(K4_DELIVERY_KEYS[mode]),'DELIVERY_INVALID')",refusal='DELIVERY_INVALID')
add('D03_capacity_chains_may_diverge',"        need(documents[:-1]==config[:-1],'CAPACITY_CHAIN_DIVERGES')","        need(len(documents)==len(config),'CAPACITY_CHAIN_DIVERGES')",refusal='CAPACITY_CHAIN_DIVERGES')
add('D04_pins_hash_not_compared',"and item['sha256']==sha(raw) and item['bytes']==len(raw),'PINS_BYTES_NOT_THE_SIGNED_HASH')","and item['bytes']==len(raw),'PINS_BYTES_NOT_THE_SIGNED_HASH')",
    refusal='PINS_BYTES_NOT_THE_SIGNED_HASH')
add('D05_pins_size_not_compared',"and item['sha256']==sha(raw) and item['bytes']==len(raw),'PINS_BYTES_NOT_THE_SIGNED_HASH')","and item['sha256']==sha(raw),'PINS_BYTES_NOT_THE_SIGNED_HASH')")
add('D06_unit_hashes_may_be_equal',"             and item['producer_unit_sha256']!=item['reader_unit_sha256'],'UNIT_HASH_INVALID')","             ,'UNIT_HASH_INVALID')",refusal='UNIT_HASH_INVALID')
add('D07_unit_hash_not_a_pin',"        need(hexpin(item['producer_unit_sha256']) and hexpin(item['reader_unit_sha256'])","        need(True")
add('D08_unit_chain_not_root_controlled',"        need(all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in item['unit_parent']),'CHAIN_NOT_ROOT_CONTROLLED')\n","")
add('D09_unit_chain_open',"        validate_chain(item['unit_parent'],UNIT_DIRECTORY,open_root=None)","        validate_chain(item['unit_parent'],UNIT_DIRECTORY,open_root='/etc')")
add('D10_pins_reader_chain_not_judged',"        private_chain(item['reader_parent'],READER_CONFIG_DIRECTORY);private_chain(item['config_parent'],CAPACITY_CONFIG_DIRECTORY)",
    "        private_chain(item['config_parent'],CAPACITY_CONFIG_DIRECTORY)")
add('D11_pins_config_chain_not_judged',"        private_chain(item['reader_parent'],READER_CONFIG_DIRECTORY);private_chain(item['config_parent'],CAPACITY_CONFIG_DIRECTORY)",
    "        private_chain(item['reader_parent'],READER_CONFIG_DIRECTORY)")
add('D12_launcher_chain_not_judged',"    private_chain(item['reader_parent'],READER_CONFIG_DIRECTORY)\n    raw=signed_bytes(item['launcher']","    raw=signed_bytes(item['launcher']")
add('D13_boot_not_checked',"    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')","    need(True,'EVIDENCE_BOOT_UNBOUND')",refusal='EVIDENCE_BOOT_UNBOUND')
add('D14_static_config_written_in_the_documents_root',"    return mode,item,files+[('STATIC_CONFIG',CAPACITY_CONFIG_DIRECTORY+'/'+STATIC_CONFIG_NAME,raw)]",
    "    return mode,item,files+[('STATIC_CONFIG',DOCUMENTS_DIRECTORY+'/'+STATIC_CONFIG_NAME,raw)]")
add('D15_a_chain_document_left_out',"files=[('CHAIN_'+label,DOCUMENTS_DIRECTORY+'/'+name,chain_document_bytes(index)) for index,(label,name,_,_,_) in enumerate(K4_CHAIN_DOCUMENTS)]",
    "files=[('CHAIN_'+label,DOCUMENTS_DIRECTORY+'/'+name,chain_document_bytes(index)) for index,(label,name,_,_,_) in enumerate(K4_CHAIN_DOCUMENTS[:-1])]")

# ---------------------------------------------------------------- effects_of: one per member
add('E01_effects_operation',"    out={'operation':OPERATION,'epoch':K4_EPOCH,'mode':mode,","    out={'operation':OPERATION[:-1],'epoch':K4_EPOCH,'mode':mode,",effect='operation')
add('E02_effects_epoch',"    out={'operation':OPERATION,'epoch':K4_EPOCH,'mode':mode,","    out={'operation':OPERATION,'epoch':K4_EPOCH[:-1],'mode':mode,",effect='epoch')
add('E03_effects_mode',"    out={'operation':OPERATION,'epoch':K4_EPOCH,'mode':mode,","    out={'operation':OPERATION,'epoch':K4_EPOCH,'mode':K4_MODES[0],",effect='mode')
add('E04_effects_files_key',"'files':[dict(file_effect(path,raw),key=key) for key,path,raw in files],","'files':[dict(file_effect(path,raw),key=path) for key,path,raw in files],",effect='files')
FE="    return {'path':path,'sha256':sha(raw),'bytes':len(raw),'mode_octal':'%04o'%PRIVATE_FILE_MODE,'uid':0,'gid':0,'links':1,'expect':'ABSENT'}"
add('E05_effects_file_hash',FE,FE.replace("'sha256':sha(raw)","'sha256':sha(raw[:-1])"))
add('E06_effects_file_size',FE,FE.replace("'bytes':len(raw)","'bytes':len(raw)+1"))
add('E07_effects_file_mode',FE,FE.replace("'%04o'%PRIVATE_FILE_MODE","'0644'"))
add('E08_effects_file_owner',FE,FE.replace("'uid':0,'gid':0","'uid':0,'gid':1000"))
add('E09_effects_file_links',FE,FE.replace("'links':1","'links':2"))
add('E10_effects_file_expect',FE,FE.replace("'expect':'ABSENT'","'expect':'ANY'"))
add('E11_effects_file_path',FE,FE.replace("{'path':path,","{'path':path+'.new',"))
add('E12_effects_boot',"         'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],'pre_existing_objects_modified':False,'secret_written':False,",
    "         'evidence_boot_id_sha256':None,'pre_existing_objects_modified':False,'secret_written':False,",effect='evidence_boot_id_sha256')
add('E13_effects_flags',"         'activation':False,'container_touched':False,'process_started':False}","         'activation':False,'container_touched':False,'process_started':None}",
    effect=['activation','container_touched','process_started','pre_existing_objects_modified','secret_written'])
add('E14_effects_documents_parent',"        out.update(documents_parent=chain_effects(item['documents_parent']),config_parent=chain_effects(item['config_parent']),directories=[],",
    "        out.update(documents_parent=chain_effects(item['config_parent']),config_parent=chain_effects(item['config_parent']),directories=[],",effect='documents_parent')
add('E15_effects_static_config',"                   static_config={'release_sha':K4_RELEASE_SHA,'package_sha':K4_PACKAGE_SHA,'chain_pins':'EQUAL_TO_THE_SEVEN_DELIVERED_DOCUMENTS'})",
    "                   static_config={'release_sha':K4_RELEASE_SHA,'package_sha':K4_PACKAGE_SHA})",effect=['static_config','static_config.release_sha','static_config.package_sha','static_config.chain_pins'])
add('E16_effects_config_parent_of_pins',"        out.update(reader_parent=chain_effects(item['reader_parent']),config_parent=chain_effects(item['config_parent']),\n",
    "        out.update(reader_parent=chain_effects(item['reader_parent']),config_parent=chain_effects(item['reader_parent']),\n",effect=['config_parent','reader_parent'])
add('E17_effects_unit_parent',"                   unit_parent=chain_effects(item['unit_parent']),directories=[],values=dict(values),",
    "                   unit_parent=chain_effects(item['reader_parent']),directories=[],values=dict(values),",effect='unit_parent')
add('E18_effects_values',"                   unit_parent=chain_effects(item['unit_parent']),directories=[],values=dict(values),",
    "                   unit_parent=chain_effects(item['unit_parent']),directories=[],values={},",effect='values')
add('E19_effects_required_config',"                                                          'sha256':values['C3PO_R2D2_V2_CAPACITY_CONFIG_SHA']},",
    "                                                          'sha256':values['C3PO_READER_LAUNCHER_SHA256']},",effect=['required_on_the_host','required_on_the_host.static_config'])
add('E20_effects_required_launcher',"'launcher':{'path':LAUNCHER_DIRECTORY+'/'+LAUNCHER_NAME,'sha256':values['C3PO_READER_LAUNCHER_SHA256']},",
    "'launcher':{'path':LAUNCHER_DIRECTORY+'/'+LAUNCHER_NAME,'sha256':values['C3PO_R2D2_V2_CAPACITY_CONFIG_SHA']},",effect='required_on_the_host.launcher')
add('E21_effects_required_producer',"'producer_unit':{'path':UNIT_DIRECTORY+'/'+PRODUCER_UNIT_NAME,'sha256':item['producer_unit_sha256']},",
    "'producer_unit':{'path':UNIT_DIRECTORY+'/'+PRODUCER_UNIT_NAME,'sha256':item['reader_unit_sha256']},",effect='required_on_the_host.producer_unit')
add('E22_effects_required_reader',"'reader_unit':{'path':UNIT_DIRECTORY+'/'+READER_UNIT_NAME,'sha256':item['reader_unit_sha256']},",
    "'reader_unit':{'path':UNIT_DIRECTORY+'/'+READER_UNIT_NAME,'sha256':item['producer_unit_sha256']},",effect='required_on_the_host.reader_unit')
add('E24_effects_launcher_directory',"directories=[{'path':LAUNCHER_DIRECTORY,'mode_octal':'%04o'%PRIVATE_DIRECTORY_MODE,'uid':0,'gid':0,'expect':'ABSENT','entries_after':1}])",
    "directories=[{'path':LAUNCHER_DIRECTORY,'mode_octal':'%04o'%PRIVATE_DIRECTORY_MODE,'uid':0,'gid':0,'expect':'ABSENT','entries_after':2}])",effect='directories')

# ---------------------------------------------------------------- the precheck
add('H01_identity_not_checked',"            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n","",refusal='EXECUTOR_IDENTITY')
add('H02_umask_not_set',"            host.umask(0o077)\n","")
add('H03_boot_not_checked',"            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')\n","",refusal='EVIDENCE_FROM_EARLIER_BOOT')
add('H33_first_of_several_binds',"    return found[0] if len(found)==1 else None","    return found[0] if found else None")
add('H34_journal_sources_not_compared',"produced is not None and read is not None and produced==read and","produced is not None and read is not None and")
add('H35_journal_root_argument_not_checked'," and ('--journal-root '+journal+' ') in producer,'JOURNAL_BIND_MISMATCH')",",'JOURNAL_BIND_MISMATCH')")
add('H38_launcher_bind_not_checked',"\n         and bind_source(reader,CONTAINER_LAUNCHER_ROOT,',readonly')==LAUNCHER_DIRECTORY,'READER_UNIT_MOUNTS_MISMATCH')",",'READER_UNIT_MOUNTS_MISMATCH')")

# ---------------------------------------------------------------- the effects and what the run does with each failure
add('W01_failed_file_does_not_stop',"            if row['state']!='INSTALLED_DURABLE':stop=row['code'] or 'INSTALL_FAILED'\n","            pass\n")
add('W02_failed_directory_does_not_stop',"            if entry['state']!='CREATED_DURABLE':stop=entry['code'] or 'CREATION_FAILED'\n","            pass\n")
add('W03_files_not_read_back',"            if stop is None:stop=readback_file(row,raw,PRIVATE_FILE_MODE,directory,host,gate)\n","            pass\n",refusal='READBACK_UNAVAILABLE')
add('W04_launcher_directory_not_read_back',"            stop=readback_directory(LAUNCHER_DIRECTORY,PRIVATE_DIRECTORY_MODE,handles['LAUNCHER_DIRECTORY'],host,gate,1)\n","            stop=None\n")
add('W05_capacity_roots_not_read_back',"                if stop is None:stop=readback_directory(path,PRIVATE_DIRECTORY_MODE,handles[key],host,gate,entries[key]+after[key])\n","                pass\n")
add('W06_capacity_roots_count_without_the_new_files',"handles[key],host,gate,entries[key]+after[key])","handles[key],host,gate,entries[key])")
add('W07_parents_not_verified_at_the_end',"                try:handle.verify(gate)\n                except Exception as error:stop=code_of(error,'READBACK_UNAVAILABLE')",
    "                try:pass\n                except Exception as error:stop=code_of(error,'READBACK_UNAVAILABLE')")
add('W08_partial_reported_as_refusal',"        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n","        return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n")
add('W09_refusal_reported_as_partial',"        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n","")
add('W10_files_created_0644',"            row=create_file(index,key,path,raw,PRIVATE_FILE_MODE,directory,host,gate,state,go16);ledger.append(row)",
    "            row=create_file(index,key,path,raw,0o644,directory,host,gate,state,go16);ledger.append(row)")
add('W13_static_config_into_documents',"                targets=[handles['DOCUMENTS']]*(len(files)-1)+[handles['CONFIG']]","                targets=[handles['DOCUMENTS']]*len(files)")
add('W14_refused_precheck_not_a_refusal',"        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK','delivered':None})",
    "        if code is not None:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,code,{'phase_reached':'PRECHECK','delivered':None})")
add('W15_delivered_hash_signed_not_observed',"'files':[{'key':row['key'],'path':row['path'],'sha256':row['sha256_observed'],","'files':[{'key':row['key'],'path':row['path'],'sha256':None,")

add('H36_reader_journal_bind_may_be_writable',"read=bind_source(reader,journal,',readonly')","read=bind_source(reader,journal,',readonly') or bind_source(reader,journal,'')")
add('W16_free_space_of_the_first_filesystem_only',"            for handle in pinned[:2 if mode=='CHAIN_STATIC' else 1]:","            for handle in pinned[:1]:")
# (Removed as equivalent after the first run of 2026-10-05: the README path grammar and the "no empty, . or .. component"
# check of pins_lines are implied by the core's clean_path, which is stricter; the .hostops leftover exclusion of the
# config file name is implied by FILE_NAME (a leftover begins with a dot). The code was removed with its mutants.)

add('H14_units_not_text_checked',"                source=journal_and_mounts(producer,reader_unit,values,item['config_parent'][-2]['path'])\n","                source=None\n",
    refusal=['JOURNAL_BIND_MISMATCH','READER_UNIT_MOUNTS_MISMATCH'])
add('H15_non_ascii_unit_accepted',"                except UnicodeDecodeError:raise Refused('JOURNAL_BIND_MISMATCH') from None",
    "                except UnicodeDecodeError:producer,reader_unit=producer.decode('latin-1'),reader_unit.decode('latin-1')")
add('H16_launcher_directory_not_held',"                launcher=private_child(host,LAUNCHER_DIRECTORY_NAME,reader,gate,'LAUNCHER_DIRECTORY');held.append(launcher)",
    "                launcher=private_child(host,LAUNCHER_DIRECTORY_NAME,reader,gate,'LAUNCHER_DIRECTORY')",
    refusal=['LAUNCHER_DIRECTORY_ABSENT','LAUNCHER_DIRECTORY_INVALID','LAUNCHER_DIRECTORY_CHANGED_DURING_PRECHECK'])
add('H18_free_space_not_checked',"                need(free>=FREE_BYTES_FLOOR,'FREE_SPACE_BELOW_FLOOR')\n","",refusal='FREE_SPACE_BELOW_FLOOR')
add('H19_budget_not_checked',"            need(left>=WRITE_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')\n","",refusal='BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
add('H20_precheck_os_error_named_failed',"            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')\n",
    "            code=code_of(error,'PRECHECK_FAILED')\n",refusal=['PRECHECK_OS_ERROR','PRECHECK_FAILED'])
add('H21_child_absent_not_refused',"    need(found is not None,code+'_ABSENT')\n","    if found is None:return None\n")
add('H22_child_mode_not_checked',"    need(found['type']=='dir' and (found['uid'],found['gid'],found['mode_octal'])==(0,0,'%04o'%PRIVATE_DIRECTORY_MODE),code+'_INVALID')",
    "    need(found['type']=='dir','%s_INVALID'%code)")
add('H23_child_type_not_checked',"    need(found['type']=='dir' and (found['uid'],found['gid'],found['mode_octal'])==(0,0,'%04o'%PRIVATE_DIRECTORY_MODE),code+'_INVALID')",
    "    need((found['uid'],found['gid'],found['mode_octal'])==(0,0,'%04o'%PRIVATE_DIRECTORY_MODE),code+'_INVALID')")
add('H24_child_followed_through_a_link',"    try:fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=parent.fd)\n    except OSError:raise Refused(code+'_CHANGED_DURING_PRECHECK')",
    "    try:fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|host.noatime(),dir_fd=parent.fd)\n    except OSError:raise Refused(code+'_CHANGED_DURING_PRECHECK')")
add('H25_child_identity_not_compared',"    if held.identity[:2]!=(found['device'],found['inode']) or held.identity[2:]!=(0,0,PRIVATE_DIRECTORY_MODE):",
    "    if held.identity[2:]!=(0,0,PRIVATE_DIRECTORY_MODE):")
add('H26_child_mode_after_open_not_compared',"    if held.identity[:2]!=(found['device'],found['inode']) or held.identity[2:]!=(0,0,PRIVATE_DIRECTORY_MODE):",
    "    if held.identity[:2]!=(found['device'],found['inode']):")
add('H27_file_absent_is_metadata',"    except FileNotFoundError:raise Refused(code+'_ABSENT') from None","    except FileNotFoundError:raise Refused(code+'_METADATA') from None")
add('H28_file_read_failure_passes_through',"        raise Refused(str(error) if str(error) in ('GO_EXPIRED','CLOCK_REVERSED') else code+'_METADATA') from None",
    "        raise")
add('H29_file_metadata_not_checked',"    need(stat.S_ISREG(info.st_mode) and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)==(0,0,mode,1),code+'_METADATA')",
    "    need(stat.S_ISREG(info.st_mode),code+'_METADATA')")
add('H30_file_links_not_checked',"(info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)==(0,0,mode,1),code+'_METADATA')",
    "(info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(0,0,mode),code+'_METADATA')")
add('H31_file_hash_not_compared',"    need(sha(raw)==digest,code+'_NOT_THE_SIGNED_BYTES')","    need(len(raw)>0,code+'_NOT_THE_SIGNED_BYTES')")

# ---------------------------------------------------------------- revision after the independent read (2026-10-05)
ID="    need(type(identity) is dict and set(identity)==set(STATIC_IDENTITY_KEYS) and identity['epoch']==K4_EPOCH and identity['namespace']==K4_EPOCH\n"
add('S07_identity_keys_not_exact',ID,ID.replace("set(identity)==set(STATIC_IDENTITY_KEYS)","set(identity)>=set(STATIC_IDENTITY_KEYS)"),refusal='STATIC_CONFIG_IDENTITY')
add('S08_identity_epoch_not_checked',ID,ID.replace(" and identity['epoch']==K4_EPOCH",""))
add('S09_identity_namespace_not_checked',ID,ID.replace(" and identity['namespace']==K4_EPOCH",""))
add('S10_identity_first_session_not_checked',"         and identity['first_session']==K4_SESSIONS[0] and identity['authorized_sessions']","         and identity['authorized_sessions']")
add('S26_identity_sessions_not_checked'," and identity['authorized_sessions']==list(K4_SESSIONS)\n","\n")
add('S27_document_order_not_a_hash',"         and hexpin(identity['document_order_sha']) and hexpin(identity['runtime_order_sha']),'STATIC_CONFIG_IDENTITY')",
    "         and hexpin(identity['runtime_order_sha']),'STATIC_CONFIG_IDENTITY')")
add('S28_runtime_order_not_a_hash',"         and hexpin(identity['document_order_sha']) and hexpin(identity['runtime_order_sha']),'STATIC_CONFIG_IDENTITY')",
    "         and hexpin(identity['document_order_sha']),'STATIC_CONFIG_IDENTITY')")
add('S22_roots_path_not_checked',"and roots[name]['path']==CONTAINER_CAPACITY_ROOT+'/'+name and hexpin(roots[name]['identity'])","and hexpin(roots[name]['identity'])",refusal='STATIC_CONFIG_ROOTS')
add('S29_root_identity_not_a_hash',"and roots[name]['path']==CONTAINER_CAPACITY_ROOT+'/'+name and hexpin(roots[name]['identity'])","and roots[name]['path']==CONTAINER_CAPACITY_ROOT+'/'+name")
add('P11_config_file_any_name',"    need(values['C3PO_R2D2_V2_CAPACITY_CONFIG_FILE']==CONTAINER_CAPACITY_ROOT+'/config/'+STATIC_CONFIG_NAME,'PINS_CONFIG_FILE')",
    "    need(values['C3PO_R2D2_V2_CAPACITY_CONFIG_FILE'].startswith(CONTAINER_CAPACITY_ROOT+'/config/'),'PINS_CONFIG_FILE')",refusal='PINS_CONFIG_FILE')
add('H04_chain_documents_not_looked_at',"                for index in range(len(files)-1):look(index,handles['DOCUMENTS'],'CHAIN_DOCUMENT_PRESENT')\n","",refusal='CHAIN_DOCUMENT_PRESENT')
add('H05_only_the_first_chain_document_looked_at',"                for index in range(len(files)-1):look(","                for index in range(1):look(")
add('H06_static_config_not_looked_at',"                look(len(files)-1,handles['CONFIG'],'STATIC_CONFIG_PRESENT')\n","",refusal='STATIC_CONFIG_PRESENT')
FE2="    need(stat.S_ISREG(info.st_mode) and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)==(0,0,PRIVATE_FILE_MODE,1)\n         and found==raw,code)"
add('H07_found_file_bytes_not_compared',FE2,FE2.replace("\n         and found==raw,code)",",code)"))
add('H39_found_file_metadata_not_checked',FE2,FE2.replace("stat.S_ISREG(info.st_mode) and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)==(0,0,PRIVATE_FILE_MODE,1)\n         and ",""))
add('H40_found_file_links_not_checked',FE2,FE2.replace("(info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)==(0,0,PRIVATE_FILE_MODE,1)","(info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(0,0,PRIVATE_FILE_MODE)"))
add('H41_found_read_failure_passes',"    except OSError:raise Refused(code) from None\n    need(stat.S_ISREG","    except OSError:raise\n    need(stat.S_ISREG")
add('H42_present_rows_recreated',"            if index in present:\n                ledger.append(present[index]);continue\n","")
add('H43_present_rows_not_read_back',"            if stop is None:stop=readback_file(row,raw,PRIVATE_FILE_MODE,directory,host,gate)\n",
    "            if stop is None and row['state']!='PRESENT_EQUAL':stop=readback_file(row,raw,PRIVATE_FILE_MODE,directory,host,gate)\n")
add('H09_pins_not_looked_at',"                look(0,reader,'PINS_ENV_PRESENT')\n","",refusal='PINS_ENV_PRESENT')
add('H10_launcher_file_not_read',"                input_file(LAUNCHER_NAME,launcher,values['C3PO_READER_LAUNCHER_SHA256'],PRIVATE_FILE_MODE,MAX_LAUNCHER_BYTES,'LAUNCHER_FILE')\n","",
    refusal=['LAUNCHER_FILE_ABSENT','LAUNCHER_FILE_METADATA','LAUNCHER_FILE_NOT_THE_SIGNED_BYTES'])
add('H11_static_config_file_not_read',"                static_config_of(input_file(STATIC_CONFIG_NAME,config,","                (lambda *a,**b:None)(input_file(STATIC_CONFIG_NAME,config,")
add('H44_static_config_file_not_compared',"input_file(STATIC_CONFIG_NAME,config,values['C3PO_R2D2_V2_CAPACITY_CONFIG_SHA'],","input_file(STATIC_CONFIG_NAME,config,sha(b''),",
    refusal=['STATIC_CONFIG_FILE_ABSENT','STATIC_CONFIG_FILE_METADATA','STATIC_CONFIG_FILE_NOT_THE_SIGNED_BYTES'])
add('H12_producer_unit_not_compared',"producer=input_file(PRODUCER_UNIT_NAME,units,item['producer_unit_sha256'],","producer=input_file(PRODUCER_UNIT_NAME,units,item['reader_unit_sha256'],",
    refusal=['PRODUCER_UNIT_ABSENT','PRODUCER_UNIT_METADATA','PRODUCER_UNIT_NOT_THE_SIGNED_BYTES'])
add('H13_reader_unit_not_compared',"reader_unit=input_file(READER_UNIT_NAME,units,item['reader_unit_sha256'],","reader_unit=input_file(READER_UNIT_NAME,units,item['producer_unit_sha256'],",
    refusal=['READER_UNIT_ABSENT','READER_UNIT_METADATA','READER_UNIT_NOT_THE_SIGNED_BYTES'])
add('H45_inputs_not_proved_unchanged',"                    gate();need(stat_signature(host.lstat(name,parent.fd))==signature,'PINS_INPUT_CHANGED')",
    "                    gate();need(True,'PINS_INPUT_CHANGED')",refusal='PINS_INPUT_CHANGED')
add('H46_inputs_signature_not_kept',"inputs.append((name,parent,stat_signature(info)))","inputs.append((name,parent,stat_signature(host.fstat(parent.fd))))")
add('H17_launcher_directory_not_looked_at',"                if entry_named(host,LAUNCHER_DIRECTORY_NAME,reader,gate) is None:detail['precheck']['launcher_directory']='ABSENT'",
    "                if True:detail['precheck']['launcher_directory']='ABSENT'",refusal=['LAUNCHER_DIRECTORY_PRESENT','LAUNCHER_DIRECTORY_PRESENT_INVALID',
    'LAUNCHER_DIRECTORY_PRESENT_CHANGED_DURING_PRECHECK','LAUNCHER_DIRECTORY'])
add('H47_launcher_directory_extra_entries_accepted',"                    need(count_entries(host,handles['LAUNCHER_DIRECTORY'].fd,gate,MAX_DIRECTORY_ENTRIES)==len(present),'LAUNCHER_DIRECTORY_PRESENT')\n","")
add('H48_launcher_file_found_not_judged',"                    look(0,handles['LAUNCHER_DIRECTORY'],'LAUNCHER_DIRECTORY_PRESENT')\n","")
add('H32_bind_line_not_anchored',"    found=re.findall(r'(?m)^  --mount type=bind","    found=re.findall(r'(?m)--mount type=bind")
add('H49_bind_line_without_its_end',"re.escape(target)+re.escape(suffix)+r' \\\\$',unit)","re.escape(target)+re.escape(suffix),unit)")
add('H50_journal_root_counted_loosely'," and producer.count('--journal-root ')==1\n"," and producer.count('--journal-root ')>=1\n")
add('W12_launcher_file_created_beside_its_directory',"            targets=[handles.get('LAUNCHER_DIRECTORY')]\n        for index,","            targets=[handles.get('READER')]\n        for index,")
add('W17_launcher_directory_made_again',"        if mode=='LAUNCHER' and targets[0] is None:","        if mode=='LAUNCHER':")
add('W18_created_flag_constant',"                                 'created_by_this_run':row['state']!='PRESENT_EQUAL'} for row in ledger],","                                 'created_by_this_run':True} for row in ledger],")
add('W19_present_files_not_counted',"'DOCUMENTS':len([index for index in range(len(files)-1) if index not in present]),","'DOCUMENTS':len(files)-1,")

add('C39_a_fifth_mode',"K4_MODES=('CHAIN_STATIC','PINS','LAUNCHER','WRITER')","K4_MODES=('CHAIN_STATIC','PINS','LAUNCHER','WRITER','E0')")
add('E23_effects_journal_bind',"                                         'journal_bind':'SAME_SOURCE_IN_BOTH_UNITS_TARGET_'+values['C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR'],",
    "                                         'journal_bind':'SAME_SOURCE_IN_BOTH_UNITS',",effect='required_on_the_host.journal_bind')
add('H37_capacity_bind_not_checked',"         and bind_source(reader,CONTAINER_CAPACITY_ROOT,',readonly')==capacity_root\n","\n")
add('W11_delivered_summary_without_the_entries',"            if mode in ('CHAIN_STATIC','WRITER'):delivered['entries_after']={key:entries[key]+after[key] for key in entries}\n","")

# ---------------------------------------------------------------- mode WRITER and Codex decision 6 (2026-10-05)
add('C50_source_root_on_the_data_volume',"K4_SOURCE_ROOT='/var/lib/c3po/r2d2-v2-source-20261005'","K4_SOURCE_ROOT='/mnt/day-d-data/r2d2-v2-source-20261005'")
add('C51_another_journal_host',"K4_JOURNAL_HOST='/var/lib/c3po-bar/journal'","K4_JOURNAL_HOST='/var/lib/c3po-bar/journal-2'")
add('C52_writer_stem',"WRITER_STEM='manifest_writer-'","WRITER_STEM='manifest_writer_'")
add('C53_writer_extension',"WRITER_EXTENSION='.py'","WRITER_EXTENSION='.pyc'")
WB="    need(len(raw)==size and sha(raw)==digest,'WRITER_NOT_THE_COMPILED_HASH')"
add('X01_writer_size_not_checked',WB,"    need(sha(raw)==digest,'WRITER_NOT_THE_COMPILED_HASH')",refusal='WRITER_NOT_THE_COMPILED_HASH')
add('X02_writer_hash_not_checked',WB,"    need(len(raw)==size,'WRITER_NOT_THE_COMPILED_HASH')")
add('X03_writer_request_hash_not_compared',"        need(item['writer_sha256']==K4_WRITER[0],'WRITER_NOT_THE_COMPILED_HASH')\n","")
add('X04_writer_chain_not_judged',"        private_chain(item['config_parent'],CAPACITY_CONFIG_DIRECTORY)\n        need(item['writer_sha256']","        need(item['writer_sha256']")
add('X05_writer_not_looked_at',"                look(0,config,'WRITER_PRESENT')\n","",refusal='WRITER_PRESENT')
add('X06_writer_directory_count_not_read_back',"        if stop is None and mode in ('CHAIN_STATIC','WRITER'):","        if stop is None and mode=='CHAIN_STATIC':")
add('X07_writer_present_counted_as_new',"                after={'CONFIG':0 if 0 in present else 1}","                after={'CONFIG':1}")
add('E25_effects_writer_path',"writer={'path_in_containers':CONTAINER_CAPACITY_ROOT+'/config/'+WRITER_STEM+K4_WRITER[0]+WRITER_EXTENSION,'compiled':True})",
    "writer={'path_in_containers':CONTAINER_CAPACITY_ROOT+'/config/'+WRITER_STEM+WRITER_EXTENSION,'compiled':True})",effect='writer')
add('E26_effects_bind_sources',"'bind_sources':{'source_root':chain_effects(item['source_chain']),","'bind_sources':{'source_root':chain_effects(item['journal_chain']),",
    effect='required_on_the_host.bind_sources')
add('X08_source_chain_not_judged',"        private_chain(item['source_chain'],K4_SOURCE_ROOT);private_chain(item['journal_chain'],K4_JOURNAL_HOST)",
    "        private_chain(item['journal_chain'],K4_JOURNAL_HOST)")
add('X09_journal_chain_not_judged',"        private_chain(item['source_chain'],K4_SOURCE_ROOT);private_chain(item['journal_chain'],K4_JOURNAL_HOST)",
    "        private_chain(item['source_chain'],K4_SOURCE_ROOT)")
add('X10_source_root_not_walked',"                walk('source_root',item['source_chain']);walk('journal',item['journal_chain'])","                walk('journal',item['journal_chain'])")
add('X11_journal_not_walked',"                walk('source_root',item['source_chain']);walk('journal',item['journal_chain'])","                walk('source_root',item['source_chain'])")
add('X12_journal_host_not_the_installed_one',"    need(produced==K4_JOURNAL_HOST,'JOURNAL_BIND_MISMATCH')\n","")
add('X13_source_bind_not_checked',"    need(bind_source(reader,values['C3PO_R2D2_V2_SHADOW_SOURCE_DIR'],',readonly')==K4_SOURCE_ROOT\n         and ","    need(")
SD="    need(text(source,JOURNAL_TARGET_PATTERN) and source not in JOURNAL_TARGETS_TAKEN and source!=values['C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR'],'PINS_SOURCE_DIR')"
add('X14_source_target_any_path',SD,SD.replace("text(source,JOURNAL_TARGET_PATTERN) and ","clean_path(source) and "),refusal='PINS_SOURCE_DIR')
add('X15_source_target_may_be_taken',SD,SD.replace(" and source not in JOURNAL_TARGETS_TAKEN",""))
add('X16_source_target_may_be_the_journal',SD,SD.replace(" and source!=values['C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR']",""))

# ---------------------------------------------------------------- the dispatcher generated for this operation: one more day
DISPATCHER=[('D73k_dispatcher_accepts_the_day_after_the_epoch','dispatcher',"'2026-10-09','2026-10-10') and end.date()==start.date()",
             "'2026-10-09','2026-10-10','2026-10-11') and end.date()==start.date()")]
CORE_ROWS_REPLACED=()

MUTANTS=M+DISPATCHER
COMBOS={}
REDUNDANT={}
# (Not mutants, equivalent by construction: the index of create_file per file -- each temporary is withdrawn before the
# next file starts, so one index for all would still never collide; the observed hash in the delivered summary is the
# signed one whenever that summary exists (readback_file passed), as in K4-E0's note.)


# ---------------------------------------------------------------- the two tables against the source itself
def _load(path):
    raw=Path(path).read_bytes();name='_hostops02_k4files_mutation_'+hashlib.sha256(raw).hexdigest()[:12]
    module=type(sys)(name);module.__dict__['__file__']='<assembled k4_files.py>';sys.modules[name]=module
    exec(compile(raw,module.__dict__['__file__'],'exec'),module.__dict__);return module

def _members(value,prefix=''):
    out=[]
    for key in sorted(value):
        if type(value[key]) is dict and not prefix and key in ('static_config','required_on_the_host'):out+=_members(value[key],prefix+key+'.')
        else:out.append(prefix+key)
    return out

def codes_of(text):
    """Every constant code the operation part can raise: the code of each need(), each Refused() and each code_of() fallback."""
    found=set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in ('need','Refused','code_of'):
            for argument in node.args:
                for item in ast.walk(argument):
                    if (isinstance(item,ast.Constant) and type(item.value) is str and item.value.isupper() and '_' in item.value
                            and item.value[0]!='_' and not item.value.startswith('C3PO_')):found.add(item.value)
    return found

# Codes built from a prefix at run time (private_child, signed_file_on_host, absent, signed_bytes): listed by hand.
DYNAMIC={'LAUNCHER_DIRECTORY_ABSENT','LAUNCHER_DIRECTORY_INVALID','LAUNCHER_DIRECTORY_CHANGED_DURING_PRECHECK','LAUNCHER_FILE_ABSENT','LAUNCHER_FILE_METADATA',
         'LAUNCHER_FILE_NOT_THE_SIGNED_BYTES','STATIC_CONFIG_FILE_ABSENT','STATIC_CONFIG_FILE_METADATA','STATIC_CONFIG_FILE_NOT_THE_SIGNED_BYTES',
         'PRODUCER_UNIT_ABSENT','PRODUCER_UNIT_METADATA','PRODUCER_UNIT_NOT_THE_SIGNED_BYTES','READER_UNIT_ABSENT','READER_UNIT_METADATA',
         'READER_UNIT_NOT_THE_SIGNED_BYTES','CHAIN_DOCUMENT_PRESENT','STATIC_CONFIG_PRESENT','PINS_ENV_PRESENT','LAUNCHER_DIRECTORY_PRESENT',
         'STATIC_CONFIG_BYTES_NOT_THE_SIGNED_HASH','LAUNCHER_BYTES_NOT_THE_SIGNED_HASH','PARENT_SETGID','CHAIN_ROW_UNSAFE',
         'LAUNCHER_DIRECTORY_PRESENT_INVALID','LAUNCHER_DIRECTORY_PRESENT_CHANGED_DURING_PRECHECK'}

def coverage(here):
    here=Path(here);errors=[];names={row[0] for row in M};module=_load(here/'build'/'k4_files.py')
    def rows(path,leaf=0o700):
        parts=path.strip('/').split('/');out=[{'path':'/','device':1,'inode':2,'uid':0,'gid':0,'mode':0o755}];prefix=''
        for index,part in enumerate(parts):
            prefix+='/'+part;out.append({'path':prefix,'device':1,'inode':3+index,'uid':0,'gid':0,'mode':leaf if index==len(parts)-1 else 0o755})
        return out
    wanted=set()
    for mode in module.K4_MODES:
        if mode in ('CHAIN_STATIC','WRITER'):continue                   # their members are the union below
        values={name:'/c3po-bar-journal' for name in module.PINS_NAMES};values.update(module.PINS_CONSTANTS)
        values.update({'C3PO_R2D2_V2_SHADOW_RELEASE_FILE':'/app/day-d-data/a/b','C3PO_R2D2_V2_SHADOW_SOURCE_DIR':'/c3po-source',
                       'C3PO_R2D2_V2_CAPACITY_CONFIG_FILE':'/c3po-capacity/config/week.static.capacity.json','C3PO_R2D2_V2_CAPACITY_CONFIG_SHA':'1'*64,
                       'C3PO_READER_LAUNCHER_SHA256':'2'*64})
        raw=module.pins_lines(values) if mode=='PINS' else b'x'
        import base64
        delivery={'PINS':{'reader_parent':rows(module.READER_CONFIG_DIRECTORY),'config_parent':rows(module.CAPACITY_CONFIG_DIRECTORY),
                          'unit_parent':rows(module.UNIT_DIRECTORY,0o755),'values':values,
                          'source_chain':rows(module.K4_SOURCE_ROOT),'journal_chain':rows(module.K4_JOURNAL_HOST),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),
                          'producer_unit_sha256':'3'*64,'reader_unit_sha256':'4'*64},
                  'LAUNCHER':{'reader_parent':rows(module.READER_CONFIG_DIRECTORY),
                              'launcher':{'content_b64':base64.b64encode(b'x').decode(),'sha256':hashlib.sha256(b'x').hexdigest(),'bytes':1}}}[mode]
        wanted|=set(_members(module.effects_of({'mode':mode,'delivery':delivery,'evidence_boot_id_sha256':'a'*64})))
    wanted|={'documents_parent','static_config.release_sha','static_config.package_sha','static_config.chain_pins','writer'}
    for member in sorted(wanted):
        if EFFECTS.get(member) not in names:errors.append('effects member without a mutant: '+member)
    codes=(codes_of((here/'op.py').read_text())|DYNAMIC)-{'CREATION_FAILED','INSTALL_FAILED','GO_EXPIRED','CLOCK_REVERSED','UNIT_FILE'}
    for code in sorted(codes):
        if REFUSALS.get(code) not in names:errors.append('refusal without a mutant: '+code)
    return errors
