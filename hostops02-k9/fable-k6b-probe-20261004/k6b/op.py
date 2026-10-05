OPERATION='GO_WRITE_HOSTOPS02_CAPACITY_SWITCH_01'
PHASE='WRITE_CAPACITY_SWITCH_ENV_FILE_AND_RECREATE_WORKER'
REQUEST_SCHEMA='WRITE_HOSTOPS02_CAPACITY_SWITCH_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_CAPACITY_SWITCH_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_CAPACITY_SWITCH_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_CAPACITY_SWITCH_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_CAPACITY_SWITCH_PLAN_V1'
SOURCE_NAME='capacity_switch.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False                  # no systemd unit is switched: an edit of the environment file and the recreate of a compose service
DATE_CLASS='WRITE_SESSIONS'               # 10-05 .. 10-10 UTC: mount/enable Mon-Thu after the close, fast disable Mon-Fri, full disable Fri
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
EVIDENCE_OPERATIONS=('GO_WRITE_HOSTOPS02_ACTIVATE_01',)                 # M3's receipt: the override file this run renders and recreates with (decision C-13)
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='CAPACITY_SWITCH_APPLIED_WORKER_RECREATED_AND_VERIFIED'
PARTIAL_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
# the partial outcomes of a run that returned its own receipt (PARTIAL_OUTCOME itself is what an escaped run says)
# a stop BEFORE the recreate was started, and a stop AFTER it was started, are separate states (Codex decision 1)
ENV_ONLY_OUTCOME='PARTIAL_ENV_FILE_EDITED_RECREATE_NOT_STARTED'
WITHDRAWN_OUTCOME='PARTIAL_ENV_EDIT_WITHDRAWN_RECREATE_NOT_STARTED'
RECREATE_FAILED_OUTCOME='PARTIAL_ENV_FILE_EDITED_RECREATE_FAILED_WORKER_UNCHANGED'
NOT_VERIFIED_OUTCOME='PARTIAL_WORKER_RECREATED_NOT_FULLY_VERIFIED'
UNCERTAIN_OUTCOME='PARTIAL_UNCERTAIN_REQUIRES_READBACK'

# ---------------------------------------------------------------- the epoch and the deploy layout, as K6a signs them
EPOCH_NAME='R2D2-V2-SHADOW-2026-10-05'                                                        # r2d2_v2_epoch_assembler.py:9
EPOCH_REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'                                     # .deploy-version and C3PO_BUILD_SHA
WORKER_SERVICE='r2d2-worker'
BUILD_KEY='C3PO_BUILD_SHA'
ACTIVATION_KEYS=('C3PO_R2D2_V2_LIVE_POLICY_FILE','C3PO_R2D2_V2_LIVE_POLICY_SHA','C3PO_R2D2_V2_SHADOW_RELEASE_FILE','C3PO_R2D2_V2_SHADOW_RELEASE_SHA')
ENV_FILE_NAME='.env'
COMPOSE_FILE_NAME='compose.yml'
DEPLOY_VERSION_NAME='.deploy-version'
LOCK_RELATIVE_DIRECTORY='runtime/security'
LOCK_FILE_NAME='deployment.lock'
REBOOT_PENDING_PATH='/run/c3po-security/reboot.pending'
MAX_ENV_FILE_BYTES=1048576
MAX_COMPOSE_FILE_BYTES=1048576
MAX_OVERRIDE_BYTES=4096
MAX_CONFIG_BYTES=1048576
# ---------------------------------------------------------------- the capacity settings (c3po/deployment/capacity-mount/README.md at the release)
KEY_MOUNT_SOURCE='C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE'                                         # read by compose only: compose.yml:169
KEY_CONFIG_FILE='C3PO_R2D2_V2_CAPACITY_CONFIG_FILE'                                           # config.py:201
KEY_CONFIG_SHA='C3PO_R2D2_V2_CAPACITY_CONFIG_SHA'                                             # config.py:202
KEY_VETO_MODE='C3PO_R2D2_V2_CAPACITY_VETO_MODE'                                               # config.py:200
KEY_REQUIRED='C3PO_R2D2_V2_CAPACITY_REQUIRED'                                                 # config.py:199
CAPACITY_KEYS=(KEY_MOUNT_SOURCE,KEY_CONFIG_FILE,KEY_CONFIG_SHA,KEY_VETO_MODE,KEY_REQUIRED)    # the order of the trailing block this source keeps in .env
VETO_MODE_VALUE='DISPATCH_AND_DERIVATION_ONLY'
REQUIRED_VALUE='true'
CAPACITY_TARGET='/c3po-capacity'
CAPACITY_SUBDIRECTORIES=('config','documents','go','payload')
PLACEHOLDER_VOLUME='c3po_capacity_unprovisioned'
DATA_TARGET='/app/day-d-data'
WORKER_TARGETS=('/app/day-d-data','/c3po-capacity','/run/c3po-maintenance')                  # check_compose_render.py:26
CAPACITY_LINE=re.compile(b'[ \t]*(?:export[ \t]+)?C3PO_R2D2_V2_CAPACITY_')                    # any line compose's dotenv parser could read as a capacity setting
# ---------------------------------------------------------------- the four modes: how many lines of the block exist before and after
MODES={'MOUNT':{'before':(0,),'after':1},'ENABLE':{'before':(1,),'after':5},
       'DISABLE_FAST':{'before':(5,),'after':4},'DISABLE_FULL':{'before':(1,4,5),'after':0}}
# ---------------------------------------------------------------- the editor of the environment file: one attached container
ENV_OWNER=(1000,1000)                     # the operational account that owns .env (the deploy writes it); the editor runs as that account, never as root
ENV_MODE=0o600
ENV_EDITOR_TARGET='/c3po-env/.env'
ENV_EDITOR_COMMAND=['python','-I','-B','-']
ENV_EDITOR_PREFIX=['run','--rm','-i','--pull','never','--init','--user','%d:%d'%ENV_OWNER,'--network','none','--read-only','--cap-drop','ALL',
                   '--security-opt','no-new-privileges']
ENV_EDIT_SCRIPT='''import ctypes,json,os,re,stat,sys
TARGET='/c3po-env/.env'
CAPACITY=re.compile(b'[ \\t]*(?:export[ \\t]+)?C3PO_R2D2_V2_CAPACITY_')
LIMIT=1048576
class Stop(Exception):pass
def not_dumpable():
    try:
        library=ctypes.CDLL(None,use_errno=True)
        return library.prctl(4,0,0,0,0)==0 and library.prctl(3,0,0,0,0)==0
    except Exception:return False
def say(status,code=None):
    sys.stdout.write(json.dumps({'code':code,'status':status},sort_keys=True)+'\\n');sys.stdout.flush()
def read_all(fd,size):
    chunks=[];offset=0
    while offset<=size:
        block=os.pread(fd,65536,offset)
        if not block:break
        chunks.append(block);offset+=len(block)
    return b''.join(chunks)
def edited(raw,spec):
    if raw!=b'' and not raw.endswith(b'\\n'):raise Stop('ENV_FILE_NOT_NEWLINE_TERMINATED')
    lines=raw[:-1].split(b'\\n') if raw else []
    marks=[index for index,line in enumerate(lines) if CAPACITY.match(line)]
    count=len(marks);head=lines[:len(lines)-count]
    if marks!=list(range(len(lines)-count,len(lines))):raise Stop('ENV_CAPACITY_LINES_NOT_TRAILING')
    if [line.decode('latin-1') for line in lines[len(lines)-count:]] not in spec['before']:raise Stop('ENV_CAPACITY_BLOCK_NOT_AS_SIGNED')
    return b''.join(line+b'\\n' for line in head)+b''.join(line.encode('ascii')+b'\\n' for line in spec['after'])
def main(spec):
    wrote=False
    try:
        if not not_dumpable():raise Stop('EDITOR_DUMPABLE_NOT_DISABLED')
        try:fd=os.open(TARGET,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
        except OSError:raise Stop('ENV_FILE_OPEN')
        try:
            info=os.fstat(fd)
            if not (stat.S_ISREG(info.st_mode) and info.st_nlink==1 and [info.st_uid,info.st_gid]==spec['owner']
                    and stat.S_IMODE(info.st_mode)==spec['mode'] and info.st_size<=LIMIT):raise Stop('ENV_FILE_NOT_AS_EXPECTED')
            raw=read_all(fd,info.st_size)
            if len(raw)!=info.st_size:raise Stop('ENV_FILE_CHANGED_DURING_READ')
            new=edited(raw,spec)
            again=os.fstat(fd)
            if (again.st_size,again.st_mtime_ns,again.st_ino)!=(info.st_size,info.st_mtime_ns,info.st_ino) or read_all(fd,info.st_size)!=raw:
                raise Stop('ENV_FILE_CHANGED_DURING_THE_EDIT')
            if len(new)>len(raw) and new[:len(raw)]==raw:
                data=new[len(raw):];wrote=True;written=os.pwrite(fd,data,len(raw))
                if written!=len(data):
                    os.ftruncate(fd,len(raw));os.fsync(fd);say('ENV_EDIT_FAILED','ENV_SHORT_WRITE_WITHDRAWN');return 3
            elif len(new)<len(raw) and raw[:len(new)]==new:
                wrote=True;os.ftruncate(fd,len(new))
            else:raise Stop('ENV_EDIT_NOT_AN_APPEND_OR_A_CUT')
            os.fsync(fd)
            say('ENV_EDIT_DONE');return 0
        finally:os.close(fd)
    except Stop as error:
        say('ENV_EDIT_REFUSED',str(error));return 1
    except Exception:
        if wrote:say('ENV_EDIT_FAILED','ENV_EDIT_OS_ERROR');return 3
        say('ENV_EDIT_REFUSED','ENV_EDIT_OS_ERROR');return 1
'''
ENV_EDIT_SCRIPT_SHA256=sha(ENV_EDIT_SCRIPT.encode('ascii'))
ENV_EDIT_STATUSES=('ENV_EDIT_DONE','ENV_EDIT_REFUSED','ENV_EDIT_FAILED')
# The source's own process, first of all (as the token program, core section 14): the core's NativeRead.not_dumpable()
# sets the dumpable attribute to 0 and reads it back 0 (prctl(2)) before the deploy tree or .env is opened; the editor's
# process does the same before it opens the file. A process that is not dumpable produces no core dump, to a file or
# through a pipe to a crash collector. Otherwise: refused, nothing changed.
PROCESS_SCOPE={'dumpable':0,'how':'prctl(PR_SET_DUMPABLE, 0), then prctl(PR_GET_DUMPABLE) must answer 0 (the core\'s dumps_disabled)',
               'when':'first, before the deploy directory, the environment file or anything else is opened',
               'editor':'the editor container\'s process makes itself non-dumpable the same way before it opens the file; otherwise EDITOR_DUMPABLE_NOT_DISABLED, nothing written',
               'bytes_of_the_file':'held only in the memory of those two processes; no byte outside the trailing capacity block is written back; no copy, log, argv or output',
               'otherwise':'refused, nothing changed: PROCESS_DUMPABLE_NOT_DISABLED'}
