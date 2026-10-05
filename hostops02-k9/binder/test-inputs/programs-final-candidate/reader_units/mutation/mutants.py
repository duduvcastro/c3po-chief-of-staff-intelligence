"""The mutants of the reader units' own part. Each row: (name, target, exact anchor, replacement); target 'op' is the
built source build/reader_units.py, in which the anchor must occur exactly once (mutate.py check). The rule of the
family: one mutant per member of effects_of(), one per refusal of validate_plan, of the render and of the precheck;
here also the constants of the epoch and of the placement, the scan, the order of the effects and what the run does
with each failure. EFFECTS and REFUSALS name, for each member and each code, the mutant that answers for it;
coverage() compares both tables with the source itself (the members effects_of() returns; the codes the operation
part can raise, return or record), so a new member or a new refusal without a mutant is an error of `mutate.py check`.
Modelled on K4-E0's list.

Codes left out of the comparison, with the reason: the fallbacks PRECHECK_OS_ERROR, PRECHECK_FAILED, INSTALL_FAILED,
FILE_UNREADABLE and PLACEMENT_INVALID (a code_of() fallback or the second branch of `findings[0] if findings else`,
never reached while the parts and the rules give a code), and PATH_CHANGED (the identity check between the lstat and
the open of a dependency directory: a race the emulation cannot interleave, no host call lies between the two)."""
import ast
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

# ---------------------------------------------------------------- constants of the epoch, the placement and the family
add('C01_another_epoch',"READER_EPOCH='R2D2-V2-SHADOW-2026-10-05'","READER_EPOCH='R2D2-V2-SHADOW-2026-09-28'",effect='epoch')
add('C02_units_in_the_runtime_directory',"UNIT_DIRECTORY='/etc/systemd/system'\n","UNIT_DIRECTORY='/run/systemd/system'\n")
add('C03_units_0640',"UNIT_MODE=0o644","UNIT_MODE=0o640")
add('C04_service_of_another_name',"READER_SERVICE_NAME='c3po-reader.service'","READER_SERVICE_NAME='c3po-reader2.service'")
add('C05_timer_of_another_name',"READER_TIMER_NAME='c3po-reader.timer'","READER_TIMER_NAME='c3po-reader2.timer'")
add('C06_alert_of_another_name',"READER_ALERT_NAME='c3po-reader-alert.service'","READER_ALERT_NAME='c3po-reader-alarm.service'")
add('C07_timer_installed_first',"UNIT_ORDER=(('READER_SERVICE',READER_SERVICE_NAME),('READER_TIMER',READER_TIMER_NAME),",
    "UNIT_ORDER=(('READER_TIMER',READER_TIMER_NAME),('READER_SERVICE',READER_SERVICE_NAME),")
add('C08_image_of_another_build',"'IMAGE_ID':'sha256:f86bfb198c186657598c2c410fb39ca3dfed781d0db0522b9a796b80275cb621',",
    "'IMAGE_ID':'sha256:f86bfb198c186657598c2c410fb39ca3dfed781d0db0522b9a796b80275cb622',",effect='values.IMAGE_ID')
add('C09_data_volume_elsewhere',"'HOST_DATA_ROOT':'/mnt/day-d-data',","'HOST_DATA_ROOT':'/mnt/day-e-data',",effect='values.HOST_DATA_ROOT')
add('C10_journal_inside_the_data_volume',"'HOST_JOURNAL_ROOT':'/var/lib/c3po-bar/journal',","'HOST_JOURNAL_ROOT':'/var/lib/c3po-bar/journal2',",effect='values.HOST_JOURNAL_ROOT')
add('C11_container_journal_elsewhere',"'CONTAINER_JOURNAL_ROOT':'/c3po-bar-journal',","'CONTAINER_JOURNAL_ROOT':'/c3po-journal',",effect='values.CONTAINER_JOURNAL_ROOT')
add('C12_capacity_elsewhere',"'HOST_CAPACITY_ROOT':'/var/lib/c3po-capacity',","'HOST_CAPACITY_ROOT':'/var/lib/c3po-capacity2',",effect='values.HOST_CAPACITY_ROOT')
add('C13_source_root_on_the_data_volume',"'HOST_SOURCE_ROOT':'/var/lib/c3po/r2d2-v2-source-20261005',","'HOST_SOURCE_ROOT':'/mnt/r2d2-v2-source-20261005',",effect='values.HOST_SOURCE_ROOT')
add('C14_source_target_of_k4_tests_renamed',"'CONTAINER_SOURCE_ROOT':'/c3po-source',","'CONTAINER_SOURCE_ROOT':'/c3po-sources',",effect='values.CONTAINER_SOURCE_ROOT')
add('C15_config_of_the_producer',"'HOST_CONFIG_DIR':'/etc/c3po-reader',","'HOST_CONFIG_DIR':'/etc/c3po-reader2',",effect='values.HOST_CONFIG_DIR')
add('C16_network_of_the_database_loopback',"'NETWORK':'c3po_c3po_internal'}","'NETWORK':'c3po_db_loopback'}",effect='values.NETWORK')
add('C17_producer_of_another_name',"PRODUCER_SERVICE_NAME='c3po-massive.service'","PRODUCER_SERVICE_NAME='c3po-massive2.service'")
add('C18_producer_of_other_bytes',"PRODUCER_SHA256='662c57b939d1a21e67e332434d3fa40368e2d503f3772f1cf3f7bd3631bdbc06'",
    "PRODUCER_SHA256='662c57b939d1a21e67e332434d3fa40368e2d503f3772f1cf3f7bd3631bdbc07'")
add('C19_producer_one_byte_longer',"PRODUCER_BYTES=1674","PRODUCER_BYTES=1675")
add('C20_reload_owner_is_the_supervisor_activation',"DAEMON_RELOAD_OWNER='GO_WRITE_HOSTOPS02_K13_READER_SWITCH_01'","DAEMON_RELOAD_OWNER='GO_WRITE_HOSTOPS02_K5_ACTIVATE_01'",
    effect='daemon_reload.owner')
add('C21_catalogue_without_its_lock',"CATALOG_FILE_NAMES=('epoch.json','maintenance.lock')","CATALOG_FILE_NAMES=('epoch.json',)")
add('C22_catalogue_files_0644',"CATALOG_FILE_MODE=0o600","CATALOG_FILE_MODE=0o644")
add('C23_template_revision_of_the_release',"TEMPLATE_REVISION='4a6f7675b8e418e0e7ee55a446250815f3bd5562'","TEMPLATE_REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'",
    effect='template_revision')
