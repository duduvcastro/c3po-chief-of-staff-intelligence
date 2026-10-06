OPERATION='GO_READONLY_HOSTOPS02_DB_PRIV_01'
PHASE='READONLY_DB_PRIV_CATALOG_ONLY'
REQUEST_SCHEMA='READONLY_HOSTOPS02_DB_PRIV_REQUEST_V1'
AUTHORITY_SCHEMA='READONLY_HOSTOPS02_DB_PRIV_AUTHORITY_V1'
GO_SCHEMA='READONLY_HOSTOPS02_DB_PRIV_GO_V1'
RECEIPT_SCHEMA='READONLY_HOSTOPS02_DB_PRIV_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_DB_PRIV_PLAN_V1'
SOURCE_NAME='db_priv.py'
WRITES_ALLOWED=False
ACTIVATION_ALLOWED=False
DATE_CLASS='READ'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
# The run that placed the two credentials this source binds read-only into its container (K3-K9, N-5)
EVIDENCE_OPERATIONS=('GO_WRITE_HOSTOPS02_K3K9_SECRETS_01',)
MAX_GATE_SPAN_SECONDS=1800
# Separate program under A2 amendment 1 revision 3 E1-11; no shared PRIV/QUERIES runtime.
MODES=('PRIV',)
COMPLETE_OUTCOME='DB_READER_PRIVILEGES_PROVEN'          # mode QUERIES
PRIV_COMPLETE_OUTCOME='DB_READER_PRIVILEGES_PROVEN'                       # mode PRIV
MISMATCH_OUTCOME='DB_PRIV_OBSERVED_EXPECTATIONS_NOT_MET'
PARTIAL_OUTCOME='DB_PRIV_PARTIAL'
REFUSED_OUTCOME='REFUSED_NOTHING_OBSERVED'
REDUCED_OUTCOME='DB_PRIV_PARTIAL'
ESCAPED_OUTCOME='DB_PRIV_PARTIAL'
PLAN_KEYS=frozenset(('mode','secrets_chain','image_id','image_revision','session','release_receipt_sha256','expected','priv_receipt',
                     'evidence_boot_id_sha256'))
PRIV_RECEIPT_KEYS=frozenset(('operation','mode','outcome','receipt_sha256','observed_at','boot_id_sha256'))
QUERIES_ONLY=('session','release_receipt_sha256','expected','priv_receipt')

DBR_EPOCH='R2D2-V2-SHADOW-2026-10-05'                  # ORD:7, EPOCH = NAMESPACE
DBR_SESSIONS=EPOCH_DAYS[3:8]                           # 2026-10-05 ... 2026-10-09
DBR_NETWORK='c3po_c3po_internal'                       # compose network c3po_internal (internal: true), where db resolves; no egress
K9_ROOT='/var/lib/c3po/r2d2-v2-k9-20261005'            # K3-K9 placement, decision N-8
SECRETS_DIRECTORY=K9_ROOT+'/secrets'
RISK_ENV_NAME='risk-db.env'
EMITTER_DIRECTORY_NAME='emitter'
EMITTER_PASSWORD_NAME='password'
SECRETS_ENTRIES=3                                      # provider.env, risk-db.env, emitter (what K3-K9 leaves)
RISK_TARGET='/c3po-dbr-risk-db.env'                    # the one file bound, read-only
EMITTER_TARGET='/c3po-dbr-emitter'                     # the emitter directory bound, read-only (it holds only the password)
DBR_CONTAINER_PREFIX='hostops02-dbr-priv-'
DBR_RUN_PREFIX=['run','--rm','-i','--pull','never','--init','--user','0:0','--network',DBR_NETWORK,'--read-only','--cap-drop','ALL',
                '--security-opt','no-new-privileges']
EXPECTED_KEYS=frozenset(('epoch_rows','binding_committed'))
LINE_KEYS_OF_MODE={'PRIV':frozenset(('schema','mode','status','risk_url','reader_privileges')),
                   'QUERIES':frozenset(('schema','mode','queries','status','risk_url','emitter_password','epoch_row','binding','emitter'))}
