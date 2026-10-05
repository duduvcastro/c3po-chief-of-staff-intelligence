OPERATION='GO_WRITE_HOSTOPS02_K3_SECRET_ENV_01'
PHASE='WRITE_READER_SECRET_ENV_IN_MEMORY'
REQUEST_SCHEMA='WRITE_HOSTOPS02_K3_SECRET_ENV_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_K3_SECRET_ENV_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_K3_SECRET_ENV_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_K3_SECRET_ENV_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_K3_SECRET_ENV_PLAN_V1'
SOURCE_NAME='k3_secret_env.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False
# WRITE_EPOCH (2026-10-03 ... 10-10 UTC): row A7 may run on the Sunday or on any evening of the sessions (DESIGN.md 9).
DATE_CLASS='WRITE_EPOCH'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
# The directory /etc/c3po-reader was created by the provisioning of 2026-10-03 (KNOWN_COMPLETE); the rows of its chain
# and the ID of the running worker come from a read-only receipt of the same boot (PROPOSED: the epoch readback, K11).
PROVISION_OPERATION='GO_WRITE_SUPERVISOR_READER_PROVISION_01'
EPOCH_READBACK_OPERATION='GO_READONLY_HOSTOPS02_EPOCH_READBACK_01'
EVIDENCE_OPERATIONS=(PROVISION_OPERATION,EPOCH_READBACK_OPERATION)
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='READER_SECRET_ENV_PLACED_AND_READ_BACK'
PARTIAL_OUTCOME='PARTIAL_SEE_SECRET_ENV_STATE'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_STATE_UNKNOWN_SECRET_ENV_MAY_EXIST'
PLAN_KEYS=frozenset(('config_chain','worker_container_id','evidence_boot_id_sha256'))

# ---- the constants of this operation. A request cannot move any of them: they are bytes of the signed source.
# The reader's configuration directory (reader README, "Environment files"; HOC section 8): root:root 0700, created by
# the provisioning; launcher/ and pins.env may or may not exist when this runs (other operations create them), so the
# directory need not be empty; secret.env must be absent.
CONFIG_DIRECTORY='/etc/c3po-reader'
CONFIG_DIRECTORY_MODE=0o700
SECRET_ENV_NAME='secret.env'
SECRET_ENV_PATH=CONFIG_DIRECTORY+'/'+SECRET_ENV_NAME
SECRET_ENV_MODE=0o600
# What a leftover of a secret looks like by its name: a temporary of the core's file writer (.hostops-<go16>-<n>.partial)
# or any other name that holds "secret.env" (secret.env.tmp, .secret.env.partial, ...). Names never leave the run.
TEMPORARY_PREFIX='.hostops-'
MAX_CONFIG_ENTRIES=64
# The two other environment files of the reader's container (README, "Environment files" 2 and 3). The README: "the
# writers and the readbacks refuse a name that appears in more than one file". Not secret; read in memory when present.
OTHER_ENV_FILES=('activation.env','pins.env')
OTHER_ENV_FILE_LIMIT=65536
# The one entry: the database URL compose gives the worker (postgresql://c3po:<password>@db:5432/c3po).
SECRET_KEY='C3PO_DATABASE_URL'
SECRET_ENVIRONMENT_NAMES=(SECRET_KEY,)
SECRET_LINE_PREFIX=b'C3PO_DATABASE_URL='
# HOC 8 accepts 1 to 4096 bytes without NUL, CR or LF; the core's parse copies only printable ASCII without a quote or a
# backslash (anything else is None, never a refusal), and this source refuses a space as well: the docker CLI's
# --env-file reader takes the value verbatim, and a URL holds no space. A stricter refusal, nothing changed.
SECRET_VALUE_GRAMMAR=rb'[\x21\x23-\x5b\x5d-\x7e]{1,4096}'
WORKER_CONTAINER_NAME='c3po-r2d2-worker-1'
WORKER_NAME_PREFIX='c3po-r2d2-worker-'
WORKER_COMPOSE_PROJECT='c3po'
WORKER_COMPOSE_SERVICE='r2d2-worker'
# The two compose labels of one container, nothing else of it (only constructs that ran on the host: index, json).
LABELS_FORMAT=('{"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
               '"service":{{json (index .Config.Labels "com.docker.compose.service")}}}')
