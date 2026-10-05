import base64

OPERATION='GO_WRITE_HOSTOPS02_INSTALL_RELEASE_01'
PHASE='WRITE_INSTALL_RELEASE_NO_ACTIVATION'
REQUEST_SCHEMA='WRITE_HOSTOPS02_INSTALL_RELEASE_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_INSTALL_RELEASE_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_INSTALL_RELEASE_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_INSTALL_RELEASE_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_INSTALL_RELEASE_PLAN_V1'
SOURCE_NAME='install_release.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False
DATE_CLASS='WRITE_FIRST_SESSION'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,)
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='RELEASE_INSTALLED_BYTES_READ_BACK_NOT_ACTIVATED'
PARTIAL_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
PLAN_KEYS=frozenset(('parent','release','evidence_boot_id_sha256'))
RELEASE_KEYS=frozenset(('path','content_b64','sha256','bytes'))

# ---- the constants of this epoch. A request cannot move any of them: they are bytes of the signed source.
RELEASE_EPOCH='R2D2-V2-SHADOW-2026-10-05'
FIRST_SESSION='2026-10-05'
RELEASE_SCHEMA_NAME='R2D2_V2_RELEASE_V3'
RELEASE_MODE='CERTIFIED'
# The New York calendar day of the first session, as two UTC instants. New York is on daylight time (UTC-4) until
# 2026-11-01, so its 5 October runs from 04:00 UTC of the 5th to 04:00 UTC of the 6th. The date class of the family
# already confines a run to the UTC day 2026-10-05; together a run lies between 04:00 and 24:00 UTC of that day.
NEW_YORK_DAY_UTC=('2026-10-05T04:00:00+00:00','2026-10-06T04:00:00+00:00')
# Where the application's worker finds a release: the data volume is bound at /app/day-d-data in the compose worker,
# and the earlier epochs installed <volume>/r2d2-v2-release-<YYYYMMDD>/release.CERTIFIED.json. A DIRECTORY of that name
# is not an entry the security guard reads (it reads root-level r2d2-v2-release-*.json files).
DATA_VOLUME='/mnt/day-d-data'
RELEASE_DIRECTORY_NAME='r2d2-v2-release-20261005'
RELEASE_FILE_NAME='release.CERTIFIED.json'
RELEASE_DIRECTORY=DATA_VOLUME+'/'+RELEASE_DIRECTORY_NAME
RELEASE_PATH=RELEASE_DIRECTORY+'/'+RELEASE_FILE_NAME
CONTAINER_DATA_VOLUME='/app/day-d-data'
CONTAINER_RELEASE_PATH=CONTAINER_DATA_VOLUME+'/'+RELEASE_DIRECTORY_NAME+'/'+RELEASE_FILE_NAME
MAINTENANCE_PIN_NAME='.r2d2-v2-pinned'
MAINTENANCE_PIN=DATA_VOLUME+'/'+MAINTENANCE_PIN_NAME
MAX_RELEASE_BYTES=32768                   # the worker refuses a release file above 65536 bytes; a signed document holds at most 65536
FREE_BYTES_FLOOR=1048576                  # bytes a non-root writer must still have on the data volume before the first creation
WRITE_ALLOWANCE_SECONDS=15                # what must be left of the budget before the first creation (the writes take milliseconds)

SCOPE_STATEMENT=('Creates the private directory '+RELEASE_DIRECTORY+' (root:root 0700) in the pinned root of the data volume and, in it, the file '
                 +RELEASE_FILE_NAME+' (root:root 0600) holding exactly the release bytes whose SHA-256 and size the request signs, for epoch '
                 +RELEASE_EPOCH+' on its first session day only. Exclusive creation, fsync and a byte readback through a descriptor inside the run. '
                 'Nothing that exists is overwritten, renamed, chmodded, chowned or removed, except the temporary of this run once its identity is '
                 'proved. No process is started, no container is created or recreated, nothing is activated, and the release is not verified with '
                 'the application here.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'epoch':RELEASE_EPOCH,'first_session':FIRST_SESSION,'new_york_day_utc':list(NEW_YORK_DAY_UTC),
       'release':{'schema':RELEASE_SCHEMA_NAME,'mode':RELEASE_MODE,'max_bytes':MAX_RELEASE_BYTES},
       'paths':{'data_volume':DATA_VOLUME,'release_directory':RELEASE_DIRECTORY,'release_file':RELEASE_PATH,
                'release_file_in_the_worker':CONTAINER_RELEASE_PATH,'maintenance_pin':MAINTENANCE_PIN},
       'files':FILES_SCOPE,'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'file_contents_read':[BOOT_ID_PATH,'the release file this run delivered (readback inside the run)'],
       'processes_started':0,
       'never':['overwrite','chmod','chown','rename','truncate','removal of anything but the temporary this run created','a process','docker','systemctl',
                'a shell','a network connection','activation','a recreate of any container','a second attempt'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'release_bytes':MAX_RELEASE_BYTES,'free_bytes_floor':FREE_BYTES_FLOOR,'write_allowance_seconds':WRITE_ALLOWANCE_SECONDS}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeFiles):
    """Everything this source can do to the host: the read primitives and the seven creating calls. No process."""


