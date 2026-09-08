"""The V3.2 price series (rev 7 §2.2 / §9.2), rev 3: every run is ONE vintage in two facts — the CAPTURE (manifest +
changed bars in one transaction, ``fetched_at`` after the last provider answer) and, once committed, the PUBLICATION
(``available_at`` stamped immediately before its insert); a cut resolves the single vintage by the publications, so a
cut between capture and availability never sees it, now or later. One critical section per market (two runs racing
on the same clock leave exactly one vintage); every served bar has its content hash recomputed; three clocks per bar;
a session the run refused is ``label_unavailable:adjustment_unknown``, never ``missing_bar``. OFF by default; the
36-month backfill is an explicit one-shot run."""
from __future__ import annotations

import logging
import re
import threading
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app import valuation_price_history as series
from app import valuation_worker as worker
from app.config import Settings
from app.database import Database
from app.market_data.eodhd import EodhdClient

NOW = datetime(2026, 9, 7, 23, 30, tzinfo=timezone.utc)
D = timedelta(days=1)
S = timedelta(seconds=1)


class ScriptedHttp:
    """Answers /api/eod calls per provider symbol; records what was asked."""

    def __init__(self, bars_by_symbol: dict[str, list[dict]]) -> None:
        self.bars_by_symbol = bars_by_symbol
        self.calls: list[dict] = []
        self.barrier: threading.Barrier | None = None  # when set, every answer waits for the other racer (C394-9)

    def get_json(self, url: str, *, params=None, headers=None):
        self.calls.append({"url": url, "params": dict(params or {})})
        provider_symbol = url.rsplit("/", 1)[-1]
        if provider_symbol.split(".")[0] == "BOOM":
            raise RuntimeError("provider down")
        if self.barrier is not None:
            self.barrier.wait(timeout=5)
        return self.bars_by_symbol.get(provider_symbol, [])


class Ticks:
    """A scripted clock: one instant per call, in order (started_at, fetched_at = capture, available_at = publication) — exactly
    three per run, ``backfill``/``nightly`` included (R6); a fourth read raises IndexError."""

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


def _rows(database: Database, analysis_type: str, market: str) -> list[dict]:
    return [s for s in database._analysis_snapshots if s["analysis_type"] == analysis_type and s["entity_key"] == market]


def test_bars_need_both_closes_and_hash_their_content_not_their_clock() -> None:
    record = series.bar_record("NASDAQ", "AAPL", "AAPL.US", _bar("2026-09-04", 230.0, 229.5))
    assert record and record["close"] == 230.0 and record["adjusted_close"] == 229.5 and record["currency"] == "USD" and record["source"] == series.SOURCE
    assert len(record["bar_sha256"]) == 64 and "fetched_at" not in record  # the run stamps the clock; the hash is the content
    assert series.bar_record("NASDAQ", "AAPL", "AAPL.US", _bar("2026-09-04", 230.0, 229.5))["bar_sha256"] == record["bar_sha256"]  # type: ignore[index]
    assert series.bar_record("NASDAQ", "AAPL", "AAPL.US", _bar("2026-09-04", 230.0, 115.0))["bar_sha256"] != record["bar_sha256"]  # type: ignore[index]
    assert series.bar_record("NASDAQ", "AAPL", "AAPL.US", {"date": "2026-09-04", "close": 230.0}) is None  # adjusted_close mandatory
    assert series.bar_record("NASDAQ", "AAPL", "AAPL.US", {"date": "bad", "close": 1.0, "adjusted_close": 1.0}) is None
    assert series.bar_record("B3", "PETR4", "PETR4.SA", _bar("2026-09-04", 36.0))["currency"] == "BRL"  # type: ignore[index]
    # the reason a row is refused survives with its session (C394-14)
    assert series.bar_defects({"date": "2026-09-04", "close": 230.0}) == ("2026-09-04", ["adjusted_close"])
    assert series.bar_defects({"date": "2026-09-04", "close": 0, "adjusted_close": "x"}) == ("2026-09-04", ["close", "adjusted_close"])
    assert series.bar_defects({"date": "bad", "close": 1.0, "adjusted_close": 1.0}) == (None, ["date"]) and series.bar_defects(_bar("2026-09-04", 1.0)) == ("2026-09-04", [])
    # the content hash is recomputable from the stored fields (C394-13); prices are canonical at 6 decimals so NUMERIC gives the same float back
    assert series.bar_content_sha256({**record, "fetched_at": NOW.isoformat(), "snapshot_id": "s"}) == record["bar_sha256"]
    assert series.bar_content_sha256({**record, "adjusted_close": 229.4}) != record["bar_sha256"] and series.bar_content_sha256({**record, "close": None}) is None
    precise = series.bar_record("NASDAQ", "AAPL", "AAPL.US", _bar("2026-09-04", 33.333333333333336, 11.1111111111111119, 1e9 / 3))
    assert precise and precise["close"] == 33.333333 and precise["adjusted_close"] == 11.111111 and precise["volume"] == 333333333.333333


def test_coverage_is_the_universe_plus_every_symbol_with_v3_evaluations() -> None:
    service, database, _ = _service({})
    database.save_analysis_snapshot("valuation_universe", "NASDAQ_UNIVERSE", "mv-1", {"methodology_version": 7},
                                    {"rows": [{"symbol": "AAPL"}, {"symbol": "msft"}], "universe_size": 2}, NOW)
    database.save_analysis_snapshot("valuation_v3_shadow", "NASDAQ_V3_SHADOW", "mv-1", {"market": "NASDAQ"},
                                    {"results": {"AAPL": {}, "NVDA": {}, "OLDC": {}}}, NOW - 3 * D)
    assert service.coverage_symbols("NASDAQ") == ["AAPL", "MSFT", "NVDA", "OLDC"]  # a delisted-from-universe name keeps its labels coming


def test_a_run_is_one_vintage_captured_in_one_transaction_then_published_with_hashes_per_symbol_and_every_loss_recorded() -> None:
    service, database, http = _service({
        "AAPL.US": [_bar("2026-09-03", 229.0, 229.0), _bar("2026-09-04", 230.0, 230.0)],
        "MSFT.US": [_bar("2026-09-04", 500.0, 499.0), {"date": "2026-09-03", "close": 498.0}, _bar("2026-08-28", 1.0), {"date": "2026-08-27", "close": 2.0}],
    })  # an incomplete row inside the window; a row and an incomplete row outside it
    calls: list[str] = []
    real_persist, real_publish = database.persist_price_history_run, database.publish_price_history_run
    database.persist_price_history_run = lambda *a, **k: (calls.append("persist"), real_persist(*a, **k))[1]  # type: ignore[method-assign]
    database.publish_price_history_run = lambda *a, **k: (calls.append("publish"), real_publish(*a, **k))[1]  # type: ignore[method-assign]
    database.save_analysis_snapshot = lambda *a, **k: (calls.append("snapshot"), Database.save_analysis_snapshot(database, *a, **k))[1]  # type: ignore[method-assign]
    result = _run(service, "NASDAQ", ["AAPL", "MSFT", "NONE", "BOOM"], now=NOW)
    assert calls == ["persist", "snapshot", "publish", "snapshot"]  # capture (manifest + bars, one transactional write) BEFORE the publication row
    assert result["bars"] == 3 and result["bars_inserted"] == 3 and result["bars_unchanged"] == 0 and result["symbols_with_bars"] == 2
    assert result["symbols_missing"] == ["BOOM", "NONE"] and result["errors"] == {"BOOM": "RuntimeError"}
    assert result["rows_rejected"] == {"MSFT": [{"session": "2026-09-03", "missing": ["adjusted_close"]}]}  # the provider answered, the series refused: session + field
    assert result["rows_rejected_incomplete"] == {"MSFT": 1} and result["rows_rejected_total"] == 1  # the incomplete row OUTSIDE the window is not evidence
    assert result["first_session"] == "2026-09-03" and result["last_session"] == "2026-09-04" and len(result["bars_sha256"]) == 64
    assert set(result["series_sha256"]) == {"AAPL", "MSFT"} and result["series_bars"] == {"AAPL": 2, "MSFT": 1} and result["symbols_unreproducible"] == {}
    manifest = database.latest_analysis_snapshot(series.ANALYSIS_TYPE, "NASDAQ")
    assert manifest and manifest["id"] == result["price_snapshot_id"] and manifest["outputs"]["bars"] == 3 and manifest["inputs"]["mode"] == "nightly"
    assert manifest["inputs"]["calendar"] == {"name": "XNYS", "exchange_calendars": "4.13.2"} and manifest["inputs"]["started_at"] == NOW.isoformat()
    assert manifest["published_at"] == NOW and manifest["inputs"]["fetched_at"] == NOW.isoformat()  # the manifest's clock is the CAPTURE
    publication = database.latest_analysis_snapshot(series.PUBLICATION_TYPE, "NASDAQ")
    assert publication and publication["id"] == result["publication_id"] and publication["published_at"] == NOW == datetime.fromisoformat(result["available_at"])
    assert publication["inputs"] == {"schema_version": series.SCHEMA_VERSION, "price_snapshot_id": manifest["id"], "fetched_at": NOW.isoformat(),
                                     "started_at": NOW.isoformat(), "available_at": NOW.isoformat()}
    assert publication["outputs"] == {"schema_version": series.SCHEMA_VERSION, "bars_sha256": result["bars_sha256"], "price_snapshot_id": manifest["id"]}
    assert {call["params"]["from"] for call in http.calls} == {"2026-09-01"} and all("api_token" in call["params"] for call in http.calls)
    # the same content again at a later clock: a new vintage, NO new rows (content dedup) — and the series hashes are the same
    again = _run(service, "NASDAQ", ["AAPL", "MSFT"], now=NOW + D)
    assert again["bars"] == 3 and again["bars_inserted"] == 0 and again["bars_unchanged"] == 3 and again["series_sha256"] == result["series_sha256"]
    # a restated bar (split) inserts only the bars that changed, and the symbol's series hash moves
    http.bars_by_symbol["AAPL.US"] = [_bar("2026-09-03", 229.0, 114.5), _bar("2026-09-04", 230.0, 230.0)]
    restated = _run(service, "NASDAQ", ["AAPL", "MSFT"], now=NOW + 2 * D)
    assert restated["bars_inserted"] == 1 and restated["bars_unchanged"] == 2 and restated["series_sha256"]["AAPL"] != result["series_sha256"]["AAPL"]
    assert restated["series_sha256"]["MSFT"] == result["series_sha256"]["MSFT"]
    assert len(_rows(database, series.ANALYSIS_TYPE, "NASDAQ")) == 3 == len(_rows(database, series.PUBLICATION_TYPE, "NASDAQ"))


def test_a_vintage_is_available_at_its_publication_never_at_its_capture_so_a_cut_between_the_two_never_sees_it() -> None:
    # C394-2 residual: capture (response at 23:01) and publication (write at 23:03) are two facts; the cut 23:02 stays no_vintage for ever
    service, database, http = _service({"AAPL.US": [_bar("2026-09-04", 230.0)]})
    started, captured, published = (datetime(2026, 9, 7, 23, m, tzinfo=timezone.utc) for m in (0, 1, 3))
    result = service.persist_run("NASDAQ", start=date(2026, 9, 1), end=date(2026, 9, 4), symbols=["AAPL"], clock=Ticks(started, captured, published))
    assert result["started_at"] == started.isoformat() and result["fetched_at"] == captured.isoformat() and result["available_at"] == published.isoformat()
    manifest = database.latest_analysis_snapshot(series.ANALYSIS_TYPE, "NASDAQ")
    assert manifest and manifest["published_at"] == captured and manifest["inputs"]["started_at"] == started.isoformat()
    publication = database.latest_analysis_snapshot(series.PUBLICATION_TYPE, "NASDAQ")
    assert publication and publication["published_at"] == published and publication["inputs"]["fetched_at"] == captured.isoformat()
    assert database.price_bars("NASDAQ", "AAPL", as_of=captured)["2026-09-04"]["fetched_at"] == captured.isoformat()  # bars carry the CAPTURE
    for cut in (started + 30 * S, captured, captured + 60 * S, published):  # inside the run, at the capture, between capture and publication, AT the publication
        assert service.series("NASDAQ", "AAPL", available_before=cut)["status"] == "no_vintage", cut
        assert service.vintage("NASDAQ", available_before=cut) is None
    seen = service.series("NASDAQ", "AAPL", available_before=published + S)
    assert seen["status"] == "ok" and seen["available_at"] == published.isoformat() and seen["fetched_at"] == captured.isoformat()
    assert seen["first_captured_at"] == captured.isoformat() and seen["bars"]["2026-09-04"]["fetched_at"] == captured.isoformat()
    # a manifest WITHOUT publication (captured, never published) is invisible: the reader resolves by publications only
    database.save_analysis_snapshot(series.ANALYSIS_TYPE, "NASDAQ", "mv", {"schema_version": series.SCHEMA_VERSION, "fetched_at": (published + D).isoformat()},
                                    {"schema_version": series.SCHEMA_VERSION, "price_snapshot_id": "orphan", "series_sha256": {"AAPL": "0" * 64}}, published + D)
    later = service.series("NASDAQ", "AAPL", available_before=published + 2 * D)
    assert later["status"] == "ok" and later["price_snapshot_id"] == result["price_snapshot_id"]
    # a publication whose manifest does not attest what it claims is refused, never replaced by an older publication
    database.save_analysis_snapshot(series.PUBLICATION_TYPE, "NASDAQ", "mv", {"price_snapshot_id": result["price_snapshot_id"], "fetched_at": captured.isoformat()},
                                    {"schema_version": series.SCHEMA_VERSION, "bars_sha256": "f" * 64}, published + 3 * D)
    broken = service.series("NASDAQ", "AAPL", available_before=published + 4 * D)
    assert broken["status"] == "manifest_mismatch" and broken["bars"] == {} and broken["window"] is None
    assert service.label_bar("NASDAQ", "AAPL", date(2026, 9, 3), 1, available_before=published + 4 * D)["status"] == "manifest_mismatch"


def test_a_cut_sees_exactly_one_vintage_and_never_completes_a_symbol_from_an_older_one() -> None:
    service, database, http = _service({"AAPL.US": [_bar("2026-09-03", 229.0), _bar("2026-09-04", 230.0)], "MSFT.US": [_bar("2026-09-04", 500.0)]})
    first = _run(service, "NASDAQ", ["AAPL", "MSFT"], now=NOW, mode="backfill")
    # S2: a 2:1 split restates AAPL's whole series; MSFT is missing from the provider that night
    http.bars_by_symbol["AAPL.US"] = [_bar("2026-09-03", 229.0, 114.5), _bar("2026-09-04", 230.0, 115.0)]
    http.bars_by_symbol["MSFT.US"] = []
    second = _run(service, "NASDAQ", ["AAPL", "MSFT"], now=NOW + 2 * D)
    assert second["symbols_missing"] == ["MSFT"] and second["bars_inserted"] == 2
    between, after = NOW + D, NOW + 3 * D
    s1, s2 = service.series("NASDAQ", "AAPL", available_before=between), service.series("NASDAQ", "AAPL", available_before=after)
    assert s1["status"] == "ok" and s1["price_snapshot_id"] == first["price_snapshot_id"] and s1["bars"]["2026-09-03"]["adjusted_close"] == 229.0
    assert s2["status"] == "ok" and s2["price_snapshot_id"] == second["price_snapshot_id"] and s2["bars"]["2026-09-03"]["adjusted_close"] == 114.5
    assert {b["fetched_at"] for b in s2["bars"].values()} == {(NOW + 2 * D).isoformat()}  # both sessions from S2, none from S1
    assert service.series("NASDAQ", "MSFT", available_before=between)["status"] == "ok"
    assert service.series("NASDAQ", "MSFT", available_before=after)["status"] == "symbol_not_in_vintage"  # S2 has no MSFT: refused, not S1's bar
    assert service.bars("NASDAQ", "MSFT", available_before=after) == {} and service.bars("NASDAQ", "AAPL", available_before=NOW) == {}
    # a vintage whose stored rows cannot reproduce its hash is refused (a self-consistent foreign row appended under the vintage's clock)
    foreign = series.bar_record("NASDAQ", "AAPL", "AAPL.US", _bar("2026-09-02", 228.0))
    database._price_bars.append({**foreign, "fetched_at": (NOW + 2 * D).isoformat(), "snapshot_id": second["price_snapshot_id"]})  # type: ignore[dict-item]
    service._series_cache.clear()
    assert service.series("NASDAQ", "AAPL", available_before=after)["status"] == "vintage_mismatch"


