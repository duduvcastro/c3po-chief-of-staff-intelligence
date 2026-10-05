OPERATION='GO_WRITE_HOSTOPS02_SUPERVISOR_ACTIVATE_01'
PHASE='WRITE_SUPERVISOR_TIMER_ACTIVATION'
REQUEST_SCHEMA='WRITE_HOSTOPS02_SUPERVISOR_ACTIVATE_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_SUPERVISOR_ACTIVATE_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_SUPERVISOR_ACTIVATE_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_SUPERVISOR_ACTIVATE_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_SUPERVISOR_ACTIVATE_PLAN_V1'
SOURCE_NAME='supervisor_activate.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=True                       # systemctl enable --now and reset-failed (rule 8.2)
DATE_CLASS='WRITE_SESSIONS'                   # B11: Monday 05/10 to Thursday 08/10 evenings (A2 section 7)
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
# Operation (4), the readback in mode GATE (L6), and operation (3), the installation of the units (E3)
EVIDENCE_OPERATIONS=('GO_READONLY_SUPERVISOR_READBACK_01','GO_WRITE_UNITS_EXCLUSIVE_INSTALL_01')
MAX_GATE_SPAN_SECONDS=900
# Two signed modes of the same bytes, one GO each (core rule 9: a wait for a state is a later read under its own GO).
COMPLETE_OUTCOME='TIMER_ENABLED_ACTIVE_RESET_PENDING'                         # mode ACTIVATE
RESET_COMPLETE_OUTCOME='SERVICE_REFUSAL_78_SEEN_RESET_FAILED_VERIFIED'          # mode RESET
PARTIAL_OUTCOME='PARTIAL_ACTIVATION_REQUIRES_READBACK'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_ACTIVATION_REQUIRES_READBACK'
MODES=('ACTIVATE','RESET')
PLAN_KEYS=frozenset(('mode','unit_directory','units','supervisor_paths','expected_entries','image_id','retention_reference',
                     'invocation_id','evidence_boot_id_sha256'))
# RESET acts on one start only: the InvocationID of the refused start, copied from a read-only receipt of the same boot
# (the ACTIVATE readback or a later read), is signed; null in ACTIVATE (decision 3 of #429 5985748037).
INVOCATION_ID='[0-9a-f]{32}'

SERVICE_UNIT='c3po-massive.service'
TIMER_UNIT='c3po-massive.timer'
DOCKER_UNIT='docker.service'
UNIT_DIRECTORY='/etc/systemd/system'
UNIT_KEYS=frozenset(('name','sha256','bytes','device','inode'))
UNIT_NAMES={'service':SERVICE_UNIT,'timer':TIMER_UNIT}
MAX_UNIT_BYTES=65536
ENABLEMENT_LINK=UNIT_DIRECTORY+'/timers.target.wants/'+TIMER_UNIT
DROP_IN_DIRECTORIES=(UNIT_DIRECTORY+'/'+SERVICE_UNIT+'.d',UNIT_DIRECTORY+'/'+TIMER_UNIT+'.d')
SUPERVISOR_CONTAINER='c3po-massive'
# Placement A, as operation (2) created it and operation (4) read it back (L6, layout_paths)
SUPERVISOR_PATHS={'CONFIG':'/etc/c3po-bar','MANIFESTS':'/etc/c3po-bar/manifests','DOCKER_CLI':'/etc/c3po-bar/docker-cli',
                  'STATE':'/var/lib/c3po-bar/supervisor','JOURNAL':'/var/lib/c3po-bar/journal'}
TOKEN_NAME='token'
JOURNAL_ENTRIES=2                             # epoch.json and maintenance.lock, the catalog of operation (4b)
COUNTED=('JOURNAL','STATE','DOCKER_CLI')      # entry counts compared with the signed ones, before and after
MAX_COUNT=4096
# The session window of the supervisor README (operation 5, "Must not"): from 60 s before the XNYS open to the close,
# 09:29-16:00 New York = 13:29-20:00 UTC this week; B11 never 10:29-17:00 BRT on a session day. The GO window must lie
# wholly outside it, with a 30-minute margin before it: the start this run causes may hang in ExecStartPre (about
# 120 s a start, SUP) and must not reach 13:29 inside the window.
SESSION_DAYS=EPOCH_DAYS[3:8]
FORBIDDEN_FROM_UTC='12:59:00'
FORBIDDEN_UNTIL_UTC='20:00:00'
SERVICE_PROPERTIES=('Id','LoadState','ActiveState','SubState','Result','ExecMainCode','ExecMainStatus','NRestarts','InvocationID',
                    'UnitFileState','FragmentPath','DropInPaths')
