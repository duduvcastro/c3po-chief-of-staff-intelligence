"""The signed plan of K11: every member that is not as it must be is refused from the bytes, by the source and by the
dispatcher before any claim, and the effects the owner signs are exactly what the plan says."""
import ast
import json

import pytest

import family as f
import hostemu
import k11

def fresh(mode='PRE',**options):
    docs,host=k11.case(mode,**options);return docs.k.m,docs,host
def refused(docs,code):
    """The source refuses with this code, touches nothing, and says it in a sealed receipt."""
    docs.chain();assert f.refusal(docs.authenticate)==code
    receipt=docs.run(f.Untouchable());assert (receipt['status'],receipt['code'],receipt['outcome'],receipt['phase_reached'])==('REFUSED',code,'REFUSED_NOTHING_OBSERVED','AUTHENTICATION')
    assert f.sealed(receipt)
def put(plan,path,value):
    target=plan
    for key in path[:-1]:target=target[key]
    target[path[-1]]=value
def repack(section,raw,prefix):
    section[prefix+'b64' if prefix else 'content_b64']=k11.b64(raw);section[prefix+'sha256' if prefix else 'sha256']=f.sha(raw);section[prefix+'bytes' if prefix else 'bytes']=len(raw)

COMMON=[(['mode'],'DRY','MODE_INVALID'),(['mode'],None,'MODE_INVALID'),(['mode'],'pre','MODE_INVALID'),(['mode'],['PRE'],'MODE_INVALID'),
        (['evidence_boot_id_sha256'],'0'*64,'EVIDENCE_BOOT_UNBOUND'),(['evidence_boot_id_sha256'],None,'EVIDENCE_BOOT_UNBOUND'),
        (['revision'],'x','REVISION_OR_PACKAGE_UNBOUND'),(['revision'],k11.REVISION.upper(),'REVISION_OR_PACKAGE_UNBOUND'),(['revision'],k11.REVISION+'0','REVISION_OR_PACKAGE_UNBOUND'),
        (['package_sha256'],'0'*64,'REVISION_OR_PACKAGE_UNBOUND'),(['package_sha256'],None,'REVISION_OR_PACKAGE_UNBOUND'),
        (['rows_in_receipt'],1,'ROWS_FLAG_INVALID'),(['rows_in_receipt'],None,'ROWS_FLAG_INVALID'),
        (['image'],None,'IMAGE_PLAN_INVALID'),(['image','image_id'],'c3po/backend:production','IMAGE_PLAN_INVALID'),(['image','reference'],'a b','IMAGE_PLAN_INVALID'),
        (['image','extra'],1,'IMAGE_PLAN_INVALID'),(['image','reference'],'-c3po/backend:production','IMAGE_PLAN_INVALID'),
        (['live'],'x','LIVE_PLAN_INVALID'),(['live','extra'],1,'LIVE_PLAN_INVALID'),(['live','directory_name'],'..','LIVE_PLAN_INVALID'),(['live','directory_name'],'a/b','LIVE_PLAN_INVALID'),
        (['live','directory_name'],'.hidden','LIVE_PLAN_INVALID'),(['live','directory_name'],None,'LIVE_PLAN_INVALID'),(['live','parent'],None,'LIVE_PLAN_INVALID'),
        (['live','parent','path'],'/','LIVE_PLAN_INVALID'),(['live','parent','extra'],1,'LIVE_PLAN_INVALID'),(['live','parent','open_root'],None,'CHAIN_ROW_UNSAFE'),
        (['live','parent','rows'],[],'CHAIN_ROW_INVALID'),(['live','parent'],'DEPLOY','LIVE_OUTSIDE_THE_DATA_VOLUME'),
        (['limits'],'x','LIMITS_PLAN_INVALID'),(['limits'],{},'LIMITS_PLAN_INVALID'),(['limits'],dict(k11.LIMITS,extra=1),'LIMITS_PLAN_INVALID'),
        (['limits'],dict(k11.LIMITS,render_ms=0),'LIMITS_PLAN_INVALID'),(['limits'],dict(k11.LIMITS,render_ms=60001),'LIMITS_PLAN_INVALID'),(['limits'],dict(k11.LIMITS,render_ms=True),'LIMITS_PLAN_INVALID'),
        (['limits'],dict(k11.LIMITS,quick_ms=0),'LIMITS_PLAN_INVALID'),(['limits'],dict(k11.LIMITS,quick_ms=60001),'LIMITS_PLAN_INVALID'),(['limits'],dict(k11.LIMITS,quick_ms='1500'),'LIMITS_PLAN_INVALID'),
        (['limits'],dict(k11.LIMITS,data_volume_free_bytes=-1),'LIMITS_PLAN_INVALID'),(['limits'],dict(k11.LIMITS,data_volume_free_bytes=(1<<50)+1),'LIMITS_PLAN_INVALID'),
        (['limits'],{key:value for key,value in k11.LIMITS.items() if key!='quick_ms'},'LIMITS_PLAN_INVALID'),
        (['limits'],{key:value for key,value in k11.LIMITS.items() if key!='data_volume_free_inodes'},'LIMITS_PLAN_INVALID'),(['limits'],dict(k11.LIMITS,data_volume_free_inodes=-1),'LIMITS_PLAN_INVALID'),
        (['limits'],dict(k11.LIMITS,data_volume_free_inodes=(1<<50)+1),'LIMITS_PLAN_INVALID'),(['limits'],dict(k11.LIMITS,data_volume_free_inodes=8.0),'LIMITS_PLAN_INVALID'),
        (['worker'],None,'WORKER_PLAN_INVALID'),(['worker','container'],'a b','WORKER_PLAN_INVALID'),(['worker','container'],'a'*64,'WORKER_PLAN_INVALID'),
        (['worker','environment'],1,'WORKER_PLAN_INVALID'),(['worker','data_source'],'/','WORKER_PLAN_INVALID'),(['worker','data_target'],'app/day-d-data','WORKER_PLAN_INVALID'),
        (['worker','data_target'],'/app/../x','WORKER_PLAN_INVALID'),(['worker','extra'],1,'WORKER_PLAN_INVALID'),
        (['release'],None,'RELEASE_PLAN_INVALID'),(['release','sha256'],'0'*64,'RELEASE_PLAN_INVALID'),(['release','bytes'],0,'RELEASE_PLAN_INVALID'),
        (['release','bytes'],65537,'RELEASE_PLAN_INVALID'),(['release','bytes'],True,'RELEASE_PLAN_INVALID'),(['release','directory_name'],'..','RELEASE_PLAN_INVALID'),
        (['release','directory_name'],'.hidden','RELEASE_PLAN_INVALID'),(['release','directory_name'],'a/b','RELEASE_PLAN_INVALID'),(['release','file_name'],'','RELEASE_PLAN_INVALID'),
        (['release','file_name'],'x'*129,'RELEASE_PLAN_INVALID'),(['release','extra'],1,'RELEASE_PLAN_INVALID'),
        (['release','parent'],None,'RELEASE_PLAN_INVALID'),(['release','parent','path'],'/','RELEASE_PLAN_INVALID'),(['release','parent','open_root'],'/opt','RELEASE_PLAN_INVALID'),
        (['release','parent','open_root'],'/','RELEASE_PLAN_INVALID'),(['release','parent','extra'],1,'RELEASE_PLAN_INVALID'),
        (['release','parent','open_root'],None,'CHAIN_ROW_UNSAFE'),(['release','parent','rows'],[],'CHAIN_ROW_INVALID'),(['release','parent','rows'],'x','CHAIN_ROW_INVALID'),
        (['deploy'],None,'DEPLOY_PLAN_INVALID'),(['deploy','version_name'],'..','DEPLOY_PLAN_INVALID'),(['deploy','version_name'],'a/b','DEPLOY_PLAN_INVALID'),
        (['deploy','version_name'],None,'DEPLOY_PLAN_INVALID'),(['deploy','lock_name'],'.','DEPLOY_PLAN_INVALID'),(['deploy','lock_name'],'a b','DEPLOY_PLAN_INVALID'),
        (['deploy','extra'],1,'DEPLOY_PLAN_INVALID'),(['deploy','tree','path'],'/','DEPLOY_PLAN_INVALID'),(['deploy','tree','open_root'],None,'CHAIN_ROW_UNSAFE'),
        (['deploy','lock_directory','open_root'],None,'CHAIN_ROW_UNSAFE'),(['deploy','lock_directory'],None,'DEPLOY_PLAN_INVALID'),
        (['units'],None,'UNITS_PLAN_INVALID'),(['units'],[{'name':'unit%d.service'%index,'expected':None} for index in range(9)],'UNITS_PLAN_INVALID'),
        (['units'],[{'name':'-x.service','expected':None}],'UNITS_PLAN_INVALID'),(['units'],[{'name':'a.socket','expected':None}],'UNITS_PLAN_INVALID'),
        (['units'],[{'name':'a.service','expected':None}]*2,'UNITS_PLAN_INVALID'),(['units'],[{'name':'a.service'}],'UNITS_PLAN_INVALID'),
        (['units'],[{'name':'a.service','expected':{}}],'UNITS_PLAN_INVALID'),(['units'],[{'name':'a.service','expected':{'Id':'a.service'}}],'UNITS_PLAN_INVALID'),
        (['units'],[{'name':'a.service','expected':{'FragmentPath':'x'}}],'UNITS_PLAN_INVALID'),(['units'],[{'name':'a.service','expected':{'TriggeredBy':''}}],'UNITS_PLAN_INVALID'),
        (['release','parent'],{'path':'/','rows':None,'open_root':None},'RELEASE_PLAN_INVALID'),(['deploy','tree'],{'path':'/','rows':None,'open_root':None},'DEPLOY_PLAN_INVALID'),
        (['units'],[{'name':'a.service','expected':{'ActiveState':'in active'}}],'UNITS_PLAN_INVALID'),(['units'],[{'name':'a.service','expected':{'ActiveState':None}}],'UNITS_PLAN_INVALID'),
        (['units'],[{'name':'a.service','expected':'inactive'}],'UNITS_PLAN_INVALID'),(['units'],['a.service'],'UNITS_PLAN_INVALID'),
        (['journal'],{'path':'/','floor_bytes':None},'JOURNAL_PLAN_INVALID'),(['journal'],{'path':'var/lib','floor_bytes':None},'JOURNAL_PLAN_INVALID'),
        (['journal'],{'path':k11.JOURNAL,'floor_bytes':-1},'JOURNAL_PLAN_INVALID'),(['journal'],{'path':k11.JOURNAL,'floor_bytes':True},'JOURNAL_PLAN_INVALID'),
        (['journal'],{'path':k11.JOURNAL,'floor_bytes':(1<<50)+1},'JOURNAL_PLAN_INVALID'),(['journal'],{'path':k11.JOURNAL},'JOURNAL_PLAN_INVALID'),(['journal'],k11.JOURNAL,'JOURNAL_PLAN_INVALID'),
        (['docker_config'],'relative','DOCKER_CONFIG_INVALID'),(['docker_config'],'/a/../b','DOCKER_CONFIG_INVALID'),(['docker_config'],5,'DOCKER_CONFIG_INVALID'),
        (['docker_config'],'/a=b','DOCKER_CONFIG_INVALID'),(['docker_config'],k11.DOCKER_CONFIG,'DOCKER_CONFIG_ONLY_IN_A_REDUCED_DRY_RUN')]
