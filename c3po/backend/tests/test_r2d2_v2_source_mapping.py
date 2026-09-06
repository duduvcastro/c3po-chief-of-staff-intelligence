"""Real private file port -> mapper -> diagnostic collector; synthetic prices only."""
from copy import deepcopy
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import json

import pytest

from app.r2d2_v2_calendar import NEW_YORK, ShadowCalendar
from app.r2d2_v2_contract import RISK_C75, evaluate_candidate, input_complete
from app.r2d2_v2_shadow import Release, ShadowCollector, candidate_inputs
from app.r2d2_v2_sources import FileShadowSource, MANIFEST_SHA, SNAPSHOT_SCHEMA, canonical
from app.r2d2_v2_store import MemoryShadowStore

DAY = date(2026, 9, 8)
INSTRUMENT = "US:SYNTHETIC"


@pytest.fixture(scope="module")
def calendar():
    return ShadowCalendar()


@pytest.fixture
def spool(tmp_path):
    root = tmp_path.resolve() / "producer-private"
    root.mkdir(mode=0o700)
    (root / "events").mkdir(mode=0o700)
    return root


def raw_instrument(calendar, now):
    detail = calendar.details(now.astimezone(NEW_YORK).date())
    stamp = now.isoformat()
    bars = []
    for day in detail["previous_sessions"]:
        close = calendar.details(day)["close"].isoformat()
        bars.append({"session_date": day.isoformat(), "open": 100., "high": 101., "low": 99., "close": 100.,
                     "volume": 150_000., "complete": True, "regular_session": True, "source_at": close, "available_at": close})
    return {"symbol": "SYNTHETIC", "market": "NASDAQ", "security_type": "COMMON_STOCK", "classification_verified": True,
        "sequence": 0, "source_at": stamp, "available_at": stamp,
        "quote": {"bid": 99.95, "ask": 100.05, "bid_source_at": stamp, "ask_source_at": stamp, "available_at": stamp},
        "daily": {"bars": bars, "splits": [], "adjustment": "RAW_UNADJUSTED", "coverage_verified": True,
                  "split_coverage_verified": True, "source_at": stamp, "available_at": stamp},
        "risk": {"value": RISK_C75, "producer": "synthetic-risk", "source_at": stamp, "available_at": stamp},
        "earnings": {"coverage_verified": True, "window_start": stamp,
                     "window_end": (detail["horizon_close"] - timedelta(minutes=5)).isoformat(),
                     "events": [], "source_at": stamp, "available_at": stamp}}


def publish(spool, row, now, sequence=0):
    envelope = {"schema": SNAPSHOT_SCHEMA, "manifest_sha": MANIFEST_SHA, "source_id": "synthetic-audited-producer",
                "source_at": now.isoformat(), "available_at": now.isoformat(), "sequence": sequence,
                "provenance": {"producer": "synthetic", "version": "fixture-v1", "payload_sha256": hashlib.sha256(canonical(row)).hexdigest()},
                "universe": {"coverage_verified": True, "instruments": [row]}}
    envelope["self_sha256"] = hashlib.sha256(canonical(envelope)).hexdigest()
    staging = spool / ".snapshot-staging"
    staging.write_bytes(canonical(envelope))
    staging.chmod(0o600)
    staging.replace(spool / "snapshot.json")
    return envelope


def mapped(spool, calendar, now, raw=None):
    raw = raw_instrument(calendar, now) if raw is None else raw
    envelope = publish(spool, raw, now)
    batch = FileShadowSource(spool).snapshot(now)
    assert batch["status"] == "AVAILABLE"
    row = batch["universe"]["instruments"][0]
    inputs = candidate_inputs(row, batch, now, calendar)
    return raw, envelope, row, inputs, evaluate_candidate(inputs)


