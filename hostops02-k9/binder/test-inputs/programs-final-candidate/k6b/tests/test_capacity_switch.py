"""K6b, the complete runs: for each mode, what is on the host afterwards, the exact commands, what the editor was
given, what the worker carries, and that nothing of the environment file or of any environment leaves the run."""
import json

import pytest

import family as f
import hostemu
import k6b

MODES=('MOUNT','ENABLE','DISABLE_FAST','DISABLE_FULL')

def complete(mode,**options):
    m,docs,host=k6b.fresh(mode,**options);before_env=k6b.env_bytes(host);old=k6b.worker(host)['Id']
    receipt=docs.run(host)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('METADATA_ONLY_REQUIRES_REVIEW',m.COMPLETE_OUTCOME,None),receipt.get('code')
    return m,docs,host,receipt,before_env,old

@pytest.mark.parametrize('mode',MODES)
def test_each_mode_edits_the_block_and_recreates_the_worker(mode):
    m,docs,host,receipt,before,old=complete(mode)
    count=k6b.AFTER[mode]
    assert k6b.env_bytes(host)==k6b.base_env(host)+''.join(line+'\n' for line in k6b.BLOCK[:count]).encode()
    assert k6b.env_bytes(host)[:len(k6b.base_env(host))]==before[:len(k6b.base_env(host))]          # every other byte as it was
    node=host.tree.get(hostemu.ENV_FILE);assert (node.uid,node.gid,node.mode,node.nlink)==(1000,1000,0o600,1)
    new=k6b.worker(host);assert new['Id']!=old and new['State']['Running'] and new['RestartCount']==0 and new['Image']==hostemu.BACKEND
    env=k6b.worker_env(host)
    for index,name in enumerate(k6b.CAPACITY_NAMES):
        if index<count:assert env[name]==k6b.BLOCK[index].split('=',1)[1]
        else:assert name not in env
    for name,value in k6b.ACTIVATION.items():assert env[name]==value
    assert env['C3PO_BUILD_SHA']==hostemu.REVISION
    capacity=[mount for mount in new['Mounts'] if mount['Destination']=='/c3po-capacity']
    assert capacity==([{'Type':'bind','Source':k6b.CAPACITY,'Destination':'/c3po-capacity','Mode':'ro','RW':False,'Propagation':'rprivate'}] if count
                      else [{'Type':'volume','Name':'c3po_c3po_capacity_unprovisioned','Source':'/var/lib/docker/volumes/c3po_c3po_capacity_unprovisioned/_data',
                             'Destination':'/c3po-capacity','Driver':'local','Mode':'z','RW':False,'Propagation':''}])
    assert receipt['mutating_calls']=={'issued':2,'succeeded':2,'failed_nothing_changed':0,'uncertain':0}
    assert receipt['env_edit']['state']=='EDITED' and receipt['env_edit']['status']=='ENV_EDIT_DONE' and receipt['env_withdraw']['state']=='NOT_STARTED'
    assert receipt['env_file_after']=='EDITED' and receipt['recreate']['state']=='RECREATED_VERIFIED' and receipt['worker_container_replaced'] is True
    assert receipt['mode']==mode and receipt['effects']==json.loads(f.canonical(m.effects_of(docs.plan)))
    assert all(value is True for key,value in receipt['recreate']['facts'].items()
               if key in ('worker_listed_once','worker_is_new','old_container_gone','running','image_is_the_signed_one','environment_as_signed',
                          'mounts_as_signed','others_unchanged','env_file_as_edited','compose_file_unchanged','override_unchanged','lock_still_named',
                          'settle_pause_taken','second_check_passed'))
    assert host.fds=={} and not host.lock_held(k6b.LOCK)

@pytest.mark.parametrize('mode',MODES)
def test_the_exact_commands_in_their_order(mode):
    m,docs,host,receipt,before,old=complete(mode)
    words=[entry['argv'] for entry in host.commands]
    docker=['/usr/bin/docker']
    files=['--project-name','c3po','--env-file',hostemu.ENV_FILE,'-f',hostemu.COMPOSE_FILE,'-f',k6b.OVERRIDE_FILE]
    edits=[argv for argv in words if argv[1:2]==['run']]
    assert edits==[docker+m.ENV_EDITOR_PREFIX+['--name','hostops02-k6b-'+docs.go16(),'--mount','type=bind,source=%s,target=/c3po-env/.env'%hostemu.ENV_FILE,
                                              hostemu.BACKEND,'python','-I','-B','-']]
    assert m.ENV_EDITOR_PREFIX==['run','--rm','-i','--pull','never','--init','--user','1000:1000','--network','none','--read-only','--cap-drop','ALL',
                                  '--security-opt','no-new-privileges']
    renders=[argv for argv in words if argv[1:2]==['compose'] and 'config' in argv]
    ups=[argv for argv in words if argv[1:2]==['compose'] and 'up' in argv]
    assert renders==[docker+['compose']+files+['config','--format','json']]*2
    assert ups==[docker+['compose']+files+['up','-d','--no-deps','--no-build','--pull','never','--force-recreate','r2d2-worker']]
    # the order: the first render before the lock, the edit, the render from the edited file, the recreate
    index=lambda argv:words.index(argv)
    first_render=words.index(renders[0]);second_render=len(words)-1-words[::-1].index(renders[1])
    assert first_render<index(edits[0])<second_render<index(ups[0])
    run=[entry for entry in host.commands if entry['argv'][1:2]==['run']][0]
    assert run['stdin']==m.editor_stdin(m.edit_spec(docs.plan)) and run['variables'] in (None,{}) and run['docker_config'] is None
    up=[entry for entry in host.commands if 'up' in entry['argv']][0]
    assert up['variables']=={'C3PO_BUILD_SHA':hostemu.REVISION} and up['stdin'] is None
    assert receipt['effects']['editor']['stdin_sha256']==f.sha(run['stdin'])

