import base64

OPERATION='GO_WRITE_HOSTOPS02_ACTIVATE_01'
PHASE='WRITE_ACTIVATE_WORKER_RELEASE_AND_LIVE_POLICY'
REQUEST_SCHEMA='WRITE_HOSTOPS02_ACTIVATE_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_ACTIVATE_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_ACTIVATE_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_ACTIVATE_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_ACTIVATE_PLAN_V1'
SOURCE_NAME='activate.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False                  # no systemd unit is switched: the recreate of a compose service is not an activation in the family's sense
DATE_CLASS='WRITE_FIRST_SESSION'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
EVIDENCE_OPERATIONS=('GO_READONLY_HOSTOPS02_EPOCH_READBACK_01',)        # the epoch readback (K11): its dry run of the same boot gives the rows this request signs
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='ACTIVATE_WORKER_RECREATED_AND_VERIFIED'
PARTIAL_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
# The three partial outcomes of a run that returned its receipt (PARTIAL_OUTCOME itself is what an escaped run says).
OBJECTS_ONLY_OUTCOME='PARTIAL_OBJECTS_LEFT_WORKER_NOT_RECREATED'
NOT_VERIFIED_OUTCOME='PARTIAL_WORKER_RECREATED_NOT_FULLY_VERIFIED'
UNCERTAIN_OUTCOME='PARTIAL_RECREATE_UNCERTAIN_REQUIRES_READBACK'

# ---------------------------------------------------------------- the epoch, as the release code compiles it
EPOCH_NAME='R2D2-V2-SHADOW-2026-10-05'                                                        # r2d2_v2_epoch_assembler.py:9
EPOCH_REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'                                     # main at the release; .deploy-version and C3PO_BUILD_SHA
EPOCH_PACKAGE_SHA256='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'       # implementation package of that revision
RUNTIME_ORDER_SHA256='1ad8b90cfab651823eb677b830a0078d10c17447575c8d813c3883a718579d8e'       # r2d2_v2_live_controller.py:30
EPOCH_FIRST_OPEN='2026-10-05T13:30:00+00:00'                                                  # open of the first session
EPOCH_LAST_CLOSE='2026-10-09T20:00:00+00:00'                                                  # close of the fifth
LIVE_POLICY_SCHEMA='R2D2_V2_LIVE_POLICY_V1'
MAX_POLICY_WINDOW_SECONDS=90*86400
MAX_POLICY_BYTES=16384
MAX_RELEASE_BYTES=65536                                                                       # what the worker accepts (r2d2_v2_shadow_worker.py:33)
MAX_ENV_FILE_BYTES=1048576
MAX_COMPOSE_FILE_BYTES=1048576
FREE_BYTES_FLOOR=1048576                  # bytes a non-root writer must still have on the filesystem of the live parent before the first creation (as install_release)
FREE_INODES_FLOOR=8                       # inodes, where the filesystem counts them: this run takes three
WORKER_SERVICE='r2d2-worker'
BUILD_KEY='C3PO_BUILD_SHA'
KEY_POLICY_FILE='C3PO_R2D2_V2_LIVE_POLICY_FILE'                                               # config.py:197 (env_prefix C3PO_, config.py:20)
KEY_POLICY_SHA='C3PO_R2D2_V2_LIVE_POLICY_SHA'                                                 # config.py:198
KEY_RELEASE_FILE='C3PO_R2D2_V2_SHADOW_RELEASE_FILE'                                           # config.py:207
KEY_RELEASE_SHA='C3PO_R2D2_V2_SHADOW_RELEASE_SHA'                                             # config.py:208
ACTIVATION_KEYS=(KEY_POLICY_FILE,KEY_POLICY_SHA,KEY_RELEASE_FILE,KEY_RELEASE_SHA)
# The layout of the deploy tree, as the pipeline's deploy job uses it (c3po-pipeline.yml:631-658, 743-746).
ENV_FILE_NAME='.env'
COMPOSE_FILE_NAME='compose.yml'
DEPLOY_VERSION_NAME='.deploy-version'
LOCK_RELATIVE_DIRECTORY='runtime/security'
LOCK_FILE_NAME='deployment.lock'
REBOOT_PENDING_PATH='/run/c3po-security/reboot.pending'
PIN_NAME='.r2d2-v2-pinned'                                                                    # scripts/c3po_security_guard.py: its existence is the whole test
STATUS_SUFFIX='.status.json'                                                                  # r2d2_v2_live_controller.py:274
# ---------------------------------------------------------------- the budget (seconds of the 60 a run has)
SETTLE_SECONDS=3                          # the one fixed pause, between the two readings of the new worker
SECOND_CHECK_RESERVE_SECONDS=2            # what must be left after the pause for the second reading
FILES_ALLOWANCE_SECONDS=1                 # the directory, the two files and their readback
UNDER_LOCK_ALLOWANCE_SECONDS=2            # the reads made again once the lock is held, before the first creation
RENDER_ALLOWANCE_FLOOR_SECONDS=3          # the render from the files is given twice what the first render took, at least this much

PLAN_KEYS=frozenset(('data_root','live_parent','directory_name','policy','override_name','release','worker','compose','deploy_directory','lock',
                     'evidence_boot_id_sha256'))
POLICY_KEYS=frozenset(('name','content_b64','sha256','bytes'))
RELEASE_KEYS=frozenset(('parent','directory_name','file_name','sha256','bytes'))
WORKER_KEYS=frozenset(('image_id','mount_target'))
COMPOSE_KEYS=frozenset(('project','env_file','files'))
LOCK_KEYS=frozenset(('directory','wait_seconds'))
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'one image ID or reference','QUICK','READ'),
          'container':command_row('docker',['container','inspect','--format',CONTAINER_FORMAT],'one container name or ID','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          'container_environment':command_row('docker',['container','inspect','--format'],'the presence and equality template, then one container ID','QUICK','READ'),
          'render':command_row('docker',['compose'],'--project-name, --env-file, the compose file of the deploy, then the override on standard input as the last file','RENDER','READ',tail=COMPOSE_CONFIG_TAIL,stdin=True),
          'render_files':command_row('docker',['compose'],'--project-name, --env-file, the compose file of the deploy and the delivered override file','RENDER','READ',tail=COMPOSE_CONFIG_TAIL),
          'recreate':command_row('docker',['compose'],'--project-name, --env-file, the compose file of the deploy and the delivered override file','RECREATE','EFFECT',tail=compose_up_tail(WORKER_SERVICE))}
