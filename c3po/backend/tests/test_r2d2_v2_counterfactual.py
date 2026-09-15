"""P5 never fetches evidence or turns an unidentified counterfactual into zero."""
from copy import deepcopy

import pytest

from app.r2d2_v2_counterfactual import evaluate, paired_summary
from app.r2d2_v2_portfolio import SELL_FACTOR
from tests.test_r2d2_v2_portfolio import candidate, event, quote, geometry

EOD = "2026-09-08T19:59:40+00:00"
END = "2026-09-09T20:00:00+00:00"


def seed():
    state, _, _ = candidate()
    return state["research"]["a"]


def first_bar(*, complete_trades=True):
    item = event("BAR", at="2026-09-08T13:30:00+00:00",
        available_at="2026-09-08T20:00:00+00:00", end_at="2026-09-08T20:00:00+00:00",
        open=100., high=101., low=100., close=101., coverage_complete=True, regular=True)
    if complete_trades:
        item["trades"] = [{"at": "2026-09-08T13:30:00+00:00", "price": 100.},
                          {"at": "2026-09-08T19:59:55+00:00", "price": 101.}]
    return item


def next_bar(**changes):
    return {**event("BAR", 2, at="2026-09-09T13:30:00+00:00", session="2026-09-09",
        end_at=END, available_at=END, open=110., high=111., low=100., close=102.,
        regular=True, coverage_complete=True), **changes}


def run(events, **kw):
    params = dict(eod_at=EOD, as_of=END, event_clock_from=EOD, event_clock_through=END)
    params.update(kw)
    return evaluate(seed(), events, **params)


def test_defined_barrier_uses_original_geometry_and_friction_without_mutating_seed():
    original = seed()
    before = deepcopy(original)
    result = evaluate(original, [first_bar(), next_bar()], eod_at=EOD, as_of=END,
                      event_clock_from=EOD, event_clock_through=END)
    assert original == before
    assert result["defined"] and result["exit_cause"] == "TARGET"
    assert result["pnl_usd"] == pytest.approx(geometry()["T"] * SELL_FACTOR - geometry()["C"])
    assert result["pnl_r"] == pytest.approx(1)
    assert result["fill_evidence"] == "MODELED_BARRIER_FILL"
    assert len(result["evidence_sha256"]) == 2
    assert not result["official_effect"]


@pytest.mark.parametrize("events", [[next_bar()], [first_bar(complete_trades=False), next_bar()]])
def test_cannot_skip_unresolved_tail_of_eod_session_for_profitable_later_bar(events):
    result = run(events)
    assert result["reason"] == "CF_FIRST_BAR_UNRESOLVED"
    assert result["pnl_usd"] is result["pnl_r"] is None


def test_daily_both_barriers_are_nd_not_stop_first_research_profit():
    result = run([first_bar(), next_bar(open=100, high=110, low=90, close=100)])
    assert result["reason"] == "CF_AMBIGUOUS" and result["pnl_usd"] is None


@pytest.mark.parametrize("coverage", [None, "2026-09-08T20:00:00+00:00"])
def test_missing_detector_coverage_is_not_evidence_of_no_events(coverage):
    result = run([first_bar(), next_bar()], event_clock_through=coverage)
    assert result["reason"] == "CF_EVENT_CLOCK_UNAVAILABLE"
    assert result["pnl_usd"] is None


def test_detector_range_start_must_cover_the_eod_exit():
    result = run([first_bar(), next_bar()], event_clock_from="2026-09-09T13:30:00+00:00")
    assert result["reason"] == "CF_EVENT_CLOCK_UNAVAILABLE"


def test_time_exit_requires_captured_quote_not_daily_closing_price():
    original = seed()
    original["maturity_at"] = "2026-09-09T19:55:00+00:00"
    daily = next_bar(open=101., low=100., high=102., close=101.)
    result = evaluate(original, [first_bar(), daily], eod_at=EOD, as_of=END,
                      event_clock_from=EOD, event_clock_through=END)
    assert result["reason"] == "CF_QUOTE_UNAVAILABLE" and result["pnl_usd"] is None
    captured = quote(3, at="2026-09-09T19:59:55+00:00", available_at=END,
                     session="2026-09-09", bid=101., ask=101.)
    observed = evaluate(original, [first_bar(), daily, captured], eod_at=EOD, as_of=END,
                        event_clock_from=EOD, event_clock_through=END)
    assert observed["defined"] and observed["exit_cause"] == "TIME"
    assert observed["pnl_usd"] == pytest.approx(101 * SELL_FACTOR - geometry()["C"])


def test_event_quote_alone_does_not_prove_no_prior_stop_in_missing_interval():
    original = seed()
    original["intent"] = {"cause": "EVENT", "at": EOD}
    result = evaluate(original, [quote(3, at="2026-09-08T19:59:50+00:00", bid=101, ask=101)],
                      eod_at=EOD, as_of=END, event_clock_from=EOD, event_clock_through=END)
    assert result["reason"] == "CF_FIRST_BAR_UNRESOLVED"


def test_evidence_after_reading_cannot_complete_a_counterfactual_retroactively():
    result = run([first_bar(), next_bar()], as_of="2026-09-08T20:00:00+00:00")
    assert not result["defined"]
    assert len(result["evidence_sha256"]) == 1


def test_duplicate_evidence_preserved_once_and_conflicting_replay_rejected():
    one = first_bar()
    result = run([one, deepcopy(one), next_bar()])
    assert result["defined"] and len(result["evidence_sha256"]) == 2
    changed = {**one, "close": 100.5}
    with pytest.raises(ValueError, match="CF_CONFLICTING_EVENT_REPLAY"):
        run([one, changed, next_bar()])


def test_pairs_keep_all_denominators_and_publish_only_conditional_difference():
    yes = run([first_bar(), next_bar()])
    missing = run([next_bar()])
    rows = [{"arm": "ELIGIBLE", "official_pnl_usd": 1., "official_pnl_r": .3, "counterfactual": yes},
            {"arm": "ELIGIBLE", "official_pnl_usd": 2., "counterfactual": missing},
            {"arm": "CONTROL", "official_pnl_usd": None, "counterfactual": yes}]
    summary = paired_summary(rows)
    arm = summary["arms"]["ELIGIBLE"]
    assert arm["subjected_episodes"] == 2 and arm["paired_episodes"] == 1
    assert arm["paired_coverage"] == .5 and arm["nd_counts"]["CF_FIRST_BAR_UNRESOLVED"] == 1
    assert arm["difference_pnl_usd_sum"] == pytest.approx(1 - yes["pnl_usd"])
    assert arm["difference_pnl_usd_sum"] < 0  # never relabel the comparison as benefit
    assert arm["paired_episodes_r"] == 1 and arm["difference_pnl_r_sum"] == pytest.approx(-.7)
    control = summary["arms"]["CONTROL"]
    assert control["counterfactual_defined"] == 1 and control["paired_episodes"] == 0
    assert control["difference_pnl_usd_sum"] is None
    assert summary["p_values"] is None and summary["official_effect"] is False


def test_empty_comparison_has_unknown_coverage_not_zero_benefit():
    empty = paired_summary([])["arms"]["ELIGIBLE"]
    assert empty["paired_coverage"] is None and empty["difference_pnl_usd_mean"] is None
