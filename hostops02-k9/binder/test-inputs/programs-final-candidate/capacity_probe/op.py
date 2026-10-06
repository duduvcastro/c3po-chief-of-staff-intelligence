OPERATION='GO_READONLY_HOSTOPS02_CAPACITY_PROBE_01'
PHASE='READONLY_CAPACITY_PROBE'
REQUEST_SCHEMA='READONLY_HOSTOPS02_CAPACITY_PROBE_REQUEST_V1'
AUTHORITY_SCHEMA='READONLY_HOSTOPS02_CAPACITY_PROBE_AUTHORITY_V1'
GO_SCHEMA='READONLY_HOSTOPS02_CAPACITY_PROBE_GO_V1'
RECEIPT_SCHEMA='READONLY_HOSTOPS02_CAPACITY_PROBE_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_CAPACITY_PROBE_PLAN_V1'
SOURCE_NAME='capacity_probe.py'
# The core's naming rule: the containers this source starts write to no host path (read-only binds only), so their
# rows are of kind CONTAINER and the source is READ (CORE.md section 8, rule 1). That class says nothing about the
# signature: A2 rev 3, section 6-A, keeps A5 and B4c under the owner's individual signature by hash.
WRITES_ALLOWED=False
ACTIVATION_ALLOWED=False
DATE_CLASS='READ'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
# Per source, not per step: no operation is required by name (the boot of the evidence binds the rows). The receipt of
# the mount (K6b, GO_WRITE_HOSTOPS02_CAPACITY_SWITCH_01) is a signed member of the LOAD plan instead (an open question).
EVIDENCE_OPERATIONS=()
# A2 rev 3 lines 66 and 113: a read has the window of its own line, at most 3600 s, on one UTC day.
MAX_GATE_SPAN_SECONDS=3600
STEPS=('CALENDAR','IDENT','LOAD')
# A2 rev 3, section 6-A: A5 (CALENDAR and IDENT) Sunday 04/10 16:26-23:30Z and Monday 05/10 to Thursday 08/10
# 20:38-23:30Z; B4c (LOAD) "the same band, after B4", and B4 has Monday to Thursday 20:38-23:30Z only.
A5_BANDS=(('2026-10-04','16:26:00','23:30:00'),('2026-10-05','20:38:00','23:30:00'),('2026-10-06','20:38:00','23:30:00'),
          ('2026-10-07','20:38:00','23:30:00'),('2026-10-08','20:38:00','23:30:00'))
B4C_BANDS=(('2026-10-05','20:38:00','23:30:00'),('2026-10-06','20:38:00','23:30:00'),('2026-10-07','20:38:00','23:30:00'),
           ('2026-10-08','20:38:00','23:30:00'))
STEP_BANDS={'CALENDAR':A5_BANDS,'IDENT':A5_BANDS,'LOAD':B4C_BANDS}

# PROPOSED new A5 band only for Tuesday 06/10; it supplements, never merges with, the original evening band.
# It grants no authority: reviewed family, binder, exact amendment and each signed request remain independent gates.
A5_ADDITIONAL_BANDS=(('2026-10-06','11:26:00','15:30:00'),)
STEP_ADDITIONAL_BANDS={'CALENDAR':A5_ADDITIONAL_BANDS,'IDENT':A5_ADDITIONAL_BANDS,'LOAD':()}
ADDITIONAL_BAND_SOURCE='PROPOSED Tuesday 06/10 A5 CALENDAR and IDENT 08:26-12:30 BRT; exact amended authority required, not operational authorization'
BAND_SOURCE='A2 rev 3 (A2_AUTORIDADE_CINCO_SESSOES.md), section 6-A, rows A5 and B4c (B4c: the band of B4)'
CALENDAR_OUTCOME='CALENDAR_LINE_READ_IN_THE_IMAGE_AS_PINNED'
IDENT_OUTCOME='ROOT_IDENTITIES_READ_TWICE_EQUAL_TO_THE_HOST'
COMPLETE_OUTCOME='STATIC_CONFIG_LOADED_WITH_THE_WORKER_BIND'
NOT_AS_EXPECTED_OUTCOME='STEP_RAN_ANSWER_NOT_AS_EXPECTED'
WITH_FINDINGS_OUTCOME='STEP_RAN_EXPECTED_ANSWER_WITH_FINDINGS'
PARTIAL_OUTCOME='PARTIAL_STEP_RESULT_UNKNOWN'
REFUSED_OUTCOME='REFUSED_NO_CONTAINER_STARTED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STEP_NOT_COMPLETE'
ESCAPED_OUTCOME='PARTIAL_STATE_UNKNOWN_CONTAINER_MAY_REMAIN'
STEP_OUTCOMES={'CALENDAR':CALENDAR_OUTCOME,'IDENT':IDENT_OUTCOME,'LOAD':COMPLETE_OUTCOME}
PLAN_KEYS=frozenset(('step','image_id','image_revision','capacity','load','evidence_boot_id_sha256'))
# The release whose image is deployed for the epoch (main at dd4ec4bb), and what its code says of the epoch: EPOCH and
# DOCUMENT_ORDER_SHA of c3po/backend/app/r2d2_v2_epoch_assembler.py lines 9 and 12, and implementation_package_sha()
# computed from that tree (tests/test_static_pins.py reads all three from a tree of the release).
RELEASE_REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
EPOCH_NAME='R2D2-V2-SHADOW-2026-10-05'
PACKAGE_SHA='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'
DOCUMENT_ORDER='1a5253bf23f5006224b79527da06697646c34c6f5a3a4f820af5da2b13d7a118'
# The tree: bound at a top-level target, read-only (capacity-mount README, "What it is"); four private children.
CAPACITY_TARGET='/c3po-capacity'
CAPACITY_TARGET_NAME='c3po-capacity'
CAPACITY_CHILDREN=('config','documents','go','payload')
CAPACITY_ROOTS=('documents','go','payload')
PRIVATE_DIRECTORY=(0,0,0o700)
CAPACITY_ROOT_NAME='[a-z0-9][a-z0-9._-]{0,62}'
CONFIG_FILE=CAPACITY_TARGET+'/config/[A-Za-z0-9][A-Za-z0-9._-]{0,99}'
CONFIG_LIMIT=4*1024*1024                  # AnchoredRoot.read's limit
WORKER_NAME='c3po-r2d2-worker-1'
VETO_MODE='DISPATCH_AND_DERIVATION_ONLY'
MOUNT_OPERATION='GO_WRITE_HOSTOPS02_CAPACITY_SWITCH_01'
MAX_MOUNT_ROWS=32
MAX_ROOT_ENTRIES=64
# The worker's settings as the host .env gives them to it (env_file of the backend services; K6b writes the capacity
# block, K6a the release pin): read as booleans only, by the core's container_environment template.
ENV_RELEASE_SHA='C3PO_R2D2_V2_SHADOW_RELEASE_SHA'
ENV_MOUNT_SOURCE='C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE'
ENV_CONFIG_FILE='C3PO_R2D2_V2_CAPACITY_CONFIG_FILE'
ENV_CONFIG_SHA='C3PO_R2D2_V2_CAPACITY_CONFIG_SHA'
ENV_VETO_MODE='C3PO_R2D2_V2_CAPACITY_VETO_MODE'
ENV_REQUIRED='C3PO_R2D2_V2_CAPACITY_REQUIRED'
ENV_SETTINGS=(ENV_CONFIG_FILE,ENV_CONFIG_SHA,ENV_VETO_MODE,ENV_REQUIRED)   # each absent, or equal to the signed value
REQUIRED_TRUE='true'
STARTED_AT='([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:[.]([0-9]{1,9}))?Z'
MAX_NEW_CONTAINER_ROWS=8
CONTAINER_PREFIX='hostops02-probe-'
RUN_COMMAND=['python','-I','-B','-']
ALARM_STATUS=142                          # 128 + SIGALRM, as docker-init reports a child its alarm ended
SCRIPT_SECONDS={'IDENT':14,'LOAD':34}     # the alarm each own script arms first; CALENDAR carries none (verbatim bytes)
CLASS_NAME='[A-Z][A-Za-z0-9_]{0,79}'      # what a script prints for an exception: a constant code or a class name
# docker container inspect of the worker: its mounts as one JSON object, four members per mount, nothing else (no
# environment, no label). Only constructs the post-deploy family ran on this host: a variable declared before a range
# and assigned inside it, if, not, json.
MOUNTS_FORMAT=('{{ $first := true }}{"mounts":[{{ range .Mounts }}{{ if not $first }},{{ end }}{{ $first = false }}'
               '{"type":{{json .Type}},"source":{{json .Source}},"destination":{{json .Destination}},"rw":{{json .RW}}}{{ end }}]}')
