import base64

OPERATION='GO_WRITE_HOSTOPS02_K12_PREFLIGHT_01'
PHASE='WRITE_K12_CAPACITY_WRITER_PREFLIGHT_DISPATCH_LAYOUT'
REQUEST_SCHEMA='WRITE_HOSTOPS02_K12_PREFLIGHT_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_K12_PREFLIGHT_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_K12_PREFLIGHT_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_K12_PREFLIGHT_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_K12_PREFLIGHT_PLAN_V1'
SOURCE_NAME='k12_preflight.py'
# A WRITE program (Codex, #429 5985748037): its own claim file, created exclusively before the run, and closed effects on
# the manifests directory. The writer's --preflight writes nothing (manifest_writer.py aeda5b12..., _preflight: a
# read-only open, fstat, access(W_OK|X_OK), fstatvfs, listings; no open with O_CREAT, write, link or unlink is reachable
# from run() with --preflight), but it REFUSES a read-only bind: _writable requires access W_OK and a filesystem without
# ST_RDONLY (MANIFEST_DIRECTORY_NOT_WRITABLE), so the read-only alternative would make the dispatch's own preflight fail
# by construction. The manifests directory is therefore bound read-write as in the dispatch, and this source proves it
# closed: the lstat signature of every entry and the fstat signature of the directory equal before and after the run.
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False
DATE_CLASS='WRITE_SESSIONS'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
EVIDENCE_OPERATIONS=('GO_READONLY_HOSTOPS02_K12_COLLECT_01',)
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='K12_PREFLIGHT_OK_IN_THE_DISPATCH_LAYOUT'
PARTIAL_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
PLAN_KEYS=frozenset(('capacity_request','parent_rows','evidence_boot_id_sha256'))
P_CLAIM_SCHEMA='K12_PREFLIGHT_CLAIM_V1'

# ---- K12 COMMON BEGIN (written by ../common_block.py; the same bytes in k12_window, k12_collect, k12_preflight) ----
# Epoch, days and the D6 clock of A2 rev3 section 7 (views 07:45:00, 08:45:00 and 09:45:00 BRT, valid 10 s; cutoff
# 10:20 BRT = 09:20 New York). The capacity days are Tuesday to Friday: A2 section 7 puts nothing of capacity on Monday.
# A window's SLOT is 1, 2 or 3 (primary, contingency 1, contingency 2): the documents tool's window_index + 1 (it counts
# from 0, capacity_day_documents.py view_schedule/enumerate). Names, views and receipts of this family use the slot.
K12_EPOCH='R2D2-V2-SHADOW-2026-10-05'
K12_DAYS=('2026-10-06','2026-10-07','2026-10-08','2026-10-09')
K12_VIEW_UTC={1:'10:45:00',2:'11:45:00',3:'12:45:00'}
K12_CUTOFF_UTC='13:20:00'
K12_VIEW_SECONDS=10
K12_MAX_WAIT_SECONDS=900
K12_MAX_START_SECONDS=900
# Placement on the host (E2 provision of 2026-10-03, request once-e2-20261003-b; CAP README "What the host payload must
# provide"; pins.env and the docker CLI directory as A1/K4 place them). The capacity tree is bound at its top-level
# container path; the manifests directory at the same path inside; the receipts directory is never bound.
# Codex, #429 5985748037 (6): every bind source and every one of its ancestors is controlled by root alone (uid 0,
# gid 0, not writable by group or other, no setgid, no link: k12_root_chain on signed rows). ONE named exception
# (Codex, #429 5986698996, this epoch only): the legacy data volume /mnt/day-d-data (uid 1000) bound READ-ONLY at
# /app/day-d-data, exactly, to read the release M1 installed (K12_RELEASE_DIR/K12_RELEASE_FILE); its ancestors are
# root-controlled, it is a mount point, and the release directory in it is root:root 0700 (k12_data_chain). The
# release's bytes are hashed against the REQUEST's release_sha256 before every use and again after it (k12_release).
# The epoch's source root /var/lib/c3po/r2d2-v2-source-20261005 is never bound (the writer reads no source directory,
# CAP:109).
K12_CAPACITY_ROOT='/var/lib/c3po-capacity'
K12_CONFIG_ROOT=K12_CAPACITY_ROOT+'/config'
K12_CAPACITY_TARGET='/c3po-capacity'
K12_CONFIG_TARGET=K12_CAPACITY_TARGET+'/config'
K12_DATA_VOLUME='/mnt/day-d-data'
K12_DATA_TARGET='/app/day-d-data'
K12_RELEASE_DIR=K12_DATA_VOLUME+'/r2d2-v2-release-20261005'
K12_RELEASE_FILE='release.CERTIFIED.json'
K12_RELEASE_MAX_BYTES=1048576
K12_SOURCE_ROOT='/var/lib/c3po/r2d2-v2-source-20261005'
K12_BAR_CONFIG='/etc/c3po-bar'
K12_MANIFESTS=K12_BAR_CONFIG+'/manifests'
K12_READER_CONFIG='/etc/c3po-reader'
K12_SECRET_ENV=K12_READER_CONFIG+'/secret.env'
K12_PINS_ENV=K12_READER_CONFIG+'/pins.env'
K12_DOCKER_CLI=K12_READER_CONFIG+'/docker-cli'
K12_READER_STATE='/var/lib/c3po-reader'
K12_RECEIPTS=K12_READER_STATE+'/capacity-receipts'
K12_JOURNAL_FORBIDDEN=(K12_DATA_VOLUME,K12_CAPACITY_ROOT,K12_BAR_CONFIG,K12_READER_CONFIG,K12_READER_STATE,K12_SOURCE_ROOT)
K12_WRITER_STEM='manifest_writer-'
K12_WRITER_MAX_BYTES=131072
K12_CONFIG_MAX_BYTES=65536
K12_PINS_MAX_BYTES=8192
K12_REQUEST_MAX_BYTES=16384
K12_STDOUT_MAX_BYTES=16384
K12_PERSISTED_MAX_BYTES=32768
K12_MANIFEST_MAX_BYTES=65536
# The documents tool's REQUEST of one window (capacity_day_documents.py at 4a6f767, request_document) and the writer's
# line (manifest_writer.py aeda5b12..., main/execute).
K12_CAPACITY_REQUEST_SCHEMA='R2D2_CAPACITY_DAY_ONCE_REQUEST_V1'
K12_CAPACITY_OPERATION='GO_CAPACITY_DAY_03'
K12_REQUEST_KEYS=frozenset(('schema','status','operation','epoch','day','window','window_index','window_count','phases','mode','view_mode',
                            'image_id','build_sha','release_sha256','package_sha256','capacity_config_file','capacity_config_sha256','network',
                            'mounts','env_files','inline_env','docker_config','writer_sha256','writer_argv','transport_watchdog_seconds',
                            'not_before','latest_start','not_after','view_opens_at','view_valid_until','cutoff_at','documentary',
                            'authority_sha256','host_binding_sha256','executor_uid'))
