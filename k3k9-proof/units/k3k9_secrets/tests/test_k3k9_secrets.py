"""K3-K9 on the emulated host: the complete run, every refusal before the first creation (nothing changed, no mutating
call), every failure after it (the withdrawal by identity, or what is left and why), the worker and its environment,
the two files of September, the signed plan, and the receipt (codes, booleans and identity rows only). On every path
that reaches the host the first call is the core's not_dumpable(); the docker commands run before any file of September
is opened; no value, line, content, digest or encoding of a secret reaches a receipt, an argv, an environment or a log
text, and the receipt does not depend on the values or their lengths."""
import errno
import json
import os
import re

import pytest

import family as f
import hostemu
import k3

M=k3.m

class Before:
    """A change of the host made before the receipts were read: the signed rows already show it."""
    def __init__(self,action):self.action=action
    def __call__(self,host):return self.action(host)

def run(prepare=None,hook=None,now=None,minutes=5,clock=None,fields=None,docs_hook=None,**world):
    """One run on a fresh emulated host. prepare(host) changes the host before the run (as it would be found);
    hook(host,name,detail,calls) acts during it. Returns (docs, host, snapshot before, receipt)."""
    k,host=k3.world(**world)
    if isinstance(prepare,Before):prepare(host);prepare=None      # the host as the receipts already saw it
    signed=dict(k3.fields(host),**(fields or {}))         # what a binder copied from the receipts, before the host changed
    if prepare is not None:prepare(host)
    docs=f.Docs(k,signed,now=now or k3.NOW,minutes=minutes)
    if docs_hook is not None:docs_hook(docs)
    before=k3.state_of(host);host.hook=hook
    options={} if clock is None else {'clock':clock}
    receipt=docs.run(host,**options)
    assert f.sealed(receipt) and type(receipt) is dict
    assert k3.leaks(k3.line(receipt))==[] and k3.leaks(k3.outside_view(host))==[]
    first_of_all(host,receipt)
    return docs,host,before,receipt

SOURCES=None
def source_access(entry):
    """True for a call of the emulated host that touches a file of September or its directory."""
    m=M();return any(type(item) is str and (item.startswith(m.RISK_URL_DIRECTORY) or item.startswith(m.EMITTER_SOURCE_DIRECTORY)
                                            or item==k3.DATA+'/.c3po-role-executor-20260908-r2') for item in entry[1:2])
def first_of_all(host,receipt):
    """On every path that reaches the host: the process is made non-dumpable by the first call of the run, once, before
    anything else; every docker command comes before the first touch of a file of September."""
    names=[entry[0] for entry in host.log]
    if not names:
        assert receipt['phase_reached'] in ('AUTHENTICATION','BEFORE_ANY_EFFECT') and 'process' not in receipt;return
    assert names[0]=='not_dumpable' and names.count('not_dumpable')>=1,names[:3]
    touched=[index for index,entry in enumerate(host.log) if source_access(entry)]
    runs=[index for index,entry in enumerate(host.log) if entry[0]=='run']
    assert not touched or not runs or max(runs)<min(touched),'a docker command after a file of September was opened'
    if 'process' in receipt:assert receipt['process']=={'dumpable_disabled':host.dumpable==0}
    else:assert receipt['phase_reached'] in ('ESCAPED','BEFORE_ANY_EFFECT')

def refused(receipt,code):
    m=M()
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('REFUSED',m.REFUSED_OUTCOME,code),(receipt['code'],code)
    assert receipt['mutating_calls']['succeeded']==0 and receipt['mutating_calls']['uncertain']==0
def partial(receipt,code):
    m=M();assert (receipt['status'],receipt['outcome'],receipt['code'])==('PARTIAL_METADATA_REQUIRES_REVIEW',m.PARTIAL_OUTCOME,code),(receipt['code'],code)
def nothing_changed(host,before):
    assert k3.state_of(host)==before and [entry for entry in host.mutating() if entry[0] not in ('create','mkdir')]==[]
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
def paths():m=M();return m.TARGET_PATHS
def secrets(host):return host.tree.get(M().K9_SECRETS_DIRECTORY)


# ---------------------------------------------------------------- the complete run
def test_complete_run_places_the_three_files_and_reads_them_back_by_descriptor():
    m=M();docs,host,before,receipt=run()
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.COMPLETE_STATUS,'K9_SECRETS_PLACED_METADATA_VERIFIED',None)
    contents=(k3.provider_content(),k3.risk_content(),k3.PASSWORD.encode())
    for path,content in zip(paths(),contents):
        node=k3.node(host,path);assert (node.kind,node.uid,node.gid,node.mode,node.nlink,bytes(node.content))==('file',0,0,0o600,1,content) and node.synced,path
    emitter=k3.node(host,m.K9_EMITTER_DIRECTORY);assert (emitter.kind,emitter.uid,emitter.gid,emitter.mode,sorted(emitter.children))==('dir',0,0,0o700,['password'])
    assert sorted(secrets(host).children)==['emitter','provider.env','risk-db.env']
    assert bytes(k3.node(host,paths()[0]).content)==b'C3PO_EODHD_API_TOKEN=%s\nC3PO_FINNHUB_API_TOKEN=%s\nC3PO_FMP_API_TOKEN=%s\n'%tuple(
        k3.TOKENS[name].encode() for name in ('C3PO_EODHD_API_TOKEN','C3PO_FINNHUB_API_TOKEN','C3PO_FMP_API_TOKEN'))
    for key,path in zip(m.FILE_ROWS,paths()):
        row=receipt['files'][key];node=k3.node(host,path)
        assert row['state']=='PLACED_VERIFIED' and row['code'] is None and row['created'] is True and row['path']==path
        for name in ('fsync_file','fsync_directory','regular','uid_0','gid_0','mode_0600','single_link','on_the_device_of_the_directory',
                     'readback_same_inode','readback_metadata_as_created'):assert row[name] is True,(key,name)
        assert (row['device'],row['inode'])==(node.dev,node.ino) and row['withdrawn'] is False and row['withdrawal_code'] is None
        assert not [name for name in row if 'size' in name or 'byte' in name or 'length' in name or 'sha' in name]
    assert receipt['emitter_directory']['state']=='CREATED_DURABLE' and receipt['emitter_directory']['observed']['entries']==0
    assert receipt['directory_readbacks']=={'secrets_directory':None,'emitter_directory':None} and receipt['readback']=='COMPLETE'
    assert receipt['mutating_calls']=={'issued':7,'succeeded':7,'failed_nothing_changed':0,'uncertain':0} and receipt['objects_left_by_this_run']==4
    assert receipt['commands_started']=={'READ':2,'CONTAINER':0,'EFFECT':0} and receipt['precheck']=={'seconds_left_before_the_first_effect':60}
    assert receipt['worker']=={'one_container_with_the_name':True,'id_equal_signed':True,'running':True,'read_twice_equal':True,'grammar_met':True,
                               'names_present':{'C3PO_EODHD_API_TOKEN':False,'C3PO_FINNHUB_API_TOKEN':False,'C3PO_FMP_API_TOKEN':False,
                                                'EODHD_API_TOKEN':True,'FINNHUB_API_TOKEN':True,'FMP_API_TOKEN':True}}
    for key in ('risk_url_source','emitter_password_source'):assert all(value is True for value in receipt[key].values()),key
    assert receipt['secrets_directory']=={'rows':k3.fields(host)['secrets_chain'],'pinned':True,'empty':True}
    assert receipt['process']=={'dumpable_disabled':True} and host.dumpable==0 and host.log[0]==('not_dumpable',)
    assert receipt['pre_existing_objects_modified'] is False and receipt['activation_performed'] is False and receipt['secret_bytes_in_receipt'] is False
    # only the three files and the directory were made, and nothing but mkdir, the creates and the writes
    assert [entry[0] for entry in host.mutating()]==['mkdir','create','write','create','write','create','write']
    for path in reversed(paths()):host.tree.remove(path)
    host.tree.remove(m.K9_EMITTER_DIRECTORY);assert k3.state_of(host)==before

def test_the_only_subprocess_reads_are_two_lists_no_inspect_or_env():
    m=M();docs,host,before,receipt=run()
    assert [e['argv'][1:] for e in host.commands]==[['ps','-a','--no-trunc','--format',m.PS_FORMAT]]*2
    assert sorted(m.COMMANDS)==['container_list']
    assert 'Env' not in m.PS_FORMAT
    assert not any('inspect' in e['argv'] for e in host.commands)
    opened=[e for e in host.log if e[0]=='open' and e[1].endswith('/config.v2.json')]
    assert len(opened)==2
    assert receipt['process']['dumpable_disabled'] is True

