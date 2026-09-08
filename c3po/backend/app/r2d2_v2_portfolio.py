"""Pure, private V2 shadow ledger (signed spec revision 2, annex A and addendum E).

No clock, calendar discovery, database, provider, orders, or V1 imports. The caller
supplies the official session and maturity, archives source evidence and persists
returned state atomically. Inputs are causal, JSON-ready dictionaries. Irrecoverable ordering gaps remain
quarantined; correcting historical evidence requires a separately reviewed replay
from the immutable journal, not clearing a flag on a newer quote. None means
not identified; it is never silently replaced by zero.

Event envelope: event_id, type, at, available_at, session (processing session;
at remains the original source/effective timestamp), instrument_key (except
session events), plus the type's fields. BAR uses end_at, open/high/low/close,
regular, coverage_complete and optional complete trades [{at, price}]. QUOTE
uses bid/ask, bid_at/ask_at, regular. TRADE/MARK uses price, regular. SPLIT uses
factor; entitlement/payment uses entitlement_id and net_per_share for entitlement.
EARNINGS uses E3 granular facts and an immutable observation-round receipt.
EARNINGS_OBSERVATION_FAILED records an explicit failed round. MATURITY, DATA_GAP, SESSION_OPEN and SESSION_CLOSE use
only the envelope (DATA_GAP also requires reason). Values/timestamps are private.

Submit known events before candidate admissions. DATA_GAP is an observability
precondition, processed before prices; it is not an additional exit cause. At equal availability, submit
trades/bars before quotes, and events before admissions. Delayed interval evidence
that overlaps a prior terminal decision is flagged, never used to rewrite cash.
The durable caller must bound/rotate the private event journal with a preserved
idempotency index; this module does not assume an unlimited in-memory history.
All price executions here are hypothetical. A demonstrated price is not a real
order fill. Event IDs are idempotent only when their complete payload matches.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_FLOOR
import hashlib
import json
import math
from typing import Any, Iterable, Mapping
from types import MappingProxyType
from zoneinfo import ZoneInfo

from .r2d2_v2_earnings_policy import event_intersects, EarningsPolicyError
from .r2d2_v2_earnings_events import validate_observation, window_covers

SCHEMA_VERSION = "R2D2_V2_PORTFOLIO_v2"
SELL_FACTOR = (1.0 - 0.0010) * (1.0 - 0.0004)
NEW_YORK = ZoneInfo("America/New_York")
GEOMETRY_FIELDS = ("P", "B", "C", "S", "T", "R_unit")
EVENT_TYPES = frozenset({"BAR", "TRADE", "QUOTE", "MARK", "EARNINGS", "EARNINGS_OBSERVATION_FAILED", "SPLIT",
    "DIVIDEND_ENTITLEMENT", "DIVIDEND_PAYMENT", "MATURITY", "DATA_GAP",
    "SESSION_OPEN", "SESSION_CLOSE"})


class PortfolioInputError(ValueError):
    """Invalid or causally incompatible input; the supplied state is unchanged."""


def _number(value: Any, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PortfolioInputError("A finite native number is required")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        raise PortfolioInputError("Invalid numerical domain")
    return result


def _time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise PortfolioInputError("An aware ISO timestamp is required")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PortfolioInputError("Invalid timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise PortfolioInputError("Naive timestamp")
    return result.astimezone(timezone.utc)


def _iso(value: Any) -> str:
    return _time(value).isoformat()


def _session(value: Any) -> str:
    if not isinstance(value, str):
        raise PortfolioInputError("Session must be an ISO date")
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError as exc:
        raise PortfolioInputError("Invalid session date") from exc
    return value


def _key(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PortfolioInputError("A nonempty private key is required")
    return value


def _digest(value: Any) -> str:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise PortfolioInputError("Input must be finite JSON data") from exc
    return hashlib.sha256(raw.encode()).hexdigest()


def _copy(state: Mapping[str, Any]) -> dict[str, Any]:
    if state.get("schema_version") != SCHEMA_VERSION:
        raise PortfolioInputError("Unknown state schema")
    _digest(state)
    return deepcopy(dict(state))


def _advance(state: dict[str, Any], available_at: str) -> None:
    current = _time(available_at)
    if state["last_available_at"] is not None and current < _time(state["last_available_at"]):
        raise PortfolioInputError("Availability order must be monotonic")
    state["last_available_at"] = current.isoformat()


def _geometry(values: Mapping[str, Any]) -> dict[str, float]:
    if not isinstance(values, Mapping) or set(values) != set(GEOMETRY_FIELDS):
        raise PortfolioInputError("Geometry must contain exactly P/B/C/S/T/R_unit")
    g = {key: _number(values[key], positive=True) for key in GEOMETRY_FIELDS}
    if not 0 < g["S"] < g["P"] < g["T"]:
        raise PortfolioInputError("Invalid barrier ordering")
    expected = {"B": g["P"] * 1.001, "C": g["P"] * 1.001 * 1.0004,
                "R_unit": g["C"] - g["S"] * SELL_FACTOR}
    expected["T"] = (g["C"] + g["R_unit"]) / SELL_FACTOR
    if any(not math.isclose(g[k], v, rel_tol=1e-10, abs_tol=1e-10) for k, v in expected.items()):
        raise PortfolioInputError("Geometry costs or R identity mismatch")
    return g


def new_portfolio(initial_nav: float = 1_000_000.0) -> dict[str, Any]:
    """Create an isolated shadow state; the contract's operational NAV is 1M."""
    initial = _number(initial_nav, positive=True)
    return {"schema_version": SCHEMA_VERSION, "initial_nav": initial, "cash": initial,
            "session": None, "session_start_nav": initial, "previous_close_nav": None,
            "last_available_at": None, "research": {}, "portfolio": {},
            "candidate_hashes": {}, "candidate_results": {}, "processed_events": {},
            "closed_in_session": [], "gap_loss_usd": 0.0, "gap_seen": [],
            "terminal_reasons": [], "event_counts": {}, "last_action": None, "last_event_order": None}


