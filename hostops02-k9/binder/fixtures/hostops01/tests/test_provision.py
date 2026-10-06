"""OP_PROVISION on the emulated host: exclusive directory creation, precheck labels, crash and rerun, the tag.
Synthetic local tests only. No SSH, host, real credential, docker binary or operational GO."""
from datetime import timedelta
import errno
import json
import os
import stat

import pytest

import family as f
import hostemu

k=f.load('provision');m=k.m
BASE=set(hostemu.world().tree.paths())
ORDER=['/etc/c3po-bar','/etc/c3po-bar/manifests','/etc/c3po-bar/docker-cli','/var/lib/c3po-bar','/var/lib/c3po-bar/supervisor',
       hostemu.DATA+'/'+f.LEAF,'/etc/c3po-reader','/etc/c3po-reader/docker-cli','/var/lib/c3po-reader',
       hostemu.DATA+'/c3po-capacity',hostemu.DATA+'/c3po-capacity/config',hostemu.DATA+'/c3po-capacity/documents',
       hostemu.DATA+'/c3po-capacity/payload',hostemu.DATA+'/c3po-capacity/go','/var/lib/c3po-reader/capacity-receipts']
REFERENCE='c3po/backend:'+f.TAG

def fresh(**options):
    host=f.world(k);return host,f.Docs(k,f.provision_fields(k,host,**options))
def new(host):return sorted(path for path in host.tree.paths() if path not in BASE)
def tags(host):return {tag:item['Id'] for item in host.docker.images for tag in item['RepoTags']}
def refusal(action):
    with pytest.raises(m.Refused) as caught:action()
    return str(caught.value)
def mkdirs(host):return [entry[1] for entry in host.log if entry[0]=='mkdir']
def at_event(host,name,occurrence,action):
    """Run action(host) when the n-th call of that name is about to happen (before it takes effect)."""
    seen=[0]
    def hook(host,event,detail,calls):
        if event==name:
            seen[0]+=1
            if seen[0]==occurrence:action(host,detail)
    host.hook=hook
def raising(kind,*arguments):
    def action(host,detail):raise kind(*arguments)
    return action


# ---------------------------------------------------------------- what the GO shows
def test_effects_shown_in_the_go_are_exactly_this_literal():
    """Written out by hand: a member that disappears from effects_of, or changes meaning, fails here."""
    host,docs=fresh();etc=host.tree.get('/etc').ino
    chains={'ETC':hostemu.rows(host,'/etc'),'VAR_LIB':hostemu.rows(host,'/var/lib'),'DATA_VOLUME':hostemu.rows(host,'/mnt/day-d-data')}
    keys=['SUP_CONFIG','SUP_MANIFESTS','SUP_DOCKER_CLI','SUP_STATE_PARENT','SUP_STATE','SUP_JOURNAL','RDR_CONFIG','RDR_DOCKER_CLI','RDR_STATE',
          'CAP_ROOT','CAP_CONFIG','CAP_DOCUMENTS','CAP_PAYLOAD','CAP_GO','CAP_RECEIPTS']
    expected={'operation':'GO_WRITE_SUPERVISOR_READER_PROVISION_01','groups':['SUPERVISOR','JOURNAL_LEAF','READER','CAPACITY','RETENTION_TAG'],
              'data_volume_path':'/mnt/day-d-data','journal_leaf':'r2d2-v2-massive-epoch03','existing_journal_leaves':[],
              'journal':{'placement':'B','path':'/mnt/day-d-data/r2d2-v2-massive-epoch03','filesystem_named_by_chain':'DATA_VOLUME','filesystem_device':811,
                         'mount_point_by_device_change':'/mnt/day-d-data','data_volume_touched_for_the_journal':True},
              'capacity':{'root_path':'/mnt/day-d-data/c3po-capacity','receipt_directory_path':'/var/lib/c3po-reader/capacity-receipts','receipts_inside_capacity_root':False},
              'creates':[{'key':key,'path':path,'mode_octal':'0700','expect':'ABSENT'} for key,path in zip(keys,ORDER)],'directories_to_create':15,
              'direct_parents':{'DATA_VOLUME':{'path':'/mnt/day-d-data','device':811,'inode':4005,'uid':1000,'gid':1000,'mode':0o755},
                                'ETC':{'path':'/etc','device':801,'inode':etc,'uid':0,'gid':0,'mode':0o755},
                                'VAR_LIB':{'path':'/var/lib','device':801,'inode':4003,'uid':0,'gid':0,'mode':0o755}},
              'chains_sha256':f.sha(f.canonical(chains)),
              'data_volume_root':{'world_writable_without_sticky':False,'device_differs_from_parent':True},
              'retention_tag':{'reference':'c3po/backend:massive-supervisor-epoch03','image_id':hostemu.BACKEND,'expect':'ABSENT'},
              'evidence_boot_id_sha256':f.BOOT_SHA,'files_created':0,'pre_existing_objects_modified':False,'daemon_reload':False,'activation':False}
    assert f.canonical(m.effects_of(docs.plan))==f.canonical(expected)==f.canonical(docs.go['effects'])
    # the continuation form and the subsets are visible too
    docs.plan['creates'][0]['expect']={'device':801,'inode':9,'entries':0};docs.plan['retention_tag']['expect']='PRESENT';effects=m.effects_of(docs.plan)
    assert effects['creates'][0]['expect']=='PRESENT' and effects['directories_to_create']==14 and effects['retention_tag']['expect']=='PRESENT'
    host,docs=fresh(groups=['SUPERVISOR']);effects=docs.go['effects']
    assert (effects['retention_tag'],effects['capacity'],effects['journal_leaf'],effects['data_volume_path'],effects['journal'])==(None,None,None,None,None)
    assert effects['data_volume_root']=={'world_writable_without_sticky':None,'device_differs_from_parent':None} and sorted(effects['direct_parents'])==['ETC','VAR_LIB']
    # the signed list of journal leaves that already exist (the capacity root is kept away from each) is what the GO shows, literally
    host,docs=fresh(existing=['r2d2-v2-massive-epoch02','r2d2-v2-massive-epoch01'])
    assert docs.go['effects']['existing_journal_leaves']==m.effects_of(docs.plan)['existing_journal_leaves']==['r2d2-v2-massive-epoch02','r2d2-v2-massive-epoch01']
    docs.plan['existing_journal_leaves']=['r2d2-v2-massive-epoch02'];docs.chain(effects=False)
    assert refusal(docs.authenticate)=='EFFECTS_BINDING','a request whose list of existing leaves changes cannot keep its GO'

def test_data_volume_root_facts_are_literal_in_the_effects_and_a_root_any_user_can_write_is_refused():
    """The observed owner and mode of the data volume root are accepted as signed, with one floor in code: a directory
    writable by others without the sticky bit lets any local user rename the root-owned leaf this run creates."""
    for mode,code in ((0o777,'CHAIN_ROW_WORLD_WRITABLE'),(0o757,'CHAIN_ROW_WORLD_WRITABLE'),(0o773,'CHAIN_ROW_WORLD_WRITABLE'),(0o702,'CHAIN_ROW_WORLD_WRITABLE')):
        host,docs=fresh();host.tree.get(hostemu.DATA).mode=mode;docs.plan['chains']['DATA_VOLUME'][-1]['mode']=mode;docs.chain()
        assert refusal(docs.authenticate)==code;result=docs.run(host);assert (result['status'],result['code'])==('REFUSED',code) and host.log==[]
    for mode in (0o755,0o775,0o1777,0o1775,0o700):
        host=f.world(k);host.tree.get(hostemu.DATA).mode=mode;docs=f.Docs(k,f.provision_fields(k,host))
        assert docs.go['effects']['data_volume_root']=={'world_writable_without_sticky':False,'device_differs_from_parent':True}
        assert docs.run(host)['outcome']=='PROVISIONED_ALL_VERIFIED_DURABLE',mode
    # the two facts are computed from the signed rows, whatever the validation later says about them
    rows=hostemu.rows(f.world(k),hostemu.DATA)
    for mode,writable in ((0o777,True),(0o757,True),(0o1777,False),(0o775,False),(0o755,False)):
        rows[-1]['mode']=mode;assert m.volume_root_facts({'DATA_VOLUME':rows},hostemu.DATA)=={'world_writable_without_sticky':writable,'device_differs_from_parent':True}
    # a data volume that is not a mount point (its device is its parent's) is not refused; the signers see it literally
    host=f.world(k);host.tree.get(hostemu.DATA).dev=801
    for child in host.tree.get(hostemu.DATA).children.values():child.dev=801
    docs=f.Docs(k,f.provision_fields(k,host));assert docs.go['effects']['data_volume_root']['device_differs_from_parent'] is False
    assert docs.run(host)['outcome']=='PROVISIONED_ALL_VERIFIED_DURABLE'
    # the same floor for every signed row inside the data volume (a capacity parent below it)
    capacity={'root_path':hostemu.DATA+'/shared/c3po-capacity','receipt_directory_path':'/var/lib/c3po-reader/capacity-receipts'}
    host=f.world(k);host.tree.add(hostemu.DATA+'/shared',uid=1000,gid=1000,mode=0o777,dev=811)
    docs=f.Docs(k,f.provision_fields(k,host,capacity=capacity));assert refusal(docs.authenticate)=='CHAIN_ROW_WORLD_WRITABLE'
    host.tree.get(hostemu.DATA+'/shared').mode=0o1777;docs=f.Docs(k,f.provision_fields(k,host,capacity=capacity))
    assert docs.run(host)['outcome']=='PROVISIONED_ALL_VERIFIED_DURABLE'


