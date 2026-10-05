"""OP_PRECHECK on the emulated host: the baseline rows the write requests sign, and the whole chain
precheck -> provision -> install -> readback built only from receipts.
Synthetic local tests only. No SSH, host, real credential, docker binary or operational GO."""
import base64
from datetime import timedelta
import json

import pytest

import family as f
import hostemu

k=f.load('precheck');m=k.m
UNITS='/etc/systemd/system'

def fresh(**options):
    host=f.world(k);return host,f.Docs(k,f.precheck_fields(k,host,**options))
def refusal(action):
    with pytest.raises(m.Refused) as caught:action()
    return str(caught.value)
def run(host,docs):
    before=host.tree.snapshot();times={path:(host.tree.get(path).atime,host.tree.get(path).mtime) for path in host.tree.paths()}
    receipt=docs.run(host)
    assert host.tree.snapshot()==before and host.mutating()==[] and receipt['writes']==0 and f.sealed(receipt)
    assert {path:(host.tree.get(path).atime,host.tree.get(path).mtime) for path in host.tree.paths()}==times
    assert 'canary' not in json.dumps(receipt) and 'never-emit' not in json.dumps(receipt)
    return receipt


def test_effects_shown_in_the_go_are_exactly_this_literal():
    """Written out by hand: a member that disappears from effects_of, or changes meaning, fails here."""
    host,docs=fresh()
    expected={'operation':'GO_READONLY_HOSTOPS_PRECHECK_01','journal_placement':'B','existing_journal_leaves':[],
              'chains':{'ETC':'/etc','VAR_LIB':'/var/lib','DATA_VOLUME':'/mnt/day-d-data','UNIT_DIRECTORY':'/etc/systemd/system'},
              'destinations':['/etc/c3po-bar','/etc/c3po-bar/manifests','/etc/c3po-bar/docker-cli','/var/lib/c3po-bar','/var/lib/c3po-bar/supervisor',
                              '/mnt/day-d-data/r2d2-v2-massive-epoch03','/etc/c3po-reader','/etc/c3po-reader/docker-cli','/var/lib/c3po-reader',
                              '/mnt/day-d-data/c3po-capacity','/mnt/day-d-data/c3po-capacity/config','/mnt/day-d-data/c3po-capacity/documents',
                              '/mnt/day-d-data/c3po-capacity/payload','/mnt/day-d-data/c3po-capacity/go','/var/lib/c3po-reader/capacity-receipts'],
              'unit_names':['c3po-massive.service','c3po-massive.timer'],
              'secret_bearing_names':['/etc/c3po-reader/secret.env','/etc/c3po-bar/token'],
              'presence_only':['/etc/.git','/etc/.etckeeper','/run/reboot-required'],
              'image_reference':'c3po/backend:production','writes':0,'activation':False}
    assert f.canonical(m.effects_of(docs.plan))==f.canonical(expected)==f.canonical(docs.go['effects'])
    host,docs=fresh(groups=['SUPERVISOR']);assert docs.go['effects']['chains']=={'ETC':'/etc','VAR_LIB':'/var/lib','UNIT_DIRECTORY':'/etc/systemd/system'}
    assert len(docs.go['effects']['destinations'])==5 and docs.go['effects']['journal_placement'] is None
    # the signed list of journal leaves that already exist is what the GO shows, literally
    host,docs=fresh(existing=['r2d2-v2-massive-epoch02','r2d2-v2-massive-epoch01'])
    assert docs.go['effects']['existing_journal_leaves']==m.effects_of(docs.plan)['existing_journal_leaves']==['r2d2-v2-massive-epoch02','r2d2-v2-massive-epoch01']
    docs.plan['existing_journal_leaves']=['r2d2-v2-massive-epoch02'];docs.chain(effects=False)
    assert refusal(docs.authenticate)=='EFFECTS_BINDING','a request whose list of existing leaves changes cannot keep its GO'
    # placement A: the journal root is a destination next to the state root, and the data volume is read only for the capacity tree
    host,docs=fresh(placement='A');effects=docs.go['effects']
    assert effects['journal_placement']=='A' and effects['destinations'][5]=='/var/lib/c3po-bar/journal' and '/mnt/day-d-data/r2d2-v2-massive-epoch03' not in effects['destinations']
    host,docs=fresh(placement='A',groups=['SUPERVISOR','JOURNAL_LEAF']);assert docs.go['effects']['chains']=={'ETC':'/etc','VAR_LIB':'/var/lib','UNIT_DIRECTORY':'/etc/systemd/system'}
    receipt=run(host,docs);assert not [entry for entry in host.log if type(entry[1]) is str and entry[1].startswith('/mnt')],'under placement A the data volume is not read'
    assert receipt['items']['destinations']['SUP_JOURNAL']=={'status':'COMPLETE','exists':False,'absent_at':'/var/lib/c3po-bar','absence_proved_at_read':True,'key':'SUP_JOURNAL','path':'/var/lib/c3po-bar/journal'}
    assert receipt['items']['chains']['VAR_LIB']['bytes_available_to_non_root_f_bavail']==595212316672,'the figure the floor of placement A is compared with'

