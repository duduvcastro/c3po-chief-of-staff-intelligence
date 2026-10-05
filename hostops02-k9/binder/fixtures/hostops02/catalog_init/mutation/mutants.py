"""The mutants of K2a's own part. Each row: (name, 'op', exact anchor, replacement). The anchor must occur exactly once
in the built source and be a text of op.py (mutate.py check). One mutant per member of effects_of(), one per refusal
of validate_plan and of the precheck, and one per condition of the verdict after the container was started.

After the reviews of 2026-10-02 and the repair: every anchor that moved was written again for the repaired text; the
mutants of the three removed lines are gone with them (the path grammar of the configuration directory, the throwaway
inside the parent of the real root, the overlap of the two paths: all three are now decided by the layout floor); new
mutants ask about the floor (P25 to P35), the directory a rehearsal gives docker (F33 to F43, K27 to K37, E39 to E51,
E56), docker's own status after a verified catalog (R12 to R16, E52), what the reads left in the directory docker was
given and how it is counted (K38 to K53, E58 to E65), the descriptors (E53 to E55); and the reviewer's own mutants
that had survived the first two passes are in the list (V11 to V21, K35, E57)."""
MUTANTS=[]
COMBOS={}
REDUNDANT={}
def add(name,old,new):MUTANTS.append((name,'op',old,new))

# ---------------------------------------------------------------- constants the signers rely on
add('C01_epoch_constant_is_another_day',"EPOCH_COMPILED='R2D2-V2-SHADOW-2026-10-05'","EPOCH_COMPILED='R2D2-V2-SHADOW-2026-10-06'")
add('C02_rehearsal_epoch_may_be_a_shadow_epoch',"REHEARSAL_EPOCH='R2D2-V2-DIAG-[A-Za-z0-9_-]{1,80}'","REHEARSAL_EPOCH='R2D2-V2-(?:DIAG|SHADOW)-[A-Za-z0-9_-]{1,80}'")
add('C03_throwaway_name_is_any_name',"THROWAWAY_NAME='c3po-bar-rehearsal-[a-z0-9][a-z0-9-]{0,39}'","THROWAWAY_NAME='[a-z0-9][a-z0-9-]{0,63}'")
add('C04_throwaway_label_may_be_empty',"THROWAWAY_NAME='c3po-bar-rehearsal-[a-z0-9][a-z0-9-]{0,39}'","THROWAWAY_NAME='c3po-bar-rehearsal-[a-z0-9-]{0,40}'")
add('C05_catalog_file_mode_0644',"CATALOG_FILE_MODE=0o600","CATALOG_FILE_MODE=0o644")
add('C06_catalog_names_are_others',"CATALOG_FILES=('epoch.json','maintenance.lock')","CATALOG_FILES=('epoch.json','producer.lock')")
add('C07_catalog_schema_is_another',"CATALOG_SCHEMA='MASSIVE_SESSION_ROOT_V1'","CATALOG_SCHEMA='MASSIVE_SESSION_ROOT_V2'")
add('C08_entry_limit_of_the_readback_raised',"MAX_CATALOG_ENTRIES=64","MAX_CATALOG_ENTRIES=6400")
add('C09_epoch_json_read_limit_raised',"MAX_EPOCH_JSON_BYTES=4096","MAX_EPOCH_JSON_BYTES=65536")
add('C10_every_new_container_row_printed',"MAX_NEW_CONTAINER_ROWS=8","MAX_NEW_CONTAINER_ROWS=80")
add('C11_app_allowed_as_container_path',"CONTAINER_ROOT_FORBIDDEN=('app','bin',","CONTAINER_ROOT_FORBIDDEN=('bin',")
add('C12_var_allowed_as_container_path',"'srv','sys','tmp','usr','var')","'srv','sys','tmp','usr')")
add('C13_no_allowance_for_the_rehearsal_directory',"FILES_ALLOWANCE_SECONDS=2 ","FILES_ALLOWANCE_SECONDS=0 ")
add('C14_provisioning_evidence_not_required',"EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,PROVISION_OPERATION)","EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,)")
add('C15_precheck_evidence_not_required',"EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,PROVISION_OPERATION)","EVIDENCE_OPERATIONS=(PROVISION_OPERATION,)")
add('C16_run_gets_the_short_class',"'python -I -B -, the container path, the epoch string; the pinned script on standard input','RUN','EFFECT',stdin=True)",
    "'python -I -B -, the container path, the epoch string; the pinned script on standard input','RUN_SHORT','EFFECT',stdin=True)")
add('C17_rehearsal_succeeds_with_the_outcome_of_the_real_run',"def success_of(plan):return COMPLETE_OUTCOME if plan['mode']=='REAL' else REHEARSAL_COMPLETE_OUTCOME",
    "def success_of(plan):return COMPLETE_OUTCOME")
add('C18_real_run_succeeds_with_the_outcome_of_the_rehearsal',"def success_of(plan):return COMPLETE_OUTCOME if plan['mode']=='REAL' else REHEARSAL_COMPLETE_OUTCOME",
    "def success_of(plan):return REHEARSAL_COMPLETE_OUTCOME")
add('C19_writes_any_day_of_the_epoch',"DATE_CLASS='WRITE_WEEKEND'","DATE_CLASS='WRITE_EPOCH'")

# ---------------------------------------------------------------- the script
PIN="    need(len(raw)==CATALOG_SCRIPT_BYTES and sha(raw)==CATALOG_SCRIPT_SHA256,'SCRIPT_NOT_THE_PINNED_HASH');return raw\n"
add('S01_script_bytes_not_compared',PIN,"    return raw\n")
add('S02_script_compared_by_size_only',PIN,"    need(len(raw)==CATALOG_SCRIPT_BYTES,'SCRIPT_NOT_THE_PINNED_HASH');return raw\n")
SIGNED="    need(type(plan['script_sha256']) is str and plan['script_sha256']==CATALOG_SCRIPT_SHA256,'SCRIPT_NOT_THE_PINNED_HASH');script_bytes()\n"
add('S03_signed_script_hash_not_compared',SIGNED,"    script_bytes()\n")
add('S04_script_not_checked_before_the_claim',SIGNED,"    need(type(plan['script_sha256']) is str and plan['script_sha256']==CATALOG_SCRIPT_SHA256,'SCRIPT_NOT_THE_PINNED_HASH')\n")
add('S05_undecodable_script_escapes_as_an_exception',"    except (ValueError,UnicodeEncodeError):raise Refused('SCRIPT_NOT_THE_PINNED_HASH') from None\n","    except KeyError:raise Refused('SCRIPT_NOT_THE_PINNED_HASH') from None\n")

# ---------------------------------------------------------------- signed rows
ROWS="    need(type(rows) is list and len(rows)>=2 and type(rows[-1]) is dict and type(rows[-1].get('path')) is str,'CHAIN_ROW_INVALID')\n"
add('V01_rows_of_the_root_directory_accepted',ROWS,ROWS.replace("len(rows)>=2","len(rows)>=1"))
add('V02_rows_type_unchecked',ROWS,"    need(len(rows)>=2,'CHAIN_ROW_INVALID')\n")
PRIVATE="    need(last['gid']==0 and last['mode']==PRIVATE_DIRECTORY_MODE,label+'_NOT_PRIVATE')"
add('V03_private_directory_group_unchecked',PRIVATE,"    need(last['mode']==PRIVATE_DIRECTORY_MODE,label+'_NOT_PRIVATE')")
add('V04_private_directory_mode_is_only_closed_to_others',PRIVATE,"    need(last['gid']==0 and not last['mode']&0o077,label+'_NOT_PRIVATE')")
add('V05_private_directory_mode_unchecked',PRIVATE,"    need(last['gid']==0,label+'_NOT_PRIVATE')")
add('V06_mount_point_accepted',"    need(last['device']==rows[-2]['device'],label+'_IS_A_MOUNT_POINT')\n","")
add('V07_rehearsal_acts_on_the_signed_parent_itself',"    return last if plan['mode']=='REAL' else last.rstrip('/')+'/'+plan['throwaway_name']\n","    return last\n")
add('V08_bind_is_read_only',"'target':plan['container_journal_root'],'read_only':False}]","'target':plan['container_journal_root'],'read_only':True}]")
add('V09_script_gets_the_host_path',"def run_words(plan):return ['python','-I','-B','-',plan['container_journal_root'],plan['epoch']]","def run_words(plan):return ['python','-I','-B','-',journal_path(plan),plan['epoch']]")
add('V10_interpreter_not_isolated',"def run_words(plan):return ['python','-I','-B','-',","def run_words(plan):return ['python','-B','-',")