# ---------------------------------------------------------------- the journal placement
ORDER_A=ORDER[:5]+['/var/lib/c3po-bar/journal']+ORDER[6:]
def test_placement_a_creates_the_journal_root_next_to_the_state_root_and_never_touches_the_data_volume():
    """Supervisor README, epoch R2D2-V2-SHADOW-2026-10-05: /var/lib/c3po-bar/journal on the root filesystem."""
    host,docs=fresh(groups=['SUPERVISOR','JOURNAL_LEAF','RETENTION_TAG'],placement='A');volume=host.tree.get(hostemu.DATA);before=volume.stat()
    assert docs.plan['data_volume_path'] is None and sorted(docs.plan['chains'])==['ETC','VAR_LIB'] and docs.plan['creates'][5]=={
        'key':'SUP_JOURNAL','path':'/var/lib/c3po-bar/journal','mode':0o700,'parent':{'entry':'SUP_STATE_PARENT'},'expect':'ABSENT'}
    assert docs.go['effects']['journal']=={'placement':'A','path':'/var/lib/c3po-bar/journal','filesystem_named_by_chain':'VAR_LIB','filesystem_device':801,
                                           'mount_point_by_device_change':'/','data_volume_touched_for_the_journal':False}
    # the receipt of 2026-10-02 read /var/lib on the device of "/", in an earlier boot; whatever the boot of the write shows, the
    # signers see it: when /var/lib is a mount of its own, the effects name it
    other=f.world(k);other.tree.get('/var/lib').dev=899
    assert f.Docs(k,f.provision_fields(k,other,groups=['SUPERVISOR','JOURNAL_LEAF'],placement='A')).go['effects']['journal']['mount_point_by_device_change']=='/var/lib'
    assert m.mount_point_of([{'path':'/','device':1},{'path':'/a','device':2},{'path':'/a/b','device':2},{'path':'/a/b/c','device':3},{'path':'/a/b/c/d','device':3}])=='/a/b/c'
    assert m.mount_point_of([{'path':'/','device':1}])=='/' and m.mount_point_of([{'path':'/','device':1},{'path':'/a','device':1}])=='/'
    assert docs.go['effects']['data_volume_root']=={'world_writable_without_sticky':None,'device_differs_from_parent':None}
    receipt=docs.run(host);assert receipt['outcome']=='PROVISIONED_ALL_VERIFIED_DURABLE' and mkdirs(host)==ORDER_A[:6]
    node=host.tree.get('/var/lib/c3po-bar/journal');row=receipt['ledger'][5]
    assert (node.kind,node.uid,node.gid,node.mode,node.dev,node.children)==('dir',0,0,0o700,801,{}) and node.synced
    assert row['observed']=={'type':'dir','uid':0,'gid':0,'mode_octal':'0700','device':801,'inode':node.ino,'entries':0}
    assert sorted(host.tree.get('/var/lib/c3po-bar').children)==['journal','supervisor']
    # nothing of the data volume was walked, opened, listed or created
    assert not [entry for entry in host.log if type(entry[1]) is str and entry[1].startswith('/mnt')] and 'DATA_VOLUME' not in receipt['chains']
    assert volume.stat()==before and sorted(volume.children)==['lost+found','provider=synthetic']
    # with the whole table: the capacity tree still hangs from the data volume (another authority, W4), the journal does not
    host,docs=fresh(placement='A');receipt=docs.run(host)
    assert receipt['outcome']=='PROVISIONED_ALL_VERIFIED_DURABLE' and mkdirs(host)==ORDER_A and host.tree.get(hostemu.DATA+'/'+f.LEAF) is None
    assert docs.go['effects']['journal']['filesystem_device']==801 and docs.go['effects']['direct_parents']['DATA_VOLUME']['uid']==1000

def test_placement_a_for_a_later_epoch_pins_the_existing_private_parent_by_its_own_chain():
    """A later epoch creates only a new journal root (and tag): /var/lib/c3po-bar exists, root:root 0700, and is signed row by row."""
    host,docs=fresh(groups=['SUPERVISOR','JOURNAL_LEAF'],placement='A');assert docs.run(host)['outcome']=='PROVISIONED_ALL_VERIFIED_DURABLE'
    host.log.clear();docs=f.Docs(k,f.provision_fields(k,host,groups=['JOURNAL_LEAF','RETENTION_TAG'],placement='A',leaf='journal-epoch04'))
    assert sorted(docs.plan['chains'])==['SUP_STATE_PARENT'] and [row['path'] for row in docs.plan['chains']['SUP_STATE_PARENT']]==['/','/var','/var/lib','/var/lib/c3po-bar']
    assert docs.plan['creates']==[{'key':'SUP_JOURNAL','path':'/var/lib/c3po-bar/journal-epoch04','mode':0o700,'parent':{'chain':'SUP_STATE_PARENT'},'expect':'ABSENT'}]
    assert docs.go['effects']['journal']['filesystem_named_by_chain']=='SUP_STATE_PARENT' and docs.go['effects']['direct_parents']['SUP_STATE_PARENT']['mode']==0o700
    receipt=docs.run(host);assert receipt['outcome']=='PROVISIONED_ALL_VERIFIED_DURABLE' and mkdirs(host)==['/var/lib/c3po-bar/journal-epoch04']
    assert sorted(host.tree.get('/var/lib/c3po-bar').children)==['journal','journal-epoch04','supervisor']
    # the private parent is an existing object: it must be exactly the signed row, and root's
    host,docs=fresh(groups=['SUPERVISOR','JOURNAL_LEAF'],placement='A');docs.run(host)
    docs=f.Docs(k,f.provision_fields(k,host,groups=['JOURNAL_LEAF'],placement='A',leaf='journal-epoch04'));host.tree.get('/var/lib/c3po-bar').mode=0o750
    refused(host,docs,'PARENT_IDENTITY_MISMATCH')
    docs.plan['chains']['SUP_STATE_PARENT'][-1]['mode']=0o770;docs.chain();assert refusal(docs.authenticate)=='CHAIN_ROW_UNSAFE'
    docs.plan['chains']['SUP_STATE_PARENT'][-1].update(mode=0o700,uid=1000);docs.chain();assert refusal(docs.authenticate)=='CHAIN_ROW_UNSAFE'

def test_placement_is_signed_and_its_parameters_follow_it():
    for placement in (None,'C','a',['A'],1,True):assert invalid(lambda plan:plan.update(journal_placement=placement))=='PLACEMENT_UNKNOWN'
    assert invalid(lambda plan:plan.update(journal_placement='A'),groups=['SUPERVISOR'])=='PLACEMENT_UNKNOWN'          # no journal group: no placement
    assert invalid(lambda plan:plan.update(journal_placement='A'))=='LAYOUT_MISMATCH'                                 # rows of B signed under A
    assert invalid(lambda plan:plan.update(journal_placement='B'),groups=['SUPERVISOR','JOURNAL_LEAF'],placement='A')=='PATH_INVALID'   # B needs the data volume
    for leaf in ('supervisor','.hidden','a/b','','x'*65,None,'r2d2-v2-release-x'):
        assert invalid(lambda plan:plan.update(journal_leaf=leaf),groups=['SUPERVISOR','JOURNAL_LEAF'],placement='A')=='LEAF_INVALID',leaf
    # under placement A a data volume path is signed only when the capacity tree needs it
    assert invalid(lambda plan:plan.update(data_volume_path=hostemu.DATA),groups=['SUPERVISOR','JOURNAL_LEAF'],placement='A')=='PATH_INVALID'
    def other_path(plan):plan['creates'][5]['path']=hostemu.DATA+'/journal'
    assert invalid(other_path,placement='A')=='LAYOUT_MISMATCH','the journal root is created at the path of the signed placement and nowhere else'
    def other_parent(plan):plan['creates'][5]['parent']={'chain':'VAR_LIB'}
    assert invalid(other_parent,placement='A')=='LAYOUT_MISMATCH'
    assert m.SCOPE['layout']['journal_placements'].keys()=={'A','B'} and [row['path'] for row in m.SCOPE['layout']['journal_row_under_placement_a']]==['/var/lib/c3po-bar/<journal leaf>']*2

def test_placement_a_process_death_at_every_call_and_signed_continuation():
    groups=['SUPERVISOR','JOURNAL_LEAF'];order=ORDER_A[:6]
    reference,docs=fresh(groups=groups,placement='A');assert docs.run(reference)['status']==m.COMPLETE_STATUS;total=reference.calls
    first=next(index for index,entry in enumerate(reference.log) if entry[0]=='mkdir')+1;seen=set()
    for index in range(first,total+1):
        host,docs=fresh(groups=groups,placement='A')
        def hook(host,name,detail,calls,index=index):
            if calls==index:raise hostemu.Death()
        host.hook=hook
        with pytest.raises(hostemu.Death):docs.perform(host)
        host.hook=None;present=new(host);count=len(present);seen.add(count);assert present==sorted(order[:count])
        label=f.Docs(k,f.provision_fields(k,host,groups=groups,placement='A')).run(host)
        if count==0:continue
        assert (label['status'],label['code'])==('REFUSED','ALL_DESTINATIONS_PRESENT' if count==6 else 'PRIOR_PROVISION_PREFIX_PRESENT')
        if count==6:continue
        fields=f.provision_fields(k,host,groups=groups,placement='A')
        for row in fields['creates']:
            node=host.tree.get(row['path'])
            if node is not None:row['expect']={'device':node.dev,'inode':node.ino,'entries':len(node.children)}
        finish=f.Docs(k,fields).run(host);assert finish['outcome']=='PROVISIONED_ALL_VERIFIED_DURABLE' and new(host)==sorted(order)
    assert seen==set(range(7))

def test_a_directory_of_the_layout_is_never_a_mount_point():
    """A directory found at a destination conforms only on the device of the directory it is in."""
    for placement,parent in (('A','/var/lib/c3po-bar'),('B',hostemu.DATA)):
        groups=['SUPERVISOR','JOURNAL_LEAF'];host,docs=fresh(groups=groups,placement=placement);docs.run(host)
        journal=docs.plan['creates'][5]['path'];host.tree.get(journal).dev=899             # another filesystem mounted on the journal root
        fields=f.provision_fields(k,host,groups=groups,placement=placement)
        for row in fields['creates']:
            node=host.tree.get(row['path']);row['expect']={'device':node.dev,'inode':node.ino,'entries':len(node.children)}
        fields['groups']=groups+['RETENTION_TAG'];fields['retention_tag']={'repository':'c3po/backend','tag':f.TAG,'image_id':hostemu.BACKEND,'expect':'ABSENT'}
        row=table(refused(host,f.Docs(k,fields),'EXPECTATION_MISMATCH'))['SUP_JOURNAL'];assert (row['state'],row['conforms'],row['device'])==('PRESENT_IDENTITY_MISMATCH',False,899)
        label=f.Docs(k,f.provision_fields(k,host,groups=groups,placement=placement)).run(host);assert label['code']=='DESTINATION_PRESENT_UNEXPECTED'


