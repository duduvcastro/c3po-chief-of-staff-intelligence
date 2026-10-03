OPERATION='GO_READONLY_HOSTOPS02_TLS_PROBE_01'
PHASE='READONLY_SUPERVISOR_TLS_PROBE'
REQUEST_SCHEMA='READONLY_HOSTOPS02_TLS_PROBE_REQUEST_V1'
AUTHORITY_SCHEMA='READONLY_HOSTOPS02_TLS_PROBE_AUTHORITY_V1'
GO_SCHEMA='READONLY_HOSTOPS02_TLS_PROBE_GO_V1'
RECEIPT_SCHEMA='READONLY_HOSTOPS02_TLS_PROBE_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_TLS_PROBE_PLAN_V1'
SOURCE_NAME='tls_probe.py'
# The core's classes decide the name. The container this source starts writes to no host path (no bind at all), so its
# row is of kind CONTAINER, which a reading source may carry (CORE.md section 8, rule 1); a source that writes nothing is
# READ and named GO_READONLY_... (assemble.py refuses any other pairing). That class says nothing about the signature:
# the weekend authority (A1 rev 2, section 4.2, row C3) keeps this run under the owner's individual signature by hash.
WRITES_ALLOWED=False
ACTIVATION_ALLOWED=False
DATE_CLASS='READ'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
# The image ID is read on the host by the precheck (README line 281: read after the deploy); the retention tag that
# must name that ID is the one supervisor operation 2 created (hostops01 provision, ledger of the tag).
PROVISION_OPERATION='GO_WRITE_SUPERVISOR_READER_PROVISION_01'
EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,PROVISION_OPERATION)
# A1 section 5: the GO of an operation of its section 4 has a short window of at most 900 seconds inside the band.
MAX_GATE_SPAN_SECONDS=900
# A1 rev 2 (sha256 909573aa7431c5340711716fa0702e2d3dde58cbbe10b9b68da0fcca109e95ba), section 4.2, row C3: Sunday
# 04/10, 08:45 to 09:30 BRT, before the installation of the units (E3). The class READ allows nine days; this source
# narrows them to that one band, checked on the signed window in validate_plan, so at both layers (the dispatcher runs
# authenticate() before any claim). Saturday is not allowed: the authority gives C3 no band that day, its reserves are
# for reads only, and its section 5 never changes the day of a request.
PROBE_DAY='2026-10-04'
PROBE_BAND=('2026-10-04T11:45:00+00:00','2026-10-04T12:30:00+00:00')
COMPLETE_OUTCOME='TLS_VERIFIED_TO_THE_PROVIDER_HOST'
VERIFIED_WITH_FINDINGS_OUTCOME='TLS_VERIFIED_WITH_FINDINGS'
NOT_VERIFIED_OUTCOME='PROBE_RAN_TLS_NOT_VERIFIED'
PARTIAL_OUTCOME='PARTIAL_PROBE_RESULT_UNKNOWN'
REFUSED_OUTCOME='REFUSED_NO_CONTAINER_STARTED'
REDUCED_OUTCOME='RECEIPT_REDUCED_PROBE_NOT_COMPLETE'
ESCAPED_OUTCOME='PARTIAL_STATE_UNKNOWN_CONTAINER_MAY_REMAIN'
PLAN_KEYS=frozenset(('image_id','image_revision','retention_tag','script_sha256','evidence_boot_id_sha256'))
# The release whose image is in production (main at dd4ec4bb), and the grammar of the retention tag of supervisor
# operation 2 (hostops01 rev 3, provision/provision_dirs.py lines 632 and 633: REPOSITORY and TAG).
RELEASE_REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
RETENTION_TAG='c3po/backend:massive-supervisor-[a-z0-9][a-z0-9.-]{0,40}'
# The provider host and port the supervisor connects to, from the release code, never typed: the transport opens
# wss://socket.massive.com/stocks (c3po/backend/app/r2d2_v2_massive_transport.py line 99 at dd4ec4bb) with no port in
# the URI, so the port is the wss default 443 (the websockets client: uri.py, "443 if secure"); the README's rehearsal
# item 2 names the same pair (c3po/deployment/massive-supervisor/README.md line 580).
PROVIDER_HOST='socket.massive.com'
PROVIDER_PORT=443
PROVIDER_SOURCE=('c3po/backend/app/r2d2_v2_massive_transport.py:99 (wss://socket.massive.com/stocks, wss default port 443) and '
                 'c3po/deployment/massive-supervisor/README.md:580 at dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858')
