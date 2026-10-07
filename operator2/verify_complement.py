"""Pure data/hash/AST check. This does not import or run the delivered programs."""
import ast,hashlib,json,pathlib,re,stat,sys
ROOT=pathlib.Path(__file__).resolve().parent

def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 raw=(ROOT/'DELIVERY_MANIFEST.json').read_bytes();v=json.loads(raw)
 assert v['schema']=='CAPTURE_OPERATOR2_DELIVERY_V1' and v['operational_READY'] is False
 expected={r['path'] for r in v['files']};assert len(expected)==len(v['files'])
 for r in v['files']:
  assert re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*',r['path'])
  p=ROOT/r['path'];s=p.lstat();assert stat.S_ISREG(s.st_mode) and not p.is_symlink()
  b=p.read_bytes();assert len(b)==r['bytes'] and sha(b)==r['sha256']
  if p.suffix=='.py':ast.parse(b,filename=r['path'])
 for p in ROOT.rglob('*'):
  assert not p.is_symlink()
  if p.is_file() and p.suffix in ('.py','.yml','.md'):
   assert p.relative_to(ROOT).as_posix() in expected
 assert sha((ROOT/'reference/capture-thursday-single-job.yml').read_bytes())=='3413dc4d76fcca5e65e092ed57b6c2b644cf0bc58be1c3ef4fbcdb3b8332012f'
 assert sha((ROOT/'reference/night_bundle.py').read_bytes())=='8cca3c5775db941b754ba14503c03bd8bdb367379546c816a6632d2ae41001fa'
 assert sha((ROOT/'reference/job_channel.py').read_bytes())=='5111e6dd46041f363ed6725fb3e2cd049a38c16b0e1d530233a86d720194b342'
 assert sha((ROOT/'reference/DATED_AUTHORITY.fixture.json').read_bytes())=='c0af50a35a90cb226346d775cd8854db1afc681744a8255a383a1d8de45677bc'
 for name,source,test,count in [('RESULT.public.json','capsule_data.py','test_capsule_data.py',27),('REHEARSAL_RESULT.public.json','rehearsal_channel.py','test_rehearsal_channel.py',7)]:
  proof=json.loads((ROOT/name).read_bytes());assert proof['methods']==count and proof['failures']==proof['errors']==0 and proof['operational_READY'] is False
  assert proof['source_sha256']==sha((ROOT/source).read_bytes()) and proof['test_sha256']==sha((ROOT/test).read_bytes())
 print(json.dumps(dict(status='PASS_COMPLEMENT_BYTES_AST_ONLY',files=len(v['files']),python_AST=sum(r['path'].endswith('.py') for r in v['files']),manifest_sha256=sha(raw),operational_READY=False),sort_keys=True,separators=(',',':')))
if __name__=='__main__':
 try:main()
 except Exception:print('COMPLEMENT_BYTES_REFUSED');sys.exit(2)
