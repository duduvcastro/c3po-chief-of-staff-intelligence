"""The point-in-time re-executor (design rev 2 of 2026-09-11, §6 tests + the auditor's three executable details): engine
equivalence with the shadow path on a shared synthetic fixture; no path of the ECONOMIC computation reads ``now``; the
forbidden current blocks are never read (poisoned fixture); the B3 lag as a labelled hypothesis; the consensus rule; the
price vintage pinned for the whole run (a publication mid-run is never mixed in); idempotency, interruption, changed
inputs and concurrency; refusal of ``v3_2_shadow`` in the official selection; the row hash after the NUMERIC round trip;
the panel classifying every record ``retrospective``; the fetch phase and the CLI. In-memory double only, no network."""
from __future__ import annotations

import json
import os
import stat
import threading
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import exchange_calendars as xcals
import pytest

from app import valuation_official as official
from app import valuation_panel as panel
from app import valuation_pit_rerun as pit
from app import valuation_price_history as series
from app import valuation_v2_engine, valuation_v3_engine, valuation_v3_macro, valuation_v3_shadow
from app.config import Settings
from app.database import Database
from app.market_data.eodhd import EodhdClient
from app.valuation_official_engine import OFFICIAL_SOURCES
from app.valuation_v3_engine import ValuationV3Engine
from app.valuation_v3_macro import canonical_payload_sha256
from app.valuation_v3_shadow import ValuationV3ShadowService

UTC = timezone.utc
T = datetime(2024, 6, 14, 21, 0, tzinfo=UTC)  # Friday 2024-06-14, XNYS closed 20:00Z: the session of T is 2024-06-14
NOW = datetime(2026, 9, 11, 18, 0, tzinfo=UTC)
VINTAGE_AT = datetime(2026, 9, 11, 3, 0, tzinfo=UTC)
SYMBOLS = ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF")
SECTOR = "Industrials"


class ScriptedHttp:
    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers
        self.calls: list[str] = []

    def get_json(self, url: str, *, params=None, headers=None):
        self.calls.append(url)
        for key, value in self.answers.items():
            if key in url:
                return value(params) if callable(value) else value
        return []


def _settings() -> Settings:
    return Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", fmp_api_token="fmp-test", auth_cookie_secure=False)


def _database() -> Database:
    return Database(_settings())


def _sessions(start: str, end: str) -> list[date]:
    return [s.date() for s in xcals.get_calendar("XNYS").sessions_in_range(start, end)]


def _bars_for(symbol: str, sessions: list[date], *, base: float) -> list[dict]:
    seed = sum(ord(c) for c in symbol)
    return [{"date": s.isoformat(), "close": round(base * (1 + 0.002 * ((i * 7 + seed) % 13 - 6)) + i * 0.01, 4),
             "adjusted_close": round(base * (1 + 0.002 * ((i * 7 + seed) % 13 - 6)) + i * 0.01, 4), "volume": 1000.0}
            for i, s in enumerate(sessions)]


def _publish_prices(database: Database, *, bars: dict[str, list[dict]] | None = None, at: datetime = VINTAGE_AT, start: date = date(2023, 6, 1),
                    end: date = date(2026, 9, 10)) -> dict[str, Any]:
    sessions = _sessions(start.isoformat(), end.isoformat())
    bars = bars if bars is not None else {f"{symbol}.US": _bars_for(symbol, sessions, base=100.0 + 10 * index) for index, symbol in enumerate(SYMBOLS)}
    http = ScriptedHttp({"/api/eod/": lambda params, _b=bars: []})
    http.answers = {f"/api/eod/{key}": rows for key, rows in bars.items()}
    producer = series.PriceHistoryService(_settings(), database, http, eodhd=EodhdClient("https://eodhd.com", "secret", http))  # type: ignore[arg-type]
    return producer.persist_run("NASDAQ", start=start, end=end, symbols=[key.split(".")[0] for key in bars], now=at)


def _payload(symbol: str, *, scale: float = 1.0, filing_lag_days: int = 45, poison: bool = False, b3: bool = False) -> dict[str, Any]:
    """An EODHD-shaped fundamentals payload: 6 fiscal years (2018–2023) and 9 quarters (2022Q1–2024Q1) with filing dates,
    outstandingShares, and — when ``poison`` — current blocks with absurd values that must never reach the engine."""
    shares = 1_000_000.0
    seed = (sum(ord(c) for c in symbol) % 7) / 10
    def income(period: date, factor: float) -> dict[str, Any]:
        revenue = 12_000_000 * factor * scale
        return {"date": period.isoformat(), "filing_date": (period + timedelta(days=filing_lag_days)).isoformat() if not b3 else period.isoformat(),
                "totalRevenue": revenue, "netIncome": revenue * (0.10 + seed / 10), "ebitda": revenue * 0.2, "operatingIncome": revenue * 0.15}
    def balance(period: date, factor: float) -> dict[str, Any]:
        return {"date": period.isoformat(), "filing_date": (period + timedelta(days=filing_lag_days)).isoformat() if not b3 else period.isoformat(),
                "totalStockholderEquity": 8_000_000 * factor * scale, "shortTermDebt": 500_000.0, "longTermDebt": 1_500_000.0, "cashAndEquivalents": 800_000.0,
                "commonStockSharesOutstanding": shares}
    def cash(period: date, factor: float) -> dict[str, Any]:
        return {"date": period.isoformat(), "filing_date": (period + timedelta(days=filing_lag_days)).isoformat() if not b3 else period.isoformat(),
                "dividendsPaid": -200_000 * factor, "freeCashFlow": 900_000 * factor, "totalCashFromOperatingActivities": 1_200_000 * factor}
    years = [date(y, 12, 31) for y in range(2018, 2024)]
    quarters = [date(2022, 3, 31), date(2022, 6, 30), date(2022, 9, 30), date(2022, 12, 31), date(2023, 3, 31), date(2023, 6, 30), date(2023, 9, 30),
                date(2023, 12, 31), date(2024, 3, 31)]
    def rows(builder, periods: list[date], quarterly: bool) -> dict[str, Any]:
        return {p.isoformat(): builder(p, (0.25 if quarterly else 1.0) * (1 + 0.05 * i)) for i, p in enumerate(periods)}
    payload: dict[str, Any] = {
        "Financials": {"Income_Statement": {"quarterly": rows(income, quarters, True), "yearly": rows(income, years, False)},
                       "Balance_Sheet": {"quarterly": rows(balance, quarters, True), "yearly": rows(balance, years, False)},
                       "Cash_Flow": {"quarterly": rows(cash, quarters, True), "yearly": rows(cash, years, False)}},
        "outstandingShares": {"annual": {str(i): {"date": y.isoformat(), "dateFormatted": y.isoformat(), "shares": shares} for i, y in enumerate(years)},
                              "quarterly": {}},
    }
    if poison:
        payload.update({"General": {"Sector": "Poison", "Code": symbol, "Name": "POISON"}, "Highlights": {"MarketCapitalization": 1e30, "PERatio": 999.0, "EarningsShare": 1e9,
                                                                                                          "BookValue": 1e9, "ReturnOnEquityTTM": 99.0, "DividendYield": 9.0},
                        "Valuation": {"TrailingPE": 999.0, "PriceBookMRQ": 999.0, "EnterpriseValueEbitda": 999.0}, "Technicals": {"Beta": 50.0},
                        "SharesStats": {"SharesOutstanding": 1.0}, "AnalystRatings": {"TargetPrice": 1e9}, "Earnings": {"Trend": {"Annual": {}}}})
    return payload


