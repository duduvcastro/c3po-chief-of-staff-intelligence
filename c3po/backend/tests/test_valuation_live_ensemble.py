"""The nightly LIVE producer of the ensemble's primary target price (``app/valuation_live_ensemble.py``).

The parity tests are the point: on the signed grid's own fixture (``tests/test_valuation_ensemble_grid._fixture``, the real
canonical readers over synthetic memory), the live computation fed the SAME inputs the grid read — a fresh pin of the same
price publication, a fresh as-filed reader, the pinned Treasury history and the pinned target rows — returns, name by name,
EXACTLY the floats ``compute_grid_section`` returns (primary, every model value, sample size, consensus, screen flag).
Everything else: fail closed per name, off by default, isolated in the worker, counts-only logs, no PIT source written.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest

from app import valuation_env, valuation_live_ensemble as live, valuation_pit_rerun as pit, valuation_worker
from app.config import Settings
from app.database import Database
from app.market_data.http import JsonHttpClient
from app.valuation_ensemble_grid import compute_grid_section
from app.valuation_ensemble_pin import PROTOCOL_CONSTANTS, instrument_file_hashes
from app.valuation_panel import _NoNetworkHttp
from app.valuation_price_history import PriceHistoryService
from app.valuation_worker import OffhoursPhase, run_worker_iteration
from app.valuation_worker_contract import VALUATION_WORKER_ADVISORY_PHASES, VALUATION_WORKER_OFFHOURS_PHASES, VALUATION_WORKER_PHASES
from tests import test_valuation_ensemble_grid as grid_tests
from tests.test_valuation_ensemble_grid import IMPLEMENTATION, _canonical_facts, _fixture
from tests.test_valuation_pit_rerun import (SECTOR, SYMBOLS, T, VINTAGE_AT, ScriptedHttp, _database, _publish_prices,
                                           _publish_sources, _sessions, _settings, _target)

BACKEND = Path(__file__).resolve().parents[1]
REPOSITORY = BACKEND.parents[1]
SIGNED_PIN = REPOSITORY / "c3po" / "ops" / "valuation-ensemble" / f"{live.SIGNED_INSTRUMENT_PIN}.json"


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    import http.client
    import socket

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("real network is forbidden in the live ensemble tests")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(http.client.HTTPSConnection, "connect", forbidden)


def _grid(fixture: tuple[Any, ...]) -> dict[str, Any]:
    database, prices, v3, served = fixture
    return compute_grid_section(database, market="NASDAQ", as_of=T, prices=prices, v3_snapshot=v3, served_snapshot=served,
                                implementation=IMPLEMENTATION, volume_basis="as_traded")


def _pinned_targets(database: Database, calls: list[str] | None = None, *, failing: set[str] | None = None):
    """The RAW rows the grid read (the FMP PIT source snapshots), served through the live reader's interface."""
    def read(market: str, symbol: str) -> list[dict[str, Any]]:
        if calls is not None:
            calls.append(symbol)
        if symbol in (failing or set()):
            raise RuntimeError("provider unavailable")
        snapshot = database.latest_analysis_snapshot(pit.SOURCE_ANALYSIS_TYPE, pit.source_entity_key(market, pit.PROVIDER_FMP, symbol))
        return list(snapshot["outputs"]["payload"]) if snapshot is not None else []
    return read


def _live(database: Database, *, targets=None, volume_basis: str | None = "as_traded") -> tuple[live.LiveInputs, dict[str, Any]]:
    """The live path at the grid's T with the grid's inputs: a NEW pin of the same publication, a NEW as-filed reader, the
    curve derived by curve_package_at from the pinned Treasury history and the pinned target rows."""
    prices = pit.PinnedPrices(PriceHistoryService(_settings(), database, _NoNetworkHttp()), "NASDAQ", as_of=T,
                              pinned_at=VINTAGE_AT + timedelta(seconds=1), pin_mode="explicit")
    history = database.latest_analysis_snapshot(pit.SOURCE_ANALYSIS_TYPE, pit.MACRO_TREASURY_KEY)["outputs"]["payload"]
    curve = pit.curve_package_at(history, as_of=T, economic_date=pit.economic_date_of("NASDAQ", T))
    assert curve is not None
    inputs = live.gather_live_inputs(database, market="NASDAQ", as_of=T, prices=prices, curve=curve, curve_reference={"origin": "fixture"},
                                     targets=targets or _pinned_targets(database), volume_basis=volume_basis)
    return inputs, live.compute_live_section(inputs)