add('C24_service_template_one_restart_more',"StartLimitBurst=40\nOnFailure","StartLimitBurst=41\nOnFailure")
add('C25_service_template_hash_follows_the_change',"READER_SERVICE_TEMPLATE_SHA256='3dc976807a0ff443307fa12e357d478980441b26d19761b0d7964b5580327770'",
    "READER_SERVICE_TEMPLATE_SHA256='3dc976807a0ff443307fa12e357d478980441b26d19761b0d7964b5580327771'")
add('C26_timer_template_without_the_boot_trigger',"OnBootSec=90s\n","OnBootSec=30s\n")
add('C27_alert_template_writes_elsewhere',"> /var/lib/c3po-reader/failed.","> /var/lib/c3po-reader/fail.")
add('C28_config_counted_eight_times',"'HOST_CONFIG_DIR':9,'NETWORK':1}","'HOST_CONFIG_DIR':8,'NETWORK':1}")
add('C29_host_path_grammar_allows_an_equal_sign',"HOST_PATH_GRAMMAR='/[A-Za-z0-9._/-]+'","HOST_PATH_GRAMMAR='/[A-Za-z0-9._=/-]+'")
add('C30_container_target_grammar_any_depth',"CONTAINER_TARGET_GRAMMAR='/c3po-[a-z0-9][a-z0-9-]*'","CONTAINER_TARGET_GRAMMAR='/[a-z0-9][a-z0-9/-]*'")
add('C31_capacity_target_not_taken',"CONTAINER_TARGETS_TAKEN=('/c3po-capacity','/c3po-reader')","CONTAINER_TARGETS_TAKEN=('/c3po-reader',)")
add('C32_launcher_target_not_taken',"CONTAINER_TARGETS_TAKEN=('/c3po-capacity','/c3po-reader')","CONTAINER_TARGETS_TAKEN=('/c3po-capacity',)")
add('C33_network_grammar_any_first_character',"NETWORK_GRAMMAR='[A-Za-z0-9][A-Za-z0-9_.-]*'","NETWORK_GRAMMAR='[A-Za-z0-9_.-]+'")
add('R10b_container_network_by_grammar',"NETWORK_GRAMMAR='[A-Za-z0-9][A-Za-z0-9_.-]*'","NETWORK_GRAMMAR='[A-Za-z0-9][A-Za-z0-9_.:-]*'",refusal='NETWORK_FORBIDDEN')
add('C34_bridge_allowed',"FORBIDDEN_NETWORKS=('host','none','bridge')","FORBIDDEN_NETWORKS=('host','none')")
add('C35_host_allowed',"FORBIDDEN_NETWORKS=('host','none','bridge')","FORBIDDEN_NETWORKS=('none','bridge')")
add('C36_percent_allowed',"TEMPLATE_FORBIDDEN_CHARACTERS=('%','$','\"',\"'\",';')","TEMPLATE_FORBIDDEN_CHARACTERS=('$','\"',\"'\",';')")
add('C37_semicolon_allowed',"TEMPLATE_FORBIDDEN_CHARACTERS=('%','$','\"',\"'\",';')","TEMPLATE_FORBIDDEN_CHARACTERS=('%','$','\"',\"'\")")
add('C38_unit_limit_of_a_document',"MAX_UNIT_BYTES=16384","MAX_UNIT_BYTES=65536")
add('C39_allowance_one_second_less',"WRITE_ALLOWANCE_SECONDS=15 ","WRITE_ALLOWANCE_SECONDS=14 ")
add('C40_allowance_one_second_more',"WRITE_ALLOWANCE_SECONDS=15 ","WRITE_ALLOWANCE_SECONDS=16 ")
add('C41_date_class_of_the_first_session_only',"DATE_CLASS='WRITE_SESSIONS'","DATE_CLASS='WRITE_FIRST_SESSION'")
add('C42_date_class_of_the_whole_epoch',"DATE_CLASS='WRITE_SESSIONS'","DATE_CLASS='WRITE_EPOCH'")
add('C43_precheck_not_cited',"EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,PRODUCER_INSTALL_OPERATION,","EVIDENCE_OPERATIONS=(PRODUCER_INSTALL_OPERATION,")
add('C44_catalogue_not_cited',",PRODUCER_READBACK_OPERATION,CATALOG_INIT_OPERATION)",",PRODUCER_READBACK_OPERATION)")
add('C45_producer_readback_not_cited',"PRODUCER_INSTALL_OPERATION,PRODUCER_READBACK_OPERATION,CATALOG","PRODUCER_INSTALL_OPERATION,CATALOG")
add('C46_catalogue_of_another_operation',"CATALOG_INIT_OPERATION='GO_WRITE_HOSTOPS02_CATALOG_INIT_01'","CATALOG_INIT_OPERATION='GO_WRITE_HOSTOPS02_CATALOG_INIT_02'")
add('C47_evidence_not_required',"EVIDENCE_REQUIRED=True","EVIDENCE_REQUIRED=False")
add('C48_gate_span_of_a_read',"MAX_GATE_SPAN_SECONDS=900","MAX_GATE_SPAN_SECONDS=3600")
add('C49_activation_allowed',"ACTIVATION_ALLOWED=False","ACTIVATION_ALLOWED=True")
add('C50_scope_says_a_process_is_started',"       'external_processes':0,\n       'never'","       'external_processes':1,\n       'never'")
add('C51_scope_never_list_loses_daemon_reload',"'never':['a process','systemctl','daemon-reload',","'never':['a process','systemctl',")
add('C52_scope_loses_the_catalogue',"       'catalog':{'files':list(CATALOG_FILE_NAMES),","       'catalogue':{'files':list(CATALOG_FILE_NAMES),")
add('C53_scope_loses_the_allowance',"'leftovers':MAX_LEFTOVERS,'write_allowance_seconds':WRITE_ALLOWANCE_SECONDS,","'leftovers':MAX_LEFTOVERS,")
add('C54_lookup_without_the_control_directory',"SCAN_DIRECTORIES=('/etc/systemd/system.control','/run/systemd/system.control',","SCAN_DIRECTORIES=('/run/systemd/system.control',")
add('C55_lookup_without_the_runtime_control',"'/etc/systemd/system.control','/run/systemd/system.control','/run/systemd/transient',","'/etc/systemd/system.control','/run/systemd/transient',")
add('C56_lookup_without_transient',"'/run/systemd/system.control','/run/systemd/transient',\n","'/run/systemd/system.control',\n")
add('C57_lookup_without_generator_early',"                  '/run/systemd/generator.early','/etc/systemd/system',","                  '/etc/systemd/system',")
add('C58_lookup_without_the_install_directory',"'/run/systemd/generator.early','/etc/systemd/system','/etc/systemd/system.attached',","'/run/systemd/generator.early','/etc/systemd/system.attached',")
add('C59_lookup_without_attached',"'/etc/systemd/system','/etc/systemd/system.attached',\n","'/etc/systemd/system',\n")
add('C60_lookup_without_runtime',"                  '/run/systemd/system','/run/systemd/system.attached','/run/systemd/generator',","                  '/run/systemd/system.attached','/run/systemd/generator',")
add('C61_lookup_without_runtime_attached',"'/run/systemd/system','/run/systemd/system.attached','/run/systemd/generator',","'/run/systemd/system','/run/systemd/generator',")
add('C62_lookup_without_generator',"'/run/systemd/system.attached','/run/systemd/generator',\n","'/run/systemd/system.attached',\n")
add('C63_lookup_without_usr_local',"                  '/usr/local/lib/systemd/system','/usr/lib/systemd/system',","                  '/usr/lib/systemd/system',")
add('C64_lookup_without_usr_lib',"'/usr/local/lib/systemd/system','/usr/lib/systemd/system','/run/systemd/generator.late')","'/usr/local/lib/systemd/system','/run/systemd/generator.late')")
add('C65_lookup_without_generator_late',"'/usr/lib/systemd/system','/run/systemd/generator.late')","'/usr/lib/systemd/system')")
add('C66_wants_not_a_dependency_directory',"DEPENDENCY_SUFFIXES=('.wants','.requires','.upholds')","DEPENDENCY_SUFFIXES=('.requires','.upholds')")
add('C67_requires_not_a_dependency_directory',"DEPENDENCY_SUFFIXES=('.wants','.requires','.upholds')","DEPENDENCY_SUFFIXES=('.wants','.upholds')")
add('C68_upholds_not_a_dependency_directory',"DEPENDENCY_SUFFIXES=('.wants','.requires','.upholds')","DEPENDENCY_SUFFIXES=('.wants','.requires')")
add('C69_scan_limit_one_more',"MAX_SCAN_ENTRIES=4096","MAX_SCAN_ENTRIES=4097")
add('C70_findings_one_more',"MAX_FINDINGS=64","MAX_FINDINGS=65")
add('C71_sixteen_leftovers_refused',"MAX_LEFTOVERS=16","MAX_LEFTOVERS=15")
add('C72_seventeen_leftovers_accepted',"MAX_LEFTOVERS=16","MAX_LEFTOVERS=17")
add('C73_no_type_level_drop_in',"    return [name+'.d',suffix+'.d']+['-'.join","    return [name+'.d']+['-'.join")
add('C74_no_dash_truncated_drop_in',"for index in range(1,len(parts))]","for index in range(1,1)]")