def _record(*, episode_key: str, instrument_key: str, session: str, opened_at: str,
            maturity_at: str, geometry: dict[str, float], arm: str, quantity: float,
            kind: str) -> dict[str, Any]:
    return {"episode_key": episode_key, "instrument_key": instrument_key,
            "session": session, "opened_at": opened_at, "maturity_at": maturity_at,
            "arm": arm, "kind": kind, "original": dict(geometry),
            "geometry": dict(geometry), "q0": quantity, "quantity": quantity,
            "initial_r_usd": quantity * geometry["R_unit"],
            "entry_cost": quantity * geometry["C"], "status": "OPEN",
            "mark": geometry["P"], "mark_at": opened_at, "mark_session": session,
            "receivables": {}, "dividend_cash": 0.0, "exit_proceeds": 0.0,
            "exit_at": None, "exit_available_at": None, "exit_interval": None,
            "exit_cause": None, "exit_price": None, "fill_evidence": None,
            "category": None, "intent": None, "flags": [], "order_unknown": False,
            "accounting_unknown": False, "horizon_breach": False,
            "previous_close_economic": None, "corporate_actions": [], "earnings_observations": {}}


def _receivable(record: Mapping[str, Any]) -> float:
    return sum(x["amount"] for x in record["receivables"].values() if not x["paid"])


def _economic_value(record: Mapping[str, Any]) -> float | None:
    if record["accounting_unknown"] or record["order_unknown"]:
        return None
    if record["status"] == "OPEN" and record["mark"] is None:
        return None
    market = record["quantity"] * record["mark"] if record["status"] == "OPEN" else 0.0
    return market + _receivable(record) + record["dividend_cash"] + record["exit_proceeds"]


def _pnl(record: Mapping[str, Any], *, require_terminal: bool = False) -> float | None:
    if require_terminal and (record["status"] != "CLOSED" or record["horizon_breach"]):
        return None
    value = _economic_value(record)
    return None if value is None else value - record["entry_cost"]


def _totals(state: Mapping[str, Any]) -> tuple[float | None, float | None, float]:
    positions = list(state["portfolio"].values())
    rights = sum(_receivable(r) for r in positions)
    if any(_economic_value(r) is None for r in positions):
        return None, None, rights
    gross = sum(r["quantity"] * r["mark"] for r in positions if r["status"] == "OPEN")
    return state["cash"] + gross + rights, gross, rights



def _sum_known(values: Iterable[float | None]) -> float:
    """Sum after an observability guard, preserving sum's order and empty zero."""
    known: list[float] = []
    for value in values:
        assert value is not None, "The preceding observability guard requires identified P&L"
        known.append(value)
    return sum(known)


def _assert_cash(state: Mapping[str, Any]) -> None:
    expected = state["initial_nav"] + sum(
        -r["entry_cost"] + r["exit_proceeds"] + r["dividend_cash"]
        for r in state["portfolio"].values())
    if abs(expected - state["cash"]) > 0.01:
        raise PortfolioInputError("Cash identity failed by more than one cent")
    nav, _, _ = _totals(state)
    if nav is not None:
        pnl = _sum_known(_pnl(r) for r in state["portfolio"].values())
        if abs(nav - state["initial_nav"] - pnl) > 0.01:
            raise PortfolioInputError("NAV/P&L identity failed by more than one cent")


def _terminal(state: dict[str, Any]) -> None:
    nav, _, _ = _totals(state)
    if nav is not None and nav <= 0.95 * state["initial_nav"]:
        if "V2_CERTIFICATION_FAILED_NAV" not in state["terminal_reasons"]:
            state["terminal_reasons"].append("V2_CERTIFICATION_FAILED_NAV")
    base = state["previous_close_nav"]
    if base is not None and state["gap_loss_usd"] > 0.01 * base:
        if "V2_CERTIFICATION_FAILED_GAP" not in state["terminal_reasons"]:
            state["terminal_reasons"].append("V2_CERTIFICATION_FAILED_GAP")


