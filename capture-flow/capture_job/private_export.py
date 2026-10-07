"""Encrypt private packets to one pinned Fable recipient. No decrypt or host calls.

Input remains private in memory; child stdout goes directly to an exclusive private
ciphertext file. Errors never print paths, plaintext or child stderr. The exact age
binary SHA must come from the separately verified pinned release/runtime manifest.
This is confidentiality only, not human authentication or operation authority.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
RECIPIENT='age1knekenhrh79x9xm0ghvhltwg075d33mljhu4y6u9zyz3cweszens2vr8x0'
AGE_RELEASE='1.3.2'
AGE_ARCHIVE_SHA='cbe24006683f8eb669266162894b9a522a1af52f2665fbc63a4bb032ed26ac10'
LIMIT=16*1024*1024
class Refused(ValueError): pass

def need(ok,code):
    if not ok:raise Refused(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def same(s):return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns

def no_links(p):
    need(p.is_absolute(),'EXPORT_RELATIVE_PATH')
    for part in (p,*p.parents):need(not part.is_symlink(),'EXPORT_SYMLINK')

def read_private(path):
    p=Path(path);no_links(p)
    fd=os.open(str(p),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        before=os.fstat(f.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid() and before.st_nlink==1
             and stat.S_IMODE(before.st_mode)==0o600 and 0<before.st_size<=LIMIT,'EXPORT_INPUT_NOT_PRIVATE')
        raw=f.read(LIMIT+1);after=os.fstat(f.fileno())
    need(same(before)==same(after)==same(p.lstat()) and len(raw)==before.st_size,'EXPORT_INPUT_CHANGED')
    return raw

def age_binary(path,pin):
    p=Path(path);no_links(p)
    need(type(pin) is str and re.fullmatch('[0-9a-f]{64}',pin) and pin!='0'*64,'EXPORT_AGE_PIN')
    st=p.lstat();need(stat.S_ISREG(st.st_mode) and st.st_nlink==1 and st.st_uid in (0,os.getuid())
                     and not st.st_mode&0o022 and st.st_mode&0o111,'EXPORT_AGE_PERMISSIONS')
    need(sha(p.read_bytes())==pin and same(st)==same(p.lstat()),'EXPORT_AGE_CHANGED')
    # The operational manifest must pin this extracted executable in addition to archive/version.
    return str(p)

def encrypt(path,age_path,age_sha256,out,runner=None):
    raw=read_private(path);exe=age_binary(age_path,age_sha256)
    p=Path(out);no_links(p.parent)
    need(p.is_absolute() and not p.exists() and not p.is_symlink(),'EXPORT_OUTPUT_EXISTS')
    meta=p.parent.lstat();need(stat.S_ISDIR(meta.st_mode) and meta.st_uid==os.getuid()
                            and stat.S_IMODE(meta.st_mode)==0o700,'EXPORT_OUTPUT_NOT_PRIVATE')
    fd=os.open(str(p),os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    ok=False
    try:
        with os.fdopen(fd,'w+b') as stream:
            original=os.fstat(stream.fileno())
            run=subprocess.run if runner is None else runner
            # Only ciphertext may be written by age. The secret payload is input, never an argv value.
            result=run([exe,'--encrypt','--recipient',RECIPIENT],input=raw,stdout=stream,
                       stderr=subprocess.DEVNULL,timeout=30,check=False,
                       env={'PATH':'/usr/bin:/bin','LC_ALL':'C'},cwd='/')
            need(result.returncode==0,'EXPORT_CIPHER_FAILED_NO_RETRY')
            stream.flush();os.fsync(stream.fileno())
            age_binary(age_path,age_sha256)
            before=os.fstat(stream.fileno())
            need((original.st_dev,original.st_ino)==(before.st_dev,before.st_ino)
                 and stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_uid==os.getuid()
                 and stat.S_IMODE(before.st_mode)==0o600 and 0<before.st_size<=LIMIT+65536,
                 'EXPORT_OUTPUT_CHANGED')
            stream.seek(0);encrypted=stream.read(LIMIT+65537);after=os.fstat(stream.fileno())
            need(same(before)==same(after)==same(p.lstat()) and len(encrypted)==before.st_size,
                 'EXPORT_OUTPUT_CHANGED')
            need(encrypted.startswith(b'age-encryption.org/v1\n'), 'EXPORT_CIPHER_FORMAT')
        ok=True
        return {'schema':'CAPTURE_PRIVATE_EXPORT_V1','status':'CIPHERTEXT_STORED_NO_OPERATION_AUTHORITY',
                'ciphertext_sha256':sha(encrypted),'plaintext_sha256':sha(raw),
                'recipient_sha256':sha(RECIPIENT.encode()),'operational_READY':False}
    finally:
        # On failure leave the exclusive file in place, never retry/overwrite it or print its contents.
        if not ok:pass

def main(argv=None):
    import argparse
    ap=argparse.ArgumentParser(description='Encrypt own private packet; no decrypt or operational authority.',allow_abbrev=False)
    ap.add_argument('--input',required=True);ap.add_argument('--age-binary',required=True)
    ap.add_argument('--age-sha256',required=True);ap.add_argument('--out',required=True)
    a=ap.parse_args(argv)
    try:
        print(json.dumps(encrypt(a.input,a.age_binary,a.age_sha256,a.out),sort_keys=True));return 0
    except (Refused,OSError,ValueError,subprocess.SubprocessError):
        print(json.dumps({'status':'PRIVATE_EXPORT_REFUSED_NO_RETRY','operational_READY':False}));return 2
if __name__=='__main__':raise SystemExit(main())
