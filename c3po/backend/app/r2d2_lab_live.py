"""The R2D2 operating live in paper from the lab (owner, 26/10/2026): its virtual fills on the R2D2 screen.

The private lab (duduvcastro/c3po-r2d2-lab, lab/live.py) replays the US session every minute on real-time data and,
after each minute, posts the WHOLE day's virtual fills here (``POST /api/v1/r2d2/lab-live``): an idempotent replace of
that day's list, never an increment. The request is authenticated by the shared secret ``C3PO_R2D2_LAB_TOKEN`` (one
value in the host .env and in the lab's secrets; never logged, never echoed). No order, no broker: the fills are the
lab's virtual book, shown in the Daily Buy / Sell Log next to (never mixed into) the paused R2D2 V2 portfolio.
"""
from __future__ import annotations

import hmac
import json
import math
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from .schemas import (R2D2CycleStatus, R2D2DashboardResponse, R2D2EpisodeStats, R2D2LearningCurvePoint,
                      R2D2LivePositionsResponse, R2D2NavSessionDelta, R2D2Position, R2D2SummaryStats, R2D2TrackPoint,
                      R2D2Trade)

TOKEN_ENV = "C3PO_R2D2_LAB_TOKEN"
SCHEMA = "C3PO-R2D2-LAB-LIVE-v1"
ANALYSIS_TYPE = "r2d2_lab_live"
METHODOLOGY_KEY = "r2d2_lab_live"
MAX_TRADES = 400
MAX_BODY_BYTES = 256 * 1024
# Plausibility bounds of one paper fill (Codex P2, #429 6424142588): every stored number, and every number derived
# from it on the screen (gross = price × quantity), stays finite; nothing out of bounds is coerced, it is refused.
MAX_PRICE = 1e6
MAX_QUANTITY = 1e9
MAX_GROSS_USD = 1e10
MAX_ABS_USD = 1e9
MAX_ABS_PERCENT = 1e4
MARKETS = ("NASDAQ", "NYSE")
SYMBOL = re.compile(r"[A-Z][A-Z0-9.\-]{0,9}")
TRADE_ID = re.compile(r"[A-Za-z0-9:._\-]{1,80}")
CONFIG = re.compile(r"[A-Za-z0-9._\-]{1,24}")
NEW_YORK = ZoneInfo("America/New_York")
MAX_POSITIONS = 100
MAX_NAV_USD = 1e10
MIN_NAV_USD = 1.0  # Codex P2 (#429 6427358471): every NAV is a denominator on the panels; a tiny one is refused
BOOK_KEYS = {"nav_start_usd", "nav_usd", "realized_nav_usd", "cash_usd", "as_of", "positions"}
POSITION_KEYS = {"symbol", "market", "quantity", "average_cost", "last_price", "cost_usd", "unrealized_pnl_usd",
                 "unrealized_return_percent", "stop_price", "opened_at"}
BOOK_SOURCE = "lab_live"
CYCLE_KEYS = {"candidates", "signals", "entries", "closed"}
# The live scenarios as the owner chose them (lab/sim.py CFGS); the Launch Gates panel shows the one in force
LIVE_RULES = {
    "TIT-2S3": "Gap ≤ −1% at the open · back above the VWAP until 15:29 ET · ADV ≥ US$15M · price ≥ US$5 · spread ≤ 3 bps",
    "TIT-2S5": "Gap ≤ −1% at the open · back above the VWAP until 15:29 ET · ADV ≥ US$15M · price ≥ US$5 · spread ≤ 5 bps",
    "TIT-2": "Gap ≤ −1% at the open · back above the VWAP until 15:29 ET · ADV ≥ US$15M · price ≥ US$5 · no spread limit",
    "TIT-1": "Gap ≤ −1% at the open · first VWAP cross until 11:29 ET · ADV ≥ US$15M · price ≥ US$5 · spread ≤ 3 bps",
}
LIVE_SLOTS = {"TIT-2S3": 20, "TIT-2S5": 20, "TIT-2": 20, "TIT-1": 1}
SESSION_CLOSE_ET = (16, 5)  # a session counts in the day scoreboard once the US close has passed
# The one R2D2 book opened on 27/10/2026 from the NAV with interest at the 26/10 close (owner 26/10/2026): the T-bill
# interest the cash-yield ledger posts for sessions from this one on is money of the book (cash and NAV).
BOOK_FIRST_SESSION = "2026-10-27"
TRADE_KEYS = {"id", "side", "symbol", "market", "quantity", "price", "executed_at", "fees_usd", "realized_pnl_usd",
              "realized_return_percent", "reason"}