@pytest.mark.parametrize('mode',MODES)
def test_the_editor_is_given_signed_values_only(mode):
    m,docs,host,receipt,before,old=complete(mode)
    spec=host.editor.calls[0]
    assert spec=={'before':[k6b.BLOCK[:count] for count in ((1,4,5) if mode=='DISABLE_FULL' else (k6b.BEFORE[mode],))],'after':k6b.BLOCK[:k6b.AFTER[mode]],
                  'owner':[1000,1000],'mode':0o600}
    run=[entry for entry in host.commands if entry['argv'][1:2]==['run']][0]
    assert hostemu.SECRET.encode() not in run['stdin'] and f.sha(before).encode() not in run['stdin']
    assert run['stdin'].startswith(m.ENV_EDIT_SCRIPT.encode()) and f.sha(m.ENV_EDIT_SCRIPT.encode())==m.ENV_EDIT_SCRIPT_SHA256

@pytest.mark.parametrize('mode',MODES)
def test_nothing_of_the_environment_file_or_of_an_environment_leaves_the_run(mode):
    m,docs,host,receipt,before,old=complete(mode)
    text=json.dumps(receipt,sort_keys=True)
    after=k6b.env_bytes(host)
    for raw in (before,after,k6b.base_env(host)):
        assert f.sha(raw) not in text and ('"%d"'%len(raw)) not in text and (':%d,'%len(raw)) not in text.replace(' ','')
    assert hostemu.SECRET not in text and 'IMAGE_ENV' not in text
    for entry in host.commands:
        assert hostemu.SECRET not in ' '.join(entry['argv']) and f.sha(before) not in ' '.join(entry['argv'])

def test_disable_full_accepts_each_signed_state_and_says_which():
    for state in (1,4,5):
        m,docs,host=k6b.fresh('DISABLE_FULL',state=state);receipt=docs.run(host)
        assert receipt['outcome']==m.COMPLETE_OUTCOME and receipt['precheck']['capacity_lines_found']==state
        assert k6b.env_bytes(host)==k6b.base_env(host) and 'C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE' not in k6b.worker_env(host)

def test_enable_then_fast_disable_then_full_disable_on_one_host():
    """The week as signed: mount, enable, fast disable, full disable, each a request of its own on the same host."""
    m,docs,host=k6b.fresh('MOUNT');assert docs.run(host)['outcome']==m.COMPLETE_OUTCOME
    for mode in ('ENABLE','DISABLE_FAST','DISABLE_FULL'):
        docs=f.Docs(docs.k,k6b.fields(host,mode));receipt=docs.run(host);assert receipt['outcome']==m.COMPLETE_OUTCOME,(mode,receipt['code'])
    assert k6b.env_bytes(host)==k6b.base_env(host)

def test_a_worker_in_a_restart_loop_is_disabled():
    """Both disables are meant to work while the worker loops (README, Disable): not running, restarted, other start."""
    for mode in ('DISABLE_FAST','DISABLE_FULL'):
        m,docs,host=k6b.fresh(mode);worker=k6b.worker(host)
        worker['State'].update(Status='restarting',Running=False,Restarting=True);worker['RestartCount']=7
        receipt=docs.run(host);assert receipt['outcome']==m.COMPLETE_OUTCOME,receipt['code']
        assert receipt['precheck']['worker_running'] is False and k6b.worker(host)['RestartCount']==0

def test_the_receipt_says_what_was_found_before():
    m,docs,host,receipt,before,old=complete('ENABLE')
    p=receipt['precheck']
    assert p['capacity_lines_found']==1 and p['worker_running'] is True and p['worker_environment_as_found'] is True and p['worker_mounts_as_found'] is True
    assert p['override_as_delivered'] is True and p['capacity_tree_as_signed'] is True and p['reboot_pending'] is False
    assert p['worker']['id']==old and set(receipt['chains'])=={'DEPLOY_DIRECTORY','OVERRIDE_DIRECTORY','CAPACITY_ROOT','LOCK_DIRECTORY'}
    m,docs,host,receipt,before,old=complete('DISABLE_FAST')
    assert receipt['precheck']['capacity_tree_as_signed'] is None and 'CAPACITY_ROOT' not in receipt['chains']
