"""K2a end to end on the emulated host, in both signed modes: what a complete run does and says, every refusal with
its code and with nothing changed, what each failure after the container was started leaves and how the receipt tells
them apart, hostile states of the file system and hostile answers of the engine, the time budget, and the crash points.
Synthetic and local: no host, no docker, no credential."""
import copy
from datetime import timedelta
import json

import pytest

import family as f
import hostemu
import k2a

MODES=('REAL','REHEARSAL')
PARTIAL='PARTIAL_METADATA_REQUIRES_REVIEW'
def fresh(mode='REAL'):
    docs,host=k2a.case(mode);return docs.k.m,docs,host
def text_fits(m,value):return m.text(value,m.COMMAND_VARIABLES['DOCKER_CONFIG']) and m.text(value,m.MOUNT_PATH)
def node(host,path):return host.tree.get(path)
def names(host,path):return sorted(node(host,path).children)
def replace(host,path,kind,**attributes):
    host.tree.remove(path);return host.tree.add(path,kind=kind,**attributes)
def refused(receipt,code,phase='PRECHECK'):
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==('REFUSED','REFUSED_NOTHING_CHANGED_NO_CONTAINER_STARTED',code,phase),(receipt['status'],receipt['code'])
    assert receipt['root_verdict']=='UNTOUCHED_NO_CONTAINER_STARTED' and receipt['mutating_calls']['succeeded']==0 and receipt['mutating_calls']['uncertain']==0
    assert receipt['objects_left_by_this_run']==0 and receipt['pre_existing_objects_modified'] is False and f.sealed(receipt)
def partial(receipt,code,verdict='NOT_TO_BE_USED_AGAIN'):
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==(PARTIAL,'PARTIAL_SEE_ROOT_VERDICT',code,'EFFECTS'),(receipt['status'],receipt['code'])
    assert receipt['root_verdict']==verdict and f.sealed(receipt)
def invariants(mode,host):
    """Whatever a run that reached the container ended in: a rehearsal never wrote into the real journal root, never
    wrote into the configuration directory of the unit and gave it to no docker command; a real run created nothing by
    itself; no descriptor is left."""
    if mode=='REHEARSAL':
        assert names(host,k2a.JOURNAL)==[] and names(host,k2a.CONFIG)==[] and [entry[:2] for entry in host.log if entry[0] in hostemu.MUTATING]==[('mkdir',k2a.REHEARSAL_CONFIG),('mkdir',k2a.REHEARSAL_ROOT)]
    else:assert [entry[0] for entry in host.log if entry[0] in hostemu.MUTATING]==[] and node(host,k2a.REHEARSAL_ROOT) is None and node(host,k2a.REHEARSAL_CONFIG) is None
    assert host.commands and all(entry['docker_config']==k2a.config_of(mode) for entry in host.commands),'every docker command of a mode under the one directory of that mode'
    assert host.fds=={} and [entry for entry in host.log if entry[0] in ('create','write','link','unlink')]==[]
def then(behaviour):
    """An emulated container that does what the correct one does and then something else."""
    def on_run(call):
        result=k2a.container(call);changed=behaviour(call,result);return result if changed is None else changed
    return on_run
def line_of(result,**changes):
    row=json.loads(result[1]);row.update(changes)
    for key in [key for key,value in row.items() if value is k2a]:del row[key]               # k2a (the module) marks a member to drop
    return result[0],(json.dumps(row,sort_keys=True)+'\n').encode()


# ---------------------------------------------------------------- complete runs
def test_real_run_creates_the_catalog_and_the_signers_see_these_literal_effects():
    m,docs,host=fresh();plan=docs.plan;root=node(host,k2a.JOURNAL);before=host.tree.snapshot()
    argv=['run','--rm','-i','--pull','never','--init','--user','0:0','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
          '--mount','type=bind,source=/var/lib/c3po-bar/journal,target=/c3po-bar-journal',hostemu.BACKEND,'python','-I','-B','-','/c3po-bar-journal','R2D2-V2-SHADOW-2026-10-05']
    assert docs.go['effects']=={'operation':'GO_WRITE_HOSTOPS02_CATALOG_INIT_01','mode':'REAL',
        'journal_root':{'path':k2a.JOURNAL,'is_the_real_journal_root':True,'expect':'PRESENT_EMPTY_ROOT_ROOT_0700_AS_SIGNED',
                        'signed_chain':{'path':k2a.JOURNAL,'row':plan['journal_chain'][-1],'chain_sha256':f.sha(f.canonical(plan['journal_chain'])),'mount_point_by_device_change':'/'},
                        'signed_chain_is_of':'THE_ROOT_ITSELF','stays_after_the_run':True},
        'real_journal_root_read_only':None,
        'docker_config':{'path':k2a.CONFIG,'row':plan['docker_config_chain'][-1],'chain_sha256':f.sha(f.canonical(plan['docker_config_chain'])),
                         'mount_point_by_device_change':'/','expect':'PRESENT_EMPTY_BEFORE_AND_AFTER','given_to_docker':True},
        'rehearsal_docker_config':None,
        'container':{'image_id':hostemu.BACKEND,'image_revision':hostemu.REVISION,'docker_config_variable':'/etc/c3po-bar/docker-cli','docker_arguments':argv,
                     'bind':{'source':k2a.JOURNAL,'target':'/c3po-bar-journal','read_only':False},'network':'none',
                     'standard_input':{'sha256':k2a.SCRIPT_SHA,'bytes':1040},'time_limit_seconds':40},
        'epoch':'R2D2-V2-SHADOW-2026-10-05','epoch_source':'c3po/backend/app/r2d2_v2_epoch_assembler.py:9 EPOCH at dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858',
        'creates':{'by_this_process':[],'by_the_container':[k2a.JOURNAL+'/epoch.json',k2a.JOURNAL+'/maintenance.lock'],'file_mode_octal':'0600'},
        'success_outcome':'CATALOG_READY_VERIFIED','evidence_boot_id_sha256':f.BOOT_SHA,'pre_existing_objects_modified':True,'removes':[],'activation':False}
    assert docs.go['success_criterion']=='CATALOG_READY_VERIFIED'
    receipt=docs.run(host)
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'],receipt['mode'])==(m.COMPLETE_STATUS,'CATALOG_READY_VERIFIED',None,'EFFECTS','REAL')
    assert receipt['root_verdict']=='CATALOG_READY_VERIFIED' and receipt['mutating_calls']=={'issued':1,'succeeded':1,'failed_nothing_changed':0,'uncertain':0}
    assert receipt['commands_started']=={'READ':3,'CONTAINER':0,'EFFECT':1} and receipt['objects_left_by_this_run']==2 and receipt['pre_existing_objects_modified'] is True
    assert receipt['journal_root']=={'path':k2a.JOURNAL,'device':root.dev,'inode':root.ino,'created_by_this_run':False} and receipt['directories']==[]
    assert receipt['run']=={'state':'RETURNED','code':None,'returncode':0,'seconds':0}
    line=receipt['script_line']
    assert (line['status'],line['created'],line['epoch_equal'],line['entries_as_expected'],line['keys_exact'],line['device'],line['inode'])==('CATALOG_READY',True,True,True,True,root.dev,root.ino)
    expected=k2a.expected_epoch_json(k2a.EPOCH,root.dev,root.ino);held=receipt['catalog']
    assert held=={'status':'COMPLETE','code':None,'entries':2,'other_entries':0,'root_unchanged':True,
                  'files':{'epoch.json':{'exists':True,'type':'file','uid':0,'gid':0,'mode_octal':'0600','links':1,'bytes':len(expected),'on_the_device_of_the_root':True},
                           'maintenance.lock':{'exists':True,'type':'file','uid':0,'gid':0,'mode_octal':'0600','links':1,'bytes':0,'on_the_device_of_the_root':True}},
                  'epoch_json':{'bytes':len(expected),'sha256':f.sha(expected),'expected_sha256':f.sha(expected),'equal_to_the_expected_bytes':True}}
    assert receipt['containers']=={'status':'COMPLETE','before':8,'after':8,'not_there_before':0,'rows':[]}
    assert receipt['docker_config']=={'path':k2a.CONFIG,'is_the_directory_of_the_unit':True,'entries_before':0,'entries_after':0,'code':None}
    assert receipt['precheck']=={'docker_config_entries':0,'journal_root_entries':0,'image':{'id_as_signed':True,'revision_as_signed':True},'containers':8,
                                 'docker_config_entries_after_the_reads':0}
    assert receipt['observed_rows']=={'docker_config':plan['docker_config_chain'],'journal':plan['journal_chain'],'reference':[]},'the rows as this run read them'
    assert receipt['observed_at']==docs.now.isoformat() and receipt['clock']=={'utc_start':docs.now.isoformat(),'utc_end':docs.now.isoformat(),'monotonic_elapsed_ms':0}
    printed=(json.dumps({'created':True,'device':root.dev,'entries':k2a.NAMES,'epoch':k2a.EPOCH,'inode':root.ino,'status':'CATALOG_READY'},sort_keys=True)+'\n').encode()
    assert (line['bytes'],line['sha256'],line['one_json_line'],line['as_signed'],line['refusal_code'],line['returncode'])==(len(printed),f.sha(printed),True,True,None,0)
    # on the host: the two files of the application, and nothing else changed anywhere
    assert names(host,k2a.JOURNAL)==k2a.NAMES and bytes(node(host,k2a.JOURNAL+'/epoch.json').content)==expected and bytes(node(host,k2a.JOURNAL+'/maintenance.lock').content)==b''
    for name in k2a.NAMES:host.tree.remove(k2a.JOURNAL+'/'+name)
    assert host.tree.snapshot()==before and host.fds=={}
    # this process changed nothing by itself: the only things that changed the host are the container's two files and the one run
    assert [entry[0] if type(entry) is tuple else entry['argv'][1] for entry in host.mutating()]==['container-write','container-write','run']
    assert [entry[0] for entry in host.log if entry[0] in hostemu.MUTATING]==[]
    # the three commands, each under the unit's empty configuration directory; the run with the script and the 40 s class
    assert [(entry['argv'][1:3],entry['docker_config'],entry['seconds'],entry['stdin'] is None) for entry in host.commands]==[
        (['image','inspect'],k2a.CONFIG,8,True),(['ps','-a'],k2a.CONFIG,8,True),(['run','--rm'],k2a.CONFIG,40,False),(['ps','-a'],k2a.CONFIG,8,True)]
    assert host.commands[2]['argv']==['/usr/bin/docker']+argv and host.commands[2]['stdin']==k2a.script() and host.commands[2]['variables']=={} and host.commands[2]['capture'] is True

