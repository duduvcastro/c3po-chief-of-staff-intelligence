"""Independent synthetic integration counterexamples; no file feeds/DB/providers."""
from datetime import date, datetime, timedelta, timezone
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
        "candidates": {}, "pending": {}, "diagnostics": [], "attempts": 0,
        "causal_list": {"commitment_sha256": "e"*64}, "programmed_zero_reason": None}
    state["sessions"][DAY] = session
    if position:
        state["ledger"], _, _ = register_candidate(state["ledger"], episode_key="synthetic-entry",
            instrument_key=INSTRUMENT, session=DAY, opened_at=OPEN,
            maturity_at="2026-09-08T19:55:00+00:00", geometry=geometry(), arm="ELIGIBLE")
    if position:
        state["watch_episodes"]["synthetic-entry"] = INSTRUMENT
        state["instrument_episodes"][INSTRUMENT] = ["synthetic-entry"]
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


def causal(symbols=None):
    return {"status": "AVAILABLE", "symbols": symbols or ["SYNTH"], "n_cut": 550,
            "list_sha256": "d"*64, "commitment_sha256": "e"*64}


def test_global_failure_before_any_episode_preserves_research_and_blocks_wallet(monkeypatch):
    fake_evaluations(monkeypatch)
    collector, state, session = setup_state(position=False)
    collector._gap(state, [], utc(OPEN), DAY, "EVENT_SOURCE_UNVERIFIED")
    collector._capture(state, [], session, batch(), utc(OPEN), causal=causal())
    assert len(state["ledger"]["research"]) == 1
    assert not state["ledger"]["portfolio"]
    assert state["ledger"]["cash"] == 1_000_000


def test_first_complete_invalid_candidate_is_not_replaced_by_later_valid_one(monkeypatch):
    fake_evaluations(monkeypatch)
    collector, state, session = setup_state(position=False)
    collector._capture(state, [], session, batch(arm=None), utc(OPEN), causal=causal())
    collector._capture(state, [], session, batch(arm="ELIGIBLE"), utc("2026-09-08T14:00:05+00:00"), causal=causal())
    assert session["candidates"][INSTRUMENT]["arm"] is None
    assert not state["ledger"]["research"]


def test_capture_uses_literal_signed_hash_format_not_json_array(monkeypatch):
    fake_evaluations(monkeypatch)
    collector, state, session = setup_state(position=False)
    collector._capture(state, [], session, batch(), utc(OPEN), causal=causal())
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
    collector._capture(state, [], session, batch(), utc(OPEN), causal=causal())
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


def test_instrument_gap_does_not_contaminate_other_name_or_later_session(monkeypatch):
    fake_evaluations(monkeypatch)
    collector, state, session = setup_state(position=False)
    collector._gap(state, [], utc(OPEN), DAY, "LIVE_EVIDENCE_STALE", instrument="US:OTHER")
    collector._capture(state, [], session, batch(), utc(OPEN), causal=causal())
    assert len(state["ledger"]["portfolio"]) == 1
    assert collector._admission_block(state, "2026-09-09", "US:OTHER") is None
    assert collector._admission_block(state, DAY, "US:OTHER") is not None


def test_verified_new_bar_restores_only_name_and_keeps_old_episode_unobservable():
    collector, state, _ = setup_state()
    journals = []
    collector._gap(state, journals, utc(OPEN)+timedelta(microseconds=1), DAY, "EVENT_SOURCE_UNVERIFIED")
    assert state["ledger"]["research"]["synthetic-entry"]["category"] == "unobservable"
    start = utc(OPEN) + timedelta(seconds=1)
    end = start + timedelta(minutes=1)
    bar = source_event("BAR", at=start.isoformat(), end_at=end.isoformat(), available_at=end.isoformat(),
        open=100, high=100, low=100, close=100, regular=True, coverage_complete=True)
    collector._events(state, journals, [bar], [], end, DAY)
    assert collector._admission_block(state, DAY, INSTRUMENT) is None
    assert collector._admission_block(state, DAY, "US:OTHER") is not None
    assert state["ledger"]["research"]["synthetic-entry"]["category"] == "unobservable"
    assert any(j["type"] == "ADMISSION_OBSERVABILITY_RESTORED" for j in journals)
    # A new outage cannot inherit a previous bar's recovery authorization.
    collector._gap(state, journals, end + timedelta(seconds=1), DAY, "EVENT_SOURCE_UNVERIFIED")
    assert collector._admission_block(state, DAY, INSTRUMENT) is not None


def test_causal_list_fixes_names_even_when_snapshot_contains_extra_name(monkeypatch):
    fake_evaluations(monkeypatch)
    collector, state, session = setup_state(position=False)
    data = batch()
    data["universe"]["instruments"].append({**data["universe"]["instruments"][0], "symbol": "EXTRA"})
    collector._capture(state, [], session, data, utc(OPEN), causal=causal())
    assert set(session["candidates"]) == {INSTRUMENT}
    assert len(state["ledger"]["research"]) == 1
    assert "NOT_IN_CAUSAL_LIST" in session["diagnostics"]


