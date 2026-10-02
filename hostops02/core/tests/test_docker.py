"""parts/docker.py on the emulated engine: image and container metadata in the proven templates, the environment of a
container as booleans, the attached run, and docker compose with an explicit file list. No docker binary."""
import json
import types

import pytest

import demos
import family as f
import hostemu

W=lambda:f.load(demos.WRITE).m
R=lambda:f.load(demos.READ).m
refusal=f.refusal
# Not named setup: pytest before 8 (its nose support, pytest 7.4 of Ubuntu 24.04 included) takes a module-level
# callable named setup for setup_module and calls it with the module, once, before the first test of the file.
def wired(m,remaining=lambda:60.0):
    host=f.wire(types.SimpleNamespace(m=m),hostemu.world());return m.Commands(host,remaining),host
COMPOSE=(hostemu.PROJECT,hostemu.ENV_FILE,[hostemu.COMPOSE_FILE])

# ---------------------------------------------------------------- image and container metadata
def test_image_facts_by_id_and_by_reference_and_what_is_never_requested():
    m=W();c,host=wired(m)
    facts=m.image_facts(c,hostemu.BACKEND)
    assert facts=={'id':hostemu.BACKEND,'repo_tags':['c3po/backend:production'],'repo_tag_count':1,'repo_tags_all_valid':True,
                   'reference_among_repo_tags':False,'revision_label':hostemu.REVISION}
    assert m.image_facts(c,'c3po/backend:production')['reference_among_repo_tags'] is True and host.docker.modes[-1]=='raw'
    assert 'never-emit' not in json.dumps(facts) and 'Env' not in m.IMAGE_FORMAT
    assert refusal(lambda:m.image_facts(c,'sha256:'+'0'*64))=='COMMAND_FAILED'
    host.docker.images[0]['Config']['Labels']={};assert m.image_facts(c,hostemu.BACKEND)['revision_label'] is None
    host.docker.images[0]['Config']['Labels']={'org.opencontainers.image.revision':'not-a-revision'};assert m.image_facts(c,hostemu.BACKEND)['revision_label'] is None
    m.image_facts(c,hostemu.BACKEND,docker_config='/etc/c3po-bar/docker-cli');assert host.commands[-1]['docker_config']=='/etc/c3po-bar/docker-cli'
    # what the engine prints must be an image ID and exactly the three members
    host.docker.images[1]['Id']='not-an-image-id';assert refusal(lambda:m.image_facts(c,'c3po/web:production'))=='IMAGE_METADATA_INVALID'
    host.docker.images[1]['Id']=hostemu.WEB;host.docker.images[1]['RepoTags']='c3po/web:production';assert refusal(lambda:m.image_facts(c,hostemu.WEB))=='IMAGE_METADATA_INVALID'

