from __future__ import annotations

import heapq
import itertools
import math
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import Mapping
from zoneinfo import ZoneInfo

from .costs import CostTable, execution_fee, time_bucket
from .execution import ExecutionModel, MarketTape
from .features import build_session_features, latest_completed_feature
from .ledger import build_closed_trade, entry_cash_cost, exit_cash_proceeds
from .models import (
    BarFeature,
    ClosedTrade,
    CostScenario,
    CorporateAction,
    CorporateActionKind,
    FeeSchedule,
    Fill,
    LedgerRecord,
    MinuteBar,
    OfficialCloseObservation,
    Position,
    PriorVolumeCurve,
    RunManifest,
    RunMode,
    SetupEvaluation,
    SetupSignal,
    Side,
    SyntheticTruthReport,
    TradePrint,
    UniverseManifest,
    UniverseMember,
)
from .signals import evaluate_s3, evaluate_s5
from .sizing import size_position
from .validation import OfficialReplayBlocked, validate_official_readiness

NEW_YORK = ZoneInfo("America/New_York")
ENTRY_CUTOFF_LOCAL = (15, 50)
MAX_SIMULTANEOUS_POSITIONS = 5
MAX_AGGREGATE_INITIAL_RISK_FRACTION = 0.0075


@dataclass(frozen=True, slots=True)
class ReplaySession:
    session_date: date
    previous_session_date: date
    regular_open: datetime
    official_close: datetime
    universe: UniverseManifest
    bars_by_symbol: Mapping[str, tuple[MinuteBar, ...]]
    prior_volume_curves_by_symbol: Mapping[str, tuple[PriorVolumeCurve, ...]]
    d1_official_closes: Mapping[str, OfficialCloseObservation]
    tapes_by_symbol: Mapping[str, MarketTape]
    official_closes: Mapping[str, OfficialCloseObservation]
    quote_max_age_milliseconds_by_bucket: Mapping[str, int]
    corporate_actions: tuple[CorporateAction, ...] = ()
    corporate_action_coverage_hash: str = ""

    def __post_init__(self) -> None:
        for field_name in ("regular_open", "official_close"):
            value = getattr(self, field_name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field_name} must be timezone-aware")
        if self.regular_open >= self.official_close:
            raise ValueError("regular_open must precede official_close")
        if self.regular_open.astimezone(NEW_YORK).date() != self.session_date:
            raise ValueError("regular_open does not belong to session_date")
        if self.official_close.astimezone(NEW_YORK).date() != self.session_date:
            raise ValueError("official_close does not belong to session_date")
        if self.universe.session_date != self.session_date:
            raise ValueError("universe manifest belongs to a different session")
        if self.universe.previous_session_date != self.previous_session_date:
            raise ValueError("universe D-1 does not match replay session")
        if self.universe.generated_at > self.regular_open:
            raise ValueError("universe manifest must be frozen before regular open")
        for symbol, bars in self.bars_by_symbol.items():
            for bar in bars:
                if bar.symbol != symbol:
                    raise ValueError("bars_by_symbol cannot mix symbols")
                if not self.regular_open <= bar.start_at < bar.end_at <= self.official_close:
                    raise ValueError("one-minute bar falls outside the regular session")
        for symbol, tape in self.tapes_by_symbol.items():
            if tape.symbol != symbol:
                raise ValueError("tapes_by_symbol cannot mix symbols")
        for symbol, curves in self.prior_volume_curves_by_symbol.items():
            if any(curve.symbol != symbol for curve in curves):
                raise ValueError("prior-volume curves cannot mix symbols")
            session_dates = [curve.session_date for curve in curves]
            if len(session_dates) != len(set(session_dates)):
                raise ValueError("prior-volume curves must have unique sessions")
            if any(curve.session_date >= self.session_date for curve in curves):
                raise ValueError("current or future volume curve would leak into RVOL")
            if any(curve.available_at > self.regular_open for curve in curves):
                raise ValueError("volume curve unavailable by regular open cannot enter RVOL")
        for symbol, observation in self.d1_official_closes.items():
            if observation.symbol != symbol:
                raise ValueError("D-1 official closes cannot mix symbols")
            if observation.session_date != self.previous_session_date:
                raise ValueError("D-1 official close belongs to the wrong session")
            if observation.available_at > self.regular_open:
                raise ValueError("D-1 close unavailable by regular open cannot enter features")
        for symbol, observation in self.official_closes.items():
            if observation.symbol != symbol:
                raise ValueError("T5 official closes cannot mix symbols")
            if observation.session_date != self.session_date:
                raise ValueError("T5 official close belongs to the wrong session")
            if observation.event_at != self.official_close:
                raise ValueError("T5 event must equal the exchange official close")
        required_buckets = {"OPEN_15", "OPEN_60", "MIDDAY", "CLOSE_30", "CLOSE_5"}
        if set(self.quote_max_age_milliseconds_by_bucket) != required_buckets:
            raise ValueError("quote-age table must define every frozen time bucket")
        if any(value <= 0 for value in self.quote_max_age_milliseconds_by_bucket.values()):
            raise ValueError("quote-age thresholds must be positive")
        for action in self.corporate_actions:
            if action.available_at > action.effective_at:
                raise ValueError(
                    "corporate action terms unavailable by effective time invalidate replay"
                )


@dataclass(frozen=True, slots=True)
class ReplayDataset:
    sessions: tuple[ReplaySession, ...]
    checksums: Mapping[str, str]
    fee_schedule: FeeSchedule
    cost_table: CostTable
    synthetic_truth: SyntheticTruthReport | None = None
    preregistration_payload: bytes | None = None

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.sessions, key=lambda item: item.session_date))
        if ordered != self.sessions:
            raise ValueError("replay sessions must be chronological")
        if len({session.session_date for session in self.sessions}) != len(self.sessions):
            raise ValueError("replay sessions must be unique")


@dataclass(frozen=True, slots=True)
class ReplayRejection:
    session_date: date
    symbol: str
    setup_version: str
    event_at: datetime | None
    reason: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReplayEntryAudit:
    session_date: date
    symbol: str
    setup_version: str
    universe_rank: int
    signal_event_at: datetime
    signal_available_at: datetime
    decision_at: datetime
    feature_as_of: datetime
    gate_values: Mapping[str, object]
    gate_result: bool
    entry_accepted: bool | None
    outcome_reason: str
    entry_expiry_at: datetime
    structural_stop: float
    post_floor_stop: float | None
    entry_atr: float
    entry_vwap: float
    entry_rvol: float
    risk_budget_usd: float | None
    quantity: int
    trial_fill: Fill | None
    final_fill: Fill | None


@dataclass(frozen=True, slots=True)
class ReplayResult:
    manifest: RunManifest
    book_policy: str
    evaluations: tuple[SetupEvaluation, ...]
    entry_audits: tuple[ReplayEntryAudit, ...]
    closed_trades: tuple[ClosedTrade, ...]
    ledger: tuple[LedgerRecord, ...]
    rejections: tuple[ReplayRejection, ...]
    ending_cash_usd: float
    ending_nav_usd: float
    daily_nav_usd: Mapping[date, float]
    open_positions: tuple[Position, ...]


@dataclass(frozen=True, slots=True)
class ReplayMatrixResult:
    results: Mapping[str, ReplayResult]
    books_share_identical_signals: bool
    zero_vs_1000ms_sign_stable: bool
    cost_monotonic_by_latency: Mapping[str, bool]

    @property
    def passed_fragility_gate(self) -> bool:
        return (
            self.books_share_identical_signals
            and self.zero_vs_1000ms_sign_stable
            and all(self.cost_monotonic_by_latency.values())
        )


@dataclass(frozen=True, slots=True)
class _EntryCandidate:
    member: UniverseMember
    signal: SetupSignal
    trial_fill: Fill
    entry_feature: BarFeature
    half_spread_usd: float
    point_half_spread_usd: float
    quote_max_age_milliseconds: int
    prior_five_minute_volume: float


