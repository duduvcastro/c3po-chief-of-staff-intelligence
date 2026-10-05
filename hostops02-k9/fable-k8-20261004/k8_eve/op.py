import base64

OPERATION='GO_WRITE_HOSTOPS02_K8_EVE_DELIVERY_01'
PHASE='WRITE_K8_EVE_DELIVERY_DAY_DOCUMENTS_AND_PAYLOAD'
REQUEST_SCHEMA='WRITE_HOSTOPS02_K8_EVE_DELIVERY_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_K8_EVE_DELIVERY_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_K8_EVE_DELIVERY_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_K8_EVE_DELIVERY_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_K8_EVE_DELIVERY_PLAN_V1'
SOURCE_NAME='k8_eve.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False
# E6 runs on the eve of a session, after the causal list of that session is committed (K9 note 5.7 rule 9): from 20:00Z
# of D-1 to 09:00Z of D, which is UTC day D-1 or D. The narrowest class of the core that holds 10-05 ... 10-09 is
# WRITE_SESSIONS; the eve band (A2 row E6) is the binder's and is checked again by perform (K8_EVE).
DATE_CLASS='WRITE_SESSIONS'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
EVIDENCE_OPERATIONS=('GO_READONLY_HOSTOPS02_K9_PHASE_READ_01',)
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='EVE_DAY_DOCUMENTS_AND_PAYLOAD_DELIVERED_READ_BACK'
PARTIAL_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
PLAN_KEYS=frozenset(('day','windows','contract','files','days_parent','identity_rule','evidence_boot_id_sha256'))

# ---- the epoch and its five sessions; the four days that have an eve with a committed causal list (K9 note 5.5: Monday
# ---- 05/10 has no K9 list). The day before each is its eve.
K8_EPOCH='R2D2-V2-SHADOW-2026-10-05'
K8_EVES={'2026-10-06':'2026-10-05','2026-10-07':'2026-10-06','2026-10-08':'2026-10-07','2026-10-09':'2026-10-08'}
K8_EVE_FROM='T20:00:00+00:00'            # on the eve: 17:00 BRT
K8_EVE_UNTIL='T09:00:00+00:00'           # on the day: 06:00 BRT, before D0 (07:26) and the first capacity window (07:38)
K8_PACKAGE='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'
K8_REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'

# ---- the capacity tree, as the reader-and-capacity provisioning created it on 03/10 (request beb45945..., KNOWN_COMPLETE:
# ---- /var/lib/c3po-capacity and its four roots, root:root 0700, on the root filesystem) and as the reader, the compose
# ---- worker and the capacity-day writer bind it read-only at /c3po-capacity (capacity-day README, "Mounts").
K8_VAR_LIB='/var/lib'
K8_CAPACITY_NAME='c3po-capacity'
K8_CAPACITY_ROOT=K8_VAR_LIB+'/'+K8_CAPACITY_NAME
K8_CAPACITY_ROOTS=('config','documents','go','payload')
K8_IDENTITY_ROOTS=('documents','go','payload')      # the three roots whose AnchoredRoot identity every capacity config pins
K8_CONTAINER_CAPACITY='/c3po-capacity'

# ---- the K9 tree (Codex's N-8 placement, W/codex-n8-placement-20261004.txt) and what the commit step leaves in it
K8_K9_ROOT='/var/lib/c3po/r2d2-v2-k9-20261005'
K8_K9_DAYS=K8_K9_ROOT+'/days'
K8_CAUSAL='causal'
K8_RECEIPTS='receipts'
K8_COMMITMENT='commitment.private.json'
K8_AUDIT='build_audit_receipt.json'
K8_COMMIT_RECEIPT='commit_launch.RECEIPT.json'
K8_COMMIT_OUTPUTS=('day/causal/'+K8_COMMITMENT,'day/causal/'+K8_AUDIT)
K8_STEP_RECEIPT_KEYS=frozenset(('schema','status','code','epoch','day','phase','operation','attempt_key','step_plan_sha256','started_at',
                                'completed_at','package_sha256','build_sha','outputs','aggregates','counts'))
K8_COMMITMENT_SCHEMA='V2_CAUSAL_LIST_COMMITMENT_V1'
K8_BUILT_EVENT='r2d2.v2.causal_list_built'
K8_AUDIT_KEYS=frozenset(('event_id','event_type','occurred_at','payload'))
K8_CAPACITY=550
K8_SYMBOL='[A-Z0-9][A-Z0-9.-]{0,19}'

# ---- the day's documents (capacity_day_documents.py, layout(); D4 = PRE_DELIVERED: the views go with the rest)
K8_CHAIN_ROLES=('CODEX','FABLE','DUDU','ACT_B','B_CODEX','B_FABLE','B_DUDU')
K8_RECORD_PINS=(('template','TEMPLATE'),('go_admission_record','GO:admission'),('go_bar_manifest_record','GO:bar_manifest'),
                ('publication_bar_manifest','PUBLICATION:bar_manifest'))
K8_GO_FILES=(('go_admission','admission'),('go_bar_manifest','bar_manifest'))
K8_CONTRACT_KEYS=frozenset(('assembler_plan','policy','order','template','owner_sha','causal_scope','consumer_plans'))
K8_WINDOW_NAME='[a-z][a-z0-9_]{0,31}'
K8_MAX_WINDOWS=3                          # a primary window and up to two contingencies (ORD:16)
K8_FILE_NAME='session=2026-10-0[6-9][.][a-z][A-Za-z0-9._-]{0,99}'
K8_CHAIN_FILE_NAME='[A-Za-z0-9][A-Za-z0-9._-]{0,127}'
K8_IDENTITY_RULES=('REFUSE_ON_MISMATCH','REPORT_ONLY')

