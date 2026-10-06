import base64

OPERATION='GO_WRITE_HOSTOPS02_K12_WINDOW_01'
PHASE='WRITE_K12_CAPACITY_WINDOW_STEP'
REQUEST_SCHEMA='WRITE_HOSTOPS02_K12_WINDOW_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_K12_WINDOW_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_K12_WINDOW_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_K12_WINDOW_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_K12_WINDOW_PLAN_V1'
SOURCE_NAME='k12_window.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False
# Tuesday 06/10 to Friday 09/10 hold every mode (the plan's day is one of K12_DAYS; REMOVE runs on Friday 09/10). The
# narrowest class of the core that holds those days is WRITE_SESSIONS (10-05 ... 10-10 UTC).
DATE_CLASS='WRITE_SESSIONS'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
# The signed rows of every directory this source walks come from a TREE read of k12_collect in the same boot.
EVIDENCE_OPERATIONS=('GO_READONLY_HOSTOPS02_K12_COLLECT_01',)
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='K12_WINDOW_STEP_COMPLETE_READ_BACK'
PARTIAL_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
PLAN_KEYS=frozenset(('mode','capacity_request','launch_request_sha256','removals','parent_rows','evidence_boot_id_sha256'))

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

W_MODES=('LAUNCH','PERSIST','STOP','REMOVE')
# Which held directories each mode walks from "/" against signed rows, and the path of each.
# The journal's and the data bind's paths are the REQUEST's (w_path). Every chain is root-controlled (k12_root_chain).
W_PATHS={'config':K12_CONFIG_ROOT,'manifests':K12_MANIFESTS,'reader_config':K12_READER_CONFIG,'docker_cli':K12_DOCKER_CLI,
         'receipts':K12_RECEIPTS,'data':K12_RELEASE_DIR}
W_PRIVATE=('config','manifests','reader_config','docker_cli','journal','receipts')   # leaf root:root 0700
W_CHAINS={'LAUNCH':('config','manifests','reader_config','docker_cli','journal','data','receipts'),
          'PERSIST':('receipts',),'STOP':('manifests',),'REMOVE':('receipts',)}
W_LAUNCH_LEAD_SECONDS=45                  # LAUNCH: the view must still be this far when the container is created
W_STOP_LEAD_SECONDS=25                    # STOP: the stop must start this long before the view (its class is 20 s)
W_PERSIST_AFTER_VIEW_SECONDS=60           # PERSIST: not before the view + 60 s (MASTER_PLAN D2: "view + 60 s")
W_REMOVE_DAY='2026-10-09'
W_REMOVE_NOT_BEFORE='20:00:00'            # Friday after the close (17:00 BRT)
W_ALLOWANCE_SECONDS=4                     # STOP, REMOVE: one effect, nothing between effects
W_ALLOWANCE_LAUNCH_SECONDS=10             # LAUNCH: one inspect (QUICK, 8 s) between create and start, and 2 s
W_ALLOWANCE_PERSIST_SECONDS=12            # PERSIST: one inspect (8 s) after the logs, and the file (4 s)
W_MAX_REMOVALS=12                         # four days of three windows
W_STOP_SECONDS='5'
K12_CREATE_PREFIX=['create','--pull','never','--init','--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
                   '--restart','no']
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'the signed image ID','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          'inspect':command_row('docker',['container','inspect','--format',K12_FORMAT],'one container name of this family or one 64-hex ID','QUICK','READ'),
          'create':command_row('docker',K12_CREATE_PREFIX,'--name, two --label, --network, two --env-file, four --env, the four --mount of the '
                               'signed REQUEST, the signed image ID, python -I -B <the writer in the config root> and the REQUEST\'s writer argv',
                               'QUICK','EFFECT'),
          'start':command_row('docker',['start'],'exactly the 64-hex ID that create printed','RUN_SHORT','EFFECT'),
          'stop':command_row('docker',['stop','-t',W_STOP_SECONDS],'exactly one 64-hex ID: the running container of that window, identified',
                             'RUN_SHORT','EFFECT'),
          'logs':command_row('docker',['logs'],'exactly one 64-hex ID: the exited container of that window, identified (standard output only; '
                             'the container\'s standard error goes to /dev/null with the CLI\'s)','QUICK','EFFECT'),
          'remove':command_row('docker',['rm'],'1 to 12 64-hex IDs: exited or never-started containers of this family, each identified and with '
                               'its private receipt on the host when it ran','QUICK','EFFECT')}

