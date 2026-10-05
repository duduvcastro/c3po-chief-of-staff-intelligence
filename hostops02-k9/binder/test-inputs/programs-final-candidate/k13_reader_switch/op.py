OPERATION='GO_WRITE_HOSTOPS02_K13_READER_SWITCH_01'
PHASE='WRITE_K13_READER_SWITCH'
REQUEST_SCHEMA='WRITE_HOSTOPS02_K13_READER_SWITCH_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_K13_READER_SWITCH_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_K13_READER_SWITCH_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_K13_READER_SWITCH_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_K13_READER_SWITCH_PLAN_V1'
SOURCE_NAME='k13_reader_switch.py'
WRITES_ALLOWED=True
# systemctl enable, start, reset-failed, disable and stop switch a unit: the rows that run them are EFFECT rows and the
# source must carry the flag (CORE.md rule 8.2). The receipt says what the run did (activation_performed,
# daemon_reload_performed).
ACTIVATION_ALLOWED=True
# M6 (Monday 05/10), M6-s (Tuesday to Friday), RST (any session day) and X1 (Friday 09/10 after the close) all fall on
# 10-05 ... 10-09 UTC: the class of the core that holds them is WRITE_SESSIONS (10-05 ... 10-10). The session days and
# the launch window are this source's own guard on top of it (READER_NOT_A_SESSION_DAY, READER_OUTSIDE_LAUNCH_WINDOW).
DATE_CLASS='WRITE_SESSIONS'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,)
MAX_GATE_SPAN_SECONDS=900
# The success outcome follows the signed mode (SUCCESS_IN_TEMPLATE=False in spec.py). COMPLETE_OUTCOME is ACTIVATE's.
COMPLETE_OUTCOME='RETURNED_REQUIRES_LIVENESS_READBACK'
RESTART_OUTCOME='RESTART_RETURNED_REQUIRES_LIVENESS_READBACK'
DEACTIVATE_OUTCOME='DEACTIVATED_REQUIRES_STOP_READBACK'
PARTIAL_OUTCOME='PARTIAL_SWITCH_STATE_REQUIRES_READBACK'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_SWITCH_STATE_REQUIRES_READBACK'
READER_MODES=('ACTIVATE','RESTART','DEACTIVATE')
MODE_OUTCOMES={'ACTIVATE':COMPLETE_OUTCOME,'RESTART':RESTART_OUTCOME,'DEACTIVATE':DEACTIVATE_OUTCOME}
PLAN_KEYS=frozenset(('mode','evidence_boot_id_sha256','unit_rows','config_rows','launcher_rows','journal_rows','release_rows','release',
                     'files','image_id','journal_free_floor_bytes','source_rows','capacity_rows'))
FILE_KEYS=('reader_service','reader_timer','reader_alert','producer_service','launcher','pins')
# What DEACTIVATE does not look at: null in its plan (anything else is refused, so a signer never signs a value that is
# not used). Revision 2 (review finding 7): stopping the reader is not blocked by the bytes of its unit files; the
# switch acts on the two unit names, and the states systemd reports for them are written in the receipt as read.
NOT_USED_BY_DEACTIVATE=('unit_rows','config_rows','launcher_rows','journal_rows','release_rows','release','files','image_id','journal_free_floor_bytes',
                        'source_rows','capacity_rows')

# ---- the reader of this epoch, as the reader README (installation candidate) and the installed producer unit fix it
READER_EPOCH='R2D2-V2-SHADOW-2026-10-05'
SESSION_DAYS=('2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09')
# New York is UTC-4 for the whole epoch (daylight time ends on 2026-11-01); none of the five sessions closes early.
# The launch window of README operation 4 is open - 6 h (03:30 New York) to the close (16:00 New York); a launch at
# or after 09:28:30 New York (the handover) is allowed and marked LATE. Seconds of the UTC day:
LAUNCH_FROM_SECONDS=7*3600+30*60
LAUNCH_UNTIL_SECONDS=20*3600
LATE_FROM_SECONDS=13*3600+28*60+30
UNIT_DIRECTORY='/etc/systemd/system'
SERVICE_UNIT='c3po-reader.service'
TIMER_UNIT='c3po-reader.timer'
ALERT_UNIT='c3po-reader-alert.service'
PRODUCER_UNIT='c3po-massive.service'
CONFIG_DIRECTORY='/etc/c3po-reader'
LAUNCHER_DIRECTORY=CONFIG_DIRECTORY+'/launcher'
LAUNCHER_NAME='reader_launcher.py'
PINS_NAME='pins.env'
SECRET_NAME='secret.env'
ACTIVATION_NAME='activation.env'
DOCKER_CLI_NAME='docker-cli'
ACTIVATION_PATH=CONFIG_DIRECTORY+'/'+ACTIVATION_NAME
# README, "Environment files" 3: constant bytes, two lines, each ended by one newline; not secret.
ACTIVATION_BYTES=b'C3PO_R2D2_V2_SHADOW_ENABLED=true\nC3PO_R2D2_V2_MASSIVE_BARS_ENABLED=true\n'
ACTIVATION_SHA256='2053f3f6f528ad7dc56d500666ac2cf48f79c3aadd3c98eb35b53ee92eff611b'
# The two journal values of the installed producer unit (e3-20261004-a): the host root on the root filesystem and its
# container path. The reader's journal bind is the producer's with ,readonly added.
JOURNAL_HOST_ROOT='/var/lib/c3po-bar/journal'
JOURNAL_CONTAINER_ROOT='/c3po-bar-journal'
CATALOG_SCHEMA_NAME='MASSIVE_SESSION_ROOT_V1'
EPOCH_FILE_NAME='epoch.json'
CATALOG_LOCK_NAME='maintenance.lock'
DATA_VOLUME='/mnt/day-d-data'
DATA_TARGET='/app/day-d-data'
CAPACITY_ROOT='/var/lib/c3po-capacity'
CAPACITY_TARGET='/c3po-capacity'
LAUNCHER_TARGET='/c3po-reader'
# Codex decision 6 (W/codex-six-design-decisions-20261004.txt item 6): every docker bind source and all its ancestors
# root-controlled. The epoch's source root moved under /var/lib/c3po and the reader binds it read-only at a top-level
# target named in pins.env (C3PO_R2D2_V2_SHADOW_SOURCE_DIR, K4 PINS): a fifth bind. The data volume bind (uid 1000)
# for the release file does NOT meet decision 6: it is read and reported (binds_not_root_controlled), not accepted
# silently and not refused here (moving the release is K10's and the signers' decision).
SOURCE_ROOT='/var/lib/c3po/r2d2-v2-source-20261005'
SOURCE_TARGET='/c3po-[a-z0-9][a-z0-9-]*'
SOURCE_TARGETS_TAKEN=(CAPACITY_TARGET,LAUNCHER_TARGET,JOURNAL_CONTAINER_ROOT)
READER_CONTAINER='c3po-reader'
PRODUCER_FLOOR_BYTES=53687091200
# README operation 4: the signed floor is at least the producer's floor plus this for each session still to be retained
# (from the signed day to the last session, that day included: 56,706,990,080 bytes on 10-05), plus the GO's allowance.
SESSION_RETENTION_BYTES=603979776
MAX_UNIT_FILE_BYTES=65536
MAX_LAUNCHER_BYTES=65536
MAX_PINS_BYTES=4096
MAX_RELEASE_BYTES=1048576
MAX_EPOCH_FILE_BYTES=4096
MAX_COMMAND_WORDS=256
# pins.env, README "Environment files" 2, with L1: exactly these names, in this order.
PINS_NAMES=('C3PO_BUILD_SHA','C3PO_R2D2_V2_SHADOW_RELEASE_FILE','C3PO_R2D2_V2_SHADOW_RELEASE_SHA','C3PO_R2D2_V2_SHADOW_SOURCE_DIR',
            'C3PO_R2D2_MICROSTRUCTURE_RAW_DIR','C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR','C3PO_R2D2_V2_CAPACITY_REQUIRED','C3PO_R2D2_V2_CAPACITY_VETO_MODE',
            'C3PO_R2D2_V2_CAPACITY_CONFIG_FILE','C3PO_R2D2_V2_CAPACITY_CONFIG_SHA','C3PO_R2D2_V2_SHADOW_POLL_SECONDS','C3PO_READER_LAUNCHER_SHA256')
