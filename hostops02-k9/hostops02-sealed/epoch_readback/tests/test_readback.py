"""K11 end to end on the emulated host, in both modes: what a complete run does and says, every finding, every
observation that can fail, hostile states of the filesystem, hostile answers of the commands, time, and what never
leaves the run. The container of every run executes the real snippet bytes (tests/k11.py)."""
import ast
import errno
import json
import types

import pytest

import family as f
import hostemu
import k11

D=hostemu.DATA_DEVICE
COMPLETE='METADATA_ONLY_REQUIRES_REVIEW';PARTIAL='PARTIAL_METADATA_REQUIRES_REVIEW'
MISMATCH='OBSERVED_ALL_EXPECTATIONS_NOT_MET'
def fresh(mode='PRE',**options):
    docs,host=k11.case(mode,**options);return docs.k.m,docs,host
def ran(mode='PRE',prepare=None,**options):
    m,docs,host=fresh(mode,**options)
    if prepare is not None:prepare(host)
    before=k11.state_of(host);receipt=docs.run(host)
    assert k11.state_of(host)==before and host.mutating()==[] and host.fds=={} and host.lock_held(k11.LOCK) is None and f.sealed(receipt),'nothing is changed, held or left open'
    return m,docs,host,receipt
def finding(receipt,code,item=None,others_complete=True):
    """A finding: exit 2, the mismatch outcome, and every other item still observed."""
    assert (receipt['status'],receipt['outcome'])==(PARTIAL,MISMATCH) and code in receipt['findings'],(code,receipt['findings'],receipt['code'])
    assert receipt['expectations_met'] is False and receipt['gates_first_session_readback'] is False
    if item is not None:assert code in receipt['items'][item]['findings'] and receipt['items'][item]['matches'] is False
    if others_complete:assert receipt['items_not_complete']==[]
def unavailable(receipt,item,code):
    assert (receipt['status'],receipt['outcome'])==(PARTIAL,'PARTIAL_OBSERVED'),(receipt['code'],receipt['items_not_complete'])
    assert receipt['code']==(receipt['findings'][0] if receipt['findings'] else 'OBSERVATION_INCOMPLETE') and receipt['expectations_met'] is False
    assert receipt['items'][item]['status']=='UNAVAILABLE' and receipt['items'][item]['code']==code and item in receipt['items_not_complete'],receipt['items'][item]
def fact_not_observed(receipt,item,code):
    """An item without any signed expectation that could not be observed: said in the receipt, and it decides nothing."""
    assert receipt['items'][item]['status']=='UNAVAILABLE' and receipt['items'][item]['code']==code,receipt['items'][item]
    assert receipt['fact_items_not_observed']==[item] and receipt['items_not_complete']==[item] and receipt['findings']==[]
    assert receipt['status']==COMPLETE and receipt['code'] is None and receipt['expectations_met'] is True
def remove(host,path):host.tree.remove(path)
def replace(host,path,**attributes):
    host.tree.remove(path);return host.tree.add(path,**attributes)
def line_of(mode='PRE',prepare=None,**options):
    """What the real snippet prints for the fixture: the dict, to be changed by a hostile container."""
    m,docs,host=fresh(mode,**options);seen=[]
    if prepare is not None:prepare(host)
    real=host.docker.on_run
    def capture(call):
        code,out=real(call);seen.append(out);return code,out
    host.docker.on_run=capture;receipt=docs.run(host);assert receipt['status']==COMPLETE
    return json.loads(seen[0])
def answer(value,code=0):
    raw=value if type(value) is bytes else f.canonical(value)+b'\n'
    return lambda call:(code,raw)


# ---------------------------------------------------------------- complete runs
BASE_ITEMS=['boot','containers','deploy_files','directories_stable','directory:DEPLOY_TREE','directory:LIVE_PARENT','directory:LOCK_DIRECTORY','directory:RELEASE_PARENT','image',
            'live_target','lock','maintenance_pin','reboot_pending','reboot_required','release_target','verify','worker','worker_environment']
def test_dry_run_completes_before_and_after_provisioning_and_says_what_it_ran():
    m,docs,host,receipt=ran('PRE')
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['findings'],receipt['mode'])==(COMPLETE,m.PRE_OUTCOME,None,[],'PRE')
    assert receipt['expectations_met'] is True and receipt['gates_first_session_readback'] is False,'a dry run is never the readback of the first session'
    assert sorted(receipt['items'])==sorted(BASE_ITEMS+['render','directory:BIND_PROBE']) and receipt['items_omitted_by_the_plan']==['docker_config','journal','docker_config_after']
    assert receipt['dry_run']=='FULL' and receipt['effects']['rehearses_install_release_and_activate'] is True and receipt['fact_items_not_observed']==[]
    assert receipt['items']['live_target']=={'expected':'DIRECTORY_ABSENT','exists':False,'status':'COMPLETE','findings':[],'matches':True,'elapsed_ms':0}
    assert receipt['commands_started']=={'READ':6,'CONTAINER':1,'EFFECT':0} and receipt['containers_run']==1 and receipt['writes']==0
    assert receipt['mutating_calls']=={'issued':0,'succeeded':0,'failed_nothing_changed':0,'uncertain':0} and receipt['phase_reached']=='OBSERVATION'
    assert receipt['items']['release_target']=={'expected':'DIRECTORY_ABSENT','exists':False,'status':'COMPLETE','findings':[],'matches':True,'elapsed_ms':0}
    assert receipt['items']['verify']['release']=={'source':'STDIN','read':True,'bytes_equal_signed':True,'verified':True,'code':None,'mode_certified':True,
                                                    'epoch_equal':True,'first_session_equal':True,'ebar_bound':True}
    assert receipt['items']['verify']['binds']==1 and receipt['items']['verify']['probe']=={'valid':True,'code':None} and receipt['items']['lock']['state']=='FREE'
    assert receipt['facts_reported_not_gated']==m.FACTS_NOT_GATED
    m,docs,host,after=ran('PRE',provisioned=True,units=k11.UNITS,journal=k11.JOURNAL,floor=1<<30)
    assert (after['status'],after['outcome'])==(COMPLETE,m.PRE_OUTCOME) and after['commands_started']['READ']==9
    assert after['items']['journal']['exists'] is True and after['items']['journal']['at_or_above_the_floor'] is True and after['items']['journal']['bytes_available']==145315507*4096

def test_readback_completes_before_and_after_provisioning():
    m,docs,host,receipt=ran('POST')
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['findings'],receipt['mode'])==(COMPLETE,m.COMPLETE_OUTCOME,None,[],'POST')
    assert receipt['gates_first_session_readback'] is True and sorted(receipt['items'])==sorted(BASE_ITEMS)
    assert receipt['items_omitted_by_the_plan']==['directory:BIND_PROBE','docker_config','render','journal','docker_config_after'] and receipt['commands_started']=={'READ':4,'CONTAINER':1,'EFFECT':0}
    target=receipt['items']['release_target']
    assert target['directory']=={'type':'dir','uid':0,'gid':0,'mode_octal':'0700','on_the_device_of_its_parent':True,'entries':1,'entries_signed':1}
    assert target['file']=={'exists':True,'type':'file','uid':0,'gid':0,'mode_octal':'0600','links':1,'bytes_equal_signed':True}
    assert receipt['items']['verify']['release']['source']=='FILE' and receipt['items']['verify']['bind_source_stable'] is True and receipt['items']['verify']['binds']==1
    assert receipt['items']['verify']['policy']=={'hash_equal_signed':True,'controller_now':{'valid':True,'code':None},'controller_at':[{'valid':True,'code':None}]*3,
                                                   'assembler':{'valid':True,'code':None}}
    assert receipt['items']['directories_stable']['directories']=={'DEPLOY_TREE':True,'LIVE_PARENT':True,'LOCK_DIRECTORY':True,'RELEASE_DIRECTORY':True,'RELEASE_PARENT':True}
    assert receipt['dry_run'] is None and receipt['effects']['rehearses_install_release_and_activate'] is False and receipt['effects']['limits'] is None
    m,docs,host,after=ran('POST',provisioned=True,units=k11.UNITS,journal=k11.JOURNAL,render=True)
    assert (after['status'],after['outcome'])==(COMPLETE,m.COMPLETE_OUTCOME) and after['items_omitted_by_the_plan']==['directory:BIND_PROBE','docker_config','docker_config_after']
    assert after['items']['unit:c3po-massive.timer']['properties']['UnitFileState']=='disabled' and after['items']['unit:docker.service']['properties']['ActiveState']=='active'

def test_commands_are_the_signed_rows_word_for_word_and_the_container_comes_first():
    m,docs,host,receipt=ran('POST',provisioned=True,units=k11.UNITS,render=True);go16=docs.go16();name='hostops02-k11-'+go16
    argv=[entry['argv'] for entry in host.commands];docker='/usr/bin/docker'
    assert argv[0]==[docker,'run','--rm','-i','--pull','never','--init','--user','0:0','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
                     '--name',name,'--mount','type=bind,source=%s,target=%s,readonly'%(k11.RELEASE_HOST,k11.TARGET),hostemu.BACKEND,'python','-I','-B','-']
    assert host.commands[0]['seconds']==40 and host.commands[0]['stdin']==m.frame_of(docs.plan,docs.pins().request) and host.commands[0]['variables']=={}
    assert argv[1][:4]==[docker,'ps','-a','--no-trunc'] and argv[2][:3]==[docker,'image','inspect'] and argv[2][-1]=='c3po/backend:production'
    assert argv[3][:3]==[docker,'container','inspect'] and argv[3][-1]==hostemu.WORKER and argv[4][:3]==[docker,'container','inspect'] and len(argv[4][-1])==64
    compose=[docker,'compose','--project-name','c3po','--env-file',hostemu.ENV_FILE,'-f',hostemu.COMPOSE_FILE]
    assert argv[5]==compose+['config','--format','json'] and argv[6]==compose+['-f','-','config','--format','json']
    assert (host.commands[5]['stdin'],host.commands[6]['stdin'])==(None,k11.override_bytes()) and host.commands[5]['variables']==host.commands[6]['variables']=={'C3PO_BUILD_SHA':k11.REVISION}
    assert (host.commands[5]['seconds'],host.commands[5]['limit'])==(15,1048576) and all(entry['seconds']==8 for entry in host.commands[1:5]+host.commands[7:])
    show=['-p','Id','-p','LoadState','-p','ActiveState','-p','SubState','-p','UnitFileState','-p','FragmentPath','-p','DropInPaths','-p','WantedBy','-p','RequiredBy','-p','TriggeredBy']
    assert argv[7:]==[['/usr/bin/systemctl','show',unit]+show for unit in k11.UNITS] and len(argv)==10
    assert all(entry['docker_config'] is None for entry in host.commands) and host.docker.compose.calls[0]['files']==[hostemu.COMPOSE_FILE]
    assert host.docker.runs[0].mounts==[{'source':k11.RELEASE_HOST,'target':k11.TARGET,'read_only':True}] and host.docker.runs[0].name==name
    # no open for writing, no creating call; the lock was only probed with a shared request and released
    assert all(not entry[2]&hostemu.WRITE_FLAGS for entry in host.log if entry[0]=='open') and not [entry for entry in host.log if entry[0] in hostemu.MUTATING]
    import fcntl
    assert [entry[2] for entry in host.log if entry[0]=='flock']==[fcntl.LOCK_SH|fcntl.LOCK_NB,fcntl.LOCK_UN]
    m,docs,host,pre=ran('PRE',probe=None);assert '--mount' not in host.commands[0]['argv'] and host.commands[0]['argv'][-5:]==[hostemu.BACKEND,'python','-I','-B','-']
    m,docs,host,pre=ran('PRE');argv=host.commands[0]['argv'];assert argv[argv.index('--mount')+1]=='type=bind,source=%s,target=%s,readonly'%(k11.PROBE,k11.PROBE_TARGET) and argv.count('--mount')==1
    order=[entry[0] for entry in host.log];assert 'run' in order and order.index('run')>order.index('lstat'),'the walks come before the first command'

def test_what_the_plan_leaves_out_is_not_observed_and_the_receipt_says_so():
    m,docs,host,receipt=ran('PRE',policy=None,environment=False,lock=False,probe=None,live=False,limits=None)
    assert receipt['status']==COMPLETE and receipt['items_omitted_by_the_plan']==['directory:LIVE_PARENT','directory:BIND_PROBE','live_target','docker_config','worker_environment','journal','lock','docker_config_after']
    assert (receipt['outcome'],receipt['dry_run'])==(m.PRE_REDUCED_OUTCOME,'REDUCED') and receipt['effects']['rehearses_install_release_and_activate'] is False
    assert 'lock' not in receipt['items'] and 'worker_environment' not in receipt['items'] and receipt['items']['verify']['policy'] is None
    assert not [entry for entry in host.log if entry[0]=='flock'] and len([entry for entry in host.commands if entry['argv'][1:3]==['container','inspect']])==1
    m,docs,host,receipt=ran('POST',render=False);assert not host.docker.compose.calls and 'render' not in receipt['items']
    assert receipt['items']['worker_environment']['live_names_equal_to_the_intended_values'] is None,'without a render only the presence of the four names is learnt'
    template=[entry for entry in host.commands if entry['argv'][1:3]==['container','inspect']][1]['argv'][4]
    assert all('"%s="'%key in template for key in k11.KEYS) and k11.POLICY_CONTAINER not in template


# ---------------------------------------------------------------- directories: signed rows, observed rows, hostile states
def test_boot_of_the_evidence_and_rows_compared_without_the_device_after_a_reboot():
    def other_boot(host):host.tree.get('/proc/sys/kernel/random/boot_id').content=bytearray(b'1f8fad5b-d9cb-469f-a165-70867728950e\n')
    m,docs,host,receipt=ran('PRE',other_boot);finding(receipt,'EVIDENCE_FROM_EARLIER_BOOT','boot')
    assert receipt['items']['boot']=={'equal_to_the_evidence':False,'device_numbers_compared':False,'status':'COMPLETE','findings':['EVIDENCE_FROM_EARLIER_BOOT'],'matches':False,'elapsed_ms':0}
    def renumbered(host):
        other_boot(host);host.tree.get(hostemu.DATA).dev=999;host.vfs[999]=host.vfs[D]
        for child in host.tree.get(hostemu.DATA).children.values():child.dev=999
    m,docs,host,receipt=ran('PRE',renumbered);assert receipt['findings']==['EVIDENCE_FROM_EARLIER_BOOT'] and receipt['items']['directory:RELEASE_PARENT']['as_signed'] is True
    def renumbered_same_boot(host):host.tree.get(hostemu.DATA).dev=999;host.vfs[999]=host.vfs[D]
    m,docs,host,receipt=ran('PRE',renumbered_same_boot);unavailable(receipt,'release_target','DIRECTORY_NOT_HELD')
    assert receipt['findings']==['PARENT_IDENTITY_MISMATCH'] and receipt['code']=='PARENT_IDENTITY_MISMATCH','the finding names the cause; the outcome says that not everything was observed'
    assert receipt['items']['directory:RELEASE_PARENT']['fields_that_differ']=={'device':True,'inode':False,'uid':False,'gid':False,'mode':False}

