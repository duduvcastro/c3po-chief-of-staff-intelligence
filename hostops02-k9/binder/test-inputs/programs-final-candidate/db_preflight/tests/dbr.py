"""Fixtures of DBR (the three read-only queries of ORD:28): the emulated host after K3-K9 placed the two credentials,
a request plan built from it as a binder copies it from the read-only receipts, and what the emulated container does.

The container runs the source's own pinned snippet (the bytes of DBR_SNIPPET, executed in this process) with a fake
database driver whose answers are a model of the database of this epoch: the epoch row (present or not), the reader's
privilege on it, the capacity binding of a session, and the emitter's authentication and preconditions. The files
the snippet reads are read through the binds of the emulated run, with the owner, mode and link count the tree says.
Every credential is a synthetic canary that must never leave a run."""
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import re
import stat
import types

import family as f
import hostemu

HERE=Path(__file__).resolve().parent
DIRECTORY=HERE.parent
K9_ROOT='/var/lib/c3po/r2d2-v2-k9-20261005'
SECRETS=K9_ROOT+'/secrets'
EPOCH='R2D2-V2-SHADOW-2026-10-05'
RELEASE='5d'*32
STATE_SHA='5a'*32
BINDING_SHA='b1'*32
RISK_CANARY='never-emit-risk-password-canary'
PASSWORD_CANARY=('never-emit-emitter-canary-'+'x'*64)[:64]
RISK_FILE=('C3PO_R2D2_RISK_DATABASE_URL=postgresql://c3po_v2_risk_reader:'+RISK_CANARY+'@db:5432/c3po\n').encode()
PROVIDER_FILE=b'C3PO_EODHD_API_TOKEN=never-emit-provider-canary\n'
NOW=datetime(2026,10,5,20,40,tzinfo=timezone.utc)        # DBR-E band of A2, Monday 17:40 BRT

def K():return f.load(DIRECTORY)


PRIVILEGES=('connect','usage','epochs_select','journal_select')
class DatabaseError(Exception):
    def __init__(self,sqlstate,text='password authentication failed for user c3po_v2_risk_reader with '+RISK_CANARY):
        Exception.__init__(self,text);self.sqlstate=sqlstate

class Database:
    """The answers of the database of this epoch, as far as the three queries reach it."""
    def __init__(self):
        self.epoch_row=None                       # None: no row; else dict(state_sha, version, release_sha, journal_head)
        self.reader_can_read=True;self.reader_role='c3po_v2_risk_reader';self.reader_restricted=True
        self.bindings={}                          # session -> binding sha
        self.journal={}                           # session -> count of capacity-prepared entries
        self.emitter_password=PASSWORD_CANARY;self.emitter_preconditions=None    # None: pass; else the code the release raises
        self.emitter_identity=('c3po','c3po_v2_causal_emitter','c3po_v2_causal_emitter','origin','on')
        self.privileges={key:True for key in PRIVILEGES};self.privilege_error=None;self.session_role=None
        self.read_only='on';self.libpq=160004;self.reader_down=False;self.connections=[];self.statements=[];self.count=None
    def answer(self,connection,sql,parameters):
        self.statements.append((connection.user,sql,parameters))
        if sql.startswith('SET '):return None
        if connection.user=='c3po_v2_causal_emitter':
            if sql.startswith('SELECT current_database()'):return [self.emitter_identity]
            raise AssertionError('the emitter is asked only its identity after _authority: '+sql[:60])
        if 'has_table_privilege' in sql:
            if self.privilege_error is not None:raise DatabaseError(self.privilege_error,'relation does not exist')
            assert parameters is None
            return [(self.reader_role,self.session_role or self.reader_role,self.read_only,self.reader_restricted)+tuple(self.privileges[key] for key in PRIVILEGES)]
        if 'count(e.epoch)' in sql:
            if not self.reader_can_read:raise DatabaseError('42501','permission denied for table r2d2_v2_shadow_epochs')
            row=self.epoch_row if parameters==(EPOCH,) else None
            if row is None:return [(0 if self.count is None else self.count,None,None,None,None)]
            return [(1 if self.count is None else self.count,row['state_sha'],row['version'],row['release_sha'],row['journal_head'])]
        if "daily_capacity" in sql:
            if not self.reader_can_read:raise DatabaseError('42501','permission denied')
            session,epoch,_,key=parameters
            sha=self.bindings.get(session) if self.epoch_row is not None and epoch==EPOCH else None
            return [(sha,self.journal.get(key[len('capacity-prepared:'):],0))]
        raise AssertionError('a statement outside the fixed set: '+sql[:80])

class Connection:
    def __init__(self,database,user):self.database,self.user,self.autocommit,self.closed=database,user,False,False;self.rows=None
    def execute(self,sql,parameters=None):
        assert not self.closed and type(sql) is str;self.rows=self.database.answer(self,sql,parameters);return self
    def fetchone(self):return None if not self.rows else self.rows[0]
    def fetchall(self):return list(self.rows or [])
    def rollback(self):self.database.statements.append((self.user,'ROLLBACK',None))
    def close(self):self.closed=True

