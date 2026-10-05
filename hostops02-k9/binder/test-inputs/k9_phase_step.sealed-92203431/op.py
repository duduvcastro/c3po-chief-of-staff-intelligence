OPERATION='GO_WRITE_HOSTOPS02_K9_PHASE_STEP_01'
PHASE='WRITE_K9_PHASE_STEP'
REQUEST_SCHEMA='WRITE_HOSTOPS02_K9_PHASE_STEP_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_K9_PHASE_STEP_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_K9_PHASE_STEP_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_K9_PHASE_STEP_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_K9_PHASE_STEP_PLAN_V1'
SOURCE_NAME='k9_phase_step.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False
DATE_CLASS='WRITE_SESSIONS'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
# The rows and the boot every request signs come from a TREE receipt of the read program (K9R) of the same boot.
EVIDENCE_OPERATIONS=('GO_READONLY_HOSTOPS02_K9_PHASE_READ_01',)
MAX_GATE_SPAN_SECONDS=900
# Exit 0 exists for one outcome per mode of the signed operation (the mode follows the operation, section 2 of DESIGN.md).
COMPLETE_OUTCOME='K9_STEP_LAUNCHED_DETACHED_READ_BACK'
K9W_ATTACHED_OUTCOME='K9_STEP_RAN_ATTACHED_RECEIPT_COMPLETE'
K9W_CLEANUP_OUTCOME='K9_CONTAINER_REMOVED_READ_BACK'
K9W_REMOVAL_ONLY_OUTCOME='K9_REMOVAL_ONLY_PREDECESSOR_NOT_COMPLETE'
K9W_NOT_COMPLETE_OUTCOME='K9_STEP_RAN_NOT_COMPLETE'
PARTIAL_OUTCOME='K9_STEP_PARTIAL_REQUIRES_REVIEW'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='K9_STEP_PARTIAL_REQUIRES_REVIEW'
ESCAPED_OUTCOME='K9_STEP_ESCAPED_STATE_UNKNOWN'
K9W_MODES=('LAUNCH','ATTACHED','CLEANUP')
K9W_SUCCESS={'LAUNCH':COMPLETE_OUTCOME,'ATTACHED':K9W_ATTACHED_OUTCOME,'CLEANUP':K9W_CLEANUP_OUTCOME}
PLAN_KEYS=frozenset(('mode','epoch','day','k9_phase','k9_operation','slot','attempt_key','run_not_after','constants','parent_rows',
                     'evidence_boot_id_sha256','bind'))

# ---------------------------------------------------------------- the epoch and the frozen interface (the same values as K9R)
K9W_EPOCH='R2D2-V2-SHADOW-2026-10-05'
K9W_DAYS=('2026-10-06','2026-10-07','2026-10-08','2026-10-09')        # Monday 05/10 has no K9 list (K9_INTERFACE_NOTE.md 5.5)
K9W_NOTE_SHA256='ab5159bea34b3239379e87c2500d383f0777cc6186618435ba0ea9f61e3d596c'        # K9_INTERFACE_NOTE.md rev 2
K9W_OPERATIONS_SHA256='bc796cb7d6d8ab29e314ad29c726f33f16f3b83dfcede7771ec2b2cdae0e7d08'  # K9_OPERATIONS.json beside it
K9W_PACKAGE_SHA256='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'
K9W_CODE_REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
K9W_SLOTS=('PRIMARY','SPARE')
# The reviewed runner (W/fable-k9runner-20261004/k9_runner.py rev 2, 40,618 bytes): the ONE place its hash is written.
# A new runner is a new value here, a new payload hash and a new review. TREE hashes the delivered file's bytes.
K9W_RUNNER_SHA256='563a4797ab2a7ef4c02a1c1937061a2644420b69bdcc2dca842cd1efd7fb7690'
K9W_ROOT='/var/lib/c3po/r2d2-v2-k9-20261005'
# Revision 2, Codex's decision 6 (#429 comment 5985748037): the source root moves off the data volume (whose root is
# uid 1000's) to /var/lib/c3po, under the same root-only chain as the K9 tree and on the filesystem of days/; no open
# root anywhere. Every bind source and every one of its ancestors is root-controlled, so no other account can swap a
# directory a container binds. The rest is Codex's N-8 decision of 2026-10-04 (W/codex-n8-placement-20261004.txt).
K9W_SOURCE_ROOT='/var/lib/c3po/r2d2-v2-source-20261005'
K9W_PLACEMENT={'k9_root':K9W_ROOT,'source_root':K9W_SOURCE_ROOT,'days':K9W_ROOT+'/days','tools':K9W_ROOT+'/tools','claims':K9W_ROOT+'/claims',
               'secrets':K9W_ROOT+'/secrets','emitter':K9W_ROOT+'/secrets/emitter','provider_env_file':K9W_ROOT+'/secrets/provider.env',
               'risk_db_env_file':K9W_ROOT+'/secrets/risk-db.env','emitter_password':K9W_ROOT+'/secrets/emitter/password',
               'source_open_root':None,'k9_open_root':None,'decision':'d30f7f9048af4a39cf4fa7d9f49292ad387a2d41f33bad39816e83d3d1fc2c53',
               'decision_6':'#429 comment 5985748037','september_open_root':'/mnt/day-d-data'}
# (K9R rev 4's object, byte for byte. september_open_root names the data volume only for K3-K9's read of the September
# secret files; no chain of this source has an open root.)
K9W_PARENT_CHAINS=('days','source_root','secrets','tools','claims')
K9W_RECEIVES_ENTRY=('days','source_root','claims')
# Codex (#429): 200 GiB available, f_bavail * f_frsize of fstatvfs on the open descriptor of days/; below it: HOLD (a refusal here).
K9W_DISK_FLOOR_BYTES=214748364800
K9W_RISK_LIMITS={'max_symbols':550,'max_total_requests':2200,'max_body_bytes':16777216,'max_total_bytes':1073741824,'max_elapsed_seconds':3600}
K9W_PROVIDER_NETWORK='bridge'
K9W_NETWORK_CLASSES=('PROVIDER','DATABASE','DATABASE_AND_PROVIDER')
K9W_CONSTANT_KEYS=frozenset(('k9_interface_note_sha256','act_b_sha256','package_sha256','code_revision','release_sha256','policy_sha256','image_id',
                             'runner_sha256','probe_snippet_sha256','networks','step_table_sha256','risk_source_pins_sha256','risk_limits',
                             'readiness_rule','disk_floor_bytes','placement'))
K9W_PRIVATE_DIRECTORY_MODE=0o700
K9W_PRIVATE_FILE_MODE=0o600

# ---------------------------------------------------------------- limits and grammar
K9W_MAX_SMALL_FILE=262144                # launch records, start markers, step receipts, step plans
K9W_MAX_PLAN_FILE=16777216               # HOST_PLAN.json and GO.json of the packaged risk plan, the packaged receipts
K9W_MAX_SYMBOLS_FILE=1048576             # control/symbols.txt
K9W_MAX_OUTPUTS=64
K9W_MAX_AGGREGATES=8
K9W_MAX_AGGREGATE_ENTRIES=4096
K9W_MAX_COUNT=10000000
K9W_MAX_LIMIT=1<<40
K9W_ENTRY='[A-Za-z0-9][A-Za-z0-9._-]{0,127}'
K9W_OUTPUT_KEY=r'(day|source)(/[A-Za-z0-9][A-Za-z0-9._=-]{0,127}){1,8}'
K9W_NETWORK_NAME='[A-Za-z0-9][A-Za-z0-9_.-]{0,63}'
K9W_COUNT_KEY='[a-z][a-z0-9]{0,30}(_[a-z0-9]{1,30}){1,4}'      # a runner's counts: constant snake names with an underscore, never a ticker (K9R rev 3)
K9W_MAX_COUNTS=64
K9W_ORDER_SCHEMA='R2D2_V2_RISK_HOST_ORDER_V1'
K9W_ORDER_ACTIONS=['READ_PROVIDERS','READ_DATABASE','WRITE_PRIVATE_RISK_ARTIFACTS']
K9W_RISK_PHASES=['preflight','acquire','execute']
K9W_RISK_NAMESPACE='R2D2-V2-DIAG-R4-'        # + D (Codex's answer to N-1: the label is private to the risk spool)
K9W_MIN_TIMEOUT_SECONDS=90             # > the runner's own stop, 60 s before run_not_after (runner MARGIN)
K9W_LAUNCH_MARGIN_SECONDS=5              # a LAUNCH container's own limit ends 5 s before run_not_after
K9W_CEILING_SLACK_SECONDS=900            # and never more than its ceiling + the longest write window after its creation
K9W_FILES_ALLOWANCE_SECONDS=4            # the files written between the first and the last effect (claim, plan, directories)
K9W_EXPIRED=('GO_EXPIRED','CLOCK_REVERSED')
# Needs that are a state of the host, not of the chain: a refusal (HOLD), never removal-only, so that the attempt key is
# not spent and the same request can run once the condition is gone (Codex: HOLD below the floor).
K9W_HOLD_CODES=('DISK_FREE_BELOW_FLOOR','ENV_FILE_NOT_PRIVATE','EMITTER_SECRET_NOT_PRIVATE','RUNNER_FILE_NOT_AS_REQUIRED')

# ---------------------------------------------------------------- the files the read program (K9R) and the runner share with this one
K9W_RECORD_SCHEMA='K9_LAUNCH_RECORD_V1'
K9W_RECORD_KEYS=frozenset(('schema','epoch','day','operation','slot','attempt_key','request_sha256','step_plan_sha256','container_id',
                           'container_name','created_at','started_at','timeout_seconds'))
K9W_STARTED_SCHEMA='K9_STEP_STARTED_V1'
K9W_STARTED_KEYS=frozenset(('schema','epoch','day','phase','operation','attempt_key','step_plan_sha256','started_at'))
K9W_STEP_SCHEMA='K9_STEP_RECEIPT_V1'
K9W_STEP_KEYS=frozenset(('schema','status','code','epoch','day','phase','operation','attempt_key','step_plan_sha256','started_at','completed_at',
                         'package_sha256','build_sha','outputs','aggregates','counts'))
K9W_STEP_FAILED_STATUSES=('REFUSED','FAILED','DEADLINE')
K9W_PACKAGED_RECEIPT_SCHEMA='R2D2_V2_RISK_HOST_PHASE_RECEIPT_V1'
K9W_PACKAGED_RECEIPT_KEYS=frozenset(('schema','phase','status','manifest_sha256','go_sha256','namespace','session_date','started_at','completed_at',
                                     'previous_receipt_sha256','outputs','operation_activation','certification_granted'))
K9W_PACKAGED_STARTED_KEYS=frozenset(('phase','manifest_sha256','go_sha256','started_at'))
K9W_PACKAGED_FAILED_SCHEMA='R2D2_V2_RISK_HOST_FAILED_V1'
K9W_PLAN_STEP_SCHEMA='K9_STEP_PLAN_V1'
K9W_CLAIM_KEYS=('epoch','day','phase','operation','slot','request_sha256')
K9W_CONTAINER_PREFIX='c3po-k9-'
K9W_LABEL_ATTEMPT='c3po.k9.attempt_key'
K9W_LABEL_REQUEST='c3po.k9.request_sha256'

# ---------------------------------------------------------------- the closed step table (K9_INTERFACE_NOTE.md 3.1-3.3), compiled
# Inside every K9 container: the tools directory, the day directory, the source root and the emitter secret directory
# at fixed targets. Hosts paths are derived from the placement and from D, never from a request.
K9W_TARGETS={'TOOLS':'/c3po-k9-tools','DAY':'/c3po-k9-day','SOURCE':'/c3po-source','EMITTER':'/c3po-k9-emitter'}
K9W_MOUNTS={'TOOLS':{'host':'tools','target':K9W_TARGETS['TOOLS'],'read_only':True},
            'DAY':{'host':'day','target':K9W_TARGETS['DAY'],'read_only':False},
            'DAY_READ_ONLY':{'host':'day','target':K9W_TARGETS['DAY'],'read_only':True},
            'DAY_RECEIPTS':{'host':'day_receipts','target':K9W_TARGETS['DAY']+'/receipts','read_only':False},
            'SOURCE':{'host':'source_root','target':K9W_TARGETS['SOURCE'],'read_only':False},
            'EMITTER':{'host':'emitter','target':K9W_TARGETS['EMITTER'],'read_only':True}}
