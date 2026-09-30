"""E-BAR cycle order: every gap dated before entry_at precedes the scheduled entry."""
from copy import deepcopy
from datetime import timedelta

from app.r2d2_v2_portfolio import apply_events, register_candidate
from app.r2d2_v2_store import utc
from test_r2d2_v2_ebar_entry import frontier, pending, quote
from test_r2d2_v2_shadow_counterexamples import DAY, INSTRUMENT, geometry, source_event

PREVIOUS = "2026-09-04"


def _old_episode(state, *, session=DAY, opened_at="2026-09-08T13:45:00+00:00", coverage="2026-09-08T13:58:00+00:00"):
    state["ledger"], _, _ = register_candidate(state["ledger"], episode_key="old", instrument_key="US:OLD",
        session=session, opened_at=opened_at, maturity_at="2026-09-21T19:55:00+00:00",
        geometry=geometry(), arm="ELIGIBLE")
    state["watch_episodes"]["old"] = "US:OLD"
    state["instrument_episodes"]["US:OLD"] = ["old"]
    state["coverage_until"]["US:OLD"] = coverage


def _observe_quote_before_entry(collector, state, session, entry, journals):
    at = utc(entry["entry_at"])
    before = (at - timedelta(seconds=3)).isoformat()
    collector._entries(state, journals, session, {}, [quote(before)], utc(before))
    return at


def _late_print(at):
    # Dated before entry_at, received after it: proves the source frontier and
    # is applied before the entry (never after it).
    return frontier((at + timedelta(seconds=1)).isoformat(), at=(at - timedelta(milliseconds=1)).isoformat())


def _new_record(state):
    return next(r for r in state["ledger"]["research"].values() if r["instrument_key"] == INSTRUMENT)


def test_stale_older_episode_in_entry_cycle(monkeypatch):
    # Reviewer repro: the old name's stale gap is dated 13:58 < entry_at and is
    # known at the same collector receipt as the entry. It must precede it.
    collector, state, session, entry, journals = pending(monkeypatch)
    _old_episode(state)
    at = _observe_quote_before_entry(collector, state, session, entry, journals)
    state, journals, _ = collector._cycle(state, {}, [_late_print(at)], [], at + timedelta(seconds=5))
    old = state["ledger"]["research"]["old"]
    assert "DATA_GAP" in old["flags"] and old["category"] == "unobservable"
    issue = next(i for i in state["data_issues"] if i["instrument"] == "US:OLD")
    assert issue["reason"] == "LIVE_EVIDENCE_STALE" and utc(issue["at"]) < at
    record = _new_record(state)
    assert record["status"] == "OPEN" and record["opened_at"] == entry["entry_at"]
    assert session["candidates"][INSTRUMENT]["entry_status"] == "OPENED"
    kinds = [j["type"] for j in journals]
    assert kinds.index("DATA_GAP") < kinds.index("CANDIDATE_ENTRY") == len(kinds) - 1
    # Admission is decided after the gap; a rejection must carry its reason.
    admission = next(j for j in journals if j["type"] == "CANDIDATE_ENTRY")["admission"]
    assert admission["admitted"] or admission["reason"]
    # The next cycle is a normal cycle and does not wedge either.
    state, _, _ = collector._cycle(state, {}, [], [], at + timedelta(seconds=10))
    assert len(state["ledger"]["research"]) == 2


