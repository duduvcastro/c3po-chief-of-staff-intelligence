from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import math

import pytest

from tests.test_r2d2_v2_earnings_policy import component as earnings_component

from app.r2d2_v2_contract import (
    CandidateInputs, CandidateValidationError, DailyBar, EVIDENCE_COMPONENTS,
    FEE, NEW_YORK, RISK_C75, SLIPPAGE, SplitRecord,
    daily_metrics, entry_geometry, evaluate_candidate, input_complete,
)


def synthetic_snapshot() -> CandidateInputs:
    """The supplied calendar and prices are synthetic, not exchange observations."""
    session = date(2030, 4, 1)
    previous = []
    day = session - timedelta(days=1)
    while len(previous) < 61:
        if day.weekday() < 5:
            previous.append(day)
        day -= timedelta(days=1)
    previous = tuple(reversed(previous))
    horizon = []
    day = session
    while len(horizon) < 10:
        if day.weekday() < 5:
            horizon.append(day)
        day += timedelta(days=1)
    decision = datetime.combine(session, time(10), NEW_YORK)
    bars = tuple(DailyBar(day, 100., 101., 99., 100., 150_000.,
                          datetime.combine(day, time(16), NEW_YORK),
                          datetime.combine(day, time(16, 1), NEW_YORK),
                          complete=True, regular_session=True) for day in previous)
    evidence = decision - timedelta(seconds=1)
    return CandidateInputs(
        symbol="SYNTHETIC", market="NYSE", security_type="COMMON_STOCK", session_date=session,
        decision_at=decision, bid=99.95, ask=100.05,
        bid_at=decision-timedelta(seconds=10), ask_at=decision-timedelta(seconds=10), risk_score=RISK_C75,
        daily_bars=bars, previous_sessions=previous, horizon_sessions=tuple(horizon),
        horizon_close_at=datetime.combine(horizon[-1], time(16), NEW_YORK),
        splits=(), split_coverage_verified=True, daily_price_basis="RAW_UNADJUSTED",
        earnings_coverage_start=session, earnings_coverage_end=horizon[-1], earnings_coverage_verified=True,
        earnings_component=earnings_component(decision_at=decision,
            maturity_at=datetime.combine(horizon[-1], time(15,55), NEW_YORK), available_at=evidence),
        source_at={name: evidence for name in EVIDENCE_COMPONENTS},
        available_at={name: evidence for name in EVIDENCE_COMPONENTS},
        sources={name: "synthetic:"+name for name in EVIDENCE_COMPONENTS},
        source_versions={name: "fixture-v1" for name in EVIDENCE_COMPONENTS},
        source_hashes={name: hashlib.sha256(name.encode()).hexdigest() for name in EVIDENCE_COMPONENTS},
    )


def test_baseline_exact_contract_and_json_projection():
    snapshot = synthetic_snapshot()
    result = evaluate_candidate(snapshot)
    assert result.status == result.arm == "ELIGIBLE"
    assert result.reasons == ()
    assert result.atr14 == 2
    assert result.adv20 == 15_000_000
    assert result.spread == pytest.approx(.001)
    assert result.geometry == entry_geometry(100., 2.)
    payload = result.to_dict()
    assert payload["research_quantity"] == 1.0
    assert payload["portfolio_eligible"] is True
    assert payload["opened_at"] == snapshot.decision_at.astimezone(timezone.utc).isoformat()
    assert payload["maturity_at"] == (snapshot.horizon_close_at-timedelta(minutes=5)).astimezone(timezone.utc).isoformat()
    assert payload["provenance"]["risk"]["sha256"] == snapshot.source_hashes["risk"]
    json.dumps(payload, allow_nan=False)
    with pytest.raises(TypeError):
        result.geometry["S"] = 0
    payload["geometry"]["S"] = 0
    assert result.geometry["S"] > 0


@pytest.mark.parametrize("risk,expected", [(0., "ELIGIBLE"), (RISK_C75, "ELIGIBLE"),
    (math.nextafter(RISK_C75, math.inf), "CONTROL"), (44.106, "CONTROL"), (55., "CONTROL"), (100., "CONTROL")])
