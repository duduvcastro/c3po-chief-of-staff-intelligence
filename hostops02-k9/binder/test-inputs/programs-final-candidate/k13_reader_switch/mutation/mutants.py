"""The mutants of K13's own part. Each row: (name, target, exact anchor, replacement); target 'op' is the built source
build/k13_reader_switch.py, in which the anchor must occur exactly once (mutate.py check). The rule of the family:
one mutant per member of effects_of(), one per refusal of validate_plan and of the precheck; here also one per word of
each command row, the constants of the epoch, the order of the switches, and what the run does with each way a switch
ends. EFFECTS and REFUSALS name, for each member and each code, the mutant that answers for it; coverage() compares
both tables with the source itself (the members effects_of() returns, the codes the operation part can raise), so a
new member or a new refusal without a mutant is an error of `mutate.py check`. Modelled on K4-E0's list."""
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

# ---------------------------------------------------------------- constants of the epoch, the units and the paths
add('C01_another_epoch',"READER_EPOCH='R2D2-V2-SHADOW-2026-10-05'","READER_EPOCH='R2D2-V2-SHADOW-2026-09-28'",effect='epoch')
add('C02_saturday_is_a_session',"'2026-10-08','2026-10-09')\n# New York","'2026-10-08','2026-10-09','2026-10-10')\n# New York")
add('C03_tuesday_is_not_a_session',"SESSION_DAYS=('2026-10-05','2026-10-06','2026-10-07',","SESSION_DAYS=('2026-10-05','2026-10-07',")
add('C04_window_opens_a_second_early',"LAUNCH_FROM_SECONDS=7*3600+30*60\n","LAUNCH_FROM_SECONDS=7*3600+30*60-1\n")
add('C05_window_opens_a_second_late',"LAUNCH_FROM_SECONDS=7*3600+30*60\n","LAUNCH_FROM_SECONDS=7*3600+30*60+1\n")
add('C06_window_closes_a_second_late',"LAUNCH_UNTIL_SECONDS=20*3600\n","LAUNCH_UNTIL_SECONDS=20*3600+1\n")
add('C07_window_closes_a_second_early',"LAUNCH_UNTIL_SECONDS=20*3600\n","LAUNCH_UNTIL_SECONDS=20*3600-1\n")
add('C08_late_a_second_early',"LATE_FROM_SECONDS=13*3600+28*60+30\n","LATE_FROM_SECONDS=13*3600+28*60+29\n")
add('C09_late_a_second_late',"LATE_FROM_SECONDS=13*3600+28*60+30\n","LATE_FROM_SECONDS=13*3600+28*60+31\n")
add('C10_late_flag_inverted',"return {'session':day,'late':seconds>=LATE_FROM_SECONDS}","return {'session':day,'late':seconds<LATE_FROM_SECONDS}")
add('C11_unit_directory',"UNIT_DIRECTORY='/etc/systemd/system'","UNIT_DIRECTORY='/usr/lib/systemd/system'")
add('C12_service_unit',"SERVICE_UNIT='c3po-reader.service'","SERVICE_UNIT='c3po-massive.service'")
add('C13_timer_unit',"TIMER_UNIT='c3po-reader.timer'","TIMER_UNIT='c3po-massive.timer'")
add('C14_alert_unit',"ALERT_UNIT='c3po-reader-alert.service'","ALERT_UNIT='c3po-reader.timer'")
add('C15_producer_unit',"PRODUCER_UNIT='c3po-massive.service'","PRODUCER_UNIT='c3po-reader.service'")
add('C16_config_directory',"CONFIG_DIRECTORY='/etc/c3po-reader'","CONFIG_DIRECTORY='/etc/c3po-bar'")
add('C17_launcher_name',"LAUNCHER_NAME='reader_launcher.py'","LAUNCHER_NAME='launcher.py'")
add('C18_pins_name',"PINS_NAME='pins.env'","PINS_NAME='secret.env'")
add('C19_secret_name',"SECRET_NAME='secret.env'","SECRET_NAME='pins.env'")
add('C20_activation_name',"ACTIVATION_NAME='activation.env'","ACTIVATION_NAME='activation.env.new'")
add('C21_docker_cli_name',"DOCKER_CLI_NAME='docker-cli'","DOCKER_CLI_NAME='launcher'")
add('C22_activation_bytes_one_flag_false',"ACTIVATION_BYTES=b'C3PO_R2D2_V2_SHADOW_ENABLED=true\\n","ACTIVATION_BYTES=b'C3PO_R2D2_V2_SHADOW_ENABLED=false\\n")
add('C23_activation_bytes_without_final_newline',"C3PO_R2D2_V2_MASSIVE_BARS_ENABLED=true\\n'\nACTIVATION_SHA256","C3PO_R2D2_V2_MASSIVE_BARS_ENABLED=true'\nACTIVATION_SHA256")
add('C24_activation_sha_signed_is_another',"ACTIVATION_SHA256='2053f3f6f528ad7dc56d500666ac2cf48f79c3aadd3c98eb35b53ee92eff611b'",
    "ACTIVATION_SHA256='2053f3f6f528ad7dc56d500666ac2cf48f79c3aadd3c98eb35b53ee92eff611c'",effect='activation_env.sha256')
add('C25_journal_host_root',"JOURNAL_HOST_ROOT='/var/lib/c3po-bar/journal'","JOURNAL_HOST_ROOT='/var/lib/c3po-bar/journal2'")
add('C26_journal_container_root',"JOURNAL_CONTAINER_ROOT='/c3po-bar-journal'","JOURNAL_CONTAINER_ROOT='/c3po-journal'",effect='journal.container_root')
add('C27_catalog_schema',"CATALOG_SCHEMA_NAME='MASSIVE_SESSION_ROOT_V1'","CATALOG_SCHEMA_NAME='MASSIVE_SESSION_ROOT_V2'")
add('C28_epoch_file_name',"EPOCH_FILE_NAME='epoch.json'","EPOCH_FILE_NAME='session.json'")
add('C29_catalog_lock_name',"CATALOG_LOCK_NAME='maintenance.lock'","CATALOG_LOCK_NAME='epoch.json'")
add('C30_data_volume',"DATA_VOLUME='/mnt/day-d-data'","DATA_VOLUME='/mnt'")
add('C31_data_target',"DATA_TARGET='/app/day-d-data'","DATA_TARGET='/app/data'")
add('C32_capacity_root',"CAPACITY_ROOT='/var/lib/c3po-capacity'","CAPACITY_ROOT='/var/lib/c3po-capacity/config'")
add('C33_capacity_target',"CAPACITY_TARGET='/c3po-capacity'","CAPACITY_TARGET='/app/c3po-capacity'")
add('C34_launcher_target',"LAUNCHER_TARGET='/c3po-reader'","LAUNCHER_TARGET='/c3po-launcher'")
add('C35_reader_container',"READER_CONTAINER='c3po-reader'","READER_CONTAINER='c3po-massive'")
add('C36_producer_floor_one_byte_more',"PRODUCER_FLOOR_BYTES=53687091200","PRODUCER_FLOOR_BYTES=53687091201")
add('C37_producer_floor_one_byte_less',"PRODUCER_FLOOR_BYTES=53687091200","PRODUCER_FLOOR_BYTES=53687091199")
add('C38_unit_file_limit',"MAX_UNIT_FILE_BYTES=65536","MAX_UNIT_FILE_BYTES=65537")
add('C39_pins_limit',"MAX_PINS_BYTES=4096","MAX_PINS_BYTES=8192")
add('C40_command_words_limit',"MAX_COMMAND_WORDS=256","MAX_COMMAND_WORDS=257")
add('C41_pins_names_lose_the_launcher_pin',",'C3PO_R2D2_V2_SHADOW_POLL_SECONDS','C3PO_READER_LAUNCHER_SHA256')",",'C3PO_R2D2_V2_SHADOW_POLL_SECONDS')")
add('C42_pins_names_out_of_order',"PINS_NAMES=('C3PO_BUILD_SHA','C3PO_R2D2_V2_SHADOW_RELEASE_FILE',","PINS_NAMES=('C3PO_R2D2_V2_SHADOW_RELEASE_FILE','C3PO_BUILD_SHA',")
add('C43_pins_value_with_spaces',"PINS_VALUE='[A-Za-z0-9._=/:-]{1,200}'","PINS_VALUE='[A-Za-z0-9._=/: -]{1,200}'")
add('C44_pins_value_may_be_empty',"PINS_VALUE='[A-Za-z0-9._=/:-]{1,200}'","PINS_VALUE='[A-Za-z0-9._=/:-]{0,200}'")
add('C45_worker_marker',"READER_MARKERS=('app.r2d2_v2_shadow_worker','reader_launcher.py')","READER_MARKERS=('app.r2d2_v2_shadow_workers','reader_launcher.py')")
add('C46_launcher_marker',"READER_MARKERS=('app.r2d2_v2_shadow_worker','reader_launcher.py')","READER_MARKERS=('app.r2d2_v2_shadow_worker',)")
add('C47_capacity_day_marker',"NOT_A_READER_MARKER='--prepare-capacity-day'","NOT_A_READER_MARKER='--capacity-day'")
add('C48_paused_not_scanned',"SCAN_STATES=('running','paused','restarting')","SCAN_STATES=('running','restarting')")
add('C49_reloading_is_not_active',"ACTIVE_STATES=('active','activating','reloading')","ACTIVE_STATES=('active','activating')")
add('C50_failed_is_not_stopped',"STOPPED_STATES=('inactive','failed')","STOPPED_STATES=('inactive',)")
add('C51_allowance_one_second_less',"SWITCH_FILE_ALLOWANCE_SECONDS=3\n","SWITCH_FILE_ALLOWANCE_SECONDS=2\n")
add('C52_allowance_one_second_more',"SWITCH_FILE_ALLOWANCE_SECONDS=3\n","SWITCH_FILE_ALLOWANCE_SECONDS=4\n")
add('C53_date_class_first_session',"DATE_CLASS='WRITE_SESSIONS'","DATE_CLASS='WRITE_FIRST_SESSION'")
add('C54_date_class_epoch',"DATE_CLASS='WRITE_SESSIONS'","DATE_CLASS='WRITE_EPOCH'")
add('C55_no_evidence_operation',"EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,)","EVIDENCE_OPERATIONS=()")
add('C56_gate_span',"MAX_GATE_SPAN_SECONDS=900","MAX_GATE_SPAN_SECONDS=899")
add('C57_outcome_of_restart_is_activate',"MODE_OUTCOMES={'ACTIVATE':COMPLETE_OUTCOME,'RESTART':RESTART_OUTCOME,","MODE_OUTCOMES={'ACTIVATE':COMPLETE_OUTCOME,'RESTART':COMPLETE_OUTCOME,",
    effect='success_outcome')