# ---- limits
K8_DELIVERY_MAX_BYTES=40960               # the contract and the twelve files; base64 of them plus the rest of the request stays below 65536
K8_RECEIPT_MAX_BYTES=262144               # the runner reads its own receipts with this limit
K8_COMMITMENT_MAX_BYTES=67108864          # MAX_CAUSAL_ENVELOPE_BYTES of r2d2_v2_causal_list.py
K8_AUDIT_MAX_BYTES=65536
K8_CHAIN_MAX_BYTES=1048576
K8_FREE_BYTES_FLOOR=4194304               # free bytes on the capacity tree's filesystem before the first creation
K8_WRITE_ALLOWANCE_SECONDS=15             # what must be left of the budget before the first creation (the writes take milliseconds)
K8_FILE_MODE=0o600
K8_DIRECTORY_MODE=0o700

def k8_layout(day,windows):
    """(key, root, name) of the signed files of one day, in creation order (six, and two per window: twelve with three
    windows); the payload file is created after them."""
    stem='session='+day
    table=[('template','documents',stem+'.template.md'),('go_admission_record','documents',stem+'.go-admission.md'),
           ('go_bar_manifest_record','documents',stem+'.go-bar_manifest.md'),('publication_bar_manifest','documents',stem+'.publication-bar_manifest.md')]
    table+=[('veto_view:'+window,'documents',stem+'.view-'+window+'.md') for window in windows]
    table+=[('go_admission','go',stem+'.admission.json'),('go_bar_manifest','go',stem+'.bar_manifest.json')]
    table+=[('capacity_config:'+window,'config',stem+'.'+window+'.capacity.json') for window in windows]
    return table
def k8_payload_name(day):return 'session='+day+'.json'
def k8_path(root,name):return K8_CAPACITY_ROOT+'/'+root+'/'+name
def k8_commit_key(day):
    """The Act B single-use key of the day's commit_launch: sha256 of the canonical [epoch, day, phase, operation]."""
    return sha(canonical([K8_EPOCH,day,'causal_list','commit_launch']))
def k8_named_in(path,directory):
    """K8's name rule for k8_create_file: a clean path whose name is one of the day's names ('session=<day>.' and a
    suffix) and whose directory, where the held parent carries signed rows, is the one the parent was walked to."""
    return (type(path) is str and clean_path(path) and text(PurePosixPath(path).name,K8_FILE_NAME)
            and (directory.rows is None or str(PurePosixPath(path).parent)==directory.rows[-1]['path']))

SCOPE_STATEMENT=('Delivers, once per session day of epoch '+K8_EPOCH+' and on its eve, after the causal list of that day is committed: into the '
                 'capacity tree '+K8_CAPACITY_ROOT+' (roots config, documents, go and payload, each a root:root 0700 directory held by descriptor) '
                 'the twelve signed files of the day (template, two GO records, publication record and one veto view per window into documents; '
                 'the admission and bar_manifest GO files into go; one capacity config per window into config), each root:root 0600 holding '
                 'exactly the bytes whose SHA-256 and size the request signs; and the payload file session=<day>.json into payload, assembled on '
                 'the host as the canonical JSON of the signed contract (the thirteenth signed file, carried whole in the payload file) and the '
                 'causal object of the commitment that the day\'s K9 commit step left in '+K8_K9_DAYS+'/<day>/causal, read by fixed path and '
                 'accepted only if its bytes are the ones the commit receipt names and its two hashes are the contract\'s causal scope. Every '
                 'name must be absent; the seven chain documents the configs pin must be in documents with their pinned bytes. Exclusive '
                 'creation, fsync and a readback of every file through descriptors inside the run. Nothing that exists is overwritten, renamed, '
                 'chmodded, chowned or removed, except the temporary of this run once its identity is proved. No symbol and no hash or size of '
                 'the payload file reaches the receipt (the commitment\'s digest is the public causal scope of the contract). No process is '
                 'started, no secret is read or written, no container is touched and nothing is activated.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,'epoch':K8_EPOCH,'days':sorted(K8_EVES),
       'eve':{'from':'D-1'+K8_EVE_FROM,'until':'D'+K8_EVE_UNTIL},
       'capacity_tree':{'path':K8_CAPACITY_ROOT,'roots':list(K8_CAPACITY_ROOTS),'directory_mode_octal':'%04o'%K8_DIRECTORY_MODE,
                        'container_path':K8_CONTAINER_CAPACITY,'identity_roots':list(K8_IDENTITY_ROOTS),'identity_rules':list(K8_IDENTITY_RULES)},
       'files':{'names':['session=<day>.template.md','session=<day>.go-admission.md','session=<day>.go-bar_manifest.md',
                         'session=<day>.publication-bar_manifest.md','session=<day>.view-<window>.md','session=<day>.admission.json',
                         'session=<day>.bar_manifest.json','session=<day>.<window>.capacity.json'],
                'payload':'session=<day>.json','mode_octal':'%04o'%K8_FILE_MODE,'max_windows':K8_MAX_WINDOWS,'how':FILES_SCOPE['file']['how'],
                'temporary_name':FILES_SCOPE['file']['temporary_name'],'leftover_pattern':LEFTOVER},
       'k9_inputs':{'days':K8_K9_DAYS,'commitment':K8_CAUSAL+'/'+K8_COMMITMENT,'audit_receipt':K8_CAUSAL+'/'+K8_AUDIT,
                    'commit_receipt':K8_RECEIPTS+'/'+K8_COMMIT_RECEIPT,'receipt_outputs':list(K8_COMMIT_OUTPUTS),'package_sha256':K8_PACKAGE,
                    'build_sha':K8_REVISION},
       'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'file_contents_read':[BOOT_ID_PATH,'the commit receipt, the commitment and its audit receipt of the day (K9 tree)',
                             'the seven chain documents the capacity configs pin (capacity tree, documents root)',
                             'every file this run delivered (readback inside the run)'],
       'processes_started':0,
       'never':['overwrite','chmod','chown','rename','truncate','removal of anything but the temporary this run created','a process','docker',
                'systemctl','a shell','a network connection','a secret','activation','a container','a second attempt','a symbol in the receipt',
                'the hash or the size of the payload file in the receipt'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'delivery_bytes':K8_DELIVERY_MAX_BYTES,'commit_receipt_bytes':K8_RECEIPT_MAX_BYTES,'commitment_bytes':K8_COMMITMENT_MAX_BYTES,
                 'audit_receipt_bytes':K8_AUDIT_MAX_BYTES,'chain_document_bytes':K8_CHAIN_MAX_BYTES,'payload_bytes':MAX_FILE_BYTES,
                 'free_bytes_floor':K8_FREE_BYTES_FLOOR,'write_allowance_seconds':K8_WRITE_ALLOWANCE_SECONDS,'capacity':K8_CAPACITY}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeFiles):
    """Everything this source can do to the host: the read primitives and the seven creating calls. No process."""


