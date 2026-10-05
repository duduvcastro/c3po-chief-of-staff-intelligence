"""K6b against the bytes it follows: the release tree at dd4ec4bb (compose.yml, config.py, the capacity-mount README and
its render checker) and the sealed activation K6a (operation name, the four names, the compose rows, the override
bytes). Each test is skipped when its location is absent; the locations are named by HOSTOPS02_TEST_RELEASE_TREE
and HOSTOPS02_TEST_K6A_DIRECTORY, with the workstation's defaults. Named "static": they pin bytes, so the mutation
harness deselects them."""
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

import pytest

import family as f
import k6b

M=k6b.load().m
RELEASE=Path(os.environ.get('HOSTOPS02_TEST_RELEASE_TREE') or '/nonexistent-release-tree')      # a checkout of dd4ec4bb; skipped without one
K6A=Path(os.environ.get('HOSTOPS02_TEST_K6A_DIRECTORY',str(Path(__file__).resolve().parents[3]/'hostops02-sealed'/'activate')))
need_release=pytest.mark.skipif(not (RELEASE/'c3po'/'compose.yml').is_file(),reason='no release tree at dd4ec4bb')
need_k6a=pytest.mark.skipif(not (K6A/'build'/'activate.py').is_file(),reason='no sealed K6a beside')

@need_release
def test_static_compose_file_of_the_release():
    text=(RELEASE/'c3po'/'compose.yml').read_text()
    worker=text[text.index('\n  r2d2-worker:\n'):text.index('\n  r2d2-shadow-candidate-worker:\n') if '\n  r2d2-shadow-candidate-worker:\n' in text else None]
    assert '      - ${C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE:-c3po_capacity_unprovisioned}:/c3po-capacity:ro\n' in worker
    assert '    env_file:\n      - ../.env\n' in worker and '      - ${C3PO_DAY_D_DATA_MOUNT_SOURCE:-c3po_day_d_data}:/app/day-d-data\n' in worker
    assert '      - ../runtime/security/maintenance:/run/c3po-maintenance:ro\n' in worker
    assert '\n  c3po_capacity_unprovisioned:\n' in text[text.index('\nvolumes:\n'):]
    assert text.count('C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE')==1 and 'C3PO_R2D2_V2_CAPACITY_REQUIRED' not in text   # the settings come from .env only
    assert not re.search(r'^\s*(include|extends):',text,re.M)

@need_release
def test_static_settings_of_the_release():
    text=(RELEASE/'c3po'/'backend'/'app'/'config.py').read_text()
    assert 'env_prefix="C3PO_"' in text
    for key in M.CAPACITY_KEYS[1:]+(M.ACTIVATION_KEYS[3],):
        assert re.search(r'^\s+%s:'%key[len('C3PO_'):].lower(),text,re.M),key
    readme=(RELEASE/'c3po'/'deployment'/'capacity-mount'/'README.md').read_text()
    for line in ('C3PO_R2D2_V2_CAPACITY_REQUIRED=true','C3PO_R2D2_V2_CAPACITY_VETO_MODE=DISPATCH_AND_DERIVATION_ONLY'):assert line in readme
    assert "sed -i '/^C3PO_R2D2_V2_CAPACITY_REQUIRED=/d' .env" in readme and "sed -i '/^C3PO_R2D2_V2_CAPACITY_/d' .env" in readme
    assert M.VETO_MODE_VALUE=='DISPATCH_AND_DERIVATION_ONLY' and M.REQUIRED_VALUE=='true'