add('C58_mode_list_loses_restart',"READER_MODES=('ACTIVATE','RESTART','DEACTIVATE')","READER_MODES=('ACTIVATE','DEACTIVATE')",refusal='MODE_INVALID')
add('C59_unit_property_dropped',"UNIT_PROPERTIES=('Id','LoadState','ActiveState','SubState','UnitFileState','FragmentPath','DropInPaths','NeedDaemonReload','Result')",
    "UNIT_PROPERTIES=('Id','LoadState','ActiveState','SubState','UnitFileState','FragmentPath','DropInPaths','Result')")

# ---------------------------------------------------------------- the command table: one mutant per word
ROW_SHOW="'service_state':command_row('systemctl',['show',SERVICE_UNIT],None,'QUICK','READ',tail=[part for key in UNIT_PROPERTIES for part in ('-p',key)]),"
add('R01_image_row_with_the_container_template',"'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT]","'image':command_row('docker',['image','inspect','--format',CONTAINER_FORMAT]")
add('R02_container_row_with_the_command_template',"'container':command_row('docker',['container','inspect','--format',CONTAINER_FORMAT]","'container':command_row('docker',['container','inspect','--format',CONTAINER_COMMAND_FORMAT]")
add('R03_listing_without_all',"'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT]","'container_list':command_row('docker',['ps','--no-trunc','--format',PS_FORMAT]")
add('R04_command_template_without_args',"CONTAINER_COMMAND_FORMAT='{\"id\":{{json .Id}},\"path\":{{json .Path}},\"args\":{{json .Args}},","CONTAINER_COMMAND_FORMAT='{\"id\":{{json .Id}},\"path\":{{json .Path}},\"args\":null,")
add('R05_command_template_without_path',"\"path\":{{json .Path}},\"args\"","\"path\":\"python\",\"args\"")
add('R06_command_template_without_exec_ids',"\"exec_ids\":{{json .ExecIDs}}}'","\"exec_ids\":null}'")
add('R07_security_template_prints_the_driver',"SECURITY_OPTIONS_FORMAT='{{json .SecurityOptions}}'","SECURITY_OPTIONS_FORMAT='{{json .DriverStatus}}'")
add('R08_service_show_of_the_timer',ROW_SHOW,ROW_SHOW.replace("['show',SERVICE_UNIT]","['show',TIMER_UNIT]"))
add('R09_service_show_without_properties',ROW_SHOW,ROW_SHOW.replace("tail=[part for key in UNIT_PROPERTIES for part in ('-p',key)]","tail=['-p','Id']"))
add('R10_timer_show_of_the_service',"'timer_state':command_row('systemctl',['show',TIMER_UNIT]","'timer_state':command_row('systemctl',['show',SERVICE_UNIT]")
add('R11_is_enabled_of_the_service',"'timer_enabled':command_row('systemctl',['is-enabled',TIMER_UNIT]","'timer_enabled':command_row('systemctl',['is-enabled',SERVICE_UNIT]")
add('R12_enable_without_now',"'enable_now_timer':command_row('systemctl',['enable','--now',TIMER_UNIT]","'enable_now_timer':command_row('systemctl',['enable',TIMER_UNIT]",effect='switches')
add('R13_enable_of_the_service',"'enable_now_timer':command_row('systemctl',['enable','--now',TIMER_UNIT]","'enable_now_timer':command_row('systemctl',['enable','--now',SERVICE_UNIT]")
add('R14_enable_is_reenable',"'enable_now_timer':command_row('systemctl',['enable','--now',TIMER_UNIT]","'enable_now_timer':command_row('systemctl',['reenable','--now',TIMER_UNIT]")
add('R15_enable_class_quick',"TIMER_UNIT],None,'SWITCH','EFFECT'),\n          'start_service'","TIMER_UNIT],None,'QUICK','EFFECT'),\n          'start_service'")
add('R16_start_blocking',"'start_service':command_row('systemctl',['start','--no-block',SERVICE_UNIT]","'start_service':command_row('systemctl',['start',SERVICE_UNIT]")
add('R17_start_of_the_timer',"'start_service':command_row('systemctl',['start','--no-block',SERVICE_UNIT]","'start_service':command_row('systemctl',['start','--no-block',TIMER_UNIT]")
add('R18_start_is_restart',"'start_service':command_row('systemctl',['start','--no-block',SERVICE_UNIT]","'start_service':command_row('systemctl',['restart','--no-block',SERVICE_UNIT]")
add('R19_start_class_switch',"SERVICE_UNIT],None,'QUICK','EFFECT'),\n          'reset_failed_service'","SERVICE_UNIT],None,'SWITCH','EFFECT'),\n          'reset_failed_service'")
add('R20_reset_failed_of_the_timer',"'reset_failed_service':command_row('systemctl',['reset-failed',SERVICE_UNIT]","'reset_failed_service':command_row('systemctl',['reset-failed',TIMER_UNIT]")
add('R21_reset_failed_is_a_restart',"'reset_failed_service':command_row('systemctl',['reset-failed',SERVICE_UNIT]","'reset_failed_service':command_row('systemctl',['try-restart',SERVICE_UNIT]")
add('R22_disable_without_now',"'disable_now_timer':command_row('systemctl',['disable','--now',TIMER_UNIT]","'disable_now_timer':command_row('systemctl',['disable',TIMER_UNIT]")
add('R23_disable_of_the_service',"'disable_now_timer':command_row('systemctl',['disable','--now',TIMER_UNIT]","'disable_now_timer':command_row('systemctl',['disable','--now',SERVICE_UNIT]")
add('R24_disable_is_mask',"'disable_now_timer':command_row('systemctl',['disable','--now',TIMER_UNIT]","'disable_now_timer':command_row('systemctl',['mask','--now',TIMER_UNIT]")
add('R25_stop_blocking',"'stop_service':command_row('systemctl',['stop','--no-block',SERVICE_UNIT]","'stop_service':command_row('systemctl',['stop',SERVICE_UNIT]")
add('R26_stop_of_the_timer',"'stop_service':command_row('systemctl',['stop','--no-block',SERVICE_UNIT]","'stop_service':command_row('systemctl',['stop','--no-block',TIMER_UNIT]")
add('R27_stop_is_kill',"'stop_service':command_row('systemctl',['stop','--no-block',SERVICE_UNIT]","'stop_service':command_row('systemctl',['kill','--no-block',SERVICE_UNIT]")
add('R28_disable_class_quick',"'disable_now_timer':command_row('systemctl',['disable','--now',TIMER_UNIT],None,'SWITCH','EFFECT'),","'disable_now_timer':command_row('systemctl',['disable','--now',TIMER_UNIT],None,'QUICK','EFFECT'),")
add('R29_activate_switches_reversed',"MODE_EFFECTS={'ACTIVATE':('enable_now_timer','start_service'),","MODE_EFFECTS={'ACTIVATE':('start_service','enable_now_timer'),")
add('R30_activate_without_the_service_start',"MODE_EFFECTS={'ACTIVATE':('enable_now_timer','start_service'),","MODE_EFFECTS={'ACTIVATE':('enable_now_timer',),")
add('R31_restart_without_the_reset',"'RESTART':('reset_failed_service','start_service'),","'RESTART':('start_service',),")
add('R32_deactivate_without_the_stop',"'DEACTIVATE':('disable_now_timer','stop_service')}","'DEACTIVATE':('disable_now_timer',)}")
add('R33_deactivate_stop_first',"'DEACTIVATE':('disable_now_timer','stop_service')}","'DEACTIVATE':('stop_service','disable_now_timer')}")
add('R34_reloading_rows_without_disable',"RELOADING_ROWS=('enable_now_timer','disable_now_timer')","RELOADING_ROWS=('enable_now_timer',)")
add('R35_reloading_rows_with_the_start',"RELOADING_ROWS=('enable_now_timer','disable_now_timer')","RELOADING_ROWS=('enable_now_timer','disable_now_timer','start_service')")

