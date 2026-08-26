from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .r2d2 import _paper_exit_execution
from .r2d2_strategy import estimated_net_exit_pnl_percent, hard_stop_quote_price


NEW_YORK = ZoneInfo("America/New_York")
SAO_PAULO = ZoneInfo("America/Sao_Paulo")
CENT_TOLERANCE_USD = 0.005
QUANTITY_TOLERANCE = 1e-7
OHLC_BOUNDARY_TOLERANCE_MINUTES = 1
OHLC_CLOCK_EXTENDED_BACKWARD_MINUTES = 10
OHLC_COMPATIBILITY_TOLERANCE_BPS = 25.0
OHLC_VIOLATION_EPISODE_LIMIT_PERCENT = 5.0
MARKET_COMPATIBILITY_CLASSES = (
    "contained",
    "clock_extended",
    "tolerance_band",
    "violation",
)
BOOTSTRAP_SEED = 20260824
BOOTSTRAP_ITERATIONS = 10_000
PANEL_I_POLICIES = ("A", "B", "B_PRIME", "C", "C_PRIME")
PANEL_II_POLICIES = ("A_MINUTE", "D", "D_PRIME")


class ExitPolicyStudyError(RuntimeError):
    pass


class ConsistencyGateError(ExitPolicyStudyError):
    def __init__(
        self,
        failures: Sequence[Mapping[str, Any]],
        *,
        gate_payload: Mapping[str, Any] | None = None,
    ) -> None:
        self.failures = [dict(item) for item in failures]
        self.gate_payload = dict(gate_payload or {})
        super().__init__(f"binding consistency gate failed with {len(self.failures)} finding(s)")


@dataclass(frozen=True, slots=True)
class LedgerFill:
    id: str
    market: str
    symbol: str
    name: str
    side: str
    quantity: float
    signal_price_local: float
    fill_price_local: float
    fx_to_usd: float
    gross_value_usd: float
    fees_usd: float
    slippage_usd: float
    realized_pnl_usd: float | None
    reason: str
    decision_snapshot: Mapping[str, Any]
    executed_at: datetime
    quote_as_of: datetime

    def __post_init__(self) -> None:
        if self.executed_at.tzinfo is None or self.quote_as_of.tzinfo is None:
            raise ValueError("ledger timestamps must be timezone-aware")
        if self.side not in {"BUY", "SELL"}:
            raise ValueError(f"unsupported ledger side: {self.side}")
        if min(self.quantity, self.signal_price_local, self.fill_price_local, self.fx_to_usd) <= 0:
            raise ValueError("ledger quantity, prices and FX must be positive")

    @property
    def corrected(self) -> bool:
        return "correction" in self.decision_snapshot

    @property
    def strategy_excluded(self) -> bool:
        return self.corrected or "operator_wind_down" in self.decision_snapshot

    @property
    def minute(self) -> datetime:
        return self.executed_at.astimezone(timezone.utc).replace(second=0, microsecond=0)


@dataclass(frozen=True, slots=True)
class StudyBar:
    symbol: str
    start_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if self.start_at.tzinfo is None:
            raise ValueError("bar timestamp must be timezone-aware")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("bar OHLC must be positive")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("bar OHLC is inconsistent")
        if self.volume < 0:
            raise ValueError("bar volume cannot be negative")

    @property
    def session_date(self) -> date:
        return self.start_at.astimezone(NEW_YORK).date()


@dataclass(frozen=True, slots=True)
class Episode:
    id: str
    market: str
    symbol: str
    name: str
    fills: tuple[LedgerFill, ...]
    opened_at: datetime
    closed_at: datetime | None
    strategy_excluded: bool = False

    @property
    def closed(self) -> bool:
        return self.closed_at is not None

    @property
    def entry_session(self) -> date:
        return self.opened_at.astimezone(NEW_YORK).date()

    @property
    def exit_session(self) -> date | None:
        if self.closed_at is None:
            return None
        return self.closed_at.astimezone(NEW_YORK).date()


@dataclass(slots=True)
class PositionState:
    quantity: float = 0.0
    average_cost_usd: float = 0.0
    fx_to_usd: float = 1.0
    realized_pnl_usd: float = 0.0
    turnover_usd: float = 0.0
    daily_realized_pnl_usd: dict[date, float] = field(default_factory=dict)

    def buy(self, fill: LedgerFill) -> None:
        total_cost = fill.gross_value_usd + fill.fees_usd
        new_quantity = self.quantity + fill.quantity
        self.average_cost_usd = (
            self.quantity * self.average_cost_usd + total_cost
        ) / new_quantity
        self.quantity = new_quantity
        self.fx_to_usd = fill.fx_to_usd
        self.turnover_usd += fill.gross_value_usd

    def actual_sell(self, fill: LedgerFill, *, use_ledger_realized: bool = False) -> float:
        if fill.quantity > self.quantity + QUANTITY_TOLERANCE:
            raise ExitPolicyStudyError(f"episode oversell at ledger fill {fill.id}")
        computed = fill.gross_value_usd - fill.fees_usd - fill.quantity * self.average_cost_usd
        realized = (
            float(fill.realized_pnl_usd)
            if use_ledger_realized and fill.realized_pnl_usd is not None
            else computed
        )
        self._record_realized(realized, fill.executed_at)
        self.turnover_usd += fill.gross_value_usd
        self.quantity = max(0.0, self.quantity - fill.quantity)
        if self.quantity <= QUANTITY_TOLERANCE:
            self.quantity = 0.0
            self.average_cost_usd = 0.0
        return realized

    def synthetic_sell(
        self,
        *,
        market: str,
        quote_price: float,
        at: datetime,
    ) -> dict[str, float]:
        execution = _paper_exit_execution(
            market=market,
            price=quote_price,
            quantity=self.quantity,
            fx=self.fx_to_usd,
        )
        realized = (
            execution["gross_value_usd"]
            - execution["fees_usd"]
            - self.quantity * self.average_cost_usd
        )
        self._record_realized(realized, at)
        self.turnover_usd += execution["gross_value_usd"]
        self.quantity = 0.0
        self.average_cost_usd = 0.0
        return {**execution, "realized_pnl_usd": realized}

    def _record_realized(self, amount: float, at: datetime) -> None:
        session = at.astimezone(SAO_PAULO).date()
        self.realized_pnl_usd += amount
        self.daily_realized_pnl_usd[session] = (
            self.daily_realized_pnl_usd.get(session, 0.0) + amount
        )