def test_container_facts_by_name_and_by_id_validate_every_member():
    m=W();c,host=wired(m);raw=host.docker.container(hostemu.WORKER)
    row=m.container_facts(c,hostemu.WORKER)
    assert row=={'name':'/'+hostemu.WORKER,'id':raw['Id'],'image_id':hostemu.BACKEND,'image_reference':'c3po/backend:production','running':True,'state':'running',
                 'started_at':raw['State']['StartedAt'],'host_pid':raw['State']['Pid'],'restarts':0,'health':None}
    assert m.container_facts(c,raw['Id'])==row and m.container_facts(c,raw['Id'],expected_name=hostemu.WORKER)==row
    assert m.container_facts(c,'c3po-db-1')['health']=='healthy'
    assert 'never-emit' not in json.dumps(row) and 'Env' not in m.CONTAINER_FORMAT
    assert refusal(lambda:m.container_facts(c,raw['Id'],expected_name='c3po-api-1'))=='CONTAINER_METADATA_INVALID'
    assert refusal(lambda:m.container_facts(c,'no-such-container'))=='COMMAND_FAILED'
    for bad in ('','/'+hostemu.WORKER,'a b','x'*129,None,7):assert refusal(lambda:m.container_facts(c,bad))=='CONTAINER_TARGET'
    assert refusal(lambda:m.container_facts(c,hostemu.WORKER,expected_name='a b'))=='CONTAINER_TARGET'
    # a container the engine reports under another name or ID than the one asked for is not accepted
    other=host.docker.container('c3po-api-1');saved=raw['Name'];raw['Name']='/renamed'
    assert refusal(lambda:m.container_facts(c,raw['Id'],expected_name=hostemu.WORKER))=='CONTAINER_METADATA_INVALID';raw['Name']=saved
    for member,value in (('Image','not-an-id'),('RestartCount',-1),('RestartCount','0')):
        saved=raw[member];raw[member]=value;assert refusal(lambda:m.container_facts(c,hostemu.WORKER))=='CONTAINER_METADATA_INVALID';raw[member]=saved
    for member,value in (('Status','unknown-state'),('Running','yes'),('Pid',-5),('StartedAt','x'*65)):
        saved=raw['State'][member];raw['State'][member]=value;assert refusal(lambda:m.container_facts(c,hostemu.WORKER))=='CONTAINER_METADATA_INVALID';raw['State'][member]=saved
    raw['State']['Health']={'Status':'weird'};assert refusal(lambda:m.container_facts(c,hostemu.WORKER))=='CONTAINER_METADATA_INVALID'
    del raw['State']['Health'];assert m.container_facts(c,hostemu.WORKER)==row
    # an engine that answers with another container than the one asked for, by name or by ID, is not believed
    other=host.docker.container('c3po-api-1');real=host.docker.container;host.docker.container=lambda reference:other
    assert refusal(lambda:m.container_facts(c,hostemu.WORKER))=='CONTAINER_METADATA_INVALID' and refusal(lambda:m.container_facts(c,raw['Id']))=='CONTAINER_METADATA_INVALID'
    assert m.container_facts(c,'c3po-api-1')['id']==other['Id'] and m.container_facts(c,other['Id'])['name']=='/c3po-api-1';host.docker.container=real
    # a restart loop is visible: state and restart count are what a liveness read compares
    raw['State'].update(Status='restarting',Running=True);raw['RestartCount']=7
    assert (m.container_facts(c,hostemu.WORKER)['state'],m.container_facts(c,hostemu.WORKER)['restarts'])==('restarting',7)

def test_container_list_is_every_container_sorted_and_a_failed_listing_is_never_an_empty_list():
    m=W();c,host=wired(m);rows=m.container_list(c)
    assert [row['id'] for row in rows]==sorted(item['Id'] for item in host.docker.containers) and {row['name'] for row in rows}=={'c3po-%s-1'%name for name in hostemu.SERVICES}
    assert all(set(row)=={'id','name','state'} and row['state']=='running' for row in rows)
    host.docker.containers.append(hostemu.container('stray',hostemu.BACKEND,'c3po/backend:production',[],running=False))
    assert len(m.container_list(c))==9 and [row for row in m.container_list(c) if row['name']=='stray'][0]['state']=='exited'
    host.docker.ps_returncode=1;assert refusal(lambda:m.container_list(c))=='COMMAND_FAILED';host.docker.ps_returncode=0
    host.docker.containers.append(dict(host.docker.containers[0]));assert refusal(lambda:m.container_list(c))=='CONTAINER_LIST_INVALID';host.docker.containers.pop()
    host.docker.containers[-1]['Name']='/bad name';assert refusal(lambda:m.container_list(c))=='CONTAINER_LIST_INVALID';host.docker.containers.pop()
    host.docker.containers=[];assert m.container_list(c)==[]
    host.docker.containers=[hostemu.container('c%d'%index,hostemu.BACKEND,'x',[]) for index in range(129)];assert refusal(lambda:m.container_list(c))=='CONTAINER_LIST_INVALID'