MOUNTS_FORMAT='{{json .Mounts}}'
MAX_MOUNTS_LISTED=32
# ---------------------------------------------------------------- the budget (seconds of the 60 a run has)
SETTLE_SECONDS=3                          # the one fixed pause, between the two readings of the new worker (as K6a)
SECOND_CHECK_RESERVE_SECONDS=2
FILES_ALLOWANCE_SECONDS=1                 # the readbacks of the environment file between the effects
UNDER_LOCK_ALLOWANCE_SECONDS=2
RENDER_ALLOWANCE_FLOOR_SECONDS=3

PLAN_KEYS=frozenset(('mode','data_root','capacity','override','worker','compose','deploy_directory','lock','probe_load_receipt_sha256','withdrawal_authorized',
                     'evidence_boot_id_sha256'))
CAPACITY_KEYS_OF_PLAN=frozenset(('root','config_name','config_sha256'))
OVERRIDE_KEYS=frozenset(('directory','name','environment'))
WORKER_KEYS=frozenset(('image_id',))
COMPOSE_KEYS=frozenset(('project','env_file','files'))
LOCK_KEYS=frozenset(('directory','wait_seconds'))
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'one image ID or reference','QUICK','READ'),
          'container':command_row('docker',['container','inspect','--format',CONTAINER_FORMAT],'one container name or ID','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          'container_environment':command_row('docker',['container','inspect','--format'],'the presence and equality template, then one container ID','QUICK','READ'),
          'container_mounts':command_row('docker',['container','inspect','--format',MOUNTS_FORMAT],'one container ID','QUICK','READ'),
          'render_files':command_row('docker',['compose'],'--project-name, --env-file, the compose file of the deploy and the delivered override file','RENDER','READ',tail=COMPOSE_CONFIG_TAIL),
          'edit_env':command_row('docker',ENV_EDITOR_PREFIX,'one read-write bind of the environment file at '+ENV_EDITOR_TARGET+', the image ID, python -I -B -','QUICK','EFFECT',stdin=True),
          'recreate':command_row('docker',['compose'],'--project-name, --env-file, the compose file of the deploy and the delivered override file','RECREATE','EFFECT',tail=compose_up_tail(WORKER_SERVICE))}
SUCCESS_CRITERIA=['the environment file is the same object (device, inode, owner, mode, one link) holding exactly the signed edit of its bytes: the trailing capacity block replaced by the signed one, every other byte as it was',
                  'the render from the edited file gives the worker the capacity mount and the capacity names of the mode, the four names of the activation and the build revision',
                  'the recreate command returned 0',
                  'exactly one container carries the name of the service and it is not the container that was there before; that one no longer exists under any name',
                  'the new container is running with restart count 0 on the signed image, read twice with a fixed pause between; the second reading shows the same container and the same start instant',
                  'its environment carries the names of the mode with the signed values and lacks the others, compared inside a docker template that prints booleans',
                  'its mount at /c3po-capacity is the one of the mode (the read-only bind of the signed tree, or the placeholder volume) and the data root is still bound',
                  'every other container is listed with the ID and the name it had under the lock before the recreate, and no other container appeared',
                  'the compose file and the override file are the same objects with the same bytes as at the first look; the lock file is still the one held']
SCOPE_STATEMENT=('Epoch R2D2-V2-SHADOW-2026-10-05, session days 2026-10-05 to 2026-10-10 UTC. One signed mode per request: MOUNT, ENABLE, '
                 'DISABLE_FAST or DISABLE_FULL of the capacity of the compose service r2d2-worker. Under the deployment lock: edits the '
                 'environment file of the compose project in place, through one attached container of the signed backend image run as the '
                 'account that owns that file, with no network, a read-only root and that one file bound read-write, which appends or cuts '
                 'the trailing block of capacity settings and nothing else; then renders the project with the compose file of the deploy '
                 'plus the override file of the activation, and recreates that one service with the same file list: one docker compose up '
                 '-d --no-deps --no-build --pull never --force-recreate. The running worker container is stopped and replaced. Rule 4 of '
                 'the core (nothing that exists is overwritten) is NOT preserved: the environment file is edited in place under the one '
                 'exception of this core generation (IN_PLACE_EDIT_EXCEPTION). Only when the request authorizes it, and only when the run '
                 'stops BEFORE the recreate was started, after an edit that was confirmed and read back, with the lock still held, the edit '
                 'is withdrawn by a second run of the same editor; never after the recreate was started. No other file, container, image or unit is changed; the '
                 'capacity tree is read, never written. No docker exec, no shell, no systemctl, no pull. No value of an environment, of the '
                 'render or of the environment file is printed, stored or put in an argv, with three exceptions that are not values of '
                 'the environment: the image reference the render names and the container IDs the engine prints are passed to docker '
                 'inspect, and the receipt says which of the signed capacity blocks the environment file held. The signed capacity values '
                 'travel on the standard input of the editor and, with the four values of the activation and the build revision, in the '
                 'argv of the docker template that compares them.')

def capacity_root_path(plan):return plan['capacity']['root'][-1]['path']
def config_container_path(plan):return CAPACITY_TARGET+'/config/'+plan['capacity']['config_name']
def capacity_values(plan):
    """The five values of the block, in its order; nothing is free: each follows from a signed member or is a constant."""
    return {KEY_MOUNT_SOURCE:capacity_root_path(plan),KEY_CONFIG_FILE:config_container_path(plan),KEY_CONFIG_SHA:plan['capacity']['config_sha256'],
            KEY_VETO_MODE:VETO_MODE_VALUE,KEY_REQUIRED:REQUIRED_VALUE}
def block_lines(plan,count):
    values=capacity_values(plan);return ['%s=%s'%(key,values[key]) for key in CAPACITY_KEYS[:count]]
def edit_spec(plan,before_counts=None,after_count=None):
    mode=MODES[plan['mode']]
    before=mode['before'] if before_counts is None else before_counts;after=mode['after'] if after_count is None else after_count
    return {'before':[block_lines(plan,count) for count in before],'after':block_lines(plan,after),'owner':list(ENV_OWNER),'mode':ENV_MODE}
def editor_stdin(spec):
    """The bytes the editor runs: the pinned script, then one line that calls it with the spec as a JSON text. The spec
    holds signed values only (paths, a hash, constants): nothing of the environment file is in it."""
    return (ENV_EDIT_SCRIPT+'raise SystemExit(main(json.loads(%s)))\n'%json.dumps(json.dumps(spec,sort_keys=True,separators=(',',':')))).encode('ascii')
