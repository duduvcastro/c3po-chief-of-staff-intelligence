from __future__ import annotations

import csv
import gzip
import hashlib
import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.r2d2_exit_policy_engine import (
    ConsistencyGateError,
    Episode,
    LedgerFill,
    PolicyOutcome,
    StudyBar,
    build_episodes,
    classify_market_compatibility,
    paired_session_bootstrap,
    reconcile_binding_gate,
    simulate_mechanical,
    simulate_overlay,
)
from app.r2d2_exit_policy_study import (
    ExitPolicyStudyError,
    MinuteAggregateReader,
    _frozen_ledger_input,
    build_report,
    canonical_sha256,
    require_off_hours,
    write_immutable_json,
)
from app.config import Settings


UTC = timezone.utc
SESSION_OPEN = datetime(2026, 8, 20, 13, 30, tzinfo=UTC)


def _buy(
    *,
    fill_id: str = "buy",
    at: datetime = SESSION_OPEN,
    signal: float = 100.0,
    quantity: float = 10.0,
    symbol: str = "TEST",
    snapshot: dict | None = None,
    quote_as_of: datetime | None = None,
) -> LedgerFill:
    fill = signal * 1.001
    gross = quantity * fill
    fees = gross * 0.0004
    return LedgerFill(
        id=fill_id,
        market="NASDAQ",
        symbol=symbol,
        name=symbol,
        side="BUY",
        quantity=quantity,
        signal_price_local=signal,
        fill_price_local=fill,
        fx_to_usd=1.0,
        gross_value_usd=gross,
        fees_usd=fees,
        slippage_usd=quantity * (fill - signal),
        realized_pnl_usd=None,
        reason="entry",
        decision_snapshot=snapshot or {"stop_price": 99.0},
        executed_at=at,
        quote_as_of=quote_as_of or at,
    )


def _sell(
    *,
    average_cost: float,
    fill_id: str,
    at: datetime,
    signal: float,
    quantity: float,
    symbol: str = "TEST",
    reason: str = "exit",
    snapshot: dict | None = None,
    quote_as_of: datetime | None = None,
) -> LedgerFill:
    fill = signal * 0.999
    gross = quantity * fill
    fees = gross * 0.0004
    realized = gross - fees - quantity * average_cost
    return LedgerFill(
        id=fill_id,
        market="NASDAQ",
        symbol=symbol,
        name=symbol,
        side="SELL",
        quantity=quantity,
        signal_price_local=signal,
        fill_price_local=fill,
        fx_to_usd=1.0,
        gross_value_usd=gross,
        fees_usd=fees,
        slippage_usd=quantity * (signal - fill),
        realized_pnl_usd=realized,
        reason=reason,
        decision_snapshot=snapshot or {},
        executed_at=at,
        quote_as_of=quote_as_of or at,
    )


def _bar(
    minute: int,
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
    symbol: str = "TEST",
    session_offset: int = 0,
) -> StudyBar:
    return StudyBar(
        symbol=symbol,
        start_at=SESSION_OPEN + timedelta(days=session_offset, minutes=minute),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1_000.0,
    )


def _episode(fills: list[LedgerFill]) -> Episode:
    return Episode(
        id=f"NASDAQ:TEST:{fills[0].id}",
        market="NASDAQ",
        symbol="TEST",
        name="TEST",
        fills=tuple(fills),
        opened_at=fills[0].executed_at,
        closed_at=fills[-1].executed_at,
    )


def test_episode_builder_keeps_partial_legs_and_marks_operator_wind_down() -> None:
    buy = _buy(quantity=10)
    average_cost = (buy.gross_value_usd + buy.fees_usd) / buy.quantity
    partial = _sell(
        average_cost=average_cost,
        fill_id="partial",
        at=SESSION_OPEN + timedelta(minutes=2),
        signal=101.0,
        quantity=4,
    )
    final = _sell(
        average_cost=average_cost,
        fill_id="wind-down",
        at=SESSION_OPEN + timedelta(minutes=3),
        signal=100.0,
        quantity=6,
        snapshot={"operator_wind_down": {"operator": "Dudu"}},
    )

    episodes, counts = build_episodes([buy, partial, final])

    assert counts == {"corrected_rows_excluded": 0, "open_episodes": 0}
    assert len(episodes) == 1
    assert [fill.id for fill in episodes[0].fills] == ["buy", "partial", "wind-down"]
    assert episodes[0].strategy_excluded is True


