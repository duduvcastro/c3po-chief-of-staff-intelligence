"""Synthetic store/release/worker tests. SQL spies are not a PostgreSQL integration test.

No local postgres/initdb/pg_ctl or Docker runtime was available during authoring;
no external database is contacted by this file.
"""
from __future__ import annotations

import builtins
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
from threading import Barrier
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.r2d2_v2_calendar import ShadowCalendar
from app.r2d2_v2_shadow import Release, ShadowCollector, export_cohort, public_summary
from app.r2d2_v2_sources import MANIFEST_SHA
from app.r2d2_v2_store import (
    MemoryShadowStore, PostgresShadowStore, ShadowIntegrityError, canonical, digest,
)
from app import r2d2_v2_shadow_worker as worker

NOW = datetime(2026, 9, 6, 20, tzinfo=timezone.utc)
EPOCH = "R2D2-V2-SHADOW-SYNTHETIC-TEST"
BUILD = "a" * 40
RECEIPT = "b" * 64


def initial(epoch=EPOCH, release=RECEIPT):
    return {"epoch": epoch, "manifest_sha": MANIFEST_SHA, "release_sha": release, "ids": []}


def add_id(identity):
    def transition(state):
        if identity in state['ids']:
            return state, [], {'id': identity, 'inserted': False}
        state['ids'].append(identity)
        return state, [{'journal_key': identity, 'type': 'SYNTHETIC_INSERT'}], {'id': identity, 'inserted': True}
    return transition


def assert_chain(row, records):
    head = ''
    for index, record in enumerate(records, 1):
        assert record['sequence'] == index
        assert record['epoch'] == EPOCH
        assert record['previous_sha'] == head
        expected = digest({k: v for k, v in record.items() if k != 'record_sha'})
        assert record['record_sha'] == expected
        head = expected
    assert row['journal_head'] == head
    assert row['sequence'] == len(records)
    assert digest(row['state']) == row['state_sha']


def test_memory_atomic_32_simultaneous_collectors_preserve_all_ids_and_chain():
    store, gate = MemoryShadowStore(), Barrier(32)
    def run(index):
        gate.wait(timeout=10)
        return store.atomic(EPOCH, initial(), add_id(f'fixture-{index}'), NOW)
    with ThreadPoolExecutor(max_workers=32) as pool:
        results = list(pool.map(run, range(32)))
    assert all(result['inserted'] for result in results)
    row, journal = store.read(EPOCH), store.journal(EPOCH)
    assert set(row['state']['ids']) == {f'fixture-{i}' for i in range(32)}
    assert len(journal) == len({r['journal_key'] for r in journal}) == 32
    assert row['version'] == 32
    assert_chain(row, journal)


def test_memory_idempotent_transition_does_not_append_duplicate_evidence():
    store = MemoryShadowStore()
    assert store.atomic(EPOCH, initial(), add_id('once'), NOW)['inserted']
    assert not store.atomic(EPOCH, initial(), add_id('once'), NOW)['inserted']
    assert store.read(EPOCH)['state']['ids'] == ['once']
    assert len(store.journal(EPOCH)) == 1
    assert_chain(store.read(EPOCH), store.journal(EPOCH))


def test_memory_callback_failure_rolls_back_state_and_journal_existing_and_new():
    store = MemoryShadowStore()
    store.atomic(EPOCH, initial(), add_id('before'), NOW)
    old, journal = store.read(EPOCH), store.journal(EPOCH)
    def fail(state):
        state['ids'].append('must-not-commit')
        raise RuntimeError('synthetic callback failed')
    with pytest.raises(RuntimeError, match='synthetic callback failed'):
        store.atomic(EPOCH, initial(), fail, NOW)
    assert store.read(EPOCH) == old and store.journal(EPOCH) == journal
    other = 'R2D2-V2-SHADOW-NEW'
    with pytest.raises(RuntimeError):
        store.atomic(other, initial(other), fail, NOW)
    assert store.read(other) is None and store.journal(other) == []


@pytest.mark.parametrize('duplicate_existing', [False, True])
def test_memory_journal_conflict_rolls_back_the_whole_transition(duplicate_existing):
    store = MemoryShadowStore()
    store.atomic(EPOCH, initial(), add_id('existing'), NOW)
    before, journal = store.read(EPOCH), store.journal(EPOCH)
    def conflict(state):
        state['ids'].append('not-committed')
        key = 'existing' if duplicate_existing else 'new-duplicate'
        payloads = [{'journal_key': key}] if duplicate_existing else [{'journal_key': key}, {'journal_key': key}]
        return state, payloads, {}
    with pytest.raises(ShadowIntegrityError, match='JOURNAL_KEY_CONFLICT'):
        store.atomic(EPOCH, initial(), conflict, NOW)
    assert store.read(EPOCH) == before and store.journal(EPOCH) == journal


