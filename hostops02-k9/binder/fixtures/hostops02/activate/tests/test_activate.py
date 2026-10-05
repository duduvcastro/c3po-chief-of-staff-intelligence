"""K6a end to end on the emulated host: what the signers see, the order of everything that changes the host, the exact
argv of every command, and what the receipt of a complete run says."""
import json

import family as f
import hostemu
import k6a

GO16=lambda docs:docs.go16()

def test_complete_run_and_the_literal_effects_the_signers_see():
    m,docs,host=k6a.fresh();plan=docs.plan;values=k6a.environment();before=k6a.worker(host)['Id']
    assert docs.go['effects']=={'operation':'GO_WRITE_HOSTOPS02_ACTIVATE_01','epoch':'R2D2-V2-SHADOW-2026-10-05','revision':hostemu.REVISION,'data_root':hostemu.DATA,
        'live_parent':{'path':k6a.LIVE_PARENT,'row':plan['live_parent'][-1],'chain_sha256':f.sha(f.canonical(plan['live_parent'])),'mount_point_by_device_change':hostemu.DATA},
        'directory':{'path':k6a.LIVE,'mode_octal':'0700','expect':'ABSENT'},
        'files':[{'key':'POLICY','path':k6a.LIVE+'/policy.json','sha256':f.sha(k6a.POLICY),'bytes':len(k6a.POLICY),'mode_octal':'0600'},
                 {'key':'OVERRIDE','path':k6a.LIVE+'/compose.override.json','sha256':f.sha(k6a.override()),'bytes':len(k6a.override()),'mode_octal':'0600'}],
        'policy':{'content_digest_sha256':f.sha(f.canonical(k6a.policy_object())),'valid_from':'2026-10-05T00:00:00+00:00','valid_until':'2026-10-10T00:00:00+00:00',
                  'capacity':550,'release_sha':f.sha(k6a.RELEASE)},
        'release':{'parent':{'path':hostemu.DATA,'row':plan['release']['parent'][-1],'chain_sha256':f.sha(f.canonical(plan['release']['parent'])),
                             'mount_point_by_device_change':hostemu.DATA},
                   'path':k6a.RELEASE_DIRECTORY+'/'+k6a.RELEASE_NAME,'sha256':f.sha(k6a.RELEASE),'bytes':len(k6a.RELEASE),
                   'expect':'INSTALLED_BY_AN_EARLIER_OPERATION_READ_AND_COMPARED_NEVER_WRITTEN'},
        'recreate':{'project':'c3po','env_file':hostemu.ENV_FILE,'files':[hostemu.COMPOSE_FILE,k6a.LIVE+'/compose.override.json'],'service':'r2d2-worker',
                    'container':hostemu.WORKER,'image_id':hostemu.BACKEND,'build_sha':hostemu.REVISION,'environment':values,
                    'worker_mount':{'source':hostemu.DATA,'target':'/app/day-d-data'},'lock':k6a.LOCK,'lock_wait_seconds':20,
                    'lock_chain_sha256':f.sha(f.canonical(plan['lock']['directory'])),
                    'deploy_directory':{'path':hostemu.DEPLOY,'row':plan['deploy_directory'][-1],'chain_sha256':f.sha(f.canonical(plan['deploy_directory'])),
                                        'mount_point_by_device_change':'/'}},
        'required':{'maintenance_pin':hostemu.PIN,'reboot_pending_marker_absent':k6a.PENDING,'deploy_version':hostemu.REVISION},
        'evidence_boot_id_sha256':f.BOOT_SHA,'pre_existing_objects_modified':'THE_WORKER_CONTAINER_IS_REPLACED','activation':False}
    assert docs.go['success_criterion']==m.success_of(plan)=='ACTIVATE_WORKER_RECREATED_AND_VERIFIED' and docs.go['scope_statement']==m.SCOPE_STATEMENT
    assert values=={'C3PO_R2D2_V2_LIVE_POLICY_FILE':'/app/day-d-data/r2d2-v2-live/2026-10-05/policy.json','C3PO_R2D2_V2_LIVE_POLICY_SHA':f.sha(k6a.POLICY),
                    'C3PO_R2D2_V2_SHADOW_RELEASE_FILE':'/app/day-d-data/r2d2-v2-release-20261005/release.CERTIFIED.json','C3PO_R2D2_V2_SHADOW_RELEASE_SHA':f.sha(k6a.RELEASE)}
    receipt=docs.run(host)
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==(m.COMPLETE_STATUS,'ACTIVATE_WORKER_RECREATED_AND_VERIFIED',None,'EFFECTS')
    assert receipt['mutating_calls']=={'issued':10,'succeeded':10,'failed_nothing_changed':0,'uncertain':0} and receipt['objects_left_by_this_run']==3
    assert receipt['commands_started']=={'READ':12,'CONTAINER':0,'EFFECT':1}
    assert receipt['worker_container_replaced'] is True and receipt['pre_existing_objects_modified'] is True
    assert receipt['activation_performed'] is False and receipt['daemon_reload_performed'] is False,'no systemd unit is switched by this operation'
    run=receipt['recreate']
    assert (run['state'],run['started'],run['returned'],run['returncode'],run['code'],run['unavailable'],run['milliseconds'])==('RECREATED_VERIFIED',True,True,0,None,{},0)
    assert sorted(run)==['code','facts','milliseconds','replaced','returncode','returned','started','state','unavailable']
    assert run['facts']=={'worker_listed_once':True,'worker_is_new':True,'old_container_gone':True,'running':True,'restarts':0,'image_is_the_signed_one':True,
        'environment_as_signed':True,'others_unchanged':True,'others_states_unchanged':True,'others_appeared':0,'others_gone':0,'others_same_name_new_id':0,
        'service_leftovers':0,'env_file_unchanged':True,'compose_file_unchanged':True,'release_unchanged':True,'files_as_delivered':True,
        'directory_entries':2,'lock_still_named':True,'settle_pause_taken':True,'second_check_passed':True,'milliseconds_between_checks':0,
        'worker_status':{'present':False,'status':None,'readiness':None}}
    assert list(run['facts'])==list(m.AFTER_FACTS),'every fact is named before anything is read'
    precheck=receipt['precheck'];assert sorted(precheck)==['containers_listed','deploy_version_is_the_revision','directory','free_bytes','free_inodes','lock_attempts',
        'maintenance_pin_present','reboot_pending','release_installed_as_signed','render','worker']
    assert (precheck['containers_listed'],precheck['free_bytes'],precheck['free_inodes'],precheck['reboot_pending'])==(8,hostemu.DATA_VFS['f_bavail']*4096,None,False)
    assert receipt['precheck']['worker']['id']==before and k6a.worker(host)['Id']!=before
    assert [row['state'] for row in receipt['directories']]==['CREATED_DURABLE'] and [row['state'] for row in receipt['ledger']]==['INSTALLED_DURABLE']*2
    assert [row['sha256_observed'] for row in receipt['ledger']]==[f.sha(k6a.POLICY),f.sha(k6a.override())]
    assert sorted(receipt['chains'])==['DEPLOY_DIRECTORY','LIVE_PARENT','LOCK_DIRECTORY','RELEASE_PARENT'] and receipt['chains']['LIVE_PARENT']==plan['live_parent']
    assert host.lock_held(k6a.LOCK) is None and host.fds=={} and host.locks=={},'the lock is released and every descriptor closed'