def test_rehearsal_creates_a_throwaway_root_runs_the_same_command_on_it_and_only_reads_the_real_root():
    m,docs,host=fresh('REHEARSAL');plan=docs.plan;before=host.tree.snapshot()
    effects=docs.go['effects']
    assert (effects['mode'],effects['success_outcome'],effects['epoch'],effects['epoch_source'])==('REHEARSAL','REHEARSAL_CATALOG_READY_VERIFIED',k2a.DIAG,'SIGNED_DIAGNOSTIC_STRING')
    assert effects['journal_root']=={'path':k2a.REHEARSAL_ROOT,'is_the_real_journal_root':False,'expect':'ABSENT_THEN_CREATED_0700_BY_THIS_RUN',
        'signed_chain':{'path':'/var/lib','row':plan['journal_chain'][-1],'chain_sha256':f.sha(f.canonical(plan['journal_chain'])),'mount_point_by_device_change':'/'},
        'signed_chain_is_of':'THE_PARENT','stays_after_the_run':True}
    assert effects['real_journal_root_read_only']=={'path':k2a.JOURNAL,'row':plan['reference_chain'][-1],'chain_sha256':f.sha(f.canonical(plan['reference_chain'])),
        'mount_point_by_device_change':'/','expect':'PRESENT_EMPTY_ROOT_ROOT_0700_AS_SIGNED','same_device_as_the_parent_of_the_throwaway':True}
    assert effects['creates']=={'by_this_process':[k2a.REHEARSAL_CONFIG,k2a.REHEARSAL_ROOT],'by_the_container':[k2a.REHEARSAL_ROOT+'/epoch.json',k2a.REHEARSAL_ROOT+'/maintenance.lock'],'file_mode_octal':'0600'}
    assert effects['container']['bind']=={'source':k2a.REHEARSAL_ROOT,'target':'/c3po-bar-journal','read_only':False} and effects['pre_existing_objects_modified'] is False
    # the configuration directory of the unit is only read; docker gets a directory this run creates beside the throwaway root
    assert k2a.REHEARSAL_CONFIG=='/var/lib/c3po-bar-rehearsal-20261003a.docker-cli'==effects['container']['docker_config_variable']
    assert effects['docker_config']=={'path':k2a.CONFIG,'row':plan['docker_config_chain'][-1],'chain_sha256':f.sha(f.canonical(plan['docker_config_chain'])),
        'mount_point_by_device_change':'/','expect':'PRESENT_EMPTY_ONLY_READ_NEVER_GIVEN_TO_DOCKER','given_to_docker':False}
    assert effects['rehearsal_docker_config']=={'path':k2a.REHEARSAL_CONFIG,'expect':'ABSENT_THEN_CREATED_0700_BY_THIS_RUN_EMPTY_AFTER_IT','given_to_docker':True,'stays_after_the_run':True}
    assert effects['container']['docker_arguments'][-9:]==['--mount','type=bind,source=%s,target=/c3po-bar-journal'%k2a.REHEARSAL_ROOT,hostemu.BACKEND,'python','-I','-B','-','/c3po-bar-journal',k2a.DIAG]
    assert docs.go['success_criterion']=='REHEARSAL_CATALOG_READY_VERIFIED'
    receipt=docs.run(host);made=node(host,k2a.REHEARSAL_ROOT);given=node(host,k2a.REHEARSAL_CONFIG)
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['mode'],receipt['root_verdict'])==(m.COMPLETE_STATUS,'REHEARSAL_CATALOG_READY_VERIFIED',None,'REHEARSAL','CATALOG_READY_VERIFIED')
    assert receipt['mutating_calls']=={'issued':3,'succeeded':3,'failed_nothing_changed':0,'uncertain':0} and receipt['objects_left_by_this_run']==4
    assert receipt['pre_existing_objects_modified'] is False and receipt['journal_root']=={'path':k2a.REHEARSAL_ROOT,'device':made.dev,'inode':made.ino,'created_by_this_run':True}
    assert [(row['key'],row['path'],row['state'],row['fsync_directory'],row['fsync_parent']) for row in receipt['directories']]==[
        ('DOCKER_CONFIG',k2a.REHEARSAL_CONFIG,'CREATED_DURABLE',True,True),('JOURNAL_ROOT',k2a.REHEARSAL_ROOT,'CREATED_DURABLE',True,True)]
    assert receipt['precheck']=={'docker_config_entries':0,'real_journal_root_entries':0,'throwaway':{'exists':False},'throwaway_docker_config':{'exists':False},
                                 'image':{'id_as_signed':True,'revision_as_signed':True},'containers':8,'docker_config_entries_after_the_reads':0}
    assert receipt['docker_config']=={'path':k2a.REHEARSAL_CONFIG,'is_the_directory_of_the_unit':False,'entries_before':0,'entries_after':0,'code':None}
    assert receipt['observed_rows']=={'docker_config':plan['docker_config_chain'],'journal':plan['journal_chain'],'reference':plan['reference_chain']}
    assert (made.kind,made.uid,made.gid,made.mode,made.dev)==('dir',0,0,0o700,hostemu.ROOT_DEVICE) and names(host,k2a.REHEARSAL_ROOT)==k2a.NAMES
    assert (given.kind,given.uid,given.gid,given.mode,given.dev)==('dir',0,0,0o700,hostemu.ROOT_DEVICE) and names(host,k2a.REHEARSAL_CONFIG)==[]
    assert bytes(node(host,k2a.REHEARSAL_ROOT+'/epoch.json').content)==k2a.expected_epoch_json(k2a.DIAG,made.dev,made.ino)
    # NEUTRAL FOR PRODUCTION: no docker command of the rehearsal ran under the directory of the unit; all four ran under the rehearsal's own
    assert [(entry['argv'][1:3],entry['docker_config']) for entry in host.commands]==[(['image','inspect'],k2a.REHEARSAL_CONFIG),(['ps','-a'],k2a.REHEARSAL_CONFIG),
                                                                                      (['run','--rm'],k2a.REHEARSAL_CONFIG),(['ps','-a'],k2a.REHEARSAL_CONFIG)]
    assert k2a.CONFIG not in json.dumps([[entry['argv'],entry['docker_config'],entry['variables']] for entry in host.commands])
    # the real journal root, the configuration directory of the unit and everything else are as they were: the only new
    # objects of the tree are the two throwaway directories and the two files of the container
    assert names(host,k2a.JOURNAL)==[] and names(host,k2a.CONFIG)==[]
    host.tree.remove(k2a.REHEARSAL_ROOT);host.tree.remove(k2a.REHEARSAL_CONFIG);assert host.tree.snapshot()==before and host.fds=={}
    assert [entry[0] if type(entry) is tuple else entry['argv'][1] for entry in host.mutating()]==['mkdir','mkdir','container-write','container-write','run']
    # in this order: the configuration directory, the two reads under it, the throwaway root, the run
    order=[(entry[0],entry[1]) if entry[0]!='run' else ('run',' '.join(entry[1][1:3])) for entry in host.log if entry[0] in ('umask','mkdir','run')]
    assert order==[('umask',0o077),('mkdir',k2a.REHEARSAL_CONFIG),('run','image inspect'),('run','ps -a'),('mkdir',k2a.REHEARSAL_ROOT),('run','run --rm'),('run','ps -a')]
    assert [entry[1] for entry in host.log if entry[0]=='fsync']==[k2a.REHEARSAL_CONFIG,'/var/lib',k2a.REHEARSAL_ROOT,'/var/lib']

@pytest.mark.parametrize('mode',MODES)
def test_everything_is_looked_at_and_the_budget_checked_before_the_first_effect(mode):
    m,docs,host=fresh(mode);docs.run(host);order=[(entry[0],entry[1]) for entry in host.log]
    first=min(index for index,entry in enumerate(host.log) if entry[0]=='mkdir' or (entry[0]=='run' and entry[1][1]=='run'))
    started=[index for index,entry in enumerate(host.log) if entry[0]=='run' and entry[1][1]=='run'][0]
    reads=[index for index,entry in enumerate(host.log) if entry[0]=='run' and entry[1][1:3] in (['image','inspect'],['ps','-a'])]
    assert reads[0]<reads[1]<started<reads[2],'image and the first listing before the container, the second listing after it'
    if mode=='REAL':assert first==started,'REAL: nothing is created; the two reads are part of the precheck'
    else:
        made=[index for index,entry in enumerate(host.log) if entry[0]=='mkdir'];assert made[0]==first<reads[0] and reads[1]<made[1]<started
        probed=[entry[1] for entry in host.log[:first] if entry[0]=='lstat'];assert k2a.REHEARSAL_ROOT in probed and k2a.REHEARSAL_CONFIG in probed
        assert ('lstat','/usr/bin/docker') in [entry[:2] for entry in host.log[:first]],'the docker binary is looked at before a directory is created for it'
    assert ('open',k2a.CONFIG) in [entry[:2] for entry in host.log[:first]] and ('open',k2a.JOURNAL) in [entry[:2] for entry in host.log[:first]]

@pytest.mark.parametrize('mode',MODES)
def test_a_second_run_on_the_same_root_is_refused_before_anything_is_started(mode):
    m,docs,host=fresh(mode);assert docs.run(host)['status']==m.COMPLETE_STATUS;before=k2a.state_of(host);runs=len(host.container_runs())
    again=f.Docs(docs.k,copy.deepcopy({key:docs.plan[key] for key in m.PLAN_KEYS}));receipt=again.run(host)
    refused(receipt,'JOURNAL_ROOT_NOT_EMPTY' if mode=='REAL' else 'REFERENCE_ROOT_NOT_EMPTY' if names(host,k2a.JOURNAL) else 'DESTINATION_PRESENT')
    assert k2a.state_of(host)==before and len(host.container_runs())==runs

def test_success_outcome_follows_the_signed_mode_and_a_go_that_names_the_other_one_is_refused():
    for mode,mine,other in (('REAL','CATALOG_READY_VERIFIED','REHEARSAL_CATALOG_READY_VERIFIED'),('REHEARSAL','REHEARSAL_CATALOG_READY_VERIFIED','CATALOG_READY_VERIFIED')):
        m,docs,host=fresh(mode);assert m.success_of(docs.plan)==mine==docs.go['success_criterion']
        docs.go['success_criterion']=other;docs.chain(criterion=False);assert f.refusal(docs.authenticate)=='GO_CRITERION'
        receipt=docs.run(f.Untouchable());assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','GO_CRITERION','AUTHENTICATION')
    assert json.loads((k2a.K().dir/'GO.UNBOUND.json').read_bytes())['success_criterion'] is None


# ---------------------------------------------------------------- the plan: refused from its bytes, before any claim
def change(path,value):
    def apply(plan,host):
        target=plan
        for key in path[:-1]:target=target[key]
        target[path[-1]]=value(plan,host) if callable(value) else value
    return apply
BOTH=[(change(['mode'],'DRY'),'MODE_INVALID'),(change(['mode'],None),'MODE_INVALID'),(change(['mode'],['REAL']),'MODE_INVALID'),
      (change(['evidence_boot_id_sha256'],None),'EVIDENCE_BOOT_UNBOUND'),(change(['evidence_boot_id_sha256'],'0'*64),'EVIDENCE_BOOT_UNBOUND'),
      (change(['script_sha256'],'3'*64),'SCRIPT_NOT_THE_PINNED_HASH'),(change(['script_sha256'],None),'SCRIPT_NOT_THE_PINNED_HASH'),
      (change(['image_revision'],'development'),'IMAGE_REVISION_UNBOUND'),(change(['image_revision'],None),'IMAGE_REVISION_UNBOUND'),
      (change(['image_id'],'c3po/backend:production'),'IMAGE_ID'),(change(['image_id'],None),'IMAGE_ID'),
      (change(['container_journal_root'],'/app'),'CONTAINER_JOURNAL_ROOT_INVALID'),(change(['container_journal_root'],'/tmp'),'CONTAINER_JOURNAL_ROOT_INVALID'),
      (change(['container_journal_root'],'/var'),'CONTAINER_JOURNAL_ROOT_INVALID'),(change(['container_journal_root'],'/app/day-d-data/journal'),'CONTAINER_JOURNAL_ROOT_INVALID'),
      (change(['container_journal_root'],'/'),'CONTAINER_JOURNAL_ROOT_INVALID'),(change(['container_journal_root'],'/..'),'CONTAINER_JOURNAL_ROOT_INVALID'),
      (change(['container_journal_root'],'/.hidden'),'CONTAINER_JOURNAL_ROOT_INVALID'),(change(['container_journal_root'],'/a,readonly'),'CONTAINER_JOURNAL_ROOT_INVALID'),
      (change(['container_journal_root'],'c3po-bar-journal'),'CONTAINER_JOURNAL_ROOT_INVALID'),(change(['container_journal_root'],None),'CONTAINER_JOURNAL_ROOT_INVALID'),
      (change(['docker_config_chain'],None),'CHAIN_ROW_INVALID'),(change(['docker_config_chain'],[]),'CHAIN_ROW_INVALID'),
      (change(['docker_config_chain'],lambda plan,host:hostemu.rows(host,'/')),'CHAIN_ROW_INVALID'),
      (change(['docker_config_chain',-1,'mode'],0o770),'CHAIN_ROW_UNSAFE'),(change(['docker_config_chain',-1,'mode'],0o750),'DOCKER_CONFIG_NOT_PRIVATE'),
      (change(['docker_config_chain',-1,'mode'],0o500),'DOCKER_CONFIG_NOT_PRIVATE'),
      (change(['docker_config_chain',-1,'uid'],1000),'CHAIN_ROW_UNSAFE'),(change(['docker_config_chain',-1,'gid'],5),'DOCKER_CONFIG_NOT_PRIVATE'),
      (change(['docker_config_chain',-1,'device'],999),'DOCKER_CONFIG_IS_A_MOUNT_POINT'),(change(['docker_config_chain',1,'uid'],1000),'CHAIN_ROW_UNSAFE'),
      (change(['docker_config_chain',-1,'inode'],0),'CHAIN_ROW_INVALID'),(change(['docker_config_chain',-2,'path'],'/etc/other'),'CHAIN_ROW_INVALID'),
      # the layout floor: the docker CLI configuration directory is the one of the unit and no other
      (change(['docker_config_chain'],lambda plan,host:hostemu.rows(host,'/etc/c3po-bar/manifests')),'DOCKER_CONFIG_NOT_THE_DIRECTORY_OF_THE_UNIT'),
      (change(['docker_config_chain'],lambda plan,host:hostemu.rows(host,k2a.JOURNAL)),'DOCKER_CONFIG_NOT_THE_DIRECTORY_OF_THE_UNIT'),
      (change(['docker_config_chain'],lambda plan,host:hostemu.rows(host,k2a.PRIVATE_PARENT)),'DOCKER_CONFIG_NOT_THE_DIRECTORY_OF_THE_UNIT'),
      (change(['docker_config_chain'],lambda plan,host:hostemu.rows(host,k2a.PRIVATE_PARENT+'/supervisor')),'DOCKER_CONFIG_NOT_THE_DIRECTORY_OF_THE_UNIT'),
      (change(['docker_config_chain'],lambda plan,host:hostemu.rows(host,host.tree.add('/etc/c3po-reader',mode=0o700) and host.tree.add('/etc/c3po-reader/docker-cli',mode=0o700) and '/etc/c3po-reader/docker-cli')),
       'DOCKER_CONFIG_NOT_THE_DIRECTORY_OF_THE_UNIT'),
      (change(['journal_chain'],None),'CHAIN_ROW_INVALID'),(change(['journal_chain'],lambda plan,host:hostemu.rows(host,'/')),'CHAIN_ROW_INVALID'),
      (change(['journal_chain',-1,'uid'],1000),'CHAIN_ROW_UNSAFE'),(change(['journal_chain',1,'mode'],0o777),'CHAIN_ROW_UNSAFE'),
      (change(['journal_chain',0,'path'],'/x'),'CHAIN_ROW_INVALID'),(change(['journal_chain',-1,'extra'],1),'CHAIN_ROW_INVALID')]