SECRET_CREATE_FLAGS=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC
READBACK_FLAGS=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK
# The longest line this source can write, plus one: every read of the readback asks for this many bytes, a constant, so
# no argument of a call depends on the length of the value.
READBACK_REQUEST=len(SECRET_LINE_PREFIX)+MAX_SECRET_VALUE_BYTES+2
WRITE_ALLOWANCE_SECONDS=15                # what must be left of the budget before the creation (the writes take milliseconds)
SECRET_ENV_STATES=('NOT_ATTEMPTED','NOT_CREATED','CREATE_UNCERTAIN','WITHDRAWN','WITHDRAWN_NOT_DURABLE','LEFT_UNVERIFIED','PLACED_VERIFIED')
# Every code a receipt of this source's run may carry (code, and code and withdrawal_code of the file row). The core's
# code_of() lets any text of the shape of a code through; here a code is a member of this list, and any other text is
# replaced by UNLISTED_CODE before the receipt is sealed.
RECEIPT_CODES=frozenset((
    # the precheck: the process, the executor, the boot, the configuration directory (the core's walk)
    'PROCESS_DUMPABLE_NOT_DISABLED','EXECUTOR_IDENTITY','NOATIME_UNAVAILABLE','BOOT_ID_INVALID','EVIDENCE_FROM_EARLIER_BOOT','PARENT_MISSING',
    'PARENT_UNREADABLE','PARENT_SYMLINK_COMPONENT','PARENT_NOT_DIRECTORY','PARENT_CHANGED_DURING_WALK','PARENT_IDENTITY_MISMATCH','PARENT_REPLACED',
    'SECRET_ENV_PRESENT','SECRET_ENV_LEFTOVER_PRESENT','ENTRY_LIMIT','SECRET_KEY_IN_ANOTHER_ENV_FILE','OTHER_ENV_FILE_UNREADABLE',
    # the worker and its environment (the core's docker helpers and runner)
    'WORKER_CONTAINER_MISMATCH','WORKER_NOT_THE_ONLY_ONE','WORKER_NOT_RUNNING','WORKER_NOT_THE_COMPOSE_SERVICE','WORKER_ENVIRONMENT_CHANGED_DURING_READ',
    'WORKER_CHANGED_DURING_READ','SECRET_ENTRY_ABSENT','SECRET_VALUE_SHAPE','SECRET_ENVIRONMENT_REPEATED','SECRET_ENVIRONMENT_NAMES',
    'CONTAINER_TARGET','CONTAINER_METADATA_INVALID','CONTAINER_LIST_INVALID','COMMAND_FAILED','COMMAND_KIND','COMMAND_ARGUMENTS','COMMAND_STDIN',
    'COMMAND_VARIABLES','COMMAND_NOT_STARTED','COMMAND_NOT_STARTED_BUDGET','COMMAND_SKIPPED_AFTER_TIMEOUT','COMMAND_TIMEOUT','COMMAND_OUTPUT_LIMIT',
    'BINARY_UNAVAILABLE_OR_UNSAFE','DOCUMENT_SIZE','DOCUMENT_TYPE','DUPLICATE_KEY','JSON_INVALID','NONFINITE_JSON',
    # the last refusals before the creation, and the clock at any point
    'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT','GO_EXPIRED','CLOCK_REVERSED','PRECHECK_OS_ERROR','PRECHECK_FAILED',
    # the creation, its readback and its withdrawal
    'SECRET_ENV_APPEARED_AFTER_PRECHECK','FILESYSTEM_READ_ONLY','FILESYSTEM_FULL','FILESYSTEM_ACCESS_DENIED','FILESYSTEM_ERROR','FSYNC_FAILED',
    'SECRET_ENV_CREATE_UNCERTAIN','SECRET_ENV_WRITE_INCOMPLETE','SECRET_ENV_METADATA_MISMATCH','SECRET_ENV_STAT_FAILED','READBACK_MISMATCH',
    'READBACK_UNAVAILABLE','SECRET_ENV_PLACEMENT_FAILED','SECRET_ENV_NOT_PLACED','SECRET_ENV_NAME_NOT_THIS_RUNS_FILE','SECRET_ENV_WITHDRAWAL_FAILED',
    'SECRET_ENV_WITHDRAWAL_UNCERTAIN','DIRECTORY_READBACK_MISMATCH'))
UNLISTED_CODE='UNLISTED_CODE'
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'container':command_row('docker',['container','inspect','--format',CONTAINER_FORMAT],'one container name or ID','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          'container_labels':command_row('docker',['container','inspect','--format',LABELS_FORMAT],'one container ID','QUICK','READ'),
          SECRET_ENVIRONMENT_ROW:command_row('docker',['container','inspect','--format',secret_environment_format(SECRET_ENVIRONMENT_NAMES)],
                                             SECRET_ENVIRONMENT_MIDDLE,'QUICK','READ')}
