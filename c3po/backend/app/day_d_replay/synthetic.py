from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .costs import CostTable
from .engine import DayDReplayHarness, ReplayDataset, ReplaySession
from .execution import ExecutionModel, MarketTape
from .ledger import build_closed_trade
from .models import (
    BarFeature,
    CostScenario,
    FeeSchedule,
    Fill,
    MinuteBar,
    OfficialCloseObservation,
    Position,
    PriorVolumeCurve,
    Quote,
    RunManifest,
    RunMode,
    SetupSignal,
    Side,
    SpreadCell,
    SyntheticTruthReport,
    TradePrint,
    UniverseManifest,
    UniverseMember,
)
from .signals import evaluate_s3, evaluate_s5
from .validation import HARNESS_CONTRACT_PATH, SIGNAL_CONTRACT_PATH, sha256_file

NEW_YORK = ZoneInfo("America/New_York")
FIXED_SEED = 20260822


def _at(hour: int, minute: int, second: int = 0, millisecond: int = 0) -> datetime:
    return datetime(2026, 8, 18, hour, minute, second, millisecond * 1000, tzinfo=NEW_YORK)


def _fill(
    *,
    symbol: str,
    side: Side,
    kind: str,
    at: datetime,
    price: float,
    quantity: int,
    fee: float = 0.0,
) -> Fill:
    return Fill(
        symbol=symbol,
        side=side,
        kind=kind,
        decision_at=at,
        arrival_at=at,
        filled_at=at,
        raw_reference_price=price,
        economic_price=price,
        quantity=quantity,
        spread_cost_per_share_usd=0.0,
        fee_usd=fee,
        quote_id=None,
        trade_id=f"{symbol}-{side}-{at.isoformat()}",
        latency_milliseconds=0,
        quote_age_milliseconds=0,
        used_trade_fallback=False,
    )


def _recover_episode(
    *,
    setup_version: str,
    planted_r: float,
    nav_scale: int = 1,
    entry_spread: float = 0.0,
    exit_spread: float = 0.0,
) -> float:
    nav = 1_000_000.0 * nav_scale
    risk_budget = nav * 0.0015
    quantity = 1000 * nav_scale
    raw_price = 100.0
    entry_price = raw_price + entry_spread
    entry = _fill(
        symbol="SYN",
        side=Side.BUY,
        kind="entry",
        at=_at(10, 0),
        price=entry_price,
        quantity=quantity,
    )
    desired_net_pnl = planted_r * risk_budget
    exit_price = (entry_price * quantity + desired_net_pnl) / quantity - exit_spread
    exit_fill = _fill(
        symbol="SYN",
        side=Side.SELL,
        kind="synthetic_truth_exit",
        at=_at(10, 30),
        price=exit_price,
        quantity=quantity,
    )
    position = Position(
        position_id=f"synthetic-{setup_version}-{planted_r}-{nav_scale}",
        setup_version=setup_version,
        symbol="SYN",
        session_date=date(2026, 8, 18),
        quantity=quantity,
        entry_fill=entry,
        average_cost_per_share=entry_price,
        risk_budget_usd=risk_budget,
        risk_per_share_usd=risk_budget / quantity,
        initial_stop=entry_price - risk_budget / quantity,
        target_price=None,
        entry_atr=0.5,
        high_water=max(entry_price, exit_price),
        remaining_quantity=quantity,
    )
    closed, _records = build_closed_trade(position=position, exit_fills=(exit_fill,))
    return closed.raw_r


def _engine_bars(symbol: str, *, benchmark: bool = False) -> tuple[MinuteBar, ...]:
    bars: list[MinuteBar] = []
    for index in range(15):
        start = _at(9, 30) + timedelta(minutes=index)
        if benchmark:
            open_, high, low, close = 500.0, 501.0, 499.0, 500.4
        else:
            open_, high, low, close = 100.0, 101.0, 99.0, 100.0
        bars.append(
            MinuteBar(
                symbol=symbol,
                start_at=start,
                end_at=start + timedelta(minutes=1),
                available_at=start + timedelta(minutes=1),
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=100_000.0,
            )
        )
    start = _at(9, 45)
    values = (500.3, 501.0, 500.0, 500.8) if benchmark else (
        100.8,
        101.6,
        100.7,
        101.5,
    )
    bars.append(
        MinuteBar(
            symbol=symbol,
            start_at=start,
            end_at=start + timedelta(minutes=1),
            available_at=start + timedelta(minutes=1),
            open=values[0],
            high=values[1],
            low=values[2],
            close=values[3],
            volume=100_000.0,
        )
    )
    return tuple(bars)


