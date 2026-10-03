"""linux_root/token_shape.py against the emulated host: the script that will run the operation's own shapes on a real
filesystem as root is coherent with the source (every shape is made, every expectation is computed and met on the
emulation), an expectation is false when its shape is missing or differs, and the script refuses to run anywhere but on
a throwaway runner. Nothing here proves a real filesystem."""
import importlib.util
import json
import os
import subprocess
import sys

import pytest

import tok

SCRIPT=tok.DIRECTORY/'linux_root'/'token_shape.py'
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
def environment():
    return dict(ENV,**{name:value for name,value in os.environ.items() if name.startswith('HOSTOPS02_TEST_')})
def module():
    if not SCRIPT.is_file():pytest.skip('a private copy without linux_root/ (the mutation harness)')
    spec=importlib.util.spec_from_file_location('_hostops02_token_shape',SCRIPT);loaded=importlib.util.module_from_spec(spec);spec.loader.exec_module(loaded);return loaded

def test_shape_self_test_makes_every_shape_and_meets_every_expectation_on_the_emulation():
    module()
    done=subprocess.run([sys.executable,'-B',str(SCRIPT),'--self-test'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=environment(),timeout=120)
    assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    result=json.loads(done.stdout);assert result['schema']=='HOSTOPS02_TOKEN_FROM_ENV_LINUX_ROOT_SHAPE_V1' and result['all_runs_made'] and result['all_expectations_met']
    assert sorted(result['runs'])==['again','complete','full_filesystem','literal_fake_value','other_value_and_length','refusals_before_any_effect']
    assert len(result['expectations'])==7 and not tok.leaks(done.stdout) and tok.LITERAL.encode() not in done.stdout
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