def test_episode_builder_excludes_correction_rows_before_grouping() -> None:
    correction = _sell(
        average_cost=100.0,
        fill_id="correction",
        at=SESSION_OPEN,
        signal=100.0,
        quantity=1,
        snapshot={"correction": {"operator": "Dudu"}},
    )

    episodes, counts = build_episodes([correction])

    assert episodes == []
    assert counts["corrected_rows_excluded"] == 1


def test_binding_gate_reconciles_money_and_accepts_one_minute_boundary() -> None:
    buy = _buy(at=SESSION_OPEN + timedelta(seconds=59))
    average_cost = (buy.gross_value_usd + buy.fees_usd) / buy.quantity
    sell = _sell(
        average_cost=average_cost,
        fill_id="sell",
        at=SESSION_OPEN + timedelta(minutes=2),
        signal=100.5,
        quantity=10,
    )
    episode = _episode([buy, sell])
    bars = [
        _bar(1, open_=100.0, high=100.2, low=99.9, close=100.1),
        _bar(2, open_=100.3, high=100.6, low=100.2, close=100.4),
    ]

    gate = reconcile_binding_gate([episode], {"TEST": bars})

    assert gate["passed"] is True
    assert gate["checked_fills"] == 2
    assert gate["timestamp_boundary_tolerance_minutes"] == 1


def test_market_compatibility_uses_signal_and_classifies_in_amendment_order() -> None:
    contained = _buy(signal=100.0)
    clock_extended = _buy(
        fill_id="clock",
        at=SESSION_OPEN + timedelta(minutes=10),
        signal=100.0,
    )
    tolerance = _buy(fill_id="tolerance", signal=100.0)
    violation = _buy(fill_id="violation", signal=100.0)

    contained_bar = _bar(0, open_=100.0, high=100.05, low=99.95, close=100.0)
    clock_bar = _bar(5, open_=100.0, high=100.05, low=99.95, close=100.0)
    tolerance_bar = _bar(0, open_=100.25, high=100.3, low=100.2, close=100.25)
    violation_bar = _bar(0, open_=100.35, high=100.4, low=100.3, close=100.35)

    assert classify_market_compatibility(
        contained, {contained_bar.start_at: contained_bar},
    )["classification"] == "contained"
    assert classify_market_compatibility(
        clock_extended, {clock_bar.start_at: clock_bar},
    )["classification"] == "clock_extended"
    assert classify_market_compatibility(
        tolerance, {tolerance_bar.start_at: tolerance_bar},
    )["classification"] == "tolerance_band"
    assert classify_market_compatibility(
        violation, {violation_bar.start_at: violation_bar},
    )["classification"] == "violation"


def test_legacy_decomposition_uses_execution_window_not_quote_window() -> None:
    fill = _buy(
        at=SESSION_OPEN,
        quote_as_of=SESSION_OPEN + timedelta(minutes=3),
        signal=100.0,
    )
    execution_bar = _bar(0, open_=99.2, high=99.5, low=99.0, close=99.3)
    quote_bar = _bar(3, open_=100.1, high=100.2, low=99.9, close=100.1)

    result = classify_market_compatibility(
        fill,
        {
            execution_bar.start_at: execution_bar,
            quote_bar.start_at: quote_bar,
        },
    )

    assert result["classification"] == "contained"
    assert result["legacy_fill_contained"] is False