def _publish_sources(database: Database, *, symbols: tuple[str, ...] = SYMBOLS, at: datetime = VINTAGE_AT, scale: dict[str, float] | None = None,
                     poison: bool = False, targets: dict[str, list[dict]] | None = None, catalogue: bool = True) -> None:
    if catalogue:
        database.save_analysis_snapshot("valuation_universe", "NASDAQ_UNIVERSE", "mv-cat",
                                        {"methodology_version": 7},
                                        {"rows": [{"symbol": s, "sector": SECTOR, "industry": "Machinery", "valuation_profile": "general", "security_type": "Stock",
                                                   "price": 1.0, "pe": 999.0, "our_tp": 1.0} for s in symbols]}, at - timedelta(hours=1))
    for symbol in symbols:
        payload = _payload(symbol, scale=(scale or {}).get(symbol, 1.0), poison=poison)
        database.save_analysis_snapshot(pit.SOURCE_ANALYSIS_TYPE, pit.source_entity_key("NASDAQ", pit.PROVIDER_EODHD, symbol), "mv-src",
                                        {"symbol": symbol, "symbol_sha256": pit.symbol_hash(symbol), "fetched_at": at.isoformat(), "payload_sha256": official.canonical_sha256(payload)},
                                        {"payload": payload, "payload_sha256": official.canonical_sha256(payload)}, at)
        if targets and symbol in targets:
            database.save_analysis_snapshot(pit.SOURCE_ANALYSIS_TYPE, pit.source_entity_key("NASDAQ", pit.PROVIDER_FMP, symbol), "mv-src",
                                            {"symbol": symbol, "fetched_at": at.isoformat(), "payload_sha256": official.canonical_sha256(targets[symbol])},
                                            {"payload": targets[symbol]}, at)
    curve = {"fetched_at": at.isoformat(), "series": {sym: [{"date": d.isoformat(), "close": 4.0 + tenor / 10 + (d.toordinal() % 5) / 100}
                                                          for d in _sessions("2023-01-01", "2026-09-10")] for tenor, sym in pit.US_CURVE_SYMBOLS}}
    curve["payload_sha256"] = canonical_payload_sha256(curve)
    database.save_analysis_snapshot(pit.SOURCE_ANALYSIS_TYPE, pit.MACRO_TREASURY_KEY, "mv-src", {"fetched_at": at.isoformat(), "payload_sha256": curve["payload_sha256"]},
                                    {"payload": curve, "payload_sha256": curve["payload_sha256"]}, at)


def _target(house: str, published: datetime, target: float, currency: str | None = "USD") -> dict[str, Any]:
    row = {"analystCompany": house, "analystName": f"{house} analyst", "publishedDate": published.isoformat(), "priceTarget": target}
    if currency is not None:
        row["currency"] = currency
    return row


def _service(database: Database) -> pit.PitRerunService:
    return pit.PitRerunService(database, settings=_settings())


def _ready(**kwargs: Any) -> Database:
    database = _database()
    _publish_prices(database)
    _publish_sources(database, **kwargs)
    return database


# ------------------------------------------------------------------ §2–§3: availability as evidence or declared hypothesis; the closed list
def test_availability_is_provider_evidence_for_us_and_a_labelled_hypothesis_for_b3_never_the_original_publication() -> None:
    us = pit.availability_of("NASDAQ", date(2023, 12, 31), date(2024, 2, 14))
    assert us == {"kind": "evidence", "rule": "provider_filing_date", "period_end": "2023-12-31", "available_at": "2024-02-14", "published_at_original": "N/D"}
    assert pit.availability_of("NASDAQ", date(2023, 12, 31), None) is None  # no filing date: not eligible, never "current"
    b3 = pit.availability_of("B3", date(2023, 12, 31), date(2023, 12, 31))
    assert b3 == {"kind": "hypothesis", "rule": "period_end+90d", "period_end": "2023-12-31", "available_at": "2024-03-30", "published_at_original": "N/D"}
    assert "original" not in b3["rule"] and "publication" not in b3["rule"]  # the lag is a declared hypothesis, not "the original publication"
    # B3 payload at T: the FY2023 statements (period end 2023-12-31) are eligible only from 2024-03-30 on
    before = pit.pit_fundamentals(_payload("PETR", b3=True), market="B3", economic_date=date(2024, 3, 29))
    after = pit.pit_fundamentals(_payload("PETR", b3=True), market="B3", economic_date=date(2024, 3, 30))
    assert before["fiscal_years"][0]["fiscal_year_end"] == "2022-12-31" and after["fiscal_years"][0]["fiscal_year_end"] == "2023-12-31"
    assert all(h["kind"] == "hypothesis" and h["published_at_original"] == "N/D" for h in after["hypotheses"]) and after["hypotheses"]
    # US payload at T = 2024-06-14: 2024Q1 (filed 2024-05-15) is in; the TTM is four quarters; nothing from the future
    us_f = pit.pit_fundamentals(_payload("AAA"), market="NASDAQ", economic_date=date(2024, 6, 14))
    assert us_f["ttm"]["basis"] == "four_quarters" and us_f["fundamentals_as_of"] == "2024-03-31" and us_f["hypotheses"] == []
    assert us_f["eligible_periods"]["Income_Statement"] == {"quarterly": 9, "yearly": 6} and us_f["shares"] == 1_000_000.0
    early = pit.pit_fundamentals(_payload("AAA"), market="NASDAQ", economic_date=date(2024, 5, 14))  # the day before 2024Q1 was filed
    assert early["fundamentals_as_of"] == "2023-12-31" and early["excluded"]["Income_Statement.quarterly:not_available_at_T"] == 1
    assert pit.AVAILABILITY_RULE.startswith("as available per evidence")


class _Poisoned(dict):
    """A payload that EXPLODES when a forbidden block is touched by any read path."""

    def _check(self, key: Any) -> None:
        if key in pit.FORBIDDEN_PAYLOAD_BLOCKS:
            raise AssertionError(f"forbidden current block {key!r} was read")

    def __getitem__(self, key: Any) -> Any:
        self._check(key)
        return super().__getitem__(key)

    def get(self, key: Any, default: Any = None) -> Any:
        self._check(key)
        return super().get(key, default)

    def __contains__(self, key: Any) -> bool:
        self._check(key)
        return super().__contains__(key)

    def items(self):  # type: ignore[override]
        raise AssertionError("the payload is never iterated whole")

    def values(self):  # type: ignore[override]
        raise AssertionError("the payload is never iterated whole")

    def __iter__(self):
        raise AssertionError("the payload is never iterated whole")


def test_forbidden_current_blocks_are_never_read_poisoned_fixture() -> None:
    # the pure reconstruction never touches General/Highlights/Valuation/Technicals/SharesStats/AnalystRatings/Earnings
    poisoned = _Poisoned(_payload("AAA", poison=True))
    clean = pit.pit_fundamentals(_payload("AAA"), market="NASDAQ", economic_date=date(2024, 6, 14))
    assert pit.pit_fundamentals(poisoned, market="NASDAQ", economic_date=date(2024, 6, 14)) == clean
    # end to end: a run over payloads whose current blocks carry absurd numbers produces EXACTLY the results of the clean payloads
    clean_db, poisoned_db = _ready(), _ready(poison=True)
    clean_receipt, clean_run = _service(clean_db).rerun("NASDAQ", as_of=T, clock=lambda: NOW)
    poisoned_receipt, poisoned_run = _service(poisoned_db).rerun("NASDAQ", as_of=T, clock=lambda: NOW)
    assert clean_run.results == poisoned_run.results and clean_receipt["evaluated"] == len(SYMBOLS)
    assert all(result["v3_internal_tp"] is not None and result["v3_internal_tp"] < 1_000 for result in poisoned_run.results.values())  # nothing of the 1e30 world
    assert clean_run.manifest["engine"] == poisoned_run.manifest["engine"] and clean_receipt["run_key"] != poisoned_receipt["run_key"]  # the payload hashes differ: another run


