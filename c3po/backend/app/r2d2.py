from __future__ import annotations

import json
import logging
import math
import statistics
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from threading import Lock
from typing import Any, Iterator
from uuid import uuid4
from zoneinfo import ZoneInfo

from .config import Settings
from .database import Database
from .market_data.b3_screener import B3ScreenerService
from .market_data.brapi import BrapiClient
from .market_data.eodhd import EodhdClient
from .market_data.fmp import FmpClient
from .market_data.models import canonical_us_security_type
from .market_data.realtime import RealtimeMarketsService
from .market_data.us_screener import USScreeningService, clamp, normalized_percent
from .one_pager import OnePagerService
from . import r2d2_strategy
from .schemas import (
    R2D2CycleStatus,
    R2D2DashboardResponse,
    R2D2LearningCurvePoint,
    R2D2LearningState,
    R2D2Position,
    R2D2SummaryStats,
    R2D2TrackPoint,
    R2D2Trade,
)

logger = logging.getLogger(__name__)
SAO_PAULO = ZoneInfo("America/Sao_Paulo")
NEW_YORK = ZoneInfo("America/New_York")
METHODOLOGY_VERSION = "R2D2-HYBRID-V27-15M-LIQUIDITY-FLOOR"
ACTIVE_MARKETS = ("NASDAQ", "NYSE")
MIN_HOLD_MINUTES = 5
ROTATION_MIN_HOLD_MINUTES = 10
ROTATION_SCORE_GAP = 6.0
DAILY_OBJECTIVE_PERCENT = 0.5
WEEKLY_CONVICTION_MIN_SCORE = 72.0
PROFIT_TRIGGER_PERCENT = 0.65
PROFIT_LOCK_FLOOR_PERCENT = 0.35
PROFIT_PULLBACK_PERCENT = 0.35
WEEKLY_PROFIT_HARVEST_FRACTION = 0.70
MIN_POSITION_PERCENT = 2.0
MAX_DYNAMIC_POSITION_PERCENT = 6.0
SIMULATED_ROUND_TRIP_COST_PERCENT = 0.28
MIN_INTRADAY_EDGE_PERCENT = 0.55
# Lowered from $20M on 2026-08-20 (Dudu's call: split the difference between
# the $20M status quo and the $10M tested alternative, deliberately to
# observe the effect on the live-quote/WebSocket bottleneck rather than
# guess at it). Also feeds the liquidity-score log10 baseline at every site
# below -- keep all three literal duplicates in sync with this constant.
US_STOCK_MIN_CASH_VOLUME = 15_000_000
US_ETF_MIN_CASH_VOLUME = 10_000_000
FAILED_ENTRY_MINUTES = 3
FAILED_ENTRY_LOSS_PERCENT = 0.30
US_FUNDAMENTAL_BACKFILL_PER_CYCLE = 40
POSITION_STREAM_PRIORITY = 200
# US session policy is centralized here so candidate screening, position
# protection and close-time decisions cannot silently drift apart again.
US_SCREENING_START_ET = time(9, 40)
US_SCREENING_CUTOFF_ET = time(15, 50)
US_REGULAR_CLOSE_ET = time(16, 0)
BASE_ENTRY_POLICY = {
    "entry_upside_floor": 20.0,
    "max_risk_score": 48.0,
    "min_confidence": 60.0,
    "max_buy_in_distance": 15.0,
    "min_technical_score": 58.0,
    "min_composite_score": 62.0,
}
ENTRY_POLICY_BOUNDS = {
    "entry_upside_floor": (18.0, 28.0),
    "max_risk_score": (40.0, 52.0),
    "min_confidence": (58.0, 72.0),
    "max_buy_in_distance": (8.0, 15.0),
    "min_technical_score": (55.0, 68.0),
    "min_composite_score": (60.0, 72.0),
}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# EODHD's own documented per-call weights (confirmed 2026-08-18, see
# https://eodhd.com/financial-apis/api-limits) for the call types R2D2 makes a
# countable number of. Historical-price-endpoint weight was not confirmed as of
# this writing, so it's tracked as a raw count only -- not folded into the
# credit estimate below, to avoid asserting a number nobody has verified.
EODHD_CONFIRMED_CREDIT_WEIGHTS: dict[str, int] = {
    "backfill_fundamentals_symbols": 10,
    "intraday_cache_misses": 5,
    "fx_quote_calls": 1,
}


def _estimate_eodhd_credits(call_counts: dict[str, int]) -> dict[str, Any]:
    """Best-effort credit estimate for this cycle's EODHD usage, from raw call
    counts R2D2 itself tracked (see EODHD_CONFIRMED_CREDIT_WEIGHTS). Only
    categories with a confirmed weight are summed; everything else is still
    reported as a raw count so nothing is silently dropped from visibility."""
    estimated_total = sum(
        call_counts.get(key, 0) * weight for key, weight in EODHD_CONFIRMED_CREDIT_WEIGHTS.items()
    )
    return {
        "call_counts": dict(call_counts),
        "estimated_credits": estimated_total,
        "unweighted_categories": sorted(set(call_counts) - set(EODHD_CONFIRMED_CREDIT_WEIGHTS)),
    }


def _trade_is_corrected(trade: dict[str, Any]) -> bool:
    """True if a trade's realized_pnl_usd is known-bad (see 2026-08-18 incident,
    PRs #5-#7): a manual cash_balance correction was posted for it and its
    decision_snapshot is annotated accordingly. The raw row is left unmodified
    for the audit trail, so anything that aggregates realized_pnl_usd for a
    performance or learning signal must exclude these explicitly instead."""
    snapshot = trade.get("decision_snapshot")
    return isinstance(snapshot, dict) and "correction" in snapshot


def _realized_return_percent(*, gross_value_usd: Any, fees_usd: Any,
                             realized_pnl_usd: Any) -> float | None:
    if realized_pnl_usd is None:
        return None
    realized = _float(realized_pnl_usd)
    released_cost_basis = _float(gross_value_usd) - _float(fees_usd) - realized
    if released_cost_basis <= 0:
        return None
    return round(realized / released_cost_basis * 100, 4)


def _date_value(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip().split()[0])


