import base64

OPERATION='GO_READONLY_HOSTOPS02_K12_COLLECT_01'
PHASE='READONLY_K12_CAPACITY_WINDOW_COLLECT'
REQUEST_SCHEMA='READONLY_HOSTOPS02_K12_COLLECT_REQUEST_V1'
AUTHORITY_SCHEMA='READONLY_HOSTOPS02_K12_COLLECT_AUTHORITY_V1'
GO_SCHEMA='READONLY_HOSTOPS02_K12_COLLECT_GO_V1'
RECEIPT_SCHEMA='READONLY_HOSTOPS02_K12_COLLECT_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_K12_COLLECT_PLAN_V1'
SOURCE_NAME='k12_collect.py'
WRITES_ALLOWED=False
ACTIVATION_ALLOWED=False
DATE_CLASS='READ'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
EVIDENCE_OPERATIONS=()
MAX_GATE_SPAN_SECONDS=3600
COMPLETE_OUTCOME='K12_OBSERVED_AS_REQUIRED'
PARTIAL_OUTCOME='OBSERVED_ALL_EXPECTATIONS_NOT_MET'
REFUSED_OUTCOME='REFUSED_NOTHING_OBSERVED'
REDUCED_OUTCOME='RECEIPT_REDUCED_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_OBSERVED'
PLAN_KEYS=frozenset(('mode','capacity_request','launch_request_sha256','tree_journal','parent_rows','evidence_boot_id_sha256'))

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

C_MODES=('COLLECT','TREE')
C_COLLECT_AFTER_VIEW_SECONDS=60           # MASTER_PLAN D2: "view + 60 s"
C_PATHS={'capacity_root':K12_CAPACITY_ROOT,'config':K12_CONFIG_ROOT,'manifests':K12_MANIFESTS,'reader_config':K12_READER_CONFIG,
         'docker_cli':K12_DOCKER_CLI,'receipts':K12_RECEIPTS,'data':K12_RELEASE_DIR}
# The journal's path is the plan's (the REQUEST's bind). Every directory of the tree must be controlled by root alone from
# '/' (Codex 6) and root:root 0700 at its leaf, except the release directory in the named read-only data volume
# (Codex #429 5986698996), judged by k12_data_chain.
C_TREE=('capacity_root','config','manifests','reader_config','docker_cli','journal','data','receipts')
C_COLLECT_CHAINS=('manifests','receipts','data')
C_VERDICTS=('VERIFIED','TERMINAL_EMPTY_LIST','STOPPED_BEFORE_THE_VIEW','NOT_VERIFIED','PENDING_PERSIST','UNCERTAIN')
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'inspect':command_row('docker',['container','inspect','--format',K12_FORMAT],'one container name of this family','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ')}

SCOPE_STATEMENT=('Read-only, epoch '+K12_EPOCH+'. COLLECT: docker container inspect, with this family\'s own format and never the '
                 'environment, of the container c3po-k12-<yyyymmdd>-w<index> of one window; the private receipt k12-<day>-w<index>.writer.json '
                 'in '+K12_RECEIPTS+' and the writer\'s line in it; the day\'s manifest in '+K12_MANIFESTS+' (metadata, and its SHA-256 '
                 'compared on the host with the line\'s). TREE: the rows of every directory a K12 request walks, the boot, and the '
                 'metadata of the environment files and of the journal catalog, each directory judged controlled by root alone from \'/\' '
                 '(uid 0, gid 0, no group or other write, no setgid, no link). Nothing is created, written, removed, started, stopped '
                 'or pulled; no secret file is opened; the manifest hash and the symbol count never leave the host.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,'epoch':K12_EPOCH,'days':list(K12_DAYS),'modes':list(C_MODES),
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'verdicts':list(C_VERDICTS),'collect_after_view_seconds':C_COLLECT_AFTER_VIEW_SECONDS,
       'placement':{key:C_PATHS[key] for key in sorted(C_PATHS)},'journal_forbidden':list(K12_JOURNAL_FORBIDDEN),
       'data_target':K12_DATA_TARGET,'data_volume_read_only_exception':K12_DATA_VOLUME,
       'release':K12_RELEASE_DIR+'/'+K12_RELEASE_FILE,'source_root_never_bound':K12_SOURCE_ROOT,
       'chain_rule':'ROOT_CONTROLLED_UID0_GID0_NO_GROUP_OR_OTHER_WRITE_NO_SETGID_NO_LINK',
       'persisted':{'schema':K12_PERSISTED_SCHEMA,'keys':sorted(K12_PERSISTED_KEYS)},'inspect_format':K12_FORMAT,
       'never':['a write','a container started, stopped or removed','docker logs','the environment of a container','the bytes of secret.env',
                'the manifest hash or the symbol count in a receipt','a symbol'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'manifest_bytes':K12_MANIFEST_MAX_BYTES,'persisted_bytes':K12_PERSISTED_MAX_BYTES}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner):
    """The read primitives and the fixed-argv runner; nothing that creates, writes or removes."""