PRIVILEGE_KEYS=('role_is_the_restricted_reader','role_restricted','transaction_read_only','database_connect','schema_usage','epochs_select',
                'journal_select')
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'the signed image ID','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          'query':command_row('docker',DBR_RUN_PREFIX,'--name hostops02-dbr-<16 hex of the GO>; PRIV: the risk URL file bound read-only, the '
                              'signed image ID, python -I -B - PRIV and its container path; QUERIES: the risk URL file and the emitter directory '
                              'bound read-only, the signed image ID, python -I -B - QUERIES, the two container paths, the epoch, the signed session, '
                              'the signed release receipt sha256 (state.release_sha of the epoch row); the pinned snippet on standard input','RUN','CONTAINER',stdin=True)}
DBR_SNIPPET=r'''"""Separate DBR-PRIV: only catalog privileges of the existing restricted reader, rolled-back readonly transaction."""
import json
import os
import re
import stat
import sys
import time

RISK_KEY=b'C3PO_R2D2_RISK_DATABASE_URL='
RISK_URL=rb'postgresql://c3po_v2_risk_reader:[\x21-\x7e]{1,4000}'
READER_ROLE='c3po_v2_risk_reader'
DATABASE={'host':'db','port':5432,'dbname':'c3po'}
CODE=r'[A-Z][A-Z0-9_]{0,79}'
PRIVILEGE_SQL=("SELECT current_user,session_user,current_setting('transaction_read_only'),"
               "(SELECT NOT (r.rolsuper OR r.rolcreaterole OR r.rolcreatedb OR r.rolreplication OR r.rolbypassrls) "
               "FROM pg_catalog.pg_roles r WHERE r.rolname=current_user),"
               "pg_catalog.has_database_privilege(current_user,pg_catalog.current_database(),'CONNECT'),"
               "pg_catalog.has_schema_privilege(current_user,'public','USAGE'),"
               "pg_catalog.has_table_privilege(current_user,'public.r2d2_v2_shadow_epochs','SELECT'),"
               "pg_catalog.has_table_privilege(current_user,'public.r2d2_v2_shadow_journal','SELECT')")
BEGIN_READER="SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
TIMEOUT="SET LOCAL statement_timeout='3s'"
CONNECT_SECONDS=5

class Refusal(ValueError):pass
def need(ok,code):
    if not ok:raise Refusal(code)

def private_bytes(path,limit):
    """A private regular file: root, 0600, one link, at most limit bytes, opened without following a link."""
    try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    except OSError:raise Refusal('FILE_UNAVAILABLE') from None
    try:
        info=os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1,'FILE_NOT_PRIVATE')
        need(info.st_size<=limit,'FILE_FORMAT')
        raw=os.read(fd,limit+1);need(len(raw)<=limit,'FILE_FORMAT');return raw
    finally:os.close(fd)

def risk_dsn(raw):
    """KEY=VALUE, one line, at most one trailing newline; the value names the restricted reader (a boolean, never echoed)."""
    body=raw[:-1] if raw.endswith(b'\n') else raw
    need(body.startswith(RISK_KEY) and b'\n' not in body,'RISK_URL_FORMAT')
    value=body[len(RISK_KEY):];need(re.fullmatch(RISK_URL,value) is not None,'RISK_URL_NOT_THE_RESTRICTED_READER')
    return value.decode('ascii')

def dsn_host_is_db(dsn):
    """Whether the host of the DSN is db, the name the database has on the compose network (a boolean; the host is
    the text between the last '@' and the next ':' or '/')."""
    rest=dsn.rsplit('@',1)[-1];return re.match(r'db(?:[:/]|$)',rest) is not None


def failure(error,fallback):
    """A constant code and, from the database driver, the SQLSTATE only. Never the text of an exception."""
    out={'status':'UNAVAILABLE','code':fallback}
    if isinstance(error,ValueError) and len(error.args)==1 and type(error.args[0]) is str and re.fullmatch(CODE,error.args[0]):out['code']=error.args[0]
    state=getattr(error,'sqlstate',None)
    if type(state) is str and re.fullmatch(r'[0-9A-Z]{5}',state):out['sqlstate']=state
    return out

def privileges_of(row):
    """The proof of statement 0: every member must be exactly True for queries 1 and 3 to run."""
    need(row is not None and len(row)==8,'PRIVILEGE_SHAPE')
    return {'status':'COMPLETE','role_is_the_restricted_reader':row[0]==READER_ROLE and row[1]==READER_ROLE,'role_restricted':row[3] is True,
            'transaction_read_only':row[2]=='on','database_connect':row[4] is True,'schema_usage':row[5] is True,
            'epochs_select':row[6] is True,'journal_select':row[7] is True}

def privileges_read(psycopg,dsn):
    """Mode PRIV: the one catalog read, in a read-only transaction that is rolled back."""
    try:
        connection=psycopg.connect(dsn,autocommit=False,connect_timeout=CONNECT_SECONDS,application_name='hostops02-dbr',options='-c default_transaction_read_only=on')
    except Exception as error:return failure(error,'READER_CONNECTION_FAILED')
    try:
        connection.execute(BEGIN_READER);connection.execute(TIMEOUT)
        return privileges_of(connection.execute(PRIVILEGE_SQL).fetchone())
    except Exception as error:return failure(error,'READER_PRIVILEGE_QUERY_FAILED')
    finally:
        try:connection.rollback()
        except Exception:pass
        try:connection.close()
        except Exception:pass



def main(arguments,psycopg,authority=None,read=private_bytes,monotonic=time.monotonic):
    out={'schema':'HOSTOPS02_DBR_SNIPPET_V2'}
    try:
        need(len(arguments)==2 and arguments[0]=='PRIV','ARGUMENTS')
        out['mode']='PRIV';risk_path=arguments[1]
    except Refusal as error:
        out.update(status='REFUSED',code=str(error));return out
    try:dsn=risk_dsn(read(risk_path,4096));out['risk_url']={'status':'COMPLETE','host_is_db':dsn_host_is_db(dsn)}
    except Exception as error:dsn=None;out['risk_url']=failure(error,'RISK_URL_UNAVAILABLE')
    out['reader_privileges']={'status':'UNAVAILABLE','code':'RISK_URL_UNAVAILABLE'} if dsn is None else privileges_read(psycopg,dsn)
    dsn=None;out['status']='DONE';return out

if __name__=='__main__':
    sys.path.insert(0,'/app')
    try:
        import psycopg
    except Exception:
        sys.stdout.write('{"code":"IMPORT_FAILED","schema":"HOSTOPS02_DBR_SNIPPET_V2","status":"REFUSED"}\n');raise SystemExit(3)
    result=main(sys.argv[1:],psycopg)
    sys.stdout.write(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n');sys.stdout.flush()
    raise SystemExit(0)
'''.encode('ascii')
DBR_SNIPPET_SHA256=sha(DBR_SNIPPET)
SCOPE_STATEMENT=('ORD:28 (M7, READONLY_PSQL_PREFLIGHT_ONLY), in two signed modes of these bytes, each its own request and GO. PRIV: the '
                 'read of the existing restricted reader role c3po_v2_risk_reader by catalog functions only (CONNECT, USAGE on public, '
                 'SELECT on r2d2_v2_shadow_epochs and r2d2_v2_shadow_journal, the role restricted, the session read-only), in one read-only '
                 'transaction, booleans only. QUERIES: exactly the three ORD:28 queries, and only with a PRIV receipt of the same boot and '
                 'UTC day that proved every privilege: query 1 the epoch row count, query 2 the emitter preconditions (the release check '
                 '_authority() as the emitter itself), query 3 whether the capacity binding of the signed session is committed. One '
                 'pinned snippet in one attached container of the signed backend image ID on the compose network c3po_c3po_internal '
                 '(database only, no egress), read-only root filesystem, no capability, read-only binds only of what K3-K9 placed under '
                 'the K9 root (PRIV: the reader URL file; QUERIES: it and the emitter password directory). No DDL, no administrator or '
                 'other credential, no inferred role. Changes nothing on the host; creates and removes one container. No credential, DSN '
                 'or value of the database state but its hashes and booleans reaches the receipt.')
