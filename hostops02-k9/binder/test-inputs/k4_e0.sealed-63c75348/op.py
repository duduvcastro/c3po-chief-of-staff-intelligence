import base64

OPERATION='GO_WRITE_HOSTOPS02_K4_E0_01'
PHASE='WRITE_K4_E0_EPOCH_ROOTS_AND_K9_RUNNER'
REQUEST_SCHEMA='WRITE_HOSTOPS02_K4_E0_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_K4_E0_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_K4_E0_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_K4_E0_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_K4_E0_PLAN_V1'
SOURCE_NAME='k4_e0.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False
# E0 runs once, on an evening before the first daily phases (A2 rev3 row E0: Monday 05/10 to Thursday 08/10). The
# narrowest class of the core that holds those days is WRITE_SESSIONS (10-05 ... 10-10 UTC); the Monday-Thursday band
# is the binder's and the signer's. A second run is refused by the source itself: both roots must be absent.
DATE_CLASS='WRITE_SESSIONS'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,)
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='EPOCH_ROOTS_CREATED_RUNNER_DELIVERED_READ_BACK'
PARTIAL_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
PLAN_KEYS=frozenset(('parent','runner','evidence_boot_id_sha256'))
RUNNER_KEYS=frozenset(('path','content_b64','sha256','bytes'))

# ---- PLACEMENT. Codex N-8 (W/codex-n8-placement-20261004.txt, sha256 d30f7f90...2c53) put the K9 tree under
# ---- /var/lib/c3po on a chain controlled by root alone; Codex decision 6 (#429 5985748037) put the source root there
# ---- too, beside the K9 root: no open root anywhere, no ancestor of uid 1000, nothing writable by group or other, no
# ---- setgid, no link, gid 0 on every component. Nothing of this source is on the data volume. Every path below
# ---- derives from these lines.
E0_EPOCH='R2D2-V2-SHADOW-2026-10-05'
VAR_LIB='/var/lib'
C3PO_NAME='c3po'
SOURCE_ROOT_NAME='r2d2-v2-source-20261005'
K9_ROOT_NAME='r2d2-v2-k9-20261005'
# ---- end of the placement

C3PO_DIRECTORY=VAR_LIB+'/'+C3PO_NAME
SOURCE_ROOT=C3PO_DIRECTORY+'/'+SOURCE_ROOT_NAME
K9_ROOT=C3PO_DIRECTORY+'/'+K9_ROOT_NAME
TOOLS_DIRECTORY=K9_ROOT+'/tools'
# The directories this run always creates, in creation order: (key, path, the key of the directory that holds it,
# the number of entries it holds when the run is complete). 'VAR_LIB_C3PO' is /var/lib/c3po, either created by this
# run first (only if absent) or found and held unchanged. The K9 note (section 3.1, Mounts): tools is bound read-only
# at /c3po-k9-tools, days/<D> is created by the first launch of each eve, claims/<attempt key>.claim by K9W, secrets/
# receives the env files and emitter/ from K3-K9; the source root receives the producers' non-secret outputs.
E0_DIRECTORIES=(('SOURCE_ROOT',SOURCE_ROOT,'VAR_LIB_C3PO',0),
                ('K9_ROOT',K9_ROOT,'VAR_LIB_C3PO',4),
                ('K9_TOOLS',TOOLS_DIRECTORY,'K9_ROOT',1),
                ('K9_DAYS',K9_ROOT+'/days','K9_ROOT',0),
                ('K9_CLAIMS',K9_ROOT+'/claims','K9_ROOT',0),
                ('K9_SECRETS',K9_ROOT+'/secrets','K9_ROOT',0))
