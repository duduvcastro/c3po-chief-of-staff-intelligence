import base64

OPERATION='GO_WRITE_HOSTOPS02_CORE_SELFTEST_01'
PHASE='WRITE_CORE_SELFTEST_NEVER_DISPATCHED'
REQUEST_SCHEMA='WRITE_HOSTOPS02_SELFTEST_WRITE_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_SELFTEST_WRITE_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_SELFTEST_WRITE_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_SELFTEST_WRITE_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_SELFTEST_WRITE_PLAN_V1'
SOURCE_NAME='selftest_write.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False
DATE_CLASS='WRITE_EPOCH'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
EVIDENCE_OPERATIONS=('GO_READONLY_HOSTOPS02_CORE_SELFTEST_01',PRECHECK_OPERATION)
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='SELFTEST_ALL_EFFECTS_VERIFIED'
PARTIAL_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
PLAN_KEYS=frozenset(('parent','open_root','directory_name','files','container','recreate','evidence_boot_id_sha256'))
FILE_KEYS=frozenset(('key','name','content_b64','sha256','bytes','mode'))
CONTAINER_PLAN_KEYS=frozenset(('image_id','script_b64','script_sha256','target','arguments','creates'))
RECREATE_KEYS=frozenset(('project','env_file','files','override_key','service','container','build_sha','environment','lock_directory','lock_open_root',
                         'lock_name','lock_wait_seconds'))
MAX_FILES=4
FILES_ALLOWANCE_SECONDS=2                 # the directory, the files and the reads between two effects
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
SERVICE='r2d2-worker'
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'one image ID or reference','QUICK','READ'),
          'container':command_row('docker',['container','inspect','--format',CONTAINER_FORMAT],'one container name or ID','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          'container_environment':command_row('docker',['container','inspect','--format'],'the presence and equality template, then one container ID','QUICK','READ'),
          'script':command_row('docker',RUN_PREFIX,'one read-write bind of the directory this run created, the signed image ID, python -I -B - and the signed arguments','RUN_SHORT','EFFECT',stdin=True),
          'render':command_row('docker',['compose'],'--project-name, --env-file and the signed -f list, the override on standard input as the last file','RENDER','READ',tail=COMPOSE_CONFIG_TAIL,stdin=True),
          'render_files':command_row('docker',['compose'],'--project-name, --env-file and the signed -f list with the delivered override file','RENDER','READ',tail=COMPOSE_CONFIG_TAIL),
          'recreate':command_row('docker',['compose'],'--project-name, --env-file and the signed -f list with the delivered override file','RECREATE','EFFECT',tail=compose_up_tail(SERVICE))}
SCOPE_STATEMENT=('Demonstration only; never bound. Creates one private directory in the signed parent and the signed files in it, runs one '
                 'attached container that writes through a bind of that directory, and recreates one compose service under the deployment '
                 'lock with an explicit file list. Nothing that exists is overwritten, renamed, chmodded, chowned or removed, except the '
                 'temporary of this run once its identity is proved.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'after_effect_reserve_seconds':AFTER_EFFECT_RESERVE_SECONDS,'files_allowance_seconds':FILES_ALLOWANCE_SECONDS,
       'files':FILES_SCOPE,'lock':LOCK_SCOPE,'service':SERVICE,'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'file_contents_read':[BOOT_ID_PATH,'the files this run delivered (readback inside the run)'],
       'never':['overwrite','chmod','chown','rename','removal of anything but the temporary this run created','docker exec','a shell',
                'systemctl','a pull','a network connection opened by this process'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,'files':MAX_FILES}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner,NativeFiles,NativeLock):
    """Everything this source can do to the host: the read primitives, the signed commands, the seven creating calls, the lock."""


def directory_path(plan):return plan['parent'][-1]['path'].rstrip('/')+'/'+plan['directory_name']

def decoded(value,digest,size,code):
    need(type(value) is str and len(value)<=4*MAX_FILE_BYTES,code)
    try:raw=base64.b64decode(value.encode('ascii'),validate=True)
    except (ValueError,UnicodeEncodeError):raise Refused(code) from None
    need(sha(raw)==digest and (size is None or len(raw)==size),code);return raw