# ---------------------------------------------------------------- validate_plan: one per refusal
add('P01_mode_unchecked',"    mode=plan['mode'];need(type(mode) is str and mode in MODES,'MODE_INVALID')\n","    mode=plan['mode']\n")
add('P02_evidence_boot_unchecked',"    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')\n","")
add('P03_image_revision_unchecked',"    need(text(plan['image_revision'],'[0-9a-f]{40}'),'IMAGE_REVISION_UNBOUND')\n","")
TARGET="    need(text(target,'/[A-Za-z0-9][A-Za-z0-9._-]{0,63}') and target[1:] not in CONTAINER_ROOT_FORBIDDEN,'CONTAINER_JOURNAL_ROOT_INVALID')\n"
add('P04_container_path_may_be_nested',TARGET,TARGET.replace("'/[A-Za-z0-9][A-Za-z0-9._-]{0,63}'","'/[A-Za-z0-9][A-Za-z0-9._/-]{0,63}'"))
add('P05_container_path_may_begin_with_a_dot',TARGET,TARGET.replace("'/[A-Za-z0-9][A-Za-z0-9._-]{0,63}'","'/[A-Za-z0-9._-]{1,64}'"))
add('P06_forbidden_top_level_directories_accepted',TARGET,TARGET.replace(" and target[1:] not in CONTAINER_ROOT_FORBIDDEN",""))
add('P07_container_path_unchecked',TARGET,"")
add('P08_docker_config_need_not_be_private',"    config=private_rows(plan['docker_config_chain'],'DOCKER_CONFIG')\n","    config=signed_rows(plan['docker_config_chain'])\n")
UNIT="    need(config[-1]['path']==UNIT_DOCKER_CONFIG,'DOCKER_CONFIG_NOT_THE_DIRECTORY_OF_THE_UNIT')\n"
add('P09_docker_config_may_be_any_private_directory',UNIT,"")
add('P25_docker_config_may_be_any_directory_of_the_configuration_tree',UNIT,UNIT.replace("config[-1]['path']==UNIT_DOCKER_CONFIG","config[-1]['path'].startswith('/etc/c3po-bar/')"))
add('P26_docker_config_of_the_unit_is_another_directory',"UNIT_DOCKER_CONFIG='/etc/c3po-bar/docker-cli'","UNIT_DOCKER_CONFIG='/etc/c3po-bar/manifests'")
MEMBERS="        need(plan['throwaway_name'] is None and plan['reference_chain'] is None,'MODE_MEMBERS_INVALID')\n"
add('P10_real_mode_accepts_a_throwaway_name',MEMBERS,"        need(plan['reference_chain'] is None,'MODE_MEMBERS_INVALID')\n")
add('P11_real_mode_accepts_a_reference_chain',MEMBERS,"        need(plan['throwaway_name'] is None,'MODE_MEMBERS_INVALID')\n")
add('P12_real_journal_root_need_not_be_private',"        journal_rows(plan['journal_chain'],'JOURNAL_ROOT')\n","        signed_rows(plan['journal_chain'])\n")
add('P27_real_journal_root_is_any_private_directory',"        journal_rows(plan['journal_chain'],'JOURNAL_ROOT')\n","        private_rows(plan['journal_chain'],'JOURNAL_ROOT')\n")
LEAF="    need(rows[-2]['path']==JOURNAL_PARENT,label+'_NOT_A_LEAF_OF_THE_PRIVATE_PARENT')\n"
add('P28_journal_root_need_not_be_in_the_private_parent',LEAF,"")
add('P29_journal_root_may_lie_anywhere_inside_the_private_parent',LEAF,LEAF.replace("rows[-2]['path']==JOURNAL_PARENT","inside(rows[-1]['path'],JOURNAL_PARENT)"))
add('P30_journal_root_only_named_like_a_leaf_of_the_private_parent',LEAF,LEAF.replace("rows[-2]['path']==JOURNAL_PARENT","rows[-1]['path'].startswith(JOURNAL_PARENT)"))
add('P31_state_root_accepted_as_a_journal_root',"    need(rows[-1]['path']!=STATE_ROOT,label+'_IS_THE_STATE_ROOT')\n","")
add('P32_state_root_is_another_directory',"STATE_ROOT='/var/lib/c3po-bar/supervisor'","STATE_ROOT='/var/lib/c3po-bar/state'")
add('P33_journal_rows_need_not_be_private',"    rows=private_rows(rows,label)\n    need(rows[-2]['path']==JOURNAL_PARENT","    rows=signed_rows(rows)\n    need(rows[-2]['path']==JOURNAL_PARENT")
EPOCH="        need(type(plan['epoch']) is str and plan['epoch']==EPOCH_COMPILED,'EPOCH_NOT_THE_COMPILED_CONSTANT')\n"
add('P13_real_epoch_is_any_shadow_epoch',EPOCH,"        need(text(plan['epoch'],'R2D2-V2-SHADOW-[A-Za-z0-9_-]{1,80}'),'EPOCH_NOT_THE_COMPILED_CONSTANT')\n")
add('P14_real_epoch_is_any_epoch',EPOCH,"        need(text(plan['epoch'],'R2D2-V2-(?:SHADOW|DIAG)-[A-Za-z0-9_-]{1,80}'),'EPOCH_NOT_THE_COMPILED_CONSTANT')\n")
add('P15_rehearsal_parent_may_be_setgid',"        parent=signed_rows(plan['journal_chain'],True)\n","        parent=signed_rows(plan['journal_chain'])\n")
add('P16_throwaway_name_unchecked',"        need(text(plan['throwaway_name'],THROWAWAY_NAME),'THROWAWAY_NAME_INVALID')\n","")
add('P17_reference_need_not_be_private',"        reference=journal_rows(plan['reference_chain'],'REFERENCE_ROOT')\n","        reference=signed_rows(plan['reference_chain'])\n")
add('P34_reference_is_any_private_directory',"        reference=journal_rows(plan['reference_chain'],'REFERENCE_ROOT')\n","        reference=private_rows(plan['reference_chain'],'REFERENCE_ROOT')\n")
add('P18_rehearsal_on_another_filesystem',"        need(reference[-1]['device']==parent[-1]['device'],'REHEARSAL_NOT_ON_THE_FILESYSTEM_OF_THE_REAL_ROOT')\n","")
FIXED="        need(parent[-1]['path']==THROWAWAY_PARENT,'THROWAWAY_PARENT_NOT_THE_FIXED_ONE')\n"
add('P19_throwaway_created_in_any_signed_directory',FIXED,"")
add('P20_throwaway_created_anywhere_below_var_lib',FIXED,FIXED.replace("parent[-1]['path']==THROWAWAY_PARENT","inside(parent[-1]['path'],THROWAWAY_PARENT)"))
add('P35_throwaway_parent_is_the_private_parent',"THROWAWAY_PARENT='/var/lib' ","THROWAWAY_PARENT='/var/lib/c3po-bar' ")
add('P21_rehearsal_epoch_unchecked',"        need(text(plan['epoch'],REHEARSAL_EPOCH),'EPOCH_NOT_A_DIAGNOSTIC_ONE')\n","")
add('P24_command_not_validated_by_validate_plan',"    run_arguments(RUN_ROW,plan['image_id'],run_mounts(plan),run_words(plan))\n\ndef effects_of(plan):","\ndef effects_of(plan):")

