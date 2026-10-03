"""The token placement on the emulated host: the complete run, every refusal before the creation (nothing changed,
no mutating call), every failure after it (the withdrawal by identity, or what is left and why), the parser of the
environment file rule by rule, the signed plan, and the receipt (codes, booleans and identity rows only)."""
from datetime import timedelta
import errno
import json
import os
import re

import pytest

import family as f
import hostemu
import tok

def M():return tok.K().m

def run(prepare=None,hook=None,env=None,now=None,minutes=5,clock=None,fields=None):
    """One run on a fresh emulated host. prepare(host) changes the host before the run (as it would be found);
    hook(host,name,detail,calls) acts during it. Returns (docs, host, snapshot before, receipt)."""
    k,host=tok.world(env)
    if prepare is not None:prepare(host)
    docs=f.Docs(k,dict(tok.fields(host),**(fields or {})),now=now or tok.NOW,minutes=minutes)
    before=tok.state_of(host);host.hook=hook
    options={} if clock is None else {'clock':clock}
    receipt=docs.run(host,**options)
    assert f.sealed(receipt) and type(receipt) is dict
    assert tok.leaks(tok.line(receipt))==[] and tok.LITERAL.encode() not in tok.line(receipt)
    assert hostemu.SECRET.encode() not in tok.line(receipt)
    return docs,host,before,receipt

def refused(receipt,code):
    m=M()
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('REFUSED',m.REFUSED_OUTCOME,code),(receipt['code'],code)
    assert receipt['mutating_calls']['succeeded']==0 and receipt['mutating_calls']['uncertain']==0
    assert receipt['objects_left_by_this_run'] in (0,None) or receipt['phase_reached']=='AUTHENTICATION'
def nothing_changed(host,before):
    assert tok.state_of(host)==before and [entry for entry in host.mutating() if entry[0]!='create']==[]
def once(action):
    """A hook that acts at the first call it matches (the action returns True or raises) and never again."""
    done=[False]
    def hook(host,name,detail,calls):
        if done[0]:return
        try:done[0]=bool(action(host,name,detail))
        except BaseException:
            done[0]=True;raise
    return hook
def always(action):
    """A hook that acts at every call (the action is given host, name and detail)."""
    def hook(host,name,detail,calls):action(host,name,detail)
    return hook
def failing(call,path,error):
    def act(host,name,detail):
        if name==call and detail[0]==path:raise error
        return False
    return act


# ---------------------------------------------------------------- the complete run
def test_complete_run_places_the_token_and_reads_it_back():
    m=M();docs,host,before,receipt=run()
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.COMPLETE_STATUS,'TOKEN_PLACED_METADATA_VERIFIED',None)
    node=tok.token_node(host)
    assert (node.kind,node.uid,node.gid,node.mode,node.nlink,bytes(node.content))==('file',0,0,0o600,1,tok.TOKEN.encode()+b'\n') and node.synced
    row=receipt['token_file'];assert row['state']=='PLACED_VERIFIED' and row['code'] is None and row['created'] is True
    for key in ('fsync_file','fsync_directory','regular','uid_0','gid_0','mode_0600','single_link','size_within_1_4096','on_the_device_of_the_directory',
                'readback_same_inode','readback_bytes_equal_what_was_written','meets_the_supervisor_file_rules'):assert row[key] is True,key
    assert (row['device'],row['inode'])==(node.dev,node.ino) and row['withdrawn'] is False and row['withdrawal_code'] is None
    assert receipt['mutating_calls']=={'issued':2,'succeeded':2,'failed_nothing_changed':0,'uncertain':0} and receipt['objects_left_by_this_run']==1
    assert receipt['precheck']=={'token_file_absent':True,'seconds_left_before_the_creation':60} and receipt['readback']=='COMPLETE'
    assert receipt['clock']=={'utc_start':tok.NOW.isoformat(),'utc_end':tok.NOW.isoformat(),'monotonic_elapsed_ms':0} and receipt['observed_at']==tok.NOW.isoformat()
    assert all(value is True for key,value in receipt['environment_file'].items() if key!='names_defined')
    assert receipt['environment_file']['names_defined']=={'C3PO_MASSIVE_API_TOKEN':False,'MASSIVE_API_TOKEN':True}
    assert receipt['deploy_chain']=={'walked_without_following_a_link':True,'root_owned_and_closed_above_the_deploy_directory':True,
                                     'no_component_world_writable_without_sticky':True}
    assert receipt['config_directory']=={'rows':tok.fields(host)['config_chain'],'pinned':True}
    assert receipt['pre_existing_objects_modified'] is False and receipt['activation_performed'] is False and receipt['secret_bytes_in_receipt'] is False
    # only the token file changed, and nothing but the creation and the write was made
    changed=tok.state_of(host);host.tree.remove(tok.TOKEN_PATH);assert tok.state_of(host)==before;del changed
    assert [entry[0] for entry in host.mutating()]==['create','write']

