from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.day_d_replay.costs import CostTable, time_bucket
from app.day_d_replay.execution import ExecutionModel, MarketTape
from app.day_d_replay.engine import DayDReplayHarness, ReplaySession, _ManagedPosition
from app.day_d_replay.ledger import build_closed_trade
from app.day_d_replay.models import (
    AdministrativeUnavailability,
    BarFeature,
    CorporateAction,
    CorporateActionKind,
    CostScenario,
    FeeSchedule,
    Fill,
    HaltInterval,
    MinuteBar,
    Position,
    PriorVolumeCurve,
    Quote,
    SecurityDailySnapshot,
    SetupSignal,
    Side,
    SpreadCell,
    TradePrint,
    UniverseManifest,
)
from app.day_d_replay.sizing import size_position
from app.day_d_replay.universe import build_d1_universe

NEW_YORK = ZoneInfo("America/New_York")


def _at(hour: int, minute: int, second: int = 0, millisecond: int = 0) -> datetime:
    return datetime(2026, 8, 21, hour, minute, second, millisecond * 1000, tzinfo=NEW_YORK)


def _fee() -> FeeSchedule:
    return FeeSchedule(
        version="DAY-D-FEE-v1",
        source="test",
        effective_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        captured_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        content_hash="f" * 64,
        commission_per_share_usd=0.0035,
        minimum_commission_usd=0.0,
        sec_section_31_rate=0.0,
        finra_taf_per_share_usd=0.0,
        finra_taf_cap_usd=0.0,
    )


def _signal() -> SetupSignal:
    return SetupSignal(
        setup_version="S3-v1",
        symbol="AAA",
        session_date=date(2026, 8, 21),
        signal_event_at=_at(10, 0),
        signal_available_at=_at(10, 0),
        decision_at=_at(10, 0),
        activation_price=100.0,
        expires_at=_at(10, 3),
        structural_stop=99.0,
        stop_rule="test",
        entry_atr=0.5,
        decision_vwap=99.5,
        rvol=2.0,
        minimum_tick=0.01,
        gate_values={},
    )


def test_bar_and_quote_availability_are_causal() -> None:
    with pytest.raises(ValueError, match="cannot be available"):
        MinuteBar(
            symbol="AAA",
            start_at=_at(9, 30),
            end_at=_at(9, 31),
            available_at=_at(9, 30, 59),
            open=100,
            high=101,
            low=99,
            close=100,
            volume=100,
        )

    future_arrival = Quote(
        "future",
        "AAA",
        _at(10, 0, 1),
        _at(10, 0, 5),
        100.0,
        100.1,
        10,
        10,
    )
    tape = MarketTape(symbol="AAA", trades=(), quotes=(future_arrival,))
    assert tape.latest_quote(_at(10, 0, 2)) is None


def test_crossed_bbo_is_rejected_and_locked_bbo_with_depth_is_eligible() -> None:
    crossed = Quote(
        "crossed", "AAA", _at(10, 0), _at(10, 0), 100.1, 100.0, 10, 10
    )
    locked = Quote(
        "locked", "AAA", _at(10, 0, 1), _at(10, 0, 1), 100.0, 100.0, 10, 10
    )
    tape = MarketTape(symbol="AAA", trades=(), quotes=(crossed, locked))

    assert tape.latest_quote(_at(10, 0)) is None
    assert tape.latest_quote(_at(10, 0, 1)) is locked


def test_replay_session_rejects_a_future_volume_curve() -> None:
    curve = PriorVolumeCurve(
        symbol="AAA",
        session_date=date(2026, 8, 22),
        available_at=_at(9, 0),
        cumulative_volume_by_minute=((0, 100.0),),
    )

    universe = UniverseManifest(
        session_date=date(2026, 8, 21),
        previous_session_date=date(2026, 8, 20),
        generated_at=_at(9, 25),
        information_cutoff_at=datetime(2026, 8, 20, 16, tzinfo=NEW_YORK),
        universe_version="DAY-D-UNIVERSE-v1",
        members=(),
        shortfall=60,
    )

    with pytest.raises(ValueError, match="future volume curve"):
        ReplaySession(
            session_date=date(2026, 8, 21),
            previous_session_date=date(2026, 8, 20),
            regular_open=_at(9, 30),
            official_close=_at(16, 0),
            universe=universe,
            bars_by_symbol={},
            prior_volume_curves_by_symbol={"AAA": (curve,)},
            d1_official_closes={},
            tapes_by_symbol={},
            official_closes={},
            quote_max_age_milliseconds_by_bucket={
                "OPEN_15": 1000,
                "OPEN_60": 1000,
                "MIDDAY": 1000,
                "CLOSE_30": 1000,
                "CLOSE_5": 1000,
            },
        )