K9W_ENV_FILES={'PROVIDER':'provider_env_file','RISK_DATABASE':'risk_db_env_file'}
K9W_FIXED_ENV=['C3PO_R2D2_V2_PRODUCERS_ENABLED=true','C3PO_BUILD_SHA='+K9W_CODE_REVISION]
K9W_DAY_DIRECTORIES=('plans','launches','receipts')
K9W_HOST_PLAN=['risk','plan','HOST_PLAN.json']
K9W_HOST_GO=['risk','plan','GO.json']
def k9w_row(phase,mode,row,network,mounts,env_files,command,ceiling,timeout,needs,removes,absent=(),present=(),symbols=False,emitter=False,
            creates_day=False,packaged_phase=None,latest=None,window_class='BEFORE_OPEN'):
    return {'phase':phase,'mode':mode,'row':row,'network':network,'mounts':list(mounts),'env_files':list(env_files),'command':command,
            'ceiling_seconds':ceiling,'timeout_seconds':timeout,'needs':[list(item) for item in needs],'removes':removes,
            'destinations_absent':[list(item) for item in absent],'destinations_present':[list(item) for item in present],
            'symbols_equal_publish_receipt':symbols,'emitter_password':emitter,'creates_day_directory':creates_day,
            'packaged_phase':packaged_phase,'latest_run_not_after_utc_of_d':latest,'window_class':window_class}
K9W_STEPS={
    'collect_launch':k9w_row('causal_list','LAUNCH','create','PROVIDER',['TOOLS','DAY'],['PROVIDER'],'RUNNER',900,None,[],None,
                             absent=[('days','<D>')],creates_day=True),
    'commit_launch':k9w_row('causal_list','LAUNCH','create','DATABASE',['TOOLS','DAY','EMITTER'],[],'RUNNER',600,None,
                            [('RUNNER','collect_launch')],'collect_launch',absent=[('day','causal')],emitter=True,latest='03:50:00'),
    'publish_launch':k9w_row('causal_list','LAUNCH','create','DATABASE',['TOOLS','DAY','SOURCE','EMITTER'],[],'RUNNER',600,None,
                             [('RUNNER','commit_launch')],'commit_launch',absent=[('day','relay'),('day','control')],emitter=True),
    'components_launch':k9w_row('components','LAUNCH','create','PROVIDER',['TOOLS','DAY','SOURCE'],['PROVIDER'],'RUNNER',2400,None,
                                [('RUNNER','publish_launch')],'publish_launch',absent=[('source','components','<D>')],symbols=True),
    'sources_launch':k9w_row('sources','LAUNCH','create','DATABASE_AND_PROVIDER',['TOOLS','DAY'],['PROVIDER','RISK_DATABASE'],'RUNNER',4500,None,
                             [('RUNNER','publish_launch')],'components_launch',absent=[('day','risk')],symbols=True),
    'bind':k9w_row('risk','ATTACHED','attached','NONE',['TOOLS','DAY'],[],'RUNNER',None,35,[('RUNNER','sources_launch'),('RUNNER','publish_launch')],None,
                   absent=[('day','risk','plan','OWNER_ORDER.json'),('day','risk','plan','SOURCE_PINS.json'),('day','risk','plan','list.private.json'),
                           ('day','risk','plan','HOST_PLAN.json'),('day','risk','plan','GO.json'),('day','risk','spool')],present=[('day','risk','plan')]),
    'preflight':k9w_row('risk','ATTACHED','attached','NONE',['DAY'],[],'PACKAGED',None,35,[('RUNNER','bind')],None,
                        present=[('day','risk','spool')],packaged_phase='preflight'),
    'acquire_launch':k9w_row('risk','LAUNCH','create','DATABASE_AND_PROVIDER',['DAY'],['PROVIDER','RISK_DATABASE'],'PACKAGED',3600,None,
                             [('PACKAGED','preflight')],'sources_launch',packaged_phase='acquire'),
    'execute_launch':k9w_row('risk','LAUNCH','create','NONE',['DAY'],[],'PACKAGED',1200,None,[('PACKAGED','acquire')],'acquire_launch',
                             packaged_phase='execute'),
    'stage':k9w_row('risk','ATTACHED','attached_short','NONE',['TOOLS','DAY_READ_ONLY','DAY_RECEIPTS','SOURCE'],[],'RUNNER',None,18,
                    [('PACKAGED','execute')],'execute_launch',absent=[('source','components','<D>','risk.json')],present=[('source','components','<D>')]),
    'capture_launch':k9w_row('capture','LAUNCH','create','PROVIDER',['TOOLS','DAY','SOURCE'],['PROVIDER'],'RUNNER',780,None,
                             [('RUNNER','publish_launch')],None,window_class='IN_SESSION'),
    'capture_cleanup':k9w_row('capture','CLEANUP',None,None,[],[],None,None,None,[],'capture_launch',window_class='IN_SESSION')}
# run_not_after of the capture launch: 11:03:00 BRT of D (K9_INTERFACE_NOTE.md 4.2, 5.5)
K9W_CAPTURE_RUN_NOT_AFTER='14:03:00'
K9W_STEP_TABLE={'steps':K9W_STEPS,'mounts':K9W_MOUNTS,'env_files':K9W_ENV_FILES,'fixed_env':K9W_FIXED_ENV,'day_directories':list(K9W_DAY_DIRECTORIES),
                'capture_run_not_after_utc_of_d':K9W_CAPTURE_RUN_NOT_AFTER,'risk_namespace_prefix':K9W_RISK_NAMESPACE,
                'launch_timeout':{'margin_seconds':K9W_LAUNCH_MARGIN_SECONDS,'ceiling_slack_seconds':K9W_CEILING_SLACK_SECONDS,
                                  'minimum_seconds':K9W_MIN_TIMEOUT_SECONDS}}
K9W_STEP_TABLE_SHA256=sha(canonical(K9W_STEP_TABLE))
K9W_PHASE_OF={name:row['phase'] for name,row in K9W_STEPS.items()}
K9W_PACKAGED_LAUNCH={'acquire':'acquire_launch','execute':'execute_launch','preflight':'preflight'}

# ---------------------------------------------------------------- the commands
# The format of the read of one K9 container by ID: K9R's K9_LAUNCHED_FORMAT byte for byte. Never the environment.
K9W_LAUNCHED_FORMAT=('{"name":{{json .Name}},"id":{{json .Id}},"image_id":{{json .Image}},"state":{{json .State.Status}},'
                     '"running":{{json .State.Running}},"exit_code":{{json .State.ExitCode}},"oom_killed":{{json .State.OOMKilled}},'
                     '"started_at":{{json .State.StartedAt}},"finished_at":{{json .State.FinishedAt}},'
                     '"attempt_key":{{json (index .Config.Labels "c3po.k9.attempt_key")}},'
                     '"request_sha256":{{json (index .Config.Labels "c3po.k9.request_sha256")}}}')
K9W_LAUNCHED_KEYS=frozenset(('name','id','image_id','state','running','exit_code','oom_killed','started_at','finished_at','attempt_key','request_sha256'))
# A detached K9 container (K9_INTERFACE_NOTE.md 3.1): never pulled, an init, uid 0, a read-only root, no capability, no new
# privilege, never restarted, and NO --rm: the engine keeps it, exited, until a RESULT read has seen its state and exit code.
K9W_CREATE_PREFIX=['create','--pull','never','--init','--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--restart','no']
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'the signed image ID','QUICK','READ'),
          'launched':command_row('docker',['container','inspect','--format',K9W_LAUNCHED_FORMAT],'one 64-hex container ID (a launch record\'s, or the one create printed)','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          'create':command_row('docker',K9W_CREATE_PREFIX,'--name, two --label, --network, up to two --env-file, two --env, up to four --mount, the signed image ID, '
                               'then the command of the step (built by k9w_container_arguments from the compiled step table)','QUICK','EFFECT'),
          'start':command_row('docker',['start'],'exactly the 64-hex ID create printed','RUN_SHORT','EFFECT'),
          'remove':command_row('docker',['rm'],'exactly one 64-hex ID: an exited K9 container named by a launch record, labels and image checked; or the '
                               'container this run created and never started, when a mounted directory changed before start','QUICK','EFFECT'),
          'attached':command_row('docker',RUN_PREFIX,'--name, two --label, up to two --env, up to four --mount, the signed image ID, '
                                 'then the command of the step (bind, preflight)','RUN','EFFECT'),
          'attached_short':command_row('docker',RUN_PREFIX,'--name, two --label, two --env, up to four --mount, the signed image ID, '
                                       'then the command of the step (stage)','RUN_SHORT','EFFECT')}

SCOPE_STATEMENT=('Writes one delegated daily step of epoch R2D2-V2-SHADOW-2026-10-05 and nothing else. Every run first proves the K9 tree, '
                 'the source root and every input by fixed path against the signed rows, then creates its claim file by exclusive creation '
                 '(an existing claim is a refusal). LAUNCH: removes the exited K9 container of the previous step named by its launch record '
                 '(docker rm of that ID, no -f, no -v, only when it is exited and carries that step\'s labels), writes the step plan, creates '
                 'and starts one detached container of the signed image ID with its own time limit and no --rm, and writes the launch record. '
                 'ATTACHED: the same with one attached docker run --rm whose receipt is read back. CLEANUP: the removal alone. When the '
                 'inputs of a step are not complete it removes the previous exited K9 container and refuses (removal-only). It reads no '
                 'secret: the docker CLI reads the environment files. Only the outcome named as success criterion counts.')
SIDE_EFFECTS=['a claim file <k9_root>/claims/<attempt_key>.claim, root:root 0600, by exclusive creation (single use per attempt key: at most one of PRIMARY and SPARE)',
              'collect_launch only: the directories days/<D>, days/<D>/plans, days/<D>/launches, days/<D>/receipts, root:root 0700',
              'the step plan days/<D>/plans/<operation>.json and, after start, the launch record days/<D>/launches/<operation>.json, root:root 0600',
              'LAUNCH: one docker create and one docker start of a container named c3po-k9-<yyyymmdd of D>-<operation> with the labels '
              'c3po.k9.attempt_key and c3po.k9.request_sha256, which then runs on its own up to its timeout -s KILL limit and is kept, exited, by the engine',
              'ATTACHED: one docker run --rm of a container of the same name and labels, ended by its own timeout -s KILL limit',
              'one docker rm of the exited container of the previous step when the table names one and its launch record, labels and image are as written',
              'LAUNCH only: one docker rm of the container this run created, before it is ever started, when a mounted directory is no longer the one held (it never runs)',
              'the docker CLI reads the environment files of the K9 tree as root and gives their values to the container it creates; nothing of them reaches this process',
              'the containers write in days/<D> and, where the table says, in the source root: their bytes are the reviewed runner\'s and the packaged executor\'s, not this source\'s']
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'after_effect_reserve_seconds':AFTER_EFFECT_RESERVE_SECONDS,
       'modes':dict(K9W_SUCCESS),'epoch':K9W_EPOCH,'days':list(K9W_DAYS),'interface_note_sha256':K9W_NOTE_SHA256,
       'operations_sha256':K9W_OPERATIONS_SHA256,'placement':K9W_PLACEMENT,'parent_chains':list(K9W_PARENT_CHAINS),
       'step_table':K9W_STEP_TABLE,'step_table_sha256':K9W_STEP_TABLE_SHA256,'disk_floor_bytes':K9W_DISK_FLOOR_BYTES,
       'contracts':{'launch_record':[K9W_RECORD_SCHEMA,sorted(K9W_RECORD_KEYS)],'start_marker':[K9W_STARTED_SCHEMA,sorted(K9W_STARTED_KEYS)],
                    'step_receipt':[K9W_STEP_SCHEMA,sorted(K9W_STEP_KEYS)],'packaged_receipt':[K9W_PACKAGED_RECEIPT_SCHEMA,sorted(K9W_PACKAGED_RECEIPT_KEYS)],
                    'step_plan':K9W_PLAN_STEP_SCHEMA,'claim':list(K9W_CLAIM_KEYS),'labels':[K9W_LABEL_ATTEMPT,K9W_LABEL_REQUEST]},
       'files':FILES_SCOPE,'side_effects':SIDE_EFFECTS,
       'never':['docker rm -f','docker rm -v','a removal of a container that is not exited, not named by a launch record of this day, or whose labels or image differ '
                '(except the container this run created and never started, withdrawn when a mount source moved)',
                'docker exec','docker kill','docker stop','a pull','a privileged container','a socket or device in a container','a bind other than the four of the table',
                'a shell','a systemctl verb','an overwrite, chmod, chown, rename or removal of a file','a read of a secret file',
                'a value of an environment, a byte or digest of a secret, a symbol of an instrument in the receipt'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'small_file_bytes':K9W_MAX_SMALL_FILE,'plan_file_bytes':K9W_MAX_PLAN_FILE,'symbols_file_bytes':K9W_MAX_SYMBOLS_FILE,
                 'max_arguments':MAX_ARGUMENTS,'files_allowance_seconds':K9W_FILES_ALLOWANCE_SECONDS,
                 'timeouts_before_a_tool_is_skipped':MAX_TOOL_TIMEOUTS}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner,NativeFiles):
    """Everything this source can do to the host: the read primitives, the signed commands and the creating calls of files."""


