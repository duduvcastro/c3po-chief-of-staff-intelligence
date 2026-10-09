"""NEW packaging checks only; closed R1/R2 test methods are never executed."""
import ast
import hashlib
import io
import json
import lzma
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
ADAPTER_SHA = 'fbcb11dde975ee15434a14a12a3b6afa9977ba3b325695b5e826756c616b858e'
WRITER_SHA = 'aeda5b12d34a406b0d61e1e4696e3c535e89fa3dc680ce0d3b14bb4d60b1d387'

PROBE = b'''import ast,hashlib,json,sys,unittest
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root))
import image_path_adapter as adapter
import test_delta_r2 as tests
assert Path(adapter.__file__).resolve()==root/'image_path_adapter.py'
assert Path(tests.__file__).resolve()==root/'test_delta_r2.py'
assert tests.BASE==root
names=unittest.defaultTestLoader.getTestCaseNames(tests.DeltaTests)
assert len(names)==11
case=tests.DeltaTests(names[0]);case.setUp()
assert hashlib.sha256(case.source).hexdigest()==sys.argv[2]
assert hashlib.sha256((root/'image_path_adapter.py').read_bytes()).hexdigest()==sys.argv[3]
for source in (root/'sources').glob('*.py'):ast.parse(source.read_bytes())
print(json.dumps({'imports':2,'source_setup':1,'closed_methods_executed':0,'sources_local':True}))
'''


class NewPackagingTests(unittest.TestCase):
    def test_new_adapter_exact_and_delta_only_changes_local_dependency_path(self):
        self.assertEqual(hashlib.sha256((ROOT/'image_path_adapter.py').read_bytes()).hexdigest(), ADAPTER_SHA)
        original=(ROOT/'historical/r2/test_delta_r2.py').read_text()
        revised=(ROOT/'test_delta_r2.py').read_text()
        expected=original.replace('BASE = ROOT.with_name("codex-epoch04-image-capacity-20261009-r1")',
                                 'BASE = ROOT  # R3 packaging only: all exact public sources travel inside this archive.')
        self.assertEqual(revised,expected)
        self.assertEqual(hashlib.sha256((ROOT/'sources/manifest_writer.py').read_bytes()).hexdigest(),WRITER_SHA)
        lineage=json.loads((ROOT/'SOURCE_LINEAGE.json').read_bytes())
        self.assertEqual(len(lineage['all_exact_public_sources']),7)
        for row in lineage['all_exact_public_sources']:
            raw=(ROOT/row['name']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),row['sha256'])

    def test_new_isolated_archive_imports_and_source_setup_without_sibling_tree(self):
        compressed=(ROOT/'PACKAGE.tar.xz').read_bytes()
        payload=lzma.decompress(compressed)
        self.assertLess(len(payload),1024*1024)
        with tempfile.TemporaryDirectory(prefix='codex-gate-r3-package-fixture-') as temp:
            isolated=Path(temp).resolve()/'alone';isolated.mkdir(mode=0o700)
            with tarfile.open(fileobj=io.BytesIO(payload),mode='r:') as archive:
                members=archive.getmembers()
                self.assertLess(len(members),64)
                self.assertEqual(len({m.name for m in members}),len(members))
                for member in members:
                    path=PurePosixPath(member.name)
                    self.assertTrue(member.isfile() and not path.is_absolute() and '..' not in path.parts)
                    self.assertLess(member.size,100000)
                    destination=isolated/member.name;destination.parent.mkdir(parents=True,exist_ok=True)
                    destination.write_bytes(archive.extractfile(member).read())
            self.assertFalse(isolated.with_name('codex-epoch04-image-capacity-20261009-r1').exists())
            manifest=json.loads((isolated/'PACKAGE_MANIFEST.json').read_bytes())
            for row in manifest['files']:
                raw=(isolated/row['name']).read_bytes()
                self.assertEqual(len(raw),row['bytes'])
                self.assertEqual(hashlib.sha256(raw).hexdigest(),row['sha256'])
            result=subprocess.run((sys.executable,'-I','-B','-',str(isolated),WRITER_SHA,ADAPTER_SHA),
                                  input=PROBE,cwd=temp,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            proof=json.loads(result.stdout)
            self.assertEqual(proof['closed_methods_executed'],0)
            self.assertTrue(proof['sources_local'])


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NewPackagingTests))
    (ROOT/'PACKAGING_RESULT.json').write_text(json.dumps({
        'schema':'CODEX_GATE_R3_NEW_PACKAGING_RESULT_V1','methods':result.testsRun,
        'failures':len(result.failures),'errors':len(result.errors),'scope':'PACKAGING_IMPORT_SETUP_ONLY',
        'closed_r1_methods_executed':0,'closed_r2_methods_executed':0,'app_imports':0,'sql_queries':0,
        'real_transport_runs':0,'adapter_sha256':ADAPTER_SHA},sort_keys=True,separators=(',',':'))+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