def test_baseline_rows_are_exactly_what_a_write_request_signs_and_absence_is_proved():
    host,docs=fresh();receipt=run(host,docs);items=receipt['items']
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.COMPLETE_STATUS,'PRECHECK_ALL_OBSERVED',None) and receipt['problems']==[]
    assert sorted(items['chains'])==['DATA_VOLUME','ETC','UNIT_DIRECTORY','VAR_LIB']
    for name,path in (('ETC','/etc'),('VAR_LIB','/var/lib'),('UNIT_DIRECTORY',UNITS),('DATA_VOLUME',hostemu.DATA)):
        chain=items['chains'][name];assert chain['rows']==hostemu.rows(host,path) and chain['status']=='COMPLETE' and chain['direct_parent_setgid'] is False
        assert all(set(row)=={'path','device','inode','uid','gid','mode'} for row in chain['rows'])
        assert all(note['accepted_by_the_write_operations'] for note in chain['notes'])
    volume=items['chains']['DATA_VOLUME']
    assert volume['notes'][-1]=={'path':hostemu.DATA,'mode_octal':'0755','setgid':False,'root_owned_not_group_or_other_writable':False,
                                 'world_writable_without_sticky':False,'accepted_by_the_write_operations':True,'mount_point_by_device_change':True}
    assert volume['bytes_available_to_non_root_f_bavail']==13200816*4096==54070542336,'the figure a floor is compared with before it is signed'
    assert items['chains']['VAR_LIB']['bytes_available_to_non_root_f_bavail']==145315507*4096==595212316672
    assert len(items['destinations'])==15
    for key,row in items['destinations'].items():
        assert row['status']=='COMPLETE' and row['exists'] is False and row['absence_proved_at_read'] is True and row['absent_at']
    assert items['destinations']['SUP_MANIFESTS']['absent_at']=='/etc/c3po-bar' and items['destinations']['CAP_GO']['absent_at']==hostemu.DATA+'/c3po-capacity'
    assert items['unit_files']=={name:{'status':'COMPLETE','exists':False} for name in docs.plan['unit_names']}
    assert items['conflicts']['status']=='COMPLETE' and items['conflicts']['findings']==[] and items['conflicts']['leftover_count']==0
    assert items['image']['id']==hostemu.BACKEND and items['image']['repo_tags']==['c3po/backend:production'] and items['image']['revision_label']==hostemu.REVISION
    assert items['image_listing']['contains_inspected_id'] is True and items['image_listing']['retention_tags_present']==[]
    assert [row['tag'] for row in items['image_listing']['rows']]==['production','rollback']
    assert items['boot']['boot_id_sha256']==f.BOOT_SHA and items['core_pattern']=={'status':'COMPLETE','is_pipe':True}
    assert items['secret_bearing_names']=={'/etc/c3po-reader/secret.env':{'status':'COMPLETE','exists':False,'absent_at':'/etc/c3po-reader'},
                                           '/etc/c3po-bar/token':{'status':'COMPLETE','exists':False,'absent_at':'/etc/c3po-bar'}}
    assert items['presence_only']=={path:{'status':'COMPLETE','exists':False} for path in ('/etc/.git','/etc/.etckeeper','/run/reboot-required')}
    assert [command['argv'][1:3] for command in host.commands]==[['image','inspect'],['image','ls']] and all(c['docker_config'] is None for c in host.commands)
    assert sorted({entry[1] for entry in host.log if entry[0]=='read'})==sorted([m.BOOT_ID_PATH,m.CORE_PATTERN_PATH])
    assert len(f.line(receipt))<16384 and receipt['size_reductions']==[] and receipt['installation_authorized'] is False