TIMER_PROPERTIES=('Id','LoadState','ActiveState','SubState','Result','UnitFileState','FragmentPath','DropInPaths',
                  'NextElapseUSecRealtime','LastTriggerUSec')
DOCKER_PROPERTIES=('Id','LoadState','ActiveState','SubState','UnitFileState')
PROPERTY_VALUE='[A-Za-z0-9_./:@+ -]{0,512}'
REFUSAL_STATUS='78'                           # the supervisor's terminal refusal; RestartPreventExitStatus=78
AFTER_EFFECT_READ_SECONDS=4                   # what the reads after the one effect may take, kept beyond its class and reserve
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker'],'systemctl':['/usr/bin/systemctl','/bin/systemctl']}
def _properties_tail(properties):return [part for key in properties for part in ('-p',key)]
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'the signed image ID, then the signed retention reference','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          'show_service':command_row('systemctl',['show',SERVICE_UNIT],None,'QUICK','READ',tail=_properties_tail(SERVICE_PROPERTIES)),
          'show_timer':command_row('systemctl',['show',TIMER_UNIT],None,'QUICK','READ',tail=_properties_tail(TIMER_PROPERTIES)),
          'show_docker':command_row('systemctl',['show',DOCKER_UNIT],None,'QUICK','READ',tail=_properties_tail(DOCKER_PROPERTIES)),
          'enable':command_row('systemctl',['enable','--now',TIMER_UNIT],None,'SWITCH','EFFECT'),
          'reset_failed':command_row('systemctl',['reset-failed',SERVICE_UNIT],None,'SWITCH','EFFECT')}
EFFECT_OF_MODE={'ACTIVATE':'enable','RESET':'reset_failed'}
SCOPE_STATEMENT=('Supervisor operation (5) of ORDEM_EPOCA_03 (B11) in two signed modes of these bytes, one GO each. ACTIVATE: systemctl '
                 'enable --now c3po-massive.timer (the timer only; systemctl reloads the manager itself, so this is the reload the '
                 'installation left to operation 5), read back at once; the immediate start of c3po-massive.service that the timer '
                 'causes is not waited for. RESET: a later run that sees that very start (its signed InvocationID) ended in exit status 78 with no claim taken, then '
                 'systemctl reset-failed c3po-massive.service. Never inside the session window of a session day. Everything is looked '
                 'at before the one effect of a run; after it nothing refuses and it is read back. No file is written by this process, '
                 'no container is started by it, the service is never started or enabled directly, nothing is stopped, disabled or '
                 'removed, no secret is read, and nothing waits.')
SIDE_EFFECTS=['ACTIVATE, systemctl enable --now c3po-massive.timer: systemctl creates the link timers.target.wants/c3po-massive.timer, '
              'reloads the manager (every unit file: operation 3 left them installed and not reloaded) and starts the timer',
              'the timer carries OnBootSec=30s, so its start starts c3po-massive.service at once: that service (not this process) runs docker rm '
              'and docker image inspect, then one docker run of the supervisor, which outside the session window refuses before reading any '
              'file (one DATA_GAP line, exit 78, no claim, no token read, no connection) and uses one of the six starts of its 8 h interval',
              'RESET, systemctl reset-failed c3po-massive.service: the failed state and the start counter of the service are cleared',
              'without a RESET the service stays failed and the start it used falls out of its 8 h interval before the next 09:29 start',
              'systemctl show of a unit the manager has not loaded makes the manager load it from disk']
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'after_effect_reserve_seconds':AFTER_EFFECT_RESERVE_SECONDS,
       'modes':{mode:{'effect':COMMANDS[EFFECT_OF_MODE[mode]]['argv'],
                      'success':COMPLETE_OUTCOME if mode=='ACTIVATE' else RESET_COMPLETE_OUTCOME} for mode in MODES},
       'daemon_reload_owner':'OPERATION_5_ACTIVATION_GO: the reload systemctl enable makes',
       'units':{'service':SERVICE_UNIT,'timer':TIMER_UNIT,'directory':UNIT_DIRECTORY,'enablement_link':ENABLEMENT_LINK,
                'drop_in_directories':list(DROP_IN_DIRECTORIES)},
       'supervisor_paths':SUPERVISOR_PATHS,'token':SUPERVISOR_PATHS['CONFIG']+'/'+TOKEN_NAME,'supervisor_container':SUPERVISOR_CONTAINER,
       'journal_entries':JOURNAL_ENTRIES,'forbidden_utc':{'days':list(SESSION_DAYS),'from':FORBIDDEN_FROM_UTC,'until':FORBIDDEN_UNTIL_UTC},
       'properties':{'service':list(SERVICE_PROPERTIES),'timer':list(TIMER_PROPERTIES),'docker':list(DOCKER_PROPERTIES)},
       'refusal_exit_status':int(REFUSAL_STATUS),'after_effect_read_seconds':AFTER_EFFECT_READ_SECONDS,
       'file_contents_read':[BOOT_ID_PATH,'the two signed unit files'],
       'metadata_only':['the token file (lstat: type, owner, mode, links; never its content or its size)',
                        'the entry counts of the journal root, the claim root and the docker CLI directory (names never leave)'],
       'side_effects':SIDE_EFFECTS,
       'reset_binding':'RESET requires the signed InvocationID, failed/failed/exit-code, ExecMainCode=1, ExecMainStatus=78, NRestarts=0; a later start is a finding',
       'never':['a start, a restart or a retry of anything','a file opened for writing','mkdir','chmod','chown','rename','removal','systemctl start, stop, restart, disable or mask',
                'systemctl enable of the service','a systemctl verb other than show, enable --now of the timer and reset-failed of the service',
                'reset-failed without an observed exit status 78','a wait, a sleep or a poll','docker exec','docker run','compose','a shell','a pull',
                'the content or the size of the token','a network connection opened by this process','flock'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'unit_bytes':MAX_UNIT_BYTES,'entries_counted':MAX_COUNT}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner):
    """Everything this source can do to the host: the read primitives and the signed commands."""


