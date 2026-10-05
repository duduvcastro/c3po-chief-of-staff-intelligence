OPERATION='GO_WRITE_HOSTOPS02_K3K9_SECRETS_01'
PHASE='WRITE_K9_SECRETS_ENVIRONMENT_FILES_AND_EMITTER_PASSWORD'
REQUEST_SCHEMA='WRITE_HOSTOPS02_K3K9_SECRETS_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_K3K9_SECRETS_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_K3K9_SECRETS_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_K3K9_SECRETS_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_K3K9_SECRETS_PLAN_V1'
SOURCE_NAME='k3k9_secrets.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False
DATE_CLASS='WRITE_SESSIONS'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
# The rows of the secrets directory come from the receipt of K4 mode E0, which creates it empty (PROPOSED name: the
# operation name the family's grammar gives to E0's stem HOSTOPS02_K4_E0); the ID of the running worker from the epoch
# readback (K11 POST, M3r) of the same boot.
# The identity rows of the files of September and of the directories that hold them come from the K9R TREE read, mode
# TREE, of the same boot (an lstat of exactly the five paths of SOURCE_PATHS: no content).
K4_E0_OPERATION='GO_WRITE_HOSTOPS02_K4_E0_01'
EPOCH_READBACK_OPERATION='GO_READONLY_HOSTOPS02_EPOCH_READBACK_01'
K9_TREE_OPERATION='GO_READONLY_HOSTOPS02_K9_PHASE_READ_01'
EVIDENCE_OPERATIONS=(K4_E0_OPERATION,EPOCH_READBACK_OPERATION,K9_TREE_OPERATION)
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='K9_SECRETS_PLACED_METADATA_VERIFIED'
PARTIAL_OUTCOME='PARTIAL_SEE_SECRET_FILE_STATES'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_STATE_UNKNOWN_SECRET_FILES_MAY_EXIST'
PLAN_KEYS=frozenset(('secrets_chain','data_volume_chain','source_rows','worker_container_id','evidence_boot_id_sha256'))

# ---- the constants of this operation. A request cannot move any of them: they are bytes of the signed source.
# PLACEMENT: decision N-8 of the co-auditor (W/codex-n8-placement-20261004.txt, sha256 d30f7f90...c2c53, by command):
# the K9 root under /var/lib/c3po, a chain controlled by root alone (no open root, no ancestor owned by uid 1000, none
# writable by group or other, no link), every new directory root:root 0700; /var/lib/c3po is created by K4 mode E0 with
# its own signed effect and is not presumed here: the request signs the rows of the whole chain. The one place where the
# K9 root is named; a change of placement is a change of this line, a new seal and a new review.
K9_ROOT='/var/lib/c3po/r2d2-v2-k9-20261005'                                     # N-8 (Codex), not under the data volume
# The open root of the two walks of the files of September ONLY (a read of a source, never the K9 tree): the data
# volume, owned by uid 1000. Its chain from "/" is signed (data_volume_chain: "/", "/mnt", "/mnt/day-d-data", from the
# receipt of K4 mode E0, which signs the same rows as the parent of the source root) and each walk must find those rows;
# the owner a September file may have besides root is the signed owner of the data volume. What crosses uid 1000 is
# DESIGN.md section 5.
SOURCE_OPEN_ROOT='/mnt/day-d-data'
K9_SECRETS_DIRECTORY=K9_ROOT+'/secrets'
K9_SECRETS_DIRECTORY_MODE=0o700
K9_SECRET_FILE_MODE=0o600
K9_EMITTER_NAME='emitter'
K9_EMITTER_DIRECTORY=K9_SECRETS_DIRECTORY+'/'+K9_EMITTER_NAME
PROVIDER_ENV_NAME='provider.env'
RISK_DB_ENV_NAME='risk-db.env'
EMITTER_PASSWORD_NAME='password'
TARGET_PATHS=(K9_SECRETS_DIRECTORY+'/'+PROVIDER_ENV_NAME,K9_SECRETS_DIRECTORY+'/'+RISK_DB_ENV_NAME,K9_EMITTER_DIRECTORY+'/'+EMITTER_PASSWORD_NAME)
SECRET_CREATE_FLAGS=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC
READBACK_FLAGS=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK
# The provider tokens, read from the environment of the running worker of the compose project (service r2d2-worker),
# whose ID the request signs. The settings of the release accept two names for each token (c3po/backend/app/config.py
# lines 107, 111 and 113 at dd4ec4bb: AliasChoices("C3PO_<X>", "<X>"), the first present winning), and the release's
# .env.example defines the unprefixed ones; the worker receives them from ../.env (compose.yml, env_file). Both names
# are read; every one present must hold the same bytes (the token placement's rule D11: no choosing which one wins), and
# provider.env holds the prefixed name, which the K9 containers' settings take first.
WORKER_CONTAINER_NAME='c3po-r2d2-worker-1'
PROVIDER_TOKEN_NAMES=(('C3PO_EODHD_API_TOKEN','EODHD_API_TOKEN'),('C3PO_FINNHUB_API_TOKEN','FINNHUB_API_TOKEN'),('C3PO_FMP_API_TOKEN','FMP_API_TOKEN'))
SECRET_ENVIRONMENT_NAMES=tuple(sorted(name for pair in PROVIDER_TOKEN_NAMES for name in pair))
# A token every reader takes as the same bytes (no quote, space, "#", "$" or backslash), one line, ASCII, 16 to 512
# characters (the grammar of the token placement, reviewed): the docker CLI reads an --env-file line literally.
PROVIDER_TOKEN_GRAMMAR=rb'[A-Za-z0-9._~+/=-]{16,512}'
# The database URL of the restricted reader role (E28: bound-package-rev3/operations/sources.py, role c3po_v2_risk_reader)
# and the password of the causal emitter role (E28: tonight_native.py, AUTHORITY_DIRECT_CHECK._read_private_password:
# exactly 64 bytes of [A-Za-z0-9_-], no newline). Both are copied from the files of September, by these fixed paths.
RISK_URL_DIRECTORY=SOURCE_OPEN_ROOT+'/.r2d2-v2-risk-secrets'
RISK_URL_NAME='risk-database-url'
RISK_URL_KEY='C3PO_R2D2_RISK_DATABASE_URL'
RISK_URL_MAX_FILE_BYTES=4096
RISK_URL_GRAMMAR=rb'postgresql://[\x21-\x7e]{1,4082}'     # with the scheme and one newline, at most RISK_URL_MAX_FILE_BYTES
RISK_URL_READER_PREFIX=b'postgresql://c3po_v2_risk_reader:'
EMITTER_SOURCE_DIRECTORY=SOURCE_OPEN_ROOT+'/.c3po-role-executor-20260908-r2/secret'
EMITTER_SOURCE_NAME='password'
EMITTER_PASSWORD_GRAMMAR=rb'[A-Za-z0-9_-]{64}'
# Everything the two walks cross below the data volume, in this order, each signed in source_rows with its identity,
# owner, mode and both change instants (never its size), and judged from the bytes: on the device of the data volume,
# owned by root or by the signed owner of the data volume, not writable by group or other (sticky or not).
SOURCE_PATHS=(RISK_URL_DIRECTORY,RISK_URL_DIRECTORY+'/'+RISK_URL_NAME,SOURCE_OPEN_ROOT+'/.c3po-role-executor-20260908-r2',EMITTER_SOURCE_DIRECTORY,
              EMITTER_SOURCE_DIRECTORY+'/'+EMITTER_SOURCE_NAME)