def test_what_is_on_the_host_afterwards_is_exactly_the_signed_bytes_and_one_new_container():
    m,docs,host=k6a.fresh();others={item['Name']:item['Id'] for item in host.docker.containers if item['Name']!='/'+hostemu.WORKER};tree=host.tree
    env=bytes(tree.get(hostemu.ENV_FILE).content);release=tree.get(k6a.RELEASE_DIRECTORY+'/'+k6a.RELEASE_NAME);inode=release.ino
    receipt=docs.run(host);assert receipt['status']==m.COMPLETE_STATUS
    live=tree.get(k6a.LIVE);assert (live.kind,live.uid,live.gid,live.mode,live.dev)==('dir',0,0,0o700,hostemu.DATA_DEVICE) and sorted(live.children)==['compose.override.json','policy.json']
    for name,raw in (('policy.json',k6a.POLICY),('compose.override.json',k6a.override())):
        node=live.children[name];assert (node.kind,node.uid,node.gid,node.mode,node.nlink,bytes(node.content))==('file',0,0,0o600,1,raw)
    assert json.loads(k6a.override())=={'services':{'r2d2-worker':{'environment':k6a.environment()}}}
    assert k6a.override().startswith(b'{"services": {"r2d2-worker": {"environment": {"C3PO_R2D2_V2_LIVE_POLICY_FILE": "/app/'),'the token shape of the override of 2026-09-28'
    new=k6a.worker(host);values=dict(item.split('=',1) for item in new['Config']['Env'])
    assert {key:values[key] for key in k6a.KEYS}==k6a.environment() and values['C3PO_BUILD_SHA']==hostemu.REVISION and new['Image']==hostemu.BACKEND
    assert {item['Name']:item['Id'] for item in host.docker.containers if item['Name']!='/'+hostemu.WORKER}==others and len(host.docker.containers)==8
    assert bytes(tree.get(hostemu.ENV_FILE).content)==env and (release.ino,bytes(release.content))==(inode,k6a.RELEASE),'the environment file and the release are read, never written'