@dataclass(frozen=True, slots=True)
class PolicyOutcome:
    episode_id: str
    policy: str
    pnl_usd: float
    turnover_usd: float
    opened_at: datetime
    exited_at: datetime
    exit_reason: str
    synthetic_exit: bool
    daily_realized_pnl_usd: Mapping[date, float]
    marked_close_pnl_usd: Mapping[date, float]
    fidelity_to_observed: Mapping[str, float] | None = None

    @property
    def hold_minutes(self) -> float:
        return max(0.0, (self.exited_at - self.opened_at).total_seconds() / 60.0)


def build_episodes(fills: Iterable[LedgerFill]) -> tuple[list[Episode], dict[str, int]]:
    ordered = sorted(fills, key=lambda item: (item.executed_at, item.id))
    active: dict[tuple[str, str], dict[str, Any]] = {}
    episodes: list[Episode] = []
    counts = {"corrected_rows_excluded": 0, "open_episodes": 0}
    for fill in ordered:
        if fill.corrected:
            counts["corrected_rows_excluded"] += 1
            continue
        key = (fill.market, fill.symbol)
        state = active.get(key)
        if state is None:
            if fill.side != "BUY":
                raise ExitPolicyStudyError(f"SELL {fill.id} begins an episode from flat")
            state = {
                "quantity": 0.0,
                "fills": [],
                "opened_at": fill.executed_at,
                "strategy_excluded": False,
            }
            active[key] = state
        if fill.side == "BUY":
            state["quantity"] += fill.quantity
        else:
            if fill.quantity > state["quantity"] + QUANTITY_TOLERANCE:
                raise ExitPolicyStudyError(f"SELL {fill.id} exceeds episode quantity")
            state["quantity"] = max(0.0, state["quantity"] - fill.quantity)
        state["fills"].append(fill)
        state["strategy_excluded"] = state["strategy_excluded"] or fill.strategy_excluded
        if state["quantity"] <= QUANTITY_TOLERANCE:
            first = state["fills"][0]
            episodes.append(Episode(
                id=f"{fill.market}:{fill.symbol}:{first.id}",
                market=fill.market,
                symbol=fill.symbol,
                name=fill.name,
                fills=tuple(state["fills"]),
                opened_at=state["opened_at"],
                closed_at=fill.executed_at,
                strategy_excluded=bool(state["strategy_excluded"]),
            ))
            del active[key]
    for (market, symbol), state in sorted(active.items()):
        first = state["fills"][0]
        episodes.append(Episode(
            id=f"{market}:{symbol}:{first.id}",
            market=market,
            symbol=symbol,
            name=first.name,
            fills=tuple(state["fills"]),
            opened_at=state["opened_at"],
            closed_at=None,
            strategy_excluded=bool(state["strategy_excluded"]),
        ))
        counts["open_episodes"] += 1
    return sorted(episodes, key=lambda item: (item.opened_at, item.id)), counts


def _bars_by_minute(bars: Sequence[StudyBar]) -> dict[datetime, StudyBar]:
    return {bar.start_at.astimezone(timezone.utc): bar for bar in bars}


def _bar_candidates(
    at: datetime,
    offsets: Sequence[int] = (0, -OHLC_BOUNDARY_TOLERANCE_MINUTES, OHLC_BOUNDARY_TOLERANCE_MINUTES),
) -> tuple[datetime, ...]:
    minute = at.astimezone(timezone.utc).replace(second=0, microsecond=0)
    return tuple(minute + timedelta(minutes=offset) for offset in offsets)


def _candidate_bar_rows(
    fill: LedgerFill,
    bars: Mapping[datetime, StudyBar],
    *,
    extended: bool,
) -> list[tuple[str, int, StudyBar]]:
    if extended:
        anchors = (("quote_as_of", fill.quote_as_of),)
        offsets = tuple(range(0, -OHLC_CLOCK_EXTENDED_BACKWARD_MINUTES - 1, -1)) + (1,)
    else:
        anchors = (
            ("executed_at", fill.executed_at),
            ("quote_as_of", fill.quote_as_of),
        )
        offsets = (0, -OHLC_BOUNDARY_TOLERANCE_MINUTES, OHLC_BOUNDARY_TOLERANCE_MINUTES)
    rows: list[tuple[str, int, StudyBar]] = []
    seen: set[datetime] = set()
    for anchor, at in anchors:
        for offset, minute in zip(offsets, _bar_candidates(at, offsets), strict=True):
            if minute in seen:
                continue
            seen.add(minute)
            bar = bars.get(minute)
            if bar is not None:
                rows.append((anchor, offset, bar))
    return rows


def _price_contained(price: float, bar: StudyBar) -> bool:
    return bar.low <= price <= bar.high


def _breach_bps(price: float, bar: StudyBar) -> float:
    if _price_contained(price, bar):
        return 0.0
    nearest_edge = bar.low if price < bar.low else bar.high
    return abs(price - nearest_edge) / price * 10_000.0