# ---------------------------------------------------------------- the plan (pure)
def c_path(name,plan):return plan['tree_journal'] if name=='journal' else C_PATHS[name]

def c_binds(plan):
    """TREE: the journal the REQUESTs will bind, judged as the REQUEST's bind is."""
    k12_journal({'source':plan['tree_journal'],'target':'/c3po-journal','readonly':True})

def c_derived(plan):
    mode=plan['mode'];need(mode in C_MODES,'MODE_INVALID')
    if mode=='TREE':
        need(plan['capacity_request'] is None and plan['launch_request_sha256'] is None and plan['parent_rows'] is None
             and plan['evidence_boot_id_sha256'] is None,'MODE_MEMBERS_INVALID')
        try:c_binds(plan)
        except Refused:raise Refused('TREE_BINDS_INVALID') from None
        return None
    need(plan['tree_journal'] is None and hexpin(plan['launch_request_sha256']),'MODE_MEMBERS_INVALID')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    derived=k12_capacity_request(plan['capacity_request'])[2]
    rows=plan['parent_rows'];need(type(rows) is dict and set(rows)==set(C_COLLECT_CHAINS),'PARENT_ROWS_INVALID')
    for name in C_COLLECT_CHAINS:
        if name=='data':k12_data_chain(rows[name]);continue
        k12_root_chain(rows[name],C_PATHS[name])
        need((rows[name][-1]['uid'],rows[name][-1]['gid'],rows[name][-1]['mode'])==(0,0,0o700),'DIRECTORY_NOT_ROOT_PRIVATE')
    return derived

def validate_plan(plan):c_derived(plan)

def effects_of(plan):
    derived=c_derived(plan);mode=plan['mode']
    out={'operation':OPERATION,'mode':mode,'epoch':K12_EPOCH,'writes':0,'containers_started_stopped_or_removed':0,'secret_files_opened':0,
         'activation':False}
    if mode=='TREE':
        out['reads']={'directories':{name:c_path(name,plan) for name in C_TREE},
                      'chain_rule':'ROOT_CONTROLLED_UID0_GID0_NO_GROUP_OR_OTHER_WRITE_NO_SETGID_NO_LINK',
                      'metadata_only':[K12_SECRET_ENV,K12_PINS_ENV,plan['tree_journal']+'/epoch.json',plan['tree_journal']+'/maintenance.lock',
                                        K12_RELEASE_DIR+'/'+K12_RELEASE_FILE],
                      'boot':BOOT_ID_PATH}
        return out
    name=k12_container_name(derived['day'],derived['index'])
    out.update(evidence_boot_id_sha256=plan['evidence_boot_id_sha256'],capacity_request_sha256=derived['sha256'],day=derived['day'],
               window=derived['window'],window_slot=derived['index'],launch_request_sha256=plan['launch_request_sha256'],
               chains={key:chain_effects(plan['parent_rows'][key]) for key in C_COLLECT_CHAINS},
               reads={'container':['container','inspect','--format','<K12_FORMAT>',name],
                      'persisted':K12_RECEIPTS+'/'+k12_persisted_name(derived['day'],derived['index']),
                      'manifest':K12_MANIFESTS+'/'+derived['day']+'.json'},
               not_before=k12_at(derived['day'],K12_VIEW_UTC[derived['index']])+' + %d s'%C_COLLECT_AFTER_VIEW_SECONDS)
    return out