REAL_ONLY=[(change(['epoch'],'R2D2-V2-SHADOW-2026-10-06'),'EPOCH_NOT_THE_COMPILED_CONSTANT'),(change(['epoch'],k2a.DIAG),'EPOCH_NOT_THE_COMPILED_CONSTANT'),
           (change(['epoch'],None),'EPOCH_NOT_THE_COMPILED_CONSTANT'),(change(['epoch'],['R2D2-V2-SHADOW-2026-10-05']),'EPOCH_NOT_THE_COMPILED_CONSTANT'),
           (change(['throwaway_name'],k2a.THROWAWAY),'MODE_MEMBERS_INVALID'),(change(['reference_chain'],lambda plan,host:hostemu.rows(host,k2a.JOURNAL)),'MODE_MEMBERS_INVALID'),
           (change(['journal_chain',-1,'mode'],0o720),'CHAIN_ROW_UNSAFE'),(change(['journal_chain',-1,'mode'],0o750),'JOURNAL_ROOT_NOT_PRIVATE'),
           (change(['journal_chain',-1,'mode'],0o500),'JOURNAL_ROOT_NOT_PRIVATE'),
           (change(['journal_chain',-1,'mode'],0o1700),'JOURNAL_ROOT_NOT_PRIVATE'),(change(['journal_chain',-1,'gid'],1000),'JOURNAL_ROOT_NOT_PRIVATE'),
           (change(['journal_chain',-1,'device'],hostemu.DATA_DEVICE),'JOURNAL_ROOT_IS_A_MOUNT_POINT'),
           (change(['journal_chain'],lambda plan,host:hostemu.rows(host,hostemu.DATA)),'CHAIN_ROW_UNSAFE'),
           # the layout floor: only a leaf of the private parent is a journal root, and never the state root
           (change(['journal_chain'],lambda plan,host:hostemu.rows(host,k2a.CONFIG)),'JOURNAL_ROOT_NOT_A_LEAF_OF_THE_PRIVATE_PARENT'),
           (change(['journal_chain'],lambda plan,host:hostemu.rows(host,'/etc/c3po-bar')),'JOURNAL_ROOT_NOT_A_LEAF_OF_THE_PRIVATE_PARENT'),
           (change(['journal_chain'],lambda plan,host:hostemu.rows(host,'/etc/c3po-bar/manifests')),'JOURNAL_ROOT_NOT_A_LEAF_OF_THE_PRIVATE_PARENT'),
           (change(['journal_chain'],lambda plan,host:hostemu.rows(host,k2a.PRIVATE_PARENT)),'JOURNAL_ROOT_NOT_A_LEAF_OF_THE_PRIVATE_PARENT'),
           (change(['journal_chain'],lambda plan,host:hostemu.rows(host,host.tree.add(k2a.JOURNAL+'/deeper',mode=0o700) and k2a.JOURNAL+'/deeper')),'JOURNAL_ROOT_NOT_A_LEAF_OF_THE_PRIVATE_PARENT'),
           (change(['journal_chain'],lambda plan,host:hostemu.rows(host,host.tree.add('/var/lib/c3po-reader',mode=0o700) and '/var/lib/c3po-reader')),'JOURNAL_ROOT_NOT_A_LEAF_OF_THE_PRIVATE_PARENT'),
           (change(['journal_chain'],lambda plan,host:hostemu.rows(host,k2a.PRIVATE_PARENT+'/supervisor')),'JOURNAL_ROOT_IS_THE_STATE_ROOT')]
REHEARSAL_ONLY=[(change(['epoch'],'R2D2-V2-SHADOW-2026-10-05'),'EPOCH_NOT_A_DIAGNOSTIC_ONE'),(change(['epoch'],'R2D2-V2-SHADOW-K2A'),'EPOCH_NOT_A_DIAGNOSTIC_ONE'),
                (change(['epoch'],'R2D2-V2-DIAG-'),'EPOCH_NOT_A_DIAGNOSTIC_ONE'),(change(['epoch'],'R2D2-V2-DIAG-a b'),'EPOCH_NOT_A_DIAGNOSTIC_ONE'),
                (change(['epoch'],None),'EPOCH_NOT_A_DIAGNOSTIC_ONE'),
                (change(['throwaway_name'],None),'THROWAWAY_NAME_INVALID'),(change(['throwaway_name'],'journal'),'THROWAWAY_NAME_INVALID'),
                (change(['throwaway_name'],'c3po-bar-rehearsal-'),'THROWAWAY_NAME_INVALID'),(change(['throwaway_name'],'c3po-bar-rehearsal-A'),'THROWAWAY_NAME_INVALID'),
                (change(['throwaway_name'],'c3po-bar-rehearsal-a/b'),'THROWAWAY_NAME_INVALID'),(change(['throwaway_name'],'../c3po-bar-rehearsal-a'),'THROWAWAY_NAME_INVALID'),
                (change(['reference_chain'],None),'CHAIN_ROW_INVALID'),(change(['reference_chain',-1,'mode'],0o500),'REFERENCE_ROOT_NOT_PRIVATE'),
                (change(['reference_chain',-1,'gid'],7),'REFERENCE_ROOT_NOT_PRIVATE'),(change(['reference_chain',-1,'uid'],1000),'CHAIN_ROW_UNSAFE'),
                (change(['reference_chain',-1,'device'],hostemu.DATA_DEVICE),'REFERENCE_ROOT_IS_A_MOUNT_POINT'),
                (change(['journal_chain',-1,'mode'],0o2755),'PARENT_SETGID'),(change(['journal_chain',-1,'mode'],0o1777),'CHAIN_ROW_UNSAFE'),
                (change(['journal_chain',-1,'device'],hostemu.DATA_DEVICE),'REHEARSAL_NOT_ON_THE_FILESYSTEM_OF_THE_REAL_ROOT'),
                (change(['journal_chain'],lambda plan,host:hostemu.rows(host,hostemu.DATA)),'CHAIN_ROW_UNSAFE'),
                # the layout floor: a throwaway is created in /var/lib and nowhere else, and the root a rehearsal reads is a journal root
                (change(['journal_chain'],lambda plan,host:hostemu.rows(host,k2a.PRIVATE_PARENT)),'THROWAWAY_PARENT_NOT_THE_FIXED_ONE'),
                (change(['journal_chain'],lambda plan,host:hostemu.rows(host,k2a.PRIVATE_PARENT+'/supervisor')),'THROWAWAY_PARENT_NOT_THE_FIXED_ONE'),
                (change(['journal_chain'],lambda plan,host:hostemu.rows(host,k2a.JOURNAL)),'THROWAWAY_PARENT_NOT_THE_FIXED_ONE'),
                (change(['journal_chain'],lambda plan,host:hostemu.rows(host,k2a.CONFIG)),'THROWAWAY_PARENT_NOT_THE_FIXED_ONE'),
                (change(['journal_chain'],lambda plan,host:hostemu.rows(host,'/etc/c3po-bar')),'THROWAWAY_PARENT_NOT_THE_FIXED_ONE'),
                (change(['journal_chain'],lambda plan,host:hostemu.rows(host,'/etc')),'THROWAWAY_PARENT_NOT_THE_FIXED_ONE'),
                (change(['journal_chain'],lambda plan,host:hostemu.rows(host,'/var')),'THROWAWAY_PARENT_NOT_THE_FIXED_ONE'),
                (change(['journal_chain'],lambda plan,host:hostemu.rows(host,host.tree.add('/var/lib/docker',mode=0o710) and '/var/lib/docker')),'THROWAWAY_PARENT_NOT_THE_FIXED_ONE'),
                (change(['journal_chain'],lambda plan,host:hostemu.rows(host,host.tree.add('/srv/k2a',mode=0o755) and '/srv/k2a')),'THROWAWAY_PARENT_NOT_THE_FIXED_ONE'),
                (change(['reference_chain'],lambda plan,host:hostemu.rows(host,'/etc/c3po-bar/manifests')),'REFERENCE_ROOT_NOT_A_LEAF_OF_THE_PRIVATE_PARENT'),
                (change(['reference_chain'],lambda plan,host:hostemu.rows(host,k2a.CONFIG)),'REFERENCE_ROOT_NOT_A_LEAF_OF_THE_PRIVATE_PARENT'),
                (change(['reference_chain'],lambda plan,host:hostemu.rows(host,k2a.PRIVATE_PARENT)),'REFERENCE_ROOT_NOT_A_LEAF_OF_THE_PRIVATE_PARENT'),
                (change(['reference_chain'],lambda plan,host:hostemu.rows(host,k2a.PRIVATE_PARENT+'/supervisor')),'REFERENCE_ROOT_IS_THE_STATE_ROOT')]
def test_plan_refusals_are_authentication_refusals_and_nothing_is_touched():
    seen=set()
    for mode,cases in (('REAL',BOTH+REAL_ONLY),('REHEARSAL',BOTH+REHEARSAL_ONLY)):
        for index,(apply,code) in enumerate(cases):
            m,docs,host=fresh(mode);apply(docs.plan,host);docs.chain()
            assert f.refusal(docs.authenticate)==code,(mode,index,code)
            receipt=docs.run(f.Untouchable());assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED',code,'AUTHENTICATION'),(mode,index)
            seen.add(code)
    assert seen>={'MODE_INVALID','EVIDENCE_BOOT_UNBOUND','SCRIPT_NOT_THE_PINNED_HASH','IMAGE_REVISION_UNBOUND','IMAGE_ID','CONTAINER_JOURNAL_ROOT_INVALID','CHAIN_ROW_INVALID',
                  'CHAIN_ROW_UNSAFE','DOCKER_CONFIG_NOT_PRIVATE','DOCKER_CONFIG_IS_A_MOUNT_POINT','EPOCH_NOT_THE_COMPILED_CONSTANT','MODE_MEMBERS_INVALID','JOURNAL_ROOT_NOT_PRIVATE',
                  'JOURNAL_ROOT_IS_A_MOUNT_POINT','EPOCH_NOT_A_DIAGNOSTIC_ONE','THROWAWAY_NAME_INVALID','REFERENCE_ROOT_NOT_PRIVATE','REFERENCE_ROOT_IS_A_MOUNT_POINT',
                  'PARENT_SETGID','REHEARSAL_NOT_ON_THE_FILESYSTEM_OF_THE_REAL_ROOT','DOCKER_CONFIG_NOT_THE_DIRECTORY_OF_THE_UNIT','JOURNAL_ROOT_NOT_A_LEAF_OF_THE_PRIVATE_PARENT',
                  'JOURNAL_ROOT_IS_THE_STATE_ROOT','THROWAWAY_PARENT_NOT_THE_FIXED_ONE','REFERENCE_ROOT_NOT_A_LEAF_OF_THE_PRIVATE_PARENT','REFERENCE_ROOT_IS_THE_STATE_ROOT'}

def test_every_forbidden_top_level_directory_of_the_readme_is_refused_as_container_path_and_a_new_one_is_accepted():
    for name in ('app','bin','boot','dev','etc','home','lib','lib64','media','mnt','opt','proc','root','run','sbin','srv','sys','tmp','usr','var'):
        m,docs,host=fresh();docs.plan['container_journal_root']='/'+name;docs.chain();assert f.refusal(docs.authenticate)=='CONTAINER_JOURNAL_ROOT_INVALID',name
    m,docs,host=fresh();docs.plan['container_journal_root']='/c3po-bar-journal-2';docs.chain();receipt=docs.run(host)
    assert receipt['status']==m.COMPLETE_STATUS and host.docker.runs[0].command[4]=='/c3po-bar-journal-2' and host.docker.runs[0].mounts[0]['target']=='/c3po-bar-journal-2'

def test_docker_config_path_is_the_one_of_the_unit_and_the_journal_path_must_fit_the_mount_grammar():
    m,docs,host=fresh();host.tree.add('/etc/c3po-bar/docker=cli',mode=0o700);docs.plan['docker_config_chain']=hostemu.rows(host,'/etc/c3po-bar/docker=cli');docs.chain()
    assert f.refusal(docs.authenticate)=='DOCKER_CONFIG_NOT_THE_DIRECTORY_OF_THE_UNIT'
    assert text_fits(m,'/var/lib/c3po-bar-rehearsal-'+'a'*40+'.docker-cli'),'the longest directory a rehearsal can give docker fits the variable'
    m,docs,host=fresh();host.tree.add('/var/lib/c3po-bar/jour=nal',mode=0o700);docs.plan['journal_chain']=hostemu.rows(host,'/var/lib/c3po-bar/jour=nal');docs.chain()
    assert f.refusal(docs.authenticate)=='MOUNT_INVALID'