# ---------------------------------------------------------------- the signed bytes, judged without the host (pure)
def k8_blob(item,code):
    """One signed file of the request: strict base64 of bytes whose SHA-256 and size the request signs."""
    need(type(item) is dict and set(item)=={'sha256','bytes','content_b64'},code)
    need(hexpin(item['sha256']) and integer(item['bytes'],1,MAX_FILE_BYTES) and type(item['content_b64']) is str,code)
    try:raw=base64.b64decode(item['content_b64'].encode('ascii'),validate=True)
    except (ValueError,UnicodeEncodeError):raise Refused(code) from None
    need(len(raw)==item['bytes'] and sha(raw)==item['sha256'],code)
    return raw

def k8_json(raw,limit,code):
    """A JSON object in exactly its canonical bytes (the store's canonical(): sorted keys, compact, ASCII)."""
    try:value=strict(raw,limit)
    except Refused:raise Refused(code) from None
    need(type(value) is dict and canonical(value)==raw,code)
    return value

def k8_pin(value,code):
    need(type(value) is dict and set(value)=={'file','sha256'} and text(value['file'],K8_CHAIN_FILE_NAME) and hexpin(value['sha256']),code)
    return value

def k8_delivery(plan):
    """Everything the request carries about the day, decoded and judged: the thirteen signed files, their names, their
    hashes against each other (every window's config pins the day's four records and its own view, all windows pin the
    same seven chain documents and the same three roots), the contract's causal scope and the two GO files' day."""
    day=plan['day'];windows=plan['windows']
    need(day in K8_EVES,'DAY_INVALID')
    need(type(windows) is list and 1<=len(windows)<=K8_MAX_WINDOWS and all(text(name,K8_WINDOW_NAME) for name in windows)
         and len(set(windows))==len(windows),'WINDOWS_INVALID')
    layout=k8_layout(day,windows);names={key:name for key,_,name in layout}
    need(type(plan['files']) is dict and set(plan['files'])==set(names),'DELIVERY_FILES_NOT_THE_LAYOUT')
    raws={key:k8_blob(plan['files'][key],'DELIVERY_FILE_INVALID') for key,_,_ in layout}
    contract_raw=k8_blob(plan['contract'],'CONTRACT_INVALID')
    need(len(contract_raw)+sum(len(raw) for raw in raws.values())<=K8_DELIVERY_MAX_BYTES,'DELIVERY_TOO_LARGE')
    contract=k8_json(contract_raw,MAX_FILE_BYTES,'CONTRACT_INVALID')
    need(set(contract)==K8_CONTRACT_KEYS,'CONTRACT_INVALID')
    scope=contract['causal_scope']
    need(type(scope) is dict and set(scope)=={'epoch','session','commitment_sha256','list_sha256'} and scope['epoch']==K8_EPOCH
         and scope['session']==day and hexpin(scope['commitment_sha256']) and hexpin(scope['list_sha256']),'CONTRACT_NOT_OF_THIS_DAY')
    chain=None;roots=None
    for window in windows:
        config=k8_json(raws['capacity_config:'+window],MAX_FILE_BYTES,'CONFIG_INVALID')
        pins=config.get('document_pins');views=config.get('veto_views');found=config.get('roots')
        need(type(pins) is dict and set(pins)==set(K8_CHAIN_ROLES)|{label for _,label in K8_RECORD_PINS},'CONFIG_PINS_INVALID')
        this={role:k8_pin(pins[role],'CONFIG_PINS_INVALID') for role in K8_CHAIN_ROLES}
        need(chain is None or this==chain,'CONFIG_PINS_INVALID');chain=this
        for key,label in K8_RECORD_PINS:
            need(pins[label]=={'file':names[key],'sha256':sha(raws[key])},'DELIVERY_NOT_CONSISTENT')
        need(views=={day:{'file':names['veto_view:'+window],'sha256':sha(raws['veto_view:'+window])}},'DELIVERY_NOT_CONSISTENT')
        need(type(found) is dict and set(found)==set(K8_IDENTITY_ROOTS) and all(
            type(found[root]) is dict and set(found[root])=={'path','identity'} and found[root]['path']==K8_CONTAINER_CAPACITY+'/'+root
            and hexpin(found[root]['identity']) for root in K8_IDENTITY_ROOTS),'CONFIG_ROOTS_INVALID')
        need(roots is None or found==roots,'CONFIG_ROOTS_INVALID');roots=found
    for key,phase in K8_GO_FILES:
        go=k8_json(raws[key],MAX_FILE_BYTES,'GO_FILE_INVALID')
        need(set(go)=={'go'} and type(go['go']) is dict,'GO_FILE_INVALID')
        need((go['go'].get('epoch'),go['go'].get('day'),go['go'].get('phase'))==(K8_EPOCH,day,phase),'GO_FILE_NOT_OF_THIS_DAY')
    return {'layout':layout,'raws':raws,'contract_raw':contract_raw,'contract':contract,'scope':scope,'chain':chain,'roots':roots}