def _grid_primary(record: dict[str, Any]) -> float | None:
    return record["variants"][live.PRIMARY]["value"]


def _assert_parity(grid: dict[str, Any], section: dict[str, Any]) -> None:
    grid_rows = {row["symbol"]: row for row in grid["records"]}
    live_rows = {row["symbol"]: row for row in section["records"]}
    assert list(live_rows) == list(grid_rows)
    for symbol, expected in grid_rows.items():
        got = live_rows[symbol]
        primary = _grid_primary(expected)
        assert got["primary_tp"] == primary and repr(got["primary_tp"]) == repr(primary), symbol  # the same float, bit for bit
        assert (got["origin"] == "ensemble") is (primary is not None) and (primary is None) is got["origin"].startswith("not_evaluable:")
        assert got["model_values"] == {model["model"]: model["value"] for model in expected["models"]}, symbol
        assert got["models_evaluated"] == sum(model["status"] == "evaluated" for model in expected["models"])
        if primary is not None:
            assert got["sample_size"] == expected["variants"][live.PRIMARY]["sample_size"]
            assert got["consensus"]["value"] == expected["consensus"]["value"]
            assert got["consensus"]["used"] is expected["variants"][live.PRIMARY]["consensus_included"]
        assert got["screened"] is expected["screened"]
        assert got["price"] == expected["price"] and got["session_date"] == expected["session_date"]


@pytest.fixture(scope="module")
def ready() -> tuple[Any, ...]:
    return _fixture()


def test_parity_with_the_signed_grid_section_is_exact_on_the_grid_fixture(ready: tuple[Any, ...]) -> None:
    grid = _grid(ready)
    inputs, section = _live(ready[0])
    # the live admission IS rev3's: the resolver's screen inputs equal the ones the grid's sibling run stored
    assert inputs.screen_inputs == ready[2]["outputs"]["screen"]
    _assert_parity(grid, section)
    primaries = [row["primary_tp"] for row in section["records"]]
    assert sum(value is not None for value in primaries) == len(SYMBOLS) and all(math.isfinite(v) for v in primaries if v is not None)
    assert all(row["consensus"]["used"] and row["consensus"]["value"] == pytest.approx(1300 / 3) for row in section["records"])
    assert section["counts"]["with_primary_tp"] == len(SYMBOLS) and section["counts"]["origins"] == {"ensemble": len(SYMBOLS)}
    assert section["counts"]["model_results"] == grid["ledger"]["model_results"]
    assert section["primary"] == live.PRIMARY == PROTOCOL_CONSTANTS["primary"] == json.loads(SIGNED_PIN.read_text())["constants"]["primary"]
    # the same inputs give the same hashes; the context names the clock, the publication and the producer's bytes
    assert [row["inputs_sha256"] for row in _live(ready[0])[1]["records"]] == [row["inputs_sha256"] for row in section["records"]]
    assert section["context"]["price_vintage"] == ready[1].manifest() and set(section["context"]["implementation"]) == set(live.IMPLEMENTATION_FILES)


@pytest.mark.parametrize("variant", [
    {"omit": {"us-gaap:InterestExpense"}},  # no reported interest: WACC models refuse
    {"omit_opening": True},  # no exact opening book: residual income refuses
    {"omit": {"us-gaap:DebtCurrent", "us-gaap:Goodwill"}},  # partial debt and intangibles
    {"etf": "CCC"},  # an ETF row: never a stock, never a TP; one fewer peer
])
def test_parity_holds_when_inputs_are_missing(variant: dict[str, Any]) -> None:
    fixture = _fixture(**variant)
    grid = _grid(fixture)
    _, section = _live(fixture[0])
    _assert_parity(grid, section)
    if "etf" in variant:
        row = next(row for row in section["records"] if row["symbol"] == variant["etf"])
        assert row["primary_tp"] is None and row["origin"] == "not_evaluable:not_a_stock" and row["models_evaluated"] == 0