def test_macro_packages_at_t_hold_only_observations_available_at_t_and_validate() -> None:
    live = _selic_package(date(2026, 9, 10))  # the live 12-year history: observations dated, each with its own available_at
    at_t = pit.selic_package_at(live, as_of=T, economic_date=date(2024, 6, 14))
    assert at_t is not None and at_t["as_of"] == "2024-06-14" and at_t["observations"][-1]["observation_date"] == "2024-01-01"
    assert all(obs["observation_date"] <= "2024-06-14" and obs["available_at"] <= T.isoformat() for obs in at_t["observations"])
    assert valuation_v3_macro.package_hash_is_valid(at_t) and at_t["derived_from"]["source_payload_sha256"] == live["payload_sha256"] and at_t["source"] == live["source"]
    ValuationV3Engine(market="B3", risk_free_rate=0.105, today=date(2024, 6, 14), macro_as_of=date(2024, 6, 14), selic_package=at_t)  # the engine accepts it as dated
    assert pit.selic_package_at(live, as_of=datetime(2011, 1, 1, tzinfo=UTC), economic_date=date(2011, 1, 1)) is None
    history = {"fetched_at": NOW.isoformat(), "series": {"US3Y.GBOND": [{"date": "2024-06-13", "close": 4.3}, {"date": "2024-06-14", "close": 4.4}],
                                                          "US10Y.GBOND": [{"date": "2024-06-13", "close": 5.0}]}}
    curve = pit.curve_package_at(history, as_of=T, economic_date=date(2024, 6, 14))
    assert curve is not None and curve["as_of"] == "2024-06-13" and curve["interpolated_5y_rate"] == pytest.approx(0.043 + (2 / 7) * 0.007)  # the last date with BOTH tenors
    assert curve["points"][0]["available_at"] == "2024-06-14T00:00:00+00:00" and valuation_v3_macro.validate_us_curve_package(curve, as_of=date(2024, 6, 13)) > 0
    assert pit.curve_package_at(history, as_of=datetime(2024, 6, 13, 12, tzinfo=UTC), economic_date=date(2024, 6, 13)) is None  # 06-13 available only from 06-14 00:00Z


def test_consensus_is_the_last_target_per_house_in_the_window_with_three_houses_and_the_currency_by_field() -> None:
    rows = [_target("H1", T - timedelta(days=10), 120.0), _target("H1", T - timedelta(days=40), 90.0),  # the LAST of H1 counts (120)
            _target("H2", T - timedelta(days=89), 100.0), _target("H3", T - timedelta(hours=1), 110.0),
            _target("H4", T + timedelta(seconds=1), 500.0),  # after T: never
            _target("H5", T - timedelta(days=90), 500.0),  # exactly T − 90 d: outside (T − 90 d, T]
            _target("H6", T - timedelta(days=5), 500.0, currency="BRL"), _target("H7", T - timedelta(days=5), 500.0, currency=None)]
    block, refused = pit.consensus_at(rows, as_of=T, currency="USD")
    assert block is not None and block["consensus_tp"] == 110.0 and block["analyst_count"] == 3 and block["horizon"] == "N/D" and block["currency"] == "USD"
    assert block["published_at"] == (T - timedelta(hours=1)).isoformat() and block["source"] == "fmp:price-target-news"
    assert refused == {"currency_field_missing": 1, "currency_mismatch": 1, "older_than_window": 1, "published_after_T": 1}
    two, refused = pit.consensus_at(rows[:3], as_of=T, currency="USD")  # H1 and H2 only
    assert two is None and refused == {"houses_below_minimum": 1}
    assert pit.consensus_at([], as_of=T, currency="USD") == (None, {"houses_below_minimum": 1})


# ------------------------------------------------------------------ §1: engine equivalence with the shadow path on ONE synthetic fixture
def _selic_package(as_of: date) -> dict:
    package = {"schema_version": "VALUATION-V3-MACRO-v1", "engine_version": 3, "source": "Banco Central do Brasil SGS 432", "series": "SGS 432",
               "as_of": as_of.isoformat(), "fetched_at": "2026-09-11T03:00:00+00:00",
               "observations": [{"observation_date": f"{year}-01-01", "annual_rate": 0.10 + (year % 3) * 0.005, "available_at": f"{year}-01-02T00:00:00+00:00"}
                                for year in range(2012, as_of.year + 1)]}
    package["payload_sha256"] = canonical_payload_sha256(package)
    return package


def _synthetic_loaded(market: str) -> dict[tuple[str, str], dict]:
    def row(symbol: str, i: int) -> dict:
        return {"symbol": symbol, "security_type": "Stock", "price": 100.0 + i, "market_cap": 1e8, "sector": SECTOR, "valuation_profile": "general", "beta": 1.0 + i / 10,
                "eps": 7.5 + i / 10, "book_value": 50.0, "pe": 13.3 + i, "forward_pe": 12.5 + i, "ev_ebitda": 8.0 + i / 2, "price_to_book": 2.0 + i / 10, "roe": 0.15}
    def packet(symbol: str, peers: list[str]) -> dict:
        return {"symbol": symbol, "peers": [{"symbol": p} for p in peers], "analyst_estimates_annual": [],
                "ratios_annual": [{"fiscal_year_end": f"{year}-12-31", "pe": 10.0 + (year - 2016), "ev_ebitda": 7.0 + (year - 2016) * 0.1, "price_to_book": 1.5 + (year - 2016) * 0.05, "roe": 0.15}
                                  for year in range(2016, 2024)],
                "key_metrics_annual": [{"fiscal_year_end": f"{year}-12-31", "eps": 7.0 + (year - 2016) * 0.1, "market_cap": 1e8, "enterprise_value": 1.1e8, "roe": 0.15} for year in range(2016, 2024)]}
    symbols = [f"{s}{'3' if market == 'B3' else ''}" for s in SYMBOLS]
    loaded: dict[tuple[str, str], dict] = {}
    for m in valuation_v3_shadow.MARKETS:
        mine = m == market
        loaded[("universe", m)] = {"entity_key": f"{m}_UNIVERSE", "outputs": {"rows": [row(s, i) for i, s in enumerate(symbols)] if mine else []}}
        loaded[("v2_data", m)] = {"entity_key": f"{m}_V2_DATA", "outputs": {"packets": {s: packet(s, [p for p in symbols if p != s]) for s in symbols} if mine else {}}}
        loaded[("chewie", m)] = {"entity_key": f"{m}_FUNDAMENTALS", "outputs": {"items": [{"symbol": s, "profitability": {"roe_percent": 15.0 + i}, "growth": {"revenue_growth_percent": 5.0 + i}} for i, s in enumerate(symbols)] if mine else []}}
        loaded[("v2_shadow", m)] = {"entity_key": f"{m}_V2_SHADOW", "outputs": {"results": {}}}
    for pm in ("B3", "US"):
        loaded[("peer_quality", pm)] = {"entity_key": f"{pm}_V2_PEER_QUALITY", "outputs": {"packets": {}}}
    return loaded


