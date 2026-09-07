"""Synthetic ledger counterexamples only: no prices, providers or application I/O."""
import copy
import json

import pytest
from tests.v2_earnings_fixtures import observation

from app.r2d2_v2_portfolio import (
    PortfolioInputError, SELL_FACTOR, apply_event, apply_events,
    export_session_statistics, new_portfolio, portfolio_summary, register_candidate,
)

SESSION = "2026-09-08"
OPEN = "2026-09-08T14:00:00+00:00"
MATURITY = "2026-09-21T19:55:00+00:00"


def geometry(price=100.0, stop=97.0):
    b = price * 1.001
    c = b * 1.0004
    r = c - stop * SELL_FACTOR
    return {"P": price, "B": b, "C": c, "S": stop, "T": (c + r) / SELL_FACTOR, "R_unit": r}


def candidate(state=None, key="a", instrument="private-a", arm="ELIGIBLE", **kwargs):
    return register_candidate(new_portfolio() if state is None else state, episode_key=key,
        instrument_key=instrument, arm=arm, session=kwargs.pop("session", SESSION),
        opened_at=kwargs.pop("opened_at", OPEN), maturity_at=kwargs.pop("maturity_at", MATURITY),
        geometry=kwargs.pop("geometry", geometry()), **kwargs)


def event(kind, n=1, *, at="2026-09-08T14:01:00+00:00", available_at=None,
          session=SESSION, instrument="private-a", **values):
    base = dict(event_id=f"private-event-{n}", type=kind, at=at,
                available_at=available_at or at, session=session)
    if not kind.startswith("SESSION_"):
        base["instrument_key"] = instrument
    result = {**base, **values}
    return observation(result) if kind == "EARNINGS" else result


def bar(n=1, **kw):
    defaults = dict(at="2026-09-08T14:01:00+00:00", end_at="2026-09-08T14:02:00+00:00",
                    available_at="2026-09-08T14:02:00+00:00", open=100.0,
                    high=101.0, low=99.0, close=100.0, regular=True, coverage_complete=True)
    defaults.update(kw)
    return event("BAR", n, **defaults)


def quote(n=1, **kw):
    at = kw.get("at", "2026-09-08T14:01:00+00:00")
    defaults = dict(at=at, bid=99.9, ask=100.1, bid_at=at, ask_at=at, regular=True)
    defaults.update(kw)
    return event("QUOTE", n, **defaults)


def apply(state, item):
    return apply_event(state, item)[0]


def test_research_one_share_and_portfolio_risk_quantity_are_independent():
    initial = new_portfolio()
    state, research, admission = candidate(initial)
    assert initial == new_portfolio()
    assert research["q0"] == 1
    quantity = admission["quantity"]
    assert quantity * geometry()["R_unit"] <= 200
    assert 200 - quantity * geometry()["R_unit"] < 0.00001
    assert state["portfolio"]["a"]["q0"] == quantity
    summary = portfolio_summary(state)
    assert summary["nav_usd"] == pytest.approx(1_000_000 - quantity * (geometry()["C"] - 100))
    assert summary["cash_identity_passed"]
    json.dumps(state, allow_nan=False)


def test_controls_and_overlapping_daily_research_survive_portfolio_constraints():
    state, _, rejected = candidate(arm="CONTROL")
    assert rejected["reason"] == "CONTROL_RESEARCH_ONLY"
    assert len(state["research"]) == 1 and not state["portfolio"]
    state = apply(state, event("SESSION_CLOSE", at="2026-09-08T20:00:00+00:00"))
    state = apply(state, event("SESSION_OPEN", 2, at="2026-09-09T13:30:00+00:00", session="2026-09-09"))
    state, _, admission = candidate(state, key="b", session="2026-09-09", opened_at="2026-09-09T14:00:00+00:00")
    assert len(state["research"]) == 2 and admission["admitted"]


def test_same_name_session_cannot_get_another_snapshot_even_with_new_key():
    state, _, _ = candidate()
    with pytest.raises(PortfolioInputError, match="first complete"):
        candidate(state, key="replacement")
    same, _, _ = candidate(state)
    assert same == state
    with pytest.raises(PortfolioInputError, match="Conflicting candidate"):
        candidate(state, geometry=geometry(stop=96))


def test_cash_name_market_capacity_and_six_decimal_quantity():
    state = new_portfolio()
    for n in range(12):
        state, _, result = candidate(state, key=str(n), instrument=f"private-{n}", geometry=geometry(stop=99.99))
        assert result["quantity"] == round(result["quantity"], 6)
        if result["admitted"]:
            position = state["portfolio"][str(n)]
            assert position["entry_cost"] <= 60_000
    totals = portfolio_summary(state)
    assert totals["gross_exposure_usd"] <= .48 * totals["nav_usd"] + .01
    assert totals["cash_usd"] >= .05 * totals["nav_usd"]
    assert any(x["reason"] != "ADMITTED" for x in state["candidate_results"].values())