C3PO_ENTRIES_IF_CREATED=2
RUNNER_STEM='k9_runner-'
RUNNER_EXTENSION='.py'
CONTAINER_TOOLS_DIRECTORY='/c3po-k9-tools'
MAX_RUNNER_BYTES=40960                    # base64 of it plus the rest of the request stays below the 65536 bytes of a signed document
# Space: one floor (Codex, 2026-10-04): 200 GiB available to a non-root writer (f_bavail * f_frsize of a held
# descriptor, before the first creation) on the filesystem that will hold both roots and days/: /var/lib/c3po when it
# exists (it must then be on the filesystem of /var/lib), otherwise /var/lib, where it will be created.
FREE_BYTES_FLOOR=214748364800
SPACE_MEASURED_ON='/var/lib/c3po if present (same filesystem as /var/lib required), else /var/lib'
WRITE_ALLOWANCE_SECONDS=15                # what must be left of the budget before the first creation (the writes take milliseconds)
C3PO_IF_ABSENT={'action':'CREATE','mode_octal':'%04o'%PRIVATE_DIRECTORY_MODE,'uid':0,'gid':0,'entries_after':C3PO_ENTRIES_IF_CREATED}
C3PO_IF_PRESENT={'action':'USE_UNCHANGED','require':'DIRECTORY_NOT_A_LINK_UID_0_GID_0_NOT_GROUP_OR_OTHER_WRITABLE_NOT_SETGID_SAME_DEVICE_AS_VAR_LIB',
                 'identity':'RECORDED_IN_THE_RECEIPT_AND_HELD_UNCHANGED_TO_THE_END'}

def runner_name(digest):return RUNNER_STEM+digest+RUNNER_EXTENSION

SCOPE_STATEMENT=('Creates, once, under '+VAR_LIB+', whose chain from "/" is controlled by root alone: the directory '+C3PO_DIRECTORY
                 +' only if it is absent (if present it must be a root:root directory on the filesystem of '+VAR_LIB+', not a link, not '
                 'writable by group or other, not setgid, and is used unchanged); in it the source root '+SOURCE_ROOT+' and the K9 root '
                 +K9_ROOT+' with its four directories tools, days, claims and secrets (every directory created root:root 0700); and in '
                 'tools the file '+runner_name('<sha256>')+' (root:root 0600) holding exactly the runner bytes whose SHA-256 and size the '
                 'request signs, for epoch '+E0_EPOCH+'. Nothing is created unless that filesystem has '+str(FREE_BYTES_FLOOR)+' bytes '
                 'available. Exclusive creation, fsync and a readback of the bytes and of every directory through descriptors inside the '
                 'run. Nothing that exists is overwritten, renamed, chmodded, chowned or removed, except the temporary of this run once its '
                 'identity is proved. No process is started, no secret is read or written, no container is touched and nothing is activated.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,'epoch':E0_EPOCH,
       'placement':{'var_lib':VAR_LIB,'c3po_directory':C3PO_DIRECTORY,'source_root':SOURCE_ROOT,'k9_root':K9_ROOT,'open_root':None},
       'c3po_directory':{'path':C3PO_DIRECTORY,'if_absent':C3PO_IF_ABSENT,'if_present':C3PO_IF_PRESENT},
       'directories':[{'key':key,'path':path,'mode_octal':'%04o'%PRIVATE_DIRECTORY_MODE,'entries_after':entries} for key,path,_,entries in E0_DIRECTORIES],
       'runner':{'directory':TOOLS_DIRECTORY,'name':runner_name('<sha256>'),'mode_octal':'%04o'%PRIVATE_FILE_MODE,'max_bytes':MAX_RUNNER_BYTES,
                 'directory_in_k9_containers':CONTAINER_TOOLS_DIRECTORY},
       'space':{'free_bytes_floor':FREE_BYTES_FLOOR,'measured_on':SPACE_MEASURED_ON},
       'files':FILES_SCOPE,'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'file_contents_read':[BOOT_ID_PATH,'the runner file this run delivered (readback inside the run)'],
       'processes_started':0,
       'never':['overwrite','chmod','chown','rename','truncate','removal of anything but the temporary this run created','a process','docker','systemctl',
                'a shell','a network connection','a secret','activation','a container','a second attempt'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'runner_bytes':MAX_RUNNER_BYTES,'free_bytes_floor':FREE_BYTES_FLOOR,'write_allowance_seconds':WRITE_ALLOWANCE_SECONDS}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeFiles):
    """Everything this source can do to the host: the read primitives and the seven creating calls. No process."""