K12_DOCUMENTARY_KEYS=frozenset(('act_b_sha256','template_record_sha256','template_sha256','admission_go_sha256','admission_go_record_sha256',
                                'bar_manifest_go_sha256','bar_manifest_go_record_sha256','publication_sha256','veto_view_sha256',
                                'contract_sha256','causal_commitment_sha256','causal_list_sha256'))
K12_WRITER_SCHEMA='R2D2_V2_BAR_MANIFEST_WRITER_RECEIPT_V1'
K12_WRITER_STATUSES={'PUBLISHED_VERIFIED':(0,),'ALREADY_PUBLISHED_VERIFIED':(0,),'MATCH_VERIFIED':(0,),'PREFLIGHT_OK':(0,),
                     'ABSENT':(3,),'REFUSED':(3,),'UNVERIFIED':(1,),'PUBLISHED_UNVERIFIED':(1,3)}
K12_WRITER_PUBLISHED=('PUBLISHED_VERIFIED','ALREADY_PUBLISHED_VERIFIED')
K12_WRITER_KEYS=frozenset(('schema','status','code','session','mode','epoch','owner_uid','release_sha256','capacity_config_sha256',
                           'package_sha256','build_sha','capacity_veto_mode','massive_bars_enabled','cutoff_at','stale_temporaries',
                           'repaired_temporaries','prepare_status','waited_seconds','view','go_sha256','go_mode','template_sha256','window',
                           'binding_sha256','symbol_count','manifest_sha256','published_at','file','checks','windows'))
K12_PREPARE_STATUSES=('ATTEMPTED','COMMITTED','ALREADY_COMMITTED','PRECOMMITTED')
K12_COMMITTED=('COMMITTED','ALREADY_COMMITTED','PRECOMMITTED')
K12_WRITER_CODE='[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+'
K12_INSTANT='[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}[+]00:00'
# The container: deterministic names, two labels, and the one inspect format of the family (never .Config.Env).
K12_LABEL_REQUEST='c3po.k12.request_sha256'
K12_LABEL_CAPACITY='c3po.k12.capacity_request_sha256'
K12_PERSISTED_SCHEMA='K12_PERSISTED_WRITER_RECEIPT_V1'
K12_PERSISTED_KEYS=frozenset(('schema','epoch','day','window','window_slot','container_id','container_name','launch_request_sha256',
                              'capacity_request_sha256','persist_request_sha256','image_id','exit_code','oom_killed','started_at',
                              'finished_at','stdout_b64','stdout_sha256','stdout_bytes'))
K12_FORMAT=('{"id":{{json .Id}},"name":{{json .Name}},"image_id":{{json .Image}},"state":{{json .State.Status}},'
            '"running":{{json .State.Running}},"exit_code":{{json .State.ExitCode}},"oom_killed":{{json .State.OOMKilled}},'
            '"started_at":{{json .State.StartedAt}},"finished_at":{{json .State.FinishedAt}},'
            '"request_label":{{json (index .Config.Labels "'+K12_LABEL_REQUEST+'")}},'
            '"capacity_label":{{json (index .Config.Labels "'+K12_LABEL_CAPACITY+'")}},'
            '"cmd":{{json .Config.Cmd}},"network_mode":{{json .HostConfig.NetworkMode}},"read_only_root":{{json .HostConfig.ReadonlyRootfs}},'
            '"auto_remove":{{json .HostConfig.AutoRemove}},"restart_policy":{{json .HostConfig.RestartPolicy.Name}},"mounts":{{json .Mounts}}}')
K12_INSPECT_KEYS=frozenset(('id','name','image_id','state','running','exit_code','oom_killed','started_at','finished_at','request_label',
                            'capacity_label','cmd','network_mode','read_only_root','auto_remove','restart_policy','mounts'))
K12_MOUNT_KEYS=frozenset(('Type','Name','Source','Destination','Driver','Mode','RW','Propagation'))
K12_NEVER_STARTED='0001-01-01T00:00:00Z'

def k12_compact(day):return day.replace('-','')
def k12_container_name(day,index):return 'c3po-k12-%s-w%d'%(k12_compact(day),index)
def k12_preflight_name(day):return 'c3po-k12-%s-preflight'%k12_compact(day)
def k12_persisted_name(day,index):return 'k12-%s-w%d.writer.json'%(day,index)
def k12_writer_name(digest):return K12_WRITER_STEM+digest+'.py'
def k12_at(day,clock):return '%sT%s+00:00'%(day,clock)

def k12_instant(value):
    """One instant of the REQUEST: exactly YYYY-MM-DDTHH:MM:SS+00:00 (what the documents tool writes)."""
    need(text(value,K12_INSTANT),'CAPACITY_REQUEST_INSTANT');return instant(value)

def k12_journal(mount):
    """The journal bind: a read-only bind of a host directory that is none of the others, contains none and lies in
    none of them, at a container path that is one component below '/' (CAP README, "The journal bind")."""
    source,target=mount['source'],mount['target']
    need(clean_path(source) and source!='/' and not any(inside(source,root) or inside(root,source) for root in K12_JOURNAL_FORBIDDEN)
         and text(target,'/[a-z0-9][a-z0-9._-]{0,62}') and target not in (K12_DATA_TARGET,K12_CAPACITY_TARGET,K12_MANIFESTS,'/app','/etc')
         and mount['readonly'] is True,'CAPACITY_REQUEST_JOURNAL')
    return {'source':source,'target':target}

def k12_data(mount):
    """The data bind (CAP:109, the release file read by the collector of --prepare-first): exactly the named exception,
    /mnt/day-d-data at /app/day-d-data, read-only (Codex #429 5986698996). Anything else is refused."""
    need(mount=={'source':K12_DATA_VOLUME,'target':K12_DATA_TARGET,'readonly':True},'CAPACITY_REQUEST_DATA_BIND')
    return {'source':K12_DATA_VOLUME,'target':K12_DATA_TARGET}

