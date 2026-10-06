"""K11 with the real system calls of its own, unmodified Native, on a private temporary tree that stands in for '/'.
No host, no docker, no systemd: the tree has no docker and no systemctl binary, so every command is refused before a
process exists (BINARY_UNAVAILABLE_OR_UNSAFE) and what is exercised is everything the source does on the filesystem:
the walks by dir_fd without following a link, the read of the installed release, the lstat probes, statvfs, and the
shared flock on the deployment lock. On the workstation a marker bit stands for O_NOATIME and the test user is
reported as root; the kernel's O_NOATIME and real uid 0 only on the Linux job."""
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

import family as f
import k11
import native_child_k11
import oslevel

ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
BOOT=b'0f8fad5b-d9cb-469f-a165-70867728950e\n'
DATA='/mnt/day-d-data';DEPLOY='/opt/chief-of-staff-digital';LOCKS=DEPLOY+'/runtime/security'
WRITE=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND

@pytest.fixture
def tree(tmp_path):
    root=Path(str(tmp_path)).resolve()/'root';root.mkdir(mode=0o755)
    for path in ('mnt/day-d-data/r2d2-v2-live','proc/sys/kernel/random','opt/chief-of-staff-digital/runtime/security','opt/chief-of-staff-digital/c3po','usr/bin','run','var/lib/c3po-bar/journal'):
        (root/path).mkdir(parents=True,mode=0o755)
    for path in list(root.rglob('*'))+[root]:os.chmod(path,0o755)
    (root/'proc/sys/kernel/random/boot_id').write_bytes(BOOT);(root/'opt/chief-of-staff-digital/.deploy-version').write_bytes((k11.REVISION+'\n').encode())
    for name,mode in (('.env',0o600),('c3po/compose.yml',0o644),('runtime/security/deployment.lock',0o644)):
        (root/'opt/chief-of-staff-digital'/name).write_bytes(b'');os.chmod(root/'opt/chief-of-staff-digital'/name,mode)
    (root/'mnt/day-d-data/.r2d2-v2-pinned').write_bytes(b'');os.chmod(root/'mnt/day-d-data/.r2d2-v2-pinned',0o600)
    os.chmod(root/'var/lib/c3po-bar/journal',0o700);os.chmod(root/'mnt/day-d-data/r2d2-v2-live',0o700)
    return root
def install(root,release=k11.RELEASE):
    directory=root/'mnt/day-d-data'/k11.RELEASE_DIRECTORY;directory.mkdir(mode=0o700);os.chmod(directory,0o700)
    (directory/k11.RELEASE_FILE).write_bytes(release);os.chmod(directory/k11.RELEASE_FILE,0o600);return directory
def fields(root,mode,signed=True,**changes):
    def chain(path):return {'path':path,'rows':oslevel.rows(root,path) if signed else None,'open_root':None}
    pre=mode=='PRE';override=k11.override_bytes()
    plan={'mode':mode,'evidence_boot_id_sha256':f.sha(BOOT.strip()),'revision':k11.REVISION,'package_sha256':k11.PACKAGE,
          'image':{'reference':'c3po/backend:production','image_id':'sha256:'+'fb'*32},
          'worker':{'container':'c3po-r2d2-worker-1','environment':True,'data_source':DATA,'data_target':k11.DATA_TARGET},
          'release':{'sha256':f.sha(k11.RELEASE),'bytes':len(k11.RELEASE),'content_b64':k11.b64(k11.RELEASE) if pre else None,'parent':chain(DATA),
                     'directory_name':k11.RELEASE_DIRECTORY,'file_name':k11.RELEASE_FILE,'container_target':None if pre else k11.TARGET,'directory_entries':None if pre else 1},
          'policy':{'sha256':f.sha(k11.POLICY),'bytes':len(k11.POLICY),'content_b64':k11.b64(k11.POLICY),'valid_at':k11.VALID_AT},
          'render':{'project':'c3po','env_file':DEPLOY+'/.env','files':[DEPLOY+'/c3po/compose.yml'],'override_b64':k11.b64(override),'override_sha256':f.sha(override),'override_bytes':len(override)},
          'deploy':{'tree':chain(DEPLOY),'lock_directory':chain(LOCKS),'lock_name':'deployment.lock','version_name':'.deploy-version'},
          'units':[{'name':'docker.service','expected':None}],'journal':{'path':k11.JOURNAL,'floor_bytes':1},'docker_config':None,'rows_in_receipt':False,'bind_probe':None,
          # a reduced dry run: without docker nothing of the container can be exercised here; the live directory and the floor of the volume are
          'dry_run':'REDUCED' if pre else None,'live':{'parent':chain(DATA+'/r2d2-v2-live'),'directory_name':k11.LIVE_NAME},'limits':{'render_ms':3000,'quick_ms':1500,'data_volume_free_bytes':1,'data_volume_free_inodes':1}}
    plan.update(changes);return plan