def test_g1_money_reconciliation_remains_exact_and_binding() -> None:
    buy = _buy()
    bad_buy = replace(buy, fees_usd=buy.fees_usd + 0.01)
    average_cost = (bad_buy.gross_value_usd + bad_buy.fees_usd) / bad_buy.quantity
    sell = _sell(
        average_cost=average_cost,
        fill_id="sell",
        at=SESSION_OPEN + timedelta(minutes=1),
        signal=100.5,
        quantity=10,
    )
    episode = _episode([bad_buy, sell])
    bars = [
        _bar(0, open_=100.0, high=100.2, low=99.9, close=100.1),
        _bar(1, open_=100.4, high=100.6, low=100.3, close=100.5),
    ]

    with pytest.raises(ConsistencyGateError) as raised:
        reconcile_binding_gate([episode], {"TEST": bars})

    assert any(item["gate"] == "fees_usd" for item in raised.value.failures)


def test_binding_gate_censors_violation_at_five_percent_without_blocking() -> None:
    buy = _buy()
    average_cost = (buy.gross_value_usd + buy.fees_usd) / buy.quantity
    sell = _sell(
        average_cost=average_cost,
        fill_id="sell",
        at=SESSION_OPEN + timedelta(minutes=1),
        signal=100.5,
        quantity=10,
    )
    episode = _episode([buy, sell])
    bars = [
        _bar(0, open_=99.0, high=99.5, low=98.5, close=99.1),
        _bar(1, open_=100.5, high=100.6, low=100.5, close=100.55),
    ]

    gate = reconcile_binding_gate(
        [episode],
        {"TEST": bars},
        constructed_episode_count=20,
    )

    compatibility = gate["market_compatibility"]
    assert gate["passed"] is True
    assert compatibility["coverage_censored_episode_ids"] == [episode.id]
    assert compatibility["coverage_censored_percent"] == pytest.approx(5.0)
    assert compatibility["threshold_passed"] is True


def test_binding_gate_fails_closed_above_violation_episode_limit() -> None:
    buy = _buy()
    average_cost = (buy.gross_value_usd + buy.fees_usd) / buy.quantity
    sell = _sell(
        average_cost=average_cost,
        fill_id="sell",
        at=SESSION_OPEN + timedelta(minutes=1),
        signal=100.5,
        quantity=10,
    )
    episode = _episode([buy, sell])
    bars = [
        _bar(0, open_=99.0, high=99.5, low=98.5, close=99.1),
        _bar(1, open_=100.5, high=100.6, low=100.5, close=100.55),
    ]

    with pytest.raises(ConsistencyGateError) as raised:
        reconcile_binding_gate(
            [episode],
            {"TEST": bars},
            constructed_episode_count=19,
        )

    assert raised.value.gate_payload["market_compatibility"]["threshold_passed"] is False
    assert any(
        item["gate"] == "market_compatibility_violation_rate"
        for item in raised.value.failures
    )


def test_frozen_probe_decomposition_contract_is_pinned() -> None:
    frozen_probe = {
        "gate_analysis_sha256": (
            "864b494e4f3798504e46aeef7da19e45690c7656676fa6ce6e96ca481e9c124c"
        ),
        "residual_probe_sha256": (
            "a104292b552f8631df9bcfbc2c727ac605222703be0ba2f1b434be382a898cf7"
        ),
        "original_failure_decomposition": {
            "synthetic_fill_vs_signal": 278,
            "clock_extended": 35,
            "tolerance_band": 89,
            "violation": 4,
        },
        "violation_episode_symbols": ["NASDAQ:LIFE", "NYSE:BVN", "NYSE:BVN", "NYSE:PJT"],
    }

    assert sum(frozen_probe["original_failure_decomposition"].values()) == 406
    assert frozen_probe["original_failure_decomposition"] == {
        "synthetic_fill_vs_signal": 278,
        "clock_extended": 35,
        "tolerance_band": 89,
        "violation": 4,
    }
    assert frozen_probe["violation_episode_symbols"] == [
        "NASDAQ:LIFE", "NYSE:BVN", "NYSE:BVN", "NYSE:PJT",
    ]