@pytest.mark.parametrize('placement',['A','B'])
def test_the_whole_chain_binds_from_receipts_only(placement):
    """precheck receipt -> provision request -> provision receipt -> install request -> both receipts -> readback request,
    on the host as the HOSTFACTS_01 receipt read it. Under placement A (the first epoch) the chain ends in the one
    outcome that satisfies the readback half of the activation gate, with nothing freed. Under placement B it ends in
    FREE_SPACE_BELOW_FLOOR until space is freed on the data volume under another authorisation."""
    host=hostemu.world();host.refused=m.Refused;precheck=f.Docs(k,f.precheck_fields(k,host,placement=placement)).run(host);items=precheck['items']
    assert precheck['outcome']=='PRECHECK_ALL_OBSERVED'
    p=f.load('provision');host.refused=p.m.Refused
    leaf=f.A_LEAF if placement=='A' else f.LEAF;groups=list(p.m.GROUPS);table=p.m.layout(groups,hostemu.DATA,leaf,f.CAPACITY,placement)
    fields={'groups':groups,'journal_placement':placement,'data_volume_path':hostemu.DATA,'journal_leaf':leaf,'existing_journal_leaves':[],'capacity':dict(f.CAPACITY),
            'chains':{name:items['chains'][name]['rows'] for name in p.m.chain_paths(table,hostemu.DATA,f.CAPACITY)},
            'creates':[dict(row,expect='ABSENT') for row in table],
            'retention_tag':{'repository':'c3po/backend','tag':f.TAG,'image_id':items['image']['id'],'expect':'ABSENT'},
            'evidence_boot_id_sha256':items['boot']['boot_id_sha256']}
    evidence=[{'role':'PRECHECK','operation':m.OPERATION,'receipt_sha256':precheck['metadata_sha256']}]
    provision=f.Docs(p,fields,evidence=evidence).run(host);assert provision['outcome']=='PROVISIONED_ALL_VERIFIED_DURABLE'
    i=f.load('install_units');host.refused=i.m.Refused
    values=dict(f.values_of(placement),IMAGE_ID=items['image']['id']);units=f.supervisor_units(values)
    fields={'unit_directory':items['chains']['UNIT_DIRECTORY']['rows'],'units':units,'network_allowlist':['bridge'],'journal_placement':placement,
            'data_volume_path':hostemu.DATA,'deploy_tree_path':f.tree_of(placement),
            'template_revision':'d7600b4d14f8a67694ffb37cde06b622f9a3bac3','acknowledged_leftovers':[],'daemon_reload_owner':'OPERATION_5_ACTIVATION_GO',
            'evidence_boot_id_sha256':items['boot']['boot_id_sha256']}
    install=f.Docs(i,fields,evidence=evidence).run(host);assert install['outcome']=='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED'
    host.tree.add('/etc/c3po-bar/token',kind='file',mode=0o600,content=b'never-emit-token-canary\n');host.is_enabled['c3po-massive.timer']='disabled'
    r=f.load('readback');host.refused=r.m.Refused;ledger={row['key']:row for row in provision['ledger']};files={row['key']:row for row in install['ledger']}
    rendered=f.reference_render(values)
    fields={'mode':'GATE','install':{'receipt_sha256':install['metadata_sha256'],'outcome':install['outcome']},
            'provision':{'receipt_sha256':provision['metadata_sha256']},'evidence_boot_id_sha256':items['boot']['boot_id_sha256'],
            'unit_directory':install['unit_directory'],
            'service':{'template_b64':base64.b64encode(f.SERVICE).decode(),'rendered_sha256':f.sha(rendered),'rendered_bytes':len(rendered),
                       'device':files['SUPERVISOR_SERVICE']['device'],'inode':files['SUPERVISOR_SERVICE']['inode']},
            'timer':{'template_b64':base64.b64encode(f.TIMER).decode(),'rendered_sha256':f.sha(f.TIMER),'rendered_bytes':len(f.TIMER),
                     'device':files['SUPERVISOR_TIMER']['device'],'inode':files['SUPERVISOR_TIMER']['inode']},
            'substitutions':values,'network_allowlist':['bridge'],'journal_placement':placement,'deploy_tree_path':f.tree_of(placement),
            'journal_mount_point':provision['effects']['journal']['mount_point_by_device_change'],
            'data_volume':{'path':hostemu.DATA,'rows':provision['chains']['DATA_VOLUME'] if placement=='B' else None},
            'layout':{key:{'device':ledger[key]['observed']['device'],'inode':ledger[key]['observed']['inode']} for key in r.m.LAYOUT_KEYS},
            'retention_reference':provision['retention_tag']['reference'],'image_revision':items['image']['revision_label'],
            'free_space_floor_bytes':56706990080,'sessions_retained':5,'other_writers_allowance_bytes':0,
            'catalog':{'expected':'NOT_YET','receipt_sha256':None,'device':None,'inode':None}}
    # binding step 2b: the floor is compared with what the precheck read on the journal root's filesystem BEFORE a readback GO is
    # asked for: the chain the provision effects name (VAR_LIB under placement A, DATA_VOLUME under placement B).
    chain=provision['effects']['journal']['filesystem_named_by_chain'];assert chain==('VAR_LIB' if placement=='A' else 'DATA_VOLUME')
    # which filesystem the journal root is on is read, not assumed: the precheck notes say where the device changes, and the
    # provision effects name the mount point computed from the rows that were signed
    assert [note['path'] for note in items['chains'][chain]['notes'] if note['mount_point_by_device_change']][-1]==provision['effects']['journal']['mount_point_by_device_change']
    assert provision['effects']['journal']['mount_point_by_device_change']==('/' if placement=='A' else hostemu.DATA)
    known=items['chains'][chain]['bytes_available_to_non_root_f_bavail'];assert known==(595212316672 if placement=='A' else 54070542336)
    evidence=[{'role':'INSTALL','operation':i.m.OPERATION,'receipt_sha256':install['metadata_sha256']}]
    readback=f.Docs(r,fields,evidence=evidence).run(host)
    if placement=='A':
        assert known>=fields['free_space_floor_bytes']
        assert readback['outcome']=='READBACK_ALL_OBSERVED_ALL_EXPECTATIONS_MET',(readback['findings'],readback['items_not_complete'])
        assert readback['items']['free_space']['bytes_available_to_non_root_f_bavail']==595212316672 and readback['items']['free_space']['filesystem_device']==801
        assert readback['items']['layout']['data_volume']['read'] is False
    else:
        assert known<fields['free_space_floor_bytes']
        assert (readback['outcome'],readback['findings'],readback['items_not_complete'])==('OBSERVED_ALL_EXPECTATIONS_NOT_MET',['FREE_SPACE_BELOW_FLOOR'],[])
        hostemu.free_space(host,f.FREED_BYTES)                               # under another authorisation; nothing in this family frees space
        readback=f.Docs(r,fields,evidence=evidence,now=f.NOW+timedelta(seconds=1)).run(host)
        assert readback['outcome']=='READBACK_ALL_OBSERVED_ALL_EXPECTATIONS_MET',(readback['findings'],readback['items_not_complete'])
    # and a second precheck now reports what exists, with the identities a continuation would sign
    host.refused=m.Refused;after=f.Docs(k,f.precheck_fields(k,host,placement=placement)).run(host)['items']
    row=after['destinations']['SUP_CONFIG'];node=host.tree.get('/etc/c3po-bar')
    assert (row['exists'],row['device'],row['inode'],row['entries'],row['table_defined_children'],row['other_entries'],row['conforms_to_layout'])==(True,node.dev,node.ino,3,2,1,True)
    row=after['destinations']['SUP_STATE_PARENT'];assert (row['entries'],row['table_defined_children'],row['other_entries'])==((2,2,0) if placement=='A' else (1,1,0))
    unit=after['unit_files']['c3po-massive.service'];node=host.tree.get(UNITS+'/c3po-massive.service')
    assert unit=={'status':'COMPLETE','exists':True,'type':'file','uid':0,'gid':0,'mode_octal':'0644','links':1,'device':node.dev,'inode':node.ino}
    assert after['image_listing']['retention_tags_present']==[f.TAG]
    assert after['secret_bearing_names']['/etc/c3po-bar/token']=={'status':'COMPLETE','exists':True,'type':'file','uid':0,'gid':0,'mode_octal':'0600','links':1}

