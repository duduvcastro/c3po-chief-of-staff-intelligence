"""Fixtures of K3-K9: the emulated host as K4 mode E0 and the activation leave it (/var/lib/c3po and the K9 root with its
empty secrets directory, root:root 0700, decision N-8; the running worker c3po-r2d2-worker-1 whose environment holds
three FAKE provider tokens), the two files of September on the data volume holding a FAKE database URL and a FAKE
emitter password, the plan a binder copies from the receipts (E0, the epoch readback, the K9R TREE read), and the scans
that prove nothing of a value leaves a run.

Every value here is a synthetic canary. The tokens and passwords are spelled in alternating case, so no four consecutive
characters of them can occur in a receipt by chance (a receipt holds lower-case hex, upper-case codes, lower-case keys,
paths and instants): a scan for every substring of four characters or more is meaningful. No value of a real host is
carried by these files."""
import base64
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

import family as f
import hostemu

HERE=Path(__file__).resolve().parent
DIRECTORY=HERE.parent
NOW=datetime(2026,10,5,20,45,tzinfo=timezone.utc)          # Monday 17:45 BRT, inside the 17:38-18:03 sends of the K9 note (6.2)
TOKENS={'C3PO_EODHD_API_TOKEN':'EoDhDcAnArYfOrTeStSoNlY','C3PO_FINNHUB_API_TOKEN':'FiNnHuBcAnArYfOrTeStS',
        'C3PO_FMP_API_TOKEN':'FmPcAnArYfOrTeStSoNlYqUiTe'}
LONGER={'C3PO_EODHD_API_TOKEN':'XeOdHdLoNgErCaNaRyFoRtEsTsOnLyAnDmOrE','C3PO_FINNHUB_API_TOKEN':'YfInNhUbLoNgErCaNaRyFoRtEsTsOnLy',
        'C3PO_FMP_API_TOKEN':'ZfMpLoNgErCaNaRyFoRtEsTsOnLyAnDmOrEsTiLl'}
URL_PASSWORD='UrLpAsSwOrDcAnArYfOrTeStS'
LONGER_URL_PASSWORD='VuRlPaSsWoRdLoNgErCaNaRyFoRtEsTsOnLyAnDmOrE'
def url(password=URL_PASSWORD,role='c3po_v2_risk_reader'):return 'postgresql://%s:%s@db:5432/c3po'%(role,password)
def emitter(seed='EmItTeR-pAsSwOrD_cAnArY-fOrTeStS_oNlY-'):
    out=seed
    while len(out)<64:out+='aBcDeFgH'
    return out[:64]
PASSWORD=emitter()
OTHER_PASSWORD=emitter('ZoThEr_EmItTeR-cAnArY_wItH-aNoThEr_StArT-')
LITERAL='FAKE-SECRET-FOR-TESTS-0001'                    # a plain fake value (exact-match scans only)

DATA=hostemu.DATA
WORKER=hostemu.WORKER
WORKER_ID='5e'*32                                   # fixed, so that two worlds differ in their secrets only
def K():return f.load(DIRECTORY)

class K9Host(hostemu.FakeHost):
    """The emulated host of the core, with one difference: the source writes each file from a memoryview of a bytearray
    (so that the bytearray can be zeroed afterwards), which the real os.write accepts and the core's emulation, written
    for create_file's bytes, asserts against. The view is copied here; the bytearray behind it is kept for the tests."""
    def write(self,fd,data):
        assert type(data) is memoryview and type(data.obj) is bytearray and data.contiguous and data.format=='B'
        self.written_from=getattr(self,'written_from',[])+[data.obj]
        return hostemu.FakeHost.write(self,fd,data.tobytes())

def m():return K().m

def world(tokens=None,url_file=None,password_file=None,extra_env=(),names='plain'):
    """(k, host): the host after K4 mode E0 and the activation: the empty secrets directory, the worker holding the
    tokens, the two files of September. names: which of the two names of each token the worker's environment holds,
    'plain' (EODHD_API_TOKEN, ...: what the release's .env.example defines, the default), 'prefixed' (C3PO_...) or
    'both' (the same value under each). Whatever the emulated worker held under these six names before is taken out."""
    k=K();mod=k.m;host=f.world(k);host.__class__=K9Host
    host.tree.add('/var/lib/c3po',uid=0,gid=0,mode=0o700)                 # what K4 mode E0 creates (N-8), with its own signed effect
    host.tree.add(mod.K9_ROOT,uid=0,gid=0,mode=0o700)
    for name in ('tools','days','claims'):host.tree.add(mod.K9_ROOT+'/'+name,uid=0,gid=0,mode=0o700)
    host.tree.add(mod.K9_SECRETS_DIRECTORY,uid=0,gid=0,mode=0o700)
    host.tree.add(mod.RISK_URL_DIRECTORY,uid=1000,gid=1000,mode=0o700)
    host.tree.add(mod.RISK_URL_DIRECTORY+'/'+mod.RISK_URL_NAME,kind='file',uid=1000,gid=1000,mode=0o600,
                  content=(url()+'\n').encode() if url_file is None else url_file)
    host.tree.add(DATA+'/.c3po-role-executor-20260908-r2',uid=1000,gid=1000,mode=0o700)
    host.tree.add(mod.EMITTER_SOURCE_DIRECTORY,uid=1000,gid=1000,mode=0o700)
    host.tree.add(mod.EMITTER_SOURCE_DIRECTORY+'/'+mod.EMITTER_SOURCE_NAME,kind='file',uid=1000,gid=1000,mode=0o600,
                  content=PASSWORD.encode() if password_file is None else password_file)
    values=dict(TOKENS if tokens is None else tokens)
    worker=host.docker.container(WORKER);worker['Id']=WORKER_ID
    env=[item for item in worker['Config']['Env'] if item.split('=',1)[0] not in mod.SECRET_ENVIRONMENT_NAMES]
    for prefixed,plain in mod.PROVIDER_TOKEN_NAMES:
        if names in ('plain','both'):env.append(plain+'='+values[prefixed])
        if names in ('prefixed','both'):env.append(prefixed+'='+values[prefixed])
    worker['Config']['Env']=env+list(extra_env)
    return k,host