# ---------------------------------------------------------------- effects_of: one per member
add('F01_effects_operation',"    return {'operation':OPERATION,'mode':plan['mode'],","    return {'operation':PHASE,'mode':plan['mode'],")
add('F02_effects_mode',"    return {'operation':OPERATION,'mode':plan['mode'],","    return {'operation':OPERATION,'mode':'REAL',")
add('F03_effects_journal_path',"            'journal_root':{'path':path,'is_the_real_journal_root':not rehearsal,","            'journal_root':{'path':plan['journal_chain'][-1]['path'],'is_the_real_journal_root':not rehearsal,")
add('F04_effects_is_the_real_root',"            'journal_root':{'path':path,'is_the_real_journal_root':not rehearsal,","            'journal_root':{'path':path,'is_the_real_journal_root':False,")
add('F05_effects_journal_expectation',"'expect':'ABSENT_THEN_CREATED_0700_BY_THIS_RUN' if rehearsal else 'PRESENT_EMPTY_ROOT_ROOT_0700_AS_SIGNED',\n                            'signed_chain'",
    "'expect':'PRESENT_EMPTY_ROOT_ROOT_0700_AS_SIGNED',\n                            'signed_chain'")
add('F06_effects_journal_chain',"'signed_chain':chain_effects(plan['journal_chain']),","'signed_chain':chain_effects(plan['docker_config_chain']),")
add('F07_effects_chain_is_of',"'signed_chain_is_of':'THE_PARENT' if rehearsal else 'THE_ROOT_ITSELF',","'signed_chain_is_of':'THE_ROOT_ITSELF',")
add('F08_effects_stays',"                            'stays_after_the_run':True},","                            'stays_after_the_run':False},")
add('F09_effects_reference_absent',"            'real_journal_root_read_only':None if not rehearsal else dict(","            'real_journal_root_read_only':None if True else dict(")
add('F10_effects_reference_chain',"dict(chain_effects(plan['reference_chain']),expect='PRESENT_EMPTY_ROOT_ROOT_0700_AS_SIGNED',","dict(chain_effects(plan['journal_chain']),expect='PRESENT_EMPTY_ROOT_ROOT_0700_AS_SIGNED',")
add('F11_effects_reference_expectation',"dict(chain_effects(plan['reference_chain']),expect='PRESENT_EMPTY_ROOT_ROOT_0700_AS_SIGNED',","dict(chain_effects(plan['reference_chain']),expect='PRESENT',")
add('F12_effects_reference_same_device',"same_device_as_the_parent_of_the_throwaway=True),","same_device_as_the_parent_of_the_throwaway=None),")
add('F13_effects_docker_config_chain',"            'docker_config':dict(chain_effects(plan['docker_config_chain']),given_to_docker=not rehearsal,","            'docker_config':dict(chain_effects(plan['journal_chain']),given_to_docker=not rehearsal,")
EXPECT="expect='PRESENT_EMPTY_ONLY_READ_NEVER_GIVEN_TO_DOCKER' if rehearsal else 'PRESENT_EMPTY_BEFORE_AND_AFTER'),"
add('F14_effects_docker_config_expectation',EXPECT,"expect='PRESENT_EMPTY_ONLY_READ_NEVER_GIVEN_TO_DOCKER' if rehearsal else 'PRESENT'),")
add('F33_effects_rehearsal_said_to_use_the_directory_of_the_unit',EXPECT,"expect='PRESENT_EMPTY_BEFORE_AND_AFTER'),")
add('F34_effects_directory_of_the_unit_said_to_be_given_to_docker_by_a_rehearsal',"given_to_docker=not rehearsal,","given_to_docker=True,")
add('F35_effects_directory_of_the_unit_said_not_to_be_given_to_docker_by_a_real_run',"given_to_docker=not rehearsal,","given_to_docker=False,")
OWN="            'rehearsal_docker_config':None if not rehearsal else {'path':use_path,'expect':'ABSENT_THEN_CREATED_0700_BY_THIS_RUN_EMPTY_AFTER_IT',\n"
add('F36_effects_without_the_directory_a_rehearsal_gives_docker',OWN,OWN.replace("None if not rehearsal else {","None if True else {"))
add('F37_effects_rehearsal_directory_for_docker_is_the_throwaway_root',OWN,OWN.replace("{'path':use_path,","{'path':path,"))
add('F38_effects_rehearsal_directory_for_docker_expectation',OWN,OWN.replace("'ABSENT_THEN_CREATED_0700_BY_THIS_RUN_EMPTY_AFTER_IT'","'PRESENT'"))
add('F39_effects_rehearsal_directory_said_not_to_be_given_to_docker',"'given_to_docker':True,'stays_after_the_run':True},","'given_to_docker':False,'stays_after_the_run':True},")
add('F40_effects_rehearsal_directory_said_to_be_removed',"'given_to_docker':True,'stays_after_the_run':True},","'given_to_docker':True,'stays_after_the_run':False},")
add('F41_effects_docker_config_variable_is_always_the_units',"'docker_config_variable':use_path,","'docker_config_variable':plan['docker_config_chain'][-1]['path'],")
add('F42_effects_without_the_docker_config_variable',"'docker_config_variable':use_path,","'docker_config_variable':None,")
add('F15_effects_image_id',"            'container':{'image_id':plan['image_id'],'image_revision':plan['image_revision'],","            'container':{'image_id':None,'image_revision':plan['image_revision'],")
add('F16_effects_image_revision',"            'container':{'image_id':plan['image_id'],'image_revision':plan['image_revision'],","            'container':{'image_id':plan['image_id'],'image_revision':None,")
add('F17_effects_docker_arguments_without_the_fixed_words',"'docker_arguments':RUN_PREFIX+run_arguments(RUN_ROW,plan['image_id'],run_mounts(plan),run_words(plan)),","'docker_arguments':run_arguments(RUN_ROW,plan['image_id'],run_mounts(plan),run_words(plan)),")
add('F18_effects_bind',"                         'bind':run_mounts(plan)[0],'network':'none',","                         'bind':None,'network':'none',")
add('F19_effects_network',"                         'bind':run_mounts(plan)[0],'network':'none',","                         'bind':run_mounts(plan)[0],'network':'bridge',")
add('F20_effects_script_hash',"'standard_input':{'sha256':CATALOG_SCRIPT_SHA256,'bytes':CATALOG_SCRIPT_BYTES},","'standard_input':{'sha256':None,'bytes':CATALOG_SCRIPT_BYTES},")
add('F21_effects_script_size',"'standard_input':{'sha256':CATALOG_SCRIPT_SHA256,'bytes':CATALOG_SCRIPT_BYTES},","'standard_input':{'sha256':CATALOG_SCRIPT_SHA256,'bytes':0},")
add('F22_effects_time_limit',"'time_limit_seconds':COMMAND_CLASSES[COMMANDS[RUN_ROW]['class']]['seconds']},","'time_limit_seconds':COMMAND_CLASSES['QUICK']['seconds']},")
add('F23_effects_epoch',"            'epoch':plan['epoch'],'epoch_source':","            'epoch':EPOCH_COMPILED,'epoch_source':")
add('F24_effects_epoch_source',"'epoch_source':'SIGNED_DIAGNOSTIC_STRING' if rehearsal else EPOCH_SOURCE,","'epoch_source':EPOCH_SOURCE,")
add('F25_effects_created_by_this_process',"            'creates':{'by_this_process':[use_path,path] if rehearsal else [],","            'creates':{'by_this_process':[],")
add('F43_effects_created_by_this_process_without_the_directory_for_docker',"            'creates':{'by_this_process':[use_path,path] if rehearsal else [],","            'creates':{'by_this_process':[path] if rehearsal else [],")
add('F26_effects_created_by_the_container',"'by_the_container':[path+'/'+name for name in CATALOG_FILES],","'by_the_container':[],")
add('F27_effects_file_mode',"                       'file_mode_octal':'%04o'%CATALOG_FILE_MODE},","                       'file_mode_octal':'0644'},")
add('F28_effects_success_outcome',"            'success_outcome':success_of(plan),'evidence_boot_id_sha256':","            'success_outcome':COMPLETE_OUTCOME,'evidence_boot_id_sha256':")
add('F29_effects_evidence_boot',"'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],\n            'pre_existing_objects_modified'","'evidence_boot_id_sha256':None,\n            'pre_existing_objects_modified'")
add('F30_effects_pre_existing_modified',"            'pre_existing_objects_modified':not rehearsal,'removes':[],'activation':False}","            'pre_existing_objects_modified':False,'removes':[],'activation':False}")
add('F31_effects_removes',"            'pre_existing_objects_modified':not rehearsal,'removes':[],'activation':False}","            'pre_existing_objects_modified':not rehearsal,'removes':None,'activation':False}")
add('F32_effects_activation',"            'pre_existing_objects_modified':not rehearsal,'removes':[],'activation':False}","            'pre_existing_objects_modified':not rehearsal,'removes':[],'activation':True}")

