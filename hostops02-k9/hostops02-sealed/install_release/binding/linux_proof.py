"""Offline, for the binder of K10: is the Linux job the proof this directory needs before anything is bound?

  python3 -B binding/linux_proof.py <TESTS.install_release.linux-root.xml> <TESTS.install_release.linux-user.xml>

Why this exists. K10 has no dry mode and nothing of it has executed its mutating path on Linux, as real root, or on
the host: every real-system-call test of the workstation ran on macOS as an ordinary user reported as root, with a
marker bit standing for O_NOATIME. Without the Linux job the first execution of mkdirat, the exclusive creation,
linkat, unlinkat and fsync by descriptor in this composition would be the single shot of Monday. The job is the frozen
core's `sh linux_root/run.sh ../install_release` on a throwaway GitHub-hosted ubuntu-24.04 runner; it writes the two
junit files named above (this directory's suite as real root and as the runner's user).

This tool reads the two files and answers LINUX_PROOF_ACCEPTED only when ALL of this holds:
  - both are junit files of the whole suite of THIS seal: the number of test cases is the one VALIDATION.json records,
    with no failure and no error;
  - in the root file every test that makes the creating calls for real ran and passed (none skipped): REQUIRED below;
  - the recording test (tests/test_native.py) says of the root run: effective uid and gid 0, Linux, Python 3.12, the
    kernel's own O_NOATIME, an ext4 filesystem, a directory 0:0 0700 and a file 0:0 0600 with one link as the kernel
    made them, link and unlink by directory descriptor, five creating calls, and the payload and the SHA256SUMS of
    this directory as it is now;
  - the same test in the user file ran on Linux with the same payload and another uid.
Anything else: LINUX_PROOF_REFUSED with the checks that failed. Every skipped test of both files is listed.
One JSON object on standard output. Exit 0 accepted, 1 refused, 2 usage. Nothing is written, nothing is contacted.
It proves nothing about the host: the host's own evidence is the receipts CONTRACT section 5 names."""
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ElementTree

HERE=Path(__file__).resolve().parent
OPERATION=HERE.parent
RECORD='test_native_run_records_where_it_ran_for_the_linux_proof'
PREFIX='k10_'
# The tests of tests/test_native.py that make mkdir, the exclusive creation, write, fsync, link and unlink for real.
REQUIRED=('test_native_install_creates_the_directory_and_the_file_with_exactly_these_system_calls',
          'test_native_refusals_leave_the_real_tree_exactly_as_it_was',
          'test_native_never_replaces_a_name_that_appears_and_withdraws_only_its_own_temporary',
          'test_native_process_death_leaves_a_state_a_later_read_tells_apart_and_a_second_run_never_repairs',
          'test_native_noatime_is_required_and_fails_closed_where_the_platform_lacks_it',
          RECORD)
LIMIT=8*1024*1024

def sha(raw):return hashlib.sha256(raw).hexdigest()

def junit(path):
    """(facts of one junit file, None) or (None, code)."""
    try:raw=Path(path).read_bytes()
    except OSError:return None,'UNREADABLE'
    if not 0<len(raw)<=LIMIT:return None,'SIZE'
    try:root=ElementTree.fromstring(raw)
    except ElementTree.ParseError:return None,'NOT_XML'
    suites=[root] if root.tag=='testsuite' else root.findall('testsuite')
    if len(suites)!=1:return None,'NOT_ONE_TESTSUITE'
    suite=suites[0];cases={};skipped=[];bad=[]
    for case in suite.iter('testcase'):
        name=case.get('name') or '';plain=name.split('[',1)[0]
        state='skipped' if case.find('skipped') is not None else 'failed' if case.find('failure') is not None or case.find('error') is not None else 'passed'
        cases.setdefault(plain,[]).append(state)
        if state=='skipped':skipped.append('%s | %s'%(name,' '.join(str(case.find('skipped').get('message') or '').split())[:200]))
        if state=='failed':bad.append(name)
    try:counts={key:int(suite.get(key)) for key in ('tests','failures','errors','skipped')}
    except (TypeError,ValueError):return None,'COUNTS_INVALID'
    properties={}
    for case in suite.iter('testcase'):
        if case.get('name')==RECORD:
            for item in case.iter('property'):
                if (item.get('name') or '').startswith(PREFIX):properties[item.get('name')[len(PREFIX):]]=item.get('value')
    return {'sha256':sha(raw),'bytes':len(raw),'counts':counts,'cases':cases,'case_count':sum(len(states) for states in cases.values()),
            'skipped':sorted(skipped),'failed':sorted(bad),'record':properties},None

