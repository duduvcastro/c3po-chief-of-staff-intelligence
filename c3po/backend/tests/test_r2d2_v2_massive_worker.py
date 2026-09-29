from types import SimpleNamespace
import pytest
from app.r2d2_v2_shadow_worker import _with_massive_source
from app.r2d2_v2_massive_journal import MassiveJournal
from app.r2d2_v2_massive_sessions import SessionJournalRoot

EPOCH='R2D2-V2-SHADOW-WORKER-SESSION'
from app.r2d2_v2_composite_source import CompositeEventSource


def test_default_off_has_no_massive_io(tmp_path):
 base=object();root=tmp_path/'absent'
 settings=SimpleNamespace(r2d2_v2_massive_journal_dir=root)
 assert _with_massive_source(settings,base,SimpleNamespace(mode='CERTIFIED',epoch=EPOCH)) is base
 assert not root.exists()


def test_enabled_worker_requires_existing_journal(tmp_path):
 root=tmp_path/'absent'
 settings=SimpleNamespace(r2d2_v2_massive_bars_enabled=True,r2d2_v2_massive_journal_dir=root)
 with pytest.raises(ValueError):_with_massive_source(settings,object(),SimpleNamespace(mode='CERTIFIED',epoch=EPOCH))
 assert not root.exists()


def test_enabled_worker_uses_readonly_journal(tmp_path):
 root=tmp_path.resolve()/'journal';root.mkdir(mode=0o700)
 journals=SessionJournalRoot(root,EPOCH,create=True)
 journals.ensure_session('2026-09-28',['AAPL'])
 settings=SimpleNamespace(r2d2_v2_massive_bars_enabled=True,r2d2_v2_massive_journal_dir=root)
 result=_with_massive_source(settings,object(),SimpleNamespace(mode='CERTIFIED',epoch=EPOCH))
 assert isinstance(result,CompositeEventSource)
 reader=result.massive.journals.open_session('2026-09-28')
 assert reader.read_only
 with pytest.raises(ValueError,match='READ_ONLY'):reader(None,{})


def test_enabled_worker_rejects_flat_journal_without_implicit_migration(tmp_path):
 MassiveJournal(tmp_path)
 settings=SimpleNamespace(r2d2_v2_massive_bars_enabled=True,r2d2_v2_massive_journal_dir=tmp_path)
 with pytest.raises(ValueError,match='MASSIVE_SESSION_ROOT_UNVERIFIED'):
  _with_massive_source(settings,object(),SimpleNamespace(mode='CERTIFIED',epoch=EPOCH))
 assert not (tmp_path/'epoch.json').exists()


def test_enabled_worker_rejects_another_release_epoch(tmp_path):
 SessionJournalRoot(tmp_path,EPOCH,create=True)
 settings=SimpleNamespace(r2d2_v2_massive_bars_enabled=True,r2d2_v2_massive_journal_dir=tmp_path)
 with pytest.raises(ValueError,match='MASSIVE_SESSION_ROOT_UNVERIFIED'):
  _with_massive_source(settings,object(),SimpleNamespace(mode='CERTIFIED',epoch='OTHER'))
