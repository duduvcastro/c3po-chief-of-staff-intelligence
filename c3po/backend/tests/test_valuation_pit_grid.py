"""The grid of PREREG_VALUATION_PIT_BACKTEST_US_V1 (``valuation_pit_grid``) over the REAL re-executor on the in-memory
double: both US exchanges per T through ``PitRerunService``'s public API, the manifest (hash, 0600, a NEW path), resuming
without recomputing a complete T, ``--max-runs``/``--stop-before``, the refusals (a vintage that cannot start the grid, a
pin in the future or before any publication, a range outside the bounds), a failing run (the manifest of what was done,
the error's type only, re-raised), the dry run and the host check (nothing written), and the report over the grid's own
manifest. Synthetic symbols, no network."""
from __future__ import annotations

import json
import os
import stat
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app import valuation_accuracy_report as accuracy
from app import valuation_official as official
from app import valuation_pit_backtest_report as backtest
from app import valuation_pit_grid as grid
from app import valuation_pit_rerun as pit
from app import valuation_price_history as series
from app.database import Database
from app.market_data.eodhd import EodhdClient
from app.valuation_v3_macro import canonical_payload_sha256
from tests.test_valuation_pit_rerun import SECTOR, VINTAGE_AT, ScriptedHttp, _bars_for, _payload, _sessions, _settings

UTC = timezone.utc
US = {"NASDAQ": ("AAA", "BBB", "CCC", "DDD", "EEE"), "NYSE": ("FFF", "GGG", "HHH", "III", "JJJ")}  # five per exchange: peers
PIN = VINTAGE_AT + timedelta(minutes=30)
SYMBOLS = [symbol for symbols in US.values() for symbol in symbols]