def classify_market_compatibility(
    fill: LedgerFill,
    bars: Mapping[datetime, StudyBar],
) -> dict[str, Any]:
    original = _candidate_bar_rows(fill, bars, extended=False)
    legacy_fill_contained = any(
        anchor == "executed_at" and _price_contained(fill.fill_price_local, bar)
        for anchor, _offset, bar in original
    )
    for anchor, offset, bar in original:
        if _price_contained(fill.signal_price_local, bar):
            return {
                "classification": "contained",
                "legacy_fill_contained": legacy_fill_contained,
                "matched_anchor": anchor,
                "matched_offset_minutes": offset,
                "matched_bar_start_at": bar.start_at.isoformat(),
                "breach_bps": 0.0,
            }

    for anchor, offset, bar in _candidate_bar_rows(fill, bars, extended=True):
        if _price_contained(fill.signal_price_local, bar):
            return {
                "classification": "clock_extended",
                "legacy_fill_contained": legacy_fill_contained,
                "matched_anchor": anchor,
                "matched_offset_minutes": offset,
                "matched_bar_start_at": bar.start_at.isoformat(),
                "breach_bps": 0.0,
            }

    nearest = min(
        original,
        key=lambda row: _breach_bps(fill.signal_price_local, row[2]),
        default=None,
    )
    if nearest is not None:
        anchor, offset, bar = nearest
        breach = _breach_bps(fill.signal_price_local, bar)
        classification = (
            "tolerance_band"
            if breach <= OHLC_COMPATIBILITY_TOLERANCE_BPS
            else "violation"
        )
        return {
            "classification": classification,
            "legacy_fill_contained": legacy_fill_contained,
            "matched_anchor": anchor,
            "matched_offset_minutes": offset,
            "matched_bar_start_at": bar.start_at.isoformat(),
            "reference_low": bar.low,
            "reference_high": bar.high,
            "breach_bps": breach,
        }
    return {
        "classification": "violation",
        "legacy_fill_contained": legacy_fill_contained,
        "matched_anchor": None,
        "matched_offset_minutes": None,
        "matched_bar_start_at": None,
        "breach_bps": None,
    }


