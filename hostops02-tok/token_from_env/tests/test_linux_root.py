"""linux_root/token_shape.py against the emulated host: the script that will run the operation's own shapes on a real
filesystem as root is coherent with the source (every shape is made, every expectation is computed and met on the
emulation), an expectation is false when its shape is missing or differs, and the script refuses to run anywhere but on
a throwaway runner. Nothing here proves a real filesystem. Revision 3: linux_root/dump_proof.py, the same way: its
collector counts what it is given and finds the canary across blocks, its expectations hold only for the rows they
require, a file case is judged by every file that appears in cores/ (revision 3a), and it refuses to run anywhere but on a throwaway runner as root. Nothing here proves what a kernel dumps."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import tok

SCRIPT=tok.DIRECTORY/'linux_root'/'token_shape.py'
DUMPS=tok.DIRECTORY/'linux_root'/'dump_proof.py'
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
def environment():
    return dict(ENV,**{name:value for name,value in os.environ.items() if name.startswith('HOSTOPS02_TEST_')})
def module(path=SCRIPT,name='_hostops02_token_shape'):
    if not path.is_file():pytest.skip('a private copy without linux_root/ (the mutation harness)')
    spec=importlib.util.spec_from_file_location(name,path);loaded=importlib.util.module_from_spec(spec);spec.loader.exec_module(loaded);return loaded

def test_shape_self_test_makes_every_shape_and_meets_every_expectation_on_the_emulation():
    module()
    done=subprocess.run([sys.executable,'-B',str(SCRIPT),'--self-test'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=environment(),timeout=120)
    assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    result=json.loads(done.stdout);assert result['schema']=='HOSTOPS02_TOKEN_FROM_ENV_LINUX_ROOT_SHAPE_V1' and result['all_runs_made'] and result['all_expectations_met']
    assert sorted(result['runs'])==['again','complete','full_filesystem','literal_fake_value','other_value_and_length','refusals_before_any_effect']
    assert len(result['expectations'])==8 and not tok.leaks(done.stdout) and tok.LITERAL.encode() not in done.stdout
    assert (result['runs']['complete']['dumpable_before'],result['runs']['complete']['dumpable_after'])==(1,0)
    assert 'without_identity' not in done.stdout.decode()

def test_shape_expectations_are_false_without_shapes_and_for_a_shape_that_differs():
    shape=module();assert not any(shape.expectations({}).values()),'a shape that was not made meets nothing'
    out=shape.collect(shape.Emulated());assert all(shape.expectations(out).values())
    def changed(edit,name):
        copy=json.loads(json.dumps(out));edit(copy);assert shape.expectations(copy)[name] is False,name
    changed(lambda copy:copy['complete']['file'].update(mode_octal='0644'),'the token placed as real root: complete, root:root 0600, one link, size within 1-4096, the bytes written')
    changed(lambda copy:copy['literal_fake_value']['file'].update(bytes_equal_the_token_and_a_newline=False),'the token placed as real root: complete, root:root 0600, one link, size within 1-4096, the bytes written')
    changed(lambda copy:copy['complete'].update(access_time_kept=False),'the environment file read without moving its access time (the kernel O_NOATIME)')
    changed(lambda copy:copy['again']['file_after'].update(inode=1),'a second run refused before any effect, the file as it was')
    changed(lambda copy:copy['other_value_and_length']['receipt']['without_identity'].update(code='X'),'the receipt the same for a token of another value and length, the inode of the file aside')
    changed(lambda copy:copy['full_filesystem']['file'].update(exists=True),'a full filesystem at the write: the file of this run withdrawn by identity, nothing left')
    changed(lambda copy:copy['refusals_before_any_effect']['receipts']['quoted'].update(code='ENV_TOKEN_ABSENT'),
            'a link at the environment file, a world-writable deploy directory, the export form, a quoted value, the name elsewhere and a second link refused before any effect')
    changed(lambda copy:copy['refusals_before_any_effect']['receipts']['second_link'].update(code='ENV_FILE_OWNER_UNEXPECTED'),
            'a link at the environment file, a world-writable deploy directory, the export form, a quoted value, the name elsewhere and a second link refused before any effect')
    changed(lambda copy:copy['complete']['receipt'].update(leaks=['FaKe']),'no receipt holds four consecutive characters of a token, nor the literal fake value')
    changed(lambda copy:copy['literal_fake_value']['receipt'].update(literal_in_receipt=True),'no receipt holds four consecutive characters of a token, nor the literal fake value')
    dumpable='the process made non-dumpable by the run itself: the kernel held 1 before the first run and 0 after it, and every receipt says so'
    changed(lambda copy:copy['complete'].update(dumpable_after=1),dumpable)
    changed(lambda copy:copy['complete'].update(dumpable_before=0),dumpable)
    changed(lambda copy:copy['again']['receipt'].update(process={'dumpable_disabled':False}),dumpable)
    changed(lambda copy:copy['refusals_before_any_effect']['receipts']['link'].update(process=None),dumpable)

def test_the_compose_corpus_is_every_listed_file_and_500_generated_files_the_parser_accepts():
    shape=module();rows=shape.corpus();names=[name for name,_ in rows]
    assert len(names)==len(set(names))
    for name,raw in rows:assert (type(shape.ours(raw)[0]) is bytes)==(not name.startswith('refused_')),name
    generated=[name for name in names if name.startswith('generated_')];assert len(generated)==shape.GENERATED==500
    assert [name for name in names if not name.startswith(('generated_','refused_'))]==[name for name,_ in shape.envfiles.ACCEPTED_FILES]
    assert len([name for name in names if name.startswith('refused_')])==len(shape.envfiles.REFUSED_FILES)
    assert shape.ours(b'MASSIVE_API_TOKEN='+tok.TOKEN.encode()+b'\n')==(tok.TOKEN.encode(),['MASSIVE_API_TOKEN'])
    assert shape.ours(b'MASSIVE_API_TOKEN='+tok.TOKEN.encode()+b'\nC3PO_MASSIVE_API_TOKEN='+tok.TOKEN.encode())==(tok.TOKEN.encode(),['C3PO_MASSIVE_API_TOKEN','MASSIVE_API_TOKEN'])
    assert shape.ours(b'INHERITED\n')==('ENV_FILE_SYNTAX_UNSUPPORTED',None)

def test_the_judgement_of_what_compose_gave():
    """An accepted file agrees only when the backend's value is the parser's, each name the parser found is there with
    that value and no other one is, and no other name is one of the two for a reader that ignores case."""
    shape=module();T=tok.TOKEN;value=T.encode()
    def agrees(environment,names=('MASSIVE_API_TOKEN',)):return shape.judge(environment,value,list(names))['agrees']
    assert agrees({'MASSIVE_API_TOKEN':T,'OTHER':'x'})
    assert agrees({'MASSIVE_API_TOKEN':T,'C3PO_MASSIVE_API_TOKEN':T},('C3PO_MASSIVE_API_TOKEN','MASSIVE_API_TOKEN'))
    assert not agrees({'MASSIVE_API_TOKEN':T+'x'})                                     # another value
    assert not agrees({})                                                              # nothing for the backend
    assert not agrees({'MASSIVE_API_TOKEN':T,'C3PO_MASSIVE_API_TOKEN':'other'})        # the backend takes the prefixed name first
    assert not agrees({'MASSIVE_API_TOKEN':T,'C3PO_MASSIVE_API_TOKEN':T})              # a name the parser did not find
    assert not agrees({'MASSIVE_API_TOKEN':T},('C3PO_MASSIVE_API_TOKEN','MASSIVE_API_TOKEN'))
    assert not agrees({'MASSIVE_API_TOKEN':T,'massive_api_token':'other'})             # a name of another case
    assert not agrees({'MASSIVE_API_TOKEN':T,'MASSIVE_API_TOKEN':T})              # the Kelvin sign
    row=shape.judge({'MASSIVE_API_TOKEN':T,'Massive_Api_Token':T},value,['MASSIVE_API_TOKEN'])
    assert row['lookalike_names']==1 and row['backend']=='EQUAL_TO_THE_PARSER' and row['agrees'] is False
    assert shape.record({'MASSIVE_API_TOKEN':'x'})=={'names':{'C3PO_MASSIVE_API_TOKEN':'ABSENT','MASSIVE_API_TOKEN':'ANOTHER_VALUE'},'lookalike_names':0}

def test_shape_refuses_to_run_outside_a_throwaway_runner():
    module()
    if not (sys.platform.startswith('linux') and os.geteuid()==0 and os.environ.get('HOSTOPS_THROWAWAY_RUNNER')=='yes'):
        for arguments in (['1001'],['--compose-agreement']):
            done=subprocess.run([sys.executable,'-B',str(SCRIPT)]+arguments,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=environment(),timeout=120)
            assert done.returncode==1 and done.stdout==b'' and b'REFUSED' in done.stderr


# ---------------------------------------------------------------- linux_root/dump_proof.py (revision 3)
def dump_row(dumped,signal_number,mode):
    row={'ok':True,'signalled':True,'signal':signal_number,'expected_signal':signal_number,'core_dumped_flag':dumped,'child_pid_matches':True,
         'dumpable_before_the_signal':1 if dumped else 0,'core_limit_unlimited':True,'dump_received':dumped,'dump_bytes':12345678 if dumped else None,
         'canary_in_the_dump':True if dumped else None,'collector_signal':(signal_number if mode=='pipe' else None) if dumped else None}
    return row
def dump_result(shape):
    out={'patterns_set':{'pipe':True,'file':True},'restored':True,'before':'|/usr/share/apport/apport -p%p','after':'|/usr/share/apport/apport -p%p'}
    for mode in shape.MODES:
        for kind in ('dumpable','protected'):
            for name,number in (('SIGQUIT',3),('SIGSEGV',11)):out['%s %s %s'%(mode,kind,name)]=dump_row(kind=='dumpable',number,mode)
    return out

def test_dump_proof_expectations_hold_only_for_the_rows_they_require():
    shape=module(DUMPS,'_hostops02_dump_proof');assert not any(shape.expectations({}).values()),'a case that was not run meets nothing'
    out=dump_result(shape);assert all(shape.expectations(out).values()) and len(shape.expectations(out))==5
    result=shape.report(out);assert result['all_cases_ran'] and result['all_expectations_met'] and len(result['cases'])==8
    def changed(edit,start):
        copy=json.loads(json.dumps(out));edit(copy);checks=shape.expectations(copy)
        assert [name for name,ok in checks.items() if not ok]==[name for name in checks if name.startswith(start)],start
    changed(lambda copy:copy['pipe protected SIGQUIT'].update(dump_received=True),'pipe: the same child')
    changed(lambda copy:copy['pipe protected SIGSEGV'].update(core_dumped_flag=True),'pipe: the same child')
    changed(lambda copy:copy['pipe protected SIGSEGV'].update(dumpable_before_the_signal=1),'pipe: the same child')
    changed(lambda copy:copy['pipe protected SIGQUIT'].update(signalled=False,signal=None),'pipe: the same child')
    changed(lambda copy:copy['pipe dumpable SIGQUIT'].update(canary_in_the_dump=False),'pipe: a dumpable child')
    changed(lambda copy:copy['pipe dumpable SIGSEGV'].update(collector_signal=3),'pipe: a dumpable child')
    changed(lambda copy:copy['pipe dumpable SIGSEGV'].update(core_limit_unlimited=False),'pipe: a dumpable child')
    changed(lambda copy:copy['patterns_set'].update(pipe=False),'pipe: a dumpable child')
    changed(lambda copy:copy['file dumpable SIGQUIT'].update(dump_bytes=0),'file: a dumpable child')
    changed(lambda copy:copy['file protected SIGSEGV'].update(dump_received=True),'file: the same child')
    changed(lambda copy:copy['file protected SIGQUIT'].update(child_pid_matches=False),'file: the same child')
    changed(lambda copy:copy.update(restored=False),'kernel.core_pattern')
    del out['file protected SIGSEGV'];assert shape.report(out)['all_cases_ran'] is False

def test_dump_proof_collector_counts_the_bytes_and_finds_the_canary_across_blocks(tmp_path):
    shape=module(DUMPS,'_hostops02_dump_proof');directory=Path(str(tmp_path)).resolve()
    (directory/'collector.py').write_text(shape.COLLECTOR);canary=shape.canary()
    assert canary==b'FAKE-CORE-DUMP-CANARY-012345678901234567890123456789' and canary not in shape.CHILD.encode() and canary not in shape.COLLECTOR.encode()
    for pid,data,found in ((101,b'x'*((1<<20)-7)+canary+b'y'*9,True),(102,b'z'*3000000,False),(103,b'',False)):
        done=subprocess.run([sys.executable,'-I','-B',str(directory/'collector.py'),str(pid),'11'],input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=120)
        assert done.returncode==0 and done.stderr==b'' and done.stdout==b''
        assert json.loads((directory/('marker.%d.json'%pid)).read_bytes())=={'pid':pid,'signal':11,'bytes':len(data),'canary_found':found}
    core=directory/'core';core.write_bytes(b'a'*((1<<20)-3)+canary+b'b');assert shape.holds_canary(str(core)) is True
    core.write_bytes(b'a'*(3<<20));assert shape.holds_canary(str(core)) is False
    assert shape.SOURCE==str(tok.DIRECTORY/'build'/'token_from_env.py') and 'Native().not_dumpable()' in shape.CHILD and "'RLIMIT_CORE'" not in shape.CHILD
    assert 'resource.setrlimit(resource.RLIMIT_CORE,(resource.RLIM_INFINITY,resource.RLIM_INFINITY))' in shape.CHILD

def test_dump_proof_judges_a_file_case_by_every_new_file_of_cores_not_by_one_name(tmp_path):
    """A review of revision 3: with kernel.core_uses_pid 1 and no %p in the pattern, the kernel names the file
    core.<pid>.<pid>; the pattern says %p, and any file that appears in cores/ during a case counts."""
    shape=module(DUMPS,'_hostops02_dump_proof');cores=Path(str(tmp_path)).resolve()
    (cores/'core.101').write_bytes(b'a');before=set(os.listdir(str(cores)))
    assert shape.new_cores(str(cores),before)==[]
    (cores/'core.202.202').write_bytes(b'b');(cores/'anything').write_bytes(b'c')
    assert shape.new_cores(str(cores),before)==['anything','core.202.202']
    source=DUMPS.read_text();assert "'cores','core.%p')" in source and "'core.%P'" not in source and "'core.%d'%pid" not in source
    assert 'new_cores(cores,before)' in source and source.count('before=set(os.listdir(cores))')==1

def test_dump_proof_refuses_to_run_outside_a_throwaway_runner_as_root():
    module(DUMPS,'_hostops02_dump_proof')
    if not (sys.platform.startswith('linux') and os.geteuid()==0 and os.environ.get('HOSTOPS_THROWAWAY_RUNNER')=='yes'):
        done=subprocess.run([sys.executable,'-B',str(DUMPS)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=environment(),timeout=120)
        assert done.returncode==1 and done.stdout==b'' and b'REFUSED' in done.stderr
    done=subprocess.run([sys.executable,'-B',str(DUMPS),'anything'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=environment(),timeout=120)
    assert done.returncode==1 and b'usage' in done.stdout