def success_of(plan):return COMPLETE_OUTCOME


# ---------------------------------------------------------------- the reads
def c_observe(action):
    """One item on its own: a failure is UNAVAILABLE with a constant code, never an absence."""
    try:
        value=action();value.setdefault('status','COMPLETE');return value
    except Refused as error:
        if str(error) in ('GO_EXPIRED','CLOCK_REVERSED'):raise
        return safe(error)
    except OSError as error:return safe(error)

def c_container(commands,derived,name,launch):
    try:row=k12_inspect(commands.output('inspect',name,docker_config=K12_DOCKER_CLI))
    except CommandFailed:
        # absent only when a listing of every container succeeds without the name; otherwise unreadable
        need(name not in [item['name'] for item in container_list(commands,docker_config=K12_DOCKER_CLI)],'CONTAINER_UNREADABLE')
        return {'present':False,'code':'CONTAINER_ABSENT'}
    return {'present':True,'ours':k12_ours(row,derived,name,launch),'id':row['id'],'state':row['state'],'running':row['running'],
            'exit_code':row['exit_code'],'oom_killed':row['oom_killed'],'started':row['started_at']!=K12_NEVER_STARTED,
            'started_at':row['started_at'],'finished_at':row['finished_at']}

def c_persisted(host,held,gate,derived,name,launch,container):
    raw,facts=k12_file(host,k12_persisted_name(derived['day'],derived['index']),held,gate,K12_PERSISTED_MAX_BYTES)
    if raw is None:return {'present':False}
    expected={'epoch':K12_EPOCH,'day':derived['day'],'window':derived['window'],'window_slot':derived['index'],'container_name':name,
              'launch_request_sha256':launch,'capacity_request_sha256':derived['sha256'],'image_id':derived['image_id']}
    out={'present':True,'private':k12_private(facts)}
    try:value,stdout=k12_persisted(raw,expected)
    except Refused as error:
        out['valid']=False;out['code']=code_of(error,'PERSISTED_RECEIPT_INVALID');return out
    out['valid']=True
    out['of_this_container']=bool(container.get('present')) and (value['container_id'],value['exit_code'],value['oom_killed'],value['started_at'],
                                                                  value['finished_at'])==(container.get('id'),container.get('exit_code'),
                                                                  container.get('oom_killed'),container.get('started_at'),container.get('finished_at'))
    out['exit_code']=value['exit_code'];out['stdout_bytes']=value['stdout_bytes']
    ended,detail=k12_ended(value,stdout,derived['day'],derived['view_opens_at'])
    out['ended']=ended;out['line_valid']=ended=='LINE';out['line_code']=None if ended!='UNKNOWN' else detail
    out['_line']=detail if ended=='LINE' else None
    return out

def c_manifest(host,held,gate,day):
    """The day's manifest on the host: metadata, and its hash kept in memory for one comparison."""
    out={'present':False,'temporaries':0,'_sha256':None};pattern=r'\.'+re.escape(day+'.json')+r'\.[0-9a-f]{16}\.tmp'
    for name in host.names(held.fd):
        if re.fullmatch(pattern,name):out['temporaries']+=1
    found=k12_entry(host,day+'.json',held,gate)
    if found is None:return out
    out.update(present=True,type=found['type'],uid=found['uid'],gid=found['gid'],mode_octal=found['mode_octal'],links=found['links'],
               private=k12_private(found))
    if found['type']=='file':
        raw,_=read_regular(host,day+'.json',held.fd,gate,K12_MANIFEST_MAX_BYTES);out['_sha256']=sha(raw);out['bytes_within_limit']=True
    return out

def c_unless_published(manifest,reason):
    """A window that did not run allows the next one, unless the day's manifest is on the host (or cannot be read)."""
    if manifest.get('status')!='COMPLETE':return 'UNCERTAIN','MANIFEST_UNAVAILABLE'
    if manifest['present']:return 'UNCERTAIN','MANIFEST_PRESENT_WITHOUT_THIS_WINDOW'
    return 'NOT_VERIFIED',reason