def test_frozen_rerun_filters_ledger_at_cutoff_and_verifies_hash() -> None:
    before = _buy(fill_id="before", at=SESSION_OPEN)
    after = _buy(fill_id="after", at=SESSION_OPEN + timedelta(days=1))
    selected_without_hash, evidence_without_hash = _frozen_ledger_input(
        [before, after],
        cutoff_at=SESSION_OPEN,
        expected_sha256=None,
    )
    expected_sha256 = evidence_without_hash["canonical_json_sha256"]

    selected, evidence = _frozen_ledger_input(
        [before, after],
        cutoff_at=SESSION_OPEN,
        expected_sha256=expected_sha256,
    )

    assert [fill.id for fill in selected_without_hash] == ["before"]
    assert [fill.id for fill in selected] == ["before"]
    assert evidence["frozen_hash_verified"] is True
    assert evidence["expected_sha256"] == expected_sha256
    assert evidence["input_cutoff_at"] == SESSION_OPEN


def test_frozen_rerun_rejects_ledger_hash_drift() -> None:
    with pytest.raises(ExitPolicyStudyError, match="frozen ledger hash mismatch"):
        _frozen_ledger_input(
            [_buy()],
            cutoff_at=SESSION_OPEN,
            expected_sha256="0" * 64,
        )


def test_take_profit_overlay_preserves_real_partial_before_anticipating_exit() -> None:
    buy = _buy(quantity=10)
    average_cost = (buy.gross_value_usd + buy.fees_usd) / buy.quantity
    partial = _sell(
        average_cost=average_cost,
        fill_id="partial",
        at=SESSION_OPEN + timedelta(minutes=1),
        signal=100.2,
        quantity=4,
    )
    final = _sell(
        average_cost=average_cost,
        fill_id="final",
        at=SESSION_OPEN + timedelta(minutes=3),
        signal=99.8,
        quantity=6,
        reason="hard stop",
    )
    episode = _episode([buy, partial, final])
    bars = [
        _bar(0, open_=100.0, high=100.2, low=99.9, close=100.1),
        _bar(1, open_=100.1, high=100.3, low=100.0, close=100.2),
        _bar(2, open_=100.35, high=100.7, low=100.3, close=100.6),
        _bar(3, open_=99.9, high=100.0, low=99.6, close=99.8),
    ]

    outcome = simulate_overlay(episode, bars, "B")

    assert outcome.synthetic_exit is True
    assert outcome.exited_at == SESSION_OPEN + timedelta(minutes=2)
    assert outcome.exit_reason == "overlay_take_profit_0.15"
    assert outcome.daily_realized_pnl_usd[date(2026, 8, 20)] == pytest.approx(outcome.pnl_usd)
    assert outcome.turnover_usd > buy.gross_value_usd + partial.gross_value_usd


def test_breakeven_activation_on_bar_n_only_applies_on_n_plus_one() -> None:
    buy = _buy(quantity=10)
    average_cost = (buy.gross_value_usd + buy.fees_usd) / buy.quantity
    final = _sell(
        average_cost=average_cost,
        fill_id="final",
        at=SESSION_OPEN + timedelta(minutes=3),
        signal=99.8,
        quantity=10,
    )
    episode = _episode([buy, final])
    bars = [
        _bar(0, open_=100.0, high=100.2, low=99.9, close=100.1),
        _bar(1, open_=100.4, high=100.8, low=99.8, close=100.5),
        _bar(2, open_=100.1, high=100.2, low=99.9, close=100.0),
        _bar(3, open_=99.8, high=99.9, low=99.6, close=99.7),
    ]

    outcome = simulate_overlay(episode, bars, "C")

    assert outcome.synthetic_exit is True
    assert outcome.exited_at == SESSION_OPEN + timedelta(minutes=2)
    assert outcome.exit_reason == "overlay_breakeven"


