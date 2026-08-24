from __future__ import annotations

import argparse
import json
from typing import Sequence

from .config import Settings
from .database import Database
from .r2d2 import R2D2Repository


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
        "--execute",
        action="store_true",
        help="Apply the planned state change. Without this flag the command is read-only.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = Settings()
    repository = R2D2Repository(Database(settings))
    current = repository.experiment(settings.r2d2_experiment_code)
    if current is None:
        raise SystemExit(f"R2D2 experiment not found: {settings.r2d2_experiment_code}")
    requested = bool(args.pause)
    output = {
        "mode": "execute" if args.execute else "plan",
        "experiment_code": settings.r2d2_experiment_code,
        "current_entries_paused": bool(current.get("entries_paused")),
        "requested_entries_paused": requested,
        "state_change_required": bool(current.get("entries_paused")) != requested,
        "operator": args.operator.strip(),
        "reason": args.reason.strip(),
    }
    if args.execute:
        changed = repository.set_entries_paused(
            settings.r2d2_experiment_code,
            paused=requested,
            operator=args.operator,
            reason=args.reason,
        )
        output.update({
            "entries_paused": bool(changed["entries_paused"]),
            "entries_paused_at": (
                changed["entries_paused_at"].isoformat()
                if changed.get("entries_paused_at") else None
            ),
        })
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