def test_order_of_everything_that_changes_the_host_and_the_lock_around_it():
    m,docs,host=k6a.fresh();docs.run(host)
    order=[entry[0] if type(entry) is tuple else ' '.join(entry['argv'][1:3]) for entry in host.mutating()]
    assert order==['mkdir','create','write','link','unlink','create','write','link','unlink','compose-recreate','compose --project-name']
    names=[entry[0] for entry in host.log];first_lock=names.index('flock');last_lock=len(names)-1-names[::-1].index('flock')
    assert first_lock<names.index('mkdir') and last_lock>names.index('compose-recreate'),'the lock is taken before the first creation and released after the recreate'
    after=[entry for entry in host.log[names.index('compose-recreate'):last_lock] if entry[0]=='run'];assert len(after)==4,'every docker readback happens while the lock is held'
    assert [entry[1] for entry in host.log if entry[0]=='umask']==[0o077] and [entry[1] for entry in host.log if entry[0]=='pause']==[3],'one umask, one fixed pause'
    go16=docs.go16();created=[entry[1] for entry in host.log if entry[0]=='create']
    assert created==[k6a.LIVE+'/.hostops-%s-0.partial'%go16,k6a.LIVE+'/.hostops-%s-1.partial'%go16]
    # nothing is read after the lock is asked for that was not also read before it, except what only makes sense under it
    paths=[entry[1] for entry in host.log[:first_lock] if entry[0] in ('open','lstat')]
    for needed in (k6a.LIVE_PARENT,k6a.RELEASE_DIRECTORY+'/'+k6a.RELEASE_NAME,hostemu.ENV_FILE,hostemu.COMPOSE_FILE,hostemu.DEPLOY+'/.deploy-version',k6a.LOCK,hostemu.PIN):assert needed in paths,needed
    # the compose file is read before the first render is made from it, and nothing but the four signed files is ever opened for its bytes
    first_render=[index for index,entry in enumerate(host.log) if entry[0]=='run' and 'config' in entry[1]][0]
    assert [entry for entry in host.log[:first_render] if entry[0]=='read' and entry[1]==hostemu.COMPOSE_FILE]
    assert {entry[1] for entry in host.log if entry[0]=='read'}=={'/proc/sys/kernel/random/boot_id',k6a.RELEASE_DIRECTORY+'/'+k6a.RELEASE_NAME,hostemu.DEPLOY+'/.deploy-version',
        hostemu.ENV_FILE,hostemu.COMPOSE_FILE,k6a.LIVE+'/policy.json',k6a.LIVE+'/compose.override.json'}
    # free space is asked of the live parent, under the lock, before the first creation
    asked=[index for index,entry in enumerate(names) if entry=='fstatvfs'];assert asked and first_lock<asked[0]<asked[-1]<names.index('mkdir')
    assert {host.log[index][1] for index in asked}=={k6a.LIVE_PARENT}