PRE_ONLY=[(['release','container_target'],k11.TARGET,'RELEASE_PLAN_INVALID'),(['release','directory_entries'],1,'RELEASE_PLAN_INVALID'),
          (['release','content_b64'],None,'RELEASE_NOT_THE_SIGNED_BYTES'),(['release','content_b64'],'not base64 !','RELEASE_NOT_THE_SIGNED_BYTES'),
          (['release','content_b64'],k11.b64(k11.RELEASE)[:16]+'\n'+k11.b64(k11.RELEASE)[16:],'RELEASE_NOT_THE_SIGNED_BYTES'),
          (['release','content_b64'],k11.b64(k11.RELEASE)[:16]+' '+k11.b64(k11.RELEASE)[16:],'RELEASE_NOT_THE_SIGNED_BYTES'),
          (['release','sha256'],'3'*64,'RELEASE_NOT_THE_SIGNED_BYTES'),(['release','bytes'],len(k11.RELEASE)+1,'RELEASE_NOT_THE_SIGNED_BYTES'),
          (['render'],None,'RENDER_REQUIRED'),(['render','extra'],1,'RENDER_PLAN_INVALID'),(['render'],'x','RENDER_PLAN_INVALID'),
          (['render','override_sha256'],'3'*64,'OVERRIDE_NOT_THE_SIGNED_BYTES'),(['render','override_bytes'],1,'OVERRIDE_NOT_THE_SIGNED_BYTES'),
          (['render','override_b64'],'@@','OVERRIDE_NOT_THE_SIGNED_BYTES'),(['render','project'],'C3PO','COMPOSE_PROJECT'),(['render','files'],[],'COMPOSE_FILES'),
          (['render','files'],['relative.yml'],'COMPOSE_FILES'),(['render','env_file'],'/etc/environment','RENDER_OUTSIDE_THE_DEPLOY_TREE'),
          (['render','files'],[hostemu.COMPOSE_FILE,'/tmp/other.yml'],'RENDER_OUTSIDE_THE_DEPLOY_TREE'),(['render','files'],[hostemu.DEPLOY],'RENDER_OUTSIDE_THE_DEPLOY_TREE'),
          (['policy','extra'],1,'POLICY_PLAN_INVALID'),(['policy'],'x','POLICY_PLAN_INVALID'),(['policy','sha256'],'3'*64,'POLICY_NOT_THE_SIGNED_BYTES'),
          (['policy','bytes'],8193,'POLICY_NOT_THE_SIGNED_BYTES'),(['policy','valid_at'],[],'POLICY_PLAN_INVALID'),(['policy','valid_at'],k11.VALID_AT+['2026-10-06T00:00:00+00:00','2026-10-07T00:00:00+00:00'],'POLICY_PLAN_INVALID'),
          (['policy','valid_at'],[k11.VALID_AT[0]]*2,'POLICY_PLAN_INVALID'),(['policy','valid_at'],[20261005],'POLICY_PLAN_INVALID'),(['policy','valid_at'],'2026-10-05T08:45:00+00:00','POLICY_PLAN_INVALID'),
          (['policy','valid_at'],['2026-10-05T08:45:00Z'],'POLICY_PLAN_INVALID'),(['policy','valid_at'],['2026-10-05T08:45:00.000000+00:00'],'POLICY_PLAN_INVALID'),
          (['policy','valid_at'],['2026-10-05T05:45:00-03:00'],'POLICY_WINDOW'),(['policy','valid_at'],['2026-10-05T08:45:00'],'POLICY_WINDOW'),(['policy','valid_at'],['monday'],'POLICY_WINDOW'),
          (['policy','valid_at'],['2026-10-01T23:59:59+00:00'],'POLICY_WINDOW'),(['policy','valid_at'],['2026-10-10T00:00:00+00:00'],'POLICY_WINDOW'),
          (['deploy','lock_directory'],'DATA','DEPLOY_PLAN_INVALID'),
          (['dry_run'],None,'DRY_RUN_PROFILE_INVALID'),(['dry_run'],'full','DRY_RUN_PROFILE_INVALID'),(['dry_run'],'PARTIAL','DRY_RUN_PROFILE_INVALID'),(['dry_run'],['FULL'],'DRY_RUN_PROFILE_INVALID'),
          (['dry_run'],True,'DRY_RUN_PROFILE_INVALID'),
          # the full dry run: every member Monday will meet is signed, the places are install_release's, the layout is activate's
          (['policy'],None,'DRY_RUN_NOT_THE_FULL_PROFILE'),(['bind_probe'],None,'DRY_RUN_NOT_THE_FULL_PROFILE'),(['live'],None,'DRY_RUN_NOT_THE_FULL_PROFILE'),
          (['limits'],None,'DRY_RUN_NOT_THE_FULL_PROFILE'),(['worker','environment'],False,'DRY_RUN_NOT_THE_FULL_PROFILE'),
          (['deploy','version_name'],'.deploy-revision','DRY_RUN_NOT_THE_LAYOUT_OF_ACTIVATE'),
          (['deploy','lock_name'],'deploy.lock','DRY_RUN_NOT_THE_LAYOUT_OF_ACTIVATE'),(['deploy','lock_name'],None,'DRY_RUN_NOT_THE_LAYOUT_OF_ACTIVATE'),
          (['deploy','lock_directory'],'RUNTIME','DRY_RUN_NOT_THE_LAYOUT_OF_ACTIVATE'),(['worker','container'],'c3po-r2d2-worker-2','DRY_RUN_NOT_THE_LAYOUT_OF_ACTIVATE'),
          (['render','env_file'],hostemu.DEPLOY+'/c3po/.env','DRY_RUN_NOT_THE_LAYOUT_OF_ACTIVATE'),(['render','files'],[hostemu.DEPLOY+'/docker-compose.yml'],'DRY_RUN_NOT_THE_LAYOUT_OF_ACTIVATE'),
          (['render','files'],[hostemu.COMPOSE_FILE,hostemu.DEPLOY+'/c3po/compose.override.yml'],'DRY_RUN_NOT_THE_LAYOUT_OF_ACTIVATE'),(['render','project'],'c3po2','DRY_RUN_NOT_THE_LAYOUT_OF_ACTIVATE')]