def test_the_script_this_source_carries_is_the_only_one_and_a_changed_constant_refuses_everything(monkeypatch):
    m,docs,host=fresh();assert f.sha(m.script_bytes())==k2a.SCRIPT_SHA==m.CATALOG_SCRIPT_SHA256 and len(m.script_bytes())==1040
    assert 'script_b64' not in docs.plan and 'script' not in docs.plan,'no request can supply script bytes'
    import base64
    for other in (base64.b64encode(m.script_bytes()+b'\n').decode(),base64.b64encode(m.script_bytes()[:-1]+b' ').decode(),'not base64!'):
        monkeypatch.setattr(m,'CATALOG_SCRIPT_B64',other)
        assert f.refusal(m.script_bytes)=='SCRIPT_NOT_THE_PINNED_HASH' and f.refusal(docs.authenticate)=='SCRIPT_NOT_THE_PINNED_HASH'
        receipt=docs.run(f.Untouchable());assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','SCRIPT_NOT_THE_PINNED_HASH','AUTHENTICATION')
    monkeypatch.undo();assert docs.run(host)['status']==m.COMPLETE_STATUS


def test_validate_plan_refuses_by_itself_what_the_command_could_not_carry():
    """validate_plan alone, as the dispatcher's local authentication reaches it: the image, the bind and the words."""
    for mode in MODES:
        m,docs,host=fresh(mode);plan=json.loads(f.canonical(docs.plan));m.validate_plan(plan)
        for key,value,code in (('image_id','sha256:short','IMAGE_ID'),('image_id',hostemu.BACKEND.upper(),'IMAGE_ID')):
            assert f.refusal(lambda:m.validate_plan(dict(plan,**{key:value})))==code
    m,docs,host=fresh('REHEARSAL');plan=json.loads(f.canonical(docs.plan));long='/'+'/'.join(['abcdefghijklmnop']*11)                 # a clean path of 187 characters
    rows=[{'path':prefix,'device':801,'inode':index+2,'uid':0,'gid':0,'mode':0o755} for index,prefix in enumerate(m.prefixes(long))]
    reference=[dict(row,device=801) for row in plan['reference_chain']]
    assert f.refusal(lambda:m.validate_plan(dict(plan,journal_chain=rows,reference_chain=reference)))=='THROWAWAY_PARENT_NOT_THE_FIXED_ONE','a throwaway is created in /var/lib only'

def test_evidence_must_name_the_precheck_and_the_provisioning_the_rows_come_from():
    for mode in MODES:
        m,docs,host=fresh(mode);assert [item['operation'] for item in docs.request['evidence']]==['GO_READONLY_HOSTOPS_PRECHECK_01','GO_WRITE_SUPERVISOR_READER_PROVISION_01']
        for missing in (0,1):
            m,docs,host=fresh(mode);del docs.request['evidence'][missing];docs.chain()
            assert f.refusal(docs.authenticate)=='EVIDENCE_OPERATION_MISSING' and docs.run(f.Untouchable())['code']=='EVIDENCE_OPERATION_MISSING'
        m,docs,host=fresh(mode);docs.request['evidence']=[];docs.chain();assert f.refusal(docs.authenticate)=='EVIDENCE_UNBOUND'


# ---------------------------------------------------------------- the precheck: each finding is a refusal with nothing changed
def other_boot(host):node(host,'/proc/sys/kernel/random/boot_id').content=bytearray(b'1f8fad5b-d9cb-469f-a165-70867728950e\n')
def answer(host,words,code,out):
    """The engine answers one read in its own way."""
    original=host.docker.run
    def run(args,stdin=None,environment=None):
        if args[:len(words)]==words:return code,out
        return original(args,stdin,environment)
    host.docker.run=run
def foreign(path,kind='file',**attributes):return lambda host:host.tree.add(path,kind=kind,**attributes)
COMMON_PRECHECK=[
    (lambda host:setattr(host,'actor',(0,5)),'EXECUTOR_IDENTITY'),(lambda host:setattr(host,'actor',(1000,0)),'EXECUTOR_IDENTITY'),(other_boot,'EVIDENCE_FROM_EARLIER_BOOT'),
    (lambda host:setattr(host,'noatime_available',False),'NOATIME_UNAVAILABLE'),
    (lambda host:host.tree.remove(k2a.CONFIG),'PARENT_MISSING'),(lambda host:replace(host,k2a.CONFIG,'symlink',mode=0o777),'PARENT_SYMLINK_COMPONENT'),
    (lambda host:replace(host,k2a.CONFIG,'file',mode=0o700),'PARENT_NOT_DIRECTORY'),(lambda host:replace(host,k2a.CONFIG,'dir',mode=0o700),'PARENT_IDENTITY_MISMATCH'),
    (lambda host:setattr(node(host,k2a.CONFIG),'mode',0o755),'PARENT_IDENTITY_MISMATCH'),(lambda host:setattr(node(host,k2a.CONFIG),'uid',1000),'PARENT_IDENTITY_MISMATCH'),
    (lambda host:setattr(node(host,'/etc/c3po-bar'),'ino',99),'PARENT_IDENTITY_MISMATCH'),(lambda host:setattr(node(host,k2a.CONFIG),'dev',hostemu.DATA_DEVICE),'PARENT_IDENTITY_MISMATCH'),
    (foreign(k2a.CONFIG+'/config.json',mode=0o600),'DOCKER_CONFIG_DIRECTORY_NOT_EMPTY'),(foreign(k2a.CONFIG+'/contexts','dir'),'DOCKER_CONFIG_DIRECTORY_NOT_EMPTY'),
    (lambda host:host.tree.remove('/usr/bin/docker'),'BINARY_UNAVAILABLE_OR_UNSAFE'),(lambda host:setattr(node(host,'/usr/bin/docker'),'mode',0o775),'BINARY_UNAVAILABLE_OR_UNSAFE'),
    (lambda host:setattr(node(host,'/usr/bin/docker'),'uid',1000),'BINARY_UNAVAILABLE_OR_UNSAFE')]
# What only a docker command shows. REAL: the two reads are part of the precheck, under the directory of the unit, and
# each finding is a refusal with nothing changed. REHEARSAL: the reads run under the directory the run has just created
# for them, so each finding is a PARTIAL that leaves that one empty directory and has touched nothing of production.
DOCKER_PRECHECK=[
    (lambda host:host.docker.images.pop(0),'IMAGE_ABSENT_OR_UNREADABLE'),
    (lambda host:host.docker.images[0]['Config']['Labels'].update({'org.opencontainers.image.revision':'0'*40}),'IMAGE_REVISION_MISMATCH'),
    (lambda host:host.docker.images[0]['Config'].update(Labels={}),'IMAGE_REVISION_MISMATCH'),
    (lambda host:answer(host,['image','inspect'],0,f.canonical({'id':hostemu.OTHER,'repo_tags':[],'revision':hostemu.REVISION})+b'\n'),'IMAGE_ID_MISMATCH'),
    (lambda host:answer(host,['image','inspect'],0,f.canonical({'id':hostemu.BACKEND,'repo_tags':[]})+b'\n'),'IMAGE_METADATA_INVALID'),
    (lambda host:answer(host,['image','inspect'],0,b'not json\n'),'JSON_INVALID'),(lambda host:answer(host,['image','inspect'],0,b''),'DOCUMENT_SIZE'),
    (lambda host:answer(host,['image','inspect'],0,b'x'*70000),'COMMAND_OUTPUT_LIMIT'),
    (lambda host:setattr(host.docker,'ps_returncode',1),'CONTAINER_LISTING_FAILED'),
    (lambda host:answer(host,['ps','-a'],0,b'{"id":"short","name":"x","state":"running"}\n'),'CONTAINER_LIST_INVALID'),
    (lambda host:answer(host,['ps','-a'],0,b'garbage\n'),'JSON_INVALID'),
    (lambda host:host.hang.add('docker'),'COMMAND_TIMEOUT'),(lambda host:host.hang.add(('image','inspect')),'COMMAND_TIMEOUT'),(lambda host:host.hang.add(('ps','-a')),'COMMAND_TIMEOUT'),
    (lambda host:host.absent.add('docker'),'COMMAND_NOT_STARTED')]
REAL_PRECHECK=[
    (lambda host:host.tree.remove(k2a.JOURNAL),'PARENT_MISSING'),(lambda host:replace(host,k2a.JOURNAL,'symlink',mode=0o777),'PARENT_SYMLINK_COMPONENT'),
    (lambda host:replace(host,k2a.PRIVATE_PARENT,'symlink',mode=0o777),'PARENT_SYMLINK_COMPONENT'),
    (lambda host:replace(host,k2a.JOURNAL,'file',mode=0o700),'PARENT_NOT_DIRECTORY'),(lambda host:replace(host,k2a.JOURNAL,'fifo',mode=0o700),'PARENT_NOT_DIRECTORY'),
    (lambda host:replace(host,k2a.JOURNAL,'dir',mode=0o700),'PARENT_IDENTITY_MISMATCH'),(lambda host:setattr(node(host,k2a.JOURNAL),'uid',1000),'PARENT_IDENTITY_MISMATCH'),
    (lambda host:setattr(node(host,k2a.JOURNAL),'gid',1000),'PARENT_IDENTITY_MISMATCH'),(lambda host:setattr(node(host,k2a.JOURNAL),'mode',0o750),'PARENT_IDENTITY_MISMATCH'),
    (lambda host:setattr(node(host,k2a.JOURNAL),'dev',hostemu.DATA_DEVICE),'PARENT_IDENTITY_MISMATCH'),(lambda host:setattr(node(host,'/var/lib'),'mode',0o775),'PARENT_IDENTITY_MISMATCH'),
    (foreign(k2a.JOURNAL+'/producer.lock',mode=0o600),'JOURNAL_ROOT_NOT_EMPTY'),(foreign(k2a.JOURNAL+'/lost+found','dir',mode=0o700),'JOURNAL_ROOT_NOT_EMPTY'),
    (foreign(k2a.JOURNAL+'/maintenance.lock',mode=0o600),'JOURNAL_ROOT_NOT_EMPTY'),(foreign(k2a.JOURNAL+'/epoch.json',kind='symlink'),'JOURNAL_ROOT_NOT_EMPTY')]
REHEARSAL_PRECHECK=[
    (foreign(k2a.REHEARSAL_ROOT,'dir',mode=0o700),'DESTINATION_PRESENT'),(foreign(k2a.REHEARSAL_ROOT,mode=0o600),'DESTINATION_PRESENT'),(foreign(k2a.REHEARSAL_ROOT,'symlink'),'DESTINATION_PRESENT'),
    (foreign(k2a.REHEARSAL_CONFIG,'dir',mode=0o700),'DESTINATION_PRESENT'),(foreign(k2a.REHEARSAL_CONFIG,mode=0o600),'DESTINATION_PRESENT'),(foreign(k2a.REHEARSAL_CONFIG,'symlink'),'DESTINATION_PRESENT'),
    (lambda host:setattr(node(host,'/var/lib'),'ino',77),'PARENT_IDENTITY_MISMATCH'),(lambda host:setattr(node(host,'/var/lib'),'mode',0o2755),'PARENT_IDENTITY_MISMATCH'),
    (lambda host:replace(host,'/var/lib','symlink',mode=0o777),'PARENT_SYMLINK_COMPONENT'),
    (lambda host:host.tree.remove(k2a.JOURNAL),'PARENT_MISSING'),(lambda host:replace(host,k2a.JOURNAL,'symlink',mode=0o777),'PARENT_SYMLINK_COMPONENT'),
    (lambda host:setattr(node(host,k2a.JOURNAL),'ino',78),'PARENT_IDENTITY_MISMATCH'),(lambda host:setattr(node(host,k2a.JOURNAL),'mode',0o755),'PARENT_IDENTITY_MISMATCH'),
    (lambda host:setattr(node(host,k2a.JOURNAL),'dev',hostemu.DATA_DEVICE),'PARENT_IDENTITY_MISMATCH'),(lambda host:setattr(node(host,'/var/lib'),'dev',hostemu.DATA_DEVICE),'PARENT_IDENTITY_MISMATCH'),
    (foreign(k2a.JOURNAL+'/epoch.json',mode=0o600),'REFERENCE_ROOT_NOT_EMPTY'),(foreign(k2a.JOURNAL+'/anything','dir'),'REFERENCE_ROOT_NOT_EMPTY')]
BEFORE_DOCKER=('EXECUTOR_IDENTITY','EVIDENCE_FROM_EARLIER_BOOT','NOATIME_UNAVAILABLE','PARENT_MISSING','PARENT_SYMLINK_COMPONENT','PARENT_NOT_DIRECTORY','PARENT_IDENTITY_MISMATCH',
               'DOCKER_CONFIG_DIRECTORY_NOT_EMPTY','JOURNAL_ROOT_NOT_EMPTY','REFERENCE_ROOT_NOT_EMPTY','DESTINATION_PRESENT','BINARY_UNAVAILABLE_OR_UNSAFE')