def _engine_s5_bars(symbol: str) -> tuple[MinuteBar, ...]:
    bars: list[MinuteBar] = []
    for index in range(14):
        start = _at(9, 30) + timedelta(minutes=index)
        bars.append(
            MinuteBar(
                symbol=symbol,
                start_at=start,
                end_at=start + timedelta(minutes=1),
                available_at=start + timedelta(minutes=1),
                open=100.0,
                high=100.5,
                low=99.5,
                close=100.0,
                volume=100_000.0,
            )
        )
    excursion_start = _at(9, 44)
    bars.append(
        MinuteBar(
            symbol=symbol,
            start_at=excursion_start,
            end_at=excursion_start + timedelta(minutes=1),
            available_at=excursion_start + timedelta(minutes=1),
            open=100.0,
            high=100.0,
            low=98.2,
            close=99.5,
            volume=100_000.0,
        )
    )
    reclaim_start = _at(9, 45)
    bars.append(
        MinuteBar(
            symbol=symbol,
            start_at=reclaim_start,
            end_at=reclaim_start + timedelta(minutes=1),
            available_at=reclaim_start + timedelta(minutes=1),
            open=99.4,
            high=99.7,
            low=99.0,
            close=99.6,
            volume=100_000.0,
        )
    )
    return tuple(bars)


def _engine_prior_curves(symbol: str) -> tuple[PriorVolumeCurve, ...]:
    points = tuple((minute, (minute + 1) * 50_000.0) for minute in range(390))
    return tuple(
        PriorVolumeCurve(
            symbol=symbol,
            session_date=date(2026, 8, 17) - timedelta(days=19 - index),
            available_at=_at(8, 0),
            cumulative_volume_by_minute=points,
        )
        for index in range(20)
    )


def _official_close(
    symbol: str, *, session_date: date, price: float
) -> OfficialCloseObservation:
    event_at = datetime.combine(
        session_date,
        datetime.min.time(),
        tzinfo=NEW_YORK,
    ).replace(hour=16)
    return OfficialCloseObservation(
        symbol=symbol,
        session_date=session_date,
        event_at=event_at,
        available_at=event_at + timedelta(seconds=1),
        price=price,
        source_id=f"synthetic-close-{symbol}-{session_date}",
    )


def _synthetic_engine_manifest() -> RunManifest:
    return RunManifest(
        run_id="synthetic-truth-engine",
        run_mode=RunMode.SYNTHETIC,
        created_at=_at(8, 0) + timedelta(days=4),
        git_commit="0" * 40,
        dataset_manifest_hash="0" * 64,
        signal_contract_hash="0" * 64,
        harness_contract_hash="0" * 64,
        preregistration_hash="0" * 64,
        setup_versions=("S3-v1", "S5-v1"),
        feature_version="DAY-D-FEATURES-v1",
        universe_version="DAY-D-UNIVERSE-v1",
        fill_version="DAY-D-FILL-v1",
        cost_model_version="DAY-D-COST-v1",
        fee_schedule_version="SYNTHETIC-FEE-v1",
        risk_policy_version="DAY-D-RISK-v1",
        calendar_version="DAY-D-CALENDAR-v1",
        harness_version="DAY-D-HARNESS-v1",
        latency_scenario="0ms",
        cost_scenario=CostScenario.POINT,
        run_seed=FIXED_SEED,
        data_gate_results=(),
        synthetic_truth_gate_passed=False,
    )


