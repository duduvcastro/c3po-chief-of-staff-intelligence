"""linux_root/shapes.py against the emulated engine: the script that will run the core's command shapes on a real
engine is coherent with the sources (every shape runs, every expectation is computed and met on the emulation), and
it refuses to run anywhere but on a throwaway runner. Nothing here proves a real engine."""
import importlib.util
import json
import os
import subprocess
import sys

import family as f

SCRIPT=f.CORE/'linux_root'/'shapes.py'
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}

def test_shapes_self_test_runs_every_shape_and_meets_every_expectation_on_the_emulation():
    done=subprocess.run([sys.executable,'-B',str(SCRIPT),'--self-test'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=120)
    assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    result=json.loads(done.stdout);assert result['schema']=='HOSTOPS02_CORE_LINUX_ROOT_SHAPES_V1' and result['all_shapes_ran'] and result['all_expectations_met']
    assert len(result['shapes'])==7 and all(row['ok'] for row in result['shapes'].values()) and len(result['expectations'])==25
    assert sorted({name.split()[0] for name in result['expectations']})==['U2','U3','U4','U5','U6','U7']

def test_shapes_refuse_to_run_outside_a_throwaway_runner_and_expectations_are_false_without_shapes():
    spec=importlib.util.spec_from_file_location('_hostops02_shapes',SCRIPT);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert not all(module.expectations({}).values()) and not any(module.expectations({}).values()),'a shape that did not run meets nothing'
    if not (sys.platform.startswith('linux') and os.geteuid()==0 and os.environ.get('HOSTOPS_THROWAWAY_RUNNER')=='yes'):
        done=subprocess.run([sys.executable,'-B',str(SCRIPT),'sha256:'+'0'*64,'/nonexistent'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=120)
        assert done.returncode==1 and done.stdout==b'' and b'REFUSED' in done.stderr
