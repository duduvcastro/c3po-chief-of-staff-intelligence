"""Separate DBR-PRIV: only catalog privileges of the existing restricted reader, rolled-back readonly transaction."""
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