def diagnostic_collector(spool, calendar, monkeypatch):
    from app import r2d2_v2_shadow as module
    def forbidden(*_args, **_kwargs):
        raise AssertionError("DIAGNOSTIC must not access the research/portfolio/event ledger")
    for name in ("new_portfolio", "register_candidate", "apply_events", "export_session_statistics"):
        monkeypatch.setattr(module, name, forbidden)
    source = FileShadowSource(spool)
    monkeypatch.setattr(source, "events", forbidden)
    release = Release(epoch="R2D2-V2-SHADOW-source-mapping-fixture", mode="DIAGNOSTIC", first_session=DAY,
                      approved_at=datetime(2026, 9, 6, 12, tzinfo=timezone.utc),
                      code_revision="f" * 40, receipt_sha="a" * 64)
    store = MemoryShadowStore()
    return ShadowCollector(store, source, release, calendar=calendar), store, release


def test_real_calendar_and_fully_valid_producer_snapshot_are_eligible(spool, calendar):
    now = calendar.details(DAY)["capture_open"]
    raw, envelope, row, inputs, result = mapped(spool, calendar, now)
    assert not calendar.is_session(date(2026, 9, 7))  # Labor Day, not a weekday approximation.
    assert inputs.previous_sessions[-1] == date(2026, 9, 4)
    assert len(inputs.previous_sessions) == 61
    assert tuple(bar.session_date for bar in inputs.daily_bars) == inputs.previous_sessions
    assert inputs.horizon_sessions == tuple(calendar.sessions(DAY, 10))
    assert row["data_available"] is True and input_complete(inputs)
    assert result.status == "ELIGIBLE" and result.reasons == ()
    assert result.risk_score == RISK_C75 and result.atr14 == 2.0 and result.adv20 == 15_000_000
    assert result.maturity_at == calendar.details(DAY)["horizon_close"] - timedelta(minutes=5)
    assert inputs.sources["calendar"] == "exchange_calendars.XNYS"
    assert inputs.source_versions["calendar"] == calendar.version
    assert inputs.source_hashes["calendar"] == calendar.details(DAY)["sha256"]
    assert inputs.source_hashes["risk"] == hashlib.sha256(canonical(raw["risk"])).hexdigest()
    assert row["risk"] == raw["risk"] and envelope["self_sha256"]


def test_resolved_null_score_is_complete_data_failure_not_pending(spool, calendar):
    now = calendar.details(DAY)["capture_open"]
    raw = raw_instrument(calendar, now)
    raw["risk"]["value"] = None
    _, _, row, inputs, result = mapped(spool, calendar, now, raw)
    assert row["data_available"] is False
    assert row["risk"]["available_at"] == now.isoformat()
    assert inputs.risk_score is None and input_complete(inputs)
    assert result.complete and result.status == "DATA_INELIGIBLE"
    assert "RISK_SCORE_INVALID" in result.reasons and "SNAPSHOT_INCOMPLETE" not in result.reasons


def test_missing_quote_remains_pending_without_synthetic_price(spool, calendar):
    now = calendar.details(DAY)["capture_open"]
    raw = raw_instrument(calendar, now)
    raw["quote"]["bid"] = None
    _, _, row, inputs, result = mapped(spool, calendar, now, raw)
    assert row["data_available"] is False and row["quote"]["bid"] is None
    assert inputs.bid is None and inputs.ask == 100.05 and not input_complete(inputs)
    assert result.status == "DATA_INELIGIBLE" and not result.complete
    assert "SNAPSHOT_INCOMPLETE" in result.reasons


@pytest.mark.parametrize("delta,expected", [(-1, "ELIGIBLE"), (0, "DATA_INELIGIBLE")])
def test_capture_end_is_exclusive_even_with_fresh_data(spool, calendar, delta, expected):
    now = calendar.details(DAY)["capture_close"] + timedelta(microseconds=delta)
    _, _, _, inputs, result = mapped(spool, calendar, now)
    assert input_complete(inputs)
    assert result.status == expected
    assert ("OUTSIDE_CAPTURE_WINDOW" in result.reasons) == (delta == 0)


