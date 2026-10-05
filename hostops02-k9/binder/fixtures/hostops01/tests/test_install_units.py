"""OP_INSTALL_UNITS on the emulated host: exclusive creation through a temporary and a link, no process, no
activation. Synthetic local tests only. No SSH, host, real credential, docker binary or operational GO."""
import errno
import json
import os
import re

import pytest

import family as f
import hostemu

k=f.load('install_units');m=k.m
UNITS='/etc/systemd/system'
SERVICE=UNITS+'/c3po-massive.service';TIMER=UNITS+'/c3po-massive.timer'
RENDERED=f.reference_render(f.VALUES)
BASE=set(hostemu.world().tree.paths())
CREATE=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC

def fresh(**options):
    host=f.world(k);return host,f.Docs(k,f.install_fields(k,host,**options))
def new(host):return sorted(path for path in host.tree.paths() if path not in BASE)
def temp(docs,index):return UNITS+'/.hostops-%s-%d.partial'%(docs.pins().go[:16],index)
def refusal(action):
    with pytest.raises(m.Refused) as caught:action()
    return str(caught.value)
def refused(host,docs,code):
    before=host.tree.snapshot();earlier=len(host.mutating());receipt=docs.run(host)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('REFUSED','REFUSED_NOTHING_CREATED',code),receipt['code']
    assert host.tree.snapshot()==before and len(host.mutating())==earlier and f.sealed(receipt)
    assert receipt['mutating_calls']['issued']==0 and receipt['ledger']==[] and receipt['objects_left_by_this_run']==0
    return receipt
def at_event(host,name,occurrence,action):
    seen=[0]
    def hook(host,event,detail,calls):
        if event==name:
            seen[0]+=1
            if seen[0]==occurrence:action(host,detail)
    host.hook=hook
def raising(kind,*arguments):
    def action(host,detail):raise kind(*arguments)
    return action
def unit_named(host,path):
    return re.fullmatch(r'.*\.(service|timer|socket|target|mount|path|slice|scope)',path) is not None and host.tree.get(path).kind=='file'

GENERIC=b'[Service]\nEnvironment=DOCKER_CONFIG=@CONFIG_DIR@/docker-cli\nExecStart=/usr/bin/docker run --network @NETWORK@ --mount source=@CONFIG_DIR@ @IMAGE_ID@\n'
def reader_units():
    holders={'CONFIG_DIR':{'kind':'ABSOLUTE_PATH','value':'/etc/c3po-reader','occurrences':2},
             'NETWORK':{'kind':'NETWORK','value':'c3po_c3po_internal','occurrences':1},
             'IMAGE_ID':{'kind':'IMAGE_ID','value':hostemu.BACKEND,'occurrences':1}}
    rendered=GENERIC.replace(b'@CONFIG_DIR@',b'/etc/c3po-reader').replace(b'@NETWORK@',b'c3po_c3po_internal').replace(b'@IMAGE_ID@',hostemu.BACKEND.encode())
    timer=b'[Timer]\nOnCalendar=Mon..Fri *-*-* 04:00:00 America/New_York\nUnit=c3po-reader.service\n'
    alert=b'[Service]\nType=oneshot\nExecStart=/usr/bin/true\n'
    return [f.unit('READER_SERVICE','c3po-reader.service','GENERIC_KINDS_V1',GENERIC,holders,rendered),
            f.unit('READER_TIMER','c3po-reader.timer','VERBATIM_V1',timer,{},timer),
            f.unit('READER_ALERT','c3po-reader-alert.service','VERBATIM_V1',alert,{},alert)],[rendered,timer,alert]


# ---------------------------------------------------------------- what the GO shows
def test_effects_shown_in_the_go_are_exactly_this_literal():
    """Written out by hand: a member that disappears from effects_of, or changes meaning, fails here."""
    host,docs=fresh();rows=hostemu.rows(host,UNITS);timer_sha='ec61b1d6cbd1d604e5c2177d186f9045e67bf21ecc092498691591dfd9164ee6'
    expected={'operation':'GO_WRITE_UNITS_EXCLUSIVE_INSTALL_01','directory':'/etc/systemd/system',
              'directory_row':{'path':'/etc/systemd/system','device':801,'inode':4001,'uid':0,'gid':0,'mode':0o755},
              'chain_sha256':f.sha(f.canonical(rows)),
              'units':[{'destination_name':'c3po-massive.service','mode_octal':'0644','profile':'MASSIVE_SUPERVISOR_SERVICE_V1',
                        'template_sha256':'9e7de1c6eaf937e5b1fc9540986fdbdf2a2f821a9c57b944f9534a605d07f04a','rendered_sha256':f.sha(RENDERED),
                        'rendered_bytes':len(RENDERED),'substitutions':dict(f.VALUES),'expect':'ABSENT'},
                       {'destination_name':'c3po-massive.timer','mode_octal':'0644','profile':'MASSIVE_SUPERVISOR_TIMER_V1','template_sha256':timer_sha,
                        'rendered_sha256':timer_sha,'rendered_bytes':234,'substitutions':{},'expect':'ABSENT'}],
              'files_to_create':2,'network_allowlist':['bridge'],'journal_placement':'B','data_volume_path':'/mnt/day-d-data','deploy_tree_path':None,
              'template_revision':'d7600b4d14f8a67694ffb37cde06b622f9a3bac3','acknowledged_leftovers':[],'evidence_boot_id_sha256':f.BOOT_SHA,
              'daemon_reload':{'performed_by_this_operation':False,'owner':'OPERATION_5_ACTIVATION_GO'},
              'external_processes':0,'pre_existing_objects_modified':False,'activation':False}
    assert f.canonical(m.effects_of(docs.plan))==f.canonical(expected)==f.canonical(docs.go['effects'])
    assert len(rows)==4 and [row['path'] for row in rows]==['/','/etc','/etc/systemd','/etc/systemd/system']
    # the continuation form: what is signed as present, and which leftovers are acknowledged, is visible too
    docs.plan['units'][0]['expect']={'device':801,'inode':7,'links':1}
    docs.plan['acknowledged_leftovers']=[{'name':'.hostops-0123456789abcdef-1.partial','device':801,'inode':9}]
    effects=m.effects_of(docs.plan)
    assert [unit['expect'] for unit in effects['units']]==['PRESENT','ABSENT'] and effects['files_to_create']==1
    assert effects['acknowledged_leftovers']==['.hostops-0123456789abcdef-1.partial']
    # placement A, the placement of the first epoch: the pair of journal paths, the placement and the deploy tree are all literal
    host,docs=fresh(placement='A');effects=docs.go['effects'];outside=f.reference_render(f.VALUES_A)
    assert (effects['journal_placement'],effects['deploy_tree_path'],effects['data_volume_path'])==('A','/opt/chief-of-staff-digital','/mnt/day-d-data')
    assert effects['units'][0]['substitutions']=={'IMAGE_ID':hostemu.BACKEND,'HOST_JOURNAL_ROOT':'/var/lib/c3po-bar/journal','CONTAINER_JOURNAL_ROOT':'/c3po-bar-journal',
        'HOST_STATE_ROOT':'/var/lib/c3po-bar/supervisor','HOST_CONFIG_DIR':'/etc/c3po-bar','NETWORK':'bridge'}
    assert (effects['units'][0]['rendered_sha256'],effects['units'][0]['rendered_bytes'])==(f.sha(outside),len(outside)) and outside!=RENDERED


