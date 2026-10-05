"""The gate on the Linux job: binding/linux_proof.py. Nothing of K10 has run its mutating path on Linux, as real
root or on the host (review of 2026-10-02); the Linux job of the frozen core, with this directory as its argument, is
the only execution before the single shot, and nothing may be bound until this tool has accepted its two junit files.

What is tested: that the tool reads the junit file pytest really writes (one real pytest run of the recording test,
which here, on whatever machine this is, must be REFUSED as a proof), that a pair of files with every required fact
is accepted, and that each missing fact refuses by name. The accepted pair is written by hand in the shape of the
real file: it is a test input, never a proof, and it says so."""
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ElementTree

import pytest

import family as f
import k10

TOOL=k10.DIRECTORY/'binding'/'linux_proof.py'
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
TESTS=40
def tool():
    spec=importlib.util.spec_from_file_location('_k10_linux_proof',TOOL);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
SUMS=k10.DIRECTORY/'SHA256SUMS'
def sums():return f.sha(SUMS.read_bytes()) if SUMS.is_file() else None

def record(**changes):
    """The properties of the recording test as a run as real root on the Linux job would write them. NOT A PROOF."""
    out={'payload_sha256':f.sha(k10.K().source),'sha256sums_sha256':sums() or 'ABSENT','euid':0,'egid':0,'platform':'linux','python':'3.12.3',
         'noatime_is_the_kernel_flag':True,'filesystem_type':'ext4','created_directory':'0:0:0700','created_file':'0:0:0600:1',
         'receipt_status':'METADATA_ONLY_REQUIRES_REVIEW','mutating_calls_succeeded':5,'linked_and_unlinked_by_dir_fd':True}
    out.update(changes);return out
def junit(properties,*,tests=TESTS,skipped=(),failed=(),errors=(),missing=(),drop_record=False,label='root',declared=None):
    """A junit file in the shape pytest writes with junit_family=xunit2: one testsuite, one testcase per test."""
    module=tool();names=[]
    for name in module.REQUIRED:
        if name in missing:continue
        if name.startswith('test_native_process_death'):names+=[name+'[%s]'%point for point in ('after_mkdir','in_write','after_write','after_link','after_unlink')]
        else:names.append(name)
    names+=['test_synthetic_filler_%s_%03d'%(label,index) for index in range(tests-len(names))]
    suite=ElementTree.Element('testsuite',name='pytest',errors=str(len(errors)),failures=str(len(failed)),skipped=str(len(skipped)),tests=str(len(names) if declared is None else declared),time='1.0',
                              timestamp='2026-10-03T03:00:00',hostname='NOT_A_PROOF_SYNTHETIC_TEST_INPUT')
    for name in names:
        case=ElementTree.SubElement(suite,'testcase',classname='tests.test_native',name=name,time='0.01');plain=name.split('[')[0]
        if plain==module.RECORD and not drop_record:
            holder=ElementTree.SubElement(case,'properties')
            for key,value in sorted(properties.items()):ElementTree.SubElement(holder,'property',name=module.PREFIX+key,value=str(value))
        if plain in skipped or name in skipped:ElementTree.SubElement(case,'skipped',type='pytest.skip',message='skipped on purpose by the test')
        if plain in failed:ElementTree.SubElement(case,'failure',message='assert False')
        if plain in errors:ElementTree.SubElement(case,'error',message='RuntimeError')
    root=ElementTree.Element('testsuites');root.append(suite);return ElementTree.tostring(root,encoding='utf-8',xml_declaration=True)
def judged(tmp_path,root,user,validation=None):
    paths=[]
    for name,raw in (('TESTS.install_release.linux-root.xml',root),('TESTS.install_release.linux-user.xml',user)):
        path=Path(str(tmp_path))/name;path.write_bytes(raw);paths.append(str(path))
    out=io.StringIO();code=tool().main(paths,validation={'suites':[{'tests':TESTS},{'tests':TESTS}]} if validation is None else validation,out=out)
    return code,json.loads(out.getvalue())
USER=dict(euid=1001,egid=118,created_directory='1001:118:0700',created_file='1001:118:0600:1')
SEAL_CHECKS=[] if sums() else ['ROOT_SHA256SUMS_IS_THIS_SEAL','USER_SHA256SUMS_IS_THIS_SEAL']        # a directory that was never sealed can have no proof
def refused(tmp_path,names,root=None,user=None,validation=None):
    code,result=judged(tmp_path,junit(record()) if root is None else root,junit(record(**USER),label='user') if user is None else user,validation)
    assert code==1 and result['decision']=='LINUX_PROOF_REFUSED' and sorted(result['failed'])==sorted(set(list(names)+SEAL_CHECKS)),(names,result['failed'])
    return result