# ---------------------------------------------------------------- the printed line
add('L01_raw_refusal_text_reaches_the_receipt',"        line['refusal_code']=row['code'] if text(row.get('code'),CODE) else 'NOT_A_CONSTANT_CODE'\n","        line['refusal_code']=row.get('code')\n")
KEYS="        line['keys_exact']=set(row)=={'status','created','epoch','device','inode','entries'}\n"
add('L02_extra_keys_accepted',KEYS,"        line['keys_exact']=set(row)>={'status','created','epoch','device','inode','entries'}\n")
add('L03_keys_unchecked',KEYS,"        line['keys_exact']=True\n")
UPDATE="            line.update(created=row['created'] is True,epoch_equal=row['epoch']==epoch,entries_as_expected=row['entries']==list(CATALOG_FILES),\n"
add('L04_created_may_be_any_truthy_value',UPDATE,UPDATE.replace("created=row['created'] is True","created=bool(row['created'])"))
add('L05_epoch_of_the_line_not_compared',UPDATE,UPDATE.replace("epoch_equal=row['epoch']==epoch","epoch_equal=True"))
add('L06_entries_of_the_line_compared_as_a_set',UPDATE,UPDATE.replace("entries_as_expected=row['entries']==list(CATALOG_FILES)","entries_as_expected=sorted(row['entries'])==list(CATALOG_FILES)"))
add('L07_entries_of_the_line_not_compared',UPDATE,UPDATE.replace("entries_as_expected=row['entries']==list(CATALOG_FILES)","entries_as_expected=True"))
IDENTITY="                        device=row['device'] if integer(row['device']) else None,inode=row['inode'] if integer(row['inode'],1) else None)\n"
add('L08_device_type_unchecked',IDENTITY,IDENTITY.replace("device=row['device'] if integer(row['device']) else None","device=row['device']"))
add('L09_inode_type_unchecked',IDENTITY,IDENTITY.replace("inode=row['inode'] if integer(row['inode'],1) else None","inode=row['inode']"))
add('L10_inode_zero_accepted',IDENTITY,IDENTITY.replace("integer(row['inode'],1)","integer(row['inode'])"))
SIGNED_LINE="            line['as_signed']=(line['created'] and line['epoch_equal'] and line['entries_as_expected'] and line['device'] is not None\n"
add('L11_created_false_accepted',SIGNED_LINE,SIGNED_LINE.replace("line['created'] and ",""))
add('L12_other_epoch_accepted',SIGNED_LINE,SIGNED_LINE.replace("line['epoch_equal'] and ",""))
add('L13_other_entries_accepted',SIGNED_LINE,SIGNED_LINE.replace("line['entries_as_expected'] and ",""))
add('L14_status_other_than_ready_or_refused_kept',"    line['status']=status if type(status) is str and status in ('CATALOG_READY','CATALOG_REFUSED') else 'OTHER'\n",
    "    line['status']='CATALOG_READY' if status!='CATALOG_REFUSED' else status\n")

# ---------------------------------------------------------------- the readback of the journal root
add('B01_other_entries_not_counted',"out['other_entries']=len([name for name in names if name not in CATALOG_FILES])","out['other_entries']=0")
add('B02_files_read_by_following_the_name_blindly',"        if out['files'][CATALOG_FILES[0]].get('type')=='file':\n","        if out['files'][CATALOG_FILES[0]].get('exists'):\n")
EXPECTED="            expected=canonical({'schema':CATALOG_SCHEMA,'epoch':epoch,'device':root.identity[0],'inode':root.identity[1]})\n"
add('B03_expected_identity_swapped',EXPECTED,EXPECTED.replace("'device':root.identity[0],'inode':root.identity[1]","'device':root.identity[1],'inode':root.identity[0]"))
add('B04_expected_epoch_is_the_constant',EXPECTED,EXPECTED.replace("'epoch':epoch,","'epoch':EPOCH_COMPILED,"))
add('B05_epoch_json_compared_as_json',"'equal_to_the_expected_bytes':raw==expected}","'equal_to_the_expected_bytes':strict(raw)==strict(expected)}")
add('B06_epoch_json_compared_by_prefix',"'equal_to_the_expected_bytes':raw==expected}","'equal_to_the_expected_bytes':raw.startswith(expected)}")
add('B07_file_read_need_not_be_the_file_looked_at',"            need((held.st_dev,held.st_ino)==listed[CATALOG_FILES[0]],'FILE_CHANGED_DURING_READ')","            need(True,'FILE_CHANGED_DURING_READ')")
add('B08_root_not_verified_after_the_run',"        try:root.verify(gate);out['root_unchanged']=True\n","        try:out['root_unchanged']=True\n")
add('B09_device_of_a_file_unchecked',"'on_the_device_of_the_root':info.st_dev==root.identity[0]}","'on_the_device_of_the_root':True}")
FILE="    return row.get('exists') is True and (row['type'],row['uid'],row['gid'],row['mode_octal'],row['links'],row['on_the_device_of_the_root'])==(\n        'file',0,0,'%04o'%CATALOG_FILE_MODE,1,True)\n"
add('B10_file_type_unchecked',FILE,"    return row.get('exists') is True and (row['uid'],row['gid'],row['mode_octal'],row['links'],row['on_the_device_of_the_root'])==(\n        0,0,'%04o'%CATALOG_FILE_MODE,1,True)\n")
add('B11_file_owner_unchecked',FILE,"    return row.get('exists') is True and (row['type'],row['gid'],row['mode_octal'],row['links'],row['on_the_device_of_the_root'])==(\n        'file',0,'%04o'%CATALOG_FILE_MODE,1,True)\n")
add('B12_file_group_unchecked',FILE,"    return row.get('exists') is True and (row['type'],row['uid'],row['mode_octal'],row['links'],row['on_the_device_of_the_root'])==(\n        'file',0,'%04o'%CATALOG_FILE_MODE,1,True)\n")
add('B13_file_mode_unchecked',FILE,"    return row.get('exists') is True and (row['type'],row['uid'],row['gid'],row['links'],row['on_the_device_of_the_root'])==(\n        'file',0,0,1,True)\n")
add('B14_file_links_unchecked',FILE,"    return row.get('exists') is True and (row['type'],row['uid'],row['gid'],row['mode_octal'],row['on_the_device_of_the_root'])==(\n        'file',0,0,'%04o'%CATALOG_FILE_MODE,True)\n")
add('B15_file_device_unchecked',FILE,"    return row.get('exists') is True and (row['type'],row['uid'],row['gid'],row['mode_octal'],row['links'])==(\n        'file',0,0,'%04o'%CATALOG_FILE_MODE,1)\n")
EXPECTED_CATALOG="    return (catalog['entries']==len(CATALOG_FILES) and all(file_as_expected(catalog['files'][name]) for name in CATALOG_FILES)\n            and catalog['epoch_json']['equal_to_the_expected_bytes'] is True)\n"
add('B16_a_third_entry_accepted',EXPECTED_CATALOG,EXPECTED_CATALOG.replace("catalog['entries']==len(CATALOG_FILES) and ",""))
add('B17_only_epoch_json_checked',EXPECTED_CATALOG,EXPECTED_CATALOG.replace("for name in CATALOG_FILES)","for name in CATALOG_FILES[:1])"))
add('B18_only_the_lock_checked',EXPECTED_CATALOG,EXPECTED_CATALOG.replace("for name in CATALOG_FILES)","for name in CATALOG_FILES[1:])").replace("\n            and catalog['epoch_json']['equal_to_the_expected_bytes'] is True)",")"))
add('B19_bytes_of_epoch_json_not_required',EXPECTED_CATALOG,EXPECTED_CATALOG.replace("\n            and catalog['epoch_json']['equal_to_the_expected_bytes'] is True)",")"))