def test_late_list_is_programmed_zero_and_never_loads_snapshot():
    collector, _, _ = setup_state(position=False)
    class Source:
        def causal_list(self, *args):
            return {"status": "MISSING", "diagnostics": [{"code": "CAUSAL_LIST_LATE"}]}
        def snapshot(self, *args):
            pytest.fail("late list must not read snapshot")
        def events(self, *args):
            return []
    collector.source = Source()
    collector.cycle(utc(OPEN))
    state = collector.store.read(EPOCH)["state"]
    session = state["sessions"][DAY]
    assert session["capture_closed"] and session["universe"] == []
    assert session["programmed_zero_reason"] == "CAUSAL_LIST_LATE"
    assert not session["candidates"] and not state["ledger"]["research"]
    assert state["first_session"] == DAY


def test_poll_outside_window_reads_no_snapshot_or_list_and_preserves_noop_state(monkeypatch):
    collector, _, _ = setup_state(position=False)
    class Source:
        def causal_list(self, *args):
            pytest.fail("outside capture window must not read list")
        def snapshot(self, *args):
            pytest.fail("outside capture window must not read snapshot")
        def events(self, *args):
            return []
    collector.source = Source()
    monkeypatch.setattr(shadow, "PortfolioBatch", lambda *_: pytest.fail("no ledger transition must not copy ledger"))
    early = utc("2026-09-08T12:00:00Z")
    collector.cycle(early)
    before = collector.store.read(EPOCH)
    result = collector.cycle(early + timedelta(seconds=1))
    assert collector.store.read(EPOCH) == before
    assert result["observed_at"] != before["state"]["last_cycle_at"]
    assert before["state"]["cycle_count"] == 0


def test_list_verification_is_cached_only_after_commit_and_state_is_compact(monkeypatch):
    fake_evaluations(monkeypatch)
    collector, _, _ = setup_state(position=False)
    class Source:
        calls = 0
        def causal_list(self, *args):
            self.calls += 1
            return {**causal(), "private_raw_registry": "large-raw-source"}
        def snapshot(self, *args):
            return batch()
        def events(self, *args):
            return []
    source = collector.source = Source()
    collector.cycle(utc(OPEN))
    collector.cycle(utc(OPEN)+timedelta(seconds=1))
    assert source.calls == 1
    state = collector.store.read(EPOCH)["state"]
    candidate = state["sessions"][DAY]["candidates"][INSTRUMENT]
    assert set(candidate) == {"status", "arm", "reasons", "evaluation_sha256"}
    assert "private_raw_registry" not in str(state)
    assert "private_raw_registry" not in str(collector._causal_cache)
    assert "private_raw_registry" in str(collector.store.journal(EPOCH))


def test_pending_private_input_moves_to_journal_and_survives_compact_restart(monkeypatch):
    fake_evaluations(monkeypatch)
    collector, state, session = setup_state(position=False)
    data = batch(complete=False, private_fixture="PRIVATE_SYNTHETIC_PAYLOAD")
    journals = []
    collector._capture(state, journals, session, data, utc(OPEN), causal=causal())
    assert "PRIVATE_SYNTHETIC_PAYLOAD" not in str(state)
    assert "PRIVATE_SYNTHETIC_PAYLOAD" in str(journals)
    receipt = session["pending"][INSTRUMENT]["receipt"]
    collector._close_capture(state, journals, session, utc(OPEN)+timedelta(minutes=1))
    assert journals[-2]["pending_receipt"] == receipt
    assert session["candidates"][INSTRUMENT]["status"] == "DATA_INELIGIBLE"


def test_mapper_never_serializes_whole_universe_per_name(monkeypatch):
    collector, _, _ = setup_state(position=False)
    row = {"symbol": "SYNTH", "market": "NASDAQ", "daily": {"bars": [
        {"session_date": d.isoformat(), "open": 100, "high": 101, "low": 99, "close": 100, "volume": 150000}
        for d in collector.calendar.details(date.fromisoformat(DAY))["previous_sessions"]]}}
    rows = [{**row, "symbol": f"S{i:04d}"} for i in range(550)]
    envelope = {"envelope_sha256": "a"*64, "universe": {"instruments": rows}}
    original = shadow.digest
    serialized = 0
    def tracked(value):
        nonlocal serialized
        assert value is not envelope, "quadratic whole-envelope hashing returned"
        serialized += len(shadow.canonical(value))
        return original(value)
    monkeypatch.setattr(shadow, "digest", tracked)
    for item in rows:
        result = shadow.candidate_inputs(item, envelope, utc(OPEN), collector.calendar)
        assert result.source_hashes["universe"] == "a"*64
    assert serialized < 3 * len(shadow.canonical(envelope))