def test_a_session_the_provider_dropped_makes_the_symbol_unreproducible_in_that_vintage() -> None:
    service, database, http = _service({"AAPL.US": [_bar("2026-09-03", 229.0), _bar("2026-09-04", 230.0)]})
    _run(service, "NASDAQ", ["AAPL"], now=NOW)
    http.bars_by_symbol["AAPL.US"] = [_bar("2026-09-04", 230.0)]  # 09-03 vanished from the provider
    second = _run(service, "NASDAQ", ["AAPL"], now=NOW + D)
    assert second["symbols_unreproducible"] == {"AAPL": ["2026-09-03"]} and second["series_bars"] == {"AAPL": 1}
    assert service.series("NASDAQ", "AAPL", available_before=NOW + 2 * D)["status"] == "vintage_unreproducible"
    assert service.series("NASDAQ", "AAPL", available_before=NOW + timedelta(hours=1))["status"] == "ok"  # the earlier vintage still reproduces


def test_clocks_are_real_instants_in_memory_as_in_postgres_and_a_batch_duplicate_is_one_row() -> None:
    service, database, http = _service({"AAPL.US": [_bar("2026-09-04", 230.0)]})
    _run(service, "NASDAQ", ["AAPL"], now=NOW)
    later_sp = (NOW + 4 * D).astimezone(ZoneInfo("America/Sao_Paulo"))  # 20:30 -03:00 sorts BEFORE "23:30" as a string
    http.bars_by_symbol["AAPL.US"] = [_bar("2026-09-04", 230.0, 57.5)]
    _run(service, "NASDAQ", ["AAPL"], now=later_sp)
    chain = database.price_bars("NASDAQ", "AAPL", as_of=NOW + 5 * D)
    assert chain["2026-09-04"]["adjusted_close"] == 57.5 and chain["2026-09-04"]["fetched_at"] == (NOW + 4 * D).isoformat()
    assert database.latest_price_bar_hashes("NASDAQ", ["AAPL"], source=series.SOURCE) == {("AAPL", "2026-09-04"): chain["2026-09-04"]["bar_sha256"]}
    assert service.series("NASDAQ", "AAPL", available_before=NOW + 5 * D)["bars"]["2026-09-04"]["adjusted_close"] == 57.5
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
    assert service.label_bar("NASDAQ", "AAPL", date(2026, 9, 7), 1, available_before=vintage_at + D)["status"] == "not_a_session"
    assert series.session_close("NASDAQ", date(2026, 9, 9)) == datetime(2026, 9, 9, 20, 0, tzinfo=timezone.utc)
    assert series.session_close("B3", date(2026, 9, 9)) == datetime(2026, 9, 9, 21, 0, tzinfo=timezone.utc)
    cut = vintage_at + D
    label = service.label_bar("NASDAQ", "AAPL", date(2026, 9, 4), 2, available_before=cut)
    assert label["status"] == "labelled" and label["session"] == "2026-09-09" and label["close"] == 232.0 and label["adjusted_close"] == 232.0
    assert label["bar_sha256"] == service.bars("NASDAQ", "AAPL", available_before=cut)["2026-09-09"]["bar_sha256"]
    assert label["available_at"] == label["fetched_at"] == label["first_captured_at"] == vintage_at.isoformat()  # one constant clock: the three coincide
    assert label["price_snapshot_id"] == service.vintage("NASDAQ", available_before=cut)["price_snapshot_id"]  # type: ignore[index]
    assert label["publication_id"] == service.vintage("NASDAQ", available_before=cut)["publication_id"]  # type: ignore[index]
    # maturity is the exchange close, not the civil date: a cut during the session, or exactly at the close, is not mature
    assert service.label_bar("NASDAQ", "AAPL", date(2026, 9, 4), 2, available_before=datetime(2026, 9, 9, 14, 5, tzinfo=timezone.utc))["status"] == "not_yet_mature"
    assert service.label_bar("NASDAQ", "AAPL", date(2026, 9, 4), 2, available_before=datetime(2026, 9, 9, 20, 0, tzinfo=timezone.utc))["status"] == "not_yet_mature"
    assert service.label_bar("NASDAQ", "AAPL", date(2026, 9, 4), 2, available_before=datetime(2026, 9, 9, 20, 0, 1, tzinfo=timezone.utc))["status"] == "no_vintage"  # closed, but no vintage yet
    assert service.label_bar("B3", "PETR4", date(2026, 9, 4), 3, available_before=cut)["status"] == "missing_bar"  # B3 had a session on 09-10; the provider gave nothing
    assert service.label_bar("B3", "VALE3", date(2026, 9, 4), 2, available_before=cut)["status"] == "symbol_not_in_vintage"
    assert service.label_bar("NASDAQ", "AAPL", date(2026, 9, 4), 126, available_before=cut)["status"] == "not_yet_mature"


def test_a_label_carries_the_availability_and_capture_of_the_chosen_vintage_and_the_first_capture_of_its_bar() -> None:
    # C394-12: under dedupe the bar row keeps S1's clock; the label must say S2's availability and capture, and S1's clock as first capture
    service, database, http = _service({"AAPL.US": [_bar("2026-09-03", 229.0), _bar("2026-09-04", 230.0)]})
    s1_started, s1_captured, s1_published = (datetime(2026, 9, 4, 23, m, tzinfo=timezone.utc) for m in (0, 1, 3))
    s2_started, s2_captured, s2_published = (datetime(2026, 9, 5, 23, m, tzinfo=timezone.utc) for m in (0, 2, 5))
    first = service.persist_run("NASDAQ", start=date(2026, 9, 1), end=date(2026, 9, 4), symbols=["AAPL"], clock=Ticks(s1_started, s1_captured, s1_published))
    http.bars_by_symbol["AAPL.US"] = [_bar("2026-09-03", 229.0), _bar("2026-09-04", 230.0, 115.0)]  # 09-03 unchanged (deduplicated), 09-04 restated
    second = service.persist_run("NASDAQ", start=date(2026, 9, 1), end=date(2026, 9, 4), symbols=["AAPL"], clock=Ticks(s2_started, s2_captured, s2_published))
    assert second["bars_inserted"] == 1 and second["bars_unchanged"] == 1
    cut = s2_published + S
    known = service.series("NASDAQ", "AAPL", available_before=cut)
    assert known["price_snapshot_id"] == second["price_snapshot_id"] and known["publication_id"] == second["publication_id"]
    assert known["available_at"] == s2_published.isoformat() and known["fetched_at"] == s2_captured.isoformat() and known["first_captured_at"] == s1_captured.isoformat()
    assert known["bars"]["2026-09-03"]["fetched_at"] == s1_captured.isoformat() and known["bars"]["2026-09-04"]["fetched_at"] == s2_captured.isoformat()
    kept = service.label_bar("NASDAQ", "AAPL", date(2026, 9, 2), 1, available_before=cut)  # 09-03: S1's row served by S2
    assert kept["status"] == "labelled" and kept["price_snapshot_id"] == second["price_snapshot_id"] and kept["publication_id"] == second["publication_id"]
    assert kept["available_at"] == s2_published.isoformat() and kept["fetched_at"] == s2_captured.isoformat() and kept["first_captured_at"] == s1_captured.isoformat()
    restated = service.label_bar("NASDAQ", "AAPL", date(2026, 9, 3), 1, available_before=cut)  # 09-04: S2's own row
    assert restated["adjusted_close"] == 115.0 and restated["first_captured_at"] == s2_captured.isoformat() and restated["available_at"] == s2_published.isoformat()
    under_s1 = service.label_bar("NASDAQ", "AAPL", date(2026, 9, 2), 1, available_before=s2_published)  # a cut at S2's availability still sees S1
    assert under_s1["price_snapshot_id"] == first["price_snapshot_id"] and under_s1["available_at"] == s1_published.isoformat()
    assert under_s1["fetched_at"] == under_s1["first_captured_at"] == s1_captured.isoformat()


def test_a_stored_bar_whose_content_no_longer_reproduces_its_hash_is_refused_and_readers_never_share_the_cache() -> None:
    # C394-13: the series hash aggregates declared bar hashes; a row altered under its old hash must not pass — and the cache must not leak
    service, database, http = _service({"AAPL.US": [_bar("2026-09-03", 229.0), _bar("2026-09-04", 230.0)]})
    _run(service, "NASDAQ", ["AAPL"], now=NOW)
    cut = NOW + D
    seen = service.series("NASDAQ", "AAPL", available_before=cut)
    assert seen["status"] == "ok" and seen["bars"]["2026-09-03"]["adjusted_close"] == 229.0
    seen["bars"]["2026-09-03"]["adjusted_close"] = 1.0  # a caller mutates what it got
    seen["bars"].pop("2026-09-04")
    seen["rejected_sessions"]["2026-09-03"] = ["close"]
    assert service.series("NASDAQ", "AAPL", available_before=cut)["bars"]["2026-09-03"]["adjusted_close"] == 229.0  # the cache did not move
    assert set(service.series("NASDAQ", "AAPL", available_before=cut)["bars"]) == {"2026-09-03", "2026-09-04"}
    assert service.series("NASDAQ", "AAPL", available_before=cut)["rejected_sessions"] == {}
    bars = service.bars("NASDAQ", "AAPL", available_before=cut)
    bars["2026-09-04"]["close"] = 0.0
    assert service.bars("NASDAQ", "AAPL", available_before=cut)["2026-09-04"]["close"] == 230.0
    assert service.label_bar("NASDAQ", "AAPL", date(2026, 9, 2), 1, available_before=cut)["adjusted_close"] == 229.0
    vintage = service.vintage("NASDAQ", available_before=cut)
    assert vintage and vintage["series_sha256"].pop("AAPL") and service.vintage("NASDAQ", available_before=cut)["series_sha256"]  # type: ignore[index]
    # the stored row is altered in place (adjusted_close), its hash kept: the recomputed content hash disagrees → refused, whole symbol
    row = next(b for b in database._price_bars if b["session_date"] == "2026-09-03")
    row["adjusted_close"] = 114.5
    service._series_cache.clear()
    tampered = service.series("NASDAQ", "AAPL", available_before=cut)
    assert tampered["status"] == "bar_hash_mismatch" and tampered["bars"] == {}
    assert service.label_bar("NASDAQ", "AAPL", date(2026, 9, 3), 1, available_before=cut)["status"] == "bar_hash_mismatch"  # even the untouched 09-04 bar
    row["adjusted_close"] = 229.0
    service._series_cache.clear()
    assert service.series("NASDAQ", "AAPL", available_before=cut)["status"] == "ok"


def test_a_session_the_run_refused_is_adjustment_unknown_never_missing_bar() -> None:
    # C394-14: the provider answered 09-10 without adjusted_close; the label says so with the field, and the manifest keeps symbol/session/field
    service, database, http = _service({"PETR4.SA": [_bar("2026-09-08", 36.0), _bar("2026-09-09", 36.5), {"date": "2026-09-10", "close": 37.0}],
                                        "VALE3.SA": [_bar("2026-09-08", 60.0), {"date": "2026-09-09", "adjusted_close": 61.0}, {"date": "2026-09-10", "close": "n/a"}]})
    vintage_at = datetime(2026, 9, 11, 2, 0, tzinfo=timezone.utc)
    result = _run(service, "B3", ["PETR4", "VALE3"], now=vintage_at, start=date(2026, 9, 8), end=date(2026, 9, 10))
    assert result["rows_rejected"] == {"PETR4": [{"session": "2026-09-10", "missing": ["adjusted_close"]}],
                                       "VALE3": [{"session": "2026-09-09", "missing": ["close"]}, {"session": "2026-09-10", "missing": ["close", "adjusted_close"]}]}
    assert result["rows_rejected_incomplete"] == {"PETR4": 1, "VALE3": 2} and result["rows_rejected_total"] == 3
    cut = vintage_at + D
    vintage = service.vintage("B3", available_before=cut)
    assert vintage and vintage["rows_rejected"] == result["rows_rejected"]
    assert service.series("B3", "PETR4", available_before=cut)["rejected_sessions"] == {"2026-09-10": ["adjusted_close"]}
    label = service.label_bar("B3", "PETR4", date(2026, 9, 4), 3, available_before=cut)  # 09-10: B3 had the session, the provider had no adjustment
    assert label["status"] == "label_unavailable:adjustment_unknown" and label["session"] == "2026-09-10" and label["missing"] == ["adjusted_close"]
    assert label["price_snapshot_id"] == result["price_snapshot_id"] and label["available_at"] == vintage_at.isoformat()
    assert service.label_bar("B3", "PETR4", date(2026, 9, 4), 2, available_before=cut)["status"] == "labelled"  # 09-09 is fine
    both = service.label_bar("B3", "VALE3", date(2026, 9, 4), 3, available_before=cut)
    assert both["status"] == "label_unavailable:adjustment_unknown" and both["missing"] == ["close", "adjusted_close"]
    assert service.label_bar("B3", "VALE3", date(2026, 9, 4), 2, available_before=cut)["missing"] == ["close"]
    # the SAME session with nothing from the provider is still missing_bar (the exchange had a session; no row at all)
    http.bars_by_symbol["PETR4.SA"] = [_bar("2026-09-08", 36.0), _bar("2026-09-09", 36.5)]
    _run(service, "B3", ["PETR4"], now=vintage_at + D, start=date(2026, 9, 8), end=date(2026, 9, 10))
    assert service.label_bar("B3", "PETR4", date(2026, 9, 4), 3, available_before=vintage_at + 2 * D)["status"] == "missing_bar"
    assert service.label_bar("B3", "PETR4", date(2026, 9, 4), 3, available_before=cut)["status"] == "label_unavailable:adjustment_unknown"  # the old cut is unchanged


def test_a_newer_manifest_or_publication_of_another_schema_never_hides_a_compatible_vintage() -> None:
    # C394-7: the vintage a cut sees is the latest COMPATIBLE publication, not the latest row of any schema
    service, database, http = _service({"AAPL.US": [_bar("2026-09-04", 230.0)]})
    first = _run(service, "NASDAQ", ["AAPL"], now=NOW)
    database.save_analysis_snapshot(series.ANALYSIS_TYPE, "NASDAQ", "mv-x", {"fetched_at": (NOW + D).isoformat()}, {"schema_version": "SOMETHING-ELSE"}, NOW + D)
    database.save_analysis_snapshot(series.PUBLICATION_TYPE, "NASDAQ", "mv-x", {"price_snapshot_id": "other", "fetched_at": (NOW + D).isoformat()},
                                    {"schema_version": "SOMETHING-ELSE"}, NOW + D)
    vintage = service.vintage("NASDAQ", available_before=NOW + 2 * D)
    assert vintage and vintage["price_snapshot_id"] == first["price_snapshot_id"] and vintage["publication_id"] == first["publication_id"]
    assert service.series("NASDAQ", "AAPL", available_before=NOW + 2 * D)["status"] == "ok"