def test_names_that_hold_a_secret_are_reported_without_size_identity_or_time():
    for size in (55,77,4097):
        host,docs=fresh();host.tree.add('/etc/c3po-reader/secret.env',kind='file',mode=0o600,content=b'C3PO_DATABASE_URL='+b's'*size)
        host.tree.add('/etc/c3po-reader/.hostops-0123456789abcdef-0.partial',kind='file',mode=0o600,content=b'never-emit-secret-canary')
        receipt=run(host,docs);row=receipt['items']['secret_bearing_names']['/etc/c3po-reader/secret.env']
        assert row=={'status':'COMPLETE','exists':True,'type':'file','uid':0,'gid':0,'mode_octal':'0600','links':1}
        node=host.tree.get('/etc/c3po-reader/secret.env');text=json.dumps(receipt)
        for number in (size,size+18,node.ino):assert str(number) not in json.dumps(row)
        assert not [entry for entry in host.log if entry[0] in ('open','read') and 'secret.env' in entry[1]]
        config=receipt['items']['destinations']['RDR_CONFIG'];assert config['exists'] is True and config['entries']==2 and config['other_entries']==2
        assert '"size"' not in json.dumps({key:value for key,value in receipt['items'].items() if key!='conflicts'})

def test_presence_of_versioning_of_etc_and_a_non_pipe_core_pattern_are_reported():
    host,docs=fresh();host.tree.add('/etc/.git');host.tree.add('/etc/.etckeeper',kind='file');host.tree.add('/run/reboot-required',kind='file')
    host.tree.get(m.CORE_PATTERN_PATH).content=bytearray(b'core\n');receipt=run(host,docs)
    assert receipt['items']['presence_only']=={path:{'status':'COMPLETE','exists':True} for path in ('/etc/.git','/etc/.etckeeper','/run/reboot-required')}
    assert receipt['items']['core_pattern']['is_pipe'] is False and receipt['outcome']=='PRECHECK_ALL_OBSERVED'