# The process itself, first of all (the token placement's D9, closed by its revision 3): before anything of the host is
# looked at, the core's NativeRead.not_dumpable() sets the dumpable attribute of this process to 0 and reads it back 0.
PROCESS_SCOPE={'dumpable':0,'how':'prctl(PR_SET_DUMPABLE, 0), then prctl(PR_GET_DUMPABLE) must answer 0 (the core\'s dumps_disabled)',
               'when':'first, before the executor, the boot, the directory, any container or any file is looked at',
               'core_dump':'none of this process, to a file or through a pipe to a crash collector: the kernel dumps no process that is not dumpable',
               'commands':'docker ps and docker container inspect are processes of their own (an exec makes them dumpable again); the '
                          'inspect that prints the entry holds the inspect object of the worker, which holds its whole environment, as '
                          'every docker container inspect of it does',
               'otherwise':'refused, nothing changed: PROCESS_DUMPABLE_NOT_DISABLED'}
SCOPE_STATEMENT=('First of all, before anything of the host is looked at, makes its own process non-dumpable (prctl PR_SET_DUMPABLE 0, read back '
                 '0 with PR_GET_DUMPABLE); otherwise it refuses with nothing changed. Copies in memory the one entry '+SECRET_KEY+' of the '
                 'environment of the running container '+WORKER_CONTAINER_NAME+' (compose project '+WORKER_COMPOSE_PROJECT+', service '
                 +WORKER_COMPOSE_SERVICE+', the only running container of that service name) whose ID the request signs, through one fixed docker '
                 'container inspect template that prints exactly that entry, read twice and compared (that entry only); the value 1 to 4096 '
                 'bytes of printable ASCII without a space, a quote or a backslash. Places it as exactly one line '+SECRET_KEY+'=<value> and '
                 'a newline in '+SECRET_ENV_PATH+', root:root 0600, one link, in the signed directory '+CONFIG_DIRECTORY+' (root:root 0700, '
                 'every component from "/" root-owned and not writable by group or other, no open root), where secret.env must be absent '
                 'and no name holding secret.env and no temporary of the core\'s file writer may be. One exclusive create relative to the '
                 'held directory, fsync of the file and of the directory, and a readback by descriptor of identity, owner, mode and links, '
                 'and of the bytes compared in memory with the line (booleans only). The file stays only when the run is complete: '
                 'after its creation, any failure (a failed call, a mismatch, an expiry of the GO, a clock reversal, a replaced directory) '
                 'removes the file this run created, through the held descriptor of its directory, while its name there still shows the '
                 'inode this run holds with one link, and only then; that removal is not stopped by the gate. On 2026-10-03 to 2026-10-10 UTC. '
                 'Nothing that exists is overwritten, renamed, chmodded, chowned or truncated, nothing is activated, and the receipt never '
                 'carries a value, a digest, a length or a size of the value, of the line or of the file.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,
       'specification':'HOC section 8 (hostops01/candidate/CONTRACT.txt, THE secret.env STEP); reader README, Environment files 1 and Operations 1',
       'config_directory':{'path':CONFIG_DIRECTORY,'uid':0,'gid':0,'mode_octal':'%04o'%CONFIG_DIRECTORY_MODE,
                           'expect':'present, signed rows from "/" (no open root, not setgid); other entries allowed (at most %d)'%MAX_CONFIG_ENTRIES,
                           'refused_names':['secret.env','any other name that holds secret.env','any name that begins with '+TEMPORARY_PREFIX],
                           'other_env_files':('activation.env and pins.env, when present: regular, read in memory (at most %d bytes), and no line of '
                                              'either may define '%OTHER_ENV_FILE_LIMIT)+SECRET_KEY+' (reader README: a name in more than one file is refused)'},
       'secret_env':{'path':SECRET_ENV_PATH,'expect':'ABSENT','type':'regular file','uid':0,'gid':0,'mode_octal':'%04o'%SECRET_ENV_MODE,'links':1,
                     'umask_octal':'0077','content':'exactly one line '+SECRET_KEY+'=<value> and a newline',
                     'value_from':'the entry '+SECRET_KEY+' of the environment of the running container '+WORKER_CONTAINER_NAME,
                     'value_grammar':SECRET_VALUE_GRAMMAR.decode('ascii'),
                     'creation':'one open O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC of the final name relative to the held descriptor of the directory',
                     'readback':'the name opened again O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_NOATIME by descriptor: the same inode, regular, uid 0, gid 0, mode 0600, one '
                                'link; its bytes compared in memory with the line written: exactly one line, the name, equal (booleans only)',
                     'withdrawal':'only after its own creation succeeded and a later step failed, only while the name shows the inode this run holds '
                                  'with one link, through the held descriptor of the directory (wherever the directory now is: the receipt says whether it was still '
                                  'at its signed path); after any failure that follows the creation, an expiry and a replaced directory included, '
                                  'and never stopped by the gate: the file stays only when the run is complete'},
       'worker':{'name':WORKER_CONTAINER_NAME,'compose_project':WORKER_COMPOSE_PROJECT,'compose_service':WORKER_COMPOSE_SERVICE,
                 'rule':'exactly one container named '+WORKER_CONTAINER_NAME+' with the signed ID, running; no other running container whose name '
                        'begins with '+WORKER_NAME_PREFIX+'; its two compose labels '+WORKER_COMPOSE_PROJECT+' and '+WORKER_COMPOSE_SERVICE+
                        '; listed again after the two reads: still the one container of the name, with the signed ID, running',
                 'id_note':'the activation (M3) recreates the worker: a request bound before it names an ID that no longer exists after it '
                           'and is refused (WORKER_CONTAINER_MISMATCH), nothing changed'},
       'exceptions_to_the_core':['rule 4 (nothing is removed but the temporary of this run once its identity is proved): this source writes '
                                 'the final name directly, with no temporary, and may remove that file, and only the file this run created, '
                                 'after any later failure of this run, an expiry of the GO and a replaced directory included, through the held '
                                 'descriptor of its directory, while the name there shows the inode this run holds with one link; that one '
                                 'removal (an unlink and an fsync of the directory) is made even after the gate refused',
                                 'rule 5 and 6 (no value of an environment reaches the run): the one fixed row container_secret_environment of '
                                 'the secrets family\'s revision of the core prints the one named entry; it stays in memory'],
       'process':PROCESS_SCOPE,
       'receipt_never':['a value','a digest of the value, of the line or of the file','a length of the value or of the line','the size of the file',
                        'a block count or a timestamp of the file'],
       'receipt_codes':sorted(RECEIPT_CODES),'receipt_code_otherwise':UNLISTED_CODE,
       'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'file_contents_read':[BOOT_ID_PATH,CONFIG_DIRECTORY+'/activation.env and '+CONFIG_DIRECTORY+'/pins.env when present (not secret, in memory)',
                             SECRET_ENV_PATH+' (the file this run created, in memory, compared with the line)'],
       'never':['overwrite','chmod','chown','rename','truncate','removal of anything but the file this run created','a temporary file',
                'a read of the deploy tree or of its .env','docker exec','docker run','compose','systemctl','a shell',
                'a network connection opened by this process','activation','a second attempt'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'write_allowance_seconds':WRITE_ALLOWANCE_SECONDS,'max_config_entries':MAX_CONFIG_ENTRIES,'readback_request_bytes':READBACK_REQUEST}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner,NativeFiles):
    """Everything this source can do to the host: the read primitives, the signed docker reads, the creating calls."""