def reconcile_binding_gate(
    episodes: Sequence[Episode],
    bars_by_symbol: Mapping[str, Sequence[StudyBar]],
    *,
    constructed_episode_count: int | None = None,
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    checked_fills = 0
    checked_episodes = 0
    compatibility_counts = {name: 0 for name in MARKET_COMPATIBILITY_CLASSES}
    compatibility_by_session: dict[str, dict[str, int]] = defaultdict(
        lambda: {name: 0 for name in MARKET_COMPATIBILITY_CLASSES}
    )
    original_failure_decomposition = {
        "synthetic_fill_vs_signal": 0,
        "clock_extended": 0,
        "tolerance_band": 0,
        "violation": 0,
    }
    violation_fills: list[dict[str, Any]] = []
    violation_episode_ids: set[str] = set()
    for episode in episodes:
        if not episode.closed or episode.strategy_excluded:
            continue
        checked_episodes += 1
        state = PositionState()
        minute_bars = _bars_by_minute(bars_by_symbol.get(episode.symbol, ()))
        for fill in episode.fills:
            checked_fills += 1
            expected_gross = fill.quantity * fill.fill_price_local * fill.fx_to_usd
            slip_rate = 0.0015 if fill.market == "B3" else 0.0010
            fee_rate = 0.0006 if fill.market == "B3" else 0.0004
            expected_fill = fill.signal_price_local * (
                1 + slip_rate if fill.side == "BUY" else 1 - slip_rate
            )
            expected_fee = expected_gross * fee_rate
            expected_slippage = (
                fill.quantity
                * abs(fill.fill_price_local - fill.signal_price_local)
                * fill.fx_to_usd
            )
            checks = {
                "gross_value_usd": (fill.gross_value_usd, expected_gross),
                "fees_usd": (fill.fees_usd, expected_fee),
                "slippage_usd": (fill.slippage_usd, expected_slippage),
            }
            for field_name, (observed, expected) in checks.items():
                if abs(observed - expected) > CENT_TOLERANCE_USD:
                    failures.append({
                        "episode_id": episode.id,
                        "fill_id": fill.id,
                        "gate": field_name,
                        "observed": observed,
                        "expected": expected,
                    })
            if not math.isclose(fill.fill_price_local, expected_fill, rel_tol=0, abs_tol=1e-7):
                failures.append({
                    "episode_id": episode.id,
                    "fill_id": fill.id,
                    "gate": "fill_friction",
                    "observed": fill.fill_price_local,
                    "expected": expected_fill,
                })
            if fill.side == "BUY":
                state.buy(fill)
            else:
                realized = state.actual_sell(fill)
                if fill.realized_pnl_usd is None or abs(fill.realized_pnl_usd - realized) > CENT_TOLERANCE_USD:
                    failures.append({
                        "episode_id": episode.id,
                        "fill_id": fill.id,
                        "gate": "realized_pnl_usd",
                        "observed": fill.realized_pnl_usd,
                        "expected": realized,
                    })
            compatibility = classify_market_compatibility(fill, minute_bars)
            classification = str(compatibility["classification"])
            compatibility_counts[classification] += 1
            session_date = fill.executed_at.astimezone(NEW_YORK).date().isoformat()
            compatibility_by_session[session_date][classification] += 1
            if not compatibility["legacy_fill_contained"]:
                decomposition_class = (
                    "synthetic_fill_vs_signal"
                    if classification == "contained"
                    else classification
                )
                original_failure_decomposition[decomposition_class] += 1
            if classification == "violation":
                violation_episode_ids.add(episode.id)
                violation_fills.append({
                    "episode_id": episode.id,
                    "fill_id": fill.id,
                    "market": fill.market,
                    "symbol": fill.symbol,
                    "side": fill.side,
                    "signal_price_local": fill.signal_price_local,
                    "executed_at": fill.executed_at.isoformat(),
                    "quote_as_of": fill.quote_as_of.isoformat(),
                    "breach_bps": compatibility["breach_bps"],
                    "reference_low": compatibility.get("reference_low"),
                    "reference_high": compatibility.get("reference_high"),
                    "matched_anchor": compatibility["matched_anchor"],
                    "matched_offset_minutes": compatibility["matched_offset_minutes"],
                    "matched_bar_start_at": compatibility["matched_bar_start_at"],
                })
        if state.quantity > QUANTITY_TOLERANCE:
            failures.append({
                "episode_id": episode.id,
                "gate": "flat_to_flat_quantity",
                "remaining_quantity": state.quantity,
            })
    denominator = constructed_episode_count if constructed_episode_count is not None else len(episodes)
    violation_rate_percent = (
        len(violation_episode_ids) / denominator * 100.0 if denominator else 0.0
    )
    threshold_passed = violation_rate_percent <= OHLC_VIOLATION_EPISODE_LIMIT_PERCENT
    if not threshold_passed:
        failures.append({
            "gate": "market_compatibility_violation_rate",
            "violation_episode_count": len(violation_episode_ids),
            "constructed_episode_count": denominator,
            "observed_percent": violation_rate_percent,
            "maximum_percent": OHLC_VIOLATION_EPISODE_LIMIT_PERCENT,
        })
    payload = {
        "passed": not failures,
        "checked_episodes": checked_episodes,
        "checked_fills": checked_fills,
        "money_tolerance_usd": CENT_TOLERANCE_USD,
        "fill_price_tolerance_local": 1e-7,
        "timestamp_boundary_tolerance_minutes": OHLC_BOUNDARY_TOLERANCE_MINUTES,
        "market_compatibility": {
            "price_field": "signal_price_local",
            "class_order": list(MARKET_COMPATIBILITY_CLASSES),
            "counts": compatibility_counts,
            "counts_by_session": {
                session: compatibility_by_session[session]
                for session in sorted(compatibility_by_session)
            },
            "original_failure_decomposition": original_failure_decomposition,
            "original_window_minutes": [-1, 0, 1],
            "clock_extended_window_minutes": [-10, 1],
            "tolerance_band_bps": OHLC_COMPATIBILITY_TOLERANCE_BPS,
            "violation_fills": violation_fills,
            "coverage_censored_episode_ids": sorted(violation_episode_ids),
            "coverage_censored_episode_count": len(violation_episode_ids),
            "constructed_episode_count": denominator,
            "coverage_censored_percent": violation_rate_percent,
            "maximum_coverage_censored_percent": OHLC_VIOLATION_EPISODE_LIMIT_PERCENT,
            "threshold_passed": threshold_passed,
        },
        "failures": failures,
    }
    if failures:
        raise ConsistencyGateError(failures, gate_payload=payload)
    return payload


def observed_outcome(episode: Episode, bars: Sequence[StudyBar]) -> PolicyOutcome:
    if episode.closed_at is None:
        raise ExitPolicyStudyError("observed outcome requires a closed episode")
    state = PositionState()
    for fill in episode.fills:
        if fill.side == "BUY":
            state.buy(fill)
        else:
            state.actual_sell(fill, use_ledger_realized=True)
    if state.quantity > QUANTITY_TOLERANCE:
        raise ExitPolicyStudyError(f"observed episode does not close: {episode.id}")
    return PolicyOutcome(
        episode_id=episode.id,
        policy="A",
        pnl_usd=sum(float(fill.realized_pnl_usd or 0.0) for fill in episode.fills),
        turnover_usd=state.turnover_usd,
        opened_at=episode.opened_at,
        exited_at=episode.closed_at,
        exit_reason=episode.fills[-1].reason,
        synthetic_exit=False,
        daily_realized_pnl_usd=dict(state.daily_realized_pnl_usd),
        marked_close_pnl_usd=_observed_marked_curve(episode, bars),
    )


def _observed_marked_curve(episode: Episode, bars: Sequence[StudyBar]) -> dict[date, float]:
    closes: dict[date, StudyBar] = {}
    for bar in bars:
        if episode.opened_at <= bar.start_at <= (episode.closed_at or bar.start_at):
            closes[bar.session_date] = bar
    state = PositionState()
    curve: dict[date, float] = {}
    fills = iter(episode.fills)
    pending = next(fills, None)
    for session, close_bar in sorted(closes.items()):
        session_end = datetime.combine(session, datetime.max.time(), tzinfo=NEW_YORK)
        while pending and pending.executed_at.astimezone(NEW_YORK) <= session_end:
            if pending.side == "BUY":
                state.buy(pending)
            else:
                state.actual_sell(pending, use_ledger_realized=True)
            pending = next(fills, None)
        unrealized = (
            state.quantity * close_bar.close * state.fx_to_usd
            - state.quantity * state.average_cost_usd
        )
        curve[session] = state.realized_pnl_usd + unrealized
    return curve


def _target_quote(average_cost_usd: float, fx: float, target_net_percent: float, market: str) -> float:
    slip = 0.0015 if market == "B3" else 0.0010
    fee = 0.0006 if market == "B3" else 0.0004
    factor = (1 - slip) * (1 - fee) * fx
    return average_cost_usd * (1 + target_net_percent / 100.0) / factor


def _stop_fill_quote(bar: StudyBar, level: float) -> float | None:
    if bar.open <= level:
        return bar.open
    if bar.low <= level:
        return level
    return None


def _target_fill_quote(bar: StudyBar, level: float) -> float | None:
    if bar.open >= level:
        return bar.open
    if bar.high >= level:
        return level
    return None


def simulate_overlay(
    episode: Episode,
    bars: Sequence[StudyBar],
    policy: str,
) -> PolicyOutcome:
    if policy not in PANEL_I_POLICIES[1:]:
        raise ValueError(f"unsupported overlay policy: {policy}")
    if episode.closed_at is None:
        raise ExitPolicyStudyError("overlay requires a closed episode")
    ordered_bars = [
        bar for bar in sorted(bars, key=lambda item: item.start_at)
        if episode.opened_at.replace(second=0, microsecond=0)
        <= bar.start_at
        <= episode.closed_at.replace(second=0, microsecond=0)
    ]
    last_bar_by_session = _last_bar_map(ordered_bars)
    events: dict[datetime, list[LedgerFill]] = defaultdict(list)
    for fill in episode.fills:
        events[fill.minute].append(fill)
    state = PositionState()
    armed_from: datetime | None = None
    stop_level: float | None = None
    peak_price = 0.0
    actual_final_reason = episode.fills[-1].reason
    marked: dict[date, float] = {}
    synthetic: tuple[datetime, str] | None = None
    for bar in ordered_bars:
        minute_events = sorted(events.get(bar.start_at, ()), key=lambda item: item.executed_at)
        if minute_events:
            for fill in minute_events:
                if fill.side == "BUY":
                    state.buy(fill)
                else:
                    state.actual_sell(fill, use_ledger_realized=True)
            if state.quantity <= QUANTITY_TOLERANCE:
                break
            continue
        if state.quantity <= QUANTITY_TOLERANCE:
            continue
        exit_quote: float | None = None
        reason: str | None = None
        if policy in {"C", "C_PRIME"} and armed_from and bar.start_at >= armed_from and stop_level:
            exit_quote = _stop_fill_quote(bar, stop_level)
            if exit_quote is not None:
                reason = "overlay_breakeven" if policy == "C" else "overlay_trailing_0_40"
        if exit_quote is None and policy in {"B", "B_PRIME"}:
            target = 0.15 if policy == "B" else 0.30
            level = _target_quote(state.average_cost_usd, state.fx_to_usd, target, episode.market)
            exit_quote = _target_fill_quote(bar, level)
            if exit_quote is not None:
                reason = f"overlay_take_profit_{target:.2f}"
        if exit_quote is not None and reason:
            later_buy = any(
                fill.side == "BUY" and fill.executed_at > bar.start_at
                for fill in episode.fills
            )
            if later_buy:
                raise ExitPolicyStudyError(
                    f"overlay exits before a later fixed entry in episode {episode.id}"
                )
            state.synthetic_sell(market=episode.market, quote_price=exit_quote, at=bar.start_at)
            synthetic = (bar.start_at, reason)
            marked[bar.session_date] = state.realized_pnl_usd
            break
        if policy in {"C", "C_PRIME"}:
            activation = _target_quote(state.average_cost_usd, state.fx_to_usd, 0.30, episode.market)
            if armed_from is None and bar.high >= activation:
                armed_from = bar.start_at + timedelta(minutes=1)
                peak_price = bar.high
                stop_level = (
                    _target_quote(state.average_cost_usd, state.fx_to_usd, 0.0, episode.market)
                    if policy == "C"
                    else peak_price * 0.996
                )
            elif policy == "C_PRIME" and armed_from is not None:
                peak_price = max(peak_price, bar.high)
                stop_level = max(float(stop_level or 0.0), peak_price * 0.996)
        if last_bar_by_session.get(bar.session_date) == bar.start_at:
            unrealized = (
                state.quantity * bar.close * state.fx_to_usd
                - state.quantity * state.average_cost_usd
            )
            marked[bar.session_date] = state.realized_pnl_usd + unrealized
    if synthetic is None:
        observed = observed_outcome(episode, bars)
        return PolicyOutcome(
            episode_id=episode.id,
            policy=policy,
            pnl_usd=observed.pnl_usd,
            turnover_usd=observed.turnover_usd,
            opened_at=observed.opened_at,
            exited_at=observed.exited_at,
            exit_reason=actual_final_reason,
            synthetic_exit=False,
            daily_realized_pnl_usd=observed.daily_realized_pnl_usd,
            marked_close_pnl_usd=observed.marked_close_pnl_usd,
        )
    return PolicyOutcome(
        episode_id=episode.id,
        policy=policy,
        pnl_usd=state.realized_pnl_usd,
        turnover_usd=state.turnover_usd,
        opened_at=episode.opened_at,
        exited_at=synthetic[0],
        exit_reason=synthetic[1],
        synthetic_exit=True,
        daily_realized_pnl_usd=dict(state.daily_realized_pnl_usd),
        marked_close_pnl_usd=marked,
    )


def _daily_wilder_atr(
    bars: Sequence[StudyBar],
    *,
    before_session: date,
) -> float | None:
    daily: list[tuple[date, float, float, float]] = []
    grouped: dict[date, list[StudyBar]] = defaultdict(list)
    for bar in bars:
        if bar.session_date < before_session:
            grouped[bar.session_date].append(bar)
    for session, items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: item.start_at)
        daily.append((session, max(item.high for item in ordered), min(item.low for item in ordered), ordered[-1].close))
    if len(daily) < 15:
        return None
    true_ranges: list[float] = []
    previous_close = daily[0][3]
    for _session, high, low, close in daily[1:]:
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
        previous_close = close
    if len(true_ranges) < 14:
        return None
    atr = sum(true_ranges[:14]) / 14.0
    for value in true_ranges[14:]:
        atr = (atr * 13.0 + value) / 14.0
    return atr