def test_memory_detects_hash_corruption_before_read_or_callback():
    store = MemoryShadowStore()
    store.atomic(EPOCH, initial(), add_id('original'), NOW)
    store._rows[EPOCH]['state']['ids'].append('synthetic-corruption')
    with pytest.raises(ShadowIntegrityError, match='STATE_HASH_MISMATCH'):
        store.read(EPOCH)
    def forbidden(state):
        pytest.fail('callback must not run over corrupt state')
    with pytest.raises(ShadowIntegrityError, match='STATE_HASH_MISMATCH'):
        store.atomic(EPOCH, initial(), forbidden, NOW)
    assert len(store.journal(EPOCH)) == 1


def test_memory_returns_detached_state_journal_and_response():
    store = MemoryShadowStore()
    answer = store.atomic(EPOCH, initial(), add_id('original'), NOW)
    answer['id'] = 'changed'
    exposed = store.read(EPOCH)
    exposed['state']['ids'].append('foreign')
    journal = store.journal(EPOCH)
    journal[0]['payload']['type'] = 'foreign'
    assert store.read(EPOCH)['state']['ids'] == ['original']
    assert store.journal(EPOCH)[0]['payload']['type'] == 'SYNTHETIC_INSERT'
    assert_chain(store.read(EPOCH), store.journal(EPOCH))


def test_memory_release_cannot_be_replaced_within_existing_epoch():
    store = MemoryShadowStore()
    store.atomic(EPOCH, initial(), add_id('original'), NOW)
    before = store.read(EPOCH)
    with pytest.raises(ShadowIntegrityError, match='RELEASE_REQUIRES_NEW_EPOCH'):
        store.atomic(EPOCH, initial(release='c'*64), add_id('new'), NOW)
    assert store.read(EPOCH) == before


@pytest.mark.parametrize('field,value', [('epoch','R2D2-V2-SHADOW-OTHER'),('manifest_sha','d'*64),('release_sha','e'*64)])
def test_memory_transition_cannot_change_frozen_identity(field,value):
    store = MemoryShadowStore()
    def alter(state):
        state[field] = value
        return state, [], {}
    with pytest.raises(ShadowIntegrityError, match='EPOCH_IDENTITY_CHANGED'):
        store.atomic(EPOCH, initial(), alter, NOW)
    assert store.read(EPOCH) is None


@pytest.fixture(scope='module')
def calendar():
    return ShadowCalendar()


def release_body(mode='CERTIFIED'):
    return {'schema':'R2D2_V2_RELEASE_V1','manifest_sha':MANIFEST_SHA,'epoch':EPOCH,
            'mode':mode,'first_session':'2026-09-08','approved_at':'2026-09-06T19:00:00+00:00',
            'code_revision':BUILD,'code_audit_sha':'c'*64,'authorization_ref':'synthetic-owner-approval',
            'calibration_status':'ACCEPTED','calibration_sha':'d'*64,'source_audit_sha':'e'*64}


def verify(body, calendar, **kwargs):
    data = canonical(body)
    return Release.verify(data, sha256(data).hexdigest(), now=NOW, build_sha=BUILD, calendar=calendar, **kwargs)


def test_release_validated_and_first_session_is_the_predetermined_date(calendar):
    release = verify(release_body(), calendar)
    assert release.first_session == date(2026,9,8)
    assert release.approved_at < calendar.details(release.first_session)['open']
    assert release.code_revision == BUILD and release.mode == 'CERTIFIED'
    assert release.receipt_sha == sha256(canonical(release_body())).hexdigest()


@pytest.mark.parametrize('status', [None,'PENDING','FAILED','REJECTED','accepted'])
def test_certified_release_rejects_calibration_not_explicitly_accepted(calendar,status):
    with pytest.raises(ShadowIntegrityError, match='CALIBRATION_AND_SOURCES_REQUIRED'):
        verify(release_body() | {'calibration_status':status}, calendar)


@pytest.mark.parametrize('field', ['calibration_sha','source_audit_sha','code_audit_sha','authorization_ref'])
def test_certified_release_rejects_each_missing_approval_reference(calendar,field):
    body = release_body();del body[field]
    with pytest.raises(ShadowIntegrityError):
        verify(body,calendar)


