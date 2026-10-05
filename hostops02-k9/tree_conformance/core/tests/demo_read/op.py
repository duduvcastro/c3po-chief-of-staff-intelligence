import base64

OPERATION='GO_READONLY_HOSTOPS02_CORE_SELFTEST_01'
PHASE='READONLY_CORE_SELFTEST_NEVER_DISPATCHED'
REQUEST_SCHEMA='READONLY_HOSTOPS02_SELFTEST_READ_REQUEST_V1'
AUTHORITY_SCHEMA='READONLY_HOSTOPS02_SELFTEST_READ_AUTHORITY_V1'
GO_SCHEMA='READONLY_HOSTOPS02_SELFTEST_READ_GO_V1'
RECEIPT_SCHEMA='READONLY_HOSTOPS02_SELFTEST_READ_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_SELFTEST_READ_PLAN_V1'
SOURCE_NAME='selftest_read.py'
WRITES_ALLOWED=False
ACTIVATION_ALLOWED=False
DATE_CLASS='READ'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=False
EVIDENCE_OPERATIONS=()
MAX_GATE_SPAN_SECONDS=3600
COMPLETE_OUTCOME='SELFTEST_ALL_OBSERVED_ALL_EXPECTATIONS_MET'
MISMATCH_OUTCOME='OBSERVED_ALL_EXPECTATIONS_NOT_MET'
PARTIAL_OUTCOME='PARTIAL_OBSERVED'
REFUSED_OUTCOME='REFUSED_NOTHING_OBSERVED'
REDUCED_OUTCOME='PARTIAL_OBSERVED'
ESCAPED_OUTCOME='PARTIAL_OBSERVED'
PLAN_KEYS=frozenset(('directories','image','containers','environment','verify','render','file','lock','evidence_boot_id_sha256'))
MAX_DIRECTORIES=6
MAX_NAMES=16
MAX_READ_BYTES=65536
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'one image ID or reference','QUICK','READ'),
          'container':command_row('docker',['container','inspect','--format',CONTAINER_FORMAT],'one container name or ID','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          'container_environment':command_row('docker',['container','inspect','--format'],'the presence and equality template, then one container ID','QUICK','READ'),
          'verify':command_row('docker',RUN_PREFIX,'read-only binds of signed directories, the signed image ID, python -I -B -','RUN_SHORT','CONTAINER',stdin=True),
          'render':command_row('docker',['compose'],'--project-name, --env-file and the signed -f list, the override on standard input as the last file','RENDER','READ',tail=COMPOSE_CONFIG_TAIL,stdin=True)}
SCOPE_STATEMENT=('Demonstration only; never bound. Reads and changes nothing on the filesystem of the host: signed directories, image and '
                 'container metadata, the signed environment names of one container as booleans, one regular file compared with a signed hash, '
                 'a compose render, and whether the deployment lock is free. It creates and removes one container that has no network and '
                 'only read-only binds.')
SIDE_EFFECTS=['one attached docker run --rm: the engine creates a container and removes it when its process ends; a run that times out may leave it running until then',
              'a shared, non-blocking flock on the deployment lock, released at once',
              'docker compose config reads the environment file; its values stay in the memory of this process and never reach the receipt']
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'after_effect_reserve_seconds':AFTER_EFFECT_RESERVE_SECONDS,'lock':LOCK_SCOPE,
       'file_contents_read':[BOOT_ID_PATH,'the one regular file the request names, to compare it with the signed hash'],
       'side_effects':SIDE_EFFECTS,
       'never':['a file opened for writing','mkdir','chmod','chown','rename','removal','docker exec','compose up','a container with a bind it can write through',
                'a shell','systemctl','a pull','a network connection opened by this process'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'directories':MAX_DIRECTORIES,'read_bytes':MAX_READ_BYTES}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner,NativeLock):
    """Everything this source can do to the host: the read primitives, the signed commands, the lock probe."""


def decoded(value,digest,code):
    need(type(value) is str and len(value)<=4*MAX_READ_BYTES,code)
    try:raw=base64.b64decode(value.encode('ascii'),validate=True)
    except (ValueError,UnicodeEncodeError):raise Refused(code) from None
    need(sha(raw)==digest,code);return raw