def c_release(host,held,gate,derived):
    """The release now: its bytes hashed against the REQUEST's (the writer read them; a change is observable here)."""
    try:return {'as_signed':k12_release(host,held,gate,derived)}
    except Refused as error:return {'as_signed':False,'code':str(error)}

def c_verdict(derived,container,persisted,manifest,release):
    """(verdict, reason) of the window; first match wins (DESIGN.md section 4)."""
    if container.get('status')!='COMPLETE':return 'UNCERTAIN','CONTAINER_UNAVAILABLE'
    if not container['present']:return c_unless_published(manifest,'CONTAINER_ABSENT')
    if not container['ours']:return 'UNCERTAIN','CONTAINER_NOT_OF_THIS_WINDOW'
    if container['running'] or container['state'] not in ('exited','created'):return 'UNCERTAIN','CONTAINER_NOT_SETTLED'
    if container['state']=='created':return c_unless_published(manifest,'NEVER_STARTED') if not container['started'] else ('UNCERTAIN','CONTAINER_NOT_SETTLED')
    if persisted.get('status')!='COMPLETE':return 'UNCERTAIN','PERSISTED_RECEIPT_UNAVAILABLE'
    if not persisted['present'] and k12_stopped(container['exit_code'],container['oom_killed'],container['finished_at'],derived['view_opens_at']):
        return 'STOPPED_BEFORE_THE_VIEW','STOPPED_BEFORE_ITS_VIEW'    # D4's stop: PERSIST keeps nothing of an empty output
    if not persisted['present']:return 'PENDING_PERSIST','LINE_NOT_YET_PERSISTED'
    if not persisted['valid']:return 'UNCERTAIN','PERSISTED_RECEIPT_INVALID'
    if not persisted['private']:return 'UNCERTAIN','PERSISTED_RECEIPT_NOT_PRIVATE'
    if not persisted['of_this_container']:return 'UNCERTAIN','PERSISTED_RECEIPT_NOT_OF_THIS_CONTAINER'
    if persisted['ended']=='STOPPED':return 'STOPPED_BEFORE_THE_VIEW','STOPPED_WITHOUT_A_LINE'
    if release.get('status')!='COMPLETE':return 'UNCERTAIN','RELEASE_UNAVAILABLE'
    if not release['as_signed']:return 'UNCERTAIN','RELEASE_NOT_THE_SIGNED_BYTES'     # Codex #429 5986698996
    if persisted['ended']!='LINE':return 'UNCERTAIN',persisted['line_code']
    line=persisted['_line']                 # one complete receipt of this day's publish run, consistent with the exit code (k12_ended)
    if line.get('capacity_config_sha256',derived['config_sha256'])!=derived['config_sha256'] or line.get('release_sha256',derived['release_sha256'])!=derived['release_sha256'] \
       or line.get('package_sha256',derived['package_sha256'])!=derived['package_sha256'] or line.get('build_sha',derived['build_sha'])!=derived['build_sha'] \
       or line.get('owner_uid',0)!=0:
        return 'UNCERTAIN','LINE_PINS_NOT_THE_SIGNED_ONES'
    if manifest.get('status')!='COMPLETE':return 'UNCERTAIN','MANIFEST_UNAVAILABLE'
    if k12_terminal(line)=='EMPTY_LIST':
        return ('TERMINAL_EMPTY_LIST','MANIFEST_SYMBOLS_EMPTY') if not manifest['present'] else ('UNCERTAIN','MANIFEST_PRESENT_WITH_AN_EMPTY_LIST')
    if line['status'] not in K12_WRITER_PUBLISHED:return 'NOT_VERIFIED','WRITER_'+line['status']
    if not (manifest['present'] and manifest['private'] and manifest['_sha256'] is not None and manifest['_sha256']==line.get('manifest_sha256')):
        return 'UNCERTAIN','MANIFEST_NOT_AS_THE_LINE_SAYS'
    if line.get('owner_uid')!=0 or line.get('capacity_config_sha256')!=derived['config_sha256'] or line.get('release_sha256')!=derived['release_sha256'] \
       or line.get('package_sha256')!=derived['package_sha256'] or line.get('build_sha')!=derived['build_sha']:
        return 'UNCERTAIN','LINE_PINS_NOT_THE_SIGNED_ONES'
    if line['status']=='PUBLISHED_VERIFIED' and derived['require_go_mode'] is not None and line.get('go_mode')!=derived['require_go_mode']:
        return 'UNCERTAIN','GO_MODE_NOT_THE_AUTHORISED_ONE'
    return 'VERIFIED','PUBLISHED_AND_READ_BACK'