def test_guards_of_the_write_operations_are_confronted_with_the_baseline():
    host,docs=fresh();host.tree.get(hostemu.DATA).mode=0o2775;receipt=run(host,docs);volume=receipt['items']['chains']['DATA_VOLUME']
    assert volume['direct_parent_setgid'] is True and volume['notes'][-1]['setgid'] is True and volume['rows'][-1]['mode']==0o2775
    host,docs=fresh();host.tree.get('/etc').mode=0o775;host.tree.get('/var/lib').uid=1000;receipt=run(host,docs)
    assert receipt['items']['chains']['ETC']['notes'][-1]['accepted_by_the_write_operations'] is False
    assert receipt['items']['chains']['VAR_LIB']['notes'][-1]['accepted_by_the_write_operations'] is False
    assert receipt['items']['chains']['UNIT_DIRECTORY']['notes'][1]['accepted_by_the_write_operations'] is False
    # the note is the write operations' own rule: inside the data volume as signed, but never writable by others without the sticky bit
    p=f.load('provision').m
    for mode,accepted in ((0o755,True),(0o775,True),(0o1777,True),(0o777,False),(0o757,False)):
        host,docs=fresh();host.tree.get(hostemu.DATA).mode=mode;note=run(host,docs)['items']['chains']['DATA_VOLUME']['notes'][-1]
        assert (note['accepted_by_the_write_operations'],note['world_writable_without_sticky'])==(accepted,not accepted),oct(mode)
        row=hostemu.rows(host,hostemu.DATA)[-1];assert (p.row_accepted(row,hostemu.DATA) is None)==accepted
    host,docs=fresh();host.tree.get('/mnt').mode=0o1777;receipt=run(host,docs)       # outside the volume the sticky bit does not help
    assert receipt['items']['chains']['DATA_VOLUME']['notes'][1]['accepted_by_the_write_operations'] is False