def listed(code):return code if code is None or code in RECEIPT_CODES else UNLISTED_CODE

def zero(buffer):
    """Best effort: a bytearray that held the value is overwritten in place (DESIGN.md, section 7)."""
    if type(buffer) is bytearray:
        for index in range(len(buffer)):buffer[index]=0


def validate_plan(plan):
    rows=validate_chain(plan['config_chain'],CONFIG_DIRECTORY,receives_entry=True)     # no open root: every row root-owned, not group- or other-writable
    need((rows[-1]['uid'],rows[-1]['gid'],rows[-1]['mode'])==(0,0,CONFIG_DIRECTORY_MODE),'CONFIG_DIRECTORY_NOT_ROOT_0700')
    need(text(plan['worker_container_id'],CONTAINER_ID),'WORKER_CONTAINER_UNBOUND')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    return {'operation':OPERATION,
            'config_directory':dict(chain_effects(plan['config_chain']),required={'uid':0,'gid':0,'mode_octal':'0700','open_root':None,
                                                                                  'secret_env':'ABSENT','leftover_of_a_secret':'ABSENT'}),
            'creates':{'path':SECRET_ENV_PATH,'type':'regular file','uid':0,'gid':0,'mode_octal':'0600','links':1,
                       'content':'exactly one line '+SECRET_KEY+'=<value> and a newline','temporary':None},
            'value':{'name':SECRET_KEY,'from_container':WORKER_CONTAINER_NAME,'container_id':plan['worker_container_id'],
                     'compose_project':WORKER_COMPOSE_PROJECT,'compose_service':WORKER_COMPOSE_SERVICE,'reads':2},
            'process':{'dumpable':0,'when':'first, before anything of the host is looked at'},
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'pre_existing_objects_modified':False,'activation':False,'value_in_receipt':False,'size_or_digest_in_receipt':False}
def success_of(plan):return COMPLETE_OUTCOME


# ---------------------------------------------------------------- the directory: secret.env absent, no leftover
def directory_facts():
    return {'rows':[],'pinned':False,'entries_before':None,'secret_env_absent':None,'no_leftover_of_a_secret':None,'key_in_no_other_env_file':None}