PINS_VALUE='[A-Za-z0-9._=/:-]{1,200}'
# A process is a reader when a word of its command names the worker module or the launcher; a capacity-day process is not.
READER_MARKERS=('app.r2d2_v2_shadow_worker','reader_launcher.py')
NOT_A_READER_MARKER='--prepare-capacity-day'
SCAN_STATES=('running','paused','restarting')
# The main command of the reader container, as the installed unit runs it (docker-init is not the main process).
READER_COMMAND_WORDS=('python','-I','-B','/c3po-reader/reader_launcher.py')
ACTIVE_STATES=('active','activating','reloading')
STOPPED_STATES=('inactive','failed')
# Seconds that must be left, beyond the effects' own classes (effects_budget), when the first effect starts: the
# creation of activation.env (milliseconds) and nothing else runs between the first effect and the last.
SWITCH_FILE_ALLOWANCE_SECONDS=3
UNIT_PROPERTIES=('Id','LoadState','ActiveState','SubState','UnitFileState','FragmentPath','DropInPaths','NeedDaemonReload','Result')
# The fixed template of the process scan: identity, the main command (path and arguments) and the exec sessions of a
# container. Nothing of the environment. The words stay in memory: only booleans and counts leave.
CONTAINER_COMMAND_FORMAT='{"id":{{json .Id}},"path":{{json .Path}},"args":{{json .Args}},"exec_ids":{{json .ExecIDs}}}'
SECURITY_OPTIONS_FORMAT='{{json .SecurityOptions}}'

BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker'],'systemctl':['/usr/bin/systemctl','/bin/systemctl']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'the signed image ID','QUICK','READ'),
          'container':command_row('docker',['container','inspect','--format',CONTAINER_FORMAT],'the name c3po-reader','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          'container_command':command_row('docker',['container','inspect','--format',CONTAINER_COMMAND_FORMAT],'one container ID of the listing','QUICK','READ'),
          'engine_security':command_row('docker',['info','--format',SECURITY_OPTIONS_FORMAT],None,'QUICK','READ'),
          'service_state':command_row('systemctl',['show',SERVICE_UNIT],None,'QUICK','READ',tail=[part for key in UNIT_PROPERTIES for part in ('-p',key)]),
          'timer_state':command_row('systemctl',['show',TIMER_UNIT],None,'QUICK','READ',tail=[part for key in UNIT_PROPERTIES for part in ('-p',key)]),
          'timer_enabled':command_row('systemctl',['is-enabled',TIMER_UNIT],None,'QUICK','READ'),
          # enable --now and disable --now reload the manager and start or stop the timer: the class of the core for a
          # verb that reloads the manager (30 s). --no-block returns once the job is queued; reset-failed clears a state:
          # QUICK (8 s). A call killed by its limit leaves its effect unknown and the run PARTIAL (rule 4.1).
          'enable_now_timer':command_row('systemctl',['enable','--now',TIMER_UNIT],None,'SWITCH','EFFECT'),
          'start_service':command_row('systemctl',['start','--no-block',SERVICE_UNIT],None,'QUICK','EFFECT'),
          'reset_failed_service':command_row('systemctl',['reset-failed',SERVICE_UNIT],None,'QUICK','EFFECT'),
          'disable_now_timer':command_row('systemctl',['disable','--now',TIMER_UNIT],None,'SWITCH','EFFECT'),
          'stop_service':command_row('systemctl',['stop','--no-block',SERVICE_UNIT],None,'QUICK','EFFECT')}
MODE_EFFECTS={'ACTIVATE':('enable_now_timer','start_service'),'RESTART':('reset_failed_service','start_service'),
              'DEACTIVATE':('disable_now_timer','stop_service')}
RELOADING_ROWS=('enable_now_timer','disable_now_timer')