@dataclass(slots=True)
class _ManagedPosition:
    position: Position
    liquidity_quintile: int
    aliases: set[str]
    exit_fills: list[Fill] = field(default_factory=list)
    dividends: list[tuple[datetime, float]] = field(default_factory=list)
    path_trades: list[TradePrint] = field(default_factory=list)
    entry_official_close_at: datetime | None = None
    entry_official_close_price: float | None = None
    last_official_mark: float | None = None
    last_mark: float = 0.0
    generation: int = 0

    @property
    def realized_exit_proceeds(self) -> float:
        return sum(exit_cash_proceeds(fill) for fill in self.exit_fills)


@dataclass(frozen=True, slots=True)
class _PlannedExit:
    fill: Fill
    partial: bool
    precedence: int


class DayDReplayHarness:
    """Research-only, fail-closed generation-one Day D replay engine."""

    def __init__(self, *, manifest: RunManifest, initial_nav_usd: float = 1_000_000.0):
        if initial_nav_usd <= 0:
            raise ValueError("initial_nav_usd must be positive")
        self.manifest = manifest
        self.initial_nav_usd = initial_nav_usd

    def run(self, dataset: ReplayDataset) -> ReplayResult:
        if self.manifest.run_mode is RunMode.OFFICIAL:
            raise OfficialReplayBlocked(
                "official replay must use run_fragility_matrix; isolated scenario output is forbidden"
            )
        return self._run_single(dataset)

    def run_flat_at_close_counterfactual(
        self, dataset: ReplayDataset
    ) -> ReplayResult:
        if self.manifest.run_mode is RunMode.OFFICIAL:
            raise OfficialReplayBlocked(
                "official replay must use run_fragility_matrix; isolated scenario output is forbidden"
            )
        return self._run_single(dataset, book_policy="flat_at_close")

    def run_fragility_matrix(self, dataset: ReplayDataset) -> ReplayMatrixResult:
        """Run the preregistered latency and cost matrix from one immutable dataset."""

        if self.manifest.run_mode is not RunMode.OFFICIAL:
            raise ValueError("fragility matrix is reserved for an official run manifest")
        latency_scenarios = ("point", "0ms", "250ms", "1000ms", "2000ms")
        cost_scenarios = (
            CostScenario.OPTIMISTIC,
            CostScenario.POINT,
            CostScenario.PESSIMISTIC,
        )
        results: dict[str, ReplayResult] = {}
        for book_policy in ("operational", "flat_at_close"):
            for latency in latency_scenarios:
                for cost in cost_scenarios:
                    manifest = replace(
                        self.manifest,
                        latency_scenario=latency,
                        cost_scenario=cost,
                    )
                    key = (
                        f"book={book_policy}|latency={latency}|cost={cost.value}"
                    )
                    results[key] = DayDReplayHarness(
                        manifest=manifest,
                        initial_nav_usd=self.initial_nav_usd,
                    )._run_single(dataset, book_policy=book_policy)

        def edge(book_policy: str, latency: str, cost: CostScenario) -> float:
            result = results[
                f"book={book_policy}|latency={latency}|cost={cost.value}"
            ]
            return result.ending_nav_usd - self.initial_nav_usd

        def sign(value: float) -> int:
            return 1 if value > 0 else -1 if value < 0 else 0

        zero_vs_1000 = sign(
            edge("operational", "0ms", CostScenario.POINT)
        ) == sign(
            edge("operational", "1000ms", CostScenario.POINT)
        )
        monotonic = {
            f"{book_policy}|{latency}": (
                edge(book_policy, latency, CostScenario.OPTIMISTIC)
                >= edge(book_policy, latency, CostScenario.POINT)
                >= edge(book_policy, latency, CostScenario.PESSIMISTIC)
            )
            for book_policy in ("operational", "flat_at_close")
            for latency in latency_scenarios
        }
        books_share_identical_signals = all(
            results[
                f"book=operational|latency={latency}|cost={cost.value}"
            ].evaluations
            == results[
                f"book=flat_at_close|latency={latency}|cost={cost.value}"
            ].evaluations
            for latency in latency_scenarios
            for cost in cost_scenarios
        )
        return ReplayMatrixResult(
            results=results,
            books_share_identical_signals=books_share_identical_signals,
            zero_vs_1000ms_sign_stable=zero_vs_1000,
            cost_monotonic_by_latency=monotonic,
        )

    def _run_single(
        self, dataset: ReplayDataset, *, book_policy: str = "operational"
    ) -> ReplayResult:
        if book_policy not in {"operational", "flat_at_close"}:
            raise ValueError("unknown replay book policy")
        validate_official_readiness(
            manifest=self.manifest,
            checksums=dataset.checksums,
            universes=[session.universe for session in dataset.sessions],
            fee_schedule=dataset.fee_schedule,
            cost_table=dataset.cost_table,
            synthetic_truth=dataset.synthetic_truth,
            preregistration_payload=dataset.preregistration_payload,
        )
        if self.manifest.run_mode is RunMode.OFFICIAL:
            missing_action_manifests = [
                session.session_date
                for session in dataset.sessions
                if len(session.corporate_action_coverage_hash) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in session.corporate_action_coverage_hash
                )
            ]
            if missing_action_manifests:
                raise ValueError(
                    "official corporate-action coverage is missing for: "
                    + ", ".join(map(str, missing_action_manifests))
                )

        execution = ExecutionModel(
            fee_schedule=dataset.fee_schedule,
            run_seed=self.manifest.run_seed,
            fixed_latency_milliseconds=self._fixed_latency(),
        )
        cash = self.initial_nav_usd
        evaluations: list[SetupEvaluation] = []
        entry_audits: dict[tuple[date, str, str], ReplayEntryAudit] = {}
        rejections: list[ReplayRejection] = []
        closed_trades: list[ClosedTrade] = []
        ledger: list[LedgerRecord] = []
        open_states: dict[str, _ManagedPosition] = {}
        daily_nav: dict[date, float] = {}
        sequence = itertools.count()

        for session in dataset.sessions:
            features = self._session_features(session)
            (
                session_evaluations,
                candidates,
                candidate_rejections,
                session_audits,
            ) = self._entries(
                session=session,
                features=features,
                cost_table=dataset.cost_table,
                execution=execution,
            )
            evaluations.extend(session_evaluations)
            rejections.extend(candidate_rejections)
            entry_audits.update(
                {
                    (audit.session_date, audit.symbol, audit.setup_version): audit
                    for audit in session_audits
                }
            )

            queue: list[tuple[datetime, int, int, str, object, int]] = []
            for action in session.corporate_actions:
                if action.effective_at >= session.official_close:
                    continue
                heapq.heappush(
                    queue,
                    (action.effective_at, 0, next(sequence), "action", action, 0),
                )
            for state in open_states.values():
                self._enqueue_next_exit(
                    queue=queue,
                    sequence=sequence,
                    state=state,
                    session=session,
                    features=features,
                    cost_table=dataset.cost_table,
                    execution=execution,
                    after=self._initial_exit_scan_after(state, session),
                )
            for candidate in candidates:
                heapq.heappush(
                    queue,
                    (
                        candidate.trial_fill.filled_at,
                        2,
                        next(sequence),
                        "entry",
                        candidate,
                        0,
                    ),
                )

            while queue:
                when, _priority, _sequence, event_type, payload, generation = heapq.heappop(
                    queue
                )
                if when >= session.official_close and event_type != "action":
                    continue
                if event_type == "action":
                    cash = self._apply_corporate_action(
                        action=payload,
                        open_states=open_states,
                        cash=cash,
                        session=session,
                        closed_trades=closed_trades,
                        ledger=ledger,
                    )
                    for state in open_states.values():
                        state.generation += 1
                        self._enqueue_next_exit(
                            queue=queue,
                            sequence=sequence,
                            state=state,
                            session=session,
                            features=features,
                            cost_table=dataset.cost_table,
                            execution=execution,
                            after=max(
                                session.regular_open - timedelta(microseconds=1),
                                payload.effective_at - timedelta(microseconds=1),
                            ),
                        )
                    continue
                if event_type == "entry":
                    candidate = payload
                    assert isinstance(candidate, _EntryCandidate)
                    cash = self._accept_entry(
                        candidate=candidate,
                        session=session,
                        execution=execution,
                        open_states=open_states,
                        cash=cash,
                        rejections=rejections,
                        entry_audits=entry_audits,
                        dataset=dataset,
                    )
                    state = next(
                        (
                            item
                            for item in open_states.values()
                            if item.position.symbol == candidate.signal.symbol
                            and item.position.setup_version == candidate.signal.setup_version
                            and item.position.opened_at == candidate.trial_fill.filled_at
                        ),
                        None,
                    )
                    if state is not None:
                        self._enqueue_next_exit(
                            queue=queue,
                            sequence=sequence,
                            state=state,
                            session=session,
                            features=features,
                            cost_table=dataset.cost_table,
                            execution=execution,
                            after=state.position.opened_at,
                        )
                    continue

                planned = payload
                assert isinstance(planned, _PlannedExit)
                state = next(
                    (
                        item
                        for item in open_states.values()
                        if item.position.position_id == planned.fill.kind.split("|")[0]
                    ),
                    None,
                )
                # Planned fills carry the position id as a private kind prefix;
                # strip it before persistence and ignore stale plans.
                if state is None or state.generation != generation:
                    continue
                persisted_fill = replace(
                    planned.fill,
                    kind=planned.fill.kind.split("|", 1)[1],
                )
                cash += exit_cash_proceeds(persisted_fill)
                state.exit_fills.append(persisted_fill)
                state.position.remaining_quantity -= persisted_fill.quantity
                state.generation += 1
                if planned.partial:
                    state.position.partial_filled = True
                    state.position.chandelier_activated = True
                if state.position.remaining_quantity > 0:
                    self._enqueue_next_exit(
                        queue=queue,
                        sequence=sequence,
                        state=state,
                        session=session,
                        features=features,
                        cost_table=dataset.cost_table,
                        execution=execution,
                        after=persisted_fill.filled_at,
                    )
                else:
                    self._append_path_trades(state, session, persisted_fill.filled_at)
                    closed, records = build_closed_trade(
                        position=state.position,
                        exit_fills=state.exit_fills,
                        entry_official_close_at=state.entry_official_close_at,
                        entry_official_close_price=state.entry_official_close_price,
                        cash_dividends=state.dividends,
                        path_trades=state.path_trades,
                        include_transfer_record=False,
                        include_dividend_records=False,
                    )
                    closed_trades.append(closed)
                    ledger.extend(records)
                    open_states.pop(state.position.position_id, None)

            for state in open_states.values():
                late_t30 = self._late_unfilled_t30_event(
                    state=state,
                    session=session,
                    cost_table=dataset.cost_table,
                    execution=execution,
                )
                if late_t30 is not None:
                    rejections.append(late_t30)

            if book_policy == "flat_at_close":
                for state in list(open_states.values()):
                    close_observation = session.official_closes.get(
                        state.position.symbol
                    )
                    if close_observation is None:
                        raise ValueError(
                            f"missing T5 official close for {state.position.symbol}"
                        )
                    close_price = close_observation.price
                    quantity = state.position.remaining_quantity
                    gross = close_price * quantity
                    fee = execution_fee(
                        dataset.fee_schedule,
                        side=Side.SELL,
                        quantity=quantity,
                        gross_notional_usd=gross,
                        event_at=session.official_close,
                    )
                    fill = Fill(
                        symbol=state.position.symbol,
                        side=Side.SELL,
                        kind="OFFICIAL_CLOSE_COUNTERFACTUAL",
                        decision_at=session.official_close,
                        arrival_at=session.official_close,
                        filled_at=session.official_close,
                        raw_reference_price=close_price,
                        economic_price=close_price,
                        quantity=quantity,
                        spread_cost_per_share_usd=0.0,
                        fee_usd=fee,
                        quote_id=None,
                        trade_id=None,
                        latency_milliseconds=0,
                        quote_age_milliseconds=None,
                        used_trade_fallback=False,
                    )
                    cash += exit_cash_proceeds(fill)
                    state.exit_fills.append(fill)
                    state.position.remaining_quantity = 0
                    self._append_path_trades(state, session, session.official_close)
                    closed, records = build_closed_trade(
                        position=state.position,
                        exit_fills=state.exit_fills,
                        entry_official_close_at=state.entry_official_close_at,
                        entry_official_close_price=state.entry_official_close_price,
                        cash_dividends=state.dividends,
                        path_trades=state.path_trades,
                        include_transfer_record=False,
                        include_dividend_records=False,
                    )
                    closed_trades.append(closed)
                    ledger.extend(records)
                    open_states.pop(state.position.position_id, None)

            for state in open_states.values():
                self._append_path_trades(state, session, session.official_close)
                close_observation = session.official_closes.get(
                    state.position.symbol
                )
                if close_observation is None:
                    if self.manifest.run_mode is RunMode.OFFICIAL:
                        raise ValueError(
                            f"missing T5 official close for open {state.position.symbol}"
                        )
                    close_price = state.last_mark
                else:
                    close_price = close_observation.price
                previous_mark = (
                    state.last_official_mark
                    if state.last_official_mark is not None
                    else state.position.entry_fill.economic_price
                )
                mark_delta = (
                    close_price - previous_mark
                ) * state.position.remaining_quantity
                marked_lifetime_pnl = (
                    state.realized_exit_proceeds
                    + close_price * state.position.remaining_quantity
                    + sum(amount for _, amount in state.dividends)
                    - entry_cash_cost(state.position.entry_fill)
                )
                first_transfer = state.entry_official_close_at is None
                ledger.append(
                    LedgerRecord(
                        position_id=state.position.position_id,
                        setup_version=state.position.setup_version,
                        symbol=state.position.symbol,
                        session_date=session.session_date,
                        component="transfer" if first_transfer else "overnight",
                        event_at=session.official_close,
                        event_type=(
                            "official_close_transfer_mark"
                            if first_transfer
                            else "daily_carry_mark"
                        ),
                        cash_delta_usd=0.0,
                        mark_delta_usd=mark_delta,
                        r_delta=mark_delta / state.position.risk_budget_usd,
                        raw_r_lifetime_after_event=(
                            marked_lifetime_pnl / state.position.risk_budget_usd
                        ),
                        metadata={
                            "official_close_price": close_price,
                            "remaining_quantity": state.position.remaining_quantity,
                            "fictitious_fee_usd": 0.0,
                        },
                    )
                )
                state.last_mark = close_price
                state.last_official_mark = close_price
                if (
                    state.position.session_date == session.session_date
                    and state.entry_official_close_at is None
                ):
                    state.entry_official_close_at = session.official_close
                    state.entry_official_close_price = close_price
                self._advance_chandelier_state(
                    state=state,
                    session=session,
                    features=features.get(state.position.symbol, []),
                    through=session.official_close,
                )
            ending_nav = cash + sum(
                state.last_mark * state.position.remaining_quantity
                for state in open_states.values()
            )
            daily_nav[session.session_date] = ending_nav

        ending_nav = (
            daily_nav[dataset.sessions[-1].session_date]
            if dataset.sessions
            else self.initial_nav_usd
        )
        return ReplayResult(
            manifest=self.manifest,
            book_policy=book_policy,
            evaluations=tuple(evaluations),
            entry_audits=tuple(
                sorted(
                    entry_audits.values(),
                    key=lambda item: (
                        item.session_date,
                        item.decision_at,
                        item.universe_rank,
                        item.setup_version,
                    ),
                )
            ),
            closed_trades=tuple(closed_trades),
            ledger=tuple(sorted(ledger, key=lambda item: item.event_at)),
            rejections=tuple(rejections),
            ending_cash_usd=cash,
            ending_nav_usd=ending_nav,
            daily_nav_usd=daily_nav,
            open_positions=tuple(state.position for state in open_states.values()),
        )

    def _fixed_latency(self) -> int | None:
        value = self.manifest.latency_scenario.strip().lower()
        if value in {"point", "500ms_jitter"}:
            return None
        if value.endswith("ms") and value[:-2].isdigit():
            return int(value[:-2])
        raise ValueError(f"unknown latency scenario: {self.manifest.latency_scenario}")

    @staticmethod
    def _session_features(session: ReplaySession) -> dict[str, list[BarFeature]]:
        result: dict[str, list[BarFeature]] = {}
        for symbol, bars in session.bars_by_symbol.items():
            d1_close = session.d1_official_closes.get(symbol)
            if d1_close is None:
                continue
            result[symbol] = build_session_features(
                list(bars),
                d1_official_close=d1_close.price,
                prior_cumulative_volume_curves=list(
                    session.prior_volume_curves_by_symbol.get(symbol, ())
                ),
            )
        return result

    def _entries(
        self,
        *,
        session: ReplaySession,
        features: Mapping[str, list[BarFeature]],
        cost_table: CostTable,
        execution: ExecutionModel,
    ) -> tuple[
        list[SetupEvaluation],
        list[_EntryCandidate],
        list[ReplayRejection],
        list[ReplayEntryAudit],
    ]:
        evaluations: list[SetupEvaluation] = []
        candidates: list[_EntryCandidate] = []
        rejections: list[ReplayRejection] = []
        audits: list[ReplayEntryAudit] = []
        qqq = features.get("QQQ", [])
        for member in session.universe.members:
            symbol_features = features.get(member.symbol, [])
            for evaluation in (
                evaluate_s3(symbol_features, qqq),
                evaluate_s5(symbol_features),
            ):
                evaluations.append(evaluation)
                signal = evaluation.signal
                if signal is None:
                    continue
                audit = ReplayEntryAudit(
                    session_date=session.session_date,
                    symbol=member.symbol,
                    setup_version=signal.setup_version,
                    universe_rank=member.rank,
                    signal_event_at=signal.signal_event_at,
                    signal_available_at=signal.signal_available_at,
                    decision_at=signal.decision_at,
                    feature_as_of=signal.decision_at,
                    gate_values=dict(signal.gate_values),
                    gate_result=True,
                    entry_accepted=None,
                    outcome_reason="PENDING_EXECUTION",
                    entry_expiry_at=signal.expires_at,
                    structural_stop=signal.structural_stop,
                    post_floor_stop=None,
                    entry_atr=signal.entry_atr,
                    entry_vwap=signal.decision_vwap,
                    entry_rvol=signal.rvol,
                    risk_budget_usd=None,
                    quantity=0,
                    trial_fill=None,
                    final_fill=None,
                )
                prepared, reason = self._prepare_entry(
                    signal=signal,
                    member=member,
                    session=session,
                    symbol_features=symbol_features,
                    cost_table=cost_table,
                    execution=execution,
                )
                if prepared is None:
                    audits.append(
                        replace(
                            audit,
                            entry_accepted=False,
                            outcome_reason=reason,
                        )
                    )
                    rejections.append(
                        ReplayRejection(
                            session_date=session.session_date,
                            symbol=member.symbol,
                            setup_version=signal.setup_version,
                            event_at=signal.decision_at,
                            reason=reason,
                        )
                    )
                else:
                    candidates.append(prepared)
                    audits.append(
                        replace(
                            audit,
                            outcome_reason="PENDING_PORTFOLIO_GATES",
                            trial_fill=prepared.trial_fill,
                        )
                    )
        candidates.sort(
            key=lambda item: (
                item.trial_fill.filled_at,
                item.member.rank,
                item.signal.setup_version,
                item.signal.symbol,
            )
        )
        return evaluations, candidates, rejections, audits

    def _prepare_entry(
        self,
        *,
        signal: SetupSignal,
        member: UniverseMember,
        session: ReplaySession,
        symbol_features: list[BarFeature],
        cost_table: CostTable,
        execution: ExecutionModel,
    ) -> tuple[_EntryCandidate | None, str]:
        tape = session.tapes_by_symbol.get(signal.symbol)
        if tape is None:
            return None, "MARKET_TAPE_MISSING"
        activation = tape.first_activation(signal)
        if activation is None:
            return None, "ENTRY_NOT_ACTIVATED_BEFORE_EXPIRY"
        bucket = time_bucket(
            activation.available_at,
            regular_open=session.regular_open,
            official_close=session.official_close,
        )
        half_spread = cost_table.half_spread(
            liquidity_quintile=member.liquidity_quintile,
            bucket=bucket,
            scenario=self.manifest.cost_scenario,
            replay_session=session.session_date,
            information_cutoff_at=session.regular_open,
        )
        point_half_spread = cost_table.half_spread(
            liquidity_quintile=member.liquidity_quintile,
            bucket=bucket,
            scenario=CostScenario.POINT,
            replay_session=session.session_date,
            information_cutoff_at=session.regular_open,
        )
        quote_age = session.quote_max_age_milliseconds_by_bucket[bucket]
        trial = execution.fill_entry(
            signal=signal,
            tape=tape,
            quantity=1,
            half_spread_usd=half_spread,
            quote_max_age_milliseconds=quote_age,
        )
        if trial is None:
            return None, "ENTRY_UNFILLED"
        blocking_action = self._entry_blocking_corporate_action(
            session=session,
            symbol=signal.symbol,
            filled_at=trial.filled_at,
        )
        if blocking_action is not None:
            return None, f"ENTRY_BLOCKED_BY_{blocking_action.kind.value.upper()}"
        if trial.filled_at >= self._entry_cutoff(session):
            return None, "ENTRY_AFTER_15_50_CUTOFF"
        feature = latest_completed_feature(symbol_features, trial.filled_at)
        if feature is None or feature.vwap is None:
            return None, "ENTRY_TIME_VWAP_UNAVAILABLE"
        if signal.setup_version == "S5-v1" and feature.vwap <= trial.economic_price:
            return None, "S5_FROZEN_VWAP_TARGET_NOT_ABOVE_FILL"
        completed = [
            item
            for item in symbol_features
            if item.available_at <= trial.decision_at
        ]
        if len(completed) < 5:
            return None, "PRIOR_FIVE_MINUTE_VOLUME_UNAVAILABLE"
        prior_volume = sum(item.bar.volume for item in completed[-5:])
        return (
            _EntryCandidate(
                member=member,
                signal=signal,
                trial_fill=trial,
                entry_feature=feature,
                half_spread_usd=half_spread,
                point_half_spread_usd=point_half_spread,
                quote_max_age_milliseconds=quote_age,
                prior_five_minute_volume=prior_volume,
            ),
            "ACCEPTED",
        )

    def _accept_entry(
        self,
        *,
        candidate: _EntryCandidate,
        session: ReplaySession,
        execution: ExecutionModel,
        open_states: dict[str, _ManagedPosition],
        cash: float,
        rejections: list[ReplayRejection],
        entry_audits: dict[tuple[date, str, str], ReplayEntryAudit],
        dataset: ReplayDataset,
    ) -> float:
        signal = candidate.signal
        audit_key = (session.session_date, signal.symbol, signal.setup_version)

        def update_audit(
            *,
            accepted: bool,
            reason: str,
            post_floor_stop: float | None = None,
            risk_budget_usd: float | None = None,
            quantity: int = 0,
            final_fill: Fill | None = None,
        ) -> None:
            current = entry_audits[audit_key]
            entry_audits[audit_key] = replace(
                current,
                entry_accepted=accepted,
                outcome_reason=reason,
                post_floor_stop=post_floor_stop,
                risk_budget_usd=risk_budget_usd,
                quantity=quantity,
                final_fill=final_fill,
            )

        def reject(
            reason: str,
            *,
            post_floor_stop: float | None = None,
            risk_budget_usd: float | None = None,
            quantity: int = 0,
            **metadata: object,
        ) -> float:
            update_audit(
                accepted=False,
                reason=reason,
                post_floor_stop=post_floor_stop,
                risk_budget_usd=risk_budget_usd,
                quantity=quantity,
            )
            rejections.append(
                ReplayRejection(
                    session_date=session.session_date,
                    symbol=signal.symbol,
                    setup_version=signal.setup_version,
                    event_at=candidate.trial_fill.filled_at,
                    reason=reason,
                    metadata=dict(metadata),
                )
            )
            return cash

        if any(signal.symbol in state.aliases for state in open_states.values()):
            return reject("DUPLICATE_SYMBOL_EXPOSURE")
        if len(open_states) >= MAX_SIMULTANEOUS_POSITIONS:
            return reject("MAX_SIMULTANEOUS_POSITIONS")
        nav = self._nav_at(
            cash=cash,
            open_states=open_states,
            session=session,
            at=candidate.trial_fill.filled_at,
        )
        sizing = size_position(
            signal=signal,
            entry_price=candidate.trial_fill.economic_price,
            entry_vwap=candidate.entry_feature.vwap or 0.0,
            entry_at=candidate.trial_fill.filled_at,
            nav_usd=nav,
            cash_usd=cash,
            prior_five_minute_volume_shares=candidate.prior_five_minute_volume,
            point_half_spread_usd=candidate.point_half_spread_usd,
            fee_schedule=dataset.fee_schedule,
        )
        if not sizing.accepted:
            return reject(
                sizing.reason,
                post_floor_stop=(sizing.initial_stop or None),
                risk_budget_usd=(sizing.risk_budget_usd or None),
                quantity=sizing.quantity,
            )
        aggregate_risk = sum(
            state.position.risk_budget_usd for state in open_states.values()
        ) + sizing.risk_budget_usd
        if aggregate_risk > nav * MAX_AGGREGATE_INITIAL_RISK_FRACTION + 1e-9:
            return reject(
                "AGGREGATE_INITIAL_RISK_CAP_BREACH",
                post_floor_stop=sizing.initial_stop,
                risk_budget_usd=sizing.risk_budget_usd,
                quantity=sizing.quantity,
            )
        tape = session.tapes_by_symbol[signal.symbol]
        fill = execution.fill_entry(
            signal=signal,
            tape=tape,
            quantity=sizing.quantity,
            half_spread_usd=candidate.half_spread_usd,
            quote_max_age_milliseconds=candidate.quote_max_age_milliseconds,
        )
        if fill is None or fill.filled_at != candidate.trial_fill.filled_at:
            return reject(
                "NONDETERMINISTIC_ENTRY_FILL",
                post_floor_stop=sizing.initial_stop,
                risk_budget_usd=sizing.risk_budget_usd,
                quantity=sizing.quantity,
            )
        total_cost = entry_cash_cost(fill)
        if total_cost > cash:
            return reject(
                "INSUFFICIENT_CASH_AT_FILL",
                post_floor_stop=sizing.initial_stop,
                risk_budget_usd=sizing.risk_budget_usd,
                quantity=sizing.quantity,
            )
        target = (
            candidate.entry_feature.vwap if signal.setup_version == "S5-v1" else None
        )
        position_id = (
            f"{session.session_date}:{signal.symbol}:{signal.setup_version}:"
            f"{fill.filled_at.isoformat()}"
        )
        position = Position(
            position_id=position_id,
            setup_version=signal.setup_version,
            symbol=signal.symbol,
            session_date=session.session_date,
            quantity=fill.quantity,
            entry_fill=fill,
            average_cost_per_share=total_cost / fill.quantity,
            risk_budget_usd=sizing.risk_budget_usd,
            risk_per_share_usd=sizing.risk_per_share_usd,
            initial_stop=sizing.initial_stop,
            target_price=target,
            entry_atr=signal.entry_atr,
            high_water=fill.raw_reference_price,
            remaining_quantity=fill.quantity,
        )
        open_states[position_id] = _ManagedPosition(
            position=position,
            liquidity_quintile=candidate.member.liquidity_quintile,
            aliases={signal.symbol},
            last_mark=fill.raw_reference_price,
        )
        update_audit(
            accepted=True,
            reason="ACCEPTED",
            post_floor_stop=sizing.initial_stop,
            risk_budget_usd=sizing.risk_budget_usd,
            quantity=fill.quantity,
            final_fill=fill,
        )
        return cash - total_cost

    def _enqueue_next_exit(
        self,
        *,
        queue: list[tuple[datetime, int, int, str, object, int]],
        sequence,
        state: _ManagedPosition,
        session: ReplaySession,
        features: Mapping[str, list[BarFeature]],
        cost_table: CostTable,
        execution: ExecutionModel,
        after: datetime,
    ) -> None:
        planned = self._plan_next_exit(
            state=state,
            session=session,
            features=features.get(state.position.symbol, []),
            cost_table=cost_table,
            execution=execution,
            after=after,
        )
        if planned is None:
            return
        prefixed = replace(
            planned.fill,
            kind=f"{state.position.position_id}|{planned.fill.kind}",
        )
        planned = replace(planned, fill=prefixed)
        heapq.heappush(
            queue,
            (
                planned.fill.filled_at,
                1,
                next(sequence),
                "exit",
                planned,
                state.generation,
            ),
        )

    @staticmethod
    def _initial_exit_scan_after(
        state: _ManagedPosition, session: ReplaySession
    ) -> datetime:
        latest_position_event = (
            state.exit_fills[-1].filled_at
            if state.exit_fills
            else state.position.opened_at
        )
        if latest_position_event < session.regular_open:
            return session.regular_open - timedelta(microseconds=1)
        return max(session.regular_open, latest_position_event)

    def _plan_next_exit(
        self,
        *,
        state: _ManagedPosition,
        session: ReplaySession,
        features: list[BarFeature],
        cost_table: CostTable,
        execution: ExecutionModel,
        after: datetime,
    ) -> _PlannedExit | None:
        tape = session.tapes_by_symbol.get(state.position.symbol)
        if tape is None:
            return None
        candidates: list[_PlannedExit] = []
        stop = self._stop_exit(
            state=state,
            session=session,
            tape=tape,
            cost_table=cost_table,
            execution=execution,
            after=after,
        )
        if stop is not None:
            candidates.append(_PlannedExit(stop, False, 0))

        position = state.position
        if position.setup_version == "S3-v1":
            if not position.partial_filled:
                partial_quantity = math.floor(position.quantity * 0.50)
                if partial_quantity > 0 and position.quantity > 1:
                    target = position.average_cost_per_share + 1.5 * position.risk_per_share_usd
                    fill = self._target_exit(
                        state=state,
                        session=session,
                        tape=tape,
                        cost_table=cost_table,
                        execution=execution,
                        after=after,
                        level=target,
                        quantity=partial_quantity,
                        kind="S3_1_5R_PARTIAL",
                    )
                    if fill is not None:
                        candidates.append(_PlannedExit(fill, True, 2))
                else:
                    activation_level = (
                        position.average_cost_per_share
                        + 1.5 * position.risk_per_share_usd
                    )
                    chandelier = self._chandelier_exit(
                        state=state,
                        session=session,
                        tape=tape,
                        features=features,
                        cost_table=cost_table,
                        execution=execution,
                        after=after,
                        activation_level=activation_level,
                    )
                    if chandelier is not None:
                        candidates.append(_PlannedExit(chandelier, False, 1))
                    runner_target = (
                        position.average_cost_per_share
                        + 2.0 * position.risk_per_share_usd
                    )
                    fill = self._target_exit(
                        state=state,
                        session=session,
                        tape=tape,
                        cost_table=cost_table,
                        execution=execution,
                        after=after,
                        level=runner_target,
                        quantity=position.remaining_quantity,
                        kind="S3_2R_TARGET",
                    )
                    if fill is not None:
                        candidates.append(_PlannedExit(fill, False, 2))
            else:
                chandelier = self._chandelier_exit(
                    state=state,
                    session=session,
                    tape=tape,
                    features=features,
                    cost_table=cost_table,
                    execution=execution,
                    after=after,
                    activation_level=None,
                )
                if chandelier is not None:
                    candidates.append(_PlannedExit(chandelier, False, 1))
                runner_target = (
                    position.average_cost_per_share + 2.0 * position.risk_per_share_usd
                )
                fill = self._target_exit(
                    state=state,
                    session=session,
                    tape=tape,
                    cost_table=cost_table,
                    execution=execution,
                    after=after,
                    level=runner_target,
                    quantity=position.remaining_quantity,
                    kind="S3_2R_TARGET",
                )
                if fill is not None:
                    candidates.append(_PlannedExit(fill, False, 2))
        elif position.setup_version == "S5-v1":
            assert position.target_price is not None
            fill = self._target_exit(
                state=state,
                session=session,
                tape=tape,
                cost_table=cost_table,
                execution=execution,
                after=after,
                level=position.target_price,
                quantity=position.remaining_quantity,
                kind="S5_FROZEN_VWAP_TARGET",
            )
            if fill is not None:
                candidates.append(_PlannedExit(fill, False, 2))
            timeout_at = position.opened_at + timedelta(seconds=2700)
            timeout = self._timeout_exit(
                state=state,
                session=session,
                tape=tape,
                cost_table=cost_table,
                execution=execution,
                after=max(after, timeout_at),
            )
            if timeout is not None:
                candidates.append(_PlannedExit(timeout, False, 3))

        t30 = self._t30_exit(
            state=state,
            session=session,
            tape=tape,
            cost_table=cost_table,
            execution=execution,
            after=after,
        )
        if t30 is not None:
            candidates.append(_PlannedExit(t30, False, 4))
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda item: (
                item.fill.decision_at,
                item.precedence,
                item.fill.filled_at,
            ),
        )

    def _stop_exit(
        self,
        *,
        state: _ManagedPosition,
        session: ReplaySession,
        tape: MarketTape,
        cost_table: CostTable,
        execution: ExecutionModel,
        after: datetime,
    ) -> Fill | None:
        stop_level = state.position.initial_stop
        fills: list[Fill] = []
        trigger = execution.find_stop_trigger(
            tape=tape,
            stop_level=stop_level,
            after=after,
            before=session.official_close,
        )
        if trigger is not None:
            half_spread = self._half_spread(
                session,
                state.liquidity_quintile,
                trigger.available_at,
                cost_table,
            )
            normal = execution.fill_stop_from_trigger(
                tape=tape,
                symbol=state.position.symbol,
                stop_level=stop_level,
                trigger=trigger,
                before=session.official_close,
                quantity=state.position.remaining_quantity,
                half_spread_usd=half_spread,
                kind="INITIAL_STOP",
                order_key=f"{state.position.position_id}|STOP|{state.generation}",
            )
            if normal is not None:
                fills.append(normal)
        for halt in tape.halts:
            if halt.end_at <= after or halt.end_at >= session.official_close:
                continue
            reopening = tape.first_trade_at_or_after(
                halt.end_at, before=session.official_close
            )
            if reopening is None or reopening.price > stop_level:
                continue
            reopening_spread = self._half_spread(
                session,
                state.liquidity_quintile,
                halt.end_at,
                cost_table,
            )
            fill = execution.fill_stop_from_trigger(
                tape=tape,
                symbol=state.position.symbol,
                stop_level=stop_level,
                trigger=reopening,
                before=session.official_close,
                quantity=state.position.remaining_quantity,
                half_spread_usd=reopening_spread,
                kind="INITIAL_STOP_REOPENING",
                order_key=f"{state.position.position_id}|REOPEN_STOP|{halt.end_at}",
                reopening_halt=halt,
            )
            if fill is not None:
                fills.append(fill)
        return min(fills, key=lambda item: item.decision_at) if fills else None

    def _target_exit(
        self,
        *,
        state: _ManagedPosition,
        session: ReplaySession,
        tape: MarketTape,
        cost_table: CostTable,
        execution: ExecutionModel,
        after: datetime,
        level: float,
        quantity: int,
        kind: str,
    ) -> Fill | None:
        activation = tape.first_upward_activation(
            level=level,
            after=after,
            before=session.official_close,
        )
        if activation is None:
            return None
        spread, quote_age = self._sell_inputs(
            session, state.liquidity_quintile, activation.available_at, cost_table
        )
        return execution.fill_ordinary_sell(
            tape=tape,
            symbol=state.position.symbol,
            decision_at=activation.available_at,
            quantity=quantity,
            half_spread_usd=spread,
            quote_max_age_milliseconds=quote_age,
            kind=kind,
            before=session.official_close,
            order_key=f"{state.position.position_id}|{kind}|{state.generation}",
        )

    def _timeout_exit(
        self,
        *,
        state: _ManagedPosition,
        session: ReplaySession,
        tape: MarketTape,
        cost_table: CostTable,
        execution: ExecutionModel,
        after: datetime,
    ) -> Fill | None:
        times = tape.observable_times(after=after, before=session.official_close)
        if not times:
            return None
        decision_at = times[0]
        spread, quote_age = self._sell_inputs(
            session, state.liquidity_quintile, decision_at, cost_table
        )
        return execution.fill_ordinary_sell(
            tape=tape,
            symbol=state.position.symbol,
            decision_at=decision_at,
            quantity=state.position.remaining_quantity,
            half_spread_usd=spread,
            quote_max_age_milliseconds=quote_age,
            kind="S5_45_MINUTE_TIMEOUT",
            before=session.official_close,
            order_key=f"{state.position.position_id}|TIMEOUT|{state.generation}",
        )

    def _t30_exit(
        self,
        *,
        state: _ManagedPosition,
        session: ReplaySession,
        tape: MarketTape,
        cost_table: CostTable,
        execution: ExecutionModel,
        after: datetime,
    ) -> Fill | None:
        start = max(after, session.official_close - timedelta(seconds=30))
        for decision_at in self._one_second_poll_times(
            start=start,
            before=session.official_close,
        ):
            spread, quote_age = self._sell_inputs(
                session, state.liquidity_quintile, decision_at, cost_table
            )
            quote = tape.latest_quote(decision_at)
            if quote is None:
                continue
            observed_quote_age = int(
                round((decision_at - quote.event_at).total_seconds() * 1000)
            )
            if observed_quote_age > quote_age:
                continue
            estimated_price = min(quote.bid, quote.midpoint - spread)
            if estimated_price <= 0:
                continue
            estimated_total = self._estimated_net_exit_total(
                state=state,
                estimated_price=estimated_price,
                decision_at=decision_at,
                execution=execution,
            )
            if estimated_total <= 0:
                continue
            fill = execution.fill_ordinary_sell(
                tape=tape,
                symbol=state.position.symbol,
                decision_at=decision_at,
                quantity=state.position.remaining_quantity,
                half_spread_usd=spread,
                quote_max_age_milliseconds=quote_age,
                kind="T30_NET_POSITIVE_EXIT",
                before=session.official_close,
                order_key=f"{state.position.position_id}|T30|{decision_at.isoformat()}",
            )
            if fill is not None:
                return fill
        return None

    def _late_unfilled_t30_event(
        self,
        *,
        state: _ManagedPosition,
        session: ReplaySession,
        cost_table: CostTable,
        execution: ExecutionModel,
    ) -> ReplayRejection | None:
        tape = session.tapes_by_symbol.get(state.position.symbol)
        if tape is None:
            return None
        start = session.official_close - timedelta(seconds=30)
        for decision_at in self._one_second_poll_times(
            start=start,
            before=session.official_close,
        ):
            spread, quote_age = self._sell_inputs(
                session, state.liquidity_quintile, decision_at, cost_table
            )
            quote = tape.latest_quote(decision_at)
            if quote is None:
                continue
            observed_quote_age = int(
                round((decision_at - quote.event_at).total_seconds() * 1000)
            )
            if observed_quote_age > quote_age:
                continue
            estimated_price = min(quote.bid, quote.midpoint - spread)
            if estimated_price <= 0:
                continue
            estimated_total = self._estimated_net_exit_total(
                state=state,
                estimated_price=estimated_price,
                decision_at=decision_at,
                execution=execution,
            )
            if estimated_total > 0:
                return ReplayRejection(
                    session_date=session.session_date,
                    symbol=state.position.symbol,
                    setup_version=state.position.setup_version,
                    event_at=decision_at,
                    reason="LATE_UNFILLED_EXIT",
                    metadata={
                        "rule": "T30_NET_POSITIVE_EXIT",
                        "estimated_net_exit_pnl_usd": estimated_total,
                        "estimated_exit_price": estimated_price,
                        "official_close_at": session.official_close.isoformat(),
                    },
                )
        return None

    @staticmethod
    def _estimated_net_exit_total(
        *,
        state: _ManagedPosition,
        estimated_price: float,
        decision_at: datetime,
        execution: ExecutionModel,
    ) -> float:
        estimated_gross = estimated_price * state.position.remaining_quantity
        estimated_fee = execution_fee(
            execution.fee_schedule,
            side=Side.SELL,
            quantity=state.position.remaining_quantity,
            gross_notional_usd=estimated_gross,
            event_at=decision_at,
        )
        return (
            state.realized_exit_proceeds
            + estimated_gross
            - estimated_fee
            + sum(amount for _, amount in state.dividends)
            - entry_cash_cost(state.position.entry_fill)
        )

    @staticmethod
    def _one_second_poll_times(
        *, start: datetime, before: datetime
    ) -> tuple[datetime, ...]:
        if start.tzinfo is None or start.utcoffset() is None:
            raise ValueError("poll start must be timezone-aware")
        if before.tzinfo is None or before.utcoffset() is None:
            raise ValueError("poll boundary must be timezone-aware")
        first = start.replace(microsecond=0)
        if first < start:
            first += timedelta(seconds=1)
        values: list[datetime] = []
        current = first
        while current < before:
            values.append(current)
            current += timedelta(seconds=1)
        return tuple(values)

    def _chandelier_exit(
        self,
        *,
        state: _ManagedPosition,
        session: ReplaySession,
        tape: MarketTape,
        features: list[BarFeature],
        cost_table: CostTable,
        execution: ExecutionModel,
        after: datetime,
        activation_level: float | None,
    ) -> Fill | None:
        high_water = state.position.high_water
        chandelier = state.position.chandelier_stop
        activated = state.position.chandelier_activated
        breaches: list[TradePrint] = []
        observed = sorted(
            tape.trades,
            key=lambda item: (item.available_at, item.event_at, item.trade_id),
        )
        for trade in observed:
            if trade.event_at <= after or trade.available_at <= after:
                continue
            if trade.available_at >= session.official_close:
                continue
            if tape.halt_at(trade.event_at) is not None:
                continue
            feature = latest_completed_feature(features, trade.available_at)
            if feature is None or feature.atr is None:
                continue
            if not activated:
                if activation_level is None or trade.price < activation_level:
                    continue
                activated = True
            high_water = max(high_water, trade.price)
            proposed = high_water - 2.5 * feature.atr
            chandelier = proposed if chandelier is None else max(chandelier, proposed)
            if trade.price > chandelier:
                breaches.clear()
                continue
            cutoff = trade.event_at - timedelta(milliseconds=1000)
            breaches = [item for item in breaches if item.event_at >= cutoff]
            if all(item.trade_id != trade.trade_id for item in breaches):
                breaches.append(trade)
            separated = any(
                (trade.event_at - item.event_at).total_seconds() >= 0.1
                for item in breaches[:-1]
            )
            if separated and sum(item.notional_usd for item in breaches) >= 5000.0:
                spread = self._half_spread(
                    session,
                    state.liquidity_quintile,
                    trade.available_at,
                    cost_table,
                )
                return execution.fill_stop_from_trigger(
                    tape=tape,
                    symbol=state.position.symbol,
                    stop_level=chandelier,
                    trigger=trade,
                    before=session.official_close,
                    quantity=state.position.remaining_quantity,
                    half_spread_usd=spread,
                    kind="S3_CHANDELIER",
                    order_key=f"{state.position.position_id}|CHANDELIER|{state.generation}",
                )
        return None

    @staticmethod
    def _advance_chandelier_state(
        *,
        state: _ManagedPosition,
        session: ReplaySession,
        features: list[BarFeature],
        through: datetime,
    ) -> None:
        if state.position.setup_version != "S3-v1":
            return
        tape = session.tapes_by_symbol.get(state.position.symbol)
        if tape is None:
            return
        high_water = state.position.high_water
        chandelier = state.position.chandelier_stop
        activated = state.position.chandelier_activated
        activation_level = (
            state.position.average_cost_per_share
            + 1.5 * state.position.risk_per_share_usd
            if state.position.quantity == 1
            else None
        )
        for trade in sorted(
            tape.trades,
            key=lambda item: (item.available_at, item.event_at, item.trade_id),
        ):
            if not state.position.opened_at <= trade.event_at <= through:
                continue
            if trade.available_at > through:
                continue
            feature = latest_completed_feature(features, trade.available_at)
            if feature is None or feature.atr is None:
                continue
            if not activated:
                if activation_level is None or trade.price < activation_level:
                    continue
                activated = True
            high_water = max(high_water, trade.price)
            proposed = high_water - 2.5 * feature.atr
            chandelier = proposed if chandelier is None else max(chandelier, proposed)
        state.position.high_water = high_water
        state.position.chandelier_activated = activated
        state.position.chandelier_stop = chandelier

    def _sell_inputs(
        self,
        session: ReplaySession,
        quintile: int,
        at: datetime,
        cost_table: CostTable,
    ) -> tuple[float, int]:
        bucket = time_bucket(
            at,
            regular_open=session.regular_open,
            official_close=session.official_close,
        )
        return (
            cost_table.half_spread(
                liquidity_quintile=quintile,
                bucket=bucket,
                scenario=self.manifest.cost_scenario,
                replay_session=session.session_date,
                information_cutoff_at=session.regular_open,
            ),
            session.quote_max_age_milliseconds_by_bucket[bucket],
        )

    def _half_spread(
        self,
        session: ReplaySession,
        quintile: int,
        at: datetime,
        cost_table: CostTable,
    ) -> float:
        return self._sell_inputs(session, quintile, at, cost_table)[0]

    @staticmethod
    def _entry_cutoff(session: ReplaySession) -> datetime:
        local = session.regular_open.astimezone(NEW_YORK)
        normal_cutoff = local.replace(
            hour=ENTRY_CUTOFF_LOCAL[0],
            minute=ENTRY_CUTOFF_LOCAL[1],
            second=0,
            microsecond=0,
        )
        return min(normal_cutoff, session.official_close - timedelta(minutes=10))

    @staticmethod
    def _entry_blocking_corporate_action(
        *, session: ReplaySession, symbol: str, filled_at: datetime
    ) -> CorporateAction | None:
        blocking_kinds = {
            CorporateActionKind.SPLIT,
            CorporateActionKind.SYMBOL_CHANGE,
            CorporateActionKind.CASH_MERGER,
            CorporateActionKind.STOCK_MERGER,
            CorporateActionKind.DELISTING_WITHOUT_CONSIDERATION,
        }
        eligible = [
            action
            for action in session.corporate_actions
            if action.symbol == symbol
            and action.kind in blocking_kinds
            and action.effective_at <= filled_at
        ]
        return min(eligible, key=lambda action: action.effective_at) if eligible else None

    @staticmethod
    def _append_path_trades(
        state: _ManagedPosition, session: ReplaySession, through: datetime
    ) -> None:
        tape = session.tapes_by_symbol.get(state.position.symbol)
        if tape is None:
            return
        known = {trade.trade_id for trade in state.path_trades}
        state.path_trades.extend(
            trade
            for trade in tape.trades
            if state.position.opened_at <= trade.event_at <= through
            and trade.trade_id not in known
        )
        state.path_trades.sort(key=lambda item: item.event_at)

    @staticmethod
    def _mark(state: _ManagedPosition, session: ReplaySession, at: datetime) -> float:
        tape = session.tapes_by_symbol.get(state.position.symbol)
        if tape is not None:
            quote = tape.latest_quote(at)
            if quote is not None:
                return quote.midpoint
            trade = tape.latest_trade(at)
            if trade is not None:
                return trade.price
        return state.last_mark

    def _nav_at(
        self,
        *,
        cash: float,
        open_states: Mapping[str, _ManagedPosition],
        session: ReplaySession,
        at: datetime,
    ) -> float:
        return cash + sum(
            self._mark(state, session, at) * state.position.remaining_quantity
            for state in open_states.values()
        )

    def _apply_corporate_action(
        self,
        *,
        action: CorporateAction,
        open_states: dict[str, _ManagedPosition],
        cash: float,
        session: ReplaySession,
        closed_trades: list[ClosedTrade],
        ledger: list[LedgerRecord],
    ) -> float:
        states = [state for state in open_states.values() if action.symbol in state.aliases]
        for state in states:
            position = state.position
            if action.kind is CorporateActionKind.CASH_DIVIDEND:
                assert action.cash_per_share_usd is not None
                amount = action.cash_per_share_usd * position.remaining_quantity
                cash += amount
                state.dividends.append((action.effective_at, amount))
                marked_lifetime = (
                    state.realized_exit_proceeds
                    + state.last_mark * position.remaining_quantity
                    + sum(value for _, value in state.dividends)
                    - entry_cash_cost(position.entry_fill)
                )
                ledger.append(
                    LedgerRecord(
                        position_id=position.position_id,
                        setup_version=position.setup_version,
                        symbol=position.symbol,
                        session_date=action.effective_at.astimezone(NEW_YORK).date(),
                        component=(
                            "intraday"
                            if state.entry_official_close_at is None
                            else "overnight"
                        ),
                        event_at=action.effective_at,
                        event_type="cash_dividend",
                        cash_delta_usd=amount,
                        mark_delta_usd=0.0,
                        r_delta=amount / position.risk_budget_usd,
                        raw_r_lifetime_after_event=(
                            marked_lifetime / position.risk_budget_usd
                        ),
                        metadata={"cash_per_share_usd": action.cash_per_share_usd},
                    )
                )
                continue
            if action.kind in {
                CorporateActionKind.SPLIT,
                CorporateActionKind.STOCK_MERGER,
            }:
                assert action.ratio is not None
                new_quantity = position.quantity * action.ratio
                new_remaining = position.remaining_quantity * action.ratio
                adjusted_exit_quantities = [
                    fill.quantity * action.ratio for fill in state.exit_fills
                ]
                if (
                    not float(new_quantity).is_integer()
                    or not float(new_remaining).is_integer()
                    or any(
                        not float(value).is_integer()
                        for value in adjusted_exit_quantities
                    )
                ):
                    raise ValueError(
                        "fractional corporate-action shares require point-in-time cash-in-lieu terms"
                    )
                new_symbol = action.new_symbol or position.symbol
                position.entry_fill = replace(
                    position.entry_fill,
                    symbol=new_symbol,
                    quantity=int(new_quantity),
                    raw_reference_price=position.entry_fill.raw_reference_price / action.ratio,
                    economic_price=position.entry_fill.economic_price / action.ratio,
                    spread_cost_per_share_usd=(
                        position.entry_fill.spread_cost_per_share_usd / action.ratio
                    ),
                )
                state.exit_fills = [
                    replace(
                        fill,
                        symbol=new_symbol,
                        quantity=int(adjusted_exit_quantities[index]),
                        raw_reference_price=fill.raw_reference_price / action.ratio,
                        economic_price=fill.economic_price / action.ratio,
                        spread_cost_per_share_usd=fill.spread_cost_per_share_usd
                        / action.ratio,
                    )
                    for index, fill in enumerate(state.exit_fills)
                ]
                state.path_trades = [
                    replace(
                        trade,
                        symbol=new_symbol,
                        price=trade.price / action.ratio,
                        size=trade.size * action.ratio,
                    )
                    for trade in state.path_trades
                ]
                position.quantity = int(new_quantity)
                position.remaining_quantity = int(new_remaining)
                position.average_cost_per_share /= action.ratio
                position.risk_per_share_usd /= action.ratio
                position.initial_stop /= action.ratio
                position.entry_atr /= action.ratio
                position.high_water /= action.ratio
                if position.target_price is not None:
                    position.target_price /= action.ratio
                if position.chandelier_stop is not None:
                    position.chandelier_stop /= action.ratio
                if state.entry_official_close_price is not None:
                    state.entry_official_close_price /= action.ratio
                if state.last_official_mark is not None:
                    state.last_official_mark /= action.ratio
                state.last_mark /= action.ratio
                position.symbol = new_symbol
                state.aliases.add(new_symbol)
                continue
            if action.kind is CorporateActionKind.SYMBOL_CHANGE:
                assert action.new_symbol is not None
                position.entry_fill = replace(position.entry_fill, symbol=action.new_symbol)
                state.exit_fills = [
                    replace(fill, symbol=action.new_symbol) for fill in state.exit_fills
                ]
                position.symbol = action.new_symbol
                state.aliases.add(action.new_symbol)
                continue
            if action.kind in {
                CorporateActionKind.CASH_MERGER,
                CorporateActionKind.DELISTING_WITHOUT_CONSIDERATION,
            }:
                price = (
                    action.consideration_per_share_usd
                    if action.kind is CorporateActionKind.CASH_MERGER
                    else 0.0
                )
                assert price is not None
                kind = (
                    "cash_merger"
                    if action.kind is CorporateActionKind.CASH_MERGER
                    else "delisting_without_consideration"
                )
                fill = Fill(
                    symbol=position.symbol,
                    side=Side.SELL,
                    kind=kind,
                    decision_at=action.effective_at,
                    arrival_at=action.effective_at,
                    filled_at=action.effective_at,
                    raw_reference_price=price,
                    economic_price=price,
                    quantity=position.remaining_quantity,
                    spread_cost_per_share_usd=0.0,
                    fee_usd=0.0,
                    quote_id=None,
                    trade_id=action.action_id,
                    latency_milliseconds=0,
                    quote_age_milliseconds=None,
                    used_trade_fallback=False,
                )
                cash += exit_cash_proceeds(fill)
                state.exit_fills.append(fill)
                position.remaining_quantity = 0
                closed, records = build_closed_trade(
                    position=position,
                    exit_fills=state.exit_fills,
                    entry_official_close_at=state.entry_official_close_at,
                    entry_official_close_price=state.entry_official_close_price,
                    cash_dividends=state.dividends,
                    path_trades=state.path_trades,
                    include_transfer_record=False,
                    include_dividend_records=False,
                )
                closed_trades.append(closed)
                ledger.extend(records)
                open_states.pop(position.position_id, None)
        return cash
