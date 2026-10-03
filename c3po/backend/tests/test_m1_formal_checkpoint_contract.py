from __future__ import annotations

import copy
import hashlib
import importlib
import json
import sys
from unittest.mock import patch
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / ".github" / "scripts"
sys.path.insert(0, str(SCRIPTS))
frozen = importlib.import_module("c3po_m1_incremental_reducer")
formal = importlib.import_module("c3po_m1_formal_checkpoint")


def _sessions(count: int) -> list[str]:
    start = date(2026, 8, 26)
    return [(start + timedelta(days=index)).isoformat() for index in range(count)]


def _snapshot(
    session: str,
    category: str | None,
    *,
    suffix: str = "a",
) -> dict[str, Any]:
    entry_id = f"entry-{session}-{suffix}"
    unavailable = [entry_id] if category is None else []
    measurements = []
    if category is not None:
        measurements.append(
            {
                "entry_id": entry_id,
                "session_date": session,
                "policy_epoch": formal.POLICY_EPOCH,
                "executed_at": f"{session}T15:00:00+00:00",
                "barrier_category": category,
                "composite_score": 0.5,
                "primary_return_60m_percent": 0.1,
                "mfe_percent": 0.2,
                "mae_percent": -0.1,
            }
        )
    price_sources = {"missing_sessions": []}
    coverage: dict[str, object] = {}
    gate = {
        "g3_coverage_censorship": {
            "maximum_percent": formal.FROZEN_NUMERIC_VIOLATION_PERCENT,
            "violation_entry_ids": [],
            "bar_unavailable_entry_ids": unavailable,
        },
        "failures": [],
    }
    payload: dict[str, Any] = {
        "schema": frozen.SNAPSHOT_SCHEMA,
        "generated_at": f"{session}T23:00:00+00:00",
        "session_date": session,
        "policy_epoch": formal.POLICY_EPOCH,
        "query_sha256": formal.FROZEN_SNAPSHOT_QUERY_SHA256,
        "database_access": {
            "effective_role": "pg_read_all_data",
            "transaction_read_only": True,
            "statement_timeout": "2min",
            "lock_timeout": "5s",
            "ddl_or_dml_executed": False,
        },
        "experiment": {"code": "R2D2-90D-001", "status": "active"},
        "frozen_source_sha256": formal.FROZEN_APP_SOURCE_SHA256,
        "policy_epochs_sha256": formal.POLICY_EPOCHS_FILE_SHA256,
        "source_entry_ids": [entry_id],
        "ledger_session_sha256": hashlib.sha256(entry_id.encode()).hexdigest(),
        "price_sources_sha256": frozen.canonical_sha256(price_sources),
        "price_sources": price_sources,
        "coverage_sha256": frozen.canonical_sha256(coverage),
        "coverage": coverage,
        "entry_gate_sha256": frozen.canonical_sha256(gate),
        "entry_gate": gate,
        "measurement_censoring": (
            {"bar_unavailable": 1} if category is None else {}
        ),
        "measurements": measurements,
    }
    payload["snapshot_sha256"] = frozen.canonical_sha256(payload)
    return payload


def _baseline() -> dict[str, Any]:
    return {
        "schema_version": frozen.BASELINE_SCHEMA,
        "analysis_interpretable": True,
        "report_sha256": frozen.BASELINE_REPORT_SHA256,
        "entry_measurements": [],
        "entry_consistency_gate": {
            "failures": [],
            "g3_coverage_censorship": {
                "maximum_percent": formal.FROZEN_NUMERIC_VIOLATION_PERCENT,
                "violation_entry_ids": [],
                "bar_unavailable_entry_ids": [],
                "bar_unavailable": [],
                "violations": [],
            },
        },
    }


def _build(
    categories: Sequence[str | None],
    checkpoint: int,
    *,
    prior: Mapping[str, Any] | None = None,
    enumeration_sha256: str = "a" * 64,
) -> dict[str, Any] | None:
    sessions = _sessions(len(categories))
    snapshots = [
        _snapshot(session, category)
        for session, category in zip(sessions, categories)
    ]
    with patch.object(frozen, "verify_baseline"):
        return formal.build_formal_checkpoint(
            _baseline(),
            snapshots,
            sessions,
            checkpoint=checkpoint,
            prior_15_artifact=prior,
            generated_at=datetime(2026, 9, 17, tzinfo=timezone.utc),
            enumeration_sha256=enumeration_sha256,
        )