def scan_directory(host,target,gate,facts,existing):
    """The names of the held directory, in memory: secret.env must be absent, and no other name may hold "secret.env" or
    begin with the temporary prefix of the core's file writer. Of a secret.env found: its type, owner, mode and links.
    Then the other environment files present must not define the key (other_env_files)."""
    count=0;present=False;leftover=False;others=[]
    for name in host.names(target.fd):
        count+=1
        need(count<=MAX_CONFIG_ENTRIES,'ENTRY_LIMIT')
        if name in OTHER_ENV_FILES:others.append(name)
        if name==SECRET_ENV_NAME:present=True
        elif name.startswith(TEMPORARY_PREFIX) or SECRET_ENV_NAME in name:leftover=True
    facts.update(entries_before=count,secret_env_absent=not present,no_leftover_of_a_secret=not leftover)
    if present:
        gate();info=host.lstat(SECRET_ENV_NAME,target.fd)
        existing.update(type=kind(info.st_mode),uid=info.st_uid,gid=info.st_gid,mode_octal='%04o'%stat.S_IMODE(info.st_mode),links=info.st_nlink)
    need(not present,'SECRET_ENV_PRESENT')
    need(not leftover,'SECRET_ENV_LEFTOVER_PRESENT')
    facts['key_in_no_other_env_file']=not any(other_env_defines_the_key(host,target,gate,name) for name in sorted(others))
    need(facts['key_in_no_other_env_file'],'SECRET_KEY_IN_ANOTHER_ENV_FILE')

def other_env_defines_the_key(host,target,gate,name):
    """Whether one of the other environment files defines the key, as the docker CLI's --env-file reader takes a line:
    the name is the text before the first "=", white space around it dropped (a line with the name alone copies the
    variable from the CLI's environment: a definition too; a comment line begins with "#" and so never has the key as
    its name; a name with white space inside or after it, which the CLI refuses, is taken as a definition: stricter)."""
    try:raw,_=read_regular(host,name,target.fd,gate,OTHER_ENV_FILE_LIMIT)
    except OSError:raise Refused('OTHER_ENV_FILE_UNREADABLE') from None          # absent since the listing, a link (O_NOFOLLOW), any error
    except Refused as error:
        if str(error) in ('FILE_NOT_REGULAR','FILE_TOO_LARGE','FILE_CHANGED_DURING_READ'):raise Refused('OTHER_ENV_FILE_UNREADABLE') from None
        raise
    for line in raw.split(b'\n'):
        if line.split(b'=',1)[0].strip()==SECRET_KEY.encode('ascii'):return True
    return False


# ---------------------------------------------------------------- the worker: the one entry, in memory
def worker_facts():
    return {'one_container_with_the_name':None,'id_equal_signed':None,'no_other_running_container_of_the_service_name':None,'running':None,
            'compose_project_and_service':None,'entry_present':None,'value_shape_met':None,'read_twice_equal':None,'same_container_after_the_reads':None}

def entry_values(commands,worker,shape):
    """One read of the one name through the fixed row: {name: bytearray or None}, empty when the name is absent. The
    core's refusals depend on the name and the shape alone. Two of them say something of the entry itself and are
    reported as the code shape: an output over the class limit (COMMAND_OUTPUT_LIMIT, 65536 bytes) and a line of the
    name that is not "NAME=VALUE" (SECRET_ENVIRONMENT_SHAPE: the entry without "="). shape is SECRET_VALUE_SHAPE for the
    first read (the same code as an empty or malformed value, so the receipt does not tell them apart), and
    WORKER_ENVIRONMENT_CHANGED_DURING_READ for the second, after a first read that was accepted. The one size class that
    remains is DESIGN.md section 8."""
    try:return container_secret_environment(commands,worker,SECRET_ENVIRONMENT_NAMES)
    except Refused as error:
        if str(error) in ('COMMAND_OUTPUT_LIMIT','SECRET_ENVIRONMENT_SHAPE'):raise Refused(shape) from None
        raise

