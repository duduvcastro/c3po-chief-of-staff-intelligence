"""Signed EMENDA 5 counterexamples at the durable ledger boundary."""
from datetime import timedelta

import pytest

from app.r2d2_v2_eod import official_close
from app.r2d2_v2_portfolio import SELL_FACTOR, export_session_statistics, portfolio_summary
from tests.test_r2d2_v2_portfolio import apply, candidate, event, geometry, quote, SESSION


def q(n=1, *, seconds=25, price=101., session=SESSION, **kw):
    at = (official_close(session) - timedelta(seconds=seconds)).isoformat()
    return quote(n, at=at, session=session, bid=price, ask=price,
                 source_id="signed-regular-feed", **kw)


def rows(state):
    return [*state["research"].values(), *state["portfolio"].values()]


def close(state, n=99, session=SESSION):
    return apply(state, event("SESSION_CLOSE", n, session=session,
                             at=official_close(session).isoformat()))


@pytest.mark.parametrize("arm", ["ELIGIBLE", "CONTROL"])
@pytest.mark.parametrize("initial_price", [99., geometry()["C"] / SELL_FACTOR])
def test_first_nonpositive_then_positive_exits_first_positive_once_in_every_arm(arm, initial_price):
    state, _, _ = candidate(arm=arm)
    state = apply(state, q(price=initial_price))
    assert all(r["status"] == "OPEN" for r in rows(state))
    positive = q(2, seconds=15)
    state = apply(state, positive)
    before = state["cash"]
    state = apply(state, positive)  # persisted event idempotency after restart
    state = apply(state, q(3, seconds=10, price=103))
    for row in rows(state):
        assert row["exit_cause"] == "EOD_POSITIVE"
        assert row["exit_price"] == 101
        assert row["exit_proceeds"] == pytest.approx(row["quantity"] * 101 * SELL_FACTOR)
        window = row["eod_windows"][SESSION]
        assert window["valid_quotes"] == 2
        assert window["observed_at"] == positive["available_at"] == row["intent"]["at"]
        assert window["pnl"] == pytest.approx(row["exit_proceeds"] - row["entry_cost"])
        assert len(window["observations"]) == 2
    assert state["cash"] == before
    assert portfolio_summary(state)["cash_identity_passed"]
    for row in state["research"].values():
        frozen = row["p5_no_eod"]
        assert frozen["seed"]["status"] == "OPEN"
        assert frozen["seed"]["q0"] == 1
        assert frozen["eod_at"] == positive["available_at"]
        assert "p5_no_eod" not in frozen["seed"]
    assert all("p5_no_eod" not in row for row in state["portfolio"].values())
    stats = export_session_statistics(state, SESSION)["arms"][arm]
    assert stats["eod_positive_exit"] == 1
    assert stats["upper_first"] == stats["lower_first"] == 0


@pytest.mark.parametrize("bad", [dict(bid=102., ask=100.), dict(bid=0.),
    dict(bid_at="2026-09-08T20:00:00+00:00"), dict(regular=False),
    dict(bid_at="2026-09-08T19:59:00+00:00"), dict(source_id="")])
@pytest.mark.parametrize("arm", ["ELIGIBLE", "CONTROL"])
def test_invalid_quote_does_not_erase_later_positive(arm, bad):
    state, _, _ = candidate(arm=arm)
    invalid = {**q(), **bad}
    state = apply(state, invalid)
    state = apply(state, q(2, seconds=15))
    for row in rows(state):
        assert row["exit_cause"] == "EOD_POSITIVE"
        assert row["eod_windows"][SESSION]["invalid_quotes"] == 1


@pytest.mark.parametrize("negative", [True, False])
@pytest.mark.parametrize("arm", ["ELIGIBLE", "CONTROL"])
def test_nonpositive_and_absent_windows_finalize_once_without_exit_or_gate_reclassification(arm, negative):
    state, _, _ = candidate(arm=arm)
    if negative:
        state = apply(state, q(price=99))
    state = close(state)
    state = close(state, n=100)
    reason = "EOD_NOT_POSITIVE" if negative else "EOD_QUOTE_UNOBSERVABLE"
    for row in rows(state):
        assert row["status"] == "OPEN"
        assert row["category"] is None
        assert row["eod_windows"][SESSION]["outcome"] == reason
        assert list(row["eod_windows"]) == [SESSION]
        assert not row["order_unknown"]