def test_container_environment_reports_presence_and_equality_as_booleans_and_no_value():
    m=W();c,host=wired(m);worker=host.docker.container(hostemu.WORKER);worker['Config']['Env']+=['EMPTY=','PATHLIKE=/a/b:c@d+e=f']
    expected={'C3PO_BUILD_SHA':hostemu.REVISION,'C3PO_SERVICE_NAME':'api','ABSENT_KEY':'x','EMPTY':'','PATHLIKE':'/a/b:c@d+e=f','C3PO_DATABASE_URL':'wrong'}
    values=m.container_environment(c,worker['Id'],expected)
    assert values=={'C3PO_BUILD_SHA':{'present':True,'equal':True},'C3PO_SERVICE_NAME':{'present':True,'equal':False},'ABSENT_KEY':{'present':False,'equal':False},
                    'EMPTY':{'present':True,'equal':True},'PATHLIKE':{'present':True,'equal':True},'C3PO_DATABASE_URL':{'present':True,'equal':False}}
    argv=host.commands[-1]['argv'];assert argv[1:4]==['container','inspect','--format'] and argv[4]==m.environment_format(expected) and argv[5]==worker['Id']
    assert hostemu.SECRET not in ' '.join(argv) and host.docker.modes[-1]=='typed'
    # a name that is a prefix of another is not that other name; an entry without "=" is no name at all
    worker['Config']['Env']+=['C3PO_BUILD_SHA_EXTRA='+hostemu.REVISION,'BARE']
    assert m.container_environment(c,worker['Id'],{'C3PO_BUILD':hostemu.REVISION,'BARE':''})=={'C3PO_BUILD':{'present':False,'equal':False},'BARE':{'present':True,'equal':False}}
    # only by ID, so the booleans are those of the container that was inspected before
    assert refusal(lambda:m.container_environment(c,hostemu.WORKER,{'A':'b'}))=='CONTAINER_TARGET'
    for bad in ({}, {'lower':'x'},{'A':'has space'},{'A':'quote"'},{'A':'back\\slash'},{'A':'{{brace}}'},{'A':None},{'A':7},{'A':'x'*257},{'A B':'x'},
                dict(('K%d'%index,'v') for index in range(17)),None,[('A','b')]):
        assert refusal(lambda:m.container_environment(c,worker['Id'],bad))=='ENVIRONMENT_EXPECTATION',bad
    host.docker.inspect_returncode=1;assert refusal(lambda:m.container_environment(c,worker['Id'],{'A':'b'}))=='COMMAND_FAILED';host.docker.inspect_returncode=0
    # the answer must be exactly one pair of booleans per signed name, and "equal" never without "present"
    render=host.docker.render
    for answer in ('{"A":{"present":true,"equal":true},"B":{"present":true,"equal":true}}','{}','{"A":{"present":true}}','{"A":{"present":"true","equal":true}}',
                   '{"A":{"present":true,"equal":1}}','{"A":{"present":false,"equal":true}}','{"A":true}','{"A":{"present":true,"equal":true,"value":"x"}}'):
        host.docker.render=lambda template,schema,raw,fallback,answer=answer:(0,answer.encode()+b'\n')
        assert refusal(lambda:m.container_environment(c,worker['Id'],{'A':'b'}))=='ENVIRONMENT_METADATA_INVALID',answer
    host.docker.render=lambda template,schema,raw,fallback:(0,b'{"A":{"present":true,"equal":false}}\n')
    assert m.container_environment(c,worker['Id'],{'A':'b'})=={'A':{'present':True,'equal':False}};host.docker.render=render

def test_environment_format_is_built_only_from_the_constructs_that_ran_on_the_host():
    m=W();template=m.environment_format({'B_KEY':'v2','A_KEY':'v1'})
    assert template==('{{"{"}}'
        '{{ $p := false }}{{ $e := false }}{{ range .Config.Env }}{{ $pieces := split . "=" }}{{ if eq (index $pieces 0) "A_KEY" }}{{ $p = true }}{{ if eq . "A_KEY=v1" }}{{ $e = true }}{{ end }}{{ end }}{{ end }}"A_KEY":{"present":{{json $p}},"equal":{{json $e}}},'
        '{{ $p := false }}{{ $e := false }}{{ range .Config.Env }}{{ $pieces := split . "=" }}{{ if eq (index $pieces 0) "B_KEY" }}{{ $p = true }}{{ if eq . "B_KEY=v2" }}{{ $e = true }}{{ end }}{{ end }}{{ end }}"B_KEY":{"present":{{json $p}},"equal":{{json $e}}}}')
    assert not template.startswith('{{{') and '{{{' not in template