# ---------------------------------------------------------------- the complete run
def test_complete_run_installs_the_two_supervisor_units_by_temporary_link_and_removal_with_no_process():
    host,docs=fresh();plan,real=docs.authenticate()
    def gate():
        host.log.append(('gate',));return real()
    receipt=docs.perform(host,gate=gate)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.COMPLETE_STATUS,'UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED',None) and f.sealed(receipt)
    assert new(host)==[SERVICE,TIMER],'no temporary, no drop-in, no enablement link is left'
    for path,content in ((SERVICE,RENDERED),(TIMER,f.TIMER)):
        node=host.tree.get(path);assert (node.kind,node.uid,node.gid,node.mode,node.nlink,bytes(node.content),node.synced)==('file',0,0,0o644,1,content,True)
    log=host.log;events=[entry for entry in log if entry[0] in hostemu.MUTATING+('fsync',)]
    names=[(entry[0],entry[1]) for entry in events]
    expected=[]
    for index,final in enumerate((SERVICE,TIMER)):
        expected+=[('create',temp(docs,index)),('write',temp(docs,index)),('fsync',temp(docs,index)),('link',temp(docs,index)),('fsync',UNITS),
                   ('unlink',temp(docs,index)),('fsync',UNITS)]
    assert names==expected,'service first, each file complete and synced before its name exists'
    creates=[entry for entry in log if entry[0]=='create'];assert all(entry[2]==CREATE and entry[3]==0o644 for entry in creates)
    assert [entry[2] for entry in log if entry[0]=='link']==[SERVICE,TIMER]
    mutating=[index for index,entry in enumerate(log) if entry[0] in hostemu.MUTATING]
    assert len(mutating)==8 and all(log[index-1]==('gate',) for index in mutating),'the gate is the call immediately before each mutating call'
    assert log.index(('umask',0o022))<mutating[0] and not [entry for entry in log if entry[0] in ('run','mkdir')]
    for name in (temp(docs,0),temp(docs,1)):
        base=os.path.basename(name);assert base.startswith('.') and base.endswith('.partial') and not re.search(r'\.(service|timer)$',base)
        assert re.fullmatch(m.LEFTOVER,base)
    ledger=receipt['ledger'];assert [row['state'] for row in ledger]==['INSTALLED_DURABLE']*2 and [row['path'] for row in ledger]==[SERVICE,TIMER]
    for row,content,path in zip(ledger,(RENDERED,f.TIMER),(SERVICE,TIMER)):
        node=host.tree.get(path)
        assert (row['bytes'],row['sha256_observed'],row['sha256_signed'])==(len(content),f.sha(content),f.sha(content))
        assert (row['mode_octal'],row['uid'],row['gid'],row['links'],row['device'],row['inode'])==('0644',0,0,1,node.dev,node.ino)
        assert row['temporary_removed'] and row['fsync_file'] and row['fsync_directory_after_link'] and row['fsync_directory_after_removal']
    assert receipt['mutating_calls']=={'issued':8,'succeeded':8,'failed_nothing_changed':0,'uncertain':0} and receipt['objects_left_by_this_run']==2
    assert receipt['external_processes']==0 and receipt['daemon_reload_owner']=='OPERATION_5_ACTIVATION_GO' and receipt['daemon_reload_performed'] is False
    assert receipt['readback']['status']=='COMPLETE' and receipt['precheck']['conflicts']['status']=='COMPLETE'
    effects=receipt['effects'];assert effects['daemon_reload']=={'performed_by_this_operation':False,'owner':'OPERATION_5_ACTIVATION_GO'}
    assert [unit['profile'] for unit in effects['units']]==['MASSIVE_SUPERVISOR_SERVICE_V1','MASSIVE_SUPERVISOR_TIMER_V1']
    assert effects['units'][0]['substitutions']==f.VALUES and effects['units'][0]['rendered_sha256']==f.sha(RENDERED)
    text=json.dumps(receipt);assert 'ExecStart' not in text and '--cap-drop' not in text and 'OnCalendar' not in text and len(f.line(receipt))<12000

def test_the_same_bytes_install_a_generic_three_unit_list_under_another_request():
    units,contents=reader_units();host,docs=fresh(units=units,allowlist=('c3po_c3po_internal',),volume=None)
    receipt=docs.run(host);assert receipt['outcome']=='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED'
    paths=[UNITS+'/'+unit['destination_name'] for unit in units];assert new(host)==sorted(paths)
    for path,content in zip(paths,contents):assert bytes(host.tree.get(path).content)==content and host.tree.get(path).mode==0o644
    assert [entry[2] for entry in host.log if entry[0]=='link']==paths


# ---------------------------------------------------------------- request validation, before any host access
def invalid(change,**options):
    host,docs=fresh(**options);change(docs.plan);docs.chain()
    code=refusal(docs.authenticate);result=docs.run(host)
    assert (result['status'],result['code'])==('REFUSED',code) and host.log==[];return code

def test_units_list_shape_names_and_expectations():
    for change in (lambda plan:plan.update(units=[]),lambda plan:plan.update(units=None),lambda plan:plan.update(units=plan['units']*5),
                   lambda plan:plan['units'][0].pop('profile'),lambda plan:plan['units'][0].update(extra=1),lambda plan:plan['units'][0].update(mode=0o600),
                   lambda plan:plan['units'][0].update(mode=0o755),lambda plan:plan['units'][0].update(mode='0644'),lambda plan:plan['units'][0].update(key='lower'),
                   lambda plan:plan['units'].__setitem__(0,'x'),lambda plan:plan['units'][0].update(placeholders=None)):
        assert invalid(change)=='UNITS_INVALID'
    for name in ('evil.service','c3po-massive.service.d','c3po-massive.socket','../c3po-x.service','c3po-.service','C3PO-massive.service',
                 'c3po-'+'x'*60+'.service','c3po-massive.service ','c3po-massive','timers.target.wants','c3po-a/b.service',None,7):
        assert invalid(lambda plan:plan['units'][0].update(destination_name=name))=='UNIT_NAME_INVALID'
    assert invalid(lambda plan:plan['units'][1].update(key='SUPERVISOR_SERVICE'))=='UNIT_NAME_DUPLICATE'
    units,_=reader_units();units[1]['destination_name']='c3po-reader.service'
    host=f.world(k);docs=f.Docs(k,f.install_fields(k,host,units=units,allowlist=('c3po_c3po_internal',),volume=None))
    assert refusal(docs.authenticate)=='UNIT_NAME_DUPLICATE'
    for expect in ('PRESENT',None,{},{'device':1,'inode':2},{'device':1,'inode':2,'links':3},{'device':1,'inode':0,'links':1},{'device':1,'inode':2,'links':True}):
        assert invalid(lambda plan:plan['units'][0].update(expect=expect))=='EXPECT_INVALID'
    def all_present(plan):
        for unit in plan['units']:unit['expect']={'device':1,'inode':2,'links':1}
    assert invalid(all_present)=='NOTHING_TO_CREATE'

def test_every_open_parameter_refuses_null_with_its_own_code():
    for change,code in ((lambda plan:plan.update(template_revision=None),'TEMPLATE_REVISION_UNBOUND'),(lambda plan:plan.update(template_revision='d7600b4'),'TEMPLATE_REVISION_UNBOUND'),
                        (lambda plan:plan.update(daemon_reload_owner=None),'RELOAD_OWNER_UNBOUND'),(lambda plan:plan.update(daemon_reload_owner='UNBOUND'),'RELOAD_OWNER_UNBOUND'),
                        (lambda plan:plan.update(daemon_reload_owner='this operation'),'RELOAD_OWNER_UNBOUND'),
                        (lambda plan:plan.update(evidence_boot_id_sha256=None),'EVIDENCE_BOOT_UNBOUND'),(lambda plan:plan.update(evidence_boot_id_sha256='0'*64),'EVIDENCE_BOOT_UNBOUND'),
                        (lambda plan:plan.update(network_allowlist=[]),'NETWORK_ALLOWLIST'),(lambda plan:plan.update(network_allowlist=None),'NETWORK_ALLOWLIST'),
                        (lambda plan:plan.update(network_allowlist=['host']),'NETWORK_FORBIDDEN'),(lambda plan:plan.update(network_allowlist=['other']),'NETWORK_NOT_AUTHORIZED'),
                        (lambda plan:plan.update(data_volume_path=None),'DATA_VOLUME_PATH'),(lambda plan:plan.update(data_volume_path='/mnt'),'B_HOST_JOURNAL_NOT_A_LEAF_OF_DATA_VOLUME'),
                        (lambda plan:plan.update(journal_placement=None),'PLACEMENT_UNKNOWN'),(lambda plan:plan.update(journal_placement='C'),'PLACEMENT_UNKNOWN'),
                        (lambda plan:plan.update(journal_placement='A',deploy_tree_path='/opt/chief-of-staff-digital'),'A_HOST_JOURNAL_INSIDE_DATA_VOLUME'),
                        (lambda plan:plan.update(deploy_tree_path='/opt/chief-of-staff-digital'),'DEPLOY_TREE_PATH'),
                        (lambda plan:plan['units'][0].update(rendered_sha256=None),'RENDERED_HASH_MISMATCH'),(lambda plan:plan['units'][0].update(rendered_bytes=None),'RENDERED_SIZE_MISMATCH'),
                        (lambda plan:plan['units'][0]['placeholders'].update(IMAGE_ID=None),'IMAGE_ID'),(lambda plan:plan['units'][0]['placeholders'].update(NETWORK=None),'NETWORK_NOT_AUTHORIZED'),
                        (lambda plan:plan['units'][0]['placeholders'].update(HOST_CONFIG_DIR=None),'PATH_INVALID'),
                        (lambda plan:plan.update(unit_directory=None),'CHAIN_ROW_INVALID'),(lambda plan:plan['unit_directory'][3].update(inode=None),'CHAIN_ROW_INVALID'),
                        (lambda plan:plan.update(acknowledged_leftovers=None),'LEFTOVERS_INVALID')):
        assert invalid(change)==code
    units,_=reader_units();host=f.world(k);docs=f.Docs(k,f.install_fields(k,host,units=units,allowlist=('c3po_c3po_internal',)))
    assert refusal(docs.authenticate)=='DATA_VOLUME_PATH','a data volume path with no supervisor unit to couple it to'
    for change in ({'journal_placement':'A'},{'journal_placement':'B'},{'deploy_tree_path':'/opt/chief-of-staff-digital'}):
        units,_=reader_units();host=f.world(k);docs=f.Docs(k,dict(f.install_fields(k,host,units=units,allowlist=('c3po_c3po_internal',),volume=None),**change))
        assert refusal(docs.authenticate)=='PLACEMENT_UNKNOWN','a placement or a deploy tree with no supervisor unit they belong to'