# calendar-pin.py, byte for byte: the lines between the markers calendar-pin-script:begin and :end of
# c3po/deployment/capacity-day/README.documents.md (opsart), inside the python fence, each ended by a newline.
CALENDAR_SCRIPT=r'''import json, sys
APPLICATION_ROOT = '/app'
sys.path.insert(0, APPLICATION_ROOT)
try:
    from app.r2d2_v2_calendar import ShadowCalendar
    from app.r2d2_v2_capacity_authority import calendar_pin
    from app.r2d2_v2_earnings_package import implementation_package_sha
    from app.r2d2_v2_epoch_assembler import DOCUMENT_ORDER_SHA, EPOCH, SESSIONS
    calendar = ShadowCalendar()
    receipt = {'status': 'CALENDAR_PIN', 'epoch': EPOCH, 'calendar_version': calendar.version,
               'calendar_pin_sha': calendar_pin(calendar, {'authorized_sessions': list(SESSIONS)}),
               'package_sha': implementation_package_sha(), 'document_order_sha': DOCUMENT_ORDER_SHA}
except Exception as error:
    print(json.dumps({'status': 'CALENDAR_PIN_REFUSED', 'code': type(error).__name__}, sort_keys=True))
    raise SystemExit(1)
print(json.dumps(receipt, sort_keys=True))
'''
CALENDAR_SCRIPT_SHA256='5a6066ae2925453a0def335d8f8ac7e802e149b56cf9e61ea3fe8843fe582b5f'
CALENDAR_SCRIPT_BYTES=876
IDENT_SCRIPT=r'''import signal
signal.alarm(14)
import json, re, sys
# HOSTOPS02 capacity probe, step IDENT. The identities of the capacity roots as the release computes them
# (AnchoredRoot: every component from '/' opened without following a link, the leaf a directory of this uid closed to
# group and other), read under the read-only bind at /c3po-capacity. One JSON line; nothing is written.
APPLICATION_ROOT = '/app'
TARGET = '/c3po-capacity'
NAMES = ('config', 'documents', 'go', 'payload')
CODE = re.compile('[A-Z][A-Z0-9_]{0,79}')
sys.path.insert(0, APPLICATION_ROOT)


def finish(line, status):
    sys.stdout.write(json.dumps(line, sort_keys=True, separators=(',', ':')) + '\n')
    sys.stdout.flush()
    raise SystemExit(status)


def code_of(error):
    text = str(error)
    if type(error).__name__ == 'ShadowIntegrityError' and CODE.fullmatch(text):
        return text
    return type(error).__name__


try:
    from app.r2d2_v2_capacity_anchored import AnchoredRoot
    identities = {}
    for name in NAMES:
        root = AnchoredRoot(TARGET + '/' + name)
        try:
            identities[name] = root.identity
        finally:
            root.close()
except Exception as error:
    finish({'status': 'ROOT_IDENTITIES_REFUSED', 'code': code_of(error)}, 1)
finish({'status': 'ROOT_IDENTITIES', 'identities': identities}, 0)
'''
IDENT_SCRIPT_SHA256='0b8b12216903b698b29a970f9e257e6e5f16e417102a637fda539dfde10545d1'
IDENT_SCRIPT_BYTES=1330
LOAD_SCRIPT=r'''import signal
signal.alarm(34)
import hashlib, json, re, sys
# HOSTOPS02 capacity probe, step LOAD: the startup checks of the worker (capacity-mount README, step 2) in a fresh
# container with the worker's read-only bind. Settings and CapacityConfig of the release, the signed values passed as
# arguments (the last line of standard input, after this text); the config is opened read-only and nothing is written.
APPLICATION_ROOT = '/app'
VETO_MODE = 'DISPATCH_AND_DERIVATION_ONLY'
CODE = re.compile('[A-Z][A-Z0-9_]{0,79}')
sys.path.insert(0, APPLICATION_ROOT)


def finish(line, status):
    sys.stdout.write(json.dumps(line, sort_keys=True, separators=(',', ':')) + '\n')
    sys.stdout.flush()
    raise SystemExit(status)


def code_of(error):
    text = str(error)
    if type(error).__name__ == 'ShadowIntegrityError' and CODE.fullmatch(text):
        return text
    return type(error).__name__


def run(values):
    try:
        from app.config import Settings
        from app.r2d2_v2_capacity_bootstrap import CapacityConfig
        settings = Settings(r2d2_v2_capacity_required=True,
                            r2d2_v2_capacity_config_file=values['config_file'],
                            r2d2_v2_capacity_config_sha=values['config_sha256'],
                            r2d2_v2_capacity_veto_mode=VETO_MODE,
                            r2d2_v2_shadow_release_sha=values['release_sha'])
        config = CapacityConfig(settings)
    except Exception as error:
        finish({'status': 'CAPACITY_STARTUP_REFUSED', 'code': code_of(error)}, 1)
    try:
        line = {'status': 'CAPACITY_STARTUP_OK', 'roots': sorted(config.roots), 'veto_mode': config.veto_mode,
                'identities': {name: config.roots[name].identity for name in sorted(config.roots)},
                'config_sha256': hashlib.sha256(config.config_root.read(config.name)).hexdigest()}
    except Exception as error:
        config.close()
        finish({'status': 'CAPACITY_STARTUP_REFUSED', 'code': code_of(error)}, 1)
    config.close()
    finish(line, 0)
'''
LOAD_SCRIPT_SHA256='c3019efaf1d51fea5188af9860f093faba4eb830f19220e222bc80b8aeaba99c'
LOAD_SCRIPT_BYTES=2050
LOAD_CALL="run(json.loads('%s'))\n"         # the one line appended to the pinned LOAD script: the signed values as JSON
# The lines the scripts print, member by member. A line is copied into the receipt only when it meets its grammar.
CALENDAR_KEYS=frozenset(('status','epoch','calendar_version','calendar_pin_sha','package_sha','document_order_sha'))
CALENDAR_VERSION='[A-Za-z0-9][A-Za-z0-9.+_-]{0,39}'
EPOCH_TEXT='[A-Z0-9][A-Z0-9_-]{0,79}'
LOAD_KEYS=frozenset(('status','roots','veto_mode','identities','config_sha256'))
LOAD_ROOT_NAMES=('documents','go','payload','restore_revocation')
VETO_MODES=('CONTINUOUS','DISPATCH_AND_DERIVATION_ONLY')
REFUSED_LINE_STATUS={'CALENDAR':'CALENDAR_PIN_REFUSED','IDENT':'ROOT_IDENTITIES_REFUSED','LOAD':'CAPACITY_STARTUP_REFUSED'}
OK_LINE_STATUS={'CALENDAR':'CALENDAR_PIN','IDENT':'ROOT_IDENTITIES','LOAD':'CAPACITY_STARTUP_OK'}
REFUSED_CODES={'CALENDAR':'CALENDAR_PIN_REFUSED_IN_THE_IMAGE','IDENT':'ROOT_IDENTITIES_REFUSED_IN_THE_IMAGE','LOAD':'CAPACITY_STARTUP_REFUSED_IN_THE_IMAGE'}
# The rows: the core's reads, one more read of the worker's mounts, and one attached run per step (IDENT twice). IDENT
# runs in the short class so that both of its runs fit the payload's 60 s: 2 x 20 + 4 = 44 s must be left before the
# first; CALENDAR and LOAD import the application and take the long class (40 + 4 = 44 s).
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'the signed image ID','QUICK','READ'),
          'container':command_row('docker',['container','inspect','--format',CONTAINER_FORMAT],'the name c3po-r2d2-worker-1 (LOAD only)','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          'container_environment':command_row('docker',['container','inspect','--format'],'the presence and equality template of the six signed names, then the ID of the worker read by the precheck (LOAD only)','QUICK','READ'),
          'worker_mounts':command_row('docker',['container','inspect','--format',MOUNTS_FORMAT],'the ID of the worker read by the precheck (LOAD only)','QUICK','READ'),
          'calendar':command_row('docker',RUN_PREFIX,'--name hostops02-probe-calendar-<16 hex of the GO>, the signed image ID, python -I -B -; '
                                 'calendar-pin.py on standard input; no bind','RUN','CONTAINER',stdin=True),
          'ident':command_row('docker',RUN_PREFIX,'--name hostops02-probe-ident-<16 hex of the GO>-<1 or 2>, the read-only bind of the signed '
                              'capacity root at /c3po-capacity, the signed image ID, python -I -B -; the pinned IDENT script on standard input',
                              'RUN_SHORT','CONTAINER',stdin=True),
          'load':command_row('docker',RUN_PREFIX,'--name hostops02-probe-load-<16 hex of the GO>, the read-only bind of the signed capacity '
                             'root at /c3po-capacity, the signed image ID, python -I -B -; the pinned LOAD script and one line of the signed '
                             'values on standard input','RUN','CONTAINER',stdin=True)}
