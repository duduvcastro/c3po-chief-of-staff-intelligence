import base64

OPERATION='GO_READONLY_HOSTOPS02_EPOCH_READBACK_01'
PHASE='READONLY_EPOCH_READBACK'
REQUEST_SCHEMA='READONLY_HOSTOPS02_EPOCH_READBACK_REQUEST_V1'
AUTHORITY_SCHEMA='READONLY_HOSTOPS02_EPOCH_READBACK_AUTHORITY_V1'
GO_SCHEMA='READONLY_HOSTOPS02_EPOCH_READBACK_GO_V1'
RECEIPT_SCHEMA='READONLY_HOSTOPS02_EPOCH_READBACK_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_EPOCH_READBACK_PLAN_V1'
SOURCE_NAME='epoch_readback.py'
WRITES_ALLOWED=False
ACTIVATION_ALLOWED=False
DATE_CLASS='READ'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
EVIDENCE_OPERATIONS=()
MAX_GATE_SPAN_SECONDS=3600
# Exit 0 exists for one outcome per signed mode. Only the POST outcome is the readback of the first session.
COMPLETE_OUTCOME='EPOCH_READBACK_POST_ALL_OBSERVED_ALL_EXPECTATIONS_MET'
PRE_OUTCOME='EPOCH_DRY_RUN_PRE_ALL_OBSERVED_ALL_EXPECTATIONS_MET'
# A dry run that leaves out any part of the full profile succeeds under another name: it is never the rehearsal of Monday.
PRE_REDUCED_OUTCOME='EPOCH_DRY_RUN_PRE_REDUCED_PROFILE_ALL_OBSERVED_ALL_EXPECTATIONS_MET'
MISMATCH_OUTCOME='OBSERVED_ALL_EXPECTATIONS_NOT_MET'
PARTIAL_OUTCOME='PARTIAL_OBSERVED'
REFUSED_OUTCOME='REFUSED_NOTHING_OBSERVED'
REDUCED_OUTCOME='PARTIAL_OBSERVED'
ESCAPED_OUTCOME='PARTIAL_OBSERVED'
MODES=('PRE','POST')
DRY_RUNS=('FULL','REDUCED')
PLAN_KEYS=frozenset(('mode','evidence_boot_id_sha256','revision','package_sha256','image','worker','release','policy','render','deploy',
                     'units','journal','docker_config','rows_in_receipt','bind_probe','dry_run','live','limits'))
RELEASE_KEYS=frozenset(('sha256','bytes','content_b64','parent','directory_name','file_name','container_target','directory_entries'))
# The epoch of this family (r2d2_v2_epoch_assembler.py lines 9, 10, 13 at the release; the controller's ORDER_SHA).
EPOCH_NAME='R2D2-V2-SHADOW-2026-10-05'
FIRST_SESSION_DAY='2026-10-05'
RUNTIME_ORDER_SHA256='1ad8b90cfab651823eb677b830a0078d10c17447575c8d813c3883a718579d8e'
RELEASE_SCHEMA_NAME='R2D2_V2_RELEASE_V3'
POLICY_SCHEMA_NAME='R2D2_V2_LIVE_POLICY_V1'
WORKER_SERVICE='r2d2-worker'
BUILD_KEY='C3PO_BUILD_SHA'
# The four names of the activation override of 2026-09-28, in its order: policy file, policy hash, release file, release hash.
LIVE_KEYS=('C3PO_R2D2_V2_LIVE_POLICY_FILE','C3PO_R2D2_V2_LIVE_POLICY_SHA','C3PO_R2D2_V2_SHADOW_RELEASE_FILE','C3PO_R2D2_V2_SHADOW_RELEASE_SHA')
REVISION='[0-9a-f]{40}'
ENTRY_NAME='[A-Za-z0-9][A-Za-z0-9._-]{0,127}'
DOTTED_NAME='[A-Za-z0-9._-]{1,128}'
CONTAINER_TARGET='/c3po-[a-z0-9][a-z0-9-]{0,40}'
UNIT_NAME=r'[A-Za-z0-9][A-Za-z0-9@_.:-]{0,120}\.(service|timer)'
UNIT_STATE='[A-Za-z0-9-]{0,32}'
SNIPPET_CODE='[A-Za-z_][A-Za-z0-9_]{0,79}'
MAX_RELEASE_BYTES=24576          # carried base64 in the request (PRE); the request is a document of at most 65536 bytes
MAX_INSTALLED_BYTES=65536        # the worker's own limit for the installed file (r2d2_v2_shadow_worker.py line 33)
MAX_POLICY_BYTES=8192
MAX_OVERRIDE_BYTES=4096
MAX_DIRECTORY_ENTRIES=8
MAX_UNITS=8
MAX_VALID_AT=4
MAX_FLOOR_BYTES=1<<50
MAX_COUNT=100000
MAX_REVISION_FILE_BYTES=128         # what activate reads of the deployed revision file
MAX_LIMIT_MILLISECONDS=60000
MAX_RENDERED_VOLUMES=64
# What install_release and activate take from the host by constant or by derivation (their own sources): a full dry
# run signs exactly these, so that it looks at the places and renders the files Monday's two writes will use.
MONDAY_DATA_VOLUME='/mnt/day-d-data'
MONDAY_DATA_TARGET='/app/day-d-data'
MONDAY_RELEASE_DIRECTORY='r2d2-v2-release-20261005'
MONDAY_RELEASE_FILE='release.CERTIFIED.json'
MONDAY_ENV_FILE='.env'
MONDAY_COMPOSE_FILE='compose.yml'
MONDAY_VERSION_NAME='.deploy-version'
MONDAY_LOCK_DIRECTORY='runtime/security'
MONDAY_LOCK_NAME='deployment.lock'
RELEASE_DIRECTORY_MODE=0o700
RELEASE_FILE_MODE=0o600
DOCKER_CONFIG_MODE=0o700
PIN_NAME='.r2d2-v2-pinned'
REBOOT_PENDING='/run/c3po-security/reboot.pending'
REBOOT_REQUIRED='/run/reboot-required'
CATALOG_NAMES=('epoch.json','maintenance.lock')
EXPIRED_CODES=('GO_EXPIRED','CLOCK_REVERSED')
# What a walk says about a directory that is not as signed: a finding. Anything else a walk refuses is an observation that failed.
WALK_FINDINGS=('PARENT_MISSING','PARENT_SYMLINK_COMPONENT','PARENT_NOT_DIRECTORY','PARENT_IDENTITY_MISMATCH','SYMLINK_COMPONENT','COMPONENT_NOT_DIRECTORY')
ROW_FIELDS=('device','inode','uid','gid','mode')
UNIT_PROPERTIES=('Id','LoadState','ActiveState','SubState','UnitFileState','FragmentPath','DropInPaths','WantedBy','RequiredBy','TriggeredBy')
GATED_PROPERTIES=('LoadState','ActiveState','SubState','UnitFileState')
CONTAINER_PREFIX='hostops02-k11-'
VERIFY_COMMAND=['python','-I','-B','-']
VERIFY_ALARM_SECONDS=30
# The pinned snippet. It runs in the container as `python -I -B -` after one line that this source writes in front of
# it (SIGNED_CONTEXT=<a literal of signed values>). Its first statement arms an alarm: the interpreter is killed by
# the kernel after VERIFY_ALARM_SECONDS, so the container ends by itself before the docker CLI's time limit. It reads
# the release (from the context, or with the worker's own reader from the read-only bind), calls the deployed
# Release.verify, read_policy and validate_policy, and prints ONE line of booleans and codes. A code is the single
# upper-case argument of an exception of the release's own two refusal classes, and otherwise the name of the
# exception's class: never a message. The reader of the worker and the controller are imported in every run, signed
# policy or not, so that no module the first session needs is imported for the first time on Monday.
VERIFY_SNIPPET=r'''import signal
signal.alarm(30)
import base64, hashlib, json, os, re, sys, types
from datetime import datetime, timezone
sys.path.insert(0, '/app')
C = SIGNED_CONTEXT
OWN = ()
def code_of(error):
    value = error.args[0] if isinstance(error, OWN) and len(error.args) == 1 and type(error.args[0]) is str else ''
    return value if re.fullmatch('[A-Z][A-Z0-9_]{0,79}', value) else type(error).__name__[:80]
def attempt(action):
    try:
        action()
        return {'valid': True, 'code': None}
    except Exception as error:
        return {'valid': False, 'code': code_of(error)}
try:
    from app.r2d2_v2_shadow import EBAR_AMENDMENT_SHA, Release, ShadowCalendar
    from app.r2d2_v2_earnings_package import implementation_package_sha
    from app import r2d2_v2_epoch_assembler as assembler
    from app.r2d2_v2_store import ShadowIntegrityError
    from app.r2d2_v2_shadow_worker import _release_bytes
    from app import r2d2_v2_live_controller as controller
    OWN = (ShadowIntegrityError, assembler.Refused)
    now = datetime.now(timezone.utc)
    calendar = ShadowCalendar()
    package = implementation_package_sha()
    release = {'source': 'STDIN' if C['release_b64'] is not None else 'FILE', 'read': False, 'bytes_equal_signed': False,
               'verified': False, 'code': None, 'mode_certified': False, 'epoch_equal': False, 'first_session_equal': False,
               'ebar_bound': False}
    try:
        if C['release_b64'] is not None:
            data = base64.b64decode(C['release_b64'], validate=True)
        else:
            data = _release_bytes(C['release_path'])
        release['read'] = True
        release['bytes_equal_signed'] = hashlib.sha256(data).hexdigest() == C['release_sha256'] and len(data) == C['release_bytes']
        found = Release.verify(data, C['release_sha256'], now=now, build_sha=C['revision'], calendar=calendar)
        release.update(verified=True, mode_certified=found.mode == 'CERTIFIED',
                       epoch_equal=found.epoch == C['epoch'] == assembler.EPOCH,
                       first_session_equal=found.first_session.isoformat() == C['first_session'] == assembler.FIRST_SESSION,
                       ebar_bound=found.ebar_amendment_sha == EBAR_AMENDMENT_SHA)
    except Exception as error:
        release['code'] = code_of(error)
    probe = None
    if C['probe_path'] is not None:
        probe = attempt(lambda: _release_bytes(C['probe_path']))
    policy = None
    if C['policy_b64'] is not None:
        raw = base64.b64decode(C['policy_b64'], validate=True)
        controller._release_bytes = lambda path: raw
        settings = types.SimpleNamespace(r2d2_v2_live_policy_file='/signed-bytes-on-standard-input',
                                         r2d2_v2_live_policy_sha=C['policy_sha256'], build_sha=C['revision'])
        identity = {'epoch': assembler.EPOCH, 'runtime_order_sha': assembler.RUNTIME_ORDER_SHA}
        bindings = {'release_sha': C['release_sha256'], 'package_sha': package, 'policy_sha': C['policy_sha256']}
        policy = {'hash_equal_signed': hashlib.sha256(raw).hexdigest() == C['policy_sha256'],
                  'controller_now': attempt(lambda: controller.read_policy(settings, now)),
                  'controller_at': [attempt(lambda item=item: controller.read_policy(settings, datetime.fromisoformat(item)))
                                    for item in C['policy_valid_at']],
                  'assembler': attempt(lambda: assembler.validate_policy(json.loads(raw), identity, bindings, calendar))}
    out = {'status': 'DONE', 'release': release, 'policy': policy, 'probe': probe, 'package_equal_signed': package == C['package_sha256'],
           'facts': {'python': '%d.%d.%d' % sys.version_info[:3], 'calendar_version': str(calendar.version)[:32]},
           'context_request_sha256': C['request_sha256']}
except BaseException as error:
    out = {'status': 'FAILED', 'code': code_of(error)}
os.write(1, json.dumps(out, sort_keys=True, separators=(',', ':')).encode('ascii') + b'\n')
raise SystemExit(0 if out['status'] == 'DONE' else 1)
'''
VERIFY_SNIPPET_SHA256=sha(VERIFY_SNIPPET.encode('ascii'))
VERIFY_LINE_KEYS=frozenset(('status','release','policy','probe','package_equal_signed','facts','context_request_sha256'))
VERIFY_RELEASE_KEYS=frozenset(('source','read','bytes_equal_signed','verified','code','mode_certified','epoch_equal','first_session_equal','ebar_bound'))
VERIFY_POLICY_KEYS=frozenset(('hash_equal_signed','controller_now','controller_at','assembler'))
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker'],'systemctl':['/usr/bin/systemctl','/bin/systemctl']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'the signed image reference','QUICK','READ'),
          'container':command_row('docker',['container','inspect','--format',CONTAINER_FORMAT],'the signed name of the worker container','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          'container_environment':command_row('docker',['container','inspect','--format'],'the presence and equality template, then the worker container ID','QUICK','READ'),
          'verify':command_row('docker',RUN_PREFIX,'--name hostops02-k11-<16 hex of the GO>, at most one read-only bind (POST: the installed release directory; PRE: the signed bind probe), the signed image ID, python -I -B -','RUN','CONTAINER',stdin=True),
          'render_base':command_row('docker',['compose'],'--project-name, --env-file and the signed -f list','RENDER','READ',tail=COMPOSE_CONFIG_TAIL),
          'render_override':command_row('docker',['compose'],'--project-name, --env-file, the signed -f list, then -f - : the signed override on standard input as the last file','RENDER','READ',tail=COMPOSE_CONFIG_TAIL,stdin=True),
          'unit':command_row('systemctl',['show'],'one signed unit name','QUICK','READ',tail=[part for key in UNIT_PROPERTIES for part in ('-p',key)])}
