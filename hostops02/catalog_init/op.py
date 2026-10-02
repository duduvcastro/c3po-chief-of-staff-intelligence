import base64

OPERATION='GO_WRITE_HOSTOPS02_CATALOG_INIT_01'
PHASE='WRITE_BAR_JOURNAL_CATALOG_INITIALISATION_4B'
REQUEST_SCHEMA='WRITE_HOSTOPS02_CATALOG_INIT_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_CATALOG_INIT_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_CATALOG_INIT_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_CATALOG_INIT_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_CATALOG_INIT_PLAN_V1'
SOURCE_NAME='catalog_init.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False
DATE_CLASS='WRITE_WEEKEND'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
# The rows a request signs come from the precheck of the boot of the write (the chains from "/") and from the ledger
# of the provisioning that created the journal root and the docker CLI configuration directory.
PROVISION_OPERATION='GO_WRITE_SUPERVISOR_READER_PROVISION_01'
EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,PROVISION_OPERATION)
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='CATALOG_READY_VERIFIED'                        # mode REAL
REHEARSAL_COMPLETE_OUTCOME='REHEARSAL_CATALOG_READY_VERIFIED'    # mode REHEARSAL: never the receipt of operation 4b
PARTIAL_OUTCOME='PARTIAL_SEE_ROOT_VERDICT'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED_NO_CONTAINER_STARTED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_STATE_UNKNOWN_ROOT_NOT_TO_BE_USED_AGAIN'
PLAN_KEYS=frozenset(('mode','journal_chain','throwaway_name','reference_chain','container_journal_root','docker_config_chain',
                     'image_id','image_revision','epoch','script_sha256','evidence_boot_id_sha256'))
MODES=('REAL','REHEARSAL')
# The epoch string of mode REAL is this constant and nothing a request can change. It is the compiled constant of the
# release: c3po/backend/app/r2d2_v2_epoch_assembler.py line 9 at dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858.
EPOCH_COMPILED='R2D2-V2-SHADOW-2026-10-05'
EPOCH_SOURCE='c3po/backend/app/r2d2_v2_epoch_assembler.py:9 EPOCH at dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
REHEARSAL_EPOCH='R2D2-V2-DIAG-[A-Za-z0-9_-]{1,80}'              # the DIAG half of validate_epoch (r2d2_v2_store.py:39)
THROWAWAY_NAME='c3po-bar-rehearsal-[a-z0-9][a-z0-9-]{0,39}'
# The layout floor of the reviewed family (hostops01 parts/layout.py: SUP_CONFIG, SUP_STATE_PARENT, SUP_STATE and the
# chain VAR_LIB), carried here as constants. Which directory is a journal root, which one is the docker CLI
# configuration directory of the unit and where a rehearsal creates are decided by this code, not by signed rows alone.
UNIT_DOCKER_CONFIG='/etc/c3po-bar/docker-cli'
JOURNAL_PARENT='/var/lib/c3po-bar'               # placement A: a journal root is a leaf of the private parent of operation 2
STATE_ROOT='/var/lib/c3po-bar/supervisor'        # and never the state root of the supervisor
THROWAWAY_PARENT='/var/lib'                      # a throwaway is a sibling of the private parent, never inside it
THROWAWAY_CONFIG_SUFFIX='.docker-cli'            # what a rehearsal gives docker as DOCKER_CONFIG: <throwaway root>.docker-cli
# The script of the supervisor README, "Catalog initialisation": exactly the lines between its two markers
# (README.md lines 353 to 373 at dd4ec4bb), 1040 bytes. Carried here so that the bytes are part of the signed source.
CATALOG_SCRIPT_SHA256='715d7a660e7a2c4dd5c11287063726cc971156dd6fefc2365c431c9aee0f4bb7'
CATALOG_SCRIPT_BYTES=1040
CATALOG_SCRIPT_B64=(
    'aW1wb3J0IGpzb24sIG9zLCBzeXMKc3lzLnBhdGguaW5zZXJ0KDAsICcvYXBwJykKdHJ5OgogICAgZnJvbSBhcHAucjJkMl92Ml9tYXNzaXZlX3Nlc3Npb25z'
    'IGltcG9ydCBTZXNzaW9uSm91cm5hbFJvb3QKICAgIGZyb20gYXBwLnIyZDJfdjJfc3RvcmUgaW1wb3J0IHZhbGlkYXRlX2Vwb2NoCiAgICByb290LCBlcG9j'
    'aCA9IHN5cy5hcmd2WzE6XQogICAgdmFsaWRhdGVfZXBvY2goZXBvY2gpCiAgICBiZWZvcmUgPSBzb3J0ZWQob3MubGlzdGRpcihyb290KSkKICAgIGlmIGJl'
    'Zm9yZSBhbmQgJ2Vwb2NoLmpzb24nIG5vdCBpbiBiZWZvcmU6CiAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignQ0FUQUxPR19JTklUX1JPT1RfTk9UX0VNUFRZ'
    'JykKICAgIFNlc3Npb25Kb3VybmFsUm9vdChyb290LCBlcG9jaCwgY3JlYXRlPVRydWUpCiAgICBTZXNzaW9uSm91cm5hbFJvb3Qocm9vdCwgZXBvY2gpCiAg'
    'ICB3aXRoIG9wZW4ob3MucGF0aC5qb2luKHJvb3QsICdlcG9jaC5qc29uJyksICdyYicpIGFzIHN0cmVhbToKICAgICAgICBjYXRhbG9nID0ganNvbi5sb2Fk'
    'cyhzdHJlYW0ucmVhZCgpKQogICAgcmVjZWlwdCA9IHsnc3RhdHVzJzogJ0NBVEFMT0dfUkVBRFknLCAnY3JlYXRlZCc6IG5vdCBiZWZvcmUsICdlcG9jaCc6'
    'IGNhdGFsb2dbJ2Vwb2NoJ10sCiAgICAgICAgICAgICAgICdkZXZpY2UnOiBjYXRhbG9nWydkZXZpY2UnXSwgJ2lub2RlJzogY2F0YWxvZ1snaW5vZGUnXSwg'
    'J2VudHJpZXMnOiBzb3J0ZWQob3MubGlzdGRpcihyb290KSl9CmV4Y2VwdCBFeGNlcHRpb24gYXMgZXJyb3I6CiAgICBjb2RlID0gZXJyb3IuYXJnc1swXSBp'
    'ZiBsZW4oZXJyb3IuYXJncykgPT0gMSBhbmQgdHlwZShlcnJvci5hcmdzWzBdKSBpcyBzdHIgZWxzZSB0eXBlKGVycm9yKS5fX25hbWVfXwogICAgcHJpbnQo'
    'anNvbi5kdW1wcyh7J3N0YXR1cyc6ICdDQVRBTE9HX1JFRlVTRUQnLCAnY29kZSc6IGNvZGV9LCBzb3J0X2tleXM9VHJ1ZSkpCiAgICByYWlzZSBTeXN0ZW1F'
    'eGl0KDEpCnByaW50KGpzb24uZHVtcHMocmVjZWlwdCwgc29ydF9rZXlzPVRydWUpKQo=')
