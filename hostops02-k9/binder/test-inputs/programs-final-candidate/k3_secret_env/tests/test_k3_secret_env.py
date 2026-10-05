"""K3 (secret.env) on the emulated host: the complete run, every refusal before the creation (nothing changed, no
mutating call), every failure after it (the withdrawal by identity, or what is left and why), the worker and its one
entry, the signed plan, and the receipt (codes, booleans and identity rows only). On every path that reaches the host
the first call is the core's not_dumpable(); no value, line, content, digest or encoding of the secret, and no length
of the value, of the line or of the file, reaches a receipt, an argv, an environment or a log text, and the receipt does
not depend on the value or its length (HOC section 8, "NO SIZE ANYWHERE" and its canary test)."""
import errno
import json
import os

import pytest

import family as f
import hostemu
import k3env as e

M=e.m
CONFIG='/etc/c3po-reader'
TARGET='/etc/c3po-reader/secret.env'
TEMPLATE='{{range .Config.Env}}{{$p := split . "="}}{{if eq (index $p 0) "C3PO_DATABASE_URL"}}{{json .}}\n{{end}}{{end}}'

def run(prepare=None,hook=None,now=None,minutes=5,clock=None,fields=None,docs_hook=None,**world):
    """One run on a fresh emulated host. prepare(host) changes the host before the run (as it would be found);
    hook(host,name,detail,calls) acts during it. Returns (docs, host, snapshot before, receipt). Every run is scanned:
    no canary form in the receipt or in what the run handed to the outside, and in the two canary worlds no length."""
    k,host=e.world(**world)
    signed=dict(e.fields(host),**(fields or {}))         # what a binder copied from the receipts, before the host changed
    if prepare is not None:prepare(host)
    docs=f.Docs(k,signed,now=now or e.NOW,minutes=minutes)
    if docs_hook is not None:docs_hook(docs)
    before=e.state_of(host);host.hook=hook
    options={} if clock is None else {'clock':clock}
    receipt=docs.run(host,**options)
    assert f.sealed(receipt) and type(receipt) is dict
    assert e.leaks(e.line(receipt))==[] and e.leaks(e.outside_view(host))==[]
    value=world.get('value',e.VALUE)
    if value in (e.VALUE_A,e.VALUE_B):
        assert e.length_leaks(e.line(receipt),(value,))==[] and e.length_leaks(e.outside_view(host),(value,))==[]
        assert not set(e.integers(json.loads(e.line(receipt))))&e.lengths(value)
    first_of_all(host,receipt)
    return docs,host,before,receipt

def first_of_all(host,receipt):
    """On every path that reaches the host: the process is made non-dumpable by the first call of the run, once, before
    anything else."""
    names=[entry[0] for entry in host.log]
    if not names:
        assert receipt['phase_reached'] in ('AUTHENTICATION','BEFORE_ANY_EFFECT') and 'process' not in receipt;return
    assert names[0]=='not_dumpable' and names.count('not_dumpable')==1,names[:3]
    if 'process' in receipt:assert receipt['process']=={'dumpable_disabled':host.dumpable==0}
    else:assert receipt['phase_reached'] in ('ESCAPED','BEFORE_ANY_EFFECT')

def refused(receipt,code):
    m=M()
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('REFUSED',m.REFUSED_OUTCOME,code),(receipt['code'],code)
    assert receipt['mutating_calls']['succeeded']==0 and receipt['mutating_calls']['uncertain']==0
def partial(receipt,code):
    m=M();assert (receipt['status'],receipt['outcome'],receipt['code'])==('PARTIAL_METADATA_REQUIRES_REVIEW',m.PARTIAL_OUTCOME,code),(receipt['code'],code)
def nothing_changed(host,before):
    assert e.state_of(host)==before and [entry for entry in host.mutating() if entry[0]!='create']==[]
def once(action):
    """A hook that acts at the first call it matches (the action returns True or raises) and never again."""
    done=[False]
    def hook(host,name,detail,calls):
        if done[0]:return
        try:done[0]=bool(action(host,name,detail))
        except BaseException:
            done[0]=True;raise
    return hook
def failing(call,path,error):
    def act(host,name,detail):
        if name==call and detail[0]==path:raise error
        return False
    return act
def node(host):return e.node(host,TARGET)


# ---------------------------------------------------------------- the complete run
def test_complete_run_places_the_one_line_and_reads_it_back():
    m=M();docs,host,before,receipt=run()
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.COMPLETE_STATUS,'READER_SECRET_ENV_PLACED_AND_READ_BACK',None)
    made=node(host);assert (made.kind,made.uid,made.gid,made.mode,made.nlink,bytes(made.content))==('file',0,0,0o600,1,e.line_of()) and made.synced
    assert bytes(made.content)==b'C3PO_DATABASE_URL='+e.VALUE.encode()+b'\n' and bytes(made.content).count(b'\n')==1
    row=receipt['secret_env']
    assert row['state']=='PLACED_VERIFIED' and row['code'] is None and row['created'] is True and row['path']==TARGET
    for name in ('all_bytes_written','fsync_file','fsync_directory','regular','uid_0','gid_0','mode_0600','single_link','on_the_device_of_the_directory',
                 'readback_same_inode','readback_metadata_as_created','readback_exactly_one_line','readback_name_is_the_key','readback_equal_to_the_worker_entry'):
        assert row[name] is True,name
    assert (row['device'],row['inode'])==(made.dev,made.ino) and row['withdrawn'] is False and row['withdrawal_code'] is None
    assert sorted(row)==sorted(m.secret_row()) and not [name for name in row if 'size' in name or 'length' in name or 'sha' in name or 'digest' in name or 'block' in name]
    assert receipt['directory_readback'] is None and receipt['readback']=='COMPLETE' and receipt['existing_secret_env'] is None
    assert receipt['mutating_calls']=={'issued':2,'succeeded':2,'failed_nothing_changed':0,'uncertain':0} and receipt['objects_left_by_this_run']==1
    assert receipt['commands_started']=={'READ':6,'CONTAINER':0,'EFFECT':0} and receipt['precheck']=={'seconds_left_before_the_first_effect':60}
    assert receipt['worker']=={'one_container_with_the_name':True,'id_equal_signed':True,'no_other_running_container_of_the_service_name':True,'running':True,
                               'compose_project_and_service':True,'entry_present':True,'value_shape_met':True,'read_twice_equal':True,
                               'same_container_after_the_reads':True}
    assert row['directory_at_the_signed_path'] is None
    assert receipt['config_directory']=={'rows':e.fields(host)['config_chain'],'pinned':True,'entries_before':1,'secret_env_absent':True,'no_leftover_of_a_secret':True,
                                         'key_in_no_other_env_file':True}
    assert receipt['process']=={'dumpable_disabled':True} and host.dumpable==0 and host.log[0]==('not_dumpable',)
    assert receipt['pre_existing_objects_modified'] is False and receipt['activation_performed'] is False and receipt['secret_bytes_in_receipt'] is False
    assert [entry[0] for entry in host.mutating()]==['create','write']
    host.tree.remove(TARGET);assert e.state_of(host)==before

@pytest.mark.parametrize('launcher,pins',[(True,False),(True,True),(False,True)])
def test_the_directory_may_hold_what_other_operations_created(launcher,pins):
    docs,host,before,receipt=run(launcher=launcher,pins=pins)
    assert receipt['status']==M().COMPLETE_STATUS and receipt['config_directory']['entries_before']==1+launcher+pins
    assert bytes(e.node(host,CONFIG+'/docker-cli').content)==b'' and (not pins or bytes(e.node(host,CONFIG+'/pins.env').content).startswith(b'C3PO_BUILD_SHA='))

def test_the_docker_commands_are_the_list_two_inspects_of_metadata_and_two_of_the_fixed_secret_template():
    m=M();docs,host,before,receipt=run();worker=e.WORKER_ID
    argv=[entry['argv'][1:] for entry in host.commands]
    assert argv==[['ps','-a','--no-trunc','--format',m.PS_FORMAT],['container','inspect','--format',m.CONTAINER_FORMAT,worker],
                  ['container','inspect','--format',m.LABELS_FORMAT,worker],['container','inspect','--format',TEMPLATE,worker],['container','inspect','--format',TEMPLATE,worker],
                  ['ps','-a','--no-trunc','--format',m.PS_FORMAT]]
    assert all(entry['argv'][0]=='/usr/bin/docker' and entry['variables']=={} and entry['docker_config'] is None and entry['stdin'] is None
               and entry['seconds']==8 for entry in host.commands)
    # HOC section 8's narrowing for the one name, with the one argued deviation: {{json .}} and a literal newline for {{println .}}
    assert m.SECRET_ENVIRONMENT_NAMES==('C3PO_DATABASE_URL',) and m.COMMANDS[m.SECRET_ENVIRONMENT_ROW]['argv']==['container','inspect','--format',TEMPLATE]
    assert TEMPLATE.replace('{{json .}}\n','{{println .}}')=='{{range .Config.Env}}{{$p := split . "="}}{{if eq (index $p 0) "C3PO_DATABASE_URL"}}{{println .}}{{end}}{{end}}'
    assert 'Env' not in m.CONTAINER_FORMAT+m.PS_FORMAT+m.LABELS_FORMAT and sorted(m.COMMANDS)==['container','container_labels','container_list','container_secret_environment']
    assert all(row['kind']=='READ' and row['class']=='QUICK' and row['tool']=='docker' and not row['stdin'] for row in m.COMMANDS.values())
    # the engine printed exactly one entry line and its own newline, nothing else of the environment
    outputs=[host.docker.render(TEMPLATE,'container',host.docker.container(e.WORKER),True)]
    assert outputs==[(0,b'"C3PO_DATABASE_URL='+e.VALUE.encode()+b'"\n\n')]