def test_the_order_of_the_run_on_the_host():
    """not_dumpable, identity, umask, boot, the secrets directory walked and listed, the docker commands, the files of
    September, the directory proved again, then mkdir, and each file: create, write, fsync, fstat, fsync of the
    directory, the readback open of the name; the two directories read back last."""
    m=M();docs,host,before,receipt=run();names=[entry[0] for entry in host.log]
    assert names[:2]==['not_dumpable','umask'] and host.log[1]==('umask',0o077)
    first_open=[entry for entry in host.log if entry[0]=='open'][0];assert first_open[1]=='/'
    risk=[index for index,entry in enumerate(host.log) if entry[0]=='open' and entry[1]==m.RISK_URL_DIRECTORY+'/'+m.RISK_URL_NAME]
    password=[index for index,entry in enumerate(host.log) if entry[0]=='open' and entry[1]==m.EMITTER_SOURCE_DIRECTORY+'/'+m.EMITTER_SOURCE_NAME]
    runs=[index for index,entry in enumerate(host.log) if entry[0]=='run'];mkdir=names.index('mkdir')
    assert len(risk)==1 and len(password)==1 and max(runs)<risk[0]<password[0]<mkdir
    creates=[entry for entry in host.log if entry[0]=='create']
    assert [entry[1:] for entry in creates]==[(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600) for path in paths()]
    for path in paths():
        own=[entry[0] for entry in host.log if entry[1:2]==(path,)]
        assert own==['create','write','fsync','fstat','open','fstat','lstat'][:len(own)] and own[:6]==['create','write','fsync','fstat','open','fstat'],(path,own)
    readback=[entry for entry in host.log if entry[0]=='open' and entry[1] in paths()]
    assert [entry[1:] for entry in readback]==[(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|hostemu.NOATIME) for path in paths()]
    assert not [entry for entry in host.log if entry[0]=='read' and entry[1] in paths()],'the content of a placed file is never read back'
    assert [entry[1] for entry in host.log if entry[0]=='fsync']==[m.K9_EMITTER_DIRECTORY,m.K9_SECRETS_DIRECTORY,paths()[0],m.K9_SECRETS_DIRECTORY,
                                                                  paths()[1],m.K9_SECRETS_DIRECTORY,paths()[2],m.K9_EMITTER_DIRECTORY]
    assert host.fds=={}

def test_every_buffer_that_held_a_value_is_zeroed_and_the_writes_came_from_them():
    m=M();k,host=k3.world();docs=f.Docs(k,k3.fields(host),now=k3.NOW);seen=[];real=m.token_values
    def spy(*arguments,**options):
        values=real(*arguments,**options);seen.append(values);return values
    m.token_values=spy
    try:receipt=docs.run(host)
    finally:m.token_values=real
    assert receipt['status']==m.COMPLETE_STATUS and len(seen)==2 and len(host.written_from)==3
    for values in seen:assert sorted(values)==['EODHD_API_TOKEN','FINNHUB_API_TOKEN','FMP_API_TOKEN'] and all(type(value) is bytearray and value and set(value)=={0} for value in values.values())
    assert all(type(buffer) is bytearray and buffer and set(buffer)=={0} for buffer in host.written_from)
    # and on a refusal after the values were read: the budget
    k,host=k3.world();docs=f.Docs(k,k3.fields(host),now=k3.NOW);seen.clear();m.token_values=spy
    budget=f.Budget(k3.NOW).attach(host).cost(24,'ps')
    try:receipt=docs.run(host,**budget.options())
    finally:m.token_values=real
    assert receipt['code']=='BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT' and len(seen)==2 and all(set(value)=={0} for values in seen for value in values.values())

def test_the_receipt_does_not_depend_on_the_values_or_their_lengths():
    """Two runs that differ only in the secrets (other values, other lengths, other first bytes): the receipts are the
    same bytes, whatever the outcome. So no value, digest, length or size of one can be in a receipt."""
    other=dict(tokens=k3.LONGER,url_file=(k3.url(k3.LONGER_URL_PASSWORD)+'\n').encode(),password_file=k3.OTHER_PASSWORD.encode())
    def same(first,second,prepare=None,hook=None):
        out=[]
        for options in (first,second):
            docs,host,before,receipt=run(prepare,hook() if hook else None,**options);out.append(k3.line(receipt))
        assert out[0]==out[1];return json.loads(out[0])
    m=M()
    assert same({},other)['status']==m.COMPLETE_STATUS
    assert same({},other,hook=lambda:once(failing('write',paths()[1],OSError(errno.ENOSPC,'full'))))['files']['risk_db_env']['state']=='WITHDRAWN'
    assert same({},other,prepare=lambda host:host.tree.add(paths()[0],kind='file',mode=0o600,content=b'x'))['code']=='SECRETS_DIRECTORY_NOT_EMPTY'
    assert same({},dict(other,url_file=k3.url(k3.LONGER_URL_PASSWORD).encode()))['status']==m.COMPLETE_STATUS
    for one,two in (('x'*15,'y'*3),('FaKe ToKeN wItH sPaCeS','FaKe$ToKeNwItHdOlLaRaNdMoRe'),('x'*513,'z'*600)):
        tokens=dict(k3.TOKENS,C3PO_FMP_API_TOKEN=one);longer=dict(k3.LONGER,C3PO_FMP_API_TOKEN=two)
        assert same(dict(tokens=tokens),dict(other,tokens=longer))['code']=='PROVIDER_TOKEN_GRAMMAR'
    for one,two in ((k3.url(k3.URL_PASSWORD,'c3po')+'\n',k3.url(k3.LONGER_URL_PASSWORD,'postgres')+'\n'),):
        assert same(dict(url_file=one.encode()),dict(other,url_file=two.encode()))['code']=='RISK_DATABASE_URL_NOT_THE_RESTRICTED_READER'
    for one,two in ((k3.url()+' \n',k3.url(k3.LONGER_URL_PASSWORD)+'\n\n'),(k3.url()+'\r\n','mysql://'+k3.LONGER_URL_PASSWORD),('','x'*4097)):
        assert same(dict(url_file=one.encode()),dict(other,url_file=two.encode()))['code']=='RISK_URL_FORMAT'
    for one,two in ((k3.PASSWORD[:63],k3.OTHER_PASSWORD+'x'),(k3.PASSWORD+'\n',k3.OTHER_PASSWORD[:10]),(k3.PASSWORD[:63]+'.',k3.OTHER_PASSWORD[:1])):
        assert same(dict(password_file=one.encode()),dict(other,password_file=two.encode()))['code']=='EMITTER_PASSWORD_FORMAT'
    assert same(dict(extra_env=['FMP_API_TOKEN=%s'%k3.TOKENS['C3PO_FMP_API_TOKEN']]),dict(other,extra_env=['FMP_API_TOKEN=%s'%k3.LONGER['C3PO_FMP_API_TOKEN']]))['code']=='SECRET_ENVIRONMENT_REPEATED'
    assert same(dict(extra_env=['C3PO_FMP_API_TOKEN=x'+k3.TOKENS['C3PO_FMP_API_TOKEN']]),dict(other,extra_env=['C3PO_FMP_API_TOKEN=y'+k3.LONGER['C3PO_FMP_API_TOKEN'][:20]]))['code']=='PROVIDER_TOKEN_DEFINITIONS_DISAGREE'
    assert same(dict(names='both'),dict(other,names='both'))['status']==m.COMPLETE_STATUS and same(dict(names='prefixed'),dict(other,names='prefixed'))['status']==m.COMPLETE_STATUS
    for one,two in (('a"b'+k3.TOKENS['C3PO_FMP_API_TOKEN'],'\n'),('x'*4097,'y'*20+' '),('',k3.LONGER['C3PO_FMP_API_TOKEN'][:15]),('\u00e9'*20,'z'*513)):
        assert same(dict(tokens=dict(k3.TOKENS,C3PO_FMP_API_TOKEN=one)),dict(other,tokens=dict(k3.LONGER,C3PO_FMP_API_TOKEN=two)))['code']=='PROVIDER_TOKEN_GRAMMAR',(one[:5],two[:5])
    for one,two in (('x'*4097,''),(k3.url()+'x'*4096,k3.url()[:5]),('\n','a'*4097)):
        assert same(dict(url_file=one.encode()),dict(other,url_file=two.encode()))['code']=='RISK_URL_FORMAT'
    for one,two in (('x'*65,'y'*63),(k3.PASSWORD*2,''),(k3.PASSWORD+'\n','!'*64)):
        assert same(dict(password_file=one.encode()),dict(other,password_file=two.encode()))['code']=='EMITTER_PASSWORD_FORMAT'


# ---------------------------------------------------------------- refusals before the first creation: nothing changed
def add(path,**attributes):return lambda host:host.tree.add(path,**attributes)
def replace(path,**attributes):
    def act(host):host.tree.remove(path);host.tree.add(path,**attributes)
    return act
def set_node(path,**attributes):
    def act(host):
        node=host.tree.get(path)
        for key,value in attributes.items():setattr(node,key,value)
    return act
def worker_env(change):
    def act(host):
        env=host.docker.container(k3.WORKER)['Config']['Env'];env[:]=change(list(env))
    return act
def token(name,value):
    """The value of one token changed under whichever of its two names the worker holds."""
    pair=[item for item in M().PROVIDER_TOKEN_NAMES if name in item][0]
    return worker_env(lambda env:[item.split('=',1)[0]+'='+value if item.split('=',1)[0] in pair else item for item in env])
def m_attr(name):return getattr(M(),name)
RISK=lambda:m_attr('RISK_URL_DIRECTORY')+'/'+m_attr('RISK_URL_NAME')
PW=lambda:m_attr('EMITTER_SOURCE_DIRECTORY')+'/'+m_attr('EMITTER_SOURCE_NAME')
def content(path,raw):return lambda host:setattr(host.tree.get(path()),'content',bytearray(raw))
def mode(path,value,**more):return lambda host:set_node(path(),mode=value,**more)(host)