SCOPE_STATEMENT=('Reads and changes nothing on the filesystem of the host. PRE (dry run): the release bytes of the signed request, verified by '
                 'the deployed code in one attached container of the signed image ID with no network, a read-only root filesystem and no bind '
                 '(or the one read-only bind of an existing private directory that the request signs as a probe of the bind itself); '
                 'the place where install_release will create its directory must still be empty. POST: the installed release file, read on the '
                 'host and verified the same way through one read-only bind of its directory. In both: the live policy candidate put to the '
                 'deployed validators in that container, signed directories walked from "/", the compose render with the intended override on '
                 'standard input (never written to the host), image and worker metadata, the signed environment names of the worker as '
                 'booleans, unit states, free space of the journal filesystem, the maintenance pin and the reboot markers by lstat, and a '
                 'shared probe of the deployment lock. It creates and removes one container. Only the outcome named as success criterion '
                 'counts: the PRE outcome is a dry run and is never the readback of the first session, and a dry run signed as REDUCED '
                 'succeeds under a name of its own and is never the rehearsal of install_release and activate. This operation authorises no '
                 'installation, no activation and no change of any kind.')
SIDE_EFFECTS=['one attached docker run --rm: the engine creates a container named hostops02-k11-<16 hex of the GO> and removes it when its process ends; '
              'the snippet arms a %d s alarm as its first statement, so the process ends by itself before the %d s limit of the docker CLI; '
              'a run whose CLI is killed first may leave the container to the engine until its process ends, and the receipt says whether one of that name is listed; '
              'a container that was created and never started has no process and no alarm: it stays in the state created until someone removes it by its name, '
              'and no source of this family removes a container'
              %(VERIFY_ALARM_SECONDS,COMMAND_CLASSES['RUN']['seconds']),
              'a shared, non-blocking flock on the deployment lock, released at once: for that instant a non-blocking exclusive request of another process fails',
              'docker compose config reads the environment file; its values stay in the memory of this process and never reach the receipt, an argv or a log',
              'the values compared with the environment of the worker (the revision, two container paths, two hashes) travel in the argv of the docker CLI; none is a secret',
              'systemctl show of a unit the manager has not loaded makes the manager load it from disk; no daemon-reload is run',
              'with a signed docker_config (a reduced dry run only: activate never sets it) every docker command runs with DOCKER_CONFIG set to that directory, '
              'only after it was seen root:root 0700 and empty; it is counted before and after and a change is a finding of its own',
              'the Docker CLI executes its installed plugin binaries to answer compose; nothing is installed or changed']
FACTS_NOT_GATED=['the state of the deployment lock (FREE or BUSY)','the marker '+REBOOT_REQUIRED,'the state of a unit without a signed expectation',
                 'a journal root that does not exist, and its free space, without a signed floor','the restart count and the health of the worker',
                 'whether the policy is inside its window at the instant of the run','the versions of Python and of the calendar library in the image',
                 'the names of the catalog files in the journal root','the owner of the maintenance pin in POST','the milliseconds of every command without signed limits',
                 'whether the rows of a directory that receives no entry after this run would be accepted by a write']
# Items that carry no signed expectation at all. When one of them cannot be observed the receipt lists it under
# fact_items_not_observed and the outcome is decided by the other items.
FACT_ITEMS=['reboot_required','unit:<name> without a signed expectation','journal without a signed floor']
# What install_release and activate refuse on before any effect, and this source therefore finds beforehand.
PRECONDITIONS={'install_release':['the release directory absent in its parent','the parent rows as that write accepts them, the data volume a mount point',
                                  'the maintenance pin a regular file of root:root (PRE)','free bytes and, where counted, free inodes of the filesystem of its parent at or above the signed floors'],
               'activate':['its directory absent in the signed live parent, the rows of that parent as the write accepts them',
                           'free bytes and, where counted, free inodes of the filesystem of the live parent at or above the signed floors',
                           'no container left under a temporary name of the worker (an interrupted recreate)',
                           'the running worker without any of the four live names, with or without a value',
                           'the render with the override: build revision, the four values, the image reference, and the policy and release files reached through '
                           'exactly one bind of the signed source at the signed target that is not read-only',
                           'the two renders and each quick docker read within the signed milliseconds','the lock file present','no security reboot pending']}
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'after_effect_reserve_seconds':AFTER_EFFECT_RESERVE_SECONDS,'lock':LOCK_SCOPE,
       'modes':{'PRE':PRE_OUTCOME+' (a dry run; never the readback of the first session)','POST':COMPLETE_OUTCOME},
       'dry_run':{'FULL':PRE_OUTCOME+': policy, bind_probe, live, limits and the environment of the worker are signed, no docker_config, the places '
                         'of install_release, the layout and the override bytes of activate',
                  'REDUCED':PRE_REDUCED_OUTCOME+': anything less; never the rehearsal of install_release and activate'},
       'monday':{'data_volume':MONDAY_DATA_VOLUME,'data_target':MONDAY_DATA_TARGET,'release_directory':MONDAY_RELEASE_DIRECTORY,'release_file':MONDAY_RELEASE_FILE,
                 'env_file':'<deploy tree>/'+MONDAY_ENV_FILE,'compose_file':'<deploy tree>/<project>/'+MONDAY_COMPOSE_FILE,'version_file':MONDAY_VERSION_NAME,
                 'lock':MONDAY_LOCK_DIRECTORY+'/'+MONDAY_LOCK_NAME,'worker_container':'<project>-'+WORKER_SERVICE+'-1',
                 'override':'json.dumps of {"services":{"'+WORKER_SERVICE+'":{"environment":{the four names}}}} with sorted keys, ASCII'},
       'preconditions_of_the_writes_found_here':PRECONDITIONS,'fact_items':FACT_ITEMS,
       'epoch':{'name':EPOCH_NAME,'first_session':FIRST_SESSION_DAY,'runtime_order_sha256':RUNTIME_ORDER_SHA256,
                'release_schema':RELEASE_SCHEMA_NAME,'policy_schema':POLICY_SCHEMA_NAME},
       'verify':{'snippet_sha256':VERIFY_SNIPPET_SHA256,'command':VERIFY_COMMAND,'alarm_seconds':VERIFY_ALARM_SECONDS,
                 'container_name':CONTAINER_PREFIX+'<first 16 hex of the GO hash>','network':'none','root_filesystem':'read-only',
                 'binds':'read-only only. POST: the installed release directory. PRE: none, or the one existing private directory the request signs as bind_probe '
                         '(the snippet reads one named file of it with the reader of the worker and prints a boolean). Every bind source is held and proved again before and after the run',
                 'standard_input':'one line that assigns a literal of signed values to the name the snippet reads, then the snippet',
                 'imports':'the release verifier, the package hash, the assembler, the reader of the worker and the live controller, in every run',
                 'prints':'one JSON line of booleans, codes and two version strings; a code is the single upper-case argument of an exception of the '
                          "release's own refusal classes (ShadowIntegrityError, the assembler's Refused), otherwise the name of the exception's class"},
       'render':{'service':WORKER_SERVICE,'live_keys':list(LIVE_KEYS),'build_key':BUILD_KEY,
                 'compared':'the render of the signed files alone with the render that adds the signed override on standard input',
                 'data_volume':'the volumes of the worker in the render with the override, judged by the rule of activate; at most %d entries'%MAX_RENDERED_VOLUMES},
       'installed_release':{'directory':{'type':'dir','uid':0,'gid':0,'mode_octal':'%04o'%RELEASE_DIRECTORY_MODE},
                            'file':{'type':'file','uid':0,'gid':0,'mode_octal':'%04o'%RELEASE_FILE_MODE,'links':1}},
       'unit_properties':list(UNIT_PROPERTIES),'unit_properties_that_can_be_signed':list(GATED_PROPERTIES),
       'lstat_only':{'maintenance_pin':'<data volume>/'+PIN_NAME,'reboot_pending':REBOOT_PENDING,'reboot_required':REBOOT_REQUIRED,
                     'catalog_names':list(CATALOG_NAMES),'compose_inputs':'the environment file and every compose file: type, owner, mode and links, never content or size'},
       'file_contents_read':[BOOT_ID_PATH,'the deployed revision file of the deploy tree','POST: the installed release file, compared with the signed hash and size'],
       'reported_not_gated':FACTS_NOT_GATED,
       'side_effects':SIDE_EFFECTS,
       'never':['a file opened for writing','mkdir','chmod','chown','rename','removal','docker exec','compose up','a container with a bind it can write through',
                'a container with a network','a shell','a pull','a systemctl verb other than show','daemon-reload','a network connection opened by this process',
                'a value of an environment, a byte of the release, of the policy or of the render in the receipt','the content, size or digest of the environment file',
                'a device or inode number observed by this run in the receipt unless the request signs rows_in_receipt true (the effects repeat the signed leaf rows)'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'release_bytes_in_request':MAX_RELEASE_BYTES,'installed_release_bytes':MAX_INSTALLED_BYTES,'policy_bytes':MAX_POLICY_BYTES,
                 'override_bytes':MAX_OVERRIDE_BYTES,'standard_input_bytes':MAX_STDIN_BYTES,'units':MAX_UNITS,'policy_instants':MAX_VALID_AT,
                 'release_directory_entries':MAX_DIRECTORY_ENTRIES,'timeouts_before_a_tool_is_skipped':MAX_TOOL_TIMEOUTS,
                 'signed_milliseconds':MAX_LIMIT_MILLISECONDS,'rendered_volumes':MAX_RENDERED_VOLUMES}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner,NativeLock):
    """Everything this source can do to the host: the read primitives, the signed commands, the lock probe."""