def _last_bar_map(bars: Sequence[StudyBar]) -> dict[date, datetime]:
    output: dict[date, datetime] = {}
    for bar in bars:
        output[bar.session_date] = max(output.get(bar.session_date, bar.start_at), bar.start_at)
    return output


def _five_minute_atr_map(bars: Sequence[StudyBar]) -> dict[datetime, float]:
    grouped: dict[tuple[date, int], list[StudyBar]] = defaultdict(list)
    for bar in sorted(bars, key=lambda item: item.start_at):
        local = bar.start_at.astimezone(NEW_YORK)
        minute_index = (local.hour * 60 + local.minute - (9 * 60 + 30)) // 5
        grouped[(bar.session_date, minute_index)].append(bar)
    output: dict[datetime, float] = {}
    for session in sorted({key[0] for key in grouped}):
        chunks = [
            sorted(grouped[key], key=lambda item: item.start_at)
            for key in sorted(grouped)
            if key[0] == session and len(grouped[key]) == 5
        ]
        tr_values: list[float] = []
        previous_close: float | None = None
        atr: float | None = None
        for chunk in chunks:
            high = max(item.high for item in chunk)
            low = min(item.low for item in chunk)
            close = chunk[-1].close
            tr = high - low if previous_close is None else max(
                high - low, abs(high - previous_close), abs(low - previous_close)
            )
            tr_values.append(tr)
            if len(tr_values) == 14:
                atr = sum(tr_values) / 14.0
            elif len(tr_values) > 14 and atr is not None:
                atr = (atr * 13.0 + tr) / 14.0
            if atr is not None:
                output[chunk[-1].start_at] = atr
            previous_close = close
    return output