def test_fixed_stop_executes_gap_at_open_before_intrabar_level() -> None:
    buy = _buy(quantity=10)
    average_cost = (buy.gross_value_usd + buy.fees_usd) / buy.quantity
    final = _sell(
        average_cost=average_cost,
        fill_id="final",
        at=SESSION_OPEN + timedelta(minutes=3),
        signal=99.0,
        quantity=10,
    )
    episode = _episode([buy, final])
    bars = [
        _bar(0, open_=100.0, high=100.2, low=99.9, close=100.1),
        _bar(1, open_=99.0, high=99.5, low=98.8, close=99.2),
        _bar(2, open_=99.2, high=99.4, low=99.0, close=99.1),
    ]

    outcome = simulate_mechanical(episode, bars, "D")

    assert outcome is not None
    assert outcome.exited_at == SESSION_OPEN + timedelta(minutes=1)
    expected_fill = 99.0 * 0.999
    expected_realized = 10 * expected_fill * (1 - 0.0004) - 10 * average_cost
    assert outcome.pnl_usd == pytest.approx(expected_realized)


def test_mechanical_policy_is_censored_when_ten_session_horizon_is_unavailable() -> None:
    buy = _buy(quantity=10)
    average_cost = (buy.gross_value_usd + buy.fees_usd) / buy.quantity
    final = _sell(
        average_cost=average_cost,
        fill_id="final",
        at=SESSION_OPEN + timedelta(days=1, minutes=2),
        signal=100.0,
        quantity=10,
    )
    episode = _episode([buy, final])
    bars = [
        _bar(0, open_=100.0, high=100.15, low=99.5, close=100.1),
        _bar(1, open_=100.1, high=100.15, low=99.5, close=100.1),
        _bar(0, open_=100.0, high=100.15, low=99.5, close=100.1, session_offset=1),
        _bar(1, open_=100.1, high=100.15, low=99.5, close=100.1, session_offset=1),
    ]

    assert simulate_mechanical(episode, bars, "D") is None


def _outcome(episode_id: str, session_offset: int, pnl: float, policy: str) -> PolicyOutcome:
    opened = SESSION_OPEN + timedelta(days=session_offset)
    return PolicyOutcome(
        episode_id=episode_id,
        policy=policy,
        pnl_usd=pnl,
        turnover_usd=1_000.0,
        opened_at=opened,
        exited_at=opened + timedelta(minutes=30),
        exit_reason="test",
        synthetic_exit=policy != "A",
        daily_realized_pnl_usd={opened.date(): pnl},
        marked_close_pnl_usd={opened.date(): pnl},
    )


def test_session_bootstrap_is_paired_and_deterministic() -> None:
    baseline = [_outcome("e1", 0, -10, "A"), _outcome("e2", 1, 5, "A")]
    challenger = [_outcome("e1", 0, 0, "B"), _outcome("e2", 1, 7, "B")]

    first = paired_session_bootstrap(baseline, challenger, iterations=1_000)
    second = paired_session_bootstrap(baseline, challenger, iterations=1_000)

    assert first == second
    assert first["mean_delta_usd"] == pytest.approx(6.0)
    assert first["session_count"] == 2
    assert first["unit"] == "entry_session_block"


def test_minute_reader_preserves_case_sensitive_symbol_identity_and_hashes(tmp_path: Path) -> None:
    source = (
        tmp_path
        / "provider=massive"
        / "dataset=minute_aggregates"
        / "session_date=2026-08-20"
        / "source.csv.gz"
    )
    source.parent.mkdir(parents=True)
    window = int(SESSION_OPEN.timestamp() * 1_000_000_000)
    with gzip.open(source, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("ticker", "window_start", "open", "high", "low", "close", "volume"),
        )
        writer.writeheader()
        writer.writerow({
            "ticker": "ALPA", "window_start": window, "open": 10,
            "high": 11, "low": 9, "close": 10.5, "volume": 100,
        })
        writer.writerow({
            "ticker": "ALpA", "window_start": window, "open": 20,
            "high": 21, "low": 19, "close": 20.5, "volume": 200,
        })
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    metadata = {"content_length": source.stat().st_size, "sha256": digest}
    source.with_name(f"{source.name}.metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8",
    )

    bars, evidence = MinuteAggregateReader(tmp_path).read(
        [(date(2026, 8, 20), source)], {"ALPA"},
    )

    assert [item.close for item in bars["ALPA"]] == [10.5]
    assert "ALpA" not in bars
    assert evidence[0]["sha256"] == digest


