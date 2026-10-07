"""Strict import of the dated, decrypted data bundle. No decrypt, app or host.

The workflow must authenticate the ephemeral recipient/job and ciphertext first.
Only the 148-file manifest approved separately is permitted by this CLI. Finished
BOUND copies remain evidence only; imports never authorize dispatch or restore
physical root identity. No tar metadata permissions, links or executable flags.
"""
import hashlib,io,json,os,pathlib,re,stat,tarfile
EXPECTED_MANIFEST='8671e15a46627734dbcc133d59b42b574ffea134548d0cec408bec2177bb5e69'
LIMIT=16*1024*1024
class Refused(ValueError):pass
def need(ok,code):
 if not ok:raise Refused(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def strict(raw):
 def pairs(items):
  out={}
  for key,val in items:need(key not in out,'BUNDLE_DUPLICATE_FIELD');out[key]=val
  return out
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:need(False,'BUNDLE_CONSTANT'))
def clean(name):
 need(type(name) is str and len(name)<=512 and re.fullmatch('[A-Za-z0-9_./-]+',name) and not name.startswith('/')
      and str(pathlib.PurePosixPath(name))==name and all(x not in ('','.','..') for x in name.split('/')),'BUNDLE_PATH')
 return name
def embedded(manifest,manifest_sha):
 rows=sorted(manifest['files'],key=lambda x:x['bundle_path'])
 return json.dumps(dict(schema='FABLE_CAPTURE_PRIVATE_BUNDLE_MANIFEST_V1',inventory_sha256=manifest_sha,files=[{k:r[k] for k in ('bundle_path','sha256','bytes')} for r in rows]),sort_keys=True,separators=(',',':')).encode()
def verify(archive,manifest_raw,manifest_sha):
 """Pure complete verification before any output directory/file is created."""
 need(type(manifest_sha) is str and re.fullmatch('[0-9a-f]{64}',manifest_sha) and sha(manifest_raw)==manifest_sha,'BUNDLE_MANIFEST_PIN')
 manifest=strict(manifest_raw);need(manifest.get('schema')=='CAPTURE_PRIVATE_INPUT_INVENTORY_V1' and manifest.get('session')=='2026-10-08','BUNDLE_SCOPE')
 rows=manifest.get('files');need(type(rows) is list and 1<=len(rows)<=200,'BUNDLE_FILE_COUNT')
 expected={}
 for row in rows:
  name=clean(row['bundle_path']);need(name not in expected and type(row.get('bytes')) is int and 0<=row['bytes']<=LIMIT
       and type(row.get('sha256')) is str and re.fullmatch('[0-9a-f]{64}',row['sha256']),'BUNDLE_MEMBER')
  expected[name]=row
 need(manifest.get('total_files')==len(expected) and manifest.get('total_bytes')==sum(r['bytes'] for r in rows) and manifest['total_bytes']<=LIMIT,'BUNDLE_TOTAL')
 for name in expected:
  need(all('/'.join(name.split('/')[:i]) not in expected for i in range(1,len(name.split('/')))),'BUNDLE_FILE_DIRECTORY_COLLISION')
 # Plain, uncompressed tar only. No decompression bombs or metadata extraction.
 need(type(archive) is bytes and 0<len(archive)<=LIMIT+len(rows)*2048+10240,'BUNDLE_ARCHIVE_SIZE')
 files={};manifest_seen=False;embedded_raw=embedded(manifest,manifest_sha)
 with tarfile.open(fileobj=io.BytesIO(archive),mode='r:') as t:
  for member in t:
   name=clean(member.name)
   if name=='BUNDLE_MANIFEST.json':
    need(not manifest_seen and member.isreg() and member.type in (tarfile.REGTYPE,tarfile.AREGTYPE) and not member.pax_headers and not member.linkname and member.size==len(embedded_raw),'BUNDLE_EMBEDDED_MANIFEST_MEMBER')
    need(t.extractfile(member).read(member.size+1)==embedded_raw,'BUNDLE_EMBEDDED_MANIFEST_PIN');manifest_seen=True;continue
   need(name in expected and name not in files and member.isreg()
       and member.type in (tarfile.REGTYPE,tarfile.AREGTYPE) and not member.pax_headers
       and not member.linkname and member.size==expected[name]['bytes'],'BUNDLE_UNEXPECTED_MEMBER')
   stream=t.extractfile(member);need(stream is not None,'BUNDLE_MEMBER_UNREADABLE');raw=stream.read(member.size+1)
   need(len(raw)==member.size and sha(raw)==expected[name]['sha256'],'BUNDLE_MEMBER_PIN');files[name]=raw
  need(not any(archive[t.offset:]),'BUNDLE_TRAILING_DATA')
 need(manifest_seen and set(files)==set(expected),'BUNDLE_MISSING_MEMBER')
 return files
