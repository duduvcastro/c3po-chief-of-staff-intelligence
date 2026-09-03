#!/usr/bin/env python3
"""Validate private M1 state and build one signed-transfer envelope source.

This helper is deliberately network-neutral.  The workflow owns SSH transport
and detached signing; this program only admits canonical, bounded reduced JSON.
It never reads raw trade rows and never writes to the public repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import c3po_m1_formal_checkpoint as formal
import c3po_m1_incremental_reducer as frozen


INGRESS_SCHEMA = "C3PO_M1_FORMAL_TRANSFER-v1"
STATE_SCHEMA = "C3PO_M1_FORMAL_STATE-v1"
PUBLIC_REPOSITORY = "duduvcastro/c3po-chief-of-staff-intelligence"
PRIVATE_REPOSITORY = "duduvcastro/c3po-r2d2-reports"
STATE_KEYS = {
    "schema",
    "status",
    "checkpoint",
    "artifact_sha256",
    "checkpoint_binding_sha256",
    "expires_at",
}
STATE_STATUSES = {
    "PENDING_15",
    "CONTINUE_TO_20",
    "TERMINAL_15",
    "COMPLETE_20",
    "EXPIRED",
}
INGRESS_KEYS = {
    "schema",
    "source_repository",
    "source_head_sha",
    "source_formal_checkpoint_sha256",
    "source_release_id",
    "source_run_id",
    "source_run_attempt",
    "public_artifact_id",
    "checkpoint",
    "artifact_sha256",
    "checkpoint_binding_sha256",
    "payload_file_sha256",
}
HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
MAX_PAYLOAD_BYTES = 65_536
MAX_STATE_BYTES = 4_096


class OrchestrationError(ValueError):
    """The reduced state or ingress source is outside the audited contract."""


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _regular_bytes(path: Path, field: str, maximum: int) -> bytes:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as exc:
        raise OrchestrationError(f"{field} is missing") from exc
    if not stat.S_ISREG(mode):
        raise OrchestrationError(f"{field} must be a regular file")
    if path.stat().st_size > maximum:
        raise OrchestrationError(f"{field} exceeds its byte ceiling")
    value = path.read_bytes()
    if len(value) > maximum:
        raise OrchestrationError(f"{field} exceeds its byte ceiling")
    return value


def _canonical_object(path: Path, field: str, maximum: int) -> tuple[dict[str, Any], bytes]:
    source = _regular_bytes(path, field, maximum)
    try:
        value = json.loads(source)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OrchestrationError(f"{field} is not valid JSON") from exc
    if not isinstance(value, Mapping):
        raise OrchestrationError(f"{field} must be an object")
    result = dict(value)
    if source != (canonical_json(result) + "\n").encode("utf-8"):
        raise OrchestrationError(f"{field} is not canonical JSON plus LF")
    return result, source


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not HEX_64.fullmatch(value):
        raise OrchestrationError(f"{field} must be a lowercase SHA-256")
    return value


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise OrchestrationError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OrchestrationError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise OrchestrationError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_orchestrated_payload(
    payload: Mapping[str, Any],
    *,
    authorized_formal_source_sha256: str,
) -> dict[str, Any]:
    _sha(authorized_formal_source_sha256, "authorized formal source")
    observed = dict(payload)
    if set(observed) != formal.FORMAL_TOP_LEVEL_FIELDS:
        raise OrchestrationError("formal payload field allowlist mismatch")
    try:
        frozen.verify_self_hash(observed, "artifact_sha256")
    except frozen.ReductionError as exc:
        raise OrchestrationError("formal payload self-hash is invalid") from exc
    if observed.get("schema") != formal.SCHEMA:
        raise OrchestrationError("formal payload schema mismatch")
    checkpoint = observed.get("checkpoint")
    if not isinstance(checkpoint, Mapping):
        raise OrchestrationError("formal checkpoint is not an object")
    required = checkpoint.get("required_measured_sessions")
    if required not in formal.CHECKPOINTS:
        raise OrchestrationError("formal checkpoint is not 15 or 20")
    if checkpoint.get("observed_measured_sessions") != required:
        raise OrchestrationError("formal measured-session clock is not exact")
    labels = {
        15: {formal.FORMAL_LABELS["refuted_15"], formal.FORMAL_LABELS["continue_20"]},
        20: {
            formal.FORMAL_LABELS["refuted_20"],
            formal.FORMAL_LABELS["positive_20"],
            formal.FORMAL_LABELS["inconclusive_20"],
        },
    }
    if observed.get("label") not in labels[int(required)]:
        raise OrchestrationError("formal label is invalid for the checkpoint")
    if required == 20:
        _sha(checkpoint.get("prior_15_artifact_sha256"), "prior checkpoint 15")
    if observed.get("checkpoint_binding_sha256") != formal._checkpoint_binding_sha256(
        observed
    ):
        raise OrchestrationError("formal checkpoint binding is invalid")
    contract = observed.get("frozen_contract")
    if not isinstance(contract, Mapping) or contract.get(
        "formal_checkpoint_sha256"
    ) != authorized_formal_source_sha256:
        raise OrchestrationError("formal source hash differs from the audited pin")
    governance = observed.get("governance")
    if not isinstance(governance, Mapping):
        raise OrchestrationError("formal governance block is absent")
    required_governance = {
        "read_only": True,
        "raw_rows_published": False,
        "entry_identifiers_published": False,
        "transient_destruction_implemented": True,
        "cross_epoch_pooling": False,
        "schedule_implemented": True,
        "private_retention_implemented": True,
        "breaker_dml_executed": False,
        "strategy_change_authorized": False,
        "v1_terminal_label_requires_m2_when_m1_not_refuted": True,
    }
    if dict(governance) != required_governance:
        raise OrchestrationError("formal governance block is not orchestrated and fail-closed")
    formal._assert_publication_boundary(observed)
    return observed


def validate_private_state(
    state_path: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    state, _ = _canonical_object(
        state_path, "private checkpoint state", MAX_STATE_BYTES
    )
    if set(state) != STATE_KEYS or state.get("schema") != STATE_SCHEMA:
        raise OrchestrationError("private state marker schema or fields mismatch")
    status = state.get("status")
    if status not in STATE_STATUSES:
        raise OrchestrationError("private state status is invalid")
    clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if status == "PENDING_15":
        if state != {
            "schema": STATE_SCHEMA,
            "status": "PENDING_15",
            "checkpoint": 15,
            "artifact_sha256": None,
            "checkpoint_binding_sha256": None,
            "expires_at": None,
        }:
            raise OrchestrationError("pending checkpoint state is not empty and exact")
        return {"action": "BUILD_15", "checkpoint": 15}

    checkpoint = state.get("checkpoint")
    if checkpoint not in formal.CHECKPOINTS:
        raise OrchestrationError("private state checkpoint is not 15 or 20")
    artifact_sha256 = _sha(state.get("artifact_sha256"), "private artifact")
    binding_sha256 = _sha(
        state.get("checkpoint_binding_sha256"), "private checkpoint binding"
    )
    expiry = _timestamp(state.get("expires_at"), "private state expiry")
    if status == "EXPIRED":
        if expiry > clock:
            raise OrchestrationError("private state is marked expired before its deadline")
        raise OrchestrationError("private formal checkpoint state is expired")
    if expiry <= clock:
        raise OrchestrationError("private formal checkpoint state passed expiry without tombstone")
    if status == "CONTINUE_TO_20":
        if checkpoint != 15:
            raise OrchestrationError("continue marker does not reference checkpoint 15")
        return {
            "action": "BUILD_20",
            "checkpoint": 20,
            "prior_15_artifact_sha256": artifact_sha256,
            "prior_15_checkpoint_binding_sha256": binding_sha256,
            "expires_at": state["expires_at"],
        }
    if status == "TERMINAL_15" and checkpoint != 15:
        raise OrchestrationError("terminal-15 marker references another checkpoint")
    if status == "COMPLETE_20" and checkpoint != 20:
        raise OrchestrationError("complete-20 marker references another checkpoint")
    return {
        "action": "NO_WORK",
        "checkpoint": checkpoint,
        "status": status,
        "artifact_sha256": artifact_sha256,
        "checkpoint_binding_sha256": binding_sha256,
        "expires_at": state["expires_at"],
    }


def validate_recomputed_prior(
    payload_path: Path,
    state_path: Path,
    *,
    authorized_formal_source_sha256: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    state = validate_private_state(state_path, now=now)
    if state.get("action") != "BUILD_20":
        raise OrchestrationError("private state does not authorize checkpoint 20")
    payload, _ = _canonical_object(
        payload_path, "recomputed checkpoint 15", MAX_PAYLOAD_BYTES
    )
    payload = _validate_orchestrated_payload(
        payload,
        authorized_formal_source_sha256=authorized_formal_source_sha256,
    )
    if (
        payload["checkpoint"].get("required_measured_sessions") != 15
        or payload.get("label") != formal.FORMAL_LABELS["continue_20"]
    ):
        raise OrchestrationError("recomputed checkpoint 15 does not arm checkpoint 20")
    if payload.get("checkpoint_binding_sha256") != state.get(
        "prior_15_checkpoint_binding_sha256"
    ):
        raise OrchestrationError("recomputed checkpoint 15 differs from the private binding")
    return {
        "canonical_prior_15_artifact_sha256": state[
            "prior_15_artifact_sha256"
        ],
        "recomputed_prior_15_artifact_sha256": payload["artifact_sha256"],
        "checkpoint_binding_sha256": payload["checkpoint_binding_sha256"],
    }


def checkpoint_progress(
    baseline_path: Path,
    enumeration_path: Path,
    snapshot_paths: Sequence[Path],
    *,
    checkpoint: int,
) -> dict[str, Any]:
    """Admit only the source prefix needed to reach one measured checkpoint.

    A source session can contain no admissible measurement, so truncating the
    enumeration to 15 or 20 lines is not equivalent to the formal clock.  The
    workflow calls this after every read and stops as soon as
    ``select_exact_prefix`` reaches the requested measured-session checkpoint.
    """

    if checkpoint not in formal.CHECKPOINTS:
        raise OrchestrationError("formal checkpoint must be 15 or 20")
    if not snapshot_paths:
        return {
            "status": "NOT_READY",
            "checkpoint": checkpoint,
            "measured_session_count": 0,
            "source_session_count": 0,
        }
    if len(snapshot_paths) > formal.MAX_SESSION_SNAPSHOT_FILES:
        raise OrchestrationError("too many session snapshots")
    try:
        formal._assert_local_frozen_sources()
        baseline = formal._bounded_json_object(
            baseline_path,
            "baseline report",
            formal.MAX_BASELINE_INPUT_BYTES,
        )
        frozen.verify_baseline(baseline)
        enumerated_sessions = formal.load_enumerated_sessions(enumeration_path)
        raw_snapshots: list[Mapping[str, Any]] = []
        total_size = 0
        for index, path in enumerate(snapshot_paths, start=1):
            total_size += formal._input_size(
                path,
                f"session snapshot {index}",
                formal.MAX_SNAPSHOT_INPUT_BYTES,
            )
            if total_size > formal.MAX_TOTAL_SNAPSHOT_INPUT_BYTES:
                raise formal.FormalCheckpointError(
                    "session snapshots exceed the aggregate byte ceiling"
                )
            raw_snapshots.append(
                formal._bounded_json_object(
                    path,
                    f"session snapshot {index}",
                    formal.MAX_SNAPSHOT_INPUT_BYTES,
                )
            )
        snapshots = formal.validate_snapshot_prefix(
            raw_snapshots,
            enumerated_sessions,
        )
        selected = formal.select_exact_prefix(baseline, snapshots, checkpoint)
        if selected is not None:
            if len(selected["snapshots"]) != len(snapshots):
                raise OrchestrationError(
                    "session snapshots extend beyond the exact checkpoint prefix"
                )
            return {
                "status": "READY",
                "checkpoint": checkpoint,
                "measured_session_count": int(
                    selected["summary"]["session_count"]
                ),
                "source_session_count": len(snapshots),
            }
        reduced = formal._reduce_prefix(
            baseline,
            snapshots,
            include_summary=False,
        )
    except (formal.FormalCheckpointError, frozen.ReductionError) as exc:
        raise OrchestrationError(str(exc)) from exc
    return {
        "status": "NOT_READY",
        "checkpoint": checkpoint,
        "measured_session_count": int(reduced["measured_session_count"]),
        "source_session_count": len(snapshots),
    }


def build_ingress_envelope(
    payload_path: Path,
    *,
    checkpoint: int,
    source_head_sha: str,
    authorized_formal_source_sha256: str,
    formal_source_path: Path,
    source_release_id: int,
    source_run_id: int,
    source_run_attempt: int,
    public_artifact_id: int,
    output: Path,
) -> dict[str, Any]:
    if not HEX_40.fullmatch(source_head_sha):
        raise OrchestrationError("authorized public head must be a lowercase Git SHA")
    actual_formal_sha256 = file_sha256(formal_source_path)
    if actual_formal_sha256 != authorized_formal_source_sha256:
        raise OrchestrationError("checked-out formal source differs from the audited pin")
    identifiers = {
        "source_release_id": source_release_id,
        "source_run_id": source_run_id,
        "source_run_attempt": source_run_attempt,
        "public_artifact_id": public_artifact_id,
    }
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in identifiers.values()
    ):
        raise OrchestrationError("transfer identifiers must be positive integers")
    payload, source = _canonical_object(
        payload_path, "formal checkpoint payload", MAX_PAYLOAD_BYTES
    )
    payload = _validate_orchestrated_payload(
        payload,
        authorized_formal_source_sha256=authorized_formal_source_sha256,
    )
    if payload["checkpoint"].get("required_measured_sessions") != checkpoint:
        raise OrchestrationError("payload checkpoint differs from requested ingress")
    envelope = {
        "schema": INGRESS_SCHEMA,
        "source_repository": PUBLIC_REPOSITORY,
        "source_head_sha": source_head_sha,
        "source_formal_checkpoint_sha256": authorized_formal_source_sha256,
        **identifiers,
        "checkpoint": checkpoint,
        "artifact_sha256": payload["artifact_sha256"],
        "checkpoint_binding_sha256": payload["checkpoint_binding_sha256"],
        "payload_file_sha256": hashlib.sha256(source).hexdigest(),
    }
    if set(envelope) != INGRESS_KEYS:
        raise AssertionError("ingress envelope fields drifted")
    if output.exists():
        raise OrchestrationError("refusing to overwrite ingress envelope")
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    with temporary.open("x", encoding="utf-8") as handle:
        handle.write(canonical_json(envelope) + "\n")
    temporary.chmod(0o600)
    os.replace(temporary, output)
    return envelope


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    state = commands.add_parser("validate-state")
    state.add_argument("--state", required=True, type=Path)
    state.add_argument("--now")
    prior = commands.add_parser("validate-recomputed-prior")
    prior.add_argument("--payload", required=True, type=Path)
    prior.add_argument("--state", required=True, type=Path)
    prior.add_argument("--authorized-formal-source-sha256", required=True)
    prior.add_argument("--now")
    progress = commands.add_parser("checkpoint-progress")
    progress.add_argument("--baseline-report", required=True, type=Path)
    progress.add_argument("--enumerated-sessions", required=True, type=Path)
    progress.add_argument(
        "--session-snapshot",
        required=True,
        action="append",
        type=Path,
    )
    progress.add_argument(
        "--checkpoint",
        required=True,
        type=int,
        choices=formal.CHECKPOINTS,
    )
    envelope = commands.add_parser("build-envelope")
    envelope.add_argument("--payload", required=True, type=Path)
    envelope.add_argument(
        "--checkpoint",
        required=True,
        type=int,
        choices=formal.CHECKPOINTS,
    )
    envelope.add_argument("--source-head-sha", required=True)
    envelope.add_argument("--authorized-formal-source-sha256", required=True)
    envelope.add_argument("--formal-source", required=True, type=Path)
    envelope.add_argument("--source-release-id", required=True, type=int)
    envelope.add_argument("--source-run-id", required=True, type=int)
    envelope.add_argument("--source-run-attempt", required=True, type=int)
    envelope.add_argument("--public-artifact-id", required=True, type=int)
    envelope.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "validate-state":
        now = _timestamp(args.now, "fixed clock") if args.now else None
        result = validate_private_state(
            args.state,
            now=now,
        )
    elif args.command == "validate-recomputed-prior":
        now = _timestamp(args.now, "fixed clock") if args.now else None
        result = validate_recomputed_prior(
            args.payload,
            args.state,
            authorized_formal_source_sha256=args.authorized_formal_source_sha256,
            now=now,
        )
    elif args.command == "checkpoint-progress":
        result = checkpoint_progress(
            args.baseline_report,
            args.enumerated_sessions,
            args.session_snapshot,
            checkpoint=args.checkpoint,
        )
    else:
        result = build_ingress_envelope(
            args.payload,
            checkpoint=args.checkpoint,
            source_head_sha=args.source_head_sha,
            authorized_formal_source_sha256=args.authorized_formal_source_sha256,
            formal_source_path=args.formal_source,
            source_release_id=args.source_release_id,
            source_run_id=args.source_run_id,
            source_run_attempt=args.source_run_attempt,
            public_artifact_id=args.public_artifact_id,
            output=args.output,
        )
    print(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