SOURCE_ROW_KEYS=('path','device','inode','uid','gid','mode','mtime_ns','ctime_ns')
EMITTER_PASSWORD_MAX_FILE_BYTES=64
WRITE_ALLOWANCE_SECONDS=15                # what must be left of the budget before the first creation (the writes take milliseconds)
SECRET_FILE_STATES=('NOT_ATTEMPTED','NOT_CREATED','CREATE_UNCERTAIN','WITHDRAWN','WITHDRAWN_NOT_DURABLE','LEFT_UNVERIFIED','PLACED_VERIFIED')
# Every code a receipt of this source's run may carry (code, and code and withdrawal_code of each file row). The core's
# code_of() lets any text of the shape of a code through; here a code is a member of this list, and any other text is
# replaced by UNLISTED_CODE before the receipt is sealed.
SOURCE_PREFIXES=('RISK_URL','EMITTER_PASSWORD')
SOURCE_SUFFIXES=('COMPONENT_ABSENT','COMPONENT_DIVERGES','FILE_ABSENT','FILE_NOT_REGULAR','FILE_LINKED','FILE_DIVERGES','FILE_CHANGED_DURING_READ','FORMAT')
RECEIPT_CODES=frozenset((
    # the precheck: the process, the executor, the boot, the secrets directory (the core's walk)
    'PROCESS_DUMPABLE_NOT_DISABLED','EXECUTOR_IDENTITY','NOATIME_UNAVAILABLE','BOOT_ID_INVALID','EVIDENCE_FROM_EARLIER_BOOT','PARENT_MISSING',
    'PARENT_UNREADABLE','PARENT_SYMLINK_COMPONENT','PARENT_NOT_DIRECTORY','PARENT_CHANGED_DURING_WALK','PARENT_IDENTITY_MISMATCH','PARENT_REPLACED',
    'SECRETS_DIRECTORY_NOT_EMPTY','ENTRY_LIMIT',
    # the worker and its environment (the core's docker helpers and runner)
    'WORKER_CONTAINER_MISMATCH','WORKER_NOT_RUNNING','WORKER_ENVIRONMENT_CHANGED_DURING_READ','PROVIDER_TOKEN_GRAMMAR','PROVIDER_TOKEN_ABSENT',
    'PROVIDER_TOKEN_DEFINITIONS_DISAGREE','SECRET_ENVIRONMENT_SHAPE','SECRET_ENVIRONMENT_REPEATED','SECRET_ENVIRONMENT_NAMES',
    'CONTAINER_TARGET','CONTAINER_METADATA_INVALID','CONTAINER_LIST_INVALID','COMMAND_FAILED','COMMAND_KIND','COMMAND_ARGUMENTS','COMMAND_STDIN',
    'COMMAND_VARIABLES','COMMAND_NOT_STARTED','COMMAND_NOT_STARTED_BUDGET','COMMAND_SKIPPED_AFTER_TIMEOUT','COMMAND_TIMEOUT','COMMAND_OUTPUT_LIMIT',
    'BINARY_UNAVAILABLE_OR_UNSAFE','DOCUMENT_SIZE','DOCUMENT_TYPE','DUPLICATE_KEY','JSON_INVALID','NONFINITE_JSON',
    # the database URL of the reader and the emitter password, as found in the files of September
    'RISK_DATABASE_URL_NOT_THE_RESTRICTED_READER','RISK_DATABASE_URL_WITH_PARAMETERS')+tuple(prefix+'_'+suffix for prefix in SOURCE_PREFIXES for suffix in SOURCE_SUFFIXES)+(
    # the last refusals before the first creation, and the clock at any point
    'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT','GO_EXPIRED','CLOCK_REVERSED','PRECHECK_OS_ERROR','PRECHECK_FAILED',
    # the directory emitter (the core's create_directory)
    'DIRECTORY_REQUEST_INVALID','DESTINATION_APPEARED_AFTER_PRECHECK','CREATED_OPEN_FAILED','CREATED_NAME_REPLACED','CREATED_METADATA_MISMATCH',
    'CREATED_STAT_FAILED','CREATED_LIST_FAILED','CREATED_NOT_EMPTY','FSYNC_FAILED','EMITTER_DIRECTORY_NOT_CREATED',
    # the creations, their readbacks and withdrawals
    'SECRET_FILE_APPEARED_AFTER_PRECHECK','FILESYSTEM_READ_ONLY','FILESYSTEM_FULL','FILESYSTEM_ACCESS_DENIED','FILESYSTEM_ERROR',
    'SECRET_FILE_CREATE_UNCERTAIN','SECRET_FILE_WRITE_INCOMPLETE','SECRET_FILE_METADATA_MISMATCH','SECRET_FILE_STAT_FAILED','READBACK_MISMATCH',
    'READBACK_UNAVAILABLE','SECRET_FILE_PLACEMENT_FAILED','SECRET_FILE_NOT_PLACED','SECRET_FILE_NAME_NOT_THIS_RUNS_FILE','SECRET_FILE_WITHDRAWAL_FAILED',
    'SECRET_FILE_WITHDRAWAL_UNCERTAIN','DIRECTORY_READBACK_MISMATCH'))