def test_immutable_writer_is_idempotent_only_for_identical_bytes(tmp_path: Path) -> None:
    target = tmp_path / "report.json"
    payload = {"schema": "test", "self": canonical_sha256({"schema": "test"})}

    write_immutable_json(target, payload)
    write_immutable_json(target, payload)

    with pytest.raises(FileExistsError, match="immutable report"):
        write_immutable_json(target, {"schema": "changed"})


def test_run_window_is_fail_closed_outside_sao_paulo_madrugada() -> None:
    require_off_hours(datetime(2026, 8, 26, 5, 0, tzinfo=UTC))  # 02:00 BRT

    with pytest.raises(ExitPolicyStudyError, match="00:00-08:00"):
        require_off_hours(datetime(2026, 8, 26, 15, 0, tzinfo=UTC))


def test_report_is_self_hashed_and_keeps_panel_ii_nonbinding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import r2d2_exit_policy_study as study

    spec = tmp_path / "spec.md"
    amendment = tmp_path / "amendment.md"
    deliverable = tmp_path / "deliverable.md"
    spec.write_bytes(b"frozen spec\n")
    amendment.write_bytes(b"signed amendment\n")
    deliverable.write_bytes(b"approved deliverable\n")
    monkeypatch.setattr(study, "SPEC_SHA256", hashlib.sha256(spec.read_bytes()).hexdigest())
    monkeypatch.setattr(
        study,
        "AMENDMENT_ONE_SHA256",
        hashlib.sha256(amendment.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(
        study,
        "DELIVERABLE_ZERO_SHA256",
        hashlib.sha256(deliverable.read_bytes()).hexdigest(),
    )
    buy = _buy(quantity=10)
    average_cost = (buy.gross_value_usd + buy.fees_usd) / buy.quantity
    sell = _sell(
        average_cost=average_cost,
        fill_id="final",
        at=SESSION_OPEN + timedelta(minutes=2),
        signal=100.5,
        quantity=10,
    )
    bars = [
        _bar(0, open_=100.0, high=100.2, low=99.9, close=100.1),
        _bar(1, open_=100.2, high=100.7, low=100.0, close=100.5),
        _bar(2, open_=100.3, high=100.6, low=100.2, close=100.4),
    ]
    source = tmp_path / "fake-source.csv.gz"
    source.write_bytes(b"not read by the patched reader")

    monkeypatch.setattr(
        study.LedgerReader,
        "read",
        lambda self, code: ({
            "id": "experiment",
            "code": code,
            "status": "running",
            "starting_capital": 1_000_000.0,
            "start_date": date(2026, 8, 17),
            "methodology_version": study.FROZEN_METHODOLOGY,
        }, [buy, sell]),
    )
    monkeypatch.setattr(
        study.MinuteAggregateReader,
        "selected_sources",
        lambda self, episodes: [(date(2026, 8, 20), source)],
    )
    monkeypatch.setattr(
        study.MinuteAggregateReader,
        "read",
        lambda self, sources, symbols: ({"TEST": bars}, [{
            "session_date": "2026-08-20",
            "path": "fake-source.csv.gz",
            "size_bytes": source.stat().st_size,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        }]),
    )
    settings = Settings(
        database_url="",
        day_d_dataset_root=tmp_path,
        r2d2_experiment_code="R2D2-90D-001",
    )

    report = build_report(
        settings=settings,
        generated_at=datetime(2026, 8, 26, 5, tzinfo=UTC),
        spec_path=spec,
        amendment_path=amendment,
        deliverable_path=deliverable,
    )

    assert report["analysis_interpretable"] is True
    assert report["panel_i"]["binding_interpretation"] is True
    assert set(report["panel_i"]["preregistered_decision_readout"].values()) == {
        "PILOT_NO_STRATEGY_PROPOSAL"
    }
    assert report["panel_ii"] is None
    assert report["governance"]["strategy_change_authorized"] is False
    without_hash = {key: value for key, value in report.items() if key != "report_sha256"}
    assert report["report_sha256"] == canonical_sha256(without_hash)