SCOPE_STATEMENT=('Switches the V2 shadow reader unit of epoch '+READER_EPOCH+' in the one mode the request signs. ACTIVATE: after '
                 'every guard is read (the session day and the launch window 07:30-20:00 UTC, the four unit files and the launcher and '
                 'pins.env by signed SHA-256, the shape of secret.env by metadata only, the release file, the journal root, its catalog '
                 'file, its device against the data volume, its free space, the engine security options, the pinned image, no other '
                 'reader container or process), creates '+ACTIVATION_PATH+' exclusively with its two constant lines (or accepts it when it '
                 'already holds exactly those bytes), then runs systemctl enable --now '+TIMER_UNIT+' and systemctl start --no-block '
                 +SERVICE_UNIT+'. RESTART: the same guards with that file required, then systemctl reset-failed and systemctl start '
                 '--no-block of the service. DEACTIVATE: no file is read, then systemctl disable --now of the timer and systemctl '
                 'stop --no-block of the service. Every switch is read back in the run. Nothing is deleted, overwritten, renamed, '
                 'chmodded or chowned; secret.env is never opened; no environment value and no command line of a container is printed; '
                 'no container is run, executed into, stopped or removed by docker; no retry, no wait for a unit to settle.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,'epoch':READER_EPOCH,'modes':MODE_OUTCOMES,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'mode_effects':MODE_EFFECTS,
       'sessions':{'days':list(SESSION_DAYS),'launch_window_utc':['07:30:00','20:00:00'],'late_from_utc':'13:28:30',
                   'new_york':'UTC-4 for the whole epoch','applies_to':['ACTIVATE','RESTART']},
       'paths':{'unit_directory':UNIT_DIRECTORY,'units':[SERVICE_UNIT,TIMER_UNIT,ALERT_UNIT,PRODUCER_UNIT],'config_directory':CONFIG_DIRECTORY,
                'launcher':LAUNCHER_DIRECTORY+'/'+LAUNCHER_NAME,'pins':CONFIG_DIRECTORY+'/'+PINS_NAME,'secret':CONFIG_DIRECTORY+'/'+SECRET_NAME,
                'activation':ACTIVATION_PATH,'docker_cli':CONFIG_DIRECTORY+'/'+DOCKER_CLI_NAME,'journal_host_root':JOURNAL_HOST_ROOT,
                'journal_container_root':JOURNAL_CONTAINER_ROOT,'data_volume':DATA_VOLUME,'data_target':DATA_TARGET,
                'capacity_root':CAPACITY_ROOT,'capacity_target':CAPACITY_TARGET,'launcher_target':LAUNCHER_TARGET,'container':READER_CONTAINER,
                'source_root':SOURCE_ROOT,'source_target':SOURCE_TARGET,'source_targets_taken':list(SOURCE_TARGETS_TAKEN)},
       'codex_decision_6':'bind sources root-controlled; the data volume bind is reported as not meeting it (binds_not_root_controlled)',
       'activation_env':{'sha256':ACTIVATION_SHA256,'bytes':len(ACTIVATION_BYTES),'mode_octal':'0600','uid':0,'gid':0,'links':1,
                         'if_absent':'CREATE_EXCLUSIVE (ACTIVATE only)','if_present':'ACCEPTED ONLY WITH THE CONSTANT BYTES, 0:0, 0600, ONE LINK'},
       'pins_names':list(PINS_NAMES),'catalog':{'schema':CATALOG_SCHEMA_NAME,'files':[EPOCH_FILE_NAME,CATALOG_LOCK_NAME]},
       'unit_properties':list(UNIT_PROPERTIES),'reader_markers':list(READER_MARKERS),'not_a_reader_marker':NOT_A_READER_MARKER,
       'scan_states':list(SCAN_STATES),'reader_command':list(READER_COMMAND_WORDS),'producer_floor_bytes':PRODUCER_FLOOR_BYTES,
       'session_retention_bytes':SESSION_RETENTION_BYTES,'files':FILES_SCOPE,
       'secret_env':'lstat only: regular, 0:0, 0600, one link; never opened, read, hashed or sized',
       'file_contents_read':[BOOT_ID_PATH,'the four unit files','the launcher','pins.env','activation.env','the release file',
                             'epoch.json of the journal root'],
       'never':['docker run','docker exec','docker stop','docker rm','docker logs','daemon-reload of its own','a drop-in','overwrite','chmod',
                'chown','rename','truncate','removal of anything but the temporary of this run','secret.env opened','an environment value printed',
                'a container command line printed','a wait for a unit to settle','a retry','a shell'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'switch_file_allowance_seconds':SWITCH_FILE_ALLOWANCE_SECONDS,'unit_file_bytes':MAX_UNIT_FILE_BYTES,
                 'launcher_bytes':MAX_LAUNCHER_BYTES,'pins_bytes':MAX_PINS_BYTES,'release_bytes':MAX_RELEASE_BYTES,
                 'epoch_file_bytes':MAX_EPOCH_FILE_BYTES,'containers':MAX_CONTAINERS}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner,NativeFiles):
    """Everything this source can do to the host: the read primitives, the fixed commands, the creating calls."""


# ---------------------------------------------------------------- the plan (pure)
def root_controlled(row):
    """Beyond validate_chain without an open root (uid 0, no write bit for group or other): group 0 and no setgid."""
    return row['gid']==0 and not row['mode']&stat.S_ISGID

def private_directory_row(row):return (row['uid'],row['gid'],row['mode'])==(0,0,0o700)

def data_volume_row(rows):
    """The row of the data volume root in the signed chain of the release directory."""
    return [row for row in rows if row['path']==DATA_VOLUME][0]          # validate_plan proved it is a component of the chain