def worker_id(host):return host.docker.container(WORKER)['Id']
def source_rows(host):
    """The rows the K9R TREE read gives of the five paths below the data volume: identity, owner, mode, both change
    instants (never the size)."""
    out=[]
    for path in K().m.SOURCE_PATHS:
        node=host.tree.get(path)
        out.append({'path':path,'device':node.dev,'inode':node.ino,'uid':node.uid,'gid':node.gid,'mode':node.mode,'mtime_ns':node.mtime,'ctime_ns':node.ctime})
    return out
def fields(host,**changes):
    mod=K().m
    out={'source_rows':source_rows(host),'secrets_chain':hostemu.rows(host,mod.K9_SECRETS_DIRECTORY),'data_volume_chain':hostemu.rows(host,mod.SOURCE_OPEN_ROOT),'worker_container_id':worker_id(host),'evidence_boot_id_sha256':f.BOOT_SHA}
    out.update(changes);return out

def case(now=None,**options):
    """(docs, host): a bound fixture that completes on a fresh emulated host."""
    k,host=world(**options);return f.Docs(k,fields(host),now=now or NOW),host

def node(host,path):return host.tree.get(path)
def state_of(host):return host.tree.snapshot()

# ---------------------------------------------------------------- what must never leave a run
def provider_content(tokens=None):
    values=TOKENS if tokens is None else tokens
    return ''.join('%s=%s\n'%(name,values[name]) for name in sorted(values)).encode()
def risk_content(value=None):return ('C3PO_R2D2_RISK_DATABASE_URL=%s\n'%(url() if value is None else value)).encode()

def secret_strings(tokens=None,password=PASSWORD,url_password=URL_PASSWORD):
    """Every form of every value a receipt, an argv, an environment or an exception must never hold: the values, the
    lines, the file contents, and their base64, hex, MD5, SHA-1 and SHA-256."""
    values=list((TOKENS if tokens is None else tokens).values())+[url(url_password),password,LITERAL]
    lines=['%s=%s'%item for item in sorted((TOKENS if tokens is None else tokens).items())]+['C3PO_R2D2_RISK_DATABASE_URL='+url(url_password)]
    contents=[provider_content(tokens),risk_content(url(url_password)),password.encode(),(url(url_password)+'\n').encode()]
    out=set(values+lines)
    for raw in [item.encode() for item in values+lines]+contents:
        out.update((base64.b64encode(raw).decode(),raw.hex(),hashlib.md5(raw).hexdigest(),hashlib.sha1(raw).hexdigest(),hashlib.sha256(raw).hexdigest()))
    return out
def substrings(value,shortest=4):
    return {value[start:start+size] for size in range(shortest,len(value)+1) for start in range(len(value)-size+1)}
CANARIES=None
def canaries():
    """The alternating-case secrets (each substring of 4 characters or more) and the URL password."""
    global CANARIES
    if CANARIES is None:
        found=set()
        for value in list(TOKENS.values())+list(LONGER.values())+[URL_PASSWORD,LONGER_URL_PASSWORD,PASSWORD,OTHER_PASSWORD]:found|=substrings(value)
        CANARIES=sorted(found,key=len)
    return CANARIES
def leaks(text,extra=()):
    """Every canary substring, and every whole secret form, that occurs in text (bytes or str)."""
    if type(text) is bytes:text=text.decode('utf-8','replace')
    found=[item for item in canaries() if item in text]
    found+=[item for item in secret_strings()|secret_strings(LONGER,OTHER_PASSWORD,LONGER_URL_PASSWORD)|set(extra) if item in text]
    return found
def line(receipt):return f.line(receipt)

def outside_view(host):
    """What a run hands to the outside besides its receipt: every argv, variable and docker config of every command,
    every environment the docker CLI was given, and every text of the host's log."""
    out=[]
    for entry in host.commands:out.append(json.dumps(entry['argv'])+json.dumps(entry['variables'])+str(entry['docker_config'])+str(entry['stdin']))
    for environment in host.docker.environments:out.append(json.dumps(environment))
    for entry in host.log:out.append(' '.join(str(item) for item in entry if type(item) in (str,int,list,tuple)))
    return '\n'.join(out)

def without_identity(receipt):
    """The receipt with what differs between two worlds (device and inode of what was created, container ids are equal
    by construction) taken out, and its own hash: for the comparison of two runs that differ in the secrets only."""
    value=json.loads(f.line(receipt));value.pop('metadata_sha256',None)
    for row in (value.get('files') or {}).values():
        row['device']=row['inode']=None
    if (value.get('emitter_directory') or {}).get('observed'):value['emitter_directory']['observed']['inode']=None
    return value
