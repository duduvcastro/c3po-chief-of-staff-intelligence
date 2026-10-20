"""The grid of PREREG_VALUATION_PIT_BACKTEST_US_V1 (``valuation_pit_grid``) over the REAL re-executor on the in-memory
double: both US exchanges per T through ``PitRerunService``'s public API, one price pin and one catalogue pin for the whole
grid (and the inputs every run must carry), the manifest (hash, 0600, printed before it is written, a NEW path in an
existing directory), resuming without recomputing a complete T and never listing half a T, ``--max-runs``,
``--stop-before`` before every exchange's run and by prediction, SIGTERM, the A → B → A trap, the refusals (a vintage
that cannot start the grid, a pin in the future or before any publication, a range outside the bounds, other producer
files), a failing run (the manifest of what was done, the error's type only, re-raised), the dry run and the host check
(nothing written), and the report over the grid's own manifest. Synthetic symbols, no network."""
from __future__ import annotations

import json
import os
import signal
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
CATALOGUE_PIN = VINTAGE_AT
SYMBOLS = [symbol for symbols in US.values() for symbol in symbols]


REAL_VOLUME_CHECK = grid.volume_check
DECIDED = {"events": 3, "as_traded_like": 3, "split_adjusted_like": 0, "decision": "as_traded", "field": "dollar_volume_median_20", "series_read": 10}


@pytest.fixture(autouse=True, name="short_grid_fixture")
def short_grid_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    short_grid(monkeypatch)