POST_ONLY=[(['release','content_b64'],k11.b64(k11.RELEASE),'RELEASE_PLAN_INVALID'),(['release','container_target'],None,'RELEASE_PLAN_INVALID'),
           (['release','container_target'],'/app','RELEASE_PLAN_INVALID'),(['release','container_target'],'/c3po-x/y','RELEASE_PLAN_INVALID'),
           (['release','container_target'],'/c3po-','RELEASE_PLAN_INVALID'),(['release','container_target'],'/c3po-X','RELEASE_PLAN_INVALID'),
           (['release','directory_entries'],0,'RELEASE_PLAN_INVALID'),(['release','directory_entries'],9,'RELEASE_PLAN_INVALID'),(['release','directory_entries'],True,'RELEASE_PLAN_INVALID'),
           (['release','directory_entries'],None,'RELEASE_PLAN_INVALID'),(['policy'],None,'POLICY_REQUIRED'),
           (['dry_run'],'FULL','DRY_RUN_PROFILE_INVALID'),(['dry_run'],'REDUCED','DRY_RUN_PROFILE_INVALID'),(['dry_run'],False,'DRY_RUN_PROFILE_INVALID')]

@pytest.mark.parametrize('mode',['PRE','POST'])
@pytest.mark.parametrize('path,value,code',COMMON)
def test_every_member_of_the_plan_that_is_not_as_it_must_be_is_refused_in_both_modes(mode,path,value,code):
    m,docs,host=fresh(mode)
    if value=='DATA' and path==['deploy','lock_directory']:value=k11.chain(host,hostemu.DATA,hostemu.DATA)
    if value=='DEPLOY' and path==['live','parent']:value=k11.chain(host,hostemu.DEPLOY,hostemu.DEPLOY)
    put(docs.plan,path,value);refused(docs,code)

@pytest.mark.parametrize('path,value,code',PRE_ONLY)
def test_members_of_the_dry_run_plan(path,value,code):
    m,docs,host=fresh('PRE')
    if value=='DATA':value=k11.chain(host,hostemu.DATA,hostemu.DATA)       # a lock directory outside the deploy tree
    if value=='RUNTIME':value=k11.chain(host,hostemu.DEPLOY+'/runtime',hostemu.DEPLOY)      # inside the tree, not the directory of the deployment lock
    put(docs.plan,path,value);refused(docs,code)

@pytest.mark.parametrize('path,value,code',POST_ONLY)
def test_members_of_the_readback_plan(path,value,code):
    m,docs,host=fresh('POST');put(docs.plan,path,value);refused(docs,code)

def test_modes_fix_what_the_plan_must_carry_and_what_it_may_leave_out():
    """PRE needs the release bytes and the render; signed as FULL it also needs the policy, the probe of the bind, the
    live directory, the limits and the worker's environment, and takes no docker configuration directory. Signed as
    REDUCED it may leave any of them out, and then succeeds under another name. POST needs the installed place and the
    policy; a render, the live directory, limits, units, the journal and the lock are the signers' choice."""
    m,docs,host=fresh('PRE');docs.authenticate();assert docs.plan['dry_run']=='FULL' and docs.go['success_criterion']==m.PRE_OUTCOME
    assert docs.go['effects']['dry_run']=='FULL' and docs.go['effects']['rehearses_install_release_and_activate'] is True
    m,docs,host=fresh('PRE',policy=None,environment=False,lock=False,probe=None,live=False,limits=None);docs.authenticate()
    assert docs.plan['policy'] is None and docs.go['effects']['policy'] is None and docs.go['effects']['deploy']['lock'] is None
    assert (docs.plan['dry_run'],docs.go['success_criterion'])==('REDUCED',m.PRE_REDUCED_OUTCOME) and docs.go['effects']['rehearses_install_release_and_activate'] is False
    assert (docs.go['effects']['live'],docs.go['effects']['limits'],docs.go['effects']['bind_probe'])==(None,None,None)
    # a plan that carries the whole profile may still be signed as REDUCED; it is then not the rehearsal either
    m,docs,host=fresh('PRE',dry_run='REDUCED');docs.authenticate();assert docs.go['success_criterion']==m.PRE_REDUCED_OUTCOME and docs.go['effects']['rehearses_install_release_and_activate'] is False
    m,docs,host=fresh('PRE',docker_config=k11.DOCKER_CONFIG);docs.authenticate();assert docs.plan['dry_run']=='REDUCED','only a reduced dry run signs a docker configuration directory'
    m,docs,host=fresh('POST',render=False);docs.authenticate();assert docs.go['effects']['render'] is None and docs.go['effects']['dry_run'] is None
    m,docs,host=fresh('POST',render=True,units=k11.UNITS,journal=k11.JOURNAL,floor=1,limits=dict(k11.LIMITS));docs.authenticate()
    m,docs,host=fresh('POST',live=False);docs.authenticate();assert docs.go['effects']['live'] is None and docs.go['effects']['rehearses_install_release_and_activate'] is False
    m,docs,host=fresh('PRE',signed_rows=False);docs.authenticate()
    assert docs.go['effects']['release']['parent']=={'path':hostemu.DATA,'open_root':hostemu.DATA,'rows_signed':False,'row':None,'chain_sha256':None,'mount_point_by_device_change':None}