def test_canonical_signed_source_and_measurement_sources_are_pinned() -> None:
    assert formal.MESA_SOURCE_SHA256 == (
        "b846371a89f9d5b3ec4ccadd8ac4cc470be89a24444cf992604dad072541658f"
    )
    assert hashlib.sha256(
        (SCRIPTS / "c3po_m1_session_snapshot.py").read_bytes()
    ).hexdigest() == formal.FROZEN_SNAPSHOT_QUERY_SHA256
    assert hashlib.sha256(
        (SCRIPTS / "c3po_m1_incremental_reducer.py").read_bytes()
    ).hexdigest() == formal.FROZEN_INCREMENTAL_REDUCER_SHA256


def test_session_enumerator_is_dynamic_read_only_and_post_close() -> None:
    source = (SCRIPTS / "c3po_m1_checkpoint_sessions.sql").read_text()
    assert "BEGIN TRANSACTION READ ONLY" in source
    assert "statement_timeout = '120s'" in source
    assert "lock_timeout = '5s'" in source
    assert "America/New_York" in source
    assert "18:00:00" in source
    assert "2026-09-02" not in source
    assert not any(
        token in source.upper()
        for token in (" INSERT ", " UPDATE ", " DELETE ", " ALTER ", " DROP ")
    )


def test_formal_cli_inputs_are_byte_and_count_bounded(tmp_path: Path) -> None:
    oversized = tmp_path / "sessions.txt"
    oversized.write_bytes(b"x" * (formal.MAX_ENUMERATION_INPUT_BYTES + 1))
    with pytest.raises(formal.FormalCheckpointError, match="byte ceiling"):
        formal.load_enumerated_sessions(oversized)

    assert formal.MAX_BASELINE_INPUT_BYTES == 8 * 1024 * 1024
    assert formal.MAX_SNAPSHOT_INPUT_BYTES == 4 * 1024 * 1024
    assert formal.MAX_TOTAL_SNAPSHOT_INPUT_BYTES == 32 * 1024 * 1024
    assert formal.MAX_SESSION_SNAPSHOT_FILES == 512


def test_session_15_uses_exact_measured_prefix_and_continues() -> None:
    result = _build(["upper_first"] * 15, 15)
    assert result is not None
    assert result["label"] == formal.FORMAL_LABELS["continue_20"]
    assert result["checkpoint"]["observed_measured_sessions"] == 15
    assert result["checkpoint"]["source_session_count"] == 15
    assert result["formal_bounds"]["ucb_98_75"]["central"] == 1.0
    assert result["formal_bounds"]["lcb_98_75"]["central"] == 1.0


def test_zero_measurement_source_session_does_not_advance_clock() -> None:
    result = _build([None] + ["upper_first"] * 15, 15)
    assert result is not None
    assert result["checkpoint"]["observed_measured_sessions"] == 15
    assert result["checkpoint"]["source_session_count"] == 16
    assert len(result["source_evidence"]) == 16


def test_session_15_refutes_on_central_ucb_at_or_below_half() -> None:
    result = _build(["lower_first"] * 15, 15)
    assert result is not None
    assert result["label"] == formal.FORMAL_LABELS["refuted_15"]
    assert result["formal_bounds"]["ucb_98_75"]["central"] == 0.0


def test_session_20_requires_bound_continue_artifact() -> None:
    with pytest.raises(formal.FormalCheckpointError, match="not armed"):
        _build(["upper_first"] * 20, 20)

    refuted = _build(["lower_first"] * 15, 15)
    assert refuted is not None
    with pytest.raises(formal.FormalCheckpointError, match="does not arm"):
        _build(
            ["upper_first"] * 20,
            20,
            prior=refuted,
        )

    continued = _build(
        ["upper_first"] * 15,
        15,
        enumeration_sha256="9" * 64,
    )
    assert continued is not None
    result = _build(
        ["upper_first"] * 20,
        20,
        prior=continued,
    )
    assert result is not None
    assert result["label"] == formal.FORMAL_LABELS["positive_20"]
    assert result["checkpoint"]["prior_15_artifact_sha256"] == continued[
        "artifact_sha256"
    ]


def test_session_20_mixed_evidence_is_formally_inconclusive() -> None:
    categories = ["upper_first", "lower_first"] * 10
    continued = _build(categories[:15], 15)
    assert continued is not None
    assert continued["label"] == formal.FORMAL_LABELS["continue_20"]
    result = _build(
        categories,
        20,
        prior=continued,
    )
    assert result is not None
    assert result["label"] == formal.FORMAL_LABELS["inconclusive_20"]
    assert result["formal_bounds"]["lcb_98_75"]["central"] <= 0.5
    assert result["formal_bounds"]["ucb_98_75"]["central"] > 0.5