SIDE_EFFECTS=['one attached docker run --rm on the network '+DBR_NETWORK+': the engine creates the container and removes it when its process ends; '
              'a run that times out may leave it until then (its name says so)',
              'two database sessions (the restricted reader, the causal emitter), each with one read-only transaction that is rolled back; '
              'the database logs the connections as it logs any other',
              'the docker CLI reads the two credential files only as bind sources; the snippet reads them inside the container, in memory']
SCOPE_STATEMENT='Separate PRIV program under A2 amendment 1 revision 3 E1-11; no shared-mode executable.'
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'after_effect_reserve_seconds':AFTER_EFFECT_RESERVE_SECONDS,
       'epoch':DBR_EPOCH,'sessions':list(DBR_SESSIONS),'network':DBR_NETWORK,
       'modes':{'PRIV':{'success':PRIV_COMPLETE_OUTCOME,'binds':['risk_url_file'],'command':'python -I -B - PRIV <risk file>'},
                'QUERIES':{'success':COMPLETE_OUTCOME,'binds':['risk_url_file','emitter_directory'],
                           'command':'python -I -B - QUERIES <risk file> <password file> <epoch> <session> <release receipt sha256>',
                           'requires':'priv_receipt: a receipt of this operation in mode PRIV, outcome '+PRIV_COMPLETE_OUTCOME+', of the same boot '
                                      'and the same UTC day, observed before the window of the request'}},
       'snippet':{'sha256':DBR_SNIPPET_SHA256,'bytes':len(DBR_SNIPPET)},
       'binds':{'risk_url_file':{'source':SECRETS_DIRECTORY+'/'+RISK_ENV_NAME,'target':RISK_TARGET,'read_only':True},
                'emitter_directory':{'source':SECRETS_DIRECTORY+'/'+EMITTER_DIRECTORY_NAME,'target':EMITTER_TARGET,'read_only':True}},
       'database':{'host':'db','port':5432,'database':'c3po','reader_role':'c3po_v2_risk_reader','emitter_role':'c3po_v2_causal_emitter',
                   'emitter_authentication':'scram-sha-256 required (libpq 16 or later)'},
       'privileges':{'PRIV':'as the restricted reader, catalog functions only: current_user = session_user = c3po_v2_risk_reader, the role '
                             'restricted (no superuser, createrole, createdb, replication, bypassrls), the transaction read-only, '
                             'has_database_privilege CONNECT, has_schema_privilege public USAGE, has_table_privilege SELECT on '
                             'public.r2d2_v2_shadow_epochs and public.r2d2_v2_shadow_journal; never DDL, never another credential'},
       'queries':{                  '1_EPOCH_ROW':'as the restricted reader: the count of rows of r2d2_v2_shadow_epochs for the epoch, and of that row state_sha, '
                                'version, whether state.release_sha equals the signed release receipt sha256 (release.receipt_sha, r2d2_v2_shadow.py:381), whether journal_head is empty',
                  '2_EMITTER_PRECONDITIONS':'as c3po_v2_causal_emitter: app.r2d2_v2_causal_emitter._authority(connection) of the release '
                                            '(r2d2_v2_causal_emitter.py:79-128), then current_database, current_user, session_user, '
                                            'session_replication_role, transaction_read_only',
                  '3_BINDING_COMMITTED':'as the restricted reader: state.daily_capacity.<session>.sha of the epoch row, and the count of '
                                        'journal entries capacity-prepared:<session>',
                  'transactions':'PRIV: one SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY; QUERIES, reader: queries 1 and 3 in one such transaction (a second only after a failed 1); '
                                 "emitter: SET TRANSACTION READ ONLY; both SET LOCAL statement_timeout='3s'; connections time out after 5 s; query 2 not begun after 20 s; "
                                 'every transaction rolled back'},
       'file_contents_read':[BOOT_ID_PATH],
       'metadata_only':['the secrets directory, the risk URL file, the emitter directory and its password file (lstat and entry counts; '
                        'never their content, size or digest, in this process)'],
       'side_effects':SIDE_EFFECTS,
       'bind_sources':'risk-db.env (0:0 0600, one link) and emitter/ (0:0 0700, only password 0:0 0600) under a chain from / in which every '
                      'component is root-owned and closed to group and other writes (no open root), the last two 0:0 0700; walked, held and '
                      'proved again just before the container (decision 6)',
       'never':['an administrator or any other database credential','a file opened for writing','mkdir','chmod','chown','rename','removal','docker exec','compose','systemctl','a shell','a pull',
                'a write bind','a DDL, an INSERT, an UPDATE, a DELETE or a SET ROLE','the provider tokens bound into the container',
                'a credential, a DSN or the text of an exception in the receipt','a network connection opened by this process'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT}}
