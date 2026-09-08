"""The V3.2 price series (rev 7 §2.2 / §9.2), rev 2: every run is ONE vintage (manifest + changed bars in one transaction,
availability stamped after the last provider answer, one series hash per symbol); a cut sees exactly one vintage and a
symbol only when its stored bars reproduce that vintage's hash; labels need the target session CLOSED before the cut.
OFF by default; the 36-month backfill is an explicit one-shot run."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app import valuation_price_history as series
from app.config import Settings
from app.database import Database
from app.market_data.eodhd import EodhdClient

NOW = datetime(2026, 9, 7, 23, 30, tzinfo=timezone.utc)
D = timedelta(days=1)


class ScriptedHttp:
    """Answers /api/eod calls per provider symbol; records what was asked."""

    def __init__(self, bars_by_symbol: dict[str, list[dict]]) -> None:
        self.bars_by_symbol = bars_by_symbol
        self.calls: list[dict] = []

    def get_json(self, url: str, *, params=None, headers=None):
        self.calls.append({"url": url, "params": dict(params or {})})
        provider_symbol = url.rsplit("/", 1)[-1]
        if provider_symbol == "BOOM.US":
            raise RuntimeError("provider down")
        return self.bars_by_symbol.get(provider_symbol, [])


class Ticks:
    """A scripted clock: one instant per call, in order."""

    def __init__(self, *instants: datetime) -> None:
        self.instants = list(instants)

    def __call__(self) -> datetime:
        return self.instants.pop(0)


def _settings() -> Settings:
    return Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False)


def _service(bars_by_symbol: dict[str, list[dict]]) -> tuple[series.PriceHistoryService, Database, ScriptedHttp]:
    settings = _settings()
    database = Database(settings)
    http = ScriptedHttp(bars_by_symbol)
    service = series.PriceHistoryService(settings, database, http, eodhd=EodhdClient("https://eodhd.com", "secret", http))  # type: ignore[arg-type]
    return service, database, http


def _bar(day: str, close: float, adjusted: float | None = None, volume: float = 1000.0) -> dict:
    return {"date": day, "close": close, "adjusted_close": close if adjusted is None else adjusted, "volume": volume}


def _run(service: series.PriceHistoryService, market: str, symbols: list[str], *, now: datetime, start=date(2026, 9, 1), end=date(2026, 9, 10), mode="nightly"):
    return service.persist_run(market, start=start, end=end, symbols=symbols, now=now, mode=mode)


def test_bars_need_both_closes_and_hash_their_content_not_their_clock() -> None:
    record = series.bar_record("NASDAQ", "AAPL", "AAPL.US", _bar("2026-09-04", 230.0, 229.5))
    assert record and record["close"] == 230.0 and record["adjusted_close"] == 229.5 and record["currency"] == "USD" and record["source"] == series.SOURCE
    assert len(record["bar_sha256"]) == 64 and "fetched_at" not in record  # the run stamps the clock; the hash is the content
    assert series.bar_record("NASDAQ", "AAPL", "AAPL.US", _bar("2026-09-04", 230.0, 229.5))["bar_sha256"] == record["bar_sha256"]  # type: ignore[index]
    assert series.bar_record("NASDAQ", "AAPL", "AAPL.US", _bar("2026-09-04", 230.0, 115.0))["bar_sha256"] != record["bar_sha256"]  # type: ignore[index]
    assert series.bar_record("NASDAQ", "AAPL", "AAPL.US", {"date": "2026-09-04", "close": 230.0}) is None  # adjusted_close mandatory
    assert series.bar_record("NASDAQ", "AAPL", "AAPL.US", {"date": "bad", "close": 1.0, "adjusted_close": 1.0}) is None
    assert series.bar_record("B3", "PETR4", "PETR4.SA", _bar("2026-09-04", 36.0))["currency"] == "BRL"  # type: ignore[index]


def test_coverage_is_the_universe_plus_every_symbol_with_v3_evaluations() -> None:
    service, database, _ = _service({})
    database.save_analysis_snapshot("valuation_universe", "NASDAQ_UNIVERSE", "mv-1", {"methodology_version": 7},
                                    {"rows": [{"symbol": "AAPL"}, {"symbol": "msft"}], "universe_size": 2}, NOW)
    database.save_analysis_snapshot("valuation_v3_shadow", "NASDAQ_V3_SHADOW", "mv-1", {"market": "NASDAQ"},
                                    {"results": {"AAPL": {}, "NVDA": {}, "OLDC": {}}}, NOW - 3 * D)
    assert service.coverage_symbols("NASDAQ") == ["AAPL", "MSFT", "NVDA", "OLDC"]  # a delisted-from-universe name keeps its labels coming


def test_a_run_is_one_vintage_written_in_one_transaction_with_hashes_per_symbol_and_every_loss_recorded() -> None:
    service, database, http = _service({
        "AAPL.US": [_bar("2026-09-03", 229.0, 229.0), _bar("2026-09-04", 230.0, 230.0)],
        "MSFT.US": [_bar("2026-09-04", 500.0, 499.0), {"date": "2026-09-03", "close": 498.0}, _bar("2026-08-28", 1.0)],  # incomplete row; a row outside the window
    })
    calls: list[str] = []
    real_persist = database.persist_price_history_run
    database.persist_price_history_run = lambda *a, **k: (calls.append("persist"), real_persist(*a, **k))[1]  # type: ignore[method-assign]
    database.save_analysis_snapshot = lambda *a, **k: (calls.append("snapshot"), real_persist.__self__.__class__.save_analysis_snapshot(database, *a, **k))[1]  # type: ignore[method-assign]
    result = _run(service, "NASDAQ", ["AAPL", "MSFT", "NONE", "BOOM"], now=NOW)
    assert calls[0] == "persist"  # manifest and bars go through the single transactional write, never two separate commits
    assert result["bars"] == 3 and result["bars_inserted"] == 3 and result["bars_unchanged"] == 0 and result["symbols_with_bars"] == 2
    assert result["symbols_missing"] == ["BOOM", "NONE"] and result["errors"] == {"BOOM": "RuntimeError"}
    assert result["rows_rejected_incomplete"] == {"MSFT": 1} and result["rows_rejected_total"] == 1  # the provider answered, the series refused: recorded
    assert result["first_session"] == "2026-09-03" and result["last_session"] == "2026-09-04" and len(result["bars_sha256"]) == 64
    assert set(result["series_sha256"]) == {"AAPL", "MSFT"} and result["series_bars"] == {"AAPL": 2, "MSFT": 1} and result["symbols_unreproducible"] == {}
    manifest = database.latest_analysis_snapshot(series.ANALYSIS_TYPE, "NASDAQ")
    assert manifest and manifest["id"] == result["price_snapshot_id"] and manifest["outputs"]["bars"] == 3 and manifest["inputs"]["mode"] == "nightly"
    assert manifest["inputs"]["calendar"] == {"name": "XNYS", "exchange_calendars": "4.13.2"} and manifest["inputs"]["started_at"] == NOW.isoformat()
    assert manifest["published_at"] == NOW and manifest["inputs"]["fetched_at"] == NOW.isoformat()
    assert {call["params"]["from"] for call in http.calls} == {"2026-09-01"} and all("api_token" in call["params"] for call in http.calls)
    # the same content again at a later clock: a new vintage, NO new rows (content dedup) — and the series hashes are the same
    again = _run(service, "NASDAQ", ["AAPL", "MSFT"], now=NOW + D)
    assert again["bars"] == 3 and again["bars_inserted"] == 0 and again["bars_unchanged"] == 3 and again["series_sha256"] == result["series_sha256"]
    # a restated bar (split) inserts only the bars that changed, and the symbol's series hash moves
    http.bars_by_symbol["AAPL.US"] = [_bar("2026-09-03", 229.0, 114.5), _bar("2026-09-04", 230.0, 230.0)]
    restated = _run(service, "NASDAQ", ["AAPL", "MSFT"], now=NOW + 2 * D)
    assert restated["bars_inserted"] == 1 and restated["bars_unchanged"] == 2 and restated["series_sha256"]["AAPL"] != result["series_sha256"]["AAPL"]
    assert restated["series_sha256"]["MSFT"] == result["series_sha256"]["MSFT"]


def test_availability_is_stamped_after_the_last_answer_so_a_cut_inside_the_run_never_sees_it() -> None:
    service, database, http = _service({"AAPL.US": [_bar("2026-09-04", 230.0)]})
    started, done = datetime(2026, 9, 7, 23, 0, tzinfo=timezone.utc), datetime(2026, 9, 7, 23, 1, tzinfo=timezone.utc)
    result = service.persist_run("NASDAQ", start=date(2026, 9, 1), end=date(2026, 9, 4), symbols=["AAPL"], clock=Ticks(started, done))
    assert result["started_at"] == started.isoformat() and result["fetched_at"] == done.isoformat()
    manifest = database.latest_analysis_snapshot(series.ANALYSIS_TYPE, "NASDAQ")
    assert manifest and manifest["published_at"] == done and manifest["inputs"]["started_at"] == started.isoformat()
    assert database.price_bars("NASDAQ", "AAPL", as_of=done)["2026-09-04"]["fetched_at"] == done.isoformat()
    assert service.series("NASDAQ", "AAPL", fetched_before=started + timedelta(seconds=30))["status"] == "no_vintage"  # the run was still fetching
    assert service.series("NASDAQ", "AAPL", fetched_before=done)["status"] == "no_vintage"  # strict <: a cut AT the availability instant sees nothing
    assert service.series("NASDAQ", "AAPL", fetched_before=done + timedelta(seconds=1))["status"] == "ok"


def test_a_cut_sees_exactly_one_vintage_and_never_completes_a_symbol_from_an_older_one() -> None:
    service, database, http = _service({"AAPL.US": [_bar("2026-09-03", 229.0), _bar("2026-09-04", 230.0)], "MSFT.US": [_bar("2026-09-04", 500.0)]})
    first = _run(service, "NASDAQ", ["AAPL", "MSFT"], now=NOW, mode="backfill")
    # S2: a 2:1 split restates AAPL's whole series; MSFT is missing from the provider that night
    http.bars_by_symbol["AAPL.US"] = [_bar("2026-09-03", 229.0, 114.5), _bar("2026-09-04", 230.0, 115.0)]
    http.bars_by_symbol["MSFT.US"] = []
    second = _run(service, "NASDAQ", ["AAPL", "MSFT"], now=NOW + 2 * D)
    assert second["symbols_missing"] == ["MSFT"] and second["bars_inserted"] == 2
    between, after = NOW + D, NOW + 3 * D
    s1, s2 = service.series("NASDAQ", "AAPL", fetched_before=between), service.series("NASDAQ", "AAPL", fetched_before=after)
    assert s1["status"] == "ok" and s1["price_snapshot_id"] == first["price_snapshot_id"] and s1["bars"]["2026-09-03"]["adjusted_close"] == 229.0
    assert s2["status"] == "ok" and s2["price_snapshot_id"] == second["price_snapshot_id"] and s2["bars"]["2026-09-03"]["adjusted_close"] == 114.5
    assert {b["fetched_at"] for b in s2["bars"].values()} == {(NOW + 2 * D).isoformat()}  # both sessions from S2, none from S1
    assert service.series("NASDAQ", "MSFT", fetched_before=between)["status"] == "ok"
    assert service.series("NASDAQ", "MSFT", fetched_before=after)["status"] == "symbol_not_in_vintage"  # S2 has no MSFT: refused, not S1's bar
    assert service.bars("NASDAQ", "MSFT", fetched_before=after) == {} and service.bars("NASDAQ", "AAPL", fetched_before=NOW) == {}
    # a vintage whose stored rows cannot reproduce its hash is refused (a foreign row appended under the vintage's clock)
    database._price_bars.append({**s2["bars"]["2026-09-04"], "id": "x", "session_date": "2026-09-02", "bar_sha256": "0" * 64, "fetched_at": (NOW + 2 * D).isoformat()})
    service._series_cache.clear()
    assert service.series("NASDAQ", "AAPL", fetched_before=after)["status"] == "vintage_mismatch"


def test_a_session_the_provider_dropped_makes_the_symbol_unreproducible_in_that_vintage() -> None:
    service, database, http = _service({"AAPL.US": [_bar("2026-09-03", 229.0), _bar("2026-09-04", 230.0)]})
    _run(service, "NASDAQ", ["AAPL"], now=NOW)
    http.bars_by_symbol["AAPL.US"] = [_bar("2026-09-04", 230.0)]  # 09-03 vanished from the provider
    second = _run(service, "NASDAQ", ["AAPL"], now=NOW + D)
    assert second["symbols_unreproducible"] == {"AAPL": ["2026-09-03"]} and second["series_bars"] == {"AAPL": 1}
    assert service.series("NASDAQ", "AAPL", fetched_before=NOW + 2 * D)["status"] == "vintage_unreproducible"
    assert service.series("NASDAQ", "AAPL", fetched_before=NOW + timedelta(hours=1))["status"] == "ok"  # the earlier vintage still reproduces


def test_clocks_are_real_instants_in_memory_as_in_postgres_and_a_batch_duplicate_is_one_row() -> None:
    service, database, http = _service({"AAPL.US": [_bar("2026-09-04", 230.0)]})
    _run(service, "NASDAQ", ["AAPL"], now=NOW)
    later_sp = (NOW + 4 * D).astimezone(ZoneInfo("America/Sao_Paulo"))  # 20:30 -03:00 sorts BEFORE "23:30" as a string
    http.bars_by_symbol["AAPL.US"] = [_bar("2026-09-04", 230.0, 57.5)]
    _run(service, "NASDAQ", ["AAPL"], now=later_sp)
    chain = database.price_bars("NASDAQ", "AAPL", as_of=NOW + 5 * D)
    assert chain["2026-09-04"]["adjusted_close"] == 57.5 and chain["2026-09-04"]["fetched_at"] == (NOW + 4 * D).isoformat()
    assert database.latest_price_bar_hashes("NASDAQ", ["AAPL"], source=series.SOURCE) == {("AAPL", "2026-09-04"): chain["2026-09-04"]["bar_sha256"]}
    assert service.series("NASDAQ", "AAPL", fetched_before=NOW + 5 * D)["bars"]["2026-09-04"]["adjusted_close"] == 57.5
    bar = series.bar_record("NYSE", "IBM", "IBM.US", _bar("2026-09-04", 250.0))
    assert bar is not None
    stamped = {**bar, "fetched_at": NOW.isoformat(), "snapshot_id": "s"}
    assert database.insert_price_bars([stamped, {**stamped, "id": "other"}]) == 1  # the same key twice in one batch: one row, like ON CONFLICT DO NOTHING
    assert database.insert_price_bars([{**stamped, "id": "third", "fetched_at": NOW.astimezone(ZoneInfo("America/Sao_Paulo")).isoformat()}]) == 0  # same instant


def test_labels_need_the_session_closed_before_the_cut_and_are_never_invented() -> None:
    service, database, http = _service({"AAPL.US": [_bar("2026-09-08", 231.0), _bar("2026-09-09", 232.0), _bar("2026-09-10", 233.0)],
                                        "PETR4.SA": [_bar("2026-09-08", 36.0), _bar("2026-09-09", 36.5)]})
    vintage_at = datetime(2026, 9, 11, 2, 0, tzinfo=timezone.utc)
    _run(service, "NASDAQ", ["AAPL"], now=vintage_at, start=date(2026, 9, 8), end=date(2026, 9, 10))
    _run(service, "B3", ["PETR4"], now=vintage_at, start=date(2026, 9, 8), end=date(2026, 9, 10))
    # 2026-09-07 is Labor Day (NYSE) and Independence Day (B3): two sessions after Friday 2026-09-04 is Wednesday 2026-09-09
    assert series.sessions_after("NASDAQ", date(2026, 9, 4), 2) == (date(2026, 9, 9), "ok") and series.sessions_after("B3", date(2026, 9, 4), 2) == (date(2026, 9, 9), "ok")
    assert series.sessions_after("NASDAQ", date(2026, 9, 7), 1) == (None, "not_a_session")  # Labor Day: said so, not "beyond calendar"
    assert series.sessions_after("NASDAQ", date(2026, 9, 4), 100000) == (None, "beyond_calendar")
    assert service.label_bar("NASDAQ", "AAPL", date(2026, 9, 7), 1, fetched_before=vintage_at + D)["status"] == "not_a_session"
    assert series.session_close("NASDAQ", date(2026, 9, 9)) == datetime(2026, 9, 9, 20, 0, tzinfo=timezone.utc)
    assert series.session_close("B3", date(2026, 9, 9)) == datetime(2026, 9, 9, 21, 0, tzinfo=timezone.utc)
    cut = vintage_at + D
    label = service.label_bar("NASDAQ", "AAPL", date(2026, 9, 4), 2, fetched_before=cut)
    assert label["status"] == "labelled" and label["session"] == "2026-09-09" and label["close"] == 232.0 and label["adjusted_close"] == 232.0
    assert label["bar_sha256"] == service.bars("NASDAQ", "AAPL", fetched_before=cut)["2026-09-09"]["bar_sha256"] and label["fetched_at"] == vintage_at.isoformat()
    assert label["price_snapshot_id"] == service.vintage("NASDAQ", fetched_before=cut)["price_snapshot_id"]  # type: ignore[index]
    # maturity is the exchange close, not the civil date: a cut during the session, or exactly at the close, is not mature
    assert service.label_bar("NASDAQ", "AAPL", date(2026, 9, 4), 2, fetched_before=datetime(2026, 9, 9, 14, 5, tzinfo=timezone.utc))["status"] == "not_yet_mature"
    assert service.label_bar("NASDAQ", "AAPL", date(2026, 9, 4), 2, fetched_before=datetime(2026, 9, 9, 20, 0, tzinfo=timezone.utc))["status"] == "not_yet_mature"
    assert service.label_bar("NASDAQ", "AAPL", date(2026, 9, 4), 2, fetched_before=datetime(2026, 9, 9, 20, 0, 1, tzinfo=timezone.utc))["status"] == "no_vintage"  # closed, but no vintage yet
    assert service.label_bar("B3", "PETR4", date(2026, 9, 4), 3, fetched_before=cut)["status"] == "missing_bar"  # B3 had a session on 09-10; the vintage has no bar
    assert service.label_bar("B3", "VALE3", date(2026, 9, 4), 2, fetched_before=cut)["status"] == "symbol_not_in_vintage"
    assert service.label_bar("NASDAQ", "AAPL", date(2026, 9, 4), 126, fetched_before=cut)["status"] == "not_yet_mature"


def test_a_newer_manifest_of_another_schema_never_hides_a_compatible_vintage() -> None:
    # C394-7: the vintage a cut sees is the latest COMPATIBLE manifest, not the latest of any schema
    service, database, http = _service({"AAPL.US": [_bar("2026-09-04", 230.0)]})
    first = _run(service, "NASDAQ", ["AAPL"], now=NOW)
    database.save_analysis_snapshot(series.ANALYSIS_TYPE, "NASDAQ", "mv-x", {"fetched_at": (NOW + D).isoformat()}, {"schema_version": "SOMETHING-ELSE"}, NOW + D)
    vintage = service.vintage("NASDAQ", fetched_before=NOW + 2 * D)
    assert vintage and vintage["price_snapshot_id"] == first["price_snapshot_id"]
    assert service.series("NASDAQ", "AAPL", fetched_before=NOW + 2 * D)["status"] == "ok"


def test_two_vintages_never_share_a_clock_and_duplicate_sessions_in_a_response_are_counted() -> None:
    # C394-9: the vintage must advance beyond the previous manifest; C394-10: an in-response duplicate is recorded, the first row wins
    service, database, http = _service({"AAPL.US": [_bar("2026-09-04", 230.0), _bar("2026-09-04", 999.0), _bar("2026-09-03", 229.0)]})
    result = _run(service, "NASDAQ", ["AAPL"], now=NOW)
    assert result["rows_duplicate_in_response"] == {"AAPL": 1} and result["rows_duplicate_total"] == 1 and result["series_bars"] == {"AAPL": 2}
    assert service.series("NASDAQ", "AAPL", fetched_before=NOW + D)["bars"]["2026-09-04"]["close"] == 230.0
    manifest = database.latest_analysis_snapshot(series.ANALYSIS_TYPE, "NASDAQ")
    assert manifest and manifest["outputs"]["rows_duplicate_in_response"] == {"AAPL": 1}
    import pytest
    with pytest.raises(ValueError, match="does not advance"):
        _run(service, "NASDAQ", ["AAPL"], now=NOW)  # the same clock again: refused, nothing written
    with pytest.raises(ValueError, match="does not advance"):
        _run(service, "NASDAQ", ["AAPL"], now=NOW - timedelta(seconds=1))
    assert len([s for s in database._analysis_snapshots if s["analysis_type"] == series.ANALYSIS_TYPE]) == 1


def test_a_session_outside_the_vintage_window_is_not_a_missing_bar() -> None:
    # C394-11: a narrower later window must not turn an existing session into "the exchange had no bar"
    service, database, http = _service({"AAPL.US": [_bar("2026-09-01", 228.0), _bar("2026-09-02", 228.5), _bar("2026-09-03", 229.0), _bar("2026-09-04", 230.0)]})
    _run(service, "NASDAQ", ["AAPL"], now=NOW, start=date(2026, 9, 1), end=date(2026, 9, 4))
    _run(service, "NASDAQ", ["AAPL"], now=NOW + D, start=date(2026, 9, 3), end=date(2026, 9, 4))
    assert service.label_bar("NASDAQ", "AAPL", date(2026, 9, 1), 1, fetched_before=NOW + timedelta(hours=1))["status"] == "labelled"  # under S1: 09-02 is there
    narrow = service.label_bar("NASDAQ", "AAPL", date(2026, 9, 1), 1, fetched_before=NOW + 2 * D)
    assert narrow["status"] == "outside_window" and narrow["session"] == "2026-09-02"
    assert service.label_bar("NASDAQ", "AAPL", date(2026, 9, 2), 1, fetched_before=NOW + 2 * D)["status"] == "labelled"  # 09-03 is inside S2


def test_postgresql_inserts_are_batched_inside_the_transaction() -> None:
    # C394-8: one executemany per chunk of 5000 bars, never one statement per bar
    class Cursor:
        def __init__(self, log: list[int]) -> None:
            self.log, self.rowcount = log, 0

        def executemany(self, sql: str, params: list[tuple]) -> None:
            assert "ON CONFLICT (market, symbol, session_date, source, fetched_at) DO NOTHING" in sql and len(params[0]) == 13
            self.log.append(len(params))
            self.rowcount = len(params)

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

    class Connection:
        def __init__(self) -> None:
            self.log: list[int] = []

        def cursor(self) -> Cursor:
            return Cursor(self.log)

    _, database, _ = _service({})
    bar = series.bar_record("NASDAQ", "AAPL", "AAPL.US", _bar("2026-09-04", 230.0))
    assert bar is not None
    bars = [{**bar, "id": str(i), "session_date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}"[:10], "fetched_at": NOW.isoformat(), "snapshot_id": "s"} for i in range(5001)]
    connection = Connection()
    assert database._insert_price_bars_pg(connection, bars) == 5001 and connection.log == [5000, 1]


def test_backfill_and_nightly_fetch_the_whole_window_and_the_phase_stays_dormant() -> None:
    service, database, http = _service({"AAPL.US": [_bar("2024-01-05", 180.0)], "BRK.B.US": [_bar("2026-01-05", 400.0), _bar("2024-01-05", 390.0)]})
    result = service.backfill("NASDAQ", months=36, now=NOW, symbols=["AAPL"])
    assert result["mode"] == "backfill" and http.calls[0]["params"]["from"] == "2023-09-01" and http.calls[0]["params"]["to"] == "2026-09-07"
    assert result["bars"] == 1 and service.last_run_at() is None  # the other markets have no manifest yet: the phase is not "done"
    assert series.window_start(date(2026, 9, 7), 36) == date(2023, 9, 1) and series.window_start(date(2026, 1, 15), 1) == date(2025, 12, 1)
    # the window defaults to the setting (not a dead knob), and a dotted ticker is requested exactly as it is persisted
    service.settings.valuation_price_history_backfill_months = 12
    shorter = service.backfill("NYSE", now=NOW, symbols=["BRK.B"])
    assert http.calls[-1]["params"]["from"] == "2025-09-01" and http.calls[-1]["url"].endswith("/api/eod/BRK.B.US")
    assert database.price_bars("NYSE", "BRK.B", as_of=NOW)["2026-01-05"]["provider_symbol"] == "BRK.B.US" and shorter["bars"] == 1  # 2024 is outside the window
    # the nightly vintage re-fetches the whole window for the coverage set (one call per symbol, unchanged bars cost nothing)
    database.save_analysis_snapshot("valuation_universe", "NYSE_UNIVERSE", "mv-1", {}, {"rows": [{"symbol": "BRK.B"}]}, NOW)
    nightly = service.nightly("NYSE", now=NOW + D)
    assert nightly["mode"] == "nightly" and http.calls[-1]["params"]["from"] == "2025-09-01" and nightly["bars_inserted"] == 0 and nightly["bars_unchanged"] == 1
    assert _settings().valuation_price_history_enabled is False  # dormant by default (rev 7 §2.2, mesa enables)
    sql = (Path(__file__).resolve().parents[2] / "db" / "049_valuation_price_history.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS valuation_price_bars" in sql and "UNIQUE (market, symbol, session_date, source, fetched_at)" in sql
    assert "BEFORE UPDATE OR DELETE ON valuation_price_bars" in sql and "BEFORE TRUNCATE ON valuation_price_bars" in sql
    assert "adjusted_close NUMERIC NOT NULL CHECK (adjusted_close > 0)" in sql and "REFERENCES analysis_snapshots(id)" in sql