# ---------------------------------------------------------------- the attached run
MOUNT={'source':hostemu.DATA,'target':'/selftest','read_only':True}
def test_run_arguments_are_the_readme_argv_with_binds_image_id_and_command():
    m=R();middle=m.run_arguments('verify',hostemu.BACKEND,[MOUNT],['python','-I','-B','-','/selftest','R2D2-V2-SHADOW-2026-10-05'])
    assert middle==['--mount','type=bind,source=/mnt/day-d-data,target=/selftest,readonly',hostemu.BACKEND,'python','-I','-B','-','/selftest','R2D2-V2-SHADOW-2026-10-05']
    assert m.run_arguments('verify',hostemu.BACKEND,[],['python'],container_name='c3po-selftest-1')[:2]==['--name','c3po-selftest-1']
    w=W();assert w.run_arguments('script',hostemu.BACKEND,[dict(MOUNT,read_only=False)],['python'])==['--mount','type=bind,source=/mnt/day-d-data,target=/selftest',hostemu.BACKEND,'python']
    assert w.COMMANDS['script']['argv']==w.RUN_PREFIX and m.COMMANDS['verify']['argv']==m.RUN_PREFIX

def test_run_arguments_refuse_a_tag_a_writable_bind_in_a_container_row_and_anything_outside_the_grammar():
    m=R()
    assert refusal(lambda:m.run_arguments('verify',hostemu.BACKEND,[dict(MOUNT,read_only=False)],['python']))=='MOUNT_NOT_READ_ONLY'
    for image in ('c3po/backend:production','sha256:'+'f'*63,'fb'*32,None):assert refusal(lambda:m.run_arguments('verify',image,[MOUNT],['python']))=='IMAGE_ID'
    for mount in (dict(MOUNT,source='relative'),dict(MOUNT,source='/a,b'),dict(MOUNT,source='/a=b'),dict(MOUNT,target='/'),dict(MOUNT,target='/a/../b'),dict(MOUNT,source='/a//b'),
                  dict(MOUNT,read_only=1),dict(MOUNT,extra=1),{'source':hostemu.DATA,'target':'/x'},dict(MOUNT,source='/a b'),None,'type=bind,source=/,target=/host'):
        assert refusal(lambda:m.run_arguments('verify',hostemu.BACKEND,[mount],['python']))=='MOUNT_INVALID',mount
    assert refusal(lambda:m.run_arguments('verify',hostemu.BACKEND,[MOUNT,dict(MOUNT,source='/etc')],['python']))=='MOUNT_INVALID','two binds on one target'
    assert refusal(lambda:m.run_arguments('verify',hostemu.BACKEND,[dict(MOUNT,target='/t%d'%index) for index in range(5)],['python']))=='MOUNT_INVALID'
    assert refusal(lambda:m.run_arguments('verify',hostemu.BACKEND,(MOUNT,),['python']))=='MOUNT_INVALID'
    for command in ([],['--privileged'],['-v','/:/host'],['python','a b'],['python','$(x)'],['python',';'],['python','x'*201],['python']*17,'python',None,['python',7]):
        assert refusal(lambda:m.run_arguments('verify',hostemu.BACKEND,[MOUNT],command))=='RUN_COMMAND_INVALID',command
    for name in ('Upper','a b','-x','x'*64):assert refusal(lambda:m.run_arguments('verify',hostemu.BACKEND,[MOUNT],['python'],container_name=name))=='CONTAINER_TARGET'
    for row in ('image','render','container_list'):assert refusal(lambda:m.run_arguments(row,hostemu.BACKEND,[MOUNT],['python']))=='COMMAND_KIND'