def simulate_mechanical(
    episode: Episode,
    bars: Sequence[StudyBar],
    policy: str,
    *,
    terminal_sessions: int = 10,
) -> PolicyOutcome | None:
    if policy not in PANEL_II_POLICIES:
        raise ValueError(f"unsupported mechanical policy: {policy}")
    buy_fills = [fill for fill in episode.fills if fill.side == "BUY"]
    if not buy_fills:
        return None
    ordered = [bar for bar in sorted(bars, key=lambda item: item.start_at) if bar.start_at >= episode.opened_at.replace(second=0, microsecond=0)]
    sessions = sorted({bar.session_date for bar in ordered if bar.session_date >= episode.entry_session})
    if not sessions:
        return None
    terminal = sessions[terminal_sessions - 1] if len(sessions) >= terminal_sessions else None
    last_bar_by_session = _last_bar_map(ordered)
    events: dict[datetime, list[LedgerFill]] = defaultdict(list)
    for fill in buy_fills:
        events[fill.minute].append(fill)
    state = PositionState()
    initial_stop = float(
        buy_fills[0].decision_snapshot.get("stop_price")
        or buy_fills[0].decision_snapshot.get("stop_price_local")
        or 0.0
    )
    daily_atr = _daily_wilder_atr(bars, before_session=episode.entry_session)
    if policy == "D_PRIME" and daily_atr is None:
        return None
    atr_map = _five_minute_atr_map(ordered) if policy == "A_MINUTE" else {}
    latest_atr: float | None = None
    stop_level: float | None = None
    high_water = 0.0
    entry_fill_notional_local = 0.0
    entry_quantity = 0.0
    marked: dict[date, float] = {}
    exit_at: datetime | None = None
    exit_reason: str | None = None
    for bar in ordered:
        if terminal is not None and bar.session_date > terminal:
            break
        minute_events = sorted(events.get(bar.start_at, ()), key=lambda item: item.executed_at)
        if minute_events:
            for fill in minute_events:
                if state.quantity <= QUANTITY_TOLERANCE and exit_at is not None:
                    return None
                state.buy(fill)
                entry_fill_notional_local += fill.fill_price_local * fill.quantity
                entry_quantity += fill.quantity
                average_entry_fill_local = entry_fill_notional_local / entry_quantity
                high_water = max(high_water, fill.fill_price_local)
                if policy == "D":
                    stop_level = average_entry_fill_local * 0.992
                elif policy == "D_PRIME":
                    assert daily_atr is not None
                    stop_level = average_entry_fill_local - 1.5 * daily_atr
                else:
                    stop_level = max(stop_level or 0.0, initial_stop)
            continue
        if state.quantity <= QUANTITY_TOLERANCE:
            continue
        if stop_level and (quote := _stop_fill_quote(bar, stop_level)) is not None:
            state.synthetic_sell(market=episode.market, quote_price=quote, at=bar.start_at)
            exit_at = bar.start_at
            exit_reason = f"{policy.lower()}_stop"
            marked[bar.session_date] = state.realized_pnl_usd
            break
        if policy == "A_MINUTE":
            if bar.start_at in atr_map:
                latest_atr = atr_map[bar.start_at]
            high_water = max(high_water, bar.high)
            atr = max(latest_atr or 0.0, bar.close * 0.004)
            atr_percent = atr / bar.close * 100.0
            effective_loss = max(0.65, min(1.5, atr_percent * 2.0))
            hard = hard_stop_quote_price(state.average_cost_usd / state.fx_to_usd, effective_loss)
            chandelier = high_water - atr * 2.5
            candidate = max(initial_stop, hard, chandelier)
            peak_net = estimated_net_exit_pnl_percent(
                high_water, state.average_cost_usd / state.fx_to_usd
            )
            if peak_net >= 8.0:
                candidate = max(candidate, state.average_cost_usd / state.fx_to_usd * 1.04, high_water - max(atr * 1.5, high_water * 0.0175))
            elif peak_net >= 4.0:
                candidate = max(candidate, state.average_cost_usd / state.fx_to_usd * 1.015, high_water - max(atr * 2.0, high_water * 0.0225))
            elif peak_net >= 1.0:
                candidate = max(candidate, state.average_cost_usd / state.fx_to_usd * 1.003)
            stop_level = max(stop_level or 0.0, candidate)
        if last_bar_by_session.get(bar.session_date) == bar.start_at:
            net = estimated_net_exit_pnl_percent(
                bar.close, state.average_cost_usd / state.fx_to_usd
            )
            if net > 0:
                state.synthetic_sell(market=episode.market, quote_price=bar.close, at=bar.start_at)
                exit_at = bar.start_at
                exit_reason = "end_of_day_positive_close_proxy"
                marked[bar.session_date] = state.realized_pnl_usd
                break
            unrealized = (
                state.quantity * bar.close * state.fx_to_usd
                - state.quantity * state.average_cost_usd
            )
            marked[bar.session_date] = state.realized_pnl_usd + unrealized
            if terminal is not None and bar.session_date == terminal:
                state.synthetic_sell(market=episode.market, quote_price=bar.close, at=bar.start_at)
                exit_at = bar.start_at
                exit_reason = f"terminal_{terminal_sessions}_sessions"
                marked[bar.session_date] = state.realized_pnl_usd
                break
    if exit_at is None or exit_reason is None:
        return None
    if any(fill.executed_at > exit_at for fill in buy_fills):
        return None
    outcome = PolicyOutcome(
        episode_id=episode.id,
        policy=policy,
        pnl_usd=state.realized_pnl_usd,
        turnover_usd=state.turnover_usd,
        opened_at=episode.opened_at,
        exited_at=exit_at,
        exit_reason=exit_reason,
        synthetic_exit=True,
        daily_realized_pnl_usd=dict(state.daily_realized_pnl_usd),
        marked_close_pnl_usd=marked,
    )
    if policy != "A_MINUTE" or episode.closed_at is None:
        return outcome
    observed = observed_outcome(episode, bars)
    return PolicyOutcome(
        **{field_name: getattr(outcome, field_name) for field_name in (
            "episode_id", "policy", "pnl_usd", "turnover_usd", "opened_at",
            "exited_at", "exit_reason", "synthetic_exit", "daily_realized_pnl_usd",
            "marked_close_pnl_usd",
        )},
        fidelity_to_observed={
            "pnl_delta_usd": outcome.pnl_usd - observed.pnl_usd,
            "exit_time_delta_minutes": (
                outcome.exited_at - observed.exited_at
            ).total_seconds() / 60.0,
        },
    )


