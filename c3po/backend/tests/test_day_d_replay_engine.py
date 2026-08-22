from __future__ import annotations

from dataclasses import replace
import hashlib
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.day_d_replay.costs import CostTable
from app.day_d_replay.engine import DayDReplayHarness, ReplayDataset, ReplaySession
from app.day_d_replay.execution import MarketTape
from app.day_d_replay.models import (
    CostScenario,
    DataGateResult,
    FeeSchedule,
    MinuteBar,
    OfficialCloseObservation,
    PriorVolumeCurve,
    Quote,
    RunManifest,
    RunMode,
    SpreadCell,
    TradePrint,
    UniverseManifest,
    UniverseMember,
)
from app.day_d_replay.synthetic import run_synthetic_truth_gate
from app.day_d_replay.validation import (
    HARNESS_CONTRACT_PATH,
    SIGNAL_CONTRACT_PATH,
    dataset_manifest_hash,
    sha256_file,
)

NEW_YORK = ZoneInfo("America/New_York")
SESSION = date(2026, 8, 21)
PREREGISTRATION_PAYLOAD = b'{"contract":"engine-test-preregistration"}'


def _at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 8, 21, hour, minute, second, tzinfo=NEW_YORK)


def _bars(symbol: str, *, qqq: bool = False) -> tuple[MinuteBar, ...]:
    bars: list[MinuteBar] = []
    for index in range(15):
        start = _at(9, 30) + timedelta(minutes=index)
        if qqq:
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
                volume=100_000,
            )
        )
    start = _at(9, 45)
    if qqq:
        values = (500.3, 501.0, 500.0, 500.8)
    else:
        values = (100.8, 101.6, 100.7, 101.5)
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
            volume=100_000,
        )
    )
    return tuple(bars)


def _prior_curves(symbol: str) -> tuple[PriorVolumeCurve, ...]:
    points = tuple((minute, (minute + 1) * 50_000.0) for minute in range(390))
    return tuple(
        PriorVolumeCurve(
            symbol=symbol,
            session_date=date(2026, 8, 20) - timedelta(days=19 - index),
            available_at=datetime(2026, 8, 20, 16, tzinfo=NEW_YORK),
            cumulative_volume_by_minute=points,
        )
        for index in range(20)
    )


def _close(symbol: str, session_date: date, price: float) -> OfficialCloseObservation:
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
        source_id=f"test-close-{symbol}-{session_date}",
    )


def _manifest() -> RunManifest:
    return RunManifest(
        run_id="synthetic-engine",
        run_mode=RunMode.SYNTHETIC,
        created_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
        git_commit="a" * 40,
        dataset_manifest_hash="b" * 64,
        signal_contract_hash="c" * 64,
        harness_contract_hash="d" * 64,
        preregistration_hash=hashlib.sha256(PREREGISTRATION_PAYLOAD).hexdigest(),
        setup_versions=("S3-v1", "S5-v1"),
        feature_version="DAY-D-FEATURES-v1",
        universe_version="DAY-D-UNIVERSE-v1",
        fill_version="DAY-D-FILL-v1",
        cost_model_version="DAY-D-COST-v1",
        fee_schedule_version="TEST-FEE-v1",
        risk_policy_version="DAY-D-RISK-v1",
        calendar_version="DAY-D-CALENDAR-v1",
        harness_version="DAY-D-HARNESS-v1",
        latency_scenario="0ms",
        cost_scenario=CostScenario.POINT,
        run_seed=1,
        data_gate_results=(),
        synthetic_truth_gate_passed=False,
    )