UNLISTED_CODE='UNLISTED_CODE'
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'container':command_row('docker',['container','inspect','--format',CONTAINER_FORMAT],'one container name or ID','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          SECRET_ENVIRONMENT_ROW:command_row('docker',['container','inspect','--format',secret_environment_format(SECRET_ENVIRONMENT_NAMES)],
                                             SECRET_ENVIRONMENT_MIDDLE,'QUICK','READ')}
# The process itself, first of all (the token placement's D9, closed by its revision 3): before anything of the host is
# looked at, the core's NativeRead.not_dumpable() sets the dumpable attribute of this process to 0 and reads it back 0.
PROCESS_SCOPE={'dumpable':0,'how':'prctl(PR_SET_DUMPABLE, 0), then prctl(PR_GET_DUMPABLE) must answer 0 (the core\'s dumps_disabled)',
               'when':'first, before the executor, the boot, any directory, any container or any file is looked at',
               'core_dump':'none of this process, to a file or through a pipe to a crash collector: the kernel dumps no process that is not dumpable',
               'commands':'docker ps and docker container inspect are processes of their own (an exec makes them dumpable again); they are '
                          'started before the files of September are read, and the inspect that prints the three tokens holds the inspect '
                          'object of the worker, which holds its whole environment, as every docker container inspect of it does',
               'otherwise':'refused, nothing changed: PROCESS_DUMPABLE_NOT_DISABLED'}