# The reachable snippet and the documentary scope contain only this program's mode.
SCOPE['modes']={'PRIV':SCOPE['modes']['PRIV']}
SCOPE['statement']=SCOPE_STATEMENT
SCOPE['queries']={}
SCOPE['binds'].pop('emitter_directory')
SCOPE['side_effects']=['One readonly database session of the restricted reader, rolled back; one attached disposable container.']
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner):
    """Everything this source can do to the host: the read primitives and the signed commands."""


def risk_source():return SECRETS_DIRECTORY+'/'+RISK_ENV_NAME
def emitter_source():return SECRETS_DIRECTORY+'/'+EMITTER_DIRECTORY_NAME
def mounts(plan):
    risk=[{'source':risk_source(),'target':RISK_TARGET,'read_only':True}]
    return risk if plan['mode']=='PRIV' else risk+[{'source':emitter_source(),'target':EMITTER_TARGET,'read_only':True}]
def run_words(plan):
    if plan['mode']=='PRIV':return ['python','-I','-B','-','PRIV',RISK_TARGET]
    return ['python','-I','-B','-','QUERIES',RISK_TARGET,EMITTER_TARGET+'/'+EMITTER_PASSWORD_NAME,DBR_EPOCH,plan['session'],plan['release_receipt_sha256']]