def k8_root_controlled(row):
    """What the K9 chain needs beyond validate_chain without an open root (uid 0 and no write bit for group or other on
    every component): group 0, and no setgid bit on any component (as K4 mode E0 required of the same chain)."""
    return row['gid']==0 and not row['mode']&stat.S_ISGID

def validate_plan(plan):
    k8_delivery(plan)
    need(plan['identity_rule'] in K8_IDENTITY_RULES,'IDENTITY_RULE_INVALID')
    validate_chain(plan['days_parent'],K8_K9_DAYS,open_root=None,receives_entry=False)
    need(all(k8_root_controlled(row) for row in plan['days_parent']),'K9_CHAIN_NOT_ROOT_CONTROLLED')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    delivery=k8_delivery(plan);day=plan['day'];scope=delivery['scope']
    return {'operation':OPERATION,'epoch':K8_EPOCH,'day':day,'eve':{'not_before':K8_EVES[day]+K8_EVE_FROM,'not_after':day+K8_EVE_UNTIL},
            'windows':list(plan['windows']),
            'capacity_tree':{'path':K8_CAPACITY_ROOT,'parent':K8_VAR_LIB,'roots':{root:K8_CAPACITY_ROOT+'/'+root for root in K8_CAPACITY_ROOTS},
                             'required':'EXISTING_DIRECTORY_NOT_A_LINK_UID_0_GID_0_MODE_0700_HELD_UNCHANGED','container_path':K8_CONTAINER_CAPACITY},
            'files':[{'key':key,'path':k8_path(root,name),'sha256':sha(delivery['raws'][key]),'bytes':len(delivery['raws'][key]),
                      'mode_octal':'%04o'%K8_FILE_MODE,'uid':0,'gid':0,'links':1,'expect':'ABSENT'} for key,root,name in delivery['layout']],
            'contract':{'sha256':sha(delivery['contract_raw']),'bytes':len(delivery['contract_raw']),'written_as_its_own_file':False,
                        'carried_whole_into':k8_path('payload',k8_payload_name(day))},
            'payload':{'path':k8_path('payload',k8_payload_name(day)),'mode_octal':'%04o'%K8_FILE_MODE,'uid':0,'gid':0,'links':1,'expect':'ABSENT',
                       'bytes':'CANONICAL_JSON_OF_CONTRACT_AND_CAUSAL_ASSEMBLED_ON_THE_HOST',
                       'causal_members':['commitment_sha256','epoch','list_sha256','session','status','symbols'],
                       'hash_and_size':'NOT_SIGNED_NOT_REPORTED_A_COMMITMENT_TO_THE_LIST'},
            'causal_scope':{'commitment_sha256':scope['commitment_sha256'],'list_sha256':scope['list_sha256']},
            'k9_inputs':{'days_parent':chain_effects(plan['days_parent']),'day_directory':K8_K9_DAYS+'/'+day,
                         'commit_receipt':K8_K9_DAYS+'/'+day+'/'+K8_RECEIPTS+'/'+K8_COMMIT_RECEIPT,
                         'commitment':K8_K9_DAYS+'/'+day+'/'+K8_CAUSAL+'/'+K8_COMMITMENT,'audit_receipt':K8_K9_DAYS+'/'+day+'/'+K8_CAUSAL+'/'+K8_AUDIT,
                         'commit_attempt_key':k8_commit_key(day),'required':'COMPLETE_RECEIPT_OF_THIS_STEP_NAMING_BOTH_FILES_BY_SHA256'},
            'chain_documents':{role:{'path':k8_path('documents',pin['file']),'sha256':pin['sha256'],'required':'PRESENT_ROOT_0600_THESE_BYTES'}
                               for role,pin in delivery['chain'].items()},
            'root_identities':{'rule':plan['identity_rule'],'pinned':{root:delivery['roots'][root]['identity'] for root in K8_IDENTITY_ROOTS}},
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'pre_existing_objects_modified':False,'secret_written':False,'activation':False,'container_touched':False,'process_started':False,
            'symbols_in_receipt':False}
def success_of(plan):return COMPLETE_OUTCOME