def test_engine_equivalence_the_rerun_and_the_shadow_path_give_identical_results_on_the_same_packets() -> None:
    as_of = date(2024, 6, 14)
    selic = _selic_package(as_of)
    curve = pit.curve_package_at({"fetched_at": "2026-09-11T03:00:00+00:00", "series": {sym: [{"date": "2024-06-13", "close": 4.0 + tenor / 10}] for tenor, sym in pit.US_CURVE_SYMBOLS}},
                                 as_of=T, economic_date=as_of)
    assert curve is not None and curve["as_of"] == "2024-06-13"
    for market in ("NASDAQ", "B3"):
        loaded = _synthetic_loaded(market)
        macro = pit.MacroAtT(selic_package=selic if market == "B3" else None, curve_package=curve if market != "B3" else None,
                             b3_risk_free_rate=0.105 if market == "B3" else None, references={})
        # the shadow's own path, line by line (valuation_v3_shadow.run_all → _contexts → ValuationV3Engine → _evaluate_market)
        contexts = ValuationV3ShadowService._contexts(loaded, as_of=as_of)
        engine = ValuationV3Engine(market="B3" if market == "B3" else "US", risk_free_rate=0.105 if market == "B3" else None, today=as_of,
                                   macro_as_of=as_of if market == "B3" else date(2024, 6, 13), us_curve_package=curve if market != "B3" else None,
                                   selic_package=selic if market == "B3" else None, enable_quality=True, enable_selic=True, enable_treasury=market != "B3")
        expected = ValuationV3ShadowService._evaluate_market(engine, contexts[market])
        actual = pit.evaluate_loaded(market, loaded, as_of_date=as_of, macro=macro)
        assert actual == expected and len(actual) == len(SYMBOLS)
        assert all(r["v3_tp"] == r["v3_internal_tp"] for r in actual.values())  # no consensus in the engine's row: the TP is the internal TP
        assert all(r["bear_tp"] < r["v3_tp"] < r["bull_tp"] for r in actual.values())


# ------------------------------------------------------------------ §1–§2: the records and the snapshot of one run
def test_rerun_persists_one_snapshot_and_explicit_records_with_the_three_clocks_and_the_provenance() -> None:
    targets = {"AAA": [_target("H1", T - timedelta(days=3), 130.0), _target("H2", T - timedelta(days=2), 140.0), _target("H3", T - timedelta(days=1), 150.0)],
               "BBB": [_target("H1", T + timedelta(days=1), 130.0), _target("H2", T - timedelta(days=2), 140.0), _target("H3", T - timedelta(days=1), 150.0)]}  # BBB: 2 houses ≤ T
    database = _ready(targets=targets)
    service = _service(database)
    receipt, run = service.rerun("NASDAQ", as_of=T, clock=lambda: NOW)
    assert service.http is not None and service.http.calls == 0  # no network
    assert receipt["records"] == {"expected": 6, "stored_before": 0, "inserted": 6, "complete": True} and receipt["idempotent"] is False and receipt["supersedes"] is None
    assert receipt["entity_key"] == f"NASDAQ_PIT_{receipt['run_key'][:16]}" and receipt["calibration"] == "absent_at_T" and receipt["with_consensus"] == 1
    snapshot = database.latest_analysis_snapshot(pit.ANALYSIS_TYPE, receipt["entity_key"])
    assert snapshot is not None and snapshot["id"] == receipt["cycle_id"] and snapshot["inputs"]["run_key"] == receipt["run_key"] and "supersedes" not in snapshot["inputs"]
    assert snapshot["inputs"]["as_of"] == T.isoformat() and snapshot["inputs"]["manifest"]["price_vintage"]["historical_vintage"] == "N/D"
    assert len(snapshot["outputs"]["prediction_identities"]) == 6 and snapshot["published_at"] == NOW
    records = database.valuation_predictions_for_cycle(receipt["cycle_id"], source=pit.SOURCE)
    assert set(records) == set(SYMBOLS)
    aaa = records["AAA"]
    assert aaa["source"] == "v3_2_shadow" and aaa["source_version"] == f"pit-rerun-v1+{pit.module_sha256()[:12]}" and aaa["scope"] == "universe"
    assert aaa["prediction_instant"] == T.isoformat() and aaa["published_at"] == NOW.isoformat() and aaa["session_date"] == "2024-06-14"
    assert aaa["tp"] == run.results["AAA"]["v3_internal_tp"] and aaa["internal_tp"] == aaa["tp"] and aaa["buy_in"] > 0 and aaa["buy_in"] <= aaa["tp"] * 0.9
    assert aaa["price"] == run.results["AAA"]["price"] and aaa["currency"] == "USD"
    provenance = aaa["decomposition"]["provenance"]
    assert provenance["rerun_of"] is None and provenance["engine"] == f"ValuationV3Engine@{pit._file_sha256('valuation_v3_engine.py')[:12]}"
    assert provenance["buy_in_rule"].startswith("official_buy_in_v1@") and provenance["buy_in_parameters"]["risk_score"] == 50.0
    assert provenance["price_vintage"] == {"publication_id": run.manifest["price_vintage"]["publication_id"], "available_at": VINTAGE_AT.isoformat(), "historical_vintage": "N/D"}
    assert provenance["calibration"] == {"status": "absent_at_T", "factor": 1.0, "snapshot_id": None} and aaa["decomposition"]["weights"]["calibration_factor"] == 1.0
    assert provenance["availability_hypotheses"] == [] and provenance["pit_excluded_inputs"]["analyst_estimates:no_history"] == 6
    assert provenance["pit_excluded_inputs"]["peer_quality:no_history"] == 6 and provenance["current_fields_admitted"] == ["sector", "industry", "valuation_profile", "security_type"]
    assert provenance["beta"]["status"] == "recomputed" and provenance["availability_rule"].startswith("as available per evidence")
    assert provenance["source_manifest_sha256"] == run.manifest["manifest_sha256"] and provenance["consensus_in_engine"] is False
    # the consensus block: dated ≤ T, horizon N/D → the panel calls it unattested by horizon; BBB (2 houses at T) carries none
    consensus = aaa["decomposition"]["consensus"]
    assert consensus["tp"] == 140.0 and consensus["horizon"] == "N/D" and consensus["currency"] == "USD" and consensus["published_at"] == (T - timedelta(days=1)).isoformat()
    assert consensus["source"] == "fmp:price-target-news" and aaa["analyst_count"] == 3 and len(consensus["payload_sha256"]) == 64
    assert panel._consensus_of(aaa)[1] == "consensus_unattested:horizon"  # design §3: the horizon N/D attests nothing — the panel never compares it
    assert provenance["run_key"] == receipt["run_key"] and provenance["declared_assumptions"] == pit.DECLARED_ASSUMPTIONS and provenance["beta"]["proxy_includes_symbol"] is True
    assert run.manifest["declared_assumptions"] == pit.DECLARED_ASSUMPTIONS and "consensus_published_date_zone" in pit.DECLARED_ASSUMPTIONS
    bbb = records["BBB"]
    assert bbb["consensus_tp"] is None and bbb["decomposition"]["consensus"]["tp"] is None and bbb["decomposition"]["consensus"]["horizon"] is None
    # the engine saw no consensus: identical TP whether or not the block exists (TP sem consenso dentro)
    assert run.results["AAA"]["consensus_tp"] is None and run.results["AAA"]["consensus_weight"] == 0.0
    # the record's identity recomputes from the stored shape
    core = {key: value for key, value in aaa.items() if key not in ("id", "row_sha256")}
    assert official.canonical_sha256(core) == aaa["row_sha256"]