SCOPE_STATEMENT=('The capacity-day window of epoch '+K12_EPOCH+', one signed mode per request. LAUNCH: docker create (no --rm, --restart no, '
                 '--pull never, --init, --user 0:0, --read-only, --cap-drop ALL, no-new-privileges) and docker start of one container named '
                 'c3po-k12-<yyyymmdd>-w<index>, labelled with this request and with the documents tool REQUEST it carries byte for byte, '
                 'running python -I -B on the writer delivered by hash in '+K12_CONFIG_ROOT+' with that REQUEST\'s argv, network, two '
                 'environment files and four binds ('+K12_DATA_VOLUME+' at '+K12_DATA_TARGET+', the journal and '+K12_CAPACITY_ROOT
                 +' read-only, '+K12_MANIFESTS+' read-write), every bind source and every ancestor of it controlled by root alone '
                 '(uid 0, gid 0, no group or other write, no setgid, no link) except the named read-only data volume (Codex #429 '
                 '5986698996: ancestors root-controlled, a mount point, the release directory root 0700, the release file hashed '
                 'against the REQUEST before the create and again after the start); the container '
                 'parks until its view. PERSIST: docker logs (no follow, no tail; QUICK class: bounded in seconds and bytes) of that '
                 'exited container, identified by its ID, name and two labels, with a known exit code and not OOM-killed; the output '
                 'must be exactly one complete writer receipt of this day and of a publish run, consistent with the exit code, or '
                 'nothing is written; that receipt and the exit state go into one new private file (root:root 0600, exclusive '
                 'creation, fsync, read back) in '+K12_RECEIPTS+'. STOP: docker stop of that running container before its view. '
                 'REMOVE: docker rm without -f or -v of exited or never-started containers of this family whose private receipt is on '
                 'the host or which ended by a stop before their view. A container is acted on only after its name, labels, image, '
                 'argv and binds were read and found to be this family\'s. Nothing is written into the manifests directory, the '
                 'capacity tree, the journal or the data directory by this process; no environment is printed; the manifest hash and '
                 'the symbol count never leave the host.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,'epoch':K12_EPOCH,'days':list(K12_DAYS),
       'modes':list(W_MODES),'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,
       'command_environment':COMMAND_ENVIRONMENT,'command_variables':COMMAND_VARIABLES,
       'clock':{'views_utc':{str(key):value for key,value in sorted(K12_VIEW_UTC.items())},'cutoff_utc':K12_CUTOFF_UTC,'view_seconds':K12_VIEW_SECONDS,
                'launch_lead_seconds':W_LAUNCH_LEAD_SECONDS,'stop_lead_seconds':W_STOP_LEAD_SECONDS,
                'persist_after_view_seconds':W_PERSIST_AFTER_VIEW_SECONDS,'remove_day':W_REMOVE_DAY,'remove_not_before_utc':W_REMOVE_NOT_BEFORE},
       'placement':{'capacity_root':K12_CAPACITY_ROOT,'config_root':K12_CONFIG_ROOT,'capacity_target':K12_CAPACITY_TARGET,
                    'data_target':K12_DATA_TARGET,'data_volume_read_only_exception':K12_DATA_VOLUME,
                    'release':K12_RELEASE_DIR+'/'+K12_RELEASE_FILE,'source_root_never_bound':K12_SOURCE_ROOT,
                    'chain_rule':'ROOT_CONTROLLED_UID0_GID0_NO_GROUP_OR_OTHER_WRITE_NO_SETGID_NO_LINK','manifests':K12_MANIFESTS,'secret_env':K12_SECRET_ENV,
                    'pins_env':K12_PINS_ENV,'docker_cli':K12_DOCKER_CLI,'receipts':K12_RECEIPTS,'writer_name':k12_writer_name('<sha256>'),
                    'journal_forbidden':list(K12_JOURNAL_FORBIDDEN)},
       'container':{'name':'c3po-k12-<yyyymmdd>-w<index>','labels':[K12_LABEL_REQUEST,K12_LABEL_CAPACITY],'inspect_format':K12_FORMAT,
                    'create_prefix':K12_CREATE_PREFIX},
       'persisted':{'directory':K12_RECEIPTS,'name':'k12-<day>-w<index>.writer.json','schema':K12_PERSISTED_SCHEMA,
                    'keys':sorted(K12_PERSISTED_KEYS),'mode_octal':'0600','content':'EXACTLY_ONE_COMPLETE_WRITER_RECEIPT_CONSISTENT_WITH_THE_EXIT_CODE'},
       'files':FILES_SCOPE,'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'never':['--rm on the launched container','-d on a run','a pull','-f or -v on rm','docker exec','a write into the manifests directory, '
                'the capacity tree, the journal or the data directory by this process','a bind source not controlled by root alone other than the named read-only data volume','a read of the data volume other than the release file','the environment of a container','the content of secret.env',
                'the manifest hash or the symbol count in a receipt','an existing file overwritten, renamed, chmodded, chowned or removed',
                'a container that is not this family\'s','activation','a second attempt'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'allowance_seconds':{'LAUNCH':W_ALLOWANCE_LAUNCH_SECONDS,'PERSIST':W_ALLOWANCE_PERSIST_SECONDS,'STOP':W_ALLOWANCE_SECONDS,
                                      'REMOVE':W_ALLOWANCE_SECONDS},'max_removals':W_MAX_REMOVALS,'stdout_bytes':K12_STDOUT_MAX_BYTES,
                 'request_bytes':K12_REQUEST_MAX_BYTES,'writer_bytes':K12_WRITER_MAX_BYTES}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner,NativeFiles):
    """The read primitives, the fixed-argv runner and the creating calls of the files part (PERSIST's one file)."""


# ---------------------------------------------------------------- the plan (pure)
def w_path(name,derived):
    return derived['journal']['source'] if name=='journal' else W_PATHS[name]