@pytest.mark.parametrize('key,path',[('RELEASE_PARENT',hostemu.DATA),('DEPLOY_TREE',hostemu.DEPLOY),('LOCK_DIRECTORY',hostemu.LOCK_DIRECTORY)])
def test_a_directory_that_is_not_the_signed_one_is_a_finding_with_booleans_and_what_depends_on_it_is_unavailable(key,path):
    for change,field in ((lambda node:setattr(node,'ino',node.ino+1),'inode'),(lambda node:setattr(node,'uid',0 if node.uid else 1000),'uid'),
                         (lambda node:setattr(node,'gid',7),'gid'),(lambda node:setattr(node,'mode',0o750),'mode')):
        m,docs,host,receipt=ran('PRE',lambda host:change(host.tree.get(path)));item=receipt['items']['directory:'+key]
        assert 'PARENT_IDENTITY_MISMATCH' in item['findings'] and item['as_signed'] is False and item['held'] is False and item['status']=='COMPLETE'
        assert item['fields_that_differ']=={name:name==field for name in ('device','inode','uid','gid','mode')} and 'owner_uid' not in item
        assert item['components_observed']==item['components'] and receipt['status']==PARTIAL
        dependent={'RELEASE_PARENT':'release_target','DEPLOY_TREE':'deploy_files','LOCK_DIRECTORY':'lock'}[key]
        assert receipt['items'][dependent]=={'status':'UNAVAILABLE','code':'DIRECTORY_NOT_HELD','elapsed_ms':0}
        assert key not in receipt['items']['directories_stable']['directories']
    for prepare,code in ((lambda host:remove(host,path),'PARENT_MISSING'),(lambda host:replace(host,path,kind='symlink',mode=0o777),'PARENT_SYMLINK_COMPONENT'),
                         (lambda host:replace(host,path,kind='file'),'PARENT_NOT_DIRECTORY'),(lambda host:replace(host,path,kind='fifo'),'PARENT_NOT_DIRECTORY')):
        m,docs,host,receipt=ran('PRE',prepare);item=receipt['items']['directory:'+key]
        assert item['findings']==[code] and item['held'] is False and item['as_signed'] is False and code in receipt['findings'] and receipt['status']==PARTIAL

def test_a_middle_component_replaced_by_a_link_is_found_and_never_followed():
    def linked(host):
        replace(host,hostemu.DEPLOY+'/runtime',kind='symlink',mode=0o777).target='/mnt/day-d-data'
    m,docs,host,receipt=ran('PRE',linked);item=receipt['items']['directory:LOCK_DIRECTORY']
    assert item['findings']==['PARENT_SYMLINK_COMPONENT'] and item['components_observed']==4 and not [entry for entry in host.log if entry[0]=='readlink']
    assert receipt['items']['lock']['code']=='DIRECTORY_NOT_HELD'

def test_without_signed_rows_the_walk_records_what_it_finds_and_says_whether_a_write_could_sign_it():
    m,docs,host,receipt=ran('PRE',signed_rows=False);assert receipt['status']==COMPLETE
    for key,root in (('RELEASE_PARENT',hostemu.DATA),('DEPLOY_TREE',hostemu.DEPLOY),('LOCK_DIRECTORY',hostemu.LOCK_DIRECTORY)):
        item=receipt['items']['directory:'+key]
        assert (item['rows_signed'],item['as_signed'],item['held'],item['rows_acceptable_to_a_write'],item['rows_refusal'])==(False,None,True,True,None) and item['path']==root
    assert receipt['items']['directory:RELEASE_PARENT']=={'path':hostemu.DATA,'components':3,'components_observed':3,'rows_signed':False,'as_signed':None,'held':True,
        'owner_uid':1000,'owner_gid':1000,'mode_octal':'0755','device_changes':1,'mount_point_by_device_change':hostemu.DATA,'leaf_is_a_mount_point':True,
        'world_writable_without_sticky':False,'setgid':False,'rows_acceptable_to_a_write':True,'rows_refusal':None,'judged_as_receiving_an_entry':True,
        'mount_point_is_the_data_volume':True,'free_bytes_floor':1048576,'free_inodes_floor':8,'entries':5,'bytes_available':13200816*4096,'inodes_available':None,
        'status':'COMPLETE','findings':[],'matches':True,'elapsed_ms':0}
    assert (receipt['items']['directory:DEPLOY_TREE']['judged_as_receiving_an_entry'],receipt['items']['directory:LIVE_PARENT']['judged_as_receiving_an_entry'])==(False,True)
    assert receipt['items']['directory:DEPLOY_TREE']['mount_point_is_the_data_volume'] is None
    # Rows no write could sign, in a directory a write of Monday still creates in: a finding on Sunday, not a surprise
    # at Monday's binding. The release parent is judged as install_release judges it (no setgid; the data volume a mount point).
    for prepare,code,flag in ((lambda host:setattr(host.tree.get(hostemu.DATA),'mode',0o777),'CHAIN_ROW_WORLD_WRITABLE','world_writable_without_sticky'),
                              (lambda host:setattr(host.tree.get(hostemu.DATA),'mode',0o2775),'PARENT_SETGID','setgid'),
                              (lambda host:setattr(host.tree.get('/mnt'),'mode',0o775),'CHAIN_ROW_UNSAFE',None),
                              (lambda host:(setattr(host.tree.get(hostemu.DATA),'dev',hostemu.ROOT_DEVICE),host.vfs.__setitem__(hostemu.ROOT_DEVICE,host.vfs[D])),'DATA_VOLUME_NOT_A_MOUNT_POINT',None)):
        m,docs,host,receipt=ran('PRE',prepare,signed_rows=False,live=False);item=receipt['items']['directory:RELEASE_PARENT']
        finding(receipt,'DIRECTORY_NOT_ACCEPTABLE_TO_THE_WRITE_THAT_FOLLOWS','directory:RELEASE_PARENT')
        assert item['rows_refusal']==code and item['rows_acceptable_to_a_write'] is False and (flag is None or item[flag] is True)
        assert item['mount_point_is_the_data_volume'] is (code!='DATA_VOLUME_NOT_A_MOUNT_POINT')
        # after install_release the same rows of the release parent are a fact: nothing is created there any more
        m,docs,host,receipt=ran('POST',prepare,signed_rows=False,live=False);item=receipt['items']['directory:RELEASE_PARENT']
        assert item['rows_refusal']==code and item['rows_acceptable_to_a_write'] is False and item['findings']==[]
        assert receipt['findings']==(['RELEASE_DIRECTORY_IS_A_MOUNT_POINT'] if code=='DATA_VOLUME_NOT_A_MOUNT_POINT' else []),'in the emulation the installed directory keeps the device of the volume'
    # the live parent receives activate's directory in both modes: a setgid parent is what activate refuses at its binding
    for mode in ('PRE','POST'):
        m,docs,host,receipt=ran(mode,lambda host:setattr(host.tree.get(k11.LIVE_PARENT),'mode',0o2700),signed_rows=False);item=receipt['items']['directory:LIVE_PARENT']
        finding(receipt,'DIRECTORY_NOT_ACCEPTABLE_TO_THE_WRITE_THAT_FOLLOWS','directory:LIVE_PARENT');assert (item['rows_refusal'],item['setgid'])==('PARENT_SETGID',True)
    # a directory that receives nothing is judged without the setgid rule, and never gated
    m,docs,host,receipt=ran('PRE',lambda host:setattr(host.tree.get(hostemu.LOCK_DIRECTORY),'mode',0o2755),signed_rows=False)
    assert receipt['status']==COMPLETE and receipt['items']['directory:LOCK_DIRECTORY']['rows_acceptable_to_a_write'] is True and receipt['items']['directory:LOCK_DIRECTORY']['setgid'] is True
    for prepare,code in ((lambda host:remove(host,hostemu.LOCK_DIRECTORY),'PARENT_MISSING'),(lambda host:replace(host,hostemu.LOCK_DIRECTORY,kind='symlink'),'SYMLINK_COMPONENT'),
                         (lambda host:replace(host,hostemu.LOCK_DIRECTORY,kind='file'),'COMPONENT_NOT_DIRECTORY')):
        m,docs,host,receipt=ran('PRE',prepare,signed_rows=False);item=receipt['items']['directory:LOCK_DIRECTORY']
        assert item['findings']==[code] and item['held'] is False and item['as_signed'] is None

def test_identities_are_booleans_and_counts_unless_the_request_signs_rows_in_receipt():
    m,docs,host,receipt=ran('POST',provisioned=True,journal=k11.JOURNAL,units=k11.UNITS,render=True);text=json.dumps(receipt['items'])
    for word in ('"device"','"inode"','"id"','"host_pid"','observed_rows'):assert word not in text,word
    numbers={str(node.ino) for path in host.tree.paths() for node in [host.tree.get(path)]}|{str(D),str(hostemu.ROOT_DEVICE)}
    values=[];stack=[receipt['items']]
    while stack:
        value=stack.pop()
        if type(value) is dict:stack.extend(value.values())
        elif type(value) is list:stack.extend(value)
        else:values.append(str(value))
    assert not [value for value in values if value in numbers and value not in ('1','2','3','4','8')],'no device or inode number is among the observed values'
    assert not [row['Id'] for row in host.docker.containers if row['Id'] in text] and hostemu.BACKEND not in text
    m,docs,host,receipt=ran('PRE',rows_in_receipt=True)
    assert receipt['items']['directory:LOCK_DIRECTORY']['observed_rows']==hostemu.rows(host,hostemu.LOCK_DIRECTORY) and receipt['status']==COMPLETE
    m,docs,host,receipt=ran('PRE',lambda host:remove(host,hostemu.LOCK_DIRECTORY),rows_in_receipt=True)
    assert receipt['items']['directory:LOCK_DIRECTORY']['observed_rows']==hostemu.rows(host,hostemu.DEPLOY+'/runtime'),'what was seen before the missing component'

def test_a_held_directory_replaced_during_the_run_is_found_at_the_end():
    def swap(path):
        def prepare(host):
            real=host.docker.on_run
            def during(call):
                host.tree.get(path).ino+=1000;return real(call)
            host.docker.on_run=during
        return prepare
    m,docs,host=fresh('PRE');swap(hostemu.DEPLOY)(host);receipt=docs.run(host)
    finding(receipt,'DIRECTORY_REPLACED_DURING_RUN','directories_stable')
    assert receipt['items']['directories_stable']['directories']=={'BIND_PROBE':True,'DEPLOY_TREE':False,'LIVE_PARENT':True,'LOCK_DIRECTORY':False,'RELEASE_PARENT':True}
    m,docs,host=fresh('POST');swap(k11.RELEASE_HOST)(host);receipt=docs.run(host)
    assert 'BIND_SOURCE_REPLACED_DURING_RUN' in receipt['findings'] and receipt['items']['verify']['bind_source_stable'] is False
    assert receipt['items']['directories_stable']['directories']['RELEASE_DIRECTORY'] is False and 'DIRECTORY_REPLACED_DURING_RUN' in receipt['findings']


# ---------------------------------------------------------------- the place of the release
@pytest.mark.parametrize('kind',['dir','file','symlink','fifo'])
def test_dry_run_finds_anything_that_already_stands_where_install_release_will_create(kind):
    m,docs,host,receipt=ran('PRE',lambda host:host.tree.add(k11.RELEASE_HOST,kind=kind,dev=D))
    finding(receipt,'RELEASE_TARGET_ALREADY_EXISTS','release_target');assert receipt['items']['release_target']['type']=={'fifo':'other'}.get(kind,kind)
    assert receipt['items']['verify']['release']['verified'] is True,'the rest of the dry run is still made'

POST_STATES=[(lambda host:remove(host,k11.RELEASE_HOST),'RELEASE_DIRECTORY_ABSENT'),
             (lambda host:replace(host,k11.RELEASE_HOST,kind='symlink',dev=D),'RELEASE_DIRECTORY_NOT_A_DIRECTORY'),
             (lambda host:replace(host,k11.RELEASE_HOST,kind='file',dev=D,content=k11.RELEASE),'RELEASE_DIRECTORY_NOT_A_DIRECTORY'),
             (lambda host:setattr(host.tree.get(k11.RELEASE_HOST),'uid',1000),'RELEASE_DIRECTORY_METADATA'),
             (lambda host:setattr(host.tree.get(k11.RELEASE_HOST),'gid',1000),'RELEASE_DIRECTORY_METADATA'),
             (lambda host:setattr(host.tree.get(k11.RELEASE_HOST),'mode',0o755),'RELEASE_DIRECTORY_METADATA'),
             (lambda host:setattr(host.tree.get(k11.RELEASE_HOST),'dev',D+1),'RELEASE_DIRECTORY_IS_A_MOUNT_POINT'),
             (lambda host:host.tree.add(k11.RELEASE_HOST+'/install.started.json',kind='file',dev=D,mode=0o600),'RELEASE_DIRECTORY_ENTRIES'),
             (lambda host:host.tree.add(k11.RELEASE_HOST+'/.hostops-0123456789abcdef-0.partial',kind='file',dev=D,mode=0o600),'RELEASE_DIRECTORY_ENTRIES'),
             (lambda host:remove(host,k11.RELEASE_HOST+'/'+k11.RELEASE_FILE),'RELEASE_FILE_ABSENT'),
             (lambda host:replace(host,k11.RELEASE_HOST+'/'+k11.RELEASE_FILE,kind='symlink',dev=D),'RELEASE_FILE_NOT_REGULAR'),
             (lambda host:replace(host,k11.RELEASE_HOST+'/'+k11.RELEASE_FILE,kind='fifo',dev=D),'RELEASE_FILE_NOT_REGULAR'),
             (lambda host:replace(host,k11.RELEASE_HOST+'/'+k11.RELEASE_FILE,kind='dir',dev=D),'RELEASE_FILE_NOT_REGULAR'),
             (lambda host:setattr(host.tree.get(k11.RELEASE_HOST+'/'+k11.RELEASE_FILE),'mode',0o644),'RELEASE_FILE_METADATA'),
             (lambda host:setattr(host.tree.get(k11.RELEASE_HOST+'/'+k11.RELEASE_FILE),'mode',0o400),'RELEASE_FILE_METADATA'),
             (lambda host:setattr(host.tree.get(k11.RELEASE_HOST+'/'+k11.RELEASE_FILE),'uid',1000),'RELEASE_FILE_METADATA'),
             (lambda host:setattr(host.tree.get(k11.RELEASE_HOST+'/'+k11.RELEASE_FILE),'gid',1000),'RELEASE_FILE_METADATA'),
             (lambda host:setattr(host.tree.get(k11.RELEASE_HOST+'/'+k11.RELEASE_FILE),'nlink',2),'RELEASE_FILE_METADATA'),
             (lambda host:setattr(host.tree.get(k11.RELEASE_HOST+'/'+k11.RELEASE_FILE),'content',bytearray(b'x'*65537)),'RELEASE_FILE_TOO_LARGE'),
             (lambda host:setattr(host.tree.get(k11.RELEASE_HOST+'/'+k11.RELEASE_FILE),'content',bytearray(k11.RELEASE[:-1]+b' ')),'RELEASE_FILE_BYTES_MISMATCH'),
             (lambda host:setattr(host.tree.get(k11.RELEASE_HOST+'/'+k11.RELEASE_FILE),'content',bytearray(k11.release_bytes(authorization_ref='FOREIGN'))),'RELEASE_FILE_BYTES_MISMATCH'),
             (lambda host:setattr(host.tree.get(k11.RELEASE_HOST+'/'+k11.RELEASE_FILE),'content',bytearray()),'RELEASE_FILE_BYTES_MISMATCH')]