def validate_plan(plan):
    need(type(plan['parent']) is list and plan['parent'] and type(plan['parent'][-1]) is dict and type(plan['parent'][-1].get('path')) is str,'CHAIN_ROW_INVALID')
    validate_chain(plan['parent'],plan['parent'][-1]['path'],plan['open_root'],receives_entry=True)
    need(text(plan['directory_name'],FILE_NAME) and clean_path(directory_path(plan)),'PATH_INVALID')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    files=plan['files'];need(type(files) is list and 0<len(files)<=MAX_FILES,'FILES_INVALID')
    for item in files:
        need(type(item) is dict and set(item)==set(FILE_KEYS) and text(item['key'],'[A-Z][A-Z0-9_]{0,31}')
             and file_request(item['name'],item['sha256'],item['bytes'],item['mode']),'FILES_INVALID')
        decoded(item['content_b64'],item['sha256'],item['bytes'],'FILE_BYTES_NOT_THE_SIGNED_HASH')
    need(len({item['key'] for item in files})==len(files)==len({item['name'] for item in files}),'FILES_INVALID')
    container=plan['container']
    if container is not None:
        need(type(container) is dict and set(container)==set(CONTAINER_PLAN_KEYS) and text(container['image_id'],IMAGE_ID) and hexpin(container['script_sha256'])
             and text(container['creates'],FILE_NAME) and container['creates'] not in [item['name'] for item in files],'CONTAINER_PLAN_INVALID')
        decoded(container['script_b64'],container['script_sha256'],None,'SCRIPT_NOT_THE_SIGNED_HASH')
        run_arguments('script',container['image_id'],[{'source':directory_path(plan),'target':container['target'],'read_only':False}],
                      ['python','-I','-B','-']+(container['arguments'] if type(container['arguments']) is list else [None]))
    recreate=plan['recreate']
    if recreate is not None:
        need(type(recreate) is dict and set(recreate)==set(RECREATE_KEYS) and recreate['service']==SERVICE and text(recreate['container'],CONTAINER_NAME)
             and text(recreate['build_sha'],'[0-9a-f]{40}') and text(recreate['lock_name'],FILE_NAME)
             and integer(recreate['lock_wait_seconds'],0,MAX_LOCK_WAIT_SECONDS),'RECREATE_PLAN_INVALID')
        need(recreate['override_key'] in [item['key'] for item in files],'RECREATE_PLAN_INVALID')
        compose_arguments(recreate['project'],recreate['env_file'],recreate['files'])                 # the signed list alone, then with the override
        compose_arguments(recreate['project'],recreate['env_file'],recreate['files']+[override_path(plan)])
        environment_format(recreate['environment'])
        need(type(recreate['lock_directory']) is list and recreate['lock_directory'] and type(recreate['lock_directory'][-1]) is dict,'CHAIN_ROW_INVALID')
        validate_chain(recreate['lock_directory'],recreate['lock_directory'][-1].get('path'),recreate['lock_open_root'])

def override_path(plan):
    item=[item for item in plan['files'] if item['key']==plan['recreate']['override_key']][0]
    return directory_path(plan)+'/'+item['name']

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    container,recreate=plan['container'],plan['recreate']
    return {'operation':OPERATION,'parent':chain_effects(plan['parent']),'open_root':plan['open_root'],
            'directory':{'path':directory_path(plan),'mode_octal':'%04o'%PRIVATE_DIRECTORY_MODE,'expect':'ABSENT'},
            'files':[{'key':item['key'],'path':directory_path(plan)+'/'+item['name'],'sha256':item['sha256'],'bytes':item['bytes'],
                      'mode_octal':'%04o'%item['mode']} for item in plan['files']],
            'container':None if container is None else {'image_id':container['image_id'],'script_sha256':container['script_sha256'],
                'bind':{'source':directory_path(plan),'target':container['target'],'read_only':False},'arguments':container['arguments'],
                'creates':directory_path(plan)+'/'+container['creates'],'network':'none'},
            'recreate':None if recreate is None else {'project':recreate['project'],'env_file':recreate['env_file'],
                'files':recreate['files']+[override_path(plan)],'service':recreate['service'],'container':recreate['container'],
                'build_sha':recreate['build_sha'],'environment':recreate['environment'],
                'lock':recreate['lock_directory'][-1]['path']+'/'+recreate['lock_name'],'lock_wait_seconds':recreate['lock_wait_seconds'],
                'lock_chain_sha256':sha(canonical(recreate['lock_directory'])),'lock_open_root':recreate['lock_open_root']},
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],'pre_existing_objects_modified':False,'activation':False}
def success_of(plan):return COMPLETE_OUTCOME


def environment_of(rendered,recreate):
    """The rendered service must carry the signed build revision and exactly the signed values of the signed names."""
    service=compose_service(rendered,recreate['service'])
    need(service['environment'].get('C3PO_BUILD_SHA')==recreate['build_sha'],'RENDER_BUILD_REVISION')
    need(all(service['environment'].get(key)==value for key,value in recreate['environment'].items()),'RENDER_ENVIRONMENT_MISMATCH')
    return service

def others(rows,name):
    """Every container but the one named, as (id, state): what must be the same before and after the recreate."""
    return sorted((row['id'],row['state']) for row in rows if row['name']!=name)

