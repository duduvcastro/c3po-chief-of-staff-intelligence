#!/usr/bin/env python3
"""Reduce baseline + one-session M1 snapshots into publishable evidence.

Only this reducer sees entry identifiers.  It verifies the signed baseline and
every transient snapshot, replaces each recomputed session idempotently, then
reproduces the frozen session bootstrap and H3 ruler with the Python standard
library.  Its output contains aggregates and hashes only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import statistics
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo


BASELINE_RUN_ID = 33022905030
BASELINE_REPORT_SHA256 = (
    "23ede14e5d76cdd70bd1df58fcde62ad9445291eacae4872174b835ac4b94756"
)
BASELINE_SCHEMA = "ENTRY-QUALITY-STUDY-V1-REPORT-v1"
SNAPSHOT_SCHEMA = "C3PO_ENTRY_QUALITY_M1_SESSION_SNAPSHOT-v1"
OUTPUT_SCHEMA = "C3PO_ENTRY_QUALITY_M1_INCREMENTAL_REDUCED-v1"
POLICY_EPOCH = "policy-a-resume-2026-08-26"
POLICY_EPOCH_START = datetime(2026, 8, 26, 13, 30, 24, 983322, tzinfo=timezone.utc)
BOOTSTRAP_SEED = 20260824
BOOTSTRAP_ITERATIONS = 10_000
MIN_HYPOTHESIS_SESSIONS = 15
MIN_HYPOTHESIS_EPISODES_PER_CELL = 30
CENSORSHIP_REVIEW_PERCENT = 20.0
BARRIER_CATEGORIES = (
    "upper_first",
    "lower_first",
    "ambiguous_same_bar",
    "censored",
)
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
NEW_YORK = ZoneInfo("America/New_York")


class ReductionError(RuntimeError):
    """An input cannot support the frozen reduced reading."""


def json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        json_ready(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def without_field(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != field}


def verify_self_hash(
    payload: Mapping[str, Any],
    field: str,
    *,
    expected: str | None = None,
) -> str:
    claimed = payload.get(field)
    if not isinstance(claimed, str) or not HEX_64.fullmatch(claimed):
        raise ReductionError(f"{field} is missing or invalid")
    observed = canonical_sha256(without_field(payload, field))
    if claimed != observed:
        raise ReductionError(f"{field} mismatch: expected {claimed}, observed {observed}")
    if expected is not None and claimed != expected:
        raise ReductionError(f"{field} is not the pinned factual baseline")
    return claimed


def verify_baseline(report: Mapping[str, Any]) -> None:
    if report.get("schema_version") != BASELINE_SCHEMA:
        raise ReductionError("baseline report schema is not frozen V1")
    verify_self_hash(
        report,
        "report_sha256",
        expected=BASELINE_REPORT_SHA256,
    )
    if not report.get("analysis_interpretable"):
        raise ReductionError("factual baseline did not pass the entry gate")


def _as_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReductionError(f"{field} must be an object")
    return value


def _as_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ReductionError(f"{field} must be a list")
    return value


def _session(value: Any, field: str) -> str:
    try:
        parsed = datetime.strptime(str(value), "%Y-%m-%d")
    except ValueError as exc:
        raise ReductionError(f"{field} must be YYYY-MM-DD") from exc
    return parsed.date().isoformat()


def _finite_or_none(value: Any, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReductionError(f"{field} must be finite or null")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ReductionError(f"{field} must be finite or null")
    return parsed


def validate_measurement(value: Any, *, session: str) -> dict[str, Any]:
    row = dict(_as_mapping(value, "measurement"))
    entry_id = row.get("entry_id")
    if not isinstance(entry_id, str) or not entry_id:
        raise ReductionError("measurement.entry_id is missing")
    if _session(row.get("session_date"), "measurement.session_date") != session:
        raise ReductionError("measurement belongs to another session")
    if row.get("policy_epoch") != POLICY_EPOCH:
        raise ReductionError("measurement belongs to another policy epoch")
    if row.get("barrier_category") not in BARRIER_CATEGORIES:
        raise ReductionError("measurement barrier category is invalid")
    for field in (
        "composite_score",
        "primary_return_60m_percent",
        "mfe_percent",
        "mae_percent",
    ):
        _finite_or_none(row.get(field), f"measurement.{field}")
    return row


def validate_snapshot(value: Any) -> dict[str, Any]:
    snapshot = dict(_as_mapping(value, "session snapshot"))
    if snapshot.get("schema") != SNAPSHOT_SCHEMA:
        raise ReductionError("session snapshot schema is invalid")
    verify_self_hash(snapshot, "snapshot_sha256")
    session = _session(snapshot.get("session_date"), "session_date")
    if snapshot.get("policy_epoch") != POLICY_EPOCH:
        raise ReductionError("session snapshot is outside the current policy epoch")
    experiment = _as_mapping(snapshot.get("experiment"), "experiment")
    if experiment.get("code") != "R2D2-90D-001":
        raise ReductionError("session snapshot belongs to another experiment")
    for field in (
        "query_sha256",
        "ledger_session_sha256",
        "price_sources_sha256",
        "coverage_sha256",
        "entry_gate_sha256",
        "policy_epochs_sha256",
    ):
        if not isinstance(snapshot.get(field), str) or not HEX_64.fullmatch(snapshot[field]):
            raise ReductionError(f"session snapshot {field} is invalid")
    for field, source_field in (
        ("price_sources_sha256", "price_sources"),
        ("coverage_sha256", "coverage"),
        ("entry_gate_sha256", "entry_gate"),
    ):
        if canonical_sha256(snapshot.get(source_field)) != snapshot[field]:
            raise ReductionError(f"session snapshot {field} mismatch")

    access = _as_mapping(snapshot.get("database_access"), "database_access")
    if (
        access.get("effective_role") != "pg_read_all_data"
        or access.get("transaction_read_only") is not True
        or access.get("ddl_or_dml_executed") is not False
    ):
        raise ReductionError("session snapshot was not produced read-only")
    price = _as_mapping(snapshot.get("price_sources"), "price_sources")
    if price.get("missing_sessions") != []:
        raise ReductionError("session price source is incomplete")
    source_hashes = _as_mapping(
        snapshot.get("frozen_source_sha256"),
        "frozen_source_sha256",
    )
    if not source_hashes or any(
        not isinstance(value, str) or not HEX_64.fullmatch(value)
        for value in source_hashes.values()
    ):
        raise ReductionError("frozen app source hashes are invalid")

    source_ids = _as_list(snapshot.get("source_entry_ids"), "source_entry_ids")
    if any(not isinstance(item, str) or not item for item in source_ids):
        raise ReductionError("source_entry_ids contains an invalid identifier")
    if len(source_ids) != len(set(source_ids)):
        raise ReductionError("source_entry_ids contains duplicates")
    measurements = [
        validate_measurement(row, session=session)
        for row in _as_list(snapshot.get("measurements"), "measurements")
    ]
    measurement_ids = [row["entry_id"] for row in measurements]
    if len(measurement_ids) != len(set(measurement_ids)):
        raise ReductionError("snapshot contains duplicate measurements")
    if not set(measurement_ids).issubset(source_ids):
        raise ReductionError("snapshot measurement is outside its source population")

    gate = _as_mapping(snapshot.get("entry_gate"), "entry_gate")
    censorship = _as_mapping(
        gate.get("g3_coverage_censorship"),
        "entry_gate.g3_coverage_censorship",
    )
    violation_ids = set(_as_list(censorship.get("violation_entry_ids"), "violation ids"))
    unavailable_ids = set(
        _as_list(censorship.get("bar_unavailable_entry_ids"), "unavailable ids")
    )
    if not (violation_ids | unavailable_ids).issubset(source_ids):
        raise ReductionError("gate censorship is outside its source population")
    if set(measurement_ids) & (violation_ids | unavailable_ids):
        raise ReductionError("a censored entry was measured")
    blocking_failures = [
        failure
        for failure in _as_list(gate.get("failures"), "entry_gate.failures")
        if not isinstance(failure, Mapping)
        or failure.get("gate") != "market_compatibility_violation_rate"
    ]
    snapshot["session_date"] = session
    snapshot["source_entry_ids"] = source_ids
    snapshot["measurements"] = measurements
    snapshot["violation_ids"] = violation_ids
    snapshot["unavailable_ids"] = unavailable_ids
    snapshot["blocking_failures"] = blocking_failures
    return snapshot


def _baseline_population(
    report: Mapping[str, Any],
) -> tuple[dict[str, str], set[str], set[str], set[str]]:
    sessions: dict[str, str] = {}
    current_epoch_ids: set[str] = set()
    for row in _as_list(report.get("entry_measurements"), "baseline.entry_measurements"):
        item = _as_mapping(row, "baseline measurement")
        entry_id = str(item["entry_id"])
        sessions[entry_id] = _session(item["session_date"], "baseline session")
        if item.get("policy_epoch") == POLICY_EPOCH:
            current_epoch_ids.add(entry_id)
    gate = _as_mapping(report.get("entry_consistency_gate"), "baseline entry gate")
    censorship = _as_mapping(gate.get("g3_coverage_censorship"), "baseline censorship")
    violation_ids = set(_as_list(censorship.get("violation_entry_ids"), "baseline violations"))
    unavailable_ids = set(
        _as_list(censorship.get("bar_unavailable_entry_ids"), "baseline unavailable")
    )
    for row in _as_list(censorship.get("bar_unavailable"), "baseline unavailable rows"):
        item = _as_mapping(row, "baseline unavailable row")
        entry_id = str(item["entry_id"])
        sessions[entry_id] = _session(item["session_date"], "baseline session")
        observed = datetime.fromisoformat(
            str(item["executed_at"]).replace("Z", "+00:00")
        )
        if observed.astimezone(timezone.utc) >= POLICY_EPOCH_START:
            current_epoch_ids.add(entry_id)
    for row in _as_list(censorship.get("violations"), "baseline violation rows"):
        item = _as_mapping(row, "baseline violation row")
        observed = datetime.fromisoformat(str(item["executed_at"]).replace("Z", "+00:00"))
        entry_id = str(item["entry_id"])
        sessions[entry_id] = observed.astimezone(NEW_YORK).date().isoformat()
        if observed.astimezone(timezone.utc) >= POLICY_EPOCH_START:
            current_epoch_ids.add(entry_id)
    if set(sessions) != (
        {str(row["entry_id"]) for row in report["entry_measurements"]}
        | violation_ids
        | unavailable_ids
    ):
        raise ReductionError("baseline population cannot be reconstructed exactly")
    return sessions, violation_ids, unavailable_ids, current_epoch_ids


def merge_current_epoch(
    baseline: Mapping[str, Any],
    snapshots: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    (
        baseline_sessions,
        violations,
        unavailable,
        current_epoch_ids,
    ) = _baseline_population(baseline)
    measurements = {
        str(row["entry_id"]): dict(row)
        for row in baseline["entry_measurements"]
        if row.get("policy_epoch") == POLICY_EPOCH
    }
    source_sessions = dict(baseline_sessions)
    observed_sessions: set[str] = set()
    source_evidence: list[dict[str, Any]] = []
    blocking_failures: list[Any] = []
    common_contract: tuple[str, str, str] | None = None
    common_source_hashes: Mapping[str, Any] | None = None
    for raw_snapshot in snapshots:
        snapshot = validate_snapshot(raw_snapshot)
        session = snapshot["session_date"]
        if session in observed_sessions:
            raise ReductionError(f"duplicate session snapshot: {session}")
        observed_sessions.add(session)
        contract = (
            snapshot["query_sha256"],
            snapshot["policy_epochs_sha256"],
            str(snapshot["experiment"]["code"]),
        )
        source_hashes = snapshot["frozen_source_sha256"]
        if common_contract is None:
            common_contract = contract
            common_source_hashes = source_hashes
        elif contract != common_contract or source_hashes != common_source_hashes:
            raise ReductionError("session snapshots do not share one frozen contract")

        stale_ids = {
            entry_id
            for entry_id, day in source_sessions.items()
            if day == session and entry_id in current_epoch_ids
        }
        for entry_id in stale_ids:
            source_sessions.pop(entry_id, None)
            current_epoch_ids.discard(entry_id)
            violations.discard(entry_id)
            unavailable.discard(entry_id)
            measurements.pop(entry_id, None)
        for entry_id in snapshot["source_entry_ids"]:
            if entry_id in source_sessions:
                raise ReductionError("entry identifier appears in two sessions")
            source_sessions[entry_id] = session
            current_epoch_ids.add(entry_id)
        violations.update(snapshot["violation_ids"])
        unavailable.update(snapshot["unavailable_ids"])
        for row in snapshot["measurements"]:
            measurements[row["entry_id"]] = row
        blocking_failures.extend(snapshot["blocking_failures"])
        source_evidence.append({
            "session_date": session,
            "constructed_entry_count": len(snapshot["source_entry_ids"]),
            "measured_entry_count": len(snapshot["measurements"]),
            "snapshot_sha256": snapshot["snapshot_sha256"],
            "query_sha256": snapshot["query_sha256"],
            "ledger_session_sha256": snapshot["ledger_session_sha256"],
            "price_sources_sha256": snapshot["price_sources_sha256"],
            "coverage_sha256": snapshot["coverage_sha256"],
            "entry_gate_sha256": snapshot["entry_gate_sha256"],
            "frozen_source_sha256": snapshot["frozen_source_sha256"],
            "measurement_censoring": snapshot.get("measurement_censoring", {}),
        })

    maximum = float(
        baseline["entry_consistency_gate"]["g3_coverage_censorship"]["maximum_percent"]
    )
    constructed_count = len(source_sessions)
    violation_percent = len(violations) / constructed_count * 100.0 if constructed_count else 0.0
    baseline_non_rate_failures = [
        failure
        for failure in baseline["entry_consistency_gate"]["failures"]
        if failure.get("gate") != "market_compatibility_violation_rate"
    ]
    gate = {
        "passed": not baseline_non_rate_failures
        and not blocking_failures
        and violation_percent <= maximum,
        "constructed_entry_count": constructed_count,
        "measured_entry_count": len([
            row for row in measurements.values() if row.get("policy_epoch") == POLICY_EPOCH
        ]),
        "numeric_violation_censored_count": len(violations),
        "numeric_violation_percent": violation_percent,
        "bar_unavailable_censored_count": len(unavailable),
        "maximum_numeric_violation_percent": maximum,
        "non_rate_failure_count": len(baseline_non_rate_failures) + len(blocking_failures),
    }
    rows = sorted(
        measurements.values(),
        key=lambda row: (row["session_date"], row["executed_at"], row["entry_id"]),
    )
    return rows, gate, sorted(source_evidence, key=lambda row: row["session_date"])


def nearest_rank(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def bootstrap_estimates(
    rows: Sequence[Mapping[str, Any]],
    statistic: Callable[[Sequence[Mapping[str, Any]]], float | None],
) -> list[float]:
    by_session: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_session.setdefault(str(row["session_date"]), []).append(row)
    sessions = sorted(by_session)
    if not sessions:
        return []
    randomizer = random.Random(BOOTSTRAP_SEED)
    estimates: list[float] = []
    for _ in range(BOOTSTRAP_ITERATIONS):
        sample: list[Mapping[str, Any]] = []
        for session in randomizer.choices(sessions, k=len(sessions)):
            sample.extend(by_session[session])
        value = statistic(sample)
        if value is not None and math.isfinite(value):
            estimates.append(value)
    return estimates


def _mean_field(rows: Sequence[Mapping[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if row.get(field) is not None]
    return statistics.mean(values) if values else None


def _barrier_probability(
    rows: Sequence[Mapping[str, Any]],
    *,
    conservative: bool,
) -> float | None:
    upper = sum(row["barrier_category"] == "upper_first" for row in rows)
    lower = sum(row["barrier_category"] == "lower_first" for row in rows)
    ambiguous = sum(row["barrier_category"] == "ambiguous_same_bar" for row in rows)
    denominator = upper + lower + (ambiguous if conservative else 0)
    return upper / denominator if denominator else None


def summarize_cell(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    categories = {
        category: sum(row["barrier_category"] == category for row in rows)
        for category in BARRIER_CATEGORIES
    }
    resolved = categories["upper_first"] + categories["lower_first"]
    conservative_denominator = resolved + categories["ambiguous_same_bar"]
    primary_values = [
        float(row["primary_return_60m_percent"])
        for row in rows
        if row.get("primary_return_60m_percent") is not None
    ]
    primary_bootstrap = bootstrap_estimates(
        rows,
        lambda sample: _mean_field(sample, "primary_return_60m_percent"),
    )
    barrier_bootstrap = bootstrap_estimates(
        rows,
        lambda sample: _barrier_probability(sample, conservative=False),
    )
    conservative_bootstrap = bootstrap_estimates(
        rows,
        lambda sample: _barrier_probability(sample, conservative=True),
    )
    barrier_ci = (
        nearest_rank(barrier_bootstrap, 0.025),
        nearest_rank(barrier_bootstrap, 0.975),
    )
    censorship_percent = categories["censored"] / len(rows) * 100.0 if rows else 0.0
    return {
        "entry_count": len(rows),
        "session_count": len({row["session_date"] for row in rows}),
        "primary_plus_60m": {
            "observed_count": len(primary_values),
            "censored_count": len(rows) - len(primary_values),
            "mean_percent": statistics.mean(primary_values) if primary_values else None,
            "median_percent": statistics.median(primary_values) if primary_values else None,
            "bootstrap_ci95_percent": [
                nearest_rank(primary_bootstrap, 0.025),
                nearest_rank(primary_bootstrap, 0.975),
            ],
        },
        "barrier": {
            "categories": categories,
            "resolved_count": resolved,
            "p_hat": categories["upper_first"] / resolved if resolved else None,
            "p_hat_conservative": (
                categories["upper_first"] / conservative_denominator
                if conservative_denominator else None
            ),
            "bootstrap_ci95": list(barrier_ci),
            "p_hat_ucb_98_75": nearest_rank(barrier_bootstrap, 0.9875),
            "p_hat_cons_ucb_98_75": nearest_rank(
                conservative_bootstrap, 0.9875
            ),
            "verdict_against_50_percent": (
                "EDGE_ABOVE_REFERENCE"
                if barrier_ci[0] is not None and barrier_ci[0] > 0.5
                else "EDGE_BELOW_REFERENCE"
                if barrier_ci[1] is not None and barrier_ci[1] < 0.5
                else "INCONCLUSIVE"
            ),
            "censorship_percent": censorship_percent,
            "censorship_status": (
                "REVIEW_REQUIRED"
                if censorship_percent > CENSORSHIP_REVIEW_PERCENT
                else "ACCEPTABLE"
            ),
        },
        "mfe_percent": _mean_field(rows, "mfe_percent"),
        "mae_percent": _mean_field(rows, "mae_percent"),
    }


def summarize_h3(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    scored = sorted(
        (row for row in rows if row.get("composite_score") is not None),
        key=lambda row: (float(row["composite_score"]), str(row["entry_id"])),
    )
    decile_size = max(1, math.ceil(len(scored) / 10)) if scored else 1
    cells = {
        "bottom_decile": scored[:decile_size],
        "top_decile": scored[-decile_size:] if scored else [],
    }
    summaries = {name: summarize_cell(values) for name, values in cells.items()}
    observed_sessions = len({
        row["session_date"] for values in cells.values() for row in values
    })
    insufficient = [
        name
        for name, summary in summaries.items()
        if summary["barrier"]["resolved_count"]
        < MIN_HYPOTHESIS_EPISODES_PER_CELL
    ]
    floor_met = observed_sessions >= MIN_HYPOTHESIS_SESSIONS
    for summary in summaries.values():
        summary["hypothesis_sample_status"] = (
            "READY"
            if floor_met
            and summary["barrier"]["resolved_count"]
            >= MIN_HYPOTHESIS_EPISODES_PER_CELL
            else "INSUFFICIENT_SAMPLE"
        )
    return {
        "hypothesis": "canonical composite does not separate forward edge",
        "status": (
            "DESCRIPTIVE_READY" if floor_met and not insufficient
            else "INSUFFICIENT_SAMPLE"
        ),
        "required_session_count": MIN_HYPOTHESIS_SESSIONS,
        "required_decided_entries_per_cell": MIN_HYPOTHESIS_EPISODES_PER_CELL,
        "observed_session_count": observed_sessions,
        "insufficient_cells": insufficient,
        "cells": summaries,
    }


def build_reduced_artifact(
    baseline: Mapping[str, Any],
    snapshots: Sequence[Mapping[str, Any]],
    *,
    reducer_query_sha256: str,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if not HEX_64.fullmatch(reducer_query_sha256):
        raise ReductionError("reducer query SHA-256 is missing or invalid")
    verify_baseline(baseline)
    rows, gate, source_evidence = merge_current_epoch(baseline, snapshots)
    generated = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if gate["passed"]:
        summary = summarize_cell(rows)
        h3 = summarize_h3(rows)
        m1_classification = (
            "PILOT" if summary["session_count"] < MIN_HYPOTHESIS_SESSIONS
            else "FULL_SAMPLE"
        )
    else:
        summary = None
        h3 = None
        m1_classification = "BLOCKED_BY_ENTRY_CONSISTENCY_GATE"
    artefact: dict[str, Any] = {
        "schema": OUTPUT_SCHEMA,
        "generated_at": generated,
        "retention": {
            "days": 30,
            "expires_at": generated + timedelta(days=30),
            "enforcement": "github_private_artifact_retention",
            "expiry_action": "automatic_expungement_and_gate_item_reopen",
        },
        "query": {
            "reducer_sha256": reducer_query_sha256,
            "session_query_sha256": sorted({
                row["query_sha256"] for row in source_evidence
            }),
        },
        "baseline": {
            "workflow_run_id": BASELINE_RUN_ID,
            "report_sha256": BASELINE_REPORT_SHA256,
        },
        "source_evidence": source_evidence,
        "entry_consistency_gate": gate,
        "analysis_interpretable": gate["passed"],
        "classification": m1_classification,
        "m1": {
            "policy_epoch": POLICY_EPOCH,
            "available": summary is not None,
            "classification": m1_classification,
            "summary": summary,
            "cross_epoch_pooling": False,
        },
        "h3": h3,
        "governance": {
            "read_only": True,
            "raw_rows_retained": False,
            "entry_identifiers_retained": False,
            "strategy_change_authorized": False,
            "canonical_admission_automatic": False,
        },
    }
    # Enforce the publication boundary structurally, not by convention.
    ready = json_ready(artefact)
    serialized = canonical_json(ready)
    for forbidden in ('"entry_id"', '"source_entry_ids"', '"measurements"'):
        if forbidden in serialized:
            raise ReductionError(f"publishable artifact leaked {forbidden}")
    ready["artifact_sha256"] = canonical_sha256(ready)
    return ready


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-report", type=Path, required=True)
    parser.add_argument("--session-snapshot", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    baseline = json.loads(args.baseline_report.read_text(encoding="utf-8"))
    snapshots = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in args.session_snapshot
    ]
    artefact = build_reduced_artifact(
        baseline,
        snapshots,
        reducer_query_sha256=os.environ.get("C3PO_EVIDENCE_REDUCER_SHA256", ""),
    )
    rendered = canonical_json(artefact) + "\n"
    if args.output is not None:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