SUCCESS_CRITERIA=['the recreate command returned 0',
                  'exactly one container carries the name of the service and it is not the container that was there before',
                  'the container that was there before no longer exists under any name',
                  'the new container is running with restart count 0 on the signed image, read twice with a fixed pause between; the second reading shows the same container and the same start instant',
                  'its environment carries the four signed names and the build revision with the signed values, compared inside a docker template that prints booleans',
                  'every other container is listed with the ID and the name it had under the lock before the recreate, and no other container appeared',
                  'the environment file and the compose file of the project are the same objects with the same bytes as at the first look (signature and a hash kept in memory)',
                  'the installed release is still reached by its name and is the same object with the signed bytes',
                  'the two delivered files and their directory are as delivered, and the lock file is still the one held in the directory still named']
SCOPE_STATEMENT=('Single shot, first session day of epoch R2D2-V2-SHADOW-2026-10-05 only. Under the deployment lock: creates one private directory in '
                 'the signed parent of the data volume, delivers into it the signed live policy and one compose override that sets four environment '
                 'names of the service r2d2-worker (live policy file and hash, release file and hash), and recreates that one service with the '
                 'compose file of the deploy plus that override: one docker compose up -d --no-deps --no-build --pull never --force-recreate. '
                 'The running worker container is stopped and replaced; no other container, no image, no unit and no existing file is changed. '
                 'Nothing that exists is overwritten, renamed, chmodded, chowned or removed, except the temporary of this run once its identity '
                 'is proved. No docker exec, no shell, no systemctl, no pull. No value read from a container, from the render or from the environment '
                 'file is printed, stored or put in an argv. The four signed values are written to the override and shown in the effects; with '
                 'the build revision they are compared inside a docker template, in whose argv they travel.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'after_effect_reserve_seconds':AFTER_EFFECT_RESERVE_SECONDS,
       'budget':{'settle_seconds':SETTLE_SECONDS,'second_check_reserve_seconds':SECOND_CHECK_RESERVE_SECONDS,'files_allowance_seconds':FILES_ALLOWANCE_SECONDS,
                 'under_lock_allowance_seconds':UNDER_LOCK_ALLOWANCE_SECONDS,'render_allowance_floor_seconds':RENDER_ALLOWANCE_FLOOR_SECONDS,
                 'rule':'before the lock is asked for and again before the first creation: recreate class + reserve + render allowance + files + settle must be left'},
       'files':FILES_SCOPE,'lock':LOCK_SCOPE,'service':WORKER_SERVICE,'environment_names':list(ACTIVATION_KEYS),'build_name':BUILD_KEY,
       'epoch':{'name':EPOCH_NAME,'revision':EPOCH_REVISION,'package_sha256':EPOCH_PACKAGE_SHA256,'runtime_order_sha256':RUNTIME_ORDER_SHA256,
                'first_open':EPOCH_FIRST_OPEN,'last_close':EPOCH_LAST_CLOSE,'policy_schema':LIVE_POLICY_SCHEMA},
       'deploy_layout':{'environment_file':ENV_FILE_NAME,'compose_file':'<project>/'+COMPOSE_FILE_NAME,'deploy_version':DEPLOY_VERSION_NAME,
                        'lock':LOCK_RELATIVE_DIRECTORY+'/'+LOCK_FILE_NAME},
       'required_before_any_effect':{'reboot_pending_marker_absent':REBOOT_PENDING_PATH,'maintenance_pin_present':'<data root>/'+PIN_NAME,
                                     'release':'installed by an earlier operation: a root:root 0700 directory holding a root:root 0600 regular file with one link whose bytes have the signed hash',
                                     'no_leftover_of_a_recreate':'no container named <anything>_<the worker container>: the temporary name compose gives while it replaces the container of a service',
                                     'free_space':'on the filesystem of the live parent, for a non-root writer: the bytes of limits.free_bytes_floor and, where inodes are counted, limits.free_inodes_floor',
                                     'unchanged_since_the_first_look':'under the lock: the deployed revision, the environment file, the compose file, the release, the worker; the release directory, the deploy tree, the project directory and the lock directory still reached by their names'},
       'success_criteria':SUCCESS_CRITERIA,
       'partial_outcomes':[OBJECTS_ONLY_OUTCOME,NOT_VERIFIED_OUTCOME,UNCERTAIN_OUTCOME,PARTIAL_OUTCOME],
       'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'file_contents_read':[BOOT_ID_PATH,'the installed release (compared by hash)',DEPLOY_VERSION_NAME+' of the deploy tree',
                             'the environment file of the compose project: read into memory twice or more and compared with itself; no value, digest or size of it leaves the run',
                             'the compose file of the deploy: the same, never judged as text (the render is)',
                             'the files this run delivered (readback inside the run)',
                             'the status file the worker writes next to the policy, if it exists: two constant codes of it, informational'],
       'side_effects':['the worker container is stopped and replaced by a new one (new ID); what it held in memory is lost',
                       'the new worker writes its own status and journal files into the directory this run created',
                       'the deployment lock is held from before the first creation until the last readback'],
       'never':['overwrite','chmod','chown','rename','removal of anything but the temporary this run created','docker exec','a shell','systemctl',
                'a pull','a build','a second recreate','a change of the environment file or of the compose file','a network connection opened by this process'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,'policy_bytes':MAX_POLICY_BYTES,
                 'release_bytes':MAX_RELEASE_BYTES,'environment_file_bytes':MAX_ENV_FILE_BYTES,'compose_file_bytes':MAX_COMPOSE_FILE_BYTES,
                 'free_bytes_floor':FREE_BYTES_FLOOR,'free_inodes_floor':FREE_INODES_FLOOR,'lock_wait_seconds':MAX_LOCK_WAIT_SECONDS}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner,NativeFiles,NativeLock):
    """Everything this source can do to the host: the read primitives, the signed commands, the seven creating calls, the lock."""


# ---------------------------------------------------------------- what the plan says (pure)
def live_path(plan):return plan['live_parent'][-1]['path'].rstrip('/')+'/'+plan['directory_name']
def policy_path(plan):return live_path(plan)+'/'+plan['policy']['name']
def override_path(plan):return live_path(plan)+'/'+plan['override_name']
def release_directory_path(plan):return plan['release']['parent'][-1]['path'].rstrip('/')+'/'+plan['release']['directory_name']
def release_path(plan):return release_directory_path(plan)+'/'+plan['release']['file_name']
def deploy_path(plan):return plan['deploy_directory'][-1]['path']
def lock_path(plan):return plan['lock']['directory'][-1]['path']+'/'+LOCK_FILE_NAME
def pin_path(plan):return plan['data_root']+'/'+PIN_NAME
def worker_name(plan):return '%s-%s-1'%(plan['compose']['project'],WORKER_SERVICE)      # the name compose gives the one container of a service
def container_path(plan,path):
    """The path the worker sees for a host path of the data root, through its one bind of the data root."""
    return plan['worker']['mount_target']+path[len(plan['data_root']):]
