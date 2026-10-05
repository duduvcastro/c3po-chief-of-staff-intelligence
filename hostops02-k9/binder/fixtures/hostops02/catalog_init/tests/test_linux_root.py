"""linux_root/catalog_shape.py against the emulated engine: the script that will run K2a's own shape on a real engine is
coherent with the source (every run is made, every expectation is computed and met on the emulation), an expectation
is false when its run is missing or differs, and the script refuses to run anywhere but on a throwaway runner.
Nothing here proves a real engine."""
import importlib.util
import json
import os
import subprocess
import sys

import k2a

SCRIPT=k2a.DIRECTORY/'linux_root'/'catalog_shape.py'
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
def environment():
    return dict(ENV,**{name:value for name,value in os.environ.items() if name.startswith('HOSTOPS02_TEST_')})
def module():
    spec=importlib.util.spec_from_file_location('_hostops02_k2a_shape',SCRIPT);loaded=importlib.util.module_from_spec(spec);spec.loader.exec_module(loaded);return loaded

def test_shape_self_test_makes_every_run_and_meets_every_expectation_on_the_emulation():
    if not SCRIPT.is_file():
        import pytest;pytest.skip('a private copy without linux_root/ (the mutation harness)')
    done=subprocess.run([sys.executable,'-B',str(SCRIPT),'--self-test'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=environment(),timeout=120)
    assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    result=json.loads(done.stdout);assert result['schema']=='HOSTOPS02_K2A_LINUX_ROOT_SHAPE_V1' and result['all_runs_made'] and result['all_expectations_met']
    assert sorted(result['runs'])==['real','real_again_on_the_initialised_root','rehearsal'] and len(result['expectations'])==14
    assert result['runs']['rehearsal']['docker_config']['path']=='/var/lib/c3po-bar-rehearsal-ci.docker-cli' and result['runs']['real']['docker_config']['path']=='/etc/c3po-bar/docker-cli'
    assert sorted({name.split()[0] for name in result['expectations'] if name.startswith('K2A-')})==['K2A-U1','K2A-U2','K2A-U3','K2A-U5','K2A-U6']
    assert result['runs']['rehearsal']['outcome']=='REHEARSAL_CATALOG_READY_VERIFIED' and result['runs']['real']['outcome']=='CATALOG_READY_VERIFIED'

def test_shape_expectations_are_false_without_runs_and_for_a_run_that_differs():
    if not SCRIPT.is_file():
        import pytest;pytest.skip('a private copy without linux_root/ (the mutation harness)')
    shape=module();assert not any(shape.expectations({}).values()),'a run that was not made meets nothing'
    m,host,image,revision=shape.emulated();out=shape.collect(m,host,image,revision)
    assert all(shape.expectations(out).values())
    changed=json.loads(json.dumps(out));changed['real']['script_line']['inode']+=1
    assert shape.expectations(changed)['K2A-U3 the container saw the device and inode the host sees'] is False
    changed=json.loads(json.dumps(out));changed['rehearsal']['docker_config']['entries_after']=1
    assert shape.expectations(changed)['K2A-U2 the docker CLI wrote nothing into the configuration directory'] is False
    changed=json.loads(json.dumps(out));changed['real']['precheck']['docker_config_entries_after_the_reads']=1
    assert shape.expectations(changed)['K2A-U2 the docker CLI wrote nothing into the configuration directory'] is False
    changed=json.loads(json.dumps(out));changed['rehearsal']['docker_config'].update(path='/etc/c3po-bar/docker-cli',is_the_directory_of_the_unit=True)
    assert shape.expectations(changed)['the rehearsal gave docker a directory of its own and the real run the directory of the unit'] is False
    changed=json.loads(json.dumps(out));changed['rehearsal']['directories'].pop(0)
    assert shape.expectations(changed)['the rehearsal created its two directories durably and left the root that stands for the real one empty'] is False
    changed=json.loads(json.dumps(out));changed['real']['containers']['not_there_before']=1
    assert shape.expectations(changed)['K2A-U5 no container is listed after the run that was not there before'] is False
    changed=json.loads(json.dumps(out));changed['real_again_on_the_initialised_root']={'ok':True,'status':'METADATA_ONLY_REQUIRES_REVIEW','code':None,'run':{}}
    assert shape.expectations(changed)['a second run on the initialised root is refused before any container is started'] is False

def test_shape_refuses_to_run_outside_a_throwaway_runner():
    if not SCRIPT.is_file():
        import pytest;pytest.skip('a private copy without linux_root/ (the mutation harness)')
    if not (sys.platform.startswith('linux') and os.geteuid()==0 and os.environ.get('HOSTOPS_THROWAWAY_RUNNER')=='yes'):
        done=subprocess.run([sys.executable,'-B',str(SCRIPT),'sha256:'+'0'*64,'0'*40],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=environment(),timeout=120)
        assert done.returncode==1 and done.stdout==b'' and b'REFUSED' in done.stderr