def test_everything_the_precheck_finds_is_a_refusal_with_nothing_created_and_nothing_started():
    for mode,cases in (('REAL',COMMON_PRECHECK+DOCKER_PRECHECK+REAL_PRECHECK),('REHEARSAL',COMMON_PRECHECK+REHEARSAL_PRECHECK)):
        for index,(prepare,code) in enumerate(cases):
            m,docs,host=fresh(mode);prepare(host);before=k2a.state_of(host);receipt=docs.run(host)
            refused(receipt,code);assert receipt['mode']==mode,(mode,index)
            assert k2a.state_of(host)==before and host.mutating()==[] and host.container_runs()==[] and host.fds=={},(mode,index,code)
            assert receipt['mutating_calls']['issued']==0 and receipt['run'] is None and receipt['catalog'] is None and receipt['journal_root'] is None
            if code in BEFORE_DOCKER or mode=='REHEARSAL':assert host.commands==[],(mode,index,code,'found on the file system before any docker command is started')
            else:assert (host.commands or code=='COMMAND_NOT_STARTED') and all(entry['docker_config']==k2a.CONFIG for entry in host.commands)
    assert {code for _,code in COMMON_PRECHECK+REAL_PRECHECK+REHEARSAL_PRECHECK}<=set(BEFORE_DOCKER) and not {code for _,code in DOCKER_PRECHECK}&set(BEFORE_DOCKER)

def test_what_a_docker_read_of_a_rehearsal_finds_is_a_partial_that_touched_nothing_of_production():
    """REHEARSAL: the image and the first listing are read under the directory the run has just created, never under
    the directory of the unit. A finding there leaves that one empty directory: the throwaway name is spent, the
    throwaway root was not created, no container was started, and production is as it was."""
    for index,(prepare,code) in enumerate(DOCKER_PRECHECK):
        m,docs,host=fresh('REHEARSAL');prepare(host);before=host.tree.snapshot();engine=k2a.state_of(host)[1:];receipt=docs.run(host)
        partial(receipt,code);assert receipt['mode']=='REHEARSAL' and receipt['run'] is None and receipt['catalog'] is None and receipt['journal_root'] is None,(index,code)
        assert [(row['key'],row['state']) for row in receipt['directories']]==[('DOCKER_CONFIG','CREATED_DURABLE')] and receipt['objects_left_by_this_run']==1,(index,code)
        assert receipt['mutating_calls']=={'issued':1,'succeeded':1,'failed_nothing_changed':0,'uncertain':0} and receipt['pre_existing_objects_modified'] is False
        assert node(host,k2a.REHEARSAL_ROOT) is None and names(host,k2a.REHEARSAL_CONFIG)==[] and names(host,k2a.JOURNAL)==[] and names(host,k2a.CONFIG)==[]
        assert host.container_runs()==[] and k2a.state_of(host)[1:]==engine and host.fds=={},(index,code)
        assert all(entry['docker_config']==k2a.REHEARSAL_CONFIG for entry in host.commands),'no docker command under the directory of the unit'
        assert [entry[:2] for entry in host.log if entry[0] in hostemu.MUTATING]==[('mkdir',k2a.REHEARSAL_CONFIG)]
        host.tree.remove(k2a.REHEARSAL_CONFIG);assert host.tree.snapshot()==before,(index,code)

def test_a_refusal_for_a_directory_that_differs_carries_the_rows_as_they_were_read():
    m,docs,host=fresh();node(host,k2a.JOURNAL).mode=0o750;node(host,k2a.JOURNAL).uid=1000;receipt=docs.run(host);refused(receipt,'PARENT_IDENTITY_MISMATCH')
    seen=receipt['observed_rows']['journal'];assert [row['path'] for row in seen]==['/','/var','/var/lib','/var/lib/c3po-bar',k2a.JOURNAL]
    assert (seen[-1]['mode'],seen[-1]['uid'])==(0o750,1000) and seen[:-1]==docs.plan['journal_chain'][:-1] and receipt['observed_rows']['docker_config']==docs.plan['docker_config_chain']
    m,docs,host=fresh('REHEARSAL');node(host,k2a.JOURNAL).ino=4242;receipt=docs.run(host);refused(receipt,'PARENT_IDENTITY_MISMATCH')
    assert receipt['observed_rows']['reference'][-1]['inode']==4242 and receipt['observed_rows']['journal']==[],'the walk stopped at the real root; the parent was not reached'

def test_a_failing_system_call_or_any_other_failure_of_the_precheck_is_a_refusal_with_its_own_code():
    for kind,code in ((OSError,'PRECHECK_OS_ERROR'),(RuntimeError,'PRECHECK_FAILED')):
        for mode in MODES:
            m,docs,host=fresh(mode)
            def hook(host,name,detail,calls,kind=kind):
                if name=='names':raise kind(5,'injected') if kind is OSError else kind('injected')
            host.hook=hook;before=k2a.state_of(host);receipt=docs.run(host)
            refused(receipt,code);assert k2a.state_of(host)==before and host.commands==[] and 'injected' not in json.dumps(receipt)

def test_a_rehearsal_whose_parent_is_not_on_the_device_it_was_signed_with_is_refused_whatever_the_walk_of_the_real_root_saw():
    """The private parent is a mount point: the real root is on another device than /var/lib. A request that signs the
    rows of /var/lib with the device of the real root passes the plan (the two chains are compared at their ends), and
    the walk of the real root accepts /var/lib with its true device. The walk of the parent itself must then refuse:
    the throwaway would not be on the filesystem of the real root."""
    k,host=k2a.world();node(host,k2a.PRIVATE_PARENT).dev=hostemu.DATA_DEVICE;node(host,k2a.JOURNAL).dev=hostemu.DATA_DEVICE
    fields=k2a.rehearsal_fields(host);assert fields['reference_chain'][2]['device']==hostemu.ROOT_DEVICE!=fields['reference_chain'][-1]['device']
    fields['journal_chain'][-1]['device']=hostemu.DATA_DEVICE;docs=f.Docs(k,fields);assert docs.authenticate()
    before=k2a.state_of(host);receipt=docs.run(host)
    refused(receipt,'PARENT_IDENTITY_MISMATCH');assert k2a.state_of(host)==before and host.commands==[] and receipt['observed_rows']['journal'][-1]['device']==hostemu.ROOT_DEVICE
    # and a private parent that is a mount point is by itself no obstacle when the throwaway's parent is on the same device
    k,host=k2a.world()
    for path in ('/var/lib',k2a.PRIVATE_PARENT,k2a.JOURNAL):node(host,path).dev=hostemu.DATA_DEVICE
    host.vfs[hostemu.DATA_DEVICE]=host.vfs.get(hostemu.DATA_DEVICE,host.vfs[hostemu.ROOT_DEVICE]);host.docker.on_run=k2a.container
    receipt=f.Docs(k,k2a.rehearsal_fields(host)).run(host);assert receipt['status']==k.m.COMPLETE_STATUS and node(host,k2a.REHEARSAL_ROOT).dev==hostemu.DATA_DEVICE

@pytest.mark.parametrize('mode',MODES)
def test_a_docker_read_that_fails_as_a_call_and_not_as_a_command_has_a_code_of_its_own(mode):
    """REAL: still the precheck, a refusal. REHEARSAL: after its first directory, a partial; the unit is not touched."""
    for kind,suffix in ((OSError,'OS_ERROR'),(RuntimeError,'FAILED')):
        for words in (['image','inspect'],['ps','-a']):
            m,docs,host=fresh(mode)
            def hook(host,name,detail,calls,kind=kind,words=words):
                if name=='run' and detail[0][1:3]==words:raise kind(5,'injected') if kind is OSError else kind('injected')
            host.hook=hook;receipt=docs.run(host);assert 'injected' not in json.dumps(receipt) and host.container_runs()==[] and host.fds=={}
            if mode=='REAL':
                refused(receipt,'PRECHECK_'+suffix);assert host.mutating()==[]
            else:
                partial(receipt,'READS_'+suffix);assert [entry[:2] for entry in host.mutating()]==[('mkdir',k2a.REHEARSAL_CONFIG)] and node(host,k2a.REHEARSAL_ROOT) is None
                assert names(host,k2a.CONFIG)==[] and all(entry['docker_config']==k2a.REHEARSAL_CONFIG for entry in host.commands)

def test_a_refusal_leaves_the_real_root_usable_under_a_new_request():
    m,docs,host=fresh();removed=host.docker.images.pop(0);refused(docs.run(host),'IMAGE_ABSENT_OR_UNREADABLE')
    host.docker.images.insert(0,removed);again=f.Docs(docs.k,copy.deepcopy({key:docs.plan[key] for key in m.PLAN_KEYS}));receipt=again.run(host)
    assert receipt['status']==m.COMPLETE_STATUS and names(host,k2a.JOURNAL)==k2a.NAMES

@pytest.mark.parametrize('mode',MODES)
def test_the_last_look_before_the_effect_sees_what_changed_after_the_first(mode):
    """Something appears, or a held directory is replaced, while the two docker reads run: found by the last look."""
    def during_the_listing(action):
        def hook(host,name,detail,calls):
            if name=='run' and detail[0][1:3]==['ps','-a'] and not getattr(host,'_done',False):host._done=True;action(host)
        return hook
    target=k2a.JOURNAL;given=k2a.config_of(mode)
    # what the docker CLI left in the directory it was given is found here, under its own code: in a rehearsal that
    # directory is the run's own, so the finding costs a throwaway and nothing of the unit
    cases=[(foreign(given+'/config.json',mode=0o600),'DOCKER_CONFIG_DIRECTORY_NOT_EMPTY_AFTER_THE_READS'),(lambda host:setattr(node(host,k2a.CONFIG),'ino',91),'PARENT_REPLACED'),
           (lambda host:setattr(node(host,target),'mode',0o755),'PARENT_REPLACED'),(lambda host:replace(host,target,'dir',mode=0o700),'PARENT_REPLACED'),
           (lambda host:setattr(node(host,'/etc'),'dev',hostemu.DATA_DEVICE),'PARENT_REPLACED')]          # an ancestor now on another device: the way from "/" is not the signed one
    cases+=[(foreign(target+'/producer.lock',mode=0o600),'JOURNAL_ROOT_NOT_EMPTY')] if mode=='REAL' else [
        (lambda host:setattr(node(host,'/var/lib'),'ino',92),'PARENT_REPLACED'),(lambda host:setattr(node(host,given),'mode',0o755),'PARENT_REPLACED'),
        (lambda host:replace(host,given,'dir',mode=0o700),'PARENT_REPLACED')]
    for action,code in cases:
        m,docs,host=fresh(mode);host.hook=during_the_listing(action);receipt=docs.run(host)
        assert host.container_runs()==[] and host.fds=={} and node(host,k2a.REHEARSAL_ROOT) is None,code
        if mode=='REAL' and code.startswith('DOCKER_CONFIG'):
            # the directory of the unit changed while the reads ran under it: never "refused, nothing changed"; the root is untouched
            assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'],receipt['root_verdict'])==(PARTIAL,'PARTIAL_SEE_ROOT_VERDICT',code,'PRECHECK','UNTOUCHED_NO_CONTAINER_STARTED')
            assert receipt['precheck']['docker_config_entries']==0 and receipt['precheck']['docker_config_entries_after_the_reads']==1 and receipt['commands_started']['READ']==2
            assert host.mutating()==[] and receipt['mutating_calls']['issued']==0 and names(host,k2a.JOURNAL)==[]
        elif mode=='REAL':
            refused(receipt,code);assert host.mutating()==[] and receipt['precheck']['docker_config_entries_after_the_reads']==0
        else:
            partial(receipt,code);assert [entry[:2] for entry in host.mutating()]==[('mkdir',k2a.REHEARSAL_CONFIG)] and names(host,k2a.CONFIG)==[] and names(host,k2a.JOURNAL)==[]


# ---------------------------------------------------------------- the budget
def timed(mode='REAL',seconds=0.0):
    m,docs,host=fresh(mode);budget=f.Budget(docs.now,seconds).attach(host);return m,docs,host,budget

def test_run_refuses_before_the_first_effect_when_the_class_of_the_run_and_its_reserve_do_not_fit():
    """REAL needs 40 + 4 s after its two reads. REHEARSAL needs 2 s more, for its directories, before it creates the
    first one: time lost before that point (here: at the umask call) is a refusal with nothing created."""
    for mode,slow,code in (('REAL',16.0,None),('REAL',16.5,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT'),('REHEARSAL',14.0,None),('REHEARSAL',14.5,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')):
        m,docs,host,budget=timed(mode);before=k2a.state_of(host)
        if mode=='REAL':budget.cost(slow,'image','inspect')
        else:
            previous=host.hook
            def hook(host,name,detail,calls,slow=slow,previous=previous):
                if name=='umask':budget.elapsed+=slow
                previous(host,name,detail,calls)
            host.hook=hook
        receipt=docs.run(host,**budget.options())
        if code is None:assert receipt['status']==m.COMPLETE_STATUS,(mode,slow)
        else:
            refused(receipt,code);assert k2a.state_of(host)==before and host.mutating()==[] and host.container_runs()==[]
            if mode=='REHEARSAL':assert host.commands==[]