# ---------------------------------------------------------------- the complete run
def test_complete_run_creates_exactly_the_table_in_order_root_owned_0700_durable_and_tags_last():
    host,docs=fresh();plan,real=docs.authenticate()
    def gate():
        host.log.append(('gate',));return real()
    receipt=docs.perform(host,gate=gate)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.COMPLETE_STATUS,'PROVISIONED_ALL_VERIFIED_DURABLE',None) and f.sealed(receipt)
    assert new(host)==sorted(ORDER) and mkdirs(host)==ORDER
    for path in ORDER:
        node=host.tree.get(path);assert (node.kind,node.uid,node.gid,node.mode,node.children)==('dir',0,0,0o700,node.children) and node.synced
    assert all(entry[2]==0o700 for entry in host.log if entry[0]=='mkdir')
    log=host.log;mutating=[index for index,entry in enumerate(log) if entry[0] in hostemu.MUTATING]
    assert len(mutating)==15 and all(log[index-1]==('gate',) for index in mutating),'the gate is the call immediately before each creation'
    assert log.index(('umask',0o077))<mutating[0] and host.mask==0o077
    for index,path in zip(mutating,ORDER):
        parent=os.path.dirname(path);after=[entry for entry in log[index+1:mutating[mutating.index(index)+1] if index!=mutating[-1] else len(log)]]
        syncs=[entry[1] for entry in after if entry[0]=='fsync'];assert syncs[:2]==[path,parent],'the new directory, then its parent'
    assert not [entry for entry in log if entry[0] in ('create','write','link','unlink')]
    runs=[entry[1][1:] for entry in log if entry[0]=='run']
    assert [argv[:2] for argv in runs]==[['image','inspect'],['image','ls'],['image','ls'],['image','tag'],['image','inspect']]
    assert runs[3]==['image','tag',hostemu.BACKEND,REFERENCE] and log.index(('run',['/usr/bin/docker']+runs[3],None))>mutating[-1]
    assert tags(host)[REFERENCE]==hostemu.BACKEND and all(entry[2] is None for entry in log if entry[0]=='run')
    ledger=receipt['ledger'];assert [row['path'] for row in ledger]==ORDER and all(row['state']=='CREATED_DURABLE' for row in ledger)
    for row in ledger:
        node=host.tree.get(row['path'])
        assert row['observed']=={'type':'dir','uid':0,'gid':0,'mode_octal':'0700','device':node.dev,'inode':node.ino,'entries':0}
        assert row['fsync_directory'] is True and row['fsync_parent'] is True and row['errno'] is None
    assert receipt['retention_tag']['state']=='CREATED_VERIFIED' and receipt['retention_tag']['readback_id_equal'] is True
    assert receipt['mutating_calls']=={'issued':16,'succeeded':16,'failed_nothing_changed':0,'uncertain':0}
    assert receipt['objects_left_by_this_run']==16 and receipt['files_created']==0 and receipt['pre_existing_objects_modified'] is False
    assert receipt['readback']['status']=='COMPLETE' and receipt['readback']['parents_unchanged'] is True
    # the data volume root is recorded as observed, not changed, and not required to be root's
    volume=receipt['chains']['DATA_VOLUME'][-1];assert (volume['uid'],volume['gid'],volume['mode'])==(1000,1000,0o755)
    node=host.tree.get(hostemu.DATA);assert (node.uid,node.gid,node.mode)==(1000,1000,0o755)
    assert '"size"' not in json.dumps(receipt) and len(f.line(receipt))<16384

def test_pre_existing_objects_are_never_modified_and_nothing_secret_is_read():
    host,docs=fresh();before={path:host.tree.get(path).stat() for path in BASE}
    host.tree.add('/etc/c3po-other/token',kind='file',mode=0o600,content=b'never-emit-token-canary')
    receipt=docs.run(host);assert receipt['status']==m.COMPLETE_STATUS
    for path,old in before.items():
        now=host.tree.get(path).stat()
        assert (now.st_mode,now.st_uid,now.st_gid,now.st_ino,now.st_dev,now.st_size)==(old.st_mode,old.st_uid,old.st_gid,old.st_ino,old.st_dev,old.st_size)
    assert [entry[1] for entry in host.log if entry[0]=='read']==[m.BOOT_ID_PATH]
    text=json.dumps(receipt);assert 'canary' not in text and 'never-emit' not in text

@pytest.mark.parametrize('groups,expected,tagged',[
    (['SUPERVISOR'],ORDER[:5],False),(['READER'],ORDER[6:9],False),(['JOURNAL_LEAF'],[ORDER[5]],False),
    (['JOURNAL_LEAF','RETENTION_TAG'],[ORDER[5]],True),(['SUPERVISOR','JOURNAL_LEAF','RETENTION_TAG'],ORDER[:6],True),
    (['READER','CAPACITY'],ORDER[6:],False),(['RETENTION_TAG'],[],True)])
def test_group_subsets_create_only_their_own_rows(groups,expected,tagged):
    host,docs=fresh(groups=groups);receipt=docs.run(host)
    assert receipt['outcome']=='PROVISIONED_ALL_VERIFIED_DURABLE' and mkdirs(host)==expected and new(host)==sorted(expected)
    assert (REFERENCE in tags(host))==tagged and sorted(docs.plan['chains'])==sorted({row['parent']['chain'] for row in docs.plan['creates'] if 'chain' in row['parent']})

def test_capacity_receipts_inside_the_capacity_root_is_shown_to_the_signers():
    capacity={'root_path':'/srv/c3po-capacity','receipt_directory_path':'/srv/c3po-capacity/receipts'}
    host=f.world(k);host.tree.add('/srv');docs=f.Docs(k,f.provision_fields(k,host,groups=['CAPACITY'],capacity=capacity))
    assert docs.go['effects']['capacity']['receipts_inside_capacity_root'] is True and 'CAPACITY_PARENT' in docs.plan['chains']
    assert docs.run(host)['outcome']=='PROVISIONED_ALL_VERIFIED_DURABLE' and '/srv/c3po-capacity/receipts' in new(host)
    host,docs=fresh();assert docs.go['effects']['capacity']['receipts_inside_capacity_root'] is False


# ---------------------------------------------------------------- request validation, before any host access
def invalid(change,**options):
    host,docs=fresh(**options);change(docs.plan);docs.chain()
    code=refusal(docs.authenticate);result=docs.run(host)
    assert (result['status'],result['code'])==('REFUSED',code) and host.log==[];return code

@pytest.mark.parametrize('groups',[[],'SUPERVISOR',None,['OTHER'],['READER','SUPERVISOR'],['SUPERVISOR','SUPERVISOR'],[['SUPERVISOR']],[1]])
def test_groups_are_an_ordered_subset(groups):
    assert invalid(lambda plan:plan.update(groups=groups))=='GROUPS_INVALID'

@pytest.mark.parametrize('leaf',['.hidden','r2d2-v2-release-epoch03.json','r2d2-v2-release-x','a/b','','x'*65,'lost+found','-leaf',None,7,'..','with space'])
def test_journal_leaf_grammar_and_denied_names(leaf):
    assert invalid(lambda plan:plan.update(journal_leaf=leaf))=='LEAF_INVALID'
def test_existing_leaves_are_signed_and_never_reused_or_covered():
    assert invalid(lambda plan:plan.update(existing_journal_leaves=[f.LEAF]))=='LEAF_INVALID'
    assert invalid(lambda plan:plan.update(existing_journal_leaves=['a','a']))=='LEAF_INVALID'
    assert invalid(lambda plan:plan.update(existing_journal_leaves=['.x']))=='LEAF_INVALID'
    for value in (None,'r2d2-v2-massive-epoch02',{}):assert invalid(lambda plan:plan.update(existing_journal_leaves=value))=='LEAF_INVALID'
    def inside_old(plan):
        plan['existing_journal_leaves']=['r2d2-v2-massive-epoch02']
        plan['capacity']={'root_path':hostemu.DATA+'/r2d2-v2-massive-epoch02/capacity','receipt_directory_path':'/var/lib/c3po-reader/capacity-receipts'}
    assert invalid(inside_old)=='CAPACITY_JOURNAL_OVERLAP'

@pytest.mark.parametrize('volume,code',[('/etc/data','PATH_FORBIDDEN_ZONE'),('/var/lib/docker/volumes/x','PATH_FORBIDDEN_ZONE'),('/usr/share/x','PATH_FORBIDDEN_ZONE'),
    ('/proc/1/root','PATH_FORBIDDEN_ZONE'),('/var/lib/c3po-bar','PATH_FORBIDDEN_ZONE'),('/var/lib/c3po-reader/x','PATH_FORBIDDEN_ZONE'),('/run/x','PATH_FORBIDDEN_ZONE'),
    ('/dev/shm','PATH_FORBIDDEN_ZONE'),('/boot','PATH_FORBIDDEN_ZONE'),('/sys/fs','PATH_FORBIDDEN_ZONE'),('/','PATH_FORBIDDEN_ZONE'),('/mnt/.hidden','PATH_FORBIDDEN_ZONE'),
    ('/mnt/../etc','PATH_INVALID'),('mnt/day-d-data','PATH_INVALID'),('/mnt//x','PATH_INVALID'),('/mnt/day d','PATH_INVALID'),(None,'PATH_INVALID'),(7,'PATH_INVALID'),
    ('/mnt/day-d-data/','PATH_INVALID'),
    # never a fixed directory of this family or a directory above one: it would lift the code floor from that chain
    ('/var','PATH_FORBIDDEN_ZONE'),('/var/lib','PATH_FORBIDDEN_ZONE'),('/etc','PATH_FORBIDDEN_ZONE'),('/etc/systemd','PATH_FORBIDDEN_ZONE')])
def test_data_volume_path_grammar_and_forbidden_zones(volume,code):
    assert invalid(lambda plan:plan.update(data_volume_path=volume))==code

@pytest.mark.parametrize('volume,leaf',[('/var/lib','c3po-reader'),('/var','x'),('/var/lib','journal'),('/var','run'),('/var/lib','docker')])
def test_a_data_volume_above_the_fixed_layout_is_refused_with_rows_that_would_otherwise_be_accepted_as_signed(volume,leaf):
    """The request of the review: /var/lib owned 1000:1000 0777 named as the data volume, the leaf landing on a fixed name."""
    host=f.world(k);node=host.tree.get(volume);node.uid=node.gid=1000;node.mode=0o1777
    fields=f.provision_fields(k,host,groups=['SUPERVISOR','JOURNAL_LEAF'],leaf=leaf);fields['data_volume_path']=volume
    table=m.layout(fields['groups'],volume,leaf,None,'B');fields['creates']=[dict(row,expect='ABSENT') for row in table]
    fields['chains']={name:hostemu.rows(host,path) for name,path in m.chain_paths(table,volume,None).items()}
    docs=f.Docs(k,fields);assert refusal(docs.authenticate)=='PATH_FORBIDDEN_ZONE'
    result=docs.run(host);assert (result['status'],result['code'])==('REFUSED','PATH_FORBIDDEN_ZONE') and host.log==[]

def test_the_composed_journal_path_is_checked_and_not_only_its_two_halves(monkeypatch):
    """Two rules close the same request; each is shown alone. With the rule on the fixed paths taken away, the path
    <data volume>/<leaf> is still refused when it is a forbidden zone, and accepted when it is not."""
    assert m.FIXED_PATHS==['/etc','/etc/systemd/system','/var/lib','/etc/c3po-bar','/var/lib/c3po-bar','/etc/c3po-reader','/var/lib/c3po-reader']
    assert m.SCOPE['fixed_paths_never_at_or_below_a_parameter']==m.FIXED_PATHS
    monkeypatch.setattr(m,'FIXED_PATHS',[])
    for leaf,code in (('c3po-reader','PATH_FORBIDDEN_ZONE'),('c3po-bar','PATH_FORBIDDEN_ZONE'),('docker','PATH_FORBIDDEN_ZONE'),('journal',None)):
        try:m.validate_parameters(['JOURNAL_LEAF'],'/var/lib',leaf,[],None,'B');found=None
        except m.Refused as error:found=str(error)
        assert found==code,leaf
    for root in ('/var','/var/lib','/etc'):assert m.open_path(root) is (root!='/etc')

