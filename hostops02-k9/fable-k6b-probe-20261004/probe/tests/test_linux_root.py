"""linux_root/ of the capacity probe offline: probe_shape.py against the emulated engine (every run made, every
expectation met, an expectation false when its run is missing or differs, a refusal anywhere but a throwaway runner),
and the text of run.sh. Nothing here proves a real engine."""
import importlib.util
import json
import os
import re
import subprocess
import sys

import pytest

import kprobe
import test_static_pins

LINUX=kprobe.DIRECTORY/'linux_root'
SCRIPT=LINUX/'probe_shape.py'
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
def environment():
    return dict(ENV,**{name:value for name,value in os.environ.items() if name.startswith('HOSTOPS02_TEST_')})
def present():
    if not SCRIPT.is_file():pytest.skip('a private copy without linux_root/ (the mutation harness)')
def module():
    spec=importlib.util.spec_from_file_location('_hostops02_capacity_probe_shape',SCRIPT);loaded=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded);return loaded

def test_shape_self_test_makes_every_run_and_meets_every_expectation_on_the_emulation():
    present()
    done=subprocess.run([sys.executable,'-B',str(SCRIPT),'--self-test'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=environment(),timeout=180)
    assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    result=json.loads(done.stdout);assert result['schema']=='HOSTOPS02_CAPACITY_PROBE_LINUX_ROOT_SHAPE_V1' and result['all_runs_made'] and result['all_expectations_met']
    assert sorted(result['runs'])==['CALENDAR','IDENT','LOAD'] and len(result['expectations'])==6

def test_shape_expectations_are_false_without_runs_and_for_a_run_that_differs():
    present();shape=module()
    assert not any(shape.expectations({}).values()),'a run that was not made meets nothing'
    out=shape.collect(shape.Emulated());assert all(shape.expectations(out).values())
    def changed(step,edit):
        copy=json.loads(json.dumps(out,default=str));edit(copy[step]);return shape.expectations(copy)
    keys=sorted(shape.expectations(out))
    calendar=[key for key in keys if key.startswith('CALENDAR')][0];ident=[key for key in keys if key.startswith('IDENT')][0]
    load=[key for key in keys if key.startswith('LOAD')][0];left='no step leaves a container';tree='the held tree is unchanged after IDENT and LOAD'
    seconds=[key for key in keys if key.startswith('every container')][0]
    assert changed('CALENDAR',lambda r:r.update(code='X'))[calendar] is False
    assert changed('CALENDAR',lambda r:r['lines'][0]['line'].update(package_sha='c'*64))[calendar] is False
    assert changed('IDENT',lambda r:r['comparison'].update(runs_agree=False))[ident] is False
    assert changed('IDENT',lambda r:r['comparison']['equal_to_the_host'].update(config=False))[ident] is False
    assert changed('LOAD',lambda r:r['lines'][0]['line'].update(code='CAPACITY_CONFIG_HASH'))[load] is False
    assert changed('LOAD',lambda r:r['precheck']['worker']['capacity_mount'].update(read_only=False))[load] is False
    assert changed('LOAD',lambda r:r['worker_after'].update(unchanged=False))[load] is False
    for step in ('CALENDAR','IDENT','LOAD'):
        assert changed(step,lambda r:r['containers_after'].update(names_present=True))[left] is False
        assert changed(step,lambda r:r['containers_after'].update(not_there_before=1))[left] is False
        assert changed(step,lambda r:r['containers'][0].update(seconds=35))[seconds] is False
        assert changed(step,lambda r:r.update(ok=False))[left] is False
    assert changed('IDENT',lambda r:r['tree_after'].update(unchanged=False))[tree] is False
    assert changed('IDENT',lambda r:r['containers'][1].update(seconds=14))[seconds] is False
    assert shape.report(dict(out,LOAD={'ok':False}))['all_runs_made'] is False

def test_shape_refuses_to_run_outside_a_throwaway_runner():
    present()
    if not (sys.platform.startswith('linux') and os.geteuid()==0 and os.environ.get('HOSTOPS_THROWAWAY_RUNNER')=='yes'):
        done=subprocess.run([sys.executable,'-B',str(SCRIPT),'sha256:'+'a'*64,'b'*64],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=environment(),timeout=120)
        assert done.returncode==1 and done.stdout==b'' and b'REFUSED' in done.stderr

def test_run_sh_is_valid_sh_guards_the_runner_and_removes_what_it_made():
    present();text=(LINUX/'run.sh').read_text()
    assert subprocess.run(['sh','-n',str(LINUX/'run.sh')]).returncode==0
    for needle in ('[ "${RUNNER_ENVIRONMENT:-}" = github-hosted ]','[ "${HOSTOPS_THROWAWAY_RUNNER:-}" = yes ]','sha256sum -c --quiet SHA256SUMS',
                   '../core/assemble.py --check .','trap cleanup EXIT','probe_shape.py "$IMAGE" "$CONFIG_SHA"','--mount "type=bind,source=$TREE,target=/c3po-capacity,readonly"',
                   'sudo -n mkdir -m 0700 "$TREE"','umask 077','-f "$RELEASE/c3po/backend/Dockerfile" "$RELEASE/c3po"','--label "org.opencontainers.image.revision=$REVISION"',
                   'MADE_TREE=yes','STARTED_WORKER=yes','BUILT=yes'):
        assert needle in text,needle
    pins=dict(reversed(line.split('  ',1)) for line in text.split("<<'PINS'")[1].split('\n',1)[1].split('PINS\n')[0].strip().splitlines())
    assert pins==test_static_pins.RELEASE_FILES
    assert text.index('MADE_TREE=yes')<text.index('probe_shape.py "$IMAGE"') and text.index('if [ "$MADE_TREE" = yes ]; then sudo -n rm -rf "$TREE"')<text.index('[ "$(uname -s)" = Linux ]')
    assert '{"schema":"R2D2_CAPACITY_BOOTSTRAP_V3","synthetic":"a static config of the tests, never authoritative"}' in text and kprobe.CONFIG.decode().strip() in text
    assert not re.search(r'(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])',text),'no address'
    assert 'set -e' not in text.split('\n# Nothing here relies')[0] and '--network none' in text

def test_run_sh_gives_the_stand_in_worker_the_settings_load_reads():
    present();text=(LINUX/'run.sh').read_text();shape=module()
    assert '-e "C3PO_R2D2_V2_SHADOW_RELEASE_SHA=$CI_RELEASE" -e "C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE=$TREE"' in text
    assert "printf '%s' 'hostops02 capacity probe ci release sha' | sha256sum" in text
    import hashlib;assert shape.CI_RELEASE_SHA==hashlib.sha256(b'hostops02 capacity probe ci release sha').hexdigest()