def k12_data_chain(rows):
    """Signed rows from '/' to the release directory in the data volume: every component outside the volume root
    controlled by root alone (uid 0 and no group or other write by validate_chain; gid 0 and no setgid here); the volume root may be another uid
    (the named exception) but not world-writable; the volume is a mount point; the release directory root:root 0700."""
    validate_chain(rows,K12_RELEASE_DIR,open_root=K12_DATA_VOLUME)
    need(all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows if not inside(row['path'],K12_DATA_VOLUME)),
         'CHAIN_NOT_ROOT_CONTROLLED')
    need(mount_point_of(rows)==K12_DATA_VOLUME,'DATA_VOLUME_NOT_A_MOUNT_POINT')
    need((rows[-1]['uid'],rows[-1]['gid'],rows[-1]['mode'])==(0,0,0o700),'RELEASE_DIRECTORY_NOT_ROOT_PRIVATE')
    return rows

def k12_release(host,held,gate,derived):
    """The release M1 installed, opened without following a link and hashed over the bytes read: root 0600 one link,
    SHA-256 = the REQUEST's release_sha256. Raises Refused. The bytes stay here."""
    raw,facts=k12_file(host,K12_RELEASE_FILE,held,gate,K12_RELEASE_MAX_BYTES)
    need(raw is not None,'RELEASE_ABSENT');need(k12_private(facts),'RELEASE_NOT_PRIVATE')
    need(sha(raw)==derived['release_sha256'],'RELEASE_NOT_THE_SIGNED_BYTES')
    return True

def k12_root_chain(rows,path):
    """Signed rows of a directory whose every component from '/' is controlled by root alone: uid 0 and not writable
    by group or other (validate_chain with no open root), and gid 0 and no setgid bit on every component (Codex 6).
    A link anywhere is refused by the walk itself (O_NOFOLLOW by dir_fd). Returns the rows."""
    validate_chain(rows,path)
    need(all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows),'CHAIN_NOT_ROOT_CONTROLLED')
    return rows

def k12_capacity_request(member):
    """The member {'b64','sha256'} of a plan: the documents tool's REQUEST of one window, carried byte for byte. Every
    value this family puts on the engine is derived here and nowhere else. Pure; raises Refused."""
    need(type(member) is dict and set(member)=={'b64','sha256'} and type(member['b64']) is str and hexpin(member['sha256']),'CAPACITY_REQUEST_INVALID')
    try:raw=base64.b64decode(member['b64'].encode('ascii'),validate=True)
    except (ValueError,UnicodeEncodeError):raise Refused('CAPACITY_REQUEST_INVALID') from None
    need(0<len(raw)<=K12_REQUEST_MAX_BYTES and sha(raw)==member['sha256'],'CAPACITY_REQUEST_NOT_THE_SIGNED_BYTES')
    try:request=document(raw)
    except Refused:raise Refused('CAPACITY_REQUEST_INVALID') from None
    exact(request,K12_REQUEST_KEYS,'CAPACITY_REQUEST_KEYS')
    need(request['schema']==K12_CAPACITY_REQUEST_SCHEMA and request['status']=='BOUND' and request['operation']==K12_CAPACITY_OPERATION
         and request['epoch']==K12_EPOCH and type(request['executor_uid']) is int and request['executor_uid']==0,'CAPACITY_REQUEST_IDENTITY')
    day=request['day'];need(type(day) is str and day in K12_DAYS,'CAPACITY_REQUEST_DAY')
    position,count=request['window_index'],request['window_count']
    need(text(request['window'],'[a-z][a-z0-9_]{0,31}') and integer(position,0,2) and integer(count,1,3) and position<count,'CAPACITY_REQUEST_WINDOW')
    index=position+1
    need(request['phases']==['admission','bar_manifest'] and request['mode']=='PREPARE_AND_PUBLISH'
         and request['view_mode'] in ('PRE_DELIVERED','IN_WINDOW'),'CAPACITY_REQUEST_MODE')
    need(text(request['image_id'],IMAGE_ID) and text(request['build_sha'],'[0-9a-f]{40}') and hexpin(request['release_sha256'])
         and hexpin(request['package_sha256']) and hexpin(request['capacity_config_sha256']) and hexpin(request['writer_sha256'])
         and hexpin(request['authority_sha256']) and hexpin(request['host_binding_sha256']),'CAPACITY_REQUEST_PINS')
    config='session=%s.%s.capacity.json'%(day,request['window'])
    need(request['capacity_config_file']==K12_CONFIG_TARGET+'/'+config,'CAPACITY_REQUEST_CONFIG_FILE')
    need(text(request['network'],'[A-Za-z0-9][A-Za-z0-9_.-]{0,62}') and request['network'] not in ('host','none','bridge','default'),
         'CAPACITY_REQUEST_NETWORK')
    files=request['env_files']
    need(type(files) is dict and set(files)=={'secret_path','pins'} and files['secret_path']==K12_SECRET_ENV and type(files['pins']) is dict
         and set(files['pins'])=={'path','sha256'} and files['pins']['path']==K12_PINS_ENV and hexpin(files['pins']['sha256']),'CAPACITY_REQUEST_ENV_FILES')
    need(request['inline_env']=={'C3PO_R2D2_V2_SHADOW_ENABLED':'true','C3PO_R2D2_V2_MASSIVE_BARS_ENABLED':'true',
                                 'C3PO_R2D2_V2_CAPACITY_CONFIG_FILE':request['capacity_config_file'],
                                 'C3PO_R2D2_V2_CAPACITY_CONFIG_SHA':request['capacity_config_sha256']},'CAPACITY_REQUEST_INLINE_ENV')
    need(request['docker_config']==K12_DOCKER_CLI,'CAPACITY_REQUEST_DOCKER_CONFIG')
    mounts=request['mounts']
    need(type(mounts) is list and len(mounts)==4 and all(type(item) is dict and set(item)=={'source','target','readonly'}
                                                        and type(item['readonly']) is bool for item in mounts),'CAPACITY_REQUEST_MOUNTS')
    fixed=[{'source':K12_CAPACITY_ROOT,'target':K12_CAPACITY_TARGET,'readonly':True},{'source':K12_MANIFESTS,'target':K12_MANIFESTS,'readonly':False}]
    others=[item for item in mounts if item not in fixed]
    datas=[item for item in others if item['target']==K12_DATA_TARGET];journals=[item for item in others if item['target']!=K12_DATA_TARGET]
    need(all(item in mounts for item in fixed) and len(datas)==1 and len(journals)==1,'CAPACITY_REQUEST_MOUNTS')
    k12_data(datas[0]);journal=k12_journal(journals[0])     # the journal lies neither in nor around the volume
    view=k12_at(day,K12_VIEW_UTC[index]);until=instant(view).timestamp()+K12_VIEW_SECONDS
    starts=k12_instant(request['not_before'])
    for key in ('latest_start','not_after','view_opens_at','view_valid_until','cutoff_at'):k12_instant(request[key])
    need(request['view_opens_at']==view and request['latest_start']==view and k12_instant(request['view_valid_until']).timestamp()==until
         and request['not_after']==request['view_valid_until'] and request['cutoff_at']==k12_at(day,K12_CUTOFF_UTC)
         and starts.date().isoformat()==day,'CAPACITY_REQUEST_CLOCK')
    given=request['writer_argv'];mode=None
    need(type(given) is list and len(given) in (9,11) and type(given[8]) is str and text(given[8],'[1-9][0-9]{0,2}')
         and int(given[8])<=K12_MAX_WAIT_SECONDS,'CAPACITY_REQUEST_WRITER_ARGV')
    wait=int(given[8])
    need(0<instant(view).timestamp()-starts.timestamp()<=min(wait,K12_MAX_START_SECONDS),'CAPACITY_REQUEST_CLOCK')
    argv=['--day',day,'--manifest-directory',K12_MANIFESTS,'--prepare-first','--view-opens-at',view,'--max-wait-seconds',str(wait)]
    if len(given)==11:mode=given[10];argv+=['--require-go-mode',mode]
    need(given==argv and mode in (None,'DELEGATED_ACT_B'),'CAPACITY_REQUEST_WRITER_ARGV')
    need(integer(request['transport_watchdog_seconds'],1,3600),'CAPACITY_REQUEST_WATCHDOG')
    documentary=request['documentary']
    need(type(documentary) is dict and set(documentary)==set(K12_DOCUMENTARY_KEYS) and all(hexpin(value) for value in documentary.values()),
         'CAPACITY_REQUEST_DOCUMENTARY')
    return raw,request,{'sha256':member['sha256'],'day':day,'window':request['window'],'index':index,'position':position,'count':count,'image_id':request['image_id'],
                        'build_sha':request['build_sha'],'network':request['network'],'mounts':[dict(item) for item in mounts],'journal':journal,
                        'config_name':config,'config_sha256':request['capacity_config_sha256'],'pins_sha256':files['pins']['sha256'],
                        'writer_sha256':request['writer_sha256'],'writer_argv':list(argv),'require_go_mode':mode,'not_before':request['not_before'],
                        'view_opens_at':view,'view_valid_until':request['view_valid_until'],'cutoff_at':request['cutoff_at'],
                        'release_sha256':request['release_sha256'],'package_sha256':request['package_sha256']}

