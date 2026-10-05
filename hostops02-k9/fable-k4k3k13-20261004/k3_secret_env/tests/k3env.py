"""Fixtures of K3 (secret.env): the emulated host as the reader provisioning of 2026-10-03 left it (/etc/c3po-reader
root:root 0700 with docker-cli/ inside), the running worker c3po-r2d2-worker-1 whose environment holds a FAKE database
URL, the plan a binder copies from the receipts, and the scans that prove nothing of the value leaves a run.

Every value here is a synthetic canary. The passwords are spelled in alternating case, so no eight consecutive bytes of
them can occur in a receipt by chance (a receipt holds lower-case hex, upper-case codes, lower-case keys, paths and
instants). Two canary worlds have values of unusual lengths (VALUE_LENGTHS); the decimal spellings of the value length,
the line length and the file size with one and with two newlines are searched for as numbers. No value of a real host is
carried by these files."""
import base64
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re

import family as f
import hostemu

HERE=Path(__file__).resolve().parent
DIRECTORY=HERE.parent
NOW=datetime(2026,10,4,22,30,tzinfo=timezone.utc)          # Sunday 19:30 BRT, the evening of row A7 (WRITE_EPOCH)
KEY='C3PO_DATABASE_URL'
PATTERN='aBcDeFgHiJkLmNoPqRsTuVwXyZ'
def password(seed,length):
    """An alternating-case canary password of exactly length bytes (letters only: printable, no space, quote or backslash)."""
    out=seed
    while len(out)<length:out+=PATTERN
    return out[:length]
def url(secret):return 'postgresql://c3po:%s@db:5432/c3po'%secret
URL_HEAD=len(url(''))
def of_length(seed,length):
    """A URL whose value is exactly length bytes."""
    return url(password(seed,length-URL_HEAD))
PASSWORD='SeCrEtEnVcAnArYpAsSwOrDoNlY'
VALUE=url(PASSWORD)                                          # the default world
VALUE_A=of_length('QwErTyCaNaRyWoRlDa',3217)                # the two canary worlds: unusual lengths, other first bytes
VALUE_B=of_length('ZxCvBnCaNaRyWoRlDb',1729)
VALUES=(VALUE,VALUE_A,VALUE_B)
LITERAL='FAKE-SECRET-FOR-TESTS-0002'                         # a plain fake value (exact-match scans only)

WORKER=hostemu.WORKER
WORKER_ID='5e'*32                                            # fixed, so that two worlds differ in their secret only
def K():return f.load(DIRECTORY)
def m():return K().m

class K3Host(hostemu.FakeHost):
    """The emulated host of the core, with one difference: the source writes from a memoryview of a bytearray (so that the
    bytearray can be zeroed afterwards), which the real os.write accepts and the core's emulation, written for
    create_file's bytes, asserts against. The view is copied here; the bytearray behind it is kept for the tests."""
    def write(self,fd,data):
        assert type(data) is memoryview and type(data.obj) is bytearray and data.contiguous and data.format=='B'
        self.written_from=getattr(self,'written_from',[])+[data.obj]
        return hostemu.FakeHost.write(self,fd,data.tobytes())

def world(value=VALUE,extra_env=(),launcher=False,pins=False):
    """(k, host): the host after the reader provisioning (/etc/c3po-reader 0700 with docker-cli/), and, when asked, after
    the operations that may come before K3 (launcher/, pins.env). The worker's C3PO_DATABASE_URL is the value given (None:
    the entry taken out)."""
    k=K();host=f.world(k);host.__class__=K3Host
    host.tree.add('/etc/c3po-reader',uid=0,gid=0,mode=0o700)
    host.tree.add('/etc/c3po-reader/docker-cli',uid=0,gid=0,mode=0o700)
    if launcher:host.tree.add('/etc/c3po-reader/launcher',uid=0,gid=0,mode=0o700)
    if pins:host.tree.add('/etc/c3po-reader/pins.env',kind='file',uid=0,gid=0,mode=0o600,content=b'C3PO_BUILD_SHA='+b'a'*40+b'\n')
    worker=host.docker.container(WORKER);worker['Id']=WORKER_ID
    env=[item for item in worker['Config']['Env'] if item.split('=',1)[0]!=KEY]
    if value is not None:env.append(KEY+'='+value)
    worker['Config']['Env']=env+list(extra_env)
    return k,host

