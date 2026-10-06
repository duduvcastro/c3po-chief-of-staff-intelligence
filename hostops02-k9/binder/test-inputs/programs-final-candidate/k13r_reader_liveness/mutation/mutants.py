"""The mutants of K13r's own part. Each row: (name, target, exact anchor, replacement); target 'op' is the built source
build/k13r_reader_liveness.py, in which the anchor must occur exactly once (mutate.py check). One mutant per member of
effects_of(), one per refusal code and one per finding of the operation part, one per word of each command row, and the
constants of the reader. EFFECTS, REFUSALS and FINDINGS name the mutant that answers for each; coverage() compares them
with the source itself. Modelled on K13's list."""
import ast
import hashlib
from pathlib import Path
import re
import sys

M=[]
EFFECTS={}
REFUSALS={}
FINDINGS={}
def add(name,old,new,effect=None,refusal=None,finding=None):
    M.append((name,'op',old,new))
    for table,keys in ((EFFECTS,effect),(REFUSALS,refusal),(FINDINGS,finding)):
        for key in ([keys] if type(keys) is str else keys or []):table.setdefault(key,name)

# ---------------------------------------------------------------- constants
add('C01_another_epoch',"READER_EPOCH='R2D2-V2-SHADOW-2026-10-05'","READER_EPOCH='R2D2-V2-SHADOW-2026-09-28'",effect='epoch')
add('C02_service_unit',"SERVICE_UNIT='c3po-reader.service'","SERVICE_UNIT='c3po-massive.service'")
add('C03_timer_unit',"TIMER_UNIT='c3po-reader.timer'","TIMER_UNIT='c3po-massive.timer'")
add('C04_unit_directory',"UNIT_DIRECTORY='/etc/systemd/system'","UNIT_DIRECTORY='/run/systemd/system'")
add('C05_reader_container',"READER_CONTAINER='c3po-reader'","READER_CONTAINER='c3po-massive'")
add('C06_data_bind',"READER_BINDS=(('/mnt/day-d-data','/app/day-d-data'),","READER_BINDS=(('/mnt/day-d-data','/app/data'),")
add('C07_journal_bind',"('/var/lib/c3po-bar/journal','/c3po-bar-journal'),","('/var/lib/c3po-bar/journal','/c3po-journal'),")
add('C08_capacity_bind',"('/var/lib/c3po-capacity','/c3po-capacity'),('/etc/c3po-reader/launcher','/c3po-reader'))","('/etc/c3po-reader/launcher','/c3po-reader'),)")
add('C09_launcher_bind',"('/etc/c3po-reader/launcher','/c3po-reader'))","('/etc/c3po-reader','/c3po-reader'))")
add('C10_reader_path',"READER_PATH='python'","READER_PATH='python3'")
add('C11_reader_args_without_isolation',"READER_ARGS=('-I','-B','/c3po-reader/reader_launcher.py')","READER_ARGS=('-B','/c3po-reader/reader_launcher.py')")
add('C12_reader_user',"READER_USER='0:0'","READER_USER='0'")
add('C13_worker_marker',"READER_MARKERS=('app.r2d2_v2_shadow_worker','reader_launcher.py')","READER_MARKERS=('app.r2d2_v2_shadow_workers','reader_launcher.py')")
add('C14_launcher_marker',"READER_MARKERS=('app.r2d2_v2_shadow_worker','reader_launcher.py')","READER_MARKERS=('app.r2d2_v2_shadow_worker',)")
add('C15_capacity_day_marker',"NOT_A_READER_MARKER='--prepare-capacity-day'","NOT_A_READER_MARKER='--capacity'")
add('C16_paused_not_scanned',"SCAN_STATES=('running','paused','restarting')","SCAN_STATES=('running','restarting')")
add('C17_failed_is_not_stopped',"STOPPED_STATES=('inactive','failed')","STOPPED_STATES=('inactive',)")
add('C17b_deactivating_is_stopped',"STOPPED_STATES=('inactive','failed')","STOPPED_STATES=('inactive','failed','deactivating')")
add('C26_timer_asked_for_nrestarts',"TIMER_PROPERTIES=('Id','LoadState','ActiveState','SubState','UnitFileState','FragmentPath','DropInPaths','Result')",
    "TIMER_PROPERTIES=('Id','LoadState','ActiveState','SubState','UnitFileState','FragmentPath','DropInPaths','Result','NRestarts')")