def editor_name(bound):return 'hostops02-k6b-'+bound['go_sha256'][:16]
def editor_mounts(plan):return [{'source':plan['compose']['env_file'],'target':ENV_EDITOR_TARGET,'read_only':False}]
def override_path(plan):return plan['override']['directory'][-1]['path']+'/'+plan['override']['name']
def override_bytes(plan):
    """The override of the activation exactly as K6a writes it (activate/op.py override_of): the four signed values."""
    return json.dumps({'services':{WORKER_SERVICE:{'environment':dict(plan['override']['environment'])}}},sort_keys=True).encode('ascii')
def deploy_path(plan):return plan['deploy_directory'][-1]['path']
def lock_path(plan):return plan['lock']['directory'][-1]['path']+'/'+LOCK_FILE_NAME
def worker_name(plan):return '%s-%s-1'%(plan['compose']['project'],WORKER_SERVICE)
def file_list(plan):return plan['compose']['files']+[override_path(plan)]
def expected_environment(plan,count):
    """{name: value} compared in the worker; the names of the block beyond count must be absent."""
    values=dict(plan['override']['environment']);values[BUILD_KEY]=EPOCH_REVISION;values.update(capacity_values(plan))
    return values
def present_names(plan,count):return set(ACTIVATION_KEYS)|{BUILD_KEY}|set(CAPACITY_KEYS[:count])
def placeholder_name(plan):return plan['compose']['project']+'_'+PLACEHOLDER_VOLUME

def chain_path(rows):
    need(type(rows) is list and rows and type(rows[-1]) is dict,'CHAIN_ROW_INVALID');return rows[-1].get('path')     # its spelling: validate_chain
def signed_chain(rows,open_root,receives_entry=False):return validate_chain(rows,chain_path(rows),open_root,receives_entry)

def validate_plan(plan):
    need(plan['mode'] in MODES,'MODE_INVALID')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    root=plan['data_root']                                    # its spelling is judged by validate_chain as an open root (PATH_INVALID)
    capacity=plan['capacity']
    need(type(capacity) is dict and set(capacity)==set(CAPACITY_KEYS_OF_PLAN) and text(capacity['config_name'],FILE_NAME)
         and hexpin(capacity['config_sha256']),'CAPACITY_REQUEST_INVALID')
    tree=chain_path(capacity['root']);signed_chain(capacity['root'],None)          # root-owned from '/', not writable by group or other
    need(text(tree,MOUNT_PATH),'CAPACITY_REQUEST_INVALID')
    override=plan['override']
    need(type(override) is dict and set(override)==set(OVERRIDE_KEYS) and text(override['name'],FILE_NAME) and type(override['environment']) is dict
         and set(override['environment'])==set(ACTIVATION_KEYS),'OVERRIDE_REQUEST_INVALID')
    signed_chain(override['directory'],root)
    need(inside(chain_path(override['directory']),root) and chain_path(override['directory'])!=root,'OVERRIDE_OUTSIDE_DATA_ROOT')
    worker=plan['worker']
    need(type(worker) is dict and set(worker)==set(WORKER_KEYS) and text(worker['image_id'],IMAGE_ID),'WORKER_REQUEST_INVALID')
    compose=plan['compose']
    need(type(compose) is dict and set(compose)==set(COMPOSE_KEYS),'COMPOSE_REQUEST_INVALID')
    compose_arguments(compose['project'],compose['env_file'],file_list(plan))
    deploy=chain_path(plan['deploy_directory']);signed_chain(plan['deploy_directory'],deploy)
    need(compose['env_file']==deploy+'/'+ENV_FILE_NAME and compose['files']==[deploy+'/'+compose['project']+'/'+COMPOSE_FILE_NAME],'COMPOSE_NOT_THE_DEPLOY_LAYOUT')
    need(not inside(root,deploy) and not inside(deploy,root),'PATHS_OVERLAP')
    # the tree must lie neither in the data volume (three services reach it read-write there) nor in the deploy tree (the next rsync removes it)
    need(not inside(tree,root) and not inside(root,tree) and not inside(tree,deploy) and not inside(deploy,tree),'CAPACITY_TREE_PLACEMENT')
    lock=plan['lock']
    need(type(lock) is dict and set(lock)==set(LOCK_KEYS) and integer(lock['wait_seconds'],0,MAX_LOCK_WAIT_SECONDS),'LOCK_REQUEST_INVALID')
    signed_chain(lock['directory'],deploy)
    need(lock['directory'][-1]['path']==deploy+'/'+LOCK_RELATIVE_DIRECTORY,'LOCK_NOT_THE_DEPLOYMENT_LOCK')
    need(hexpin(plan['probe_load_receipt_sha256']) if plan['mode']=='ENABLE' else plan['probe_load_receipt_sha256'] is None,'LOAD_EVIDENCE_INVALID')
    need(type(plan['withdrawal_authorized']) is bool,'WITHDRAWAL_REQUEST_INVALID')
    environment_format(expected_environment(plan,5))                         # every value fits the grammar of the template
    run_arguments('edit_env',worker['image_id'],editor_mounts(plan),ENV_EDITOR_COMMAND)

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    mode=MODES[plan['mode']];compose=plan['compose'];stdin=editor_stdin(edit_spec(plan));overrides=override_bytes(plan)
    after=mode['after'];values=capacity_values(plan)
    return {'operation':OPERATION,'mode':plan['mode'],'epoch':EPOCH_NAME,'revision':EPOCH_REVISION,
            'environment_file':{'path':compose['env_file'],'owner':list(ENV_OWNER),'mode_octal':'%04o'%ENV_MODE,
                                'trailing_capacity_block_before_one_of':[block_lines(plan,count) for count in mode['before']],
                                'trailing_capacity_block_after':block_lines(plan,after),
                                'rule':'no capacity line outside the trailing block; every other byte unchanged; same object'},
            'editor':{'row':'edit_env','argv_prefix':ENV_EDITOR_PREFIX,'image_id':plan['worker']['image_id'],'mounts':editor_mounts(plan),
                      'command':ENV_EDITOR_COMMAND,'script_sha256':ENV_EDIT_SCRIPT_SHA256,'stdin_sha256':sha(stdin),'stdin_bytes':len(stdin),
                      'container_name':'hostops02-k6b-<first 16 hex of the GO hash>[-withdraw]'},
            'withdrawal':{'authorized':plan['withdrawal_authorized'],'row':'edit_env','container_name':'hostops02-k6b-<first 16 hex of the GO hash>-withdraw',
                          'stdin_sha256_by_block_found':({str(count):sha(editor_stdin(edit_spec(plan,(after,),count))) for count in mode['before']}
                                                         if plan['withdrawal_authorized'] else {}),
                          'when':'only if authorized here; only BEFORE the recreate is started, after an edit the editor confirmed and the host read back, '
                                 'while the lock file is still the one held; never after the recreate was started, whatever it did',
                          'effect':'the inverse edit of E1, by the same row: the trailing block found before is put back; every other byte unchanged'},
            'process':{'dumpable':0,'when':'first, before the deploy directory or the environment file is opened; the editor before it opens the file',
                       'core_dump':'none, to a file or through a pipe'},
            'core_exception':{'rule_4_preserved':False,'core_sha256':CORE_SHA256,'exception':'IN_PLACE_EDIT_EXCEPTION of this core generation: row edit_env of '
                              'source capacity_switch edits <deploy>/.env in place (append to, or cut the end of, the trailing capacity block)'},
            'bind_source_chain':{'rows':[{key:row[key] for key in ('path','uid','gid','mode')} for row in plan['deploy_directory']]+
                                        [{'path':compose['env_file'],'uid':ENV_OWNER[0],'gid':ENV_OWNER[1],'mode':ENV_MODE}],
                                 'all_root_controlled':all(row['uid']==0 for row in plan['deploy_directory']) and ENV_OWNER[0]==0,
                                 'note':'decision 6 asks every bind source and its ancestors to be root-controlled; this one is not (open item)'},
            'override':{'path':override_path(plan),'sha256':sha(overrides),'bytes':len(overrides),'directory':chain_effects(plan['override']['directory']),
                        'environment':dict(plan['override']['environment']),'expect':'DELIVERED_BY_THE_ACTIVATION_READ_AND_COMPARED_NEVER_WRITTEN'},
            'capacity_tree':{'host_path':capacity_root_path(plan),'root':chain_effects(plan['capacity']['root']),'container_target':CAPACITY_TARGET,
                             'config_file':config_container_path(plan),'config_sha256':plan['capacity']['config_sha256'],
                             'read':plan['mode'] in ('MOUNT','ENABLE'),'expect':'READ_NEVER_WRITTEN'},
            'recreate':{'project':compose['project'],'env_file':compose['env_file'],'files':file_list(plan),'service':WORKER_SERVICE,
                        'container':worker_name(plan),'image_id':plan['worker']['image_id'],'build_sha':EPOCH_REVISION,
                        'lock':lock_path(plan),'lock_wait_seconds':plan['lock']['wait_seconds'],'lock_chain_sha256':sha(canonical(plan['lock']['directory'])),
                        'deploy_directory':chain_effects(plan['deploy_directory'])},
            'worker_after':{'environment_present':{key:values[key] for key in CAPACITY_KEYS[:after]},'environment_absent':list(CAPACITY_KEYS[after:]),
                            'activation_environment':dict(plan['override']['environment']),
                            'capacity_mount':({'type':'bind','source':capacity_root_path(plan),'target':CAPACITY_TARGET,'read_only':True} if after
                                              else {'type':'volume','name':placeholder_name(plan),'target':CAPACITY_TARGET,'read_only':True}),
                            'data_mount':{'type':'bind','source':plan['data_root'],'target':DATA_TARGET}},
            'required':{'reboot_pending_marker_absent':REBOOT_PENDING_PATH,'deploy_version':EPOCH_REVISION,
                        'probe_load_receipt_sha256':plan['probe_load_receipt_sha256'],
                        'worker_running_before':plan['mode'] in ('MOUNT','ENABLE')},
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'pre_existing_objects_modified':'THE_ENVIRONMENT_FILE_IS_EDITED_IN_PLACE_AND_THE_WORKER_CONTAINER_IS_REPLACED','activation':False}
def success_of(plan):return COMPLETE_OUTCOME

SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'after_effect_reserve_seconds':AFTER_EFFECT_RESERVE_SECONDS,
       'modes':MODES,'capacity_keys_in_block_order':list(CAPACITY_KEYS),'veto_mode':VETO_MODE_VALUE,'required_value':REQUIRED_VALUE,
       'capacity_target':CAPACITY_TARGET,'capacity_subdirectories':list(CAPACITY_SUBDIRECTORIES),'placeholder_volume':PLACEHOLDER_VOLUME,
       'worker_targets':list(WORKER_TARGETS),'data_target':DATA_TARGET,
       'editor':{'owner':list(ENV_OWNER),'mode':ENV_MODE,'target':ENV_EDITOR_TARGET,'command':ENV_EDITOR_COMMAND,'script_sha256':ENV_EDIT_SCRIPT_SHA256,
                 'statuses':list(ENV_EDIT_STATUSES)},
       'mounts_format':MOUNTS_FORMAT,'process':PROCESS_SCOPE,
       'budget':{'settle_seconds':SETTLE_SECONDS,'second_check_reserve_seconds':SECOND_CHECK_RESERVE_SECONDS,'files_allowance_seconds':FILES_ALLOWANCE_SECONDS,
                 'under_lock_allowance_seconds':UNDER_LOCK_ALLOWANCE_SECONDS,'render_allowance_floor_seconds':RENDER_ALLOWANCE_FLOOR_SECONDS,
                 'rule':'before the lock is asked for and again before the first effect: edit class + recreate class + reserve + render allowance + files + settle must be left'},
       'files':FILES_SCOPE,'lock':LOCK_SCOPE,'service':WORKER_SERVICE,'activation_names':list(ACTIVATION_KEYS),'build_name':BUILD_KEY,
       'epoch':{'name':EPOCH_NAME,'revision':EPOCH_REVISION},
       'deploy_layout':{'environment_file':ENV_FILE_NAME,'compose_file':'<project>/'+COMPOSE_FILE_NAME,'deploy_version':DEPLOY_VERSION_NAME,
                        'lock':LOCK_RELATIVE_DIRECTORY+'/'+LOCK_FILE_NAME},
       'success_criteria':SUCCESS_CRITERIA,
       'partial_outcomes':[ENV_ONLY_OUTCOME,WITHDRAWN_OUTCOME,RECREATE_FAILED_OUTCOME,NOT_VERIFIED_OUTCOME,UNCERTAIN_OUTCOME,PARTIAL_OUTCOME],
       'failure_phases':['BEFORE_THE_EDIT','BEFORE_THE_RECREATE','AFTER_THE_RECREATE_STARTED'],
       'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'file_contents_read':[BOOT_ID_PATH,DEPLOY_VERSION_NAME+' of the deploy tree',
                             'the environment file of the compose project: read into memory, edited only by the editor container, compared with the signed edit; no value, digest or size of it leaves the run',
                             'the compose file of the deploy: compared with itself, never judged as text (the render is)',
                             'the override file of the activation: compared with the four signed values',
                             'the static capacity config in the config directory of the tree (MOUNT, ENABLE): compared with the signed hash'],
       'side_effects':['the environment file of the compose project gains or loses the trailing capacity lines of the mode: every service that is created later from it (all six backend services) gets them',
                       'the worker container is stopped and replaced by a new one (new ID); what it held in memory is lost',
                       'the deployment lock is held from before the first effect until the last readback'],
       'never':['overwrite of any byte of the environment file that is not in the trailing capacity block','chmod','chown','rename','removal of any file',
                'docker exec','a shell','systemctl','a pull','a build','a second recreate','a change of the compose file, of the override or of the capacity tree',
                'a network connection opened by this process or by the editor'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'environment_file_bytes':MAX_ENV_FILE_BYTES,'compose_file_bytes':MAX_COMPOSE_FILE_BYTES,'override_bytes':MAX_OVERRIDE_BYTES,
                 'config_bytes':MAX_CONFIG_BYTES,'lock_wait_seconds':MAX_LOCK_WAIT_SECONDS,'mounts_listed':MAX_MOUNTS_LISTED}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner,NativeFiles,NativeLock):
    """Everything this source can do to the host: the read primitives, the signed commands, the lock. Of the files
    part it uses the umask only: this source creates no file and no directory of its own."""


# ---------------------------------------------------------------- the environment file, in memory (pure)
def env_lines(raw):
    need(raw==b'' or raw.endswith(b'\n'),'ENV_FILE_NOT_NEWLINE_TERMINATED')
    return raw[:-1].split(b'\n') if raw else []
def edited_env(raw,spec):
    """(new bytes, the block found): the same rule the editor applies, computed here first and compared after. The
    capacity lines must be the trailing lines of the file and be exactly one of the signed blocks."""
    lines=env_lines(raw);marks=[index for index,line in enumerate(lines) if CAPACITY_LINE.match(line)]
    count=len(marks);head=lines[:len(lines)-count]
    need(marks==list(range(len(lines)-count,len(lines))),'ENV_CAPACITY_LINES_NOT_TRAILING')
    block=[line.decode('latin-1') for line in lines[len(lines)-count:]]
    need(block in spec['before'],'ENV_CAPACITY_BLOCK_NOT_AS_SIGNED')
    # the signed blocks are prefixes of one another: the result is always an append to the end or a cut of the end
    return b''.join(line+b'\n' for line in head)+b''.join(line.encode('ascii')+b'\n' for line in spec['after']),block


# ---------------------------------------------------------------- what is read on the host
def hold(host,fd,pinned,**how):
    try:holder=Pinned(host,fd,**how)
    except BaseException:
        host.close(fd);raise
    pinned.append(holder);return holder

def deploy_version(host,directory,gate):
    gate()
    try:named=host.lstat(DEPLOY_VERSION_NAME,directory.fd)
    except FileNotFoundError:raise Refused('DEPLOY_VERSION_ABSENT') from None
    need(stat.S_ISREG(named.st_mode),'DEPLOY_VERSION_NOT_REGULAR')
    raw,_=read_regular(host,DEPLOY_VERSION_NAME,directory.fd,gate,128)
    need(raw.strip()==EPOCH_REVISION.encode('ascii'),'DEPLOY_VERSION_MISMATCH')

def identity_of(info):
    """The object, without its content: what an in-place edit keeps (device, inode, owner, group, mode, links)."""
    return (info.st_dev,info.st_ino,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)

def env_file_read(host,directory,gate):
    """(bytes, fstat) of the environment file: a regular file of the editor's account, mode 0600, one link. The bytes
    stay in memory: no value, digest or size of that file leaves the run."""
    gate()
    try:named=host.lstat(ENV_FILE_NAME,directory.fd)
    except FileNotFoundError:raise Refused('ENV_FILE_ABSENT') from None
    need(stat.S_ISREG(named.st_mode),'ENV_FILE_NOT_REGULAR')
    return read_regular(host,ENV_FILE_NAME,directory.fd,gate,MAX_ENV_FILE_BYTES)

def project_directory(host,plan,deploy,gate,pinned):
    name=plan['compose']['project'];gate()
    try:named=host.lstat(name,deploy.fd)
    except FileNotFoundError:raise Refused('COMPOSE_FILE_ABSENT') from None
    need(stat.S_ISDIR(named.st_mode),'COMPOSE_DIRECTORY_NOT_A_DIRECTORY')
    gate();fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=deploy.fd)
    return hold(host,fd,pinned,parent=deploy,name=name)      # proved again by name under the lock (DEPLOY_TREE_REPLACED)