# ---------------------------------------------------------------- the core's create_file for names with "=" (derived, tests/k8copy.py)
def k8_create_file(index,key,path,content,mode,directory,host,gate,state,go16):
    """The core's create_file (parts/files.py of generation 4c24c5cf...) for the capacity loader's names, which hold
    an '=' that the core's FILE_NAME refuses. Derived mechanically (tests/k8copy.py): this docstring, k8_named_in for
    named_in, and nine local names prefixed k8. Same states, codes, calls and order as the core's function."""
    k8entry={'key':key,'path':path,'state':'NOT_ATTEMPTED','code':None,'errno':None,'bytes':None,
           'sha256_signed':sha(content) if type(content) is bytes else None,'sha256_observed':None,'mode_octal':None,'uid':None,'gid':None,'links':None,
           'device':None,'inode':None,'temporary_name':None,'temporary_removed':False,'temporary_removal_code':None,
           'temporary_removal_errno':None,'fsync_file':False,'fsync_directory_after_link':False,'fsync_directory_after_removal':False}
    def k8failed(code,error=None,**more):
        k8entry.update(code=code,**more)
        if error is not None:k8entry['errno']=number(error)
        return k8entry
    def k8withdrawn(code,error=None):
        """A failure before the final name exists (never the expiry and replaced-directory paths, which do not come
        here): the temporary of this run is k8withdrawn by the same gated removal as after the link, relative to the
        descriptor held, and only if the name still shows the file's descriptor. Otherwise it stays, labelled."""
        k8failed(code,error)
        k8entry['temporary_removal_code']=remove_own_temporary(k8temp,fd,directory,host,gate,state,k8entry)
        if k8entry['temporary_removed']:k8entry['state']='NOT_CREATED'
        return k8entry
    if not (type(content) is bytes and 0<len(content)<=MAX_FILE_BYTES and type(mode) is int and mode in FILE_MODES
            and k8_named_in(path,directory) and text(go16,'[0-9a-f]{16}') and integer(index,0,99)):return k8failed('FILE_REQUEST_INVALID')
    name=PurePosixPath(path).name;k8temp=k8entry['temporary_name']=TEMPORARY%(go16,index)
    try:directory.verify(gate)
    except Refused as error:return k8failed(code_of(error,'PARENT_REPLACED'))
    k8flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC
    try:fd=mutate(state,gate,lambda:host.create(k8temp,k8flags,mode,directory.fd))
    except Refused as error:return k8failed(code_of(error,'GO_EXPIRED'))
    except OSError as error:
        return k8failed('TEMPORARY_NAME_OCCUPIED' if error.errno==errno.EEXIST else filesystem_code(error),error,state='NOT_CREATED')
    k8entry['state']='TEMPORARY_ONLY'
    try:
        k8written=0
        try:
            while k8written<len(content):
                k8size=mutate(state,gate,lambda:host.write(fd,content[k8written:k8written+65536]))
                if type(k8size) is not int or k8size<=0:return k8withdrawn('WRITE_INCOMPLETE')
                k8written+=k8size
        except Refused as error:return k8failed(code_of(error,'GO_EXPIRED'))
        except OSError as error:return k8withdrawn(filesystem_code(error),error)
        k8entry['bytes']=k8written
        try:host.fsync(fd);k8entry['fsync_file']=True
        except OSError as error:return k8withdrawn('FSYNC_FAILED',error)
        try:
            k8info=host.fstat(fd)
            k8entry.update(mode_octal='%04o'%stat.S_IMODE(k8info.st_mode),uid=k8info.st_uid,gid=k8info.st_gid,links=k8info.st_nlink,
                         device=k8info.st_dev,inode=k8info.st_ino)
            if not (stat.S_ISREG(k8info.st_mode) and k8info.st_nlink==1 and k8info.st_uid==0 and k8info.st_gid==0
                    and stat.S_IMODE(k8info.st_mode)==mode and k8info.st_size==len(content)
                    and k8info.st_dev==directory.identity[0]):return k8withdrawn('CREATED_METADATA_MISMATCH')
        except OSError as error:return k8withdrawn('CREATED_STAT_FAILED',error)
        try:directory.verify(gate)
        except Refused as error:return k8failed(code_of(error,'PARENT_REPLACED'))
        # link() acts on the name, not on the descriptor held: the name is looked at again right before it. A swap
        # after this lstat is not excluded; it is caught after the link (TEMPORARY_REPLACED, in-run readback).
        try:
            gate();k8named=host.lstat(k8temp,directory.fd)
            if (k8named.st_dev,k8named.st_ino,k8named.st_nlink)!=(k8info.st_dev,k8info.st_ino,1):return k8failed('TEMPORARY_REPLACED')
        except Refused as error:return k8failed(code_of(error,'GO_EXPIRED'))
        except OSError as error:return k8failed('TEMPORARY_REPLACED',error)
        # Complete, fsynced bytes are the only thing that ever appears under the final name.
        try:mutate(state,gate,lambda:host.link(k8temp,name,directory.fd))
        except Refused as error:return k8failed(code_of(error,'GO_EXPIRED'))
        except OSError as error:
            if error.errno!=errno.EEXIST:return k8withdrawn(filesystem_code(error),error)
            # Something took the name after the precheck. It is not touched; only this run's own temporary is k8withdrawn.
            k8failed('DESTINATION_APPEARED_AFTER_PRECHECK',error)
            k8entry['temporary_removal_code']=remove_own_temporary(k8temp,fd,directory,host,gate,state,k8entry)
            if k8entry['temporary_removed']:k8entry['state']='NOT_CREATED'
            return k8entry
        k8entry['state']='LINKED_TEMPORARY_PRESENT'
        try:host.fsync(directory.fd);k8entry['fsync_directory_after_link']=True
        except OSError as error:return k8failed('FSYNC_FAILED',error)
        code=k8entry['temporary_removal_code']=remove_own_temporary(k8temp,fd,directory,host,gate,state,k8entry)
        if k8entry['temporary_removed']:k8entry['state']='INSTALLED_NOT_DURABLE'
        if code is not None:return k8failed(code,errno=k8entry['temporary_removal_errno'])
        try:k8entry['links']=host.fstat(fd).st_nlink
        except OSError as error:return k8failed('CREATED_STAT_FAILED',error)
        if k8entry['links']!=1:return k8failed('CREATED_METADATA_MISMATCH')
        k8entry['state']='INSTALLED_DURABLE';return k8entry
    finally:
        try:host.close(fd)
        except Exception:pass