# ---------------------------------------------------------------- validate_plan: one mutant per refusal
add('P01_mode_not_checked',"    need(plan['mode'] in READER_MODES,'MODE_INVALID')\n","")
add('P02_boot_not_checked',"    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')\n","",refusal='EVIDENCE_BOOT_UNBOUND')
add('P03_unit_chain_not_validated',"    validate_chain(plan['unit_rows'],UNIT_DIRECTORY)\n","")
add('P04_unit_chain_group_accepted',"    need(all(root_controlled(row) for row in plan['unit_rows']),'UNIT_CHAIN_NOT_ROOT_CONTROLLED')\n","",refusal='UNIT_CHAIN_NOT_ROOT_CONTROLLED')
add('P05_root_controlled_accepts_setgid',"    return row['gid']==0 and not row['mode']&stat.S_ISGID","    return row['gid']==0")
add('P06_root_controlled_accepts_any_group',"    return row['gid']==0 and not row['mode']&stat.S_ISGID","    return not row['mode']&stat.S_ISGID")
add('P07_files_keys_not_exact',"    files=exact(plan['files'],FILE_KEYS,'FILE_PINS_INVALID')","    files=plan['files']",refusal='FILE_PINS_INVALID')
add('P11_file_pins_not_checked',"    need(all(hexpin(files[key]) for key in FILE_KEYS),'FILE_PINS_INVALID')\n","")
add('P12_config_chain_not_validated',"    validate_chain(plan['config_rows'],CONFIG_DIRECTORY,receives_entry=True)\n","")
add('P13_config_may_be_setgid',"    validate_chain(plan['config_rows'],CONFIG_DIRECTORY,receives_entry=True)\n","    validate_chain(plan['config_rows'],CONFIG_DIRECTORY)\n")
add('P14_config_not_private',"and private_directory_row(plan['config_rows'][-1]),'CONFIG_DIRECTORY_NOT_PRIVATE')","and True,'CONFIG_DIRECTORY_NOT_PRIVATE')",refusal='CONFIG_DIRECTORY_NOT_PRIVATE')
add('P15_config_chain_group',"    need(all(root_controlled(row) for row in plan['config_rows']) and","    need(True and")
add('P16_private_row_any_mode',"def private_directory_row(row):return (row['uid'],row['gid'],row['mode'])==(0,0,0o700)","def private_directory_row(row):return (row['uid'],row['gid'])==(0,0)")
add('P17_launcher_chain_not_validated',"    validate_chain(plan['launcher_rows'],LAUNCHER_DIRECTORY)\n","")
add('P18_launcher_not_under_config',"    need(plan['launcher_rows'][:-1]==plan['config_rows'] and private_directory_row(plan['launcher_rows'][-1]),'LAUNCHER_DIRECTORY_NOT_PRIVATE')",
    "    need(private_directory_row(plan['launcher_rows'][-1]),'LAUNCHER_DIRECTORY_NOT_PRIVATE')",refusal='LAUNCHER_DIRECTORY_NOT_PRIVATE')
add('P19_launcher_not_private',"    need(plan['launcher_rows'][:-1]==plan['config_rows'] and private_directory_row(plan['launcher_rows'][-1]),'LAUNCHER_DIRECTORY_NOT_PRIVATE')",
    "    need(plan['launcher_rows'][:-1]==plan['config_rows'],'LAUNCHER_DIRECTORY_NOT_PRIVATE')")
add('P20_journal_chain_not_validated',"    validate_chain(plan['journal_rows'],JOURNAL_HOST_ROOT)\n","")
add('P21_journal_not_private',"and private_directory_row(plan['journal_rows'][-1]),'JOURNAL_ROOT_NOT_PRIVATE')","and True,'JOURNAL_ROOT_NOT_PRIVATE')",refusal='JOURNAL_ROOT_NOT_PRIVATE')
add('P22_journal_chain_group',"    need(all(root_controlled(row) for row in plan['journal_rows']) and","    need(True and")
add('P23_release_outside_the_volume',"         and inside(rows[-1]['path'],DATA_VOLUME) and rows[-1]['path']!=DATA_VOLUME,'RELEASE_NOT_IN_THE_DATA_VOLUME')",
    "         and rows[-1]['path']!=DATA_VOLUME,'RELEASE_NOT_IN_THE_DATA_VOLUME')",refusal='RELEASE_NOT_IN_THE_DATA_VOLUME')
add('P24_release_is_the_volume',"         and inside(rows[-1]['path'],DATA_VOLUME) and rows[-1]['path']!=DATA_VOLUME,'RELEASE_NOT_IN_THE_DATA_VOLUME')",
    "         and inside(rows[-1]['path'],DATA_VOLUME),'RELEASE_NOT_IN_THE_DATA_VOLUME')")
add('P25_release_chain_without_open_root',"    validate_chain(rows,rows[-1]['path'],open_root=DATA_VOLUME)\n","    validate_chain(rows,rows[-1]['path'],open_root=None)\n")
add('P26_release_chain_not_validated',"    validate_chain(rows,rows[-1]['path'],open_root=DATA_VOLUME)\n","")
add('P27_data_volume_not_a_mount_point',"    need(mount_point_of(rows[:len(prefixes(DATA_VOLUME))])==DATA_VOLUME,'DATA_VOLUME_NOT_A_MOUNT_POINT')\n","",refusal='DATA_VOLUME_NOT_A_MOUNT_POINT')
add('P28_journal_on_the_data_volume',"    need(plan['journal_rows'][-1]['device']!=data_volume_row(rows)['device'],'JOURNAL_ON_THE_DATA_VOLUME')\n","",refusal='JOURNAL_ON_THE_DATA_VOLUME')
add('P29_data_volume_row_of_the_root',"    return [row for row in rows if row['path']==DATA_VOLUME][0]","    return rows[0]")
add('P30_release_keys_not_exact',"    release=exact(plan['release'],('name','sha256'),'RELEASE_PLAN_INVALID')","    release=plan['release']",refusal='RELEASE_PLAN_INVALID')
add('P31_release_name_not_checked',"    need(text(release['name'],FILE_NAME) and hexpin(release['sha256']),'RELEASE_PLAN_INVALID')","    need(hexpin(release['sha256']),'RELEASE_PLAN_INVALID')")
add('P32_release_hash_not_checked',"    need(text(release['name'],FILE_NAME) and hexpin(release['sha256']),'RELEASE_PLAN_INVALID')","    need(text(release['name'],FILE_NAME),'RELEASE_PLAN_INVALID')")
add('P33_image_not_checked',"    need(text(plan['image_id'],IMAGE_ID),'IMAGE_ID_INVALID')\n","",refusal='IMAGE_ID_INVALID')
add('P36_release_rows_not_a_list',"    need(type(rows) is list and rows and type(rows[-1]) is dict and type(rows[-1].get('path')) is str and clean_path(rows[-1]['path'])\n",
    "    need(rows and type(rows[-1]) is dict and type(rows[-1].get('path')) is str\n")

# ---------------------------------------------------------------- effects_of: one mutant per member
add('E01_operation',"    out={'operation':OPERATION,'epoch':READER_EPOCH,","    out={'operation':PHASE,'epoch':READER_EPOCH,",effect='operation')
add('E02_mode',"'mode':mode,'success_outcome':MODE_OUTCOMES[mode],","'mode':'ACTIVATE','success_outcome':MODE_OUTCOMES[mode],",effect='mode')
add('E03_success_outcome_in_effects',"'mode':mode,'success_outcome':MODE_OUTCOMES[mode],","'mode':mode,'success_outcome':COMPLETE_OUTCOME,")
add('E04_switches',"         'switches':[COMMANDS[name]['argv'] for name in MODE_EFFECTS[mode]],","         'switches':[COMMANDS[name]['argv'] for name in MODE_EFFECTS['ACTIVATE']],")
add('E05_activation_path',"         'activation_env':{'path':ACTIVATION_PATH,'sha256':ACTIVATION_SHA256,","         'activation_env':{'path':CONFIG_DIRECTORY,'sha256':ACTIVATION_SHA256,",effect='activation_env.path')
add('E06_activation_action',"'action':{'ACTIVATE':'CREATE_IF_ABSENT_ACCEPT_IF_CONSTANT','RESTART':'REQUIRED_CONSTANT',","'action':{'ACTIVATE':'CREATE_IF_ABSENT','RESTART':'REQUIRED_CONSTANT',",
    effect='activation_env.action')
add('E09_unit_timer',"TIMER_UNIT:files['reader_timer'],ALERT_UNIT:","TIMER_UNIT:files['reader_service'],ALERT_UNIT:",effect='unit_files.c3po-reader.timer')
add('E10_unit_alert',"ALERT_UNIT:files['reader_alert'],","ALERT_UNIT:None,",effect='unit_files.c3po-reader-alert.service')
add('E11_unit_producer',"                       PRODUCER_UNIT:files['producer_service']},","                       PRODUCER_UNIT:files['launcher']},",effect='unit_files.c3po-massive.service')
add('E12_boot',"         'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],'files_deleted':False,","         'evidence_boot_id_sha256':None,'files_deleted':False,",effect='evidence_boot_id_sha256')
add('E13_files_deleted',"'files_deleted':False,'daemon_reload':'BY_ENABLE_OR_DISABLE_ONLY'}","'files_deleted':None,'daemon_reload':'BY_ENABLE_OR_DISABLE_ONLY'}",effect='files_deleted')
add('E14_daemon_reload',"'files_deleted':False,'daemon_reload':'BY_ENABLE_OR_DISABLE_ONLY'}","'files_deleted':False,'daemon_reload':'NONE'}",effect='daemon_reload')
add('E17_window_utc',"'utc':['07:30:00','20:00:00'],'late_from_utc':'13:28:30'},","'utc':['07:30:00','20:59:59'],'late_from_utc':'13:28:30'},",effect='launch_window.utc')
add('E18_window_late',"'utc':['07:30:00','20:00:00'],'late_from_utc':'13:28:30'},","'utc':['07:30:00','20:00:00'],'late_from_utc':'13:30:00'},",effect='launch_window.late_from_utc')
add('E19_launcher_directory',"               launcher={'directory':chain_effects(plan['launcher_rows']),","               launcher={'directory':chain_effects(plan['config_rows']),",effect='launcher.directory')
add('E20_launcher_sha',"'sha256':files['launcher']},\n               pins_sha256=files['pins'],","'sha256':files['pins']},\n               pins_sha256=files['pins'],",effect='launcher.sha256')
add('E21_pins_sha',"               pins_sha256=files['pins'],\n","               pins_sha256=files['launcher'],\n",effect='pins_sha256')
add('E22_journal_root',"               journal={'root':chain_effects(plan['journal_rows']),","               journal={'root':chain_effects(plan['journal_rows'][:-1]),",effect='journal.root')
add('E23_journal_container',"'container_root':JOURNAL_CONTAINER_ROOT,\n","'container_root':JOURNAL_HOST_ROOT,\n")
add('E24_journal_floor',"                        'free_floor_bytes':plan['journal_free_floor_bytes'],","                        'free_floor_bytes':PRODUCER_FLOOR_BYTES,",effect='journal.free_floor_bytes')
add('E25_journal_data_device',"'data_volume_device':data_volume_row(plan['release_rows'])['device']},","'data_volume_device':plan['journal_rows'][-1]['device']},",effect='journal.data_volume_device')
add('E26_release_path',"               release={'path':release_path_of(plan),","               release={'path':plan['release']['name'],",effect='release.path')
add('E27_release_sha',"'sha256':plan['release']['sha256'],'directory':chain_effects(plan['release_rows'])},","'sha256':files['pins'],'directory':chain_effects(plan['release_rows'])},",effect='release.sha256')
add('E28_release_directory',"'directory':chain_effects(plan['release_rows'])},\n","'directory':chain_effects(plan['release_rows'][:-1])},\n",effect='release.directory')
add('E29_image',"               image_id=plan['image_id'])","               image_id=None)",effect='image_id')
add('E30_success_of_is_constant',"def success_of(plan):return MODE_OUTCOMES[plan['mode']]","def success_of(plan):return COMPLETE_OUTCOME")
add('E31_release_path_joins_without_slash',"def release_path_of(plan):return plan['release_rows'][-1]['path']+'/'+plan['release']['name']",
    "def release_path_of(plan):return plan['release_rows'][-1]['path']+plan['release']['name']")