def k12_mount_word(item):
    """--mount value of one bind of the REQUEST (the core's own grammar and form)."""
    return mount_argument({'source':item['source'],'target':item['target'],'read_only':item['readonly']})

def k12_container_words(derived,name,labels):
    """What follows a create or run row's fixed prefix: --name, the labels, --network, the two env files (the docker
    CLI reads them on the host; they are never mounted, opened or hashed here), the four inline values, the four binds
    in the REQUEST's order, the image ID, and the writer by its content-addressed path in the config root, with the
    REQUEST's argv. Every word is a value of the signed REQUEST or a compiled constant."""
    words=['--name',name]
    for key,value in labels:words+=['--label','%s=%s'%(key,value)]
    words+=['--network',derived['network'],'--env-file',K12_SECRET_ENV,'--env-file',K12_PINS_ENV,
            '--env','C3PO_R2D2_V2_SHADOW_ENABLED=true','--env','C3PO_R2D2_V2_MASSIVE_BARS_ENABLED=true',
            '--env','C3PO_R2D2_V2_CAPACITY_CONFIG_FILE='+K12_CONFIG_TARGET+'/'+derived['config_name'],
            '--env','C3PO_R2D2_V2_CAPACITY_CONFIG_SHA='+derived['config_sha256']]
    for item in derived['mounts']:words+=['--mount',k12_mount_word(item)]
    return words+[derived['image_id'],'python','-I','-B',K12_CONFIG_TARGET+'/'+k12_writer_name(derived['writer_sha256'])]+list(derived['writer_argv'])

def k12_expected_mounts(derived):
    """The mount list a container of this family must show in `docker inspect` (Type bind, RW the opposite of readonly)."""
    return sorted([{'source':item['source'],'destination':item['target'],'rw':not item['readonly']} for item in derived['mounts']],
                  key=lambda item:item['destination'])

def k12_inspect(raw):
    """One line of K12_FORMAT, member by member. Raises Refused('K12_INSPECT_INVALID')."""
    row=decode(raw)
    need(set(row)==set(K12_INSPECT_KEYS) and text(row['id'],CONTAINER_ID) and text(row['name'],'/'+CONTAINER_NAME) and text(row['image_id'],IMAGE_ID)
         and type(row['state']) is str and row['state'] in CONTAINER_STATES and type(row['running']) is bool and type(row['exit_code']) is int
         and type(row['oom_killed']) is bool and all(type(row[key]) is str and len(row[key])<=64 for key in ('started_at','finished_at'))
         and all(row[key] in (None,'') or hexpin(row[key]) for key in ('request_label','capacity_label'))
         and type(row['cmd']) is list and len(row['cmd'])<=64 and all(type(word) is str and len(word)<=8192 for word in row['cmd'])
         and type(row['network_mode']) is str and len(row['network_mode'])<=128 and type(row['read_only_root']) is bool
         and type(row['auto_remove']) is bool and type(row['restart_policy']) is str and len(row['restart_policy'])<=32
         and type(row['mounts']) is list and len(row['mounts'])<=16,'K12_INSPECT_INVALID')
    mounts=[]
    for item in row['mounts']:
        need(type(item) is dict and set(item)<=K12_MOUNT_KEYS and item.get('Type')=='bind' and type(item.get('Source')) is str
             and type(item.get('Destination')) is str and type(item.get('RW')) is bool,'K12_INSPECT_INVALID')
        mounts.append({'source':item['Source'],'destination':item['Destination'],'rw':item['RW']})
    row['mounts']=sorted(mounts,key=lambda item:item['destination']);return row

def k12_ours(row,derived,name,request_sha256):
    """True when the inspected container is the one this family created for that window and launch request: name,
    image, the two labels, the writer's argv and the binds of the REQUEST, the network, a read-only root, no --rm and
    no restart policy. A container that is not ours is never stopped, read for its output or removed."""
    return (row['name']=='/'+name and row['image_id']==derived['image_id'] and row['request_label']==request_sha256
            and row['capacity_label']==derived['sha256'] and row['network_mode']==derived['network'] and row['read_only_root'] is True
            and row['auto_remove'] is False and row['restart_policy'] in ('no','') and row['mounts']==k12_expected_mounts(derived)
            and row['cmd']==['python','-I','-B',K12_CONFIG_TARGET+'/'+k12_writer_name(derived['writer_sha256'])]+derived['writer_argv'])