CONTAINER_PREFIX='hostops02-tls-'
PROBE_COMMAND=['python','-I','-B','-']
PROBE_NETWORK='bridge'
# The core's RUN_PREFIX (the README's catalog argv) with one word changed: the network is bridge, the network of the
# owner's sheet (line 7) for the unit, instead of none. Same options, nothing added: removed on exit, standard input
# attached, never a pull, an init process, uid 0, read-only root filesystem, no capability, no new privilege.
PROBE_PREFIX=['run','--rm','-i','--pull','never','--init','--user','0:0','--network',PROBE_NETWORK,'--read-only','--cap-drop','ALL',
              '--security-opt','no-new-privileges']
# Seconds of the script (constants of its text, compared by a test): each step bounded, the whole ended by the
# kernel at ALARM, before the 20 s of the class RUN_SHORT at which the docker CLI is killed.
PROBE_SECONDS={'dns':4,'connect':4,'handshake':4,'alarm':14}
PROBE_ALARM_STATUS=142                        # 128 + SIGALRM, as docker-init reports a child the alarm killed
# The pinned probe script, given to the container on standard input and nothing else. Its bytes are part of this
# signed source; the SHA-256 and the size below are compared before anything is looked at.
PROBE_SCRIPT=r'''import signal
signal.alarm(14)
import hashlib, json, os, socket, ssl, sys, threading, time
# HOSTOPS02 C3, the TLS probe of supervisor rehearsal item 2. It resolves the provider host, opens ONE TCP connection
# and makes ONE TLS handshake with the default verifying context, then closes. It sends no application byte, no HTTP
# request and no credential, and it prints one JSON line of counts, booleans, constant codes, a hash and timings.
HOST = 'socket.massive.com'
PORT = 443
DNS_SECONDS = 4.0
CONNECT_SECONDS = 4.0
HANDSHAKE_SECONDS = 4.0
MAX_ADDRESSES = 16
NOT_FOUND = tuple(getattr(socket, name) for name in ('EAI_NONAME', 'EAI_NODATA') if hasattr(socket, name))
started = time.monotonic()
line = {'schema': 'HOSTOPS02_TLS_PROBE_LINE_V1', 'host': HOST, 'port': PORT,
        'context': {'verify_mode_required': False, 'check_hostname': False},
        'dns': {'answered': False, 'addresses': 0, 'ipv4': 0, 'ipv6': 0, 'code': None, 'ms': None},
        'tcp': {'connected': False, 'attempts': 0, 'family': None, 'code': None, 'ms': None},
        'tls': {'handshake': False, 'verified': False, 'version': None, 'cipher': None, 'leaf_sha256': None,
                'verify_code': None, 'code': None, 'ms': None},
        'application_bytes_sent': 0, 'status': None, 'total_ms': None}


def elapsed(since):
    return int((time.monotonic() - since) * 1000)


def finish(status):
    line['status'] = status
    line['total_ms'] = elapsed(started)
    sys.stdout.write(json.dumps(line, sort_keys=True, separators=(',', ':')) + '\n')
    sys.stdout.flush()
    os._exit(0)


def probe():
    context = ssl.create_default_context()
    line['context'] = {'verify_mode_required': context.verify_mode == ssl.CERT_REQUIRED,
                       'check_hostname': context.check_hostname is True}
    if not (line['context']['verify_mode_required'] and line['context']['check_hostname']):
        finish('TLS_CONTEXT_NOT_VERIFYING')
    found = {}

    def resolve():
        try:
            found['rows'] = socket.getaddrinfo(HOST, PORT, 0, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        except socket.gaierror as error:
            found['code'] = 'DNS_NAME_NOT_RESOLVED' if error.errno in NOT_FOUND else 'DNS_FAILED'
        except Exception:
            found['code'] = 'DNS_FAILED'

    began = time.monotonic()
    worker = threading.Thread(target=resolve)
    worker.daemon = True
    worker.start()
    worker.join(DNS_SECONDS)
    line['dns']['ms'] = elapsed(began)
    if worker.is_alive():
        line['dns']['code'] = 'DNS_TIMEOUT'
        finish('DNS_NOT_ANSWERED')
    if 'rows' not in found:
        line['dns']['code'] = found.get('code', 'DNS_FAILED')
        finish('DNS_NOT_ANSWERED')
    addresses = []
    for family, _, _, _, address in found['rows']:
        if family in (socket.AF_INET, socket.AF_INET6) and (family, address) not in addresses:
            addresses.append((family, address))
    addresses = addresses[:MAX_ADDRESSES]
    line['dns']['addresses'] = len(addresses)
    line['dns']['ipv4'] = len([item for item in addresses if item[0] == socket.AF_INET])
    line['dns']['ipv6'] = len([item for item in addresses if item[0] == socket.AF_INET6])
    if not addresses:
        line['dns']['code'] = 'DNS_NO_ADDRESS'
        finish('DNS_NOT_ANSWERED')
    line['dns']['answered'] = True
    began = time.monotonic()
    deadline = began + CONNECT_SECONDS
    connection = None
    code = None
    for family, address in addresses:
        left = deadline - time.monotonic()
        if left <= 0:
            break
        line['tcp']['attempts'] += 1
        candidate = socket.socket(family, socket.SOCK_STREAM)
        candidate.settimeout(left)
        try:
            candidate.connect(address)
        except socket.timeout:
            code = 'TCP_TIMEOUT'
        except ConnectionRefusedError:
            code = 'TCP_REFUSED'
        except OSError:
            code = 'TCP_UNREACHABLE'
        else:
            connection = candidate
            line['tcp']['family'] = 'ipv4' if family == socket.AF_INET else 'ipv6'
            break
        candidate.close()
    line['tcp']['ms'] = elapsed(began)
    if connection is None:
        line['tcp']['code'] = code or 'TCP_TIMEOUT'
        finish('TCP_NOT_CONNECTED')
    line['tcp']['connected'] = True
    began = time.monotonic()
    connection.settimeout(HANDSHAKE_SECONDS)
    try:
        tls = context.wrap_socket(connection, server_hostname=HOST, do_handshake_on_connect=False)
        tls.do_handshake()
    except ssl.SSLCertVerificationError as error:
        line['tls']['ms'] = elapsed(began)
        line['tls']['code'] = 'TLS_CERTIFICATE_NOT_VERIFIED'
        number = getattr(error, 'verify_code', None)
        line['tls']['verify_code'] = number if type(number) is int and 0 <= number <= 1000 else None
        finish('TLS_NOT_VERIFIED')
    except socket.timeout:
        line['tls']['ms'] = elapsed(began)
        line['tls']['code'] = 'TLS_HANDSHAKE_TIMEOUT'
        finish('TLS_HANDSHAKE_FAILED')
    except ssl.SSLError:
        line['tls']['ms'] = elapsed(began)
        line['tls']['code'] = 'TLS_PROTOCOL_ERROR'
        finish('TLS_HANDSHAKE_FAILED')
    except OSError:
        line['tls']['ms'] = elapsed(began)
        line['tls']['code'] = 'TLS_CONNECTION_ERROR'
        finish('TLS_HANDSHAKE_FAILED')
    line['tls']['ms'] = elapsed(began)
    leaf = tls.getpeercert(binary_form=True)
    cipher = tls.cipher()
    line['tls'].update(handshake=True, verified=True, version=tls.version(), cipher=cipher[0] if cipher else None,
                       leaf_sha256=hashlib.sha256(leaf).hexdigest() if leaf else None)
    tls.close()
    finish('TLS_VERIFIED')


try:
    probe()
except Exception:
    finish('PROBE_FAILED')
'''
PROBE_SCRIPT_SHA256='d625d84f41bdf91396211025afbb80afa0a42e960bc1a19cb9e95428c0619566'
PROBE_SCRIPT_BYTES=5746
# The one line the script prints, member by member. A line is copied into the receipt only after every member was
# checked against this grammar and the members agree with its status; otherwise only its size and hash are kept.
LINE_SCHEMA='HOSTOPS02_TLS_PROBE_LINE_V1'
LINE_KEYS=frozenset(('schema','host','port','context','dns','tcp','tls','application_bytes_sent','status','total_ms'))
LINE_CONTEXT_KEYS=frozenset(('verify_mode_required','check_hostname'))
LINE_DNS_KEYS=frozenset(('answered','addresses','ipv4','ipv6','code','ms'))
LINE_TCP_KEYS=frozenset(('connected','attempts','family','code','ms'))
LINE_TLS_KEYS=frozenset(('handshake','verified','version','cipher','leaf_sha256','verify_code','code','ms'))
LINE_STATUSES=('TLS_VERIFIED','DNS_NOT_ANSWERED','TCP_NOT_CONNECTED','TLS_NOT_VERIFIED','TLS_HANDSHAKE_FAILED','TLS_CONTEXT_NOT_VERIFYING','PROBE_FAILED')
DNS_CODES=('DNS_TIMEOUT','DNS_NAME_NOT_RESOLVED','DNS_FAILED','DNS_NO_ADDRESS')
TCP_CODES=('TCP_TIMEOUT','TCP_REFUSED','TCP_UNREACHABLE')
TLS_CODES=('TLS_CERTIFICATE_NOT_VERIFIED','TLS_HANDSHAKE_TIMEOUT','TLS_PROTOCOL_ERROR','TLS_CONNECTION_ERROR')
TLS_VERSIONS=('TLSv1.2','TLSv1.3')
CIPHER_NAME='[A-Z0-9][A-Z0-9_-]{0,63}'
MAX_ADDRESSES_COUNTED=16
MAX_LINE_MILLISECONDS=60000
MAX_VERIFY_CODE=1000
MAX_NEW_CONTAINER_ROWS=8
RUN_ROW='probe'
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'the signed image ID, then the signed retention tag','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          RUN_ROW:command_row('docker',PROBE_PREFIX,'--name hostops02-tls-<16 hex of the GO>, the signed image ID, python -I -B -; '
                              'the pinned probe script on standard input; no bind','RUN_SHORT','CONTAINER',stdin=True)}