# ---------------------------------------------------------------- the verdict of a run that returned
add('R01_engine_status_not_told_apart',"    engine=result['returncode'] in RUN_ENGINE_STATUSES\n","    engine=False\n")
VERDICT="    return 'ENGINE_COULD_NOT_RUN_THE_CONTAINER' if engine and failure is not None else failure\n"
add('R12_engine_status_spends_a_verified_root',VERDICT,"    return 'ENGINE_COULD_NOT_RUN_THE_CONTAINER' if engine else failure\n")
add('R13_engine_status_without_a_verified_catalog_reported_as_the_scripts',VERDICT,"    return failure\n")
JUDGED="    failure=catalog_failure(result['returncode'] if not engine else 0,line,catalog,identity)\n"
add('R14_engine_status_judged_as_a_status_of_the_script',JUDGED,"    failure=catalog_failure(result['returncode'],line,catalog,identity)\n")
add('R15_every_status_but_zero_left_to_the_line_and_the_readback',JUDGED,"    failure=catalog_failure(0,line,catalog,identity)\n")
add('R16_only_125_is_a_status_of_docker_itself',"    engine=result['returncode'] in RUN_ENGINE_STATUSES\n","    engine=result['returncode']==125\n")
add('R02_missing_line_not_told_apart',"    if not line['one_json_line']:return 'SCRIPT_OUTPUT_NOT_ONE_LINE'\n","")
add('R03_refusal_of_the_script_not_told_apart',"    if line['status']=='CATALOG_REFUSED':return 'SCRIPT_REFUSED'\n","")
add('R04_exit_status_of_the_run_ignored',"    if returncode!=0:return 'SCRIPT_FAILED'\n","")
add('R05_line_not_required_as_signed',"    if not line['as_signed']:return 'SCRIPT_LINE_NOT_AS_SIGNED'\n","")
add('R06_identity_of_the_container_not_compared_with_the_hosts',"    if (line['device'],line['inode'])!=tuple(identity):return 'CATALOG_IDENTITY_NOT_THE_HOSTS'\n","")
add('R07_only_the_inode_compared',"    if (line['device'],line['inode'])!=tuple(identity):return 'CATALOG_IDENTITY_NOT_THE_HOSTS'\n","    if line['inode']!=tuple(identity)[1]:return 'CATALOG_IDENTITY_NOT_THE_HOSTS'\n")
add('R08_only_the_device_compared',"    if (line['device'],line['inode'])!=tuple(identity):return 'CATALOG_IDENTITY_NOT_THE_HOSTS'\n","    if line['device']!=tuple(identity)[0]:return 'CATALOG_IDENTITY_NOT_THE_HOSTS'\n")
add('R09_unavailable_readback_not_told_apart',"    if catalog['status']!='COMPLETE':return 'CATALOG_READBACK_UNAVAILABLE'\n    if not catalog_as_expected(catalog):return 'CATALOG_READBACK_MISMATCH'\n",
    "    if catalog['status']!='COMPLETE' or not catalog_as_expected(catalog):return 'CATALOG_READBACK_MISMATCH'\n")
add('R10_host_readback_not_required',"    if not catalog_as_expected(catalog):return 'CATALOG_READBACK_MISMATCH'\n","")
add('R11_unavailable_readback_accepted',"    if catalog['status']!='COMPLETE':return 'CATALOG_READBACK_UNAVAILABLE'\n    if not catalog_as_expected(catalog):return 'CATALOG_READBACK_MISMATCH'\n",
    "    if catalog['status']=='COMPLETE' and not catalog_as_expected(catalog):return 'CATALOG_READBACK_MISMATCH'\n")

# ---------------------------------------------------------------- perform: the precheck, one per refusal
add('K01_executor_identity_unchecked',"            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n","")
add('K02_executor_group_unchecked',"            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n","            need(tuple(host.identity())[0]==0,'EXECUTOR_IDENTITY')\n")
add('K03_umask_inherited',"            host.umask(0o077)\n","")
add('K04_umask_022',"            host.umask(0o077)\n","            host.umask(0o022)\n")
add('K05_boot_of_the_evidence_unchecked',"            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')\n","")
add('K06_docker_run_under_a_configuration_directory_with_content',"            need(precheck['docker_config_entries']==0,'DOCKER_CONFIG_DIRECTORY_NOT_EMPTY')\n","")
add('K07_real_root_of_the_rehearsal_may_hold_entries',"                need(precheck['real_journal_root_entries']==0,'REFERENCE_ROOT_NOT_EMPTY')\n","")
add('K08_existing_throwaway_not_refused_by_the_precheck',"                need(found.get('status')=='COMPLETE' and found['exists'] is False,'DESTINATION_PRESENT')\n","")
add('K09_docker_started_with_a_root_that_holds_entries',"                need(precheck['journal_root_entries']==0,'JOURNAL_ROOT_NOT_EMPTY')\n","")
add('K10_absent_image_not_told_apart',"            except CommandFailed:raise Refused('IMAGE_ABSENT_OR_UNREADABLE') from None\n","            except KeyError:raise Refused('IMAGE_ABSENT_OR_UNREADABLE') from None\n")
add('K11_image_id_not_compared',"            need(image['id']==plan['image_id'],'IMAGE_ID_MISMATCH')\n","")
add('K12_image_revision_not_compared',"            need(image['revision_label']==plan['image_revision'],'IMAGE_REVISION_MISMATCH')\n","")
add('K13_failed_listing_not_told_apart',"            except CommandFailed:raise Refused('CONTAINER_LISTING_FAILED') from None\n            precheck['containers']","            except KeyError:raise Refused('CONTAINER_LISTING_FAILED') from None\n            precheck['containers']")
LOOK="            for handle in pinned+list(handles.values()):handle.verify(gate)\n"
add('K14_no_last_look_at_the_held_directories',LOOK,"")
add('K27_no_last_look_at_the_directory_a_rehearsal_created',LOOK,"            for handle in pinned:handle.verify(gate)\n")
add('K15_no_last_look_at_the_real_root',"            if root is not None:need(count_entries(host,root.fd,gate,MAX_DIRECTORY_ENTRIES)==0,'JOURNAL_ROOT_NOT_EMPTY')\n","")
AFTER="        need(precheck['docker_config_entries_after_the_reads']==0,CONFIG_CHANGED)\n"
add('K16_no_last_look_at_the_configuration_directory',AFTER,"")
UNKNOWN="        need(precheck.get('docker_config_entries_after_the_reads') is not None,CONFIG_UNKNOWN)\n"
add('K52_count_that_could_not_be_taken_reported_as_a_changed_directory',UNKNOWN,"")
add('K53_count_that_could_not_be_taken_accepted',UNKNOWN+AFTER,"        need(not precheck['docker_config_entries_after_the_reads'],CONFIG_CHANGED)\n")
add('K28_what_the_reads_left_not_told_apart_from_what_was_found',"CONFIG_CHANGED='DOCKER_CONFIG_DIRECTORY_NOT_EMPTY_AFTER_THE_READS'","CONFIG_CHANGED='DOCKER_CONFIG_DIRECTORY_NOT_EMPTY'")
COUNTED="            counted=attempt(lambda:count_entries(host,use.fd,gate,MAX_DIRECTORY_ENTRIES))\n"
add('K29_last_look_counts_the_directory_of_the_unit_whatever_docker_was_given',COUNTED,COUNTED.replace("use.fd","config.fd"))
REPORTED="            precheck['docker_config_entries_after_the_reads']=counted if type(counted) is int else None\n"
add('K30_count_after_the_reads_not_reported',REPORTED,REPORTED.replace("=counted if type(counted) is int else None","=0"))
add('K38_count_that_could_not_be_taken_reported_as_zero',REPORTED,REPORTED.replace("counted if type(counted) is int else None","counted if type(counted) is int else 0"))
add('K39_directory_not_counted_after_a_read_that_failed',"        except Exception as error:failure=error\n        if commands.started['READ']:\n","        except Exception as error:raise\n        if commands.started['READ']:\n")
add('K40_directory_counted_although_no_docker_command_was_started',"        if commands.started['READ']:\n","        if True:\n")
add('K41_failure_of_a_read_lost_once_the_directory_was_counted',"        if failure is not None:raise failure\n","")
GIVEN="        if given==0 or code in (CONFIG_CHANGED,CONFIG_UNKNOWN):return code\n"
add('K42_changed_directory_does_not_outrank_the_first_finding',GIVEN,"        return code\n")
add('K43_unknown_count_does_not_outrank_the_first_finding',GIVEN,"        if not given or code in (CONFIG_CHANGED,CONFIG_UNKNOWN):return code\n")
OUTRANKED="        precheck['first_finding']=code;return CONFIG_UNKNOWN if given is None else CONFIG_CHANGED\n"
add('K44_first_finding_not_kept',OUTRANKED,"        return CONFIG_UNKNOWN if given is None else CONFIG_CHANGED\n")
add('K45_unknown_count_reported_as_a_changed_directory',OUTRANKED,"        precheck['first_finding']=code;return CONFIG_CHANGED\n")
add('K46_changed_directory_reported_as_an_unknown_count',OUTRANKED,"        precheck['first_finding']=code;return CONFIG_UNKNOWN\n")
NEVER="            if code in (CONFIG_CHANGED,CONFIG_UNKNOWN):return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,code,{'phase_reached':'PRECHECK'})\n"
add('K47_changed_directory_of_the_unit_called_a_refusal',NEVER,"")
add('K48_unknown_directory_of_the_unit_called_a_refusal',NEVER,NEVER.replace("code in (CONFIG_CHANGED,CONFIG_UNKNOWN)","code==CONFIG_CHANGED"))
add('K49_changed_directory_of_the_unit_called_a_refusal_when_known',NEVER,NEVER.replace("code in (CONFIG_CHANGED,CONFIG_UNKNOWN)","code==CONFIG_UNKNOWN"))
add('K50_precheck_of_a_real_run_decided_without_the_count',"            code=after_reads(code)\n","")
add('K51_reads_of_a_rehearsal_decided_without_the_count',"stop=after_reads(code_of(error,'READS_OS_ERROR' if isinstance(error,OSError) else 'READS_FAILED'))","stop=code_of(error,'READS_OS_ERROR' if isinstance(error,OSError) else 'READS_FAILED')")
BUDGET="            need(gate()>=effects_budget(RUN_ROW)+(FILES_ALLOWANCE_SECONDS if rehearsal else 0),'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')\n"
add('K17_budget_unchecked',BUDGET,"")
add('K18_budget_without_the_reserve',BUDGET,BUDGET.replace("effects_budget(RUN_ROW)","COMMAND_CLASSES['RUN']['seconds']"))
add('K19_budget_without_the_allowance_of_the_rehearsal',BUDGET,BUDGET.replace("(FILES_ALLOWANCE_SECONDS if rehearsal else 0)","0"))
add('K20_budget_with_the_allowance_in_real_mode',BUDGET,BUDGET.replace("(FILES_ALLOWANCE_SECONDS if rehearsal else 0)","FILES_ALLOWANCE_SECONDS"))
IMAGE_READ="        try:image=image_facts(commands,plan['image_id'],docker_config=use_path)\n"
add('K21_image_read_with_roots_own_configuration',IMAGE_READ,"        try:image=image_facts(commands,plan['image_id'])\n")
add('K31_image_read_of_a_rehearsal_under_the_directory_of_the_unit',IMAGE_READ,IMAGE_READ.replace("docker_config=use_path","docker_config=plan['docker_config_chain'][-1]['path']"))
FIRST_LISTING="        try:listed=container_list(commands,docker_config=use_path)\n"
add('K22_first_listing_with_roots_own_configuration',FIRST_LISTING,"        try:listed=container_list(commands)\n")
add('K32_first_listing_of_a_rehearsal_under_the_directory_of_the_unit',FIRST_LISTING,FIRST_LISTING.replace("docker_config=use_path","docker_config=plan['docker_config_chain'][-1]['path']"))
PROBES="                for label,target in (('throwaway',path),('throwaway_docker_config',use_path)):\n"
add('K33_existing_directory_for_docker_not_refused_by_the_precheck',PROBES,"                for label,target in (('throwaway',path),):\n")
add('K34_existing_throwaway_root_not_refused_by_the_precheck',PROBES,"                for label,target in (('throwaway_docker_config',use_path),):\n")
add('K35_probe_that_did_not_establish_absence_accepted',"                    need(found.get('status')=='COMPLETE' and found['exists'] is False,'DESTINATION_PRESENT')\n",
    "                    need(found.get('exists') is not True,'DESTINATION_PRESENT')\n")