def _factor_bars() -> dict[str, list[dict[str, Any]]]:
    """One common factor with loadings 0.6…1.4 plus small idiosyncratic moves: recomputed betas inside (0.27, 2.09), so
    clamp(r5y + β·0.055, 0.06, 0.16) is NOT clamped and the curve and the beta reach every DCF/DDM/RI value."""
    sessions = _sessions("2023-06-01", "2026-09-10")
    bars: dict[str, list[dict[str, Any]]] = {}
    for index, symbol in enumerate(SYMBOLS):
        loading, level, rows = 0.6 + 0.16 * index, 0.0, []
        for i, session in enumerate(sessions):
            level += loading * (0.01 * math.sin(i * 0.7) + 0.004 * math.cos(i * 1.3)) + 0.002 * math.sin(i * (index + 2) * 0.37)
            close = round((100.0 + 10 * index) * math.exp(level), 4)
            rows.append({"date": session.isoformat(), "close": close, "adjusted_close": close, "volume": 1000.0})
        bars[f"{symbol}.US"] = rows
    return bars


def test_parity_holds_on_the_capm_path_where_the_curve_and_the_beta_move_the_tp(monkeypatch: pytest.MonkeyPatch) -> None:
    # the grid fixture's betas (2–3) clamp every cost of equity at 0.16: here they do not, so a different beta, rate or proxy
    # in the live path would show in the floats
    original = grid_tests._publish_prices
    monkeypatch.setattr(grid_tests, "_publish_prices", lambda database: original(database, bars=_factor_bars()))
    fixture = _fixture()
    grid = _grid(fixture)
    inputs, section = _live(fixture[0])
    betas = [inputs.prices.beta(symbol)[0] for symbol in SYMBOLS]
    assert all(beta is not None and 0.27 < beta < 2.09 for beta in betas)
    _assert_parity(grid, section)
    assert all(row["primary_tp"] is not None for row in section["records"])


def test_a_name_without_inputs_or_targets_gets_a_reason_never_a_number() -> None:
    fixture = _fixture()
    database = fixture[0]
    grid = _grid(fixture)
    # a later catalogue adds a stock the as-filed store does not cover and the publication does not price
    database.save_analysis_snapshot("valuation_universe", "NASDAQ_UNIVERSE", "mv-cat", {"methodology_version": 7},
                                    {"rows": [{"symbol": s, "sector": SECTOR, "industry": "Machinery", "valuation_profile": "general",
                                               "security_type": "Stock"} for s in (*SYMBOLS, "ZZZ")]}, VINTAGE_AT)
    calls: list[str] = []
    _, section = _live(database, targets=_pinned_targets(database, calls, failing={"BBB"}))
    rows = {row["symbol"]: row for row in section["records"]}
    assert rows["ZZZ"]["primary_tp"] is None and rows["ZZZ"]["origin"] == "not_evaluable:not_admitted_at_T:statement_vintages_missing"
    assert rows["ZZZ"]["consensus"]["reason"] == "not_fetched:company_not_evaluable" and "ZZZ" not in calls  # no read for a hopeless name
    # a provider failure refuses the name: never a TP computed without the consensus it could not read
    assert rows["BBB"]["primary_tp"] is None and rows["BBB"]["origin"] == "not_evaluable:targets_fetch_failed:RuntimeError"
    assert rows["BBB"]["models_evaluated"] >= 3  # the models ran; the number is withheld
    # every other name is the grid's number: the extra name is no peer and the failed read moves no one else
    for row in grid["records"]:
        if row["symbol"] != "BBB":
            assert rows[row["symbol"]]["primary_tp"] == _grid_primary(row)
    counts = json.dumps(section["counts"])
    assert not any(f'"{symbol}"' in counts for symbol in (*SYMBOLS, "ZZZ"))  # aggregates hold reasons and counts, never a name
    assert section["counts"]["origins"]["not_evaluable:targets_fetch_failed:RuntimeError"] == 1