def release_of(plan):
    """The release bytes the request carries, decoded and compared with the signed hash and size. Pure."""
    item=plan['release']
    need(type(item) is dict and set(item)==set(RELEASE_KEYS),'RELEASE_PLAN_INVALID')
    need(item['path']==RELEASE_PATH,'RELEASE_PATH_NOT_THE_SIGNED_CONSTANT')
    need(file_request(RELEASE_FILE_NAME,item['sha256'],item['bytes'],PRIVATE_FILE_MODE) and item['bytes']<=MAX_RELEASE_BYTES,'RELEASE_PLAN_INVALID')
    need(type(item['content_b64']) is str,'RELEASE_BYTES_NOT_THE_SIGNED_HASH')
    try:raw=base64.b64decode(item['content_b64'].encode('ascii'),validate=True)
    except (ValueError,UnicodeEncodeError):raise Refused('RELEASE_BYTES_NOT_THE_SIGNED_HASH') from None
    need(len(raw)==item['bytes'] and sha(raw)==item['sha256'],'RELEASE_BYTES_NOT_THE_SIGNED_HASH')
    return raw

def release_facts(raw):
    """What the release says of itself, decoded as the application decodes it (one JSON object, no duplicate key, no
    non-finite number). Only the scope is judged here: schema, mode, epoch and first session are constants of this
    source. Whether the release verifies is the application's question, asked in a container by the epoch readback."""
    try:body=strict(raw)
    except Refused:raise Refused('RELEASE_NOT_JSON') from None
    need(type(body) is dict,'RELEASE_NOT_JSON')
    need(body.get('schema')==RELEASE_SCHEMA_NAME and body.get('mode')==RELEASE_MODE,'RELEASE_NOT_A_CERTIFIED_V3_RELEASE')
    need(body.get('epoch')==RELEASE_EPOCH,'RELEASE_EPOCH_NOT_THIS_EPOCH')
    need(body.get('first_session')==FIRST_SESSION,'RELEASE_FIRST_SESSION_NOT_THIS_EPOCH')
    need(text(body.get('code_revision'),'[0-9a-f]{40}') and hexpin(body.get('implementation_package_sha'))
         and text(body.get('approved_at'),'[0-9T:.+Z-]{1,40}'),'RELEASE_FIELDS_INVALID')
    return {'schema':body['schema'],'mode':body['mode'],'epoch':body['epoch'],'first_session':body['first_session'],
            'code_revision':body['code_revision'],'implementation_package_sha':body['implementation_package_sha'],'approved_at':body['approved_at']}

def validate_plan(plan):
    validate_chain(plan['parent'],DATA_VOLUME,open_root=DATA_VOLUME,receives_entry=True)
    need(mount_point_of(plan['parent'])==DATA_VOLUME,'DATA_VOLUME_NOT_A_MOUNT_POINT')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    release_facts(release_of(plan))
    need(instant(NEW_YORK_DAY_UTC[0])<=instant(plan['window']['not_before']) and instant(plan['window']['expires_at'])<=instant(NEW_YORK_DAY_UTC[1]),
         'WINDOW_NOT_ON_THE_FIRST_SESSION_DAY_IN_NEW_YORK')

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    return {'operation':OPERATION,'parent':chain_effects(plan['parent']),'open_root':DATA_VOLUME,
            'directory':{'path':RELEASE_DIRECTORY,'mode_octal':'%04o'%PRIVATE_DIRECTORY_MODE,'uid':0,'gid':0,'expect':'ABSENT'},
            'file':{'path':RELEASE_PATH,'sha256':plan['release']['sha256'],'bytes':plan['release']['bytes'],
                    'mode_octal':'%04o'%PRIVATE_FILE_MODE,'uid':0,'gid':0,'links':1},
            'release':release_facts(release_of(plan)),
            'release_file_in_the_worker':CONTAINER_RELEASE_PATH,
            'maintenance_pin':{'path':MAINTENANCE_PIN,'required':'PRESENT_REGULAR_ROOT_OWNED'},
            'new_york_day_utc':list(NEW_YORK_DAY_UTC),
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'pre_existing_objects_modified':False,'activation':False,'container_recreated':False,'process_started':False}
def success_of(plan):return COMPLETE_OUTCOME