FILE_ROWS=('provider_env','risk_db_env','emitter_password')
SCOPE_STATEMENT=('First of all, before anything of the host is looked at, makes its own process non-dumpable (prctl PR_SET_DUMPABLE 0, read back '
                 '0 with PR_GET_DUMPABLE); otherwise it refuses with nothing changed. Copies in memory the three provider tokens '
                 'C3PO_EODHD_API_TOKEN, C3PO_FINNHUB_API_TOKEN and C3PO_FMP_API_TOKEN from the environment of the running container '
                 +WORKER_CONTAINER_NAME+' whose ID the request signs, each from its prefixed or its unprefixed name (every one present '
                 'byte-equal; one fixed docker container inspect template that prints exactly those six entries, read twice and compared), '
                 'the database URL of the restricted reader role from '+RISK_URL_DIRECTORY+'/'
                 +RISK_URL_NAME+' and the emitter password from '+EMITTER_SOURCE_DIRECTORY+'/'+EMITTER_SOURCE_NAME+' (every component '
                 'below the data volume and both files equal to signed identity rows before each is opened, read once, unchanged while '
                 'read, within a fixed grammar; the URL with no query or fragment), and places them in the signed, empty '
                 'directory '+K9_SECRETS_DIRECTORY+' (root:root 0700, the K9 root root:root 0700, every component from "/" root-owned and '
                 'not writable by group or other, no open root): provider.env with the three tokens, risk-db.env with '+RISK_URL_KEY+
                 ', and the directory emitter (root:root 0700) with password, the same 64 bytes. One mkdir and three exclusive creates '
                 'relative to held descriptors, every file root:root 0600 with one link, fsync of each file and directory, and a readback '
                 'by descriptor of identity, owner, mode and links; the content is never read back. If a step after a creation fails, the '
                 'file this run created is removed while its name still shows the inode this run holds, and only then. On 2026-10-05 to '
                 '2026-10-10 UTC. Nothing that exists is overwritten, renamed, chmodded, chowned or truncated, nothing is activated, and '
                 'the receipt never carries a value, a digest, a length or a size of a value, of a line or of a file.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,
       'placement':{'k9_root':K9_ROOT,'status':'decision N-8 of the co-auditor (codex-n8-placement-20261004.txt, sha256 d30f7f9048af4a39cf4fa7d9f49292ad387a2d41f33bad39816e83d3d1fc2c53)',
                    'k9_chain':'signed rows from "/", every row root-owned and not writable by group or other, no open root; the K9 root and secrets root:root 0700',
                    'source_open_root':SOURCE_OPEN_ROOT+' (the two walks of the files of September only)',
                    'secrets_directory':K9_SECRETS_DIRECTORY,'emitter_directory':K9_EMITTER_DIRECTORY,'files':list(TARGET_PATHS)},
       'secrets_directory':{'path':K9_SECRETS_DIRECTORY,'uid':0,'gid':0,'mode_octal':'%04o'%K9_SECRETS_DIRECTORY_MODE,
                            'expect':'present, signed rows from "/" (the K9 root root:root 0700 too, no open root), empty'},
       'emitter_directory':{'path':K9_EMITTER_DIRECTORY,'uid':0,'gid':0,'mode_octal':'0700','expect':'ABSENT','creation':'the core\'s create_directory'},
       'files':{'provider_env':{'path':TARGET_PATHS[0],'content':'one line NAME=VALUE per token, NAME the first of its pair, in this order, each ending in a newline',
                                'names':[list(pair) for pair in PROVIDER_TOKEN_NAMES],'from':'the environment of the running container '+WORKER_CONTAINER_NAME,
                                'rule':'for each token at least one of its two names present, every one present within the grammar and byte-equal',
                                'value_grammar':PROVIDER_TOKEN_GRAMMAR.decode('ascii')},
                'risk_db_env':{'path':TARGET_PATHS[1],'content':RISK_URL_KEY+'=VALUE and a newline','from':RISK_URL_DIRECTORY+'/'+RISK_URL_NAME,
                               'value_grammar':RISK_URL_GRAMMAR.decode('ascii'),'value_begins_with':RISK_URL_READER_PREFIX.decode('ascii'),
                               'file':'the value, then at most one newline'},
                'emitter_password':{'path':TARGET_PATHS[2],'content':'the 64 bytes of the source file, nothing added','from':EMITTER_SOURCE_DIRECTORY+'/'+EMITTER_SOURCE_NAME,
                                    'value_grammar':EMITTER_PASSWORD_GRAMMAR.decode('ascii')},
                'every_file':{'type':'regular file','uid':0,'gid':0,'mode_octal':'%04o'%K9_SECRET_FILE_MODE,'links':1,'umask_octal':'0077',
                              'creation':'one open O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC relative to the held descriptor of its directory',
                              'readback':'the name opened again O_RDONLY|O_NOFOLLOW by descriptor: the same inode, regular, uid 0, gid 0, mode 0600, one link; never the content',
                              'withdrawal':'only after its own creation succeeded and a later step failed, only while the name shows the inode this run holds '
                                           'with one link; never after the expiry of the GO or a replaced directory'}},
       'sources':{'paths':list(SOURCE_PATHS),'rows':'signed (source_rows, from the K9R TREE read of the same boot): device, inode, uid, gid, mode, '
                          'mtime_ns, ctime_ns, never the size; on the device of '+SOURCE_OPEN_ROOT+', owned by root or by its signed owner, '
                          'not writable by group or other',
                  'walk':'"/", "/mnt", '+SOURCE_OPEN_ROOT+' equal to data_volume_chain (a mount point), then each component below it '
                         'compared by lstat with its signed row before it is opened, without following a link, and again by descriptor',
                  'file':'regular, one link, its lstat equal to its signed row before it is opened, unchanged while read; whether group or '
                         'other may read it is reported, never refused'},
       'exceptions_to_the_core':['rule 4 (nothing is removed but the temporary of this run once its identity is proved): this source may remove '
                                 'the final name of one of its three files, and only the file this run created, after a later step of this run '
                                 'failed, while the name shows the inode this run holds with one link; never after the expiry of the GO, never '
                                 'after its directory was found replaced',
                                 'rule 5 and 6 (no value of an environment reaches the run): the one fixed row container_secret_environment of '
                                 'the secrets family\'s revision of the core prints the six named entries; they stay in memory'],
       'process':PROCESS_SCOPE,
       'receipt_never':['a value','a digest of a value, of a line or of a file','a length of a value or of a line','the size of a file','any byte of a source file'],
       'receipt_codes':sorted(RECEIPT_CODES),'receipt_code_otherwise':UNLISTED_CODE,
       'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'file_contents_read':[BOOT_ID_PATH,RISK_URL_DIRECTORY+'/'+RISK_URL_NAME+' (in memory)',EMITTER_SOURCE_DIRECTORY+'/'+EMITTER_SOURCE_NAME+' (in memory)'],
       'never':['overwrite','chmod','chown','rename','truncate','removal of anything but a file this run created','a read of the deploy tree or of its .env',
                'docker exec','docker run','compose','systemctl','a shell','a network connection opened by this process','activation','a second attempt'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'write_allowance_seconds':WRITE_ALLOWANCE_SECONDS,'risk_url_file_bytes':RISK_URL_MAX_FILE_BYTES,
                 'emitter_password_file_bytes':EMITTER_PASSWORD_MAX_FILE_BYTES}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner,NativeFiles):
    """Everything this source can do to the host: the read primitives, the signed docker reads, the creating calls."""


def listed(code):return code if code is None or code in RECEIPT_CODES else UNLISTED_CODE

def zero(buffer):
    """Best effort: a bytearray that held a value is overwritten in place (DESIGN.md, section 8)."""
    if type(buffer) is bytearray:
        for index in range(len(buffer)):buffer[index]=0