def test_container_run_passes_the_bytes_and_returns_the_result_without_raising():
    m=R();c,host=wired(m);host.docker.on_run=demos.reading_container
    result=m.container_run(c,'verify',hostemu.BACKEND,[MOUNT],['python','-I','-B','-'],demos.READ_SCRIPT,docker_config='/etc/c3po-bar/docker-cli')
    assert result['started'] and result['returned'] and result['returncode']==0 and result['code'] is None
    assert m.single_line(result['output'])=={'entries':sorted(host.tree.get(hostemu.DATA).children),'status':'LISTED'}
    last=host.commands[-1];assert last['stdin']==demos.READ_SCRIPT and last['seconds']==20
    assert last['argv']==['/usr/bin/docker','run','--rm','-i','--pull','never','--init','--user','0:0','--network','none','--read-only','--cap-drop','ALL',
                          '--security-opt','no-new-privileges','--mount','type=bind,source=/mnt/day-d-data,target=/selftest,readonly',hostemu.BACKEND,'python','-I','-B','-']
    assert last['docker_config']=='/etc/c3po-bar/docker-cli' and host.docker.runs[-1].environment=={'DOCKER_CONFIG':'/etc/c3po-bar/docker-cli'}
    assert c.started=={'READ':0,'CONTAINER':1,'EFFECT':0} and host.mutating()==[] and len(host.container_runs())==1
    # the engine's own failures are a returned exit status, not an exception: 125 for an image that is not there
    host.docker.images=[item for item in host.docker.images if item['Id']!=hostemu.BACKEND]
    result=m.container_run(c,'verify',hostemu.BACKEND,[MOUNT],['python'],b'x');assert (result['returned'],result['returncode'])==(True,125) and 125 in m.RUN_ENGINE_STATUSES
    # a timeout: started, not returned; the container may still exist
    host.hang={('run','--rm')};result=m.container_run(c,'verify',hostemu.BACKEND,[MOUNT],['python'],b'x')
    assert result=={'started':True,'returned':False,'returncode':None,'output':b'','code':'COMMAND_TIMEOUT'}
    # no budget for the whole class: not started at all
    c2,host2=wired(m,lambda:23.9);result=m.container_run(c2,'verify',hostemu.BACKEND,[MOUNT],['python'],b'x')
    assert result=={'started':False,'returned':False,'returncode':None,'output':b'','code':'COMMAND_NOT_STARTED_BUDGET'} and host2.commands==[]
    w=W();cw,_=wired(w);assert refusal(lambda:w.container_run(cw,'script',hostemu.BACKEND,[],['python'],b'x'))=='COMMAND_KIND'

def test_container_effect_is_counted_and_a_container_row_cannot_be_used_as_an_effect():
    w=W();c,host=wired(w);host.docker.on_run=lambda call:(call.write('/selftest/made',b'x') or 0,b'{"ok":true}\n');state=w.Effects()
    result=w.container_effect(state,c,'script',hostemu.BACKEND,[dict(MOUNT,read_only=False)],['python','-I','-B','-'],b'script')
    assert result['returned'] and result['returncode']==0 and w.single_line(result['output'])=={'ok':True} and state.pending
    assert host.tree.get(hostemu.DATA+'/made') is not None and len(host.effect_commands())==1 and c.started['EFFECT']==1
    state.done();assert state.counts()=={'issued':1,'succeeded':1,'failed_nothing_changed':0,'uncertain':0}
    r=R();cr,_=wired(r);assert refusal(lambda:r.container_effect(r.Effects(),cr,'verify',hostemu.BACKEND,[MOUNT],['python'],b'x'))=='COMMAND_KIND'

def test_single_line_is_exactly_one_json_object_on_one_line():
    m=W();assert m.single_line(b'{"a":1}\n')=={'a':1}
    for raw,code in ((b'{"a":1}','RUN_OUTPUT_NOT_ONE_LINE'),(b'{"a":1}\n{"b":2}\n','RUN_OUTPUT_NOT_ONE_LINE'),(b'','RUN_OUTPUT_NOT_ONE_LINE'),(b'\n','DOCUMENT_SIZE'),
                     (b'[1]\n','DOCUMENT_TYPE'),(b'{"a":1,"a":2}\n','DUPLICATE_KEY'),(b'not json\n','JSON_INVALID'),(b'{"a":NaN}\n','NONFINITE_JSON'),('text\n','RUN_OUTPUT_NOT_ONE_LINE')):
        assert refusal(lambda:m.single_line(raw))==code,raw


