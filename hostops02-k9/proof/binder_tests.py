"""Offline binder CI step helpers. No binder source, acceptance or frozen test is modified."""
import hashlib
import json
import os
import re
import stat
from collections import Counter
import xml.etree.ElementTree as ET

CANDIDATE_SEAL = '26fa5bf47caf63f7298ab9a6bfa2652d108636fb5ec8be546776eb0f616677a5'
BINDER_SOURCE = 'bb255f8693d2213e5fad33c440bc4a6802f8122310c5384b192922f58fa49fc5'
CONFIG_SHA256 = '91619929a513074f2eee01a6bcd78342305e0066e61ac79f2afd087c2e035897'
PROBE = """import importlib.metadata,json,os,platform,sys
import pytest,exchange_calendars
print(json.dumps({'version':platform.python_version(),'implementation':platform.python_implementation(),
 'uid':os.getuid(),'euid':os.geteuid(),'executable':sys.executable,
 'dependencies':{name:importlib.metadata.version(name) for name in ('pytest','exchange_calendars')},
 'installed':dict(sorted((d.metadata['Name'],d.version) for d in importlib.metadata.distributions()))},sort_keys=True))
"""
VERSION_PROBE = "import json,os,sys; print(json.dumps({'version':list(sys.version_info[:2]),'uid':os.getuid(),'euid':os.geteuid()}))"
REQUIRED_TESTS = ('test_actual_pinned_tool_reverifies_all_windows',
                  'test_actual_pinned_tool_reverifies_k12_document_bytes',
                  'test_the_w1_candidates_own_suite_passes_on_documents_bound_by_the_binder',
                  'test_actual_pinned_tool_refuses_k8_documents_from_other_calendar',
                  'test_actual_pinned_tool_refuses_k12_documents_from_other_calendar')
NEW_CASE_COUNT = 93


def case_name_sha256(name):
    if type(name) is not str or not name:
        raise ValueError('case name must be an explicit nonempty string')
    return hashlib.sha256(name.encode('utf-8')).hexdigest()


def case_inventory(names=None, hashes=None, label='case inventory', unique=False):
    """Exactly one explicit inventory; hash case.name without changing the JUnit."""
    if (names is None)==(hashes is None):
        raise ValueError(label+' is missing or ambiguous')
    values=names if names is not None else hashes
    if type(values) not in (list,tuple) or not values:
        raise ValueError(label+' must be an explicit nonempty array')
    if names is not None:
        result=[case_name_sha256(name) for name in values]
    else:
        if any(type(pin) is not str or re.fullmatch('[0-9a-f]{64}',pin) is None for pin in values):
            raise ValueError(label+' hash is malformed')
        result=list(values)
    if unique and len(set(result))!=len(result):
        raise ValueError(label+' must be unique')
    return result


def inventory_contains(full, part):
    full_counts=Counter(full)
    return all(full_counts[pin]>=count for pin,count in Counter(part).items())


def read_regular(path):
    """Parse and hash the same stable consumed bytes; refuse linked paths or nonregular evidence."""
    absolute=os.path.abspath(path)
    if os.path.realpath(absolute)!=absolute:raise ValueError('binder evidence path is linked')
    fd=os.open(absolute,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0))
    try:
        first=os.fstat(fd)
        if not stat.S_ISREG(first.st_mode):raise ValueError('binder evidence is not regular')
        chunks=[]
        while True:
            chunk=os.read(fd,1024*1024)
            if not chunk:break
            chunks.append(chunk)
        last=os.fstat(fd)
        identity=lambda v:(v.st_dev,v.st_ino,v.st_size,v.st_mtime_ns,v.st_ctime_ns)
        if identity(first)!=identity(last):raise ValueError('binder evidence changed while read')
        return b''.join(chunks)
    finally:os.close(fd)


def sha_file(path):
    digest=hashlib.sha256()
    with open(path,'rb') as handle:
        for block in iter(lambda:handle.read(1<<20),b''):digest.update(block)
    return digest.hexdigest()


def regular(path):
    return stat.S_ISREG(os.lstat(path).st_mode)