def test_daily_loss_and_terminal_nav_veto_are_distinct_and_exits_continue():
    state, _, _ = candidate(geometry=geometry(stop=99.99))
    state = apply(state, event("MARK", price=50.0, regular=True))
    state, _, admission = candidate(state, key="b", instrument="private-b", opened_at="2026-09-08T14:01:01+00:00")
    assert admission["reason"] == "DAILY_LOSS_LIMIT"
    assert not state["terminal_reasons"]
    state = apply(state, event("MARK", 2, at="2026-09-08T14:02:00+00:00", price=1.0, regular=True))
    assert state["terminal_reasons"] == ["V2_CERTIFICATION_FAILED_NAV"]
    state = apply(state, event("TRADE", 3, at="2026-09-08T14:03:00+00:00", price=1.0, regular=True))
    assert state["portfolio"]["a"]["status"] == "CLOSED"


def test_quotes_do_not_trigger_trade_barriers_and_granular_stop_keeps_gap_price():
    state, _, _ = candidate()
    state = apply(state, quote(bid=89.9, ask=90.1))
    assert state["research"]["a"]["status"] == "OPEN"
    state = apply(state, event("TRADE", 2, at="2026-09-08T14:02:00+00:00", price=90.0, regular=True))
    row = state["research"]["a"]
    assert row["category"] == "lower_first" and row["exit_price"] == 90
    assert row["exit_proceeds"] == pytest.approx(90 * SELL_FACTOR)
    assert row["fill_evidence"] == "DEMONSTRATED_TRADE_REFERENCE"


@pytest.mark.parametrize("opening,category,price", [(90.0, "lower_first", 90.0), (110.0, "upper_first", geometry()["T"])])
def test_opening_gap_is_not_ambiguous_when_later_range_hits_both(opening, category, price):
    state, _, _ = candidate()
    state = apply(state, bar(open=opening, low=85.0, high=115.0, close=100.0))
    assert state["research"]["a"]["category"] == category
    assert state["research"]["a"]["exit_price"] == price


def test_two_barrier_ambiguity_uses_stop_first_only_for_portfolio():
    state, _, _ = candidate()
    state = apply(state, bar(low=95.0, high=110.0))
    research, position = state["research"]["a"], state["portfolio"]["a"]
    assert research["category"] == position["category"] == "ambiguous"
    assert research["exit_price"] is None and research["accounting_unknown"]
    assert position["exit_price"] == 97 and position["fill_evidence"] == "MODELED_BARRIER_FILL"
    stats = export_session_statistics(state, SESSION)
    assert stats["arms"]["ELIGIBLE"]["ambiguous"] == 1
    assert stats["arms"]["ELIGIBLE"]["upper_first"] == stats["arms"]["ELIGIBLE"]["lower_first"] == 0
    assert stats["portfolio_pnl_usd_sum"] is not None


def test_single_intrabar_stop_is_modeled_and_does_not_invent_exact_timestamp():
    state, _, _ = candidate()
    state = apply(state, bar(low=95.0))
    row = state["research"]["a"]
    assert row["category"] == "lower_first"
    assert row["exit_price"] == 97 and row["exit_at"] is None
    assert row["exit_interval"] and row["fill_evidence"] == "MODELED_BARRIER_FILL"


def test_partial_entry_bar_without_trades_is_unknown_and_later_price_does_not_repair_order():
    state, _, _ = candidate(opened_at="2026-09-08T14:00:30+00:00")
    state = apply(state, bar(at=OPEN, end_at="2026-09-08T14:01:00+00:00", available_at="2026-09-08T14:01:00+00:00"))
    assert "PARTIAL_ENTRY_BAR_WITHOUT_TRADES" in state["research"]["a"]["flags"]
    state = apply(state, event("TRADE", 2, at="2026-09-08T14:02:00+00:00", price=90.0, regular=True))
    assert state["research"]["a"]["category"] == "unobservable"
    assert portfolio_summary(state)["nav_usd"] is None
    assert export_session_statistics(state, SESSION)["data_gate_unknown"]