def test_a_market_without_a_curve_or_with_a_foreign_pin_is_refused_before_any_name(ready: tuple[Any, ...]) -> None:
    database, prices = ready[0], ready[1]
    for curve in ({}, {"interpolated_5y_rate": None}):
        with pytest.raises(live.LiveEnsembleError, match="treasury_curve_unavailable"):
            live.gather_live_inputs(database, market="NASDAQ", as_of=T, prices=prices, curve=curve, curve_reference={},
                                    targets=_pinned_targets(database), volume_basis="as_traded")
    with pytest.raises(live.LiveEnsembleError, match="price_pin_not_of_this_section"):
        live.gather_live_inputs(database, market="NASDAQ", as_of=T + timedelta(days=1), prices=prices, curve={"interpolated_5y_rate": 0.04},
                                curve_reference={}, targets=_pinned_targets(database), volume_basis="as_traded")
    with pytest.raises(live.LiveEnsembleError, match="catalogue_missing"):
        empty = _database()
        _publish_prices(empty)
        pinned = pit.PinnedPrices(PriceHistoryService(_settings(), empty, _NoNetworkHttp()), "NASDAQ", as_of=T,
                                  pinned_at=VINTAGE_AT + timedelta(seconds=1), pin_mode="explicit")
        _canonical_facts(empty)
        live.gather_live_inputs(empty, market="NASDAQ", as_of=T, prices=pinned, curve={"interpolated_5y_rate": 0.04}, curve_reference={},
                                targets=_pinned_targets(empty), volume_basis=None)


def test_an_undetermined_volume_basis_leaves_screened_unknown_and_every_tp_unchanged(ready: tuple[Any, ...]) -> None:
    _, decided = _live(ready[0])
    _, unknown = _live(ready[0], volume_basis=None)
    assert all(row["screened"] is None for row in unknown["records"]) and unknown["counts"]["screened"] is None
    assert [row["primary_tp"] for row in unknown["records"]] == [row["primary_tp"] for row in decided["records"]]


# ------------------------------------------------------------------ the nightly run: live fetches in memory, one snapshot per market
CLOCK = VINTAGE_AT + timedelta(minutes=1)  # 03:01Z on 2026-09-11: the session of the clock is 2026-09-10, the publication's last


def _live_world() -> tuple[Database, ScriptedHttp]:
    database = _database()
    _publish_prices(database)
    _publish_sources(database, poison=True)
    _canonical_facts(database)

    def targets(params: dict[str, Any]) -> list[dict[str, Any]]:
        if params.get("page"):
            return []
        return [_target(house, CLOCK - timedelta(days=10), value) for house, value in (("A", 100), ("B", 200), ("C", 1000))]

    def gbond(rate: float):
        def rows(params: dict[str, Any]) -> list[dict[str, Any]]:
            return [{"date": day, "close": rate, "adjusted_close": rate, "volume": 0} for day in ("2026-09-08", "2026-09-09", "2026-09-10")]
        return rows

    http = ScriptedHttp({"/stable/price-target-news": targets, "/api/eod/US3Y.GBOND": gbond(3.9), "/api/eod/US10Y.GBOND": gbond(4.3)})
    return database, http


def _on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(valuation_env.ENSEMBLE_LIVE_ENV, "true")