def real_excursions(episode: Episode, bars: Sequence[StudyBar]) -> dict[str, Any]:
    first_buy = next(fill for fill in episode.fills if fill.side == "BUY")
    state = PositionState()
    path = [
        bar for bar in bars
        if first_buy.minute <= bar.start_at <= (episode.closed_at or bar.start_at)
    ]
    if not path:
        raise ExitPolicyStudyError(f"no price path for episode {episode.id}")
    events: dict[datetime, list[LedgerFill]] = defaultdict(list)
    for fill in episode.fills:
        events[fill.minute].append(fill)
    favorable: list[float] = []
    adverse: list[float] = []
    for bar in sorted(path, key=lambda item: item.start_at):
        minute_events = sorted(events.get(bar.start_at, ()), key=lambda item: item.executed_at)
        if minute_events:
            for fill in minute_events:
                if fill.side == "BUY":
                    state.buy(fill)
                else:
                    state.actual_sell(fill, use_ledger_realized=True)
            continue
        if state.quantity <= QUANTITY_TOLERANCE:
            continue
        average_cost_local = state.average_cost_usd / state.fx_to_usd
        favorable.append(estimated_net_exit_pnl_percent(bar.high, average_cost_local))
        adverse.append(estimated_net_exit_pnl_percent(bar.low, average_cost_local))
    if not favorable or not adverse:
        raise ExitPolicyStudyError(f"no event-free excursion bar for episode {episode.id}")
    mfe = max(favorable)
    mae = min(adverse)
    observed = observed_outcome(episode, bars)
    stop_like = any(
        token in observed.exit_reason.lower()
        for token in ("stop", "failed entry", "failed-entry")
    )
    return {
        "episode_id": episode.id,
        "mfe_net_percent": mfe,
        "mae_net_percent": mae,
        "final_pnl_usd": observed.pnl_usd,
        "touched_plus_0_3_then_lost": mfe >= 0.30 and observed.pnl_usd < 0,
        "stop_like_exit": stop_like,
        "minutes_to_exit": observed.hold_minutes,
    }


def _max_drawdown(values: Sequence[float], starting_capital: float) -> float:
    nav = starting_capital
    peak = starting_capital
    worst = 0.0
    for value in values:
        nav += value
        peak = max(peak, nav)
        worst = min(worst, (nav / peak - 1.0) * 100.0 if peak else 0.0)
    return worst


def policy_metrics(outcomes: Sequence[PolicyOutcome], starting_capital: float) -> dict[str, Any]:
    ordered = sorted(outcomes, key=lambda item: (item.exited_at, item.episode_id))
    pnls = [item.pnl_usd for item in ordered]
    wins = [value for value in pnls if value > 0]
    losses = [value for value in pnls if value < 0]
    daily: dict[date, float] = defaultdict(float)
    marked: dict[date, float] = defaultdict(float)
    for outcome in ordered:
        for session, value in outcome.daily_realized_pnl_usd.items():
            daily[session] += value
        for session, value in outcome.marked_close_pnl_usd.items():
            marked[session] += value
    sessions = sorted(set(daily) | set(marked))
    nav = starting_capital
    daily_track = []
    for session in sessions:
        pnl = daily.get(session, 0.0)
        prior_nav = nav
        nav += pnl
        daily_track.append({
            "session_date": session.isoformat(),
            "realized_pnl_usd": pnl,
            "prior_close_accounting_nav_usd": prior_nav,
            "realized_return_percent": pnl / prior_nav * 100.0 if prior_nav else 0.0,
        })
    return {
        "episode_count": len(ordered),
        "total_net_pnl_usd": sum(pnls),
        "win_rate_percent": len(wins) / len(pnls) * 100.0 if pnls else 0.0,
        "average_gain_usd": statistics.fmean(wins) if wins else 0.0,
        "average_loss_usd": statistics.fmean(losses) if losses else 0.0,
        "average_gain_to_loss": (
            statistics.fmean(wins) / abs(statistics.fmean(losses))
            if wins and losses else None
        ),
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "max_realized_drawdown_percent": _max_drawdown(
            [daily.get(session, 0.0) for session in sessions], starting_capital
        ),
        "average_hold_minutes": statistics.fmean(item.hold_minutes for item in ordered) if ordered else 0.0,
        "gross_turnover_usd": sum(item.turnover_usd for item in ordered),
        "days_realized_ge_0_15_percent": sum(
            row["realized_return_percent"] >= 0.15 for row in daily_track
        ) / len(daily_track) * 100.0 if daily_track else 0.0,
        "daily_realized_track": daily_track,
        "marked_economic_curve": _portfolio_marked_curve(ordered, sessions),
    }