def test_complete_granular_entry_bar_ignores_preentry_touch():
    state, _, _ = candidate(opened_at="2026-09-08T14:00:30+00:00")
    trades = [{"at": OPEN, "price": 100.0}, {"at": "2026-09-08T14:00:10+00:00", "price": 90.0},
              {"at": "2026-09-08T14:00:40+00:00", "price": 110.0}]
    state = apply(state, bar(at=OPEN, end_at="2026-09-08T14:01:00+00:00", available_at="2026-09-08T14:01:00+00:00",
                            low=90.0, high=110.0, close=110.0, trades=trades))
    assert state["research"]["a"]["category"] == "upper_first"
    assert state["research"]["a"]["exit_at"] == trades[-1]["at"]


def test_split_transforms_execution_only_and_preserves_every_cash_identity():
    state, _, _ = candidate()
    original = copy.deepcopy(state["portfolio"]["a"])
    before = portfolio_summary(state)
    state = apply(state, event("SPLIT", factor=2.0))
    row = state["portfolio"]["a"]
    assert row["original"] == original["original"]
    assert row["q0"] == original["q0"] and row["quantity"] == original["quantity"] * 2
    assert row["geometry"] == {k: v / 2 for k, v in original["geometry"].items()}
    assert row["initial_r_usd"] == original["initial_r_usd"]
    assert portfolio_summary(state)["nav_usd"] == before["nav_usd"]
    state = apply(state, event("TRADE", 2, at="2026-09-08T14:02:00+00:00", price=48.5, regular=True))
    pnl = export_session_statistics(state, SESSION)["portfolio_pnl_usd_sum"]
    assert pnl == pytest.approx(-original["initial_r_usd"])


def test_dividend_receivable_payment_after_sale_never_double_counts_or_moves_barriers():
    state, _, _ = candidate()
    original = copy.deepcopy(state["portfolio"]["a"])
    state = apply(state, event("DIVIDEND_ENTITLEMENT", entitlement_id="private-div", net_per_share=1.25))
    assert state["portfolio"]["a"]["geometry"] == original["geometry"]
    assert state["cash"] == pytest.approx(1_000_000 - original["entry_cost"])
    state = apply(state, event("TRADE", 2, at="2026-09-08T14:02:00+00:00", price=97.0, regular=True))
    before = portfolio_summary(state)
    state = apply(state, event("DIVIDEND_PAYMENT", 3, at="2026-09-08T14:03:00+00:00", entitlement_id="private-div"))
    after = portfolio_summary(state)
    assert after["nav_usd"] == pytest.approx(before["nav_usd"])
    assert after["receivables_usd"] == 0
    assert after["cash_usd"] - before["cash_usd"] == pytest.approx(original["quantity"] * 1.25)
    assert export_session_statistics(state, SESSION)["portfolio_pnl_usd_sum"] == pytest.approx(-original["initial_r_usd"] + original["quantity"] * 1.25)


def test_unsupported_net_dividend_is_unknown_not_zero():
    state, _, _ = candidate()
    state = apply(state, event("DIVIDEND_ENTITLEMENT", entitlement_id="private-div", net_per_share=None))
    assert portfolio_summary(state)["nav_usd"] is None
    assert export_session_statistics(state, SESSION)["portfolio_pnl_usd_sum"] is None


def test_earnings_closes_both_research_arms_at_first_valid_postintent_quote():
    state, _, _ = candidate()
    state, _, _ = candidate(state, key="control", instrument="private-b", arm="CONTROL")
    items = [event("EARNINGS", 1, earnings_at="2026-09-15T12:00:00+00:00"),
             event("EARNINGS", 2, instrument="private-b", earnings_at="2026-09-15T12:00:00+00:00"),
             quote(3, at="2026-09-08T14:01:01+00:00"),
             quote(4, instrument="private-b", at="2026-09-08T14:01:01+00:00")]
    state, _ = apply_events(state, items)
    assert {r["category"] for r in state["research"].values()} == {"time_or_event_exit"}
    assert len(state["portfolio"]) == 1
    assert state["portfolio"]["a"]["exit_cause"] == "EVENT"


def test_time_intent_is_not_backfilled_by_quote_from_before_deadline():
    maturity = "2026-09-08T14:01:00+00:00"  # supplied synthetic calendar boundary
    state, _, _ = candidate(maturity_at=maturity)
    state = apply(state, event("MATURITY"))
    state = apply(state, quote(2, at="2026-09-08T14:01:01+00:00", bid_at="2026-09-08T14:00:59+00:00"))
    assert state["portfolio"]["a"]["status"] == "OPEN"
    state = apply(state, quote(3, at="2026-09-08T14:01:02+00:00"))
    assert state["portfolio"]["a"]["exit_at"] == "2026-09-08T14:01:02+00:00"


