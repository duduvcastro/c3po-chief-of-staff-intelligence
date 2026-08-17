#!/usr/bin/env python3
"""Reject sensitive, generated or unexpectedly large Git-tracked files."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MAX_FILE_BYTES = 20 * 1024 * 1024

FORBIDDEN_PARTS = {
    ".next",
    ".pnpm-store",
    ".venv",
    "__pycache__",
    "billfish_reports",
    "node_modules",
    "output",
    "outputs",
    "tmp",
    "whatsapp_session",
}

FORBIDDEN_SUFFIXES = {
    ".db",
    ".jks",
    ".key",
    ".keystore",
    ".mobileprovision",
    ".p12",
    ".pem",
    ".pfx",
    ".sqlite",
    ".sqlite3",
}

SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "GitHub token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
}


def tracked_files() -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=ROOT, text=False
    )
    return [ROOT / item.decode("utf-8") for item in output.split(b"\0") if item]


def is_forbidden_path(path: Path) -> str | None:
    relative = path.relative_to(ROOT)
    parts = set(relative.parts)
    name = relative.name

    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return "environment file"
    if path.suffix.lower() in FORBIDDEN_SUFFIXES:
        return f"credential/database extension {path.suffix}"
    if parts & FORBIDDEN_PARTS:
        return f"private/generated directory {sorted(parts & FORBIDDEN_PARTS)[0]}"
    if relative.parts[:2] == ("c3po", "data"):
        return "private C3PO data"
    if name.startswith("whatsapp_unread_") and path.suffix == ".json":
        return "private WhatsApp export"
    return None


def scan_text(path: Path) -> list[str]:
    if path.stat().st_size > 2 * 1024 * 1024:
        return []
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    return [label for label, pattern in SECRET_PATTERNS.items() if pattern.search(content)]


def main() -> int:
    findings: list[str] = []
    for path in tracked_files():
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        forbidden_reason = is_forbidden_path(path)
        if forbidden_reason:
            findings.append(f"{relative}: {forbidden_reason}")
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            findings.append(
                f"{relative}: file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB"
            )
        for secret_type in scan_text(path):
            findings.append(f"{relative}: possible {secret_type}")

    if findings:
        print("Sensitive-file check failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1

    print("Sensitive-file check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