STEP_ROWS={'CALENDAR':('calendar',),'IDENT':('ident','ident'),'LOAD':('load',)}
SIGNATURE_REGIME=('individual, by the hash of its own request (A2 rev 3, section 6-A: A5 and B4c are IND); a container run, never '
                  'a read of any grid')
SCOPE_STATEMENT=('The capacity probe of epoch R2D2-V2-SHADOW-2026-10-05, one signed step per request (A2 rev 3, section 6-A). CALENDAR '
                 '(A5): one attached container of the signed image ID with no bind runs calendar-pin.py (sha256 5a6066ae...) and its '
                 'line must name the epoch, the package and the document order pinned here. IDENT (A5): the capacity tree is walked '
                 'from / by its signed parent rows and held; two containers, one after the other, each with the tree bound read-only '
                 'at /c3po-capacity, print the AnchoredRoot identities, which must agree and equal those computed from the device and '
                 'inode numbers read on the host. LOAD (B4c): the running worker c3po-r2d2-worker-1 is on the signed image with one '
                 'read-only bind of the signed tree at /c3po-capacity, the static config on the host has the signed hash, and one '
                 'fresh container with the same bind loads Settings and CapacityConfig with the signed config path, config hash and '
                 'release hash and must print CAPACITY_STARTUP_OK, the roots documents, go and payload and the veto mode '
                 'DISPATCH_AND_DERIVATION_ONLY. Every container: removed on exit, never a pull, an init process, uid 0, no network, '
                 'read-only root filesystem, no capability, no new privilege, no environment file, no DOCKER_CONFIG. Nothing on the '
                 'filesystem of the host is created, changed or removed; no unit is touched; no container is removed by this '
                 'process; a timeout stops the docker CLI, not the container. Its signature is individual by the hash of its request.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'after_effect_reserve_seconds':AFTER_EFFECT_RESERVE_SECONDS,
       'steps':{'CALENDAR':{'rows':list(STEP_ROWS['CALENDAR']),'success':CALENDAR_OUTCOME,'bands':[list(band) for band in A5_BANDS+A5_ADDITIONAL_BANDS]},
                'IDENT':{'rows':list(STEP_ROWS['IDENT']),'success':IDENT_OUTCOME,'bands':[list(band) for band in A5_BANDS+A5_ADDITIONAL_BANDS]},
                'LOAD':{'rows':list(STEP_ROWS['LOAD']),'success':COMPLETE_OUTCOME,'bands':[list(band) for band in B4C_BANDS]},
                'band_source':BAND_SOURCE,'additional_band_source':ADDITIONAL_BAND_SOURCE},
       'release':{'revision':RELEASE_REVISION,'epoch':EPOCH_NAME,'package_sha':PACKAGE_SHA,'document_order_sha':DOCUMENT_ORDER},
       'scripts':{'CALENDAR':{'sha256':CALENDAR_SCRIPT_SHA256,'bytes':CALENDAR_SCRIPT_BYTES,'carried_byte_for_byte':True,'alarm_seconds':None},
                  'IDENT':{'sha256':IDENT_SCRIPT_SHA256,'bytes':IDENT_SCRIPT_BYTES,'alarm_seconds':SCRIPT_SECONDS['IDENT']},
                  'LOAD':{'sha256':LOAD_SCRIPT_SHA256,'bytes':LOAD_SCRIPT_BYTES,'alarm_seconds':SCRIPT_SECONDS['LOAD'],
                          'appended_line':LOAD_CALL.strip()},
                  'command':RUN_COMMAND,'alarm_exit_status':ALARM_STATUS},
       'capacity':{'target':CAPACITY_TARGET,'children':list(CAPACITY_CHILDREN),'roots':list(CAPACITY_ROOTS),
                   'children_owner_mode':'root:root 0700','config_file':CONFIG_FILE,'config_limit_bytes':CONFIG_LIMIT},
       'worker':{'name':WORKER_NAME,'mounts_format':MOUNTS_FORMAT,'veto_mode':VETO_MODE,'mount_operation':MOUNT_OPERATION},
       'container':{'prefix':RUN_PREFIX,'names':CONTAINER_PREFIX+'<step>-<first 16 hex of the GO sha256>[-1|-2]','command':RUN_COMMAND,
                    'network':'none','environment_file':None,'docker_config':None},
       'signature':SIGNATURE_REGIME,
       'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'file_contents_read':[BOOT_ID_PATH,'the static config file of a LOAD plan, by descriptor under the held tree (hashed in memory)'],
       'side_effects':['one attached docker run --rm per container (CALENDAR and LOAD one, IDENT two, one after the other): the engine '
                       'creates the container under the name of the step and the GO and removes it when its process ends',
                       'IDENT and LOAD bind the signed capacity root read-only at /c3po-capacity: the container reads the tree; '
                       'nothing in it is written by this process or by the scripts',
                       'the IDENT and LOAD scripts arm an alarm as their first statement (14 s and 34 s) so that their process ends '
                       'before the class limit of the docker CLI; calendar-pin.py is carried byte for byte and arms none',
                       'the docker CLI runs with the fixed environment of the core and no DOCKER_CONFIG'],
       'never':['a writable bind, or a bind of anything but the signed capacity root','a network','docker exec','a shell','systemctl',
                'a pull','an image by tag','--privileged, a device or a capability','the removal of any container',
                'any write on the filesystem of the host','a value of an environment','an environment file'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'mount_rows':MAX_MOUNT_ROWS,'new_container_rows':MAX_NEW_CONTAINER_ROWS}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner):
    """Everything this source can do to the host: the read primitives and the signed commands."""