def _portfolio_marked_curve(
    outcomes: Sequence[PolicyOutcome],
    sessions: Sequence[date],
) -> list[dict[str, Any]]:
    curve = []
    for session in sessions:
        total = 0.0
        for outcome in outcomes:
            values = outcome.marked_close_pnl_usd
            if session in values:
                total += float(values[session])
                continue
            opened_session = outcome.opened_at.astimezone(NEW_YORK).date()
            exited_session = outcome.exited_at.astimezone(NEW_YORK).date()
            if session >= exited_session:
                total += outcome.pnl_usd
            elif session >= opened_session:
                prior_sessions = sorted(
                    marked_session for marked_session in values if marked_session < session
                )
                if prior_sessions:
                    total += float(values[prior_sessions[-1]])
        curve.append({"session_date": session.isoformat(), "marked_pnl_usd": total})
    return curve


def paired_session_bootstrap(
    baseline: Sequence[PolicyOutcome],
    challenger: Sequence[PolicyOutcome],
    *,
    seed: int = BOOTSTRAP_SEED,
    iterations: int = BOOTSTRAP_ITERATIONS,
) -> dict[str, Any]:
    baseline_by_id = {item.episode_id: item for item in baseline}
    challenger_by_id = {item.episode_id: item for item in challenger}
    if set(baseline_by_id) != set(challenger_by_id):
        raise ExitPolicyStudyError("paired bootstrap requires an identical episode cohort")
    session_blocks: dict[date, list[float]] = defaultdict(list)
    for episode_id, base in baseline_by_id.items():
        candidate = challenger_by_id[episode_id]
        session_blocks[base.opened_at.astimezone(NEW_YORK).date()].append(
            candidate.pnl_usd - base.pnl_usd
        )
    sessions = sorted(session_blocks)
    if not sessions:
        return {
            "paired_episode_count": 0,
            "session_count": 0,
            "mean_delta_usd": 0.0,
            "confidence_interval_95_usd": [0.0, 0.0],
            "seed": seed,
            "iterations": iterations,
        }
    rng = random.Random(seed)
    samples: list[float] = []
    for _ in range(iterations):
        draw = [rng.choice(sessions) for _session in sessions]
        values = [delta for session in draw for delta in session_blocks[session]]
        samples.append(statistics.fmean(values))
    samples.sort()
    lower = samples[int(iterations * 0.025)]
    upper = samples[min(iterations - 1, int(iterations * 0.975))]
    deltas = [value for values in session_blocks.values() for value in values]
    return {
        "paired_episode_count": len(deltas),
        "session_count": len(sessions),
        "mean_delta_usd": statistics.fmean(deltas),
        "confidence_interval_95_usd": [lower, upper],
        "seed": seed,
        "iterations": iterations,
        "unit": "entry_session_block",
    }


def panel_report(
    outcomes_by_policy: Mapping[str, Sequence[PolicyOutcome]],
    *,
    baseline_policy: str,
    starting_capital: float,
) -> dict[str, Any]:
    baseline = list(outcomes_by_policy[baseline_policy])
    metrics = {
        policy: policy_metrics(list(outcomes), starting_capital)
        for policy, outcomes in outcomes_by_policy.items()
    }
    inference = {
        policy: paired_session_bootstrap(baseline, list(outcomes))
        for policy, outcomes in outcomes_by_policy.items()
        if policy != baseline_policy
    }
    sessions = sorted({item.opened_at.astimezone(NEW_YORK).date() for item in baseline})
    classification = "PILOT" if len(sessions) < 15 else "FULL"
    decisions: dict[str, str] = {}
    for policy, result in inference.items():
        if classification == "PILOT":
            decisions[policy] = "PILOT_NO_STRATEGY_PROPOSAL"
            continue
        lower, upper = result["confidence_interval_95_usd"]
        drawdown_not_worse = (
            metrics[policy]["max_realized_drawdown_percent"]
            >= metrics[baseline_policy]["max_realized_drawdown_percent"]
        )
        if lower > 0 and drawdown_not_worse:
            decisions[policy] = "CHALLENGER_DOMINANT_BY_PREREGISTERED_RULE"
        elif upper < 0:
            decisions[policy] = "BASELINE_DOMINANT_BY_PAIRED_PNL"
        else:
            decisions[policy] = "AMBIGUOUS"
    return {
        "baseline_policy": baseline_policy,
        "common_cohort": True,
        "session_count": len(sessions),
        "classification": classification,
        "metrics": metrics,
        "paired_inference": inference,
        "preregistered_decision_readout": decisions,
    }


def excursion_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    stop_rows = [item for item in rows if item["stop_like_exit"]]
    return {
        "episode_count": len(rows),
        "mfe_net_percent": [item["mfe_net_percent"] for item in rows],
        "mae_net_percent": [item["mae_net_percent"] for item in rows],
        "touched_plus_0_3_then_lost_count": sum(
            bool(item["touched_plus_0_3_then_lost"]) for item in rows
        ),
        "churn": {
            "stop_episode_count": len(stop_rows),
            "under_15_minutes_percent": _fraction_under(stop_rows, 15),
            "under_30_minutes_percent": _fraction_under(stop_rows, 30),
            "under_60_minutes_percent": _fraction_under(stop_rows, 60),
        },
        "episodes": [dict(item) for item in rows],
    }


def _fraction_under(rows: Sequence[Mapping[str, Any]], minutes: float) -> float:
    if not rows:
        return 0.0
    return sum(float(item["minutes_to_exit"]) < minutes for item in rows) / len(rows) * 100.0
