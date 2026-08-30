from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import code_census as code_census_module
from app.code_census import (
    CENSUS_METHODOLOGY,
    CodeCensusService,
    measure_repository,
)
from app.config import Settings


def _write(root: Path, relative: str, lines: int) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x\n" * lines, encoding="utf-8")


def _repo(tmp_path: Path) -> Path:
    _write(tmp_path, "c3po/backend/app/r2d2.py", 100)
    _write(tmp_path, "c3po/backend/app/code_census.py", 20)
    _write(tmp_path, "c3po/backend/tests/test_r2d2.py", 40)
    _write(tmp_path, "work/morning_summary.py", 30)
    _write(tmp_path, "c3po/frontend/app/page.tsx", 50)
    _write(tmp_path, "c3po/frontend/app/globals.css", 10)
    _write(tmp_path, "c3po/db/031_code_census.sql", 5)
    _write(tmp_path, ".github/workflows/pipeline.yml", 8)
    _write(tmp_path, "scripts/rerun.sh", 4)
    _write(tmp_path, "c3po/docs/SPEC.md", 25)
    # noise that must never count
    _write(tmp_path, "c3po/frontend/node_modules/x/index.js", 9_999)
    _write(tmp_path, "c3po/backend/.venv/lib/junk.py", 9_999)
    _write(tmp_path, "outputs/evidence/run.log", 123)
    return tmp_path


def test_measure_repository_counts_frozen_layers_and_excludes_vendored_trees(
    tmp_path: Path,
) -> None:
    measurement = measure_repository(_repo(tmp_path))

    assert measurement is not None
    assert measurement["methodology"] == CENSUS_METHODOLOGY
    assert measurement["layers"] == {
        "backend_app": {"lines": 120, "files": 2},
        "tests": {"lines": 40, "files": 1},
        "other_python": {"lines": 30, "files": 1},
        "frontend": {"lines": 60, "files": 2},
        "ops": {"lines": 12, "files": 2},
        "sql": {"lines": 5, "files": 1},
    }
    assert measurement["total_lines"] == 267
    assert measurement["total_files"] == 9
    assert measurement["docs_lines"] == 25
    assert measurement["docs_files"] == 1


def test_measure_repository_refuses_a_directory_that_is_not_the_checkout(
    tmp_path: Path,
) -> None:
    assert measure_repository(tmp_path) is None


class _FakeConnection:
    def __init__(self, log: list[tuple[str, tuple]]) -> None:
        self._log = log

    def execute(self, sql: str, params: tuple = ()) -> SimpleNamespace:
        self._log.append((sql, params))
        return SimpleNamespace(rowcount=1, fetchall=lambda: [])

    def commit(self) -> None:
        pass


class _FakeDatabase:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []

    @contextmanager
    def connection(self):
        yield _FakeConnection(self.executed)


def test_daily_census_waits_for_two_am_brt_and_runs_once_per_session(
    tmp_path: Path,
) -> None:
    settings = Settings(database_url="", auth_cookie_secure=False)
    database = _FakeDatabase()
    service = CodeCensusService(settings, database)  # type: ignore[arg-type]
    ping_statuses: list[str] = []
    service.healthcheck.ping = lambda status="success": ping_statuses.append(status) or True  # type: ignore[method-assign]
    root = _repo(tmp_path)

    before_window = datetime(2026, 8, 27, 4, 30, tzinfo=timezone.utc)  # 01:30 BRT
    assert service.run_daily_if_due(root, now=before_window) is False
    assert database.executed == []

    in_window = datetime(2026, 8, 27, 5, 1, tzinfo=timezone.utc)  # 02:01 BRT
    assert service.run_daily_if_due(root, now=in_window) is True
    assert ping_statuses == ["start", "success"]
    assert len(database.executed) == 1
    sql, params = database.executed[0]
    assert "INSERT INTO code_census_daily" in sql
    assert "ON CONFLICT (session_date) DO NOTHING" in sql
    assert params[0].isoformat() == "2026-08-27"
    assert params[3] == 267

    later_same_session = datetime(2026, 8, 27, 9, 0, tzinfo=timezone.utc)
    assert service.run_daily_if_due(root, now=later_same_session) is False
    assert len(database.executed) == 1


def test_census_refuses_to_record_a_partial_walk_as_complete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repo(tmp_path)
    real_count = code_census_module._count_lines

    def failing_count(path: Path) -> int | None:
        if path.name == "r2d2.py":
            raise OSError("simulated unreadable file")
        return real_count(path)

    monkeypatch.setattr(code_census_module, "_count_lines", failing_count)

    measurement = measure_repository(root)
    assert measurement is not None
    assert measurement["unreadable_files"] == 1

    database = _FakeDatabase()
    service = CodeCensusService(
        Settings(database_url="", auth_cookie_secure=False),
        database,  # type: ignore[arg-type]
    )
    ping_statuses: list[str] = []
    service.healthcheck.ping = lambda status="success": ping_statuses.append(status) or True  # type: ignore[method-assign]
    in_window = datetime(2026, 8, 27, 5, 1, tzinfo=timezone.utc)
    assert service.run_daily_if_due(root, now=in_window) is False
    assert database.executed == []
    assert ping_statuses == ["start", "fail"]