add('C27_timer_without_result',",'FragmentPath','DropInPaths','Result')\n",",'FragmentPath','DropInPaths')\n")
add('C28_timer_row_with_the_service_list',"tail=[part for key in TIMER_PROPERTIES for part in ('-p',key)]),","tail=[part for key in UNIT_PROPERTIES for part in ('-p',key)]),")
add('C29_timer_parsed_with_the_service_list',"TIMER_UNIT,TIMER_PROPERTIES);findings","TIMER_UNIT,UNIT_PROPERTIES);findings")
add('C30_service_parsed_with_the_timer_list',"SERVICE_UNIT,UNIT_PROPERTIES);findings","SERVICE_UNIT,TIMER_PROPERTIES);findings")
add('C18_command_words',"MAX_COMMAND_WORDS=256","MAX_COMMAND_WORDS=257")
add('C19_mounts_limit',"MAX_READER_MOUNTS=16","MAX_READER_MOUNTS=17")
add('C20_property_dropped',",'Result','NRestarts')\n# A timer",",'Result')\n# A timer")
add('C21_evidence_not_the_switch',"EVIDENCE_OPERATIONS=(SWITCH_OPERATION,)","EVIDENCE_OPERATIONS=()")
add('C22_switch_operation',"SWITCH_OPERATION='GO_WRITE_HOSTOPS02_K13_READER_SWITCH_01'","SWITCH_OPERATION='GO_WRITE_HOSTOPS02_K13_READER_SWITCH_02'")
add('C23_mode_list',"LIVENESS_MODES=('LIVE','STOPPED')","LIVENESS_MODES=('LIVE',)")
add('C24_stopped_outcome_is_live',"MODE_OUTCOMES={'LIVE':COMPLETE_OUTCOME,'STOPPED':STOPPED_OUTCOME}","MODE_OUTCOMES={'LIVE':COMPLETE_OUTCOME,'STOPPED':COMPLETE_OUTCOME}",effect='success_outcome')
add('C25_gate_span',"MAX_GATE_SPAN_SECONDS=900","MAX_GATE_SPAN_SECONDS=901")

