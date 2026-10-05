"""Pure EMENDA 5 quote-window evaluation, without provider or trading I/O.

The caller supplies the official regular-session close and reconciled economic
amounts. It must apply STOP/TARGET/EVENT precedence before consuming an exit.
Window state belongs to one episode and session and is persisted by the caller.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Mapping

SELL_FACTOR = (1 - 0.0010) * (1 - 0.0004)
AMENDMENT_SHA = "399db28ba31cc4d0b33aefe7fa025e15cd2d8164596c36fc5ab6a4a070729e30"


@lru_cache(maxsize=2048)
def official_close(session: str) -> datetime:
    """Pinned XNYS calendar data, also used for NASDAQ by the V2 contract.

    This resolves holidays/early closes locally; it does not contact a provider.
    Invalid/non-session dates fail closed instead of assuming 16:00 New York.
    """
    import exchange_calendars

    if date.fromisoformat(session).isoformat() != session:
        raise ValueError("EOD_SESSION_INVALID")
    calendar = exchange_calendars.get_calendar("XNYS")
    if not calendar.is_session(session):
        raise ValueError("EOD_NOT_A_SESSION")
    return calendar.session_close(session).to_pydatetime().astimezone(timezone.utc)


def _aware(value: datetime) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _finite(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


@dataclass(frozen=True)
class EodQuote:
    bid: float
    ask: float
    bid_at: datetime
    ask_at: datetime
    observed_at: datetime
    source: str
    regular: bool


@dataclass(frozen=True)
class EodDecision:
    state: dict[str, Any]
    reason: str
    midpoint: float | None = None
    net_fill: float | None = None
    pnl: float | None = None


def observe(state: Mapping[str, Any], quote: EodQuote, *, session_close: datetime,
            quantity: float, entry_cost: float, entitlements: float) -> EodDecision:
    """Evaluate each causal valid quote; nonpositive quotes keep the window open.

entry_cost is the episode's total cost (including entry friction); entitlements
is its reconciled unpaid receivables plus already-paid dividend cash. Neither
is inferred from prices. Invalid economic inputs cannot create an exit.
"""
    if not _aware(session_close) or not _aware(quote.observed_at):
        raise ValueError("EOD_CLOCK_INVALID")
    result = dict(state)
    if result.get("outcome") is not None:
        return EodDecision(result, "EOD_ALREADY_FINAL")
    if not session_close - timedelta(seconds=30) <= quote.observed_at < session_close:
        return EodDecision(result, "EOD_OUTSIDE_WINDOW")
    previous = result.get("last_observed_at")
    if previous and quote.observed_at < datetime.fromisoformat(previous):
        raise ValueError("EOD_OBSERVATION_ORDER")
    result["last_observed_at"] = quote.observed_at.isoformat()
    valid = (quote.regular is True and isinstance(quote.source, str) and bool(quote.source.strip())
             and _finite(quote.bid) and _finite(quote.ask) and 0 < quote.bid <= quote.ask
             and all(_aware(at) and 0 <= (quote.observed_at - at).total_seconds() <= 10
                     for at in (quote.bid_at, quote.ask_at)))
    if not valid:
        result["invalid_quotes"] = result.get("invalid_quotes", 0) + 1
        return EodDecision(result, "EOD_INVALID_QUOTE")
    result["valid_quotes"] = result.get("valid_quotes", 0) + 1
    if not all(_finite(v) for v in (quantity, entry_cost, entitlements)) or quantity <= 0 or entry_cost <= 0:
        result["economic_unknown"] = True
        return EodDecision(result, "EOD_ACCOUNTING_UNAVAILABLE")
    midpoint = (quote.bid + quote.ask) / 2
    net_fill = midpoint * SELL_FACTOR
    pnl = quantity * net_fill - entry_cost + entitlements
    if not all(math.isfinite(v) for v in (midpoint, net_fill, pnl)):
        result["economic_unknown"] = True
        return EodDecision(result, "EOD_ACCOUNTING_UNAVAILABLE")
    if pnl <= 0:
        return EodDecision(result, "EOD_CONTINUE", midpoint, net_fill, pnl)
    result.update(outcome="EOD_POSITIVE", source=quote.source,
                  source_at=min(quote.bid_at, quote.ask_at).isoformat(),
                  observed_at=quote.observed_at.isoformat(), midpoint=midpoint,
                  net_fill=net_fill, pnl=pnl)
    return EodDecision(result, "EOD_POSITIVE", midpoint, net_fill, pnl)


def finish(state: Mapping[str, Any], *, observed_at: datetime, session_close: datetime) -> EodDecision:
    """Finalize once at/after the close; do not invent a fill for missing quotes."""
    if not _aware(observed_at) or not _aware(session_close) or observed_at < session_close:
        raise ValueError("EOD_WINDOW_NOT_CLOSED")
    result = dict(state)
    if result.get("outcome") is not None:
        return EodDecision(result, "EOD_ALREADY_FINAL")
    reason = ("EOD_QUOTE_UNOBSERVABLE" if not result.get("valid_quotes") else
              "EOD_ACCOUNTING_UNAVAILABLE" if result.get("economic_unknown") else "EOD_NOT_POSITIVE")
    result["outcome"] = reason
    return EodDecision(result, reason)