def _synthetic_engine_session(close_price: float) -> ReplaySession:
    session_date = date(2026, 8, 18)
    previous_session = date(2026, 8, 17)
    cutoff = datetime(2026, 8, 17, 16, tzinfo=NEW_YORK)
    universe = UniverseManifest(
        session_date=session_date,
        previous_session_date=previous_session,
        generated_at=_at(9, 25),
        information_cutoff_at=cutoff,
        universe_version="DAY-D-UNIVERSE-v1",
        members=(
            UniverseMember(
                rank=1,
                symbol="SYN",
                issuer_id="synthetic-issuer",
                listing_mic="XNAS",
                security_type="US_DOMESTIC_OPERATING_COMPANY_COMMON_STOCK",
                d1_close_usd=100.0,
                median_dollar_volume_20d_usd=100_000_000.0,
                history_session_count=20,
                liquidity_quintile=1,
                data_as_of=cutoff,
            ),
        ),
        shortfall=59,
    )
    entry_quote_at = _at(9, 46, 1)
    return ReplaySession(
        session_date=session_date,
        previous_session_date=previous_session,
        regular_open=_at(9, 30),
        official_close=_at(16, 0),
        universe=universe,
        bars_by_symbol={
            "SYN": _engine_bars("SYN"),
            "QQQ": _engine_bars("QQQ", benchmark=True),
        },
        prior_volume_curves_by_symbol={
            "SYN": _engine_prior_curves("SYN"),
            "QQQ": _engine_prior_curves("QQQ"),
        },
        d1_official_closes={
            "SYN": _official_close(
                "SYN", session_date=previous_session, price=100.0
            ),
            "QQQ": _official_close(
                "QQQ", session_date=previous_session, price=500.0
            ),
        },
        tapes_by_symbol={
            "SYN": MarketTape(
                symbol="SYN",
                trades=(),
                quotes=(
                    Quote(
                        "synthetic-entry",
                        "SYN",
                        entry_quote_at,
                        entry_quote_at,
                        101.60,
                        101.62,
                        10_000,
                        10_000,
                    ),
                ),
            ),
            "QQQ": MarketTape(symbol="QQQ", trades=(), quotes=()),
        },
        official_closes={
            "SYN": _official_close(
                "SYN", session_date=session_date, price=close_price
            )
        },
        quote_max_age_milliseconds_by_bucket={
            "OPEN_15": 2_000,
            "OPEN_60": 2_000,
            "MIDDAY": 2_000,
            "CLOSE_30": 2_000,
            "CLOSE_5": 2_000,
        },
    )


def _synthetic_engine_s5_session(close_price: float) -> ReplaySession:
    session_date = date(2026, 8, 18)
    previous_session = date(2026, 8, 17)
    cutoff = datetime(2026, 8, 17, 16, tzinfo=NEW_YORK)
    universe = UniverseManifest(
        session_date=session_date,
        previous_session_date=previous_session,
        generated_at=_at(9, 25),
        information_cutoff_at=cutoff,
        universe_version="DAY-D-UNIVERSE-v1",
        members=(
            UniverseMember(
                rank=1,
                symbol="SYN",
                issuer_id="synthetic-issuer",
                listing_mic="XNAS",
                security_type="US_DOMESTIC_OPERATING_COMPANY_COMMON_STOCK",
                d1_close_usd=100.0,
                median_dollar_volume_20d_usd=100_000_000.0,
                history_session_count=20,
                liquidity_quintile=1,
                data_as_of=cutoff,
            ),
        ),
        shortfall=59,
    )
    entry_quote_at = _at(9, 46, 1)
    return ReplaySession(
        session_date=session_date,
        previous_session_date=previous_session,
        regular_open=_at(9, 30),
        official_close=_at(16, 0),
        universe=universe,
        bars_by_symbol={
            "SYN": _engine_s5_bars("SYN"),
            "QQQ": _engine_bars("QQQ", benchmark=True),
        },
        prior_volume_curves_by_symbol={
            "SYN": _engine_prior_curves("SYN"),
            "QQQ": _engine_prior_curves("QQQ"),
        },
        d1_official_closes={
            "SYN": _official_close(
                "SYN", session_date=previous_session, price=100.0
            ),
            "QQQ": _official_close(
                "QQQ", session_date=previous_session, price=500.0
            ),
        },
        tapes_by_symbol={
            "SYN": MarketTape(
                symbol="SYN",
                trades=(),
                quotes=(
                    Quote(
                        "synthetic-s5-entry",
                        "SYN",
                        entry_quote_at,
                        entry_quote_at,
                        99.70,
                        99.72,
                        10_000,
                        10_000,
                    ),
                ),
            ),
            "QQQ": MarketTape(symbol="QQQ", trades=(), quotes=()),
        },
        official_closes={
            "SYN": _official_close(
                "SYN", session_date=session_date, price=close_price
            )
        },
        quote_max_age_milliseconds_by_bucket={
            "OPEN_15": 2_000,
            "OPEN_60": 2_000,
            "MIDDAY": 2_000,
            "CLOSE_30": 2_000,
            "CLOSE_5": 2_000,
        },
    )


