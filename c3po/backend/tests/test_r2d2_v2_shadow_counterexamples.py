"""Independent synthetic integration counterexamples; no file feeds/DB/providers."""
from datetime import date, datetime, timezone
from hashlib import sha256
from types import SimpleNamespace

import pytest

from app import r2d2_v2_shadow as shadow
from app.r2d2_v2_calendar import ShadowCalendar
from app.r2d2_v2_portfolio import register_candidate
from app.r2d2_v2_store import MemoryShadowStore, utc

DAY = "2026-09-08"
OPEN = "2026-09-08T14:00:00+00:00"
EPOCH = "R2D2-V2-SHADOW-SYNTHETIC"
INSTRUMENT = "US:SYNTH"


def geometry():
    p, s = 100.0, 97.0
    b, c = p * 1.001, p * 1.001 * 1.0004
    sell = .999 * .9996
    r = c - s * sell
    return dict(P=p, B=b, C=c, S=s, T=(c+r)/sell, R_unit=r)


def setup_state(*, position=True):
    release = shadow.Release(EPOCH, "CERTIFIED", date(2026, 9, 8),
        datetime(2026, 9, 7, tzinfo=timezone.utc), "a"*40, "b"*64)
    collector = shadow.ShadowCollector(MemoryShadowStore(), None, release, calendar=ShadowCalendar())
    state = collector._initial()
    state["clock_receipts"] = ["SESSION_OPEN:" + DAY]
    session = {"date": DAY, "entry_session": True, "calendar_sha": "c"*64,
        "capture_closed": True, "universe": [INSTRUMENT], "universe_sha": "d"*64,
        "candidates": {}, "pending": {}, "diagnostics": [], "attempts": 0}
    state["sessions"][DAY] = session
    if position:
        state["ledger"], _, _ = register_candidate(state["ledger"], episode_key="synthetic-entry",
            instrument_key=INSTRUMENT, session=DAY, opened_at=OPEN,
            maturity_at="2026-09-08T19:55:00+00:00", geometry=geometry(), arm="ELIGIBLE")
    return collector, state, session


def source_event(kind, *, at, sequence=0, **fields):
    result = {"event_id": f"synthetic-{sequence}", "envelope_sha256": str(sequence % 10)*64,
        "type": kind, "at": at, "available_at": at, "session": DAY,
        "instrument_key": INSTRUMENT, "source_id": "synthetic-source", "sequence": sequence}
    return {**result, **fields}


def test_gap_before_new_terminal_event_cannot_disappear_when_episode_closes():
    collector, state, _ = setup_state()
    now = utc("2026-09-08T14:05:00+00:00")
    item = source_event("TRADE", at=now.isoformat(), price=110, regular=True)
    collector._events(state, [], [item], [], now, DAY)
    # More than90s without evidence preceded this isolated trade; closure must
    # not remove the record from the coverage check or certify a first touch.
    assert state["data_issues"], "The pre-terminal evidence gap disappeared"


def test_quote_known_exactly_at_close_is_processed_before_close_clock():
    collector, state, _ = setup_state()
    state["last_price_at"][INSTRUMENT] = "2026-09-08T19:59:55+00:00"
    now = utc("2026-09-08T20:00:00+00:00")
    item = source_event("QUOTE", at=now.isoformat(), bid=99.9, ask=100.1,
        bid_at=now.isoformat(), ask_at=now.isoformat(), regular=True)
    result, _, _ = collector._cycle(state, {"status": "MISSING"}, [item], [], now)
    record = result["ledger"]["portfolio"]["synthetic-entry"]
    assert record["status"] == "CLOSED"
    assert record["exit_at"] == now.isoformat()
    assert not record["horizon_breach"]


def test_intention_precedes_simultaneous_mark_in_collector_and_ledger():
    collector, state, _ = setup_state()
    now = utc("2026-09-08T14:01:00+00:00")
    events = [source_event("MARK", at=now.isoformat(), price=100, regular=True),
              source_event("EARNINGS", at=now.isoformat(), sequence=1,
                           earnings_at="2026-09-08T18:00:00+00:00")]
    collector._events(state, [], events, [], now, DAY)
    assert state["ledger"]["research"]["synthetic-entry"]["intent"]["cause"] == "EVENT"


