"""New final-source proof driver for Fable; never import or run app/child/host."""
import hashlib,json,sys,unittest
from pathlib import Path

def main():
    root=Path(__file__).resolve().parent
    loader=unittest.TestLoader();suite=unittest.TestSuite()
    for name in ('test_j4_receipt_codec.NewJ4Decoder', 'test_j4_receipt_clock_delta.NewFinalDelta',
                 'test_j4_receipt_stdout_delta.NewStdoutDelta', 'test_j4_receipt_mode_delta.NewExactModeDelta'):
        suite.addTests(loader.loadTestsFromName(name))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    source=root/'j4_receipt_adapter.py'
    raw={'schema':'J4_RECEIPT_CODEC_FIXTURE_RESULT_V1','scope':'NEW_PURE_CODEC_FIXTURES_ONLY',
         'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
         'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
         'skipped':len(result.skipped),'pass':result.wasSuccessful() and result.testsRun==41,
         'actual_installation_certified':False,'operational_GO':False}
    print(json.dumps(raw,sort_keys=True,separators=(',',':')))
    return 0 if raw['pass'] else 1

if __name__=='__main__':raise SystemExit(main())