# What the script leaves in an empty root, as the application defines it: maintenance.lock first
# (r2d2_v2_massive_maintenance.py:26), then epoch.json in place (r2d2_v2_massive_sessions.py:58-75, 204-205), both
# 0600, one link, owned by the uid of the container (0). epoch.json is the canonical JSON of the four members below;
# the producer compares its bytes at every start (_immutable, :64) and the reader its content (_verify, :213-215).
CATALOG_FILES=('epoch.json','maintenance.lock')
CATALOG_SCHEMA='MASSIVE_SESSION_ROOT_V1'
CATALOG_FILE_MODE=0o600
MAX_CATALOG_ENTRIES=64
MAX_EPOCH_JSON_BYTES=4096
MAX_NEW_CONTAINER_ROWS=8
# README "Substitution grammar", placement A: the container journal root is exactly one new top-level directory, and
# never one the image or the runtime provides (the list is the README's floor).
CONTAINER_ROOT_FORBIDDEN=('app','bin','boot','dev','etc','home','lib','lib64','media','mnt','opt','proc','root','run','sbin','srv','sys','tmp','usr','var')
FILES_ALLOWANCE_SECONDS=2                 # mode REHEARSAL: the two directories this run creates before the container
# What the docker commands that ran before the container left in the directory they were given. A run that finds this
# cannot say that nothing changed: it is never a refusal.
CONFIG_CHANGED='DOCKER_CONFIG_DIRECTORY_NOT_EMPTY_AFTER_THE_READS'
CONFIG_UNKNOWN='DOCKER_CONFIG_DIRECTORY_NOT_READ_AFTER_THE_READS'
RUN_ROW='catalog_init'
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'the signed image ID','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          RUN_ROW:command_row('docker',RUN_PREFIX,'one read-write bind of the journal root at the signed container path, the signed image ID, '
                              'python -I -B -, the container path, the epoch string; the pinned script on standard input','RUN','EFFECT',stdin=True)}