# ------------------------------------------------------------------ §6 (auditor iii): no path of the ECONOMIC computation reads now
class _ExplodingDatetime(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        raise AssertionError("the economic computation read the wall clock")

    @classmethod
    def today(cls):  # type: ignore[override]
        raise AssertionError("the economic computation read the wall clock")


def test_no_path_of_the_economic_computation_reads_now_while_the_persistence_clock_is_real(monkeypatch: pytest.MonkeyPatch) -> None:
    database = _ready()
    service = _service(database)
    prices = service.pin_vintage("NASDAQ", as_of=T, pinned_at=NOW)  # the only clock reading before the computation: the vintage selection
    for module in (pit, valuation_v3_engine, valuation_v2_engine, valuation_v3_shadow, valuation_v3_macro, official, series):
        monkeypatch.setattr(module, "datetime", _ExplodingDatetime)
    with pytest.raises(AssertionError):
        pit.datetime.now(UTC)  # the patch is live
    computation = service.compute("NASDAQ", as_of=T, prices=prices)  # T, the filters, today, macro as_of, the consensus cut: no now()
    assert computation.manifest["economic_date"] == "2024-06-14" and computation.macro.macro_as_of("NASDAQ") <= date(2024, 6, 14)
    assert all(r["macro_inputs"]["us_curve_hash"] == computation.macro.curve_package["payload_sha256"] for r in computation.results.values())  # type: ignore[index]
    monkeypatch.undo()
    real_before = datetime.now(UTC)
    receipt = service.persist(computation)  # the persistence clock is the REAL now
    published = datetime.fromisoformat(receipt["published_at"])
    assert real_before <= published <= datetime.now(UTC) and published >= T
    record = next(iter(database.valuation_predictions_for_cycle(receipt["cycle_id"], source=pit.SOURCE).values()))
    assert datetime.fromisoformat(record["published_at"]) == published and datetime.fromisoformat(record["prediction_instant"]) == T
    # a persistence clock before T is refused (prediction_from_row's check, mirrored before any write)
    earlier = T - timedelta(days=7)
    with pytest.raises(pit.PitRerunInputError, match="precedes T"):
        service.persist(service.compute("NASDAQ", as_of=earlier, prices=service.pin_vintage("NASDAQ", as_of=earlier, pinned_at=NOW)), clock=lambda: earlier - timedelta(days=1))


# ------------------------------------------------------------------ §2 (auditor i): the price vintage is pinned once for the whole run
def test_price_vintage_is_pinned_at_run_start_and_a_publication_mid_run_is_never_mixed_in(monkeypatch: pytest.MonkeyPatch) -> None:
    database = _ready()
    service = _service(database)
    first = database.latest_analysis_snapshot(series.PUBLICATION_TYPE, "NASDAQ")
    assert first is not None
    prices = service.pin_vintage("NASDAQ", as_of=T, pinned_at=NOW)
    assert prices.publication_id == first["id"] and prices.available_at == VINTAGE_AT
    sessions = _sessions("2023-06-01", "2026-09-10")
    shifted = {f"{symbol}.US": [{**bar, "close": bar["close"] * 2, "adjusted_close": bar["adjusted_close"] * 2} for bar in _bars_for(symbol, sessions, base=100.0 + 10 * i)]
               for i, symbol in enumerate(SYMBOLS)}
    original_bars = pit.PinnedPrices.bars
    published: list[str] = []

    def bars_then_publish(self: pit.PinnedPrices, symbol: str) -> dict:
        result = original_bars(self, symbol)
        if not published:  # a NEW vintage (every close doubled) appears after the first symbol was read
            published.append(_publish_prices(database, bars=shifted, at=VINTAGE_AT + timedelta(hours=1))["publication_id"])
        return result

    monkeypatch.setattr(pit.PinnedPrices, "bars", bars_then_publish)
    computation = service.compute("NASDAQ", as_of=T, prices=prices)
    monkeypatch.undo()
    latest = database.latest_analysis_snapshot(series.PUBLICATION_TYPE, "NASDAQ")
    assert latest is not None and latest["id"] == published[0] != prices.publication_id  # the store moved on...
    assert computation.manifest["price_vintage"]["publication_id"] == prices.publication_id  # ...the run did not
    unshifted = {symbol: _bars_for(symbol, sessions, base=100.0 + 10 * i) for i, symbol in enumerate(SYMBOLS)}
    for symbol, result in computation.results.items():
        assert result["price"] == next(b["close"] for b in reversed(unshifted[symbol]) if b["date"] <= "2024-06-14")  # every price from the pinned vintage
    # a fresh run now pins the new vintage (another run_key) — the two never mix
    receipt, later = _service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW + timedelta(hours=2))
    assert later.manifest["price_vintage"]["publication_id"] == published[0] and receipt["run_key"] != computation.run_key
    assert all(later.resolver.per_symbol[s]["row"]["price"] == 2 * computation.resolver.per_symbol[s]["row"]["price"] for s in SYMBOLS)
    # the pinned publication no longer resolving as pinned is a refusal, never a substitution
    pinned = service.pin_vintage("NASDAQ", as_of=T, pinned_at=NOW)
    monkeypatch.setattr(pinned.reader, "series", lambda market, symbol, *, available_before: {"status": "ok", "publication_id": "someone-else", "bars": {}})
    with pytest.raises(pit.PitRerunInputError, match="no longer resolves as pinned"):
        pinned.bars("AAA")
    monkeypatch.setattr(pinned.reader, "series", lambda market, symbol, *, available_before: {"status": "manifest_mismatch", "publication_id": pinned.publication_id, "bars": {}})
    with pytest.raises(pit.PitRerunInputError, match="refuses to mix"):
        pinned.bars("BBB")
    with pytest.raises(pit.PitRerunInputError, match="no verifiable price vintage"):
        service.pin_vintage("NASDAQ", as_of=T, pinned_at=VINTAGE_AT - timedelta(days=1))  # nothing published before that cut
    # P3-2: a T whose session is after the vintage's last session (2026-09-10) is refused — a stale close is never the close of a later session
    assert service.pin_vintage("NASDAQ", as_of=datetime(2026, 9, 10, 21, 0, tzinfo=UTC), pinned_at=NOW).session_date == "2026-09-10"  # the last session: accepted
    with pytest.raises(pit.PitRerunInputError, match="after the last session 2026-09-10"):
        service.pin_vintage("NASDAQ", as_of=datetime(2026, 9, 14, 21, 0, tzinfo=UTC), pinned_at=NOW)


# ------------------------------------------------------------------ §4 (auditor ii): identity, idempotency, interruption, changed inputs, concurrency
def test_run_key_is_a_canonical_sha256_and_the_lock_key_derives_from_it() -> None:
    manifest = {"b": [1, 2], "a": {"y": 1.5, "x": None}}
    key = pit.run_key_of(source_version_text="pit-rerun-v1+abc", market="NASDAQ", as_of=T, manifest=manifest)
    assert key == official.canonical_sha256(["pit-rerun-v1+abc", "NASDAQ", T.isoformat(), manifest]) and len(key) == 64
    assert key == pit.run_key_of(source_version_text="pit-rerun-v1+abc", market="NASDAQ", as_of=T.astimezone(timezone(timedelta(hours=-3))), manifest={"a": {"x": None, "y": 1.5}, "b": [1, 2]})
    assert key != pit.run_key_of(source_version_text="pit-rerun-v1+abd", market="NASDAQ", as_of=T, manifest=manifest)
    assert pit.advisory_lock_key(key) == int.from_bytes(bytes.fromhex(key[:16]), "big", signed=True) and -(2 ** 63) <= pit.advisory_lock_key(key) < 2 ** 63
    assert pit.advisory_lock_key("ff" * 32) == -1 and pit.advisory_lock_key("7f" + "ff" * 31) == 2 ** 63 - 1


