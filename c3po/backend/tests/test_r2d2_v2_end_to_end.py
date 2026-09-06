"""Synthetic private spool -> real policy/ledger -> durable store/export gates."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256

import pytest

from app.r2d2_v2_calendar import ShadowCalendar
from app.r2d2_v2_causal_list import DAILY_SCHEMA, REGISTRY_SCHEMA, build_commitment
from app.r2d2_v2_shadow import Release, ShadowCollector, export_cohort
from app.r2d2_v2_sources import FileShadowSource, MANIFEST_SHA, AMENDMENT_SHA, canonical
from app.r2d2_v2_store import MemoryShadowStore, ShadowIntegrityError, digest, utc

DAY = date(2026, 9, 8)
EPOCH = "R2D2-V2-SHADOW-INTEGRATION-FIXTURE"


def write(path, body):
    body = deepcopy(body)
    body.pop("self_sha256", None)
    body["self_sha256"] = digest(body)
    path.write_bytes(canonical(body))
    path.chmod(0o600)
    return body


def causal_source(root, calendar, rows):
    previous = calendar.details(DAY)["previous_sessions"][-1]
    close = calendar.details(previous)["close"]
    available = (close + timedelta(minutes=2)).isoformat()
    registry = dict(schema=REGISTRY_SCHEMA, source_id="synthetic-registry",
        source_at=(close + timedelta(seconds=1)).isoformat(), available_at=available, captured_at=available,
        coverage_verified=True, instruments=[{key: row[key] for key in
            ("symbol", "market", "security_type", "classification_verified")} for row in rows])
    daily_rows = []
    for row in rows:
        daily = deepcopy(row["daily"])
        daily.update(source_at=close.isoformat(), available_at=available)
        daily_rows.append({"symbol": row["symbol"], "daily": daily})
    daily = dict(schema=DAILY_SCHEMA, source_id="synthetic-daily", source_at=close.isoformat(),
        available_at=available, instruments=daily_rows)
    commitment = build_commitment(epoch=EPOCH, day=DAY, built_at=close+timedelta(minutes=5),
        calendar=calendar, registry_bytes=canonical(registry), daily_bytes=canonical(daily))
    binding = {key: commitment[key] for key in ("epoch", "session", "manifest_sha", "amendment_sha", "list_sha256", "n_cut")}
    binding["commitment_sha256"] = digest(commitment)
    audit = dict(event_id="synthetic-build", event_type="r2d2.v2.causal_list_built",
                 occurred_at=commitment["built_at"], payload=binding)
    published = (close+timedelta(minutes=6)).isoformat()
    publication = dict(event_id="synthetic-publication", event_type="r2d2.v2.causal_list_published",
        occurred_at=published, payload={**binding, "build_audit_event_id": audit["event_id"],
            "channel": "relay", "publication_reference": "synthetic/list.json", "published_at": published})
    envelope = {"commitment": commitment, "audit_receipt": audit, "publication_receipt": publication}
    directory = root / "causal_list" / EPOCH
    directory.mkdir(parents=True, mode=0o700)
    (root / "causal_list").chmod(0o700)
    target = directory / (DAY.isoformat()+".json")
    target.write_bytes(canonical(envelope)); target.chmod(0o600)
    persisted = {item["event_id"]: deepcopy(item) for item in (audit, publication)}
    def verify(receipt, expected):
        actual = persisted.get(receipt["event_id"])
        return actual == receipt and {key: actual[key] for key in expected} == expected
    return FileShadowSource(root, causal_receipt_verifier=verify)


@pytest.fixture
def rig(tmp_path):
    calendar = ShadowCalendar()
    now = calendar.details(DAY)["capture_open"] + timedelta(seconds=5)
    root = tmp_path.resolve() / "source"
    root.mkdir(mode=0o700)
    (root / "events").mkdir(mode=0o700)
    rows = []
    for name, risk in (("SYNTHA", 20), ("SYNTHB", 80)):
        daily = []
        for day in calendar.details(DAY)["previous_sessions"]:
            close = calendar.details(day)["close"].isoformat()
            daily.append(dict(session_date=day.isoformat(), open=100, high=101, low=99, close=100,
                volume=200_000, complete=True, regular_session=True, source_at=close, available_at=close))
        stamp = now.isoformat()
        rows.append(dict(symbol=name, market="NASDAQ", security_type="COMMON_STOCK", classification_verified=True,
            sequence=0, source_at=stamp, available_at=stamp,
            quote=dict(bid=99.95, ask=100.05, bid_source_at=stamp, ask_source_at=stamp, available_at=stamp, received_at=stamp),
            daily=dict(bars=daily, splits=[], adjustment="RAW_UNADJUSTED", coverage_verified=True,
                       split_coverage_verified=True, source_at=stamp, available_at=stamp),
            risk=dict(value=risk, producer="synthetic", source_at=stamp, available_at=stamp),
            earnings=dict(coverage_verified=True, window_start=stamp, window_end="2026-10-01T00:00:00Z",
                          events=[], source_at=stamp, available_at=stamp)))
    snapshot = dict(schema="V2_SHADOW_SOURCE_SNAPSHOT_V2", manifest_sha=MANIFEST_SHA, amendment_sha=AMENDMENT_SHA,
        source_id="synthetic", source_at=now.isoformat(), available_at=now.isoformat(), sequence=0,
        provenance=dict(producer="synthetic", version="v1", payload_sha256=digest(rows)),
        universe=dict(coverage_verified=True, instruments=rows))
    write(root / "snapshot.json", snapshot)
    release = Release(EPOCH, "CERTIFIED", DAY, utc("2026-09-06T18:00:00Z"), "a" * 40, "b" * 64)
    store = MemoryShadowStore()
    collector = ShadowCollector(store, causal_source(root, calendar, rows), release, calendar=calendar)
    return collector, store, root, snapshot, now


def event_file(root, event, sequence):
    body = dict(schema="V2_SHADOW_SOURCE_EVENT_V2", manifest_sha=MANIFEST_SHA, amendment_sha=AMENDMENT_SHA, source_id="synthetic-events",
        source_at=event.get("end_at", event["at"]), available_at=event["available_at"], sequence=sequence,
        provenance=dict(producer="synthetic", version="v1", payload_sha256=digest(event)),
        event_id=f"fixture-{sequence}", event=event)
    body["self_sha256"] = digest(body)
    return write(root / "events" / (body["event_id"] + "." + body["self_sha256"] + ".json"), body)


def test_two_arms_first_partial_bar_and_restart_have_single_receipts(rig):
    collector, store, root, _, now = rig
    collector.cycle(now)
    original = store.read(EPOCH)["state"]
    assert len(original["ledger"]["research"]) == 2
    assert len(original["ledger"]["portfolio"]) == 1
    assert {r["arm"] for r in original["ledger"]["research"].values()} == {"ELIGIBLE", "CONTROL"}
    # The full minute has a pre-entry portion. A complete raw trade tape proves
    # that the first post-entry print is the upper touch, without using its low
    # from before entry. This is a hypothetical modeled target, not an order.
    minute = now.replace(second=0)
    end = minute + timedelta(minutes=1)
    event_file(root, dict(type="BAR", at=minute.isoformat(), end_at=end.isoformat(),
        available_at=end.isoformat(), session=DAY.isoformat(), instrument_key="NASDAQ:SYNTHA",
        open=90, high=110, low=90, close=110, regular=True, coverage_complete=True,
        trades=[dict(at=minute.isoformat(), price=90), dict(at=(minute + timedelta(seconds=10)).isoformat(), price=110)]), 0)
    collector.cycle(end)
    saved = store.read(EPOCH)["state"]
    research = next(r for r in saved["ledger"]["research"].values() if r["instrument_key"] == "US:SYNTHA")
    assert research["category"] == "upper_first"
    wallet = next(iter(saved["ledger"]["portfolio"].values()))
    assert wallet["status"] == "CLOSED" and wallet["category"] == "upper_first"
    before_count = len(store.journal(EPOCH))
    restart = ShadowCollector(store, FileShadowSource(root, causal_receipt_verifier=collector.source._causal_receipt_verifier), collector.release, calendar=collector.calendar)
    restart.cycle(end + timedelta(seconds=1))
    after = store.read(EPOCH)["state"]
    assert after["ledger"]["cash"] == saved["ledger"]["cash"]
    assert len(store.journal(EPOCH)) == before_count
    assert len(after["event_receipts"]) == 1


def test_changed_receipt_after_restart_rolls_back_without_cash_rewrite(rig):
    collector, store, root, _, now = rig
    collector.cycle(now)
    at = now + timedelta(seconds=10)
    event = dict(type="QUOTE", at=at.isoformat(), available_at=at.isoformat(), session=DAY.isoformat(),
                 instrument_key="US:SYNTHA", bid=99.95, ask=100.05, bid_at=at.isoformat(), ask_at=at.isoformat(), regular=True)
    original = event_file(root, event, 0)
    collector.cycle(at)
    before = store.read(EPOCH)
    (root / "events" / (original["event_id"] + "." + original["self_sha256"] + ".json")).unlink()
    event_file(root, {**event, "bid": 99.90}, 0)
    restart = ShadowCollector(store, FileShadowSource(root, causal_receipt_verifier=collector.source._causal_receipt_verifier), collector.release, calendar=collector.calendar)
    with pytest.raises(ShadowIntegrityError, match="EVENT_ID_MUTATED"):
        restart.cycle(at + timedelta(seconds=1))
    assert store.read(EPOCH) == before


def test_live_clock_after_io_cannot_capture_in_a_window_that_closed(rig):
    collector, store, _, _, now = rig
    last_in_window = now.replace(second=59, microsecond=900_000)
    after_window = now.replace(minute=1, second=0)
    times = iter([last_in_window, after_window])
    collector.clock = lambda: next(times)
    collector.cycle()
    state = store.read(EPOCH)["state"]
    assert not state["ledger"]["research"]
    assert state["last_cycle_at"] == after_window.isoformat()
    assert store.journal(EPOCH)[-1]["recorded_at"] == after_window.isoformat()


def test_old_price_is_rechecked_at_live_decision_after_io(rig):
    collector, store, _, _, now = rig
    times = iter([now, now + timedelta(seconds=11)])
    collector.clock = lambda: next(times)
    collector.cycle()
    saved = store.read(EPOCH)["state"]
    assert not saved["ledger"]["research"]
    assert all(c["status"] == "DATA_INELIGIBLE" for c in saved["sessions"][DAY.isoformat()]["candidates"].values())


def test_cohort_export_retains_zero_days_and_does_not_hide_missing_session(rig):
    collector, store, _, _, _ = rig
    final = collector.calendar.details(collector.schedule[48])["close"]
    collector.cycle(final)
    state = store.read(EPOCH)["state"]
    result = export_cohort(state, 40, now=final, calendar=collector.calendar)
    assert len(result["sessions"]) == 40 and result["data_gate_unknown"]
    assert all(r["portfolio_episode_count"] == 0 for r in result["sessions"])
    assert result["statistical_verdict"] == "NOT_COMPUTED"
    assert "SYNTHA" not in str(result)
    with pytest.raises(ShadowIntegrityError, match="COHORT_NOT_MATURE"):
        export_cohort(state, 60, now=final, calendar=collector.calendar)