SCOPE_STATEMENT=('Supervisor operation 4b, the catalog initialisation of the bar journal, as the supervisor README at dd4ec4bb describes it. '
                 'Starts one attached container of the signed image ID with the argv of that README word for word: removed on exit, never a '
                 'pull, an init process, uid 0, no network, read-only root filesystem, no capability, the journal root bound read-write at '
                 'the signed container path as its only mount, the docker CLI under an empty configuration directory, and the '
                 'script whose SHA-256 is 715d7a660e7a2c4dd5c11287063726cc971156dd6fefc2365c431c9aee0f4bb7 on standard input. The container '
                 'creates maintenance.lock and epoch.json in the journal root. Mode REAL acts on the journal root that operation 2 created, '
                 'a leaf of /var/lib/c3po-bar that is not the state root, with the docker CLI under /etc/c3po-bar/docker-cli, and binds '
                 'that root for good to the epoch R2D2-V2-SHADOW-2026-10-05, the compiled constant of the release; this process itself '
                 'creates nothing there. Mode REHEARSAL creates two private throwaway directories in /var/lib, a journal root and a '
                 'configuration directory for the docker CLI, runs the same command on them with a diagnostic epoch string, and only '
                 'reads the real journal root and the configuration directory of the unit: no docker command of a rehearsal runs under '
                 'the directory of the unit. Nothing is removed: the throwaway directories and the two files stay. Once the container '
                 'was started, anything but a verified CATALOG_READY leaves a root that is not to be used again. Nothing that exists is '
                 'overwritten, renamed, chmodded or chowned by this process; no unit is touched; a timeout stops the docker CLI, not '
                 'the container.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'after_effect_reserve_seconds':AFTER_EFFECT_RESERVE_SECONDS,
       'files_allowance_seconds':FILES_ALLOWANCE_SECONDS,'files':FILES_SCOPE,
       'modes':list(MODES),'success_outcome':{'REAL':COMPLETE_OUTCOME,'REHEARSAL':REHEARSAL_COMPLETE_OUTCOME},
       'epoch':{'REAL':EPOCH_COMPILED,'REAL_source':EPOCH_SOURCE,'REHEARSAL_grammar':REHEARSAL_EPOCH},
       'script':{'sha256':CATALOG_SCRIPT_SHA256,'bytes':CATALOG_SCRIPT_BYTES,'carried_in_this_source':True,
                 'reference':'c3po/deployment/massive-supervisor/README.md at dd4ec4bb, the lines between the two catalog-init-script markers'},
       'catalog':{'names':list(CATALOG_FILES),'type':'regular file','uid':0,'gid':0,'mode_octal':'%04o'%CATALOG_FILE_MODE,'links':1,
                  'epoch_json':'canonical JSON of schema %s, the epoch, and the device and inode of the journal root as this process reads them on the host'%CATALOG_SCHEMA},
       'throwaway_name':THROWAWAY_NAME,'container_journal_root_forbidden':list(CONTAINER_ROOT_FORBIDDEN),
       'layout':{'docker_config_of_the_unit':UNIT_DOCKER_CONFIG,'journal_root':'a leaf of '+JOURNAL_PARENT,'never_a_journal_root':STATE_ROOT,
                 'throwaway_parent':THROWAWAY_PARENT,'throwaway_docker_config':'<throwaway root>'+THROWAWAY_CONFIG_SUFFIX},
       'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'file_contents_read':[BOOT_ID_PATH,'epoch.json of the journal root, after the container (compared with the expected bytes; only its size and hash leave)'],
       'side_effects':['one container of the signed image is created and removed by the engine (docker run --rm)',
                       'mode REAL: the journal root gains maintenance.lock and epoch.json and is bound to the epoch for good',
                       'mode REHEARSAL: two directories stay in '+THROWAWAY_PARENT+', the throwaway root with its two files and the empty configuration directory docker was given',
                       'a container whose docker CLI was stopped by the time limit is left to the engine; the receipt says whether one is listed that was not there before'],
       'never':['overwrite','chmod','chown','rename','any removal','a second run on a root','docker exec','a shell','systemctl','a pull','a network for the container',
                'any other mount','the token, a manifest, the state root or the configuration directory in the container','--name or any option the README does not write',
                'a docker command of a rehearsal under the configuration directory of the unit'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'catalog_entries':MAX_CATALOG_ENTRIES,'epoch_json_bytes':MAX_EPOCH_JSON_BYTES,'new_container_rows':MAX_NEW_CONTAINER_ROWS}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner,NativeFiles):
    """Everything this source can do to the host: the read primitives, the three signed commands, and the creating
    calls of the files part, of which this operation uses mkdir and fsync only (the throwaway directory of REHEARSAL)."""


def script_bytes():
    """The pinned script, from the constant this source carries. Nothing else is ever given to the container."""
    try:raw=base64.b64decode(CATALOG_SCRIPT_B64.encode('ascii'),validate=True)
    except (ValueError,UnicodeEncodeError):raise Refused('SCRIPT_NOT_THE_PINNED_HASH') from None
    need(len(raw)==CATALOG_SCRIPT_BYTES and sha(raw)==CATALOG_SCRIPT_SHA256,'SCRIPT_NOT_THE_PINNED_HASH');return raw

def signed_rows(rows,receives_entry=False):
    """Signed rows of an existing directory that is not "/": every component root-owned and closed to group and other."""
    need(type(rows) is list and len(rows)>=2 and type(rows[-1]) is dict and type(rows[-1].get('path')) is str,'CHAIN_ROW_INVALID')
    return validate_chain(rows,rows[-1]['path'],None,receives_entry)

