"""Separate DBR: exactly the three ORD:28 queries; no privilege query or PRIV execution branch."""
import json
import os
import re
import stat
import sys
import time

RISK_KEY=b'C3PO_R2D2_RISK_DATABASE_URL='
RISK_URL=rb'postgresql://c3po_v2_risk_reader:[\x21-\x7e]{1,4000}'
READER_ROLE='c3po_v2_risk_reader'
EMITTER_ROLE='c3po_v2_causal_emitter'
DATABASE={'host':'db','port':5432,'dbname':'c3po'}
CODE=r'[A-Z][A-Z0-9_]{0,79}'
EPOCH=r'R2D2-V2-(?:SHADOW|DIAG)-[A-Za-z0-9_-]{1,80}'
HEX=r'[0-9a-f]{64}'
EPOCH_ROW_SQL=("SELECT count(e.epoch),max(e.state_sha),max(e.version),max(e.state->>'release_sha'),max(e.journal_head) "
               "FROM public.r2d2_v2_shadow_epochs e WHERE e.epoch=%s::text")
BINDING_SQL=("SELECT (SELECT e.state->'daily_capacity'->(%s::text)->>'sha' FROM public.r2d2_v2_shadow_epochs e WHERE e.epoch=%s::text),"
             "(SELECT count(*) FROM public.r2d2_v2_shadow_journal j WHERE j.epoch=%s::text AND j.journal_key=%s::text)")
IDENTITY_SQL=("SELECT current_database(),current_user,session_user,current_setting('session_replication_role'),"
              "current_setting('transaction_read_only')")
BEGIN_READER="SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
BEGIN_EMITTER="SET TRANSACTION READ ONLY"
TIMEOUT="SET LOCAL statement_timeout='3s'"
CONNECT_SECONDS=5
EMITTER_LATEST_START_SECONDS=20

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

def emitter_password(raw):
    need(re.fullmatch(rb'[A-Za-z0-9_-]{64}',raw) is not None,'EMITTER_PASSWORD_FORMAT');return raw.decode('ascii')

def failure(error,fallback):
    """A constant code and, from the database driver, the SQLSTATE only. Never the text of an exception."""
    out={'status':'UNAVAILABLE','code':fallback}
    if isinstance(error,ValueError) and len(error.args)==1 and type(error.args[0]) is str and re.fullmatch(CODE,error.args[0]):out['code']=error.args[0]
    state=getattr(error,'sqlstate',None)
    if type(state) is str and re.fullmatch(r'[0-9A-Z]{5}',state):out['sqlstate']=state
    return out



def reader_queries(psycopg,dsn,epoch,session,release_sha):
    """Queries 1 and 3, as the restricted reader, in one read-only repeatable-read transaction that is rolled back (a
    second one for query 3 only when query 1 failed and aborted the first)."""
    epoch_row={'status':'UNAVAILABLE','code':'NOT_RUN'};binding={'status':'UNAVAILABLE','code':'NOT_RUN'}
    try:
        connection=psycopg.connect(dsn,autocommit=False,connect_timeout=CONNECT_SECONDS,application_name='hostops02-dbr',options='-c default_transaction_read_only=on')
    except Exception as error:
        down=failure(error,'READER_CONNECTION_FAILED');return down,dict(down)
    try:
        aborted=False
        try:
            connection.execute(BEGIN_READER);connection.execute(TIMEOUT)
            row=connection.execute(EPOCH_ROW_SQL,(epoch,)).fetchone()
            need(row is not None and len(row)==5,'EPOCH_ROW_SHAPE')
            count=row[0];need(type(count) is int and count in (0,1),'EPOCH_ROW_COUNT')
            epoch_row={'status':'COMPLETE','rows':count,
                       'state_sha':row[1] if count==1 and type(row[1]) is str and re.fullmatch(HEX,row[1]) else None,
                       'version':row[2] if count==1 and type(row[2]) is int and row[2]>=0 else None,
                       'release_sha_equal':(row[3]==release_sha) if count==1 else None,
                       'journal_head_empty':(row[4]=='') if count==1 else None}
        except Exception as error:epoch_row=failure(error,'EPOCH_ROW_FAILED');aborted=True
        try:
            if aborted:connection.rollback();connection.execute(BEGIN_READER);connection.execute(TIMEOUT)
            row=connection.execute(BINDING_SQL,(session,epoch,epoch,'capacity-prepared:'+session)).fetchone()
            need(row is not None and len(row)==2 and type(row[1]) is int and row[1]>=0,'BINDING_SHAPE')
            sha=row[0] if type(row[0]) is str and re.fullmatch(HEX,row[0]) else None
            need(row[0] is None or sha is not None,'BINDING_SHA_FORMAT')
            binding={'status':'COMPLETE','session':session,'committed':sha is not None,'binding_sha256':sha,'journal_entries':row[1]}
        except Exception as error:binding=failure(error,'BINDING_FAILED')
    finally:
        try:connection.rollback()
        except Exception:pass
        try:connection.close()
        except Exception:pass
    return epoch_row,binding

