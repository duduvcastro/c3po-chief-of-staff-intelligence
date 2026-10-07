"""Strict ciphertext-decoded night evidence import. Never rewrites signed bytes.

Manifest authenticity is supplied by the externally read-back #429 control. This
importer proves only storage/bytes; the guarded binder must re-derive completion.
"""
import argparse,hashlib,io,json,os,pathlib,re,stat,tarfile
class Refused(ValueError):pass
def need(ok,code):
 if not ok:raise Refused(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def strict(raw):
 def pairs(items):
  out={}
  for k,v in items:need(k not in out,'NIGHT_DUPLICATE');out[k]=v
  return out
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:need(False,'NIGHT_CONSTANT'))
def inspect(raw,pin):
 need(type(raw) is bytes and 0<len(raw)<=16*1024*1024 and len(raw)%512==0,'NIGHT_TAR_SIZE');files={};used=0
 with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as t:
  for m in t:
   need(m.isfile() and m.type==tarfile.REGTYPE and not m.pax_headers and not m.linkname and m.uid==m.gid==0 and m.size<=2*1024*1024,'NIGHT_TAR_MEMBER')
   name=m.name;need(name not in files and (name=='MANIFEST.private.json' or re.fullmatch(r'(commit_result|publish_launch)/bound/(?:[A-Za-z0-9_.-]{1,100}|templates/[A-Za-z0-9_.-]{1,100}|\.dispatch-root/\.go-[0-9a-f]{64}\.claim|\.dispatch-root/[a-z0-9-]{1,100}-once/(?:exit.json|intent.json|spawn.claim|stderr.private|stdout.private.json))',name)),'NIGHT_TAR_PATH')
   need(m.offset_data==m.offset+512 and raw[m.offset+257:m.offset+265]==b'ustar\x0000','NIGHT_USTAR_ONLY')
   files[name]=t.extractfile(m).read();used=max(used,m.offset_data+((m.size+511)//512)*512)
 need(len(files)<=256 and len(raw)-used>=1024 and not any(raw[used:]),'NIGHT_TAR_END')
 manifest=files.pop('MANIFEST.private.json',None);need(manifest is not None and sha(manifest)==pin,'NIGHT_MANIFEST_PIN');v=strict(manifest)
 need(set(v)=={'schema','session','grid','slot','files'} and v['schema']=='CAPTURE_NIGHT_EVIDENCE_V1' and v['session']=='2026-10-08' and v['grid']=='G19' and v['slot'] in ('PRIMARY','SPARE'),'NIGHT_MANIFEST_SCOPE')
 need(type(v['files']) is list and len(v['files'])==len(files),'NIGHT_MEMBER_COUNT');listed={}
 for row in v['files']:
  need(set(row)=={'path','bytes','sha256'} and row['path'] in files and row['path'] not in listed,'NIGHT_LISTED_MEMBER');b=files[row['path']]
  need(type(row['bytes']) is int and len(b)==row['bytes'] and sha(b)==row['sha256'],'NIGHT_MEMBER_PIN');listed[row['path']]=b
 for op in ('commit_result','publish_launch'):
  for name in ('PREPARE.json','PARAMETERS.json','REQUEST.BOUND.json','DISPATCH.BOUND.json','CLAIM_ROOT_IDENTITY.json','GO_SCOPE.txt','FINAL_PAYLOAD.BOUND.py','SHA256SUMS','OWNER_QUESTION.txt'):
   need(op+'/bound/'+name in files,'NIGHT_REQUIRED_BOUND')
  need(any(n.startswith(op+'/bound/.dispatch-root/') and n.endswith('/exit.json') for n in files),'NIGHT_REQUIRED_RESULT')
 return v,listed

def main():
 ap=argparse.ArgumentParser(allow_abbrev=False);ap.add_argument('--tar',required=True);ap.add_argument('--manifest-sha256',required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
 p=pathlib.Path(a.tar);need(p.is_absolute() and not p.is_symlink(),'NIGHT_INPUT_PATH');s=p.lstat();need(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o600,'NIGHT_PRIVATE_INPUT');fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as f:
  before=os.fstat(f.fileno());raw=f.read(16*1024*1024+1);after=os.fstat(f.fileno())
 need((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)==(p.lstat().st_dev,p.lstat().st_ino,p.lstat().st_size,p.lstat().st_mtime_ns,p.lstat().st_ctime_ns),'NIGHT_INPUT_CHANGED')
 v,files=inspect(raw,a.manifest_sha256);out=pathlib.Path(a.out);need(out.is_absolute() and not out.exists() and out.parent.is_dir(),'NIGHT_OUTPUT')
 for q in (out,*out.parents):need(not q.is_symlink(),'NIGHT_OUTPUT_LINK')
 out.mkdir(mode=0o700)
 for name,b in sorted(files.items()):
  dest=out/name
  for parent in reversed(dest.parent.parents):
   if parent==out or out in parent.parents:
    if not parent.exists():parent.mkdir(mode=0o700)
  if not dest.parent.exists():dest.parent.mkdir(mode=0o700)
  fd=os.open(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
 print(json.dumps(dict(status='NIGHT_BYTES_IMPORTED_NOT_VERIFIED',slot=v['slot'],files=len(files),manifest_sha256=a.manifest_sha256,operational_READY=False)))
if __name__=='__main__':main()
