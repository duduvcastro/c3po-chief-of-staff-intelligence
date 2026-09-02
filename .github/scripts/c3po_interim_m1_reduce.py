#!/usr/bin/env python3
"""Reduce server-side M1 sufficient statistics with the frozen bootstrap ruler.

The SQL peer emits no trade-level rows.  This program runs on the GitHub
runner, not on production, and deliberately refuses to calculate M1 unless the
SQL equivalence gate proves complete coverage of the canonical population.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


SOURCE_SCHEMA = "C3PO_ENTRY_QUALITY_M1_SERVER_AGGREGATE-v1"
OUTPUT_SCHEMA = "C3PO_ENTRY_QUALITY_M1_INTERIM_REDUCED-v2"
BLOCKED_SCHEMA = "C3PO_ENTRY_QUALITY_M1_SOURCE_BLOCKED-v1"
POLICY_EPOCH = "policy-a-resume-2026-08-26"
BOOTSTRAP_SEED = 20260824
BOOTSTRAP_ITERATIONS = 10_000
MIN_DECISION_SESSIONS = 15
MIN_HYPOTHESIS_ENTRIES_PER_CELL = 30
CENSORSHIP_REVIEW_PERCENT = 20.0
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
SENSITIVE_KEY = re.compile(
    r"(password|passwd|secret|token|credential|private.?key|api.?key|"
    r"endpoint|database.?url|dsn|uri|url)",
    re.IGNORECASE,
)
PROHIBITED_VALUE = re.compile(
    r"(postgres(?:ql)?://|https?://|gh[opusr]_[A-Za-z0-9_]+|"
    r"sk-[A-Za-z0-9_-]+)",
    re.IGNORECASE,
)
RAW_IDENTIFIER = re.compile(r"^[0-9a-f]{8}-[0-9a-f-]{27,}$", re.IGNORECASE)


class ReductionError(RuntimeError):
    """The reduced source violates the frozen M1 contract."""


class SourceIncomplete(ReductionError):
    """The persisted source cannot reproduce the canonical population."""

    def __init__(self, reasons: Sequence[str], fallback: Mapping[str, Any]) -> None:
        self.reasons = tuple(str(reason) for reason in reasons)
        self.fallback = dict(fallback)
        super().__init__(
            "source is not canonically equivalent: "
            + (", ".join(self.reasons) if self.reasons else "unspecified gate failure")
        )


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def nearest_rank(values: Sequence[float], fraction: float) -> float | None:
    """Mirror r2d2_entry_quality_engine._percentile exactly."""
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReductionError(f"{field} must be a non-negative integer")
    return value


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReductionError(f"{field} must be numeric")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ReductionError(f"{field} must be finite")
    return parsed


def _session(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ReductionError(f"{field} must be an ISO session date")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ReductionError(f"{field} must be an ISO session date") from exc
    return value


def validate_session_stats(
    rows: Any,
    *,
    include_continuous: bool = False,
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise ReductionError("session_stats must be a list")
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    for index, source in enumerate(rows):
        if not isinstance(source, Mapping):
            raise ReductionError(f"session_stats[{index}] must be an object")
        prefix = f"session_stats[{index}]"
        row: dict[str, Any] = {
            "session_date": _session(source.get("session_date"), f"{prefix}.session_date"),
            "entry_count": _integer(source.get("entry_count"), f"{prefix}.entry_count"),
            "upper_first": _integer(source.get("upper_first"), f"{prefix}.upper_first"),
            "lower_first": _integer(source.get("lower_first"), f"{prefix}.lower_first"),
            "ambiguous_same_bar": _integer(
                source.get("ambiguous_same_bar"),
                f"{prefix}.ambiguous_same_bar",
            ),
            "censored": _integer(source.get("censored"), f"{prefix}.censored"),
        }
        if sum(row[name] for name in (
            "upper_first", "lower_first", "ambiguous_same_bar", "censored"
        )) != row["entry_count"]:
            raise ReductionError(f"{prefix} categories do not equal entry_count")
        cell: str | None = None
        if "cell" in source:
            cell = str(source["cell"])
            if cell not in {"bottom_decile", "top_decile"}:
                raise ReductionError(f"{prefix}.cell is not an H3 cell")
            row["cell"] = cell
        key = (row["session_date"], cell)
        if key in seen:
            raise ReductionError(f"duplicate session statistic: {key}")
        seen.add(key)
        if include_continuous:
            for stem in ("primary", "mfe", "mae"):
                count_name = f"{stem}_observed_count"
                sum_name = f"{stem}_sum"
                row[count_name] = _integer(source.get(count_name), f"{prefix}.{count_name}")
                row[sum_name] = _finite_number(source.get(sum_name), f"{prefix}.{sum_name}")
                if row[count_name] > row["entry_count"]:
                    raise ReductionError(f"{prefix}.{count_name} exceeds entry_count")
        output.append(row)
    return sorted(output, key=lambda row: (row.get("cell", ""), row["session_date"]))


def bootstrap_estimates(
    rows: Sequence[Mapping[str, Any]],
    statistic: Callable[[Sequence[Mapping[str, Any]]], float | None],
    *,
    seed: int = BOOTSTRAP_SEED,
    iterations: int = BOOTSTRAP_ITERATIONS,
) -> list[float]:
    """Session bootstrap with the same Random.choices call pattern as production."""
    by_session = {str(row["session_date"]): row for row in rows}
    sessions = sorted(by_session)
    if not sessions:
        return []
    randomizer = random.Random(seed)
    estimates: list[float] = []
    for _ in range(iterations):
        sampled = [
            by_session[session]
            for session in randomizer.choices(sessions, k=len(sessions))
        ]
        value = statistic(sampled)
        if value is not None and math.isfinite(value):
            estimates.append(value)
    return estimates


def _barrier_probability(
    rows: Sequence[Mapping[str, Any]],
    *,
    conservative: bool,
) -> float | None:
    upper = sum(int(row["upper_first"]) for row in rows)
    lower = sum(int(row["lower_first"]) for row in rows)
    ambiguous = sum(int(row["ambiguous_same_bar"]) for row in rows)
    denominator = upper + lower + (ambiguous if conservative else 0)
    return upper / denominator if denominator else None


def _mean_from_sufficient_stats(
    rows: Sequence[Mapping[str, Any]],
    *,
    stem: str,
) -> float | None:
    count = sum(int(row[f"{stem}_observed_count"]) for row in rows)
    total = sum(float(row[f"{stem}_sum"]) for row in rows)
    return total / count if count else None


def summarize_barrier(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    categories = {
        name: sum(int(row[name]) for row in rows)
        for name in ("upper_first", "lower_first", "ambiguous_same_bar", "censored")
    }
    entry_count = sum(int(row["entry_count"]) for row in rows)
    resolved = categories["upper_first"] + categories["lower_first"]
    conservative_denominator = resolved + categories["ambiguous_same_bar"]
    central = bootstrap_estimates(
        rows,
        lambda sample: _barrier_probability(sample, conservative=False),
    )
    conservative = bootstrap_estimates(
        rows,
        lambda sample: _barrier_probability(sample, conservative=True),
    )
    ci = [nearest_rank(central, 0.025), nearest_rank(central, 0.975)]
    censorship_percent = (
        categories["censored"] / entry_count * 100.0 if entry_count else 0.0
    )
    return {
        "categories": categories,
        "resolved_count": resolved,
        "p_hat": categories["upper_first"] / resolved if resolved else None,
        "p_hat_conservative": (
            categories["upper_first"] / conservative_denominator
            if conservative_denominator else None
        ),
        "bootstrap_ci95": ci,
        "p_hat_ucb_98_75": nearest_rank(central, 0.9875),
        "p_hat_cons_ucb_98_75": nearest_rank(conservative, 0.9875),
        "verdict_against_50_percent": (
            "EDGE_ABOVE_REFERENCE"
            if ci[0] is not None and ci[0] > 0.5
            else "EDGE_BELOW_REFERENCE"
            if ci[1] is not None and ci[1] < 0.5
            else "INCONCLUSIVE"
        ),
        "censorship_percent": censorship_percent,
        "censorship_status": (
            "REVIEW_REQUIRED"
            if censorship_percent > CENSORSHIP_REVIEW_PERCENT
            else "ACCEPTABLE"
        ),
    }


def summarize_h3_cell(
    rows: Sequence[Mapping[str, Any]],
    *,
    primary_median: float | None,
) -> dict[str, Any]:
    entry_count = sum(int(row["entry_count"]) for row in rows)
    primary_count = sum(int(row["primary_observed_count"]) for row in rows)
    primary_total = sum(float(row["primary_sum"]) for row in rows)
    primary_estimates = bootstrap_estimates(
        rows,
        lambda sample: _mean_from_sufficient_stats(sample, stem="primary"),
    )
    mfe_count = sum(int(row["mfe_observed_count"]) for row in rows)
    mae_count = sum(int(row["mae_observed_count"]) for row in rows)
    return {
        "entry_count": entry_count,
        "session_count": len({str(row["session_date"]) for row in rows}),
        "primary_plus_60m": {
            "observed_count": primary_count,
            "censored_count": entry_count - primary_count,
            "mean_percent": primary_total / primary_count if primary_count else None,
            "median_percent": primary_median,
            "bootstrap_ci95_percent": [
                nearest_rank(primary_estimates, 0.025),
                nearest_rank(primary_estimates, 0.975),
            ],
        },
        "barrier": summarize_barrier(rows),
        "mfe_percent": (
            sum(float(row["mfe_sum"]) for row in rows) / mfe_count
            if mfe_count else None
        ),
        "mae_percent": (
            sum(float(row["mae_sum"]) for row in rows) / mae_count
            if mae_count else None
        ),
    }


def summarize_h3(
    rows: Sequence[Mapping[str, Any]],
    cell_totals: Mapping[str, Any],
) -> dict[str, Any]:
    ordered_cells = ("bottom_decile", "top_decile")
    summaries: dict[str, Any] = {}
    for cell in ordered_cells:
        cell_rows = [row for row in rows if row.get("cell") == cell]
        total = cell_totals.get(cell) if isinstance(cell_totals, Mapping) else None
        if total is not None and not isinstance(total, Mapping):
            raise ReductionError(f"h3.cell_totals.{cell} must be an object")
        raw_median = (total or {}).get("primary_median")
        median = (
            None
            if raw_median is None
            else _finite_number(raw_median, f"h3.cell_totals.{cell}.primary_median")
        )
        summaries[cell] = summarize_h3_cell(cell_rows, primary_median=median)

    observed_sessions = len({str(row["session_date"]) for row in rows})
    insufficient = [
        cell
        for cell in ordered_cells
        if summaries[cell]["barrier"]["resolved_count"]
        < MIN_HYPOTHESIS_ENTRIES_PER_CELL
    ]
    session_floor_met = observed_sessions >= MIN_DECISION_SESSIONS
    for cell in ordered_cells:
        summaries[cell]["hypothesis_sample_status"] = (
            "READY"
            if session_floor_met
            and summaries[cell]["barrier"]["resolved_count"]
            >= MIN_HYPOTHESIS_ENTRIES_PER_CELL
            else "INSUFFICIENT_SAMPLE"
        )
    return {
        "hypothesis": "canonical composite does not separate forward edge",
        "status": (
            "DESCRIPTIVE_READY"
            if session_floor_met and not insufficient
            else "INSUFFICIENT_SAMPLE"
        ),
        "required_session_count": MIN_DECISION_SESSIONS,
        "required_decided_entries_per_cell": MIN_HYPOTHESIS_ENTRIES_PER_CELL,
        "observed_session_count": observed_sessions,
        "insufficient_cells": insufficient,
        "cells": summaries,
    }


def _parse_generated_at(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ReductionError("generated_at must be an RFC3339 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReductionError("generated_at must be an RFC3339 string") from exc
    if parsed.tzinfo is None:
        raise ReductionError("generated_at must include a timezone")
    return parsed.astimezone(timezone.utc)


def _require_hash(value: str, field: str) -> str:
    if not HEX_64.fullmatch(value):
        raise ReductionError(f"{field} must be a lowercase SHA-256")
    return value


def _validate_source_contract(source: Mapping[str, Any]) -> None:
    if source.get("schema") != SOURCE_SCHEMA:
        raise ReductionError("unsupported aggregate source schema")
    access = source.get("database_access")
    if not isinstance(access, Mapping):
        raise ReductionError("database_access is missing")
    if access.get("effective_role") != "pg_read_all_data":
        raise ReductionError("aggregate was not read under pg_read_all_data")
    if access.get("transaction_read_only") != "on":
        raise ReductionError("aggregate transaction was not read-only")
    if access.get("statement_timeout") not in {"2min", "120s", "120000ms"}:
        raise ReductionError("aggregate statement_timeout is not 120 seconds")
    if access.get("lock_timeout") not in {"5s", "5000ms"}:
        raise ReductionError("aggregate lock_timeout is not 5 seconds")
    if access.get("ddl_or_dml_executed") is not False:
        raise ReductionError("aggregate does not attest zero DDL/DML")

    ruler = source.get("ruler")
    if not isinstance(ruler, Mapping):
        raise ReductionError("ruler is missing")
    expected = {
        "policy_epoch": POLICY_EPOCH,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_iterations": BOOTSTRAP_ITERATIONS,
        "percentile_method": "nearest_rank_ceil_qn_minus_1",
        "current_epoch_only": True,
        "cross_epoch_pooling": False,
    }
    mismatches = [key for key, value in expected.items() if ruler.get(key) != value]
    if mismatches:
        raise ReductionError("frozen ruler mismatch: " + ", ".join(sorted(mismatches)))

    equivalence = source.get("equivalence")
    if not isinstance(equivalence, Mapping):
        raise ReductionError("equivalence gate is missing")
    if (
        equivalence.get("canonical_equivalent") is not True
        or equivalence.get("source_complete") is not True
    ):
        reasons = equivalence.get("reasons")
        fallback = source.get("fallback")
        raise SourceIncomplete(
            reasons if isinstance(reasons, list) else ["equivalence_gate_failed"],
            fallback if isinstance(fallback, Mapping) else {},
        )


def _walk_for_sensitive_values(value: Any, path: str = "root") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if SENSITIVE_KEY.search(str(key)):
                raise ReductionError(f"sensitive key in reduced artifact: {path}.{key}")
            _walk_for_sensitive_values(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_for_sensitive_values(child, f"{path}[{index}]")
    elif isinstance(value, str):
        if PROHIBITED_VALUE.search(value):
            raise ReductionError(f"prohibited value in reduced artifact: {path}")
        if RAW_IDENTIFIER.fullmatch(value):
            raise ReductionError(f"raw identifier in reduced artifact: {path}")


def reduce_source(
    source: Mapping[str, Any],
    *,
    source_sha256: str,
    query_sha256: str,
    reducer_sha256: str,
) -> dict[str, Any]:
    _validate_source_contract(source)
    source_sha256 = _require_hash(source_sha256, "source_sha256")
    query_sha256 = _require_hash(query_sha256, "query_sha256")
    reducer_sha256 = _require_hash(reducer_sha256, "reducer_sha256")
    generated_at = _parse_generated_at(source.get("generated_at"))

    m1_rows = validate_session_stats(source.get("session_stats"))
    if not m1_rows:
        raise ReductionError("equivalent aggregate has no current-epoch session stats")
    barrier = summarize_barrier(m1_rows)
    session_count = len(m1_rows)
    entry_count = sum(int(row["entry_count"]) for row in m1_rows)

    h3_source = source.get("h3")
    if not isinstance(h3_source, Mapping):
        raise ReductionError("h3 source is missing")
    h3_rows = validate_session_stats(
        h3_source.get("session_stats"),
        include_continuous=True,
    )
    h3 = summarize_h3(h3_rows, h3_source.get("cell_totals") or {})

    cohort = source.get("cohort")
    if not isinstance(cohort, Mapping):
        raise ReductionError("cohort source is missing")
    measured_count = _integer(
        cohort.get("current_epoch_measured_count"),
        "cohort.current_epoch_measured_count",
    )
    if measured_count != entry_count:
        raise ReductionError("session stats do not reconcile to measured cohort")

    decision_reading = session_count >= MIN_DECISION_SESSIONS
    ucb = barrier["p_hat_ucb_98_75"]
    refuted = bool(decision_reading and ucb is not None and ucb <= 0.5)
    expires_at = generated_at + timedelta(days=30)

    payload: dict[str, Any] = {
        "schema": OUTPUT_SCHEMA,
        "generated_at": generated_at.isoformat(),
        "retention": {
            "days": 30,
            "expires_at": expires_at.isoformat(),
            "enforcement": "github_private_artifact_retention",
            "expiry_action": "automatic_expungement_and_gate_item_reopen",
        },
        "query": {
            "path": ".github/scripts/c3po_interim_m1_server_aggregate.sql",
            "sha256": query_sha256,
        },
        "reducer": {
            "path": ".github/scripts/c3po_interim_m1_reduce.py",
            "sha256": reducer_sha256,
        },
        "database_access": {
            "effective_role": "pg_read_all_data",
            "transaction_read_only": True,
            "statement_timeout": source["database_access"]["statement_timeout"],
            "lock_timeout": source["database_access"]["lock_timeout"],
            "ddl_or_dml_executed": False,
        },
        "source_evidence": {
            "aggregate_sha256": source_sha256,
            "canonical_equivalent": True,
            "complete_population": True,
            "server_side_aggregate_only": True,
        },
        "dry_run": True,
        "analysis_interpretable": True,
        "entry_gate_passed": True,
        "classification": "PILOT" if session_count < MIN_DECISION_SESSIONS else "FULL_SAMPLE",
        "cohort": {
            "constructed_entry_count": cohort.get("current_epoch_constructed_count"),
            "market_compatibility_censored_count": (
                int(cohort.get("current_epoch_bar_unavailable_count") or 0)
                + int(cohort.get("current_epoch_market_compatibility_violation_count") or 0)
            ),
            "numeric_violation_censored_count": cohort.get(
                "current_epoch_market_compatibility_violation_count"
            ),
            "bar_unavailable_censored_count": cohort.get(
                "current_epoch_bar_unavailable_count"
            ),
            "measured_entry_count": measured_count,
        },
        "m1": {
            "policy_epoch": POLICY_EPOCH,
            "available": True,
            "classification": (
                "PILOT" if session_count < MIN_DECISION_SESSIONS else "FULL_SAMPLE"
            ),
            "cross_epoch_pooling": False,
            "population": {
                "entry_count": entry_count,
                "session_count": session_count,
            },
            "barrier": barrier,
            "kill_criterion": {
                "minimum_session_count": MIN_DECISION_SESSIONS,
                "observed_session_count": session_count,
                "reading_eligible": decision_reading,
                "one_sided_ucb_level": 0.9875,
                "threshold": 0.5,
                "refuted": refuted if decision_reading else None,
                "result": (
                    "WAIT_SAMPLE"
                    if not decision_reading
                    else "V1_REFUTED"
                    if refuted
                    else "NOT_REFUTED"
                ),
            },
        },
        "h3": h3,
        "partial_verdict": {
            "status": "PILOT_ONLY" if not decision_reading else "DECISION_READING_READY",
            "m1": barrier["verdict_against_50_percent"],
            "h3": h3["status"],
            "strategy_change_authorized": False,
            "canonical_admission_automatic": False,
        },
    }
    payload["artifact_sha256"] = canonical_sha256(payload)
    _walk_for_sensitive_values(payload)
    return payload


def blocked_diagnostic(error: SourceIncomplete) -> dict[str, Any]:
    """A console-only diagnostic.  It is deliberately not an M1 artifact."""
    return {
        "schema": BLOCKED_SCHEMA,
        "status": "BLOCKED_SOURCE_INCOMPLETE",
        "m1_emitted": False,
        "reasons": list(error.reasons),
        "fallback": error.fallback,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail-closed runner-side reducer for server-aggregated M1 evidence",
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--query",
        type=Path,
        default=Path(".github/scripts/c3po_interim_m1_server_aggregate.sql"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    input_bytes = args.input.read_bytes()
    try:
        source = json.loads(input_bytes)
    except json.JSONDecodeError as exc:
        raise SystemExit("aggregate source is not valid JSON") from exc
    if not isinstance(source, Mapping):
        raise SystemExit("aggregate source must be a JSON object")

    reducer_path = Path(__file__).resolve()
    try:
        payload = reduce_source(
            source,
            source_sha256=hashlib.sha256(input_bytes).hexdigest(),
            query_sha256=file_sha256(args.query),
            reducer_sha256=file_sha256(reducer_path),
        )
    except SourceIncomplete as exc:
        diagnostic = blocked_diagnostic(exc)
        _walk_for_sensitive_values(diagnostic)
        print(json.dumps(diagnostic, ensure_ascii=True, sort_keys=True), file=sys.stderr)
        return 3
    except ReductionError as exc:
        print(f"M1 reduction rejected: {exc}", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.tmp-{os.getpid()}")
    try:
        temporary.write_bytes(canonical_json_bytes(payload) + b"\n")
        os.replace(temporary, args.output)
    finally:
        temporary.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