def test_two_identical_runs_give_one_cycle_and_zero_new_rows() -> None:
    database = _ready()
    first, _ = _service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW)
    second, _ = _service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW + timedelta(days=1))  # another instance, another clock: same inputs
    assert second["run_key"] == first["run_key"] and second["cycle_id"] == first["cycle_id"] and second["idempotent"] is True
    assert second["records"] == {"expected": 6, "stored_before": 6, "inserted": 0, "complete": True} and second["published_at"] == first["published_at"]
    assert len(database._valuation_predictions) == 6 and sum(1 for s in database._analysis_snapshots if s["analysis_type"] == pit.ANALYSIS_TYPE) == 1


def test_an_interrupted_run_is_completed_under_the_same_cycle_without_duplicates(monkeypatch: pytest.MonkeyPatch) -> None:
    database = _ready()
    real_insert = database.insert_valuation_predictions

    def half_then_die(records: list[dict]) -> int:
        real_insert(records[: len(records) // 2])
        raise RuntimeError("process killed after a partial persistence")

    monkeypatch.setattr(database, "insert_valuation_predictions", half_then_die)
    with pytest.raises(RuntimeError, match="partial persistence"):
        _service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW)
    monkeypatch.undo()
    snapshot = next(s for s in database._analysis_snapshots if s["analysis_type"] == pit.ANALYSIS_TYPE)
    assert len(database._valuation_predictions) == 3
    receipt, _ = _service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW + timedelta(hours=5))
    assert receipt["cycle_id"] == snapshot["id"] and receipt["idempotent"] is True and receipt["records"] == {"expected": 6, "stored_before": 3, "inserted": 3, "complete": True}
    records = database.valuation_predictions_for_cycle(receipt["cycle_id"], source=pit.SOURCE)
    assert set(records) == set(SYMBOLS) and len(database._valuation_predictions) == 6
    assert {(s, r["row_sha256"]) for s, r in records.items()} == {tuple(pair) for pair in snapshot["outputs"]["prediction_identities"]}  # the SET, not a count
    assert all(r["published_at"] == snapshot["published_at"].isoformat() for r in records.values())  # completed rows carry the cycle's clock
    # a stored identity the computation does not reproduce is an integrity failure, never silently completed
    database._valuation_predictions.append({**records["AAA"], "symbol": "AAA", "row_sha256": "0" * 64, "id": "x", "source_version": "other"})
    database.drop_official_cycle_cache()
    with pytest.raises(pit.PitRerunIntegrityError, match="does not reproduce"):
        _service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW + timedelta(hours=6))


def test_changed_inputs_make_a_new_run_key_naming_the_superseded_one() -> None:
    database = _ready()
    first, _ = _service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW)
    _publish_sources(database, symbols=("AAA",), at=VINTAGE_AT + timedelta(hours=1), scale={"AAA": 1.3}, catalogue=False)  # a new fundamentals payload for one name
    second, _ = _service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW + timedelta(hours=1))
    assert second["run_key"] != first["run_key"] and second["cycle_id"] != first["cycle_id"] and second["supersedes"] == first["run_key"] and second["idempotent"] is False
    snapshot = database.latest_analysis_snapshot(pit.ANALYSIS_TYPE, second["entity_key"])
    assert snapshot is not None and snapshot["inputs"]["supersedes"] == first["run_key"] and second["records"]["inserted"] == 6
    assert len(database._valuation_predictions) == 12  # two cycles, nothing rewritten
    first_snapshot = database.latest_analysis_snapshot(pit.ANALYSIS_TYPE, first["entity_key"])
    assert first_snapshot is not None and "supersedes" not in first_snapshot["inputs"]
    # another T is another run, never a supersession
    other, _ = _service(database).rerun("NASDAQ", as_of=T - timedelta(days=7), clock=lambda: NOW + timedelta(hours=2))
    assert other["supersedes"] is None and other["run_key"] not in (first["run_key"], second["run_key"])


def _panel_cell(database: Database, *, cut: datetime) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    reader = series.PriceHistoryService(_settings(), database, panel._NoNetworkHttp())
    receipt, detail = panel.PanelService(database, price_history=reader).run(cut=cut, markets=["NASDAQ"], sources=[pit.SOURCE])
    return receipt["payload"]["results"]["NASDAQ"][pit.SOURCE], detail


def test_the_panel_serves_the_current_run_and_refuses_the_superseded_one() -> None:
    # P2-2 (a): run 1 → changed fundamentals → run 2 (supersedes run 1): the panel serves run 2's cycle, run 1's rows are ``superseded_run``
    database = _ready()
    first, _ = _service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW)
    _publish_sources(database, symbols=("AAA",), at=VINTAGE_AT + timedelta(hours=1), scale={"AAA": 1.3}, catalogue=False)
    second, _ = _service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW + timedelta(hours=1))
    assert second["supersedes"] == first["run_key"] and len(database._valuation_predictions) == 12
    assert panel.superseded_run_keys(database, market="NASDAQ", as_of=T.isoformat()) == {first["run_key"]}
    cell, detail = _panel_cell(database, cut=NOW + timedelta(hours=2))
    assert cell["records"] == {"read": 12, "admissible": 6, "refused": {"superseded_run": 6}, "reruns": 0}  # never ``duplicate_session`` on the OLD cycle
    assert {row["cycle_id"] for row in detail} == {second["cycle_id"]} and len(detail) == 6
    # a third run (inputs changed again) supersedes transitively: both earlier cycles refused
    _publish_sources(database, symbols=("BBB",), at=VINTAGE_AT + timedelta(hours=2), scale={"BBB": 0.8}, catalogue=False)
    third, _ = _service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW + timedelta(hours=3))
    assert third["supersedes"] == second["run_key"]
    assert panel.superseded_run_keys(database, market="NASDAQ", as_of=T.isoformat()) == {first["run_key"], second["run_key"]}
    cell, detail = _panel_cell(database, cut=NOW + timedelta(hours=4))
    assert cell["records"]["refused"] == {"superseded_run": 12} and {row["cycle_id"] for row in detail} == {third["cycle_id"]}
    # another T is untouched by the chain
    assert panel.superseded_run_keys(database, market="NASDAQ", as_of=(T - timedelta(days=7)).isoformat()) == set()


def test_the_panel_never_mixes_a_crashed_partial_cycle_with_the_run_that_superseded_it(monkeypatch: pytest.MonkeyPatch) -> None:
    # P2-2 (a), crash variant: 3 rows persisted, then the inputs change → a new run; the panel serves ONLY the new cycle
    database = _ready()
    real_insert = database.insert_valuation_predictions

    def three_then_die(records: list[dict]) -> int:
        real_insert(records[:3])
        raise RuntimeError("killed after three rows")

    monkeypatch.setattr(database, "insert_valuation_predictions", three_then_die)
    with pytest.raises(RuntimeError, match="killed"):
        _service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW)
    monkeypatch.undo()
    partial = next(s for s in database._analysis_snapshots if s["analysis_type"] == pit.ANALYSIS_TYPE)
    assert len(database._valuation_predictions) == 3
    _publish_sources(database, symbols=("AAA",), at=VINTAGE_AT + timedelta(hours=1), scale={"AAA": 1.3}, catalogue=False)
    receipt, _ = _service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW + timedelta(hours=1))
    assert receipt["supersedes"] == partial["inputs"]["run_key"] and receipt["cycle_id"] != partial["id"] and receipt["records"]["inserted"] == 6
    cell, detail = _panel_cell(database, cut=NOW + timedelta(hours=2))
    assert cell["records"] == {"read": 9, "admissible": 6, "refused": {"superseded_run": 3}, "reruns": 0}
    assert {row["cycle_id"] for row in detail} == {receipt["cycle_id"]} and len(detail) == 6