def test_slow_reads_of_a_rehearsal_leave_a_run_that_is_not_started():
    """REHEARSAL: the reads come after the first directory, so the time they take cannot be a refusal any more. A run
    that no longer fits is not started (the core's own check): PARTIAL, the two empty throwaway directories stay."""
    for slow,fits in ((16.0,True),(16.5,False)):
        m,docs,host,budget=timed('REHEARSAL');budget.cost(slow,'image','inspect');receipt=docs.run(host,**budget.options())
        if fits:
            assert receipt['status']==m.COMPLETE_STATUS;continue
        partial(receipt,'COMMAND_NOT_STARTED_BUDGET');assert host.container_runs()==[] and names(host,k2a.REHEARSAL_ROOT)==[] and names(host,k2a.REHEARSAL_CONFIG)==[]
        assert receipt['mutating_calls']=={'issued':3,'succeeded':2,'failed_nothing_changed':1,'uncertain':0} and receipt['objects_left_by_this_run']==2 and names(host,k2a.JOURNAL)==[]

def test_a_run_that_does_not_fit_any_more_when_it_is_started_is_not_started():
    """Time passes between the budget check and the start (here: a slow fsync of the rehearsal's directory). The
    container is not started. REHEARSAL: the empty throwaway exists, so the run is a partial."""
    m,docs,host,budget=timed('REHEARSAL')
    previous=host.hook
    def hook(host,name,detail,calls):
        if name=='fsync':budget.elapsed+=4.5                    # four fsyncs: 18 s in all
        previous(host,name,detail,calls)
    host.hook=hook;receipt=docs.run(host,**budget.options())
    partial(receipt,'COMMAND_NOT_STARTED_BUDGET');assert receipt['run']=={'state':'NOT_STARTED','code':'COMMAND_NOT_STARTED_BUDGET','returncode':None,'seconds':0.0}
    assert host.container_runs()==[] and names(host,k2a.REHEARSAL_ROOT)==[] and receipt['mutating_calls']=={'issued':3,'succeeded':2,'failed_nothing_changed':1,'uncertain':0}
    assert receipt['catalog'] is None and receipt['objects_left_by_this_run']==2

def test_the_run_gets_the_whole_class_and_the_readback_runs_in_what_is_left():
    m,docs,host,budget=timed('REAL',0.5);budget.cost(39.0,'run','--rm');receipt=docs.run(host,**budget.options())
    assert receipt['status']==m.COMPLETE_STATUS and receipt['run']['seconds']==39.0 and receipt['clock']['monotonic_elapsed_ms']==40500


# ---------------------------------------------------------------- the container is not started, times out, or cannot be run
@pytest.mark.parametrize('mode',MODES)
def test_a_run_that_was_never_started_changed_nothing_by_itself(mode):
    m,docs,host=fresh(mode);host.absent.add(('run','--rm'));before=k2a.state_of(host);receipt=docs.run(host)
    assert receipt['run']=={'state':'NOT_STARTED','code':'COMMAND_NOT_STARTED','returncode':None,'seconds':0} and host.container_runs()==[] and receipt['catalog'] is None
    if mode=='REAL':
        refused(receipt,'COMMAND_NOT_STARTED','EFFECTS');assert k2a.state_of(host)==before and receipt['mutating_calls']=={'issued':1,'succeeded':0,'failed_nothing_changed':1,'uncertain':0}
    else:
        partial(receipt,'COMMAND_NOT_STARTED');assert names(host,k2a.REHEARSAL_ROOT)==[] and receipt['objects_left_by_this_run']==2 and names(host,k2a.JOURNAL)==[]

@pytest.mark.parametrize('mode',MODES)
def test_a_timeout_is_never_a_refusal_whatever_the_container_did(mode):
    root=k2a.root_of(mode)
    for group,entries in (('hang',0),('hang_after',2)):
        m,docs,host=fresh(mode);getattr(host,group).add(('run','--rm'));receipt=docs.run(host)
        partial(receipt,'COMMAND_TIMEOUT');assert receipt['run']['state']=='DID_NOT_RETURN' and receipt['run']['returncode'] is None
        assert receipt['mutating_calls']['uncertain']==1 and receipt['catalog']['entries']==entries==len(names(host,root)) and receipt['script_line']['one_json_line'] is False
        assert receipt['containers']['status']=='COMPLETE' and receipt['objects_left_by_this_run']==entries+(2 if mode=='REHEARSAL' else 0),'the readback and the listing still run'
        if entries:assert receipt['catalog']['epoch_json']['equal_to_the_expected_bytes'] is True,'a complete catalog on disk without the line of the run is still not a verified run'

def test_output_beyond_the_limit_and_an_expiry_during_the_run_are_uncertain():
    m,docs,host=fresh();host.docker.on_run=then(lambda call,result:(0,b'x'*70000));receipt=docs.run(host)
    partial(receipt,'COMMAND_OUTPUT_LIMIT');assert receipt['run']['state']=='DID_NOT_RETURN' and receipt['catalog']['entries']==2
    m,docs,host=fresh();wall=[docs.now]
    host.docker.on_run=then(lambda call,result:wall.__setitem__(0,docs.now+timedelta(minutes=6)))            # the GO window ends while the container runs
    receipt=docs.run(host,clock=lambda:wall[0])
    partial(receipt,'CATALOG_READBACK_UNAVAILABLE');assert receipt['catalog']['code']=='GO_EXPIRED' and receipt['containers']['code']=='GO_EXPIRED' and names(host,k2a.JOURNAL)==k2a.NAMES
    assert receipt['catalog']['entries'] is None and receipt['catalog']['files']=={},'after the expiry nothing more is read from the root: not even its names'
    assert receipt['mutating_calls']['uncertain']==1 and receipt['docker_config']['code']=='GO_EXPIRED' and receipt['clock'] is not None

@pytest.mark.parametrize('mode',MODES)
def test_an_engine_that_could_not_run_the_container_still_spends_the_root(mode):
    """125, 126, 127: the script never ran and the root is empty. By the README's rule that is not a refusal."""
    for status in (125,126,127):
        m,docs,host=fresh(mode);host.docker.on_run=lambda call:(status,b'');receipt=docs.run(host)
        partial(receipt,'ENGINE_COULD_NOT_RUN_THE_CONTAINER');assert receipt['run']=={'state':'RETURNED','code':None,'returncode':status,'seconds':0}
        assert receipt['catalog']['entries']==0 and receipt['catalog']['status']=='COMPLETE' and receipt['mutating_calls']['uncertain']==1 and receipt['mutating_calls']['failed_nothing_changed']==0
    m,docs,host=fresh(mode);host.docker.images[0]['Id']=hostemu.OTHER;answer(host,['image','inspect'],0,f.canonical({'id':hostemu.BACKEND,'repo_tags':[],'revision':hostemu.REVISION})+b'\n')
    receipt=docs.run(host);partial(receipt,'ENGINE_COULD_NOT_RUN_THE_CONTAINER');assert receipt['run']['returncode']==125,'the emulated engine itself: the image is not there by ID'


# ---------------------------------------------------------------- what the container says: hostile answers
def drop(*keys):return lambda call,result:line_of(result,**{key:k2a for key in keys})
def altered(**changes):return lambda call,result:line_of(result,**changes)
def status(code):return lambda call,result:(code,result[1])
ANSWERS=[
    (lambda call,result:(137,b''),'SCRIPT_OUTPUT_NOT_ONE_LINE'),(lambda call,result:(0,b''),'SCRIPT_OUTPUT_NOT_ONE_LINE'),(lambda call,result:(0,result[1]*2),'SCRIPT_OUTPUT_NOT_ONE_LINE'),
    (lambda call,result:(0,result[1][:-1]),'SCRIPT_OUTPUT_NOT_ONE_LINE'),(lambda call,result:(0,b'warning\n'+result[1]),'SCRIPT_OUTPUT_NOT_ONE_LINE'),
    (lambda call,result:(0,b'["CATALOG_READY"]\n'),'SCRIPT_OUTPUT_NOT_ONE_LINE'),(lambda call,result:(0,b'{"status":"CATALOG_READY","status":"CATALOG_READY"}\n'),'SCRIPT_OUTPUT_NOT_ONE_LINE'),
    (lambda call,result:(0,b'{"status":NaN}\n'),'SCRIPT_OUTPUT_NOT_ONE_LINE'),(lambda call,result:(0,b'\n'),'SCRIPT_OUTPUT_NOT_ONE_LINE'),
    (lambda call,result:(1,b'{"code": "MASSIVE_SESSION_ROOT_OWNER", "status": "CATALOG_REFUSED"}\n'),'SCRIPT_REFUSED'),
    (lambda call,result:(0,b'{"code": "MASSIVE_MAINTENANCE_BUSY", "status": "CATALOG_REFUSED"}\n'),'SCRIPT_REFUSED'),
    (status(1),'SCRIPT_FAILED'),(status(3),'SCRIPT_FAILED'),(status(-9),'SCRIPT_FAILED'),
    (altered(status='READY'),'SCRIPT_LINE_NOT_AS_SIGNED'),(altered(status=None),'SCRIPT_LINE_NOT_AS_SIGNED'),(altered(status=['CATALOG_READY']),'SCRIPT_LINE_NOT_AS_SIGNED'),
    (altered(created=False),'SCRIPT_LINE_NOT_AS_SIGNED'),(altered(created=1),'SCRIPT_LINE_NOT_AS_SIGNED'),(altered(epoch='R2D2-V2-SHADOW-2026-10-06'),'SCRIPT_LINE_NOT_AS_SIGNED'),
    (altered(epoch=None),'SCRIPT_LINE_NOT_AS_SIGNED'),(altered(entries=['epoch.json']),'SCRIPT_LINE_NOT_AS_SIGNED'),(altered(entries=['epoch.json','maintenance.lock','x']),'SCRIPT_LINE_NOT_AS_SIGNED'),
    (altered(entries=['maintenance.lock','epoch.json']),'SCRIPT_LINE_NOT_AS_SIGNED'),(altered(extra=1),'SCRIPT_LINE_NOT_AS_SIGNED'),(drop('entries'),'SCRIPT_LINE_NOT_AS_SIGNED'),
    (drop('device'),'SCRIPT_LINE_NOT_AS_SIGNED'),(altered(device='801'),'SCRIPT_LINE_NOT_AS_SIGNED'),(altered(device=True),'SCRIPT_LINE_NOT_AS_SIGNED'),
    (altered(device=-1),'SCRIPT_LINE_NOT_AS_SIGNED'),(altered(inode=0),'SCRIPT_LINE_NOT_AS_SIGNED'),(altered(inode=1.5),'SCRIPT_LINE_NOT_AS_SIGNED'),
    (altered(device=hostemu.DATA_DEVICE),'CATALOG_IDENTITY_NOT_THE_HOSTS'),(altered(inode=7),'CATALOG_IDENTITY_NOT_THE_HOSTS')]
@pytest.mark.parametrize('mode',MODES)
def test_anything_but_the_expected_line_after_a_started_run_is_partial_and_never_a_refusal(mode):
    for index,(behaviour,code) in enumerate(ANSWERS):
        m,docs,host=fresh(mode);host.docker.on_run=then(behaviour);receipt=docs.run(host)
        partial(receipt,code);assert receipt['run']['state']=='RETURNED',(index,code)
        assert receipt['mutating_calls']['uncertain']==1 and receipt['mutating_calls']['failed_nothing_changed']==0 and receipt['catalog']['entries']==2,index
        assert receipt['catalog']['epoch_json']['equal_to_the_expected_bytes'] is True,'what is on disk is still reported as it is'
        invariants(mode,host)

def test_a_refusal_of_the_script_is_reported_with_its_constant_code_and_never_with_raw_text():
    def crowded(call):
        call.write(call.command[4]+'/producer.lock',b'');return k2a.catalog_model(call,call.command[4:])       # appeared after the last look
    m,docs,host=fresh();host.docker.on_run=crowded;receipt=docs.run(host)
    partial(receipt,'SCRIPT_REFUSED');line=receipt['script_line']
    assert (line['status'],line['refusal_code'],line['returncode'],line['created'])==('CATALOG_REFUSED','CATALOG_INIT_ROOT_NOT_EMPTY',1,None)
    assert receipt['catalog']['entries']==1 and receipt['catalog']['other_entries']==1 and receipt['catalog']['files']=={'epoch.json':{'exists':False},'maintenance.lock':{'exists':False}}
    assert b'producer.lock' not in f.line(receipt),'a name that is not one of the two is counted, never printed'
    # the known wart of the pinned script: the text of whatever exception it caught
    message='not enough values to unpack (expected 2, got 1)'
    m,docs,host=fresh();host.docker.on_run=lambda call:(1,(json.dumps({'status':'CATALOG_REFUSED','code':message},sort_keys=True)+'\n').encode());receipt=docs.run(host)
    partial(receipt,'SCRIPT_REFUSED');assert receipt['script_line']['refusal_code']=='NOT_A_CONSTANT_CODE' and message.encode() not in f.line(receipt)
    for code in (None,5,'lower_case','A'*81,['X']):
        m,docs,host=fresh();host.docker.on_run=lambda call:(1,(json.dumps({'status':'CATALOG_REFUSED','code':code})+'\n').encode());receipt=docs.run(host)
        partial(receipt,'SCRIPT_REFUSED');assert receipt['script_line']['refusal_code']=='NOT_A_CONSTANT_CODE'