def pinned(script,digest,size):
    """The bytes of one pinned script, from the constant this source carries, compared with its pins."""
    raw=script.encode('ascii')
    need(len(raw)==size and sha(raw)==digest,'SCRIPT_NOT_THE_PINNED_HASH');return raw

def scripts():
    """The three pinned scripts, each checked."""
    return {'CALENDAR':pinned(CALENDAR_SCRIPT,CALENDAR_SCRIPT_SHA256,CALENDAR_SCRIPT_BYTES),
            'IDENT':pinned(IDENT_SCRIPT,IDENT_SCRIPT_SHA256,IDENT_SCRIPT_BYTES),
            'LOAD':pinned(LOAD_SCRIPT,LOAD_SCRIPT_SHA256,LOAD_SCRIPT_BYTES)}

def load_values(plan):
    load=plan['load'];return {'config_file':load['config_file'],'config_sha256':load['config_sha256'],'release_sha':load['release_sha']}

def stdin_of(plan):
    """What the container of the step gets on standard input: the pinned script; for LOAD one more line that passes
    the signed values as a JSON literal (paths and hashes of a fixed grammar: no quote, no backslash)."""
    raw=scripts()[plan['step']]
    if plan['step']!='LOAD':return raw
    literal=canonical(load_values(plan)).decode('ascii')
    need("'" not in literal and '\\' not in literal,'LOAD_VALUES_INVALID')
    return raw+(LOAD_CALL%literal).encode('ascii')

def container_names(plan,go16):
    """One name per container of the step: the prefix, the step, the first 16 hex of the GO (IDENT adds -1 and -2)."""
    base=CONTAINER_PREFIX+plan['step'].lower()+'-'+go16
    return [base+'-1',base+'-2'] if plan['step']=='IDENT' else [base]

def mounts_of(plan):
    """The one read-only bind of IDENT and LOAD: the signed capacity root at /c3po-capacity; none for CALENDAR."""
    if plan['step']=='CALENDAR':return []
    return [{'source':plan['capacity']['root_path'],'target':CAPACITY_TARGET,'read_only':True}]

def validate_window(window,step):
    """The signed window lies in one band of the step: its day, between its two instants (UTC)."""
    start,end=instant(window['not_before']),instant(window['expires_at'])
    day=start.date().isoformat()
    bands=[(begin,stop) for band_day,begin,stop in STEP_BANDS[step]+STEP_ADDITIONAL_BANDS[step] if band_day==day]
    need(bool(bands),'STEP_DAY_NOT_IN_SCOPE')
    # One complete band, not the union's envelope: a request cannot bridge the morning/evening gap.
    need(any(instant(day+'T'+begin+'+00:00')<=start and end<=instant(day+'T'+stop+'+00:00') for begin,stop in bands),
         'STEP_WINDOW_OUTSIDE_THE_BAND')

def validate_capacity(capacity):
    need(type(capacity) is dict and set(capacity)=={'root_path','parent_rows'},'CAPACITY_UNBOUND')
    path=capacity['root_path']
    need(text(path,MOUNT_PATH) and clean_path(path) and len(prefixes(path))>=3
         and text(PurePosixPath(path).name,CAPACITY_ROOT_NAME),'CAPACITY_ROOT_INVALID')
    validate_chain(capacity['parent_rows'],str(PurePosixPath(path).parent))