def verify_candidate(directory):
    """The exact published manifest, every listed byte, and no hidden unlisted/linked source."""
    directory=os.path.abspath(directory)
    if os.path.realpath(directory)!=directory or not os.path.isdir(directory):
        raise ValueError('binder directory is not a real directory')
    seal=os.path.join(directory,'SHA256SUMS')
    if not regular(seal) or sha_file(seal)!=CANDIDATE_SEAL:
        raise ValueError('binder manifest differs from the published candidate')
    listed={}
    with open(seal,'r',encoding='utf-8') as handle:
        for line in handle.read().splitlines():
            digest,separator,name=line.partition('  ')
            if not separator or not re.fullmatch('[0-9a-f]{64}',digest) or name in listed:
                raise ValueError('binder manifest is malformed')
            if name.startswith('/') or any(part in ('','.','..') for part in name.split('/')):
                raise ValueError('binder manifest path is unsafe')
            listed[name]=digest
    present=[]
    for folder,names,files in os.walk(directory,followlinks=False):
        for name in names:
            if os.path.islink(os.path.join(folder,name)):
                raise ValueError('binder source contains a directory link')
        for name in files:
            path=os.path.join(folder,name)
            if not regular(path):raise ValueError('binder source contains a nonregular file')
            present.append(os.path.relpath(path,directory))
    if set(present)!=set(listed)|{'SHA256SUMS'}:
        raise ValueError('binder source has missing or unlisted files')
    if not all(sha_file(os.path.join(directory,name))==digest for name,digest in listed.items()):
        raise ValueError('binder listed bytes differ')
    if listed.get('bind/bind_once.py')!=BINDER_SOURCE:
        raise ValueError('binder source is not the unit guard revision')
    return {'manifest_sha256':CANDIDATE_SEAL,'binder_sha256':BINDER_SOURCE,'files':len(listed),
            'accepted_seals_sha256':sha_file(os.path.join(directory,'bind','ACCEPTED_SEALS.json'))}


def read_requirements(path):
    spec=json.loads(read_regular(path))
    if any(key in spec for key in ('binder_case_names','bootstrap_new_cases','w1_case_names')):
        raise ValueError('operative requirements must use only hashed case inventories')
    for field,count_field in (('binder_case_name_sha256','binder_expected_count'),
                              ('w1_case_name_sha256','w1_expected_count')):
        values=case_inventory(hashes=spec.get(field),label=field)
        count=spec.get(count_field)
        if type(count) is not int or count<=0 or len(values)!=count:
            raise ValueError(field+' count differs from its inventory')
    new=case_inventory(hashes=spec.get('bootstrap_new_case_name_sha256'),
                       label='bootstrap_new_case_name_sha256',unique=True)
    if len(new)!=NEW_CASE_COUNT:
        raise ValueError('mandatory new BOOT case inventory count differs')
    if not inventory_contains(spec['binder_case_name_sha256'],new):
        raise ValueError('new BOOT inventory is not contained in the full binder inventory')
    if set(spec.get('versions',{}))!={'3.9','3.12'}:
        raise ValueError('both binder interpreter requirements are mandatory')
    for version,row in spec['versions'].items():
        if set(row.get('dependencies',{}))!={'pytest','exchange_calendars'}:
            raise ValueError('pytest and exchange_calendars exact versions are mandatory')
        if not all(re.fullmatch(r'\d+(?:\.\d+)+(?:[a-z0-9.]+)?',v) for v in row['dependencies'].values()):
            raise ValueError('binder dependency version is not exact')
        requirements=row.get('requirements',[])
        if not requirements or any(not re.fullmatch(r'[A-Za-z0-9_.-]+==[A-Za-z0-9_.+-]+',p) for p in requirements):
            raise ValueError('binder requirements must all use exact versions')
        for package,want in row['dependencies'].items():
            if not any(p.replace('_','-')==package.replace('_','-')+'=='+want for p in requirements):
                raise ValueError('binder requirements do not install the declared dependency')
    return spec