# ---------------------------------------------------------------- effects_of: one mutant per member
add('E01_operation',"    return {'operation':OPERATION,'epoch':READER_EPOCH,","    return {'operation':PHASE,'epoch':READER_EPOCH,",effect='operation')
add('E02_directory_of_the_journal',"'directory':chain_effects(plan['unit_rows']),","'directory':chain_effects(plan['journal_rows']),",effect='directory')
add('E03_every_unit_said_absent',"                      'expect':'ABSENT' if unit['expect']=='ABSENT' else 'PRESENT'} for unit in plan['units']],",
    "                      'expect':'ABSENT'} for unit in plan['units']],",effect='units')
add('E04_every_unit_with_the_service_hash',"'rendered_sha256':sha(renders[unit['key']]),'rendered_bytes':len(renders[unit['key']]),",
    "'rendered_sha256':sha(renders['READER_SERVICE']),'rendered_bytes':len(renders[unit['key']]),")
add('E05_files_to_create_counts_every_unit',"'files_to_create':sum(1 for unit in plan['units'] if unit['expect']=='ABSENT'),","'files_to_create':len(plan['units']),",effect='files_to_create')
add('E06_values_member_dropped',"            'values':dict(READER_VALUES),'template_revision':TEMPLATE_REVISION,","            'template_revision':TEMPLATE_REVISION,")
add('E07_journal_of_the_data_volume',"            'journal':chain_effects(plan['journal_rows']),","            'journal':chain_effects(plan['data_rows']),",effect='journal')
add('E08_data_volume_of_the_journal',"'data_volume':chain_effects(plan['data_rows']),\n            'producer_unit'","'data_volume':chain_effects(plan['journal_rows']),\n            'producer_unit'",effect='data_volume')
add('E09_producer_path',"'producer_unit':{'path':UNIT_DIRECTORY+'/'+PRODUCER_SERVICE_NAME,'sha256':PRODUCER_SHA256,'bytes':PRODUCER_BYTES,'read_only':True},",
    "'producer_unit':{'path':UNIT_DIRECTORY,'sha256':PRODUCER_SHA256,'bytes':PRODUCER_BYTES,'read_only':True},",effect='producer_unit.path')
add('E10_producer_sha',"'sha256':PRODUCER_SHA256,'bytes':PRODUCER_BYTES,'read_only':True},","'sha256':None,'bytes':PRODUCER_BYTES,'read_only':True},",effect='producer_unit.sha256')
add('E11_producer_bytes',"'bytes':PRODUCER_BYTES,'read_only':True},","'bytes':0,'read_only':True},",effect='producer_unit.bytes')
add('E12_producer_written',"'read_only':True},\n","'read_only':False},\n",effect='producer_unit.read_only')
add('E13_leftovers_not_shown',"            'acknowledged_leftovers':[item['name'] for item in plan['acknowledged_leftovers']],","            'acknowledged_leftovers':[],",effect='acknowledged_leftovers')
add('E14_boot_not_the_signed_one',"            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],\n            'daemon_reload'","            'evidence_boot_id_sha256':'0'*64,\n            'daemon_reload'",
    effect='evidence_boot_id_sha256')
add('E15_reload_said_performed',"            'daemon_reload':{'performed_by_this_operation':False,'owner':DAEMON_RELOAD_OWNER},\n            'external_processes'",
    "            'daemon_reload':{'performed_by_this_operation':True,'owner':DAEMON_RELOAD_OWNER},\n            'external_processes'",effect='daemon_reload.performed_by_this_operation')
add('E16_effects_say_a_process',"            'external_processes':0,'pre_existing_objects_modified':False,'activation':False}","            'external_processes':1,'pre_existing_objects_modified':False,'activation':False}",
    effect='external_processes')
add('E17_effects_say_existing_objects_modified',"            'external_processes':0,'pre_existing_objects_modified':False,'activation':False}","            'external_processes':0,'pre_existing_objects_modified':True,'activation':False}",
    effect='pre_existing_objects_modified')