def test_signal_bar_cannot_activate_its_own_fill() -> None:
    same = TradePrint("same", "AAA", _at(10, 0), _at(10, 0), 101.0, 100)
    later = TradePrint("later", "AAA", _at(10, 0, 1), _at(10, 0, 1), 101.0, 100)

    activation = MarketTape(symbol="AAA", trades=(same, later), quotes=()).first_activation(
        _signal()
    )

    assert activation is not None
    assert activation.source_id == "later"


def test_entry_latency_starts_when_activation_becomes_observable() -> None:
    activation = TradePrint(
        "delayed-activation",
        "AAA",
        _at(10, 0, 1),
        _at(10, 0, 5),
        101.0,
        100,
    )
    arrival = _at(10, 0, 5, 500)
    quote = Quote("arrival-bbo", "AAA", arrival, arrival, 101.0, 101.1, 100, 100)
    tape = MarketTape(symbol="AAA", trades=(activation,), quotes=(quote,))
    model = ExecutionModel(
        fee_schedule=_fee(), run_seed=1, fixed_latency_milliseconds=500
    )

    fill = model.fill_entry(
        signal=_signal(),
        tape=tape,
        quantity=10,
        half_spread_usd=0.05,
        quote_max_age_milliseconds=1000,
    )

    assert fill is not None
    assert fill.decision_at == _at(10, 0, 5)
    assert fill.arrival_at == arrival


def test_stop_requires_two_distinct_prints_and_recovery_resets_sequence() -> None:
    trades = (
        TradePrint("one", "AAA", _at(10, 1, 0), _at(10, 1, 0), 99.0, 30),
        TradePrint("recover", "AAA", _at(10, 1, 0, 150), _at(10, 1, 0, 150), 99.1, 30),
        TradePrint("two", "AAA", _at(10, 1, 0, 300), _at(10, 1, 0, 300), 99.0, 30),
        TradePrint("three", "AAA", _at(10, 1, 0, 450), _at(10, 1, 0, 450), 98.9, 30),
    )
    tape = MarketTape(symbol="AAA", trades=trades, quotes=())

    trigger = ExecutionModel.find_stop_trigger(
        tape=tape,
        stop_level=99.0,
        after=_at(10, 0),
        before=_at(10, 2),
    )

    assert trigger is not None
    assert trigger.trade_id == "three"


def test_stop_crossed_during_halt_fills_at_reopening_not_old_stop() -> None:
    halt = HaltInterval("AAA", _at(10, 1), _at(10, 5), _at(10, 1))
    reopening = TradePrint("reopen", "AAA", _at(10, 5), _at(10, 5), 95.0, 100)
    tape = MarketTape(symbol="AAA", trades=(reopening,), quotes=(), halts=(halt,))
    model = ExecutionModel(
        fee_schedule=_fee(), run_seed=1, fixed_latency_milliseconds=500
    )

    fill = model.fill_stop_from_trigger(
        tape=tape,
        symbol="AAA",
        stop_level=99.0,
        trigger=reopening,
        before=_at(16, 0),
        quantity=10,
        half_spread_usd=0.05,
        kind="INITIAL_STOP_REOPENING",
        order_key="reopen",
        reopening_halt=halt,
    )

    assert fill is not None
    assert fill.filled_at == _at(10, 5)
    assert fill.economic_price == pytest.approx(94.9)


