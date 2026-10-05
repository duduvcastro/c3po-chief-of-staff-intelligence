"""The emulation itself. What the emulated Docker CLI does with a template is the only "engine" the helpers of the core
meet offline, so its behaviour is pinned here against the documented semantics of Go's text/template and of the
Docker CLI, construct by construct. Nothing here proves a real engine: that is the Linux job of each operation."""
import errno
import fcntl
import json

import pytest

import hostemu
from hostemu import execute,parse,Struct,rawify,TemplateSyntax,ExecError

def render(template,data,missing_error=False):return execute(parse(template),data,missing_error)

def test_variables_declared_outside_a_block_are_assigned_inside_it_and_keep_the_value():
    """Go 1.11: "=" changes the variable of the enclosing scope; ":=" inside a block declares a new one that ends with it."""
    assert render('{{ $p := false }}{{ range . }}{{ if eq . "b" }}{{ $p = true }}{{ end }}{{ end }}{{json $p}}',['a','b','c'])=='true'
    assert render('{{ $p := false }}{{ range . }}{{ if eq . "z" }}{{ $p = true }}{{ end }}{{ end }}{{json $p}}',['a','b','c'])=='false'
    assert render('{{ $p := false }}{{ range . }}{{ $p := true }}{{ end }}{{json $p}}',['a'])=='false','a declaration inside the block shadows'
    assert render('{{ $p := 1 }}{{ $p := 2 }}{{json $p}}',None)=='2','a second declaration in the same scope is allowed'
    with pytest.raises(ExecError):render('{{ $q = true }}',None)
    assert render('{{ $x := "a" }}{{ if true }}{{ $x = "b" }}{{ end }}{{ $x }}',None)=='b'

def test_comparison_and_boolean_functions_follow_text_template():
    assert render('{{json (eq "a" "a")}} {{json (eq "a" "b")}} {{json (eq 1 1)}} {{json (ne "a" "b")}}',None)=='true false true true'
    assert render('{{json (eq "x" "a" "x")}}',None)=='true','eq compares the first argument with each of the others'
    for bad in ('{{eq "a" 1}}','{{eq 1 true}}','{{eq "a"}}','{{eq . "a"}}'):
        with pytest.raises(ExecError):render(bad,None)
    assert render('{{if or false false}}y{{else}}n{{end}}{{if or false true}}y{{else}}n{{end}}{{if and true false}}y{{else}}n{{end}}{{if not false}}y{{end}}',None)=='nyny'
    assert render('{{or "" "fallback"}}|{{and "a" "b"}}',None)=='fallback|b','or and and return one of their arguments'

def test_split_lower_len_and_index_on_the_result():
    assert render('{{ $pieces := split . "=" }}{{index $pieces 0}}|{{len $pieces}}','KEY=va=lue')=='KEY|3'
    assert render('{{ $pieces := split . "=" }}{{index $pieces 0}}|{{len $pieces}}','NOEQUALS')=='NOEQUALS|1'
    assert render('{{lower .}}','MiXeD')=='mixed'
    with pytest.raises(ExecError):render('{{ $pieces := split . "=" }}{{index $pieces 1}}','NOEQUALS')
    with pytest.raises(ExecError):render('{{split . "="}}',7)

def test_else_if_and_literal_braces():
    template='{{if eq . "a"}}A{{else if eq . "b"}}B{{else}}C{{end}}'
    assert [render(template,value) for value in ('a','b','c')]==['A','B','C']
    assert render('{{"{"}}"k":{{json .}}}',1)=='{"k":1}'
    with pytest.raises(TemplateSyntax):parse('{{{json .}}}')          # three braces: the lesson of an earlier payload
    with pytest.raises(TemplateSyntax):parse('{{ nosuchfunction . }}')
    with pytest.raises(TemplateSyntax):parse('{{if true}}unclosed')

def test_typed_execution_first_then_the_raw_fallback_with_missingkey_error():
    host=hostemu.world();docker=host.docker;worker=docker.container(hostemu.WORKER)
    code,out=docker.run(['container','inspect','--format','{{json .Config.Env}}',hostemu.WORKER]);assert code==0 and docker.modes[-1]=='typed'
    code,out=docker.run(['container','inspect','--format','{{if index .State "Health"}}h{{else}}n{{end}}',hostemu.WORKER])
    assert (code,out,docker.modes[-1])==(0,b'n\n','raw'),'index of a typed struct fails; the raw JSON is then used'
    code,out=docker.run(['container','inspect','--format','{{if index .State "Health"}}{{json (index .State "Health" "Status")}}{{end}}','c3po-db-1'])
    assert (code,out)==(0,b'"healthy"\n')
    assert docker.run(['container','inspect','--format','{{.NoSuchField}}',hostemu.WORKER])[0]==1,'neither mode has the field'
    assert docker.run(['container','inspect','--format','{{{bad}}}',hostemu.WORKER])[0]==64
    assert docker.run(['container','inspect','--format','{{.Id}}','no-such-container'])==(1,b'')
    assert docker.run(['container','inspect','--format','{{.Id}}',worker['Id']])==(0,(worker['Id']+'\n').encode()),'a full ID resolves as a name does'