def c_public(item):return {key:value for key,value in item.items() if not key.startswith('_')}

def c_collect(plan,derived,host,gate,commands,items,handles,detail):
    name=k12_container_name(derived['day'],derived['index']);launch=plan['launch_request_sha256']
    for key in C_COLLECT_CHAINS:
        observed=detail.setdefault('parents',{}).setdefault(key,[])
        def hold(key=key,observed=observed):
            handles[key]=Pinned(host,walk_pinned(host,plan['parent_rows'][key],gate,observed),rows=plan['parent_rows'][key]);return {}
        items['directory:'+key]=c_observe(hold)
    container=items['container']=c_observe(lambda:c_container(commands,derived,name,launch))
    if 'receipts' in handles:
        persisted=items['persisted']=c_observe(lambda:c_persisted(host,handles['receipts'],gate,derived,name,launch,container))
    else:persisted=items['persisted']={'status':'UNAVAILABLE','code':'DIRECTORY_NOT_HELD'}
    if 'manifests' in handles:manifest=items['manifest']=c_observe(lambda:c_manifest(host,handles['manifests'],gate,derived['day']))
    else:manifest=items['manifest']={'status':'UNAVAILABLE','code':'DIRECTORY_NOT_HELD'}
    def stable():
        for handle in handles.values():handle.verify(gate)
        return {}
    items['directories_stable']=c_observe(stable)
    if 'data' in handles:release=items['release']=c_observe(lambda:c_release(host,handles['data'],gate,derived))
    else:release=items['release']={'status':'UNAVAILABLE','code':'DIRECTORY_NOT_HELD'}
    verdict,reason=c_verdict(derived,container,persisted,manifest,release)
    line=persisted.get('_line') if persisted.get('status')=='COMPLETE' else None
    equal=None
    if line is not None and manifest.get('status')=='COMPLETE' and manifest.get('_sha256') is not None:equal=manifest['_sha256']==line.get('manifest_sha256')
    findings=[]
    if items['directories_stable']['status']!='COMPLETE':findings.append('DIRECTORIES_NOT_STABLE')
    top={'window_verdict':verdict,'window_reason':reason,'contingency_allowed':verdict=='NOT_VERIFIED','day_decided':verdict in ('VERIFIED','TERMINAL_EMPTY_LIST','STOPPED_BEFORE_THE_VIEW'),
         'writer_line':None if line is None else k12_line_public(line),'manifest_sha256_equals_the_line':equal,
         'binding_may_be_committed':None if line is None else line.get('prepare_status') in ('ATTEMPTED',)+K12_COMMITTED,
         'container_name':name,'container_id':container.get('id'),'exit_code':container.get('exit_code'),
         'manifest_on_host':None if manifest.get('status')!='COMPLETE' else {'present':manifest['present'],'private_one_link':bool(manifest.get('private'))}}
    complete=verdict=='VERIFIED' and not findings and all(item.get('status')=='COMPLETE' for item in items.values())
    return complete,top,findings

