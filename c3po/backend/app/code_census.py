from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .config import Settings
from .database import Database
from .observability import HealthcheckPing


logger = logging.getLogger("c3po.code_census")

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
CENSUS_METHODOLOGY = "raw-line-count-frozen-globs-v1"
CENSUS_EARLIEST_LOCAL_HOUR = 2

# The census walks the deployed repository checkout mounted read-only into the
# server-usage worker. Layer membership is frozen here so the daily series stays
# comparable; changing any glob is a methodology bump, never a silent edit.
EXCLUDED_DIR_NAMES = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".next",
    "dist",
    "build",
    ".pytest_cache",
    ".ruff_cache",
    "outputs",
    "generated-one-pagers",
    "generated-investor-relations",
}

LAYER_ORDER = (
    "backend_app",
    "tests",
    "other_python",
    "frontend",
    "ops",
    "sql",
)

FRONTEND_SUFFIXES = {".ts", ".tsx", ".js", ".mjs", ".css"}
OPS_SUFFIXES = {".yml", ".yaml", ".sh", ".service", ".timer"}


def _classify(relative: Path) -> str | None:
    parts = relative.parts
    suffix = relative.suffix.lower()
    if suffix == ".md":
        return "docs_markdown"
    if suffix == ".py":
        if parts[:3] == ("c3po", "backend", "app"):
            return "backend_app"
        if parts[:3] == ("c3po", "backend", "tests"):
            return "tests"
        return "other_python"
    if parts[:2] == ("c3po", "frontend") and suffix in FRONTEND_SUFFIXES:
        return "frontend"
    if suffix == ".sql" and parts[:2] == ("c3po", "db"):
        return "sql"
    if (
        parts[:2] == (".github", "workflows")
        or parts[:1] == ("ops",)
        or suffix in {".sh", ".service", ".timer"}
        or relative.name == "Dockerfile"
        or relative.name == "compose.yml"
    ) and (suffix in OPS_SUFFIXES or relative.name in {"Dockerfile", "compose.yml"}):
        return "ops"
    return None


def _count_lines(path: Path) -> int | None:
    """Line count for a text file; None means binary-by-design, never an error."""
    data = path.read_bytes()
    if b"\x00" in data[:1024]:
        return None
    if not data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def measure_repository(root: Path) -> dict[str, Any] | None:
    """Count lines per frozen layer. Returns None when root is not a repo checkout."""
    if not (root / "c3po" / "backend" / "app").is_dir():
        return None
    layers: dict[str, dict[str, int]] = {
        name: {"lines": 0, "files": 0} for name in (*LAYER_ORDER, "docs_markdown")
    }
    unreadable_files = 0
    unreadable_directories = 0
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = sorted(directory.iterdir())
        except OSError:
            unreadable_directories += 1
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name not in EXCLUDED_DIR_NAMES:
                    stack.append(entry)
                continue
            layer = _classify(entry.relative_to(root))
            if layer is None:
                continue
            try:
                lines = _count_lines(entry)
            except OSError:
                unreadable_files += 1
                continue
            if lines is None:
                continue
            layers[layer]["lines"] += lines
            layers[layer]["files"] += 1
    docs = layers.pop("docs_markdown")
    return {
        "methodology": CENSUS_METHODOLOGY,
        "layers": layers,
        "total_lines": sum(item["lines"] for item in layers.values()),
        "total_files": sum(item["files"] for item in layers.values()),
        "docs_lines": docs["lines"],
        "docs_files": docs["files"],
        "unreadable_files": unreadable_files,
        "unreadable_directories": unreadable_directories,
    }


class CodeCensusService:
    def __init__(self, settings: Settings, database: Database) -> None:
        self.settings = settings
        self.database = database
        self._last_attempted_session: date | None = None
        self.healthcheck = HealthcheckPing(settings.healthcheck_code_census_url)

    def run_daily_if_due(self, root: Path, now: datetime | None = None) -> bool:
        """Idempotent daily census at/after 02:00 America/Sao_Paulo."""
        local = (now or datetime.now(timezone.utc)).astimezone(SAO_PAULO)
        if local.hour < CENSUS_EARLIEST_LOCAL_HOUR:
            return False
        session = local.date()
        if self._last_attempted_session == session:
            return False
        self._last_attempted_session = session
        self.healthcheck.ping("start")
        try:
            measurement = measure_repository(root)
        except Exception:
            self.healthcheck.ping("fail")
            raise
        if measurement is None:
            logger.warning("Code census skipped: %s is not a repository checkout", root)
            self.healthcheck.ping("fail")
            return False
        if measurement["unreadable_files"] or measurement["unreadable_directories"]:
            # A partial walk must never be recorded as a complete census.
            logger.warning(
                "Code census refused: %s unreadable file(s) and %s unreadable directory(ies) under %s",
                measurement["unreadable_files"],
                measurement["unreadable_directories"],
                root,
            )
            self.healthcheck.ping("fail")
            return False
        try:
            with self.database.connection() as connection:
                inserted = connection.execute(
                    """INSERT INTO code_census_daily
                       (session_date, methodology, layers, total_lines, total_files,
                        docs_lines, docs_files, generated_at)
                       VALUES (%s,%s,%s::jsonb,%s,%s,%s,%s,%s)
                       ON CONFLICT (session_date) DO NOTHING""",
                    (
                        session,
                        measurement["methodology"],
                        json.dumps(measurement["layers"]),
                        measurement["total_lines"],
                        measurement["total_files"],
                        measurement["docs_lines"],
                        measurement["docs_files"],
                        datetime.now(timezone.utc),
                    ),
                ).rowcount
                connection.commit()
        except Exception:
            self.healthcheck.ping("fail")
            raise
        if inserted:
            logger.info(
                "Code census %s: %s lines / %s files (+%s doc lines)",
                session,
                measurement["total_lines"],
                measurement["total_files"],
                measurement["docs_lines"],
            )
        self.healthcheck.ping("success")
        return bool(inserted)

    def snapshot(self, days: int | None = None) -> dict[str, Any]:
        query = """SELECT session_date, methodology, layers, total_lines, total_files,
                          docs_lines, docs_files, generated_at
                   FROM code_census_daily
                   ORDER BY session_date DESC"""
        params: tuple[int, ...] = ()
        if days is not None:
            query += " LIMIT %s"
            params = (max(2, days),)
        with self.database.connection() as connection:
            rows = connection.execute(query, params).fetchall()
        series = [
            {
                "session_date": row[0].isoformat(),
                "methodology": row[1],
                "layers": row[2],
                "total_lines": row[3],
                "total_files": row[4],
                "docs_lines": row[5],
                "docs_files": row[6],
                "generated_at": row[7].isoformat(),
            }
            for row in rows
        ]
        latest = series[0] if series else None
        previous = series[1] if len(series) > 1 else None
        # A methodology change resets the comparison baseline: deltas across
        # different rulers would fabricate growth or shrinkage.
        delta_comparable = bool(
            latest and previous and latest["methodology"] == previous["methodology"]
        )
        return {
            "latest": latest,
            "previous": previous,
            "delta_comparable": delta_comparable,
            "total_delta_vs_previous": (
                latest["total_lines"] - previous["total_lines"]
                if delta_comparable else None
            ),
            "layer_order": list(LAYER_ORDER),
            "series": list(reversed(series)),
        }
