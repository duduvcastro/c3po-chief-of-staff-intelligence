"""The Linux job of K6a, as far as a workstation can check it: the shapes script is coherent with the source (its
collection runs on the emulated host and meets every expectation), the shell script parses, and both refuse to run
anywhere but on a throwaway runner. Nothing here proves anything about a real engine: the job was never run."""
import json
import os
from pathlib import Path
import subprocess
import sys

import k6a

ROOT=k6a.DIRECTORY/'linux_root'
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
ENV.update({name:value for name,value in os.environ.items() if name.startswith('HOSTOPS02_TEST_')})

def test_shapes_script_runs_on_the_emulated_host_and_every_expectation_is_met():
    if not (ROOT/'shapes.py').is_file():
        import pytest;pytest.skip('the private copy of a mutation run carries no linux_root')
    done=subprocess.run([sys.executable,'-B',str(ROOT/'shapes.py'),'--self-test'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=120)
    assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    result=json.loads(done.stdout)
    assert result['schema']=='HOSTOPS02_ACTIVATE_LINUX_ROOT_SHAPES_V1' and result['all_shapes_ran'] is True and result['all_expectations_met'] is True
    assert len(result['shapes'])==6 and len(result['expectations'])==19 and b'never-emit' not in done.stdout
    complete=result['shapes']['complete_run']['receipt']
    assert complete['recreate']['state']=='RECREATED_VERIFIED' and complete['mutating_calls']=={'issued':10,'succeeded':10,'failed_nothing_changed':0,'uncertain':0}
    left=result['shapes']['refused_while_a_container_carries_a_temporary_name_of_the_worker']
    assert (left['receipt']['code'],left['host_unchanged'],left['listed_before'])==('WORKER_SERVICE_LEFTOVER_CONTAINER',True,8) and result['shapes']['complete_run']['before']['other']==result['shapes']['complete_run']['after']['other']
    cut=result['shapes']['recreate_of_a_third_service_interrupted_inside_the_stop']
    assert cut['emulated'] is True and cut['order']=='NEW_FIRST' and cut['during_the_stop']==[['NAME','running',True],['TEMPORARY_NAME','created',False]],'no engine here: the rows are canned'

def test_the_order_of_an_interrupted_recreate_is_read_from_the_rows_of_the_service_and_no_id_leaves():
    """The two functions of the shapes script that turn `docker ps -a` rows into what the Linux job records."""
    if not (ROOT/'shapes.py').is_file():
        import pytest;pytest.skip('the private copy of a mutation run carries no linux_root')
    import importlib.util
    spec=importlib.util.spec_from_file_location('_k6a_shapes',ROOT/'shapes.py');shapes=importlib.util.module_from_spec(spec);spec.loader.exec_module(shapes)
    name='hostops02ci-probe-1';old,new='a'*64,'b'*64;temporary=old[:12]+'_'+name
    def rows(*items):return shapes.view(name,[old],list(items))
    assert rows((name,old,'running'),(temporary,new,'created'))==[['NAME','running',True],['TEMPORARY_NAME','created',False]]
    assert rows(('x'+name,new,'exited'))==[['OTHER_NAME','exited',False]] and 'a'*12 not in json.dumps(rows((temporary,old,'exited')))
    stopping=rows((name,old,'running'));stopped=rows((name,old,'exited'))
    assert shapes.order_of(rows((name,old,'running'),(temporary,new,'created')),rows((name,old,'exited'),(temporary,new,'created')))=='NEW_FIRST'
    assert shapes.order_of(stopping,stopped)=='OLD_FIRST' and shapes.order_of(rows((temporary,old,'exited')),rows((temporary,old,'exited'),(name,new,'created')))=='OLD_FIRST'
    assert shapes.order_of(rows((name,new,'running')),rows((name,new,'running')))=='UNDETERMINED','the recreate was over before the look: nothing is concluded'
    assert shapes.order_of([],[])=='UNDETERMINED' and shapes.order_of(stopping,rows((name,old,'exited'),(temporary,new,'created')))=='UNDETERMINED'

def test_shapes_script_and_job_refuse_to_run_outside_a_throwaway_runner():
    if not (ROOT/'shapes.py').is_file():
        import pytest;pytest.skip('the private copy of a mutation run carries no linux_root')
    done=subprocess.run([sys.executable,'-B',str(ROOT/'shapes.py'),'sha256:'+'0'*64,'/nonexistent','x','/nonexistent'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=60)
    assert done.returncode==1 and b'REFUSED' in done.stderr and done.stdout==b''
    done=subprocess.run(['/bin/sh','-n',str(ROOT/'run.sh')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=60)
    assert done.returncode==0 and done.stderr==b'','the shell script parses'
    done=subprocess.run(['/bin/sh',str(ROOT/'run.sh')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=60)
    assert done.returncode==1 and done.stderr.startswith(b'REFUSED: ') and b'sudo' not in done.stdout,'nothing is done and sudo is not called'
    text=(ROOT/'run.sh').read_text()
    assert text.index('refuse "a GitHub-hosted runner is required')<text.index('sudo -n true') and 'set -e' not in text.replace('"set -e"','')