def secret_line(commands,worker,facts,buffers):
    """The content of secret.env in a new bytearray: C3PO_DATABASE_URL=<value> and a newline. The worker is proved first
    (the list, the inspect, the labels); the entry is read twice through the fixed row and compared (presence and
    bytes); every buffer is registered for zeroing. The facts of the value are said only of an accepted read."""
    listed_rows=container_list(commands)
    named=[row for row in listed_rows if row['name']==WORKER_CONTAINER_NAME]
    facts['one_container_with_the_name']=len(named)==1
    facts['id_equal_signed']=len(named)==1 and named[0]['id']==worker
    need(facts['one_container_with_the_name'] and facts['id_equal_signed'],'WORKER_CONTAINER_MISMATCH')
    facts['no_other_running_container_of_the_service_name']=not [row for row in listed_rows if row['name'].startswith(WORKER_NAME_PREFIX)
                                                                 and row['id']!=worker and row['state']=='running']
    need(facts['no_other_running_container_of_the_service_name'],'WORKER_NOT_THE_ONLY_ONE')
    row=container_facts(commands,worker,expected_name=WORKER_CONTAINER_NAME)
    facts['running']=row['running'] is True and row['state']=='running' and named[0]['state']=='running'
    need(facts['running'],'WORKER_NOT_RUNNING')
    labels=decode(commands.output('container_labels',worker))
    need(type(labels) is dict and set(labels)=={'project','service'},'CONTAINER_METADATA_INVALID')
    facts['compose_project_and_service']=labels['project']==WORKER_COMPOSE_PROJECT and labels['service']==WORKER_COMPOSE_SERVICE
    need(facts['compose_project_and_service'],'WORKER_NOT_THE_COMPOSE_SERVICE')
    first=entry_values(commands,worker,'SECRET_VALUE_SHAPE');buffers.extend(first.values())
    need(SECRET_KEY in first,'SECRET_ENTRY_ABSENT')
    value=first[SECRET_KEY]
    need(value is not None and re.fullmatch(SECRET_VALUE_GRAMMAR,value) is not None,'SECRET_VALUE_SHAPE')
    facts.update(entry_present=True,value_shape_met=True)          # said only of an accepted value: a refusal says its code alone
    try:second=entry_values(commands,worker,'WORKER_ENVIRONMENT_CHANGED_DURING_READ')
    except Refused as error:
        if str(error)=='WORKER_ENVIRONMENT_CHANGED_DURING_READ':facts['read_twice_equal']=False
        raise
    buffers.extend(second.values())
    facts['read_twice_equal']=sorted(second)==sorted(first) and second[SECRET_KEY]==value
    need(facts['read_twice_equal'],'WORKER_ENVIRONMENT_CHANGED_DURING_READ')
    # The inspects name the worker by its 64-hex ID, which the docker CLI also matches against names: the listing after
    # the reads proves the signed ID is still the one container of that name, running.
    again=[row for row in container_list(commands) if row['name']==WORKER_CONTAINER_NAME]
    facts['same_container_after_the_reads']=len(again)==1 and again[0]['id']==worker and again[0]['state']=='running'
    need(facts['same_container_after_the_reads'],'WORKER_CHANGED_DURING_READ')
    # allocated once at its final length and filled in place: no growth leaves a freed copy of the value behind
    content=bytearray(len(SECRET_LINE_PREFIX)+len(value)+1);buffers.append(content)
    content[:len(SECRET_LINE_PREFIX)]=SECRET_LINE_PREFIX;content[len(SECRET_LINE_PREFIX):-1]=value;content[-1]=0x0a
    return content


# ---------------------------------------------------------------- the creation, its readback and its withdrawal
def secret_row():
    return {'path':SECRET_ENV_PATH,'state':'NOT_ATTEMPTED','code':None,'errno':None,'created':False,'all_bytes_written':None,'fsync_file':False,
            'fsync_directory':False,'device':None,'inode':None,'regular':None,'uid_0':None,'gid_0':None,'mode_0600':None,'single_link':None,
            'on_the_device_of_the_directory':None,'readback_same_inode':None,'readback_metadata_as_created':None,'readback_exactly_one_line':None,
            'readback_name_is_the_key':None,'readback_equal_to_the_worker_entry':None,
            'withdrawn':False,'withdrawal_code':None,'withdrawal_errno':None,'fsync_directory_after_withdrawal':False,'directory_at_the_signed_path':None}

METADATA_FACTS=('regular','uid_0','gid_0','mode_0600','single_link','on_the_device_of_the_directory')
READBACK_FACTS=('readback_same_inode','readback_metadata_as_created','readback_exactly_one_line','readback_name_is_the_key',
                'readback_equal_to_the_worker_entry')

def metadata_facts(info,row,directory):
    """Owner, mode, type and links of the created file through a descriptor; never its size."""
    row.update(regular=stat.S_ISREG(info.st_mode),uid_0=info.st_uid==0,gid_0=info.st_gid==0,mode_0600=stat.S_IMODE(info.st_mode)==SECRET_ENV_MODE,
               single_link=info.st_nlink==1,on_the_device_of_the_directory=info.st_dev==directory.identity[0])
    return all(row[key] for key in METADATA_FACTS)

def ungated():
    """The gate of the one call made after the gate may have refused: the withdrawal (DESIGN.md section 6)."""
    return None