# ---------------------------------------------------------------- command rows and templates: one per word
add('R01_mounts_template_prints_the_config',"MOUNTS_FORMAT='{{json .Mounts}}'","MOUNTS_FORMAT='{{json .HostConfig.Binds}}'")
add('R02_command_template_without_args',"COMMAND_FORMAT=('{\"id\":{{json .Id}},\"path\":{{json .Path}},\"args\":{{json .Args}},","COMMAND_FORMAT=('{\"id\":{{json .Id}},\"path\":{{json .Path}},\"args\":null,")
add('R03_command_template_init_constant','"init":{{json .HostConfig.Init}},','"init":true,')
add('R04_command_template_read_only_constant','"read_only":{{json .HostConfig.ReadonlyRootfs}},','"read_only":true,')
add('R05_command_template_user_constant','"user":{{json .Config.User}}}\')','"user":"0:0"}\')')
add('R06_scan_template_without_args',"SCAN_FORMAT='{\"id\":{{json .Id}},\"path\":{{json .Path}},\"args\":{{json .Args}}}'","SCAN_FORMAT='{\"id\":{{json .Id}},\"path\":{{json .Path}},\"args\":null}'")
add('R07_scan_template_without_path',"SCAN_FORMAT='{\"id\":{{json .Id}},\"path\":{{json .Path}},","SCAN_FORMAT='{\"id\":{{json .Id}},\"path\":\"x\",")
add('R08_container_row_with_the_scan_template',"'container':command_row('docker',['container','inspect','--format',CONTAINER_FORMAT]","'container':command_row('docker',['container','inspect','--format',SCAN_FORMAT]")
add('R09_listing_without_all',"'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT]","'container_list':command_row('docker',['ps','--no-trunc','--format',PS_FORMAT]")
add('R10_mounts_row_with_the_command_template',"'mounts':command_row('docker',['container','inspect','--format',MOUNTS_FORMAT]","'mounts':command_row('docker',['container','inspect','--format',COMMAND_FORMAT]")
add('R11_command_row_with_the_scan_template',"'reader_command':command_row('docker',['container','inspect','--format',COMMAND_FORMAT]","'reader_command':command_row('docker',['container','inspect','--format',SCAN_FORMAT]")
add('R12_service_show_of_the_timer',"'service_state':command_row('systemctl',['show',SERVICE_UNIT]","'service_state':command_row('systemctl',['show',TIMER_UNIT]")
add('R13_timer_show_of_the_service',"'timer_state':command_row('systemctl',['show',TIMER_UNIT]","'timer_state':command_row('systemctl',['show',SERVICE_UNIT]")
add('R14_is_enabled_of_the_service',"'timer_enabled':command_row('systemctl',['is-enabled',TIMER_UNIT]","'timer_enabled':command_row('systemctl',['is-enabled',SERVICE_UNIT]")
add('R15_show_without_properties',"'timer_state':command_row('systemctl',['show',TIMER_UNIT],None,'QUICK','READ',tail=[part for key in TIMER_PROPERTIES for part in ('-p',key)]),",
    "'timer_state':command_row('systemctl',['show',TIMER_UNIT],None,'QUICK','READ',tail=['-p','Id']),")

# ---------------------------------------------------------------- plan and effects
add('P01_mode_not_checked',"    need(plan['mode'] in LIVENESS_MODES,'MODE_INVALID')\n","",refusal='MODE_INVALID')
add('P02_image_not_checked',"    need(text(plan['image_id'],IMAGE_ID),'IMAGE_ID_INVALID')\n","",refusal='IMAGE_ID_INVALID')
add('P03_boot_not_checked',"    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')\n","",refusal='EVIDENCE_BOOT_UNBOUND')
add('E01_operation',"    return {'operation':OPERATION,'epoch':READER_EPOCH,","    return {'operation':PHASE,'epoch':READER_EPOCH,",effect='operation')
add('E02_mode',"'epoch':READER_EPOCH,'mode':plan['mode'],","'epoch':READER_EPOCH,'mode':'LIVE',",effect='mode')
add('E03_success',"'success_outcome':MODE_OUTCOMES[plan['mode']],\n","'success_outcome':COMPLETE_OUTCOME,\n")
add('E04_image',"            'image_id':plan['image_id'],'evidence_boot_id_sha256':","            'image_id':None,'evidence_boot_id_sha256':",effect='image_id')
add('E05_boot',"'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],\n            'expect'","'evidence_boot_id_sha256':None,\n            'expect'",effect='evidence_boot_id_sha256')
add('E06_expect_service',"'expect':{'service':'active' if live else 'inactive or failed',","'expect':{'service':'active',",effect='expect.service')
add('E07_expect_timer',"'timer':'enabled and active' if live else 'disabled and inactive',","'timer':'enabled and active',",effect='expect.timer')
add('E08_expect_container',"if live else 'none',\n","if live else 'one',\n",effect='expect.reader_container')
add('E09_expect_others',"                      'other_readers':'none'},","                      'other_readers':'any'},",effect='expect.other_readers')
add('E10_writes',"            'writes':0,'side_effects':[]}","            'writes':None,'side_effects':[]}",effect='writes')
add('E11_side_effects',"            'writes':0,'side_effects':[]}","            'writes':0,'side_effects':None}",effect='side_effects')
add('E12_success_of_constant',"def success_of(plan):return MODE_OUTCOMES[plan['mode']]","def success_of(plan):return COMPLETE_OUTCOME")
add('E13_mode_flag_inverted',"    live=plan['mode']=='LIVE'\n    return {","    live=plan['mode']!='LIVE'\n    return {")
EFFECTS['success_outcome']='E03_success'

