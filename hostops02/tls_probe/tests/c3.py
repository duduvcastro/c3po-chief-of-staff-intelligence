"""Fixtures of C3 (the TLS probe): the plan a binder copies from the read-only receipts, the emulated host as supervisor
operation 2 leaves it (the retention tag on the production image), a model of the line the pinned script prints, and,
for the tests that run the REAL script in a real child interpreter, a throwaway certificate authority made by the
openssl program at test time, a local TLS server, and a test-only prelude.

The prelude is the only thing that makes the real script reach the local server instead of the provider: it is
written IN FRONT of the pinned bytes on the child's standard input, by the test, and it replaces socket.getaddrinfo
for the provider's name and adds the throwaway authority to the context that ssl.create_default_context returns. It is
never part of the source: the source gives the container the pinned bytes alone (tests/test_tls_probe.py checks what
the engine receives). No key is written anywhere but the temporary directory of a test run."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
from datetime import datetime,timezone

import family as f
import hostemu

# The emulated CLI of the frozen core parses the options its family writes and refuses any other (hostemu.RunCall). C3
# adds one, --log-driver, with a value: the emulation is told so here, in the operation's own tests, without a byte of the
# core changing. RunCall reads the module's tuple when it parses, so the value is then kept like --network's.
if '--log-driver' not in hostemu.RUN_VALUES:hostemu.RUN_VALUES=tuple(hostemu.RUN_VALUES)+('--log-driver',)

HERE=Path(__file__).resolve().parent
DIRECTORY=HERE.parent
TAG='c3po/backend:massive-supervisor-epoch03'        # what operation 2 created (the sheet's tag; any name of the grammar)
NOW=datetime(2026,10,4,11,50,tzinfo=timezone.utc)    # inside the band of A1 4.2 C3 (11:45 to 12:30 UTC)
PROVIDER='socket.massive.com'
LEAF='4d'*32                                         # a leaf hash of the model; the real one is the throwaway certificate's
OTHER_NAME='other.invalid'

def K():return f.load(DIRECTORY)
def fields(**changes):
    out={'image_id':hostemu.BACKEND,'image_revision':hostemu.REVISION,'retention_tag':TAG,'script_sha256':K().m.PROBE_SCRIPT_SHA256,
         'evidence_boot_id_sha256':f.BOOT_SHA}
    out.update(changes);return out
def backend(host):return [item for item in host.docker.images if item['Id']==hostemu.BACKEND][0]
def world():
    """The emulated host after supervisor operation 2: its directories, and the retention tag on the production image."""
    k=K();host=f.world(k);hostemu.provision_supervisor(host);backend(host)['RepoTags'].append(TAG);host.docker.on_run=container
    return k,host
def case(now=None,**changes):
    """(docs, host): a bound fixture that completes on a fresh emulated host."""
    k,host=world();return f.Docs(k,fields(**changes),now=now or NOW),host


# ---------------------------------------------------------------- the line, as the script prints it
def empty_line():
    return {'schema':'HOSTOPS02_TLS_PROBE_LINE_V1','host':PROVIDER,'port':443,'context':{'verify_mode_required':True,'check_hostname':True},
            'dns':{'answered':False,'addresses':0,'ipv4':0,'ipv6':0,'code':None,'ms':None},
            'tcp':{'connected':False,'attempts':0,'family':None,'code':None,'ms':None},
            'tls':{'handshake':False,'verified':False,'version':None,'cipher':None,'leaf_sha256':None,'verify_code':None,'code':None,'ms':None},
            'application_bytes_sent':0,'status':None,'total_ms':7}
def model_line(kind='verified'):
    """The line of the script for one way a probe can end, member for member (timings are fixed small numbers).
    tests/test_probe_script.py compares each kind with the line of the real script in the same situation."""
    line=empty_line();dns,tcp,tls=line['dns'],line['tcp'],line['tls']
    if kind=='context':
        line['context']={'verify_mode_required':True,'check_hostname':False};line['status']='TLS_CONTEXT_NOT_VERIFYING';return line
    if kind=='optional':                       # a context that checks the name but does not require a certificate
        line['context']={'verify_mode_required':False,'check_hostname':True};line['status']='TLS_CONTEXT_NOT_VERIFYING';return line
    if kind=='failed':                         # an exception before the context existed: every member as the script began
        line['context']={'verify_mode_required':False,'check_hostname':False};line['status']='PROBE_FAILED';return line
    if kind in ('nxdomain','dns_timeout','dns_failed','no_address'):
        dns.update(ms=1,code={'nxdomain':'DNS_NAME_NOT_RESOLVED','dns_timeout':'DNS_TIMEOUT','dns_failed':'DNS_FAILED','no_address':'DNS_NO_ADDRESS'}[kind])
        line['status']='DNS_NOT_ANSWERED';return line
    dns.update(answered=True,addresses=1,ipv4=1,ms=1)
    if kind in ('refused','tcp_timeout','unreachable'):
        tcp.update(attempts=1,ms=1,code={'refused':'TCP_REFUSED','tcp_timeout':'TCP_TIMEOUT','unreachable':'TCP_UNREACHABLE'}[kind])
        line['status']='TCP_NOT_CONNECTED';return line
    tcp.update(connected=True,attempts=1,family='ipv4',ms=1);tls['ms']=2
    if kind in ('untrusted','other_name'):
        tls.update(code='TLS_CERTIFICATE_NOT_VERIFIED',verify_code=20 if kind=='untrusted' else 62);line['status']='TLS_NOT_VERIFIED';return line
    if kind in ('hang','garbage','reset'):
        tls['code']={'hang':'TLS_HANDSHAKE_TIMEOUT','garbage':'TLS_PROTOCOL_ERROR','reset':'TLS_CONNECTION_ERROR'}[kind]
        line['status']='TLS_HANDSHAKE_FAILED';return line
    assert kind=='verified',kind
    tls.update(handshake=True,verified=True,version='TLSv1.3',cipher='TLS_AES_256_GCM_SHA384',leaf_sha256=LEAF);line['status']='TLS_VERIFIED'
    return line
def line_bytes(row):return (json.dumps(row,sort_keys=True,separators=(',',':'))+'\n').encode()

def assert_probe_run(call,image=hostemu.BACKEND):
    """What the engine was asked for is the probe's run and nothing else: the pinned bytes, the prefix of the core with
    the network bridge, the name of this GO, no bind, no variable, the image by ID, python -I -B -."""
    m=K().m
    assert call.stdin==m.script_bytes() and f.sha(call.stdin)==m.PROBE_SCRIPT_SHA256
    assert call.flags==['--rm','-i','--init','--read-only'] and call.network=='bridge' and call.read_only_root
    assert call.name is not None and call.name.startswith('hostops02-tls-') and len(call.name)==30
    assert call.options=={'--pull':['never'],'--user':['0:0'],'--network':['bridge'],'--cap-drop':['ALL'],'--security-opt':['no-new-privileges'],
                          '--log-driver':['none'],'--name':[call.name]}
    assert call.mounts==[] and call.environment=={} and call.image==image and call.command==['python','-I','-B','-']

def container(call,kind='verified',returncode=0):
    """The emulated container of a correct run."""
    assert_probe_run(call);return returncode,line_bytes(model_line(kind))
def answers(kind='verified',returncode=0,output=None,before=None):
    """An on_run that checks the run and answers one line (or the given bytes); before(call) runs first."""
    def on_run(call):
        assert_probe_run(call)
        if before is not None:before(call)
        return returncode,(line_bytes(model_line(kind)) if output is None else output)
    return on_run


# ---------------------------------------------------------------- the real script, a throwaway authority, a local server
def openssl():
    for candidate in ('/usr/bin/openssl',shutil.which('openssl')):
        if candidate and os.path.isfile(candidate):return candidate
    return None

CONFIG='''[req]
distinguished_name=dn
[dn]
[v3_ca]
basicConstraints=critical,CA:TRUE
keyUsage=critical,keyCertSign,cRLSign
subjectKeyIdentifier=hash
[v3_leaf]
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:%s
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid
'''
def certificates(directory):
    """A throwaway authority and two leaves it signed (the provider's name and another one), made by the openssl
    program in a private directory. Returns {'ca','leaf','leaf_key','other','other_key','leaf_sha256'}; the keys never
    leave that directory."""
    tool=openssl();directory=Path(str(directory));directory.mkdir(parents=True,exist_ok=True);os.chmod(str(directory),0o700)
    def run(*arguments):
        done=subprocess.run([tool]+list(arguments),stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=str(directory),timeout=60)
        assert done.returncode==0,done.stderr.decode()[-500:]
    run('ecparam','-name','prime256v1','-genkey','-noout','-out','ca.key')
    (directory/'ca.cnf').write_text(CONFIG%PROVIDER)
    run('req','-x509','-new','-key','ca.key','-sha256','-days','2','-subj','/CN=hostops02 tls probe test authority','-config','ca.cnf','-extensions','v3_ca','-out','ca.pem')
    for name,host in (('leaf',PROVIDER),('other',OTHER_NAME)):
        (directory/(name+'.cnf')).write_text(CONFIG%host)
        run('ecparam','-name','prime256v1','-genkey','-noout','-out',name+'.key')
        run('req','-new','-key',name+'.key','-subj','/CN='+host,'-config',name+'.cnf','-out',name+'.csr')
        run('x509','-req','-in',name+'.csr','-CA','ca.pem','-CAkey','ca.key','-set_serial','2' if name=='leaf' else '3','-sha256','-days','2',
            '-extfile',name+'.cnf','-extensions','v3_leaf','-out',name+'.pem')
    der=ssl.PEM_cert_to_DER_cert((directory/'leaf.pem').read_text())
    return {'ca':str(directory/'ca.pem'),'leaf':str(directory/'leaf.pem'),'leaf_key':str(directory/'leaf.key'),'other':str(directory/'other.pem'),
            'other_key':str(directory/'other.key'),'leaf_sha256':hashlib.sha256(der).hexdigest()}

LOOPBACK={'ipv4':(socket.AF_INET,'127.0.0.1'),'ipv6':(socket.AF_INET6,'::1')}
def ipv6_loopback():
    """True when a socket can be bound to the IPv6 loopback of this machine."""
    try:
        probe=socket.socket(socket.AF_INET6,socket.SOCK_STREAM)
        try:probe.bind(('::1',0));return True
        finally:probe.close()
    except OSError:return False

class Server:
    """A local TLS server on the loopback (127.0.0.1, or ::1 with family='ipv6') for the real script. Modes: 'good' (the
    provider's leaf), 'tls12' (the provider's leaf, TLS 1.2 only and one suite, ECDHE-ECDSA-AES128-GCM-SHA256: a
    version and a cipher that differ from what a TLS 1.3 default negotiates), 'other_name' (a leaf of another name, same
    authority), 'hang' (accepts and never answers), 'garbage' (answers bytes that are not TLS). Records each connection: the server name the client sent, whether the
    handshake completed, the TLS version and cipher name the SERVER negotiated, and how many application bytes arrived
    after the handshake (read until the client closes)."""
    def __init__(self,certs,mode='good',family='ipv4'):
        kind,address=LOOPBACK[family]
        self.mode=mode;self.connections=[];self.listener=socket.socket(kind,socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);self.listener.bind((address,0));self.listener.listen(8)
        self.port=self.listener.getsockname()[1];self.stopped=False
        self.context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        name='other' if mode=='other_name' else 'leaf';self.context.load_cert_chain(certs[name],certs[name+'_key'])
        if mode=='tls12':
            if ssl.HAS_TLSv1_3:self.context.maximum_version=ssl.TLSVersion.TLSv1_2     # a library without TLS 1.3 offers 1.2 at most anyway
            self.context.set_ciphers(TLS12_CIPHER)
        def sni(connection,server_name,context):self.current['server_name']=server_name
        self.context.sni_callback=sni;self.current={}
        self.thread=threading.Thread(target=self.serve);self.thread.daemon=True;self.thread.start()
    def serve(self):
        while not self.stopped:
            try:connection,_=self.listener.accept()
            except OSError:return
            self.current={'server_name':None,'handshake':False,'application_bytes':None,'version':None,'cipher':None};self.connections.append(self.current)
            try:
                if self.mode=='hang':
                    time.sleep(6);connection.close();continue
                if self.mode=='garbage':
                    connection.sendall(b'HTTP/1.0 400 not tls here\r\n\r\n'*4);time.sleep(0.5);connection.close();continue
                connection.settimeout(5)
                try:tls=self.context.wrap_socket(connection,server_side=True)
                except (ssl.SSLError,OSError):connection.close();continue
                self.current.update(handshake=True,version=tls.version(),cipher=(tls.cipher() or (None,))[0]);received=0
                try:
                    while True:
                        block=tls.recv(4096)
                        if not block:break
                        received+=len(block)
                except (ssl.SSLError,OSError):pass
                self.current['application_bytes']=received;tls.close()
            except Exception:
                try:connection.close()
                except OSError:pass
    def close(self):
        self.stopped=True
        try:self.listener.close()
        except OSError:pass

TLS12_CIPHER='ECDHE-ECDSA-AES128-GCM-SHA256'

def closed_port(family='ipv4'):
    """A port of the loopback (127.0.0.1, or ::1) on which nothing listens (bound, then released)."""
    kind,address=LOOPBACK[family]
    probe=socket.socket(kind,socket.SOCK_STREAM);probe.bind((address,0));port=probe.getsockname()[1];probe.close();return port

PRELUDE='''import socket as _socket, ssl as _ssl, time as _time, errno as _errno
_ADDRESSES=%(addresses)r;_DNS=%(dns)r;_CA=%(ca)r;_VERIFYING=%(verifying)r;_VERIFY_MODE=%(verify_mode)r
_SocketClass=_socket.socket
def _getaddrinfo(host, port, *rest, **named):
    if (host, port) == (%(host)r, 443):
        if _DNS == 'nxdomain':raise _socket.gaierror(_socket.EAI_NONAME, 'test prelude')
        if _DNS == 'failed':raise _socket.gaierror(_socket.EAI_AGAIN, 'test prelude')
        if _DNS == 'raise':raise RuntimeError('test prelude: a resolver error that is not a gaierror')
        if _DNS == 'hang':_time.sleep(%(hang)r)
        family = rest[0] if rest else named.get('family', 0)
        rows = [(_socket.AF_INET6 if ':' in address else _socket.AF_INET, _socket.SOCK_STREAM, 6, '', (address, number) if ':' not in address else (address, number, 0, 0)) for address, number in _ADDRESSES]
        return [row for row in rows if family in (0, _socket.AF_UNSPEC) or row[0] == family]
    raise _socket.gaierror(_socket.EAI_NONAME, 'test prelude: no name but the provider on 443 resolves, and never through the network')
_socket.getaddrinfo=_getaddrinfo
_real_context=_ssl.create_default_context
def _context(*rest, **named):
    context=_real_context(*rest, **named)
    if _CA:context.load_verify_locations(cafile=_CA)
    if not _VERIFYING:context.check_hostname=False
    if _VERIFY_MODE == 'optional':context.verify_mode=_ssl.CERT_OPTIONAL
    return context
_ssl.create_default_context=_context
if %(connect)r == 'slow':
    _real_connect=_SocketClass.connect
    _first=[True]
    def _connect(self, address):
        if _first[0]:
            _first[0]=False
            _time.sleep(3.0)
        return _real_connect(self, address)
    _SocketClass.connect=_connect
if %(connect)r == 'hang':
    def _connect(self, address):
        limit=self.gettimeout()
        _time.sleep(30 if limit is None else limit)
        raise _socket.timeout('test prelude')
    _SocketClass.connect=_connect
if %(no_ipv6_socket)r:
    def _socket_of(family=-1, *rest, **named):
        if family == _socket.AF_INET6:raise OSError(_errno.EAFNOSUPPORT, 'test prelude: a kernel without IPv6')
        return _SocketClass(family, *rest, **named)
    _socket.socket=_socket_of
if %(fail)r:
    def _broken(*rest, **named):raise RuntimeError('test prelude')
    _ssl.create_default_context=_broken
'''
def prelude(addresses,ca=None,dns='answer',verifying=True,hang=30,connect='normal',fail=False,verify_mode='required',no_ipv6_socket=False):
    """The test-only lines written in front of the pinned script: the provider's name answers the given (address,
    port) pairs (only those of the family asked for, when one is), and the context of the default verifying kind also
    trusts the throwaway authority. Test situations: a resolver that hangs (dns='hang') or fails with an error that is
    not a gaierror (dns='raise'), a connect that never completes within its timeout (connect='hang') or whose first
    attempt takes three seconds (connect='slow'), a context that does not check the name (verifying=False) or does not
    require a certificate (verify_mode='optional'), a kernel without IPv6 sockets (no_ipv6_socket=True), an exception
    inside the script (fail=True)."""
    return (PRELUDE%{'addresses':[list(item) for item in addresses],'dns':dns,'ca':ca,'verifying':verifying,'host':PROVIDER,'hang':hang,
                     'connect':connect,'fail':fail,'verify_mode':verify_mode,'no_ipv6_socket':no_ipv6_socket}).encode()

def run_script(stdin,timeout=40):
    """The bytes under `python -I -B -` in a child of the interpreter that runs the tests, as the container runs them."""
    started=time.monotonic()
    done=subprocess.run([sys.executable,'-I','-B','-'],input=stdin,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={'PATH':'/usr/bin:/bin'},timeout=timeout)
    return done.returncode,done.stdout,done.stderr,time.monotonic()-started


# ---------------------------------------------------------------- the release, when a tree of it is at hand
RELEASE='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
RELEASE_FILES={'c3po/deployment/massive-supervisor/README.md':'644c6211c7351de1dfd17d880842deaf4d5e5b34ea63d23a274c5f4e463461c5',
               'c3po/backend/app/r2d2_v2_massive_transport.py':'2ff62bb69a6868a168f67ec7436e02753cc3b3c62196107d892fc7e490a4dc5b',
               'c3po/backend/Dockerfile':'508636d0bb9cbc81076dfcfeb49cab03f1762c613b740d4a7391faf1a26e8ebf'}
def release_tree():
    """A directory that holds the files of the release this operation is frozen against (each compared by hash), or
    None. Looked for in HOSTOPS02_TEST_RELEASE_TREE, in work/release of this operation directory (an extraction made
    with `git archive dd4ec4bb`), and in the directories above it (a checkout of the release that holds this one)."""
    candidates=[Path(os.environ['HOSTOPS02_TEST_RELEASE_TREE'])] if os.environ.get('HOSTOPS02_TEST_RELEASE_TREE') else []
    candidates+=[DIRECTORY/'work'/'release']+list(DIRECTORY.parents)[:6]
    for candidate in candidates:
        try:
            if all(f.sha((candidate/name).read_bytes())==pin for name,pin in RELEASE_FILES.items()):return candidate.resolve()
        except OSError:continue
    return None