def test_placement_a_installs_the_unit_of_the_first_epoch_and_refuses_values_of_the_other_placement():
    host,docs=fresh(placement='A');receipt=docs.run(host);outside=f.reference_render(f.VALUES_A)
    assert receipt['outcome']=='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED' and bytes(host.tree.get(SERVICE).content)==outside
    assert b'--mount type=bind,source=/var/lib/c3po-bar/journal,target=/c3po-bar-journal ' in outside and b'RequiresMountsFor=/var/lib/c3po-bar/journal ' in outside
    assert (receipt['effects']['journal_placement'],receipt['ledger'][0]['sha256_observed'])==('A',f.sha(outside))
    assert not [entry for entry in host.log if type(entry[1]) is str and entry[1].startswith(('/mnt','/var/lib','/opt'))],'the installer opens none of the paths it renders'
    for change,code in ((lambda plan:plan.update(deploy_tree_path=None),'DEPLOY_TREE_PATH'),(lambda plan:plan.update(deploy_tree_path='/var/lib'),'A_HOST_JOURNAL_INSIDE_DEPLOY_TREE'),
                        (lambda plan:plan.update(deploy_tree_path='/var/lib/c3po-bar/journal'),'A_HOST_JOURNAL_INSIDE_DEPLOY_TREE'),
                        (lambda plan:plan.update(journal_placement='B',deploy_tree_path=None),'B_HOST_JOURNAL_NOT_A_LEAF_OF_DATA_VOLUME'),
                        (lambda plan:plan.update(data_volume_path='/var/lib'),'PRIVATE_ROOT_INSIDE_DATA_VOLUME'),
                        (lambda plan:plan.update(data_volume_path='/var/lib/c3po-bar/journal'),'A_HOST_JOURNAL_INSIDE_DATA_VOLUME'),
                        (lambda plan:plan.update(data_volume_path=None),'DATA_VOLUME_PATH')):
        assert invalid(change,placement='A')==code
    # the rendered hash signed for one placement's values cannot be installed with the other's
    host,docs=fresh(placement='A');docs.plan['units'][0]['placeholders']=dict(f.VALUES);docs.chain()
    assert refusal(docs.authenticate)=='A_HOST_JOURNAL_INSIDE_DATA_VOLUME'
    host,docs=fresh();docs.plan['units'][0]['placeholders']=dict(f.VALUES_A);docs.chain();assert refusal(docs.authenticate)=='B_HOST_JOURNAL_NOT_A_LEAF_OF_DATA_VOLUME'

def test_unit_directory_chain_has_a_code_floor_and_is_the_fixed_directory():
    for change,code in ((lambda plan:plan['unit_directory'].pop(),'CHAIN_ROW_INVALID'),(lambda plan:plan['unit_directory'][3].update(path='/etc/systemd/user'),'CHAIN_ROW_INVALID'),
                        (lambda plan:plan['unit_directory'][3].update(uid=1000),'CHAIN_ROW_UNSAFE'),(lambda plan:plan['unit_directory'][1].update(mode=0o777),'CHAIN_ROW_UNSAFE'),
                        (lambda plan:plan['unit_directory'][2].update(mode=0o775),'CHAIN_ROW_UNSAFE'),(lambda plan:plan['unit_directory'][3].update(mode=0o2755),'PARENT_SETGID')):
        assert invalid(change)==code
    for leftovers in ([{'name':'x.partial','device':1,'inode':2}],[{'name':'.hostops-0123456789abcdef-0.partial','device':1}],
                      [{'name':'.hostops-0123456789abcdef-0.partial','device':1,'inode':2}]*2,[{'name':'c3po-massive.service','device':1,'inode':2}],
                      [{'name':'.hostops-0123456789abcdef-0.partial','device':1,'inode':2}]*17):
        assert invalid(lambda plan:plan.update(acknowledged_leftovers=leftovers))=='LEFTOVERS_INVALID'

def test_templates_travel_in_the_signed_request_within_an_aggregate_cap():
    big=b'#'+b'x'*13000+b'\n';units=[f.unit('U%d'%index,'c3po-u%d.service'%index,'VERBATIM_V1',big,{},big) for index in range(2)]
    host=f.world(k);fields=f.install_fields(k,host,units=units,volume=None);docs=f.Docs(k,fields)
    assert refusal(docs.authenticate)=='TEMPLATE_TOO_LARGE'
    assert len(f.canonical(f.Docs(k,f.install_fields(k,f.world(k))).request))<65536


# ---------------------------------------------------------------- precheck
def test_unit_directory_must_be_the_pinned_one():
    for field,attribute in (('device','dev'),('inode','ino'),('uid','uid'),('gid','gid'),('mode','mode')):
        for path in ('/etc','/etc/systemd','/etc/systemd/system'):
            host,docs=fresh();node=host.tree.get(path);setattr(node,attribute,0o711 if field=='mode' else getattr(node,attribute)+1)
            receipt=refused(host,docs,'PARENT_IDENTITY_MISMATCH');assert receipt['unit_directory'][-1][field]!=docs.plan['unit_directory'][len(receipt['unit_directory'])-1][field]
    host,docs=fresh();host.tree.remove('/etc/systemd');host.tree.add('/etc/systemd',kind='symlink',mode=0o777);refused(host,docs,'PARENT_SYMLINK_COMPONENT')
    host,docs=fresh();host.tree.get(m.BOOT_ID_PATH).content=bytearray(b'11111111-2222-3333-4444-555555555555\n');refused(host,docs,'EVIDENCE_FROM_EARLIER_BOOT')

def units_table(receipt):return {row['key']:row for row in receipt['precheck']['units']}

def test_precheck_names_what_exists_with_distinct_codes_and_no_content():
    host,docs=fresh();host.tree.add(SERVICE,kind='file',mode=0o644,content=b'[Unit]\nDescription=foreign\n')
    row=units_table(refused(host,docs,'UNIT_PRESENT_FOREIGN_CONTENT'))['SUPERVISOR_SERVICE']
    assert (row['state'],row['type'],row['links'],row['bytes_equal_signed_render'])==('PRESENT_FOREIGN','file',1,False)
    assert 'size' not in row and 'sha256' not in row,'of a file that is not the signed render neither a digest nor a size is reported'
    host,docs=fresh();host.tree.add(SERVICE,kind='file',mode=0o600,content=RENDERED)              # right bytes, wrong mode: not what this code creates
    row=units_table(refused(host,docs,'UNIT_PRESENT_FOREIGN_CONTENT'))['SUPERVISOR_SERVICE']
    assert (row['mode_octal'],row['bytes_equal_signed_render'],row['sha256'],row['size'])==('0600',True,f.sha(RENDERED),len(RENDERED))
    host,docs=fresh();host.tree.add(SERVICE,kind='file',mode=0o644,content=b'')                    # zero bytes under a unit name
    assert units_table(refused(host,docs,'UNIT_PRESENT_FOREIGN_CONTENT'))['SUPERVISOR_SERVICE']['bytes_equal_signed_render'] is False
    for kind in ('symlink','dir','fifo'):
        host,docs=fresh();host.tree.add(TIMER,kind=kind,mode=0o777)
        rows=units_table(refused(host,docs,'UNIT_NAME_OCCUPIED'))
        assert rows['SUPERVISOR_TIMER']['state']=='OCCUPIED_NOT_REGULAR' and rows['SUPERVISOR_SERVICE']['state']=='OK_ABSENT','both names are evaluated'
        assert 'size' not in rows['SUPERVISOR_TIMER']
    host,docs=fresh();host.tree.add(SERVICE,kind='file',mode=0o644,content=RENDERED)
    rows=units_table(refused(host,docs,'PRIOR_PARTIAL_REQUIRES_RECONCILIATION'))
    assert rows['SUPERVISOR_SERVICE']['state']=='PRESENT_EQUAL_NOT_SIGNED' and rows['SUPERVISOR_SERVICE']['sha256']==f.sha(RENDERED) and rows['SUPERVISOR_TIMER']['state']=='OK_ABSENT'
    host,docs=fresh();host.tree.add(TIMER,kind='file',mode=0o644,content=f.TIMER);refused(host,docs,'PRIOR_PARTIAL_REQUIRES_RECONCILIATION')
    host,docs=fresh();host.tree.add(SERVICE,kind='file',mode=0o644,content=RENDERED);host.tree.add(TIMER,kind='file',mode=0o644,content=f.TIMER)
    receipt=refused(host,docs,'ALL_UNITS_PRESENT');assert 'INSTALLED' not in json.dumps(receipt['precheck']),'what exists, never a statement that an installation happened'
    assert 'ExecStart' not in json.dumps(receipt)
    host,docs=fresh();host.tree.add(UNITS+'/.hostops-0123456789abcdef-0.partial',kind='file',mode=0o644,content=b'half')
    receipt=refused(host,docs,'PRIOR_PARTIAL_REQUIRES_RECONCILIATION')
    assert receipt['precheck']['conflicts']['leftovers_not_acknowledged']==['.hostops-0123456789abcdef-0.partial'] and receipt['precheck']['conflicts']['leftovers'][0]['size']==4
    host,docs=fresh();host.tree.add(temp(docs,1),kind='file',mode=0o644);refused(host,docs,'TEMPORARY_NAME_OCCUPIED')
    host,docs=fresh();node=host.tree.add(SERVICE,kind='file',mode=0o644,content=RENDERED)
    host.tree.get(UNITS).children['.hostops-0123456789abcdef-0.partial']=node;node.nlink=2
    rows=units_table(refused(host,docs,'PRIOR_PARTIAL_REQUIRES_RECONCILIATION'));assert rows['SUPERVISOR_SERVICE']['links']==2