@pytest.mark.parametrize('capacity,code',[
    ({'root_path':'/etc/c3po-bar/capacity','receipt_directory_path':'/var/lib/c3po-reader/r'},'PATH_FORBIDDEN_ZONE'),
    ({'root_path':'/etc/systemd/system/capacity','receipt_directory_path':'/var/lib/c3po-reader/r'},'PATH_FORBIDDEN_ZONE'),
    ({'root_path':'/var/lib/c3po-reader/capacity','receipt_directory_path':'/var/lib/c3po-reader/r'},'PATH_FORBIDDEN_ZONE'),
    ({'root_path':'/capacity','receipt_directory_path':'/var/lib/c3po-reader/r'},'PATH_FORBIDDEN_ZONE'),
    ({'root_path':hostemu.DATA+'/r2d2-v2-release-x','receipt_directory_path':'/var/lib/c3po-reader/r'},'PATH_FORBIDDEN_ZONE'),
    ({'root_path':hostemu.DATA+'/'+f.LEAF+'/capacity','receipt_directory_path':'/var/lib/c3po-reader/r'},'CAPACITY_JOURNAL_OVERLAP'),
    ({'root_path':hostemu.DATA+'/'+f.LEAF,'receipt_directory_path':'/var/lib/c3po-reader/r'},'CAPACITY_JOURNAL_OVERLAP'),
    ({'root_path':hostemu.DATA,'receipt_directory_path':'/var/lib/c3po-reader/r'},'CAPACITY_JOURNAL_OVERLAP'),
    ({'root_path':'/mnt','receipt_directory_path':'/var/lib/c3po-reader/r'},'PATH_FORBIDDEN_ZONE'),
    ({'root_path':hostemu.DATA+'/capacity','receipt_directory_path':'/var/lib/other/r'},'CAPACITY_RECEIPTS_PARENT'),
    ({'root_path':hostemu.DATA+'/capacity','receipt_directory_path':hostemu.DATA+'/capacity/config'},'CAPACITY_RECEIPTS_PARENT'),
    ({'root_path':hostemu.DATA+'/capacity','receipt_directory_path':hostemu.DATA+'/capacity/a/b'},'CAPACITY_RECEIPTS_PARENT'),
    ({'root_path':hostemu.DATA+'/capacity','receipt_directory_path':'/var/lib/c3po-reader/.r'},'CAPACITY_RECEIPTS_PARENT'),
    ({'root_path':hostemu.DATA+'/capacity','receipt_directory_path':'/var/lib/c3po-reader'},'CAPACITY_RECEIPTS_PARENT'),
    ({'root_path':None,'receipt_directory_path':None},'PATH_INVALID'),({'root_path':hostemu.DATA+'/capacity'},'PATH_INVALID'),(None,'PATH_INVALID'),
    ({'root_path':hostemu.DATA+'/cap acity','receipt_directory_path':'/var/lib/c3po-reader/r'},'PATH_INVALID')])
def test_capacity_paths_forbidden_zones_journal_overlap_and_receipt_parent(capacity,code):
    assert invalid(lambda plan:plan.update(capacity=capacity))==code
def test_capacity_receipts_under_the_reader_state_need_the_reader_group():
    host=f.world(k);fields=f.provision_fields(k,host,groups=['READER','CAPACITY'])
    fields['groups']=['CAPACITY'];fields['creates']=[row for row in fields['creates'] if row['key'].startswith('CAP_')]
    docs=f.Docs(k,fields);assert refusal(docs.authenticate)=='CAPACITY_RECEIPTS_PARENT'

def test_parameters_of_groups_not_selected_must_be_null():
    for change,code in ((lambda plan:plan.update(journal_leaf=f.LEAF),'LEAF_INVALID'),(lambda plan:plan.update(capacity=f.CAPACITY),'PATH_INVALID'),
                        (lambda plan:plan.update(data_volume_path=hostemu.DATA),'PATH_INVALID'),
                        (lambda plan:plan.update(retention_tag={'repository':'c3po/backend','tag':f.TAG,'image_id':hostemu.BACKEND,'expect':'ABSENT'}),'TAG_INVALID')):
        assert invalid(change,groups=['SUPERVISOR'])==code

def test_creates_must_equal_the_code_table_instantiated_for_the_signed_parameters():
    def swap(plan):plan['creates'][1],plan['creates'][2]=plan['creates'][2],plan['creates'][1]
    for change in (lambda plan:plan['creates'][0].update(path='/etc/c3po-baz'),lambda plan:plan['creates'][0].update(mode=0o755),
                   lambda plan:plan['creates'][0].update(mode='0700'),lambda plan:plan['creates'][1].update(parent={'chain':'ETC'}),
                   lambda plan:plan['creates'][0].update(key='OTHER'),lambda plan:plan['creates'].pop(),swap,
                   lambda plan:plan['creates'].append({'key':'X','path':'/opt/c3po-bar','mode':448,'parent':{'chain':'ETC'},'expect':'ABSENT'}),
                   lambda plan:plan['creates'][0].update(extra=1),lambda plan:plan['creates'][0].pop('expect'),lambda plan:plan.update(creates=None),
                   lambda plan:plan['creates'].__setitem__(0,'x')):
        assert invalid(change)=='LAYOUT_MISMATCH'
    for expect in ('PRESENT',None,{},{'device':1,'inode':2},{'device':1,'inode':0,'entries':0},{'device':-1,'inode':2,'entries':0},
                   {'device':1,'inode':2,'entries':True},{'device':1,'inode':2,'entries':5000},{'device':'1','inode':2,'entries':0}):
        assert invalid(lambda plan:plan['creates'][0].update(expect=expect))=='EXPECT_INVALID'
    # a present child cannot be signed under an absent parent
    assert invalid(lambda plan:plan['creates'][1].update(expect={'device':1,'inode':2,'entries':0}))=='EXPECT_INVALID'
    def all_present(plan):
        for row in plan['creates']:row['expect']={'device':1,'inode':2,'entries':0}
        plan['retention_tag']['expect']='PRESENT'
    assert invalid(all_present)=='NOTHING_TO_CREATE'

def test_chains_are_signed_rows_of_observed_values_with_a_floor_outside_the_data_volume():
    for change,code in (
            (lambda plan:plan['chains'].pop('ETC'),'CHAIN_MISSING'),(lambda plan:plan['chains'].update(EXTRA=plan['chains']['ETC']),'CHAIN_MISSING'),
            (lambda plan:plan.update(chains=None),'CHAIN_MISSING'),(lambda plan:plan['chains'].update(ETC=None),'CHAIN_ROW_INVALID'),
            (lambda plan:plan['chains']['ETC'].pop(),'CHAIN_ROW_INVALID'),(lambda plan:plan['chains']['ETC'][1].update(path='/usr'),'CHAIN_ROW_INVALID'),
            (lambda plan:plan['chains']['ETC'][1].update(inode=0),'CHAIN_ROW_INVALID'),(lambda plan:plan['chains']['ETC'][1].update(device=-1),'CHAIN_ROW_INVALID'),
            (lambda plan:plan['chains']['ETC'][1].update(uid=None),'CHAIN_ROW_INVALID'),(lambda plan:plan['chains']['ETC'][1].update(gid=True),'CHAIN_ROW_INVALID'),
            (lambda plan:plan['chains']['ETC'][1].update(mode=0o10000),'CHAIN_ROW_INVALID'),(lambda plan:plan['chains']['ETC'][1].update(mode='0755'),'CHAIN_ROW_INVALID'),
            (lambda plan:plan['chains']['ETC'][1].update(extra=1),'CHAIN_ROW_INVALID'),(lambda plan:plan['chains']['ETC'][0].pop('gid'),'CHAIN_ROW_INVALID'),
            # outside the data volume: root-owned and not writable by group or other, in code
            (lambda plan:plan['chains']['ETC'][1].update(uid=1000),'CHAIN_ROW_UNSAFE'),(lambda plan:plan['chains']['ETC'][1].update(mode=0o775),'CHAIN_ROW_UNSAFE'),
            (lambda plan:plan['chains']['VAR_LIB'][1].update(mode=0o757),'CHAIN_ROW_UNSAFE'),(lambda plan:plan['chains']['ETC'][0].update(uid=1),'CHAIN_ROW_UNSAFE'),
            (lambda plan:plan['chains']['DATA_VOLUME'][1].update(uid=1000),'CHAIN_ROW_UNSAFE'),          # /mnt is not inside the data volume
            (lambda plan:plan['chains']['DATA_VOLUME'][1].update(mode=0o1777),'CHAIN_ROW_UNSAFE'),       # sticky does not help outside it
            # the directory that receives a new entry is never setgid
            (lambda plan:plan['chains']['DATA_VOLUME'][-1].update(mode=0o2755),'PARENT_SETGID'),(lambda plan:plan['chains']['ETC'][-1].update(mode=0o2755),'PARENT_SETGID'),
            (lambda plan:plan['chains']['VAR_LIB'][-1].update(mode=0o2755),'PARENT_SETGID')):
        assert invalid(change)==code
    # at the data volume root the observed owner and mode are accepted as signed (and still compared on the host)
    host,docs=fresh();host.tree.get(hostemu.DATA).mode=0o775;docs.plan['chains']['DATA_VOLUME'][-1]['mode']=0o775;docs.chain()
    assert docs.run(host)['outcome']=='PROVISIONED_ALL_VERIFIED_DURABLE'

@pytest.mark.parametrize('tag,code',[({'repository':'c3po/backend','tag':'production','image_id':hostemu.BACKEND,'expect':'ABSENT'},'TAG_INVALID'),
    ({'repository':'c3po/backend','tag':'rollback','image_id':hostemu.BACKEND,'expect':'ABSENT'},'TAG_INVALID'),
    ({'repository':'c3po/backend','tag':'massive-supervisor-Epoch','image_id':hostemu.BACKEND,'expect':'ABSENT'},'TAG_INVALID'),
    ({'repository':'c3po/web','tag':f.TAG,'image_id':hostemu.BACKEND,'expect':'ABSENT'},'TAG_INVALID'),
    ({'repository':'c3po/backend','tag':None,'image_id':hostemu.BACKEND,'expect':'ABSENT'},'TAG_INVALID'),(None,'TAG_INVALID'),
    ({'repository':'c3po/backend','tag':f.TAG,'image_id':hostemu.BACKEND},'TAG_INVALID'),
    ({'repository':'c3po/backend','tag':f.TAG,'image_id':'c3po/backend:production','expect':'ABSENT'},'IMAGE_ID'),
    ({'repository':'c3po/backend','tag':f.TAG,'image_id':None,'expect':'ABSENT'},'IMAGE_ID'),
    ({'repository':'c3po/backend','tag':f.TAG,'image_id':hostemu.BACKEND,'expect':None},'EXPECT_INVALID'),
    ({'repository':'c3po/backend','tag':f.TAG,'image_id':hostemu.BACKEND,'expect':['ABSENT']},'EXPECT_INVALID')])
def test_retention_tag_grammar(tag,code):
    assert invalid(lambda plan:plan.update(retention_tag=tag))==code