# ---------------------------------------------------------------- docker compose
def test_compose_arguments_always_name_the_project_the_environment_file_and_every_file():
    m=W()
    assert m.compose_arguments(*COMPOSE)==['--project-name','c3po','--env-file',hostemu.ENV_FILE,'-f',hostemu.COMPOSE_FILE]
    assert m.compose_arguments(hostemu.PROJECT,hostemu.ENV_FILE,[hostemu.COMPOSE_FILE,'/mnt/day-d-data/live/compose.proof.json'],True)[-6:]==[
        '-f',hostemu.COMPOSE_FILE,'-f','/mnt/day-d-data/live/compose.proof.json','-f','-']
    for project in ('','C3PO','a b','-x',None,'x'*64):assert refusal(lambda:m.compose_arguments(project,hostemu.ENV_FILE,[hostemu.COMPOSE_FILE]))=='COMPOSE_PROJECT'
    for env_file,files in ((None,[hostemu.COMPOSE_FILE]),('relative/.env',[hostemu.COMPOSE_FILE]),('/',[hostemu.COMPOSE_FILE]),(hostemu.ENV_FILE,[]),(hostemu.ENV_FILE,None),
                           (hostemu.ENV_FILE,[hostemu.COMPOSE_FILE]*2),(hostemu.ENV_FILE,['-']),(hostemu.ENV_FILE,['compose.yml']),(hostemu.ENV_FILE,['/a/../b.yml']),
                           (hostemu.ENV_FILE,(hostemu.COMPOSE_FILE,)),(hostemu.ENV_FILE,['/f%d.yml'%index for index in range(5)]),(hostemu.ENV_FILE,[hostemu.COMPOSE_FILE,7]),
                           (hostemu.ENV_FILE,[hostemu.COMPOSE_FILE,'--project-directory'])):
        assert refusal(lambda:m.compose_arguments(hostemu.PROJECT,env_file,files))=='COMPOSE_FILES',(env_file,files)

def test_compose_render_with_the_override_on_standard_input_and_the_build_revision_as_a_variable():
    m=W();c,host=wired(m);rendered=m.compose_render(c,'render',*COMPOSE,hostemu.REVISION,override=demos.override())
    service=m.compose_service(rendered,'r2d2-worker')
    assert service['image']=='c3po/backend:production' and service['environment']['C3PO_BUILD_SHA']==hostemu.REVISION
    assert all(service['environment'][key]==value for key,value in demos.KEYS.items())
    last=host.commands[-1];assert last['argv'][1:]==['compose','--project-name','c3po','--env-file',hostemu.ENV_FILE,'-f',hostemu.COMPOSE_FILE,'-f','-','config','--format','json']
    assert last['variables']=={'C3PO_BUILD_SHA':hostemu.REVISION} and last['stdin']==demos.override() and last['seconds']==15 and last['limit']==1048576
    assert host.mutating()==[] and host.docker.compose.calls[-1]['files']==[hostemu.COMPOSE_FILE,'-']
    # the render carries the values of the environment file: the caller sees them, a receipt never may
    assert hostemu.SECRET in json.dumps(rendered)
    assert m.compose_service(rendered,'web')=={'image':'c3po/web:production','environment':{}}
    for name in ('no-such-service','Bad Name',None):assert refusal(lambda:m.compose_service(rendered,name))=='COMPOSE_SERVICE_INVALID'
    for bad in ({'image':7},{'image':''},{'image':'x','environment':[]},{'image':'x','environment':{'A':1}},'text'):
        assert refusal(lambda:m.compose_service({'services':{'r2d2-worker':bad}},'r2d2-worker'))=='COMPOSE_SERVICE_INVALID'
    assert m.compose_service({'services':{'x':{'image':'i','environment':{'A':None,'B':'b'}}}},'x')['environment']=={'A':None,'B':'b'}

