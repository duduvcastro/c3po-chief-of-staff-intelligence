from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Sequence

from .synthetic import run_synthetic_truth_gate


def _aware_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("measured-at must include a timezone")
    return parsed


def _write_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the Day D same-commit synthetic-truth artifact."
    )
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--measured-at", required=True, type=_aware_timestamp)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args(argv)

    report = run_synthetic_truth_gate(
        git_commit=arguments.git_commit,
        measured_at=arguments.measured_at,
    )
    payload = asdict(report)
    payload["measured_at"] = report.measured_at.isoformat()
    _write_atomic(arguments.output, payload)
    return 0 if report.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