def withdraw(fd,row,directory,host,state,code,error=None):
    """The one removal of this source: the file it created, after any later failure (an expiry, a clock reversal and a
    replaced directory included), through the held descriptor of its directory, while the name there still shows the
    inode of the descriptor held and that inode has one link. Anything else at the name is left in place. Not stopped by
    the gate: a file left half written or unverified would block every later attempt, and no removal exists. Whether the
    directory is still at its signed path is said, so the receipt names where the file was."""
    row['code']=code
    if error is not None:row['errno']=number(error)
    row['state']='LEFT_UNVERIFIED'
    try:
        directory.verify(ungated);row['directory_at_the_signed_path']=True
    except Refused:row['directory_at_the_signed_path']=False
    except Exception:pass
    try:
        named=host.lstat(SECRET_ENV_NAME,directory.fd);held=host.fstat(fd)
        if (named.st_dev,named.st_ino)!=(held.st_dev,held.st_ino) or named.st_nlink!=1:
            row['withdrawal_code']='SECRET_ENV_NAME_NOT_THIS_RUNS_FILE';return row
        mutate(state,ungated,lambda:host.unlink(SECRET_ENV_NAME,directory.fd))
    except OSError as error:
        row.update(withdrawal_code='SECRET_ENV_WITHDRAWAL_FAILED',withdrawal_errno=number(error));return row
    except Exception:
        if state.pending:state.unknown()
        row['withdrawal_code']='SECRET_ENV_WITHDRAWAL_UNCERTAIN';return row
    row.update(withdrawn=True,state='WITHDRAWN_NOT_DURABLE')
    try:host.fsync(directory.fd)
    except Exception as error:      # any failure here: the removal is done, its durability is not known (never a second withdrawal)
        row.update(withdrawal_code='FSYNC_FAILED',withdrawal_errno=number(error));return row
    row.update(state='WITHDRAWN',fsync_directory_after_withdrawal=True);return row

def readback(info,row,content,directory,host,gate,buffers):
    """The directory proved again from "/", the name opened again without following a link, and the new descriptor
    proved: the same inode, regular, root:root, 0600, one link. Only then are its bytes read, into a bytearray that is
    zeroed afterwards, each read asking for the same constant number of bytes, and compared in memory with the line
    written: exactly one line, the name, equal. Booleans only."""
    directory.verify(gate);gate()
    fd=host.open(SECRET_ENV_NAME,READBACK_FLAGS|host.noatime(),dir_fd=directory.fd)
    try:
        seen=host.fstat(fd)
        row['readback_same_inode']=(seen.st_dev,seen.st_ino)==(info.st_dev,info.st_ino)
        row['readback_metadata_as_created']=metadata_facts(seen,secret_row(),directory)
        if not (row['readback_same_inode'] and row['readback_metadata_as_created']):return False
        found=bytearray();buffers.append(found)
        while len(found)<READBACK_REQUEST:
            gate();block=host.read(fd,READBACK_REQUEST)
            if not block:break
            found.extend(block)
    finally:host.close(fd)
    row.update(readback_exactly_one_line=found.count(b'\n')==1 and found[-1:]==b'\n',readback_name_is_the_key=found[:len(SECRET_LINE_PREFIX)]==SECRET_LINE_PREFIX,
               readback_equal_to_the_worker_entry=found==content)
    return all(row[key] is True for key in READBACK_FACTS)

def place_secret(content,directory,host,gate,state,row,buffers,entries_before,readbacks):
    """One exclusive create of the final name, the writes from a view of the bytearray, fsync of the file, its metadata,
    fsync of the directory, the readback, the directory read back. Any failure after the create withdraws the file. Fills and returns the row; never raises for a failure of the host (an
    interrupt or the death of the process is not caught)."""
    fd=None;view=memoryview(content)
    try:
        try:fd=mutate(state,gate,lambda:host.create(SECRET_ENV_NAME,SECRET_CREATE_FLAGS,SECRET_ENV_MODE,directory.fd))
        except Refused as error:
            row['code']=code_of(error,'GO_EXPIRED');return row
        except OSError as error:
            row.update(state='NOT_CREATED',errno=number(error),
                       code='SECRET_ENV_APPEARED_AFTER_PRECHECK' if error.errno==errno.EEXIST else filesystem_code(error))
            return row
        except Exception:
            if state.pending:state.unknown()
            row.update(state='CREATE_UNCERTAIN',code='SECRET_ENV_CREATE_UNCERTAIN');return row
        row['created']=True;row['state']='LEFT_UNVERIFIED'
        try:
            written=0;row['all_bytes_written']=False
            try:
                while written<len(content):
                    size=mutate(state,gate,lambda:host.write(fd,view[written:]))
                    if type(size) is not int or size<=0:return withdraw(fd,row,directory,host,state,'SECRET_ENV_WRITE_INCOMPLETE')
                    written+=size
            except Refused as error:return withdraw(fd,row,directory,host,state,code_of(error,'GO_EXPIRED'))
            except OSError as error:return withdraw(fd,row,directory,host,state,filesystem_code(error),error)
            row['all_bytes_written']=written==len(content)
            try:host.fsync(fd);row['fsync_file']=True
            except OSError as error:return withdraw(fd,row,directory,host,state,'FSYNC_FAILED',error)
            try:
                info=host.fstat(fd);row.update(device=info.st_dev,inode=info.st_ino)
                if not metadata_facts(info,row,directory):return withdraw(fd,row,directory,host,state,'SECRET_ENV_METADATA_MISMATCH')
            except OSError as error:return withdraw(fd,row,directory,host,state,'SECRET_ENV_STAT_FAILED',error)
            try:host.fsync(directory.fd);row['fsync_directory']=True
            except OSError as error:return withdraw(fd,row,directory,host,state,'FSYNC_FAILED',error)
            try:
                if not readback(info,row,content,directory,host,gate,buffers):return withdraw(fd,row,directory,host,state,'READBACK_MISMATCH')
            except Refused as error:
                return withdraw(fd,row,directory,host,state,str(error) if str(error) in ('GO_EXPIRED','CLOCK_REVERSED','PARENT_REPLACED') else 'READBACK_MISMATCH')
            except OSError as error:return withdraw(fd,row,directory,host,state,'READBACK_UNAVAILABLE',error)
            # the directory read back from "/": the same identity, and exactly one entry more than before
            try:
                directory.verify(gate)
                readbacks['config_directory']=None if count_entries(host,directory.fd,gate,MAX_CONFIG_ENTRIES+1)==entries_before+1 else 'READBACK_MISMATCH'
            except Exception as error:
                readbacks['config_directory']=code_of(error,'READBACK_UNAVAILABLE')
            if readbacks['config_directory']:return withdraw(fd,row,directory,host,state,'DIRECTORY_READBACK_MISMATCH')
            row.update(state='PLACED_VERIFIED',code=None);return row
        except Exception:
            # neither an OS error nor a refusal (the call it interrupted is uncertain): the file of this run is withdrawn
            # by identity, as after any other failure
            if state.pending:state.unknown()
            return withdraw(fd,row,directory,host,state,'SECRET_ENV_PLACEMENT_FAILED')
    finally:
        view.release()
        if fd is not None:
            try:host.close(fd)
            except Exception:pass