# ---------------------------------------------------------------- the signed plan (pure)
def unpacked(value,digest,size,limit,code):
    """Bytes that travel base64 in the signed plan: exactly the signed hash and size, and no larger than the limit."""
    need(type(value) is str and len(value)<=4*limit and hexpin(digest) and integer(size,1,limit),code)
    try:raw=base64.b64decode(value.encode('ascii'),validate=True)
    except (ValueError,UnicodeEncodeError):raise Refused(code) from None
    need(sha(raw)==digest and len(raw)==size,code);return raw

def json_object(raw,code):
    try:value=strict(raw)
    except Refused:raise Refused(code) from None
    need(type(value) is dict,code);return value

def chain_spec(item,code,receives_entry=False):
    """One directory of the plan: its path, the rows a receipt of the same boot gave for it (or null: observed, compared
    with nothing) and the root below which an operational account owns the tree (or null). receives_entry: a later
    write creates an entry in it, so its signed rows must be rows that write accepts (no setgid directory)."""
    need(type(item) is dict and set(item)=={'path','rows','open_root'} and type(item['path']) is str and clean_path(item['path']) and item['path']!='/',code)
    root=item['open_root']
    need(root is None or (type(root) is str and clean_path(root) and root!='/' and inside(item['path'],root)),code)
    if item['rows'] is not None:validate_chain(item['rows'],item['path'],root,receives_entry)
    return item

def release_path_of(plan):
    release=plan['release'];return release['parent']['path']+'/'+release['directory_name']+'/'+release['file_name']
def container_path_of(plan):
    """The installed release file as the worker sees it: the data volume is bound at worker.data_target."""
    worker=plan['worker'];return worker['data_target']+release_path_of(plan)[len(worker['data_source']):]
def live_path_of(plan):
    """Where activate will create its directory: the signed name in the signed parent."""
    live=plan['live'];return live['parent']['path']+'/'+live['directory_name']
def host_path_of(plan,path):
    """The host path of a path the worker sees through its bind of the data volume."""
    worker=plan['worker'];return worker['data_source']+path[len(worker['data_target']):]
def mounts_of(plan):
    """The binds of the container, all read-only: in POST the installed release directory; in PRE none, or the one
    existing private directory the request signs as a probe of the bind itself."""
    release,probe=plan['release'],plan['bind_probe']
    if plan['mode']=='PRE':return [] if probe is None else [{'source':probe['directory']['path'],'target':probe['container_target'],'read_only':True}]
    return [{'source':release['parent']['path']+'/'+release['directory_name'],'target':release['container_target'],'read_only':True}]
def context_of(plan,request_sha256):
    release,policy,probe=plan['release'],plan['policy'],plan['bind_probe']
    return {'request_sha256':request_sha256,'revision':plan['revision'],'package_sha256':plan['package_sha256'],'epoch':EPOCH_NAME,
            'first_session':FIRST_SESSION_DAY,'release_sha256':release['sha256'],'release_bytes':release['bytes'],'release_b64':release['content_b64'],
            'release_path':None if plan['mode']=='PRE' else release['container_target']+'/'+release['file_name'],
            'policy_b64':None if policy is None else policy['content_b64'],'policy_sha256':None if policy is None else policy['sha256'],
            'policy_valid_at':[] if policy is None else list(policy['valid_at']),
            'probe_path':None if probe is None else probe['container_target']+'/'+probe['file_name']}
def frame_of(plan,request_sha256):
    """Standard input of the container: one assignment of signed values, then the pinned snippet."""
    return b'SIGNED_CONTEXT='+repr(context_of(plan,request_sha256)).encode('ascii')+b'\n'+VERIFY_SNIPPET.encode('ascii')