def environment_of(plan):
    """The four names and values of the override: nothing here is free, each follows from another signed member."""
    return {KEY_POLICY_FILE:container_path(plan,policy_path(plan)),KEY_POLICY_SHA:plan['policy']['sha256'],
            KEY_RELEASE_FILE:container_path(plan,release_path(plan)),KEY_RELEASE_SHA:plan['release']['sha256']}
def override_of(plan):
    """The bytes of the compose override: one JSON object with the token shape of the override of 2026-09-28."""
    return json.dumps({'services':{WORKER_SERVICE:{'environment':environment_of(plan)}}},sort_keys=True).encode('ascii')

def chain_path(rows):
    need(type(rows) is list and rows and type(rows[-1]) is dict and type(rows[-1].get('path')) is str,'CHAIN_ROW_INVALID');return rows[-1]['path']
def signed_chain(rows,open_root,receives_entry=False):return validate_chain(rows,chain_path(rows),open_root,receives_entry)

def policy_instant(value):
    try:return instant(value)
    except Refused:raise Refused('POLICY_WINDOW') from None

def policy_of(plan):
    """(bytes, object) of the signed live policy. The bytes must have the signed hash and size; the object must be
    what the controller of the release (read_policy) and its assembler (validate_policy) will require of it."""
    item=plan['policy']
    need(type(item) is dict and set(item)==set(POLICY_KEYS) and file_request(item['name'],item['sha256'],item['bytes'],PRIVATE_FILE_MODE)
         and item['bytes']<=MAX_POLICY_BYTES and type(item['content_b64']) is str,'POLICY_REQUEST_INVALID')
    try:raw=base64.b64decode(item['content_b64'].encode('ascii'),validate=True)
    except (ValueError,UnicodeEncodeError):raise Refused('POLICY_BYTES_NOT_THE_SIGNED_HASH') from None
    need(sha(raw)==item['sha256'] and len(raw)==item['bytes'],'POLICY_BYTES_NOT_THE_SIGNED_HASH')
    try:policy=strict(raw)
    except Refused:raise Refused('POLICY_JSON_INVALID') from None
    need(type(policy) is dict,'POLICY_JSON_INVALID')
    return raw,policy

