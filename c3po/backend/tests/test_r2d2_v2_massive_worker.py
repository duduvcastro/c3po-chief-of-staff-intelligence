from types import SimpleNamespace
import pytest
from app.r2d2_v2_shadow_worker import _with_massive_source
from app.r2d2_v2_massive_journal import MassiveJournal
from app.r2d2_v2_composite_source import CompositeEventSource


def test_default_off_has_no_massive_io(tmp_path):
 base=object();root=tmp_path/'absent'
 settings=SimpleNamespace(r2d2_v2_massive_journal_dir=root)
 assert _with_massive_source(settings,base,SimpleNamespace(mode='CERTIFIED')) is base
 assert not root.exists()


def test_enabled_worker_requires_existing_journal(tmp_path):
 root=tmp_path/'absent'
 settings=SimpleNamespace(r2d2_v2_massive_bars_enabled=True,r2d2_v2_massive_journal_dir=root)
 with pytest.raises(ValueError):_with_massive_source(settings,object(),SimpleNamespace(mode='CERTIFIED'))
 assert not root.exists()


def test_enabled_worker_uses_readonly_journal(tmp_path):
 root=tmp_path.resolve()/'journal';MassiveJournal(root)
 settings=SimpleNamespace(r2d2_v2_massive_bars_enabled=True,r2d2_v2_massive_journal_dir=root)
 result=_with_massive_source(settings,object(),SimpleNamespace(mode='CERTIFIED'))
 assert isinstance(result,CompositeEventSource)
 assert result.massive.journal.read_only
 with pytest.raises(ValueError,match='READ_ONLY'):result.massive.journal(None,{})