@pytest.mark.parametrize("delta,expected", [(-1, "DATA_INELIGIBLE"), (0, "ELIGIBLE"), (1, "ELIGIBLE")])
def test_earnings_coverage_must_reach_exact_maturity_instant(spool, calendar, delta, expected):
    now = calendar.details(DAY)["capture_open"]
    raw = raw_instrument(calendar, now)
    maturity = calendar.details(DAY)["horizon_close"] - timedelta(minutes=5)
    raw["earnings"]["window_end"] = (maturity + timedelta(microseconds=delta)).isoformat()
    _, _, _, inputs, result = mapped(spool, calendar, now, raw)
    assert input_complete(inputs)
    assert result.status == expected
    assert inputs.earnings_coverage_verified is (delta >= 0)
    assert ("EARNINGS_COVERAGE_UNVERIFIED" in result.reasons) == (delta < 0)


def test_earnings_window_start_cannot_be_widened_to_midnight(spool, calendar):
    now = calendar.details(DAY)["capture_open"]
    raw = raw_instrument(calendar, now)
    raw["earnings"]["window_start"] = (now + timedelta(microseconds=1)).isoformat()
    _, _, _, inputs, result = mapped(spool, calendar, now, raw)
    assert input_complete(inputs) and not inputs.earnings_coverage_verified
    assert result.status == "DATA_INELIGIBLE" and "EARNINGS_COVERAGE_UNVERIFIED" in result.reasons


@pytest.mark.parametrize("offset,expected", [(0, "INELIGIBLE"), (1, "ELIGIBLE")])
def test_known_earnings_at_maturity_included_but_one_microsecond_after_excluded(spool, calendar, offset, expected):
    now = calendar.details(DAY)["capture_open"]
    raw = raw_instrument(calendar, now)
    maturity = calendar.details(DAY)["horizon_close"] - timedelta(minutes=5)
    raw["earnings"]["window_end"] = (maturity + timedelta(seconds=1)).isoformat()
    raw["earnings"]["events"] = [{"event_at": (maturity + timedelta(microseconds=offset)).isoformat(), "available_at": now.isoformat()}]
    _, _, row, inputs, result = mapped(spool, calendar, now, raw)
    assert row["data_available"] is True and input_complete(inputs)
    assert result.status == expected
    assert ("EARNINGS_WITHIN_HORIZON" in result.reasons) == (offset == 0)


def test_raw_bar_values_are_preserved_exactly_in_mapper(spool, calendar):
    now = calendar.details(DAY)["capture_open"]
    raw = raw_instrument(calendar, now)
    raw["daily"]["bars"][-1].update(open=99.1, high=105.9, low=97.2, close=102.3, volume=123456.0)
    _, _, _, inputs, _ = mapped(spool, calendar, now, raw)
    for original, bar in zip(raw["daily"]["bars"], inputs.daily_bars, strict=True):
        values = asdict(bar)
        for name in ("open", "high", "low", "close", "volume", "complete", "regular_session"):
            assert values[name] == original[name]
        assert values["session_date"] == date.fromisoformat(original["session_date"])
        assert values["source_at"] == datetime.fromisoformat(original["source_at"])
        assert values["available_at"] == datetime.fromisoformat(original["available_at"])
    assert inputs.daily_price_basis == "RAW_UNADJUSTED"


@pytest.mark.parametrize("change,reason", [
    (lambda row: row["daily"]["bars"].pop(), "DAILY_BARS_COUNT_OR_TYPE"),
    (lambda row: row["daily"]["bars"][0].pop("source_at"), "DAILY_EVIDENCE_NOT_CAUSAL"),
    (lambda row: row["daily"]["bars"][0].update(complete=False), "DAILY_NOT_COMPLETE_REGULAR"),
    (lambda row: row["daily"].update(adjustment="ADJUSTED"), "DAILY_PRICE_BASIS_UNVERIFIED"),
    (lambda row: row["daily"].update(split_coverage_verified=False), "SPLIT_COVERAGE_UNVERIFIED"),
])
def test_mapper_never_fills_missing_daily_evidence(spool, calendar, change, reason):
    now = calendar.details(DAY)["capture_open"]
    raw = raw_instrument(calendar, now)
    change(raw)
    _, _, row, inputs, result = mapped(spool, calendar, now, raw)
    assert row["data_available"] is False and input_complete(inputs)
    assert len(inputs.daily_bars) == len(raw["daily"]["bars"])
    assert result.status == "DATA_INELIGIBLE" and reason in result.reasons