# ---------------------------------------------------------------- the signed plan (pure)
def k9w_attempt_key(epoch,day,phase,operation):
    """The Act B single-use key: sha256 of the canonical list [epoch, day, phase, operation] (actb03_lib.attempt_key)."""
    return sha(canonical([epoch,day,phase,operation]))

def k9w_day_shift(day,count):
    return datetime.fromordinal(datetime.fromisoformat(day).toordinal()+count).date().isoformat()

def k9w_at(day,clock_text):
    return instant(day+'T'+clock_text+'+00:00')

def k9w_after(point,seconds):
    """point + seconds as a UTC instant (the core imports no timedelta)."""
    return datetime.fromtimestamp(point.timestamp()+seconds,timezone.utc)

def k9w_container_name(day,operation):
    return K9W_CONTAINER_PREFIX+day.replace('-','')+'-'+operation

def k9w_chain(item,path,open_root,receives_entry,code):
    """One signed chain: the core's rule with no open root (every component uid 0, not writable by group or other), and
    (as K4-E0) gid 0 and no setgid bit on every component, and a leaf that is root's private directory (0:0 0700), as E0
    creates every K9 directory and the source root. open_root is always None (decision 6); it stays a member of the
    signed chain object so that the object is K9R's."""
    need(type(item) is dict and set(item)=={'path','rows','open_root'} and item['path']==path and item['open_root']==open_root and item['rows'] is not None,code)
    rows=validate_chain(item['rows'],path,open_root,receives_entry)
    need(all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows),'CHAIN_ROW_GROUP_OR_SETGID')
    need((rows[-1]['uid'],rows[-1]['gid'],rows[-1]['mode'])==(0,0,K9W_PRIVATE_DIRECTORY_MODE),'CHAIN_LEAF_NOT_ROOT_PRIVATE')
    return item

def k9w_instant_text(value,code):
    """An instant written exactly as datetime.isoformat() writes it in UTC."""
    try:point=instant(value)
    except Refused:raise Refused(code) from None
    need(point.isoformat()==value,code)
    return point

def k9w_constants(plan):
    """The week's constants: the same object K9R signs. Compared with the compiled values where this source has them."""
    values=plan['constants']
    need(type(values) is dict and set(values)==K9W_CONSTANT_KEYS,'CONSTANTS_INVALID')
    need(values['k9_interface_note_sha256']==K9W_NOTE_SHA256 and values['package_sha256']==K9W_PACKAGE_SHA256
         and values['code_revision']==K9W_CODE_REVISION,'CONSTANTS_NOT_THE_COMPILED_ONES')
    need(values['placement']==K9W_PLACEMENT,'PLACEMENT_NOT_THE_COMPILED_ONE')
    need(all(hexpin(values[key]) for key in ('act_b_sha256','release_sha256','policy_sha256','runner_sha256','probe_snippet_sha256','step_table_sha256',
                                             'risk_source_pins_sha256')) and text(values['image_id'],IMAGE_ID),'CONSTANTS_INVALID')
    need(values['step_table_sha256']==K9W_STEP_TABLE_SHA256,'STEP_TABLE_NOT_THE_COMPILED_ONE')
    need(values['runner_sha256']==K9W_RUNNER_SHA256,'RUNNER_NOT_THE_COMPILED_ONE')
    networks=values['networks']
    need(type(networks) is dict and set(networks)==set(K9W_NETWORK_CLASSES) and all(text(value,K9W_NETWORK_NAME) for value in networks.values()),'CONSTANTS_INVALID')
    need(networks['PROVIDER']==K9W_PROVIDER_NETWORK and 'none' not in networks.values() and 'host' not in networks.values(),'NETWORKS_NOT_THE_COMPILED_ONES')
    need(canonical(values['risk_limits'])==canonical(K9W_RISK_LIMITS),'RISK_LIMITS_NOT_THE_COMPILED_ONES')
    # K9R's to judge (it compiles the rule and the snippet); here the grammar only, so that one object serves both programs
    rule=values['readiness_rule']
    need(type(rule) is dict and 0<len(rule)<=8 and all(text(key,'[a-z][a-z0-9_]{0,63}') and integer(value,0,K9W_MAX_COUNT) for key,value in rule.items()),'CONSTANTS_INVALID')
    need(integer(values['disk_floor_bytes'],0,K9W_MAX_LIMIT) and values['disk_floor_bytes']==K9W_DISK_FLOOR_BYTES,'DISK_FLOOR_NOT_THE_COMPILED_ONE')
    return values

def k9w_owner_order(day,cutoff_at):
    """The packaged executor's owner order for D (risk_host_executor.py:163-166): its exact canonical bytes."""
    return canonical({'schema':K9W_ORDER_SCHEMA,'actions':list(K9W_ORDER_ACTIONS),
                      'scope':{'namespace':K9W_RISK_NAMESPACE+day,'session_date':day,'cutoff_at':cutoff_at,'phases':list(K9W_RISK_PHASES)}})

def k9w_bind(plan):
    """bind only: the risk documents' signed values. The cutoff and the phase windows are grid instants of D; the owner
    order is the canonical bytes those values determine, carried as ASCII text with their hash for the signer's sheet
    (the runner's RISK_KEYS: namespace, cutoff_at, phase_windows, owner_order_text, owner_order_sha256)."""
    value=plan['bind'];day=plan['day']
    need(type(value) is dict and set(value)=={'namespace','cutoff_at','phase_windows','owner_order_text','owner_order_sha256'},'BIND_INVALID')
    need(value['namespace']==K9W_RISK_NAMESPACE+day,'BIND_NAMESPACE_NOT_THE_COMPILED_ONE')
    cutoff=k9w_instant_text(value['cutoff_at'],'BIND_INVALID')
    windows=value['phase_windows']
    need(type(windows) is dict and set(windows)==set(K9W_RISK_PHASES),'BIND_INVALID')
    bounds={}
    for name in K9W_RISK_PHASES:
        item=windows[name];need(type(item) is dict and set(item)=={'not_before','not_after'},'BIND_INVALID')
        bounds[name]=(k9w_instant_text(item['not_before'],'BIND_INVALID'),k9w_instant_text(item['not_after'],'BIND_INVALID'))
        need(bounds[name][0]<bounds[name][1],'BIND_WINDOWS_INVALID')
    low,high=k9w_at(k9w_day_shift(day,-1),'20:00:00'),k9w_at(day,'13:30:00')
    need(low<=cutoff and all(low<=start and end<=high for start,end in bounds.values()),'BIND_WINDOWS_INVALID')
    need(bounds['preflight'][0]<=bounds['acquire'][0]<=bounds['execute'][0] and cutoff<=bounds['acquire'][0]
         and bounds['acquire'][1]<=bounds['execute'][1],'BIND_WINDOWS_INVALID')
    need(type(value['owner_order_text']) is str and 0<len(value['owner_order_text'])<=4096 and text(value['owner_order_text'],'[ -~]+'),'BIND_ORDER_NOT_ASCII')
    raw=value['owner_order_text'].encode('ascii')
    need(raw==k9w_owner_order(day,value['cutoff_at']),'BIND_ORDER_NOT_THE_DETERMINED_BYTES')
    need(value['owner_order_sha256']==sha(raw),'BIND_ORDER_SHA256_MISMATCH')
    return value

def validate_plan(plan):
    mode=plan['mode'];need(type(mode) is str and mode in K9W_MODES,'MODE_INVALID')
    need(plan['epoch']==K9W_EPOCH,'EPOCH_INVALID')
    k9w_constants(plan)
    day=plan['day'];need(type(day) is str and day in K9W_DAYS,'DAY_INVALID')
    operation=plan['k9_operation'];need(type(operation) is str and operation in K9W_STEPS,'OPERATION_INVALID')
    step=K9W_STEPS[operation]
    need(step['mode']==mode and plan['k9_phase']==step['phase'],'OPERATION_NOT_OF_THIS_MODE')
    need(type(plan['slot']) is str and plan['slot'] in K9W_SLOTS,'SLOT_INVALID')
    need(plan['attempt_key']==k9w_attempt_key(K9W_EPOCH,day,step['phase'],operation),'ATTEMPT_KEY_MISMATCH')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    rows=plan['parent_rows']
    need(type(rows) is dict and set(rows)==set(K9W_PARENT_CHAINS),'PARENT_ROWS_INVALID')
    for name in K9W_PARENT_CHAINS:
        k9w_chain(rows[name],K9W_PLACEMENT[name],None,name in K9W_RECEIVES_ENTRY,'PARENT_ROWS_INVALID')
    # the source root lies on the filesystem of days/ (decision 6): the device of both signed leaves is one
    need(rows['source_root']['rows'][-1]['device']==rows['days']['rows'][-1]['device'],'SOURCE_ROOT_NOT_ON_THE_FILESYSTEM_OF_DAYS')
    if mode=='LAUNCH':
        point=k9w_instant_text(plan['run_not_after'],'RUN_NOT_AFTER_INVALID')
        if operation=='capture_launch':need(point==k9w_at(day,K9W_CAPTURE_RUN_NOT_AFTER),'RUN_NOT_AFTER_INVALID')
    else:need(plan['run_not_after'] is None,'RUN_NOT_AFTER_INVALID')
    if operation=='bind':k9w_bind(plan)
    else:need(plan['bind'] is None,'BIND_INVALID')
    # every argv this request can start, built once from the bytes with placeholders of the right grammar
    if step['row'] is not None:
        k9w_container_arguments(plan,'1'*64,'2'*64,K9W_MIN_TIMEOUT_SECONDS,{'manifest':'3'*64,'go':'4'*64,'previous':'5'*64})

def k9w_window_of(plan,now):
    """Pure, from the signed bytes and the clock, checked by perform before anything is observed (not by validate_plan:
    the core's conformance suite moves one plan's window across every day of the date class). The window lies in the eve
    or the morning of D (20:00Z of D-1 to 15:00Z of D); a before-open step ends by 13:30Z of D, an in-session step starts
    at 13:30Z of D or later; a LAUNCH's run_not_after is its window end plus its ceiling (capture: 14:03:00Z of D), on the
    UTC day of its window, and before the step's own limit (commit 03:50Z, publish 14:00Z of D); a cleanup starts after
    the capture's run_not_after; the time left to run_not_after leaves the container its minimum timeout."""
    day=plan['day'];step=K9W_STEPS[plan['k9_operation']]
    start,end=instant(plan['window']['not_before']),instant(plan['window']['expires_at'])
    low,high=k9w_at(k9w_day_shift(day,-1),'20:00:00'),k9w_at(day,'15:00:00')
    need(low<=start and end<=high,'WINDOW_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY')
    opening=k9w_at(day,'13:30:00')
    if step['window_class']=='BEFORE_OPEN':need(end<=opening,'WINDOW_NOT_OF_THE_STEP_CLASS')
    else:need(start>=opening,'WINDOW_NOT_OF_THE_STEP_CLASS')
    if plan['k9_operation']=='capture_cleanup':need(start>=k9w_at(day,K9W_CAPTURE_RUN_NOT_AFTER),'CLEANUP_BEFORE_CAPTURE_RUN_NOT_AFTER')
    if step['mode']!='LAUNCH':return None
    limit=instant(plan['run_not_after'])
    if plan['k9_operation']!='capture_launch':
        need(limit==k9w_after(end,step['ceiling_seconds']),'RUN_NOT_AFTER_NOT_WINDOW_END_PLUS_CEILING')
    need(limit.date()==start.date() and limit<=high,'RUN_NOT_AFTER_OUTSIDE_THE_UTC_DAY')
    if step['latest_run_not_after_utc_of_d'] is not None:need(limit<=k9w_at(day,step['latest_run_not_after_utc_of_d']),'RUN_NOT_AFTER_AFTER_THE_STEP_LIMIT')
    need((limit-now).total_seconds()>=K9W_MIN_TIMEOUT_SECONDS+K9W_LAUNCH_MARGIN_SECONDS+MAX_SECONDS,'RUN_NOT_AFTER_TOO_CLOSE')
    return limit