def policy_digest(policy):
    """The digest of the policy as the assembler of the release computes it: keys sorted, compact separators, text that
    is not ASCII as itself in UTF-8 (r2d2_v2_epoch_assembler.py:24-28). It is the policy_sha of Act B. A text that
    cannot be encoded (a lone surrogate) is refused: effects_of() is computed during the authentication."""
    try:return sha(json.dumps(policy,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8'))
    except ValueError:raise Refused('POLICY_JSON_INVALID') from None

def validate_policy(policy,plan):
    need(policy.get('schema')==LIVE_POLICY_SCHEMA and policy.get('mode')=='LIVE','POLICY_SCHEMA')
    need(policy.get('epoch')==EPOCH_NAME and policy.get('release_sha')==plan['release']['sha256'],'POLICY_IDENTITY')
    need(policy.get('order_sha')==RUNTIME_ORDER_SHA256,'POLICY_RUNTIME_ORDER')
    need(policy.get('package_sha')==EPOCH_PACKAGE_SHA256,'POLICY_PACKAGE')
    need(policy.get('code_revision')==EPOCH_REVISION,'POLICY_REVISION')
    need(integer(policy.get('capacity'),1,550),'POLICY_CAPACITY')
    need(all(hexpin(policy.get(key)) for key in ('c8_receipt_sha','head_go_sha')),'POLICY_RECERTIFICATION')
    start,end=policy_instant(policy.get('valid_from')),policy_instant(policy.get('valid_until'))
    need(start<end and (end-start).total_seconds()<=MAX_POLICY_WINDOW_SECONDS,'POLICY_WINDOW')
    need(start<=instant(EPOCH_FIRST_OPEN) and end>=instant(EPOCH_LAST_CLOSE),'POLICY_NOT_EPOCH_WIDE')
    # The controller refuses a policy outside its window at every step: the window of this run must lie inside it. Its
    # end does (the run is on the first session day and the policy ends after the last close); its start is compared.
    need(start<=instant(plan['window']['not_before']),'POLICY_WINDOW_DOES_NOT_COVER_THE_GO')

def validate_plan(plan):
    root=plan['data_root']
    need(clean_path(root),'PATH_INVALID')                        # "/" itself is refused as an open root by validate_chain, with the same code
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    signed_chain(plan['live_parent'],root,receives_entry=True)
    need(inside(plan['live_parent'][-1]['path'],root),'LIVE_PARENT_OUTSIDE_DATA_ROOT')
    need(text(plan['directory_name'],FILE_NAME) and clean_path(live_path(plan)),'DIRECTORY_NAME_INVALID')
    release=plan['release']
    need(type(release) is dict and set(release)==set(RELEASE_KEYS) and text(release['directory_name'],FILE_NAME) and text(release['file_name'],FILE_NAME)
         and hexpin(release['sha256']) and integer(release['bytes'],1,MAX_RELEASE_BYTES),'RELEASE_REQUEST_INVALID')
    signed_chain(release['parent'],root)
    need(inside(release['parent'][-1]['path'],root),'RELEASE_OUTSIDE_DATA_ROOT')
    need(not inside(live_path(plan),release_directory_path(plan)) and not inside(release_directory_path(plan),live_path(plan)),'PATHS_OVERLAP')
    raw,policy=policy_of(plan);validate_policy(policy,plan)
    name=plan['override_name']
    # not the policy's name, and not one of the names the worker itself writes next to the policy (policy.json.status.json, ...)
    need(text(name,FILE_NAME) and name!=plan['policy']['name'] and not name.startswith(plan['policy']['name']+'.'),'OVERRIDE_NAME_INVALID')
    need(clean_path(policy_path(plan)) and clean_path(override_path(plan)),'FILE_PATH_INVALID')
    worker=plan['worker']
    need(type(worker) is dict and set(worker)==set(WORKER_KEYS) and text(worker['image_id'],IMAGE_ID)
         and clean_path(worker['mount_target']) and worker['mount_target']!='/','WORKER_REQUEST_INVALID')
    compose=plan['compose']
    need(type(compose) is dict and set(compose)==set(COMPOSE_KEYS),'COMPOSE_REQUEST_INVALID')
    compose_arguments(compose['project'],compose['env_file'],compose['files'])                       # the signed list alone, then with the override
    compose_arguments(compose['project'],compose['env_file'],compose['files']+[override_path(plan)])
    deploy=chain_path(plan['deploy_directory']);signed_chain(plan['deploy_directory'],deploy)     # the deploy tree: owned by the operational account
    # the file list of the deploy and nothing else: <deploy>/.env and <deploy>/<project>/compose.yml (c3po-pipeline.yml:745-746)
    need(compose['env_file']==deploy+'/'+ENV_FILE_NAME and compose['files']==[deploy+'/'+compose['project']+'/'+COMPOSE_FILE_NAME],'COMPOSE_NOT_THE_DEPLOY_LAYOUT')
    need(not inside(root,deploy) and not inside(deploy,root),'PATHS_OVERLAP')
    lock=plan['lock']
    need(type(lock) is dict and set(lock)==set(LOCK_KEYS) and integer(lock['wait_seconds'],0,MAX_LOCK_WAIT_SECONDS),'LOCK_REQUEST_INVALID')
    signed_chain(lock['directory'],deploy)
    need(lock['directory'][-1]['path']==deploy+'/'+LOCK_RELATIVE_DIRECTORY,'LOCK_NOT_THE_DEPLOYMENT_LOCK')
    environment_format(dict(environment_of(plan),**{BUILD_KEY:EPOCH_REVISION}))                      # every value fits the grammar of the template

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    raw,policy=policy_of(plan);override=override_of(plan);compose=plan['compose']
    return {'operation':OPERATION,'epoch':EPOCH_NAME,'revision':EPOCH_REVISION,'data_root':plan['data_root'],
            'live_parent':chain_effects(plan['live_parent']),
            'directory':{'path':live_path(plan),'mode_octal':'%04o'%PRIVATE_DIRECTORY_MODE,'expect':'ABSENT'},
            'files':[{'key':'POLICY','path':policy_path(plan),'sha256':plan['policy']['sha256'],'bytes':plan['policy']['bytes'],'mode_octal':'%04o'%PRIVATE_FILE_MODE},
                     {'key':'OVERRIDE','path':override_path(plan),'sha256':sha(override),'bytes':len(override),'mode_octal':'%04o'%PRIVATE_FILE_MODE}],
            'policy':{'content_digest_sha256':policy_digest(policy),'valid_from':policy.get('valid_from'),'valid_until':policy.get('valid_until'),
                      'capacity':policy.get('capacity'),'release_sha':policy.get('release_sha')},
            'release':{'parent':chain_effects(plan['release']['parent']),'path':release_path(plan),'sha256':plan['release']['sha256'],
                       'bytes':plan['release']['bytes'],'expect':'INSTALLED_BY_AN_EARLIER_OPERATION_READ_AND_COMPARED_NEVER_WRITTEN'},
            'recreate':{'project':compose['project'],'env_file':compose['env_file'],'files':compose['files']+[override_path(plan)],'service':WORKER_SERVICE,
                        'container':worker_name(plan),'image_id':plan['worker']['image_id'],'build_sha':EPOCH_REVISION,'environment':environment_of(plan),
                        'worker_mount':{'source':plan['data_root'],'target':plan['worker']['mount_target']},
                        'lock':lock_path(plan),'lock_wait_seconds':plan['lock']['wait_seconds'],'lock_chain_sha256':sha(canonical(plan['lock']['directory'])),
                        'deploy_directory':chain_effects(plan['deploy_directory'])},
            'required':{'maintenance_pin':pin_path(plan),'reboot_pending_marker_absent':REBOOT_PENDING_PATH,'deploy_version':EPOCH_REVISION},
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],'pre_existing_objects_modified':'THE_WORKER_CONTAINER_IS_REPLACED','activation':False}
def success_of(plan):return COMPLETE_OUTCOME


# ---------------------------------------------------------------- what is read on the host
def hold(host,fd,pinned,**how):
    """A Pinned for a descriptor just opened; the descriptor is closed if it cannot be pinned."""
    try:holder=Pinned(host,fd,**how)
    except BaseException:
        host.close(fd);raise
    pinned.append(holder);return holder

def installed_release(host,plan,parent,gate,pinned):
    """The directory an earlier operation installed the release into, by name under its pinned parent, never through
    a link: a directory of root:root, mode 0700, on the device of its parent. Returns it held."""
    name=plan['release']['directory_name']
    gate()
    try:named=host.lstat(name,parent.fd)
    except FileNotFoundError:raise Refused('RELEASE_NOT_INSTALLED') from None
    need(stat.S_ISDIR(named.st_mode),'RELEASE_DIRECTORY_NOT_AS_INSTALLED')
    gate();fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=parent.fd)
    directory=hold(host,fd,pinned,parent=parent,name=name)
    need(directory.identity==(named.st_dev,named.st_ino,0,0,PRIVATE_DIRECTORY_MODE) and named.st_dev==parent.identity[0],'RELEASE_DIRECTORY_NOT_AS_INSTALLED')
    return directory

