import hashlib,json,pathlib,sys,unittest
HOME=pathlib.Path(__file__).resolve().parent
sys.path[:0]=[str(HOME/'channel'),str(HOME/'program')]
def audit(event,args):
 if event.startswith(('subprocess.','socket.connect','os.system','os.posix_spawn','os.fork')):raise RuntimeError('FOUNDATION_NO_HOST_OR_NETWORK')
sys.addaudithook(audit)
suite=unittest.TestSuite()
for name in ('test_job_channel','test_checked_program','test_parameter_render'):suite.addTests(unittest.defaultTestLoader.loadTestsFromName(name))
r=unittest.TextTestRunner(verbosity=1).run(suite)
report=dict(schema='CAPTURE_FLOW_FOUNDATION_PROOF_V1',methods=r.testsRun,failures=len(r.failures),errors=len(r.errors),files={str(p.relative_to(HOME)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(HOME.rglob('*.py'))},actual_host_calls=0,actual_prepare_sign_dispatch=0,actual_runtime_measurements=0,full_live_adapter_implemented=False,operational_READY=False)
(HOME/'RESULT.public.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
raise SystemExit(0 if r.wasSuccessful() else 2)