def compose_file_state(host,directory,gate):
    gate()
    try:named=host.lstat(COMPOSE_FILE_NAME,directory.fd)
    except FileNotFoundError:raise Refused('COMPOSE_FILE_ABSENT') from None
    need(stat.S_ISREG(named.st_mode),'COMPOSE_FILE_NOT_REGULAR')
    raw,info=read_regular(host,COMPOSE_FILE_NAME,directory.fd,gate,MAX_COMPOSE_FILE_BYTES)
    return stat_signature(info),sha(raw)

def override_state(host,plan,directory,gate):
    """The override the activation delivered: root:root 0600, one link, exactly the bytes of the four signed values."""
    name=plan['override']['name'];gate()
    try:named=host.lstat(name,directory.fd)
    except FileNotFoundError:raise Refused('OVERRIDE_ABSENT') from None
    need(stat.S_ISREG(named.st_mode),'OVERRIDE_NOT_AS_DELIVERED')            # never opened when it is not a regular file (a fifo would block)
    raw,info=read_regular(host,name,directory.fd,gate,MAX_OVERRIDE_BYTES)     # what was read is what is judged: its own fstat
    need(info.st_nlink==1 and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(0,0,0o600) and raw==override_bytes(plan),'OVERRIDE_NOT_AS_DELIVERED')
    return stat_signature(info)

def capacity_tree(host,plan,root,gate,pinned):
    """The tree the mount names: four root:root 0700 directories under the held root, on its device, never through a
    link; in config, the static config a regular root:root 0600 file of one link with the signed hash."""
    for name in CAPACITY_SUBDIRECTORIES:
        gate()
        try:named=host.lstat(name,root.fd)
        except FileNotFoundError:raise Refused('CAPACITY_TREE_INCOMPLETE') from None
        need(stat.S_ISDIR(named.st_mode) and (named.st_uid,named.st_gid,stat.S_IMODE(named.st_mode))==(0,0,0o700) and named.st_dev==root.identity[0],
             'CAPACITY_TREE_NOT_PRIVATE')
    gate();fd=host.open('config',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=root.fd)
    config=hold(host,fd,pinned,parent=root,name='config')
    name=plan['capacity']['config_name'];gate()
    try:named=host.lstat(name,config.fd)
    except FileNotFoundError:raise Refused('CAPACITY_CONFIG_ABSENT') from None
    need(stat.S_ISREG(named.st_mode),'CAPACITY_CONFIG_NOT_PRIVATE')
    raw,info=read_regular(host,name,config.fd,gate,MAX_CONFIG_BYTES)
    need(info.st_nlink==1 and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(0,0,0o600),'CAPACITY_CONFIG_NOT_PRIVATE')
    need(sha(raw)==plan['capacity']['config_sha256'],'CAPACITY_CONFIG_HASH_MISMATCH')
    return config

def reached_by_name(holder,gate):
    try:holder.verify(gate);return True
    except Refused as error:
        if str(error)!='PARENT_REPLACED':raise
        return False

def leftovers(rows,container):return [row for row in rows if row['name'].endswith('_'+container)]
def alive(row):return row['running'] is True and row['state']=='running'
def plain(path):return str(PurePosixPath(path)) if type(path) is str else path

def stopwatch(monotonic):
    try:start=monotonic()
    except Exception:start=None
    def read():
        try:return int(round((monotonic()-start)*1000))
        except Exception:return None
    return read

def mounts_of(commands,container_id):
    """docker inspect of the mounts of one container (by ID): Type, Name, Source, Destination, RW of each. A mount
    names host paths and volume names, never a value of the environment."""
    try:rows=strict(commands.output('container_mounts',container_id))
    except Refused as error:
        if isinstance(error,CommandFailed) or str(error) in ('COMMAND_TIMEOUT','COMMAND_OUTPUT_LIMIT','GO_EXPIRED'):raise
        raise Refused('MOUNTS_METADATA_INVALID') from None
    need(type(rows) is list and len(rows)<=MAX_MOUNTS_LISTED and all(type(row) is dict and type(row.get('Destination')) is str
         and type(row.get('Type')) is str and type(row.get('RW')) is bool for row in rows),'MOUNTS_METADATA_INVALID')
    return rows

def mounts_as(plan,rows,count):
    """The mount at /c3po-capacity is the one of a block of `count` lines (the read-only bind of the signed tree from
    the first line on, the placeholder volume without it), and the data root is still bound read-write."""
    capacity=[row for row in rows if plain(row['Destination'])==CAPACITY_TARGET];data=[row for row in rows if plain(row['Destination'])==DATA_TARGET]
    if len(capacity)!=1 or len(data)!=1:return False
    mount=capacity[0]
    if count:right=mount['Type']=='bind' and plain(mount.get('Source'))==capacity_root_path(plan) and mount['RW'] is False
    else:right=mount['Type']=='volume' and mount.get('Name')==placeholder_name(plan) and mount['RW'] is False
    return right and data[0]['Type']=='bind' and plain(data[0].get('Source'))==plan['data_root'] and data[0]['RW'] is True

def environment_as(values,plan,count):
    present=present_names(plan,count)
    return all(item=={'present':True,'equal':True} if name in present else item['present'] is False for name,item in values.items())

def render_errors(rendered,plan,count):
    """check_compose_render.py of the release (check(), placeholder or bind=<tree>), ported: r2d2-worker and no other
    service mounts /c3po-capacity, once, read-only; its three targets unchanged; the project name; the placeholder
    declared with its project name when it is used."""
    errors=[];services=rendered.get('services');found=[]
    for name,service in services.items():
        if type(service) is not dict:errors.append('SERVICE');continue
        for volume in service.get('volumes') or []:
            if type(volume) is not dict:errors.append('LONG_FORM')
            elif volume.get('target')==CAPACITY_TARGET:found.append((name,volume))
    if [name for name,_ in found]!=[WORKER_SERVICE]:return errors+['ONCE_ON_THE_WORKER_ONLY']
    mount=found[0][1]
    if mount.get('read_only') is not True:errors.append('READ_ONLY')
    targets=[volume.get('target') for volume in services[WORKER_SERVICE]['volumes'] if type(volume) is dict]
    if sorted(map(str,targets))!=sorted(WORKER_TARGETS):errors.append('WORKER_TARGETS')
    if rendered.get('name')!=plan['compose']['project']:errors.append('PROJECT')
    declared=rendered.get('volumes')
    if declared is None:declared={}
    if type(declared) is not dict:errors.append('VOLUMES');declared={}
    placeholder=declared.get(PLACEHOLDER_VOLUME)
    named=type(placeholder) is dict and placeholder.get('name')==placeholder_name(plan)
    if count:
        if (mount.get('type'),mount.get('source'))!=('bind',capacity_root_path(plan)):errors.append('BIND')
        if PLACEHOLDER_VOLUME in declared and not named:errors.append('PLACEHOLDER_NAME')
    else:
        if (mount.get('type'),mount.get('source'))!=('volume',PLACEHOLDER_VOLUME):errors.append('PLACEHOLDER')
        if not named:errors.append('PLACEHOLDER_NAME')
    return errors

def service_of(rendered,plan,count,findings=None):
    """What a render must say of the worker: the build revision, the four values of the activation, the capacity names
    of a block of `count` lines with the signed values and none of the others, the data root bound at its target, and
    the capacity mount of that block. Never prints a value."""
    service=compose_service(rendered,WORKER_SERVICE);environment=service['environment'];values=expected_environment(plan,count)
    for ok,code in ((environment.get(BUILD_KEY)==EPOCH_REVISION,'RENDER_BUILD_REVISION'),
                    (all(environment.get(key)==values[key] for key in ACTIVATION_KEYS),'RENDER_ACTIVATION_ENVIRONMENT_MISMATCH')):
        if findings is None:need(ok,code)
        elif not ok:findings.append(code)
    need(all(environment.get(key)==values[key] for key in CAPACITY_KEYS[:count]) and not [key for key in CAPACITY_KEYS[count:] if key in environment],
         'RENDER_CAPACITY_ENVIRONMENT_MISMATCH')
    need(text(service['image'],REFERENCE) and not service['image'].startswith('-'),'RENDER_IMAGE_INVALID')
    volumes=rendered['services'][WORKER_SERVICE].get('volumes')
    need(type(volumes) is list and len(volumes)<=64 and all(type(item) is dict and type(item.get('target')) is str and item['target'] for item in volumes),
         'RENDER_VOLUMES_INVALID')
    data=[item for item in volumes if plain(item['target'])==DATA_TARGET]
    need(len(data)==1 and data[0].get('type')=='bind' and plain(data[0].get('source'))==plan['data_root'] and data[0].get('read_only') in (None,False),
         'WORKER_DATA_MOUNT_NOT_AS_SIGNED')
    need(not render_errors(rendered,plan,count),'RENDER_CAPACITY_MOUNT_NOT_AS_SIGNED')
    return service