def release_state(host,plan,directory,gate):
    """The installed release: a regular file of root:root, mode 0600, one link, whose bytes have the signed size and
    hash. Returns its signature, for the comparison under the lock."""
    release=plan['release'];gate()
    try:named=host.lstat(release['file_name'],directory.fd)
    except FileNotFoundError:raise Refused('RELEASE_NOT_INSTALLED') from None
    need(stat.S_ISREG(named.st_mode) and named.st_nlink==1 and (named.st_uid,named.st_gid,stat.S_IMODE(named.st_mode))==(0,0,PRIVATE_FILE_MODE),
         'RELEASE_FILE_NOT_AS_INSTALLED')
    raw,info=read_regular(host,release['file_name'],directory.fd,gate,MAX_RELEASE_BYTES)
    need((info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'RELEASE_FILE_NOT_AS_INSTALLED')
    need(len(raw)==release['bytes'] and sha(raw)==release['sha256'],'RELEASE_HASH_MISMATCH')
    return stat_signature(info)

def deploy_version(host,directory,gate):
    """.deploy-version of the deploy tree says the revision of the epoch (the pipeline writes it after a healthy deploy)."""
    gate()
    try:named=host.lstat(DEPLOY_VERSION_NAME,directory.fd)
    except FileNotFoundError:raise Refused('DEPLOY_VERSION_ABSENT') from None
    need(stat.S_ISREG(named.st_mode),'DEPLOY_VERSION_NOT_REGULAR')
    raw,_=read_regular(host,DEPLOY_VERSION_NAME,directory.fd,gate,128)
    need(raw.strip()==EPOCH_REVISION.encode('ascii'),'DEPLOY_VERSION_MISMATCH')

def env_file_state(host,directory,gate):
    """What tells that the environment file is the same object with the same bytes as at another instant of this run:
    its signature and the hash of its bytes. Both stay in memory: no value, digest or size of that file leaves the run."""
    gate()
    try:named=host.lstat(ENV_FILE_NAME,directory.fd)
    except FileNotFoundError:raise Refused('ENV_FILE_ABSENT') from None
    need(stat.S_ISREG(named.st_mode),'ENV_FILE_NOT_REGULAR')
    raw,info=read_regular(host,ENV_FILE_NAME,directory.fd,gate,MAX_ENV_FILE_BYTES)
    return stat_signature(info),sha(raw)

def project_directory(host,plan,deploy,gate,pinned):
    """The directory of the compose project in the deploy tree, <deploy>/<project>, by name under the pinned deploy
    tree, never through a link (the deploy job fills it by rsync: c3po-pipeline.yml:702-711). Returns it held."""
    name=plan['compose']['project'];gate()
    try:named=host.lstat(name,deploy.fd)
    except FileNotFoundError:raise Refused('COMPOSE_FILE_ABSENT') from None
    need(stat.S_ISDIR(named.st_mode),'COMPOSE_DIRECTORY_NOT_A_DIRECTORY')
    gate();fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=deploy.fd)
    directory=hold(host,fd,pinned,parent=deploy,name=name)
    need(directory.identity[:2]==(named.st_dev,named.st_ino),'COMPOSE_DIRECTORY_NOT_A_DIRECTORY')
    return directory

def compose_file_state(host,directory,gate):
    """The same for the compose file of the deploy. Its text is never judged here (the render is): this only tells
    whether it is the object, with the bytes, that the first render was made from. The render has no other input
    than this file, the environment file and the build revision of the command (c3po/compose.yml at the release)."""
    gate()
    try:named=host.lstat(COMPOSE_FILE_NAME,directory.fd)
    except FileNotFoundError:raise Refused('COMPOSE_FILE_ABSENT') from None
    need(stat.S_ISREG(named.st_mode),'COMPOSE_FILE_NOT_REGULAR')
    raw,info=read_regular(host,COMPOSE_FILE_NAME,directory.fd,gate,MAX_COMPOSE_FILE_BYTES)
    return stat_signature(info),sha(raw)

def reached_by_name(holder,gate):
    """True while the way from '/' still leads to the directory held, by its name (Pinned.verify of the core: the chain
    walked again, or the name looked at again in the parent). What is read through a descriptor is only then what the
    path shows. An expired window is not an answer and is raised."""
    try:holder.verify(gate);return True
    except Refused as error:
        if str(error)!='PARENT_REPLACED':raise
        return False

def free_inodes(host,fd):
    """Inodes a non-root writer can still take on the filesystem of a held descriptor; None where the filesystem
    counts none (f_files 0: it does not run out of them apart from its bytes)."""
    numbers=host.fstatvfs(fd);total,free=getattr(numbers,'f_files',0),getattr(numbers,'f_favail',None)
    return free if integer(total,1) and integer(free) else None

def leftovers(rows,container):
    """Containers a recreate of the service left behind: while compose replaces the container of a service, one of the
    two (the one being replaced, or the one that replaces it, depending on the compose version) carries the name
    <12 hex of an ID>_<name of the service's container>. With one present, a recreate cannot leave the listing as it
    was, and an earlier recreate is known to have been interrupted."""
    return [row for row in rows if row['name'].endswith('_'+container)]

def alive(row):
    """A container that runs: the flag and the state both say so (a paused or restarting container has the flag alone)."""
    return row['running'] is True and row['state']=='running'

def plain(path):
    """An absolute path as compose may print it (a trailing or a doubled slash, a "." component) in the one spelling the
    signed paths have; anything else stays as it is, and so stays unequal to a signed path."""
    return str(PurePosixPath(path)) if type(path) is str else path

def stopwatch(monotonic):
    """read() gives the milliseconds since now, or None when the clock fails: a timing is reported, it never decides
    and never raises."""
    try:start=monotonic()
    except Exception:start=None
    def read():
        try:return int(round((monotonic()-start)*1000))
        except Exception:return None
    return read

def service_of(rendered,plan):
    """What a render must say of the worker service: the build revision of the epoch, the four signed values, and that
    the two files the values name are reached through the one bind of the data root at the signed target."""
    service=compose_service(rendered,WORKER_SERVICE);environment=service['environment'];expected=environment_of(plan)
    need(environment.get(BUILD_KEY)==EPOCH_REVISION,'RENDER_BUILD_REVISION')
    need(all(environment.get(key)==value for key,value in expected.items()),'RENDER_ENVIRONMENT_MISMATCH')
    need(text(service['image'],REFERENCE) and not service['image'].startswith('-'),'RENDER_IMAGE_INVALID')
    volumes=rendered['services'][WORKER_SERVICE].get('volumes')
    need(type(volumes) is list and len(volumes)<=64 and all(type(item) is dict and type(item.get('target')) is str and item['target'] for item in volumes),
         'RENDER_VOLUMES_INVALID')
    binds=[(plain(item['target']),item) for item in volumes]
    for path in (expected[KEY_POLICY_FILE],expected[KEY_RELEASE_FILE]):
        covering=[pair for pair in binds if inside(path,pair[0])]
        need(len(covering)==1 and covering[0][0]==plan['worker']['mount_target'] and covering[0][1].get('type')=='bind'
             and plain(covering[0][1].get('source'))==plan['data_root'] and covering[0][1].get('read_only') in (None,False),'WORKER_MOUNT_NOT_AS_SIGNED')
    return service

