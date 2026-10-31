"""Instrument binding for the owner-signed ensemble protocol, before any labels.

The binding is an out-of-band trust anchor: its pin digest and comment identities
must come from the reviewed, owner-signed technical-channel receipt. A supplied
JSON document cannot authenticate its own signature or grant operational authority.
This module verifies bytes/identity against that anchor; it does not publish a pin.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .valuation_ensemble_inputs import canonical_hash


PREREG_COMMIT = "3908cb9672b7fb4ed03124907b50caa14c5e36f2"  # rev 2, owner-signed 31/10/2026 18:36 BRT (receipt 6549453772)
PREREG_SHA256 = "b786ef8ff21d2b0dbcc2e39bcaec3a984e7a204b8a796d34a84c49ace69db9a9"
REV3_MANIFEST_SHA256 = "73a81bcef1cd93425dfab785ae57c52118ba09493a4b7169e31a0e0b6665f805"
PIN_SCHEMA = "VALUATION-ENSEMBLE-INSTRUMENT-PIN-v1"
MANIFEST_SCHEMA = "VALUATION-ENSEMBLE-GRID-MANIFEST-v1"
PROTOCOL_CONSTANTS: dict[str, Any] = {
    "primary": "minmax_trimmed_mean_with_consensus", "minimum_values": 3,
    "decision_horizon": 126, "required_horizon": 252, "descriptive_horizons": [21, 63],
    "ic_min": 0.02, "p_max": 0.05, "attrition_cap_126": 0.15,
    "minimum_blocks_126": 8, "coverage_floor": 0.60, "median_screened_floor": 150,
    "minimum_ic_names": 10, "minimum_spread_names": 30,
    "block_variance_factor": 1.5, "design_seed": 20261026,
    "precision": "median_absolute_log_error_served_minus_ensemble",
    "prediction": "h_over_252_times_log_tp_over_price",
    "trimmed_extremes": "exactly_one_minimum_and_one_maximum",
    "consensus": "mean_latest_eligible_per_house_from_pinned_V3_RAW_snapshot",
}


@dataclass(frozen=True)
class InstrumentBinding:
    expected_pin_sha256: str
    prereg_commit: str
    instrument_commit: str
    owner_signature_comment_id: int
    technical_GO_comment_id: int


def _digest(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _commit(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def _positive_id(value: Any) -> bool:
    return type(value) is int and value > 0


def _instrument_path(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if value in (".github/workflows/valuation-ensemble-grid.yml", ".github/workflows/valuation-ensemble-readiness.yml"):
        return True
    return re.fullmatch(r"c3po/backend/app/(valuation_ensemble_[a-z0-9_]+|valuation_pit_rerun|valuation_accuracy_report|valuation_pit_backtest_report|valuation_pit_panel|valuation_panel|valuation_price_history|statement_vintages|sec_xbrl|cvm_fundamentals|valuation_asfiled|valuation_v2_engine|valuation_pit_served|valuation_official|valuation_v3_macro)\.py", value) is not None


def _instant(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset() is None:
            return None
        return result.astimezone(timezone.utc)
    except ValueError:
        return None


def instrument_file_hashes(repository_root: Path | None = None) -> dict[str, str]:
    """Hash the complete instrument surface, including executor and workflow.

    Reads implementation source bytes only. There is no data, DB or label read.
    Missing required files are an error, not a smaller instrument inventory.
    """
    root = repository_root or Path(__file__).resolve().parents[3]
    app = root / "c3po/backend/app"
    files = sorted(app.glob("valuation_ensemble_*.py"))
    files += [app / name for name in ("valuation_pit_rerun.py", "valuation_accuracy_report.py",
        "valuation_pit_backtest_report.py", "valuation_pit_panel.py", "valuation_panel.py",
        "valuation_price_history.py", "statement_vintages.py", "sec_xbrl.py", "cvm_fundamentals.py",
        "valuation_asfiled.py", "valuation_v2_engine.py", "valuation_pit_served.py", "valuation_official.py", "valuation_v3_macro.py")]
    files += [root / ".github/workflows/valuation-ensemble-grid.yml",
              root / ".github/workflows/valuation-ensemble-readiness.yml"]  # rev 2 §6: the readiness run before the pin
    required = {"valuation_ensemble_grid.py", "valuation_ensemble_grid_consensus.py",
                "valuation_ensemble_report.py", "valuation_ensemble_executor.py",
                "valuation_ensemble_pin.py", "valuation_ensemble_frozen.py", "valuation_ensemble_readiness.py",
                "valuation-ensemble-readiness.yml"}
    if not required.issubset({p.name for p in files}):
        raise ValueError("ensemble_instrument_inventory_incomplete")
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def validate_instrument_pin(pin: Mapping[str, Any] | None, *, file_hashes: Mapping[str, str],
                            binding: InstrumentBinding) -> list[str]:
    if pin is None:
        return ["ensemble_instrument_not_pinned"]
    if not isinstance(pin, Mapping) or not isinstance(file_hashes, Mapping) or not isinstance(binding, InstrumentBinding):
        return ["ensemble_instrument_pin_invalid"]
    problems: list[str] = []
    try:
        identity = canonical_hash(dict(pin))
    except (ValueError, TypeError, OverflowError):
        return ["ensemble_instrument_pin_invalid"]
    if not _digest(binding.expected_pin_sha256) or identity != binding.expected_pin_sha256:
        problems.append("ensemble_instrument_pin_identity_mismatch")
    if (binding.prereg_commit != PREREG_COMMIT or pin.get("prereg_commit") != PREREG_COMMIT
            or pin.get("prereg_sha256") != PREREG_SHA256):
        problems.append("ensemble_prereg_identity_mismatch")
    if pin.get("schema") != PIN_SCHEMA:
        problems.append("ensemble_instrument_pin_schema")
    if not _commit(binding.instrument_commit) or pin.get("instrument_commit") != binding.instrument_commit:
        problems.append("ensemble_instrument_commit_mismatch")
    for key, expected in (("owner_signature_comment_id", binding.owner_signature_comment_id),
                          ("technical_GO_comment_id", binding.technical_GO_comment_id)):
        if not _positive_id(expected) or not _positive_id(pin.get(key)) or pin.get(key) != expected:
            problems.append("ensemble_instrument_" + key + "_mismatch")
    if pin.get("constants") != PROTOCOL_CONSTANTS:
        problems.append("ensemble_instrument_constants_mismatch")
    if _instant(pin.get("published_at")) is None:
        problems.append("ensemble_instrument_pin_publication_time_invalid")
    expected_files = pin.get("files")
    if (not isinstance(expected_files, dict) or not expected_files or not file_hashes
            or any(not isinstance(k, str) for k in expected_files)
            or any(not isinstance(k, str) for k in file_hashes)):
        problems.append("ensemble_instrument_file_inventory_missing")
    else:
        if set(expected_files) != set(file_hashes):
            problems.append("ensemble_instrument_file_inventory_mismatch")
        for name in sorted(set(expected_files) | set(file_hashes)):
            if not _instrument_path(name):
                problems.append("ensemble_instrument_noncanonical_file_path")
            if (not _digest(expected_files.get(name)) or not _digest(file_hashes.get(name))
                    or expected_files.get(name) != file_hashes.get(name)):
                problems.append("ensemble_instrument_mismatch:" + name)
        required_names = {"valuation_ensemble_grid.py", "valuation_ensemble_grid_consensus.py",
                          "valuation_ensemble_report.py", "valuation_ensemble_executor.py",
                          "valuation_ensemble_pin.py", "valuation_pit_rerun.py", "valuation_accuracy_report.py", "valuation-ensemble-grid.yml",
                          "valuation_ensemble_frozen.py", "valuation_ensemble_readiness.py", "valuation-ensemble-readiness.yml"}
        if not required_names.issubset({Path(name).name for name in expected_files}):
            problems.append("ensemble_instrument_required_file_missing")
    return sorted(set(problems))


def validate_manifest_binding(manifest: Mapping[str, Any], pin: Mapping[str, Any],
                              binding: InstrumentBinding) -> list[str]:
    """Validate run binding and timing; report additionally checks paired inputs/grid.

    Pin validation against actual source bytes must have succeeded first.
    A backdated JSON timestamp is not independent proof of publication: the binding
    still has to originate from the already published signed channel receipt.
    """
    if not isinstance(manifest, Mapping) or not isinstance(pin, Mapping) or not isinstance(binding, InstrumentBinding):
        return ["ensemble_manifest_invalid"]
    problems: list[str] = []
    if manifest.get("schema") != MANIFEST_SCHEMA:
        problems.append("ensemble_manifest_schema")
    if manifest.get("complete") is not True:
        problems.append("ensemble_manifest_not_complete")
    if manifest.get("prereg_sha256") != PREREG_SHA256:
        problems.append("ensemble_manifest_prereg_mismatch")
    if manifest.get("instrument_pin_sha256") != binding.expected_pin_sha256:
        problems.append("ensemble_manifest_pin_mismatch")
    if manifest.get("rev3_manifest_sha256") != REV3_MANIFEST_SHA256:
        problems.append("ensemble_inputs_differ_from_rev3")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        return sorted(set(problems + ["ensemble_manifest_entries_missing"]))
    published = _instant(pin.get("published_at"))
    identities: set[tuple[Any, Any, Any]] = set()
    for item in entries:
        if not isinstance(item, dict):
            problems.append("ensemble_manifest_entry_invalid")
            continue
        identity = (item.get("market"), item.get("session_date"), item.get("as_of"))
        if any(not isinstance(x, str) or not x for x in identity):
            problems.append("ensemble_manifest_duplicate_or_invalid_session")
            continue
        if identity in identities:
            problems.append("ensemble_manifest_duplicate_or_invalid_session")
        identities.add(identity)
        if item.get("instrument_commit") != binding.instrument_commit:
            problems.append("ensemble_run_instrument_commit_mismatch")
        if item.get("instrument_pin_sha256") != binding.expected_pin_sha256:
            problems.append("ensemble_run_pin_mismatch")
        if item.get("implementation_files") != pin.get("files"):
            problems.append("ensemble_run_instrument_files_mismatch")
        started = _instant(item.get("started_at"))
        if published is None or started is None or started < published:
            problems.append("ensemble_run_precedes_published_instrument_pin")
    return sorted(set(problems))