@pytest.mark.parametrize("seconds", [31, 0, -1])
@pytest.mark.parametrize("arm", ["ELIGIBLE", "CONTROL"])
def test_positive_outside_observation_window_never_retroactively_exits(arm, seconds):
    state, _, _ = candidate(arm=arm)
    state = apply(state, q(seconds=seconds))
    assert all(r["status"] == "OPEN" for r in rows(state))


@pytest.mark.parametrize("arm", ["ELIGIBLE", "CONTROL"])
def test_late_collector_receipt_ignores_on_time_source_tick(arm):
    state, _, _ = candidate(arm=arm)
    state = apply(state, q(seconds=1, available_at="2026-09-08T20:00:00+00:00"))
    assert all(r["status"] == "OPEN" for r in rows(state))


@pytest.mark.parametrize("arm", ["ELIGIBLE", "CONTROL"])
def test_short_session_uses_official_thirteen_oclock_close(arm):
    session = "2026-11-27"
    assert official_close(session).isoformat() == "2026-11-27T18:00:00+00:00"
    state, _, _ = candidate(arm=arm, session=session, opened_at="2026-11-27T15:00:00+00:00",
                            maturity_at="2026-12-10T20:55:00+00:00")
    state = apply(state, q(seconds=30, session=session))
    assert all(r["exit_cause"] == "EOD_POSITIVE" for r in rows(state))


@pytest.mark.parametrize("price,cause", [(90, "STOP"), (110, "TARGET")])
@pytest.mark.parametrize("arm", ["ELIGIBLE", "CONTROL"])
def test_same_instant_barrier_precedes_eod_quote(arm, price, cause):
    state, _, _ = candidate(arm=arm)
    item = q(2)
    state = apply(state, event("TRADE", at=item["at"], price=price, regular=True))
    state = apply(state, item)
    assert all(r["exit_cause"] == cause for r in rows(state))


@pytest.mark.parametrize("arm", ["ELIGIBLE", "CONTROL"])
def test_event_same_instant_blocks_eod_and_waits_for_strictly_later_quote(arm):
    state, _, _ = candidate(arm=arm)
    item = q(2)
    # Pending detection is a persisted ledger intention. EVENT's existing
    # strict post-detection quote requirement must survive the new exit rule.
    for row in rows(state):
        row["intent"] = {"cause": "EVENT", "at": item["at"]}
    state = apply(state, item)
    assert all(r["status"] == "OPEN" for r in rows(state))
    state = apply(state, q(3, seconds=24))
    assert all(r["exit_cause"] == "EVENT" for r in rows(state))


@pytest.mark.parametrize("seconds,expected", [(25, "EOD_POSITIVE"), (24, "TIME")])
@pytest.mark.parametrize("arm", ["ELIGIBLE", "CONTROL"])
def test_eod_precedes_only_simultaneous_time_not_earlier_time(arm, seconds, expected):
    state, _, _ = candidate(arm=arm, maturity_at=q()["at"])
    state = apply(state, q(seconds=seconds))
    assert all(r["exit_cause"] == expected for r in rows(state))


@pytest.mark.parametrize("arm", ["ELIGIBLE", "CONTROL"])
def test_split_and_paid_dividend_are_counted_once_in_economic_profit(arm):
    state, _, _ = candidate(arm=arm)
    state = apply(state, event("SPLIT", factor=2))
    state = apply(state, event("DIVIDEND_ENTITLEMENT", 2,
        at="2026-09-08T14:02:00+00:00", entitlement_id="d", net_per_share=1))
    state = apply(state, event("DIVIDEND_PAYMENT", 3,
        at="2026-09-08T14:03:00+00:00", entitlement_id="d"))
    state = apply(state, q(4, price=50))
    for row in rows(state):
        assert row["exit_cause"] == "EOD_POSITIVE"
        expected = row["quantity"] * 50 * SELL_FACTOR - row["entry_cost"] + row["dividend_cash"]
        assert row["eod_windows"][SESSION]["pnl"] == pytest.approx(expected)
    assert portfolio_summary(state)["cash_identity_passed"]


@pytest.mark.parametrize("arm", ["ELIGIBLE", "CONTROL"])
def test_unidentified_accounting_cannot_manufacture_positive_exit(arm):
    state, _, _ = candidate(arm=arm)
    state = apply(state, event("DIVIDEND_ENTITLEMENT", entitlement_id="unknown", net_per_share=None))
    state = apply(state, q(2, price=101))
    state = close(state)
    assert all(r["status"] == "OPEN" and r["eod_windows"][SESSION]["outcome"] ==
               "EOD_ACCOUNTING_UNAVAILABLE" for r in rows(state))