def child(root,plan,tmp_path):
    path=Path(str(tmp_path))/'fields.json';path.write_bytes(json.dumps(plan).encode())
    done=subprocess.run([sys.executable,'-B',str(Path(native_child_k11.__file__)),str(root),str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        env=dict(ENV,HOME=os.environ.get('HOME','')),timeout=120)
    assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    result=json.loads(done.stdout);return result['receipt'],result['events'],result['calls']
def snapshot(root):
    out={}
    for path in sorted([root]+list(root.rglob('*'))):
        info=os.lstat(path);out[str(path.relative_to(root))]=(stat.S_IFMT(info.st_mode),stat.S_IMODE(info.st_mode),info.st_nlink,info.st_ino,info.st_mtime_ns,
                                                              info.st_size if stat.S_ISREG(info.st_mode) else None)
    return out
FILESYSTEM_ITEMS=('boot','directory:RELEASE_PARENT','directory:DEPLOY_TREE','directory:LOCK_DIRECTORY','directory:LIVE_PARENT','release_target','live_target','deploy_files',
                  'maintenance_pin','journal','lock','reboot_pending','reboot_required','directories_stable')

@pytest.mark.parametrize('mode',['PRE','POST'])
def test_native_run_reads_with_read_only_system_calls_and_leaves_no_trace(tree,tmp_path,mode):
    if mode=='POST':install(tree)
    before=snapshot(tree);receipt,events,calls=child(tree,fields(tree,mode),tmp_path)
    assert snapshot(tree)==before,'nothing created, removed or modified (sizes, link counts, modification times)'
    # The temporary tree is one filesystem: its "data volume" is no mount point, and the dry run says so as it would on
    # a host where the volume is not mounted (install_release refuses that). Nothing else is found.
    volume=['DIRECTORY_NOT_ACCEPTABLE_TO_THE_WRITE_THAT_FOLLOWS'] if mode=='PRE' else []
    assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and receipt['findings']==volume,receipt['findings']
    assert (receipt['items']['directory:RELEASE_PARENT']['rows_refusal'],receipt['items']['directory:RELEASE_PARENT']['mount_point_is_the_data_volume'])==('DATA_VOLUME_NOT_A_MOUNT_POINT',False)
    for name in FILESYSTEM_ITEMS:assert receipt['items'][name]['status']=='COMPLETE' and receipt['items'][name]['findings']==(volume if name=='directory:RELEASE_PARENT' else []),(name,receipt['items'][name])
    assert sorted(receipt['items_not_complete'])==['containers','image','render','unit:docker.service','verify','worker','worker_environment']
    assert receipt['fact_items_not_observed']==['unit:docker.service'] and receipt['items']['live_target']['exists'] is False
    parent=receipt['items']['directory:RELEASE_PARENT'];assert parent['bytes_available']>=parent['free_bytes_floor']==1 and receipt['items']['maintenance_pin']['root_owned'] is True
    assert parent['free_inodes_floor']==1 and (parent['inodes_available'] is None or parent['inodes_available']>=1),'the real fstatvfs of the workstation: inodes counted, or not counted at all'
    assert all(receipt['items'][name]['code']=='BINARY_UNAVAILABLE_OR_UNSAFE' for name in ('verify','containers','image','worker','render','unit:docker.service'))
    assert receipt['commands_started']=={'READ':0,'CONTAINER':0,'EFFECT':0} and receipt['mutating_calls']['issued']==0
    # every open: read-only, no link followed, by dir_fd except the root, with the no-atime flag on every directory walk
    opens=[entry for entry in calls if entry['call']=='open'];assert opens and all(not entry['flags']&WRITE and entry['flags']&os.O_NOFOLLOW for entry in opens)
    assert all(entry['by_dir_fd'] or entry['path']=='/' for entry in opens) and not [entry for entry in calls if entry['call']=='stat' and entry['follow_symlinks']]
    assert not [entry for entry in calls if entry['call'] in ('mkdir','fsync','link','unlink','umask','readlink')]
    assert [entry['operation'] for entry in calls if entry['call']=='flock']==[fcntl.LOCK_SH|fcntl.LOCK_NB,fcntl.LOCK_UN]
    assert not [event for event in events if event[0]!='open'],'no file-changing and no process-starting event in the interpreter: %r'%events[:3]
    assert receipt['items']['lock']['state']=='FREE' and receipt['items']['journal']['at_or_above_the_floor'] is True and receipt['items']['journal']['bytes_available']>0
    if mode=='POST':
        target=receipt['items']['release_target'];assert target['file']['bytes_equal_signed'] is True and target['directory']['entries']==1
        assert receipt['items']['directories_stable']['directories']['RELEASE_DIRECTORY'] is True
        read=[entry for entry in opens if entry['path'].endswith('/'+k11.RELEASE_FILE)];assert len(read)==1 and read[0]['flags']&os.O_NONBLOCK and read[0]['noatime']
    else:assert receipt['items']['release_target']['exists'] is False

def test_native_run_on_hostile_states_of_a_real_filesystem(tree,tmp_path):
    """Real symbolic links, a real second link, a real foreign file and a lock another descriptor holds."""
    directory=install(tree);os.link(directory/k11.RELEASE_FILE,tree/'mnt/day-d-data/second-name')
    receipt,events,calls=child(tree,fields(tree,'POST'),tmp_path);assert receipt['items']['release_target']['findings']==['RELEASE_FILE_METADATA'] and receipt['items']['release_target']['file']['links']==2
    os.unlink(tree/'mnt/day-d-data/second-name');(directory/k11.RELEASE_FILE).unlink();os.symlink(str(tree/'opt/chief-of-staff-digital/.env'),directory/k11.RELEASE_FILE)
    receipt,events,calls=child(tree,fields(tree,'POST'),tmp_path);assert receipt['items']['release_target']['findings']==['RELEASE_FILE_NOT_REGULAR'] and receipt['items']['release_target']['file']['type']=='symlink'
    assert not [entry for entry in calls if entry['call']=='open' and entry['path'].endswith('/'+k11.RELEASE_FILE)],'a link is classified by lstat and never opened'
    (directory/k11.RELEASE_FILE).unlink();(directory/k11.RELEASE_FILE).write_bytes(k11.RELEASE[:-1]+b' ');os.chmod(directory/k11.RELEASE_FILE,0o600);(directory/'foreign').write_bytes(b'x')
    receipt,events,calls=child(tree,fields(tree,'POST'),tmp_path);assert receipt['items']['release_target']['findings']==['RELEASE_DIRECTORY_ENTRIES','RELEASE_FILE_BYTES_MISMATCH']
    plan=fields(tree,'POST');os.rename(tree/'opt/chief-of-staff-digital/runtime',tree/'opt/chief-of-staff-digital/runtime.real');os.symlink('runtime.real',tree/'opt/chief-of-staff-digital/runtime')
    receipt,events,calls=child(tree,plan,tmp_path);assert receipt['items']['directory:LOCK_DIRECTORY']['findings']==['PARENT_SYMLINK_COMPONENT'] and receipt['items']['lock']['code']=='DIRECTORY_NOT_HELD'
    assert receipt['items']['directory:DEPLOY_TREE']['findings']==['PARENT_IDENTITY_MISMATCH'] or receipt['items']['directory:DEPLOY_TREE']['as_signed'] is True
    os.unlink(tree/'opt/chief-of-staff-digital/runtime');os.rename(tree/'opt/chief-of-staff-digital/runtime.real',tree/'opt/chief-of-staff-digital/runtime')
    with open(tree/'opt/chief-of-staff-digital/runtime/security/deployment.lock','rb') as holder:
        fcntl.flock(holder,fcntl.LOCK_EX|fcntl.LOCK_NB);receipt,events,calls=child(tree,fields(tree,'POST',signed=False),tmp_path)
    assert receipt['items']['lock']['state']=='BUSY' and receipt['items']['lock']['status']=='COMPLETE','a lock another process holds is seen and nothing waits'
    assert receipt['items']['directory:LOCK_DIRECTORY']['as_signed'] is None and receipt['items']['directory:LOCK_DIRECTORY']['held'] is True
    # what stands where activate will create: a real directory, then a real dangling link, each seen by lstat and never opened
    live=tree/'mnt/day-d-data/r2d2-v2-live'/k11.LIVE_NAME;live.mkdir(mode=0o700)
    receipt,events,calls=child(tree,fields(tree,'POST'),tmp_path);assert receipt['items']['live_target']['findings']==['LIVE_DIRECTORY_ALREADY_EXISTS'] and receipt['items']['live_target']['type']=='dir'
    live.rmdir();os.symlink('/nonexistent',live)
    receipt,events,calls=child(tree,fields(tree,'PRE'),tmp_path);assert (receipt['items']['live_target']['findings'],receipt['items']['live_target']['type'])==(['LIVE_DIRECTORY_ALREADY_EXISTS'],'symlink')
    assert not [entry for entry in calls if entry['call']=='open' and entry['path'].endswith('/'+k11.LIVE_NAME)]