def validate_plan(plan):
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    directories=plan['directories']
    need(type(directories) is list and 0<len(directories)<=MAX_DIRECTORIES,'DIRECTORIES_INVALID')
    for item in directories:
        need(type(item) is dict and set(item)=={'key','rows','open_root'} and text(item['key'],'[A-Z][A-Z0-9_]{0,31}')
             and type(item['rows']) is list and item['rows'] and type(item['rows'][-1]) is dict and type(item['rows'][-1].get('path')) is str,'DIRECTORIES_INVALID')
        validate_chain(item['rows'],item['rows'][-1]['path'],item['open_root'])
    keys=[item['key'] for item in directories];need(len(set(keys))==len(keys),'DIRECTORIES_INVALID')
    image=plan['image']
    need(image is None or (type(image) is dict and set(image)=={'reference','image_id','revision'} and text(image['reference'],REFERENCE)
                           and text(image['image_id'],IMAGE_ID) and text(image['revision'],'[0-9a-f]{40}')),'IMAGE_PLAN_INVALID')
    containers=plan['containers']
    need(containers is None or (type(containers) is list and 0<len(containers)<=MAX_NAMES and all(text(name,CONTAINER_NAME) for name in containers)
                                and len(set(containers))==len(containers)),'CONTAINERS_INVALID')
    environment=plan['environment']
    if environment is not None:
        need(type(environment) is dict and set(environment)=={'container','expected'} and containers is not None and environment['container'] in containers,'ENVIRONMENT_PLAN_INVALID')
        environment_format(environment['expected'])
    verify=plan['verify']
    if verify is not None:
        need(image is not None,'VERIFY_PLAN_INVALID')
        need(type(verify) is dict and set(verify)=={'script_b64','script_sha256','directory_key','target','expect'} and verify['directory_key'] in keys
             and hexpin(verify['script_sha256']) and type(verify['expect']) is dict,'VERIFY_PLAN_INVALID')
        decoded(verify['script_b64'],verify['script_sha256'],'SCRIPT_NOT_THE_SIGNED_HASH')
        run_arguments('verify',image['image_id'],[mount_of(plan)],['python','-I','-B','-'])
    render=plan['render']
    if render is not None:
        need(type(render) is dict and set(render)=={'project','env_file','files','override_b64','override_sha256','service','build_sha','environment'}
             and hexpin(render['override_sha256']) and text(render['service'],COMPOSE_SERVICE) and text(render['build_sha'],'[0-9a-f]{40}')
             and type(render['environment']) is dict,'RENDER_PLAN_INVALID')
        decoded(render['override_b64'],render['override_sha256'],'OVERRIDE_NOT_THE_SIGNED_HASH')
        compose_arguments(render['project'],render['env_file'],render['files'],True);environment_format(render['environment'])
    item=plan['file']
    if item is not None:
        need(type(item) is dict and set(item)=={'directory_key','name','sha256','bytes'} and item['directory_key'] in keys and text(item['name'],'[A-Za-z0-9._-]{1,128}')
             and item['name'] not in ('.','..') and hexpin(item['sha256']) and integer(item['bytes'],1,MAX_READ_BYTES),'FILE_PLAN_INVALID')
    lock=plan['lock']
    if lock is not None:
        need(type(lock) is dict and set(lock)=={'directory_key','name'} and lock['directory_key'] in keys and text(lock['name'],'[A-Za-z0-9._-]{1,128}')
             and lock['name'] not in ('.','..'),'LOCK_PLAN_INVALID')

def rows_of(plan,key):return [item for item in plan['directories'] if item['key']==key][0]['rows']
def mount_of(plan):
    return {'source':rows_of(plan,plan['verify']['directory_key'])[-1]['path'],'target':plan['verify']['target'],'read_only':True}

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    verify,render,item,lock=plan['verify'],plan['render'],plan['file'],plan['lock']
    return {'operation':OPERATION,'directories':{entry['key']:dict(chain_effects(entry['rows']),open_root=entry['open_root']) for entry in plan['directories']},
            'image':plan['image'],'containers':plan['containers'],'environment':plan['environment'],
            'verify':None if verify is None else {'script_sha256':verify['script_sha256'],'bind':mount_of(plan),'expect':verify['expect'],'network':'none'},
            'render':None if render is None else {key:render[key] for key in ('project','env_file','files','override_sha256','service','build_sha','environment')},
            'file':None if item is None else {'path':rows_of(plan,item['directory_key'])[-1]['path']+'/'+item['name'],'sha256':item['sha256'],'bytes':item['bytes']},
            'lock':None if lock is None else rows_of(plan,lock['directory_key'])[-1]['path']+'/'+lock['name'],
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],'writes':0,'containers_run':0 if verify is None else 1,'activation':False}
def success_of(plan):return COMPLETE_OUTCOME


def _reduce_directories(receipt):
    for item in (receipt.get('items') or {}).values():
        if type(item) is dict and 'observed' in item:item['observed']=len(item['observed'])
