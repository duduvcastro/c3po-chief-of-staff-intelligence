"""Standalone -I -B fixture driver; no operational entrypoint or authority."""
import hashlib
import json
from pathlib import Path
import platform
import sys
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
SOURCE_NAMES = ('bounded_readback.py','bounded_image_capacity_gate.py','image_path_adapter.py',
                'image_capacity_gate.py','finite_batch.py','verification_binding.py','test_bounded_readback.py')

def main():
    suite = unittest.defaultTestLoader.discover(str(ROOT), pattern='test_bounded_readback.py')
    with (ROOT/'TEST_RESULT.log').open('w',encoding='utf-8') as output:
        result = unittest.TextTestRunner(stream=output,verbosity=2).run(suite)
    report = {'schema':'BOUNDED_READBACK_REQUIRED_FIXTURE_RESULT_V1','mode':'SYNTHETIC_ONLY',
        'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'skips':len(result.skipped),'python':platform.python_version(),'platform':sys.platform,
        'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCE_NAMES},
        'SQL_execution':False,'app_imports':False,'physical_proof':False,'operational_GO':False}
    (ROOT/'TEST_RESULT.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,sort_keys=True))
    return 0 if result.wasSuccessful() and result.testsRun==34 and not result.skipped else 1

if __name__=='__main__':raise SystemExit(main())