def runner_of(plan):
    """The runner bytes the request carries, decoded and compared with the signed hash and size; the path must be the
    content-addressed name of that hash in the tools directory. Pure."""
    item=plan['runner']
    need(type(item) is dict and set(item)==set(RUNNER_KEYS),'RUNNER_PLAN_INVALID')
    need(file_request(RUNNER_STEM+'x'+RUNNER_EXTENSION,item['sha256'],item['bytes'],PRIVATE_FILE_MODE) and item['bytes']<=MAX_RUNNER_BYTES,'RUNNER_PLAN_INVALID')
    need(item['path']==TOOLS_DIRECTORY+'/'+runner_name(item['sha256']),'RUNNER_PATH_NOT_CONTENT_ADDRESSED')
    need(type(item['content_b64']) is str,'RUNNER_BYTES_NOT_THE_SIGNED_HASH')
    try:raw=base64.b64decode(item['content_b64'].encode('ascii'),validate=True)
    except (ValueError,UnicodeEncodeError):raise Refused('RUNNER_BYTES_NOT_THE_SIGNED_HASH') from None
    need(len(raw)==item['bytes'] and sha(raw)==item['sha256'],'RUNNER_BYTES_NOT_THE_SIGNED_HASH')
    return raw

def root_controlled(row):
    """What the chain needs beyond validate_chain without an open root (which already requires uid 0 and no write bit
    for group or other on every component): group 0, and no setgid bit on any component."""
    return row['gid']==0 and not row['mode']&stat.S_ISGID

def validate_plan(plan):
    validate_chain(plan['parent'],VAR_LIB,open_root=None,receives_entry=True)
    need(all(root_controlled(row) for row in plan['parent']),'CHAIN_NOT_ROOT_CONTROLLED')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    runner_of(plan)

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    digest=plan['runner']['sha256']
    return {'operation':OPERATION,'epoch':E0_EPOCH,
            'parent':chain_effects(plan['parent']),'open_root':None,
            'c3po_directory':{'path':C3PO_DIRECTORY,'if_absent':C3PO_IF_ABSENT,'if_present':C3PO_IF_PRESENT},
            'directories':{key:{'path':path,'mode_octal':'%04o'%PRIVATE_DIRECTORY_MODE,'uid':0,'gid':0,'expect':'ABSENT','entries_after':entries}
                           for key,path,_,entries in E0_DIRECTORIES},
            'runner':{'path':TOOLS_DIRECTORY+'/'+runner_name(digest),'sha256':digest,'bytes':plan['runner']['bytes'],
                      'mode_octal':'%04o'%PRIVATE_FILE_MODE,'uid':0,'gid':0,'links':1,
                      'path_in_k9_containers':CONTAINER_TOOLS_DIRECTORY+'/'+runner_name(digest)},
            'space':{'free_bytes_floor':FREE_BYTES_FLOOR,'measured_on':SPACE_MEASURED_ON},
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'pre_existing_objects_modified':False,'secret_written':False,'activation':False,'container_touched':False,'process_started':False}
def success_of(plan):return COMPLETE_OUTCOME


def entry_named(host,name,parent,gate):
    """One lstat of a plain name in the held, pinned parent; no link is followed. None when the name does not exist."""
    gate()
    try:info=host.lstat(name,parent.fd)
    except FileNotFoundError:return None
    return {'type':kind(info.st_mode),'uid':info.st_uid,'gid':info.st_gid,'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),'links':info.st_nlink,
            'device':info.st_dev,'inode':info.st_ino}