add('K36_rehearsal_creates_a_directory_for_a_docker_that_cannot_be_started',"                binary(host,BINARIES['docker'],gate)","                pass")
add('K37_last_look_of_a_real_run_without_its_root',"                before=reads(config,root)\n","                before=reads(config,None)\n")
add('K23_precheck_failure_is_not_a_refusal',"            return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})\n","            return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,code,{'phase_reached':'PRECHECK'})\n")

# ---------------------------------------------------------------- perform: the effects and what is said about them
add('E01_container_started_in_a_directory_that_is_not_as_asked',"    return None if entry['state']=='CREATED_DURABLE' else (entry['code'] or 'CREATION_FAILED')\n",
    "    return None if entry['state'].startswith('CREATED') else (entry['code'] or 'CREATION_FAILED')\n")
SPENT="            elif not state.clean():facts['verdict']='NOT_TO_BE_USED_AGAIN'\n"
add('E02_created_directory_not_labelled_as_spent',SPENT,"")
add('E39_refused_rehearsal_labelled_as_spent',SPENT,"            else:facts['verdict']='NOT_TO_BE_USED_AGAIN'\n")
RUN="            result=container_effect(state,commands,RUN_ROW,plan['image_id'],mounts,words,script,docker_config=use_path)\n"
add('E03_run_with_roots_own_configuration',RUN,"            result=container_effect(state,commands,RUN_ROW,plan['image_id'],mounts,words,script)\n")
add('E40_run_of_a_rehearsal_under_the_directory_of_the_unit',RUN,RUN.replace("docker_config=use_path","docker_config=plan['docker_config_chain'][-1]['path']"))
FIRST="            stop=directory_stop(entry)\n            if stop is None:\n                try:before=reads(handles['DOCKER_CONFIG'],None)\n"
add('E41_reads_made_whatever_became_of_the_directory_for_docker',FIRST,FIRST.replace("stop=directory_stop(entry)","stop=None"))
add('E42_last_look_of_a_rehearsal_at_the_directory_of_the_unit',FIRST,FIRST.replace("reads(handles['DOCKER_CONFIG'],None)","reads(config,None)"))
add('E43_failing_call_of_a_read_not_told_apart',"stop=after_reads(code_of(error,'READS_OS_ERROR' if isinstance(error,OSError) else 'READS_FAILED'))","stop=after_reads(code_of(error,'READS_FAILED'))")
SECOND="                stop=directory_stop(entry)\n            if stop is None:root=handles['JOURNAL_ROOT']\n"
add('E44_container_started_whatever_became_of_the_throwaway_root',SECOND,SECOND.replace("stop=directory_stop(entry)","stop=None"))
add('E45_directory_for_docker_created_beside_the_real_root',"            entry=create_directory('DOCKER_CONFIG',use_path,PRIVATE_DIRECTORY_MODE,parent,host,gate,state,handles)",
    "            entry=create_directory('DOCKER_CONFIG',use_path,PRIVATE_DIRECTORY_MODE,reference,host,gate,state,handles)")
add('E46_rehearsal_gives_docker_the_directory_of_the_unit',"    return plan['docker_config_chain'][-1]['path'] if plan['mode']=='REAL' else journal_path(plan)+THROWAWAY_CONFIG_SUFFIX\n",
    "    return plan['docker_config_chain'][-1]['path']\n")