# ---------------------------------------------------------------- what the container leaves: hostile states of the file system
def edit(name,**attributes):
    def apply(call,result):
        target=call.node(call.command[4]+'/'+name)
        for key,value in attributes.items():setattr(target,key,bytearray(value) if key=='content' else value)
    return apply
def swap(name,kind,**attributes):
    def apply(call,result):
        root=call.node(call.command[4]);old=root.children.pop(name);root.children[name]=hostemu.Node(kind,dev=old.dev,ino=old.ino+1000,**attributes)
    return apply
def add(name,kind='file',**attributes):
    def apply(call,result):
        root=call.node(call.command[4]);root.children[name]=hostemu.Node(kind,dev=root.dev,ino=root.ino+2000,**attributes)
    return apply
def remove(name):return lambda call,result:call.node(call.command[4]).children.pop(name) and None
def rewritten(transform):
    def apply(call,result):
        target=call.node(call.command[4]+'/epoch.json');target.content=bytearray(transform(json.loads(bytes(target.content))))
    return apply
def with_member(**changes):return rewritten(lambda value:f.canonical(dict(value,**changes)))
STATES=[
    (add('producer.lock',mode=0o600),'CATALOG_READBACK_MISMATCH'),(add('session_date=2026-10-05','dir',mode=0o700),'CATALOG_READBACK_MISMATCH'),
    (remove('maintenance.lock'),'CATALOG_READBACK_MISMATCH'),(remove('epoch.json'),'CATALOG_READBACK_MISMATCH'),
    (swap('epoch.json','symlink',mode=0o777),'CATALOG_READBACK_MISMATCH'),(swap('epoch.json','dir',mode=0o700),'CATALOG_READBACK_MISMATCH'),
    (swap('epoch.json','fifo',mode=0o600),'CATALOG_READBACK_MISMATCH'),(swap('maintenance.lock','symlink',mode=0o777),'CATALOG_READBACK_MISMATCH'),
    (swap('maintenance.lock','dir',mode=0o700),'CATALOG_READBACK_MISMATCH'),(swap('maintenance.lock','fifo',mode=0o600),'CATALOG_READBACK_MISMATCH'),
    (edit('epoch.json',mode=0o644),'CATALOG_READBACK_MISMATCH'),(edit('epoch.json',mode=0o400),'CATALOG_READBACK_MISMATCH'),(edit('epoch.json',uid=1000),'CATALOG_READBACK_MISMATCH'),
    (edit('epoch.json',gid=1000),'CATALOG_READBACK_MISMATCH'),(edit('epoch.json',nlink=2),'CATALOG_READBACK_MISMATCH'),(edit('epoch.json',dev=hostemu.DATA_DEVICE),'CATALOG_READBACK_MISMATCH'),
    (edit('maintenance.lock',mode=0o640),'CATALOG_READBACK_MISMATCH'),(edit('maintenance.lock',mode=0o700),'CATALOG_READBACK_MISMATCH'),(edit('maintenance.lock',uid=1000),'CATALOG_READBACK_MISMATCH'),
    (edit('maintenance.lock',gid=7),'CATALOG_READBACK_MISMATCH'),(edit('maintenance.lock',nlink=2),'CATALOG_READBACK_MISMATCH'),(edit('maintenance.lock',dev=hostemu.DATA_DEVICE),'CATALOG_READBACK_MISMATCH'),
    (with_member(epoch='R2D2-V2-SHADOW-2026-10-06'),'CATALOG_READBACK_MISMATCH'),(with_member(device=1),'CATALOG_READBACK_MISMATCH'),(with_member(inode=1),'CATALOG_READBACK_MISMATCH'),
    (with_member(schema='MASSIVE_SESSION_ROOT_V2'),'CATALOG_READBACK_MISMATCH'),(with_member(extra=1),'CATALOG_READBACK_MISMATCH'),
    (rewritten(lambda value:json.dumps(value,sort_keys=True).encode()),'CATALOG_READBACK_MISMATCH'),(rewritten(lambda value:f.canonical(value)+b'\n'),'CATALOG_READBACK_MISMATCH'),
    (rewritten(lambda value:b''),'CATALOG_READBACK_MISMATCH'),(rewritten(lambda value:f.canonical(value)[:40]),'CATALOG_READBACK_MISMATCH'),
    (rewritten(lambda value:b' '*5000),'CATALOG_READBACK_UNAVAILABLE'),
    (lambda call,result:setattr(call.node(call.command[4]),'mode',0o755),'CATALOG_READBACK_UNAVAILABLE'),(lambda call,result:setattr(call.node(call.command[4]),'uid',1000),'CATALOG_READBACK_UNAVAILABLE'),
    (lambda call,result:[call.node(call.command[4]).children.__setitem__('f%d'%index,hostemu.Node('file',mode=0o600)) for index in range(70)] and None,'CATALOG_READBACK_UNAVAILABLE')]
@pytest.mark.parametrize('mode',MODES)
def test_a_root_that_is_not_exactly_the_catalog_of_the_application_is_not_verified_whatever_the_line_says(mode):
    """The container prints the expected line and exits 0; what is on disk differs in one respect."""
    for index,(behaviour,code) in enumerate(STATES):
        m,docs,host=fresh(mode);host.docker.on_run=then(behaviour);receipt=docs.run(host)
        partial(receipt,code);assert receipt['script_line']['status']=='CATALOG_READY' and receipt['mutating_calls']['uncertain']==1,index
        assert (receipt['catalog']['status']=='COMPLETE')==(code=='CATALOG_READBACK_MISMATCH'),index
        assert b'session_date' not in f.line(receipt);invariants(mode,host)

def test_epoch_json_exchanged_between_the_look_at_its_metadata_and_the_read_is_not_verified():
    """The file whose bytes are compared must be the file whose owner, mode and links were taken."""
    m,docs,host=fresh()
    def hook(host,name,detail,calls):
        if name=='lstat' and detail[0]==k2a.JOURNAL+'/maintenance.lock':
            root=node(host,k2a.JOURNAL);old=root.children['epoch.json']
            root.children['epoch.json']=hostemu.Node('file',mode=0o600,dev=old.dev,ino=old.ino+900,content=bytes(old.content))          # same bytes, another file
    host.hook=hook;receipt=docs.run(host)
    partial(receipt,'CATALOG_READBACK_UNAVAILABLE');assert receipt['catalog']['code']=='FILE_CHANGED_DURING_READ' and receipt['catalog']['epoch_json'] is None

@pytest.mark.parametrize('mode',MODES)
def test_a_root_that_was_replaced_at_its_path_during_the_run_is_not_verified(mode):
    path=k2a.root_of(mode)
    def moved_away(call,result):
        parent=call.docker.host.tree.get(path.rsplit('/',1)[0]);old=parent.children.pop(path.rsplit('/',1)[1])
        parent.children[path.rsplit('/',1)[1]]=hostemu.Node('dir',mode=0o700,dev=old.dev,ino=old.ino+500)                 # another empty private directory at the path
    m,docs,host=fresh(mode);host.docker.on_run=then(moved_away);receipt=docs.run(host)
    partial(receipt,'CATALOG_READBACK_UNAVAILABLE');assert receipt['catalog']['code']=='PARENT_REPLACED' and receipt['catalog']['root_unchanged'] is False
    assert receipt['catalog']['entries']==2 and receipt['catalog']['epoch_json']['equal_to_the_expected_bytes'] is True,'the held descriptor still shows what the container wrote'

@pytest.mark.parametrize('mode',MODES)
def test_a_readback_that_fails_is_unavailable_with_its_own_code_and_the_run_is_not_verified(mode):
    for kind,code in ((OSError,'READBACK_OS_ERROR'),(RuntimeError,'READBACK_FAILED')):
        m,docs,host=fresh(mode);armed=[]
        def hook(host,name,detail,calls,kind=kind):
            if name=='run' and detail[0][1]=='run':armed.append(True)
            elif armed and name=='lstat' and detail[0].endswith('/epoch.json'):raise kind(5,'injected') if kind is OSError else kind('injected')
        host.hook=hook;receipt=docs.run(host)
        partial(receipt,'CATALOG_READBACK_UNAVAILABLE');assert receipt['catalog']['code']==code and receipt['catalog']['status']=='UNAVAILABLE' and receipt['catalog']['entries']==2
        assert receipt['mutating_calls']['uncertain']==1 and 'injected' not in json.dumps(receipt);invariants(mode,host)

def test_the_readback_reads_epoch_json_only_and_never_opens_the_lock_file():
    m,docs,host=fresh();docs.run(host)
    opened=[entry[1] for entry in host.log if entry[0]=='open' and entry[1].startswith(k2a.JOURNAL+'/')];assert opened==[k2a.JOURNAL+'/epoch.json']
    read=[entry[1] for entry in host.log if entry[0]=='read'];assert sorted(set(read))==['/proc/sys/kernel/random/boot_id',k2a.JOURNAL+'/epoch.json']

@pytest.mark.parametrize('mode',MODES)
def test_a_container_killed_part_way_leaves_states_the_receipt_tells_apart(mode):
    def lock_only(call):
        call.write(call.command[4]+'/maintenance.lock',b'');return 137,b''
    def torn(call):
        call.write(call.command[4]+'/maintenance.lock',b'');call.write(call.command[4]+'/epoch.json',b'{"device":');return 137,b''
    def empty_file(call):
        call.write(call.command[4]+'/maintenance.lock',b'');call.write(call.command[4]+'/epoch.json',b'');return 137,b''
    for behaviour,entries,epoch_json in ((lambda call:(137,b''),0,None),(lock_only,1,None),(torn,2,False),(empty_file,2,False)):
        m,docs,host=fresh(mode);host.docker.on_run=behaviour;receipt=docs.run(host);held=receipt['catalog']
        partial(receipt,'SCRIPT_OUTPUT_NOT_ONE_LINE');assert held['entries']==entries and held['files']['maintenance.lock']['exists'] is (entries>0)
        assert held['files']['epoch.json']['exists'] is (entries==2) and (held['epoch_json'] or {}).get('equal_to_the_expected_bytes')==epoch_json
        assert receipt['objects_left_by_this_run']==entries+(2 if mode=='REHEARSAL' else 0)
        assert receipt['pre_existing_objects_modified']==(False if mode=='REHEARSAL' else entries>0)


# ---------------------------------------------------------------- a verified catalog with a finding beside it
@pytest.mark.parametrize('mode',MODES)
def test_a_container_that_was_not_there_before_makes_a_verified_run_partial_and_is_listed(mode):
    def leaves(call,result):call.docker.containers.append(hostemu.container('zealous_hopper',hostemu.BACKEND,hostemu.BACKEND,[]))
    m,docs,host=fresh(mode);host.docker.on_run=then(leaves);receipt=docs.run(host);new=host.docker.container('zealous_hopper')
    partial(receipt,'CONTAINER_PRESENT_THAT_WAS_NOT_THERE_BEFORE','CATALOG_VERIFIED_WITH_FINDINGS')
    assert receipt['containers']=={'status':'COMPLETE','before':8,'after':9,'not_there_before':1,'rows':[{'id':new['Id'],'name':'zealous_hopper','state':'running'}]}
    assert receipt['mutating_calls']['uncertain']==0 and receipt['catalog']['status']=='COMPLETE' and receipt['script_line']['status']=='CATALOG_READY'
    # with a timeout the same listing says that the container may still be writing
    m,docs,host=fresh(mode);host.docker.on_run=then(leaves);host.hang_after.add(('run','--rm'));receipt=docs.run(host)
    partial(receipt,'COMMAND_TIMEOUT');assert receipt['containers']['not_there_before']==1 and receipt['containers']['rows'][0]['state']=='running'
    # more than eight newcomers: counted, eight rows
    def many(call,result):
        for index in range(11):call.docker.containers.append(hostemu.container('name_%d'%index,hostemu.BACKEND,hostemu.BACKEND,[]))
    m,docs,host=fresh(mode);host.docker.on_run=then(many);receipt=docs.run(host);assert receipt['containers']['not_there_before']==11 and len(receipt['containers']['rows'])==8
    # a container that went away meanwhile is not a finding
    m,docs,host=fresh(mode);host.docker.on_run=then(lambda call,result:call.docker.containers.pop(0) and None);receipt=docs.run(host)
    assert receipt['status']==m.COMPLETE_STATUS and receipt['containers']['after']==7