SCOPE_STATEMENT=('Rehearsal item 2 of the supervisor README at dd4ec4bb: a TLS connection to socket.massive.com:443 from the network '
                 'bridge, without a token, before the supervisor units are installed. Starts one attached container of the signed image '
                 'ID (the production backend image by its local ID, with the release revision label and the signed retention tag) on the '
                 'network bridge: removed on exit, never a pull, an init process, uid 0, read-only root filesystem, no capability, no bind, '
                 'no environment file, no DOCKER_CONFIG and no token. Its standard input is the probe script whose SHA-256 is pinned in '
                 'this source: it resolves socket.massive.com, opens one TCP connection to port 443 and makes one TLS handshake with the '
                 'default verifying context for that host name, then closes; it sends no application byte and no HTTP request. The '
                 'receipt holds counts, booleans, constant codes, the SHA-256 of the leaf certificate, the TLS version and cipher names '
                 'and timings, never an address. Nothing on the filesystem of the host is created, changed or removed; no unit is '
                 'touched; no container is removed by this process; a timeout stops the docker CLI, not the container. Success is one '
                 'outcome: TLS verified to the provider host and the container gone.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'after_effect_reserve_seconds':AFTER_EFFECT_RESERVE_SECONDS,
       'band':{'day':PROBE_DAY,'not_before':PROBE_BAND[0],'not_after':PROBE_BAND[1],
               'source':'A1 rev 2 (909573aa7431c5340711716fa0702e2d3dde58cbbe10b9b68da0fcca109e95ba), section 4.2, row C3'},
       'provider':{'host':PROVIDER_HOST,'port':PROVIDER_PORT,'source':PROVIDER_SOURCE},
       'container':{'prefix':PROBE_PREFIX,'name':CONTAINER_PREFIX+'<first 16 hex of the GO sha256>','command':PROBE_COMMAND,
                    'network':PROBE_NETWORK,'binds':[],'environment_file':None,'docker_config':None,'token':None},
       'script':{'sha256':PROBE_SCRIPT_SHA256,'bytes':PROBE_SCRIPT_BYTES,'carried_in_this_source':True,'seconds':PROBE_SECONDS,
                 'exit_status_of_its_alarm':PROBE_ALARM_STATUS,'context':'ssl.create_default_context(), server name '+PROVIDER_HOST,
                 'sends':'the TCP and TLS handshake only; no application byte, no HTTP request, no credential'},
       'line':{'schema':LINE_SCHEMA,'statuses':list(LINE_STATUSES),'dns_codes':list(DNS_CODES),'tcp_codes':list(TCP_CODES),
               'tls_codes':list(TLS_CODES),'tls_versions':list(TLS_VERSIONS),'cipher':CIPHER_NAME},
       'image':{'revision':RELEASE_REVISION,'retention_tag':RETENTION_TAG},
       'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'file_contents_read':[BOOT_ID_PATH],
       'side_effects':['one attached docker run --rm: the engine creates a container named '+CONTAINER_PREFIX+'<first 16 hex of the GO sha256>, '
                       'attaches it to the network bridge and removes it when its process ends; it writes the output of the container to its log '
                       'driver, removed with the container',
                       'the container asks the DNS servers the engine gives the network bridge for socket.massive.com, opens one TCP connection '
                       'to port 443 of one of the answers and makes one TLS handshake (ClientHello with the server name socket.massive.com): '
                       'the provider sees a connection without any credential from the public address of the host',
                       'the script arms a 14 s alarm as its first statement, so its process ends by itself before the 20 s limit of the docker '
                       'CLI; a run whose CLI is killed first may leave the container to the engine until its process ends, and the receipt says '
                       'whether one of that name is listed; a container created and never started stays in the state created, and no source '
                       'of this family removes a container',
                       'the docker CLI runs with the fixed environment of the core and no DOCKER_CONFIG: it reads the configuration of root, as '
                       'the precheck of this family did'],
       'never':['a bind or mount of any host path','an environment file or a variable given to the container','the token or any path of '
                '/etc/c3po-bar','an HTTP request or any application byte to the provider','a second connection or a retry','docker exec',
                'a shell','systemctl','a pull','a network other than bridge','--privileged, a device or a capability',
                'the removal of any container','any write on the filesystem of the host','an address in the receipt'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'addresses_counted':MAX_ADDRESSES_COUNTED,'line_milliseconds':MAX_LINE_MILLISECONDS,'new_container_rows':MAX_NEW_CONTAINER_ROWS}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner):
    """Everything this source can do to the host: the read primitives and the three signed commands."""


