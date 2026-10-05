"""The W1 candidate's own test file, run with its synthetic `bound` fixture replaced by documents that bind_once.py
produced (prepare and sign, REHEARSAL mode, fake transport). Nothing else of that file is changed: every test that
takes the fixture then starts from the binder's request, authority, GO and dispatch configuration."""
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

import helpers as h

START = '@pytest.fixture\ndef bound(tmp_path):\n'
END = '    return root,request,authority,go,config,save_docs,pin,put\n'
REPLACEMENT = START + '    import w1_bound_adapter\n    return w1_bound_adapter.bound(tmp_path,sys.modules[__name__])\n'


def test_the_w1_candidates_own_suite_passes_on_documents_bound_by_the_binder(base, families):
    derived = h.copy_family(families['w1'], base / 'derived')
    path = derived / 'test_w1_preflight_once.py'
    sealed = path.read_text(encoding='utf-8')
    assert sealed.count(START) == 1 and sealed.count(END) == 1
    first, last = sealed.index(START), sealed.index(END) + len(END)
    changed = sealed[:first] + REPLACEMENT + sealed[last:]
    assert changed[:first] == sealed[:first] and changed[first + len(REPLACEMENT):] == sealed[last:]          # one block, nothing else
    path.write_text(changed, encoding='utf-8')
    counter = base / 'fixtures-built'
    environment = {'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': '%s:%s' % (h.BIND, h.HERE),
                   'BIND_TEST_W1_FAMILY': str(families['w1']), 'BIND_TEST_FIXTURE_COUNTER': str(counter), 'HOME': os.environ.get('HOME', '/'), 'BIND_TEST_REVIEWED_REFERENCE_ROOT':os.environ['BIND_TEST_REVIEWED_REFERENCE_ROOT']}
    done = subprocess.run([sys.executable, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--junitxml', str(base / 'junit.xml'), str(path)],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environment, cwd=str(derived), timeout=1200)
    tail = done.stdout.decode('utf-8', 'replace')[-3000:]
    assert done.returncode == 0, tail

    def figures(text):
        suite = re.search(r'<testsuite [^>]*>', text).group(0)
        return {key: int(re.search(key + r'="(\d+)"', suite).group(1)) for key in ('tests', 'failures', 'errors', 'skipped')}
    ours = figures((base / 'junit.xml').read_text(encoding='utf-8'))
    theirs = figures((families['w1'] / 'TESTS.xml').read_text(encoding='utf-8'))
    assert ours['failures'] == ours['errors'] == 0 and ours['tests'] == theirs['tests'] >= 517, (ours, theirs)
    # Portable offline proof omits exact archived private receipts and the unrelated checkout.
    # Every permitted omission is named; no broad skip-count relaxation.
    allowed = {
        'test_real_earlier_documents_are_refused_by_the_source_even_inside_their_own_window_as_uid_0['+name+']'
        for name in ('hostfacts01','postdeploy01_rev4','standalone')
    } | {
        'test_real_earlier_config_is_refused_by_the_dispatcher_before_any_claim['+name+']'
        for name in ('hostfacts01','postdeploy01_rev4','standalone')
    } | {'test_the_earlier_final_payload_and_the_earlier_dispatcher_cannot_carry_this_operation',
         'test_no_entry_name_of_the_private_receipt_is_in_a_fixture_or_in_this_file',
         'test_signed_constants_are_the_ones_of_the_repository_checkout'}
    skipped = {case.attrib['name'] for case in ET.parse(base/'junit.xml').iter('testcase') if case.find('skipped') is not None}
    assert skipped <= allowed, skipped - allowed
    assert ours['skipped'] == len(skipped)
    built = len(counter.read_bytes())
    assert built >= 200, built          # the substituted fixture really was the one the tests received
    print('candidate tests: %d, fixtures built by the binder: %d' % (ours['tests'], built))
