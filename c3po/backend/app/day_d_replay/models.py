from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any


def require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


class RunMode(StrEnum):
    SYNTHETIC = "synthetic"
    OFFICIAL = "official"


class CostScenario(StrEnum):
    OPTIMISTIC = "optimistic"
    POINT = "point"
    PESSIMISTIC = "pessimistic"


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class ExitKind(StrEnum):
    INITIAL_STOP = "initial_stop"
    HARD_STOP = "hard_stop"
    CHANDELIER = "chandelier"
    TARGET = "target"
    TIMEOUT = "timeout"
    T30 = "T30"
    PORTFOLIO_OVERRIDE = "portfolio_override"
    OFFICIAL_CLOSE_COUNTERFACTUAL = "official_close_counterfactual"


class CorporateActionKind(StrEnum):
    SPLIT = "split"
    CASH_DIVIDEND = "cash_dividend"
    SYMBOL_CHANGE = "symbol_change"
    CASH_MERGER = "cash_merger"
    STOCK_MERGER = "stock_merger"
    DELISTING_WITHOUT_CONSIDERATION = "delisting_without_consideration"


@dataclass(frozen=True, slots=True)
class MinuteBar:
    symbol: str
    start_at: datetime
    end_at: datetime
    available_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        require_aware(self.start_at, "start_at")
        require_aware(self.end_at, "end_at")
        require_aware(self.available_at, "available_at")
        if self.end_at <= self.start_at:
            raise ValueError("bar end_at must be after start_at")
        if (self.end_at - self.start_at).total_seconds() != 60:
            raise ValueError("Day D bars must cover exactly 60 seconds")
        if self.available_at < self.end_at:
            raise ValueError("a bar cannot be available before its interval ends")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("bar prices must be positive")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("bar OHLC values are inconsistent")
        if self.volume < 0:
            raise ValueError("bar volume cannot be negative")


@dataclass(frozen=True, slots=True)
class TradePrint:
    trade_id: str
    symbol: str
    event_at: datetime
    available_at: datetime
    price: float
    size: float

    def __post_init__(self) -> None:
        require_aware(self.event_at, "event_at")
        require_aware(self.available_at, "available_at")
        if self.available_at < self.event_at:
            raise ValueError("trade cannot be available before it occurs")
        if self.price <= 0 or self.size <= 0:
            raise ValueError("trade price and size must be positive")

    @property
    def notional_usd(self) -> float:
        return self.price * self.size


@dataclass(frozen=True, slots=True)
class Quote:
    quote_id: str
    symbol: str
    event_at: datetime
    available_at: datetime
    bid: float
    ask: float
    bid_size: float
    ask_size: float

    def __post_init__(self) -> None:
        require_aware(self.event_at, "event_at")
        require_aware(self.available_at, "available_at")
        if self.available_at < self.event_at:
            raise ValueError("quote cannot be available before it occurs")
        if min(self.bid, self.ask, self.bid_size, self.ask_size) <= 0:
            raise ValueError("quote prices and sizes must be positive")

    @property
    def crossed(self) -> bool:
        return self.bid > self.ask

    @property
    def locked(self) -> bool:
        return self.bid == self.ask

    @property
    def midpoint(self) -> float:
        return (self.bid + self.ask) / 2.0


@dataclass(frozen=True, slots=True)
class HaltInterval:
    symbol: str
    start_at: datetime
    end_at: datetime
    known_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.start_at, "start_at")
        require_aware(self.end_at, "end_at")
        require_aware(self.known_at, "known_at")
        if self.end_at <= self.start_at:
            raise ValueError("halt end_at must be after start_at")
        if self.known_at > self.end_at:
            raise ValueError("halt cannot become known after its end")

    def contains(self, at: datetime) -> bool:
        return self.start_at <= at < self.end_at


@dataclass(frozen=True, slots=True)
class SecurityDailySnapshot:
    session_date: date
    available_at: datetime
    symbol: str
    issuer_id: str
    listing_mic: str
    security_type: str
    adjusted_close_usd: float
    adjusted_regular_volume: float
    active: bool = True

    def __post_init__(self) -> None:
        require_aware(self.available_at, "available_at")
        if self.adjusted_close_usd <= 0 or self.adjusted_regular_volume < 0:
            raise ValueError("daily close must be positive and volume non-negative")

    @property
    def dollar_volume_usd(self) -> float:
        return self.adjusted_close_usd * self.adjusted_regular_volume