def worker_status(host,name,directory,gate):
    """Informational, never decides: the two constant codes of the status file the controller of the new worker writes
    next to the policy, when it already exists. LIVE_EPOCH_NOT_FOUND is what it says while no epoch row exists."""
    def code(value):return value if text(value,'[A-Z0-9_]{1,100}') else None
    try:
        try:named=host.lstat(name,directory.fd)
        except FileNotFoundError:return {'present':False,'status':None,'readiness':None}
        if not stat.S_ISREG(named.st_mode):return {'present':None,'status':None,'readiness':None}
        raw,_=read_regular(host,name,directory.fd,gate,65536);value=strict(raw)
        if type(value) is not dict:return {'present':True,'status':None,'readiness':None}
        return {'present':True,'status':code(value.get('status')),'readiness':code(value.get('readiness'))}
    except Exception:return {'present':None,'status':None,'readiness':None}

AFTER_FACTS=('worker_listed_once','worker_is_new','old_container_gone','running','restarts','image_is_the_signed_one','environment_as_signed',
             'others_unchanged','others_states_unchanged','others_appeared','others_gone','others_same_name_new_id','service_leftovers',
             'env_file_unchanged','compose_file_unchanged','release_unchanged','files_as_delivered','directory_entries','lock_still_named',
             'settle_pause_taken','second_check_passed','milliseconds_between_checks','worker_status')
def read_after(c):
    """Everything read after the recreate command was started, each fact on its own: a read that fails leaves its
    facts None and its constant code under its step, and never hides another. Returns (facts, failed, unchanged);
    unchanged is True only when the worker is proved to be the container it was, as it was, in an unchanged listing."""
    host,gate,commands,plan,before,container=c['host'],c['gate'],c['commands'],c['plan'],c['before'],c['container']
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
            values=container_environment(commands,seen['first']['id'],c['signed'])
            facts['environment_as_signed']=all(item=={'present':True,'equal':True} for item in values.values())
    def containers():
        rows=container_list(commands);named=[row['id'] for row in rows if row['name']==container]
        def others(source,states):return sorted((row['id'],row['name'])+((row['state'],) if states else ()) for row in source if row['name']!=container)
        facts.update(worker_listed_once=len(named)==1 and ('first' not in seen or named==[seen['first']['id']]),
                     old_container_gone=before['id'] not in [row['id'] for row in rows],
                     others_unchanged=others(rows,False)==others(c['listing'],False),others_states_unchanged=others(rows,True)==others(c['listing'],True))
        if 'first' not in seen and len(named)==1:facts['worker_is_new']=named[0]!=before['id']      # the inspect failed: the listing still says which container it is
        seen['listing_unchanged']=sorted((row['id'],row['name']) for row in rows)==sorted((row['id'],row['name']) for row in c['listing'])
        # numbers only, never judged: what of the other containers differs, by name (names are unique in an engine), and
        # how many containers carry a temporary name of the worker's (an interrupted recreate, of either compose order)
        was={row['name']:row['id'] for row in c['listing'] if row['name']!=container};now={row['name']:row['id'] for row in rows if row['name']!=container}
        facts.update(others_appeared=len([name for name in now if name not in was]),others_gone=len([name for name in was if name not in now]),
                     others_same_name_new_id=len([name for name in now if name in was and now[name]!=was[name]]),service_leftovers=len(leftovers(rows,container)))
    def environment_file():facts['env_file_unchanged']=reached_by_name(c['deploy'],gate) and env_file_state(host,c['deploy'],gate)==c['env_before']
    def compose_file():facts['compose_file_unchanged']=reached_by_name(c['project'],gate) and compose_file_state(host,c['project'],gate)==c['compose_before']
    def release():facts['release_unchanged']=reached_by_name(c['release_directory'],gate) and release_state(host,plan,c['release_directory'],gate)==c['release_before']
    def delivered():
        # each readback proves the directory again first (its descriptor, its name in the pinned parent, owner and mode),
        # then the file: the inode this run created, one link, root:root 0600, the signed bytes
        directory=c['handles']['DIRECTORY'];codes=[readback_file(row,raw,PRIVATE_FILE_MODE,directory,host,gate) for row,raw in zip(c['ledger'],c['contents'])]
        facts['directory_entries']=count_entries(host,directory.fd,gate,MAX_DIRECTORY_ENTRIES)
        facts['files_as_delivered']=codes==[None,None]
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
    def status():facts['worker_status']=worker_status(host,plan['policy']['name']+STATUS_SUFFIX,c['handles']['DIRECTORY'],gate)
    for label,action in (('WORKER',worker),('ENVIRONMENT',environment),('CONTAINERS',containers),('ENV_FILE',environment_file),('COMPOSE_FILE',compose_file),
                         ('RELEASE',release),('FILES',delivered),('LOCK',locked),('SETTLE',settle),('SECOND_CHECK',second),('WORKER_STATUS',status)):step(label,action)
    first=seen.get('first')
    unchanged=bool(first is not None and seen.get('listing_unchanged') is True and alive(first)
                   and all(first[key]==before[key] for key in ('started_at','restarts')))
    return facts,failed,unchanged