def validate_plan(plan):
    need(type(plan['mode']) is str and plan['mode'] in MODES,'MODE_INVALID')
    need(type(plan['secrets_chain']) is list,'CHAIN_ROW_INVALID')
    rows=validate_chain(plan['secrets_chain'],SECRETS_DIRECTORY)
    need(all((row['uid'],row['gid'],row['mode'])==(0,0,0o700) for row in rows[-2:]),'SECRETS_CHAIN_NOT_ROOT_0700')
    need(text(plan['image_id'],IMAGE_ID),'IMAGE_PLAN_INVALID')
    need(text(plan['image_revision'],'[0-9a-f]{40}'),'IMAGE_PLAN_INVALID')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    if plan['mode']=='PRIV':
        need(all(plan[key] is None for key in QUERIES_ONLY),'PRIV_PLAN_CARRIES_QUERIES_MEMBERS')
    else:
        need(type(plan['session']) is str and plan['session'] in DBR_SESSIONS,'SESSION_NOT_OF_THE_EPOCH')
        need(hexpin(plan['release_receipt_sha256']),'RELEASE_SHA_INVALID')
        expected=plan['expected'];exact(expected,EXPECTED_KEYS,'EXPECTATION_INVALID')
        need(expected['epoch_rows'] is None or (type(expected['epoch_rows']) is int and expected['epoch_rows'] in (0,1)),'EXPECTATION_INVALID')
        need(expected['binding_committed'] is None or type(expected['binding_committed']) is bool,'EXPECTATION_INVALID')
        # the PRIV receipt that proved SELECT: this operation, mode PRIV, its success, the same boot, the same UTC day, earlier
        priv=plan['priv_receipt'];exact(priv,PRIV_RECEIPT_KEYS,'PRIV_RECEIPT_REQUIRED')
        need(priv['operation']==OPERATION and priv['mode']=='PRIV','PRIV_RECEIPT_NOT_OF_THIS_OPERATION')
        need(priv['outcome']==PRIV_COMPLETE_OUTCOME,'PRIV_RECEIPT_DID_NOT_PROVE_SELECT')
        need(hexpin(priv['receipt_sha256']),'PRIV_RECEIPT_REQUIRED')
        need(priv['boot_id_sha256']==plan['evidence_boot_id_sha256'],'PRIV_RECEIPT_OF_ANOTHER_BOOT')
        observed=instant(priv['observed_at']);start=instant(plan['window']['not_before'])
        need(observed.date()==start.date() and observed<start,'PRIV_RECEIPT_NOT_OF_THIS_DAY')
    run_arguments('query',plan['image_id'],mounts(plan),run_words(plan),DBR_CONTAINER_PREFIX+'0'*16)

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    return {'operation':OPERATION,'mode':plan['mode'],'secrets':chain_effects(plan['secrets_chain']),'image_id':plan['image_id'],
            'image_revision':plan['image_revision'],'network':DBR_NETWORK,'binds':mounts(plan),'command':run_words(plan),
            'snippet_sha256':DBR_SNIPPET_SHA256,'epoch':DBR_EPOCH,'session':plan['session'],'release_receipt_sha256':plan['release_receipt_sha256'],
            'expected':plan['expected'],'priv_receipt':plan['priv_receipt'],'queries':0 if plan['mode']=='PRIV' else 3,
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],'writes':0,'containers_run':1,'activation':False}
def success_of(plan):return PRIV_COMPLETE_OUTCOME if plan['mode']=='PRIV' else COMPLETE_OUTCOME


