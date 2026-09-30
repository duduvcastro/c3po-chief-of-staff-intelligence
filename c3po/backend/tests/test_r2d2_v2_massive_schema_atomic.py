"""Initialization is one transaction and never exposes a partial catalog."""
import sqlite3
import subprocess
import sys
from pathlib import Path
from threading import Event, Thread
import pytest
from app.r2d2_v2_massive_journal import MassiveJournal
from app.r2d2_v2_massive_sessions import SessionJournalRoot
from app.r2d2_v2_massive_session_source import MassiveSessionEventSource
from test_r2d2_v2_massive_sessions import NOW, OLD


def test_failed_schema_creation_rolls_back_all_tables(tmp_path,monkeypatch):
    def fail(db):raise RuntimeError('schema-fixture')
    monkeypatch.setattr(MassiveJournal,'_create_clock_schema',staticmethod(fail))
    with pytest.raises(RuntimeError,match='schema-fixture'):MassiveJournal(tmp_path)
    with sqlite3.connect(tmp_path/'sequence.sqlite3') as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()==[]
    # Existing uninitialized bytes are not silently blessed/recreated.
    with pytest.raises(sqlite3.OperationalError):MassiveJournal(tmp_path)


def test_process_death_during_schema_leaves_no_partial_committed_tables(tmp_path):
    catalog=SessionJournalRoot(tmp_path,'crash-schema-fixture',create=True)
    path=catalog.prepare_session(OLD,['AAPL'])
    script='''import os,sys
from app.r2d2_v2_massive_journal import MassiveJournal
def die(db):os._exit(73)
MassiveJournal._create_clock_schema=staticmethod(die)
MassiveJournal(sys.argv[1])
'''
    process=subprocess.run([sys.executable,'-B','-c',script,str(path)],check=False)
    assert process.returncode==73
    result=MassiveSessionEventSource(catalog).prepare_events(NOW,{})
    assert result['diagnostics']==[{'code':'RAW_APPEND_IN_PROGRESS'}]
    assert not result['events'] and result['cursor']=={}
    with sqlite3.connect(path/'sequence.sqlite3') as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()==[]
    assert not list((path/'receipts').iterdir())


def test_catalog_reader_during_schema_creation_defers_then_reads_ready(tmp_path,monkeypatch):
    catalog=SessionJournalRoot(tmp_path,'schema-fixture',create=True)
    path=catalog.prepare_session(OLD,['AAPL'])
    entered=Event();release=Event();failures=[]
    original=MassiveJournal._create_clock_schema
    def paused(db):
        entered.set()
        assert release.wait(10),'reader did not release schema creator'
        original(db)
    monkeypatch.setattr(MassiveJournal,'_create_clock_schema',staticmethod(paused))
    def create():
        try:
            MassiveJournal(path)
            catalog.mark_ready(OLD)
        except BaseException as exc:failures.append(exc)
    worker=Thread(target=create);worker.start()
    try:
        assert entered.wait(10)
        # An independent SQLite reader sees no receipts/retention half-schema.
        with sqlite3.connect(path/'sequence.sqlite3') as db:
            assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()==[]
        result=MassiveSessionEventSource(catalog).prepare_events(NOW,{})
        assert result['diagnostics']==[{'code':'RAW_APPEND_IN_PROGRESS'}]
        assert not result['events'] and result['cursor']=={}
        assert not (path/'ready.json').exists()
    finally:
        release.set();worker.join(10)
    assert not worker.is_alive() and not failures
    ready=MassiveSessionEventSource(catalog).prepare_events(NOW,{})
    assert not ready['diagnostics'] and not ready['events']
    assert ready['cursor']['sessions']=={OLD:0}


def test_published_empty_corrupt_schema_is_not_blessed_as_initializing(tmp_path):
    catalog=SessionJournalRoot(tmp_path,'published-schema-fixture',create=True)
    journal=catalog.ensure_session(OLD,['AAPL'])
    with journal._connect() as db:
        db.execute('DROP TABLE receipt_clocks')
        db.execute('DROP TABLE retention_state')
        db.execute('DROP TABLE receipts')
    result=MassiveSessionEventSource(catalog).prepare_events(NOW,{})
    assert result['diagnostics']==[{'code':'MASSIVE_SESSION_SOURCE_UNVERIFIED'}]
    assert not result['events'] and result['cursor']=={}