# ---------------------------------------------------------------- the observations: one per refusal and per finding
add('O01_properties_any_bytes',"    need(re.fullmatch(rb'[ -~\\n]*',raw) is not None,'UNIT_PROPERTIES_INVALID');values={}","    values={}",refusal='UNIT_PROPERTIES_INVALID')
add('O02_property_value_any',"            need(key not in values and text(value,'[A-Za-z0-9_./:@+ -]{0,512}'),'UNIT_PROPERTIES_INVALID');values[key]=value",
    "            need(key not in values,'UNIT_PROPERTIES_INVALID');values[key]=value")
add('O03_properties_incomplete',"    need(set(values)==set(properties) and values['Id']==unit,'UNIT_PROPERTIES_INVALID')","    need(values.get('Id',unit)==unit,'UNIT_PROPERTIES_INVALID')")
add('O04_property_id_any',"    need(set(values)==set(properties) and values['Id']==unit,'UNIT_PROPERTIES_INVALID')","    need(set(values)==set(properties),'UNIT_PROPERTIES_INVALID')")
add('O05_property_line_without_equals',"key,separator,value=line.partition('=');need(separator=='=','UNIT_PROPERTIES_INVALID')","key,separator,value=line.partition('=')")
add('O06_not_loaded_unseen',"    if values['LoadState']!='loaded':out.append('READER_UNIT_NOT_LOADED')\n","",finding='READER_UNIT_NOT_LOADED')
add('O07_fragment_unseen',"    if values['FragmentPath']!=UNIT_DIRECTORY+'/'+unit or values['DropInPaths']!='':","    if values['DropInPaths']!='':",finding='READER_UNIT_NOT_THE_INSTALLED_FILE')
add('O08_drop_in_unseen',"    if values['FragmentPath']!=UNIT_DIRECTORY+'/'+unit or values['DropInPaths']!='':","    if values['FragmentPath']!=UNIT_DIRECTORY+'/'+unit:")
add('O09_boot_unseen',"        return item_of(['BOOT_NOT_THE_EVIDENCE'] if digest!=self.plan['evidence_boot_id_sha256'] else [],","        return item_of([],",finding='BOOT_NOT_THE_EVIDENCE')
add('O10_boot_digest_not_reported',"boot_id_sha256=digest)","boot_id_sha256=None)")
add('O11_service_not_active_unseen',"        if self.live and values['ActiveState']!='active':findings.append('SERVICE_NOT_ACTIVE')\n","",finding='SERVICE_NOT_ACTIVE')
add('O12_service_activating_is_active',"        if self.live and values['ActiveState']!='active':","        if self.live and values['ActiveState'] not in ('active','activating'):")
add('O13_service_not_stopped_unseen',"        if not self.live and values['ActiveState'] not in STOPPED_STATES:findings.append('SERVICE_NOT_STOPPED')\n","",finding='SERVICE_NOT_STOPPED')
add('O14_service_facts_dropped',"        return item_of(findings,**{key:values[key] for key in ('LoadState','ActiveState','SubState','Result','NRestarts')})","        return item_of(findings)")
add('O15_enabled_word_any',"        need(re.fullmatch(rb'[a-z-]{1,32}\\n?',raw) is not None,'TIMER_ENABLED_INVALID');word","        word",refusal='TIMER_ENABLED_INVALID')
add('O16_timer_live_unseen',"        if self.live and (word!='enabled' or values['ActiveState']!='active'):findings.append('TIMER_NOT_ENABLED_AND_ACTIVE')\n","",finding='TIMER_NOT_ENABLED_AND_ACTIVE')
add('O17_timer_live_word_only',"        if self.live and (word!='enabled' or values['ActiveState']!='active'):","        if self.live and (word!='enabled'):")
add('O18_timer_live_state_only',"        if self.live and (word!='enabled' or values['ActiveState']!='active'):","        if self.live and (values['ActiveState']!='active'):")
add('O19_timer_stopped_unseen',"        if not self.live and (word!='disabled' or values['ActiveState']!='inactive'):findings.append('TIMER_NOT_DISABLED_AND_INACTIVE')\n","",
    finding='TIMER_NOT_DISABLED_AND_INACTIVE')