def test_two_vintages_never_share_a_clock_and_duplicate_sessions_in_a_response_are_counted() -> None:
    # C394-9: the vintage must advance beyond the previous manifest AND publication; C394-10: an in-response duplicate is recorded, the first row wins
    service, database, http = _service({"AAPL.US": [_bar("2026-09-04", 230.0), _bar("2026-09-04", 999.0), _bar("2026-09-03", 229.0)]})
    result = _run(service, "NASDAQ", ["AAPL"], now=NOW)
    assert result["rows_duplicate_in_response"] == {"AAPL": 1} and result["rows_duplicate_total"] == 1 and result["series_bars"] == {"AAPL": 2}
    assert service.series("NASDAQ", "AAPL", available_before=NOW + D)["bars"]["2026-09-04"]["close"] == 230.0
    manifest = database.latest_analysis_snapshot(series.ANALYSIS_TYPE, "NASDAQ")
    assert manifest and manifest["outputs"]["rows_duplicate_in_response"] == {"AAPL": 1}
    with pytest.raises(ValueError, match="does not advance beyond the previous manifest"):
        _run(service, "NASDAQ", ["AAPL"], now=NOW)  # the same clock again: refused, nothing written
    with pytest.raises(ValueError, match="does not advance"):
        _run(service, "NASDAQ", ["AAPL"], now=NOW - S)
    # a capture that predates the previous PUBLICATION is refused too (the vintage would not be unique on the availability clock)
    published = service.persist_run("NASDAQ", start=date(2026, 9, 1), end=date(2026, 9, 10), symbols=["AAPL"], clock=Ticks(NOW + D, NOW + D + S, NOW + D + 60 * S))
    with pytest.raises(ValueError, match="does not advance beyond the previous publication"):
        service.persist_run("NASDAQ", start=date(2026, 9, 1), end=date(2026, 9, 10), symbols=["AAPL"], clock=Ticks(NOW + D + 2 * S, NOW + D + 30 * S, NOW + 2 * D))
    assert len(_rows(database, series.ANALYSIS_TYPE, "NASDAQ")) == 2 == len(_rows(database, series.PUBLICATION_TYPE, "NASDAQ"))
    assert service.vintage("NASDAQ", available_before=NOW + 2 * D)["price_snapshot_id"] == published["price_snapshot_id"]  # type: ignore[index]
    # the publication writer itself refuses a capture behind the previous publication's capture, or a clock that went backwards
    def inputs(captured: datetime) -> dict:  # a publication attests the capture it was checked against (R10)
        return {"schema_version": series.SCHEMA_VERSION, "price_snapshot_id": "x", "fetched_at": captured.isoformat(), "started_at": NOW.isoformat()}

    with pytest.raises(ValueError, match="does not advance beyond the capture the previous publication"):
        database.publish_price_history_run(series.PUBLICATION_TYPE, series.ANALYSIS_TYPE, "NASDAQ", "mv", inputs(NOW + D), {}, fetched_at=NOW + D, clock=lambda: NOW + 3 * D)
    with pytest.raises(ValueError, match="clock went backwards"):
        database.publish_price_history_run(series.PUBLICATION_TYPE, series.ANALYSIS_TYPE, "NASDAQ", "mv", inputs(NOW + 3 * D), {}, fetched_at=NOW + 3 * D,
                                           clock=lambda: NOW + 2 * D)
    with pytest.raises(ValueError, match="availability .* does not advance beyond the previous publication"):
        database.publish_price_history_run(series.PUBLICATION_TYPE, series.ANALYSIS_TYPE, "NASDAQ", "mv", inputs(NOW + D + 2 * S), {}, fetched_at=NOW + D + 2 * S,
                                           clock=lambda: NOW + D + 60 * S)  # the same availability instant as the previous publication
    assert len(_rows(database, series.PUBLICATION_TYPE, "NASDAQ")) == 2


def test_two_runs_racing_on_the_same_clock_leave_exactly_one_vintage() -> None:
    # C394-9 residual: both runs pass the fetch stage before either writes; the market's critical section admits ONE manifest + publication
    service, database, http = _service({"AAPL.US": [_bar("2026-09-04", 230.0)]})
    http.barrier = threading.Barrier(2)  # both provider answers are released together: both racers hold fetched_at = NOW before any write
    outcomes: dict[str, object] = {}

    def race(name: str) -> None:
        try:
            outcomes[name] = _run(service, "NASDAQ", ["AAPL"], now=NOW)
        except ValueError as error:
            outcomes[name] = error

    threads = [threading.Thread(target=race, args=(name,)) for name in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not any(thread.is_alive() for thread in threads)
    errors = [value for value in outcomes.values() if isinstance(value, ValueError)]
    assert len(errors) == 1 and "does not advance beyond the previous manifest" in str(errors[0]), outcomes
    assert len(_rows(database, series.ANALYSIS_TYPE, "NASDAQ")) == 1 == len(_rows(database, series.PUBLICATION_TYPE, "NASDAQ"))
    assert len(database._price_bars) == 1 and service.series("NASDAQ", "AAPL", available_before=NOW + S)["status"] == "ok"
    assert database.price_history_lock("NASDAQ") is database.price_history_lock("NASDAQ") and database.price_history_lock("B3") is not database.price_history_lock("NASDAQ")


def test_postgresql_writers_take_the_advisory_lock_first_and_refuse_before_writing() -> None:
    # the PostgreSQL path of C394-9 / R2: advisory lock → re-read both clocks → check → DEDUPE READ → build → manifest → bars → commit;
    # a stale capture writes nothing and never even reads the hashes
    class Result:
        def __init__(self, row=None, rows=()) -> None:
            self.row, self.rows = row, list(rows)

        def fetchone(self):
            return self.row

        def fetchall(self):
            return list(self.rows)

    class Cursor:
        def __init__(self, log: list[tuple[str, tuple]]) -> None:
            self.log, self.rowcount = log, 0

        def executemany(self, sql: str, params: list[tuple]) -> None:
            self.log.append(("EXECUTEMANY", (len(params),)))
            self.rowcount = len(params)

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

    class Connection:
        def __init__(self, manifest_row, publication_row, hashes=()) -> None:
            self.log: list[tuple[str, tuple]] = []
            self.rows = {"valuation_price_history": manifest_row, "valuation_price_history_publication": publication_row}
            self.hashes = list(hashes)
            self.committed = 0
            self.bars_allowed = False

        def execute(self, sql: str, params: tuple = ()) -> Result:
            self.log.append((" ".join(sql.split()), params))
            if sql.strip().startswith("SELECT id::text"):
                return Result(self.rows.get(params[0]))
            if sql.strip().startswith("SELECT DISTINCT ON (symbol, session_date)"):
                return Result(rows=self.hashes)
            return Result(None)

        def cursor(self) -> Cursor:
            assert self.bars_allowed, "no bars must be written"
            return Cursor(self.log)

        def commit(self) -> None:
            self.log.append(("COMMIT", ()))
            self.committed += 1

    _, database, _ = _service({})
    database.database_url = "postgresql://fake"
    connection = Connection(("m1", NOW), ("p1", NOW + 3 * S, NOW.isoformat()), hashes=[("AAPL", "2026-09-03", "a" * 64)])
    bar = series.bar_record("NASDAQ", "AAPL", "AAPL.US", _bar("2026-09-04", 230.0))
    assert bar is not None
    stamped = [{**bar, "fetched_at": (NOW + 10 * S).isoformat(), "snapshot_id": "s2"}]
    built: list[dict] = []

    def build(latest: dict) -> tuple[dict, dict, datetime, str, list[dict]]:
        built.append(latest)
        connection.log.append(("BUILD", (sorted(latest.items()),)))
        return {"a": 1}, {"b": 2}, NOW + 10 * S, "s2", stamped

    @contextmanager
    def fake_connection():
        yield connection

    database.connection = fake_connection  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="does not advance beyond the previous publication"):
        database.persist_price_history_run(series.ANALYSIS_TYPE, series.PUBLICATION_TYPE, "NASDAQ", "mv", fetched_at=NOW + 2 * S, symbols=["AAPL"], source=series.SOURCE,
                                           build=build)
    assert connection.log[0] == ("SELECT pg_advisory_xact_lock(hashtext(%s))", ("valuation_price_history:NASDAQ",))
    assert [entry[1][0] for entry in connection.log[1:3]] == ["valuation_price_history", "valuation_price_history_publication"]
    assert len(connection.log) == 3 and connection.committed == 0 and built == []  # nothing read for dedupe, nothing built, nothing inserted, nothing committed
    # T5: a phase's due is re-checked INSIDE the advisory-locked transaction, on the publication just re-read (p1 at NOW + 3 s ≥ due): refused as
    # "already published" after the lock and the two clock reads, before the dedupe read — a skip for the phase, nothing built or committed
    connection.log.clear()
    with pytest.raises(series.AlreadyPublishedError, match=re.escape(f"already published since {(NOW + 2 * S).isoformat()}: the latest publication of NASDAQ is at "
                                                                     f"{(NOW + 3 * S).isoformat()}")):
        database.persist_price_history_run(series.ANALYSIS_TYPE, series.PUBLICATION_TYPE, "NASDAQ", "mv", fetched_at=NOW + 10 * S, symbols=["AAPL"], source=series.SOURCE,
                                           build=build, due=NOW + 2 * S)
    assert connection.log[0][0].startswith("SELECT pg_advisory_xact_lock") and len(connection.log) == 3 and connection.committed == 0 and built == []
    connection.log.clear()
    with pytest.raises(ValueError, match="does not advance beyond the capture"):
        database.publish_price_history_run(series.PUBLICATION_TYPE, series.ANALYSIS_TYPE, "NASDAQ", "mv", {"fetched_at": NOW.isoformat()}, {}, fetched_at=NOW,
                                           clock=lambda: NOW + 9 * S)
    assert connection.log[0][0] == "SELECT pg_advisory_xact_lock(hashtext(%s))" and len(connection.log) == 3 and connection.committed == 0
    # a capture that advances (R2): lock → both clocks → DISTINCT ON hashes (same transaction) → build with those hashes → manifest → executemany → ONE commit
    connection.log.clear()
    connection.bars_allowed = True
    assert database.persist_price_history_run(series.ANALYSIS_TYPE, series.PUBLICATION_TYPE, "NASDAQ", "mv", fetched_at=NOW + 10 * S, symbols=["AAPL"],
                                              source=series.SOURCE, build=build) == 1
    steps = [entry[0].split("(")[0].split(" FROM")[0].strip() for entry in connection.log]
    assert steps == ["SELECT pg_advisory_xact_lock", "SELECT id::text, published_at", "SELECT id::text, published_at, inputs->>'fetched_at'",
                     "SELECT DISTINCT ON", "BUILD", "INSERT INTO analysis_snapshots", "EXECUTEMANY", "COMMIT"], steps
    assert built == [{("AAPL", "2026-09-03"): "a" * 64}]  # the builder got the hashes the transaction read
    dedupe = connection.log[3]
    assert "ORDER BY symbol, session_date, fetched_at DESC" in dedupe[0] and dedupe[1] == ("NASDAQ", series.SOURCE, ["AAPL"])
    insert = connection.log[5]
    assert insert[1][0] == "s2" and insert[1][1] == series.ANALYSIS_TYPE and insert[1][6] == NOW + 10 * S and insert[1][7] == "m1" and connection.committed == 1
    assert connection.log[6] == ("EXECUTEMANY", (1,))
    # a builder whose manifest clock is not the checked clock is refused (nothing written after the dedupe read)
    connection.log.clear()
    with pytest.raises(ValueError, match="differs from the checked clock"):
        database.persist_price_history_run(series.ANALYSIS_TYPE, series.PUBLICATION_TYPE, "NASDAQ", "mv", fetched_at=NOW + 11 * S, symbols=["AAPL"],
                                           source=series.SOURCE, build=build)
    assert [entry[0][:6] for entry in connection.log][-2:] == ["SELECT", "BUILD"] and connection.committed == 1
    connection.log.clear()

    def clock() -> datetime:
        connection.log.append(("CLOCK", ()))  # the availability stamp, logged where it happens
        return NOW + 12 * S

    publication_id, available_at = database.publish_price_history_run(series.PUBLICATION_TYPE, series.ANALYSIS_TYPE, "NASDAQ", "mv",
                                                                       {"fetched_at": (NOW + 10 * S).isoformat()}, {}, fetched_at=NOW + 10 * S, clock=clock)
    steps = [entry[0].split("(")[0].split(" FROM")[0].strip() for entry in connection.log]
    assert steps == ["SELECT pg_advisory_xact_lock", "SELECT id::text, published_at", "SELECT id::text, published_at, inputs->>'fetched_at'", "CLOCK",
                     "INSERT INTO analysis_snapshots", "COMMIT"]  # lock → re-read both clocks → check → stamp → insert: nothing between the stamp and the write
    insert = connection.log[-2]
    assert insert[1][0] == publication_id and insert[1][1] == series.PUBLICATION_TYPE
    assert insert[1][6] == available_at == NOW + 12 * S and insert[1][7] == "p1" and '"available_at": "' + available_at.isoformat() + '"' in insert[1][4]
    assert connection.committed == 2


def test_the_capture_builder_runs_under_the_market_lock_with_the_latest_hashes_and_the_store_keeps_its_own_copies() -> None:
    # R2 in memory: the dedupe read and the builder happen inside the critical section; R3: the manifest stored is not the builder's dicts
    service, database, http = _service({"AAPL.US": [_bar("2026-09-03", 229.0), _bar("2026-09-04", 230.0)]})
    first = _run(service, "NASDAQ", ["AAPL"], now=NOW)
    seen: list[object] = []
    outputs = {"schema_version": series.SCHEMA_VERSION, "price_snapshot_id": "m2", "series_sha256": {"AAPL": "x" * 64}, "nested": {"k": [1]}}

    def build(latest: dict) -> tuple[dict, dict, datetime, str, list[dict]]:
        lock = database.price_history_lock("NASDAQ")
        probe: list[bool] = []
        thread = threading.Thread(target=lambda: probe.append(lock.acquire(blocking=False)))
        thread.start()
        thread.join(timeout=5)
        seen.append((dict(latest), probe))
        return {"fetched_at": (NOW + S).isoformat()}, outputs, NOW + S, "m2", []

    assert database.persist_price_history_run(series.ANALYSIS_TYPE, series.PUBLICATION_TYPE, "NASDAQ", "mv", fetched_at=NOW + S, symbols=["AAPL"],
                                              source=series.SOURCE, build=build) == 0
    chain = database.price_bars("NASDAQ", "AAPL", as_of=NOW)
    assert seen == [({("AAPL", "2026-09-03"): chain["2026-09-03"]["bar_sha256"], ("AAPL", "2026-09-04"): chain["2026-09-04"]["bar_sha256"]}, [False])]  # held by the writer
    assert database.price_history_lock("NASDAQ").acquire(blocking=False)  # released once the capture returned
    database.price_history_lock("NASDAQ").release()
    outputs["nested"]["k"].append(2)
    outputs["series_sha256"]["AAPL"] = "y" * 64
    stored = database.analysis_snapshot_by_id("m2")
    assert stored and stored["outputs"]["nested"] == {"k": [1]} and stored["outputs"]["series_sha256"] == {"AAPL": "x" * 64}
    assert first["price_snapshot_id"] != "m2" and service.vintage("NASDAQ", available_before=NOW + D)["price_snapshot_id"] == first["price_snapshot_id"]  # type: ignore[index]


