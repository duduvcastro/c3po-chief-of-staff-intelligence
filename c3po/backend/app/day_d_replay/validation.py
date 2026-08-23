from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

from .costs import CostTable
from .models import (
    FeeSchedule,
    RunManifest,
    RunMode,
    SyntheticTruthReport,
    UniverseManifest,
)

C3PO_ROOT = Path(__file__).resolve().parents[3]
SIGNAL_CONTRACT_PATH = C3PO_ROOT / "docs" / "day_d" / "replay_signal_spec_v1.json"
HARNESS_CONTRACT_PATH = (
    C3PO_ROOT / "docs" / "day_d" / "replay_harness_contract_v1.json"
)

REQUIRED_DATA_GATES = {"T1_TRADE_COVERAGE", "T4_BBO_QUALITY", "T5_BAR_AND_CLOSE"}
REQUIRED_SYNTHETIC_PROPERTIES = {
    "future_data_mutation_does_not_change_prior_decision",
    "same_bar_fill_is_rejected",
    "zero_latency_result_is_not_worse_than_point_result_after_costs",
    "optimistic_net_result_gte_point_gte_pessimistic",
    "R_is_invariant_to_virtual_NAV_scale",
    "raw_tail_R_is_not_clipped",
    "adjacent_halts_delay_execution_until_final_reopen",
}
SYNTHETIC_WORLD_PLANTS = {"negative": -0.5, "zero": 0.0, "positive": 0.5}
SYNTHETIC_WORLD_TOLERANCE_R = 0.025