def checker():
    spec=importlib.util.spec_from_file_location('check_compose_render',str(RELEASE/'c3po'/'deployment'/'capacity-mount'/'check_compose_render.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

@need_release
def test_static_render_rule_is_the_checker_of_the_release():
    c=checker()
    assert (c.SERVICE,c.TARGET,c.PLACEHOLDER,c.PROJECT)==(M.WORKER_SERVICE,M.CAPACITY_TARGET,M.PLACEHOLDER_VOLUME,'c3po')
    assert sorted(c.WORKER_TARGETS)==sorted(M.WORKER_TARGETS)
    # the same verdict on renders of every state and on each way a render can be wrong
    renders=[]
    for mode,state in (('MOUNT',0),('ENABLE',1),('DISABLE_FAST',5),('DISABLE_FULL',4)):
        m,docs,host=k6b.fresh(mode,state=state)
        code,value=host.docker.compose.render([k6b.hostemu.COMPOSE_FILE,k6b.OVERRIDE_FILE],None,{})
        renders.append((docs.plan,value,1 if state else 0))
    import copy
    cases=[]
    for plan,value,count in renders:
        cases.append((plan,value,count))
        for change in (lambda v:[i.update(read_only=False) for i in v['services']['r2d2-worker']['volumes'] if i['target']=='/c3po-capacity'],
                       lambda v:v.update(name='other'),lambda v:v.setdefault('volumes',{}).update(c3po_capacity_unprovisioned={'name':'x'}),
                       lambda v:v['services']['api'].update(volumes=[{'type':'volume','source':'x','target':'/c3po-capacity'}]),
                       lambda v:v['services']['r2d2-worker']['volumes'].append({'type':'bind','source':'/x','target':'/y'}),
                       lambda v:[i.update(source='/var/lib/x') for i in v['services']['r2d2-worker']['volumes'] if i['target']=='/c3po-capacity'],
                       lambda v:v.pop('volumes',None)):
            other=copy.deepcopy(value);change(other);cases.append((plan,other,count))
    for plan,value,count in cases:
        expect='bind='+k6b.CAPACITY if count else 'placeholder'
        assert (c.check(value,expect)==[])==(M.render_errors(value,plan,count)==[]),(expect,c.check(value,expect),M.render_errors(value,plan,count))

def k6a_module():
    import family as fam
    return fam.load(K6A).m

@need_k6a
def test_static_the_activation_s_bytes():
    a=k6a_module()
    assert M.EVIDENCE_OPERATIONS==(a.OPERATION,) and M.ACTIVATION_KEYS==a.ACTIVATION_KEYS and M.EPOCH_REVISION==a.EPOCH_REVISION
    assert M.EPOCH_NAME==a.EPOCH_NAME and M.WORKER_SERVICE==a.WORKER_SERVICE and M.BUILD_KEY==a.BUILD_KEY
    assert (M.ENV_FILE_NAME,M.COMPOSE_FILE_NAME,M.DEPLOY_VERSION_NAME,M.LOCK_RELATIVE_DIRECTORY,M.LOCK_FILE_NAME,M.REBOOT_PENDING_PATH)==\
           (a.ENV_FILE_NAME,a.COMPOSE_FILE_NAME,a.DEPLOY_VERSION_NAME,a.LOCK_RELATIVE_DIRECTORY,a.LOCK_FILE_NAME,a.REBOOT_PENDING_PATH)
    # the same compose rows: the recreate word for word, the render from the files
    assert M.COMMANDS['recreate']==a.COMMANDS['recreate'] and M.COMMANDS['render_files']==a.COMMANDS['render_files']
    assert M.COMMANDS['render_files']['tail']==a.COMMANDS['render_files']['tail'] and M.COMMANDS['render_files']['class']==a.COMMANDS['render_files']['class']
    for name in ('image','container','container_list','container_environment'):assert M.COMMANDS[name]==a.COMMANDS[name]
    assert (M.SETTLE_SECONDS,M.SECOND_CHECK_RESERVE_SECONDS,M.UNDER_LOCK_ALLOWANCE_SECONDS,M.RENDER_ALLOWANCE_FLOOR_SECONDS)==\
           (a.SETTLE_SECONDS,a.SECOND_CHECK_RESERVE_SECONDS,a.UNDER_LOCK_ALLOWANCE_SECONDS,a.RENDER_ALLOWANCE_FLOOR_SECONDS)

@need_k6a
def test_static_the_override_is_the_one_the_activation_writes():
    sys.path.insert(0,str(K6A/'tests'))
    try:
        import k6a
        m,docs,host=k6a.fresh();values=m.environment_of(docs.plan);raw=m.override_of(docs.plan)
    finally:sys.path.remove(str(K6A/'tests'))
    plan={'override':{'environment':values}}
    assert M.override_bytes(plan)==raw and json.loads(raw)=={'services':{'r2d2-worker':{'environment':values}}}
    # the file list: the deploy's compose file, then the override in the live directory K6a created
    effects=m.effects_of(docs.plan)
    assert effects['recreate']['files'][-1]==[item for item in effects['files'] if item['key']=='OVERRIDE'][0]['path']

def test_static_editor_prefix_and_classes():
    assert M.COMMANDS['edit_env']['argv']==M.ENV_EDITOR_PREFIX and M.COMMANDS['edit_env']['class']=='QUICK' and M.COMMANDS['edit_env']['kind']=='EFFECT'
    assert M.ENV_EDITOR_PREFIX==M.RUN_PREFIX[:7]+['1000:1000']+M.RUN_PREFIX[8:]                 # the core's run prefix, the user alone changed
    assert M.COMMANDS['container_mounts']['argv']==['container','inspect','--format','{{json .Mounts}}']
    assert M.ENV_EDIT_SCRIPT_SHA256==f.sha(M.ENV_EDIT_SCRIPT.encode())