EFFECTS.update({'switches':'E04_switches','success_outcome':'E03_success_outcome_in_effects','journal.container_root':'E23_journal_container'})

# ---------------------------------------------------------------- the precheck: one mutant per refusal (and per guard)
add('G01_executor_not_checked',"            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')\n","",refusal='EXECUTOR_IDENTITY')
add('G02_umask_not_set',"            host.umask(0o077)\n            need(boot_id","            need(boot_id")
add('G03_boot_not_compared',"            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')\n","",refusal='EVIDENCE_FROM_EARLIER_BOOT')
add('G06_session_day_not_checked',"    need(day in SESSION_DAYS,'READER_NOT_A_SESSION_DAY')\n","",refusal='READER_NOT_A_SESSION_DAY')
add('G07_window_not_bounded',"    need(LAUNCH_FROM_SECONDS<=seconds<LAUNCH_UNTIL_SECONDS,'READER_OUTSIDE_LAUNCH_WINDOW')\n","",refusal='READER_OUTSIDE_LAUNCH_WINDOW')
add('G08_window_end_inclusive',"    need(LAUNCH_FROM_SECONDS<=seconds<LAUNCH_UNTIL_SECONDS,","    need(LAUNCH_FROM_SECONDS<=seconds<=LAUNCH_UNTIL_SECONDS,")
add('G09_window_in_local_time',"    point=now.astimezone(timezone.utc);day=point.date().isoformat()","    point=now;day=point.date().isoformat()")
add('G10_unit_hash_not_compared',"                need(sha(texts[key])==files[key],'UNIT_FILE_NOT_AS_SIGNED')\n","",refusal='UNIT_FILE_NOT_AS_SIGNED')
add('G11_unit_mode_0600',"texts[key]=pinned_file(host,unit,units,gate,0o644,","texts[key]=pinned_file(host,unit,units,gate,0o600,")
add('G12_pinned_file_absent_not_checked',"    need(info is not None and stat.S_ISREG(info.st_mode) and info.st_size<=limit,code)","    need(stat.S_ISREG(info.st_mode) and info.st_size<=limit,code)")
add('G13_pinned_file_any_owner',"    need((held.st_uid,held.st_gid,stat.S_IMODE(held.st_mode),held.st_nlink)==(0,0,mode,1),code)","    need((stat.S_IMODE(held.st_mode),held.st_nlink)==(mode,1),code)")
add('G14_pinned_file_any_links',"    need((held.st_uid,held.st_gid,stat.S_IMODE(held.st_mode),held.st_nlink)==(0,0,mode,1),code)","    need((held.st_uid,held.st_gid,stat.S_IMODE(held.st_mode))==(0,0,mode),code)")
add('G15_pinned_file_not_regular',"    need(info is not None and stat.S_ISREG(info.st_mode) and info.st_size<=limit,code)","    need(info is not None and info.st_size<=limit,code)")
add('G16_pinned_file_size_unbounded',"    need(info is not None and stat.S_ISREG(info.st_mode) and info.st_size<=limit,code)","    need(info is not None and stat.S_ISREG(info.st_mode),code)")
add('G17_pinned_file_held_not_compared',"    need((held.st_dev,held.st_ino)==(info.st_dev,info.st_ino),code)\n","")
add('G18_pinned_file_absent_at_open_escapes',"    except FileNotFoundError:raise Refused(code) from None\n    need((held","    except FileNotFoundError:raise\n    need((held")
add('G19_alert_not_read',"('reader_alert',ALERT_UNIT),","")
add('G21_service_not_fit',"            unit_fit(service,SERVICE_UNIT);unit_fit(timer,TIMER_UNIT)","            unit_fit(timer,TIMER_UNIT)")
add('G22_timer_not_fit',"            unit_fit(service,SERVICE_UNIT);unit_fit(timer,TIMER_UNIT)","            unit_fit(service,SERVICE_UNIT)")
add('G23_not_loaded_accepted',"    need(values['LoadState']=='loaded','READER_UNIT_NOT_LOADED')\n","",refusal='READER_UNIT_NOT_LOADED')
add('G24_fragment_not_checked',"    need(values['FragmentPath']==UNIT_DIRECTORY+'/'+unit and values['DropInPaths']=='','READER_UNIT_NOT_THE_INSTALLED_FILE')",
    "    need(values['DropInPaths']=='','READER_UNIT_NOT_THE_INSTALLED_FILE')",refusal='READER_UNIT_NOT_THE_INSTALLED_FILE')
add('G25_drop_in_accepted',"    need(values['FragmentPath']==UNIT_DIRECTORY+'/'+unit and values['DropInPaths']=='','READER_UNIT_NOT_THE_INSTALLED_FILE')",
    "    need(values['FragmentPath']==UNIT_DIRECTORY+'/'+unit,'READER_UNIT_NOT_THE_INSTALLED_FILE')")
add('G26_properties_any_bytes',"    need(re.fullmatch(rb'[ -~\\n]*',raw) is not None,'UNIT_PROPERTIES_INVALID');values={}","    values={}",refusal='UNIT_PROPERTIES_INVALID')
add('G27_property_line_without_equals',"key,separator,value=line.partition('=');need(separator=='=','UNIT_PROPERTIES_INVALID')","key,separator,value=line.partition('=')")
add('G28_property_value_any',"            need(key not in values and text(value,'[A-Za-z0-9_./:@+ -]{0,512}'),'UNIT_PROPERTIES_INVALID');values[key]=value",
    "            need(key not in values,'UNIT_PROPERTIES_INVALID');values[key]=value")
add('G29_property_twice',"            need(key not in values and text(value,'[A-Za-z0-9_./:@+ -]{0,512}'),'UNIT_PROPERTIES_INVALID');values[key]=value",
    "            need(text(value,'[A-Za-z0-9_./:@+ -]{0,512}'),'UNIT_PROPERTIES_INVALID');values[key]=value")
add('G30_properties_incomplete',"    need(set(values)==set(UNIT_PROPERTIES) and values['Id']==unit,'UNIT_PROPERTIES_INVALID')","    need(values.get('Id',unit)==unit,'UNIT_PROPERTIES_INVALID')")
add('G31_property_id_any',"    need(set(values)==set(UNIT_PROPERTIES) and values['Id']==unit,'UNIT_PROPERTIES_INVALID')","    need(set(values)==set(UNIT_PROPERTIES),'UNIT_PROPERTIES_INVALID')")
add('G32_enabled_word_any',"    need(re.fullmatch(rb'[a-z-]{1,32}\\n?',raw) is not None,'TIMER_ENABLED_INVALID')\n","",refusal='TIMER_ENABLED_INVALID')
add('G33_text_checks_skipped',"                unit_text_checks(texts['reader_service'],texts['producer_service'],plan['image_id'],target)\n","")
add('G34_mounts_not_checked',"    need(all(service.count(('  --mount type=bind,source=%s,target=%s,readonly \\\\\\n'%pair).encode('ascii'))==1 for pair in mounts)\n         and service.count(b'--mount ')==len(mounts),",
    "    need(True,",refusal='READER_UNIT_MOUNTS_NOT_AS_SIGNED')
add('G35_mount_count_not_checked',"         and service.count(b'--mount ')==len(mounts),'READER_UNIT_MOUNTS_NOT_AS_SIGNED')","         ,'READER_UNIT_MOUNTS_NOT_AS_SIGNED')")
add('G36_mount_without_readonly',",target=%s,readonly \\\\\\n'%pair",",target=%s,readonly'%pair")
add('G37_mount_list_loses_the_capacity',"(CAPACITY_ROOT,CAPACITY_TARGET),(LAUNCHER_DIRECTORY,LAUNCHER_TARGET),\n","(LAUNCHER_DIRECTORY,LAUNCHER_TARGET),\n")
add('G38_image_not_checked',"    need(service.count(image_id.encode('ascii'))==2 and b'@' not in service,'READER_UNIT_IMAGE_NOT_THE_PIN')","    pass",refusal='READER_UNIT_IMAGE_NOT_THE_PIN')
add('G39_placeholder_accepted',"    need(service.count(image_id.encode('ascii'))==2 and b'@' not in service,","    need(service.count(image_id.encode('ascii'))==2,")
add('G40_image_once_enough',"    need(service.count(image_id.encode('ascii'))==2 and","    need(service.count(image_id.encode('ascii'))>=1 and")
add('G41_producer_not_checked',"    need(producer.count(('  --mount type=bind,source=%s,target=%s \\\\\\n'%(JOURNAL_HOST_ROOT,JOURNAL_CONTAINER_ROOT)).encode('ascii'))==1\n         and ",
    "    need(",refusal='PRODUCER_UNIT_JOURNAL_NOT_AS_SIGNED')