@pytest.mark.parametrize('field', ['calibration_sha','source_audit_sha','code_audit_sha'])
def test_release_rejects_malformed_hashes(calendar,field):
    with pytest.raises(ShadowIntegrityError):
        verify(release_body() | {field:'not-a-sha'},calendar)


def test_release_wrong_build_wrong_policy_and_wrong_file_hash_are_rejected(calendar):
    body = release_body()
    with pytest.raises(ShadowIntegrityError, match='RELEASE_CODE_OR_AUTHORIZATION_UNVERIFIED'):
        verify(body | {'code_revision':'f'*40},calendar)
    with pytest.raises(ShadowIntegrityError, match='RELEASE_POLICY_MISMATCH'):
        verify(body | {'manifest_sha':'f'*64},calendar)
    data = canonical(body)
    with pytest.raises(ShadowIntegrityError, match='RELEASE_HASH_MISMATCH'):
        Release.verify(data,'0'*64,now=NOW,build_sha=BUILD,calendar=calendar)


def test_release_requires_approval_before_now_and_before_first_market_open(calendar):
    with pytest.raises(ShadowIntegrityError, match='RELEASE_MUST_PRECEDE_FIRST_SESSION'):
        verify(release_body() | {'approved_at':(NOW+timedelta(seconds=1)).isoformat()},calendar)
    body = release_body() | {'first_session':'2026-09-04'}
    with pytest.raises(ShadowIntegrityError, match='RELEASE_MUST_PRECEDE_FIRST_SESSION'):
        verify(body,calendar)
    opening = calendar.details(date(2026,9,8))['open']
    body = release_body() | {'approved_at':opening.isoformat()}
    data = canonical(body)
    with pytest.raises(ShadowIntegrityError, match='RELEASE_MUST_PRECEDE_FIRST_SESSION'):
        Release.verify(data,sha256(data).hexdigest(),now=opening,build_sha=BUILD,calendar=calendar)


def test_diagnostic_release_has_no_ledger_clock_or_certifiable_cohort(calendar):
    body = release_body('DIAGNOSTIC')
    for key in ('calibration_sha','calibration_status','source_audit_sha'):body.pop(key)
    diagnostic = verify(body,calendar)
    collector = ShadowCollector(MemoryShadowStore(),object(),diagnostic,calendar=calendar)
    state = collector._initial()
    assert state['ledger'] is None and state['mode'] == 'DIAGNOSTIC'
    assert public_summary(state)['cohort_clock_started'] is False
    for size in (20,30):
        with pytest.raises(ShadowIntegrityError, match='COHORT_NOT_AUTHORIZED'):
            export_cohort(state,size,now=NOW,calendar=calendar)
    certified = verify(release_body(),calendar)
    store = MemoryShadowStore()
    store.atomic(diagnostic.epoch,state,lambda s:(s,[],{}),NOW)
    with pytest.raises(ShadowIntegrityError, match='RELEASE_REQUIRES_NEW_EPOCH'):
        store.atomic(certified.epoch,{**state,'release_sha':certified.receipt_sha},lambda s:(s,[],{}),NOW)


def test_calendar_has_exact_windows_holidays_dst_and_early_close(calendar):
    first = date(2026,9,8)
    details = calendar.details(first)
    assert len(details['previous_sessions']) == 61
    assert details['previous_sessions'][-1] == date(2026,9,4)
    assert not calendar.is_session(date(2026,9,7))
    assert len(details['horizon_sessions']) == 10 and details['horizon_sessions'][0] == first
    assert len(calendar.sessions(first,39)) == 39
    assert details['capture_open'].hour == 14
    assert calendar.details(date(2026,11,2))['capture_open'].hour == 15
    early = calendar.details(date(2026,11,27))
    assert early['close'].astimezone(ZoneInfo('America/New_York')).hour == 13
    assert calendar.regular(early['open'],end=early['close'])
    assert not calendar.regular(early['open'],end=early['close']+timedelta(microseconds=1))
    assert not calendar.regular(datetime(2026,9,7,14,tzinfo=timezone.utc))


def test_worker_off_never_accesses_settings_beyond_enabled_or_files(monkeypatch):
    class OffSettings:
        r2d2_v2_shadow_enabled = False
        def __getattr__(self,name):
            pytest.fail(f'OFF accessed setting {name}')
    def forbidden(*args,**kwargs):pytest.fail('OFF attempted filesystem access')
    monkeypatch.setattr(worker.os,'open',forbidden)
    monkeypatch.setattr(worker,'ShadowCalendar',forbidden)
    assert worker.build_collector(OffSettings(),now=NOW) is None