def private_rows(rows,label):
    """Signed rows of an existing private directory: root:root, mode 0700 exactly, on the device of its parent (the
    journal root is never a mount point on the host, README "Journal placement")."""
    rows=signed_rows(rows);last=rows[-1]
    need(last['gid']==0 and last['mode']==PRIVATE_DIRECTORY_MODE,label+'_NOT_PRIVATE')          # root-owned like every row: signed_rows
    need(last['device']==rows[-2]['device'],label+'_IS_A_MOUNT_POINT')
    return rows

def journal_rows(rows,label):
    """Signed rows of a journal root: a private directory that is a leaf of the private parent operation 2 created,
    and not the state root of the supervisor. No other directory is a journal root, whatever a request signs."""
    rows=private_rows(rows,label)
    need(rows[-2]['path']==JOURNAL_PARENT,label+'_NOT_A_LEAF_OF_THE_PRIVATE_PARENT')
    need(rows[-1]['path']!=STATE_ROOT,label+'_IS_THE_STATE_ROOT')
    return rows

def journal_path(plan):
    """The host path the container gets: the signed journal root (REAL), or the throwaway this run creates (REHEARSAL)."""
    last=plan['journal_chain'][-1]['path']
    return last if plan['mode']=='REAL' else last.rstrip('/')+'/'+plan['throwaway_name']
def docker_config_path(plan):
    """The directory every docker command of the run gets as DOCKER_CONFIG: the unit's own (REAL), or a throwaway this
    run creates beside the throwaway root (REHEARSAL), so that a rehearsal starts no docker command under the unit's."""
    return plan['docker_config_chain'][-1]['path'] if plan['mode']=='REAL' else journal_path(plan)+THROWAWAY_CONFIG_SUFFIX
def run_mounts(plan):return [{'source':journal_path(plan),'target':plan['container_journal_root'],'read_only':False}]
def run_words(plan):return ['python','-I','-B','-',plan['container_journal_root'],plan['epoch']]

