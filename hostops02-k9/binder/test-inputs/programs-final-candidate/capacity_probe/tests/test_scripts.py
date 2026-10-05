"""The REAL pinned scripts, in a child interpreter under `python -I -B -` as the container runs them, with a test-only
prelude written IN FRONT of the pinned bytes (never part of the source; tests/test_probe.py checks what the engine gets):

- CALENDAR: calendar-pin.py against the release's own modules (a tree of the release and an interpreter that has its
  requirements: the 3.12 test environment); its line must meet the source's grammar and name the epoch, the package
  and the document order the source pins. Without the release it must print its own refusal line.
- IDENT: the release's AnchoredRoot on a private temporary tree; the prelude maps /c3po-capacity to that tree for
  os.path.abspath only, so the identity covers the components of the temporary path and is compared with the release's
  digest of the same numbers. Refusals: a child that is not private, absent, or a link.
- LOAD: with a stub application (Settings and CapacityConfig that record what they get), every branch of the script;
  and, when the release and its requirements are at hand, the release's own Settings and CapacityConfig up to their
  first refusal on a private tree (the hash of the config), which proves the five settings are accepted by name.
- The digest: the source's identity function and the release's r2d2_v2_store.digest give the same hash.
Nothing here reaches a network or a host path outside the temporary directory of the test."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

import kprobe

K=kprobe.K
VENV=kprobe.app_python()

def release():
    tree=kprobe.release_tree()
    if tree is None:pytest.skip('no tree of the release at hand')
    return tree
def application_interpreter():
    """An interpreter that has the release's requirements (pydantic_settings, exchange_calendars), or a skip."""
    for candidate in (str(VENV) if VENV else None,sys.executable):
        if not candidate or not os.path.isfile(candidate):continue
        done=subprocess.run([candidate,'-I','-B','-c','import pydantic_settings, exchange_calendars'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if done.returncode==0:return candidate
    pytest.skip('no interpreter with the release requirements')

def run_script(stdin,python=None,timeout=120):
    started=time.monotonic()
    done=subprocess.run([python or sys.executable,'-I','-B','-'],input=stdin,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={'PATH':'/usr/bin:/bin'},timeout=timeout)
    return done.returncode,done.stdout,done.stderr,time.monotonic()-started
def prelude(*paths,abspath=None):
    text='import sys as _sys\n'+''.join('_sys.path.insert(0, %r)\n'%str(path) for path in paths)
    if abspath is not None:
        text+=('import os as _os\n_real_abspath=_os.path.abspath\n'
               '_os.path.abspath=lambda path: %r + path if path.startswith(\'/c3po-capacity\') else _real_abspath(path)\n')%str(abspath)
    return text.encode()
def one_line(step,returncode,out,err,expected_status):
    assert out.endswith(b'\n') and out.count(b'\n')==1,(returncode,out,err[-600:])
    row=json.loads(out);assert K().m.line_grammar(step,row) is True,row
    assert returncode==(0 if row['status']==K().m.OK_LINE_STATUS[step] else 1) and row['status']==expected_status,(returncode,row,err[-600:])
    return row


# ---------------------------------------------------------------- CALENDAR
def test_calendar_pin_in_the_release_prints_the_line_the_source_expects():
    tree=release();python=application_interpreter();m=K().m
    returncode,out,err,_=run_script(prelude(tree/'c3po'/'backend')+m.scripts()['CALENDAR'],python)
    row=one_line('CALENDAR',returncode,out,err,'CALENDAR_PIN')
    assert (row['epoch'],row['package_sha'],row['document_order_sha'])==(m.EPOCH_NAME,m.PACKAGE_SHA,m.DOCUMENT_ORDER)==(kprobe.EPOCH,kprobe.PACKAGE,kprobe.ORDER)
    version=subprocess.run([python,'-I','-c','import exchange_calendars;print(exchange_calendars.__version__)'],stdout=subprocess.PIPE).stdout.decode().strip()
    assert row['calendar_version']==version
    assert set(row)==set(kprobe.calendar_line()) and out==kprobe.calendar_bytes(row),'the model prints what the script prints'
    m.validate_members(kprobe.fields('CALENDAR'))
    assert m.expectation_code('CALENDAR',[{'line':row,'valid':True}],None) is None

def test_calendar_pin_without_the_application_prints_its_own_refusal():
    returncode,out,err,_=run_script(K().m.scripts()['CALENDAR'])
    row=one_line('CALENDAR',returncode,out,err,'CALENDAR_PIN_REFUSED');assert row['code']=='ModuleNotFoundError'
    assert K().m.expectation_code('CALENDAR',[{'line':row,'valid':True}],None)=='CALENDAR_PIN_REFUSED_IN_THE_IMAGE'


# ---------------------------------------------------------------- IDENT
def private_tree(tmp_path):
    root=Path(str(tmp_path)).resolve()/'host'/'c3po-capacity';root.mkdir(parents=True)
    os.chmod(str(root),0o700)
    for name in kprobe.CHILDREN:(root/name).mkdir(mode=0o700);os.chmod(str(root/name),0o700)
    return root
def store(tree):
    spec=importlib.util.spec_from_file_location('_release_store',str(tree/'c3po/backend/app/r2d2_v2_store.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def anchored_identity(digest,path):
    """The identity AnchoredRoot computes for path: [part, st_dev, st_ino] of every component below '/'."""
    parts=Path(path).parts[1:];nodes=[];current='/'
    for part in parts:
        current=os.path.join(current,part);info=os.stat(current,follow_symlinks=False);nodes.append([part,info.st_dev,info.st_ino])
    return digest(nodes)

@pytest.mark.parametrize('python',[sys.executable,'/usr/bin/python3'])
def test_ident_script_with_the_release_anchored_root_on_a_private_tree(tmp_path,python):
    tree=release();root=private_tree(tmp_path);digest=store(tree).digest
    stdin=prelude(tree/'c3po'/'backend',abspath=root.parent)+K().m.scripts()['IDENT']
    returncode,out,err,seconds=run_script(stdin,python)
    row=one_line('IDENT',returncode,out,err,'ROOT_IDENTITIES')
    assert row['identities']=={name:anchored_identity(digest,str(root/name)) for name in kprobe.CHILDREN}
    assert out==kprobe.compact(row) and seconds<14

def test_ident_script_refuses_with_the_release_code_or_the_class_name(tmp_path):
    tree=release()
    def link(root):os.rmdir(str(root/'documents'));os.symlink(str(root/'go'),str(root/'documents'))
    for index,(change,codes) in enumerate(((lambda root:os.chmod(str(root/'go'),0o750),('ROOT_NOT_PRIVATE',)),
                                           (lambda root:os.rmdir(str(root/'payload')),('FileNotFoundError',)),
                                           (link,('OSError','NotADirectoryError')),
                                           (lambda root:os.chmod(str(root),0o755),None))):
        base=tmp_path/('case-%d'%index);base.mkdir();root=private_tree(base);change(root)
        returncode,out,err,_=run_script(prelude(tree/'c3po'/'backend',abspath=root.parent)+K().m.scripts()['IDENT'])
        if codes is None:
            one_line('IDENT',returncode,out,err,'ROOT_IDENTITIES')        # AnchoredRoot checks the owner and mode of the leaf only
            continue
        row=one_line('IDENT',returncode,out,err,'ROOT_IDENTITIES_REFUSED');assert row['code'] in codes,row

def test_ident_script_without_the_application_prints_its_own_refusal():
    returncode,out,err,_=run_script(K().m.scripts()['IDENT'])
    row=one_line('IDENT',returncode,out,err,'ROOT_IDENTITIES_REFUSED');assert row['code']=='ModuleNotFoundError'

def test_the_source_and_the_model_compute_the_release_digest(tmp_path):
    tree=release();module=store(tree);m=K().m
    class Info:
        def __init__(self,device,inode):self.st_dev,self.st_ino=device,inode
    for root,child,name in (((66306,81150),(66306,81151),'documents'),((1,2),(3,4),'go'),((2**40,2**33),(7,2**31-1),'payload')):
        expected=module.digest([['c3po-capacity',root[0],root[1]],[name,child[0],child[1]]])
        assert m.root_identity(Info(*root),name,Info(*child))==expected==kprobe.digest([['c3po-capacity',root[0],root[1]],[name,child[0],child[1]]])
    for value in ([['c3po-capacity',1,2]],{'b':[1,'x'],'a':None},'é'):
        assert module.canonical(value)==m.canonical(value) and module.digest(value)==m.sha(m.canonical(value))
    # The emulated container's identity is the identity of the real script for the same numbers (tests/kprobe.identity_in).
    root=private_tree(tmp_path);top,child=os.stat(str(root)),os.stat(str(root/'go'))
    assert kprobe.digest([['c3po-capacity',top.st_dev,top.st_ino],['go',child.st_dev,child.st_ino]])==m.root_identity(top,'go',child)


# ---------------------------------------------------------------- LOAD
STUB_CONFIG='''class Settings:
    def __init__(self, **values):
        self.values = values
'''
STUB_BOOTSTRAP='''import json, os, sys
class ShadowIntegrityError(ValueError):
    pass
class Root:
    def __init__(self, name):
        self.identity = %(identity)r[name]
class Reader:
    def __init__(self, raw):
        self.raw = raw
    def read(self, name):
        assert name == 'week.static.capacity.json'
        return self.raw
class CapacityConfig:
    def __init__(self, settings):
        sys.stderr.write('SETTINGS ' + json.dumps(settings.values, sort_keys=True) + '\\n')
        mode = %(mode)r
        if mode == 'shadow':
            raise ShadowIntegrityError('CAPACITY_CONFIG_HASH')
        if mode == 'shadow_text':
            raise ShadowIntegrityError('the config is not what was signed')
        if mode == 'value':
            raise ValueError('CAPACITY_CONFIG_HASH')
        if mode == 'missing':
            raise FileNotFoundError(2, 'No such file')
        self.sha = settings.values['r2d2_v2_capacity_config_sha']
        self.name = 'week.static.capacity.json'
        self.config_root = Reader(%(config)r if mode != 'other_sha' else b'another config')
        self.veto_mode = settings.values['r2d2_v2_capacity_veto_mode'] if mode not in ('continuous', 'veto') else 'CONTINUOUS'
        names = ['documents', 'go', 'payload'] + (['restore_revocation'] if mode == 'continuous' else [])
        self.roots = {name: Root(name) for name in names}
        if mode == 'broken_roots':
            self.roots = {'documents': object()}
    def close(self):
        sys.stderr.write('CLOSED\\n')
'''
def stub(tmp_path,mode):
    directory=Path(str(tmp_path)).resolve()/('stub-'+mode)/'app';directory.mkdir(parents=True)
    identity={name:hashlib.sha256(name.encode()).hexdigest() for name in ('documents','go','payload','restore_revocation')}
    (directory/'__init__.py').write_text('');(directory/'config.py').write_text(STUB_CONFIG)
    (directory/'r2d2_v2_capacity_bootstrap.py').write_text(STUB_BOOTSTRAP%{'mode':mode,'identity':identity,'config':kprobe.CONFIG})
    return directory.parent,identity

@pytest.mark.parametrize('mode,status,check',[
    ('ok','CAPACITY_STARTUP_OK',None),('continuous','CAPACITY_STARTUP_OK','CAPACITY_ROOTS_NOT_THE_THREE'),
    ('other_sha','CAPACITY_STARTUP_OK','CAPACITY_CONFIG_SHA_NOT_EQUAL'),('veto','CAPACITY_STARTUP_OK','CAPACITY_VETO_MODE_NOT_AS_SIGNED'),
    ('shadow','CAPACITY_STARTUP_REFUSED','CAPACITY_CONFIG_HASH'),('shadow_text','CAPACITY_STARTUP_REFUSED','ShadowIntegrityError'),
    ('value','CAPACITY_STARTUP_REFUSED','ValueError'),('missing','CAPACITY_STARTUP_REFUSED','FileNotFoundError'),
    ('broken_roots','CAPACITY_STARTUP_REFUSED','AttributeError'),
])
def test_load_script_every_branch_with_a_stub_application(tmp_path,mode,status,check):
    m=K().m;directory,identity=stub(tmp_path,mode);plan=kprobe.fields('LOAD')
    returncode,out,err,_=run_script(prelude(directory)+m.stdin_of(plan))
    row=one_line('LOAD',returncode,out,err,status)
    settings=[line for line in err.decode().splitlines() if line.startswith('SETTINGS ')]
    assert json.loads(settings[0][9:])=={'r2d2_v2_capacity_required':True,'r2d2_v2_capacity_config_file':kprobe.CONFIG_PATH,
                                         'r2d2_v2_capacity_config_sha':kprobe.CONFIG_SHA,'r2d2_v2_capacity_veto_mode':'DISPATCH_AND_DERIVATION_ONLY',
                                         'r2d2_v2_shadow_release_sha':kprobe.RELEASE_SHA}
    if status=='CAPACITY_STARTUP_OK':
        assert 'CLOSED' in err.decode() and row['identities']=={name:identity[name] for name in row['roots']}
        host={name:identity[name] for name in ('config','documents','go','payload') if name in identity}
        assert m.expectation_code('LOAD',[{'line':row,'valid':True}],host,kprobe.CONFIG_SHA)==check
        if mode=='ok':assert out==kprobe.compact(row) and row==dict(row,status='CAPACITY_STARTUP_OK',veto_mode='DISPATCH_AND_DERIVATION_ONLY',config_sha256=kprobe.CONFIG_SHA)
    else:
        assert row['code']==check and ('CLOSED' in err.decode())==(mode=='broken_roots')

def test_load_script_with_the_release_settings_and_capacity_config_refuses_a_config_of_another_hash(tmp_path):
    """The release's own Settings (pydantic, populate_by_name) takes the five values by name, and CapacityConfig opens
    the config through AnchoredRoot and refuses it by its hash: the first refusal of the real startup checks."""
    tree=release();python=application_interpreter();m=K().m
    root=private_tree(tmp_path);config=root/'config'/'week.static.capacity.json';config.write_bytes(b'{}\n');os.chmod(str(config),0o600)
    values={'config_file':str(config),'config_sha256':kprobe.CONFIG_SHA,'release_sha':kprobe.RELEASE_SHA}
    stdin=prelude(tree/'c3po'/'backend')+m.scripts()['LOAD']+(m.LOAD_CALL%json.dumps(values,sort_keys=True,separators=(',',':'))).encode()
    returncode,out,err,_=run_script(stdin,python)
    row=one_line('LOAD',returncode,out,err,'CAPACITY_STARTUP_REFUSED');assert row['code']=='CAPACITY_CONFIG_HASH',(row,err[-800:])
    values['config_file']=str(root/'config'/'absent.json')
    stdin=prelude(tree/'c3po'/'backend')+m.scripts()['LOAD']+(m.LOAD_CALL%json.dumps(values,sort_keys=True,separators=(',',':'))).encode()
    row=one_line('LOAD',*run_script(stdin,python)[:3],'CAPACITY_STARTUP_REFUSED');assert row['code']=='FileNotFoundError'
    os.chmod(str(root/'config'),0o755);values['config_file']=str(config)
    stdin=prelude(tree/'c3po'/'backend')+m.scripts()['LOAD']+(m.LOAD_CALL%json.dumps(values,sort_keys=True,separators=(',',':'))).encode()
    row=one_line('LOAD',*run_script(stdin,python)[:3],'CAPACITY_STARTUP_REFUSED');assert row['code']=='ROOT_NOT_PRIVATE'

def test_load_script_without_the_application_prints_its_own_refusal():
    m=K().m;returncode,out,err,_=run_script(m.stdin_of(kprobe.fields('LOAD')))
    row=one_line('LOAD',returncode,out,err,'CAPACITY_STARTUP_REFUSED');assert row['code']=='ModuleNotFoundError'

@pytest.mark.parametrize('step',('IDENT','LOAD'))
def test_the_alarm_ends_a_script_that_hangs_before_the_limit_of_the_docker_cli(tmp_path,step):
    """An application whose import never returns: the alarm armed by the first statement ends the interpreter."""
    directory=Path(str(tmp_path)).resolve()/'hang'/'app';directory.mkdir(parents=True);(directory/'__init__.py').write_text('import time\ntime.sleep(120)\n')
    m=K().m;raw=m.stdin_of(kprobe.fields(step))
    returncode,out,err,seconds=run_script(prelude(directory.parent)+raw,timeout=60)
    assert returncode==-14 and out==b'' and m.SCRIPT_SECONDS[step]-0.5<=seconds<m.SCRIPT_SECONDS[step]+4,(returncode,seconds)

RECORDING=b'''import sys as _s, atexit as _a
class _Path(list):
    def insert(self, index, value):
        _s.stderr.write('PATH_INSERT %d %s\\n' % (index, value))
        list.insert(self, index, value)
_s.path = _Path(_s.path)
'''
@pytest.mark.parametrize('step',('CALENDAR','IDENT','LOAD'))
def test_every_script_puts_the_application_root_first_on_its_path_before_importing_it(step):
    """In the image the application is /app/app and python -I does not add the working directory: each script must
    insert /app at the head of sys.path itself (the recording prelude sees the insertion; nothing else is inserted)."""
    m=K().m;returncode,out,err,_=run_script(RECORDING+m.stdin_of(kprobe.fields(step)))
    inserts=[line for line in err.decode().splitlines() if line.startswith('PATH_INSERT ')]
    assert inserts==['PATH_INSERT 0 /app'],err[-600:]
    assert json.loads(out)['code']=='ModuleNotFoundError'
