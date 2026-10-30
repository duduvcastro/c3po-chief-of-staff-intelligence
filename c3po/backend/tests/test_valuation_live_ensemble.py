"""The nightly LIVE producer of the ensemble's primary target price (``app/valuation_live_ensemble.py``).

The parity tests are the point: on the signed grid's own fixture (``tests/test_valuation_ensemble_grid._fixture``, the real
canonical readers over synthetic memory), the live computation fed the SAME inputs the grid read — a fresh pin of the same
price publication, a fresh as-filed reader, the pinned Treasury history and the pinned target rows — returns, name by name,
EXACTLY the floats ``compute_grid_section`` returns (primary, every model value, sample size, consensus, screen flag),
also when listed-only names are added to the population. Then: fail closed per name, the provider breaker, the wall-clock
deadline with tested names first, the uncapped population, off by default, isolated in the worker (never ahead of the
decisor, a retry cap and a last start), counts-only logs, no PIT source written.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest

from app import valuation_env, valuation_live_ensemble as live, valuation_pit_backtest_report as backtest
from app import valuation_pit_rerun as pit, valuation_price_history as series, valuation_worker
from app.config import Settings
from app.database import Database
from app.market_data.eodhd import EodhdClient
from app.market_data.http import JsonHttpClient, MarketDataRequestError
from app.valuation_ensemble_grid import compute_grid_section
from app.valuation_ensemble_inputs import canonical_hash
from app.valuation_ensemble_pin import PROTOCOL_CONSTANTS, instrument_file_hashes
from app.valuation_panel import _NoNetworkHttp
from app.valuation_price_history import PriceHistoryService
from app.valuation_worker import OffhoursPhase, run_worker_iteration
from app.valuation_worker_contract import VALUATION_WORKER_ADVISORY_PHASES, VALUATION_WORKER_OFFHOURS_PHASES, VALUATION_WORKER_PHASES
from tests import test_valuation_ensemble_grid as grid_tests
from tests.test_valuation_ensemble_grid import IMPLEMENTATION, _canonical_facts, _fixture
from tests.test_valuation_pit_rerun import (SECTOR, SYMBOLS, T, VINTAGE_AT, ScriptedHttp, _bars_for, _database, _publish_prices,
                                           _publish_sources, _sessions, _settings, _target)

BACKEND = Path(__file__).resolve().parents[1]
REPOSITORY = BACKEND.parents[1]
SIGNED_PIN = REPOSITORY / "c3po" / "ops" / "valuation-ensemble" / f"{live.SIGNED_INSTRUMENT_PIN}.json"
SAO_PAULO = ZoneInfo("America/Sao_Paulo")


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


def _pinned_targets(database: Database, calls: list[tuple[str, int | None]] | None = None, *, failing: set[str] | None = None,
                    advance: list[int] | None = None):
    """The RAW rows the grid read (the FMP PIT source snapshots), served through the live reader's interface."""
    def read(market: str, symbol: str, *, pages: int | None = None) -> list[dict[str, Any]]:
        if calls is not None:
            calls.append((symbol, pages))
        if advance is not None:
            advance[0] += 1
        if symbol in (failing or set()):
            raise RuntimeError("provider unavailable")
        snapshot = database.latest_analysis_snapshot(pit.SOURCE_ANALYSIS_TYPE, pit.source_entity_key(market, pit.PROVIDER_FMP, symbol))
        return list(snapshot["outputs"]["payload"]) if snapshot is not None else []
    return read


def _inputs(database: Database, *, targets=None, volume_basis: str | None = "as_traded", listed: bool = True) -> live.LiveInputs:
    """The live path at the grid's T with the grid's inputs: a NEW pin of the same publication, a NEW as-filed reader, the
    curve derived by curve_package_at from the pinned Treasury history and the pinned target rows."""
    prices = pit.PinnedPrices(PriceHistoryService(_settings(), database, _NoNetworkHttp()), "NASDAQ", as_of=T,
                              pinned_at=VINTAGE_AT + timedelta(seconds=1), pin_mode="explicit")
    snapshot = database.latest_analysis_snapshot(pit.SOURCE_ANALYSIS_TYPE, pit.MACRO_TREASURY_KEY)
    assert snapshot is not None
    curve = pit.curve_package_at(snapshot["outputs"]["payload"], as_of=T, economic_date=pit.economic_date_of("NASDAQ", T))
    assert curve is not None
    return live.gather_live_inputs(database, market="NASDAQ", as_of=T, prices=prices, curve=curve, curve_reference={"origin": "fixture"},
                                   targets=targets or _pinned_targets(database), volume_basis=volume_basis, listed=listed)


def _live(database: Database, **kwargs: Any) -> tuple[live.LiveInputs, dict[str, Any]]:
    inputs = _inputs(database, **kwargs)
    return inputs, live.compute_live_section(inputs)


def _grid_primary(record: dict[str, Any]) -> float | None:
    return record["variants"][live.PRIMARY]["value"]


def _assert_parity(grid: dict[str, Any], section: dict[str, Any]) -> None:
    grid_rows = {row["symbol"]: row for row in grid["records"]}
    live_rows = {row["symbol"]: row for row in section["records"] if row["in_served_catalogue"]}
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
        assert got["screened"] is expected["screened"] and got["pit_tested"] is expected["screened"]
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
    assert section["counts"]["model_results"] == grid["ledger"]["model_results"] and section["complete"] is True
    assert section["primary"] == live.PRIMARY == PROTOCOL_CONSTANTS["primary"] == json.loads(SIGNED_PIN.read_text())["constants"]["primary"]
    # the same inputs give the same hashes; the context names the clock, the publication and the producer's bytes
    assert [row["inputs_sha256"] for row in _live(ready[0])[1]["records"]] == [row["inputs_sha256"] for row in section["records"]]
    assert section["context"]["price_vintage"] == ready[1].manifest() and set(section["context"]["implementation"]) == set(live.IMPLEMENTATION_FILES)
    assert {"valuation_official.py", "valuation_pit_grid.py", "market_data/eodhd.py", "valuation_panel.py"} <= set(live.IMPLEMENTATION_FILES)


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


def _factor_bars(symbols: tuple[str, ...] = SYMBOLS) -> dict[str, list[dict[str, Any]]]:
    """One common factor with loadings 0.6…1.4 plus small idiosyncratic moves: recomputed betas inside (0.27, 2.09), so
    clamp(r5y + β·0.055, 0.06, 0.16) is NOT clamped and the curve and the beta reach every DCF/DDM/RI value."""
    sessions = _sessions("2023-06-01", "2026-09-10")
    bars: dict[str, list[dict[str, Any]]] = {}
    for index, symbol in enumerate(symbols):
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