def test_restart_across_entry_minute_with_previous_day_position(monkeypatch):
    # Collector down from 14:00:57 to 14:20 while a D-1 episode is open.
    collector, state, session, entry, journals = pending(monkeypatch)
    ledger = collector._initial()["ledger"]
    ledger, _, _ = register_candidate(ledger, episode_key="old", instrument_key="US:OLD",
        session=PREVIOUS, opened_at="2026-09-04T14:01:00+00:00",
        maturity_at="2026-09-21T19:55:00+00:00", geometry=geometry(), arm="ELIGIBLE")
    ledger, _ = apply_events(ledger, [
        {"event_id": "clock:SESSION_CLOSE:" + PREVIOUS, "type": "SESSION_CLOSE", "session": PREVIOUS,
         "at": "2026-09-04T20:00:00+00:00", "available_at": "2026-09-04T20:00:01+00:00"},
        {"event_id": "clock:SESSION_OPEN:" + DAY, "type": "SESSION_OPEN", "session": DAY,
         "at": "2026-09-08T13:30:00+00:00", "available_at": "2026-09-08T13:30:01+00:00"}])
    state["ledger"] = ledger
    state["watch_episodes"]["old"] = "US:OLD"
    state["instrument_episodes"]["US:OLD"] = ["old"]
    state["coverage_until"]["US:OLD"] = "2026-09-04T20:00:00+00:00"
    at = _observe_quote_before_entry(collector, state, session, entry, journals)
    restart = utc("2026-09-08T14:20:00+00:00")
    before = source_event("TRADE", at="2026-09-08T14:00:30+00:00", sequence=0, price=100.,
                          regular=True, instrument_key="US:OLD")
    after_old = source_event("TRADE", at="2026-09-08T14:10:00+00:00", sequence=1, price=100.,
                             regular=True, instrument_key="US:OLD")
    after_new = source_event("TRADE", at="2026-09-08T14:05:00+00:00", sequence=2, price=101.05,
                             regular=True)
    proof = _late_print(at)
    events = [before, after_old, after_new, proof]
    state, journals, _ = collector._cycle(state, {}, deepcopy(events), [], restart)
    old = state["ledger"]["research"]["old"]
    assert "DATA_GAP" in old["flags"]
    assert all(utc(i["at"]) < at for i in state["data_issues"] if i["instrument"] == "US:OLD")
    record = _new_record(state)
    assert record["opened_at"] == entry["entry_at"] and record["status"] == "OPEN"
    assert journals[-1]["type"] == "CANDIDATE_ENTRY"
    # Only the pre-entry event is applied in the entry cycle; later evidence is
    # left unacknowledged for the next receipt instead of preceding the entry.
    assert set(state["event_receipts"]) == {before["event_id"], proof["event_id"]}
    state, journals, _ = collector._cycle(state, {}, deepcopy(events), [], restart + timedelta(seconds=5))
    assert set(state["event_receipts"]) == {e["event_id"] for e in events}
    applied = [j for j in journals if j["type"] == "SOURCE_EVENT"]
    assert [j["source"]["event_id"] for j in applied] == [after_new["event_id"], after_old["event_id"]]
    assert applied[0]["result"][0]["affected_records"] == 1
    # Repeating the cycle is idempotent and never raises the pre-entry guard.
    state, _, _ = collector._cycle(state, {}, deepcopy(events), [], restart + timedelta(seconds=10))
    assert len(state["ledger"]["research"]) == 2


def test_post_entry_bar_revealing_old_coverage_hole_cannot_wedge(monkeypatch):
    # A bar at/after entry_at can reveal a hole dated before entry_at. It is
    # applied only in a later receipt, never immediately after the entry.
    collector, state, session, entry, journals = pending(monkeypatch)
    _old_episode(state, coverage="2026-09-08T14:00:00+00:00")
    at = _observe_quote_before_entry(collector, state, session, entry, journals)
    end = (at + timedelta(minutes=1)).isoformat()
    bar = source_event("BAR", at=(at + timedelta(seconds=30)).isoformat(), available_at=end, sequence=0,
        end_at=end, open=100., high=100., low=100., close=100., regular=True, coverage_complete=True,
        instrument_key="US:OLD")
    now = utc(end) + timedelta(seconds=1)
    proof = frontier((at + timedelta(seconds=1)).isoformat())
    state, journals, _ = collector._cycle(state, {}, [deepcopy(bar), proof], [], now)
    assert journals[-1]["type"] == "CANDIDATE_ENTRY" and not state["event_receipts"]
    state, journals, _ = collector._cycle(state, {}, [deepcopy(bar), proof], [], now + timedelta(seconds=1))
    assert bar["event_id"] in state["event_receipts"]
    assert "DATA_GAP" in state["ledger"]["research"]["old"]["flags"]
    assert "DATA_GAP" not in _new_record(state)["flags"]


