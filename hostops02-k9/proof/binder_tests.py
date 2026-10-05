"""Offline binder CI step helpers. No binder source, acceptance or frozen test is modified."""
import hashlib
import json
import os
import re
import stat
import xml.etree.ElementTree as ET

CANDIDATE_SEAL = '139ee102ea9da6e238a2bf8188785493630d2c2c408b78d85c81673b904d9654'
BINDER_SOURCE = '337e70dc1568ba8b279b9eec01603b3a5aa8276f52cba1a35c8dc264d63cd4fd'
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
                  'test_the_w1_candidates_own_suite_passes_on_documents_bound_by_the_binder')


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
    with open(path,'r',encoding='utf-8') as handle:spec=json.load(handle)
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


def inspect_junit(path,required_tests=REQUIRED_TESTS):
    try:node=ET.parse(path).getroot()
    except ET.ParseError as error:raise ValueError('binder report is malformed') from error
    suites=[node] if node.tag=='testsuite' else list(node.findall('testsuite')) if node.tag=='testsuites' else []
    if not suites:raise ValueError('binder report has no test suite')
    counts={key:sum(int(s.get(key,'0')) for s in suites) for key in ('tests','failures','errors','skipped')}
    cases=[case for suite in suites for case in suite.iter('testcase')]
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
    for required in required_tests:
        matching=[c for c in cases if c.get('name')==required]
        if len(matching)!=1 or any(c.find(tag) is not None for c in matching for tag in ('skipped','failure','error')):
            missing.append(required)
    return {'counts':counts,'passed':counts['tests']-counts['failures']-counts['errors']-counts['skipped'],
            'skipped_tests':skipped,'failed_tests':failed,'required_tests_not_passed':missing,
            'sha256':sha_file(path),
            'complete':counts['failures']==counts['errors']==0 and not missing,
            'privileged_execution':'NOT_REQUESTED: non-root binder suite only; emulated target identities are not host proof'}
