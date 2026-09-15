"""Real local files + collector transactions; no live data or provider calls."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json

import pytest

from app import r2d2_v2_raw_source as raw
from app.r2d2_v2_calendar import ShadowCalendar
from app.r2d2_v2_sources import canonical
from app.r2d2_v2_store import ShadowIntegrityError
from tests.test_r2d2_v2_shadow_counterexamples import setup_state, INSTRUMENT

AT = datetime(2026, 9, 8, 19, 59, 40, tzinfo=timezone.utc)
NOW = AT + timedelta(seconds=5)
PART = "session_date=2026-09-08/feed=quote-part-00001.ndjson"


def line(price=101, *, feed="quote", at=AT, received=None):
    payload = {"s": "SYNTH", "t": int(at.timestamp() * 1000)}
    payload.update({"bp": price, "ap": price} if feed == "quote" else {"p": price})
    return canonical({"schema_version": 1, "provider": "EODHD", "feed": feed,
        "received_at": (received or at).isoformat(), "event_at": at.isoformat(),
        "payload_raw": json.dumps(payload)}) + b"\n"


@pytest.fixture
def source(tmp_path):
    root = tmp_path.resolve() / "source"
    root.mkdir(mode=0o700)
    (root / "events").mkdir(mode=0o700)
    spool = tmp_path.resolve() / "raw"
    (spool / "session_date=2026-09-08").mkdir(parents=True)
    return raw.SpoolShadowSource(root, raw_root=spool, first_session=date(2026, 9, 8), calendar=ShadowCalendar())


def write(source, data, part=PART):
    path = source.raw_root / part
    path.write_bytes(data)
    path.chmod(0o600)
    return path


def test_proposed_cursor_is_replayable_until_commit_and_partial_append_is_retained(source):
    first, second = line(99), line(101)
    path = write(source, first + second[:30])
    cursor = {}
    batch = source.prepare_events(NOW, cursor)
    assert cursor == {} and batch["diagnostics"] == [{"code": "RAW_APPEND_IN_PROGRESS"}]
    assert batch["events"] == []
    assert source.prepare_events(NOW, {}) == batch
    assert batch["cursor"] == {}
    with path.open("ab") as stream:
        stream.write(second[30:])
    rest = source.prepare_events(NOW, batch["cursor"])
    assert not rest["diagnostics"] and [e["bid"] for e in rest["events"]] == [99, 101]
    assert rest["events"][1]["sequence"] == 1


def test_restart_append_to_older_part_is_not_missed(source):
    first = write(source, line(99))
    write(source, line(100), PART.replace("00001", "00002"))
    batch = source.prepare_events(NOW, {})
    with first.open("ab") as stream:
        stream.write(line(102))
    rebuilt = raw.SpoolShadowSource(source.root, raw_root=source.raw_root,
                                   first_session=source.first_session, calendar=source.calendar)
    rest = rebuilt.prepare_events(NOW, batch["cursor"])
    assert not rest["diagnostics"]
    assert [e["bid"] for e in rest["events"]] == [102]


@pytest.mark.parametrize("mutation,code", [
    ("truncate", "RAW_TRUNCATED_OR_CURSOR_INVALID"),
    ("replace", "RAW_FILE_REPLACED"),
    ("rewrite", "RAW_APPEND_BOUNDARY_CHANGED"),
    ("delete", "RAW_CAPTURE_NOT_OBSERVED"),
])
def test_continuity_failure_never_advances_cursor_or_returns_partial_events(source, mutation, code):
    path = write(source, line())
    cursor = source.prepare_events(NOW, {})["cursor"]
    old = deepcopy(cursor)
    if mutation == "truncate":
        path.write_bytes(b"")
    elif mutation == "replace":
        other = path.with_suffix(".new")
        other.write_bytes(path.read_bytes())
        other.replace(path)
    elif mutation == "rewrite":
        path.write_bytes(path.read_bytes().replace(b'101', b'102'))
    else:
        path.unlink()
    batch = source.prepare_events(NOW, cursor)
    assert batch["diagnostics"] == [{"code": code}]
    assert batch["events"] == [] and batch["cursor"] == old and cursor == old


def test_joint_feed_budget_refuses_whole_batch_and_never_hides_trade(source, monkeypatch):
    quote, trade = line(), line(90, feed="trade")
    write(source, quote)
    write(source, trade, PART.replace("quote", "trade"))
    monkeypatch.setattr(raw, "MAX_CYCLE_BYTES", len(quote))
    batch = source.prepare_events(NOW, {})
    assert batch == {"events": [], "diagnostics": [{"code": "RAW_READ_BUDGET_EXCEEDED"}], "cursor": {}}


def test_symlink_is_rejected_and_does_not_read_target(source, tmp_path):
    target = tmp_path / "target"
    target.write_bytes(line())
    (source.raw_root / PART).symlink_to(target)
    batch = source.prepare_events(NOW, {})
    assert batch["events"] == [] and batch["diagnostics"]


def seed_collector(source):
    collector, state, _ = setup_state()
    collector.source = source
    for book in ("research", "portfolio"):
        state["ledger"][book]["synthetic-entry"]["maturity_at"] = "2026-09-21T19:55:00+00:00"
    state["coverage_until"][INSTRUMENT] = NOW.isoformat()
    collector.store.atomic(collector.release.epoch, collector._initial(),
                           lambda unused: (state, [], {}), AT - timedelta(seconds=1))
    return collector


def test_real_collector_commits_first_positive_and_cursor_together_then_restarts(source):
    write(source, line(99) + line(101) + line(103))
    collector = seed_collector(source)
    collector.cycle(NOW)
    saved = collector.store.read(collector.release.epoch)
    assert saved["state"]["raw_source_cursor"]["files"][PART]["sequence"] == 3
    for book in ("research", "portfolio"):
        row = saved["state"]["ledger"][book]["synthetic-entry"]
        assert row["exit_cause"] == "EOD_POSITIVE" and row["exit_price"] == 101
        assert row["exit_at"] == NOW.isoformat()
    journal = collector.store.journal(collector.release.epoch)
    assert len([r for r in journal if r["payload"]["type"] == "SOURCE_EVENT"]) == 3
    assert len([r for r in journal if r["payload"]["type"] == "SOURCE_CURSOR"]) == 1
    collector.source = raw.SpoolShadowSource(source.root, raw_root=source.raw_root,
        first_session=source.first_session, calendar=source.calendar)
    collector.cycle(NOW + timedelta(seconds=1))
    assert collector.store.read(collector.release.epoch)["state"]["event_receipts"] == saved["state"]["event_receipts"]
    assert collector.store.journal(collector.release.epoch) == journal


def test_failed_commit_does_not_lose_raw_quote_or_cursor(source, monkeypatch):
    write(source, line())
    collector = seed_collector(source)
    before = collector.store.read(collector.release.epoch)
    atomic = collector.store.atomic

    def fail(epoch, initial, transition, now):
        def wrapped(state):
            state, records, response = transition(state)
            assert state["raw_source_cursor"] and any(r["type"] == "SOURCE_CURSOR" for r in records)
            raise RuntimeError("synthetic commit failure")
        return atomic(epoch, initial, wrapped, now)

    monkeypatch.setattr(collector.store, "atomic", fail)
    with pytest.raises(RuntimeError, match="commit failure"):
        collector.cycle(NOW)
    assert collector.store.read(collector.release.epoch) == before
    monkeypatch.setattr(collector.store, "atomic", atomic)
    collector.cycle(NOW)
    saved = collector.store.read(collector.release.epoch)["state"]
    assert saved["raw_source_cursor"] and saved["ledger"]["research"]["synthetic-entry"]["exit_cause"] == "EOD_POSITIVE"


def test_same_snapshot_trade_stop_precedes_quote_across_two_spool_files(source):
    write(source, line(103))
    write(source, line(90, feed="trade", received=AT + timedelta(seconds=1)), PART.replace("quote", "trade"))
    collector = seed_collector(source)
    collector.cycle(NOW)
    saved = collector.store.read(collector.release.epoch)["state"]
    assert all(saved["ledger"][book]["synthetic-entry"]["exit_cause"] == "STOP" for book in ("research", "portfolio"))


def test_concurrent_cursor_change_is_refused(source):
    collector = seed_collector(source)
    state = collector.store.read(collector.release.epoch)["state"]
    state["raw_source_cursor"] = {"files": {"newer": {}}}
    with pytest.raises(ShadowIntegrityError, match="CURSOR_CONCURRENT"):
        collector._cycle_with_cursor(state, {}, [], [], NOW, causal=None, cursor={}, next_cursor={})


def test_partial_trade_does_not_expose_positive_quote_from_other_file(source):
    write(source, line(103))
    write(source, line(90, feed="trade")[:-15], PART.replace("quote", "trade"))
    batch = source.prepare_events(NOW, {})
    assert batch == {"events": [], "diagnostics": [{"code": "RAW_APPEND_IN_PROGRESS"}], "cursor": {}}


def test_raw_receipts_are_bounded_in_epoch_state_and_remain_verified_by_p5(source):
    from app.r2d2_v2_counterfactual_archive import summarize
    from app.r2d2_v2_store import digest
    write(source, line(99) + line(101) + line(103))
    collector = seed_collector(source)
    collector.cycle(NOW)
    saved, journal = collector.store.read_with_journal(collector.release.epoch)
    assert saved['state']['event_receipts'] == {}
    cursor_records = [r for r in journal if r['payload']['type'] == 'SOURCE_CURSOR']
    assert len(cursor_records[0]['payload']['raw_receipts']) == 3
    result = summarize(saved, journal, sessions=['2026-09-08'], cutoff=NOW.isoformat())
    assert result['archive_status'] == 'VERIFIED' and result['archive_record_count'] == 3
    changed = deepcopy(saved)
    changed['state']['raw_source_cursor']['files'][PART]['sequence'] += 1
    changed['state_sha'] = digest(changed['state'])
    with pytest.raises(ShadowIntegrityError, match='RAW_CURSOR_HEAD'):
        summarize(changed, journal, sessions=['2026-09-08'], cutoff=NOW.isoformat())


def test_failed_source_leaves_durable_cursor_unchanged(source):
    write(source, line(99))
    collector = seed_collector(source)
    collector.cycle(NOW)
    before = collector.store.read(collector.release.epoch)['state']['raw_source_cursor']
    with (source.raw_root / PART).open('ab') as stream:
        stream.write(b'partial')
    collector.cycle(NOW + timedelta(seconds=1))
    after = collector.store.read(collector.release.epoch)['state']
    assert after['raw_source_cursor'] == before
    assert after['data_issues']


@pytest.mark.parametrize('mode', ['CERTIFIED', 'DIAGNOSTIC'])
def test_worker_binds_existing_spool_only_for_certified_without_starting_capture(tmp_path, monkeypatch, mode):
    from hashlib import sha256
    from types import SimpleNamespace
    from app import database, r2d2_v2_shadow_worker as worker
    from tests.test_r2d2_v2_store_worker import release_body, BUILD, NOW as APPROVED_NOW

    class NoDatabaseIO:
        def __init__(self, settings):
            pass
        def connection(self):
            pytest.fail('Construction must not query the database')
        def initialize(self):
            pytest.fail('Construction must not migrate')

    monkeypatch.setattr(database, 'Database', NoDatabaseIO)
    data = canonical(release_body(mode))
    release = tmp_path / 'release.json'
    release.write_bytes(data)
    release.chmod(0o600)
    settings = SimpleNamespace(r2d2_v2_shadow_enabled=True, database_url='synthetic-only',
        r2d2_v2_shadow_release_file=str(release), r2d2_v2_shadow_release_sha=sha256(data).hexdigest(),
        build_sha=BUILD, r2d2_v2_shadow_source_dir=tmp_path / 'source',
        r2d2_microstructure_raw_dir=tmp_path / 'existing-raw')
    collector = worker.build_collector(settings, now=APPROVED_NOW)
    assert isinstance(collector.source, raw.SpoolShadowSource) is (mode == 'CERTIFIED')
    assert not settings.r2d2_microstructure_raw_dir.exists()
    assert not settings.r2d2_v2_shadow_source_dir.exists()