def policy_of(plan):
    """The policy candidate of the plan: its bytes are the signed ones, it names this epoch, this release, this
    revision, this package and the compiled order, and every signed instant lies inside its window."""
    policy=plan['policy']
    need(type(policy) is dict and set(policy)=={'sha256','bytes','content_b64','valid_at'},'POLICY_PLAN_INVALID')
    raw=unpacked(policy['content_b64'],policy['sha256'],policy['bytes'],MAX_POLICY_BYTES,'POLICY_NOT_THE_SIGNED_BYTES')
    body=json_object(raw,'POLICY_INVALID')
    # The controller compares the hash of the file; the assembler compares the hash of the canonical form of its
    # content (r2d2_v2_epoch_assembler.py: canonical, digest, POLICY_HASH). One signed hash meets both only when the
    # file is that canonical form, byte for byte.
    need(raw==json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8'),'POLICY_NOT_CANONICAL')
    need(body.get('schema')==POLICY_SCHEMA_NAME and body.get('mode')=='LIVE' and body.get('epoch')==EPOCH_NAME
         and body.get('release_sha')==plan['release']['sha256'] and body.get('code_revision')==plan['revision']
         and body.get('package_sha')==plan['package_sha256'] and body.get('order_sha')==RUNTIME_ORDER_SHA256,'POLICY_SCOPE')
    moments=policy['valid_at']
    need(type(moments) is list and 0<len(moments)<=MAX_VALID_AT and all(type(item) is str for item in moments) and len(set(moments))==len(moments),'POLICY_PLAN_INVALID')
    try:
        start,end=instant(body.get('valid_from')),instant(body.get('valid_until'));points=[instant(item) for item in moments]
    except Refused:raise Refused('POLICY_WINDOW') from None
    # An instant is spelled as isoformat() writes it: the container may run another interpreter than the dispatcher.
    need(all(point.isoformat()==item for point,item in zip(points,moments)),'POLICY_PLAN_INVALID')
    need(start<end and all(start<=point<end for point in points),'POLICY_WINDOW')
    return raw

def override_of(plan):
    """(bytes, environment) of the intended activation override: exactly the four live names of the worker service."""
    render=plan['render']
    need(type(render) is dict and set(render)=={'project','env_file','files','override_b64','override_sha256','override_bytes'},'RENDER_PLAN_INVALID')
    raw=unpacked(render['override_b64'],render['override_sha256'],render['override_bytes'],MAX_OVERRIDE_BYTES,'OVERRIDE_NOT_THE_SIGNED_BYTES')
    body=json_object(raw,'OVERRIDE_INVALID')
    need(set(body)=={'services'} and type(body['services']) is dict and set(body['services'])=={WORKER_SERVICE}
         and type(body['services'][WORKER_SERVICE]) is dict and set(body['services'][WORKER_SERVICE])=={'environment'},'OVERRIDE_INVALID')
    environment=body['services'][WORKER_SERVICE]['environment']
    need(type(environment) is dict and set(environment)==set(LIVE_KEYS) and all(text(value,ENVIRONMENT_VALUE) and value for value in environment.values()),'OVERRIDE_INVALID')
    return raw,environment

def activate_override(environment):
    """The bytes activate writes as its override file for these four values (activate: override_of)."""
    return json.dumps({'services':{WORKER_SERVICE:{'environment':environment}}},sort_keys=True).encode('ascii')

def full_profile(plan,environment):
    """The full dry run: every member Monday's runs will meet is signed, and the places and files are the ones
    install_release and activate use. Anything less is signed as REDUCED and succeeds under another name."""
    worker,release,deploy,render=plan['worker'],plan['release'],plan['deploy'],plan['render']
    need(plan['policy'] is not None and plan['bind_probe'] is not None and plan['live'] is not None and plan['limits'] is not None
         and worker['environment'] is True,'DRY_RUN_NOT_THE_FULL_PROFILE')
    tree=deploy['tree']['path']
    need(worker['data_source']==MONDAY_DATA_VOLUME and worker['data_target']==MONDAY_DATA_TARGET and release['parent']['path']==MONDAY_DATA_VOLUME
         and release['directory_name']==MONDAY_RELEASE_DIRECTORY and release['file_name']==MONDAY_RELEASE_FILE,'DRY_RUN_NOT_THE_PLACES_OF_INSTALL_RELEASE')
    need(render['env_file']==tree+'/'+MONDAY_ENV_FILE and render['files']==[tree+'/'+render['project']+'/'+MONDAY_COMPOSE_FILE]
         and deploy['version_name']==MONDAY_VERSION_NAME and deploy['lock_directory']['path']==tree+'/'+MONDAY_LOCK_DIRECTORY
         and deploy['lock_name']==MONDAY_LOCK_NAME and worker['container']=='%s-%s-1'%(render['project'],WORKER_SERVICE),'DRY_RUN_NOT_THE_LAYOUT_OF_ACTIVATE')
    need(override_of(plan)[0]==activate_override(environment),'OVERRIDE_NOT_AS_ACTIVATE_WRITES_IT')
    rows=release['parent']['rows']                                   # install_release: the signed rows show the data volume as a mount point
    need(rows is None or mount_point_of(rows)==MONDAY_DATA_VOLUME,'DATA_VOLUME_NOT_A_MOUNT_POINT')

def validate_plan(plan):
    mode=plan['mode'];need(type(mode) is str and mode in MODES,'MODE_INVALID');pre=mode=='PRE'
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    need(text(plan['revision'],REVISION) and hexpin(plan['package_sha256']),'REVISION_OR_PACKAGE_UNBOUND')
    need(type(plan['rows_in_receipt']) is bool,'ROWS_FLAG_INVALID')
    profile=plan['dry_run']
    need((type(profile) is str and profile in DRY_RUNS) if pre else profile is None,'DRY_RUN_PROFILE_INVALID')
    image=plan['image']
    need(type(image) is dict and set(image)=={'reference','image_id'} and text(image['reference'],REFERENCE) and text(image['image_id'],IMAGE_ID),'IMAGE_PLAN_INVALID')
    need(not image['reference'].startswith('-'),'IMAGE_PLAN_INVALID')                 # activate refuses a rendered image that begins like an option
    worker=plan['worker']
    need(type(worker) is dict and set(worker)=={'container','environment','data_source','data_target'} and text(worker['container'],CONTAINER_NAME)
         and not text(worker['container'],CONTAINER_ID) and type(worker['environment']) is bool
         and all(type(worker[key]) is str and clean_path(worker[key]) and worker[key]!='/' for key in ('data_source','data_target')),'WORKER_PLAN_INVALID')
    release=plan['release']
    need(type(release) is dict and set(release)==set(RELEASE_KEYS) and hexpin(release['sha256']) and integer(release['bytes'],1,MAX_INSTALLED_BYTES)
         and text(release['directory_name'],ENTRY_NAME) and text(release['file_name'],ENTRY_NAME),'RELEASE_PLAN_INVALID')
    chain_spec(release['parent'],'RELEASE_PLAN_INVALID',True)
    need(inside(release['parent']['path'],worker['data_source']),'RELEASE_OUTSIDE_THE_DATA_VOLUME')
    need(clean_path(release_path_of(plan)) and clean_path(container_path_of(plan)),'RELEASE_PLAN_INVALID')
    if pre:
        need(release['container_target'] is None and release['directory_entries'] is None,'RELEASE_PLAN_INVALID')
        body=json_object(unpacked(release['content_b64'],release['sha256'],release['bytes'],MAX_RELEASE_BYTES,'RELEASE_NOT_THE_SIGNED_BYTES'),'RELEASE_INVALID')
        need(body.get('schema')==RELEASE_SCHEMA_NAME and body.get('mode')=='CERTIFIED' and body.get('epoch')==EPOCH_NAME
             and body.get('first_session')==FIRST_SESSION_DAY and body.get('code_revision')==plan['revision']
             and body.get('implementation_package_sha')==plan['package_sha256'],'RELEASE_SCOPE')
    else:
        need(release['content_b64'] is None and text(release['container_target'],CONTAINER_TARGET)
             and integer(release['directory_entries'],1,MAX_DIRECTORY_ENTRIES),'RELEASE_PLAN_INVALID')
    live=plan['live']
    need(live is None or (type(live) is dict and set(live)=={'parent','directory_name'} and text(live['directory_name'],ENTRY_NAME)),'LIVE_PLAN_INVALID')
    if live is not None:
        chain_spec(live['parent'],'LIVE_PLAN_INVALID',True)
        need(inside(live['parent']['path'],worker['data_source']) and clean_path(live_path_of(plan)),'LIVE_OUTSIDE_THE_DATA_VOLUME')
        place=release['parent']['path']+'/'+release['directory_name']
        need(not inside(live_path_of(plan),place) and not inside(place,live_path_of(plan)),'LIVE_AND_RELEASE_OVERLAP')
    limits=plan['limits']
    need(limits is None or (type(limits) is dict and set(limits)=={'render_ms','quick_ms','data_volume_free_bytes','data_volume_free_inodes'}
                            and integer(limits['render_ms'],1,MAX_LIMIT_MILLISECONDS) and integer(limits['quick_ms'],1,MAX_LIMIT_MILLISECONDS)
                            and integer(limits['data_volume_free_bytes'],0,MAX_FLOOR_BYTES) and integer(limits['data_volume_free_inodes'],0,MAX_FLOOR_BYTES)),'LIMITS_PLAN_INVALID')
    policy=plan['policy']
    need(policy is not None or pre,'POLICY_REQUIRED')
    if policy is not None:policy_of(plan)
    deploy=plan['deploy']
    need(type(deploy) is dict and set(deploy)=={'tree','lock_directory','lock_name','version_name'} and text(deploy['version_name'],DOTTED_NAME)
         and deploy['version_name'] not in ('.','..') and (deploy['lock_name'] is None or (text(deploy['lock_name'],DOTTED_NAME) and deploy['lock_name'] not in ('.','..'))),
         'DEPLOY_PLAN_INVALID')
    chain_spec(deploy['tree'],'DEPLOY_PLAN_INVALID');chain_spec(deploy['lock_directory'],'DEPLOY_PLAN_INVALID')
    need(inside(deploy['lock_directory']['path'],deploy['tree']['path']),'DEPLOY_PLAN_INVALID')
    render=plan['render']
    need(render is not None or not pre,'RENDER_REQUIRED')
    if render is not None:
        _,environment=override_of(plan)
        compose_arguments(render['project'],render['env_file'],render['files'],True)
        need(all(inside(item,deploy['tree']['path']) and item!=deploy['tree']['path'] for item in [render['env_file']]+render['files']),'RENDER_OUTSIDE_THE_DEPLOY_TREE')
        need(environment[LIVE_KEYS[3]]==release['sha256'] and environment[LIVE_KEYS[2]]==container_path_of(plan),'OVERRIDE_RELEASE_BINDING')
        need(clean_path(environment[LIVE_KEYS[0]]) and inside(environment[LIVE_KEYS[0]],worker['data_target']) and environment[LIVE_KEYS[0]]!=worker['data_target']
             and hexpin(environment[LIVE_KEYS[1]]) and (policy is None or environment[LIVE_KEYS[1]]==policy['sha256']),'OVERRIDE_POLICY_BINDING')
        # the policy file of the override is a file directly in the directory activate will create
        need(live is None or str(PurePosixPath(host_path_of(plan,environment[LIVE_KEYS[0]])).parent)==live_path_of(plan),'OVERRIDE_POLICY_NOT_IN_THE_LIVE_DIRECTORY')
        if profile=='FULL':full_profile(plan,environment)
    units=plan['units']
    need(type(units) is list and len(units)<=MAX_UNITS and all(type(item) is dict and set(item)=={'name','expected'} and text(item['name'],UNIT_NAME) for item in units)
         and len({item['name'] for item in units})==len(units),'UNITS_PLAN_INVALID')
    need(all(item['expected'] is None or (type(item['expected']) is dict and item['expected'] and set(item['expected'])<=set(GATED_PROPERTIES)
                                          and all(text(value,UNIT_STATE) for value in item['expected'].values())) for item in units),'UNITS_PLAN_INVALID')
    journal=plan['journal']
    need(journal is None or (type(journal) is dict and set(journal)=={'path','floor_bytes'} and type(journal['path']) is str and clean_path(journal['path'])
                             and journal['path']!='/' and (journal['floor_bytes'] is None or integer(journal['floor_bytes'],0,MAX_FLOOR_BYTES))),'JOURNAL_PLAN_INVALID')
    need(plan['docker_config'] is None or (text(plan['docker_config'],COMMAND_VARIABLES['DOCKER_CONFIG']) and clean_path(plan['docker_config'])),'DOCKER_CONFIG_INVALID')
    need(plan['docker_config'] is None or profile=='REDUCED','DOCKER_CONFIG_ONLY_IN_A_REDUCED_DRY_RUN')
    probe=plan['bind_probe']
    need(probe is None or (pre and type(probe) is dict and set(probe)=={'directory','file_name','container_target'} and text(probe['file_name'],DOTTED_NAME)
                           and probe['file_name'] not in ('.','..') and text(probe['container_target'],CONTAINER_TARGET)),'BIND_PROBE_INVALID')
    if probe is not None:chain_spec(probe['directory'],'BIND_PROBE_INVALID')
    run_arguments('verify',image['image_id'],mounts_of(plan),VERIFY_COMMAND,CONTAINER_PREFIX+'0'*16)
    need(len(frame_of(plan,'0'*64))<=MAX_STDIN_BYTES,'VERIFY_FRAME_TOO_LARGE')

def expected_environment(plan):
    """What is compared with the environment of the running worker: the revision and, with a render, the four intended
    values; without one, the four names against the empty value, so that only their presence is learnt."""
    intended={key:'' for key in LIVE_KEYS} if plan['render'] is None else override_of(plan)[1]
    return dict(intended,**{BUILD_KEY:plan['revision']})

def chain_effects_of(item):
    if item['rows'] is None:
        return {'path':item['path'],'open_root':item['open_root'],'rows_signed':False,'row':None,'chain_sha256':None,'mount_point_by_device_change':None}
    return dict(chain_effects(item['rows']),open_root=item['open_root'],rows_signed=True)

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    release,policy,render,deploy=plan['release'],plan['policy'],plan['render'],plan['deploy'];pre=plan['mode']=='PRE'
    return {'operation':OPERATION,'mode':plan['mode'],'gates_first_session_readback':not pre,
            'epoch':EPOCH_NAME,'first_session':FIRST_SESSION_DAY,'revision':plan['revision'],'package_sha256':plan['package_sha256'],
            'image':plan['image'],'worker':plan['worker'],
            'release':{'sha256':release['sha256'],'bytes':release['bytes'],'path':release_path_of(plan),'path_in_the_worker':container_path_of(plan),
                       'source':'THE_BYTES_OF_THE_REQUEST_ON_STANDARD_INPUT' if pre else 'THE_INSTALLED_FILE_THROUGH_A_READ_ONLY_BIND',
                       'expected_on_the_host':'DIRECTORY_ABSENT' if pre else 'INSTALLED','directory_entries':release['directory_entries'],
                       'parent':chain_effects_of(release['parent'])},
            'verify':{'snippet_sha256':VERIFY_SNIPPET_SHA256,'image_id':plan['image']['image_id'],'binds':mounts_of(plan),'network':'none',
                      'command':VERIFY_COMMAND,'alarm_seconds':VERIFY_ALARM_SECONDS},
            'policy':None if policy is None else {'sha256':policy['sha256'],'bytes':policy['bytes'],'valid_at':policy['valid_at']},
            'render':None if render is None else {'project':render['project'],'env_file':render['env_file'],'files':render['files'],
                                                  'override_sha256':render['override_sha256'],'service':WORKER_SERVICE,'environment':override_of(plan)[1]},
            'deploy':{'tree':chain_effects_of(deploy['tree']),'lock_directory':chain_effects_of(deploy['lock_directory']),
                      'lock':None if deploy['lock_name'] is None else deploy['lock_directory']['path']+'/'+deploy['lock_name'],
                      'version_file':deploy['tree']['path']+'/'+deploy['version_name']},
            'maintenance_pin':plan['worker']['data_source']+'/'+PIN_NAME,
            'dry_run':plan['dry_run'],'rehearses_install_release_and_activate':plan['dry_run']=='FULL','limits':plan['limits'],
            'live':None if plan['live'] is None else {'path':live_path_of(plan),'expected_on_the_host':'DIRECTORY_ABSENT','parent':chain_effects_of(plan['live']['parent'])},
            'bind_probe':None if plan['bind_probe'] is None else {'directory':chain_effects_of(plan['bind_probe']['directory']),
                                                                  'file':plan['bind_probe']['directory']['path']+'/'+plan['bind_probe']['file_name']},
            'units':plan['units'],'journal':plan['journal'],'docker_config':plan['docker_config'],'rows_in_receipt':plan['rows_in_receipt'],
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],'writes':0,'containers_run':1,'activation':False}
def success_of(plan):
    if plan['mode']=='PRE':return PRE_OUTCOME if plan['dry_run']=='FULL' else PRE_REDUCED_OUTCOME
    return COMPLETE_OUTCOME