def test_compose_render_from_files_and_its_refusals():
    m=W();c,host=wired(m);host.tree.add(hostemu.DATA+'/o.json',kind='file',content=demos.override(),dev=hostemu.DATA_DEVICE)
    rendered=m.compose_render(c,'render_files',hostemu.PROJECT,hostemu.ENV_FILE,[hostemu.COMPOSE_FILE,hostemu.DATA+'/o.json'],hostemu.REVISION)
    assert m.compose_service(rendered,'r2d2-worker')['environment']['C3PO_R2D2_V2_LIVE_POLICY_SHA']=='5'*64 and host.commands[-1]['stdin'] is None
    # the row and the way it is used must agree: a row that takes standard input needs the override, and the reverse
    assert refusal(lambda:m.compose_render(c,'render',*COMPOSE,hostemu.REVISION))=='COMMAND_KIND'
    assert refusal(lambda:m.compose_render(c,'render_files',*COMPOSE,hostemu.REVISION,override=b'{}'))=='COMMAND_KIND'
    assert refusal(lambda:m.compose_render(c,'recreate',*COMPOSE,hostemu.REVISION))=='COMMAND_KIND' and refusal(lambda:m.compose_render(c,'image',*COMPOSE,hostemu.REVISION))=='COMMAND_KIND'
    for revision in ('development','',None,'A'*40):assert refusal(lambda:m.compose_render(c,'render_files',*COMPOSE,revision))=='COMMAND_VARIABLES'
    assert refusal(lambda:m.compose_render(c,'render_files',hostemu.PROJECT,hostemu.ENV_FILE,[hostemu.COMPOSE_FILE,'/no/such.json'],hostemu.REVISION))=='COMMAND_FAILED'
    for output in (b'',b'not json',b'[]',b'{"services":[]}',b'{"a":1,"a":2}'):
        host.docker.compose.config_output=output;assert refusal(lambda:m.compose_render(c,'render_files',*COMPOSE,hostemu.REVISION))=='COMPOSE_RENDER_INVALID',output
    host.docker.compose.config_output=b'{"services":{},"pad":"'+b'x'*1048576+b'"}';assert refusal(lambda:m.compose_render(c,'render_files',*COMPOSE,hostemu.REVISION))=='COMMAND_OUTPUT_LIMIT'
    host.docker.compose.config_output=b'{"services":{},"pad":"'+b'x'*200000+b'"}';assert m.compose_render(c,'render_files',*COMPOSE,hostemu.REVISION)['services']=={}

def test_compose_up_recreates_only_the_named_service_with_the_same_file_list_and_is_counted():
    m=W();c,host=wired(m);host.tree.add(hostemu.DATA+'/o.json',kind='file',content=demos.override(),dev=hostemu.DATA_DEVICE);state=m.Effects()
    before={item['Name']:item['Id'] for item in host.docker.containers};files=[hostemu.COMPOSE_FILE,hostemu.DATA+'/o.json']
    result=m.compose_up(state,c,'recreate',hostemu.PROJECT,hostemu.ENV_FILE,files,hostemu.REVISION)
    assert result=={'started':True,'returned':True,'returncode':0,'output':b'','code':None} and state.pending
    last=host.commands[-1];assert last['argv'][1:]==['compose','--project-name','c3po','--env-file',hostemu.ENV_FILE,'-f',hostemu.COMPOSE_FILE,'-f',hostemu.DATA+'/o.json',
                                                     'up','-d','--no-deps','--no-build','--pull','never','--force-recreate','r2d2-worker']
    assert (last['seconds'],last['capture'],last['variables'],last['stdin'])==(30,False,{'C3PO_BUILD_SHA':hostemu.REVISION},None)
    after={item['Name']:item['Id'] for item in host.docker.containers};assert [name for name in before if before[name]!=after[name]]==['/'+hostemu.WORKER]
    values=m.container_environment(c,after['/'+hostemu.WORKER],dict(demos.KEYS,C3PO_BUILD_SHA=hostemu.REVISION));assert all(item['equal'] for item in values.values())
    state.done()
    # a render row, a row for another form of up, or standard input cannot reach compose_up
    for row in ('render','render_files','image','script'):assert refusal(lambda:m.compose_up(m.Effects(),c,row,*COMPOSE,hostemu.REVISION))=='COMMAND_KIND'
    assert refusal(lambda:m.compose_up_tail('Bad Service'))=='COMPOSE_SERVICE' and m.COMMANDS['recreate']['tail']==m.compose_up_tail('r2d2-worker')

def test_compose_up_without_the_build_revision_would_render_development_which_is_why_it_is_always_passed():
    """compose.yml interpolates C3PO_BUILD_SHA with the default "development": the recreate of 2026-09-28 exported the
    revision, and a recreate without it would start a worker whose release verification fails."""
    m=W();c,host=wired(m);code,out=host.docker.run(['compose']+m.compose_arguments(*COMPOSE)+['config','--format','json'])
    assert json.loads(out)['services']['r2d2-worker']['environment']['C3PO_BUILD_SHA']=='development'
    assert m.compose_service(m.compose_render(c,'render_files',*COMPOSE,hostemu.REVISION),'r2d2-worker')['environment']['C3PO_BUILD_SHA']==hostemu.REVISION
