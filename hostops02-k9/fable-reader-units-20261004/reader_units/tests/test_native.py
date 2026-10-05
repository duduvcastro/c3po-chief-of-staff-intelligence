"""The reader units with the real system calls, made by the source's own unmodified Native, on a private temporary tree
that stands in for '/'. No host, no docker, no process started by the source. The substitution of '/' and of the uid
is made on the os module (tests/oslevel.py of the frozen core; the data-volume device shift of tests/native_support.py,
a byte-identical copy of install_release's), and every system call is recorded with the arguments it received.
On the workstation this proves real lstat/open/read/write/fsync/link/unlink by dir_fd, real O_EXCL|O_NOFOLLOW, a real
race at the final name and a real process death, with macOS errno values as an ordinary user; the kernel's O_NOATIME,
Linux errno values and real uid 0 only when the suite is run as root on Linux (the Linux-root CI job: NOT RUN)."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import family as f
import native_child
import native_support
import native_tree
import ru

ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
WRITE_FLAGS=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND|os.O_EXCL
NAMES=[name for _,name in ru.NAMES]

def snapshot(root):
    out={}
    for path in sorted([root]+list(root.rglob('*'))):
        info=os.lstat(path);out[str(path.relative_to(root))]=(stat.S_IFMT(info.st_mode),stat.S_IMODE(info.st_mode),info.st_nlink,info.st_ino,info.st_mtime_ns,
                                                              info.st_size if stat.S_ISREG(info.st_mode) else None)
    return out
def run(root,plan,native=None):
    k=ru.K();old=os.umask(0o027)
    try:
        with native_support.Volume(root) as record:receipt=f.Docs(k,plan).run(native() if native else None)
    finally:os.umask(old)
    receipt['_calls']=record.calls;return receipt
def child(root,plan,tmp_path,point):
    path=Path(str(tmp_path))/'fields.json';path.write_bytes(json.dumps(plan).encode())
    command=[sys.executable,'-B',str(Path(native_child.__file__)),str(root),str(path),point]
    return subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(ENV,HOME=os.environ.get('HOME','')),timeout=120)

def test_native_run_installs_the_three_units_with_exactly_these_system_calls(tmp_path):
    root=native_tree.build(tmp_path);units=root/'etc'/'systemd'/'system';before=set(os.listdir(units))
    receipt=run(root,native_tree.fields(root));calls=receipt.pop('_calls');done=ru.K().m.rendered_units()
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('METADATA_ONLY_REQUIRES_REVIEW','UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED',None),receipt['code']
    assert set(os.listdir(units))-before==set(NAMES)
    for key,name in ru.NAMES:
        info=os.lstat(units/name);assert (units/name).read_bytes()==done[key]
        assert (stat.S_ISREG(info.st_mode),stat.S_IMODE(info.st_mode),info.st_nlink)==(True,0o644,1)
    opens=[entry for entry in calls if entry['call']=='open' and not entry['flags']&os.O_CREAT]
    assert opens and all(entry['flags']&os.O_NOFOLLOW for entry in opens) and not any(entry['flags']&WRITE_FLAGS for entry in opens)
    assert all(entry['by_dir_fd'] or entry['path']=='/' for entry in opens)
    assert not [entry for entry in opens if entry['path'].startswith(ru.JOURNAL+'/') or entry['path'].startswith(ru.DATA+'/')]
    stats=[entry for entry in calls if entry['call']=='stat'];assert stats and all(entry['follow_symlinks'] is False and entry['by_dir_fd'] for entry in stats)
    go16=f.Docs(ru.K(),native_tree.fields(root)).go16()
    temporaries=[ru.UNITS+'/.hostops-%s-%d.partial'%(go16,index) for index in range(3)]
    changing=[entry for entry in calls if entry['call'] in ('mkdir','link','unlink') or (entry['call']=='open' and entry['flags']&os.O_CREAT)]
    assert [(entry['call'],entry['path']) for entry in changing]==[item for index,name in enumerate(NAMES) for item in
        (('open',temporaries[index]),('link',ru.UNITS+'/'+name),('unlink',temporaries[index]))]
    wanted=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC
    for entry in changing:
        assert entry['by_dir_fd']
        if entry['call']=='open':assert entry['flags']&wanted==wanted and not entry['flags']&(os.O_TRUNC|os.O_APPEND) and entry['mode']==0o644
        if entry['call']=='link':assert entry['follow_symlinks'] is False and entry['same_directory']
    assert [entry['mask'] for entry in calls if entry['call']=='umask']==[0o022]
    assert receipt['catalog']['epoch.json']['mode_octal']=='0600' and receipt['producer']['sha256']==ru.unit_texts.PRODUCER_RENDER_SHA256

def test_native_precheck_refusal_changes_nothing(tmp_path):
    root=native_tree.build(tmp_path);(root/'etc'/'systemd'/'system'/'c3po-reader.timer.d').mkdir();before=snapshot(root)
    receipt=run(root,native_tree.fields(root));calls=receipt.pop('_calls')
    assert (receipt['status'],receipt['code'])==('REFUSED','DROP_IN_PRESENT') and snapshot(root)==before
    assert not [entry for entry in calls if entry['call'] in ('mkdir','link','unlink') or (entry['call']=='open' and entry['flags']&os.O_CREAT)]

def test_native_catalogue_absent_refuses(tmp_path):
    root=native_tree.build(tmp_path);os.unlink(root/'var'/'lib'/'c3po-bar'/'journal'/'epoch.json');before=snapshot(root)
    receipt=run(root,native_tree.fields(root));receipt.pop('_calls')
    assert (receipt['status'],receipt['code'])==('REFUSED','CATALOG_NOT_INITIALISED') and snapshot(root)==before

def test_native_a_name_taken_at_the_last_moment_is_not_replaced(tmp_path):
    root=native_tree.build(tmp_path);units=root/'etc'/'systemd'/'system';native=ru.K().m.Native
    class Racing(native):
        def link(self,source,target,dir_fd):
            if target=='c3po-reader.timer':
                descriptor=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644,dir_fd=dir_fd);os.write(descriptor,b'other\n');os.close(descriptor)
            return native.link(self,source,target,dir_fd)
    receipt=run(root,native_tree.fields(root),Racing);receipt.pop('_calls')
    assert (receipt['outcome'],receipt['code'])==('PARTIAL_REQUIRES_RECONCILIATION','DESTINATION_APPEARED_AFTER_PRECHECK')
    assert (units/'c3po-reader.timer').read_bytes()==b'other\n' and not (units/'c3po-reader-alert.service').exists()
    assert [row['state'] for row in receipt['ledger']]==['INSTALLED_DURABLE','NOT_CREATED','NOT_ATTEMPTED']
    assert not [name for name in os.listdir(units) if name.startswith('.hostops')]

def test_native_death_after_the_first_link_leaves_what_the_next_precheck_reports(tmp_path):
    root=native_tree.build(tmp_path);units=root/'etc'/'systemd'/'system';plan=native_tree.fields(root)
    done=child(root,plan,tmp_path,'after_link_1');assert done.returncode==137 and done.stdout==b'',done.stderr.decode()[-2000:]
    go16=f.Docs(ru.K(),plan).go16();temporary='.hostops-%s-0.partial'%go16
    assert (units/'c3po-reader.service').read_bytes()==ru.K().m.rendered_units()['READER_SERVICE']
    assert os.lstat(units/temporary).st_ino==os.lstat(units/'c3po-reader.service').st_ino and os.lstat(units/temporary).st_nlink==2
    receipt=run(root,native_tree.fields(root));receipt.pop('_calls')
    assert receipt['code']=='PRIOR_PARTIAL_REQUIRES_RECONCILIATION' and receipt['precheck']['conflicts']['leftovers_not_acknowledged']==[temporary]

def test_native_death_in_a_write_leaves_only_a_temporary(tmp_path):
    root=native_tree.build(tmp_path);units=root/'etc'/'systemd'/'system';plan=native_tree.fields(root)
    done=child(root,plan,tmp_path,'in_write_2');assert done.returncode==137,done.stderr.decode()[-2000:]
    go16=f.Docs(ru.K(),plan).go16()
    assert (units/'c3po-reader.service').exists() and not (units/'c3po-reader.timer').exists()
    assert sorted(name for name in os.listdir(units) if name.startswith('.hostops'))==['.hostops-%s-1.partial'%go16]
