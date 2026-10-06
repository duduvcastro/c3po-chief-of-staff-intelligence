"""Privacy and whole-package integrity gate; does not convert failed proof steps to PASS."""
import hashlib,json,re,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
listed={}
for line in (root/'SHA256SUMS').read_text().splitlines():
 h,n=line.split('  ',1)
 if n in listed:raise SystemExit('DUPLICATE_MANIFEST')
 listed[n]=h
actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() or p.is_symlink()}
if actual!=set(listed)|{'SHA256SUMS'}:raise SystemExit('PACKAGE_SET_CHANGED')
for n,h in listed.items():
 p=root/n
 if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=h:raise SystemExit('PACKAGE_CHANGED')
out=Path(sys.argv[1]);files=[p for p in out.rglob('*') if p.is_file()]
if not files:raise SystemExit('NO_OUTPUTS')
# Private source input is never published. Raw logs remain available to the job even if this gate refuses upload.
private=re.compile(rb'/Users/[^\s\"\']+|[A-Za-z0-9._%+-]{1,128}@[A-Za-z0-9.-]{1,128}\.[A-Za-z]{2,}')
for p in files:
 if p.is_symlink():raise SystemExit('LINKED_ARTIFACT_UPLOAD_REFUSED')
 for match in private.finditer(p.read_bytes()):
  # These two reserved fixture addresses are literal sealed test inputs, bound to the package hashes checked above.
  allowed={hashlib.sha256(x).hexdigest() for x in (b'fixture@unused.invalid',b'changed@unused.invalid')}
  if hashlib.sha256(match.group()).hexdigest() not in allowed:raise SystemExit('PRIVATE_ARTIFACT_CONTENT_UPLOAD_REFUSED')
print(json.dumps({'status':'ARTIFACT_PRIVACY_AND_PACKAGE_INTEGRITY_CHECKED','files':len(files),'proof_success_not_inferred':True}))