@pytest.mark.parametrize('mode',MODES)
def test_a_listing_that_fails_after_the_run_and_a_configuration_directory_that_changed_are_findings(mode):
    m,docs,host=fresh(mode);host.docker.on_run=then(lambda call,result:setattr(call.docker,'ps_returncode',1));receipt=docs.run(host)
    partial(receipt,'CONTAINER_LISTING_UNAVAILABLE_AFTER_RUN','CATALOG_VERIFIED_WITH_FINDINGS')
    assert receipt['containers']=={'status':'UNAVAILABLE','code':'COMMAND_FAILED','returncode':1,'before':8,'after':None,'not_there_before':None,'rows':[]}
    m,docs,host=fresh(mode);host.docker.on_run=then(lambda call,result:call.docker.host.hang.add(('ps','-a')));receipt=docs.run(host)
    partial(receipt,'CONTAINER_LISTING_UNAVAILABLE_AFTER_RUN','CATALOG_VERIFIED_WITH_FINDINGS');assert receipt['containers']['code']=='COMMAND_TIMEOUT' and receipt['containers']['after'] is None
    given=k2a.config_of(mode)                      # the directory docker was given: the unit's in REAL, the run's own in REHEARSAL
    m,docs,host=fresh(mode);host.docker.on_run=then(lambda call,result:call.docker.host.tree.add(given+'/config.json',kind='file',mode=0o600) and None);receipt=docs.run(host)
    partial(receipt,'DOCKER_CONFIG_DIRECTORY_NOT_EMPTY_AFTER_RUN','CATALOG_VERIFIED_WITH_FINDINGS');assert receipt['docker_config']['entries_after']==1 and receipt['docker_config']['path']==given
    assert names(host,k2a.CONFIG)==([] if mode=='REHEARSAL' else ['config.json'])
    m,docs,host=fresh(mode);host.docker.on_run=then(lambda call,result:setattr(call.docker.host.tree.get(given),'mode',0o755));receipt=docs.run(host)
    partial(receipt,'DOCKER_CONFIG_READBACK_UNAVAILABLE','CATALOG_VERIFIED_WITH_FINDINGS')
    assert receipt['docker_config']=={'path':given,'is_the_directory_of_the_unit':mode=='REAL','entries_before':0,'entries_after':None,'code':'PARENT_REPLACED'}
    for receipt in (receipt,):assert receipt['mutating_calls']['uncertain']==0 and receipt['mutating_calls']['succeeded']==(1 if mode=='REAL' else 3)
    # a catalog that is not verified outranks a finding beside it
    m,docs,host=fresh(mode)
    def both(call,result):
        call.docker.containers.append(hostemu.container('zealous_hopper',hostemu.BACKEND,hostemu.BACKEND,[]));call.node(call.command[4]+'/epoch.json').mode=0o644
    host.docker.on_run=then(both);receipt=docs.run(host);partial(receipt,'CATALOG_READBACK_MISMATCH');assert receipt['containers']['not_there_before']==1


# ---------------------------------------------------------------- the rehearsal's own directory
def test_rehearsal_directory_failures_before_the_container():
    def appears(path):
        def hook(host,name,detail,calls):
            if name=='mkdir' and detail[0]==path:host.tree.add(path,mode=0o755,uid=1000)
        return hook
    # the name of the first directory appears after the precheck: nothing was created, nothing was started
    m,docs,host=fresh('REHEARSAL');host.hook=appears(k2a.REHEARSAL_CONFIG);receipt=docs.run(host)
    refused(receipt,'DESTINATION_APPEARED_AFTER_PRECHECK','EFFECTS');assert host.commands==[] and [row['state'] for row in receipt['directories']]==['NOT_CREATED']
    assert node(host,k2a.REHEARSAL_CONFIG).uid==1000 and node(host,k2a.REHEARSAL_ROOT) is None,'what appeared is left alone'
    m,docs,host=fresh('REHEARSAL');host.readonly=True;receipt=docs.run(host);refused(receipt,'FILESYSTEM_READ_ONLY','EFFECTS');assert host.commands==[]
    # the name of the throwaway root appears after the reads: the first directory exists, so this is a partial; no container
    m,docs,host=fresh('REHEARSAL');host.hook=appears(k2a.REHEARSAL_ROOT);receipt=docs.run(host)
    partial(receipt,'DESTINATION_APPEARED_AFTER_PRECHECK');assert host.container_runs()==[] and [(row['key'],row['state']) for row in receipt['directories']]==[('DOCKER_CONFIG','CREATED_DURABLE'),('JOURNAL_ROOT','NOT_CREATED')]
    assert node(host,k2a.REHEARSAL_ROOT).uid==1000 and receipt['objects_left_by_this_run']==1 and receipt['run'] is None and len(host.commands)==2
    # created, but not what was asked for: left in place, labelled, and no container is started in it
    for prepare,code,state in ((lambda host:setattr(host,'creator',(0,5)),'CREATED_METADATA_MISMATCH','CREATED_METADATA_MISMATCH'),
                               (lambda host:setattr(host,'created_device',hostemu.DATA_DEVICE),'CREATED_METADATA_MISMATCH','CREATED_METADATA_MISMATCH'),
                               (lambda host:setattr(host,'mask',0o277),None,'CREATED_DURABLE')):
        m,docs,host=fresh('REHEARSAL');prepare(host);receipt=docs.run(host)
        if code is None:
            assert receipt['status']==m.COMPLETE_STATUS and node(host,k2a.REHEARSAL_ROOT).mode==0o700 and host.mask==0o077,'the run sets its own umask'
            continue
        partial(receipt,code);assert [row['state'] for row in receipt['directories']]==[state] and host.commands==[] and receipt['run'] is None
        assert receipt['objects_left_by_this_run']==1 and names(host,k2a.REHEARSAL_CONFIG)==[] and node(host,k2a.REHEARSAL_ROOT) is None and names(host,k2a.JOURNAL)==[]
    # the same failures at the second directory, the throwaway root: no container is started in it
    for prepare,code,state in ((lambda host:setattr(host,'creator',(0,5)),'CREATED_METADATA_MISMATCH','CREATED_METADATA_MISMATCH'),
                               (lambda host:setattr(host,'created_device',hostemu.DATA_DEVICE),'CREATED_METADATA_MISMATCH','CREATED_METADATA_MISMATCH')):
        m,docs,host=fresh('REHEARSAL')
        def hook(host,name,detail,calls,prepare=prepare):
            if name=='mkdir' and detail[0]==k2a.REHEARSAL_ROOT:prepare(host)
        host.hook=hook;receipt=docs.run(host)
        partial(receipt,code);assert [row['state'] for row in receipt['directories']]==['CREATED_DURABLE',state] and host.container_runs()==[] and receipt['run'] is None
        assert receipt['objects_left_by_this_run']==2 and names(host,k2a.REHEARSAL_ROOT)==[] and names(host,k2a.JOURNAL)==[]
    for which,states,commands in ((k2a.REHEARSAL_CONFIG,['CREATED_NOT_DURABLE'],0),(k2a.REHEARSAL_ROOT,['CREATED_DURABLE','CREATED_NOT_DURABLE'],2)):
        m,docs,host=fresh('REHEARSAL')
        def failing(host,name,detail,calls,which=which):
            if name=='fsync' and detail[0]==which:raise OSError(5,'injected')
        host.hook=failing;receipt=docs.run(host);partial(receipt,'FSYNC_FAILED')
        assert [row['state'] for row in receipt['directories']]==states and host.container_runs()==[] and len(host.commands)==commands


# ---------------------------------------------------------------- crash points
@pytest.mark.parametrize('mode',MODES)
def test_a_death_before_the_first_effect_is_a_refusal_and_after_it_a_partial_of_unknown_state(mode):
    m,docs,host=fresh(mode);assert docs.run(host)['status']==m.COMPLETE_STATUS;log=list(host.log);total=host.calls
    events=[entry for entry in log if entry[0] not in ('container-write','compose-recreate')];assert len(events)==total
    first=min(index for index,entry in enumerate(events,1) if entry[0]=='mkdir' or (entry[0]=='run' and entry[1][1]=='run'))
    seen=set()
    for index in range(1,total+1):
        m,docs,host=fresh(mode);before=k2a.state_of(host)
        def hook(host,name,detail,calls,index=index):
            if calls==index:raise hostemu.Death('dead')
        host.hook=hook;receipt=docs.run(host);changed=k2a.state_of(host)!=before
        if index<first:
            assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','RUN_FAILED_BEFORE_ANY_EFFECT','BEFORE_ANY_EFFECT') and not changed,index
        else:
            assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==(PARTIAL,'PARTIAL_STATE_UNKNOWN_ROOT_NOT_TO_BE_USED_AGAIN','RUN_ESCAPED_STATE_UNKNOWN','ESCAPED'),index
            assert receipt['mutating_calls']['issued']>=1
        root=node(host,k2a.root_of(mode));seen.add('absent' if root is None else tuple(sorted(root.children)))
        assert f.sealed(receipt) and 'dead' not in json.dumps(receipt)
    # what a later read can find after a death, by where it fell: untouched, (the empty throwaway,) or the complete catalog
    assert seen==({(),tuple(k2a.NAMES)} if mode=='REAL' else {'absent',(),tuple(k2a.NAMES)})

def test_a_death_at_the_start_of_the_container_leaves_the_real_root_empty_and_the_call_uncertain():
    m,docs,host=fresh()
    def hook(host,name,detail,calls):
        if name=='run' and detail[0][1]=='run':raise hostemu.Death('dead')
    host.hook=hook;receipt=docs.run(host)
    assert (receipt['status'],receipt['code'])==(PARTIAL,'RUN_ESCAPED_STATE_UNKNOWN') and receipt['mutating_calls']=={'issued':1,'succeeded':0,'failed_nothing_changed':0,'uncertain':1}
    assert names(host,k2a.JOURNAL)==[]


# ---------------------------------------------------------------- the receipt
@pytest.mark.parametrize('mode',MODES)
def test_receipt_carries_no_script_byte_no_environment_value_and_fits_the_limit(mode):
    def leaves(call,result):call.docker.containers.append(hostemu.container('zealous_hopper',hostemu.BACKEND,hostemu.BACKEND,['TOKEN='+hostemu.SECRET]))
    for prepare in (lambda host:None,lambda host:host.hang_after.add(('run','--rm')),lambda host:setattr(host.docker,'on_run',then(leaves)),lambda host:host.docker.images.pop(0)):
        m,docs,host=fresh(mode);prepare(host);receipt=docs.run(host);line=f.line(receipt)
        assert hostemu.SECRET.encode() not in line and b'never-emit' not in line and len(line)<=m.RECEIPT_LIMIT and f.sealed(receipt)
        assert b'SessionJournalRoot' not in line and m.CATALOG_SCRIPT_B64[:60].encode() not in line and receipt['secret_bytes_in_receipt'] is False
        assert receipt['activation_performed'] is False and receipt['daemon_reload_performed'] is False and receipt['ready'] is False

def test_a_receipt_too_large_is_reduced_by_flagged_steps_and_is_then_never_complete():
    m,docs,host=fresh();receipt=docs.run(host);big=copy.deepcopy(receipt);big.pop('metadata_sha256');big['observed_rows']={'journal':['x'*100]*700}
    reduced=m.seal(big);assert reduced['size_reductions']==['OBSERVED_ROWS_DROPPED'] and reduced['observed_rows']=={'reduced_for_size':True}
    assert (reduced['status'],reduced['outcome'])==(PARTIAL,'RECEIPT_REDUCED_STATE_REQUIRES_READBACK') and reduced['mutating_calls']==receipt['mutating_calls'] and f.sealed(reduced)
    big=copy.deepcopy(receipt);big.pop('metadata_sha256');big['observed_rows']={'journal':['x'*100]*700};big['containers']['rows']=['y'*100]*700
    reduced=m.seal(big);assert reduced['size_reductions']==['OBSERVED_ROWS_DROPPED','NEW_CONTAINER_ROWS_DROPPED'] and reduced['containers']['rows']==[]

def test_what_the_gate_readback_signs_is_in_a_complete_receipt():
    """hostops01's readback signs catalog{expected, receipt_sha256, device, inode} from the 4b receipt: the hash of this
    receipt, and the identity of the root, which the container's line and the host agree on."""
    m,docs,host=fresh();receipt=docs.run(host);root=node(host,k2a.JOURNAL)
    assert receipt['metadata_sha256'] and (receipt['script_line']['device'],receipt['script_line']['inode'])==(receipt['journal_root']['device'],receipt['journal_root']['inode'])==(root.dev,root.ino)
    assert receipt['effects']['journal_root']['is_the_real_journal_root'] is True and receipt['effects']['epoch']=='R2D2-V2-SHADOW-2026-10-05' and receipt['mode']=='REAL'