class _SeriesDatabase:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows
        self.executed: list[tuple[str, tuple]] = []

    @contextmanager
    def connection(self):
        rows = self._rows

        def execute(sql: str, params: tuple = ()) -> SimpleNamespace:
            self.executed.append((sql, params))
            return SimpleNamespace(rowcount=0, fetchall=lambda: rows)

        yield SimpleNamespace(
            execute=execute,
            commit=lambda: None,
        )


def _series_row(session: str, methodology: str, total: int) -> tuple:
    generated = datetime(2026, 8, 27, 5, 0, tzinfo=timezone.utc)
    return (
        datetime.fromisoformat(session).date(),
        methodology,
        {"backend_app": {"lines": total, "files": 1}},
        total,
        1,
        0,
        0,
        generated,
    )


def test_snapshot_never_compares_totals_across_methodology_changes() -> None:
    settings = Settings(database_url="", auth_cookie_secure=False)

    changed = CodeCensusService(
        settings,
        _SeriesDatabase([  # type: ignore[arg-type]
            _series_row("2026-08-28", "raw-line-count-frozen-globs-v2", 110_000),
            _series_row("2026-08-27", CENSUS_METHODOLOGY, 107_033),
        ]),
    ).snapshot()
    assert changed["delta_comparable"] is False
    assert changed["total_delta_vs_previous"] is None

    stable = CodeCensusService(
        settings,
        _SeriesDatabase([  # type: ignore[arg-type]
            _series_row("2026-08-28", CENSUS_METHODOLOGY, 107_500),
            _series_row("2026-08-27", CENSUS_METHODOLOGY, 107_033),
        ]),
    ).snapshot()
    assert stable["delta_comparable"] is True
    assert stable["total_delta_vs_previous"] == 467


def test_snapshot_compound_growth_since_the_measurement_start() -> None:
    settings = Settings(database_url="", auth_cookie_secure=False)

    snapshot = CodeCensusService(
        settings,
        _SeriesDatabase([  # type: ignore[arg-type]
            _series_row("2026-08-30", CENSUS_METHODOLOGY, 121_927),
            _series_row("2026-08-28", CENSUS_METHODOLOGY, 110_000),
            _series_row("2026-08-26", CENSUS_METHODOLOGY, 100_000),
        ]),
    ).snapshot()

    growth = snapshot["compound_growth"]
    assert growth is not None
    assert growth["baseline_date"] == "2026-08-26"
    assert growth["days"] == 4
    assert abs(growth["total_growth_pct"] - 21.927) < 0.0005
    assert abs(growth["daily_compound_pct"] - 5.0812) < 0.001
    # Annualizing four days is mathematically defined but numerically wild;
    # the payload still reports it and display rules live in the frontend.
    assert 1e9 < growth["cagr_annualized_pct"] < 1e10


def test_snapshot_compound_growth_restarts_at_a_methodology_change() -> None:
    settings = Settings(database_url="", auth_cookie_secure=False)

    snapshot = CodeCensusService(
        settings,
        _SeriesDatabase([  # type: ignore[arg-type]
            _series_row("2026-08-30", CENSUS_METHODOLOGY, 121_927),
            _series_row("2026-08-29", CENSUS_METHODOLOGY, 110_000),
            _series_row("2026-08-28", "raw-line-count-frozen-globs-v0", 108_000),
        ]),
    ).snapshot()

    growth = snapshot["compound_growth"]
    assert growth is not None
    assert growth["baseline_date"] == "2026-08-29"
    assert growth["days"] == 1
    assert abs(growth["total_growth_pct"] - 10.8427) < 0.001
    assert growth["daily_compound_pct"] == growth["total_growth_pct"]


def test_snapshot_compound_growth_needs_a_window_and_a_nonzero_baseline() -> None:
    settings = Settings(database_url="", auth_cookie_secure=False)

    single = CodeCensusService(
        settings,
        _SeriesDatabase([  # type: ignore[arg-type]
            _series_row("2026-08-30", CENSUS_METHODOLOGY, 121_927),
        ]),
    ).snapshot()
    assert single["compound_growth"] is None

    all_changed = CodeCensusService(
        settings,
        _SeriesDatabase([  # type: ignore[arg-type]
            _series_row("2026-08-30", CENSUS_METHODOLOGY, 121_927),
            _series_row("2026-08-29", "raw-line-count-frozen-globs-v0", 110_000),
        ]),
    ).snapshot()
    assert all_changed["compound_growth"] is None

    zero_baseline = CodeCensusService(
        settings,
        _SeriesDatabase([  # type: ignore[arg-type]
            _series_row("2026-08-30", CENSUS_METHODOLOGY, 121_927),
            _series_row("2026-08-29", CENSUS_METHODOLOGY, 0),
        ]),
    ).snapshot()
    assert zero_baseline["compound_growth"] is None


def test_snapshot_returns_complete_history_in_chronological_order_by_default() -> None:
    database = _SeriesDatabase(
        [
            _series_row("2026-08-28", CENSUS_METHODOLOGY, 107_500),
            _series_row("2026-08-27", CENSUS_METHODOLOGY, 107_033),
            _series_row("2026-08-26", CENSUS_METHODOLOGY, 106_500),
        ]
    )
    service = CodeCensusService(
        Settings(database_url="", auth_cookie_secure=False),
        database,  # type: ignore[arg-type]
    )

    snapshot = service.snapshot()

    assert [row["session_date"] for row in snapshot["series"]] == [
        "2026-08-26",
        "2026-08-27",
        "2026-08-28",
    ]
    sql, params = database.executed[0]
    assert "LIMIT" not in sql
    assert params == ()
