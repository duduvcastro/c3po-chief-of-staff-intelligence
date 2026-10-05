"""The pinned script, run for real against the application modules of the release in a real directory, compared with
the model that stands for the container in the emulated tests (k2a.catalog_model), and with the bytes the operation's
readback expects. This is what keeps the emulated container from being this suite's opinion of the application.
Needs a tree of the release (k2a.release_tree); skipped without one. No host, no docker: `python -B -` in a child
process whose working directory is c3po/backend of that tree, the root a private temporary directory."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

import family as f
import k2a

ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
def backend():
    tree=k2a.release_tree()
    if tree is None:pytest.skip('no tree of the release at hand (HOSTOPS02_TEST_RELEASE_TREE)')
    return tree/'c3po'/'backend'
def real(root,*arguments):
    """The script as the container gets it: on standard input, with its arguments, `app` importable."""
    done=subprocess.run([sys.executable,'-B','-',str(root)]+list(arguments),input=k2a.script(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,cwd=str(backend()),timeout=60)
    assert done.stderr==b'',done.stderr.decode()[-2000:]
    return done.returncode,done.stdout
def model(root,*arguments):return k2a.catalog_model(k2a.RealDirectory(),[str(root)]+list(arguments),euid=os.geteuid())
def content(root):
    out={}
    for name in sorted(os.listdir(root)):
        info=os.lstat(root/name);out[name]=(stat.S_IFMT(info.st_mode),stat.S_IMODE(info.st_mode),info.st_nlink,(root/name).read_bytes() if stat.S_ISREG(info.st_mode) else None)
    return out
def pair(tmp_path,name,mode=0o700,prepare=None):
    roots=[]
    for label in ('real','model'):
        root=Path(str(tmp_path)).resolve()/(name+'-'+label);root.mkdir();os.chmod(root,mode)
        if prepare:prepare(root)
        roots.append(root)
    return roots
def same(left,right,roots):
    """Equal exit status and equal line, device and inode apart (two directories); each equal to its own directory's."""
    assert left[0]==right[0] and left[1].count(b'\n')==1==right[1].count(b'\n') and left[1].endswith(b'\n')
    rows=[json.loads(raw) for raw in (left[1],right[1])]
    for row,root in zip(rows,roots):
        if row['status']=='CATALOG_READY':
            info=os.stat(root);assert (row.pop('device'),row.pop('inode'))==(info.st_dev,info.st_ino)
    assert rows[0]==rows[1];return rows[0]

def test_real_script_and_model_agree_on_an_empty_root_and_the_bytes_are_what_the_readback_expects(tmp_path):
    m=k2a.K().m;roots=pair(tmp_path,'empty');row=same(real(roots[0],k2a.DIAG),model(roots[1],k2a.DIAG),roots)
    assert row=={'status':'CATALOG_READY','created':True,'epoch':k2a.DIAG,'entries':['epoch.json','maintenance.lock']}
    for root in roots:
        info=os.stat(root);found=content(root)
        expected=m.canonical({'schema':m.CATALOG_SCHEMA,'epoch':k2a.DIAG,'device':info.st_dev,'inode':info.st_ino})
        assert found=={'epoch.json':(stat.S_IFREG,0o600,1,expected),'maintenance.lock':(stat.S_IFREG,0o600,1,b'')} and expected==k2a.expected_epoch_json(k2a.DIAG,info.st_dev,info.st_ino)
        assert stat.S_IMODE(info.st_mode)==0o700,'the root itself is not changed'

