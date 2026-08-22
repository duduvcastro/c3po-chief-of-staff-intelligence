from __future__ import annotations

import json
import hashlib
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.day_d_replay.costs import CostTable
from app.day_d_replay.engine import DayDReplayHarness, ReplayDataset
from app.day_d_replay.models import (
    CostScenario,
    DataGateResult,
    FeeSchedule,
    RunManifest,
    RunMode,
    SpreadCell,
    UniverseManifest,
    UniverseMember,
)
from app.day_d_replay.synthetic import run_synthetic_truth_gate
from app.day_d_replay.synthetic_gate import main as synthetic_gate_main
from app.day_d_replay.validation import (
    HARNESS_CONTRACT_PATH,
    SIGNAL_CONTRACT_PATH,
    OfficialReplayBlocked,
    dataset_manifest_hash,
    sha256_file,
    validate_official_readiness,
)

C3PO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = C3PO_ROOT / "docs" / "day_d" / "replay_harness_contract_v1.json"
PREREGISTRATION_PAYLOAD = b'{"contract":"final-test-preregistration"}'


def _fee() -> FeeSchedule:
    return FeeSchedule(
        version="DAY-D-FEE-v1",
        source="audited-test-schedule",
        effective_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        captured_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        content_hash="f" * 64,
        commission_per_share_usd=0.0035,
        minimum_commission_usd=0.0,
        sec_section_31_rate=0.0,
        finra_taf_per_share_usd=0.000195,
        finra_taf_cap_usd=9.79,
    )


def _manifest(*, checksums: dict[str, str]) -> RunManifest:
    measured = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    gates = tuple(
        DataGateResult(gate=gate, passed=True, measured_at=measured, evidence_hash="e" * 64)
        for gate in ("T1_TRADE_COVERAGE", "T4_BBO_QUALITY", "T5_BAR_AND_CLOSE")
    )
    return RunManifest(
        run_id="official-test",
        run_mode=RunMode.OFFICIAL,
        created_at=measured,
        git_commit="a" * 40,
        dataset_manifest_hash=dataset_manifest_hash(checksums),
        signal_contract_hash=sha256_file(SIGNAL_CONTRACT_PATH),
        harness_contract_hash=sha256_file(HARNESS_CONTRACT_PATH),
        preregistration_hash=hashlib.sha256(PREREGISTRATION_PAYLOAD).hexdigest(),
        setup_versions=("S3-v1", "S5-v1"),
        feature_version="DAY-D-FEATURES-v1",
        universe_version="DAY-D-UNIVERSE-v1",
        fill_version="DAY-D-FILL-v1",
        cost_model_version="DAY-D-COST-v1",
        fee_schedule_version="DAY-D-FEE-v1",
        risk_policy_version="DAY-D-RISK-v1",
        calendar_version="DAY-D-CALENDAR-v1",
        harness_version="DAY-D-HARNESS-v1",
        latency_scenario="point",
        cost_scenario=CostScenario.POINT,
        run_seed=11,
        data_gate_results=gates,
        synthetic_truth_gate_passed=True,
    )


def _universe() -> UniverseManifest:
    cutoff = datetime(2026, 8, 20, 20, tzinfo=timezone.utc)
    return UniverseManifest(
        session_date=date(2026, 8, 21),
        previous_session_date=date(2026, 8, 20),
        generated_at=datetime(2026, 8, 21, 13, 20, tzinfo=timezone.utc),
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
                median_dollar_volume_20d_usd=100_000_000.0,
                history_session_count=20,
                liquidity_quintile=1,
                data_as_of=cutoff,
            ),
        ),
        shortfall=59,
    )


def _cost_table() -> CostTable:
    return CostTable.from_cells(
        "DAY-D-COST-v1",
        (
            SpreadCell(
                liquidity_quintile=1,
                time_bucket="ALL",
                half_spread_p25_usd=0.01,
                half_spread_p50_usd=0.02,
                observation_count=100,
                source_sessions_end=date(2026, 8, 20),
                available_at=datetime(2026, 8, 20, 22, tzinfo=timezone.utc),
            ),
        ),
    )


def test_harness_contract_is_research_only_and_fail_closed() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    assert contract["contract_version"] == "DAY-D-REPLAY-HARNESS-CONTRACT-v1"
    assert contract["production_behavior_change_authorized"] is False
    assert contract["capital_use_authorized"] is False
    assert contract["official_market_replay_executed_by_this_change"] is False
    assert contract["official_run_prerequisites"]["missing_requirement_behavior"] == (
        "raise_and_emit_no_official_result"
    )
    assert contract["synthetic_truth_gate"]["mandatory_before_any_official_result"] is True
    assert contract["official_result_matrix"] == {
        "book_policies": ["operational", "flat_at_close"],
        "latency_scenarios": ["point", "0ms", "250ms", "1000ms", "2000ms"],
        "cost_scenarios": ["optimistic", "point", "pessimistic"],
        "required_result_count": 30,
        "operational_and_counterfactual_books_share_identical_signals": True,
        "counterfactual_differs_only_by_official_close_liquidation_policy": True,
        "cost_monotonicity_checked_for_both_books": True,
    }
    assert contract["entry_audit"]["one_record_per_generated_setup_signal"] is True
    assert "final_fill" in contract["entry_audit"]["required_fields"]
    stage0 = json.loads(
        (C3PO_ROOT / "docs" / "day_d" / "stage0_contract.json").read_text(
            encoding="utf-8"
        )
    )
    reference = stage0["replay_harness_contract"]
    assert reference["path"] == "day_d/replay_harness_contract_v1.json"
    assert reference["implementation_package"] == "app.day_d_replay"
    assert reference["production_behavior_change_authorized"] is False
    assert reference["official_market_replay_executed"] is False