def test_exact_argv_standard_input_and_variables_of_every_command():
    m,docs,host=k6a.fresh();old=k6a.worker(host)['Id'];docs.run(host);new=k6a.worker(host)['Id'];docker='/usr/bin/docker'
    base=['--project-name','c3po','--env-file',hostemu.ENV_FILE,'-f',hostemu.COMPOSE_FILE];override=k6a.LIVE+'/compose.override.json'
    signed=dict(k6a.environment(),C3PO_BUILD_SHA=hostemu.REVISION);template=m.environment_format(signed)
    rows=[(entry['argv'],entry['stdin'],entry['variables'],entry['seconds'],entry['capture']) for entry in host.commands]
    build={'C3PO_BUILD_SHA':hostemu.REVISION}
    assert rows==[
        ([docker,'container','inspect','--format',m.CONTAINER_FORMAT,hostemu.WORKER],None,{},8,True),
        ([docker,'image','inspect','--format',m.IMAGE_FORMAT,hostemu.BACKEND],None,{},8,True),
        ([docker,'container','inspect','--format',template,old],None,{},8,True),
        ([docker,'compose']+base+['-f','-','config','--format','json'],k6a.override(),build,15,True),
        ([docker,'image','inspect','--format',m.IMAGE_FORMAT,'c3po/backend:production'],None,{},8,True),
        ([docker,'container','inspect','--format',m.CONTAINER_FORMAT,hostemu.WORKER],None,{},8,True),
        ([docker,'ps','-a','--no-trunc','--format',m.PS_FORMAT],None,{},8,True),
        ([docker,'compose']+base+['-f',override,'config','--format','json'],None,build,15,True),
        # the recreate of 2026-09-28, word for word (worker-live-control.bound.py lines 223, 303, 323), output not captured
        ([docker,'compose','--project-name','c3po','--env-file',hostemu.ENV_FILE,'-f',hostemu.COMPOSE_FILE,'-f',override,
          'up','-d','--no-deps','--no-build','--pull','never','--force-recreate','r2d2-worker'],None,build,30,False),
        ([docker,'container','inspect','--format',m.CONTAINER_FORMAT,hostemu.WORKER],None,{},8,True),
        ([docker,'container','inspect','--format',template,new],None,{},8,True),
        ([docker,'ps','-a','--no-trunc','--format',m.PS_FORMAT],None,{},8,True),
        ([docker,'container','inspect','--format',m.CONTAINER_FORMAT,new],None,{},8,True)]
    assert all(entry['docker_config'] is None for entry in host.commands) and len(host.effect_commands())==1
    assert not [entry for entry in host.commands if 'exec' in entry['argv'] or 'run' in entry['argv'][1:2]],'no docker exec, no container run'
    text=json.dumps([entry['argv'] for entry in host.commands]);assert hostemu.SECRET not in text and 'never-emit' not in text,'no value of an environment in any argv'
    assert sorted(m.COMMANDS)==['container','container_environment','container_list','image','recreate','render','render_files']

def test_receipt_never_carries_a_value_of_the_environment_file_and_fits_the_limit():
    def busy(host):host.lock_holder[k6a.LOCK]='EX'
    def failing(host):host.docker.compose.up_returncode=1
    def hanging(host):host.hang_after.add(('compose','up'))
    for prepare in (lambda host:None,busy,failing,hanging):
        m,docs,host=k6a.fresh();prepare(host);receipt=docs.run(host);line=f.line(receipt)
        assert hostemu.SECRET.encode() not in line and b'never-emit' not in line and len(line)<=m.RECEIPT_LIMIT and f.sealed(receipt)
        assert receipt['secret_bytes_in_receipt'] is False and k6a.POLICY not in line and k6a.b64(k6a.POLICY).encode() not in line,'the bytes delivered are named by hash, not carried'
        env=bytes(host.tree.get(hostemu.ENV_FILE).content)
        assert f.sha(env).encode() not in line and ('"bytes":%d'%len(env)).encode() not in line.replace(b' ',b''),'no digest and no size of the environment file'
        assert f.sha(bytes(host.tree.get(hostemu.COMPOSE_FILE).content)).encode() not in line,'and none of the compose file'