def w_chains(plan,derived):
    """The signed rows of every directory the mode walks, validated: every chain controlled by root alone, every
    component from '/' (k12_root_chain, Codex 6), and the leaf of each private directory root:root 0700."""
    rows=plan['parent_rows'];names=W_CHAINS[plan['mode']]
    need(type(rows) is dict and set(rows)==set(names),'PARENT_ROWS_INVALID')
    for name in names:
        if name=='data':k12_data_chain(rows[name]);continue           # the named read-only exception
        k12_root_chain(rows[name],w_path(name,derived))
        leaf=rows[name][-1]
        need(name not in W_PRIVATE or (leaf['uid'],leaf['gid'],leaf['mode'])==(0,0,0o700),'DIRECTORY_NOT_ROOT_PRIVATE')
    return rows

def w_removals(plan):
    """REMOVE: 1 to 12 rows {day, window_slot, container_id, image_id, launch_request_sha256, capacity_request_sha256},
    distinct by container and by window."""
    items=plan['removals']
    need(type(items) is list and items,'REMOVALS_INVALID')        # at most 12: four days x three slots, distinct below
    for item in items:
        need(type(item) is dict and set(item)=={'day','window_slot','container_id','image_id','launch_request_sha256','capacity_request_sha256'}
             and item['day'] in K12_DAYS and integer(item['window_slot'],1,3) and text(item['container_id'],CONTAINER_ID)
             and text(item['image_id'],IMAGE_ID) and hexpin(item['launch_request_sha256']) and hexpin(item['capacity_request_sha256']),'REMOVALS_INVALID')
    need(len({item['container_id'] for item in items})==len(items) and len({(item['day'],item['window_slot']) for item in items})==len(items),
         'REMOVALS_INVALID')
    return items

def w_derived(plan):
    """Everything the run will put on the engine, from the signed plan alone."""
    mode=plan['mode'];need(mode in W_MODES,'MODE_INVALID')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    if mode=='REMOVE':
        need(plan['capacity_request'] is None and plan['launch_request_sha256'] is None,'MODE_MEMBERS_INVALID')
        w_removals(plan);derived={'journal':{'source':None}}
    else:
        need(plan['removals'] is None and ((plan['launch_request_sha256'] is None) if mode=='LAUNCH' else hexpin(plan['launch_request_sha256'])),
             'MODE_MEMBERS_INVALID')
        derived=k12_capacity_request(plan['capacity_request'])[2]
    w_chains(plan,derived)
    return derived

def validate_plan(plan):w_derived(plan)

def w_labels(derived,request_sha256):return [(K12_LABEL_REQUEST,request_sha256),(K12_LABEL_CAPACITY,derived['sha256'])]

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared. For
    LAUNCH the create argv carries the label of this request's own hash, which no plan can hold: it is shown with the
    placeholder <this request's sha256>."""
    derived=w_derived(plan);mode=plan['mode']
    out={'operation':OPERATION,'mode':mode,'epoch':K12_EPOCH,'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
         'chains':{name:chain_effects(plan['parent_rows'][name]) for name in W_CHAINS[mode]},
         'writes_into_manifests_capacity_journal_or_data':False,'chain_rule':'ROOT_CONTROLLED_UID0_GID0_NO_GROUP_OR_OTHER_WRITE_NO_SETGID_NO_LINK','environment_printed':False,'activation':False}
    if mode=='REMOVE':
        out['removals']=[{'container_name':k12_container_name(item['day'],item['window_slot']),'container_id':item['container_id'],
                          'image_id':item['image_id'],'labels':{K12_LABEL_REQUEST:item['launch_request_sha256'],K12_LABEL_CAPACITY:item['capacity_request_sha256']},
                          'require':'EXITED_WITH_ITS_PRIVATE_RECEIPT_OR_STOPPED_BEFORE_ITS_VIEW_OR_NEVER_STARTED'} for item in plan['removals']]
        out['command']=['rm']+[item['container_id'] for item in plan['removals']]
        out['force']=False;out['volumes']=False
        return out
    name=k12_container_name(derived['day'],derived['index'])
    out.update(capacity_request_sha256=derived['sha256'],day=derived['day'],window=derived['window'],window_slot=derived['index'],
               container_name=name,view_opens_at=derived['view_opens_at'],cutoff_at=derived['cutoff_at'])
    if mode=='LAUNCH':
        out['create']=K12_CREATE_PREFIX+k12_container_words(derived,name,w_labels(derived,'<this request\'s sha256>'))
        out['start']=['start','<the 64-hex ID create printed>']
        out['docker_config']=K12_DOCKER_CLI
        out['writer']={'path':K12_CONFIG_ROOT+'/'+k12_writer_name(derived['writer_sha256']),'sha256':derived['writer_sha256'],'require':'ROOT_0600_ONE_LINK'}
        out['capacity_config']={'path':K12_CONFIG_ROOT+'/'+derived['config_name'],'sha256':derived['config_sha256'],'require':'ROOT_0600_ONE_LINK'}
        out['pins_env']={'path':K12_PINS_ENV,'sha256':derived['pins_sha256'],'require':'ROOT_0600_ONE_LINK'}
        out['secret_env']={'path':K12_SECRET_ENV,'require':'ROOT_0600_ONE_LINK','read':'METADATA_ONLY'}
        out['journal']={'path':derived['journal']['source'],'target':derived['journal']['target'],'require':'ROOT_0700_CATALOG_ROOT_0600'}
        out['data']={'path':K12_DATA_VOLUME,'target':K12_DATA_TARGET,'read_only':True,'exception':'CODEX_429_5986698996',
                     'release':{'path':K12_RELEASE_DIR+'/'+K12_RELEASE_FILE,'sha256':derived['release_sha256'],'require':'ROOT_0600_ONE_LINK',
                                'checked':'BEFORE_THE_CREATE_AND_AFTER_THE_START'}}
        out['container']={'removed_on_exit':False,'restart':'no','parks_until':derived['view_opens_at']}
        out['earlier_windows']='EXITED_WITH_PRIVATE_RECEIPT_AND_ONE_VALID_LINE_NOT_TERMINAL_OR_NEVER_STARTED_OR_ABSENT'
        out['earlier_window_stopped_before_its_view']='REFUSED_DAY_STOPPED'
        out['manifest_of_the_day']='ABSENT_OR_TWO_LINKS_OR_AFTER_AN_EARLIER_WINDOW_WITH_A_LINE'
    elif mode=='PERSIST':
        out['launch_request_sha256']=plan['launch_request_sha256']
        out['read']=['logs','<the 64-hex ID of that exited container>']
        out['logs_bounds']={'class':'QUICK','seconds':COMMAND_CLASSES['QUICK']['seconds'],'stdout_bytes':K12_STDOUT_MAX_BYTES,'follow':False,'tail':False}
        out['requires']='EXACTLY_ONE_COMPLETE_WRITER_RECEIPT_CONSISTENT_WITH_THE_EXIT_CODE_NOT_OOM'
        out['creates']={'path':K12_RECEIPTS+'/'+k12_persisted_name(derived['day'],derived['index']),'mode_octal':'0600','uid':0,'gid':0,
                        'schema':K12_PERSISTED_SCHEMA,'expect':'ABSENT'}
    else:
        out['launch_request_sha256']=plan['launch_request_sha256']
        out['stop']=['stop','-t',W_STOP_SECONDS,'<the 64-hex ID of that running container>']
        out['not_later_than_seconds_before_the_view']=W_STOP_LEAD_SECONDS
    return out