add('E18_effects_say_activation',"            'external_processes':0,'pre_existing_objects_modified':False,'activation':False}","            'external_processes':0,'pre_existing_objects_modified':False,'activation':True}",
    effect='activation')
EFFECTS['values']='E06_values_member_dropped';EFFECTS['producer_unit']='E09_producer_path';EFFECTS['daemon_reload']='E15_reload_said_performed'

# ---------------------------------------------------------------- the render and the placement rules
add('R01_forbidden_characters_unchecked',"         and not any(character.encode('ascii') in template for character in TEMPLATE_FORBIDDEN_CHARACTERS),'TEMPLATE_CHARACTERS')",
    "         ,'TEMPLATE_CHARACTERS')",refusal='TEMPLATE_CHARACTERS')
add('R02_template_bytes_any',"    need(type(template) is bytes and re.fullmatch(rb'[\\x20-\\x7e\\n]*',template) is not None\n         and not any(",
    "    need(type(template) is bytes\n         and not any(")
add('R03_placeholder_counts_unchecked',"==SERVICE_OCCURRENCES,'PLACEHOLDER_COUNTS')","==SERVICE_OCCURRENCES or True,'PLACEHOLDER_COUNTS')",refusal='PLACEHOLDER_COUNTS')
add('R04_extra_values_accepted',"set(values)==set(SERVICE_OCCURRENCES) and all(","set(values)>=set(SERVICE_OCCURRENCES) and all(",refusal='SUBSTITUTION_KEYS')
add('R05_values_of_any_type',"and all(type(value) is str for value in values.values()),'SUBSTITUTION_KEYS')",",'SUBSTITUTION_KEYS')")
add('R06_host_paths_not_clean',"need(text(values[name],HOST_PATH_GRAMMAR) and clean_path(values[name]),'PATH_INVALID')",
    "need(text(values[name],HOST_PATH_GRAMMAR),'PATH_INVALID')",refusal='PATH_INVALID')
add('R08_container_targets_unchecked',"need(text(values[name],CONTAINER_TARGET_GRAMMAR),'CONTAINER_TARGET_INVALID')","need(True,'CONTAINER_TARGET_INVALID')",refusal='CONTAINER_TARGET_INVALID')
add('R09_image_unchecked',"    need(text(values['IMAGE_ID'],IMAGE_ID),'IMAGE_ID_INVALID')\n","",refusal='IMAGE_ID_INVALID')
add('R11_placement_not_judged_at_render',"    findings=placement_findings(values)\n    need(not findings,","    findings=[]\n    need(not findings,")
add('R12_surviving_sign_allowed',"    need(b'@' not in rendered,'UNRESOLVED_PLACEHOLDER')","    need(True,'UNRESOLVED_PLACEHOLDER')",refusal='UNRESOLVED_PLACEHOLDER')
add('R13_any_size',"    need(len(rendered)<=MAX_UNIT_BYTES,'RENDER_TOO_LARGE')","    need(True,'RENDER_TOO_LARGE')",refusal='RENDER_TOO_LARGE')
add('R14_substitution_of_one_value_only',"    for name in sorted(values):rendered=rendered.replace(","    for name in sorted(values)[:1]:rendered=rendered.replace(")
add('R15_verbatim_with_a_sign',"is not None and b'@' not in template\n         and 0<len(template)","is not None\n         and 0<len(template)",refusal='VERBATIM_TEMPLATE_INVALID')
add('R16_verbatim_any_size',"         and 0<len(template)<=MAX_UNIT_BYTES,'VERBATIM_TEMPLATE_INVALID')","         and 0<len(template),'VERBATIM_TEMPLATE_INVALID')")
add('R17_template_hashes_unchecked',"    need(sha(READER_SERVICE_TEMPLATE)==READER_SERVICE_TEMPLATE_SHA256 and","    need(True or sha(READER_SERVICE_TEMPLATE)==READER_SERVICE_TEMPLATE_SHA256 and",
    refusal='TEMPLATE_HASH_MISMATCH')
add('R18_timer_rendered_like_the_service',"'READER_TIMER':verbatim(READER_TIMER_TEMPLATE),","'READER_TIMER':READER_TIMER_TEMPLATE+b'\\n',")
add('P01_config_overlap_unchecked',"    if any(overlap(config,other) for other in (data,capacity,journal,source)):found.append(","    if any(overlap(config,other) for other in ()):found.append(",
    refusal='CONFIG_DIRECTORY_OVERLAPS_A_BIND_SOURCE')
add('P02_config_against_the_source_unchecked',"for other in (data,capacity,journal,source)):found.append('CONFIG","for other in (data,capacity,journal)):found.append('CONFIG")
add('P03_journal_overlap_unchecked',"    if any(overlap(journal,other) for other in (data,capacity,source)):","    if any(overlap(journal,other) for other in ()):",refusal='HOST_JOURNAL_OVERLAPS_A_BIND_SOURCE')
add('P04_source_overlap_unchecked',"    if any(overlap(source,other) for other in (data,capacity)):","    if any(overlap(source,other) for other in ()):",refusal='SOURCE_ROOT_OVERLAPS_A_BIND_SOURCE')
add('P05_capacity_overlap_unchecked',"    if overlap(capacity,data):found.append(","    if False:found.append(",refusal='CAPACITY_ROOT_OVERLAPS_THE_DATA_VOLUME')
add('P06_producer_roots_unchecked',"    if any(overlap(journal,other) for other in producer_sources if other!=journal):","    if any(overlap(journal,other) for other in () if other!=journal):",
    refusal='HOST_JOURNAL_OVERLAPS_A_PRODUCER_PRIVATE_ROOT')
add('P07_overlap_one_way_only',"def overlap(first,second):return inside(first,second) or inside(second,first)","def overlap(first,second):return inside(first,second)")
add('P08_targets_may_be_equal',"    if len(set(targets))!=len(targets) or any(target in","    if any(target in",refusal='CONTAINER_TARGETS_NOT_DISTINCT')
add('P09_taken_targets_allowed',"or any(target in CONTAINER_TARGETS_TAKEN for target in targets):found.append(","or False:found.append(")

# ---------------------------------------------------------------- the producer unit
add('F01_producer_facts_any_shape',"len(images)==2 and len(set(images))==1 and body.count('--mount ')==len(binds),'PRODUCER_UNIT_NOT_AS_SIGNED')",
    "len(images)>=1,'PRODUCER_UNIT_NOT_AS_SIGNED')",refusal='PRODUCER_UNIT_NOT_AS_SIGNED')