REFUSALS=[
    # the secrets directory
    ('secrets_directory_holds_a_file',lambda host:add(M().K9_SECRETS_DIRECTORY+'/provider.env',kind='file',mode=0o600,content=b'x')(host),'SECRETS_DIRECTORY_NOT_EMPTY'),
    ('secrets_directory_holds_emitter',lambda host:add(M().K9_EMITTER_DIRECTORY,mode=0o700)(host),'SECRETS_DIRECTORY_NOT_EMPTY'),
    ('secrets_directory_holds_a_link',lambda host:add(M().K9_SECRETS_DIRECTORY+'/risk-db.env',kind='symlink',mode=0o777,target='/etc/x')(host),'SECRETS_DIRECTORY_NOT_EMPTY'),
    ('secrets_directory_absent',lambda host:host.tree.remove(M().K9_SECRETS_DIRECTORY),'PARENT_MISSING'),
    ('secrets_directory_replaced',lambda host:replace(M().K9_SECRETS_DIRECTORY,uid=0,gid=0,mode=0o700)(host),'PARENT_IDENTITY_MISMATCH'),
    ('secrets_directory_mode_changed',lambda host:set_node(M().K9_SECRETS_DIRECTORY,mode=0o755)(host),'PARENT_IDENTITY_MISMATCH'),
    ('k9_root_is_a_link',lambda host:replace(M().K9_ROOT,kind='symlink',mode=0o777,target='/tmp')(host),'PARENT_SYMLINK_COMPONENT'),
    # the worker and its environment
    ('worker_absent',lambda host:host.docker.containers.remove(host.docker.container(k3.WORKER)),'WORKER_CONTAINER_MISMATCH'),
    ('worker_recreated_under_another_id',lambda host:host.docker.container(k3.WORKER).update(Id='6f'*32),'WORKER_CONTAINER_MISMATCH'),
    ('worker_stopped',lambda host:host.docker.container(k3.WORKER)['State'].update(Status='exited',Running=False),'WORKER_NOT_RUNNING'),
    ('worker_restarting',lambda host:host.docker.container(k3.WORKER)['State'].update(Status='restarting'),'WORKER_NOT_RUNNING'),
    ('worker_list_fails',lambda host:setattr(host.docker,'ps_returncode',1),'COMMAND_FAILED'),
    ('worker_config_unsafe',lambda host:set_node(M().DOCKER_CONTAINER_ROOT+'/'+k3.WORKER_ID+'/'+M().WORKER_CONFIG_NAME,mode=0o644)(host),'WORKER_CONFIG_METADATA_UNSAFE'),
    ('docker_absent',lambda host:host.absent.add('docker'),'COMMAND_NOT_STARTED'),
    ('docker_hangs',lambda host:host.hang.add(('ps',)),'COMMAND_TIMEOUT'),
    ('docker_binary_not_root_owned',lambda host:set_node('/usr/bin/docker',uid=1000)(host),'BINARY_UNAVAILABLE_OR_UNSAFE'),
    ('token_absent',worker_env(lambda env:[item for item in env if not item.startswith('FINNHUB_API_TOKEN=')]),'PROVIDER_TOKEN_ABSENT'),
    ('every_token_absent',worker_env(lambda env:[item for item in env if not item.split('=',1)[0].endswith('_API_TOKEN')]),'PROVIDER_TOKEN_ABSENT'),
    ('token_repeated',worker_env(lambda env:env+['EODHD_API_TOKEN=OtHeRvAlUeFoRtEsTs']),'SECRET_ENVIRONMENT_REPEATED'),
    ('token_under_both_names_disagreeing',worker_env(lambda env:env+['C3PO_FMP_API_TOKEN=OtHeRfMpVaLuEfOrTeStS']),'PROVIDER_TOKEN_DEFINITIONS_DISAGREE'),
    ('prefixed_name_empty_above_a_filled_one',worker_env(lambda env:env+['C3PO_EODHD_API_TOKEN=']),'PROVIDER_TOKEN_GRAMMAR'),
    ('prefixed_name_short_beside_a_filled_one',worker_env(lambda env:env+['C3PO_EODHD_API_TOKEN=abc']),'PROVIDER_TOKEN_GRAMMAR'),
    ('plain_name_short_beside_a_filled_prefixed_one',worker_env(lambda env:['C3PO_'+item if item.split('=',1)[0] in ('EODHD_API_TOKEN','FINNHUB_API_TOKEN','FMP_API_TOKEN') else item
                                                                             for item in env]+['EODHD_API_TOKEN=abc']),'PROVIDER_TOKEN_GRAMMAR'),
    ('token_empty',token('C3PO_FMP_API_TOKEN',''),'PROVIDER_TOKEN_GRAMMAR'),
    ('token_with_a_quote',token('C3PO_FMP_API_TOKEN','FmPcAnArY"fOrTeStS'),'PROVIDER_TOKEN_GRAMMAR'),
    ('token_with_a_newline',token('C3PO_FMP_API_TOKEN','FmPcAnArY\nC3PO_EODHD_API_TOKEN=x'),'PROVIDER_TOKEN_GRAMMAR'),
    ('token_over_4096_bytes',token('C3PO_FMP_API_TOKEN','Ab'*2049),'PROVIDER_TOKEN_GRAMMAR'),
    ('token_with_a_space',token('C3PO_FMP_API_TOKEN','FmPcAnArY fOrTeStS'),'PROVIDER_TOKEN_GRAMMAR'),
    ('token_too_short',token('C3PO_EODHD_API_TOKEN','EoDhDsHoRtToKeN'),'PROVIDER_TOKEN_GRAMMAR'),
    ('token_too_long',token('C3PO_EODHD_API_TOKEN','Ab'*256+'c'),'PROVIDER_TOKEN_GRAMMAR'),
    ('token_with_a_dollar',token('C3PO_FINNHUB_API_TOKEN','FiNnHuB$cAnArYfOrTeSt'),'PROVIDER_TOKEN_GRAMMAR'),
    # the database URL of the reader: the walk and the file against their signed rows, then the content
    ('risk_directory_absent',lambda host:host.tree.remove(M().RISK_URL_DIRECTORY+'/'+M().RISK_URL_NAME) or host.tree.remove(M().RISK_URL_DIRECTORY),'RISK_URL_COMPONENT_ABSENT'),
    ('risk_directory_is_a_link',lambda host:replace(M().RISK_URL_DIRECTORY,kind='symlink',mode=0o777,target='/etc')(host),'RISK_URL_COMPONENT_DIVERGES'),
    ('risk_directory_is_a_file',lambda host:replace(M().RISK_URL_DIRECTORY,kind='file',mode=0o600)(host),'RISK_URL_COMPONENT_DIVERGES'),
    ('risk_directory_replaced',lambda host:replace(M().RISK_URL_DIRECTORY,uid=1000,gid=1000,mode=0o700)(host),'RISK_URL_COMPONENT_DIVERGES'),
    ('risk_directory_mode_changed',lambda host:set_node(M().RISK_URL_DIRECTORY,mode=0o777)(host),'RISK_URL_COMPONENT_DIVERGES'),
    ('risk_directory_entries_changed',lambda host:set_node(M().RISK_URL_DIRECTORY,mtime=7)(host),'RISK_URL_COMPONENT_DIVERGES'),
    ('risk_directory_metadata_changed',lambda host:set_node(M().RISK_URL_DIRECTORY,ctime=7)(host),'RISK_URL_COMPONENT_DIVERGES'),
    ('risk_directory_on_another_device',lambda host:set_node(M().RISK_URL_DIRECTORY,dev=999)(host),'RISK_URL_COMPONENT_DIVERGES'),
    ('mnt_group_writable_after_the_signature',lambda host:set_node('/mnt',mode=0o775)(host),'RISK_URL_COMPONENT_DIVERGES'),
    ('data_volume_of_another_owner_after_the_signature',lambda host:set_node(k3.DATA,uid=1001)(host),'RISK_URL_COMPONENT_DIVERGES'),
    ('data_volume_replaced_after_the_signature',lambda host:set_node(k3.DATA,ino=99)(host),'RISK_URL_COMPONENT_DIVERGES'),
    ('var_lib_c3po_mode_changed_after_the_signature',lambda host:set_node('/var/lib/c3po',mode=0o755)(host),'PARENT_IDENTITY_MISMATCH'),
    ('var_lib_c3po_replaced_after_the_signature',lambda host:replace('/var/lib/c3po',uid=0,gid=0,mode=0o700)(host),'PARENT_IDENTITY_MISMATCH'),
    ('risk_file_absent',lambda host:host.tree.remove(RISK()),'RISK_URL_FILE_ABSENT'),
    ('risk_file_is_a_link',lambda host:replace(RISK(),kind='symlink',mode=0o777,target='/etc/hostname')(host),'RISK_URL_FILE_NOT_REGULAR'),
    ('risk_file_is_a_fifo',lambda host:replace(RISK(),kind='fifo',mode=0o600,uid=1000,gid=1000)(host),'RISK_URL_FILE_NOT_REGULAR'),
    ('risk_file_is_a_directory',lambda host:replace(RISK(),mode=0o700,uid=1000,gid=1000)(host),'RISK_URL_FILE_NOT_REGULAR'),
    ('risk_file_with_a_second_link',lambda host:set_node(RISK(),nlink=2)(host),'RISK_URL_FILE_LINKED'),
    ('risk_file_substituted',lambda host:replace(RISK(),kind='file',uid=1000,gid=1000,mode=0o600,content=(k3.url(k3.LONGER_URL_PASSWORD)+'\n').encode())(host),'RISK_URL_FILE_DIVERGES'),
    ('risk_file_rewritten',lambda host:set_node(RISK(),mtime=7)(host),'RISK_URL_FILE_DIVERGES'),
    ('risk_file_metadata_changed',lambda host:set_node(RISK(),ctime=7)(host),'RISK_URL_FILE_DIVERGES'),
    ('risk_file_mode_changed',mode(RISK,0o620),'RISK_URL_FILE_DIVERGES'),
    ('risk_file_owner_changed',lambda host:set_node(RISK(),uid=1001)(host),'RISK_URL_FILE_DIVERGES'),
    ('risk_file_group_changed',lambda host:set_node(RISK(),gid=5)(host),'RISK_URL_FILE_DIVERGES'),
    ('risk_file_too_large',Before(content(RISK,(k3.url()+'x'*4096).encode())),'RISK_URL_FORMAT'),
    ('risk_url_of_4096_bytes_without_a_newline',Before(content(RISK,(k3.url()+'x'*(4096-len(k3.url()))).encode())),'RISK_URL_FORMAT'),
    ('risk_file_of_4097_bytes_with_its_newline',Before(content(RISK,(k3.url()+'x'*(4096-len(k3.url()))+'\n').encode())),'RISK_URL_FORMAT'),
    ('risk_file_empty',Before(content(RISK,b'')),'RISK_URL_FORMAT'),
    ('risk_url_two_newlines',Before(content(RISK,(k3.url()+'\n\n').encode())),'RISK_URL_FORMAT'),
    ('risk_url_crlf',Before(content(RISK,(k3.url()+'\r\n').encode())),'RISK_URL_FORMAT'),
    ('risk_url_leading_space',Before(content(RISK,(' '+k3.url()+'\n').encode())),'RISK_URL_FORMAT'),
    ('risk_url_with_a_space',Before(content(RISK,(k3.url('UrL pAsS')+'\n').encode())),'RISK_URL_FORMAT'),
    ('risk_url_other_scheme',Before(content(RISK,(k3.url().replace('postgresql://','postgres://')+'\n').encode())),'RISK_URL_FORMAT'),
    ('risk_url_not_ascii',Before(content(RISK,(k3.url()+'\u00e9\n').encode())),'RISK_URL_FORMAT'),
    ('risk_url_of_the_owner_role',Before(content(RISK,(k3.url(role='c3po')+'\n').encode())),'RISK_DATABASE_URL_NOT_THE_RESTRICTED_READER'),
    ('risk_url_of_a_reader_lookalike',Before(content(RISK,(k3.url(role='c3po_v2_risk_reader_x')+'\n').encode())),'RISK_DATABASE_URL_NOT_THE_RESTRICTED_READER'),
    ('risk_url_with_a_user_parameter',Before(content(RISK,(k3.url()+'?user=postgres\n').encode())),'RISK_DATABASE_URL_WITH_PARAMETERS'),
    ('risk_url_with_a_service_parameter',Before(content(RISK,(k3.url()+'?service=admin\n').encode())),'RISK_DATABASE_URL_WITH_PARAMETERS'),
    ('risk_url_with_a_host_and_user_parameter',Before(content(RISK,(k3.url()+'?host=db&user=c3po\n').encode())),'RISK_DATABASE_URL_WITH_PARAMETERS'),
    ('risk_url_with_a_fragment',Before(content(RISK,(k3.url()+'#x\n').encode())),'RISK_DATABASE_URL_WITH_PARAMETERS'),
    # the emitter password, likewise
    ('password_directory_absent',lambda host:host.tree.remove(PW()) or host.tree.remove(M().EMITTER_SOURCE_DIRECTORY),'EMITTER_PASSWORD_COMPONENT_ABSENT'),
    ('password_parent_is_a_link',lambda host:replace(k3.DATA+'/.c3po-role-executor-20260908-r2',kind='symlink',mode=0o777,target='/tmp')(host),'EMITTER_PASSWORD_COMPONENT_DIVERGES'),
    ('password_parent_mode_changed',lambda host:set_node(k3.DATA+'/.c3po-role-executor-20260908-r2',mode=0o750)(host),'EMITTER_PASSWORD_COMPONENT_DIVERGES'),
    ('password_directory_mode_changed',lambda host:set_node(M().EMITTER_SOURCE_DIRECTORY,mode=0o707)(host),'EMITTER_PASSWORD_COMPONENT_DIVERGES'),
    ('password_directory_entries_changed',lambda host:set_node(M().EMITTER_SOURCE_DIRECTORY,mtime=9)(host),'EMITTER_PASSWORD_COMPONENT_DIVERGES'),
    ('password_file_absent',lambda host:host.tree.remove(PW()),'EMITTER_PASSWORD_FILE_ABSENT'),
    ('password_file_is_a_link',lambda host:replace(PW(),kind='symlink',mode=0o777,target='/etc/hostname')(host),'EMITTER_PASSWORD_FILE_NOT_REGULAR'),
    ('password_file_with_a_second_link',lambda host:set_node(PW(),nlink=2)(host),'EMITTER_PASSWORD_FILE_LINKED'),
    ('password_file_substituted',lambda host:replace(PW(),kind='file',uid=1000,gid=1000,mode=0o600,content=k3.OTHER_PASSWORD.encode())(host),'EMITTER_PASSWORD_FILE_DIVERGES'),
    ('password_file_mode_changed',mode(PW,0o660),'EMITTER_PASSWORD_FILE_DIVERGES'),
    ('password_file_owner_changed',lambda host:set_node(PW(),uid=33)(host),'EMITTER_PASSWORD_FILE_DIVERGES'),
    ('password_file_rewritten',lambda host:set_node(PW(),mtime=9)(host),'EMITTER_PASSWORD_FILE_DIVERGES'),
    ('password_63_bytes',Before(content(PW,k3.PASSWORD[:63].encode())),'EMITTER_PASSWORD_FORMAT'),
    ('password_with_a_newline',Before(content(PW,(k3.PASSWORD+'\n').encode())),'EMITTER_PASSWORD_FORMAT'),
    ('password_with_a_dot',Before(content(PW,(k3.PASSWORD[:63]+'.').encode())),'EMITTER_PASSWORD_FORMAT'),
    ('password_empty',Before(content(PW,b'')),'EMITTER_PASSWORD_FORMAT'),
    # the executor, the boot, the filesystem primitives
    ('executor_not_root',lambda host:setattr(host,'actor',(1000,1000)),'EXECUTOR_IDENTITY'),
    ('executor_group_not_root',lambda host:setattr(host,'actor',(0,1000)),'EXECUTOR_IDENTITY'),
    ('boot_of_another_evidence',lambda host:setattr(host.tree.get('/proc/sys/kernel/random/boot_id'),'content',bytearray(b'11111111-2222-3333-4444-555555555555\n')),'EVIDENCE_FROM_EARLIER_BOOT'),
    ('noatime_unavailable',lambda host:setattr(host,'noatime_available',False),'NOATIME_UNAVAILABLE'),
]
@pytest.mark.parametrize('name,prepare,code',REFUSALS,ids=[row[0] for row in REFUSALS])
def test_refusal_before_the_first_creation_changes_nothing(name,prepare,code):
    docs,host,before,receipt=run(prepare);refused(receipt,code);nothing_changed(host,before)
    assert receipt['phase_reached']=='PRECHECK' and receipt['mutating_calls']['issued']==0 and receipt['objects_left_by_this_run']==0
    assert all(row['state']=='NOT_ATTEMPTED' for row in receipt['files'].values()) and receipt['emitter_directory']['state']=='NOT_ATTEMPTED'
    assert not [entry for entry in host.log if entry[0] in ('create','mkdir','write','unlink')]
    assert receipt['code'] in M().RECEIPT_CODES and receipt['process']=={'dumpable_disabled':True}