def item_of(findings=(),**facts):return dict(facts,status='COMPLETE',findings=sorted(set(findings)))
CODE_OR_NONE='[A-Z][A-Z0-9_]{0,79}'
def checked_part(value,keys):
    """One part of the snippet's line: COMPLETE with exactly its keys, or UNAVAILABLE with a constant code (and a SQLSTATE)."""
    need(type(value) is dict and value.get('status') in ('COMPLETE','UNAVAILABLE'),'SNIPPET_LINE_INVALID')
    if value['status']=='UNAVAILABLE':
        need(set(value)<={'status','code','sqlstate'} and text(value.get('code'),CODE_OR_NONE)
             and ('sqlstate' not in value or text(value['sqlstate'],'[0-9A-Z]{5}')),'SNIPPET_LINE_INVALID')
        return value
    need(set(value)==set(keys)|{'status'},'SNIPPET_LINE_INVALID');return value
def snippet_line(raw,plan):
    """The one line the snippet prints, every member typed; nothing in it is copied to the receipt unchecked."""
    line=single_line(raw);mode=plan['mode']
    need(set(line)==set(LINE_KEYS_OF_MODE[mode]) and line['schema']=='HOSTOPS02_DBR_SNIPPET_V2' and line['mode']==mode and line['status']=='DONE','SNIPPET_LINE_INVALID')
    risk=checked_part(line['risk_url'],('host_is_db',))
    if risk['status']=='COMPLETE':need(type(risk['host_is_db']) is bool,'SNIPPET_LINE_INVALID')
    if mode=='PRIV':
        privileges=checked_part(line['reader_privileges'],PRIVILEGE_KEYS)
        if privileges['status']=='COMPLETE':need(all(type(privileges[key]) is bool for key in PRIVILEGE_KEYS),'SNIPPET_LINE_INVALID')
        return line
    need(line['queries']==3,'SNIPPET_LINE_INVALID');checked_part(line['emitter_password'],())
    row=checked_part(line['epoch_row'],('rows','state_sha','version','release_sha_equal','journal_head_empty'))
    if row['status']=='COMPLETE':
        need(type(row['rows']) is int and row['rows'] in (0,1),'SNIPPET_LINE_INVALID')
        present=row['rows']==1
        need((row['state_sha'] is None or hexpin(row['state_sha'])) and (row['version'] is None or integer(row['version']))
             and all((type(row[key]) is bool) if present else (row[key] is None) for key in ('release_sha_equal','journal_head_empty')),'SNIPPET_LINE_INVALID')
    binding=checked_part(line['binding'],('session','committed','binding_sha256','journal_entries'))
    if binding['status']=='COMPLETE':
        need(binding['session']==plan['session'] and type(binding['committed']) is bool and integer(binding['journal_entries'])
             and (hexpin(binding['binding_sha256']) if binding['committed'] else binding['binding_sha256'] is None),'SNIPPET_LINE_INVALID')
    emitter=checked_part(line['emitter'],('authority_passed','database_is_c3po','current_user_is_the_emitter','session_user_equal',
                                          'replication_role_origin','transaction_read_only'))
    if emitter['status']=='COMPLETE':need(all(type(value) is bool for key,value in emitter.items() if key!='status'),'SNIPPET_LINE_INVALID')
    return line