def test_split_source_clock_is_not_synthesized_by_mapper(spool, calendar):
    now = calendar.details(DAY)["capture_open"]
    raw = raw_instrument(calendar, now)
    raw["daily"]["splits"] = [{"factor": 2, "effective_at": now.isoformat(), "available_at": now.isoformat()}]
    _, _, _, inputs, result = mapped(spool, calendar, now, raw)
    assert len(inputs.splits) == 1 and inputs.splits[0].source_at is None
    assert input_complete(inputs) and result.status == "DATA_INELIGIBLE"
    assert "SPLIT_RECORD_INVALID" in result.reasons


def test_diagnostic_freezes_first_complete_null_score_and_never_creates_ledger(spool, calendar, monkeypatch):
    collector, store, release = diagnostic_collector(spool, calendar, monkeypatch)
    now = calendar.details(DAY)["capture_open"]
    raw = raw_instrument(calendar, now)
    raw["risk"]["value"] = None
    first_envelope = publish(spool, raw, now)
    first = collector.cycle(now)
    saved = store.read(release.epoch)["state"]
    frozen = deepcopy(saved["sessions"][DAY.isoformat()]["candidates"][INSTRUMENT])
    assert saved["ledger"] is None and not saved["event_receipts"]
    assert frozen["status"] == "DATA_INELIGIBLE" and frozen["input_complete"] is True
    later = now + timedelta(seconds=1)
    publish(spool, raw_instrument(calendar, later), later, sequence=1)
    collector.cycle(later)
    saved = store.read(release.epoch)["state"]
    assert saved["sessions"][DAY.isoformat()]["candidates"][INSTRUMENT] == frozen
    candidates = [r["payload"] for r in store.journal(release.epoch) if r["payload"]["type"] == "CANDIDATE"]
    assert len(candidates) == 1
    assert candidates[0]["observation"]["source"]["risk"]["value"] is None
    assert "research" not in candidates[0] and "admission" not in candidates[0]
    assert first["mode"] == "DIAGNOSTIC" and first["cohort_clock_started"] is False
    assert first["production_orders"] is False and first["certification_computed"] is False
    assert "SYNTHETIC" not in json.dumps(first)
    assert first_envelope["self_sha256"]


def test_diagnostic_can_complete_missing_quote_inside_window_once(spool, calendar, monkeypatch):
    collector, store, release = diagnostic_collector(spool, calendar, monkeypatch)
    now = calendar.details(DAY)["capture_open"]
    raw = raw_instrument(calendar, now)
    raw["quote"]["bid"] = None
    publish(spool, raw, now)
    collector.cycle(now)
    session = store.read(release.epoch)["state"]["sessions"][DAY.isoformat()]
    assert session["candidates"] == {} and INSTRUMENT in session["pending"]
    later = now + timedelta(seconds=1)
    publish(spool, raw_instrument(calendar, later), later, sequence=1)
    collector.cycle(later)
    state = store.read(release.epoch)["state"]
    session = state["sessions"][DAY.isoformat()]
    assert session["pending"] == {} and len(session["candidates"]) == 1
    assert session["candidates"][INSTRUMENT]["status"] == "ELIGIBLE"
    assert session["candidates"][INSTRUMENT]["decision_at"] == later.isoformat()
    assert state["ledger"] is None