def test_cost_table_never_uses_current_or_future_session() -> None:
    table = CostTable.from_cells(
        "DAY-D-COST-v1",
        (
            SpreadCell(
                1, "OPEN_15", 0.01, 0.02, 100, date(2026, 8, 20), _at(9, 0)
            ),
            SpreadCell(
                1, "OPEN_15", 0.50, 0.60, 100, date(2026, 8, 21), _at(9, 0)
            ),
        ),
    )

    value = table.half_spread(
        liquidity_quintile=1,
        bucket="OPEN_15",
        scenario=CostScenario.POINT,
        replay_session=date(2026, 8, 21),
        information_cutoff_at=_at(9, 30),
    )

    assert value == pytest.approx(0.02)


def test_cost_table_ignores_a_cell_computed_after_the_replay_cutoff() -> None:
    table = CostTable.from_cells(
        "DAY-D-COST-v1",
        (
            SpreadCell(
                1, "OPEN_15", 0.01, 0.02, 100, date(2026, 8, 20), _at(9, 0)
            ),
            SpreadCell(
                1, "OPEN_15", 0.50, 0.60, 100, date(2026, 8, 20), _at(10, 0)
            ),
        ),
    )

    value = table.half_spread(
        liquidity_quintile=1,
        bucket="OPEN_15",
        scenario=CostScenario.POINT,
        replay_session=date(2026, 8, 21),
        information_cutoff_at=_at(9, 30),
    )

    assert value == pytest.approx(0.02)


def test_cost_buckets_follow_an_exchange_early_close() -> None:
    regular_open = _at(9, 30)
    early_close = _at(13, 0)

    assert time_bucket(
        _at(12, 29, 59),
        regular_open=regular_open,
        official_close=early_close,
    ) == "MIDDAY"
    assert time_bucket(
        _at(12, 30),
        regular_open=regular_open,
        official_close=early_close,
    ) == "CLOSE_30"
    assert time_bucket(
        _at(12, 55),
        regular_open=regular_open,
        official_close=early_close,
    ) == "CLOSE_5"


def test_sizing_rejects_instead_of_resizing_notional_and_participation() -> None:
    oversized = size_position(
        signal=_signal(),
        entry_price=100.0,
        entry_vwap=99.5,
        entry_at=_at(10, 0),
        nav_usd=1_000_000.0,
        cash_usd=1_000_000.0,
        prior_five_minute_volume_shares=1_000_000.0,
        point_half_spread_usd=0.02,
        fee_schedule=_fee(),
    )

    assert oversized.accepted is False
    assert oversized.reason == "POSITION_NOTIONAL_CAP_BREACH"
    assert oversized.quantity == 0

    wider_stop_signal = replace(_signal(), decision_vwap=99.0)
    illiquid = size_position(
        signal=wider_stop_signal,
        entry_price=100.0,
        entry_vwap=99.0,
        entry_at=_at(10, 0),
        nav_usd=1_000_000.0,
        cash_usd=1_000_000.0,
        prior_five_minute_volume_shares=1_000.0,
        point_half_spread_usd=0.02,
        fee_schedule=_fee(),
    )

    assert illiquid.accepted is False
    assert illiquid.reason == "PARTICIPATION_CAP_BREACH"
    assert illiquid.quantity == 0


def test_universe_ignores_correction_received_after_d1_close() -> None:
    d1 = date(2026, 8, 20)
    cutoff = datetime(2026, 8, 20, 16, tzinfo=NEW_YORK)
    snapshots: list[SecurityDailySnapshot] = []
    for offset in range(20):
        session = d1 - timedelta(days=19 - offset)
        snapshots.append(
            SecurityDailySnapshot(
                session_date=session,
                available_at=cutoff - timedelta(days=20 - offset),
                symbol="AAA",
                issuer_id="issuer-aaa",
                listing_mic="XNAS",
                security_type="US_DOMESTIC_OPERATING_COMPANY_COMMON_STOCK",
                adjusted_close_usd=100.0,
                adjusted_regular_volume=1_000_000,
            )
        )
    snapshots.append(
        SecurityDailySnapshot(
            session_date=d1,
            available_at=cutoff + timedelta(hours=12),
            symbol="AAA",
            issuer_id="issuer-aaa",
            listing_mic="XNAS",
            security_type="US_DOMESTIC_OPERATING_COMPANY_COMMON_STOCK",
            adjusted_close_usd=1.0,
            adjusted_regular_volume=1,
        )
    )

    universe = build_d1_universe(
        session_date=date(2026, 8, 21),
        previous_session_date=d1,
        generated_at=datetime(2026, 8, 21, 9, 25, tzinfo=NEW_YORK),
        d1_information_cutoff_at=cutoff,
        snapshots=snapshots,
        selection_count=1,
    )

    assert universe.members[0].symbol == "AAA"
    assert universe.members[0].d1_close_usd == 100.0
    assert universe.members[0].data_as_of <= cutoff