def test_the_order_of_the_run_on_the_host():
    """not_dumpable, umask, boot, the directory walked and listed, the docker commands, the directory proved again, then
    the create, the write, fsync, fstat, fsync of the directory, the readback open and reads, the directory again."""
    m=M()
    class Reads(e.K3Host):
        def read(self,fd,size):
            self.sizes=getattr(self,'sizes',[])+[(self.path_of(fd),size)];return e.K3Host.read(self,fd,size)
    docs,host,before,receipt=run(lambda host:setattr(host,'__class__',Reads));names=[entry[0] for entry in host.log]
    assert names[:2]==['not_dumpable','umask'] and host.log[1]==('umask',0o077)
    assert [entry for entry in host.log if entry[0]=='open'][0][1]=='/'
    listing=names.index('names');runs=[index for index,name in enumerate(names) if name=='run'];create=names.index('create')
    assert listing<min(runs) and max(runs)<create
    assert [entry[1:] for entry in host.log if entry[0]=='create']==[(TARGET,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)]
    own=[entry[0] for entry in host.log if entry[1:2]==(TARGET,)]
    assert own==['create','write','fsync','fstat','open','fstat','read','read'],own
    assert [entry[1:] for entry in host.log if entry[0]=='open' and entry[1]==TARGET]==[(TARGET,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|hostemu.NOATIME)]
    assert [entry[1] for entry in host.log if entry[0]=='fsync']==[TARGET,CONFIG]
    # every read of the readback asks for the same constant: no argument of a call depends on the value's length
    assert [size for path,size in host.sizes if path==TARGET]==[m.READBACK_REQUEST]*2 and m.READBACK_REQUEST==len('C3PO_DATABASE_URL=')+4096+2
    for value in (e.VALUE_A,e.VALUE_B):
        docs,host,before,receipt=run(lambda host:setattr(host,'__class__',Reads),value=value)
        assert receipt['status']==m.COMPLETE_STATUS and [size for path,size in host.sizes if path==TARGET]==[m.READBACK_REQUEST]*2
    assert host.fds=={}

def test_every_buffer_that_held_the_value_is_zeroed_and_the_write_came_from_one():
    m=M();k,host=e.world();docs=f.Docs(k,e.fields(host),now=e.NOW);seen=[];zeroed=[];real=m.container_secret_environment;real_zero=m.zero
    def spy(*arguments,**options):
        values=real(*arguments,**options);seen.append(values);return values
    def zero(buffer):zeroed.append(buffer);real_zero(buffer)
    m.container_secret_environment=spy;m.zero=zero
    try:receipt=docs.run(host)
    finally:m.container_secret_environment=real;m.zero=real_zero
    assert receipt['status']==m.COMPLETE_STATUS and len(seen)==2 and len(host.written_from)==1
    for values in seen:assert sorted(values)==['C3PO_DATABASE_URL'] and all(type(value) is bytearray and value and set(value)=={0} for value in values.values())
    assert all(type(buffer) is bytearray and buffer and set(buffer)=={0} for buffer in host.written_from)
    # the two reads, the line, and the bytes read back: four bytearrays, each zeroed
    assert len(zeroed)==4 and all(type(buffer) is bytearray and buffer and set(buffer)=={0} for buffer in zeroed)
    # and on a refusal after the value was read: the budget
    k,host=e.world();docs=f.Docs(k,e.fields(host),now=e.NOW);seen.clear();m.container_secret_environment=spy
    budget=f.Budget(e.NOW).attach(host).cost(12,'container','inspect')
    try:receipt=docs.run(host,**budget.options())
    finally:m.container_secret_environment=real
    assert receipt['code']=='BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT' and len(seen)==2 and all(set(value)=={0} for values in seen for value in values.values())

def same(first,second,prepare=None,hook=None):
    """Two runs that differ only in the secret (the two canary worlds, or the given options): the same receipt bytes."""
    out=[]
    for options in (first,second):
        docs,host,before,receipt=run(prepare,hook() if hook else None,**options);out.append(e.line(receipt))
    assert out[0]==out[1];return json.loads(out[0])

A=dict(value=e.VALUE_A);B=dict(value=e.VALUE_B)
def test_the_receipt_does_not_depend_on_the_value_or_its_length():
    """Two runs that differ only in the secret (other value, other length, other first bytes): the receipts are the same
    bytes, whatever the outcome. So no value, digest, length or size of one can be in a receipt."""
    m=M()
    assert same(A,B)['status']==m.COMPLETE_STATUS and same({},A)['status']==m.COMPLETE_STATUS
    assert same(A,B,hook=lambda:once(failing('write',TARGET,OSError(errno.ENOSPC,'full'))))['secret_env']['state']=='WITHDRAWN'
    assert same(A,B,hook=lambda:once(failing('fsync',CONFIG,OSError(errno.EIO,'io'))))['secret_env']['state']=='WITHDRAWN'
    def tamper(host,name,detail):
        if name=='open' and detail[0]==TARGET and detail[1]&os.O_ACCMODE==os.O_RDONLY:host.tree.get(TARGET).content.extend(b'X');return True
        return False
    assert same(A,B,hook=lambda:once(tamper))['secret_env']['readback_equal_to_the_worker_entry'] is False
    for one,two in (('postgresql://a b','x'*5000),('','a"b'),('a\\b'*40,'\t'),('é'*30,'x\ny'),('x'*4097,' '*20)):
        assert same(dict(value=one),dict(value=two))['code']=='SECRET_VALUE_SHAPE',(one[:5],two[:5])
    assert same(dict(value=None),dict(value=None,extra_env=['C3PO_DATABASE_URLX='+e.VALUE_A]))['code']=='SECRET_ENTRY_ABSENT'
    assert same(dict(value='x'*70000),dict(value='x'*5000))['code']=='SECRET_VALUE_SHAPE' and same(dict(value='x'*70000),dict(value=' '))['worker']['entry_present'] is None
    assert same(dict(extra_env=['C3PO_DATABASE_URL='+e.VALUE_A]),dict(value=e.VALUE_B,extra_env=['C3PO_DATABASE_URL=x']))['code']=='SECRET_ENVIRONMENT_REPEATED'

@pytest.mark.parametrize('content',[b'',b'x',e.line_of(e.VALUE_A),e.line_of(e.VALUE_B),e.line_of(e.VALUE_B)+b'\n',b'y'*70000])
def test_a_secret_env_found_present_says_type_owner_mode_and_links_and_never_its_size(content):
    """HOC 8: a refusal with a pre-existing file holds type, uid, gid, mode and links only. Files of other sizes give
    the same receipt bytes."""
    def present(host):host.tree.add(TARGET,kind='file',uid=0,gid=0,mode=0o600,content=content)
    docs,host,before,receipt=run(present);refused(receipt,'SECRET_ENV_PRESENT');nothing_changed(host,before)
    assert receipt['existing_secret_env']=={'type':'file','uid':0,'gid':0,'mode_octal':'0600','links':1}
    assert receipt['config_directory']['secret_env_absent'] is False and receipt['worker']['one_container_with_the_name'] is None and host.commands==[]
    assert not [entry for entry in host.log if entry[0] in ('open','read') and entry[1]==TARGET]
    reference=run(lambda host:host.tree.add(TARGET,kind='file',uid=0,gid=0,mode=0o600,content=b'reference'))[3]
    assert e.line(receipt)==e.line(reference)
    for number in (len(content),len(content)-1,len(content)-len('C3PO_DATABASE_URL=')-1):
        if number>=1000:assert e.length_leaks(e.line(receipt))==[] and number not in set(e.integers(json.loads(e.line(receipt))))

def test_the_canary_worlds_leave_no_length_and_no_form_of_the_value_on_any_path():
    """HOC 8's canary test on the two worlds of unusual lengths: complete, refused with the file present, refused by the
    shape, changed between the reads, partial after a failed write, a withdrawal that fails, an expiry after the creation.
    run() scans the receipt and what was handed to the outside each time; here also the exception texts."""
    m=M()
    for world in (A,B):
        run(**world)
        run(lambda host,world=world:host.tree.add(TARGET,kind='file',uid=0,gid=0,mode=0o600,content=e.line_of(world['value'])),**world)
        run(hook=once(failing('write',TARGET,OSError(errno.ENOSPC,'full'))),**world)
        run(hook=lambda host,name,detail,calls:(_ for _ in ()).throw(OSError(errno.EBUSY,'busy')) if name=='unlink' or (name=='fsync' and detail[0]==TARGET) else None,**world)
        run(fields={'worker_container_id':'6f'*32},**world)
    for bad in ('a b'+e.VALUE_A,e.VALUE_A+'x'*1000,e.VALUE_A+'"'):
        docs,host,before,receipt=run(value=bad);refused(receipt,'SECRET_VALUE_SHAPE')
        assert e.length_leaks(e.line(receipt),(bad,))==[]
    # the exceptions of the parse and of this source carry constant codes only
    raw=b'"C3PO_DATABASE_URL='+e.VALUE_A.encode()+b'"\n"C3PO_DATABASE_URL='+e.VALUE_B.encode()+b'"\n\n'
    try:m.secret_entries(raw,m.SECRET_ENVIRONMENT_NAMES)
    except m.Refused as error:text=repr(error)+str(error)+repr(error.args)
    assert text and e.leaks(text)==[] and e.length_leaks(text)==[] and 'SECRET_ENVIRONMENT_REPEATED' in text