add('O20_timer_stopped_word_only',"        if not self.live and (word!='disabled' or values['ActiveState']!='inactive'):","        if not self.live and (word!='disabled'):")
add('O21_timer_stopped_state_only',"        if not self.live and (word!='disabled' or values['ActiveState']!='inactive'):","        if not self.live and (values['ActiveState']!='inactive'):")
add('O22_unit_findings_dropped',"        values=unit_values(self.commands,'timer_state',TIMER_UNIT,TIMER_PROPERTIES);findings=unit_found(values,TIMER_UNIT)","        values=unit_values(self.commands,'timer_state',TIMER_UNIT,TIMER_PROPERTIES);findings=[]")
add('O23_reader_not_running_unseen',"        if self.live and (self.reader is None or self.reader['state']!='running'):findings.append('READER_CONTAINER_NOT_RUNNING')\n","",
    finding='READER_CONTAINER_NOT_RUNNING')
add('O24_reader_absent_accepted',"        if self.live and (self.reader is None or self.reader['state']!='running'):","        if self.live and self.reader is not None and self.reader['state']!='running':")
add('O25_reader_left_unseen',"        if not self.live and self.reader is not None:findings.append('READER_CONTAINER_PRESENT')\n","",finding='READER_CONTAINER_PRESENT')
add('O26_inspect_without_a_listed_reader',"    def container(self):\n        need(self.reader is not None,'READER_CONTAINER_ABSENT')\n","    def container(self):\n",refusal='READER_CONTAINER_ABSENT')
add('O27_reader_changed_accepted',"        need(facts['id']==self.reader['id'],'READER_CONTAINER_CHANGED')\n","",refusal='READER_CONTAINER_CHANGED')
add('O28_container_not_running_unseen',"        if facts['running'] is not True:findings.append('READER_CONTAINER_NOT_RUNNING')\n","")
add('O29_image_unseen',"        if facts['image_id']!=self.plan['image_id']:findings.append('READER_IMAGE_NOT_THE_PIN')\n","",finding='READER_IMAGE_NOT_THE_PIN')
add('O30_image_reported_equal',"image_equal_the_pin=facts['image_id']==self.plan['image_id'],","image_equal_the_pin=True,")
add('O31_started_at_dropped',"                       started_at=facts['started_at'],restarts=facts['restarts'],","                       started_at=None,restarts=facts['restarts'],")
add('O32_restarts_dropped',"started_at=facts['started_at'],restarts=facts['restarts'],health","started_at=facts['started_at'],restarts=None,health")
add('O33_mounts_without_a_reader',"    def mounts(self):\n        need(self.reader is not None,'READER_CONTAINER_ABSENT')\n","    def mounts(self):\n")
add('O34_mounts_unseen',"        findings=[] if found==expected else ['READER_MOUNTS_NOT_THE_FIVE_READ_ONLY_BINDS']","        findings=[]",finding='READER_MOUNTS_NOT_THE_FIVE_READ_ONLY_BINDS')
add('O35_writable_unseen',"        if [mount for mount in found if mount['rw']]:findings.append('READER_MOUNT_WRITABLE')\n","",finding='READER_MOUNT_WRITABLE')
add('O36_expected_mounts_writable',"[{'type':'bind','source':source,'destination':target,'rw':False} for source,target in","[{'type':'bind','source':source,'destination':target,'rw':True} for source,target in")
add('O37_expected_mounts_any_type',"[{'type':'bind','source':source,","[{'type':'volume','source':source,")
add('O38_mounts_shape_any',"    need(type(value) is list and len(value)<=MAX_READER_MOUNTS,'MOUNTS_INVALID');out=[]","    out=[]",refusal='MOUNTS_INVALID')
add('O39_mount_entry_any',"and type(mount.get('RW')) is bool,'MOUNTS_INVALID')","and True,'MOUNTS_INVALID')")
add('O40_mount_source_any',"type(mount.get('Source')) is str and type(mount.get('Destination')) is str","type(mount.get('Destination')) is str")
add('O41_mount_count_dropped',"        return item_of(findings,mounts=found,count=len(found),","        return item_of(findings,mounts=found,count=5,")
add('O42_command_without_a_reader',"    def command(self):\n        need(self.reader is not None,'READER_CONTAINER_ABSENT')\n","    def command(self):\n")
add('O43_command_shape_any',"        need(set(value)=={'id','path','args','init','read_only','user'} and value['id']==self.reader['id'],'CONTAINER_COMMAND_INVALID')\n","",
    refusal='CONTAINER_COMMAND_INVALID')