def test_a_refusal_says_what_was_found_up_to_it_and_nothing_after():
    m=M()
    docs,host,before,receipt=run(token('C3PO_FMP_API_TOKEN','FmPcAnArY fOrTeStS'))
    assert receipt['worker']['grammar_met'] is None and receipt['worker']['names_present'] is None and receipt['worker']['running'] is True
    assert receipt['worker']['read_twice_equal'] is None and receipt['risk_url_source']['present'] is None and not [entry for entry in host.log if source_access(entry)]
    docs,host,before,receipt=run(Before(mode(RISK,0o640)))
    assert receipt['status']==m.COMPLETE_STATUS and receipt['risk_url_source']['not_readable_by_group_or_other'] is False
    docs,host,before,receipt=run(Before(content(RISK,(k3.url(role='c3po')+'\n').encode())))
    assert receipt['risk_url_source']['grammar_met'] is True and receipt['risk_url_source']['userinfo_names_the_restricted_reader'] is False
    assert receipt['risk_url_source']['no_query_or_fragment'] is None
    docs,host,before,receipt=run(Before(content(RISK,(k3.url()+'?user=x\n').encode())))
    assert receipt['risk_url_source']['userinfo_names_the_restricted_reader'] is True and receipt['risk_url_source']['no_query_or_fragment'] is False
    docs,host,before,receipt=run(Before(content(RISK,b'x'*5000)))
    assert receipt['risk_url_source']['grammar_met'] is None and receipt['risk_url_source']['unchanged_during_read'] is None and receipt['risk_url_source']['regular'] is True
    assert receipt['emitter_password_source']['present'] is None
    docs,host,before,receipt=run(lambda host:host.docker.container(k3.WORKER).update(Id='6f'*32))
    assert receipt['worker']['one_container_with_the_name'] is True and receipt['worker']['id_equal_signed'] is False and receipt['worker']['running'] is None
    assert [entry['argv'][1] for entry in host.commands]==['ps']

def test_the_facts_of_a_refused_source_walk_and_nothing_opened_past_a_divergence():
    m=M()
    docs,host,before,receipt=run(lambda host:set_node(m.RISK_URL_DIRECTORY,mode=0o777)(host));refused(receipt,'RISK_URL_COMPONENT_DIVERGES')
    assert receipt['risk_url_source']['components_as_signed'] is None and receipt['risk_url_source']['present'] is None
    assert not [entry for entry in host.log if entry[0]=='open' and entry[1]==m.RISK_URL_DIRECTORY],'a component that diverges is never opened'
    docs,host,before,receipt=run(lambda host:set_node(RISK(),mtime=7)(host));refused(receipt,'RISK_URL_FILE_DIVERGES')
    assert receipt['risk_url_source']['components_as_signed'] is True and receipt['risk_url_source']['file_as_signed'] is None
    assert not [entry for entry in host.log if entry[0]=='open' and entry[1]==RISK()],'a file that diverges is never opened'
    docs,host,before,receipt=run(lambda host:set_node(k3.DATA,dev=999)(host));refused(receipt,'RISK_URL_COMPONENT_DIVERGES')
    assert not [entry for entry in host.log if entry[0]=='open' and entry[1]==k3.DATA]