def _recover_full_harness_episode(*, setup_version: str, planted_r: float) -> float:
    fee = FeeSchedule(
        version="SYNTHETIC-FEE-v1",
        source="synthetic-truth",
        effective_at=_at(8, 0),
        captured_at=_at(8, 0),
        content_hash="0" * 64,
        commission_per_share_usd=0.0,
        minimum_commission_usd=0.0,
        sec_section_31_rate=0.0,
        finra_taf_per_share_usd=0.0,
        finra_taf_cap_usd=0.0,
    )
    cost = CostTable.from_cells(
        "DAY-D-COST-v1",
        (
            SpreadCell(
                liquidity_quintile=1,
                time_bucket="ALL",
                half_spread_p25_usd=0.0,
                half_spread_p50_usd=0.0,
                observation_count=100,
                source_sessions_end=date(2026, 8, 17),
                available_at=_at(8, 0),
            ),
        ),
    )
    manifest = _synthetic_engine_manifest()

    session_factory = (
        _synthetic_engine_session
        if setup_version == "S3-v1"
        else _synthetic_engine_s5_session
    )
    if setup_version not in {"S3-v1", "S5-v1"}:
        raise ValueError("unsupported synthetic setup")

    def run(close_price: float):
        return DayDReplayHarness(manifest=manifest).run_flat_at_close_counterfactual(
            ReplayDataset(
                sessions=(session_factory(close_price),),
                checksums={},
                fee_schedule=fee,
                cost_table=cost,
            )
        )

    calibration_price = 101.62 if setup_version == "S3-v1" else 99.72
    calibration = run(calibration_price)
    audit = next(
        item
        for item in calibration.entry_audits
        if item.entry_accepted and item.setup_version == setup_version
    )
    assert audit.final_fill is not None
    assert audit.risk_budget_usd is not None
    desired_close = (
        audit.final_fill.economic_price
        + planted_r * audit.risk_budget_usd / audit.final_fill.quantity
    )
    result = run(desired_close)
    closed = next(
        trade for trade in result.closed_trades if trade.setup_version == setup_version
    )
    return closed.raw_r


def _feature(
    *,
    symbol: str,
    start: datetime,
    open_: float,
    high: float,
    low: float,
    close: float,
    vwap: float,
    rvol: float,
    atr: float,
) -> BarFeature:
    bar = MinuteBar(
        symbol=symbol,
        start_at=start,
        end_at=start + timedelta(minutes=1),
        available_at=start + timedelta(minutes=1),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1000.0,
    )
    return BarFeature(
        bar=bar,
        cumulative_volume=1000.0,
        vwap=vwap,
        rvol=rvol,
        atr=atr,
    )


def _s3_features() -> tuple[list[BarFeature], list[BarFeature]]:
    stock = [
        _feature(
            symbol="SYN",
            start=_at(9, 30) + timedelta(minutes=index),
            open_=100.0,
            high=100.2,
            low=99.8,
            close=100.0,
            vwap=100.0,
            rvol=2.0,
            atr=0.2,
        )
        for index in range(15)
    ]
    stock.append(
        _feature(
            symbol="SYN",
            start=_at(9, 45),
            open_=100.1,
            high=100.3,
            low=100.05,
            close=100.25,
            vwap=100.05,
            rvol=2.0,
            atr=0.2,
        )
    )
    qqq = [
        _feature(
            symbol="QQQ",
            start=_at(9, 30) + timedelta(minutes=index),
            open_=500.0,
            high=500.3,
            low=499.9,
            close=500.2,
            vwap=500.0,
            rvol=1.0,
            atr=0.5,
        )
        for index in range(16)
    ]
    return stock, qqq