@pytest.mark.parametrize('index',range(len(POST_STATES)))
def test_readback_finds_every_way_the_installed_release_is_not_what_install_release_leaves(index):
    prepare,code=POST_STATES[index];m,docs,host,receipt=ran('POST',prepare)
    assert receipt['status']==PARTIAL and code in receipt['findings'] and code in receipt['items']['release_target']['findings'] and receipt['gates_first_session_readback'] is False
    if code in ('RELEASE_DIRECTORY_ABSENT','RELEASE_DIRECTORY_NOT_A_DIRECTORY'):
        assert receipt['items']['verify']=={'status':'UNAVAILABLE','code':'RELEASE_DIRECTORY_NOT_HELD','elapsed_ms':0} and host.docker.runs==[],'no directory is bound that the run does not hold'
    else:assert receipt['items']['verify']['started'] is True and host.docker.runs[0].mounts[0]['read_only'] is True

def test_what_the_worker_s_own_reader_says_about_a_file_it_would_refuse():
    """The container reads the installed file with the reader of the deployed worker: a file that reader refuses, or
    other bytes, is found there as well as on the host."""
    file=k11.RELEASE_HOST+'/'+k11.RELEASE_FILE
    m,docs,host,receipt=ran('POST',lambda host:setattr(host.tree.get(file),'mode',0o644));release=receipt['items']['verify']['release']
    assert (release['read'],release['verified'],release['code'])==(False,False,'RELEASE_FILE_NOT_PRIVATE_OR_INVALID')
    assert {'RELEASE_FILE_METADATA','RELEASE_NOT_READ_IN_THE_CONTAINER','RELEASE_NOT_VERIFIED'}<=set(receipt['findings'])
    m,docs,host,receipt=ran('POST',lambda host:setattr(host.tree.get(file),'content',bytearray(k11.release_bytes(authorization_ref='FOREIGN'))));release=receipt['items']['verify']['release']
    assert (release['read'],release['bytes_equal_signed'],release['verified'],release['code'])==(True,False,False,'RELEASE_HASH_MISMATCH')
    assert {'RELEASE_FILE_BYTES_MISMATCH','RELEASE_BYTES_NOT_THE_SIGNED_ONES','RELEASE_NOT_VERIFIED'}<=set(receipt['findings'])
    m,docs,host,receipt=ran('POST',lambda host:replace(host,file,kind='symlink',dev=D));release=receipt['items']['verify']['release']
    assert (release['read'],release['code'])==(False,'OSError') and 'RELEASE_NOT_READ_IN_THE_CONTAINER' in receipt['findings']

def test_release_directory_that_changes_while_it_is_opened_is_an_observation_that_failed():
    m,docs,host=fresh('POST');seen=[]
    def hook(host,name,detail,calls):
        if name=='lstat' and detail[0]==k11.RELEASE_HOST and not seen:
            seen.append(1);host.hook=lambda host,name,detail,calls:(host.tree.get(k11.RELEASE_HOST).__setattr__('ino',77777) if name=='open' and detail[0]==k11.RELEASE_HOST else None)
    host.hook=hook;receipt=docs.run(host)
    assert receipt['items']['release_target']['code']=='RELEASE_DIRECTORY_CHANGED_DURING_READ' and receipt['items']['verify']['code']=='RELEASE_DIRECTORY_NOT_HELD' and host.fds=={}


# ---------------------------------------------------------------- the container: what the deployed code says
def knob(**knobs):
    def prepare(host):host.docker.on_run=k11.Container(k11.fake_tree(**knobs))
    return prepare
@pytest.mark.parametrize('mode',['PRE','POST'])
def test_what_the_deployed_code_refuses_is_a_finding_with_its_own_constant_code(mode):
    m,docs,host,receipt=ran(mode,knob(verify_error='READINESS_FIRST_SESSION_MISMATCH'));finding(receipt,'RELEASE_NOT_VERIFIED','verify')
    assert receipt['items']['verify']['release']['code']=='READINESS_FIRST_SESSION_MISMATCH' and receipt['items']['verify']['release']['read'] is True
    m,docs,host,receipt=ran(mode,knob(package='a'*64));assert {'PACKAGE_NOT_THE_SIGNED_ONE','RELEASE_NOT_VERIFIED','POLICY_REFUSED_BY_THE_CONTROLLER','POLICY_REFUSED_BY_THE_ASSEMBLER'}<=set(receipt['findings'])
    assert receipt['items']['verify']['release']['code']=='RELEASE_IMPLEMENTATION_PACKAGE_MISMATCH' and receipt['items']['verify']['package_equal_signed'] is False
    assert receipt['items']['verify']['policy']['controller_at']==[{'valid':False,'code':'LIVE_POLICY_INVALID'}]*3 and receipt['items']['verify']['policy']['assembler']['code']=='POLICY_PACKAGE'
    m,docs,host,receipt=ran(mode,knob(assembler_epoch='R2D2-V2-SHADOW-2026-09-28'));assert 'RELEASE_SCOPE_NOT_AS_SIGNED' in receipt['findings'] and receipt['items']['verify']['release']['epoch_equal'] is False
    m,docs,host,receipt=ran(mode,knob(policy_error='LIVE_POLICY_INVALID'));finding(receipt,'POLICY_REFUSED_BY_THE_CONTROLLER','verify')
    assert receipt['items']['verify']['policy']['controller_now']=={'valid':False,'code':'LIVE_POLICY_INVALID'} and receipt['items']['verify']['release']['verified'] is True
    m,docs,host,receipt=ran(mode,knob(assembler_error='POLICY_NOT_EPOCH_WIDE'));finding(receipt,'POLICY_REFUSED_BY_THE_ASSEMBLER','verify')
    assert receipt['items']['verify']['policy']['assembler']=={'valid':False,'code':'POLICY_NOT_EPOCH_WIDE'}

def test_release_without_the_bar_amendment_or_a_policy_the_validators_refuse_is_found_by_the_deployed_code():
    release=k11.release_bytes(ebar_amendment_sha=None);policy=k11.policy_bytes(release)
    m,docs,host,receipt=ran('PRE',release=release,policy=policy);finding(receipt,'RELEASE_SCOPE_NOT_AS_SIGNED','verify')
    assert receipt['items']['verify']['release']['ebar_bound'] is False and receipt['items']['verify']['release']['verified'] is True
    # a policy whose capacity the controller refuses; one whose canonical hash the assembler refuses in the container
    m,docs,host,receipt=ran('POST',policy=k11.policy_bytes(capacity=0));finding(receipt,'POLICY_REFUSED_BY_THE_CONTROLLER','verify')
    m,docs,host,receipt=ran('POST',knob(assembler_error='POLICY_HASH'));finding(receipt,'POLICY_REFUSED_BY_THE_ASSEMBLER','verify');assert receipt['items']['verify']['policy']['assembler']['code']=='POLICY_HASH'
    # the window of the policy at the instant of the run is a fact, not a gate: every signed instant is inside
    later=k11.policy_bytes(valid_from='2026-10-05T08:00:00+00:00',valid_until='2026-10-09T21:00:00+00:00')
    m,docs,host,receipt=ran('POST',policy=later);policy=receipt['items']['verify']['policy']
    if policy['controller_now']['valid'] is False:assert policy['controller_now']['code']=='LIVE_POLICY_OUTSIDE_WINDOW' and receipt['status']==COMPLETE

def test_a_container_that_fails_says_so_with_a_constant_and_never_with_a_message():
    m,docs,host,receipt=ran('PRE',knob(import_error=True));finding(receipt,'VERIFY_SNIPPET_FAILED','verify')
    assert (receipt['items']['verify']['snippet_code'],receipt['items']['verify']['returncode'])==('ImportError',1) and 'cannot be imported' not in json.dumps(receipt)
    m,docs,host,receipt=ran('PRE',knob(calendar_error=True));assert receipt['items']['verify']['snippet_code']=='RuntimeError' and '/some/path' not in json.dumps(receipt)
    # docker's own statuses: the engine could not run the container (the image is not present by that ID)
    m,docs,host,receipt=ran('PRE',lambda host:host.docker.images[0].__setitem__('Id','sha256:'+'ab'*32))
    assert 'VERIFY_ENGINE_FAILURE' in receipt['items']['verify']['findings'] and (receipt['items']['verify']['returncode'],receipt['items']['verify']['engine_failure'])==(125,True)
    for code,raw in ((3,b''),(1,b'Traceback (most recent call last):\n  File "<stdin>"\n'),(142,b''),(137,b'{"status":"DONE"}\n'),(1,b'{"status":"FAILED","code":"a message with spaces"}\n'),
                     (1,b'{"status":"FAILED","code":"X","more":1}\n'),(2,b'[]\n')):
        m,docs,host,receipt=ran('PRE',lambda host:setattr(host.docker,'on_run',answer(raw,code)))
        assert receipt['items']['verify']['findings']==['VERIFY_RUN_FAILED'] and receipt['items']['verify']['returncode']==code and 'snippet_code' not in receipt['items']['verify']
        assert 'Traceback' not in json.dumps(receipt) and 'a message' not in json.dumps(receipt)

def test_hostile_output_of_the_container_is_an_observation_that_failed_never_a_verified_release():
    good=line_of('POST')
    def changed(**changes):return dict(good,**changes)
    def release(**changes):return changed(release=dict(good['release'],**changes))
    def policy(**changes):return changed(policy=dict(good['policy'],**changes))
    hostile=[b'',b'not json\n',f.canonical(good),f.canonical(good)+b'\n'+f.canonical(good)+b'\n',b'[]\n',b'{"status":"DONE","status":"DONE"}\n',
             changed(status='FAILED'),changed(extra=1),{key:value for key,value in good.items() if key!='facts'},changed(context_request_sha256='9'*64),
             changed(package_equal_signed='true'),changed(package_equal_signed=1),release(source='STDIN'),release(verified=1),release(read=None),release(extra=True),
             release(code='a message with spaces'),release(code='RELEASE_HASH_MISMATCH'),release(verified=False),release(verified=False,code='a message with spaces'),
             release(verified=False,code=7),changed(probe={'valid':True,'code':None}),policy(controller_at=[{'valid':'yes','code':None}]+good['policy']['controller_at'][1:]),
             policy(controller_at=[None]+good['policy']['controller_at'][1:]),policy(assembler={'valid':True,'code':None,'extra':1}),policy(controller_now={'valid':True,'code':None,'at':'x'}),
             {key:value for key,value in release().items()}|{'release':{}},
             changed(release=None),changed(facts={'python':'3.12.14'}),changed(facts=dict(good['facts'],python='3.12')),changed(facts=dict(good['facts'],calendar_version='4 13')),
             changed(facts=dict(good['facts'],calendar_version='')),changed(policy=None),policy(hash_equal_signed=1),policy(controller_at=good['policy']['controller_at'][:2]),
             policy(controller_at=good['policy']['controller_at']+[{'valid':True,'code':None}]),policy(controller_at='x'),policy(assembler={'valid':True}),
             policy(assembler={'valid':'yes','code':None}),policy(controller_now={'valid':False,'code':'spaces in code'}),policy(controller_now=None),policy(extra=1)]
    for index,value in enumerate(hostile):
        m,docs,host,receipt=ran('POST',lambda host:setattr(host.docker,'on_run',answer(value)))
        unavailable(receipt,'verify','VERIFY_OUTPUT_INVALID');assert receipt['items']['verify']['returned'] is True and receipt['findings']==[],index
    # too much output is cut by the runner at the limit of the class
    m,docs,host,receipt=ran('POST',lambda host:setattr(host.docker,'on_run',answer(b'x'*65537+b'\n')));unavailable(receipt,'verify','COMMAND_OUTPUT_LIMIT')
    # and a container that answers for a plan without a policy as if it had one
    without=dict(line_of('PRE',policy=None),policy=good['policy'])
    m,docs,host,receipt=ran('PRE',lambda host:setattr(host.docker,'on_run',answer(without)),policy=None);unavailable(receipt,'verify','VERIFY_OUTPUT_INVALID')

def test_a_well_formed_line_that_says_no_is_believed_item_by_item():
    good=line_of('POST')
    for changes,code in ((dict(package_equal_signed=False),'PACKAGE_NOT_THE_SIGNED_ONE'),
                         (dict(release=dict(good['release'],bytes_equal_signed=False)),'RELEASE_BYTES_NOT_THE_SIGNED_ONES'),
                         (dict(release=dict(good['release'],read=False,verified=False,code='OSError',bytes_equal_signed=False)),'RELEASE_NOT_READ_IN_THE_CONTAINER'),
                         (dict(release=dict(good['release'],mode_certified=False)),'RELEASE_SCOPE_NOT_AS_SIGNED'),(dict(release=dict(good['release'],first_session_equal=False)),'RELEASE_SCOPE_NOT_AS_SIGNED'),
                         (dict(release=dict(good['release'],epoch_equal=False)),'RELEASE_SCOPE_NOT_AS_SIGNED'),(dict(release=dict(good['release'],ebar_bound=False)),'RELEASE_SCOPE_NOT_AS_SIGNED'),
                         (dict(policy=dict(good['policy'],hash_equal_signed=False)),'POLICY_BYTES_NOT_THE_SIGNED_ONES'),
                         (dict(policy=dict(good['policy'],controller_at=good['policy']['controller_at'][:2]+[{'valid':False,'code':'LIVE_POLICY_OUTSIDE_WINDOW'}])),'POLICY_REFUSED_BY_THE_CONTROLLER'),
                         (dict(policy=dict(good['policy'],assembler={'valid':False,'code':'POLICY_HASH'})),'POLICY_REFUSED_BY_THE_ASSEMBLER')):
        m,docs,host,receipt=ran('POST',lambda host:setattr(host.docker,'on_run',answer(dict(good,**changes))));finding(receipt,code,'verify')
        assert receipt['findings']==sorted({code}|({'RELEASE_NOT_VERIFIED'} if code=='RELEASE_NOT_READ_IN_THE_CONTAINER' else set()))
    now=dict(good,policy=dict(good['policy'],controller_now={'valid':False,'code':'LIVE_POLICY_OUTSIDE_WINDOW'}))
    m,docs,host,receipt=ran('POST',lambda host:setattr(host.docker,'on_run',answer(now)));assert receipt['status']==COMPLETE,'the instant of the run is a fact'