@dataclass(frozen=True, slots=True)
class PriorVolumeCurve:
    symbol: str
    session_date: date
    available_at: datetime
    cumulative_volume_by_minute: tuple[tuple[int, float], ...]

    def __post_init__(self) -> None:
        require_aware(self.available_at, "available_at")
        if not self.symbol:
            raise ValueError("prior-volume curve requires a symbol")
        minutes = [minute for minute, _value in self.cumulative_volume_by_minute]
        values = [value for _minute, value in self.cumulative_volume_by_minute]
        if minutes != sorted(minutes) or len(minutes) != len(set(minutes)):
            raise ValueError("prior-volume curve minutes must be unique and ordered")
        if any(minute not in range(390) for minute in minutes):
            raise ValueError("prior-volume curve minute must be inside regular hours")
        if any(value < 0 for value in values):
            raise ValueError("prior-volume curve cannot contain negative volume")
        if any(current < previous for previous, current in zip(values, values[1:])):
            raise ValueError("prior-volume curve must be cumulative and monotonic")

    def value_at(self, minute: int) -> float | None:
        return dict(self.cumulative_volume_by_minute).get(minute)


@dataclass(frozen=True, slots=True)
class OfficialCloseObservation:
    symbol: str
    session_date: date
    event_at: datetime
    available_at: datetime
    price: float
    source_id: str

    def __post_init__(self) -> None:
        require_aware(self.event_at, "event_at")
        require_aware(self.available_at, "available_at")
        if self.available_at < self.event_at:
            raise ValueError("official close cannot be available before it occurs")
        if self.event_at.date() != self.session_date:
            raise ValueError("official-close event must belong to its session")
        if not self.symbol or not self.source_id:
            raise ValueError("official close requires symbol and source provenance")
        if self.price <= 0:
            raise ValueError("official close must be positive")


@dataclass(frozen=True, slots=True)
class AdministrativeUnavailability:
    symbol: str
    reason_code: str
    available_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.available_at, "available_at")


@dataclass(frozen=True, slots=True)
class UniverseMember:
    rank: int
    symbol: str
    issuer_id: str
    listing_mic: str
    security_type: str
    d1_close_usd: float
    median_dollar_volume_20d_usd: float
    history_session_count: int
    liquidity_quintile: int
    data_as_of: datetime
    selection_reason: str = "D1_MEDIAN_DOLLAR_VOLUME"
    substitution_reason: str | None = None

    def __post_init__(self) -> None:
        require_aware(self.data_as_of, "data_as_of")
        if self.rank <= 0:
            raise ValueError("universe rank must be positive")
        if not all((self.symbol, self.issuer_id, self.listing_mic, self.security_type)):
            raise ValueError("universe member identity is incomplete")
        if self.d1_close_usd <= 0:
            raise ValueError("D-1 close must be positive")
        if self.median_dollar_volume_20d_usd < 0:
            raise ValueError("median dollar volume cannot be negative")
        if self.history_session_count != 20:
            raise ValueError("Day D universe members require exactly 20 sessions")
        if self.liquidity_quintile not in range(1, 6):
            raise ValueError("liquidity quintile must be 1..5")


@dataclass(frozen=True, slots=True)
class UniverseManifest:
    session_date: date
    previous_session_date: date
    generated_at: datetime
    information_cutoff_at: datetime
    universe_version: str
    members: tuple[UniverseMember, ...]
    benchmark_symbols: tuple[str, ...] = ("QQQ",)
    shortfall: int = 0

    def __post_init__(self) -> None:
        require_aware(self.generated_at, "generated_at")
        require_aware(self.information_cutoff_at, "information_cutoff_at")
        if self.information_cutoff_at > self.generated_at:
            raise ValueError("universe cutoff cannot follow manifest generation")
        symbols = [member.symbol for member in self.members]
        issuers = [member.issuer_id for member in self.members]
        if len(symbols) != len(set(symbols)):
            raise ValueError("universe symbols must be unique")
        if len(issuers) != len(set(issuers)):
            raise ValueError("universe issuers must be unique")
        ranks = [member.rank for member in self.members]
        if ranks != list(range(1, len(self.members) + 1)):
            raise ValueError("universe ranks must be contiguous and ordered")
        medians = [member.median_dollar_volume_20d_usd for member in self.members]
        if medians != sorted(medians, reverse=True):
            raise ValueError("universe members must remain in frozen D-1 rank order")
        if any(member.data_as_of > self.information_cutoff_at for member in self.members):
            raise ValueError("universe member uses information after the frozen cutoff")
        if self.shortfall < 0:
            raise ValueError("universe shortfall cannot be negative")
        if not self.benchmark_symbols or len(self.benchmark_symbols) != len(
            set(self.benchmark_symbols)
        ):
            raise ValueError("benchmark symbols must be present and unique")
        if set(symbols) & set(self.benchmark_symbols):
            raise ValueError("benchmark symbols cannot be tradeable universe members")


@dataclass(frozen=True, slots=True)
class BarFeature:
    bar: MinuteBar
    cumulative_volume: float
    vwap: float | None
    rvol: float | None
    atr: float | None

    @property
    def event_at(self) -> datetime:
        return self.bar.end_at

    @property
    def available_at(self) -> datetime:
        return self.bar.available_at