def test_chain_rows_are_the_family_s_rule_and_a_row_that_no_write_could_sign_is_refused():
    m,docs,host=fresh('PRE');docs.plan['release']['parent']['rows'][-1]['mode']=0o777;refused(docs,'CHAIN_ROW_WORLD_WRITABLE')
    m,docs,host=fresh('PRE');docs.plan['deploy']['tree']['rows'][1]['uid']=1000;refused(docs,'CHAIN_ROW_UNSAFE')          # /opt itself must be root's
    m,docs,host=fresh('PRE');docs.plan['deploy']['tree']['rows'][-1]['path']='/opt/other';refused(docs,'CHAIN_ROW_INVALID')
    m,docs,host=fresh('PRE');docs.plan['deploy']['lock_directory']['rows'].pop();refused(docs,'CHAIN_ROW_INVALID')
    m,docs,host=fresh('PRE');docs.plan['release']['parent']['rows'][-1]['inode']=0;refused(docs,'CHAIN_ROW_INVALID')

@pytest.mark.parametrize('mode',['PRE','POST'])
def test_names_that_are_each_valid_but_make_a_path_no_request_can_sign_are_refused(mode):
    m,docs,host=fresh(mode);docs.plan['release']['directory_name']='d'*120;docs.plan['release']['file_name']='f'*100;refused(docs,'RELEASE_PLAN_INVALID')

def test_release_place_is_inside_the_data_volume_the_worker_sees():
    m,docs,host=fresh('PRE');docs.plan['release']['parent']=k11.chain(host,hostemu.DEPLOY,hostemu.DEPLOY);refused(docs,'RELEASE_OUTSIDE_THE_DATA_VOLUME')
    m,docs,host=fresh('PRE');docs.plan['worker']['data_source']='/mnt/day-d';refused(docs,'RELEASE_OUTSIDE_THE_DATA_VOLUME')      # a prefix of the name is not the directory
    m,docs,host=fresh('PRE',dry_run='REDUCED');host.tree.add(hostemu.DATA+'/releases',uid=0,gid=0,mode=0o700,dev=hostemu.DATA_DEVICE)
    docs.plan['release']['parent']=k11.chain(host,hostemu.DATA+'/releases',hostemu.DATA)
    raw=k11.override_bytes(**{k11.KEYS[2]:k11.DATA_TARGET+'/releases/'+k11.RELEASE_DIRECTORY+'/'+k11.RELEASE_FILE});repack(docs.plan['render'],raw,'override_')
    docs.chain();docs.authenticate()
    assert docs.go['effects']['release']['path_in_the_worker']=='/app/day-d-data/releases/r2d2-v2-release-20261005/release.CERTIFIED.json'
    assert docs.go['effects']['release']['path']=='/mnt/day-d-data/releases/r2d2-v2-release-20261005/release.CERTIFIED.json'
    docs.plan['dry_run']='FULL';refused(docs,'DRY_RUN_NOT_THE_PLACES_OF_INSTALL_RELEASE')        # install_release creates in the root of the data volume
    m,docs,host=fresh('POST',signed_rows=False);docs.plan['release']['parent']['path']=hostemu.DATA+'/a=b';refused(docs,'MOUNT_INVALID')   # a bind source docker's --mount cannot spell

@pytest.mark.parametrize('change,code',[(dict(schema='R2D2_V2_RELEASE_V2'),'RELEASE_SCOPE'),(dict(mode='DIAGNOSTIC'),'RELEASE_SCOPE'),(dict(epoch='R2D2-V2-SHADOW-2026-09-28'),'RELEASE_SCOPE'),
                                        (dict(first_session='2026-10-06'),'RELEASE_SCOPE'),(dict(code_revision='0'*40),'RELEASE_SCOPE'),(dict(implementation_package_sha='a'*64),'RELEASE_SCOPE')])
def test_release_bytes_of_the_dry_run_name_this_epoch_this_revision_and_this_package(change,code):
    m,docs,host=fresh('PRE');raw=k11.release_bytes(**change);repack(docs.plan['release'],raw,'')
    policy=k11.policy_bytes(raw);repack(docs.plan['policy'],policy,'');repack(docs.plan['render'],k11.override_bytes(raw,policy),'override_')
    refused(docs,code)

def test_release_bytes_must_be_one_json_object_and_fit_the_request():
    for raw in (b'[]',b'{"schema":"R2D2_V2_RELEASE_V3","schema":"R2D2_V2_RELEASE_V3"}',b'not json',b'{"x":NaN}'):
        m,docs,host=fresh('PRE');repack(docs.plan['release'],raw,'');refused(docs,'RELEASE_INVALID')
    m,docs,host=fresh('PRE');big=k11.release_bytes(pad='x'*(m.MAX_RELEASE_BYTES));assert len(big)>m.MAX_RELEASE_BYTES
    repack(docs.plan['release'],big,'');refused(docs,'RELEASE_NOT_THE_SIGNED_BYTES')
    m,docs,host=fresh('PRE');exact=k11.release_bytes(pad='x');exact=k11.release_bytes(pad='x'*(m.MAX_RELEASE_BYTES-len(exact)+1));assert len(exact)==m.MAX_RELEASE_BYTES
    policy=k11.policy_bytes(exact);repack(docs.plan['release'],exact,'');repack(docs.plan['policy'],policy,'');repack(docs.plan['render'],k11.override_bytes(exact,policy),'override_')
    docs.chain();docs.authenticate();assert len(docs.raw()[0])<=65536,'the largest release the plan accepts still fits a signed document'

@pytest.mark.parametrize('change,code',[(dict(schema='OTHER'),'POLICY_SCOPE'),(dict(mode='PROOF'),'POLICY_SCOPE'),(dict(epoch='R2D2-V2-SHADOW-2026-09-28'),'POLICY_SCOPE'),
                                        (dict(release_sha='a'*64),'POLICY_SCOPE'),(dict(code_revision='0'*40),'POLICY_SCOPE'),(dict(package_sha='a'*64),'POLICY_SCOPE'),
                                        (dict(order_sha='a'*64),'POLICY_SCOPE'),(dict(valid_from='2026-10-05T09:00:00+00:00'),'POLICY_WINDOW'),
                                        (dict(valid_until='2026-10-09T19:59:59+00:00'),'POLICY_WINDOW'),(dict(valid_from='2026-10-11T00:00:00+00:00'),'POLICY_WINDOW'),
                                        (dict(valid_from='2026-10-02T00:00:00'),'POLICY_WINDOW'),(dict(valid_from=None),'POLICY_WINDOW'),(dict(valid_until='never'),'POLICY_WINDOW')])