def k9w_host_paths(day):
    return {'tools':K9W_PLACEMENT['tools'],'day':K9W_PLACEMENT['days']+'/'+day,'day_receipts':K9W_PLACEMENT['days']+'/'+day+'/receipts',
            'source_root':K9W_SOURCE_ROOT,'emitter':K9W_PLACEMENT['emitter']}

def k9w_mounts(day,names):
    paths=k9w_host_paths(day)
    return [{'source':paths[K9W_MOUNTS[name]['host']],'target':K9W_MOUNTS[name]['target'],'read_only':K9W_MOUNTS[name]['read_only']} for name in names]

def k9w_step_plan_path(operation):return K9W_TARGETS['DAY']+'/plans/'+operation+'.json'

def k9w_command(plan,timeout,plan_sha256,packaged):
    """The command of the step: the content-addressed runner with its step plan, or the packaged risk CLI."""
    step=K9W_STEPS[plan['k9_operation']];values=plan['constants']
    head=['timeout','-s','KILL',str(timeout),'python']
    if step['command']=='RUNNER':
        return head+['-I',K9W_TARGETS['TOOLS']+'/k9_runner-'+values['runner_sha256']+'.py','--plan',k9w_step_plan_path(plan['k9_operation']),'--plan-sha256',plan_sha256]
    day_root=K9W_TARGETS['DAY']
    words=head+['-m','app.r2d2_v2_risk_host_executor',step['packaged_phase'],'--manifest',day_root+'/'+'/'.join(K9W_HOST_PLAN),'--manifest-sha256',packaged['manifest'],
                '--go',day_root+'/'+'/'.join(K9W_HOST_GO),'--go-sha256',packaged['go'],'--source-root','/app','--spool-root',day_root+'/risk/spool']
    if step['packaged_phase']!='preflight':words+=['--previous-receipt-sha256',packaged['previous']]
    return words

def k9w_container_arguments(plan,request_sha256,plan_sha256,timeout,packaged):
    """K9W's own argv builder (K9_INTERFACE_NOTE.md F5): what follows the fixed prefix of the create, attached or
    attached_short row. --name, the two labels, the network (create rows: the attached prefix fixes --network none), the
    env files of the step, the two fixed --env words, the mounts of the step (the core's mount_argument), the signed image
    ID, then the command. Every word in the core's run grammar; at most MAX_ARGUMENTS words."""
    step=K9W_STEPS[plan['k9_operation']];values=plan['constants'];day=plan['day']
    need(step['row'] in ('create','attached','attached_short'),'COMMAND_KIND')
    need(hexpin(request_sha256) and hexpin(plan_sha256) and integer(timeout,K9W_MIN_TIMEOUT_SECONDS if step['mode']=='LAUNCH' else 1,7200),'RUN_COMMAND_INVALID')
    need(text(values['image_id'],IMAGE_ID),'IMAGE_ID')
    name=k9w_container_name(day,plan['k9_operation']);need(text(name,'[a-z0-9][a-z0-9_.-]{0,62}'),'CONTAINER_TARGET')
    words=['--name',name,'--label',K9W_LABEL_ATTEMPT+'='+plan['attempt_key'],'--label',K9W_LABEL_REQUEST+'='+request_sha256]
    if step['row']=='create':
        network='none' if step['network']=='NONE' else values['networks'][step['network']]
        need(text(network,K9W_NETWORK_NAME),'NETWORK_INVALID');words+=['--network',network]
    else:need(step['network']=='NONE' and not step['env_files'],'NETWORK_INVALID')
    for name_of in step['env_files']:words+=['--env-file',K9W_PLACEMENT[K9W_ENV_FILES[name_of]]]
    for word in K9W_FIXED_ENV:words+=['--env',word]
    mounts=k9w_mounts(day,step['mounts'])
    need(len(mounts)<=MAX_MOUNTS and len({mount['target'] for mount in mounts})==len(mounts),'MOUNT_INVALID')
    for mount in mounts:words+=['--mount',mount_argument(mount)]
    command=k9w_command(plan,timeout,plan_sha256,packaged)
    need(0<len(command)<=2*MAX_RUN_WORDS and all(text(word,RUN_WORD) for word in command) and not command[0].startswith('-'),'RUN_COMMAND_INVALID')
    words+=[values['image_id']]+command
    need(len(words)<=MAX_ARGUMENTS and all(type(word) is str and word and len(word)<=8192 for word in words),'COMMAND_ARGUMENTS')
    return words

def k9w_chain_effects(item):return dict(chain_effects(item['rows']),open_root=item['open_root'])

def k9w_step_of(plan):
    """What the signers see of the step: the compiled row with its host paths, the argv with placeholders, the files."""
    operation=plan['k9_operation'];step=K9W_STEPS[operation];day=plan['day'];days=K9W_PLACEMENT['days']+'/'+day
    seen={'row':step,'container_name':k9w_container_name(day,operation) if step['row'] else None,
          'labels':{K9W_LABEL_ATTEMPT:plan['attempt_key'],K9W_LABEL_REQUEST:'<this request sha256>'} if step['row'] else None,
          'claim_file':K9W_PLACEMENT['claims']+'/'+plan['attempt_key']+'.claim',
          'step_plan_file':days+'/plans/'+operation+'.json' if step['row'] else None,
          'launch_record_file':days+'/launches/'+operation+'.json' if step['mode']=='LAUNCH' else None,
          'directories_created':[days]+[days+'/'+name for name in K9W_DAY_DIRECTORIES] if step['creates_day_directory'] else [],
          'removes_the_container_of':step['removes'],
          'removal_record_file':days+'/launches/'+step['removes']+'.json' if step['removes'] else None,
          'removal_container_name':k9w_container_name(day,step['removes']) if step['removes'] else None,
          'removal_argv':['rm','<the 64-hex ID of that record, exited, labels and image as written>'] if step['removes'] else None,
          'withdrawal_argv':['rm','<the 64-hex ID this run created, never started, when a mounted directory is no longer the one held>'] if step['row']=='create' else None,
          'mounts':k9w_mounts(day,step['mounts']),
          'env_files':[K9W_PLACEMENT[K9W_ENV_FILES[name]] for name in step['env_files']]}
    if step['row'] is not None:
        prefix=K9W_CREATE_PREFIX if step['row']=='create' else RUN_PREFIX
        timeout=K9W_MIN_TIMEOUT_SECONDS if step['mode']=='LAUNCH' else step['timeout_seconds']          # a LAUNCH's is computed at create
        seen['argv']=prefix+k9w_container_arguments(plan,'1'*64,'2'*64,timeout,{'manifest':'3'*64,'go':'4'*64,'previous':'5'*64})
        seen['argv_placeholders']={'1'*64:'<this request sha256>','2'*64:'<sha256 of the step plan>','3'*64:'<sha256 of risk/plan/HOST_PLAN.json>',
                                   '4'*64:'<sha256 of risk/plan/GO.json>','5'*64:'<sha256 of the previous packaged receipt>',
                                   str(timeout):('<min(run_not_after - now at create - %d s, ceiling + %d s)>'%(K9W_LAUNCH_MARGIN_SECONDS,K9W_CEILING_SLACK_SECONDS)
                                                 if step['mode']=='LAUNCH' else 'the fixed limit of the attached step')}
    return seen

def effects_of(plan):
    rows=plan['parent_rows'];step=K9W_STEPS.get(plan['k9_operation']) if type(plan['k9_operation']) is str else None
    launch=step is not None and step['mode']=='LAUNCH'
    return {'operation':OPERATION,'mode':plan['mode'],'epoch':plan['epoch'],'day':plan['day'],'k9_phase':plan['k9_phase'],
            'k9_operation':plan['k9_operation'],'slot':plan['slot'],'attempt_key':plan['attempt_key'],'run_not_after':plan['run_not_after'],
            'constants':plan['constants'],'parent_rows':None if rows is None else {name:k9w_chain_effects(rows[name]) for name in K9W_PARENT_CHAINS},
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],'bind':plan['bind'],
            'step':None if step is None else k9w_step_of(plan),
            'removal_only':'when an input of the step is not complete: the claim, the removal of the previous exited K9 container if the table names one, '
                           'then REFUSED_PREDECESSOR_NOT_COMPLETE (a subset of these effects)',
            'claims':1,'containers_created':0 if step is None or step['row'] is None else 1,'containers_removed_at_most':0 if step is None else (0 if step['removes'] is None else 1)+(1 if step['row']=='create' else 0),
            'files_created_at_most':0 if step is None else 1+(1 if step['row'] else 0)+(1 if launch else 0),
            'directories_created_at_most':0 if step is None or not step['creates_day_directory'] else 1+len(K9W_DAY_DIRECTORIES),'activation':False}

def success_of(plan):
    return K9W_SUCCESS.get(plan.get('mode'),COMPLETE_OUTCOME) if type(plan.get('mode')) is str else COMPLETE_OUTCOME