def test_ps_lists_every_container_typed_and_never_falls_back():
    host=hostemu.world();docker=host.docker
    code,out=docker.run(['ps','-a','--no-trunc','--format','{"id":{{json .ID}},"name":{{json .Names}},"state":{{json .State}}}'])
    rows=[json.loads(line) for line in out.splitlines()];assert code==0 and len(rows)==8 and {row['name'] for row in rows}=={'c3po-%s-1'%name for name in hostemu.SERVICES}
    assert docker.run(['ps','-a','--no-trunc','--format','{{.Config}}'])[0]==1
    with pytest.raises(AssertionError):docker.run(['ps','--format','{{.ID}}'])

def test_attached_run_is_parsed_as_the_cli_parses_it_and_binds_behave_as_the_kernel_does():
    host=hostemu.world();docker=host.docker;seen=[]
    def behaviour(call):
        seen.append(call);assert call.read('/in/.deploy-version')==(hostemu.REVISION+'\n').encode() and '.env' in call.listdir('/in')
        with pytest.raises(OSError) as caught:call.write('/in/new',b'x')
        assert caught.value.errno==errno.EROFS
        with pytest.raises(OSError) as caught:call.write('/elsewhere',b'x')
        assert caught.value.errno==errno.EROFS,'the root filesystem of the container is read-only'
        call.write('/out/made.json',b'{}');return 3,b'line\n'
    docker.on_run=behaviour
    argv=['run','--rm','-i','--pull','never','--init','--user','0:0','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
          '--mount','type=bind,source=%s,target=/in,readonly'%hostemu.DEPLOY,'--mount','type=bind,source=%s,target=/out'%hostemu.DATA,hostemu.BACKEND,'python','-I','-B','-','/out']
    assert docker.run(argv,b'script',{'DOCKER_CONFIG':'/etc/c3po-bar/docker-cli'})==(3,b'line\n')
    call=seen[0];assert (call.image,call.command,call.stdin,call.network,call.read_only_root,call.name)==(hostemu.BACKEND,['python','-I','-B','-','/out'],b'script','none',True,None)
    assert call.mounts==[{'source':hostemu.DEPLOY,'target':'/in','read_only':True},{'source':hostemu.DATA,'target':'/out','read_only':False}]
    assert call.environment=={'DOCKER_CONFIG':'/etc/c3po-bar/docker-cli'} and call.options['--user']==['0:0'] and call.options['--cap-drop']==['ALL']
    made=host.tree.get(hostemu.DATA+'/made.json');assert (made.uid,made.gid,made.mode,made.dev,bytes(made.content))==(0,0,0o600,hostemu.DATA_DEVICE,b'{}')
    assert ('container-write',hostemu.DATA+'/made.json',2) in host.log
    # the engine refuses before the container exists: an image that is not present under --pull never, a bind source that is absent
    assert docker.run(argv[:-6]+['sha256:'+'0'*64,'python'],b'x')==(125,b'') and docker.run(argv[:-6]+['c3po/backend:production','python'],b'x')==(125,b'')
    absent=list(argv);absent[16]='type=bind,source=/no/such/dir,target=/in,readonly';assert docker.run(absent,b'x')==(125,b'')
    for word in ('-d','--privileged','-v','--env'):
        with pytest.raises(AssertionError):docker.run(['run','--rm',word,hostemu.BACKEND,'x'],b'x')
    with pytest.raises(AssertionError):docker.run(['run','--pull','never',hostemu.BACKEND,'x'],b'x')          # a container that would stay