def test_risk_arms_use_full_precision_without_legacy_gate(risk, expected):
    result = evaluate_candidate(replace(synthetic_snapshot(), risk_score=risk))
    assert result.status == expected
    assert result.arm == expected
    assert result.to_dict()["research_eligible"] is True
    assert result.to_dict()["portfolio_eligible"] is (expected == "ELIGIBLE")


@pytest.mark.parametrize("risk", [None, True, False, "44.0", -1, 101., math.nan, math.inf, -math.inf, 10**1000])
def test_invalid_risk_is_counted_outside_both_arms(risk):
    result = evaluate_candidate(replace(synthetic_snapshot(), risk_score=risk))
    assert result.status == "DATA_INELIGIBLE"
    assert result.arm is None
    assert "RISK_SCORE_INVALID" in result.reasons
    json.dumps(result.to_dict(), allow_nan=False)


def test_completeness_is_separate_from_eligibility_and_known_missing_risk():
    snapshot = synthetic_snapshot()
    assert input_complete(snapshot)
    assert not input_complete(replace(snapshot, ask=None))
    assert not input_complete(replace(snapshot, available_at={}))
    missing_risk = replace(snapshot, risk_score=None)
    assert input_complete(missing_risk)
    assert evaluate_candidate(missing_risk).status == "DATA_INELIGIBLE"
    too_old = replace(snapshot, bid_at=snapshot.decision_at-timedelta(seconds=11))
    assert input_complete(too_old)
    assert "QUOTE_AGE_BID" in evaluate_candidate(too_old).reasons
    missing_quote = evaluate_candidate(replace(snapshot, ask=None))
    assert not missing_quote.complete
    assert "SNAPSHOT_INCOMPLETE" in missing_quote.reasons
    assert evaluate_candidate(CandidateInputs()).status == "DATA_INELIGIBLE"


@pytest.mark.parametrize("offset,inside", [(0, True), (59.999999, True), (60, False), (-.000001, False)])
def test_capture_window_is_half_open(offset, inside):
    snapshot = synthetic_snapshot()
    decision = snapshot.decision_at + timedelta(seconds=offset)
    stamp = decision-timedelta(seconds=1)
    result = evaluate_candidate(replace(snapshot, decision_at=decision, bid_at=stamp, ask_at=stamp,
        earnings_component=earnings_component(decision_at=decision,
            maturity_at=snapshot.horizon_close_at-timedelta(minutes=5), available_at=stamp),
        source_at={name:stamp for name in EVIDENCE_COMPONENTS}, available_at={name:stamp for name in EVIDENCE_COMPONENTS}))
    assert (result.status == "ELIGIBLE") is inside
    assert ("OUTSIDE_CAPTURE_WINDOW" in result.reasons) is not inside


def test_quote_each_side_age_integrity_and_policy_thresholds():
    snapshot = synthetic_snapshot()
    assert evaluate_candidate(snapshot).status == "ELIGIBLE"  # exactly10s
    for field in ("bid_at", "ask_at"):
        for delta in (timedelta(seconds=-10, microseconds=-1), timedelta(microseconds=1)):
            result = evaluate_candidate(replace(snapshot, **{field: snapshot.decision_at+delta}))
            assert "QUOTE_AGE_"+field[:3].upper() in result.reasons
    for updates in ({"bid":True}, {"ask":math.inf}, {"bid":100.1,"ask":100.}, {"ask":0.}):
        assert evaluate_candidate(replace(snapshot, **updates)).status == "DATA_INELIGIBLE"
    assert evaluate_candidate(replace(snapshot, bid=100., ask=100.)).status == "ELIGIBLE"
    wide = evaluate_candidate(replace(snapshot, bid=99., ask=101.))
    assert wide.status == "INELIGIBLE" and "SPREAD_TOO_WIDE" in wide.reasons
    assert "PRICE_BELOW_MINIMUM" in evaluate_candidate(replace(snapshot, bid=4.99, ask=4.99)).reasons