def test_boot_of_the_evidence_is_signed_and_compared_before_anything_else():
    for value in (None,'0'*64,'x'):assert invalid(lambda plan:plan.update(evidence_boot_id_sha256=value))=='EVIDENCE_BOOT_UNBOUND'
    host,docs=fresh();host.tree.get(m.BOOT_ID_PATH).content=bytearray(b'11111111-2222-3333-4444-555555555555\n')
    receipt=docs.run(host)
    assert (receipt['status'],receipt['code'])==('REFUSED','EVIDENCE_FROM_EARLIER_BOOT') and new(host)==[] and receipt['precheck']==[]
    assert not [entry for entry in host.log if entry[0] in ('lstat','run')],'refused before any chain is walked'
    host,docs=fresh();host.tree.get(m.BOOT_ID_PATH).content=bytearray(b'not a boot id\n')
    assert docs.run(host)['code']=='BOOT_ID_INVALID' and new(host)==[]


# ---------------------------------------------------------------- precheck: everything before the first creation
def refused(host,docs,code):
    before=host.tree.snapshot();images=json.dumps(host.docker.images);earlier=len(host.mutating());receipt=docs.run(host)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('REFUSED','REFUSED_NOTHING_CREATED',code),receipt['code']
    assert host.tree.snapshot()==before and json.dumps(host.docker.images)==images and len(host.mutating())==earlier and f.sealed(receipt)
    assert receipt['mutating_calls']['issued']==0 and receipt['ledger']==[] and receipt['objects_left_by_this_run']==0
    return receipt

@pytest.mark.parametrize('chain,index',[('ETC',0),('ETC',1),('VAR_LIB',1),('VAR_LIB',2),('DATA_VOLUME',1),('DATA_VOLUME',2)])
@pytest.mark.parametrize('field,value',[('device',7),('inode',99999),('uid',0),('gid',0),('mode',0o700)])
def test_every_chain_component_must_equal_its_signed_row_on_all_five_values(chain,index,field,value):
    host,docs=fresh();row=docs.plan['chains'][chain][index];node=host.tree.get(row['path'])
    # change the HOST after the row was signed, so the request stays valid and the mismatch is on the host
    attribute={'device':'dev','inode':'ino','uid':'uid','gid':'gid','mode':'mode'}[field]
    setattr(node,attribute,getattr(node,attribute)+1 if field!='mode' else 0o711)
    receipt=refused(host,docs,'PARENT_IDENTITY_MISMATCH')
    seen=[rows[index] for rows in receipt['chains'].values() if len(rows)>index and rows[index]['path']==row['path']]
    assert seen and seen[-1][field]!=row[field],'the refusal carries the observed row'

def test_parent_missing_symlinked_or_not_a_directory():
    host,docs=fresh();host.tree.remove('/var/lib');host.tree.add('/var/lib',kind='symlink',mode=0o777)
    assert refused(host,docs,'PARENT_SYMLINK_COMPONENT')['chains']['VAR_LIB'][-1]['type']=='symlink'
    host,docs=fresh();host.tree.remove('/var/lib');host.tree.add('/var/lib',kind='file');refused(host,docs,'PARENT_NOT_DIRECTORY')
    host,docs=fresh();host.tree.remove('/mnt/day-d-data');refused(host,docs,'PARENT_MISSING')

def test_a_component_swapped_between_its_lstat_and_its_open_is_refused_whichever_of_the_two_saw_the_signed_directory():
    """The walk classifies a component by lstat and then opens it. The descriptor held must be the object the lstat saw:
    the signed row alone would accept the second case below, where the object that was classified is not the one held."""
    # the lstat sees the signed directory; another one stands at the name when it is opened
    host,docs=fresh();real=host.lstat;seen=[0]
    def swapped_after(name,dir_fd):
        info=real(name,dir_fd)
        if host.path_of(dir_fd)=='/var' and name=='lib' and not seen[0]:
            seen[0]=1;var=host.tree.get('/var');var.children['lib.moved']=var.children.pop('lib');host.tree.add('/var/lib',mode=0o755)
        return info
    host.lstat=swapped_after;receipt=docs.run(host)
    assert seen==[1] and (receipt['status'],receipt['outcome'],receipt['code'])==('REFUSED','REFUSED_NOTHING_CREATED','PARENT_CHANGED_DURING_WALK')
    assert host.mutating()==[] and receipt['mutating_calls']['issued']==0 and f.sealed(receipt)
    # the lstat sees some other directory; the signed one is back at the name when it is opened
    host,docs=fresh();real=host.lstat;seen=[0]
    def decoy_before(name,dir_fd):
        if host.path_of(dir_fd)=='/var' and name=='lib' and not seen[0]:
            seen[0]=1;var=host.tree.get('/var');signed=var.children.pop('lib');host.tree.add('/var/lib',mode=0o755)
            try:return real(name,dir_fd)
            finally:var.children['lib']=signed
        return real(name,dir_fd)
    host.lstat=decoy_before;receipt=docs.run(host)
    assert seen==[1] and (receipt['status'],receipt['outcome'],receipt['code'])==('REFUSED','REFUSED_NOTHING_CREATED','PARENT_CHANGED_DURING_WALK')
    assert host.mutating()==[] and new(host)==[] and receipt['mutating_calls']['issued']==0 and f.sealed(receipt)

def table(receipt):return {row['key']:row for row in receipt['precheck']}

@pytest.mark.parametrize('path,key',[(ORDER[0],'SUP_CONFIG'),(ORDER[3],'SUP_STATE_PARENT'),(ORDER[5],'SUP_JOURNAL'),(ORDER[6],'RDR_CONFIG'),(ORDER[8],'RDR_STATE'),(ORDER[9],'CAP_ROOT')])
@pytest.mark.parametrize('kind',['file','symlink','fifo','dir_0755','dir_other_owner','dir_other_group','dir_with_foreign_entry'])
def test_any_object_at_a_destination_that_is_not_the_layout_is_refused_and_named(path,key,kind):
    host,docs=fresh();device=host.tree.get(os.path.dirname(path)).dev
    if kind in ('file','symlink','fifo'):host.tree.add(path,kind=kind,mode=0o600,dev=device,content=b'foreign')
    elif kind=='dir_0755':host.tree.add(path,mode=0o755,dev=device)
    elif kind=='dir_other_owner':host.tree.add(path,mode=0o700,uid=1000,gid=1000,dev=device)
    elif kind=='dir_other_group':host.tree.add(path,mode=0o700,uid=0,gid=4,dev=device)
    else:
        host.tree.add(path,mode=0o700,dev=device);host.tree.add(path+'/token',kind='file',mode=0o600,dev=device,content=b'never-emit-token-canary')
    receipt=refused(host,docs,'DESTINATION_PRESENT_UNEXPECTED');row=table(receipt)[key]
    assert (row['observed'],row['state'])==('PRESENT','PRESENT_UNEXPECTED') and row['type']==('dir' if kind.startswith('dir') else 'symlink' if kind=='symlink' else 'file' if kind=='file' else 'other')
    if kind=='dir_with_foreign_entry':assert (row['entries'],row['foreign_entries'])==(1,1)
    assert '"size"' not in json.dumps(receipt) and 'canary' not in json.dumps(receipt) and not [e for e in host.log if e[0]=='read' and 'token' in e[1]]
    others=[other for name,other in table(receipt).items() if name!=key];assert all(other['state']=='OK_ABSENT' for other in others)

def test_children_below_a_directory_that_does_not_exist_are_absent_by_implication():
    host,docs=fresh();host.tree.add(ORDER[3],kind='file')
    rows=table(refused(host,docs,'DESTINATION_PRESENT_UNEXPECTED'))
    assert rows['SUP_MANIFESTS']['observed']=='ABSENT_PARENT_ABSENT' and rows['SUP_CONFIG']['observed']=='ABSENT' and rows['SUP_STATE']['observed']=='ABSENT_PARENT_ABSENT'

def conforming(host,paths):
    for path in paths:host.tree.add(path,mode=0o700,dev=host.tree.get(os.path.dirname(path)).dev)
def test_rerun_labels_what_exists_and_never_calls_it_an_installation():
    for count in range(1,15):
        host,docs=fresh();conforming(host,ORDER[:count]);receipt=refused(host,docs,'PRIOR_PROVISION_PREFIX_PRESENT')
        states=[row['state'] for row in receipt['precheck']];assert states==['PRESENT_NOT_SIGNED']*count+['OK_ABSENT']*(15-count)
    host,docs=fresh();conforming(host,ORDER);receipt=refused(host,docs,'ALL_DESTINATIONS_PRESENT');assert receipt['retention_tag']['tag_present'] is False
    for paths in ([ORDER[3]],[ORDER[0],ORDER[2]],[ORDER[5]],ORDER[6:9],[ORDER[0],ORDER[1],ORDER[3]]):
        host,docs=fresh();conforming(host,paths);receipt=refused(host,docs,'PRESENT_SET_NOT_A_PREFIX')
        assert sorted(row['path'] for row in receipt['precheck'] if row['observed']=='PRESENT')==sorted(paths)
    for word in ('INSTALLED','PROVISIONED','COMPLETE'):assert word not in json.dumps(receipt['precheck'])+str(receipt['code'])

def test_precheck_looks_at_every_destination_before_reporting():
    host,docs=fresh();host.tree.add(ORDER[0],kind='file');conforming(host,[ORDER[8]]);host.docker.images[1]['RepoTags'].append(REFERENCE)
    receipt=refused(host,docs,'DESTINATION_PRESENT_UNEXPECTED');rows=table(receipt)
    assert rows['SUP_CONFIG']['state']=='PRESENT_UNEXPECTED' and rows['RDR_STATE']['state']=='PRESENT_NOT_SIGNED'
    assert receipt['retention_tag']['code']=='RETENTION_TAG_EXISTS' and receipt['retention_tag']['tag_points_to_signed_image'] is False
    assert len(receipt['precheck'])==15


# ---------------------------------------------------------------- continuation, signed
def continued(host):
    """A request as a binder would write it after a read-only receipt: what exists is signed as present."""
    fields=f.provision_fields(k,host)
    for row in fields['creates']:
        node=host.tree.get(row['path'])
        if node is not None:row['expect']={'device':node.dev,'inode':node.ino,'entries':len(node.children)}
    if REFERENCE in tags(host):fields['retention_tag']['expect']='PRESENT'
    return f.Docs(k,fields)

def shape_of(host):return sorted((path,host.tree.get(path).kind,host.tree.get(path).uid,host.tree.get(path).gid,host.tree.get(path).mode) for path in new(host))