def test_container_that_does_not_start_or_does_not_return_and_what_may_be_left():
    m,docs,host,receipt=ran('PRE',lambda host:host.hang.add(('run','--rm')))
    assert receipt['items']['verify']=={'started':True,'returned':False,'returncode':None,'binds':1,'frame_sha256':f.sha(m.frame_of(docs.plan,docs.pins().request)),
        'snippet_sha256':m.VERIFY_SNIPPET_SHA256,'status':'UNAVAILABLE','code':'COMMAND_TIMEOUT','container_may_still_exist':True,'elapsed_ms':0}
    unavailable(receipt,'verify','COMMAND_TIMEOUT');assert receipt['items']['containers']['verify_container_present'] is False and receipt['containers_run']==1
    # the CLI was killed and the engine still has the container: the listing says so by its name
    def left(host):
        host.hang.add(('run','--rm'));host.docker.before=lambda docker,args:(docker.containers.append(hostemu.container('hostops02-k11-'+holder[0].go16(),hostemu.BACKEND,'x',[]))
                                                                             if args[:1]==['ps'] and not docker.container('hostops02-k11-'+holder[0].go16()) else None)
    holder=[];m,docs,host=fresh('PRE');holder.append(docs);left(host);receipt=docs.run(host)
    assert 'VERIFY_CONTAINER_LEFT_BEHIND' in receipt['findings'] and receipt['items']['containers']['verify_container_present'] is True and receipt['items']['containers']['listed']==9
    m,docs,host,receipt=ran('PRE',lambda host:host.absent.add(('run','--rm')))
    assert receipt['items']['verify']['started'] is False and receipt['items']['verify']['code']=='COMMAND_NOT_STARTED' and receipt['items']['verify']['container_may_still_exist'] is False
    assert receipt['containers_run']==0 and receipt['items']['image']['status']=='COMPLETE'
    m,docs,host,receipt=ran('PRE',lambda host:host.tree.remove('/usr/bin/docker'));unavailable(receipt,'verify','BINARY_UNAVAILABLE_OR_UNSAFE')
    assert all(receipt['items'][name]['code']=='BINARY_UNAVAILABLE_OR_UNSAFE' for name in ('containers','image','worker','render')) and host.commands==[]
    assert receipt['items']['worker_environment']['code']=='WORKER_NOT_OBSERVED' and receipt['items']['lock']['status']=='COMPLETE'
    m,docs,host,receipt=ran('PRE',lambda host:setattr(host.tree.get('/usr/bin/docker'),'mode',0o777));unavailable(receipt,'verify','BINARY_UNAVAILABLE_OR_UNSAFE')

def test_the_container_is_not_started_without_its_whole_class_time_and_the_run_goes_on():
    m,docs,host=fresh('PRE');now=docs.now
    docs.shift(now,now+__import__('datetime').timedelta(seconds=43));receipt=docs.run(host)
    assert receipt['items']['verify']['code']=='COMMAND_NOT_STARTED_BUDGET' and receipt['items']['verify']['started'] is False and host.docker.runs==[]
    assert receipt['items']['render']['status']=='COMPLETE' and receipt['items']['lock']['status']=='COMPLETE' and receipt['status']==PARTIAL
    m,docs,host=fresh('PRE');docs.shift(now,now+__import__('datetime').timedelta(seconds=44));receipt=docs.run(host);assert receipt['status']==COMPLETE

def test_expiry_stops_the_run_and_keeps_what_was_observed():
    m,docs,host=fresh('PRE');budget=f.Budget(docs.now).attach(host).cost(70,'ps','-a');receipt=docs.run(host,**budget.options())
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(PARTIAL,'PARTIAL_OBSERVED','GO_EXPIRED') and host.fds=={}
    assert receipt['items']['verify']['status']=='COMPLETE' and receipt['items']['containers']['status']=='COMPLETE' and receipt['items']['image']=={'status':'UNAVAILABLE','code':'GO_EXPIRED','elapsed_ms':0}
    assert 'worker' not in receipt['items'] and 'lock' not in receipt['items'] and 'directories_stable' not in receipt['items'],'nothing is observed after the expiry'
    m,docs,host=fresh('PRE',probe=None);budget=f.Budget(docs.now).attach(host).cost(61,'run','--rm');receipt=docs.run(host,**budget.options())
    assert receipt['code']=='GO_EXPIRED' and receipt['items']['containers']['code']=='GO_EXPIRED' and receipt['items']['containers']['elapsed_ms']==0
    assert sorted(receipt['items'])==['boot','containers','directory:DEPLOY_TREE','directory:LIVE_PARENT','directory:LOCK_DIRECTORY','directory:RELEASE_PARENT','live_target','release_target','verify']
    # with a bind, the expiry is met when the bind source is proved again after the run: the container item itself says so
    m,docs,host=fresh('PRE');budget=f.Budget(docs.now).attach(host).cost(61,'run','--rm');receipt=docs.run(host,**budget.options())
    assert receipt['code']=='GO_EXPIRED' and receipt['items']['verify']=={'status':'UNAVAILABLE','code':'GO_EXPIRED','elapsed_ms':61000} and 'containers' not in receipt['items']
    # elapsed time of every item and of the two renders is in the receipt (what the activation's budget is computed from)
    m,docs,host=fresh('PRE');budget=f.Budget(docs.now).attach(host).cost(7,'run','--rm').cost(2,'config');receipt=docs.run(host,**budget.options())
    assert receipt['status']==COMPLETE and receipt['items']['verify']['elapsed_ms']==7000 and receipt['items']['render']['elapsed_ms']==4000
    assert (receipt['items']['render']['base_ms'],receipt['items']['render']['override_ms'])==(2000,2000) and receipt['clock']['monotonic_elapsed_ms']==11000

def test_a_tool_that_timed_out_twice_is_not_started_again():
    m,docs,host,receipt=ran('PRE',lambda host:host.hang.update({('image','inspect'),('container','inspect')}),provisioned=True,units=k11.UNITS)
    assert receipt['items']['image']['code']=='COMMAND_TIMEOUT' and receipt['items']['worker']['code']=='COMMAND_TIMEOUT'
    assert receipt['items']['render']['code']=='COMMAND_SKIPPED_AFTER_TIMEOUT' and not host.docker.compose.calls
    assert receipt['items']['unit:docker.service']['status']=='COMPLETE','another tool is not affected'

def test_death_of_the_process_at_the_container_leaves_a_partial_of_unknown_state_and_nothing_open():
    m,docs,host=fresh('POST')
    def hook(host,name,detail,calls):
        if name=='run':raise hostemu.Death('dead')
    host.hook=hook;before=k11.state_of(host);receipt=docs.run(host)
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==(PARTIAL,'PARTIAL_OBSERVED','RUN_ESCAPED_STATE_UNKNOWN','ESCAPED')
    assert host.fds=={} and k11.state_of(host)==before and f.sealed(receipt)


# ---------------------------------------------------------------- image, worker, containers
def test_image_and_worker_metadata():
    def moved(host):host.docker.images[0]['RepoTags']=[];host.docker.images[3]['RepoTags'].append('c3po/backend:production')
    m,docs,host,receipt=ran('PRE',moved);assert {'IMAGE_ID_MISMATCH','RENDER_IMAGE_NOT_THE_SIGNED_REFERENCE'}&set(receipt['findings'])=={'IMAGE_ID_MISMATCH'}
    assert receipt['items']['image']['id_equal_signed'] is False and 'VERIFY_ENGINE_FAILURE' not in receipt['findings'],'the run itself takes the image by its ID'
    m,docs,host,receipt=ran('PRE',lambda host:host.docker.images[0]['Config']['Labels'].__setitem__('org.opencontainers.image.revision','0'*40));finding(receipt,'IMAGE_REVISION_MISMATCH','image')
    m,docs,host,receipt=ran('PRE',lambda host:host.docker.images.__delitem__(0));unavailable(receipt,'image','COMMAND_FAILED');assert receipt['items']['image']['returncode']==1
    m,docs,host,receipt=ran('PRE',lambda host:host.docker.container(hostemu.WORKER).__setitem__('Image',hostemu.OTHER));finding(receipt,'WORKER_IMAGE_MISMATCH','worker')
    m,docs,host,receipt=ran('PRE',lambda host:host.docker.container(hostemu.WORKER)['State'].update(Status='restarting',Running=False));finding(receipt,'WORKER_NOT_RUNNING','worker')
    m,docs,host,receipt=ran('PRE',lambda host:host.docker.container(hostemu.WORKER)['State'].update(Status='paused'));finding(receipt,'WORKER_NOT_RUNNING','worker')
    m,docs,host,receipt=ran('PRE',lambda host:host.docker.container(hostemu.WORKER).__setitem__('RestartCount',5))
    assert receipt['status']==COMPLETE and receipt['items']['worker']['restarts']==5,'the restart count is reported, not gated'
    m,docs,host,receipt=ran('PRE',lambda host:host.docker.containers.remove(host.docker.container(hostemu.WORKER)));unavailable(receipt,'worker','COMMAND_FAILED')
    assert receipt['items']['worker_environment']['code']=='WORKER_NOT_OBSERVED' and receipt['items']['containers']['worker_listed'] is False
    m,docs,host,receipt=ran('PRE',lambda host:setattr(host.docker,'ps_returncode',1));unavailable(receipt,'containers','COMMAND_FAILED')
    m,docs,host,receipt=ran('PRE',lambda host:host.docker.containers.append(hostemu.container('stray',hostemu.BACKEND,'x',[],running=False)))
    assert receipt['status']==COMPLETE and receipt['items']['containers']['by_state']=={'exited':1,'running':8} and receipt['items']['containers']['listed']==9

def test_environment_of_the_worker_is_booleans_and_only_its_revision_is_gated():
    def revision(host):
        env=host.docker.container(hostemu.WORKER)['Config']['Env'];env[env.index('C3PO_BUILD_SHA='+k11.REVISION)]='C3PO_BUILD_SHA='+'0'*40
    m,docs,host,receipt=ran('PRE',revision);finding(receipt,'WORKER_BUILD_REVISION_MISMATCH','worker_environment')
    assert receipt['items']['worker_environment']['names']['C3PO_BUILD_SHA']=={'present':True,'equal':False}
    m,docs,host,receipt=ran('PRE',lambda host:host.docker.container(hostemu.WORKER)['Config']['Env'].remove('C3PO_BUILD_SHA='+k11.REVISION));finding(receipt,'WORKER_BUILD_REVISION_MISMATCH','worker_environment')
    intended=json.loads(k11.override_bytes())['services']['r2d2-worker']['environment']
    def activated(host):host.docker.container(hostemu.WORKER)['Config']['Env']+=['%s=%s'%item for item in sorted(intended.items())][:3]+[k11.KEYS[3]+'='+'9'*64]
    m,docs,host,receipt=ran('PRE',activated);item=receipt['items']['worker_environment']
    finding(receipt,'WORKER_ALREADY_CARRIES_A_LIVE_NAME','worker_environment');assert (item['live_names_present'],item['live_names_equal_to_the_intended_values'])==(4,3)
    assert hostemu.SECRET not in json.dumps(receipt) and '9'*64 not in json.dumps(receipt['items'])
    m,docs,host,receipt=ran('PRE',lambda host:setattr(host.docker,'inspect_returncode',1));unavailable(receipt,'worker','COMMAND_FAILED')


# ---------------------------------------------------------------- the render
def test_render_with_the_override_is_compared_with_the_render_without_it_and_nothing_of_it_leaves():
    m,docs,host,receipt=ran('PRE');item=receipt['items']['render']
    assert item=={'services':8,'environment_equal':{key:True for key in k11.KEYS},'build_revision_equal':True,'image_reference_equal_signed':True,'other_services_unchanged':True,
                  'worker_changes_only_the_live_names':True,'live_names_already_in_the_base_render':0,
                  'data_volume_bind':{'volumes_listed':1,'policy_and_release_reached_through_the_one_signed_bind':True},'rendered_canonical_bytes':item['rendered_canonical_bytes'],
                  'base_ms':0,'override_ms':0,'status':'COMPLETE','findings':[],'matches':True,'elapsed_ms':0}
    assert hostemu.SECRET not in json.dumps(receipt) and 'postgresql' not in json.dumps(receipt) and item['rendered_canonical_bytes']>2000
    base=lambda host:host.docker.compose.base['services']
    m,docs,host,receipt=ran('PRE',lambda host:base(host)['r2d2-worker'].__setitem__('image','c3po/backend:rollback'));finding(receipt,'RENDER_IMAGE_NOT_THE_SIGNED_REFERENCE','render')
    m,docs,host,receipt=ran('PRE',lambda host:base(host)['r2d2-worker']['environment'].pop('C3PO_BUILD_SHA'));finding(receipt,'RENDER_BUILD_REVISION_MISMATCH','render')
    m,docs,host,receipt=ran('PRE',lambda host:base(host)['r2d2-worker']['environment'].update({k11.KEYS[0]:'/old',k11.KEYS[1]:'e'*64}))
    assert receipt['status']==COMPLETE and receipt['items']['render']['live_names_already_in_the_base_render']==2,'names already in the base are replaced by the override: a fact'