def _reduce_precheck(receipt):receipt['precheck']={'reduced_for_size':True}
def _reduce_parent(receipt):receipt['parent']=len(receipt.get('parent') or [])
REDUCTIONS=[('PRECHECK_DROPPED',_reduce_precheck),('PARENT_REDUCED_TO_COUNT',_reduce_parent)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    files=[decoded(item['content_b64'],item['sha256'],item['bytes'],'FILE_BYTES_NOT_THE_SIGNED_HASH') for item in plan['files']]     # pure
    container,recreate=plan['container'],plan['recreate']
    script=None if container is None else decoded(container['script_b64'],container['script_sha256'],None,'SCRIPT_NOT_THE_SIGNED_HASH')
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    detail={'parent':[],'precheck':{}};directories=[];ledger=[];handles={};pinned=[];lock=[None]
    commands=Commands(host,gate);go16=bound['go_sha256'][:16];run={'container':None,'recreate':None}
    def finish(status,outcome,code,extra):
        receipt=envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),clock=timing(begun,mark,clock,monotonic),
            commands_started=dict(commands.started),mutating_calls=state.counts(),parent=detail['parent'],precheck=detail['precheck'],
            directories=directories,ledger=ledger,container=run['container'],recreate=run['recreate'],
            objects_left_by_this_run=objects_left(directories,ledger)+(1 if (run['container'] or {}).get('created') else 0),
            pre_existing_objects_modified=bool((run['recreate'] or {}).get('recreated')),**extra))
        return seal(receipt)
    try:
        # ---- everything is looked at before the first creation
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o077)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            parent=Pinned(host,walk_pinned(host,plan['parent'],gate,detail['parent']),rows=plan['parent']);pinned.append(parent)
            found=probe(host,directory_path(plan),gate);detail['precheck']['directory']={'exists':found.get('exists')}
            need(found.get('status')=='COMPLETE' and found['exists'] is False,'DESTINATION_PRESENT')
            if container is not None:
                try:image=image_facts(commands,container['image_id'])
                except CommandFailed:raise Refused('IMAGE_ABSENT_OR_UNREADABLE') from None
                need(image['id']==container['image_id'],'IMAGE_ID_MISMATCH')
            if recreate is not None:
                holder=Pinned(host,walk_pinned(host,recreate['lock_directory'],gate,[]),rows=recreate['lock_directory']);pinned.append(holder)
                lock[0]=open_lock(host,recreate['lock_name'],holder,gate)
                before=container_facts(commands,recreate['container']);listing=container_list(commands)
                need(before['running'] is True and before['state']=='running','CONTAINER_NOT_RUNNING')
                detail['precheck']['container']={'id':before['id'],'started_at':before['started_at'],'restarts':before['restarts']}
                override=files[[item['key'] for item in plan['files']].index(recreate['override_key'])]
                rendered=compose_render(commands,'render',recreate['project'],recreate['env_file'],recreate['files'],recreate['build_sha'],override=override)
                service=environment_of(rendered,recreate)
                need(image_facts(commands,service['image'])['id']==before['image_id'],'RENDER_IMAGE_CHANGED')
                detail['precheck']['render']={'environment_as_signed':True,'image_is_the_running_one':True}
            # The last refusals before the first effect: the lock (waited for at most the signed seconds, and never
            # past the point where the effects would no longer fit), then the time every effect still to run needs.
            needed=effects_budget(*([] if container is None else ['script'])+([] if recreate is None else ['recreate']))+FILES_ALLOWANCE_SECONDS
            if recreate is not None:
                detail['precheck']['lock_attempts']=acquire_lock(host,lock[0],gate,recreate['lock_wait_seconds'],needed)
                need(lock_still_named(host,recreate['lock_name'],holder,lock[0]),'LOCK_FILE_REPLACED')
            need(gate()>=needed,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})
        # ---- from here on nothing refuses unless nothing has changed
        stop=None;path=directory_path(plan)
        entry=create_directory('DIRECTORY',path,PRIVATE_DIRECTORY_MODE,parent,host,gate,state,handles);directories.append(entry)
        if entry['state']!='CREATED_DURABLE':stop=entry['code'] or 'CREATION_FAILED'
        for index,(item,content) in enumerate(zip(plan['files'],files)):
            if stop is not None:
                ledger.append({'key':item['key'],'path':path+'/'+item['name'],'state':'NOT_ATTEMPTED','code':None});continue
            row=create_file(index,item['key'],path+'/'+item['name'],content,item['mode'],handles['DIRECTORY'],host,gate,state,go16);ledger.append(row)
            if row['state']!='INSTALLED_DURABLE':stop=row['code'] or 'INSTALL_FAILED'
        if stop is None:
            for item,content,row in zip(plan['files'],files,ledger):
                stop=stop or readback_file(row,content,item['mode'],handles['DIRECTORY'],host,gate)
        if stop is None and container is not None:
            facts={'state':'NOT_STARTED','code':None,'returncode':None,'created':False};run['container']=facts
            result=container_effect(state,commands,'script',container['image_id'],[{'source':path,'target':container['target'],'read_only':False}],
                                    ['python','-I','-B','-']+container['arguments'],script)
            facts.update(code=result['code'],returncode=result['returncode'])
            if not result['started']:stop=result['code']
            elif not result['returned']:facts['state']='UNCERTAIN';stop=result['code']
            else:
                # the command returned: what it left is read on the host, and only then is the call settled
                try:
                    seen=probe(host,path+'/'+container['creates'],gate);facts['created']=bool(seen.get('exists'))
                    line=single_line(result['output']) if result['returncode']==0 else None
                    good=(result['returncode']==0 and line=={'status':'DONE','created':container['creates']} and facts['created']
                          and (seen['type'],seen['uid'],seen['gid'],seen['mode_octal'],seen['links'])==('file',0,0,'0600',1))
                except Exception:good=False;seen=None
                if good:state.done();facts['state']='DONE_VERIFIED'
                elif seen is not None and seen.get('exists') is False:state.fail();facts['state']='NOTHING_CREATED';stop='SCRIPT_FAILED_NOTHING_CREATED'
                else:state.unknown();facts['state']='UNCERTAIN';stop='SCRIPT_RESULT_NOT_VERIFIED'
        if stop is None and recreate is not None:
            facts={'state':'NOT_STARTED','code':None,'returncode':None,'recreated':False};run['recreate']=facts
            try:
                # under the lock, with the override now a file: the render the recreate will use, and nothing else changed meanwhile
                need(lock_still_named(host,recreate['lock_name'],holder,lock[0]),'LOCK_FILE_REPLACED')
                listed=recreate['files']+[override_path(plan)]
                environment_of(compose_render(commands,'render_files',recreate['project'],recreate['env_file'],listed,recreate['build_sha']),recreate)
                need(others(container_list(commands),recreate['container'])==others(listing,recreate['container']),'CONTAINER_SET_CHANGED')
            except Exception as error:stop=code_of(error,'RECREATE_PRECHECK_FAILED')
            if stop is None:
                result=compose_up(state,commands,'recreate',recreate['project'],recreate['env_file'],listed,recreate['build_sha'])
                facts.update(code=result['code'],returncode=result['returncode'])
                if not result['started']:stop=result['code']
                else:
                    try:
                        after=container_facts(commands,recreate['container']);values=container_environment(commands,after['id'],recreate['environment'])
                        facts.update(recreated=after['id']!=before['id'],running=after['running'],restarts=after['restarts'],
                                     environment_as_signed=all(item['equal'] for item in values.values()),
                                     others_unchanged=others(container_list(commands),recreate['container'])==others(listing,recreate['container']))
                        good=(result['returned'] and result['returncode']==0 and facts['recreated'] and after['running'] and after['restarts']==0
                              and after['image_id']==before['image_id'] and facts['environment_as_signed'] and facts['others_unchanged'])
                        unchanged=(after['id'],after['started_at'])==(before['id'],before['started_at'])
                    except Exception:good=False;unchanged=False
                    if good:
                        if result['returned']:state.done()
                        facts['state']='RECREATED_VERIFIED'
                    elif result['returned'] and unchanged:state.fail();facts['state']='NOT_RECREATED';stop='RECREATE_FAILED_CONTAINER_UNCHANGED'
                    else:
                        if result['returned']:state.unknown()
                        facts['state']='UNCERTAIN';stop=result['code'] or 'RECREATE_NOT_VERIFIED'
                    if stop is None and not result['returned']:stop=result['code'] or 'RECREATE_NOT_VERIFIED'
        check=None
        if stop is None:
            check=readback_directory(path,PRIVATE_DIRECTORY_MODE,handles['DIRECTORY'],host,gate,len(plan['files'])+(1 if container is not None else 0))
            if check is None:
                try:parent.verify(gate)
                except Exception as error:check=code_of(error,'READBACK_UNAVAILABLE')
            stop=check
        extra={'phase_reached':'EFFECTS','readback':'COMPLETE' if stop is None else None}
        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        # REFUSED only while no mutating call succeeded and none is uncertain; otherwise the run is a partial.
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)
    finally:
        if lock[0] is not None:release_lock(host,lock[0])
        for handle in list(handles.values())+pinned:
            try:handle.close()
            except Exception:pass
