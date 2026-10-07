"""Fixed age decryption into exclusive local private storage. No SSH or API."""
import argparse,hashlib,os,pathlib,stat,subprocess
AGE='eb7dd1b518f0a307c99cd97782623c5321da049154b04acd2d98d21aa7bc9b2c'
def read(p,limit,private):
 p=pathlib.Path(p)
 if not p.is_absolute() or any(q.is_symlink() for q in (p,*p.parents)):raise ValueError('DECRYPT_PATH')
 with os.fdopen(os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK),'rb') as f:
  a=os.fstat(f.fileno());raw=f.read(limit+1);b=os.fstat(f.fileno())
 if not stat.S_ISREG(a.st_mode) or a.st_nlink!=1 or a.st_mode&0o022 or len(raw)>limit or (a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)!=(b.st_dev,b.st_ino,b.st_size,b.st_mtime_ns,b.st_ctime_ns) or (a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)!=(p.lstat().st_dev,p.lstat().st_ino,p.lstat().st_size,p.lstat().st_mtime_ns,p.lstat().st_ctime_ns):raise ValueError('DECRYPT_FILE')
 if private and (a.st_uid!=os.getuid() or stat.S_IMODE(a.st_mode)!=0o600):raise ValueError('DECRYPT_PRIVATE')
 return raw
def main():
 ap=argparse.ArgumentParser(allow_abbrev=False)
 for k in ('age','key','cipher','cipher-sha256','out'):ap.add_argument('--'+k,required=True)
 a=ap.parse_args();binary=read(a.age,16*1024*1024,False);cipher=read(a.cipher,16*1024*1024,True);read(a.key,65536,True)
 if hashlib.sha256(binary).hexdigest()!=AGE or hashlib.sha256(cipher).hexdigest()!=a.cipher_sha256 or not cipher.startswith(b'age-encryption.org/v1\n'):raise ValueError('DECRYPT_PIN')
 p=pathlib.Path(a.out);s=p.parent.lstat()
 if not p.is_absolute() or any(q.is_symlink() for q in (p,*p.parents)) or not stat.S_ISDIR(s.st_mode) or s.st_uid!=os.getuid() or stat.S_IMODE(s.st_mode)!=0o700:raise ValueError('DECRYPT_OUTPUT')
 # stdout is held private and bounded; age cannot choose an output pathname.
 r=subprocess.run([a.age,'-d','-i',a.key],input=cipher,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},timeout=30,check=False)
 if r.returncode or not 0<len(r.stdout)<=16*1024*1024:raise ValueError('DECRYPT_REFUSED_NO_RETRY')
 with os.fdopen(os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'wb') as f:f.write(r.stdout);f.flush();os.fsync(f.fileno())
 print('{"status":"PRIVATE_CIPHERTEXT_DECODED_NOT_AUTHORITY","operational_READY":false}')
if __name__=='__main__':main()