def validate_plan(plan):
    need(plan['mode'] in READER_MODES,'MODE_INVALID')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    if plan['mode']=='DEACTIVATE':
        need(all(plan[key] is None for key in NOT_USED_BY_DEACTIVATE),'PLAN_MEMBER_NOT_USED_BY_MODE')
        return
    validate_chain(plan['unit_rows'],UNIT_DIRECTORY)
    need(all(root_controlled(row) for row in plan['unit_rows']),'UNIT_CHAIN_NOT_ROOT_CONTROLLED')
    files=exact(plan['files'],FILE_KEYS,'FILE_PINS_INVALID')
    need(all(hexpin(files[key]) for key in FILE_KEYS),'FILE_PINS_INVALID')
    validate_chain(plan['config_rows'],CONFIG_DIRECTORY,receives_entry=True)
    need(all(root_controlled(row) for row in plan['config_rows']) and private_directory_row(plan['config_rows'][-1]),'CONFIG_DIRECTORY_NOT_PRIVATE')
    validate_chain(plan['launcher_rows'],LAUNCHER_DIRECTORY)
    need(plan['launcher_rows'][:-1]==plan['config_rows'] and private_directory_row(plan['launcher_rows'][-1]),'LAUNCHER_DIRECTORY_NOT_PRIVATE')
    validate_chain(plan['journal_rows'],JOURNAL_HOST_ROOT)
    need(all(root_controlled(row) for row in plan['journal_rows']) and private_directory_row(plan['journal_rows'][-1]),'JOURNAL_ROOT_NOT_PRIVATE')
    validate_chain(plan['source_rows'],SOURCE_ROOT)
    need(all(root_controlled(row) for row in plan['source_rows']) and private_directory_row(plan['source_rows'][-1]),'SOURCE_ROOT_NOT_PRIVATE')
    validate_chain(plan['capacity_rows'],CAPACITY_ROOT)
    need(all(root_controlled(row) for row in plan['capacity_rows']) and private_directory_row(plan['capacity_rows'][-1]),'CAPACITY_ROOT_NOT_PRIVATE')
    rows=plan['release_rows']
    need(type(rows) is list and rows and type(rows[-1]) is dict and type(rows[-1].get('path')) is str and clean_path(rows[-1]['path'])
         and inside(rows[-1]['path'],DATA_VOLUME) and rows[-1]['path']!=DATA_VOLUME,'RELEASE_NOT_IN_THE_DATA_VOLUME')
    validate_chain(rows,rows[-1]['path'],open_root=DATA_VOLUME)
    need(mount_point_of(rows[:len(prefixes(DATA_VOLUME))])==DATA_VOLUME,'DATA_VOLUME_NOT_A_MOUNT_POINT')
    need(plan['journal_rows'][-1]['device']!=data_volume_row(rows)['device'],'JOURNAL_ON_THE_DATA_VOLUME')
    release=exact(plan['release'],('name','sha256'),'RELEASE_PLAN_INVALID')
    need(text(release['name'],FILE_NAME) and hexpin(release['sha256']),'RELEASE_PLAN_INVALID')
    need(text(plan['image_id'],IMAGE_ID),'IMAGE_ID_INVALID')
    need(integer(plan['journal_free_floor_bytes'],floor_minimum(plan)),'FREE_FLOOR_BELOW_PRODUCER_FLOOR')

def floor_minimum(plan):
    """The producer's floor plus the retention of every session from the signed day on (the plan's window was proved a
    UTC instant of that day before validate_plan runs)."""
    day=instant(plan['window']['not_before']).date().isoformat()
    return PRODUCER_FLOOR_BYTES+SESSION_RETENTION_BYTES*len([item for item in SESSION_DAYS if item>=day])