def test_evidence_future_and_hash_or_version_omissions_fail_closed():
    snapshot = synthetic_snapshot()
    for component in EVIDENCE_COMPONENTS:
        late = snapshot.decision_at+timedelta(seconds=1)
        result = evaluate_candidate(replace(snapshot, available_at=snapshot.available_at | {component:late}))
        assert "EVIDENCE_NOT_CAUSAL_"+component.upper() in result.reasons
    assert "EVIDENCE_PROVENANCE_RISK" in evaluate_candidate(replace(snapshot, source_hashes=snapshot.source_hashes | {"risk":""})).reasons
    assert "EVIDENCE_PROVENANCE_CALENDAR" in evaluate_candidate(replace(snapshot, source_versions=snapshot.source_versions | {"calendar":""})).reasons
    assert evaluate_candidate(replace(snapshot, source_at={})).arm is None


def test_calendar_exact_windows_and_regular_complete_bars():
    snapshot = synthetic_snapshot()
    for bars in (snapshot.daily_bars[:-1], tuple(reversed(snapshot.daily_bars)),
                 snapshot.daily_bars[:-1]+(snapshot.daily_bars[-2],)):
        assert evaluate_candidate(replace(snapshot,daily_bars=bars)).status == "DATA_INELIGIBLE"
    for updates in ({"complete":False}, {"regular_session":False}, {"high":98.}, {"volume":True},
                    {"available_at":snapshot.decision_at+timedelta(seconds=1)}):
        bars = snapshot.daily_bars[:-1]+(replace(snapshot.daily_bars[-1], **updates),)
        assert evaluate_candidate(replace(snapshot,daily_bars=bars)).status == "DATA_INELIGIBLE"
    for horizon in (snapshot.horizon_sessions[:-1], tuple(reversed(snapshot.horizon_sessions)),
                    (snapshot.horizon_sessions[1],)*10):
        assert "HORIZON_CALENDAR_INVALID" in evaluate_candidate(replace(snapshot,horizon_sessions=horizon)).reasons
    early_close = datetime.combine(snapshot.horizon_sessions[-1], time(13), NEW_YORK)
    result = evaluate_candidate(replace(snapshot,horizon_close_at=early_close,
        earnings_component=earnings_component(decision_at=snapshot.decision_at,
            maturity_at=early_close-timedelta(minutes=5))))
    assert result.maturity_at.astimezone(NEW_YORK).time() == time(12,55)


def test_wilder_seed_14_then_46_recursive_updates_not_last_sma():
    snapshot = synthetic_snapshot()
    # First60bars range2; finalbar range4. Sixty TRs, last recursion only differs.
    bars = snapshot.daily_bars[:-1]+(replace(snapshot.daily_bars[-1], high=102., low=98.),)
    result = evaluate_candidate(replace(snapshot,daily_bars=bars))
    assert result.atr14 == pytest.approx((13*2+4)/14)
    # Put the shock immediately after the seed: its effect must decay46 updates.
    bars = list(snapshot.daily_bars)
    bars[14] = replace(bars[14], high=102.,low=98.)
    result = evaluate_candidate(replace(snapshot,daily_bars=tuple(bars)))
    assert result.atr14 == pytest.approx(2+(2/14)*(13/14)**46)
    assert result.atr14 > 2  # SMA of the final14ranges would be exactly2.


@pytest.mark.parametrize("ratio", [2., .2])
def test_effective_known_split_normalizes_atr_without_changing_dollar_turnover(ratio):
    snapshot = synthetic_snapshot()
    effective = datetime.combine(snapshot.previous_sessions[30],time(9,30),NEW_YORK)
    split = SplitRecord(effective,ratio,effective-timedelta(days=3),effective-timedelta(days=2))
    bars = tuple(replace(bar,open=100*ratio,high=101*ratio,low=99*ratio,close=100*ratio,volume=150_000/ratio)
                 if index<30 else bar for index,bar in enumerate(snapshot.daily_bars))
    adjusted = evaluate_candidate(replace(snapshot,daily_bars=bars,splits=(split,)))
    assert adjusted.atr14 == pytest.approx(2.)
    assert adjusted.adv20 == pytest.approx(15_000_000.)
    unadjusted = evaluate_candidate(replace(snapshot,daily_bars=bars))
    assert unadjusted.atr14 != pytest.approx(2.)