def short_grid(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fixture's vintage spans 2023-06-01 … 2024-07-31: the grid starts on 2024-06-03 (200 prior sessions) and ends 22
    sessions before 2024-07-31 — four instants at a step of 5. Its series hold no split: the volume check is decided here
    (``DECIDED``) and read for real in its own test."""
    monkeypatch.setattr(backtest, "GRID_START", date(2024, 6, 3))
    monkeypatch.setattr(backtest, "MIN_PRIOR_SESSIONS", 200)
    monkeypatch.setattr(grid, "volume_check", lambda *args, **kwargs: dict(DECIDED))


def _publish_prices(database: Database, *, end: date = date(2024, 7, 31), at: datetime = VINTAGE_AT, scale: float = 1.0) -> None:
    sessions = _sessions("2023-06-01", end.isoformat())
    for offset, (market, symbols) in enumerate(US.items()):
        bars = {f"{symbol}.US": [{**bar, "close": bar["close"] * scale, "adjusted_close": bar["adjusted_close"] * scale}
                                 for bar in _bars_for(symbol, sessions, base=100.0 + 10 * index)] for index, symbol in enumerate(symbols)}
        http = ScriptedHttp({f"/api/eod/{key}": rows for key, rows in bars.items()})
        producer = series.PriceHistoryService(_settings(), database, http, eodhd=EodhdClient("https://eodhd.com", "secret", http))  # type: ignore[arg-type]
        producer.persist_run(market, start=date(2023, 6, 1), end=end, symbols=list(symbols), now=at + timedelta(minutes=offset))


def _catalogue(database: Database, market: str, symbols: tuple[str, ...] | list[str], at: datetime) -> None:
    database.save_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE", "mv-cat", {"methodology_version": 7},
                                    {"rows": [{"symbol": s, "sector": SECTOR, "industry": "Machinery", "valuation_profile": "general", "security_type": "Stock"}
                                              for s in symbols]}, at)


def _source(database: Database, market: str, symbol: str, at: datetime) -> None:
    payload = _payload(symbol)
    database.save_analysis_snapshot(pit.SOURCE_ANALYSIS_TYPE, pit.source_entity_key(market, pit.PROVIDER_EODHD, symbol), "mv-src",
                                    {"symbol": symbol, "symbol_sha256": pit.symbol_hash(symbol), "fetched_at": at.isoformat(),
                                     "payload_sha256": official.canonical_sha256(payload)},
                                    {"payload": payload, "payload_sha256": official.canonical_sha256(payload)}, at)


def _treasury(database: Database, at: datetime) -> None:
    curve = {"fetched_at": at.isoformat(), "series": {sym: [{"date": d.isoformat(), "close": 4.0 + tenor / 10} for d in _sessions("2023-01-01", "2024-07-31")]
                                                     for tenor, sym in pit.US_CURVE_SYMBOLS}}
    curve["payload_sha256"] = canonical_payload_sha256(curve)
    database.save_analysis_snapshot(pit.SOURCE_ANALYSIS_TYPE, pit.MACRO_TREASURY_KEY, "mv-src", {"fetched_at": at.isoformat(), "payload_sha256": curve["payload_sha256"]},
                                    {"payload": curve, "payload_sha256": curve["payload_sha256"]}, at)


def _store(**prices: Any) -> Database:
    database = Database(_settings())
    _publish_prices(database, **prices)
    for market, symbols in US.items():
        _catalogue(database, market, symbols, VINTAGE_AT - timedelta(hours=1))
        for symbol in symbols:
            _source(database, market, symbol, VINTAGE_AT)
    _treasury(database, VINTAGE_AT)
    return database


def _runs(database: Database) -> list[dict[str, Any]]:
    return [item for item in database._analysis_snapshots if item["analysis_type"] == pit.ANALYSIS_TYPE]


def _args(manifest: Path | None, *extra: str, pin: datetime = PIN, catalogue_pin: datetime = CATALOGUE_PIN) -> list[str]:
    args = ["--market", "US", "--price-pinned-at", pin.isoformat(), "--catalogue-pinned-at", catalogue_pin.isoformat(), "--statements", "provider"]
    return args + (["--manifest-out", str(manifest)] if manifest is not None else []) + list(extra)


def _lines(text: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _manifest(path: Path) -> dict[str, Any]:
    return backtest.load_manifest(path.read_text(encoding="utf-8"))


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
    sources = grid.resolve_sources(database, backtest.MARKETS, CATALOGUE_PIN)
    assert sources["NASDAQ"]["catalogue_rows"] == 5 and sources["NASDAQ"]["pit_sources"] == 5 and len(sources["NASDAQ"]["expected"]) == 10  # EODHD + FMP (absent)
    with pytest.raises(grid.GridError, match="no NASDAQ catalogue published before"):
        grid.resolve_sources(database, backtest.MARKETS, VINTAGE_AT - timedelta(days=1))
    assert grid.ENGINE_FILES == pit.IMPLEMENTATION_FILES and grid.producer()["engine_sha256"] == official.canonical_sha256({"files": grid.engine_files(), "objects": grid.engine_objects()})


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
    assert run["price_vintage"] == lines[-1]["manifest"]["price_pin"]["NASDAQ"]["publication_id"] and lines[0]["elapsed_seconds"] >= 0 and lines[0]["peak_rss_kb"] > 0
    assert stat.S_IMODE(os.stat(first).st_mode) == 0o600
    manifest = _manifest(first)  # the hash recomputes
    assert manifest == lines[-1]["manifest"] and lines[-1]["manifest_sha256"] == manifest["manifest_sha256"] == backtest.manifest_sha256(manifest)
    assert manifest["complete"] is False and manifest["remaining"] == 2 and manifest["stopped"] == {"reason": "max_runs", "at": "2024-06-18T04:00:00+00:00"}
    assert [(entry["session_date"], entry["market"]) for entry in manifest["grid"]] == [("2024-06-03", "NASDAQ"), ("2024-06-03", "NYSE"), ("2024-06-10", "NASDAQ"),
                                                                                         ("2024-06-10", "NYSE")]
    assert manifest["grid"][0]["as_of"] == "2024-06-04T04:00:00+00:00" and manifest["owner_order_sha256"] == "a" * 64 and manifest["grid_start"] == "2024-06-03"
    assert manifest["producer"] == grid.producer() and manifest["statements"] == "provider" and manifest["step_sessions"] == 5
    catalogue = manifest["catalogue_pin"]
    assert catalogue["requested_at"] == CATALOGUE_PIN.isoformat() and catalogue["NASDAQ"]["catalogue_rows"] == 5 and "expected" not in catalogue["NASDAQ"]
    assert len(_runs(database)) == 4
    snapshot = _runs(database)[0]
    assert snapshot["inputs"]["manifest"]["engine"]["implementation_file_sha256"] == grid.engine_files()  # the producer the reuse compares IS the run's
    assert snapshot["inputs"]["catalogue_pin"]["resolved_snapshot_id"] == catalogue["NASDAQ"]["catalogue_snapshot_id"]
    # resume: the two complete instants are reused, never recomputed; the rest is computed; the manifest is complete
    second = tmp_path / "grid-2.json"
    assert grid.main(_args(second), database=database, settings=_settings()) == 0
    lines = _lines(capsys.readouterr().out)
    resumed = _manifest(second)
    assert [line["runs"]["NYSE"]["reused"] for line in lines if line["kind"] == "t"] == [True, True, False, False] and len(_runs(database)) == 8
    assert resumed["complete"] is True and resumed["remaining"] == 0 and resumed["stopped"] is None and len(resumed["grid"]) == 8
    assert resumed["grid"][:4] == [{**entry, "idempotent": True, "reused": True} for entry in manifest["grid"]]
    # the report reads exactly the grid's runs: every one current and complete (this fixture has no as-filed table and a 2023 vintage)
    monkeypatch.setattr(backtest, "STATEMENTS", "provider")
    monkeypatch.setattr(backtest, "PRICE_VINTAGE_FROM_LATEST", date(2030, 1, 1))
    service = backtest.PitBacktestReportService(backtest.ReadOnlyStore(database), settings=_settings())  # type: ignore[arg-type]
    payload = service.report(resumed, prereg_sha256="f" * 64, code_pins=accuracy.pins_of(backtest.code_fingerprint()))["payload"]
    assert payload["grid"]["status"] == "PREREG" and payload["runs"]["status"] == {"current": 8} and payload["runs"]["incomplete"] == 0
    assert payload["runs"]["producer"]["engine_files"] == grid.engine_files() and payload["records"]["observations"] == 40
    assert payload["coverage"]["US"]["evaluated"] == 40 and payload["coverage"]["US"]["catalogue_stocks"] == 40 and payload["coverage"]["US"]["records_share"] == 1.0
    assert payload["screen"]["removed_by_rule"] == {"market_cap_below_min": 40}  # 1M shares at ~$100: nothing passes the PIT screen
    assert payload["verdict"]["status"] == "UNMEASURED" and payload["verdict"]["reasons"] == ["no_eligible_observations"]
    with pytest.raises(SystemExit):
        grid.main(_args(second), database=database, settings=_settings())  # an existing path is refused before anything runs
    # --recompute-existing goes through the public API: every run comes back idempotent, nothing written
    third = tmp_path / "grid-3.json"
    assert grid.main(_args(third, "--recompute-existing"), database=database, settings=_settings()) == 0
    again = _manifest(third)
    assert all(entry["idempotent"] and not entry["reused"] for entry in again["grid"]) and len(_runs(database)) == 8
    assert [entry["run_key"] for entry in again["grid"]] == [entry["run_key"] for entry in resumed["grid"]]


def test_every_run_carries_the_grids_catalogue_treasury_and_sources(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    database = _store()
    assert grid.main(_args(tmp_path / "a.json", "--to", "2024-06-03"), database=database, settings=_settings()) == 0
    # a later catalogue drops a name: a pin after it resolves it; the reused runs carry the first one → refused
    _catalogue(database, "NASDAQ", US["NASDAQ"][:-1], VINTAGE_AT + timedelta(minutes=5))
    with pytest.raises(grid.GridError, match="read other inputs than the grid resolved at start"):
        grid.main(_args(tmp_path / "b.json", "--to", "2024-06-03", catalogue_pin=VINTAGE_AT + timedelta(minutes=10)), database=database, settings=_settings())
    assert _manifest(tmp_path / "b.json")["stopped"]["error"] == "GridError"
    # the pinned catalogue (before it) is still the grid's: reused, accepted
    assert grid.main(_args(tmp_path / "c.json", "--to", "2024-06-03"), database=database, settings=_settings()) == 0
    assert all(entry["reused"] for entry in _manifest(tmp_path / "c.json")["grid"])
    # a re-fetched source snapshot or another Treasury history after the runs: the reused runs read the old ones → refused
    _source(database, "NYSE", "FFF", VINTAGE_AT + timedelta(minutes=20))
    with pytest.raises(grid.GridError, match="pit_source"):
        grid.main(_args(tmp_path / "d.json", "--to", "2024-06-03"), database=database, settings=_settings())
    fresh = _store()
    assert grid.main(_args(tmp_path / "e.json", "--to", "2024-06-03"), database=fresh, settings=_settings()) == 0
    _treasury(fresh, VINTAGE_AT + timedelta(minutes=20))
    with pytest.raises(grid.GridError, match="treasury_snapshot"):
        grid.main(_args(tmp_path / "f.json", "--to", "2024-06-03"), database=fresh, settings=_settings())
    capsys.readouterr()


def test_an_a_b_a_sequence_of_inputs_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    database = _store()
    assert grid.main(_args(tmp_path / "a.json", "--to", "2024-06-03"), database=database, settings=_settings()) == 0  # A (catalogue 1)
    _catalogue(database, "NASDAQ", US["NASDAQ"][:-1], VINTAGE_AT + timedelta(minutes=5))
    later = VINTAGE_AT + timedelta(minutes=10)
    assert grid.main(_args(tmp_path / "b.json", "--to", "2024-06-03", "--recompute-existing", catalogue_pin=later), database=database, settings=_settings()) == 0  # B
    assert _manifest(tmp_path / "b.json")["grid"][0]["supersedes"] == _manifest(tmp_path / "a.json")["grid"][0]["run_key"]
    # back to catalogue 1: A comes back idempotent, but the store's latest run of (NASDAQ, T) is B — never a silent success
    with pytest.raises(grid.GridError, match="is not the run just computed"):
        grid.main(_args(tmp_path / "c.json", "--to", "2024-06-03", "--recompute-existing"), database=database, settings=_settings())
    assert _manifest(tmp_path / "c.json")["grid"] == [] and _manifest(tmp_path / "c.json")["stopped"]["market"] == "NASDAQ"
    capsys.readouterr()


def test_a_failing_nyse_run_never_leaves_half_a_t_in_the_manifest_and_the_resume_reuses_nasdaq(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    database = _store()
    original = pit.PitRerunService.rerun
    calls: list[str] = []

    def flaky(self: pit.PitRerunService, market: str, **kwargs: Any) -> Any:
        calls.append(market)
        if len(calls) == 4:
            raise ValueError("FFF exploded")  # a message that names a symbol: never printed
        return original(self, market, **kwargs)

    monkeypatch.setattr(pit.PitRerunService, "rerun", flaky)
    path = tmp_path / "failed.json"
    with pytest.raises(ValueError, match="FFF exploded"):
        grid.main(_args(path), database=database, settings=_settings())
    out = capsys.readouterr().out
    assert "FFF" not in out and "exploded" not in out and _lines(out)[-1]["kind"] == "manifest"
    manifest = _manifest(path)
    assert manifest["stopped"] == {"reason": "error", "at": "2024-06-11T04:00:00+00:00", "market": "NYSE", "error": "ValueError"}
    assert [entry["session_date"] for entry in manifest["grid"]] == ["2024-06-03", "2024-06-03"] and manifest["complete"] is False  # never half a T
    assert len(_runs(database)) == 3  # NASDAQ of the second T was written: it is reused, never listed alone
    monkeypatch.setattr(pit.PitRerunService, "rerun", original)
    capped = tmp_path / "capped.json"
    assert grid.main(_args(capped, "--max-runs", "0"), database=database, settings=_settings()) == 0  # NYSE still missing: the T needs a run
    assert [entry["session_date"] for entry in _manifest(capped)["grid"]] == ["2024-06-03", "2024-06-03"] and len(_runs(database)) == 3
    assert _manifest(capped)["stopped"] == {"reason": "max_runs", "at": "2024-06-11T04:00:00+00:00"}
    resumed = tmp_path / "resumed.json"
    assert grid.main(_args(resumed), database=database, settings=_settings()) == 0
    second = [entry for entry in _manifest(resumed)["grid"] if entry["session_date"] == "2024-06-10"]
    assert [(entry["market"], entry["reused"]) for entry in second] == [("NASDAQ", True), ("NYSE", False)]
    capsys.readouterr()


def test_the_stop_window_is_checked_before_every_run_by_clock_and_by_prediction_and_sigterm_stops_between_runs(tmp_path: Path,
                                                                                                              capsys: pytest.CaptureFixture[str],
                                                                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    database = _store()
    now = datetime(2026, 10, 18, 22, 0, tzinfo=UTC)
    stop = now + timedelta(minutes=30)
    ticks: list[datetime] = []

    def clock() -> datetime:  # 1: the pin check; 2: before T1; 3: before NASDAQ; 4: before NYSE → past the stop
        ticks.append(now)
        return now if len(ticks) < 4 else stop + timedelta(seconds=1)

    path = tmp_path / "stop.json"
    assert grid.main(_args(path, "--stop-before", stop.isoformat(), "--sources", "v3_2_shadow"), database=database, settings=_settings(), clock=clock) == 0  # the rev-1 timing
    stopped = _manifest(path)
    assert stopped["stopped"] == {"reason": "stop_before", "at": "2024-06-04T04:00:00+00:00", "market": "NYSE"} and stopped["grid"] == [] and len(_runs(database)) == 1
    # by prediction, before any instant is measured: 300 s per run, two runs per T, × 1.5 = 900 s → a stop 800 s away starts nothing
    run = grid.GridRun(database, _settings(), market_group="US", price_pinned_at=PIN, catalogue_pinned_at=CATALOGUE_PIN, statements="provider", step=5,
                       clock=lambda: now, monotonic=lambda: 0.0, emit=lambda line: None, sources=("v3_2_shadow",))
    prior = run.run(start=None, end=None, max_runs=None, stop_before=now + timedelta(seconds=800), recompute_existing=True, owner_order_sha256=None)
    assert prior["stopped"] == {"reason": "stop_before_predicted", "at": "2024-06-04T04:00:00+00:00"} and prior["grid"] == []
    # by prediction, measured: the first instant (900 s predicted < 1,200 s) took 1,000 s; the next (1.5 × 1,000 s) would end after the stop → not started
    steps = iter(range(0, 100_000, 200))
    run = grid.GridRun(database, _settings(), market_group="US", price_pinned_at=PIN, catalogue_pinned_at=CATALOGUE_PIN, statements="provider", step=5,
                       clock=lambda: now, monotonic=lambda: float(next(steps)), emit=lambda line: None, sources=("v3_2_shadow",))
    predicted = run.run(start=None, end=None, max_runs=None, stop_before=now + timedelta(seconds=1200), recompute_existing=True, owner_order_sha256=None)
    assert predicted["stopped"] == {"reason": "stop_before_predicted", "at": "2024-06-11T04:00:00+00:00"} and len(predicted["grid"]) == 2
    # SIGTERM during a run: the run completes, the next one is not started, the manifest is written, the handler restored
    fresh = _store()
    original = pit.PitRerunService.rerun
    before = signal.getsignal(signal.SIGTERM)

    def terminated(self: pit.PitRerunService, market: str, **kwargs: Any) -> Any:
        result = original(self, market, **kwargs)
        os.kill(os.getpid(), signal.SIGTERM)
        return result

    monkeypatch.setattr(pit.PitRerunService, "rerun", terminated)
    term = tmp_path / "term.json"
    assert grid.main(_args(term, "--sources", "v3_2_shadow"), database=fresh, settings=_settings()) == 0
    assert _manifest(term)["stopped"] == {"reason": "terminated", "at": "2024-06-04T04:00:00+00:00", "market": "NYSE"} and len(_runs(fresh)) == 1
    assert signal.getsignal(signal.SIGTERM) == before
    capsys.readouterr()


def test_the_manifest_is_printed_before_it_is_written_and_the_producer_can_be_required(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    database = _store()

    def broken(path: Path, detail: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(pit, "write_private_detail", broken)
    with pytest.raises(OSError):
        grid.main(_args(tmp_path / "x.json", "--to", "2024-06-03"), database=database, settings=_settings())
    printed = _lines(capsys.readouterr().out)[-1]
    assert printed["kind"] == "manifest" and printed["manifest"]["manifest_sha256"] == printed["manifest_sha256"]  # nothing lost when the write fails
    monkeypatch.undo()
    short_grid(monkeypatch)
    with pytest.raises(SystemExit):
        grid.main(_args(tmp_path / "x.json", "--expect-producer-sha256", "0" * 64), database=database, settings=_settings())
    assert grid.main(_args(tmp_path / "y.json", "--to", "2024-06-03", "--expect-producer-sha256", grid.producer()["engine_sha256"]),
                     database=database, settings=_settings()) == 0
    with pytest.raises(SystemExit):
        grid.main(_args(tmp_path / "absent" / "z.json"), database=database, settings=_settings())  # the directory must exist: nothing runs
    capsys.readouterr()


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
    with monkeypatch.context() as patch:
        other_readers = {**grid.engine_objects(), "app.database.Database.price_bars": "0" * 64}
        patch.setattr(grid, "engine_objects", lambda: other_readers)
        assert not reusable()  # another store reader
    original = database.valuation_predictions_for_cycle
    with monkeypatch.context() as patch:
        patch.setattr(database, "valuation_predictions_for_cycle", lambda cycle_id, *, source: dict(list(original(cycle_id, source=source).items())[1:]))
        assert not reusable()  # a cycle missing a record is not complete
    assert grid.main(_args(tmp_path / "b.json", "--max-runs", "0"), database=database, settings=_settings()) == 0
    resumed = _manifest(tmp_path / "b.json")
    assert resumed["complete"] is True and len(resumed["grid"]) == 8 and all(entry["reused"] for entry in resumed["grid"]) and resumed["stopped"] is None


def test_the_cli_refuses_what_would_not_be_the_pre_registered_grid_and_the_dry_run_and_host_check_write_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    database = _store()
    for refused in (["--market", "US", "--price-pinned-at", "2026-09-11T03:30:00", "--catalogue-pinned-at", CATALOGUE_PIN.isoformat(),
                     "--manifest-out", str(tmp_path / "x.json")],  # naive pin
                    ["--market", "US", "--price-pinned-at", PIN.isoformat(), "--manifest-out", str(tmp_path / "x.json")],  # no catalogue pin
                    _args(tmp_path / "x.json", pin=datetime.now(UTC) + timedelta(days=1)),  # a price pin in the future
                    _args(tmp_path / "x.json", catalogue_pin=datetime.now(UTC) + timedelta(days=1)),  # a catalogue pin in the future
                    _args(tmp_path / "x.json", pin=VINTAGE_AT - timedelta(days=1)),  # before any publication
                    _args(tmp_path / "x.json", catalogue_pin=VINTAGE_AT - timedelta(days=1)),  # before any catalogue
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
    assert printed["price_pin"]["NASDAQ"]["publication_id"] and printed["catalogue_pin"]["NYSE"]["catalogue_rows"] == 5
    assert len(database._analysis_snapshots) == count and os.environ["PGOPTIONS"].endswith(accuracy.READ_ONLY_PGOPTION)
    monkeypatch.setenv("PGOPTIONS", "")
    database.begin_ingestion_run("synthetic-source", "Synthetic", "regulatory_disclosure", {})  # an investor-relations poll: seconds long
    assert grid.main(["--market", "US", "--host-check"], database=database, settings=_settings()) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["kind"] == "host_check" and checked["publications"]["NYSE"]["symbols"] == 5 and checked["publications"]["NYSE"]["from"] == "2023-06-01"
    assert checked["coverage"] == {"mode": "vintages", "table_present": False, "NASDAQ": {"catalogue": 5, "covered_in_catalogue": 0},
                                   "NYSE": {"catalogue": 5, "covered_in_catalogue": 0}}
    assert checked["ingestion_runs"] == {"running": 1, "blocking": 0} and checked["producer"]["engine_files"] == grid.engine_files()
    assert checked["producer"]["engine_objects"] == grid.engine_objects()
    assert len(database._analysis_snapshots) == count and not any(symbol in json.dumps(checked) for symbol in SYMBOLS)
    later = datetime.now(UTC) + timedelta(minutes=31)
    assert grid.running_ingestions(database, later) == {"running": 1, "blocking": 1}  # running for more than 30 min: whatever its source, it blocks
    assert grid.running_ingestions(database, datetime.now(UTC) + timedelta(hours=13)) == {"running": 0, "blocking": 0}  # older than 12 h: abandoned
    database.begin_ingestion_run("valuation-nightly", "Valuation worker", grid.NIGHTLY_SOURCE_TYPE, {})
    assert grid.running_ingestions(database, datetime.now(UTC)) == {"running": 2, "blocking": 1}  # the nightly worker blocks from its start
    with pytest.raises(SystemExit):
        grid.main(["--market", "US", "--host-check", "--price-pinned-at", PIN.isoformat()], database=database, settings=_settings())


def test_every_disagreement_of_a_run_with_the_grids_inputs_is_named_on_its_own() -> None:
    resolved = {"catalogue_snapshot_id": "catalogue-1", "classification_sha256": "c" * 64, "treasury_snapshot_id": "treasury-1",
                "expected": {f"{pit.PROVIDER_EODHD}:{'s' * 16}": "2026-09-11T03:00:00+00:00"}}
    run = {"sources": [{"role": "catalogue", "classification_sha256": "c" * 64},
                       {"role": pit.PROVIDER_EODHD, "market": "NASDAQ", "symbol_sha256": "s" * 16, "published_at": "2026-09-11T03:00:00+00:00"}],
           "macro": {"curve": {"snapshot_id": "treasury-1"}}}
    assert grid.check_sources(run, resolved, market="NASDAQ", catalogue_snapshot_id="catalogue-1") == []
    assert grid.check_sources(run, resolved, market="NASDAQ", catalogue_snapshot_id="catalogue-2") == ["catalogue_snapshot"]  # the same content, another snapshot
    other = {**run, "sources": [{"role": "catalogue", "classification_sha256": "d" * 64}, run["sources"][1]]}
    assert grid.check_sources(other, resolved, market="NASDAQ", catalogue_snapshot_id="catalogue-1") == ["catalogue_classification"]  # the pinned id, other rows
    assert grid.check_sources({**run, "macro": {"curve": {"snapshot_id": "treasury-2"}}}, resolved, market="NASDAQ",
                              catalogue_snapshot_id="catalogue-1") == ["treasury_snapshot"]
    later = {**run, "sources": [run["sources"][0], {**run["sources"][1], "published_at": "2026-09-12T03:00:00+00:00"}]}
    assert grid.check_sources(later, resolved, market="NASDAQ", catalogue_snapshot_id="catalogue-1") == [f"pit_source:{pit.PROVIDER_EODHD}"]


def test_an_error_outside_a_run_still_prints_and_writes_the_manifest_of_what_was_done(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    database = _store()
    original = grid.reusable_run
    calls: list[str] = []

    def failing_lookup(*args: Any, **kwargs: Any) -> Any:
        calls.append(args[1])
        if len(calls) > 2:  # the second T's reuse lookup: outside any run
            raise RuntimeError("the store went away while reading AAA")
        return original(*args, **kwargs)

    monkeypatch.setattr(grid, "reusable_run", failing_lookup)
    path = tmp_path / "lookup.json"
    with pytest.raises(RuntimeError):
        grid.main(_args(path), database=database, settings=_settings())
    out = capsys.readouterr().out
    manifest = _manifest(path)
    assert manifest["stopped"] == {"reason": "error", "at": "2024-06-11T04:00:00+00:00", "market": "NASDAQ", "error": "RuntimeError"}
    assert len(manifest["grid"]) == 2 and manifest["complete"] is False and "AAA" not in out and _lines(out)[-1]["kind"] == "manifest"


def _split_bars(symbol: str, sessions: list[date], *, at: int | None, factor: float, adjusted_volume: bool) -> list[dict[str, Any]]:
    """A series with a ``factor``:1 split at session index ``at``: the as-traded close is ``factor`` × the adjusted one before
    it; the volume is in traded shares (it jumps by ``factor`` at the split) or split-adjusted (it does not)."""
    rows = _bars_for(symbol, sessions, base=50.0)
    out = []
    for index, row in enumerate(rows):
        before = at is not None and index < at
        traded = 1000.0 if before else 1000.0 * (factor if at is not None else 1.0)
        out.append({**row, "close": round(row["adjusted_close"] * (factor if before else 1.0), 4),
                    "volume": 1000.0 * factor if adjusted_volume and at is not None else traded})
    return out


def test_the_volume_check_reads_the_capital_events_of_the_pinned_vintages_and_an_undetermined_one_runs_nothing(tmp_path: Path,
                                                                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    sessions = _sessions("2023-06-01", "2024-07-31")
    for adjusted, decision in ((False, "as_traded"), (True, "split_adjusted")):
        database = Database(_settings())
        for offset, (market, symbols) in enumerate(US.items()):
            bars = {f"{symbol}.US": _split_bars(symbol, sessions, at=60 + 40 * index if market == "NASDAQ" and index < 3 else None, factor=2.0 + index,
                                                adjusted_volume=adjusted) for index, symbol in enumerate(symbols)}
            http = ScriptedHttp({f"/api/eod/{key}": rows for key, rows in bars.items()})
            producer = series.PriceHistoryService(_settings(), database, http, eodhd=EodhdClient("https://eodhd.com", "secret", http))  # type: ignore[arg-type]
            producer.persist_run(market, start=date(2023, 6, 1), end=date(2024, 7, 31), symbols=list(symbols), now=VINTAGE_AT + timedelta(minutes=offset))
            _catalogue(database, market, symbols, VINTAGE_AT - timedelta(hours=1))
        pins = grid.resolve_pins(database, _settings(), backtest.MARKETS, PIN)
        checked = REAL_VOLUME_CHECK(database, _settings(), pins, backtest.MARKETS, CATALOGUE_PIN)
        assert checked == {"events": 3, "as_traded_like": 0 if adjusted else 3, "split_adjusted_like": 3 if adjusted else 0, "decision": decision,
                           "field": backtest.VOLUME_BASES[decision], "series_read": 10}, adjusted
    # a later republication (traded-share volumes) never changes the check of the PINNED publications
    for offset, (market, symbols) in enumerate(US.items()):
        bars = {f"{symbol}.US": _split_bars(symbol, sessions, at=60 + 40 * index if market == "NASDAQ" and index < 3 else None, factor=2.0 + index,
                                            adjusted_volume=False) for index, symbol in enumerate(symbols)}
        http = ScriptedHttp({f"/api/eod/{key}": rows for key, rows in bars.items()})
        producer = series.PriceHistoryService(_settings(), database, http, eodhd=EodhdClient("https://eodhd.com", "secret", http))  # type: ignore[arg-type]
        producer.persist_run(market, start=date(2023, 6, 1), end=date(2024, 7, 31), symbols=list(symbols), now=VINTAGE_AT + timedelta(hours=2, minutes=offset))
    assert REAL_VOLUME_CHECK(database, _settings(), pins, backtest.MARKETS, CATALOGUE_PIN)["decision"] == "split_adjusted"
    monkeypatch.setattr(grid, "volume_check", lambda *args, **kwargs: {**DECIDED, "decision": "undetermined", "field": None})
    store = _store()
    with pytest.raises(SystemExit):
        grid.main(_args(tmp_path / "undetermined.json"), database=store, settings=_settings())
    assert _runs(store) == [] and not (tmp_path / "undetermined.json").exists()