def judged(line,plan):
    """The findings of a valid line: unconditional rules, then (QUERIES) the signed expectations."""
    findings=[]
    parts=('risk_url','reader_privileges') if plan['mode']=='PRIV' else ('risk_url','emitter_password','epoch_row','binding','emitter')
    for key in parts:
        if line[key]['status']!='COMPLETE':findings.append('QUERY_UNAVAILABLE_'+key.upper())
    if line['risk_url']['status']=='COMPLETE' and line['risk_url']['host_is_db'] is not True:findings.append('RISK_URL_HOST_IS_NOT_DB')
    if plan['mode']=='PRIV':
        privileges=line['reader_privileges']
        if privileges['status']=='COMPLETE' and not all(privileges[key] is True for key in PRIVILEGE_KEYS):findings.append('READER_PRIVILEGE_NOT_PROVEN')
        return findings
    expected=plan['expected'];row,binding,emitter=line['epoch_row'],line['binding'],line['emitter']
    if row['status']=='COMPLETE':
        if expected['epoch_rows'] is not None and row['rows']!=expected['epoch_rows']:findings.append('EPOCH_ROW_COUNT_NOT_AS_SIGNED')
        if row['rows']==1 and row['release_sha_equal'] is not True:findings.append('EPOCH_RELEASE_SHA_MISMATCH')
        if row['rows']==1 and row['version']==0 and row['journal_head_empty'] is not True:findings.append('EPOCH_ZERO_VERSION_JOURNAL')
    if binding['status']=='COMPLETE':
        if expected['binding_committed'] is not None and binding['committed']!=expected['binding_committed']:findings.append('BINDING_NOT_AS_SIGNED')
        if binding['committed']!=(binding['journal_entries']==1):findings.append('BINDING_AND_JOURNAL_DISAGREE')
    if emitter['status']=='COMPLETE':
        if not all(value is True for key,value in emitter.items() if key!='status'):findings.append('EMITTER_IDENTITY_NOT_AS_REQUIRED')
    return findings

def _reduce_line(receipt):
    if type(receipt.get('items')) is dict and type(receipt['items'].get('query')) is dict:receipt['items']['query'].pop('line',None)