@dataclass(frozen=True, slots=True)
class SetupSignal:
    setup_version: str
    symbol: str
    session_date: date
    signal_event_at: datetime
    signal_available_at: datetime
    decision_at: datetime
    activation_price: float
    expires_at: datetime
    structural_stop: float
    stop_rule: str
    entry_atr: float
    decision_vwap: float
    rvol: float
    minimum_tick: float
    gate_values: dict[str, Any]
    target_hint: float | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "signal_event_at",
            "signal_available_at",
            "decision_at",
            "expires_at",
        ):
            require_aware(getattr(self, field_name), field_name)
        if self.signal_event_at > self.decision_at:
            raise ValueError("signal event cannot occur after decision")
        if self.signal_available_at > self.decision_at:
            raise ValueError("signal cannot be used before it is available")
        if self.decision_at >= self.expires_at:
            raise ValueError("signal must have a future expiry")
        if min(
            self.activation_price,
            self.structural_stop,
            self.entry_atr,
            self.decision_vwap,
            self.rvol,
            self.minimum_tick,
        ) <= 0:
            raise ValueError("signal prices and feature values must be positive")


@dataclass(frozen=True, slots=True)
class SetupEvaluation:
    setup_version: str
    symbol: str
    session_date: date | None
    attempted: bool
    accepted: bool
    decision_at: datetime | None
    reasons: tuple[str, ...]
    signal: SetupSignal | None = None


@dataclass(frozen=True, slots=True)
class FeeSchedule:
    version: str
    source: str
    effective_at: datetime
    captured_at: datetime
    content_hash: str
    commission_per_share_usd: float
    minimum_commission_usd: float
    sec_section_31_rate: float
    finra_taf_per_share_usd: float
    finra_taf_cap_usd: float

    def __post_init__(self) -> None:
        require_aware(self.effective_at, "effective_at")
        require_aware(self.captured_at, "captured_at")
        values = (
            self.commission_per_share_usd,
            self.minimum_commission_usd,
            self.sec_section_31_rate,
            self.finra_taf_per_share_usd,
            self.finra_taf_cap_usd,
        )
        if any(value < 0 for value in values):
            raise ValueError("fee schedule values cannot be negative")
        if not self.source or not self.content_hash:
            raise ValueError("fee schedule provenance is required")


@dataclass(frozen=True, slots=True)
class SpreadCell:
    liquidity_quintile: int
    time_bucket: str
    half_spread_p25_usd: float
    half_spread_p50_usd: float
    observation_count: int
    source_sessions_end: date
    available_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.available_at, "available_at")
        if self.liquidity_quintile not in range(1, 6):
            raise ValueError("liquidity quintile must be 1..5")
        if min(self.half_spread_p25_usd, self.half_spread_p50_usd) < 0:
            raise ValueError("spread values cannot be negative")
        if self.half_spread_p25_usd > self.half_spread_p50_usd:
            raise ValueError("p25 spread cannot exceed p50")
        if self.observation_count < 0:
            raise ValueError("observation_count cannot be negative")


@dataclass(frozen=True, slots=True)
class DataGateResult:
    gate: str
    passed: bool
    measured_at: datetime
    evidence_hash: str
    git_commit: str | None = None

    def __post_init__(self) -> None:
        require_aware(self.measured_at, "measured_at")
        if not self.gate or not self.evidence_hash:
            raise ValueError("data-gate identity and evidence hash are required")


@dataclass(frozen=True, slots=True)
class CorporateAction:
    action_id: str
    symbol: str
    kind: CorporateActionKind
    event_at: datetime
    available_at: datetime
    effective_at: datetime
    ratio: float | None = None
    cash_per_share_usd: float | None = None
    new_symbol: str | None = None
    consideration_per_share_usd: float | None = None

    def __post_init__(self) -> None:
        for field_name in ("event_at", "available_at", "effective_at"):
            require_aware(getattr(self, field_name), field_name)
        if self.available_at < self.event_at:
            raise ValueError("corporate action cannot be available before its event")
        if self.kind in {CorporateActionKind.SPLIT, CorporateActionKind.STOCK_MERGER}:
            if self.ratio is None or self.ratio <= 0:
                raise ValueError("share-changing corporate action requires a positive ratio")
        if self.kind is CorporateActionKind.STOCK_MERGER and not self.new_symbol:
            raise ValueError("stock merger requires new_symbol")
        if self.kind is CorporateActionKind.CASH_DIVIDEND:
            if self.cash_per_share_usd is None or self.cash_per_share_usd < 0:
                raise ValueError("cash dividend requires non-negative cash per share")
        if self.kind is CorporateActionKind.SYMBOL_CHANGE and not self.new_symbol:
            raise ValueError("symbol change requires new_symbol")
        if self.kind is CorporateActionKind.CASH_MERGER:
            if (
                self.consideration_per_share_usd is None
                or self.consideration_per_share_usd < 0
            ):
                raise ValueError("cash merger requires non-negative consideration")