def test_a_session_the_provider_refused_after_storing_it_is_adjustment_unknown_not_unreproducible() -> None:
    # R1 (C394-14 on the realistic path): S1 stored 09-08/09-09/09-10; S2 answers 09-10 without adjusted_close. The provider answered — it is
    # not a vanished session: 09-10 under S2 is adjustment_unknown, 09-09 is labelled, the series is ok and nothing is "unreproducible"
    service, database, http = _service({"PETR4.SA": [_bar("2026-09-08", 36.0), _bar("2026-09-09", 36.5), _bar("2026-09-10", 37.0)]})
    s1_at = datetime(2026, 9, 11, 2, 0, tzinfo=timezone.utc)
    first = _run(service, "B3", ["PETR4"], now=s1_at, start=date(2026, 9, 8), end=date(2026, 9, 10))
    assert service.label_bar("B3", "PETR4", date(2026, 9, 4), 3, available_before=s1_at + timedelta(hours=1))["status"] == "labelled"
    http.bars_by_symbol["PETR4.SA"] = [_bar("2026-09-08", 36.0), _bar("2026-09-09", 36.5), {"date": "2026-09-10", "close": 37.0}]
    second = _run(service, "B3", ["PETR4"], now=s1_at + D, start=date(2026, 9, 8), end=date(2026, 9, 10))
    assert second["symbols_unreproducible"] == {} and second["rows_rejected"] == {"PETR4": [{"session": "2026-09-10", "missing": ["adjusted_close"]}]}
    assert second["series_bars"] == {"PETR4": 2} and second["bars_inserted"] == 0 and second["bars_unchanged"] == 2
    cut = s1_at + 2 * D
    known = service.series("B3", "PETR4", available_before=cut)
    assert known["status"] == "ok" and set(known["bars"]) == {"2026-09-08", "2026-09-09"} and known["price_snapshot_id"] == second["price_snapshot_id"]
    assert known["rejected_sessions"] == {"2026-09-10": ["adjusted_close"]}
    refused = service.label_bar("B3", "PETR4", date(2026, 9, 4), 3, available_before=cut)
    assert refused["status"] == "label_unavailable:adjustment_unknown" and refused["session"] == "2026-09-10" and refused["missing"] == ["adjusted_close"]
    assert refused["price_snapshot_id"] == second["price_snapshot_id"]
    labelled = service.label_bar("B3", "PETR4", date(2026, 9, 4), 2, available_before=cut)
    assert labelled["status"] == "labelled" and labelled["session"] == "2026-09-09" and labelled["close"] == 36.5
    # the older cut still serves S1's 09-10 (its own vintage), and S1's stored row is untouched
    assert service.label_bar("B3", "PETR4", date(2026, 9, 4), 3, available_before=s1_at + timedelta(hours=1))["price_snapshot_id"] == first["price_snapshot_id"]
    assert len([b for b in database._price_bars if b["session_date"] == "2026-09-10"]) == 1
    # a session with NO row at all is still a vanished session: unreproducible, refused
    http.bars_by_symbol["PETR4.SA"] = [_bar("2026-09-08", 36.0), _bar("2026-09-09", 36.5)]
    third = _run(service, "B3", ["PETR4"], now=s1_at + 2 * D, start=date(2026, 9, 8), end=date(2026, 9, 10))
    assert third["symbols_unreproducible"] == {"PETR4": ["2026-09-10"]}
    assert service.series("B3", "PETR4", available_before=s1_at + 3 * D)["status"] == "vintage_unreproducible"
    # an incomplete duplicate of a usable row is noise, not a refusal: the series keeps the bar and the manifest records no rejection
    http.bars_by_symbol["VALE3.SA"] = [_bar("2026-09-08", 60.0), {"date": "2026-09-08", "close": 60.0}, _bar("2026-09-09", 61.0)]
    fourth = _run(service, "B3", ["VALE3"], now=s1_at + 3 * D, start=date(2026, 9, 8), end=date(2026, 9, 10))
    assert fourth["rows_rejected"] == {} and fourth["rows_rejected_total"] == 0 and fourth["series_bars"] == {"VALE3": 2}
    assert service.label_bar("B3", "VALE3", date(2026, 9, 4), 1, available_before=s1_at + 4 * D)["status"] == "labelled"


def test_the_producers_result_is_a_deep_copy_never_the_stored_manifest() -> None:
    # R3: mutating what persist_run returned must not change the next read (in-memory store keeps its own dicts)
    service, database, http = _service({"PETR4.SA": [_bar("2026-09-08", 36.0), {"date": "2026-09-09", "close": 36.5}], "VALE3.SA": [_bar("2026-09-08", 60.0)]})
    result = _run(service, "B3", ["PETR4", "VALE3", "BOOM"], now=NOW, start=date(2026, 9, 8), end=date(2026, 9, 10))
    result["rows_rejected"]["PETR4"][0]["missing"].append("close")
    result["rows_rejected"]["VALE3"] = [{"session": "2026-09-08", "missing": ["close"]}]
    result["series_sha256"]["VALE3"] = "0" * 64
    result["symbols_unreproducible"]["PETR4"] = ["2026-09-08"]
    result["errors"]["VALE3"] = "Invented"
    result["symbols_missing"].append("VALE3")
    cut = NOW + 3 * D  # after the close of 2026-09-09 on B3
    vintage = service.vintage("B3", available_before=cut)
    assert vintage and vintage["rows_rejected"] == {"PETR4": [{"session": "2026-09-09", "missing": ["adjusted_close"]}]} and vintage["symbols_unreproducible"] == {}
    manifest = database.latest_analysis_snapshot(series.ANALYSIS_TYPE, "B3")
    assert manifest and manifest["outputs"]["errors"] == {"BOOM": "RuntimeError"} and manifest["outputs"]["symbols_missing"] == ["BOOM"]
    assert manifest["outputs"]["series_sha256"]["VALE3"] != "0" * 64
    assert service.series("B3", "VALE3", available_before=cut)["status"] == "ok" and service.series("B3", "PETR4", available_before=cut)["status"] == "ok"
    assert service.label_bar("B3", "PETR4", date(2026, 9, 4), 2, available_before=cut)["missing"] == ["adjusted_close"]


def test_a_publication_or_manifest_without_parseable_clocks_is_manifest_mismatch_never_an_exception() -> None:
    # R4: attestation also requires parseable inputs.fetched_at/from/to (manifest) and available_at (publication)
    service, database, http = _service({"AAPL.US": [_bar("2026-09-03", 229.0), _bar("2026-09-04", 230.0)]})
    first = _run(service, "NASDAQ", ["AAPL"], now=NOW)
    good = database.latest_analysis_snapshot(series.ANALYSIS_TYPE, "NASDAQ")
    assert good
    bars_hash = good["outputs"]["bars_sha256"]

    def publish(n: int, inputs: dict) -> None:
        database.save_analysis_snapshot(series.PUBLICATION_TYPE, "NASDAQ", "mv", inputs, {"schema_version": series.SCHEMA_VERSION, "bars_sha256": bars_hash,
                                                                                         "price_snapshot_id": inputs["price_snapshot_id"]}, NOW + n * D)

    def manifest(snapshot_id: str, inputs: dict, at: datetime) -> None:
        database.save_analysis_snapshot(series.ANALYSIS_TYPE, "NASDAQ", "mv", inputs, {**good["outputs"], "price_snapshot_id": snapshot_id}, at, snapshot_id=snapshot_id)

    # 1. a manifest WITHOUT fetched_at attested by a publication without fetched_at either (None == None would have passed the equality check)
    manifest("m-nofetch", {"schema_version": series.SCHEMA_VERSION, "from": "2026-09-01", "to": "2026-09-10"}, NOW + D)
    publish(1, {"schema_version": series.SCHEMA_VERSION, "price_snapshot_id": "m-nofetch", "started_at": NOW.isoformat(), "available_at": (NOW + D).isoformat()})
    broken = service.series("NASDAQ", "AAPL", available_before=NOW + D + S)
    assert broken["status"] == "manifest_mismatch" and broken["fetched_at"] is None and broken["bars"] == {}
    assert service.label_bar("NASDAQ", "AAPL", date(2026, 9, 3), 1, available_before=NOW + D + S)["status"] == "manifest_mismatch"
    # 2. a manifest whose window does not parse
    manifest("m-nowindow", {"schema_version": series.SCHEMA_VERSION, "fetched_at": (NOW + 2 * D).isoformat(), "from": "soon", "to": None}, NOW + 2 * D)
    publish(2, {"schema_version": series.SCHEMA_VERSION, "price_snapshot_id": "m-nowindow", "fetched_at": (NOW + 2 * D).isoformat(), "available_at": (NOW + 2 * D).isoformat()})
    assert service.series("NASDAQ", "AAPL", available_before=NOW + 2 * D + S)["status"] == "manifest_mismatch"
    # 3. a publication whose own available_at is missing or garbage
    manifest("m-fine", {"schema_version": series.SCHEMA_VERSION, "fetched_at": (NOW + 3 * D).isoformat(), "from": "2026-09-01", "to": "2026-09-10"}, NOW + 3 * D)
    publish(3, {"schema_version": series.SCHEMA_VERSION, "price_snapshot_id": "m-fine", "fetched_at": (NOW + 3 * D).isoformat()})
    assert service.series("NASDAQ", "AAPL", available_before=NOW + 3 * D + S)["status"] == "manifest_mismatch"
    publish(4, {"schema_version": series.SCHEMA_VERSION, "price_snapshot_id": "m-fine", "fetched_at": (NOW + 3 * D).isoformat(), "available_at": "yesterday"})
    assert service.series("NASDAQ", "AAPL", available_before=NOW + 4 * D + S)["status"] == "manifest_mismatch"
    # the same manifest with every clock parseable is served (the bars reproduce the same series hash)
    publish(5, {"schema_version": series.SCHEMA_VERSION, "price_snapshot_id": "m-fine", "fetched_at": (NOW + 3 * D).isoformat(), "available_at": (NOW + 5 * D).isoformat()})
    served = service.series("NASDAQ", "AAPL", available_before=NOW + 5 * D + S)
    assert served["status"] == "ok" and served["price_snapshot_id"] == "m-fine" and set(served["bars"]) == {"2026-09-03", "2026-09-04"}
    assert service.series("NASDAQ", "AAPL", available_before=NOW + S)["price_snapshot_id"] == first["price_snapshot_id"]


def test_a_refused_read_is_never_cached_so_a_manifest_that_appears_later_is_served() -> None:
    # R5: only status == ok enters the series cache
    service, database, http = _service({"AAPL.US": [_bar("2026-09-03", 229.0), _bar("2026-09-04", 230.0)]})
    result = _run(service, "NASDAQ", ["AAPL"], now=NOW)
    cut = NOW + D
    manifest = next(item for item in database._analysis_snapshots if item["id"] == result["price_snapshot_id"])
    database._analysis_snapshots.remove(manifest)  # the publication points to a manifest that is not there (yet)
    assert service.series("NASDAQ", "AAPL", available_before=cut)["status"] == "manifest_mismatch"
    assert service.label_bar("NASDAQ", "AAPL", date(2026, 9, 3), 1, available_before=cut)["status"] == "manifest_mismatch"
    assert service._series_cache == {}
    database._analysis_snapshots.append(manifest)  # the manifest appears
    served = service.series("NASDAQ", "AAPL", available_before=cut)
    assert served["status"] == "ok" and served["price_snapshot_id"] == result["price_snapshot_id"] and len(service._series_cache) == 1
    assert service.label_bar("NASDAQ", "AAPL", date(2026, 9, 3), 1, available_before=cut)["status"] == "labelled"
    # a symbol the vintage refuses is not cached either
    assert service.series("NASDAQ", "MSFT", available_before=cut)["status"] == "symbol_not_in_vintage" and len(service._series_cache) == 1


def test_backfill_and_nightly_read_a_scripted_clock_exactly_three_times() -> None:
    # R6: the window's end is the run's first tick (started_at); no fourth tick for the window
    service, database, http = _service({"AAPL.US": [_bar("2026-09-04", 230.0)]})
    started, captured, published = (datetime(2026, 9, 7, 23, m, tzinfo=timezone.utc) for m in (0, 1, 3))
    ticks = Ticks(started, captured, published)
    result = service.backfill("NASDAQ", months=1, symbols=["AAPL"], clock=ticks)
    assert ticks.instants == [] and result["started_at"] == started.isoformat() and result["fetched_at"] == captured.isoformat()
    assert result["available_at"] == published.isoformat() and (http.calls[-1]["params"]["from"], http.calls[-1]["params"]["to"]) == ("2026-08-01", "2026-09-07")
    database.save_analysis_snapshot("valuation_universe", "NASDAQ_UNIVERSE", "mv-1", {}, {"rows": [{"symbol": "AAPL"}]}, NOW)
    n_started, n_captured, n_published = (datetime(2026, 9, 8, 23, m, tzinfo=timezone.utc) for m in (0, 2, 5))
    ticks = Ticks(n_started, n_captured, n_published)
    nightly = service.nightly("NASDAQ", clock=ticks)
    assert ticks.instants == [] and nightly["started_at"] == n_started.isoformat() and nightly["available_at"] == n_published.isoformat()
    assert http.calls[-1]["params"]["to"] == "2026-09-08" and http.calls[-1]["params"]["from"] == "2023-09-01"
    with pytest.raises(IndexError):  # a fourth tick is never asked for: a two-tick script fails inside the run, not in the window arithmetic
        service.nightly("NASDAQ", clock=Ticks(datetime(2026, 9, 9, 23, 0, tzinfo=timezone.utc), datetime(2026, 9, 9, 23, 1, tzinfo=timezone.utc)))
    assert len(_rows(database, series.PUBLICATION_TYPE, "NASDAQ")) == 2  # the interrupted run published nothing (its capture stays captured-never-published)
    assert service.nightly("NASDAQ", now=NOW + 5 * D)["started_at"] == (NOW + 5 * D).isoformat()  # a constant clock still works


def test_a_run_with_no_bars_for_any_symbol_is_refused_and_the_previous_vintage_stays_served() -> None:
    # R8: the provider fully down (every symbol an error or an empty answer) must never publish an empty vintage over the previous one
    service, database, http = _service({"AAPL.US": [_bar("2026-09-03", 229.0), _bar("2026-09-04", 230.0)]})
    first = _run(service, "NASDAQ", ["AAPL"], now=NOW)
    http.bars_by_symbol["AAPL.US"] = []
    with pytest.raises(ValueError, match=r"provider returned no bars for 2 symbols of NASDAQ \(1 errors, 0 symbols with every row refused, 1 empty answers\)"):
        _run(service, "NASDAQ", ["AAPL", "BOOM"], now=NOW + D)
    with pytest.raises(ValueError, match=r"provider returned no bars for 1 symbols of NASDAQ \(0 errors, 0 symbols with every row refused, 1 empty answers\)"):
        service.backfill("NASDAQ", months=1, now=NOW + D, symbols=["AAPL"])
    # R13: a symbol the provider answered but whose EVERY row the series refused (a close missing) is counted apart from errors and empty answers
    http.bars_by_symbol["AAPL.US"] = [{"date": "2026-09-03", "close": 229.0}, {"date": "2026-09-04", "adjusted_close": 230.0}]
    http.bars_by_symbol["MSFT.US"] = [{"date": "2026-08-03", "close": 1.0}]  # refused AND outside the window: not evidence, an empty answer
    with pytest.raises(ValueError, match=r"provider returned no bars for 5 symbols of NASDAQ \(1 errors, 1 symbols with every row refused, 3 empty answers\)"):
        _run(service, "NASDAQ", ["AAPL", "BOOM", "NONE", "NADA", "MSFT"], now=NOW + D)
    assert len(_rows(database, series.ANALYSIS_TYPE, "NASDAQ")) == 1 == len(_rows(database, series.PUBLICATION_TYPE, "NASDAQ")) and len(database._price_bars) == 2
    later = service.series("NASDAQ", "AAPL", available_before=NOW + 2 * D)
    assert later["status"] == "ok" and later["price_snapshot_id"] == first["price_snapshot_id"] and len(later["bars"]) == 2
    assert service.label_bar("NASDAQ", "AAPL", date(2026, 9, 3), 1, available_before=NOW + 2 * D)["status"] == "labelled"
    # one symbol with bars is enough: the others are recorded as missing, as before
    http.bars_by_symbol["AAPL.US"] = [_bar("2026-09-04", 230.0)]
    partial = _run(service, "NASDAQ", ["AAPL", "BOOM", "NONE"], now=NOW + D)
    assert partial["symbols_with_bars"] == 1 and partial["symbols_missing"] == ["BOOM", "NONE"] and partial["errors"] == {"BOOM": "RuntimeError"}