def test_worker_enabled_without_database_refuses_before_reading_release(monkeypatch):
    def forbidden(*args,**kwargs):pytest.fail('release file read without a database setting')
    monkeypatch.setattr(worker.os,'open',forbidden)
    with pytest.raises(ShadowIntegrityError,match='PERSISTENT_DATABASE_REQUIRED'):
        worker.build_collector(SimpleNamespace(r2d2_v2_shadow_enabled=True,database_url=''),now=NOW)


def test_worker_capabilities_does_not_import_settings_database_or_read_files(monkeypatch,capsys):
    original = builtins.__import__
    def guarded_import(name,*args,**kwargs):
        if name in ('config','database','app.config','app.database'):
            pytest.fail('capabilities imported runtime settings or database')
        return original(name,*args,**kwargs)
    def forbidden(*args,**kwargs):pytest.fail('capabilities attempted runtime access')
    monkeypatch.setattr(builtins,'__import__',guarded_import)
    monkeypatch.setattr(worker.os,'open',forbidden)
    monkeypatch.setattr(worker,'build_collector',forbidden)
    assert worker.main(['--capabilities']) == 0
    public = json.loads(capsys.readouterr().out)
    assert public['production_ready'] is False
    assert public['activation_blocked_until_audited_producer'] is True
    assert public['missing_producer_contracts']


class SQLSpy:
    """Models context rollback and SQL ordering only, not PostgreSQL locking/JSONB."""
    def __init__(self, fail_journal=False):
        self.calls=[];self.commits=0;self.rolled_back=False;self.fail_journal=fail_journal;self.state=initial()
    def __enter__(self):return self
    def __exit__(self,kind,error,traceback):self.rolled_back=kind is not None
    def execute(self,sql,parameters):
        sql=' '.join(sql.split());self.calls.append((sql,parameters))
        if 'INSERT INTO r2d2_v2_shadow_epochs' in sql:
            self.state=json.loads(parameters[2])
        if 'INSERT INTO r2d2_v2_shadow_journal' in sql and self.fail_journal:
            raise RuntimeError('synthetic journal constraint failure')
        if 'SELECT state,state_sha,manifest_sha' in sql:
            result=(self.state,digest(self.state),self.state['manifest_sha'],0,'')
        elif 'SELECT COALESCE(MAX(sequence),0)' in sql:result=(0,)
        else:result=None
        return SimpleNamespace(fetchone=lambda:deepcopy(result))
    def commit(self):self.commits+=1


def test_postgres_protocol_locks_epoch_before_sequence_and_commits_state_with_journal():
    connection=SQLSpy();store=PostgresShadowStore(lambda:connection)
    assert store.atomic(EPOCH,initial(),add_id('once'),NOW)['inserted']
    queries=[q for q,_ in connection.calls]
    lock=next(i for i,q in enumerate(queries) if 'FOR UPDATE' in q)
    maximum=next(i for i,q in enumerate(queries) if 'MAX(sequence)' in q)
    journal=next(i for i,q in enumerate(queries) if 'INSERT INTO r2d2_v2_shadow_journal' in q)
    update=next(i for i,q in enumerate(queries) if q.startswith('UPDATE'))
    assert lock<maximum<journal<update
    assert connection.commits==1 and not connection.rolled_back
    assert all('r2d2_v2_shadow_' in q for q in queries)
    assert not any('CREATE ' in q or 'r2d2_positions' in q or 'r2d2_trades' in q for q in queries)


@pytest.mark.parametrize('fail_journal',[False,True])
def test_postgres_protocol_callback_or_journal_failure_exits_without_commit(fail_journal):
    connection=SQLSpy(fail_journal);store=PostgresShadowStore(lambda:connection)
    def fail(state):
        state['ids'].append('not-committed')
        raise RuntimeError('synthetic callback failed')
    transition=add_id('once') if fail_journal else fail
    with pytest.raises(RuntimeError):store.atomic(EPOCH,initial(),transition,NOW)
    assert connection.commits==0 and connection.rolled_back
    assert not any(q.startswith('UPDATE') for q,_ in connection.calls)


@pytest.mark.parametrize('backend',['memory','postgres-spy'])
def test_store_rejects_initial_epoch_different_from_transaction_namespace(backend):
    connection=SQLSpy()
    store=MemoryShadowStore() if backend=='memory' else PostgresShadowStore(lambda:connection)
    mismatched=initial(epoch='R2D2-V2-SHADOW-OTHER')
    with pytest.raises(ShadowIntegrityError):
        store.atomic(EPOCH,mismatched,add_id('must-not-cross-epochs'),NOW)
    if backend=='memory':
        assert store.read(EPOCH) is None
    else:
        assert connection.commits==0