BIND={'type':'bind','source':hostemu.DATA,'target':k11.DATA_TARGET}
VOLUMES=[(lambda worker:worker.pop('volumes'),'RENDER_VOLUMES_INVALID',None),(lambda worker:worker.__setitem__('volumes',['/mnt/day-d-data:/app/day-d-data']),'RENDER_VOLUMES_INVALID',None),
         (lambda worker:worker.__setitem__('volumes',{'data':BIND}),'RENDER_VOLUMES_INVALID',None),(lambda worker:worker['volumes'].append({'type':'bind','source':'/srv'}),'RENDER_VOLUMES_INVALID',None),
         (lambda worker:worker['volumes'].append({'type':'bind','source':'/srv','target':''}),'RENDER_VOLUMES_INVALID',None),
         (lambda worker:worker['volumes'].append({'type':'bind','source':'/srv','target':7}),'RENDER_VOLUMES_INVALID',None),
         (lambda worker:worker['volumes'].extend({'type':'bind','source':'/srv','target':'/srv/%d'%index} for index in range(64)),'RENDER_VOLUMES_INVALID',None),
         (lambda worker:worker['volumes'][0].update(read_only=True),'WORKER_MOUNT_NOT_AS_SIGNED',False),(lambda worker:worker['volumes'][0].update(source='/srv/other'),'WORKER_MOUNT_NOT_AS_SIGNED',False),
         (lambda worker:worker['volumes'][0].update(type='volume',source='c3po_day_d_data'),'WORKER_MOUNT_NOT_AS_SIGNED',False),(lambda worker:worker['volumes'][0].pop('type'),'WORKER_MOUNT_NOT_AS_SIGNED',False),
         (lambda worker:worker.__setitem__('volumes',[]),'WORKER_MOUNT_NOT_AS_SIGNED',False),(lambda worker:worker['volumes'][0].update(target='/app/day-d'),'WORKER_MOUNT_NOT_AS_SIGNED',False),
         (lambda worker:worker['volumes'][0].update(target='/app'),'WORKER_MOUNT_NOT_AS_SIGNED',False),
         # another mount that also covers the policy or the release file: the worker would read it through that one
         (lambda worker:worker['volumes'].append({'type':'volume','source':'live','target':k11.DATA_TARGET+'/r2d2-v2-live'}),'WORKER_MOUNT_NOT_AS_SIGNED',False),
         (lambda worker:worker['volumes'].append({'type':'bind','source':'/srv/releases','target':k11.DATA_TARGET+'/'+k11.RELEASE_DIRECTORY}),'WORKER_MOUNT_NOT_AS_SIGNED',False),
         (lambda worker:worker['volumes'].append({'type':'bind','source':'/srv/app','target':'/app'}),'WORKER_MOUNT_NOT_AS_SIGNED',False),
         (lambda worker:worker['volumes'].append(dict(BIND)),'WORKER_MOUNT_NOT_AS_SIGNED',False),
         # what activate accepts as well: another spelling of the same paths, an explicit read_only false, mounts that cover neither file
         (lambda worker:worker['volumes'][0].update(target=k11.DATA_TARGET+'/',source=hostemu.DATA+'/'),None,True),(lambda worker:worker['volumes'][0].update(target='/app//day-d-data/.'),None,True),
         (lambda worker:worker['volumes'][0].update(read_only=False),None,True),(lambda worker:worker['volumes'].append({'type':'volume','source':'cache','target':'/app/cache'}),None,True),
         (lambda worker:worker['volumes'].append({'type':'bind','source':'/srv','target':k11.DATA_TARGET+'-other','read_only':True}),None,True),
         (lambda worker:worker['volumes'].extend({'type':'bind','source':'/srv','target':'/srv/%d'%index} for index in range(63)),None,True)]
@pytest.mark.parametrize('index',range(len(VOLUMES)))
def test_render_must_reach_the_policy_and_the_release_through_the_one_signed_bind_by_the_rule_of_activate(index):
    """activate refuses, before any effect and with its GO spent, a render whose worker does not have the data volume as
    exactly one read-write bind of the signed source at the signed target (WORKER_MOUNT_NOT_AS_SIGNED,
    RENDER_VOLUMES_INVALID). The dry run applies the same rule to the same render and makes it a finding."""
    change,code,bound=VOLUMES[index]
    m,docs,host,receipt=ran('PRE',lambda host:change(host.docker.compose.base['services']['r2d2-worker']));item=receipt['items']['render']
    assert item['data_volume_bind']['policy_and_release_reached_through_the_one_signed_bind'] is bound
    if code is None:assert receipt['status']==COMPLETE and item['findings']==[]
    else:
        finding(receipt,code,'render');assert receipt['findings']==[code] and receipt['outcome']==MISMATCH
    m,docs,host,receipt=ran('POST',lambda host:change(host.docker.compose.base['services']['r2d2-worker']),render=True)
    assert (receipt['status']==COMPLETE) is (code is None),'the readback applies the rule whenever it signs a render: activate is still to come'

def test_a_render_that_does_not_do_what_the_signed_override_says_is_found():
    """The override is exactly four names by its bytes; what compose makes of it is compared all the same."""
    def second(change):
        def prepare(host):
            def before(docker,args):
                if args[:1]==['compose'] and '-' in args:change(docker.compose.base)
            host.docker.before=before
        return prepare
    for change,code in ((lambda base:base['services']['api']['environment'].update(X='1'),'OVERRIDE_CHANGES_MORE_THAN_THE_WORKER'),
                        (lambda base:base['services'].pop('web'),'OVERRIDE_CHANGES_MORE_THAN_THE_WORKER'),(lambda base:base.update(name='other'),'OVERRIDE_CHANGES_MORE_THAN_THE_WORKER'),
                        (lambda base:base['services']['r2d2-worker']['environment'].update(C3PO_R2D2_V2_SHADOW_ENABLED='true'),'OVERRIDE_CHANGES_MORE_THAN_THE_LIVE_NAMES'),
                        (lambda base:base['services']['r2d2-worker'].update(command=['sh']),'OVERRIDE_CHANGES_MORE_THAN_THE_LIVE_NAMES')):
        m,docs,host=fresh('PRE');second(change)(host);receipt=docs.run(host);finding(receipt,code,'render')
    # a compose that ignores the override: the four names are not what was signed
    m,docs,host=fresh('PRE');plain=json.dumps(host.docker.compose.base).encode()
    m,docs,host,receipt=ran('PRE',lambda host:setattr(host.docker.compose,'config_output',plain));finding(receipt,'RENDER_ENVIRONMENT_NOT_AS_SIGNED','render')
    assert receipt['items']['render']['environment_equal']=={key:False for key in k11.KEYS} and receipt['items']['render']['worker_changes_only_the_live_names'] is True

def test_render_that_cannot_be_made_is_unavailable_with_a_constant_code():
    for prepare,code in ((lambda host:setattr(host.docker.compose,'config_output',b'not json'),'COMPOSE_RENDER_INVALID'),(lambda host:setattr(host.docker.compose,'config_output',b'[]'),'COMPOSE_RENDER_INVALID'),
                         (lambda host:setattr(host.docker.compose,'config_returncode',15),'COMMAND_FAILED'),(lambda host:host.docker.compose.base['services'].pop('r2d2-worker'),'COMPOSE_SERVICE_INVALID'),
                         (lambda host:setattr(host.docker.compose,'config_output',b'{"services":{},"pad":"'+b'x'*1048576+b'"}'),'COMMAND_OUTPUT_LIMIT'),
                         (lambda host:host.hang.add(('compose','config')),'COMMAND_TIMEOUT'),(lambda host:host.absent.add(('compose','config')),'COMMAND_NOT_STARTED'),
                         (lambda host:host.tree.remove(hostemu.ENV_FILE),'COMMAND_FAILED')):
        m,docs,host,receipt=ran('PRE',prepare);assert receipt['items']['render']['status']=='UNAVAILABLE' and receipt['items']['render']['code']==code,code
        assert receipt['status']==PARTIAL and receipt['items']['verify']['status']=='COMPLETE' and hostemu.SECRET not in json.dumps(receipt)


# ---------------------------------------------------------------- deploy tree, pin, markers, lock
def test_deployed_revision_compose_inputs_and_the_maintenance_pin():
    version=hostemu.DEPLOY+'/.deploy-version'
    m,docs,host,receipt=ran('PRE',lambda host:setattr(host.tree.get(version),'content',bytearray(b'0'*40+b'\n')));finding(receipt,'DEPLOYED_REVISION_MISMATCH','deploy_files')
    # activate compares the revision with surrounding white space aside (its deploy_version); the readback must not be stricter than the write it precedes
    for content in (k11.REVISION.encode(),k11.REVISION.encode()+b'\r\n',b' '+k11.REVISION.encode()+b'\n\n'):
        m,docs,host,receipt=ran('POST',lambda host:setattr(host.tree.get(version),'content',bytearray(content)));assert receipt['status']==COMPLETE
    for content in (k11.REVISION[:39].encode()+b'\n',k11.REVISION.encode()+b'0\n',k11.REVISION.upper().encode()+b'\n',b'\n'):
        m,docs,host,receipt=ran('PRE',lambda host:setattr(host.tree.get(version),'content',bytearray(content)));finding(receipt,'DEPLOYED_REVISION_MISMATCH','deploy_files')
    m,docs,host,receipt=ran('PRE',lambda host:remove(host,version));finding(receipt,'DEPLOYED_REVISION_FILE_ABSENT','deploy_files')
    m,docs,host,receipt=ran('PRE',lambda host:replace(host,version,kind='symlink'));unavailable(receipt,'deploy_files','OS_ERROR');assert receipt['items']['deploy_files']['errno']==errno.ELOOP
    m,docs,host,receipt=ran('PRE',lambda host:replace(host,version,kind='dir'));unavailable(receipt,'deploy_files','FILE_NOT_REGULAR')
    m,docs,host,receipt=ran('PRE',lambda host:setattr(host.tree.get(version),'content',bytearray(b'x'*129)));unavailable(receipt,'deploy_files','FILE_TOO_LARGE')
    m,docs,host,receipt=ran('PRE',lambda host:setattr(host.tree.get(version),'content',bytearray(k11.REVISION.encode()+b'\n'*88)));assert receipt['status']==COMPLETE,'128 bytes: what activate still reads'
    m,docs,host,receipt=ran('PRE');inputs=receipt['items']['deploy_files']['compose_inputs']
    assert inputs==[{'exists':True,'regular':True,'uid':1000,'gid':1000,'mode_octal':'0600','links':1},{'exists':True,'regular':True,'uid':1000,'gid':1000,'mode_octal':'0644','links':1}]
    assert 'size' not in json.dumps(receipt['items']['deploy_files']) and 'sha256' not in json.dumps(receipt['items']['deploy_files']),'of the environment file nothing but its metadata'
    for prepare in (lambda host:replace(host,hostemu.ENV_FILE,kind='symlink',uid=1000),lambda host:replace(host,hostemu.COMPOSE_FILE,kind='dir',uid=1000)):
        m,docs,host,receipt=ran('PRE',prepare);assert 'COMPOSE_INPUT_ABSENT_OR_NOT_REGULAR' in receipt['items']['deploy_files']['findings']
    m,docs,host,receipt=ran('POST',render=False);assert receipt['items']['deploy_files']['compose_inputs']==[],'without a render the inputs of compose are not looked at'
    m,docs,host,receipt=ran('PRE',lambda host:remove(host,hostemu.PIN));finding(receipt,'MAINTENANCE_PIN_ABSENT','maintenance_pin')
    for kind in ('symlink','dir'):
        m,docs,host,receipt=ran('PRE',lambda host:replace(host,hostemu.PIN,kind=kind,dev=D));finding(receipt,'MAINTENANCE_PIN_NOT_REGULAR','maintenance_pin')
    m,docs,host,receipt=ran('PRE',lambda host:replace(host,hostemu.DATA,kind='symlink'));assert receipt['items']['maintenance_pin']=={'status':'UNAVAILABLE','code':'SYMLINK_COMPONENT','elapsed_ms':0}

def test_reboot_markers_and_the_deployment_lock():
    m,docs,host,receipt=ran('POST',lambda host:host.tree.add('/run/c3po-security/reboot.pending',kind='file'));finding(receipt,'REBOOT_PENDING_MARKER_PRESENT','reboot_pending')
    m,docs,host,receipt=ran('POST',lambda host:host.tree.add('/run/reboot-required',kind='file'))
    assert receipt['status']==COMPLETE and receipt['items']['reboot_required']['exists'] is True,'a kernel waiting for a reboot is reported, not gated'
    for holder,state in (('EX','BUSY'),('SH','FREE')):
        m,docs,host,receipt=ran('POST',lambda host:host.lock_holder.__setitem__(k11.LOCK,holder))
        assert receipt['status']==COMPLETE and receipt['items']['lock']=={'exists':True,'state':state,'still_named':True,'status':'COMPLETE','findings':[],'matches':True,'elapsed_ms':0}
    m,docs,host,receipt=ran('POST',lambda host:remove(host,k11.LOCK));finding(receipt,'LOCK_FILE_ABSENT','lock');assert not [entry for entry in host.log if entry[0]=='flock']
    m,docs,host,receipt=ran('POST',lambda host:replace(host,k11.LOCK,kind='symlink',uid=1000));unavailable(receipt,'lock','LOCK_FILE_NOT_REGULAR')
    m,docs,host,receipt=ran('POST',lambda host:setattr(host.tree.get(k11.LOCK),'nlink',2));unavailable(receipt,'lock','LOCK_FILE_NOT_REGULAR')
    m,docs,host=fresh('POST')
    def hook(host,name,detail,calls):
        if name=='flock':raise OSError(errno.EIO,'injected')
    host.hook=hook;receipt=docs.run(host);unavailable(receipt,'lock','LOCK_UNAVAILABLE');assert host.fds=={} and host.lock_held(k11.LOCK) is None


# ---------------------------------------------------------------- units and the journal filesystem
def test_unit_states_are_facts_unless_the_request_signs_an_expectation():
    m,docs,host,receipt=ran('POST',units=('c3po-massive.timer','c3po-reader.service'))
    assert receipt['status']==COMPLETE and receipt['items']['unit:c3po-reader.service']['properties']['LoadState']=='not-found','a unit that is not installed is a fact'
    assert receipt['items']['unit:c3po-massive.timer']['gated'] is False and receipt['items']['unit:c3po-massive.timer']['expected'] is None
    def expecting(expected):
        def run(prepare=None):
            m,docs,host=fresh('POST',provisioned=True,units=('c3po-massive.timer',));docs.plan['units'][0]['expected']=expected;docs.chain()
            if prepare:prepare(host)
            return docs.run(host)
        return run
    run=expecting({'LoadState':'loaded','ActiveState':'inactive','UnitFileState':'disabled'});assert run()['status']==COMPLETE
    for key,value in (('ActiveState','active'),('UnitFileState','enabled'),('LoadState','masked')):
        receipt=run(lambda host:host.units['c3po-massive.timer'].__setitem__(key,value));finding(receipt,'UNIT_STATE_NOT_AS_SIGNED','unit:c3po-massive.timer')
        assert receipt['items']['unit:c3po-massive.timer']['properties'][key]==value and receipt['items']['unit:c3po-massive.timer']['gated'] is True
    assert expecting({'SubState':'dead'})(lambda host:host.units['c3po-massive.timer'].__setitem__('ActiveState','active'))['status']==COMPLETE,'only the signed properties are compared'