def fake_evaluations(monkeypatch):
    def mapped(row, batch, now, calendar):
        return SimpleNamespace(row=row, available_at={"quote": utc(row["available_at"])})
    def evaluated(inputs):
        row = inputs.row
        return SimpleNamespace(to_dict=lambda: {"arm": row.get("arm", "ELIGIBLE"),
            "status": "ELIGIBLE" if row.get("arm", "ELIGIBLE") else "DATA_INELIGIBLE",
            "geometry": geometry(), "maturity_at": "2026-09-21T19:55:00+00:00", "reasons": []})
    monkeypatch.setattr(shadow, "candidate_inputs", mapped)
    monkeypatch.setattr(shadow, "evaluate_candidate", evaluated)
    monkeypatch.setattr(shadow, "input_complete", lambda x: x.row.get("complete", True))


def batch(arm="ELIGIBLE", **changes):
    row = {"market": "NASDAQ", "symbol": "SYNTH", "available_at": OPEN, "arm": arm, **changes}
    return {"status": "AVAILABLE", "universe": {"coverage_verified": True, "instruments": [row]}}


def test_global_failure_before_any_episode_preserves_research_and_blocks_wallet(monkeypatch):
    fake_evaluations(monkeypatch)
    collector, state, session = setup_state(position=False)
    collector._gap(state, [], utc(OPEN), DAY, "EVENT_SOURCE_UNVERIFIED")
    collector._capture(state, [], session, batch(), utc(OPEN))
    assert len(state["ledger"]["research"]) == 1
    assert not state["ledger"]["portfolio"]
    assert state["ledger"]["cash"] == 1_000_000


def test_first_complete_invalid_candidate_is_not_replaced_by_later_valid_one(monkeypatch):
    fake_evaluations(monkeypatch)
    collector, state, session = setup_state(position=False)
    collector._capture(state, [], session, batch(arm=None), utc(OPEN))
    collector._capture(state, [], session, batch(arm="ELIGIBLE"), utc("2026-09-08T14:00:05+00:00"))
    assert session["candidates"][INSTRUMENT]["arm"] is None
    assert not state["ledger"]["research"]


def test_capture_uses_literal_signed_hash_format_not_json_array(monkeypatch):
    fake_evaluations(monkeypatch)
    collector, state, session = setup_state(position=False)
    collector._capture(state, [], session, batch(), utc(OPEN))
    signed = sha256(f"{EPOCH}|{DAY}|SYNTH".encode()).hexdigest()
    assert signed in state["ledger"]["research"]


def test_public_status_exposes_global_data_failure_even_without_episodes():
    collector, state, _ = setup_state(position=False)
    collector._gap(state, [], utc(OPEN), DAY, "EVENT_SOURCE_UNVERIFIED")
    public = shadow.public_summary(state)
    assert public.get("data_gate_unknown") is True
    assert "SYNTH" not in str(public.get("data_issue_counts", {}))


def test_fresh_quotes_alone_do_not_establish_continuous_trade_barrier_coverage():
    collector, state, _ = setup_state()
    for n, stamp in enumerate(["2026-09-08T14:00:30+00:00", "2026-09-08T14:01:00+00:00",
                               "2026-09-08T14:01:31+00:00"]):
        item = source_event("QUOTE", at=stamp, sequence=n, bid=99.9, ask=100.1,
                            bid_at=stamp, ask_at=stamp, regular=True)
        collector._events(state, [], [item], [], utc(stamp), DAY)
    assert state["data_issues"], "Quote freshness was used as evidence of trade/barrier coverage"


def test_repeated_global_gap_reaches_research_created_after_first_failure(monkeypatch):
    fake_evaluations(monkeypatch)
    collector, state, session = setup_state(position=False)
    collector._gap(state, [], utc(OPEN), DAY, "EVENT_SOURCE_UNVERIFIED")
    collector._capture(state, [], session, batch(), utc(OPEN))
    collector._events(state, [], [], [{"code": "SYNTHETIC_SOURCE_MISSING"}],
                      utc("2026-09-08T14:00:05+00:00"), DAY)
    assert len(state["ledger"]["research"]) == 1
    assert all(r["category"] == "unobservable" for r in state["ledger"]["research"].values())


def test_sequence_gap_at_price_timestamp_is_persisted_without_priority_abort():
    collector, state, _ = setup_state()
    now = utc("2026-09-08T14:01:00+00:00")
    missing_first = source_event("TRADE", at=now.isoformat(), sequence=1, price=110, regular=True)
    collector._events(state, [], [missing_first], [], now, DAY)
    assert state["data_issues"]
    assert state["ledger"]["research"]["synthetic-entry"]["category"] == "unobservable"