def _admission(state: Mapping[str, Any], instrument: str, g: dict[str, float], arm: str) -> dict[str, Any]:
    result = {"admitted": False, "reason": None, "quantity": 0.0}
    def reject(reason: str) -> dict[str, Any]:
        return {**result, "reason": reason}
    if arm == "CONTROL":
        return reject("CONTROL_RESEARCH_ONLY")
    if state["terminal_reasons"]:
        return reject("TERMINAL_VETO")
    nav, gross, _ = _totals(state)
    if nav is None or nav <= 0:
        return reject("NAV_UNOBSERVABLE")
    assert gross is not None  # _totals returns NAV/gross as a jointly known pair.
    start = state["session_start_nav"]
    if start is None:
        return reject("DAY_NAV_UNOBSERVABLE")
    if nav <= 0.98 * start:
        return reject("DAILY_LOSS_LIMIT")
    live = [r for r in state["portfolio"].values() if r["status"] == "OPEN"]
    if any(r["instrument_key"] == instrument for r in live):
        return reject("POSITION_ALREADY_OPEN")
    if instrument in state["closed_in_session"]:
        return reject("NO_SAME_DAY_REENTRY")
    if (gross > 0.48 * nav or state["cash"] < 0.05 * nav
            or any(r["quantity"] * r["mark"] > 0.06 * nav for r in live)):
        return reject("MARKED_CAP_EXCESS")
    capacity = min(0.06 * nav, 0.48 * nav - gross, 0.95 * nav - gross,
                   state["cash"] - 0.05 * nav)
    quantity = min(0.0002 * nav / g["R_unit"], capacity / g["C"])
    if quantity <= 0:
        return reject("NO_CAPACITY")
    quantity = float(Decimal(str(quantity)).quantize(Decimal("0.000001"), rounding=ROUND_FLOOR))
    if quantity <= 0:
        return reject("QUANTITY_ROUNDS_TO_ZERO")
    return {"admitted": True, "reason": "ADMITTED", "quantity": quantity}