def script_bytes():
    """The pinned probe script, from the constant this source carries. Nothing else is ever given to the container."""
    raw=PROBE_SCRIPT.encode('ascii')
    need(len(raw)==PROBE_SCRIPT_BYTES and sha(raw)==PROBE_SCRIPT_SHA256,'SCRIPT_NOT_THE_PINNED_HASH');return raw

def container_name(bound):
    """The name the engine gives the container: the prefix and the first 16 hex of the GO hash (one name per GO)."""
    return CONTAINER_PREFIX+bound['go_sha256'][:16]

def validate_window(window):
    """The signed window lies in the band of the authority: the one day, from 11:45 to 12:30 UTC."""
    start,end=instant(window['not_before']),instant(window['expires_at'])
    need(start.date().isoformat()==PROBE_DAY,'PROBE_DAY_NOT_IN_SCOPE')
    need(instant(PROBE_BAND[0])<=start and end<=instant(PROBE_BAND[1]),'PROBE_WINDOW_OUTSIDE_THE_BAND')

def validate_members(plan):
    """Every member of the plan but the window: refused from the bytes, before any claim."""
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    need(type(plan['script_sha256']) is str and plan['script_sha256']==PROBE_SCRIPT_SHA256,'SCRIPT_NOT_THE_PINNED_HASH');script_bytes()
    need(type(plan['image_revision']) is str and plan['image_revision']==RELEASE_REVISION,'IMAGE_REVISION_NOT_THE_RELEASE')
    need(text(plan['retention_tag'],RETENTION_TAG),'RETENTION_TAG_INVALID')
    run_arguments(RUN_ROW,plan['image_id'],[],PROBE_COMMAND,CONTAINER_PREFIX+'0'*16)