# ---------------------------------------------------------------- reads (the read program's helpers, written again here)
def k9w_child(host,parent_fd,name,gate):
    """A directory entry of a held directory, classified by lstat and opened without following a link: (fd, fstat)."""
    gate();named=host.lstat(name,parent_fd)
    need(not stat.S_ISLNK(named.st_mode),'SYMLINK_COMPONENT');need(stat.S_ISDIR(named.st_mode),'COMPONENT_NOT_DIRECTORY')
    gate();fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=parent_fd)
    try:
        info=host.fstat(fd);need((info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'PATH_CHANGED');return fd,info
    except BaseException:
        host.close(fd);raise

def k9w_descend(host,base_fd,parts,gate):
    fd=None
    try:
        for part in parts:
            child,_=k9w_child(host,base_fd if fd is None else fd,part,gate)
            if fd is not None:host.close(fd)
            fd=child
        return fd
    except BaseException:
        if fd is not None:host.close(fd)
        raise

def k9w_read(host,base_fd,parts,gate,limit):
    """(bytes, fstat) of a regular file below a held directory; FileNotFoundError when a component or the file is absent."""
    fd=k9w_descend(host,base_fd,parts[:-1],gate)
    try:
        gate();named=host.lstat(parts[-1],base_fd if fd is None else fd)
        need(stat.S_ISREG(named.st_mode),'FILE_NOT_REGULAR')
        raw,info=read_regular(host,parts[-1],base_fd if fd is None else fd,gate,limit)
        need((info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'FILE_CHANGED_DURING_READ');return raw,info
    finally:
        if fd is not None:host.close(fd)

def k9w_maybe(host,base_fd,parts,gate,limit=K9W_MAX_SMALL_FILE):
    try:return k9w_read(host,base_fd,parts,gate,limit)
    except FileNotFoundError:return None

def k9w_lexists(host,base_fd,parts,gate):
    """True when the last name exists (any type) below a held directory whose components are directories; False when
    any component or the name is absent. A component that is a link or not a directory is a refusal (never followed)."""
    try:fd=k9w_descend(host,base_fd,parts[:-1],gate)
    except FileNotFoundError:return False
    try:
        gate()
        try:host.lstat(parts[-1],base_fd if fd is None else fd)
        except FileNotFoundError:return False
        return True
    finally:
        if fd is not None:host.close(fd)

def k9w_private(info,mode):
    return (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(0,0,mode) and (not stat.S_ISREG(info.st_mode) or info.st_nlink==1)

def k9w_document(raw,code):
    try:value=strict(raw,K9W_MAX_PLAN_FILE)
    except Refused:raise Refused(code) from None
    need(type(value) is dict,code);return value

def k9w_secret_private(host,parent,name,gate):
    """lstat only: a regular file of root, 0600, one link. Never opened, never its size or a digest."""
    parent.verify(gate);gate()
    try:found=host.lstat(name,parent.fd)
    except FileNotFoundError:return False
    return stat.S_ISREG(found.st_mode) and k9w_private(found,K9W_PRIVATE_FILE_MODE)

def k9w_outputs_ok(outputs,aggregates):
    def keys_ok(value,limit):return type(value) is dict and len(value)<=limit and all(text(key,K9W_OUTPUT_KEY) for key in value)
    return (keys_ok(outputs,K9W_MAX_OUTPUTS) and all(text(value,HEX64) for value in outputs.values()) and keys_ok(aggregates,K9W_MAX_AGGREGATES)
            and all(type(value) is dict and set(value)=={'files','sha256'} and integer(value['files'],0,K9W_MAX_AGGREGATE_ENTRIES) and text(value['sha256'],HEX64)
                    for value in aggregates.values()))

def k9w_counts_ok(value,depth=0):
    return (type(value) is dict and len(value)<=K9W_MAX_COUNTS
            and all(text(key,K9W_COUNT_KEY) and (integer(item,0,K9W_MAX_COUNT) or (depth==0 and k9w_counts_ok(item,1))) for key,item in value.items()))

def k9w_times_ok(first,second,now):
    try:return instant(first)<=instant(second)<=now
    except Refused:return False

def k9w_launched_facts(commands,target):
    """One container by its 64-hex ID with the launched format; CommandFailed when the engine does not know it."""
    need(text(target,CONTAINER_ID),'CONTAINER_TARGET')
    row=decode(commands.output('launched',target))
    need(set(row)==K9W_LAUNCHED_KEYS and row['id']==target and text(row['name'],'/'+CONTAINER_NAME) and text(row['image_id'],IMAGE_ID)
         and type(row['state']) is str and row['state'] in CONTAINER_STATES and type(row['running']) is bool and type(row['oom_killed']) is bool
         and integer(row['exit_code'],-1,255) and all(type(row[key]) is str and len(row[key])<=64 for key in ('started_at','finished_at'))
         and all(row[key] in ('',None) or text(row[key],HEX64) for key in ('attempt_key','request_sha256')),'LAUNCHED_METADATA_INVALID')
    return row


class K9Step:
    """The checks of one run, all before the first effect. Each method returns facts for the receipt and raises Refused
    only for what makes the run a refusal."""
    def __init__(self,plan,host,gate,commands,bound,clock):
        self.plan,self.host,self.gate,self.commands,self.clock=plan,host,gate,commands,clock
        self.day=plan['day'];self.operation=plan['k9_operation'];self.step=K9W_STEPS[self.operation];self.values=plan['constants']
        self.request_sha256=bound['request_sha256'];self.held={};self.unmet=[];self.predecessors={};self.packaged={}
        self.removable=None;self.listing=None;self.day_exists=None

    def hold(self,key,fd,**options):
        try:self.held[key]=Pinned(self.host,fd,**options)
        except BaseException:
            self.host.close(fd);raise
        return self.held[key]

    def chains(self):
        rows=self.plan['parent_rows']
        for key,name in (('DAYS','days'),('CLAIMS','claims'),('TOOLS','tools'),('SECRETS','secrets'),('SOURCE_ROOT','source_root')):
            self.hold(key,walk_pinned(self.host,rows[name]['rows'],self.gate,[]),rows=rows[name]['rows'])
        need(self.held['SOURCE_ROOT'].identity[0]==self.held['DAYS'].identity[0],'SOURCE_ROOT_NOT_ON_THE_FILESYSTEM_OF_DAYS')
        return {'held':sorted(self.held),'source_root_on_the_filesystem_of_days':True}

    def claim_absent(self):
        claims=self.held['CLAIMS'];claims.verify(self.gate);self.gate()
        try:self.host.lstat(self.plan['attempt_key']+'.claim',claims.fd)
        except FileNotFoundError:return {'claim_absent':True}
        raise Refused('CLAIM_EXISTS')

    def day_directory(self):
        """days/<D>: held when it exists, root's and private; the three directories K9W writes in, likewise."""
        days=self.held['DAYS'];days.verify(self.gate)
        try:fd,info=k9w_child(self.host,days.fd,self.day,self.gate)
        except FileNotFoundError:
            self.day_exists=False;return {'day_directory':'ABSENT'}
        day=self.hold('DAY',fd,parent=days,name=self.day);self.day_exists=True
        need(k9w_private(info,K9W_PRIVATE_DIRECTORY_MODE) and info.st_dev==days.identity[0],'DAY_DIRECTORY_NOT_PRIVATE')
        for name in K9W_DAY_DIRECTORIES:
            try:child,found=k9w_child(self.host,day.fd,name,self.gate)
            except FileNotFoundError:raise Refused('DAY_LAYOUT_INVALID') from None
            self.hold('DAY_'+name.upper(),child,parent=day,name=name)
            need(k9w_private(found,K9W_PRIVATE_DIRECTORY_MODE),'DAY_LAYOUT_INVALID')
        return {'day_directory':'PRESENT_PRIVATE'}

    def containers(self):
        """docker ps -a: the K9 containers the engine knows (names and states only in the receipt)."""
        self.listing=container_list(self.commands)
        mine=[row for row in self.listing if row['name'].startswith(K9W_CONTAINER_PREFIX)]
        return {'containers':len(self.listing),'k9_containers':sorted([row['name'],row['state']] for row in mine)}

    def previous(self):
        """The container this step removes (section 3.2 of the note): named by its launch record, inspected by ID."""
        removes=self.step['removes']
        if removes is None:return {'removes':None}
        name=k9w_container_name(self.day,removes);listed=[row for row in self.listing if row['name']==name]
        facts={'removes':removes,'name_listed':bool(listed)}
        if not self.day_exists:return dict(facts,record=False)
        day=self.held['DAY'];day.verify(self.gate)
        found=k9w_maybe(self.host,day.fd,['launches',removes+'.json'],self.gate)
        if found is None:return dict(facts,record=False)
        raw,info=found;record=k9w_document(raw,'PREVIOUS_LAUNCH_RECORD_INVALID')
        key=k9w_attempt_key(K9W_EPOCH,self.day,K9W_PHASE_OF[removes],removes)
        need(set(record)==K9W_RECORD_KEYS and record['schema']==K9W_RECORD_SCHEMA and record['epoch']==K9W_EPOCH and record['day']==self.day
             and record['operation']==removes and record['attempt_key']==key and record['container_name']==name and text(record['container_id'],CONTAINER_ID)
             and hexpin(record['request_sha256']) and hexpin(record['step_plan_sha256']) and k9w_private(info,K9W_PRIVATE_FILE_MODE),'PREVIOUS_LAUNCH_RECORD_INVALID')
        facts.update(record=True,record_sha256=sha(raw))
        ids=[row for row in self.listing if row['id']==record['container_id']]
        if not ids:return dict(facts,present=False)
        row=k9w_launched_facts(self.commands,record['container_id'])
        need(row['name']=='/'+name and row['image_id']==self.values['image_id'] and row['attempt_key']==key
             and row['request_sha256']==record['request_sha256'],'PREVIOUS_CONTAINER_NOT_AS_RECORDED')
        need(row['state']=='exited' and row['running'] is False,'UNCERTAIN_PREVIOUS_RUNNING')
        self.removable={'id':record['container_id'],'operation':removes,'exit_code':row['exit_code'],'oom_killed':row['oom_killed']}
        return dict(facts,present=True,state=row['state'],exit_code=row['exit_code'],oom_killed=row['oom_killed'],finished_at=row['finished_at'])

    def unmet_need(self,code):
        if code not in self.unmet:self.unmet.append(code)

    def runner_need(self,launch):
        """A runner step's files: its plan (hashed), its start marker, its one receipt COMPLETE, no FAILED; for a
        launch, its launch record with the same step plan hash; for the container this step removes, exit 0, not OOM."""
        day=self.held.get('DAY');facts={'kind':'RUNNER','complete':False}
        if day is None:return dict(facts,reason='DAY_DIRECTORY_ABSENT')
        day.verify(self.gate)
        phase=K9W_PHASE_OF[launch];key=k9w_attempt_key(K9W_EPOCH,self.day,phase,launch);now=self.clock()
        plan_file=k9w_maybe(self.host,day.fd,['plans',launch+'.json'],self.gate)
        if plan_file is None:return dict(facts,reason='STEP_PLAN_ABSENT')
        plan_sha=sha(plan_file[0])
        if K9W_STEPS[launch]['mode']=='LAUNCH':
            record=k9w_maybe(self.host,day.fd,['launches',launch+'.json'],self.gate)
            if record is None:return dict(facts,reason='LAUNCH_RECORD_ABSENT')
            body=k9w_document(record[0],'LAUNCH_RECORD_INVALID')
            if not (set(body)==K9W_RECORD_KEYS and body.get('attempt_key')==key and body.get('step_plan_sha256')==plan_sha and body.get('day')==self.day):
                return dict(facts,reason='LAUNCH_RECORD_NOT_OF_THIS_STEP')
        files={}
        for suffix in ('STARTED','RECEIPT','FAILED'):files[suffix]=k9w_maybe(self.host,day.fd,['receipts',launch+'.'+suffix+'.json'],self.gate)
        if files['FAILED'] is not None:return dict(facts,reason='STEP_FAILED')
        if files['STARTED'] is None or files['RECEIPT'] is None:return dict(facts,reason='STEP_RECEIPT_ABSENT')
        identity={'epoch':K9W_EPOCH,'day':self.day,'phase':phase,'operation':launch,'attempt_key':key,'step_plan_sha256':plan_sha}
        marker=k9w_document(files['STARTED'][0],'STEP_RECEIPT_INVALID');receipt=k9w_document(files['RECEIPT'][0],'STEP_RECEIPT_INVALID')
        marker_ok=(set(marker)==K9W_STARTED_KEYS and marker['schema']==K9W_STARTED_SCHEMA and all(marker[name]==value for name,value in identity.items())
                   and k9w_times_ok(marker['started_at'],marker['started_at'],now))
        receipt_ok=(set(receipt)==K9W_STEP_KEYS and receipt['schema']==K9W_STEP_SCHEMA and all(receipt[name]==value for name,value in identity.items())
                    and receipt['status']=='COMPLETE' and receipt['code'] is None and receipt['package_sha256']==K9W_PACKAGE_SHA256
                    and receipt['build_sha']==K9W_CODE_REVISION and k9w_times_ok(receipt['started_at'],receipt['completed_at'],now)
                    and k9w_outputs_ok(receipt['outputs'],receipt['aggregates']) and k9w_counts_ok(receipt['counts']))
        private=all(k9w_private(found[1],K9W_PRIVATE_FILE_MODE) for found in (files['STARTED'],files['RECEIPT']))
        if not (marker_ok and receipt_ok and private):return dict(facts,reason='STEP_RECEIPT_NOT_OF_THIS_STEP')
        removable=self.removable
        if removable is not None and removable['operation']==launch and (removable['exit_code']!=0 or removable['oom_killed']):
            return dict(facts,reason='EXIT_CODE_CONTRADICTS_THE_RECEIPT')
        return dict(facts,complete=True,reason=None,receipt_sha256=sha(files['RECEIPT'][0]),step_plan_sha256=plan_sha,outputs=receipt['outputs'])

    def packaged_plan(self):
        """The hashes of the packaged risk plan and GO, computed on the host."""
        if 'manifest' in self.packaged:return self.packaged
        day=self.held['DAY'];day.verify(self.gate)
        plan_raw=k9w_maybe(self.host,day.fd,list(K9W_HOST_PLAN),self.gate,K9W_MAX_PLAN_FILE);go_raw=k9w_maybe(self.host,day.fd,list(K9W_HOST_GO),self.gate,K9W_MAX_PLAN_FILE)
        if plan_raw is None or go_raw is None:return self.packaged
        self.packaged.update(manifest=sha(plan_raw[0]),go=sha(go_raw[0]),plan_document=k9w_document(plan_raw[0],'HOST_PLAN_INVALID'))
        return self.packaged

    def packaged_need(self,phase):
        """The packaged executor's receipt of a phase in spool/<HOST_PLAN sha256>: COMPLETE, bound to this plan and GO, D's namespace."""
        facts={'kind':'PACKAGED','complete':False}
        if self.held.get('DAY') is None:return dict(facts,reason='DAY_DIRECTORY_ABSENT')
        packaged=self.packaged_plan()
        if 'manifest' not in packaged:return dict(facts,reason='HOST_PLAN_ABSENT')
        day=self.held['DAY'];base=['risk','spool',packaged['manifest']];now=self.clock()
        files={suffix:k9w_maybe(self.host,day.fd,base+[phase+'.'+suffix+'.json'],self.gate,K9W_MAX_PLAN_FILE) for suffix in ('STARTED','RECEIPT','FAILED')}
        if files['FAILED'] is not None:return dict(facts,reason='STEP_FAILED')
        if files['STARTED'] is None or files['RECEIPT'] is None:return dict(facts,reason='STEP_RECEIPT_ABSENT')
        marker=k9w_document(files['STARTED'][0],'STEP_RECEIPT_INVALID');receipt=k9w_document(files['RECEIPT'][0],'STEP_RECEIPT_INVALID')
        bound={'phase':phase,'manifest_sha256':packaged['manifest'],'go_sha256':packaged['go']}
        marker_ok=set(marker)==K9W_PACKAGED_STARTED_KEYS and all(marker[name]==value for name,value in bound.items())
        receipt_ok=(set(receipt)==K9W_PACKAGED_RECEIPT_KEYS and receipt['schema']==K9W_PACKAGED_RECEIPT_SCHEMA and all(receipt[name]==value for name,value in bound.items())
                    and receipt['status']=='COMPLETE' and receipt['session_date']==self.day and receipt['namespace']==K9W_RISK_NAMESPACE+self.day
                    and receipt['operation_activation'] is False and receipt['certification_granted'] is False and type(receipt['outputs']) is dict
                    and k9w_times_ok(receipt['started_at'],receipt['completed_at'],now))
        if not (marker_ok and receipt_ok):return dict(facts,reason='STEP_RECEIPT_NOT_OF_THIS_STEP')
        removable=self.removable
        if removable is not None and removable['operation']==K9W_PACKAGED_LAUNCH[phase] and (removable['exit_code']!=0 or removable['oom_killed']):
            return dict(facts,reason='EXIT_CODE_CONTRADICTS_THE_RECEIPT')
        return dict(facts,complete=True,reason=None,receipt_sha256=sha(files['RECEIPT'][0]),manifest_sha256=packaged['manifest'],go_sha256=packaged['go'],
                    outputs=receipt['outputs'])

    def needs(self):
        """Everything the step needs on the host by fixed path. A need not met is collected, never raised: the run then
        does removal-only (or refuses when there is nothing to remove)."""
        step=self.step;facts={}
        if step['creates_day_directory']:
            if self.day_exists:self.unmet_need('DAY_DIRECTORY_EXISTS')
        elif not self.day_exists:self.unmet_need('DAY_DIRECTORY_ABSENT')
        for kind_of,name in step['needs']:
            found=self.runner_need(name) if kind_of=='RUNNER' else self.packaged_need(name)
            self.predecessors[name]=found
            facts[name]={key:found.get(key) for key in ('kind','complete','reason','receipt_sha256')}
            if not found['complete']:self.unmet_need('REFUSED_PREDECESSOR_NOT_COMPLETE')
        if self.unmet or self.step['mode']=='CLEANUP':return dict(facts,needs_not_met=list(self.unmet))
        day=self.held.get('DAY');source=self.held['SOURCE_ROOT']
        for item in step['destinations_absent']+step['destinations_present']:
            root,parts=item[0],[self.day if part=='<D>' else part for part in item[1:]]
            if root=='days':continue                                   # days/<D> itself: decided above
            base=day if root=='day' else source;base.verify(self.gate)
            exists=k9w_lexists(self.host,base.fd,parts,self.gate)
            if item in step['destinations_absent'] and exists:self.unmet_need('DESTINATION_EXISTS')
            if item in step['destinations_present'] and not exists:self.unmet_need('INPUT_DIRECTORY_ABSENT')
        if step['symbols_equal_publish_receipt']:
            outputs=self.predecessors['publish_launch'].get('outputs') or {}
            found=k9w_maybe(self.host,day.fd,['control','symbols.txt'],self.gate,K9W_MAX_SYMBOLS_FILE)
            if found is None or outputs.get('day/control/symbols.txt')!=sha(found[0]):self.unmet_need('SYMBOLS_NOT_AS_PUBLISHED')
        if self.operation=='preflight':
            outputs=self.predecessors['bind'].get('outputs') or {};packaged=self.packaged_plan()
            if ('manifest' not in packaged or outputs.get('day/risk/plan/HOST_PLAN.json')!=packaged['manifest']
                    or outputs.get('day/risk/plan/GO.json')!=packaged['go']):self.unmet_need('RISK_PLAN_NOT_AS_BOUND')
        if step['packaged_phase'] is not None:
            packaged=self.packaged_plan();now=self.clock()
            try:
                bounds=packaged['plan_document']['phase_windows'][step['packaged_phase']]
                inside_window=instant(bounds['not_before'])<=now<=instant(bounds['not_after'])
            except (KeyError,TypeError,Refused):inside_window=False
            if not inside_window:self.unmet_need('RISK_PHASE_WINDOW_NOT_OPEN')
            spool=['risk','spool',packaged.get('manifest','0'*64)]
            if step['packaged_phase']!='preflight' and any(k9w_lexists(self.host,day.fd,spool+[step['packaged_phase']+'.'+suffix+'.json'],self.gate)
                                                           for suffix in ('STARTED','RECEIPT','FAILED')):self.unmet_need('DESTINATION_EXISTS')
            if step['packaged_phase']=='preflight' and k9w_lexists(self.host,day.fd,spool,self.gate):self.unmet_need('DESTINATION_EXISTS')
        secrets=self.held['SECRETS']
        for name in step['env_files']:
            if not k9w_secret_private(self.host,secrets,K9W_PLACEMENT[K9W_ENV_FILES[name]].rsplit('/',1)[1],self.gate):self.unmet_need('ENV_FILE_NOT_PRIVATE')
        if step['emitter_password']:
            secrets.verify(self.gate)
            try:
                fd,info=k9w_child(self.host,secrets.fd,'emitter',self.gate);emitter=self.hold('EMITTER',fd,parent=secrets,name='emitter')
                if not (k9w_private(info,K9W_PRIVATE_DIRECTORY_MODE) and k9w_secret_private(self.host,emitter,'password',self.gate)):self.unmet_need('EMITTER_SECRET_NOT_PRIVATE')
            except FileNotFoundError:self.unmet_need('EMITTER_SECRET_NOT_PRIVATE')
        if step['command']=='RUNNER':
            tools=self.held['TOOLS'];tools.verify(self.gate);self.gate()
            try:found=self.host.lstat('k9_runner-'+self.values['runner_sha256']+'.py',tools.fd);ok=stat.S_ISREG(found.st_mode) and k9w_private(found,K9W_PRIVATE_FILE_MODE)
            except FileNotFoundError:ok=False
            if not ok:self.unmet_need('RUNNER_FILE_NOT_AS_REQUIRED')
        if 'DAY_RECEIPTS' in step['mounts'] and self.held.get('DAY_RECEIPTS') is None:self.unmet_need('DAY_LAYOUT_INVALID')
        days=self.held['DAYS'];days.verify(self.gate);available=free_bytes(self.host,days.fd)
        if available<K9W_DISK_FLOOR_BYTES:self.unmet_need('DISK_FREE_BELOW_FLOOR')
        return dict(facts,needs_not_met=list(self.unmet),days_bytes_available=available,floor_bytes=K9W_DISK_FLOOR_BYTES,hold=available<K9W_DISK_FLOOR_BYTES)

    def engine(self):
        """FULL mode only: the signed image is present with the revision label; no K9 container is active; the name of
        this step's container is free."""
        found=image_facts(self.commands,self.values['image_id'])
        need(found['id']==self.values['image_id'] and found['revision_label']==K9W_CODE_REVISION,'IMAGE_NOT_THE_SIGNED_ONE')
        need(not [row for row in self.listing if row['name'].startswith(K9W_CONTAINER_PREFIX) and row['state'] in ('running','restarting','paused','removing')],
             'ANOTHER_K9_CONTAINER_ACTIVE')
        need(not [row for row in self.listing if row['name']==k9w_container_name(self.day,self.operation)],'CONTAINER_NAME_IN_USE')
        # every bind source: held (its ancestors are the signed root-only chains, walked and held) and itself root's,
        # gid 0, not writable by group or other, not setgid; its device the one of days/ (no mount inside the tree)
        for name in self.step['mounts']:
            if self.step['creates_day_directory'] and K9W_MOUNT_HELD[name] in ('DAY','DAY_RECEIPTS'):continue     # created by this run: proved 0:0 0700 there
            held=self.held.get(K9W_MOUNT_HELD[name]);need(held is not None,'MOUNT_SOURCE_NOT_ROOT_CONTROLLED')
            device,_,uid,gid,mode=held.identity
            need(uid==0 and gid==0 and not mode&0o022 and not mode&stat.S_ISGID and device==self.held['DAYS'].identity[0],'MOUNT_SOURCE_NOT_ROOT_CONTROLLED')
        return {'mount_sources_root_controlled':True,'image_equal_signed':True,'revision_equal_signed':True,'no_active_k9_container':True,'own_name_free':True}

    def close(self):
        for key in sorted(self.held,reverse=True):
            try:self.held[key].close()
            except Exception:pass


K9W_STEP_PLAN_KEYS=frozenset(('schema','epoch','day','k9_phase','k9_operation','slot','attempt_key','request_sha256','go_sha256',
                              'run_not_after','constants','network_class','database','risk','step_row'))
K9W_STEP_PLAN_CONSTANTS=('package_sha256','code_revision','act_b_sha256','release_sha256','policy_sha256','runner_sha256','risk_source_pins_sha256',
                         'risk_limits','disk_floor_bytes')
# The emitter's non-secret connection names (K9_INTERFACE_NOTE.md 4.3; the runner's DB); the password is the file of the EMITTER mount.
K9W_EMITTER_DATABASE={'host':'db','port':5432,'dbname':'c3po','role':'c3po_v2_causal_emitter'}

def k9w_step_plan(plan,bound,checks,run_not_after):
    """The step plan K9_STEP_PLAN_V1 the runner reads by --plan and --plan-sha256: canonical bytes, exactly the keys of
    the runner's PLAN_KEYS (fable-k9runner-20261004, read 2026-10-04 21:2xZ; DESIGN.md section 5). The runner reads its
    predecessors' receipts itself by fixed path; this file carries the identity, the deadline, the signed constants, the
    network class, the emitter's connection names (commit, publish), the bind's signed risk values, and the compiled row."""
    step=checks.step;values=plan['constants'];operation=plan['k9_operation']
    row=dict(step,operation=operation,container_name=k9w_container_name(plan['day'],operation),step_table_sha256=K9W_STEP_TABLE_SHA256)
    body={'schema':K9W_PLAN_STEP_SCHEMA,'epoch':K9W_EPOCH,'day':plan['day'],'k9_phase':step['phase'],'k9_operation':operation,'slot':plan['slot'],
          'attempt_key':plan['attempt_key'],'request_sha256':bound['request_sha256'],'go_sha256':bound['go_sha256'],'run_not_after':run_not_after,
          'constants':{key:values[key] for key in K9W_STEP_PLAN_CONSTANTS},'network_class':step['network'],
          'database':dict(K9W_EMITTER_DATABASE) if step['emitter_password'] else None,
          'risk':dict(plan['bind']) if operation=='bind' else None,'step_row':row}
    return canonical(body)


def k9w_settle(state,result,settled):
    """Exactly one of done / fail / unknown for an effect() that returned (effect() settled the others itself)."""
    if not (result['started'] and result['returned']):return
    {'DONE':state.done,'FAIL':state.fail}.get(settled,state.unknown)()

def k9w_command_facts(result):
    return {'started':result['started'],'returned':result['returned'],'returncode':result['returncode'],'code':result['code']}


def _never_complete(receipt):
    receipt['expectations_met']=False
    if receipt.get('code') is None:receipt['code']='RECEIPT_REDUCED_FOR_SIZE'
def _drop_checks(receipt):
    _never_complete(receipt)
    for name in ('checks',):
        if type(receipt.get(name)) is dict:receipt[name]={key:'REDUCED' for key in receipt[name]}
def _drop_effects(receipt):
    _never_complete(receipt);receipt['effects']='REDUCED'
REDUCTIONS=[('CHECKS_REDUCED',_drop_checks),('EFFECTS_REDUCED',_drop_effects)]


def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    commands=Commands(host,gate);checks=K9Step(plan,host,gate,commands,bound,clock)            # pure: nothing is touched
    step=checks.step;operation=plan['k9_operation'];go16=bound['go_sha256'][:16]
    gate()                                                                                      # first gate call: before anything is observed
    state.started=True
    facts={};ledger={'directories':[],'files':[],'commands':{}};out={'container_id':None,'launch_record_sha256':None,'step_plan_sha256':None,
                                                                    'timeout_seconds':None,'removed':None,'removal_read_back':False,'receipt':None}
    def finish(status,outcome,code,reached,extra=None):
        if status==COMPLETE_STATUS and state.uncertain()!=0:
            status,outcome,code=PARTIAL_STATUS,PARTIAL_OUTCOME,'EFFECT_NOT_SETTLED'                 # never a success with an uncertain effect
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),k9_operation=operation,day=plan['day'],slot=plan['slot'],
            mode=plan['mode'],effects=effects_of(plan),clock=timing(begun,mark,clock,monotonic),commands_started=dict(commands.started),
            mutating_calls=state.counts(),phase_reached=reached,checks=facts,ledger=ledger,objects_left_by_this_run=objects_left(ledger['directories'],ledger['files']),
            expectations_met=status==COMPLETE_STATUS,**dict(out,**(extra or {})))))
    def observe(label,action):
        gate();facts[label]=action()
    removal_only=False
    try:
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')                     # first, before anything is looked at
            k9w_window_of(plan,clock())                                                 # pure: the window belongs to D
            host.umask(0o077)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            observe('chains',checks.chains)
            observe('claim',checks.claim_absent)
            observe('day',checks.day_directory)
            observe('containers',checks.containers)
            observe('previous',checks.previous)
            observe('needs',checks.needs)
            held=[code for code in checks.unmet if code in K9W_HOLD_CODES]
            if held:raise Refused(held[0])
            if checks.unmet or step['mode']=='CLEANUP':
                if checks.removable is None:
                    raise Refused('CLEANUP_NOTHING_TO_REMOVE' if step['mode']=='CLEANUP' and not checks.unmet else checks.unmet[0])
                removal_only=step['mode']!='CLEANUP'
                rows=('remove',)
            else:
                observe('engine',checks.engine)
                rows=(('remove',) if checks.removable is not None else ())+(('create','start') if step['row']=='create' else (step['row'],))
            budget=effects_budget(*rows)+K9W_FILES_ALLOWANCE_SECONDS
            facts['budget']={'rows':list(rows),'seconds_needed':budget}
            need(gate()>=budget,'BUDGET_INSUFFICIENT')
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,'PRECHECK')

        # ---------------------------------------------------------------- effects: from here on nothing refuses
        claim=canonical({'epoch':K9W_EPOCH,'day':plan['day'],'phase':step['phase'],'operation':operation,'slot':plan['slot'],'request_sha256':bound['request_sha256']})
        claims=checks.held['CLAIMS']
        row=create_file(0,'CLAIM',K9W_PLACEMENT['claims']+'/'+plan['attempt_key']+'.claim',claim,K9W_PRIVATE_FILE_MODE,claims,host,gate,state,go16)
        ledger['files'].append(row)
        if row['state']!='INSTALLED_DURABLE':
            if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,'CLAIM_EXISTS' if row['code']=='DESTINATION_APPEARED_AFTER_PRECHECK' else row['code'] or 'CLAIM_NOT_CREATED','CLAIM')
            return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,row['code'] or 'CLAIM_NOT_CREATED','CLAIM')
        stop=readback_file(row,claim,K9W_PRIVATE_FILE_MODE,claims,host,gate)
        if stop is not None:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,'CLAIM')

        removal=None
        if checks.removable is not None:
            removal=effect(state,commands,'remove',checks.removable['id'],capture=True);ledger['commands']['remove']=k9w_command_facts(removal)
            if not removal['started']:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,removal['code'] or 'REMOVE_NOT_STARTED','REMOVE')
            if not removal['returned']:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,removal['code'] or 'REMOVE_UNCERTAIN','REMOVE')
            if removal['returncode']!=0 or removal_only or step['mode']=='CLEANUP':
                # read back now: a failed removal stops the step; for removal-only and cleanup it is the last effect
                gone=k9w_removal_readback(state,removal,commands,checks,out)
                if gone is not True:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,'PREVIOUS_CONTAINER_NOT_REMOVED' if gone is False else 'REMOVAL_READBACK_UNAVAILABLE','REMOVE')
                if step['mode']=='CLEANUP':return finish(COMPLETE_STATUS,K9W_CLEANUP_OUTCOME,None,'REMOVED')
                if removal['returncode']!=0:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,'PREVIOUS_CONTAINER_REMOVAL_STATUS_NONZERO','REMOVE')
                if removal_only:return finish(PARTIAL_STATUS,K9W_REMOVAL_ONLY_OUTCOME,checks.unmet[0],'REMOVAL_ONLY',{'needs_not_met':list(checks.unmet)})

        # FULL mode: the day's directories (collect_launch), the step plan, the container
        day=checks.held.get('DAY')
        if step['creates_day_directory']:
            handles={}
            try:
                entry=create_directory('DAY',K9W_PLACEMENT['days']+'/'+plan['day'],K9W_PRIVATE_DIRECTORY_MODE,checks.held['DAYS'],host,gate,state,handles)
                ledger['directories'].append(entry)
                if 'DAY' in handles:checks.held['DAY']=handles.pop('DAY')
                if entry['state']!='CREATED_DURABLE':return k9w_stopped(finish,state,removal,commands,checks,out,entry['code'] or 'DIRECTORY_NOT_CREATED','DIRECTORIES')
                day=checks.held['DAY']
                for name in K9W_DAY_DIRECTORIES:
                    key='DAY_'+name.upper()
                    entry=create_directory(key,K9W_PLACEMENT['days']+'/'+plan['day']+'/'+name,K9W_PRIVATE_DIRECTORY_MODE,day,host,gate,state,handles)
                    ledger['directories'].append(entry)
                    if key in handles:checks.held[key]=handles.pop(key)
                    if entry['state']!='CREATED_DURABLE':return k9w_stopped(finish,state,removal,commands,checks,out,entry['code'] or 'DIRECTORY_NOT_CREATED','DIRECTORIES')
            finally:
                for handle in handles.values():
                    try:handle.close()
                    except Exception:pass
        run_not_after=plan['run_not_after'] if step['mode']=='LAUNCH' else k9w_after(instant(plan['window']['expires_at']),MAX_SECONDS).isoformat()
        content=k9w_step_plan(plan,bound,checks,run_not_after);plans=checks.held['DAY_PLANS']
        row=create_file(1,'STEP_PLAN',K9W_PLACEMENT['days']+'/'+plan['day']+'/plans/'+operation+'.json',content,K9W_PRIVATE_FILE_MODE,plans,host,gate,state,go16)
        ledger['files'].append(row)
        stop=row['code'] if row['state']!='INSTALLED_DURABLE' else readback_file(row,content,K9W_PRIVATE_FILE_MODE,plans,host,gate)
        if stop is None and step['creates_day_directory']:
            for entry in ledger['directories']:
                held=checks.held[entry['key']];stop=readback_directory(entry['path'],K9W_PRIVATE_DIRECTORY_MODE,held,host,gate,
                                                                       len(K9W_DAY_DIRECTORIES) if entry['key']=='DAY' else 1 if entry['key']=='DAY_PLANS' else 0)
                if stop is not None:break
        if stop is not None:return k9w_stopped(finish,state,removal,commands,checks,out,stop,'STEP_PLAN')
        plan_sha256=sha(content);out['step_plan_sha256']=plan_sha256
        packaged={'manifest':checks.packaged.get('manifest'),'go':checks.packaged.get('go'),
                  'previous':(checks.predecessors.get(step['needs'][0][1]) or {}).get('receipt_sha256') if step['needs'] else None}

        if step['mode']=='ATTACHED':
            middle=k9w_container_arguments(plan,bound['request_sha256'],plan_sha256,step['timeout_seconds'],packaged)
            moved=k9w_mounts_moved(checks)
            if moved:
                out['mount_sources_replaced']=moved
                return k9w_stopped(finish,state,removal,commands,checks,out,'MOUNT_SOURCE_REPLACED_BEFORE_START','ATTACHED')
            result=effect(state,commands,step['row'],*middle,capture=True);ledger['commands'][step['row']]=k9w_command_facts(result)
            if not result['started']:return k9w_stopped(finish,state,removal,commands,checks,out,result['code'] or 'ATTACHED_NOT_STARTED','ATTACHED')
            if not result['returned']:return k9w_stopped(finish,state,removal,commands,checks,out,result['code'] or 'ATTACHED_DID_NOT_RETURN','ATTACHED')
            verdict=k9w_attached_result(plan,checks,result['returncode'],plan_sha256,result['output'])
            moved=k9w_mounts_moved(checks)
            if moved:out['mount_sources_replaced_after_run']=moved;verdict['complete']=False;verdict['code']='MOUNT_SOURCE_REPLACED_AROUND_THE_RUN'

            out['receipt']=verdict
            k9w_settle(state,result,'FAIL' if verdict['engine_refused'] else 'DONE')
            k9w_removal_readback(state,removal,commands,checks,out);gone=k9w_removal_code(removal,out)
            if gone is not None:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,gone,'ATTACHED')
            if verdict['complete']:return finish(COMPLETE_STATUS,K9W_ATTACHED_OUTCOME,None,'ATTACHED')
            return finish(PARTIAL_STATUS,K9W_NOT_COMPLETE_OUTCOME,verdict['code'],'ATTACHED')

        # LAUNCH: create, start, the launch record, then the readbacks
        now=clock();timeout=int((instant(plan['run_not_after'])-now).total_seconds())-K9W_LAUNCH_MARGIN_SECONDS
        if operation!='capture_launch':timeout=min(timeout,step['ceiling_seconds']+K9W_CEILING_SLACK_SECONDS)      # capture: its fixed 14:03Z bounds it
        if timeout<K9W_MIN_TIMEOUT_SECONDS:return k9w_stopped(finish,state,removal,commands,checks,out,'RUN_NOT_AFTER_TOO_CLOSE','CREATE')
        out['timeout_seconds']=timeout
        middle=k9w_container_arguments(plan,bound['request_sha256'],plan_sha256,timeout,packaged)
        created_at=now.isoformat()
        created=effect(state,commands,'create',*middle,capture=True);ledger['commands']['create']=k9w_command_facts(created)
        identifier=None
        if created['started'] and created['returned'] and created['returncode']==0:
            raw=created['output']
            if type(raw) is bytes and raw.endswith(b'\n') and raw.count(b'\n')==1 and text(raw[:-1].decode('ascii','replace'),CONTAINER_ID):identifier=raw[:-1].decode('ascii')
        if identifier is None:
            if created['started'] and created['returned']:
                exists=k9w_name_listed(commands,k9w_container_name(plan['day'],operation))
                k9w_settle(state,created,'FAIL' if exists is False else 'UNKNOWN')
            return k9w_stopped(finish,state,removal,commands,checks,out,created['code'] or 'CREATE_FAILED','CREATE')
        out['container_id']=identifier
        # The engine resolves a bind source by path when the container starts, following links. Every bind source and
        # its ancestors are root's (decision 6), so only root can move one; as defence in depth every mounted directory
        # is still proved again from "/" right before start; a divergence removes the created (never started) container.
        moved=k9w_mounts_moved(checks)
        if moved:
            out['mount_sources_replaced']=moved
            withdrawn=effect(state,commands,'remove',identifier,capture=True);ledger['commands']['remove_created']=k9w_command_facts(withdrawn)
            gone=k9w_listed_absent(commands,identifier) if withdrawn['started'] and withdrawn['returned'] else None
            k9w_settle(state,created,'DONE');k9w_settle(state,withdrawn,'DONE' if gone is True else 'FAIL' if gone is False and withdrawn['returncode']!=0 else 'UNKNOWN')
            out['created_container_removed']=gone
            return k9w_stopped(finish,state,removal,commands,checks,out,'MOUNT_SOURCE_REPLACED_BEFORE_START','START')
        started_at=clock().isoformat()
        started=effect(state,commands,'start',identifier,capture=True);ledger['commands']['start']=k9w_command_facts(started)
        if not (started['started'] and started['returned'] and started['returncode']==0):
            seen=attempt(lambda:k9w_launched_facts(commands,identifier))
            k9w_settle(state,created,'DONE' if seen.get('id')==identifier else 'UNKNOWN')
            k9w_settle(state,started,'FAIL' if seen.get('state')=='created' else 'UNKNOWN')
            return k9w_stopped(finish,state,None,commands,checks,out,started['code'] or 'START_FAILED','START',removal)
        record=canonical({'schema':K9W_RECORD_SCHEMA,'epoch':K9W_EPOCH,'day':plan['day'],'operation':operation,'slot':plan['slot'],'attempt_key':plan['attempt_key'],
                          'request_sha256':bound['request_sha256'],'step_plan_sha256':plan_sha256,'container_id':identifier,
                          'container_name':k9w_container_name(plan['day'],operation),'created_at':created_at,'started_at':started_at,'timeout_seconds':timeout})
        launches=checks.held['DAY_LAUNCHES']
        row=create_file(2,'LAUNCH_RECORD',K9W_PLACEMENT['days']+'/'+plan['day']+'/launches/'+operation+'.json',record,K9W_PRIVATE_FILE_MODE,launches,host,gate,state,go16)
        ledger['files'].append(row)
        stop=row['code'] if row['state']!='INSTALLED_DURABLE' else readback_file(row,record,K9W_PRIVATE_FILE_MODE,launches,host,gate)
        if row['state']=='INSTALLED_DURABLE':out['launch_record_sha256']=sha(record)
        # readback of the container this run created and started: by ID, its name, image, labels and a started state
        seen=attempt(lambda:k9w_launched_facts(commands,identifier))
        expected=seen.get('id')==identifier and seen.get('name')=='/'+k9w_container_name(plan['day'],operation) and seen.get('image_id')==plan['constants']['image_id']
        labelled=expected and seen.get('attempt_key')==plan['attempt_key'] and seen.get('request_sha256')==bound['request_sha256']
        k9w_settle(state,created,'DONE' if labelled else 'UNKNOWN')
        k9w_settle(state,started,'DONE' if labelled and seen.get('state') in ('running','exited') else 'UNKNOWN')
        out['container_readback']={key:seen.get(key) for key in ('status','code','state','running','exit_code')} if 'status' in seen else {
            'as_built':labelled,'state':seen.get('state'),'running':seen.get('running'),'exit_code':seen.get('exit_code')}
        k9w_removal_readback(state,removal,commands,checks,out)
        moved=k9w_mounts_moved(checks)
        if moved:
            out['mount_sources_replaced_after_start']=moved
            return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,'MOUNT_SOURCE_REPLACED_AROUND_START','READBACK')
        if stop is not None:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,'LAUNCH_RECORD')
        if not (labelled and seen.get('state') in ('running','exited')):return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,'LAUNCHED_CONTAINER_NOT_AS_BUILT','READBACK')
        gone=k9w_removal_code(removal,out)
        if gone is not None:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,gone,'READBACK')
        return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,'LAUNCHED')
    finally:checks.close()