def test_horizon_breach_retains_position_and_late_close_does_not_replace_n10_endpoint():
    state, _, _ = candidate(maturity_at="2026-09-08T19:55:00+00:00")
    state = apply(state, event("MATURITY", at="2026-09-08T19:55:00+00:00"))
    state = apply(state, event("SESSION_CLOSE", 2, at="2026-09-08T20:00:00+00:00"))
    assert state["portfolio"]["a"]["status"] == "OPEN"
    state = apply(state, event("SESSION_OPEN", 3, at="2026-09-09T13:30:00+00:00", session="2026-09-09"))
    state = apply(state, quote(4, at="2026-09-09T13:30:01+00:00", session="2026-09-09"))
    row = state["portfolio"]["a"]
    assert row["status"] == "CLOSED" and row["horizon_breach"]
    assert row["exit_at"].startswith("2026-09-09")
    assert export_session_statistics(state, SESSION)["portfolio_pnl_usd_sum"] is None


def test_same_instant_stop_beats_time_intent_and_charges_one_exit():
    state, _, _ = candidate(maturity_at="2026-09-08T14:01:00+00:00")
    state, _ = apply_events(state, [event("MATURITY"), event("TRADE", 2, price=95.0, regular=True), quote(3)])
    assert state["portfolio"]["a"]["exit_cause"] == "STOP"
    assert portfolio_summary(state)["cash_identity_passed"]


@pytest.mark.parametrize("cause", ["EARNINGS", "MATURITY"])
@pytest.mark.parametrize("arm", ["ELIGIBLE", "CONTROL"])
@pytest.mark.parametrize("low,high", [(95.0, 101.0), (99.0, 110.0), (95.0, 110.0)])
def test_event_inside_bar_with_touch_does_not_invent_chronology(cause, arm, low, high):
    when = "2026-09-08T14:01:30+00:00"
    state, _, _ = candidate(arm=arm, maturity_at=when if cause == "MATURITY" else MATURITY)
    values = {"earnings_at": "2026-09-15T12:00:00+00:00"} if cause == "EARNINGS" else {}
    state = apply(state, event(cause, at=when, **values))
    state = apply(state, bar(2, low=low, high=high))
    research = state["research"]["a"]
    assert research["category"] == "unobservable"
    assert research["exit_price"] is None and research["exit_at"] is None
    assert research["accounting_unknown"] and research["order_unknown"]
    assert research["exit_cause"] == "EVENT_BARRIER_ORDER_UNRESOLVED"
    stats = export_session_statistics(state, SESSION)
    assert stats["arms"][arm]["unobservable"] == 1
    assert stats["arms"][arm]["ambiguous"] == 0
    assert stats["arms"][arm]["upper_first"] == stats["arms"][arm]["lower_first"] == 0
    assert stats["data_gate_unknown"]
    if arm == "CONTROL":
        assert not state["portfolio"] and stats["finalized"]
        return
    assert state["portfolio"]["a"]["status"] == "OPEN"
    assert stats["portfolio_pnl_usd_sum"] is None and not stats["finalized"]
    assert portfolio_summary(state)["nav_usd"] is None
    state = apply(state, quote(3, at="2026-09-08T14:02:01+00:00"))
    later = export_session_statistics(state, SESSION)
    assert later["finalized"] and later["portfolio_pnl_usd_sum"] is None
    assert later["data_gate_unknown"]  # A later quote cannot reconstruct the missing order.


@pytest.mark.parametrize("cause", ["EARNINGS", "MATURITY"])
@pytest.mark.parametrize("arm", ["ELIGIBLE", "CONTROL"])
@pytest.mark.parametrize("opening,category,price", [(90.0, "lower_first", 90.0),
                                                    (110.0, "upper_first", geometry()["T"])])
def test_demonstrated_bar_open_precedes_intent_inside_interval(cause, arm, opening, category, price):
    when = "2026-09-08T14:01:30+00:00"
    state, _, _ = candidate(arm=arm, maturity_at=when if cause == "MATURITY" else MATURITY)
    values = {"earnings_at": "2026-09-15T12:00:00+00:00"} if cause == "EARNINGS" else {}
    state = apply(state, event(cause, at=when, **values))
    state = apply(state, bar(2, open=opening, low=85.0, high=115.0, close=100.0))
    research = state["research"]["a"]
    assert research["category"] == category and research["exit_price"] == price
    assert research["exit_at"] == "2026-09-08T14:01:00+00:00"
    assert not research["order_unknown"] and not research["accounting_unknown"]
    assert not export_session_statistics(state, SESSION)["data_gate_unknown"]
    if arm == "ELIGIBLE":
        assert state["portfolio"]["a"]["exit_price"] == price
        assert portfolio_summary(state)["cash_identity_passed"]