def success_of(plan):return COMPLETE_OUTCOME


# ---------------------------------------------------------------- the run
def w_clock(plan,derived,begun):
    """The instant of the run against the window of the mode (pure; before anything is observed)."""
    mode=plan['mode']
    if mode=='REMOVE':
        need(begun.date().isoformat()==W_REMOVE_DAY and begun>=instant(k12_at(W_REMOVE_DAY,W_REMOVE_NOT_BEFORE)),'REMOVE_OUTSIDE_FRIDAY_EVENING')
        return
    view=instant(derived['view_opens_at'])
    need(begun.date().isoformat()==derived['day'],'RUN_NOT_ON_THE_DAY_OF_THE_WINDOW')
    if mode=='PERSIST':
        need((begun-view).total_seconds()>=W_PERSIST_AFTER_VIEW_SECONDS,'PERSIST_BEFORE_THE_VIEW_AND_A_MINUTE');return
    need(begun>=instant(derived['not_before']),'RUN_BEFORE_THE_WINDOW_START')
    lead=W_LAUNCH_LEAD_SECONDS if mode=='LAUNCH' else W_STOP_LEAD_SECONDS
    need((view-begun).total_seconds()>=lead,'TOO_CLOSE_TO_THE_VIEW')

def w_hold(host,rows,gate,observed):return Pinned(host,walk_pinned(host,rows,gate,observed),rows=rows)

def w_inspect(commands,target):return k12_inspect(commands.output('inspect',target,docker_config=K12_DOCKER_CLI))

def w_try_inspect(commands,target):
    """The container's row, or None when docker inspect does not answer it (absent or broken: one case)."""
    try:return w_inspect(commands,target)
    except CommandFailed:return None

def w_listed_without(commands,name):
    """True only when a listing of every container succeeded and does not hold that name (an inspect that fails is not a
    proof of absence: the daemon may not have answered)."""
    try:return name not in [row['name'] for row in container_list(commands,docker_config=K12_DOCKER_CLI)]
    except Exception:return False

def w_summary(row):
    if row is None:return None
    return {'id':row['id'],'name':row['name'],'state':row['state'],'running':row['running'],'exit_code':row['exit_code'],
            'oom_killed':row['oom_killed'],'started':row['started_at']!=K12_NEVER_STARTED,'finished_at':row['finished_at']}