def test_a_value_that_changes_between_the_two_reads_is_refused():
    def changing(host,name,detail,calls):
        if name=='not_dumpable' and [entry[0] for entry in host.log].count('not_dumpable')==3:
            env=host.docker.container(k3.WORKER)['Config']['Env']
            env[:]=[item if not item.startswith('FMP_API_TOKEN=') else 'FMP_API_TOKEN=FmPcHaNgEdCaNaRyVaLuE' for item in env]
    docs,host,before,receipt=run(hook=changing);refused(receipt,'WORKER_ENVIRONMENT_CHANGED_DURING_READ');nothing_changed(host,before)
    assert receipt['worker']['read_twice_equal'] is False and receipt['worker']['grammar_met'] is True

def test_a_source_file_that_changes_while_read_is_refused():
    def touched(host,name,detail,calls):
        if name=='read' and detail[0]==RISK():host.tree.get(RISK()).mtime+=1
    docs,host,before,receipt=run(hook=touched);refused(receipt,'RISK_URL_FILE_CHANGED_DURING_READ')
    def swapped(host,name,detail,calls):
        if name=='fstat' and detail[0]==PW() and not getattr(host,'_swapped',False):
            host._swapped=True;node=host.tree.get(PW());node.ino+=1000
    docs,host,before,receipt=run(hook=swapped);refused(receipt,'EMITTER_PASSWORD_FILE_CHANGED_DURING_READ')

ACCEPTED=[('risk_url_without_a_newline',Before(content(RISK,k3.url().encode()))),('risk_file_root_owned',Before(lambda host:set_node(RISK(),uid=0,gid=0)(host))),
          ('risk_file_readable_by_group',Before(mode(RISK,0o640))),('risk_file_0444',Before(mode(RISK,0o444))),('password_file_root_owned',Before(lambda host:set_node(PW(),uid=0)(host))),
          ('source_directories_root_owned',Before(lambda host:(set_node(m_attr('RISK_URL_DIRECTORY'),uid=0)(host),set_node(m_attr('EMITTER_SOURCE_DIRECTORY'),uid=0)(host)))),
          ('risk_url_of_exactly_4096_bytes_with_its_newline',Before(content(RISK,(k3.url()+'x'*(4095-len(k3.url()))+'\n').encode()))),
          ('another_container_running',lambda host:host.docker.containers.append(hostemu.container('stray',hostemu.BACKEND,'c3po/backend:production',[]))),
          ('another_entry_in_the_k9_root',add('/var/lib/c3po/r2d2-v2-k9-20261005/other',mode=0o700)),
          ('token_of_exactly_512_characters',token('C3PO_EODHD_API_TOKEN','Ab'*256)),('token_of_exactly_16_characters',token('C3PO_EODHD_API_TOKEN','EoDhDtOkEnSiXtEe')),
          ('a_lower_case_name_is_not_one_of_the_six',worker_env(lambda env:env+['eodhd_api_token=x'])),
          ('another_name_that_ends_like_one',worker_env(lambda env:env+['OLD_EODHD_API_TOKEN=x','EODHD_API_TOKEN_OLD=y']))]
@pytest.mark.parametrize('name,prepare',ACCEPTED,ids=[row[0] for row in ACCEPTED])
def test_accepted_states_complete(name,prepare):
    docs,host,before,receipt=run(prepare);assert receipt['status']==M().COMPLETE_STATUS,receipt['code']

def test_a_process_that_cannot_be_made_non_dumpable_is_a_refusal_before_anything_is_looked_at():
    class Answers(k3.K9Host):
        answer=False
        def not_dumpable(self):self.event('not_dumpable');return self.answer
    for prepare in ((lambda host:setattr(host,'dumpable_refused',True)),(lambda host:setattr(host,'__class__',Answers)),
                    (lambda host:(setattr(host,'__class__',Answers),setattr(host,'answer',1))),(lambda host:(setattr(host,'__class__',Answers),setattr(host,'answer',None)))):
        k,host=k3.world();prepare(host);docs=f.Docs(k,k3.fields(host),now=k3.NOW);before=k3.state_of(host)
        receipt=docs.run(host);refused(receipt,'PROCESS_DUMPABLE_NOT_DISABLED');nothing_changed(host,before)
        assert host.log==[('not_dumpable',)] and host.commands==[] and receipt['process']=={'dumpable_disabled':False}
        assert receipt['worker']['one_container_with_the_name'] is None and k3.leaks(k3.line(receipt))==[]
    for error,code in ((OSError(errno.EPERM,'x'),'PRECHECK_OS_ERROR'),(RuntimeError('x'),'PRECHECK_FAILED')):
        def hook(host,name,detail,calls,error=error):
            if name=='not_dumpable':raise error
        k,host=k3.world();host.hook=hook;receipt=f.Docs(k,k3.fields(host),now=k3.NOW).run(host)
        refused(receipt,code);assert host.log==[('not_dumpable',)] and receipt['process']=={'dumpable_disabled':False}

def test_the_process_is_made_non_dumpable_first_on_every_path():
    for name,prepare,_ in REFUSALS:
        docs,host,before,receipt=run(prepare);assert host.log[0]==('not_dumpable',) and receipt['process']=={'dumpable_disabled':True},name