def test_window_close_freezes_missing_quote_and_never_uses_arriving_price(spool, calendar, monkeypatch):
    collector, store, release = diagnostic_collector(spool, calendar, monkeypatch)
    detail = calendar.details(DAY)
    raw = raw_instrument(calendar, detail["capture_open"])
    raw["quote"]["bid"] = None
    publish(spool, raw, detail["capture_open"])
    collector.cycle(detail["capture_open"])
    publish(spool, raw_instrument(calendar, detail["capture_close"]), detail["capture_close"], sequence=1)
    collector.cycle(detail["capture_close"])
    state = store.read(release.epoch)["state"]
    session = state["sessions"][DAY.isoformat()]
    assert session["capture_closed"] is True and session["pending"] == {}
    frozen = session["candidates"][INSTRUMENT]
    assert frozen["status"] == "DATA_INELIGIBLE" and frozen["input_complete"] is False
    assert "CAPTURE_WINDOW_INCOMPLETE" in frozen["reasons"]
    candidates = [r["payload"] for r in store.journal(release.epoch) if r["payload"]["type"].startswith("CANDIDATE")]
    assert len(candidates) == 1 and candidates[0]["type"] == "CANDIDATE_INCOMPLETE"
    assert candidates[0]["observation"]["source"]["quote"]["bid"] is None
    collector.cycle(detail["capture_close"] + timedelta(seconds=1))
    assert store.read(release.epoch)["state"]["sessions"][DAY.isoformat()]["candidates"][INSTRUMENT] == frozen
    assert state["ledger"] is None


def test_calendar_counts_are_exact_with_real_installed_exchange_calendar(calendar):
    detail = calendar.details(DAY)
    assert len(detail["previous_sessions"]) == 61
    assert len(detail["horizon_sessions"]) == 10
    assert len(calendar.sessions(DAY, 39)) == 39
    assert len(calendar.sessions(DAY, 1)) == 1
    assert detail["horizon_sessions"][0] == DAY
    assert detail["previous_sessions"][-1] < DAY
    assert all(calendar.is_session(day) for day in detail["previous_sessions"] + detail["horizon_sessions"])


def test_daily_coverage_false_is_not_promoted_by_other_valid_fields(spool, calendar):
    now = calendar.details(DAY)["capture_open"]
    raw = raw_instrument(calendar, now)
    raw["daily"]["coverage_verified"] = False
    _, _, row, inputs, result = mapped(spool, calendar, now, raw)
    assert row["data_available"] is False and input_complete(inputs)
    assert result.status == "DATA_INELIGIBLE"


def test_future_availability_of_earnings_item_cannot_be_hidden_by_calendar_receipt(spool, calendar):
    now = calendar.details(DAY)["capture_open"]
    raw = raw_instrument(calendar, now)
    maturity = calendar.details(DAY)["horizon_close"] - timedelta(minutes=5)
    raw["earnings"]["window_end"] = (maturity + timedelta(seconds=2)).isoformat()
    raw["earnings"]["events"] = [{"event_at": (maturity + timedelta(seconds=1)).isoformat(),
                                    "available_at": (now + timedelta(seconds=1)).isoformat()}]
    _, _, row, inputs, result = mapped(spool, calendar, now, raw)
    assert row["data_available"] is False and input_complete(inputs)
    assert result.status == "DATA_INELIGIBLE"


def test_real_thanksgiving_early_close_is_used_for_maturity(spool, calendar):
    entry = date(2026, 11, 13)
    detail = calendar.details(entry)
    now = detail["capture_open"]
    _, _, row, inputs, result = mapped(spool, calendar, now)
    assert not calendar.is_session(date(2026, 11, 26))
    assert inputs.horizon_sessions[-1] == date(2026, 11, 27)
    assert detail["horizon_close"].astimezone(NEW_YORK).hour == 13
    assert row["data_available"] is True and result.status == "ELIGIBLE"
    assert result.maturity_at.astimezone(NEW_YORK).isoformat() == "2026-11-27T12:55:00-05:00"