def _junit_layout(raw):
    """Accept literal pytest hierarchy; no result may hide outside a direct case."""
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('JUnit declarations are not evidence')
    try:node=ET.fromstring(raw)
    except ET.ParseError as error:raise ValueError('JUnit is malformed') from error
    suites=[node] if node.tag=='testsuite' else list(node) if node.tag=='testsuites' else []
    if not suites or any(s.tag!='testsuite' for s in suites):
        raise ValueError('JUnit ambiguous suite structure')
    if list(node.iter('testsuite'))!=suites or len(list(node.iter('testsuites')))!=(1 if node.tag=='testsuites' else 0):
        raise ValueError('JUnit nested suite structure')
    keys=('tests','failures','errors','skipped')
    counts=dict.fromkeys(keys,0);cases=[]
    def number(element,key):
        text=element.get(key)
        if type(text) is not str or re.fullmatch('[0-9]+',text) is None:
            raise ValueError('JUnit count is not an explicit nonnegative integer')
        return int(text)
    def leaf(element):
        if len(element):raise ValueError('JUnit hidden element inside result or output')
    def properties(element):
        if any(p.tag!='property' or len(p) for p in element):
            raise ValueError('JUnit ambiguous properties')
    for suite in suites:
        direct=list(suite.findall('testcase'))
        for element in suite:
            if element.tag=='properties':properties(element)
            elif element.tag in ('system-out','system-err'):leaf(element)
            elif element.tag=='testcase':
                if not element.get('name'):raise ValueError('JUnit case has no name')
                outcomes=[]
                for child in element:
                    if child.tag=='properties':properties(child)
                    elif child.tag in ('failure','error','skipped'):
                        leaf(child);outcomes.append(child.tag)
                    elif child.tag in ('system-out','system-err'):leaf(child)
                    else:raise ValueError('JUnit ambiguous testcase child')
                if len(outcomes)>1:raise ValueError('JUnit ambiguous multiple case results')
            else:raise ValueError('JUnit ambiguous testsuite child')
        declared={key:number(suite,key) for key in keys}
        actual={'tests':len(direct),'failures':sum(c.find('failure') is not None for c in direct),
                'errors':sum(c.find('error') is not None for c in direct),
                'skipped':sum(c.find('skipped') is not None for c in direct)}
        if declared!=actual:raise ValueError('JUnit suite counts contradict its direct cases')
        for key in keys:counts[key]+=declared[key]
        cases.extend(direct)
    if list(node.iter('testcase'))!=cases:raise ValueError('JUnit nested or misplaced testcase')
    for tag in ('failure','error','skipped'):
        direct_results=[c.find(tag) for c in cases if c.find(tag) is not None]
        if list(node.iter(tag))!=direct_results:raise ValueError('JUnit hidden failure error or omission')
    if node.tag=='testsuites':
        for key in keys:
            if node.get(key) is not None and number(node,key)!=counts[key]:
                raise ValueError('JUnit container counts contradict its suites')
    return counts,cases


def inspect_junit(path,required_tests=REQUIRED_TESTS,expected_case_names=None,new_case_names=None,
                  expected_case_name_hashes=None,new_case_name_hashes=None):
    expected=case_inventory(expected_case_names,expected_case_name_hashes,'expected collection')
    new=[]
    if new_case_names is not None or new_case_name_hashes is not None:
        new=case_inventory(new_case_names,new_case_name_hashes,'mandatory new case inventory',unique=True)
        if not inventory_contains(expected,new):
            raise ValueError('new case inventory is not contained in the expected collection')
    raw=read_regular(path)
    counts,cases=_junit_layout(raw)
    if counts['tests']!=len(cases) or counts['tests']<=0:
        raise ValueError('binder report count does not match cases')
    skipped=[];failed=[]
    for case in cases:
        name='%s::%s'%(case.get('classname',''),case.get('name',''))
        skip=case.find('skipped')
        if skip is not None:
            skipped.append({'test':name,'reason':skip.get('message') or (skip.text or '').strip()})
        if case.find('failure') is not None or case.find('error') is not None:failed.append(name)
    if counts['skipped']!=len(skipped) or counts['failures']+counts['errors']!=len(failed):
        raise ValueError('binder report failure/skip counts do not match cases')
    missing=[]
    if Counter(case_name_sha256(c.get('name')) for c in cases)!=Counter(expected):missing.append('FULL_PINNED_COLLECTION')
    for required in new:
        matching=[c for c in cases if case_name_sha256(c.get('name'))==required]
        if len(matching)!=1 or any(c.find(tag) is not None for c in matching for tag in ('skipped','failure','error')):
            label=next((name for name in new_case_names or [] if case_name_sha256(name)==required),required)
            missing.append('NEW_BOOTSTRAP_CASE:'+label)
    for required in required_tests:
        matching=[c for c in cases if c.get('name')==required]
        if len(matching)!=1 or any(c.find(tag) is not None for c in matching for tag in ('skipped','failure','error')):
            missing.append(required)
    return {'counts':counts,'passed':counts['tests']-counts['failures']-counts['errors']-counts['skipped'],
            'skipped_tests':skipped,'failed_tests':failed,'required_tests_not_passed':missing,
            'sha256':hashlib.sha256(raw).hexdigest(),
            'complete':counts['failures']==counts['errors']==0 and not missing,
            'privileged_execution':'NOT_REQUESTED: non-root binder suite only; emulated target identities are not host proof'}