# ---------------------------------------------------------------- refusals before the creation: nothing changed
def add(path,**attributes):return lambda host:host.tree.add(path,**attributes)
def replace(path,**attributes):
    def act(host):host.tree.remove(path);host.tree.add(path,**attributes)
    return act
def set_node(path,**attributes):
    def act(host):
        item=host.tree.get(path)
        for key,value in attributes.items():setattr(item,key,value)
    return act
def worker_env(change):
    def act(host):
        env=host.docker.container(e.WORKER)['Config']['Env'];env[:]=change(list(env))
    return act
def value(text):return worker_env(lambda env:[item if not item.startswith('C3PO_DATABASE_URL=') else 'C3PO_DATABASE_URL='+text for item in env])
def labels(**changes):return lambda host:host.docker.container(e.WORKER)['Config']['Labels'].update(changes)
def replica(name,running=True):
    return lambda host:host.docker.containers.append(hostemu.container(name,hostemu.BACKEND,'c3po/backend:production',['C3PO_DATABASE_URL=x'],
                                                                         project='c3po',service='r2d2-worker',running=running))
def many(host):
    for index in range(64):host.tree.add(CONFIG+'/other-%02d'%index,kind='file',mode=0o600)

REFUSALS=[
    # the configuration directory
    ('secret_env_present',add(TARGET,kind='file',uid=0,gid=0,mode=0o600,content=b'C3PO_DATABASE_URL=old\n'),'SECRET_ENV_PRESENT'),
    ('secret_env_present_empty',add(TARGET,kind='file',uid=0,gid=0,mode=0o600),'SECRET_ENV_PRESENT'),
    ('secret_env_a_directory',add(TARGET,mode=0o700),'SECRET_ENV_PRESENT'),
    ('secret_env_a_link',add(TARGET,kind='symlink',mode=0o777,target='/etc/shadow'),'SECRET_ENV_PRESENT'),
    ('secret_env_a_fifo',add(TARGET,kind='fifo',mode=0o600),'SECRET_ENV_PRESENT'),
    ('temporary_of_the_file_writer_left',add(CONFIG+'/.hostops-0123456789abcdef-00.partial',kind='file',mode=0o600),'SECRET_ENV_LEFTOVER_PRESENT'),
    ('temporary_of_another_kind',add(CONFIG+'/.hostops-x',kind='file',mode=0o600),'SECRET_ENV_LEFTOVER_PRESENT'),
    ('secret_env_tmp_left',add(CONFIG+'/secret.env.tmp',kind='file',mode=0o600),'SECRET_ENV_LEFTOVER_PRESENT'),
    ('dot_secret_env_partial_left',add(CONFIG+'/.secret.env.partial',kind='file',mode=0o600),'SECRET_ENV_LEFTOVER_PRESENT'),
    ('too_many_entries',many,'ENTRY_LIMIT'),
    ('a_leftover_and_the_key_in_pins_env',lambda host:(add(CONFIG+'/secret.env.tmp',kind='file',mode=0o600)(host),add(CONFIG+'/pins.env',kind='file',mode=0o600,content=b'C3PO_DATABASE_URL=x\n')(host)),'SECRET_ENV_LEFTOVER_PRESENT'),
    ('secret_env_and_a_leftover',lambda host:(add(TARGET,kind='file',mode=0o600)(host),add(CONFIG+'/secret.env.tmp',kind='file',mode=0o600)(host)),'SECRET_ENV_PRESENT'),
    ('sixty_four_entries_and_a_leftover',lambda host:(many(host),host.tree.remove(CONFIG+'/other-63'),host.tree.remove(CONFIG+'/other-62'),add(CONFIG+'/.hostops-y',kind='file',mode=0o600)(host)),'SECRET_ENV_LEFTOVER_PRESENT'),
    ('config_directory_absent',lambda host:host.tree.remove(CONFIG+'/docker-cli') or host.tree.remove(CONFIG),'PARENT_MISSING'),
    ('config_directory_replaced',lambda host:replace(CONFIG,uid=0,gid=0,mode=0o700)(host),'PARENT_IDENTITY_MISMATCH'),
    ('config_directory_mode_changed',set_node(CONFIG,mode=0o755),'PARENT_IDENTITY_MISMATCH'),
    ('config_directory_owner_changed',set_node(CONFIG,uid=1000),'PARENT_IDENTITY_MISMATCH'),
    ('config_directory_a_link',lambda host:replace(CONFIG,kind='symlink',mode=0o777,target='/tmp')(host),'PARENT_SYMLINK_COMPONENT'),
    ('etc_changed',set_node('/etc',mode=0o775),'PARENT_IDENTITY_MISMATCH'),
    # the worker and its environment
    ('worker_absent',lambda host:host.docker.containers.remove(host.docker.container(e.WORKER)),'WORKER_CONTAINER_MISMATCH'),
    ('worker_recreated_by_the_activation',lambda host:host.docker.container(e.WORKER).update(Id='6f'*32),'WORKER_CONTAINER_MISMATCH'),
    ('worker_stopped',lambda host:host.docker.container(e.WORKER)['State'].update(Status='exited',Running=False),'WORKER_NOT_RUNNING'),
    ('worker_restarting',lambda host:host.docker.container(e.WORKER)['State'].update(Status='restarting'),'WORKER_NOT_RUNNING'),
    ('worker_running_flag_false',lambda host:host.docker.container(e.WORKER)['State'].update(Running=False),'WORKER_NOT_RUNNING'),
    ('worker_paused_but_said_running',lambda host:host.docker.container(e.WORKER)['State'].update(Status='paused'),'WORKER_NOT_RUNNING'),
    ('a_second_replica_running',replica('c3po-r2d2-worker-2'),'WORKER_NOT_THE_ONLY_ONE'),
    ('a_compose_run_container_running',replica('c3po-r2d2-worker-run-0a1b2c3d4e5f'),'WORKER_NOT_THE_ONLY_ONE'),
    ('worker_of_another_project',labels(**{'com.docker.compose.project':'c3po-staging'}),'WORKER_NOT_THE_COMPOSE_SERVICE'),
    ('worker_of_another_service',labels(**{'com.docker.compose.service':'api'}),'WORKER_NOT_THE_COMPOSE_SERVICE'),
    ('worker_without_labels',lambda host:host.docker.container(e.WORKER)['Config'].update(Labels={}),'WORKER_NOT_THE_COMPOSE_SERVICE'),
    ('worker_list_fails',lambda host:setattr(host.docker,'ps_returncode',1),'COMMAND_FAILED'),
    ('worker_inspect_fails',lambda host:setattr(host.docker,'inspect_returncode',1),'COMMAND_FAILED'),
    ('docker_absent',lambda host:host.absent.add('docker'),'COMMAND_NOT_STARTED'),
    ('docker_hangs',lambda host:host.hang.add(('container','inspect')),'COMMAND_TIMEOUT'),
    ('docker_binary_not_root_owned',set_node('/usr/bin/docker',uid=1000),'BINARY_UNAVAILABLE_OR_UNSAFE'),
    ('entry_absent',worker_env(lambda env:[item for item in env if not item.startswith('C3PO_DATABASE_URL=')]),'SECRET_ENTRY_ABSENT'),
    ('entry_repeated',worker_env(lambda env:env+['C3PO_DATABASE_URL=OtHeRvAlUeFoRtEsTs']),'SECRET_ENVIRONMENT_REPEATED'),
    ('value_empty',value(''),'SECRET_VALUE_SHAPE'),
    ('value_with_a_space',value('postgresql://c3po:SpAcE iN@db:5432/c3po'),'SECRET_VALUE_SHAPE'),
    ('value_with_a_trailing_space',value(e.VALUE+' '),'SECRET_VALUE_SHAPE'),
    ('value_with_a_quote',value('postgresql://c3po:QuO"tE@db:5432/c3po'),'SECRET_VALUE_SHAPE'),
    ('value_with_a_backslash',value('postgresql://c3po:BaCk\\SlAsH@db:5432/c3po'),'SECRET_VALUE_SHAPE'),
    ('value_with_a_newline',value('postgresql://c3po:x\nC3PO_OTHER=y'),'SECRET_VALUE_SHAPE'),
    ('value_with_a_carriage_return',value('postgresql://c3po:x\r@db'),'SECRET_VALUE_SHAPE'),
    ('value_with_a_nul',value('postgresql://c3po:x\x00y@db'),'SECRET_VALUE_SHAPE'),
    ('value_with_a_tab',value('postgresql://c3po:x\ty@db'),'SECRET_VALUE_SHAPE'),
    ('value_not_ascii',value('postgresql://c3po:pé@db'),'SECRET_VALUE_SHAPE'),
    ('value_of_4097_bytes',value('x'*4097),'SECRET_VALUE_SHAPE'),
    ('value_over_the_output_limit',value('x'*70000),'SECRET_VALUE_SHAPE'),
    # the executor, the boot, the filesystem primitives
    ('executor_not_root',lambda host:setattr(host,'actor',(1000,1000)),'EXECUTOR_IDENTITY'),
    ('executor_group_not_root',lambda host:setattr(host,'actor',(0,1000)),'EXECUTOR_IDENTITY'),
    ('boot_of_another_evidence',lambda host:setattr(host.tree.get('/proc/sys/kernel/random/boot_id'),'content',bytearray(b'11111111-2222-3333-4444-555555555555\n')),'EVIDENCE_FROM_EARLIER_BOOT'),
    ('noatime_unavailable',lambda host:setattr(host,'noatime_available',False),'NOATIME_UNAVAILABLE'),
]
@pytest.mark.parametrize('name,prepare,code',REFUSALS,ids=[row[0] for row in REFUSALS])
def test_refusal_before_the_creation_changes_nothing(name,prepare,code):
    docs,host,before,receipt=run(prepare);refused(receipt,code);nothing_changed(host,before)
    assert receipt['phase_reached']=='PRECHECK' and receipt['mutating_calls']['issued']==0 and receipt['objects_left_by_this_run']==0
    assert receipt['secret_env']['state']=='NOT_ATTEMPTED' and receipt['secret_env']['created'] is False
    assert not [entry for entry in host.log if entry[0] in ('create','mkdir','write','unlink')]
    assert receipt['code'] in M().RECEIPT_CODES and receipt['process']=={'dumpable_disabled':True}
    assert (receipt['existing_secret_env'] is not None)==(code=='SECRET_ENV_PRESENT')