def test_gap_is_economic_dividend_adjusted_and_gains_do_not_offset_losses():
    state, _, _ = candidate(geometry=geometry(stop=99.99))
    state, _, _ = candidate(state, key="b", instrument="private-b", geometry=geometry(stop=99.99))
    state = apply(state, event("SESSION_CLOSE", at="2026-09-08T20:00:00+00:00"))
    state = apply(state, event("SESSION_OPEN", 2, at="2026-09-09T13:30:00+00:00", session="2026-09-09"))
    assert portfolio_summary(state)["nav_usd"] is None
    state = apply(state, event("DIVIDEND_ENTITLEMENT", 3, at="2026-09-09T13:30:00+00:00", session="2026-09-09", entitlement_id="private-div", net_per_share=1.0))
    state = apply(state, event("MARK", 4, at="2026-09-09T13:30:01+00:00", session="2026-09-09", price=70.0, regular=True))
    q = state["portfolio"]["a"]["quantity"]
    assert state["gap_loss_usd"] == pytest.approx(q * 29)
    state = apply(state, event("MARK", 5, instrument="private-b", at="2026-09-09T13:30:01+00:00", session="2026-09-09", price=130.0, regular=True))
    assert state["gap_loss_usd"] == pytest.approx(q * 29)
    assert "V2_CERTIFICATION_FAILED_GAP" in state["terminal_reasons"]


def test_duplicate_events_are_idempotent_payload_conflicts_rejected_and_batch_atomic():
    state, _, _ = candidate()
    e = event("DIVIDEND_ENTITLEMENT", entitlement_id="private-div", net_per_share=1.0)
    state = apply(state, e)
    duplicate, receipt = apply_event(state, e)
    assert duplicate == state and receipt["status"] == "DUPLICATE"
    with pytest.raises(PortfolioInputError, match="Conflicting event"):
        apply(state, {**e, "net_per_share": 2.0})
    before = copy.deepcopy(state)
    with pytest.raises(PortfolioInputError):
        apply_events(state, [event("MARK", 2, at="2026-09-08T14:02:00+00:00", price=102.0, regular=True),
                             event("MARK", 3, at="2026-09-08T14:03:00+00:00", price=float("nan"), regular=True)])
    assert state == before


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), "100"])
def test_nonfinite_bool_and_coerced_geometry_rejected(value):
    invalid = geometry()
    invalid["P"] = value
    with pytest.raises(PortfolioInputError):
        candidate(geometry=invalid)


def test_out_of_order_availability_rejected_and_stale_quote_marks_unknown():
    state, _, _ = candidate()
    state = apply(state, quote(at="2026-09-08T14:02:00+00:00", bid_at="2026-09-08T14:01:00+00:00"))
    assert portfolio_summary(state)["nav_usd"] is None
    with pytest.raises(PortfolioInputError, match="monotonic"):
        apply(state, event("MARK", 2, price=100, regular=True))


def test_public_statistics_keep_all_denominators_and_no_private_keys():
    state, _, _ = candidate()
    state, _, _ = candidate(state, key="b", instrument="private-b", arm="CONTROL")
    state = apply(state, event("TRADE", price=110, regular=True))
    stats = export_session_statistics(state, SESSION)
    assert stats["arms"]["ELIGIBLE"]["upper_first"] == 1
    assert stats["arms"]["CONTROL"]["pending"] == 1
    assert stats["portfolio_episode_count"] == 1
    assert stats["data_gate_unknown"] and not stats["finalized"]
    text = json.dumps([stats, portfolio_summary(state)])
    assert "private-" not in text and "instrument_key" not in text and "episode_key" not in text
    empty = export_session_statistics(state, "2026-09-10")
    assert empty["portfolio_episode_count"] == 0 and empty["portfolio_pnl_usd_sum"] == 0


def test_maturity_is_not_missed_when_scheduler_notification_is_late():
    state, _, _ = candidate(maturity_at="2026-09-08T14:01:00+00:00")
    state = apply(state, quote(at="2026-09-08T14:01:01+00:00"))
    assert state["research"]["a"]["category"] == "time_or_event_exit"
    assert state["research"]["a"]["exit_cause"] == "TIME"


def test_time_intent_at_bar_open_precedes_a_later_intrabar_stop():
    state, _, _ = candidate(maturity_at="2026-09-08T14:01:00+00:00")
    state = apply(state, bar(low=95.0))
    assert state["portfolio"]["a"]["status"] == "OPEN"
    assert state["portfolio"]["a"]["intent"]["cause"] == "TIME"


def test_complete_trade_claim_must_match_its_ohlc():
    state, _, _ = candidate()
    with pytest.raises(PortfolioInputError, match="reconcile"):
        apply(state, bar(trades=[{"at": "2026-09-08T14:01:00+00:00", "price": 100.0}]))