add('E47_directory_for_docker_is_the_throwaway_root_itself',"THROWAWAY_CONFIG_SUFFIX='.docker-cli' ","THROWAWAY_CONFIG_SUFFIX='' ")
add('E48_directory_for_docker_named_with_a_hyphen',"THROWAWAY_CONFIG_SUFFIX='.docker-cli' ","THROWAWAY_CONFIG_SUFFIX='-docker-cli' ")
HELD="            use=handles['DOCKER_CONFIG'] if rehearsal else config\n"
add('E49_directory_of_the_unit_read_back_after_the_run_of_a_rehearsal',HELD,"            use=config\n")
SAID="                facts['docker_config']={'path':use_path,'is_the_directory_of_the_unit':not rehearsal,'entries_before':0,\n"
add('E50_receipt_names_the_directory_of_the_unit_for_a_rehearsal',SAID,SAID.replace("'path':use_path,","'path':plan['docker_config_chain'][-1]['path'],"))
add('E51_receipt_says_the_directory_of_the_unit_for_a_rehearsal',SAID,SAID.replace("'is_the_directory_of_the_unit':not rehearsal,","'is_the_directory_of_the_unit':True,"))
STATUS="                    if result['returncode']!=0:stop='ENGINE_STATUS_AFTER_A_VERIFIED_CATALOG'\n                    elif containers['status']!='COMPLETE'"
add('E52_engine_status_after_a_verified_catalog_not_reported',STATUS,"                    if containers['status']!='COMPLETE'")
add('E53_no_descriptor_closed_when_a_walked_directory_cannot_be_held',"        try:host.close(fd)\n        except Exception:pass\n        raise\n","        raise\n")
add('E54_chains_walked_without_the_device',"    fd=walk_pinned(host,rows,gate,observed)\n","    fd=walk_pinned(host,rows,gate,observed,False)\n")
add('E55_held_directories_verified_without_the_device',"    try:return Pinned(host,fd,rows=rows)\n","    try:return Pinned(host,fd,rows=rows,compare_device=False)\n")
add('E04_unstarted_rehearsal_not_labelled_as_spent',"                if rehearsal:facts['verdict']='NOT_TO_BE_USED_AGAIN'\n","")
add('E05_state_of_the_run_always_returned',"                run['state']='RETURNED' if result['returned'] else 'DID_NOT_RETURN'\n","                run['state']='RETURNED'\n")
add('E06_readback_for_the_compiled_epoch',"                catalog=catalog_readback(host,gate,root,plan['epoch']);facts['catalog']=catalog\n","                catalog=catalog_readback(host,gate,root,EPOCH_COMPILED);facts['catalog']=catalog\n")
LISTING="                listing=attempt(lambda:container_list(commands,docker_config=use_path))\n"
add('E07_second_listing_with_roots_own_configuration',LISTING,"                listing=attempt(lambda:container_list(commands))\n")
add('E56_second_listing_of_a_rehearsal_under_the_directory_of_the_unit',LISTING,LISTING.replace("docker_config=use_path","docker_config=plan['docker_config_chain'][-1]['path']"))
add('E57_new_containers_told_by_name',"known=set(row['id'] for row in before);new=[row for row in listing if row['id'] not in known]","known=set(row['name'] for row in before);new=[row for row in listing if row['name'] not in known]")
add('E08_new_containers_compared_by_count',"new=[row for row in listing if row['id'] not in known]","new=listing[len(known):]")
add('E09_configuration_directory_not_verified_after_the_run',"                    use.verify(gate);return count_entries(host,use.fd,gate,MAX_DIRECTORY_ENTRIES)\n","                    return count_entries(host,use.fd,gate,MAX_DIRECTORY_ENTRIES)\n")
FAILURE="                failure=run_failure(result,line,catalog,root.identity[:2]) if result['returned'] else (result['code'] or 'COMMAND_FAILED')\n"
add('E10_run_that_did_not_return_judged_by_what_is_on_disk',FAILURE,"                failure=run_failure(result,line,catalog,root.identity[:2])\n")
SETTLE="                    if failure is None:state.done()\n                    else:state.unknown()\n"
add('E11_unverified_run_settled_as_done',SETTLE,"                    state.done()\n")
add('E12_unverified_run_settled_as_nothing_changed',SETTLE,"                    if failure is None:state.done()\n                    else:state.fail()\n")
add('E13_verified_run_left_uncertain',SETTLE,"                    state.unknown()\n")
add('E14_unverified_root_not_labelled_as_spent',"                if failure is not None:stop=failure;facts['verdict']='NOT_TO_BE_USED_AGAIN'\n","                if failure is not None:stop=failure\n")
add('E15_listing_failure_after_the_run_ignored',"                    elif containers['status']!='COMPLETE':stop='CONTAINER_LISTING_UNAVAILABLE_AFTER_RUN'\n","")
add('E16_new_container_ignored',"                    elif containers['not_there_before']:stop='CONTAINER_PRESENT_THAT_WAS_NOT_THERE_BEFORE'\n","")
add('E17_unavailable_configuration_readback_ignored',"                    elif facts['docker_config']['entries_after'] is None:stop='DOCKER_CONFIG_READBACK_UNAVAILABLE'\n","")
add('E18_content_in_the_configuration_directory_ignored',"                    elif facts['docker_config']['entries_after']:stop='DOCKER_CONFIG_DIRECTORY_NOT_EMPTY_AFTER_RUN'\n","")
add('E19_findings_beside_a_verified_catalog_called_verified',"                    facts['verdict']='CATALOG_READY_VERIFIED' if stop is None else 'CATALOG_VERIFIED_WITH_FINDINGS'\n","                    facts['verdict']='CATALOG_READY_VERIFIED'\n")
add('E20_partial_called_a_refusal',"        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)\n",
    "        return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n")
add('E21_clean_refusal_called_a_partial',"        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n","")
add('E22_objects_left_without_the_files_of_the_container',"        if catalog is not None:left=None if catalog['entries'] is None else left+catalog['entries']\n","")
MODIFIED="        touched=[False] if rehearsal else [None if given is None else given>0,False if catalog is None else (None if catalog['entries'] is None else catalog['entries']>0)]\n"
add('E23_modified_real_root_not_said',MODIFIED,MODIFIED.replace("False if catalog is None else (None if catalog['entries'] is None else catalog['entries']>0)","False"))
add('E24_rehearsal_said_to_modify_an_existing_object',MODIFIED,MODIFIED.replace("[False] if rehearsal else ",""))
add('E58_modified_directory_of_the_unit_not_said',MODIFIED,MODIFIED.replace("[None if given is None else given>0,","[False,"))
add('E59_unknown_state_of_the_directory_of_the_unit_reported_as_unmodified',MODIFIED,MODIFIED.replace("None if given is None else given>0","bool(given)"))
SAID_MODIFIED="            pre_existing_objects_modified=True if True in touched else (None if None in touched else False),**extra))\n"
add('E60_unknown_modification_outranks_a_known_one',SAID_MODIFIED,SAID_MODIFIED.replace("True if True in touched else (None if None in touched else False)","None if None in touched else (True in touched)"))
add('E61_unknown_modification_reported_as_none_happened',SAID_MODIFIED,SAID_MODIFIED.replace("True if True in touched else (None if None in touched else False)","True in touched"))
GIVEN_COUNT="        given=precheck.get('docker_config_entries_after_the_reads',0) if facts['docker_config'] is None else facts['docker_config']['entries_after']\n"
add('E62_what_docker_left_before_the_container_not_counted',GIVEN_COUNT,GIVEN_COUNT.replace("precheck.get('docker_config_entries_after_the_reads',0)","0"))
add('E63_what_docker_left_after_the_container_not_counted',GIVEN_COUNT,GIVEN_COUNT.replace("facts['docker_config']['entries_after']","0"))
LEFT="        if left is not None:left=None if given is None else left+given\n"
add('E64_entries_docker_left_not_among_the_objects_left',LEFT,"")
add('E65_unknown_count_of_what_docker_left_reported_as_none_left',LEFT,"        if left is not None:left=left+(given or 0)\n")
add('E25_receipt_without_the_mode',"observed_at=begun.isoformat(),mode=plan['mode'],effects=effects_of(plan),","observed_at=begun.isoformat(),mode=None,effects=effects_of(plan),")
add('E26_seconds_of_the_run_not_measured',"                       seconds=round(ended-started,3) if type(started) in (int,float) and type(ended) in (int,float) else None)\n","                       seconds=None)\n")
add('E27_identity_of_the_root_not_in_the_receipt',"            facts['root']={'path':path,'device':root.identity[0],'inode':root.identity[1],'created_by_this_run':rehearsal}\n",
    "            facts['root']={'path':path,'device':None,'inode':None,'created_by_this_run':rehearsal}\n")
add('E28_descriptors_left_open',"        for handle in list(handles.values())+pinned:\n","        for handle in []:\n")
add('E29_not_started_run_reported_without_its_code',"            run.update(code=result['code'],returncode=result['returncode'],","            run.update(code=None,returncode=result['returncode'],")
add('E30_reduction_keeps_the_rows',"def _reduce_observed(receipt):receipt['observed_rows']={'reduced_for_size':True}","def _reduce_observed(receipt):receipt['observed_rows']=receipt['observed_rows']")