def emitter_query(psycopg,authority,password):
    """Query 2, as the emitter itself (SCRAM required): the release's own precondition check, then its identity."""
    try:
        need(psycopg.pq.version()>=160000,'LIBPQ16_REQUIRED')
        connection=psycopg.connect(host=DATABASE['host'],port=DATABASE['port'],dbname=DATABASE['dbname'],user=EMITTER_ROLE,password=password,
                                   autocommit=False,connect_timeout=CONNECT_SECONDS,require_auth='scram-sha-256',options='',application_name='hostops02-dbr')
    except Exception as error:return failure(error,'EMITTER_CONNECTION_FAILED')
    try:
        connection.execute(BEGIN_EMITTER);connection.execute(TIMEOUT)
        authority(connection)
        row=connection.execute(IDENTITY_SQL).fetchone();need(row is not None and len(row)==5,'EMITTER_IDENTITY_SHAPE')
        return {'status':'COMPLETE','authority_passed':True,'database_is_c3po':row[0]=='c3po','current_user_is_the_emitter':row[1]==EMITTER_ROLE,
                'session_user_equal':row[2]==row[1],'replication_role_origin':row[3]=='origin','transaction_read_only':row[4]=='on'}
    except Exception as error:return failure(error,'EMITTER_AUTHORITY_FAILED')
    finally:
        try:connection.rollback()
        except Exception:pass
        try:connection.close()
        except Exception:pass

def main(arguments,psycopg,authority,read=private_bytes,monotonic=time.monotonic):
    out={'schema':'HOSTOPS02_DBR_SNIPPET_V2'};started=monotonic()
    try:
        need(len(arguments)==6 and arguments[0]=='QUERIES','ARGUMENTS');out['mode']='QUERIES'
        risk_path,password_path,epoch,session,release_sha=arguments[1:]
        need(re.fullmatch(EPOCH,epoch) is not None and re.fullmatch(r'2026-10-0[5-9]',session) is not None and re.fullmatch(HEX,release_sha) is not None,'ARGUMENTS')
    except Refusal as error:
        out.update(status='REFUSED',code=str(error));return out
    try:dsn=risk_dsn(read(risk_path,4096));out['risk_url']={'status':'COMPLETE','host_is_db':dsn_host_is_db(dsn)}
    except Exception as error:dsn=None;out['risk_url']=failure(error,'RISK_URL_UNAVAILABLE')
    out['queries']=3
    try:password=emitter_password(read(password_path,64));out['emitter_password']={'status':'COMPLETE'}
    except Exception as error:password=None;out['emitter_password']=failure(error,'EMITTER_PASSWORD_UNAVAILABLE')
    if dsn is None:out['epoch_row']=out['binding']={'status':'UNAVAILABLE','code':'RISK_URL_UNAVAILABLE'}
    else:out['epoch_row'],out['binding']=reader_queries(psycopg,dsn,epoch,session,release_sha)
    if password is None:out['emitter']={'status':'UNAVAILABLE','code':'EMITTER_PASSWORD_UNAVAILABLE'}
    elif monotonic()-started>EMITTER_LATEST_START_SECONDS:out['emitter']={'status':'UNAVAILABLE','code':'SNIPPET_DEADLINE'}
    else:out['emitter']=emitter_query(psycopg,authority,password)
    dsn=password=None
    out['status']='DONE';return out

if __name__=='__main__':
    sys.path.insert(0,'/app')
    try:
        import psycopg
        from app.r2d2_v2_causal_emitter import _authority
    except Exception:
        sys.stdout.write('{"code":"IMPORT_FAILED","schema":"HOSTOPS02_DBR_SNIPPET_V2","status":"REFUSED"}\n');raise SystemExit(3)
    result=main(sys.argv[1:],psycopg,_authority)
    sys.stdout.write(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n');sys.stdout.flush()
    raise SystemExit(0)