add('O44_command_unseen',"        if words!=[READER_PATH]+list(READER_ARGS):findings.append('READER_COMMAND_NOT_THE_LAUNCHER')\n","",finding='READER_COMMAND_NOT_THE_LAUNCHER')
add('O45_init_unseen',"        if value['init'] is not True:findings.append('READER_WITHOUT_INIT')\n","",finding='READER_WITHOUT_INIT')
add('O46_init_truthy',"        if value['init'] is not True:findings","        if not value['init'] and value['init'] is not None:findings")
add('O47_read_only_unseen',"        if value['read_only'] is not True:findings.append('READER_ROOT_NOT_READ_ONLY')\n","",finding='READER_ROOT_NOT_READ_ONLY')
add('O48_user_unseen',"        if value['user']!=READER_USER:findings.append('READER_NOT_UID_0')\n","",finding='READER_NOT_UID_0')
add('O49_launcher_flag_true',"        return item_of(findings,launcher_command=words==[READER_PATH]+list(READER_ARGS),","        return item_of(findings,launcher_command=True,")
add('O50_command_words_any',"    need(type(value.get('path')) is str and (value.get('args') is None or (type(value['args']) is list and len(value['args'])<=MAX_COMMAND_WORDS",
    "    need((value.get('args') is None or (type(value['args']) is list and len(value['args'])<=MAX_COMMAND_WORDS")
add('O51_command_words_unbounded',"len(value['args'])<=MAX_COMMAND_WORDS\n","True\n")
add('O52_command_word_types_any',"                                                                         and all(type(word) is str for word in value['args']))),'CONTAINER_COMMAND_INVALID')",
    "                                                                         )),'CONTAINER_COMMAND_INVALID')")
add('O53_scan_without_listing',"        need(self.containers is not None,'CONTAINER_LIST_UNAVAILABLE')\n","",refusal='CONTAINER_LIST_UNAVAILABLE')
add('O54_scan_exited_too',"            if row['state'] not in SCAN_STATES or row['name']==READER_CONTAINER:continue","            if row['name']==READER_CONTAINER:continue")
add('O55_scan_includes_the_reader',"            if row['state'] not in SCAN_STATES or row['name']==READER_CONTAINER:continue","            if row['state'] not in SCAN_STATES:continue")
add('O56_scan_shape_any',"            need(set(value)=={'id','path','args'} and value['id']==row['id'],'CONTAINER_COMMAND_INVALID')\n","")
add('O57_others_unseen',"        return item_of(['READER_PROCESS_ELSEWHERE'] if [row for row in rows if row['reader_like']] else [],","        return item_of([],",finding='READER_PROCESS_ELSEWHERE')
add('O58_capacity_day_is_a_reader',"for marker in READER_MARKERS) and not any(NOT_A_READER_MARKER in word for word in words)","for marker in READER_MARKERS)")
add('O59_marker_exact_word',"    return any(marker in word for word in words for marker in READER_MARKERS)","    return any(marker==word for word in words for marker in READER_MARKERS)")
add('O60_others_names_dropped',"                       reader_like=[row['name'] for row in rows if row['reader_like']])","                       reader_like=[])")