# ---------------------------------------------------------------- the observations
def item_of(status='COMPLETE',findings=(),**fields):
    """One observation: whether it could be made (status) and, separately, whether what was seen is what was signed."""
    codes=sorted(set(findings))
    return dict(fields,status=status,findings=codes,matches=(not codes) if status=='COMPLETE' else None)

def verdict(value):
    return type(value) is dict and set(value)=={'valid','code'} and type(value['valid']) is bool and (value['code'] is None or text(value['code'],SNIPPET_CODE))

def verify_line(raw,returncode,plan,request_sha256):
    """The one line the snippet prints, member by member: booleans, constant codes, two version strings. None when a
    run that failed printed nothing this source can read."""
    try:line=single_line(raw)
    except Refused:
        need(returncode!=0,'VERIFY_OUTPUT_INVALID');return None
    if returncode!=0:
        return line if set(line)=={'status','code'} and line['status']=='FAILED' and text(line['code'],SNIPPET_CODE) else None
    need(set(line)==set(VERIFY_LINE_KEYS) and line['status']=='DONE' and line['context_request_sha256']==request_sha256
         and type(line['package_equal_signed']) is bool,'VERIFY_OUTPUT_INVALID')
    release,policy,facts=line['release'],line['policy'],line['facts']
    need(type(release) is dict and set(release)==set(VERIFY_RELEASE_KEYS) and release['source']==('STDIN' if plan['mode']=='PRE' else 'FILE')
         and all(type(release[key]) is bool for key in VERIFY_RELEASE_KEYS-{'source','code'})
         and (release['code'] is None or text(release['code'],SNIPPET_CODE)) and (release['code'] is None)==release['verified'],'VERIFY_OUTPUT_INVALID')
    need(type(facts) is dict and set(facts)=={'python','calendar_version'} and text(facts['python'],r'[0-9]{1,2}\.[0-9]{1,3}\.[0-9]{1,3}')
         and text(facts['calendar_version'],'[0-9A-Za-z.+_-]{1,32}'),'VERIFY_OUTPUT_INVALID')
    need((policy is None)==(plan['policy'] is None) and (line['probe'] is None)==(plan['bind_probe'] is None)
         and (line['probe'] is None or verdict(line['probe'])),'VERIFY_OUTPUT_INVALID')
    if policy is not None:
        need(type(policy) is dict and set(policy)==set(VERIFY_POLICY_KEYS) and type(policy['hash_equal_signed']) is bool and verdict(policy['controller_now'])
             and verdict(policy['assembler']) and type(policy['controller_at']) is list and len(policy['controller_at'])==len(plan['policy']['valid_at'])
             and all(verdict(item) for item in policy['controller_at']),'VERIFY_OUTPUT_INVALID')
    return line

def free_inodes(host,fd):
    """Inodes a non-root writer can still take on the filesystem of a held descriptor; None where the filesystem
    counts none (f_files 0: it does not run out of them apart from its bytes). (activate: free_inodes)"""
    numbers=host.fstatvfs(fd);total,free=getattr(numbers,'f_files',0),getattr(numbers,'f_favail',None)
    return free if integer(total,1) and integer(free) else None

def plain(path):
    """An absolute path as compose may print it (a trailing or a doubled slash, a "." component) in the one spelling the
    signed paths have; anything else stays as it is, and so stays unequal to a signed path. (activate: plain)"""
    return str(PurePosixPath(path)) if type(path) is str else path

def data_bind_of(volumes,paths,source,target):
    """activate's own rule for the render it recreates from (activate: service_of): every volume has a target, and each
    of the paths the override names is covered by exactly one of them, which is the bind of the signed source at the
    signed target and is not read-only. None: the volumes are not a list activate accepts. Otherwise True or False."""
    if not (type(volumes) is list and len(volumes)<=MAX_RENDERED_VOLUMES
            and all(type(item) is dict and type(item.get('target')) is str and item['target'] for item in volumes)):return None
    binds=[(plain(item['target']),item) for item in volumes]
    for path in paths:
        covering=[pair for pair in binds if inside(path,pair[0])]
        if not (len(covering)==1 and covering[0][0]==target and covering[0][1].get('type')=='bind'
                and plain(covering[0][1].get('source'))==source and covering[0][1].get('read_only') in (None,False)):return False
    return True