@pytest.mark.parametrize('mode',['PRE','POST'])
def test_policy_candidate_names_this_epoch_release_revision_package_and_order_and_covers_every_signed_instant(mode,change,code):
    m,docs,host=fresh(mode,render=True);raw=k11.policy_bytes(**change);repack(docs.plan['policy'],raw,'')
    repack(docs.plan['render'],k11.override_bytes(policy=raw),'override_');refused(docs,code)

def test_policy_window_holds_its_first_instant_and_not_its_last():
    m,docs,host=fresh('POST');docs.plan['policy']['valid_at']=['2026-10-02T00:00:00+00:00','2026-10-09T23:59:59.999999+00:00'];docs.chain();docs.authenticate()
    docs.plan['policy']['valid_at']=['2026-10-10T00:00:00+00:00'];refused(docs,'POLICY_WINDOW')

def test_policy_bytes_must_be_one_json_object_and_a_z_suffix_in_the_policy_is_read():
    for raw in (b'[]',b'{"a":1,"a":1}',b'x'):
        m,docs,host=fresh('POST');repack(docs.plan['policy'],raw,'');refused(docs,'POLICY_INVALID')
    m,docs,host=fresh('POST');raw=k11.policy_bytes(valid_from='2026-10-02T00:00:00Z',valid_until='2026-10-10T00:00:00Z');repack(docs.plan['policy'],raw,'')
    docs.chain();docs.authenticate()

OVERRIDES=[({'services':{'r2d2-worker':{'environment':{}}}},'OVERRIDE_INVALID'),({'services':{}},'OVERRIDE_INVALID'),({'services':None},'OVERRIDE_INVALID'),
           ({'services':{'r2d2-worker':None}},'OVERRIDE_INVALID'),({'services':{'r2d2-worker':{'environment':None}}},'OVERRIDE_INVALID'),({},'OVERRIDE_INVALID')]
def test_override_is_exactly_the_four_live_names_of_the_worker_service():
    good=json.loads(k11.override_bytes());environment=good['services']['r2d2-worker']['environment']
    cases=list(OVERRIDES)+[(dict(good,name='c3po'),'OVERRIDE_INVALID'),({'services':dict(good['services'],api={'environment':{}})},'OVERRIDE_INVALID'),
        ({'services':{'r2d2-worker':{'environment':environment,'image':'c3po/backend:rollback'}}},'OVERRIDE_INVALID'),
        ({'services':{'r2d2-worker':{'environment':dict(environment,C3PO_R2D2_V2_SHADOW_ENABLED='true')}}},'OVERRIDE_INVALID'),
        ({'services':{'r2d2-worker':{'environment':{key:value for key,value in environment.items() if key!=k11.KEYS[1]}}}},'OVERRIDE_INVALID'),
        ({'services':{'r2d2-worker':{'environment':dict(environment,**{k11.KEYS[0]:''})}}},'OVERRIDE_INVALID'),
        ({'services':{'r2d2-worker':{'environment':dict(environment,**{k11.KEYS[0]:'/app/day-d-data/a b'})}}},'OVERRIDE_INVALID'),
        ({'services':{'r2d2-worker':{'environment':dict(environment,**{k11.KEYS[3]:None})}}},'OVERRIDE_INVALID'),
        ({'services':{'r2d2-worker':{'environment':dict(environment,**{k11.KEYS[3]:'a'*64})}}},'OVERRIDE_RELEASE_BINDING'),
        ({'services':{'r2d2-worker':{'environment':dict(environment,**{k11.KEYS[2]:'/app/day-d-data/other/release.CERTIFIED.json'})}}},'OVERRIDE_RELEASE_BINDING'),
        ({'services':{'r2d2-worker':{'environment':dict(environment,**{k11.KEYS[2]:k11.RELEASE_HOST+'/'+k11.RELEASE_FILE})}}},'OVERRIDE_RELEASE_BINDING'),
        ({'services':{'r2d2-worker':{'environment':dict(environment,**{k11.KEYS[0]:'/etc/policy.json'})}}},'OVERRIDE_POLICY_BINDING'),
        ({'services':{'r2d2-worker':{'environment':dict(environment,**{k11.KEYS[0]:k11.DATA_TARGET})}}},'OVERRIDE_POLICY_BINDING'),
        ({'services':{'r2d2-worker':{'environment':dict(environment,**{k11.KEYS[0]:k11.DATA_TARGET+'/../x'})}}},'OVERRIDE_POLICY_BINDING'),
        ({'services':{'r2d2-worker':{'environment':dict(environment,**{k11.KEYS[1]:'a'*64})}}},'OVERRIDE_POLICY_BINDING'),
        ({'services':{'r2d2-worker':{'environment':dict(environment,**{k11.KEYS[1]:'0'*64})}}},'OVERRIDE_POLICY_BINDING'),
        ({'services':{'r2d2-worker':{'environment':dict(environment,**{k11.KEYS[1]:'nothex'})}}},'OVERRIDE_POLICY_BINDING')]
    for body,code in cases:
        m,docs,host=fresh('PRE');repack(docs.plan['render'],f.canonical(body),'override_');refused(docs,code)
    for raw in (b'[]',b'services: {}',b'{"services":{},"services":{}}'):
        m,docs,host=fresh('PRE');repack(docs.plan['render'],raw,'override_');refused(docs,'OVERRIDE_INVALID')
    # without a policy in the plan the policy hash of the override is still a hash, and is compared with nothing
    m,docs,host=fresh('PRE',policy=None);docs.authenticate()
    body=json.loads(k11.override_bytes());body['services']['r2d2-worker']['environment'][k11.KEYS[1]]='nothex'
    repack(docs.plan['render'],f.canonical(body),'override_');refused(docs,'OVERRIDE_POLICY_BINDING')

def test_frame_fits_standard_input_and_holds_only_signed_values(monkeypatch):
    m,docs,host=fresh('PRE');frame=m.frame_of(docs.plan,'9'*64);head,_,rest=frame.partition(b'\n')
    assert head.startswith(b'SIGNED_CONTEXT=') and rest==m.VERIFY_SNIPPET.encode('ascii') and len(frame)<=m.MAX_STDIN_BYTES
    context=ast.literal_eval(head[len(b'SIGNED_CONTEXT='):].decode('ascii'))
    assert context=={'request_sha256':'9'*64,'revision':k11.REVISION,'package_sha256':k11.PACKAGE,'epoch':k11.EPOCH,'first_session':k11.FIRST,
                     'release_sha256':f.sha(k11.RELEASE),'release_bytes':len(k11.RELEASE),'release_b64':k11.b64(k11.RELEASE),'release_path':None,
                     'policy_b64':k11.b64(k11.POLICY),'policy_sha256':f.sha(k11.POLICY),'policy_valid_at':k11.VALID_AT,'probe_path':k11.PROBE_TARGET+'/'+k11.RELEASE_FILE}
    m,post,host=fresh('POST');context=ast.literal_eval(m.frame_of(post.plan,'9'*64).partition(b'\n')[0][len(b'SIGNED_CONTEXT='):].decode('ascii'))
    assert context['release_b64'] is None and context['release_path']==k11.TARGET+'/'+k11.RELEASE_FILE and context['probe_path'] is None
    m,none,host=fresh('PRE',policy=None);context=ast.literal_eval(m.frame_of(none.plan,'9'*64).partition(b'\n')[0][len(b'SIGNED_CONTEXT='):].decode('ascii'))
    assert (context['policy_b64'],context['policy_sha256'],context['policy_valid_at'])==(None,None,[])
    monkeypatch.setattr(m,'MAX_STDIN_BYTES',len(frame)-1);refused(docs,'VERIFY_FRAME_TOO_LARGE')
    monkeypatch.setattr(m,'MAX_STDIN_BYTES',len(frame));docs.authenticate()