@pytest.mark.parametrize('attribute',['gid','uid'])
def test_a_unit_file_of_another_group_or_owner_is_not_what_this_code_installs_whether_signed_absent_or_present(attribute):
    """Equal bytes, mode 0644, one link, but group 4 (or owner 4): not the file this code creates. Signed as absent it is
    foreign content; signed as present, with its exact identity, it is still not verified."""
    host,docs=fresh();host.tree.add(SERVICE,kind='file',mode=0o644,content=RENDERED,**{attribute:4})
    row=units_table(refused(host,docs,'UNIT_PRESENT_FOREIGN_CONTENT'))['SUPERVISOR_SERVICE']
    assert (row['state'],row[attribute],row['mode_octal'],row['links'],row['bytes_equal_signed_render'])==('PRESENT_FOREIGN',4,'0644',1,True)
    host,docs=fresh();node=host.tree.add(SERVICE,kind='file',mode=0o644,content=RENDERED,**{attribute:4})
    docs.plan['units'][0]['expect']={'device':node.dev,'inode':node.ino,'links':1};docs.chain()
    row=units_table(refused(host,docs,'EXPECTATION_MISMATCH'))['SUPERVISOR_SERVICE']
    assert (row['state'],row[attribute],row['bytes_equal_signed_render'],row['device'],row['inode'])==('PRESENT_IDENTITY_MISMATCH',4,True,node.dev,node.ino)
    # the control: the same file as root:root is verified against the render and the signed identity, and left alone
    host,docs=fresh();node=host.tree.add(SERVICE,kind='file',mode=0o644,content=RENDERED);before=node.stat()
    docs.plan['units'][0]['expect']={'device':node.dev,'inode':node.ino,'links':1};docs.chain();receipt=docs.run(host)
    assert receipt['outcome']=='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED' and receipt['ledger'][0]['state']=='PRESENT_VERIFIED_NOT_TOUCHED' and node.stat()==before

def test_all_units_present_is_said_only_of_settled_files():
    """Both names hold the signed render, but one still shares its inode with a temporary (a death between link and
    removal), or a temporary lies beside them: that is the state of an interrupted run, not "all present"."""
    def both(host):
        service=host.tree.add(SERVICE,kind='file',mode=0o644,content=RENDERED);timer=host.tree.add(TIMER,kind='file',mode=0o644,content=f.TIMER)
        return service,timer
    host,docs=fresh();both(host);refused(host,docs,'ALL_UNITS_PRESENT')
    host,docs=fresh();service,timer=both(host);host.tree.get(UNITS).children['.hostops-0123456789abcdef-1.partial']=timer;timer.nlink=2
    receipt=refused(host,docs,'PRIOR_PARTIAL_REQUIRES_RECONCILIATION');rows=units_table(receipt)
    assert (rows['SUPERVISOR_SERVICE']['links'],rows['SUPERVISOR_TIMER']['links'])==(1,2) and receipt['precheck']['conflicts']['leftovers_not_acknowledged']==['.hostops-0123456789abcdef-1.partial']
    host,docs=fresh();both(host);host.tree.add(UNITS+'/.hostops-0123456789abcdef-0.partial',kind='file',mode=0o644,content=b'half')
    refused(host,docs,'PRIOR_PARTIAL_REQUIRES_RECONCILIATION')                 # one-link files, but a temporary nobody acknowledged
    host,docs=fresh();service,timer=both(host);timer.nlink=2                    # two links, the other name somewhere else
    refused(host,docs,'PRIOR_PARTIAL_REQUIRES_RECONCILIATION')

def test_foreign_unit_content_never_leaves_as_a_digest_or_a_size():
    secret=b'[Service]\nEnvironment=API_KEY=never-emit-inline-secret-0123456789\n'
    host,docs=fresh();host.tree.add(SERVICE,kind='file',mode=0o644,content=secret);receipt=refused(host,docs,'UNIT_PRESENT_FOREIGN_CONTENT')
    text=json.dumps(receipt);row=units_table(receipt)['SUPERVISOR_SERVICE']
    for value in (f.sha(secret),'never-emit','"size": %d'%len(secret),'"size":%d'%len(secret)):assert value not in text
    assert len(secret) not in [value for value in row.values() if type(value) is int] and set(row)=={'key','destination_name','expected','observed','type','uid','gid','mode_octal','links',
                                                                 'device','inode','bytes_equal_signed_render','state'}

LOOKUP=['/etc/systemd/system.control','/run/systemd/system.control','/run/systemd/transient','/run/systemd/generator.early','/etc/systemd/system',
        '/etc/systemd/system.attached','/run/systemd/system','/run/systemd/system.attached','/run/systemd/generator','/usr/local/lib/systemd/system',
        '/usr/lib/systemd/system','/run/systemd/generator.late']
def test_static_lookup_directories_cover_the_manager_search_path():
    assert m.LOOKUP_DIRECTORIES==LOOKUP and m.SCOPE['conflict_scan']['lookup_directories']==LOOKUP
    assert m.drop_in_names('c3po-massive.service')==['c3po-massive.service.d','service.d','c3po-.service.d']
    assert m.drop_in_names('c3po-reader-alert.service')==['c3po-reader-alert.service.d','service.d','c3po-.service.d','c3po-reader-.service.d']
    assert m.drop_in_names('c3po-massive.timer')==['c3po-massive.timer.d','timer.d','c3po-.timer.d']

@pytest.mark.parametrize('directory',LOOKUP)
@pytest.mark.parametrize('entry,code',[('c3po-massive.service.d','DROP_IN_PRESENT'),('c3po-massive.timer.d','DROP_IN_PRESENT'),('service.d','DROP_IN_PRESENT'),
    ('timer.d','DROP_IN_PRESENT'),('c3po-.service.d','DROP_IN_PRESENT'),('c3po-.timer.d','DROP_IN_PRESENT'),
    ('timers.target.wants/c3po-massive.timer','ENABLEMENT_LINK_PRESENT'),('multi-user.target.wants/c3po-massive.service','ENABLEMENT_LINK_PRESENT'),
    ('other.target.requires/c3po-massive.service','ENABLEMENT_LINK_PRESENT'),('docker.service.upholds/c3po-massive.service','ENABLEMENT_LINK_PRESENT'),
    ('c3po-massive.service','UNIT_SHADOWED_IN_OTHER_PATH'),('c3po-massive.timer','UNIT_SHADOWED_IN_OTHER_PATH'),
    # the unit's own dependency directories: links inside them are dependencies OF the unit, with no drop-in at all
    ('c3po-massive.service.wants','OWN_DEPENDENCY_DIRECTORY_PRESENT'),('c3po-massive.service.requires','OWN_DEPENDENCY_DIRECTORY_PRESENT'),
    ('c3po-massive.service.upholds','OWN_DEPENDENCY_DIRECTORY_PRESENT'),('c3po-massive.timer.wants','OWN_DEPENDENCY_DIRECTORY_PRESENT'),
    ('c3po-massive.timer.requires','OWN_DEPENDENCY_DIRECTORY_PRESENT'),('c3po-massive.timer.upholds','OWN_DEPENDENCY_DIRECTORY_PRESENT')])