def test_future_known_split_not_applied_and_unknown_split_cannot_leak():
    snapshot = synthetic_snapshot()
    known = snapshot.decision_at-timedelta(days=1)
    future_split = SplitRecord(snapshot.decision_at+timedelta(days=1),2.,known,known)
    assert evaluate_candidate(replace(snapshot,splits=(future_split,))).atr14 == 2.
    unavailable = future_split._replace(available_at=snapshot.decision_at+timedelta(seconds=1))
    assert "SPLIT_RECORD_INVALID" in evaluate_candidate(replace(snapshot,splits=(unavailable,))).reasons
    assert "SPLIT_DUPLICATE_EFFECTIVE_AT" in evaluate_candidate(replace(snapshot,splits=(future_split,future_split))).reasons
    assert "SPLIT_COVERAGE_UNVERIFIED" in evaluate_candidate(replace(snapshot,split_coverage_verified=False)).reasons
    assert "DAILY_PRICE_BASIS_UNVERIFIED" in evaluate_candidate(replace(snapshot,daily_price_basis="TOTAL_RETURN_ADJUSTED")).reasons


def test_adv_uses_last20_full_raw_sessions_and_piso_inclusive():
    snapshot = synthetic_snapshot()
    bars = tuple(replace(bar,volume=0.) if index<41 else bar for index,bar in enumerate(snapshot.daily_bars))
    assert evaluate_candidate(replace(snapshot,daily_bars=bars)).status == "ELIGIBLE"
    low = bars[:-1]+(replace(bars[-1],volume=149_999.),)
    result = evaluate_candidate(replace(snapshot,daily_bars=low))
    assert result.status == "INELIGIBLE"
    assert "ADV20_BELOW_MINIMUM" in result.reasons


def _earnings_event(snapshot, *, day=None, at=None, granularity="DAY", classification="EXCLUDES"):
    value = earnings_component(decision_at=snapshot.decision_at,
        maturity_at=snapshot.horizon_close_at-timedelta(minutes=5))
    when = at.astimezone(NEW_YORK).date() if at is not None else day
    item = {"event_date": when.isoformat(), "granularity": "INSTANT" if at is not None else granularity,
        "event_at": at.isoformat() if at is not None else None,
        "available_at": value["available_at"], "source": "calendar", "classification": classification}
    value["evidence"]["known_events"] = [item]
    value["evidence"]["cadence_applicable"] = False
    value["events"] = [{k: item[k] for k in ("event_date", "granularity", "available_at") +
        (("event_at",) if at is not None else ())}]
    excluded = classification == "EXCLUDES"
    value["exclusion"] = {"excluded": excluded, "reasons": ["EARNINGS_WITHIN_HORIZON"] if excluded else []}
    return value


def test_e3_exclusion_and_missing_evidence_are_data_before_both_risk_arms():
    snapshot = synthetic_snapshot()
    for risk in (20., 60.):
        value = _earnings_event(snapshot, day=snapshot.horizon_sessions[4])
        scheduled = evaluate_candidate(replace(snapshot,risk_score=risk,earnings_component=value))
        assert scheduled.status == "DATA_INELIGIBLE" and scheduled.arm is None
        assert scheduled.reasons == ("EARNINGS_WITHIN_HORIZON",)
        unknown = evaluate_candidate(replace(snapshot,risk_score=risk,earnings_component=None))
        assert unknown.status == "DATA_INELIGIBLE" and unknown.arm is None
        assert "EARNINGS_EVIDENCE_INVALID" in unknown.reasons
    for day in (snapshot.session_date,snapshot.horizon_sessions[-1]):
        for granularity in ("DAY", "BMO", "AMC"):
            value = _earnings_event(snapshot, day=day, granularity=granularity)
            assert evaluate_candidate(replace(snapshot, earnings_component=value)).reasons == ("EARNINGS_WITHIN_HORIZON",)


def test_legacy_fields_neither_grant_coverage_nor_override_signed_component():
    snapshot = synthetic_snapshot()
    assert evaluate_candidate(replace(snapshot, earnings_component=None)).status == "DATA_INELIGIBLE"
    changed = replace(snapshot, earnings_coverage_verified=False, earnings_coverage_end=None,
        earnings_dates=(snapshot.session_date,), earnings_at=(snapshot.decision_at,))
    assert evaluate_candidate(changed).status == "ELIGIBLE"