def validate_plan(plan):
    rows=validate_chain(plan['secrets_chain'],K9_SECRETS_DIRECTORY,receives_entry=True)      # no open root: every row root-owned, not group- or other-writable
    need(all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows),'CHAIN_ROW_NOT_ROOT_GROUP')
    need((rows[-2]['uid'],rows[-2]['gid'],rows[-2]['mode'])==(0,0,K9_SECRETS_DIRECTORY_MODE),'K9_ROOT_NOT_ROOT_0700')
    need((rows[-1]['uid'],rows[-1]['gid'],rows[-1]['mode'])==(0,0,K9_SECRETS_DIRECTORY_MODE),'SECRETS_DIRECTORY_NOT_ROOT_0700')
    volume=validate_chain(plan['data_volume_chain'],SOURCE_OPEN_ROOT,open_root=SOURCE_OPEN_ROOT)     # "/" and "/mnt" root-owned and closed
    need(mount_point_of(volume)==SOURCE_OPEN_ROOT,'DATA_VOLUME_NOT_A_MOUNT_POINT')
    sources=plan['source_rows']
    need(type(sources) is list and len(sources)==len(SOURCE_PATHS)
         and all(type(row) is dict and set(row)==set(SOURCE_ROW_KEYS) and row['path']==path and integer(row['device']) and integer(row['inode'],1)
                 and integer(row['uid']) and integer(row['gid']) and integer(row['mode'],0,0o7777) and integer(row['mtime_ns']) and integer(row['ctime_ns'])
                 for row,path in zip(sources,SOURCE_PATHS)),'SOURCE_ROWS_INVALID')
    need(all(row['device']==volume[-1]['device'] for row in sources),'SOURCE_ROWS_OFF_THE_DATA_VOLUME')
    need(all(not row['mode']&0o022 for row in sources),'SOURCE_ROWS_WRITABLE_BY_GROUP_OR_OTHER')
    need(all(row['uid'] in (0,volume[-1]['uid']) for row in sources),'SOURCE_ROWS_OWNER_UNEXPECTED')
    need(text(plan['worker_container_id'],CONTAINER_ID),'WORKER_CONTAINER_UNBOUND')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    return {'operation':OPERATION,'k9_root':K9_ROOT,'placement':'N-8',
            'secrets_directory':dict(chain_effects(plan['secrets_chain']),required={'uid':0,'gid':0,'mode_octal':'0700','entries':0,'k9_root':'root:root 0700','open_root':None}),
            'creates':{'directory':{'path':K9_EMITTER_DIRECTORY,'uid':0,'gid':0,'mode_octal':'0700'},
                       'files':[{'path':path,'uid':0,'gid':0,'mode_octal':'0600','links':1} for path in TARGET_PATHS]},
            'values':{'provider_env':{'names':[list(pair) for pair in PROVIDER_TOKEN_NAMES],'from_container':WORKER_CONTAINER_NAME,
                                      'container_id':plan['worker_container_id']},
                      'data_volume':dict(chain_effects(plan['data_volume_chain']),open_root_of='the two walks of the files of September only'),
                      'source_rows_sha256':sha(canonical(plan['source_rows'])),
                      'risk_db_env':{'name':RISK_URL_KEY,'from_file':RISK_URL_DIRECTORY+'/'+RISK_URL_NAME},
                      'emitter_password':{'from_file':EMITTER_SOURCE_DIRECTORY+'/'+EMITTER_SOURCE_NAME}},
            'process':{'dumpable':0,'when':'first, before anything of the host is looked at'},
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'pre_existing_objects_modified':False,'activation':False,'value_in_receipt':False,'size_or_digest_in_receipt':False}
def success_of(plan):return COMPLETE_OUTCOME


# ---------------------------------------------------------------- the worker: the three tokens, in memory
def worker_facts():
    return {'one_container_with_the_name':None,'id_equal_signed':None,'running':None,'names_present':None,'grammar_met':None,'read_twice_equal':None}

def token_values(commands,worker):
    """One read of the six names through the fixed row: {name: bytearray or None} of those present (None: a value the
    core's parse does not copy, empty, over 4096 bytes, with a quote, a backslash or a byte outside printable ASCII). The
    core's refusals depend on the names and the shape alone. One refusal depends on a size: an output over the class
    limit (65536 bytes for six entries) is COMMAND_OUTPUT_LIMIT, reported as PROVIDER_TOKEN_GRAMMAR, which it implies."""
    try:return container_secret_environment(commands,worker,SECRET_ENVIRONMENT_NAMES)
    except Refused as error:
        if str(error)=='COMMAND_OUTPUT_LIMIT':raise Refused('PROVIDER_TOKEN_GRAMMAR') from None
        raise

def provider_content(commands,worker,facts,buffers):
    """The content of provider.env in a new bytearray: one line C3PO_<X>=VALUE per token, in the order of
    PROVIDER_TOKEN_NAMES. For each token at least one of its two names is present, every value present meets the grammar
    and all are byte-equal. The six names are read twice through the fixed row and compared (presence and bytes); every
    buffer is registered for zeroing. The facts are said only of an accepted read, so a refusal says nothing of a
    value but its code."""
    listed_rows=[row for row in container_list(commands) if row['name']==WORKER_CONTAINER_NAME]
    facts['one_container_with_the_name']=len(listed_rows)==1
    facts['id_equal_signed']=len(listed_rows)==1 and listed_rows[0]['id']==worker
    need(facts['one_container_with_the_name'] and facts['id_equal_signed'],'WORKER_CONTAINER_MISMATCH')
    row=container_facts(commands,worker,expected_name=WORKER_CONTAINER_NAME)
    facts['running']=row['running'] is True and row['state']=='running' and listed_rows[0]['state']=='running'
    need(facts['running'],'WORKER_NOT_RUNNING')
    first=token_values(commands,worker);buffers.extend(first.values())
    # Each rule over every token before the next rule, so that the code is decided by the presence of names first, then
    # by the grammar, then by the equality: never by which value happens to come first, or by its length.
    need(all(any(name in first for name in pair) for pair in PROVIDER_TOKEN_NAMES),'PROVIDER_TOKEN_ABSENT')
    need(all(value is not None and re.fullmatch(PROVIDER_TOKEN_GRAMMAR,value) is not None for value in first.values()),'PROVIDER_TOKEN_GRAMMAR')
    chosen=[]
    for pair in PROVIDER_TOKEN_NAMES:
        present=[first[name] for name in pair if name in first]
        need(all(value==present[0] for value in present),'PROVIDER_TOKEN_DEFINITIONS_DISAGREE')
        chosen.append(present[0])
    second=token_values(commands,worker);buffers.extend(second.values())
    facts.update(names_present={name:name in first for name in SECRET_ENVIRONMENT_NAMES},grammar_met=True,
                 read_twice_equal=sorted(first)==sorted(second) and all(first[name]==second[name] for name in first))
    need(facts['read_twice_equal'],'WORKER_ENVIRONMENT_CHANGED_DURING_READ')
    content=bytearray();buffers.append(content)
    for (name,_),value in zip(PROVIDER_TOKEN_NAMES,chosen):
        content.extend(name.encode('ascii'));content.extend(b'=');content.extend(value);content.extend(b'\n')
    return content


# ---------------------------------------------------------------- the files of September: read once, in memory
def source_facts():
    """Booleans of one file of September. unchanged_during_read and grammar_met are said together, and only of a content
    that is accepted: a file over the bound and a file outside the grammar leave the same facts and the same code, so
    the receipt does not say which (that would be a bound on its size)."""
    return {'components_as_signed':None,'present':None,'regular':None,'single_link':None,'file_as_signed':None,
            'not_readable_by_group_or_other':None,'unchanged_during_read':None,'grammar_met':None}