def test_synthetic_truth_recovers_all_three_worlds_and_properties() -> None:
    report = run_synthetic_truth_gate(
        git_commit="a" * 40,
        measured_at=datetime(2026, 8, 22, 12, tzinfo=timezone.utc),
    )

    assert report.passed is True
    assert report.world_results["negative"]["mean"] == pytest.approx(-0.5)
    assert report.world_results["zero"]["mean"] == pytest.approx(0.0)
    assert report.world_results["positive"]["mean"] == pytest.approx(0.5)
    assert all(report.property_results.values())


def test_synthetic_truth_cli_persists_auditable_artifact(tmp_path: Path) -> None:
    output = tmp_path / "synthetic-truth.json"

    status = synthetic_gate_main(
        (
            "--git-commit",
            "a" * 40,
            "--measured-at",
            "2026-08-22T12:00:00+00:00",
            "--output",
            str(output),
        )
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert status == 0
    assert payload["passed"] is True
    assert payload["git_commit"] == "a" * 40
    assert len(payload["evidence_hash"]) == 64
    assert not output.with_suffix(".json.tmp").exists()


def test_official_replay_is_blocked_without_same_commit_synthetic_truth() -> None:
    checksums = {"market-data.parquet": "c" * 64}
    manifest = _manifest(checksums=checksums)

    with pytest.raises(OfficialReplayBlocked, match="synthetic-truth report is missing"):
        validate_official_readiness(
            manifest=manifest,
            checksums=checksums,
            universes=(_universe(),),
            fee_schedule=_fee(),
            cost_table=_cost_table(),
            synthetic_truth=None,
            preregistration_payload=PREREGISTRATION_PAYLOAD,
        )


def test_official_readiness_accepts_complete_provenance() -> None:
    checksums = {"market-data.parquet": "c" * 64}
    manifest = _manifest(checksums=checksums)
    report = run_synthetic_truth_gate(
        git_commit=manifest.git_commit,
        measured_at=manifest.created_at,
    )

    validate_official_readiness(
        manifest=manifest,
        checksums=checksums,
        universes=(_universe(),),
        fee_schedule=_fee(),
        cost_table=_cost_table(),
        synthetic_truth=report,
        preregistration_payload=PREREGISTRATION_PAYLOAD,
    )


def test_official_readiness_rejects_tampered_synthetic_payload() -> None:
    checksums = {"market-data.parquet": "c" * 64}
    manifest = _manifest(checksums=checksums)
    report = run_synthetic_truth_gate(
        git_commit=manifest.git_commit,
        measured_at=manifest.created_at,
    )
    tampered_worlds = dict(report.world_results)
    tampered_worlds["positive"] = dict(tampered_worlds["positive"])
    tampered_worlds["positive"]["mean"] = 99.0

    with pytest.raises(OfficialReplayBlocked, match="evidence hash"):
        validate_official_readiness(
            manifest=manifest,
            checksums=checksums,
            universes=(_universe(),),
            fee_schedule=_fee(),
            cost_table=_cost_table(),
            synthetic_truth=replace(report, world_results=tampered_worlds),
            preregistration_payload=PREREGISTRATION_PAYLOAD,
        )


def test_official_readiness_validates_each_dataset_checksum() -> None:
    checksums = {"market-data.parquet": "not-a-sha256"}
    manifest = _manifest(checksums=checksums)
    report = run_synthetic_truth_gate(
        git_commit=manifest.git_commit,
        measured_at=manifest.created_at,
    )

    with pytest.raises(OfficialReplayBlocked, match=r"checksum\[market-data.parquet\]"):
        validate_official_readiness(
            manifest=manifest,
            checksums=checksums,
            universes=(_universe(),),
            fee_schedule=_fee(),
            cost_table=_cost_table(),
            synthetic_truth=report,
            preregistration_payload=PREREGISTRATION_PAYLOAD,
        )


def test_official_readiness_rejects_an_unbound_preregistration() -> None:
    checksums = {"market-data.parquet": "c" * 64}
    manifest = _manifest(checksums=checksums)
    report = run_synthetic_truth_gate(
        git_commit=manifest.git_commit,
        measured_at=manifest.created_at,
    )

    with pytest.raises(OfficialReplayBlocked, match="preregistration hash"):
        validate_official_readiness(
            manifest=manifest,
            checksums=checksums,
            universes=(_universe(),),
            fee_schedule=_fee(),
            cost_table=_cost_table(),
            synthetic_truth=report,
            preregistration_payload=b"tampered",
        )


def test_isolated_official_scenario_cannot_be_reported() -> None:
    checksums = {"market-data.parquet": "c" * 64}
    manifest = _manifest(checksums=checksums)
    report = run_synthetic_truth_gate(
        git_commit=manifest.git_commit,
        measured_at=manifest.created_at,
    )
    dataset = ReplayDataset(
        sessions=(),
        checksums=checksums,
        fee_schedule=_fee(),
        cost_table=_cost_table(),
        synthetic_truth=report,
    )

    with pytest.raises(OfficialReplayBlocked, match="run_fragility_matrix"):
        DayDReplayHarness(manifest=manifest).run(dataset)