# ---------------------------------------------------------------- the run
add('X01_executor_not_checked',"        need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')","        pass",refusal='EXECUTOR_IDENTITY')
add('X02_boot_not_observed',"        observe('boot',reader.boot)\n","")
add('X03_service_not_observed',"        observe('service',reader.service)\n","")
add('X04_timer_not_observed',"        observe('timer',reader.timer)\n","")
add('X05_container_not_observed',"            observe('container',reader.container)\n","")
add('X06_mounts_not_observed',"            observe('mounts',reader.mounts)\n","")
add('X07_command_not_observed',"            observe('command',reader.command)\n","")
add('X08_others_not_observed',"        observe('other_readers',reader.others)\n","")
add('X09_live_items_in_stopped',"        if live:\n            observe('container',reader.container)","        if True:\n            observe('container',reader.container)")
add('X10_expiry_not_a_stop',"        if found.get('status')=='UNAVAILABLE' and found.get('code') in EXPIRED_CODES:raise Refused(found['code'])\n","")
add('X11_incomplete_is_complete',"        elif incomplete:status,outcome,code=","        elif False:status,outcome,code=")
add('X12_findings_are_complete',"        elif findings:status,outcome,code=PARTIAL_STATUS,MISMATCH_OUTCOME,findings[0]\n","")
add('X13_stop_ignored',"        if stop is not None:status,outcome,code=PARTIAL_STATUS,PARTIAL_OUTCOME,stop\n        elif","        if False:pass\n        elif")
add('X14_success_is_live_always',"        else:status,outcome,code=COMPLETE_STATUS,success_of(plan),None","        else:status,outcome,code=COMPLETE_STATUS,COMPLETE_OUTCOME,None")
add('X15_refusal_after_an_observation',"        if not items:\n            return seal(envelope(REFUSED_STATUS","        if True:\n            return seal(envelope(REFUSED_STATUS")
add('X17_expectations_met_always',"expectations_met=status==COMPLETE_STATUS,writes=0,","expectations_met=True,writes=0,")
add('X18_reduction_dropped',"REDUCTIONS=[('ITEMS_REDUCED_TO_STATUS',_reduce_items)]","REDUCTIONS=[]")
add('X19_reduction_keeps_nothing',"    receipt['items']={name:{key:item.get(key) for key in ('status','findings','code')}","    receipt['items']={name:{key:item.get(key) for key in ('status',)}")
add('X20_listing_count_dropped',"        return item_of(findings,containers=len(self.containers),","        return item_of(findings,containers=0,")

# ---------------------------------------------------------------- revision 2: Codex decision 6
add('D01_source_root_elsewhere',"SOURCE_ROOT='/var/lib/c3po/r2d2-v2-source-20261005'","SOURCE_ROOT='/mnt/day-d-data/r2d2-v2-source-20261005'")
add('D02_source_target_any',"SOURCE_TARGET='/c3po-[a-z0-9][a-z0-9-]*'","SOURCE_TARGET='/[A-Za-z0-9._/-]+'")
add('D03_source_target_may_be_taken',"    need(text(plan['source_target'],SOURCE_TARGET) and plan['source_target'] not in [target for _,target in READER_BINDS],'SOURCE_TARGET_INVALID')",
    "    need(text(plan['source_target'],SOURCE_TARGET),'SOURCE_TARGET_INVALID')")
add('D04_source_target_not_checked',"    need(text(plan['source_target'],SOURCE_TARGET) and plan['source_target'] not in [target for _,target in READER_BINDS],'SOURCE_TARGET_INVALID')\n","",
    refusal='SOURCE_TARGET_INVALID')