def test_compose_takes_nothing_implicit_merges_overrides_and_recreates_one_service():
    host=hostemu.world();docker=host.docker;base=['compose','--project-name',hostemu.PROJECT,'--env-file',hostemu.ENV_FILE,'-f',hostemu.COMPOSE_FILE]
    code,out=docker.run(base+['config','--format','json'],None,{'C3PO_BUILD_SHA':hostemu.REVISION});plain=json.loads(out)
    assert code==0 and set(plain['services'])==set(hostemu.SERVICES) and plain['services']['r2d2-worker']['environment']['C3PO_BUILD_SHA']==hostemu.REVISION
    assert json.loads(docker.run(base+['config','--format','json'])[1])['services']['r2d2-worker']['environment']['C3PO_BUILD_SHA']=='development'
    override=json.dumps({'services':{'r2d2-worker':{'environment':{'NEW_KEY':'v'}}}}).encode()
    merged=json.loads(docker.run(base+['-f','-','config','--format','json'],override,{'C3PO_BUILD_SHA':hostemu.REVISION})[1])
    assert merged['services']['r2d2-worker']['environment']=={**plain['services']['r2d2-worker']['environment'],'NEW_KEY':'v'}
    assert merged['services']['api']==plain['services']['api']
    for arguments in (['compose','config','--format','json'],['compose','--project-name',hostemu.PROJECT,'config'],['compose','-f',hostemu.COMPOSE_FILE,'config','--format','json']):
        with pytest.raises(AssertionError):docker.run(arguments)
    assert docker.run(base+['-f','/no/such/file.json','config','--format','json'])[0]==14
    assert docker.run(base+['-f','-','config','--format','json'],b'not json')[0]==15
    host.tree.add('/mnt/day-d-data/override.json',kind='file',content=override,dev=hostemu.DATA_DEVICE)
    before=dict((item['Name'],item['Id']) for item in docker.containers);files=base+['-f','/mnt/day-d-data/override.json']
    assert docker.run(files+['up','-d','--no-deps','--no-build','--pull','never','--force-recreate','r2d2-worker'],None,{'C3PO_BUILD_SHA':hostemu.REVISION})==(0,b'')
    after=dict((item['Name'],item['Id']) for item in docker.containers)
    assert [name for name in before if before[name]!=after[name]]==['/'+hostemu.WORKER] and len(after)==8
    worker=docker.container(hostemu.WORKER);assert 'NEW_KEY=v' in worker['Config']['Env'] and worker['RestartCount']==0 and worker['State']['Running']
    assert ('compose-recreate',hostemu.WORKER) in host.log
    for tail in (['up','-d','r2d2-worker'],['up','-d','--no-deps','--no-build','--pull','never','--force-recreate'],['down'],['restart','r2d2-worker']):
        with pytest.raises(AssertionError):docker.run(files+tail)

def test_flock_emulation_refuses_while_another_process_holds_the_lock_and_never_blocks():
    host=hostemu.world();path=hostemu.LOCK_DIRECTORY+'/'+hostemu.LOCK_NAME;import os
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|hostemu.NOATIME;fd=host.open('/',flags)
    for part in hostemu.LOCK_DIRECTORY.strip('/').split('/'):fd=host.open(part,flags,dir_fd=fd)
    lock=host.open(hostemu.LOCK_NAME,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
    host.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);assert host.lock_held(path)=='EX';host.flock(lock,fcntl.LOCK_UN);assert host.lock_held(path) is None
    host.lock_holder[path]='EX'
    for operation in (fcntl.LOCK_EX|fcntl.LOCK_NB,fcntl.LOCK_SH|fcntl.LOCK_NB):
        with pytest.raises(BlockingIOError) as caught:host.flock(lock,operation)
        assert caught.value.errno==errno.EWOULDBLOCK
    host.lock_holder[path]='SH';host.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB);assert host.lock_held(path)=='SH';host.flock(lock,fcntl.LOCK_UN)
    with pytest.raises(BlockingIOError):host.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with pytest.raises(AssertionError):host.flock(lock,fcntl.LOCK_EX)                     # a blocking request would park the run
    host.lock_released_after=2
    with pytest.raises(BlockingIOError):host.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with pytest.raises(BlockingIOError):host.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    host.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);assert host.lock_held(path)=='EX';host.close(lock);assert host.lock_held(path) is None

def test_world_is_the_baseline_of_the_epoch_and_carries_no_number_of_the_real_host():
    host=hostemu.world();tree=host.tree
    assert [tree.get(path) for path in ('/etc/c3po-bar','/var/lib/c3po-bar','/etc/c3po-reader','/var/lib/c3po-reader','/etc/systemd/system/c3po-massive.service')]==[None]*5
    assert tree.get(hostemu.PIN).kind=='file' and tree.get(hostemu.DATA).dev==hostemu.DATA_DEVICE!=tree.get('/var/lib').dev==hostemu.ROOT_DEVICE
    assert (tree.get(hostemu.DEPLOY).uid,tree.get(hostemu.ENV_FILE).mode,tree.get(hostemu.LOCK_DIRECTORY+'/'+hostemu.LOCK_NAME).uid)==(1000,0o600,1000)
    assert host.docker.info['ServerVersion']=='29.5.3' and host.docker.info['DriverStatus']==[['driver-type','io.containerd.snapshotter.v1']] and b'systemd 255' in host.systemd_version
    assert len(host.docker.containers)==8 and host.docker.container(hostemu.WORKER)['Config']['Labels']['com.docker.compose.service']=='r2d2-worker'
    hostemu.provision_supervisor(host)
    for path in ('/etc/c3po-bar/docker-cli','/var/lib/c3po-bar/journal','/var/lib/c3po-bar/supervisor'):
        node=tree.get(path);assert (node.kind,node.uid,node.gid,node.mode,node.dev,node.children)==('dir',0,0,0o700,hostemu.ROOT_DEVICE,{})
    assert hostemu.rows(host,'/var/lib/c3po-bar/journal')[-1]=={'path':'/var/lib/c3po-bar/journal','device':hostemu.ROOT_DEVICE,'inode':tree.get('/var/lib/c3po-bar/journal').ino,'uid':0,'gid':0,'mode':0o700}
