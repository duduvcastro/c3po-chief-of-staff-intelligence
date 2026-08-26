from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.r2d2_entry_quality_engine import (
    EntryMeasurement,
    atr_class,
    hypothesis_reports,
    measure_entry,
    quote_age_class,
    reconcile_entry_gate,
    summarize_cell,
)
from app.r2d2_entry_quality_study import (
    RawTradeMinuteReader,
    _load_policy_epochs,
    build_report,
    write_report_package,
)
from app.r2d2_exit_policy_engine import LedgerFill, StudyBar
from app.r2d2_exit_policy_study import canonical_sha256
from app.config import Settings
import app.r2d2_entry_quality_study as study_module


UTC = timezone.utc
SESSION_OPEN = datetime(2026, 8, 20, 13, 30, tzinfo=UTC)


def _buy(
    *,
    fill_id: str = "buy",
    at: datetime = SESSION_OPEN + timedelta(seconds=10),
    signal: float = 100.0,
    stop: float = 99.0,
    symbol: str = "TEST",
    quote_as_of: datetime | None = None,
) -> LedgerFill:
    quantity = 10.0
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
        reason="Tactical quality-momentum route passed",
        decision_snapshot={
            "stop_price": stop,
            "valuation_basis": "canonical C3PO valuation universe",
            "composite_score": 75.0,
            "fundamental_score": 78.0,
            "technical_score": 72.0,
            "risk_score": 40.0,
            "buy_in_distance": 2.0,
            "entry_decision_reasons": ["Tactical quality-momentum route passed"],
            "technical_indicators": {
                "atr": 1.0,
                "atr_percent": 1.0,
                "vwap": 99.5,
                "ema8": 99.75,
            },
        },
        executed_at=at,
        quote_as_of=quote_as_of or at,
    )


def _bar(
    minute: int,
    *,
    high: float = 100.5,
    low: float = 99.5,
    open_: float = 100.0,
    close: float = 100.0,
    symbol: str = "TEST",
    start: datetime = SESSION_OPEN,
) -> StudyBar:
    return StudyBar(
        symbol=symbol,
        start_at=start + timedelta(minutes=minute),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1_000.0,
    )


@pytest.mark.parametrize(
    ("high", "low", "expected"),
    (
        (101.1, 99.5, "upper_first"),
        (100.5, 98.9, "lower_first"),
        (101.1, 98.9, "ambiguous_same_bar"),
        (100.5, 99.5, "censored"),
    ),
)
def test_barrier_has_four_exclusive_categories(
    high: float,
    low: float,
    expected: str,
) -> None:
    result = measure_entry(
        _buy(),
        [_bar(1, high=high, low=low)],
        policy_epoch="epoch",
    )

    assert result.barrier_category == expected


def test_entry_minute_is_excluded_and_activation_starts_on_next_bar() -> None:
    result = measure_entry(
        _buy(),
        [
            _bar(0, high=101.5, low=98.5),
            _bar(1, high=101.1, low=99.5),
        ],
        policy_epoch="epoch",
    )

    assert result.barrier_category == "upper_first"
    assert result.minutes_to_peak == 0


def test_horizons_beyond_same_session_close_are_censored() -> None:
    entry_at = datetime(2026, 8, 20, 19, 29, 10, tzinfo=UTC)
    bars = [
        _bar(
            minute,
            start=entry_at.replace(second=0),
            high=100.5,
            low=99.5,
        )
        for minute in range(1, 31)
    ]

    result = measure_entry(
        _buy(at=entry_at),
        bars,
        policy_epoch="epoch",
    )

    assert result.endpoint_returns_percent["plus_15m"] is not None
    assert result.endpoint_returns_percent["plus_30m"] is not None
    assert result.endpoint_returns_percent["plus_60m"] is None
    assert result.endpoint_returns_percent["plus_120m"] is None