def driver(database):
    """A module with the two members of psycopg the snippet uses: connect and pq.version."""
    def connect(conninfo=None,**options):
        database.connections.append(dict(options,conninfo=conninfo))
        assert options.get('autocommit') is False and options.get('connect_timeout')==5
        if conninfo is not None:
            assert options.get('options')=='-c default_transaction_read_only=on'
            if database.reader_down:raise DatabaseError('08001','could not connect to server db')
            assert conninfo==database.dsn,'the reader connects with exactly the DSN of the placed file'
            return Connection(database,'c3po_v2_risk_reader')
        assert (options['host'],options['port'],options['dbname'],options['user'],options['require_auth'])==('db',5432,'c3po','c3po_v2_causal_emitter','scram-sha-256')
        if options['password']!=database.emitter_password:raise DatabaseError('28P01','password authentication failed for user c3po_v2_causal_emitter '+options['password'])
        return Connection(database,'c3po_v2_causal_emitter')
    return types.SimpleNamespace(connect=connect,pq=types.SimpleNamespace(version=lambda:database.libpq))

class ReleaseError(ValueError):pass
def model_authority(database):
    """What _authority (r2d2_v2_causal_emitter.py:79-128) does, as far as the snippet sees it: it refuses a connection in
    autocommit, runs its three SELECTs and raises ShadowIntegrityError(<constant code>) when a precondition fails."""
    def authority(connection):
        if getattr(connection,'autocommit',None) is not False:raise ReleaseError('CAUSAL_TRANSACTION_REQUIRED')
        database.statements.append((connection.user,'AUTHORITY_THREE_SELECTS',None))
        if database.emitter_preconditions is not None:raise ReleaseError(database.emitter_preconditions)
    return authority

def snippet_module():
    """The pinned snippet's functions, from the bytes the source carries (no action on import: the main guard)."""
    namespace={'__name__':'hostops02_dbr_snippet'};exec(compile(K().m.DBR_SNIPPET,'<dbr-snippet>','exec'),namespace)
    return types.SimpleNamespace(**namespace)

def bound_reader(call):
    """The private-file read of the snippet, through the binds of the emulated run (owner, mode, links of the tree)."""
    def read(path,limit):
        node=call.node(path)
        if node is None or node.kind=='symlink':raise snippet_module().Refusal('FILE_UNAVAILABLE')
        if not (node.kind=='file' and node.uid==0 and node.mode==0o600 and node.nlink==1):raise snippet_module().Refusal('FILE_NOT_PRIVATE')
        if len(node.content)>limit:raise snippet_module().Refusal('FILE_FORMAT')
        return bytes(node.content)
    return read

def container(database):
    def on_run(call):
        assert call.network=='c3po_c3po_internal' and call.read_only_root and call.options['--user']==['0:0'] and call.options['--cap-drop']==['ALL']
        assert all(mount['read_only'] for mount in call.mounts) and call.command[:4]==['python','-I','-B','-']
        assert call.stdin==K().m.DBR_SNIPPET
        module=snippet_module()
        result=module.main(call.command[4:],driver(database),model_authority(database),read=bound_reader(call))
        return 0,(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n').encode()
    return on_run

def world():
    """The emulated host after K4-E0 made the K9 tree and K3-K9 placed its secrets."""
    k=K();host=f.world(k)
    host.tree.add('/var/lib/c3po',mode=0o755);host.tree.add(K9_ROOT,mode=0o700);host.tree.add(SECRETS,mode=0o700)
    host.tree.add(SECRETS+'/provider.env',kind='file',mode=0o600,content=PROVIDER_FILE)
    host.tree.add(SECRETS+'/risk-db.env',kind='file',mode=0o600,content=RISK_FILE)
    host.tree.add(SECRETS+'/emitter',mode=0o700);host.tree.add(SECRETS+'/emitter/password',kind='file',mode=0o600,content=PASSWORD_CANARY.encode())
    database=Database();database.dsn=RISK_FILE.decode().strip().split('=',1)[1];host.database=database;host.docker.on_run=container(database)
    return k,host

PRIV_AT='2026-10-05T20:20:00+00:00'                        # a PRIV run earlier the same UTC day (DBR-PRIV slot)
def priv_receipt(**changes):
    receipt={'operation':'GO_READONLY_HOSTOPS02_DB_PRIV_01','mode':'PRIV','outcome':'DB_READER_PRIVILEGES_PROVEN',
             'receipt_sha256':'7e'*32,'observed_at':PRIV_AT,'boot_id_sha256':f.BOOT_SHA}
    receipt.update(changes);return receipt

def fields(host,mode='QUERIES',**changes):
    plan={'mode':mode,'secrets_chain':hostemu.rows(host,SECRETS),'image_id':hostemu.BACKEND,'image_revision':hostemu.REVISION,
          'evidence_boot_id_sha256':f.BOOT_SHA}
    if mode=='QUERIES':
        plan.update(session='2026-10-05',release_receipt_sha256=RELEASE,expected={'epoch_rows':None,'binding_committed':None},priv_receipt=priv_receipt())
    else:plan.update(session=None,release_receipt_sha256=None,expected=None,priv_receipt=None)
    plan.update(changes);return plan

def case(now=None,mode='QUERIES',**changes):
    """(docs, host); for another instant, the PRIV receipt is moved to 20 minutes before it (same day)."""
    k,host=world();plan=fields(host,mode,**changes)
    if now is not None and mode=='QUERIES' and 'priv_receipt' not in changes and now.hour>=1:
        plan['priv_receipt']=priv_receipt(observed_at=(now-timedelta(minutes=20)).isoformat())
    return f.Docs(k,plan,now=NOW if now is None else now),host

CANARIES=(RISK_CANARY,PASSWORD_CANARY,'never-emit')
def clean(receipt):
    line=f.line(receipt).decode()
    return not any(canary in line for canary in CANARIES) and hostemu.SECRET not in line