def k12_writer_line(raw,day):
    """The writer's one line (README "Receipt"): exactly one JSON object on one line, its schema, a known status with its
    code, the session, and the type of every member this family copies or compares. Returns the object. Raises Refused."""
    need(type(raw) is bytes and 0<len(raw)<=K12_STDOUT_MAX_BYTES and raw.endswith(b'\n') and raw.count(b'\n')==1,'WRITER_LINE_NOT_ONE_LINE')
    try:raw.decode('ascii')
    except UnicodeDecodeError:raise Refused('WRITER_LINE_NOT_ASCII') from None
    try:line=strict(raw[:-1],K12_STDOUT_MAX_BYTES)
    except Refused:raise Refused('WRITER_LINE_INVALID') from None
    need(type(line) is dict and set(line)<=K12_WRITER_KEYS and {'schema','status','code','session','mode'}<=set(line)
         and line['schema']==K12_WRITER_SCHEMA and line['status'] in K12_WRITER_STATUSES,'WRITER_LINE_INVALID')
    need((line['code'] is None)==(line['status'] in ('PUBLISHED_VERIFIED','ALREADY_PUBLISHED_VERIFIED','MATCH_VERIFIED','PREFLIGHT_OK'))
         and (line['code'] is None or text(line['code'],K12_WRITER_CODE)),'WRITER_LINE_INVALID')
    need(line['session'] in (day,None) and line['mode'] in (None,'PUBLISH','VERIFY_ONLY','PREFLIGHT'),'WRITER_LINE_INVALID')
    for key in ('release_sha256','capacity_config_sha256','package_sha256','go_sha256','template_sha256','binding_sha256','manifest_sha256'):
        need(key not in line or hexpin(line[key]),'WRITER_LINE_INVALID')
    need(('owner_uid' not in line or integer(line['owner_uid'])) and ('build_sha' not in line or text(line['build_sha'],'[0-9a-f]{40}'))
         and ('prepare_status' not in line or line['prepare_status'] in K12_PREPARE_STATUSES)
         and ('go_mode' not in line or line['go_mode'] in ('DELEGATED_ACT_B','INDIVIDUAL'))
         and ('symbol_count' not in line or integer(line['symbol_count'],0,550))
         and all(key not in line or integer(line[key],0,4096) for key in ('stale_temporaries','repaired_temporaries'))
         and ('massive_bars_enabled' not in line or type(line['massive_bars_enabled']) is bool)
         and ('capacity_veto_mode' not in line or text(line['capacity_veto_mode'],'[A-Z][A-Z0-9_]{0,63}'))
         and ('waited_seconds' not in line or (type(line['waited_seconds']) in (int,float) and 0<=line['waited_seconds']<=1000))
         and all(key not in line or text(line[key],'[0-9T:.+-]{10,40}') for key in ('cutoff_at','published_at'))
         and all(key not in line or type(line[key]) is dict for key in ('view','window','file','checks','windows')),'WRITER_LINE_INVALID')
    return line

def k12_line_public(line):
    """What of the writer's line may leave the host (CAP README, "Private and public"): status, code, binding hash,
    prepare status, the GO it verified, the pins it loaded, counts of temporaries, clocks. Never the manifest hash or
    the symbol count (together an unsalted commitment to the list): only whether they were present."""
    keep=('status','code','session','mode','owner_uid','prepare_status','binding_sha256','go_sha256','go_mode','template_sha256',
          'release_sha256','capacity_config_sha256','package_sha256','build_sha','capacity_veto_mode','massive_bars_enabled',
          'stale_temporaries','repaired_temporaries','waited_seconds','published_at','cutoff_at')
    public={key:line[key] for key in keep if key in line}
    public.update(manifest_sha256_present='manifest_sha256' in line,symbol_count_present='symbol_count' in line)
    return public

def k12_persisted(raw,expected):
    """The persisted writer receipt (written by k12_window PERSIST): canonical JSON with exactly K12_PERSISTED_KEYS, its
    members equal to the expected ones, and the standard output it carries equal to its own hash and size. Returns
    (document, stdout bytes). Raises Refused('PERSISTED_RECEIPT_INVALID')."""
    try:value=document(raw)
    except Refused:raise Refused('PERSISTED_RECEIPT_INVALID') from None
    need(set(value)==set(K12_PERSISTED_KEYS) and value['schema']==K12_PERSISTED_SCHEMA
         and all(value[key]==expected[key] for key in expected),'PERSISTED_RECEIPT_INVALID')
    need(type(value['stdout_b64']) is str and hexpin(value['stdout_sha256']) and integer(value['stdout_bytes'],0,K12_STDOUT_MAX_BYTES)
         and type(value['exit_code']) is int and type(value['oom_killed']) is bool and text(value['container_id'],CONTAINER_ID)
         and hexpin(value['persist_request_sha256']),'PERSISTED_RECEIPT_INVALID')
    try:stdout=base64.b64decode(value['stdout_b64'].encode('ascii'),validate=True)
    except (ValueError,UnicodeEncodeError):raise Refused('PERSISTED_RECEIPT_INVALID') from None
    need(len(stdout)==value['stdout_bytes'] and sha(stdout)==value['stdout_sha256'],'PERSISTED_RECEIPT_INVALID')
    return value,stdout

