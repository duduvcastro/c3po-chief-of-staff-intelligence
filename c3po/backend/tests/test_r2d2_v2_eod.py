from datetime import datetime, timedelta, timezone

import pytest

from app.r2d2_v2_eod import EodQuote, SELL_FACTOR, finish, observe

CLOSE = datetime(2026, 9, 18, 20, tzinfo=timezone.utc)


def quote(price, seconds=20, **overrides):
    at = CLOSE - timedelta(seconds=seconds)
    fields = dict(bid=price, ask=price, bid_at=at, ask_at=at, observed_at=at,
                  source="synthetic-regular-stream", regular=True)
    return EodQuote(**(fields | overrides))


def apply(state, q, **overrides):
    return observe(state, q, **(dict(session_close=CLOSE, quantity=1.,
                                    entry_cost=100., entitlements=0.) | overrides))


@pytest.mark.parametrize("first", [99., 100. / SELL_FACTOR])
def test_first_nonpositive_then_positive_exits_on_later_quote_once(first):
    start = {}
    before = apply(start, quote(first, 29))
    assert before.reason == "EOD_CONTINUE" and start == {}
    after = apply(before.state, quote(101., 5))
    assert after.reason == "EOD_POSITIVE"
    assert after.state['observed_at'] == (CLOSE - timedelta(seconds=5)).isoformat()
    assert after.net_fill == pytest.approx(101. * SELL_FACTOR)
    duplicate = apply(after.state, quote(102., 1))
    assert duplicate.reason == "EOD_ALREADY_FINAL" and duplicate.state == after.state


def test_valid_negative_is_different_from_no_valid_quote_and_finalization_is_once():
    negative = apply({}, quote(99.))
    result = finish(negative.state, observed_at=CLOSE, session_close=CLOSE)
    assert result.reason == "EOD_NOT_POSITIVE"
    absent = finish({}, observed_at=CLOSE, session_close=CLOSE)
    assert absent.reason == "EOD_QUOTE_UNOBSERVABLE"
    assert finish(absent.state, observed_at=CLOSE, session_close=CLOSE).reason == "EOD_ALREADY_FINAL"


@pytest.mark.parametrize("changes", [dict(regular=False), dict(source=""), dict(bid=102.,ask=101.),
    dict(bid=float('nan')), dict(ask=float('inf')), dict(bid=-1.),
    dict(bid_at=CLOSE), dict(ask_at=CLOSE-timedelta(seconds=31))])
def test_invalid_quotes_do_not_end_window(changes):
    bad = apply({}, quote(101., 20, **changes))
    assert bad.reason == "EOD_INVALID_QUOTE" and bad.state['invalid_quotes'] == 1
    assert apply(bad.state, quote(101., 5)).reason == "EOD_POSITIVE"


@pytest.mark.parametrize("seconds", [31, 0, -1])
def test_outside_window_or_received_after_close_never_creates_exit(seconds):
    assert apply({}, quote(101., seconds)).reason == "EOD_OUTSIDE_WINDOW"


def test_short_session_and_inclusive_start_boundary():
    close = CLOSE - timedelta(hours=3)
    at = close - timedelta(seconds=30)
    q = quote(101., observed_at=at, bid_at=at, ask_at=at)
    assert apply({}, q, session_close=close).reason == "EOD_POSITIVE"
    assert apply({}, q).reason == "EOD_OUTSIDE_WINDOW"


def test_costs_and_entitlements_are_total_amounts_without_double_friction():
    result = apply({}, quote(100.), quantity=2., entry_cost=202., entitlements=3.)
    assert result.reason == "EOD_POSITIVE"
    assert result.pnl == pytest.approx(2 * 100 * SELL_FACTOR - 202 + 3)


def test_unknown_accounting_is_not_reported_as_a_loss_or_a_missing_quote():
    result = apply({}, quote(101.), entitlements=float('nan'))
    assert result.reason == "EOD_ACCOUNTING_UNAVAILABLE"
    assert finish(result.state, observed_at=CLOSE, session_close=CLOSE).reason == "EOD_ACCOUNTING_UNAVAILABLE"


def test_regressing_observation_clock_is_rejected():
    result = apply({}, quote(99., 10))
    with pytest.raises(ValueError, match="EOD_OBSERVATION_ORDER"):
        apply(result.state, quote(101., 20))