def test_required_tests_are_the_ones_of_this_suite_that_make_the_creating_calls_for_real():
    module=tool();source=(k10.HERE/'test_native.py').read_text()
    assert module.REQUIRED==('test_native_install_creates_the_directory_and_the_file_with_exactly_these_system_calls',
                             'test_native_refusals_leave_the_real_tree_exactly_as_it_was',
                             'test_native_never_replaces_a_name_that_appears_and_withdraws_only_its_own_temporary',
                             'test_native_process_death_leaves_a_state_a_later_read_tells_apart_and_a_second_run_never_repairs',
                             'test_native_noatime_is_required_and_fails_closed_where_the_platform_lacks_it',
                             'test_native_run_records_where_it_ran_for_the_linux_proof')
    assert all(source.count('\ndef %s('%name)==1 for name in module.REQUIRED) and module.RECORD==module.REQUIRED[-1]
    native=__import__('test_native');assert module.PREFIX==native.RECORD_PREFIX

def test_a_pair_with_every_required_fact_is_accepted_and_the_output_names_the_two_files_by_hash(tmp_path):
    root,user=junit(record()),junit(record(**USER),label='user');code,result=judged(tmp_path,root,user)
    if not sums():
        assert code==1 and sorted(result['failed'])==SEAL_CHECKS;return
    assert code==0 and result['decision']=='LINUX_PROOF_ACCEPTED' and result['failed']==[] and result['host_evidence'] is False,result['failed']
    assert result['schema']=='HOSTOPS02_INSTALL_RELEASE_LINUX_PROOF_V1' and result['payload_sha256']==f.sha(k10.K().source) and result['sha256sums_sha256']==sums()
    assert result['files']['root']['sha256']==f.sha(root) and result['files']['user']['sha256']==f.sha(user) and result['files']['root']['counts']['tests']==TESTS
    assert result['files']['root']['record']['euid']=='0' and result['files']['user']['record']['euid']=='1001' and len(result['checks'])==25
    # a skip outside the creating tests does not refuse, and is listed
    code,result=judged(tmp_path,junit(record(),skipped=('test_synthetic_filler_root_003',)),user)
    assert code==0 and result['files']['root']['skipped']==['test_synthetic_filler_root_003 | skipped on purpose by the test']

@pytest.mark.parametrize('change,name',[
    (dict(euid=1001),'ROOT_EFFECTIVE_UID_AND_GID_0'),(dict(egid=1001),'ROOT_EFFECTIVE_UID_AND_GID_0'),
    (dict(platform='darwin'),'ROOT_RAN_ON_LINUX'),(dict(python='3.9.6'),'ROOT_PYTHON_3_12'),(dict(python='3.13.1'),'ROOT_PYTHON_3_12'),
    (dict(noatime_is_the_kernel_flag=False),'ROOT_KERNEL_NOATIME'),(dict(filesystem_type='overlay'),'ROOT_FILESYSTEM_EXT4'),(dict(filesystem_type='UNKNOWN'),'ROOT_FILESYSTEM_EXT4'),
    (dict(created_directory='0:1000:0700'),'ROOT_CREATED_DIRECTORY_ROOT_ROOT_0700'),(dict(created_directory='0:0:0755'),'ROOT_CREATED_DIRECTORY_ROOT_ROOT_0700'),
    (dict(created_file='0:0:0600:2'),'ROOT_CREATED_FILE_ROOT_ROOT_0600_ONE_LINK'),(dict(created_file='0:0:0644:1'),'ROOT_CREATED_FILE_ROOT_ROOT_0600_ONE_LINK'),
    (dict(created_file='1000:0:0600:1'),'ROOT_CREATED_FILE_ROOT_ROOT_0600_ONE_LINK'),
    (dict(payload_sha256='a'*64),'ROOT_PAYLOAD_IS_THE_SEALED_ONE'),(dict(sha256sums_sha256='a'*64),'ROOT_SHA256SUMS_IS_THIS_SEAL'),(dict(sha256sums_sha256='ABSENT'),'ROOT_SHA256SUMS_IS_THIS_SEAL'),
    (dict(mutating_calls_succeeded=4),'ROOT_RUN_COMPLETED_WITH_FIVE_CREATING_CALLS'),(dict(receipt_status='REFUSED'),'ROOT_RUN_COMPLETED_WITH_FIVE_CREATING_CALLS'),
    (dict(linked_and_unlinked_by_dir_fd=False),'ROOT_RUN_COMPLETED_WITH_FIVE_CREATING_CALLS')])