def judge(root,user,validation,payload_sha256,sums_sha256):
    """The checks, in order: (identifier, True or False)."""
    expected={suite.get('tests') for suite in validation.get('suites',[])} if type(validation) is dict else set()
    tests=expected.pop() if len(expected)==1 else None
    checks=[]
    def check(name,ok):checks.append((name,bool(ok)))
    check('VALIDATION_NAMES_ONE_TEST_COUNT',type(tests) is int and tests>0)
    for label,item in (('ROOT',root),('USER',user)):
        counts=item['counts']
        check(label+'_IS_THE_WHOLE_SUITE_OF_THIS_SEAL',counts['tests']==tests==item['case_count'])
        check(label+'_NO_FAILURE_NO_ERROR',counts['failures']==0 and counts['errors']==0 and not item['failed'])
        check(label+'_RECORD_PRESENT',item['cases'].get(RECORD)==['passed'] and bool(item['record']))
        check(label+'_RAN_ON_LINUX',str(item['record'].get('platform','')).startswith('linux'))
        check(label+'_PAYLOAD_IS_THE_SEALED_ONE',item['record'].get('payload_sha256')==payload_sha256)
        check(label+'_SHA256SUMS_IS_THIS_SEAL',sums_sha256 is not None and item['record'].get('sha256sums_sha256')==sums_sha256)
        check(label+'_RUN_COMPLETED_WITH_FIVE_CREATING_CALLS',item['record'].get('receipt_status')=='METADATA_ONLY_REQUIRES_REVIEW'
              and item['record'].get('mutating_calls_succeeded')=='5' and item['record'].get('linked_and_unlinked_by_dir_fd')=='True')
        check(label+'_KERNEL_NOATIME',item['record'].get('noatime_is_the_kernel_flag')=='True')
    record=root['record']
    check('ROOT_EVERY_CREATING_TEST_RAN',all(root['cases'].get(name) and set(root['cases'][name])=={'passed'} for name in REQUIRED))
    check('ROOT_EFFECTIVE_UID_AND_GID_0',(record.get('euid'),record.get('egid'))==('0','0'))
    check('ROOT_PYTHON_3_12',str(record.get('python','')).startswith('3.12.'))
    check('ROOT_FILESYSTEM_EXT4',record.get('filesystem_type')=='ext4')
    check('ROOT_CREATED_DIRECTORY_ROOT_ROOT_0700',record.get('created_directory')=='0:0:0700')
    check('ROOT_CREATED_FILE_ROOT_ROOT_0600_ONE_LINK',record.get('created_file')=='0:0:0600:1')
    check('USER_IS_NOT_ROOT',user['record'].get('euid') not in (None,'0'))
    check('TWO_DIFFERENT_FILES',root['sha256']!=user['sha256'])
    return checks

def main(arguments,validation=None,out=None):
    """validation and out exist for the tests of this tool; the command line never sets them."""
    out=sys.stdout if out is None else out
    if len(arguments)!=2 or any(item.startswith('-') for item in arguments):
        sys.stderr.write(__doc__);return 2
    if validation is None:
        try:validation=json.loads((OPERATION/'VALIDATION.json').read_bytes())
        except (OSError,ValueError):validation={}
    payload_sha256=sha((OPERATION/'build'/'install_release.py').read_bytes())
    sums=OPERATION/'SHA256SUMS';sums_sha256=sha(sums.read_bytes()) if sums.is_file() else None
    files={};problems=[]
    for label,path in zip(('root','user'),arguments):
        files[label],code=junit(path)
        if code is not None:problems.append('%s_FILE_%s'%(label.upper(),code))
    result={'schema':'HOSTOPS02_INSTALL_RELEASE_LINUX_PROOF_V1','payload_sha256':payload_sha256,'sha256sums_sha256':sums_sha256,
            'required_root_tests':list(REQUIRED),'host_evidence':False}
    if problems:
        result.update(decision='LINUX_PROOF_REFUSED',failed=problems)
    else:
        checks=judge(files['root'],files['user'],validation,payload_sha256,sums_sha256);failed=[name for name,ok in checks if not ok]
        result.update(decision='LINUX_PROOF_ACCEPTED' if not failed else 'LINUX_PROOF_REFUSED',failed=failed,checks=[name for name,_ in checks],
                      files={label:{key:item[key] for key in ('sha256','bytes','counts','skipped','failed','record')} for label,item in files.items()})
    out.write(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n')
    return 0 if result['decision']=='LINUX_PROOF_ACCEPTED' else 1

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