def test_session_20_recomputes_15_and_rejects_backfill_drift() -> None:
    continued = _build(["upper_first"] * 15, 15)
    assert continued is not None
    drifted = ["lower_first"] + ["upper_first"] * 19
    with pytest.raises(formal.FormalCheckpointError, match="exact prefix"):
        _build(drifted, 20, prior=continued)


def test_session_20_rejects_tampered_prior_artifact() -> None:
    continued = _build(["upper_first"] * 15, 15)
    assert continued is not None
    tampered = copy.deepcopy(continued)
    tampered["population_counts"]["upper_first"] = 14
    with pytest.raises(formal.FormalCheckpointError, match="self-hash"):
        _build(["upper_first"] * 20, 20, prior=tampered)

    extended = copy.deepcopy(continued)
    extended["unexpected"] = "not part of the formal schema"
    extended["artifact_sha256"] = frozen.canonical_sha256(
        {key: value for key, value in extended.items() if key != "artifact_sha256"}
    )
    with pytest.raises(formal.FormalCheckpointError, match="fields are not exact"):
        _build(["upper_first"] * 20, 20, prior=extended)


def test_not_ready_emits_no_formal_payload() -> None:
    assert _build(["upper_first"] * 14, 15) is None


def test_missing_first_session_or_source_drift_fails_closed() -> None:
    sessions = _sessions(15)
    snapshots = [_snapshot(day, "upper_first") for day in sessions]
    with patch.object(frozen, "verify_baseline"):
        with pytest.raises(formal.FormalCheckpointError, match="exact enumeration prefix"):
            formal.build_formal_checkpoint(
                _baseline(),
                snapshots[1:],
                sessions,
                checkpoint=15,
                enumeration_sha256="b" * 64,
            )

    drifted = copy.deepcopy(snapshots)
    drifted[0]["frozen_source_sha256"] = {
        **formal.FROZEN_APP_SOURCE_SHA256,
        "r2d2_entry_quality_engine.py": "0" * 64,
    }
    drifted[0]["snapshot_sha256"] = frozen.canonical_sha256(
        {key: value for key, value in drifted[0].items() if key != "snapshot_sha256"}
    )
    with patch.object(frozen, "verify_baseline"):
        with pytest.raises(formal.FormalCheckpointError, match="source differs"):
            formal.build_formal_checkpoint(
                _baseline(),
                drifted,
                sessions,
                checkpoint=15,
                enumeration_sha256="b" * 64,
            )


def test_gate_failure_produces_no_formal_artifact() -> None:
    sessions = _sessions(15)
    snapshots = [_snapshot(day, "upper_first") for day in sessions]
    censorship = snapshots[0]["entry_gate"]["g3_coverage_censorship"]
    violation_id = "entry-2026-08-26-violation"
    snapshots[0]["source_entry_ids"].append(violation_id)
    censorship["violation_entry_ids"] = [violation_id]
    snapshots[0]["entry_gate_sha256"] = frozen.canonical_sha256(
        snapshots[0]["entry_gate"]
    )
    snapshots[0]["snapshot_sha256"] = frozen.canonical_sha256(
        {key: value for key, value in snapshots[0].items() if key != "snapshot_sha256"}
    )
    with patch.object(frozen, "verify_baseline"):
        with pytest.raises(formal.FormalCheckpointError, match="gate failed"):
            formal.build_formal_checkpoint(
                _baseline(),
                snapshots,
                sessions,
                checkpoint=15,
                enumeration_sha256="c" * 64,
            )


def test_payload_is_self_hashed_reduced_and_preparation_only() -> None:
    result = _build(["upper_first"] * 15, 15)
    assert result is not None
    frozen.verify_self_hash(result, "artifact_sha256")
    serialized = frozen.canonical_json(result)
    for forbidden in formal.FORBIDDEN_PUBLISHED_KEYS:
        assert f'"{forbidden}"' not in serialized
    assert result["governance"]["raw_rows_published"] is False
    assert result["governance"]["entry_identifiers_published"] is False
    assert result["governance"]["transient_destruction_implemented"] is False
    assert result["governance"]["schedule_implemented"] is False
    assert result["governance"]["private_retention_implemented"] is False
    assert result["governance"]["breaker_dml_executed"] is False
    assert result["governance"]["strategy_change_authorized"] is False
    assert len(json.dumps(result).encode()) < 65_536


def test_factual_baseline_is_mandatory_and_hash_pinned() -> None:
    sessions = _sessions(15)
    snapshots = [_snapshot(day, "upper_first") for day in sessions]
    with pytest.raises(frozen.ReductionError, match="report_sha256"):
        formal.build_formal_checkpoint(
            _baseline(),
            snapshots,
            sessions,
            checkpoint=15,
            enumeration_sha256="d" * 64,
        )