def editor_line(result):
    """The status and the constant code of the one line the editor printed; (None, None) when it printed something else."""
    try:
        line=single_line(result['output'])
        if set(line)=={'status','code'} and line['status'] in ENV_EDIT_STATUSES and (line['code'] is None or text(line['code'],CODE)):
            return line['status'],line['code']
    except Exception:pass
    return None,None

def settle_edit(host,state,result,deploy,gate,before,expected,identity):
    """Settle one call of the editor from what the environment file holds afterwards, read on the host: the expected
    bytes on the same object is done; the bytes before on the same object (and a command that returned) is a failure
    that changed nothing; anything else, or a file that cannot be read, is unknown. Returns the row for the receipt."""
    status,code=editor_line(result)
    row={'started':result['started'],'returned':result['returned'],'returncode':result['returncode'],'status':status,'code':code or result['code'],'state':None}
    if not result['started']:row['state']='NOT_STARTED';return row
    try:
        if not reached_by_name(deploy,gate):raise Refused('DEPLOY_TREE_REPLACED')
        raw,info=env_file_read(host,deploy,gate);same=identity_of(info)==identity
        if same and raw==expected:found='EDITED'
        elif same and raw==before:found='UNCHANGED'
        else:found='OTHER'
    except Exception:found='UNREADABLE'
    if not result['returned']:row['state']=found;return row                     # effect() settled it as unknown already
    if found=='EDITED' and result['returncode']==0 and status=='ENV_EDIT_DONE':state.done()
    elif found=='UNCHANGED' and status=='ENV_EDIT_REFUSED':state.fail()
    else:state.unknown()
    row['state']=found;return row

NOT_STARTED={'started':False,'returned':False,'returncode':None,'status':None,'code':None,'state':'NOT_STARTED'}
def env_file_after(edit,withdraw):
    """What the environment file holds at the end, as far as this run read it: UNCHANGED, EDITED (the signed edit),
    RESTORED (edited, then the edit withdrawn), or UNKNOWN (a call whose result could not be read back)."""
    if withdraw['started'] and not withdraw['returned']:return 'UNKNOWN'          # the editor may still be running
    if withdraw['state']=='EDITED':return 'RESTORED'
    if withdraw['state'] in ('OTHER','UNREADABLE'):return 'UNKNOWN'
    if edit['started'] and not edit['returned']:return 'UNKNOWN'
    if edit['state']=='EDITED':return 'EDITED'
    if edit['state']=='NOT_STARTED' or (edit['state']=='UNCHANGED' and edit['status']=='ENV_EDIT_REFUSED'):return 'UNCHANGED'
    return 'UNKNOWN'
def edit_stop(row):
    """The code a call of the editor that did not end as signed stops the run with."""
    if row['state']=='NOT_STARTED':return row['code'] or 'COMMAND_NOT_STARTED'
    if not row['returned']:return row['code'] or 'ENV_EDIT_DID_NOT_RETURN'
    if row['state']=='UNCHANGED':return row['code'] if row['status']=='ENV_EDIT_REFUSED' and row['code'] else 'ENV_EDIT_FILE_UNCHANGED'
    if row['state']=='EDITED':return 'ENV_EDIT_STATUS_NOT_DONE'
    if row['state']=='UNREADABLE':return 'ENV_FILE_UNREADABLE_AFTER_THE_EDIT'
    return 'ENV_FILE_NOT_AS_EDITED'

def still_listed(commands,name):
    """Whether a container of that name is still listed (an editor whose CLI was killed: CORE U10); None if unreadable."""
    try:return name in [row['name'] for row in container_list(commands)]
    except Exception:return None

AFTER_FACTS=('worker_listed_once','worker_is_new','old_container_gone','running','restarts','image_is_the_signed_one','environment_as_signed',
             'mounts_as_signed','others_unchanged','others_states_unchanged','others_appeared','others_gone','others_same_name_new_id','service_leftovers',
             'env_file_as_edited','compose_file_unchanged','override_unchanged','lock_still_named','settle_pause_taken','second_check_passed',
             'milliseconds_between_checks')
def read_after(c):
    """Everything read after the recreate command was started, each fact on its own (K6a's rule)."""
    host,gate,commands,plan,before,container,count=c['host'],c['gate'],c['commands'],c['plan'],c['before'],c['container'],c['count']
    facts={name:None for name in AFTER_FACTS};failed={};seen={}
    def step(label,action):
        try:action()
        except Exception as error:failed[label]=code_of(error,'OS_ERROR' if isinstance(error,OSError) else 'READBACK_FAILED')
    def worker():
        row=container_facts(commands,container);seen['first']=row;seen['at']=c['monotonic']()
        facts.update(worker_is_new=row['id']!=before['id'],running=alive(row),restarts=row['restarts'],
                     image_is_the_signed_one=row['image_id']==plan['worker']['image_id'])
    def environment():
        if 'first' in seen:
            facts['environment_as_signed']=environment_as(container_environment(commands,seen['first']['id'],c['signed']),plan,count)
    def mounts():
        if 'first' in seen:facts['mounts_as_signed']=mounts_as(plan,mounts_of(commands,seen['first']['id']),count)
    def containers():
        rows=container_list(commands);named=[row['id'] for row in rows if row['name']==container]
        def others(source,states):return sorted((row['id'],row['name'])+((row['state'],) if states else ()) for row in source if row['name']!=container)
        facts.update(worker_listed_once=len(named)==1 and ('first' not in seen or named==[seen['first']['id']]),
                     old_container_gone=before['id'] not in [row['id'] for row in rows],
                     others_unchanged=others(rows,False)==others(c['listing'],False),others_states_unchanged=others(rows,True)==others(c['listing'],True))
        if 'first' not in seen and len(named)==1:facts['worker_is_new']=named[0]!=before['id']
        seen['listing_unchanged']=sorted((row['id'],row['name']) for row in rows)==sorted((row['id'],row['name']) for row in c['listing'])
        was={row['name']:row['id'] for row in c['listing'] if row['name']!=container};now={row['name']:row['id'] for row in rows if row['name']!=container}
        facts.update(others_appeared=len([name for name in now if name not in was]),others_gone=len([name for name in was if name not in now]),
                     others_same_name_new_id=len([name for name in now if name in was and now[name]!=was[name]]),service_leftovers=len(leftovers(rows,container)))
    def environment_file():
        if reached_by_name(c['deploy'],gate):
            raw,info=env_file_read(host,c['deploy'],gate);facts['env_file_as_edited']=raw==c['expected'] and identity_of(info)==c['identity']
        else:facts['env_file_as_edited']=False
    def compose_file():facts['compose_file_unchanged']=reached_by_name(c['project'],gate) and compose_file_state(host,c['project'],gate)==c['compose_before']
    def override():
        def now():
            try:return override_state(host,plan,c['override_directory'],gate)
            except Refused as error:
                if c['override_before'] is not None or str(error) in ('GO_EXPIRED','CLOCK_REVERSED'):raise
                return None                                   # a disable that went on with an override not as delivered: compared as it was
        facts['override_unchanged']=reached_by_name(c['override_directory'],gate) and now()==c['override_before']
    def locked():facts['lock_still_named']=reached_by_name(c['lock_directory'],gate) and lock_still_named(host,LOCK_FILE_NAME,c['lock_directory'],c['lock'])
    def settle():
        facts['settle_pause_taken']=False
        if 'first' in seen and gate()>=SETTLE_SECONDS+SECOND_CHECK_RESERVE_SECONDS:
            host.pause(SETTLE_SECONDS);facts['settle_pause_taken']=True
    def second():
        if 'first' in seen:
            first=seen['first'];row=container_facts(commands,first['id'],expected_name=container)
            facts['second_check_passed']=row['started_at']==first['started_at'] and alive(row) and row['restarts']==0
            facts['milliseconds_between_checks']=int((c['monotonic']()-seen['at'])*1000)
    for label,action in (('WORKER',worker),('ENVIRONMENT',environment),('MOUNTS',mounts),('CONTAINERS',containers),('ENV_FILE',environment_file),
                         ('COMPOSE_FILE',compose_file),('OVERRIDE',override),('LOCK',locked),('SETTLE',settle),('SECOND_CHECK',second)):step(label,action)
    first=seen.get('first')
    unchanged=bool(first is not None and seen.get('listing_unchanged') is True and alive(first)
                   and all(first[key]==before[key] for key in ('started_at','restarts')))
    return facts,failed,unchanged