add('F02_journal_root_argument_twice',"need(len(roots)==1 and body.count('--journal-root')==1 and","need(len(roots)>=1 and")
add('F03_readonly_journal_bind_of_the_producer',"    need(len(journal)==1 and journal[0][2]=='','PRODUCER_UNIT_NOT_AS_SIGNED')","    need(len(journal)==1,'PRODUCER_UNIT_NOT_AS_SIGNED')")
add('F04_producer_text_any_bytes',"    need(type(raw) is bytes and re.fullmatch(rb'[\\x20-\\x7e\\n]*',raw) is not None,'PRODUCER_UNIT_NOT_AS_SIGNED')","    need(type(raw) is bytes,'PRODUCER_UNIT_NOT_AS_SIGNED')")
add('F05_producer_absence_not_a_refusal',"    except FileNotFoundError:raise Refused('PRODUCER_UNIT_ABSENT') from None","    except FileNotFoundError:return None",refusal='PRODUCER_UNIT_ABSENT')
add('F06_producer_metadata_unchecked',"==(0,0,UNIT_MODE,1),\n         'PRODUCER_UNIT_NOT_AS_SIGNED')","==(0,0,UNIT_MODE,1) or True,\n         'PRODUCER_UNIT_NOT_AS_SIGNED')")
add('F07_producer_bytes_unchecked',"len(raw)==PRODUCER_BYTES and sha(raw)==PRODUCER_SHA256,'PRODUCER_UNIT_NOT_AS_SIGNED')","len(raw)==PRODUCER_BYTES,'PRODUCER_UNIT_NOT_AS_SIGNED')")
add('F08_producer_values_unchecked',"==(READER_VALUES['HOST_JOURNAL_ROOT'],READER_VALUES['CONTAINER_JOURNAL_ROOT'],READER_VALUES['IMAGE_ID']),'PRODUCER_VALUES_NOT_THE_READER_VALUES')",
    "!=None,'PRODUCER_VALUES_NOT_THE_READER_VALUES')",refusal='PRODUCER_VALUES_NOT_THE_READER_VALUES')
add('F09_producer_roots_not_judged',"    findings=placement_findings(READER_VALUES,facts['other_sources'])","    findings=placement_findings(READER_VALUES,[])")
add('F10_producer_read_without_its_identity',"    need((info.st_dev,info.st_ino)==(named.st_dev,named.st_ino) and len(raw)==PRODUCER_BYTES","    need(len(raw)==PRODUCER_BYTES")

# ---------------------------------------------------------------- validate_plan
add('V01_unit_chain_not_root_only',"    root_only_chain(plan['unit_rows'],UNIT_DIRECTORY,'UNIT_CHAIN_NOT_ROOT_CONTROLLED')","    validate_chain(plan['unit_rows'],UNIT_DIRECTORY,receives_entry=True)",
    refusal='UNIT_CHAIN_NOT_ROOT_CONTROLLED')
add('V02_unit_directory_may_be_setgid',"    rows=validate_chain(rows,path,open_root=None,receives_entry=True)\n","    rows=validate_chain(rows,path,open_root=None,receives_entry=False)\n")
add('V03_journal_chain_not_root_only',"    journal=root_only_chain(plan['journal_rows'],READER_VALUES['HOST_JOURNAL_ROOT'],'JOURNAL_CHAIN_NOT_ROOT_CONTROLLED')",
    "    journal=validate_chain(plan['journal_rows'],READER_VALUES['HOST_JOURNAL_ROOT'])",refusal='JOURNAL_CHAIN_NOT_ROOT_CONTROLLED')
add('V04_setgid_components_accepted',"    need(all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows),code)","    need(all(row['gid']==0 for row in rows),code)")
add('V05_journal_root_any_mode',"(journal[-1]['uid'],journal[-1]['gid'],journal[-1]['mode'])==(0,0,0o700),'JOURNAL_ROOT_NOT_PRIVATE')",
    "(journal[-1]['uid'],journal[-1]['gid'])==(0,0),'JOURNAL_ROOT_NOT_PRIVATE')",refusal='JOURNAL_ROOT_NOT_PRIVATE')
add('V06_data_volume_without_open_root',"    data=validate_chain(plan['data_rows'],READER_VALUES['HOST_DATA_ROOT'],open_root=READER_VALUES['HOST_DATA_ROOT'])",
    "    data=validate_chain(plan['data_rows'],READER_VALUES['HOST_DATA_ROOT'],open_root='/mnt')")
add('V07_data_volume_need_not_be_a_mount',"    need(mount_point_of(data)==READER_VALUES['HOST_DATA_ROOT'],'DATA_VOLUME_NOT_A_MOUNT_POINT')\n","",refusal='DATA_VOLUME_NOT_A_MOUNT_POINT')
add('V08_journal_may_share_the_data_device',"    need(journal[-1]['device']!=data[-1]['device'],'JOURNAL_ON_THE_DATA_VOLUME')\n","",refusal='JOURNAL_ON_THE_DATA_VOLUME')
add('V09_boot_unchecked',"    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')\n","",refusal='EVIDENCE_BOOT_UNBOUND')
add('V10_fewer_units_accepted',"    need(type(units) is list and len(units)==len(UNIT_ORDER),'UNITS_INVALID')","    need(type(units) is list and 0<len(units)<=len(UNIT_ORDER),'UNITS_INVALID')",
    refusal='UNITS_INVALID')
add('V11_more_units_accepted',"    need(type(units) is list and len(units)==len(UNIT_ORDER),'UNITS_INVALID')","    need(type(units) is list and len(units)>=len(UNIT_ORDER),'UNITS_INVALID')")
add('V12_unit_members_not_exact',"        need(type(unit) is dict and set(unit)==set(UNIT_KEYS),'UNITS_INVALID')","        need(type(unit) is dict and set(unit)>=set(UNIT_KEYS),'UNITS_INVALID')")
add('V13_unit_names_unchecked',"        need(unit['key']==key and unit['destination_name']==name,'UNIT_NAME_INVALID')","        need(unit['key']==key,'UNIT_NAME_INVALID')",refusal='UNIT_NAME_INVALID')
add('V14_unit_keys_unchecked',"        need(unit['key']==key and unit['destination_name']==name,'UNIT_NAME_INVALID')","        need(unit['destination_name']==name,'UNIT_NAME_INVALID')")
add('V15_expect_three_links',"and integer(expect['inode'],1) and integer(expect['links'],1,2)),'EXPECT_INVALID')","and integer(expect['inode'],1) and integer(expect['links'],1,3)),'EXPECT_INVALID')",
    refusal='EXPECT_INVALID')