def test_process_death_at_every_call_leaves_a_prefix_that_the_next_run_labels_and_a_signed_continuation_finishes():
    reference,docs=fresh();assert docs.run(reference)['status']==m.COMPLETE_STATUS;total=reference.calls
    first=next(index for index,entry in enumerate(reference.log) if entry[0]=='mkdir')+1
    seen=set()
    for index in range(first,total+1):
        host,docs=fresh()
        def hook(host,name,detail,calls,index=index):
            if calls==index:raise hostemu.Death()
        host.hook=hook
        with pytest.raises(hostemu.Death):docs.perform(host)
        host.hook=None;present=new(host);count=len(present);tagged=REFERENCE in tags(host)
        assert present==sorted(ORDER[:count]),'a crash leaves a prefix of the table, in table order'
        assert all((host.tree.get(path).uid,host.tree.get(path).gid,host.tree.get(path).mode)==(0,0,0o700) for path in present)
        seen.add((count,tagged));again=f.Docs(k,f.provision_fields(k,host));before=host.tree.snapshot();label=again.run(host)
        if count==0:
            assert label['outcome']=='PROVISIONED_ALL_VERIFIED_DURABLE';continue
        expected='ALL_DESTINATIONS_PRESENT' if count==15 else 'PRIOR_PROVISION_PREFIX_PRESENT'
        assert (label['status'],label['code'])==('REFUSED',expected) and host.tree.snapshot()==before,'a rerun never continues by itself'
        assert label['retention_tag']['tag_present'] is tagged
        if count==15 and tagged:continue
        finish=continued(host).run(host)
        assert finish['outcome']=='PROVISIONED_ALL_VERIFIED_DURABLE' and shape_of(host)==shape_of(reference) and tags(host)==tags(reference)
        assert [row['state'] for row in finish['ledger']]==['PRESENT_VERIFIED_NOT_TOUCHED']*count+['CREATED_DURABLE']*(15-count)
        assert sorted(set(mkdirs(host)))==sorted(ORDER)
    assert {count for count,_ in seen}==set(range(16)) and (15,True) in seen and (15,False) in seen

def test_continuation_verifies_what_it_signs_as_present_and_touches_none_of_it():
    host,docs=fresh(groups=['SUPERVISOR']);docs.run(host);host.log.clear()
    host.tree.add('/etc/c3po-bar/token',kind='file',mode=0o600,content=b'never-emit-token-canary')     # the owner's delivery, in between
    docs=continued(host);before={path:host.tree.get(path).stat() for path in ORDER[:5]};receipt=docs.run(host)
    assert receipt['outcome']=='PROVISIONED_ALL_VERIFIED_DURABLE' and mkdirs(host)==ORDER[5:]
    assert all(host.tree.get(path).stat()==old for path,old in before.items()) and 'canary' not in json.dumps(receipt)
    for change in (lambda row:row['expect'].update(inode=row['expect']['inode']+1),lambda row:row['expect'].update(device=row['expect']['device']+1),
                   lambda row:row['expect'].update(entries=row['expect']['entries']+1)):
        host,docs=fresh(groups=['SUPERVISOR']);docs.run(host);docs=continued(host);change(docs.plan['creates'][0]);docs.chain()
        receipt=refused(host,docs,'EXPECTATION_MISMATCH');assert table(receipt)['SUP_CONFIG']['state']=='PRESENT_IDENTITY_MISMATCH'
    host,docs=fresh(groups=['SUPERVISOR']);docs.run(host);docs=continued(host);host.tree.get(ORDER[0]).mode=0o750
    assert table(refused(host,docs,'EXPECTATION_MISMATCH'))['SUP_CONFIG']['state']=='PRESENT_IDENTITY_MISMATCH'
    host,docs=fresh(groups=['SUPERVISOR']);docs.run(host);docs=continued(host);host.tree.remove(ORDER[4])
    assert table(refused(host,docs,'EXPECTATION_MISMATCH'))['SUP_STATE']['state']=='EXPECTED_PRESENT_ABSENT'
    # signed as present, right identity and entry count, root-owned 0700, but another group: not what this code creates
    for attribute,value in (('gid',4),('uid',1000)):
        host,docs=fresh(groups=['SUPERVISOR']);docs.run(host);docs=continued(host);setattr(host.tree.get(ORDER[3]),attribute,value)
        row=table(refused(host,docs,'EXPECTATION_MISMATCH'))['SUP_STATE_PARENT'];assert (row['state'],row['conforms'],row[attribute])==('PRESENT_IDENTITY_MISMATCH',False,value)


# ---------------------------------------------------------------- failures at and after a creation
def test_object_appearing_between_precheck_and_creation_is_left_intact():
    for position in (1,2,7,15):
        host,docs=fresh();path=ORDER[position-1]
        at_event(host,'mkdir',position,lambda host,detail:host.tree.add(detail[0],kind='file',mode=0o644,dev=host.tree.get(os.path.dirname(detail[0])).dev,content=b'foreign bytes'))
        receipt=docs.run(host);node=host.tree.get(path)
        assert (node.kind,bytes(node.content),node.mode)==('file',b'foreign bytes',0o644)
        row=receipt['ledger'][position-1];assert (row['state'],row['code'],row['errno'])==('NOT_CREATED','DESTINATION_APPEARED_AFTER_PRECHECK',errno.EEXIST)
        assert [entry['state'] for entry in receipt['ledger']]==['CREATED_DURABLE']*(position-1)+['NOT_CREATED']+['NOT_ATTEMPTED']*(15-position)
        assert receipt['status']==('REFUSED' if position==1 else m.PARTIAL_STATUS) and receipt['code']=='DESTINATION_APPEARED_AFTER_PRECHECK'
        assert receipt['outcome']==('REFUSED_NOTHING_CREATED' if position==1 else 'PARTIAL_REQUIRES_RECONCILIATION')
        assert len(mkdirs(host))==position and REFERENCE not in tags(host) and receipt['retention_tag']['state']=='NOT_ATTEMPTED'

@pytest.mark.parametrize('number,code',[(errno.EROFS,'FILESYSTEM_READ_ONLY'),(errno.ENOSPC,'FILESYSTEM_FULL'),(errno.EDQUOT,'FILESYSTEM_FULL'),
                                        (errno.EACCES,'FILESYSTEM_ACCESS_DENIED'),(errno.EPERM,'FILESYSTEM_ACCESS_DENIED'),(errno.EIO,'FILESYSTEM_ERROR'),
                                        (errno.ENAMETOOLONG,'FILESYSTEM_ERROR')])
@pytest.mark.parametrize('position',[1,6])
def test_failed_mkdir_has_its_own_code_and_is_a_refusal_only_when_nothing_was_created(number,code,position):
    host,docs=fresh();at_event(host,'mkdir',position,raising(OSError,number,'injected'));receipt=docs.run(host)
    row=receipt['ledger'][position-1];assert (row['state'],row['code'],row['errno'])==('NOT_CREATED',code,number)
    assert receipt['status']==('REFUSED' if position==1 else m.PARTIAL_STATUS) and receipt['code']==code and new(host)==sorted(ORDER[:position-1])
    assert receipt['mutating_calls']=={'issued':position,'succeeded':position-1,'failed_nothing_changed':1,'uncertain':0}

def after_mkdir(host,position,kind,occurrence,action):
    """Arm at the n-th mkdir; then act on the following call of the given kind (the calls that prove the new directory)."""
    state={'armed':False,'count':0,'mkdirs':0}
    def hook(host,name,detail,calls):
        if name=='mkdir':
            state['mkdirs']+=1;state['armed']=state['mkdirs']==position;state['count']=0;return
        if state['armed'] and name==kind:
            state['count']+=1
            if state['count']==occurrence:state['armed']=False;action(host,detail)
    host.hook=hook

@pytest.mark.parametrize('position',[1,6,15])
@pytest.mark.parametrize('kind,occurrence,number,state,code',[
    ('open',1,errno.ENOENT,'CREATED_UNVERIFIED','CREATED_OPEN_FAILED'),('open',1,errno.ELOOP,'CREATED_UNVERIFIED','CREATED_OPEN_FAILED'),
    ('open',1,errno.EMFILE,'CREATED_UNVERIFIED','CREATED_OPEN_FAILED'),('open',1,errno.ENOTDIR,'CREATED_UNVERIFIED','CREATED_OPEN_FAILED'),
    ('fstat',1,errno.EIO,'CREATED_UNVERIFIED','CREATED_STAT_FAILED'),('fstat',2,errno.EIO,'CREATED_UNVERIFIED','CREATED_STAT_FAILED'),
    ('lstat',1,errno.EIO,'CREATED_UNVERIFIED','CREATED_STAT_FAILED'),('names',1,errno.EIO,'CREATED_UNVERIFIED','CREATED_LIST_FAILED'),
    ('fsync',1,errno.EIO,'CREATED_NOT_DURABLE','FSYNC_FAILED'),('fsync',2,errno.EIO,'CREATED_NOT_DURABLE','FSYNC_FAILED')])
def test_a_failure_after_a_successful_mkdir_is_never_reported_as_not_created_or_as_a_refusal(position,kind,occurrence,number,state,code):
    host,docs=fresh();after_mkdir(host,position,kind,occurrence,raising(OSError,number,'injected'));receipt=docs.run(host)
    row=receipt['ledger'][position-1]
    assert (row['state'],row['code'])==(state,code) and row['errno']==number and host.tree.get(ORDER[position-1]) is not None
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,'PARTIAL_REQUIRES_RECONCILIATION',code)
    assert receipt['objects_left_by_this_run']==position and receipt['mutating_calls']['succeeded']==position
    assert [entry['state'] for entry in receipt['ledger'][position:]]==['NOT_ATTEMPTED']*(15-position) and len(mkdirs(host))==position
    assert new(host)==sorted(ORDER[:position]),'nothing is removed and nothing later is created'

def test_created_directory_that_does_not_match_is_left_in_place_and_labelled():
    host,docs=fresh();host.grpid=True;receipt=docs.run(host)             # a grpid mount: the child takes the parent's group
    row=receipt['ledger'][5];assert (row['state'],row['code'])==('CREATED_METADATA_MISMATCH','CREATED_METADATA_MISMATCH') and row['observed']['gid']==1000
    assert receipt['status']==m.PARTIAL_STATUS and host.tree.get(ORDER[5]).gid==1000 and len(mkdirs(host))==6
    host,docs=fresh();host.mask=0o022
    def keep(mask):host.event('umask',mask);return 0o022
    host.umask=keep;receipt=docs.run(host)                               # a umask that did not take: mode is verified, never corrected
    assert receipt['ledger'][0]['state']=='CREATED_DURABLE'              # mkdir(0700) under 022 is still 0700
    host,docs=fresh();after_mkdir(host,1,'open',1,lambda host,detail:setattr(host.tree.get(ORDER[0]),'mode',0o755));receipt=docs.run(host)
    assert receipt['ledger'][0]['state']=='CREATED_METADATA_MISMATCH' and host.tree.get(ORDER[0]).mode==0o755 and receipt['status']==m.PARTIAL_STATUS
    host,docs=fresh();host.created_device=899;receipt=docs.run(host)   # the new directory is not on its parent's device
    row=receipt['ledger'][0];assert (row['state'],row['code'],row['observed']['device'])==('CREATED_METADATA_MISMATCH','CREATED_METADATA_MISMATCH',899)
    assert receipt['status']==m.PARTIAL_STATUS and len(mkdirs(host))==1 and host.tree.get(ORDER[0]) is not None
    host,docs=fresh();after_mkdir(host,6,'open',1,lambda host,detail:host.tree.add(ORDER[5]+'/planted',kind='file',dev=811));receipt=docs.run(host)
    assert (receipt['ledger'][5]['state'],receipt['code'])==('CREATED_NOT_EMPTY','CREATED_NOT_EMPTY') and host.tree.get(ORDER[5]+'/planted') is not None
    def swap(host,detail):                                               # the owner of the volume root renames something else over the name
        host.tree.remove(ORDER[5]);host.tree.add(ORDER[5],mode=0o700,dev=811)
    host,docs=fresh();after_mkdir(host,6,'fstat',1,swap);receipt=docs.run(host)
    assert (receipt['ledger'][5]['state'],receipt['ledger'][5]['code'])==('CREATED_UNVERIFIED','CREATED_NAME_REPLACED') and receipt['status']==m.PARTIAL_STATUS