def test_forbidden_intraday_reason_cannot_substitute_universe_member() -> None:
    with pytest.raises(ValueError, match="cannot remove"):
        build_d1_universe(
            session_date=date(2026, 8, 21),
            previous_session_date=date(2026, 8, 20),
            generated_at=_at(9, 25),
            d1_information_cutoff_at=datetime(2026, 8, 20, 16, tzinfo=NEW_YORK),
            snapshots=[],
            unavailability=(
                AdministrativeUnavailability("AAA", "MISSING_LIVE_QUOTE", _at(9, 20)),
            ),
        )


def test_ledger_preserves_intraday_plus_overnight_identity_and_raw_tail() -> None:
    entry = Fill(
        "AAA", Side.BUY, "entry", _at(15, 0), _at(15, 0), _at(15, 0),
        100.0, 100.0, 100, 0.0, 0.0, None, "entry", 0, 0, False,
    )
    exit_fill = Fill(
        "AAA", Side.SELL, "target",
        _at(10, 0) + timedelta(days=1),
        _at(10, 0) + timedelta(days=1),
        _at(10, 0) + timedelta(days=1),
        107.0, 107.0, 100, 0.0, 0.0, None, "exit", 0, 0, False,
    )
    position = Position(
        position_id="p1",
        setup_version="S3-v1",
        symbol="AAA",
        session_date=date(2026, 8, 21),
        quantity=100,
        entry_fill=entry,
        average_cost_per_share=100.0,
        risk_budget_usd=100.0,
        risk_per_share_usd=1.0,
        initial_stop=99.0,
        target_price=None,
        entry_atr=0.5,
        high_water=107.0,
        remaining_quantity=100,
    )

    closed, records = build_closed_trade(
        position=position,
        exit_fills=(exit_fill,),
        entry_official_close_at=_at(16, 0),
        entry_official_close_price=101.0,
    )

    assert closed.raw_r == pytest.approx(7.0)
    assert closed.raw_r > 5.0
    assert closed.consolidated_r == pytest.approx(closed.intraday_r + closed.overnight_r)
    assert any(record.event_type == "official_close_transfer_mark" for record in records)

    persisted_transfer, no_duplicate_records = build_closed_trade(
        position=position,
        exit_fills=(exit_fill,),
        entry_official_close_at=_at(16, 0),
        entry_official_close_price=101.0,
        include_transfer_record=False,
    )

    assert persisted_transfer.intraday_r == pytest.approx(closed.intraday_r)
    assert persisted_transfer.overnight_r == pytest.approx(closed.overnight_r)
    assert persisted_transfer.consolidated_r == pytest.approx(closed.consolidated_r)
    assert not any(
        record.event_type == "official_close_transfer_mark"
        for record in no_duplicate_records
    )


