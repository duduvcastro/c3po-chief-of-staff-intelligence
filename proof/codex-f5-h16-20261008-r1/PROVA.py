import json,pathlib,sys,unittest,hashlib,platform
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
 manifest=json.loads((ROOT/"MANIFEST.json").read_bytes())
 for row in manifest["files"]:
  raw=(ROOT/row["name"]).read_bytes()
  if len(raw)!=row["bytes"] or sha(raw)!=row["sha256"]:raise SystemExit("SOURCE_CHANGED")
 suite=unittest.defaultTestLoader.loadTestsFromName("test_h16")
 result=unittest.TextTestRunner(verbosity=2).run(suite)
 out={"schema":"NEW_F5_LINUX_RESULT_V1","family":"F5","tests":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),"python":platform.python_version(),"platform":platform.system(),"manifest_sha256":sha((ROOT/"MANIFEST.json").read_bytes()),"host_operated":False,"runtime_accepted":False,"operational_GO":False}
 raw=(json.dumps(out,sort_keys=True,separators=(",",":"))+"\n").encode()
 if len(sys.argv)==2:pathlib.Path(sys.argv[1]).write_bytes(raw)
 print(raw.decode(),end="")
 raise SystemExit(0 if result.wasSuccessful() else 1)
if __name__=="__main__":main()