def test_same_cycle_source_gap_attaches_to_new_episode(monkeypatch):
    collector, state, session, entry, journals = pending(monkeypatch)
    at = _observe_quote_before_entry(collector, state, session, entry, journals)
    gaps = [{"instrument": None, "reason": "RAW_POLL_PERSISTENT_FAILURE"}]
    state, journals, _ = collector._cycle(state, {}, [_late_print(at)], [], at + timedelta(seconds=2), source_gaps=gaps)
    record = _new_record(state)
    assert "DATA_GAP" in record["flags"]
    admission = next(j for j in journals if j["type"] == "CANDIDATE_ENTRY")["admission"]
    assert admission == {"admitted": False, "reason": "COLLECTION_DATA_GATE_BLOCKED", "quantity": 0.0}
    kinds = [j["type"] for j in journals]
    assert kinds[-2:] == ["CANDIDATE_ENTRY", "DATA_GAP"]


def test_two_due_entries_in_one_receipt_each_follow_their_pre_entry_gaps(monkeypatch):
    collector, state, session, entry, journals = pending(monkeypatch)
    _old_episode(state)
    first = _observe_quote_before_entry(collector, state, session, entry, journals)
    second = first + timedelta(minutes=1)
    other = deepcopy(entry)
    other.update(episode_key="two", instrument_key="US:TWO", decision_at=(first + timedelta(seconds=2)).isoformat(),
                 entry_at=second.isoformat(), quote={**quote((second - timedelta(seconds=2)).isoformat()),
                 "instrument_key": "US:TWO", "collector_available_at": (second - timedelta(seconds=2)).isoformat()})
    session["entries_pending"]["US:TWO"] = other
    session["candidates"]["US:TWO"] = {}
    between = source_event("TRADE", at=(first + timedelta(seconds=20)).isoformat(), sequence=0, price=101.05,
                           regular=True)
    proof = frontier((second + timedelta(seconds=1)).isoformat())
    state, journals, _ = collector._cycle(state, {}, [between, proof], [], second + timedelta(seconds=5))
    assert {r["instrument_key"] for r in state["ledger"]["research"].values()} == {"US:OLD", INSTRUMENT, "US:TWO"}
    kinds = [j["type"] for j in journals]
    assert kinds.index("DATA_GAP") < kinds.index("CANDIDATE_ENTRY")
    # The evidence between both entries is applied after the first, before the second.
    order = [j.get("instrument_key") or j.get("source", {}).get("event_id")
             for j in journals if j["type"] in {"CANDIDATE_ENTRY", "SOURCE_EVENT"}]
    assert order == [INSTRUMENT, between["event_id"], "US:TWO", proof["event_id"]]
    assert "DATA_GAP" in state["ledger"]["research"]["old"]["flags"]


def test_out_of_order_at_within_one_source_across_entry_boundary(monkeypatch):
    # P1-3: sequence is receipt order and `at` provider time. A late print
    # (seq 1, at < entry_at) after a tick (seq 0, at > entry_at) is contiguous;
    # splitting the receipt at entry_at must not invent a global sequence gap,
    # nor may the deferred tick's re-offer create a second one.
    collector, state, session, entry, journals = pending(monkeypatch)
    at = _observe_quote_before_entry(collector, state, session, entry, journals)
    e0 = source_event("TRADE", at=(at + timedelta(milliseconds=5)).isoformat(), sequence=0, price=101.05,
                      regular=True, instrument_key="US:OTHER")
    e1 = source_event("TRADE", at=(at - timedelta(milliseconds=5)).isoformat(), sequence=1, price=101.05,
                      regular=True, instrument_key="US:OTHER")
    e1["available_at"] = e0["available_at"]
    # No frontier proof yet: the entry waits and the tick dated after it is deferred.
    state, journals, _ = collector._cycle(state, {}, deepcopy([e0, e1]), [], at + timedelta(seconds=2))
    assert set(state["event_receipts"]) == {e1["event_id"]}
    assert state["event_sequence_deferred"] == {e0["event_id"]: ["synthetic-source", 0]}
    assert not state["data_issues"] and INSTRUMENT in session["entries_pending"]
    proof = frontier((at + timedelta(seconds=2)).isoformat())
    state, journals, _ = collector._cycle(state, {}, deepcopy([e0, e1, proof]), [], at + timedelta(seconds=3))
    assert not state["data_issues"]
    assert _new_record(state)["status"] == "OPEN" and "DATA_GAP" not in _new_record(state)["flags"]
    assert "event_sequence_deferred" not in state
    assert state["event_sequences"] == {"synthetic-source": 1, "frontier-source": 0}