def test_every_conflict_object_in_every_lookup_directory_refuses_the_install(directory,entry,code):
    if directory==UNITS and code=='UNIT_SHADOWED_IN_OTHER_PATH':return                # there it is the destination itself
    host,docs=fresh();host.tree.add(directory)
    kind='symlink' if '/' in entry else 'file' if entry.endswith(('.service','.timer')) else 'dir'
    host.tree.add(directory+'/'+entry,kind=kind,mode=0o777 if kind=='symlink' else 0o755)
    receipt=refused(host,docs,code);found=receipt['precheck']['conflicts']['findings']
    assert {'code':code,'directory':directory,'name':entry.split('/')[-1],'within':entry.split('/')[0] if '/' in entry else None} in found
    assert not [e for e in host.log if e[0]=='read' and e[1]!=m.BOOT_ID_PATH]

@pytest.mark.parametrize('directory',LOOKUP)
@pytest.mark.parametrize('alias,target,name',[('backup.service','c3po-massive.service','c3po-massive.service'),
    ('other.timer','/etc/systemd/system/c3po-massive.timer','c3po-massive.timer'),('x.service','../system/c3po-massive.service','c3po-massive.service')])
def test_an_alias_link_to_a_signed_name_in_any_lookup_directory_refuses_the_install(directory,alias,target,name):
    """A symbolic link whose text ends in the unit's name makes its own name an alias of the unit once the unit exists."""
    host,docs=fresh();host.tree.add(directory);host.tree.add(directory+'/'+alias,kind='symlink',mode=0o777).target=target
    receipt=refused(host,docs,'ALIAS_LINK_PRESENT')
    assert {'code':'ALIAS_LINK_PRESENT','directory':directory,'name':alias,'within':name} in receipt['precheck']['conflicts']['findings']
    assert [entry[1] for entry in host.log if entry[0]=='readlink']==[directory+'/'+alias],'only the link text is read; nothing is followed'
    assert not [e for e in host.log if e[0]=='read' and e[1]!=m.BOOT_ID_PATH]

def test_own_dependency_directory_and_alias_edge_cases():
    # a link inside the unit's own .wants directory is found whatever the directory holds, and even when it is empty
    host,docs=fresh();host.tree.add(UNITS+'/c3po-massive.service.wants/other.service',kind='symlink',mode=0o777)
    receipt=refused(host,docs,'OWN_DEPENDENCY_DIRECTORY_PRESENT');assert receipt['precheck']['conflicts']['finding_codes']==['OWN_DEPENDENCY_DIRECTORY_PRESENT']
    # not a directory at that name: still the finding (and the scan of that lookup directory is incomplete)
    host,docs=fresh();host.tree.add(UNITS+'/c3po-massive.timer.requires',kind='symlink',mode=0o777)
    receipt=refused(host,docs,'OWN_DEPENDENCY_DIRECTORY_PRESENT');assert receipt['precheck']['conflicts']['directories'][UNITS]['code']=='DEPENDENCY_DIRECTORY_NOT_A_DIRECTORY'
    # links that are not aliases of a signed name are left alone: another target, another type, a regular file of that name
    host,docs=fresh();host.tree.add(UNITS+'/backup.service',kind='symlink',mode=0o777).target='/usr/lib/systemd/system/docker.service'
    host.tree.add(UNITS+'/c3po-massive.service.bak',kind='symlink',mode=0o777).target='c3po-massive.service'
    host.tree.add('/usr/lib/systemd/system/plain.service',kind='file',mode=0o644,content=b'c3po-massive.service')
    assert docs.run(host)['outcome']=='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED'
    assert sorted(entry[1] for entry in host.log if entry[0]=='readlink')==[UNITS+'/backup.service']
    # a link whose text cannot be read makes the scan unavailable, never an absence
    host,docs=fresh();host.tree.add(UNITS+'/backup.service',kind='symlink',mode=0o777).target='c3po-massive.service'
    at_event(host,'readlink',1,raising(OSError,errno.EIO,'injected'));receipt=refused(host,docs,'CONFLICT_SCAN_UNAVAILABLE')
    assert receipt['precheck']['conflicts']['directories'][UNITS]=={'status':'UNAVAILABLE','code':'OS_ERROR','errno':errno.EIO}

def test_a_scan_that_cannot_be_completed_is_never_an_absence():
    host,docs=fresh();host.tree.remove('/usr/lib');host.tree.add('/usr/lib',kind='symlink',mode=0o777)
    receipt=refused(host,docs,'CONFLICT_SCAN_UNAVAILABLE');assert receipt['precheck']['conflicts']['directories']['/usr/lib/systemd/system']=={'status':'UNAVAILABLE','code':'SYMLINK_COMPONENT'}
    host,docs=fresh();host.tree.remove(UNITS+'/timers.target.wants');host.tree.add(UNITS+'/timers.target.wants',kind='symlink',mode=0o777)
    receipt=refused(host,docs,'CONFLICT_SCAN_UNAVAILABLE');assert receipt['precheck']['conflicts']['directories'][UNITS]['code']=='DEPENDENCY_DIRECTORY_NOT_A_DIRECTORY'
    host,docs=fresh()
    for index in range(4097):host.tree.add('/usr/lib/systemd/system/unit-%04d.service'%index,kind='file')
    receipt=refused(host,docs,'CONFLICT_SCAN_UNAVAILABLE');assert receipt['precheck']['conflicts']['directories']['/usr/lib/systemd/system']['code']=='SCAN_LIMIT'
    host,docs=fresh()
    for name in ('/run/systemd','/usr/lib/systemd/system'):host.tree.remove(name)         # a lookup directory that does not exist is a proved absence
    assert docs.run(host)['outcome']=='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED'


# ---------------------------------------------------------------- failures at and after a creation
def test_file_placed_between_precheck_and_link_keeps_its_bytes():
    for position,final in ((1,SERVICE),(2,TIMER)):
        host,docs=fresh()
        at_event(host,'link',position,lambda host,detail:host.tree.add(detail[1],kind='file',mode=0o600,content=b'foreign bytes'))
        receipt=docs.run(host);node=host.tree.get(final)
        assert (bytes(node.content),node.mode,node.nlink)==(b'foreign bytes',0o600,1),'a link never replaces anything'
        row=receipt['ledger'][position-1]
        assert (row['state'],row['code'],row['errno'],row['temporary_removed'])==('NOT_CREATED','DESTINATION_APPEARED_AFTER_PRECHECK',errno.EEXIST,True)
        assert host.tree.get(temp(docs,position-1)) is None and receipt['status']==m.PARTIAL_STATUS and receipt['code']=='DESTINATION_APPEARED_AFTER_PRECHECK'
        assert receipt['objects_left_by_this_run']==position-1 and new(host)==sorted([SERVICE,TIMER][:position])

@pytest.mark.parametrize('number,code',[(errno.EEXIST,'TEMPORARY_NAME_OCCUPIED'),(errno.EROFS,'FILESYSTEM_READ_ONLY'),(errno.ENOSPC,'FILESYSTEM_FULL'),
                                        (errno.EDQUOT,'FILESYSTEM_FULL'),(errno.EACCES,'FILESYSTEM_ACCESS_DENIED'),(errno.EPERM,'FILESYSTEM_ACCESS_DENIED'),
                                        (errno.EIO,'FILESYSTEM_ERROR'),(errno.ELOOP,'FILESYSTEM_ERROR')])
def test_failed_temporary_creation_is_a_refusal_only_when_nothing_was_created(number,code):
    host,docs=fresh();at_event(host,'create',1,raising(OSError,number,'injected'));receipt=docs.run(host)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('REFUSED','REFUSED_NOTHING_CREATED',code) and new(host)==[]
    assert (receipt['ledger'][0]['state'],receipt['ledger'][0]['errno'],receipt['ledger'][1]['state'])==('NOT_CREATED',number,'NOT_ATTEMPTED')
    host,docs=fresh();at_event(host,'create',2,raising(OSError,number,'injected'));receipt=docs.run(host)
    assert (receipt['status'],receipt['code'])==(m.PARTIAL_STATUS,code) and new(host)==[SERVICE]
    assert [row['state'] for row in receipt['ledger']]==['INSTALLED_DURABLE','NOT_CREATED']

def after(host,trigger,occurrence,kind,count,action):
    """Arm at the n-th call named trigger; then act on the following call of the given kind."""
    state={'armed':False,'seen':0,'triggers':0}
    def hook(host,name,detail,calls):
        if state['armed'] and name==kind:
            state['seen']+=1
            if state['seen']==count:state['armed']=False;action(host,detail)
        if name==trigger:
            state['triggers']+=1
            if state['triggers']==occurrence:state['armed']=True;state['seen']=0
    host.hook=hook