def test_an_identical_catalogue_republished_is_the_same_run() -> None:
    # P2-2 (b): the manifest names the catalogue by the canonical hash of the admitted classification, never by snapshot id/clock
    database = _ready()
    first, run = _service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW)
    catalogue_ref = next(ref for ref in run.manifest["sources"] if ref["role"] == "catalogue")
    assert set(catalogue_ref) == {"role", "market", "classification_sha256", "rows", "fields_admitted"} and catalogue_ref["rows"] == 6
    assert catalogue_ref["classification_sha256"] == official.canonical_sha256(sorted(({"symbol": s, "sector": SECTOR, "industry": "Machinery", "valuation_profile": "general",
                                                                                          "security_type": "Stock"} for s in SYMBOLS), key=lambda r: r["symbol"]))
    database.save_analysis_snapshot("valuation_universe", "NASDAQ_UNIVERSE", "mv-cat", {"methodology_version": 7},  # the nightly re-publication of the SAME universe
                                    {"rows": [{"symbol": s, "sector": SECTOR, "industry": "Machinery", "valuation_profile": "general", "security_type": "Stock",
                                               "price": 2.0, "pe": 1.0, "our_tp": 3.0} for s in reversed(SYMBOLS)]}, VINTAGE_AT + timedelta(days=1, hours=1))  # other order, other current numbers
    second, again = _service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW + timedelta(days=1, hours=2))
    assert second["run_key"] == first["run_key"] and second["idempotent"] is True and second["records"]["inserted"] == 0 and len(database._valuation_predictions) == 6
    assert again.resolver.catalogue_snapshot_id != run.resolver.catalogue_snapshot_id and second["catalogue_snapshot_id"] == again.resolver.catalogue_snapshot_id
    # a changed classification IS another run
    database.save_analysis_snapshot("valuation_universe", "NASDAQ_UNIVERSE", "mv-cat", {"methodology_version": 7},
                                    {"rows": [{"symbol": s, "sector": SECTOR if s != "AAA" else "Energy", "industry": "Machinery", "valuation_profile": "general", "security_type": "Stock"}
                                              for s in SYMBOLS]}, VINTAGE_AT + timedelta(days=2))
    third, _ = _service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW + timedelta(days=2))
    assert third["run_key"] != first["run_key"] and third["supersedes"] == first["run_key"]


def test_persist_raises_when_the_cycle_would_stay_incomplete(monkeypatch: pytest.MonkeyPatch) -> None:
    # P3-5: stored + inserted != expected is an integrity failure, never a silent ``complete: false``
    database = _ready()
    monkeypatch.setattr(database, "insert_valuation_predictions", lambda records: 0)
    with pytest.raises(pit.PitRerunIntegrityError, match=r"0 stored \+ 0 inserted != 6 expected"):
        _service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW)


def test_two_concurrent_runs_leave_one_cycle() -> None:
    database = _ready()
    receipts: list[dict] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def run() -> None:
        try:
            barrier.wait()
            receipts.append(_service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW)[0])
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors and len(receipts) == 2
    assert {r["cycle_id"] for r in receipts} == {receipts[0]["cycle_id"]} and sorted(r["idempotent"] for r in receipts) == [False, True]
    assert sum(r["records"]["inserted"] for r in receipts) == 6 and len(database._valuation_predictions) == 6
    assert sum(1 for s in database._analysis_snapshots if s["analysis_type"] == pit.ANALYSIS_TYPE) == 1


# ------------------------------------------------------------------ the official selection keeps refusing v3_2_shadow
def test_v3_2_shadow_is_recordable_but_the_official_selection_refuses_it() -> None:
    assert official.RECORDABLE_SOURCES == (*OFFICIAL_SOURCES, "v3_2_shadow") and "v3_2_shadow" not in OFFICIAL_SOURCES
    assert official._selected_source({"generation_id": "g", "source": "v3_2_shadow"}) is None  # Q3: not servable, loudly
    database = _database()
    with pytest.raises(ValueError, match="not an official source"):
        database.insert_valuation_official_selection({"generation_id": "g1", "source": "v3_2_shadow", "source_version": "x", "cycles": {}, "targeted": {},
                                                      "session_dates": {}, "validated_complete": True, "activated_at": NOW, "activated_by": "t",
                                                      "previous_generation_id": None, "receipt": {}})
    with pytest.raises(ValueError):
        official.select_generation(database, cycles={"B3": "c", "NASDAQ": "c", "NYSE": "c"}, now=datetime.now(UTC), activated_by="mesa", reason="try",
                                   source="v3_2_shadow")
    assert database.latest_valuation_official_selection() is None


# ------------------------------------------------------------------ the hash survives the NUMERIC round trip (Decimal(repr()) discipline)
def _pg_row(record: dict[str, Any]) -> tuple[Any, ...]:
    numeric = Database._numeric_param
    return (record["id"], record["source"], record["source_version"], record["market"], record["symbol"], record["scope"], record["session_date"], record["cycle_id"],
            datetime.fromisoformat(record["prediction_instant"]), datetime.fromisoformat(record["published_at"]), numeric(record["tp"]), numeric(record["buy_in"]),
            numeric(record["internal_tp"]), numeric(record["consensus_tp"]), record["consensus_source"], record["analyst_count"], numeric(record["consensus_weight_percent"]),
            numeric(record["price"]), record["currency"], json.loads(json.dumps(record["decomposition"])), record["row_sha256"])


def test_row_sha256_is_reproducible_after_the_numeric_round_trip() -> None:
    database = _ready()
    receipt, run = _service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW)
    records = database.valuation_predictions_for_cycle(receipt["cycle_id"], source=pit.SOURCE)
    for record in records.values():
        assert isinstance(record["tp"], float) and Decimal(repr(record["tp"])) == Database._numeric_param(record["tp"]) and float(Database._numeric_param(record["tp"])) == record["tp"]  # type: ignore[arg-type]
        rebuilt = database._prediction_record(_pg_row(record))
        assert rebuilt == record
        core = {key: value for key, value in rebuilt.items() if key not in ("id", "row_sha256")}
        assert official.canonical_sha256(core) == record["row_sha256"]
    # the identities the computation recomputes for the same cycle and clock are exactly the stored ones
    again = run.records(cycle_id=receipt["cycle_id"], published_at=datetime.fromisoformat(receipt["published_at"]))
    assert {(r["symbol"], r["row_sha256"]) for r in again} == {(s, r["row_sha256"]) for s, r in records.items()}