def k12_entry(host,name,parent,gate):
    """One lstat of a plain name in a held directory; no link is followed. None when the name does not exist."""
    gate()
    try:info=host.lstat(name,parent.fd)
    except FileNotFoundError:return None
    return {'type':kind(info.st_mode),'uid':info.st_uid,'gid':info.st_gid,'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),'links':info.st_nlink}

def k12_file(host,name,parent,gate,limit):
    """(bytes, metadata) of one regular file of a held directory read without following a link, or (None, None) when
    the name does not exist. The bytes stay with the caller."""
    try:raw,info=read_regular(host,name,parent.fd,gate,limit)
    except FileNotFoundError:return None,None
    return raw,{'type':'file','uid':info.st_uid,'gid':info.st_gid,'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),'links':info.st_nlink}

def k12_private(facts):
    """A regular file of root:root, mode 0600, one link."""
    return facts is not None and facts['type']=='file' and (facts['uid'],facts['gid'],facts['mode_octal'],facts['links'])==(0,0,'0600',1)

def k12_line_of(value,stdout,day):
    """The writer's line from a persisted receipt, or (None, code) when it is not one valid line."""
    try:return k12_writer_line(stdout,day),None
    except Refused as error:return None,code_of(error,'WRITER_LINE_INVALID')

def k12_stopped(exit_code,oom_killed,finished,view):
    """The end of D4's stop (a veto): exit 143 or 137 (the signal of docker stop through docker-init), not OOM,
    finished before the view (the writer prints its line only at its own end, after the view)."""
    finished=finished if type(finished) is str else ''
    return (exit_code in (137,143) and oom_killed is False and text(finished[:19],'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}')
            and finished[:19]<view[:19])

def k12_receipt_line(stdout,day,exit_code):
    """PERSIST's strict reading of the logs (Codex 2): exactly one complete writer receipt, consistent with the exit code
    of the container (README status table), of this session and of a publish run. Raises Refused; truncated,
    duplicated or inconsistent output is never a receipt."""
    line=k12_writer_line(stdout,day)
    need(type(exit_code) is int and exit_code in K12_WRITER_STATUSES[line['status']] and line['session']==day and line['mode']=='PUBLISH',
         'WRITER_RECEIPT_INCONSISTENT')
    return line

def k12_ended(value,stdout,day,view):
    """How a window's container ended, from its persisted receipt: ('LINE', line) for one complete receipt consistent
    with the exit code (k12_receipt_line); ('STOPPED', None) for no output at all and the signature of D4's stop
    (k12_stopped), a veto, which holds for the whole day (ORD:17); ('UNKNOWN', code) for anything else: never a ground
    for another window. (PERSIST stores nothing but a complete receipt; the other cases are kept for a file that is
    not what PERSIST wrote.)"""
    try:return 'LINE',k12_receipt_line(stdout,day,value['exit_code'])
    except Refused as error:code=code_of(error,'WRITER_LINE_INVALID')
    if stdout==b'' and k12_stopped(value['exit_code'],value['oom_killed'],value['finished_at'],view):return 'STOPPED',None
    return 'UNKNOWN','ENDED_WITHOUT_A_LINE' if stdout==b'' else code

def k12_terminal(line):
    """'PUBLISHED' when the window published and verified (README outcome rule), 'EMPTY_LIST' for the empty monitored
    list with a committed binding (terminal for the day, D12), None otherwise. Its line is always one complete receipt
    of this day's publish run (k12_receipt_line), so neither None nor another mode reaches it."""
    if line['status'] in K12_WRITER_PUBLISHED:return 'PUBLISHED'
    if line['code']=='MANIFEST_SYMBOLS_EMPTY' and line.get('prepare_status') in K12_COMMITTED:return 'EMPTY_LIST'
    return None
# ---- K12 COMMON END ----

P_CHAINS=('config','manifests','reader_config','docker_cli','journal','data','receipts')
P_PATHS={'config':K12_CONFIG_ROOT,'manifests':K12_MANIFESTS,'reader_config':K12_READER_CONFIG,'docker_cli':K12_DOCKER_CLI,'receipts':K12_RECEIPTS,'data':K12_RELEASE_DIR}
P_ALLOWANCE_SECONDS=8                     # the claim file (4 s) before the run, and 4 s
def p_claim_name(day):return 'k12-%s-preflight.claim.json'%day
P_RUN_PREFIX=['run','--rm','--pull','never','--init','--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges']
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'the signed image ID','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          'preflight':command_row('docker',P_RUN_PREFIX,'--name, two --label, --network, two --env-file, four --env, the four --mount of the '
                                  'primary window\'s REQUEST, the signed image ID, python -I -B <the writer in the config root>, the REQUEST\'s '
                                  'writer argv and --preflight','RUN','EFFECT')}

SCOPE_STATEMENT=('One attached docker run --rm (--pull never, --init, --user 0:0, --read-only, --cap-drop ALL, no-new-privileges) named '
                 'c3po-k12-<yyyymmdd>-preflight, of epoch '+K12_EPOCH+', in the primary window\'s dispatch layout: the network, the two '
                 'environment files, the four inline values and the four binds ('+K12_DATA_VOLUME+' at '+K12_DATA_TARGET+', the journal and '
                 +K12_CAPACITY_ROOT+' read-only, '+K12_MANIFESTS+' read-write as the writer\'s preflight requires) of the documents tool '
                 'REQUEST the plan carries, every bind source and every ancestor of it controlled by root alone (uid 0, gid 0, no group '
                 'or other write, no setgid, no link) except the named read-only data volume (Codex #429 5986698996; the release file '
                 'hashed against the REQUEST before the run and again after it), running python -I -B on the writer '
                 'delivered by hash in '+K12_CONFIG_ROOT+' with that REQUEST\'s argv and --preflight, before that window starts. Before '
                 'the run, one claim file k12-<day>-preflight.claim.json (root:root 0600, exclusive creation, fsync, read back) in '
                 +K12_RECEIPTS+': one preflight per day. Closed effects on the manifests directory: the container is proved gone and '
                 'every entry of the directory and the directory itself unchanged afterwards (lstat/fstat signatures). Nothing else is '
                 'created, changed or removed by this process; secret.env is never opened; the environment of a container is never printed.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,'epoch':K12_EPOCH,'days':list(K12_DAYS),
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'run_prefix':P_RUN_PREFIX,
       'placement':{'capacity_root':K12_CAPACITY_ROOT,'config_root':K12_CONFIG_ROOT,'manifests':K12_MANIFESTS,'secret_env':K12_SECRET_ENV,
                    'pins_env':K12_PINS_ENV,'docker_cli':K12_DOCKER_CLI,'receipts':K12_RECEIPTS,'data_target':K12_DATA_TARGET,
                    'data_volume_read_only_exception':K12_DATA_VOLUME,'release':K12_RELEASE_DIR+'/'+K12_RELEASE_FILE,'source_root_never_bound':K12_SOURCE_ROOT,'writer_name':k12_writer_name('<sha256>'),
                    'journal_forbidden':list(K12_JOURNAL_FORBIDDEN),'chain_rule':'ROOT_CONTROLLED_UID0_GID0_NO_GROUP_OR_OTHER_WRITE_NO_SETGID_NO_LINK'},
       'claim':{'directory':K12_RECEIPTS,'name':'k12-<day>-preflight.claim.json','schema':P_CLAIM_SCHEMA,'mode_octal':'0600','expect':'ABSENT'},
       'manifests_effects':'CLOSED: NO ENTRY CREATED, CHANGED OR REMOVED; THE DIRECTORY UNCHANGED','files':FILES_SCOPE,
       'success':{'status':'PREFLIGHT_OK','mode':'PREFLIGHT','exit_code':0,'checks.directory_checked':True,
                  'pins':['capacity_config_sha256','release_sha256','package_sha256','build_sha'],'massive_bars_enabled':True,'owner_uid':0},
       'never':['a container that stays','-d','a pull','a file created, changed or removed by this process other than its claim','the content of secret.env',
                'a bind source not controlled by root alone other than the named read-only data volume','a read of the data volume other than the release file','a second preflight of the day',
                'the environment of a container','activation','a second attempt'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'allowance_seconds':P_ALLOWANCE_SECONDS,'stdout_bytes':K12_STDOUT_MAX_BYTES,'request_bytes':K12_REQUEST_MAX_BYTES,
                 'writer_bytes':K12_WRITER_MAX_BYTES}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner,NativeFiles):
    """The read primitives, the fixed-argv runner and the creating calls of the files part (the claim file only)."""