def test_each_fact_of_the_root_run_is_required(tmp_path,change,name):
    refused(tmp_path,[name],root=junit(record(**change)))

def test_whole_suite_no_failure_every_creating_test_and_the_user_run_are_required(tmp_path):
    module=tool();count=[0]
    def directory():
        count[0]+=1;path=tmp_path/str(count[0]);path.mkdir();return path
    for name in module.REQUIRED:
        expected=['ROOT_EVERY_CREATING_TEST_RAN']+(['ROOT_RECORD_PRESENT'] if name==module.RECORD else [])
        refused(directory(),expected,root=junit(record(),skipped=(name,)))
        gone=junit(record(),missing=(name,))
        if name==module.RECORD:
            refused(directory(),['ROOT_EVERY_CREATING_TEST_RAN','ROOT_RECORD_PRESENT','ROOT_RAN_ON_LINUX','ROOT_PAYLOAD_IS_THE_SEALED_ONE','ROOT_SHA256SUMS_IS_THIS_SEAL',
                                 'ROOT_RUN_COMPLETED_WITH_FIVE_CREATING_CALLS','ROOT_KERNEL_NOATIME','ROOT_EFFECTIVE_UID_AND_GID_0','ROOT_PYTHON_3_12','ROOT_FILESYSTEM_EXT4',
                                 'ROOT_CREATED_DIRECTORY_ROOT_ROOT_0700','ROOT_CREATED_FILE_ROOT_ROOT_0600_ONE_LINK'],root=gone)
        else:refused(directory(),['ROOT_EVERY_CREATING_TEST_RAN'],root=gone)
    # one parameter of the process-death test skipped is enough to refuse
    refused(directory(),['ROOT_EVERY_CREATING_TEST_RAN'],root=junit(record(),skipped=('test_native_process_death_leaves_a_state_a_later_read_tells_apart_and_a_second_run_never_repairs[after_link]',)))
    refused(directory(),['ROOT_NO_FAILURE_NO_ERROR'],root=junit(record(),failed=('test_synthetic_filler_root_001',)))
    refused(directory(),['ROOT_NO_FAILURE_NO_ERROR','ROOT_EVERY_CREATING_TEST_RAN'],root=junit(record(),errors=(module.REQUIRED[0],)))
    refused(directory(),['USER_NO_FAILURE_NO_ERROR'],user=junit(record(**USER),label='user',failed=('test_synthetic_filler_user_001',)))
    # a subset of the suite, or another number of tests than the seal records, is not the suite of this seal
    refused(directory(),['ROOT_IS_THE_WHOLE_SUITE_OF_THIS_SEAL'],root=junit(record(),tests=TESTS-1))
    refused(directory(),['ROOT_IS_THE_WHOLE_SUITE_OF_THIS_SEAL'],root=junit(record(),tests=TESTS-1,declared=TESTS))       # the count the file declares is not trusted
    refused(directory(),['ROOT_IS_THE_WHOLE_SUITE_OF_THIS_SEAL'],root=junit(record(),tests=TESTS,declared=TESTS+1))
    refused(directory(),['USER_IS_THE_WHOLE_SUITE_OF_THIS_SEAL'],user=junit(record(**USER),label='user',tests=TESTS+1))
    for validation in ({'suites':[{'tests':TESTS},{'tests':TESTS+1}]},{'suites':[]},{},{'suites':[{'tests':0}]}):
        names=['VALIDATION_NAMES_ONE_TEST_COUNT','ROOT_IS_THE_WHOLE_SUITE_OF_THIS_SEAL','USER_IS_THE_WHOLE_SUITE_OF_THIS_SEAL']
        refused(directory(),names,validation=validation)
    # the user run: on Linux, the same payload, another uid; and it is another file than the root run
    refused(directory(),['USER_IS_NOT_ROOT'],user=junit(record(),label='user'))
    refused(directory(),['USER_RAN_ON_LINUX'],user=junit(record(platform='darwin',**USER),label='user'))
    refused(directory(),['USER_PAYLOAD_IS_THE_SEALED_ONE'],user=junit(record(payload_sha256='b'*64,**USER),label='user'))
    refused(directory(),['USER_RECORD_PRESENT','USER_RAN_ON_LINUX','USER_PAYLOAD_IS_THE_SEALED_ONE','USER_SHA256SUMS_IS_THIS_SEAL','USER_RUN_COMPLETED_WITH_FIVE_CREATING_CALLS',
                         'USER_KERNEL_NOATIME','USER_IS_NOT_ROOT'],user=junit(record(**USER),label='user',drop_record=True))
    same=junit(record());refused(directory(),['USER_IS_NOT_ROOT','TWO_DIFFERENT_FILES'],root=same,user=same)