class Readback:
    """The observations of one run. Each method is one item of the receipt and fails on its own."""
    def __init__(self,plan,host,gate,commands,bound,monotonic):
        self.plan,self.host,self.gate,self.commands,self.monotonic=plan,host,gate,commands,monotonic
        self.pre=plan['mode']=='PRE';self.held={};self.same_boot=True;self.config_signed=plan['docker_config'];self.config_usable=False
        self.request_sha256=bound['request_sha256'];self.name=CONTAINER_PREFIX+bound['go_sha256'][:16]
        self.frame=frame_of(plan,self.request_sha256);self.expected=expected_environment(plan)
        self.override=None if plan['render'] is None else override_of(plan)[0]
        self.worker_id=None;self.entries_before=None

    def config(self):
        """DOCKER_CONFIG of every docker command: nothing when the plan signs none; otherwise that directory, and only
        after it was seen private and empty."""
        if self.config_signed is None:return None
        need(self.config_usable,'DOCKER_CONFIG_DIRECTORY_UNAVAILABLE');return self.config_signed

    def timed(self,action):
        """(what one command answered, the milliseconds it took)."""
        mark=self.monotonic();result=action();return result,int((self.monotonic()-mark)*1000)
    def slow(self,key,*milliseconds):
        """The finding of a command that took longer than the signed limit of its kind; nothing without signed limits."""
        limits=self.plan['limits']
        if limits is None or all(value<=limits[key] for value in milliseconds):return []
        return ['RENDER_SLOWER_THAN_THE_SIGNED_LIMIT' if key=='render_ms' else 'DOCKER_CALL_SLOWER_THAN_THE_SIGNED_LIMIT']

    def boot(self):
        self.same_boot=boot_id_sha256(self.host,self.gate)==self.plan['evidence_boot_id_sha256']
        # A reboot may renumber devices: one finding here, and the signed rows are then compared without the device.
        return item_of(findings=[] if self.same_boot else ['EVIDENCE_FROM_EARLIER_BOOT'],equal_to_the_evidence=self.same_boot,
                       device_numbers_compared=self.same_boot)

    def directory(self,key,spec,receives_entry=False,write_follows=False,volume=None):
        """One directory walked from "/" without following a link and held for the rest of the run. With signed rows the
        walk compares every component; without, it records what it finds. Identities are reported as booleans and
        counts; the rows themselves only when the request signs rows_in_receipt.
        receives_entry: a write creates an entry here, so the observed rows are judged as that write judges its signed
        rows (the family's rule, no setgid directory; with volume, the filesystem's mount point is that volume).
        write_follows: that write is still to come, so rows it would refuse are a finding and not only a fact."""
        host,signed=self.host,spec['rows'];observed=[];findings=[];fd=None
        try:
            if signed is None:fd=descend(host,spec['path'],self.gate,observed)
            else:fd=walk_pinned(host,signed,self.gate,observed,self.same_boot)
        except FileNotFoundError:findings.append('PARENT_MISSING')
        except Refused as error:
            if str(error) not in WALK_FINDINGS:raise
            findings.append(str(error))
        facts={'path':spec['path'],'components':len(prefixes(spec['path'])),'components_observed':len(observed),'rows_signed':signed is not None,
               'as_signed':None if signed is None else fd is not None,'held':fd is not None}
        if fd is None:
            if signed is not None and findings==['PARENT_IDENTITY_MISMATCH']:
                facts['fields_that_differ']={field:observed[-1][field]!=signed[len(observed)-1][field] for field in ROW_FIELDS}
        else:
            try:
                self.held[key]=Pinned(host,fd,rows=[dict(row) for row in observed] if signed is None else signed,compare_device=signed is None or self.same_boot)
            except BaseException:
                host.close(fd);raise
            leaf=observed[-1]
            try:validate_chain([dict(row) for row in observed],spec['path'],spec['open_root'],receives_entry);acceptable,why=True,None
            except Refused as error:acceptable,why=False,code_of(error,'CHAIN_ROW_INVALID')
            on_volume=None if volume is None else mount_point_of(observed)==volume
            if acceptable and on_volume is False:acceptable,why=False,'DATA_VOLUME_NOT_A_MOUNT_POINT'
            if write_follows and not acceptable:findings.append('DIRECTORY_NOT_ACCEPTABLE_TO_THE_WRITE_THAT_FOLLOWS')
            # room for what the write creates, on the filesystem of the directory it creates in, as that write asks for it
            available,inodes=free_bytes(host,fd),free_inodes(host,fd);limits=self.plan['limits']
            if receives_entry and limits is not None:
                facts.update(free_bytes_floor=limits['data_volume_free_bytes'],free_inodes_floor=limits['data_volume_free_inodes'])
                if available<limits['data_volume_free_bytes']:findings.append('DATA_VOLUME_FREE_SPACE_BELOW_FLOOR')
                if inodes is not None and inodes<limits['data_volume_free_inodes']:findings.append('DATA_VOLUME_FREE_INODES_BELOW_FLOOR')
            facts.update(owner_uid=leaf['uid'],owner_gid=leaf['gid'],mode_octal='%04o'%leaf['mode'],
                         device_changes=sum(1 for previous,row in zip(observed,observed[1:]) if row['device']!=previous['device']),
                         mount_point_by_device_change=mount_point_of(observed),
                         leaf_is_a_mount_point=len(observed)>1 and observed[-1]['device']!=observed[-2]['device'],
                         world_writable_without_sticky=world_writable_without_sticky(leaf),setgid=bool(leaf['mode']&stat.S_ISGID),
                         rows_acceptable_to_a_write=acceptable,rows_refusal=why,judged_as_receiving_an_entry=receives_entry,
                         mount_point_is_the_data_volume=on_volume,
                         entries=count_entries(host,fd,self.gate,MAX_COUNT),bytes_available=available,inodes_available=inodes)
        if self.plan['rows_in_receipt']:facts['observed_rows']=observed
        return item_of(findings=findings,**facts)

    def release_target(self):
        """PRE: nothing stands where install_release will create its directory. POST: the directory and the file as
        install_release leaves them, the bytes equal to the signed hash; the directory is then held for the bind."""
        parent=self.held.get('RELEASE_PARENT');need(parent is not None,'DIRECTORY_NOT_HELD')
        host,release=self.host,self.plan['release'];name=release['directory_name'];expected='DIRECTORY_ABSENT' if self.pre else 'INSTALLED'
        parent.verify(self.gate);self.gate()
        try:named=host.lstat(name,parent.fd)
        except FileNotFoundError:
            return item_of(findings=[] if self.pre else ['RELEASE_DIRECTORY_ABSENT'],expected=expected,exists=False)
        if self.pre:return item_of(findings=['RELEASE_TARGET_ALREADY_EXISTS'],expected=expected,exists=True,type=kind(named.st_mode))
        if not stat.S_ISDIR(named.st_mode):
            return item_of(findings=['RELEASE_DIRECTORY_NOT_A_DIRECTORY'],expected=expected,exists=True,type=kind(named.st_mode))
        self.gate();fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=parent.fd)
        try:
            info=host.fstat(fd);need((info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'RELEASE_DIRECTORY_CHANGED_DURING_READ')
            self.held['RELEASE_DIRECTORY']=Pinned(host,fd,parent=parent,name=name)
        except BaseException:
            host.close(fd);raise
        findings=[];entries=count_entries(host,fd,self.gate,MAX_COUNT)
        directory={'type':'dir','uid':info.st_uid,'gid':info.st_gid,'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),
                   'on_the_device_of_its_parent':info.st_dev==parent.identity[0],'entries':entries,'entries_signed':release['directory_entries']}
        if (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))!=(0,0,RELEASE_DIRECTORY_MODE):findings.append('RELEASE_DIRECTORY_METADATA')
        if not directory['on_the_device_of_its_parent']:findings.append('RELEASE_DIRECTORY_IS_A_MOUNT_POINT')
        if entries!=release['directory_entries']:findings.append('RELEASE_DIRECTORY_ENTRIES')
        self.gate()
        try:leaf=host.lstat(release['file_name'],fd)
        except FileNotFoundError:
            return item_of(findings=findings+['RELEASE_FILE_ABSENT'],expected=expected,exists=True,directory=directory,file={'exists':False})
        found={'exists':True,'type':kind(leaf.st_mode),'uid':leaf.st_uid,'gid':leaf.st_gid,'mode_octal':'%04o'%stat.S_IMODE(leaf.st_mode),'links':leaf.st_nlink}
        if not stat.S_ISREG(leaf.st_mode):
            return item_of(findings=findings+['RELEASE_FILE_NOT_REGULAR'],expected=expected,exists=True,directory=directory,file=found)
        if (leaf.st_uid,leaf.st_gid,stat.S_IMODE(leaf.st_mode),leaf.st_nlink)!=(0,0,RELEASE_FILE_MODE,1):findings.append('RELEASE_FILE_METADATA')
        try:raw,read=read_regular(host,release['file_name'],fd,self.gate,MAX_INSTALLED_BYTES)
        except Refused as error:
            if str(error)!='FILE_TOO_LARGE':raise
            return item_of(findings=findings+['RELEASE_FILE_TOO_LARGE'],expected=expected,exists=True,directory=directory,file=found)
        need((read.st_dev,read.st_ino)==(leaf.st_dev,leaf.st_ino),'RELEASE_FILE_CHANGED_DURING_READ')
        found['bytes_equal_signed']=sha(raw)==release['sha256'] and len(raw)==release['bytes']
        if not found['bytes_equal_signed']:findings.append('RELEASE_FILE_BYTES_MISMATCH')
        return item_of(findings=findings,expected=expected,exists=True,directory=directory,file=found)

    def live_target(self):
        """Nothing stands yet where activate will create its directory: one lstat of the signed name in the held,
        signed parent (activate refuses DESTINATION_PRESENT before any effect, and its GO is then spent)."""
        parent=self.held.get('LIVE_PARENT');need(parent is not None,'DIRECTORY_NOT_HELD')
        parent.verify(self.gate);self.gate()
        try:named=self.host.lstat(self.plan['live']['directory_name'],parent.fd)
        except FileNotFoundError:return item_of(expected='DIRECTORY_ABSENT',exists=False)
        return item_of(findings=['LIVE_DIRECTORY_ALREADY_EXISTS'],expected='DIRECTORY_ABSENT',exists=True,type=kind(named.st_mode))

    def configuration(self):
        """The signed configuration directory of the docker CLI: root:root 0700 and empty, counted before any command."""
        rows=[];fd=descend(self.host,self.config_signed,self.gate,rows)
        try:
            info=self.host.fstat(fd);self.held['DOCKER_CONFIG']=Pinned(self.host,fd,rows=rows)
        except BaseException:
            self.host.close(fd);raise
        private=(info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(0,0,DOCKER_CONFIG_MODE)
        self.entries_before=count_entries(self.host,fd,self.gate,MAX_COUNT);self.config_usable=private and self.entries_before==0
        return item_of(findings=[] if self.config_usable else ['DOCKER_CONFIG_NOT_PRIVATE_AND_EMPTY'],path=self.config_signed,private=private,
                       entries_before=self.entries_before,passed_to_the_docker_commands=self.config_usable)

    def configuration_after(self):
        handle=self.held.get('DOCKER_CONFIG');need(handle is not None and self.entries_before is not None,'DOCKER_CONFIG_DIRECTORY_UNAVAILABLE')
        entries=count_entries(self.host,handle.fd,self.gate,MAX_COUNT)
        return item_of(findings=[] if entries==self.entries_before else ['DOCKER_CONFIG_CHANGED_DURING_RUN'],entries_before=self.entries_before,entries_after=entries)

    def verify(self):
        """The one container of the run. Started before every other command: it needs its whole class time."""
        plan=self.plan;config=self.config();mounts=mounts_of(plan)
        if mounts:
            handle=self.held.get('BIND_PROBE' if self.pre else 'RELEASE_DIRECTORY')
            need(handle is not None,'BIND_PROBE_NOT_HELD' if self.pre else 'RELEASE_DIRECTORY_NOT_HELD');handle.verify(self.gate)
        result=container_run(self.commands,'verify',plan['image']['image_id'],mounts,VERIFY_COMMAND,self.frame,docker_config=config,container_name=self.name)
        facts={'started':result['started'],'returned':result['returned'],'returncode':result['returncode'],'binds':len(mounts),
               'frame_sha256':sha(self.frame),'snippet_sha256':VERIFY_SNIPPET_SHA256}
        if not result['returned']:
            # Not started: nothing ran. Started and not returned: the CLI was killed; "containers" says what is left.
            return dict(facts,status='UNAVAILABLE',code=result['code'] if text(result['code'],CODE) else 'VERIFY_RUN_NOT_COMPLETED',
                        container_may_still_exist=result['started'])
        if mounts:
            try:handle.verify(self.gate);facts['bind_source_stable']=True
            except Refused as error:
                if str(error) in EXPIRED_CODES:raise
                facts['bind_source_stable']=False
        code=result['returncode'];facts['engine_failure']=code in RUN_ENGINE_STATUSES
        try:line=verify_line(result['output'],code,plan,self.request_sha256)
        except Refused as error:return dict(facts,status='UNAVAILABLE',code=code_of(error,'VERIFY_OUTPUT_INVALID'),container_may_still_exist=False)
        if code!=0:
            if facts['engine_failure']:return item_of(findings=['VERIFY_ENGINE_FAILURE'],**facts)
            if line is None:return item_of(findings=['VERIFY_RUN_FAILED'],**facts)
            return item_of(findings=['VERIFY_SNIPPET_FAILED'],snippet_code=line['code'],**facts)
        release,policy=line['release'],line['policy'];findings=[]
        if mounts and not facts['bind_source_stable']:findings.append('BIND_SOURCE_REPLACED_DURING_RUN')
        if line['probe'] is not None and not line['probe']['valid']:findings.append('BIND_PROBE_NOT_READ')
        if not line['package_equal_signed']:findings.append('PACKAGE_NOT_THE_SIGNED_ONE')
        if not release['read']:findings.append('RELEASE_NOT_READ_IN_THE_CONTAINER')
        elif not release['bytes_equal_signed']:findings.append('RELEASE_BYTES_NOT_THE_SIGNED_ONES')
        if not release['verified']:findings.append('RELEASE_NOT_VERIFIED')
        elif not (release['mode_certified'] and release['epoch_equal'] and release['first_session_equal'] and release['ebar_bound']):
            findings.append('RELEASE_SCOPE_NOT_AS_SIGNED')
        if policy is not None:
            if not policy['hash_equal_signed']:findings.append('POLICY_BYTES_NOT_THE_SIGNED_ONES')
            if not all(item['valid'] for item in policy['controller_at']):findings.append('POLICY_REFUSED_BY_THE_CONTROLLER')
            if not policy['assembler']['valid']:findings.append('POLICY_REFUSED_BY_THE_ASSEMBLER')
        return item_of(findings=findings,release=release,policy=policy,probe=line['probe'],package_equal_signed=line['package_equal_signed'],image_facts=line['facts'],**facts)

    def containers(self):
        """Every container the engine knows, as counts; and whether the container of this run is still there."""
        rows,taken=self.timed(lambda:container_list(self.commands,self.config()));present=any(row['name']==self.name for row in rows)
        states={state:len([row for row in rows if row['state']==state]) for state in sorted({row['state'] for row in rows})}
        # a container an interrupted recreate of the worker's service left under its temporary name <hex>_<container>:
        # activate refuses on it before any effect (WORKER_SERVICE_LEFTOVER_CONTAINER; activate: leftovers)
        leftovers=len([row for row in rows if row['name'].endswith('_'+self.plan['worker']['container'])])
        return item_of(findings=(['VERIFY_CONTAINER_LEFT_BEHIND'] if present else [])+(['WORKER_SERVICE_LEFTOVER_CONTAINER'] if leftovers else [])+self.slow('quick_ms',taken),
                       command_ms=taken,listed=len(rows),by_state=states,worker_service_leftovers=leftovers,
                       worker_listed=any(row['name']==self.plan['worker']['container'] for row in rows),verify_container_present=present)

    def image(self):
        signed=self.plan['image'];facts,taken=self.timed(lambda:image_facts(self.commands,signed['reference'],self.config()));findings=self.slow('quick_ms',taken)
        equal=facts['id']==signed['image_id'];revision=facts['revision_label']==self.plan['revision']
        if not equal:findings.append('IMAGE_ID_MISMATCH')
        if not revision:findings.append('IMAGE_REVISION_MISMATCH')
        return item_of(findings=findings,command_ms=taken,reference=signed['reference'],id_equal_signed=equal,revision_equal_signed=revision,
                       repo_tag_count=facts['repo_tag_count'],reference_among_repo_tags=facts['reference_among_repo_tags'])

    def worker(self):
        signed=self.plan['worker'];facts,taken=self.timed(lambda:container_facts(self.commands,signed['container'],docker_config=self.config()));findings=self.slow('quick_ms',taken)
        self.worker_id=facts['id'];equal=facts['image_id']==self.plan['image']['image_id'];running=facts['running'] and facts['state']=='running'
        if not equal:findings.append('WORKER_IMAGE_MISMATCH')
        if not running:findings.append('WORKER_NOT_RUNNING')
        return item_of(findings=findings,command_ms=taken,container=signed['container'],image_id_equal_signed=equal,running=running,state=facts['state'],
                       restarts=facts['restarts'],health=facts['health'],started_at=facts['started_at'],
                       image_reference_equal_signed=facts['image_reference']==self.plan['image']['reference'])

    def worker_environment(self):
        """Booleans only: the revision of the worker, and that it has none of the four live names yet, with or without
        a value: activate refuses a worker that already carries one (WORKER_ALREADY_CARRIES_THE_KEYS), before any effect."""
        need(self.worker_id is not None,'WORKER_NOT_OBSERVED')
        values,taken=self.timed(lambda:container_environment(self.commands,self.worker_id,self.expected,docker_config=self.config()))
        build=values[BUILD_KEY]['equal'];present=[key for key in LIVE_KEYS if values[key]['present']]
        return item_of(findings=([] if build else ['WORKER_BUILD_REVISION_MISMATCH'])+(['WORKER_ALREADY_CARRIES_A_LIVE_NAME'] if present else [])
                                +self.slow('quick_ms',taken),command_ms=taken,build_revision_equal_signed=build,
                       live_names_present=len(present),
                       live_names_equal_to_the_intended_values=None if self.plan['render'] is None else len([key for key in LIVE_KEYS if values[key]['equal']]),
                       names={key:values[key] for key in sorted(values)})

    def render(self):
        """The render of the signed files, and the render with the override on standard input. Both stay in memory:
        what leaves is booleans and counts."""
        plan=self.plan;render=plan['render'];config=self.config();intended=override_of(plan)[1];findings=[]
        mark=self.monotonic()
        base=compose_render(self.commands,'render_base',render['project'],render['env_file'],render['files'],plan['revision'],docker_config=config)
        middle=self.monotonic()
        over=compose_render(self.commands,'render_override',render['project'],render['env_file'],render['files'],plan['revision'],override=self.override,docker_config=config)
        end=self.monotonic()
        before=compose_service(base,WORKER_SERVICE);after=compose_service(over,WORKER_SERVICE)
        equal={key:after['environment'].get(key)==intended[key] for key in LIVE_KEYS}
        build=after['environment'].get(BUILD_KEY)==plan['revision'];reference=after['image']==plan['image']['reference']
        others=set(base['services'])==set(over['services']) and all(base['services'][name]==over['services'][name] for name in base['services'] if name!=WORKER_SERVICE)
        project={key:value for key,value in base.items() if key!='services'}=={key:value for key,value in over.items() if key!='services'}
        def without(service,names):
            return {key:({name:item for name,item in value.items() if name not in names} if key=='environment' and type(value) is dict else value)
                    for key,value in service.items()}
        only=without(base['services'][WORKER_SERVICE],LIVE_KEYS)==without(over['services'][WORKER_SERVICE],LIVE_KEYS)
        if not all(equal.values()):findings.append('RENDER_ENVIRONMENT_NOT_AS_SIGNED')
        if not build:findings.append('RENDER_BUILD_REVISION_MISMATCH')
        if not reference:findings.append('RENDER_IMAGE_NOT_THE_SIGNED_REFERENCE')
        if not (others and project):findings.append('OVERRIDE_CHANGES_MORE_THAN_THE_WORKER')
        if not only:findings.append('OVERRIDE_CHANGES_MORE_THAN_THE_LIVE_NAMES')
        # the policy file and the release file of the override, reached through the one bind of the data volume
        volumes=over['services'][WORKER_SERVICE].get('volumes');worker=plan['worker']
        bound=data_bind_of(volumes,[intended[LIVE_KEYS[0]],intended[LIVE_KEYS[2]]],worker['data_source'],worker['data_target'])
        if bound is None:findings.append('RENDER_VOLUMES_INVALID')
        elif not bound:findings.append('WORKER_MOUNT_NOT_AS_SIGNED')
        bind={'volumes_listed':len(volumes) if type(volumes) is list else None,'policy_and_release_reached_through_the_one_signed_bind':bound}
        base_ms,override_ms=int((middle-mark)*1000),int((end-middle)*1000);findings+=self.slow('render_ms',base_ms,override_ms)
        return item_of(findings=findings,services=len(over['services']),environment_equal=equal,build_revision_equal=build,image_reference_equal_signed=reference,
                       other_services_unchanged=others and project,worker_changes_only_the_live_names=only,
                       live_names_already_in_the_base_render=len([key for key in LIVE_KEYS if key in before['environment']]),
                       data_volume_bind=bind,rendered_canonical_bytes=len(canonical(over)),
                       base_ms=base_ms,override_ms=override_ms)

    def deploy_files(self):
        """The deployed revision (content compared as activate compares it: the revision, surrounding white space
        aside; the pipeline writes the revision and one newline), and the inputs of compose by lstat: never their
        content or size."""
        tree=self.held.get('DEPLOY_TREE');need(tree is not None,'DIRECTORY_NOT_HELD')
        plan=self.plan;deploy,render=plan['deploy'],plan['render'];findings=[]
        try:
            raw,_=read_regular(self.host,deploy['version_name'],tree.fd,self.gate,MAX_REVISION_FILE_BYTES);version={'exists':True,'equal_to_the_signed_revision':raw.strip()==plan['revision'].encode('ascii')}
            if not version['equal_to_the_signed_revision']:findings.append('DEPLOYED_REVISION_MISMATCH')
        except FileNotFoundError:
            version={'exists':False,'equal_to_the_signed_revision':False};findings.append('DEPLOYED_REVISION_FILE_ABSENT')
        inputs=[]
        for path in ([] if render is None else [render['env_file']]+render['files']):
            found=probe(self.host,path,self.gate)
            if found.get('status')!='COMPLETE':raise Refused(found.get('code') if text(found.get('code'),CODE) else 'COMPOSE_INPUT_UNAVAILABLE')
            regular=found['exists'] and found['type']=='file'
            inputs.append({'exists':found['exists'],'regular':regular,'uid':found.get('uid'),'gid':found.get('gid'),'mode_octal':found.get('mode_octal'),'links':found.get('links')})
            if not regular:findings.append('COMPOSE_INPUT_ABSENT_OR_NOT_REGULAR')
        return item_of(findings=findings,deployed_revision=version,compose_inputs=inputs)

    def lstat_of(self,path,finding_when_present=None,finding_when_absent=None):
        found=probe(self.host,path,self.gate)
        if found.get('status')!='COMPLETE':raise Refused(found.get('code') if text(found.get('code'),CODE) else 'PROBE_UNAVAILABLE')
        findings=[finding_when_present] if found['exists'] and finding_when_present else [finding_when_absent] if not found['exists'] and finding_when_absent else []
        return item_of(findings=findings,exists=found['exists'],type=found.get('type'),uid=found.get('uid'),gid=found.get('gid'),mode_octal=found.get('mode_octal'))

    def pin(self):
        """The maintenance pin in the root of the data volume, by lstat: its presence holds the automatic routine."""
        found=self.lstat_of(self.plan['worker']['data_source']+'/'+PIN_NAME,finding_when_absent='MAINTENANCE_PIN_ABSENT')
        if found['exists'] and found['type']!='file':return item_of(findings=['MAINTENANCE_PIN_NOT_REGULAR'],exists=True,type=found['type'])
        if not found['exists']:return found
        owned=(found['uid'],found['gid'])==(0,0)
        # install_release refuses a pin that is not root:root (MAINTENANCE_PIN_NOT_ROOT_OWNED); after it, a fact
        return item_of(findings=['MAINTENANCE_PIN_NOT_ROOT_OWNED'] if self.pre and not owned else [],root_owned=owned,
                       **{key:found[key] for key in ('exists','type','uid','gid','mode_octal')})

    def unit(self,signed):
        name=signed['name'];raw=self.commands.output('unit',name)
        need(re.fullmatch(rb'[ -~\n]*',raw) is not None,'PROPERTY_OUTPUT_INVALID');values={}
        for line in raw.decode('ascii').splitlines():
            if not line:continue
            key,separator,value=line.partition('=');need(separator=='=','PROPERTY_LINE_INVALID')
            if key in UNIT_PROPERTIES:
                need(key not in values and text(value,'[A-Za-z0-9_./:@+ -]{0,512}'),'PROPERTY_VALUE_INVALID');values[key]=value
        need(set(values)==set(UNIT_PROPERTIES),'PROPERTY_MISSING');need(values['Id']==name,'UNIT_ID_MISMATCH')
        expected=signed['expected'] or {}
        return item_of(findings=[] if all(values[key]==value for key,value in expected.items()) else ['UNIT_STATE_NOT_AS_SIGNED'],
                       properties=values,expected=signed['expected'],gated=signed['expected'] is not None)

    def journal(self):
        """Free space of the filesystem of the journal root, on the root itself. A root that does not exist is a fact;
        it is a finding only when the request signs a floor."""
        signed=self.plan['journal'];floor=signed['floor_bytes']
        try:fd=descend(self.host,signed['path'],self.gate)
        except FileNotFoundError:
            return item_of(findings=[] if floor is None else ['JOURNAL_ROOT_ABSENT'],path=signed['path'],exists=False,floor_bytes=floor)
        try:
            info=self.host.fstat(fd);available=free_bytes(self.host,fd);entries=count_entries(self.host,fd,self.gate,MAX_COUNT);names={}
            for name in CATALOG_NAMES:
                self.gate()
                try:self.host.lstat(name,fd);names[name]=True
                except FileNotFoundError:names[name]=False
            above=None if floor is None else available>=floor
            return item_of(findings=['FREE_SPACE_BELOW_FLOOR'] if above is False else [],path=signed['path'],exists=True,owner_uid=info.st_uid,owner_gid=info.st_gid,
                           mode_octal='%04o'%stat.S_IMODE(info.st_mode),bytes_available=available,floor_bytes=floor,at_or_above_the_floor=above,
                           entries=entries,catalog_names_present=names)
        finally:self.host.close(fd)

    def lock(self):
        directory=self.held.get('LOCK_DIRECTORY');need(directory is not None,'DIRECTORY_NOT_HELD');name=self.plan['deploy']['lock_name']
        try:fd=open_lock(self.host,name,directory,self.gate)
        except Refused as error:
            if str(error)!='LOCK_FILE_ABSENT':raise
            return item_of(findings=['LOCK_FILE_ABSENT'],exists=False)
        try:
            state=probe_lock(self.host,fd);return item_of(exists=True,state=state,still_named=lock_still_named(self.host,name,directory,fd))
        finally:self.host.close(fd)

    def stable(self):
        """Every directory held is still the one its way from "/" shows."""
        result={}
        for key in sorted(self.held):
            try:self.held[key].verify(self.gate);result[key]=True
            except Refused as error:
                if str(error) in EXPIRED_CODES:raise
                result[key]=False
        return item_of(findings=[] if all(result.values()) else ['DIRECTORY_REPLACED_DURING_RUN'],directories=result)

    def close(self):
        for handle in self.held.values():
            try:handle.close()
            except Exception:pass


def _never_complete(receipt):
    """A receipt reduced for size says of itself that it is not the success of its mode (the core has already set its
    status and outcome): neither flag stays true, and it carries a constant code."""
    receipt['expectations_met']=False;receipt['gates_first_session_readback']=False
    if receipt.get('code') is None:receipt['code']='RECEIPT_REDUCED_FOR_SIZE'
def _drop_rows(receipt):
    _never_complete(receipt)
    for item in (receipt.get('items') or {}).values():
        if type(item) is dict and 'observed_rows' in item:item['observed_rows']=len(item['observed_rows'])
def _reduce_items(receipt):
    _never_complete(receipt)
    receipt['items']={name:{key:item.get(key) for key in ('status','matches','findings','code')} for name,item in (receipt.get('items') or {}).items()}
REDUCTIONS=[('OBSERVED_ROWS_REDUCED_TO_COUNTS',_drop_rows),('ITEMS_REDUCED_TO_STATUS',_reduce_items)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    commands=Commands(host,gate);reader=Readback(plan,host,gate,commands,bound,monotonic)                 # pure: nothing is touched
    release,deploy=plan['release'],plan['deploy'];items={};omitted=[];facts_only=set();pre=plan['mode']=='PRE'
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    def observe(label,action,gated=True):
        """One item, observed on its own. An expiry stops the run; any other failure is that item's UNAVAILABLE.
        gated False: the item carries no signed expectation (a fact): when it cannot be observed the receipt says so
        and the outcome is decided by the other items."""
        started=monotonic()
        if not gated:facts_only.add(label)
        try:
            gate();found=action()
        except Exception as error:found=safe(error)
        found['elapsed_ms']=int((monotonic()-started)*1000);items[label]=found
        if found.get('status')=='UNAVAILABLE' and found.get('code') in EXPIRED_CODES:raise Refused(found['code'])
    def optional(present,label,action,gated=True):
        if present:observe(label,action,gated)
        else:omitted.append(label)
    def finish(stop=None):
        findings=sorted({code for item in items.values() for code in item.get('findings') or []})
        incomplete=sorted(label for label,item in items.items() if item.get('status')!='COMPLETE')
        deciding=[label for label in incomplete if label not in facts_only]
        if stop is not None:status,outcome,code=PARTIAL_STATUS,PARTIAL_OUTCOME,stop
        elif deciding:status,outcome,code=PARTIAL_STATUS,PARTIAL_OUTCOME,findings[0] if findings else 'OBSERVATION_INCOMPLETE'
        elif findings:status,outcome,code=PARTIAL_STATUS,MISMATCH_OUTCOME,findings[0]
        else:status,outcome,code=COMPLETE_STATUS,success_of(plan),None
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),mode=plan['mode'],effects=effects_of(plan),
            clock=timing(begun,mark,clock,monotonic),commands_started=dict(commands.started),mutating_calls=state.counts(),items=items,
            findings=findings,items_not_complete=incomplete,fact_items_not_observed=[label for label in incomplete if label in facts_only],
            items_omitted_by_the_plan=omitted,dry_run=plan['dry_run'],expectations_met=status==COMPLETE_STATUS,
            gates_first_session_readback=status==COMPLETE_STATUS and plan['mode']=='POST',facts_reported_not_gated=FACTS_NOT_GATED,
            writes=0,containers_run=commands.started['CONTAINER'],phase_reached='OBSERVATION')))
    try:
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')                  # first, before anything is looked at
            observe('boot',reader.boot)
            # the release parent receives install_release's directory (still to come in PRE); the live parent receives activate's
            observe('directory:RELEASE_PARENT',lambda:reader.directory('RELEASE_PARENT',release['parent'],True,pre,plan['worker']['data_source']))
            for key,spec in (('DEPLOY_TREE',deploy['tree']),('LOCK_DIRECTORY',deploy['lock_directory'])):
                observe('directory:'+key,lambda key=key,spec=spec:reader.directory(key,spec))
            optional(plan['live'] is not None,'directory:LIVE_PARENT',lambda:reader.directory('LIVE_PARENT',plan['live']['parent'],True,True))
            optional(plan['bind_probe'] is not None,'directory:BIND_PROBE',lambda:reader.directory('BIND_PROBE',plan['bind_probe']['directory']))
            observe('release_target',reader.release_target)
            optional(plan['live'] is not None,'live_target',reader.live_target)
            optional(plan['docker_config'] is not None,'docker_config',reader.configuration)
            observe('verify',reader.verify)                                         # the container, before every other command
            observe('containers',reader.containers)
            observe('image',reader.image)
            observe('worker',reader.worker)
            optional(plan['worker']['environment'],'worker_environment',reader.worker_environment)
            optional(plan['render'] is not None,'render',reader.render)
            observe('deploy_files',reader.deploy_files)
            observe('maintenance_pin',reader.pin)
            for signed in plan['units']:observe('unit:'+signed['name'],lambda signed=signed:reader.unit(signed),signed['expected'] is not None)
            optional(plan['journal'] is not None,'journal',reader.journal,plan['journal'] is not None and plan['journal']['floor_bytes'] is not None)
            optional(deploy['lock_name'] is not None,'lock',reader.lock)
            observe('reboot_pending',lambda:reader.lstat_of(REBOOT_PENDING,finding_when_present='REBOOT_PENDING_MARKER_PRESENT'))
            observe('reboot_required',lambda:reader.lstat_of(REBOOT_REQUIRED),False)
            optional(plan['docker_config'] is not None,'docker_config_after',reader.configuration_after)
            observe('directories_stable',reader.stable)
        except Refused as error:
            code=code_of(error,'OBSERVATION_FAILED')
            if not items:
                return seal(envelope(REFUSED_STATUS,REFUSED_OUTCOME,code,dict(bound,phase_reached='BEFORE_ANY_OBSERVATION',mode=plan['mode'],
                                                                             mutating_calls=state.counts(),writes=0)))
            return finish(code)
        return finish()
    finally:reader.close()