class LabLiveRefused(ValueError):
    """A payload this endpoint does not store; the message names the field, never echoes a value."""


def authorized(header: str | None, environ: Mapping[str, str] | None = None) -> bool:
    """``Authorization: Bearer <token>`` against the configured token, in constant time. No token configured: refused."""
    expected = (os.environ if environ is None else environ).get(TOKEN_ENV, "").strip()
    if len(expected) < 32 or not header or not header.startswith("Bearer "):
        return False
    return hmac.compare_digest(header[len("Bearer "):].strip().encode(), expected.encode())


def parse(body: bytes) -> Any:
    """The request body as JSON; anything else is refused without echoing it."""
    def no_constant(_: str) -> Any:
        raise ValueError("NaN or Infinity")

    try:
        return json.loads(body.decode("utf-8"), parse_constant=no_constant)
    except (UnicodeDecodeError, ValueError):
        raise LabLiveRefused("the body is not JSON") from None


def _optional(value: Any, name: str, *, bound: float) -> float | None:
    return None if value is None else _number(value, name, bound=bound)


def _number(value: Any, name: str, *, bound: float, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LabLiveRefused(f"{name} is not a number")
    try:
        number = float(value)
    except (OverflowError, ValueError):
        raise LabLiveRefused(f"{name} is not a finite number") from None
    if not math.isfinite(number) or abs(number) > bound:
        raise LabLiveRefused(f"{name} is out of bounds")
    if positive and number <= 0:
        raise LabLiveRefused(f"{name} is not positive")
    return number


def _instant(value: Any, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        raise LabLiveRefused(f"{name} is not an ISO-8601 instant") from None
    if parsed.tzinfo is None:
        raise LabLiveRefused(f"{name} has no zone")
    return parsed.astimezone(timezone.utc)


def validate(payload: Any, *, now: datetime | None = None) -> dict[str, Any]:
    """The payload as stored: the exact schema, closed vocabularies, every fill on the posted session day."""
    if not isinstance(payload, dict) or not {"schema", "day", "config", "trades"} <= set(payload) <= {
            "schema", "day", "config", "trades", "book", "cycle"}:
        raise LabLiveRefused("the payload keys are not schema, day, config, trades and an optional book and cycle")
    if payload["schema"] != SCHEMA:
        raise LabLiveRefused("unexpected schema")
    try:
        day = date.fromisoformat(str(payload["day"]))
    except ValueError:
        raise LabLiveRefused("day is not YYYY-MM-DD") from None
    clock = now or datetime.now(timezone.utc)
    if abs((day - clock.astimezone(NEW_YORK).date()).days) > 3:
        raise LabLiveRefused("day is not a recent session")
    if not isinstance(payload["config"], str) or CONFIG.fullmatch(payload["config"]) is None:
        raise LabLiveRefused("config is not a scenario name")
    trades = payload["trades"]
    if not isinstance(trades, list) or len(trades) > MAX_TRADES:
        raise LabLiveRefused("trades is not a list of at most %d fills" % MAX_TRADES)
    seen: set[str] = set()
    out = []
    for trade in trades:
        if not isinstance(trade, dict) or set(trade) != TRADE_KEYS:
            raise LabLiveRefused("a fill's keys are not exactly the expected ones")
        if not isinstance(trade["id"], str) or TRADE_ID.fullmatch(trade["id"]) is None or trade["id"] in seen:
            raise LabLiveRefused("a fill id is invalid or repeated")
        seen.add(trade["id"])
        if trade["side"] not in ("BUY", "SELL"):
            raise LabLiveRefused("side is not BUY or SELL")
        if not isinstance(trade["symbol"], str) or SYMBOL.fullmatch(trade["symbol"]) is None:
            raise LabLiveRefused("symbol is not a ticker")
        if trade["market"] not in MARKETS:
            raise LabLiveRefused("market is not NASDAQ or NYSE")
        executed = _instant(trade["executed_at"], "executed_at")
        if executed.astimezone(NEW_YORK).date() != day:
            raise LabLiveRefused("a fill is not on the posted session day")
        if not isinstance(trade["reason"], str) or not 0 < len(trade["reason"]) <= 200:
            raise LabLiveRefused("reason is not a short text")
        pnl = _optional(trade["realized_pnl_usd"], "realized_pnl_usd", bound=MAX_ABS_USD)
        ret = _optional(trade["realized_return_percent"], "realized_return_percent", bound=MAX_ABS_PERCENT)
        if trade["side"] == "BUY" and (pnl is not None or ret is not None):
            raise LabLiveRefused("a BUY carries no realized result")
        quantity = _number(trade["quantity"], "quantity", bound=MAX_QUANTITY, positive=True)
        price = _number(trade["price"], "price", bound=MAX_PRICE, positive=True)
        if not quantity * price <= MAX_GROSS_USD:
            raise LabLiveRefused("price × quantity is out of bounds")
        out.append({"id": trade["id"], "side": trade["side"], "symbol": trade["symbol"], "market": trade["market"],
                    "quantity": quantity, "price": price, "executed_at": executed.isoformat(),
                    "fees_usd": abs(_number(trade["fees_usd"], "fees_usd", bound=MAX_ABS_USD)), "realized_pnl_usd": pnl,
                    "realized_return_percent": ret, "reason": trade["reason"]})
    document = {"schema": SCHEMA, "day": day.isoformat(), "config": payload["config"], "trades": out}
    if "book" in payload:
        document["book"] = _book(payload["book"])
    if "cycle" in payload:
        cycle = payload["cycle"]
        if not isinstance(cycle, dict) or set(cycle) != CYCLE_KEYS or not all(
                isinstance(cycle[key], int) and not isinstance(cycle[key], bool) and 0 <= cycle[key] <= 1_000_000
                for key in CYCLE_KEYS):
            raise LabLiveRefused("the cycle is not exactly candidates, signals, entries, closed counts")
        document["cycle"] = {key: cycle[key] for key in sorted(CYCLE_KEYS)}
    return document


def _book(book: Any) -> dict[str, Any]:
    """The lab's open book: NAV, cash and positions (owner 26/10/2026: one R2D2 book on every panel)."""
    if not isinstance(book, dict) or set(book) != BOOK_KEYS:
        raise LabLiveRefused("the book keys are not exactly the expected ones")
    positions = book["positions"]
    if not isinstance(positions, list) or len(positions) > MAX_POSITIONS:
        raise LabLiveRefused("the book positions are not a list of at most %d" % MAX_POSITIONS)
    out = []
    for item in positions:
        if not isinstance(item, dict) or set(item) != POSITION_KEYS:
            raise LabLiveRefused("a position's keys are not exactly the expected ones")
        if not isinstance(item["symbol"], str) or SYMBOL.fullmatch(item["symbol"]) is None:
            raise LabLiveRefused("a position symbol is not a ticker")
        if item["market"] not in MARKETS:
            raise LabLiveRefused("a position market is not NASDAQ or NYSE")
        quantity = _number(item["quantity"], "quantity", bound=MAX_QUANTITY, positive=True)
        last = _number(item["last_price"], "last_price", bound=MAX_PRICE, positive=True)
        if not quantity * last <= MAX_GROSS_USD:
            raise LabLiveRefused("a position value is out of bounds")
        out.append({"symbol": item["symbol"], "market": item["market"], "quantity": quantity,
                    "average_cost": _number(item["average_cost"], "average_cost", bound=MAX_PRICE, positive=True),
                    "last_price": last, "cost_usd": _number(item["cost_usd"], "cost_usd", bound=MAX_GROSS_USD, positive=True),
                    "unrealized_pnl_usd": _number(item["unrealized_pnl_usd"], "unrealized_pnl_usd", bound=MAX_ABS_USD),
                    "unrealized_return_percent": _number(item["unrealized_return_percent"], "unrealized_return_percent",
                                                         bound=MAX_ABS_PERCENT),
                    "stop_price": _number(item["stop_price"], "stop_price", bound=MAX_PRICE),
                    "opened_at": _instant(item["opened_at"], "opened_at").isoformat()})
    navs = {key: _number(book[key], key, bound=MAX_NAV_USD, positive=True)
            for key in ("nav_start_usd", "nav_usd", "realized_nav_usd")}
    if min(navs.values()) < MIN_NAV_USD:
        raise LabLiveRefused("a book NAV is below the floor")
    derived = [navs["nav_usd"] / navs["nav_start_usd"]] + [item["quantity"] * item["last_price"] / navs["nav_usd"] for item in out]
    if not all(math.isfinite(value) and abs(value) <= MAX_NAV_USD for value in derived):
        raise LabLiveRefused("a book ratio is out of bounds")
    return {**navs, "cash_usd": _number(book["cash_usd"], "cash_usd", bound=MAX_NAV_USD),
            "as_of": _instant(book["as_of"], "as_of").isoformat(), "positions": out}


def store(database: Any, payload: Any, *, now: datetime | None = None) -> dict[str, Any]:
    """Validate and store the day's fills (the latest post of a day wins). Returns the counts, never the fills."""
    document = validate(payload, now=now)
    clock = now or datetime.now(timezone.utc)
    methodology = database.ensure_methodology_version(
        METHODOLOGY_KEY, 1, {"schema": SCHEMA, "source": "duduvcastro/c3po-r2d2-lab lab/live.py"},
        "R2D2 live in paper from the lab: the day's virtual fills, replaced on every post (owner, 26/10/2026)")
    database.save_analysis_snapshot(ANALYSIS_TYPE, document["day"], methodology,
                                    {"schema": SCHEMA, "config": document["config"]}, document, clock)
    return {"day": document["day"], "config": document["config"], "fills": len(document["trades"])}


def today_trades(database: Any, *, now: datetime | None = None) -> list[R2D2Trade]:
    """The fills of today's US session (by New York date), newest first, as R2D2 trades for the dashboard."""
    clock = now or datetime.now(timezone.utc)
    snapshot = database.latest_analysis_snapshot(ANALYSIS_TYPE, clock.astimezone(NEW_YORK).date().isoformat())
    outputs = (snapshot or {}).get("outputs")
    if not isinstance(outputs, dict) or outputs.get("schema") != SCHEMA:
        return []
    trades = []
    for item in outputs.get("trades") or []:
        executed = datetime.fromisoformat(item["executed_at"])
        gross = item["price"] * item["quantity"]
        trades.append(R2D2Trade(
            id="lab:" + item["id"], market=item["market"], symbol=item["symbol"], name=item["symbol"], side=item["side"],
            quantity=item["quantity"], signal_price_local=item["price"], fill_price_local=item["price"], currency="USD",
            gross_value_usd=gross, fees_usd=item["fees_usd"], slippage_usd=0.0, realized_pnl_usd=item["realized_pnl_usd"],
            realized_return_percent=item["realized_return_percent"],
            reason="R2D2 ao vivo (%s, papel): %s" % (outputs.get("config"), item["reason"]),
            executed_at=executed, quote_as_of=executed))
    return sorted(trades, key=lambda trade: trade.executed_at, reverse=True)


def learning_curve(database: Any, *, now: datetime | None = None, days: int = 90) -> list[R2D2LearningCurvePoint]:
    """One point per lab session with closed trades (positive and negative realized sells), oldest first: the live
    R2D2 continues the Learning Curve after the paused V2 book's sessions."""
    today = (now or datetime.now(timezone.utc)).astimezone(NEW_YORK).date()
    keys = [(today - timedelta(days=offset)).isoformat() for offset in range(days)]
    points = []
    for day, snapshot in sorted(database.latest_analysis_snapshots(ANALYSIS_TYPE, keys).items()):
        outputs = snapshot.get("outputs")
        if not isinstance(outputs, dict) or outputs.get("schema") != SCHEMA:
            continue
        results = [item.get("realized_pnl_usd") for item in outputs.get("trades") or [] if item.get("side") == "SELL"]
        positive = sum(1 for pnl in results if pnl is not None and pnl > 0)
        negative = sum(1 for pnl in results if pnl is not None and pnl < 0)
        if positive + negative:
            points.append(R2D2LearningCurvePoint(session_date=day, positive_percent=round(positive / (positive + negative) * 100, 1),
                                                 positive_trades=positive, negative_trades=negative))
    return points


def _lab_snapshots(database: Any, now: datetime | None, days: int) -> list[tuple[str, dict[str, Any]]]:
    today = (now or datetime.now(timezone.utc)).astimezone(NEW_YORK).date()
    # the next session too: the opening book of tomorrow is posted the evening before (lab book_post.yml)
    keys = [(today - timedelta(days=offset)).isoformat() for offset in range(-1, days)]
    found = []
    for day, snapshot in sorted(database.latest_analysis_snapshots(ANALYSIS_TYPE, keys).items()):
        outputs = snapshot.get("outputs")
        if isinstance(outputs, dict) and outputs.get("schema") == SCHEMA:
            found.append((day, outputs))
    return found


def latest_book(database: Any, *, now: datetime | None = None) -> tuple[str, str, dict[str, Any], list[tuple[str, dict[str, Any]]]] | None:
    """The newest lab session that posted a book (day, config, book) and every session with a book, oldest first."""
    sessions = [(day, outputs) for day, outputs in _lab_snapshots(database, now, 90) if isinstance(outputs.get("book"), dict)]
    if not sessions:
        return None
    day, outputs = sessions[-1]
    return day, str(outputs.get("config")), outputs["book"], sessions


def _positions(book: dict[str, Any], now: datetime | None = None, nav: float | None = None) -> list[R2D2Position]:
    """The open positions; ``nav`` is the effective NAV the panels show (the book's NAV plus the interest it earned),
    the denominator of every allocation (Codex #494 finding 3)."""
    effective: float = book["nav_usd"] if nav is None else nav
    as_of = datetime.fromisoformat(book["as_of"])
    age = max(0.0, ((now or datetime.now(timezone.utc)) - as_of).total_seconds())
    freshness = "fresh" if age <= 120 else "aging" if age <= 420 else "stale"  # the lab posts the marks every <= 5 min
    rows = []
    for item in book["positions"]:
        value = item["quantity"] * item["last_price"]
        rows.append(R2D2Position(
            market=item["market"], symbol=item["symbol"], name=item["symbol"], currency="USD", quantity=item["quantity"],
            average_cost_local=item["average_cost"], last_price_local=item["last_price"], market_value_usd=round(value, 2),
            unrealized_pnl_usd=item["unrealized_pnl_usd"], unrealized_return_percent=item["unrealized_return_percent"],
            mark_pnl_usd=item["unrealized_pnl_usd"], mark_return_percent=item["unrealized_return_percent"],
            estimated_exit_pnl_usd=item["unrealized_pnl_usd"], estimated_exit_return_percent=item["unrealized_return_percent"],
            allocation_percent=round(value / effective * 100, 4) if effective > 0 else 0.0, stop_price_local=item["stop_price"],
            data_status="live", decision_state="hold", quote_status="lab", quote_as_of=as_of, quote_age_seconds=round(age, 1),
            quote_freshness=freshness, trend_state="vwap rule", volume_state="adv rule",
            opened_at=datetime.fromisoformat(item["opened_at"]), updated_at=as_of))
    return sorted(rows, key=lambda row: row.market_value_usd, reverse=True)


def _interest(interest: list[tuple[str, float]] | None, today: str) -> tuple[float, float]:
    """(interest of the book since its first session, interest posted for today's session)."""
    rows = interest or []
    return (sum(amount for day, amount in rows if BOOK_FIRST_SESSION <= day <= today),
            sum(amount for day, amount in rows if day == today))


def apply_book(response: R2D2DashboardResponse, database: Any, *, now: datetime | None = None,
               interest: list[tuple[str, float]] | None = None) -> R2D2DashboardResponse:
    """One R2D2 book on every panel (owner 26/10/2026): NAV, cash, positions, daily P&L, the session delta and the
    track record come from the live lab book once it has posted one; the paused V2 book is the history before it."""
    found = latest_book(database, now=now)
    if found is None:
        return response
    day, config, book, sessions = found
    today = (now or datetime.now(timezone.utc)).astimezone(NEW_YORK).date().isoformat()
    clock = (now or datetime.now(timezone.utc)).astimezone(NEW_YORK)
    closed_now = (clock.hour, clock.minute) >= SESSION_CLOSE_ET
    by_day = dict(_lab_snapshots(database, now, 90))
    results = _session_results(by_day, today)
    accrued, interest_today = _interest(interest, today)
    if today in results:
        open_nav, close_nav = results[today]
    else:  # no live session yet today: the latest book, unchanged
        open_nav = close_nav = book["nav_usd"] if day < today else book["nav_start_usd"]
    daily = close_nav - open_nav
    nav = (book["nav_usd"] if day <= today else close_nav) + accrued
    close_nav, open_nav = close_nav + accrued, open_nav + accrued
    previous = open_nav - interest_today  # the NAV at the previous close, before today's T-bill interest
    daily_percent = daily / previous * 100 if previous > 0 else 0.0
    positions = _positions(book, now, nav=book["nav_usd"] + accrued)
    exposure = sum(position.market_value_usd for position in positions)
    starting = response.starting_capital_usd
    total_return = (nav / starting - 1) * 100 if starting > 0 else 0.0
    known = {point.session_date for point in response.track_record}
    track = list(response.track_record)
    for session_day, (session_open, session_close) in sorted(results.items()):
        if session_day in known:
            continue
        session_accrued, session_interest = _interest(interest, session_day)
        session_previous = session_open + session_accrued - session_interest
        track.append(R2D2TrackPoint(
            session_date=session_day, nav_usd=round(session_close + session_accrued, 2),
            daily_pnl_usd=round(session_close - session_open, 2),
            daily_return_percent=round((session_close - session_open) / session_previous * 100, 4) if session_previous > 0 else 0.0,
            is_final=session_day < today or closed_now))
    total = close_nav - previous
    delta = R2D2NavSessionDelta(
        status="available", session_date=today, previous_session_date=None, current_total_nav_usd=round(close_nav, 2),
        previous_total_nav_usd=round(previous, 2), total_delta_usd=round(total, 2),
        total_delta_percent=round(total / previous * 100, 4) if previous > 0 else 0.0, organic_delta_usd=round(daily, 2),
        organic_delta_percent=round(daily_percent, 4), interest_delta_usd=round(interest_today, 2),
        interest_delta_percent=round(interest_today / previous * 100, 4) if previous > 0 else 0.0,
        interest_status="posted" if interest_today else "pending")
    today_doc = by_day.get(today) or {}
    closed_results = _closed_episodes(today_doc.get("trades") or [])
    positive = sum(1 for pnl in closed_results if pnl > 0)
    negative = sum(1 for pnl in closed_results if pnl < 0)
    episodes = R2D2EpisodeStats(
        session_date=today, closed_episodes=len(closed_results), decided_episodes=positive + negative,
        positive_episodes=positive, negative_episodes=negative, flat_episodes=len(closed_results) - positive - negative,
        win_rate_percent=round(positive / (positive + negative) * 100, 2) if positive + negative else 0.0)
    stats = _scoreboard(response.stats, track, by_day, today, closed_now)
    cycle = today_doc.get("cycle")
    last_cycle = response.last_cycle
    if today_doc:
        last_cycle = R2D2CycleStatus(
            status="completed" if closed_now else "running",
            started_at=datetime.fromisoformat(today + "T09:30:00").replace(tzinfo=NEW_YORK),
            scanned_count=(cycle or {}).get("candidates", 0), signal_count=(cycle or {}).get("signals", 0),
            trade_count=len(today_doc.get("trades") or []), metadata={"source": BOOK_SOURCE, "config": str(today_doc.get("config"))})
    return response.model_copy(update={
        "book_source": BOOK_SOURCE, "live_rule": LIVE_RULES.get(config), "live_slots": LIVE_SLOTS.get(config),
        "experiment_code": "R2D2 LIVE · %s" % config, "status": "running",
        "methodology_version": "R2D2 LIVE · %s" % config, "today_episode_stats": episodes, "stats": stats,
        "last_cycle": last_cycle, "entries_paused": False, "nav_usd": round(nav, 2), "accounting_nav_usd": round(nav, 2),
        "accounting_nav_ex_interest_usd": round(nav - response.interest_income_epoch_usd, 2),
        "accounting_total_nav_usd": round(nav, 2),
        "cash_usd": round(book["cash_usd"] + accrued, 2), "gross_exposure_usd": round(exposure, 2), "open_positions": len(positions),
        "positions": positions, "total_return_percent": round(total_return, 4),
        "accounting_total_return_percent": round(total_return, 4), "daily_pnl_usd": round(daily, 2),
        "organic_daily_pnl_usd": round(daily, 2), "daily_return_percent": round(daily_percent, 4), "daily_pnl_date": today,
        "nav_session_delta": delta, "track_record": track})


def _session_results(by_day: dict[str, dict[str, Any]], today: str) -> dict[str, tuple[float, float]]:
    """(opening NAV, closing NAV) of every live session up to today, from the stored documents alone, so the history and
    the scoreboard survive the New York date change without a new write (Codex #494 finding 1). A session with a book:
    its own NAVs. A session without one (fills only, e.g. 26/10/2026): it closed at the opening NAV of the next session
    that posted a book, and opened that much below its realized sells; with no later book it is not shown yet."""
    book_days = sorted(day for day, outputs in by_day.items() if isinstance(outputs.get("book"), dict))
    results: dict[str, tuple[float, float]] = {}
    for day in sorted(day for day in by_day if day <= today):
        outputs = by_day[day]
        book = outputs.get("book")
        if isinstance(book, dict):
            results[day] = (book["nav_start_usd"], book["nav_usd"])
            continue
        trades = outputs.get("trades") or []
        later = [other for other in book_days if other > day]
        if not trades or not later:
            continue
        close = by_day[later[0]]["book"]["nav_start_usd"]
        results[day] = (close - sum(item.get("realized_pnl_usd") or 0.0 for item in trades if item.get("side") == "SELL"), close)
    return results


def _closed_episodes(trades: list[dict[str, Any]]) -> list[float]:
    """The realized result of every position closed in the session, one per episode (Codex #494 finding 2): per symbol,
    in time order, an episode opens with a BUY into a flat book (or with a SELL of a position carried from an earlier
    session) and closes when its quantity returns to zero; partial sells add up inside it."""
    closed: list[float] = []
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for item in trades:
        by_symbol.setdefault(item["symbol"], []).append(item)
    for fills in by_symbol.values():
        quantity, result = 0.0, 0.0
        for item in sorted(fills, key=lambda fill: (fill["executed_at"], fill["side"] != "BUY")):
            if item["side"] == "BUY":
                quantity += item["quantity"]
                continue
            if quantity <= 1e-9:  # a position carried from an earlier session: its buy is not in this document
                quantity = item["quantity"]
            result += item.get("realized_pnl_usd") or 0.0
            quantity -= item["quantity"]
            if quantity <= 1e-6 * max(item["quantity"], 1.0):
                closed.append(result)
                quantity, result = 0.0, 0.0
    return closed


def _scoreboard(v2: R2D2SummaryStats, track: list[R2D2TrackPoint], by_day: dict[str, dict[str, Any]], today: str,
                closed_now: bool) -> R2D2SummaryStats:
    """The paused V2 book's lifetime scoreboard plus the live sessions (days from the track, legs from the sells)."""
    lab_days = [point for point in track if point.session_date in by_day and (point.session_date < today or closed_now)]
    sells = [item.get("realized_pnl_usd") for day, outputs in by_day.items() if day <= today
             for item in outputs.get("trades") or [] if item.get("side") == "SELL"]
    closed = v2.closed_days + len(lab_days)
    positive_days = v2.positive_days + sum(point.daily_return_percent > 0 for point in lab_days)
    return R2D2SummaryStats(
        closed_days=closed, positive_days=positive_days,
        above_half_percent_days=v2.above_half_percent_days + sum(point.daily_return_percent >= 0.5 for point in lab_days),
        negative_days=v2.negative_days + sum(point.daily_return_percent < 0 for point in lab_days),
        below_minus_half_percent_days=v2.below_minus_half_percent_days + sum(point.daily_return_percent <= -0.5 for point in lab_days),
        flat_days=v2.flat_days + sum(abs(point.daily_return_percent) < 1e-9 for point in lab_days),
        win_rate_percent=round(positive_days / closed * 100, 2) if closed else 0.0,
        total_transactions=v2.total_transactions + len(sells),
        positive_transactions=v2.positive_transactions + sum(1 for pnl in sells if pnl is not None and pnl > 0),
        negative_transactions=v2.negative_transactions + sum(1 for pnl in sells if pnl is not None and pnl < 0))


def apply_book_live(response: R2D2LivePositionsResponse, database: Any, *, now: datetime | None = None,
                    interest: list[tuple[str, float]] | None = None) -> R2D2LivePositionsResponse:
    found = latest_book(database, now=now)
    if found is None:
        return response
    book = found[2]
    accrued = _interest(interest, (now or datetime.now(timezone.utc)).astimezone(NEW_YORK).date().isoformat())[0]
    positions = _positions(book, now, nav=book["nav_usd"] + accrued)
    return response.model_copy(update={
        "nav_usd": round(book["nav_usd"] + accrued, 2), "cash_usd": round(book["cash_usd"] + accrued, 2),
        "gross_exposure_usd": round(sum(position.market_value_usd for position in positions), 2),
        "open_positions": len(positions), "positions": positions})