def test_the_budget_is_the_last_refusal_and_the_directory_is_proved_again_before_the_first_creation():
    m=M();k,host=k3.world();docs=f.Docs(k,k3.fields(host),now=k3.NOW);budget=f.Budget(k3.NOW).attach(host).cost(23.5,'ps')
    before=k3.state_of(host);receipt=docs.run(host,**budget.options())
    refused(receipt,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT');nothing_changed(host,before);assert receipt['precheck']['seconds_left_before_the_first_effect']==13
    k,host=k3.world();docs=f.Docs(k,k3.fields(host),now=k3.NOW);budget=f.Budget(k3.NOW).attach(host).cost(23,'ps')
    receipt=docs.run(host,**budget.options());refused(receipt,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT');assert receipt['precheck']['seconds_left_before_the_first_effect']==14
    k,host=k3.world();docs=f.Docs(k,k3.fields(host),now=k3.NOW);budget=f.Budget(k3.NOW).attach(host).cost(22.5,'ps')
    receipt=docs.run(host,**budget.options());assert receipt['status']==m.COMPLETE_STATUS and receipt['precheck']['seconds_left_before_the_first_effect']==15
    # the secrets directory replaced after the reads and before the first creation
    def swap(host,name,detail,calls):
        if name=='open' and detail[0]==PW():replace(m.K9_SECRETS_DIRECTORY,uid=0,gid=0,mode=0o700)(host)
    docs,host,before,receipt=run(hook=swap);refused(receipt,'PARENT_REPLACED');assert not [entry for entry in host.log if entry[0] in ('mkdir','create')]
    assert receipt['phase_reached']=='PRECHECK' and receipt['emitter_directory']['state']=='NOT_ATTEMPTED'


# ---------------------------------------------------------------- after the first creation: withdrawal, partial, uncertainty
def test_a_full_filesystem_at_the_mkdir_is_a_refusal_with_nothing_changed():
    m=M();docs,host,before,receipt=run(hook=once(failing('mkdir',m.K9_EMITTER_DIRECTORY,OSError(errno.ENOSPC,'full'))))
    refused(receipt,'FILESYSTEM_FULL');nothing_changed(host,before)
    assert receipt['emitter_directory']['state']=='NOT_CREATED' and receipt['phase_reached']=='EFFECTS' and receipt['objects_left_by_this_run']==0
    assert receipt['mutating_calls']=={'issued':1,'succeeded':0,'failed_nothing_changed':1,'uncertain':0}

@pytest.mark.parametrize('index',[0,1,2])
def test_a_write_that_fails_withdraws_that_file_and_leaves_the_ones_before_it(index):
    m=M();path=paths()[index]
    docs,host,before,receipt=run(hook=once(failing('write',path,OSError(errno.ENOSPC,'full'))))
    partial(receipt,'FILESYSTEM_FULL');row=receipt['files'][m.FILE_ROWS[index]]
    assert row['state']=='WITHDRAWN' and row['withdrawn'] is True and row['code']=='FILESYSTEM_FULL' and row['errno']==errno.ENOSPC and row['fsync_directory_after_withdrawal'] is True
    assert k3.node(host,path) is None and k3.node(host,m.K9_EMITTER_DIRECTORY) is not None
    for later in range(index+1,3):assert receipt['files'][m.FILE_ROWS[later]]['state']=='NOT_ATTEMPTED' and k3.node(host,paths()[later]) is None
    for earlier in range(index):assert receipt['files'][m.FILE_ROWS[earlier]]['state']=='PLACED_VERIFIED' and k3.node(host,paths()[earlier]) is not None
    assert receipt['objects_left_by_this_run']==1+index and receipt['directory_readbacks']=={'secrets_directory':None,'emitter_directory':None}
    # mkdir, the creates and writes before, this create, its failed write, the unlink: each counted
    assert receipt['mutating_calls']=={'issued':3+2*index+1,'succeeded':2+2*index+1,'failed_nothing_changed':1,'uncertain':0}
    unlink=[i for i,entry in enumerate(host.log) if entry[0]=='unlink'];assert [host.log[i][1] for i in unlink]==[path]
    assert host.log[unlink[0]+1]==('fsync',m.K9_EMITTER_DIRECTORY if index==2 else m.K9_SECRETS_DIRECTORY)

@pytest.mark.parametrize('call,code',[('fsync','FSYNC_FAILED'),('fstat','SECRET_FILE_STAT_FAILED')])
def test_a_failed_fsync_or_fstat_after_the_write_withdraws(call,code):
    m=M();docs,host,before,receipt=run(hook=once(failing(call,paths()[1],OSError(errno.EIO,'io'))))
    partial(receipt,code);row=receipt['files']['risk_db_env'];assert row['state']=='WITHDRAWN' and k3.node(host,paths()[1]) is None

def test_metadata_other_than_root_0600_with_one_link_is_withdrawn():
    for attribute,value in (('gid',5),('mode',0o640),('uid',1000),('nlink',2),('dev',999)):
        def change(host,name,detail,attribute=attribute,value=value):
            if name=='write' and detail[0]==paths()[0]:setattr(host.tree.get(paths()[0]),attribute,value);return True
            return False
        docs,host,before,receipt=run(hook=once(change));row=receipt['files']['provider_env']
        partial(receipt,'SECRET_FILE_METADATA_MISMATCH')
        if attribute=='nlink':assert row['state']=='LEFT_UNVERIFIED' and row['withdrawal_code']=='SECRET_FILE_NAME_NOT_THIS_RUNS_FILE',attribute
        else:assert row['state']=='WITHDRAWN' and k3.node(host,paths()[0]) is None,attribute

def test_a_name_replaced_before_the_readback_is_left_and_another_object_is_never_removed():
    m=M()
    def swap(host,name,detail):
        if name=='fsync' and detail[0]==m.K9_SECRETS_DIRECTORY and any(entry[:2]==('fsync',paths()[0]) for entry in host.log):
            host.tree.remove(paths()[0]);host.tree.add(paths()[0],kind='file',mode=0o600,uid=0,gid=0,content=b'someone else');return True
        return False
    docs,host,before,receipt=run(hook=once(swap));partial(receipt,'READBACK_MISMATCH');row=receipt['files']['provider_env']
    assert row['readback_same_inode'] is False and row['state']=='LEFT_UNVERIFIED' and row['withdrawal_code']=='SECRET_FILE_NAME_NOT_THIS_RUNS_FILE'
    assert bytes(k3.node(host,paths()[0]).content)==b'someone else' and not [entry for entry in host.log if entry[0]=='unlink']
    assert receipt['objects_left_by_this_run']==2

def test_a_file_that_appears_after_the_precheck_is_not_touched():
    m=M()
    def appear(host,name,detail):
        if name=='mkdir':host.tree.add(paths()[1],kind='file',mode=0o600,content=b'raced');return True
        return False
    docs,host,before,receipt=run(hook=once(appear));partial(receipt,'SECRET_FILE_APPEARED_AFTER_PRECHECK')
    row=receipt['files']['risk_db_env'];assert row['state']=='NOT_CREATED' and row['errno']==errno.EEXIST and bytes(k3.node(host,paths()[1]).content)==b'raced'
    assert receipt['files']['provider_env']['state']=='PLACED_VERIFIED' and receipt['objects_left_by_this_run']==2

def test_an_expiry_after_a_creation_leaves_the_file_unverified_and_removes_nothing():
    m=M();docs,host,before,receipt=run(hook=None);k,host=k3.world();docs=f.Docs(k,k3.fields(host),now=k3.NOW)
    plan,real=docs.authenticate();calls=[0]
    def gate():
        if any(entry[0]=='create' and entry[1]==paths()[2] for entry in host.log):raise m.Refused('GO_EXPIRED')
        return real()
    receipt=docs.perform(host,gate=gate)
    partial(receipt,'GO_EXPIRED');row=receipt['files']['emitter_password']
    assert row['state']=='LEFT_UNVERIFIED' and row['withdrawn'] is False and row['withdrawal_code'] is None and k3.node(host,paths()[2]) is not None
    assert not [entry for entry in host.log if entry[0]=='unlink']

def test_a_failure_of_another_kind_after_a_creation_withdraws_and_a_death_leaves_no_receipt():
    m=M()
    def boom(host,name,detail):
        if name=='write' and detail[0]==paths()[0]:raise RuntimeError('not an OSError')
        return False
    docs,host,before,receipt=run(hook=once(boom));partial(receipt,'SECRET_FILE_PLACEMENT_FAILED')
    row=receipt['files']['provider_env'];assert row['state']=='WITHDRAWN' and receipt['mutating_calls']['uncertain']==1,'the write it interrupted is uncertain'
    k,host=k3.world();docs=f.Docs(k,k3.fields(host),now=k3.NOW)
    def die(host,name,detail,calls):
        if name=='write':raise hostemu.Death()
    host.hook=die
    with pytest.raises(hostemu.Death):docs.perform(host)
    assert k3.node(host,paths()[0]) is not None and k3.leaks(k3.outside_view(host))==[]

def test_an_unlink_that_fails_leaves_the_file_with_its_code():
    m=M();state={'n':0}
    def hook(host,name,detail,calls):
        if name=='write' and detail[0]==paths()[0]:raise OSError(errno.ENOSPC,'full')
        if name=='unlink':raise OSError(errno.EBUSY,'busy')
    docs,host,before,receipt=run(hook=hook);partial(receipt,'FILESYSTEM_FULL');row=receipt['files']['provider_env']
    assert row['state']=='LEFT_UNVERIFIED' and row['withdrawal_code']=='SECRET_FILE_WITHDRAWAL_FAILED' and row['withdrawal_errno']==errno.EBUSY

def test_a_directory_readback_that_finds_another_entry_is_a_partial():
    m=M()
    def extra(host,name,detail):
        if name=='open' and detail[0]==paths()[2]:host.tree.add(m.K9_SECRETS_DIRECTORY+'/stray',kind='file',mode=0o600);return True
        return False
    docs,host,before,receipt=run(hook=once(extra));partial(receipt,'DIRECTORY_READBACK_MISMATCH')
    assert receipt['directory_readbacks']=={'secrets_directory':'READBACK_MISMATCH','emitter_directory':None}
    assert all(row['state']=='PLACED_VERIFIED' for row in receipt['files'].values()) and receipt['readback'] is None

def test_a_code_shaped_text_raised_by_the_host_is_reported_as_unlisted():
    m=M()
    for call,path in (('lstat',m.RISK_URL_DIRECTORY+'/'+m.RISK_URL_NAME),('write',paths()[0]),('unlink',paths()[0])):
        def hook(host,name,detail,calls,call=call,path=path):
            if name==call and detail[0]==path:raise m.Refused('FAKETOKENINCAPITALS')
            if call=='unlink' and name=='write' and detail[0]==paths()[0]:raise OSError(errno.ENOSPC,'full')
        docs,host,before,receipt=run(hook=hook)
        text=k3.line(receipt).decode();assert 'FAKETOKENINCAPITALS' not in text and 'UNLISTED_CODE' in text,call


# ---------------------------------------------------------------- the plan, the effects, the evidence
def test_the_plan_is_refused_from_its_bytes_before_any_claim():
    m=M();k,host=k3.world();good=k3.fields(host)
    def code(**changes):
        docs=f.Docs(k,dict(good,**changes),now=k3.NOW);return f.refusal(docs.authenticate)
    rows=good['secrets_chain']
    def changed(index,**values):
        out=json.loads(json.dumps(rows));out[index].update(values);return out
    assert code(secrets_chain=changed(-1,mode=0o755))=='SECRETS_DIRECTORY_NOT_ROOT_0700'
    assert code(secrets_chain=changed(-1,gid=5))=='CHAIN_ROW_NOT_ROOT_GROUP'
    for index in range(len(rows)):
        assert code(secrets_chain=changed(index,gid=1000))=='CHAIN_ROW_NOT_ROOT_GROUP',index
        if index<len(rows)-1:assert code(secrets_chain=changed(index,mode=rows[index]['mode']|0o2000))=='CHAIN_ROW_NOT_ROOT_GROUP',index
    assert code(secrets_chain=changed(-1,mode=0o2700))=='PARENT_SETGID'
    assert code(secrets_chain=changed(-1,uid=1000))=='CHAIN_ROW_UNSAFE' and code(secrets_chain=changed(-1,mode=0o770))=='CHAIN_ROW_UNSAFE'
    for index in range(len(rows)-1):
        # no open root (N-8): every component root-owned and closed to group and other writes, whatever its depth
        assert code(secrets_chain=changed(index,uid=1000))=='CHAIN_ROW_UNSAFE',index
        assert code(secrets_chain=changed(index,mode=0o775))=='CHAIN_ROW_UNSAFE',index
        assert code(secrets_chain=changed(index,mode=0o1777))=='CHAIN_ROW_UNSAFE',index
    assert code(secrets_chain=changed(-2,mode=0o755))=='K9_ROOT_NOT_ROOT_0700'
    assert code(secrets_chain=changed(-1,mode=0o750))=='SECRETS_DIRECTORY_NOT_ROOT_0700'
    assert code(secrets_chain=rows[:-1])=='CHAIN_ROW_INVALID' and code(secrets_chain=hostemu.rows(host,k3.DATA))=='CHAIN_ROW_INVALID'
    assert code(secrets_chain=None)=='CHAIN_ROW_INVALID'
    for value in (None,'5e'*31,'5E'*32,k3.WORKER,7):assert code(worker_container_id=value)=='WORKER_CONTAINER_UNBOUND',value
    for value in (None,'0'*64,'x'):assert code(evidence_boot_id_sha256=value)=='EVIDENCE_BOOT_UNBOUND'
    # the chain of the K9 tree crosses nothing of uid 1000, and /var/lib/c3po may be 0755 or 0700 as K4 mode E0 leaves it
    assert f.Docs(k,good,now=k3.NOW).authenticate() and [row['path'] for row in rows]==['/','/var','/var/lib','/var/lib/c3po',m.K9_ROOT,m.K9_SECRETS_DIRECTORY]
    assert all(row['uid']==0 for row in rows) and f.Docs(k,dict(good,secrets_chain=changed(3,mode=0o755)),now=k3.NOW).authenticate()
    assert code(secrets_chain=hostemu.rows(host,'/mnt/day-d-data'))=='CHAIN_ROW_INVALID'
    # the signed rows of the data volume: "/" and "/mnt" root-owned and closed, the volume itself as found (the open root)
    volume=good['data_volume_chain']
    def volume_changed(index,**values):
        out=json.loads(json.dumps(volume));out[index].update(values);return out
    assert code(data_volume_chain=volume_changed(1,mode=0o775))=='CHAIN_ROW_UNSAFE' and code(data_volume_chain=volume_changed(1,uid=1000))=='CHAIN_ROW_UNSAFE'
    assert code(data_volume_chain=volume_changed(2,mode=0o777))=='CHAIN_ROW_WORLD_WRITABLE' and code(data_volume_chain=volume[:2])=='CHAIN_ROW_INVALID'
    assert code(data_volume_chain=rows)=='CHAIN_ROW_INVALID' and f.Docs(k,dict(good,data_volume_chain=volume_changed(2,mode=0o750)),now=k3.NOW).authenticate()
    assert code(data_volume_chain=volume_changed(2,device=volume[1]['device']))=='DATA_VOLUME_NOT_A_MOUNT_POINT'
    # the signed rows below the data volume: exactly the five paths, on its device, owned by root or by its owner, closed
    sources=good['source_rows']
    def source_changed(index,**values):
        out=json.loads(json.dumps(sources));out[index].update(values);return out
    for index in range(5):
        for mode in (0o770,0o707,0o1777,0o1770,0o620,0o602):
            assert code(source_rows=source_changed(index,mode=mode))=='SOURCE_ROWS_WRITABLE_BY_GROUP_OR_OTHER',(index,mode)
        assert code(source_rows=source_changed(index,device=999))=='SOURCE_ROWS_OFF_THE_DATA_VOLUME',index
        assert code(source_rows=source_changed(index,uid=1001))=='SOURCE_ROWS_OWNER_UNEXPECTED',index
        assert f.Docs(k,dict(good,source_rows=source_changed(index,uid=0,gid=5)),now=k3.NOW).authenticate()
        for key,value in (('path','/x'),('inode',0),('mtime_ns',-1),('ctime_ns',None),('mode',0o17777),('size',1)):
            assert code(source_rows=source_changed(index,**{key:value}))=='SOURCE_ROWS_INVALID',(index,key)
    assert code(source_rows=sources[:4])=='SOURCE_ROWS_INVALID' and code(source_rows=sources[::-1])=='SOURCE_ROWS_INVALID' and code(source_rows=None)=='SOURCE_ROWS_INVALID'
    assert [row['path'] for row in sources]==list(m.SOURCE_PATHS) and not [row for row in sources if 'size' in row]

def test_the_effects_the_signers_see():
    m=M();k,host=k3.world();plan=dict(k3.fields(host));effects=m.effects_of(plan)
    assert effects=={'operation':'GO_WRITE_HOSTOPS02_K3K9_SECRETS_01','k9_root':'/var/lib/c3po/r2d2-v2-k9-20261005','placement':'N-8',
                     'secrets_directory':dict(m.chain_effects(plan['secrets_chain']),required={'uid':0,'gid':0,'mode_octal':'0700','entries':0,'k9_root':'root:root 0700','open_root':None}),
                     'creates':{'directory':{'path':'/var/lib/c3po/r2d2-v2-k9-20261005/secrets/emitter','uid':0,'gid':0,'mode_octal':'0700'},
                                'files':[{'path':'/var/lib/c3po/r2d2-v2-k9-20261005/secrets/'+name,'uid':0,'gid':0,'mode_octal':'0600','links':1}
                                         for name in ('provider.env','risk-db.env','emitter/password')]},
                     'values':{'worker_config':{'root':m.DOCKER_CONTAINER_ROOT,'leaf':m.WORKER_CONFIG_NAME,'max_bytes':m.WORKER_CONFIG_MAX_BYTES,'root_only':True,'private_mode':'0600','no_cli_inspect':True},'provider_env':{'names':[['C3PO_EODHD_API_TOKEN','EODHD_API_TOKEN'],['C3PO_FINNHUB_API_TOKEN','FINNHUB_API_TOKEN'],
                                                         ['C3PO_FMP_API_TOKEN','FMP_API_TOKEN']],'from_container':'c3po-r2d2-worker-1','container_id':k3.WORKER_ID},
                               'data_volume':dict(m.chain_effects(plan['data_volume_chain']),open_root_of='the two walks of the files of September only'),
                               'source_rows_sha256':m.sha(m.canonical(plan['source_rows'])),
                               'risk_db_env':{'name':'C3PO_R2D2_RISK_DATABASE_URL','from_file':'/mnt/day-d-data/.r2d2-v2-risk-secrets/risk-database-url'},
                               'emitter_password':{'from_file':'/mnt/day-d-data/.c3po-role-executor-20260908-r2/secret/password'}},
                     'process':{'dumpable':0,'when':'first, before anything of the host is looked at'},'evidence_boot_id_sha256':f.BOOT_SHA,
                     'pre_existing_objects_modified':False,'activation':False,'value_in_receipt':False,'size_or_digest_in_receipt':False}
    docs=f.Docs(k,plan,now=k3.NOW);docs.authority['effects']['values']['risk_db_env']['from_file']='/elsewhere';docs.chain(effects=False)
    assert f.refusal(docs.authenticate)=='EFFECTS_BINDING'

def test_the_evidence_names_k4_e0_and_the_epoch_readback():
    m=M();k,host=k3.world()
    assert m.EVIDENCE_OPERATIONS==('GO_WRITE_HOSTOPS02_K4_E0_01','GO_READONLY_HOSTOPS02_EPOCH_READBACK_01','GO_READONLY_HOSTOPS02_K9_PHASE_READ_01')
    for missing in m.EVIDENCE_OPERATIONS:
        evidence=[{'role':'R%d'%index,'operation':name,'receipt_sha256':'b'*64} for index,name in enumerate(m.EVIDENCE_OPERATIONS) if name!=missing]
        assert f.refusal(f.Docs(k,k3.fields(host),now=k3.NOW,evidence=evidence).authenticate)=='EVIDENCE_OPERATION_MISSING'

def test_the_placement_is_one_constant_of_decision_n8():
    m=M();source=(k3.DIRECTORY/'op.py').read_text()
    assert source.count("'/var/lib/c3po/r2d2-v2-k9-20261005'")==1 and 'N-8 (Codex)' in source.splitlines()[[index for index,line in enumerate(source.splitlines()) if line.startswith('K9_ROOT=')][0]]
    assert not m.K9_ROOT.startswith(m.SOURCE_OPEN_ROOT+'/') and m.K9_ROOT.startswith('/var/lib/c3po/')
    assert 'd30f7f9048af4a39cf4fa7d9f49292ad387a2d41f33bad39816e83d3d1fc2c53' in m.SCOPE['placement']['status'] and all(path.startswith(m.K9_ROOT+'/') for path in m.TARGET_PATHS+(m.K9_SECRETS_DIRECTORY,))
    assert m.K9_SECRETS_DIRECTORY==m.K9_ROOT+'/secrets' and m.TARGET_PATHS==(m.K9_ROOT+'/secrets/provider.env',m.K9_ROOT+'/secrets/risk-db.env',m.K9_ROOT+'/secrets/emitter/password')


def test_a_component_above_the_data_volume_that_is_not_root_safe_refuses_the_source_walk():
    """The walk compares "/" and "/mnt" with their signed rows too: a change after the signature is a divergence."""
    m=M()
    for change in (dict(mode=0o775),dict(uid=1000)):
        k,host=k3.world();rows=hostemu.rows(host,k3.DATA)+k3.source_rows(host)[0:2];set_node('/mnt',**change)(host);gate=lambda:60.0;facts=m.source_facts()
        assert f.refusal(lambda:m.source_bytes(host,'RISK_URL',rows,m.RISK_URL_MAX_FILE_BYTES,gate,facts))=='RISK_URL_COMPONENT_DIVERGES'
        assert facts['components_as_signed'] is None
        assert facts['present'] is None and host.fds=={}


@pytest.mark.parametrize('names',['plain','prefixed','both'])
def test_either_name_of_each_token_and_both_with_one_value_give_the_prefixed_file(names):
    m=M();docs,host,before,receipt=run(names=names)
    assert receipt['status']==m.COMPLETE_STATUS and bytes(k3.node(host,paths()[0]).content)==k3.provider_content()
    present=receipt['worker']['names_present']
    assert present=={name:(name.startswith('C3PO_') and names!='plain') or (not name.startswith('C3PO_') and names!='prefixed') for name in m.SECRET_ENVIRONMENT_NAMES}
    # mixed: one token under its prefixed name only, another under both, the third under its plain name only
    def mix(host):
        env=host.docker.container(k3.WORKER)['Config']['Env']
        env[:]=[item for item in env if item.split('=',1)[0] not in m.SECRET_ENVIRONMENT_NAMES]+[
            'C3PO_EODHD_API_TOKEN='+k3.TOKENS['C3PO_EODHD_API_TOKEN'],'C3PO_FINNHUB_API_TOKEN='+k3.TOKENS['C3PO_FINNHUB_API_TOKEN'],
            'FINNHUB_API_TOKEN='+k3.TOKENS['C3PO_FINNHUB_API_TOKEN'],'FMP_API_TOKEN='+k3.TOKENS['C3PO_FMP_API_TOKEN']]
    docs,host,before,receipt=run(mix);assert receipt['status']==m.COMPLETE_STATUS and bytes(k3.node(host,paths()[0]).content)==k3.provider_content()


def test_a_name_that_appears_or_disappears_between_the_two_reads_is_refused():
    def appearing(host,name,detail,calls):
        if name=='not_dumpable' and [entry[0] for entry in host.log].count('not_dumpable')==3:
            host.docker.container(k3.WORKER)['Config']['Env'].append('C3PO_FMP_API_TOKEN='+k3.TOKENS['C3PO_FMP_API_TOKEN'])
    docs,host,before,receipt=run(hook=appearing);refused(receipt,'WORKER_ENVIRONMENT_CHANGED_DURING_READ');assert receipt['worker']['read_twice_equal'] is False

def test_no_secret_inspect_row_is_available_to_the_operation():
    m=M();assert set(m.COMMANDS)=={'container_list'}
    assert m.SECRET_ENVIRONMENT_ROW not in m.COMMANDS


def test_a_readback_that_finds_other_metadata_withdraws_and_a_replaced_directory_stops_the_run():
    m=M()
    def chmod(host,name,detail):
        if name=='fsync' and detail[0]==m.K9_SECRETS_DIRECTORY and any(entry[:2]==('fsync',paths()[0]) for entry in host.log):
            host.tree.get(paths()[0]).mode=0o644;return True
        return False
    docs,host,before,receipt=run(hook=once(chmod));partial(receipt,'READBACK_MISMATCH');row=receipt['files']['provider_env']
    assert row['readback_same_inode'] is True and row['readback_metadata_as_created'] is False and row['state']=='WITHDRAWN' and k3.node(host,paths()[0]) is None
    def move(host,name,detail):
        if name=='fsync' and detail[0]==paths()[0]:
            old=host.tree.get(m.K9_SECRETS_DIRECTORY);host.tree.remove(m.K9_SECRETS_DIRECTORY);host.tree.add(m.K9_ROOT+'/moved',mode=0o700)
            host.tree.get(m.K9_ROOT).children['moved']=old;host.tree.add(m.K9_SECRETS_DIRECTORY,uid=0,gid=0,mode=0o700);return True
        return False
    docs,host,before,receipt=run(hook=once(move));partial(receipt,'PARENT_REPLACED');row=receipt['files']['provider_env']
    assert row['state']=='LEFT_UNVERIFIED' and row['withdrawn'] is False and not [entry for entry in host.log if entry[0]=='unlink']
    assert receipt['files']['risk_db_env']['state']=='NOT_ATTEMPTED'

def test_short_writes_are_continued_and_a_write_of_nothing_withdraws():
    m=M()
    class Short(k3.K9Host):
        def write(self,fd,data):return k3.K9Host.write(self,fd,data[:5])
    docs,host,before,receipt=run(lambda host:setattr(host,'__class__',Short))
    assert receipt['status']==m.COMPLETE_STATUS and [bytes(k3.node(host,path).content) for path in paths()]==[k3.provider_content(),k3.risk_content(),k3.PASSWORD.encode()]
    class Nothing(k3.K9Host):
        def write(self,fd,data):
            self.event('write',self.path_of(fd),0);return 0
    docs,host,before,receipt=run(lambda host:setattr(host,'__class__',Nothing));partial(receipt,'SECRET_FILE_WRITE_INCOMPLETE')
    assert receipt['files']['provider_env']['state']=='WITHDRAWN' and k3.node(host,paths()[0]) is None

def test_an_expiry_at_the_readback_leaves_the_file_and_withdraws_nothing():
    m=M();k,host=k3.world();docs=f.Docs(k,k3.fields(host),now=k3.NOW);plan,real=docs.authenticate()
    def gate():
        created=[index for index,entry in enumerate(host.log) if entry[0]=='create' and entry[1]==paths()[2]]
        if created and any(entry==('fsync',m.K9_EMITTER_DIRECTORY) for entry in host.log[created[0]:]):raise m.Refused('GO_EXPIRED')
        return real()
    receipt=docs.perform(host,gate=gate);partial(receipt,'GO_EXPIRED');row=receipt['files']['emitter_password']
    assert row['state']=='LEFT_UNVERIFIED' and row['fsync_directory'] is True and row['withdrawal_code'] is None and not [entry for entry in host.log if entry[0]=='unlink']

def test_an_uncertain_creation_says_that_what_is_left_is_not_known():
    m=M()
    def boom(host,name,detail):
        if name=='create' and detail[0]==paths()[1]:raise RuntimeError('not an OSError')
        return False
    docs,host,before,receipt=run(hook=once(boom));partial(receipt,'SECRET_FILE_CREATE_UNCERTAIN')
    assert receipt['files']['risk_db_env']['state']=='CREATE_UNCERTAIN' and receipt['objects_left_by_this_run'] is None and receipt['mutating_calls']['uncertain']==1

def test_a_refused_parse_of_the_tokens_zeroes_what_it_made():
    m=M();recorded=[];real=m.zero_secret_values
    def spy(values):recorded.append(dict(values or {}));real(values)
    m.zero_secret_values=spy
    try:docs,host,before,receipt=run(worker_env(lambda env:env+['EODHD_API_TOKEN='+k3.TOKENS['C3PO_EODHD_API_TOKEN']]))
    finally:m.zero_secret_values=real
    refused(receipt,'SECRET_ENVIRONMENT_REPEATED')
    assert recorded and all(type(value) is bytearray and set(value)=={0} for values in recorded for value in values.values()) and any(recorded)

def test_with_several_causes_the_code_depends_on_the_names_and_never_on_a_length_or_a_character():
    """The review's M1 and m1: worlds that differ only in the length or the characters of the values (600 bytes, 5000
    bytes, a quote, a backslash, a newline, non-ASCII) give byte-identical receipts when another cause is also present:
    an absent token, a repeated name, a disagreement."""
    m=M()
    def receipt_of(prepare):
        docs,host,before,receipt=run(prepare);return k3.line(receipt)
    def without(name):return lambda env:[item for item in env if not item.startswith(name+'=')]
    for bad in ('x'*600,'x'*5000,'a"b'*30,'a\\b'*30,'a\nb'*30,'é'*40,''):
        absent=receipt_of(worker_env(lambda env,bad=bad:[item if not item.startswith('FMP_API_TOKEN=') else 'FMP_API_TOKEN='+bad for item in without('EODHD_API_TOKEN')(env)]))
        assert absent==receipt_of(worker_env(lambda env:without('EODHD_API_TOKEN')(env))),bad[:4]
        assert json.loads(absent)['code']=='PROVIDER_TOKEN_ABSENT'
        repeated=receipt_of(worker_env(lambda env,bad=bad:env+['EODHD_API_TOKEN='+bad]))
        assert repeated==receipt_of(worker_env(lambda env:env+['EODHD_API_TOKEN=OtHeRvAlUeFoRtEsTsXx'])) and json.loads(repeated)['code']=='SECRET_ENVIRONMENT_REPEATED'
        first=receipt_of(worker_env(lambda env,bad=bad:['EODHD_API_TOKEN='+bad]+[item for item in env if not item.startswith('EODHD_API_TOKEN=')]+['EODHD_API_TOKEN=y'*5]))
        assert json.loads(first)['code']=='SECRET_ENVIRONMENT_REPEATED' and first==repeated
        grammar=receipt_of(token('C3PO_FMP_API_TOKEN',bad))
        assert json.loads(grammar)['code']=='PROVIDER_TOKEN_GRAMMAR' and grammar==receipt_of(token('C3PO_FMP_API_TOKEN','short'))
    # over the output limit of the command (64 KiB for the six entries) the code is the grammar's too
    assert json.loads(receipt_of(token('C3PO_FMP_API_TOKEN','x'*70000)))['code']=='PROVIDER_TOKEN_GRAMMAR'

def test_the_source_walk_compares_slash_with_its_own_row_and_each_descriptor_after_it_is_opened():
    """"/" is compared with the row of data_volume_chain (a request may carry rows of "/" from two receipts); a
    directory replaced between its lstat and its open is found through the new descriptor."""
    m=M();k,host=k3.world();good=k3.fields(host)
    volume=json.loads(json.dumps(good['data_volume_chain']));volume[0]['mode']=0o700
    docs=f.Docs(k,dict(good,data_volume_chain=volume),now=k3.NOW);receipt=docs.run(host);refused(receipt,'RISK_URL_COMPONENT_DIVERGES')
    class Swap(k3.K9Host):
        def lstat(self,name,dir_fd):
            result=k3.K9Host.lstat(self,name,dir_fd)
            if self.path_of(dir_fd)==k3.DATA and name=='.r2d2-v2-risk-secrets' and not getattr(self,'swapped',False):
                self.swapped=True;replace(m.RISK_URL_DIRECTORY,uid=1000,gid=1000,mode=0o700)(self)
            return result
    docs,host,before,receipt=run(lambda host:setattr(host,'__class__',Swap));refused(receipt,'RISK_URL_COMPONENT_DIVERGES')
    assert receipt['risk_url_source']['components_as_signed'] is None