def test_gate_keeps_ledger_exact_and_censors_market_violation_first() -> None:
    fill = _buy()
    violation = _bar(0, open_=100.5, high=100.6, low=100.4, close=100.5)

    passing = reconcile_entry_gate(
        [fill],
        {"TEST": [violation]},
        constructed_entry_count=100,
    )

    assert passing["g1_ledger_and_friction"]["passed"] is True
    assert passing["g2_market_compatibility"]["counts"]["violation"] == 1
    assert passing["g3_coverage_censorship"]["censored_entry_ids"] == ["buy"]
    assert passing["g3_coverage_censorship"]["censored_percent_of_constructed_entries"] == 1.0
    assert passing["passed"] is True

    blocked = reconcile_entry_gate([fill], {"TEST": [violation]})
    assert blocked["passed"] is False
    assert blocked["g3_coverage_censorship"]["threshold_passed"] is False

    bad_fill = replace(fill, gross_value_usd=fill.gross_value_usd + 0.01)
    exact = reconcile_entry_gate([bad_fill], {"TEST": [_bar(0)]})
    assert exact["g1_ledger_and_friction"]["passed"] is False


def test_raw_reader_streams_trade_rows_excludes_dark_pool_and_orders_ticks(
    tmp_path: Path,
) -> None:
    session = date(2026, 8, 20)
    folder = tmp_path / f"session_date={session.isoformat()}"
    folder.mkdir()
    path = folder / "feed=trade-part-000.ndjson"
    base_ms = int((SESSION_OPEN + timedelta(minutes=1)).timestamp() * 1_000)
    rows = [
        {"payload_raw": {"s": "TEST", "p": 101.0, "v": 2, "t": base_ms + 20_000}},
        {"payload_raw": {"s": "TEST", "p": 99.0, "v": 1, "t": base_ms + 10_000}},
        {"payload_raw": {"s": "TEST", "p": 110.0, "v": 9, "t": base_ms + 15_000, "dp": True}},
        {"payload_raw": {"s": "OTHER", "p": 1.0, "v": 1, "t": base_ms + 10_000}},
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    bars, evidence, covered = RawTradeMinuteReader(tmp_path).read([session], {"TEST"})

    assert covered == {session}
    assert len(bars["TEST"]) == 1
    bar = bars["TEST"][0]
    assert (bar.open, bar.high, bar.low, bar.close, bar.volume) == (99.0, 101.0, 99.0, 101.0, 3.0)
    assert evidence[0]["rows_seen"] == 4
    assert evidence[0]["selected_rows"] == 2
    assert evidence[0]["dark_pool_rows_excluded"] == 1


def _measurement(
    index: int,
    *,
    hour: int,
    regime: str,
    barrier: str,
) -> EntryMeasurement:
    observed = SESSION_OPEN + timedelta(days=index % 15)
    return EntryMeasurement(
        entry_id=f"entry-{index}",
        market="NASDAQ",
        symbol=f"S{index}",
        session_date=observed.date(),
        policy_epoch="epoch",
        executed_at=observed,
        quote_as_of=observed,
        valuation_basis="canonical",
        route="tactical_quality_momentum",
        entry_hour_brt=hour,
        regime=regime,
        composite_score=float(index),
        fundamental_score=float(index),
        technical_score=float(index),
        risk_score=float(index),
        buy_in_distance_percent=float(index) / 10,
        atr_percent=1.0,
        quote_age_seconds=0.0,
        stretch=float(index) / 1_000,
        net0_percent=-0.28,
        risk_one_r_percent=1.0,
        barrier_category=barrier,
        primary_return_60m_percent=0.1,
        endpoint_returns_percent={"plus_60m": 0.1},
        mfe_percent=0.3,
        mae_percent=-0.2,
        minutes_to_peak=10,
    )


def test_hypothesis_floor_uses_decided_barriers_per_cell_and_is_local() -> None:
    rows = [
        _measurement(
            index,
            hour=10 if index < 30 else 12,
            regime="fade" if index < 30 else "trend_up",
            barrier="upper_first" if index % 2 == 0 else "lower_first",
        )
        for index in range(60)
    ]

    report = hypothesis_reports(rows, stretch_upper_quartile=0.045)

    assert report["H1"]["status"] == "DESCRIPTIVE_READY"
    assert report["H1"]["cells"]["10_to_12_brt"]["hypothesis_sample_status"] == "READY"
    assert report["H2"]["status"] == "DESCRIPTIVE_READY"
    assert report["H3"]["status"] == "INSUFFICIENT_SAMPLE"
    assert set(report["H3"]["insufficient_cells"]) == {"bottom_decile", "top_decile"}


def test_censorship_review_and_existing_classes_are_explicit() -> None:
    rows = [
        _measurement(
            index,
            hour=10,
            regime="trend_up",
            barrier="censored" if index < 3 else "upper_first",
        )
        for index in range(10)
    ]

    summary = summarize_cell(rows)

    assert summary["barrier"]["censorship_percent"] == 30.0
    assert summary["barrier"]["censorship_status"] == "REVIEW_REQUIRED"
    assert atr_class(0.2) == "below_strategy_band"
    assert atr_class(3.5) == "strategy_band_0_25_to_3_5"
    assert atr_class(4.0) == "elevated_3_5_to_5"
    assert atr_class(5.1) == "extreme_above_5"
    assert quote_age_class(5.0) == "fresh"
    assert quote_age_class(30.0) == "aging"
    assert quote_age_class(30.1) == "stale"


def test_policy_epoch_manifest_is_hashed_contiguous_and_exposes_unknown_origin() -> None:
    path = Path(__file__).resolve().parents[2] / "docs" / "ENTRY_QUALITY_STUDY_V1_POLICY_EPOCHS.json"

    epochs, evidence = _load_policy_epochs(path)

    assert evidence["manifest_sha256"] == "7c26c7e4ad011f74e752e00fce711451744d838d4d2923a86808fe12c1954dea"
    assert len(epochs) == 43
    assert epochs[0].code_provenance_status == "UNRESOLVED_PRE_REPOSITORY"
    assert epochs[-1].policy_epoch == "policy-a-resume-2026-08-26"
    assert epochs[-1].effective_to is None


def test_dry_run_builds_hashed_insufficient_sample_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry_at = datetime(2026, 8, 26, 13, 31, 10, tzinfo=UTC)
    fill = _buy(at=entry_at)
    trade = {
        **{
            field: getattr(fill, field)
            for field in (
                "id", "market", "symbol", "name", "side", "quantity",
                "signal_price_local", "fill_price_local", "fx_to_usd",
                "gross_value_usd", "fees_usd", "slippage_usd",
                "realized_pnl_usd", "reason", "decision_snapshot",
                "executed_at", "quote_as_of",
            )
        },
        "cycle_id": "cycle-1",
    }
    trade["decision_snapshot"] = {
        **trade["decision_snapshot"],
        "policy_epoch": "policy-a-resume-2026-08-26",
    }

    class FakeDatabase:
        database_url = ""

        def __init__(self, _settings: Settings) -> None:
            self._r2d2_memory = {
                "experiment": {
                    "id": "experiment-1",
                    "code": "R2D2_LIVE_EXPERIMENT",
                    "status": "running",
                },
                "trades": [trade],
            }
            self._r2d2_entry_score_observations = []

    monkeypatch.setattr(study_module, "Database", FakeDatabase)

    raw_root = tmp_path / "raw"
    folder = raw_root / "session_date=2026-08-26"
    folder.mkdir(parents=True)
    raw_path = folder / "feed=trade-part-000.ndjson"
    events = []
    for minute in range(0, 62):
        event_at = entry_at.replace(second=0) + timedelta(minutes=minute, seconds=20)
        events.append({
            "payload_raw": {
                "s": "TEST",
                "p": 100.0 + minute / 100,
                "v": 10,
                "t": int(event_at.timestamp() * 1_000),
            }
        })
    raw_path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )

    settings = Settings(
        database_url="",
        day_d_dataset_root=tmp_path / "day-d",
        r2d2_microstructure_raw_dir=raw_root,
        r2d2_experiment_code="R2D2_LIVE_EXPERIMENT",
    )
    docs = Path(__file__).resolve().parents[2] / "docs"
    manifest, report = build_report(
        settings=settings,
        policy_epochs_path=docs / "ENTRY_QUALITY_STUDY_V1_POLICY_EPOCHS.json",
        generated_at=datetime(2026, 8, 26, 23, 0, tzinfo=UTC),
        dry_run=True,
    )

    assert report["classification"] == "INSUFFICIENT_SAMPLE"
    assert report["analysis_interpretable"] is True
    assert report["cohort"]["measured_entry_count"] == 1
    assert list(report["policy_epoch_results"]) == ["policy-a-resume-2026-08-26"]
    assert report["report_sha256"] == canonical_sha256({
        key: value for key, value in report.items() if key != "report_sha256"
    })

    output = tmp_path / "package"
    write_report_package(output, manifest, report)
    before = (output / "report.json").read_bytes()
    write_report_package(output, manifest, report)
    assert (output / "report.json").read_bytes() == before
    sums = json.loads((output / "SHA256SUMS.json").read_text(encoding="utf-8"))
    assert set(sums) == {"manifest.json", "report.json"}
