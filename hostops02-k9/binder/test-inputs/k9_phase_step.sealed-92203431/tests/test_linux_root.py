"""The Linux job of K9W, as far as a workstation can check it: the shapes script is coherent with the source (its
collection runs on the emulated host and meets every expectation), the shell script parses, and both refuse to run
anywhere but on a throwaway runner. Nothing here proves anything about a real engine: the job was never run."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import k9w

ROOT=Path(k9w.DIRECTORY)/'linux_root'
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
ENV.update({name:value for name,value in os.environ.items() if name.startswith('HOSTOPS02_TEST_')})

def test_shapes_script_runs_on_the_emulated_host_and_every_expectation_is_met():
    if not (ROOT/'shapes.py').is_file():pytest.skip('the private copy of a mutation run carries no linux_root')
    done=subprocess.run([sys.executable,'-B',str(ROOT/'shapes.py'),'--self-test'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=120)
    assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    result=json.loads(done.stdout)
    assert result['schema']=='HOSTOPS02_K9_PHASE_STEP_LINUX_ROOT_SHAPES_V1' and result['all_shapes_ran'] is True and result['all_expectations_met'] is True
    assert len(result['shapes'])==3 and len(result['expectations'])==9 and b'never-emit' not in done.stdout and result['emulated'] is True

def test_shapes_script_and_job_refuse_to_run_outside_a_throwaway_runner():
    if not (ROOT/'shapes.py').is_file():pytest.skip('the private copy of a mutation run carries no linux_root')
    done=subprocess.run([sys.executable,'-B',str(ROOT/'shapes.py'),'sha256:'+'0'*64],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=60)
    assert done.returncode==1 and b'REFUSED' in done.stderr and done.stdout==b''
    done=subprocess.run(['/bin/sh','-n',str(ROOT/'run.sh')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=60)
    assert done.returncode==0 and done.stderr==b'','the shell script parses'
    done=subprocess.run(['/bin/sh',str(ROOT/'run.sh')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=60)
    assert done.returncode==1 and done.stderr.startswith(b'REFUSED: ') and b'sudo' not in done.stdout,'nothing is done and sudo is not called'
    text=(ROOT/'run.sh').read_text()
    assert text.index('refuse "a GitHub-hosted runner is required')<text.index('sudo -n true') and 'set -e\n' not in text