def _s5_features() -> list[BarFeature]:
    values: list[BarFeature] = []
    for index in range(13):
        values.append(
            _feature(
                symbol="SYN",
                start=_at(9, 30) + timedelta(minutes=index),
                open_=100.0,
                high=100.1,
                low=99.95,
                close=100.0,
                vwap=100.0,
                rvol=1.0,
                atr=0.2,
            )
        )
    values.append(
        _feature(
            symbol="SYN",
            start=_at(9, 43),
            open_=100.0,
            high=100.0,
            low=99.6,
            close=99.8,
            vwap=100.0,
            rvol=1.2,
            atr=0.2,
        )
    )
    values.append(
        _feature(
            symbol="SYN",
            start=_at(9, 44),
            open_=99.85,
            high=100.05,
            low=99.8,
            close=100.01,
            vwap=99.98,
            rvol=2.0,
            atr=0.2,
        )
    )
    return values


def _future_mutation_property() -> bool:
    def decision_fingerprint(signal: SetupSignal | None) -> tuple[object, ...] | None:
        if signal is None:
            return None
        return (
            signal.setup_version,
            signal.symbol,
            signal.session_date,
            signal.signal_event_at,
            signal.signal_available_at,
            signal.decision_at,
            signal.activation_price,
            signal.structural_stop,
            signal.entry_atr,
            signal.decision_vwap,
            signal.rvol,
            signal.minimum_tick,
            signal.gate_values,
        )

    s3, qqq = _s3_features()
    first_s3 = evaluate_s3(s3, qqq).signal
    mutated_s3 = evaluate_s3(
        s3
        + [
            _feature(
                symbol="SYN",
                start=_at(15, 0),
                open_=50.0,
                high=200.0,
                low=1.0,
                close=150.0,
                vwap=80.0,
                rvol=10.0,
                atr=50.0,
            )
        ],
        qqq,
    ).signal
    s5 = _s5_features()
    first_s5 = evaluate_s5(s5).signal
    mutated_s5 = evaluate_s5(
        s5
        + [
            _feature(
                symbol="SYN",
                start=_at(15, 0),
                open_=50.0,
                high=200.0,
                low=1.0,
                close=150.0,
                vwap=80.0,
                rvol=10.0,
                atr=50.0,
            )
        ]
    ).signal
    return decision_fingerprint(first_s3) == decision_fingerprint(
        mutated_s3
    ) and decision_fingerprint(first_s5) == decision_fingerprint(mutated_s5)


def _same_bar_property() -> bool:
    signal = SetupSignal(
        setup_version="S3-v1",
        symbol="SYN",
        session_date=date(2026, 8, 18),
        signal_event_at=_at(10, 0),
        signal_available_at=_at(10, 0),
        decision_at=_at(10, 0),
        activation_price=100.0,
        expires_at=_at(10, 3),
        structural_stop=99.0,
        stop_rule="synthetic",
        entry_atr=0.5,
        decision_vwap=99.5,
        rvol=2.0,
        minimum_tick=0.01,
        gate_values={},
    )
    same_bar = TradePrint("same", "SYN", _at(10, 0), _at(10, 0), 101.0, 100.0)
    later = TradePrint(
        "later", "SYN", _at(10, 0, 1), _at(10, 0, 1), 101.0, 100.0
    )
    activation = MarketTape(symbol="SYN", trades=(same_bar, later), quotes=()).first_activation(
        signal
    )
    return activation is not None and activation.source_id == "later"