def test_real_sequence_gap_is_still_global_and_covers_new_episode(monkeypatch):
    collector, state, session, entry, journals = pending(monkeypatch)
    at = _observe_quote_before_entry(collector, state, session, entry, journals)
    skipped = source_event("TRADE", at=(at - timedelta(seconds=1)).isoformat(), sequence=1, price=101.05,
                           regular=True, instrument_key="US:OTHER")
    state, journals, _ = collector._cycle(state, {}, [skipped, _late_print(at)], [], at + timedelta(seconds=2))
    assert [(i["reason"], i["instrument"]) for i in state["data_issues"]] == [("EVENT_SEQUENCE_GAP", "*")]
    assert "DATA_GAP" in _new_record(state)["flags"]


def test_deferred_cycle_receipts_are_released_on_acknowledgement(monkeypatch):
    # P2-4: a composite gap receipted by a deferred cycle and not offered again
    # is released with the acknowledged cursor, not kept forever.
    collector, state, session, entry, journals = pending(monkeypatch)
    _old_episode(state, coverage="2026-09-08T13:59:00+00:00")
    at = _observe_quote_before_entry(collector, state, session, entry, journals)
    now = at + timedelta(seconds=40)
    gap = source_event("DATA_GAP", at="2026-09-08T13:59:00+00:00", available_at=now.isoformat(), sequence=0,
                       instrument_key="US:OLD", source_id="composite-barrier-v2", event_id="composite-gap:x",
                       reason="BAR_WAIT_TIMEOUT")
    later = source_event("TRADE", at=(at + timedelta(seconds=30)).isoformat(), sequence=0, price=100.,
                         regular=True, instrument_key="US:OLD")
    proof = frontier((at + timedelta(seconds=1)).isoformat())
    receipts = {e["event_id"]: e["envelope_sha256"] for e in (gap, later, proof)}
    state["raw_source_cursor"] = {"position": 0}
    state, journals, _ = collector._cycle_with_cursor(state, {}, deepcopy([gap, later, proof]), [], now,
        causal=None, cursor={"position": 0}, next_cursor={"position": 1}, raw_receipts=receipts)
    assert state["raw_source_cursor"] == {"position": 0}
    assert set(state["event_receipts"]) == {gap["event_id"]}
    assert state["provisional_receipts"] == {gap["event_id"]: gap["envelope_sha256"]}
    assert _new_record(state)["status"] == "OPEN"
    # The re-offer from the same position no longer carries the gap.
    receipts.pop(gap["event_id"])
    state, journals, _ = collector._cycle_with_cursor(state, {}, deepcopy([later, proof]), [], now + timedelta(seconds=1),
        causal=None, cursor={"position": 0}, next_cursor={"position": 1}, raw_receipts=receipts)
    assert state["raw_source_cursor"] == {"position": 1}
    assert not state["event_receipts"] and "provisional_receipts" not in state
    assert "event_sequence_deferred" not in state
    ack = next(j for j in journals if j["type"] == "SOURCE_CURSOR")
    assert ack["released_receipts"] == {gap["event_id"]: gap["envelope_sha256"]}
    assert not [i for i in state["data_issues"] if i["reason"] == "EVENT_SEQUENCE_GAP"]