def snapshot(s):return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns
def private_read(p,maximum):
 p=pathlib.Path(p);need(p.is_absolute(),'BUNDLE_PRIVATE_PATH')
 for parent in (p,*p.parents):need(not parent.is_symlink(),'BUNDLE_PRIVATE_SYMLINK')
 fd=os.open(str(p),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  a=os.fstat(f.fileno());need(stat.S_ISREG(a.st_mode) and a.st_nlink==1 and a.st_uid==os.getuid() and stat.S_IMODE(a.st_mode)==0o600 and 0<a.st_size<=maximum,'BUNDLE_INPUT_NOT_PRIVATE');raw=f.read(maximum+1);b=os.fstat(f.fileno())
 need(snapshot(a)==snapshot(b)==snapshot(p.lstat()) and len(raw)==a.st_size,'BUNDLE_INPUT_CHANGED');return raw
def store(out,files):
 out=pathlib.Path(out);need(out.is_absolute(),'BUNDLE_OUTPUT_PATH')
 for ancestor in (out,*out.parents):need(not ancestor.is_symlink(),'BUNDLE_OUTPUT_SYMLINK')
 root=os.open(str(out),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:
  meta=os.fstat(root);need(meta.st_uid==os.getuid() and stat.S_IMODE(meta.st_mode)==0o700 and not os.listdir(root),'BUNDLE_OUTPUT_NOT_OWN_EMPTY')
  def rooted():
   held=os.fstat(root);named=out.lstat();need(stat.S_ISDIR(named.st_mode) and (held.st_dev,held.st_ino)==(named.st_dev,named.st_ino)==(meta.st_dev,meta.st_ino),'BUNDLE_ROOT_REPLACED')
  for name,raw in files.items():
   rooted();parts=clean(name).split('/');current=os.dup(root)
   try:
    for part in parts[:-1]:
     try:os.mkdir(part,0o700,dir_fd=current)
     except FileExistsError:pass
     child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=current);s=os.fstat(child)
     need(s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o700,'BUNDLE_CHILD_NOT_PRIVATE');os.close(current);current=child
    fd=os.open(parts[-1],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=current)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    os.fsync(current);rooted()
   finally:os.close(current)
  os.fsync(root);rooted()
 finally:os.close(root)
def main(argv=None):
 import argparse
 ap=argparse.ArgumentParser(allow_abbrev=False);ap.add_argument('--decrypted-tar',required=True);ap.add_argument('--manifest',required=True);ap.add_argument('--manifest-sha256',required=True);ap.add_argument('--out',required=True);a=ap.parse_args(argv)
 try:
  need(a.manifest_sha256==EXPECTED_MANIFEST,'BUNDLE_DATED_APPROVED_MANIFEST_REQUIRED')
  mr=private_read(a.manifest,1024*1024);raw=private_read(a.decrypted_tar,LIMIT+500000);files=verify(raw,mr,a.manifest_sha256);store(a.out,files)
  print(json.dumps(dict(status='PRIVATE_DATA_STORED_NOT_OPERATION_AUTHORITY',manifest_sha256=sha(mr),archive_sha256=sha(raw),files=len(files),operational_READY=False)));return 0
 except (Refused,OSError,ValueError,KeyError,TypeError,tarfile.TarError):print('{"status":"PRIVATE_BUNDLE_REFUSED_NO_RETRY","operational_READY":false}');return 2
if __name__=='__main__':raise SystemExit(main())