def test_a_refusal_says_what_was_found_up_to_it_and_nothing_after():
    docs,host,before,receipt=run(value('a b'))
    assert receipt['worker']['entry_present'] is None and receipt['worker']['value_shape_met'] is None and receipt['worker']['read_twice_equal'] is None
    assert receipt['worker']['compose_project_and_service'] is True and len(host.commands)==4
    docs,host,before,receipt=run(lambda host:host.docker.container(e.WORKER).update(Id='6f'*32))
    assert receipt['worker']['one_container_with_the_name'] is True and receipt['worker']['id_equal_signed'] is False and receipt['worker']['running'] is None
    assert [entry['argv'][1] for entry in host.commands]==['ps']
    docs,host,before,receipt=run(add(CONFIG+'/secret.env.tmp',kind='file',mode=0o600))
    assert receipt['config_directory']['secret_env_absent'] is True and receipt['config_directory']['no_leftover_of_a_secret'] is False and host.commands==[]
    docs,host,before,receipt=run(replica('c3po-r2d2-worker-2'))
    assert receipt['worker']['no_other_running_container_of_the_service_name'] is False and receipt['worker']['running'] is None and len(host.commands)==1
    docs,host,before,receipt=run(labels(**{'com.docker.compose.service':'api'}))
    assert receipt['worker']['compose_project_and_service'] is False and receipt['worker']['entry_present'] is None and len(host.commands)==3

def test_a_value_that_changes_or_disappears_between_the_two_reads_is_refused():
    def second_read(change):
        def hook(host,name,detail,calls):
            argv=detail[0] if name=='run' else None
            if argv and argv[-1]==e.WORKER_ID and argv[4]==TEMPLATE and [entry[1][4] for entry in host.log if entry[0]=='run' and len(entry[1])>4].count(TEMPLATE)==2:
                env=host.docker.container(e.WORKER)['Config']['Env'];env[:]=change(env)
        return hook
    for change in (lambda env:[item if not item.startswith('C3PO_DATABASE_URL=') else 'C3PO_DATABASE_URL=postgresql://c3po:ChAnGeD@db:5432/c3po' for item in env],
                   lambda env:[item for item in env if not item.startswith('C3PO_DATABASE_URL=')],
                   lambda env:[item if not item.startswith('C3PO_DATABASE_URL=') else item+'x' for item in env]):
        docs,host,before,receipt=run(hook=second_read(change));refused(receipt,'WORKER_ENVIRONMENT_CHANGED_DURING_READ');nothing_changed(host,before)
        assert receipt['worker']['read_twice_equal'] is False and receipt['worker']['value_shape_met'] is True
    # a change of another entry of the worker between the reads is not looked at (only the selected field: HOC 8)
    docs,host,before,receipt=run(hook=second_read(lambda env:env+['C3PO_OTHER=changed']));assert receipt['status']==M().COMPLETE_STATUS
    docs,host,before,receipt=run(hook=second_read(lambda env:env+['C3PO_DATABASE_URL=x']));refused(receipt,'SECRET_ENVIRONMENT_REPEATED')

ACCEPTED=[('value_of_exactly_4096_bytes',value('p'*4096)),('value_of_one_byte',value('x')),
          ('value_with_a_dollar_and_a_hash',value('postgresql://c3po:DoL$aR#hAsH@db:5432/c3po')),
          ('a_stopped_replica',replica('c3po-r2d2-worker-2',running=False)),
          ('another_container_running',lambda host:host.docker.containers.append(hostemu.container('stray',hostemu.BACKEND,'c3po/backend:production',[]))),
          ('another_entry_in_the_directory',add(CONFIG+'/activation.env',kind='file',mode=0o600)),
          ('a_lower_case_name_is_not_the_key',worker_env(lambda env:env+['c3po_database_url=x'])),
          ('another_name_that_begins_like_it',worker_env(lambda env:env+['C3PO_DATABASE_URL_OLD=y','OLD_C3PO_DATABASE_URL=z']))]
@pytest.mark.parametrize('name,prepare',ACCEPTED,ids=[row[0] for row in ACCEPTED])
def test_accepted_states_complete(name,prepare):
    docs,host,before,receipt=run(prepare);assert receipt['status']==M().COMPLETE_STATUS,receipt['code']
    found=bytes(node(host).content);assert found.count(b'\n')==1 and found.startswith(b'C3PO_DATABASE_URL=') and found.endswith(b'\n')

def test_the_line_holds_the_value_bytes_exactly_at_the_bounds():
    for text in ('x','p'*4096,'postgresql://c3po:DoL$aR#hAsH@db:5432/c3po'):
        docs,host,before,receipt=run(value(text));assert bytes(node(host).content)==b'C3PO_DATABASE_URL='+text.encode()+b'\n'

def test_a_process_that_cannot_be_made_non_dumpable_is_a_refusal_before_anything_is_looked_at():
    class Answers(e.K3Host):
        answer=False
        def not_dumpable(self):self.event('not_dumpable');return self.answer
    for prepare in ((lambda host:setattr(host,'dumpable_refused',True)),(lambda host:setattr(host,'__class__',Answers)),
                    (lambda host:(setattr(host,'__class__',Answers),setattr(host,'answer',1))),(lambda host:(setattr(host,'__class__',Answers),setattr(host,'answer',None)))):
        k,host=e.world();prepare(host);docs=f.Docs(k,e.fields(host),now=e.NOW);before=e.state_of(host)
        receipt=docs.run(host);refused(receipt,'PROCESS_DUMPABLE_NOT_DISABLED');nothing_changed(host,before)
        assert host.log==[('not_dumpable',)] and host.commands==[] and receipt['process']=={'dumpable_disabled':False}
        assert receipt['worker']['one_container_with_the_name'] is None and e.leaks(e.line(receipt))==[]
    for error,code in ((OSError(errno.EPERM,'x'),'PRECHECK_OS_ERROR'),(RuntimeError('x'),'PRECHECK_FAILED')):
        def hook(host,name,detail,calls,error=error):
            if name=='not_dumpable':raise error
        k,host=e.world();host.hook=hook;receipt=f.Docs(k,e.fields(host),now=e.NOW).run(host)
        refused(receipt,code);assert host.log==[('not_dumpable',)] and receipt['process']=={'dumpable_disabled':False}

def test_the_process_is_made_non_dumpable_first_on_every_path():
    for name,prepare,_ in REFUSALS:
        docs,host,before,receipt=run(prepare);assert host.log[0]==('not_dumpable',) and receipt['process']=={'dumpable_disabled':True},name