def test_hostile_answers_of_systemctl_are_observations_that_failed():
    def answers(raw,code=0):
        def prepare(host):host.systemctl=lambda args:(code,raw)
        return prepare
    good=b'Id=docker.service\nLoadState=loaded\nActiveState=active\nSubState=running\nUnitFileState=enabled\nFragmentPath=/usr/lib/systemd/system/docker.service\nDropInPaths=\nWantedBy=multi-user.target\nRequiredBy=\nTriggeredBy=docker.socket\n'
    m,docs,host,receipt=ran('POST',answers(good),units=('docker.service',));assert receipt['status']==COMPLETE and receipt['items']['unit:docker.service']['properties']['TriggeredBy']=='docker.socket'
    m,docs,host,receipt=ran('POST',answers(good+b'Extra=ignored\n\n'),units=('docker.service',));assert receipt['status']==COMPLETE
    for raw,code,expected in ((good.replace(b'SubState=running\n',b''),0,'PROPERTY_MISSING'),(good+b'no separator\n',0,'PROPERTY_LINE_INVALID'),(good+b'Id=docker.service\n',0,'PROPERTY_VALUE_INVALID'),
                              (good.replace(b'running',b'run;ning'),0,'PROPERTY_VALUE_INVALID'),(good.replace(b'running',b'run\xc3\xa9'),0,'PROPERTY_OUTPUT_INVALID'),
                              (good.replace(b'running',b'run\tning'),0,'PROPERTY_OUTPUT_INVALID'),(good.replace(b'Id=docker.service',b'Id=other.service'),0,'UNIT_ID_MISMATCH'),
                              (b'',0,'PROPERTY_MISSING'),(good,1,'COMMAND_FAILED'),(b'x'*65537,0,'COMMAND_OUTPUT_LIMIT')):
        # with a signed expectation the unit gates, and an answer that cannot be read is an observation that failed
        m,docs,host=fresh('POST',units=('docker.service',));docs.plan['units'][0]['expected']={'ActiveState':'active'};docs.chain();answers(raw,code)(host);receipt=docs.run(host)
        unavailable(receipt,'unit:docker.service',expected);assert receipt['fact_items_not_observed']==[] and receipt['gates_first_session_readback'] is False
        # without one the unit is a fact: the receipt says that it was not observed, and the other items decide
        m,docs,host,receipt=ran('POST',answers(raw,code),units=('docker.service',));fact_not_observed(receipt,'unit:docker.service',expected)
    m,docs,host,receipt=ran('POST',lambda host:host.tree.remove('/usr/bin/systemctl'),units=('docker.service',));fact_not_observed(receipt,'unit:docker.service','BINARY_UNAVAILABLE_OR_UNSAFE')
    assert receipt['items']['verify']['status']=='COMPLETE'

def test_free_space_of_the_journal_filesystem_and_a_root_that_does_not_exist_yet():
    m,docs,host,receipt=ran('POST',journal=k11.JOURNAL)
    assert receipt['status']==COMPLETE and receipt['items']['journal']=={'path':k11.JOURNAL,'exists':False,'floor_bytes':None,'status':'COMPLETE','findings':[],'matches':True,'elapsed_ms':0}
    m,docs,host,receipt=ran('POST',journal=k11.JOURNAL,floor=1);finding(receipt,'JOURNAL_ROOT_ABSENT','journal')
    available=145315507*4096
    m,docs,host,receipt=ran('POST',provisioned=True,journal=k11.JOURNAL,floor=available);assert receipt['status']==COMPLETE and receipt['items']['journal']['at_or_above_the_floor'] is True
    m,docs,host,receipt=ran('POST',provisioned=True,journal=k11.JOURNAL,floor=available+1);finding(receipt,'FREE_SPACE_BELOW_FLOOR','journal')
    def catalog(host):
        for name in ('epoch.json','maintenance.lock','session_date=2026-10-05'):host.tree.add(k11.JOURNAL+'/'+name,kind='file',mode=0o600)
    m,docs,host,receipt=ran('POST',catalog,provisioned=True,journal=k11.JOURNAL);item=receipt['items']['journal']
    assert (item['entries'],item['catalog_names_present'],item['owner_uid'],item['mode_octal'],item['bytes_available'])==(3,{'epoch.json':True,'maintenance.lock':True},0,'0700',available)
    assert 'session_date' not in json.dumps(receipt),'no name of the journal root leaves but the two catalog names'
    m,docs,host,receipt=ran('POST',lambda host:replace(host,'/var/lib/c3po-bar',kind='symlink'),provisioned=True,journal=k11.JOURNAL);fact_not_observed(receipt,'journal','SYMLINK_COMPONENT')
    m,docs,host,receipt=ran('POST',lambda host:replace(host,k11.JOURNAL,kind='file'),provisioned=True,journal=k11.JOURNAL);fact_not_observed(receipt,'journal','COMPONENT_NOT_DIRECTORY')
    m,docs,host,receipt=ran('POST',lambda host:replace(host,'/var/lib/c3po-bar',kind='symlink'),provisioned=True,journal=k11.JOURNAL,floor=1);unavailable(receipt,'journal','SYMLINK_COMPONENT')
    assert receipt['fact_items_not_observed']==[],'with a signed floor the journal gates'
    m,docs,host=fresh('POST',provisioned=True,journal=k11.JOURNAL);host.vfs[hostemu.ROOT_DEVICE]=types.SimpleNamespace(f_frsize=0,f_blocks=1,f_bfree=1,f_bavail=1)
    receipt=docs.run(host);assert receipt['items']['journal']['code']=='STATVFS_INVALID' and host.fds=={}


# ---------------------------------------------------------------- the docker configuration directory
def test_signed_docker_configuration_directory_is_used_only_when_private_and_empty_and_counted_twice():
    m,docs,host,receipt=ran('PRE',provisioned=True,docker_config=k11.DOCKER_CONFIG)
    assert receipt['status']==COMPLETE and receipt['items_omitted_by_the_plan']==['journal'] and all(entry['docker_config']==k11.DOCKER_CONFIG for entry in host.commands)
    assert (receipt['outcome'],receipt['dry_run'])==(m.PRE_REDUCED_OUTCOME,'REDUCED'),'activate never sets DOCKER_CONFIG: a run that does is not its rehearsal'
    assert receipt['items']['docker_config']=={'path':k11.DOCKER_CONFIG,'private':True,'entries_before':0,'passed_to_the_docker_commands':True,'status':'COMPLETE','findings':[],'matches':True,'elapsed_ms':0}
    assert receipt['items']['docker_config_after']=={'entries_before':0,'entries_after':0,'status':'COMPLETE','findings':[],'matches':True,'elapsed_ms':0}
    for prepare in (lambda host:host.tree.add(k11.DOCKER_CONFIG+'/config.json',kind='file'),lambda host:setattr(host.tree.get(k11.DOCKER_CONFIG),'mode',0o755),
                    lambda host:setattr(host.tree.get(k11.DOCKER_CONFIG),'uid',1000),lambda host:setattr(host.tree.get(k11.DOCKER_CONFIG),'gid',1000)):
        m,docs,host,receipt=ran('PRE',prepare,provisioned=True,docker_config=k11.DOCKER_CONFIG)
        assert receipt['items']['docker_config']['findings']==['DOCKER_CONFIG_NOT_PRIVATE_AND_EMPTY'] and host.commands==[],'no docker command runs with a directory that is not the signed kind'
        assert all(receipt['items'][name]['code']=='DOCKER_CONFIG_DIRECTORY_UNAVAILABLE' for name in ('verify','containers','image','worker','render'))
    m,docs,host,receipt=ran('PRE',docker_config=k11.DOCKER_CONFIG);unavailable(receipt,'docker_config','OS_ERROR')
    assert receipt['items']['verify']['code']=='DOCKER_CONFIG_DIRECTORY_UNAVAILABLE' and receipt['items']['docker_config_after']['code']=='DOCKER_CONFIG_DIRECTORY_UNAVAILABLE'
    # the CLI wrote into the directory during the run: a finding of its own
    def writes(host):
        real=host.docker.on_run
        def during(call):
            host.tree.add(k11.DOCKER_CONFIG+'/config.json',kind='file');return real(call)
        host.docker.on_run=during
    m,docs,host=fresh('PRE',provisioned=True,docker_config=k11.DOCKER_CONFIG);writes(host);receipt=docs.run(host)
    finding(receipt,'DOCKER_CONFIG_CHANGED_DURING_RUN','docker_config_after');assert receipt['items']['docker_config_after']['entries_after']==1


# ---------------------------------------------------------------- the receipt
def test_no_byte_of_the_release_of_the_policy_or_of_the_override_is_in_a_receipt():
    for mode in ('PRE','POST'):
        m,docs,host,receipt=ran(mode,render=True,provisioned=True,units=k11.UNITS,journal=k11.JOURNAL);text=json.dumps(receipt)
        for raw in (k11.RELEASE,k11.POLICY,k11.override_bytes()):
            assert k11.b64(raw) not in text and raw.decode() not in text and raw.decode().replace('"','\\"') not in text
        assert 'authorization_ref' not in text and 'c8_receipt_sha' not in text and 'SYNTHETIC' not in text and hostemu.SECRET not in text and 'never-emit' not in text
        assert len(f.line(receipt))<20000 and receipt['size_reductions']==[]

def test_receipt_is_reduced_by_flagged_steps_and_a_reduced_receipt_is_never_complete(monkeypatch):
    m,docs,host=fresh('PRE',rows_in_receipt=True);full=len(f.line(docs.run(host)))
    m,docs,host=fresh('PRE',rows_in_receipt=True);monkeypatch.setattr(m,'RECEIPT_LIMIT',full-200);receipt=docs.run(host)
    assert receipt['size_reductions']==['OBSERVED_ROWS_REDUCED_TO_COUNTS'] and (receipt['status'],receipt['outcome'])==(PARTIAL,'PARTIAL_OBSERVED')
    assert receipt['items']['directory:LOCK_DIRECTORY']['observed_rows']==5 and receipt['items']['verify']['release']['verified'] is True and f.sealed(receipt)
    assert (receipt['code'],receipt['expectations_met'],receipt['gates_first_session_readback'])==('RECEIPT_REDUCED_FOR_SIZE',False,False)
    second=len(f.line(receipt))-200
    m,docs,host=fresh('PRE',rows_in_receipt=True);monkeypatch.setattr(m,'RECEIPT_LIMIT',second);receipt=docs.run(host)
    assert receipt['size_reductions']==['OBSERVED_ROWS_REDUCED_TO_COUNTS','ITEMS_REDUCED_TO_STATUS'] and receipt['status']==PARTIAL
    assert receipt['items']['verify']=={'status':'COMPLETE','matches':True,'findings':[],'code':None} and len(f.line(receipt))<=second
    assert (receipt['code'],receipt['expectations_met'],receipt['gates_first_session_readback'])==('RECEIPT_REDUCED_FOR_SIZE',False,False)
    m,docs,host=fresh('PRE');monkeypatch.setattr(m,'RECEIPT_LIMIT',3000);receipt=docs.run(host)
    assert receipt['size_reductions']==['RECEIPT_REDUCED_TO_MINIMUM'] and receipt['status']==PARTIAL and receipt['code']=='RECEIPT_REDUCED_TO_MINIMUM' and f.sealed(receipt)

def test_only_a_complete_readback_gates_the_first_session_and_the_dispatcher_files_each_outcome(tmp_path):
    for index,(mode,prepare,status,verdict) in enumerate((('POST',None,COMPLETE,'KNOWN_COMPLETE'),('PRE',None,COMPLETE,'KNOWN_COMPLETE'),
                                                          ('POST',lambda host:remove(host,hostemu.PIN),PARTIAL,'KNOWN_PARTIAL'),('POST',lambda host:setattr(host,'actor',(1000,1000)),'REFUSED','KNOWN_REFUSAL'))):
        m,docs,host=fresh(mode);directory=tmp_path/str(index);directory.mkdir();dispatch=f.Dispatch(docs,directory)
        if prepare:prepare(host)
        receipt=docs.run(host);assert receipt['status']==status
        assert receipt.get('gates_first_session_readback',False) is (mode=='POST' and status==COMPLETE)
        result=dispatch.resume(dispatch.proof(dispatch.prepare()),dispatch.fake(out=f.line(receipt),status=verdict));assert result['status']==verdict


# ---------------------------------------------------------------- the probe of the read-only bind (PRE, the signers' choice)
def catalog(host):
    for name in ('epoch.json','maintenance.lock'):host.tree.add(k11.JOURNAL+'/'+name,kind='file',mode=0o600,content=b'{}')
def test_bind_probe_binds_one_existing_private_directory_read_only_and_reads_one_file_with_the_worker_s_reader():
    """What POST does with the installed release, exercised on Sunday on a directory that already exists: the same
    --mount words, the same reader, a boolean out. The directory is walked, held and proved again like every other."""
    m,docs,host,receipt=ran('PRE',catalog,provisioned=True,probe=k11.JOURNAL)
    assert receipt['status']==COMPLETE and receipt['items']['verify']['probe']=={'valid':True,'code':None} and receipt['items']['verify']['binds']==1
    assert host.docker.runs[0].mounts==[{'source':k11.JOURNAL,'target':'/c3po-bind-probe','read_only':True}] and receipt['items']['verify']['bind_source_stable'] is True
    argv=host.commands[0]['argv'];assert argv[argv.index('--mount')+1]=='type=bind,source=%s,target=/c3po-bind-probe,readonly'%k11.JOURNAL
    assert receipt['items']['directory:BIND_PROBE']['as_signed'] is True and receipt['items']['directories_stable']['directories']['BIND_PROBE'] is True
    assert docs.go['effects']['bind_probe']=={'directory':dict(m.chain_effects(hostemu.rows(host,k11.JOURNAL)),open_root=None,rows_signed=True),'file':k11.JOURNAL+'/epoch.json'}
    assert docs.go['effects']['verify']['binds']==[{'source':k11.JOURNAL,'target':'/c3po-bind-probe','read_only':True}]
    context=ast.literal_eval(host.commands[0]['stdin'].partition(b'\n')[0][len(b'SIGNED_CONTEXT='):].decode());assert context['probe_path']=='/c3po-bind-probe/epoch.json'
    # the file is not there, or is not what the worker's reader accepts: a finding with the reader's own code
    m,docs,host,receipt=ran('PRE',provisioned=True,probe=k11.JOURNAL);finding(receipt,'BIND_PROBE_NOT_READ','verify');assert receipt['items']['verify']['probe']=={'valid':False,'code':'FileNotFoundError'}
    def readable(host):catalog(host);host.tree.get(k11.JOURNAL+'/epoch.json').mode=0o644
    m,docs,host,receipt=ran('PRE',readable,provisioned=True,probe=k11.JOURNAL);finding(receipt,'BIND_PROBE_NOT_READ','verify')
    assert receipt['items']['verify']['probe']['code']=='RELEASE_FILE_NOT_PRIVATE_OR_INVALID' and receipt['items']['verify']['release']['verified'] is True
    # the directory is not the signed one, or is gone: nothing is bound that the run does not hold
    m,docs,host=fresh('PRE',provisioned=True,probe=k11.JOURNAL);host.tree.get(k11.JOURNAL).ino+=1;receipt=docs.run(host)
    assert receipt['items']['directory:BIND_PROBE']['findings']==['PARENT_IDENTITY_MISMATCH'] and receipt['items']['verify']=={'status':'UNAVAILABLE','code':'BIND_PROBE_NOT_HELD','elapsed_ms':0}
    assert host.docker.runs==[]
    # replaced while the container ran
    m,docs,host=fresh('PRE',provisioned=True,probe=k11.JOURNAL);catalog(host);real=host.docker.on_run
    def during(call):
        host.tree.get(k11.JOURNAL).ino+=1000;return real(call)
    host.docker.on_run=during;receipt=docs.run(host);assert {'BIND_SOURCE_REPLACED_DURING_RUN','DIRECTORY_REPLACED_DURING_RUN'}<=set(receipt['findings'])