@dataclass(frozen=True, slots=True)
class Fill:
    symbol: str
    side: Side
    kind: str
    decision_at: datetime
    arrival_at: datetime
    filled_at: datetime
    raw_reference_price: float
    economic_price: float
    quantity: int
    spread_cost_per_share_usd: float
    fee_usd: float
    quote_id: str | None
    trade_id: str | None
    latency_milliseconds: int
    quote_age_milliseconds: int | None
    used_trade_fallback: bool

    def __post_init__(self) -> None:
        for field_name in ("decision_at", "arrival_at", "filled_at"):
            require_aware(getattr(self, field_name), field_name)
        if self.arrival_at < self.decision_at or self.filled_at < self.arrival_at:
            raise ValueError("fill timestamps are not causal")
        if self.quantity <= 0:
            raise ValueError("fill quantity must be positive")
        if min(self.raw_reference_price, self.economic_price) < 0:
            raise ValueError("fill prices cannot be negative")
        if (
            min(self.raw_reference_price, self.economic_price) == 0
            and self.kind != "delisting_without_consideration"
        ):
            raise ValueError("zero fill is reserved for a zero-recovery delisting")
        if self.fee_usd < 0 or self.spread_cost_per_share_usd < 0:
            raise ValueError("fill costs cannot be negative")


@dataclass(slots=True)
class Position:
    position_id: str
    setup_version: str
    symbol: str
    session_date: date
    quantity: int
    entry_fill: Fill
    average_cost_per_share: float
    risk_budget_usd: float
    risk_per_share_usd: float
    initial_stop: float
    target_price: float | None
    entry_atr: float
    high_water: float
    remaining_quantity: int
    same_symbol_session_reentry: bool = False
    partial_filled: bool = False
    chandelier_activated: bool = False
    chandelier_stop: float | None = None
    opened_at: datetime = field(init=False)

    def __post_init__(self) -> None:
        self.opened_at = self.entry_fill.filled_at
        if self.quantity <= 0 or self.remaining_quantity <= 0:
            raise ValueError("position quantity must be positive")
        if self.remaining_quantity > self.quantity:
            raise ValueError("remaining quantity cannot exceed original quantity")


@dataclass(frozen=True, slots=True)
class LedgerRecord:
    position_id: str
    setup_version: str
    symbol: str
    session_date: date
    component: str
    event_at: datetime
    event_type: str
    cash_delta_usd: float
    mark_delta_usd: float
    r_delta: float
    raw_r_lifetime_after_event: float
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        require_aware(self.event_at, "event_at")


@dataclass(frozen=True, slots=True)
class ClosedTrade:
    position_id: str
    setup_version: str
    symbol: str
    entry_fill: Fill
    exit_fills: tuple[Fill, ...]
    risk_budget_usd: float
    gross_pnl_usd: float
    net_pnl_usd: float
    intraday_net_pnl_usd: float
    overnight_net_pnl_usd: float
    raw_r: float
    intraday_r: float
    overnight_r: float
    consolidated_r: float
    mfe_r: float
    mae_r: float
    opened_at: datetime
    closed_at: datetime
    same_symbol_session_reentry: bool = False


@dataclass(frozen=True, slots=True)
class RunManifest:
    run_id: str
    run_mode: RunMode
    created_at: datetime
    git_commit: str
    dataset_manifest_hash: str
    signal_contract_hash: str
    harness_contract_hash: str
    preregistration_hash: str
    setup_versions: tuple[str, ...]
    feature_version: str
    universe_version: str
    fill_version: str
    cost_model_version: str
    fee_schedule_version: str
    risk_policy_version: str
    calendar_version: str
    harness_version: str
    latency_scenario: str
    cost_scenario: CostScenario
    run_seed: int
    data_gate_results: tuple[DataGateResult, ...]
    synthetic_truth_gate_passed: bool

    def __post_init__(self) -> None:
        require_aware(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class SyntheticTruthReport:
    version: str
    git_commit: str
    harness_contract_hash: str
    signal_contract_hash: str
    run_seed: int
    passed: bool
    measured_at: datetime
    evidence_hash: str
    world_results: dict[str, dict[str, float]]
    property_results: dict[str, bool]

    def __post_init__(self) -> None:
        require_aware(self.measured_at, "measured_at")
        if not all(
            (
                self.version,
                self.git_commit,
                self.harness_contract_hash,
                self.signal_contract_hash,
                self.evidence_hash,
            )
        ):
            raise ValueError("synthetic-truth provenance is incomplete")
