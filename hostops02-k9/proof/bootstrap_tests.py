# Offline family CI checks; no host, Docker, GO or mutable source acceptance.
import hashlib, os, re, stat, json
import xml.etree.ElementTree as ET

def sha_file(p):
    d=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):d.update(b)
    return d.hexdigest()

def verify_unit(root,unit):
    if unit.get('withheld'):raise ValueError('bootstrap requires complete exact unit')
    path=os.path.abspath(os.path.join(root,unit['dest']))
    if os.path.commonpath((root,path))!=root or os.path.realpath(path)!=path:raise ValueError('unit leaves tree or is linked')
    sums=os.path.join(path,unit['seal_file'])
    if not stat.S_ISREG(os.lstat(sums).st_mode) or sha_file(sums)!=unit['seal_sha256']:raise ValueError('unit manifest differs')
    rows={}
    for line in open(sums,encoding='utf-8').read().splitlines():
        h,sep,name=line.partition('  ')
        if not sep or not re.fullmatch('[0-9a-f]{64}',h) or name in rows or name.startswith('/') or any(s in ('','.','..') for s in name.split('/')):raise ValueError('manifest invalid')
        rows[name]=h
    found=set()
    for folder,dirs,files in os.walk(path,followlinks=False):
        if any(os.path.islink(os.path.join(folder,x)) for x in dirs):raise ValueError('directory link')
        for name in files:
            f=os.path.join(folder,name);rel=os.path.relpath(f,path)
            if not stat.S_ISREG(os.lstat(f).st_mode):raise ValueError('nonregular file')
            found.add(rel)
    if found!=set(rows)|{unit['seal_file']}:raise ValueError('unlisted or missing file')
    if any(sha_file(os.path.join(path,n))!=h for n,h in rows.items()):raise ValueError('unit bytes differ')
    return {'unit':unit['dest'],'manifest_sha256':unit['seal_sha256'],'files':len(rows),'entries':rows}

def read_regular(path):
    if os.path.realpath(path)!=os.path.abspath(path):raise ValueError('artifact path is linked')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        a=os.fstat(fd)
        if not stat.S_ISREG(a.st_mode):raise ValueError("artifact not regular")
        chunks=[]
        while True:
            raw=os.read(fd,1048576)
            if not raw:break
            chunks.append(raw)
        z=os.fstat(fd)
        if (a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)!=(z.st_dev,z.st_ino,z.st_size,z.st_mtime_ns,z.st_ctime_ns):raise ValueError("artifact changed during consumed read")
        return b"".join(chunks)
    finally:os.close(fd)

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


def inspect_junit(path,expected_cases=None):
    consumed=read_regular(path)
    counts,cases=_junit_layout(consumed)
    if counts['tests']!=len(cases) or counts['tests']<=0:raise ValueError('JUnit invalid count')
    if any(counts[k]!=len([c for c in cases if c.find(tag) is not None]) for k,tag in [('failures','failure'),('errors','error'),('skipped','skipped')]):raise ValueError('JUnit contradictory results')
    if any(counts[k] for k in ['failures','errors','skipped']):raise ValueError('mandatory tests failed or omitted')
    required={'test_full_positive_observes_identity_and_creates_only_durable_epoch_claim','test_two_distinct_go_hashes_share_the_epoch_claim_and_second_cannot_write','test_create_can_raise_after_creating_and_still_reports_uncertainty','test_native_exclusive_create_between_threads_has_exactly_one_winner','test_final_clock_failure_after_cleanup_keeps_consumed_claim_and_holds'}
    if not required.issubset({c.get('name') for c in cases}):raise ValueError('required semantic cases absent')
    if expected_cases is None:
        expected_cases=json.loads(read_regular(os.path.join(os.path.dirname(__file__),'BOOTSTRAP_TEST_EXPECTATIONS.json')))['case_names']
    if not expected_cases or sorted(c.get('name') for c in cases)!=sorted(expected_cases):raise ValueError('complete sealed family collection differs')
    return {'counts':counts,'passed':len(cases),'sha256':hashlib.sha256(consumed).hexdigest(),'complete':True,'omissions':0,'scope':'Linux offline synthetic and primitive tests only; not host or operational receipts'}