def test_bind_probe_plan_and_the_line_of_a_container_that_answers_for_a_probe_nobody_signed():
    for change,code in ((dict(file_name='..'),'BIND_PROBE_INVALID'),(dict(file_name='a/b'),'BIND_PROBE_INVALID'),(dict(container_target='/app'),'BIND_PROBE_INVALID'),
                        (dict(container_target='/c3po-a/b'),'BIND_PROBE_INVALID'),(dict(extra=1),'BIND_PROBE_INVALID'),(dict(directory=None),'BIND_PROBE_INVALID'),
                        (dict(directory={'path':'/','rows':None,'open_root':None}),'BIND_PROBE_INVALID'),(dict(directory={'path':'/var/lib/x=y','rows':None,'open_root':None}),'MOUNT_INVALID')):
        m,docs,host=fresh('PRE',provisioned=True,probe=k11.JOURNAL);docs.plan['bind_probe'].update(change);docs.chain();assert f.refusal(docs.authenticate)==code,change
    m,docs,host=fresh('PRE',provisioned=True,probe=k11.JOURNAL);docs.plan['bind_probe']['directory']['rows'][-1]['uid']=1000;docs.chain();assert f.refusal(docs.authenticate)=='CHAIN_ROW_UNSAFE'
    m,docs,host=fresh('POST',provisioned=True);docs.plan['bind_probe']={'directory':k11.chain(host,k11.JOURNAL,None),'file_name':'epoch.json','container_target':'/c3po-bind-probe'}
    docs.chain();assert f.refusal(docs.authenticate)=='BIND_PROBE_INVALID','POST has the bind of the installed release: no probe'
    for value in ('x',[]):
        m,docs,host=fresh('PRE');docs.plan['bind_probe']=value;docs.chain();assert f.refusal(docs.authenticate)=='BIND_PROBE_INVALID'
    good=line_of('PRE',provisioned=True,probe=k11.JOURNAL,prepare=catalog)
    for value in (dict(good,probe=None),dict(good,probe={'valid':True}),dict(good,probe={'valid':1,'code':None}),dict(good,probe='yes')):
        m,docs,host,receipt=ran('PRE',lambda host:(catalog(host),setattr(host.docker,'on_run',answer(value))),provisioned=True,probe=k11.JOURNAL);unavailable(receipt,'verify','VERIFY_OUTPUT_INVALID')
    m,docs,host,receipt=ran('PRE',lambda host:(catalog(host),setattr(host.docker,'on_run',answer(dict(good,probe={'valid':False,'code':'OSError'})))),provisioned=True,probe=k11.JOURNAL)
    finding(receipt,'BIND_PROBE_NOT_READ','verify')


# ---------------------------------------------------------------- what the first mutation trial showed to be untested
def test_release_parent_and_bind_source_are_proved_again_before_they_are_used():
    m,docs,host=fresh('POST')
    def hook(host,name,detail,calls):
        if name=='fstatvfs' and detail[0]==hostemu.LOCK_DIRECTORY:host.tree.get(hostemu.DATA).ino+=1          # after its walk, before release_target
    host.hook=hook;receipt=docs.run(host)
    assert receipt['items']['release_target']=={'status':'UNAVAILABLE','code':'PARENT_REPLACED','elapsed_ms':0} and host.docker.runs==[] and host.fds=={}
    m,docs,host=fresh('POST');file=k11.RELEASE_HOST+'/'+k11.RELEASE_FILE;seen=[]
    def after_the_read(host,name,detail,calls):
        if name=='fstat' and detail[0]==file:
            seen.append(calls)
            if len(seen)==2:host.tree.get(k11.RELEASE_HOST).ino+=1          # after the read of release_target, before the container
    host.hook=after_the_read;receipt=docs.run(host)
    assert receipt['items']['release_target']['status']=='COMPLETE' and receipt['items']['verify']=={'status':'UNAVAILABLE','code':'PARENT_REPLACED','elapsed_ms':0}
    assert host.docker.runs==[],'a directory that is no longer the one the run opened is not bound'

def test_every_one_of_the_four_names_must_be_as_signed_and_in_the_render_with_the_override():
    intended=json.loads(k11.override_bytes())['services']['r2d2-worker']['environment']
    m,docs,host=fresh('PRE');wrong=json.loads(json.dumps(host.docker.compose.base));wrong['services']['r2d2-worker']['environment'].update(dict(intended,**{k11.KEYS[1]:'e'*64}))
    m,docs,host,receipt=ran('PRE',lambda host:setattr(host.docker.compose,'config_output',json.dumps(wrong).encode()));finding(receipt,'RENDER_ENVIRONMENT_NOT_AS_SIGNED','render')
    assert receipt['items']['render']['environment_equal']=={k11.KEYS[0]:True,k11.KEYS[1]:False,k11.KEYS[2]:True,k11.KEYS[3]:True}
    # the base already has the four values and the render with the override loses them: only the second render counts
    def prepare(host):
        host.docker.compose.base['services']['r2d2-worker']['environment'].update(intended);plain=json.loads(json.dumps(host.docker.compose.base))
        for key in k11.KEYS:plain['services']['r2d2-worker']['environment'].pop(key)
        def before(docker,args):
            if args[:1]==['compose'] and '-' in args:docker.compose.config_output=json.dumps(plain).encode()
        host.docker.before=before
    m,docs,host=fresh('PRE');prepare(host);receipt=docs.run(host)
    assert 'RENDER_ENVIRONMENT_NOT_AS_SIGNED' in receipt['findings'] and receipt['items']['render']['live_names_already_in_the_base_render']==4


# ---------------------------------------------------------------- the review of 02/10: what Monday's two single-shot writes refuse on is found here
def full_volume(blocks,**inodes):
    def prepare(host):
        old=host.vfs[D];host.vfs[D]=types.SimpleNamespace(f_frsize=old.f_frsize,f_blocks=old.f_blocks,f_bfree=blocks,f_bavail=blocks,**inodes)
    return prepare

def test_a_worker_that_already_carries_a_live_name_is_a_finding_even_when_the_value_is_empty():
    """activate refuses, before any effect and with its GO spent, a worker that has any of the four names
    (WORKER_ALREADY_CARRIES_THE_KEYS). The payload of 28/09 refused only non-empty values: an empty placeholder line
    in the environment file passed then and is refused now. The readback finds it too: activate is still to come."""
    for mode,options in (('PRE',{}),('POST',{}),('POST',{'render':True})):
        for names in ([k11.KEYS[0]+'='],[k11.KEYS[2]],[key+'=/old/value' for key in k11.KEYS]):
            m,docs,host,receipt=ran(mode,lambda host:host.docker.container(hostemu.WORKER)['Config']['Env'].extend(names),**options);item=receipt['items']['worker_environment']
            finding(receipt,'WORKER_ALREADY_CARRIES_A_LIVE_NAME','worker_environment');assert item['live_names_present']==len(names) and receipt['findings']==['WORKER_ALREADY_CARRIES_A_LIVE_NAME']
            assert item['names'][names[0].split('=')[0]]['present'] is True and item['build_revision_equal_signed'] is True
    m,docs,host,receipt=ran('PRE');item=receipt['items']['worker_environment']
    assert item=={'build_revision_equal_signed':True,'command_ms':0,'live_names_present':0,'live_names_equal_to_the_intended_values':0,
                  'names':dict({key:{'present':False,'equal':False} for key in k11.KEYS},C3PO_BUILD_SHA={'present':True,'equal':True}),
                  'status':'COMPLETE','findings':[],'matches':True,'elapsed_ms':0},'booleans and counts, and nothing else: no intended value, no observed value'

def test_a_pin_install_release_refuses_is_a_finding_of_the_dry_run_and_a_fact_of_the_readback():
    """install_release: MAINTENANCE_PIN_NOT_ROOT_OWNED, before any effect, GO spent."""
    m,docs,host,receipt=ran('PRE')
    assert receipt['items']['maintenance_pin']=={'exists':True,'type':'file','uid':0,'gid':0,'mode_octal':'0600','root_owned':True,'status':'COMPLETE','findings':[],'matches':True,'elapsed_ms':0}
    for owner in ((1000,1000),(1000,0),(0,1000)):
        def owned(host):host.tree.get(hostemu.PIN).uid,host.tree.get(hostemu.PIN).gid=owner
        m,docs,host,receipt=ran('PRE',owned);finding(receipt,'MAINTENANCE_PIN_NOT_ROOT_OWNED','maintenance_pin')
        assert (receipt['items']['maintenance_pin']['uid'],receipt['items']['maintenance_pin']['gid'],receipt['items']['maintenance_pin']['root_owned'])==owner+(False,)
        m,docs,host,receipt=ran('POST',owned);assert receipt['status']==COMPLETE and receipt['items']['maintenance_pin']['root_owned'] is False,'after install_release the owner of the pin is a fact'