def validate_load(load):
    need(type(load) is dict and set(load)=={'config_file','config_sha256','release_sha','mount_receipt_sha256'},'LOAD_UNBOUND')
    need(text(load['config_file'],CONFIG_FILE),'CONFIG_FILE_INVALID')                 # one name, no '/': clean by its grammar
    need(hexpin(load['config_sha256']),'CONFIG_SHA_INVALID')
    need(hexpin(load['release_sha']),'RELEASE_SHA_INVALID')
    need(hexpin(load['mount_receipt_sha256']),'MOUNT_RECEIPT_UNBOUND')
    need(len({load['config_sha256'],load['release_sha'],load['mount_receipt_sha256']})==3,'LOAD_HASH_REUSED')

def validate_members(plan):
    """Every member of the plan but the step and the window: refused from the bytes, before any claim."""
    step=plan['step']
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    need(type(plan['image_revision']) is str and plan['image_revision']==RELEASE_REVISION,'IMAGE_REVISION_NOT_THE_RELEASE')
    if step=='CALENDAR':need(plan['capacity'] is None,'CAPACITY_NOT_OF_THE_STEP')
    else:validate_capacity(plan['capacity'])
    if step=='LOAD':validate_load(plan['load'])
    else:need(plan['load'] is None,'LOAD_NOT_OF_THE_STEP')
    for row,name in zip(STEP_ROWS[step],container_names(plan,'0'*16)):
        run_arguments(row,plan['image_id'],mounts_of(plan),RUN_COMMAND,name)
    stdin_of(plan)                       # checks the three pinned scripts, and the LOAD values

def validate_plan(plan):
    need(type(plan['step']) is str and plan['step'] in STEPS,'STEP_INVALID')
    validate_window(plan['window'],plan['step'])
    validate_members(plan)

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    step=plan['step'];raw=stdin_of(plan);capacity=plan['capacity'];load=plan['load']
    containers=[]
    for row,name in zip(STEP_ROWS[step],container_names(plan,'<first 16 hex of the GO sha256>')):
        containers.append({'name':name,'docker_arguments':COMMANDS[row]['argv']+['--name',name]+run_arguments(row,plan['image_id'],mounts_of(plan),RUN_COMMAND),
                           'binds':mounts_of(plan),'network':'none','environment_file':None,'docker_config_variable':None,
                           'standard_input':{'sha256':sha(raw),'bytes':len(raw),'pinned_script_sha256':sha(scripts()[step])},
                           'time_limit_seconds':COMMAND_CLASSES[COMMANDS[row]['class']]['seconds'],'alarm_seconds':SCRIPT_SECONDS.get(step),
                           'removed_by_the_engine':True})
    out={'operation':OPERATION,'step':step,'success_outcome':success_of(plan),
         'bands':[list(band) for band in STEP_BANDS[step]+STEP_ADDITIONAL_BANDS[step]],'band_source':BAND_SOURCE,
         'image':{'id':plan['image_id'],'revision':plan['image_revision'],'by_id_never_a_tag':True},
         'containers':containers,'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
         'signature':SIGNATURE_REGIME,'writes':0,'removes':[],'activation':False,'containers_run':len(containers)}
    if STEP_ADDITIONAL_BANDS[step]:out['additional_band_source']=ADDITIONAL_BAND_SOURCE
    out['capacity']=None if capacity is None else {'root_path':capacity['root_path'],'parents':chain_effects(capacity['parent_rows']),
                                                   'children':list(CAPACITY_CHILDREN),'children_owner_mode':'root:root 0700','target':CAPACITY_TARGET}
    out['load']=None if load is None else {'config_file':load['config_file'],'config_sha256':load['config_sha256'],'release_sha':load['release_sha'],
                                           'mount_receipt':{'operation':MOUNT_OPERATION,'receipt_sha256':load['mount_receipt_sha256']},
                                           'veto_mode':VETO_MODE,'worker':WORKER_NAME,
                                           'expected':{'status':'CAPACITY_STARTUP_OK','roots':list(CAPACITY_ROOTS),'veto_mode':VETO_MODE}}
    if step=='CALENDAR':out['expected_line']={'status':'CALENDAR_PIN','epoch':EPOCH_NAME,'package_sha':PACKAGE_SHA,'document_order_sha':DOCUMENT_ORDER}
    return out
def success_of(plan):return STEP_OUTCOMES[plan['step']]