def _register_candidate_inplace(state: dict[str, Any], *, episode_key: str, instrument_key: str,
                       session: str, opened_at: str, maturity_at: str,
                       geometry: Mapping[str, Any], arm: str,
                       admission_block_reason: str | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Record both research arms; independently size/admit only the eligible arm."""
    ep, instrument = _key(episode_key), _key(instrument_key)
    session = _session(session)
    opened, maturity = _iso(opened_at), _iso(maturity_at)
    if _time(opened).astimezone(NEW_YORK).date().isoformat() != session or _time(maturity) <= _time(opened):
        raise PortfolioInputError("Entry session or official maturity mismatch")
    if arm not in {"ELIGIBLE", "CONTROL"}:
        raise PortfolioInputError("Only prevalidated research arms can be registered")
    g = _geometry(geometry)
    payload = {"episode_key": ep, "instrument_key": instrument, "session": session,
               "opened_at": opened, "maturity_at": maturity, "geometry": g, "arm": arm}
    if admission_block_reason is not None:
        admission_block_reason = _key(admission_block_reason)
    digest = _digest({**payload, "admission_block_reason": admission_block_reason})
    result = state
    if ep in result["candidate_hashes"]:
        if result["candidate_hashes"][ep] != digest:
            raise PortfolioInputError("Conflicting candidate replay")
        return result, deepcopy(result["research"][ep]), deepcopy(result["candidate_results"][ep])
    if any(r["instrument_key"] == instrument and r["session"] == session for r in result["research"].values()):
        raise PortfolioInputError("Only the first complete snapshot per name/session is allowed")
    _advance(result, opened)
    if result["session"] is None:
        result["session"] = session
    elif result["session"] != session:
        raise PortfolioInputError("SESSION_OPEN required before a new session")
    research = _record(**payload, quantity=1.0, kind="RESEARCH")
    decision = (_admission(result, instrument, g, arm) if admission_block_reason is None or arm == "CONTROL"
                else {"admitted": False, "reason": admission_block_reason, "quantity": 0.0})
    result["research"][ep] = research
    if decision["admitted"]:
        position = _record(**payload, quantity=decision["quantity"], kind="PORTFOLIO")
        result["portfolio"][ep] = position
        result["cash"] -= position["entry_cost"]
    result["candidate_hashes"][ep] = digest
    result["candidate_results"][ep] = decision
    result["last_action"] = "CANDIDATE"
    _terminal(result)
    return result, deepcopy(research), deepcopy(decision)


def _flag(record: dict[str, Any], reason: str, *, order: bool = False, accounting: bool = False) -> None:
    if reason not in record["flags"]:
        record["flags"].append(reason)
    record["order_unknown"] |= order
    record["accounting_unknown"] |= accounting
    if order:
        record["category"] = "unobservable"


def _mark(state: dict[str, Any], record: dict[str, Any], price: float, at: str, session: str) -> None:
    if record["status"] != "OPEN":
        return
    if _time(at).astimezone(NEW_YORK).date().isoformat() != session:
        _flag(record, "STALE_MARK_SESSION")
        return
    if record["mark_at"] is not None and _time(at) < _time(record["mark_at"]):
        return  # delayed evidence does not overwrite a newer mark
    record.update(mark=price, mark_at=at, mark_session=session)
    ep = record["episode_key"]
    if (record["kind"] == "PORTFOLIO" and ep not in state["gap_seen"]
            and record["previous_close_economic"] is not None):
        now_value = _economic_value(record)
        if now_value is not None:
            change = now_value - record["previous_close_economic"]
            state["gap_loss_usd"] += -min(change, 0.0)
            state["gap_seen"].append(ep)


def _close(state: dict[str, Any], record: dict[str, Any], *, cause: str, price: float,
           at: str | None, available_at: str, category: str, evidence: str,
           interval: list[str] | None = None) -> None:
    if record["status"] != "OPEN":
        return
    proceeds = record["quantity"] * price * SELL_FACTOR
    record.update(status="CLOSED", exit_cause=cause, exit_price=price, exit_at=at,
                  exit_available_at=available_at, exit_interval=interval,
                  exit_proceeds=proceeds, fill_evidence=evidence,
                  category="unobservable" if record["order_unknown"] or record["horizon_breach"] else category)
    if record["kind"] == "PORTFOLIO":
        state["cash"] += proceeds
        if record["instrument_key"] not in state["closed_in_session"]:
            state["closed_in_session"].append(record["instrument_key"])


def _intent(record: dict[str, Any], cause: str, at: str) -> None:
    if record["status"] != "OPEN":
        return
    current = record["intent"]
    if current is None or _time(at) < _time(current["at"]) or (
            _time(at) == _time(current["at"]) and cause == "EVENT"):
        record["intent"] = {"cause": cause, "at": at}


def _barrier_trade(state: dict[str, Any], record: dict[str, Any], price: float,
                   at: str, available: str, session: str) -> None:
    if record["status"] != "OPEN" or _time(at) < _time(record["opened_at"]):
        return
    if _time(at).astimezone(NEW_YORK).date().isoformat() != session:
        _flag(record, "LATE_TRADE_FROM_PREVIOUS_SESSION", order=True)
        return
    if record["mark_at"] is not None and _time(at) < _time(record["mark_at"]):
        _flag(record, "LATE_TRADE_BEFORE_PRICE_DECISION", order=True)
        return
    _mark(state, record, price, at, session)
    # Earlier exact time/event intent wins; same instant STOP/TARGET has priority.
    if record["intent"] and _time(record["intent"]["at"]) < _time(at):
        return
    if record["order_unknown"]:
        return
    g = record["geometry"]
    if price <= g["S"]:
        _close(state, record, cause="STOP", price=price, at=at, available_at=available,
               category="lower_first", evidence="DEMONSTRATED_TRADE_REFERENCE")
    elif price >= g["T"]:
        _close(state, record, cause="TARGET", price=g["T"], at=at, available_at=available,
               category="upper_first", evidence="DEMONSTRATED_TRADE_REFERENCE" if price == g["T"] else "MODELED_BARRIER_FILL")


def _apply_bar(state: dict[str, Any], record: dict[str, Any], event: Mapping[str, Any]) -> None:
    start, end, available = _iso(event["at"]), _iso(event["end_at"]), _iso(event["available_at"])
    if not _time(start) < _time(end) <= _time(available):
        raise PortfolioInputError("Invalid completed bar interval")
    prices = {key: _number(event[key], positive=True) for key in ("open", "high", "low", "close")}
    if not prices["low"] <= min(prices["open"], prices["close"]) <= max(prices["open"], prices["close"]) <= prices["high"]:
        raise PortfolioInputError("Invalid OHLC ordering")
    if event.get("regular") is not True:
        return
    if record["status"] != "OPEN":
        # Evidence arriving after an exit must not silently revise a past decision.
        terminal = record["exit_at"] or (record["exit_interval"] or [None, None])[1]
        if terminal and _time(end) > _time(record["opened_at"]) and _time(start) < _time(terminal):
            if event.get("coverage_complete") is not True:
                _flag(record, "LATE_COVERAGE_GAP_BEFORE_EXIT", order=True)
            elif _time(terminal) < _time(end):
                _flag(record, "LATE_INTERVAL_OVERLAPS_EXIT", order=True)
        return
    if _time(end) <= _time(record["opened_at"]):
        return
    if _time(start).astimezone(NEW_YORK).date().isoformat() != event["session"]:
        _flag(record, "LATE_BAR_FROM_PREVIOUS_SESSION", order=True)
        return
    if event.get("coverage_complete") is not True:
        _flag(record, "BAR_COVERAGE_GAP", order=True)
        record["mark"] = None
        return
    if record["mark_at"] is not None and _time(end) < _time(record["mark_at"]):
        _flag(record, "LATE_BAR_BEFORE_PRICE_DECISION", order=True)
        return
    trades = event.get("trades")
    if trades is not None:
        if not isinstance(trades, list):
            raise PortfolioInputError("Complete trade evidence must be a list")
        if not trades:
            raise PortfolioInputError("OHLC requires at least one complete trade")
        trade_prices = [_number(t["price"], positive=True) for t in trades]
        expected = {"open": trade_prices[0], "close": trade_prices[-1],
                    "low": min(trade_prices), "high": max(trade_prices)}
        if any(not math.isclose(prices[k], v, rel_tol=1e-10, abs_tol=1e-10) for k, v in expected.items()):
            raise PortfolioInputError("Complete trades do not reconcile to OHLC")
        previous = None
        for trade in trades:
            when, price = _iso(trade["at"]), _number(trade["price"], positive=True)
            if not _time(start) <= _time(when) < _time(end) or (previous and _time(when) < previous):
                raise PortfolioInputError("Trade evidence must be ordered inside its bar")
            previous = _time(when)
            _barrier_trade(state, record, price, when, available, event["session"])
        return
    if _time(start) < _time(record["opened_at"]):
        _flag(record, "PARTIAL_ENTRY_BAR_WITHOUT_TRADES", order=True)
        record["mark"] = None
        return
    g = record["geometry"]
    lower, upper = prices["low"] <= g["S"], prices["high"] >= g["T"]
    intent = record["intent"]
    if intent:
        if (_time(start) < _time(intent["at"]) < _time(end)
                and g["S"] < prices["open"] < g["T"] and (lower or upper)):
            _flag(record, "EVENT_BARRIER_ORDER_UNRESOLVED", order=True)
            if record["kind"] == "RESEARCH":
                # The ambiguous category is reserved for an unresolved S/T pair.
                # A competing TIME/EVENT intent cannot identify even that pair's
                # terminal order; retain the explicit cause and unknown P&L.
                record.update(status="CLOSED", category="unobservable",
                              exit_available_at=available, exit_interval=[start, end],
                              exit_cause="EVENT_BARRIER_ORDER_UNRESOLVED",
                              fill_evidence="UNIDENTIFIED_EXECUTION", accounting_unknown=True)
            return
        if (_time(intent["at"]) < _time(start) or
                (_time(intent["at"]) == _time(start) and g["S"] < prices["open"] < g["T"])):
            _mark(state, record, prices["close"], end, event["session"])
            return
    if record["order_unknown"]:
        _mark(state, record, prices["close"], end, event["session"])
        return
    if prices["open"] <= g["S"]:
        _mark(state, record, prices["open"], start, event["session"])
        _close(state, record, cause="STOP", price=prices["open"], at=start, available_at=available,
               category="lower_first", evidence="DEMONSTRATED_BAR_OPEN_REFERENCE")
    elif prices["open"] >= g["T"]:
        _mark(state, record, prices["open"], start, event["session"])
        _close(state, record, cause="TARGET", price=g["T"], at=start, available_at=available,
               category="upper_first", evidence="DEMONSTRATED_BAR_OPEN_REFERENCE" if prices["open"] == g["T"] else "MODELED_BARRIER_FILL")
    elif lower or upper:
        category = "ambiguous" if lower and upper else "lower_first" if lower else "upper_first"
        if lower and upper and record["kind"] == "RESEARCH":
            _ambiguous_research(record, available, [start, end])
            return
        # Stop-first is authorized only for the portfolio; neither record enters
        # resolved research counts when the order of the two barriers is unknown.
        _close(state, record, cause="STOP" if lower else "TARGET", price=g["S"] if lower else g["T"],
               at=None, available_at=available, category=category, evidence="MODELED_BARRIER_FILL",
               interval=[start, end])
    else:
        _mark(state, record, prices["close"], end, event["session"])


def _apply_quote(state: dict[str, Any], record: dict[str, Any], event: Mapping[str, Any]) -> None:
    if record["status"] != "OPEN" or event.get("regular") is not True:
        return
    bid, ask = _number(event["bid"], positive=True), _number(event["ask"], positive=True)
    if ask < bid:
        raise PortfolioInputError("Crossed quote")
    at, available = _iso(event["at"]), _iso(event["available_at"])
    bid_at, ask_at = _time(event["bid_at"]), _time(event["ask_at"])
    if any(when > _time(at) or not 0 <= (_time(available) - when).total_seconds() <= 10 for when in (bid_at, ask_at)):
        record["mark"] = None
        _flag(record, "QUOTE_STALE_OR_FUTURE")
        return
    if _time(at) < _time(record["opened_at"]):
        return
    price = (bid + ask) / 2
    _mark(state, record, price, at, event["session"])
    intent = record["intent"]
    post_intent = (min(bid_at, ask_at) > _time(intent["at"]) if intent and intent["cause"] == "EVENT"
                   else intent and min(bid_at, ask_at) >= _time(intent["at"]))
    if intent and post_intent:
        _close(state, record, cause=intent["cause"], price=price, at=at, available_at=available,
               category="time_or_event_exit", evidence="DEMONSTRATED_QUOTE_REFERENCE")


def _corporate(state: dict[str, Any], record: dict[str, Any], event: Mapping[str, Any]) -> None:
    kind, at = event["type"], _iso(event["at"])
    if _time(at) < _time(record["opened_at"]):
        return
    if kind == "SPLIT":
        if record["status"] != "OPEN":
            terminal = record["exit_at"] or (record["exit_interval"] or [None])[0]
            if terminal is not None and _time(at) <= _time(terminal):
                _flag(record, "LATE_SPLIT_AFTER_TERMINAL_DECISION", accounting=True, order=True)
            return
        if record["mark_at"] is not None and _time(at) < _time(record["mark_at"]):
            _flag(record, "LATE_SPLIT_AFTER_PRICE_DECISION", accounting=True, order=True)
            return
        factor = _number(event["factor"], positive=True)
        record["quantity"] *= factor
        record["geometry"] = {k: v / factor for k, v in record["geometry"].items()}
        if record["mark"] is not None:
            record["mark"] /= factor
        record["corporate_actions"].append({"type": kind, "at": at, "available_at": _iso(event["available_at"]), "factor": factor})
    elif kind == "DIVIDEND_ENTITLEMENT":
        entitlement = _key(event["entitlement_id"])
        if entitlement in record["receivables"]:
            raise PortfolioInputError("Duplicate entitlement under another event ID")
        closed_before = record["exit_at"] is not None and _time(record["exit_at"]) < _time(at)
        if record["status"] == "CLOSED" and (closed_before or record["exit_at"] is None):
            if record["exit_at"] is None:
                _flag(record, "CORPORATE_TERMINAL_ORDER_UNRESOLVED", accounting=True)
            return
        value = event.get("net_per_share")
        if value is None:
            _flag(record, "DIVIDEND_NET_VALUE_UNOBSERVABLE", accounting=True)
            return
        per_share = _number(value)
        if per_share < 0:
            raise PortfolioInputError("Negative dividend entitlement")
        entitled_quantity = record["q0"]
        for action in record["corporate_actions"]:
            if action["type"] == "SPLIT" and _time(action["at"]) <= _time(at):
                entitled_quantity *= action["factor"]
        record["receivables"][entitlement] = {"amount": per_share * entitled_quantity, "paid": False, "at": at}
    elif kind == "DIVIDEND_PAYMENT":
        entitlement = _key(event["entitlement_id"])
        item = record["receivables"].get(entitlement)
        if item is None:
            return  # instrument payment can concern other episodes' entitlements
        if _time(at) < _time(item["at"]) or item["paid"]:
            raise PortfolioInputError("Invalid or duplicate dividend payment")
        item["paid"] = True
        record["dividend_cash"] += item["amount"]
        if record["kind"] == "PORTFOLIO":
            state["cash"] += item["amount"]


def _session_event(state: dict[str, Any], event: Mapping[str, Any]) -> None:
    session, at = event["session"], _iso(event["at"])
    if event["type"] == "SESSION_OPEN":
        if state["session"] is not None and session <= state["session"]:
            raise PortfolioInputError("SESSION_OPEN must advance the official session")
        state["session"] = session
        state["session_start_nav"] = (state["previous_close_nav"] if state["portfolio"] else state["initial_nav"])
        state["closed_in_session"], state["gap_seen"] = [], []
        state["gap_loss_usd"] = 0.0
        for records in (state["research"], state["portfolio"]):
            for record in records.values():
                if record["status"] == "OPEN":
                    record["mark"] = None
    else:
        if session != state["session"]:
            raise PortfolioInputError("SESSION_CLOSE session mismatch")
        for records in (state["research"], state["portfolio"]):
            for record in records.values():
                if record["status"] == "OPEN":
                    if _time(record["maturity_at"]) <= _time(at):
                        _intent(record, "TIME", record["maturity_at"])
                    if record["intent"] and _time(record["intent"]["at"]) <= _time(at):
                        record["horizon_breach"] = True
                        record["category"] = "unobservable"
                        _flag(record, "HORIZON_BREACH/DATA_UNOBSERVABLE")
                    record["previous_close_economic"] = _economic_value(record)
        state["previous_close_nav"] = _totals(state)[0]


def _apply_event_inplace(state: dict[str, Any], event: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Mutate only the disposable state owned by an active PortfolioBatch."""
    if not isinstance(event, Mapping):
        raise PortfolioInputError("Event must be an object")
    event = dict(event)
    identifier, kind = _key(event["event_id"]), event["type"]
    if kind not in EVENT_TYPES:
        raise PortfolioInputError("Unsupported event type")
    digest = _digest(event)
    result = state
    if identifier in result["processed_events"]:
        if result["processed_events"][identifier] != digest:
            raise PortfolioInputError("Conflicting event replay")
        return result, {"status": "DUPLICATE", "type": kind, "affected_records": 0}
    at, available, session = _iso(event["at"]), _iso(event["available_at"]), _session(event["session"])
    if _time(at) > _time(available):
        raise PortfolioInputError("Event cannot be known before it happens")
    if kind in {"EARNINGS", "EARNINGS_OBSERVATION_FAILED"}:
        try:
            validate_observation(event, detected_at=_time(available))
        except EarningsPolicyError as exc:
            raise PortfolioInputError(str(exc)) from None
    if result["last_action"] == "CANDIDATE" and result["last_available_at"] == available:
        raise PortfolioInputError("Known events must precede simultaneous admissions")
    priority = {"SESSION_OPEN": 0, "SPLIT": 1, "DIVIDEND_ENTITLEMENT": 1,
                "DIVIDEND_PAYMENT": 1, "MATURITY": 2, "EARNINGS": 2,
                "TRADE": 3, "BAR": 3, "MARK": 4, "QUOTE": 4,
                "DATA_GAP": 1, "EARNINGS_OBSERVATION_FAILED": 1, "SESSION_CLOSE": 6}[kind]
    previous_order = result["last_event_order"]
    if (previous_order is not None and previous_order[:2] == [available, at]
            and priority < previous_order[2]):
        raise PortfolioInputError("Simultaneous events violate exit/corporate priority")
    _advance(result, available)
    if kind.startswith("SESSION_"):
        _session_event(result, {**event, "at": at, "session": session})
        affected = 0
    else:
        if result["session"] is None:
            result["session"] = session
        if session != result["session"]:
            raise PortfolioInputError("Event session mismatch; SESSION_OPEN required")
        instrument = _key(event["instrument_key"])
        records = [record for group in (result["research"], result["portfolio"])
                   for record in group.values() if record["instrument_key"] == instrument]
        affected = len(records)
        for record in records:
            if kind in {"BAR", "TRADE", "QUOTE", "MARK"}:
                known_until = _time(event["end_at"]) if kind == "BAR" else _time(at)
                if _time(record["maturity_at"]) <= known_until:
                    _intent(record, "TIME", record["maturity_at"])
            if kind == "BAR":
                _apply_bar(result, record, event)
            elif kind in {"TRADE", "MARK"}:
                price = _number(event["price"], positive=True)
                if event.get("regular") is True:
                    if kind == "TRADE":
                        _barrier_trade(result, record, price, at, available, session)
                    elif _time(at) >= _time(record["opened_at"]):
                        _mark(result, record, price, at, session)
            elif kind == "QUOTE":
                _apply_quote(result, record, event)
            elif kind in {"SPLIT", "DIVIDEND_ENTITLEMENT", "DIVIDEND_PAYMENT"}:
                _corporate(result, record, event)
            elif kind in {"EARNINGS", "EARNINGS_OBSERVATION_FAILED"}:
                # Detection does not replace the original episode horizon or
                # rewrite a terminal episode after a late provider correction.
                if record["status"] != "OPEN" or _time(available) < _time(record["opened_at"]):
                    continue
                failed = kind == "EARNINGS_OBSERVATION_FAILED" or not window_covers(event,
                    opened_at=_time(record["opened_at"]), maturity_at=_time(record["maturity_at"]))
                identity = ("failed:" + event["round_id"] if failed else
                            "event:" + event["earnings_event_id"] + ":" + event["revision_sha256"])
                if identity in record["earnings_observations"]:
                    continue
                if failed:
                    code = "EARNINGS_OBSERVATION_FAILED"
                    _flag(record, code, order=True)
                    record["mark"] = None
                elif event_intersects(event, opened_at=_time(record["opened_at"]),
                                      maturity_at=_time(record["maturity_at"])):
                    code = "EARNINGS_DETECTED_AFTER_ENTRY"
                    _intent(record, "EVENT", available)
                else:
                    continue
                record["earnings_observations"][identity] = {"code": code,
                    "session": _time(available).astimezone(NEW_YORK).date().isoformat(),
                    "processing_session": session,
                    "detected_at": available, "source_detected_at": at, "round_id": event["round_id"]}
            elif kind == "MATURITY":
                if _time(record["maturity_at"]) <= _time(at):
                    _intent(record, "TIME", record["maturity_at"])
            elif kind == "DATA_GAP":
                _key(event["reason"])
                terminal = record["exit_at"] or (record["exit_interval"] or [None, None])[1]
                if (record["status"] == "OPEN" and _time(at) >= _time(record["opened_at"])) or (
                        terminal and _time(record["opened_at"]) <= _time(at) < _time(terminal)):
                    _flag(record, "DATA_GAP", order=True)
                    if record["status"] == "OPEN":
                        record["mark"] = None
    result["processed_events"][identifier] = digest
    result["last_action"] = "EVENT"
    result["last_event_order"] = [available, at, priority]
    result["event_counts"][kind] = result["event_counts"].get(kind, 0) + 1
    _terminal(result)
    return result, {"status": "APPLIED", "type": kind, "affected_records": affected}




class PortfolioBatch:
    """A disposable transaction-local ledger, with one full-state copy.

Each operation validates its own inputs and keeps the signed admission/veto
checks. Full JSON/cash validation occurs at the transaction boundaries, never
for each instrument/tick. An exception permanently poisons the batch; finish is
the only commit boundary. No database commit or I/O occurs in this class.

state is an O(1), top-level read-only borrowed view for causal routing predicates.
Nested values remain internal and must not be mutated or persisted by the caller.
Only the dict returned by finish can be persisted. On success ownership transfers
to the caller and this batch cannot be reused. Journaling returns are detached.
"""
    def __init__(self, initial_state: Mapping[str, Any]):
        self._state = _copy(initial_state)
        _assert_cash(self._state)
        self._status = "ACTIVE"
        self._view = MappingProxyType(self._state)

    def _active(self) -> dict[str, Any]:
        if self._status != "ACTIVE":
            raise PortfolioInputError("Portfolio batch is no longer active")
        assert self._state is not None  # Only ACTIVE owns the transaction state.
        return self._state

    def _poison(self) -> None:
        self._status = "FAILED"
        self._state = None
        self._view = None

    @property
    def state(self) -> Mapping[str, Any]:
        self._active()
        assert self._view is not None  # The ACTIVE state and view share a lifetime.
        return self._view

    def event(self, event: Mapping[str, Any]) -> dict[str, Any]:
        state = self._active()
        try:
            _, receipt = _apply_event_inplace(state, event)
            return receipt
        except BaseException:
            self._poison()
            raise

    def register(self, **kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        state = self._active()
        try:
            _, research, admission = _register_candidate_inplace(state, **kwargs)
            return research, admission
        except BaseException:
            self._poison()
            raise

    def finish(self) -> dict[str, Any]:
        state = self._active()
        try:
            _assert_cash(state)
            _digest(state)  # includes finite JSON validation before transfer
        except BaseException:
            self._poison()
            raise
        result = state
        self._status = "FINISHED"
        self._state = None
        self._view = None
        return result


def register_candidate(state: Mapping[str, Any], *, episode_key: str, instrument_key: str,
                       session: str, opened_at: str, maturity_at: str,
                       geometry: Mapping[str, Any], arm: str,
                       admission_block_reason: str | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Single-operation compatibility wrapper over the transaction-local batch."""
    batch = PortfolioBatch(state)
    research, admission = batch.register(episode_key=episode_key, instrument_key=instrument_key,
        session=session, opened_at=opened_at, maturity_at=maturity_at, geometry=geometry,
        arm=arm, admission_block_reason=admission_block_reason)
    return batch.finish(), research, admission


def apply_events(state: Mapping[str, Any], events: list[Mapping[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Copy once for a complete batch; an exception leaves the input untouched."""
    batch = PortfolioBatch(state)
    receipts = [batch.event(event) for event in events]
    return batch.finish(), receipts


def apply_event(state: Mapping[str, Any], event: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    result, receipts = apply_events(state, [event])
    return result, receipts[0]


def _ambiguous_research(record: dict[str, Any], available: str, interval: list[str]) -> None:
    # Only the portfolio is authorized to turn an ambiguous pair into stop-first
    # economic P&L. Research ambiguity has no invented price/P&L.
    record.update(status="CLOSED", category="ambiguous", exit_available_at=available,
                  exit_interval=interval, exit_cause="AMBIGUOUS_ORDER",
                  fill_evidence="UNIDENTIFIED_EXECUTION", accounting_unknown=True)


def portfolio_summary(state: Mapping[str, Any]) -> dict[str, Any]:
    """Public aggregate projection. No symbols, keys, event payloads or positions."""
    _assert_cash(state)
    nav, gross, rights = _totals(state)
    positions = list(state["portfolio"].values())
    research = list(state["research"].values())
    return {"schema_version": SCHEMA_VERSION, "initial_nav_usd": state["initial_nav"],
            "cash_usd": state["cash"], "nav_usd": nav, "gross_exposure_usd": gross,
            "receivables_usd": rights, "pnl_usd": None if nav is None else nav - state["initial_nav"],
            "research_count": len(research), "portfolio_count": len(positions),
            "open_positions": sum(r["status"] == "OPEN" for r in positions),
            "closed_positions": sum(r["status"] == "CLOSED" for r in positions),
            "unobservable_research": sum(r["category"] == "unobservable" for r in research),
            "indeterminate_portfolio": sum(_pnl(r) is None for r in positions),
            "horizon_breaches": sum(r["horizon_breach"] for r in research),
            "modeled_research_fills": sum(r["fill_evidence"] == "MODELED_BARRIER_FILL" for r in research),
            "gap_loss_usd": state["gap_loss_usd"], "terminal_reasons": list(state["terminal_reasons"]),
            "cash_identity_passed": True, "event_counts": dict(state["event_counts"])}


def export_session_statistics(state: Mapping[str, Any], session_date: str) -> dict[str, Any]:
    """Finalized-entry-session sufficient statistics; no inference/calibration.

Portfolio sum is None if any admitted episode is still open, breached its
horizon, or has unidentified accounting. Its denominator retains all admitted
episodes. Research upper/lower counts never absorb ambiguous or censored cases.
"""
    session = _session(session_date)
    records = [r for r in state["research"].values() if r["session"] == session]
    positions = [r for r in state["portfolio"].values() if r["session"] == session]
    categories = ("upper_first", "lower_first", "ambiguous", "time_or_event_exit", "unobservable")
    arms = {}
    for arm in ("ELIGIBLE", "CONTROL"):
        selected = [r for r in records if r["arm"] == arm]
        arms[arm] = {"episodes": len(selected), **{k: sum(r["category"] == k for r in selected) for k in categories},
                     "pending": sum(r["category"] is None for r in selected)}
    pnl = [_pnl(r, require_terminal=True) for r in positions]
    unidentified = sum(x is None for x in pnl)
    gate = (any(r["category"] == "unobservable" for r in records) or unidentified > 0
            or any(r["category"] is None for r in records))
    return {"schema_version": "R2D2_V2_SESSION_STATISTICS_v1", "session_date": session,
            "arms": arms, "portfolio_pnl_usd_sum": None if unidentified else _sum_known(pnl),
            "portfolio_episode_count": len(positions), "portfolio_pnl_indeterminate_count": unidentified,
            "data_gate_unknown": gate, "terminal_veto": bool(state["terminal_reasons"]),
            "finalized": all(r["status"] == "CLOSED" for r in records + positions),
            "observed_execution_certified": False}


def earnings_observation_counts(state: Mapping[str, Any], session_date: str) -> dict[str, dict[str, int]]:
    """Public counts by factual detection session and arm, never private IDs."""
    session = _session(session_date)
    return earnings_public_sessions(state).get(session, _empty_earnings_session())["counts"]


def _empty_earnings_session() -> dict[str, Any]:
    codes = ("EARNINGS_DETECTED_AFTER_ENTRY", "EARNINGS_OBSERVATION_FAILED")
    return {"counts": {arm: dict.fromkeys(codes, 0) for arm in ("ELIGIBLE", "CONTROL")},
            "exits": {arm: {"closed_episodes": 0, "event_exits": 0,
                "event_exit_fraction": None, "detection_to_exit_seconds_sum": 0.0,
                "mean_detection_to_exit_seconds": None} for arm in ("ELIGIBLE", "CONTROL")}}


def earnings_public_sessions(state: Mapping[str, Any]) -> dict[str, Any]:
    """One aggregate pass for the public view, with no name or event IDs.

Detection counts are episode/revision pairs by detection session. Exit ratios
use episodes closed in each factual exit-receipt session, including all causes.
Neither an empty denominator nor an unseen event is assigned a fraction.
"""
    result: dict[str, Any] = {}
    for record in state["research"].values():
        for receipt in record["earnings_observations"].values():
            summary = result.setdefault(receipt["session"], _empty_earnings_session())
            summary["counts"][record["arm"]][receipt["code"]] += 1
        if record["status"] != "CLOSED" or record["exit_available_at"] is None:
            continue
        day = _time(record["exit_available_at"]).astimezone(NEW_YORK).date().isoformat()
        exits = result.setdefault(day, _empty_earnings_session())["exits"][record["arm"]]
        exits["closed_episodes"] += 1
        if record["exit_cause"] == "EVENT":
            exits["event_exits"] += 1
            exits["detection_to_exit_seconds_sum"] += (_time(record["exit_available_at"]) - _time(record["intent"]["at"])).total_seconds()
    for summary in result.values():
        for exits in summary["exits"].values():
            if exits["closed_episodes"]:
                exits["event_exit_fraction"] = exits["event_exits"] / exits["closed_episodes"]
            if exits["event_exits"]:
                exits["mean_detection_to_exit_seconds"] = exits["detection_to_exit_seconds_sum"] / exits["event_exits"]
    return result