K9W_MOUNT_HELD={'TOOLS':'TOOLS','DAY':'DAY','DAY_READ_ONLY':'DAY','DAY_RECEIPTS':'DAY_RECEIPTS','SOURCE':'SOURCE_ROOT','EMITTER':'EMITTER'}
def k9w_mounts_moved(checks):
    """The mount names of the step whose directory is no longer the one held (walked again from "/" without following
    a link, identity compared): [] when every one is still in place."""
    moved=[]
    for name in checks.step['mounts']:
        held=checks.held.get(K9W_MOUNT_HELD[name])
        try:
            need(held is not None,'DIRECTORY_NOT_HELD');held.verify(checks.gate)
        except Exception:moved.append(name)
    return moved

def k9w_listed_absent(commands,identifier):
    """True when a complete listing no longer shows the ID, False when it does, None when the listing is unavailable."""
    try:rows=container_list(commands)
    except Exception:return None
    return not [row for row in rows if row['id']==identifier]

def k9w_name_listed(commands,name):
    try:rows=container_list(commands)
    except Exception:return None
    return bool([row for row in rows if row['name']==name])

def k9w_removal_readback(state,removal,commands,checks,out):
    """The readback of a removal that returned (once per run): a complete listing without the ID settles it as done; a
    listing that still shows it after a non-zero status proves nothing changed; anything else is uncertain. None when
    no removal returned."""
    if removal is None or not (removal['started'] and removal['returned']):return None
    if out['removal_read_back']:return out['removed']
    gone=k9w_listed_absent(commands,checks.removable['id']);out['removed']=gone;out['removal_read_back']=True
    k9w_settle(state,removal,'DONE' if gone is True else 'FAIL' if gone is False and removal['returncode']!=0 else 'UNKNOWN')
    return gone

