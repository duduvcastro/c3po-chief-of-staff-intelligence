"""Current R6 fixture selection only; no operational command or application."""
from pathlib import Path
import hashlib,json,sys,unittest

root=Path(__file__).resolve().parent
sys.path.insert(0,str(root))
selection=json.loads((root/'CURRENT_TEST_SELECTION.json').read_text())
for name,digest in selection['required_source_sha256'].items():
    if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:
        raise SystemExit('Required fixture source changed: '+name)
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name)
                         for name in selection['required_test_modules'])
if suite.countTestCases()!=selection['required_methods']:
    raise SystemExit('Current required fixture count changed')
result=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