def w_earlier(ctx,containers):
    """LAUNCH: the containers of this family for the same day, against the window being launched. A later window's
    container, any of them not settled, an earlier one that ran without its private receipt, or an earlier receipt that
    shows the day decided (published, or the empty list) is a refusal (ORD:16; CAP outcome rule; S1D)."""
    derived=ctx['derived'];day=derived['day'];prefix='c3po-k12-%s-'%k12_compact(day);seen=[]
    need(not [row for row in containers if row['name'].startswith('c3po-k12-') and not row['name'].startswith(prefix) and row['state']!='exited'
              and row['state']!='created'],'CAPACITY_CONTAINER_OF_ANOTHER_DAY_NOT_SETTLED')
    for row in containers:
        if not row['name'].startswith(prefix):continue
        seen.append({'name':row['name'],'state':row['state']})
        need(row['name']!=k12_container_name(day,derived['index']),'CONTAINER_NAME_TAKEN')
        need(row['state'] in ('exited','created'),'CAPACITY_CONTAINER_OF_THE_DAY_NOT_SETTLED')
        need(row['name'] in [k12_container_name(day,index) for index in range(1,derived['index'])],'CAPACITY_CONTAINER_OF_THE_DAY_NOT_EARLIER')
    ctx['detail']['day_containers']=seen
    for index in range(1,derived['index']):
        name=k12_container_name(day,index);found=[row for row in containers if row['name']==name]
        if not found or found[0]['state']=='created':continue
        raw,facts=k12_file(ctx['host'],k12_persisted_name(day,index),ctx['handles']['receipts'],ctx['gate'],K12_PERSISTED_MAX_BYTES)
        if raw is None:
            # PERSIST keeps nothing but a complete receipt: an earlier container without one either ended by D4's stop
            # before its view (the day is stopped, ORD:17) or is not settled.
            row=w_try_inspect(ctx['commands'],found[0]['id'])
            need(not (row is not None and k12_stopped(row['exit_code'],row['oom_killed'],row['finished_at'],k12_at(day,K12_VIEW_UTC[index]))),
                 'DAY_STOPPED_BEFORE_A_VIEW')
        need(raw is not None,'EARLIER_WINDOW_RECEIPT_NOT_PERSISTED')
        need(k12_private(facts),'EARLIER_WINDOW_RECEIPT_NOT_PRIVATE')
        value,stdout=k12_persisted(raw,{'epoch':K12_EPOCH,'day':day,'window_slot':index,'container_id':found[0]['id'],'container_name':name})
        ended,line=k12_ended(value,stdout,day,k12_at(day,K12_VIEW_UTC[index]))
        need(ended!='STOPPED','DAY_STOPPED_BEFORE_A_VIEW')
        need(ended=='LINE','EARLIER_WINDOW_ENDED_WITHOUT_A_VALID_LINE')
        terminal=k12_terminal(line);ctx['earlier_line']=True       # a LINE is of a publish run (k12_receipt_line)
        need(terminal!='PUBLISHED','DAY_ALREADY_PUBLISHED')
        need(terminal!='EMPTY_LIST','DAY_TERMINAL_EMPTY_LIST')