def worker_id(host):return host.docker.container(WORKER)['Id']
def fields(host,**changes):
    out={'config_chain':hostemu.rows(host,'/etc/c3po-reader'),'worker_container_id':worker_id(host),'evidence_boot_id_sha256':f.BOOT_SHA}
    out.update(changes);return out

def case(now=None,**options):
    """(docs, host): a bound fixture that completes on a fresh emulated host."""
    k,host=world(**options);return f.Docs(k,fields(host),now=now or NOW),host

def node(host,path):return host.tree.get(path)
def state_of(host):return host.tree.snapshot()
def line_of(value=VALUE):return (KEY+'='+value+'\n').encode()

# ---------------------------------------------------------------- what must never leave a run
def forms(value):
    """Every form of one value HOC section 8 names: the value and the line, and of the value, the line and the file
    content (one and two newlines) their base64, hex, MD5, SHA-1 and SHA-256."""
    line=KEY+'='+value
    raws=[value.encode(),line.encode(),(line+'\n').encode(),(line+'\n\n').encode()]
    out={value,line}
    for raw in raws:
        out.update((base64.b64encode(raw).decode(),raw.hex(),hashlib.md5(raw).hexdigest(),hashlib.sha1(raw).hexdigest(),hashlib.sha256(raw).hexdigest()))
    return out
def lengths(value):
    """The value length, the line length (without and with its newline) and the file size with two newlines."""
    size=len(value.encode());line=len(KEY)+1+size
    return {size,line,line+1,line+2}
def windows(value,size=8):return {value[start:start+size] for start in range(len(value)-size+1)}
WINDOWS=None
def canaries():
    """Every 8-byte substring of the passwords of the three worlds (the URL text around them is not secret)."""
    global WINDOWS
    if WINDOWS is None:
        found=set()
        for value in VALUES:found|=windows(value[len('postgresql://c3po:'):-len('@db:5432/c3po')])
        WINDOWS=sorted(found)
    return WINDOWS
def leaks(text,extra=()):
    """Every canary window, and every whole secret form, that occurs in text (bytes or str); and the emulator's own
    environment canary (other entries of the worker, the deploy .env), which must never be printed either."""
    if type(text) is bytes:text=text.decode('utf-8','replace')
    found=[item for item in canaries() if item in text]
    for value in VALUES:found+=[item for item in forms(value) if item in text]
    found+=[item for item in (LITERAL,hostemu.SECRET)+tuple(extra) if item in text]
    return found
NUMBER=r'(?<![0-9A-Za-z]){}(?![0-9A-Za-z])'
def length_leaks(text,values=(VALUE_A,VALUE_B)):
    """The decimal spelling of each length of the canary worlds, as a number standing alone in text, and as a hex
    number: none may occur. (The default world's lengths are small and occur in instants and hashes by chance; its
    receipts are compared byte for byte with the canary worlds' instead.)"""
    if type(text) is bytes:text=text.decode('utf-8','replace')
    found=[]
    for value in values:
        for number in lengths(value):
            for spelling in (str(number),'%x'%number,'%o'%number):
                if re.search(NUMBER.format(spelling),text):found.append(spelling)
    return found
def integers(value):
    """Every integer of a decoded JSON document."""
    if type(value) is int:yield value
    elif type(value) is dict:
        for item in value.values():yield from integers(item)
    elif type(value) is list:
        for item in value:yield from integers(item)
def line(receipt):return f.line(receipt)

def outside_view(host):
    """What a run hands to the outside besides its receipt: every argv, variable, standard input and docker config of
    every command, every environment the docker CLI was given, and every text of the host's log but the byte counts of
    write calls (the emulator's record of the argument the kernel receives, not something the run emits)."""
    out=[]
    for entry in host.commands:out.append(json.dumps(entry['argv'])+json.dumps(entry['variables'])+str(entry['docker_config'])+str(entry['stdin']))
    for environment in host.docker.environments:out.append(json.dumps(environment))
    for entry in host.log:
        detail=entry[:2] if entry[0]=='write' else entry
        out.append(' '.join(str(item) for item in detail if type(item) in (str,int,list,tuple)))
    return '\n'.join(out)

def without_identity(receipt):
    """The receipt with what differs between two worlds (device and inode of what was created) taken out: for the
    comparison of two runs that differ in the secret only."""
    value=json.loads(f.line(receipt));value.pop('metadata_sha256',None)
    row=value.get('secret_env') or {}
    if row:row['device']=row['inode']=None
    return value