class R2D2Repository:
    """Persistent paper ledger. It deliberately exposes no real-broker operation."""

    def __init__(self, database: Database) -> None:
        self.database = database
        if not hasattr(database, "_r2d2_memory"):
            database._r2d2_memory = {  # type: ignore[attr-defined]
                "experiment": None, "positions": {}, "trades": [], "snapshots": {},
                "cycles": [], "decisions": [], "learning": [],
            }
        if not hasattr(database, "_r2d2_risk_evaluation_lock"):
            database._r2d2_risk_evaluation_lock = Lock()  # type: ignore[attr-defined]
        if not hasattr(database, "_r2d2_fast_risk_alerts"):
            database._r2d2_fast_risk_alerts = set()  # type: ignore[attr-defined]

    @property
    def memory(self) -> dict[str, Any]:
        return self.database._r2d2_memory  # type: ignore[attr-defined]

    @contextmanager
    def risk_evaluation_lock(self, experiment_id: str) -> Iterator[bool]:
        """Serialize position evaluation across the normal and dedicated loops.

        PostgreSQL owns the production lock, so the guarantee also holds if the
        worker is ever split across processes. The in-memory lock keeps unit
        tests and local paper runs equivalent.
        """
        if not self.database.database_url:
            lock: Lock = self.database._r2d2_risk_evaluation_lock  # type: ignore[attr-defined]
            acquired = lock.acquire(blocking=False)
            try:
                yield acquired
            finally:
                if acquired:
                    lock.release()
            return

        lock_name = f"r2d2-risk-evaluation:{experiment_id}"
        with self.database.connection() as connection:
            acquired = bool(connection.execute(
                "SELECT pg_try_advisory_xact_lock(hashtext(%s))",
                (lock_name,),
            ).fetchone()[0])
            try:
                yield acquired
            finally:
                # The transaction-scoped advisory lock is released here even
                # when evaluation or paper execution raises.
                connection.rollback()

    def ensure_experiment(self, settings: Settings) -> dict[str, Any]:
        start = _date_value(settings.r2d2_start_date)
        checkpoint = start + timedelta(days=max(settings.r2d2_checkpoint_days, 1) - 1)
        mandate = {
            "mode": "paper_only",
            "real_broker_execution": False,
            "markets": list(ACTIVE_MARKETS),
            "retired_markets": {
                "B3": "Disabled for paper intraday execution because the available quote feed is delayed by five minutes.",
            },
            "max_positions": settings.r2d2_max_positions,
            "max_position_percent": settings.r2d2_max_position_percent,
            "max_market_percent": settings.r2d2_max_market_percent,
            "max_cash_percent": settings.r2d2_max_cash_percent,
            "minimum_invested_percent": 100.0 - settings.r2d2_max_cash_percent,
            "minimum_cash_buffer_percent": settings.r2d2_min_cash_buffer_percent,
            "max_gross_exposure_percent": settings.r2d2_max_gross_exposure_percent,
            "daily_loss_limit_percent": settings.r2d2_daily_loss_limit_percent,
            "soft_loss_exit_percent": settings.r2d2_soft_loss_exit_percent,
            "max_position_loss_percent": settings.r2d2_max_position_loss_percent,
            "leverage": False,
            "short_selling": False,
            "derivatives": False,
            "decision_cadence_seconds": 20,
            "candidate_scan_seconds": settings.r2d2_cycle_seconds,
            "daily_order_target_range": [20, 80],
            "max_daily_orders": settings.r2d2_max_daily_orders,
            "order_target_is_mandatory": False,
            "efficiency_definition": "net P&L after simulated fees and slippage, never raw order count",
            "performance_target_percent": DAILY_OBJECTIVE_PERCENT,
            "performance_target_is_mandatory": False,
            "horizon_policy": {
                "daily_objective": (
                    "Seek +0.5% at portfolio level through the tactical sleeve; never force a trade "
                    "or weaken hard risk controls to manufacture the target."
                ),
                "weekly_conviction": (
                    "A position may cross sessions while fundamental conviction, live trend, flow, "
                    "momentum and price structure remain aligned."
                ),
                "decision_priority": [
                    "confirmed hard risk", "confirmed reversal", "capital preservation",
                    "daily portfolio objective", "weekly expected value", "turnover minimization",
                ],
            },
            "exit_replacement": "immediate eligible scan across open US markets",
            "opportunity_funnel": {
                "coverage": "full quoted EODHD catalog for NASDAQ, NYSE, NYSE Arca and NYSE American",
                "security_types": ["stocks", "ETFs"],
                "deep_shortlist_per_market": "uncapped -- every symbol clearing the price/liquidity bar",
                "technical_reviews_per_market": {
                    "cash_deployment": settings.r2d2_deployment_technical_review_per_market,
                    "standard": settings.r2d2_standard_technical_review_per_market,
                },
                "entry_routes": [
                    "strategic valuation", "tactical quality momentum",
                    "cost-aware intraday momentum",
                ],
            },
            "position_sizing": {
                "model": "risk-normalized (Turtle-style)",
                "minimum_percent": MIN_POSITION_PERCENT,
                "risk_budget_percent": r2d2_strategy.RISK_BUDGET_PERCENT,
                "maximum_percent": min(
                    MAX_DYNAMIC_POSITION_PERCENT,
                    settings.r2d2_max_position_percent,
                ),
                "portfolio_pacing": (
                    "treat 25% cash as a normal ceiling, seek at least 75% invested with eligible signals, "
                    "and preserve a 5% execution buffer"
                ),
                "cash_deployment": "expand technical review and size eligible entries while cash exceeds the ceiling",
            },
            "continuous_operation": True,
            "checkpoint_days": settings.r2d2_checkpoint_days,
            "checkpoint_is_termination": False,
            "daily_learning": "versioned, bounded and audit-trailed",
            "fundamental_layer": [
                "C3PO TP", "DCF", "multiples", "consensus", "buy-in", "quality",
                "CVM/Finnhub insider governance signal (borrowed via Dark Side's risk score, not independently checked here)",
            ],
            "technical_layer": [
                "session VWAP", "EMA 8/20/50", "RSI 14", "MACD acceleration",
                "momentum 15/30/60m", "relative volume", "OBV slope", "MFI 14",
                "price structure", "EMA slope", "selling-volume pressure",
                "ATR drawdown", "relative strength", "ATR regime",
            ],
            "exit_layer": [
                "live-quote hard stop", "weighted technical-defense score",
                "failed-entry fast exit", "two-review confirmation", "progressive 50% risk reduction",
                "defensive soft-loss exit", "adaptive ATR stop", "profit lock",
                "multi-horizon trend and flow reversal",
                "weekly-conviction hold", "stagnation time stop", "opportunity-cost rotation",
                "same-cycle replacement", "same-session full-exit re-entry lock", "anomalous tick guard",
            ],
            "turnover_policy": {
                "style": "high-turnover paper intraday",
                "target_orders_per_session": "20-80 when qualified signals exist",
                "hard_order_cap": settings.r2d2_max_daily_orders,
                "minimum_hold_minutes": MIN_HOLD_MINUTES,
                "rotation_hold_minutes": ROTATION_MIN_HOLD_MINUTES,
                "reentry_cooldown_minutes": settings.r2d2_trade_cooldown_minutes,
                "full_exit_reentry_policy": "blocked until the next Sao Paulo trading date",
                "profit_trigger_percent": PROFIT_TRIGGER_PERCENT,
                "simulated_round_trip_cost_percent": SIMULATED_ROUND_TRIP_COST_PERCENT,
                "minimum_modeled_edge_percent": MIN_INTRADAY_EDGE_PERCENT,
            },
            "quote_policy": {
                "execution_markets": list(ACTIVE_MARKETS),
                "required_status": "live",
                "maximum_age_seconds": settings.r2d2_live_quote_max_age_seconds,
                "b3_policy": "exit existing paper positions during the B3 session; never open a new B3 position",
            },
        }
        now = datetime.now(timezone.utc)
        status = "scheduled" if now.astimezone(SAO_PAULO).date() < start else "running"
        payload = {
            "id": str(uuid4()), "code": settings.r2d2_experiment_code, "status": status,
            "base_currency": "USD", "starting_capital": settings.r2d2_starting_capital_usd,
            "cash_balance": settings.r2d2_starting_capital_usd, "start_date": start,
            "checkpoint_date": checkpoint, "methodology_version": METHODOLOGY_VERSION,
            "mandate": mandate, "created_at": now, "updated_at": now,
        }
        if not self.database.database_url:
            if not self.memory["experiment"]:
                self.memory["experiment"] = payload
            elif now.astimezone(SAO_PAULO).date() >= self.memory["experiment"]["start_date"]:
                self.memory["experiment"]["status"] = "running"
            return dict(self.memory["experiment"])
        with self.database.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO r2d2_experiments
                    (id, code, status, starting_capital, cash_balance, start_date, end_date,
                     checkpoint_date, is_continuous, methodology_version, mandate)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s::jsonb)
                ON CONFLICT (code) DO UPDATE SET mandate = EXCLUDED.mandate,
                    checkpoint_date = EXCLUDED.checkpoint_date, is_continuous = TRUE,
                    methodology_version = EXCLUDED.methodology_version, updated_at = now(),
                    status = CASE
                        WHEN r2d2_experiments.status = 'paused' THEN 'paused'
                        WHEN (CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date
                             < r2d2_experiments.start_date THEN 'scheduled'
                        ELSE 'running' END
                RETURNING id::text, code, status, base_currency, starting_capital, cash_balance,
                          start_date, checkpoint_date, methodology_version, mandate, created_at, updated_at
                """,
                (payload["id"], payload["code"], payload["status"], payload["starting_capital"],
                 payload["cash_balance"], start, checkpoint, checkpoint, METHODOLOGY_VERSION, json.dumps(mandate)),
            ).fetchone()
            connection.commit()
        return self._experiment(row)

    @staticmethod
    def _experiment(row: Any) -> dict[str, Any]:
        keys = ("id", "code", "status", "base_currency", "starting_capital", "cash_balance",
                "start_date", "checkpoint_date", "methodology_version", "mandate", "created_at", "updated_at")
        return dict(zip(keys, row))

    def positions(self, experiment_id: str) -> list[dict[str, Any]]:
        if not self.database.database_url:
            return [dict(value) for value in self.memory["positions"].values()]
        with self.database.connection() as connection:
            rows = connection.execute(
                """SELECT market, symbol, name, currency, quantity, average_cost_local,
                          average_cost_usd, last_price_local, fx_to_usd, high_water_price_local,
                          stop_price_local, opened_at, updated_at, strategy_snapshot,
                          hard_stop_price_local, chandelier_atr_local, chandelier_atr_as_of,
                          chandelier_stop_price_local, chandelier_confirmation_count,
                          chandelier_last_confirmation_tick_at
                   FROM r2d2_positions WHERE experiment_id = %s ORDER BY market, symbol""",
                (experiment_id,),
            ).fetchall()
        keys = ("market", "symbol", "name", "currency", "quantity", "average_cost_local",
                "average_cost_usd", "last_price_local", "fx_to_usd", "high_water_price_local",
                "stop_price_local", "opened_at", "updated_at", "strategy_snapshot",
                "hard_stop_price_local", "chandelier_atr_local", "chandelier_atr_as_of",
                "chandelier_stop_price_local", "chandelier_confirmation_count",
                "chandelier_last_confirmation_tick_at")
        return [dict(zip(keys, row)) for row in rows]

    def update_mark(self, experiment_id: str, market: str, symbol: str, price: float, fx: float,
                    high_water: float, stop: float, updated_at: datetime,
                    strategy_snapshot: dict[str, Any] | None = None, *,
                    write_high_water: bool = True) -> None:
        if not self.database.database_url:
            item = self.memory["positions"].get((market, symbol))
            if item:
                item.update(last_price_local=price, fx_to_usd=fx,
                            stop_price_local=stop, updated_at=updated_at)
                if write_high_water:
                    item["high_water_price_local"] = max(
                        _float(item.get("high_water_price_local")), high_water,
                    )
                if strategy_snapshot is not None:
                    item["strategy_snapshot"] = strategy_snapshot
            return
        with self.database.connection() as connection:
            connection.execute(
                """UPDATE r2d2_positions SET last_price_local=%s, fx_to_usd=%s,
                          high_water_price_local=CASE WHEN %s THEN
                              GREATEST(high_water_price_local, %s) ELSE high_water_price_local END,
                          stop_price_local=%s, updated_at=%s,
                          strategy_snapshot=COALESCE(%s::jsonb, strategy_snapshot)
                   WHERE experiment_id=%s AND market=%s AND symbol=%s""",
                (price, fx, write_high_water, high_water, stop, updated_at,
                 json.dumps(strategy_snapshot) if strategy_snapshot is not None else None,
                 experiment_id, market, symbol),
            )
            connection.commit()

    def update_chandelier_anchor(self, experiment_id: str, market: str, symbol: str,
                                 *, atr: float, hard_stop: float, as_of: datetime) -> None:
        """Refresh ATR without taking high-water ownership from the fast watcher."""
        if atr <= 0:
            return
        if not self.database.database_url:
            item = self.memory["positions"].get((market, symbol))
            if not item:
                return
            item["chandelier_atr_local"] = atr
            item["chandelier_atr_as_of"] = as_of
            item["hard_stop_price_local"] = max(
                _float(item.get("hard_stop_price_local")), hard_stop,
            )
            candidate = _float(item["high_water_price_local"]) - atr * 2.5
            item["chandelier_stop_price_local"] = max(
                _float(item.get("chandelier_stop_price_local")), candidate,
            )
            return
        with self.database.connection() as connection:
            connection.execute(
                """UPDATE r2d2_positions
                   SET chandelier_atr_local=%s, chandelier_atr_as_of=%s,
                       hard_stop_price_local=GREATEST(COALESCE(hard_stop_price_local, 0), %s),
                       chandelier_stop_price_local=GREATEST(
                           COALESCE(chandelier_stop_price_local, 0),
                           high_water_price_local - (%s * 2.5)
                       )
                   WHERE experiment_id=%s AND market=%s AND symbol=%s""",
                (atr, as_of, hard_stop, atr, experiment_id, market, symbol),
            )
            connection.commit()

    def observe_fast_risk_tick(self, experiment_id: str, market: str, symbol: str,
                               *, price: float, tick_as_of: datetime) -> dict[str, Any] | None:
        """Atomically advance monotonic high-water and distinct-tick confirmation state."""
        if not self.database.database_url:
            item = self.memory["positions"].get((market, symbol))
            if not item:
                return None
            item["high_water_price_local"] = max(_float(item["high_water_price_local"]), price)
            atr = _float(item.get("chandelier_atr_local"))
            if atr > 0:
                item["chandelier_stop_price_local"] = max(
                    _float(item.get("chandelier_stop_price_local")),
                    _float(item["high_water_price_local"]) - atr * 2.5,
                )
            stop = _float(item.get("chandelier_stop_price_local"))
            last_confirmation = item.get("chandelier_last_confirmation_tick_at")
            distinct = not isinstance(last_confirmation, datetime) or tick_as_of > last_confirmation
            if stop > 0 and price <= stop and distinct:
                item["chandelier_confirmation_count"] = int(item.get("chandelier_confirmation_count") or 0) + 1
                item["chandelier_last_confirmation_tick_at"] = tick_as_of
            elif stop > 0 and price > stop:
                item["chandelier_confirmation_count"] = 0
                item["chandelier_last_confirmation_tick_at"] = None
            return dict(item)
        with self.database.connection() as connection:
            row = connection.execute(
                """UPDATE r2d2_positions
                   SET high_water_price_local=GREATEST(high_water_price_local, %s),
                       chandelier_stop_price_local=CASE
                           WHEN chandelier_atr_local IS NULL THEN chandelier_stop_price_local
                           ELSE GREATEST(
                               COALESCE(chandelier_stop_price_local, 0),
                               GREATEST(high_water_price_local, %s) - chandelier_atr_local * 2.5
                           )
                       END,
                       chandelier_confirmation_count=CASE
                           WHEN chandelier_atr_local IS NOT NULL
                            AND %s <= GREATEST(
                                COALESCE(chandelier_stop_price_local, 0),
                                GREATEST(high_water_price_local, %s) - chandelier_atr_local * 2.5
                            )
                            AND (chandelier_last_confirmation_tick_at IS NULL
                                 OR %s > chandelier_last_confirmation_tick_at)
                           THEN chandelier_confirmation_count + 1
                           WHEN chandelier_atr_local IS NOT NULL
                            AND %s > GREATEST(
                                COALESCE(chandelier_stop_price_local, 0),
                                GREATEST(high_water_price_local, %s) - chandelier_atr_local * 2.5
                            )
                           THEN 0
                           ELSE chandelier_confirmation_count
                       END,
                       chandelier_last_confirmation_tick_at=CASE
                           WHEN chandelier_atr_local IS NOT NULL
                            AND %s <= GREATEST(
                                COALESCE(chandelier_stop_price_local, 0),
                                GREATEST(high_water_price_local, %s) - chandelier_atr_local * 2.5
                            )
                            AND (chandelier_last_confirmation_tick_at IS NULL
                                 OR %s > chandelier_last_confirmation_tick_at)
                           THEN %s
                           WHEN chandelier_atr_local IS NOT NULL
                            AND %s > GREATEST(
                                COALESCE(chandelier_stop_price_local, 0),
                                GREATEST(high_water_price_local, %s) - chandelier_atr_local * 2.5
                            )
                           THEN NULL
                           ELSE chandelier_last_confirmation_tick_at
                       END
                   WHERE experiment_id=%s AND market=%s AND symbol=%s
                   RETURNING high_water_price_local, hard_stop_price_local,
                             chandelier_atr_local, chandelier_atr_as_of,
                             chandelier_stop_price_local, chandelier_confirmation_count,
                             chandelier_last_confirmation_tick_at""",
                (
                    price, price, price, price, tick_as_of, price, price,
                    price, price, tick_as_of, tick_as_of, price, price,
                    experiment_id, market, symbol,
                ),
            ).fetchone()
            connection.commit()
        if not row:
            return None
        keys = (
            "high_water_price_local", "hard_stop_price_local", "chandelier_atr_local",
            "chandelier_atr_as_of", "chandelier_stop_price_local",
            "chandelier_confirmation_count", "chandelier_last_confirmation_tick_at",
        )
        return dict(zip(keys, row))

    def advance_fast_high_water(self, experiment_id: str, market: str, symbol: str,
                                *, price: float) -> None:
        """Advance high-water without touching Chandelier confirmation state."""
        if not self.database.database_url:
            item = self.memory["positions"].get((market, symbol))
            if item:
                item["high_water_price_local"] = max(
                    _float(item["high_water_price_local"]), price,
                )
            return
        with self.database.connection() as connection:
            connection.execute(
                """UPDATE r2d2_positions
                   SET high_water_price_local=GREATEST(high_water_price_local, %s)
                   WHERE experiment_id=%s AND market=%s AND symbol=%s""",
                (price, experiment_id, market, symbol),
            )
            connection.commit()

    def execute_trade(self, experiment: dict[str, Any], *, cycle_id: str, candidate: dict[str, Any],
                      side: str, quantity: float, signal_price: float, fill_price: float, fx: float,
                      fees: float, slippage: float, reason: str, decision: dict[str, Any],
                      quote_as_of: datetime,
                      fast_exit_audit: dict[str, Any] | None = None) -> dict[str, Any]:
        trade_id = str(uuid4())
        now = datetime.now(timezone.utc)
        gross = quantity * fill_price * fx
        position_key = (candidate["market"], candidate["symbol"])
        realized: float | None = None
        if not self.database.database_url:
            current = self.memory["positions"].get(position_key)
            cash = _float(experiment["cash_balance"])
            if side == "BUY":
                total_cost = gross + fees
                if total_cost > cash + 0.01:
                    raise ValueError("Paper order exceeds available cash")
                old_qty = _float(current.get("quantity")) if current else 0.0
                old_cost = _float(current.get("average_cost_usd")) if current else 0.0
                new_qty = old_qty + quantity
                avg_usd = ((old_qty * old_cost) + gross + fees) / new_qty
                self.memory["positions"][position_key] = {
                    "market": candidate["market"], "symbol": candidate["symbol"], "name": candidate["name"],
                    "currency": candidate["currency"], "quantity": new_qty,
                    "average_cost_local": avg_usd / fx, "average_cost_usd": avg_usd,
                    "last_price_local": fill_price, "fx_to_usd": fx,
                    "high_water_price_local": fill_price, "stop_price_local": candidate["stop_price"],
                    "hard_stop_price_local": candidate["stop_price"],
                    "chandelier_atr_local": None, "chandelier_atr_as_of": None,
                    "chandelier_stop_price_local": None,
                    "chandelier_confirmation_count": 0,
                    "chandelier_last_confirmation_tick_at": None,
                    "opened_at": current.get("opened_at", now) if current else now, "updated_at": now,
                    "strategy_snapshot": decision,
                }
                experiment["cash_balance"] = cash - total_cost
            else:
                if not current or quantity > _float(current["quantity"]) + 1e-8:
                    raise ValueError("Paper sell exceeds the virtual position")
                realized = gross - fees - quantity * _float(current["average_cost_usd"])
                remaining = _float(current["quantity"]) - quantity
                experiment["cash_balance"] = cash + gross - fees
                if remaining <= 1e-8:
                    self.memory["positions"].pop(position_key, None)
                else:
                    current.update(quantity=remaining, last_price_local=fill_price, updated_at=now)
            self.memory["experiment"].update(cash_balance=experiment["cash_balance"], status="running", updated_at=now)
        else:
            with self.database.connection() as connection:
                locked = connection.execute(
                    "SELECT cash_balance FROM r2d2_experiments WHERE id=%s FOR UPDATE",
                    (experiment["id"],),
                ).fetchone()
                cash = _float(locked[0])
                current = connection.execute(
                    """SELECT quantity, average_cost_usd, opened_at FROM r2d2_positions
                       WHERE experiment_id=%s AND market=%s AND symbol=%s FOR UPDATE""",
                    (experiment["id"], candidate["market"], candidate["symbol"]),
                ).fetchone()
                if side == "BUY":
                    if gross + fees > cash + 0.01:
                        raise ValueError("Paper order exceeds available cash")
                    old_qty, old_cost = (_float(current[0]), _float(current[1])) if current else (0.0, 0.0)
                    new_qty = old_qty + quantity
                    avg_usd = ((old_qty * old_cost) + gross + fees) / new_qty
                    connection.execute(
                        """INSERT INTO r2d2_positions
                           (experiment_id, market, symbol, name, currency, quantity, average_cost_local,
                            average_cost_usd, last_price_local, fx_to_usd, high_water_price_local,
                            stop_price_local, opened_at, updated_at, strategy_snapshot,
                            hard_stop_price_local)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                           ON CONFLICT (experiment_id, market, symbol) DO UPDATE SET
                             quantity=EXCLUDED.quantity, average_cost_local=EXCLUDED.average_cost_local,
                             average_cost_usd=EXCLUDED.average_cost_usd, last_price_local=EXCLUDED.last_price_local,
                             fx_to_usd=EXCLUDED.fx_to_usd, high_water_price_local=GREATEST(r2d2_positions.high_water_price_local, EXCLUDED.high_water_price_local),
                             stop_price_local=EXCLUDED.stop_price_local,
                             hard_stop_price_local=EXCLUDED.hard_stop_price_local,
                             updated_at=EXCLUDED.updated_at,
                             strategy_snapshot=EXCLUDED.strategy_snapshot""",
                        (experiment["id"], candidate["market"], candidate["symbol"], candidate["name"],
                         candidate["currency"], new_qty, avg_usd / fx, avg_usd, fill_price, fx, fill_price,
                         candidate["stop_price"], current[2] if current else now, now,
                         json.dumps(decision, default=str), candidate["stop_price"]),
                    )
                    cash -= gross + fees
                else:
                    if not current or quantity > _float(current[0]) + 1e-8:
                        raise ValueError("Paper sell exceeds the virtual position")
                    realized = gross - fees - quantity * _float(current[1])
                    remaining = _float(current[0]) - quantity
                    if remaining <= 1e-8:
                        connection.execute(
                            "DELETE FROM r2d2_positions WHERE experiment_id=%s AND market=%s AND symbol=%s",
                            (experiment["id"], candidate["market"], candidate["symbol"]),
                        )
                    else:
                        connection.execute(
                            """UPDATE r2d2_positions SET quantity=%s, last_price_local=%s,
                                      fx_to_usd=%s, updated_at=%s
                               WHERE experiment_id=%s AND market=%s AND symbol=%s""",
                            (remaining, fill_price, fx, now, experiment["id"], candidate["market"], candidate["symbol"]),
                        )
                    cash += gross - fees
                connection.execute(
                    "UPDATE r2d2_experiments SET cash_balance=%s, status='running', updated_at=%s WHERE id=%s",
                    (cash, now, experiment["id"]),
                )
                connection.execute(
                    """INSERT INTO r2d2_trades
                       (id, experiment_id, cycle_id, market, symbol, name, side, quantity,
                        signal_price_local, fill_price_local, fx_to_usd, gross_value_usd, fees_usd,
                        slippage_usd, realized_pnl_usd, reason, decision_snapshot, executed_at, quote_as_of,
                        fast_exit_rule, fast_exit_level_local, fast_exit_atr_local, fast_exit_tick_as_of)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s)""",
                    (trade_id, experiment["id"], cycle_id, candidate["market"], candidate["symbol"],
                     candidate["name"], side, quantity, signal_price, fill_price, fx, gross, fees,
                     slippage, realized, reason, json.dumps(decision, default=str), now, quote_as_of,
                     (fast_exit_audit or {}).get("rule"), (fast_exit_audit or {}).get("level"),
                     (fast_exit_audit or {}).get("atr"), (fast_exit_audit or {}).get("tick_as_of")),
                )
                connection.commit()
            experiment["cash_balance"] = cash
        trade = {
            "id": trade_id, "experiment_id": experiment["id"], "cycle_id": cycle_id,
            "market": candidate["market"], "symbol": candidate["symbol"], "name": candidate["name"],
            "side": side, "quantity": quantity, "signal_price_local": signal_price,
            "fill_price_local": fill_price, "fx_to_usd": fx, "gross_value_usd": gross,
            "fees_usd": fees, "slippage_usd": slippage, "realized_pnl_usd": realized,
            "realized_return_percent": _realized_return_percent(
                gross_value_usd=gross, fees_usd=fees, realized_pnl_usd=realized,
            ),
            "reason": reason, "decision_snapshot": decision, "executed_at": now,
            "quote_as_of": quote_as_of, "currency": candidate["currency"],
            "fast_exit_rule": (fast_exit_audit or {}).get("rule"),
            "fast_exit_level_local": (fast_exit_audit or {}).get("level"),
            "fast_exit_atr_local": (fast_exit_audit or {}).get("atr"),
            "fast_exit_tick_as_of": (fast_exit_audit or {}).get("tick_as_of"),
        }
        if not self.database.database_url:
            self.memory["trades"].append(trade)
        return trade

    def save_decision(self, experiment_id: str, cycle_id: str, candidate: dict[str, Any],
                      action: str, reasons: list[str], trade_id: str | None = None) -> None:
        payload = {
            "id": str(uuid4()), "experiment_id": experiment_id, "cycle_id": cycle_id,
            "evaluated_at": datetime.now(timezone.utc), "market": candidate["market"],
            "symbol": candidate["symbol"], "action": action,
            "fundamental_score": candidate.get("fundamental_score", 0),
            "technical_score": candidate.get("technical_score", 0),
            "risk_score": candidate.get("risk_score", 100),
            "composite_score": candidate.get("composite_score", 0),
            "reasons": reasons, "inputs": candidate, "trade_id": trade_id,
        }
        if not self.database.database_url:
            self.memory["decisions"].append(payload)
            return
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO r2d2_decisions
                   (id, experiment_id, cycle_id, evaluated_at, market, symbol, action,
                    fundamental_score, technical_score, risk_score, composite_score,
                    reasons, inputs, trade_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)""",
                (payload["id"], experiment_id, cycle_id, payload["evaluated_at"], payload["market"],
                 payload["symbol"], action, payload["fundamental_score"], payload["technical_score"],
                 payload["risk_score"], payload["composite_score"], json.dumps(reasons),
                 json.dumps(candidate, default=str), trade_id),
            )
            connection.commit()

    def save_snapshot(self, experiment_id: str, session_date: date, nav: float, cash: float,
                      exposure: float, positions: int, is_final: bool = False) -> dict[str, Any]:
        snapshots = self.snapshots(experiment_id)
        prior = next((item for item in reversed(snapshots) if item["session_date"] < session_date), None)
        if prior:
            base = _float(prior["nav_usd"])
        elif not self.database.database_url:
            base = _float((self.memory.get("experiment") or {}).get("starting_capital"), nav)
        else:
            with self.database.connection() as connection:
                row = connection.execute(
                    "SELECT starting_capital FROM r2d2_experiments WHERE id=%s",
                    (experiment_id,),
                ).fetchone()
            base = _float(row[0], nav) if row else nav
        pnl = nav - base
        daily_return = pnl / base * 100 if base else 0.0
        payload = {
            "session_date": session_date, "nav_usd": nav, "cash_usd": cash,
            "daily_pnl_usd": pnl, "daily_return_percent": daily_return,
            "gross_exposure_usd": exposure, "open_positions": positions, "is_final": is_final,
        }
        if not self.database.database_url:
            self.memory["snapshots"][session_date] = payload
            return payload
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO r2d2_daily_snapshots
                   (experiment_id, session_date, nav_usd, cash_usd, daily_pnl_usd,
                    daily_return_percent, gross_exposure_usd, open_positions, is_final)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (experiment_id, session_date) DO UPDATE SET
                     nav_usd=EXCLUDED.nav_usd, cash_usd=EXCLUDED.cash_usd,
                     daily_pnl_usd=EXCLUDED.daily_pnl_usd,
                     daily_return_percent=EXCLUDED.daily_return_percent,
                     gross_exposure_usd=EXCLUDED.gross_exposure_usd,
                     open_positions=EXCLUDED.open_positions,
                     is_final=r2d2_daily_snapshots.is_final OR EXCLUDED.is_final, updated_at=now()""",
                (experiment_id, session_date, nav, cash, pnl, daily_return, exposure, positions, is_final),
            )
            connection.commit()
        return payload

    def snapshots(self, experiment_id: str) -> list[dict[str, Any]]:
        if not self.database.database_url:
            return [dict(value) for _, value in sorted(self.memory["snapshots"].items())]
        with self.database.connection() as connection:
            rows = connection.execute(
                """SELECT session_date, nav_usd, cash_usd, daily_pnl_usd,
                          daily_return_percent, gross_exposure_usd, open_positions, is_final
                   FROM r2d2_daily_snapshots WHERE experiment_id=%s ORDER BY session_date""",
                (experiment_id,),
            ).fetchall()
        keys = ("session_date", "nav_usd", "cash_usd", "daily_pnl_usd", "daily_return_percent",
                "gross_exposure_usd", "open_positions", "is_final")
        return [dict(zip(keys, row)) for row in rows]

    def finalize_before(self, experiment_id: str, session_date: date) -> None:
        if not self.database.database_url:
            for key, item in self.memory["snapshots"].items():
                if key < session_date:
                    item["is_final"] = True
            return
        with self.database.connection() as connection:
            connection.execute(
                """UPDATE r2d2_daily_snapshots SET is_final=TRUE, updated_at=now()
                   WHERE experiment_id=%s AND session_date < %s AND is_final=FALSE""",
                (experiment_id, session_date),
            )
            connection.commit()

    def trades(self, experiment_id: str, limit: int = 250) -> list[dict[str, Any]]:
        if not self.database.database_url:
            return [dict(item) for item in reversed(self.memory["trades"][-limit:])]
        with self.database.connection() as connection:
            rows = connection.execute(
                """SELECT id::text, market, symbol, name, side, quantity, signal_price_local,
                          fill_price_local, fx_to_usd, gross_value_usd, fees_usd, slippage_usd,
                          realized_pnl_usd, reason, decision_snapshot, executed_at, quote_as_of
                   FROM r2d2_trades WHERE experiment_id=%s ORDER BY executed_at DESC LIMIT %s""",
                (experiment_id, limit),
            ).fetchall()
        keys = ("id", "market", "symbol", "name", "side", "quantity", "signal_price_local",
                "fill_price_local", "fx_to_usd", "gross_value_usd", "fees_usd", "slippage_usd",
                "realized_pnl_usd", "reason", "decision_snapshot", "executed_at", "quote_as_of")
        return [dict(zip(keys, row)) for row in rows]

    def trade_summary(self, experiment_id: str) -> dict[str, int]:
        if not self.database.database_url:
            trades = [
                item for item in self.memory["trades"]
                if item.get("experiment_id") == experiment_id and not _trade_is_corrected(item)
            ]
            return {
                "total_transactions": len(trades),
                "positive_transactions": sum(_float(item.get("realized_pnl_usd")) > 0 for item in trades),
                "negative_transactions": sum(_float(item.get("realized_pnl_usd")) < 0 for item in trades),
            }
        with self.database.connection() as connection:
            row = connection.execute(
                """SELECT COUNT(*),
                          COUNT(*) FILTER (WHERE realized_pnl_usd > 0),
                          COUNT(*) FILTER (WHERE realized_pnl_usd < 0)
                   FROM r2d2_trades
                   WHERE experiment_id=%s AND NOT (decision_snapshot ? 'correction')""",
                (experiment_id,),
            ).fetchone()
        return dict(zip(
            ("total_transactions", "positive_transactions", "negative_transactions"),
            (int(value or 0) for value in (row or (0, 0, 0))),
        ))

    def daily_learning_curve(self, experiment_id: str) -> list[dict[str, Any]]:
        """One row per session day with at least one closed (SELL, realized)
        trade: how many closed positive vs negative -- the "Learning Curve"
        chart's raw material. Deliberately NOT derived from trades()/limit=250
        (which only covers the last ~1-2 days at real trading volume); this
        aggregates the full r2d2_trades history so the chart still works
        after weeks/months, the same way track_record does via a separate
        query rather than the capped trades list. Corrected/phantom trades
        excluded, same as trade_summary().
        """
        if not self.database.database_url:
            trades = [
                item for item in self.memory["trades"]
                if item.get("experiment_id") == experiment_id and not _trade_is_corrected(item)
            ]
            buckets: dict[date, dict[str, int]] = {}
            for item in trades:
                pnl = item.get("realized_pnl_usd")
                if pnl is None:
                    continue
                executed_at = item.get("executed_at")
                if not isinstance(executed_at, datetime):
                    continue
                session_date = executed_at.astimezone(SAO_PAULO).date()
                bucket = buckets.setdefault(session_date, {"positive": 0, "negative": 0})
                if _float(pnl) > 0:
                    bucket["positive"] += 1
                elif _float(pnl) < 0:
                    bucket["negative"] += 1
            return [
                {"session_date": session_date, "positive": bucket["positive"], "negative": bucket["negative"]}
                for session_date, bucket in sorted(buckets.items())
                if bucket["positive"] + bucket["negative"] > 0
            ]
        with self.database.connection() as connection:
            rows = connection.execute(
                """SELECT (executed_at AT TIME ZONE 'America/Sao_Paulo')::date AS session_date,
                          COUNT(*) FILTER (WHERE realized_pnl_usd > 0),
                          COUNT(*) FILTER (WHERE realized_pnl_usd < 0)
                   FROM r2d2_trades
                   WHERE experiment_id=%s AND realized_pnl_usd IS NOT NULL
                     AND NOT (decision_snapshot ? 'correction')
                   GROUP BY session_date
                   ORDER BY session_date""",
                (experiment_id,),
            ).fetchall()
        return [
            {"session_date": row[0], "positive": int(row[1] or 0), "negative": int(row[2] or 0)}
            for row in rows
        ]

    def learning_states(self, experiment_id: str) -> list[dict[str, Any]]:
        if not self.database.database_url:
            return [dict(item) for item in self.memory["learning"]]
        with self.database.connection() as connection:
            rows = connection.execute(
                """SELECT version, effective_date, sample_days, sample_trades,
                          parameters, metrics, rationale, created_at
                   FROM r2d2_learning_states
                   WHERE experiment_id=%s ORDER BY effective_date""",
                (experiment_id,),
            ).fetchall()
        keys = ("version", "effective_date", "sample_days", "sample_trades",
                "parameters", "metrics", "rationale", "created_at")
        return [dict(zip(keys, row)) for row in rows]

    def save_learning_state(self, experiment_id: str, state: dict[str, Any]) -> dict[str, Any]:
        if not self.database.database_url:
            existing = next(
                (item for item in self.memory["learning"] if item["effective_date"] == state["effective_date"]),
                None,
            )
            if existing:
                return dict(existing)
            payload = {**state, "created_at": datetime.now(timezone.utc)}
            self.memory["learning"].append(payload)
            return dict(payload)
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO r2d2_learning_states
                       (id, experiment_id, effective_date, version, sample_days, sample_trades,
                        parameters, metrics, rationale)
                   VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb)
                   ON CONFLICT (experiment_id, effective_date) DO NOTHING""",
                (str(uuid4()), experiment_id, state["effective_date"], state["version"],
                 state["sample_days"], state["sample_trades"], json.dumps(state["parameters"]),
                 json.dumps(state["metrics"]), json.dumps(state["rationale"])),
            )
            row = connection.execute(
                """SELECT version, effective_date, sample_days, sample_trades,
                          parameters, metrics, rationale, created_at
                   FROM r2d2_learning_states
                   WHERE experiment_id=%s AND effective_date=%s""",
                (experiment_id, state["effective_date"]),
            ).fetchone()
            connection.commit()
        keys = ("version", "effective_date", "sample_days", "sample_trades",
                "parameters", "metrics", "rationale", "created_at")
        return dict(zip(keys, row))

    def in_cooldown(self, experiment_id: str, market: str, symbol: str, since: datetime) -> bool:
        if not self.database.database_url:
            return any(
                row["experiment_id"] == experiment_id
                and row["market"] == market and row["symbol"] == symbol
                and row["executed_at"] >= since
                for row in self.memory["trades"]
            )
        with self.database.connection() as connection:
            row = connection.execute(
                """SELECT 1 FROM r2d2_trades
                   WHERE experiment_id=%s AND market=%s AND symbol=%s AND executed_at >= %s
                   LIMIT 1""",
                (experiment_id, market, symbol, since),
            ).fetchone()
        return bool(row)

    def loss_exit_on_session(self, experiment_id: str, market: str, symbol: str,
                             session_date: date) -> bool:
        """True if a full exit realized a LOSS for this symbol so far this session.

        Only a loss-side exit blocks same-day re-entry -- repeatedly buying
        back into a setup that just got stopped out is the churn this guard
        exists to prevent. A profit-taking exit (tactical/weekly harvest,
        armed profit lock) does not block: every one of those exit reasons
        says the capital was "released for same-cycle replacement" -- a
        blanket same-day block on the same symbol directly contradicted that
        stated intent (see 2026-08-18 investigation). Corrected/phantom
        trades are excluded, matching trade_summary()'s exclusion.
        """
        if not self.database.database_url:
            return any(
                row["experiment_id"] == experiment_id
                and row["market"] == market and row["symbol"] == symbol
                and row["side"] == "SELL"
                and row["executed_at"].astimezone(SAO_PAULO).date() == session_date
                and _float(row.get("realized_pnl_usd")) <= 0
                and not _trade_is_corrected(row)
                for row in self.memory["trades"]
            )
        with self.database.connection() as connection:
            row = connection.execute(
                """SELECT 1 FROM r2d2_trades
                   WHERE experiment_id=%s AND market=%s AND symbol=%s AND side='SELL'
                     AND (executed_at AT TIME ZONE 'America/Sao_Paulo')::date=%s
                     AND realized_pnl_usd <= 0
                     AND NOT (decision_snapshot ? 'correction')
                   LIMIT 1""",
                (experiment_id, market, symbol, session_date),
            ).fetchone()
        return bool(row)

    def start_cycle(self, experiment_id: str, markets: list[str], status: str = "running") -> str:
        cycle_id = str(uuid4())
        payload = {"id": cycle_id, "experiment_id": experiment_id, "started_at": datetime.now(timezone.utc),
                   "completed_at": None, "status": status, "markets": markets, "scanned_count": 0,
                   "signal_count": 0, "trade_count": 0, "error_summary": None}
        if not self.database.database_url:
            self.memory["cycles"].append(payload)
            return cycle_id
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO r2d2_cycles (id, experiment_id, started_at, status, markets)
                   VALUES (%s,%s,%s,%s,%s::jsonb)""",
                (cycle_id, experiment_id, payload["started_at"], status, json.dumps(markets)),
            )
            connection.commit()
        return cycle_id

    def finish_cycle(self, cycle_id: str, status: str, scanned: int, signals: int, trades: int,
                     error: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        now = datetime.now(timezone.utc)
        if not self.database.database_url:
            item = next((row for row in self.memory["cycles"] if row["id"] == cycle_id), None)
            if item:
                item.update(completed_at=now, status=status, scanned_count=scanned,
                            signal_count=signals, trade_count=trades, error_summary=error,
                            metadata=metadata or {})
            return
        with self.database.connection() as connection:
            connection.execute(
                """UPDATE r2d2_cycles SET completed_at=%s, status=%s, scanned_count=%s,
                          signal_count=%s, trade_count=%s, error_summary=%s, metadata=%s::jsonb WHERE id=%s""",
                (now, status, scanned, signals, trades, error, json.dumps(metadata or {}), cycle_id),
            )
            connection.commit()

    def last_cycle(self, experiment_id: str) -> dict[str, Any] | None:
        if not self.database.database_url:
            matches = [
                item for item in self.memory["cycles"]
                if item["experiment_id"] == experiment_id
                and not item.get("metadata", {}).get("risk_monitor")
            ]
            return dict(matches[-1]) if matches else None
        with self.database.connection() as connection:
            row = connection.execute(
                """SELECT status, started_at, completed_at, scanned_count, signal_count,
                          trade_count, error_summary FROM r2d2_cycles
                   WHERE experiment_id=%s
                     AND NOT (COALESCE(metadata, '{}'::jsonb) ? 'risk_monitor')
                   ORDER BY started_at DESC LIMIT 1""",
                (experiment_id,),
            ).fetchone()
        if not row:
            return None
        return dict(zip(("status", "started_at", "completed_at", "scanned_count", "signal_count",
                         "trade_count", "error_summary"), row))


class R2D2PaperService:
    def __init__(self, settings: Settings, database: Database, realtime: RealtimeMarketsService,
                 b3_screener: B3ScreenerService, one_pagers: OnePagerService) -> None:
        self.settings = settings
        self.repo = R2D2Repository(database)
        self.realtime = realtime
        self.b3_screener = b3_screener
        self.one_pagers = one_pagers
        self._us_basis: dict[str, tuple[date, dict[str, Any], float]] = {}
        self._us_backfill_attempted: dict[str, date] = {}
        self._us_scan_counts: dict[str, dict[str, int]] = {}
        self._intraday_cache: dict[tuple[str, str], tuple[datetime, list[dict[str, Any]]]] = {}
        self._fx_cache: tuple[datetime, float] | None = None
        self._eodhd_call_counts: dict[str, int] = {}
        self._ws_core_symbols: list[str] = []
        self._ws_rotation_symbols: list[str] = []
        self._ws_rotation_cursor = 0
        self._ws_rotation_age = 0
        self._fmp_quote_cache: dict[str, tuple[datetime, dict[str, Any] | None]] = {}
        self._technical_review_stats: dict[str, Any] = {}
        self._active_policy = dict(BASE_ENTRY_POLICY)
        self._learning_state: dict[str, Any] | None = None
        self._fast_risk_seen_ticks: dict[tuple[str, str], datetime] = {}

    def ensure_initialized(self) -> dict[str, Any]:
        experiment = self.repo.ensure_experiment(self.settings)
        if not self.repo.snapshots(experiment["id"]):
            self.repo.save_snapshot(
                experiment["id"], experiment["start_date"], _float(experiment["starting_capital"]),
                _float(experiment["cash_balance"]), 0.0, 0, False,
            )
        self._ensure_daily_learning(experiment, datetime.now(SAO_PAULO).date())
        return experiment

    def _ensure_daily_learning(self, experiment: dict[str, Any], effective_date: date) -> dict[str, Any]:
        states = self.repo.learning_states(experiment["id"])
        current = next((item for item in reversed(states) if item["effective_date"] == effective_date), None)
        if current:
            self._active_policy = {**BASE_ENTRY_POLICY, **dict(current["parameters"])}
            self._learning_state = current
            return current

        previous = states[-1] if states else None
        parameters = {**BASE_ENTRY_POLICY, **(dict(previous["parameters"]) if previous else {})}
        snapshots = [
            item for item in self.repo.snapshots(experiment["id"])
            if item.get("is_final") and item["session_date"] < effective_date
        ][-30:]
        exits = [
            item for item in self.repo.trades(experiment["id"], limit=250)
            if item.get("realized_pnl_usd") is not None
            and item["executed_at"].astimezone(SAO_PAULO).date() < effective_date
            and not _trade_is_corrected(item)
        ][:50]
        returns = [_float(item["daily_return_percent"]) for item in snapshots]
        realized = [_float(item["realized_pnl_usd"]) for item in exits]
        wins = [value for value in realized if value > 0]
        losses = [value for value in realized if value < 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = min(99.0, gross_profit / gross_loss) if gross_loss else (99.0 if gross_profit else 0.0)
        peak = 0.0
        max_drawdown = 0.0
        for item in snapshots:
            nav = _float(item["nav_usd"])
            peak = max(peak, nav)
            if peak:
                max_drawdown = max(max_drawdown, (peak - nav) / peak * 100)
        metrics = {
            "win_rate_percent": round(len(wins) / len(realized) * 100, 2) if realized else 0.0,
            "average_daily_return_percent": round(statistics.mean(returns), 4) if returns else 0.0,
            "profit_factor": round(profit_factor, 3),
            "max_drawdown_percent": round(max_drawdown, 3),
        }
        rationale: list[str] = []
        if previous is None:
            rationale.append("Baseline policy registered before the first autonomous session.")
        elif len(snapshots) < 5 or len(realized) < 8:
            rationale.append("Daily evidence recorded; parameters held until at least 5 sessions and 8 completed exits exist.")
        elif metrics["win_rate_percent"] < 45 or profit_factor < 1.0 or max_drawdown > 4.0:
            parameters.update({
                "entry_upside_floor": parameters["entry_upside_floor"] + 0.5,
                "max_risk_score": parameters["max_risk_score"] - 0.5,
                "max_buy_in_distance": parameters["max_buy_in_distance"] - 0.5,
                "min_technical_score": parameters["min_technical_score"] + 0.5,
                "min_composite_score": parameters["min_composite_score"] + 0.5,
            })
            rationale.append("Risk gates tightened after weak realized outcomes or elevated drawdown.")
        elif metrics["win_rate_percent"] >= 60 and profit_factor >= 1.35 and max_drawdown <= 2.5:
            parameters.update({
                "entry_upside_floor": parameters["entry_upside_floor"] - 0.25,
                "max_buy_in_distance": parameters["max_buy_in_distance"] + 0.25,
                "min_technical_score": parameters["min_technical_score"] - 0.25,
                "min_composite_score": parameters["min_composite_score"] - 0.25,
            })
            rationale.append("Entry gates widened marginally after persistent positive risk-adjusted outcomes.")
        else:
            rationale.append("Daily review completed; evidence did not justify a parameter change.")
        parameters = {
            key: round(max(ENTRY_POLICY_BOUNDS[key][0], min(ENTRY_POLICY_BOUNDS[key][1], value)), 2)
            for key, value in parameters.items()
        }
        state = self.repo.save_learning_state(experiment["id"], {
            "version": int(previous["version"]) + 1 if previous else 1,
            "effective_date": effective_date,
            "sample_days": len(snapshots),
            "sample_trades": len(realized),
            "parameters": parameters,
            "metrics": metrics,
            "rationale": rationale,
        })
        self._active_policy = dict(state["parameters"])
        self._learning_state = state
        return state

    def dashboard(self) -> R2D2DashboardResponse:
        experiment = self.ensure_initialized()
        positions = self.repo.positions(experiment["id"])
        stream = getattr(self.realtime, "stream", None)
        if stream:
            stream.set_group(
                "r2d2-dashboard",
                [row["symbol"] for row in positions if row["market"] in ACTIVE_MARKETS],
                priority=140,
            )
        cash = _float(experiment["cash_balance"])
        now = datetime.now(timezone.utc)
        display_marks: dict[tuple[str, str], tuple[float, str, datetime | None]] = {}
        for row in positions:
            stored_price = _float(row["last_price_local"])
            tick = stream.quote(row["symbol"]) if stream and row["market"] in ACTIVE_MARKETS else None
            if (
                tick
                and self._live_us_quote(tick, now)
                and stored_price > 0
                and abs(tick.price / stored_price - 1) <= 0.35
            ):
                display_marks[(row["market"], row["symbol"])] = (tick.price, "live", tick.as_of)
            else:
                display_marks[(row["market"], row["symbol"])] = (
                    stored_price,
                    "stored",
                    row.get("updated_at"),
                )
        exposure = sum(
            _float(row["quantity"])
            * display_marks[(row["market"], row["symbol"])][0]
            * _float(row["fx_to_usd"], 1)
            for row in positions
        )
        nav = cash + exposure
        snapshots = self.repo.snapshots(experiment["id"])
        local_date = datetime.now(SAO_PAULO).date()
        current = next((row for row in reversed(snapshots) if row["session_date"] <= local_date), None)
        daily_pnl = _float(current.get("daily_pnl_usd")) if current else 0.0
        daily_return = _float(current.get("daily_return_percent")) if current else 0.0
        daily_pnl_date = current["session_date"].isoformat() if current else None
        cumulative_pnl = sum(
            _float(row.get("daily_pnl_usd"))
            for row in snapshots
            if row["session_date"] <= local_date
        )
        starting_capital = _float(experiment["starting_capital"])
        accounting_nav = starting_capital + cumulative_pnl
        closed = [row for row in snapshots if row.get("is_final")]
        positives = sum(_float(row["daily_return_percent"]) > 0 for row in closed)
        negatives = sum(_float(row["daily_return_percent"]) < 0 for row in closed)
        trade_summary = self.repo.trade_summary(experiment["id"])
        learning_curve_rows = self.repo.daily_learning_curve(experiment["id"])
        stats = R2D2SummaryStats(
            closed_days=len(closed), positive_days=positives,
            above_half_percent_days=sum(_float(row["daily_return_percent"]) >= 0.5 for row in closed),
            negative_days=negatives,
            below_minus_half_percent_days=sum(_float(row["daily_return_percent"]) <= -0.5 for row in closed),
            flat_days=sum(abs(_float(row["daily_return_percent"])) < 1e-9 for row in closed),
            win_rate_percent=round(positives / len(closed) * 100, 2) if closed else 0.0,
            **trade_summary,
        )
        position_models = []
        for row in positions:
            strategy = dict(row.get("strategy_snapshot") or {})
            technical = dict(strategy.get("live_technical") or strategy.get("technical_indicators") or {})
            logo_url = str(strategy.get("logo_url") or "").strip() or None
            if not logo_url and row["market"] in ACTIVE_MARKETS:
                logo_url = f"https://eodhd.com/img/logos/US/{str(row['symbol']).lower()}.png"
            display_price, quote_status, quote_as_of = display_marks[(row["market"], row["symbol"])]
            market_value = _float(row["quantity"]) * display_price * _float(row["fx_to_usd"], 1)
            cost = _float(row["quantity"]) * _float(row["average_cost_usd"])
            pnl = market_value - cost
            decision_state = str(strategy.get("decision_state") or "monitor")
            if quote_status == "live" and decision_state == "awaiting live quote":
                decision_state = "live monitoring"
            position_models.append(R2D2Position(
                market=row["market"], symbol=row["symbol"], name=row["name"], logo_url=logo_url,
                currency=row["currency"],
                quantity=_float(row["quantity"]), average_cost_local=_float(row["average_cost_local"]),
                last_price_local=display_price, market_value_usd=round(market_value, 2),
                unrealized_pnl_usd=round(pnl, 2), unrealized_return_percent=round(pnl / cost * 100, 6) if cost else 0,
                allocation_percent=round(market_value / nav * 100, 2) if nav else 0,
                stop_price_local=_float(row["stop_price_local"]),
                technical_score=_float(technical.get("score")),
                trend_state=str(technical.get("trend_state") or "pending"),
                volume_state=str(technical.get("volume_state") or "pending"),
                data_status=str(technical.get("data_status") or "pending"),
                decision_state=decision_state,
                quote_status=quote_status,
                quote_as_of=quote_as_of,
                technical_as_of=technical.get("as_of"),
                opened_at=row["opened_at"], updated_at=row["updated_at"],
            ))
        trades = [R2D2Trade(
            id=row["id"], market=row["market"], symbol=row["symbol"], name=row["name"], side=row["side"],
            quantity=_float(row["quantity"]), signal_price_local=_float(row["signal_price_local"]),
            fill_price_local=_float(row["fill_price_local"]), currency="BRL" if row["market"] == "B3" else "USD",
            gross_value_usd=_float(row["gross_value_usd"]), fees_usd=_float(row["fees_usd"]),
            slippage_usd=_float(row["slippage_usd"]),
            realized_pnl_usd=_float(row["realized_pnl_usd"]) if row.get("realized_pnl_usd") is not None else None,
            realized_return_percent=_realized_return_percent(
                gross_value_usd=row["gross_value_usd"], fees_usd=row["fees_usd"],
                realized_pnl_usd=row.get("realized_pnl_usd"),
            ),
            reason=row["reason"], executed_at=row["executed_at"], quote_as_of=row["quote_as_of"],
        ) for row in self.repo.trades(experiment["id"])]
        last_cycle = self.repo.last_cycle(experiment["id"])
        today = datetime.now(SAO_PAULO).date()
        learning = self._learning_state or self._ensure_daily_learning(experiment, today)
        return R2D2DashboardResponse(
            experiment_code=experiment["code"], status=experiment["status"],
            methodology_version=experiment["methodology_version"], start_date=experiment["start_date"].isoformat(),
            checkpoint_date=experiment["checkpoint_date"].isoformat(),
            checkpoint_reached=today >= experiment["checkpoint_date"],
            checkpoint_days=(experiment["checkpoint_date"] - experiment["start_date"]).days + 1,
            operating_days_elapsed=max(0, (today - experiment["start_date"]).days + 1),
            starting_capital_usd=starting_capital, nav_usd=round(nav, 2),
            accounting_nav_usd=round(accounting_nav, 2), cumulative_pnl_usd=round(cumulative_pnl, 2),
            cash_usd=round(cash, 2),
            gross_exposure_usd=round(exposure, 2),
            total_return_percent=round((accounting_nav / starting_capital - 1) * 100, 4),
            daily_pnl_usd=round(daily_pnl, 2), daily_return_percent=round(daily_return, 4),
            daily_pnl_date=daily_pnl_date,
            open_positions=len(positions), stats=stats,
            track_record=[R2D2TrackPoint(
                session_date=row["session_date"].isoformat(), nav_usd=_float(row["nav_usd"]),
                daily_pnl_usd=_float(row["daily_pnl_usd"]), daily_return_percent=_float(row["daily_return_percent"]),
                is_final=bool(row["is_final"]),
            ) for row in snapshots],
            learning_curve=[R2D2LearningCurvePoint(
                session_date=row["session_date"].isoformat(),
                positive_percent=round(row["positive"] / (row["positive"] + row["negative"]) * 100, 1),
                positive_trades=row["positive"], negative_trades=row["negative"],
            ) for row in learning_curve_rows],
            positions=position_models, trades=trades,
            last_cycle=R2D2CycleStatus(**last_cycle) if last_cycle else None,
            learning=R2D2LearningState(
                version=int(learning["version"]), effective_date=learning["effective_date"].isoformat(),
                sample_days=int(learning["sample_days"]), sample_trades=int(learning["sample_trades"]),
                parameters={key: _float(value) for key, value in dict(learning["parameters"]).items()},
                metrics={key: _float(value) for key, value in dict(learning["metrics"]).items()},
                rationale=list(learning["rationale"]),
            ),
            mandate=dict(experiment["mandate"]), generated_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def open_markets(now: datetime) -> list[str]:
        """Markets eligible for candidate screening and new entries."""
        markets: list[str] = []
        us = now.astimezone(NEW_YORK)
        if us.weekday() < 5 and US_SCREENING_START_ET <= us.time() <= US_SCREENING_CUTOFF_ET:
            markets.extend(("NASDAQ", "NYSE"))
        return markets

    @staticmethod
    def risk_markets(now: datetime) -> list[str]:
        """Markets whose positions still require regular-session protection.

        Candidate screening deliberately stops at 15:50 ET. Open positions
        remain exposed through the official close, so the dedicated monitor
        must keep running for those final ten minutes without reopening the
        entry pipeline.
        """
        markets: list[str] = []
        us = now.astimezone(NEW_YORK)
        if us.weekday() < 5 and US_SCREENING_START_ET <= us.time() < US_REGULAR_CLOSE_ET:
            markets.extend(("NASDAQ", "NYSE"))
        return markets

    @staticmethod
    def _seconds_to_us_close(market: str, now: datetime) -> float | None:
        """Seconds remaining until the official 16:00 ET regular close."""
        if market not in ACTIVE_MARKETS:
            return None
        us = now.astimezone(NEW_YORK)
        if us.weekday() >= 5:
            return None
        close = datetime.combine(us.date(), US_REGULAR_CLOSE_ET, tzinfo=NEW_YORK)
        remaining = (close - us).total_seconds()
        return remaining if 0 <= remaining else None

    @staticmethod
    def _b3_session_open(now: datetime) -> bool:
        local = now.astimezone(SAO_PAULO)
        return local.weekday() < 5 and time(10, 10) <= local.time() <= time(17, 50)

    def run_cycle(self, now: datetime | None = None, *, force: bool = False,
                  scan_entries: bool = True) -> R2D2DashboardResponse:
        now = now or datetime.now(timezone.utc)
        experiment = self.ensure_initialized()
        local_day = now.astimezone(SAO_PAULO).date()
        self.repo.finalize_before(experiment["id"], local_day)
        learning = self._ensure_daily_learning(experiment, local_day)
        markets = self.open_markets(now)
        if local_day < experiment["start_date"]:
            cycle_id = self.repo.start_cycle(experiment["id"], [], "scheduled")
            self.repo.finish_cycle(cycle_id, "scheduled", 0, 0, 0)
            return self.dashboard()
        positions_at_start = self.repo.positions(experiment["id"])
        legacy_b3_exit_window = (
            self._b3_session_open(now)
            and any(position["market"] == "B3" for position in positions_at_start)
        )
        if force and not markets:
            markets = list(ACTIVE_MARKETS)
        cycle_markets = [*markets, *(["B3-EXIT-ONLY"] if legacy_b3_exit_window else [])]
        cycle_id = self.repo.start_cycle(
            experiment["id"], cycle_markets,
            "running" if cycle_markets else "market_closed",
        )
        if not cycle_markets:
            self.repo.finish_cycle(cycle_id, "market_closed", 0, 0, 0)
            return self.dashboard()
        scanned = signals = trade_count = 0
        errors: list[str] = []
        try:
            positions = positions_at_start
            stream = getattr(self.realtime, "stream", None)
            if stream:
                stream.set_group(
                    "r2d2-positions",
                    [position["symbol"] for position in positions if position["market"] != "B3"],
                    priority=POSITION_STREAM_PRIORITY,
                )
            quote_map = self._position_quotes(positions, now)
            exit_count = self._mark_and_exit(experiment, cycle_id, positions, quote_map, now)
            trade_count += exit_count
            self._snapshot(experiment, local_day, now)
            positions = self.repo.positions(experiment["id"])
            # Risk checks run every 20 seconds, while candidate scans run every minute.
            # An exit must reopen the opportunity set immediately instead of leaving a
            # vacant slot idle until the next scheduled full scan.
            replacement_scan = exit_count > 0
            if not scan_entries and not replacement_scan:
                self.repo.finish_cycle(cycle_id, "succeeded", 0, 0, trade_count)
                return self.dashboard()
            candidates: list[dict[str, Any]] = []
            self._us_scan_counts = {}
            self._eodhd_call_counts = {}
            for market in ACTIVE_MARKETS:
                if market in markets:
                    candidates.extend(self._us_candidates(market, now))
            scanned = sum(
                self._us_scan_counts.get(market, {}).get(
                    "universe_count",
                    sum(item["market"] == market for item in candidates),
                )
                for market in ACTIVE_MARKETS
                if market in markets
            )
            pre_entry_dashboard = self.dashboard()
            cash_percent = (
                pre_entry_dashboard.cash_usd / pre_entry_dashboard.nav_usd * 100
                if pre_entry_dashboard.nav_usd else 100.0
            )
            deployment_mode = cash_percent > self.settings.r2d2_max_cash_percent
            self._enrich_technicals(
                candidates,
                review_limit=(
                    self.settings.r2d2_deployment_technical_review_per_market
                    if deployment_mode
                    else self.settings.r2d2_standard_technical_review_per_market
                ),
                max_ws_symbols=(
                    max(0, stream.max_symbols - len({
                        position["symbol"] for position in positions if position["market"] != "B3"
                    }))
                    if stream else None
                ),
            )
            for candidate in candidates:
                candidate["learning_version"] = int(learning["version"])
                candidate["entry_policy"] = dict(self._active_policy)
            candidates.sort(key=lambda item: item["composite_score"], reverse=True)
            orders_today = sum(
                row["executed_at"].astimezone(SAO_PAULO).date() == local_day
                for row in self.repo.trades(experiment["id"], limit=500)
            )
            for candidate in candidates:
                if candidate.get("technical_reviewed") is False:
                    continue
                if orders_today >= self.settings.r2d2_max_daily_orders:
                    break
                if any(row["market"] == candidate["market"] and row["symbol"] == candidate["symbol"] for row in positions):
                    continue
                if len(positions) >= self.settings.r2d2_max_positions:
                    rotation_trades = self._rotate_if_better(
                        experiment, cycle_id, candidate, positions, quote_map, now,
                    )
                    if rotation_trades:
                        trade_count += rotation_trades
                        orders_today += rotation_trades
                        signals += 1
                        positions = self.repo.positions(experiment["id"])
                    continue
                if self.repo.loss_exit_on_session(
                    experiment["id"], candidate["market"], candidate["symbol"], local_day,
                ):
                    self.repo.save_decision(
                        experiment["id"], cycle_id, candidate, "REJECT",
                        ["A loss exit already executed for this symbol in this session; capital must rotate to another opportunity"],
                    )
                    continue
                cooldown_since = now - timedelta(minutes=self.settings.r2d2_trade_cooldown_minutes)
                if self.repo.in_cooldown(
                    experiment["id"], candidate["market"], candidate["symbol"], cooldown_since,
                ):
                    self.repo.save_decision(
                        experiment["id"], cycle_id, candidate, "REJECT",
                        [f"{self.settings.r2d2_trade_cooldown_minutes}-minute re-entry cooldown is active"],
                    )
                    continue
                action, reasons = self._entry_decision(candidate)
                if action != "BUY":
                    self.repo.save_decision(experiment["id"], cycle_id, candidate, action, reasons)
                    continue
                signals += 1
                trade = self._buy(
                    experiment, cycle_id, candidate, positions, now,
                    entry_reasons=reasons,
                )
                if trade:
                    trade_count += 1
                    orders_today += 1
                    positions = self.repo.positions(experiment["id"])
            self._snapshot(experiment, local_day, now)
            self.repo.finish_cycle(cycle_id, "succeeded" if not errors else "partial", scanned, signals, trade_count,
                                   "; ".join(errors)[:1000] or None,
                                   metadata={
                                       "scan_funnel": dict(self._us_scan_counts),
                                       "eodhd_usage": _estimate_eodhd_credits(self._eodhd_call_counts),
                                       "technical_review": dict(self._technical_review_stats),
                                   })
        except Exception as exc:
            logger.exception("R2D2 cycle failed")
            self.repo.finish_cycle(cycle_id, "failed", scanned, signals, trade_count, str(exc)[:1000])
        return self.dashboard()

    def run_risk_monitor_cycle(self, now: datetime | None = None) -> int:
        """Re-evaluate open positions without entering the screening pipeline."""
        now = now or datetime.now(timezone.utc)
        experiment = self.ensure_initialized()
        positions = self.repo.positions(experiment["id"])
        if not positions:
            return 0

        markets = self.risk_markets(now)
        legacy_b3_exit_window = (
            self._b3_session_open(now)
            and any(position["market"] == "B3" for position in positions)
        )
        cycle_markets = [*markets, *(["B3-EXIT-ONLY"] if legacy_b3_exit_window else [])]
        if not cycle_markets:
            return 0

        stream = getattr(self.realtime, "stream", None)
        if stream:
            stream.set_group(
                "r2d2-positions",
                [position["symbol"] for position in positions if position["market"] != "B3"],
                priority=POSITION_STREAM_PRIORITY,
            )

        cycle_id = self.repo.start_cycle(experiment["id"], cycle_markets, "running")
        exits = 0
        monitor_metadata = {
            "risk_monitor": {
                "enabled": True,
                "positions": len(positions),
                "interval_seconds": self.settings.r2d2_risk_monitor_interval_seconds,
            },
        }
        try:
            quotes = self._position_quotes(positions, now)
            exits = self._mark_and_exit(experiment, cycle_id, positions, quotes, now)
            if exits:
                self._snapshot(experiment, now.astimezone(SAO_PAULO).date(), now)
            self.repo.finish_cycle(
                cycle_id, "succeeded", 0, 0, exits,
                metadata=monitor_metadata,
            )
        except Exception as exc:
            logger.exception("R2D2 dedicated risk-monitor cycle failed")
            self.repo.finish_cycle(
                cycle_id, "failed", 0, 0, exits, str(exc)[:1000],
                metadata=monitor_metadata,
            )
        return exits

    def run_fast_risk_watcher_cycle(self, now: datetime | None = None) -> int:
        """Check fresh in-memory ticks for unconditional and confirmed price stops."""
        now = now or datetime.now(timezone.utc)
        experiment = self.ensure_initialized()
        positions = self.repo.positions(experiment["id"])
        if not positions or not self.risk_markets(now):
            return 0
        stream = getattr(self.realtime, "stream", None)
        if not stream:
            return 0
        stream.set_group(
            "r2d2-positions",
            [position["symbol"] for position in positions if position["market"] in ACTIVE_MARKETS],
            priority=POSITION_STREAM_PRIORITY,
        )
        exits = 0
        with self.repo.risk_evaluation_lock(experiment["id"]) as acquired:
            if not acquired:
                return 0
            for position in self.repo.positions(experiment["id"]):
                if position["market"] not in ACTIVE_MARKETS:
                    continue
                quote = stream.quote(position["symbol"])
                if not quote:
                    continue
                tick_as_of = quote.as_of
                if tick_as_of.tzinfo is None:
                    tick_as_of = tick_as_of.replace(tzinfo=timezone.utc)
                else:
                    tick_as_of = tick_as_of.astimezone(timezone.utc)
                tick_age = max(0.0, (now - tick_as_of).total_seconds())
                alert_key = (position["market"], position["symbol"])
                alert_store: set[tuple[str, str, str]] = self.repo.database._r2d2_fast_risk_alerts  # type: ignore[attr-defined]
                if tick_age > self.settings.r2d2_fast_risk_tick_max_age_seconds:
                    stale_key = (*alert_key, "tick")
                    if stale_key not in alert_store:
                        logger.warning(
                            "R2D2 fast watcher skipping stale tick market=%s symbol=%s age=%.1fs",
                            *alert_key, tick_age,
                        )
                        alert_store.add(stale_key)
                    continue
                alert_store.discard((*alert_key, "tick"))
                if self._fast_risk_seen_ticks.get(alert_key) == tick_as_of:
                    continue
                strategy = dict(position.get("strategy_snapshot") or {})
                cached_technical = dict(
                    strategy.get("live_technical") or strategy.get("technical_indicators") or {},
                )
                if self._quote_is_anomalous(position, quote.price, cached_technical, strategy):
                    logger.warning(
                        "R2D2 fast watcher rejected anomalous tick market=%s symbol=%s price=%.6f tick=%s",
                        *alert_key, quote.price, tick_as_of.isoformat(),
                    )
                    continue
                hard_stop = _float(position.get("hard_stop_price_local"))
                if hard_stop <= 0:
                    self.repo.advance_fast_high_water(
                        experiment["id"], position["market"], position["symbol"], price=quote.price,
                    )
                    missing_key = (*alert_key, "hard-stop")
                    if missing_key not in alert_store:
                        logger.warning(
                            "R2D2 fast watcher awaiting hard-stop anchor market=%s symbol=%s",
                            *alert_key,
                        )
                        alert_store.add(missing_key)
                    continue
                alert_store.discard((*alert_key, "hard-stop"))
                atr = _float(position.get("chandelier_atr_local"))
                atr_as_of = position.get("chandelier_atr_as_of")
                atr_age = (
                    max(0.0, (now - atr_as_of.astimezone(timezone.utc)).total_seconds())
                    if isinstance(atr_as_of, datetime) else float("inf")
                )
                rule: str | None = None
                level = hard_stop
                average_cost = _float(position["average_cost_local"])
                exit_slippage_rate = 0.0015 if position["market"] == "B3" else 0.0010
                exit_fee_rate = 0.0006 if position["market"] == "B3" else 0.0004
                mark_pnl_pct = (quote.price / average_cost - 1) * 100
                estimated_net_exit_pnl_pct = r2d2_strategy.estimated_net_exit_pnl_percent(
                    quote.price, average_cost,
                    slippage_rate=exit_slippage_rate, fee_rate=exit_fee_rate,
                )
                if quote.price <= hard_stop:
                    rule = "hard_stop"
                elif (
                    (seconds_to_close := self._seconds_to_us_close(position["market"], now)) is not None
                    and 0 <= seconds_to_close <= r2d2_strategy.END_OF_DAY_PROFIT_EXIT_LEAD_SECONDS
                    and estimated_net_exit_pnl_pct > 0
                ):
                    # Re-evaluated on every distinct fresh tick throughout T-30s.
                    # A position that was negative at 15:59:30 but turns positive
                    # even on the final tick is therefore still liquidated.
                    rule = "end_of_day_positive"
                    level = average_cost
                elif atr <= 0 or atr_age > self.settings.r2d2_fast_risk_atr_max_age_seconds:
                    self.repo.advance_fast_high_water(
                        experiment["id"], position["market"], position["symbol"], price=quote.price,
                    )
                    stale_key = (*alert_key, "atr")
                    if stale_key not in alert_store:
                        logger.warning(
                            "R2D2 fast watcher degraded to hard-stop only market=%s symbol=%s atr_age=%s",
                            *alert_key, f"{atr_age:.1f}s" if atr_age != float("inf") else "missing",
                        )
                        alert_store.add(stale_key)
                    continue
                else:
                    alert_store.discard((*alert_key, "atr"))
                    state = self.repo.observe_fast_risk_tick(
                        experiment["id"], position["market"], position["symbol"],
                        price=quote.price, tick_as_of=tick_as_of,
                    )
                    if not state:
                        continue
                    level = _float(state.get("chandelier_stop_price_local"))
                    if (
                        level > 0 and quote.price <= level
                        and int(state.get("chandelier_confirmation_count") or 0) >= 2
                    ):
                        rule = "chandelier_2tick"
                if not rule:
                    self._fast_risk_seen_ticks[alert_key] = tick_as_of
                    continue
                cycle_id = self.repo.start_cycle(
                    experiment["id"], [position["market"]], "running",
                )
                reason = (
                    f"Fast risk watcher {rule} exit at mark {mark_pnl_pct:+.2f}%, "
                    f"estimated net {estimated_net_exit_pnl_pct:+.2f}% on fresh tick "
                    f"{tick_as_of.isoformat()}; level {level:.4f}."
                )
                candidate = {
                    "market": position["market"], "symbol": position["symbol"],
                    "name": position["name"], "currency": position["currency"],
                    "stop_price": level, "fundamental_score": 0,
                    "technical_score": 0, "risk_score": 0, "composite_score": 0,
                }
                self._sell(
                    experiment, cycle_id, candidate, position, quote,
                    _float(position.get("fx_to_usd"), 1.0), reason,
                    fast_exit_audit={
                        "rule": rule, "level": level, "atr": atr or None,
                        "tick_as_of": tick_as_of,
                    },
                )
                self.repo.finish_cycle(
                    cycle_id, "succeeded", 0, 0, 1,
                    metadata={"fast_risk_watcher": {"rule": rule, "symbol": position["symbol"]}},
                )
                self._fast_risk_seen_ticks[alert_key] = tick_as_of
                exits += 1
        return exits

    def _position_quotes(self, positions: list[dict[str, Any]], now: datetime) -> dict[tuple[str, str], Any]:
        output: dict[tuple[str, str], Any] = {}
        for market in {row["market"] for row in positions}:
            symbols = [row["symbol"] for row in positions if row["market"] == market]
            rows = self.realtime._b3_portfolio_rows(now, symbols) if market == "B3" else self.realtime._us_portfolio_rows(market, now, symbols)
            if market in ACTIVE_MARKETS:
                rows = [self.realtime._apply_stream_row(row) for row in rows]
            output.update({(market, row.symbol): row for row in rows})
        return output

    def _live_us_quote(self, quote: Any, now: datetime) -> bool:
        if str(getattr(quote, "status", "live")) != "live":
            return False
        as_of = getattr(quote, "as_of", None)
        if not isinstance(as_of, datetime):
            return False
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        age_seconds = max(0.0, (now - as_of.astimezone(timezone.utc)).total_seconds())
        return age_seconds <= self.settings.r2d2_live_quote_max_age_seconds

    @staticmethod
    def _risk_priority(position: dict[str, Any], quotes: dict[tuple[str, str], Any]) -> tuple[float, ...]:
        quote = quotes.get((position["market"], position["symbol"]))
        price = _float(getattr(quote, "price", None), _float(position.get("last_price_local")))
        average_cost = _float(position.get("average_cost_local"))
        stop = _float(position.get("stop_price_local"))
        pnl_percent = (price / average_cost - 1) * 100 if price > 0 and average_cost > 0 else 0.0
        stop_buffer_percent = (price / stop - 1) * 100 if price > 0 and stop > 0 else 999.0
        risk_tier = 0.0 if stop_buffer_percent <= 0.25 else (1.0 if pnl_percent < 0 else 2.0)
        return (risk_tier, stop_buffer_percent, pnl_percent)

    def _mark_and_exit(self, experiment: dict[str, Any], cycle_id: str, positions: list[dict[str, Any]],
                       quotes: dict[tuple[str, str], Any], now: datetime) -> int:
        with self.repo.risk_evaluation_lock(experiment["id"]) as acquired:
            if not acquired:
                logger.debug("R2D2 risk evaluation skipped because another loop owns the lock")
                return 0
            # Refresh under the lock so a caller cannot act on a position that
            # the competing loop sold after the caller built its original list.
            current_positions = self.repo.positions(experiment["id"])
            prioritized = sorted(current_positions, key=lambda item: self._risk_priority(item, quotes))
            return self._mark_and_exit_locked(experiment, cycle_id, prioritized, quotes, now)

    def _mark_and_exit_locked(self, experiment: dict[str, Any], cycle_id: str,
                              positions: list[dict[str, Any]],
                              quotes: dict[tuple[str, str], Any], now: datetime) -> int:
        portfolio_daily_return = self.dashboard().daily_return_percent
        market_reference_change = {
            market: statistics.median(changes)
            for market in ACTIVE_MARKETS
            if (changes := [
                _float(getattr(quote, "change_percent", 0.0))
                for (quote_market, _), quote in quotes.items()
                if quote_market == market and getattr(quote, "change_percent", None) is not None
            ])
        }
        exits = 0
        for position in positions:
            quote = quotes.get((position["market"], position["symbol"]))
            if not quote:
                continue
            conversion = _float(position.get("fx_to_usd"), 0.2) if position["market"] == "B3" else 1.0
            strategy = dict(position.get("strategy_snapshot") or {})
            if position["market"] == "B3":
                strategy.update({
                    "decision_state": "exit delayed market",
                    "last_review_at": now.isoformat(),
                    "retirement_policy": "B3 removed from R2D2 intraday execution",
                })
                self.repo.update_mark(
                    experiment["id"], position["market"], position["symbol"], quote.price,
                    conversion, max(_float(position["high_water_price_local"]), quote.price),
                    _float(position["stop_price_local"]), now, strategy,
                    write_high_water=not self.settings.r2d2_fast_risk_watcher_enabled,
                )
                if self._b3_session_open(now):
                    candidate = {
                        "market": position["market"], "symbol": position["symbol"],
                        "name": position["name"], "currency": position["currency"],
                        "stop_price": _float(position["stop_price_local"]),
                        "fundamental_score": 0, "technical_score": 0, "risk_score": 0,
                        "composite_score": 0,
                    }
                    self._sell(
                        experiment, cycle_id, candidate, position, quote, conversion,
                        "B3 position retired: the five-minute delayed feed is incompatible with the R2D2 intraday mandate.",
                    )
                    exits += 1
                continue
            if position["market"] not in ACTIVE_MARKETS:
                continue
            if not self._live_us_quote(quote, now):
                awaiting_since_raw = strategy.get("awaiting_live_quote_since")
                try:
                    awaiting_since = datetime.fromisoformat(awaiting_since_raw) if awaiting_since_raw else now
                except ValueError:
                    awaiting_since = now
                if awaiting_since.tzinfo is None:
                    awaiting_since = awaiting_since.replace(tzinfo=timezone.utc)
                awaiting_minutes = max(0.0, (now - awaiting_since).total_seconds() / 60)
                strategy.update({
                    "decision_state": "awaiting live quote",
                    "last_review_at": now.isoformat(),
                    "quote_status": str(getattr(quote, "status", "unavailable")),
                    "awaiting_live_quote_since": awaiting_since.isoformat(),
                    "awaiting_live_quote_minutes": round(awaiting_minutes, 1),
                })
                grace_exceeded = awaiting_minutes >= self.settings.r2d2_delayed_quote_protection_grace_minutes
                if not grace_exceeded or quote.price <= 0:
                    self.repo.update_mark(
                        experiment["id"], position["market"], position["symbol"],
                        _float(position["last_price_local"]), conversion,
                        _float(position["high_water_price_local"]),
                        _float(position["stop_price_local"]), now, strategy,
                        write_high_water=not self.settings.r2d2_fast_risk_watcher_enabled,
                    )
                    continue
                # Grace period exceeded. Root-caused 2026-08-18: an earlier version of
                # this fallback trusted quote.price purely because status != "live",
                # and that field turned out to sometimes carry genuinely ancient data
                # (observed: a quote timestamped in 2022 and one in April while "today"
                # was August) rather than a merely-delayed live tick -- producing two
                # exits (SPCX, DINO) at wildly wrong prices. The "delayed" label alone
                # does not mean "a few minutes behind"; it can mean "arbitrarily stale
                # cached data of unknown age." So: validate the quote's own as_of
                # timestamp directly before ever using its price for an exit fill,
                # independent of what status string it carries.
                quote_as_of = getattr(quote, "as_of", None)
                quote_age_minutes: float | None = None
                if isinstance(quote_as_of, datetime):
                    as_of_utc = quote_as_of if quote_as_of.tzinfo else quote_as_of.replace(tzinfo=timezone.utc)
                    quote_age_minutes = max(0.0, (now - as_of_utc.astimezone(timezone.utc)).total_seconds() / 60)
                data_trustworthy = (
                    quote_age_minutes is not None
                    and quote_age_minutes <= self.settings.r2d2_delayed_quote_fallback_max_age_minutes
                )
                strategy["quote_data_age_minutes"] = round(quote_age_minutes, 1) if quote_age_minutes is not None else None
                if not data_trustworthy:
                    strategy["decision_state"] = "delayed quote past grace period -- needs manual review"
                    self.repo.update_mark(
                        experiment["id"], position["market"], position["symbol"],
                        _float(position["last_price_local"]), conversion,
                        _float(position["high_water_price_local"]),
                        _float(position["stop_price_local"]), now, strategy,
                        write_high_water=not self.settings.r2d2_fast_risk_watcher_enabled,
                    )
                    continue
                # The quote's own timestamp is recent enough to trust: fall back to
                # the hard stop only -- not the full technical cascade, which needs
                # fresh indicators this feed can't currently supply.
                average_cost = _float(position["average_cost_local"])
                exit_slippage_rate = 0.0015 if position["market"] == "B3" else 0.0010
                exit_fee_rate = 0.0006 if position["market"] == "B3" else 0.0004
                hard_stop = r2d2_strategy.hard_stop_quote_price(
                    average_cost, self.settings.r2d2_max_position_loss_percent,
                    slippage_rate=exit_slippage_rate, fee_rate=exit_fee_rate,
                )
                high_water = max(_float(position["high_water_price_local"]), quote.price)
                if quote.price > hard_stop:
                    self.repo.update_mark(
                        experiment["id"], position["market"], position["symbol"],
                        _float(position["last_price_local"]), conversion, high_water,
                        _float(position["stop_price_local"]), now, strategy,
                        write_high_water=not self.settings.r2d2_fast_risk_watcher_enabled,
                    )
                    continue
                mark_pnl_pct = (quote.price / average_cost - 1) * 100
                estimated_net_exit_pnl_pct = r2d2_strategy.estimated_net_exit_pnl_percent(
                    quote.price, average_cost,
                    slippage_rate=exit_slippage_rate, fee_rate=exit_fee_rate,
                )
                strategy["decision_state"] = "exit"
                self.repo.update_mark(
                    experiment["id"], position["market"], position["symbol"], quote.price,
                    conversion, high_water, _float(position["stop_price_local"]), now, strategy,
                    write_high_water=not self.settings.r2d2_fast_risk_watcher_enabled,
                )
                candidate = {
                    "market": position["market"], "symbol": position["symbol"], "name": position["name"],
                    "currency": position["currency"], "stop_price": hard_stop, "fundamental_score": 0,
                    "technical_score": 0, "risk_score": 0, "composite_score": 0,
                }
                self._sell(
                    experiment, cycle_id, candidate, position, quote, conversion,
                    f"Protective hard-stop exit on a delayed quote at mark {mark_pnl_pct:+.2f}%, "
                    f"estimated net {estimated_net_exit_pnl_pct:+.2f}%: no live "
                    f"quote for {awaiting_minutes:.1f} minutes (grace period "
                    f"{self.settings.r2d2_delayed_quote_protection_grace_minutes:.1f} min); the quote's "
                    f"own timestamp was {quote_age_minutes:.1f} minutes old (within the "
                    f"{self.settings.r2d2_delayed_quote_fallback_max_age_minutes:.0f}-minute trust bound), "
                    "so it was used as a protective backstop rather than leaving the position "
                    f"unprotected. Maximum position-loss policy is {self.settings.r2d2_max_position_loss_percent:.2f}%.",
                )
                exits += 1
                continue
            technical: dict[str, Any]
            try:
                technical = self._technical_snapshot({
                    "market": position["market"], "symbol": position["symbol"],
                    "price": quote.price, "day_change": quote.change_percent or 0.0,
                    "quote_as_of": quote.as_of,
                })
            except Exception as exc:
                technical = dict(strategy.get("live_technical") or strategy.get("technical_indicators") or {})
                technical.update({
                    "data_status": "stale" if technical else "unavailable",
                    "error": f"{type(exc).__name__}: {exc}"[:180],
                    "as_of": now.isoformat(),
                })
            if self._quote_is_anomalous(position, quote.price, technical, strategy):
                strategy.update({
                    "live_technical": technical,
                    "decision_state": "validating quote",
                    "pending_anomaly_price": quote.price,
                    "pending_anomaly_at": now.isoformat(),
                })
                self.repo.update_mark(
                    experiment["id"], position["market"], position["symbol"],
                    _float(position["last_price_local"]), conversion,
                    _float(position["high_water_price_local"]), _float(position["stop_price_local"]),
                    now, strategy,
                    write_high_water=not self.settings.r2d2_fast_risk_watcher_enabled,
                )
                continue
            strategy.pop("pending_anomaly_price", None)
            strategy.pop("pending_anomaly_at", None)
            strategy.pop("awaiting_live_quote_since", None)
            strategy.pop("awaiting_live_quote_minutes", None)
            high_water = max(_float(position["high_water_price_local"]), quote.price)
            average_cost = _float(position["average_cost_local"])
            held_minutes = max(0.0, (now - position["opened_at"]).total_seconds() / 60)
            bearish_votes = sum((
                quote.price < _float(technical.get("vwap"), quote.price),
                quote.price < _float(technical.get("ema8"), quote.price),
                _float(technical.get("ema8")) < _float(technical.get("ema20")),
                _float(technical.get("macd_histogram")) < 0 and _float(technical.get("macd_acceleration")) < 0,
                _float(technical.get("momentum30")) < -0.35,
                str(technical.get("price_structure")) == "breakdown",
            ))
            failed_entry_votes = sum((
                quote.price < _float(technical.get("vwap"), quote.price),
                quote.price < _float(technical.get("ema8"), quote.price),
                _float(technical.get("momentum15")) < 0,
                _float(technical.get("momentum30")) < 0,
                _float(technical.get("macd_histogram")) < 0
                and _float(technical.get("macd_acceleration")) <= 0,
            ))
            defense = self._technical_defense(
                technical=technical,
                price=quote.price,
                day_change=_float(getattr(quote, "change_percent", 0.0)),
                market_change=market_reference_change.get(position["market"], 0.0),
            )
            technical_score = _float(technical.get("score"))
            entry_fundamental = _float(strategy.get("fundamental_score"), 50.0)
            live_composite = round(entry_fundamental * 0.48 + technical_score * 0.52, 2)
            atr = max(_float(technical.get("atr")), quote.price * 0.004)
            weekly_conviction = self._weekly_conviction(
                strategy=strategy,
                technical=technical,
                price=quote.price,
                high_water=high_water,
                atr=atr,
                bearish_votes=bearish_votes,
            )
            risk_state = r2d2_strategy.PositionRiskState(
                defense_streak=int(strategy.get("defense_streak") or 0),
                defense_reductions=int(strategy.get("defense_reductions") or 0),
                stop_breach_count=int(strategy.get("stop_breach_count") or 0),
                profit_harvest_count=int(strategy.get("profit_harvest_count") or 0),
                gain_protection_streak=int(strategy.get("gain_protection_streak") or 0),
            )
            exit_slippage_rate = 0.0015 if position["market"] == "B3" else 0.0010
            exit_fee_rate = 0.0006 if position["market"] == "B3" else 0.0004
            exit_result, risk_state = r2d2_strategy.exit_decision(
                technical=technical,
                quote_price=quote.price,
                average_cost=average_cost,
                high_water=high_water,
                held_minutes=held_minutes,
                day_change=_float(getattr(quote, "change_percent", 0.0)),
                market_change=market_reference_change.get(position["market"], 0.0),
                state=risk_state,
                weekly_conviction_state=weekly_conviction,
                stop_price=_float(position["stop_price_local"]),
                max_position_loss_percent=self.settings.r2d2_max_position_loss_percent,
                soft_loss_exit_percent=self.settings.r2d2_soft_loss_exit_percent,
                seconds_to_close=self._seconds_to_us_close(position["market"], now),
                exit_slippage_rate=exit_slippage_rate,
                exit_fee_rate=exit_fee_rate,
            )
            reason = exit_result.reason
            sell_fraction = exit_result.sell_fraction
            decision_state = exit_result.decision_state
            defense_streak = risk_state.defense_streak
            defense_reductions = risk_state.defense_reductions
            stop_breaches = risk_state.stop_breach_count
            profit_harvest_count = risk_state.profit_harvest_count
            gain_protection_streak = risk_state.gain_protection_streak

            # Mirrors r2d2_strategy.exit_decision's internal stop/pnl math so the
            # live cache can persist the same stop price and telemetry it decided against.
            trailing_distance = atr * 2.5
            trailing = high_water - trailing_distance
            stop = max(_float(position["stop_price_local"]), trailing)
            mark_pnl_pct = (quote.price / average_cost - 1) * 100
            estimated_net_exit_pnl_pct = r2d2_strategy.estimated_net_exit_pnl_percent(
                quote.price, average_cost,
                slippage_rate=exit_slippage_rate, fee_rate=exit_fee_rate,
            )
            mark_peak_pnl_pct = (high_water / average_cost - 1) * 100
            estimated_net_peak_pnl_pct = r2d2_strategy.estimated_net_exit_pnl_percent(
                high_water, average_cost,
                slippage_rate=exit_slippage_rate, fee_rate=exit_fee_rate,
            )
            atr_percent = max(0.0, _float(technical.get("atr_percent")))
            effective_max_loss_percent = max(
                self.settings.r2d2_max_position_loss_percent,
                min(1.5, atr_percent * 2.0),
            )
            hard_stop = r2d2_strategy.hard_stop_quote_price(
                average_cost, effective_max_loss_percent,
                slippage_rate=exit_slippage_rate, fee_rate=exit_fee_rate,
            )
            stop = max(stop, hard_stop)
            self.repo.update_chandelier_anchor(
                experiment["id"], position["market"], position["symbol"],
                atr=atr, hard_stop=hard_stop, as_of=now,
            )
            soft_loss_threshold = max(
                self.settings.r2d2_soft_loss_exit_percent,
                min(0.7, atr_percent * 0.4),
            )
            if estimated_net_peak_pnl_pct >= 8.0:
                stop = max(
                    stop,
                    average_cost * 1.04,
                    high_water - max(atr * 1.5, high_water * 0.0175),
                )
            elif estimated_net_peak_pnl_pct >= 4.0:
                stop = max(
                    stop,
                    average_cost * 1.015,
                    high_water - max(atr * 2.0, high_water * 0.0225),
                )
            elif estimated_net_peak_pnl_pct >= 1.0:
                # A modest winner must not become a loser while its trend remains healthy.
                stop = max(stop, average_cost * 1.003)
            profit_lock_level = max(
                PROFIT_LOCK_FLOOR_PERCENT,
                estimated_net_peak_pnl_pct - PROFIT_PULLBACK_PERCENT,
            )
            strategy.update({
                "live_technical": technical,
                "live_composite_score": live_composite,
                "stop_breach_count": stop_breaches,
                "bearish_votes": bearish_votes,
                "failed_entry_votes": failed_entry_votes,
                "technical_defense": defense,
                "defense_streak": defense_streak,
                "defense_reductions": defense_reductions,
                "gain_protection_streak": gain_protection_streak,
                "held_minutes": round(held_minutes, 1),
                "mark_pnl_percent": round(mark_pnl_pct, 3),
                "estimated_net_exit_pnl_percent": round(estimated_net_exit_pnl_pct, 3),
                "mark_peak_pnl_percent": round(mark_peak_pnl_pct, 3),
                "peak_pnl_percent": round(estimated_net_peak_pnl_pct, 3),
                "profit_trigger_percent": round(max(PROFIT_TRIGGER_PERCENT, effective_max_loss_percent), 3),
                "profit_lock_level_percent": round(profit_lock_level, 3),
                "profit_harvest_count": profit_harvest_count,
                "profit_harvest_fraction": WEEKLY_PROFIT_HARVEST_FRACTION,
                "weekly_conviction_active": weekly_conviction["active"],
                "weekly_conviction_score": weekly_conviction["score"],
                "weekly_conviction_reasons": weekly_conviction["reasons"],
                "daily_objective_percent": DAILY_OBJECTIVE_PERCENT,
                "daily_objective_status": (
                    "reached" if portfolio_daily_return >= DAILY_OBJECTIVE_PERCENT else "in progress"
                ),
                "portfolio_daily_return_percent": round(portfolio_daily_return, 4),
                "quote_status": "live",
                "quote_as_of": quote.as_of.isoformat(),
                "soft_loss_threshold_percent": round(soft_loss_threshold, 3),
                "hard_stop_percent": self.settings.r2d2_max_position_loss_percent,
                "decision_state": "exit" if reason else decision_state,
                "last_review_at": now.isoformat(),
            })
            self.repo.update_mark(
                experiment["id"], position["market"], position["symbol"], quote.price,
                conversion, high_water, stop, now, strategy,
                write_high_water=not self.settings.r2d2_fast_risk_watcher_enabled,
            )
            if reason:
                candidate = {"market": position["market"], "symbol": position["symbol"], "name": position["name"],
                             "currency": position["currency"], "stop_price": stop, "fundamental_score": 0,
                             "technical_score": technical_score, "risk_score": 0,
                             "composite_score": live_composite, "technical_indicators": technical}
                candidate["defense_sell_fraction"] = sell_fraction
                self._sell(
                    experiment, cycle_id, candidate, position, quote, conversion, reason,
                    quantity_fraction=sell_fraction,
                )
                if sell_fraction < 1.0:
                    strategy["decision_state"] = "position reduced"
                    strategy["last_defense_action_at"] = now.isoformat()
                    self.repo.update_mark(
                        experiment["id"], position["market"], position["symbol"], quote.price,
                        conversion, high_water, stop, now, strategy,
                        write_high_water=not self.settings.r2d2_fast_risk_watcher_enabled,
                    )
                exits += 1
        return exits

    @staticmethod
    def _technical_defense(*, technical: dict[str, Any], price: float,
                           day_change: float, market_change: float) -> dict[str, Any]:
        """Weight trend, structure, flow and volatility instead of relying on a raw loss percentage."""
        return r2d2_strategy.technical_defense(
            technical=technical, price=price, day_change=day_change, market_change=market_change,
        )

    @staticmethod
    def _weekly_conviction(*, strategy: dict[str, Any], technical: dict[str, Any],
                           price: float, high_water: float, atr: float,
                           bearish_votes: int) -> dict[str, Any]:
        """Classify a multi-session hold without weakening execution risk controls."""
        return r2d2_strategy.weekly_conviction(
            strategy=strategy, technical=technical, price=price,
            high_water=high_water, atr=atr, bearish_votes=bearish_votes,
        )

    @staticmethod
    def _quote_is_anomalous(position: dict[str, Any], price: float, technical: dict[str, Any],
                            strategy: dict[str, Any]) -> bool:
        previous = _float(position.get("last_price_local"))
        if previous <= 0 or price <= 0:
            return True
        move_percent = abs(price / previous - 1) * 100
        threshold = max(8.0, _float(technical.get("atr_percent"), 1.5) * 5.0)
        if move_percent <= threshold:
            return False
        pending = _float(strategy.get("pending_anomaly_price"))
        return not pending or abs(price / pending - 1) > 0.012

    def _b3_candidates(self) -> list[dict[str, Any]]:
        response = self.b3_screener.matrix()
        output = []
        for item in response.items:
            # Matrix remains the fundamental source of truth, but the execution
            # engine needs a wider funnel than the displayed top-ten table.
            if item.signal_quality != "validated":
                continue
            if item.tp_upside_percent < 10 or item.risk_score > 60:
                continue
            output.append({
                "market": "B3", "symbol": item.symbol, "name": item.name, "currency": "BRL",
                "logo_url": item.logo_url,
                "price": item.price, "quote_as_of": item.as_of, "upside": item.tp_upside_percent,
                "buy_in_distance": item.price_vs_buy_in_percent, "risk_score": item.risk_score,
                "fundamental_score": min(100.0, item.power_score),
                "technical_score": self._day_technical_score(item.change_percent or 0.0),
                "technical_validated": False, "day_change": item.change_percent or 0.0,
                "confidence": item.valuation_confidence, "stop_price": item.price * 0.955,
                "thesis": f"Validated C3PO TP {item.our_tp:.2f}; upside {item.tp_upside_percent:.1f}%; risk {item.risk_score:.0f}/100.",
            })
        for item in output:
            item["composite_score"] = self._composite(item)
        return sorted(output, key=lambda item: item["composite_score"], reverse=True)[:40]

    def _us_candidates(self, market: str, now: datetime) -> list[dict[str, Any]]:
        rows = self.realtime._us_investable_rows(market, now)
        catalog = self.realtime._us_symbol_catalog(now)
        catalog_securities = [
            (symbol, metadata)
            for symbol, metadata in catalog.items()
            if self.realtime._portfolio_catalog_market(metadata) == market
            and self.realtime._is_portfolio_security(metadata)
        ]
        classified: list[tuple[Any, str]] = []
        for row in rows:
            metadata = catalog.get(row.symbol) or {}
            security_type = canonical_us_security_type(
                row.symbol,
                metadata.get("Type") or metadata.get("type"),
            )
            classified.append((row, security_type))

        eligible: list[tuple[Any, str]] = []
        for row, security_type in classified:
            minimum_cash_volume = US_ETF_MIN_CASH_VOLUME if security_type == "ETF" else US_STOCK_MIN_CASH_VOLUME
            if row.price < 3 or row.cash_volume < minimum_cash_volume:
                continue
            eligible.append((row, security_type))

        # Every symbol that clears the price/liquidity bar gets deep evaluation --
        # no additional volume-ranked cap. The rank_key ordering is kept so that,
        # if evaluation capacity is ever constrained upstream, the most liquid
        # names are still reviewed first.
        rank_key = lambda item: item[0].cash_volume * (  # noqa: E731
            1 + max(-2.0, min(6.0, item[0].change_percent)) / 20
        )
        stocks = sorted(
            (item for item in eligible if item[1] == "Stock"),
            key=rank_key,
            reverse=True,
        )
        etfs = sorted(
            (item for item in eligible if item[1] == "ETF"),
            key=rank_key,
            reverse=True,
        )
        shortlist = [*stocks, *etfs]
        self._us_scan_counts[market] = {
            "universe_count": len(catalog_securities),
            "quoted_count": len(classified),
            "missing_quote_count": max(0, len(catalog_securities) - len(classified)),
            "tradeable_count": len(eligible),
            "stock_count": sum(
                canonical_us_security_type(
                    symbol,
                    metadata.get("Type") or metadata.get("type"),
                ) == "Stock"
                for symbol, metadata in catalog_securities
            ),
            "etf_count": sum(
                canonical_us_security_type(
                    symbol,
                    metadata.get("Type") or metadata.get("type"),
                ) == "ETF"
                for symbol, metadata in catalog_securities
            ),
            "deep_shortlist_count": len(shortlist),
        }
        if not shortlist:
            return []

        snapshot = self.repo.database.latest_analysis_snapshot(
            "valuation_universe", f"{market}_UNIVERSE",
        )
        snapshot_outputs = snapshot.get("outputs") if snapshot and isinstance(snapshot.get("outputs"), dict) else {}
        snapshot_rows = snapshot_outputs.get("rows") if isinstance(snapshot_outputs.get("rows"), list) else []
        canonical = {
            str(item.get("symbol") or "").upper(): item
            for item in snapshot_rows
            if isinstance(item, dict) and item.get("symbol")
        }

        today = now.date()
        missing = [
            row.symbol
            for row, security_type in stocks
            if row.symbol not in canonical
            and (row.symbol not in self._us_basis or self._us_basis[row.symbol][0] != today)
            and self._us_backfill_attempted.get(row.symbol) != today
        ][:US_FUNDAMENTAL_BACKFILL_PER_CYCLE]
        if missing and self.one_pagers is not None:
            self._us_backfill_attempted.update({symbol: today for symbol in missing})
            client = EodhdClient(
                self.settings.eodhd_base_url,
                self.settings.eodhd_api_token,
                self.one_pagers.market_data.http,
            )
            fundamentals = client.fundamentals(missing, exchange="US", workers=8)
            histories = client.histories(missing, exchange="US", days=365, workers=8)
            self._eodhd_call_counts["backfill_fundamentals_symbols"] = (
                self._eodhd_call_counts.get("backfill_fundamentals_symbols", 0) + len(missing)
            )
            self._eodhd_call_counts["backfill_history_symbols"] = (
                self._eodhd_call_counts.get("backfill_history_symbols", 0) + len(missing)
            )
            quote_by_symbol = {row.symbol: row for row, _ in shortlist}
            for symbol in missing:
                row = quote_by_symbol.get(symbol)
                fundamental = fundamentals.get(symbol)
                history = histories.get(symbol, [])
                if not row or not fundamental or len(history) < 40:
                    continue
                try:
                    analysis = self.one_pagers._analyze(
                        symbol, "US", {"price": row.price, "currency": "USD", "as_of": row.as_of,
                                        "change_percent": row.change_percent}, fundamental, history,
                    )
                except Exception:
                    continue
                operating_quality = clamp(
                    50
                    + (normalized_percent(fundamental.get("returnOnEquity")) or 0) * 0.45
                    + (normalized_percent(fundamental.get("profitMargins")) or 0) * 0.30,
                    20, 95,
                )
                self._us_basis[symbol] = (today, analysis, operating_quality)

        output: list[dict[str, Any]] = []
        for row, security_type in shortlist:
            canonical_row = canonical.get(row.symbol)
            cached = self._us_basis.get(row.symbol)
            # Root-caused 2026-08-20: B3 candidates already require
            # signal_quality == "validated" (b3_screener.py's stricter gate)
            # before R2D2 will trade on them; this US path had no equivalent
            # check and would happily use a "provisional" canonical row --
            # the same lower-confidence tier B3 explicitly excludes from
            # Candidate Stocks / Last Jedi. A provisional row now falls
            # through to the same-day backfill / technical-only tiers below
            # instead of being trusted directly.
            if canonical_row and canonical_row.get("signal_quality") != "validated":
                canonical_row = None
            if canonical_row:
                c3po_tp = _float(canonical_row.get("our_tp"))
                upside = (c3po_tp / row.price - 1) * 100 if c3po_tp else 0.0
                risk = _float(canonical_row.get("risk_score"), 55.0)
                confidence = _float(canonical_row.get("valuation_confidence"), 55.0)
                buy_in = _float(canonical_row.get("buy_in"))
                distance = (row.price / buy_in - 1) * 100 if buy_in else 0.0
                fundamental_score = _float(canonical_row.get("score"), 50.0)
                thesis = str(canonical_row.get("thesis") or "Canonical C3PO valuation evidence.")
                basis_source = "canonical C3PO valuation universe"
            elif cached:
                analysis = cached[1]
                c3po_tp = _float(analysis.get("c3po_tp"))
                upside = (c3po_tp / row.price - 1) * 100 if c3po_tp else _float(analysis.get("upside_percent"))
                risk = _float(analysis.get("risk_score"), 55.0)
                confidence = _float(analysis.get("confidence"), 55.0)
                buy_in = _float(analysis.get("buy_in"))
                distance = (row.price / buy_in - 1) * 100 if buy_in else 0.0
                fundamental_score = USScreeningService._power_score(
                    upside, risk, cached[2], confidence, distance,
                )
                thesis = f"C3PO TP {c3po_tp:.2f}; valuation backfill completed for the current session."
                basis_source = "same-day C3PO valuation backfill"
            else:
                minimum_cash_volume = US_ETF_MIN_CASH_VOLUME if security_type == "ETF" else US_STOCK_MIN_CASH_VOLUME
                liquidity_score = max(
                    40.0,
                    min(95.0, 48.0 + math.log10(max(row.cash_volume / minimum_cash_volume, 1.0)) * 18.0),
                )
                day_score = self._day_technical_score(row.change_percent)
                risk = max(38.0, min(70.0, 58.0 + abs(row.change_percent) * 1.4 - (liquidity_score - 50) * 0.18))
                confidence = max(40.0, min(58.0, 42.0 + (liquidity_score - 40) * 0.22))
                upside = 0.0
                distance = 0.0
                c3po_tp = 0.0
                fundamental_score = max(40.0, min(62.0, 36.0 + liquidity_score * 0.30 + day_score * 0.12))
                thesis = (
                    f"Full-exchange {security_type.lower()} scan; live technical confirmation is required "
                    "before any paper order because canonical valuation evidence is not yet available."
                )
                basis_source = "full-exchange provisional technical scan"

            minimum_cash_volume = US_ETF_MIN_CASH_VOLUME if security_type == "ETF" else US_STOCK_MIN_CASH_VOLUME
            liquidity_score = max(
                0.0,
                min(100.0, 50.0 + math.log10(max(row.cash_volume / minimum_cash_volume, 1.0)) * 20.0),
            )
            day_score = self._day_technical_score(row.change_percent)
            item = {
                "market": market, "symbol": row.symbol, "name": row.name, "currency": "USD",
                "logo_url": f"https://eodhd.com/img/logos/US/{row.symbol.lower()}.png",
                "security_type": security_type,
                "price": row.price, "quote_as_of": row.as_of, "upside": upside,
                "buy_in_distance": distance, "risk_score": risk, "fundamental_score": fundamental_score,
                "technical_score": day_score, "confidence": confidence,
                "technical_validated": False, "day_change": row.change_percent,
                "technical_reviewed": False,
                "quote_status": row.status,
                "stop_price": row.price * (1 - self.settings.r2d2_max_position_loss_percent / 100),
                "thesis": thesis,
                "valuation_basis": basis_source,
            }
            item["composite_score"] = self._composite(item)
            item["pretrade_rank"] = round(
                item["composite_score"] * 0.45 + day_score * 0.35 + liquidity_score * 0.20,
                3,
            )
            output.append(item)
        return sorted(output, key=lambda item: item["pretrade_rank"], reverse=True)

    def _enrich_technicals(self, candidates: list[dict[str, Any]], *, review_limit: int = 16,
                           max_ws_symbols: int | None = None) -> None:
        """Confirm entry timing with five-minute candles for the best fundamental names."""
        selected: list[dict[str, Any]] = []
        review_sets: list[list[dict[str, Any]]] = []
        for market in ("B3", "NASDAQ", "NYSE"):
            rows = sorted(
                (item for item in candidates if item["market"] == market),
                key=lambda item: item.get("pretrade_rank", item["fundamental_score"]), reverse=True,
            )[:max(1, review_limit)]
            for item in rows:
                item["technical_reviewed"] = True
            review_sets.append(rows)
        for index in range(max((len(rows) for rows in review_sets), default=0)):
            for rows in review_sets:
                if index < len(rows):
                    selected.append(rows[index])
        rotation_stats: dict[str, Any] = {}
        if max_ws_symbols is not None:
            # Root-caused 2026-08-19: NASDAQ/NYSE technical confirmation requires a
            # live EODHD WebSocket tick (see _technical_snapshot's data_status gate --
            # the REST intraday endpoint alone can lag over a day and must never be
            # treated as "live"). The stream carries at most max_symbols tickers
            # total, with open positions reserved first by the caller; requesting
            # more review slots than remain here just guarantees a chunk of
            # candidates get zero chance at a tick and fail as "confirmation
            # unavailable" every cycle, regardless of how liquid they actually are.
            # Trim to what the stream can actually carry, ranked by pretrade rank
            # across both markets combined, and mark the rest not-reviewed so they
            # cleanly wait for a future cycle instead of being evaluated on stale
            # default technicals.
            ws_bound = sorted(
                (item for item in selected if item["market"] != "B3"),
                key=lambda item: item.get("pretrade_rank", item["fundamental_score"]), reverse=True,
            )
            ws_bound, fmp_stats = self._fmp_prefilter_ws_candidates(ws_bound)
            ws_selected, rotation_stats = self._rotating_ws_batch(
                ws_bound,
                max(0, max_ws_symbols),
            )
            rotation_stats = {**rotation_stats, **fmp_stats}
            selected_ids = {id(item) for item in ws_selected}
            overflow = [item for item in ws_bound if id(item) not in selected_ids]
            for item in overflow:
                item["technical_reviewed"] = False
            dropped = {id(item) for item in overflow}
            selected = [item for item in selected if id(item) not in dropped]
        stream = getattr(self.realtime, "stream", None)
        if stream:
            stream.set_group(
                "r2d2-analysis",
                [item["symbol"] for item in selected if item["market"] != "B3"],
                priority=110,
            )
        market_changes = {
            market: statistics.median([item["day_change"] for item in candidates if item["market"] == market])
            for market in ("B3", "NASDAQ", "NYSE")
            if any(item["market"] == market for item in candidates)
        }
        for item in selected:
            try:
                if item["market"] in ACTIVE_MARKETS and stream:
                    live_quote = stream.quote(item["symbol"])
                    if live_quote:
                        item["price"] = live_quote.price
                        item["quote_as_of"] = live_quote.as_of
                        item["quote_status"] = (
                            "live" if self._live_us_quote(live_quote, datetime.now(timezone.utc))
                            else "stale"
                        )
                snapshot = self._technical_snapshot(item)
                relative_strength = item["day_change"] - market_changes.get(item["market"], 0.0)
                score = snapshot["score"] + max(-8.0, min(8.0, relative_strength * 3.0))
                item["technical_score"] = round(max(0.0, min(100.0, score)), 2)
                item["technical_validated"] = (
                    snapshot.get("data_status") == "live"
                    and item.get("quote_status") == "live"
                )
                item["technical_indicators"] = {**snapshot, "relative_strength": round(relative_strength, 3)}
                stop_distance = min(
                    item["price"] * self.settings.r2d2_max_position_loss_percent / 100,
                    max(snapshot["atr"] * 0.45, item["price"] * 0.004),
                )
                item["stop_price"] = item["price"] - stop_distance
                item["composite_score"] = self._composite(item)
            except Exception as exc:
                item["technical_error"] = f"{type(exc).__name__}: {exc}"[:240]
                item["technical_score"] = 0.0
                item["technical_validated"] = False
                item["composite_score"] = self._composite(item)

        us_selected = [item for item in selected if item["market"] in ACTIVE_MARKETS]
        live_usable = sum(bool(item.get("technical_validated")) for item in us_selected)
        self._technical_review_stats = {
            "eligible_count": rotation_stats.get("rotation_eligible_count", len(us_selected)),
            "subscribed_count": len(us_selected),
            "live_usable_count": live_usable,
            "live_usable_percent": round(live_usable / len(us_selected) * 100, 2) if us_selected else 0.0,
            **rotation_stats,
        }

    def _fmp_prefilter_ws_candidates(
        self,
        candidates: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Use FMP batch quotes to promote live candidates before EODHD slots.

        This changes subscription order only. It neither replaces the EODHD
        tick used for technical validation nor changes any entry/exit/risk
        threshold. Missing or failed FMP data falls back to the existing
        pretrade ranking so the secondary provider can never stop R2D2.
        """
        stats: dict[str, Any] = {
            "fmp_prefilter_enabled": bool(self.settings.r2d2_fmp_prefilter_enabled),
            "fmp_prefilter_candidate_count": len(candidates),
            "fmp_prefilter_quote_count": 0,
            "fmp_prefilter_fresh_count": 0,
            "fmp_prefilter_cache_hit_count": 0,
            "fmp_prefilter_fetched_symbol_count": 0,
            "fmp_prefilter_failed_chunk_count": 0,
            "fmp_prefilter_fallback": False,
        }
        if (
            not candidates
            or not self.settings.r2d2_fmp_prefilter_enabled
            or not self.settings.fmp_api_token
            or self.one_pagers is None
        ):
            stats["fmp_prefilter_fallback"] = True
            return candidates, stats

        now = datetime.now(timezone.utc)
        symbols = [item["symbol"] for item in candidates]
        quotes: dict[str, dict[str, Any]] = {}
        cache_ttl = max(1, self.settings.r2d2_fmp_prefilter_cache_seconds)
        missing: list[str] = []
        negative_cache_count = 0
        for symbol in symbols:
            cached = self._fmp_quote_cache.get(symbol)
            if not cached or (now - cached[0]).total_seconds() > cache_ttl:
                missing.append(symbol)
                continue
            cached_quote = cached[1]
            if cached_quote is None:
                negative_cache_count += 1
            else:
                quotes[symbol] = cached_quote
        stats["fmp_prefilter_cache_hit_count"] = len(symbols) - len(missing)
        stats["fmp_prefilter_cache_coverage_percent"] = round(
            (len(symbols) - len(missing)) / len(symbols) * 100, 2,
        ) if symbols else 0.0
        stats["fmp_prefilter_negative_cache_count"] = negative_cache_count

        if missing:
            client = FmpClient(
                self.settings.fmp_base_url,
                self.settings.fmp_api_token,
                self.one_pagers.market_data.http,
            )
            diagnostics: dict[str, Any] = {}
            fetched_quotes = client.batch_quotes(
                missing,
                chunk_size=self.settings.r2d2_fmp_prefilter_batch_size,
                diagnostics=diagnostics,
            )
            quotes.update(fetched_quotes)
            failed_symbols = set(diagnostics.get("failed_symbols") or [])
            successful_symbols = set(diagnostics.get("successful_symbols") or [])
            for symbol in successful_symbols:
                self._fmp_quote_cache[symbol] = (now, fetched_quotes.get(symbol))
            stats["fmp_prefilter_fetched_symbol_count"] = len(missing)
            stats["fmp_prefilter_failed_chunk_count"] = int(
                diagnostics.get("failed_chunk_count") or 0
            )
            stats["fmp_prefilter_failed_symbol_count"] = len(failed_symbols)
            stats["fmp_prefilter_failure_types"] = diagnostics.get("failure_types") or []
            if failed_symbols:
                logger.warning(
                    "FMP prefilter degraded: %s chunks / %s symbols failed (%s)",
                    stats["fmp_prefilter_failed_chunk_count"],
                    len(failed_symbols),
                    ", ".join(stats["fmp_prefilter_failure_types"]) or "unknown error",
                )

        # Bound memory across changing universes without invalidating current
        # negative-cache entries during their useful TTL.
        if len(self._fmp_quote_cache) > 5_000:
            self._fmp_quote_cache = {
                symbol: cached for symbol, cached in self._fmp_quote_cache.items()
                if (now - cached[0]).total_seconds() <= cache_ttl
            }

        max_age = max(1, self.settings.r2d2_fmp_prefilter_max_quote_age_seconds)
        fresh_symbols: set[str] = set()
        for symbol, quote in quotes.items():
            timestamp = int(_float(quote.get("timestamp")))
            if timestamp <= 0:
                continue
            quote_at = datetime.fromtimestamp(timestamp, timezone.utc)
            if -5 <= (now - quote_at).total_seconds() <= max_age:
                fresh_symbols.add(symbol)
        stats["fmp_prefilter_quote_count"] = len(quotes)
        stats["fmp_prefilter_fresh_count"] = len(fresh_symbols)
        if not fresh_symbols:
            stats["fmp_prefilter_fallback"] = True
            return candidates, stats

        # FMP freshness is a promotion tier, not a new eligibility gate.
        # Existing pretrade_rank remains the complete ordering inside each
        # tier, and unconfirmed names stay in the deterministic rotation tail.
        ranked = sorted(
            candidates,
            key=lambda item: (
                item["symbol"] in fresh_symbols,
                item.get("pretrade_rank", item["fundamental_score"]),
            ),
            reverse=True,
        )
        return ranked, stats

    def _rotating_ws_batch(
        self,
        candidates: list[dict[str, Any]],
        capacity: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Keep top-ranked names stable while rotating the remaining live slots.

        Replacing the entire analysis group each screening cycle gives newly
        subscribed symbols almost no opportunity to produce a live tick before
        technical validation runs. The core remains subscribed continuously;
        the rotating window advances only after its grace period.
        """
        ranked = sorted(
            candidates,
            key=lambda item: item.get("pretrade_rank", item["fundamental_score"]),
            reverse=True,
        )
        capacity = min(max(0, capacity), len(ranked))
        if capacity == 0:
            self._ws_core_symbols = []
            self._ws_rotation_symbols = []
            self._ws_rotation_cursor = 0
            self._ws_rotation_age = 0
            return [], {
                "rotation_eligible_count": len(ranked),
                "core_count": 0,
                "rotating_count": 0,
                "rotation_pool_count": len(ranked),
                "rotation_window_age_cycles": 0,
                "rotation_grace_cycles": max(1, self.settings.r2d2_ws_rotation_grace_cycles),
            }

        core_percent = max(0.0, min(100.0, self.settings.r2d2_ws_rotation_core_percent))
        core_count = min(capacity, int(round(capacity * core_percent / 100.0)))
        ranked_by_symbol = {item["symbol"]: item for item in ranked}
        retained_core = [
            ranked_by_symbol[symbol]
            for symbol in self._ws_core_symbols
            if symbol in ranked_by_symbol
        ][:core_count]
        retained_symbols = {item["symbol"] for item in retained_core}
        core = list(retained_core)
        for item in ranked:
            if len(core) >= core_count:
                break
            if item["symbol"] in retained_symbols:
                continue
            core.append(item)
            retained_symbols.add(item["symbol"])
        self._ws_core_symbols = [item["symbol"] for item in core]
        core_symbols = set(self._ws_core_symbols)
        tail = [item for item in ranked if item["symbol"] not in core_symbols]
        rotating_capacity = min(capacity - core_count, len(tail))
        tail_by_symbol = {item["symbol"]: item for item in tail}
        grace_cycles = max(1, self.settings.r2d2_ws_rotation_grace_cycles)

        keep_window = (
            self._ws_rotation_symbols
            and self._ws_rotation_age < grace_cycles
            and any(symbol in tail_by_symbol for symbol in self._ws_rotation_symbols)
        )
        if keep_window:
            rotating = [
                tail_by_symbol[symbol]
                for symbol in self._ws_rotation_symbols
                if symbol in tail_by_symbol
            ][:rotating_capacity]
            self._ws_rotation_age += 1
        else:
            if self._ws_rotation_symbols and tail:
                self._ws_rotation_cursor = (
                    self._ws_rotation_cursor + max(1, rotating_capacity)
                ) % len(tail)
            else:
                self._ws_rotation_cursor = 0
            rotating = [
                tail[(self._ws_rotation_cursor + offset) % len(tail)]
                for offset in range(rotating_capacity)
            ] if tail else []
            self._ws_rotation_age = 1

        if len(rotating) < rotating_capacity and tail:
            retained = {item["symbol"] for item in rotating}
            for offset in range(len(tail)):
                item = tail[(self._ws_rotation_cursor + offset) % len(tail)]
                if item["symbol"] in retained:
                    continue
                rotating.append(item)
                retained.add(item["symbol"])
                if len(rotating) >= rotating_capacity:
                    break

        self._ws_rotation_symbols = [item["symbol"] for item in rotating]
        return [*core, *rotating], {
            "rotation_eligible_count": len(ranked),
            "core_count": len(core),
            "core_retained_count": len(retained_core),
            "core_replaced_count": max(0, len(core) - len(retained_core)),
            "rotating_count": len(rotating),
            "rotation_pool_count": len(tail),
            "rotation_cursor": self._ws_rotation_cursor,
            "rotation_window_age_cycles": self._ws_rotation_age,
            "rotation_grace_cycles": grace_cycles,
        }

    def _technical_snapshot(self, item: dict[str, Any]) -> dict[str, Any]:
        live_rows: list[dict[str, Any]] = []
        rows = self._historical_intraday(item)
        if item["market"] != "B3":
            stream = getattr(self.realtime, "stream", None)
            if stream:
                live_rows = stream.bars(item["symbol"], limit=180)
        merged: dict[datetime, dict[str, Any]] = {}
        for row in [*rows, *live_rows]:
            timestamp = self._bar_timestamp(row.get("timestamp"))
            updated_at = self._bar_timestamp(row.get("updated_at")) or timestamp
            close = _float(row.get("close"))
            if timestamp is None or close <= 0:
                continue
            merged[timestamp] = {
                "timestamp": timestamp,
                "open": _float(row.get("open"), close),
                "close": close,
                "high": max(close, _float(row.get("high"), close)),
                "low": min(close, _float(row.get("low"), close)),
                "volume": max(0.0, _float(row.get("volume"))),
                "source": row.get("source") or "historical",
                "updated_at": updated_at,
            }
        bars = [merged[key] for key in sorted(merged)][-180:]
        if len(bars) < 35:
            raise ValueError("fewer than 35 valid five-minute candles")
        current_price = _float(item.get("price"))
        if live_rows and current_price > 0:
            latest = bars[-1]
            latest["close"] = current_price
            latest["high"] = max(_float(latest.get("high"), current_price), current_price)
            latest["low"] = min(_float(latest.get("low"), current_price), current_price)
            latest["source"] = "EODHD Real-Time WebSocket"
            latest["updated_at"] = self._bar_timestamp(item.get("quote_as_of")) or latest["updated_at"]
        closes = [bar["close"] for bar in bars]
        volumes = [bar["volume"] for bar in bars]
        ema8 = self._ema(closes, 8)
        ema12 = self._ema(closes, 12)
        ema20 = self._ema(closes, 20)
        ema26 = self._ema(closes, 26)
        ema50 = self._ema(closes, 50)
        macd_series = [
            self._ema(closes[:index], 12) - self._ema(closes[:index], 26)
            for index in range(26, len(closes) + 1)
        ]
        macd = ema12 - ema26
        macd_signal = self._ema(macd_series, 9)
        macd_histogram = macd - macd_signal
        prior_macd_signal = self._ema(macd_series[:-1], 9) if len(macd_series) > 9 else macd_signal
        prior_macd = macd_series[-2] if len(macd_series) > 1 else macd
        macd_acceleration = macd_histogram - (prior_macd - prior_macd_signal)
        deltas = [current - prior for prior, current in zip(closes[-15:-1], closes[-14:])]
        gains = sum(max(delta, 0.0) for delta in deltas) / 14
        losses = sum(max(-delta, 0.0) for delta in deltas) / 14
        rsi = 100.0 if losses == 0 else 100 - 100 / (1 + gains / losses)
        session_date = bars[-1]["timestamp"].date()
        session_bars = [bar for bar in bars if bar["timestamp"].date() == session_date] or bars[-78:]
        typical = [(bar["high"] + bar["low"] + bar["close"]) / 3 for bar in session_bars]
        session_volumes = [bar["volume"] for bar in session_bars]
        volume_sum = sum(session_volumes)
        vwap = (
            sum(price * volume for price, volume in zip(typical, session_volumes)) / volume_sum
            if volume_sum else statistics.mean([bar["close"] for bar in session_bars])
        )
        true_ranges = []
        for previous, bar in zip(bars[-15:-1], bars[-14:]):
            true_ranges.append(max(
                bar["high"] - bar["low"], abs(bar["high"] - previous["close"]),
                abs(bar["low"] - previous["close"]),
            ))
        atr = statistics.mean(true_ranges) if true_ranges else closes[-1] * 0.02
        median_volume = statistics.median(volumes[-23:-3]) or 1.0
        relative_volume = statistics.mean(volumes[-3:]) / median_volume
        momentum15 = (closes[-1] / closes[-4] - 1) * 100
        momentum30 = (closes[-1] / closes[-7] - 1) * 100
        momentum60 = (closes[-1] / closes[-13] - 1) * 100
        ema8_prior = self._ema(closes[:-3], 8)
        ema20_prior = self._ema(closes[:-3], 20)
        ema8_slope = (ema8 / ema8_prior - 1) * 100 if ema8_prior else 0.0
        ema20_slope = (ema20 / ema20_prior - 1) * 100 if ema20_prior else 0.0
        vwap_distance = (closes[-1] / vwap - 1) * 100 if vwap else 0.0
        prior_high = max(bar["high"] for bar in bars[-21:-1])
        recent = bars[-6:]
        previous_window = bars[-12:-6]
        older_window = bars[-21:-6]
        higher_high = max(bar["high"] for bar in recent) > max(bar["high"] for bar in previous_window)
        higher_low = min(bar["low"] for bar in recent) > min(bar["low"] for bar in previous_window)
        lower_high = max(bar["high"] for bar in recent) < max(bar["high"] for bar in previous_window)
        lower_low = min(bar["low"] for bar in recent) < min(bar["low"] for bar in previous_window)
        failed_breakout = (
            max(bar["high"] for bar in recent) > max(bar["high"] for bar in older_window)
            and closes[-1] < max(bar["high"] for bar in older_window)
            and momentum15 < 0
        )
        if closes[-1] >= prior_high:
            price_structure = "breakout"
        elif closes[-1] < min(bar["low"] for bar in previous_window):
            price_structure = "breakdown"
        elif failed_breakout:
            price_structure = "failed-breakout"
        elif lower_high and lower_low:
            price_structure = "lower-lows"
        elif higher_high and higher_low:
            price_structure = "higher-highs"
        else:
            price_structure = "range"
        obv = [0.0]
        for prior, current, volume in zip(closes[-25:-1], closes[-24:], volumes[-24:]):
            obv.append(obv[-1] + (volume if current > prior else -volume if current < prior else 0.0))
        obv_scale = max(sum(volumes[-12:]), 1.0)
        obv_slope = (obv[-1] - obv[-7]) / obv_scale * 100 if len(obv) >= 7 else 0.0
        positive_flow = negative_flow = 0.0
        flow_bars = bars[-15:]
        flow_typical = [(bar["high"] + bar["low"] + bar["close"]) / 3 for bar in flow_bars]
        for prior, current, bar in zip(flow_typical[:-1], flow_typical[1:], flow_bars[1:]):
            flow = current * bar["volume"]
            if current >= prior:
                positive_flow += flow
            else:
                negative_flow += flow
        mfi = 100.0 if negative_flow == 0 else 100 - 100 / (1 + positive_flow / negative_flow)
        atr_percent = atr / closes[-1] * 100
        recent_high = max(bar["high"] for bar in bars[-13:])
        drawdown_atr = max(0.0, (recent_high - closes[-1]) / max(atr, closes[-1] * 0.001))
        pressure_bars = bars[-6:]
        pressure_volume = sum(bar["volume"] for bar in pressure_bars)
        sell_volume_ratio = (
            sum(bar["volume"] for bar in pressure_bars if bar["close"] < bar["open"]) / pressure_volume
            if pressure_volume else 0.5
        )
        path = sum(abs(current - prior) for prior, current in zip(closes[-13:-1], closes[-12:]))
        trend_efficiency = abs(closes[-1] - closes[-13]) / path if path else 0.0
        trend_score = 50.0
        trend_score += 18 if closes[-1] > vwap else -18
        trend_score += 18 if ema8 > ema20 else -18
        trend_score += 10 if ema20 > ema50 else -10
        trend_score += min(10.0, trend_efficiency * 20) if momentum60 > 0 else -min(10.0, trend_efficiency * 20)
        momentum_score = 50.0
        momentum_score += 12 if 50 <= rsi <= 68 else 5 if 44 <= rsi < 50 else -15 if rsi < 38 or rsi > 78 else -4
        momentum_score += 14 if macd_histogram > 0 else -14
        momentum_score += 10 if macd_acceleration > 0 else -10
        momentum_score += 8 if momentum15 > 0 and momentum30 > 0 else -8
        flow_score = 50.0
        flow_score += 18 if relative_volume >= 1.2 and momentum15 > 0 else -14 if relative_volume >= 1.2 and momentum15 < 0 else 4 if relative_volume >= 0.8 else -8
        flow_score += max(-15.0, min(15.0, obv_slope * 3.0))
        flow_score += 8 if 52 <= mfi <= 78 else -8 if mfi < 35 or mfi > 88 else 0
        structure_score = {
            "breakout": 90.0, "higher-highs": 75.0, "range": 50.0,
            "failed-breakout": 28.0, "lower-lows": 24.0, "breakdown": 12.0,
        }[price_structure]
        volatility_score = 72.0 if 0.25 <= atr_percent <= 3.5 else 48.0 if atr_percent <= 5 else 20.0
        score = (
            max(0.0, min(100.0, trend_score)) * 0.30
            + max(0.0, min(100.0, momentum_score)) * 0.25
            + max(0.0, min(100.0, flow_score)) * 0.20
            + structure_score * 0.15
            + volatility_score * 0.10
        )
        latest_at = bars[-1]["timestamp"]
        has_live = any(bar.get("source") == "EODHD Real-Time WebSocket" for bar in bars[-3:])
        latest_observed_at = max(
            (
                bar.get("updated_at") or bar["timestamp"]
                for bar in bars[-3:]
                if bar.get("source") == "EODHD Real-Time WebSocket"
            ),
            default=latest_at,
        )
        age_minutes = max(0.0, (datetime.now(timezone.utc) - latest_observed_at).total_seconds() / 60)
        data_status = "live" if has_live and age_minutes <= 3 else "near-live" if item["market"] == "B3" and age_minutes <= 20 else "delayed"
        trend_state = "bullish" if trend_score >= 65 else "bearish" if trend_score < 42 else "neutral"
        volume_state = "accumulation" if flow_score >= 65 else "distribution" if flow_score < 40 else "neutral"
        return {
            "score": round(max(0.0, min(100.0, score)), 2), "vwap": round(vwap, 6),
            "ema8": round(ema8, 6), "ema20": round(ema20, 6), "ema50": round(ema50, 6),
            "rsi14": round(rsi, 3), "macd": round(macd, 6), "macd_signal": round(macd_signal, 6),
            "macd_histogram": round(macd_histogram, 6), "macd_acceleration": round(macd_acceleration, 6),
            "momentum15": round(momentum15, 3), "momentum30": round(momentum30, 3),
            "momentum60": round(momentum60, 3),
            "ema8_slope15": round(ema8_slope, 4), "ema20_slope15": round(ema20_slope, 4),
            "vwap_distance_percent": round(vwap_distance, 4),
            "relative_volume": round(relative_volume, 3), "atr": round(atr, 6),
            "atr_percent": round(atr_percent, 3), "obv_slope": round(obv_slope, 3),
            "sell_volume_ratio": round(sell_volume_ratio, 4),
            "drawdown_atr": round(drawdown_atr, 3),
            "mfi14": round(mfi, 3), "trend_efficiency": round(trend_efficiency, 3),
            "price_structure": price_structure, "trend_state": trend_state,
            "volume_state": volume_state, "data_status": data_status,
            "data_age_minutes": round(age_minutes, 1), "as_of": latest_observed_at.isoformat(),
            "trend_score": round(max(0.0, min(100.0, trend_score)), 2),
            "momentum_score": round(max(0.0, min(100.0, momentum_score)), 2),
            "flow_score": round(max(0.0, min(100.0, flow_score)), 2),
        }

    def _historical_intraday(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        """Cache the candle baseline while live ticks keep the active bar current."""
        market = str(item["market"])
        symbol = str(item["symbol"]).upper()
        key = (market, symbol)
        now = datetime.now(timezone.utc)
        ttl = timedelta(minutes=5 if market == "B3" else 60)
        cached = self._intraday_cache.get(key)
        if cached and now - cached[0] < ttl:
            self._eodhd_call_counts["intraday_cache_hits"] = (
                self._eodhd_call_counts.get("intraday_cache_hits", 0) + 1
            )
            return [dict(row) for row in cached[1]]
        if market == "B3":
            rows = BrapiClient(
                self.settings.brapi_base_url, self.settings.brapi_token, self.one_pagers.market_data.http,
            ).intraday(symbol, interval="5m", days=5)
        else:
            self._eodhd_call_counts["intraday_cache_misses"] = (
                self._eodhd_call_counts.get("intraday_cache_misses", 0) + 1
            )
            rows = EodhdClient(
                self.settings.eodhd_base_url, self.settings.eodhd_api_token, self.one_pagers.market_data.http,
            ).intraday(symbol, exchange="US", interval="5m", days=7)
        normalized = [dict(row) for row in rows]
        self._intraday_cache[key] = (now, normalized)
        return [dict(row) for row in normalized]

    @staticmethod
    def _bar_timestamp(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        try:
            if isinstance(value, (int, float)) or str(value).strip().isdigit():
                timestamp = float(value)
                if timestamp > 10_000_000_000:
                    timestamp /= 1000
                return datetime.fromtimestamp(timestamp, tz=timezone.utc)
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError, OSError):
            return None

    @staticmethod
    def _ema(values: list[float], period: int) -> float:
        return r2d2_strategy.ema(values, period)

    @staticmethod
    def _day_technical_score(change: float) -> float:
        # Avoids chasing parabolic moves while rewarding confirmed positive momentum.
        if change < -3 or change > 6:
            return 25.0
        return max(20.0, min(88.0, 52 + change * 8))

    @staticmethod
    def _composite(item: dict[str, Any]) -> float:
        entry = max(0.0, min(100.0, 100 - max(item["buy_in_distance"], 0) * 5))
        return round(item["fundamental_score"] * 0.55 + item["technical_score"] * 0.30 + entry * 0.15, 3)

    def _entry_decision(self, item: dict[str, Any]) -> tuple[str, list[str]]:
        return r2d2_strategy.entry_decision(item, self._active_policy)

    def _target_position_percent(self, item: dict[str, Any], *, cash_overhang_percent: float = 0.0) -> float:
        """Size conviction while reducing capital assigned to risk and volatility."""
        return r2d2_strategy.target_position_percent(
            item, cash_overhang_percent=cash_overhang_percent,
            max_position_percent=self.settings.r2d2_max_position_percent,
        )

    def _rotate_if_better(self, experiment: dict[str, Any], cycle_id: str, candidate: dict[str, Any],
                          positions: list[dict[str, Any]], quotes: dict[tuple[str, str], Any],
                          now: datetime) -> int:
        action, reasons = self._entry_decision(candidate)
        if action != "BUY":
            return 0
        dashboard = self.dashboard()
        candidate_market_exposure = sum(
            position.market_value_usd for position in dashboard.positions
            if position.market == candidate["market"]
        )
        if candidate_market_exposure >= dashboard.nav_usd * self.settings.r2d2_max_market_percent / 100:
            eligible_markets = {candidate["market"]}
        else:
            eligible_markets = set(ACTIVE_MARKETS)
        ranked: list[tuple[float, float, dict[str, Any]]] = []
        for position in positions:
            if position["market"] not in eligible_markets:
                continue
            held_minutes = max(0.0, (now - position["opened_at"]).total_seconds() / 60)
            if held_minutes < ROTATION_MIN_HOLD_MINUTES:
                continue
            strategy = dict(position.get("strategy_snapshot") or {})
            technical = dict(strategy.get("live_technical") or {})
            current_score = _float(
                strategy.get("live_composite_score"),
                _float(strategy.get("composite_score"), 50.0),
            )
            pnl_pct = (
                _float(position["last_price_local"]) / _float(position["average_cost_local"]) - 1
            ) * 100
            technical_score = _float(technical.get("score"), _float(strategy.get("technical_score"), 50.0))
            score_gap = candidate["composite_score"] - current_score
            if bool(strategy.get("weekly_conviction_active")):
                continue
            weak_enough = technical_score < 52 or pnl_pct <= 0.5 or score_gap >= ROTATION_SCORE_GAP + 6
            if score_gap >= ROTATION_SCORE_GAP and weak_enough:
                ranked.append((score_gap, -technical_score, position))
        if not ranked:
            return 0
        score_gap, _, position = max(ranked, key=lambda item: (item[0], item[1]))
        quote = quotes.get((position["market"], position["symbol"]))
        if not quote or not self._live_us_quote(quote, now):
            return 0
        fx = 1 / self._usd_fx(now) if position["market"] == "B3" else 1.0
        reason = (
            f"Opportunity-cost rotation: {candidate['symbol']} scored {candidate['composite_score']:.1f}/100, "
            f"{score_gap:.1f} points above {position['symbol']}; the incumbent's live trend no longer justified the slot."
        )
        exit_item = {
            "market": position["market"], "symbol": position["symbol"], "name": position["name"],
            "currency": position["currency"], "stop_price": _float(position["stop_price_local"]),
            "fundamental_score": 0, "technical_score": 0, "risk_score": 0,
            "composite_score": candidate["composite_score"] - score_gap,
        }
        self._sell(experiment, cycle_id, exit_item, position, quote, fx, reason)
        refreshed = self.repo.positions(experiment["id"])
        trade = self._buy(
            experiment, cycle_id, candidate, refreshed, now,
            entry_reasons=reasons,
        )
        if not trade:
            self.repo.save_decision(
                experiment["id"], cycle_id, candidate, "REJECT",
                [*reasons, "Rotation exit completed, but portfolio capacity blocked the replacement order."],
            )
            return 1
        return 2

    def _buy(self, experiment: dict[str, Any], cycle_id: str, item: dict[str, Any],
             positions: list[dict[str, Any]], now: datetime | None = None,
             *, entry_reasons: list[str] | None = None) -> dict[str, Any] | None:
        if item.get("market") not in ACTIVE_MARKETS or item.get("quote_status") != "live":
            return None
        # Root-caused 2026-08-20: item["price"] was captured during
        # _enrich_technicals, potentially minutes before _buy actually runs
        # (ranking, rotation and cooldown checks all sit in between) -- the
        # same stale-quote class of bug already fixed on the exit side via the
        # Risk Monitor. Re-pull the freshest available tick right before
        # computing the fill so a slow-to-execute BUY doesn't fill on a price
        # the market has already moved past. If no fresh tick is available
        # (e.g. the symbol churned out of the WebSocket subscription), fall
        # back to whatever quote _enrich_technicals captured -- but only if
        # it's still within the same freshness window every other live-quote
        # check in this service uses; otherwise the BUY waits for a cycle
        # where a trustworthy price actually exists instead of filling blind.
        stream = getattr(self.realtime, "stream", None)
        if stream:
            fresh_quote = stream.quote(item["symbol"])
            if fresh_quote is not None:
                item = {**item, "price": fresh_quote.price, "quote_as_of": fresh_quote.as_of}
        # The cycle timestamp can be minutes old by the time ranking and
        # portfolio checks reach this fill. Freshness must be measured against
        # the wall clock at execution, not against the beginning of the cycle.
        fill_now = datetime.now(timezone.utc)
        quote_as_of = item.get("quote_as_of")
        if not isinstance(quote_as_of, datetime):
            return None
        as_of = quote_as_of if quote_as_of.tzinfo else quote_as_of.replace(tzinfo=timezone.utc)
        if (fill_now - as_of).total_seconds() > self.settings.r2d2_live_quote_max_age_seconds:
            return None
        dashboard = self.dashboard()
        if dashboard.daily_return_percent <= -self.settings.r2d2_daily_loss_limit_percent:
            return None
        nav = dashboard.nav_usd
        cash_percent = dashboard.cash_usd / nav * 100 if nav else 100.0
        cash_overhang_percent = max(0.0, cash_percent - self.settings.r2d2_max_cash_percent)
        target_position_percent = self._target_position_percent(
            item, cash_overhang_percent=cash_overhang_percent,
        )
        minimum_position_usd = nav * MIN_POSITION_PERCENT / 100
        market_exposure = sum(position.market_value_usd for position in dashboard.positions if position.market == item["market"])
        max_market = nav * self.settings.r2d2_max_market_percent / 100
        max_gross_percent = min(
            self.settings.r2d2_max_gross_exposure_percent,
            100.0 - self.settings.r2d2_min_cash_buffer_percent,
        )
        max_gross = nav * max_gross_percent / 100
        execution_cost_buffer = nav * 0.0005
        remaining_slots_after_buy = max(0, self.settings.r2d2_max_positions - len(positions) - 1)
        reserved_for_remaining_slots = minimum_position_usd * remaining_slots_after_buy
        portfolio_pacing_capacity = (
            max_gross - dashboard.gross_exposure_usd
            - reserved_for_remaining_slots - execution_cost_buffer
        )
        capacity = min(
            nav * self.settings.r2d2_max_position_percent / 100,
            max_market - market_exposure,
            max_gross - dashboard.gross_exposure_usd - execution_cost_buffer,
            portfolio_pacing_capacity,
            dashboard.cash_usd,
        )
        # Fees and simulated slippage reduce NAV by a few dollars after each fill.
        # A 10% tolerance on the minimum ticket prevents fees and simulated
        # slippage from blocking the final diversification slot while the 95%
        # gross exposure ceiling and 5% cash buffer remain hard.
        if capacity < minimum_position_usd * 0.90:
            return None
        allocation = min(capacity, nav * target_position_percent / 100)
        fx = 1 / self._usd_fx(datetime.now(timezone.utc)) if item["market"] == "B3" else 1.0
        slippage_rate = 0.0015 if item["market"] == "B3" else 0.0010
        fee_rate = 0.0006 if item["market"] == "B3" else 0.0004
        fill = item["price"] * (1 + slippage_rate)
        precision = 1 if item["market"] == "B3" else 100
        quantity = math.floor((allocation / (fill * fx)) * precision) / precision
        if quantity <= 0:
            return None
        gross = quantity * fill * fx
        fees = gross * fee_rate
        slippage = quantity * (fill - item["price"]) * fx
        average_cost_local = (gross + fees) / (quantity * fx)
        atr_percent = max(
            0.0,
            _float((item.get("technical_indicators") or {}).get("atr_percent")),
        )
        effective_max_loss_percent = max(
            self.settings.r2d2_max_position_loss_percent,
            min(1.5, atr_percent * 2.0),
        )
        item = {
            **item,
            "stop_price": max(
                _float(item.get("stop_price")),
                r2d2_strategy.hard_stop_quote_price(
                    average_cost_local, effective_max_loss_percent,
                    slippage_rate=slippage_rate, fee_rate=fee_rate,
                ),
            ),
        }
        actual_position_percent = allocation / nav * 100 if nav else 0.0
        sizing_factors = {
            "composite_score": round(_float(item.get("composite_score")), 2),
            "confidence": round(_float(item.get("confidence")), 2),
            "technical_score": round(_float(item.get("technical_score")), 2),
            "risk_score": round(_float(item.get("risk_score")), 2),
            "atr_percent": round(_float((item.get("technical_indicators") or {}).get("atr_percent"), 2.5), 3),
            "risk_budget_percent": r2d2_strategy.RISK_BUDGET_PERCENT,
        }
        decision = {
            **item,
            "allocation_usd": allocation,
            "target_position_percent": target_position_percent,
            "actual_position_percent": round(actual_position_percent, 3),
            "cash_before_percent": round(cash_percent, 3),
            "cash_ceiling_percent": self.settings.r2d2_max_cash_percent,
            "cash_deployment_mode": cash_overhang_percent > 0,
            "sizing_model": "risk-normalized (Turtle-style)",
            "sizing_factors": sizing_factors,
            "entry_decision_reasons": list(entry_reasons or []),
            "ranking_thesis": item.get("thesis"),
            "paper_only": True,
        }
        sizing_reason = (
            f"Dynamic sizing {actual_position_percent:.2f}% of NAV "
            f"(target {target_position_percent:.2f}%; conviction, risk and ATR adjusted"
            f"{' with cash deployment active' if cash_overhang_percent > 0 else ''})."
        )
        technical_reasons = list(entry_reasons or ["Entry decision approved."])
        execution_reasons = [*technical_reasons, sizing_reason]
        trade = self.repo.execute_trade(
            experiment, cycle_id=cycle_id, candidate=item, side="BUY", quantity=quantity,
            signal_price=item["price"], fill_price=fill, fx=fx, fees=fees, slippage=slippage,
            reason=" ".join(execution_reasons),
            decision=decision, quote_as_of=item["quote_as_of"],
        )
        self.repo.save_decision(
            experiment["id"], cycle_id, decision, "BUY", execution_reasons, trade["id"],
        )
        return trade

    def _sell(self, experiment: dict[str, Any], cycle_id: str, item: dict[str, Any], position: dict[str, Any],
              quote: Any, fx: float, reason: str, *, quantity_fraction: float = 1.0,
              fast_exit_audit: dict[str, Any] | None = None) -> dict[str, Any]:
        slip_rate = 0.0015 if item["market"] == "B3" else 0.0010
        fee_rate = 0.0006 if item["market"] == "B3" else 0.0004
        fill = quote.price * (1 - slip_rate)
        full_quantity = _float(position["quantity"])
        fraction = max(0.0, min(1.0, quantity_fraction))
        quantity = math.floor(full_quantity * fraction * 100) / 100
        if quantity <= 0 or full_quantity - quantity < 0.01:
            quantity = full_quantity
        gross = quantity * fill * fx
        fees = gross * fee_rate
        slippage = quantity * (quote.price - fill) * fx
        trade = self.repo.execute_trade(
            experiment, cycle_id=cycle_id, candidate=item, side="SELL", quantity=quantity,
            signal_price=quote.price, fill_price=fill, fx=fx, fees=fees, slippage=slippage,
            reason=reason, decision={**item, "paper_only": True}, quote_as_of=quote.as_of,
            fast_exit_audit=fast_exit_audit,
        )
        self.repo.save_decision(experiment["id"], cycle_id, item, "SELL", [reason], trade["id"])
        return trade

    def _usd_fx(self, now: datetime) -> float:
        if self._fx_cache and now < self._fx_cache[0]:
            return self._fx_cache[1]
        client = EodhdClient(self.settings.eodhd_base_url, self.settings.eodhd_api_token, self.one_pagers.market_data.http)
        self._eodhd_call_counts["fx_quote_calls"] = self._eodhd_call_counts.get("fx_quote_calls", 0) + 1
        quote = client.quotes(["USDBRL.FOREX"])[0]
        self._fx_cache = (now + timedelta(minutes=10), quote.price)
        return quote.price

    def _snapshot(self, experiment: dict[str, Any], local_day: date, now: datetime) -> None:
        positions = self.repo.positions(experiment["id"])
        exposure = sum(_float(row["quantity"]) * _float(row["last_price_local"]) * _float(row["fx_to_usd"], 1)
                       for row in positions)
        cash = _float(experiment["cash_balance"])
        all_closed = not self.open_markets(now) and now.astimezone(NEW_YORK).time() >= time(16, 5)
        self.repo.save_snapshot(experiment["id"], local_day, cash + exposure, cash, exposure, len(positions), all_closed)