def validate_plan(plan):
    mode=plan['mode'];need(type(mode) is str and mode in MODES,'MODE_INVALID')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    need(type(plan['script_sha256']) is str and plan['script_sha256']==CATALOG_SCRIPT_SHA256,'SCRIPT_NOT_THE_PINNED_HASH');script_bytes()
    need(text(plan['image_revision'],'[0-9a-f]{40}'),'IMAGE_REVISION_UNBOUND')
    target=plan['container_journal_root']
    need(text(target,'/[A-Za-z0-9][A-Za-z0-9._-]{0,63}') and target[1:] not in CONTAINER_ROOT_FORBIDDEN,'CONTAINER_JOURNAL_ROOT_INVALID')
    config=private_rows(plan['docker_config_chain'],'DOCKER_CONFIG')
    need(config[-1]['path']==UNIT_DOCKER_CONFIG,'DOCKER_CONFIG_NOT_THE_DIRECTORY_OF_THE_UNIT')
    if mode=='REAL':
        need(plan['throwaway_name'] is None and plan['reference_chain'] is None,'MODE_MEMBERS_INVALID')
        journal_rows(plan['journal_chain'],'JOURNAL_ROOT')
        need(type(plan['epoch']) is str and plan['epoch']==EPOCH_COMPILED,'EPOCH_NOT_THE_COMPILED_CONSTANT')
    else:
        parent=signed_rows(plan['journal_chain'],True)
        need(parent[-1]['path']==THROWAWAY_PARENT,'THROWAWAY_PARENT_NOT_THE_FIXED_ONE')
        need(text(plan['throwaway_name'],THROWAWAY_NAME),'THROWAWAY_NAME_INVALID')
        reference=journal_rows(plan['reference_chain'],'REFERENCE_ROOT')
        need(reference[-1]['device']==parent[-1]['device'],'REHEARSAL_NOT_ON_THE_FILESYSTEM_OF_THE_REAL_ROOT')
        need(text(plan['epoch'],REHEARSAL_EPOCH),'EPOCH_NOT_A_DIAGNOSTIC_ONE')
    run_arguments(RUN_ROW,plan['image_id'],run_mounts(plan),run_words(plan))

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    rehearsal=plan['mode']=='REHEARSAL';path=journal_path(plan);use_path=docker_config_path(plan)
    return {'operation':OPERATION,'mode':plan['mode'],
            'journal_root':{'path':path,'is_the_real_journal_root':not rehearsal,
                            'expect':'ABSENT_THEN_CREATED_0700_BY_THIS_RUN' if rehearsal else 'PRESENT_EMPTY_ROOT_ROOT_0700_AS_SIGNED',
                            'signed_chain':chain_effects(plan['journal_chain']),'signed_chain_is_of':'THE_PARENT' if rehearsal else 'THE_ROOT_ITSELF',
                            'stays_after_the_run':True},
            'real_journal_root_read_only':None if not rehearsal else dict(chain_effects(plan['reference_chain']),expect='PRESENT_EMPTY_ROOT_ROOT_0700_AS_SIGNED',
                                                                           same_device_as_the_parent_of_the_throwaway=True),
            'docker_config':dict(chain_effects(plan['docker_config_chain']),given_to_docker=not rehearsal,
                                 expect='PRESENT_EMPTY_ONLY_READ_NEVER_GIVEN_TO_DOCKER' if rehearsal else 'PRESENT_EMPTY_BEFORE_AND_AFTER'),
            'rehearsal_docker_config':None if not rehearsal else {'path':use_path,'expect':'ABSENT_THEN_CREATED_0700_BY_THIS_RUN_EMPTY_AFTER_IT',
                                                                   'given_to_docker':True,'stays_after_the_run':True},
            'container':{'image_id':plan['image_id'],'image_revision':plan['image_revision'],'docker_config_variable':use_path,
                         'docker_arguments':RUN_PREFIX+run_arguments(RUN_ROW,plan['image_id'],run_mounts(plan),run_words(plan)),
                         'bind':run_mounts(plan)[0],'network':'none','standard_input':{'sha256':CATALOG_SCRIPT_SHA256,'bytes':CATALOG_SCRIPT_BYTES},
                         'time_limit_seconds':COMMAND_CLASSES[COMMANDS[RUN_ROW]['class']]['seconds']},
            'epoch':plan['epoch'],'epoch_source':'SIGNED_DIAGNOSTIC_STRING' if rehearsal else EPOCH_SOURCE,
            'creates':{'by_this_process':[use_path,path] if rehearsal else [],'by_the_container':[path+'/'+name for name in CATALOG_FILES],
                       'file_mode_octal':'%04o'%CATALOG_FILE_MODE},
            'success_outcome':success_of(plan),'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'pre_existing_objects_modified':not rehearsal,'removes':[],'activation':False}
def success_of(plan):return COMPLETE_OUTCOME if plan['mode']=='REAL' else REHEARSAL_COMPLETE_OUTCOME


def script_line(result,epoch):
    """What the container printed, reduced to what is compared. as_signed is true for exactly the line of a creating
    run: the six keys, CATALOG_READY, created true, the signed epoch, the two names in order, an integer identity. Of
    a refusal only a constant code is kept: the script prints the text of whatever exception it caught (README,
    "Known wart"), and raw text never leaves this process."""
    output=result['output'] if type(result.get('output')) is bytes else b''
    line={'returncode':result['returncode'],'bytes':len(output),'sha256':sha(output) if output else None,'one_json_line':False,'status':None,
          'refusal_code':None,'as_signed':False,'keys_exact':None,'created':None,'epoch_equal':None,'entries_as_expected':None,'device':None,'inode':None}
    try:row=single_line(output)
    except Refused:return line
    line['one_json_line']=True;status=row.get('status')
    line['status']=status if type(status) is str and status in ('CATALOG_READY','CATALOG_REFUSED') else 'OTHER'
    if line['status']=='CATALOG_REFUSED':
        line['refusal_code']=row['code'] if text(row.get('code'),CODE) else 'NOT_A_CONSTANT_CODE'
    if line['status']=='CATALOG_READY':
        line['keys_exact']=set(row)=={'status','created','epoch','device','inode','entries'}
        if line['keys_exact']:
            line.update(created=row['created'] is True,epoch_equal=row['epoch']==epoch,entries_as_expected=row['entries']==list(CATALOG_FILES),
                        device=row['device'] if integer(row['device']) else None,inode=row['inode'] if integer(row['inode'],1) else None)
            line['as_signed']=(line['created'] and line['epoch_equal'] and line['entries_as_expected'] and line['device'] is not None
                               and line['inode'] is not None)
    return line

def catalog_readback(host,gate,root,epoch):
    """What the run left in the journal root, read on the host through the descriptor held since before the container:
    how many entries, the two catalog names with type, owner, mode, links and size (other names are counted, never
    printed), and epoch.json compared byte for byte with what the application writes for this epoch and for the
    device and inode of this directory. maintenance.lock is never opened. Never raises: what was read stays in the row."""
    out={'status':'UNAVAILABLE','code':None,'entries':None,'other_entries':None,'files':{},'epoch_json':None,'root_unchanged':None}
    try:
        gate();names=[];listed={}
        for name in host.names(root.fd):
            names.append(name);need(len(names)<=MAX_CATALOG_ENTRIES,'ENTRY_LIMIT')
        out['entries']=len(names);out['other_entries']=len([name for name in names if name not in CATALOG_FILES])
        for name in CATALOG_FILES:
            if name not in names:
                out['files'][name]={'exists':False};continue
            gate();info=host.lstat(name,root.fd);listed[name]=(info.st_dev,info.st_ino)
            out['files'][name]={'exists':True,'type':kind(info.st_mode),'uid':info.st_uid,'gid':info.st_gid,'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),
                                'links':info.st_nlink,'bytes':info.st_size,'on_the_device_of_the_root':info.st_dev==root.identity[0]}
        if out['files'][CATALOG_FILES[0]].get('type')=='file':
            expected=canonical({'schema':CATALOG_SCHEMA,'epoch':epoch,'device':root.identity[0],'inode':root.identity[1]})
            raw,held=read_regular(host,CATALOG_FILES[0],root.fd,gate,MAX_EPOCH_JSON_BYTES)
            need((held.st_dev,held.st_ino)==listed[CATALOG_FILES[0]],'FILE_CHANGED_DURING_READ')          # the file read is the one whose metadata was taken
            out['epoch_json']={'bytes':len(raw),'sha256':sha(raw),'expected_sha256':sha(expected),'equal_to_the_expected_bytes':raw==expected}
        try:root.verify(gate);out['root_unchanged']=True
        except Refused as error:
            if str(error)=='PARENT_REPLACED':out['root_unchanged']=False
            raise
        out['status']='COMPLETE'
    except Exception as error:
        out['code']=code_of(error,'READBACK_OS_ERROR' if isinstance(error,OSError) else 'READBACK_FAILED')
    return out

def file_as_expected(row):
    return row.get('exists') is True and (row['type'],row['uid'],row['gid'],row['mode_octal'],row['links'],row['on_the_device_of_the_root'])==(
        'file',0,0,'%04o'%CATALOG_FILE_MODE,1,True)
def catalog_as_expected(catalog):
    """A complete readback shows exactly the two files of the application, and epoch.json holds the expected bytes."""
    return (catalog['entries']==len(CATALOG_FILES) and all(file_as_expected(catalog['files'][name]) for name in CATALOG_FILES)
            and catalog['epoch_json']['equal_to_the_expected_bytes'] is True)

def run_failure(result,line,catalog,identity):
    """None when the container that returned is the verified creation of the catalog; otherwise the first thing that
    is not as it must be, in the order in which the run produces it. One of docker's own statuses (125, 126, 127)
    does not by itself spend the root: `--rm` can turn a clean exit into 125 when the wait for the removal fails
    (README, "Exit statuses"). With such a status the line and the host readback decide: when both are those of a
    verified creation this returns None and the caller reports the status as a finding beside a verified catalog."""
    engine=result['returncode'] in RUN_ENGINE_STATUSES
    failure=catalog_failure(result['returncode'] if not engine else 0,line,catalog,identity)
    return 'ENGINE_COULD_NOT_RUN_THE_CONTAINER' if engine and failure is not None else failure
def catalog_failure(returncode,line,catalog,identity):
    if not line['one_json_line']:return 'SCRIPT_OUTPUT_NOT_ONE_LINE'
    if line['status']=='CATALOG_REFUSED':return 'SCRIPT_REFUSED'
    if returncode!=0:return 'SCRIPT_FAILED'
    if not line['as_signed']:return 'SCRIPT_LINE_NOT_AS_SIGNED'
    if (line['device'],line['inode'])!=tuple(identity):return 'CATALOG_IDENTITY_NOT_THE_HOSTS'
    if catalog['status']!='COMPLETE':return 'CATALOG_READBACK_UNAVAILABLE'
    if not catalog_as_expected(catalog):return 'CATALOG_READBACK_MISMATCH'
    return None

def _reduce_observed(receipt):receipt['observed_rows']={'reduced_for_size':True}
def _reduce_containers(receipt):
    if type(receipt.get('containers')) is dict:receipt['containers']['rows']=[]
REDUCTIONS=[('OBSERVED_ROWS_DROPPED',_reduce_observed),('NEW_CONTAINER_ROWS_DROPPED',_reduce_containers)]

def pin_chain(host,rows,gate,observed):
    """Walks a signed chain and holds its last directory. A descriptor that does not become a held directory is closed."""
    fd=walk_pinned(host,rows,gate,observed)
    try:return Pinned(host,fd,rows=rows)
    except BaseException:
        try:host.close(fd)
        except Exception:pass
        raise

def directory_stop(entry):
    """None for a directory this run created and proved; otherwise the code its ledger row carries."""
    return None if entry['state']=='CREATED_DURABLE' else (entry['code'] or 'CREATION_FAILED')

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    script=script_bytes();rehearsal=plan['mode']=='REHEARSAL'                                    # pure
    path=journal_path(plan);use_path=docker_config_path(plan);mounts=run_mounts(plan);words=run_words(plan)
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    commands=Commands(host,gate);observed={'docker_config':[],'journal':[],'reference':[]};precheck={}
    directories=[];handles={};pinned=[]
    facts={'run':None,'script_line':None,'catalog':None,'containers':None,'docker_config':None,'root':None,'verdict':'UNTOUCHED_NO_CONTAINER_STARTED'}
    def finish(status,outcome,code,extra):
        catalog=facts['catalog'];left=objects_left(directories,[])
        if catalog is not None:left=None if catalog['entries'] is None else left+catalog['entries']
        # What the docker commands of the run left in the directory they were given counts as left by this run; in mode
        # REAL that directory is the unit's, an object that existed before. A count that could not be taken is unknown.
        given=precheck.get('docker_config_entries_after_the_reads',0) if facts['docker_config'] is None else facts['docker_config']['entries_after']
        if left is not None:left=None if given is None else left+given
        touched=[False] if rehearsal else [None if given is None else given>0,False if catalog is None else (None if catalog['entries'] is None else catalog['entries']>0)]
        receipt=envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),mode=plan['mode'],effects=effects_of(plan),
            clock=timing(begun,mark,clock,monotonic),commands_started=dict(commands.started),mutating_calls=state.counts(),
            observed_rows=observed,precheck=precheck,directories=directories,journal_root=facts['root'],run=facts['run'],script_line=facts['script_line'],
            catalog=catalog,containers=facts['containers'],docker_config=facts['docker_config'],root_verdict=facts['verdict'],
            objects_left_by_this_run=left,
            pre_existing_objects_modified=True if True in touched else (None if None in touched else False),**extra))
        return seal(receipt)
    def reads(use,root):
        """The two docker reads, under the directory docker is given in this mode, and then the last look: every
        directory held is still what was walked or created and the root (REAL) is still empty. Whatever the reads end
        in, once one of them was started the directory docker was given is counted again before anything is concluded:
        the count goes into the precheck, and a directory that is not empty is a finding of its own. Returns the
        containers listed."""
        failure=None
        try:
            try:image=image_facts(commands,plan['image_id'],docker_config=use_path)
            except CommandFailed:raise Refused('IMAGE_ABSENT_OR_UNREADABLE') from None
            need(image['id']==plan['image_id'],'IMAGE_ID_MISMATCH')
            need(image['revision_label']==plan['image_revision'],'IMAGE_REVISION_MISMATCH')
            precheck['image']={'id_as_signed':True,'revision_as_signed':True}
            try:listed=container_list(commands,docker_config=use_path)
            except CommandFailed:raise Refused('CONTAINER_LISTING_FAILED') from None
            precheck['containers']=len(listed)
            for handle in pinned+list(handles.values()):handle.verify(gate)
            if root is not None:need(count_entries(host,root.fd,gate,MAX_DIRECTORY_ENTRIES)==0,'JOURNAL_ROOT_NOT_EMPTY')
        except Exception as error:failure=error
        if commands.started['READ']:
            counted=attempt(lambda:count_entries(host,use.fd,gate,MAX_DIRECTORY_ENTRIES))
            precheck['docker_config_entries_after_the_reads']=counted if type(counted) is int else None
        if failure is not None:raise failure
        need(precheck.get('docker_config_entries_after_the_reads') is not None,CONFIG_UNKNOWN)
        need(precheck['docker_config_entries_after_the_reads']==0,CONFIG_CHANGED)
        return listed
    def after_reads(code):
        """The code of a failed read or of a failed last look, unless the directory docker was given is not known to be
        empty after the reads: then that is the finding, and the first one is kept beside it in the precheck."""
        given=precheck.get('docker_config_entries_after_the_reads',0)
        if given==0 or code in (CONFIG_CHANGED,CONFIG_UNKNOWN):return code
        precheck['first_finding']=code;return CONFIG_UNKNOWN if given is None else CONFIG_CHANGED
    try:
        # ---- everything the file system shows is looked at before anything is created or started
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o077)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            config=pin_chain(host,plan['docker_config_chain'],gate,observed['docker_config']);pinned.append(config)
            precheck['docker_config_entries']=count_entries(host,config.fd,gate,MAX_DIRECTORY_ENTRIES)
            need(precheck['docker_config_entries']==0,'DOCKER_CONFIG_DIRECTORY_NOT_EMPTY')
            if rehearsal:
                reference=pin_chain(host,plan['reference_chain'],gate,observed['reference']);pinned.append(reference)
                precheck['real_journal_root_entries']=count_entries(host,reference.fd,gate,MAX_DIRECTORY_ENTRIES)
                need(precheck['real_journal_root_entries']==0,'REFERENCE_ROOT_NOT_EMPTY')
                parent=pin_chain(host,plan['journal_chain'],gate,observed['journal']);pinned.append(parent)
                for label,target in (('throwaway',path),('throwaway_docker_config',use_path)):
                    found=probe(host,target,gate);precheck[label]={'exists':found.get('exists')}
                    need(found.get('status')=='COMPLETE' and found['exists'] is False,'DESTINATION_PRESENT')
                binary(host,BINARIES['docker'],gate)                      # no directory is created for a docker that cannot be started
            else:
                root=pin_chain(host,plan['journal_chain'],gate,observed['journal']);pinned.append(root)
                precheck['journal_root_entries']=count_entries(host,root.fd,gate,MAX_DIRECTORY_ENTRIES)
                need(precheck['journal_root_entries']==0,'JOURNAL_ROOT_NOT_EMPTY')
                # REAL: the reads run under the directory of the unit and are part of the precheck.
                before=reads(config,root)
            # The last refusal that costs nothing: the whole class of the run and its reserve fit in what is left.
            need(gate()>=effects_budget(RUN_ROW)+(FILES_ALLOWANCE_SECONDS if rehearsal else 0),'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:
            # A refusal says that nothing changed. When a docker read of the precheck ran (REAL: under the directory of
            # the unit) and that directory is not known to be empty afterwards, that cannot be said: the root is
            # untouched and usable, and the run is a partial whose code names the directory.
            code=after_reads(code)
            if code in (CONFIG_CHANGED,CONFIG_UNKNOWN):return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,code,{'phase_reached':'PRECHECK'})
            return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})
        # ---- from here on nothing refuses unless nothing has changed and no container was started
        stop=None
        if rehearsal:
            # A rehearsal never gives docker the directory of the unit. It creates a configuration directory of its
            # own, makes the two reads under it, and only then creates the throwaway root. What fails after the first
            # directory exists is a PARTIAL: the throwaway name is spent, production is as it was.
            entry=create_directory('DOCKER_CONFIG',use_path,PRIVATE_DIRECTORY_MODE,parent,host,gate,state,handles);directories.append(entry)
            stop=directory_stop(entry)
            if stop is None:
                try:before=reads(handles['DOCKER_CONFIG'],None)
                except Exception as error:stop=after_reads(code_of(error,'READS_OS_ERROR' if isinstance(error,OSError) else 'READS_FAILED'))
            if stop is None:
                entry=create_directory('JOURNAL_ROOT',path,PRIVATE_DIRECTORY_MODE,parent,host,gate,state,handles);directories.append(entry)
                stop=directory_stop(entry)
            if stop is None:root=handles['JOURNAL_ROOT']
            elif not state.clean():facts['verdict']='NOT_TO_BE_USED_AGAIN'
        if stop is None:
            use=handles['DOCKER_CONFIG'] if rehearsal else config
            facts['root']={'path':path,'device':root.identity[0],'inode':root.identity[1],'created_by_this_run':rehearsal}
            run={'state':'NOT_STARTED','code':None,'returncode':None,'seconds':None};facts['run']=run
            started=attempt(monotonic)
            result=container_effect(state,commands,RUN_ROW,plan['image_id'],mounts,words,script,docker_config=use_path)
            ended=attempt(monotonic)
            run.update(code=result['code'],returncode=result['returncode'],
                       seconds=round(ended-started,3) if type(started) in (int,float) and type(ended) in (int,float) else None)
            if not result['started']:
                stop=result['code'] or 'COMMAND_NOT_STARTED'
                if rehearsal:facts['verdict']='NOT_TO_BE_USED_AGAIN'
            else:
                # The container was started. What it left is read on the host, whatever the docker CLI said; only then is the call settled.
                run['state']='RETURNED' if result['returned'] else 'DID_NOT_RETURN'
                line=script_line(result,plan['epoch']);facts['script_line']=line
                catalog=catalog_readback(host,gate,root,plan['epoch']);facts['catalog']=catalog
                listing=attempt(lambda:container_list(commands,docker_config=use_path))
                if type(listing) is list:
                    known=set(row['id'] for row in before);new=[row for row in listing if row['id'] not in known]
                    containers={'status':'COMPLETE','before':len(before),'after':len(listing),'not_there_before':len(new),'rows':new[:MAX_NEW_CONTAINER_ROWS]}
                else:containers=dict(listing,before=len(before),after=None,not_there_before=None,rows=[])
                facts['containers']=containers
                def config_entries():
                    use.verify(gate);return count_entries(host,use.fd,gate,MAX_DIRECTORY_ENTRIES)
                entries=attempt(config_entries)
                facts['docker_config']={'path':use_path,'is_the_directory_of_the_unit':not rehearsal,'entries_before':0,
                                        'entries_after':entries if type(entries) is int else None,'code':None if type(entries) is int else entries.get('code')}
                failure=run_failure(result,line,catalog,root.identity[:2]) if result['returned'] else (result['code'] or 'COMMAND_FAILED')
                if result['returned']:
                    if failure is None:state.done()
                    else:state.unknown()
                if failure is not None:stop=failure;facts['verdict']='NOT_TO_BE_USED_AGAIN'
                else:
                    if result['returncode']!=0:stop='ENGINE_STATUS_AFTER_A_VERIFIED_CATALOG'
                    elif containers['status']!='COMPLETE':stop='CONTAINER_LISTING_UNAVAILABLE_AFTER_RUN'
                    elif containers['not_there_before']:stop='CONTAINER_PRESENT_THAT_WAS_NOT_THERE_BEFORE'
                    elif facts['docker_config']['entries_after'] is None:stop='DOCKER_CONFIG_READBACK_UNAVAILABLE'
                    elif facts['docker_config']['entries_after']:stop='DOCKER_CONFIG_DIRECTORY_NOT_EMPTY_AFTER_RUN'
                    facts['verdict']='CATALOG_READY_VERIFIED' if stop is None else 'CATALOG_VERIFIED_WITH_FINDINGS'
        extra={'phase_reached':'EFFECTS'}
        if stop is None:return finish(COMPLETE_STATUS,success_of(plan),None,extra)
        # REFUSED only while no mutating call succeeded and none is uncertain: no directory was created and no process of the run existed.
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)
    finally:
        for handle in list(handles.values())+pinned:
            try:handle.close()
            except Exception:pass