def test_files_that_are_not_junit_and_a_wrong_call(tmp_path):
    module=tool();good=junit(record())
    for raw,code in ((b'NOT_RUN: pytest wrote no junit file as root\n','ROOT_FILE_NOT_XML'),(b'','ROOT_FILE_SIZE'),(b'<testsuites></testsuites>','ROOT_FILE_NOT_ONE_TESTSUITE'),
                     (b'<testsuites><testsuite tests="x" failures="0" errors="0" skipped="0"/></testsuites>','ROOT_FILE_COUNTS_INVALID')):
        code_,result=judged(tmp_path,raw,good);assert code_==1 and result['decision']=='LINUX_PROOF_REFUSED' and result['failed']==[code] and 'files' not in result
    out=io.StringIO();assert module.main([str(tmp_path/'absent.xml'),str(tmp_path/'absent2.xml')],validation={},out=out)==1
    assert json.loads(out.getvalue())['failed']==['ROOT_FILE_UNREADABLE','USER_FILE_UNREADABLE']
    for arguments in ([],['one.xml'],['a','b','c'],['--force','b']):
        out=io.StringIO();assert module.main(arguments,out=out)==2 and out.getvalue()==''

def test_the_file_pytest_really_writes_is_read_and_a_run_on_this_machine_alone_is_never_a_proof(tmp_path):
    """One real pytest run of the recording test with the options of the Linux job: the tool finds the test case and
    its properties in pytest's own file. It is a single test, given twice: refused, wherever this suite runs."""
    report=tmp_path/'TESTS.real.xml'
    done=subprocess.run([sys.executable,'-B','-m','pytest','-p','no:cacheprovider','-q','--basetemp',str(tmp_path/'base'),'-k','test_native_run_records_where_it_ran_for_the_linux_proof',
                         '--junitxml',str(report),'-o','junit_family=xunit2',str(k10.HERE/'test_native.py')],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                        env=dict(ENV,HOME=os.environ.get('HOME','')),cwd=str(k10.DIRECTORY),timeout=300)
    assert done.returncode==0 and report.is_file(),done.stdout.decode()[-2000:]
    out=io.StringIO();code=tool().main([str(report),str(report)],validation={'suites':[{'tests':1}]},out=out);result=json.loads(out.getvalue())
    assert code==1 and result['decision']=='LINUX_PROOF_REFUSED' and {'ROOT_EVERY_CREATING_TEST_RAN','TWO_DIFFERENT_FILES'}<=set(result['failed'])
    found=result['files']['root'];assert found['counts']=={'tests':1,'failures':0,'errors':0,'skipped':0} and found['sha256']==f.sha(report.read_bytes())
    assert sorted(found['record'])==sorted(record()) and found['record']['payload_sha256']==f.sha(k10.K().source) and found['record']['receipt_status']=='METADATA_ONLY_REQUIRES_REVIEW'
    assert found['record']['python']=='%d.%d.%d'%sys.version_info[:3] and found['record']['platform']==sys.platform and 'ROOT_RECORD_PRESENT' not in result['failed']
    # the command line, as the binder runs it
    done=subprocess.run([sys.executable,'-B',str(TOOL),str(report),str(report)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=60)
    assert done.returncode==1 and done.stderr==b'' and json.loads(done.stdout)['decision']=='LINUX_PROOF_REFUSED'
    done=subprocess.run([sys.executable,'-B',str(TOOL)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=60)
    assert done.returncode==2 and done.stdout==b'' and b'linux_proof.py' in done.stderr