# ---------------------------------------------------------------- second pass: what the first list did not ask
add('G01_no_gate_before_the_first_observation',"    gate()                                                    # first gate call: before anything is observed\n","")
add('K24_last_look_at_the_first_held_directory_only',LOOK,LOOK.replace("pinned+list(handles.values())","pinned[:1]+list(handles.values())"))
add('K25_last_look_skips_the_configuration_directory',LOOK,LOOK.replace("pinned+list(handles.values())","pinned[1:]+list(handles.values())"))
def without_device(name,chain,rows):
    """The walk of one chain as the earlier bytes wrote it, without the comparison of the device."""
    return "%s=Pinned(host,walk_pinned(host,plan['%s'],gate,observed['%s'],False),rows=plan['%s']);pinned.append(%s)\n"%(name,chain,rows,chain,name)
CONFIG_WALK="            config=pin_chain(host,plan['docker_config_chain'],gate,observed['docker_config']);pinned.append(config)\n"
add('W01_configuration_directory_walked_without_the_device',CONFIG_WALK,"            "+without_device('config','docker_config_chain','docker_config'))
add('W02_rows_of_the_configuration_directory_not_reported',CONFIG_WALK,CONFIG_WALK.replace("observed['docker_config'])","[])"))
REFERENCE_WALK="                reference=pin_chain(host,plan['reference_chain'],gate,observed['reference']);pinned.append(reference)\n"
add('W03_real_root_of_the_rehearsal_walked_without_the_device',REFERENCE_WALK,"                "+without_device('reference','reference_chain','reference'))
add('W04_rows_of_the_real_root_not_reported_by_the_rehearsal',REFERENCE_WALK,REFERENCE_WALK.replace("observed['reference'])","[])"))
PARENT_WALK="                parent=pin_chain(host,plan['journal_chain'],gate,observed['journal']);pinned.append(parent)\n"
add('W05_parent_of_the_throwaway_walked_without_the_device',PARENT_WALK,"                "+without_device('parent','journal_chain','journal'))
add('W06_rows_of_the_parent_not_reported',PARENT_WALK,PARENT_WALK.replace("observed['journal'])","[])"))
ROOT_WALK="                root=pin_chain(host,plan['journal_chain'],gate,observed['journal']);pinned.append(root)\n"
add('W07_journal_root_walked_without_the_device',ROOT_WALK,"                "+without_device('root','journal_chain','journal'))
add('W08_rows_of_the_journal_root_not_reported',ROOT_WALK,ROOT_WALK.replace("observed['journal'])","[])"))
add('W10_parent_of_the_throwaway_not_held_for_the_last_look',PARENT_WALK,PARENT_WALK.replace(";pinned.append(parent)\n",";pinned.append(config)\n"))
add('W09_real_root_of_the_rehearsal_not_held_for_the_last_look',REFERENCE_WALK,REFERENCE_WALK.replace(";pinned.append(reference)\n",";pinned.append(config)\n"))
add('E31_reduction_keeps_the_container_rows',"    if type(receipt.get('containers')) is dict:receipt['containers']['rows']=[]\n","    if type(receipt.get('containers')) is dict:receipt['containers']['rows']=receipt['containers']['rows']\n")
add('E32_receipt_without_the_instant_of_the_observation',"dict(bound,observed_at=begun.isoformat(),mode=plan['mode'],","dict(bound,observed_at=None,mode=plan['mode'],")
add('E33_receipt_without_the_rows_as_read',"            observed_rows=observed,precheck=precheck,","            observed_rows=None,precheck=precheck,")
add('E34_receipt_without_the_precheck',"            observed_rows=observed,precheck=precheck,","            observed_rows=observed,precheck=None,")
add('E35_receipt_without_the_command_counts',"commands_started=dict(commands.started),mutating_calls=state.counts(),","commands_started=None,mutating_calls=state.counts(),")
add('E36_receipt_without_the_clock',"            clock=timing(begun,mark,clock,monotonic),","            clock=None,")
LINE="    line={'returncode':result['returncode'],'bytes':len(output),'sha256':sha(output) if output else None,'one_json_line':False,'status':None,\n"
add('L15_hash_of_the_printed_line_not_reported',LINE,LINE.replace("'sha256':sha(output) if output else None","'sha256':None"))
add('L16_size_of_the_printed_line_not_reported',LINE,LINE.replace("'bytes':len(output)","'bytes':0"))
add('L17_exit_status_not_reported_with_the_line',LINE,LINE.replace("'returncode':result['returncode']","'returncode':None"))
add('E37_script_given_to_the_container_is_not_the_pinned_one',"    script=script_bytes();rehearsal=plan['mode']=='REHEARSAL'","    script=script_bytes()+b'\\n';rehearsal=plan['mode']=='REHEARSAL'")
add('E38_directory_of_the_rehearsal_created_beside_the_real_root',"            entry=create_directory('JOURNAL_ROOT',path,PRIVATE_DIRECTORY_MODE,parent,host,gate,state,handles)","            entry=create_directory('JOURNAL_ROOT',path,PRIVATE_DIRECTORY_MODE,reference,host,gate,state,handles)")
add('K26_failing_system_call_of_the_precheck_not_told_apart',"            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')\n","            code=code_of(error,'PRECHECK_FAILED')\n")
add('B20_failing_system_call_of_the_readback_not_told_apart',"        out['code']=code_of(error,'READBACK_OS_ERROR' if isinstance(error,OSError) else 'READBACK_FAILED')\n","        out['code']=code_of(error,'READBACK_FAILED')\n")
add('B21_readback_reported_complete_after_a_failure',"    out={'status':'UNAVAILABLE','code':None,'entries':None,","    out={'status':'COMPLETE','code':None,'entries':None,")

# ---------------------------------------------------------------- third pass: the mutants of the reviewer that survived
# the first two passes (review of 2026-10-02), each answered by a test of tests/test_review_findings.py or by an
# assertion added to tests/test_catalog_init.py.
add('V11_real_epoch_accepted_by_its_prefix',EPOCH,EPOCH.replace("plan['epoch']==EPOCH_COMPILED","plan['epoch'].startswith(EPOCH_COMPILED)"))
add('V12_unknown_number_of_objects_left_reported_as_a_number',"        if catalog is not None:left=None if catalog['entries'] is None else left+catalog['entries']\n",
    "        if catalog is not None:left=left+(catalog['entries'] or 0)\n")
add('V13_unknown_modification_reported_as_false',MODIFIED,MODIFIED.replace("(None if catalog['entries'] is None else catalog['entries']>0)","bool(catalog['entries'])"))
add('V14_expected_hash_is_the_observed_one',"'expected_sha256':sha(expected)","'expected_sha256':sha(raw)")
add('V15_root_unchanged_false_for_any_refusal',"            if str(error)=='PARENT_REPLACED':out['root_unchanged']=False\n","            out['root_unchanged']=False\n")
add('V16_container_path_of_65_characters',TARGET,TARGET.replace("{0,63}') and target[1:]","{0,64}') and target[1:]"))
add('V17_entry_limit_off_by_one',"need(len(names)<=MAX_CATALOG_ENTRIES,'ENTRY_LIMIT')","need(len(names)<MAX_CATALOG_ENTRIES,'ENTRY_LIMIT')")
add('V18_throwaway_label_of_41_characters',"THROWAWAY_NAME='c3po-bar-rehearsal-[a-z0-9][a-z0-9-]{0,39}'","THROWAWAY_NAME='c3po-bar-rehearsal-[a-z0-9][a-z0-9-]{0,40}'")
add('V19_rehearsal_epoch_of_81_characters',"REHEARSAL_EPOCH='R2D2-V2-DIAG-[A-Za-z0-9_-]{1,80}'","REHEARSAL_EPOCH='R2D2-V2-DIAG-[A-Za-z0-9_-]{1,81}'")
add('V20_activation_allowed',"\nACTIVATION_ALLOWED=False\n","\nACTIVATION_ALLOWED=True\n")
add('V21_readback_without_its_first_gate',"        gate();names=[];listed={}\n","        names=[];listed={}\n")

