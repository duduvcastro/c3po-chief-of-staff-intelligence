"""Only the 55 NEW native fixture cases, with exact own source verification.

The three closed component TestCase suites are data helpers, never selected.
T14 actual age cipher has its separate four-case Linux proof. No real host,
provider, owner question, production SQL/Docker, installation or dispatch.
"""
import ast
import hashlib
import io
import json
import os
import platform
import stat
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).absolute().parent
MODULES=('test_native','test_integrated','test_real_adapters','test_night','test_writer_stop','test_assembly_entry')
EXPECTED=55


def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode()


def verify():
    for parent in (ROOT,*ROOT.parents):
        if stat.S_ISLNK(parent.lstat().st_mode):raise ValueError('PROOF_SOURCE_LINK')
    path=ROOT/'MANIFEST.json';before=path.lstat();raw=path.read_bytes()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or stat.S_IMODE(before.st_mode)!=0o444 or before!=path.lstat():
        raise ValueError('PROOF_MANIFEST_CHANGED')
    manifest=json.loads(raw);names=set();trees={}
    for row in manifest['files']:
        name=row['name']
        if name in names or '/' in name or name in ('.','..'):raise ValueError('PROOF_MEMBER')
        names.add(name);path=ROOT/name;before=path.lstat();body=path.read_bytes()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or stat.S_IMODE(before.st_mode)!=0o444 or before!=path.lstat():
            raise ValueError('PROOF_SOURCE_PERMISSION')
        if len(body)!=row['bytes'] or sha(body)!=row['sha256']:raise ValueError('PROOF_SOURCE_PIN')
        if name.endswith('.py'):trees[name]=ast.parse(body,filename=name)
    origin=json.loads((ROOT/'K12_READER_ORIGIN.json').read_bytes())
    nodes=[n for n in trees['k12_reader_reference.py'].body if isinstance(n,ast.FunctionDef) and n.name==origin['function']]
    for node in nodes:
        for part in ast.walk(node):
            # Python 3.12 adds an empty type_params AST field. The historical
            # reader has no type parameters; compare its unchanged 3.9 AST.
            if hasattr(part,'type_params') and part.type_params==[]:delattr(part,'type_params')
    if len(nodes)!=1 or ast.dump(nodes[0],include_attributes=False)!=origin['AST']:
        raise ValueError('PROOF_K12_READER_AST_CHANGED')
    return sha(raw),len(names),len(trees)


def cases(suite):
    for item in suite:
        if isinstance(item,unittest.TestSuite):yield from cases(item)
        else:yield item.id()


def main():
    if len(sys.argv)!=2:raise ValueError('PROOF_OUTPUT_ARGUMENT')
    before=verify();sys.path.insert(0,str(ROOT))
    suite=unittest.defaultTestLoader.loadTestsFromNames(MODULES)
    ids=list(cases(suite))
    if len(ids)!=EXPECTED or len(set(ids))!=EXPECTED or any(i.split('.')[0] not in MODULES for i in ids):
        raise ValueError('PROOF_NEW_CASE_SET')
    # Failure text remains private to this isolated proof. Only counts/IDs and
    # own source pins enter the public artifact; fixture temp paths never do.
    result=unittest.TextTestRunner(stream=io.StringIO(),verbosity=2).run(suite)
    after=verify()
    if before!=after:raise ValueError('PROOF_SOURCE_CHANGED_DURING_CASES')
    value={'schema':'F6_NATIVE_NEW_FIXTURE_RESULT_V2','mode':'FIXTURE','status':'PASS' if result.wasSuccessful() else 'FAIL',
        'test_count':result.testsRun,'failure_count':len(result.failures),'error_count':len(result.errors),
        'case_ids':ids,'new_modules':list(MODULES),'manifest_sha256':before[0],'manifest_file_count':before[1],
        'AST_count':before[2],'python':platform.python_version(),'platform':platform.system(),
        'historical_component_suites_replayed':False,'physical_runtime_accepted':False,
        'production_host_SQL_Docker_provider_operated':False,'owner_question_sent':False,
        'full_operational_rehearsal_complete':False,'operational_GO':False,'T14_actual_crypto':'SEPARATE_OWN_LINUX_RESULT_REQUIRED'}
    data=canonical(value);target=Path(sys.argv[1]);fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:os.write(fd,data);os.fsync(fd)
    finally:os.close(fd)
    print(data.decode(),end='');return 0 if result.wasSuccessful() else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        print('{"schema":"F6_NATIVE_PROOF_HOLD_V2","status":"HOLD","operational_GO":false}')
        raise SystemExit(2)
