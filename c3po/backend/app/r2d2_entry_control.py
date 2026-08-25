from __future__ import annotations

import argparse
import json
from typing import Sequence

from .config import Settings
from .database import Database
from .r2d2 import R2D2Repository
from .r2d2_entry_score_adapter import ADAPTER_VERSION


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan or apply the R2D2 new-entry circuit breaker.",
    )
    state = parser.add_mutually_exclusive_group(required=True)
    state.add_argument("--pause", action="store_true", help="Block all new paper entries.")
    state.add_argument("--resume", action="store_true", help="Permit new paper entries again.")
    parser.add_argument("--operator", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument(
        "--policy-epoch",
        help="Required for resume; immutable label for the policy epoch beginning now.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply the planned state change. Without this flag the command is read-only.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.resume and not (args.policy_epoch or "").strip():
        raise SystemExit("--policy-epoch is required with --resume")
    if args.pause and args.policy_epoch:
        raise SystemExit("--policy-epoch may only be used with --resume")
    settings = Settings()
    repository = R2D2Repository(Database(settings))
    current = repository.experiment(settings.r2d2_experiment_code)
    if current is None:
        raise SystemExit(f"R2D2 experiment not found: {settings.r2d2_experiment_code}")
    requested = bool(args.pause)
    requested_epoch = (args.policy_epoch or "").strip() or None
    blocked_reasons: list[str] = []
    if args.resume and not settings.r2d2_entry_score_adapter_enabled:
        blocked_reasons.append("C3PO_R2D2_ENTRY_SCORE_ADAPTER_ENABLED must be true")
    if args.resume and not bool(current.get("entries_paused")):
        if (
            current.get("policy_epoch") != requested_epoch
            or current.get("entry_score_adapter_version") != ADAPTER_VERSION
        ):
            blocked_reasons.append("entries are already active under a different or missing policy epoch")
    output = {
        "mode": "execute" if args.execute else "plan",
        "experiment_code": settings.r2d2_experiment_code,
        "current_entries_paused": bool(current.get("entries_paused")),
        "requested_entries_paused": requested,
        "state_change_required": bool(current.get("entries_paused")) != requested,
        "operator": args.operator.strip(),
        "reason": args.reason.strip(),
        "current_policy_epoch": current.get("policy_epoch"),
        "requested_policy_epoch": requested_epoch,
        "methodology_version": current.get("methodology_version"),
        "entry_score_adapter": {
            "configured": bool(settings.r2d2_entry_score_adapter_enabled),
            "version": ADAPTER_VERSION,
            "default_enabled": False,
            "external_api_calls": 0,
            "decision_influence": False,
        },
        "resume_ready": not blocked_reasons,
        "blocked_reasons": blocked_reasons,
    }
    if args.execute and blocked_reasons:
        print(json.dumps(output, sort_keys=True))
        return 2
    if args.execute:
        changed = repository.set_entries_paused(
            settings.r2d2_experiment_code,
            paused=requested,
            operator=args.operator,
            reason=args.reason,
            policy_epoch=requested_epoch,
            entry_score_adapter_version=ADAPTER_VERSION if args.resume else None,
        )
        output.update({
            "entries_paused": bool(changed["entries_paused"]),
            "entries_paused_at": (
                changed["entries_paused_at"].isoformat()
                if changed.get("entries_paused_at") else None
            ),
            "policy_epoch": changed.get("policy_epoch"),
            "policy_epoch_started_at": (
                changed["policy_epoch_started_at"].isoformat()
                if changed.get("policy_epoch_started_at") else None
            ),
            "entry_score_adapter_version": changed.get("entry_score_adapter_version"),
        })
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