def hold_existing(host,name,parent,found,gate):
    """The existing /var/lib/c3po, opened by the held descriptor of /var/lib without following a link, and held: the
    descriptor must be the object the lstat saw. Returns the Pinned child."""
    gate()
    try:fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=parent.fd)
    except OSError:raise Refused('C3PO_DIRECTORY_CHANGED_DURING_PRECHECK') from None
    try:held=Pinned(host,fd,parent=parent,name=name)
    except BaseException:
        host.close(fd);raise
    if held.identity[:2]!=(found['device'],found['inode']) or held.identity[2:]!=(found['uid'],found['gid'],int(found['mode_octal'],8)):
        held.close();raise Refused('C3PO_DIRECTORY_CHANGED_DURING_PRECHECK')
    return held

def _reduce_precheck(receipt):receipt['precheck']={'reduced_for_size':True}
def _reduce_parent(receipt):receipt['parent']=len(receipt.get('parent') or [])
REDUCTIONS=[('PRECHECK_DROPPED',_reduce_precheck),('PARENT_REDUCED_TO_COUNT',_reduce_parent)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    content=runner_of(plan)                                   # pure: the bytes that will be written, and no others
    runner_path=TOOLS_DIRECTORY+'/'+runner_name(plan['runner']['sha256'])
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    detail={'parent':[],'precheck':{}};directories=[];ledger=[];handles={};pinned=[];c3po={'state':None,'found':None,'created':False}
    go16=bound['go_sha256'][:16]
    def finish(status,outcome,code,extra):
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),
            clock=timing(begun,mark,clock,monotonic),mutating_calls=state.counts(),parent=detail['parent'],precheck=detail['precheck'],
            c3po_directory=c3po,directories=directories,ledger=ledger,objects_left_by_this_run=objects_left(directories,ledger),
            pre_existing_objects_modified=False,**extra)))
    try:
        # ---- everything is looked at before the first creation
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o077)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            var_lib=Pinned(host,walk_pinned(host,plan['parent'],gate,detail['parent']),rows=plan['parent']);pinned.append(var_lib)
            # /var/lib/c3po: never presumed. Absent: it is created first (the signed if_absent), and neither root can exist.
            # Present: a root directory on the filesystem of /var/lib, closed to group and other, held unchanged to the end
            # (the signed if_present), and neither root name may exist in it.
            found=entry_named(host,C3PO_NAME,var_lib,gate);c3po['found']=found;c3po['state']='ABSENT' if found is None else 'PRESENT'
            if found is not None:
                need(found['type']=='dir','C3PO_DIRECTORY_NOT_A_DIRECTORY')
                need((found['uid'],found['gid'])==(0,0),'C3PO_DIRECTORY_NOT_ROOT_OWNED')
                need(not int(found['mode_octal'],8)&0o022,'C3PO_DIRECTORY_WRITABLE_BY_GROUP_OR_OTHER')
                need(not int(found['mode_octal'],8)&stat.S_ISGID,'C3PO_DIRECTORY_SETGID')
                need(found['device']==var_lib.identity[0],'C3PO_DIRECTORY_ON_ANOTHER_FILESYSTEM')
                handles['VAR_LIB_C3PO']=hold_existing(host,C3PO_NAME,var_lib,found,gate)
                found=entry_named(host,SOURCE_ROOT_NAME,handles['VAR_LIB_C3PO'],gate);detail['precheck']['source_root']={'exists':found is not None,'found':found}
                need(found is None,'SOURCE_ROOT_PRESENT')
                found=entry_named(host,K9_ROOT_NAME,handles['VAR_LIB_C3PO'],gate);detail['precheck']['k9_root']={'exists':found is not None,'found':found}
                need(found is None,'K9_ROOT_PRESENT')
            space=handles.get('VAR_LIB_C3PO',var_lib)
            free=free_bytes(host,space.fd);detail['precheck']['free_bytes']=free
            detail['precheck']['free_bytes_measured_on']=C3PO_DIRECTORY if 'VAR_LIB_C3PO' in handles else VAR_LIB
            need(free>=FREE_BYTES_FLOOR,'FREE_SPACE_BELOW_FLOOR')
            # The last refusal that costs nothing on the host: the time the creations and the readback may take.
            left=gate();detail['precheck']['seconds_left_before_first_effect']=int(left)
            need(left>=WRITE_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK','delivered':None})
        # ---- from here on nothing refuses unless nothing has changed
        stop=None;table=list(E0_DIRECTORIES)
        if 'VAR_LIB_C3PO' not in handles:
            table.insert(0,('VAR_LIB_C3PO',C3PO_DIRECTORY,'VAR_LIB',C3PO_ENTRIES_IF_CREATED));handles['VAR_LIB']=var_lib
        for key,path,holder,_ in table:
            if stop is not None:
                directories.append({'key':key,'path':path,'state':'NOT_ATTEMPTED','code':None});continue
            entry=create_directory(key,path,PRIVATE_DIRECTORY_MODE,handles[holder],host,gate,state,handles)
            directories.append(entry)
            if entry['state']!='CREATED_DURABLE':stop=entry['code'] or 'CREATION_FAILED'
            elif key=='VAR_LIB_C3PO':c3po['created']=True
        if stop is None:
            row=create_file(0,'K9_RUNNER',runner_path,content,PRIVATE_FILE_MODE,handles['K9_TOOLS'],host,gate,state,go16);ledger.append(row)
            if row['state']!='INSTALLED_DURABLE':stop=row['code'] or 'INSTALL_FAILED'
        else:ledger.append({'key':'K9_RUNNER','path':runner_path,'state':'NOT_ATTEMPTED','code':None})
        # ---- the readback inside the run: the bytes through a descriptor, every created directory from "/", the
        # ---- directory found (if any) unchanged, the chain walked again
        if stop is None:stop=readback_file(row,content,PRIVATE_FILE_MODE,handles['K9_TOOLS'],host,gate)
        for key,path,_,entries in table:
            if stop is None:stop=readback_directory(path,PRIVATE_DIRECTORY_MODE,handles[key],host,gate,entries)
        if stop is None and not c3po['created']:
            try:handles['VAR_LIB_C3PO'].verify(gate)
            except Exception as error:stop=code_of(error,'READBACK_UNAVAILABLE')
        for held in pinned:
            if stop is None:
                try:held.verify(gate)
                except Exception as error:stop=code_of(error,'READBACK_UNAVAILABLE')
        delivered=None
        if stop is None:
            held=handles['VAR_LIB_C3PO'].identity
            delivered={'source_root':SOURCE_ROOT,'k9_root':K9_ROOT,
                       'c3po_directory':{'path':C3PO_DIRECTORY,'created_by_this_run':c3po['created'],'device':held[0],'inode':held[1],'uid':held[2],
                                         'gid':held[3],'mode_octal':'%04o'%held[4]},
                       'directories':{entry['key']:{'path':entry['path'],'mode_octal':entry['observed']['mode_octal'],'uid':entry['observed']['uid'],
                                                    'gid':entry['observed']['gid'],'entries':entries}
                                      for entry,(_,_,_,entries) in zip(directories,table)},
                       'runner':{'path':runner_path,'path_in_k9_containers':CONTAINER_TOOLS_DIRECTORY+'/'+runner_name(row['sha256_observed']),
                                 'sha256':row['sha256_observed'],'bytes':row['bytes'],'mode_octal':row['mode_octal'],'uid':row['uid'],'gid':row['gid'],
                                 'links':row['links'],'bytes_equal_the_signed_bytes':True},
                       'epoch':E0_EPOCH}
        extra={'phase_reached':'EFFECTS','readback':'COMPLETE' if stop is None else None,'delivered':delivered}
        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        # REFUSED only while no mutating call succeeded and none is uncertain; otherwise the run is a partial.
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)
    finally:
        for key,handle in list(handles.items()):
            if key!='VAR_LIB':
                try:handle.close()
                except Exception:pass
        for handle in pinned:
            try:handle.close()
            except Exception:pass