def test_scope_statement_says_what_the_code_guarantees_about_values_and_names_the_ones_it_does_carry():
    """The owner signs this sentence in every GO. The four signed values and the build revision do travel: into the
    override, into the effects and the receipt, and into the argv of the docker template that compares them."""
    m,docs,host=k6a.fresh();statement=m.SCOPE_STATEMENT;receipt=docs.run(host)
    assert 'No value of any environment' not in statement
    assert statement.endswith('No docker exec, no shell, no systemctl, no pull. No value read from a container, from the render or from the environment file is printed, '
                              'stored or put in an argv. The four signed values are written to the override and shown in the effects; with the build revision they '
                              'are compared inside a docker template, in whose argv they travel.')
    values=k6a.environment();template=[entry['argv'][4] for entry in host.commands if k6a.is_environment(entry['argv'][1:])]
    assert len(template)==2 and all(value in text for value in list(values.values())+[hostemu.REVISION] for text in template),'the five signed values travel in the argv of the template'
    assert all(value.encode() in bytes(host.tree.get(k6a.OVERRIDE_FILE).content) for value in values.values()) and receipt['effects']['recreate']['environment']==values
    # what was READ (the environment of the containers, the render, the environment file) is in no argv and in no receipt
    words=json.dumps([entry['argv'] for entry in host.commands])+json.dumps(receipt)
    assert hostemu.SECRET not in words and 'never-emit' not in words and 'postgresql://' not in words
    assert m.SCOPE['statement']==statement and docs.go['scope_statement']==statement

def test_what_the_new_worker_writes_next_to_the_policy_is_tolerated_and_its_status_is_reported_not_judged():
    """The controller of the new worker writes its status and journal into the directory this run created. Whatever
    it says, and LIVE_EPOCH_NOT_FOUND is what it says while no epoch row exists, the run is judged on its own criteria."""
    def writes(status,extra=()):
        def after_up(compose,new):
            tree=compose.docker.host.tree
            tree.add(k6a.LIVE+'/policy.json.status.json',kind='file',dev=hostemu.DATA_DEVICE,mode=0o600,content=status)
            tree.add(k6a.LIVE+'/policy.json.live.2026-10-05.ndjson',kind='file',dev=hostemu.DATA_DEVICE,mode=0o600,content=b'{}\n')
            for name in extra:tree.add(k6a.LIVE+'/'+name,kind='file',dev=hostemu.DATA_DEVICE,mode=0o600,content=b'x')
        return after_up
    expected=f.canonical({'at':'2026-10-05T08:50:10+00:00','readiness':'BLOCKED','status':'LIVE_EPOCH_NOT_FOUND','subscription':{'symbols':['ZZSYMBOL','ZZOTHER']}})+b'\n'
    for raw,seen,entries in ((expected,{'present':True,'status':'LIVE_EPOCH_NOT_FOUND','readiness':'BLOCKED'},4),
                             (f.canonical({'status':'LIVE_POLICY_OR_RELEASE_MISSING','readiness':'BLOCKED'}),{'present':True,'status':'LIVE_POLICY_OR_RELEASE_MISSING','readiness':'BLOCKED'},4),
                             (f.canonical({'status':'lower case is not a code','readiness':7}),{'present':True,'status':None,'readiness':None},4),
                             (b'[1,2]',{'present':True,'status':None,'readiness':None},4),(b'not json',{'present':None,'status':None,'readiness':None},4),
                             (b'{"status":"X"}'+b' '*70000,{'present':None,'status':None,'readiness':None},4)):
        m,docs,host=k6a.fresh();host.docker.compose.after_up=writes(raw,());receipt=docs.run(host)
        assert (receipt['status'],receipt['code'])==(m.COMPLETE_STATUS,None),raw[:30]
        assert receipt['recreate']['facts']['worker_status']==seen and receipt['recreate']['facts']['directory_entries']==entries
        assert b'ZZSYMBOL' not in f.line(receipt),'nothing of the status file but its two codes'
    # a status name that is not a regular file is not followed and not read
    for kind in ('symlink','fifo','dir'):
        m,docs,host=k6a.fresh()
        def odd(compose,new,kind=kind):compose.docker.host.tree.add(k6a.LIVE+'/policy.json.status.json',kind=kind,dev=hostemu.DATA_DEVICE)
        host.docker.compose.after_up=odd;receipt=docs.run(host)
        assert receipt['status']==m.COMPLETE_STATUS and receipt['recreate']['facts']['worker_status']=={'present':None,'status':None,'readiness':None}
        assert not [entry for entry in host.log if entry[0]=='open' and entry[1]==k6a.LIVE+'/policy.json.status.json'],'what is not a regular file is not opened'

