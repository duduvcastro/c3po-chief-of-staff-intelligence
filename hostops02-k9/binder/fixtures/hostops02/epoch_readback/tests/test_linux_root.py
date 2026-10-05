"""The Linux job's shapes script of K11, run on the emulation: the script is coherent with the source it exercises.
Nothing here says anything about a real engine (linux_root/shapes_k11.py says what does)."""
import json
import os
from pathlib import Path
import subprocess
import sys

import k11

SCRIPT=k11.DIRECTORY/'linux_root'/'shapes_k11.py'
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','HOME':os.environ.get('HOME','')}

def test_shapes_self_test_runs_every_shape_and_meets_every_expectation_on_the_emulation():
    done=subprocess.run([sys.executable,'-B',str(SCRIPT),'--self-test'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=120)
    assert done.stderr==b'' and done.returncode==0,done.stdout.decode()[-2000:]+done.stderr.decode()[-2000:]
    result=json.loads(done.stdout);assert result['every_shape_ran'] and result['every_expectation_met'] and len(result['expectations'])==7 and len(result['shapes'])==6
    assert result['shapes']['pre_with_the_probe_of_the_bind']['probe']=={'valid':True,'code':None} and result['shapes']['pre_with_the_probe_of_the_bind']['verified'] is True
    assert result['shapes']['alarm_ends_a_hanging_interpreter']['returncode']==142 and result['shapes']['post_file_the_reader_refuses']['code']=='RELEASE_FILE_NOT_PRIVATE_OR_INVALID'

def test_shapes_refuse_to_run_anywhere_but_a_throwaway_runner(tmp_path):
    done=subprocess.run([sys.executable,'-B',str(SCRIPT),'sha256:'+'ab'*32,str(tmp_path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=60)
    assert done.returncode==1 and done.stdout.startswith(b'REFUSED') and list(Path(str(tmp_path)).iterdir())==[]
