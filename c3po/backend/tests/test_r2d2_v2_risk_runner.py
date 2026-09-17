"""Synthetic fixtures only; these tests are not a contemporary provider proof."""
import json
import hashlib
import stat
from contextlib import contextmanager
from datetime import datetime, date, timezone

import pytest

from app.r2d2_v2_risk_acquisition import HttpReply, SourceRequest
from app.r2d2_v2_risk_runner import capture_direct_insider_batch, ReadOnlyInsiderDatabaseReader, PacedRiskTransport

NOW = datetime(2026,9,17,18,tzinfo=timezone.utc)

class Result:
    def __init__(self, rows): self.rows=rows
    def fetchone(self): return self.rows[0]
    def fetchall(self): return self.rows

class Connection:
    autocommit=False
    def __init__(self, rows=(), mode='on', role=('synthetic_reader',False), authority=None, acl=None):
        self.rows,self.mode,self.calls=list(rows),mode,[]
        self.role=role
        self.authority=authority
        self.acl=acl
    def execute(self, sql, params=None):
        self.calls.append((sql,params))
        if sql=='SHOW transaction_read_only': return Result([(self.mode,)])
        if sql=='SHOW transaction_isolation': return Result([('repeatable read',)])
        if sql==ReadOnlyInsiderDatabaseReader.ROLE_SQL:
            row=self.authority
            if row is None:
                row=(self.role[0],self.role[0],self.role[1] is False,True,True,True) if self.role else None
            return Result([row])
        if sql==ReadOnlyInsiderDatabaseReader.ACL_SQL:
            return Result([self.acl if self.acl is not None else ('ir_events',True,True,True,True,True,True)])
        if sql=='SELECT transaction_timestamp()': return Result([(NOW,)])
        return Result(self.rows)


def reader(connection):
    @contextmanager
    def factory(): yield connection
    return ReadOnlyInsiderDatabaseReader(factory,clock=lambda:NOW)


def provider(request):
    return HttpReply(200,json.dumps({'symbol':request.parameters['symbol'],'data':[
        {'name':'Synthetic','transactionCode':'P','transactionDate':'2026-09-01',
         'filingDate':'2026-09-01','change':2,'share':20,'transactionPrice':5}]}).encode())


def capture(tmp_path, **options):
    defaults=dict(entries=[{'symbol':'TEST','market':'US','identity':None}],
                  output_path=tmp_path/'batch',namespace='R2D2-V2-DIAG-R4-2026-09-18',
                  session_date=date(2026,9,18),clock=lambda:NOW,
                  transport=provider,database_reader=reader(Connection()))
    defaults.update(options)
    return capture_direct_insider_batch(**defaults)


def test_reader_executes_read_only_before_select():
    conn=Connection()
    value=reader(conn)('TEST',NOW)
    assert conn.calls[0][0]=='SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'
    assert conn.calls[-1][1][0]=='TEST' and conn.calls[-1][1][2]==NOW
    assert value['counts']=={'buy_count':0,'sell_count':0,'total_count':0}
    assert value['transaction_read_only'] and not value['coverage_verified']


def test_read_only_denied_is_sanitized():
    with pytest.raises(ValueError,match='DATABASE_READ_ONLY_COMPARISON_FAILED'):
        reader(Connection(mode='off'))('TEST',NOW)


def test_batch_receipts_private_hashes_and_db_difference(tmp_path):
    result=capture(tmp_path)
    assert result['counts']['coverage_verified']==1
    assert result['counts']['db_different']==1
    manifest_path=tmp_path/'batch'/'MANIFEST.json'
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest()==result['manifest_sha256']
    manifest=json.loads(manifest_path.read_bytes())
    assert manifest['phase_pending']==0 and not manifest['database_writes']
    assert stat.S_IMODE((tmp_path/'batch').stat().st_mode)==0o700
    for name,digest in manifest['files'].items():
        path=tmp_path/'batch'/name
        assert stat.S_IMODE(path.stat().st_mode)==0o600
        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest


@pytest.mark.parametrize('option',[{'max_total_bytes':1},{'max_total_requests':1,'transport':lambda _:HttpReply(500,b'')}])
def test_budget_failure_cannot_publish_completed_manifest(tmp_path,option):
    with pytest.raises(ValueError,match='BUDGET'):
        capture(tmp_path,**option)
    assert not (tmp_path/'batch'/'MANIFEST.json').exists()


def test_duplicate_input_and_existing_output_refused(tmp_path):
    with pytest.raises(ValueError,match='SYMBOL_LIST'):
        capture(tmp_path,entries=[{'symbol':'TEST','market':'US'}]*2)
    capture(tmp_path)
    with pytest.raises(FileExistsError): capture(tmp_path)


def test_database_failure_never_calls_provider_or_completes(tmp_path):
    calls=[]
    def fail(*_): raise ValueError('DB failed')
    with pytest.raises(ValueError): capture(tmp_path,database_reader=fail,transport=lambda r:calls.append(r))
    assert calls==[] and not (tmp_path/'batch'/'MANIFEST.json').exists()


def test_pacing_waits_and_checks_guard_after_wait():
    now=[0.0]; actions=[]
    def sleep(seconds): actions.append('sleep'); now[0]+=seconds
    paced=PacedRiskTransport(lambda _:HttpReply(200,b'{}'),limit=1,monotonic=lambda:now[0],
        sleep=sleep,before_request=lambda:actions.append('guard'))
    request=SourceRequest('finnhub','/unused',{})
    paced(request);paced(request)
    assert actions==['guard','sleep','guard'] and now[0]==61


def test_reader_counts_original_metadata_and_excludes_unknown():
    rows=[('sec',str(i),'TEST','US','Insider Transaction',NOW,meta)
          for i,meta in enumerate([{'is_purchase':True},{'is_sale':True},{}])]
    receipt=reader(Connection(rows))('TEST',NOW)
    assert receipt['row_count']==3 and receipt['counts']=={'buy_count':1,'sell_count':1,'total_count':2}


def test_factory_is_lazy_and_uses_existing_settings():
    from app.config import Settings
    from app.r2d2_v2_risk_runner import runtime_dependencies
    calls=[]
    @contextmanager
    def factory():
        calls.append('db');yield Connection()
    transport,db=runtime_dependencies(settings=Settings(),connection_factory=factory,clock=lambda:NOW)
    assert callable(transport) and calls==[]
    assert db('TEST',NOW)['transaction_read_only'] and calls==['db']


def test_final_seal_detects_tampering(tmp_path):
    original=reader(Connection())
    def tamper(symbol,cutoff):
        path=tmp_path/'batch'/'000000.database.private.json'
        if path.exists(): path.write_text('tampered')
        return original(symbol,cutoff)
    with pytest.raises(ValueError,match='SPOOL_INTEGRITY'):
        capture(tmp_path,entries=[{'symbol':'TEST','market':'US'},{'symbol':'OTHER','market':'US'}],database_reader=tamper)
    assert not (tmp_path/'batch'/'MANIFEST.json').exists()


@pytest.mark.parametrize('role', [('postgres',True), ('reader',None), ('reader',0), ('',False),
                                 (' reader',False), ('bad\nrole',False), ('x'*64,False), None])
def test_superuser_or_invalid_identity_refused_before_event_query(role):
    connection=Connection(role=role)
    with pytest.raises(ValueError,match='DATABASE_READ_ONLY_COMPARISON_FAILED'):
        reader(connection)('TEST',NOW)
    assert not any('FROM public.ir_events' in sql for sql,_ in connection.calls)


def test_private_receipt_identifies_non_superuser_role():
    connection=Connection(role=('synthetic_reader',False))
    receipt=reader(connection)('TEST',NOW)
    assert receipt['database_role']=='synthetic_reader' and receipt['is_superuser'] is False
    role_sql,params=next(call for call in connection.calls if 'pg_catalog.pg_roles' in call[0])
    assert params is None and 'current_user' in role_sql