def test_a_session_outside_the_vintage_window_is_not_a_missing_bar() -> None:
    # C394-11: a narrower later window must not turn an existing session into "the exchange had no bar"
    service, database, http = _service({"AAPL.US": [_bar("2026-09-01", 228.0), _bar("2026-09-02", 228.5), _bar("2026-09-03", 229.0), _bar("2026-09-04", 230.0)]})
    _run(service, "NASDAQ", ["AAPL"], now=NOW, start=date(2026, 9, 1), end=date(2026, 9, 4))
    _run(service, "NASDAQ", ["AAPL"], now=NOW + D, start=date(2026, 9, 3), end=date(2026, 9, 4))
    assert service.label_bar("NASDAQ", "AAPL", date(2026, 9, 1), 1, available_before=NOW + timedelta(hours=1))["status"] == "labelled"  # under S1: 09-02 is there
    narrow = service.label_bar("NASDAQ", "AAPL", date(2026, 9, 1), 1, available_before=NOW + 2 * D)
    assert narrow["status"] == "outside_window" and narrow["session"] == "2026-09-02"
    assert service.label_bar("NASDAQ", "AAPL", date(2026, 9, 2), 1, available_before=NOW + 2 * D)["status"] == "labelled"  # 09-03 is inside S2


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
    bars = [{**bar, "id": str(i), "session_date": (date(2013, 1, 1) + i * D).isoformat(), "fetched_at": NOW.isoformat(), "snapshot_id": "s"} for i in range(5001)]
    connection = Connection()  # 5001 real sessions: the parameter builder checks every bar (an invented month would be refused, as the DATE column refuses it)
    assert database._insert_price_bars_pg(connection, bars) == 5001 and connection.log == [5000, 1]


def test_backfill_and_nightly_fetch_the_whole_window_and_the_phase_stays_dormant() -> None:
    service, database, http = _service({"AAPL.US": [_bar("2024-01-05", 180.0)], "BRK.B.US": [_bar("2026-01-05", 400.0), _bar("2024-01-05", 390.0)],
                                        "PETR4.SA": [_bar("2026-09-04", 36.0)]})
    result = service.backfill("NASDAQ", months=36, now=NOW, symbols=["AAPL"])
    assert result["mode"] == "backfill" and http.calls[0]["params"]["from"] == "2023-09-01" and http.calls[0]["params"]["to"] == "2026-09-07"
    assert result["bars"] == 1 and service.last_run_at() is None  # the other markets have no publication yet: the phase is not "done"
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
    # last_run_at reads the PUBLICATIONS of every market: a manifest without publication does not complete the phase
    service.backfill("B3", now=NOW + D, symbols=["PETR4"])
    assert service.last_run_at() == NOW  # the earliest of the three latest publications (NASDAQ's)
    database.save_analysis_snapshot(series.ANALYSIS_TYPE, "NASDAQ", "mv", {}, {"schema_version": series.SCHEMA_VERSION}, NOW + 2 * D)  # captured, never published
    assert service.last_run_at() == NOW
    assert _settings().valuation_price_history_enabled is False  # dormant by default (rev 7 §2.2, mesa enables)
    sql = (Path(__file__).resolve().parents[2] / "db" / "049_valuation_price_history.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS valuation_price_bars" in sql and "UNIQUE (market, symbol, session_date, source, fetched_at)" in sql
    assert "BEFORE UPDATE OR DELETE ON valuation_price_bars" in sql and "BEFORE TRUNCATE ON valuation_price_bars" in sql
    assert "adjusted_close NUMERIC NOT NULL CHECK (adjusted_close > 0)" in sql and "REFERENCES analysis_snapshots(id)" in sql
    assert "valuation_price_history_publication" in sql and "pg_advisory_xact_lock" in sql  # the publication row and the lock are declared with the DDL


def test_run_all_gives_every_market_its_turn_and_fails_at_the_end_naming_only_the_refused_ones(caplog: pytest.LogCaptureFixture) -> None:
    # R9: B3 comes first in MARKETS; its refusal (an empty answer, R8) must not abort NASDAQ/NYSE — they publish, B3 does not, the phase still fails loudly
    service, database, http = _service({"AAPL.US": [_bar("2026-09-04", 230.0)], "IBM.US": [_bar("2026-09-04", 250.0)], "PETR4.SA": []})
    for market, symbol in (("B3", "PETR4"), ("NASDAQ", "AAPL"), ("NYSE", "IBM")):
        database.save_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE", "mv-1", {}, {"rows": [{"symbol": symbol}]}, NOW)
    assert series.MARKETS == ("B3", "NASDAQ", "NYSE")
    with caplog.at_level(logging.ERROR, logger="app.valuation_price_history"):
        with pytest.raises(ValueError) as refused:
            service.run_all(now=NOW)
    message = str(refused.value)
    assert message.startswith("valuation_price_history nightly failed for B3 (2 of 3 markets published): B3: ValueError: provider returned no bars for 1 symbols of B3")
    assert "NASDAQ" not in message and "NYSE" not in message  # the failed markets only
    logged = [record for record in caplog.records if record.name == "app.valuation_price_history"]
    assert [record.getMessage() for record in logged] == ["valuation_price_history B3 nightly failed; the other markets still run"]
    assert logged[0].levelno == logging.ERROR and logged[0].exc_info and "provider returned no bars for 1 symbols of B3" in str(logged[0].exc_info[1])
    assert {call["url"].rsplit("/", 1)[-1] for call in http.calls} == {"PETR4.SA", "AAPL.US", "IBM.US"}  # every market was asked
    assert len(_rows(database, series.PUBLICATION_TYPE, "NASDAQ")) == 1 == len(_rows(database, series.PUBLICATION_TYPE, "NYSE"))
    assert _rows(database, series.ANALYSIS_TYPE, "B3") == [] == _rows(database, series.PUBLICATION_TYPE, "B3")
    assert service.series("NASDAQ", "AAPL", available_before=NOW + S)["status"] == "ok" and service.series("NYSE", "IBM", available_before=NOW + S)["status"] == "ok"
    assert service.vintage("B3", available_before=NOW + S) is None and service.last_run_at() is None  # B3 has no publication: the phase is not complete
    # two markets refused (B3 no coverage, NYSE provider down): both named, NASDAQ published
    database._analysis_snapshots[:] = [item for item in database._analysis_snapshots if item["entity_key"] != "B3_UNIVERSE"]
    http.bars_by_symbol["IBM.US"] = []
    with pytest.raises(ValueError, match=r"nightly failed for B3, NYSE \(1 of 3 markets published\): B3: ValueError: no symbols to fetch for B3.*; NYSE: ValueError: provider"):
        service.run_all(now=NOW + D)
    assert len(_rows(database, series.PUBLICATION_TYPE, "NASDAQ")) == 2 and len(_rows(database, series.PUBLICATION_TYPE, "NYSE")) == 1
    # every market fine: the three results, no exception, the phase complete
    database.save_analysis_snapshot("valuation_universe", "B3_UNIVERSE", "mv-1", {}, {"rows": [{"symbol": "PETR4"}]}, NOW)
    http.bars_by_symbol["PETR4.SA"], http.bars_by_symbol["IBM.US"] = [_bar("2026-09-04", 36.0)], [_bar("2026-09-04", 250.0)]
    results = service.run_all(now=NOW + 2 * D)
    assert set(results) == set(series.MARKETS) and all(result["symbols_with_bars"] == 1 for result in results.values())
    assert service.last_run_at() == NOW + 2 * D


def test_a_previous_publication_without_a_parseable_capture_is_refused_by_name_and_never_written_in_the_first_place() -> None:
    # R10 in memory: the writers name the poisoned publication instead of dying on a parse error — and refuse to write such a row themselves
    service, database, http = _service({"AAPL.US": [_bar("2026-09-04", 230.0)]})
    first = _run(service, "NASDAQ", ["AAPL"], now=NOW)
    good = {"schema_version": series.SCHEMA_VERSION, "price_snapshot_id": first["price_snapshot_id"]}
    database.price_history_lock = lambda market: pytest.fail(f"the lock of {market} was taken before the attestation check")  # type: ignore[method-assign]
    for attested in ({}, {"fetched_at": None}, {"fetched_at": ""}, {"fetched_at": "x"}, {"fetched_at": (NOW + 2 * S).isoformat()},
                     {"fetched_at": NOW + S}, {"fetched_at": (NOW + S).replace(tzinfo=None)}):  # S6: the checked instant itself, but not an ISO-8601 string
        with pytest.raises(ValueError, match=rf"publication of NASDAQ attests fetched_at {re.escape(repr(attested.get('fetched_at')))}, not the checked capture "
                                             + re.escape((NOW + S).isoformat()) + " as an ISO-8601 string"):
            database.publish_price_history_run(series.PUBLICATION_TYPE, series.ANALYSIS_TYPE, "NASDAQ", "mv", {**good, **attested}, {}, fetched_at=NOW + S,
                                               clock=lambda: pytest.fail("never stamped"))
    del database.price_history_lock
    assert len(_rows(database, series.PUBLICATION_TYPE, "NASDAQ")) == 1  # nothing written
    # the same instant with another offset IS the checked capture
    same_instant = (NOW + S).astimezone(ZoneInfo("America/Sao_Paulo")).isoformat()
    publication_id, _ = database.publish_price_history_run(series.PUBLICATION_TYPE, series.ANALYSIS_TYPE, "NASDAQ", "mv", {**good, "fetched_at": same_instant}, {},
                                                           fetched_at=NOW + S, clock=lambda: NOW + 2 * S)
    assert database.analysis_snapshot_by_id(publication_id)["inputs"]["fetched_at"] == same_instant  # type: ignore[index]
    # a poisoned row that got in by another door: every writer refuses it BY ID, nothing is written, and the readers refuse it without an exception
    for poison, at in (("garbage", NOW + D), (None, NOW + 2 * D)):
        poisoned = database.save_analysis_snapshot(series.PUBLICATION_TYPE, "NASDAQ", "mv", {**good, "fetched_at": poison, "available_at": at.isoformat()},
                                                   {**good, "bars_sha256": first["bars_sha256"]}, at)
        expected = rf"previous publication {poisoned} of NASDAQ has no parseable fetched_at \({poison!r}\)"
        with pytest.raises(ValueError, match=expected):
            _run(service, "NASDAQ", ["AAPL"], now=at + D)
        with pytest.raises(ValueError, match=expected):
            database.publish_price_history_run(series.PUBLICATION_TYPE, series.ANALYSIS_TYPE, "NASDAQ", "mv", {**good, "fetched_at": (at + D).isoformat()}, {},
                                               fetched_at=at + D, clock=lambda: at + D)
        assert service.series("NASDAQ", "AAPL", available_before=at + S)["status"] == "manifest_mismatch"
    assert len(_rows(database, series.ANALYSIS_TYPE, "NASDAQ")) == 1 and len(_rows(database, series.PUBLICATION_TYPE, "NASDAQ")) == 4 and len(database._price_bars) == 1
    assert service.series("NASDAQ", "AAPL", available_before=NOW + S)["price_snapshot_id"] == first["price_snapshot_id"]


def test_postgresql_writers_refuse_a_previous_publication_without_a_parseable_capture_by_name() -> None:
    # R10 on the PostgreSQL path: lock → both clocks re-read → the poisoned publication named → nothing read for dedupe, built, inserted or committed
    class Result:
        def __init__(self, row=None) -> None:
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        def __init__(self, publication_row) -> None:
            self.log: list[str] = []
            self.rows = {"valuation_price_history": ("m1", NOW), "valuation_price_history_publication": publication_row}
            self.committed = 0

        def execute(self, sql: str, params: tuple = ()) -> Result:
            self.log.append(" ".join(sql.split()).split(" FROM")[0])
            assert sql.strip().startswith(("SELECT pg_advisory_xact_lock", "SELECT id::text")), sql  # never the dedupe read, never an insert
            return Result(self.rows.get(params[0])) if sql.strip().startswith("SELECT id::text") else Result()

        def cursor(self):
            raise AssertionError("no bars must be written")

        def commit(self) -> None:
            self.committed += 1

    _, database, _ = _service({})
    database.database_url = "postgresql://fake"
    connection = Connection(("p-bad", NOW + 3 * S, "garbage"))

    @contextmanager
    def fake_connection():
        yield connection

    database.connection = fake_connection  # type: ignore[method-assign]
    previous_clocks = ["SELECT pg_advisory_xact_lock(hashtext(%s))", "SELECT id::text, published_at", "SELECT id::text, published_at, inputs->>'fetched_at'"]
    for poisoned, raw in (("p-bad", "garbage"), ("p-none", None)):
        connection.rows["valuation_price_history_publication"] = (poisoned, NOW + 3 * S, raw)
        expected = rf"previous publication {poisoned} of NASDAQ has no parseable fetched_at \({raw!r}\)"
        connection.log.clear()
        with pytest.raises(ValueError, match=expected):
            database.persist_price_history_run(series.ANALYSIS_TYPE, series.PUBLICATION_TYPE, "NASDAQ", "mv", fetched_at=NOW + 10 * S, symbols=["AAPL"],
                                               source=series.SOURCE, build=lambda latest: pytest.fail("never built"))
        assert connection.log == previous_clocks and connection.committed == 0
        connection.log.clear()
        with pytest.raises(ValueError, match=expected):
            database.publish_price_history_run(series.PUBLICATION_TYPE, series.ANALYSIS_TYPE, "NASDAQ", "mv", {"fetched_at": (NOW + 10 * S).isoformat()}, {},
                                               fetched_at=NOW + 10 * S, clock=lambda: pytest.fail("never stamped"))
        assert connection.log == previous_clocks and connection.committed == 0
    # a publication whose inputs do not attest the checked capture is refused BEFORE the lock: nothing read, nothing written
    connection.log.clear()
    with pytest.raises(ValueError, match="publication of NASDAQ attests fetched_at 'x', not the checked capture"):
        database.publish_price_history_run(series.PUBLICATION_TYPE, series.ANALYSIS_TYPE, "NASDAQ", "mv", {"fetched_at": "x"}, {}, fetched_at=NOW + 10 * S,
                                           clock=lambda: NOW + 12 * S)
    assert connection.log == [] and connection.committed == 0
    # S6: the checked capture as a datetime (json.dumps would fail inside the transaction) is refused before the lock too
    with pytest.raises(ValueError, match=r"publication of NASDAQ attests fetched_at datetime\.datetime\(.*\), not the checked capture .* as an ISO-8601 string"):
        database.publish_price_history_run(series.PUBLICATION_TYPE, series.ANALYSIS_TYPE, "NASDAQ", "mv", {"fetched_at": NOW + 10 * S}, {}, fetched_at=NOW + 10 * S,
                                           clock=lambda: pytest.fail("never stamped"))
    assert connection.log == [] and connection.committed == 0


def test_a_publication_whose_attested_availability_is_not_its_own_clock_is_manifest_mismatch() -> None:
    # R11: inputs.available_at must be the instant of the row's published_at (the clock a cut is compared with); a claim is refused, never served
    service, database, http = _service({"AAPL.US": [_bar("2026-09-03", 229.0), _bar("2026-09-04", 230.0)]})
    first = _run(service, "NASDAQ", ["AAPL"], now=NOW)
    good = {"schema_version": series.SCHEMA_VERSION, "price_snapshot_id": first["price_snapshot_id"]}
    outputs = {**good, "bars_sha256": first["bars_sha256"]}

    def publish(claimed: str, published_at: datetime) -> None:
        database.save_analysis_snapshot(series.PUBLICATION_TYPE, "NASDAQ", "mv", {**good, "fetched_at": NOW.isoformat(), "available_at": claimed}, outputs, published_at)

    publish((NOW + D).isoformat(), NOW + 2 * D)  # claims an availability a day BEFORE the row's clock (a retro-dated vintage)
    lied = service.series("NASDAQ", "AAPL", available_before=NOW + 2 * D + S)
    assert lied["status"] == "manifest_mismatch" and lied["bars"] == {} and lied["available_at"] == (NOW + 2 * D).isoformat()  # the header says the row's clock
    assert service.label_bar("NASDAQ", "AAPL", date(2026, 9, 3), 1, available_before=NOW + 2 * D + S)["status"] == "manifest_mismatch"
    publish((NOW + 4 * D).isoformat(), NOW + 3 * D)  # claims a LATER one
    assert service.series("NASDAQ", "AAPL", available_before=NOW + 3 * D + S)["status"] == "manifest_mismatch"
    assert service.vintage("NASDAQ", available_before=NOW + 3 * D + S)["status"] == "manifest_mismatch"  # type: ignore[index]
    publish((NOW + 5 * D).astimezone(ZoneInfo("America/Sao_Paulo")).isoformat(), NOW + 5 * D)  # the same instant in another offset: attested
    served = service.series("NASDAQ", "AAPL", available_before=NOW + 5 * D + S)
    assert served["status"] == "ok" and served["available_at"] == (NOW + 5 * D).isoformat() and served["price_snapshot_id"] == first["price_snapshot_id"]
    assert service.series("NASDAQ", "AAPL", available_before=NOW + S)["status"] == "ok"  # the writer's own publication: available_at == published_at by construction


def test_the_memory_double_stores_and_returns_deep_copies_and_a_capture_with_a_malformed_bar_leaves_nothing_behind() -> None:
    # R12: the publication writer stores deep copies, analysis_snapshot_by_id returns one, and the capture is atomic (as psycopg's rollback makes it in PostgreSQL)
    _, database, _ = _service({})
    inputs = {"price_snapshot_id": "m1", "fetched_at": NOW.isoformat(), "nested": {"k": [1]}}
    outputs = {"bars_sha256": "a" * 64, "tags": ["a"]}
    publication_id, _ = database.publish_price_history_run(series.PUBLICATION_TYPE, series.ANALYSIS_TYPE, "NASDAQ", "mv", inputs, outputs, fetched_at=NOW,
                                                           clock=lambda: NOW + S)
    inputs["nested"]["k"].append(2)
    inputs["price_snapshot_id"] = "other"
    outputs["tags"].append("b")
    stored = database.analysis_snapshot_by_id(publication_id)
    assert stored and stored["inputs"] == {"price_snapshot_id": "m1", "fetched_at": NOW.isoformat(), "nested": {"k": [1]}, "available_at": (NOW + S).isoformat()}
    assert stored["outputs"] == {"bars_sha256": "a" * 64, "tags": ["a"]}
    stored["inputs"]["nested"]["k"].append(3)
    stored["outputs"]["tags"].clear()
    again = database.analysis_snapshot_by_id(publication_id)
    assert again and again["inputs"]["nested"] == {"k": [1]} and again["outputs"]["tags"] == ["a"]
    # a builder that hands back a malformed bar (a NOT NULL column missing, an unparseable clock) writes NO manifest and NO bar
    bar = series.bar_record("NASDAQ", "AAPL", "AAPL.US", _bar("2026-09-04", 230.0))
    assert bar is not None
    good = {**bar, "fetched_at": (NOW + 2 * S).isoformat(), "snapshot_id": "m2"}

    def capture(snapshot_id: str, at: datetime, bars: list[dict]):
        return lambda latest: ({"fetched_at": at.isoformat()}, {"schema_version": series.SCHEMA_VERSION}, at, snapshot_id, bars)

    for broken, reason in (({key: value for key, value in good.items() if key != "currency"}, r"price bar 'AAPL' '2026-09-04' lacks currency"),
                           ({**good, "bar_sha256": None, "snapshot_id": None}, "lacks snapshot_id, bar_sha256"),
                           ({**good, "fetched_at": "soon"}, r"price bar 'AAPL' '2026-09-04' has no parseable fetched_at \('soon'\)")):
        with pytest.raises(ValueError, match=reason):
            database.persist_price_history_run(series.ANALYSIS_TYPE, series.PUBLICATION_TYPE, "NASDAQ", "mv", fetched_at=NOW + 2 * S, symbols=["AAPL"],
                                               source=series.SOURCE, build=capture("m2", NOW + 2 * S, [good, broken]))
        assert database.analysis_snapshot_by_id("m2") is None and database._price_bars == [] and _rows(database, series.ANALYSIS_TYPE, "NASDAQ") == []
        with pytest.raises(ValueError, match=reason):
            database.insert_price_bars([broken])
        assert database._price_bars == []
    # the same capture with well-formed bars then succeeds at the SAME clock: proof the refused ones left no manifest behind
    assert database.persist_price_history_run(series.ANALYSIS_TYPE, series.PUBLICATION_TYPE, "NASDAQ", "mv", fetched_at=NOW + 2 * S, symbols=["AAPL"],
                                              source=series.SOURCE, build=capture("m2", NOW + 2 * S, [good])) == 1
    assert database.analysis_snapshot_by_id("m2") and len(database._price_bars) == 1
    # and if the append itself failed after the manifest was written, the manifest is rolled back (what psycopg's context manager does for PostgreSQL):
    # that row alone, removed from the list (S3) — a row of another type that shares the id (in by another door) and every other row stay, untouched
    database.save_analysis_snapshot("valuation_universe", "NASDAQ_UNIVERSE", "mv", {}, {"rows": []}, NOW, snapshot_id="m3")
    before = list(database._analysis_snapshots)
    database._append_price_bars_memory = lambda prepared: (_ for _ in ()).throw(RuntimeError("disk full"))  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="disk full"):
        database.persist_price_history_run(series.ANALYSIS_TYPE, series.PUBLICATION_TYPE, "NASDAQ", "mv", fetched_at=NOW + 3 * S, symbols=["AAPL"],
                                           source=series.SOURCE, build=capture("m3", NOW + 3 * S, [{**good, "fetched_at": (NOW + 3 * S).isoformat(), "snapshot_id": "m3"}]))
    assert len(database._analysis_snapshots) == len(before) and all(kept is seeded for kept, seeded in zip(database._analysis_snapshots, before))
    foreign = database.analysis_snapshot_by_id("m3")
    assert foreign and foreign["analysis_type"] == "valuation_universe"  # the foreign row with the same id survived: only the manifest row was removed
    assert len(_rows(database, series.ANALYSIS_TYPE, "NASDAQ")) == 1 and len(database._price_bars) == 1
    # the PostgreSQL parameter builder refuses the same bars (inside the transaction: nothing committed)
    with pytest.raises(ValueError, match="lacks currency"):
        Database._price_bar_params({key: value for key, value in good.items() if key != "currency"})