def _reduce_precheck(receipt):receipt['precheck']={'reduced_for_size':True}
def _reduce_chains(receipt):receipt['chains']={key:len(rows) for key,rows in (receipt.get('chains') or {}).items()}
REDUCTIONS=[('PRECHECK_DROPPED',_reduce_precheck),('CHAINS_REDUCED_TO_COUNTS',_reduce_chains)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    mode=plan['mode'];spec=edit_spec(plan);stdin=editor_stdin(spec);after=MODES[mode]['after']                    # pure
    signed=expected_environment(plan,5);compose=plan['compose'];container=worker_name(plan);listed=file_list(plan)
    active=mode in ('MOUNT','ENABLE')                       # the worker must run before; the tree is read
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    detail={'chains':{},'precheck':{},'budget':{},'process':{'dumpable_disabled':None}};pinned=[];lock=[None]
    commands=Commands(host,gate)
    edit=dict(NOT_STARTED);withdraw=dict(NOT_STARTED);findings=[];detail['precheck']['findings']=findings
    def judge(ok,code):
        """MOUNT and ENABLE refuse; a disable reports and goes on: it must work on a worker that loops because the
        epoch's pins no longer hold (MNT, "While the flag is on")."""
        if active:need(ok,code)
        elif not ok:findings.append(code)
    def looked(action):
        try:return action()
        except Refused as error:
            if active or str(error) in ('GO_EXPIRED','CLOCK_REVERSED'):raise
            findings.append(code_of(error,'FINDING'));return None
    run={'state':'NOT_STARTED','code':None,'returncode':None,'started':False,'returned':False,'milliseconds':None,'replaced':False,'facts':None,'unavailable':None}
    def finish(status,outcome,code,extra):
        receipt=envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),clock=timing(begun,mark,clock,monotonic),
            commands_started=dict(commands.started),mutating_calls=state.counts(),mode=mode,chains=detail['chains'],precheck=detail['precheck'],
            budget=detail['budget'],process=detail['process'],env_edit=edit,env_withdraw=withdraw,recreate=run,worker_container_replaced=run['replaced'],
            env_file_after=env_file_after(edit,withdraw),pre_existing_objects_modified=not state.clean(),
            failure_phase=None if code is None else ('AFTER_THE_RECREATE_STARTED' if run['started'] else
                                                     'BEFORE_THE_RECREATE' if edit['started'] else 'BEFORE_THE_EDIT'),**extra))
        return seal(receipt)
    def chain(key,rows):
        seen=[];detail['chains'][key]=seen
        return hold(host,walk_pinned(host,rows,gate,seen),pinned,rows=rows)
    try:
        # ---- everything is looked at before the first effect
        try:
            # first, before anything is opened: this process made non-dumpable and proved so (PROCESS_SCOPE)
            detail['process']['dumpable_disabled']=False
            need(host.not_dumpable() is True,'PROCESS_DUMPABLE_NOT_DISABLED');detail['process']['dumpable_disabled']=True
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o077)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            deploy=chain('DEPLOY_DIRECTORY',plan['deploy_directory'])
            looked(lambda:deploy_version(host,deploy,gate))
            env_before,env_info=env_file_read(host,deploy,gate)
            identity=identity_of(env_info)
            need(identity[2:]==ENV_OWNER+(ENV_MODE,1),'ENV_FILE_NOT_EDITABLE_BY_THE_EDITOR')
            # decision 6 (every bind source and its ancestors root-controlled): reported as read, not judged (open item)
            detail['precheck']['bind_source_root_controlled']=bool(all(row.get('uid')==0 for row in detail['chains']['DEPLOY_DIRECTORY']) and identity[2]==0)
            expected,block=edited_env(env_before,spec)
            withdrawn_spec=edit_spec(plan,(after,),len(block))                         # the inverse edit, used only if the render after the edit is not as signed
            detail['precheck']['capacity_lines_found']=len(block)
            project=project_directory(host,plan,deploy,gate,pinned)
            compose_before=compose_file_state(host,project,gate)
            override_directory=chain('OVERRIDE_DIRECTORY',plan['override']['directory'])
            override_before=looked(lambda:override_state(host,plan,override_directory,gate))
            tree=None
            if active:
                tree=chain('CAPACITY_ROOT',plan['capacity']['root'])
                capacity_tree(host,plan,tree,gate,pinned)
            lock_directory=chain('LOCK_DIRECTORY',plan['lock']['directory'])
            lock[0]=open_lock(host,LOCK_FILE_NAME,lock_directory,gate)
            detail['precheck'].update(deploy_version_is_the_revision='DEPLOY_VERSION_MISMATCH' not in findings and 'DEPLOY_VERSION_ABSENT' not in findings,
                                      override_as_delivered=override_before is not None,capacity_tree_as_signed=True if active else None)
            # the worker as it is: by name; for MOUNT and ENABLE running and in the state of the block found
            before=container_facts(commands,container)
            detail['precheck']['worker']={'id':before['id'],'started_at':before['started_at'],'restarts':before['restarts'],'state':before['state']}
            judge(before['image_id']==plan['worker']['image_id'],'WORKER_IMAGE_NOT_THE_SIGNED_ONE')
            try:image=image_facts(commands,plan['worker']['image_id'])
            except CommandFailed:raise Refused('IMAGE_ABSENT_OR_UNREADABLE') from None
            judge(image['revision_label']==EPOCH_REVISION,'IMAGE_REVISION_MISMATCH')
            values=container_environment(commands,before['id'],signed);mounts=mounts_of(commands,before['id'])
            detail['precheck'].update(worker_running=alive(before),worker_environment_as_found=environment_as(values,plan,len(block)),
                                      worker_mounts_as_found=mounts_as(plan,mounts,len(block)))
            if active:
                need(alive(before),'WORKER_NOT_RUNNING')
                need(detail['precheck']['worker_environment_as_found'],'WORKER_ENVIRONMENT_NOT_AS_FOUND_IN_THE_FILE')
                need(detail['precheck']['worker_mounts_as_found'],'WORKER_MOUNTS_NOT_AS_FOUND_IN_THE_FILE')
            # the render from the files as they are, timed: the same render runs again between the edit and the recreate
            began=monotonic()
            service=service_of(compose_render(commands,'render_files',compose['project'],compose['env_file'],listed,EPOCH_REVISION),plan,len(block),
                               None if active else findings)
            measured=monotonic()-began
            try:resolved=image_facts(commands,service['image'])
            except CommandFailed:raise Refused('RENDER_IMAGE_UNRESOLVED') from None
            judge(resolved['id']==plan['worker']['image_id'],'RENDER_IMAGE_CHANGED')
            detail['precheck']['render']={'as_the_file_says':True,'image_is_the_signed_one':resolved['id']==plan['worker']['image_id']}
            allowance=min(COMMAND_CLASSES['RENDER']['seconds'],max(RENDER_ALLOWANCE_FLOOR_SECONDS,int(2*measured)+1))
            needed=effects_budget('edit_env','recreate')+allowance+FILES_ALLOWANCE_SECONDS+SETTLE_SECONDS
            detail['budget']={'first_render_milliseconds':int(measured*1000),'render_allowance_seconds':allowance,'needed_before_first_effect_seconds':needed,
                              'kept_while_waiting_for_the_lock_seconds':needed+UNDER_LOCK_ALLOWANCE_SECONDS,'left_when_the_lock_was_asked_for_milliseconds':int(gate()*1000)}
            need(needed+UNDER_LOCK_ALLOWANCE_SECONDS<MAX_SECONDS,'BUDGET_CANNOT_HOLD_BOTH_EFFECTS')
            detail['precheck']['lock_attempts']=acquire_lock(host,lock[0],gate,plan['lock']['wait_seconds'],needed+UNDER_LOCK_ALLOWANCE_SECONDS)
            need(lock_still_named(host,LOCK_FILE_NAME,lock_directory,lock[0]),'LOCK_FILE_REPLACED')
            pending=probe(host,REBOOT_PENDING_PATH,gate)
            need(pending.get('status')=='COMPLETE','REBOOT_STATE_UNAVAILABLE');need(pending.get('exists') is False,'SECURITY_REBOOT_PENDING')
            need(reached_by_name(override_directory,gate),'OVERRIDE_DIRECTORY_REPLACED')
            need(reached_by_name(lock_directory,gate),'LOCK_DIRECTORY_REPLACED')
            if tree is not None:
                need(reached_by_name(tree,gate),'CAPACITY_ROOT_REPLACED')
                capacity_tree(host,plan,tree,gate,pinned)                 # the static config again, under the lock
            looked(lambda:deploy_version(host,deploy,gate))
            again_raw,again_info=env_file_read(host,deploy,gate)
            need(again_raw==env_before and stat_signature(again_info)==stat_signature(env_info),'ENV_FILE_CHANGED_BEFORE_THE_LOCK')
            need(compose_file_state(host,project,gate)==compose_before,'COMPOSE_FILE_CHANGED_BEFORE_THE_LOCK')
            need(looked(lambda:override_state(host,plan,override_directory,gate))==override_before,'OVERRIDE_CHANGED_BEFORE_THE_LOCK')
            try:again_image=image_facts(commands,service['image'])
            except CommandFailed:raise Refused('RENDER_IMAGE_UNRESOLVED') from None
            need(again_image['id']==resolved['id'],'RENDER_IMAGE_CHANGED_BEFORE_THE_LOCK')        # a tag moved while the lock was waited for
            again=container_facts(commands,container)
            keys=('id','started_at','restarts') if active else ('id',)
            need(all(again[key]==before[key] for key in keys) and (alive(again) or not active),'WORKER_CHANGED_BEFORE_THE_LOCK')
            listing=container_list(commands)
            need([row['id'] for row in listing if row['name']==container]==[before['id']],'CONTAINER_LIST_INCONSISTENT')
            need(not leftovers(listing,container),'WORKER_SERVICE_LEFTOVER_CONTAINER')
            need(not [row for row in listing if row['name'] in (editor_name(bound),editor_name(bound)+'-withdraw')],'EDITOR_NAME_TAKEN')
            need(reached_by_name(project,gate),'DEPLOY_TREE_REPLACED')         # last, right before the editor binds .env by its path
            detail['precheck'].update(reboot_pending=False,containers_listed=len(listing))
            left=gate();detail['budget']['left_before_first_effect_milliseconds']=int(left*1000)
            need(left>=needed,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})
        # ---- from here on nothing refuses unless nothing has changed
        stop=None
        mount=editor_mounts(plan)
        result=container_effect(state,commands,'edit_env',plan['worker']['image_id'],mount,ENV_EDITOR_COMMAND,stdin,container_name=editor_name(bound))
        edit=settle_edit(host,state,result,deploy,gate,env_before,expected,identity)
        if result['started'] and not result['returned']:edit['container_left']=still_listed(commands,editor_name(bound))
        if edit['state']!='EDITED' or not result['returned'] or result['returncode']!=0 or edit['status']!='ENV_EDIT_DONE':
            stop=edit_stop(edit)
        if stop is None:
            taken=stopwatch(monotonic)
            try:
                need(lock_still_named(host,LOCK_FILE_NAME,lock_directory,lock[0]),'LOCK_FILE_REPLACED')
                need(service_of(compose_render(commands,'render_files',compose['project'],compose['env_file'],listed,EPOCH_REVISION),plan,after,
                                None if active else [])['image']==service['image'],'RENDER_IMAGE_CHANGED')
            except Exception as error:stop=code_of(error,'RENDER_AFTER_EDIT_OS_ERROR' if isinstance(error,OSError) else 'RENDER_AFTER_EDIT_FAILED')
            detail['budget']['render_after_the_edit_milliseconds']=taken()
            # the allowance the budget kept for this render (core rule 4.2): a slower render is a failure, not a late recreate
            if stop is None and (detail['budget']['render_after_the_edit_milliseconds'] is None or detail['budget']['render_after_the_edit_milliseconds']>allowance*1000):
                stop='RENDER_AFTER_EDIT_OVER_ITS_ALLOWANCE'
        if stop is None:
            try:
                need(reached_by_name(project,gate),'DEPLOY_TREE_REPLACED')
                need(reached_by_name(override_directory,gate),'OVERRIDE_DIRECTORY_REPLACED')
                need(reached_by_name(lock_directory,gate),'LOCK_DIRECTORY_REPLACED')
            except Exception as error:stop=code_of(error,'RECREATE_PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'RECREATE_PRECHECK_FAILED')
        if stop is None:
            taken=stopwatch(monotonic)
            result=compose_up(state,commands,'recreate',compose['project'],compose['env_file'],listed,EPOCH_REVISION)
            run.update(started=result['started'],returned=result['returned'],returncode=result['returncode'],code=result['code'],milliseconds=taken())
            if not result['started']:stop=result['code'] or 'COMMAND_NOT_STARTED'
            else:
                facts,failed,unchanged=read_after({'host':host,'gate':gate,'commands':commands,'plan':plan,'before':before,'container':container,'count':after,
                    'listing':listing,'signed':signed,'deploy':deploy,'expected':expected,'identity':identity,'project':project,'compose_before':compose_before,
                    'override_directory':override_directory,'override_before':override_before,'lock_directory':lock_directory,'lock':lock[0],'monotonic':monotonic})
                run.update(facts=facts,unavailable=failed)
                criteria=[(result['code'] or 'RECREATE_RETURNED_NONZERO',bool(result['returned'] and result['returncode']==0)),
                          ('WORKER_NOT_FOUND_AFTER_RECREATE',facts['worker_listed_once']),('WORKER_NOT_RECREATED',facts['worker_is_new']),
                          ('OLD_CONTAINER_STILL_PRESENT',facts['old_container_gone']),('WORKER_NOT_RUNNING_AFTER_RECREATE',facts['running']),
                          ('WORKER_RESTARTED_AFTER_RECREATE',None if facts['restarts'] is None else facts['restarts']==0),
                          ('WORKER_IMAGE_CHANGED',facts['image_is_the_signed_one']),('ENVIRONMENT_NOT_AS_SIGNED',facts['environment_as_signed']),
                          ('MOUNTS_NOT_AS_SIGNED',facts['mounts_as_signed']),('OTHER_CONTAINERS_CHANGED',facts['others_unchanged']),
                          ('ENV_FILE_NOT_AS_EDITED',facts['env_file_as_edited']),('COMPOSE_FILE_CHANGED',facts['compose_file_unchanged']),
                          ('OVERRIDE_CHANGED',facts['override_unchanged']),('LOCK_FILE_REPLACED',facts['lock_still_named']),
                          ('SECOND_CHECK_NOT_APART',facts['settle_pause_taken']),('WORKER_CHANGED_BETWEEN_THE_TWO_CHECKS',facts['second_check_passed'])]
                missing=[name if value is False else 'READBACK_UNAVAILABLE' for name,value in criteria if value is not True]
                if not missing:
                    state.done();run.update(state='RECREATED_VERIFIED',replaced=True)
                elif result['returned'] and unchanged:
                    state.fail();run.update(state='NOT_RECREATED',replaced=False)
                    stop='RECREATE_FAILED_CONTAINER_UNCHANGED' if result['returncode'] else 'RECREATE_RETURNED_ZERO_CONTAINER_UNCHANGED'
                else:
                    if result['returned']:state.unknown()
                    if facts['worker_is_new'] is True:
                        once=not [name for name,value in criteria[:-2] if value is not True] and facts['second_check_passed'] is not False
                        run.update(state='RECREATED_VERIFIED_ONCE' if once else 'RECREATED_NOT_VERIFIED',replaced=True)
                    else:run.update(state='UNCERTAIN',replaced=None)
                    stop=missing[0]
        if (stop is not None and plan['withdrawal_authorized'] and edit['state']=='EDITED' and edit['returncode']==0 and edit['status']=='ENV_EDIT_DONE'      # exit 0: it returned
                and not run['started']):
            # MNT, step 1: "If config or the check fails, nothing was recreated. Delete the line appended above." The signed
            # effect E1' (effects.withdrawal): only when authorized, only BEFORE the recreate was started (no rollback is
            # inferred from a recreate that ran), only after an edit the editor confirmed and the host read back, and only
            # while the lock is still the one held. The inverse edit, by the same editor; never a second recreate.
            try:held=lock_still_named(host,LOCK_FILE_NAME,lock_directory,lock[0])
            except Exception:held=False
            if held:
                back=container_effect(state,commands,'edit_env',plan['worker']['image_id'],mount,ENV_EDITOR_COMMAND,editor_stdin(withdrawn_spec),
                                      container_name=editor_name(bound)+'-withdraw')
                withdraw=settle_edit(host,state,back,deploy,gate,expected,env_before,identity)
                if back['started'] and not back['returned']:withdraw['container_left']=still_listed(commands,editor_name(bound)+'-withdraw')
        extra={'phase_reached':'EFFECTS','readback':'COMPLETE' if stop is None else None}
        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        if run['state'] in ('RECREATED_VERIFIED_ONCE','RECREATED_NOT_VERIFIED'):outcome=NOT_VERIFIED_OUTCOME
        elif run['state']=='UNCERTAIN' or env_file_after(edit,withdraw)=='UNKNOWN':outcome=UNCERTAIN_OUTCOME
        elif run['state']=='NOT_RECREATED':outcome=RECREATE_FAILED_OUTCOME
        elif withdraw['state']=='EDITED':outcome=WITHDRAWN_OUTCOME
        else:outcome=ENV_ONLY_OUTCOME
        return finish(PARTIAL_STATUS,outcome,stop,extra)
    finally:
        if lock[0] is not None:release_lock(host,lock[0])
        for handle in pinned:
            try:handle.close()
            except Exception:pass