def _reduce_precheck(receipt):receipt['precheck']={'reduced_for_size':True}
def _reduce_chains(receipt):receipt['chains']={key:len(rows) for key,rows in (receipt.get('chains') or {}).items()}
REDUCTIONS=[('PRECHECK_DROPPED',_reduce_precheck),('CHAINS_REDUCED_TO_COUNTS',_reduce_chains)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    content,_=policy_of(plan);override=override_of(plan);expected=environment_of(plan)                      # pure
    signed=dict(expected);signed[BUILD_KEY]=EPOCH_REVISION
    compose=plan['compose'];container=worker_name(plan);live=live_path(plan);listed=compose['files']+[override_path(plan)]
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    detail={'chains':{},'precheck':{},'budget':{}};directories=[];ledger=[];handles={};pinned=[];lock=[None]
    commands=Commands(host,gate);go16=bound['go_sha256'][:16]
    run={'state':'NOT_STARTED','code':None,'returncode':None,'started':False,'returned':False,'milliseconds':None,'replaced':False,'facts':None,'unavailable':None}
    def finish(status,outcome,code,extra):
        receipt=envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),clock=timing(begun,mark,clock,monotonic),
            commands_started=dict(commands.started),mutating_calls=state.counts(),chains=detail['chains'],precheck=detail['precheck'],budget=detail['budget'],
            directories=directories,ledger=ledger,recreate=run,objects_left_by_this_run=objects_left(directories,ledger),
            worker_container_replaced=run['replaced'],pre_existing_objects_modified=run['replaced'] is not False,**extra))
        return seal(receipt)
    def chain(key,rows):
        seen=[];detail['chains'][key]=seen
        return hold(host,walk_pinned(host,rows,gate,seen),pinned,rows=rows)
    try:
        # ---- everything is looked at before the first creation
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o077)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            parent=chain('LIVE_PARENT',plan['live_parent'])
            found=probe(host,live,gate);detail['precheck']['directory']={'exists':found.get('exists')}
            need(found.get('exists') is False,'DESTINATION_PRESENT')                 # absent, proved: an unreadable path is not an absence
            need(probe(host,pin_path(plan),gate).get('type')=='file','MAINTENANCE_PIN_ABSENT')
            release_directory=installed_release(host,plan,chain('RELEASE_PARENT',plan['release']['parent']),gate,pinned)
            release_before=release_state(host,plan,release_directory,gate)
            deploy=chain('DEPLOY_DIRECTORY',plan['deploy_directory'])
            deploy_version(host,deploy,gate)
            env_before=env_file_state(host,deploy,gate)
            project=project_directory(host,plan,deploy,gate,pinned)
            compose_before=compose_file_state(host,project,gate)
            lock_directory=chain('LOCK_DIRECTORY',plan['lock']['directory'])
            lock[0]=open_lock(host,LOCK_FILE_NAME,lock_directory,gate)
            detail['precheck'].update(maintenance_pin_present=True,release_installed_as_signed=True,deploy_version_is_the_revision=True)
            # the worker as it is, its image, and that it is not activated yet
            before=container_facts(commands,container)
            detail['precheck']['worker']={'id':before['id'],'started_at':before['started_at'],'restarts':before['restarts'],'state':before['state']}
            need(alive(before),'WORKER_NOT_RUNNING')
            need(before['image_id']==plan['worker']['image_id'],'WORKER_IMAGE_NOT_THE_SIGNED_ONE')
            try:image=image_facts(commands,plan['worker']['image_id'])
            except CommandFailed:raise Refused('IMAGE_ABSENT_OR_UNREADABLE') from None
            need(image['id']==plan['worker']['image_id'] and image['revision_label']==EPOCH_REVISION,'IMAGE_REVISION_MISMATCH')
            values=container_environment(commands,before['id'],signed)
            need(values[BUILD_KEY]=={'present':True,'equal':True},'WORKER_BUILD_REVISION')
            need(not any(values[key]['present'] for key in ACTIVATION_KEYS),'WORKER_ALREADY_CARRIES_THE_KEYS')
            # the render the recreate will be made from, with the override still only bytes; timed, because the same
            # render runs again from the files between the first creation and the recreate
            began=monotonic()
            service=service_of(compose_render(commands,'render',compose['project'],compose['env_file'],compose['files'],EPOCH_REVISION,override=override),plan)
            measured=monotonic()-began
            try:resolved=image_facts(commands,service['image'])
            except CommandFailed:raise Refused('RENDER_IMAGE_UNRESOLVED') from None
            need(resolved['id']==plan['worker']['image_id'],'RENDER_IMAGE_CHANGED')
            detail['precheck']['render']={'environment_as_signed':True,'image_is_the_running_one':True,'data_root_bound_at_the_signed_target':True}
            # The last refusals before the first effect: the lock (waited for at most the signed seconds, and never
            # past the point where what follows would no longer fit), what is read again once it is held, the time.
            allowance=min(COMMAND_CLASSES['RENDER']['seconds'],max(RENDER_ALLOWANCE_FLOOR_SECONDS,int(2*measured)+1))
            needed=effects_budget('recreate')+allowance+FILES_ALLOWANCE_SECONDS+SETTLE_SECONDS
            detail['budget']={'first_render_milliseconds':int(measured*1000),'render_allowance_seconds':allowance,'needed_before_first_effect_seconds':needed,
                              'kept_while_waiting_for_the_lock_seconds':needed+UNDER_LOCK_ALLOWANCE_SECONDS,'left_when_the_lock_was_asked_for_milliseconds':int(gate()*1000)}
            detail['precheck']['lock_attempts']=acquire_lock(host,lock[0],gate,plan['lock']['wait_seconds'],needed+UNDER_LOCK_ALLOWANCE_SECONDS)
            need(lock_still_named(host,LOCK_FILE_NAME,lock_directory,lock[0]),'LOCK_FILE_REPLACED')
            pending=probe(host,REBOOT_PENDING_PATH,gate)
            need(pending.get('status')=='COMPLETE','REBOOT_STATE_UNAVAILABLE');need(pending.get('exists') is False,'SECURITY_REBOOT_PENDING')
            # what was read through a descriptor is what the path shows only while the name still leads to it: the
            # three directories that are held and not re-proved by a creating call (the live parent is, by the core)
            need(reached_by_name(release_directory,gate),'RELEASE_DIRECTORY_REPLACED')
            need(reached_by_name(project,gate),'DEPLOY_TREE_REPLACED')                # proves the deploy tree first, then the project directory in it
            need(reached_by_name(lock_directory,gate),'LOCK_DIRECTORY_REPLACED')
            deploy_version(host,deploy,gate)
            need(env_file_state(host,deploy,gate)==env_before,'ENV_FILE_CHANGED_BEFORE_THE_LOCK')
            need(compose_file_state(host,project,gate)==compose_before,'COMPOSE_FILE_CHANGED_BEFORE_THE_LOCK')
            need(release_state(host,plan,release_directory,gate)==release_before,'RELEASE_CHANGED_BEFORE_THE_LOCK')
            again=container_facts(commands,container)
            need(all(again[key]==before[key] for key in ('id','started_at','restarts')) and alive(again),'WORKER_CHANGED_BEFORE_THE_LOCK')
            listing=container_list(commands)
            need([row['id'] for row in listing if row['name']==container]==[before['id']],'CONTAINER_LIST_INCONSISTENT')
            # a container left by an interrupted recreate of the service: compose would remove or replace it during the
            # recreate, so the listing could not stay as it is and the run could not complete
            need(not leftovers(listing,container),'WORKER_SERVICE_LEFTOVER_CONTAINER')
            # room for one directory and two small files, where it is knowable before the first creation
            free,inodes=free_bytes(host,parent.fd),free_inodes(host,parent.fd)
            detail['precheck'].update(reboot_pending=False,containers_listed=len(listing),free_bytes=free,free_inodes=inodes)
            need(free>=FREE_BYTES_FLOOR,'DATA_VOLUME_FREE_SPACE_BELOW_FLOOR')
            need(inodes is None or inodes>=FREE_INODES_FLOOR,'DATA_VOLUME_FREE_INODES_BELOW_FLOOR')
            left=gate();detail['budget']['left_before_first_effect_milliseconds']=int(left*1000)
            need(left>=needed,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})
        # ---- from here on nothing refuses unless nothing has changed
        stop=None;contents=(content,override)
        entry=create_directory('DIRECTORY',live,PRIVATE_DIRECTORY_MODE,parent,host,gate,state,handles);directories.append(entry)
        if entry['state']!='CREATED_DURABLE':stop=entry['code'] or 'CREATION_FAILED'
        for index,(key,path,raw) in enumerate((('POLICY',policy_path(plan),content),('OVERRIDE',override_path(plan),override))):
            if stop is not None:
                ledger.append({'key':key,'path':path,'state':'NOT_ATTEMPTED','code':None});continue
            row=create_file(index,key,path,raw,PRIVATE_FILE_MODE,handles['DIRECTORY'],host,gate,state,go16);ledger.append(row)
            if row['state']!='INSTALLED_DURABLE':stop=row['code'] or 'INSTALL_FAILED'
        if stop is None:
            for row,raw in zip(ledger,contents):stop=stop or readback_file(row,raw,PRIVATE_FILE_MODE,handles['DIRECTORY'],host,gate)
        if stop is None:stop=readback_directory(live,PRIVATE_DIRECTORY_MODE,handles['DIRECTORY'],host,gate,len(contents))
        if stop is None:
            # under the lock, with the override now a file: the render the recreate will use
            taken=stopwatch(monotonic)
            try:
                need(lock_still_named(host,LOCK_FILE_NAME,lock_directory,lock[0]),'LOCK_FILE_REPLACED')
                need(service_of(compose_render(commands,'render_files',compose['project'],compose['env_file'],listed,EPOCH_REVISION),plan)['image']==service['image'],
                     'RENDER_IMAGE_CHANGED')
                # last, right before the one command that changes the worker: the names still lead to what is held
                need(reached_by_name(release_directory,gate),'RELEASE_DIRECTORY_REPLACED')
                need(reached_by_name(project,gate),'DEPLOY_TREE_REPLACED')
                need(reached_by_name(lock_directory,gate),'LOCK_DIRECTORY_REPLACED')
            except Exception as error:stop=code_of(error,'RECREATE_PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'RECREATE_PRECHECK_FAILED')
            detail['budget']['render_from_the_files_milliseconds']=taken()
        if stop is None:
            taken=stopwatch(monotonic)
            result=compose_up(state,commands,'recreate',compose['project'],compose['env_file'],listed,EPOCH_REVISION)
            run.update(started=result['started'],returned=result['returned'],returncode=result['returncode'],code=result['code'],milliseconds=taken())
            if not result['started']:stop=result['code'] or 'COMMAND_NOT_STARTED'
            else:
                # the command was started: what it left is read on the host, and only then is the call settled
                facts,failed,unchanged=read_after({'host':host,'gate':gate,'commands':commands,'plan':plan,'before':before,'container':container,
                    'listing':listing,'signed':signed,'deploy':deploy,'env_before':env_before,'handles':handles,'ledger':ledger,'contents':contents,
                    'project':project,'compose_before':compose_before,'release_directory':release_directory,'release_before':release_before,
                    'lock_directory':lock_directory,'lock':lock[0],'monotonic':monotonic})
                run.update(facts=facts,unavailable=failed)
                criteria=[(result['code'] or 'RECREATE_RETURNED_NONZERO',bool(result['returned'] and result['returncode']==0)),
                          ('WORKER_NOT_FOUND_AFTER_RECREATE',facts['worker_listed_once']),('WORKER_NOT_RECREATED',facts['worker_is_new']),
                          ('OLD_CONTAINER_STILL_PRESENT',facts['old_container_gone']),('WORKER_NOT_RUNNING_AFTER_RECREATE',facts['running']),
                          ('WORKER_RESTARTED_AFTER_RECREATE',None if facts['restarts'] is None else facts['restarts']==0),
                          ('WORKER_IMAGE_CHANGED',facts['image_is_the_signed_one']),('ENVIRONMENT_NOT_AS_SIGNED',facts['environment_as_signed']),
                          ('OTHER_CONTAINERS_CHANGED',facts['others_unchanged']),('ENV_FILE_CHANGED',facts['env_file_unchanged']),
                          ('COMPOSE_FILE_CHANGED',facts['compose_file_unchanged']),('RELEASE_CHANGED',facts['release_unchanged']),
                          ('FILES_NOT_AS_DELIVERED',facts['files_as_delivered']),('LOCK_FILE_REPLACED',facts['lock_still_named']),
                          ('SECOND_CHECK_NOT_APART',facts['settle_pause_taken']),('WORKER_CHANGED_BETWEEN_THE_TWO_CHECKS',facts['second_check_passed'])]
                # a criterion that is False names itself; one that could not be read (None) is READBACK_UNAVAILABLE
                missing=[name if value is False else 'READBACK_UNAVAILABLE' for name,value in criteria if value is not True]
                if not missing:
                    state.done();run.update(state='RECREATED_VERIFIED',replaced=True)
                elif result['returned'] and unchanged:
                    # a read proved that nothing changed: the same container, as it was, in an unchanged listing
                    state.fail();run.update(state='NOT_RECREATED',replaced=False)
                    stop='RECREATE_FAILED_CONTAINER_UNCHANGED' if result['returncode'] else 'RECREATE_RETURNED_ZERO_CONTAINER_UNCHANGED'
                else:
                    if result['returned']:state.unknown()
                    if facts['worker_is_new'] is True:
                        once=not [name for name,value in criteria[:-2] if value is not True] and facts['second_check_passed'] is not False
                        run.update(state='RECREATED_VERIFIED_ONCE' if once else 'RECREATED_NOT_VERIFIED',replaced=True)
                    else:run.update(state='UNCERTAIN',replaced=None)
                    stop=missing[0]
        extra={'phase_reached':'EFFECTS','readback':'COMPLETE' if stop is None else None}
        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        # REFUSED only while no mutating call succeeded and none is uncertain; otherwise the run is a partial.
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        outcome={'RECREATED_VERIFIED_ONCE':NOT_VERIFIED_OUTCOME,'RECREATED_NOT_VERIFIED':NOT_VERIFIED_OUTCOME,'UNCERTAIN':UNCERTAIN_OUTCOME}.get(run['state'],OBJECTS_ONLY_OUTCOME)
        return finish(PARTIAL_STATUS,outcome,stop,extra)
    finally:
        if lock[0] is not None:release_lock(host,lock[0])
        for handle in list(handles.values())+pinned:
            try:handle.close()
            except Exception:pass