def test_the_nightly_run_publishes_one_snapshot_per_market_from_live_reads_and_writes_no_pit_source(
        monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    _on(monkeypatch)
    database, http = _live_world()
    sources_before = sum(s["analysis_type"] == pit.SOURCE_ANALYSIS_TYPE for s in database._analysis_snapshots)
    with caplog.at_level(logging.INFO):
        summary = live.run_nightly(database, _settings(), cast(JsonHttpClient, http), clock=lambda: CLOCK, markets=("NASDAQ",))
    assert summary["published"] == 1 and summary["with_primary_tp"] == len(SYMBOLS) and summary["failures"] == {}
    assert summary["provider_reads"] == {"eodhd": 1, "fmp": len(SYMBOLS)}
    snapshot = database.latest_analysis_snapshot(live.ANALYSIS_TYPE, "NASDAQ_UNIVERSE")
    assert snapshot is not None and snapshot["outputs"]["as_of"] == CLOCK.isoformat()
    records = snapshot["outputs"]["records"]
    assert [row["symbol"] for row in records] == sorted(SYMBOLS) and all(row["origin"] == "ensemble" for row in records)
    assert all(row["as_of"] == CLOCK.isoformat() and row["session_date"] == "2026-09-10" and len(row["inputs_sha256"]) == 64 for row in records)
    assert snapshot["outputs"]["context"]["curve"]["origin"] == "live_fetch:" + pit.MACRO_TREASURY_KEY
    assert snapshot["outputs"]["volume_check"]["decision"] == "undetermined" and all(row["screened"] is None for row in records)
    assert snapshot["outputs"]["governance"]["served"] is False
    # the fetches stayed in memory: the signed grid's pinned sources are untouched
    assert sum(s["analysis_type"] == pit.SOURCE_ANALYSIS_TYPE for s in database._analysis_snapshots) == sources_before
    assert {url.split("?")[0].rsplit("/", 1)[-1] for url in http.calls} <= {"price-target-news", "US3Y.GBOND", "US10Y.GBOND"}
    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "Valuation ensemble live: pending=1 published=1" in text and not any(symbol in text for symbol in SYMBOLS)
    # nothing official: the analysis type is not a producer cycle
    assert not database.valuation_predictions_for_cycle(str(snapshot["id"]), source="official_internal_v1")
    # a retry inside the night skips the exchange already published: no read at all
    calls = len(http.calls)
    again = live.run_nightly(database, _settings(), cast(JsonHttpClient, http), clock=lambda: CLOCK + timedelta(minutes=30),
                             since=CLOCK, markets=("NASDAQ",))
    assert again["markets_pending"] == 0 and again["published"] == 0 and len(http.calls) == calls


def test_one_market_failing_never_blocks_the_other_and_the_night_stays_due(monkeypatch: pytest.MonkeyPatch,
                                                                           caplog: pytest.LogCaptureFixture) -> None:
    _on(monkeypatch)
    database, http = _live_world()  # NYSE has neither a price publication nor a catalogue
    with caplog.at_level(logging.INFO), pytest.raises(live.LiveEnsembleError, match=r"^markets_not_published:1$"):
        live.run_nightly(database, _settings(), cast(JsonHttpClient, http), clock=lambda: CLOCK)
    assert database.latest_analysis_snapshot(live.ANALYSIS_TYPE, "NASDAQ_UNIVERSE") is not None
    assert database.latest_analysis_snapshot(live.ANALYSIS_TYPE, "NYSE_UNIVERSE") is None
    assert live.last_run_at(database) is None  # the night is not done until both exchanges have their snapshot
    assert "failures={'price_vintage:PitRerunInputError': 1}" in "\n".join(r.getMessage() for r in caplog.records)
    # a Treasury outage refuses both exchanges: no rate is guessed
    database, http = _live_world()
    http.answers = {key: value for key, value in http.answers.items() if "GBOND" not in key}
    with pytest.raises(live.LiveEnsembleError, match=r"^markets_not_published:1$"):
        live.run_nightly(database, _settings(), cast(JsonHttpClient, http), clock=lambda: CLOCK, markets=("NASDAQ",))
    assert database.latest_analysis_snapshot(live.ANALYSIS_TYPE, "NASDAQ_UNIVERSE") is None


def test_switch_off_nothing_is_read_fetched_or_written(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(valuation_env.ENSEMBLE_LIVE_ENV, raising=False)

    class Exploding:
        def __getattr__(self, name: str) -> Any:
            raise AssertionError("touched while the switch is off: " + name)

    assert valuation_env.ensemble_live_enabled() is False
    assert live.run_nightly(cast(Database, Exploding()), cast(Settings, Exploding()), cast(JsonHttpClient, Exploding()),
                            clock=lambda: (_ for _ in ()).throw(AssertionError("clock read while off"))) == {"enabled": False}
    for raw in ("true", "TRUE", " True ", "1", "yes", "on"):
        monkeypatch.setenv(valuation_env.ENSEMBLE_LIVE_ENV, raw)
        assert valuation_env.ensemble_live_enabled() is True, raw
    for raw in ("", "false", "0", "no", "off", "enabled"):
        monkeypatch.setenv(valuation_env.ENSEMBLE_LIVE_ENV, raw)
        assert valuation_env.ensemble_live_enabled() is False, raw
    assert valuation_env.ENSEMBLE_LIVE_ENV in valuation_env.ENVIRONMENT_NAMES and "ensemble_live" not in Settings.model_fields
    monkeypatch.delenv(valuation_env.ENSEMBLE_LIVE_ENV, raising=False)
    assert valuation_worker.run_ensemble_live(cast(Database, Exploding()), cast(Settings, Exploding()),
                                              cast(JsonHttpClient, Exploding())) == {"enabled": False}
    # the worker never even loads the producer unless the switch schedules its phase
    loaded = subprocess.run([sys.executable, "-c", "import sys, app.valuation_worker; print('app.valuation_live_ensemble' in sys.modules)"],
                            cwd=BACKEND, capture_output=True, text=True, check=True, env={**os.environ, valuation_env.ENSEMBLE_LIVE_ENV: ""})
    assert loaded.stdout.strip() == "False"
    # the worker schedules the phase only when switched on, after the price series and after every existing phase
    source = (BACKEND / "app" / "valuation_worker.py").read_text(encoding="utf-8")
    phases = source[source.index("offhours_phases = ("):source.index("while True:")]
    at = phases.index('OffhoursPhase("ensemble_live"')
    assert at > max(phases.index('"price_history"'), phases.index('OffhoursPhase("decisor_shadow"'), phases.index("CASH_YIELD_PHASE_KEY"))
    assert "if valuation_env.ensemble_live_enabled() else ()" in phases[at:]
    assert VALUATION_WORKER_PHASES["ensemble_live"]["code"] == "valuation-worker-ensemble-live"
    assert "ensemble_live" in VALUATION_WORKER_ADVISORY_PHASES and "ensemble_live" not in VALUATION_WORKER_OFFHOURS_PHASES


def test_the_health_card_expects_the_phase_only_when_on_and_never_goes_offline_for_it(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.test_system_health import _service

    now = datetime.now(timezone.utc)
    states = {definition["code"]: {"last_status": "succeeded", "started_at": now, "completed_at": now, "last_success_at": now, "last_error": None,
                                   "metadata": {"phase": phase}}
              for phase, definition in VALUATION_WORKER_PHASES.items() if phase != "ensemble_live"}
    service = _service(valuation_phase_states=states)
    monkeypatch.delenv(valuation_env.ENSEMBLE_LIVE_ENV, raising=False)
    monkeypatch.setenv(valuation_env.DECISOR_SHADOW_ENV, "true")
    monkeypatch.setenv(valuation_env.EARNINGS_CALENDAR_ENV, "true")
    dormant = service._valuation_worker_phase_health(now)
    assert dormant.status == "healthy" and "ensemble_live" not in (dormant.detail or "")
    _on(monkeypatch)
    missing = service._valuation_worker_phase_health(now)
    assert missing.status == "attention" and "Advisory · ensemble_live: not run yet" in (missing.detail or "")


def test_a_failing_live_phase_never_breaks_another_phase_nor_pages(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    _on(monkeypatch)
    database, http = _live_world()
    local = datetime(2026, 9, 11, 1, 30, tzinfo=ZoneInfo("America/Sao_Paulo"))
    ran: list[str] = []
    pushes: list[Any] = []

    class _Push:
        def notify(self, **kwargs: Any) -> None:
            pushes.append(kwargs)

    phases = (
        OffhoursPhase("ensemble_live", lambda: live.last_run_at(database),
                      lambda: live.run_nightly(database, _settings(), cast(JsonHttpClient, http), clock=lambda: CLOCK)),  # NYSE is missing
        OffhoursPhase("v3_shadow", lambda: None, lambda: ran.append("v3_shadow") or {"rows": 1}),
    )
    with caplog.at_level(logging.INFO):
        result = run_worker_iteration(database, now=local, canonical_due=False, canonical_operation=lambda: None, offhours_phases=phases,
                                      push_notifications=cast(Any, _Push()))
    assert result.phase_statuses == {"ensemble_live": "failed", "v3_shadow": "succeeded"} and ran == ["v3_shadow"] and pushes == []
    run = next(r for r in database._ingestion_runs.values() if r["source_code"] == VALUATION_WORKER_PHASES["ensemble_live"]["code"])
    assert run["status"] == "failed" and run["error_summary"] == "LiveEnsembleError: markets_not_published:1"  # a count, never a name
    assert result.next_wake_at == local + timedelta(minutes=30)  # retried inside the window, the published exchange skipped then
    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "failed (advisory, not paged): LiveEnsembleError" in text and not any(symbol in text for symbol in SYMBOLS)


def test_the_live_producer_is_outside_the_signed_instrument_and_leaves_its_bytes_untouched() -> None:
    files = json.loads(SIGNED_PIN.read_text(encoding="utf-8"))["files"]
    assert "c3po/backend/app/valuation_live_ensemble.py" not in files
    assert "c3po/backend/app/valuation_live_ensemble.py" not in instrument_file_hashes(REPOSITORY)
    for path, digest in files.items():  # every signed instrument file is byte-identical to the owner-signed pin
        assert hashlib.sha256((REPOSITORY / path).read_bytes()).hexdigest() == digest, path
    assert not any(name.startswith("valuation_ensemble_") for name in live.__name__.split("."))  # outside the pin's glob