def k9w_removal_code(removal,out):
    """None when no removal was made or it was read back as done; otherwise the code that stops the step."""
    if removal is None:return None
    if out['removed'] is True:return None
    return 'PREVIOUS_CONTAINER_NOT_REMOVED' if out['removed'] is False else 'REMOVAL_READBACK_UNAVAILABLE'

def k9w_stopped(finish,state,removal,commands,checks,out,code,reached,deferred=None):
    """A FULL-mode run that stops after its claim: settle a pending removal by reading it back, then PARTIAL."""
    k9w_removal_readback(state,removal if removal is not None else deferred,commands,checks,out)
    return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,code,reached)

def k9w_attached_result(plan,checks,returncode,plan_sha256,output=b''):
    """After an attached run returned: its receipt read back (the runner's in days/<D>/receipts, or the packaged one in
    the spool). engine_refused: docker's own status with no start marker (nothing ran in the container). The runner prints
    its terminal receipt's bytes as its one result line (its DESIGN.md section 6 item 3): for bind and stage the line
    must be the receipt file's bytes, or the step is not complete."""
    operation=plan['k9_operation'];step=checks.step;day=checks.held['DAY'];gate=checks.gate;host=checks.host;now=checks.clock()
    verdict={'returncode':returncode,'complete':False,'engine_refused':False,'code':None,'receipt_sha256':None}
    try:
        day.verify(gate)
        if step['command']=='PACKAGED':
            base=['risk','spool',checks.packaged['manifest']];phase=step['packaged_phase']
            files={suffix:k9w_maybe(host,day.fd,base+[phase+'.'+suffix+'.json'],gate,K9W_MAX_PLAN_FILE) for suffix in ('STARTED','RECEIPT','FAILED')}
            bound={'phase':phase,'manifest_sha256':checks.packaged['manifest'],'go_sha256':checks.packaged['go']}
            ok=False
            if files['RECEIPT'] is not None and files['FAILED'] is None and files['STARTED'] is not None:
                receipt=k9w_document(files['RECEIPT'][0],'STEP_RECEIPT_INVALID');marker=k9w_document(files['STARTED'][0],'STEP_RECEIPT_INVALID')
                ok=(set(marker)==K9W_PACKAGED_STARTED_KEYS and all(marker[key]==value for key,value in bound.items())
                    and set(receipt)==K9W_PACKAGED_RECEIPT_KEYS and receipt['schema']==K9W_PACKAGED_RECEIPT_SCHEMA and all(receipt[key]==value for key,value in bound.items())
                    and receipt['status']=='COMPLETE' and receipt['session_date']==plan['day'] and receipt['namespace']==K9W_RISK_NAMESPACE+plan['day']
                    and receipt['operation_activation'] is False and receipt['certification_granted'] is False
                    and k9w_times_ok(receipt['started_at'],receipt['completed_at'],now))
                verdict['receipt_sha256']=sha(files['RECEIPT'][0])
            elif files['FAILED'] is not None:
                failed=k9w_document(files['FAILED'][0],'STEP_RECEIPT_INVALID')
                verdict['code']=failed.get('code') if text(failed.get('code'),CODE) else 'PACKAGED_PHASE_FAILED'
        else:
            key=plan['attempt_key'];files={suffix:k9w_maybe(host,day.fd,['receipts',operation+'.'+suffix+'.json'],gate) for suffix in ('STARTED','RECEIPT','FAILED')}
            identity={'epoch':K9W_EPOCH,'day':plan['day'],'phase':step['phase'],'operation':operation,'attempt_key':key,'step_plan_sha256':plan_sha256}
            ok=False
            if files['RECEIPT'] is not None and files['FAILED'] is None and files['STARTED'] is not None:
                receipt=k9w_document(files['RECEIPT'][0],'STEP_RECEIPT_INVALID');marker=k9w_document(files['STARTED'][0],'STEP_RECEIPT_INVALID')
                ok=(set(receipt)==K9W_STEP_KEYS and receipt['schema']==K9W_STEP_SCHEMA and all(receipt[name]==value for name,value in identity.items())
                    and receipt['status']=='COMPLETE' and receipt['code'] is None and receipt['package_sha256']==K9W_PACKAGE_SHA256
                    and receipt['build_sha']==K9W_CODE_REVISION and k9w_times_ok(receipt['started_at'],receipt['completed_at'],now)
                    and k9w_outputs_ok(receipt['outputs'],receipt['aggregates']) and k9w_counts_ok(receipt['counts'])
                    and set(marker)==K9W_STARTED_KEYS and marker['schema']==K9W_STARTED_SCHEMA and all(marker[name]==value for name,value in identity.items())
                    and all(k9w_private(found[1],K9W_PRIVATE_FILE_MODE) for found in (files['STARTED'],files['RECEIPT'])))
                verdict['receipt_sha256']=sha(files['RECEIPT'][0])
                verdict['result_line_is_the_receipt']=type(output) is bytes and output==files['RECEIPT'][0]+b'\n'
                if ok and not verdict['result_line_is_the_receipt']:ok=False;verdict['code']='ATTACHED_RESULT_LINE_NOT_THE_RECEIPT'
                if ok and operation=='bind':ok=k9w_bind_outputs(plan,checks,receipt['outputs'])
                if ok and operation=='stage':ok=k9w_stage_outputs(plan,checks,receipt['outputs'])
            elif files['FAILED'] is not None:
                failed=k9w_document(files['FAILED'][0],'STEP_RECEIPT_INVALID')
                verdict['code']=failed.get('code') if text(failed.get('code'),CODE) else 'STEP_FAILED'
        verdict['engine_refused']=files['STARTED'] is None and files['RECEIPT'] is None and files['FAILED'] is None and returncode in RUN_ENGINE_STATUSES
        verdict['complete']=bool(ok) and returncode==0
        if not verdict['complete'] and verdict['code'] is None:
            verdict['code']=('ATTACHED_ENGINE_REFUSED' if verdict['engine_refused'] else 'EXIT_CODE_CONTRADICTS_THE_RECEIPT' if ok
                             else 'ATTACHED_RECEIPT_NOT_COMPLETE')
    except Exception as error:
        verdict['code']=code_of(error,'ATTACHED_RECEIPT_UNAVAILABLE')
    return verdict