def forbidden_intervals():
    return [(instant(day+'T'+FORBIDDEN_FROM_UTC+'+00:00'),instant(day+'T'+FORBIDDEN_UNTIL_UTC+'+00:00')) for day in SESSION_DAYS]

def outside_session_window(start,end):
    """True when [start, end) meets none of the forbidden intervals."""
    return all(end<=low or start>=high for low,high in forbidden_intervals())

def supervisor_rows(plan,key):return plan['supervisor_paths'][key]

def validate_plan(plan):
    need(type(plan['mode']) is str and plan['mode'] in MODES,'MODE_INVALID')
    need(plan['invocation_id'] is None if plan['mode']=='ACTIVATE' else text(plan['invocation_id'],INVOCATION_ID),'INVOCATION_ID_INVALID')
    window=plan['window'];start,end=instant(window['not_before']),instant(window['expires_at'])
    need(outside_session_window(start,end),'WINDOW_INSIDE_SESSION_WINDOW')
    need(type(plan['unit_directory']) is list,'CHAIN_ROW_INVALID')
    rows=validate_chain(plan['unit_directory'],UNIT_DIRECTORY)
    need(rows[-1]['uid']==0 and rows[-1]['gid']==0,'UNIT_DIRECTORY_NOT_ROOT')
    units=plan['units'];exact(units,('service','timer'),'UNITS_INVALID')
    for key,name in UNIT_NAMES.items():
        item=units[key]
        need(type(item) is dict and set(item)==set(UNIT_KEYS) and item['name']==name and hexpin(item['sha256'])
             and integer(item['bytes'],1,MAX_UNIT_BYTES) and integer(item['device']) and integer(item['inode'],1),'UNITS_INVALID')
    paths=plan['supervisor_paths'];exact(paths,tuple(SUPERVISOR_PATHS),'SUPERVISOR_PATHS_INVALID')
    for key,path in SUPERVISOR_PATHS.items():
        need(type(paths[key]) is list,'CHAIN_ROW_INVALID')
        leaf=validate_chain(paths[key],path)[-1]
        need((leaf['uid'],leaf['gid'],leaf['mode'])==(0,0,0o700),'SUPERVISOR_PATH_NOT_PRIVATE')
    expected=plan['expected_entries'];exact(expected,COUNTED,'EXPECTED_ENTRIES_INVALID')
    need(expected['JOURNAL']==JOURNAL_ENTRIES and type(expected['JOURNAL']) is int,'EXPECTED_ENTRIES_INVALID')
    need(integer(expected['STATE'],0,MAX_COUNT) and type(expected['DOCKER_CLI']) is int and expected['DOCKER_CLI']==0,'EXPECTED_ENTRIES_INVALID')
    need(text(plan['image_id'],IMAGE_ID),'IMAGE_PLAN_INVALID')
    need(text(plan['retention_reference'],REFERENCE) and ':' in plan['retention_reference'] and not text(plan['retention_reference'],'sha256:.*'),'IMAGE_PLAN_INVALID')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    mode=plan['mode'];activate=mode=='ACTIVATE'
    return {'operation':OPERATION,'mode':mode,'unit_directory':chain_effects(plan['unit_directory']),'units':plan['units'],
            'supervisor_paths':{key:chain_effects(rows) for key,rows in sorted(plan['supervisor_paths'].items())},
            'expected_entries':plan['expected_entries'],'image_id':plan['image_id'],'retention_reference':plan['retention_reference'],
            'command':COMMANDS[EFFECT_OF_MODE[mode]]['argv'],'reset_failed_only_after_exit_status':None if activate else int(REFUSAL_STATUS),
            'invocation_id':plan['invocation_id'],
            'forbidden_utc':{'days':list(SESSION_DAYS),'from':FORBIDDEN_FROM_UTC,'until':FORBIDDEN_UNTIL_UTC},
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],'activation':True,'daemon_reload':activate,
            'service_started_or_enabled_directly':False,'waits':False,'files_written_by_this_process':0,'containers_started_by_this_process':0}