def test_parity_holds_at_the_edges_of_the_consensus_window(monkeypatch: pytest.MonkeyPatch) -> None:
    # (T − 90 d, T]: T − 89 d and T itself count, T − 90 d, T − 91 d and anything after T never do; the latest row of a house
    # wins; a target in another currency is refused; fewer than three houses leaves the TP on the models alone
    day = timedelta(days=1)
    rich = [_target("A", T - 89 * day, 120), _target("B", T - 91 * day, 900), _target("C", T + timedelta(hours=1), 5000),
            _target("D", T - 60 * day, 999), _target("D", T - 30 * day, 150), _target("E", T - 90 * day, 777), _target("F", T, 180),
            _target("G", T - 5 * day, 3000, currency="EUR")]
    thin = [_target("A", T - 89 * day, 120), _target("B", T - 91 * day, 900), _target("C", T + day, 5000), _target("D", T - 2 * day, 140)]
    window = {symbol: (rich if index < 3 else thin) for index, symbol in enumerate(SYMBOLS)}
    original = grid_tests._publish_sources
    monkeypatch.setattr(grid_tests, "_publish_sources",
                        lambda database, *, targets=None, poison=False, **kw: original(database, targets=window, poison=poison, **kw))
    fixture = _fixture()
    grid = _grid(fixture)
    _, section = _live(fixture[0])
    _assert_parity(grid, section)
    rows = {row["symbol"]: row for row in section["records"]}
    grid_rows = {row["symbol"]: row for row in grid["records"]}
    for symbol in SYMBOLS[:3]:
        assert rows[symbol]["consensus"]["value"] == grid_rows[symbol]["consensus"]["value"] == 150.0  # mean of A 120, D 150, F 180
        assert rows[symbol]["consensus"]["analyst_count"] == 3 and rows[symbol]["consensus"]["used"] is True
    for symbol in SYMBOLS[3:]:
        assert rows[symbol]["consensus"]["reason"] == grid_rows[symbol]["consensus"]["reason"] == "houses_below_minimum"
        assert rows[symbol]["consensus"]["used"] is False and rows[symbol]["primary_tp"] is not None


def test_a_name_without_inputs_or_targets_gets_a_reason_never_a_number() -> None:
    fixture = _fixture()
    database = fixture[0]
    grid = _grid(fixture)
    # a later catalogue adds a stock the as-filed store does not cover and the publication does not price
    database.save_analysis_snapshot("valuation_universe", "NASDAQ_UNIVERSE", "mv-cat", {"methodology_version": 7},
                                    {"rows": [{"symbol": s, "sector": SECTOR, "industry": "Machinery", "valuation_profile": "general",
                                               "security_type": "Stock"} for s in (*SYMBOLS, "ZZZ")]}, VINTAGE_AT)
    calls: list[tuple[str, int | None]] = []
    _, section = _live(database, targets=_pinned_targets(database, calls, failing={"BBB"}))
    rows = {row["symbol"]: row for row in section["records"]}
    assert rows["ZZZ"]["primary_tp"] is None and rows["ZZZ"]["origin"] == "not_evaluable:not_admitted_at_T:statement_vintages_missing"
    assert rows["ZZZ"]["consensus"]["reason"] == "not_fetched:company_not_evaluable" and "ZZZ" not in [s for s, _ in calls]
    # a provider failure refuses the name: never a TP computed without the consensus it could not read
    assert rows["BBB"]["primary_tp"] is None and rows["BBB"]["origin"] == "not_evaluable:targets_fetch_failed:RuntimeError"
    assert rows["BBB"]["consensus"]["reason"] == "targets_fetch_failed:RuntimeError" and rows["BBB"]["models_evaluated"] >= 3
    # every other name is the grid's number: the extra name is no peer and the failed read moves no one else
    for row in grid["records"]:
        if row["symbol"] != "BBB":
            assert rows[row["symbol"]]["primary_tp"] == _grid_primary(row)
    counts = json.dumps(section["counts"])
    assert not any(f'"{symbol}"' in counts for symbol in (*SYMBOLS, "ZZZ"))  # aggregates hold reasons and counts, never a name
    assert section["counts"]["origins"]["not_evaluable:targets_fetch_failed:RuntimeError"] == 1
    assert section["counts"]["targets"] == {"attempted": len(SYMBOLS), "failed": 1, "circuit_open": False}
    # one failure in six is above the 10 % tolerance: the section would not be published tonight
    assert live.unpublishable(section) == "targets_failed_share"