@pytest.mark.parametrize('unit',[1,2])
@pytest.mark.parametrize('trigger,kind,count,number,state,code,left',[
    # before the final name exists the run withdraws its own temporary (identity proved): nothing is left to remove later
    ('create','write',1,errno.ENOSPC,'NOT_CREATED','FILESYSTEM_FULL','none'),('create','write',1,errno.EIO,'NOT_CREATED','FILESYSTEM_ERROR','none'),
    ('create','fsync',1,errno.EIO,'NOT_CREATED','FSYNC_FAILED','none'),('create','fstat',1,errno.EIO,'NOT_CREATED','CREATED_STAT_FAILED','none'),
    ('create','link',1,errno.EROFS,'NOT_CREATED','FILESYSTEM_READ_ONLY','none'),('create','link',1,errno.EMLINK,'NOT_CREATED','FILESYSTEM_ERROR','none'),
    ('link','fsync',1,errno.EIO,'LINKED_TEMPORARY_PRESENT','FSYNC_FAILED','both'),('link','lstat',1,errno.EIO,'LINKED_TEMPORARY_PRESENT','TEMPORARY_REMOVAL_FAILED','both'),
    ('link','unlink',1,errno.EACCES,'LINKED_TEMPORARY_PRESENT','TEMPORARY_REMOVAL_FAILED','both'),
    ('unlink','fsync',1,errno.EIO,'INSTALLED_NOT_DURABLE','FSYNC_FAILED','final'),('unlink','fstat',1,errno.EIO,'INSTALLED_NOT_DURABLE','CREATED_STAT_FAILED','final')])
def test_a_failure_after_the_temporary_exists_is_never_a_refusal_and_names_the_state(unit,trigger,kind,count,number,state,code,left):
    host,docs=fresh();after(host,trigger,unit,kind,count,raising(OSError,number,'injected'));receipt=docs.run(host)
    row=receipt['ledger'][unit-1];final=(SERVICE,TIMER)[unit-1];name=temp(docs,unit-1)
    assert (row['state'],row['code'],row['errno'])==(state,code,number)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,'PARTIAL_REQUIRES_RECONCILIATION',code)
    present={'none':[],'temp':[name],'both':sorted([name,final]),'final':[final]}[left];assert new(host)==sorted(([SERVICE] if unit==2 else [])+present)
    assert receipt['objects_left_by_this_run']==len(new(host)) and receipt['mutating_calls']['succeeded']>=1
    if left=='none':
        assert (row['temporary_removed'],row['temporary_removal_code'],row['temporary_removal_errno'])==(True,None,None)
        assert [entry[1] for entry in host.log if entry[0]=='unlink'][-1]==name and host.tree.get(final) is None
    if unit==1:assert receipt['ledger'][1]['state']=='NOT_ATTEMPTED' and host.tree.get(TIMER) is None
    for path in new(host):
        if unit_named(host,path):assert bytes(host.tree.get(path).content) in (RENDERED,f.TIMER),'only complete bytes ever stand under a unit name'

def test_a_temporary_that_cannot_be_withdrawn_stays_and_is_labelled():
    """The withdrawal is itself a gated, identity-proved removal: when it cannot be made the temporary stays, named."""
    host,docs=fresh();state={'seen':0}
    def hook(host,name,detail,calls):
        if name=='write' and not state['seen']:
            state['seen']=1;raise OSError(errno.ENOSPC,'injected')
        if name=='unlink':raise OSError(errno.EACCES,'injected')
    host.hook=hook;receipt=docs.run(host);row=receipt['ledger'][0]
    assert (row['state'],row['code'],row['errno'],row['temporary_removed'],row['temporary_removal_code'],row['temporary_removal_errno'])==(
        'TEMPORARY_ONLY','FILESYSTEM_FULL',errno.ENOSPC,False,'TEMPORARY_REMOVAL_FAILED',errno.EACCES)
    assert new(host)==[temp(docs,0)] and receipt['objects_left_by_this_run']==1 and receipt['status']==m.PARTIAL_STATUS
    # the name no longer shows the descriptor held: it is somebody else's object and is never removed
    host,docs=fresh()
    def swap(host,detail):
        directory=host.tree.get(UNITS);name=os.path.basename(temp(docs,0));directory.children.pop(name);host.tree.add(temp(docs,0),kind='file',mode=0o600,content=b'somebody else')
        raise OSError(errno.EIO,'injected')
    after(host,'create',1,'fsync',1,swap);receipt=docs.run(host);row=receipt['ledger'][0]
    assert (row['state'],row['code'],row['temporary_removed'],row['temporary_removal_code'])==('TEMPORARY_ONLY','FSYNC_FAILED',False,'TEMPORARY_REPLACED')
    assert bytes(host.tree.get(temp(docs,0)).content)==b'somebody else' and not [entry for entry in host.log if entry[0]=='unlink']
    # an expired window forbids the removal like any other mutating call
    host,docs=fresh();plan,real=docs.authenticate();state={'expired':False}
    def gate():
        if state['expired']:raise m.Refused('GO_EXPIRED')
        return real()
    def expire(host,detail):
        state['expired']=True;raise OSError(errno.EIO,'injected')
    after(host,'create',1,'fsync',1,expire);receipt=docs.perform(host,gate=gate);row=receipt['ledger'][0]
    assert (row['state'],row['code'],row['temporary_removal_code'])==('TEMPORARY_ONLY','FSYNC_FAILED','GO_EXPIRED') and new(host)==[temp(docs,0)]
    assert not [entry for entry in host.log if entry[0]=='unlink']

def test_temporary_swapped_right_before_the_link_is_caught_and_no_name_is_given_to_it():
    """link() acts on the name, not on the descriptor held: the name is looked at again immediately before it."""
    for kind in ('symlink','file'):
        host,docs=fresh();seen=[0]
        def hook(host,name,detail,calls,kind=kind):
            if name=='lstat' and detail[0]==temp(docs,0) and not seen[0]:
                seen[0]=1;directory=host.tree.get(UNITS);own=directory.children.pop(os.path.basename(detail[0]));own.nlink-=1
                host.tree.add(detail[0],kind=kind,mode=0o777 if kind=='symlink' else 0o644,content=RENDERED if kind=='file' else b'')
        host.hook=hook;receipt=docs.run(host);row=receipt['ledger'][0]
        assert (row['state'],row['code'],row['temporary_removed'])==('TEMPORARY_ONLY','TEMPORARY_REPLACED',False) and receipt['status']==m.PARTIAL_STATUS
        assert host.tree.get(SERVICE) is None and not [entry for entry in host.log if entry[0] in ('link','unlink')]
        assert host.tree.get(temp(docs,0)).kind==kind,'the foreign object is left where it is'
    # a second link on the run's own file is not the file the run wrote alone either
    host,docs=fresh();seen=[0]
    def hook(host,name,detail,calls):
        if name=='lstat' and detail[0]==temp(docs,0) and not seen[0]:
            seen[0]=1;directory=host.tree.get(UNITS);own=directory.children[os.path.basename(detail[0])];directory.children['.extra']=own;own.nlink+=1
    host.hook=hook;receipt=docs.run(host);assert receipt['ledger'][0]['code']=='TEMPORARY_REPLACED' and host.tree.get(SERVICE) is None
    # the residual: a swap after that look and before link() gives the final name to the foreign object; it is labelled, never complete
    host,docs=fresh()
    def late(host,detail):
        directory=host.tree.get(UNITS);own=directory.children.pop(os.path.basename(detail[0]));own.nlink-=1;host.tree.add(detail[0],kind='symlink',mode=0o777)
    at_event(host,'link',1,late);receipt=docs.run(host);row=receipt['ledger'][0]
    assert (row['state'],row['code'],receipt['status'],receipt['outcome'])==('LINKED_TEMPORARY_PRESENT','TEMPORARY_REPLACED',m.PARTIAL_STATUS,'PARTIAL_REQUIRES_RECONCILIATION')
    assert host.tree.get(SERVICE).kind=='symlink' and receipt['ledger'][1]['state']=='NOT_ATTEMPTED'