def as_signed(info,row):
    """An lstat or fstat equal to a signed row on every member the row has (the data volume's rows have no instants).
    Compared in memory; never the size."""
    seen={'device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid,'gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode),
          'mtime_ns':info.st_mtime_ns,'ctime_ns':info.st_ctime_ns}
    return all(seen[key]==row[key] for key in seen if key in row)

def source_walk(host,prefix,rows,gate,facts):
    """"/" opened, then each component looked at with lstat and compared with its signed row BEFORE it is opened, then
    opened by the held descriptor without following a link and compared again through the new descriptor. Returns the
    descriptor of the last directory."""
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()
    gate();fd=host.open('/',flags)
    try:
        need(as_signed(host.fstat(fd),rows[0]),prefix+'_COMPONENT_DIVERGES')
        for row in rows[1:]:
            name=PurePosixPath(row['path']).name;gate()
            try:named=host.lstat(name,fd)
            except FileNotFoundError:raise Refused(prefix+'_COMPONENT_ABSENT') from None
            need(stat.S_ISDIR(named.st_mode) and as_signed(named,row),prefix+'_COMPONENT_DIVERGES')
            gate();child=host.open(name,flags,dir_fd=fd);host.close(fd);fd=child
            held=host.fstat(fd)
            need((held.st_dev,held.st_ino)==(named.st_dev,named.st_ino) and as_signed(held,row),prefix+'_COMPONENT_DIVERGES')
        facts['components_as_signed']=True
        return fd
    except BaseException:
        host.close(fd);raise

READ_CODES={'FILE_NOT_REGULAR':'FILE_DIVERGES','FILE_TOO_LARGE':'FORMAT','FILE_CHANGED_DURING_READ':'FILE_CHANGED_DURING_READ'}
def source_bytes(host,prefix,rows,limit,gate,facts):
    """The bytes of one file of September: the signed walk to its directory (the data volume's rows, then the rows of
    source_rows above it), the file's lstat equal to its signed row before it is opened, one read through the held
    descriptor, unchanged while read."""
    fd=source_walk(host,prefix,rows[:-1],gate,facts)
    try:
        name=PurePosixPath(rows[-1]['path']).name;gate()
        try:named=host.lstat(name,fd)
        except FileNotFoundError:raise Refused(prefix+'_FILE_ABSENT') from None
        facts['present']=True
        need(stat.S_ISREG(named.st_mode),prefix+'_FILE_NOT_REGULAR');facts['regular']=True
        need(named.st_nlink==1,prefix+'_FILE_LINKED');facts['single_link']=True
        need(as_signed(named,rows[-1]),prefix+'_FILE_DIVERGES');facts['file_as_signed']=True
        facts['not_readable_by_group_or_other']=not named.st_mode&0o044          # the exposure as found: said, never a refusal
        try:raw,info=read_regular(host,name,fd,gate,limit)
        except FileNotFoundError:raise Refused(prefix+'_FILE_CHANGED_DURING_READ') from None
        except Refused as error:
            code=str(error);raise Refused(prefix+'_'+READ_CODES[code] if code in READ_CODES else code) from None
        gate()
        try:after=host.lstat(name,fd)
        except FileNotFoundError:raise Refused(prefix+'_FILE_CHANGED_DURING_READ') from None
        need(stat_signature(info)==stat_signature(named)==stat_signature(after),prefix+'_FILE_CHANGED_DURING_READ')
        return raw
    finally:host.close(fd)

def risk_url_content(raw,facts,buffers):
    """C3PO_R2D2_RISK_DATABASE_URL=<the value>\\n in a new bytearray. The file holds the value and at most one newline."""
    view=memoryview(raw)
    try:
        value=view[:-1] if raw[-1:]==b'\n' else view
        need(re.fullmatch(RISK_URL_GRAMMAR,value) is not None,'RISK_URL_FORMAT')
        facts.update(unchanged_during_read=True,grammar_met=True)
        facts['userinfo_names_the_restricted_reader']=value[:len(RISK_URL_READER_PREFIX)]==RISK_URL_READER_PREFIX
        need(facts['userinfo_names_the_restricted_reader'],'RISK_DATABASE_URL_NOT_THE_RESTRICTED_READER')
        # libpq takes parameters from a query string (user=, service=, host=, options=, ...) over the userinfo: none at all
        facts['no_query_or_fragment']=re.search(rb'[?#]',value) is None                 # searched in the view: no copy
        need(facts['no_query_or_fragment'],'RISK_DATABASE_URL_WITH_PARAMETERS')
        content=bytearray();buffers.append(content)
        content.extend(RISK_URL_KEY.encode('ascii'));content.extend(b'=');content.extend(value);content.extend(b'\n')
        return content
    finally:view.release()

def emitter_password_content(raw,facts,buffers):
    """The 64 bytes of the source file in a new bytearray, nothing added."""
    need(re.fullmatch(EMITTER_PASSWORD_GRAMMAR,raw) is not None,'EMITTER_PASSWORD_FORMAT')
    facts.update(unchanged_during_read=True,grammar_met=True)
    content=bytearray(raw);buffers.append(content);return content


# ---------------------------------------------------------------- the creations, their readbacks and their withdrawals
def file_row(path):
    return {'path':path,'state':'NOT_ATTEMPTED','code':None,'errno':None,'created':False,'fsync_file':False,'fsync_directory':False,
            'device':None,'inode':None,'regular':None,'uid_0':None,'gid_0':None,'mode_0600':None,'single_link':None,
            'on_the_device_of_the_directory':None,'readback_same_inode':None,'readback_metadata_as_created':None,
            'withdrawn':False,'withdrawal_code':None,'withdrawal_errno':None,'fsync_directory_after_withdrawal':False}