@pytest.fixture(autouse=True)
def short_grid(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fixture's vintage spans 2023-06-01 … 2024-07-31: the grid starts on 2024-06-03 (200 prior sessions) and ends 22
    sessions before 2024-07-31 — five instants at a step of 5."""
    monkeypatch.setattr(backtest, "GRID_START", date(2024, 6, 3))
    monkeypatch.setattr(backtest, "MIN_PRIOR_SESSIONS", 200)


def _publish_prices(database: Database, *, end: date = date(2024, 7, 31), at: datetime = VINTAGE_AT, scale: float = 1.0) -> None:
    sessions = _sessions("2023-06-01", end.isoformat())
    for offset, (market, symbols) in enumerate(US.items()):
        bars = {f"{symbol}.US": [{**bar, "close": bar["close"] * scale, "adjusted_close": bar["adjusted_close"] * scale}
                                 for bar in _bars_for(symbol, sessions, base=100.0 + 10 * index)] for index, symbol in enumerate(symbols)}
        http = ScriptedHttp({f"/api/eod/{key}": rows for key, rows in bars.items()})
        producer = series.PriceHistoryService(_settings(), database, http, eodhd=EodhdClient("https://eodhd.com", "secret", http))  # type: ignore[arg-type]
        producer.persist_run(market, start=date(2023, 6, 1), end=end, symbols=list(symbols), now=at + timedelta(minutes=offset))


def _store(**prices: Any) -> Database:
    database = Database(_settings())
    _publish_prices(database, **prices)
    for market, symbols in US.items():
        database.save_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE", "mv-cat", {"methodology_version": 7},
                                        {"rows": [{"symbol": s, "sector": SECTOR, "industry": "Machinery", "valuation_profile": "general", "security_type": "Stock"}
                                                  for s in symbols]}, VINTAGE_AT - timedelta(hours=1))
        for symbol in symbols:
            payload = _payload(symbol)
            database.save_analysis_snapshot(pit.SOURCE_ANALYSIS_TYPE, pit.source_entity_key(market, pit.PROVIDER_EODHD, symbol), "mv-src",
                                            {"symbol": symbol, "symbol_sha256": pit.symbol_hash(symbol), "fetched_at": VINTAGE_AT.isoformat(),
                                             "payload_sha256": official.canonical_sha256(payload)},
                                            {"payload": payload, "payload_sha256": official.canonical_sha256(payload)}, VINTAGE_AT)
    curve = {"fetched_at": VINTAGE_AT.isoformat(), "series": {sym: [{"date": d.isoformat(), "close": 4.0 + tenor / 10} for d in _sessions("2023-01-01", "2024-07-31")]
                                                             for tenor, sym in pit.US_CURVE_SYMBOLS}}
    curve["payload_sha256"] = canonical_payload_sha256(curve)
    database.save_analysis_snapshot(pit.SOURCE_ANALYSIS_TYPE, pit.MACRO_TREASURY_KEY, "mv-src", {"fetched_at": VINTAGE_AT.isoformat(), "payload_sha256": curve["payload_sha256"]},
                                    {"payload": curve, "payload_sha256": curve["payload_sha256"]}, VINTAGE_AT)
    return database


def _runs(database: Database) -> list[dict[str, Any]]:
    return [item for item in database._analysis_snapshots if item["analysis_type"] == pit.ANALYSIS_TYPE]


def _args(manifest: Path | None, *extra: str, pin: datetime = PIN) -> list[str]:
    args = ["--market", "US", "--price-pinned-at", pin.isoformat(), "--statements", "provider"]
    return args + (["--manifest-out", str(manifest)] if manifest is not None else []) + list(extra)


def _lines(text: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_the_plan_is_the_report_modules_grid_and_a_vintage_that_cannot_start_it_is_refused() -> None:
    database = _store()
    pins = grid.resolve_pins(database, _settings(), backtest.MARKETS, PIN)
    bounds, full, sessions = grid.plan(pins, step=5, start=None, end=None)
    assert (bounds["first_eligible"], bounds["last_eligible"]) == ("2024-06-03", "2024-06-28") and full == sessions
    assert [day.isoformat() for day in full] == ["2024-06-03", "2024-06-10", "2024-06-17", "2024-06-25"]  # 19 June is no session: five sessions apart
    assert grid.plan(pins, step=5, start=date(2024, 6, 10), end=date(2024, 6, 20))[2] == [date(2024, 6, 10), date(2024, 6, 17)]  # a sub-range of THE grid
    with pytest.raises(grid.GridError, match="within the pre-registered bounds"):
        grid.plan(pins, step=5, start=date(2024, 5, 31), end=None)
    with pytest.raises(grid.GridError, match="cannot start the grid at 2023-06-05"):
        grid.plan(pins, step=5, start=None, end=None, grid_start=date(2023, 6, 5))  # 200 prior sessions do not exist there: not the pre-registered grid
    with pytest.raises(grid.GridError, match="no verifiable NASDAQ price vintage"):
        grid.resolve_pins(database, _settings(), backtest.MARKETS, VINTAGE_AT - timedelta(days=1))


def test_the_grid_runs_both_exchanges_per_t_writes_the_manifest_and_resumes_without_recomputing(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    database = _store()
    first = tmp_path / "grid-1.json"
    assert grid.main(_args(first, "--max-runs", "2", "--owner-order-sha256", "a" * 64), database=database, settings=_settings()) == 0
    out = capsys.readouterr().out
    lines = _lines(out)
    assert not any(symbol in out for symbol in SYMBOLS)  # aggregates only
    assert [line["kind"] for line in lines] == ["t", "t", "manifest"] and set(lines[0]["runs"]) == {"NASDAQ", "NYSE"}
    run = lines[0]["runs"]["NASDAQ"]
    assert run["reused"] is False and run["idempotent"] is False and run["records"] == 5 and run["evaluated"] == 5 and run["elapsed_seconds"] >= 0
    assert run["price_vintage"] == lines[-1]["manifest"]["price_pin"]["NASDAQ"]["publication_id"] and lines[0]["elapsed_seconds"] >= 0
    assert stat.S_IMODE(os.stat(first).st_mode) == 0o600
    manifest = backtest.load_manifest(first.read_text(encoding="utf-8"))  # the hash recomputes
    assert manifest == lines[-1]["manifest"] and lines[-1]["manifest_sha256"] == manifest["manifest_sha256"] == backtest.manifest_sha256(manifest)
    assert manifest["complete"] is False and manifest["remaining"] == 2 and manifest["stopped"] == {"reason": "max_runs", "at": "2024-06-18T04:00:00+00:00"}
    assert [(entry["session_date"], entry["market"]) for entry in manifest["grid"]] == [("2024-06-03", "NASDAQ"), ("2024-06-03", "NYSE"), ("2024-06-10", "NASDAQ"),
                                                                                         ("2024-06-10", "NYSE")]
    assert manifest["grid"][0]["as_of"] == "2024-06-04T04:00:00+00:00" and manifest["owner_order_sha256"] == "a" * 64 and manifest["grid_start"] == "2024-06-03"
    assert manifest["producer"] == grid.producer() and manifest["statements"] == "provider" and manifest["step_sessions"] == 5
    assert len(_runs(database)) == 4
    snapshot = _runs(database)[0]
    assert snapshot["inputs"]["manifest"]["engine"]["implementation_file_sha256"] == grid.engine_files()  # the producer the reuse compares IS the run's
    # resume: the two complete instants are reused, never recomputed; the rest is computed; the manifest is complete
    second = tmp_path / "grid-2.json"
    assert grid.main(_args(second), database=database, settings=_settings()) == 0
    lines = _lines(capsys.readouterr().out)
    resumed = backtest.load_manifest(second.read_text(encoding="utf-8"))
    assert [line["runs"]["NYSE"]["reused"] for line in lines if line["kind"] == "t"] == [True, True, False, False] and len(_runs(database)) == 8
    assert resumed["complete"] is True and resumed["remaining"] == 0 and resumed["stopped"] is None and len(resumed["grid"]) == 8
    assert resumed["grid"][:4] == [{**entry, "idempotent": True, "reused": True} for entry in manifest["grid"]]
    # the report reads exactly the grid's runs: every one current and complete
    monkeypatch.setattr(backtest, "STATEMENTS", "provider")  # this fixture has no as-filed table
    service = backtest.PitBacktestReportService(backtest.ReadOnlyStore(database), settings=_settings())  # type: ignore[arg-type]
    payload = service.report(resumed, prereg_sha256="f" * 64, code_pins=accuracy.pins_of(backtest.code_fingerprint()))["payload"]
    monkeypatch.undo()
    monkeypatch.setattr(backtest, "GRID_START", date(2024, 6, 3))
    monkeypatch.setattr(backtest, "MIN_PRIOR_SESSIONS", 200)
    assert payload["grid"]["status"] == "PREREG" and payload["runs"]["status"] == {"current": 8} and payload["runs"]["incomplete"] == 0
    assert payload["runs"]["producer"]["engine_files"] == grid.engine_files() and payload["records"]["observations"] == 40
    assert payload["coverage"]["US"]["evaluated"] == 40 and payload["verdict"]["status"] == "FAIL" and "blocks_below_min:1<12" in payload["verdict"]["reasons"]
    with pytest.raises(SystemExit):
        grid.main(_args(second), database=database, settings=_settings())  # an existing path is refused before anything runs
    # --recompute-existing goes through the public API: every run comes back idempotent, nothing written
    third = tmp_path / "grid-3.json"
    assert grid.main(_args(third, "--recompute-existing"), database=database, settings=_settings()) == 0
    again = backtest.load_manifest(third.read_text(encoding="utf-8"))
    assert all(entry["idempotent"] and not entry["reused"] for entry in again["grid"]) and len(_runs(database)) == 8
    assert [entry["run_key"] for entry in again["grid"]] == [entry["run_key"] for entry in resumed["grid"]]


def test_a_new_pin_recomputes_and_supersedes_and_the_stop_window_is_honoured(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    database = _store()
    assert grid.main(_args(tmp_path / "a.json", "--to", "2024-06-03"), database=database, settings=_settings()) == 0
    before = backtest.load_manifest((tmp_path / "a.json").read_text(encoding="utf-8"))
    _publish_prices(database, at=VINTAGE_AT + timedelta(hours=2), scale=2.0)  # another publication; the old pin still resolves the old one
    assert grid.main(_args(tmp_path / "b.json", "--to", "2024-06-03"), database=database, settings=_settings()) == 0
    assert backtest.load_manifest((tmp_path / "b.json").read_text(encoding="utf-8"))["grid"] == [{**entry, "idempotent": True, "reused": True} for entry in before["grid"]]
    newer = VINTAGE_AT + timedelta(hours=3)
    assert grid.main(_args(tmp_path / "c.json", "--to", "2024-06-03", pin=newer), database=database, settings=_settings()) == 0
    after = backtest.load_manifest((tmp_path / "c.json").read_text(encoding="utf-8"))
    assert all(not entry["reused"] for entry in after["grid"]) and [entry["supersedes"] for entry in after["grid"]] == [entry["run_key"] for entry in before["grid"]]
    capsys.readouterr()
    late = tmp_path / "d.json"
    assert grid.main(_args(late, "--stop-before", (datetime.now(UTC) - timedelta(minutes=1)).isoformat(), pin=newer), database=database, settings=_settings()) == 0
    stopped = backtest.load_manifest(late.read_text(encoding="utf-8"))
    assert [entry["reused"] for entry in stopped["grid"]] == [True, True]  # the reusable first T costs nothing and is listed
    assert stopped["stopped"] == {"reason": "stop_before", "at": "2024-06-11T04:00:00+00:00"} and stopped["complete"] is False


def test_a_failing_run_writes_what_was_done_names_only_the_errors_type_and_reraises(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    database = _store()
    original = pit.PitRerunService.rerun
    calls: list[str] = []

    def flaky(self: pit.PitRerunService, market: str, **kwargs: Any) -> Any:
        calls.append(market)
        if len(calls) == 3:
            raise ValueError("AAA exploded")  # a message that names a symbol: never printed
        return original(self, market, **kwargs)

    monkeypatch.setattr(pit.PitRerunService, "rerun", flaky)
    path = tmp_path / "failed.json"
    with pytest.raises(ValueError, match="AAA exploded"):
        grid.main(_args(path), database=database, settings=_settings())
    out = capsys.readouterr().out
    assert "AAA" not in out and "exploded" not in out
    manifest = backtest.load_manifest(path.read_text(encoding="utf-8"))
    assert manifest["stopped"] == {"reason": "error", "at": "2024-06-11T04:00:00+00:00", "market": "NASDAQ", "error": "ValueError"}
    assert [entry["session_date"] for entry in manifest["grid"]] == ["2024-06-03", "2024-06-03"] and manifest["complete"] is False  # never half a T
    # a run that resolves another publication than the grid's pin is refused (the grid reads ONE vintage)
    monkeypatch.setattr(pit.PitRerunService, "rerun", original)
    monkeypatch.setattr(grid, "resolve_pins", lambda *args, **kwargs: _wrong_pins(database))
    with pytest.raises(grid.GridError, match="another publication"):
        grid.main(_args(tmp_path / "wrong.json", "--recompute-existing"), database=database, settings=_settings())


def _wrong_pins(database: Database) -> dict[str, dict[str, Any]]:
    reader = series.PriceHistoryService(_settings(), database, ScriptedHttp({}))  # type: ignore[arg-type]
    pins: dict[str, dict[str, Any]] = {}
    for market in backtest.MARKETS:
        vintage = reader.vintage(market, available_before=PIN)
        assert vintage is not None
        pins[market] = {"status": "ok", "publication_id": "another", "price_snapshot_id": vintage["price_snapshot_id"], "available_at": vintage["available_at"],
                        "bars_sha256": vintage["bars_sha256"], "from": vintage["from"], "to": vintage["to"]}
    return pins


def test_the_cli_refuses_what_would_not_be_the_pre_registered_grid_and_the_dry_run_and_host_check_write_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    database = _store()
    for refused in (["--market", "US", "--price-pinned-at", "2026-09-11T03:30:00", "--manifest-out", str(tmp_path / "x.json")],  # naive pin
                    _args(tmp_path / "x.json", pin=datetime.now(UTC) + timedelta(days=1)),  # a pin in the future
                    _args(tmp_path / "x.json", pin=VINTAGE_AT - timedelta(days=1)),  # before any publication
                    _args(tmp_path / "x.json", "--from", "2024-05-01"),  # outside the bounds
                    _args(tmp_path / "x.json", "--grid-start", "2023-06-05"),  # a start the vintage cannot hold
                    _args(None),  # no manifest path
                    _args(tmp_path / "x.json", "--owner-order-sha256", "nope"),
                    _args(tmp_path / "x.json", "--max-runs", "-1"),
                    _args(None, "--dry-run", "--max-runs", "1")):
        with pytest.raises(SystemExit):
            grid.main(refused, database=database, settings=_settings())
    assert not (tmp_path / "x.json").exists() and _runs(database) == []
    capsys.readouterr()
    monkeypatch.setenv("PGOPTIONS", "")
    count = len(database._analysis_snapshots)
    assert grid.main(_args(None, "--dry-run"), database=database, settings=_settings()) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["kind"] == "dry_run" and printed["grid"]["count"] == 4 and printed["grid"]["sessions"][0] == "2024-06-03" and printed["prereg_grid_sessions"] == 4
    assert printed["reusable"] == {"runs": 0, "t_complete": 0} and printed["coverage"] == {"mode": "provider"} and printed["grid_start"] == "2024-06-03"
    assert printed["price_pin"]["NASDAQ"]["publication_id"] and len(database._analysis_snapshots) == count and os.environ["PGOPTIONS"].endswith(accuracy.READ_ONLY_PGOPTION)
    monkeypatch.setenv("PGOPTIONS", "")
    assert grid.main(["--market", "US", "--host-check"], database=database, settings=_settings()) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["kind"] == "host_check" and checked["publications"]["NYSE"]["symbols"] == 5 and checked["publications"]["NYSE"]["from"] == "2023-06-01"
    assert checked["coverage"] == {"mode": "vintages", "table_present": False, "NASDAQ": {"catalogue": 5, "covered_in_catalogue": 0},
                                   "NYSE": {"catalogue": 5, "covered_in_catalogue": 0}}
    assert len(database._analysis_snapshots) == count and not any(symbol in json.dumps(checked) for symbol in SYMBOLS)
    with pytest.raises(SystemExit):
        grid.main(["--market", "US", "--host-check", "--price-pinned-at", PIN.isoformat()], database=database, settings=_settings())


def test_reuse_requires_the_same_code_pin_mode_and_a_complete_cycle(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    database = _store()
    assert grid.main(_args(tmp_path / "a.json"), database=database, settings=_settings()) == 0
    capsys.readouterr()
    pins = grid.resolve_pins(database, _settings(), backtest.MARKETS, PIN)
    as_of = backtest.t_instant(date(2024, 6, 3))

    def reusable(**changes: Any) -> bool:
        options = {"publication_id": pins["NASDAQ"]["publication_id"], "statements": "provider", **changes}
        return grid.reusable_run(database, "NASDAQ", as_of, **options) is not None

    assert reusable()
    assert not reusable(publication_id="another") and not reusable(statements="vintages")
    with monkeypatch.context() as patch:
        patch.setattr(pit, "source_version", lambda: "pit-rerun-v1+otherbytes00")
        assert not reusable()  # another re-executor: recomputed, never reused
    with monkeypatch.context() as patch:
        other_engine = {**grid.engine_files(), "valuation_v3_engine.py": "0" * 64}
        patch.setattr(grid, "engine_files", lambda: other_engine)
        assert not reusable()  # another engine
    original = database.valuation_predictions_for_cycle
    with monkeypatch.context() as patch:
        patch.setattr(database, "valuation_predictions_for_cycle", lambda cycle_id, *, source: dict(list(original(cycle_id, source=source).items())[1:]))
        assert not reusable()  # a cycle missing a record is not complete
    # a complete grid resumed with --max-runs 0 lists every T, computing nothing
    assert grid.main(_args(tmp_path / "b.json", "--max-runs", "0"), database=database, settings=_settings()) == 0
    resumed = backtest.load_manifest((tmp_path / "b.json").read_text(encoding="utf-8"))
    assert resumed["complete"] is True and len(resumed["grid"]) == 8 and all(entry["reused"] for entry in resumed["grid"]) and resumed["stopped"] is None