# ---------------------------------------------------------------- the tree, held from "/"
def held_child(host,parent,name,gate,missing,not_directory):
    """A directory by name in a held parent, never through a link: lstat, open without following, fstat equal."""
    gate()
    try:named=host.lstat(name,parent.fd)
    except FileNotFoundError:raise Refused(missing) from None
    need(stat.S_ISDIR(named.st_mode),not_directory)
    gate();fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=parent.fd)
    try:
        info=host.fstat(fd)
        need((info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'CAPACITY_CHANGED_DURING_WALK')
        return Pinned(host,fd,parent=parent,name=name),info
    except BaseException:
        host.close(fd);raise

def private(info):return (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==PRIVATE_DIRECTORY

def root_identity(root,name,child):
    """AnchoredRoot's identity of /c3po-capacity/<name>, as the release computes it (r2d2_v2_store.digest of the list of
    [part, device, inode] of each component below '/'), from the numbers read on the host."""
    return sha(canonical([[CAPACITY_TARGET_NAME,root.st_dev,root.st_ino],[name,child.st_dev,child.st_ino]]))

def hold_tree(host,plan,gate,held):
    """The parents by their signed rows, the root and its four children; each held. Returns the report and the identities."""
    capacity=plan['capacity'];path=capacity['root_path']
    fd=walk_pinned(host,capacity['parent_rows'],gate,[])
    try:parents=Pinned(host,fd,rows=capacity['parent_rows'])
    except BaseException:
        host.close(fd);raise
    held.append(parents)
    root,info=held_child(host,parents,PurePosixPath(path).name,gate,'CAPACITY_ROOT_ABSENT','CAPACITY_ROOT_NOT_A_DIRECTORY');held.append(root)
    need(private(info),'CAPACITY_ROOT_NOT_PRIVATE')
    names=[]
    for name in host.names(root.fd):
        names.append(name);need(len(names)<=MAX_ROOT_ENTRIES,'CAPACITY_ROOT_ENTRY_LIMIT')
    others=sorted(name for name in names if name not in CAPACITY_CHILDREN)
    for name in others:                        # nothing but directories directly in the bound root (a socket or a file is never bound unseen)
        gate();need(stat.S_ISDIR(host.lstat(name,root.fd).st_mode),'CAPACITY_ROOT_ENTRY_NOT_A_DIRECTORY')
    children={};identities={}
    for name in CAPACITY_CHILDREN:
        child,found=held_child(host,root,name,gate,'CAPACITY_CHILD_ABSENT','CAPACITY_CHILD_NOT_A_DIRECTORY');held.append(child)
        need(private(found),'CAPACITY_CHILD_NOT_PRIVATE')
        children[name]={'device':found.st_dev,'inode':found.st_ino,'same_device_as_root':found.st_dev==info.st_dev}
        identities[name]=root_identity(info,name,found)
    report={'parents_as_signed':True,'root':{'device':info.st_dev,'inode':info.st_ino,'private':True,'other_directories':len(others),'ctime_ns':info.st_ctime_ns},
            'children':children,'identities':identities}
    return report,identities,{name:held[-len(CAPACITY_CHILDREN)+index] for index,name in enumerate(CAPACITY_CHILDREN)}

def config_file_facts(host,plan,config,gate):
    """The static config as the worker would read it, on the host: by name in the held config directory, regular, owned
    by root, one link, closed to group and other (AnchoredRoot.read's policy), its SHA-256 equal to the signed one."""
    name=PurePosixPath(plan['load']['config_file']).name
    try:raw,info=read_regular(host,name,config.fd,gate,CONFIG_LIMIT)
    except FileNotFoundError:raise Refused('CONFIG_FILE_ABSENT') from None
    except OSError:raise Refused('CONFIG_FILE_UNREADABLE') from None
    need(info.st_uid==0 and info.st_nlink==1 and not stat.S_IMODE(info.st_mode)&0o077,'CONFIG_FILE_NOT_PRIVATE')
    need(sha(raw)==plan['load']['config_sha256'],'CONFIG_FILE_HASH_MISMATCH')
    return {'regular':True,'private':True,'sha256_as_signed':True,'bytes':len(raw)}

def worker_mounts(commands,worker_id):
    """The mounts of the worker: type, source, destination and RW of each, nothing else."""
    try:row=decode(commands.output('worker_mounts',worker_id))
    except CommandFailed:raise Refused('WORKER_MOUNTS_UNREADABLE') from None
    need(set(row)=={'mounts'} and type(row['mounts']) is list and len(row['mounts'])<=MAX_MOUNT_ROWS,'WORKER_MOUNTS_INVALID')
    for item in row['mounts']:
        need(type(item) is dict and set(item)=={'type','source','destination','rw'} and type(item['type']) is str and type(item['source']) is str
             and type(item['destination']) is str and type(item['rw']) is bool,'WORKER_MOUNTS_INVALID')
    return row['mounts']

def worker_facts(commands,plan):
    """The running worker: on the signed image, exactly one mount at /c3po-capacity, a read-only bind of the signed root."""
    try:worker=container_facts(commands,WORKER_NAME,expected_name=WORKER_NAME)
    except CommandFailed:raise Refused('WORKER_ABSENT_OR_UNREADABLE') from None
    need(worker['running'] is True and worker['state']=='running','WORKER_NOT_RUNNING')
    need(worker['image_id']==plan['image_id'],'WORKER_NOT_ON_THE_SIGNED_IMAGE')
    mounts=worker_mounts(commands,worker['id'])
    at=[item for item in mounts if item['destination']==CAPACITY_TARGET]
    need(at,'WORKER_CAPACITY_MOUNT_ABSENT');need(len(at)==1,'WORKER_CAPACITY_MOUNT_NOT_ONE')
    need(at[0]['type']=='bind','WORKER_CAPACITY_MOUNT_NOT_A_BIND')
    need(at[0]['source']==plan['capacity']['root_path'],'WORKER_CAPACITY_MOUNT_OTHER_SOURCE')
    need(at[0]['rw'] is False,'WORKER_CAPACITY_MOUNT_WRITABLE')
    root=plan['capacity']['root_path']
    for item in mounts:
        if item is at[0]:continue
        need(not inside(item['destination'],CAPACITY_TARGET),'WORKER_MOUNT_INSIDE_THE_CAPACITY_TARGET')
        need(not (item['source'].startswith('/') and (inside(item['source'],root) or inside(root,item['source']))),'WORKER_OTHER_MOUNT_REACHES_THE_TREE')
    settings=worker_settings(commands,plan,worker['id'])
    return worker,{'id':worker['id'],'started_at':worker['started_at'],'restarts':worker['restarts'],'running':True,'image_as_signed':True,
                   'mounts':len(mounts),'capacity_mount':{'type':'bind','source_as_signed':True,'read_only':True},'other_mounts_clear_of_the_tree':True,
                   'settings':settings}

def worker_settings(commands,plan,worker_id):
    """The worker's environment against the signed values, as booleans: the release pin present and equal, the mount
    source present and equal to the signed root, each capacity setting absent or equal (REQUIRED true, the veto mode)."""
    load=plan['load']
    expected={ENV_RELEASE_SHA:load['release_sha'],ENV_MOUNT_SOURCE:plan['capacity']['root_path'],ENV_CONFIG_FILE:load['config_file'],
              ENV_CONFIG_SHA:load['config_sha256'],ENV_VETO_MODE:VETO_MODE,ENV_REQUIRED:REQUIRED_TRUE}
    try:found=container_environment(commands,worker_id,expected)
    except CommandFailed:raise Refused('WORKER_ENVIRONMENT_UNREADABLE') from None
    need(found[ENV_RELEASE_SHA]['present'] and found[ENV_RELEASE_SHA]['equal'],'WORKER_RELEASE_SHA_NOT_AS_SIGNED')
    need(found[ENV_MOUNT_SOURCE]['present'] and found[ENV_MOUNT_SOURCE]['equal'],'WORKER_MOUNT_SOURCE_NOT_AS_SIGNED')
    for name in ENV_SETTINGS:need(found[name]['equal'] or not found[name]['present'],'WORKER_CAPACITY_SETTING_NOT_AS_SIGNED')
    return found

def started_ns(value):
    """The engine's StartedAt (RFC 3339, UTC, up to nanoseconds) as nanoseconds since the epoch; None for any other text."""
    match=re.fullmatch(STARTED_AT,value) if type(value) is str else None
    if match is None:return None
    try:moment=datetime(*[int(item) for item in match.groups()[:6]],tzinfo=timezone.utc)
    except ValueError:return None
    return int(moment.timestamp())*10**9+int((match.group(7) or '').ljust(9,'0'))

def changed_after(ctime_ns,started):
    """Reported, never judged: whether the root of the tree changed (status change time) after the worker started."""
    begun=started_ns(started)
    return None if begun is None or type(ctime_ns) is not int else ctime_ns>begun


# ---------------------------------------------------------------- the lines the scripts print
def line_grammar(step,row):
    """True when the printed object is exactly what the step's script prints. Pure; never raises for a dict."""
    if row.get('status')==REFUSED_LINE_STATUS[step]:
        return set(row)=={'status','code'} and text(row['code'],CLASS_NAME)
    if row.get('status')!=OK_LINE_STATUS[step]:return False
    if step=='CALENDAR':
        return (set(row)==CALENDAR_KEYS and text(row['epoch'],EPOCH_TEXT) and text(row['calendar_version'],CALENDAR_VERSION)
                and hexpin(row['calendar_pin_sha']) and hexpin(row['package_sha']) and hexpin(row['document_order_sha']))
    if step=='IDENT':
        identities=row.get('identities')
        return (set(row)=={'status','identities'} and type(identities) is dict and set(identities)==set(CAPACITY_CHILDREN)
                and all(hexpin(value) for value in identities.values()))
    roots,identities=row.get('roots'),row.get('identities')
    return (set(row)==LOAD_KEYS and type(roots) is list and all(type(name) is str and name in LOAD_ROOT_NAMES for name in roots)
            and roots==sorted(set(roots)) and type(row['veto_mode']) is str and row['veto_mode'] in VETO_MODES
            and type(identities) is dict and set(identities)==set(roots) and all(hexpin(value) for value in identities.values())
            and hexpin(row['config_sha256']))

def line_of(step,result):
    """What a container printed, reduced to what may leave this process: a line that meets the grammar is copied (codes,
    hashes, a version name, booleans); of any other output nothing but two booleans (some output, one JSON line)."""
    output=result['output'] if type(result.get('output')) is bytes else b''
    out={'returncode':result['returncode'],'output_present':len(output)>0,'one_json_line':False,'valid':False,'line':None}
    try:row=single_line(output)
    except Refused:return out
    out['one_json_line']=True
    if not line_grammar(step,row):return out
    out.update(valid=True,line=dict(row,identities=dict(row['identities'])) if 'identities' in row else dict(row))
    return out

def answer_code(step,result,line):
    """None when the run returned one valid line with the exit status that line implies; else the constant code."""
    if not result['returned']:return result['code'] or 'COMMAND_FAILED'
    if not line['valid']:
        if result['returncode'] in RUN_ENGINE_STATUSES:return 'ENGINE_COULD_NOT_RUN_THE_CONTAINER'
        if result['returncode']==ALARM_STATUS:return 'SCRIPT_ENDED_BY_ITS_ALARM'
        if not line['one_json_line']:return 'OUTPUT_NOT_ONE_LINE'
        return 'LINE_NOT_AS_SPECIFIED'
    expected=0 if line['line']['status']==OK_LINE_STATUS[step] else 1
    if result['returncode']!=expected:return 'EXIT_STATUS_NOT_AS_THE_LINE'
    return None

def expectation_code(step,lines,host_identities,plan_config_sha=None):
    """None when the valid line(s) say what the step must find; else the constant code of the first difference."""
    first=lines[0]['line']
    if any(line['line']['status']==REFUSED_LINE_STATUS[step] for line in lines):return REFUSED_CODES[step]
    if step=='CALENDAR':
        if first['epoch']!=EPOCH_NAME:return 'CALENDAR_EPOCH_MISMATCH'
        if first['package_sha']!=PACKAGE_SHA:return 'CALENDAR_PACKAGE_MISMATCH'
        if first['document_order_sha']!=DOCUMENT_ORDER:return 'CALENDAR_DOCUMENT_ORDER_MISMATCH'
        return None
    if step=='IDENT':
        if lines[0]['line']['identities']!=lines[1]['line']['identities']:return 'IDENTITIES_DIFFER_BETWEEN_THE_TWO_RUNS'
        if any(first['identities'][name]!=host_identities[name] for name in CAPACITY_ROOTS):return 'IDENTITIES_DIFFER_FROM_THE_HOST'
        return None
    if first['roots']!=list(CAPACITY_ROOTS):return 'CAPACITY_ROOTS_NOT_THE_THREE'
    if first['veto_mode']!=VETO_MODE:return 'CAPACITY_VETO_MODE_NOT_AS_SIGNED'
    if first['config_sha256']!=plan_config_sha:return 'CAPACITY_CONFIG_SHA_NOT_EQUAL'
    if any(first['identities'][name]!=host_identities[name] for name in CAPACITY_ROOTS):return 'LOAD_IDENTITIES_DIFFER_FROM_THE_HOST'
    return None

def finding_code(after,worker_after,tree):
    """None when nothing is left and nothing moved; else the first finding beside an expected answer."""
    if after['status']!='COMPLETE':return 'CONTAINER_LISTING_UNAVAILABLE_AFTER_RUN'
    if after['names_present']:return 'CONTAINER_OF_THE_STEP_STILL_LISTED'
    if after['not_there_before']:return 'CONTAINER_PRESENT_THAT_WAS_NOT_THERE_BEFORE'
    if worker_after is not None:
        if worker_after['status']!='COMPLETE':return 'WORKER_UNAVAILABLE_AFTER_THE_STEP'
        if not worker_after['unchanged']:return 'WORKER_CHANGED_DURING_THE_STEP'
    if tree is not None:
        if tree['status']!='COMPLETE':return 'CAPACITY_TREE_UNAVAILABLE_AFTER_THE_STEP'
        if not tree['unchanged']:return 'CAPACITY_TREE_CHANGED_DURING_THE_STEP'
    return None

def step_verdict(step,results,lines,host_identities,after,worker_after,tree,plan_config_sha=None):
    """(status, outcome, code) once a container of the step was started."""
    for result,line in zip(results,lines):
        code=answer_code(step,result,line)
        if code is not None:return PARTIAL_STATUS,PARTIAL_OUTCOME,code
    if len(results)<len(STEP_ROWS[step]):return PARTIAL_STATUS,PARTIAL_OUTCOME,'SECOND_RUN_NOT_STARTED'
    code=expectation_code(step,lines,host_identities,plan_config_sha)
    if code is not None:return PARTIAL_STATUS,NOT_AS_EXPECTED_OUTCOME,code
    code=finding_code(after,worker_after,tree)
    if code is not None:return PARTIAL_STATUS,WITH_FINDINGS_OUTCOME,code
    return COMPLETE_STATUS,STEP_OUTCOMES[step],None

def comparison(step,lines,host_identities):
    """Booleans beside the lines: whether the two IDENT runs agree, and each printed identity against the host's (the
    config directory's too, reported and not required). None when there is nothing to compare."""
    valid=[line['line'] for line in lines if line is not None and line['valid'] and line['line']['status']==OK_LINE_STATUS[step]]
    if step=='CALENDAR' or not valid:return None
    first=valid[0]['identities']
    return {'runs_agree':(len(valid)==2 and valid[1]['identities']==first) if step=='IDENT' else None,
            'equal_to_the_host':{name:first[name]==host_identities[name] for name in sorted(first) if name in host_identities}}

def tree_after(held,gate):
    """Every held directory of the tree proved again from '/': unchanged, changed, or not observed (a constant code)."""
    try:
        for item in held:item.verify(gate)
        return {'status':'COMPLETE','unchanged':True,'code':None}
    except Exception as error:
        if isinstance(error,Refused) and str(error)=='PARENT_REPLACED':return {'status':'COMPLETE','unchanged':False,'code':'PARENT_REPLACED'}
        return {'status':'UNAVAILABLE','unchanged':None,'code':safe(error)['code']}

def worker_again(commands,worker):
    """The worker after the container: the same container (ID), still running, on the same image."""
    try:again=container_facts(commands,WORKER_NAME,expected_name=WORKER_NAME)
    except Exception as error:return {'status':'UNAVAILABLE','unchanged':None,'code':safe(error)['code']}
    same=again['id']==worker['id'] and again['running'] is True and again['image_id']==worker['image_id'] and again['restarts']==worker['restarts']
    return {'status':'COMPLETE','unchanged':same,'code':None}

REDUCTIONS=[]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    step=plan['step'];raw=stdin_of(plan);names=container_names(plan,bound['go_sha256'][:16]);rows=STEP_ROWS[step]   # pure
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    commands=Commands(host,gate);held=[]
    precheck={'image':None,'capacity':None,'config_file':None,'worker':None,'containers_before':None,'names_free':None}
    facts={'containers':[],'lines':[],'host_identities':None,'containers_after':None,'worker_after':None,'tree_after':None}
    def finish(status,outcome,code,phase):
        lines=facts['lines']
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),step=step,effects=effects_of(plan),
            clock=timing(begun,mark,clock,monotonic),commands_started=dict(commands.started),mutating_calls=state.counts(),
            precheck=precheck,containers=facts['containers'],lines=lines,host_identities=facts['host_identities'],
            comparison=comparison(step,lines,facts['host_identities']),containers_after=facts['containers_after'],worker_after=facts['worker_after'],tree_after=facts['tree_after'],
            step_succeeded=status==COMPLETE_STATUS,writes=0,containers_run=commands.started['CONTAINER'],phase_reached=phase)))
    try:
        # ---- everything is looked at before the first container: a refusal up to here has started nothing
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            try:image=image_facts(commands,plan['image_id'])
            except CommandFailed:raise Refused('IMAGE_ABSENT_OR_UNREADABLE') from None
            need(image['id']==plan['image_id'],'IMAGE_ID_MISMATCH')
            need(image['revision_label']==plan['image_revision'],'IMAGE_REVISION_MISMATCH')
            precheck['image']={'id_as_signed':True,'revision_as_signed':True}
            if step!='CALENDAR':
                report,identities,children=hold_tree(host,plan,gate,held)
                precheck['capacity']=report;facts['host_identities']=identities
            if step=='LOAD':
                precheck['config_file']=config_file_facts(host,plan,children['config'],gate)
                worker,precheck['worker']=worker_facts(commands,plan)
                precheck['worker']['root_changed_after_the_worker_started']=changed_after(report['root']['ctime_ns'],worker['started_at'])
            try:before=container_list(commands)
            except CommandFailed:raise Refused('CONTAINER_LISTING_FAILED') from None
            precheck['containers_before']=len(before)
            precheck['names_free']=not any(row['name'] in names for row in before)
            need(precheck['names_free'],'CONTAINER_NAME_TAKEN')
            # The last refusal that costs nothing: every container of the step, by its class, and the reserve.
            need(gate()>=effects_budget(*rows),'BUDGET_INSUFFICIENT_BEFORE_THE_CONTAINER')
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,'PRECHECK')
        # ---- the containers of the step, one after the other; the second IDENT run only after the first returned
        results=[]
        for row,name in zip(rows,names):
            if results and not results[-1]['returned']:break
            record={'name':name,'state':'NOT_STARTED','returncode':None,'code':None,'seconds':None};facts['containers'].append(record)
            started=attempt(monotonic)
            result=container_run(commands,row,plan['image_id'],mounts_of(plan),RUN_COMMAND,raw,container_name=name)
            ended=attempt(monotonic)
            record.update(code=result['code'],returncode=result['returncode'],
                          seconds=round(ended-started,3) if type(started) in (int,float) and type(ended) in (int,float) else None)
            if not result['started']:
                if not results:return finish(REFUSED_STATUS,REFUSED_OUTCOME,result['code'] or 'COMMAND_NOT_STARTED','CONTAINER_NOT_STARTED')
                break
            record['state']='RETURNED' if result['returned'] else 'DID_NOT_RETURN'
            results.append(result);facts['lines'].append(line_of(step,result) if result['returned'] else None)
        # ---- after them: what the engine still lists, the worker, the tree, whatever the runs said
        listing=attempt(lambda:container_list(commands))
        if type(listing) is list:
            known=set(row['id'] for row in before);new=[row for row in listing if row['id'] not in known]
            facts['containers_after']={'status':'COMPLETE','code':None,'before':len(before),'after':len(listing),'not_there_before':len(new),
                                       'names_present':any(row['name'] in names for row in listing),
                                       'rows':[{'id':row['id'],'state':row['state'],'of_this_step':row['name'] in names} for row in new[:MAX_NEW_CONTAINER_ROWS]]}
        else:facts['containers_after']={'status':'UNAVAILABLE','code':listing.get('code'),'before':len(before),'after':None,'not_there_before':None,
                                        'names_present':None,'rows':[]}
        if step=='LOAD':facts['worker_after']=worker_again(commands,worker)
        if step!='CALENDAR':facts['tree_after']=tree_after(held,gate)
        status,outcome,code=step_verdict(step,results,facts['lines'],facts['host_identities'],facts['containers_after'],
                                         facts['worker_after'],facts['tree_after'],plan['load']['config_sha256'] if step=='LOAD' else None)
        return finish(status,outcome,code,'CONTAINER')
    finally:
        for item in reversed(held):item.close()