def left_by_this_run(row):
    """1 when the file this run created is on the host, 0 when none is, None when the creation itself was uncertain."""
    if row['state']=='CREATE_UNCERTAIN':return None
    return 1 if row['state'] in ('PLACED_VERIFIED','LEFT_UNVERIFIED') else 0


def _reduce_rows(receipt):receipt['config_directory']=dict(receipt.get('config_directory') or {},rows=None)
REDUCTIONS=[('CONFIG_ROWS_REDUCED',_reduce_rows)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    worker=plan['worker_container_id']                        # pure: everything below reads the host
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    commands=Commands(host,gate)
    process={'dumpable_disabled':None}
    config=directory_facts();existing={}
    workers=worker_facts()
    precheck={'seconds_left_before_the_first_effect':None}
    pinned=[];buffers=[];row=secret_row();readbacks={'config_directory':None}
    def finish(status,outcome,code,extra):
        row.update(code=listed(row['code']),withdrawal_code=listed(row['withdrawal_code']))
        return seal(envelope(status,outcome,listed(code),dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),
            clock=timing(begun,mark,clock,monotonic),commands_started=dict(commands.started),mutating_calls=state.counts(),process=process,
            config_directory=config,existing_secret_env=existing or None,worker=workers,precheck=precheck,secret_env=row,
            directory_readback=listed(readbacks['config_directory']),objects_left_by_this_run=left_by_this_run(row),
            pre_existing_objects_modified=False,**extra)))
    try:
        # ---- everything is looked at before the creation
        try:
            # first, before anything of the host is looked at: this process made non-dumpable and proved so (PROCESS_SCOPE)
            process['dumpable_disabled']=False
            need(host.not_dumpable() is True,'PROCESS_DUMPABLE_NOT_DISABLED');process['dumpable_disabled']=True
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o077)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            target=Pinned(host,walk_pinned(host,plan['config_chain'],gate,config['rows']),rows=plan['config_chain']);pinned.append(target)
            config['pinned']=True
            scan_directory(host,target,gate,config,existing)
            content=secret_line(commands,worker,workers,buffers)
            # The last refusals that cost nothing on the host: the time the creation and readback may take, and the
            # directory proved again from "/" just before the creation.
            left=gate();precheck['seconds_left_before_the_first_effect']=int(left)
            need(left>=WRITE_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
            target.verify(gate)
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})
        # ---- from here on nothing refuses unless nothing has changed
        place_secret(content,target,host,gate,state,row,buffers,config['entries_before'],readbacks)
        stop=None if row['state']=='PLACED_VERIFIED' else (row['code'] or 'SECRET_ENV_NOT_PLACED')
        extra={'phase_reached':'EFFECTS','readback':'COMPLETE' if stop is None else None}
        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        # REFUSED only while no mutating call succeeded and none is uncertain; otherwise the run is a partial.
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)
    finally:
        for buffer in buffers:zero(buffer)
        for handle in pinned:
            try:handle.close()
            except Exception:pass