def c_tree(plan,host,gate,items,detail):
    """TREE: rows of every directory (descend, no link followed), their privacy, the env files and the catalog by lstat."""
    rows={};handles={}
    try:
        for key in C_TREE:
            def one(key=key):
                found=[];fd=descend(host,c_path(key,plan),gate,found);rows[key]=found
                handles[key]=Pinned(host,fd,rows=found);leaf=found[-1]
                return {'rows':found,'private':(leaf['uid'],leaf['gid'],leaf['mode'])==(0,0,0o700),'mount_point_by_device_change':mount_point_of(found)}
            items['directory:'+key]=c_observe(one)
        def files():
            out={}
            for key,name in (('reader_config','secret.env'),('reader_config','pins.env'),('journal','epoch.json'),('journal','maintenance.lock'),
                             ('data',K12_RELEASE_FILE)):
                found=k12_entry(host,name,handles[key],gate);out[name]={'present':found is not None,'private':k12_private(found)}
            out['docker_cli_entries']=count_entries(host,handles['docker_cli'].fd,gate);return out
        items['files']=c_observe(files) if all(key in handles for key in ('reader_config','journal','docker_cli','data')) else {'status':'UNAVAILABLE','code':'DIRECTORY_NOT_HELD'}
    finally:
        for handle in handles.values():
            try:handle.close()
            except Exception:pass
    findings=[]
    for key in C_TREE:
        item=items['directory:'+key]
        if item['status']!='COMPLETE':continue
        if not item['private']:findings.append('DIRECTORY_NOT_ROOT_PRIVATE:'+key)
        # Codex 6: every component from '/' controlled by root alone (no open root anywhere)
        try:
            if key=='data':k12_data_chain(item['rows'])
            else:k12_root_chain(item['rows'],c_path(key,plan))
        except Refused as error:findings.append(code_of(error,'CHAIN_ROW_UNSAFE')+':'+key)
    if items['files']['status']=='COMPLETE':
        for name in ('secret.env','pins.env','epoch.json','maintenance.lock',K12_RELEASE_FILE):
            if not items['files'][name]['private']:findings.append('FILE_NOT_ROOT_PRIVATE:'+name)
        if items['files']['docker_cli_entries']!=0:findings.append('DOCKER_CLI_DIRECTORY_NOT_EMPTY')
    complete=not findings and all(item.get('status')=='COMPLETE' for item in items.values())
    return complete,{'observed_rows':{key:items['directory:'+key].get('rows') for key in C_TREE}},findings

def _reduce_items(receipt):receipt['items']={key:{'status':value.get('status')} for key,value in (receipt.get('items') or {}).items()}
def _reduce_parents(receipt):receipt['parents']={key:len(value) for key,value in (receipt.get('parents') or {}).items()}
REDUCTIONS=[('PARENTS_REDUCED_TO_COUNT',_reduce_parents),('ITEMS_REDUCED_TO_STATUS',_reduce_items)]

def c_window(plan,derived,begun):
    if plan['mode']=='TREE':return
    view=instant(derived['view_opens_at'])
    need(begun.date().isoformat()==derived['day'],'RUN_NOT_ON_THE_DAY_OF_THE_WINDOW')
    need((begun-view).total_seconds()>=C_COLLECT_AFTER_VIEW_SECONDS,'COLLECT_BEFORE_THE_VIEW_AND_A_MINUTE')

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    derived=c_derived(plan)
    gate()
    state.started=True
    commands=Commands(host,gate);items={};detail={};handles={}
    def finish(status,outcome,code,extra):
        parents=detail.pop('parents',{})
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),mode=plan['mode'],
            clock=timing(begun,mark,clock,monotonic),commands_started=dict(commands.started),mutating_calls=state.counts(),
            items={key:c_public(value) for key,value in items.items()},parents=parents,**extra)))
    try:
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            c_window(plan,derived,begun)
            boot=boot_id_sha256(host,gate)
            if plan['mode']=='COLLECT':need(boot==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'BEFORE_OBSERVATION'})
        try:
            if plan['mode']=='TREE':complete,top,findings=c_tree(plan,host,gate,items,detail);top['boot_id_sha256']=boot
            else:complete,top,findings=c_collect(plan,derived,host,gate,commands,items,handles,detail)
        except Refused as error:
            return finish(PARTIAL_STATUS,ESCAPED_OUTCOME,code_of(error,'RUN_STOPPED'),{'phase_reached':'OBSERVATION','findings':['RUN_STOPPED'],
                                                                              'window_verdict':'UNCERTAIN','window_reason':'RUN_STOPPED'})
        extra=dict(top,phase_reached='OBSERVATION',findings=findings)
        if complete:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,None,extra)
    finally:
        for handle in handles.values():
            try:handle.close()
            except Exception:pass