def test_deferred_receipt_mutation_before_acknowledgement_still_detected(monkeypatch):
    from app.r2d2_v2_store import ShadowIntegrityError
    import pytest
    collector, state, session, entry, journals = pending(monkeypatch)
    at = _observe_quote_before_entry(collector, state, session, entry, journals)
    gap = source_event("DATA_GAP", at="2026-09-08T13:59:00+00:00", available_at=(at + timedelta(seconds=1)).isoformat(),
                       sequence=0, instrument_key="US:OLD", source_id="composite-barrier-v2",
                       event_id="composite-gap:x", reason="BAR_WAIT_TIMEOUT")
    # The entry awaits its frontier, so the tick dated after it is deferred.
    later = source_event("TRADE", at=(at + timedelta(seconds=1)).isoformat(), sequence=0, price=100.,
                         regular=True, instrument_key="US:OTHER")
    state["raw_source_cursor"] = {"position": 0}
    state, _, _ = collector._cycle_with_cursor(state, {}, deepcopy([gap, later]), [], at + timedelta(seconds=2),
        causal=None, cursor={"position": 0}, next_cursor={"position": 1},
        raw_receipts={e["event_id"]: e["envelope_sha256"] for e in (gap, later)})
    assert state["raw_source_cursor"] == {"position": 0}
    assert state["provisional_receipts"] == {gap["event_id"]: gap["envelope_sha256"]}
    with pytest.raises(ShadowIntegrityError, match="EVENT_ID_MUTATED"):
        collector._cycle_with_cursor(state, {}, [{**gap, "envelope_sha256": "f" * 64}], [], at + timedelta(seconds=3),
            causal=None, cursor={"position": 0}, next_cursor={"position": 1},
            raw_receipts={gap["event_id"]: "f" * 64})


def test_restart_backlog_with_quote_hole_never_holds_stream_past_wait(monkeypatch):
    # Restart with backlog and no quote received after entry_at: the entry may
    # hold evidence dated at/after it only through entry_at + 150 s of collector
    # time, then resolves explicitly and the other episodes' evidence flows.
    from app.r2d2_v2_shadow import ENTRY_FRONTIER_WAIT
    collector, state, session, entry, journals = pending(monkeypatch)
    at = _observe_quote_before_entry(collector, state, session, entry, journals)
    _old_episode(state, coverage=at.isoformat())
    bars = []
    for minute in range(2):
        start, end = at + timedelta(minutes=minute), at + timedelta(minutes=minute + 1)
        bars.append(source_event("BAR", at=start.isoformat(), available_at=end.isoformat(), sequence=minute,
            end_at=end.isoformat(), open=100., high=100., low=100., close=100., regular=True,
            coverage_complete=True, instrument_key="US:OLD"))
    backlog = {"held": {}, "backlog": True}
    edge = at + ENTRY_FRONTIER_WAIT
    state, _, _ = collector._cycle(state, {}, deepcopy(bars), [], edge, frontier=backlog)
    assert INSTRUMENT in session["entries_pending"] and not state["event_receipts"]
    state, journals, _ = collector._cycle(state, {}, deepcopy(bars), [], edge + timedelta(seconds=1), frontier=backlog)
    assert session["candidates"][INSTRUMENT]["entry_reason"] == "ENTRY_QUOTE_FRONTIER_TIMEOUT"
    assert set(state["event_receipts"]) == {bar["event_id"] for bar in bars}
    assert state["coverage_until"]["US:OLD"] == bars[-1]["end_at"]
    assert not state["data_issues"] and "DATA_GAP" not in state["ledger"]["research"]["old"]["flags"]
    kinds = [j["type"] for j in journals]
    assert kinds.index("CANDIDATE_ENTRY") < kinds.index("SOURCE_EVENT")


def test_backlog_before_entry_is_not_held_and_keeps_waiting(monkeypatch):
    # Past the wait, a backlog still dated before entry_at advances normally;
    # the entry keeps waiting for the frontier the backlog will deliver.
    collector, state, session, entry, journals = pending(monkeypatch)
    at = _observe_quote_before_entry(collector, state, session, entry, journals)
    early = source_event("TRADE", at=(at - timedelta(seconds=2)).isoformat(), sequence=0, price=100.,
                         regular=True, instrument_key="US:OTHER")
    now = at + timedelta(minutes=20)
    state, _, _ = collector._cycle(state, {}, [early], [], now, frontier={"held": {}, "backlog": True})
    assert INSTRUMENT in session["entries_pending"] and early["event_id"] in state["event_receipts"]
    state, _, _ = collector._cycle(state, {}, [_late_print(at)], [], now + timedelta(seconds=1),
                                   frontier={"held": {}, "backlog": True})
    assert _new_record(state)["opened_at"] == entry["entry_at"]