def test_parent_replaced_between_two_creations_stops_the_run():
    def replace(host,detail):
        old=host.tree.root.children.pop('etc');host.tree.root.children['etc.old']=old;host.tree.add('/etc',mode=0o755)
    host,docs=fresh();at_event(host,'mkdir',2,None);seen=[0]
    def hook(host,name,detail,calls):
        if name=='fsync' and detail[0]=='/etc' and not seen[0]:seen[0]=1;replace(host,detail)
    host.hook=hook;receipt=docs.run(host)
    assert receipt['ledger'][0]['state']=='CREATED_DURABLE' and (receipt['ledger'][1]['state'],receipt['ledger'][1]['code'])==('NOT_ATTEMPTED','PARENT_REPLACED')
    assert (receipt['status'],receipt['code'])==(m.PARTIAL_STATUS,'PARENT_REPLACED') and len(mkdirs(host))==1 and host.tree.get('/etc/c3po-bar') is None
    def before_first(host,name,detail,calls):
        if name=='umask':host.tree.get('/var/lib').mode=0o700
    host,docs=fresh();host.hook=before_first;receipt=docs.run(host)
    assert (receipt['status'],receipt['code'])==('REFUSED','PARENT_IDENTITY_MISMATCH') and host.mutating()==[] and new(host)==[]

def test_created_directory_replaced_before_its_children_are_created_stops_the_run():
    host,docs=fresh(groups=['SUPERVISOR']);seen=[0]
    def hook(host,name,detail,calls):
        if name=='fsync' and detail[0]=='/etc' and not seen[0]:
            seen[0]=1;etc=host.tree.get('/etc');etc.children['c3po-bar.moved']=etc.children.pop('c3po-bar');host.tree.add('/etc/c3po-bar',mode=0o700)
    host.hook=hook;receipt=docs.run(host)
    assert receipt['ledger'][0]['state']=='CREATED_DURABLE' and (receipt['ledger'][1]['state'],receipt['ledger'][1]['code'])==('NOT_ATTEMPTED','PARENT_REPLACED')
    assert receipt['status']==m.PARTIAL_STATUS and host.tree.get('/etc/c3po-bar').children=={} and host.tree.get('/etc/c3po-bar.moved').children=={}

def test_pinned_parent_changed_after_the_last_creation_is_caught_by_the_readback():
    host,docs=fresh(groups=['JOURNAL_LEAF'])
    def hook(host,name,detail,calls):
        if name=='fsync' and detail[0]==hostemu.DATA:host.tree.get(hostemu.DATA).mode=0o775
    host.hook=hook;receipt=docs.run(host)
    assert receipt['ledger'][0]['state']=='CREATED_DURABLE' and (receipt['status'],receipt['code'])==(m.PARTIAL_STATUS,'PARENT_REPLACED')
    assert receipt['readback']['parents_unchanged'] is None and receipt['readback']['status']=='UNAVAILABLE'

@pytest.mark.parametrize('reason,code',[('expire','GO_EXPIRED'),('reverse','CLOCK_REVERSED')])
def test_window_expiry_or_clock_reversal_between_creations_issues_no_further_mutating_call(reason,code):
    reference,docs=fresh();plan,real=docs.authenticate();counter=[0]
    def counting():
        counter[0]+=1;return real()
    docs.perform(reference,gate=counting);total=counter[0]
    for limit in range(1,total+1):
        host,docs=fresh();plan,real=docs.authenticate();calls=[0];stopped=[None]
        def gate():
            calls[0]+=1
            if calls[0]>=limit:
                stopped[0]=len(host.log);raise m.Refused(code)
            return real()
        try:receipt=docs.perform(host,gate=gate)
        except m.Refused:
            assert limit==1 and host.log==[];continue
        assert not [entry for entry in host.log[stopped[0]:] if entry in host.mutating()],'no mutating call after the gate refused'
        created=len(new(host))
        if created==0 and REFERENCE not in tags(host):assert receipt['status']=='REFUSED' and receipt['code'] in (code,'TAG_LISTING_UNAVAILABLE','PRECHECK_FAILED')
        else:
            assert receipt['status']==m.PARTIAL_STATUS and receipt['outcome']=='PARTIAL_REQUIRES_RECONCILIATION'
            assert [row['state'] for row in receipt['ledger']][:created]==['CREATED_DURABLE']*created or 'CREATED' in receipt['ledger'][created-1]['state']
        assert f.sealed(receipt)

def test_readback_inside_the_run_catches_a_change_after_creation():
    host,docs=fresh(groups=['SUPERVISOR'])
    def hook(host,name,detail,calls):
        if name=='fsync' and detail[0]==ORDER[3] and host.tree.get(ORDER[4]) is not None:host.tree.get(ORDER[0]).mode=0o755
    host.hook=hook;receipt=docs.run(host)
    assert (receipt['status'],receipt['code'])==(m.PARTIAL_STATUS,'READBACK_MISMATCH') and receipt['readback']['status']=='UNAVAILABLE'
    host,docs=fresh(groups=['SUPERVISOR'])
    def hook(host,name,detail,calls):
        if name=='fsync' and detail[0]==ORDER[3] and host.tree.get(ORDER[4]) is not None and host.tree.get(ORDER[2]+'/config.json') is None:
            host.tree.add(ORDER[2]+'/config.json',kind='file')
    host.hook=hook;assert docs.run(host)['code']=='READBACK_MISMATCH'

def test_noatime_unavailable_and_unsafe_docker_binary_fail_closed():
    host,docs=fresh();host.noatime_available=False;refused(host,docs,'NOATIME_UNAVAILABLE')
    host,docs=fresh();host.tree.get('/usr/bin/docker').mode=0o775;receipt=refused(host,docs,'BINARY_UNAVAILABLE_OR_UNSAFE')
    assert receipt['retention_tag']['code']=='BINARY_UNAVAILABLE_OR_UNSAFE' and not host.commands
    host,docs=fresh();host.tree.remove('/usr/bin/docker');refused(host,docs,'BINARY_UNAVAILABLE_OR_UNSAFE')
    host,docs=fresh(groups=['SUPERVISOR']);host.tree.remove('/usr/bin/docker');assert docs.run(host)['status']==m.COMPLETE_STATUS and not host.commands


# ---------------------------------------------------------------- the retention tag
def test_tag_is_refused_when_it_exists_and_absence_is_never_inferred_from_a_failed_command():
    host,docs=fresh();host.docker.images[0]['RepoTags'].append(REFERENCE)
    assert refused(host,docs,'RETENTION_TAG_EXISTS')['retention_tag']['tag_points_to_signed_image'] is True
    host,docs=fresh();host.docker.images[1]['RepoTags'].append(REFERENCE)
    assert refused(host,docs,'RETENTION_TAG_EXISTS')['retention_tag']['tag_points_to_signed_image'] is False
    host,docs=fresh();host.docker.images[0]['Id']='sha256:'+'ee'*32
    assert refused(host,docs,'IMAGE_ABSENT_OR_UNREADABLE')['retention_tag']['code']=='IMAGE_ABSENT_OR_UNREADABLE'
    # the signed string must resolve to an image whose own ID is that string, in the full form
    host,docs=fresh();host.docker.images[0]['Id']='sha256:'+'ee'*32;host.docker.images[1]['RepoTags'].append(hostemu.BACKEND)
    refused(host,docs,'IMAGE_ID_MISMATCH')
    host,docs=fresh();host.docker.images[0]['Id']='fbfbfbfbfbfb';host.docker.images[0]['RepoTags'].append(hostemu.BACKEND)
    refused(host,docs,'IMAGE_METADATA_INVALID')
    host,docs=fresh();host.docker.ls_returncode=1;refused(host,docs,'TAG_LISTING_UNAVAILABLE')
    host,docs=fresh();host.docker.ls_override=b'';refused(host,docs,'TAG_LISTING_INCONSISTENT')
    host,docs=fresh();host.docker.ls_override=b'{"id":"sha256:'+b'9c'*32+b'","repository":"c3po/backend","tag":"rollback"}\n'
    refused(host,docs,'TAG_LISTING_INCONSISTENT')
    for garbage in (b'not json\n',b'{"id":"fbfb","repository":"c3po/backend","tag":"production"}\n',b'{"id":"'+hostemu.BACKEND.encode()+b'","repository":"other","tag":"x"}\n',
                    b'[]\n',b'{"id":"'+hostemu.BACKEND.encode()+b'","repository":"c3po/backend","tag":"a b"}\n'):
        host,docs=fresh();host.docker.ls_override=garbage;refused(host,docs,'TAG_LISTING_UNAVAILABLE')
    host,docs=fresh();host.hang.add('docker');receipt=refused(host,docs,'COMMAND_TIMEOUT');assert len(host.commands)==1

def tag_only(**changes):
    host,docs=fresh(groups=['RETENTION_TAG']);return host,docs