def test_free_space_of_the_data_volume_below_the_signed_floor_of_install_release():
    """install_release: DATA_VOLUME_FREE_SPACE_BELOW_FLOOR (its constant is the floor the dry run signs)."""
    floor=k11.LIMITS['data_volume_free_bytes'];assert floor%4096==0
    for blocks,below in ((0,True),(floor//4096-1,True),(floor//4096,False)):
        m,docs,host,receipt=ran('PRE',full_volume(blocks));item=receipt['items']['directory:RELEASE_PARENT']
        assert (item['bytes_available'],item['free_bytes_floor'])==(blocks*4096,floor)
        if below:
            finding(receipt,'DATA_VOLUME_FREE_SPACE_BELOW_FLOOR','directory:RELEASE_PARENT');assert receipt['findings']==['DATA_VOLUME_FREE_SPACE_BELOW_FLOOR']
            # judged on the filesystem of each directory a write of Monday creates in (here the same volume), and on no other
            assert receipt['items']['directory:LIVE_PARENT']['findings']==['DATA_VOLUME_FREE_SPACE_BELOW_FLOOR'] and receipt['items']['directory:BIND_PROBE']['findings']==[]
            assert 'free_bytes_floor' not in receipt['items']['directory:DEPLOY_TREE'] and 'free_bytes_floor' not in receipt['items']['directory:BIND_PROBE']
        else:assert receipt['status']==COMPLETE
    # the live parent on a filesystem of its own that is full, the volume itself with room: activate's refusal, found on the live parent alone
    def nested(host):
        host.tree.get(k11.LIVE_PARENT).dev=977;host.vfs[977]=types.SimpleNamespace(f_frsize=4096,f_blocks=1000,f_bfree=3,f_bavail=3)
    m,docs,host=fresh('PRE');nested(host);docs.plan['live']['parent']=k11.chain(host,k11.LIVE_PARENT,hostemu.DATA);docs.chain();receipt=docs.run(host)
    finding(receipt,'DATA_VOLUME_FREE_SPACE_BELOW_FLOOR','directory:LIVE_PARENT');assert receipt['items']['directory:RELEASE_PARENT']['findings']==[] and receipt['items']['directory:LIVE_PARENT']['bytes_available']==3*4096
    # inodes, where the filesystem counts them (activate: DATA_VOLUME_FREE_INODES_BELOW_FLOOR): a filesystem that counts none is never short of them
    blocks=13200816
    for inodes,below in ((dict(f_files=1000,f_favail=7),True),(dict(f_files=1000,f_favail=0),True),(dict(f_files=1000,f_favail=8),False),(dict(f_files=0,f_favail=0),False),(dict(f_files=1000),False),({},False)):
        m,docs,host,receipt=ran('PRE',full_volume(blocks,**inodes));item=receipt['items']['directory:LIVE_PARENT']
        counted=inodes.get('f_favail') if inodes.get('f_files') and 'f_favail' in inodes else None
        assert (item['inodes_available'],item['free_inodes_floor'],receipt['items']['directory:DEPLOY_TREE']['inodes_available'])==(counted,8,None)
        if below:
            finding(receipt,'DATA_VOLUME_FREE_INODES_BELOW_FLOOR','directory:LIVE_PARENT');assert receipt['findings']==['DATA_VOLUME_FREE_INODES_BELOW_FLOOR']
            assert receipt['items']['directory:RELEASE_PARENT']['findings']==['DATA_VOLUME_FREE_INODES_BELOW_FLOOR']
        else:assert receipt['status']==COMPLETE
    m,docs,host,receipt=ran('PRE',full_volume(blocks,f_files=1000,f_favail=0),limits=None);assert receipt['status']==COMPLETE and receipt['items']['directory:LIVE_PARENT']['inodes_available']==0
    m,docs,host,receipt=ran('POST',full_volume(blocks,f_files=1000,f_favail=0),limits=dict(k11.LIMITS));finding(receipt,'DATA_VOLUME_FREE_INODES_BELOW_FLOOR','directory:LIVE_PARENT')
    m,docs,host,receipt=ran('PRE',full_volume(0),limits=None)
    assert receipt['status']==COMPLETE and receipt['outcome']==m.PRE_REDUCED_OUTCOME and 'free_bytes_floor' not in receipt['items']['directory:RELEASE_PARENT'],'without signed limits the space is a fact'
    m,docs,host,receipt=ran('POST',full_volume(0));assert receipt['status']==COMPLETE
    m,docs,host,receipt=ran('POST',full_volume(0),limits=dict(k11.LIMITS));finding(receipt,'DATA_VOLUME_FREE_SPACE_BELOW_FLOOR','directory:RELEASE_PARENT')

def test_docker_reads_and_renders_slower_than_the_signed_milliseconds_are_findings():
    """activate makes its quick docker reads and one render before its first effect and refuses when the time left no
    longer holds the recreate (LOCK_NOT_TAKEN_BUDGET, BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT). The dry run measures
    the same commands and judges each against the milliseconds the request signs."""
    def timed(mode,costs,**options):
        m,docs,host=fresh(mode,**options);budget=f.Budget(docs.now).attach(host)
        for seconds,words in costs(host):budget.cost(seconds,*words)
        return m,docs.run(host,**budget.options())
    worker_id=lambda host:host.docker.container(hostemu.WORKER)['Id']
    quick=[(lambda host:[(1.6,('ps','-a'))],'containers'),(lambda host:[(1.6,('image','inspect'))],'image'),(lambda host:[(1.6,('container','inspect',hostemu.WORKER))],'worker'),
           (lambda host:[(1.6,('container','inspect',worker_id(host)))],'worker_environment')]
    for costs,item in quick:
        m,receipt=timed('PRE',costs);finding(receipt,'DOCKER_CALL_SLOWER_THAN_THE_SIGNED_LIMIT',item)
        assert receipt['items'][item]['command_ms']==1600 and [name for name,found in receipt['items'].items() if found['findings']]==[item]
        m,receipt=timed('PRE',costs,limits=None);assert receipt['status']==COMPLETE and receipt['items'][item]['command_ms']==1600,'without signed limits the milliseconds are a fact'
        m,receipt=timed('POST',costs);assert receipt['status']==COMPLETE
        m,receipt=timed('POST',costs,limits=dict(k11.LIMITS));finding(receipt,'DOCKER_CALL_SLOWER_THAN_THE_SIGNED_LIMIT',item)
    m,receipt=timed('PRE',lambda host:[(1.5,('ps','-a')),(1.5,('image','inspect')),(1.5,('container','inspect')),(3,('config',))])
    assert receipt['status']==COMPLETE and receipt['items']['image']['command_ms']==1500 and receipt['items']['render']['base_ms']==3000,'at the limit is within the limit'
    for costs,base,override in ((lambda host:[(3.5,('config',))],3500,3500),(lambda host:[(1,('config',)),(3.5,('config','-'))],1000,3500),(lambda host:[(3.5,('config',)),(1,('config','-'))],3500,1000)):
        m,receipt=timed('PRE',costs);finding(receipt,'RENDER_SLOWER_THAN_THE_SIGNED_LIMIT','render')
        assert (receipt['items']['render']['base_ms'],receipt['items']['render']['override_ms'])==(base,override) and receipt['findings']==['RENDER_SLOWER_THAN_THE_SIGNED_LIMIT']
        m,receipt=timed('PRE',costs,limits=None);assert receipt['status']==COMPLETE
        m,receipt=timed('POST',costs,render=True,limits=dict(k11.LIMITS));finding(receipt,'RENDER_SLOWER_THAN_THE_SIGNED_LIMIT','render')
    # the two limits are judged apart: a slow render is not a slow read, a slow read is not a slow render
    m,receipt=timed('PRE',lambda host:[(2,('config',))],limits=dict(k11.LIMITS,quick_ms=1));assert receipt['items']['render']['findings']==[]
    assert 'DOCKER_CALL_SLOWER_THAN_THE_SIGNED_LIMIT' not in receipt['findings']
    m,receipt=timed('PRE',lambda host:[(2,('image','inspect'))],limits=dict(k11.LIMITS,render_ms=1,quick_ms=2500));assert receipt['status']==COMPLETE

@pytest.mark.parametrize('mode',['PRE','POST'])
def test_place_where_activate_will_create_its_directory_must_be_empty_in_its_signed_parent(mode):
    """activate walks its signed live parent and refuses DESTINATION_PRESENT or PARENT_* before any effect, GO spent."""
    for kind in ('dir','file','symlink','fifo'):
        m,docs,host,receipt=ran(mode,lambda host:host.tree.add(k11.LIVE_HOST,kind=kind,dev=D,mode=0o700))
        finding(receipt,'LIVE_DIRECTORY_ALREADY_EXISTS','live_target')
        assert receipt['items']['live_target']=={'expected':'DIRECTORY_ABSENT','exists':True,'type':{'fifo':'other'}.get(kind,kind),'status':'COMPLETE','findings':['LIVE_DIRECTORY_ALREADY_EXISTS'],'matches':False,'elapsed_ms':0}
        assert not [entry for entry in host.log if entry[0]=='open' and entry[1]==k11.LIVE_HOST],'what stands there is classified by lstat and never opened'
    m,docs,host,receipt=ran(mode,lambda host:remove(host,k11.LIVE_PARENT))
    assert receipt['items']['directory:LIVE_PARENT']['findings']==['PARENT_MISSING'] and receipt['items']['live_target']=={'status':'UNAVAILABLE','code':'DIRECTORY_NOT_HELD','elapsed_ms':0}
    assert receipt['status']==PARTIAL and receipt['code']=='PARENT_MISSING','a missing parent is told apart from a missing directory'
    for change,field in ((lambda node:setattr(node,'uid',1000),'uid'),(lambda node:setattr(node,'mode',0o755),'mode'),(lambda node:setattr(node,'ino',node.ino+1),'inode')):
        m,docs,host,receipt=ran(mode,lambda host:change(host.tree.get(k11.LIVE_PARENT)));item=receipt['items']['directory:LIVE_PARENT']
        assert item['findings']==['PARENT_IDENTITY_MISMATCH'] and item['fields_that_differ'][field] is True and receipt['items']['live_target']['code']=='DIRECTORY_NOT_HELD'
    m,docs,host,receipt=ran(mode,lambda host:replace(host,k11.LIVE_PARENT,kind='symlink',dev=D));assert receipt['items']['directory:LIVE_PARENT']['findings']==['PARENT_SYMLINK_COMPONENT']
    # the rows of the live parent for the request of activate, from this very boot, when the request signs rows_in_receipt
    m,docs,host,receipt=ran(mode,rows_in_receipt=True,signed_rows=False);item=receipt['items']['directory:LIVE_PARENT']
    assert item['observed_rows']==hostemu.rows(host,k11.LIVE_PARENT) and item['rows_acceptable_to_a_write'] is True and item['judged_as_receiving_an_entry'] is True and receipt['status']==COMPLETE
    # the parent is proved again before the name is looked at
    m,docs,host=fresh(mode)
    def hook(host,name,detail,calls):
        if name=='lstat' and detail[0]==k11.RELEASE_HOST:host.tree.get(k11.LIVE_PARENT).ino+=1          # after the walk of the live parent, before live_target
    host.hook=hook;receipt=docs.run(host)
    assert receipt['items']['live_target']=={'status':'UNAVAILABLE','code':'PARENT_REPLACED','elapsed_ms':0} and host.fds=={}
    # without the member nothing of it is looked at
    m,docs,host,receipt=ran(mode,lambda host:host.tree.add(k11.LIVE_HOST,dev=D),live=False)
    assert receipt['status']==COMPLETE and 'live_target' not in receipt['items'] and not [entry for entry in host.log if entry[0]=='lstat' and entry[1]==k11.LIVE_HOST]

def test_an_item_without_any_signed_expectation_that_cannot_be_observed_does_not_decide_the_readback():
    """The readback of Monday is single-shot: a reboot-required marker that cannot be read, a unit that is only
    reported, a journal without a floor are said in the receipt and leave the outcome to the items that gate."""
    def unreadable(host):
        def hook(host,name,detail,calls):
            if name=='lstat' and detail[0]=='/run/reboot-required':raise OSError(errno.EIO,'injected')
        host.hook=hook
    for mode in ('PRE','POST'):
        m,docs,host=fresh(mode);unreadable(host);receipt=docs.run(host);fact_not_observed(receipt,'reboot_required','OS_ERROR')
        assert receipt['outcome']==m.success_of(docs.plan) and receipt['gates_first_session_readback'] is (mode=='POST') and receipt['items']['reboot_required']['errno']==errno.EIO
    # the marker that gates, read through the same directory, still decides
    m,docs,host=fresh('POST')
    def pending(host,name,detail,calls):
        if name=='lstat' and detail[0]=='/run/c3po-security':raise OSError(errno.EIO,'injected')
    host.hook=pending;receipt=docs.run(host);unavailable(receipt,'reboot_pending','OS_ERROR');assert receipt['fact_items_not_observed']==[]
    # an expiry is never a fact: the run stops whatever the item
    m,docs,host=fresh('POST',units=('docker.service',));budget=f.Budget(docs.now).attach(host).cost(70,'show');receipt=docs.run(host,**budget.options())
    assert (receipt['status'],receipt['code'])==(PARTIAL,'GO_EXPIRED') and receipt['gates_first_session_readback'] is False

def test_installed_file_with_the_signed_hash_and_another_signed_size_and_a_file_swapped_while_it_is_read():
    m,docs,host=fresh('POST');docs.plan['release']['bytes']=len(k11.RELEASE)+1;docs.chain();receipt=docs.run(host)
    assert 'RELEASE_FILE_BYTES_MISMATCH' in receipt['items']['release_target']['findings'] and receipt['items']['release_target']['file']['bytes_equal_signed'] is False
    assert receipt['items']['verify']['release']['bytes_equal_signed'] is False and receipt['status']==PARTIAL,'the size is compared on the host and in the container'
    m,docs,host=fresh('POST');file=k11.RELEASE_HOST+'/'+k11.RELEASE_FILE
    def swap(host,name,detail,calls):
        if name=='open' and detail[0]==file:host.tree.get(file).ino+=1000          # after the lstat that classified it, before it is opened
    host.hook=swap;receipt=docs.run(host)
    assert receipt['items']['release_target']=={'status':'UNAVAILABLE','code':'RELEASE_FILE_CHANGED_DURING_READ','elapsed_ms':0} and host.fds=={}
    assert receipt['status']==PARTIAL and receipt['gates_first_session_readback'] is False

def test_items_that_could_carry_names_or_contents_have_exactly_these_members():
    """A later edit cannot add a nominal value unnoticed: container names, the content of the revision file, the
    intended values of the environment."""
    m,docs,host,receipt=ran('POST',render=True);items=receipt['items']
    assert items['containers']=={'command_ms':0,'listed':8,'by_state':{'running':8},'worker_service_leftovers':0,'worker_listed':True,'verify_container_present':False,
                                 'status':'COMPLETE','findings':[],'matches':True,'elapsed_ms':0}
    assert items['deploy_files']=={'deployed_revision':{'exists':True,'equal_to_the_signed_revision':True},
                                   'compose_inputs':[{'exists':True,'regular':True,'uid':1000,'gid':1000,'mode_octal':'0600','links':1},{'exists':True,'regular':True,'uid':1000,'gid':1000,'mode_octal':'0644','links':1}],
                                   'status':'COMPLETE','findings':[],'matches':True,'elapsed_ms':0}
    assert set(items['worker_environment'])=={'build_revision_equal_signed','command_ms','live_names_present','live_names_equal_to_the_intended_values','names','status','findings','matches','elapsed_ms'}
    assert set(items['worker'])=={'command_ms','container','image_id_equal_signed','running','state','restarts','health','started_at','image_reference_equal_signed','status','findings','matches','elapsed_ms'}
    assert set(items['image'])=={'command_ms','reference','id_equal_signed','revision_equal_signed','repo_tag_count','reference_among_repo_tags','status','findings','matches','elapsed_ms'}
    text=json.dumps(items);assert not [row['Name'] for row in host.docker.containers if row['Name'].strip('/') in text.replace(hostemu.WORKER,'')] and k11.POLICY_CONTAINER not in text

def test_a_reduced_readback_receipt_never_says_that_it_gates_the_first_session(monkeypatch):
    m,docs,host=fresh('POST',rows_in_receipt=True);full=docs.run(host);assert full['status']==COMPLETE and full['gates_first_session_readback'] is True
    for limit,steps in ((len(f.line(full))-200,['OBSERVED_ROWS_REDUCED_TO_COUNTS']),(None,['OBSERVED_ROWS_REDUCED_TO_COUNTS','ITEMS_REDUCED_TO_STATUS'])):
        if limit is None:limit=len(f.line(receipt))-200
        m,docs,host=fresh('POST',rows_in_receipt=True);monkeypatch.setattr(m,'RECEIPT_LIMIT',limit);receipt=docs.run(host)
        assert receipt['size_reductions']==steps and (receipt['status'],receipt['outcome'],receipt['code'])==(PARTIAL,'PARTIAL_OBSERVED','RECEIPT_REDUCED_FOR_SIZE')
        assert receipt['gates_first_session_readback'] is False and receipt['expectations_met'] is False and f.sealed(receipt)
    # a receipt that already carries a code keeps it
    m,docs,host=fresh('POST',rows_in_receipt=True);remove(host,hostemu.PIN);monkeypatch.setattr(m,'RECEIPT_LIMIT',len(f.line(full))-200);receipt=docs.run(host)
    assert receipt['code']=='MAINTENANCE_PIN_ABSENT' and receipt['gates_first_session_readback'] is False and receipt['size_reductions']==['OBSERVED_ROWS_REDUCED_TO_COUNTS']

def test_rule_of_the_bind_is_read_from_the_render_with_the_override_which_is_the_one_activate_recreates_from():
    def only_with_the_override(host):
        def before(docker,args):
            if args[:1]==['compose'] and '-' in args:docker.compose.base['services']['r2d2-worker']['volumes'][0]['read_only']=True
        host.docker.before=before
    m,docs,host=fresh('PRE');only_with_the_override(host);receipt=docs.run(host)
    assert receipt['findings']==['OVERRIDE_CHANGES_MORE_THAN_THE_LIVE_NAMES','WORKER_MOUNT_NOT_AS_SIGNED'] and receipt['items']['render']['data_volume_bind']['policy_and_release_reached_through_the_one_signed_bind'] is False

@pytest.mark.parametrize('mode',['PRE','POST'])
def test_container_an_interrupted_recreate_of_the_worker_left_behind_is_a_finding(mode):
    """activate: WORKER_SERVICE_LEFTOVER_CONTAINER, before any effect and with its GO spent. While compose replaces
    the container of a service one of the two carries the name <hex>_<container>; one that is still there tells of a
    recreate that was interrupted, and activate's recreate could not leave the listing as it found it."""
    for name,state in (('0123456789ab_'+hostemu.WORKER,False),('f00dfeedc0de_'+hostemu.WORKER,True)):
        m,docs,host,receipt=ran(mode,lambda host:host.docker.containers.append(hostemu.container(name,hostemu.BACKEND,'c3po/backend:production',[],running=state)))
        finding(receipt,'WORKER_SERVICE_LEFTOVER_CONTAINER','containers');assert receipt['items']['containers']['worker_service_leftovers']==1 and receipt['items']['containers']['listed']==9
        assert name not in json.dumps(receipt),'a count, never the name'
    # a container of another service whose name merely ends alike, or that carries the worker's name inside, is not one
    for name in ('other-'+hostemu.WORKER,hostemu.WORKER+'_old','c3po-r2d2-worker-10','x_c3po-r2d2-shadow-candidate-worker-1','0123456789ab_'+hostemu.WORKER+'0','ab_'+hostemu.WORKER+'-old'):
        m,docs,host,receipt=ran(mode,lambda host:host.docker.containers.append(hostemu.container(name,hostemu.BACKEND,'x',[],running=False)))
        assert receipt['status']==COMPLETE and receipt['items']['containers']['worker_service_leftovers']==0,name