def test_what_exists_is_reported_with_metadata_and_counts_never_names():
    host,docs=fresh();host.tree.add('/etc/c3po-bar/manifests',mode=0o700);host.tree.get('/etc/c3po-bar').mode=0o700
    host.tree.add('/etc/c3po-bar/private-name-canary',kind='file');host.tree.add('/var/lib/c3po-bar',kind='file',content=b'x'*31)
    host.tree.add(UNITS+'/c3po-massive.timer',kind='file',mode=0o644,content=f.TIMER);host.tree.add(UNITS+'/c3po-massive.timer.d')
    host.tree.add(UNITS+'/.hostops-0123456789abcdef-1.partial',kind='file',mode=0o644,content=b'half')
    host.docker.images[1]['RepoTags'].append('c3po/backend:massive-supervisor-epoch02')
    receipt=run(host,docs);items=receipt['items'];row=items['destinations']['SUP_CONFIG']
    assert (row['type'],row['uid'],row['gid'],row['mode_octal'],row['entries'],row['table_defined_children'],row['other_entries'])==('dir',0,0,'0700',2,1,1)
    assert items['destinations']['SUP_MANIFESTS']['exists'] is True and items['destinations']['SUP_DOCKER_CLI']['exists'] is False
    assert items['destinations']['SUP_STATE_PARENT']['type']=='file' and items['destinations']['SUP_STATE']['status']=='UNAVAILABLE'
    assert items['unit_files']['c3po-massive.timer']['links']==1 and 'size' not in items['unit_files']['c3po-massive.timer']
    assert items['conflicts']['finding_codes']==['DROP_IN_PRESENT']
    assert items['conflicts']['leftovers'][0]['name']=='.hostops-0123456789abcdef-1.partial' and items['image_listing']['retention_tags_present']==['massive-supervisor-epoch02']
    assert 'private-name' not in json.dumps(receipt) and receipt['outcome']=='PARTIAL_OBSERVED'

def test_a_unit_file_at_a_signed_name_is_reported_without_its_size():
    """This operation cannot tell whether the file is the signed render; of a foreign unit with an inline secret the
    size would measure the secret."""
    secret=b'[Service]\nEnvironment=API_KEY=never-emit-inline-secret-0123456789\n'
    host,docs=fresh();host.tree.add(UNITS+'/c3po-massive.service',kind='file',mode=0o644,content=secret);receipt=run(host,docs)
    row=receipt['items']['unit_files']['c3po-massive.service']
    assert set(row)=={'status','exists','type','uid','gid','mode_octal','links','device','inode'} and len(secret) not in [value for value in row.values() if type(value) is int]
    assert not [entry for entry in host.log if entry[0] in ('open','read') and entry[1]==UNITS+'/c3po-massive.service']

