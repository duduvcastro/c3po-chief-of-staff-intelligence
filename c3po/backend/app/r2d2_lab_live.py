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
from datetime import date, datetime, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from .schemas import R2D2Trade

TOKEN_ENV = "C3PO_R2D2_LAB_TOKEN"
SCHEMA = "C3PO-R2D2-LAB-LIVE-v1"
ANALYSIS_TYPE = "r2d2_lab_live"
METHODOLOGY_KEY = "r2d2_lab_live"
MAX_TRADES = 400
MAX_BODY_BYTES = 256 * 1024
MARKETS = ("NASDAQ", "NYSE")
SYMBOL = re.compile(r"[A-Z][A-Z0-9.\-]{0,9}")
TRADE_ID = re.compile(r"[A-Za-z0-9:._\-]{1,80}")
CONFIG = re.compile(r"[A-Za-z0-9._\-]{1,24}")
NEW_YORK = ZoneInfo("America/New_York")
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


def _number(value: Any, name: str, *, positive: bool = False, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise LabLiveRefused(f"{name} is not a finite number")
    if positive and float(value) <= 0:
        raise LabLiveRefused(f"{name} is not positive")
    return float(value)


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
    if not isinstance(payload, dict) or set(payload) != {"schema", "day", "config", "trades"}:
        raise LabLiveRefused("the payload keys are not exactly schema, day, config, trades")
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
        pnl = _number(trade["realized_pnl_usd"], "realized_pnl_usd", nullable=True)
        ret = _number(trade["realized_return_percent"], "realized_return_percent", nullable=True)
        if trade["side"] == "BUY" and (pnl is not None or ret is not None):
            raise LabLiveRefused("a BUY carries no realized result")
        out.append({"id": trade["id"], "side": trade["side"], "symbol": trade["symbol"], "market": trade["market"],
                    "quantity": _number(trade["quantity"], "quantity", positive=True),
                    "price": _number(trade["price"], "price", positive=True), "executed_at": executed.isoformat(),
                    "fees_usd": abs(_number(trade["fees_usd"], "fees_usd") or 0.0), "realized_pnl_usd": pnl,
                    "realized_return_percent": ret, "reason": trade["reason"]})
    return {"schema": SCHEMA, "day": day.isoformat(), "config": payload["config"], "trades": out}


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