# ---------------------------------------------------------------- the host: held directories and private files
def k8_entry(host,name,parent,gate):
    """One lstat of a plain name in a held parent; no link is followed. None when the name does not exist."""
    gate()
    try:info=host.lstat(name,parent.fd)
    except FileNotFoundError:return None
    return {'type':kind(info.st_mode),'uid':info.st_uid,'gid':info.st_gid,'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),'links':info.st_nlink,
            'device':info.st_dev,'inode':info.st_ino}

def k8_hold(host,name,parent,gate,codes,seen):
    """An existing directory that must be a real directory, root:root, mode 0700 exactly: looked at by lstat, opened by
    the held parent without following a link, and held; the descriptor must be the object the lstat saw. codes =
    (absent, not as required, changed between the two). Returns the Pinned child."""
    found=k8_entry(host,name,parent,gate);seen[name]=found
    need(found is not None,codes[0])
    need(found['type']=='dir' and (found['uid'],found['gid'],found['mode_octal'])==(0,0,'%04o'%K8_DIRECTORY_MODE),codes[1])
    gate()
    try:fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=parent.fd)
    except OSError:raise Refused(codes[2]) from None
    try:held=Pinned(host,fd,parent=parent,name=name)
    except BaseException:
        host.close(fd);raise
    if held.identity!=(found['device'],found['inode'],0,0,K8_DIRECTORY_MODE):
        held.close();raise Refused(codes[2])
    return held

def k8_read(host,name,parent,gate,limit,codes,seen):
    """The bytes of an existing private file of a held directory: a regular file, root:root, mode 0600, one link, read
    by descriptor without following a link and unchanged during the read. codes = (absent, not as required)."""
    found=k8_entry(host,name,parent,gate);seen[name]=found
    need(found is not None,codes[0])
    need(found['type']=='file' and (found['uid'],found['gid'],found['mode_octal'],found['links'])==(0,0,'%04o'%K8_FILE_MODE,1),codes[1])
    raw,info=read_regular(host,name,parent.fd,gate,limit)
    need((info.st_dev,info.st_ino)==(found['device'],found['inode']) and info.st_uid==0 and info.st_gid==0
         and stat.S_IMODE(info.st_mode)==K8_FILE_MODE and info.st_nlink==1,codes[1])
    return raw

def k8_commit_outputs(raw,day):
    """The day's commit receipt (K9_STEP_RECEIPT_V1, the member set K9R and the runner use): COMPLETE, of this epoch,
    day, phase, operation and Act B key, of the pinned package and revision, naming both files of Dd/causal by hash."""
    try:receipt=strict(raw,K8_RECEIPT_MAX_BYTES)
    except Refused:raise Refused('COMMIT_RECEIPT_INVALID') from None
    need(type(receipt) is dict and set(receipt)==K8_STEP_RECEIPT_KEYS and receipt['schema']=='K9_STEP_RECEIPT_V1','COMMIT_RECEIPT_INVALID')
    need(receipt['status']=='COMPLETE' and receipt['code'] is None,'COMMIT_RECEIPT_NOT_COMPLETE')
    need((receipt['epoch'],receipt['day'],receipt['phase'],receipt['operation'],receipt['attempt_key'])==
         (K8_EPOCH,day,'causal_list','commit_launch',k8_commit_key(day)),'COMMIT_RECEIPT_NOT_OF_THIS_STEP')
    need((receipt['package_sha256'],receipt['build_sha'])==(K8_PACKAGE,K8_REVISION),'COMMIT_RECEIPT_NOT_OF_THIS_PACKAGE')
    outputs=receipt['outputs']
    need(type(outputs) is dict and all(hexpin(outputs.get(key)) for key in K8_COMMIT_OUTPUTS),'COMMIT_RECEIPT_WITHOUT_THE_COMMITMENT')
    return outputs