def test_effects_are_exactly_what_the_plan_says_in_both_modes():
    m,docs,host=fresh('PRE',units=k11.UNITS,journal=k11.JOURNAL,floor=7,rows_in_receipt=True);effects=docs.go['effects']
    override=json.loads(k11.override_bytes())['services']['r2d2-worker']['environment']
    def chain(path,root):
        rows=hostemu.rows(host,path)
        return {'path':path,'row':rows[-1],'chain_sha256':f.sha(f.canonical(rows)),'mount_point_by_device_change':hostemu.DATA if path.startswith(hostemu.DATA) else '/','open_root':root,'rows_signed':True}
    expected={'operation':'GO_READONLY_HOSTOPS02_EPOCH_READBACK_01','mode':'PRE','gates_first_session_readback':False,'epoch':k11.EPOCH,'first_session':k11.FIRST,
              'revision':k11.REVISION,'package_sha256':k11.PACKAGE,'image':{'reference':'c3po/backend:production','image_id':hostemu.BACKEND},
              'worker':{'container':hostemu.WORKER,'environment':True,'data_source':hostemu.DATA,'data_target':k11.DATA_TARGET},
              'release':{'sha256':f.sha(k11.RELEASE),'bytes':len(k11.RELEASE),'path':k11.RELEASE_HOST+'/'+k11.RELEASE_FILE,
                         'path_in_the_worker':k11.DATA_TARGET+'/'+k11.RELEASE_DIRECTORY+'/'+k11.RELEASE_FILE,'source':'THE_BYTES_OF_THE_REQUEST_ON_STANDARD_INPUT',
                         'expected_on_the_host':'DIRECTORY_ABSENT','directory_entries':None,'parent':chain(hostemu.DATA,hostemu.DATA)},
              'verify':{'snippet_sha256':f.sha(m.VERIFY_SNIPPET.encode()),'image_id':hostemu.BACKEND,'binds':[{'source':k11.PROBE,'target':k11.PROBE_TARGET,'read_only':True}],
                        'network':'none','command':['python','-I','-B','-'],'alarm_seconds':30},
              'policy':{'sha256':f.sha(k11.POLICY),'bytes':len(k11.POLICY),'valid_at':k11.VALID_AT},
              'render':{'project':'c3po','env_file':hostemu.ENV_FILE,'files':[hostemu.COMPOSE_FILE],'override_sha256':f.sha(k11.override_bytes()),'service':'r2d2-worker','environment':override},
              'deploy':{'tree':chain(hostemu.DEPLOY,hostemu.DEPLOY),'lock_directory':chain(hostemu.LOCK_DIRECTORY,hostemu.DEPLOY),'lock':k11.LOCK,'version_file':hostemu.DEPLOY+'/.deploy-version'},
              'maintenance_pin':hostemu.PIN,'bind_probe':{'directory':chain(k11.PROBE,hostemu.DATA),'file':k11.PROBE+'/'+k11.RELEASE_FILE},
              'dry_run':'FULL','rehearses_install_release_and_activate':True,'limits':{'render_ms':3000,'quick_ms':1500,'data_volume_free_bytes':1048576,'data_volume_free_inodes':8},
              'live':{'path':'/mnt/day-d-data/r2d2-v2-live/2026-10-05','expected_on_the_host':'DIRECTORY_ABSENT','parent':chain(k11.LIVE_PARENT,hostemu.DATA)},
              'units':[{'name':name,'expected':None} for name in k11.UNITS],'journal':{'path':k11.JOURNAL,'floor_bytes':7},
              'docker_config':None,'rows_in_receipt':True,'evidence_boot_id_sha256':f.BOOT_SHA,'writes':0,'containers_run':1,'activation':False}
    assert effects==expected
    m,docs,host=fresh('PRE',docker_config=k11.DOCKER_CONFIG);assert (docs.go['effects']['docker_config'],docs.go['effects']['dry_run'])==(k11.DOCKER_CONFIG,'REDUCED')
    m,docs,host=fresh('POST');effects=docs.go['effects']
    assert (effects['mode'],effects['gates_first_session_readback'],effects['render'],effects['journal'],effects['docker_config'],effects['rows_in_receipt'])==('POST',True,None,None,None,False)
    assert (effects['dry_run'],effects['rehearses_install_release_and_activate'],effects['limits'],effects['bind_probe'],effects['live']['path'])==(None,False,None,None,k11.LIVE_HOST)
    assert effects['release']['source']=='THE_INSTALLED_FILE_THROUGH_A_READ_ONLY_BIND' and effects['release']['expected_on_the_host']=='INSTALLED' and effects['release']['directory_entries']==1
    assert effects['verify']['binds']==[{'source':k11.RELEASE_HOST,'target':k11.TARGET,'read_only':True}] and effects['units']==[]

def test_success_criterion_follows_the_signed_mode_and_a_go_for_the_other_mode_is_refused(tmp_path):
    full='EPOCH_DRY_RUN_PRE_ALL_OBSERVED_ALL_EXPECTATIONS_MET';reduced='EPOCH_DRY_RUN_PRE_REDUCED_PROFILE_ALL_OBSERVED_ALL_EXPECTATIONS_MET';post='EPOCH_READBACK_POST_ALL_OBSERVED_ALL_EXPECTATIONS_MET'
    for index,(mode,options,outcome,others) in enumerate((('PRE',{},full,(post,reduced)),('PRE',{'dry_run':'REDUCED'},reduced,(post,full)),('PRE',{'probe':None},reduced,(full,)),
                                                          ('POST',{},post,(full,reduced)))):
        for other in others:
            m,docs,host=fresh(mode,**options);assert docs.go['success_criterion']==outcome==m.success_of(docs.plan)
            docs.go['success_criterion']=other;docs.chain(criterion=False);assert f.refusal(docs.authenticate)=='GO_CRITERION'
            directory=tmp_path/('%d-%s'%(index,other[:22]));directory.mkdir();dispatch=f.Dispatch(docs,directory);docs.go['success_criterion']=other;docs.chain(criterion=False);dispatch.save(rebind=False)
            assert f.refusal(dispatch.prepare)=='GO_CRITERION' and not dispatch.claims(),'the dispatcher refuses it locally, before any claim'
    k=f.load(k11.DIRECTORY);assert json.loads((k.dir/'GO.UNBOUND.json').read_bytes())['success_criterion'] is None,'the template carries no outcome: it follows the mode'
    assert len({k.m.PRE_OUTCOME,k.m.PRE_REDUCED_OUTCOME,k.m.COMPLETE_OUTCOME,k.m.MISMATCH_OUTCOME,k.m.PARTIAL_OUTCOME,k.m.REFUSED_OUTCOME})==6
    # a reduced dry run completes on the host under its own name, and the receipt and the effects say what it is
    m,docs,host=fresh('PRE',dry_run='REDUCED');receipt=docs.run(host)
    assert (receipt['status'],receipt['outcome'],receipt['dry_run'])==('METADATA_ONLY_REQUIRES_REVIEW',reduced,'REDUCED') and receipt['gates_first_session_readback'] is False