def metadata_facts(info,row,directory):
    """Owner, mode, type and links of a created file through a descriptor; never its size."""
    row.update(regular=stat.S_ISREG(info.st_mode),uid_0=info.st_uid==0,gid_0=info.st_gid==0,mode_0600=stat.S_IMODE(info.st_mode)==K9_SECRET_FILE_MODE,
               single_link=info.st_nlink==1,on_the_device_of_the_directory=info.st_dev==directory.identity[0])
    return all(row[key] for key in ('regular','uid_0','gid_0','mode_0600','single_link','on_the_device_of_the_directory'))

def withdraw(name,fd,row,directory,host,gate,state,code,error=None):
    """The one removal of this source: the file it created, after a later step failed, while the name still shows the
    inode of the descriptor held and that inode has one link. Anything else at the name is left in place."""
    row['code']=code
    if error is not None:row['errno']=number(error)
    row['state']='LEFT_UNVERIFIED'
    try:
        named=host.lstat(name,directory.fd);held=host.fstat(fd)
        if (named.st_dev,named.st_ino)!=(held.st_dev,held.st_ino) or named.st_nlink!=1:
            row['withdrawal_code']='SECRET_FILE_NAME_NOT_THIS_RUNS_FILE';return row
        mutate(state,gate,lambda:host.unlink(name,directory.fd))
    except Refused as error:
        row['withdrawal_code']=code_of(error,'GO_EXPIRED');return row
    except OSError as error:
        row.update(withdrawal_code='SECRET_FILE_WITHDRAWAL_FAILED',withdrawal_errno=number(error));return row
    except Exception:
        if state.pending:state.unknown()
        row['withdrawal_code']='SECRET_FILE_WITHDRAWAL_UNCERTAIN';return row
    row.update(withdrawn=True,state='WITHDRAWN_NOT_DURABLE')
    try:host.fsync(directory.fd)
    except OSError as error:
        row.update(withdrawal_code='FSYNC_FAILED',withdrawal_errno=number(error));return row
    row.update(state='WITHDRAWN',fsync_directory_after_withdrawal=True);return row

def readback(name,info,row,directory,host,gate):
    """The directory proved again from "/", the name opened again without following a link, and the new descriptor
    proved: the same inode, regular, root:root, 0600, one link. The content is not read."""
    directory.verify(gate);gate()
    fd=host.open(name,READBACK_FLAGS|host.noatime(),dir_fd=directory.fd)
    try:seen=host.fstat(fd)
    finally:host.close(fd)
    row['readback_same_inode']=(seen.st_dev,seen.st_ino)==(info.st_dev,info.st_ino)
    probe_row=file_row(row['path']);row['readback_metadata_as_created']=metadata_facts(seen,probe_row,directory)
    return row['readback_same_inode'] and row['readback_metadata_as_created']

def place_file(name,content,directory,host,gate,state,row):
    """One exclusive create, the writes from a view of the bytearray, fsync of the file, its metadata, fsync of the
    directory, the readback by descriptor. Fills and returns the row; never raises for a failure of the host (an
    interrupt or the death of the process is not caught)."""
    fd=None;view=memoryview(content)
    try:
        try:fd=mutate(state,gate,lambda:host.create(name,SECRET_CREATE_FLAGS,K9_SECRET_FILE_MODE,directory.fd))
        except Refused as error:
            row['code']=code_of(error,'GO_EXPIRED');return row
        except OSError as error:
            row.update(state='NOT_CREATED',errno=number(error),
                       code='SECRET_FILE_APPEARED_AFTER_PRECHECK' if error.errno==errno.EEXIST else filesystem_code(error))
            return row
        except Exception:
            if state.pending:state.unknown()
            row.update(state='CREATE_UNCERTAIN',code='SECRET_FILE_CREATE_UNCERTAIN');return row
        row['created']=True;row['state']='LEFT_UNVERIFIED'
        try:
            written=0
            try:
                while written<len(content):
                    size=mutate(state,gate,lambda:host.write(fd,view[written:]))
                    if type(size) is not int or size<=0:return withdraw(name,fd,row,directory,host,gate,state,'SECRET_FILE_WRITE_INCOMPLETE')
                    written+=size
            except Refused as error:
                row['code']=code_of(error,'GO_EXPIRED');return row
            except OSError as error:return withdraw(name,fd,row,directory,host,gate,state,filesystem_code(error),error)
            try:host.fsync(fd);row['fsync_file']=True
            except OSError as error:return withdraw(name,fd,row,directory,host,gate,state,'FSYNC_FAILED',error)
            try:
                info=host.fstat(fd);row.update(device=info.st_dev,inode=info.st_ino)
                if not metadata_facts(info,row,directory):return withdraw(name,fd,row,directory,host,gate,state,'SECRET_FILE_METADATA_MISMATCH')
            except OSError as error:return withdraw(name,fd,row,directory,host,gate,state,'SECRET_FILE_STAT_FAILED',error)
            try:host.fsync(directory.fd);row['fsync_directory']=True
            except OSError as error:return withdraw(name,fd,row,directory,host,gate,state,'FSYNC_FAILED',error)
            try:
                if not readback(name,info,row,directory,host,gate):return withdraw(name,fd,row,directory,host,gate,state,'READBACK_MISMATCH')
            except Refused as error:
                if str(error) in ('GO_EXPIRED','CLOCK_REVERSED','PARENT_REPLACED'):
                    row['code']=str(error);return row
                return withdraw(name,fd,row,directory,host,gate,state,'READBACK_MISMATCH')
            except OSError as error:return withdraw(name,fd,row,directory,host,gate,state,'READBACK_UNAVAILABLE',error)
            row.update(state='PLACED_VERIFIED',code=None);return row
        except Exception:
            # neither an OS error nor a refusal (the call it interrupted is uncertain): the file of this run is withdrawn
            # by identity, as after any other failure
            if state.pending:state.unknown()
            return withdraw(name,fd,row,directory,host,gate,state,'SECRET_FILE_PLACEMENT_FAILED')
    finally:
        view.release()
        if fd is not None:
            try:host.close(fd)
            except Exception:pass