def k8_causal(commitment_raw,audit_raw,outputs,day,scope):
    """The causal object of the payload file, from the commitment the commit step left: its bytes and those of its audit
    receipt are the ones the commit receipt names; it is of this epoch and day; its list is a list of distinct names of
    the producer's grammar, at most the capacity, whose digest it carries; its digest and its list's digest are the
    contract's causal scope; the audit receipt is the build event of exactly this commitment. Pure."""
    need(sha(commitment_raw)==outputs[K8_COMMIT_OUTPUTS[0]] and sha(audit_raw)==outputs[K8_COMMIT_OUTPUTS[1]],'COMMITMENT_NOT_THE_COMMIT_RECEIPT_OUTPUT')
    commitment=k8_json(commitment_raw,K8_COMMITMENT_MAX_BYTES,'COMMITMENT_INVALID')
    need(commitment.get('schema')==K8_COMMITMENT_SCHEMA,'COMMITMENT_INVALID')
    need(commitment.get('epoch')==K8_EPOCH and commitment.get('session')==day,'COMMITMENT_NOT_OF_THIS_DAY')
    names=commitment.get('list')
    need(type(names) is list and len(names)<=K8_CAPACITY and all(text(name,K8_SYMBOL) for name in names) and len(set(names))==len(names),
         'COMMITMENT_LIST_INVALID')
    list_sha=sha(canonical(names));commitment_sha=sha(commitment_raw)
    need(commitment.get('list_sha256')==list_sha,'COMMITMENT_LIST_INVALID')
    need(commitment_sha==scope['commitment_sha256'],'COMMITMENT_NOT_THE_CONTRACT_SCOPE')
    need(list_sha==scope['list_sha256'],'LIST_NOT_THE_CONTRACT_SCOPE')
    audit=k8_json(audit_raw,K8_AUDIT_MAX_BYTES,'AUDIT_RECEIPT_NOT_BOUND')
    payload=audit.get('payload')
    need(set(audit)==K8_AUDIT_KEYS and audit['event_type']==K8_BUILT_EVENT and audit['occurred_at']==commitment.get('built_at')
         and type(payload) is dict and payload.get('commitment_sha256')==commitment_sha and payload.get('list_sha256')==list_sha
         and payload.get('epoch')==K8_EPOCH and payload.get('session')==day,'AUDIT_RECEIPT_NOT_BOUND')
    return {'epoch':K8_EPOCH,'session':day,'status':'AVAILABLE','symbols':names,'list_sha256':list_sha,'commitment_sha256':commitment_sha}

def k8_identity(capacity,held):
    """The AnchoredRoot identity a container computes for /c3po-capacity/<root> when the tree is bound at /c3po-capacity:
    the digest of [[name, device, inode], ...] of the components below '/', with the host's numbers (a bind mount shows
    the device and inode of its source; unverified on the host, hence the signed rule)."""
    return sha(canonical([[K8_CAPACITY_NAME,capacity.identity[0],capacity.identity[1]],[held.name,held.identity[0],held.identity[1]]]))

def k8_withheld(row):
    """The ledger row of the payload file without what would commit to the list: no hash, no size."""
    return dict(row,bytes=None,sha256_signed=None,sha256_observed=None,hash_and_size_withheld=True)