def test_another_container_that_only_changes_state_is_reported_and_does_not_decide():
    m,docs,host=k6a.fresh()
    def flips(compose,new):compose.docker.containers[0]['State'].update(Status='restarting')
    host.docker.compose.after_up=flips;receipt=docs.run(host);facts=receipt['recreate']['facts']
    assert receipt['status']==m.COMPLETE_STATUS and facts['others_unchanged'] is True and facts['others_states_unchanged'] is False

def test_timings_are_reported_and_a_clock_that_fails_never_breaks_a_run():
    m=k6a.load().m;ticks=iter([10.0,12.5]);read=m.stopwatch(lambda:next(ticks));assert read()==2500
    def broken():raise RuntimeError('clock')
    assert m.stopwatch(broken)() is None
    ticks=iter([1.0]);read=m.stopwatch(lambda:next(ticks));assert read() is None,'the clock failed at the second reading'
    # a path as compose may print it, in the one spelling the signed paths have
    assert [m.plain(value) for value in ('/mnt/day-d-data/','/mnt//day-d-data','/mnt/./day-d-data','/mnt/day-d-data')]==['/mnt/day-d-data']*4
    assert (m.plain('/mnt/day-d-data/..'),m.plain('//mnt/day-d-data'),m.plain('mnt/day-d-data'),m.plain(None),m.plain(7))==('/mnt/day-d-data/..','//mnt/day-d-data','mnt/day-d-data',None,7)

def test_source_constants_are_the_ones_of_the_release_and_of_the_precedent():
    m=k6a.load().m
    assert m.ACTIVATION_KEYS==('C3PO_R2D2_V2_LIVE_POLICY_FILE','C3PO_R2D2_V2_LIVE_POLICY_SHA','C3PO_R2D2_V2_SHADOW_RELEASE_FILE','C3PO_R2D2_V2_SHADOW_RELEASE_SHA')
    assert (m.EPOCH_NAME,m.EPOCH_REVISION,m.WORKER_SERVICE)==('R2D2-V2-SHADOW-2026-10-05','dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858','r2d2-worker')
    assert (m.WRITES_ALLOWED,m.ACTIVATION_ALLOWED,m.DATE_CLASS,m.DATES)==(True,False,'WRITE_FIRST_SESSION',('2026-10-05',))
    assert m.COMMANDS['recreate']['tail']==['up','-d','--no-deps','--no-build','--pull','never','--force-recreate','r2d2-worker'] and m.COMMANDS['recreate']['class']=='RECREATE'
    assert m.effects_budget('recreate')==34 and (m.SETTLE_SECONDS,m.FILES_ALLOWANCE_SECONDS,m.UNDER_LOCK_ALLOWANCE_SECONDS,m.RENDER_ALLOWANCE_FLOOR_SECONDS,m.SECOND_CHECK_RESERVE_SECONDS)==(3,1,2,3,2)
    assert m.BINARIES=={'docker':['/usr/bin/docker','/usr/local/bin/docker']},'root-owned system directories only'
    assert m.REBOOT_PENDING_PATH=='/run/c3po-security/reboot.pending' and m.PIN_NAME=='.r2d2-v2-pinned' and m.MAX_LOCK_WAIT_SECONDS==20
    assert (m.FREE_BYTES_FLOOR,m.FREE_INODES_FLOOR,m.MAX_COMPOSE_FILE_BYTES,m.COMPOSE_FILE_NAME)==(1048576,8,1048576,'compose.yml')
    assert m.SCOPE['limits']['free_bytes_floor']==1048576 and m.SCOPE['limits']['free_inodes_floor']==8 and m.SCOPE['limits']['compose_file_bytes']==1048576
    assert m.EVIDENCE_OPERATIONS==('GO_READONLY_HOSTOPS02_EPOCH_READBACK_01',) and m.SCOPE['evidence_operations_required']==['GO_READONLY_HOSTOPS02_EPOCH_READBACK_01']
    assert len(m.SUCCESS_CRITERIA)==9 and sorted(m.SCOPE['required_before_any_effect'])==['free_space','maintenance_pin_present','no_leftover_of_a_recreate',
        'reboot_pending_marker_absent','release','unchanged_since_the_first_look']
    assert [kind for kind in ('READ','CONTAINER','EFFECT') for row in m.COMMANDS.values() if row['kind']==kind]==['READ']*6+['EFFECT']