def test_tag_command_outcomes_are_labelled_and_a_failure_is_absence_only_when_a_listing_proves_it():
    host,docs=fresh();host.docker.tag_returncode=1;receipt=docs.run(host)
    assert (receipt['retention_tag']['state'],receipt['retention_tag']['code'],receipt['retention_tag']['returncode'])==('NOT_CREATED','TAG_COMMAND_FAILED',1)
    assert (receipt['status'],receipt['code'])==(m.PARTIAL_STATUS,'TAG_COMMAND_FAILED') and len(new(host))==15 and receipt['objects_left_by_this_run']==15
    assert receipt['mutating_calls']=={'issued':16,'succeeded':15,'failed_nothing_changed':1,'uncertain':0}
    host,docs=tag_only();host.docker.tag_returncode=1;receipt=docs.run(host)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('REFUSED','REFUSED_NOTHING_CREATED','TAG_COMMAND_FAILED')
    # the command failed and the listing afterwards fails too: nothing proves absence
    host,docs=tag_only()
    def after(docker,args):
        if args[:2]==['image','tag']:docker.ls_returncode=1
    host.docker.before=after;host.docker.tag_returncode=1;receipt=docs.run(host)
    assert (receipt['retention_tag']['state'],receipt['status'],receipt['mutating_calls']['uncertain'])==('UNCERTAIN',m.PARTIAL_STATUS,1)
    # the command reported an error but the tag is there
    host,docs=tag_only()
    def odd(docker,args):
        if args[:2]==['image','tag']:docker.images[0]['RepoTags'].append(REFERENCE)
    host.docker.before=odd;host.docker.tag_returncode=1;receipt=docs.run(host)
    assert (receipt['retention_tag']['state'],receipt['status'])==('UNCERTAIN',m.PARTIAL_STATUS)
    host,docs=tag_only();host.hang.add(('image','tag'));receipt=docs.run(host)
    assert (receipt['retention_tag']['state'],receipt['retention_tag']['code'],receipt['status'])==('UNCERTAIN','TAG_COMMAND_TIMEOUT',m.PARTIAL_STATUS)
    assert [command['argv'][1:3] for command in host.commands].count(['image','tag'])==1,'never a second attempt'
    host,docs=tag_only();host.docker.tag_effect=False;receipt=docs.run(host)
    assert (receipt['retention_tag']['state'],receipt['retention_tag']['code'],receipt['status'])==('CREATED_UNVERIFIED','TAG_READBACK_UNAVAILABLE',m.PARTIAL_STATUS)
    host,docs=tag_only()
    def elsewhere(docker,args):
        if args[:2]==['image','tag']:docker.tag_effect=False;docker.images[1]['RepoTags'].append(REFERENCE)
    host.docker.before=elsewhere;receipt=docs.run(host)
    assert (receipt['retention_tag']['state'],receipt['retention_tag']['code'],receipt['retention_tag']['readback_id_equal'])==('CREATED_UNVERIFIED','TAG_READBACK_MISMATCH',False)

def test_tag_readback_needs_the_reference_among_the_tags_of_the_signed_image():
    """The tag command returned 0 and inspect by reference prints the signed ID, but the tag list of that image does not
    carry the reference: the reference resolved some other way and the tag is not proved. Never CREATED_VERIFIED."""
    for groups,created in ((['RETENTION_TAG'],0),(None,15)):
        host,docs=fresh(groups=groups)
        def resolves_without_the_tag(docker,args):
            if args[:2]==['image','tag']:
                docker.tag_effect=False;find=docker.find
                docker.find=lambda reference:dict(docker.images[0]) if reference==REFERENCE else find(reference)
        host.docker.before=resolves_without_the_tag;receipt=docs.run(host);facts=receipt['retention_tag']
        assert (facts['state'],facts['code'],facts['readback_id_equal'],facts['returncode'])==('CREATED_UNVERIFIED','TAG_READBACK_MISMATCH',True,0)
        assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,'PARTIAL_REQUIRES_RECONCILIATION','TAG_READBACK_MISMATCH')
        assert receipt['mutating_calls']=={'issued':created+1,'succeeded':created+1,'failed_nothing_changed':0,'uncertain':0}
        assert REFERENCE not in tags(host) and receipt['objects_left_by_this_run']==created+1 and receipt['readback'] is None and f.sealed(receipt)
        assert [command['argv'][1:3] for command in host.commands].count(['image','tag'])==1,'never a second attempt'

FAILURES=[lambda:OSError(errno.EAGAIN,'injected'),lambda:OSError(errno.ENOMEM,'injected'),lambda:OSError(errno.EMFILE,'injected'),lambda:RuntimeError('injected')]
@pytest.mark.parametrize('make',FAILURES)
@pytest.mark.parametrize('occurrence,state,code,counts,left',[
    (3,'NOT_ATTEMPTED','TAG_LISTING_UNAVAILABLE',{'issued':15,'succeeded':15,'failed_nothing_changed':0,'uncertain':0},15),
    (4,'UNCERTAIN','TAG_COMMAND_FAILED',{'issued':16,'succeeded':15,'failed_nothing_changed':0,'uncertain':1},15),
    (5,'CREATED_UNVERIFIED','TAG_READBACK_UNAVAILABLE',{'issued':16,'succeeded':16,'failed_nothing_changed':0,'uncertain':0},16)])
def test_a_process_that_cannot_be_started_after_the_last_mkdir_never_costs_the_ledger(make,occurrence,state,code,counts,left):
    """An OS error while a docker process is started (no descriptor, no memory, no process slot) is not a Refused. At the
    tag step the fifteen directories exist: their device and inode must still reach the receipt, with a constant code."""
    host,docs=fresh()
    def fail(host,detail):raise make()
    at_event(host,'run',occurrence,fail);receipt=docs.run(host)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,'PARTIAL_REQUIRES_RECONCILIATION',code) and f.sealed(receipt)
    assert [row['state'] for row in receipt['ledger']]==['CREATED_DURABLE']*15 and receipt['phase_reached']=='CREATION'
    for row in receipt['ledger']:
        node=host.tree.get(row['path']);assert (row['observed']['device'],row['observed']['inode'])==(node.dev,node.ino)
    assert receipt['retention_tag']['state']==state and receipt['mutating_calls']==counts and receipt['objects_left_by_this_run']==left
    assert 'injected' not in json.dumps(receipt) and set(receipt['chains'])=={'ETC','VAR_LIB','DATA_VOLUME'}

@pytest.mark.parametrize('make',FAILURES)
def test_a_process_that_cannot_be_started_elsewhere_is_labelled_by_what_is_known(make):
    def fail(host,detail):raise make()
    for occurrence in (1,2):                                             # in the precheck: nothing was created, the table is in the receipt
        host,docs=fresh();at_event(host,'run',occurrence,fail);receipt=docs.run(host)
        assert (receipt['status'],receipt['outcome'])==('REFUSED','REFUSED_NOTHING_CREATED') and new(host)==[] and len(receipt['precheck'])==15
        assert receipt['code'] in ('PRECHECK_OS_ERROR','PRECHECK_FAILED')
    # the tag command reported an error and the listing that would prove absence cannot be started: uncertain, never "not created"
    host,docs=fresh(groups=['RETENTION_TAG']);host.docker.tag_returncode=1;at_event(host,'run',5,fail);receipt=docs.run(host)
    assert (receipt['retention_tag']['state'],receipt['status'],receipt['mutating_calls']['uncertain'])==('UNCERTAIN',m.PARTIAL_STATUS,1)

def test_tag_step_reads_the_listing_again_and_needs_budget():
    host,docs=tag_only();count=[0]
    def racing(docker,args):
        if args[:2]==['image','ls']:
            count[0]+=1
            if count[0]==2:docker.images[1]['RepoTags'].append(REFERENCE)
    host.docker.before=racing;receipt=docs.run(host)
    assert (receipt['retention_tag']['state'],receipt['retention_tag']['code'],receipt['status'])==('NOT_ATTEMPTED','TAG_APPEARED_AFTER_PRECHECK','REFUSED')
    assert tags(host)[REFERENCE]==hostemu.OTHER and ['image','tag'] not in [command['argv'][1:3] for command in host.commands]
    for remaining,attempted in ((15.9,False),(16.0,True)):
        host,docs=tag_only();plan,real=docs.authenticate()
        def gate():
            real();return remaining
        receipt=docs.perform(host,gate=gate)
        assert (['image','tag'] in [command['argv'][1:3] for command in host.commands])==attempted
        assert receipt['retention_tag']['code']==(None if attempted else 'TAG_NOT_ATTEMPTED_BUDGET') and (receipt['status']==m.COMPLETE_STATUS)==attempted
    host,docs=fresh();host.docker.images[0]['RepoTags'].append(REFERENCE);docs.plan['retention_tag']['expect']='PRESENT';docs.chain()
    receipt=docs.run(host)
    assert receipt['outcome']=='PROVISIONED_ALL_VERIFIED_DURABLE' and receipt['retention_tag']['state']=='PRESENT_VERIFIED_NOT_TOUCHED'
    assert ['image','tag'] not in [command['argv'][1:3] for command in host.commands]
    host,docs=fresh();docs.plan['retention_tag']['expect']='PRESENT';docs.chain();refused(host,docs,'EXPECTATION_MISMATCH')
    host,docs=fresh();host.docker.images[1]['RepoTags'].append(REFERENCE);docs.plan['retention_tag']['expect']='PRESENT';docs.chain()
    refused(host,docs,'EXPECTATION_MISMATCH')


# ---------------------------------------------------------------- receipt size
def test_receipt_at_the_caps_needs_no_reduction_and_a_reduced_receipt_is_never_complete(monkeypatch):
    host=f.world(k);deep='/mnt/'+'/'.join(['d%02d-'%index+'x'*40 for index in range(2)])
    node=host.tree.add(deep,uid=1000,gid=1000,dev=811)
    for index in range(1,3):host.tree.get('/mnt/'+'/'.join(deep.split('/')[2:2+index])).dev=811
    capacity={'root_path':deep+'/'+'c'*64,'receipt_directory_path':'/var/lib/c3po-reader/'+'r'*64}
    fields=f.provision_fields(k,host,leaf='j'*64,capacity=capacity)
    fields['data_volume_path']=deep;table=m.layout(fields['groups'],deep,'j'*64,capacity,'B')
    fields['creates']=[dict(row,expect='ABSENT') for row in table];fields['chains']={name:hostemu.rows(host,path) for name,path in m.chain_paths(table,deep,capacity).items()}
    fields['retention_tag']['tag']='massive-supervisor-'+'e'*41
    for row in fields['chains']['DATA_VOLUME'][2:]:host.tree.get(row['path']).uid=0;row['uid']=0;row['gid']=host.tree.get(row['path']).gid
    docs=f.Docs(k,fields);receipt=docs.run(host)
    assert receipt['outcome']=='PROVISIONED_ALL_VERIFIED_DURABLE' and receipt['size_reductions']==[] and len(f.line(receipt))<24000
    monkeypatch.setattr(m,'RECEIPT_LIMIT',9000);host,docs=fresh();receipt=docs.run(host)
    assert receipt['status']==m.PARTIAL_STATUS and receipt['outcome']=='RECEIPT_REDUCED_STATE_REQUIRES_READBACK' and f.sealed(receipt)
    assert receipt['size_reductions'] and len(receipt['ledger'])==15 and receipt['mutating_calls']['succeeded']==16 and len(f.line(receipt))<=9000
    monkeypatch.setattr(m,'RECEIPT_LIMIT',600);host,docs=fresh();receipt=docs.run(host)
    assert receipt['code']=='RECEIPT_REDUCED_TO_MINIMUM' and receipt['status']==m.PARTIAL_STATUS and receipt['mutating_calls']['succeeded']==16 and f.sealed(receipt)
    assert receipt['objects_left_by_this_run']==16 and receipt['outcome']=='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
    monkeypatch.setattr(m,'RECEIPT_LIMIT',5000);host,docs=fresh();receipt=docs.run(host)
    assert 'LEDGER_REDUCED_TO_STATES' in receipt['size_reductions'] and [row['state'] for row in receipt['ledger']]==['CREATED_DURABLE']*15