def p_path(name,derived):return derived['journal']['source'] if name=='journal' else P_PATHS[name]

def p_derived(plan):
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    derived=k12_capacity_request(plan['capacity_request'])[2]
    need(derived['index']==1,'NOT_THE_PRIMARY_WINDOW')
    rows=plan['parent_rows'];need(type(rows) is dict and set(rows)==set(P_CHAINS),'PARENT_ROWS_INVALID')
    for name in P_CHAINS:
        if name=='data':k12_data_chain(rows[name]);continue               # the named read-only exception
        k12_root_chain(rows[name],p_path(name,derived))                   # Codex 6: root alone from '/'
        need((rows[name][-1]['uid'],rows[name][-1]['gid'],rows[name][-1]['mode'])==(0,0,0o700),'DIRECTORY_NOT_ROOT_PRIVATE')
    return derived

def validate_plan(plan):p_derived(plan)

def p_words(derived,request_sha256):
    labels=[(K12_LABEL_REQUEST,request_sha256),(K12_LABEL_CAPACITY,derived['sha256'])]
    return k12_container_words(derived,k12_preflight_name(derived['day']),labels)+['--preflight']

def effects_of(plan):
    derived=p_derived(plan)
    return {'operation':OPERATION,'epoch':K12_EPOCH,'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'capacity_request_sha256':derived['sha256'],'day':derived['day'],'window':derived['window'],'window_slot':1,
            'run':P_RUN_PREFIX+p_words(derived,'<this request\'s sha256>'),'docker_config':K12_DOCKER_CLI,
            'container_name':k12_preflight_name(derived['day']),'before':derived['not_before'],
            'chains':{name:chain_effects(plan['parent_rows'][name]) for name in P_CHAINS},
            'writer':{'path':K12_CONFIG_ROOT+'/'+k12_writer_name(derived['writer_sha256']),'sha256':derived['writer_sha256'],'require':'ROOT_0600_ONE_LINK'},
            'capacity_config':{'path':K12_CONFIG_ROOT+'/'+derived['config_name'],'sha256':derived['config_sha256'],'require':'ROOT_0600_ONE_LINK'},
            'pins_env':{'path':K12_PINS_ENV,'sha256':derived['pins_sha256'],'require':'ROOT_0600_ONE_LINK'},
            'secret_env':{'path':K12_SECRET_ENV,'require':'ROOT_0600_ONE_LINK','read':'METADATA_ONLY'},
            'journal':{'path':derived['journal']['source'],'target':derived['journal']['target'],'require':'ROOT_0700_CATALOG_ROOT_0600'},
            'data':{'path':K12_DATA_VOLUME,'target':K12_DATA_TARGET,'read_only':True,'exception':'CODEX_429_5986698996',
                    'release':{'path':K12_RELEASE_DIR+'/'+K12_RELEASE_FILE,'sha256':derived['release_sha256'],'require':'ROOT_0600_ONE_LINK',
                               'checked':'BEFORE_THE_RUN_AND_AFTER_IT'}},
            'chain_rule':'ROOT_CONTROLLED_UID0_GID0_NO_GROUP_OR_OTHER_WRITE_NO_SETGID_NO_LINK',
            'creates':{'path':K12_RECEIPTS+'/'+p_claim_name(derived['day']),'mode_octal':'0600','uid':0,'gid':0,'schema':P_CLAIM_SCHEMA,
                       'expect':'ABSENT','before':'THE_RUN'},
            'manifests':{'path':K12_MANIFESTS,'bound':'READ_WRITE_AS_IN_THE_DISPATCH','effects':'CLOSED',
                         'proof':'LSTAT_SIGNATURE_OF_EVERY_ENTRY_AND_FSTAT_SIGNATURE_OF_THE_DIRECTORY_EQUAL_BEFORE_AND_AFTER'},
            'after':{'container':'ABSENT','manifests_directory':'UNCHANGED'},
            'files_created_by_this_process':1,'activation':False}
def success_of(plan):return COMPLETE_OUTCOME

def p_manifest_state(host,held,day,gate):
    """The manifests directory, closed: the number of its entries and whether the day's manifest is among them (what
    the receipt shows), and the SHA-256 of every entry's name with its lstat signature and of the directory's own fstat
    signature (kept in memory for one comparison: names and signatures never leave this function's caller)."""
    present=0;rows=[]
    for name in sorted(host.names(held.fd)):
        gate();rows.append([name,list(stat_signature(host.lstat(name,held.fd)))])
        if name==day+'.json':present+=1
    rows.append(['.',list(stat_signature(host.fstat(held.fd)))])
    return {'entries':len(rows)-1,'manifest_present':present==1,'_signature':sha(canonical(rows))}

def p_public(state):return {key:value for key,value in state.items() if not key.startswith('_')}

def p_checks(line):
    """The preflight's checks object, booleans and counts only (anything else is not copied)."""
    checks=line.get('checks') or {}
    return {key:value for key,value in sorted(checks.items()) if text(key,'[a-z][a-z0-9_]{0,63}') and (type(value) is bool or integer(value,0,1000000))}

def p_ok(line,derived,returncode):
    checks=line.get('checks') or {}
    return (returncode==0 and line['status']=='PREFLIGHT_OK' and line['mode']=='PREFLIGHT' and line['session']==derived['day']
            and line.get('owner_uid')==0 and line.get('capacity_config_sha256')==derived['config_sha256']
            and line.get('release_sha256')==derived['release_sha256'] and line.get('package_sha256')==derived['package_sha256']
            and line.get('build_sha')==derived['build_sha'] and line.get('massive_bars_enabled') is True and checks.get('directory_checked') is True)

