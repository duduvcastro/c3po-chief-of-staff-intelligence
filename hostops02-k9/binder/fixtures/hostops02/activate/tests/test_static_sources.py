"""Static pins of what K6a took from outside itself: the release tree at dd4ec4bb (names of the settings, the epoch
constants, the deploy job's lock, marker and compose invocation, the worker's bind) and the activation payload that
ran on the host on 2026-09-28 (the four names, the compose words, the override shape). Both are read only when their
location is given (HOSTOPS02_TEST_RELEASE_REPOSITORY, a checkout that holds dd4ec4bb; HOSTOPS02_TEST_ACTIVATION_28,
the file worker-live-control.bound.py) and are skipped otherwise: they exist only on the build machine."""
import ast
import os
from pathlib import Path
import re
import subprocess

import pytest

import family as f
import k6a

REPOSITORY=os.environ.get('HOSTOPS02_TEST_RELEASE_REPOSITORY')
PRECEDENT=os.environ.get('HOSTOPS02_TEST_ACTIVATION_28')
REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'

def show(path):
    if not REPOSITORY:pytest.skip('HOSTOPS02_TEST_RELEASE_REPOSITORY is not set')
    done=subprocess.run(['git','-C',REPOSITORY,'show',REVISION+':'+path],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if done.returncode:pytest.skip('the checkout does not hold '+REVISION)
    return done.stdout.decode()

def test_static_the_four_names_are_the_settings_of_the_release():
    m=k6a.load().m;config=show('c3po/backend/app/config.py')
    assert 'env_prefix="C3PO_"' in config
    for key in m.ACTIVATION_KEYS:assert re.search(r'^    %s: '%key[len('C3PO_'):].lower(),config,re.M),key
    assert 'build_sha' in config and m.BUILD_KEY=='C3PO_BUILD_SHA'

def test_static_the_epoch_constants_are_the_compiled_ones():
    m=k6a.load().m;assembler=show('c3po/backend/app/r2d2_v2_epoch_assembler.py');controller=show('c3po/backend/app/r2d2_v2_live_controller.py')
    assert "EPOCH = '%s'"%m.EPOCH_NAME in assembler and "RUNTIME_ORDER_SHA = '%s'"%m.RUNTIME_ORDER_SHA256 in assembler
    assert 'ORDER_SHA = "%s"'%m.RUNTIME_ORDER_SHA256 in controller and '"%s"'%m.LIVE_POLICY_SCHEMA in controller
    assert 'path.with_name(path.name + "%s")'%m.STATUS_SUFFIX in controller and 'raise ShadowIntegrityError("LIVE_EPOCH_NOT_FOUND")' in controller
    assert 'not 1 <= policy["capacity"] <= 550' in controller and '(end-start).total_seconds() > 90 * 86400' in controller
    assert "FIRST_SESSION = '2026-10-05'" in assembler and "'2026-10-09')" in assembler
    assert 'info.st_size > %d'%m.MAX_RELEASE_BYTES in show('c3po/backend/app/r2d2_v2_shadow_worker.py')
    assert subprocess.run(['git','-C',REPOSITORY,'rev-parse',REVISION+'^{commit}'],stdout=subprocess.PIPE).stdout.decode().strip()==m.EPOCH_REVISION

def test_static_the_deploy_layout_is_the_one_of_the_pipeline():
    m=k6a.load().m;pipeline=show('.github/workflows/c3po-pipeline.yml')
    assert 'APP_DIR=/opt/chief-of-staff-digital' in pipeline and 'exec 9>>"$APP_DIR/%s/%s"'%(m.LOCK_RELATIVE_DIRECTORY,m.LOCK_FILE_NAME) in pipeline and 'flock -w 120 9' in pipeline
    assert 'if [ -e %s ]; then'%m.REBOOT_PENDING_PATH in pipeline
    assert 'C3PO_BUILD_SHA="$REVISION" docker compose --env-file %s -f c3po/%s up -d --no-build'%(m.ENV_FILE_NAME,m.COMPOSE_FILE_NAME) in pipeline
    assert "printf '%s\\n' \"$REVISION\" > "+m.DEPLOY_VERSION_NAME in pipeline
    compose=show('c3po/compose.yml');service=compose.split('\n  r2d2-worker:\n')[1].split('\n\n')[0]
    assert '- ${C3PO_DAY_D_DATA_MOUNT_SOURCE:-c3po_day_d_data}:/app/day-d-data' in service and 'C3PO_BUILD_SHA: ${C3PO_BUILD_SHA:-development}' in service
    assert 'image: c3po/backend:production' in service and 'restart: unless-stopped' in service and m.WORKER_SERVICE=='r2d2-worker'
    assert "ROOT / '%s'"%m.PIN_NAME in show('scripts/c3po_security_guard.py') or m.PIN_NAME in show('scripts/c3po_security_guard.py')

def test_static_the_command_words_are_the_ones_that_ran_on_2026_09_28():
    if not PRECEDENT or not Path(PRECEDENT).is_file():pytest.skip('HOSTOPS02_TEST_ACTIVATION_28 is not set')
    m=k6a.load().m;text=Path(PRECEDENT).read_text();tree=ast.parse(text)
    keys=[node.value for node in ast.walk(tree) if isinstance(node,ast.Assign) and getattr(node.targets[0],'id',None)=='KEYS'][0]
    assert tuple(ast.literal_eval(keys))==m.ACTIVATION_KEYS
    assert "base = ['docker', 'compose', '--project-name', 'c3po', '--env-file', str(ROOT / '.env'), '-f', str(ROOT / 'c3po/compose.yml')]" in text
    assert "run(base + ['-f', '-', 'config', '--format', 'json'], json.dumps(override))" in text and "cmd = base + ['-f', str(OVERRIDE)]" in text
    assert "run(cmd + ['up', '-d', '--no-deps', '--no-build', '--pull', 'never', '--force-recreate', 'r2d2-worker'])" in text
    assert m.COMMANDS['recreate']['tail']==['up','-d','--no-deps','--no-build','--pull','never','--force-recreate','r2d2-worker'] and m.COMPOSE_CONFIG_TAIL==['config','--format','json']
    assert "override = {'services': {'r2d2-worker': {'environment': {KEYS[0]: policy_container_path, KEYS[1]: expected, KEYS[2]: release_container_path, KEYS[3]: request['release_sha256']}}}}" in text
    assert "write_new(OVERRIDE, json.dumps(override).encode())" in text and 'PRIVATE.mkdir(mode=448)' in text and "os.open(POLICY, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 384)" in text
    # the override of this source has the same token shape (json.dumps with its default separators)
    docs,host=k6a.case();assert m.override_of(docs.plan)==k6a.override() and b'": "' in k6a.override() and b'", "' in k6a.override()

def test_static_the_policy_digest_is_the_assemblers_and_the_render_has_two_inputs():
    """What the repair of 2026-10-02 took from the release tree: the digest the assembler computes of a policy (Act B's
    policy_sha), and that the compose file names no other file than the environment file, so that the compose file and
    the environment file are all a render is made from."""
    m=k6a.load().m;assembler=show('c3po/backend/app/r2d2_v2_epoch_assembler.py')
    assert "return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()" in assembler
    assert 'return hashlib.sha256(canonical(value)).hexdigest()' in assembler
    import hashlib,json
    policy=k6a.policy_object(note='café')
    assert m.policy_digest(policy)==hashlib.sha256(json.dumps(policy,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    compose=show('c3po/compose.yml')
    assert not re.search(r'^\s*(include|extends)\s*:',compose,re.M),'no other compose file is pulled in'
    assert set(re.findall(r'env_file:\n\s+- (\S+)\n(?!\s+- )',compose))=={'../.env'},'the one environment file of every service is the deploy tree\'s'
    assert not re.search(r'^\s*(configs|secrets)\s*:',compose,re.M)

def test_static_the_production_worker_is_stopped_by_the_kill_as_the_linux_job_models_it():
    """python as PID 1, no SIGTERM handler, no init, no stop_grace_period: every stop waits the engine's whole timeout.
    The shapes of the Linux job stop their worker the same way (linux_root/shapes.py), and DESIGN.md section 5 builds
    its estimate of the recreate on it."""
    compose=show('c3po/compose.yml');service=compose.split('\n  r2d2-worker:\n')[1].split('\n\n')[0]
    assert 'command: ["python", "-m", "app.r2d2_worker"]' in service
    assert 'stop_grace_period' not in service and 'init:' not in service and 'stop_signal' not in service
    worker=show('c3po/backend/app/r2d2_worker.py');assert 'signal.signal' not in worker and 'SIGTERM' not in worker
    dockerfile=show('c3po/backend/Dockerfile');assert 'ENTRYPOINT' not in dockerfile and 'tini' not in dockerfile
    shapes=k6a.DIRECTORY/'linux_root'/'shapes.py'
    if shapes.is_file():
        text=shapes.read_text();block=text.split("COMPOSE='''",1)[1].split("'''",1)[0];worker_block=block.split('  r2d2-worker:\n')[1].split('\n  api:\n')[0]
        assert 'stop_grace_period' not in worker_block and 'init' not in worker_block and 'stop_grace_period' not in block.split('\n  probe:\n')[1]

def test_static_the_evidence_names_the_operation_of_the_epoch_readback_as_its_own_source_spells_it():
    """The coupling the repair accepted: if K11's operation name changes, this constant follows (and the payload hash)."""
    m=k6a.load().m;sibling=k6a.DIRECTORY.parent/'epoch_readback'/'op.py'
    if not sibling.is_file():pytest.skip('the epoch readback is not beside this operation')
    names=re.findall(r"^OPERATION='([A-Z0-9_]+)'$",sibling.read_text(),re.M)
    assert len(names)==1 and m.EVIDENCE_OPERATIONS==(names[0],)
