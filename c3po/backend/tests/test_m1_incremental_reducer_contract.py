from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

import pytest

from app.r2d2_entry_quality_engine import (
    EntryMeasurement,
    hypothesis_reports,
    summarize_cell as frozen_summarize_cell,
)


def _load_reducer() -> ModuleType:
    path = Path(__file__).resolve().parents[3] / ".github/scripts/c3po_m1_incremental_reducer.py"
    spec = importlib.util.spec_from_file_location("c3po_m1_incremental_reducer", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


REDUCER = _load_reducer()


def _measurement(
    entry_id: str,
    session: date,
    *,
    composite: float,
    barrier: str,
    primary: float | None,
    policy_epoch: str | None = None,
) -> EntryMeasurement:
    at = datetime.combine(session, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=15)
    return EntryMeasurement(
        entry_id=entry_id,
        market="NYSE",
        symbol="TEST",
        session_date=session,
        policy_epoch=policy_epoch or REDUCER.POLICY_EPOCH,
        executed_at=at,
        quote_as_of=at - timedelta(seconds=2),
        valuation_basis="canonical",
        route="cost_aware_intraday",
        entry_hour_brt=12,
        regime="mixed",
        composite_score=composite,
        fundamental_score=70.0,
        technical_score=60.0,
        risk_score=50.0,
        buy_in_distance_percent=1.0,
        atr_percent=2.0,
        quote_age_seconds=2.0,
        stretch=0.01,
        net0_percent=-0.1,
        risk_one_r_percent=1.0,
        barrier_category=barrier,
        primary_return_60m_percent=primary,
        endpoint_returns_percent={"plus_60m": primary},
        mfe_percent=1.5,
        mae_percent=-0.8,
        minutes_to_peak=20,
    )


def _rows() -> list[EntryMeasurement]:
    rows: list[EntryMeasurement] = []
    for day in range(1, 7):
        session = date(2026, 8, day)
        for offset in range(4):
            rows.append(_measurement(
                f"entry-{day}-{offset}",
                session,
                composite=float(day * 10 + offset),
                barrier=("upper_first" if (day + offset) % 3 else "lower_first"),
                primary=float(day - offset),
            ))
    return rows


def test_stdlib_reducer_matches_frozen_bootstrap_and_h3_exactly() -> None:
    rows = _rows()
    dictionaries = [asdict(row) for row in rows]

    assert REDUCER.summarize_cell(dictionaries) == frozen_summarize_cell(rows)
    assert REDUCER.summarize_h3(dictionaries) == hypothesis_reports(
        rows,
        stretch_upper_quartile=None,
    )["H3"]


def _baseline(rows: list[EntryMeasurement]) -> dict[str, object]:
    report: dict[str, object] = {
        "schema_version": REDUCER.BASELINE_SCHEMA,
        "analysis_interpretable": True,
        "entry_measurements": [asdict(row) for row in rows],
        "entry_consistency_gate": {
            "failures": [],
            "g3_coverage_censorship": {
                "maximum_percent": 5.0,
                "violation_entry_ids": [],
                "bar_unavailable_entry_ids": [],
                "violations": [],
                "bar_unavailable": [],
            },
        },
    }
    report["report_sha256"] = REDUCER.canonical_sha256(report)
    return report


def _snapshot(session: date, rows: list[EntryMeasurement]) -> dict[str, object]:
    gate = {
        "failures": [],
        "g3_coverage_censorship": {
            "violation_entry_ids": [],
            "bar_unavailable_entry_ids": [],
        },
    }
    price_sources = {"missing_sessions": []}
    coverage: dict[str, object] = {}
    value: dict[str, object] = {
        "schema": REDUCER.SNAPSHOT_SCHEMA,
        "session_date": session.isoformat(),
        "policy_epoch": REDUCER.POLICY_EPOCH,
        "query_sha256": "1" * 64,
        "ledger_session_sha256": "2" * 64,
        "price_sources_sha256": REDUCER.canonical_sha256(price_sources),
        "price_sources": price_sources,
        "coverage_sha256": REDUCER.canonical_sha256(coverage),
        "coverage": coverage,
        "entry_gate_sha256": REDUCER.canonical_sha256(gate),
        "entry_gate": gate,
        "policy_epochs_sha256": "3" * 64,
        "database_access": {
            "effective_role": "pg_read_all_data",
            "transaction_read_only": True,
            "ddl_or_dml_executed": False,
        },
        "experiment": {"code": "R2D2-90D-001", "status": "active"},
        "source_entry_ids": [row.entry_id for row in rows],
        "measurements": [asdict(row) for row in rows],
        "measurement_censoring": {},
        "frozen_source_sha256": {"engine": "4" * 64},
        "experiment": {"code": "R2D2-90D-001", "status": "active"},
    }
    value["snapshot_sha256"] = REDUCER.canonical_sha256(value)
    return value


def test_session_replacement_is_idempotent_and_publishable_output_has_no_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_rows = _rows()
    prior_epoch_same_date = _measurement(
        "prior-epoch-same-date",
        date(2026, 8, 6),
        composite=1.0,
        barrier="lower_first",
        primary=-1.0,
        policy_epoch="policy-a-prior",
    )
    baseline_rows_with_prior = [*baseline_rows, prior_epoch_same_date]
    report = _baseline(baseline_rows_with_prior)
    monkeypatch.setattr(REDUCER, "BASELINE_REPORT_SHA256", report["report_sha256"])
    replacement = [
        _measurement(
            "replacement-entry",
            date(2026, 8, 6),
            composite=99.0,
            barrier="upper_first",
            primary=4.0,
        )
    ]
    snapshot = _snapshot(date(2026, 8, 6), replacement)

    artefact = REDUCER.build_reduced_artifact(
        report,
        [snapshot],
        reducer_query_sha256="5" * 64,
        generated_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
    )

    assert artefact["m1"]["summary"]["entry_count"] == len(baseline_rows) - 4 + 1
    assert artefact["entry_consistency_gate"]["constructed_entry_count"] == (
        len(baseline_rows_with_prior) - 4 + 1
    )
    serialized = json.dumps(artefact, sort_keys=True)
    assert '"entry_id"' not in serialized
    assert '"source_entry_ids"' not in serialized
    assert '"measurements"' not in serialized
    assert artefact["artifact_sha256"] == REDUCER.canonical_sha256(
        REDUCER.without_field(artefact, "artifact_sha256")
    )


def test_corrupted_session_snapshot_fails_closed() -> None:
    snapshot = _snapshot(date(2026, 8, 6), _rows()[-4:])
    snapshot["measurements"] = []

    with pytest.raises(REDUCER.ReductionError, match="snapshot_sha256 mismatch"):
        REDUCER.validate_snapshot(snapshot)


def test_snapshot_from_another_experiment_fails_closed() -> None:
    snapshot = _snapshot(date(2026, 8, 6), _rows()[-4:])
    snapshot["experiment"] = {"code": "OTHER", "status": "active"}
    snapshot["snapshot_sha256"] = REDUCER.canonical_sha256(
        REDUCER.without_field(snapshot, "snapshot_sha256")
    )

    with pytest.raises(REDUCER.ReductionError, match="another experiment"):
        REDUCER.validate_snapshot(snapshot)


def test_snapshot_self_hash_survives_json_round_trip_with_datetimes() -> None:
    snapshot = _snapshot(date(2026, 8, 6), _rows()[-4:])
    reloaded = json.loads(REDUCER.canonical_json(snapshot))

    validated = REDUCER.validate_snapshot(reloaded)

    assert validated["snapshot_sha256"] == snapshot["snapshot_sha256"]


def test_mixed_deployed_source_hashes_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = _baseline(_rows())
    monkeypatch.setattr(REDUCER, "BASELINE_REPORT_SHA256", report["report_sha256"])
    first = _snapshot(date(2026, 8, 5), _rows()[-8:-4])
    second = _snapshot(date(2026, 8, 6), _rows()[-4:])
    second["frozen_source_sha256"] = {"engine": "9" * 64}
    second["snapshot_sha256"] = REDUCER.canonical_sha256(
        REDUCER.without_field(second, "snapshot_sha256")
    )

    with pytest.raises(REDUCER.ReductionError, match="one frozen contract"):
        REDUCER.merge_current_epoch(report, [first, second])