def test_ledger_lifetime_values_follow_event_time_even_when_rows_are_suppressed() -> None:
    entry = Fill(
        "AAA", Side.BUY, "entry", _at(15, 0), _at(15, 0), _at(15, 0),
        100.0, 100.0, 10, 0.0, 0.0, None, "entry", 0, 0, False,
    )
    exit_fill = Fill(
        "AAA", Side.SELL, "exit",
        _at(10, 0) + timedelta(days=1),
        _at(10, 0) + timedelta(days=1),
        _at(10, 0) + timedelta(days=1),
        101.0, 101.0, 10, 0.0, 0.0, None, "exit", 0, 0, False,
    )
    position = Position(
        position_id="chronological-ledger",
        setup_version="S3-v1",
        symbol="AAA",
        session_date=date(2026, 8, 21),
        quantity=10,
        entry_fill=entry,
        average_cost_per_share=100.0,
        risk_budget_usd=100.0,
        risk_per_share_usd=10.0,
        initial_stop=90.0,
        target_price=None,
        entry_atr=5.0,
        high_water=101.0,
        remaining_quantity=10,
    )

    closed, records = build_closed_trade(
        position=position,
        exit_fills=(exit_fill,),
        entry_official_close_at=_at(16, 0),
        entry_official_close_price=100.0,
        cash_dividends=((_at(9, 0) + timedelta(days=1), 5.0),),
        include_transfer_record=False,
        include_dividend_records=False,
    )

    exit_record = next(record for record in records if record.event_type == "exit_fill")
    assert closed.net_pnl_usd == pytest.approx(15.0)
    assert exit_record.raw_r_lifetime_after_event == pytest.approx(0.15)


def test_carried_chandelier_ignores_trade_unavailable_by_official_close() -> None:
    entry = Fill(
        "AAA",
        Side.BUY,
        "entry",
        _at(15, 0),
        _at(15, 0),
        _at(15, 0),
        100.0,
        100.0,
        10,
        0.0,
        0.0,
        None,
        "entry",
        0,
        0,
        False,
    )
    position = Position(
        position_id="stale-high-water",
        setup_version="S3-v1",
        symbol="AAA",
        session_date=date(2026, 8, 21),
        quantity=10,
        entry_fill=entry,
        average_cost_per_share=100.0,
        risk_budget_usd=10.0,
        risk_per_share_usd=1.0,
        initial_stop=99.0,
        target_price=None,
        entry_atr=0.5,
        high_water=100.0,
        remaining_quantity=10,
        partial_filled=True,
        chandelier_activated=True,
    )
    state = _ManagedPosition(
        position=position,
        liquidity_quintile=1,
        aliases={"AAA"},
        last_mark=100.0,
    )
    delayed = TradePrint(
        "delayed",
        "AAA",
        _at(15, 59),
        _at(16, 0, 1),
        110.0,
        100,
    )
    bar = MinuteBar(
        symbol="AAA",
        start_at=_at(15, 58),
        end_at=_at(15, 59),
        available_at=_at(15, 59),
        open=100.0,
        high=100.1,
        low=99.9,
        close=100.0,
        volume=100,
    )
    session = SimpleNamespace(
        tapes_by_symbol={
            "AAA": MarketTape(symbol="AAA", trades=(delayed,), quotes=())
        }
    )

    DayDReplayHarness._advance_chandelier_state(
        state=state,
        session=session,
        features=[BarFeature(bar, 100.0, 100.0, 1.0, 0.5)],
        through=_at(16, 0),
    )

    assert position.high_water == 100.0
    assert position.chandelier_stop is None


def test_overnight_position_includes_prints_at_the_opening_timestamp() -> None:
    prior_day = _at(15, 0) - timedelta(days=1)
    entry = Fill(
        "AAA",
        Side.BUY,
        "entry",
        prior_day,
        prior_day,
        prior_day,
        100.0,
        100.0,
        10,
        0.0,
        0.0,
        None,
        "entry-prior-day",
        0,
        0,
        False,
    )
    position = Position(
        position_id="overnight-open",
        setup_version="S5-v1",
        symbol="AAA",
        session_date=prior_day.date(),
        quantity=10,
        entry_fill=entry,
        average_cost_per_share=100.0,
        risk_budget_usd=10.0,
        risk_per_share_usd=1.0,
        initial_stop=99.0,
        target_price=101.0,
        entry_atr=0.5,
        high_water=100.0,
        remaining_quantity=10,
    )
    state = _ManagedPosition(
        position=position,
        liquidity_quintile=1,
        aliases={"AAA"},
        last_mark=100.0,
    )

    scan_after = DayDReplayHarness._initial_exit_scan_after(
        state,
        SimpleNamespace(regular_open=_at(9, 30)),
    )

    assert scan_after == _at(9, 30) - timedelta(microseconds=1)