def _latency_property() -> bool:
    fee = FeeSchedule(
        version="SYNTHETIC-FEE-v1",
        source="synthetic",
        effective_at=_at(9, 0),
        captured_at=_at(9, 0),
        content_hash="0" * 64,
        commission_per_share_usd=0.0,
        minimum_commission_usd=0.0,
        sec_section_31_rate=0.0,
        finra_taf_per_share_usd=0.0,
        finra_taf_cap_usd=0.0,
    )
    signal = SetupSignal(
        setup_version="S3-v1",
        symbol="SYN",
        session_date=date(2026, 8, 18),
        signal_event_at=_at(10, 0),
        signal_available_at=_at(10, 0),
        decision_at=_at(10, 0),
        activation_price=100.0,
        expires_at=_at(10, 3),
        structural_stop=99.0,
        stop_rule="synthetic",
        entry_atr=0.5,
        decision_vwap=99.5,
        rvol=2.0,
        minimum_tick=0.01,
        gate_values={},
    )
    quotes = (
        Quote("q1", "SYN", _at(10, 0, 0, 100), _at(10, 0, 0, 100), 100.0, 100.1, 10, 10),
        Quote("q2", "SYN", _at(10, 0, 0, 600), _at(10, 0, 0, 600), 100.5, 100.6, 10, 10),
    )
    tape = MarketTape(symbol="SYN", trades=(), quotes=quotes)
    zero = ExecutionModel(
        fee_schedule=fee, run_seed=FIXED_SEED, fixed_latency_milliseconds=0
    ).fill_entry(
        signal=signal,
        tape=tape,
        quantity=10,
        half_spread_usd=0.05,
        quote_max_age_milliseconds=1000,
    )
    point = ExecutionModel(
        fee_schedule=fee, run_seed=FIXED_SEED, fixed_latency_milliseconds=500
    ).fill_entry(
        signal=signal,
        tape=tape,
        quantity=10,
        half_spread_usd=0.05,
        quote_max_age_milliseconds=1000,
    )
    return zero is not None and point is not None and zero.economic_price <= point.economic_price


def run_synthetic_truth_gate(
    *,
    git_commit: str,
    measured_at: datetime,
    harness_contract_path: Path = HARNESS_CONTRACT_PATH,
    signal_contract_path: Path = SIGNAL_CONTRACT_PATH,
) -> SyntheticTruthReport:
    """Run the deterministic CI truth worlds through the real R ledger."""

    world_results: dict[str, dict[str, float]] = {}
    thresholds = {
        "negative": (-0.5, lambda value: value <= -0.4),
        "zero": (0.0, lambda value: abs(value) <= 0.05),
        "positive": (0.5, lambda value: value >= 0.4),
    }
    world_passes: list[bool] = []
    for world, (planted, predicate) in thresholds.items():
        setup_results = {
            setup: _recover_full_harness_episode(
                setup_version=setup,
                planted_r=planted,
            )
            for setup in ("S3-v1", "S5-v1")
        }
        recovered = sum(setup_results.values()) / len(setup_results)
        setup_results["mean"] = recovered
        setup_results["planted"] = planted
        world_results[world] = setup_results
        world_passes.append(predicate(recovered))

    optimistic = _recover_episode(
        setup_version="S3-v1", planted_r=0.5, entry_spread=0.01, exit_spread=0.01
    )
    point = _recover_episode(
        setup_version="S3-v1", planted_r=0.5, entry_spread=0.02, exit_spread=0.02
    )
    pessimistic = _recover_episode(
        setup_version="S3-v1", planted_r=0.5, entry_spread=0.04, exit_spread=0.04
    )
    scale_one = _recover_episode(setup_version="S5-v1", planted_r=0.5, nav_scale=1)
    scale_two = _recover_episode(setup_version="S5-v1", planted_r=0.5, nav_scale=2)
    raw_tail = _recover_episode(setup_version="S3-v1", planted_r=7.0)
    properties = {
        "future_data_mutation_does_not_change_prior_decision": _future_mutation_property(),
        "same_bar_fill_is_rejected": _same_bar_property(),
        "zero_latency_result_is_not_worse_than_point_result_after_costs": _latency_property(),
        "optimistic_net_result_gte_point_gte_pessimistic": optimistic >= point >= pessimistic,
        "R_is_invariant_to_virtual_NAV_scale": abs(scale_one - scale_two) < 1e-12,
        "raw_tail_R_is_not_clipped": raw_tail > 5.0,
    }
    passed = all(world_passes) and all(properties.values())
    evidence = {
        "version": "DAY-D-SYNTHETIC-TRUTH-v1",
        "git_commit": git_commit,
        "seed": FIXED_SEED,
        "world_results": world_results,
        "property_results": properties,
    }
    evidence_hash = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return SyntheticTruthReport(
        version="DAY-D-SYNTHETIC-TRUTH-v1",
        git_commit=git_commit,
        harness_contract_hash=sha256_file(harness_contract_path),
        signal_contract_hash=sha256_file(signal_contract_path),
        run_seed=FIXED_SEED,
        passed=passed,
        measured_at=measured_at,
        evidence_hash=evidence_hash,
        world_results=world_results,
        property_results=properties,
    )
