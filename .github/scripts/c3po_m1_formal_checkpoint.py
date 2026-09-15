#!/usr/bin/env python3
"""Build a reduced formal M1 checkpoint from frozen per-session snapshots.

The module is deliberately orchestration-neutral.  It does not schedule a run,
open an issue, retain an artefact, or mutate the R2D2 breaker.  A remote private
runner may feed it chronological snapshots produced by
``c3po_m1_session_snapshot.py``.  Only the exact prefix reaching 15 or 20
measured sessions is admitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import c3po_m1_incremental_reducer as frozen


SCHEMA = "C3PO_ENTRY_QUALITY_M1_FORMAL_CHECKPOINT-v1"
POLICY_EPOCH = "policy-a-resume-2026-08-26"
POLICY_EPOCH_START = "2026-08-26"
CHECKPOINTS = (15, 20)
REFERENCE_PROBABILITY = 0.5
FORMAL_TAIL_PROBABILITY = 0.0125
FROZEN_NUMERIC_VIOLATION_PERCENT = 5.0
NOT_READY_EXIT = 3
MAX_ENUMERATION_INPUT_BYTES = 64 * 1024
MAX_BASELINE_INPUT_BYTES = 8 * 1024 * 1024
MAX_SNAPSHOT_INPUT_BYTES = 4 * 1024 * 1024
MAX_TOTAL_SNAPSHOT_INPUT_BYTES = 32 * 1024 * 1024
MAX_SESSION_SNAPSHOT_FILES = 512
MAX_PRIOR_ARTIFACT_INPUT_BYTES = 64 * 1024

MESA_SOURCE_SHA256 = (
    "b846371a89f9d5b3ec4ccadd8ac4cc470be89a24444cf992604dad072541658f"
)
V1_KILL_CRITERION_SHA256 = (
    "b2ea9f1ebf5de12fe9cdebae4ed84b7af4e3bc6379100b495f1d5819ff80c799"
)
ENTRY_QUALITY_SPEC_SHA256 = (
    "63cdb045a69dfe31246e82fa64e00dd1f9e0357897259a0d420ad81d0957a41e"
)
POLICY_EPOCHS_FILE_SHA256 = (
    "4333ccde1f6da47b113b1c5a9dbcc1df29bc0b171d483247172443b911688ae1"
)
POLICY_EPOCHS_MANIFEST_SHA256 = (
    "7c26c7e4ad011f74e752e00fce711451744d838d4d2923a86808fe12c1954dea"
)
FROZEN_SNAPSHOT_QUERY_SHA256 = (
    "3fe89fd60e7b544571eb45dfc478abc5ffcc08d448bcff4aab5dbd143b4d83f3"
)
FROZEN_INCREMENTAL_REDUCER_SHA256 = (
    "cfc90a1a9b35c0fa4aed8ae70d39bce29a1148d35bfcae5f6ad91a23293ac859"
)
FROZEN_APP_SOURCE_SHA256 = {
    "r2d2_entry_quality_engine.py": (
        "764bcc3ed9240debb5605217be0206599918acfae147d814841ea4ddd29d99e8"
    ),
    "r2d2_entry_quality_study.py": (
        "b39fbfc59b17fe9f6554dfb19912a604a30513e7524429bdaa697166be37d9c2"
    ),
}
FORMAL_LABELS = {
    "refuted_15": "M1_REFUTED_AT_15",
    "continue_20": "M1_CONTINUE_TO_20",
    "refuted_20": "M1_REFUTED_AT_20",
    "positive_20": "M1_POSITIVE_BOUND_AT_20",
    "inconclusive_20": "M1_INCONCLUSIVE_AT_20",
}
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FORBIDDEN_PUBLISHED_KEYS = {
    "entry_id",
    "source_entry_ids",
    "measurements",
    "symbol",
    "position",
    "trade_id",
}
CHECKPOINT_BINDING_FIELDS = (
    "schema",
    "label",
    "checkpoint",
    "population_counts",
    "formal_bounds",
    "entry_consistency_gate",
    "source_evidence",
    "frozen_contract",
    "governance",
)
FORMAL_TOP_LEVEL_FIELDS = set(CHECKPOINT_BINDING_FIELDS) | {
    "generated_at",
    "checkpoint_binding_sha256",
    "artifact_sha256",
}


class FormalCheckpointError(RuntimeError):
    """The evidence cannot support a formal M1 checkpoint."""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _input_size(path: Path, field: str, maximum: int) -> int:
    if not path.is_file():
        raise FormalCheckpointError(f"{field} is not a regular input file")
    size = path.stat().st_size
    if size > maximum:
        raise FormalCheckpointError(f"{field} exceeds its input byte ceiling")
    return size


def _bounded_input(path: Path, field: str, maximum: int) -> bytes:
    _input_size(path, field, maximum)
    value = path.read_bytes()
    # Recheck the actual read in case the file changed after stat().
    if len(value) > maximum:
        raise FormalCheckpointError(f"{field} exceeds its input byte ceiling")
    return value


def _bounded_json_object(path: Path, field: str, maximum: int) -> Mapping[str, Any]:
    return _json_object(_bounded_input(path, field, maximum), field)


def _json_object(source: bytes, field: str) -> Mapping[str, Any]:
    try:
        value = json.loads(source)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FormalCheckpointError(f"{field} is not valid JSON") from exc
    if not isinstance(value, Mapping):
        raise FormalCheckpointError(f"{field} must contain a JSON object")
    return value


def _assert_local_frozen_sources() -> dict[str, str]:
    root = Path(__file__).resolve().parent
    observed = {
        "session_snapshot.py": _file_sha256(root / "c3po_m1_session_snapshot.py"),
        "incremental_reducer.py": _file_sha256(
            root / "c3po_m1_incremental_reducer.py"
        ),
        "formal_checkpoint.py": _file_sha256(Path(__file__).resolve()),
    }
    expected = {
        "session_snapshot.py": FROZEN_SNAPSHOT_QUERY_SHA256,
        "incremental_reducer.py": FROZEN_INCREMENTAL_REDUCER_SHA256,
    }
    for name, digest in expected.items():
        if observed[name] != digest:
            raise FormalCheckpointError(f"frozen local source changed: {name}")
    return observed


def load_enumerated_sessions(path: Path) -> list[str]:
    try:
        source = _bounded_input(
            path,
            "session enumeration",
            MAX_ENUMERATION_INPUT_BYTES,
        ).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FormalCheckpointError("session enumeration is not UTF-8") from exc
    sessions = [line.strip() for line in source.splitlines()]
    if not sessions or any(not DATE.fullmatch(value) for value in sessions):
        raise FormalCheckpointError("session enumeration is empty or malformed")
    if sessions != sorted(set(sessions)):
        raise FormalCheckpointError("session enumeration is not unique and chronological")
    if sessions[0] != POLICY_EPOCH_START:
        raise FormalCheckpointError("session enumeration omits the first policy session")
    return sessions


def _float(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FormalCheckpointError(f"{field} must be numeric")
    observed = float(value)
    if not math.isfinite(observed):
        raise FormalCheckpointError(f"{field} must be finite")
    return observed


def _validate_frozen_snapshot(raw: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = frozen.validate_snapshot(raw)
    if snapshot["query_sha256"] != FROZEN_SNAPSHOT_QUERY_SHA256:
        raise FormalCheckpointError("snapshot query is outside the frozen contract")
    if snapshot["policy_epochs_sha256"] != POLICY_EPOCHS_FILE_SHA256:
        raise FormalCheckpointError("policy epoch table differs from the frozen contract")
    if snapshot["frozen_source_sha256"] != FROZEN_APP_SOURCE_SHA256:
        raise FormalCheckpointError("deployed entry-quality source differs from the freeze")
    censorship = snapshot["entry_gate"].get("g3_coverage_censorship") or {}
    maximum = _float(censorship.get("maximum_percent"), "maximum_percent")
    if maximum != FROZEN_NUMERIC_VIOLATION_PERCENT:
        raise FormalCheckpointError("numeric violation threshold differs from the freeze")
    return snapshot


def validate_snapshot_prefix(
    raw_snapshots: Sequence[Mapping[str, Any]],
    enumerated_sessions: Sequence[str],
) -> list[dict[str, Any]]:
    if not raw_snapshots:
        raise FormalCheckpointError("no session snapshots were provided")
    snapshots = sorted(
        (_validate_frozen_snapshot(value) for value in raw_snapshots),
        key=lambda item: item["session_date"],
    )
    dates = [item["session_date"] for item in snapshots]
    if len(dates) != len(set(dates)):
        raise FormalCheckpointError("duplicate session snapshot")
    if dates != list(enumerated_sessions[: len(dates)]):
        raise FormalCheckpointError("snapshots are not the exact enumeration prefix")
    contracts = {
        (
            item["query_sha256"],
            item["policy_epochs_sha256"],
            frozen.canonical_sha256(item["frozen_source_sha256"]),
        )
        for item in snapshots
    }
    if len(contracts) != 1:
        raise FormalCheckpointError("snapshots do not share one frozen contract")
    return snapshots


def _reduce_prefix(
    baseline: Mapping[str, Any],
    snapshots: Sequence[Mapping[str, Any]],
    *,
    include_summary: bool = True,
) -> dict[str, Any]:
    (
        baseline_sessions,
        violations,
        unavailable,
        current_epoch_ids,
    ) = frozen._baseline_population(baseline)
    measurements = {
        str(row["entry_id"]): dict(row)
        for row in baseline["entry_measurements"]
        if row.get("policy_epoch") == POLICY_EPOCH
    }
    source_sessions = dict(baseline_sessions)
    blocking_failures: list[Any] = []
    source_evidence: list[dict[str, Any]] = []

    for snapshot in snapshots:
        session_ids = set(snapshot["source_entry_ids"])
        session = snapshot["session_date"]
        stale_ids = {
            entry_id
            for entry_id, observed_session in source_sessions.items()
            if observed_session == session and entry_id in current_epoch_ids
        }
        for entry_id in stale_ids:
            source_sessions.pop(entry_id, None)
            current_epoch_ids.discard(entry_id)
            violations.discard(entry_id)
            unavailable.discard(entry_id)
            measurements.pop(entry_id, None)
        if set(source_sessions) & session_ids:
            raise FormalCheckpointError("entry identifier appears in two sessions")
        for entry_id in session_ids:
            source_sessions[entry_id] = session
            current_epoch_ids.add(entry_id)
        violations.update(snapshot["violation_ids"])
        unavailable.update(snapshot["unavailable_ids"])
        for row in snapshot["measurements"]:
            entry_id = row["entry_id"]
            if entry_id in measurements:
                raise FormalCheckpointError("duplicate entry measurement")
            measurements[entry_id] = row
        blocking_failures.extend(snapshot["blocking_failures"])
        source_evidence.append(
            {
                "session_date": snapshot["session_date"],
                "constructed_entry_count": len(session_ids),
                "measured_entry_count": len(snapshot["measurements"]),
                "snapshot_sha256": snapshot["snapshot_sha256"],
                "ledger_session_sha256": snapshot["ledger_session_sha256"],
                "price_sources_sha256": snapshot["price_sources_sha256"],
                "coverage_sha256": snapshot["coverage_sha256"],
                "entry_gate_sha256": snapshot["entry_gate_sha256"],
            }
        )

    constructed_count = len(source_sessions)
    violation_percent = (
        len(violations) / constructed_count * 100.0 if constructed_count else 0.0
    )
    baseline_non_rate_failures = [
        failure
        for failure in baseline["entry_consistency_gate"]["failures"]
        if failure.get("gate") != "market_compatibility_violation_rate"
    ]
    gate = {
        "passed": (
            not baseline_non_rate_failures
            and not blocking_failures
            and violation_percent <= FROZEN_NUMERIC_VIOLATION_PERCENT
        ),
        "constructed_entry_count": constructed_count,
        "measured_entry_count": len(
            [
                row
                for row in measurements.values()
                if row.get("policy_epoch") == POLICY_EPOCH
            ]
        ),
        "numeric_violation_censored_count": len(violations),
        "numeric_violation_percent": violation_percent,
        "bar_unavailable_censored_count": len(unavailable),
        "maximum_numeric_violation_percent": FROZEN_NUMERIC_VIOLATION_PERCENT,
        "non_rate_failure_count": len(baseline_non_rate_failures)
        + len(blocking_failures),
    }
    rows = sorted(
        measurements.values(),
        key=lambda row: (row["session_date"], row.get("executed_at", ""), row["entry_id"]),
    )
    result = {
        "measured_session_count": len({row["session_date"] for row in rows}),
        "gate": gate,
        "source_evidence": source_evidence,
        # This field never crosses the publication boundary.  Keeping the exact
        # baseline-replaced population here prevents the formal bounds from
        # accidentally diverging from the summary/gate population.
        "rows": rows,
    }
    if include_summary:
        result["summary"] = frozen.summarize_cell(rows)
    return result


def select_exact_prefix(
    baseline: Mapping[str, Any],
    snapshots: Sequence[Mapping[str, Any]],
    checkpoint: int,
) -> dict[str, Any] | None:
    if checkpoint not in CHECKPOINTS:
        raise FormalCheckpointError("formal checkpoint must be 15 or 20")
    for index in range(1, len(snapshots) + 1):
        reduced = _reduce_prefix(
            baseline,
            snapshots[:index],
            include_summary=False,
        )
        measured_sessions = int(reduced["measured_session_count"])
        if measured_sessions == checkpoint:
            reduced["summary"] = frozen.summarize_cell(reduced["rows"])
            reduced["snapshots"] = list(snapshots[:index])
            return reduced
        if measured_sessions > checkpoint:
            raise FormalCheckpointError("measured-session clock skipped a checkpoint")
    return None


def _formal_bounds(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, float]]:
    central = frozen.bootstrap_estimates(
        rows,
        lambda sample: frozen._barrier_probability(sample, conservative=False),
    )
    conservative = frozen.bootstrap_estimates(
        rows,
        lambda sample: frozen._barrier_probability(sample, conservative=True),
    )
    values = {
        "central": central,
        "conservative": conservative,
    }
    output: dict[str, dict[str, float]] = {"ucb_98_75": {}, "lcb_98_75": {}}
    for name, estimates in values.items():
        upper = frozen.nearest_rank(estimates, 1.0 - FORMAL_TAIL_PROBABILITY)
        lower = frozen.nearest_rank(estimates, FORMAL_TAIL_PROBABILITY)
        if upper is None or lower is None:
            raise FormalCheckpointError("formal barrier bounds are unavailable")
        output["ucb_98_75"][name] = upper
        output["lcb_98_75"][name] = lower
    return output


def _label(checkpoint: int, central_ucb: float, central_lcb: float) -> str:
    if central_ucb <= REFERENCE_PROBABILITY:
        return FORMAL_LABELS[f"refuted_{checkpoint}"]
    if checkpoint == 15:
        return FORMAL_LABELS["continue_20"]
    if central_lcb > REFERENCE_PROBABILITY:
        return FORMAL_LABELS["positive_20"]
    return FORMAL_LABELS["inconclusive_20"]


def _assert_publication_boundary(payload: Mapping[str, Any]) -> None:
    rendered = frozen.canonical_json(payload)
    for key in FORBIDDEN_PUBLISHED_KEYS:
        if f'"{key}"' in rendered:
            raise FormalCheckpointError(f"reduced artifact leaked {key}")
    if len(rendered.encode("utf-8")) > 65_536:
        raise FormalCheckpointError("reduced formal artifact exceeds 64 KiB")


def _checkpoint_binding_view(payload: Mapping[str, Any]) -> dict[str, Any]:
    try:
        view = {field: payload[field] for field in CHECKPOINT_BINDING_FIELDS}
        contract = dict(view["frozen_contract"])
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalCheckpointError("formal checkpoint binding is incomplete") from exc
    # The enumerator is append-only: its whole-file hash legitimately changes
    # between the 15th and 20th readings.  The exact selected prefix is instead
    # bound by checkpoint dates plus every reduced source-evidence hash.
    contract.pop("session_enumeration_sha256", None)
    view["frozen_contract"] = contract
    return view


def _checkpoint_binding_sha256(payload: Mapping[str, Any]) -> str:
    return frozen.canonical_sha256(_checkpoint_binding_view(payload))


def _validate_prior_15_artifact(raw: Mapping[str, Any]) -> dict[str, Any]:
    prior = dict(raw)
    if set(prior) != FORMAL_TOP_LEVEL_FIELDS:
        raise FormalCheckpointError("checkpoint 15 artifact fields are not exact")
    try:
        frozen.verify_self_hash(prior, "artifact_sha256")
    except frozen.ReductionError as exc:
        raise FormalCheckpointError("checkpoint 15 artifact self-hash is invalid") from exc
    if prior.get("schema") != SCHEMA:
        raise FormalCheckpointError("checkpoint 15 artifact schema is invalid")
    checkpoint = prior.get("checkpoint")
    if not isinstance(checkpoint, Mapping) or (
        checkpoint.get("required_measured_sessions") != 15
        or checkpoint.get("observed_measured_sessions") != 15
    ):
        raise FormalCheckpointError("prior artifact is not the formal checkpoint 15")
    if prior.get("label") != FORMAL_LABELS["continue_20"]:
        raise FormalCheckpointError("checkpoint 15 artifact does not arm checkpoint 20")
    claimed_binding = prior.get("checkpoint_binding_sha256")
    if (
        not isinstance(claimed_binding, str)
        or not HEX_64.fullmatch(claimed_binding)
        or claimed_binding != _checkpoint_binding_sha256(prior)
    ):
        raise FormalCheckpointError("checkpoint 15 binding is invalid")
    return prior


def build_formal_checkpoint(
    baseline: Mapping[str, Any],
    raw_snapshots: Sequence[Mapping[str, Any]],
    enumerated_sessions: Sequence[str],
    *,
    checkpoint: int,
    prior_15_artifact: Mapping[str, Any] | None = None,
    generated_at: datetime | None = None,
    enumeration_sha256: str,
) -> dict[str, Any] | None:
    if not HEX_64.fullmatch(enumeration_sha256):
        raise FormalCheckpointError("session enumeration SHA-256 is invalid")
    if checkpoint == 20 and prior_15_artifact is None:
        raise FormalCheckpointError("checkpoint 20 is not armed by checkpoint 15")
    if checkpoint == 15 and prior_15_artifact is not None:
        raise FormalCheckpointError("checkpoint 15 must not receive a prior artifact")

    local_sources = _assert_local_frozen_sources()
    frozen.verify_baseline(baseline)
    snapshots = validate_snapshot_prefix(raw_snapshots, enumerated_sessions)
    prior_artifact_sha256: str | None = None
    if checkpoint == 20:
        assert prior_15_artifact is not None
        prior = _validate_prior_15_artifact(prior_15_artifact)
        recomputed_15 = build_formal_checkpoint(
            baseline,
            raw_snapshots,
            enumerated_sessions,
            checkpoint=15,
            generated_at=generated_at,
            enumeration_sha256=enumeration_sha256,
        )
        if recomputed_15 is None:
            raise FormalCheckpointError("checkpoint 15 cannot be recomputed")
        if recomputed_15["label"] != FORMAL_LABELS["continue_20"]:
            raise FormalCheckpointError(
                "checkpoint 15 recomputation no longer arms checkpoint 20"
            )
        if prior["checkpoint_binding_sha256"] != recomputed_15[
            "checkpoint_binding_sha256"
        ]:
            raise FormalCheckpointError(
                "checkpoint 15 artifact does not match the recomputed exact prefix"
            )
        prior_artifact_sha256 = str(prior["artifact_sha256"])
    selected = select_exact_prefix(baseline, snapshots, checkpoint)
    if selected is None:
        return None
    if not selected["gate"]["passed"]:
        raise FormalCheckpointError("entry consistency gate failed at checkpoint")

    selected_snapshots = selected["snapshots"]
    rows = selected["rows"]
    bounds = _formal_bounds(rows)
    label = _label(
        checkpoint,
        bounds["ucb_98_75"]["central"],
        bounds["lcb_98_75"]["central"],
    )
    barrier = selected["summary"]["barrier"]
    generated = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "label": label,
        "generated_at": generated.isoformat(),
        "checkpoint": {
            "policy_epoch": POLICY_EPOCH,
            "required_measured_sessions": checkpoint,
            "observed_measured_sessions": selected["summary"]["session_count"],
            "source_session_count": len(selected_snapshots),
            "first_source_session": selected_snapshots[0]["session_date"],
            "checkpoint_source_session": selected_snapshots[-1]["session_date"],
            "reference_probability": REFERENCE_PROBABILITY,
            **(
                {"prior_15_artifact_sha256": prior_artifact_sha256}
                if prior_artifact_sha256 is not None
                else {}
            ),
        },
        "population_counts": {
            "entries": selected["summary"]["entry_count"],
            "resolved": barrier["resolved_count"],
            "upper_first": barrier["categories"]["upper_first"],
            "lower_first": barrier["categories"]["lower_first"],
            "ambiguous_same_bar": barrier["categories"]["ambiguous_same_bar"],
            "censored": barrier["categories"]["censored"],
        },
        "formal_bounds": bounds,
        "entry_consistency_gate": selected["gate"],
        "source_evidence": selected["source_evidence"],
        "frozen_contract": {
            "mesa_pre_registration_sha256": MESA_SOURCE_SHA256,
            "factual_baseline_run_id": frozen.BASELINE_RUN_ID,
            "factual_baseline_report_sha256": frozen.BASELINE_REPORT_SHA256,
            "v1_kill_criterion_sha256": V1_KILL_CRITERION_SHA256,
            "entry_quality_spec_sha256": ENTRY_QUALITY_SPEC_SHA256,
            "policy_epochs_file_sha256": POLICY_EPOCHS_FILE_SHA256,
            "policy_epochs_manifest_sha256": POLICY_EPOCHS_MANIFEST_SHA256,
            "session_enumeration_sha256": enumeration_sha256,
            "session_snapshot_sha256": local_sources["session_snapshot.py"],
            "incremental_reducer_sha256": local_sources["incremental_reducer.py"],
            "formal_checkpoint_sha256": local_sources["formal_checkpoint.py"],
            "app_source_sha256": FROZEN_APP_SOURCE_SHA256,
            "bootstrap_seed": frozen.BOOTSTRAP_SEED,
            "bootstrap_iterations": frozen.BOOTSTRAP_ITERATIONS,
            "tail_probability": FORMAL_TAIL_PROBABILITY,
        },
        "governance": {
            "read_only": True,
            "raw_rows_published": False,
            "entry_identifiers_published": False,
            "transient_destruction_implemented": False,
            "cross_epoch_pooling": False,
            "schedule_implemented": False,
            "private_retention_implemented": False,
            "breaker_dml_executed": False,
            "strategy_change_authorized": False,
            "v1_terminal_label_requires_m2_when_m1_not_refuted": True,
        },
    }
    ready = frozen.json_ready(payload)
    ready["checkpoint_binding_sha256"] = _checkpoint_binding_sha256(ready)
    _assert_publication_boundary(ready)
    ready["artifact_sha256"] = frozen.canonical_sha256(ready)
    return ready


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=int, choices=CHECKPOINTS)
    parser.add_argument("--baseline-report", required=True, type=Path)
    parser.add_argument("--enumerated-sessions", required=True, type=Path)
    parser.add_argument("--session-snapshot", required=True, action="append", type=Path)
    parser.add_argument("--prior-15-artifact", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.output.exists():
        raise FormalCheckpointError("refusing to overwrite a formal artifact")
    if len(args.session_snapshot) > MAX_SESSION_SNAPSHOT_FILES:
        raise FormalCheckpointError("too many session snapshot inputs")
    preflight_snapshot_bytes = sum(
        _input_size(path, "session snapshot", MAX_SNAPSHOT_INPUT_BYTES)
        for path in args.session_snapshot
    )
    if preflight_snapshot_bytes > MAX_TOTAL_SNAPSHOT_INPUT_BYTES:
        raise FormalCheckpointError("session snapshots exceed the aggregate byte ceiling")
    sessions = load_enumerated_sessions(args.enumerated_sessions)
    baseline = _bounded_json_object(
        args.baseline_report,
        "factual baseline",
        MAX_BASELINE_INPUT_BYTES,
    )
    snapshots: list[Mapping[str, Any]] = []
    observed_snapshot_bytes = 0
    for path in args.session_snapshot:
        source = _bounded_input(path, "session snapshot", MAX_SNAPSHOT_INPUT_BYTES)
        observed_snapshot_bytes += len(source)
        if observed_snapshot_bytes > MAX_TOTAL_SNAPSHOT_INPUT_BYTES:
            raise FormalCheckpointError(
                "session snapshots exceed the aggregate byte ceiling"
            )
        snapshots.append(_json_object(source, "session snapshot"))
    prior_15_artifact = (
        _bounded_json_object(
            args.prior_15_artifact,
            "checkpoint 15 artifact",
            MAX_PRIOR_ARTIFACT_INPUT_BYTES,
        )
        if args.prior_15_artifact is not None
        else None
    )
    result = build_formal_checkpoint(
        baseline,
        snapshots,
        sessions,
        checkpoint=args.checkpoint,
        prior_15_artifact=prior_15_artifact,
        enumeration_sha256=_file_sha256(args.enumerated_sessions),
    )
    if result is None:
        print(
            frozen.canonical_json(
                {
                    "status": "NOT_READY",
                    "checkpoint": args.checkpoint,
                    "source_session_count": len(snapshots),
                }
            )
        )
        return NOT_READY_EXIT
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.{os.getpid()}.tmp")
    if temporary.exists():
        raise FormalCheckpointError("temporary formal artifact path already exists")
    with temporary.open("x", encoding="utf-8") as handle:
        handle.write(frozen.canonical_json(result) + "\n")
    temporary.chmod(0o600)
    os.replace(temporary, args.output)
    print(result["artifact_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
