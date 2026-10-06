"""Synthetic fixture world only; no Docker binary, network, operational host or authoritative owner."""
from datetime import datetime
from pathlib import Path
import hashlib,json,sys
DIRECTORY=Path(__file__).resolve().parent.parent
CORE=DIRECTORY.parent/'core_bootstrap_identity'
sys.path.insert(0,str(CORE/'tests'))
import family as f
import hostemu

def sha(raw):return hashlib.sha256(raw).hexdigest()
CANARY='synthetic-secret-must-never-leave-bootstrap'
RUNNER=b'"""synthetic never-executed runner fixture"""\n'
POLICY=f.canonical({'schema':'R2D2_V2_LIVE_POLICY_V1','epoch':'R2D2-V2-SHADOW-2026-10-05','mode':'LIVE','valid_from':'2026-10-02T00:00:00+00:00','valid_until':'2026-10-10T00:00:00+00:00'})
RELEASE=f.canonical({'schema':'R2D2_V2_RELEASE_V3','epoch':'R2D2-V2-SHADOW-2026-10-05','mode':'CERTIFIED','synthetic':True})
POLICY_DIRECTORY=hostemu.DATA+'/r2d2-v2-live/2026-10-05'
RELEASE_DIRECTORY=hostemu.DATA+'/r2d2-v2-release-20261005'
NOW=datetime.fromisoformat('2026-10-06T12:26:00+00:00')

def world(k):
    host=f.world(k);m=k.m;tree=host.tree
    tree.add('/var/lib/c3po',mode=0o755)
    for path in (m.K9_ROOT,m.K9_SOURCE_ROOT)+tuple(m.K9_PLACEMENT[key] for key in m.K9_PARENT_CHAINS):tree.add(path,mode=0o700)
    tree.add(m.K9_PLACEMENT['tools']+'/k9_runner-'+sha(RUNNER)+'.py',kind='file',mode=0o600,content=RUNNER)
    for path in (m.SOURCE_PATHS[0],m.SOURCE_PATHS[2],m.SOURCE_PATHS[3],hostemu.DATA+'/r2d2-v2-live',POLICY_DIRECTORY,RELEASE_DIRECTORY):tree.add(path,mode=0o700,dev=hostemu.DATA_DEVICE)
    for path in (m.SOURCE_PATHS[1],m.SOURCE_PATHS[4]):tree.add(path,kind='file',mode=0o600,dev=hostemu.DATA_DEVICE,content=CANARY.encode())
    tree.add(POLICY_DIRECTORY+'/policy.json',kind='file',mode=0o600,dev=hostemu.DATA_DEVICE,content=POLICY)
    tree.add(RELEASE_DIRECTORY+'/release.CERTIFIED.json',kind='file',mode=0o600,dev=hostemu.DATA_DEVICE,content=RELEASE)
    worker=host.docker.container(hostemu.WORKER)
    worker['Config']['Env']+=['UNRELATED_SECRET='+CANARY,'C3PO_R2D2_V2_LIVE_POLICY_FILE=/app/day-d-data/r2d2-v2-live/2026-10-05/policy.json','C3PO_R2D2_V2_LIVE_POLICY_SHA='+sha(POLICY),'C3PO_R2D2_V2_SHADOW_RELEASE_FILE=/app/day-d-data/r2d2-v2-release-20261005/release.CERTIFIED.json','C3PO_R2D2_V2_SHADOW_RELEASE_SHA='+sha(RELEASE)]
    return host

def fields(k,host):
    m=k.m
    sources=[]
    for path in m.SOURCE_PATHS:
        info=host.tree.get(path).stat()
        sources.append({'path':path,'device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid,'gid':info.st_gid,'mode':info.st_mode&0o7777,'mtime_ns':info.st_mtime_ns,'ctime_ns':info.st_ctime_ns})
    return {'mode':m.BOOTSTRAP_MODE,'epoch':m.BOOTSTRAP_EPOCH,'slot':m.BOOTSTRAP_SLOT,'attempt_key':m.bootstrap_key(),
      'constants':{'package_sha256':m.K9_PACKAGE_SHA256,'code_revision':m.K9_CODE_REVISION,'release_sha256':sha(RELEASE),'policy_sha256':sha(POLICY),'image_id':hostemu.BACKEND,'runner_sha256':sha(RUNNER),'disk_floor_bytes':m.K9_DISK_FLOOR_BYTES,'placement':dict(m.K9_PLACEMENT)},
      'parent_rows':{name:{'path':m.K9_PLACEMENT[name],'rows':hostemu.rows(host,m.K9_PLACEMENT[name]),'open_root':None} for name in m.K9_PARENT_CHAINS},
      'data_volume_chain':hostemu.rows(host,m.K9_DATA_VOLUME),'source_rows':sources,'evidence_boot_id_sha256':f.BOOT_SHA,
      'policy_read':{'policy':{'directory':{'path':POLICY_DIRECTORY,'rows':hostemu.rows(host,POLICY_DIRECTORY),'open_root':hostemu.DATA},'file_name':'policy.json'},'release':{'directory':{'path':RELEASE_DIRECTORY,'rows':hostemu.rows(host,RELEASE_DIRECTORY),'open_root':hostemu.DATA},'file_name':'release.CERTIFIED.json'},'worker':{'container':hostemu.WORKER,'data_source':hostemu.DATA,'data_target':'/app/day-d-data'}}}

def case():
    k=f.load(DIRECTORY);host=world(k);docs=f.Docs(k,fields(k,host),now=NOW)
    return docs,host

def mutations(host):return [call for call in host.log if call[0] in ('create','write','fsync','unlink','mkdir','rename','link','chmod','chown')]