def test_short_write_wrong_metadata_and_a_replaced_temporary_are_labelled_and_nothing_is_repaired():
    host,docs=fresh();host.write=lambda fd,data:(host.event('write',host.path_of(fd),0),0)[1];receipt=docs.run(host)
    assert (receipt['ledger'][0]['state'],receipt['code'],receipt['status'])==('NOT_CREATED','WRITE_INCOMPLETE',m.PARTIAL_STATUS) and new(host)==[]
    host,docs=fresh();host.creator=(0,1000);receipt=docs.run(host)
    assert (receipt['ledger'][0]['state'],receipt['code'],receipt['ledger'][0]['gid'])==('NOT_CREATED','CREATED_METADATA_MISMATCH',1000) and new(host)==[]
    assert not [entry for entry in host.log if entry[0]=='link'],'a file with the wrong group never gets a unit name; no chown exists in this source'
    host,docs=fresh()
    def keep(mask):host.event('umask',mask);return 0o022
    host.umask=keep;host.mask=0o077;receipt=docs.run(host)                 # a umask that did not take: 0600 instead of 0644 is caught, not corrected
    assert (receipt['code'],receipt['ledger'][0]['mode_octal'])==('CREATED_METADATA_MISMATCH','0600') and new(host)==[]
    host,docs=fresh();host.created_device=899;receipt=docs.run(host)     # the file is not on the device of the pinned directory
    assert (receipt['ledger'][0]['state'],receipt['code'],receipt['ledger'][0]['device'])==('NOT_CREATED','CREATED_METADATA_MISMATCH',899) and new(host)==[]
    host,docs=fresh()
    def swap(host,detail):
        directory=host.tree.get(UNITS);name=os.path.basename(detail[0]);own=directory.children.pop(name);own.nlink-=1
        host.tree.add(detail[0],kind='file',mode=0o600,content=b'somebody else')
    after(host,'link',1,'lstat',1,swap);receipt=docs.run(host)
    row=receipt['ledger'][0];assert (row['state'],row['code'],row['temporary_removed'])==('LINKED_TEMPORARY_PRESENT','TEMPORARY_REPLACED',False)
    assert bytes(host.tree.get(temp(docs,0)).content)==b'somebody else' and bytes(host.tree.get(SERVICE).content)==RENDERED and receipt['status']==m.PARTIAL_STATUS
    assert not [entry for entry in host.log if entry[0]=='unlink'],'a name that no longer shows the held inode is never removed'

def test_a_second_link_or_foreign_bytes_on_the_temporary_are_caught_on_the_descriptor_before_any_unit_name_exists():
    """Between the fsync of the temporary and its fstat somebody gives it a second name, or appends to it. It is no
    longer the file this run wrote alone: the check on the descriptor withdraws it; no name systemd loads is given."""
    host,docs=fresh()
    def second_name(host,detail):
        directory=host.tree.get(UNITS);own=directory.children[os.path.basename(detail[0])];directory.children['.extra']=own;own.nlink+=1
    after(host,'create',1,'fstat',1,second_name);receipt=docs.run(host);row=receipt['ledger'][0]
    assert (row['state'],row['code'],row['links'],row['temporary_removed'],row['temporary_removal_code'])==('NOT_CREATED','CREATED_METADATA_MISMATCH',2,True,None)
    assert new(host)==[UNITS+'/.extra'] and not [entry for entry in host.log if entry[0]=='link'] and receipt['status']==m.PARTIAL_STATUS
    assert receipt['ledger'][1]['state']=='NOT_ATTEMPTED' and receipt['objects_left_by_this_run']==0
    host,docs=fresh()
    def appended(host,detail):host.tree.get(detail[0]).content.extend(b'ExecStartPre=/usr/bin/true\n')
    after(host,'create',1,'fstat',1,appended);receipt=docs.run(host);row=receipt['ledger'][0]
    assert (row['state'],row['code'],row['bytes'],row['temporary_removed'])==('NOT_CREATED','CREATED_METADATA_MISMATCH',len(RENDERED),True)
    assert new(host)==[] and not [entry for entry in host.log if entry[0]=='link'],'bytes that are not the signed render never stand under a unit name'
    assert receipt['status']==m.PARTIAL_STATUS and receipt['ledger'][1]['state']=='NOT_ATTEMPTED'

def test_a_file_that_keeps_a_second_name_after_the_removal_of_the_temporary_is_not_called_installed():
    """Somebody links the file under a third name before the temporary is removed: after the removal it still has two
    links. The run stops there; the second unit is not attempted."""
    host,docs=fresh()
    def third_name(host,detail):
        directory=host.tree.get(UNITS);own=directory.children[os.path.basename(detail[0])];directory.children['.extra']=own;own.nlink+=1
    after(host,'link',1,'unlink',1,third_name);receipt=docs.run(host);row=receipt['ledger'][0]
    assert (row['state'],row['code'],row['links'],row['temporary_removed'])==('INSTALLED_NOT_DURABLE','CREATED_METADATA_MISMATCH',2,True)
    assert receipt['ledger'][1]['state']=='NOT_ATTEMPTED' and host.tree.get(TIMER) is None and receipt['readback'] is None
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,'PARTIAL_REQUIRES_RECONCILIATION','CREATED_METADATA_MISMATCH')
    assert new(host)==sorted([UNITS+'/.extra',SERVICE]) and len([entry for entry in host.log if entry[0]=='create'])==1

def test_unit_directory_replaced_between_two_units_stops_the_run():
    host,docs=fresh()
    def replace(host,detail):
        etc=host.tree.get('/etc/systemd');old=etc.children.pop('system');etc.children['system.old']=old;host.tree.add(UNITS,mode=0o755)
    after(host,'unlink',1,'fsync',1,replace);receipt=docs.run(host)
    assert [row['state'] for row in receipt['ledger']]==['INSTALLED_DURABLE','NOT_ATTEMPTED'] and receipt['ledger'][1]['code']=='PARENT_REPLACED'
    assert receipt['status']==m.PARTIAL_STATUS and host.tree.get(TIMER) is None and len([e for e in host.log if e[0]=='create'])==1

def test_unit_directory_replaced_between_the_temporary_and_the_link_stops_before_the_name_exists():
    host,docs=fresh()
    def replace(host,detail):
        etc=host.tree.get('/etc/systemd');old=etc.children.pop('system');etc.children['system.old']=old;host.tree.add(UNITS,mode=0o755)
    after(host,'create',1,'fsync',1,replace);receipt=docs.run(host);row=receipt['ledger'][0]
    assert (row['state'],row['code'])==('TEMPORARY_ONLY','PARENT_REPLACED') and receipt['status']==m.PARTIAL_STATUS
    assert not [entry for entry in host.log if entry[0]=='link'],'no name is given to the file in a directory that is no longer the pinned one'
    assert host.tree.get('/etc/systemd/system.old/c3po-massive.service') is None and host.tree.get(SERVICE) is None

@pytest.mark.parametrize('code',['GO_EXPIRED','CLOCK_REVERSED'])
def test_window_expiry_or_clock_reversal_issues_no_further_mutating_call(code):
    reference,docs=fresh();plan,real=docs.authenticate();counter=[0]
    def counting():
        counter[0]+=1;return real()
    docs.perform(reference,gate=counting);states=set()
    for limit in range(1,counter[0]+1):
        host,docs=fresh();plan,real=docs.authenticate();calls=[0];stopped=[None]
        def gate():
            calls[0]+=1
            if calls[0]>=limit:
                if stopped[0] is None:stopped[0]=len(host.log)
                raise m.Refused(code)
            return real()
        try:receipt=docs.perform(host,gate=gate)
        except m.Refused:
            assert limit==1 and host.log==[];continue
        assert not [entry for entry in host.log[stopped[0]:] if entry[0] in hostemu.MUTATING],'no mutating call after the gate refused'
        assert f.sealed(receipt) and receipt['status']==('REFUSED' if not new(host) and receipt['mutating_calls']['succeeded']==0 else m.PARTIAL_STATUS)
        for path in new(host):
            if unit_named(host,path):assert bytes(host.tree.get(path).content) in (RENDERED,f.TIMER)
        states|={row['state'] for row in receipt['ledger']}
    assert {'TEMPORARY_ONLY','LINKED_TEMPORARY_PRESENT','INSTALLED_DURABLE','NOT_ATTEMPTED'}<=states

def test_readback_inside_the_run_catches_bytes_changed_after_the_link():
    host,docs=fresh()
    def tamper(host,detail):host.tree.get(SERVICE).content=bytearray(RENDERED.replace(b'--cap-drop ALL',b'--cap-add ALL'))
    after(host,'unlink',2,'fsync',1,tamper);receipt=docs.run(host)
    assert (receipt['status'],receipt['code'],receipt['readback']['status'])==(m.PARTIAL_STATUS,'READBACK_HASH_MISMATCH','UNAVAILABLE')
    assert receipt['ledger'][0]['sha256_observed']!=receipt['ledger'][0]['sha256_signed']
    # the same bytes, owner and mode under the final name, but another file than the one this run created
    host,docs=fresh()
    def replace(host,detail):
        directory=host.tree.get(UNITS);old=directory.children.pop('c3po-massive.service')
        host.tree.add(SERVICE,kind='file',mode=0o644,content=RENDERED);assert host.tree.get(SERVICE).ino!=old.ino
    after(host,'unlink',2,'fsync',1,replace);receipt=docs.run(host)
    assert (receipt['status'],receipt['code'])==(m.PARTIAL_STATUS,'READBACK_HASH_MISMATCH') and receipt['ledger'][0]['sha256_observed']==receipt['ledger'][0]['sha256_signed']