def success_of(plan):return COMPLETE_OUTCOME if plan['mode']=='ACTIVATE' else RESET_COMPLETE_OUTCOME


def unit_show(commands,name,properties,unit):
    """The signed properties of one unit, as systemctl show prints them: each exactly once, values in a plain grammar."""
    raw=commands.output(name)
    need(re.fullmatch(rb'[ -~\n]*',raw) is not None,'PROPERTY_OUTPUT_INVALID');values={}
    for line in raw.decode('ascii').splitlines():
        if not line:continue
        key,separator,value=line.partition('=');need(separator=='=','PROPERTY_LINE_INVALID')
        if key in properties:
            need(key not in values and text(value,PROPERTY_VALUE),'PROPERTY_VALUE_INVALID');values[key]=value
    need(set(values)==set(properties),'PROPERTY_MISSING');need(values['Id']==unit,'UNIT_ID_MISMATCH')
    return values

def service_of(commands):return unit_show(commands,'show_service',SERVICE_PROPERTIES,SERVICE_UNIT)
def timer_of(commands):return unit_show(commands,'show_timer',TIMER_PROPERTIES,TIMER_UNIT)
def installed(values,unit):return values['FragmentPath']==UNIT_DIRECTORY+'/'+unit and values['DropInPaths']==''
def timer_off(values):return values['UnitFileState']=='disabled' and values['ActiveState']=='inactive'
def timer_on(values):return values['UnitFileState']=='enabled' and values['ActiveState']=='active' and values['NextElapseUSecRealtime'] not in ('','n/a')
def service_idle(values):return values['ActiveState']=='inactive' and values['SubState']=='dead' and values['Result']=='success'
def service_refused(values):
    """The terminal refusal of the immediate start: failed, by exit status 78, not restarted."""
    return (values['ActiveState'],values['SubState'],values['Result'],values['ExecMainCode'],values['ExecMainStatus'],values['NRestarts'])==(
        'failed','failed','exit-code','1',REFUSAL_STATUS,'0') and values['InvocationID']!=''
def service_pending_or_refused(values):
    """What the service may show right after the timer's start: not started yet, starting, running, or the refusal."""
    return service_refused(values) or (values['InvocationID']=='' and service_idle(values)) or (
        values['ActiveState'] in ('activating','active','deactivating') and values['SubState'] not in ('auto-restart','auto-restart-queued'))

def unit_file(host,directory,item,gate):
    """Bytes and identity of one installed unit file, compared with the signed ones (a unit file is not a secret)."""
    raw,info=read_regular(host,item['name'],directory.fd,gate,MAX_UNIT_BYTES)
    same=(sha(raw)==item['sha256'] and len(raw)==item['bytes'] and (info.st_dev,info.st_ino)==(item['device'],item['inode'])
          and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)==(0,0,0o644,1))
    return {'as_installed':same}

