"""Revocation and empty-poll persistence counterexamples; no database/server."""
from datetime import datetime, timezone
from hashlib import sha256
from types import SimpleNamespace

import pytest

from app.r2d2_v2_shadow_worker import recheck_release
from app.r2d2_v2_store import MemoryShadowStore, PostgresShadowStore, ShadowIntegrityError, digest

NOW = datetime(2026, 9, 6, 21, tzinfo=timezone.utc)
EPOCH = "R2D2-V2-SHADOW-RUNTIME"


def state():
    return {"epoch": EPOCH, "manifest_sha": "a" * 64, "release_sha": "b" * 64, "value": 0}


def test_empty_poll_does_not_change_version_hash_or_journal():
    store = MemoryShadowStore()
    store.atomic(EPOCH, state(), lambda s: (s, [], {}), NOW)
    before = store.read(EPOCH)
    for _ in range(20):
        assert store.atomic(EPOCH, state(), lambda s: (s, [], {"idle": True}), NOW) == {"idle": True}
    assert store.read(EPOCH) == before
    assert store.journal(EPOCH) == []
    def real_change(s):
        s["value"] = 1
        return s, [{"journal_key": "changed"}], {}
    store.atomic(EPOCH, state(), real_change, NOW)
    assert store.read(EPOCH)["version"] == before["version"] + 1
    assert len(store.journal(EPOCH)) == 1


def test_empty_poll_still_detects_state_corruption():
    store = MemoryShadowStore()
    store.atomic(EPOCH, state(), lambda s: (s, [], {}), NOW)
    store._rows[EPOCH]["state"]["value"] = 100
    with pytest.raises(ShadowIntegrityError, match="STATE_HASH_MISMATCH"):
        store.atomic(EPOCH, state(), lambda s: (s, [], {}), NOW)


def test_postgres_empty_poll_keeps_row_lock_but_omits_jsonb_update():
    class Connection:
        def __init__(self):
            self.queries = []
            self.commits = 0
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def execute(self, sql, args):
            self.queries.append(sql)
            if "SELECT state,state_sha" in sql:
                result = (state(), digest(state()), "a" * 64, 7, "")
            elif "MAX(sequence)" in sql:
                result = (0,)
            else:
                result = None
            return SimpleNamespace(fetchone=lambda: result)
        def commit(self):
            self.commits += 1
    connection = Connection()
    result = PostgresShadowStore(lambda: connection).atomic(
        EPOCH, state(), lambda s: (s, [], {"idle": True}), NOW)
    assert result == {"idle": True}
    assert any("FOR UPDATE" in q for q in connection.queries)
    assert not any(q.lstrip().startswith("UPDATE") for q in connection.queries)
    assert not any("INSERT INTO r2d2_v2_shadow_journal" in q for q in connection.queries)
    assert connection.commits == 1


@pytest.mark.parametrize("mode,epoch", [
    ("DIAGNOSTIC", EPOCH), ("CERTIFIED", "R2D2-V2-DIAG-RUNTIME")])
def test_epoch_mode_namespace_cannot_be_crossed(mode, epoch):
    initial = state() | {"mode": mode, "epoch": epoch}
    with pytest.raises(ShadowIntegrityError, match="EPOCH_MODE_NAMESPACE_MISMATCH"):
        MemoryShadowStore().atomic(epoch, initial, lambda s: (s, [], {}), NOW)


@pytest.mark.parametrize("replacement", ["CERTIFIED", None, "INVALID", "REMOVE"])
def test_transition_cannot_promote_or_erase_diagnostic_mode(replacement):
    epoch = "R2D2-V2-DIAG-RUNTIME"
    initial = state() | {"epoch": epoch, "mode": "DIAGNOSTIC"}
    store = MemoryShadowStore()
    store.atomic(epoch, initial, lambda s: (s, [], {}), NOW)
    before = store.read(epoch)
    def promote(s):
        if replacement == "REMOVE":
            s.pop("mode")
        else:
            s["mode"] = replacement
        return s, [{"journal_key": "forbidden-promotion"}], {}
    with pytest.raises(ShadowIntegrityError, match="EPOCH_MODE_CHANGED"):
        store.atomic(epoch, initial, promote, NOW)
    assert store.read(epoch) == before
    assert store.journal(epoch) == []


@pytest.fixture
def pinned(tmp_path):
    path = tmp_path / "release.json"
    data = b'{"synthetic_receipt":"already validated at startup"}'
    path.write_bytes(data)
    path.chmod(0o600)
    signature = sha256(data).hexdigest()
    settings = SimpleNamespace(r2d2_v2_shadow_enabled=True, build_sha="c" * 40,
        r2d2_v2_shadow_release_sha=signature, r2d2_v2_shadow_release_file=str(path))
    collector = SimpleNamespace(release=SimpleNamespace(code_revision="c" * 40, receipt_sha=signature))
    return path, settings, collector


def test_pinned_release_check_does_not_rebuild_runtime(monkeypatch, pinned):
    from app import r2d2_v2_shadow_worker as worker
    def forbidden(*args, **kwargs):
        pytest.fail("polling rebuilt runtime")
    monkeypatch.setattr(worker, "ShadowCalendar", forbidden)
    monkeypatch.setattr(worker, "build_collector", forbidden)
    _, settings, collector = pinned
    recheck_release(settings, collector)


@pytest.mark.parametrize("change", ["bytes", "settings_sha", "build", "disable", "permissions", "delete"])
def test_release_revocation_is_detected_before_another_cycle(change, pinned):
    path, settings, collector = pinned
    if change == "bytes":
        path.write_bytes(b"changed")
    elif change == "settings_sha":
        settings.r2d2_v2_shadow_release_sha = "d" * 64
    elif change == "build":
        settings.build_sha = "d" * 40
    elif change == "disable":
        settings.r2d2_v2_shadow_enabled = False
    elif change == "permissions":
        path.chmod(0o644)
    else:
        path.unlink()
    with pytest.raises((ShadowIntegrityError, FileNotFoundError)):
        recheck_release(settings, collector)