def _reduce_parents(receipt):receipt['parents']={key:len(value) for key,value in (receipt.get('parents') or {}).items()}
def _reduce_detail(receipt):receipt['detail']={'reduced_for_size':True}
REDUCTIONS=[('PARENTS_REDUCED_TO_COUNT',_reduce_parents),('DETAIL_DROPPED',_reduce_detail)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    derived=p_derived(plan);words=p_words(derived,bound['request_sha256'])
    gate()
    state.started=True
    commands=Commands(host,gate);handles={};detail={'parents':{}};name=k12_preflight_name(derived['day']);ledger=[];kept={}
    def finish(status,outcome,code,extra):
        parents=detail.pop('parents',{})
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),
            clock=timing(begun,mark,clock,monotonic),commands_started=dict(commands.started),mutating_calls=state.counts(),parents=parents,
            detail=detail,ledger=ledger,objects_left_by_this_run=objects_left([],ledger),pre_existing_objects_modified=False,**extra)))
    try:
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o077)
            need(begun.date().isoformat()==derived['day'],'RUN_NOT_ON_THE_DAY_OF_THE_WINDOW')
            need(begun<instant(derived['not_before']),'PREFLIGHT_NOT_BEFORE_THE_PRIMARY_WINDOW')
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            for key in P_CHAINS:
                handles[key]=Pinned(host,walk_pinned(host,plan['parent_rows'][key],gate,detail['parents'].setdefault(key,[])),rows=plan['parent_rows'][key])
            raw,facts=k12_file(host,k12_writer_name(derived['writer_sha256']),handles['config'],gate,K12_WRITER_MAX_BYTES)
            need(raw is not None,'WRITER_FILE_ABSENT');need(k12_private(facts),'WRITER_FILE_NOT_PRIVATE')
            need(sha(raw)==derived['writer_sha256'],'WRITER_BYTES_NOT_THE_SIGNED_ONES')
            raw,facts=k12_file(host,derived['config_name'],handles['config'],gate,K12_CONFIG_MAX_BYTES)
            need(raw is not None,'CAPACITY_CONFIG_ABSENT');need(k12_private(facts),'CAPACITY_CONFIG_NOT_PRIVATE')
            need(sha(raw)==derived['config_sha256'],'CAPACITY_CONFIG_NOT_THE_SIGNED_BYTES')
            raw,facts=k12_file(host,'pins.env',handles['reader_config'],gate,K12_PINS_MAX_BYTES)
            need(raw is not None,'PINS_ENV_ABSENT');need(k12_private(facts),'PINS_ENV_NOT_PRIVATE')
            need(sha(raw)==derived['pins_sha256'],'PINS_ENV_NOT_THE_SIGNED_BYTES')
            k12_release(host,handles['data'],gate,derived)
            found=k12_entry(host,'secret.env',handles['reader_config'],gate)
            need(found is not None,'SECRET_ENV_ABSENT');need(k12_private(found),'SECRET_ENV_NOT_PRIVATE')
            need(count_entries(host,handles['docker_cli'].fd,gate)==0,'DOCKER_CLI_DIRECTORY_NOT_EMPTY')
            for entry in ('epoch.json','maintenance.lock'):
                need(k12_private(k12_entry(host,entry,handles['journal'],gate)),'JOURNAL_CATALOG_NOT_AS_REQUIRED')
            need(k12_entry(host,p_claim_name(derived['day']),handles['receipts'],gate) is None,'PREFLIGHT_ALREADY_CLAIMED')
            kept['before']=p_manifest_state(host,handles['manifests'],derived['day'],gate);detail['manifests_before']=p_public(kept['before'])
            image=image_facts(commands,derived['image_id'],docker_config=K12_DOCKER_CLI)
            need(image['id']==derived['image_id'],'IMAGE_ID_MISMATCH');need(image['revision_label']==derived['build_sha'],'IMAGE_REVISION_MISMATCH')
            prefix='c3po-k12-%s-'%k12_compact(derived['day'])
            listed=[row for row in container_list(commands,docker_config=K12_DOCKER_CLI) if row['name'].startswith(prefix)]
            need(not [row for row in listed if row['name']==name],'PREFLIGHT_CONTAINER_PRESENT')
            need(not listed,'CAPACITY_CONTAINER_OF_THE_DAY_PRESENT')
            left=gate();detail['seconds_left_before_first_effect']=int(left)
            need(left>=effects_budget('preflight')+P_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})
        extra={'phase_reached':'EFFECTS','preflight':None}
        claim=canonical({'schema':P_CLAIM_SCHEMA,'epoch':K12_EPOCH,'day':derived['day'],'window':derived['window'],
                         'capacity_request_sha256':derived['sha256'],'preflight_request_sha256':bound['request_sha256'],'container_name':name})
        entry=create_file(0,'PREFLIGHT_CLAIM',K12_RECEIPTS+'/'+p_claim_name(derived['day']),claim,PRIVATE_FILE_MODE,handles['receipts'],host,gate,
                          state,bound['go_sha256'][:16])
        ledger.append(entry)
        if entry['state']!='INSTALLED_DURABLE':
            stop=entry['code'] or 'CLAIM_FAILED'
            return finish(REFUSED_STATUS if state.clean() else PARTIAL_STATUS,REFUSED_OUTCOME if state.clean() else PARTIAL_OUTCOME,stop,extra)
        stop=readback_file(entry,claim,PRIVATE_FILE_MODE,handles['receipts'],host,gate)
        if stop is not None:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)
        result=effect(state,commands,'preflight',*words,capture=True,docker_config=K12_DOCKER_CLI)
        detail['run']={key:result[key] for key in ('started','returned','returncode','code')}
        # from here the claim is on the host: never a refusal (one preflight per day; a second attempt needs a new decision)
        if not result['started']:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,result['code'] or 'PREFLIGHT_NOT_STARTED',extra)
        try:
            left=[row for row in container_list(commands,docker_config=K12_DOCKER_CLI) if row['name']==name]
            handles['manifests'].verify(gate);after=p_manifest_state(host,handles['manifests'],derived['day'],gate)
            clean=not left and after==kept['before']
            detail.update(container_left=bool(left),manifests_after=p_public(after),manifests_unchanged=after==kept['before'])
        except Exception as error:
            if result['returned']:state.unknown()
            return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,code_of(error,'READBACK_UNAVAILABLE'),extra)
        if not result['returned']:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,'PREFLIGHT_UNCERTAIN',extra)
        if not clean:
            state.unknown();return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,'PREFLIGHT_LEFT_SOMETHING',extra)
        state.fail()          # the container ran and is gone, the manifests directory is as it was: the run changed nothing
        try:k12_release(host,handles['data'],gate,derived)        # the bytes the preflight read are still the signed ones
        except Exception as error:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,'RELEASE_CHANGED_DURING_PREFLIGHT',extra)
        if result['returncode'] in RUN_ENGINE_STATUSES:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,'PREFLIGHT_ENGINE_FAILURE',extra)
        line,code=k12_line_of(None,result['output'],derived['day'])
        if line is None:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,code,extra)
        ok=p_ok(line,derived,result['returncode'])
        extra['preflight']=dict(k12_line_public(line),checks=p_checks(line),returncode=result['returncode'],ok=ok)
        if ok:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,'PREFLIGHT_NOT_OK',extra)
    finally:
        for handle in handles.values():
            try:handle.close()
            except Exception:pass
