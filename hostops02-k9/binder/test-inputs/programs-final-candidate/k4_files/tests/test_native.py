"""The K4 files modes with the real system calls, made by the source's own unmodified Native, on a private temporary
tree that stands in for '/'. No host, no docker, no process started by the source. The substitution of '/' and of the
uid is made on the os module (tests/oslevel.py of the frozen core) and every system call is recorded with the arguments
it received. On the workstation this proves real open/write/fsync/link/unlink and mkdir by dir_fd, real
O_EXCL|O_NOFOLLOW, real refusals and a real process death, with macOS errno values as an ordinary user; the kernel's
O_NOATIME, Linux errno values and real uid 0 only when the suite is run as root on Linux (set 3: NOT RUN by the author)."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

import family as f
import k4f
import native_child
import oslevel

ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
BOOT=b'0f8fad5b-d9cb-469f-a165-70867728950e\n'
WRITE_FLAGS=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND|os.O_EXCL

@pytest.fixture
def tree(tmp_path):
    """A private tree for "/": the provisioned reader and capacity directories (0700), the unit directory (0755), the
    boot identifier; with `pins=True` (see delivered) also what B5, A8 and B2 leave before B6."""
    root=Path(str(tmp_path)).resolve()/'root';root.mkdir(mode=0o755)
    for path in ('proc/sys/kernel/random','etc/systemd/system','var/lib/c3po-capacity/documents','var/lib/c3po-capacity/config',
                 'var/lib/c3po-capacity/payload','var/lib/c3po-capacity/go','etc/c3po-reader/docker-cli','var/lib/c3po/r2d2-v2-source-20261005',
                 'var/lib/c3po-bar/journal'):(root/path).mkdir(parents=True)
    for path in list(root.rglob('*'))+[root]:os.chmod(path,0o755)
    for path in ('etc/c3po-reader','etc/c3po-reader/docker-cli','var/lib/c3po-capacity','var/lib/c3po-capacity/documents','var/lib/c3po-capacity/config',
                 'var/lib/c3po-capacity/payload','var/lib/c3po-capacity/go','var/lib/c3po','var/lib/c3po/r2d2-v2-source-20261005','var/lib/c3po-bar',
                 'var/lib/c3po-bar/journal'):os.chmod(root/path,0o700)
    (root/'proc/sys/kernel/random/boot_id').write_bytes(BOOT)
    return root

def delivered(root,m):
    """What B5, A8 and B2 leave before B6: the static config, the launcher, the two units."""
    for relative,content,mode in (('var/lib/c3po-capacity/config/week.static.capacity.json',k4f.static_config(m),0o600),
                                  ('etc/systemd/system/c3po-massive.service',k4f.producer_unit(),0o644),
                                  ('etc/systemd/system/c3po-reader.service',k4f.reader_unit(),0o644)):
        (root/relative).write_bytes(content);os.chmod(root/relative,mode)
    (root/'etc/c3po-reader/launcher').mkdir();os.chmod(root/'etc/c3po-reader/launcher',0o700)
    (root/'etc/c3po-reader/launcher/reader_launcher.py').write_bytes(k4f.LAUNCHER);os.chmod(root/'etc/c3po-reader/launcher/reader_launcher.py',0o600)

def fields(root,mode,m):
    rows=lambda path:oslevel.rows(root,path);boot=f.sha(BOOT.strip())
    if mode=='CHAIN_STATIC':
        delivery={'documents_parent':rows(k4f.DOCUMENTS),'config_parent':rows(k4f.CONFIG),'static_config':k4f.member(k4f.static_config(m))}
    elif mode=='PINS':
        values=k4f.pins_values(m);raw=k4f.render(values,m)
        delivery={'reader_parent':rows(k4f.READER),'config_parent':rows(k4f.CONFIG),'unit_parent':rows(k4f.UNITS),'values':values,'sha256':f.sha(raw),
                  'source_chain':rows(k4f.SOURCE_ROOT),'journal_chain':rows(k4f.JOURNAL_HOST),
                  'bytes':len(raw),'producer_unit_sha256':f.sha(k4f.producer_unit()),'reader_unit_sha256':f.sha(k4f.reader_unit())}
    elif mode=='WRITER':delivery={'config_parent':rows(k4f.CONFIG),'writer_sha256':m.K4_WRITER[0]}
    else:delivery={'reader_parent':rows(k4f.READER),'launcher':k4f.member(k4f.LAUNCHER)}
    return {'mode':mode,'delivery':delivery,'evidence_boot_id_sha256':boot}

def child(root,plan,tmp_path,point=None):
    path=Path(str(tmp_path))/'fields.json';path.write_bytes(json.dumps(plan).encode())
    command=[sys.executable,'-B',str(Path(native_child.__file__)),str(root),str(path)]+([point] if point else [])
    return subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(ENV,HOME=os.environ.get('HOME','')),timeout=120)

def snapshot(root):
    out={}
    for path in sorted([root]+list(root.rglob('*'))):
        info=os.lstat(path);out[str(path.relative_to(root))]=(stat.S_IFMT(info.st_mode),stat.S_IMODE(info.st_mode),info.st_nlink,info.st_ino,info.st_mtime_ns,
                                                              info.st_size if stat.S_ISREG(info.st_mode) else None)
    return out

def run(root,plan):
    k=k4f.K();old=os.umask(0o027)
    try:
        with oslevel.Substitute(root) as record:receipt=f.Docs(k,plan).run(None)
    finally:os.umask(old)
    receipt['_calls']=record.calls;return receipt

@pytest.mark.parametrize('mode',['CHAIN_STATIC','PINS','LAUNCHER','WRITER'],ids=['chain','pins','launcher','writer'])
def test_native_each_mode_creates_exactly_its_files_with_these_system_calls(tree,tmp_path,mode):
    m=k4f.K().m
    if mode=='PINS':delivered(tree,m)
    before=snapshot(tree);done=child(tree,fields(tree,mode,m),tmp_path);assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    result=json.loads(done.stdout);receipt,events,calls=result['receipt'],result['events'],result['calls']
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('METADATA_ONLY_REQUIRES_REVIEW','K4_FILES_DELIVERED_READ_BACK',None),receipt
    wanted={'CHAIN_STATIC':[k4f.DOCUMENTS+'/'+row[1] for row in m.K4_CHAIN_DOCUMENTS]+[k4f.STATIC],'PINS':[k4f.PINS],'LAUNCHER':[k4f.LAUNCHER_FILE],
            'WRITER':[k4f.writer_path(m)]}[mode]
    contents={'CHAIN_STATIC':[m.chain_document_bytes(index) for index in range(7)]+[k4f.static_config(m)],'PINS':[k4f.render(k4f.pins_values(m),m)],
              'LAUNCHER':[k4f.LAUNCHER],'WRITER':[m.writer_bytes()]}[mode]
    for path,raw in zip(wanted,contents):
        info=os.lstat(tree/path[1:]);assert (stat.S_ISREG(info.st_mode),stat.S_IMODE(info.st_mode),info.st_nlink)==(True,0o600,1) and (tree/path[1:]).read_bytes()==raw
    created=sorted(set(snapshot(tree))-set(before))
    assert created==sorted([path[1:] for path in wanted]+(['etc/c3po-reader/launcher'] if mode=='LAUNCHER' else []))
    after=snapshot(tree);receiving={path.rsplit('/',1)[0][1:] for path in wanted}|({'etc/c3po-reader'} if mode=='LAUNCHER' else set())
    assert {name:value for name,value in after.items() if name in before and name not in receiving}=={name:value for name,value in before.items() if name not in receiving}
    opens=[entry for entry in calls if entry['call']=='open' and not entry['flags']&os.O_CREAT]
    assert opens and all(entry['flags']&os.O_NOFOLLOW for entry in opens) and all(not entry['flags']&WRITE_FLAGS for entry in opens)
    assert all(entry['by_dir_fd'] or entry['path']=='/' for entry in opens),'only "/" is opened by absolute path'
    changing=[entry for entry in calls if entry['call'] in ('mkdir','link','unlink') or (entry['call']=='open' and entry['flags']&os.O_CREAT)]
    expected=[('mkdir',k4f.LAUNCHER_DIRECTORY)] if mode=='LAUNCHER' else []
    for index,path in enumerate(wanted):
        temporary=path.rsplit('/',1)[0]+'/.hostops-%s-%d.partial'%(result['go16'],index);expected+=[('open',temporary),('link',path),('unlink',temporary)]
    assert [(entry['call'],entry['path']) for entry in changing]==expected and all(entry['by_dir_fd'] for entry in changing)
    creates=[entry for entry in changing if entry['call']=='open'];bits=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC
    assert all(entry['flags']&bits==bits and not entry['flags']&(os.O_TRUNC|os.O_APPEND) and entry['mode']==0o600 for entry in creates)
    assert all(entry['follow_symlinks'] is False and entry['same_directory'] for entry in changing if entry['call']=='link')
    assert [entry['mask'] for entry in calls if entry['call']=='umask']==[0o077]
    assert {event[0] for event in events}<={'open','open-for-writing','os.link','os.mkdir','os.remove'}
    assert [event[0] for event in events if event[0]!='open']==(['os.mkdir'] if mode=='LAUNCHER' else [])+['open-for-writing','os.link','os.remove']*len(wanted)

def test_native_run_records_where_it_ran_for_the_linux_proof(tree,tmp_path,request):
    m=k4f.K().m;euid,egid=os.geteuid(),os.getegid();done=child(tree,fields(tree,'CHAIN_STATIC',m),tmp_path)
    assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    result=json.loads(done.stdout);receipt=result['receipt'];assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW',receipt
    leaf=os.lstat(tree/k4f.STATIC[1:]);sums=k4f.DIRECTORY/'SHA256SUMS'
    facts={'payload_sha256':f.sha(k4f.K().source),'sha256sums_sha256':f.sha(sums.read_bytes()) if sums.is_file() else 'ABSENT','euid':euid,'egid':egid,
           'platform':sys.platform,'python':'%d.%d.%d'%sys.version_info[:3],'noatime_is_the_kernel_flag':bool(result['noatime_is_the_kernel_flag']),
           'created_file':'%d:%d:%04o:%d'%(leaf.st_uid,leaf.st_gid,stat.S_IMODE(leaf.st_mode),leaf.st_nlink),'receipt_status':receipt['status'],
           'mutating_calls_succeeded':receipt['mutating_calls']['succeeded']}
    for name,value in sorted(facts.items()):request.node.user_properties.append(('k4files_'+name,value))
    if euid==0 and sys.platform.startswith('linux'):assert facts['noatime_is_the_kernel_flag'] and facts['created_file']=='0:0:0600:1',facts

def test_native_refusals_leave_the_real_tree_exactly_as_it_was(tree):
    m=k4f.K().m
    def refused(plan,code):
        before=snapshot(tree);receipt=run(tree,plan)
        assert (receipt['status'],receipt['code'])==('REFUSED',code),receipt['code'];assert snapshot(tree)==before and receipt['mutating_calls']['issued']==0
        assert not [entry for entry in receipt['_calls'] if entry['call'] in ('mkdir','link','unlink','fsync') or (entry['call']=='open' and entry['flags']&os.O_CREAT)]
    documents=tree/'var/lib/c3po-capacity/documents';plan=fields(tree,'CHAIN_STATIC',m)
    (documents/'ADENDO_EPOCA_03.md').write_bytes(b'x');refused(plan,'CHAIN_DOCUMENT_PRESENT');os.unlink(documents/'ADENDO_EPOCA_03.md')
    os.symlink('nowhere',documents/'B_DUDU_ADENDO_EPOCA_03.md');refused(plan,'CHAIN_DOCUMENT_PRESENT');os.unlink(documents/'B_DUDU_ADENDO_EPOCA_03.md')
    os.chmod(documents,0o750);refused(plan,'PARENT_IDENTITY_MISMATCH');os.chmod(documents,0o700)
    (tree/'proc/sys/kernel/random/boot_id').write_bytes(b'1f8fad5b-d9cb-469f-a165-70867728950e\n');refused(plan,'EVIDENCE_FROM_EARLIER_BOOT')
    (tree/'proc/sys/kernel/random/boot_id').write_bytes(BOOT)
    plan=fields(tree,'LAUNCHER',m);(tree/'etc/c3po-reader/launcher').mkdir();os.chmod(tree/'etc/c3po-reader/launcher',0o755)
    refused(plan,'LAUNCHER_DIRECTORY_PRESENT_INVALID');os.chmod(tree/'etc/c3po-reader/launcher',0o700)
    (tree/'etc/c3po-reader/launcher/reader_launcher.py').write_bytes(b'other');os.chmod(tree/'etc/c3po-reader/launcher/reader_launcher.py',0o600)
    refused(plan,'LAUNCHER_DIRECTORY_PRESENT');os.unlink(tree/'etc/c3po-reader/launcher/reader_launcher.py');os.rmdir(tree/'etc/c3po-reader/launcher')
    delivered(tree,m);plan=fields(tree,'PINS',m);launcher=tree/'etc/c3po-reader/launcher/reader_launcher.py'
    launcher.write_bytes(k4f.LAUNCHER+b'#');refused(plan,'LAUNCHER_FILE_NOT_THE_SIGNED_BYTES');launcher.write_bytes(k4f.LAUNCHER)
    os.chmod(launcher,0o644);refused(plan,'LAUNCHER_FILE_METADATA');os.chmod(launcher,0o600)
    os.link(launcher,tree/'etc/c3po-reader/launcher-second-link');refused(plan,'LAUNCHER_FILE_METADATA')
    os.unlink(tree/'etc/c3po-reader/launcher-second-link')
    os.rename(launcher,tree/'proc/launcher-real');os.symlink('../../../proc/launcher-real',launcher);refused(plan,'PRECHECK_OS_ERROR')
    os.unlink(launcher);os.rename(tree/'proc/launcher-real',launcher)
    os.chmod(tree/'etc/systemd/system/c3po-reader.service',0o664);refused(plan,'READER_UNIT_METADATA');os.chmod(tree/'etc/systemd/system/c3po-reader.service',0o644)
    (tree/'etc/c3po-reader/pins.env').write_bytes(b'x');refused(plan,'PINS_ENV_PRESENT')

@pytest.mark.parametrize('point,written',[('in_write',0),('after_link_1',1),('after_link_4',4),('after_link_8',8)])
def test_native_process_death_leaves_only_complete_files_under_final_names(tree,tmp_path,point,written):
    m=k4f.K().m;done=child(tree,fields(tree,'CHAIN_STATIC',m),tmp_path,point)
    assert done.returncode==137 and done.stdout==b''
    paths=[k4f.DOCUMENTS+'/'+row[1] for row in m.K4_CHAIN_DOCUMENTS]+[k4f.STATIC]
    contents=[m.chain_document_bytes(index) for index in range(7)]+[k4f.static_config(m)]
    present=[path for path in paths if (tree/path[1:]).exists()];assert present==paths[:written]
    for path,raw in zip(paths[:written],contents):assert (tree/path[1:]).read_bytes()==raw
    leftovers=[item.name for directory in ('var/lib/c3po-capacity/documents','var/lib/c3po-capacity/config') for item in (tree/directory).iterdir()
               if item.name.startswith('.hostops-')]
    assert len(leftovers)==1,'the one temporary of the step that died stays (no removal in the family)'