def test_earlier_trade_received_after_newer_price_does_not_invent_retroactive_exit():
    state, _, _ = candidate()
    state = apply(state, event("MARK", at="2026-09-08T14:02:00+00:00", price=100.0, regular=True))
    state = apply(state, event("TRADE", 2, at="2026-09-08T14:01:00+00:00",
                              available_at="2026-09-08T14:03:00+00:00", price=90.0, regular=True))
    assert state["portfolio"]["a"]["status"] == "OPEN"
    assert state["research"]["a"]["category"] == "unobservable"
    assert portfolio_summary(state)["nav_usd"] is None


def test_late_split_does_not_adjust_an_already_post_split_price_twice():
    state, _, _ = candidate()
    state = apply(state, event("MARK", at="2026-09-08T14:02:00+00:00", price=50.0, regular=True))
    state = apply(state, event("SPLIT", 2, at="2026-09-08T14:01:00+00:00",
                              available_at="2026-09-08T14:03:00+00:00", factor=2.0))
    assert state["portfolio"]["a"]["mark"] == 50
    assert state["portfolio"]["a"]["accounting_unknown"]


def test_simultaneous_trade_after_quote_is_rejected_instead_of_changing_charged_exit():
    state, _, _ = candidate(maturity_at="2026-09-08T14:01:00+00:00")
    state = apply(state, quote())
    with pytest.raises(PortfolioInputError, match="priority"):
        apply(state, event("TRADE", 2, price=90, regular=True))


def test_events_known_at_an_admission_instant_must_be_processed_first():
    state, _, _ = candidate()
    with pytest.raises(PortfolioInputError, match="precede"):
        apply(state, event("MARK", at=OPEN, price=100, regular=True))


def test_gap_after_demonstrated_terminal_is_ignored_but_prior_gap_is_retained():
    state, _, _ = candidate()
    state = apply(state, event("TRADE", price=110.0, regular=True))
    state = apply(state, event("DATA_GAP", 2, at="2026-09-08T14:02:00+00:00", reason="coverage absent"))
    assert state["research"]["a"]["category"] == "upper_first"
    state = apply(state, event("DATA_GAP", 3, at="2026-09-08T14:00:30+00:00",
                              available_at="2026-09-08T14:03:00+00:00", reason="earlier gap discovered"))
    assert state["research"]["a"]["category"] == "unobservable"
    assert portfolio_summary(state)["nav_usd"] is None


def test_old_source_event_is_kept_as_old_source_and_not_a_current_session_price():
    state, _, _ = candidate()
    state = apply(state, event("SESSION_CLOSE", at="2026-09-08T20:00:00+00:00"))
    state = apply(state, event("SESSION_OPEN", 2, at="2026-09-09T13:30:00+00:00", session="2026-09-09"))
    state = apply(state, quote(3, at="2026-09-08T19:59:59+00:00",
                              available_at="2026-09-09T13:30:01+00:00", session="2026-09-09"))
    assert state["portfolio"]["a"]["mark"] is None
    assert state["portfolio"]["a"]["mark_session"] == SESSION
    assert state["portfolio"]["a"]["status"] == "OPEN"


def test_overnight_split_and_dividend_keep_gap_in_same_economic_unit():
    state, _, _ = candidate()
    state = apply(state, event("SESSION_CLOSE", at="2026-09-08T20:00:00+00:00"))
    state = apply(state, event("SESSION_OPEN", 2, at="2026-09-09T13:30:00+00:00", session="2026-09-09"))
    state = apply(state, event("SPLIT", 3, at="2026-09-09T13:30:00+00:00", session="2026-09-09", factor=2.0))
    state = apply(state, event("DIVIDEND_ENTITLEMENT", 4, at="2026-09-09T13:30:00+00:00", session="2026-09-09", entitlement_id="private-div", net_per_share=0.5))
    state = apply(state, event("MARK", 5, at="2026-09-09T13:30:01+00:00", session="2026-09-09", price=49.5, regular=True))
    assert state["gap_loss_usd"] == pytest.approx(0.0, abs=1e-8)
    assert portfolio_summary(state)["cash_identity_passed"]


def test_prior_day_position_exit_blocks_reentry_but_preserves_new_research():
    state, _, _ = candidate()
    state = apply(state, event("SESSION_CLOSE", at="2026-09-08T20:00:00+00:00"))
    state = apply(state, event("SESSION_OPEN", 2, at="2026-09-09T13:30:00+00:00", session="2026-09-09"))
    state = apply(state, event("TRADE", 3, at="2026-09-09T13:30:01+00:00", session="2026-09-09", price=97.0, regular=True))
    state, research, admission = candidate(state, key="b", session="2026-09-09", opened_at="2026-09-09T14:00:00+00:00")
    assert research["q0"] == 1 and len(state["research"]) == 2
    assert admission["reason"] == "NO_SAME_DAY_REENTRY"