def entry_named(host,name,parent,gate):
    """One lstat of a plain name in the held, pinned parent; no link is followed. None when the name does not exist."""
    gate()
    try:info=host.lstat(name,parent.fd)
    except FileNotFoundError:return None
    return {'type':kind(info.st_mode),'uid':info.st_uid,'gid':info.st_gid,'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),'links':info.st_nlink}

def _reduce_precheck(receipt):receipt['precheck']={'reduced_for_size':True}
def _reduce_parent(receipt):receipt['parent']=len(receipt.get('parent') or [])
REDUCTIONS=[('PRECHECK_DROPPED',_reduce_precheck),('PARENT_REDUCED_TO_COUNT',_reduce_parent)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    content=release_of(plan)                                  # pure: the bytes that will be written, and no others
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    detail={'parent':[],'precheck':{}};directories=[];ledger=[];handles={};pinned=[]
    go16=bound['go_sha256'][:16]
    def finish(status,outcome,code,extra):
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),
            clock=timing(begun,mark,clock,monotonic),mutating_calls=state.counts(),parent=detail['parent'],precheck=detail['precheck'],
            directories=directories,ledger=ledger,objects_left_by_this_run=objects_left(directories,ledger),
            pre_existing_objects_modified=False,**extra)))
    try:
        # ---- everything is looked at before the first creation
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o077)
            need(instant(NEW_YORK_DAY_UTC[0])<=clock()<instant(NEW_YORK_DAY_UTC[1]),'NOT_THE_FIRST_SESSION_DAY_IN_NEW_YORK')
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            parent=Pinned(host,walk_pinned(host,plan['parent'],gate,detail['parent']),rows=plan['parent']);pinned.append(parent)
            # The pin holds the automatic security routine (merge, reboot) for the epoch. It is also the witness that
            # what root creates in this directory is root:root: an entry root made there earlier.
            pin=entry_named(host,MAINTENANCE_PIN_NAME,parent,gate);detail['precheck']['maintenance_pin']=pin
            need(pin is not None,'MAINTENANCE_PIN_ABSENT')
            need(pin['type']=='file','MAINTENANCE_PIN_NOT_A_REGULAR_FILE')
            need((pin['uid'],pin['gid'])==(0,0),'MAINTENANCE_PIN_NOT_ROOT_OWNED')
            found=entry_named(host,RELEASE_DIRECTORY_NAME,parent,gate);detail['precheck']['destination']={'exists':found is not None,'found':found}
            need(found is None,'DESTINATION_PRESENT')
            free=free_bytes(host,parent.fd);detail['precheck']['free_bytes']=free
            need(free>=FREE_BYTES_FLOOR,'DATA_VOLUME_FREE_SPACE_BELOW_FLOOR')
            # The last refusal that costs nothing on the host: the time the creations and the readback may take.
            left=gate();detail['precheck']['seconds_left_before_first_effect']=int(left)
            need(left>=WRITE_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK','installed':None})
        # ---- from here on nothing refuses unless nothing has changed
        stop=None
        entry=create_directory('RELEASE_DIRECTORY',RELEASE_DIRECTORY,PRIVATE_DIRECTORY_MODE,parent,host,gate,state,handles);directories.append(entry)
        if entry['state']!='CREATED_DURABLE':stop=entry['code'] or 'CREATION_FAILED'
        if stop is None:
            row=create_file(0,'RELEASE',RELEASE_PATH,content,PRIVATE_FILE_MODE,handles['RELEASE_DIRECTORY'],host,gate,state,go16);ledger.append(row)
            if row['state']!='INSTALLED_DURABLE':stop=row['code'] or 'INSTALL_FAILED'
        else:ledger.append({'key':'RELEASE','path':RELEASE_PATH,'state':'NOT_ATTEMPTED','code':None})
        # ---- the readback inside the run: the bytes through a descriptor, the directory from "/", the parent again
        if stop is None:stop=readback_file(row,content,PRIVATE_FILE_MODE,handles['RELEASE_DIRECTORY'],host,gate)
        if stop is None:stop=readback_directory(RELEASE_DIRECTORY,PRIVATE_DIRECTORY_MODE,handles['RELEASE_DIRECTORY'],host,gate,1)
        if stop is None:
            try:parent.verify(gate)
            except Exception as error:stop=code_of(error,'READBACK_UNAVAILABLE')
        installed=None
        if stop is None:
            installed={'path':RELEASE_PATH,'release_file_in_the_worker':CONTAINER_RELEASE_PATH,'sha256':row['sha256_observed'],'bytes':row['bytes'],
                       'mode_octal':row['mode_octal'],'uid':row['uid'],'gid':row['gid'],'links':row['links'],
                       'directory_mode_octal':entry['observed']['mode_octal'],'directory_entries':1,
                       'bytes_equal_the_signed_bytes':True,'epoch':RELEASE_EPOCH,'verified_with_the_application':False}
        extra={'phase_reached':'EFFECTS','readback':'COMPLETE' if stop is None else None,'installed':installed}
        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        # REFUSED only while no mutating call succeeded and none is uncertain; otherwise the run is a partial.
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)
    finally:
        for handle in list(handles.values())+pinned:
            try:handle.close()
            except Exception:pass