REDUCTIONS=[('SNIPPET_LINE_DROPPED',_reduce_line)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    commands=Commands(host,gate);items={};findings=[];held={};go16=bound['go_sha256'][:16];name=DBR_CONTAINER_PREFIX+go16
    def observe(key,action):
        """One item, observed on its own. An expiry stops the run; any other failure is that item's UNAVAILABLE."""
        try:
            items[key]=action();findings.extend(items[key].get('findings',[]))
        except Exception as error:
            items[key]=safe(error)
            if items[key].get('code') in ('GO_EXPIRED','CLOCK_REVERSED'):raise
    def finish(status,outcome,code):
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),clock=timing(begun,mark,clock,monotonic),
            commands_started=dict(commands.started),mutating_calls=state.counts(),items=items,findings=sorted(set(findings)),writes=0,
            containers_run=commands.started['CONTAINER'],phase_reached='OBSERVATION')))
    try:
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            def boot():
                same=boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256']
                return item_of(findings=[] if same else ['EVIDENCE_FROM_EARLIER_BOOT'],equal_to_the_evidence=same)
            observe('boot',boot)
            def secrets():
                held['SECRETS']=Pinned(host,walk_pinned(host,plan['secrets_chain'],gate,[]),rows=plan['secrets_chain'])
                fd=held['SECRETS'].fd;entries=count_entries(host,fd,gate);facts={'entries':entries};found=[]
                if entries!=SECRETS_ENTRIES:found.append('SECRETS_DIRECTORY_NOT_AS_PLACED')
                for key,named,want,mode in (('risk_url_file',RISK_ENV_NAME,'file',0o600),('emitter_directory',EMITTER_DIRECTORY_NAME,'dir',0o700)):
                    gate()
                    try:info=host.lstat(named,fd)
                    except FileNotFoundError:facts[key]={'exists':False};found.append('CREDENTIAL_ABSENT');continue
                    facts[key]={'exists':True,'type':kind(info.st_mode),'uid':info.st_uid,'gid':info.st_gid,'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),'links':info.st_nlink}
                    if (kind(info.st_mode),info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))!=(want,0,0,mode) or (want=='file' and info.st_nlink!=1):
                        found.append('CREDENTIAL_NOT_PRIVATE')
                if not found:
                    gate();held['EMITTER']=Pinned(host,host.open(EMITTER_DIRECTORY_NAME,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=fd),
                                                  parent=held['SECRETS'],name=EMITTER_DIRECTORY_NAME)
                    inner=count_entries(host,held['EMITTER'].fd,gate);facts['emitter_entries']=inner
                    try:info=host.lstat(EMITTER_PASSWORD_NAME,held['EMITTER'].fd)
                    except FileNotFoundError:info=None
                    facts['emitter_password_file']={'exists':info is not None}
                    if info is None:found.append('CREDENTIAL_ABSENT')
                    else:
                        facts['emitter_password_file'].update(type=kind(info.st_mode),uid=info.st_uid,gid=info.st_gid,mode_octal='%04o'%stat.S_IMODE(info.st_mode),links=info.st_nlink)
                        if (kind(info.st_mode),info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)!=('file',0,0,0o600,1):found.append('CREDENTIAL_NOT_PRIVATE')
                    if inner!=1:found.append('EMITTER_DIRECTORY_NOT_AS_PLACED')
                return item_of(findings=found,**facts)
            observe('secrets',secrets)
            def image():
                facts=image_facts(commands,plan['image_id']);found=[]
                if facts['id']!=plan['image_id']:found.append('IMAGE_ID_MISMATCH')
                if facts['revision_label']!=plan['image_revision']:found.append('IMAGE_REVISION_MISMATCH')
                return item_of(findings=found,id_equal=facts['id']==plan['image_id'],revision_equal=facts['revision_label']==plan['image_revision'])
            observe('image',image)
            listed=[]
            def before():
                listed.extend(container_list(commands))
                return item_of(findings=['DBR_CONTAINER_NAME_PRESENT'] if [row for row in listed if row['name']==name] else [],containers=len(listed))
            observe('containers_before',before)
            # the container only when nothing it would read is in doubt: credentials as placed, image as signed, name free
            ready=all(items.get(key,{}).get('status')=='COMPLETE' and not items[key]['findings'] for key in ('boot','secrets','image','containers_before'))
            ran=[False]
            def query():
                if not ready:return {'status':'UNAVAILABLE','code':'NOT_STARTED_PRECONDITIONS'}
                for handle in held.values():handle.verify(gate)
                result=container_run(commands,'query',plan['image_id'],mounts(plan),run_words(plan),DBR_SNIPPET,container_name=name)
                ran[0]=result['started']
                facts={'started':result['started'],'returned':result['returned'],'returncode':result['returncode'],'code':result['code'],
                       'container_may_still_exist':result['started'] and not result['returned']}
                if not result['returned']:return dict(facts,status='UNAVAILABLE',code=result['code'] or 'QUERY_RUN_NOT_COMPLETED')
                facts['engine_failure']=result['returncode'] in RUN_ENGINE_STATUSES
                if result['returncode']!=0:return dict(facts,status='UNAVAILABLE',code='QUERY_RUN_FAILED')
                line=snippet_line(result['output'],plan)
                return item_of(findings=judged(line,plan),line={key:value for key,value in line.items() if key not in ('schema','status')},**facts)
            observe('query',query)
            def after():
                rows=container_list(commands)
                left=bool([row for row in rows if row['name']==name])
                return item_of(findings=['DBR_CONTAINER_LEFT'] if left else [],containers=len(rows),dbr_container_present=left)
            if ran[0]:observe('containers_after',after)
        except Refused as error:
            code=code_of(error,'OBSERVATION_FAILED')
            if not items:return seal(envelope(REFUSED_STATUS,REFUSED_OUTCOME,code,dict(bound,phase_reached='BEFORE_ANY_OBSERVATION',mutating_calls=state.counts(),writes=0)))
            return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,code)
        status=combined(items.values())
        if status!='COMPLETE':return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,'OBSERVATION_INCOMPLETE')
        if findings:return finish(PARTIAL_STATUS,MISMATCH_OUTCOME,sorted(set(findings))[0])
        return finish(COMPLETE_STATUS,success_of(plan),None)
    finally:
        for handle in list(held.values())[::-1]:
            try:handle.close()
            except Exception:pass