def test_real_script_and_model_agree_on_a_second_run_another_epoch_and_a_string_that_is_no_epoch(tmp_path):
    roots=pair(tmp_path,'again');same(real(roots[0],k2a.EPOCH),model(roots[1],k2a.EPOCH),roots);before=[content(root) for root in roots]
    row=same(real(roots[0],k2a.EPOCH),model(roots[1],k2a.EPOCH),roots);assert row['created'] is False and [content(root) for root in roots]==before
    row=same(real(roots[0],k2a.DIAG),model(roots[1],k2a.DIAG),roots);assert row=={'status':'CATALOG_REFUSED','code':'MASSIVE_SESSION_MANIFEST_CHANGED'}
    row=same(real(roots[0],'not an epoch'),model(roots[1],'not an epoch'),roots);assert row=={'status':'CATALOG_REFUSED','code':'EPOCH_INVALID'}
    row=same(real(roots[0]),model(roots[1]),roots);assert row['status']=='CATALOG_REFUSED' and 'unpack' in row['code'],'the known wart: the text of the exception'
    assert [content(root) for root in roots]==before
    fresh=pair(tmp_path,'no-epoch');assert same(real(fresh[0],'R2D2-V3-SHADOW-X'),model(fresh[1],'R2D2-V3-SHADOW-X'),fresh)['code']=='EPOCH_INVALID' and [content(root) for root in fresh]==[{},{}]

def test_real_script_and_model_agree_on_a_root_that_is_not_empty_or_not_private(tmp_path):
    for name,prepare in (('lock',lambda root:(root/'producer.lock').touch(mode=0o600)),('directory',lambda root:(root/'lost+found').mkdir(mode=0o700)),
                         ('only-the-lock',lambda root:(root/'maintenance.lock').touch(mode=0o600))):
        roots=pair(tmp_path,name,prepare=prepare);before=[content(root) for root in roots]
        assert same(real(roots[0],k2a.DIAG),model(roots[1],k2a.DIAG),roots)=={'status':'CATALOG_REFUSED','code':'CATALOG_INIT_ROOT_NOT_EMPTY'} and [content(root) for root in roots]==before
    for mode in (0o750,0o755,0o701):
        roots=pair(tmp_path,'mode-%o'%mode,mode=mode)
        assert same(real(roots[0],k2a.DIAG),model(roots[1],k2a.DIAG),roots)=={'status':'CATALOG_REFUSED','code':'SOURCE_DIRECTORY_NOT_PRIVATE'} and [content(root) for root in roots]==[{},{}]

def test_the_reader_path_of_the_release_accepts_exactly_what_the_readback_verifies(tmp_path):
    """SessionJournalRoot without create (what the reader does) on a root that holds the two files with the expected
    bytes; and it refuses when epoch.json differs in the ways the readback calls a mismatch."""
    m=k2a.K().m;root=Path(str(tmp_path)).resolve()/'reader';root.mkdir();os.chmod(root,0o700);info=os.stat(root)
    program=("import sys\nsys.path.insert(0,'.')\nfrom app.r2d2_v2_massive_sessions import SessionJournalRoot\n"
             "try:\n    SessionJournalRoot(sys.argv[1],sys.argv[2]);print('ACCEPTED')\nexcept Exception as error:print(error.args[0])\n")
    def reader():
        done=subprocess.run([sys.executable,'-B','-c',program,str(root),k2a.DIAG],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,cwd=str(backend()),timeout=60)
        assert done.stderr==b'';return done.stdout.decode().strip()
    def put(name,raw,mode=0o600):
        path=root/name
        if path.exists():path.unlink()
        fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode);os.write(fd,raw);os.close(fd);os.chmod(path,mode)
    expected=m.canonical({'schema':m.CATALOG_SCHEMA,'epoch':k2a.DIAG,'device':info.st_dev,'inode':info.st_ino})
    put('maintenance.lock',b'');put('epoch.json',expected);assert reader()=='ACCEPTED'
    for raw in (m.canonical({'schema':m.CATALOG_SCHEMA,'epoch':k2a.EPOCH,'device':info.st_dev,'inode':info.st_ino}),
                m.canonical({'schema':m.CATALOG_SCHEMA,'epoch':k2a.DIAG,'device':info.st_dev,'inode':info.st_ino+1}),
                m.canonical({'schema':m.CATALOG_SCHEMA,'epoch':k2a.DIAG,'device':info.st_dev+1,'inode':info.st_ino}),b''):
        put('epoch.json',raw);assert reader()!='ACCEPTED'
    put('epoch.json',expected,0o644);assert reader()=='MASSIVE_SESSION_FILE_UNSAFE'
    put('epoch.json',expected);put('maintenance.lock',b'',0o640);assert reader()=='MASSIVE_MAINTENANCE_UNSAFE'
    put('maintenance.lock',b'');assert reader()=='ACCEPTED'