def test_a_run_with_no_symbols_to_fetch_is_refused_before_any_request_and_never_an_empty_vintage() -> None:
    # R14: an empty coverage set (no universe row, no V3 shadow symbol) is not a vintage: refused before the clock, the provider or the store are touched
    service, database, http = _service({"AAPL.US": [_bar("2026-09-04", 230.0)]})
    first = _run(service, "NASDAQ", ["AAPL"], now=NOW)
    for symbols in ([], ["", "  "]):
        with pytest.raises(ValueError, match="no symbols to fetch for NASDAQ: an empty vintage is refused"):
            _run(service, "NASDAQ", symbols, now=NOW + D)
    with pytest.raises(ValueError, match="no symbols to fetch for NASDAQ"):  # refused before the clock is read: an empty script never raises IndexError
        service.persist_run("NASDAQ", start=date(2026, 9, 1), end=date(2026, 9, 10), symbols=[], clock=Ticks())
    with pytest.raises(ValueError, match="no symbols to fetch for NASDAQ"):  # S2: backfill/nightly refuse BEFORE their first tick (the window's end) too
        service.backfill("NASDAQ", months=1, symbols=[], clock=Ticks())
    with pytest.raises(ValueError, match="no symbols to fetch for NASDAQ"):
        service.backfill("NASDAQ", months=1, symbols=["", "  "], clock=Ticks())
    assert service.coverage_symbols("B3") == []
    with pytest.raises(ValueError, match="no symbols to fetch for B3"):
        service.nightly("B3", clock=Ticks())
    untouched = Ticks(NOW + D)
    with pytest.raises(ValueError, match="no symbols to fetch for B3"):
        service.nightly("B3", now=NOW + D, clock=untouched)
    assert untouched.instants == [NOW + D]  # the scripted instant was never consumed
    assert len(http.calls) == 1  # only the first run asked the provider
    assert len(_rows(database, series.ANALYSIS_TYPE, "NASDAQ")) == 1 == len(_rows(database, series.PUBLICATION_TYPE, "NASDAQ")) and len(database._price_bars) == 1
    assert _rows(database, series.ANALYSIS_TYPE, "B3") == [] == _rows(database, series.PUBLICATION_TYPE, "B3")
    assert service.series("NASDAQ", "AAPL", available_before=NOW + 2 * D)["price_snapshot_id"] == first["price_snapshot_id"]  # the previous vintage stays served
    assert service.vintage("B3", available_before=NOW + 2 * D) is None


def test_run_all_skips_the_markets_already_published_since_the_phase_came_due_so_a_retry_re_runs_only_the_failed_one(caplog: pytest.LogCaptureFixture) -> None:
    # S1: B3 has no coverage and the worker retries the phase every 30 minutes until 08h — NASDAQ/NYSE are fetched and published ONCE, B3 refused each time
    service, database, http = _service({"AAPL.US": [_bar("2026-09-04", 230.0)], "IBM.US": [_bar("2026-09-04", 250.0)], "PETR4.SA": [_bar("2026-09-04", 36.0)]})
    for market, symbol in (("NASDAQ", "AAPL"), ("NYSE", "IBM")):
        database.save_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE", "mv-1", {}, {"rows": [{"symbol": symbol}]}, NOW)
    tonight = datetime(2026, 9, 8, 4, 5, tzinfo=timezone.utc)  # 01:05 America/Sao_Paulo of 2026-09-08: the phase came due at 01:00 (04:00 UTC)
    due = datetime(2026, 9, 8, 4, 0, tzinfo=timezone.utc)
    assert series.offhours_due_at(tonight) == due
    attempts = [tonight + n * timedelta(minutes=30) for n in range(3)]
    with caplog.at_level(logging.INFO, logger="app.valuation_price_history"):
        for attempt in attempts:
            with pytest.raises(ValueError) as refused:
                service.run_all(now=attempt)
            note = "" if attempt == tonight else f", 2 already published since {due.isoformat()}"
            assert str(refused.value).startswith(f"valuation_price_history nightly failed for B3 (2 of 3 markets published{note}): B3: ValueError: no symbols to fetch for B3")
            assert service.last_run_at() is None  # B3 never published: the worker keeps the phase due (and retries) — without re-running the others
    calls = sorted(call["url"].rsplit("/", 1)[-1] for call in http.calls)
    assert calls == ["AAPL.US", "IBM.US"]  # the provider was consulted exactly once per published market, never for B3
    assert len(_rows(database, series.PUBLICATION_TYPE, "NASDAQ")) == 1 == len(_rows(database, series.PUBLICATION_TYPE, "NYSE"))  # published exactly once
    assert len(_rows(database, series.ANALYSIS_TYPE, "NASDAQ")) == 1 == len(_rows(database, series.ANALYSIS_TYPE, "NYSE"))
    assert _rows(database, series.ANALYSIS_TYPE, "B3") == [] == _rows(database, series.PUBLICATION_TYPE, "B3")
    skipped = [record.getMessage() for record in caplog.records if record.name == "app.valuation_price_history" and "skipped" in record.getMessage()]
    assert skipped == [f"valuation_price_history {market} already published at {tonight.isoformat()} (phase due {due.isoformat()}): skipped"
                       for _ in attempts[1:] for market in ("NASDAQ", "NYSE")]
    # B3 gets coverage on the next retry: B3 alone runs, the others are recorded as skipped with their availability, the phase completes
    database.save_analysis_snapshot("valuation_universe", "B3_UNIVERSE", "mv-1", {}, {"rows": [{"symbol": "PETR4"}]}, NOW)
    fourth = attempts[-1] + timedelta(minutes=30)
    results = service.run_all(now=fourth)
    assert results["NASDAQ"] == results["NYSE"] == {"skipped": "already published", "available_at": tonight.isoformat()}
    assert results["B3"]["mode"] == "nightly" and results["B3"]["available_at"] == fourth.isoformat() and results["B3"]["symbols_with_bars"] == 1
    assert sorted(call["url"].rsplit("/", 1)[-1] for call in http.calls) == ["AAPL.US", "IBM.US", "PETR4.SA"]
    assert service.last_run_at() == tonight and not worker._phase_is_due(service.last_run_at(), worker.start_of_today(tonight.astimezone(worker.SAO_PAULO))
                                                                                                + timedelta(hours=worker.OFFHOURS_START_HOUR))  # the worker agrees
    # the next night every market is due again (its publication precedes the new due instant): all three run, nothing skipped
    next_night = tonight + D
    results = service.run_all(now=next_night)
    assert all(result["mode"] == "nightly" and result["available_at"] == next_night.isoformat() for result in results.values())
    assert all(len(_rows(database, series.PUBLICATION_TYPE, market)) == 2 for market in series.MARKETS) and len(http.calls) == 6
    # an explicit due instant (the worker's phase due, when handed over) is honoured: everything published at/after it is skipped, nothing asked
    assert service.run_all(now=next_night + timedelta(hours=2), due_at=next_night) == {market: {"skipped": "already published", "available_at": next_night.isoformat()}
                                                                                       for market in series.MARKETS}
    assert service.run_all(next_night + timedelta(hours=2), due_at=next_night.astimezone(ZoneInfo("America/Sao_Paulo")))["B3"]["skipped"] == "already published"
    assert len(http.calls) == 6 and all(len(_rows(database, series.PUBLICATION_TYPE, market)) == 2 for market in series.MARKETS)
    # a due instant one second after the publications: nothing is skipped (a publication BEFORE the due is last night's)
    with pytest.raises(ValueError, match="does not advance beyond the previous manifest"):  # the constant clock refuses the re-run: proof it was attempted
        service.run_all(now=next_night, due_at=next_night + S)
    # the real clock by default (no argument): the due is derived from it; with no coverage anywhere nothing is asked and nothing ticks
    empty, _, empty_http = _service({})
    with pytest.raises(ValueError, match=r"nightly failed for B3, NASDAQ, NYSE \(0 of 3 markets published\): B3: ValueError: no symbols to fetch for B3"):
        empty.run_all()
    assert empty_http.calls == []