add('V16_expect_any_object',"        need(expect=='ABSENT' or (type(expect) is dict and set(expect)==set(EXPECT_KEYS) and","        need(expect=='ABSENT' or (type(expect) is dict and")
add('V17_expect_inode_zero',"and integer(expect['inode'],1) and integer(expect['links'],1,2)","and integer(expect['inode']) and integer(expect['links'],1,2)")
add('V18_rendered_size_unchecked',"        need(unit['rendered_sha256']==sha(content) and unit['rendered_bytes']==len(content),'RENDERED_HASH_MISMATCH')",
    "        need(unit['rendered_sha256']==sha(content),'RENDERED_HASH_MISMATCH')",refusal='RENDERED_HASH_MISMATCH')
add('V19_rendered_hash_unchecked',"        need(unit['rendered_sha256']==sha(content) and unit['rendered_bytes']==len(content),'RENDERED_HASH_MISMATCH')",
    "        need(unit['rendered_bytes']==len(content),'RENDERED_HASH_MISMATCH')")
add('V20_nothing_to_create_accepted',"    need(any(unit['expect']=='ABSENT' for unit,_ in out),'NOTHING_TO_CREATE')","    need(True,'NOTHING_TO_CREATE')",refusal='NOTHING_TO_CREATE')
add('V21_leftovers_any_list',"    need(type(items) is list and len(items)<=MAX_LEFTOVERS,'LEFTOVERS_INVALID')","    need(type(items) is list,'LEFTOVERS_INVALID')",refusal='LEFTOVERS_INVALID')
add('V22_leftover_name_any',"set(item)==set(LEFTOVER_KEYS) and text(item['name'],LEFTOVER)\n","set(item)==set(LEFTOVER_KEYS)\n")
add('V23_leftover_twice',"    need(len({item['name'] for item in items})==len(items),'LEFTOVERS_INVALID')","    need(True,'LEFTOVERS_INVALID')")
add('V24_leftover_inode_zero',"             and integer(item['device']) and integer(item['inode'],1),'LEFTOVERS_INVALID')","             and integer(item['device']) and integer(item['inode']),'LEFTOVERS_INVALID')")
add('V25_leftovers_not_validated',"    units_of(plan);leftovers_of(plan)","    units_of(plan)")

# ---------------------------------------------------------------- the precheck
add('K01_executor_unchecked',"            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n","",refusal='EXECUTOR_IDENTITY')
add('K02_umask_private',"            host.umask(0o022)\n","            host.umask(0o077)\n")
add('K03_boot_unchecked',"            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')\n","",refusal='EVIDENCE_FROM_EARLIER_BOOT')
add('K04_producer_not_read',"            detail['producer']=producer_unit(host,directory,gate)\n","")
add('K05_journal_not_walked',"            journal=Pinned(host,walk_pinned(host,plan['journal_rows'],gate,detail['journal']),rows=plan['journal_rows']);held.append(journal)\n",
    "            journal=directory\n")
add('K06_data_volume_not_walked',"            held.append(Pinned(host,walk_pinned(host,plan['data_rows'],gate,detail['data_volume']),rows=plan['data_rows']))\n","")
add('K07_catalogue_not_looked_at',"            detail['catalog']=catalog_files(host,journal,gate)\n","")
add('K08_catalogue_absence_accepted',"        except FileNotFoundError:raise Refused('CATALOG_NOT_INITIALISED') from None","        except FileNotFoundError:continue",refusal='CATALOG_NOT_INITIALISED')
add('K09_catalogue_metadata_unchecked',"==(0,0,CATALOG_FILE_MODE,1),\n             'CATALOG_FILE_NOT_PRIVATE')","==(0,0,CATALOG_FILE_MODE,1) or True,\n             'CATALOG_FILE_NOT_PRIVATE')",
    refusal='CATALOG_FILE_NOT_PRIVATE')
add('K10_occupied_names_accepted',"    if 'OCCUPIED_NOT_REGULAR' in states:return 'UNIT_NAME_OCCUPIED'\n","",refusal='UNIT_NAME_OCCUPIED')
add('K11_foreign_units_accepted',"    if 'PRESENT_FOREIGN' in states:return 'UNIT_PRESENT_FOREIGN_CONTENT'\n","",refusal='UNIT_PRESENT_FOREIGN_CONTENT')
add('K12_expectations_unchecked',"    if states&{'EXPECTED_PRESENT_ABSENT','PRESENT_IDENTITY_MISMATCH'} or set(signed)-set(seen):return 'EXPECTATION_MISMATCH'\n","",refusal='EXPECTATION_MISMATCH')
add('K13_missing_acknowledged_leftover_accepted',"'PRESENT_IDENTITY_MISMATCH'} or set(signed)-set(seen):return","'PRESENT_IDENTITY_MISMATCH'}:return")
add('K14_all_present_is_a_partial',"        return 'ALL_UNITS_PRESENT' if settled else 'PRIOR_PARTIAL_REQUIRES_RECONCILIATION'","        return 'PRIOR_PARTIAL_REQUIRES_RECONCILIATION'",refusal='ALL_UNITS_PRESENT')
add('K15_all_present_with_two_links',"and all(row['links']==1 for row in rows) and not","and not")
add('K16_present_equal_units_ignored',"    if 'PRESENT_EQUAL_NOT_SIGNED' in states:\n","    if False:\n",refusal='PRIOR_PARTIAL_REQUIRES_RECONCILIATION')
add('K17_unacknowledged_leftovers_ignored',"    if scan['leftover_count']>MAX_FINDINGS or scan['leftovers_not_acknowledged']:\n","    if scan['leftover_count']>MAX_FINDINGS:\n")
add('K18_own_temporary_unacknowledged_is_a_partial',"        return 'TEMPORARY_NAME_OCCUPIED' if own&set(scan['leftovers_not_acknowledged']) else","        return",refusal='TEMPORARY_NAME_OCCUPIED')
add('K20_drop_ins_accepted',"    for code in ('DROP_IN_PRESENT','OWN_DEPENDENCY_DIRECTORY_PRESENT',","    for code in ('OWN_DEPENDENCY_DIRECTORY_PRESENT',",refusal='DROP_IN_PRESENT')
add('K21_own_dependency_accepted',"('DROP_IN_PRESENT','OWN_DEPENDENCY_DIRECTORY_PRESENT','ENABLEMENT_LINK_PRESENT',","('DROP_IN_PRESENT','ENABLEMENT_LINK_PRESENT',",
    refusal='OWN_DEPENDENCY_DIRECTORY_PRESENT')