def _reduce_precheck(receipt):receipt['precheck']={'reduced_for_size':True}
def _reduce_parent(receipt):receipt['parent']=len(receipt.get('parent') or [])
REDUCTIONS=[('PRECHECK_DROPPED',_reduce_precheck),('PARENT_REDUCED_TO_COUNT',_reduce_parent)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    delivery=k8_delivery(plan)                                 # pure: the signed bytes that will be written, and no others
    day=plan['day'];layout=delivery['layout'];payload_name=k8_payload_name(day)
    start,end=instant(plan['window']['not_before']),instant(plan['window']['expires_at'])
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    detail={'parent':[],'precheck':{'capacity':{},'k9':{},'chain':{},'destinations_present':[],'identities_equal':{}}}
    ledger=[];held={};pinned=[];go16=bound['go_sha256'][:16];summary={'list_empty':None}
    def finish(status,outcome,code,extra):
        rows=[k8_withheld(row) if row['key']=='payload' else row for row in ledger]
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),
            clock=timing(begun,mark,clock,monotonic),mutating_calls=state.counts(),parent=detail['parent'],precheck=detail['precheck'],
            ledger=rows,objects_left_by_this_run=objects_left([],ledger),pre_existing_objects_modified=False,**extra)))
    try:
        # ---- everything is looked at before the first creation
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            need(instant(K8_EVES[day]+K8_EVE_FROM)<=start and end<=instant(day+K8_EVE_UNTIL),'WINDOW_NOT_IN_THE_EVE_OF_THE_DAY')
            host.umask(0o077)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            days=Pinned(host,walk_pinned(host,plan['days_parent'],gate,detail['parent']),rows=plan['days_parent']);pinned.append(days)
            var_lib=Pinned(host,walk_pinned(host,plan['days_parent'][:3],gate,[]),rows=plan['days_parent'][:3]);pinned.append(var_lib)
            # the capacity tree: the root and its four roots, each root:root 0700, held to the end
            capacity=k8_hold(host,K8_CAPACITY_NAME,var_lib,gate,('CAPACITY_DIRECTORY_ABSENT','CAPACITY_DIRECTORY_NOT_PRIVATE',
                             'CAPACITY_DIRECTORY_CHANGED_DURING_PRECHECK'),detail['precheck']['capacity']);held['capacity']=capacity
            for root in K8_CAPACITY_ROOTS:
                held[root]=k8_hold(host,root,capacity,gate,('CAPACITY_DIRECTORY_ABSENT','CAPACITY_DIRECTORY_NOT_PRIVATE',
                                   'CAPACITY_DIRECTORY_CHANGED_DURING_PRECHECK'),detail['precheck']['capacity'])
            # the day's K9 directory and what the commit step left in it, by fixed path
            k9=('K9_DIRECTORY_ABSENT','K9_DIRECTORY_NOT_PRIVATE','K9_DIRECTORY_CHANGED_DURING_PRECHECK')
            held['day']=k8_hold(host,day,days,gate,k9,detail['precheck']['k9'])
            held['receipts']=k8_hold(host,K8_RECEIPTS,held['day'],gate,k9,detail['precheck']['k9'])
            held['causal']=k8_hold(host,K8_CAUSAL,held['day'],gate,k9,detail['precheck']['k9'])
            outputs=k8_commit_outputs(k8_read(host,K8_COMMIT_RECEIPT,held['receipts'],gate,K8_RECEIPT_MAX_BYTES,
                                              ('COMMIT_RECEIPT_ABSENT','K9_FILE_NOT_PRIVATE'),detail['precheck']['k9']),day)
            commitment_raw=k8_read(host,K8_COMMITMENT,held['causal'],gate,K8_COMMITMENT_MAX_BYTES,('COMMITMENT_ABSENT','K9_FILE_NOT_PRIVATE'),
                                   detail['precheck']['k9'])
            audit_raw=k8_read(host,K8_AUDIT,held['causal'],gate,K8_AUDIT_MAX_BYTES,('COMMITMENT_ABSENT','K9_FILE_NOT_PRIVATE'),detail['precheck']['k9'])
            causal=k8_causal(commitment_raw,audit_raw,outputs,day,delivery['scope'])
            summary['list_empty']=not causal['symbols']
            # at most 40960 bytes of contract and 550 names of at most 20 characters: far below MAX_FILE_BYTES, which
            # k8_create_file enforces again (FILE_REQUEST_INVALID) before anything is created
            payload=canonical({'contract':delivery['contract'],'causal':causal})
            commitment_raw=audit_raw=None
            # the seven chain documents every config pins: present in documents, private, with the pinned bytes
            for role,pin in sorted(delivery['chain'].items()):
                raw=k8_read(host,pin['file'],held['documents'],gate,K8_CHAIN_MAX_BYTES,('CHAIN_DOCUMENT_ABSENT','CHAIN_DOCUMENT_NOT_PRIVATE'),
                            detail['precheck']['chain'])
                need(sha(raw)==pin['sha256'],'CHAIN_DOCUMENT_NOT_AS_PINNED')
            # every name this run creates is absent (all looked at, then one refusal naming them)
            for key,root,name in layout+[('payload','payload',payload_name)]:
                if k8_entry(host,name,held[root],gate) is not None:detail['precheck']['destinations_present'].append(key)
            need(not detail['precheck']['destinations_present'],'DESTINATION_PRESENT')
            for root in K8_IDENTITY_ROOTS:
                detail['precheck']['identities_equal'][root]=k8_identity(capacity,held[root])==delivery['roots'][root]['identity']
            need(plan['identity_rule']=='REPORT_ONLY' or all(detail['precheck']['identities_equal'].values()),'CAPACITY_ROOT_IDENTITY_NOT_THE_CONFIG')
            free=free_bytes(host,held['payload'].fd);detail['precheck']['free_bytes']=free
            need(free>=K8_FREE_BYTES_FLOOR,'CAPACITY_FREE_SPACE_BELOW_FLOOR')
            # the last refusal that costs nothing on the host: the time the creations and the readback may take
            left=gate();detail['precheck']['seconds_left_before_first_effect']=int(left)
            need(left>=K8_WRITE_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK','delivered':None})
        # ---- from here on nothing refuses unless nothing has changed
        stop=None;table=[(key,root,name,delivery['raws'][key]) for key,root,name in layout]+[('payload','payload',payload_name,payload)]
        for index,(key,root,name,content) in enumerate(table):
            if stop is not None:
                ledger.append({'key':key,'path':k8_path(root,name),'state':'NOT_ATTEMPTED','code':None});continue
            row=k8_create_file(index,key,k8_path(root,name),content,K8_FILE_MODE,held[root],host,gate,state,go16);ledger.append(row)
            if row['state']!='INSTALLED_DURABLE':stop=row['code'] or 'INSTALL_FAILED'
        # ---- the readback inside the run: every file through a descriptor, every held directory proved again
        for (key,root,name,content),row in zip(table,ledger):
            if stop is None:stop=readback_file(row,content,K8_FILE_MODE,held[root],host,gate)
        for key in ('capacity',)+K8_CAPACITY_ROOTS+('day','causal','receipts'):
            if stop is None:
                try:held[key].verify(gate)
                except Exception as error:stop=code_of(error,'READBACK_UNAVAILABLE')
        # (the two pinned chains need no walk of their own here: the capacity root's verify walks /var/lib's rows and the
        # day directory's walks the rows to days)
        delivered=None
        if stop is None:
            files={row['key']:{'path':row['path'],'sha256':row['sha256_observed'],'bytes':row['bytes'],'mode_octal':row['mode_octal'],'uid':row['uid'],
                               'gid':row['gid'],'links':row['links']} for row in ledger[:-1]}
            last=ledger[-1]
            delivered={'epoch':K8_EPOCH,'day':day,'windows':list(plan['windows']),'files':files,
                       'contract':{'sha256':sha(delivery['contract_raw']),'carried_whole_into_the_payload_file':True},
                       'payload':{'path':last['path'],'mode_octal':last['mode_octal'],'uid':last['uid'],'gid':last['gid'],'links':last['links'],
                                  'bytes_equal_the_assembled_bytes':True,'hash_and_size_withheld':True},
                       'causal':{'commitment_is_the_commit_receipt_output':True,'commitment_and_list_are_the_contract_causal_scope':True,
                                 'list_empty':summary['list_empty']},
                       'root_identities_equal_the_config':dict(detail['precheck']['identities_equal']),'identity_rule':plan['identity_rule']}
        extra={'phase_reached':'EFFECTS','readback':'COMPLETE' if stop is None else None,'delivered':delivered}
        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        # REFUSED only while no mutating call succeeded and none is uncertain; otherwise the run is a partial.
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)
    finally:
        for key in ('causal','receipts','day')+tuple(reversed(K8_CAPACITY_ROOTS))+('capacity',):
            if key in held:
                try:held[key].close()
                except Exception:pass
        for handle in pinned:
            try:handle.close()
            except Exception:pass