add('G42_producer_argument_not_checked',"         and producer.count((' --journal-root %s '%JOURNAL_CONTAINER_ROOT).encode('ascii'))==1,'PRODUCER_UNIT_JOURNAL_NOT_AS_SIGNED')",
    "         ,'PRODUCER_UNIT_JOURNAL_NOT_AS_SIGNED')")
add('G43_launcher_not_compared',"MAX_LAUNCHER_BYTES,'LAUNCHER_NOT_AS_SIGNED'))==files['launcher'],'LAUNCHER_NOT_AS_SIGNED')","MAX_LAUNCHER_BYTES,'LAUNCHER_NOT_AS_SIGNED'))!=1,'LAUNCHER_NOT_AS_SIGNED')",
    refusal='LAUNCHER_NOT_AS_SIGNED')
add('G44_launcher_mode_0644',"pinned_file(host,LAUNCHER_NAME,launcher,gate,0o600,","pinned_file(host,LAUNCHER_NAME,launcher,gate,0o644,")
add('G45_pins_not_compared',"                need(sha(pins)==files['pins'],'PINS_NOT_AS_SIGNED')\n","",refusal='PINS_NOT_AS_SIGNED')
add('G46_pins_mode_0644',"pins=pinned_file(host,PINS_NAME,config,gate,0o600,","pins=pinned_file(host,PINS_NAME,config,gate,0o644,")
add('G47_secret_absent_accepted',"                need(secret is not None and stat.S_ISREG(secret.st_mode) and","                need(secret is None or stat.S_ISREG(secret.st_mode) and",refusal='SECRET_ENV_SHAPE')
add('G48_secret_any_mode',"(secret.st_uid,secret.st_gid,stat.S_IMODE(secret.st_mode),secret.st_nlink)==(0,0,0o600,1),","(secret.st_uid,secret.st_gid,secret.st_nlink)==(0,0,1),")
add('G49_secret_any_links',"(secret.st_uid,secret.st_gid,stat.S_IMODE(secret.st_mode),secret.st_nlink)==(0,0,0o600,1),","(secret.st_uid,secret.st_gid,stat.S_IMODE(secret.st_mode))==(0,0,0o600),")
add('G50_secret_any_kind',"need(secret is not None and stat.S_ISREG(secret.st_mode) and (secret","need(secret is not None and (secret")
add('G51_docker_cli_not_checked',"                need(cli is not None and stat.S_ISDIR(cli.st_mode) and (cli.st_uid,cli.st_gid,stat.S_IMODE(cli.st_mode))==(0,0,0o700),'DOCKER_CLI_DIRECTORY_NOT_PRIVATE')",
    "                pass",refusal='DOCKER_CLI_DIRECTORY_NOT_PRIVATE')
add('G52_docker_cli_any_kind',"need(cli is not None and stat.S_ISDIR(cli.st_mode) and (cli","need(cli is not None and (cli")
add('G53_activation_any_content',"'ACTIVATION_ENV_NOT_THE_CONSTANT')==ACTIVATION_BYTES,\n                         'ACTIVATION_ENV_NOT_THE_CONSTANT')",
    "'ACTIVATION_ENV_NOT_THE_CONSTANT')!=1,\n                         'ACTIVATION_ENV_NOT_THE_CONSTANT')",refusal='ACTIVATION_ENV_NOT_THE_CONSTANT')
add('G54_activation_mode_0644',"need(pinned_file(host,ACTIVATION_NAME,config,gate,0o600,len(ACTIVATION_BYTES),'ACTIVATION_ENV_NOT_THE_CONSTANT')",
    "need(pinned_file(host,ACTIVATION_NAME,config,gate,0o644,len(ACTIVATION_BYTES),'ACTIVATION_ENV_NOT_THE_CONSTANT')")
add('G55_restart_without_activation',"                need(mode=='ACTIVATE' or found['activation_env']=='CONSTANT','ACTIVATION_ENV_ABSENT')\n","",refusal='ACTIVATION_ENV_ABSENT')
add('G56_catalog_any_bytes',"MAX_EPOCH_FILE_BYTES,'CATALOG_FILE_NOT_PRIVATE')==expected,'CATALOG_NOT_THIS_EPOCH_AND_ROOT')","MAX_EPOCH_FILE_BYTES,'CATALOG_FILE_NOT_PRIVATE')!=1,'CATALOG_NOT_THIS_EPOCH_AND_ROOT')",
    refusal='CATALOG_NOT_THIS_EPOCH_AND_ROOT')
add('G57_catalog_inode_of_the_parent',"'device':journal.identity[0],'inode':journal.identity[1]})","'device':journal.identity[0],'inode':journal.rows[-2]['inode']})")
add('G58_lock_not_checked',"                need(lock is not None and stat.S_ISREG(lock.st_mode) and (lock.st_uid,lock.st_gid,stat.S_IMODE(lock.st_mode),lock.st_nlink)==(0,0,0o600,1),\n                     'CATALOG_FILE_NOT_PRIVATE')",
    "                pass",refusal='CATALOG_FILE_NOT_PRIVATE')
add('G59_lock_any_links',"(lock.st_uid,lock.st_gid,stat.S_IMODE(lock.st_mode),lock.st_nlink)==(0,0,0o600,1)","(lock.st_uid,lock.st_gid,stat.S_IMODE(lock.st_mode))==(0,0,0o600)")
add('G60_lock_any_kind',"need(lock is not None and stat.S_ISREG(lock.st_mode) and (lock","need(lock is not None and (lock")
add('G61_free_space_not_checked',"                need(free>=plan['journal_free_floor_bytes'],'JOURNAL_FREE_SPACE_BELOW_FLOOR')\n","",refusal='JOURNAL_FREE_SPACE_BELOW_FLOOR')
add('G62_free_space_strict',"                need(free>=plan['journal_free_floor_bytes'],","                need(free>plan['journal_free_floor_bytes'],")
add('G63_release_not_compared',"MAX_RELEASE_BYTES,'RELEASE_NOT_AS_SIGNED'))==plan['release']['sha256'],","MAX_RELEASE_BYTES,'RELEASE_NOT_AS_SIGNED'))!=1,",refusal='RELEASE_NOT_AS_SIGNED')
add('G64_engine_not_read',"                seen['engine']=engine_options(commands)\n","")
add('G65_engine_shape_any',"    need(value is None or (type(value) is list and len(value)<=64 and all(type(item) is str and len(item)<=256 for item in value)),\n         'ENGINE_SECURITY_OPTIONS_INVALID')",
    "    pass",refusal='ENGINE_SECURITY_OPTIONS_INVALID')
add('G66_engine_userns_accepted',"if 'userns' in item.lower() or 'rootless' in item.lower()],","if 'rootless' in item.lower()],",refusal='ENGINE_USERNS_OR_ROOTLESS')
add('G67_engine_rootless_accepted',"if 'userns' in item.lower() or 'rootless' in item.lower()],","if 'userns' in item.lower()],")
add('G68_engine_case_sensitive',"or 'rootless' in item.lower()],","or 'rootless' in item],")
add('G69_engine_options_count',"    return {'options':len(value or []),'userns_or_rootless':False}","    return {'options':0,'userns_or_rootless':False}")
add('G70_image_id_not_compared',"                need(image['id']==plan['image_id'],'IMAGE_NOT_PRESENT')\n","",refusal='IMAGE_NOT_PRESENT')
add('G71_pins_release_file_any',"                need(values['C3PO_R2D2_V2_SHADOW_RELEASE_FILE']==DATA_TARGET+release_path_of(plan)[len(DATA_VOLUME):]\n                     and ",
    "                need(",refusal='PINS_CONTENT_NOT_AS_SIGNED')
add('G72_pins_release_sha_any',"                     and values['C3PO_R2D2_V2_SHADOW_RELEASE_SHA']==plan['release']['sha256']\n","")
add('G73_pins_journal_any',"                     and values['C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR']==JOURNAL_CONTAINER_ROOT\n","")
add('G74_pins_launcher_any',"                     and values['C3PO_READER_LAUNCHER_SHA256']==files['launcher'],'PINS_CONTENT_NOT_AS_SIGNED')","                     ,'PINS_CONTENT_NOT_AS_SIGNED')")
add('G75_pins_build_sha_any',"                need(values['C3PO_BUILD_SHA']==image['revision_label'],'PINS_BUILD_SHA_NOT_THE_IMAGE_REVISION')\n","",refusal='PINS_BUILD_SHA_NOT_THE_IMAGE_REVISION')
add('G76_pins_any_bytes',"    need(type(raw) is bytes and re.fullmatch(rb'[ -~\\n]*',raw) is not None and raw.endswith(b'\\n'),'PINS_CONTENT_NOT_AS_SIGNED')",
    "    need(type(raw) is bytes and raw.endswith(b'\\n'),'PINS_CONTENT_NOT_AS_SIGNED')")
add('G77_pins_without_final_newline',"re.fullmatch(rb'[ -~\\n]*',raw) is not None and raw.endswith(b'\\n'),'PINS_CONTENT_NOT_AS_SIGNED')","re.fullmatch(rb'[ -~\\n]*',raw) is not None,'PINS_CONTENT_NOT_AS_SIGNED')")
add('G78_pins_any_count',"    need(len(lines)==len(PINS_NAMES),'PINS_CONTENT_NOT_AS_SIGNED');values={}","    values={}")
add('G79_pins_any_name',"        need(key==name and text(value,PINS_VALUE),'PINS_CONTENT_NOT_AS_SIGNED');values[key]=value","        need(text(value,PINS_VALUE),'PINS_CONTENT_NOT_AS_SIGNED');values[key]=value")
add('G81_scan_not_made',"                scan=process_scan(commands,containers);seen['process_scan']=scan","                scan=[];seen['process_scan']=scan")
add('G82_scan_any_shape',"        need(set(value)=={'id','path','args','exec_ids'} and value['id']==row['id'] and type(value['path']) is str\n",
    "        need(set(value)=={'id','path','args','exec_ids'}\n",refusal='CONTAINER_COMMAND_INVALID')