@pytest.mark.parametrize("kind", ["TRADE", "MARK", "BAR"])
def test_old_session_price_cannot_become_today_mark_when_newer_than_last_historical_mark(kind):
    state, _, _ = candidate()
    state = apply(state, event("SESSION_CLOSE", at="2026-09-08T20:00:00+00:00"))
    state = apply(state, event("SESSION_OPEN", 2, at="2026-09-09T13:30:00+00:00", session="2026-09-09"))
    values = dict(at="2026-09-08T19:58:00+00:00", available_at="2026-09-09T13:30:01+00:00",
                  session="2026-09-09", regular=True)
    if kind == "BAR":
        delayed = event(kind, 3, **values, end_at="2026-09-08T19:59:00+00:00",
                        open=100.0, high=110.0, low=95.0, close=100.0, coverage_complete=True)
    else:
        delayed = event(kind, 3, **values, price=90.0)
    state = apply(state, delayed)
    assert state["portfolio"]["a"]["mark"] is None
    assert state["portfolio"]["a"]["mark_session"] == SESSION
    assert state["portfolio"]["a"]["status"] == "OPEN"
    assert portfolio_summary(state)["nav_usd"] is None


def test_global_data_failure_blocks_only_wallet_without_faking_nav_or_losing_research():
    state, research, decision = candidate(admission_block_reason="GLOBAL_DATA_UNAVAILABLE")
    assert research["q0"] == 1.0 and research["arm"] == "ELIGIBLE"
    assert len(state["research"]) == 1 and not state["portfolio"]
    assert decision == {"admitted": False, "quantity": 0.0, "reason": "GLOBAL_DATA_UNAVAILABLE"}
    assert portfolio_summary(state)["nav_usd"] == 1_000_000
    same, _, _ = candidate(state, admission_block_reason="GLOBAL_DATA_UNAVAILABLE")
    assert same == state
    with pytest.raises(PortfolioInputError, match="Conflicting candidate"):
        candidate(state)
    with pytest.raises(PortfolioInputError):
        candidate(admission_block_reason="")


def test_gap_at_same_instant_precedes_price_and_remains_a_persistable_diagnostic():
    state, _, _ = candidate()
    state, receipts = apply_events(state, [event("DATA_GAP", reason="sequence missing"),
        event("TRADE", 2, price=110.0, regular=True)])
    assert len(receipts) == 2
    assert state["research"]["a"]["category"] == "unobservable"
    assert state["portfolio"]["a"]["status"] == "OPEN"
    assert portfolio_summary(state)["nav_usd"] is None


def batch_candidate_kwargs(key="a", instrument="private-a", **changes):
    return {"episode_key": key, "instrument_key": instrument, "session": SESSION,
            "opened_at": OPEN, "maturity_at": MATURITY, "geometry": geometry(),
            "arm": "ELIGIBLE", **changes}


def test_interleaved_batch_matches_single_operation_semantics_and_statistics():
    from app.r2d2_v2_portfolio import PortfolioBatch
    initial = new_portfolio()
    stream = [event("DIVIDEND_ENTITLEMENT", entitlement_id="private-div", net_per_share=1),
              event("TRADE", 2, at="2026-09-08T14:02:00+00:00", price=97, regular=True)]
    expected, research, admission = candidate(initial)
    expected = apply(expected, stream[0])
    expected, control, control_admission = candidate(expected, key="b", instrument="private-b", arm="CONTROL",
                                                      opened_at="2026-09-08T14:01:01+00:00")
    expected = apply(expected, stream[1])
    batch = PortfolioBatch(initial)
    assert batch.register(**batch_candidate_kwargs()) == (research, admission)
    assert batch.event(stream[0])["status"] == "APPLIED"
    assert batch.register(**batch_candidate_kwargs("b", "private-b", arm="CONTROL",
        opened_at="2026-09-08T14:01:01+00:00")) == (control, control_admission)
    batch.event(stream[1])
    actual = batch.finish()
    assert actual == expected
    assert portfolio_summary(actual) == portfolio_summary(expected)
    assert export_session_statistics(actual, SESSION) == export_session_statistics(expected, SESSION)
    assert initial == new_portfolio()