def test_the_phase_due_convention_is_the_workers() -> None:
    # S1: run_all's default due instant is exactly the worker's OffhoursPhase due (start_of_today(now) + start_hour, America/Sao_Paulo), in UTC
    assert series.OFFHOURS_DUE_HOUR == worker.OFFHOURS_START_HOUR == worker.OffhoursPhase("price_history", lambda: None, lambda: None).start_hour
    assert series.SAO_PAULO.key == worker.SAO_PAULO.key == "America/Sao_Paulo"
    for now in (datetime(2026, 9, 8, 4, 5, tzinfo=timezone.utc), datetime(2026, 9, 8, 1, 30, tzinfo=timezone.utc),  # 22:30 of the 7th in São Paulo
                datetime(2026, 9, 8, 0, 30, tzinfo=worker.SAO_PAULO), datetime(2026, 9, 8, 12, 0), NOW,
                datetime(2026, 9, 8, 0, 0), datetime(2026, 9, 8, 1, 30), datetime(2026, 9, 8, 2, 59, 59)):  # naive = São Paulo wall time, as the worker reads it (T2)
        local = now if now.tzinfo is None else now.astimezone(worker.SAO_PAULO)  # the worker's start_of_today reads a naive date as the local date: no conversion
        expected = worker.start_of_today(local) + timedelta(hours=worker.OFFHOURS_START_HOUR)
        assert series.offhours_due_at(now) == expected and series.offhours_due_at(now).tzinfo is timezone.utc
        # the skip rule is the complement of the worker's due rule: a publication at/after the due is "done", one before it is "due"
        assert not worker._phase_is_due(expected, expected) and worker._phase_is_due(expected - S, expected)
    assert series.offhours_due_at(datetime(2026, 9, 8, 1, 30, tzinfo=timezone.utc)) == datetime(2026, 9, 7, 4, 0, tzinfo=timezone.utc)
    assert series.offhours_due_at(datetime(2026, 9, 8, 4, 5, tzinfo=timezone.utc)) == datetime(2026, 9, 8, 4, 0, tzinfo=timezone.utc)
    # T2: a NAIVE 01:30 is 01:30 in São Paulo — the phase of the 8th came due at 01:00 (04:00 UTC) — never 01:30 UTC (22:30 of the 7th: the eve's due)
    naive = datetime(2026, 9, 8, 1, 30)
    assert series.offhours_due_at(naive) == worker.start_of_today(naive) + timedelta(hours=worker.OFFHOURS_START_HOUR) == datetime(2026, 9, 8, 4, 0, tzinfo=timezone.utc)
    assert series.offhours_due_at(naive) != series.offhours_due_at(naive.replace(tzinfo=timezone.utc)) == datetime(2026, 9, 7, 4, 0, tzinfo=timezone.utc)
    assert series._worker_instant(naive) == naive.replace(tzinfo=worker.SAO_PAULO) == datetime(2026, 9, 8, 4, 30, tzinfo=timezone.utc)
    assert worker._phase_is_due(naive, worker.start_of_today(naive) + timedelta(hours=2)) and not worker._phase_is_due(naive, series.offhours_due_at(naive))
    # run_all reads a naive now AND a naive due_at the same way, for the skip and for the run's own clock
    service, database, http = _service({"AAPL.US": [_bar("2026-09-04", 230.0)], "IBM.US": [_bar("2026-09-04", 250.0)], "PETR4.SA": [_bar("2026-09-04", 36.0)]})
    for market, symbol in (("B3", "PETR4"), ("NASDAQ", "AAPL"), ("NYSE", "IBM")):
        database.save_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE", "mv-1", {}, {"rows": [{"symbol": symbol}]}, NOW)
    tonight = datetime(2026, 9, 8, 4, 5, tzinfo=timezone.utc)  # 01:05 in São Paulo
    service.run_all(now=tonight)
    assert service.run_all(now=naive, due_at=datetime(2026, 9, 8, 1, 0)) == {market: {"skipped": "already published", "available_at": tonight.isoformat()}
                                                                            for market in series.MARKETS}  # due 01:00 SP ≤ 01:05 SP: skipped
    assert all(result["skipped"] == "already published" for result in service.run_all(now=naive).values())  # the default due of a naive 01:30 SP is 01:00 SP of the 8th
    again = service.run_all(now=naive, due_at=datetime(2026, 9, 8, 1, 10))  # due 01:10 SP > 01:05 SP: due again — read as UTC it would be 22:10 of the eve and skip
    assert all(result["mode"] == "nightly" and result["available_at"] == datetime(2026, 9, 8, 4, 30, tzinfo=timezone.utc).isoformat() for result in again.values())
    assert all(len(_rows(database, series.PUBLICATION_TYPE, market)) == 2 for market in series.MARKETS)  # the run's clock was 01:30 SP = 04:30 UTC, not 01:30 UTC


def test_the_memory_double_returns_deep_copies_from_every_snapshot_reader() -> None:
    # S4: latest_analysis_snapshot / latest_analysis_snapshot_before hand out deep copies (PostgreSQL decodes fresh JSON on every read)
    service, database, http = _service({"AAPL.US": [_bar("2026-09-04", 230.0)]})
    database.save_analysis_snapshot("valuation_universe", "NASDAQ_UNIVERSE", "mv", {"n": {"k": [1]}}, {"rows": [{"symbol": "AAPL"}], "schema_version": "x"}, NOW)
    for read in (lambda: database.latest_analysis_snapshot("valuation_universe", "NASDAQ_UNIVERSE"),
                 lambda: database.latest_analysis_snapshot_before("valuation_universe", "NASDAQ_UNIVERSE", NOW + S),
                 lambda: database.latest_analysis_snapshot_before("valuation_universe", "NASDAQ_UNIVERSE", NOW + S, schema_version="x")):
        got = read()
        assert got and got["outputs"]["rows"] == [{"symbol": "AAPL"}] and got["inputs"]["n"] == {"k": [1]}
        got["outputs"]["rows"].append({"symbol": "EVIL"})
        got["outputs"]["rows"][0]["symbol"] = "MSFT"
        got["inputs"]["n"]["k"].clear()
        got["outputs"]["schema_version"] = "y"
        again = read()
        assert again and again["outputs"]["rows"] == [{"symbol": "AAPL"}] and again["inputs"]["n"] == {"k": [1]} and again["outputs"]["schema_version"] == "x"
    assert service.coverage_symbols("NASDAQ") == ["AAPL"]
    # the publication a reader resolves is a copy too: mutating what vintage() read never poisons the next cut
    first = _run(service, "NASDAQ", ["AAPL"], now=NOW + D)
    publication = database.latest_analysis_snapshot_before(series.PUBLICATION_TYPE, "NASDAQ", NOW + 2 * D, schema_version=series.SCHEMA_VERSION)
    assert publication and publication["id"] == first["publication_id"]
    publication["inputs"]["price_snapshot_id"] = "elsewhere"
    publication["outputs"]["bars_sha256"] = "0" * 64
    assert service.vintage("NASDAQ", available_before=NOW + 2 * D)["status"] == "ok"  # type: ignore[index]
    assert service.series("NASDAQ", "AAPL", available_before=NOW + 2 * D)["price_snapshot_id"] == first["price_snapshot_id"]


def test_the_memory_double_mirrors_the_ddl_checks_on_market_prices_and_hash() -> None:
    # S5: what migration 049 refuses with a CHECK, the in-memory double refuses before any write — and the PostgreSQL parameter builder alike
    _, database, _ = _service({})
    sql = (Path(__file__).resolve().parents[2] / "db" / "049_valuation_price_history.sql").read_text(encoding="utf-8")
    assert Database._PRICE_BAR_MARKETS == series.MARKETS and "market TEXT NOT NULL CHECK (market IN ('B3', 'NASDAQ', 'NYSE'))" in sql
    assert "close NUMERIC NOT NULL CHECK (close > 0)" in sql and "adjusted_close NUMERIC NOT NULL CHECK (adjusted_close > 0)" in sql
    assert "bar_sha256 TEXT NOT NULL CHECK (bar_sha256 ~ '^[0-9a-f]{64}$')" in sql and Database._PRICE_BAR_SHA256.pattern == "^[0-9a-f]{64}$"
    bar = series.bar_record("NASDAQ", "AAPL", "AAPL.US", _bar("2026-09-04", 230.0))
    assert bar is not None
    good = {**bar, "fetched_at": NOW.isoformat(), "snapshot_id": "m1"}
    cases = (
        ({**good, "market": "LSE"}, r"price bar 'AAPL' '2026-09-04' has market 'LSE', not one of B3, NASDAQ, NYSE"),
        ({**good, "market": "nasdaq"}, r"has market 'nasdaq', not one of B3, NASDAQ, NYSE"),
        ({**good, "close": 0}, r"price bar 'AAPL' '2026-09-04' has close 0, not a number > 0"),
        ({**good, "adjusted_close": -1.5}, r"has adjusted_close -1\.5, not a number > 0"),
        ({**good, "close": "230.0"}, r"has close '230\.0', not a number > 0"),
        ({**good, "close": True}, r"has close True, not a number > 0"),
        ({**good, "adjusted_close": float("nan")}, r"has adjusted_close nan, not a number > 0"),
        ({**good, "adjusted_close": float("inf")}, r"has adjusted_close inf, not a number > 0"),
        ({**good, "bar_sha256": "A" * 64}, r"price bar 'AAPL' '2026-09-04' has bar_sha256 'A{64}', not 64 lowercase hex characters"),
        ({**good, "bar_sha256": "a" * 63}, r"not 64 lowercase hex characters"),
        ({**good, "bar_sha256": "a" * 64 + "\n"}, r"not 64 lowercase hex characters"),
        ({**good, "bar_sha256": 12345}, r"has bar_sha256 12345, not 64 lowercase hex characters"),
        # T4: session_date must be a canonical ISO date (the DATE column; the series compares sessions as text), volume a finite number when present
        ({**good, "session_date": "soon"}, r"price bar 'AAPL' 'soon' has session_date 'soon', not an ISO date \(YYYY-MM-DD\)"),
        ({**good, "session_date": "2026-9-4"}, r"has session_date '2026-9-4', not an ISO date"),
        ({**good, "session_date": "20260904"}, r"has session_date '20260904', not an ISO date"),
        ({**good, "session_date": "2026-13-01"}, r"has session_date '2026-13-01', not an ISO date"),
        ({**good, "session_date": 20260904}, r"has session_date 20260904, not an ISO date"),
        ({**good, "session_date": datetime(2026, 9, 4)}, r"has session_date datetime\.datetime\(2026, 9, 4, 0, 0\), not an ISO date"),
        ({**good, "volume": True}, r"price bar 'AAPL' '2026-09-04' has volume True, not a finite number"),
        ({**good, "volume": "1000"}, r"has volume '1000', not a finite number"),
        ({**good, "volume": float("nan")}, r"has volume nan, not a finite number"),
        ({**good, "volume": float("-inf")}, r"has volume -inf, not a finite number"),
        ({**good, "volume": Decimal("NaN")}, r"has volume Decimal\('NaN'\), not a finite number"),
        ({**good, "volume": Decimal("Infinity")}, r"has volume Decimal\('Infinity'\), not a finite number"),
    )
    for broken, reason in cases:
        with pytest.raises(ValueError, match=reason):
            database.insert_price_bars([good, broken])
        assert database._price_bars == []
        with pytest.raises(ValueError, match=reason):
            Database._price_bar_params(broken)
        with pytest.raises(ValueError, match=reason):
            database.persist_price_history_run(series.ANALYSIS_TYPE, series.PUBLICATION_TYPE, "NASDAQ", "mv", fetched_at=NOW, symbols=["AAPL"], source=series.SOURCE,
                                               build=lambda latest: ({"fetched_at": NOW.isoformat()}, {"schema_version": series.SCHEMA_VERSION}, NOW, "m1", [good, broken]))
        assert database.analysis_snapshot_by_id("m1") is None and database._price_bars == [] and _rows(database, series.ANALYSIS_TYPE, "NASDAQ") == []
    # what the CHECKs admit is admitted: Decimal (psycopg's NUMERIC) and int prices, a volume of any finite value (no CHECK on it: negative, zero, Decimal,
    # a huge int, None), a session_date as a date object (the DATE column), every market of the enum
    assert database.insert_price_bars([{**good, "close": Decimal("230.5"), "adjusted_close": 1, "volume": -1}]) == 1
    assert database.insert_price_bars([{**good, "id": "b3", "market": "B3", "fetched_at": (NOW + S).isoformat()},
                                       {**good, "id": "nyse", "market": "NYSE", "fetched_at": (NOW + S).isoformat()}]) == 2
    assert database.insert_price_bars([{**good, "id": "v0", "volume": 0, "fetched_at": (NOW + 2 * S).isoformat()},
                                       {**good, "id": "vd", "volume": Decimal("1.5"), "session_date": date(2026, 9, 3), "fetched_at": (NOW + 2 * S).isoformat()},
                                       {**good, "id": "vn", "volume": None, "session_date": "2026-09-02", "fetched_at": (NOW + 2 * S).isoformat()},
                                       {**good, "id": "vb", "volume": 10**400, "session_date": "2026-09-01", "fetched_at": (NOW + 2 * S).isoformat()}]) == 4
    assert Database._price_bar_params({**good, "close": Decimal("230.5")})[4] == Decimal("230.5")


def test_the_ddl_mirror_compares_prices_in_their_own_type_and_a_huge_int_is_a_numeric_never_an_overflow() -> None:
    # T3: NUMERIC has no float range — 10**400 is a value PostgreSQL stores; the double must accept it without converting to float (OverflowError)
    assert Database._positive_price(10**400) is True and Database._positive_price(-(10**400)) is False and Database._positive_price(0) is False
    assert Database._positive_price(Decimal("1e400")) is True and Database._positive_price(Decimal("0.000001")) is True
    assert Database._positive_price(Decimal("NaN")) is False and Database._positive_price(Decimal("-NaN")) is False  # is_finite before any comparison: no InvalidOperation
    assert Database._positive_price(Decimal("Infinity")) is False and Database._positive_price(Decimal("-Infinity")) is False and Database._positive_price(Decimal("-1")) is False
    assert Database._positive_price(1e-300) is True and Database._positive_price(float("inf")) is False and Database._positive_price(float("nan")) is False
    assert Database._positive_price(True) is False and Database._positive_price("1") is False and Database._positive_price(None) is False
    assert Database._finite_number(10**400) is True and Database._finite_number(-(10**400)) is True and Database._finite_number(False) is False
    _, database, _ = _service({})
    bar = series.bar_record("NASDAQ", "AAPL", "AAPL.US", _bar("2026-09-04", 230.0))
    assert bar is not None
    huge = {**bar, "close": 10**400, "adjusted_close": Decimal("1e400"), "volume": -(10**400), "fetched_at": NOW.isoformat(), "snapshot_id": "m1"}
    assert database.insert_price_bars([huge]) == 1 and Database._price_bar_params(huge)[4] == 10**400  # accepted, no exception, the value untouched
    with pytest.raises(ValueError, match=r"has close -1000000000000000+, not a number > 0"):
        database.insert_price_bars([{**huge, "id": "neg", "close": -(10**400)}])
    # the series side canonicalises to a float and refuses what does not fit one — never an exception, on the provider path or when a reader recomputes a hash
    assert series._number(10**400) is None and series._price(10**400) is None
    assert series.bar_defects({"date": "2026-09-04", "close": 10**400, "adjusted_close": 1.0}) == ("2026-09-04", ["close"])
    assert series.bar_content_sha256({**huge, "market": "NASDAQ"}) is None