def k9w_bind_outputs(plan,checks,outputs):
    """bind: the documents it wrote are where the executor reads them, the owner order is the signed bytes and the
    source pins are the signed constant (both hashed again on the host)."""
    day=checks.held['DAY'];names=('OWNER_ORDER.json','SOURCE_PINS.json','list.private.json','HOST_PLAN.json','GO.json')
    if not all(text(outputs.get('day/risk/plan/'+name),HEX64) for name in names):return False
    if outputs['day/risk/plan/OWNER_ORDER.json']!=plan['bind']['owner_order_sha256']:return False
    if outputs['day/risk/plan/SOURCE_PINS.json']!=plan['constants']['risk_source_pins_sha256']:return False
    for name in ('OWNER_ORDER.json','HOST_PLAN.json','GO.json'):
        found=k9w_maybe(checks.host,day.fd,['risk','plan',name],checks.gate,K9W_MAX_PLAN_FILE)
        if found is None or sha(found[0])!=outputs['day/risk/plan/'+name]:return False
    return k9w_lexists(checks.host,day.fd,['risk','spool'],checks.gate)

def k9w_stage_outputs(plan,checks,outputs):
    """stage: components/<D>/risk.json in the source root is the execute receipt's risk.json, hashed again."""
    key='source/components/'+plan['day']+'/risk.json';expected=(checks.predecessors.get('execute') or {}).get('outputs') or {}
    if outputs.get(key) is None or outputs.get(key)!=expected.get('risk_sha256'):return False
    source=checks.held['SOURCE_ROOT'];source.verify(checks.gate)
    found=k9w_maybe(checks.host,source.fd,['components',plan['day'],'risk.json'],checks.gate,K9W_MAX_PLAN_FILE)
    return found is not None and sha(found[0])==outputs[key]