def test_the_creation_is_one_exclusive_create_relative_to_the_held_directory_after_the_umask():
    docs,host,before,receipt=run()
    names=[entry[0] for entry in host.log];create=[entry for entry in host.log if entry[0]=='create']
    assert len(create)==1 and create[0][1:]==(tok.TOKEN_PATH,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    assert names.index('umask')<names.index('create') and [entry for entry in host.log if entry[0]=='umask']==[('umask',0o077)]
    assert [entry[1] for entry in host.log if entry[0]=='fsync']==[tok.TOKEN_PATH,tok.CONFIG]
    # the environment file: looked at, opened once without following a link, looked at again; never written
    assert [entry for entry in host.log if entry[0]=='open' and entry[1]==tok.ENV_FILE]==[('open',tok.ENV_FILE,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|hostemu.NOATIME)]
    assert [entry[0] for entry in host.log if entry[1:2]==(tok.ENV_FILE,)]==['lstat','open','fstat','read','read','fstat','lstat']
    # the readback opens the token by name in the held directory, read-only, without following a link
    assert [entry for entry in host.log if entry[0]=='open' and entry[1]==tok.TOKEN_PATH]==[('open',tok.TOKEN_PATH,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|hostemu.NOATIME)]
    assert host.fds=={}

def test_the_bytearray_that_held_the_value_is_zeroed_and_the_write_came_from_it():
    docs,host,before,receipt=run();assert receipt['status']==M().COMPLETE_STATUS
    assert len(host.written_from)==1 and type(host.written_from[0]) is bytearray and set(host.written_from[0])=={0}

@pytest.mark.parametrize('key',['C3PO_MASSIVE_API_TOKEN','MASSIVE_API_TOKEN'])
def test_either_name_alone_and_both_names_with_one_value(key):
    m=M()
    for env in (tok.env_with(key=key),tok.env_with(key=key,after=b'C3PO_MASSIVE_API_TOKEN='+tok.TOKEN.encode()+b'\n'),
                tok.env_with(key=key,before=b'MASSIVE_API_TOKEN='+tok.TOKEN.encode()+b'\n')):
        docs,host,before,receipt=run(env=env)
        assert receipt['status']==m.COMPLETE_STATUS and bytes(tok.token_node(host).content)==tok.TOKEN.encode()+b'\n'
        names=receipt['environment_file']['names_defined'];assert names[key] is True
        assert names=={name:any(line.startswith(name.encode()+b'=') for line in env.split(b'\n')) for name in m.TOKEN_KEYS}

def test_the_longest_value_of_the_grammar_is_placed_and_read_back():
    value='Ab'*256;docs,host,before,receipt=run(env=tok.env_with(token=value))
    assert receipt['status']==M().COMPLETE_STATUS and bytes(tok.token_node(host).content)==value.encode()+b'\n' and receipt['token_file']['size_within_1_4096'] is True

def test_the_evidence_names_the_precheck_and_the_provisioning_of_operation_2():
    k,host=tok.world()
    for missing in ('GO_READONLY_HOSTOPS_PRECHECK_01','GO_WRITE_SUPERVISOR_READER_PROVISION_01'):
        evidence=[{'role':'R%d'%index,'operation':name,'receipt_sha256':'b'*64} for index,name in enumerate(('GO_READONLY_HOSTOPS_PRECHECK_01','GO_WRITE_SUPERVISOR_READER_PROVISION_01')) if name!=missing]
        docs=f.Docs(k,tok.fields(host),now=tok.NOW,evidence=evidence);assert f.refusal(docs.authenticate)=='EVIDENCE_OPERATION_MISSING'

def test_writes_shorter_than_asked_are_continued_until_every_byte_is_written():
    class Short(tok.TokenHost):
        def write(self,fd,data):return tok.TokenHost.write(self,fd,data[:5])
    def prepare(host):host.__class__=Short
    docs,host,before,receipt=run(prepare)
    assert receipt['status']==M().COMPLETE_STATUS and bytes(tok.token_node(host).content)==tok.TOKEN.encode()+b'\n'
    assert len([entry for entry in host.log if entry[0]=='write'])==5 and receipt['mutating_calls']['succeeded']==6

def test_the_receipt_does_not_depend_on_the_token_value_or_length():
    """Two runs that differ only in the token, of different lengths: the receipts are the same bytes. So no value, digest,
    length or line count of it can be in a receipt, whatever the outcome."""
    def same(env_a,env_b,prepare=None,hook=None):
        out=[]
        for env in (env_a,env_b):
            docs,host,before,receipt=run(prepare,hook() if hook else None,env=env);out.append(tok.line(receipt))
        assert out[0]==out[1];return json.loads(out[0])
    assert same(tok.env_with(),tok.env_with(token=tok.LONGER))['status']==M().COMPLETE_STATUS
    assert same(tok.env_with(),tok.env_with(token=tok.LONGER),hook=lambda:once(failing('write',tok.TOKEN_PATH,OSError(errno.ENOSPC,'full'))))['token_file']['state']=='WITHDRAWN'
    assert same(tok.env_with(),tok.env_with(token=tok.LONGER),prepare=lambda host:host.tree.add(tok.TOKEN_PATH,kind='file',mode=0o600,content=b'x'))['code']=='TOKEN_FILE_PRESENT'
    for one,other in (('x'*15,'x'*3),('x'*513,'x'*600),('"'+tok.TOKEN+'"','"'+tok.LONGER+'"'),(tok.TOKEN+' ',tok.LONGER+' '),(tok.TOKEN+'$X',tok.LONGER+'$X'),('','x')):
        assert same(tok.env_with(token=one),tok.env_with(token=other))['code']=='ENV_TOKEN_VALUE_GRAMMAR'
    assert same(tok.env_with(after=b'C3PO_MASSIVE_API_TOKEN=FaKeOtHeRvAlUeFoRtEsTs\n'),tok.env_with(token=tok.LONGER,after=b'C3PO_MASSIVE_API_TOKEN=FaKeOtHeRvAlUeFoRtEsTsXy\n'))['code']=='ENV_TOKEN_DEFINITIONS_DISAGREE'


# ---------------------------------------------------------------- refusals before the creation: nothing changed
def add(path,**attributes):return lambda host:host.tree.add(path,**attributes)
def replace(path,**attributes):
    def act(host):host.tree.remove(path);host.tree.add(path,**attributes)
    return act
def env_mode(mode):
    def act(host):host.tree.get(tok.ENV_FILE).mode=mode
    return act
def env_owner(uid):
    def act(host):host.tree.get(tok.ENV_FILE).uid=uid
    return act
def set_mode(path,mode,uid=None):
    def act(host):
        node=host.tree.get(path);node.mode=mode
        if uid is not None:node.uid=uid
    return act

REFUSALS=[
    ('token_file_present',add(tok.TOKEN_PATH,kind='file',mode=0o600,content=b'previous'),'TOKEN_FILE_PRESENT'),
    ('token_name_is_a_link',add(tok.TOKEN_PATH,kind='symlink',mode=0o777,target='/nowhere'),'TOKEN_FILE_PRESENT'),
    ('token_name_is_a_directory',add(tok.TOKEN_PATH,mode=0o700),'TOKEN_FILE_PRESENT'),
    ('token_name_is_an_empty_file',add(tok.TOKEN_PATH,kind='file',mode=0o600),'TOKEN_FILE_PRESENT'),
    ('deploy_directory_absent',lambda host:host.tree.remove(tok.DEPLOY),'DEPLOY_DIRECTORY_ABSENT'),
    ('deploy_directory_is_a_link',replace(tok.DEPLOY,kind='symlink',mode=0o777,target='/srv/deploy'),'DEPLOY_CHAIN_SYMLINK'),
    ('opt_is_a_link',replace('/opt',kind='symlink',mode=0o777,target='/srv'),'DEPLOY_CHAIN_SYMLINK'),
    ('deploy_directory_is_a_file',replace(tok.DEPLOY,kind='file',mode=0o644),'DEPLOY_CHAIN_NOT_A_DIRECTORY'),
    ('deploy_directory_world_writable',set_mode(tok.DEPLOY,0o777),'DEPLOY_CHAIN_WORLD_WRITABLE'),
    ('deploy_directory_world_writable_setgid',set_mode(tok.DEPLOY,0o2777),'DEPLOY_CHAIN_WORLD_WRITABLE'),
    ('opt_group_writable',set_mode('/opt',0o775),'DEPLOY_CHAIN_NOT_ROOT_OWNED_ABOVE_THE_DEPLOY_DIRECTORY'),
    ('opt_not_root_owned',set_mode('/opt',0o755,uid=1000),'DEPLOY_CHAIN_NOT_ROOT_OWNED_ABOVE_THE_DEPLOY_DIRECTORY'),
    ('env_file_absent',lambda host:host.tree.remove(tok.ENV_FILE),'ENV_FILE_ABSENT'),
    ('env_file_is_a_link',replace(tok.ENV_FILE,kind='symlink',mode=0o777,target='/etc/hostname'),'ENV_FILE_NOT_REGULAR'),
    ('env_file_is_a_fifo',replace(tok.ENV_FILE,kind='fifo',mode=0o600,uid=1000,gid=1000),'ENV_FILE_NOT_REGULAR'),
    ('env_file_is_a_directory',replace(tok.ENV_FILE,mode=0o700,uid=1000,gid=1000),'ENV_FILE_NOT_REGULAR'),
    ('env_file_world_writable',env_mode(0o602),'ENV_FILE_WORLD_WRITABLE'),
    ('env_file_world_writable_and_readable',env_mode(0o666),'ENV_FILE_WORLD_WRITABLE'),
    ('env_file_of_another_owner',env_owner(1001),'ENV_FILE_OWNER_UNEXPECTED'),
    ('env_file_too_large',lambda host:host.tree.get(tok.ENV_FILE).content.extend(b'#'*(65536-len(host.tree.get(tok.ENV_FILE).content)+1)),'ENV_FILE_TOO_LARGE'),
    ('noatime_unavailable',lambda host:setattr(host,'noatime_available',False),'NOATIME_UNAVAILABLE'),
]
@pytest.mark.parametrize('name,prepare,code',REFUSALS,ids=[row[0] for row in REFUSALS])
def test_refusal_before_the_creation_changes_nothing(name,prepare,code):
    docs,host,before,receipt=run(prepare);refused(receipt,code);nothing_changed(host,before)
    assert receipt['phase_reached']=='PRECHECK' and receipt['token_file']['state']=='NOT_ATTEMPTED' and receipt['mutating_calls']['issued']==0
    assert not [entry for entry in host.log if entry[0]=='create']
    if name!='token_file_present' and not name.startswith('token_name'):assert tok.token_node(host) is None
    else:assert receipt['precheck']['token_file_absent'] is False

ACCEPTED=[('deploy_directory_world_writable_with_sticky',set_mode(tok.DEPLOY,0o1777)),('deploy_directory_group_writable',set_mode(tok.DEPLOY,0o775)),
          ('deploy_directory_and_env_file_root_owned',lambda host:(set_mode(tok.DEPLOY,0o755,uid=0)(host),env_owner(0)(host))),('env_file_group_writable',env_mode(0o660)),('env_file_0644',env_mode(0o644)),
          ('env_file_root_owned',env_owner(0)),('env_file_of_exactly_65536_bytes',lambda host:host.tree.get(tok.ENV_FILE).content.extend(b'#'*(65536-len(host.tree.get(tok.ENV_FILE).content)))),
          ('another_entry_in_the_configuration_directory',add(tok.CONFIG+'/token.new',kind='file',mode=0o600,content=b'x'))]
@pytest.mark.parametrize('name,prepare',ACCEPTED,ids=[row[0] for row in ACCEPTED])
def test_states_the_rules_accept_complete(name,prepare):
    docs,host,before,receipt=run(prepare);assert receipt['status']==M().COMPLETE_STATUS,receipt['code']
    assert bytes(tok.token_node(host).content)==tok.TOKEN.encode()+b'\n'

def deeper(host):
    host.tree.add('/srv/a/b/deploy',uid=1000,gid=1000);host.tree.add('/srv/a/b/deploy/.env',kind='file',uid=1000,gid=1000,mode=0o600,content=tok.env_with())
def test_an_unwritable_or_deeper_deploy_chain_is_judged_as_read():
    m=M()
    docs,host,before,receipt=run(deeper,fields={'deploy_directory':'/srv/a/b/deploy'})
    assert receipt['status']==m.COMPLETE_STATUS and receipt['effects']['environment_file']['path']=='/srv/a/b/deploy/.env'
    docs,host,before,receipt=run(lambda host:(deeper(host),setattr(host.tree.get('/srv/a'),'mode',0o757)),fields={'deploy_directory':'/srv/a/b/deploy'})
    refused(receipt,'DEPLOY_CHAIN_NOT_ROOT_OWNED_ABOVE_THE_DEPLOY_DIRECTORY');nothing_changed(host,before)
    assert receipt['deploy_chain']=={'walked_without_following_a_link':True,'root_owned_and_closed_above_the_deploy_directory':False,
                                     'no_component_world_writable_without_sticky':False}

def test_parse_refusals_through_the_run_change_nothing():
    for env,code in ((tok.BASE_ENV,'ENV_TOKEN_ABSENT'),(tok.BASE_ENV+b'export MASSIVE_API_TOKEN='+tok.TOKEN.encode()+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
                     (tok.BASE_ENV+b'MASSIVE_API_TOKEN="'+tok.TOKEN.encode()+b'"\n','ENV_TOKEN_VALUE_GRAMMAR'),
                     (tok.env_with()+b'C3PO_MASSIVE_API_TOKEN=FaKeOtHeRvAlUeFoRtEsTs\n','ENV_TOKEN_DEFINITIONS_DISAGREE'),
                     (tok.env_with().replace(b'\n',b'\r\n'),'ENV_FILE_SYNTAX_UNSUPPORTED')):
        docs,host,before,receipt=run(env=env);refused(receipt,code);nothing_changed(host,before);assert tok.token_node(host) is None
        facts=receipt['environment_file']
        assert facts['unchanged_during_read'] is True and facts['value_grammar_met'] is None
        assert facts['syntax_within_the_accepted_subset'] is (None if code in ('ENV_FILE_SYNTAX_UNSUPPORTED','ENV_TOKEN_DEFINITION_NOT_PLAIN') else True)

def test_the_environment_file_changed_while_it_was_read_is_a_refusal():
    def grow(host,name,detail):
        if name=='read' and detail[0]==tok.ENV_FILE:host.tree.get(tok.ENV_FILE).content.extend(b'#\n');return True
    def swap_before_open(host,name,detail):
        if name=='open' and detail[0]==tok.ENV_FILE:
            host.tree.remove(tok.ENV_FILE);host.tree.add(tok.ENV_FILE,kind='file',uid=1000,gid=1000,mode=0o600,content=tok.env_with());return True
    def swap_after_read(host,name,detail):
        if name=='lstat' and detail[0]==tok.ENV_FILE and [entry for entry in host.log if entry[0]=='read' and entry[1]==tok.ENV_FILE]:
            host.tree.remove(tok.ENV_FILE);host.tree.add(tok.ENV_FILE,kind='file',uid=1000,gid=1000,mode=0o600,content=tok.env_with());return True
    def touch_after_read(host,name,detail):
        if name=='lstat' and detail[0]==tok.ENV_FILE and [entry for entry in host.log if entry[0]=='read' and entry[1]==tok.ENV_FILE]:
            host.tree.get(tok.ENV_FILE).mtime+=1;return True
    def gone_before_open(host,name,detail):
        if name=='open' and detail[0]==tok.ENV_FILE:host.tree.remove(tok.ENV_FILE);return True
    for action in (grow,swap_before_open,swap_after_read,touch_after_read,gone_before_open):
        docs,host,before,receipt=run(hook=once(action));refused(receipt,'ENV_FILE_CHANGED_DURING_READ')
        assert receipt['environment_file']['unchanged_during_read'] is None and tok.token_node(host) is None

class AtTheOpen(tok.TokenHost):
    """An emulated host on which the environment file is other at the moment it is opened (the core's emulation resolves
    a name before its hook runs, so a change at the open itself needs this)."""
    change=None;name='.env'
    def open(self,name,flags,dir_fd=None):
        if name==self.name and dir_fd is not None and self.change is not None:
            change,self.change=self.change,None;restore=change(self.fds[dir_fd][0].children)
            try:return tok.TokenHost.open(self,name,flags,dir_fd)
            finally:
                if restore is not None:restore()
        return tok.TokenHost.open(self,name,flags,dir_fd)
def at_the_open(change,name='.env'):
    def prepare(host):host.__class__=AtTheOpen;host.change=change;host.name=name
    return prepare
def test_the_environment_file_other_at_the_open_is_a_refusal():
    def vanish(children):children.pop('.env');return None
    def fifo(children):children['.env']=hostemu.Node('fifo',uid=1000,gid=1000,mode=0o600,ino=9001);return None
    def swapped_for_the_open_only(children):
        old=children['.env'];children['.env']=hostemu.Node('file',uid=1000,gid=1000,mode=0o600,ino=9002,content=tok.env_with())
        def restore():children['.env']=old
        return restore
    for change,code in ((vanish,'ENV_FILE_CHANGED_DURING_READ'),(fifo,'ENV_FILE_NOT_REGULAR'),(swapped_for_the_open_only,'ENV_FILE_CHANGED_DURING_READ')):
        docs,host,before,receipt=run(at_the_open(change));refused(receipt,code);assert tok.token_node(host) is None

def test_a_deploy_directory_replaced_during_the_walk_is_a_refusal():
    def swapped(children):
        old=children['chief-of-staff-digital'];children['chief-of-staff-digital']=hostemu.Node('dir',uid=1000,gid=1000,mode=0o755,ino=9003)
        def restore():children['chief-of-staff-digital']=old
        return restore
    docs,host,before,receipt=run(at_the_open(swapped,'chief-of-staff-digital'));refused(receipt,'DEPLOY_CHAIN_CHANGED_DURING_WALK')
    assert receipt['deploy_chain']['walked_without_following_a_link'] is None

def test_a_failing_system_call_of_the_precheck_is_told_apart():
    docs,host,before,receipt=run(hook=once(failing('lstat',tok.TOKEN_PATH,OSError(errno.EIO,'x'))));refused(receipt,'PRECHECK_OS_ERROR')
    docs,host,before,receipt=run(hook=once(failing('lstat',tok.TOKEN_PATH,RuntimeError('x'))));refused(receipt,'PRECHECK_FAILED')

def test_a_configuration_directory_that_is_not_the_signed_one_is_a_refusal():
    def swap(host,name,detail):
        if name=='umask':host.tree.remove(tok.CONFIG);host.tree.add(tok.CONFIG,mode=0o700);return True
    docs,host,before,receipt=run(hook=once(swap));refused(receipt,'PARENT_IDENTITY_MISMATCH');assert receipt['phase_reached']=='PRECHECK'
    assert receipt['config_directory']['pinned'] is False and len(receipt['config_directory']['rows'])==3 and not [entry for entry in host.log if entry[0]=='create']

def test_the_configuration_directory_replaced_before_the_creation_is_a_refusal():
    def swap(host,name,detail):
        if name=='open' and detail[0]==tok.ENV_FILE:
            node=host.tree.get(tok.CONFIG);host.tree.remove(tok.CONFIG);host.tree.add(tok.CONFIG,mode=0o700);return True
    docs,host,before,receipt=run(hook=once(swap));refused(receipt,'PARENT_REPLACED')
    assert receipt['token_file']['state']=='NOT_ATTEMPTED' and not [entry for entry in host.log if entry[0]=='create']

def test_boot_and_budget_are_refused_before_the_creation():
    docs,host,before,receipt=run(fields={'evidence_boot_id_sha256':'c'*64});refused(receipt,'EVIDENCE_FROM_EARLIER_BOOT');nothing_changed(host,before)
    docs,host,before,receipt=run(minutes=14/60);refused(receipt,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT');nothing_changed(host,before)
    assert receipt['precheck']['seconds_left_before_the_creation']==14
    docs,host,before,receipt=run(minutes=15/60);assert receipt['status']==M().COMPLETE_STATUS and receipt['precheck']['seconds_left_before_the_creation']==15

def test_a_token_that_appears_after_the_precheck_is_left_alone_and_the_run_is_a_refusal():
    def appear(host,name,detail):
        if name=='create':host.tree.add(tok.TOKEN_PATH,kind='file',mode=0o600,content=b'theirs');return True
    docs,host,before,receipt=run(hook=once(appear));refused(receipt,'TOKEN_FILE_APPEARED_AFTER_PRECHECK')
    assert bytes(tok.token_node(host).content)==b'theirs' and receipt['token_file']['state']=='NOT_CREATED' and receipt['token_file']['errno']==errno.EEXIST
    assert receipt['mutating_calls']=={'issued':1,'succeeded':0,'failed_nothing_changed':1,'uncertain':0} and receipt['objects_left_by_this_run']==0

def test_a_refused_creation_is_a_refusal():
    docs,host,before,receipt=run(lambda host:setattr(host,'readonly',True));refused(receipt,'FILESYSTEM_READ_ONLY')
    assert receipt['token_file']['state']=='NOT_CREATED' and tok.token_node(host) is None and receipt['phase_reached']=='EFFECTS'
    docs,host,before,receipt=run(hook=once(failing('create',tok.TOKEN_PATH,OSError(errno.EACCES,'denied'))));refused(receipt,'FILESYSTEM_ACCESS_DENIED')
    assert receipt['token_file']['errno']==errno.EACCES

def test_expiry_at_the_creation_is_a_refusal_with_nothing_issued():
    now=tok.NOW;moments=[]
    def clock():return now if len([entry for entry in moments])<1 else now+timedelta(minutes=10)
    def mark(host,name,detail):
        if name=='lstat' and detail[0]==tok.ENV_FILE and [entry for entry in host.log if entry[0]=='read' and entry[1]==tok.ENV_FILE]:moments.append(1);return True
    # the gate before the budget refuses first: the expiry is seen before the creation
    docs,host,before,receipt=run(hook=once(mark),clock=clock);refused(receipt,'GO_EXPIRED');assert receipt['mutating_calls']['issued']==0


# ---------------------------------------------------------------- failures after the creation
def test_a_full_filesystem_at_the_write_withdraws_the_file_of_this_run():
    m=M();docs,host,before,receipt=run(hook=once(failing('write',tok.TOKEN_PATH,OSError(errno.ENOSPC,'full'))))
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,m.PARTIAL_OUTCOME,'FILESYSTEM_FULL')
    row=receipt['token_file']
    assert (row['state'],row['created'],row['withdrawn'],row['errno'],row['withdrawal_code'],row['fsync_directory_after_withdrawal'])==('WITHDRAWN',True,True,errno.ENOSPC,None,True)
    assert tok.token_node(host) is None and tok.state_of(host)==before and receipt['objects_left_by_this_run']==0 and receipt['readback'] is None
    assert receipt['mutating_calls']=={'issued':3,'succeeded':2,'failed_nothing_changed':1,'uncertain':0} and receipt['phase_reached']=='EFFECTS'
    assert [entry[0] for entry in host.mutating()]==['create','write','unlink'] and [entry[1] for entry in host.log if entry[0]=='fsync']==[tok.CONFIG]

@pytest.mark.parametrize('number,code',[(errno.EIO,'FILESYSTEM_ERROR'),(errno.EDQUOT,'FILESYSTEM_FULL'),(errno.EROFS,'FILESYSTEM_READ_ONLY')])
def test_any_write_error_is_withdrawn_with_its_code(number,code):
    docs,host,before,receipt=run(hook=once(failing('write',tok.TOKEN_PATH,OSError(number,'x'))))
    assert receipt['code']==code and receipt['token_file']['state']=='WITHDRAWN' and tok.token_node(host) is None

def test_a_write_that_writes_nothing_is_withdrawn():
    class Nothing(tok.TokenHost):
        def write(self,fd,data):self.event('write',self.path_of(fd),len(data));return 0
    docs,host,before,receipt=run(lambda host:setattr(host,'__class__',Nothing))
    assert receipt['code']=='TOKEN_WRITE_INCOMPLETE' and receipt['token_file']['state']=='WITHDRAWN' and tok.token_node(host) is None
    assert receipt['status']==M().PARTIAL_STATUS

def test_a_failed_fsync_of_the_file_or_of_the_directory_is_withdrawn():
    docs,host,before,receipt=run(hook=once(failing('fsync',tok.TOKEN_PATH,OSError(errno.EIO,'x'))))
    assert receipt['code']=='FSYNC_FAILED' and receipt['token_file']['state']=='WITHDRAWN' and receipt['token_file']['fsync_file'] is False and tok.token_node(host) is None
    docs,host,before,receipt=run(hook=once(failing('fsync',tok.CONFIG,OSError(errno.EIO,'x'))))
    row=receipt['token_file']
    assert receipt['code']=='FSYNC_FAILED' and row['state']=='WITHDRAWN' and row['fsync_file'] is True and row['fsync_directory'] is False and tok.token_node(host) is None

@pytest.mark.parametrize('label,change,key',[('group',lambda node:setattr(node,'gid',1000),'gid_0'),('owner',lambda node:setattr(node,'uid',1000),'uid_0'),
                                             ('mode',lambda node:setattr(node,'mode',0o644),'mode_0600'),('device',lambda node:setattr(node,'dev',999),'on_the_device_of_the_directory'),
                                             ('size',lambda node:node.content.extend(b'x'),None)])
def test_metadata_other_than_the_contract_is_withdrawn(label,change,key):
    def act(host,name,detail):
        if name=='fsync' and detail[0]==tok.TOKEN_PATH:change(tok.token_node(host));return True
    docs,host,before,receipt=run(hook=once(act));row=receipt['token_file']
    assert receipt['code']=='TOKEN_METADATA_MISMATCH' and row['state']=='WITHDRAWN' and tok.token_node(host) is None
    if key is not None:assert row[key] is False
    else:assert all(row[name] is True for name in ('regular','uid_0','gid_0','mode_0600','single_link','size_within_1_4096'))

def test_the_metadata_facts_of_one_stat():
    """The function that turns one stat of the token file into the booleans of the receipt, alone: a regular file of
    the contract; then each member that departs from it."""
    import stat as modes
    import types
    m=M();config=types.SimpleNamespace(identity=(801,5049,0,0,0o700))
    def info(**change):
        values=dict(st_mode=modes.S_IFREG|0o600,st_uid=0,st_gid=0,st_nlink=1,st_size=22,st_dev=801);values.update(change)
        return types.SimpleNamespace(**values)
    row=m.token_row();assert m.metadata_facts(info(),row,config) is True and row['meets_the_supervisor_file_rules'] is True
    for change,key,verdict in ((dict(st_mode=modes.S_IFIFO|0o600),'regular',False),(dict(st_size=0),'size_within_1_4096',False),
                               (dict(st_size=4097),'size_within_1_4096',False),(dict(st_size=4096),'size_within_1_4096',True),(dict(st_size=1),'size_within_1_4096',True),
                               (dict(st_uid=1),'uid_0',False),(dict(st_gid=1),'gid_0',False),(dict(st_mode=modes.S_IFREG|0o400),'mode_0600',False),
                               (dict(st_nlink=0),'single_link',False),(dict(st_dev=802),'on_the_device_of_the_directory',False)):
        row=m.token_row();result=m.metadata_facts(info(**change),row,config)
        assert row[key] is verdict and result is verdict,(change,key)
        assert row['meets_the_supervisor_file_rules'] is (verdict or key in ('gid_0','on_the_device_of_the_directory')),(change,key)

def test_a_second_link_to_the_file_is_never_removed():
    def link(host,name,detail):
        if name=='fsync' and detail[0]==tok.TOKEN_PATH:
            node=tok.token_node(host);host.tree.get(tok.CONFIG).children['other-name']=node;node.nlink=2;return True
    docs,host,before,receipt=run(hook=once(link));row=receipt['token_file']
    assert receipt['code']=='TOKEN_METADATA_MISMATCH' and row['single_link'] is False and row['state']=='LEFT_UNVERIFIED'
    assert row['withdrawal_code']=='TOKEN_NAME_NOT_THIS_RUNS_FILE' and tok.token_node(host) is not None and receipt['objects_left_by_this_run']==1
    assert not [entry for entry in host.log if entry[0]=='unlink'] and receipt['status']==M().PARTIAL_STATUS

def test_the_readback_compares_the_bytes_and_the_inode():
    def change(host,name,detail):
        if name=='open' and detail[0]==tok.TOKEN_PATH:tok.token_node(host).content[0:1]=b'Z';return True
    docs,host,before,receipt=run(hook=once(change));row=receipt['token_file']
    assert receipt['code']=='READBACK_MISMATCH' and row['readback_bytes_equal_what_was_written'] is False and row['readback_same_inode'] is True
    assert row['state']=='WITHDRAWN' and tok.token_node(host) is None
    def swap(host,name,detail):                                     # between the fsync of the directory and the readback
        if name=='fsync' and detail[0]==tok.CONFIG:
            host.tree.remove(tok.TOKEN_PATH);host.tree.add(tok.TOKEN_PATH,kind='file',mode=0o600,content=tok.TOKEN.encode()+b'\n');return True
    docs,host,before,receipt=run(hook=once(swap));row=receipt['token_file']
    assert receipt['code']=='READBACK_MISMATCH' and row['readback_same_inode'] is False and row['state']=='LEFT_UNVERIFIED'
    assert row['withdrawal_code']=='TOKEN_NAME_NOT_THIS_RUNS_FILE' and tok.token_node(host) is not None and not [entry for entry in host.log if entry[0]=='unlink']
    def mode(host,name,detail):
        if name=='open' and detail[0]==tok.TOKEN_PATH:tok.token_node(host).mode=0o640;return True
    docs,host,before,receipt=run(hook=once(mode))
    assert receipt['code']=='READBACK_MISMATCH' and receipt['token_file']['mode_0600'] is False and receipt['token_file']['state']=='WITHDRAWN'

def test_a_failed_readback_is_withdrawn_and_a_vanished_file_is_not_called_withdrawn():
    docs,host,before,receipt=run(hook=once(failing('read',tok.TOKEN_PATH,OSError(errno.EIO,'x'))))
    assert receipt['code']=='READBACK_UNAVAILABLE' and receipt['token_file']['state']=='WITHDRAWN' and receipt['token_file']['errno']==errno.EIO
    def vanish(host,name,detail):
        if name=='fsync' and detail[0]==tok.CONFIG:host.tree.remove(tok.TOKEN_PATH);return True
    docs,host,before,receipt=run(hook=once(vanish));row=receipt['token_file']
    assert receipt['code']=='READBACK_UNAVAILABLE' and row['state']=='LEFT_UNVERIFIED' and row['withdrawal_code']=='TOKEN_WITHDRAWAL_FAILED' and row['withdrawn'] is False
    def large(host,name,detail):
        if name=='open' and detail[0]==tok.TOKEN_PATH:tok.token_node(host).content.extend(b'y'*4096);return True
    docs,host,before,receipt=run(hook=once(large))
    assert receipt['code']=='READBACK_MISMATCH' and receipt['token_file']['state']=='WITHDRAWN'

def test_a_replaced_configuration_directory_stops_the_run_and_nothing_is_removed():
    def swap(host,name,detail):
        if name=='fsync' and detail[0]==tok.CONFIG:
            host.tree.remove(tok.CONFIG);host.tree.add(tok.CONFIG,mode=0o700);return True
    docs,host,before,receipt=run(hook=once(swap));row=receipt['token_file']
    assert receipt['code']=='PARENT_REPLACED' and row['state']=='LEFT_UNVERIFIED' and row['withdrawal_code'] is None and receipt['status']==M().PARTIAL_STATUS
    assert not [entry for entry in host.log if entry[0]=='unlink'] and receipt['objects_left_by_this_run']==1

def test_expiry_after_the_creation_leaves_the_file_and_says_so():
    created=[]
    def clock():return tok.NOW+timedelta(minutes=10) if created else tok.NOW
    def mark(host,name,detail):
        if name=='create':created.append(1);return True
    m=M();docs,host,before,receipt=run(hook=once(mark),clock=clock);row=receipt['token_file']
    assert (receipt['status'],receipt['code'],row['state'],row['withdrawn'])==(m.PARTIAL_STATUS,'GO_EXPIRED','LEFT_UNVERIFIED',False)
    assert tok.token_node(host) is not None and receipt['objects_left_by_this_run']==1 and receipt['mutating_calls']['succeeded']==1

def test_expiry_at_the_readback_leaves_the_file_and_never_removes_it():
    late=[]
    def clock():return tok.NOW+timedelta(minutes=10) if late else tok.NOW
    def at(call,path):
        def act(host,name,detail):
            if name==call and detail[0]==path:late.append(1);return True
        return act
    m=M()
    for call,path in (('fsync',tok.CONFIG),('open',tok.TOKEN_PATH)):        # before the directory is proved again; inside the read
        del late[:];docs,host,before,receipt=run(hook=once(at(call,path)),clock=clock);row=receipt['token_file']
        assert (receipt['status'],receipt['code'],row['state'],row['withdrawn'],row['withdrawal_code'])==(m.PARTIAL_STATUS,'GO_EXPIRED','LEFT_UNVERIFIED',False,None),call
        assert tok.token_node(host) is not None and not [entry for entry in host.log if entry[0]=='unlink']

def test_a_withdrawal_that_fails_leaves_the_file_and_says_why():
    def both(host,name,detail):
        if name=='write' and detail[0]==tok.TOKEN_PATH:raise OSError(errno.ENOSPC,'full')
        if name=='unlink' and detail[0]==tok.TOKEN_PATH:raise OSError(errno.EBUSY,'busy')
    docs,host,before,receipt=run(hook=always(both));row=receipt['token_file']
    assert (receipt['code'],row['state'],row['withdrawal_code'],row['withdrawal_errno'],row['withdrawn'])==('FILESYSTEM_FULL','LEFT_UNVERIFIED','TOKEN_WITHDRAWAL_FAILED',errno.EBUSY,False)
    assert tok.token_node(host) is not None and receipt['objects_left_by_this_run']==1
    def fsync_after(host,name,detail):
        if name=='write' and detail[0]==tok.TOKEN_PATH:raise OSError(errno.ENOSPC,'full')
        if name=='fsync' and detail[0]==tok.CONFIG:raise OSError(errno.EIO,'x')
    docs,host,before,receipt=run(hook=always(fsync_after));row=receipt['token_file']
    assert (row['state'],row['withdrawal_code'],row['withdrawn'],row['fsync_directory_after_withdrawal'])==('WITHDRAWN_NOT_DURABLE','FSYNC_FAILED',True,False)
    assert tok.token_node(host) is None and receipt['objects_left_by_this_run']==0

def test_an_unexpected_failure_after_the_creation_is_withdrawn_and_one_at_the_creation_is_uncertain():
    m=M()
    def boom(call):
        def act(host,name,detail):
            if name==call and detail[0]==tok.TOKEN_PATH:raise RuntimeError('injected')
            return False
        return act
    docs,host,before,receipt=run(hook=once(boom('write')))
    assert receipt['code']=='TOKEN_PLACEMENT_FAILED' and receipt['token_file']['state']=='WITHDRAWN' and receipt['mutating_calls']['uncertain']==1
    assert receipt['status']==m.PARTIAL_STATUS and tok.token_node(host) is None
    docs,host,before,receipt=run(hook=once(boom('create')))
    assert (receipt['status'],receipt['code'],receipt['token_file']['state'],receipt['objects_left_by_this_run'])==(m.PARTIAL_STATUS,'TOKEN_CREATE_UNCERTAIN','CREATE_UNCERTAIN',None)
    def write_then_unlink(host,name,detail):
        if name=='write' and detail[0]==tok.TOKEN_PATH:raise OSError(errno.ENOSPC,'full')
        if name=='unlink':raise RuntimeError('injected')
    docs,host,before,receipt=run(hook=always(write_then_unlink));row=receipt['token_file']
    assert (row['state'],row['withdrawal_code'])==('LEFT_UNVERIFIED','TOKEN_WITHDRAWAL_UNCERTAIN') and receipt['mutating_calls']['uncertain']==1

def test_the_death_of_the_process_after_the_creation_is_never_a_refusal():
    m=M()
    def die(host,name,detail):
        if name=='write':raise hostemu.Death()
    docs,host,before,receipt=run(hook=always(die))
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==(m.PARTIAL_STATUS,m.ESCAPED_OUTCOME,'RUN_ESCAPED_STATE_UNKNOWN','ESCAPED')


# ---------------------------------------------------------------- the parser of the environment file, rule by rule
def parse(raw):
    """The value and newline a file yields, or the constant code of its refusal (never anything of the bytes)."""
    m=M()
    try:found=m.token_definitions(raw);content=m.token_content(raw,found)
    except m.Refused as error:
        assert error.args==(str(error),) and re.fullmatch('[A-Z][A-Z0-9_]+',str(error)) and error.__cause__ is None and error.__context__ is None
        text=repr(error)+str(error)+repr(error.args);assert not tok.leaks(text) and tok.LITERAL not in text
        return str(error)
    assert type(content) is bytearray;return bytes(content)

T=tok.TOKEN.encode();L=tok.LITERAL.encode();GOOD=T+b'\n'
ACCEPTED_FILES=[
    ('plain',b'MASSIVE_API_TOKEN='+T+b'\n'),
    ('no_final_newline',b'MASSIVE_API_TOKEN='+T),
    ('the_literal_fake_value',None),
    ('c3po_name',b'C3PO_MASSIVE_API_TOKEN='+T+b'\n'),
    ('both_names_equal',b'MASSIVE_API_TOKEN='+T+b'\nC3PO_MASSIVE_API_TOKEN='+T+b'\n'),
    ('twice_equal',b'MASSIVE_API_TOKEN='+T+b'\nX=1\nMASSIVE_API_TOKEN='+T+b'\n'),
    ('every_other_form_of_other_names',b'# a comment\n\n  \t\n   # indented comment with \xc3\xa9 and \xe2\x80\x9cquotes\xe2\x80\x9d\n'
        b'OTHER="quoted value # not a comment $NOT"\nOTHER2=\'single $x "y"\'\nexport OTHER3=1\nOTHER4: yaml style\n  OTHER5 = spaced  # comment\n'
        b'INHERITED\nexport INHERITED2\nOTHER6=value with spaces # and a comment\nOTHER7=S\xc3\xa3o Paulo\nOTHER8=\nOTHER9="" \nOTHER.A-B[0]=x\n'
        b'OTHER10="a" # c\nOTHER11=\'b\'\t\nexport\tOTHER12=1\nexport=1\nexportOTHER=1\nOTHER13=\'"\'\n'
        b'MASSIVE_API_TOKEN='+T+b'\n#MASSIVE_API_TOKEN=commented-out-value\n  # MASSIVE_API_TOKEN=x\n'),
    ('names_that_only_contain_the_name',b'MASSIVE_API_TOKEN_OLD=FaKeOlDvAlUeFoRtEsTs\nOLD_MASSIVE_API_TOKEN=x\nMASSIVE_API_TOKEN2=y\nMASSIVE.API.TOKEN=z\n'
        b'MASSIVE_API_TOKEN='+T+b'\nC3PO_MASSIVE_API_TOKEN_X=w\n'),
    ('sixteen_characters',None),('five_hundred_and_twelve_characters',None),('every_character_of_the_grammar',None),
]
@pytest.mark.parametrize('name,raw',ACCEPTED_FILES,ids=[row[0] for row in ACCEPTED_FILES])
def test_files_the_parser_accepts(name,raw):
    if name=='the_literal_fake_value':assert parse(b'MASSIVE_API_TOKEN='+L+b'\n')==L+b'\n';return
    if name=='sixteen_characters':assert parse(b'MASSIVE_API_TOKEN='+b'Ab'*8)==b'Ab'*8+b'\n';return
    if name=='five_hundred_and_twelve_characters':assert parse(b'MASSIVE_API_TOKEN='+b'Ab'*256+b'\n')==b'Ab'*256+b'\n';return
    if name=='every_character_of_the_grammar':
        value=b'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._~+/=-'
        assert parse(b'C3PO_MASSIVE_API_TOKEN='+value+b'\n')==value+b'\n';return
    assert parse(raw)==GOOD

REFUSED_FILES=[
    # the file
    ('carriage_return_line_ends',b'MASSIVE_API_TOKEN='+T+b'\r\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('carriage_return_elsewhere',b'A=1\r\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('nul_byte',b'A=\x00\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('byte_order_mark',b'\xef\xbb\xbfMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('no_break_space_before_a_name',b'\xc2\xa0A=1\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('vertical_tab_before_a_name',b'\x0bA=1\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('form_feed_line',b'\x0c\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('non_ascii_name',b'CAF\xc3\x89=1\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('name_with_a_space',b'FOO BAR=1\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('a_line_of_punctuation',b'!!!\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('a_quoted_line',b'"A=1"\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('quoted_value_over_two_lines_hiding_a_definition',b'MASSIVE_API_TOKEN='+T+b'\nOTHER="abc\nMASSIVE_API_TOKEN=FaKeHiDdEnVaLuEfOrTeStS\n"\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('single_quoted_value_over_two_lines',b"OTHER='abc\ndef'\nMASSIVE_API_TOKEN="+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('quoted_value_with_a_backslash',b'OTHER="a\\"b"\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('quoted_value_ending_in_a_backslash',b'OTHER="ab\\\\"\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('a_statement_after_a_closing_quote',b'OTHER="x" MASSIVE_API_TOKEN=FaKeHiDdEnVaLuEfOrTeStS\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('text_after_a_closing_quote',b"OTHER='x'y\nMASSIVE_API_TOKEN="+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('value_beginning_with_a_vertical_tab',b'OTHER=\x0b"a\nb"\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('value_beginning_with_a_form_feed',b'OTHER=\x0cx\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('unquoted_value_beginning_with_a_vertical_tab',b'OTHER=\x0bx\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('unclosed_quote_alone',b'OTHER="\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('unclosed_quote_with_a_comment_sign',b'OTHER=\'#x\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('value_beginning_with_a_no_break_space_and_a_quote',b'OTHER=\xc2\xa0"a\nMASSIVE_API_TOKEN=FaKeHiDdEnVaLuEfOrTeStS\n"\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('value_beginning_with_another_non_ascii_byte',b'OTHER=\xe3\x80\x80x\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    # a definition that is not the plain form
    ('export',b'export MASSIVE_API_TOKEN='+T+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    ('export_with_a_tab',b'export\tC3PO_MASSIVE_API_TOKEN='+T+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    ('leading_space',b' MASSIVE_API_TOKEN='+T+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    ('leading_tab',b'\tMASSIVE_API_TOKEN='+T+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    ('space_before_the_sign',b'MASSIVE_API_TOKEN ='+T+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    ('space_after_the_sign',b'MASSIVE_API_TOKEN= '+T+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    ('tab_after_the_sign',b'MASSIVE_API_TOKEN=\t'+T+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    ('colon',b'MASSIVE_API_TOKEN: '+T+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    ('colon_without_space',b'MASSIVE_API_TOKEN:'+T+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    ('lower_case',b'massive_api_token='+T+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    ('mixed_case',b'MASSIVE_API_TOKEN='+T+b'\nMassive_Api_Token='+T+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    ('lower_case_c3po',b'MASSIVE_API_TOKEN='+T+b'\nc3po_massive_api_token='+T+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    ('taken_from_the_environment_of_compose',b'MASSIVE_API_TOKEN\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    ('export_taken_from_the_environment',b'MASSIVE_API_TOKEN='+T+b'\nexport C3PO_MASSIVE_API_TOKEN\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    # no definition
    ('empty_file',b'','ENV_TOKEN_ABSENT'),
    ('only_other_names',b'C3PO_DB_PASSWORD=x\nEODHD_API_TOKEN=y\n','ENV_TOKEN_ABSENT'),
    ('commented_out',b'# MASSIVE_API_TOKEN='+T+b'\n#C3PO_MASSIVE_API_TOKEN='+T+b'\n','ENV_TOKEN_ABSENT'),
    # definitions that disagree
    ('two_names_two_values',b'MASSIVE_API_TOKEN='+T+b'\nC3PO_MASSIVE_API_TOKEN=FaKeOtHeRvAlUeFoRtEsTs\n','ENV_TOKEN_DEFINITIONS_DISAGREE'),
    ('one_name_twice_two_values',b'MASSIVE_API_TOKEN=FaKeOtHeRvAlUeFoRtEsTs\nMASSIVE_API_TOKEN='+T+b'\n','ENV_TOKEN_DEFINITIONS_DISAGREE'),
    ('third_definition_disagrees',b'MASSIVE_API_TOKEN='+T+b'\nC3PO_MASSIVE_API_TOKEN='+T+b'\nMASSIVE_API_TOKEN=FaKeOtHeRvAlUeFoRtEsTs\n','ENV_TOKEN_DEFINITIONS_DISAGREE'),
    ('one_value_a_prefix_of_the_other',b'MASSIVE_API_TOKEN='+T+b'\nC3PO_MASSIVE_API_TOKEN='+T+b'x\n','ENV_TOKEN_DEFINITIONS_DISAGREE'),
    ('one_letter_of_another_case',b'MASSIVE_API_TOKEN='+T+b'\nC3PO_MASSIVE_API_TOKEN='+T.swapcase()+b'\n','ENV_TOKEN_DEFINITIONS_DISAGREE'),
    ('an_empty_and_a_good_one',b'MASSIVE_API_TOKEN=\nC3PO_MASSIVE_API_TOKEN='+T+b'\n','ENV_TOKEN_DEFINITIONS_DISAGREE'),
    # the value
    ('empty_value',b'MASSIVE_API_TOKEN=\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('fifteen_characters',b'MASSIVE_API_TOKEN='+b'Ab'*7+b'A\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('five_hundred_and_thirteen_characters',b'MASSIVE_API_TOKEN='+b'Ab'*256+b'A\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('double_quoted',b'MASSIVE_API_TOKEN="'+T+b'"\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('single_quoted',b"MASSIVE_API_TOKEN='"+T+b"'\n",'ENV_TOKEN_VALUE_GRAMMAR'),
    ('trailing_space',b'MASSIVE_API_TOKEN='+T+b' \n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('trailing_tab',b'MASSIVE_API_TOKEN='+T+b'\t\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('inline_comment',b'MASSIVE_API_TOKEN='+T+b' # the token\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('a_hash_inside',b'MASSIVE_API_TOKEN='+T+b'#x\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('a_variable',b'MASSIVE_API_TOKEN=$OTHER_VALUE_FOR_TESTS\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('a_braced_variable',b'MASSIVE_API_TOKEN='+T+b'${X}\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('a_backslash',b'MASSIVE_API_TOKEN='+T+b'\\n\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('a_space_inside',b'MASSIVE_API_TOKEN=FaKe ToKeNfOrTeStSoNlY\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('a_non_ascii_letter',b'MASSIVE_API_TOKEN='+T+b'\xc3\xa9\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('a_quote_inside',b'MASSIVE_API_TOKEN='+T+b'"x\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('an_at_sign',b'MASSIVE_API_TOKEN='+T+b'@x\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('a_comma',b'MASSIVE_API_TOKEN='+T+b',x\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('a_colon',b'MASSIVE_API_TOKEN='+T+b':x\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('a_semicolon',b'MASSIVE_API_TOKEN='+T+b';x\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('a_backtick',b'MASSIVE_API_TOKEN='+T+b'`x`\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('the_literal_fake_value_quoted',b'MASSIVE_API_TOKEN="'+L+b'"\n','ENV_TOKEN_VALUE_GRAMMAR'),
]
@pytest.mark.parametrize('name,raw,code',REFUSED_FILES,ids=[row[0] for row in REFUSED_FILES])
def test_files_the_parser_refuses_with_a_constant_code(name,raw,code):
    assert parse(raw)==code

def test_the_first_line_outside_the_rules_decides_and_every_line_is_judged():
    assert parse(b'export MASSIVE_API_TOKEN='+T+b'\n\r\n')=='ENV_FILE_SYNTAX_UNSUPPORTED'          # the whole file first
    assert parse(b'export MASSIVE_API_TOKEN='+T+b'\n!!!\n')=='ENV_TOKEN_DEFINITION_NOT_PLAIN'
    assert parse(b'!!!\nexport MASSIVE_API_TOKEN='+T+b'\n')=='ENV_FILE_SYNTAX_UNSUPPORTED'
    assert parse(b'MASSIVE_API_TOKEN='+T+b'\n'+b'#\n'*100+b'!!!')=='ENV_FILE_SYNTAX_UNSUPPORTED'      # a bad last line without newline

def test_offsets_are_those_of_the_value_and_nothing_else_leaves_the_parser():
    m=M();raw=b'# x\nA=1\nMASSIVE_API_TOKEN='+T+b'\nC3PO_MASSIVE_API_TOKEN='+T
    found=m.token_definitions(raw)
    assert [(name,raw[start:end]) for name,start,end in found]==[('MASSIVE_API_TOKEN',T),('C3PO_MASSIVE_API_TOKEN',T)]
    assert all(type(start) is int and type(end) is int for _,start,end in found)
    first=m.token_content(raw,found);second=m.token_content(raw,found)
    assert first==second==bytearray(GOOD) and first is not second
    m.zero(first);assert first==bytearray(len(GOOD)) and second==bytearray(GOOD)
    m.zero(b'immutable');m.zero(None)                                # only a bytearray is touched


# ---------------------------------------------------------------- the signed plan
def plan_refusal(changes,now=None):
    k,host=tok.world();docs=f.Docs(k,dict(tok.fields(host),**changes),now=now or tok.NOW)
    code=f.refusal(docs.authenticate);result=docs.run(f.Untouchable())
    assert (result['status'],result['code'],result['phase_reached'])==('REFUSED',code,'AUTHENTICATION')
    return code

def test_the_plan_is_refused_before_the_claim():
    k,host=tok.world();rows=tok.fields(host)['config_chain']
    def row(**change):return rows[:-1]+[dict(rows[-1],**change)]
    assert plan_refusal({'config_chain':row(mode=0o755)})=='CONFIG_DIRECTORY_NOT_ROOT_0700'
    assert plan_refusal({'config_chain':row(mode=0o750)})=='CONFIG_DIRECTORY_NOT_ROOT_0700'
    assert plan_refusal({'config_chain':row(gid=1000)})=='CONFIG_DIRECTORY_NOT_ROOT_0700'
    assert plan_refusal({'config_chain':row(mode=0o2700)})=='PARENT_SETGID'
    assert plan_refusal({'config_chain':row(uid=1000)})=='CHAIN_ROW_UNSAFE'
    assert plan_refusal({'config_chain':row(mode=0o770)})=='CHAIN_ROW_UNSAFE'
    assert plan_refusal({'config_chain':rows[:-1]})=='CHAIN_ROW_INVALID'
    assert plan_refusal({'config_chain':tok.hostemu.rows(host,'/etc/c3po-bar/manifests')})=='CHAIN_ROW_INVALID'
    assert plan_refusal({'config_chain':rows[:1]+[dict(rows[1],mode=0o777)]+rows[2:]})=='CHAIN_ROW_UNSAFE'
    for value in (None,'relative/deploy','/','/etc','/etc/c3po-bar','/etc/c3po-bar/sub','/opt/../etc','/opt/x/','//opt',5,'/opt/a b'):
        assert plan_refusal({'deploy_directory':value})=='DEPLOY_DIRECTORY_INVALID',value
    for value in (None,'0'*64,'A'*64,'a'*63):assert plan_refusal({'evidence_boot_id_sha256':value})=='EVIDENCE_BOOT_UNBOUND'
    assert plan_refusal({},now=tok.NOW.replace(day=2))=='WINDOW_NOT_ON_A_TOKEN_DAY'
    for value in ('/etc/c3po','/etc/c3po-bar2','/opt/chief-of-staff-digital'):
        k,host=tok.world();f.Docs(k,dict(tok.fields(host),deploy_directory=value),now=tok.NOW).authenticate()

def test_effects_are_exactly_what_the_signers_must_see():
    m=M();docs,host=tok.case();rows=tok.fields(host)['config_chain']
    assert docs.go['effects']=={'operation':'GO_WRITE_HOSTOPS02_TOKEN_FROM_ENV_01',
        'config_directory':{'path':'/etc/c3po-bar','row':rows[-1],'chain_sha256':f.sha(f.canonical(rows)),'mount_point_by_device_change':'/',
                            'required':{'uid':0,'gid':0,'mode_octal':'0700'}},
        'token_file':{'path':'/etc/c3po-bar/token','expect':'ABSENT','uid':0,'gid':0,'mode_octal':'0600','links':1,
                      'content':'the value of the environment file, then one newline','size':'within 1-4096 (a boolean, never the size)'},
        'environment_file':{'path':'/opt/chief-of-staff-digital/.env','deploy_directory':'/opt/chief-of-staff-digital','keys':['C3PO_MASSIVE_API_TOKEN','MASSIVE_API_TOKEN'],
                            'value_grammar':'[A-Za-z0-9._~+/=-]{16,512}','chain':'walked by this run, not signed'},
        'token_days':['2026-10-03','2026-10-04'],'evidence_boot_id_sha256':f.BOOT_SHA,
        'pre_existing_objects_modified':False,'process_started':False,'activation':False,'value_in_receipt':False}
    assert (m.WRITES_ALLOWED,m.ACTIVATION_ALLOWED)==(True,False) and docs.request['activation_allowed'] is False

def test_effects_carry_what_the_signers_must_see():
    m=M();docs,host=tok.case();effects=docs.go['effects']
    assert effects['token_file']['path']=='/etc/c3po-bar/token' and effects['token_file']['expect']=='ABSENT' and effects['token_file']['mode_octal']=='0600'
    assert effects['environment_file']['path']=='/opt/chief-of-staff-digital/.env' and effects['environment_file']['keys']==['C3PO_MASSIVE_API_TOKEN','MASSIVE_API_TOKEN']
    assert effects['config_directory']['row']==tok.fields(host)['config_chain'][-1] and effects['config_directory']['required']=={'uid':0,'gid':0,'mode_octal':'0700'}
    assert effects['config_directory']['chain_sha256']==f.sha(f.canonical(tok.fields(host)['config_chain']))
    assert effects['token_days']==['2026-10-03','2026-10-04'] and effects['evidence_boot_id_sha256']==f.BOOT_SHA
    assert effects['value_in_receipt'] is False and effects['process_started'] is False and effects['activation'] is False and effects['pre_existing_objects_modified'] is False
    other=m.effects_of(dict(docs.plan,deploy_directory='/srv/deploy'));assert other['environment_file']['path']=='/srv/deploy/.env' and other!=effects


# ---------------------------------------------------------------- the receipt: codes, booleans and identity rows only
ROW_KEYS={'path','state','code','errno','created','fsync_file','fsync_directory','device','inode','regular','uid_0','gid_0','mode_0600','single_link',
          'size_within_1_4096','on_the_device_of_the_directory','readback_same_inode','readback_bytes_equal_what_was_written','meets_the_supervisor_file_rules',
          'withdrawn','withdrawal_code','withdrawal_errno','fsync_directory_after_withdrawal'}
def test_the_receipt_holds_codes_booleans_and_identity_rows_only():
    m=M();docs,host,before,receipt=run()
    assert set(receipt)=={'schema','operation','status','outcome','code','scope_sha256','core_sha256','activation_performed','daemon_reload_performed',
                          'secret_bytes_in_receipt','ready','request_sha256','authority_sha256','go_sha256','payload_sha256','host_binding_sha256',
                          'observed_at','effects','clock','mutating_calls','config_directory','deploy_chain','environment_file','precheck','token_file',
                          'objects_left_by_this_run','pre_existing_objects_modified','phase_reached','readback','size_reductions','metadata_sha256'}
    row=receipt['token_file'];assert set(row)==ROW_KEYS==set(m.token_row()) and row['state'] in m.TOKEN_STATES
    for key,value in row.items():
        if key in ('device','inode','errno','withdrawal_errno'):assert value is None or type(value) is int
        elif key in ('path','state','code','withdrawal_code'):assert value is None or (type(value) is str and re.fullmatch('[A-Z0-9_]+|/etc/c3po-bar/token',value))
        else:assert type(value) is bool or value is None,key
    def flat(value):
        if type(value) is dict:return [item for inner in value.values() for item in flat(inner)]
        return [value]
    assert all(type(value) is bool or value is None for value in flat(receipt['environment_file'])+flat(receipt['deploy_chain']))
    assert set(receipt['environment_file'])==set(m.environment_facts()) and set(receipt['deploy_chain'])==set(m.chain_facts())
    words=json.dumps({key:value for key,value in receipt.items() if key!='effects'})
    for word in ('length','line_count','lines','value_sha256','"bytes"','"size"'):assert word not in words

def test_a_receipt_that_exceeds_the_limit_keeps_the_record_of_mutating_calls():
    m=M();receipt={'status':m.COMPLETE_STATUS,'config_directory':{'rows':[{'pad':'x'*70000}]},'mutating_calls':{'issued':2}}
    sealed=m.seal(receipt)
    assert sealed['size_reductions']==['CONFIG_ROWS_REDUCED_TO_COUNT'] and sealed['config_directory']=={'rows_reduced_for_size':1}
    assert sealed['status']==m.PARTIAL_STATUS and sealed['outcome']==m.REDUCED_OUTCOME and sealed['mutating_calls']=={'issued':2}


# ---------------------------------------------------------------- what the source never does
def test_static_the_operation_part_reads_no_environment_and_starts_nothing():
    own=(tok.DIRECTORY/'op.py').read_text()
    for word in (r'\benviron\b','getenv','putenv','subprocess','Popen','socket','docker inspect','docker exec',r'\bexec\b'):assert not re.search(word,own),word
    m=M();assert [name for name in dir(m.Native) if not name.startswith('_')]==sorted(['identity','noatime','open','close','fstat','lstat','fstatvfs','read','names',
                                                                                      'umask','mkdir','create','write','fsync','link','unlink'])
    assert 'runner' not in f.assembler().load_spec(tok.DIRECTORY).PARTS and not hasattr(m,'COMMANDS')