class OfficialReplayBlocked(RuntimeError):
    """Raised before an official run can emit any result artifact."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dataset_manifest_hash(checksums: Mapping[str, str]) -> str:
    canonical = json.dumps(
        dict(sorted(checksums.items())),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def synthetic_truth_evidence_hash(report: SyntheticTruthReport) -> str:
    evidence = {
        "version": report.version,
        "git_commit": report.git_commit,
        "harness_contract_hash": report.harness_contract_hash,
        "signal_contract_hash": report.signal_contract_hash,
        "seed": report.run_seed,
        "passed": report.passed,
        "measured_at": report.measured_at.isoformat(),
        "world_results": report.world_results,
        "property_results": report.property_results,
    }
    return hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _require_sha256(value: str, field_name: str, failures: list[str]) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        failures.append(f"{field_name} must be a lowercase SHA-256 digest")


def validate_official_readiness(
    *,
    manifest: RunManifest,
    checksums: Mapping[str, str],
    universes: Sequence[UniverseManifest],
    fee_schedule: FeeSchedule,
    cost_table: CostTable,
    synthetic_truth: SyntheticTruthReport | None,
    preregistration_payload: bytes | None = None,
    signal_contract_path: Path = SIGNAL_CONTRACT_PATH,
    harness_contract_path: Path = HARNESS_CONTRACT_PATH,
) -> None:
    """Fail closed before market data can be replayed in official mode."""

    if manifest.run_mode is not RunMode.OFFICIAL:
        return

    failures: list[str] = []
    if len(manifest.git_commit) not in {40, 64} or any(
        character not in "0123456789abcdef" for character in manifest.git_commit
    ):
        failures.append("git_commit must be a lowercase Git object id")
    for field_name in (
        "dataset_manifest_hash",
        "signal_contract_hash",
        "harness_contract_hash",
        "preregistration_hash",
    ):
        _require_sha256(str(getattr(manifest, field_name)), field_name, failures)

    if preregistration_payload is None:
        failures.append("final preregistration artifact is missing")
    elif hashlib.sha256(preregistration_payload).hexdigest() != manifest.preregistration_hash:
        failures.append("preregistration hash does not match its artifact")

    if manifest.signal_contract_hash != sha256_file(signal_contract_path):
        failures.append("signal contract hash does not match the checked-in contract")
    if manifest.harness_contract_hash != sha256_file(harness_contract_path):
        failures.append("harness contract hash does not match the checked-in contract")
    if not checksums:
        failures.append("dataset checksums are missing")
    else:
        for artifact_path, checksum in checksums.items():
            if not artifact_path:
                failures.append("dataset checksum contains an empty artifact path")
            _require_sha256(str(checksum), f"checksum[{artifact_path}]", failures)
        if manifest.dataset_manifest_hash != dataset_manifest_hash(checksums):
            failures.append("dataset manifest hash does not match the persisted checksums")

    gate_names = [result.gate for result in manifest.data_gate_results]
    duplicate_gates = sorted(
        gate for gate in set(gate_names) if gate_names.count(gate) > 1
    )
    if duplicate_gates:
        failures.append("duplicate data-gate results: " + ", ".join(duplicate_gates))
    for result in manifest.data_gate_results:
        _require_sha256(result.evidence_hash, f"{result.gate} evidence_hash", failures)
        if result.measured_at > manifest.created_at:
            failures.append(f"{result.gate} was measured after run creation")
        if result.git_commit is not None and result.git_commit != manifest.git_commit:
            failures.append(f"{result.gate} used a different Git commit")
    passed_gates = {result.gate for result in manifest.data_gate_results if result.passed}
    missing_gates = sorted(REQUIRED_DATA_GATES - passed_gates)
    if missing_gates:
        failures.append(f"required data gates did not pass: {', '.join(missing_gates)}")
    if not universes:
        failures.append("point-in-time universe manifests are missing")
    for universe in universes:
        if universe.universe_version != "DAY-D-UNIVERSE-v1":
            failures.append(f"unexpected universe version for {universe.session_date}")
        if universe.information_cutoff_at.date() != universe.previous_session_date:
            failures.append(f"universe cutoff is not D-1 for {universe.session_date}")
        if universe.generated_at.date() > universe.session_date:
            failures.append(f"universe was generated after session {universe.session_date}")
        if len(universe.members) + universe.shortfall != 60:
            failures.append(
                f"universe size plus shortfall must equal 60 for {universe.session_date}"
            )
        if universe.benchmark_symbols != ("QQQ",):
            failures.append(f"official benchmark must be QQQ for {universe.session_date}")

    if not cost_table.cells:
        failures.append("causal cost table is empty")
    if manifest.cost_model_version != cost_table.version:
        failures.append("cost table version does not match run manifest")
    if manifest.fee_schedule_version != fee_schedule.version:
        failures.append("fee schedule version does not match run manifest")
    if fee_schedule.captured_at > manifest.created_at:
        failures.append("fee schedule was captured after run creation")
    _require_sha256(fee_schedule.content_hash, "fee schedule content_hash", failures)

    if synthetic_truth is None:
        failures.append("synthetic-truth report is missing")
    else:
        if synthetic_truth.version != "DAY-D-SYNTHETIC-TRUTH-v1":
            failures.append("synthetic truth has an unexpected version")
        if (
            synthetic_truth.passed is not True
            or manifest.synthetic_truth_gate_passed is not True
        ):
            failures.append("synthetic-truth gate did not pass")
        if synthetic_truth.git_commit != manifest.git_commit:
            failures.append("synthetic truth did not run from the official replay commit")
        if synthetic_truth.harness_contract_hash != manifest.harness_contract_hash:
            failures.append("synthetic truth used a different harness contract")
        if synthetic_truth.signal_contract_hash != manifest.signal_contract_hash:
            failures.append("synthetic truth used a different signal contract")
        if synthetic_truth.run_seed != 20260822:
            failures.append("synthetic truth did not use the frozen seed")
        if synthetic_truth.measured_at > manifest.created_at:
            failures.append("synthetic truth was measured after run creation")
        _require_sha256(
            synthetic_truth.evidence_hash,
            "synthetic truth evidence_hash",
            failures,
        )
        if synthetic_truth.evidence_hash != synthetic_truth_evidence_hash(
            synthetic_truth
        ):
            failures.append("synthetic-truth evidence hash does not match its payload")
        for world, planted in SYNTHETIC_WORLD_PLANTS.items():
            result = synthetic_truth.world_results.get(world)
            if result is None:
                failures.append(f"synthetic world is missing: {world}")
                continue
            if result.get("planted") != planted:
                failures.append(f"synthetic world plant changed: {world}")
            setup_values = []
            for setup in ("S3-v1", "S5-v1"):
                recovered = result.get(setup)
                if recovered is None:
                    failures.append(f"synthetic world {world} is missing {setup}")
                    continue
                if not isinstance(recovered, (int, float)) or not math.isfinite(
                    recovered
                ):
                    failures.append(
                        f"synthetic world {world}/{setup} is not a finite number"
                    )
                    continue
                setup_values.append(recovered)
                if abs(recovered - planted) > SYNTHETIC_WORLD_TOLERANCE_R:
                    failures.append(
                        f"synthetic world {world}/{setup} exceeded bilateral tolerance"
                    )
            mean = result.get("mean")
            if not isinstance(mean, (int, float)) or not math.isfinite(mean):
                failures.append(f"synthetic world mean is not finite: {world}")
            elif len(setup_values) == 2 and abs(
                mean - sum(setup_values) / 2.0
            ) > 1e-12:
                failures.append(f"synthetic world mean is inconsistent: {world}")
        missing_properties = sorted(
            property_name
            for property_name in REQUIRED_SYNTHETIC_PROPERTIES
            if synthetic_truth.property_results.get(property_name) is not True
        )
        if missing_properties:
            failures.append(
                "synthetic properties did not pass: " + ", ".join(missing_properties)
            )

    if tuple(sorted(manifest.setup_versions)) != ("S3-v1", "S5-v1"):
        failures.append("official generation-one replay must contain S3-v1 and S5-v1")
    expected_versions = {
        "feature_version": "DAY-D-FEATURES-v1",
        "universe_version": "DAY-D-UNIVERSE-v1",
        "fill_version": "DAY-D-FILL-v1",
        "cost_model_version": "DAY-D-COST-v1",
        "risk_policy_version": "DAY-D-RISK-v1",
        "calendar_version": "DAY-D-CALENDAR-v1",
        "harness_version": "DAY-D-HARNESS-v1",
    }
    for field_name, expected in expected_versions.items():
        if getattr(manifest, field_name) != expected:
            failures.append(f"{field_name} must be {expected}")

    if failures:
        raise OfficialReplayBlocked("official replay blocked: " + "; ".join(failures))