def test_engine_runs_s3_causally_and_t30_exits_only_net_positive() -> None:
    cutoff = datetime(2026, 8, 20, 16, tzinfo=NEW_YORK)
    universe = UniverseManifest(
        session_date=SESSION,
        previous_session_date=date(2026, 8, 20),
        generated_at=_at(9, 25),
        information_cutoff_at=cutoff,
        universe_version="DAY-D-UNIVERSE-v1",
        members=(
            UniverseMember(
                rank=1,
                symbol="AAA",
                issuer_id="issuer-aaa",
                listing_mic="XNAS",
                security_type="US_DOMESTIC_OPERATING_COMPANY_COMMON_STOCK",
                d1_close_usd=100.0,
                median_dollar_volume_20d_usd=100_000_000,
                history_session_count=20,
                liquidity_quintile=1,
                data_as_of=cutoff,
            ),
        ),
        shortfall=59,
    )
    quotes = (
        Quote("entry", "AAA", _at(9, 46, 1), _at(9, 46, 1), 101.60, 101.62, 1000, 1000),
        Quote("t30", "AAA", _at(15, 59, 31), _at(15, 59, 31), 102.00, 102.02, 1000, 1000),
    )
    qqq_quotes = (
        Quote("qqq", "QQQ", _at(9, 46, 1), _at(9, 46, 1), 500.7, 500.8, 1000, 1000),
    )
    session = ReplaySession(
        session_date=SESSION,
        previous_session_date=date(2026, 8, 20),
        regular_open=_at(9, 30),
        official_close=_at(16, 0),
        universe=universe,
        bars_by_symbol={"AAA": _bars("AAA"), "QQQ": _bars("QQQ", qqq=True)},
        prior_volume_curves_by_symbol={
            "AAA": _prior_curves("AAA"),
            "QQQ": _prior_curves("QQQ"),
        },
        d1_official_closes={
            "AAA": _close("AAA", date(2026, 8, 20), 100.0),
            "QQQ": _close("QQQ", date(2026, 8, 20), 500.0),
        },
        tapes_by_symbol={
            "AAA": MarketTape(symbol="AAA", trades=(), quotes=quotes),
            "QQQ": MarketTape(symbol="QQQ", trades=(), quotes=qqq_quotes),
        },
        official_closes={"AAA": _close("AAA", SESSION, 102.0)},
        quote_max_age_milliseconds_by_bucket={
            "OPEN_15": 2000,
            "OPEN_60": 2000,
            "MIDDAY": 2000,
            "CLOSE_30": 2000,
            "CLOSE_5": 2000,
        },
    )
    fee = FeeSchedule(
        version="TEST-FEE-v1",
        source="test",
        effective_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        captured_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        content_hash="f" * 64,
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
                1,
                "ALL",
                0.0,
                0.0,
                100,
                date(2026, 8, 20),
                datetime(2026, 8, 20, 17, tzinfo=NEW_YORK),
            ),
        ),
    )

    result = DayDReplayHarness(manifest=_manifest()).run(
        ReplayDataset(
            sessions=(session,),
            checksums={},
            fee_schedule=fee,
            cost_table=cost,
        )
    )

    accepted_s3 = [
        evaluation
        for evaluation in result.evaluations
        if evaluation.setup_version == "S3-v1" and evaluation.accepted
    ]
    assert len(accepted_s3) == 1
    assert accepted_s3[0].signal is not None
    assert accepted_s3[0].signal.decision_at == _at(9, 46)
    accepted_audits = [audit for audit in result.entry_audits if audit.entry_accepted]
    assert len(accepted_audits) == 1
    audit = accepted_audits[0]
    assert audit.universe_rank == 1
    assert audit.gate_result is True
    assert audit.outcome_reason == "ACCEPTED"
    assert audit.post_floor_stop is not None
    assert audit.risk_budget_usd == pytest.approx(1_000_000.0 * 0.0015)
    assert audit.final_fill is not None
    assert audit.final_fill.filled_at == _at(9, 46, 1)
    assert len(result.closed_trades) == 1
    trade = result.closed_trades[0]
    assert trade.entry_fill.filled_at == _at(9, 46, 1)
    assert trade.exit_fills[-1].kind == "T30_NET_POSITIVE_EXIT"
    assert trade.net_pnl_usd > 0
    assert result.open_positions == ()
    assert result.ending_nav_usd > 1_000_000.0

    negative_t30 = replace(
        session,
        tapes_by_symbol={
            "AAA": MarketTape(
                symbol="AAA",
                trades=(),
                quotes=(
                    quotes[0],
                    Quote(
                        "negative-t30",
                        "AAA",
                        _at(15, 59, 31),
                        _at(15, 59, 31),
                        101.0,
                        101.02,
                        1000,
                        1000,
                    ),
                ),
            ),
            "QQQ": MarketTape(symbol="QQQ", trades=(), quotes=qqq_quotes),
        },
        official_closes={"AAA": _close("AAA", SESSION, 103.0)},
    )
    carried = DayDReplayHarness(manifest=_manifest()).run(
        ReplayDataset(
            sessions=(negative_t30,),
            checksums={},
            fee_schedule=fee,
            cost_table=cost,
        )
    )
    assert len(carried.open_positions) == 1
    open_position = carried.open_positions[0]
    assert carried.ending_nav_usd == pytest.approx(
        carried.ending_cash_usd + open_position.remaining_quantity * 103.0
    )
    transfer = [
        record
        for record in carried.ledger
        if record.event_type == "official_close_transfer_mark"
    ]
    assert len(transfer) == 1
    assert transfer[0].metadata["official_close_price"] == 103.0

    flat = DayDReplayHarness(
        manifest=_manifest()
    ).run_flat_at_close_counterfactual(
        ReplayDataset(
            sessions=(negative_t30,),
            checksums={},
            fee_schedule=fee,
            cost_table=cost,
        )
    )
    assert flat.book_policy == "flat_at_close"
    assert flat.open_positions == ()
    assert flat.ending_nav_usd == pytest.approx(flat.ending_cash_usd)
    assert len(flat.closed_trades) == 1
    counterfactual_fill = flat.closed_trades[0].exit_fills[-1]
    assert counterfactual_fill.kind == "OFFICIAL_CLOSE_COUNTERFACTUAL"
    assert counterfactual_fill.filled_at == negative_t30.official_close
    assert counterfactual_fill.economic_price == 103.0
    assert counterfactual_fill.spread_cost_per_share_usd == 0.0
    assert not any(
        record.event_type == "official_close_transfer_mark"
        for record in flat.ledger
    )

    prewindow_quote_at = _at(15, 59, 29) + timedelta(milliseconds=500)
    static_inside_window = replace(
        session,
        tapes_by_symbol={
            "AAA": MarketTape(
                symbol="AAA",
                trades=(),
                quotes=(
                    quotes[0],
                    Quote(
                        "fresh-before-t30",
                        "AAA",
                        prewindow_quote_at,
                        prewindow_quote_at,
                        102.0,
                        102.02,
                        1000,
                        1000,
                    ),
                ),
            ),
            "QQQ": MarketTape(symbol="QQQ", trades=(), quotes=qqq_quotes),
        },
    )
    polled = DayDReplayHarness(manifest=_manifest()).run(
        ReplayDataset(
            sessions=(static_inside_window,),
            checksums={},
            fee_schedule=fee,
            cost_table=cost,
        )
    )
    assert polled.closed_trades[0].exit_fills[-1].decision_at == _at(15, 59, 30)

    no_t30_lookahead = replace(
        session,
        tapes_by_symbol={
            "AAA": MarketTape(
                symbol="AAA",
                trades=(
                    TradePrint(
                        "future-positive-trade",
                        "AAA",
                        _at(15, 59, 31),
                        _at(15, 59, 31),
                        102.0,
                        10,
                    ),
                ),
                quotes=(
                    quotes[0],
                    Quote(
                        "observable-negative-bid",
                        "AAA",
                        _at(15, 59, 30),
                        _at(15, 59, 30),
                        101.0,
                        101.02,
                        1000,
                        1000,
                    ),
                ),
            ),
            "QQQ": MarketTape(symbol="QQQ", trades=(), quotes=qqq_quotes),
        },
        official_closes={"AAA": _close("AAA", SESSION, 102.0)},
    )
    no_lookahead_result = DayDReplayHarness(manifest=_manifest()).run(
        ReplayDataset(
            sessions=(no_t30_lookahead,),
            checksums={},
            fee_schedule=fee,
            cost_table=cost,
        )
    )
    assert no_lookahead_result.closed_trades == ()
    assert len(no_lookahead_result.open_positions) == 1

    too_late_quote = replace(
        session,
        tapes_by_symbol={
            "AAA": MarketTape(
                symbol="AAA",
                trades=(),
                quotes=(
                    quotes[0],
                    Quote(
                        "positive-at-last-second",
                        "AAA",
                        _at(15, 59, 59),
                        _at(15, 59, 59),
                        102.0,
                        102.02,
                        1000,
                        1000,
                    ),
                ),
            ),
            "QQQ": MarketTape(symbol="QQQ", trades=(), quotes=qqq_quotes),
        },
    )
    late_result = DayDReplayHarness(
        manifest=replace(_manifest(), latency_scenario="2000ms")
    ).run(
        ReplayDataset(
            sessions=(too_late_quote,),
            checksums={},
            fee_schedule=fee,
            cost_table=cost,
        )
    )
    assert len(late_result.open_positions) == 1
    late_event = next(
        rejection
        for rejection in late_result.rejections
        if rejection.reason == "LATE_UNFILLED_EXIT"
    )
    assert late_event.event_at == _at(15, 59, 59)
    assert late_event.metadata["estimated_net_exit_pnl_usd"] > 0

    created_at = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    checksums = {"synthetic-session.ndjson": "c" * 64}
    official_manifest = replace(
        _manifest(),
        run_id="official-matrix-test",
        run_mode=RunMode.OFFICIAL,
        created_at=created_at,
        dataset_manifest_hash=dataset_manifest_hash(checksums),
        signal_contract_hash=sha256_file(SIGNAL_CONTRACT_PATH),
        harness_contract_hash=sha256_file(HARNESS_CONTRACT_PATH),
        preregistration_hash=hashlib.sha256(PREREGISTRATION_PAYLOAD).hexdigest(),
        data_gate_results=tuple(
            DataGateResult(
                gate=gate,
                passed=True,
                measured_at=created_at,
                evidence_hash="f" * 64,
                git_commit="a" * 40,
            )
            for gate in ("T1_TRADE_COVERAGE", "T4_BBO_QUALITY", "T5_BAR_AND_CLOSE")
        ),
        synthetic_truth_gate_passed=True,
    )
    truth = run_synthetic_truth_gate(
        git_commit=official_manifest.git_commit,
        measured_at=created_at,
    )
    official_dataset = ReplayDataset(
        sessions=(
            replace(
                static_inside_window,
                corporate_action_coverage_hash="a" * 64,
            ),
        ),
        checksums=checksums,
        fee_schedule=fee,
        cost_table=cost,
        synthetic_truth=truth,
        preregistration_payload=PREREGISTRATION_PAYLOAD,
    )

    matrix = DayDReplayHarness(
        manifest=official_manifest
    ).run_fragility_matrix(official_dataset)

    assert len(matrix.results) == 30
    assert {
        result.book_policy for result in matrix.results.values()
    } == {"operational", "flat_at_close"}
    assert (
        "book=operational|latency=1000ms|cost=pessimistic"
        in matrix.results
    )
    assert matrix.books_share_identical_signals is True
    assert len(matrix.cost_monotonic_by_latency) == 10
    assert matrix.passed_fragility_gate is True