def test_earnings_precise_instant_respects_inclusive_entry_and_maturity():
    snapshot = synthetic_snapshot()
    maturity = snapshot.horizon_close_at-timedelta(minutes=5)
    for at in (snapshot.decision_at,maturity):
        value = _earnings_event(snapshot, at=at)
        assert evaluate_candidate(replace(snapshot,earnings_component=value)).reasons == ("EARNINGS_WITHIN_HORIZON",)
    for at, classification in ((snapshot.decision_at-timedelta(microseconds=1),"PUBLISHED_BEFORE_DECISION"),
            (maturity+timedelta(microseconds=1),"AFTER_MATURITY")):
        value = _earnings_event(snapshot, at=at, classification=classification)
        assert evaluate_candidate(replace(snapshot,earnings_component=value)).status == "ELIGIBLE"


def test_earnings_component_cannot_move_calendar_maturity_or_nominal_boundary():
    snapshot = synthetic_snapshot()
    value = earnings_component(decision_at=snapshot.decision_at,
        maturity_at=snapshot.horizon_close_at-timedelta(minutes=6))
    assert evaluate_candidate(replace(snapshot,earnings_component=value)).reasons == ("EARNINGS_EVIDENCE_INVALID",)
    later = snapshot.decision_at + timedelta(seconds=37)
    shifted = replace(snapshot,decision_at=later,bid_at=later,ask_at=later,
        source_at={name: later for name in EVIDENCE_COMPONENTS},
        available_at={name: later for name in EVIDENCE_COMPONENTS})
    unchanged = evaluate_candidate(shifted)
    assert unchanged.status == "ELIGIBLE"
    actual = earnings_component(decision_at=later,maturity_at=snapshot.horizon_close_at-timedelta(minutes=5))
    assert evaluate_candidate(replace(shifted,earnings_component=actual)).status == "ELIGIBLE"
    actual["evidence"]["decision_at"] = later.isoformat()
    assert evaluate_candidate(replace(shifted,earnings_component=actual)).reasons == ("EARNINGS_EVIDENCE_INVALID",)


def test_geometry_net_plus_minus_one_r_including_sequential_costs():
    g = entry_geometry(100.,2.)
    net = lambda price: price*(1-SLIPPAGE)*(1-FEE)
    assert g["B"] == pytest.approx(100.1)
    assert g["C"] == pytest.approx(100.14004)
    assert g["S"] == pytest.approx(97.1)
    assert net(g["S"])-g["C"] == pytest.approx(-g["R_unit"])
    assert net(g["T"])-g["C"] == pytest.approx(g["R_unit"])
    assert g["R_unit"] > 1.5*2.  # Costs are part of the economic one-R.
    for atr in (.01,100.):
        with pytest.raises(CandidateValidationError,match="GEOMETRY_INELIGIBLE"):
            entry_geometry(100.,atr)
    with pytest.raises(CandidateValidationError,match="GEOMETRY_INPUT_INVALID"):
        entry_geometry(True,2.)


def test_universe_invalid_or_known_excluded_is_not_a_control():
    snapshot = synthetic_snapshot()
    assert evaluate_candidate(replace(snapshot,security_type="COMMON_STOCK_ADR")).status == "ELIGIBLE"
    assert evaluate_candidate(replace(snapshot,security_type="ETF")).status == "INELIGIBLE"
    assert evaluate_candidate(replace(snapshot,security_type=None)).status == "DATA_INELIGIBLE"
    assert evaluate_candidate(replace(snapshot,market="B3")).arm is None
    assert evaluate_candidate(replace(snapshot,market=None)).status == "DATA_INELIGIBLE"


def test_evaluation_does_not_mutate_inputs_or_require_global_state():
    snapshot = synthetic_snapshot()
    bars,metadata = snapshot.daily_bars,dict(snapshot.available_at)
    first = evaluate_candidate(snapshot).to_dict()
    second = evaluate_candidate(snapshot).to_dict()
    assert first == second
    assert snapshot.daily_bars is bars
    assert snapshot.available_at == metadata