def test_a_name_whose_aggregation_refuses_keeps_its_consensus_label(ready: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise live.NotEvaluable("model_value_not_positive")

    monkeypatch.setattr(live, "aggregate_grid_variants", refuse)
    _, section = _live(ready[0])
    row = section["records"][0]
    assert row["origin"] == "not_evaluable:consensus_or_aggregation:model_value_not_positive"
    assert row["consensus"]["value"] == pytest.approx(1300 / 3) and row["consensus"]["reason"] == "aggregation_refused"


def test_a_market_without_a_curve_or_with_a_foreign_pin_is_refused_before_any_name(ready: tuple[Any, ...]) -> None:
    database, prices = ready[0], ready[1]
    for curve in ({}, {"interpolated_5y_rate": None}):
        with pytest.raises(live.LiveEnsembleError, match="treasury_curve_unavailable"):
            live.gather_live_inputs(database, market="NASDAQ", as_of=T, prices=prices, curve=curve, curve_reference={},
                                    targets=_pinned_targets(database), volume_basis="as_traded")
    with pytest.raises(live.LiveEnsembleError, match="price_pin_not_of_this_section"):
        live.gather_live_inputs(database, market="NASDAQ", as_of=T + timedelta(days=1), prices=prices, curve={"interpolated_5y_rate": 0.04},
                                curve_reference={}, targets=_pinned_targets(database), volume_basis="as_traded")
    empty = _database()
    _publish_prices(empty)
    pinned = pit.PinnedPrices(PriceHistoryService(_settings(), empty, _NoNetworkHttp()), "NASDAQ", as_of=T,
                              pinned_at=VINTAGE_AT + timedelta(seconds=1), pin_mode="explicit")
    _canonical_facts(empty)
    with pytest.raises(live.LiveEnsembleError, match="catalogue_missing"):
        live.gather_live_inputs(empty, market="NASDAQ", as_of=T, prices=pinned, curve={"interpolated_5y_rate": 0.04}, curve_reference={},
                                targets=_pinned_targets(empty), volume_basis=None)


def test_an_undetermined_volume_basis_keeps_every_tp_and_tests_only_names_kept_under_both_bases(ready: tuple[Any, ...]) -> None:
    _, decided = _live(ready[0])
    _, unknown = _live(ready[0], volume_basis=None)
    assert all(row["screened"] is None for row in unknown["records"]) and unknown["counts"]["screened"] is None
    assert [row["primary_tp"] for row in unknown["records"]] == [row["primary_tp"] for row in decided["records"]]
    assert unknown["context"]["pit_tested_rule"] == "screen:both_bases" and decided["context"]["pit_tested_rule"] == "screen:as_traded"


# ------------------------------------------------------------------ the population: every US common stock, tested names flagged
def _listed(database: Database, symbols: tuple[str, ...], *, market: str = "NASDAQ", tamper: bool = False,
            at: datetime = VINTAGE_AT) -> None:
    listings = [{"market": market, "symbol": symbol, "name": symbol + " Inc", "security_type": "Stock", "listing_class": "equity",
                 "isin": None, "attributes": {}} for symbol in symbols]
    listings.append({"market": market, "symbol": "ETFX", "name": "An ETF", "security_type": "ETF", "listing_class": "fund", "isin": None,
                     "attributes": {}})
    outputs: dict[str, Any] = {"schema": live.LISTED_SCHEMA, "market": market, "source_url": "official", "listings": listings}
    outputs["manifest_sha256"] = canonical_hash(outputs)
    if tamper:
        outputs["listings"] = outputs["listings"][:-2]
    database.save_analysis_snapshot(live.LISTED_ANALYSIS, market, "mv-listed", {}, outputs, at)


def _wide_world() -> Database:
    """The grid fixture's six served names plus GGG (priced and filed like them, listed, not served) and PPP (priced, never
    filed); ZZZ, when listed, has neither."""
    wide = (*SYMBOLS, "GGG", "PPP")
    sessions = _sessions("2023-06-01", "2026-09-10")
    database = _database()
    _publish_prices(database, bars={f"{s}.US": _bars_for(s, sessions, base=100.0 + 10 * i) for i, s in enumerate(wide)})
    _publish_sources(database, poison=True, targets={s: [_target(h, T - timedelta(days=10), v) for h, v in (("A", 100), ("B", 200), ("C", 1000))]
                                                    for s in SYMBOLS})
    return database


def test_the_population_is_every_listed_common_stock_and_adding_it_moves_no_tested_number(monkeypatch: pytest.MonkeyPatch) -> None:
    database = _wide_world()
    with monkeypatch.context() as scoped:  # canonical facts for GGG too (it is filed like the others)
        scoped.setattr(grid_tests, "SYMBOLS", (*SYMBOLS, "GGG"))
        _canonical_facts(database)
    _, served_only = _live(database, listed=False)
    _listed(database, (*SYMBOLS, "GGG", "PPP", "ZZZ"))
    calls: list[tuple[str, int | None]] = []
    inputs, wide = _live(database, targets=_pinned_targets(database, calls))
    assert [row["symbol"] for row in inputs.extra_rows] == ["GGG", "PPP", "ZZZ"] and inputs.listed_reference["status"] == "read"
    rows = {row["symbol"]: row for row in wide["records"]}
    assert set(rows) == {*SYMBOLS, "GGG", "PPP", "ZZZ"} and "ETFX" not in rows  # every common stock, no ETF from the listing
    for row in served_only["records"]:  # the served names keep the grid's proxy and peers: identical numbers
        assert {k: v for k, v in rows[row["symbol"]].items() if k != "inputs_sha256"} == {k: v for k, v in row.items() if k != "inputs_sha256"}
    ggg = rows["GGG"]
    assert ggg["in_served_catalogue"] is False and ggg["pit_tested"] is False and ggg["primary_tp"] is not None and ggg["origin"] == "ensemble"
    assert ggg["model_values"]["pe"] is None  # no classification in a listing: the peer models refuse, the intrinsic ones value it
    # a listed-only name says which coverage it lacks, and each section counts them
    assert rows["ZZZ"]["origin"] == "not_evaluable:no_price_history" and rows["ZZZ"]["pit_tested"] is False
    assert rows["PPP"]["origin"] == "not_evaluable:no_asfiled_statements"
    assert wide["counts"]["listed_only_coverage"] == {"names": 3, "no_price_history": 1, "no_asfiled_statements": 1, "admitted": 1,
                                                      "evaluable": 1, "chunks_failed": 0}
    assert ("GGG", live.EXTRA_TARGET_PAGES) in calls and all(pages is None for symbol, pages in calls if symbol != "GGG")
    assert wide["counts"]["population_rows"] == len(SYMBOLS) + 3 and wide["counts"]["listed_only_stocks"] == 3
    assert "GGG" not in inputs.prices._bars and set(SYMBOLS) <= set(inputs.prices._bars)  # the chunk's series were dropped
    # a listing whose manifest does not verify adds nothing
    _listed(database, (*SYMBOLS, "GGG", "PPP", "ZZZ", "YYY"), tamper=True, at=VINTAGE_AT + timedelta(minutes=1))
    tampered = _inputs(database)
    assert tampered.extra_rows == [] and tampered.listed_reference["status"] == "refused_manifest"


def test_a_target_history_that_fills_the_page_cap_is_refused_for_a_listed_only_name(monkeypatch: pytest.MonkeyPatch) -> None:
    database = _wide_world()
    with monkeypatch.context() as scoped:
        scoped.setattr(grid_tests, "SYMBOLS", (*SYMBOLS, "GGG"))
        _canonical_facts(database)
    _listed(database, (*SYMBOLS, "GGG"))
    base = _pinned_targets(database)

    def full(market: str, symbol: str, *, pages: int | None = None) -> list[dict[str, Any]]:
        if symbol == "GGG":
            return [_target(f"H{i}", T - timedelta(days=200), 10.0) for i in range(live.EXTRA_TARGET_PAGES * live.TARGET_PAGE_LIMIT)]
        return base(market, symbol, pages=pages)

    _, section = _live(database, targets=full)
    ggg = next(row for row in section["records"] if row["symbol"] == "GGG")
    assert ggg["primary_tp"] is None and ggg["origin"] == "not_evaluable:targets_history_beyond_page_cap"


@pytest.fixture
def _two_tested(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fixture's names are tiny (10 shares): open the screen's floors and keep the TWO most liquid as the tested ones."""
    monkeypatch.setattr(backtest, "SCREEN_MIN_MARKET_CAP", 0.0)
    monkeypatch.setattr(backtest, "SCREEN_MIN_DOLLAR_VOLUME", 0.0)
    monkeypatch.setattr(backtest, "SCREEN_TOP_PER_EXCHANGE", 2)


@pytest.mark.usefixtures("_two_tested")
def test_under_a_deadline_the_tested_names_are_read_first_and_the_rest_stays_pending(ready: tuple[Any, ...]) -> None:
    database = ready[0]
    calls: list[tuple[str, int | None]] = []
    advance = [0]
    start = datetime(2026, 9, 11, 7, 0, tzinfo=timezone.utc)
    inputs = _inputs(database, targets=_pinned_targets(database, calls, advance=advance))
    section = live.compute_live_section(inputs, deadline=start + timedelta(minutes=2, seconds=30),
                                        clock=lambda: start + timedelta(minutes=advance[0]))
    rows = {row["symbol"]: row for row in section["records"]}
    tested = {symbol for symbol, row in rows.items() if row["pit_tested"]}
    assert tested == {"EEE", "FFF"}  # the two highest closes × the same volume
    assert [symbol for symbol, _ in calls][:2] in (["FFF", "EEE"], ["EEE", "FFF"]) and len(calls) == 3  # tested first, then by liquidity
    assert calls[2][0] == "DDD"  # the most liquid of the rest
    assert all(rows[symbol]["primary_tp"] is not None for symbol in tested | {"DDD"})
    pending = [symbol for symbol, row in rows.items() if row["origin"] == "not_evaluable:pending_targets"]
    assert sorted(pending) == ["AAA", "BBB", "CCC"] and all(rows[s]["primary_tp"] is None for s in pending)
    assert section["complete"] is False and section["counts"]["reach"] == {"reached": 3, "pending": 3}
    assert section["counts"]["pit_tested_pending"] == 0 and live.unpublishable(section) is None  # the tested names are complete
    # a deadline before the tested names are done: the section is never published
    advance[0] = 0
    calls.clear()
    early = live.compute_live_section(_inputs(database, targets=_pinned_targets(database, calls, advance=advance)),
                                      deadline=start + timedelta(seconds=30), clock=lambda: start + timedelta(minutes=advance[0]))
    assert early["counts"]["pit_tested_pending"] == 1 and live.unpublishable(early) == "tested_names_pending"


def _with_listed_world(monkeypatch: pytest.MonkeyPatch) -> Database:
    database = _wide_world()
    with monkeypatch.context() as scoped:
        scoped.setattr(grid_tests, "SYMBOLS", (*SYMBOLS, "GGG"))
        _canonical_facts(database)
    return database


def test_a_failing_listed_chunk_refuses_that_chunk_only(monkeypatch: pytest.MonkeyPatch) -> None:
    database = _with_listed_world(monkeypatch)
    _, served_only = _live(database, listed=False)
    _listed(database, (*SYMBOLS, "GGG", "PPP", "ZZZ"))

    def broken(self: Any) -> None:
        raise RuntimeError("database connection lost")

    monkeypatch.setattr(live._PopulationResolver, "resolve", broken)
    _, section = _live(database)
    rows = {row["symbol"]: row for row in section["records"]}
    assert all(rows[s]["origin"] == "not_evaluable:listed_chunk_failed:RuntimeError" for s in ("GGG", "PPP", "ZZZ"))
    for row in served_only["records"]:  # the served names (and their tested ones) are untouched
        assert rows[row["symbol"]]["primary_tp"] == row["primary_tp"] and rows[row["symbol"]]["model_values"] == row["model_values"]
    assert section["counts"]["listed_only_coverage"]["chunks_failed"] == 1 and live.unpublishable(section) is None
    # every population row stays in every model's denominator, the refused chunk included
    assert all(sum(counts.values()) == section["counts"]["population_rows"] for counts in section["counts"]["model_results"].values())
    assert section["counts"]["model_results"]["pe"]["not_evaluable:listed_chunk_failed:RuntimeError"] == 3


@pytest.mark.usefixtures("_two_tested")
def test_an_open_breaker_after_the_tested_reads_skips_the_listed_only_names(monkeypatch: pytest.MonkeyPatch) -> None:
    database = _with_listed_world(monkeypatch)
    _listed(database, (*SYMBOLS, "GGG", "PPP", "ZZZ"))
    monkeypatch.setattr(live, "TARGETS_BREAKER_CONSECUTIVE", 2)
    resolved: list[str] = []
    original = live._PopulationResolver.resolve

    def spy(self: Any) -> Any:
        resolved.append("chunk")
        return original(self)

    monkeypatch.setattr(live._PopulationResolver, "resolve", spy)
    calls: list[tuple[str, int | None]] = []
    _, section = _live(database, targets=_pinned_targets(database, calls, failing=set(SYMBOLS) | {"GGG"}))
    rows = {row["symbol"]: row for row in section["records"]}
    assert sorted(symbol for symbol, _ in calls) == ["EEE", "FFF"] and resolved == []  # no chunk walked, no further read
    assert all(rows[s]["origin"] == "not_evaluable:skipped:targets_circuit_open" for s in ("GGG", "PPP", "ZZZ"))
    assert section["counts"]["targets"]["circuit_open"] is True and live.unpublishable(section) == "targets_circuit_open"


def test_a_malformed_or_differently_spelled_listing_never_breaks_the_served_section() -> None:
    fixture = _fixture()
    database = fixture[0]
    outputs: dict[str, Any] = {"schema": live.LISTED_SCHEMA, "market": "NASDAQ", "listings": {"not": "a list"}}
    outputs["manifest_sha256"] = canonical_hash(outputs)
    database.save_analysis_snapshot(live.LISTED_ANALYSIS, "NASDAQ", "mv-listed", {}, outputs, VINTAGE_AT)
    rows, reference = live.listed_population(database, "NASDAQ")
    assert rows == [] and reference["status"] == "refused_listings"
    _, section = _live(database)
    assert section["counts"]["with_primary_tp"] == len(SYMBOLS) and section["context"]["listed"]["status"] == "refused_listings"
    # one row per share class whatever the spelling, and a served name is never listed twice
    _listed(database, ("BRK.B", "BRK-B", "brk/b", " aaa "), at=VINTAGE_AT + timedelta(minutes=1))
    rows, reference = live.listed_population(database, "NASDAQ")
    assert [row["symbol"] for row in rows] == ["AAA", "BRK-B"] and reference["stocks"] == 2
    assert [row["symbol"] for row in _inputs(database).extra_rows] == ["BRK-B"]


def _nyse(database: Database) -> None:
    sessions = _sessions("2023-06-01", "2026-09-10")
    nyse = ScriptedHttp({"/api/eod/NYA.US": _bars_for("NYA", sessions, base=50.0)})
    series.PriceHistoryService(_settings(), database, nyse, eodhd=EodhdClient("https://eodhd.com", "secret", nyse)).persist_run(  # type: ignore[arg-type]
        "NYSE", start=date(2023, 6, 1), end=date(2026, 9, 10), symbols=["NYA"], now=VINTAGE_AT)
    database.save_analysis_snapshot("valuation_universe", "NYSE_UNIVERSE", "mv-cat", {"methodology_version": 7},
                                    {"rows": [{"symbol": "NYA", "sector": SECTOR, "industry": "Machinery", "valuation_profile": "general",
                                               "security_type": "Stock"}]}, VINTAGE_AT - timedelta(hours=1))


def test_one_exchange_failing_its_preparation_never_costs_the_other_its_night(monkeypatch: pytest.MonkeyPatch,
                                                                              caplog: pytest.LogCaptureFixture) -> None:
    _on(monkeypatch)
    database, http = _live_world()
    _nyse(database)
    original = live._LiveSection.prepare_served

    def prepare(self: Any) -> None:
        if self.market == "NYSE":
            raise RuntimeError("statement store unreachable")
        original(self)

    monkeypatch.setattr(live._LiveSection, "prepare_served", prepare)
    with caplog.at_level(logging.INFO), pytest.raises(live.LiveEnsembleError, match=r"^markets_not_published:1$"):
        live.run_nightly(database, _settings(), cast(JsonHttpClient, http), clock=lambda: CLOCK)
    nasdaq = database.latest_analysis_snapshot(live.ANALYSIS_TYPE, "NASDAQ_UNIVERSE")
    assert nasdaq is not None and nasdaq["outputs"]["counts"]["with_primary_tp"] == len(SYMBOLS)
    assert database.latest_analysis_snapshot(live.ANALYSIS_TYPE, "NYSE_UNIVERSE") is None
    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "failures={'section:RuntimeError': 1}" in text and "unreachable" not in text  # a count and a class, never the text


def test_provider_requests_are_bounded_as_a_whole_by_the_time_left(monkeypatch: pytest.MonkeyPatch) -> None:
    bounds: list[float] = []
    outcomes: list[Any] = []

    class Bounded:
        def __init__(self, *, timeout: float) -> None:
            bounds.append(timeout)

        def get_json(self, url: str, *, params: Any = None, headers: Any = None) -> Any:
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    monkeypatch.setattr(live, "DeadlineJsonHttpClient", Bounded)
    start = datetime(2026, 9, 11, 8, 29, 50, tzinfo=timezone.utc)
    now = [start]
    near = live._DeadlineHttp(JsonHttpClient(timeout=15.0, max_retries=1), deadline=start + timedelta(seconds=10), clock=lambda: now[0])
    outcomes[:] = [MarketDataRequestError("TimeoutError"), {"ok": True}]
    assert near.get_json("https://provider.example/x") == {"ok": True} and bounds == [10.0, 10.0]  # the whole response, never past it
    far = live._DeadlineHttp(JsonHttpClient(timeout=15.0, max_retries=0), deadline=start + timedelta(hours=1), clock=lambda: now[0])
    bounds.clear()
    outcomes[:] = [[1, 2]]
    assert far.get_json("https://provider.example/x") == [1, 2] and bounds == [live.REQUEST_TIMEOUT_SECONDS]

    class Drip(Bounded):
        def get_json(self, url: str, *, params: Any = None, headers: Any = None) -> Any:
            now[0] += timedelta(seconds=20)  # the attempt used up the time left: the retry must not start
            raise MarketDataRequestError("TimeoutError")

    monkeypatch.setattr(live, "DeadlineJsonHttpClient", Drip)
    with pytest.raises(live.LiveEnsembleDeadline):
        near.get_json("https://provider.example/x")


def test_past_the_publish_grace_a_finished_section_is_not_written(monkeypatch: pytest.MonkeyPatch) -> None:
    _on(monkeypatch)
    monkeypatch.setattr(backtest, "SCREEN_MIN_MARKET_CAP", 0.0)
    monkeypatch.setattr(backtest, "SCREEN_MIN_DOLLAR_VOLUME", 0.0)
    monkeypatch.setattr(backtest, "SCREEN_TOP_PER_EXCHANGE", 1)
    database, http = _live_world()
    with pytest.raises(live.LiveEnsembleError, match=r"^markets_not_published:1$"):
        live.run_nightly(database, _settings(), cast(JsonHttpClient, http), clock=lambda: CLOCK + timedelta(minutes=10 * _target_calls(http)),
                         deadline=CLOCK + timedelta(minutes=2, seconds=30), markets=("NASDAQ",))
    assert _target_calls(http) == 1 and database.latest_analysis_snapshot(live.ANALYSIS_TYPE, "NASDAQ_UNIVERSE") is None


# ------------------------------------------------------------------ the nightly run: live fetches in memory, one snapshot per market
CLOCK = VINTAGE_AT + timedelta(minutes=1)  # 03:01Z on 2026-09-11: the session of the clock is 2026-09-10, the publication's last


def _live_world(*, targets_fail: bool = False) -> tuple[Database, ScriptedHttp]:
    database = _database()
    _publish_prices(database)
    _publish_sources(database, poison=True)
    _canonical_facts(database)

    def targets(params: dict[str, Any]) -> list[dict[str, Any]]:
        if targets_fail:
            raise MarketDataRequestError("403 Forbidden")
        if params.get("page"):
            return []
        return [_target(house, CLOCK - timedelta(days=10), value) for house, value in (("A", 100), ("B", 200), ("C", 1000))]

    def gbond(rate: float):
        def rows(params: dict[str, Any]) -> list[dict[str, Any]]:
            return [{"date": day, "close": rate, "adjusted_close": rate, "volume": 0} for day in ("2026-09-08", "2026-09-09", "2026-09-10")]
        return rows

    http = ScriptedHttp({"/stable/price-target-news": targets, "/api/eod/US3Y.GBOND": gbond(3.9), "/api/eod/US10Y.GBOND": gbond(4.3)})
    return database, http


def _target_calls(http: ScriptedHttp) -> int:
    return sum("price-target-news" in url for url in http.calls)


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
    assert summary["provider_reads"] == {"eodhd": 1, "fmp": len(SYMBOLS)} and summary["names_pending"] == 0
    snapshot = database.latest_analysis_snapshot(live.ANALYSIS_TYPE, "NASDAQ_UNIVERSE")
    assert snapshot is not None and snapshot["outputs"]["as_of"] == CLOCK.isoformat() and snapshot["outputs"]["complete"] is True
    records = snapshot["outputs"]["records"]
    assert [row["symbol"] for row in records] == sorted(SYMBOLS) and all(row["origin"] == "ensemble" for row in records)
    assert all(row["as_of"] == CLOCK.isoformat() and row["session_date"] == "2026-09-10" and len(row["inputs_sha256"]) == 64 for row in records)
    assert snapshot["outputs"]["context"]["curve"]["origin"] == "live_fetch:" + pit.MACRO_TREASURY_KEY
    # NYSE has no publication: the volume basis is never voted on one exchange alone; TPs do not depend on it
    assert snapshot["outputs"]["volume_check"] == {"decision": "not_every_exchange_pinned"} and all(row["screened"] is None for row in records)
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


def test_the_volume_basis_is_voted_over_both_exchanges_even_when_one_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    _on(monkeypatch)
    database, http = _live_world()
    sessions = _sessions("2023-06-01", "2026-09-10")
    nyse = ScriptedHttp({"/api/eod/NYA.US": _bars_for("NYA", sessions, base=50.0)})
    series.PriceHistoryService(_settings(), database, nyse, eodhd=EodhdClient("https://eodhd.com", "secret", nyse)).persist_run(  # type: ignore[arg-type]
        "NYSE", start=date(2023, 6, 1), end=date(2026, 9, 10), symbols=["NYA"], now=VINTAGE_AT)
    voted: list[list[str]] = []

    def spy(database: Database, settings: Settings, prices: dict[str, pit.PinnedPrices]) -> tuple[str | None, dict[str, Any]]:
        voted.append(sorted(prices))
        return None, {"decision": "undetermined"}

    monkeypatch.setattr(live, "decide_volume_basis", spy)
    live.run_nightly(database, _settings(), cast(JsonHttpClient, http), clock=lambda: CLOCK, markets=("NASDAQ",))
    assert voted == [["NASDAQ", "NYSE"]]


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


def test_the_breaker_stops_reading_a_failing_provider_and_nothing_is_published(monkeypatch: pytest.MonkeyPatch) -> None:
    _on(monkeypatch)
    monkeypatch.setattr(live, "TARGETS_BREAKER_CONSECUTIVE", 3)
    database, http = _live_world(targets_fail=True)
    with pytest.raises(live.LiveEnsembleError, match=r"^markets_not_published:1$"):
        live.run_nightly(database, _settings(), cast(JsonHttpClient, http), clock=lambda: CLOCK, markets=("NASDAQ",))
    assert _target_calls(http) == 3  # three failed reads, then no more requests tonight
    assert database.latest_analysis_snapshot(live.ANALYSIS_TYPE, "NASDAQ_UNIVERSE") is None


def test_every_target_read_failing_is_a_failed_phase_and_the_health_card_is_not_green(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.test_system_health import _service

    _on(monkeypatch)
    database, http = _live_world(targets_fail=True)  # six names under the breaker's ten: the failed share refuses the section
    local = datetime(2026, 9, 11, 1, 30, tzinfo=SAO_PAULO)
    phase = OffhoursPhase("ensemble_live", lambda: live.last_run_at(database),
                          lambda: live.run_nightly(database, _settings(), cast(JsonHttpClient, http), clock=lambda: CLOCK, markets=("NASDAQ",)))
    result = run_worker_iteration(database, now=local, canonical_due=False, canonical_operation=lambda: None, offhours_phases=(phase,))
    assert result.phase_statuses == {"ensemble_live": "failed"} and _target_calls(http) == len(SYMBOLS)
    assert database.latest_analysis_snapshot(live.ANALYSIS_TYPE, "NASDAQ_UNIVERSE") is None
    code = VALUATION_WORKER_PHASES["ensemble_live"]["code"]
    now = datetime.now(timezone.utc)
    states = {definition["code"]: {"last_status": "succeeded", "started_at": now, "completed_at": now, "last_success_at": now,
                                   "last_error": None, "metadata": {"phase": phase_key}}
              for phase_key, definition in VALUATION_WORKER_PHASES.items()}
    states[code] = {**database.ingestion_run_health([code])[code], "metadata": {"phase": "ensemble_live"}}
    monkeypatch.setenv(valuation_env.DECISOR_SHADOW_ENV, "true")
    monkeypatch.setenv(valuation_env.EARNINGS_CALENDAR_ENV, "true")
    card = _service(valuation_phase_states=states)._valuation_worker_phase_health(now)
    assert card.status == "attention" and "ensemble_live: LiveEnsembleError: markets_not_published:1" in (card.detail or "")


@pytest.mark.usefixtures("_two_tested")
def test_a_deadline_mid_sweep_publishes_the_tested_names_and_records_the_night_as_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    _on(monkeypatch)
    database, http = _live_world()
    deadline = CLOCK + timedelta(minutes=2, seconds=30)
    with pytest.raises(live.LiveEnsembleError, match=r"^markets_partial:1:names_pending:3$"):
        live.run_nightly(database, _settings(), cast(JsonHttpClient, http), clock=lambda: CLOCK + timedelta(minutes=_target_calls(http)),
                         deadline=deadline, markets=("NASDAQ",))
    assert _target_calls(http) == 3
    snapshot = database.latest_analysis_snapshot(live.ANALYSIS_TYPE, "NASDAQ_UNIVERSE")
    assert snapshot is not None and snapshot["outputs"]["complete"] is False
    rows = {row["symbol"]: row for row in snapshot["outputs"]["records"]}
    assert all(row["primary_tp"] is not None for row in rows.values() if row["pit_tested"])
    assert snapshot["outputs"]["counts"]["reach"] == {"reached": 3, "pending": 3}
    # a deadline already past: nothing is read (not even whether tonight already published an exchange), nothing is
    # written, the run says so
    database, http = _live_world()
    asked: list[str] = []
    published_at = database.latest_analysis_snapshot_published_at
    monkeypatch.setattr(database, "latest_analysis_snapshot_published_at",
                        lambda analysis, entity: asked.append(entity) or published_at(analysis, entity))
    with pytest.raises(live.LiveEnsembleError, match=r"^markets_not_published:2$"):
        live.run_nightly(database, _settings(), cast(JsonHttpClient, http), clock=lambda: CLOCK, deadline=CLOCK, since=CLOCK - timedelta(hours=1))
    assert asked == [] and http.calls == [] and database.latest_analysis_snapshot(live.ANALYSIS_TYPE, "NASDAQ_UNIVERSE") is None


def test_the_phase_closes_its_run_stops_after_two_failures_and_never_starts_at_or_after_five(monkeypatch: pytest.MonkeyPatch) -> None:
    _on(monkeypatch)
    database, http = _live_world()
    night = datetime(2026, 9, 11, 0, 0, tzinfo=SAO_PAULO)
    phase = OffhoursPhase("ensemble_live", lambda: live.last_run_at(database),
                          lambda: valuation_worker.run_ensemble_live(database, _settings(), cast(JsonHttpClient, http), now=night,
                                                                     clock=lambda: night + valuation_worker.ENSEMBLE_LIVE_DEADLINE),
                          end_hour=valuation_worker.ENSEMBLE_LIVE_LAST_START_HOUR, max_failures=valuation_worker.ENSEMBLE_LIVE_MAX_FAILURES)
    statuses = [run_worker_iteration(database, now=night + timedelta(hours=1, minutes=30 + 30 * step), canonical_due=False,
                                     canonical_operation=lambda: None, offhours_phases=(phase,)).phase_statuses["ensemble_live"]
                for step in range(3)]
    statuses.append(run_worker_iteration(database, now=night + timedelta(hours=5), canonical_due=False, canonical_operation=lambda: None,
                                         offhours_phases=(phase,)).phase_statuses["ensemble_live"])
    assert statuses == ["failed", "failed", "retry_cap", "outside_window"] and http.calls == []
    runs = [run for run in database._ingestion_runs.values() if run["source_code"] == VALUATION_WORKER_PHASES["ensemble_live"]["code"]]
    assert len(runs) == 2 and all(run["status"] == "failed" and run["completed_at"] is not None for run in runs)  # closed, never `running`
    assert all(run["error_summary"] == "LiveEnsembleError: markets_not_published:2" for run in runs)
    assert valuation_worker.ENSEMBLE_LIVE_DEADLINE == timedelta(hours=5, minutes=30) and valuation_worker.ENSEMBLE_LIVE_LAST_START_HOUR == 5


def test_the_live_phase_never_runs_ahead_of_a_deferred_decisor() -> None:
    database = _database()
    local = datetime(2026, 9, 11, 1, 30, tzinfo=SAO_PAULO)
    ready = local + timedelta(minutes=1)
    order: list[str] = []
    decided: list[datetime] = []
    now = [local]

    def decisor() -> dict[str, int]:
        order.append("decisor")
        decided.append(now[0])
        return {"verdicts": 1}

    def waits() -> datetime | None:
        return valuation_worker.ensemble_live_not_before(database, now=now[0], decisor_scheduled=True,
                                                         decisor_last_run_at=lambda: decided[-1] if decided else None,
                                                         decisor_not_before=lambda: ready)

    phases = (OffhoursPhase("decisor_shadow", lambda: decided[-1] if decided else None, decisor, not_before=lambda: ready),
              OffhoursPhase("ensemble_live", lambda: None, lambda: order.append("live") or {"names": 1}, end_hour=5, max_failures=2,
                            not_before=waits))
    first = run_worker_iteration(database, now=local, canonical_due=False, canonical_operation=lambda: None, offhours_phases=phases)
    assert first.phase_statuses == {"decisor_shadow": "deferred", "ensemble_live": "deferred"} and order == []
    assert first.next_wake_at == ready
    now[0] = ready
    second = run_worker_iteration(database, now=ready, canonical_due=False, canonical_operation=lambda: None, offhours_phases=phases)
    assert second.phase_statuses == {"decisor_shadow": "succeeded", "ensemble_live": "succeeded"} and order == ["decisor", "live"]
    # a decisor that is off, done tonight or not deferred never holds the live phase
    assert valuation_worker.ensemble_live_not_before(database, now=local, decisor_scheduled=False, decisor_last_run_at=lambda: None,
                                                     decisor_not_before=lambda: ready) is None
    assert valuation_worker.ensemble_live_not_before(database, now=local, decisor_scheduled=True, decisor_last_run_at=lambda: None,
                                                     decisor_not_before=lambda: None) is None
    # the main loop wires it so
    source = (BACKEND / "app" / "valuation_worker.py").read_text(encoding="utf-8")
    phases_source = source[source.index("offhours_phases = ("):source.index("while True:")]
    wiring = phases_source[phases_source.index('OffhoursPhase("ensemble_live"'):]
    for fragment in ("end_hour=ENSEMBLE_LIVE_LAST_START_HOUR", "max_failures=ENSEMBLE_LIVE_MAX_FAILURES", "not_before=lambda: ensemble_live_not_before(",
                     "clock=lambda: datetime.now(SAO_PAULO)",
                     "decisor_last_run_at=lambda: decision_last_run_at(database)", "decisor_not_before=lambda: decision_not_before(database)"):
        assert fragment in wiring, fragment


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
    local = datetime(2026, 9, 11, 1, 30, tzinfo=SAO_PAULO)
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


def test_an_earlier_phase_crossing_the_last_start_admits_no_new_live_run() -> None:
    # the pass opens at 04:59:59; an earlier phase runs until 05:29:59; the live phase is admitted on ITS clock, not the pass's
    def phases(effective: bool, ran: list[str], clock: list[datetime]) -> tuple[OffhoursPhase, ...]:
        def long() -> dict[str, int]:
            clock[0] = datetime(2026, 9, 11, 5, 29, 59, tzinfo=SAO_PAULO)
            ran.append("v3_shadow")
            return {"rows": 1}
        return (OffhoursPhase("v3_shadow", lambda: None, long),
                OffhoursPhase("ensemble_live", lambda: None, lambda: ran.append("live") or {"names": 1},
                              end_hour=valuation_worker.ENSEMBLE_LIVE_LAST_START_HOUR, max_failures=valuation_worker.ENSEMBLE_LIVE_MAX_FAILURES,
                              clock=(lambda: clock[0]) if effective else None))

    opening = datetime(2026, 9, 11, 4, 59, 59, tzinfo=SAO_PAULO)
    ran: list[str] = []
    clock = [opening]
    result = run_worker_iteration(_database(), now=opening, canonical_due=False, canonical_operation=lambda: None,
                                  offhours_phases=phases(True, ran, clock))
    assert result.phase_statuses == {"v3_shadow": "succeeded", "ensemble_live": "outside_window"} and ran == ["v3_shadow"]
    # the defect it closes: on the pass's opening instant the live run would have started at 05:29:59
    ran, clock = [], [opening]
    naive = run_worker_iteration(_database(), now=opening, canonical_due=False, canonical_operation=lambda: None,
                                 offhours_phases=phases(False, ran, clock))
    assert naive.phase_statuses["ensemble_live"] == "succeeded" and ran == ["v3_shadow", "live"]


@pytest.mark.parametrize("slow_read", ["last_completed_at", "failure_count", "not_before"])
def test_a_readiness_read_crossing_the_last_start_admits_no_new_live_run(monkeypatch: pytest.MonkeyPatch, slow_read: str) -> None:
    # the phase's turn opens at 04:59:59 on its own clock and one of its readiness reads costs 2 s: the admission is decided on
    # a reading taken after them, so nothing runs or is recorded at 05:00:01; the same read ending at 04:59:57 still runs
    def turn(opening: datetime) -> tuple[str, list[str], list[dict[str, Any]]]:
        database = _database()
        clock = [opening]
        ran: list[str] = []

        def slow(value: Any) -> Any:
            clock[0] += timedelta(seconds=2)
            return value

        if slow_read == "failure_count":
            count = database.count_ingestion_runs
            monkeypatch.setattr(database, "count_ingestion_runs", lambda *args, **kwargs: slow(count(*args, **kwargs)))
        phase = OffhoursPhase("ensemble_live", (lambda: slow(None)) if slow_read == "last_completed_at" else (lambda: None),
                              lambda: ran.append("live") or {"names": 1},
                              end_hour=valuation_worker.ENSEMBLE_LIVE_LAST_START_HOUR, max_failures=valuation_worker.ENSEMBLE_LIVE_MAX_FAILURES,
                              not_before=(lambda: slow(None)) if slow_read == "not_before" else None, clock=lambda: clock[0])
        result = run_worker_iteration(database, now=opening, canonical_due=False, canonical_operation=lambda: None, offhours_phases=(phase,))
        runs = [run for run in database._ingestion_runs.values() if run["source_code"] == VALUATION_WORKER_PHASES["ensemble_live"]["code"]]
        return result.phase_statuses["ensemble_live"], ran, runs

    status, ran, runs = turn(datetime(2026, 9, 11, 4, 59, 59, tzinfo=SAO_PAULO))
    assert status == "outside_window" and ran == [] and runs == []
    status, ran, runs = turn(datetime(2026, 9, 11, 4, 59, 55, tzinfo=SAO_PAULO))
    assert status == "succeeded" and ran == ["live"] and len(runs) == 1 and runs[0]["status"] == "succeeded"


def test_the_recorded_start_is_the_admission_instant_whatever_the_source_upsert_costs(monkeypatch: pytest.MonkeyPatch) -> None:
    # admitted at 04:59:59 on its own clock; the data source's upsert inside begin_ingestion_run then costs 2 s: the run's
    # recorded start is the admission (04:59:59), never the 05:00:01 at which that bookkeeping round trip ends
    database = _database()
    clock = [datetime(2026, 9, 11, 4, 59, 59, tzinfo=SAO_PAULO)]
    upsert = database.ensure_data_source

    def slow_upsert(*args: Any, **kwargs: Any) -> str:
        clock[0] += timedelta(seconds=2)
        return upsert(*args, **kwargs)

    monkeypatch.setattr(database, "ensure_data_source", slow_upsert)
    phase = OffhoursPhase("ensemble_live", lambda: None, lambda: {"names": 1},
                          end_hour=valuation_worker.ENSEMBLE_LIVE_LAST_START_HOUR, max_failures=valuation_worker.ENSEMBLE_LIVE_MAX_FAILURES,
                          clock=lambda: clock[0])
    result = run_worker_iteration(database, now=clock[0], canonical_due=False, canonical_operation=lambda: None, offhours_phases=(phase,))
    runs = [run for run in database._ingestion_runs.values() if run["source_code"] == VALUATION_WORKER_PHASES["ensemble_live"]["code"]]
    assert result.phase_statuses["ensemble_live"] == "succeeded" and len(runs) == 1 and clock[0].second == 1
    assert runs[0]["started_at"] == datetime(2026, 9, 11, 4, 59, 59, tzinfo=SAO_PAULO)
    with pytest.raises(ValueError):  # a naive admission instant is refused before anything is written
        database.begin_ingestion_run("probe", "probe", "test", {}, started_at=datetime(2026, 9, 11, 4, 59, 59))
    assert len(database._ingestion_runs) == 1


@pytest.mark.parametrize(("start", "reads_before_the_cut"), [
    (datetime(2026, 9, 11, 8, 29, 59, tzinfo=timezone.utc), 1),  # the cut falls inside the resolver's issuer reads
    (datetime(2026, 9, 11, 8, 29, 46, tzinfo=timezone.utc), 7),  # the resolver finishes; the cut falls inside the preparation
])
def test_no_new_read_starts_after_the_cut(monkeypatch: pytest.MonkeyPatch, start: datetime, reads_before_the_cut: int) -> None:
    _on(monkeypatch)
    database, http = _live_world()
    deadline = datetime(2026, 9, 11, 8, 30, tzinfo=timezone.utc)  # 05:30 BRT
    now = [start]
    starts: list[datetime] = []
    original = pit.AsFiledReader.facts

    def slow(self: Any, issuer_key: str, *, as_of: datetime, refused: Any) -> Any:
        starts.append(now[0])
        now[0] += timedelta(seconds=2)  # every issuer read takes two seconds
        return original(self, issuer_key, as_of=as_of, refused=refused)

    monkeypatch.setattr(pit.AsFiledReader, "facts", slow)
    with pytest.raises(live.LiveEnsembleError, match=r"^markets_not_published:1$"):
        live.run_nightly(database, _settings(), cast(JsonHttpClient, http), clock=lambda: now[0], deadline=deadline, markets=("NASDAQ",))
    assert len(starts) == reads_before_the_cut and all(instant < deadline for instant in starts)  # the read in flight may finish
    assert database.latest_analysis_snapshot(live.ANALYSIS_TYPE, "NASDAQ_UNIVERSE") is None and _target_calls(http) == 0


def test_the_nightly_run_reads_no_catalogue_published_after_its_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    _on(monkeypatch)
    database, http = _live_world()
    database.save_analysis_snapshot("valuation_universe", "NASDAQ_UNIVERSE", "mv-cat", {"methodology_version": 7},
                                    {"rows": [{"symbol": s, "sector": SECTOR, "industry": "Machinery", "valuation_profile": "general",
                                               "security_type": "Stock"} for s in (*SYMBOLS, "LATE")]}, CLOCK + timedelta(minutes=5))
    _listed(database, (*SYMBOLS, "LATER"), at=CLOCK + timedelta(minutes=5))
    live.run_nightly(database, _settings(), cast(JsonHttpClient, http), clock=lambda: CLOCK, markets=("NASDAQ",))
    snapshot = database.latest_analysis_snapshot(live.ANALYSIS_TYPE, "NASDAQ_UNIVERSE")
    assert snapshot is not None and [row["symbol"] for row in snapshot["outputs"]["records"]] == sorted(SYMBOLS)
    assert snapshot["outputs"]["context"]["listed"] == {"status": "absent"}