# ------------------------------------------------------------------ the panel classifies every record retrospective
def test_the_panel_classifies_every_pit_record_retrospective_and_never_in_the_decision() -> None:
    database = _ready()
    _service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW)
    reader = series.PriceHistoryService(_settings(), database, panel._NoNetworkHttp())
    service = panel.PanelService(database, price_history=reader)
    receipt, detail = service.run(cut=NOW + timedelta(hours=1), markets=["NASDAQ"], sources=[pit.SOURCE])
    cell = receipt["payload"]["results"]["NASDAQ"][pit.SOURCE]
    assert cell["records"]["read"] == 6 and cell["records"]["admissible"] == 6 and cell["observations"]["cohort"] == {"retrospective": 6}
    assert cell["retrospective"]["observations"]["n"] == 6 and cell["retrospective"]["diagnostic_only"] is True and cell["retrospective"]["decision"] is None
    assert cell["decision"]["status"] == "UNMEASURED" and "no_live_cohort" in cell["decision"]["reasons"]
    assert all(row["cohort"] == "retrospective" and row["source"] == "v3_2_shadow" for row in detail)
    assert all(row["horizons"]["126"]["status"] == "labelled" for row in detail)  # T + 126 sessions closed long before the cut: measured, apart


# ------------------------------------------------------------------ --fetch and the CLI
def test_fetch_persists_dated_hashed_snapshots_and_prints_nothing_nominal(capsys: pytest.CaptureFixture[str]) -> None:
    database = _database()
    database.save_analysis_snapshot("valuation_universe", "NASDAQ_UNIVERSE", "mv", {}, {"rows": [{"symbol": "AAA"}, {"symbol": "BBB"}]}, NOW)
    targets = [_target("H1", T, 100.0)]
    http = ScriptedHttp({"/api/v1.1/fundamentals/AAA.US": _payload("AAA", poison=True), "/api/v1.1/fundamentals/BBB.US": {},
                         "/stable/price-target-news": targets, "/api/eod/US3Y.GBOND": [{"date": "2024-06-13", "close": 4.3}], "/api/eod/US10Y.GBOND": [{"date": "2024-06-13", "close": 5.0}]})
    assert pit.main(["--market", "NASDAQ", "--fetch"], database=database, settings=_settings(), http=http) == 0  # type: ignore[arg-type]
    out = capsys.readouterr().out
    assert "AAA" not in out and "BBB" not in out
    printed = json.loads(out)
    assert printed["symbols_requested"] == 2 and printed["fundamentals_persisted"] == 1 and printed["fundamentals_failed:PitRerunInputError"] == 1 and printed["targets_persisted"] == 2
    snapshot = database.latest_analysis_snapshot(pit.SOURCE_ANALYSIS_TYPE, pit.source_entity_key("NASDAQ", pit.PROVIDER_EODHD, "AAA"))
    assert snapshot is not None and snapshot["inputs"]["payload_sha256"] == official.canonical_sha256(_payload("AAA", poison=True)) == snapshot["outputs"]["payload_sha256"]
    assert snapshot["inputs"]["symbol_sha256"] == pit.symbol_hash("AAA") and datetime.fromisoformat(snapshot["inputs"]["fetched_at"]) <= datetime.now(UTC)
    assert snapshot["outputs"]["payload"]["Financials"]["Income_Statement"]["yearly"]["2023-12-31"]["filing_date"] == "2024-02-14"  # RAW: the filter happens at rerun time
    macro = database.latest_analysis_snapshot(pit.SOURCE_ANALYSIS_TYPE, pit.MACRO_TREASURY_KEY)
    assert macro is not None and macro["outputs"]["payload"]["series"]["US3Y.GBOND"] == [{"date": "2024-06-13", "close": 4.3}] and len(macro["outputs"]["payload_sha256"]) == 64
    assert sum(1 for url in http.calls if "fundamentals" in url) == 2 and sum(1 for url in http.calls if "price-target-news" in url) == 2  # one read per symbol and provider
    assert pit.curve_package_at(macro["outputs"]["payload"], as_of=T, economic_date=date(2024, 6, 14)) is not None
    # P3-4: a price-target payload that is not the provider's list (an error object) is refused, never persisted as an empty history
    broken = ScriptedHttp({"/api/v1.1/fundamentals/CCC.US": _payload("CCC"), "/stable/price-target-news": {"Error Message": "limit reached"}})
    fetcher = pit.PitFetchService(_settings(), database, broken)  # type: ignore[arg-type]
    with pytest.raises(pit.PitRerunInputError, match="not a list"):
        fetcher.fetch_targets("NASDAQ", "CCC")
    counts = fetcher.fetch("NASDAQ", ["CCC"], macro=False)
    assert counts["fundamentals_persisted"] == 1 and counts["targets_failed:PitRerunInputError"] == 1 and "targets_persisted" not in counts
    assert database.latest_analysis_snapshot(pit.SOURCE_ANALYSIS_TYPE, pit.source_entity_key("NASDAQ", pit.PROVIDER_FMP, "CCC")) is None


def test_cli_rerun_requires_a_zoned_as_of_writes_the_private_detail_exclusively_and_prints_aggregates_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    database = _ready()
    with pytest.raises(SystemExit):
        pit.main(["--market", "NASDAQ", "--rerun", "--as-of", "2024-06-14T21:00:00"], database=database, settings=_settings())  # naive: refused
    with pytest.raises(SystemExit):
        pit.main(["--market", "NASDAQ", "--rerun"], database=database, settings=_settings())
    with pytest.raises(SystemExit):
        pit.main(["--market", "NASDAQ", "--fetch", "--as-of", "2024-06-14T21:00:00+00:00"], database=database, settings=_settings())
    capsys.readouterr()
    detail = tmp_path / "detail.json"
    assert pit.main(["--market", "NASDAQ", "--rerun", "--as-of", "2024-06-14T18:00:00-03:00", "--detail", str(detail)], database=database, settings=_settings()) == 0
    out = capsys.readouterr().out
    printed = json.loads(out)
    assert printed["as_of"] == T.isoformat() and printed["records"]["inserted"] == 6 and all(symbol not in out for symbol in SYMBOLS)
    assert stat.S_IMODE(os.stat(detail).st_mode) == 0o600
    written = json.loads(detail.read_text(encoding="utf-8"))
    assert set(written["results"]) == set(SYMBOLS) and written["run_key"] == printed["run_key"]
    with pytest.raises(SystemExit):  # an existing path is refused by the parser before anything runs
        pit.main(["--market", "NASDAQ", "--rerun", "--as-of", "2024-06-14T18:00:00-03:00", "--detail", str(detail)], database=database, settings=_settings())
    link = tmp_path / "link.json"
    link.symlink_to(tmp_path / "missing.json")
    with pytest.raises(SystemExit):
        pit.main(["--market", "NASDAQ", "--rerun", "--as-of", "2024-06-14T18:00:00-03:00", "--detail", str(link)], database=database, settings=_settings())
    with pytest.raises(FileExistsError):
        pit.write_private_detail(link, {})
    assert not (tmp_path / "missing.json").exists()


def test_the_run_refuses_a_naive_t_and_counts_inadmissible_names() -> None:
    database = _ready()
    service = _service(database)
    with pytest.raises(pit.PitRerunInputError, match="time zone"):
        service.compute("NASDAQ", as_of=datetime(2024, 6, 14, 21, 0), prices=service.pin_vintage("NASDAQ", as_of=T, pinned_at=NOW))
    # a T with fewer than 90 valid sessions in the vintage for every name: nothing evaluated, everything explained
    early = datetime(2023, 8, 1, 21, 0, tzinfo=UTC)
    receipt, run = service.rerun("NASDAQ", as_of=early, clock=lambda: NOW)
    assert receipt["evaluated"] == 0 and receipt["records"]["expected"] == 0 and run.resolver.not_evaluable == {s: "fewer_than_90_valid_sessions_at_T" for s in SYMBOLS}