add('G83_scan_args_unbounded',"len(value['args'])<=MAX_COMMAND_WORDS and ","")
add('G84_scan_exec_ids_any',"(type(value['exec_ids']) is list and all(type(item) is str for item in value['exec_ids']))","(type(value['exec_ids']) is list)")
add('G85_scan_args_any',"(type(value['args']) is list and len(value['args'])","(type(value['args']) in (list,str) and len(value['args'])")
add('G88_scan_exec_count',"                    'exec_sessions':len(value['exec_ids'] or [])})","                    'exec_sessions':0})")
add('G89_scan_exited_too',"        if row['state'] not in SCAN_STATES:continue\n","")
add('G90_capacity_day_is_a_reader',"for marker in READER_MARKERS) and not any(NOT_A_READER_MARKER in word for word in words)","for marker in READER_MARKERS)")
add('G91_marker_exact_word',"    return any(marker in word for word in words for marker in READER_MARKERS)","    return any(marker==word for word in words for marker in READER_MARKERS)")
add('G92_fresh_timer_enabled_accepted',"                    need(word=='disabled' and timer['ActiveState']=='inactive','TIMER_ENABLED_BEFORE_ACTIVATION')\n","",refusal='TIMER_ENABLED_BEFORE_ACTIVATION')
add('G93_fresh_timer_active_accepted',"                    need(word=='disabled' and timer['ActiveState']=='inactive',","                    need(word=='disabled',")
add('G94_fresh_service_active_accepted',"                    need(service['ActiveState'] in STOPPED_STATES,'SERVICE_ACTIVE_BEFORE_ACTIVATION')\n","",refusal='SERVICE_ACTIVE_BEFORE_ACTIVATION')
add('G95_reconcile_any_state',"                    need(service['ActiveState'] in STOPPED_STATES+ACTIVE_STATES,'SERVICE_STATE_UNEXPECTED')\n","",refusal='SERVICE_STATE_UNEXPECTED')
add('G96_reconcile_not_said',"                    found['reconcile']=True\n","                    pass\n")
add('G97_restart_timer_disabled_accepted',"                    need(word=='enabled','TIMER_NOT_ENABLED')\n","",refusal='TIMER_NOT_ENABLED')
add('G98_restart_active_accepted',"                    need(service['ActiveState'] in STOPPED_STATES,'SERVICE_NOT_STOPPED')\n","",refusal='SERVICE_NOT_STOPPED')
add('GA0_reconcile_container_not_checked',"                    need(facts['running'] is True and facts['image_id']==plan['image_id'],'READER_CONTAINER_NOT_THE_PINNED_READER')\n","",
    refusal='READER_CONTAINER_NOT_THE_PINNED_READER')
