"""New untrusted data-bundle guards; fixture data only, no decrypt/network/host."""
import copy,hashlib,io,json,os,pathlib,sys,tarfile,tempfile,unittest
sys.dont_write_bytecode=True;sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import private_bundle as m
COUNT=0
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def manifest(files):return canonical(dict(schema='CAPTURE_PRIVATE_INPUT_INVENTORY_V1',session='2026-10-08',files=[dict(bundle_path=n,sha256=m.sha(b),bytes=len(b)) for n,b in files],total_files=len(files),total_bytes=sum(len(b) for n,b in files)))
def archive(files,member_type=None,pax=None,extra_manifest=None,include_manifest=True):
 out=io.BytesIO()
 with tarfile.open(fileobj=out,mode='w',format=tarfile.PAX_FORMAT if pax else tarfile.USTAR_FORMAT) as t:
  for n,b in files:
   info=tarfile.TarInfo(n);info.size=len(b)
   if member_type:info.type=member_type;info.linkname='outside'
   if pax:info.pax_headers=pax
   t.addfile(info,io.BytesIO(b))
  if include_manifest:
   raw=extra_manifest if extra_manifest is not None else m.embedded(json.loads(manifest(files)),m.sha(manifest(files)));info=tarfile.TarInfo('BUNDLE_MANIFEST.json');info.size=len(raw);t.addfile(info,io.BytesIO(raw))
 return out.getvalue()
class Tests(unittest.TestCase):
 def setUp(self):self.files=[('evidence/TREE_POST/bound/PREPARE.json',b'private fixture'),('documents/proof.json',b'fixture proof')];self.mr=manifest(self.files);self.pin=m.sha(self.mr)
 def verify(self,raw=None,mr=None,pin=None):
  global COUNT;COUNT+=1
  return m.verify(raw or archive(self.files),mr or self.mr,pin or self.pin)
 def test_exact_all_files_before_storage(self):self.assertEqual(self.verify(),dict(self.files))
 def test_embedded_manifest_wrong_missing_duplicate(self):
  for raw in [archive(self.files,extra_manifest=b'wrong'),archive(self.files,include_manifest=False),archive(self.files)+archive(self.files)]:
   with self.assertRaises(m.Refused):self.verify(raw=raw)
 def test_empty_historical_stderr_exact(self):
  fs=self.files+[('evidence/stdout/stderr.private.txt',b'')];mr=manifest(fs);self.assertEqual(self.verify(raw=archive(fs),mr=mr,pin=m.sha(mr)),dict(fs))
 def test_wrong_manifest_pin(self):
  with self.assertRaises(m.Refused):self.verify(pin='a'*64)
 def test_wrong_session(self):
  v=json.loads(self.mr);v['session']='2026-10-09';raw=canonical(v)
  with self.assertRaises(m.Refused):self.verify(mr=raw,pin=m.sha(raw))
 def test_extra_missing_duplicate_and_changed_files(self):
  for fs in [self.files+[('extra',b'x')],self.files[:1],self.files+self.files[:1],[(self.files[0][0],b'changed fixture'),self.files[1]]]:
   with self.assertRaises(m.Refused):self.verify(raw=archive(fs))
 def test_absolute_and_parent_paths(self):
  for name in ('/outside','../outside','ok/../../outside','a//b','a/./b'):
   fs=[(name,b'fixture')];raw=manifest(fs)
   with self.assertRaises(m.Refused):self.verify(raw=archive(fs),mr=raw,pin=m.sha(raw))
 def test_symlink_hardlink_directory_and_fifo_refused(self):
  for typ in (tarfile.SYMTYPE,tarfile.LNKTYPE,tarfile.DIRTYPE,tarfile.FIFOTYPE):
   with self.assertRaises(m.Refused):self.verify(raw=archive(self.files,member_type=typ))
 def test_pax_and_trailing_data_refused(self):
  with self.assertRaises(m.Refused):self.verify(raw=archive(self.files,pax={'comment':'untrusted'}))
  with self.assertRaises(m.Refused):self.verify(raw=archive(self.files)+b'nonzero extra bytes')
 def test_manifest_count_and_size_mismatch(self):
  for key,val in [('total_files',99),('total_bytes',0)]:
   v=json.loads(self.mr);v[key]=val;raw=canonical(v)
   with self.assertRaises(m.Refused):self.verify(mr=raw,pin=m.sha(raw))
 def test_file_directory_collision_refused(self):
  fs=[('a',b'one'),('a/b',b'two')];raw=manifest(fs)
  with self.assertRaises(m.Refused):self.verify(raw=archive(fs),mr=raw,pin=m.sha(raw))
 def test_storage_private_no_overwrite(self):
  global COUNT;COUNT+=1
  with tempfile.TemporaryDirectory(dir=str(pathlib.Path(tempfile.gettempdir()).resolve())) as td:
   root=pathlib.Path(td);root.chmod(0o700);files=self.verify();m.store(str(root),files)
   for n,b in files.items():self.assertEqual((root/n).read_bytes(),b);self.assertEqual((root/n).stat().st_mode&0o777,0o600)
   self.assertEqual((root/'evidence').stat().st_mode&0o777,0o700)
   with self.assertRaises(m.Refused):m.store(str(root),files)
 def test_storage_symlink_and_public_root_refused(self):
  global COUNT;COUNT+=2
  with tempfile.TemporaryDirectory(dir=str(pathlib.Path(tempfile.gettempdir()).resolve())) as td:
   base=pathlib.Path(td);out=base/'out';out.mkdir(mode=0o755);link=base/'link';link.symlink_to(out)
   for p in (out,link):
    with self.assertRaises(m.Refused):m.store(str(p),dict(self.files))
 def test_private_input_mode_and_link_guards(self):
  global COUNT;COUNT+=3
  with tempfile.TemporaryDirectory(dir=str(pathlib.Path(tempfile.gettempdir()).resolve())) as td:
   root=pathlib.Path(td);p=root/'input';p.write_bytes(b'fixture');p.chmod(0o600);self.assertEqual(m.private_read(str(p),100),b'fixture')
   p.chmod(0o644)
   with self.assertRaises(m.Refused):m.private_read(str(p),100)
   p.chmod(0o600);os.link(p,root/'hardlink')
   with self.assertRaises(m.Refused):m.private_read(str(p),100)
if __name__=='__main__':
 denied=[]
 def audit(event,args):
  if event.startswith(('socket.','subprocess.')) or event in ('os.system','os.exec','os.posix_spawn','os.fork'):denied.append(event);raise RuntimeError('OFFLINE_NO_NETWORK_CHILD_HOST')
 sys.addaudithook(audit);result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests));root=pathlib.Path(__file__).resolve().parent
 report=dict(schema='CAPTURE_PRIVATE_BUNDLE_TEST_V2',methods=result.testsRun,scenarios=COUNT,failures=len(result.failures),errors=len(result.errors),audit_denials=len(denied),source_sha256=m.sha((root/'private_bundle.py').read_bytes()),test_sha256=m.sha(pathlib.Path(__file__).read_bytes()),expected_private_manifest_sha256=m.EXPECTED_MANIFEST,actual_decrypt_calls=0,host_calls=0,operational_READY=False)
 with (root/'BUNDLE_TEST_RESULT.json').open('x') as f:f.write(json.dumps(report,sort_keys=True,indent=2)+'\n')
 print(json.dumps(report));raise SystemExit(0 if result.wasSuccessful() and not denied else 1)