def test_own_dependency_directories_and_alias_links_are_reported_before_anything_is_signed():
    host,docs=fresh();host.tree.add(UNITS+'/c3po-massive.service.wants/other.service',kind='symlink',mode=0o777)
    host.tree.add('/usr/lib/systemd/system/c3po-massive.timer.requires');host.tree.add(UNITS+'/backup.service',kind='symlink',mode=0o777).target='c3po-massive.service'
    conflicts=run(host,docs)['items']['conflicts'];assert conflicts['finding_codes']==['ALIAS_LINK_PRESENT','OWN_DEPENDENCY_DIRECTORY_PRESENT']
    assert {'code':'OWN_DEPENDENCY_DIRECTORY_PRESENT','directory':UNITS,'name':'c3po-massive.service.wants','within':None} in conflicts['findings']
    assert {'code':'OWN_DEPENDENCY_DIRECTORY_PRESENT','directory':'/usr/lib/systemd/system','name':'c3po-massive.timer.requires','within':None} in conflicts['findings']
    assert {'code':'ALIAS_LINK_PRESENT','directory':UNITS,'name':'backup.service','within':'c3po-massive.service'} in conflicts['findings']

def test_a_failed_observation_is_unavailable_with_a_code_and_never_an_absence():
    host,docs=fresh();host.tree.remove('/var/lib');host.tree.add('/var/lib',kind='symlink',mode=0o777);receipt=run(host,docs)
    chain=receipt['items']['chains']['VAR_LIB'];assert (chain['status'],chain['code'])==('UNAVAILABLE','SYMLINK_COMPONENT') and len(chain['rows'])==2
    row=receipt['items']['destinations']['SUP_STATE_PARENT'];assert (row['status'],row['code'],row['exists'])==('UNAVAILABLE','SYMLINK_COMPONENT',None)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,'PARTIAL_OBSERVED','SYMLINK_COMPONENT') and 'SYMLINK_COMPONENT' in receipt['problems']
    host,docs=fresh();host.tree.add('/etc/c3po-reader',kind='symlink',mode=0o777);host.tree.add('/etc/c3po-bar',kind='symlink',mode=0o777);receipt=run(host,docs)
    assert receipt['items']['secret_bearing_names']=={'/etc/c3po-reader/secret.env':{'status':'UNAVAILABLE','code':'SYMLINK_COMPONENT','at':'/etc/c3po-reader'},
                                                      '/etc/c3po-bar/token':{'status':'UNAVAILABLE','code':'SYMLINK_COMPONENT','at':'/etc/c3po-bar'}}
    host,docs=fresh();host.tree.remove(hostemu.DATA);receipt=run(host,docs)
    assert receipt['items']['chains']['DATA_VOLUME']['status']=='UNAVAILABLE' and receipt['items']['destinations']['SUP_JOURNAL']['exists'] is False
    host,docs=fresh();host.docker.images[0]['RepoTags']=[];receipt=run(host,docs)
    assert receipt['items']['image']=={'status':'UNAVAILABLE','code':'IMAGE_ABSENT_OR_UNREADABLE','returncode':1} and receipt['outcome']=='PARTIAL_OBSERVED'
    assert receipt['items']['image_listing']['contains_inspected_id'] is None
    host,docs=fresh();host.docker.ls_returncode=1;receipt=run(host,docs);assert receipt['items']['image_listing']=={'status':'UNAVAILABLE','code':'TAG_LISTING_UNAVAILABLE'}
    host,docs=fresh();host.docker.ls_override=b'{"id":"fbfb","repository":"c3po/backend","tag":"production"}\n';assert run(host,docs)['items']['image_listing']['code']=='TAG_LISTING_UNAVAILABLE'
    host,docs=fresh();host.docker.ls_override=b'{"id":"sha256:'+b'9c'*32+b'","repository":"c3po/backend","tag":"rollback"}\n'
    receipt=run(host,docs);assert receipt['items']['image_listing']['contains_inspected_id'] is False and receipt['items']['image_listing']['status']=='COMPLETE'
    host,docs=fresh();host.hang.add('docker');receipt=run(host,docs);assert receipt['items']['image']['code']=='COMMAND_TIMEOUT' and len(host.commands)==2
    host,docs=fresh();host.tree.remove(m.BOOT_ID_PATH);host.tree.remove(m.CORE_PATTERN_PATH);receipt=run(host,docs)
    assert receipt['items']['boot']['status']=='UNAVAILABLE' and receipt['items']['core_pattern']['status']=='UNAVAILABLE' and receipt['items']['chains']['ETC']['status']=='COMPLETE'
    host,docs=fresh();host.noatime_available=False;receipt=run(host,docs);assert receipt['outcome']=='PARTIAL_OBSERVED' and 'NOATIME_UNAVAILABLE' in receipt['problems']