def validate_plan(plan):
    validate_window(plan['window'])
    validate_members(plan)

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    return {'operation':OPERATION,
            'container':{'image_id':plan['image_id'],'image_revision':plan['image_revision'],'retention_tag':plan['retention_tag'],
                         'docker_arguments':PROBE_PREFIX+['--name',CONTAINER_PREFIX+'<first 16 hex of the GO sha256>',plan['image_id']]+PROBE_COMMAND,
                         'network':PROBE_NETWORK,'binds':[],'environment_file':None,'docker_config_variable':None,'token':None,
                         'standard_input':{'sha256':PROBE_SCRIPT_SHA256,'bytes':PROBE_SCRIPT_BYTES},
                         'time_limit_seconds':COMMAND_CLASSES[COMMANDS[RUN_ROW]['class']]['seconds'],'alarm_seconds':PROBE_SECONDS['alarm'],
                         'removed_by_the_engine':True},
            'provider':{'host':PROVIDER_HOST,'port':PROVIDER_PORT,'source':PROVIDER_SOURCE,'connections':1,'tls_handshakes':1,
                        'application_bytes':0,'http_request':False,'credential':False},
            'probe_seconds':PROBE_SECONDS,
            'band':{'day':PROBE_DAY,'not_before':PROBE_BAND[0],'not_after':PROBE_BAND[1]},
            'success_outcome':success_of(plan),'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'writes':0,'removes':[],'activation':False,'containers_run':1}
def success_of(plan):return COMPLETE_OUTCOME


def line_grammar(row):
    """True when the printed object is exactly what the script prints: every member of its type and range, and the
    members in agreement with its status. Pure; never raises for a dict."""
    def flag(value):return type(value) is bool
    def milliseconds(value):return value is None or integer(value,0,MAX_LINE_MILLISECONDS)
    def code(value,codes):return value is None or (type(value) is str and value in codes)
    if not (set(row)==LINE_KEYS and row['schema']==LINE_SCHEMA and row['host']==PROVIDER_HOST and type(row['port']) is int
            and row['port']==PROVIDER_PORT and type(row['application_bytes_sent']) is int and row['application_bytes_sent']==0
            and type(row['status']) is str and row['status'] in LINE_STATUSES and integer(row['total_ms'],0,MAX_LINE_MILLISECONDS)):return False
    context,dns,tcp,tls=row['context'],row['dns'],row['tcp'],row['tls']
    if not (type(context) is dict and set(context)==LINE_CONTEXT_KEYS and flag(context['verify_mode_required']) and flag(context['check_hostname'])):return False
    if not (type(dns) is dict and set(dns)==LINE_DNS_KEYS and flag(dns['answered']) and integer(dns['addresses'],0,MAX_ADDRESSES_COUNTED)
            and integer(dns['ipv4'],0,MAX_ADDRESSES_COUNTED) and integer(dns['ipv6'],0,MAX_ADDRESSES_COUNTED)
            and dns['ipv4']+dns['ipv6']==dns['addresses'] and code(dns['code'],DNS_CODES) and milliseconds(dns['ms'])):return False
    if not (type(tcp) is dict and set(tcp)==LINE_TCP_KEYS and flag(tcp['connected']) and integer(tcp['attempts'],0,MAX_ADDRESSES_COUNTED)
            and tcp['attempts']<=dns['addresses'] and (tcp['family'] is None or tcp['family'] in ('ipv4','ipv6'))
            and code(tcp['code'],TCP_CODES) and milliseconds(tcp['ms'])):return False
    if not (type(tls) is dict and set(tls)==LINE_TLS_KEYS and flag(tls['handshake']) and flag(tls['verified'])
            and (tls['version'] is None or (type(tls['version']) is str and tls['version'] in TLS_VERSIONS))
            and (tls['cipher'] is None or text(tls['cipher'],CIPHER_NAME)) and (tls['leaf_sha256'] is None or hexpin(tls['leaf_sha256']))
            and (tls['verify_code'] is None or integer(tls['verify_code'],0,MAX_VERIFY_CODE)) and code(tls['code'],TLS_CODES)
            and milliseconds(tls['ms'])):return False
    verifying=context['verify_mode_required'] and context['check_hostname']
    nothing_after_dns=not tcp['connected'] and tcp['attempts']==0 and tcp['family'] is None and tcp['code'] is None
    no_handshake=not tls['handshake'] and not tls['verified'] and tls['version'] is None and tls['cipher'] is None and tls['leaf_sha256'] is None
    untouched_tls=no_handshake and tls['code'] is None and tls['verify_code'] is None
    answered=dns['answered'] and dns['addresses']>=1 and dns['code'] is None
    connected=tcp['connected'] and tcp['attempts']>=1 and tcp['family'] is not None and tcp['code'] is None
    status=row['status']
    if status=='TLS_VERIFIED':
        return (verifying and answered and connected and tls['handshake'] and tls['verified'] and tls['version'] is not None
                and tls['cipher'] is not None and tls['leaf_sha256'] is not None and tls['code'] is None and tls['verify_code'] is None)
    if status=='DNS_NOT_ANSWERED':return verifying and not dns['answered'] and dns['code'] is not None and nothing_after_dns and untouched_tls
    if status=='TCP_NOT_CONNECTED':
        return verifying and answered and not tcp['connected'] and tcp['family'] is None and tcp['code'] is not None and untouched_tls
    if status=='TLS_NOT_VERIFIED':return verifying and answered and connected and no_handshake and tls['code']=='TLS_CERTIFICATE_NOT_VERIFIED'
    if status=='TLS_HANDSHAKE_FAILED':
        return (verifying and answered and connected and no_handshake and tls['code'] in TLS_CODES and tls['code']!='TLS_CERTIFICATE_NOT_VERIFIED'
                and tls['verify_code'] is None)
    if status=='TLS_CONTEXT_NOT_VERIFYING':return not verifying and not dns['answered'] and dns['code'] is None and nothing_after_dns and untouched_tls
    return True                                                       # PROBE_FAILED: the script's own catch-all, members as they were

def probe_line(result):
    """What the container printed, reduced to what may leave this process. Every member of a line that meets the
    grammar is copied (counts, booleans, constant codes, the TLS version and cipher names, a hash, timings); of any other
    output only its size and hash are kept, never a byte of it."""
    output=result['output'] if type(result.get('output')) is bytes else b''
    out={'returncode':result['returncode'],'bytes':len(output),'sha256':sha(output) if output else None,'one_json_line':False,'valid':False,
         'status':None,'context':None,'dns':None,'tcp':None,'tls':None,'application_bytes_sent':None,'total_ms':None}
    try:row=single_line(output)
    except Refused:return out
    out['one_json_line']=True
    if not line_grammar(row):return out
    out.update(valid=True,status=row['status'],context=dict(row['context']),dns=dict(row['dns']),tcp=dict(row['tcp']),tls=dict(row['tls']),
               application_bytes_sent=row['application_bytes_sent'],total_ms=row['total_ms'])
    return out

def probe_code(probe):
    """The constant code of a valid line that is not a verified TLS: the step that failed, else the status."""
    return probe['dns']['code'] or probe['tcp']['code'] or probe['tls']['code'] or probe['status']

def run_verdict(result,probe,after):
    """(status, outcome, code) once the container was started. A verified TLS that left anything behind, or whose CLI
    reported one of docker's own statuses, is a finding beside the verified line; a valid line that is not a verified TLS
    is the probe's own answer; anything else leaves the result unknown."""
    if not result['returned']:return PARTIAL_STATUS,PARTIAL_OUTCOME,result['code'] or 'COMMAND_FAILED'
    engine=result['returncode'] in RUN_ENGINE_STATUSES
    if not probe['valid']:
        if engine:code='ENGINE_COULD_NOT_RUN_THE_CONTAINER'
        elif result['returncode']==PROBE_ALARM_STATUS:code='PROBE_ENDED_BY_ITS_ALARM'
        elif not probe['one_json_line']:code='PROBE_OUTPUT_NOT_ONE_LINE'
        else:code='PROBE_LINE_NOT_AS_SPECIFIED'
        return PARTIAL_STATUS,PARTIAL_OUTCOME,code
    if result['returncode']!=0 and not engine:return PARTIAL_STATUS,PARTIAL_OUTCOME,'PROBE_EXIT_STATUS_NOT_ZERO'
    if probe['status']!='TLS_VERIFIED':return PARTIAL_STATUS,NOT_VERIFIED_OUTCOME,probe_code(probe)
    if engine:return PARTIAL_STATUS,VERIFIED_WITH_FINDINGS_OUTCOME,'ENGINE_STATUS_AFTER_A_VERIFIED_PROBE'
    if after['status']!='COMPLETE':return PARTIAL_STATUS,VERIFIED_WITH_FINDINGS_OUTCOME,'CONTAINER_LISTING_UNAVAILABLE_AFTER_RUN'
    if after['name_present']:return PARTIAL_STATUS,VERIFIED_WITH_FINDINGS_OUTCOME,'CONTAINER_OF_THE_PROBE_STILL_LISTED'
    if after['not_there_before']:return PARTIAL_STATUS,VERIFIED_WITH_FINDINGS_OUTCOME,'CONTAINER_PRESENT_THAT_WAS_NOT_THERE_BEFORE'
    return COMPLETE_STATUS,COMPLETE_OUTCOME,None

REDUCTIONS=[]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    script=script_bytes();name=container_name(bound)                                     # pure
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    commands=Commands(host,gate)
    precheck={'image':None,'retention_tag':None,'containers_before':None,'name_free':None}
    facts={'container':None,'probe':None,'containers_after':None}
    def finish(status,outcome,code,phase):
        probe,after=facts['probe'],facts['containers_after']
        verified=probe is not None and probe['valid'] and probe['status']=='TLS_VERIFIED'
        removed=None if after is None or after['status']!='COMPLETE' else (not after['name_present'] and after['not_there_before']==0)
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),
            clock=timing(begun,mark,clock,monotonic),commands_started=dict(commands.started),mutating_calls=state.counts(),
            precheck=precheck,container=facts['container'],probe=probe,containers_after=after,tls_verified=verified,container_removed=removed,
            writes=0,containers_run=commands.started['CONTAINER'],phase_reached=phase)))
    # ---- everything is looked at before the container is started: a refusal up to here has started nothing
    try:
        need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
        need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
        try:image=image_facts(commands,plan['image_id'])
        except CommandFailed:raise Refused('IMAGE_ABSENT_OR_UNREADABLE') from None
        need(image['id']==plan['image_id'],'IMAGE_ID_MISMATCH')
        need(image['revision_label']==plan['image_revision'],'IMAGE_REVISION_MISMATCH')
        precheck['image']={'id_as_signed':True,'revision_as_signed':True}
        try:tagged=image_facts(commands,plan['retention_tag'])
        except CommandFailed:raise Refused('RETENTION_TAG_ABSENT_OR_UNREADABLE') from None
        need(tagged['id']==plan['image_id'] and tagged['reference_among_repo_tags'],'RETENTION_TAG_NOT_ON_THE_SIGNED_IMAGE')
        precheck['retention_tag']={'resolves_to_the_signed_image':True}
        try:before=container_list(commands)
        except CommandFailed:raise Refused('CONTAINER_LISTING_FAILED') from None
        precheck['containers_before']=len(before)
        precheck['name_free']=not any(row['name']==name for row in before)
        need(precheck['name_free'],'CONTAINER_NAME_TAKEN')
        # The last refusal that costs nothing: the whole class of the run and the reserve for the listing after it.
        need(gate()>=effects_budget(RUN_ROW),'BUDGET_INSUFFICIENT_BEFORE_THE_CONTAINER')
        code=None
    except Exception as error:
        code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
    if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,'PRECHECK')
    # ---- the one container
    container={'name':name,'state':'NOT_STARTED','returncode':None,'code':None,'seconds':None};facts['container']=container
    started=attempt(monotonic)
    result=container_run(commands,RUN_ROW,plan['image_id'],[],PROBE_COMMAND,script,container_name=name)
    ended=attempt(monotonic)
    container.update(code=result['code'],returncode=result['returncode'],
                     seconds=round(ended-started,3) if type(started) in (int,float) and type(ended) in (int,float) else None)
    if not result['started']:return finish(REFUSED_STATUS,REFUSED_OUTCOME,result['code'] or 'COMMAND_NOT_STARTED','CONTAINER_NOT_STARTED')
    container['state']='RETURNED' if result['returned'] else 'DID_NOT_RETURN'
    if result['returned']:facts['probe']=probe_line(result)
    # ---- after it: what the engine still lists, whatever the run said
    listing=attempt(lambda:container_list(commands))
    if type(listing) is list:
        known=set(row['id'] for row in before);new=[row for row in listing if row['id'] not in known]
        facts['containers_after']={'status':'COMPLETE','code':None,'before':len(before),'after':len(listing),'not_there_before':len(new),
                                   'name_present':any(row['name']==name for row in listing),
                                   'rows':[{'id':row['id'],'state':row['state'],'is_the_probe':row['name']==name} for row in new[:MAX_NEW_CONTAINER_ROWS]]}
    else:facts['containers_after']={'status':'UNAVAILABLE','code':listing.get('code'),'before':len(before),'after':None,'not_there_before':None,
                                    'name_present':None,'rows':[]}
    status,outcome,code=run_verdict(result,facts['probe'],facts['containers_after'])
    return finish(status,outcome,code,'CONTAINER')
