"""NEW standalone legacy ABI input packaging vector; no closed test import."""
from pathlib import Path
import ast,hashlib,io,os,tarfile,tempfile,unittest

class PackagingDelta(unittest.TestCase):
 def test_new_extracted_historical_input_resolves_from_file_not_cwd(self):
  root=Path(__file__).parent;raw=(root/'test_c6_delta.py').read_bytes()
  tree=ast.parse(raw);assignment=next(x for x in tree.body if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='HISTORICAL_RUNNER' for t in x.targets))
  self.assertIsInstance(assignment.value,ast.BinOp)
  payload=io.BytesIO()
  with tarfile.open(fileobj=payload,mode='w') as tar:
   for name in ('test_c6_delta.py','sources/historical_k9_runner.py'):
    data=(root/name).read_bytes();entry=tarfile.TarInfo(name);entry.size=len(data);tar.addfile(entry,io.BytesIO(data))
  with tempfile.TemporaryDirectory(prefix='new-c6-package-',dir=root) as directory:
   dest=Path(directory).resolve();payload.seek(0)
   with tarfile.open(fileobj=payload) as tar:
    for member in tar.getmembers():
     target=dest/member.name;target.parent.mkdir(exist_ok=True);target.write_bytes(tar.extractfile(member).read())
   outside=dest/'unrelated-cwd';outside.mkdir();previous=os.getcwd()
   try:
    os.chdir(outside);scope={'Path':Path,'__file__':str(dest/'test_c6_delta.py')}
    code=ast.Expression(assignment.value);ast.fix_missing_locations(code);input_path=eval(compile(code,'packaged-path-only','eval'),scope)
    self.assertEqual(hashlib.sha256(input_path.read_bytes()).hexdigest(),'563a4797ab2a7ef4c02a1c1937061a2644420b69bdcc2dca842cd1efd7fb7690')
   finally:os.chdir(previous)

if __name__=='__main__':unittest.main(verbosity=2)