def test_request_shape():
    for change,code in ((lambda plan:plan.update(groups=['SUPERVISOR','RETENTION_TAG']),'GROUPS_INVALID'),(lambda plan:plan.update(groups=None),'GROUPS_INVALID'),
                        (lambda plan:plan.update(groups=[]),'GROUPS_INVALID'),(lambda plan:plan.update(unit_names=[]),'UNIT_NAME_INVALID'),
                        (lambda plan:plan.update(unit_names=['docker.service']),'UNIT_NAME_INVALID'),(lambda plan:plan.update(unit_names=['c3po-a.service']*2),'UNIT_NAME_INVALID'),
                        (lambda plan:plan.update(unit_names=None),'UNIT_NAME_INVALID'),(lambda plan:plan.update(image_reference='c3po/backend:rollback'),'IMAGE_REFERENCE_INVALID'),
                        (lambda plan:plan.update(image_reference=None),'IMAGE_REFERENCE_INVALID'),(lambda plan:plan.update(data_volume_path=None),'PATH_INVALID'),
                        (lambda plan:plan.update(data_volume_path='/etc'),'PATH_FORBIDDEN_ZONE'),(lambda plan:plan.update(journal_leaf=None),'LEAF_INVALID'),
                        (lambda plan:plan.update(data_volume_path='/var/lib'),'PATH_FORBIDDEN_ZONE'),(lambda plan:plan.update(data_volume_path='/var'),'PATH_FORBIDDEN_ZONE'),
                        (lambda plan:plan.update(existing_journal_leaves=None),'LEAF_INVALID'),(lambda plan:plan.update(existing_journal_leaves=[f.LEAF]),'LEAF_INVALID'),
                        (lambda plan:plan.update(journal_placement=None),'PLACEMENT_UNKNOWN'),(lambda plan:plan.update(journal_placement='C'),'PLACEMENT_UNKNOWN'),
                        (lambda plan:plan.update(capacity={'root_path':None,'receipt_directory_path':None}),'PATH_INVALID')):
        host,docs=fresh();change(docs.plan);docs.chain();assert refusal(docs.authenticate)==code
        result=docs.run(host);assert (result['status'],result['code'],result['outcome'])==('REFUSED',code,'REFUSED_NOTHING_OBSERVED') and host.log==[]
    host,docs=fresh(groups=['JOURNAL_LEAF']);receipt=run(host,docs)
    assert sorted(receipt['items']['chains'])==['DATA_VOLUME','UNIT_DIRECTORY'] and list(receipt['items']['destinations'])==['SUP_JOURNAL']
    host,docs=fresh(capacity={'root_path':'/srv/c3po-capacity','receipt_directory_path':'/srv/c3po-capacity/receipts'});host.tree.add('/srv')
    receipt=run(host,docs);assert receipt['items']['chains']['CAPACITY_PARENT']['rows']==hostemu.rows(host,'/srv')

def test_window_expiry_during_the_precheck_keeps_what_was_read(monkeypatch):
    host,docs=fresh();wall=[f.NOW];calls=[0]
    def clock():
        calls[0]+=1
        if calls[0]>60:wall[0]=f.NOW+timedelta(minutes=6)
        return wall[0]
    receipt=docs.run(host,clock=clock)
    assert (receipt['status'],receipt['outcome'])==(m.PARTIAL_STATUS,'PARTIAL_OR_WINDOW_EXPIRED') and receipt['items']['boot']['status']=='COMPLETE' and host.commands==[]
    monkeypatch.setattr(m,'RECEIPT_LIMIT',6000);host,docs=fresh();receipt=docs.run(host)
    assert receipt['status']==m.PARTIAL_STATUS and receipt['outcome']=='PARTIAL_OBSERVED' and receipt['size_reductions'] and f.sealed(receipt)