def test_readback_inside_the_run_catches_owner_group_mode_or_a_second_name_changed_after_the_installation():
    """The checks at creation are made on the temporary; the readback makes them again on the final name, after
    everything else: a change in between is a partial, never the success outcome."""
    def mode(node):node.mode=0o664
    def owner(node):node.uid=1000
    def group(node):node.gid=4
    def second_name(node):node.nlink+=1
    for change in (mode,owner,group,second_name):
        host,docs=fresh();after(host,'unlink',2,'fsync',1,lambda host,detail,change=change:change(host.tree.get(SERVICE)));receipt=docs.run(host)
        assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,'PARTIAL_REQUIRES_RECONCILIATION','READBACK_HASH_MISMATCH'),change.__name__
        assert receipt['readback']=={'status':'UNAVAILABLE','code':'READBACK_HASH_MISMATCH'} and [row['state'] for row in receipt['ledger']]==['INSTALLED_DURABLE']*2
        assert receipt['ledger'][0]['sha256_observed']==receipt['ledger'][0]['sha256_signed'],'the bytes are the signed ones; it is the metadata that changed'


# ---------------------------------------------------------------- crash, rerun label, signed continuation
def continued(host,docs):
    fields=f.install_fields(k,host);directory=host.tree.get(UNITS)
    for unit in fields['units']:
        node=directory.children.get(unit['destination_name'])
        if node is not None:unit['expect']={'device':node.dev,'inode':node.ino,'links':node.nlink}
    fields['acknowledged_leftovers']=[{'name':name,'device':node.dev,'inode':node.ino} for name,node in sorted(directory.children.items())
                                      if re.fullmatch(m.LEFTOVER,name)]
    return f.Docs(k,fields,now=f.NOW+__import__('datetime').timedelta(seconds=1))      # another GO: another temporary name

def test_process_death_at_every_call_leaves_a_state_that_lstat_tells_apart_and_a_rerun_labels():
    reference,docs=fresh();assert docs.run(reference)['status']==m.COMPLETE_STATUS;total=reference.calls
    first=next(index for index,entry in enumerate(reference.log) if entry[0]=='create')+1;labels=set()
    for index in range(first,total+1):
        host,docs=fresh()
        def hook(host,name,detail,calls,index=index):
            if calls==index:raise hostemu.Death()
        host.hook=hook
        with pytest.raises(hostemu.Death):docs.perform(host)
        host.hook=None;left=new(host);directory=host.tree.get(UNITS)
        for path in left:
            node=host.tree.get(path)
            if unit_named(host,path):assert bytes(node.content) in (RENDERED,f.TIMER) and node.mode==0o644,'no half-written unit under a loadable name'
            else:assert re.fullmatch(m.LEFTOVER,os.path.basename(path)),'anything else left is a dot-prefixed temporary'
        again=f.Docs(k,f.install_fields(k,host),now=f.NOW+__import__('datetime').timedelta(seconds=2));before=host.tree.snapshot();label=again.run(host)
        finals=[path for path in left if unit_named(host,path)];temps=[path for path in left if not unit_named(host,path)]
        if not left:
            assert label['outcome']=='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED';labels.add('NOTHING');continue
        expected='ALL_UNITS_PRESENT' if len(finals)==2 and not temps else 'PRIOR_PARTIAL_REQUIRES_RECONCILIATION'
        assert (label['status'],label['code'])==('REFUSED',expected) and host.tree.snapshot()==before,'a rerun never continues by itself and never overwrites'
        labels.add((len(finals),len(temps),label['code']))
        if len(finals)==2 and not temps:continue
        finish=continued(host,docs).run(host)
        if len(finals)==2:assert finish['code']=='NOTHING_TO_CREATE';continue
        assert finish['outcome']=='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED',finish['code']
        assert bytes(host.tree.get(SERVICE).content)==RENDERED and bytes(host.tree.get(TIMER).content)==f.TIMER
        assert sorted(path for path in new(host) if not unit_named(host,path))==sorted(temps),'an acknowledged leftover is verified and never touched'
    assert 'NOTHING' in labels and (0,1,'PRIOR_PARTIAL_REQUIRES_RECONCILIATION') in labels and (1,1,'PRIOR_PARTIAL_REQUIRES_RECONCILIATION') in labels
    assert (1,0,'PRIOR_PARTIAL_REQUIRES_RECONCILIATION') in labels and (2,0,'ALL_UNITS_PRESENT') in labels
    assert (2,1,'PRIOR_PARTIAL_REQUIRES_RECONCILIATION') in labels,'both names and a temporary: never called a complete set'

def test_continuation_verifies_signed_present_units_against_the_render_and_the_signed_identity():
    host,docs=fresh();at_event(host,'create',2,raising(hostemu.Death))
    with pytest.raises(hostemu.Death):docs.perform(host)
    host.hook=None;host.log.clear();docs=continued(host,docs);before=host.tree.get(SERVICE).stat();receipt=docs.run(host)
    assert receipt['outcome']=='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED' and [row['state'] for row in receipt['ledger']]==['PRESENT_VERIFIED_NOT_TOUCHED','INSTALLED_DURABLE']
    assert host.tree.get(SERVICE).stat()==before and [entry[2] for entry in host.log if entry[0]=='link']==[TIMER]
    for change in (lambda unit:unit['expect'].update(inode=unit['expect']['inode']+1),lambda unit:unit['expect'].update(device=unit['expect']['device']+1),
                   lambda unit:unit['expect'].update(links=2)):
        host,docs=fresh();at_event(host,'create',2,raising(hostemu.Death))
        with pytest.raises(hostemu.Death):docs.perform(host)
        host.hook=None;docs=continued(host,docs);change(docs.plan['units'][0]);docs.chain()
        assert units_table(refused(host,docs,'EXPECTATION_MISMATCH'))['SUPERVISOR_SERVICE']['state']=='PRESENT_IDENTITY_MISMATCH'
    host,docs=fresh();at_event(host,'create',2,raising(hostemu.Death))
    with pytest.raises(hostemu.Death):docs.perform(host)
    host.hook=None;docs=continued(host,docs);host.tree.get(SERVICE).content=bytearray(RENDERED.replace(b'bridge',b'brIdge'))
    refused(host,docs,'EXPECTATION_MISMATCH')
    host,docs=fresh();at_event(host,'create',2,raising(hostemu.Death))
    with pytest.raises(hostemu.Death):docs.perform(host)
    host.hook=None;docs=continued(host,docs);docs.plan['acknowledged_leftovers']=[{'name':'.hostops-0123456789abcdef-1.partial','device':1,'inode':2}];docs.chain()
    refused(host,docs,'EXPECTATION_MISMATCH')
    # a leftover is acknowledged by name AND identity: the right name on another inode or device is not the one that was signed
    for field in ('inode','device'):
        host,docs=fresh();at_event(host,'link',2,raising(hostemu.Death))
        with pytest.raises(hostemu.Death):docs.perform(host)
        host.hook=None;docs=continued(host,docs);assert len(docs.plan['acknowledged_leftovers'])==1
        docs.plan['acknowledged_leftovers'][0][field]+=1;docs.chain();receipt=refused(host,docs,'PRIOR_PARTIAL_REQUIRES_RECONCILIATION')
        assert receipt['precheck']['conflicts']['leftovers_acknowledged']==[] and len(receipt['precheck']['conflicts']['leftovers_not_acknowledged'])==1
    host,docs=fresh();at_event(host,'link',2,raising(hostemu.Death))
    with pytest.raises(hostemu.Death):docs.perform(host)
    host.hook=None;docs=continued(host,docs);receipt=docs.run(host)
    assert receipt['outcome']=='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED' and len(receipt['precheck']['conflicts']['leftovers_acknowledged'])==1


# ---------------------------------------------------------------- receipt size
def test_receipt_at_the_caps_needs_no_reduction(monkeypatch):
    body=b'#'+b'y'*2900+b'\n';units=[f.unit('U%d'%index,'c3po-'+('u%d'%index)*14+'.service','VERBATIM_V1',body+bytes([48+index]),{},body+bytes([48+index])) for index in range(8)]
    host=f.world(k)
    for directory in LOOKUP:
        host.tree.add(directory)
        for index in range(8):host.tree.add(directory+'/target-%d.target.wants'%index)
    docs=f.Docs(k,f.install_fields(k,host,units=units,volume=None));receipt=docs.run(host)
    assert receipt['outcome']=='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED' and receipt['size_reductions']==[] and len(f.line(receipt))<30000
    host,docs=fresh();monkeypatch.setattr(m,'RECEIPT_LIMIT',5200);receipt=docs.run(host)
    assert receipt['status']==m.PARTIAL_STATUS and receipt['outcome']=='RECEIPT_REDUCED_STATE_REQUIRES_READBACK' and receipt['size_reductions'] and f.sealed(receipt)
    assert [row['state'] for row in receipt['ledger']]==['INSTALLED_DURABLE']*2