add('D05_source_bind_not_expected',"for source,target in READER_BINDS+((SOURCE_ROOT,self.plan['source_target']),)],","for source,target in READER_BINDS],")
add('D06_source_bind_at_any_target',"for source,target in READER_BINDS+((SOURCE_ROOT,self.plan['source_target']),)],","for source,target in READER_BINDS+((SOURCE_ROOT,'/c3po-source'),)],")
add('D07_data_volume_not_reported',"NOT_ROOT_CONTROLLED_SOURCES=('/mnt/day-d-data',)","NOT_ROOT_CONTROLLED_SOURCES=()")
add('D08_not_root_controlled_any_mount',"not_root_controlled_sources=[mount['source'] for mount in found if mount['source'] in NOT_ROOT_CONTROLLED_SOURCES])",
    "not_root_controlled_sources=list(NOT_ROOT_CONTROLLED_SOURCES))")
add('E14_source_bind_target',"'source_bind':{'source':SOURCE_ROOT,'target':plan['source_target']},","'source_bind':{'source':SOURCE_ROOT,'target':None},",effect=['source_bind.target','source_bind.source'])
add('E15_binds_not_root_controlled',"'binds_not_root_controlled':list(NOT_ROOT_CONTROLLED_SOURCES),\n","'binds_not_root_controlled':[],\n",effect='binds_not_root_controlled')

# ---------------------------------------------------------------- the dispatcher and the launcher: the core's rows apply unchanged
# (the demonstration read operation has the same date class, READ, and so the same date literal)
MUTANTS=M
CORE_ROWS_REPLACED=()
COMBOS={}
REDUNDANT={}
# Codes no mutant can reach, with the reason (coverage() accepts them):
EQUIVALENT={'OBSERVATION_FAILED':'the fallback of code_of() in perform(): only a Refused reaches that handler, and every Refused '
                                  'raised there carries a constant code (EXECUTOR_IDENTITY, GO_EXPIRED, CLOCK_REVERSED); a mutant '
                                  'code=str(error) was run on 2026-10-04 and survived, as it must'}


def _load(path):
    raw=Path(path).read_bytes();name='_hostops02_k13r_mutation_'+hashlib.sha256(raw).hexdigest()[:12]
    module=type(sys)(name);module.__dict__['__file__']='<assembled k13r_reader_liveness.py>';sys.modules[name]=module
    exec(compile(raw,module.__dict__['__file__'],'exec'),module.__dict__);return module

def _members(value,prefix=''):
    out=[]
    for key in sorted(value):
        if type(value[key]) is dict:out+=_members(value[key],prefix+key+'.')
        else:out.append(prefix+key)
    return out

def codes_of(text):
    """The last argument of each need(), Refused() and code_of() of the operation part."""
    found=set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in ('need','Refused','code_of'):
            for argument in node.args[-1:]:
                for item in ast.walk(argument):
                    if isinstance(item,ast.Constant) and type(item.value) is str and re.fullmatch('[A-Z][A-Z0-9_]{2,79}',item.value):found.add(item.value)
    return found

def findings_of(text):
    """Every finding the operation part can write: the constants appended to a findings list or given to item_of()."""
    return set(re.findall(r"(?:append\(|item_of\(\[|else \[)'([A-Z][A-Z0-9_]{2,79})'",text))

def coverage(here):
    here=Path(here);errors=[];names={row[0] for row in M};module=_load(here/'build'/'k13r_reader_liveness.py')
    wanted=set(_members(module.effects_of({'mode':'LIVE','image_id':'sha256:'+'d'*64,'evidence_boot_id_sha256':'a'*64,'source_target':'/c3po-source'})))
    for member in sorted(wanted):
        if EFFECTS.get(member) not in names:errors.append('effects member without a mutant: '+member)
    for member in EFFECTS:
        if member not in wanted:errors.append('mutant table names an effects member that does not exist: '+member)
    text=(here/'op.py').read_text()
    for table,codes,label in ((REFUSALS,codes_of(text),'refusal'),(FINDINGS,findings_of(text),'finding')):
        for code in sorted(codes):
            if table.get(code) not in names and code not in EQUIVALENT:errors.append('%s without a mutant: %s'%(label,code))
        for code in table:
            if code not in codes:errors.append('mutant table names a %s that does not exist: %s'%(label,code))
    return errors