def test_superuser_receipt_injected_cannot_trigger_provider(tmp_path):
    original=reader(Connection())
    calls=[]
    def bad(symbol,cutoff):
        receipt=original(symbol,cutoff);receipt['is_superuser']=True;return receipt
    with pytest.raises(ValueError,match='RUNNER_DATABASE_RECEIPT_INVALID'):
        capture(tmp_path,database_reader=bad,transport=lambda request:calls.append(request))
    assert not calls and not (tmp_path/'batch'/'MANIFEST.json').exists()


@pytest.mark.parametrize('position', [2,3,4,5])
def test_role_authority_refused_before_event_read(position):
    authority=['reader','reader',True,True,True,True];authority[position]=False
    connection=Connection(authority=tuple(authority))
    with pytest.raises(ValueError,match='DATABASE_READ_ONLY_COMPARISON_FAILED'):
        reader(connection)('TEST',NOW)
    assert not any('FROM public.ir_events' in sql for sql,_ in connection.calls)


@pytest.mark.parametrize('position',[1,2,3,4,5,6])
def test_acl_select_only_owner_schema_and_rls_guards(position):
    acl=['ir_events',True,True,True,True,True,True];acl[position]=False
    connection=Connection(acl=tuple(acl))
    with pytest.raises(ValueError,match='DATABASE_READ_ONLY_COMPARISON_FAILED'):
        reader(connection)('TEST',NOW)
    assert not any('FROM public.ir_events' in sql for sql,_ in connection.calls)


def test_session_identity_must_match_effective_role():
    with pytest.raises(ValueError,match='DATABASE_READ_ONLY_COMPARISON_FAILED'):
        reader(Connection(authority=('reader','owner',True,True,True,True)))('TEST',NOW)


def test_real_factory_dedicated_dsn_and_read_only_options(monkeypatch):
    import psycopg
    from app.config import Settings
    from app.r2d2_v2_risk_runner import runtime_dependencies
    calls=[]
    @contextmanager
    def connect(*args,**kwargs):
        calls.append((args,kwargs));yield Connection()
    monkeypatch.setattr(psycopg,'connect',connect)
    settings=Settings(database_url='FORBIDDEN_MAIN',r2d2_risk_database_url='PRIVATE_RESTRICTED')
    _,db=runtime_dependencies(settings=settings,clock=lambda:NOW)
    assert calls==[]
    db('TEST',NOW)
    assert calls==[(('PRIVATE_RESTRICTED',),{'connect_timeout':15,'options':'-c default_transaction_read_only=on'})]


def test_missing_dedicated_dsn_never_falls_back(monkeypatch):
    import psycopg
    from app.config import Settings
    from app.r2d2_v2_risk_runner import runtime_dependencies
    monkeypatch.setattr(psycopg,'connect',lambda *a,**k:pytest.fail('No connection allowed'))
    with pytest.raises(ValueError,match='DEDICATED_DATABASE_CONNECTION_REQUIRED'):
        runtime_dependencies(settings=Settings(database_url='DO_NOT_USE',r2d2_risk_database_url=''))


def test_non_utc_cutoff_refused_before_db_or_spool(tmp_path):
    from datetime import timedelta
    with pytest.raises(ValueError,match='RUNNER_UTC_REQUIRED'):
        capture(tmp_path,query_cutoff_at=NOW.astimezone(timezone(timedelta(hours=3))),
                database_reader=lambda *_:pytest.fail('DB forbidden'))
    assert not (tmp_path/'batch').exists()


def test_runtime_transport_rejects_fmp_before_http():
    calls=[]
    paced=PacedRiskTransport(lambda request:calls.append(request))
    with pytest.raises(ValueError,match='PROVIDER_NOT_ALLOWED'):
        paced(SourceRequest('fmp','/stable/grades',{'symbol':'TEST'}))
    assert calls==[]


def test_dedicated_database_setting_env_and_private_repr(monkeypatch):
    from app.config import Settings
    monkeypatch.setenv('C3PO_R2D2_RISK_DATABASE_URL','synthetic-dedicated-dsn')
    settings=Settings(database_url='synthetic-main',_env_file=None)
    assert settings.r2d2_risk_database_url=='synthetic-dedicated-dsn'
    assert settings.database_url=='synthetic-main'
    assert 'synthetic-dedicated-dsn' not in repr(settings)
