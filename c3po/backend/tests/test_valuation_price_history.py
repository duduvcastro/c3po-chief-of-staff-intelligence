"""The V3.2 price series (rev 7 §2.2 / §9.2): bars are produced from the provider with both closes, persisted append-only
with the run's fetched_at and a manifest, read back only as they were known before a cut, and located h sessions ahead on
the exchange calendar. OFF by default; the 36-month backfill is an explicit one-shot run."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import valuation_price_history as series
from app.config import Settings
from app.database import Database
from app.market_data.eodhd import EodhdClient

NOW = datetime(2026, 9, 7, 23, 30, tzinfo=timezone.utc)


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


def test_bars_need_both_closes_and_carry_the_run_clock_and_a_hash() -> None:
    record = series.bar_record("NASDAQ", "AAPL", "AAPL.US", _bar("2026-09-04", 230.0, 229.5), fetched_at=NOW)
    assert record and record["close"] == 230.0 and record["adjusted_close"] == 229.5 and record["currency"] == "USD" and record["source"] == series.SOURCE
    assert record["fetched_at"] == NOW.isoformat() and len(record["bar_sha256"]) == 64
    assert series.bar_record("NASDAQ", "AAPL", "AAPL.US", {"date": "2026-09-04", "close": 230.0}, fetched_at=NOW) is None  # adjusted_close mandatory
    assert series.bar_record("NASDAQ", "AAPL", "AAPL.US", {"date": "bad", "close": 1.0, "adjusted_close": 1.0}, fetched_at=NOW) is None
    assert series.bar_record("B3", "PETR4", "PETR4.SA", _bar("2026-09-04", 36.0), fetched_at=NOW)["currency"] == "BRL"  # type: ignore[index]


def test_coverage_is_the_universe_plus_every_symbol_with_v3_evaluations() -> None:
    service, database, _ = _service({})
    database.save_analysis_snapshot("valuation_universe", "NASDAQ_UNIVERSE", "mv-1", {"methodology_version": 7},
                                    {"rows": [{"symbol": "AAPL"}, {"symbol": "msft"}], "universe_size": 2}, NOW)
    database.save_analysis_snapshot("valuation_v3_shadow", "NASDAQ_V3_SHADOW", "mv-1", {"market": "NASDAQ"},
                                    {"results": {"AAPL": {}, "NVDA": {}, "OLDC": {}}}, NOW - timedelta(days=3))
    assert service.coverage_symbols("NASDAQ") == ["AAPL", "MSFT", "NVDA", "OLDC"]  # a delisted-from-universe name keeps its labels coming


def test_a_run_persists_bars_once_with_a_manifest_and_records_missing_symbols_and_provider_errors() -> None:
    service, database, http = _service({
        "AAPL.US": [_bar("2026-09-03", 229.0, 229.0), _bar("2026-09-04", 230.0, 230.0)],
        "MSFT.US": [_bar("2026-09-04", 500.0, 499.0), {"date": "2026-09-03", "close": 498.0}],  # the second row lacks adjusted_close
    })
    result = service.persist_run("NASDAQ", start=date(2026, 9, 1), end=date(2026, 9, 4), symbols=["AAPL", "MSFT", "NONE", "BOOM"], now=NOW, mode="nightly")
    assert result["bars"] == 3 and result["bars_inserted"] == 3 and result["symbols_with_bars"] == 2
    assert result["symbols_missing"] == ["BOOM", "NONE"] and result["errors"] == {"BOOM": "RuntimeError"}
    assert result["first_session"] == "2026-09-03" and result["last_session"] == "2026-09-04" and len(result["bars_sha256"]) == 64
    manifest = database.latest_analysis_snapshot(series.ANALYSIS_TYPE, "NASDAQ")
    assert manifest and manifest["id"] == result["price_snapshot_id"] and manifest["outputs"]["bars"] == 3 and manifest["inputs"]["mode"] == "nightly"
    assert {call["params"]["from"] for call in http.calls} == {"2026-09-01"} and all("api_token" in call["params"] for call in http.calls)
    # the same bars again (a second run at a LATER clock) are new rows — append-only, a new vintage per fetch
    again = service.persist_run("NASDAQ", start=date(2026, 9, 1), end=date(2026, 9, 4), symbols=["AAPL"], now=NOW + timedelta(hours=1), mode="nightly")
    assert again["bars_inserted"] == 2
    # ... but replaying the SAME run clock inserts nothing (idempotent by (market, symbol, session, source, fetched_at))
    replay = service.persist_run("NASDAQ", start=date(2026, 9, 1), end=date(2026, 9, 4), symbols=["AAPL"], now=NOW, mode="nightly")
    assert replay["bars_inserted"] == 0


def test_readers_see_only_what_was_fetched_before_their_cut_and_the_latest_vintage() -> None:
    service, database, http = _service({"AAPL.US": [_bar("2026-09-04", 230.0, 230.0)]})
    service.persist_run("NASDAQ", start=date(2026, 9, 4), end=date(2026, 9, 4), symbols=["AAPL"], now=NOW, mode="nightly")
    http.bars_by_symbol["AAPL.US"] = [_bar("2026-09-04", 230.0, 115.0)]  # a 2:1 split restates adjusted_close later
    service.persist_run("NASDAQ", start=date(2026, 9, 4), end=date(2026, 9, 4), symbols=["AAPL"], now=NOW + timedelta(days=2), mode="nightly")
    before_split = service.bars("NASDAQ", "AAPL", fetched_before=NOW + timedelta(days=1))
    after_split = service.bars("NASDAQ", "AAPL", fetched_before=NOW + timedelta(days=3))
    assert before_split["2026-09-04"]["adjusted_close"] == 230.0 and after_split["2026-09-04"]["adjusted_close"] == 115.0
    assert service.bars("NASDAQ", "AAPL", fetched_before=NOW) == {}  # a cut at the fetch instant sees nothing (strict <)


def test_labels_are_located_on_the_exchange_calendar_and_never_invented() -> None:
    service, database, http = _service({"AAPL.US": [_bar("2026-09-08", 231.0), _bar("2026-09-09", 232.0), _bar("2026-09-10", 233.0)],
                                        "PETR4.SA": [_bar("2026-09-08", 36.0), _bar("2026-09-09", 36.5)]})
    service.persist_run("NASDAQ", start=date(2026, 9, 8), end=date(2026, 9, 10), symbols=["AAPL"], now=NOW + timedelta(days=4), mode="nightly")
    service.persist_run("B3", start=date(2026, 9, 8), end=date(2026, 9, 9), symbols=["PETR4"], now=NOW + timedelta(days=4), mode="nightly")
    # 2026-09-07 is Labor Day (NYSE) and Independence Day (B3): two sessions after Friday 2026-09-04 is Wednesday 2026-09-09
    assert series.sessions_after("NASDAQ", date(2026, 9, 4), 2) == date(2026, 9, 9) and series.sessions_after("B3", date(2026, 9, 4), 2) == date(2026, 9, 9)
    cut = NOW + timedelta(days=5)
    label = service.label_bar("NASDAQ", "AAPL", date(2026, 9, 4), 2, fetched_before=cut)
    assert label["status"] == "labelled" and label["session"] == "2026-09-09" and label["close"] == 232.0 and label["adjusted_close"] == 232.0
    assert label["bar_sha256"] == service.bars("NASDAQ", "AAPL", fetched_before=cut)["2026-09-09"]["bar_sha256"]
    assert label["fetched_at"] == (NOW + timedelta(days=4)).isoformat()
    assert service.label_bar("B3", "PETR4", date(2026, 9, 4), 3, fetched_before=cut)["status"] == "missing_bar"  # 2026-09-10 has no bar persisted
    assert service.label_bar("NASDAQ", "AAPL", date(2026, 9, 4), 2, fetched_before=NOW + timedelta(days=3))["status"] == "missing_bar"  # not known before that cut
    assert service.label_bar("NASDAQ", "AAPL", date(2026, 9, 4), 126, fetched_before=cut)["status"] == "not_yet_mature"


def test_backfill_window_and_dormant_wiring() -> None:
    service, database, http = _service({"AAPL.US": [_bar("2024-01-05", 180.0)]})
    result = service.backfill("NASDAQ", months=36, now=NOW, symbols=["AAPL"])
    assert result["mode"] == "backfill" and http.calls[0]["params"]["from"] <= "2023-09-30" and http.calls[0]["params"]["to"] == "2026-09-07"
    assert result["bars"] == 1 and service.last_run_at() is None  # the other markets have no manifest yet: the phase is not "done"
    assert _settings().valuation_price_history_enabled is False  # dormant by default (rev 7 §2.2, mesa enables)
    sql = (Path(__file__).resolve().parents[2] / "db" / "049_valuation_price_history.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS valuation_price_bars" in sql and "UNIQUE (market, symbol, session_date, source, fetched_at)" in sql
    assert "BEFORE UPDATE OR DELETE ON valuation_price_bars" in sql and "adjusted_close NUMERIC NOT NULL CHECK (adjusted_close > 0)" in sql