def test_the_one_container_row_of_this_source_takes_no_bind_it_could_write_through():
    k=f.load(k11.DIRECTORY);m=k.m;mount={'source':k11.RELEASE_HOST,'target':k11.TARGET,'read_only':False}
    assert f.refusal(lambda:m.run_arguments('verify',hostemu.BACKEND,[mount],m.VERIFY_COMMAND))=='MOUNT_NOT_READ_ONLY'
    assert m.run_arguments('verify',hostemu.BACKEND,[dict(mount,read_only=True)],m.VERIFY_COMMAND)[:2]==['--mount','type=bind,source=%s,target=%s,readonly'%(k11.RELEASE_HOST,k11.TARGET)]
    m2,docs,host=fresh('POST');assert all(item['read_only'] is True for item in m.mounts_of(docs.plan)) and m.COMMANDS['verify']['kind']=='CONTAINER'

def test_a_malformed_plan_cannot_spend_the_go(tmp_path):
    """The dispatcher runs the source's own validation locally: a refusal from the bytes leaves no claim."""
    for index,(mode,path,value,code) in enumerate((('PRE',['render'],None,'RENDER_REQUIRED'),('POST',['policy'],None,'POLICY_REQUIRED'),
                                                   ('PRE',['bind_probe'],None,'DRY_RUN_NOT_THE_FULL_PROFILE'),('PRE',['policy'],None,'DRY_RUN_NOT_THE_FULL_PROFILE'),
                                                   ('PRE',['live'],None,'DRY_RUN_NOT_THE_FULL_PROFILE'),('POST',['docker_config'],k11.DOCKER_CONFIG,'DOCKER_CONFIG_ONLY_IN_A_REDUCED_DRY_RUN'),
                                                   ('POST',['release','directory_entries'],0,'RELEASE_PLAN_INVALID'),('PRE',['release','sha256'],'3'*64,'RELEASE_NOT_THE_SIGNED_BYTES'))):
        m,docs,host=fresh(mode);put(docs.plan,path,value);docs.chain();directory=tmp_path/str(index);directory.mkdir();dispatch=f.Dispatch(docs,directory)
        assert f.refusal(dispatch.prepare)==code and not dispatch.claims()

def test_static_scope_names_the_snippet_the_modes_and_the_limits():
    k=f.load(k11.DIRECTORY);m=k.m;scope=m.SCOPE
    assert scope['verify']['snippet_sha256']==f.sha(m.VERIFY_SNIPPET.encode('ascii'))==m.VERIFY_SNIPPET_SHA256 and scope['verify']['alarm_seconds']==30
    assert 'signal.alarm(%d)\n'%m.VERIFY_ALARM_SECONDS in m.VERIFY_SNIPPET and m.VERIFY_SNIPPET.startswith('import signal\nsignal.alarm(')
    assert m.VERIFY_ALARM_SECONDS+2*m.AFTER_EFFECT_RESERVE_SECONDS<=m.COMMAND_CLASSES[m.COMMANDS['verify']['class']]['seconds'],'the alarm ends the container before the CLI limit'
    assert set(scope['modes'])=={'PRE','POST'} and scope['modes']['POST']==m.COMPLETE_OUTCOME and scope['modes']['PRE'].startswith(m.PRE_OUTCOME)
    assert [row['kind'] for row in m.COMMANDS.values()].count('CONTAINER')==1 and not [row for row in m.COMMANDS.values() if row['kind']=='EFFECT']
    assert m.COMMANDS['verify']['argv']==['run','--rm','-i','--pull','never','--init','--user','0:0','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges']
    assert m.COMMANDS['unit']['argv']==['show'] and m.COMMANDS['unit']['tail']==['-p','Id','-p','LoadState','-p','ActiveState','-p','SubState','-p','UnitFileState','-p','FragmentPath',
                                                                              '-p','DropInPaths','-p','WantedBy','-p','RequiredBy','-p','TriggeredBy']
    assert (m.COMMANDS['render_base']['stdin'],m.COMMANDS['render_override']['stdin'])==(False,True) and m.COMMANDS['render_base']['tail']==['config','--format','json']
    assert m.EPOCH_NAME=='R2D2-V2-SHADOW-2026-10-05' and m.FIRST_SESSION_DAY=='2026-10-05' and m.DATE_CLASS=='READ' and m.MAX_GATE_SPAN_SECONDS==3600
    assert set(scope['dry_run'])=={'FULL','REDUCED'} and scope['dry_run']['FULL'].startswith(m.PRE_OUTCOME+':') and scope['dry_run']['REDUCED'].startswith(m.PRE_REDUCED_OUTCOME+':')
    assert scope['monday']['data_volume']=='/mnt/day-d-data' and scope['monday']['release_directory']=='r2d2-v2-release-20261005' and scope['monday']['lock']=='runtime/security/deployment.lock'
    assert scope['fact_items']==m.FACT_ITEMS and set(scope['preconditions_of_the_writes_found_here'])=={'install_release','activate'}
    assert m.WRITES_ALLOWED is False and m.ACTIVATION_ALLOWED is False and not hasattr(m,'create_file') and not hasattr(m,'NativeFiles')