REDUCTIONS=[]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    mode=plan['mode'];activate=mode=='ACTIVATE';effect_name=EFFECT_OF_MODE[mode]
    commands=Commands(host,gate);held={};findings=[];precheck={};observed={};runs={}
    flags={'activation':False,'reload':False}
    def finish(status,outcome,code,phase):
        receipt=envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),clock=timing(begun,mark,clock,monotonic),
            commands_started=dict(commands.started),mutating_calls=state.counts(),mode=mode,precheck=precheck,observed=observed,runs=runs,
            findings=sorted(set(findings)),phase_reached=phase,activation_performed=flags['activation'],daemon_reload_performed=flags['reload'],
            files_written_by_this_process=0,containers_started_by_this_process=0))
        return seal(receipt)
    def count(key):return count_entries(host,held[key].fd,gate,MAX_COUNT)
    def supervisor_present():return bool([row for row in container_list(commands) if row['name']==SUPERVISOR_CONTAINER])
    try:
        # ---- everything is looked at before the one effect; a refusal here has changed nothing
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            now=clock();need(outside_session_window(now,now),'CLOCK_INSIDE_SESSION_WINDOW')
            held['UNITS']=Pinned(host,walk_pinned(host,plan['unit_directory'],gate,[]),rows=plan['unit_directory'])
            for key in ('service','timer'):
                precheck['unit_file_'+key]=unit_file(host,held['UNITS'],plan['units'][key],gate)
                need(precheck['unit_file_'+key]['as_installed'],'UNIT_FILE_NOT_AS_INSTALLED')
            for path in DROP_IN_DIRECTORIES:
                found=probe(host,path,gate);need(found.get('status')=='COMPLETE','UNIT_PATH_UNREADABLE')
                need(found['exists'] is False,'DROP_IN_PRESENT')
            found=probe(host,ENABLEMENT_LINK,gate);need(found.get('status')=='COMPLETE','UNIT_PATH_UNREADABLE')
            if activate:need(found['exists'] is False,'ENABLEMENT_LINK_PRESENT')
            else:need((found['exists'],found.get('type'))==(True,'symlink'),'ENABLEMENT_LINK_ABSENT')
            for key,path in SUPERVISOR_PATHS.items():
                held[key]=Pinned(host,walk_pinned(host,supervisor_rows(plan,key),gate,[]),rows=supervisor_rows(plan,key))
            entries={key:count(key) for key in COUNTED};precheck['entries']=entries
            need(entries=={key:plan['expected_entries'][key] for key in COUNTED},'SUPERVISOR_ENTRIES_NOT_AS_SIGNED')
            precheck['manifests']=count('MANIFESTS')
            try:token=host.lstat(TOKEN_NAME,held['CONFIG'].fd)
            except FileNotFoundError:raise Refused('TOKEN_ABSENT') from None
            precheck['token']={'type':kind(token.st_mode),'uid':token.st_uid,'gid':token.st_gid,'mode_octal':'%04o'%stat.S_IMODE(token.st_mode),'links':token.st_nlink}
            need((precheck['token']['type'],token.st_uid,token.st_gid,stat.S_IMODE(token.st_mode),token.st_nlink)==('file',0,0,0o600,1),'TOKEN_METADATA')
            image=image_facts(commands,plan['image_id']);need(image['id']==plan['image_id'],'IMAGE_ID_MISMATCH')
            tag=image_facts(commands,plan['retention_reference']);need(tag['id']==plan['image_id'],'RETENTION_TAG_ELSEWHERE')
            precheck['image']={'id_equal':True,'retention_tag_points_at_it':True,'revision_label':image['revision_label']}
            need(not supervisor_present(),'SUPERVISOR_CONTAINER_PRESENT')
            docker_unit=unit_show(commands,'show_docker',DOCKER_PROPERTIES,DOCKER_UNIT);observed['docker_before']=docker_unit
            need(docker_unit['ActiveState']=='active','DOCKER_SERVICE_NOT_ACTIVE')
            service=service_of(commands);timer=timer_of(commands);observed['service_before']=service;observed['timer_before']=timer
            need(timer['DropInPaths']=='' and service['DropInPaths']=='','DROP_IN_PRESENT')
            if activate:
                need(timer_off(timer),'TIMER_NOT_DISABLED_AND_INACTIVE')
                need(service_idle(service) and service['InvocationID']=='','SERVICE_NOT_IDLE')
                # the units as operation (3) installed them and operation (4) verified them: loaded from the installed fragment
                need(service['LoadState']=='loaded' and timer['LoadState']=='loaded','UNIT_LOAD_STATE')
                need(installed(service,SERVICE_UNIT) and installed(timer,TIMER_UNIT),'UNIT_NOT_THE_INSTALLED_FRAGMENT')
            else:
                need(timer_on(timer) and installed(timer,TIMER_UNIT) and timer['LoadState']=='loaded','TIMER_NOT_ENABLED_AND_ACTIVE')
                need(service_refused(service) and installed(service,SERVICE_UNIT) and service['LoadState']=='loaded','SERVICE_NOT_REFUSED_78')
                need(service['InvocationID']==plan['invocation_id'],'SERVICE_INVOCATION_NOT_THE_SIGNED_ONE')
            for handle in held.values():handle.verify(gate)
            # The last refusal (rule 4.2): the one effect needs its class and reserve, plus the reads after it.
            precheck['seconds_left_before_the_effect']=int(gate())
            need(gate()>=effects_budget(effect_name)+AFTER_EFFECT_READ_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,'PRECHECK')
        # ---- the one effect of this mode; from here on nothing refuses unless nothing has changed
        stop=None
        def read(action,key):
            """One read back after the effect. A failure (an expiry included) is that read's UNAVAILABLE, never an absence."""
            try:observed[key]=action();return observed[key]
            except Exception as error:
                observed[key]=safe(error);return None
        result=effect(state,commands,effect_name)
        runs[effect_name]={key:result[key] for key in ('started','returned','returncode','code')}
        if not result['started']:stop=result['code']
        elif activate:
            # enable --now: the link, the reload of the manager, the start of the timer; done only when show says so
            timer=read(lambda:timer_of(commands),'timer_after')
            if result['returned'] and result['returncode']==0 and timer is not None and timer_on(timer):
                state.done();flags['activation']=True;flags['reload']=True
            elif result['returned'] and timer is not None and timer_off(timer):state.fail();stop='ENABLE_FAILED_TIMER_UNCHANGED'
            else:
                if result['returned']:state.unknown()
                flags['activation']=None;flags['reload']=None;stop=result['code'] or 'ENABLE_NOT_VERIFIED'
        else:
            service=read(lambda:service_of(commands),'service_after')
            if result['returned'] and result['returncode']==0 and service is not None and service_idle(service):state.done()
            elif result['returned'] and service is not None and service_refused(service):state.fail();stop='RESET_FAILED_SERVICE_STILL_FAILED'
            else:
                if result['returned']:state.unknown()
                stop=result['code'] or 'RESET_NOT_VERIFIED'
        # ---- what the run leaves, read back whatever happened above (nothing of it refuses)
        after={}
        def readback():
            after['timer']=timer_of(commands);after['service']=service_of(commands)
            found=probe(host,ENABLEMENT_LINK,gate);after['enablement_link']={'exists':found.get('exists'),'type':found.get('type')}
            after['supervisor_container_present']=supervisor_present()
            after['entries']={key:count(key) for key in COUNTED}
            after['unit_files']={key:unit_file(host,held['UNITS'],plan['units'][key],gate)['as_installed'] for key in ('service','timer')}
            for handle in held.values():handle.verify(gate)
            return after
        done=read(readback,'readback')
        if done is None:findings.append('READBACK_INCOMPLETE')
        else:
            if after['entries']!=precheck['entries']:findings.append('SUPERVISOR_ENTRIES_CHANGED')
            if not all(after['unit_files'].values()):findings.append('UNIT_FILE_CHANGED')
            if stop is None:
                if not timer_on(after['timer']):findings.append('TIMER_NOT_ACTIVE_AFTER_RUN')
                if (after['enablement_link']['exists'],after['enablement_link']['type'])!=(True,'symlink'):findings.append('ENABLEMENT_LINK_ABSENT')
                if activate:
                    # the start the timer caused is not waited for; what it shows at this read is a fact, unless it already
                    # ended otherwise than in the refusal (a restart, an exit 0, another status)
                    if not service_pending_or_refused(after['service']):findings.append('SERVICE_START_NOT_A_REFUSAL')
                else:
                    if not service_idle(after['service']):findings.append('SERVICE_NOT_IDLE_AFTER_RESET')
                    if after['service']['InvocationID']!=plan['invocation_id']:findings.append('SERVICE_STARTED_AGAIN')
                    if after['supervisor_container_present']:findings.append('SUPERVISOR_CONTAINER_LEFT')
        if stop is None and not findings:return finish(COMPLETE_STATUS,success_of(plan),None,'EFFECTS')
        stop=stop or sorted(set(findings))[0]
        # REFUSED only while no mutating call succeeded and none is uncertain; otherwise the run is a partial.
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,'EFFECTS')
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,'EFFECTS')
    finally:
        for handle in held.values():
            try:handle.close()
            except Exception:pass