def left_by_this_run(directory_row,rows):
    """Objects this run created and left on the host: the directory emitter and the files placed or left; None when a
    creation itself was uncertain."""
    if directory_row['state']=='NOT_ATTEMPTED' and all(row['state']=='NOT_ATTEMPTED' for row in rows):return 0
    if any(row['state']=='CREATE_UNCERTAIN' for row in rows):return None
    created=0 if directory_row['state'] in ('NOT_ATTEMPTED','NOT_CREATED') else 1
    return created+sum(1 for row in rows if row['state'] in ('PLACED_VERIFIED','LEFT_UNVERIFIED'))


def _reduce_rows(receipt):receipt['secrets_directory']={'rows_reduced_for_size':len((receipt.get('secrets_directory') or {}).get('rows') or [])}
REDUCTIONS=[('SECRETS_ROWS_REDUCED_TO_COUNT',_reduce_rows)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    worker=plan['worker_container_id']                        # pure: everything below reads the host
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    commands=Commands(host,gate)
    process={'dumpable_disabled':None}
    secrets_rows=[];secrets={'rows':secrets_rows,'pinned':False,'empty':None}
    workers=worker_facts();url=dict(source_facts(),userinfo_names_the_restricted_reader=None,no_query_or_fragment=None);password=source_facts()
    precheck={'seconds_left_before_the_first_effect':None}
    pinned=[];handles={};buffers=[]
    directory=[{'key':'EMITTER','path':K9_EMITTER_DIRECTORY,'state':'NOT_ATTEMPTED','code':None,'errno':None,'observed':None,
                'fsync_directory':False,'fsync_parent':False}]
    rows=[file_row(path) for path in TARGET_PATHS];readbacks={'secrets_directory':None,'emitter_directory':None}
    def finish(status,outcome,code,extra):
        for row in rows:row.update(code=listed(row['code']),withdrawal_code=listed(row['withdrawal_code']))
        directory[0]['code']=listed(directory[0]['code'])
        return seal(envelope(status,outcome,listed(code),dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),
            clock=timing(begun,mark,clock,monotonic),commands_started=dict(commands.started),mutating_calls=state.counts(),process=process,
            secrets_directory=secrets,worker=workers,risk_url_source=url,emitter_password_source=password,precheck=precheck,
            emitter_directory=directory[0],files=dict(zip(FILE_ROWS,rows)),directory_readbacks={key:listed(value) for key,value in readbacks.items()},
            objects_left_by_this_run=left_by_this_run(directory[0],rows),pre_existing_objects_modified=False,**extra)))
    try:
        # ---- everything is looked at before the first creation
        try:
            # first, before anything of the host is looked at: this process made non-dumpable and proved so (PROCESS_SCOPE)
            process['dumpable_disabled']=False
            need(host.not_dumpable() is True,'PROCESS_DUMPABLE_NOT_DISABLED');process['dumpable_disabled']=True
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o077)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            target=Pinned(host,walk_pinned(host,plan['secrets_chain'],gate,secrets_rows),rows=plan['secrets_chain']);pinned.append(target)
            secrets['pinned']=True
            secrets['empty']=count_entries(host,target.fd,gate)==0
            need(secrets['empty'],'SECRETS_DIRECTORY_NOT_EMPTY')
            # the provider tokens first: the docker commands start before any file of September is in this process
            provider=provider_content(commands,worker,workers,buffers)
            volume,sources=plan['data_volume_chain'],plan['source_rows']
            risk=risk_url_content(source_bytes(host,'RISK_URL',volume+sources[0:2],RISK_URL_MAX_FILE_BYTES,gate,url),url,buffers)
            emitter=emitter_password_content(source_bytes(host,'EMITTER_PASSWORD',volume+sources[2:5],EMITTER_PASSWORD_MAX_FILE_BYTES,gate,password),password,buffers)
            # The last refusals that cost nothing on the host: the time the creations and readbacks may take, and the
            # secrets directory proved again from "/" just before the first creation.
            left=gate();precheck['seconds_left_before_the_first_effect']=int(left)
            need(left>=WRITE_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
            target.verify(gate)
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})
        # ---- from here on nothing refuses unless nothing has changed
        directory[0]=create_directory('EMITTER',K9_EMITTER_DIRECTORY,0o700,target,host,gate,state,handles)
        stop=None if directory[0]['state']=='CREATED_DURABLE' else (directory[0]['code'] or 'EMITTER_DIRECTORY_NOT_CREATED')
        if stop is None:
            for row,name,content,where in ((rows[0],PROVIDER_ENV_NAME,provider,target),(rows[1],RISK_DB_ENV_NAME,risk,target),
                                           (rows[2],EMITTER_PASSWORD_NAME,emitter,handles['EMITTER'])):
                place_file(name,content,where,host,gate,state,row)
                if row['state']!='PLACED_VERIFIED':
                    stop=row['code'] or 'SECRET_FILE_NOT_PLACED';break
        if stop is None:
            # both directories read back from "/": identity, owner, mode, and exactly the entries this run put in them
            readbacks['secrets_directory']=readback_directory(K9_SECRETS_DIRECTORY,K9_SECRETS_DIRECTORY_MODE,target,host,gate,3)
            readbacks['emitter_directory']=readback_directory(K9_EMITTER_DIRECTORY,0o700,handles['EMITTER'],host,gate,1)
            if readbacks['secrets_directory'] or readbacks['emitter_directory']:stop='DIRECTORY_READBACK_MISMATCH'
        extra={'phase_reached':'EFFECTS','readback':'COMPLETE' if stop is None else None}
        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        # REFUSED only while no mutating call succeeded and none is uncertain; otherwise the run is a partial.
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)
    finally:
        for buffer in buffers:zero(buffer)
        for handle in list(handles.values())+pinned:
            try:handle.close()
            except Exception:pass