REDUCTIONS=[('DIRECTORY_ROWS_REDUCED_TO_COUNTS',_reduce_directories)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    verify,render=plan['verify'],plan['render']
    script=None if verify is None else decoded(verify['script_b64'],verify['script_sha256'],'SCRIPT_NOT_THE_SIGNED_HASH')                 # pure
    override=None if render is None else decoded(render['override_b64'],render['override_sha256'],'OVERRIDE_NOT_THE_SIGNED_HASH')
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    commands=Commands(host,gate);items={};findings=[];held={}
    def observe(name,action):
        """One item, observed on its own. An expiry stops the run; any other failure is that item's UNAVAILABLE."""
        try:items[name]=dict(action(),status='COMPLETE')
        except Exception as error:
            items[name]=safe(error)
            if items[name].get('code') in ('GO_EXPIRED','CLOCK_REVERSED'):raise
    def finding(code):findings.append(code)
    def finish(status,outcome,code):
        receipt=envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),clock=timing(begun,mark,clock,monotonic),
            commands_started=dict(commands.started),mutating_calls=state.counts(),items=items,findings=sorted(set(findings)),writes=0,
            containers_run=commands.started['CONTAINER'],phase_reached='OBSERVATION'))
        return seal(receipt)
    try:
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            def boot():
                same=boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256']
                if not same:finding('EVIDENCE_FROM_EARLIER_BOOT')
                return {'equal_to_the_evidence':same}
            observe('boot',boot)
            for entry in plan['directories']:
                def directory(entry=entry):
                    observed=[]
                    try:held[entry['key']]=Pinned(host,walk_pinned(host,entry['rows'],gate,observed),rows=entry['rows'])
                    except Refused as error:
                        finding(code_of(error,'PARENT_IDENTITY_MISMATCH'));return {'observed':observed,'as_signed':False}
                    return {'observed':observed,'as_signed':True,'entries':count_entries(host,held[entry['key']].fd,gate),
                            'bytes_available':free_bytes(host,held[entry['key']].fd)}
                observe('directory:'+entry['key'],directory)
            def image():
                facts=image_facts(commands,plan['image']['reference'])
                if facts['id']!=plan['image']['image_id']:finding('IMAGE_ID_MISMATCH')
                if facts['revision_label']!=plan['image']['revision']:finding('IMAGE_REVISION_MISMATCH')
                return facts
            if plan['image'] is not None:observe('image',image)
            def containers():
                rows=[container_facts(commands,name) for name in plan['containers']];listed=container_list(commands)
                if not all(row['running'] and row['state']=='running' for row in rows):finding('CONTAINER_NOT_RUNNING')
                if any(row['restarts'] for row in rows):finding('CONTAINER_RESTARTED')
                if sorted(row['id'] for row in rows)!=[row['id'] for row in listed]:finding('CONTAINER_SET_NOT_THE_SIGNED_ONE')
                return {'rows':rows,'listed':len(listed)}
            if plan['containers'] is not None:observe('containers',containers)
            if plan['environment'] is not None:
                def environment():
                    target=container_facts(commands,plan['environment']['container'])
                    values=container_environment(commands,target['id'],plan['environment']['expected'])
                    if not all(value['equal'] for value in values.values()):finding('ENVIRONMENT_NOT_AS_SIGNED')
                    return {'names':values}
                observe('environment',environment)
            if verify is not None:
                def container_item():
                    result=container_run(commands,'verify',plan['image']['image_id'],[mount_of(plan)],['python','-I','-B','-'],script)
                    facts={'started':result['started'],'returned':result['returned'],'returncode':result['returncode'],'code':result['code'],
                           'container_may_still_exist':result['started'] and not result['returned']}
                    if not result['returned']:
                        finding('VERIFY_RUN_NOT_COMPLETED');return facts
                    facts['engine_failure']=result['returncode'] in RUN_ENGINE_STATUSES
                    line=single_line(result['output']) if result['returncode']==0 else None
                    facts['as_expected']=line==verify['expect']
                    if not facts['as_expected']:finding('VERIFY_RESULT_NOT_AS_SIGNED')
                    return facts
                observe('verify',container_item)
            if render is not None:
                def rendered():
                    service=compose_service(compose_render(commands,'render',render['project'],render['env_file'],render['files'],render['build_sha'],override=override),render['service'])
                    equal={key:service['environment'].get(key)==value for key,value in sorted(render['environment'].items())}
                    revision=service['environment'].get('C3PO_BUILD_SHA')==render['build_sha']
                    if not (all(equal.values()) and revision):finding('RENDER_NOT_AS_SIGNED')
                    return {'environment_equal':equal,'build_revision_equal':revision,'image_reference':service['image'] if text(service['image'],REFERENCE) else None}
                observe('render',rendered)
            if plan['file'] is not None:
                def regular():
                    item=plan['file'];raw,info=read_regular(host,item['name'],held[item['directory_key']].fd,gate,MAX_READ_BYTES)
                    equal=sha(raw)==item['sha256'] and len(raw)==item['bytes']
                    if not equal:finding('FILE_NOT_THE_SIGNED_BYTES')
                    return dict(shape(info),links=info.st_nlink,bytes_equal_signed=equal)
                observe('file',regular)
            if plan['lock'] is not None:
                def locked():
                    lock=plan['lock'];fd=open_lock(host,lock['name'],held[lock['directory_key']],gate)
                    try:return {'state':probe_lock(host,fd)}
                    finally:host.close(fd)
                observe('lock',locked)
        except Refused as error:
            code=code_of(error,'OBSERVATION_FAILED')
            if not items:return seal(envelope(REFUSED_STATUS,REFUSED_OUTCOME,code,dict(bound,phase_reached='BEFORE_ANY_OBSERVATION',mutating_calls=state.counts(),writes=0)))
            return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,code)
        status=combined(items.values())
        if status!='COMPLETE':return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,'OBSERVATION_INCOMPLETE')
        if findings:return finish(PARTIAL_STATUS,MISMATCH_OUTCOME,sorted(set(findings))[0])
        return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None)
    finally:
        for handle in held.values():
            try:handle.close()
            except Exception:pass
