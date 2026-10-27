"""The host driver of the ensemble grade: pinned files, the journal that makes an interrupted chunk lose nothing, the
operational guard and the aggregates-only output. Synthetic: the executor's own fixture (a double of the section), no
connection, no real input, no label."""
from __future__ import annotations

import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app import valuation_ensemble_driver as driver
from tests.test_valuation_ensemble_executor import NOW, fixture


def _legacy(tmp_path: Path, context: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str, str]:
    legacy = tmp_path / "legacy"
    (legacy / driver.ORDERS).mkdir(parents=True)
    (legacy / driver.PINS).mkdir(parents=True)
    order = json.dumps(context["order"], sort_keys=True).encode()
    order_sha = __import__("hashlib").sha256(order).hexdigest()
    (legacy / driver.ORDERS / f"{order_sha}.json").write_bytes(order)
    pin_sha = context["binding"].expected_pin_sha256
    (legacy / driver.PINS / f"{pin_sha}.json").write_text(json.dumps(context["pin"]), encoding="utf-8")
    monkeypatch.setattr(driver, "instrument_file_hashes", lambda root: dict(context["files"]))
    return legacy, order_sha, pin_sha


def _run(context: dict[str, Any], tmp_path: Path, legacy: Path, order_sha: str, pin_sha: str, max_runs: int) -> dict[str, Any]:
    return driver.run_chunk(context["database"], None, rev3=context["rev3"], order_sha256=order_sha, pin_sha256=pin_sha,
                            binding=context["binding"], max_runs=max_runs, stop_before=NOW + timedelta(minutes=30), legacy_root=legacy,
                            store_root=tmp_path / "store", clock=context["clock"], prices_for=context["prices"], guard=context["guard"])