def release_path_of(plan):return plan['release_rows'][-1]['path']+'/'+plan['release']['name']

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    mode=plan['mode'];files=plan['files'] or {}
    out={'operation':OPERATION,'epoch':READER_EPOCH,'mode':mode,'success_outcome':MODE_OUTCOMES[mode],
         'switches':[COMMANDS[name]['argv'] for name in MODE_EFFECTS[mode]],
         'activation_env':{'path':ACTIVATION_PATH,'sha256':ACTIVATION_SHA256,
                           'action':{'ACTIVATE':'CREATE_IF_ABSENT_ACCEPT_IF_CONSTANT','RESTART':'REQUIRED_CONSTANT','DEACTIVATE':'NOT_LOOKED_AT'}[mode]},
         'unit_names':[SERVICE_UNIT,TIMER_UNIT],
         'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],'files_deleted':False,'daemon_reload':'BY_ENABLE_OR_DISABLE_ONLY'}
    if mode=='DEACTIVATE':
        out.update(unit_directory=None,unit_files=None,bind_sources=None,launch_window=None,launcher=None,pins_sha256=None,journal=None,release=None,image_id=None);return out
    out.update(unit_directory=chain_effects(plan['unit_rows']),
               unit_files={SERVICE_UNIT:files['reader_service'],TIMER_UNIT:files['reader_timer'],ALERT_UNIT:files['reader_alert'],
                           PRODUCER_UNIT:files['producer_service']},
               launch_window={'days':list(SESSION_DAYS),'utc':['07:30:00','20:00:00'],'late_from_utc':'13:28:30'},
               launcher={'directory':chain_effects(plan['launcher_rows']),'sha256':files['launcher']},
               pins_sha256=files['pins'],
               journal={'root':chain_effects(plan['journal_rows']),'container_root':JOURNAL_CONTAINER_ROOT,
                        'free_floor_bytes':plan['journal_free_floor_bytes'],'data_volume_device':data_volume_row(plan['release_rows'])['device']},
               release={'path':release_path_of(plan),'sha256':plan['release']['sha256'],'directory':chain_effects(plan['release_rows'])},
               bind_sources={'source_root':chain_effects(plan['source_rows']),'capacity_root':chain_effects(plan['capacity_rows']),
                             'not_root_controlled':[DATA_VOLUME]},
               image_id=plan['image_id'])
    return out

def success_of(plan):return MODE_OUTCOMES[plan['mode']]


# ---------------------------------------------------------------- what is read
def launch_window(now):
    """The session day and the launch window (README operation 4): seconds of the UTC day, New York being UTC-4."""
    point=now.astimezone(timezone.utc);day=point.date().isoformat()
    need(day in SESSION_DAYS,'READER_NOT_A_SESSION_DAY')
    seconds=point.hour*3600+point.minute*60+point.second
    need(LAUNCH_FROM_SECONDS<=seconds<LAUNCH_UNTIL_SECONDS,'READER_OUTSIDE_LAUNCH_WINDOW')
    return {'session':day,'late':seconds>=LATE_FROM_SECONDS}

def entry_of(host,name,parent,gate):
    """One lstat of a plain name in a held, pinned directory; no link followed. None when the name does not exist."""
    gate()
    try:info=host.lstat(name,parent.fd)
    except FileNotFoundError:return None
    return info

def pinned_file(host,name,parent,gate,mode,limit,code):
    """A regular file of a held directory, root:root, the given mode, one link, read through a descriptor that must be
    the object the lstat saw. Returns its bytes. code is the refusal for every way it is not so."""
    info=entry_of(host,name,parent,gate)
    need(info is not None and stat.S_ISREG(info.st_mode) and info.st_size<=limit,code)
    try:raw,held=read_regular(host,name,parent.fd,gate,limit)
    except FileNotFoundError:raise Refused(code) from None
    need((held.st_dev,held.st_ino)==(info.st_dev,info.st_ino),code)
    need((held.st_uid,held.st_gid,stat.S_IMODE(held.st_mode),held.st_nlink)==(0,0,mode,1),code)
    return raw

def unit_values(commands,row,unit):
    """systemctl show of one unit: the properties of UNIT_PROPERTIES, each exactly once (any order)."""
    raw=commands.output(row)
    need(re.fullmatch(rb'[ -~\n]*',raw) is not None,'UNIT_PROPERTIES_INVALID');values={}
    for line in raw.decode('ascii').splitlines():
        if not line:continue
        key,separator,value=line.partition('=');need(separator=='=','UNIT_PROPERTIES_INVALID')
        if key in UNIT_PROPERTIES:
            need(key not in values and text(value,'[A-Za-z0-9_./:@+ -]{0,512}'),'UNIT_PROPERTIES_INVALID');values[key]=value
    need(set(values)==set(UNIT_PROPERTIES) and values['Id']==unit,'UNIT_PROPERTIES_INVALID')
    return values

def timer_enabled_word(commands):
    """systemctl is-enabled of the timer: the one word it prints. Its exit status (0 for enabled and for several other
    words, non-zero for disabled) adds nothing to the word and is not judged."""
    _,raw=commands.call('timer_enabled')
    need(re.fullmatch(rb'[a-z-]{1,32}\n?',raw) is not None,'TIMER_ENABLED_INVALID')
    return raw.decode('ascii').strip()

def unit_fit(values,unit):
    """The unit the manager has loaded is the installed file, with no drop-in."""
    need(values['LoadState']=='loaded','READER_UNIT_NOT_LOADED')
    need(values['FragmentPath']==UNIT_DIRECTORY+'/'+unit and values['DropInPaths']=='','READER_UNIT_NOT_THE_INSTALLED_FILE')

def engine_options(commands):
    """docker info SecurityOptions: true when neither user-namespace remapping nor rootless mode is named."""
    value=strict(commands.output('engine_security'))
    need(value is None or (type(value) is list and len(value)<=64 and all(type(item) is str and len(item)<=256 for item in value)),
         'ENGINE_SECURITY_OPTIONS_INVALID')
    need(not [item for item in value or [] if 'userns' in item.lower() or 'rootless' in item.lower()],'ENGINE_USERNS_OR_ROOTLESS')
    return {'options':len(value or []),'userns_or_rootless':False}

def reader_like(words):
    return any(marker in word for word in words for marker in READER_MARKERS) and not any(NOT_A_READER_MARKER in word for word in words)

def process_scan(commands,containers):
    """The main command of every container that can hold a process (README: a docker top of every running container;
    docker top is not a verb this core can run, see DESIGN.md). Booleans and counts only."""
    out=[]
    for row in containers:
        if row['state'] not in SCAN_STATES:continue
        value=decode(commands.output('container_command',row['id']))
        need(set(value)=={'id','path','args','exec_ids'} and value['id']==row['id'] and type(value['path']) is str
             and (value['args'] is None or (type(value['args']) is list and len(value['args'])<=MAX_COMMAND_WORDS and all(type(word) is str for word in value['args'])))
             and (value['exec_ids'] is None or (type(value['exec_ids']) is list and all(type(item) is str for item in value['exec_ids']))),
             'CONTAINER_COMMAND_INVALID')
        words=[value['path']]+list(value['args'] or [])
        out.append({'id':row['id'],'name':row['name'],'state':row['state'],'reader_like':reader_like(words),'launcher_command':words==list(READER_COMMAND_WORDS),
                    'exec_sessions':len(value['exec_ids'] or [])})
    return out

def pins_values(raw):
    """pins.env: ASCII, exactly the twelve names in order, one NAME=value per line, each ended by one newline."""
    need(type(raw) is bytes and re.fullmatch(rb'[ -~\n]*',raw) is not None and raw.endswith(b'\n'),'PINS_CONTENT_NOT_AS_SIGNED')
    lines=raw.decode('ascii').split('\n')[:-1]
    need(len(lines)==len(PINS_NAMES),'PINS_CONTENT_NOT_AS_SIGNED');values={}
    for line,name in zip(lines,PINS_NAMES):
        key,_,value=line.partition('=')            # a line with no '=' has an empty value, which the grammar refuses
        need(key==name and text(value,PINS_VALUE),'PINS_CONTENT_NOT_AS_SIGNED');values[key]=value
    return values

def unit_text_checks(service,producer,image_id,source_target):
    """The installed texts compared as text (README operation 4, parameters and mounts): the five read-only binds of
    the reader (README's four and the source root of decision 6), its image twice and no placeholder left; the
    producer's journal bind and argument, the same two values."""
    mounts=[(DATA_VOLUME,DATA_TARGET),(JOURNAL_HOST_ROOT,JOURNAL_CONTAINER_ROOT),(CAPACITY_ROOT,CAPACITY_TARGET),(LAUNCHER_DIRECTORY,LAUNCHER_TARGET),
            (SOURCE_ROOT,source_target)]
    need(all(service.count(('  --mount type=bind,source=%s,target=%s,readonly \\\n'%pair).encode('ascii'))==1 for pair in mounts)
         and service.count(b'--mount ')==len(mounts),'READER_UNIT_MOUNTS_NOT_AS_SIGNED')
    need(service.count(image_id.encode('ascii'))==2 and b'@' not in service,'READER_UNIT_IMAGE_NOT_THE_PIN')
    need(producer.count(('  --mount type=bind,source=%s,target=%s \\\n'%(JOURNAL_HOST_ROOT,JOURNAL_CONTAINER_ROOT)).encode('ascii'))==1
         and producer.count((' --journal-root %s '%JOURNAL_CONTAINER_ROOT).encode('ascii'))==1,'PRODUCER_UNIT_JOURNAL_NOT_AS_SIGNED')


# ---------------------------------------------------------------- settling a switch by its readback
# What each switch changes, as positions of (timer enabled word, timer ActiveState, service ActiveState): a failed switch
# proved nothing changed only when these read as before the run.
TARGET_WORD={'enable_now_timer':'enabled','disable_now_timer':'disabled'}
SETTLED_BY={'enable_now_timer':(0,1),'disable_now_timer':(0,1),'start_service':(2,),'reset_failed_service':(2,),'stop_service':(2,)}
def settle(state,name,result,before,after):
    """Exactly one of done / fail / unknown for a switch that started and returned, from what was read after it.
    before and after are (timer enabled word, timer ActiveState, service ActiveState); after is None when the readback
    failed. Returns the label written in the receipt."""
    if after is None:
        state.unknown();return 'UNKNOWN'
    word,timer,service=after
    reached={'enable_now_timer':word=='enabled' and timer=='active',
             'start_service':service in ('active','activating'),
             'reset_failed_service':result['returncode']==0 and service!='failed',
             'disable_now_timer':word=='disabled' and timer=='inactive',
             'stop_service':service not in ACTIVE_STATES}[name]
    if reached:
        state.done();return 'DONE'
    # enable --now and disable --now create or remove the symlinks, then reload the manager, then start or stop the
    # timer. When the word read before was already the target word, a failure may have come after the reload: nothing
    # read can prove that nothing changed (review finding 2).
    reloaded=name in TARGET_WORD and before[0]==TARGET_WORD[name]
    if result['returncode']!=0 and not reloaded and [after[index] for index in SETTLED_BY[name]]==[before[index] for index in SETTLED_BY[name]]:
        state.fail();return 'FAILED_NOTHING_CHANGED'
    state.unknown();return 'UNKNOWN'

def _reduce_scan(receipt):
    precheck=receipt.get('precheck') or {}
    if type(precheck.get('process_scan')) is list:precheck['process_scan']={'containers':len(precheck['process_scan']),
                                                                             'reader_like':sum(1 for row in precheck['process_scan'] if row.get('reader_like'))}
def _reduce_precheck(receipt):receipt['precheck']={'reduced_for_size':True}
REDUCTIONS=[('PROCESS_SCAN_REDUCED_TO_COUNTS',_reduce_scan),('PRECHECK_DROPPED',_reduce_precheck)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    mode=plan['mode'];switches=MODE_EFFECTS[mode];files=plan['files']        # pure: what will be compared and run
    gate()                                                                    # first gate call: before anything is observed
    state.started=True
    commands=Commands(host,gate);go16=bound['go_sha256'][:16]
    seen={'chains':{}};held=[];ledger=[];results={};after={}
    found={'activation_env':None,'window':None,'reconcile':False,'before':None}
    def finish(status,outcome,code,extra):
        labels=[item.get('settled') for item in results.values()]
        switched=True if 'DONE' in labels else (None if 'UNKNOWN' in labels else False)
        reloads=[results[name] for name in RELOADING_ROWS if name in results and results[name]['started']]
        reloaded=(True if [item for item in reloads if item.get('returncode')==0] else
                  None if [item for item in reloads if item['settled'] in ('UNKNOWN','DONE')] else False)
        changes=[item.get('changed') for item in results.values()]
        changed=True if True in changes else (None if None in changes else False)
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),mode=mode,effects=effects_of(plan),
            clock=timing(begun,mark,clock,monotonic),commands_started=dict(commands.started),mutating_calls=state.counts(),
            precheck=seen,activation_env=found['activation_env'],launch=found['window'],reconcile=found['reconcile'],
            ledger=ledger,switches=results,after=after,objects_left_by_this_run=objects_left([],ledger),
            binds_not_root_controlled=[] if mode=='DEACTIVATE' else [DATA_VOLUME],switches_changed_state=changed,activation_performed=switched,daemon_reload_performed=reloaded,files_deleted=False,**extra)))
    try:
        # ---- everything is looked at before the first effect
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o077)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            texts={}
            if mode!='DEACTIVATE':
                found['window']=launch_window(clock())
                units=Pinned(host,walk_pinned(host,plan['unit_rows'],gate,seen['chains'].setdefault('units',[])),rows=plan['unit_rows']);held.append(units)
                for key,unit in (('reader_service',SERVICE_UNIT),('reader_timer',TIMER_UNIT),('reader_alert',ALERT_UNIT),('producer_service',PRODUCER_UNIT)):
                    texts[key]=pinned_file(host,unit,units,gate,0o644,MAX_UNIT_FILE_BYTES,'UNIT_FILE_NOT_AS_SIGNED')
                    need(sha(texts[key])==files[key],'UNIT_FILE_NOT_AS_SIGNED')
                seen['unit_files']='EQUAL_TO_THE_SIGNED_HASHES'
            service=unit_values(commands,'service_state',SERVICE_UNIT);timer=unit_values(commands,'timer_state',TIMER_UNIT)
            word=timer_enabled_word(commands)
            seen['units']={'service':service,'timer':timer,'timer_enabled':word}
            if mode!='DEACTIVATE':
                unit_fit(service,SERVICE_UNIT);unit_fit(timer,TIMER_UNIT)
            found['before']=(word,timer['ActiveState'],service['ActiveState'])
            if mode!='DEACTIVATE':
                config=Pinned(host,walk_pinned(host,plan['config_rows'],gate,seen['chains'].setdefault('config',[])),rows=plan['config_rows']);held.append(config)
                launcher=Pinned(host,walk_pinned(host,plan['launcher_rows'],gate,seen['chains'].setdefault('launcher',[])),rows=plan['launcher_rows']);held.append(launcher)
                need(sha(pinned_file(host,LAUNCHER_NAME,launcher,gate,0o600,MAX_LAUNCHER_BYTES,'LAUNCHER_NOT_AS_SIGNED'))==files['launcher'],'LAUNCHER_NOT_AS_SIGNED')
                pins=pinned_file(host,PINS_NAME,config,gate,0o600,MAX_PINS_BYTES,'PINS_NOT_AS_SIGNED')
                need(sha(pins)==files['pins'],'PINS_NOT_AS_SIGNED')
                # secret.env: metadata only, never opened (its content cannot be signed; README asks for its shape)
                secret=entry_of(host,SECRET_NAME,config,gate)
                need(secret is not None and stat.S_ISREG(secret.st_mode) and (secret.st_uid,secret.st_gid,stat.S_IMODE(secret.st_mode),secret.st_nlink)==(0,0,0o600,1),
                     'SECRET_ENV_SHAPE')
                cli=entry_of(host,DOCKER_CLI_NAME,config,gate)
                need(cli is not None and stat.S_ISDIR(cli.st_mode) and (cli.st_uid,cli.st_gid,stat.S_IMODE(cli.st_mode))==(0,0,0o700),'DOCKER_CLI_DIRECTORY_NOT_PRIVATE')
                present=entry_of(host,ACTIVATION_NAME,config,gate)
                if present is None:found['activation_env']='ABSENT'
                else:
                    need(pinned_file(host,ACTIVATION_NAME,config,gate,0o600,len(ACTIVATION_BYTES),'ACTIVATION_ENV_NOT_THE_CONSTANT')==ACTIVATION_BYTES,
                         'ACTIVATION_ENV_NOT_THE_CONSTANT')
                    found['activation_env']='CONSTANT'
                need(mode=='ACTIVATE' or found['activation_env']=='CONSTANT','ACTIVATION_ENV_ABSENT')
                # the journal root: owner and mode by its signed rows, the catalog of this epoch bound to its identity
                journal=Pinned(host,walk_pinned(host,plan['journal_rows'],gate,seen['chains'].setdefault('journal',[])),rows=plan['journal_rows']);held.append(journal)
                expected=canonical({'schema':CATALOG_SCHEMA_NAME,'epoch':READER_EPOCH,'device':journal.identity[0],'inode':journal.identity[1]})
                need(pinned_file(host,EPOCH_FILE_NAME,journal,gate,0o600,MAX_EPOCH_FILE_BYTES,'CATALOG_FILE_NOT_PRIVATE')==expected,'CATALOG_NOT_THIS_EPOCH_AND_ROOT')
                lock=entry_of(host,CATALOG_LOCK_NAME,journal,gate)
                need(lock is not None and stat.S_ISREG(lock.st_mode) and (lock.st_uid,lock.st_gid,stat.S_IMODE(lock.st_mode),lock.st_nlink)==(0,0,0o600,1),
                     'CATALOG_FILE_NOT_PRIVATE')
                release=Pinned(host,walk_pinned(host,plan['release_rows'],gate,seen['chains'].setdefault('release',[])),rows=plan['release_rows']);held.append(release)
                # decision 6: the source root and the capacity tree, bind sources of the reader, walked by root-only chains
                held.append(Pinned(host,walk_pinned(host,plan['source_rows'],gate,seen['chains'].setdefault('source',[])),rows=plan['source_rows']))
                held.append(Pinned(host,walk_pinned(host,plan['capacity_rows'],gate,seen['chains'].setdefault('capacity',[])),rows=plan['capacity_rows']))
                # the journal's device differs from the data volume's: refused from the signed rows (validate_plan), and
                # both walks above held each directory equal to its signed row, device included
                free=free_bytes(host,journal.fd)
                seen['journal']={'device':journal.identity[0],'inode':journal.identity[1],'free_bytes':free,'catalog':'EPOCH_JSON_EQUAL','maintenance_lock':'PRIVATE'}
                need(free>=plan['journal_free_floor_bytes'],'JOURNAL_FREE_SPACE_BELOW_FLOOR')
                need(sha(pinned_file(host,plan['release']['name'],release,gate,0o600,MAX_RELEASE_BYTES,'RELEASE_NOT_AS_SIGNED'))==plan['release']['sha256'],
                     'RELEASE_NOT_AS_SIGNED')
                seen['files']={'launcher':files['launcher'],'pins':files['pins'],'release':plan['release']['sha256'],'secret_env':'SHAPE_ONLY_AS_REQUIRED',
                               'docker_cli':'PRIVATE_DIRECTORY','activation_env':found['activation_env']}
                seen['engine']=engine_options(commands)
                image=image_facts(commands,plan['image_id'])
                need(image['id']==plan['image_id'],'IMAGE_NOT_PRESENT')
                seen['image']={'id':image['id'],'revision_label':image['revision_label']}
                values=pins_values(pins)
                need(values['C3PO_R2D2_V2_SHADOW_RELEASE_FILE']==DATA_TARGET+release_path_of(plan)[len(DATA_VOLUME):]
                     and values['C3PO_R2D2_V2_SHADOW_RELEASE_SHA']==plan['release']['sha256']
                     and values['C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR']==JOURNAL_CONTAINER_ROOT
                     and values['C3PO_READER_LAUNCHER_SHA256']==files['launcher'],'PINS_CONTENT_NOT_AS_SIGNED')
                need(values['C3PO_BUILD_SHA']==image['revision_label'],'PINS_BUILD_SHA_NOT_THE_IMAGE_REVISION')
                target=values['C3PO_R2D2_V2_SHADOW_SOURCE_DIR']
                need(text(target,SOURCE_TARGET) and target not in SOURCE_TARGETS_TAKEN,'PINS_SOURCE_DIR_NOT_A_TOP_LEVEL_TARGET')
                unit_text_checks(texts['reader_service'],texts['producer_service'],plan['image_id'],target)
                containers=container_list(commands)
                scan=process_scan(commands,containers);seen['process_scan']=scan
                own=[row for row in containers if row['name']==READER_CONTAINER]
                active=service['ActiveState'] in ACTIVE_STATES
                if mode=='ACTIVATE' and found['activation_env']=='ABSENT':
                    need(word=='disabled' and timer['ActiveState']=='inactive','TIMER_ENABLED_BEFORE_ACTIVATION')
                    need(service['ActiveState'] in STOPPED_STATES,'SERVICE_ACTIVE_BEFORE_ACTIVATION')
                elif mode=='ACTIVATE':
                    need(service['ActiveState'] in STOPPED_STATES+ACTIVE_STATES,'SERVICE_STATE_UNEXPECTED')
                    found['reconcile']=True
                else:
                    need(word=='enabled','TIMER_NOT_ENABLED')
                    need(service['ActiveState'] in STOPPED_STATES,'SERVICE_NOT_STOPPED')
                    need(service['NeedDaemonReload']=='no','READER_UNIT_NEEDS_DAEMON_RELOAD')
                if mode=='ACTIVATE' and found['reconcile'] and active and own:
                    # the reader being reconciled: its own container, running the pinned image, and no reader elsewhere
                    facts=container_facts(commands,READER_CONTAINER,expected_name=READER_CONTAINER)
                    need(facts['id']==own[0]['id'],'READER_CONTAINER_CHANGED')
                    need(facts['running'] is True and facts['image_id']==plan['image_id'],'READER_CONTAINER_NOT_THE_PINNED_READER')
                    need([row['launcher_command'] for row in scan if row['id']==facts['id']]==[True],'READER_CONTAINER_NOT_THE_PINNED_READER')
                    need(service['NeedDaemonReload']=='no','READER_UNIT_NEEDS_DAEMON_RELOAD')
                    seen['reconciled_container']={'id':facts['id'],'started_at':facts['started_at'],'restarts':facts['restarts']}
                    need(not [row for row in scan if row['reader_like'] and row['name']!=READER_CONTAINER],'READER_PROCESS_FOUND')
                else:
                    need(not own,'READER_CONTAINER_PRESENT')
                    need(not [row for row in scan if row['reader_like']],'READER_PROCESS_FOUND')
            # the last refusal that costs nothing on the host: every switch of the mode fits, with the file allowance
            left=gate();seen['seconds_left_before_first_effect']=int(left)
            need(left>=effects_budget(*switches)+SWITCH_FILE_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})
        # ---- effects: from here on nothing refuses unless nothing has changed
        stop=None
        if mode=='ACTIVATE' and found['activation_env']=='ABSENT':
            row=create_file(0,'ACTIVATION_ENV',ACTIVATION_PATH,ACTIVATION_BYTES,0o600,config,host,gate,state,go16);ledger.append(row)
            if row['state']!='INSTALLED_DURABLE':stop=row['code'] or 'ACTIVATION_ENV_NOT_CREATED'
        for name in switches:
            if stop is not None:
                results[name]={'started':False,'settled':'NOT_ATTEMPTED'};continue          # 'changed' is set after the readback
            result=effect(state,commands,name)
            results[name]={'started':result['started'],'returned':result['returned'],'returncode':result['returncode'],'code':result['code'],
                           'settled':None if result['returned'] else ('NOT_STARTED' if not result['started'] else 'UNKNOWN')}
            if not result['started']:stop=result['code'] or 'SWITCH_NOT_STARTED'
            elif not result['returned']:stop=result['code'] or 'SWITCH_UNCERTAIN'
            elif result['returncode']!=0:stop='SWITCH_COMMAND_FAILED'
        # ---- readback inside the run: the unit states, then the file this run created or accepted
        read=None
        try:
            word=timer_enabled_word(commands);timer=unit_values(commands,'timer_state',TIMER_UNIT);service=unit_values(commands,'service_state',SERVICE_UNIT)
            read=(word,timer['ActiveState'],service['ActiveState'])
            after.update(timer_enabled=word,timer={key:timer[key] for key in ('ActiveState','SubState','UnitFileState')},
                         service={key:service[key] for key in ('ActiveState','SubState','Result')})
        except Exception as error:
            after['units']=safe(error)
            if stop is None:stop=code_of(error,'READBACK_UNAVAILABLE')
        for name,item in results.items():
            if item['settled'] is None:item['settled']=settle(state,name,item,found['before'],read)
            # what the switch changed, as read (README reconcile: "the starts then change nothing and the receipt says so")
            item['changed']=(False if not item['started'] else None if read is None or not item.get('returned') else
                             [read[index] for index in SETTLED_BY[name]]!=[found['before'][index] for index in SETTLED_BY[name]])
        if mode=='ACTIVATE':
            if ledger:
                failed=readback_file(ledger[0],ACTIVATION_BYTES,0o600,config,host,gate) if ledger[0]['state']=='INSTALLED_DURABLE' else None
                if failed is not None and stop is None:stop=failed
            elif found['activation_env']=='CONSTANT':
                try:
                    need(pinned_file(host,ACTIVATION_NAME,config,gate,0o600,len(ACTIVATION_BYTES),'ACTIVATION_ENV_CHANGED')==ACTIVATION_BYTES,'ACTIVATION_ENV_CHANGED')
                    after['activation_env']='CONSTANT'
                except Exception as error:
                    after['activation_env']=safe(error)
                    if stop is None:stop=code_of(error,'READBACK_UNAVAILABLE')
        if mode!='DEACTIVATE':
            # a fact, not a gate: with --no-block the container may not exist yet
            def container_after():
                rows=[row for row in container_list(commands) if row['name']==READER_CONTAINER]
                if not rows:return {'status':'COMPLETE','exists':False}
                facts=container_facts(commands,READER_CONTAINER,expected_name=READER_CONTAINER)
                return {'status':'COMPLETE','exists':True,'id':facts['id'],'state':facts['state'],'started_at':facts['started_at'],
                        'image_equal_the_pin':facts['image_id']==plan['image_id'],'restarts':facts['restarts']}
            after['container']=attempt(container_after)
        if stop is None and [name for name,item in results.items() if item['settled']!='DONE']:stop='SWITCH_NOT_READ_BACK_AS_DONE'
        extra={'phase_reached':'EFFECTS'}
        if stop is None:return finish(COMPLETE_STATUS,MODE_OUTCOMES[mode],None,extra)
        # REFUSED only while no call succeeded and none is uncertain; otherwise the run is a partial.
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)
    finally:
        for handle in held:
            try:handle.close()
            except Exception:pass