def test_the_memory_double_stores_the_json_mirror_of_every_snapshot_as_the_jsonb_column_would() -> None:
    # T4: what a reader gets back from the in-memory store is what JSONB gives back — a datetime/date/Decimal as its string, a tuple as a list, a
    # non-string key as a string — fresh objects, never the caller's dicts; the two series writers included
    _, database, _ = _service({})
    inputs = {"at": NOW, "day": date(2026, 9, 7), "dec": Decimal("1.5"), "pair": (1, 2), 3: "three", "nested": {"k": [NOW + S]}}
    outputs = {"rows": [{"symbol": "AAPL", "when": NOW}], "n": 1.0}
    snapshot_id = database.save_analysis_snapshot("some_analysis", "KEY", "mv", inputs, outputs, NOW)
    stored = database.analysis_snapshot_by_id(snapshot_id)
    assert stored and stored["inputs"] == {"at": str(NOW), "day": "2026-09-07", "dec": "1.5", "pair": [1, 2], "3": "three", "nested": {"k": [str(NOW + S)]}}
    assert stored["outputs"] == {"rows": [{"symbol": "AAPL", "when": str(NOW)}], "n": 1.0} and stored["published_at"] == NOW  # the TIMESTAMPTZ stays a datetime
    assert isinstance(stored["inputs"]["at"], str) and datetime.fromisoformat(stored["inputs"]["at"]) == NOW  # the string still parses as the instant
    assert inputs["at"] is NOW and inputs["pair"] == (1, 2) and 3 in inputs and outputs["rows"][0]["when"] is NOW  # the caller's dicts are untouched
    inputs["nested"]["k"].append("later")
    outputs["rows"].clear()
    assert database.latest_analysis_snapshot("some_analysis", "KEY")["inputs"]["nested"] == {"k": [str(NOW + S)]}  # type: ignore[index]
    assert database.latest_analysis_snapshot("some_analysis", "KEY")["outputs"]["rows"] == [{"symbol": "AAPL", "when": str(NOW)}]  # type: ignore[index]
    # the capture writer: a builder whose manifest carries a datetime stores its string (the PostgreSQL row would carry the same text)
    bar = series.bar_record("NASDAQ", "AAPL", "AAPL.US", _bar("2026-09-04", 230.0))
    assert bar is not None
    stamped = {**bar, "fetched_at": (NOW + S).isoformat(), "snapshot_id": "m1"}
    manifest_inputs = {"fetched_at": (NOW + S).isoformat(), "started_at": NOW, "window": ("2026-09-01", "2026-09-04")}
    manifest_outputs = {"schema_version": series.SCHEMA_VERSION, "series_sha256": {"AAPL": bar["bar_sha256"]}, "first": date(2026, 9, 4)}
    assert database.persist_price_history_run(series.ANALYSIS_TYPE, series.PUBLICATION_TYPE, "NASDAQ", "mv", fetched_at=NOW + S, symbols=["AAPL"], source=series.SOURCE,
                                              build=lambda latest: (manifest_inputs, manifest_outputs, NOW + S, "m1", [stamped])) == 1
    manifest = database.analysis_snapshot_by_id("m1")
    assert manifest and manifest["inputs"] == {"fetched_at": (NOW + S).isoformat(), "started_at": str(NOW), "window": ["2026-09-01", "2026-09-04"]}
    assert manifest["outputs"] == {"schema_version": series.SCHEMA_VERSION, "series_sha256": {"AAPL": bar["bar_sha256"]}, "first": "2026-09-04"}
    assert manifest_inputs["started_at"] is NOW and manifest_inputs["window"] == ("2026-09-01", "2026-09-04")  # the builder's dicts stay the caller's
    manifest_outputs["series_sha256"]["AAPL"] = "0" * 64
    assert database.analysis_snapshot_by_id("m1")["outputs"]["series_sha256"] == {"AAPL": bar["bar_sha256"]}  # type: ignore[index]
    # the publication writer: the same mirror (a tuple in outputs comes back a list; the stamped available_at is the string the writer adds)
    publication_id, available_at = database.publish_price_history_run(series.PUBLICATION_TYPE, series.ANALYSIS_TYPE, "NASDAQ", "mv",
                                                                       {"price_snapshot_id": "m1", "fetched_at": (NOW + S).isoformat(), "since": date(2026, 9, 1)},
                                                                       {"bars_sha256": "a" * 64, "pair": (1, 2)}, fetched_at=NOW + S, clock=lambda: NOW + 2 * S)
    publication = database.analysis_snapshot_by_id(publication_id)
    assert publication and publication["inputs"] == {"price_snapshot_id": "m1", "fetched_at": (NOW + S).isoformat(), "since": "2026-09-01",
                                                     "available_at": available_at.isoformat()}
    assert publication["outputs"] == {"bars_sha256": "a" * 64, "pair": [1, 2]} and publication["published_at"] == NOW + 2 * S


def test_a_poisoned_last_publication_refuses_both_writers_whatever_the_schema_until_the_mesa_fixes_it_by_hand(monkeypatch: pytest.MonkeyPatch) -> None:
    # T1 (the R10 runbook, truthfully): while the poisoned row is the LAST publication of the market, the capture AND the publication writers refuse by id,
    # whatever SCHEMA_VERSION says (the previous-publication readers are not schema-filtered, by design: the clock chain crosses schemas); the module cannot
    # write past it. The only exits are manual, under the mesa's order: (a) an UPDATE of that row's inputs.fetched_at by the DB operator, or (b) a manual
    # INSERT of a well-formed publication row for the same manifest after it. Both are probed here on the in-memory double.
    service, database, http = _service({"AAPL.US": [_bar("2026-09-03", 229.0), _bar("2026-09-04", 230.0)]})
    database.save_analysis_snapshot("valuation_universe", "NASDAQ_UNIVERSE", "mv-1", {}, {"rows": [{"symbol": "AAPL"}]}, NOW)  # coverage for run_all below
    first = _run(service, "NASDAQ", ["AAPL"], now=NOW)
    good = {"schema_version": series.SCHEMA_VERSION, "price_snapshot_id": first["price_snapshot_id"]}
    outputs = {**good, "bars_sha256": first["bars_sha256"]}
    poisoned = database.save_analysis_snapshot(series.PUBLICATION_TYPE, "NASDAQ", "mv", {**good, "fetched_at": "garbage", "available_at": (NOW + D).isoformat()},
                                               outputs, NOW + D)
    refusal = rf"previous publication {poisoned} of NASDAQ has no parseable fetched_at \('garbage'\)"
    with pytest.raises(ValueError, match=refusal):
        _run(service, "NASDAQ", ["AAPL"], now=NOW + 2 * D)
    with pytest.raises(ValueError, match=refusal):
        database.publish_price_history_run(series.PUBLICATION_TYPE, series.ANALYSIS_TYPE, "NASDAQ", "mv", {**good, "fetched_at": (NOW + 2 * D).isoformat()}, {},
                                           fetched_at=NOW + 2 * D, clock=lambda: NOW + 2 * D)
    # a SCHEMA_VERSION bump does not help: the writers read the previous publication of ANY schema (a later cut of the new schema would still be poisoned)
    monkeypatch.setattr(series, "SCHEMA_VERSION", "VALUATION-PRICE-HISTORY-v99")
    with pytest.raises(ValueError, match=refusal):
        _run(service, "NASDAQ", ["AAPL"], now=NOW + 2 * D)
    with pytest.raises(ValueError, match=refusal):
        service.run_all(now=NOW + 2 * D, due_at=NOW + 2 * D)
    monkeypatch.undo()
    assert len(_rows(database, series.ANALYSIS_TYPE, "NASDAQ")) == 1 and len(_rows(database, series.PUBLICATION_TYPE, "NASDAQ")) == 2 and len(database._price_bars) == 2
    assert service.series("NASDAQ", "AAPL", available_before=NOW + D + S)["status"] == "manifest_mismatch"  # the poisoned row is refused by the readers too
    assert service.series("NASDAQ", "AAPL", available_before=NOW + S)["price_snapshot_id"] == first["price_snapshot_id"]  # earlier cuts keep the previous vintage
    # exit (a): the DB operator corrects inputs.fetched_at of THAT row (an UPDATE on analysis_snapshots: the DDL declares no trigger on that table — pinned below)
    row = next(item for item in database._analysis_snapshots if item["id"] == poisoned)
    row["inputs"]["fetched_at"] = NOW.isoformat()  # the capture the row attests: the manifest's own clock
    fixed = _run(service, "NASDAQ", ["AAPL"], now=NOW + 2 * D)  # the next capture proceeds
    assert fixed["price_snapshot_id"] != first["price_snapshot_id"] and fixed["available_at"] == (NOW + 2 * D).isoformat()
    assert service.series("NASDAQ", "AAPL", available_before=NOW + D + S)["status"] == "ok"  # the corrected row now attests its manifest: served for its cuts
    assert service.series("NASDAQ", "AAPL", available_before=NOW + 3 * D)["price_snapshot_id"] == fixed["price_snapshot_id"]
    # exit (b): poisoned again (missing fetched_at); the operator INSERTS a well-formed publication for the same manifest AFTER it, attesting the manifest's capture
    poisoned_again = database.save_analysis_snapshot(series.PUBLICATION_TYPE, "NASDAQ", "mv", {**good, "price_snapshot_id": fixed["price_snapshot_id"],
                                                                                              "available_at": (NOW + 3 * D).isoformat()},
                                                     {**outputs, "price_snapshot_id": fixed["price_snapshot_id"], "bars_sha256": fixed["bars_sha256"]}, NOW + 3 * D)
    with pytest.raises(ValueError, match=rf"previous publication {poisoned_again} of NASDAQ has no parseable fetched_at \(None\)"):
        _run(service, "NASDAQ", ["AAPL"], now=NOW + 4 * D)
    manual = database.save_analysis_snapshot(series.PUBLICATION_TYPE, "NASDAQ", "mv",
                                             {"schema_version": series.SCHEMA_VERSION, "price_snapshot_id": fixed["price_snapshot_id"], "fetched_at": fixed["fetched_at"],
                                              "started_at": fixed["started_at"], "available_at": (NOW + 3 * D + S).isoformat()},
                                             {"schema_version": series.SCHEMA_VERSION, "bars_sha256": fixed["bars_sha256"], "price_snapshot_id": fixed["price_snapshot_id"]},
                                             NOW + 3 * D + S)
    served = service.series("NASDAQ", "AAPL", available_before=NOW + 3 * D + 2 * S)
    assert served["status"] == "ok" and served["publication_id"] == manual and served["price_snapshot_id"] == fixed["price_snapshot_id"]
    third = _run(service, "NASDAQ", ["AAPL"], now=NOW + 4 * D)  # the next capture proceeds: the manual row is the last publication and attests a parseable capture
    assert third["available_at"] == (NOW + 4 * D).isoformat() and service.series("NASDAQ", "AAPL", available_before=NOW + 5 * D)["price_snapshot_id"] == third["price_snapshot_id"]
    assert service.series("NASDAQ", "AAPL", available_before=NOW + 3 * D + S)["status"] == "manifest_mismatch"  # the poisoned row itself stays refused for its own cuts
    # the doc's claim: analysis_snapshots has no trigger (an UPDATE by the operator is not blocked), unlike the append-only bars table
    migrations = sorted((Path(__file__).resolve().parents[2] / "db").glob("*.sql"))
    assert any("CREATE TABLE IF NOT EXISTS analysis_snapshots" in path.read_text(encoding="utf-8") for path in migrations)
    assert not any(re.search(r"CREATE (?:OR REPLACE )?(?:TRIGGER|RULE|POLICY)[^;]*\bON analysis_snapshots\b", path.read_text(encoding="utf-8")) for path in migrations)
    assert any(re.search(r"CREATE TRIGGER[^;]*\bON valuation_price_bars\b", path.read_text(encoding="utf-8")) for path in migrations)


def test_a_market_that_published_since_the_due_while_this_run_was_fetching_is_skipped_inside_the_lock_never_re_published(caplog: pytest.LogCaptureFixture) -> None:
    # T5: run_all's first "already published" check is per process; the writer re-checks the due INSIDE the market's lock right before the capture write.
    # Here another run (another process, in production) publishes NASDAQ between that first check and the lock — provoked from inside the provider answer.
    service, database, http = _service({"AAPL.US": [_bar("2026-09-04", 230.0)], "IBM.US": [_bar("2026-09-04", 250.0)], "PETR4.SA": [_bar("2026-09-04", 36.0)]})
    for market, symbol in (("B3", "PETR4"), ("NASDAQ", "AAPL"), ("NYSE", "IBM")):
        database.save_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE", "mv-1", {}, {"rows": [{"symbol": symbol}]}, NOW)
    due = datetime(2026, 9, 8, 4, 0, tzinfo=timezone.utc)  # 01:00 in São Paulo
    interloper_at, attempt = due + timedelta(minutes=1), due + timedelta(minutes=2)
    other = series.PriceHistoryService(_settings(), database, http, eodhd=EodhdClient("https://eodhd.com", "secret", ScriptedHttp({"AAPL.US": [_bar("2026-09-04", 231.0)]})))  # type: ignore[arg-type]
    interleaved: list[dict] = []
    real_get_json = http.get_json

    def get_json(url: str, *, params=None, headers=None):
        if url.endswith("AAPL.US") and not interleaved:  # the other process publishes NASDAQ while this run is fetching it: after the first check, before the lock
            interleaved.append(other.persist_run("NASDAQ", start=date(2026, 9, 1), end=date(2026, 9, 8), symbols=["AAPL"], now=interloper_at))
        return real_get_json(url, params=params, headers=headers)

    http.get_json = get_json  # type: ignore[method-assign]
    with caplog.at_level(logging.INFO, logger="app.valuation_price_history"):
        results = service.run_all(now=attempt)
    assert interleaved and interleaved[0]["available_at"] == interloper_at.isoformat()
    assert results["NASDAQ"] == {"skipped": "already published", "available_at": interloper_at.isoformat()}  # the writer's refusal is a skip, not a failure
    assert results["B3"]["mode"] == "nightly" and results["NYSE"]["mode"] == "nightly" and results["B3"]["available_at"] == attempt.isoformat()
    assert [call["url"].rsplit("/", 1)[-1] for call in http.calls] == ["PETR4.SA", "AAPL.US", "IBM.US"]  # this run DID fetch NASDAQ: the first check had passed
    nasdaq = _rows(database, series.PUBLICATION_TYPE, "NASDAQ")
    assert len(nasdaq) == 1 and nasdaq[0]["id"] == interleaved[0]["publication_id"] and len(_rows(database, series.ANALYSIS_TYPE, "NASDAQ")) == 1  # nothing written by this run
    assert service.series("NASDAQ", "AAPL", available_before=attempt + S)["bars"]["2026-09-04"]["close"] == 231.0  # the other run's vintage, not this run's 230.0
    assert [record.getMessage() for record in caplog.records if "while this run was fetching" in record.getMessage()] == [
        f"valuation_price_history NASDAQ already published at {interloper_at.isoformat()} (phase due {due.isoformat()}) while this run was fetching: skipped, nothing written"]
    assert service.last_run_at() == interloper_at  # the phase completed: every market has a publication since the due
    # the writer's refusal by itself: a clear ValueError naming the due and the publication, nothing written; without a due (a backfill) the same run proceeds
    with pytest.raises(series.AlreadyPublishedError, match=re.escape(f"already published since {due.isoformat()}: the latest publication of NASDAQ is at "
                                                                     f"{interloper_at.isoformat()}, nothing written")) as refused:
        service.persist_run("NASDAQ", start=date(2026, 9, 1), end=date(2026, 9, 8), symbols=["AAPL"], now=attempt + S, due=due)
    assert isinstance(refused.value, ValueError) and refused.value.due == due and refused.value.available_at == interloper_at and refused.value.entity_key == "NASDAQ"
    assert len(_rows(database, series.PUBLICATION_TYPE, "NASDAQ")) == 1 == len(_rows(database, series.ANALYSIS_TYPE, "NASDAQ"))
    with pytest.raises(series.AlreadyPublishedError):  # the due in any zone is the same instant (01:00 in São Paulo); run_all alone reads a naive one the worker's way
        service.nightly("NASDAQ", now=attempt + S, due=datetime(2026, 9, 8, 1, 0, tzinfo=ZoneInfo("America/Sao_Paulo")))
    later = service.persist_run("NASDAQ", start=date(2026, 9, 1), end=date(2026, 9, 8), symbols=["AAPL"], now=attempt + S, due=interloper_at + S)  # due after it: due again
    assert later["available_at"] == (attempt + S).isoformat()
    assert service.backfill("NASDAQ", months=1, now=attempt + 2 * S, symbols=["AAPL"])["available_at"] == (attempt + 2 * S).isoformat()  # no due: never refused by it