def test_chunks_journal_every_section_and_resume_to_complete(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    context = fixture(monkeypatch, tmp_path)
    legacy, order_sha, pin_sha = _legacy(tmp_path, context, monkeypatch)
    first = _run(context, tmp_path, legacy, order_sha, pin_sha, 2)
    assert (first["computed_this_chunk"], first["prior_entries"], first["journaled_this_chunk"], first["complete"], first["remaining"]) == (2, 0, 2, False, 2)
    assert "SYNTHETIC" not in json.dumps(first)  # aggregates only
    journal = tmp_path / "store" / f"journal-{order_sha}-{pin_sha}.jsonl"
    assert len(journal.read_text().splitlines()) == 2 and oct(journal.stat().st_mode & 0o777) == "0o600"
    for directory in ("store", "store/receipts", "store/manifests"):
        assert oct((tmp_path / directory).stat().st_mode & 0o777) == "0o700"
    second = _run(context, tmp_path, legacy, order_sha, pin_sha, 4)
    assert (second["computed_this_chunk"], second["prior_entries"], second["complete"], second["remaining"]) == (2, 2, True, 0)
    manifest = json.loads((tmp_path / "store" / "manifests" / f"{second['manifest_sha256']}.json").read_text())
    assert manifest["complete"] is True and len(manifest["entries"]) == 4
    assert manifest["entries"] == driver.read_journal(journal)  # the journal rebuilds exactly the executor's entries


def test_an_interrupted_chunk_loses_no_committed_section(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    context = fixture(monkeypatch, tmp_path)
    legacy, order_sha, pin_sha = _legacy(tmp_path, context, monkeypatch)
    calls = {"n": 0}

    def fail_on_second(database: Any, **kw: Any) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise ValueError("ensemble_execution_window_ended")
    context["compute_hook"] = fail_on_second
    with pytest.raises(ValueError, match="window_ended"):
        _run(context, tmp_path, legacy, order_sha, pin_sha, 4)
    journal = tmp_path / "store" / f"journal-{order_sha}-{pin_sha}.jsonl"
    assert len(driver.read_journal(journal)) == 1
    context["compute_hook"] = None
    resumed = _run(context, tmp_path, legacy, order_sha, pin_sha, 4)
    assert (resumed["prior_entries"], resumed["computed_this_chunk"], resumed["complete"]) == (1, 3, True)


def test_a_torn_last_journal_line_is_cut_and_any_other_bad_line_refuses(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    good = json.dumps({"schema": driver.JOURNAL_SCHEMA, "entry": {"market": "NYSE", "session_date": "2021-06-01", "as_of": "x"}})
    fd = os.open(journal, os.O_WRONLY | os.O_CREAT, 0o600)
    os.write(fd, (good + "\n" + good[:20]).encode())
    os.close(fd)
    assert len(driver.read_journal(journal)) == 1
    assert journal.read_text() == good + "\n"  # the torn bytes are gone: the next append starts on its own line
    driver.append_journal(journal, {"market": "NASDAQ", "session_date": "2021-06-01", "as_of": "x"})
    assert len(driver.read_journal(journal)) == 2
    journal.write_text(good + "\nnot json\n" + good + "\n")
    with pytest.raises(ValueError):
        driver.read_journal(journal)
    journal.chmod(0o644)
    with pytest.raises(ValueError, match="journal_not_private"):
        driver.read_journal(journal)


def test_running_code_must_be_the_checkout_and_the_checkout_path_has_no_link(tmp_path: Path) -> None:
    app = tmp_path / "app"
    app.mkdir()
    (app / "valuation_ensemble_x.py").write_bytes(b"a")
    (app / "valuation_pit_rerun.py").write_bytes(b"b")
    digest = {name: __import__("hashlib").sha256(data).hexdigest() for name, data in (("valuation_ensemble_x.py", b"a"), ("valuation_pit_rerun.py", b"b"))}
    checkout = {driver.APP_PREFIX + name: value for name, value in digest.items()}
    driver.running_files(checkout, app)
    (app / "valuation_pit_rerun.py").write_bytes(b"changed")
    with pytest.raises(ValueError, match="running_code_differs"):
        driver.running_files(checkout, app)
    (app / "valuation_pit_rerun.py").write_bytes(b"b")
    (app / "valuation_ensemble_extra.py").write_bytes(b"c")
    with pytest.raises(ValueError, match="running_modules_differ"):
        driver.running_files(checkout, app)
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "order.json").write_text("{}")
    (tmp_path / "root").mkdir()
    (tmp_path / "root" / "c3po").symlink_to(tmp_path / "real")
    with pytest.raises(ValueError, match="symlink"):
        driver.checkout_file(tmp_path / "root", Path("c3po/order.json"))


class _Database:
    database_url = ""

    def __init__(self) -> None:
        self._ingestion_runs: dict[str, dict[str, Any]] = {}


def test_the_guard_refuses_blocking_ingestions_and_waits_for_an_asfiled_poll() -> None:
    database = _Database()
    clock = lambda: NOW  # noqa: E731
    ticks = {"t": 0.0}
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        ticks["t"] += seconds
        if len(sleeps) == 3:
            database._ingestion_runs["p"]["status"] = "succeeded"
    guard = driver.operational_guard(database, clock=clock, blocking=lambda db, now: 0, sleep=sleep, monotonic=lambda: ticks["t"])
    assert guard() is None and sleeps == []
    database._ingestion_runs["p"] = {"status": "running", "source_code": "sec_asfiled", "started_at": NOW - timedelta(minutes=1)}
    assert guard() is None and len(sleeps) == 3  # waited for the poll to end
    database._ingestion_runs["p"] = {"status": "running", "source_code": "sec_asfiled", "started_at": NOW - timedelta(minutes=1)}
    with pytest.raises(ValueError, match="asfiled_poll_running"):
        driver.operational_guard(database, clock=clock, blocking=lambda db, now: 0, sleep=sleep, monotonic=lambda: ticks["t"], wait_seconds=0)()
    database._ingestion_runs["p"]["started_at"] = NOW - timedelta(hours=13)  # outside the window: not a poll in flight
    assert driver.operational_guard(database, clock=clock, blocking=lambda db, now: 0, sleep=sleep, monotonic=lambda: ticks["t"], wait_seconds=0)() is None
    with pytest.raises(ValueError, match="blocking_ingestion"):
        driver.operational_guard(database, clock=clock, blocking=lambda db, now: 1)()


def test_a_refusal_prints_a_code_never_free_text(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("PGOPTIONS", "")
    assert driver.refusal_code(ValueError("ensemble_owner_order_expired")) == "ensemble_owner_order_expired"
    assert driver.refusal_code(ValueError("pinned price vintage of NASDAQ AAPL")) == "exception:ValueError"
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"{}")))

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("TICKER leaked")
    monkeypatch.setattr(driver, "run_chunk", refuse)
    code = driver.main(["--owner-order-sha256", "a" * 64, "--pin-sha256", "b" * 64, "--instrument-commit", "c" * 40,
                        "--owner-signature-comment-id", "1", "--technical-go-comment-id", "2", "--max-runs", "3",
                        "--stop-before", (NOW + timedelta(hours=1)).isoformat()], database=object(), settings=object())
    out = capsys.readouterr()
    assert code == 2 and "TICKER" not in out.out and json.loads(out.out.splitlines()[-1])["reason"] == "exception:RuntimeError"


def test_the_price_reader_is_the_rev3_pin() -> None:
    assert driver.price_pin_of({"price_pin": {"requested_at": "2026-10-19T18:30:00-03:00"}}) == datetime(2026, 10, 19, 21, 30, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        driver.price_pin_of({"price_pin": {}})