add('K22_enablement_accepted',"'OWN_DEPENDENCY_DIRECTORY_PRESENT','ENABLEMENT_LINK_PRESENT','UNIT_SHADOWED_IN_OTHER_PATH'):","'OWN_DEPENDENCY_DIRECTORY_PRESENT','UNIT_SHADOWED_IN_OTHER_PATH'):",
    refusal='ENABLEMENT_LINK_PRESENT')
add('K23_shadow_accepted',"'ENABLEMENT_LINK_PRESENT','UNIT_SHADOWED_IN_OTHER_PATH'):\n","'ENABLEMENT_LINK_PRESENT'):\n",refusal='UNIT_SHADOWED_IN_OTHER_PATH')
add('K24_scan_unavailable_accepted',"    if scan['status']!='COMPLETE':return 'CONFLICT_SCAN_UNAVAILABLE'\n","",refusal='CONFLICT_SCAN_UNAVAILABLE')
add('K25_budget_unchecked',"                need(left>=WRITE_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')\n","",refusal='BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
add('K26_budget_skipped_when_refused',"            if code is None:\n                # The last refusal","            if True:\n                # The last refusal")
add('K27_shadow_in_the_install_directory_too',"                if directory!=UNIT_DIRECTORY and present(name,fd) is not None:add(","                if present(name,fd) is not None:add(")
add('K28_scan_limit_dropped',"                listed.append(name);need(len(listed)<=MAX_SCAN_ENTRIES,'SCAN_LIMIT')","                listed.append(name)",refusal='SCAN_LIMIT')
add('K29_dependency_file_ignored',"                    issues.append('DEPENDENCY_DIRECTORY_NOT_A_DIRECTORY');continue","                    continue",refusal='DEPENDENCY_DIRECTORY_NOT_A_DIRECTORY')
add('K30_leftovers_anywhere',"                if directory==UNIT_DIRECTORY and text(entry,LEFTOVER):","                if directory=='/run/systemd/system' and text(entry,LEFTOVER):")
add('K31_enablement_not_looked_for',"                        if present(name,child) is not None:add('ENABLEMENT_LINK_PRESENT',directory,name,label)","                        pass")
add('K32_findings_not_capped',"            'findings':findings[:MAX_FINDINGS],'findings_truncated'","            'findings':findings,'findings_truncated'")
add('K33_foreign_unit_digest_reported',"            if equal:row.update(sha256=sha(raw),size=len(raw))","            row.update(sha256=sha(raw),size=len(raw))")
add('K34_equal_bytes_without_owner',"        conforms=bool(equal and named.st_uid==0 and named.st_gid==0 and stat.S_IMODE(named.st_mode)==UNIT_MODE)","        conforms=bool(equal)")
add('K35_present_identity_unchecked',"        elif conforms and (named.st_dev,named.st_ino,named.st_nlink)==(expect['device'],expect['inode'],expect['links']):row['state']='OK_PRESENT'",
    "        elif conforms:row['state']='OK_PRESENT'")
add('K36_own_temporaries_of_present_units',"own={TEMPORARY%(go16,index) for index,(unit,_) in enumerate(units) if unit['expect']=='ABSENT'}","own={TEMPORARY%(go16,index) for index in range(1)}")
add('K37_acknowledgement_by_name_only',"            scan['leftovers_acknowledged']=sorted(name for name in seen if signed.get(name)==seen[name])\n            scan['leftovers_not_acknowledged']=sorted(name for name in seen if signed.get(name)!=seen[name])",
    "            scan['leftovers_acknowledged']=sorted(name for name in seen if name in signed)\n            scan['leftovers_not_acknowledged']=sorted(name for name in seen if name not in signed)")

# ---------------------------------------------------------------- the effects and the readback
CREATE="            row=create_file(index,unit['key'],path,content,UNIT_MODE,directory,host,gate,state,go16);ledger.append(row)\n"
add('W01_every_unit_with_the_same_temporary',CREATE,CREATE.replace("create_file(index,","create_file(0,"))
add('W02_units_written_private',CREATE,CREATE.replace("content,UNIT_MODE,directory","content,0o600,directory"))
add('W03_unit_written_without_its_last_byte',CREATE,CREATE.replace("path,content,UNIT_MODE","path,content[:-1],UNIT_MODE"))
add('W04_temporary_keyed_by_the_request',"    go16=bound['go_sha256'][:16]\n    def finish","    go16=bound['request_sha256'][:16]\n    def finish")
STOP="            if row['state']!='INSTALLED_DURABLE':stop=row['code'] or 'INSTALL_FAILED'\n"
add('W05_a_failed_unit_does_not_stop_the_next',STOP,"")
add('W06_a_linked_temporary_counts_as_installed',STOP,"            if row['state'] not in ('INSTALLED_DURABLE','LINKED_TEMPORARY_PRESENT'):stop=row['code'] or 'INSTALL_FAILED'\n")
add('W07_present_units_written_again',"            if unit['expect']!='ABSENT' or stop is not None:\n","            if stop is not None:\n")
add('W08_skipped_rows_say_present',"'state':'NOT_ATTEMPTED' if unit['expect']=='ABSENT' else 'PRESENT_VERIFIED_NOT_TOUCHED'});continue","'state':'PRESENT_VERIFIED_NOT_TOUCHED'});continue")
add('W09_installed_bytes_not_read_back',"                    stop=readback_file(row,content,UNIT_MODE,directory,host,gate);continue","                    continue")
add('W10_present_units_not_read_back',"                try:\n                    raw,info=read_regular(host,unit['destination_name'],directory.fd,gate,MAX_UNIT_BYTES)\n                    row['sha256_observed']=sha(raw);expect=unit['expect']",
    "                try:\n                    continue\n                    raw,info=read_regular(host,unit['destination_name'],directory.fd,gate,MAX_UNIT_BYTES)\n                    row['sha256_observed']=sha(raw);expect=unit['expect']")
add('W11_present_bytes_not_compared',"                    need(raw==content and (info.st_dev,info.st_ino,info.st_nlink)==","                    need((info.st_dev,info.st_ino,info.st_nlink)==",refusal='READBACK_HASH_MISMATCH')
add('W12_present_identity_not_compared',"and (info.st_dev,info.st_ino,info.st_nlink)==(expect['device'],expect['inode'],expect['links'])\n","\n")
add('W13_present_metadata_not_compared',"                         and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(0,0,UNIT_MODE),'READBACK_HASH_MISMATCH')","                         ,'READBACK_HASH_MISMATCH')")
add('W14_directory_not_verified_at_the_end',"            try:directory.verify(gate)\n            except Exception as error:stop=code_of(error,'READBACK_UNAVAILABLE')","            pass",refusal='READBACK_UNAVAILABLE')
add('W15_complete_whatever_the_readback_says',"        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)\n","        if True:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)\n")
CLEAN="        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n"
add('W16_a_run_that_changed_the_host_is_a_refusal',CLEAN,"        if True:return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n")
add('W17_a_run_that_changed_nothing_is_a_partial',CLEAN,"")
add('W18_objects_left_not_counted',"ledger=ledger,objects_left_by_this_run=objects_left([],ledger),","ledger=ledger,objects_left_by_this_run=0,")
add('W19_receipt_says_existing_objects_modified',"            pre_existing_objects_modified=False,**extra)))","            pre_existing_objects_modified=True,**extra)))")
add('W20_readback_complete_when_it_stopped',"extra={'phase_reached':'CREATION','readback':'COMPLETE' if stop is None else None}","extra={'phase_reached':'CREATION','readback':'COMPLETE'}")
add('W21_effects_phase_reported_as_the_precheck',"extra={'phase_reached':'CREATION',","extra={'phase_reached':'PRECHECK',")
add('W22_partial_with_the_complete_status',"        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)\n    finally:","        return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,stop,extra)\n    finally:")
add('W23_success_criterion_is_the_partial',"def success_of(plan):return COMPLETE_OUTCOME\n","def success_of(plan):return PARTIAL_OUTCOME\n")
add('W24_held_directories_left_open',"        for handle in held:\n            try:handle.close()","        for handle in held[1:]:\n            try:handle.close()")
add('W25_receipt_without_the_catalogue',"producer=detail['producer'],catalog=detail['catalog'],precheck","producer=detail['producer'],catalog=None,precheck")
add('W26_reductions_lose_the_first_step',"REDUCTIONS=[('SCAN_DIRECTORIES_REDUCED_TO_STATUS',_reduce_scan),('PRECHECK_REDUCED_TO_STATES',_reduce_precheck)]",
    "REDUCTIONS=[('PRECHECK_REDUCED_TO_STATES',_reduce_precheck)]")
add('W27_reload_owner_not_in_the_receipt',"external_processes=0,daemon_reload_owner=DAEMON_RELOAD_OWNER,","external_processes=0,daemon_reload_owner=None,")

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

# Codes the operation part returns or records rather than raises (the precedence table and the scan), all answered above.
RETURNED=('UNIT_NAME_OCCUPIED','UNIT_PRESENT_FOREIGN_CONTENT','EXPECTATION_MISMATCH','ALL_UNITS_PRESENT','PRIOR_PARTIAL_REQUIRES_RECONCILIATION',
          'TEMPORARY_NAME_OCCUPIED','DROP_IN_PRESENT','OWN_DEPENDENCY_DIRECTORY_PRESENT','ENABLEMENT_LINK_PRESENT','UNIT_SHADOWED_IN_OTHER_PATH',
          'CONFLICT_SCAN_UNAVAILABLE','DEPENDENCY_DIRECTORY_NOT_A_DIRECTORY','CONFIG_DIRECTORY_OVERLAPS_A_BIND_SOURCE','HOST_JOURNAL_OVERLAPS_A_BIND_SOURCE',
          'SOURCE_ROOT_OVERLAPS_A_BIND_SOURCE','CAPACITY_ROOT_OVERLAPS_THE_DATA_VOLUME','HOST_JOURNAL_OVERLAPS_A_PRODUCER_PRIVATE_ROOT','CONTAINER_TARGETS_NOT_DISTINCT')
EXCLUDED=('PRECHECK_OS_ERROR','PRECHECK_FAILED','INSTALL_FAILED','FILE_UNREADABLE','PLACEMENT_INVALID','PATH_CHANGED')


# ---------------------------------------------------------------- the two tables against the source itself
def _load(path):
    raw=Path(path).read_bytes();name='_hostops02_reader_units_mutation_'+hashlib.sha256(raw).hexdigest()[:12]
    module=type(sys)(name);module.__dict__['__file__']='<assembled reader_units.py>';sys.modules[name]=module
    exec(compile(raw,module.__dict__['__file__'],'exec'),module.__dict__);return module

def codes_of(text):
    """Every constant code the operation part can raise: the code argument of each need(), Refused(), code_of() and
    root_only_chain() call. The codes it returns or records are the table RETURNED, checked against the source text."""
    found=set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in ('need','Refused','code_of','root_only_chain') and node.args:
            for argument in node.args[-1:]:
                for item in ast.walk(argument):
                    if isinstance(item,ast.Constant) and type(item.value) is str and re.fullmatch('[A-Z][A-Z0-9_]{2,79}',item.value):found.add(item.value)
    return found

def coverage(here):
    """Errors when a member of effects_of() or a refusal of the operation part has no mutant named for it. Members are
    the top-level keys, and the keys of 'values', 'producer_unit' and 'daemon_reload'."""
    here=Path(here);errors=[];names={row[0] for row in M};module=_load(here/'build'/'reader_units.py')
    rows=lambda path:[{'path':p,'device':1,'inode':2+i,'uid':0,'gid':0,'mode':0o755} for i,p in enumerate(module.prefixes(path))]
    plan={'unit_rows':rows('/etc/systemd/system'),'journal_rows':rows('/var/lib/c3po-bar/journal'),'data_rows':rows('/mnt/day-d-data'),
          'units':[{'key':key,'destination_name':name,'expect':'ABSENT'} for key,name in module.UNIT_ORDER],'acknowledged_leftovers':[],
          'evidence_boot_id_sha256':'a'*64}
    effects=module.effects_of(plan);wanted=set()
    for key,value in effects.items():
        wanted.add(key)
        if key in ('values','producer_unit','daemon_reload'):wanted|={key+'.'+inner for inner in value}
    for member in sorted(wanted):
        if EFFECTS.get(member) not in names:errors.append('effects member without a mutant: '+member)
    for member in EFFECTS:
        if member not in wanted:errors.append('mutant table names an effects member that does not exist: '+member)
    source=(here/'op.py').read_text()
    codes=(codes_of(source)|{code for code in RETURNED if "'"+code+"'" in source})-set(EXCLUDED)
    for code in RETURNED:
        if "'"+code+"'" not in source:errors.append('returned code not in the source: '+code)
    for code in sorted(codes):
        if REFUSALS.get(code) not in names:errors.append('refusal without a mutant: '+code)
    for code in REFUSALS:
        if code not in codes:errors.append('mutant table names a refusal that does not exist: '+code)
    return errors
