"""K9R with the real system calls of its own, unmodified Native, on a private temporary tree that stands in for '/'.
No host, no docker: the tree has no docker binary, so every command is refused before a process exists
(BINARY_UNAVAILABLE_OR_UNSAFE) and what is exercised is everything the source does on the filesystem: the walks by
dir_fd without following a link, the lstat of the secret files (never opened), the hash of the runner, the reads of the
launch record, the markers, the receipt and the outputs, statvfs. On the workstation a marker bit stands for O_NOATIME
and the test user is reported as root; the kernel's O_NOATIME and real uid 0 only on the Linux job (not run)."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

import family as f
import k9r
import native_child_k9r
import oslevel

ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
BOOT=b'0f8fad5b-d9cb-469f-a165-70867728950e\n'
WRITE=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND

def write(path,content,mode=0o600):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content);os.chmod(path,mode)

@pytest.fixture
def tree(tmp_path):
    root=Path(str(tmp_path)).resolve()/'root';root.mkdir(mode=0o755)
    for path in ('proc/sys/kernel/random','mnt/day-d-data','usr/bin'):(root/path).mkdir(parents=True,mode=0o755)
    for name in ('k9_root','days','tools','claims','secrets','emitter','source_root'):
        path=root/k9r.PLACEMENT[name].lstrip('/');path.mkdir(parents=True,exist_ok=True)
    for path in list(root.rglob('*'))+[root]:os.chmod(path,0o755)
    for name in ('k9_root','days','tools','claims','secrets','emitter','source_root'):os.chmod(root/k9r.PLACEMENT[name].lstrip('/'),0o700)
    (root/'proc/sys/kernel/random/boot_id').write_bytes(BOOT)
    write(root/k9r.PLACEMENT['provider_env_file'].lstrip('/'),('C3PO_EODHD_API_TOKEN=%s\n'%k9r.CANARY).encode())
    write(root/k9r.PLACEMENT['risk_db_env_file'].lstrip('/'),('C3PO_R2D2_RISK_DATABASE_URL=postgresql://reader:%s@db/c3po\n'%k9r.CANARY).encode())
    write(root/k9r.PLACEMENT['emitter_password'].lstrip('/'),(k9r.CANARY+'\n').encode())
    write(root/(k9r.PLACEMENT['tools']+'/k9_runner-'+f.sha(k9r.RUNNER)+'.py').lstrip('/'),k9r.RUNNER)
    write(root/k9r.SEPTEMBER[1].lstrip('/'),(k9r.CANARY+'\n').encode());write(root/k9r.SEPTEMBER[4].lstrip('/'),(k9r.CANARY+'\n').encode())
    for path in (k9r.SEPTEMBER[0],k9r.SEPTEMBER[2],k9r.SEPTEMBER[3]):os.chmod(root/path.lstrip('/'),0o700)
    return root

def snapshot(root):
    out={}
    for path in sorted([root]+list(root.rglob('*'))):
        info=os.lstat(path);out[str(path.relative_to(root))]=(stat.S_IFMT(info.st_mode),stat.S_IMODE(info.st_mode),info.st_nlink,info.st_ino,info.st_mtime_ns,
                                                              info.st_size if stat.S_ISREG(info.st_mode) else None)
    return out

def child(root,plan,now,tmp_path):
    path=Path(str(tmp_path))/'fields.json';path.write_bytes(json.dumps(plan).encode())
    done=subprocess.run([sys.executable,'-B',str(Path(native_child_k9r.__file__)),str(root),str(path),now],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        env=dict(ENV,HOME=os.environ.get('HOME','')),timeout=120)
    assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    result=json.loads(done.stdout);assert k9r.CANARY not in done.stdout.decode().replace('"'+k9r.CANARY,'')
    return result['receipt'],result['events'],result['calls']

def common(receipt,events,calls):
    line=json.dumps(receipt);assert k9r.CANARY not in line
    opens=[entry for entry in calls if entry['call']=='open'];assert opens and all(not entry['flags']&WRITE and entry['flags']&os.O_NOFOLLOW for entry in opens)
    assert all(entry['by_dir_fd'] or entry['path']=='/' for entry in opens) and not [entry for entry in calls if entry['call']=='stat' and entry['follow_symlinks']]
    assert not [entry for entry in calls if entry['call'] in ('mkdir','fsync','link','unlink','umask','readlink','flock')]
    assert not [event for event in events if event[0]!='open'],'no file-changing and no process-starting event: %r'%events[:3]
    assert not [entry for entry in opens if '/secrets/' in entry['path'] and not entry['flags']&os.O_DIRECTORY],'a secret file is never opened'
    assert receipt['mutating_calls']['issued']==0 and receipt['commands_started']=={'READ':0,'CONTAINER':0,'EFFECT':0}

def test_native_tree_reads_rows_and_metadata_and_leaves_no_trace(tree,tmp_path):
    before=snapshot(tree);plan=k9r.tree_fields(k9r.constants())
    receipt,events,calls=child(tree,plan,k9r.TREE_MOMENT,tmp_path);common(receipt,events,calls)
    assert snapshot(tree)==before
    # one filesystem: the "data volume" is no mount point and the K9 tree shares its device; the tree read says both
    real=os.statvfs(str(tree));short=real.f_bavail*real.f_frsize<214748364800      # the workstation's own disk, judged as the host's would be
    assert receipt['items']['k9_filesystem']['hold'] is short and abs(receipt['items']['k9_filesystem']['days_bytes_available']-real.f_bavail*real.f_frsize)<1<<30
    assert receipt['findings']==sorted(['DATA_VOLUME_NOT_A_MOUNT_POINT']+(['DISK_FREE_BELOW_FLOOR'] if short else [])) and receipt['boot_id_sha256']==f.sha(BOOT.strip())
    assert [row['path'] for row in receipt['items']['directory:K9_ROOT']['observed_rows']]==['/','/var','/var/lib','/var/lib/c3po',k9r.K9_ROOT]
    for name in ('DAYS','SOURCE_ROOT','SECRETS','TOOLS','CLAIMS'):
        item=receipt['items']['directory:'+name];assert item['status']=='COMPLETE' and item['root_private'] is True and item['rows_acceptable_to_the_k9_requests'] is True
        assert [row['path'] for row in item['observed_rows']][-1]==k9r.PLACEMENT[{'DAYS':'days','SOURCE_ROOT':'source_root','SECRETS':'secrets','TOOLS':'tools','CLAIMS':'claims'}[name]]
    september=receipt['items']['september_sources'];assert september['findings']==['DATA_VOLUME_NOT_A_MOUNT_POINT'] and len(september['components'])==5
    assert not [entry for entry in calls if entry['call']=='open' and entry['path'].endswith(('/risk-database-url','/password'))],'never opened'
    assert receipt['items']['runner_file']['bytes_equal_signed'] is True and receipt['items']['secret:EMITTER/password']['private'] is True
    reads=[entry for entry in calls if entry['call']=='open' and entry['path'].endswith('.py')];assert len(reads)==1 and reads[0]['flags']&os.O_NONBLOCK and reads[0]['noatime']

def result_tree(root):
    """What a launch of collect_launch and its runner leave, written with real files (the host side of the emulated world)."""
    host_path=lambda path:root/path.lstrip('/')
    record=dict(schema='K9_LAUNCH_RECORD_V1',epoch=k9r.EPOCH,day=k9r.DAY,operation='collect_launch',slot='PRIMARY',
                attempt_key=k9r.attempt_key(k9r.EPOCH,k9r.DAY,'causal_list','collect_launch'),request_sha256=k9r.REQUEST_OF_THE_LAUNCH,
                step_plan_sha256=k9r.STEP_PLAN,container_id='ab'*32,container_name='c3po-k9-20261006-collect_launch',
                created_at='2026-10-05T21:29:10+00:00',started_at='2026-10-05T21:29:11+00:00',timeout_seconds=1235)
    for directory in ('','launches','receipts','inputs'):
        path=host_path(k9r.day_path(directory) if directory else k9r.day_path());path.mkdir(exist_ok=True);os.chmod(path,0o700)
    write(host_path(k9r.day_path('launches','collect_launch.json')),f.canonical(record))
    identity={'epoch':k9r.EPOCH,'day':k9r.DAY,'phase':'causal_list','operation':'collect_launch','attempt_key':record['attempt_key'],'step_plan_sha256':k9r.STEP_PLAN}
    write(host_path(k9r.day_path('receipts','collect_launch.STARTED.json')),f.canonical(dict(identity,schema='K9_STEP_STARTED_V1',started_at='2026-10-05T21:29:12+00:00')))
    outputs={}
    for key,content in k9r.OUTPUTS['collect_launch'].items():
        write(host_path(k9r.day_path()+'/'+key.split('/',1)[1]),content);outputs[key]=f.sha(content)
    write(host_path(k9r.day_path('receipts','collect_launch.RECEIPT.json')),f.canonical(dict(identity,schema='K9_STEP_RECEIPT_V1',status='COMPLETE',code=None,
          started_at='2026-10-05T21:29:12+00:00',completed_at='2026-10-05T21:40:00+00:00',package_sha256=k9r.PACKAGE,build_sha=k9r.REVISION,
          outputs=outputs,aggregates={},counts={'registry_symbols':1})))

def test_native_result_reads_the_step_files_and_hashes_the_outputs_again(tree,tmp_path):
    result_tree(tree);before=snapshot(tree)
    plan={'mode':'RESULT','epoch':k9r.EPOCH,'day':k9r.DAY,'k9_phase':'causal_list','k9_operation':'collect_result','slot':'PRIMARY',
          'attempt_key':k9r.attempt_key(k9r.EPOCH,k9r.DAY,'causal_list','collect_result'),'run_not_after':'2026-10-05T21:49:59+00:00',
          'constants':k9r.constants(),'parent_rows':{name:{'path':k9r.PLACEMENT[name],'rows':oslevel.rows(tree,k9r.PLACEMENT[name]),'open_root':k9r.open_root(name)} for name in k9r.CHAINS},
          'evidence_boot_id_sha256':f.sha(BOOT.strip()),'policy_read':None}
    receipt,events,calls=child(tree,plan,'2026-10-05T21:50:00+00:00',tmp_path);common(receipt,events,calls)
    assert snapshot(tree)==before
    items=receipt['items']
    # without docker the container cannot be inspected, so no step file can be tied to the launch in time (rev 4): the
    # marker and the receipt are read with real system calls and judged not of this step; the outputs are not hashed
    assert items['launch_record']['valid'] is True and items['launched_container']['code']=='BINARY_UNAVAILABLE_OR_UNSAFE'
    assert items['step_receipts']['receipt'] is True and items['step_receipts']['receipt_valid'] is False and items['step_receipts']['started_valid'] is False
    assert items['outputs']['applicable'] is False and receipt['phase_result']=='UNCERTAIN' and receipt['phase_reason']=='OBSERVATION_INCOMPLETE'
    reads=[entry for entry in calls if entry['call']=='open' and entry['path'].endswith(('.STARTED.json','.RECEIPT.json','collect_launch.json'))]
    assert len(reads)==3 and all(entry['by_dir_fd'] and entry['flags']&os.O_NOFOLLOW for entry in reads)