add('GA1_reconcile_container_any_image',"need(facts['running'] is True and facts['image_id']==plan['image_id'],","need(facts['running'] is True,")
add('GA2_reconcile_container_not_running',"need(facts['running'] is True and facts['image_id']==plan['image_id'],","need(facts['image_id']==plan['image_id'],")
add('GA3_reconcile_second_reader_accepted',"                    need(not [row for row in scan if row['reader_like'] and row['name']!=READER_CONTAINER],'READER_PROCESS_FOUND')\n","")
add('GA4_reconcile_when_inactive',"                if mode=='ACTIVATE' and found['reconcile'] and active and own:","                if mode=='ACTIVATE' and found['reconcile'] and own:")
add('GA5_container_present_accepted',"                    need(not own,'READER_CONTAINER_PRESENT')\n","",refusal='READER_CONTAINER_PRESENT')
add('GA6_reader_process_accepted',"                    need(not [row for row in scan if row['reader_like']],'READER_PROCESS_FOUND')\n","",refusal='READER_PROCESS_FOUND')
add('GA7_reconciled_container_facts_dropped',"seen['reconciled_container']={'id':facts['id'],","seen['reconciled_container']={'id':None,")
add('GA8_budget_not_checked',"            need(left>=effects_budget(*switches)+SWITCH_FILE_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')\n","",
    refusal='BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
add('GA9_budget_strict',"            need(left>=effects_budget(*switches)+","            need(left>effects_budget(*switches)+")
add('GB0_budget_of_one_switch',"need(left>=effects_budget(*switches)+SWITCH_FILE_ALLOWANCE_SECONDS,","need(left>=effects_budget(switches[-1])+SWITCH_FILE_ALLOWANCE_SECONDS,")
add('GB1_precheck_os_error_code',"code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')","code=code_of(error,'PRECHECK_FAILED')",refusal='PRECHECK_OS_ERROR')
add('GB2_precheck_failure_is_not_a_refusal',"        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})\n","",refusal='PRECHECK_FAILED')
add('GB3_seconds_left_not_said',"            left=gate();seen['seconds_left_before_first_effect']=int(left)","            left=gate();seen['seconds_left_before_first_effect']=0")

# ---------------------------------------------------------------- effects and readback
add('W01_file_created_in_reconcile',"        if mode=='ACTIVATE' and found['activation_env']=='ABSENT':\n            row=create_file(","        if mode=='ACTIVATE':\n            row=create_file(")
add('W02_file_mode_0644',"            row=create_file(0,'ACTIVATION_ENV',ACTIVATION_PATH,ACTIVATION_BYTES,0o600,","            row=create_file(0,'ACTIVATION_ENV',ACTIVATION_PATH,ACTIVATION_BYTES,0o644,")
add('W03_switch_after_a_failed_file',"            if row['state']!='INSTALLED_DURABLE':stop=row['code'] or 'ACTIVATION_ENV_NOT_CREATED'\n","")
add('W05_not_started_continues',"            if not result['started']:stop=result['code'] or 'SWITCH_NOT_STARTED'\n","            if not result['started']:pass\n")
add('W06_uncertain_continues',"            elif not result['returned']:stop=result['code'] or 'SWITCH_UNCERTAIN'\n","")
add('W07_failed_command_continues',"            elif result['returncode']!=0:stop='SWITCH_COMMAND_FAILED'\n","")
add('W08_readback_failure_ignored',"            if stop is None:stop=code_of(error,'READBACK_UNAVAILABLE')\n        for name,item","            pass\n        for name,item",refusal='READBACK_UNAVAILABLE')
add('W09_settle_skipped',"            if item['settled'] is None:item['settled']=settle(state,name,item,found['before'],read)\n","            pass\n")
add('W10_readback_of_the_timer_word_as_before',"            read=(word,timer['ActiveState'],service['ActiveState'])","            read=found['before']")
add('W11_settle_unknown_when_no_readback_is_done',"    if after is None:\n        state.unknown();return 'UNKNOWN'","    if after is None:\n        state.done();return 'DONE'")
add('W12_enable_reached_without_active',"reached={'enable_now_timer':word=='enabled' and timer=='active',","reached={'enable_now_timer':word=='enabled',")
add('W13_enable_reached_without_word',"reached={'enable_now_timer':word=='enabled' and timer=='active',","reached={'enable_now_timer':timer=='active',")
add('W14_start_reached_when_reloading',"             'start_service':service in ('active','activating'),","             'start_service':service in ACTIVE_STATES,")
add('W15_start_reached_when_inactive',"             'start_service':service in ('active','activating'),","             'start_service':service!='failed',")
add('W16_reset_reached_on_failure',"             'reset_failed_service':result['returncode']==0 and service!='failed',","             'reset_failed_service':service!='failed',")
add('W17_reset_reached_when_failed',"             'reset_failed_service':result['returncode']==0 and service!='failed',","             'reset_failed_service':result['returncode']==0,")
add('W18_disable_reached_without_inactive',"             'disable_now_timer':word=='disabled' and timer=='inactive',","             'disable_now_timer':word=='disabled',")
add('W19_disable_reached_without_word',"             'disable_now_timer':word=='disabled' and timer=='inactive',","             'disable_now_timer':timer=='inactive',")
add('W20_stop_reached_always',"             'stop_service':service not in ACTIVE_STATES}[name]","             'stop_service':True}[name]")
add('W22_failed_whatever_changed',"and [after[index] for index in SETTLED_BY[name]]==[before[index] for index in SETTLED_BY[name]]:","and True:")
add('W23_enable_judged_on_the_service',"SETTLED_BY={'enable_now_timer':(0,1),","SETTLED_BY={'enable_now_timer':(2,),")
add('W24_start_judged_on_the_timer',"'disable_now_timer':(0,1),'start_service':(2,),","'disable_now_timer':(0,1),'start_service':(0,1),")
add('W25_stop_judged_on_the_timer',"'reset_failed_service':(2,),'stop_service':(2,)}","'reset_failed_service':(2,),'stop_service':(0,)}")
add('W26_disable_judged_on_the_service',"'enable_now_timer':(0,1),'disable_now_timer':(0,1),","'enable_now_timer':(0,1),'disable_now_timer':(2,),")
add('W27_reset_judged_on_the_timer',"'start_service':(2,),'reset_failed_service':(2,),","'start_service':(2,),'reset_failed_service':(1,),")
add('W28_created_file_not_read_back',"                failed=readback_file(ledger[0],ACTIVATION_BYTES,0o600,config,host,gate) if ledger[0]['state']=='INSTALLED_DURABLE' else None",
    "                failed=None")
add('W29_readback_failure_not_a_stop',"                if failed is not None and stop is None:stop=failed\n","")
add('W30_reconciled_file_not_read_again',"                    need(pinned_file(host,ACTIVATION_NAME,config,gate,0o600,len(ACTIVATION_BYTES),'ACTIVATION_ENV_CHANGED')==ACTIVATION_BYTES,'ACTIVATION_ENV_CHANGED')\n",
    "",refusal='ACTIVATION_ENV_CHANGED')
add('W31_reconciled_readback_failure_ignored',"                    after['activation_env']=safe(error)\n                    if stop is None:stop=code_of(error,'READBACK_UNAVAILABLE')",
    "                    after['activation_env']=safe(error)")
add('W32_container_fact_is_a_gate',"            after['container']=attempt(container_after)","            after['container']=container_after()")
add('W33_container_fact_image',"'image_equal_the_pin':facts['image_id']==plan['image_id'],","'image_equal_the_pin':True,")
add('W34_container_fact_id',"return {'status':'COMPLETE','exists':True,'id':facts['id'],","return {'status':'COMPLETE','exists':True,'id':None,")
add('W35_complete_with_an_unsettled_switch',"        if stop is None and [name for name,item in results.items() if item['settled']!='DONE']:stop='SWITCH_NOT_READ_BACK_AS_DONE'\n","")
add('W36_complete_whatever',"        if stop is None:return finish(COMPLETE_STATUS,MODE_OUTCOMES[mode],None,extra)\n","        if True:return finish(COMPLETE_STATUS,MODE_OUTCOMES[mode],None,extra)\n")
add('W37_changed_host_is_a_refusal',"        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n","        if True:return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n")
add('W38_clean_run_is_a_partial',"        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)\n","")
add('W39_activation_performed_always',"        switched=True if 'DONE' in labels else (None if 'UNKNOWN' in labels else False)","        switched=True")
add('W40_activation_uncertain_said_false',"        switched=True if 'DONE' in labels else (None if 'UNKNOWN' in labels else False)","        switched=True if 'DONE' in labels else False")
add('W43_complete_outcome_is_activate',"        if stop is None:return finish(COMPLETE_STATUS,MODE_OUTCOMES[mode],None,extra)","        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)")
add('W44_partial_reported_complete',"        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)\n","        return finish(COMPLETE_STATUS,PARTIAL_OUTCOME,stop,extra)\n")
add('W45_objects_left_not_counted',"objects_left_by_this_run=objects_left([],ledger),","objects_left_by_this_run=0,")
add('W46_reconcile_not_reported',"launch=found['window'],reconcile=found['reconcile'],","launch=found['window'],reconcile=False,")
add('W47_held_not_closed',"        for handle in held:\n            try:handle.close()","        for handle in []:\n            try:handle.close()")
add('W48_after_units_dropped',"            after.update(timer_enabled=word,","            after.update(timer_enabled=None,")
add('W49_files_deleted_said',"activation_performed=switched,daemon_reload_performed=reloaded,files_deleted=False,","activation_performed=switched,daemon_reload_performed=reloaded,files_deleted=None,")
add('W50_reduction_scan_dropped',"REDUCTIONS=[('PROCESS_SCAN_REDUCED_TO_COUNTS',_reduce_scan),('PRECHECK_DROPPED',_reduce_precheck)]","REDUCTIONS=[('PRECHECK_DROPPED',_reduce_precheck)]")
add('W51_reduction_precheck_dropped',"REDUCTIONS=[('PROCESS_SCAN_REDUCED_TO_COUNTS',_reduce_scan),('PRECHECK_DROPPED',_reduce_precheck)]","REDUCTIONS=[('PROCESS_SCAN_REDUCED_TO_COUNTS',_reduce_scan)]")
add('W52_reduction_scan_counts',"'reader_like':sum(1 for row in precheck['process_scan'] if row.get('reader_like'))}","'reader_like':0}")
add('W53_before_state_of_the_service_not_kept',"            found['before']=(word,timer['ActiveState'],service['ActiveState'])","            found['before']=(word,timer['ActiveState'],None)")
add('W54_launch_not_reported',"launch=found['window'],reconcile","launch=None,reconcile")
# ---------------------------------------------------------------- revision 2: the review's findings (2026-10-04)
add('C60_deactivate_uses_the_units',"NOT_USED_BY_DEACTIVATE=('unit_rows','config_rows',","NOT_USED_BY_DEACTIVATE=('config_rows',")
add('C61_deactivate_uses_the_files',"'release','files','image_id','journal_free_floor_bytes',\n","'release','image_id','journal_free_floor_bytes',\n")
add('C62_retention_per_session',"SESSION_RETENTION_BYTES=603979776\n","SESSION_RETENTION_BYTES=603979775\n")
add('C63_reader_command_words',"READER_COMMAND_WORDS=('python','-I','-B','/c3po-reader/reader_launcher.py')","READER_COMMAND_WORDS=('python','-B','/c3po-reader/reader_launcher.py')")
add('P08_deactivate_accepts_unused_members',"        need(all(plan[key] is None for key in NOT_USED_BY_DEACTIVATE),'PLAN_MEMBER_NOT_USED_BY_MODE')\n","",refusal='PLAN_MEMBER_NOT_USED_BY_MODE')
add('P09_deactivate_validated_like_activate',"    if plan['mode']=='DEACTIVATE':\n        need(all(plan[key] is None","    if False:\n        need(all(plan[key] is None")
add('P34_floor_not_checked',"    need(integer(plan['journal_free_floor_bytes'],floor_minimum(plan)),'FREE_FLOOR_BELOW_PRODUCER_FLOOR')","    pass",refusal='FREE_FLOOR_BELOW_PRODUCER_FLOOR')
add('P35_floor_of_the_producer_alone',"    return PRODUCER_FLOOR_BYTES+SESSION_RETENTION_BYTES*len([item for item in SESSION_DAYS if item>=day])","    return PRODUCER_FLOOR_BYTES")
add('P37_floor_counts_every_session',"for item in SESSION_DAYS if item>=day])","for item in SESSION_DAYS])")
add('P38_floor_leaves_the_day_out',"for item in SESSION_DAYS if item>=day])","for item in SESSION_DAYS if item>day])")
add('E07_unit_directory',"    out.update(unit_directory=chain_effects(plan['unit_rows']),","    out.update(unit_directory=chain_effects(plan['unit_rows'][:-1]),",effect='unit_directory')
add('E08_unit_service',"               unit_files={SERVICE_UNIT:files['reader_service'],","               unit_files={SERVICE_UNIT:files['reader_timer'],",effect='unit_files.c3po-reader.service')
add('E15_deactivate_names_a_window',"bind_sources=None,launch_window=None,","bind_sources=None,launch_window=list(SESSION_DAYS),")
add('E15b_deactivate_names_unit_files',"        out.update(unit_directory=None,unit_files=None,","        out.update(unit_directory=None,unit_files={},")
add('E16_window_days',"               launch_window={'days':list(SESSION_DAYS),","               launch_window={'days':list(DATES),",effect='launch_window.days')
add('E32_unit_names',"         'unit_names':[SERVICE_UNIT,TIMER_UNIT],","         'unit_names':[SERVICE_UNIT],",effect='unit_names')
add('G04_window_not_checked',"                found['window']=launch_window(clock())\n","")
add('G05_units_walked_in_deactivate',"            texts={}\n            if mode!='DEACTIVATE':\n","            texts={}\n            if True:\n")
add('G20_unit_fit_in_deactivate',"            if mode!='DEACTIVATE':\n                unit_fit(service,SERVICE_UNIT)","            if True:\n                unit_fit(service,SERVICE_UNIT)")
add('G86_scan_path_ignored',"        words=[value['path']]+list(value['args'] or [])","        words=list(value['args'] or [])")
add('G87_scan_args_ignored',"        words=[value['path']]+list(value['args'] or [])","        words=[value['path']]")
add('G99_restart_stale_unit_accepted',"'SERVICE_NOT_STOPPED')\n                    need(service['NeedDaemonReload']=='no','READER_UNIT_NEEDS_DAEMON_RELOAD')\n","'SERVICE_NOT_STOPPED')\n",
    refusal='READER_UNIT_NEEDS_DAEMON_RELOAD')
add('GB4_reconcile_stale_unit_accepted',"'READER_CONTAINER_NOT_THE_PINNED_READER')\n                    need(service['NeedDaemonReload']=='no','READER_UNIT_NEEDS_DAEMON_RELOAD')\n",
    "'READER_CONTAINER_NOT_THE_PINNED_READER')\n")
add('GB5_reconcile_id_not_compared',"                    need(facts['id']==own[0]['id'],'READER_CONTAINER_CHANGED')\n","",refusal='READER_CONTAINER_CHANGED')
add('GB6_reconcile_command_not_checked',"                    need([row['launcher_command'] for row in scan if row['id']==facts['id']]==[True],'READER_CONTAINER_NOT_THE_PINNED_READER')\n","")
add('GB7_launcher_command_any',"'launcher_command':words==list(READER_COMMAND_WORDS),","'launcher_command':True,")
add('W04_switch_after_a_stop',"            if stop is not None:\n                results[name]={'started':False,'settled':'NOT_ATTEMPTED'};continue","            if False:\n                pass")
add('W21_failed_without_returncode',"    if result['returncode']!=0 and not reloaded and [after","    if not reloaded and [after")
add('W21b_reload_rule_ignored',"    if result['returncode']!=0 and not reloaded and","    if result['returncode']!=0 and")
add('W21c_reload_rule_on_the_wrong_word',"    reloaded=name in TARGET_WORD and before[0]==TARGET_WORD[name]","    reloaded=name in TARGET_WORD and before[0]!=TARGET_WORD[name]")
add('W21d_target_words_swapped',"TARGET_WORD={'enable_now_timer':'enabled','disable_now_timer':'disabled'}","TARGET_WORD={'enable_now_timer':'disabled','disable_now_timer':'enabled'}")
add('W41_reload_said_for_every_switch',"        reloads=[results[name] for name in RELOADING_ROWS if name in results and results[name]['started']]","        reloads=[item for item in results.values() if item['started']]")
add('W42_reload_uncertain_said_false',"                  None if [item for item in reloads if item['settled'] in ('UNKNOWN','DONE')] else False)","                  False)")
add('W42b_reload_on_failure_said_true',"        reloaded=(True if [item for item in reloads if item.get('returncode')==0] else","        reloaded=(True if reloads else")
add('W42c_reload_done_with_failure_said_false',"item['settled'] in ('UNKNOWN','DONE')] else False)","item['settled'] in ('UNKNOWN',)] else False)")
add('W55_changed_unknown_said_false',"        changed=True if True in changes else (None if None in changes else False)","        changed=True if True in changes else False")
add('W56_changed_never_said',"        changed=True if True in changes else","        changed=False if True in changes else")
add('W57_changed_compares_nothing',"[read[index] for index in SETTLED_BY[name]]!=[found['before'][index] for index in SETTLED_BY[name]])","[read[index] for index in SETTLED_BY[name]]!=[read[index] for index in SETTLED_BY[name]])")
add('W58_changed_for_an_unreturned_switch',"None if read is None or not item.get('returned') else","None if read is None else")
add('W59_not_started_said_unknown',"item['changed']=(False if not item['started'] else","item['changed']=(None if not item['started'] else")
add('W60_changed_not_reported',"switches_changed_state=changed,","switches_changed_state=None,")
# ---------------------------------------------------------------- revision 2: Codex decision 6 (bind sources root-controlled)
add('D01_source_root_elsewhere',"SOURCE_ROOT='/var/lib/c3po/r2d2-v2-source-20261005'","SOURCE_ROOT='/mnt/day-d-data/r2d2-v2-source-20261005'")
add('D02_source_target_any',"SOURCE_TARGET='/c3po-[a-z0-9][a-z0-9-]*'","SOURCE_TARGET='/[A-Za-z0-9._/-]+'")
add('D03_source_target_may_be_the_capacity',"SOURCE_TARGETS_TAKEN=(CAPACITY_TARGET,LAUNCHER_TARGET,JOURNAL_CONTAINER_ROOT)","SOURCE_TARGETS_TAKEN=(LAUNCHER_TARGET,JOURNAL_CONTAINER_ROOT)")
add('D04_source_target_may_be_the_launcher',"SOURCE_TARGETS_TAKEN=(CAPACITY_TARGET,LAUNCHER_TARGET,JOURNAL_CONTAINER_ROOT)","SOURCE_TARGETS_TAKEN=(CAPACITY_TARGET,JOURNAL_CONTAINER_ROOT)")
add('D05_source_target_may_be_the_journal',"SOURCE_TARGETS_TAKEN=(CAPACITY_TARGET,LAUNCHER_TARGET,JOURNAL_CONTAINER_ROOT)","SOURCE_TARGETS_TAKEN=(CAPACITY_TARGET,LAUNCHER_TARGET)")
add('D06_source_chain_not_validated',"    validate_chain(plan['source_rows'],SOURCE_ROOT)\n","")
add('D07_source_chain_not_private',"    need(all(root_controlled(row) for row in plan['source_rows']) and private_directory_row(plan['source_rows'][-1]),'SOURCE_ROOT_NOT_PRIVATE')\n","",
    refusal='SOURCE_ROOT_NOT_PRIVATE')
add('D08_source_leaf_any_mode',"and private_directory_row(plan['source_rows'][-1]),'SOURCE_ROOT_NOT_PRIVATE')","and True,'SOURCE_ROOT_NOT_PRIVATE')")
add('D09_capacity_chain_not_validated',"    validate_chain(plan['capacity_rows'],CAPACITY_ROOT)\n","")
add('D10_capacity_chain_not_private',"    need(all(root_controlled(row) for row in plan['capacity_rows']) and private_directory_row(plan['capacity_rows'][-1]),'CAPACITY_ROOT_NOT_PRIVATE')\n","",
    refusal='CAPACITY_ROOT_NOT_PRIVATE')
add('D11_capacity_leaf_any_mode',"and private_directory_row(plan['capacity_rows'][-1]),'CAPACITY_ROOT_NOT_PRIVATE')","and True,'CAPACITY_ROOT_NOT_PRIVATE')")
add('D12_source_not_walked',"                held.append(Pinned(host,walk_pinned(host,plan['source_rows'],gate,seen['chains'].setdefault('source',[])),rows=plan['source_rows']))\n","")
add('D13_capacity_not_walked',"                held.append(Pinned(host,walk_pinned(host,plan['capacity_rows'],gate,seen['chains'].setdefault('capacity',[])),rows=plan['capacity_rows']))\n","")
add('D14_pins_source_dir_any',"                need(text(target,SOURCE_TARGET) and target not in SOURCE_TARGETS_TAKEN,'PINS_SOURCE_DIR_NOT_A_TOP_LEVEL_TARGET')\n","",
    refusal='PINS_SOURCE_DIR_NOT_A_TOP_LEVEL_TARGET')
add('D15_pins_source_dir_taken_accepted',"need(text(target,SOURCE_TARGET) and target not in SOURCE_TARGETS_TAKEN,","need(text(target,SOURCE_TARGET),")
add('D16_source_bind_not_required',"            (SOURCE_ROOT,source_target)]","            ]")
add('D17_source_bind_at_any_target',"unit_text_checks(texts['reader_service'],texts['producer_service'],plan['image_id'],target)","unit_text_checks(texts['reader_service'],texts['producer_service'],plan['image_id'],'/c3po-source')")
add('D18_data_volume_flag_dropped',"binds_not_root_controlled=[] if mode=='DEACTIVATE' else [DATA_VOLUME],","binds_not_root_controlled=[],")
add('D19_data_volume_flag_in_deactivate',"binds_not_root_controlled=[] if mode=='DEACTIVATE' else [DATA_VOLUME],","binds_not_root_controlled=[DATA_VOLUME],")
add('E33_bind_source_root',"               bind_sources={'source_root':chain_effects(plan['source_rows']),","               bind_sources={'source_root':chain_effects(plan['journal_rows']),",effect='bind_sources.source_root')
add('E34_bind_capacity_root',"'capacity_root':chain_effects(plan['capacity_rows']),","'capacity_root':chain_effects(plan['source_rows']),",effect='bind_sources.capacity_root')
add('E35_bind_not_root_controlled',"                             'not_root_controlled':[DATA_VOLUME]},","                             'not_root_controlled':[]},",effect='bind_sources.not_root_controlled')
add('E36_deactivate_names_bind_sources',"out.update(unit_directory=None,unit_files=None,bind_sources=None,","out.update(unit_directory=None,unit_files=None,bind_sources={},")
REFUSALS.update({'MODE_INVALID':'P01_mode_not_checked','UNIT_PROPERTIES_INVALID':'G26_properties_any_bytes'})

# ---------------------------------------------------------------- the dispatcher generated for this operation
# Two rows of the core's list are anchored on the date literal of its demonstration write operation (WRITE_EPOCH);
# these are the same two for the literal of this operation (WRITE_SESSIONS), and one more for the day after (K4-E0's rows).
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
    raw=Path(path).read_bytes();name='_hostops02_k13_mutation_'+hashlib.sha256(raw).hexdigest()[:12]
    module=type(sys)(name);module.__dict__['__file__']='<assembled k13_reader_switch.py>';sys.modules[name]=module
    exec(compile(raw,module.__dict__['__file__'],'exec'),module.__dict__);return module

LEAVES=('unit_directory','directory','root','source_root','capacity_root')          # chain_effects() results: one member each
def _members(value,prefix=''):
    out=[]
    for key in sorted(value):
        if type(value[key]) is dict and key not in LEAVES:out+=_members(value[key],prefix+key+'.')
        else:out.append(prefix+key)
    return out

def codes_of(text):
    """Every constant code the operation part can raise: the last argument of each need(), Refused() and code_of()."""
    found=set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in ('need','Refused','code_of'):
            for argument in node.args[-1:]:
                for item in ast.walk(argument):
                    if isinstance(item,ast.Constant) and type(item.value) is str and re.fullmatch('[A-Z][A-Z0-9_]{2,79}',item.value):found.add(item.value)
    return found

def coverage(here):
    """Errors when a member of effects_of() (mode ACTIVATE, which has every member) or a refusal of the operation part
    has no mutant named for it."""
    here=Path(here);errors=[];names={row[0] for row in M};module=_load(here/'build'/'k13_reader_switch.py')
    def rows(path,device=1,data=False):
        out=[];prefix=''
        for index,part in enumerate(['']+path.strip('/').split('/')):
            prefix=(prefix.rstrip('/')+'/'+part) if part else '/'
            on=2 if data and prefix.startswith('/mnt/day-d-data') else device
            out.append({'path':prefix,'device':on,'inode':index+10,'uid':0,'gid':0,'mode':0o700 if index>=3 else 0o755})
        return out
    plan={'mode':'ACTIVATE','evidence_boot_id_sha256':'a'*64,'unit_rows':rows('/etc/systemd/system'),'config_rows':rows('/etc/c3po-reader'),
          'launcher_rows':rows('/etc/c3po-reader/launcher'),'journal_rows':rows('/var/lib/c3po-bar/journal'),
          'release_rows':rows('/mnt/day-d-data/r',data=True),'release':{'name':'r.json','sha256':'b'*64},
          'files':{key:'c'*64 for key in module.FILE_KEYS},'image_id':'sha256:'+'d'*64,'journal_free_floor_bytes':module.PRODUCER_FLOOR_BYTES,
          'source_rows':rows('/var/lib/c3po/r2d2-v2-source-20261005'),'capacity_rows':rows('/var/lib/c3po-capacity')}
    wanted=set(_members(module.effects_of(plan)))
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