def complete_zero_epoch():
    collector, state, _ = setup_state(position=False)
    state["readiness_sha"] = "1"*64
    state["sessions"] = {day: {"date": day, "capture_closed": True, "universe": [], "diagnostics": []}
                         for day in state["schedule"][:60]}
    return collector, state


def test_40_60_exports_have_49_69_maturity_and_match_adapter_prefix():
    from app.r2d2_v2_inference_input import adapt_collector_export, validate_cohort_prefix
    collector, state = complete_zero_epoch()
    close49 = collector.calendar.details(collector.schedule[48])["close"]
    close69 = collector.calendar.details(collector.schedule[68])["close"]
    first = shadow.export_cohort(state, 40, now=close49, calendar=collector.calendar)
    second = shadow.export_cohort(state, 60, now=close69, calendar=collector.calendar)
    assert first["maturity_session_index"] == 49 and second["maturity_session_index"] == 69
    assert first["sessions_completed"] == 49 and second["sessions_completed"] == 69
    assert len(adapt_collector_export(first).to_session_rows()) == 40
    validate_cohort_prefix(adapt_collector_export(first), adapt_collector_export(second))
    with pytest.raises(shadow.ShadowIntegrityError, match="COHORT_NOT_MATURE"):
        shadow.export_cohort(state, 40, now=close49-timedelta(microseconds=1), calendar=collector.calendar)
    for old_size in (20, 30):
        with pytest.raises(shadow.ShadowIntegrityError, match="COHORT_NOT_AUTHORIZED"):
            shadow.export_cohort(state, old_size, now=close69, calendar=collector.calendar)


@pytest.mark.parametrize("veto_session,blocks40", [(47, True), (49, False)])
def test_veto_first_observed_after_maturity_cannot_contaminate_earlier_reading(veto_session, blocks40):
    collector, state = complete_zero_epoch()
    reason = "V2_CERTIFICATION_FAILED_NAV"
    state["ledger"]["terminal_reasons"] = [reason]
    at = collector.calendar.details(collector.schedule[veto_session])["close"]
    state["terminal_veto_history"] = [{"reason": reason, "session": collector.schedule[veto_session].isoformat(), "observed_at": at.isoformat()}]
    later = collector.calendar.details(collector.schedule[68])["close"]
    assert shadow.export_cohort(state, 40, now=later, calendar=collector.calendar)["terminal_veto"] is blocks40
    assert shadow.export_cohort(state, 60, now=later, calendar=collector.calendar)["terminal_veto"] is True


def test_untimed_veto_is_unknown_blocking_and_unrelated_later_data_issue_is_not_global():
    collector, state = complete_zero_epoch()
    close = collector.calendar.details(collector.schedule[68])["close"]
    state["data_issues"] = [{"session": collector.schedule[50].isoformat(), "instrument": "US:OTHER", "reason": "LIVE_EVIDENCE_STALE"}]
    assert not shadow.export_cohort(state, 40, now=close, calendar=collector.calendar)["data_gate_unknown"]
    state["ledger"]["terminal_reasons"] = ["V2_CERTIFICATION_FAILED_NAV"]
    assert shadow.export_cohort(state, 40, now=close, calendar=collector.calendar)["terminal_veto"]


@pytest.mark.parametrize('with_trade', [False, True])
def test_preentry_bar_coverage_does_not_create_a_gap_before_new_episode(with_trade):
    collector, state, _ = setup_state()
    state['coverage_until'][INSTRUMENT] = '2026-09-08T13:31:00+00:00'
    now = utc(OPEN) + timedelta(seconds=1)
    events = [source_event('TRADE', at=now.isoformat(), price=100, regular=True)] if with_trade else []
    collector._events(state, [], events, [], now, DAY)
    assert not state['data_issues']
    assert state['ledger']['research']['synthetic-entry']['category'] is None


def test_coverage_after_entry_is_preserved_for_watchdog():
    collector, state, _ = setup_state()
    state['coverage_until'][INSTRUMENT] = (utc(OPEN)+timedelta(seconds=80)).isoformat()
    collector._events(state, [], [], [], utc(OPEN)+timedelta(seconds=120), DAY)
    assert not state['data_issues']


def test_explicit_producer_gap_before_any_position_blocks_that_name_only(monkeypatch):
    fake_evaluations(monkeypatch)
    collector, state, session = setup_state(position=False)
    event = source_event('DATA_GAP', at=OPEN, reason='SYNTHETIC_STREAM_GAP')
    collector._events(state, [], [event], [], utc(OPEN), DAY)
    collector._capture(state, [], session, batch(), utc(OPEN), causal=causal())
    assert len(state['ledger']['research']) == 1
    assert not state['ledger']['portfolio']
    assert collector._admission_block(state, DAY, 'US:OTHER') is None