# ---------------------------------------------------------------- the review of 02/10
def test_policy_bytes_must_be_the_canonical_form_the_assembler_hashes():
    """The controller compares the hash of the file, the assembler the hash of the canonical form of its content: a
    policy file with a trailing newline or with spaces is accepted by the one and refused by the other (POLICY_HASH).
    Decidable from the bytes: refused here, before any claim, and never learnt in the container on Monday."""
    body=json.loads(k11.POLICY)
    unsorted=json.dumps(dict(reversed(list(body.items()))),separators=(',',':')).encode()
    for raw in (k11.POLICY+b'\n',json.dumps(body).encode(),json.dumps(body,indent=2,sort_keys=True).encode(),unsorted,b' '+k11.POLICY):
        for mode in ('PRE','POST'):
            m,docs,host=fresh(mode,render=True,policy=raw);assert raw!=k11.POLICY;refused(docs,'POLICY_NOT_CANONICAL')
    accented=k11.policy_bytes(authorization_ref='ap\u00f3s')          # the assembler's form keeps non-ASCII characters as UTF-8, it does not escape them
    exact=json.dumps(json.loads(accented),sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8');assert exact!=accented and 'ap\u00f3s'.encode('utf-8') in exact
    m,docs,host=fresh('POST',policy=exact);docs.authenticate()
    m,docs,host=fresh('POST',policy=accented);refused(docs,'POLICY_NOT_CANONICAL')
    m,docs,host=fresh('POST',policy=k11.policy_bytes(capacity=1.0));docs.authenticate()        # a number keeps the spelling json gives it

def test_full_dry_run_renders_the_override_bytes_activate_writes_and_names_the_policy_in_its_directory():
    m,docs,host=fresh('PRE');environment=json.loads(k11.override_bytes())['services']['r2d2-worker']['environment']
    assert base64_of(docs.plan['render'])==json.dumps({'services':{'r2d2-worker':{'environment':environment}}},sort_keys=True).encode('ascii')==m.activate_override(environment)
    for raw in (f.canonical(json.loads(k11.override_bytes())),k11.override_bytes()+b'\n',json.dumps(json.loads(k11.override_bytes()),indent=1,sort_keys=True).encode()):
        m,docs,host=fresh('PRE');repack(docs.plan['render'],raw,'override_');refused(docs,'OVERRIDE_NOT_AS_ACTIVATE_WRITES_IT')
        m,docs,host=fresh('PRE',dry_run='REDUCED');repack(docs.plan['render'],raw,'override_');docs.chain();docs.authenticate()
        m,docs,host=fresh('POST',render=True);repack(docs.plan['render'],raw,'override_');docs.chain();docs.authenticate()
    # the policy file of the override lies directly in the directory activate will create
    for path in (k11.DATA_TARGET+'/r2d2-v2-live/policy.json',k11.DATA_TARGET+'/r2d2-v2-live/2026-10-06/policy.json',k11.DATA_TARGET+'/r2d2-v2-live/2026-10-05/deeper/policy.json',
                 k11.DATA_TARGET+'/policy.json',k11.DATA_TARGET+'/r2d2-v2-live/2026-10-05'):
        for mode in ('PRE','POST'):
            m,docs,host=fresh(mode,render=True);repack(docs.plan['render'],k11.override_bytes(**{k11.KEYS[0]:path}),'override_');refused(docs,'OVERRIDE_POLICY_NOT_IN_THE_LIVE_DIRECTORY')
    m,docs,host=fresh('POST',render=True,live=False);repack(docs.plan['render'],k11.override_bytes(**{k11.KEYS[0]:k11.DATA_TARGET+'/elsewhere/policy.json'}),'override_');docs.chain();docs.authenticate()
    m,docs,host=fresh('PRE');repack(docs.plan['render'],k11.override_bytes(**{k11.KEYS[0]:k11.DATA_TARGET+'/r2d2-v2-live/2026-10-05/live-policy.json'}),'override_');docs.chain();docs.authenticate()
def base64_of(render):
    import base64
    return base64.b64decode(render['override_b64'])

def test_live_directory_lies_in_the_data_volume_and_apart_from_the_release():
    m,docs,host=fresh('PRE');docs.plan['live']={'parent':k11.chain(host,hostemu.DATA,hostemu.DATA),'directory_name':k11.RELEASE_DIRECTORY};refused(docs,'LIVE_AND_RELEASE_OVERLAP')
    m,docs,host=fresh('POST');host.tree.add(k11.RELEASE_HOST+'/live',mode=0o700,dev=hostemu.DATA_DEVICE)
    docs.plan['live']={'parent':k11.chain(host,k11.RELEASE_HOST,hostemu.DATA),'directory_name':'x'};refused(docs,'LIVE_AND_RELEASE_OVERLAP')
    m,docs,host=fresh('PRE',dry_run='REDUCED');host.tree.add(hostemu.DATA+'/releases',mode=0o700,dev=hostemu.DATA_DEVICE)
    host.tree.add(hostemu.DATA+'/releases/r2d2-v2-release-20261005',mode=0o700,dev=hostemu.DATA_DEVICE)
    docs.plan['release']['parent']=k11.chain(host,hostemu.DATA+'/releases/r2d2-v2-release-20261005',hostemu.DATA);docs.plan['release']['directory_name']='inner'
    docs.plan['live']={'parent':k11.chain(host,hostemu.DATA+'/releases',hostemu.DATA),'directory_name':'r2d2-v2-release-20261005'};refused(docs,'LIVE_AND_RELEASE_OVERLAP')
    m,docs,host=fresh('PRE');docs.plan['worker']['data_source']='/mnt/day-d';refused(docs,'RELEASE_OUTSIDE_THE_DATA_VOLUME')
    m,docs,host=fresh('POST');assert docs.go['effects']['live']=={'path':k11.LIVE_HOST,'expected_on_the_host':'DIRECTORY_ABSENT','parent':dict(m.chain_effects(hostemu.rows(host,k11.LIVE_PARENT)),open_root=hostemu.DATA,rows_signed=True)}

def test_signed_rows_of_a_directory_that_receives_an_entry_are_judged_as_the_write_judges_them():
    """install_release and activate validate their parent rows with receives_entry (no setgid directory): rows they
    would refuse at their binding are refused here at this binding, for the release parent and the live parent."""
    for mode in ('PRE','POST'):
        m,docs,host=fresh(mode);docs.plan['release']['parent']['rows'][-1]['mode']=0o2755;refused(docs,'PARENT_SETGID')
        m,docs,host=fresh(mode);docs.plan['live']['parent']['rows'][-1]['mode']=0o2700;refused(docs,'PARENT_SETGID')
        m,docs,host=fresh(mode);docs.plan['deploy']['tree']['rows'][-1]['mode']=0o2755;docs.plan['deploy']['lock_directory']['rows'][-2]['mode']=0o2755
        docs.plan['deploy']['lock_directory']['rows'][-4]['mode']=0o2755;docs.chain();docs.authenticate()          # nothing is created in the deploy tree by this family

def test_places_of_install_release_are_what_the_full_dry_run_signs():
    """install_release takes its directory from constants of its own source: a full dry run that names another volume,
    parent, directory or file would look at a place Monday's write never uses."""
    def moved(change):
        m,docs,host=fresh('PRE');change(docs,host);docs.chain();return docs
    def other_file(docs,host):
        docs.plan['release']['file_name']='release.json';repack(docs.plan['render'],k11.override_bytes(**{k11.KEYS[2]:k11.DATA_TARGET+'/'+k11.RELEASE_DIRECTORY+'/release.json'}),'override_')
    def other_directory(docs,host):
        docs.plan['release']['directory_name']='r2d2-v2-release-20261006';repack(docs.plan['render'],k11.override_bytes(**{k11.KEYS[2]:k11.DATA_TARGET+'/r2d2-v2-release-20261006/'+k11.RELEASE_FILE}),'override_')
    def other_target(docs,host):
        docs.plan['worker']['data_target']='/app/data';environment={k11.KEYS[0]:'/app/data/r2d2-v2-live/2026-10-05/policy.json',k11.KEYS[2]:'/app/data/'+k11.RELEASE_DIRECTORY+'/'+k11.RELEASE_FILE}
        repack(docs.plan['render'],k11.override_bytes(**environment),'override_')
    def other_source(docs,host):
        docs.plan['worker']['data_source']='/mnt';environment={k11.KEYS[0]:k11.DATA_TARGET+'/day-d-data/r2d2-v2-live/2026-10-05/policy.json',
                                                               k11.KEYS[2]:k11.DATA_TARGET+'/day-d-data/'+k11.RELEASE_DIRECTORY+'/'+k11.RELEASE_FILE}
        repack(docs.plan['render'],k11.override_bytes(**environment),'override_')
    for change in (other_file,other_directory,other_target,other_source):
        docs=moved(change);refused(docs,'DRY_RUN_NOT_THE_PLACES_OF_INSTALL_RELEASE');docs.plan['dry_run']='REDUCED';docs.chain();docs.authenticate()
    # the signed rows of the release parent show the data volume as a mount point, as install_release requires of its own
    m,docs,host=fresh('PRE')
    for row in docs.plan['release']['parent']['rows']:row['device']=hostemu.ROOT_DEVICE
    refused(docs,'DATA_VOLUME_NOT_A_MOUNT_POINT');docs.plan['dry_run']='REDUCED';docs.chain();docs.authenticate()
    # a live parent whose path leaves no room for the name is refused from the bytes
    m,docs,host=fresh('POST');long=hostemu.DATA+'/'+'p'*100;host.tree.add(long,mode=0o700,dev=hostemu.DATA_DEVICE)
    docs.plan['live']={'parent':k11.chain(host,long,hostemu.DATA),'directory_name':'d'*128};refused(docs,'LIVE_OUTSIDE_THE_DATA_VOLUME')