def test_the_budget_is_the_last_refusal_and_the_directory_is_proved_again_before_the_creation():
    m=M()
    for cost,left,status in ((11.5,14,'REFUSED'),(11.25,15,m.COMPLETE_STATUS),(12,12,'REFUSED')):
        k,host=e.world();docs=f.Docs(k,e.fields(host),now=e.NOW);budget=f.Budget(e.NOW).attach(host).cost(cost,'container','inspect')
        before=e.state_of(host);receipt=docs.run(host,**budget.options())
        assert receipt['status']==status and receipt['precheck']['seconds_left_before_the_first_effect']==left,(cost,receipt['code'])
        if status=='REFUSED':refused(receipt,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT');nothing_changed(host,before)
    # the directory replaced after the reads and before the creation
    def swap(host,name,detail,calls):
        if name=='run' and detail[0][-2:]==[TEMPLATE,e.WORKER_ID] and sum(1 for entry in host.log if entry[0]=='run')==5:
            replace(CONFIG,uid=0,gid=0,mode=0o700)(host)
    docs,host,before,receipt=run(hook=swap);refused(receipt,'PARENT_REPLACED');assert not [entry for entry in host.log if entry[0]=='create']
    assert receipt['phase_reached']=='PRECHECK' and receipt['secret_env']['state']=='NOT_ATTEMPTED'


# ---------------------------------------------------------------- after the creation: withdrawal, partial, uncertainty
def test_a_full_filesystem_at_the_create_is_a_refusal_with_nothing_changed():
    docs,host,before,receipt=run(hook=once(failing('create',TARGET,OSError(errno.ENOSPC,'full'))))
    refused(receipt,'FILESYSTEM_FULL');nothing_changed(host,before)
    assert receipt['secret_env']['state']=='NOT_CREATED' and receipt['phase_reached']=='EFFECTS' and receipt['objects_left_by_this_run']==0
    assert receipt['mutating_calls']=={'issued':1,'succeeded':0,'failed_nothing_changed':1,'uncertain':0}

def test_a_file_that_appears_after_the_precheck_is_not_touched_and_nothing_changed():
    def appear(host,name,detail):
        if name=='create':host.tree.add(TARGET,kind='file',mode=0o600,content=b'raced');return True
        return False
    docs,host,before,receipt=run(hook=once(appear));refused(receipt,'SECRET_ENV_APPEARED_AFTER_PRECHECK')
    row=receipt['secret_env'];assert row['state']=='NOT_CREATED' and row['errno']==errno.EEXIST and bytes(node(host).content)==b'raced'
    assert receipt['objects_left_by_this_run']==0 and not [entry for entry in host.log if entry[0] in ('write','unlink')]

@pytest.mark.parametrize('error,code',[(OSError(errno.ENOSPC,'full'),'FILESYSTEM_FULL'),(OSError(errno.EIO,'io'),'FILESYSTEM_ERROR'),
                                       (OSError(errno.EROFS,'ro'),'FILESYSTEM_READ_ONLY')])
def test_a_write_that_fails_withdraws_the_file(error,code):
    docs,host,before,receipt=run(hook=once(failing('write',TARGET,error)))
    partial(receipt,code);row=receipt['secret_env']
    assert row['state']=='WITHDRAWN' and row['withdrawn'] is True and row['code']==code and row['errno']==error.errno and row['fsync_directory_after_withdrawal'] is True
    assert row['all_bytes_written'] is False and node(host) is None and e.state_of(host)==before and receipt['objects_left_by_this_run']==0
    assert receipt['mutating_calls']=={'issued':3,'succeeded':2,'failed_nothing_changed':1,'uncertain':0}
    unlink=[i for i,entry in enumerate(host.log) if entry[0]=='unlink'];assert [host.log[i][1] for i in unlink]==[TARGET]
    assert host.log[unlink[0]+1]==('fsync',CONFIG)

@pytest.mark.parametrize('call,path,code',[('fsync',TARGET,'FSYNC_FAILED'),('fstat',TARGET,'SECRET_ENV_STAT_FAILED'),('fsync',CONFIG,'FSYNC_FAILED')])
def test_a_failed_fsync_or_fstat_after_the_write_withdraws(call,path,code):
    docs,host,before,receipt=run(hook=once(failing(call,path,OSError(errno.EIO,'io'))))
    partial(receipt,code);row=receipt['secret_env'];assert row['state']=='WITHDRAWN' and node(host) is None and row['all_bytes_written'] is True

def test_metadata_other_than_root_0600_with_one_link_is_withdrawn():
    for attribute,new in (('gid',5),('mode',0o640),('uid',1000),('nlink',2),('dev',999)):
        def change(host,name,detail,attribute=attribute,new=new):
            if name=='write' and detail[0]==TARGET:setattr(host.tree.get(TARGET),attribute,new);return True
            return False
        docs,host,before,receipt=run(hook=once(change));row=receipt['secret_env']
        partial(receipt,'SECRET_ENV_METADATA_MISMATCH')
        if attribute=='nlink':assert row['state']=='LEFT_UNVERIFIED' and row['withdrawal_code']=='SECRET_ENV_NAME_NOT_THIS_RUNS_FILE',attribute
        else:assert row['state']=='WITHDRAWN' and node(host) is None,attribute

def test_a_name_replaced_before_the_readback_is_left_and_another_object_is_never_removed_or_read():
    def swap(host,name,detail):
        if name=='fsync' and detail[0]==CONFIG:
            host.tree.remove(TARGET);host.tree.add(TARGET,kind='file',mode=0o600,uid=0,gid=0,content=b'someone else');return True
        return False
    docs,host,before,receipt=run(hook=once(swap));partial(receipt,'READBACK_MISMATCH');row=receipt['secret_env']
    assert row['readback_same_inode'] is False and row['readback_equal_to_the_worker_entry'] is None and row['state']=='LEFT_UNVERIFIED'
    assert row['withdrawal_code']=='SECRET_ENV_NAME_NOT_THIS_RUNS_FILE' and bytes(node(host).content)==b'someone else'
    assert not [entry for entry in host.log if entry[0] in ('unlink','read') and entry[1]==TARGET] and receipt['objects_left_by_this_run']==1

@pytest.mark.parametrize('change,facts',[
    (lambda content:content.extend(b'C3PO_OTHER=x\n'),('readback_exactly_one_line','readback_equal_to_the_worker_entry')),
    (lambda content:content.__setitem__(0,ord('X')),('readback_name_is_the_key','readback_equal_to_the_worker_entry')),
    (lambda content:content.__setitem__(len(content)-2,ord('Z')),('readback_equal_to_the_worker_entry',)),
    (lambda content:content.__setitem__(len(content)-1,ord('Z')),('readback_exactly_one_line','readback_equal_to_the_worker_entry')),
    (lambda content:content.extend(b'\n'),('readback_exactly_one_line','readback_equal_to_the_worker_entry')),
    (lambda content:content.extend(b'p'*5000),('readback_exactly_one_line','readback_equal_to_the_worker_entry')),
    (lambda content:content.__delitem__(slice(0,len(content))),('readback_exactly_one_line','readback_name_is_the_key','readback_equal_to_the_worker_entry'))])
def test_a_readback_that_finds_other_bytes_in_the_same_file_withdraws_it(change,facts):
    def tamper(host,name,detail):
        if name=='open' and detail[0]==TARGET:change(host.tree.get(TARGET).content);return True
        return False
    docs,host,before,receipt=run(hook=once(tamper));partial(receipt,'READBACK_MISMATCH');row=receipt['secret_env']
    assert row['readback_same_inode'] is True and row['readback_metadata_as_created'] is True and row['state']=='WITHDRAWN' and node(host) is None
    for name in ('readback_exactly_one_line','readback_name_is_the_key','readback_equal_to_the_worker_entry'):
        assert row[name] is (name not in facts),name

def test_a_readback_that_finds_other_metadata_withdraws_and_a_replaced_directory_stops_the_run():
    def chmod(host,name,detail):
        if name=='fsync' and detail[0]==CONFIG:host.tree.get(TARGET).mode=0o644;return True
        return False
    docs,host,before,receipt=run(hook=once(chmod));partial(receipt,'READBACK_MISMATCH');row=receipt['secret_env']
    assert row['readback_same_inode'] is True and row['readback_metadata_as_created'] is False and row['state']=='WITHDRAWN' and node(host) is None
    assert row['readback_equal_to_the_worker_entry'] is None and not [entry for entry in host.log if entry[0]=='read' and entry[1]==TARGET]
    def move(host,name,detail):
        if name=='fsync' and detail[0]==TARGET:
            old=host.tree.get(CONFIG);host.tree.remove(CONFIG);host.tree.add('/etc/moved',mode=0o700)
            host.tree.get('/etc').children['moved']=old;host.tree.add(CONFIG,uid=0,gid=0,mode=0o700);return True
        return False
    docs,host,before,receipt=run(hook=once(move));partial(receipt,'PARENT_REPLACED');row=receipt['secret_env']
    # the file is withdrawn through the held descriptor of the directory, wherever it now is, and the receipt says so
    assert (row['state'],row['withdrawn'],row['directory_at_the_signed_path'])==('WITHDRAWN',True,False) and e.node(host,'/etc/moved/secret.env') is None
    # (the emulator logs the unlink under the path the directory had when it was opened; the node gone is the moved one)
    assert len([entry for entry in host.log if entry[0]=='unlink'])==1 and node(host) is None and receipt['objects_left_by_this_run']==0

def test_a_readback_read_that_fails_withdraws():
    docs,host,before,receipt=run(hook=once(failing('read',TARGET,OSError(errno.EIO,'io'))))
    partial(receipt,'READBACK_UNAVAILABLE');assert receipt['secret_env']['state']=='WITHDRAWN' and node(host) is None
    docs,host,before,receipt=run(hook=once(lambda host,name,detail:(_ for _ in ()).throw(OSError(errno.EIO,'io')) if name=='open' and detail[0]==TARGET else False))
    partial(receipt,'READBACK_UNAVAILABLE');assert receipt['secret_env']['state']=='WITHDRAWN'

@pytest.mark.parametrize('refusal',['GO_EXPIRED','CLOCK_REVERSED'])
@pytest.mark.parametrize('stage',['create','fsync','read'])
def test_an_expiry_or_a_clock_reversal_after_the_creation_withdraws_the_file_although_the_gate_refuses(refusal,stage):
    """Review 2, point 1: after the create (an empty file), after the fsync (a complete file not read back) or during the
    readback, the gate refuses from then on; the file this run created is withdrawn anyway, by the held descriptor."""
    m=M();k,host=e.world();docs=f.Docs(k,e.fields(host),now=e.NOW);plan,real=docs.authenticate()
    def gate():
        if any(entry[0]==stage and entry[1]==TARGET for entry in host.log):raise m.Refused(refusal)
        return real()
    receipt=docs.perform(host,gate=gate)
    partial(receipt,refusal);row=receipt['secret_env']
    assert (row['state'],row['withdrawn'],row['withdrawal_code'],row['fsync_directory_after_withdrawal'],row['directory_at_the_signed_path'])==('WITHDRAWN',True,None,True,True)
    assert node(host) is None and [entry[1] for entry in host.log if entry[0]=='unlink']==[TARGET] and receipt['objects_left_by_this_run']==0
    assert row['all_bytes_written'] is (stage!='create')

def test_a_failure_of_another_kind_after_the_creation_withdraws_and_a_death_leaves_no_receipt():
    def boom(host,name,detail):
        if name=='write' and detail[0]==TARGET:raise RuntimeError('not an OSError')
        return False
    docs,host,before,receipt=run(hook=once(boom));partial(receipt,'SECRET_ENV_PLACEMENT_FAILED')
    row=receipt['secret_env'];assert row['state']=='WITHDRAWN' and receipt['mutating_calls']['uncertain']==1,'the write it interrupted is uncertain'
    k,host=e.world();docs=f.Docs(k,e.fields(host),now=e.NOW)
    def die(host,name,detail,calls):
        if name=='write':raise hostemu.Death()
    host.hook=die
    with pytest.raises(hostemu.Death):docs.perform(host)
    assert node(host) is not None and bytes(node(host).content)==b'' and e.leaks(e.outside_view(host))==[]

def test_an_unlink_that_fails_leaves_the_file_with_its_code():
    def hook(host,name,detail,calls):
        if name=='write' and detail[0]==TARGET:raise OSError(errno.ENOSPC,'full')
        if name=='unlink':raise OSError(errno.EBUSY,'busy')
    docs,host,before,receipt=run(hook=hook);partial(receipt,'FILESYSTEM_FULL');row=receipt['secret_env']
    assert row['state']=='LEFT_UNVERIFIED' and row['withdrawal_code']=='SECRET_ENV_WITHDRAWAL_FAILED' and row['withdrawal_errno']==errno.EBUSY
    assert receipt['objects_left_by_this_run']==1
    def uncertain(host,name,detail,calls):
        if name=='write' and detail[0]==TARGET:raise OSError(errno.ENOSPC,'full')
        if name=='unlink':raise RuntimeError('not an OSError')
    docs,host,before,receipt=run(hook=uncertain);row=receipt['secret_env']
    assert row['withdrawal_code']=='SECRET_ENV_WITHDRAWAL_UNCERTAIN' and receipt['mutating_calls']['uncertain']==1
    def unsynced(host,name,detail,calls):
        if name=='write' and detail[0]==TARGET:raise OSError(errno.ENOSPC,'full')
        if name=='fsync' and any(entry[0]=='unlink' for entry in host.log):raise OSError(errno.EIO,'io')
    docs,host,before,receipt=run(hook=unsynced);row=receipt['secret_env']
    assert (row['state'],row['withdrawn'],row['withdrawal_code'],row['fsync_directory_after_withdrawal'])==('WITHDRAWN_NOT_DURABLE',True,'FSYNC_FAILED',False)
    assert node(host) is None and receipt['objects_left_by_this_run']==0

def test_a_directory_readback_that_finds_another_entry_is_a_partial():
    def extra(host,name,detail):
        if name=='open' and detail[0]==TARGET:host.tree.add(CONFIG+'/stray',kind='file',mode=0o600);return True
        return False
    docs,host,before,receipt=run(hook=once(extra));partial(receipt,'DIRECTORY_READBACK_MISMATCH')
    assert receipt['directory_readback']=='READBACK_MISMATCH' and receipt['secret_env']['state']=='WITHDRAWN' and receipt['readback'] is None
    assert node(host) is None and e.node(host,CONFIG+'/stray') is not None and receipt['objects_left_by_this_run']==0
    def gone(host,name,detail,calls):
        if name=='names' and any(entry[0]=='create' for entry in host.log):raise OSError(errno.EIO,'io')
    docs,host,before,receipt=run(hook=gone);partial(receipt,'DIRECTORY_READBACK_MISMATCH');assert receipt['directory_readback']=='READBACK_UNAVAILABLE'
    assert receipt['secret_env']['state']=='WITHDRAWN' and node(host) is None

def test_the_directory_readback_proves_the_directory_again_from_the_root():
    """The directory replaced after the file was read back: the held descriptor still counts the old directory's two
    entries, and only the walk from "/" sees the replacement."""
    def swap(host,name,detail,calls):
        if name=='read' and detail[0]==TARGET and sum(1 for entry in host.log if entry[0]=='read' and entry[1]==TARGET)==2:
            old=host.tree.get(CONFIG);host.tree.remove(CONFIG);host.tree.add('/etc/moved',mode=0o700)
            host.tree.get('/etc').children['moved']=old;host.tree.add(CONFIG,uid=0,gid=0,mode=0o700)
    docs,host,before,receipt=run(hook=swap);partial(receipt,'DIRECTORY_READBACK_MISMATCH');row=receipt['secret_env']
    assert receipt['directory_readback']=='PARENT_REPLACED' and receipt['readback'] is None
    assert (row['state'],row['directory_at_the_signed_path'])==('WITHDRAWN',False) and e.node(host,'/etc/moved/secret.env') is None and node(host) is None

def test_a_code_shaped_text_raised_by_the_host_is_reported_as_unlisted():
    m=M()
    for call in ('lstat','write','unlink','names'):
        def hook(host,name,detail,calls,call=call):
            if name==call and (call=='names' or detail[0] in (TARGET,CONFIG)):
                raise m.Refused('FAKETOKENINCAPITALS')
            if call=='unlink' and name=='write' and detail[0]==TARGET:raise OSError(errno.ENOSPC,'full')
        docs,host,before,receipt=run(hook=hook)
        text=e.line(receipt).decode();assert 'FAKETOKENINCAPITALS' not in text,call
        # a refusal raised by the host's unlink is no refusal of the gate (the withdrawal is not gated): uncertain
        if call=='unlink':assert receipt['secret_env']['withdrawal_code']=='SECRET_ENV_WITHDRAWAL_UNCERTAIN'
        else:assert 'UNLISTED_CODE' in text,call

def test_short_writes_are_continued_and_a_write_of_nothing_withdraws():
    m=M()
    class Short(e.K3Host):
        def write(self,fd,data):return e.K3Host.write(self,fd,data[:5])
    docs,host,before,receipt=run(lambda host:setattr(host,'__class__',Short))
    assert receipt['status']==m.COMPLETE_STATUS and bytes(node(host).content)==e.line_of() and receipt['secret_env']['all_bytes_written'] is True
    class Nothing(e.K3Host):
        def write(self,fd,data):
            # a second write after one that wrote nothing means the run would loop: fail at once instead of hanging
            self.event('write',self.path_of(fd),0);self.nothing=getattr(self,'nothing',0)+1
            if self.nothing>1:raise AssertionError('a write of nothing was followed by another write')
            return 0
    docs,host,before,receipt=run(lambda host:setattr(host,'__class__',Nothing));partial(receipt,'SECRET_ENV_WRITE_INCOMPLETE')
    assert receipt['secret_env']['state']=='WITHDRAWN' and node(host) is None and receipt['secret_env']['all_bytes_written'] is False

def test_an_uncertain_creation_says_that_what_is_left_is_not_known():
    def boom(host,name,detail):
        if name=='create':raise RuntimeError('not an OSError')
        return False
    docs,host,before,receipt=run(hook=once(boom));partial(receipt,'SECRET_ENV_CREATE_UNCERTAIN')
    assert receipt['secret_env']['state']=='CREATE_UNCERTAIN' and receipt['objects_left_by_this_run'] is None and receipt['mutating_calls']['uncertain']==1


# ---------------------------------------------------------------- the plan, the effects, the evidence
def test_the_plan_is_refused_from_its_bytes_before_any_claim():
    k,host=e.world();good=e.fields(host)
    def code(**changes):
        docs=f.Docs(k,dict(good,**changes),now=e.NOW);return f.refusal(docs.authenticate)
    rows=good['config_chain']
    def changed(index,**values):
        out=json.loads(json.dumps(rows));out[index].update(values);return out
    assert [row['path'] for row in rows]==['/','/etc','/etc/c3po-reader'] and f.Docs(k,good,now=e.NOW).authenticate()
    assert code(config_chain=changed(-1,mode=0o755))=='CONFIG_DIRECTORY_NOT_ROOT_0700' and code(config_chain=changed(-1,mode=0o750))=='CONFIG_DIRECTORY_NOT_ROOT_0700'
    assert code(config_chain=changed(-1,gid=5))=='CONFIG_DIRECTORY_NOT_ROOT_0700' and code(config_chain=changed(-1,mode=0o2700))=='PARENT_SETGID'
    assert code(config_chain=changed(-1,mode=0o1700))=='CONFIG_DIRECTORY_NOT_ROOT_0700'
    for index in range(len(rows)):
        # no open root: every component root-owned and closed to group and other writes, whatever its depth
        assert code(config_chain=changed(index,uid=1000))=='CHAIN_ROW_UNSAFE',index
        assert code(config_chain=changed(index,mode=0o775))=='CHAIN_ROW_UNSAFE',index
        assert code(config_chain=changed(index,mode=0o1777))=='CHAIN_ROW_UNSAFE',index
    assert code(config_chain=rows[:-1])=='CHAIN_ROW_INVALID' and code(config_chain=hostemu.rows(host,'/etc'))=='CHAIN_ROW_INVALID'
    assert code(config_chain=None)=='CHAIN_ROW_INVALID' and code(config_chain=hostemu.rows(host,'/etc/c3po-reader/docker-cli'))=='CHAIN_ROW_INVALID'
    for wrong in (None,'5e'*31,'5E'*32,e.WORKER,7):assert code(worker_container_id=wrong)=='WORKER_CONTAINER_UNBOUND',wrong
    for wrong in (None,'0'*64,'x'):assert code(evidence_boot_id_sha256=wrong)=='EVIDENCE_BOOT_UNBOUND'
    assert f.Docs(k,dict(good,config_chain=changed(1,gid=7)),now=e.NOW).authenticate()      # /etc of another group, closed to it: accepted

def test_the_effects_the_signers_see():
    m=M();k,host=e.world();plan=dict(e.fields(host));effects=m.effects_of(plan)
    assert effects=={'operation':'GO_WRITE_HOSTOPS02_K3_SECRET_ENV_01',
                     'config_directory':dict(m.chain_effects(plan['config_chain']),required={'uid':0,'gid':0,'mode_octal':'0700','open_root':None,
                                                                                            'secret_env':'ABSENT','leftover_of_a_secret':'ABSENT'}),
                     'creates':{'path':'/etc/c3po-reader/secret.env','type':'regular file','uid':0,'gid':0,'mode_octal':'0600','links':1,
                                'content':'exactly one line C3PO_DATABASE_URL=<value> and a newline','temporary':None},
                     'value':{'name':'C3PO_DATABASE_URL','from_container':'c3po-r2d2-worker-1','container_id':e.WORKER_ID,
                              'compose_project':'c3po','compose_service':'r2d2-worker','reads':2},
                     'process':{'dumpable':0,'when':'first, before anything of the host is looked at'},'evidence_boot_id_sha256':f.BOOT_SHA,
                     'pre_existing_objects_modified':False,'activation':False,'value_in_receipt':False,'size_or_digest_in_receipt':False}
    docs=f.Docs(k,plan,now=e.NOW);docs.authority['effects']['creates']['path']='/elsewhere';docs.chain(effects=False)
    assert f.refusal(docs.authenticate)=='EFFECTS_BINDING'

def test_the_evidence_names_the_provisioning_and_the_epoch_readback():
    m=M();k,host=e.world()
    assert m.EVIDENCE_OPERATIONS==('GO_WRITE_SUPERVISOR_READER_PROVISION_01','GO_READONLY_HOSTOPS02_EPOCH_READBACK_01')
    for missing in m.EVIDENCE_OPERATIONS:
        evidence=[{'role':'R%d'%index,'operation':name,'receipt_sha256':'b'*64} for index,name in enumerate(m.EVIDENCE_OPERATIONS) if name!=missing]
        assert f.refusal(f.Docs(k,e.fields(host),now=e.NOW,evidence=evidence).authenticate)=='EVIDENCE_OPERATION_MISSING'

def test_the_date_class_covers_the_sunday_and_every_session_day():
    m=M();assert m.DATE_CLASS=='WRITE_EPOCH' and m.DATES==('2026-10-03','2026-10-04','2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09','2026-10-10')
    from datetime import datetime,timezone
    for when in (datetime(2026,10,4,22,30,tzinfo=timezone.utc),datetime(2026,10,5,1,0,tzinfo=timezone.utc),datetime(2026,10,9,23,0,tzinfo=timezone.utc)):
        docs,host,before,receipt=run(now=when);assert receipt['status']==m.COMPLETE_STATUS,when
    k,host=e.world();docs=f.Docs(k,e.fields(host),now=datetime(2026,10,11,1,0,tzinfo=timezone.utc))
    assert f.refusal(docs.authenticate)=='DATE_NOT_IN_SCOPE'

def test_the_secret_row_is_started_only_through_its_helper_and_its_answer_only_in_its_shape():
    m=M();k,host=e.world()
    c=m.Commands(host,lambda:60.0)
    for through in (None,'container_environment','effect'):
        assert f.refusal(lambda:c.output(m.SECRET_ENVIRONMENT_ROW,e.WORKER_ID,through=through))=='COMMAND_KIND'
    assert host.commands==[]
    render=host.docker.render
    for answer,code in ((b'"OTHER_NAME=x"\n"C3PO_DATABASE_URL=%s"\n\n'%e.VALUE.encode(),'SECRET_VALUE_SHAPE'),
                        (b'C3PO_DATABASE_URL=%s\n\n'%e.VALUE.encode(),'SECRET_VALUE_SHAPE'),
                        (b'"C3PO_DATABASE_URL=%s"\n'%e.VALUE.encode(),'SECRET_VALUE_SHAPE'),
                        (b'\n','SECRET_ENTRY_ABSENT'),
                        (b'"C3PO_DATABASE_URL=%s"\n"C3PO_DATABASE_URL=%s"\n\n'%(e.VALUE.encode(),e.VALUE.encode()),'SECRET_ENVIRONMENT_REPEATED')):
        def forged(template,schema,raw,fallback,answer=answer):
            return (0,answer) if template.startswith('{{range') else render(template,schema,raw,fallback)
        docs,host,before,receipt=run(lambda host,forged=forged:setattr(host.docker,'render',forged));refused(receipt,code)
    for answer in (b'{"project":"c3po"}\n',b'["c3po","r2d2-worker"]\n',b'not json\n'):
        def forged(template,schema,raw,fallback,answer=answer):
            return (0,answer) if template.startswith('{"project"') else render(template,schema,raw,fallback)
        docs,host,before,receipt=run(lambda host,forged=forged:setattr(host.docker,'render',forged))
        assert receipt['status']=='REFUSED' and receipt['code'] in ('CONTAINER_METADATA_INVALID','JSON_INVALID','DOCUMENT_TYPE'),receipt['code']

def test_a_refused_parse_of_the_entry_zeroes_what_it_made():
    m=M();recorded=[];real=m.zero_secret_values
    def spy(values):recorded.append(dict(values or {}));real(values)
    m.zero_secret_values=spy
    try:docs,host,before,receipt=run(worker_env(lambda env:env+['C3PO_DATABASE_URL='+e.VALUE]))
    finally:m.zero_secret_values=real
    refused(receipt,'SECRET_ENVIRONMENT_REPEATED')
    assert recorded and all(type(item) is bytearray and set(item)=={0} for values in recorded for item in values.values()) and any(recorded)

def test_with_several_causes_the_code_never_depends_on_a_length_or_a_character_of_the_value():
    """Worlds that differ only in the length or the characters of the value give byte-identical receipts when another
    cause is also present: labels of another service, a second replica, a repeated entry, the file present."""
    def receipt_of(prepare,**world):
        docs,host,before,receipt=run(prepare,**world);return e.line(receipt)
    for bad in ('x'*600,'x'*5000,'a"b'*30,'a\\b'*30,'a\nb'*30,'é'*40,'',' '):
        for cause,code in ((labels(**{'com.docker.compose.service':'api'}),'WORKER_NOT_THE_COMPOSE_SERVICE'),(replica('c3po-r2d2-worker-2'),'WORKER_NOT_THE_ONLY_ONE'),
                           (add(TARGET,kind='file',mode=0o600),'SECRET_ENV_PRESENT'),(worker_env(lambda env:env+['C3PO_DATABASE_URL=y']),'SECRET_ENVIRONMENT_REPEATED')):
            one=receipt_of(cause,value=bad);assert one==receipt_of(cause) and json.loads(one)['code']==code,(bad[:4],code)
        if bad!='x'*600:
            shape=receipt_of(value(bad));assert json.loads(shape)['code']=='SECRET_VALUE_SHAPE' and shape==receipt_of(value('a b')),bad[:4]


# ---------------------------------------------------------------- the review's points (2026-10-04)
def ps_state(state):
    """The listing says another state for the worker than the inspect does (the emulator derives one from the other)."""
    def act(host):
        render=host.docker.render
        def forged(template,schema,raw,fallback):
            if template==M().PS_FORMAT and raw.get('ID')==e.WORKER_ID:raw=dict(raw,State=state)
            return render(template,schema,raw,fallback)
        host.docker.render=forged
    return act
def test_the_listing_must_say_running_too():
    docs,host,before,receipt=run(ps_state('exited'));refused(receipt,'WORKER_NOT_RUNNING');nothing_changed(host,before)
    assert receipt['worker']['running'] is False and len(host.commands)==2

def env_file(name,content,**attributes):
    return lambda host:host.tree.add(CONFIG+'/'+name,kind=attributes.pop('kind','file'),uid=0,gid=0,mode=attributes.pop('mode',0o600),content=content,**attributes)
@pytest.mark.parametrize('name',['pins.env','activation.env'])
@pytest.mark.parametrize('content',[b'C3PO_DATABASE_URL=postgresql://other\n',b'C3PO_BUILD_SHA=x\n  C3PO_DATABASE_URL=y\n',b'C3PO_DATABASE_URL\n',
                                    b'C3PO_DATABASE_URL =y\n',b'\tC3PO_DATABASE_URL=\r\n',b'A=1\nC3PO_DATABASE_URL='])
def test_the_key_defined_in_another_env_file_is_refused(name,content):
    """README: "the writers and the readbacks refuse a name that appears in more than one file"."""
    docs,host,before,receipt=run(env_file(name,content));refused(receipt,'SECRET_KEY_IN_ANOTHER_ENV_FILE');nothing_changed(host,before)
    assert receipt['config_directory']['key_in_no_other_env_file'] is False and host.commands==[]

@pytest.mark.parametrize('content',[b'',b'#C3PO_DATABASE_URL=x\n',b'  # C3PO_DATABASE_URL=x\n',b'C3PO_DATABASE_URL_OLD=x\n',b'OLD_C3PO_DATABASE_URL=x\n',
                                    b'X=C3PO_DATABASE_URL=y\n',b'C3PO_BUILD_SHA='+b'a'*40+b'\n'+b'C'*(65536-56)])
def test_another_env_file_that_does_not_define_the_key_is_accepted(content):
    docs,host,before,receipt=run(lambda host:(env_file('pins.env',content)(host),env_file('activation.env',content)(host)))
    assert receipt['status']==M().COMPLETE_STATUS and receipt['config_directory']['key_in_no_other_env_file'] is True
    assert bytes(e.node(host,CONFIG+'/pins.env').content)==content

@pytest.mark.parametrize('prepare',[env_file('pins.env',b'x'*65537),env_file('pins.env',b'',kind='dir',mode=0o700),
                                    env_file('activation.env',b'',kind='symlink',mode=0o777,target='/etc/shadow'),env_file('activation.env',b'',kind='fifo')])
def test_another_env_file_that_cannot_be_read_as_a_regular_file_is_refused(prepare):
    docs,host,before,receipt=run(prepare);refused(receipt,'OTHER_ENV_FILE_UNREADABLE');nothing_changed(host,before)
    assert receipt['config_directory']['key_in_no_other_env_file'] is None

def test_an_output_over_the_limit_at_the_second_read_is_a_change_and_says_nothing_of_its_size():
    def second_read(change):
        def hook(host,name,detail,calls):
            argv=detail[0] if name=='run' else None
            if argv and argv[4]==TEMPLATE and [entry[1][4] for entry in host.log if entry[0]=='run' and len(entry[1])>4].count(TEMPLATE)==2:
                env=host.docker.container(e.WORKER)['Config']['Env'];env[:]=[item if not item.startswith('C3PO_DATABASE_URL=') else 'C3PO_DATABASE_URL='+change for item in env]
        return hook
    receipts=[]
    for change in ('x'*70000,'postgresql://c3po:ChAnGeD@db:5432/c3po','y'*5000):
        docs,host,before,receipt=run(hook=second_read(change));refused(receipt,'WORKER_ENVIRONMENT_CHANGED_DURING_READ');receipts.append(e.line(receipt))
        assert receipt['worker']['read_twice_equal'] is False and receipt['worker']['value_shape_met'] is True
    assert receipts[0]==receipts[1]==receipts[2]

def test_the_one_size_class_that_remains_is_an_output_over_the_limit():
    """DESIGN.md section 8: a repeated entry whose output exceeds the command's 65,536 bytes is refused by the shape, not
    by the repetition (the runner stops before the parse sees the names). Pinned so that a change is seen."""
    docs,host,before,receipt=run(worker_env(lambda env:env+['C3PO_DATABASE_URL='+'z'*40000]),value='w'*40000);refused(receipt,'SECRET_VALUE_SHAPE')
    docs,host,before,receipt=run(worker_env(lambda env:env+['C3PO_DATABASE_URL='+'z'*4000]),value='w'*4000);refused(receipt,'SECRET_ENVIRONMENT_REPEATED')

def test_a_withdrawal_whose_fsync_fails_in_any_way_is_said_once():
    for error in (OSError(errno.EIO,'io'),RuntimeError('not an OSError')):
        def hook(host,name,detail,calls,error=error):
            if name=='write' and detail[0]==TARGET:raise OSError(errno.ENOSPC,'full')
            if name=='fsync' and any(entry[0]=='unlink' for entry in host.log):raise error
        docs,host,before,receipt=run(hook=hook);partial(receipt,'FILESYSTEM_FULL');row=receipt['secret_env']
        assert (row['state'],row['withdrawn'],row['withdrawal_code'],row['code'])==('WITHDRAWN_NOT_DURABLE',True,'FSYNC_FAILED','FILESYSTEM_FULL')
        assert row['withdrawal_errno']==(errno.EIO if isinstance(error,OSError) else None) and node(host) is None and receipt['objects_left_by_this_run']==0
        assert [entry[0] for entry in host.log].count('unlink')==1

def test_a_code_shaped_text_at_the_directory_readback_is_reported_as_unlisted():
    m=M()
    def hook(host,name,detail,calls):
        if name=='names' and any(entry[0]=='create' for entry in host.log):raise m.Refused('FAKETOKENINCAPITALS')
    docs,host,before,receipt=run(hook=hook);partial(receipt,'DIRECTORY_READBACK_MISMATCH')
    assert receipt['directory_readback']=='UNLISTED_CODE' and 'FAKETOKENINCAPITALS' not in e.line(receipt).decode()

def test_the_line_is_built_in_one_buffer_of_its_final_length():
    m=M();buffers=[]
    k,host=e.world();commands=m.Commands(host,lambda:60.0);facts=m.worker_facts()
    content=m.secret_line(commands,e.WORKER_ID,facts,buffers)
    assert bytes(content)==e.line_of() and buffers[-1] is content and len(buffers)==3
    for buffer in buffers:m.zero(buffer)

def test_a_leftover_is_refused_before_another_env_file_is_read():
    def both(host):
        add(CONFIG+'/secret.env.tmp',kind='file',mode=0o600)(host);add(CONFIG+'/pins.env',kind='file',mode=0o600,content=b'C3PO_DATABASE_URL=x\n')(host)
    docs,host,before,receipt=run(both);refused(receipt,'SECRET_ENV_LEFTOVER_PRESENT')
    assert receipt['config_directory']['key_in_no_other_env_file'] is None and not [entry for entry in host.log if entry[0]=='open' and entry[1]==CONFIG+'/pins.env']


# ---------------------------------------------------------------- the second independent read (2026-10-04)
def test_the_entry_without_an_equals_sign_gives_the_receipt_of_an_empty_value():
    """Review 2, point 3: the bare name (the core's parse: SECRET_ENVIRONMENT_SHAPE) and an empty value (None:
    SECRET_VALUE_SHAPE) are one code and one receipt."""
    bare=worker_env(lambda env:[item if not item.startswith('C3PO_DATABASE_URL=') else 'C3PO_DATABASE_URL' for item in env])
    one=run(bare)[3];two=run(value(''))[3];refused(one,'SECRET_VALUE_SHAPE');assert e.line(one)==e.line(two)
    def second_read(host,name,detail,calls):
        argv=detail[0] if name=='run' else None
        if argv and argv[4]==TEMPLATE and [entry[1][4] for entry in host.log if entry[0]=='run' and len(entry[1])>4].count(TEMPLATE)==2:bare(host)
    docs,host,before,receipt=run(hook=second_read);refused(receipt,'WORKER_ENVIRONMENT_CHANGED_DURING_READ');assert receipt['worker']['read_twice_equal'] is False

@pytest.mark.parametrize('change',['recreated','stopped','removed','renamed'])
def test_the_worker_is_listed_again_after_the_reads(change):
    """Review 2, point 4: the inspects name the worker by its 64-hex ID, which the CLI also matches against names; the
    listing after the second read must still show the signed ID as the one running container of the name."""
    def act(host):
        worker=host.docker.container(e.WORKER)
        if change=='recreated':worker['Id']='6f'*32
        elif change=='stopped':worker['State'].update(Status='exited',Running=False)
        elif change=='removed':host.docker.containers.remove(worker)
        else:worker['Name']='/c3po-r2d2-worker-old'
    def hook(host,name,detail,calls):
        argv=detail[0] if name=='run' else None
        if argv and argv[1]=='ps' and [entry[1][1] for entry in host.log if entry[0]=='run'].count('ps')==2:act(host)      # just before the second listing
    docs,host,before,receipt=run(hook=hook);refused(receipt,'WORKER_CHANGED_DURING_READ');nothing_changed(host,before)
    assert receipt['worker']['read_twice_equal'] is True and receipt['worker']['same_container_after_the_reads'] is False and len(host.commands)==6

def test_a_withdrawal_after_a_failed_write_says_the_directory_was_at_its_path():
    docs,host,before,receipt=run(hook=once(failing('write',TARGET,OSError(errno.ENOSPC,'full'))));row=receipt['secret_env']
    assert (row['state'],row['directory_at_the_signed_path'])==('WITHDRAWN',True)
    def gone(host,name,detail):
        if name=='write' and detail[0]==TARGET:
            old=host.tree.get(CONFIG);host.tree.remove(CONFIG);host.tree.add('/etc/moved',mode=0o700)
            host.tree.get('/etc').children['moved']=old;host.tree.add(CONFIG,uid=0,gid=0,mode=0o700)
            raise OSError(errno.ENOSPC,'full')
        return False
    docs,host,before,receipt=run(hook=once(gone));row=receipt['secret_env']
    assert (row['state'],row['directory_at_the_signed_path'])==('WITHDRAWN',False) and e.node(host,'/etc/moved/secret.env') is None