def w_launch_precheck(ctx):
    host,gate,derived,handles,detail=ctx['host'],ctx['gate'],ctx['derived'],ctx['handles'],ctx['detail']
    for name in W_CHAINS['LAUNCH']:
        observed=detail['parents'].setdefault(name,[]);handles[name]=w_hold(host,ctx['plan']['parent_rows'][name],gate,observed)
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
    found=k12_entry(host,'secret.env',handles['reader_config'],gate)         # metadata only: never opened, never hashed
    need(found is not None,'SECRET_ENV_ABSENT');need(k12_private(found),'SECRET_ENV_NOT_PRIVATE')
    need(count_entries(host,handles['docker_cli'].fd,gate)==0,'DOCKER_CLI_DIRECTORY_NOT_EMPTY')
    for name in ('epoch.json','maintenance.lock'):
        need(k12_private(k12_entry(host,name,handles['journal'],gate)),'JOURNAL_CATALOG_NOT_AS_REQUIRED')
    present=k12_entry(host,derived['day']+'.json',handles['manifests'],gate)
    detail['manifest_before']={'present':present is not None,'links':None if present is None else present['links']}
    image=image_facts(ctx['commands'],derived['image_id'],docker_config=K12_DOCKER_CLI)
    need(image['id']==derived['image_id'],'IMAGE_ID_MISMATCH');need(image['revision_label']==derived['build_sha'],'IMAGE_REVISION_MISMATCH')
    containers=container_list(ctx['commands'],docker_config=K12_DOCKER_CLI)
    detail['containers_listed']=len(containers)
    need(not [row for row in containers if row['name']==k12_preflight_name(derived['day'])],'PREFLIGHT_CONTAINER_PRESENT')
    w_earlier(ctx,containers)
    # A published manifest of the day (one link) that no earlier window of this family explains: never a new window.
    # Two links is the interrupted publication the next window completes (ORD:33(a)): allowed.
    need(not (present is not None and present['links']==1 and not ctx.get('earlier_line')),'MANIFEST_PRESENT_WITHOUT_AN_EARLIER_WINDOW')
    left=gate();detail['seconds_left_before_first_effect']=int(left)
    need(left>=effects_budget('create','start')+W_ALLOWANCE_LAUNCH_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
    lead=(instant(derived['view_opens_at'])-ctx['clock']()).total_seconds();detail['seconds_to_the_view_before_create']=int(lead)
    need(lead>=W_LAUNCH_LEAD_SECONDS,'TOO_CLOSE_TO_THE_VIEW')

def w_launch(ctx):
    derived,state,commands,detail=ctx['derived'],ctx['state'],ctx['commands'],ctx['detail']
    name=k12_container_name(derived['day'],derived['index'])
    words=k12_container_words(derived,name,w_labels(derived,ctx['bound']['request_sha256']))
    result=effect(state,commands,'create',*words,capture=True,docker_config=K12_DOCKER_CLI)
    detail['create']={key:result[key] for key in ('started','returned','returncode','code')}
    if not result['started']:return result['code'] or 'CREATE_NOT_STARTED'
    if not result['returned']:
        detail['after_create']=w_summary(w_try_inspect(commands,name));return 'CREATE_UNCERTAIN'
    output=result['output']
    if result['returncode']!=0 or not (len(output)==65 and text(output[:64].decode('ascii','replace'),CONTAINER_ID) and output[64:]==b'\n'):
        row=w_try_inspect(commands,name);detail['after_create']=w_summary(row)
        if row is None and w_listed_without(commands,name):state.fail();return 'CREATE_FAILED'
        state.unknown();return 'CREATE_RETURNED_WITHOUT_ITS_ID' if row is not None else 'CREATE_FAILED_STATE_UNKNOWN'
    identifier=output[:64].decode('ascii');row=w_try_inspect(commands,identifier);detail['after_create']=w_summary(row)
    if row is None or row['id']!=identifier or not k12_ours(row,derived,name,ctx['bound']['request_sha256']):
        state.unknown();return 'CREATED_CONTAINER_NOT_AS_SIGNED'
    if row['state']!='created' or row['started_at']!=K12_NEVER_STARTED:state.unknown();return 'CREATED_CONTAINER_NOT_AS_SIGNED'
    state.done();ctx['container_id']=identifier
    result=effect(state,commands,'start',identifier,docker_config=K12_DOCKER_CLI)
    detail['start']={key:result[key] for key in ('started','returned','returncode','code')}
    if not result['started']:return result['code'] or 'START_NOT_STARTED'
    row=w_try_inspect(commands,identifier);detail['after_start']=w_summary(row)
    if not result['returned']:return 'START_UNCERTAIN'
    if row is None or not k12_ours(row,derived,name,ctx['bound']['request_sha256']):state.unknown();return 'STARTED_CONTAINER_NOT_READ_BACK'
    if row['started_at']==K12_NEVER_STARTED and row['state']=='created':state.fail();return 'START_FAILED'
    if row['started_at']==K12_NEVER_STARTED:state.unknown();return 'STARTED_CONTAINER_NOT_READ_BACK'
    state.done()
    try:k12_release(ctx['host'],ctx['handles']['data'],ctx['gate'],derived)       # the bytes the writer read are still the signed ones
    except Exception as error:return 'RELEASE_CHANGED_DURING_LAUNCH'
    if result['returncode']!=0:return 'START_RETURNED_NONZERO'
    detail['launched']={'container_id':identifier,'container_name':name,'running':row['running'],'state':row['state'],
                        'parks_until':derived['view_opens_at']}
    return None

def w_identified(ctx,target):
    """The container of this window and launch request, by its deterministic name; refused unless it is ours."""
    derived=ctx['derived'];name=k12_container_name(derived['day'],derived['index'])
    row=w_try_inspect(ctx['commands'],target or name)
    need(row is not None,'CONTAINER_ABSENT')
    need(k12_ours(row,derived,name,ctx['plan']['launch_request_sha256']),'CONTAINER_NOT_OF_THIS_WINDOW')
    return row

def w_persist_precheck(ctx):
    host,gate,derived,handles,detail=ctx['host'],ctx['gate'],ctx['derived'],ctx['handles'],ctx['detail']
    handles['receipts']=w_hold(host,ctx['plan']['parent_rows']['receipts'],gate,detail['parents'].setdefault('receipts',[]))
    need(k12_entry(host,k12_persisted_name(derived['day'],derived['index']),handles['receipts'],gate) is None,'PERSISTED_RECEIPT_PRESENT')
    row=w_identified(ctx,None);detail['container']=w_summary(row)
    need(row['state']!='created','CONTAINER_NEVER_STARTED')
    need(row['state']=='exited' and row['running'] is False,'CONTAINER_NOT_EXITED')
    need(row['oom_killed'] is False and integer(row['exit_code'],0,255) and row['started_at']!=K12_NEVER_STARTED,'CONTAINER_EXIT_NOT_KNOWN')
    ctx['row']=row
    left=gate();detail['seconds_left_before_first_effect']=int(left)
    need(left>=effects_budget('logs')+W_ALLOWANCE_PERSIST_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')

def w_persist(ctx):
    derived,state,commands,detail,row=ctx['derived'],ctx['state'],ctx['commands'],ctx['detail'],ctx['row']
    result=effect(state,commands,'logs',row['id'],capture=True,docker_config=K12_DOCKER_CLI)
    detail['logs']={key:result[key] for key in ('started','returned','returncode','code')}
    if not result['started']:return result['code'] or 'LOGS_NOT_STARTED'
    if not result['returned']:return 'LOGS_UNCERTAIN'
    state.fail()                    # docker logs reads; the core counts it as an effect: settled as "nothing changed"
    if result['returncode']!=0:return 'LOGS_FAILED'
    stdout=result['output']
    if len(stdout)>K12_STDOUT_MAX_BYTES:return 'STDOUT_TOO_LARGE'
    again=w_try_inspect(commands,row['id'])
    if again is None or (again['id'],again['state'],again['finished_at'],again['exit_code'])!=(row['id'],row['state'],row['finished_at'],row['exit_code']):
        return 'CONTAINER_CHANGED_DURING_PERSIST'
    try:line=k12_receipt_line(stdout,derived['day'],row['exit_code'])
    except Refused as error:
        # nothing written: only one complete receipt is ever persisted (the code goes on to perform; the logs read is settled)
        detail['writer_line']={'valid':False,'code':str(error),'stdout_bytes':len(stdout)};raise
    detail['writer_line']={'valid':True,'code':None,'public':k12_line_public(line),'terminal':k12_terminal(line),'stdout_bytes':len(stdout)}
    body={'schema':K12_PERSISTED_SCHEMA,'epoch':K12_EPOCH,'day':derived['day'],'window':derived['window'],'window_slot':derived['index'],
          'container_id':row['id'],'container_name':row['name'][1:],'launch_request_sha256':ctx['plan']['launch_request_sha256'],
          'capacity_request_sha256':derived['sha256'],'persist_request_sha256':ctx['bound']['request_sha256'],'image_id':row['image_id'],
          'exit_code':row['exit_code'],'oom_killed':row['oom_killed'],'started_at':row['started_at'],'finished_at':row['finished_at'],
          'stdout_b64':base64.b64encode(stdout).decode('ascii'),'stdout_sha256':sha(stdout),'stdout_bytes':len(stdout)}
    content=canonical(body);path=K12_RECEIPTS+'/'+k12_persisted_name(derived['day'],derived['index'])
    entry=create_file(0,'PERSISTED_WRITER_RECEIPT',path,content,PRIVATE_FILE_MODE,ctx['handles']['receipts'],ctx['host'],ctx['gate'],state,ctx['go16'])
    ctx['ledger'].append(entry)
    if entry['state']!='INSTALLED_DURABLE':return entry['code'] or 'PERSIST_FAILED'
    return readback_file(entry,content,PRIVATE_FILE_MODE,ctx['handles']['receipts'],ctx['host'],ctx['gate'])

def w_stop_precheck(ctx):
    host,gate,derived,handles,detail=ctx['host'],ctx['gate'],ctx['derived'],ctx['handles'],ctx['detail']
    handles['manifests']=w_hold(host,ctx['plan']['parent_rows']['manifests'],gate,detail['parents'].setdefault('manifests',[]))
    detail['manifest_names_before']=w_manifest_state(ctx)
    row=w_identified(ctx,None);detail['container']=w_summary(row)
    need(row['state']=='running' and row['running'] is True,'CONTAINER_NOT_RUNNING')
    ctx['row']=row
    left=gate();detail['seconds_left_before_first_effect']=int(left)
    need(left>=effects_budget('stop')+W_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
    need((instant(derived['view_opens_at'])-ctx['clock']()).total_seconds()>=W_STOP_LEAD_SECONDS,'TOO_CLOSE_TO_THE_VIEW')

def w_manifest_state(ctx):
    """The day's manifest and the writer's temporaries of the day in the manifests directory: two counts and a flag.
    Names of other days and of other files are not reported."""
    day=ctx['derived']['day'];present=0;temporaries=0;pattern=r'\.'+re.escape(day+'.json')+r'\.[0-9a-f]{16}\.tmp'
    for name in ctx['host'].names(ctx['handles']['manifests'].fd):
        if name==day+'.json':present+=1
        elif re.fullmatch(pattern,name):temporaries+=1
    return {'manifest_present':present==1,'temporaries':temporaries}

def w_stop(ctx):
    state,commands,detail,row=ctx['state'],ctx['commands'],ctx['detail'],ctx['row']
    result=effect(state,commands,'stop',row['id'],docker_config=K12_DOCKER_CLI)
    detail['stop']={key:result[key] for key in ('started','returned','returncode','code')}
    if not result['started']:return result['code'] or 'STOP_NOT_STARTED'
    after=w_try_inspect(commands,row['id']);detail['after_stop']=w_summary(after)
    if not result['returned']:return 'STOP_UNCERTAIN'
    if after is not None and after['id']==row['id'] and after['state']=='exited' and after['running'] is False:state.done()
    elif after is not None and after['id']==row['id'] and after['running'] is True:
        state.fail();return 'STOP_FAILED'
    else:
        state.unknown();return 'STOPPED_CONTAINER_NOT_READ_BACK'
    try:
        ctx['handles']['manifests'].verify(ctx['gate']);detail['manifest_names_after']=w_manifest_state(ctx)
    except Exception as error:return code_of(error,'READBACK_UNAVAILABLE')
    if detail['manifest_names_after']!=detail['manifest_names_before']:return 'MANIFEST_DIRECTORY_CHANGED_DURING_STOP'
    if result['returncode']!=0:return 'STOP_RETURNED_NONZERO'
    return None

def w_remove_precheck(ctx):
    host,gate,handles,detail,commands=ctx['host'],ctx['gate'],ctx['handles'],ctx['detail'],ctx['commands']
    handles['receipts']=w_hold(host,ctx['plan']['parent_rows']['receipts'],gate,detail['parents'].setdefault('receipts',[]))
    rows=[]
    for item in ctx['plan']['removals']:
        name=k12_container_name(item['day'],item['window_slot'])
        row=w_try_inspect(commands,item['container_id'])
        need(row is not None,'CONTAINER_ABSENT')
        need(row['id']==item['container_id'] and row['name']=='/'+name and row['image_id']==item['image_id']
             and row['request_label']==item['launch_request_sha256'] and row['capacity_label']==item['capacity_request_sha256']
             and row['auto_remove'] is False,'CONTAINER_NOT_OF_THIS_FAMILY')
        need(row['running'] is False and row['state'] in ('exited','created'),'CONTAINER_NOT_STOPPED')
        need(row['state']=='exited' or row['started_at']==K12_NEVER_STARTED,'CONTAINER_NOT_STOPPED')
        if row['state']=='exited':
            raw,facts=k12_file(host,k12_persisted_name(item['day'],item['window_slot']),handles['receipts'],gate,K12_PERSISTED_MAX_BYTES)
            if raw is None and k12_stopped(row['exit_code'],row['oom_killed'],row['finished_at'],k12_at(item['day'],K12_VIEW_UTC[item['window_slot']])):
                rows.append(w_summary(row));continue        # ended by D4's stop before its view: no receipt was ever printed
            need(raw is not None,'PERSISTED_RECEIPT_MISSING');need(k12_private(facts),'PERSISTED_RECEIPT_NOT_PRIVATE')
            k12_persisted(raw,{'epoch':K12_EPOCH,'day':item['day'],'window_slot':item['window_slot'],'container_id':item['container_id'],
                               'container_name':name,'launch_request_sha256':item['launch_request_sha256'],
                               'capacity_request_sha256':item['capacity_request_sha256'],'image_id':item['image_id']})
        rows.append(w_summary(row))
    detail['containers']=rows
    listed=container_list(commands,docker_config=K12_DOCKER_CLI);named={item['container_id'] for item in ctx['plan']['removals']}
    detail['family_containers_not_named']=sorted(row['name'] for row in listed if row['name'].startswith('c3po-k12-') and row['id'] not in named)
    left=gate();detail['seconds_left_before_first_effect']=int(left)
    need(left>=effects_budget('remove')+W_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')

def w_remove(ctx):
    state,commands,detail=ctx['state'],ctx['commands'],ctx['detail']
    identifiers=[item['container_id'] for item in ctx['plan']['removals']]
    result=effect(state,commands,'remove',*identifiers,capture=True,docker_config=K12_DOCKER_CLI)
    detail['remove']={key:result[key] for key in ('started','returned','returncode','code')}
    if not result['started']:return result['code'] or 'REMOVE_NOT_STARTED'
    try:listed={row['id'] for row in container_list(commands,docker_config=K12_DOCKER_CLI)}
    except Exception as error:
        if result['returned']:state.unknown()
        return code_of(error,'READBACK_UNAVAILABLE')
    removed=[identifier for identifier in identifiers if identifier not in listed]
    detail['removed']=len(removed);detail['left']=len(identifiers)-len(removed)
    if not result['returned']:return 'REMOVE_UNCERTAIN'
    if removed:state.done()
    else:state.fail()
    if len(removed)!=len(identifiers):return 'REMOVE_INCOMPLETE'
    if result['returncode']!=0:return 'REMOVE_RETURNED_NONZERO'
    return None

W_STEPS={'LAUNCH':(w_launch_precheck,w_launch),'PERSIST':(w_persist_precheck,w_persist),'STOP':(w_stop_precheck,w_stop),
         'REMOVE':(w_remove_precheck,w_remove)}

def _reduce_parents(receipt):receipt['parents']={key:len(value) for key,value in (receipt.get('parents') or {}).items()}
def _reduce_detail(receipt):receipt['detail']={'reduced_for_size':True}
REDUCTIONS=[('PARENTS_REDUCED_TO_COUNT',_reduce_parents),('DETAIL_DROPPED',_reduce_detail)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    derived=w_derived(plan)                   # pure: everything the run will put on the engine, and nothing else
    gate()                                    # first gate call: before anything is observed
    state.started=True
    commands=Commands(host,gate);ledger=[];handles={}
    detail={'parents':{}}
    ctx={'plan':plan,'derived':derived,'host':host,'gate':gate,'commands':commands,'state':state,'bound':bound,'clock':clock,
         'handles':handles,'detail':detail,'ledger':ledger,'go16':bound['go_sha256'][:16]}
    def finish(status,outcome,code,extra):
        parents=detail.pop('parents',{})
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),mode=plan['mode'],
            clock=timing(begun,mark,clock,monotonic),commands_started=dict(commands.started),mutating_calls=state.counts(),parents=parents,
            detail=detail,ledger=ledger,objects_left_by_this_run=objects_left([],ledger),pre_existing_objects_modified=False,**extra)))
    precheck,step=W_STEPS[plan['mode']]
    try:
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o077)
            w_clock(plan,derived,begun)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            precheck(ctx)
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})
        try:stop=step(ctx)
        except Exception as error:
            stop=code_of(error,'EFFECT_STEP_FAILED')
            if state.pending:state.unknown()
        extra={'phase_reached':'EFFECTS','container_id':ctx.get('container_id')}
        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)
    finally:
        for handle in handles.values():
            try:handle.close()
            except Exception:pass