def test_batch_performs_one_full_state_copy_and_only_boundary_validation(monkeypatch):
    from app import r2d2_v2_portfolio as module
    initial = new_portfolio()
    calls = {"copy": 0, "state_hash": 0, "cash_validation": 0}
    original_copy, original_digest, original_cash = module._copy, module._digest, module._assert_cash
    def counted_copy(value):
        calls["copy"] += 1
        return original_copy(value)
    def counted_digest(value):
        if isinstance(value, dict) and value.get("schema_version") == module.SCHEMA_VERSION:
            calls["state_hash"] += 1
        return original_digest(value)
    def counted_cash(value):
        calls["cash_validation"] += 1
        return original_cash(value)
    monkeypatch.setattr(module, "_copy", counted_copy)
    monkeypatch.setattr(module, "_digest", counted_digest)
    monkeypatch.setattr(module, "_assert_cash", counted_cash)
    batch = module.PortfolioBatch(initial)
    for n in range(25):
        batch.register(**batch_candidate_kwargs(str(n), f"private-{n}", arm="CONTROL"))
    for n in range(25):
        batch.event(event("MARK", n, instrument=f"private-{n}", price=100, regular=True))
    assert calls == {"copy": 1, "state_hash": 1, "cash_validation": 1}
    finished = batch.finish()
    assert len(finished["research"]) == 25
    assert calls == {"copy": 1, "state_hash": 2, "cash_validation": 2}


@pytest.mark.parametrize("failure", ["event", "register", "missing_field"])
def test_failed_batch_cannot_finish_or_resume_and_original_is_unchanged(failure):
    from app.r2d2_v2_portfolio import PortfolioBatch
    original = new_portfolio()
    batch = PortfolioBatch(original)
    batch.register(**batch_candidate_kwargs())
    batch.event(event("MARK", price=102, regular=True))
    with pytest.raises((PortfolioInputError, KeyError)):
        if failure == "event":
            batch.event(event("MARK", 2, at="2026-09-08T14:02:00+00:00", price=float("nan"), regular=True))
        elif failure == "register":
            batch.register(**batch_candidate_kwargs(geometry=geometry(stop=96)))
        else:
            batch.event({"type": "MARK"})
    assert original == new_portfolio()
    with pytest.raises(PortfolioInputError, match="no longer active"):
        batch.finish()
    with pytest.raises(PortfolioInputError, match="no longer active"):
        batch.event(event("MARK", 3, price=100, regular=True))
    with pytest.raises(PortfolioInputError, match="no longer active"):
        batch.register(**batch_candidate_kwargs("c", "private-c"))
    with pytest.raises(PortfolioInputError, match="no longer active"):
        _ = batch.state


def test_finish_validation_failure_also_poisons_batch(monkeypatch):
    from app import r2d2_v2_portfolio as module
    initial = new_portfolio()
    batch = module.PortfolioBatch(initial)
    batch.register(**batch_candidate_kwargs())
    original_apply = module._apply_event_inplace
    def broken_internal(state, value):
        state, receipt = original_apply(state, value)
        state["cash"] += 1.0  # emulate an implementation defect, not an input policy
        return state, receipt
    monkeypatch.setattr(module, "_apply_event_inplace", broken_internal)
    batch.event(event("MARK", price=100, regular=True))
    with pytest.raises(PortfolioInputError, match="identity failed"):
        batch.finish()
    with pytest.raises(PortfolioInputError, match="no longer active"):
        batch.finish()
    assert initial == new_portfolio()


def test_completed_batch_cannot_mutate_transferred_result_and_journal_records_are_detached():
    from app.r2d2_v2_portfolio import PortfolioBatch
    batch = PortfolioBatch(new_portfolio())
    research, admission = batch.register(**batch_candidate_kwargs())
    research["geometry"]["S"] = 1
    admission["quantity"] = 0
    assert batch.state["research"]["a"]["geometry"]["S"] == 97
    with pytest.raises(TypeError):
        batch.state["cash"] = 0
    batch.event(event("TRADE", price=97, regular=True))
    assert research["status"] == "OPEN"
    finished = batch.finish()
    before = copy.deepcopy(finished)
    with pytest.raises(PortfolioInputError):
        batch.finish()
    with pytest.raises(PortfolioInputError):
        batch.event(event("MARK", 2, price=99, regular=True))
    assert finished == before


def test_batch_duplicate_replays_match_wrappers_and_do_not_poison_success():
    from app.r2d2_v2_portfolio import PortfolioBatch
    batch = PortfolioBatch(new_portfolio())
    first = batch.register(**batch_candidate_kwargs())
    assert batch.register(**batch_candidate_kwargs()) == first
    e = event("MARK", price=100, regular=True)
    assert batch.event(e)["status"] == "APPLIED"
    assert batch.event(e)["status"] == "DUPLICATE"
    assert len(batch.finish()["research"]) == 1