def test_split_and_dividend_preserve_position_value_and_credit_cash() -> None:
    entry = Fill(
        "AAA",
        Side.BUY,
        "entry",
        _at(10, 0),
        _at(10, 0),
        _at(10, 0),
        100.0,
        100.0,
        10,
        0.0,
        0.0,
        None,
        "entry-action",
        0,
        0,
        False,
    )
    position = Position(
        position_id="corporate-action",
        setup_version="S3-v1",
        symbol="AAA",
        session_date=date(2026, 8, 21),
        quantity=10,
        entry_fill=entry,
        average_cost_per_share=100.0,
        risk_budget_usd=10.0,
        risk_per_share_usd=1.0,
        initial_stop=99.0,
        target_price=None,
        entry_atr=0.5,
        high_water=102.0,
        remaining_quantity=10,
    )
    state = _ManagedPosition(
        position=position,
        liquidity_quintile=1,
        aliases={"AAA"},
        last_mark=102.0,
    )
    open_states = {position.position_id: state}
    harness = DayDReplayHarness(manifest=SimpleNamespace())
    ledger = []
    split_at = _at(11, 0)
    split = CorporateAction(
        action_id="split-2-for-1",
        symbol="AAA",
        kind=CorporateActionKind.SPLIT,
        event_at=split_at - timedelta(days=1),
        available_at=split_at - timedelta(days=1),
        effective_at=split_at,
        ratio=2.0,
    )

    cash = harness._apply_corporate_action(
        action=split,
        open_states=open_states,
        cash=1_000.0,
        session=SimpleNamespace(),
        closed_trades=[],
        ledger=ledger,
    )

    assert cash == 1_000.0
    assert position.quantity == 20
    assert position.remaining_quantity == 20
    assert position.average_cost_per_share == 50.0
    assert position.initial_stop == 49.5
    assert state.last_mark == 51.0
    assert position.quantity * state.last_mark == pytest.approx(10 * 102.0)

    dividend_at = _at(12, 0)
    dividend = CorporateAction(
        action_id="cash-dividend",
        symbol="AAA",
        kind=CorporateActionKind.CASH_DIVIDEND,
        event_at=dividend_at - timedelta(days=1),
        available_at=dividend_at - timedelta(days=1),
        effective_at=dividend_at,
        cash_per_share_usd=0.50,
    )
    cash = harness._apply_corporate_action(
        action=dividend,
        open_states=open_states,
        cash=cash,
        session=SimpleNamespace(),
        closed_trades=[],
        ledger=ledger,
    )

    assert cash == pytest.approx(1_010.0)
    assert state.dividends == [(dividend_at, 10.0)]
    assert ledger[-1].event_type == "cash_dividend"
    assert ledger[-1].cash_delta_usd == 10.0


def test_effective_terminal_action_blocks_a_new_entry_but_dividend_does_not() -> None:
    merger = CorporateAction(
        action_id="merger",
        symbol="AAA",
        kind=CorporateActionKind.CASH_MERGER,
        event_at=_at(9, 0),
        available_at=_at(9, 0),
        effective_at=_at(10, 0),
        consideration_per_share_usd=100.0,
    )
    dividend = CorporateAction(
        action_id="dividend",
        symbol="AAA",
        kind=CorporateActionKind.CASH_DIVIDEND,
        event_at=_at(9, 0),
        available_at=_at(9, 0),
        effective_at=_at(10, 0),
        cash_per_share_usd=0.25,
    )

    blocked = DayDReplayHarness._entry_blocking_corporate_action(
        session=SimpleNamespace(corporate_actions=(dividend, merger)),
        symbol="AAA",
        filled_at=_at(10, 1),
    )
    before_effective = DayDReplayHarness._entry_blocking_corporate_action(
        session=SimpleNamespace(corporate_actions=(dividend, merger)),
        symbol="AAA",
        filled_at=_at(9, 59),
    )

    assert blocked is merger
    assert before_effective is None
