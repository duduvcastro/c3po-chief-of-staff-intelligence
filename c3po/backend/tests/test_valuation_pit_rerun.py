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
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, time as wall_time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

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
from tests import asfiled_front

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


def _quarterly_income(rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {"Financials": {"Income_Statement": {"quarterly": rows}}}


def _eligible_quarters(payload: dict[str, Any], market: str, economic_date: date) -> tuple[list[tuple[str, str]], dict[str, int]]:
    excluded: Counter[str] = Counter()
    rows = pit.eligible_statements(payload, market=market, economic_date=economic_date, excluded=excluded)["Income_Statement"]["quarterly"]
    return [(row["period_end"].isoformat(), row["availability"]["available_at"]) for row in rows], dict(excluded)


def test_a_period_after_t_and_a_us_filing_before_the_period_end_are_refused_and_counted() -> None:
    at = date(2026, 9, 25)
    rows, excluded = _eligible_quarters(_quarterly_income({
        "2026-12-31": {"date": "2026-12-31", "filing_date": "2026-09-01", "totalRevenue": 999},  # a FUTURE period "filed" before T
        "2026-06-30": {"date": "2026-06-30", "filing_date": "2026-08-01", "totalRevenue": 100},  # the only sound one
        "2026-03-31": {"date": "2026-03-31", "filing_date": "2026-01-15", "totalRevenue": 50},   # filed before its own period end
        "2025-12-31": {"date": "2025-12-31", "totalRevenue": 40}}), "NASDAQ", at)                # no filing date: unchanged rule, not eligible
    assert rows == [("2026-06-30", "2026-08-01")]
    assert excluded == {"Income_Statement.quarterly:period_after_T": 1, "Income_Statement.quarterly:filing_before_period_end": 1,
                        "Income_Statement.quarterly:filing_date_missing": 1}


def test_the_boundaries_period_end_equal_to_t_and_filing_equal_to_period_end_are_accepted() -> None:
    at = date(2024, 6, 14)
    rows, excluded = _eligible_quarters(_quarterly_income({
        "2024-06-14": {"date": "2024-06-14", "filing_date": "2024-06-14", "totalRevenue": 10},   # period_end == T == filing_date
        "2024-03-31": {"date": "2024-03-31", "filing_date": "2024-03-31", "totalRevenue": 9}}), "NYSE", at)  # filing == period end
    assert rows == [("2024-06-14", "2024-06-14"), ("2024-03-31", "2024-03-31")] and excluded == {}


def test_b3_eligibility_is_unchanged_by_the_date_sanity_rules() -> None:
    at = date(2024, 6, 14)
    payload = _quarterly_income({
        "2024-09-30": {"date": "2024-09-30", "filing_date": "2024-06-01", "totalRevenue": 999},  # future: excluded before as well (lag), now named period_after_T
        "2024-03-31": {"date": "2024-03-31", "filing_date": "2024-03-31", "totalRevenue": 9},    # +90 d = 2024-06-29 > T: not available
        "2024-03-15": {"date": "2024-03-15", "filing_date": "2024-01-01", "totalRevenue": 8},    # B3 filing_date is not evidence: never checked
        "2023-12-31": {"date": "2023-12-31", "totalRevenue": 7}})                                 # B3 ignores a missing filing_date
    rows, excluded = _eligible_quarters(payload, "B3", at)
    assert rows == [("2024-03-15", "2024-06-13"), ("2023-12-31", "2024-03-30")]
    assert excluded == {"Income_Statement.quarterly:period_after_T": 1, "Income_Statement.quarterly:not_available_at_T": 1}
    # the B3 fixture used by the rest of the suite: the eligible set at every T is exactly {period_end + 90 d ≤ T}
    for economic_date in (date(2024, 3, 29), date(2024, 3, 30), date(2024, 6, 29), date(2024, 12, 31)):
        statements = pit.eligible_statements(_payload("PETR", b3=True), market="B3", economic_date=economic_date, excluded=Counter())
        for by_frequency in statements.values():
            for frequency, eligible in by_frequency.items():
                periods = {date.fromisoformat(key) for key in _payload("PETR", b3=True)["Financials"]["Income_Statement"][frequency]}
                assert [row["period_end"] for row in eligible] == sorted((p for p in periods if p + timedelta(days=90) <= economic_date), reverse=True)


def test_the_ttm_and_the_balance_sheet_never_use_a_future_quarter_or_a_filing_before_its_period() -> None:
    at = date(2024, 6, 14)
    clean = pit.pit_fundamentals(_payload("AAA"), market="NASDAQ", economic_date=at)
    contaminated = _payload("AAA")
    for statement, absurd in (("Income_Statement", {"totalRevenue": 1e15, "netIncome": 1e14, "ebitda": 1e14, "operatingIncome": 1e14}),
                              ("Balance_Sheet", {"totalStockholderEquity": 1e15, "shortTermDebt": 1e14, "longTermDebt": 1e14, "cashAndEquivalents": 1.0,
                                                 "commonStockSharesOutstanding": 1.0}),
                              ("Cash_Flow", {"dividendsPaid": -1e14, "freeCashFlow": 1e14, "totalCashFromOperatingActivities": 1e14})):
        for frequency in ("quarterly", "yearly"):
            contaminated["Financials"][statement][frequency]["2024-09-30"] = {"date": "2024-09-30", "filing_date": "2024-06-01", **absurd}  # period after T
            contaminated["Financials"][statement][frequency]["2024-06-14"] = {"date": "2024-06-14", "filing_date": "2024-05-01", **absurd}  # filed before its end
    result = pit.pit_fundamentals(contaminated, market="NASDAQ", economic_date=at)
    for key in ("ttm", "cash_flow_ttm", "balance", "shares", "shares_availability", "revenue_growth", "fiscal_years", "fundamentals_as_of", "eligible_periods"):
        assert result[key] == clean[key], key
    assert result["balance"]["period_end"] == "2024-03-31" and result["fundamentals_as_of"] == "2024-03-31"
    for statement in ("Income_Statement", "Balance_Sheet", "Cash_Flow"):
        for frequency in ("quarterly", "yearly"):
            assert result["excluded"][f"{statement}.{frequency}:period_after_T"] == 1
            assert result["excluded"][f"{statement}.{frequency}:filing_before_period_end"] == 1


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


def test_an_explicit_price_pin_gives_every_run_of_a_grid_one_vintage_and_names_the_run_by_the_publication(capsys: pytest.CaptureFixture[str]) -> None:
    # P2-1: the nightly series republishes its whole window; a grid run across a phase must not mix vintages
    database = _ready()
    first = database.latest_analysis_snapshot(series.PUBLICATION_TYPE, "NASDAQ")
    assert first is not None
    sessions = _sessions("2023-06-01", "2026-09-10")
    doubled = {f"{symbol}.US": [{**bar, "close": bar["close"] * 2, "adjusted_close": bar["adjusted_close"] * 2} for bar in _bars_for(symbol, sessions, base=100.0 + 10 * i)]
               for i, symbol in enumerate(SYMBOLS)}
    newer = _publish_prices(database, bars=doubled, at=VINTAGE_AT + timedelta(hours=1))["publication_id"]  # the store moved on before the grid started
    pin = VINTAGE_AT + timedelta(minutes=30)
    grid = [_service(database).rerun("NASDAQ", as_of=T - timedelta(days=7 * k), clock=lambda k=k: NOW + timedelta(hours=k), price_pinned_at=pin) for k in range(3)]
    assert {receipt["price_vintage"] for receipt, _ in grid} == {first["id"]} != {newer}  # every T of the grid: the pinned publication, never the newer one
    assert all(receipt["price_pin"] == {"mode": "explicit", "requested_at": pin.isoformat(), "resolved_publication_id": first["id"]} for receipt, _ in grid)
    receipt, run = grid[0]
    snapshot = database.latest_analysis_snapshot(pit.ANALYSIS_TYPE, receipt["entity_key"])
    assert snapshot is not None and snapshot["inputs"]["price_pin"] == receipt["price_pin"] and "price_pin" not in run.manifest  # beside the manifest, never in run_key
    assert set(run.manifest["price_vintage"]) == {"publication_id", "price_snapshot_id", "available_at", "bars_sha256", "window", "historical_vintage"}
    # the pin is a pointer: another instant resolving the SAME publication is the same run (no supersession, nothing written)
    again, _ = _service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW + timedelta(days=1), price_pinned_at=VINTAGE_AT + timedelta(minutes=45))
    assert again["run_key"] == receipt["run_key"] and again["idempotent"] is True and again["records"]["inserted"] == 0 and again["supersedes"] is None
    # without a pin the run start's clock resolves the newer publication: another run, superseding the pinned one
    unpinned, later = _service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW + timedelta(days=2))
    assert unpinned["price_vintage"] == newer and unpinned["price_pin"]["mode"] == "run_start" and unpinned["supersedes"] == receipt["run_key"]
    assert all(later.resolver.per_symbol[s]["row"]["price"] == 2 * run.resolver.per_symbol[s]["row"]["price"] for s in SYMBOLS)
    # refusals: a naive pin; a pin after the run start (it would resolve another vintage when repeated); a pin before any publication
    with pytest.raises(pit.PitRerunInputError, match="time zone"):
        _service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW, price_pinned_at=datetime(2026, 9, 11, 3, 30))
    with pytest.raises(pit.PitRerunInputError, match="after the run start"):
        _service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW, price_pinned_at=NOW + timedelta(seconds=1))
    with pytest.raises(pit.PitRerunInputError, match="no verifiable price vintage"):
        _service(database).rerun("NASDAQ", as_of=T, clock=lambda: NOW, price_pinned_at=VINTAGE_AT - timedelta(days=1))
    # the CLI: zone mandatory, --rerun only; the printed receipt names the pinned publication
    with pytest.raises(SystemExit):
        pit.main(["--market", "NASDAQ", "--rerun", "--as-of", "2024-06-14T18:00:00-03:00", "--price-pinned-at", "2026-09-11T03:30:00"], database=database, settings=_settings())
    with pytest.raises(SystemExit):
        pit.main(["--market", "NASDAQ", "--fetch", "--price-pinned-at", "2026-09-11T03:30:00+00:00"], database=database, settings=_settings())
    capsys.readouterr()
    assert pit.main(["--market", "NASDAQ", "--rerun", "--as-of", "2024-05-31T18:00:00-03:00", "--price-pinned-at", "2026-09-11T00:30:00-03:00"],
                    database=database, settings=_settings()) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["price_vintage"] == first["id"] and printed["price_pin"]["mode"] == "explicit" and printed["price_pin"]["requested_at"] == "2026-09-11T03:30:00+00:00"


def test_a_bar_dated_off_the_exchange_calendar_is_never_read_and_is_counted() -> None:
    """Design §2: sessions off the calendar are excluded from windows, counts and prices. The producer validates ISO dates,
    not the calendar (inventory rev 4a §2 C: one B3 bar on Saturday 2024-03-16), so the PIT reader must drop them itself."""
    at = datetime(2024, 6, 17, 21, 0, tzinfo=UTC)  # Monday 2024-06-17, an XNYS session (closed 20:00Z)
    sessions = _sessions("2023-06-01", "2026-09-10")
    clean = {f"{symbol}.US": _bars_for(symbol, sessions, base=100.0 + 10 * i) for i, symbol in enumerate(SYMBOLS)}
    clean["AAA.US"] = [bar for bar in clean["AAA.US"] if bar["date"] != "2024-06-17"]  # AAA has no bar on the session of T (both stores)
    absurd = {"close": 9_999.0, "adjusted_close": 9_999.0, "volume": 1.0}
    dirty = {key: list(rows) for key, rows in clean.items()}
    dirty["AAA.US"] = sorted(dirty["AAA.US"] + [{"date": "2024-06-15", **absurd}], key=lambda bar: bar["date"])  # Saturday after the last AAA bar ≤ T
    dirty["BBB.US"] = sorted(dirty["BBB.US"] + [{"date": "2024-03-16", **absurd}], key=lambda bar: bar["date"])  # Saturday inside the beta window
    dirty["CCC.US"] = sorted(dirty["CCC.US"] + [{"date": "2024-06-22", **absurd}], key=lambda bar: bar["date"])  # Saturday after T: filtered by date
    computations = {}
    for name, bars in (("clean", clean), ("dirty", dirty)):
        database = _database()
        _publish_prices(database, bars=bars)
        _publish_sources(database)
        service = _service(database)
        prices = service.pin_vintage("NASDAQ", as_of=at, pinned_at=NOW)
        computations[name] = service.compute("NASDAQ", as_of=at, prices=prices)
    clean_run, dirty_run = computations["clean"], computations["dirty"]
    assert "2024-06-15" in [bar["date"] for bar in dirty["AAA.US"]]  # the store DOES hold the Saturday bars...
    assert "2024-06-15" not in dirty_run.resolver.prices.bars("AAA") and "2024-03-16" not in dirty_run.resolver.prices.bars("BBB")  # ...never served
    assert dirty_run.resolver.prices.off_calendar_bars == 2 and clean_run.resolver.prices.off_calendar_bars == 0  # the one after T is outside the date filter
    assert dirty_run.resolver.excluded["price_bars:off_calendar_session"] == 2 and "price_bars:off_calendar_session" not in clean_run.resolver.excluded
    # the price of T is the last CALENDAR session ≤ T (Friday 2024-06-14), never the Saturday bar; beta and the 90-session count unchanged
    assert dirty_run.resolver.per_symbol["AAA"]["row"]["price"] == clean_run.resolver.per_symbol["AAA"]["row"]["price"] != absurd["close"]
    assert dirty_run.resolver.per_symbol["AAA"]["row"]["price_session"] == "2024-06-14"
    for symbol in SYMBOLS:
        assert dirty_run.resolver.per_symbol[symbol] == clean_run.resolver.per_symbol[symbol], symbol
        assert dirty_run.resolver.prices.valid_sessions(symbol) == clean_run.resolver.prices.valid_sessions(symbol)
    assert dirty_run.results == clean_run.results  # the engine sees exactly the clean inputs
    excluded_clean = dict(clean_run.resolver.excluded)
    excluded_dirty = {key: value for key, value in dirty_run.resolver.excluded.items() if key != "price_bars:off_calendar_session"}
    assert excluded_dirty == excluded_clean


def test_a_bar_date_the_calendar_cannot_place_is_a_refusal_never_a_silent_drop(monkeypatch: pytest.MonkeyPatch) -> None:
    """P3-3 of the 10/10 review (mutant M6: the ``PitRerunInputError`` of ``_is_calendar_session`` replaced by ``return
    False`` survived every test): a bar ≤ T dated where the exchange calendar cannot answer — before its first session
    (≈ 20 years back) or not a date at all — refuses the run; it is never dropped and counted as an off-calendar bar."""
    database = _ready()
    service = _service(database)
    pinned = service.pin_vintage("NASDAQ", as_of=T, pinned_at=NOW)
    sound = {"close": 100.0, "adjusted_close": 100.0, "volume": 1.0}
    held = {"2005-01-03": dict(sound), "2024-06-13": dict(sound), "2024-06-14": dict(sound)}  # 2005-01-03: a Monday before the calendar's first session
    monkeypatch.setattr(pinned.reader, "series", lambda market, symbol, *, available_before: {"status": "ok", "publication_id": pinned.publication_id,
                                                                                             "bars": {key: dict(value) for key, value in held.items()}})
    with pytest.raises(pit.PitRerunInputError, match="calendar cannot place a bar dated '2005-01-03'"):
        pinned.bars("AAA")
    assert pinned.off_calendar_bars == 0 and "AAA" not in pinned._bars  # refused: nothing kept, nothing counted as "off calendar"
    with pytest.raises(pit.PitRerunInputError, match="calendar cannot place a bar dated '2024-13-01'"):
        pinned._is_calendar_session("2024-13-01")
    with pytest.raises(pit.PitRerunInputError, match="calendar cannot place"):  # the whole run refuses, it never computes around the bar
        service.compute("NASDAQ", as_of=T, prices=pinned)


def _publish_b3_prices(database: Database, bars: dict[str, list[dict]]) -> dict[str, Any]:
    http = ScriptedHttp({f"/api/eod/{key}": rows for key, rows in bars.items()})
    producer = series.PriceHistoryService(_settings(), database, http, eodhd=EodhdClient("https://eodhd.com", "secret", http))  # type: ignore[arg-type]
    return producer.persist_run("B3", start=date(2023, 6, 1), end=date(2026, 9, 10), symbols=[key.split(".")[0] for key in bars], now=VINTAGE_AT)


def test_weekday_holidays_and_b3_closures_are_off_calendar_bars_dropped_and_counted() -> None:
    # XNYS: Good Friday 2024-03-29 inside the beta window, and Independence Day (Thursday 2024-07-04) right before T — AAA has no bar on
    # the session of T (Friday 2024-07-05), so without the calendar the holiday bar would become the price of T
    at = datetime(2024, 7, 5, 21, 0, tzinfo=UTC)
    absurd = {"close": 9_999.0, "adjusted_close": 9_999.0, "volume": 1.0}
    clean = _clean_bars()
    clean["AAA.US"] = [bar for bar in clean["AAA.US"] if bar["date"] != "2024-07-05"]
    dirty = {key: list(rows) for key, rows in clean.items()}
    dirty["AAA.US"] = sorted(dirty["AAA.US"] + [{"date": "2024-07-04", **absurd}], key=lambda bar: bar["date"])
    dirty["BBB.US"] = sorted(dirty["BBB.US"] + [{"date": "2024-03-29", **absurd}], key=lambda bar: bar["date"])
    clean_run, dirty_run = _compute_with_bars(clean, at=at), _compute_with_bars(dirty, at=at)
    assert dirty_run.resolver.prices.off_calendar_bars == 2 and dirty_run.resolver.excluded["price_bars:off_calendar_session"] == 2
    assert dirty_run.resolver.per_symbol["AAA"]["row"]["price_session"] == "2024-07-03" != "2024-07-04"
    assert dirty_run.resolver.per_symbol == clean_run.resolver.per_symbol and dirty_run.results == clean_run.results
    # B3 (BVMF): carnival Monday and Tuesday 2024-02-12/13 and the Saturday 2024-03-16 the inventory found are dropped; Ash Wednesday 2024-02-14 IS a session
    database = _database()
    b3_sessions = [s.date() for s in xcals.get_calendar("BVMF").sessions_in_range("2023-06-01", "2026-09-10")]
    assert date(2024, 2, 14) in b3_sessions and date(2024, 2, 12) not in b3_sessions
    b3_bars = _bars_for("AAAA3", b3_sessions, base=30.0) + [{"date": day, **absurd} for day in ("2024-02-12", "2024-02-13", "2024-03-16")]
    _publish_b3_prices(database, {"AAAA3.SA": sorted(b3_bars, key=lambda bar: bar["date"])})
    prices = _service(database).pin_vintage("B3", as_of=datetime(2024, 6, 14, 21, 0, tzinfo=UTC), pinned_at=NOW)
    kept = prices.bars("AAAA3")
    assert prices.off_calendar_bars == 3 and not {"2024-02-12", "2024-02-13", "2024-03-16"} & set(kept) and "2024-02-14" in kept
    assert all(bar["close"] != absurd["close"] for bar in kept.values()) and prices.valid_sessions("AAAA3") == sum(1 for s in b3_sessions if s <= date(2024, 6, 14))


# ------------------------------------------------------------------ P2-2: the price basis — levels on the as-traded close, returns on the adjusted close
def _compute_with_bars(bars: dict[str, list[dict]], *, at: datetime = T) -> pit.PitComputation:
    database = _database()
    _publish_prices(database, bars=bars)
    _publish_sources(database)
    service = _service(database)
    return service.compute("NASDAQ", as_of=at, prices=service.pin_vintage("NASDAQ", as_of=at, pinned_at=NOW))


def _clean_bars() -> dict[str, list[dict]]:
    sessions = _sessions("2023-06-01", "2026-09-10")
    return {f"{symbol}.US": _bars_for(symbol, sessions, base=100.0 + 10 * i) for i, symbol in enumerate(SYMBOLS)}


def test_the_price_level_is_the_as_traded_close_and_adjusted_close_only_feeds_returns() -> None:
    clean = _clean_bars()
    doubled_close = {key: [{**bar, "close": bar["close"] * 2} for bar in rows] for key, rows in clean.items()}  # levels ×2, returns unchanged
    halved_adjusted = {key: [{**bar, "adjusted_close": bar["adjusted_close"] / 2} for bar in rows] for key, rows in clean.items()}  # a constant adjustment
    base, levels, adjusted = _compute_with_bars(clean), _compute_with_bars(doubled_close), _compute_with_bars(halved_adjusted)
    for symbol in SYMBOLS:
        row, row_levels, row_adjusted = (run.resolver.per_symbol[symbol]["row"] for run in (base, levels, adjusted))
        assert row_levels["price"] == 2 * row["price"] and row_levels["market_cap"] == 2 * row["market_cap"]  # every level reads close...
        assert row_levels["beta"] == pytest.approx(row["beta"])  # ...and never the returns
        assert row_adjusted == row  # adjusted_close never reaches a level; a constant adjustment leaves every log return as it was
    assert adjusted.results == base.results
    assert base.manifest["price_basis"] == pit.PRICE_BASIS and base.manifest["price_basis"]["level"] == "close" and base.manifest["price_basis"]["returns"] == "adjusted_close"
    assert panel.LABEL_CONVENTION == "total_return:adjusted_close"  # the panel's a(T) = adjusted_close(T) / close(T) assumes the TP on the as-traded basis
    assert "price_basis" in pit.DECLARED_ASSUMPTIONS and base.resolver.price_basis_evidence == {"symbols_read": 6, "capital_event_sessions": 0, "symbols_with_capital_events": 0}


def test_a_capital_event_between_the_shares_period_and_t_refuses_the_name_and_the_evidence_is_counted() -> None:
    clean = _clean_bars()
    bars = {key: [dict(bar) for bar in rows] for key, rows in clean.items()}

    def raw_before(key: str, session: str, factor: float) -> None:  # the as-traded close × factor before ``session``; the adjusted series stays continuous
        bars[key] = [{**bar, "close": round(bar["close"] * factor, 4)} if bar["date"] < session else bar for bar in bars[key]]

    raw_before("AAA.US", "2024-05-01", 10.0)   # 10:1 split AFTER the shares' period end (balance 2024-03-31, filed 2024-05-15) and before T: refused
    raw_before("BBB.US", "2024-02-01", 10.0)   # 10:1 split BEFORE the shares' period end: the reported count already carries it
    raw_before("CCC.US", "2024-05-01", 1 / 0.85)  # a 15 % one-day dividend: below the threshold, never a capital event
    raw_before("DDD.US", "2024-07-01", 10.0)   # a split AFTER T: outside every bar the run reads
    base, run = _compute_with_bars(clean), _compute_with_bars(bars)
    assert run.resolver.not_evaluable == {"AAA": "capital_event_between_shares_and_T"} and "AAA" not in run.results and set(run.results) == set(SYMBOLS) - {"AAA"}
    assert run.resolver.prices.capital_events("AAA") == ["2024-05-01"] and run.resolver.prices.capital_events("BBB") == ["2024-02-01"]
    assert run.resolver.prices.capital_events("CCC") == [] and run.resolver.prices.capital_events("DDD") == []
    assert run.resolver.price_basis_evidence == {"symbols_read": 6, "capital_event_sessions": 2, "symbols_with_capital_events": 2}
    assert run.summary()["price_basis_evidence"] == run.resolver.price_basis_evidence and run.summary()["not_evaluable"] == {"capital_event_between_shares_and_T": 1}
    for symbol, factor in (("BBB", 1.0), ("CCC", 1.0), ("DDD", 10.0)):  # the price of T is the as-traded close of T (DDD: before its split, 10×);
        assert run.resolver.per_symbol[symbol]["row"]["price"] == pytest.approx(factor * base.resolver.per_symbol[symbol]["row"]["price"])  # the beta
        assert run.resolver.per_symbol[symbol]["beta_audit"] == base.resolver.per_symbol[symbol]["beta_audit"]  # reads the continuous adjusted series
        assert run.resolver.per_symbol[symbol]["row"]["beta"] == pytest.approx(base.resolver.per_symbol[symbol]["row"]["beta"])


# ------------------------------------------------------------------ as-filed statements: the 051 fact store, read at accepted_at ≤ T
NEW_YORK = ZoneInfo("America/New_York")
ISSUERS = {symbol: f"00000001{index:02d}" for index, symbol in enumerate(SYMBOLS)}  # synthetic issuer keys (never a real CIK)
REVENUE, NET_INCOME, OPERATING, D_AND_A = ("us-gaap:Revenues", "us-gaap:NetIncomeLoss", "us-gaap:OperatingIncomeLoss",
                                           "us-gaap:DepreciationDepletionAndAmortization")
OPERATING_CASH, CAPEX = "us-gaap:NetCashProvidedByUsedInOperatingActivities", "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment"
EQUITY, CASH, DEBT_CURRENT, DEBT_LONG = ("us-gaap:StockholdersEquity", "us-gaap:CashAndCashEquivalentsAtCarryingValue", "us-gaap:DebtCurrent",
                                         "us-gaap:LongTermDebtNoncurrent")
SHARES = "dei:EntityCommonStockSharesOutstanding"
Fact = tuple[str, float, date, date | None]  # (concept, value, period_end, period_start — None for an instant)


@pytest.fixture
def front() -> Iterator[Any]:
    """The as-filed front's REAL modules (the tree's, else the byte-identical snapshot of fable/val-xbrl): see tests/asfiled_front.py."""
    with asfiled_front.installed() as modules:
        yield modules


def _accepted(day: date | str, at: wall_time = wall_time(16, 30)) -> datetime:
    return datetime.combine(date.fromisoformat(str(day)), at, tzinfo=NEW_YORK)


def _file(front: Any, database: Database, symbol: str, doc_id: str, accepted: datetime, facts: list[Fact], *, form: str = "10-Q") -> None:
    """One SEC document into the REAL 051 store: its registry row (with the catalogue's symbol) and its facts, as the front's
    ingestor writes them."""
    issuer, filed = ISSUERS[symbol], accepted.astimezone(NEW_YORK).date()
    store = front.statement_vintages.StatementVintageStore(database)
    store.register_filings([{"market": "US", "issuer_key": issuer, "source": front.sec_xbrl.FILING_SOURCE, "doc_id": doc_id, "form": form, "symbols": [symbol],
                             "filed_date": filed, "accepted_at": accepted, "accepted_source": "sec_header"}])
    store.insert_vintages("US", issuer, [{"market": "US", "issuer_key": issuer, "source": front.sec_xbrl.VINTAGE_SOURCE, "doc_id": doc_id, "form": form,
                                          "period_start": start, "period_end": end, "concept": concept, "unit": front.sec_xbrl.CONCEPT_UNITS[concept],
                                          "value": value, "filed_date": filed, "accepted_at": accepted} for concept, value, end, start in facts])


def _quarter_start(period_end: date) -> date:
    return date(period_end.year, period_end.month - 2, 1)


def _consistent_payload(symbol: str) -> dict[str, Any]:
    """``_payload`` made consistent with ONE set of filings: EBITDA = operating income + D&A (5 % of revenue), free cash flow
    = operating cash flow − capex (25 % of it), no dividends (the SEC ladder has no such concept) and the Q4 balance equal to
    the fiscal-year one (as filed, one fact per date)."""
    payload = _payload(symbol)
    financials = payload["Financials"]
    for rows in financials["Income_Statement"].values():
        for row in rows.values():
            row["ebitda"] = row["operatingIncome"] + row["totalRevenue"] * 0.05
    for rows in financials["Cash_Flow"].values():
        for row in rows.values():
            row.pop("dividendsPaid")
            row["freeCashFlow"] = row["totalCashFromOperatingActivities"] - abs(row["totalCashFromOperatingActivities"] * 0.25)
    for period, row in financials["Balance_Sheet"]["quarterly"].items():
        row.update(financials["Balance_Sheet"]["yearly"].get(period, {}))
    return payload


def _file_payload(front: Any, database: Database, symbol: str, payload: dict[str, Any], *, at: wall_time = wall_time(16, 30)) -> list[str]:
    """``payload`` as its SEC filer filed it: per period end ONE document (a 10-K at a fiscal-year end, else a 10-Q) accepted at
    ``at`` New York on the payload's filing date — three-month facts per quarter (the Q4 too: a filer may report it), twelve-
    month facts per year, the balance instants and the cover-page share count (dated 20 days after the period). Returns the
    document ids, oldest first."""
    financials = payload["Financials"]
    documents: list[str] = []
    for period in sorted({period for statement in financials.values() for rows in statement.values() for period in rows}):
        end, facts, filed = date.fromisoformat(period), [], None
        for frequency, start in (("quarterly", _quarter_start(end)), ("yearly", date(end.year, 1, 1))):
            income, cash = financials["Income_Statement"][frequency].get(period), financials["Cash_Flow"][frequency].get(period)
            if income:
                filed = income["filing_date"]
                facts += [(REVENUE, income["totalRevenue"], end, start), (NET_INCOME, income["netIncome"], end, start),
                          (OPERATING, income["operatingIncome"], end, start), (D_AND_A, income["totalRevenue"] * 0.05, end, start)]
            if cash:
                facts += [(OPERATING_CASH, cash["totalCashFromOperatingActivities"], end, start), (CAPEX, cash["totalCashFromOperatingActivities"] * 0.25, end, start)]
        balance = financials["Balance_Sheet"]["quarterly"].get(period) or financials["Balance_Sheet"]["yearly"].get(period)
        if balance:
            filed = filed or balance["filing_date"]
            facts += [(EQUITY, balance["totalStockholderEquity"], end, None), (CASH, balance["cashAndEquivalents"], end, None),
                      (DEBT_CURRENT, balance["shortTermDebt"], end, None), (DEBT_LONG, balance["longTermDebt"], end, None),
                      (SHARES, balance["commonStockSharesOutstanding"], end + timedelta(days=20), None)]
        document = f"{ISSUERS[symbol]}-{period}"
        _file(front, database, symbol, document, _accepted(filed, at), facts, form="10-K" if period in financials["Income_Statement"]["yearly"] else "10-Q")
        documents.append(document)
    return documents


def _compute(database: Database, at: datetime = T, statements: str = "auto") -> pit.PitComputation:
    service = _service(database)
    return service.compute("NASDAQ", as_of=at, prices=service.pin_vintage("NASDAQ", as_of=at, pinned_at=NOW), statements=statements)


def _as_filed(front: Any, database: Database, symbol: str, *, as_of: datetime, market: str = "NASDAQ") -> tuple[dict[str, Any], dict[str, Any]]:
    """The reconstruction of one covered name at ``as_of`` from the REAL store: (pit_fundamentals, the reference + the payload)."""
    reader = pit.AsFiledReader(database)
    assert reader.present() and symbol in reader.coverage(market)
    payload, reference = pit.as_filed_payload(reader.facts(ISSUERS[symbol], as_of=as_of, refused=Counter()), market=market, front=reader.front)
    return pit.pit_fundamentals(payload, market=market, economic_date=pit.economic_date_of(market, as_of)), {**reference, "payload": payload}


def test_without_the_front_the_run_is_the_provider_run_and_a_table_without_its_reader_is_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the as-filed front in the tree (this branch alone): no table → the provider run to the byte; a table → refused, never guessed."""
    monkeypatch.setattr(pit, "AS_FILED_FRONT", {"no_such_as_filed_store": ("StatementVintageStore",)})
    assert pit.as_filed_front() == (None, "app.no_such_as_filed_store is not in this tree")
    database = _ready()
    assert not hasattr(database, "_statement_vintages")  # no migration 051 here: no table
    auto, provider = _compute(database), _compute(database, statements="provider")
    assert auto.run_key == provider.run_key and auto.results == provider.results and auto.manifest == provider.manifest  # a no-op, to the byte
    assert auto.summary()["statements"] == {"mode": "auto", "table_present": False, "basis": {"provider_payload": 6}, "coverage": None}
    assert provider.summary()["statements"] == {"mode": "provider", "table_present": None, "basis": {"provider_payload": 6}, "coverage": None}  # never asked
    with pytest.raises(pit.PitRerunInputError, match="statement_vintages does not exist"):
        _compute(database, statements="vintages")
    setattr(database, "_statement_vintages", [])  # the table without its reader
    with pytest.raises(pit.PitRerunInputError, match=r"reader is not complete in this tree \(app.no_such_as_filed_store is not in this tree\)"):
        _compute(database)
    monkeypatch.setattr(pit, "AS_FILED_FRONT", {"valuation_pit_rerun": ("no_such_reader_piece",)})  # a module that drifted: named, never half-used
    with pytest.raises(pit.PitRerunInputError, match=r"app.valuation_pit_rerun lacks no_such_reader_piece"):
        _compute(database)
    assert _compute(database, statements="provider").run_key == provider.run_key  # the default never asks


def test_with_the_front_an_empty_table_is_still_the_provider_run_and_the_default_never_reads_it(front: Any) -> None:
    database = _ready()
    provider, absent = _compute(database, statements="provider"), _compute(database)
    assert absent.run_key == provider.run_key and absent.summary()["statements"]["table_present"] is False  # the front in the tree, no table: no-op
    front.statement_vintages.StatementVintageStore(database)  # the tables exist (the writer created them) and cover nobody
    empty = _compute(database)
    assert empty.run_key == provider.run_key and empty.manifest == provider.manifest and empty.summary()["statements"]["table_present"] is True
    assert empty.summary()["statements"]["coverage"] == {"covered": 0, "covered_in_catalogue": 0, "covered_without_rows_by_T": 0}
    _file_payload(front, database, "AAA", _payload("AAA"))  # a table that covers a name: read only when asked
    service = _service(database)
    default = service.compute("NASDAQ", as_of=T, prices=service.pin_vintage("NASDAQ", as_of=T, pinned_at=NOW))
    assert pit.STATEMENTS_DEFAULT == "provider" and default.summary()["statements"] == {"mode": "provider", "table_present": None,
                                                                                        "basis": {"provider_payload": 6}, "coverage": None}
    assert default.run_key == provider.run_key != _compute(database).run_key
    receipt, _run = service.rerun("NASDAQ", as_of=T, clock=lambda: NOW)
    assert receipt["statements"]["mode"] == "provider" and receipt["run_key"] == default.run_key


def test_as_filed_facts_rebuild_a_covered_name_with_the_providers_numbers_and_the_regulators_instant(front: Any) -> None:
    database = _ready()
    consistent = _consistent_payload("AAA")
    _republish_payload(database, "AAA", consistent)  # the provider's statements of AAA = what its filer filed (same numbers, same days)
    _file_payload(front, database, "AAA", consistent)
    provider, auto = _compute(database, statements="provider"), _compute(database)
    assert auto.results == provider.results and auto.run_key != provider.run_key  # same filings, same numbers — but another input, another run
    assert auto.resolver.per_symbol["AAA"]["statements_basis"] == "statement_vintages" and auto.resolver.per_symbol["BBB"]["statements_basis"] == "provider_payload"
    assert auto.summary()["statements"] == {"mode": "auto", "table_present": True, "basis": {"provider_payload": 5, "statement_vintages": 1},
                                            "coverage": {"covered": 1, "covered_in_catalogue": 1, "covered_without_rows_by_T": 0}}
    assert auto.provenance_for("AAA")["statements_basis"] == "statement_vintages" and auto.provenance_for("AAA")["availability_hypotheses"] == []
    aaa_refs = [ref for ref in auto.manifest["sources"] if ref.get("symbol_sha256") == pit.symbol_hash("AAA")]
    assert [ref["role"] for ref in aaa_refs] == ["statement_vintages"]  # the provider payload is never read for a covered name with its own share count
    assert aaa_refs[0]["facts"] == len(database._statement_vintages) == 4 * 11 + 7 * 11 + 2 * 17  # type: ignore[attr-defined]  # 13 documents, two annual
    assert aaa_refs[0]["facts_superseded_by_T"] == 0 and aaa_refs[0]["quarters_derived"] == 0  # reports with the Q4 and the year
    assert "issuer_key" not in json.dumps(aaa_refs) and ISSUERS["AAA"] not in json.dumps(aaa_refs)  # the manifest stays non-nominal
    fundamentals = auto.resolver.per_symbol["AAA"]["fundamentals"]
    assert fundamentals["eligible_periods"] == {"Income_Statement": {"quarterly": 9, "yearly": 6}, "Cash_Flow": {"quarterly": 9, "yearly": 6},
                                                "Balance_Sheet": {"quarterly": 13, "yearly": 6}}  # a balance at every reported date; fiscal years at their ends
    assert fundamentals["shares_availability"]["rule"] == "regulator_accepted_at" and fundamentals["shares_availability"]["documents"] == [f"{ISSUERS['AAA']}-2024-03-31"]
    # the instant, not the day: T at the close of 2024-05-15 (16:00 New York) precedes the 16:30 acceptance of 2024Q1 — the provider's
    # filing DATE 2024-05-15 lets the quarter in, the regulator's acceptance does not
    close_of_filing_day = datetime(2024, 5, 15, 16, 0, tzinfo=NEW_YORK)
    day, instant = _compute(database, close_of_filing_day, "provider"), _compute(database, close_of_filing_day)
    assert day.resolver.per_symbol["AAA"]["fundamentals"]["fundamentals_as_of"] == "2024-03-31"
    assert instant.resolver.per_symbol["AAA"]["fundamentals"]["fundamentals_as_of"] == "2023-12-31"
    assert instant.resolver.per_symbol["BBB"]["fundamentals"]["fundamentals_as_of"] == "2024-03-31"  # an uncovered name keeps the provider's day rule


def test_a_restatement_accepted_by_t_replaces_the_fact_one_after_t_is_never_read_and_the_bridge_agrees(front: Any) -> None:
    database = _ready()
    _file_payload(front, database, "AAA", _consistent_payload("AAA"))
    base = _compute(database)
    q3_start, q3_end = date(2023, 7, 1), date(2023, 9, 30)
    original = next(row for row in database._statement_vintages if row["concept"] == REVENUE and row["period_end"] == q3_end  # type: ignore[attr-defined]
                    and row["period_start"] == q3_start)
    _file(front, database, "AAA", "restated-after-T", _accepted("2024-07-01", wall_time(9, 0)), [(REVENUE, 1e15, q3_end, q3_start)], form="10-Q/A")
    assert _compute(database).run_key == base.run_key  # accepted after T: it does not exist at T — the same run, to the byte
    _file(front, database, "AAA", "amended-by-T", _accepted("2024-06-03", wall_time(9, 0)), [(REVENUE, float(original["value"]) * 1.5, q3_end, q3_start)],
          form="10-Q/A")
    amended = _compute(database)
    assert amended.run_key != base.run_key  # an acceptance by T backfilled later IS new content: another run
    reference = next(ref for ref in amended.manifest["sources"] if ref["role"] == "statement_vintages")
    assert reference["facts_superseded_by_T"] == 1 and amended.resolver.excluded["statement_vintages:facts_superseded_by_a_later_report_by_T"] == 1
    fundamentals, detail = _as_filed(front, database, "AAA", as_of=T)
    quarters = detail["payload"]["Financials"]["Income_Statement"]["quarterly"]
    last_four = ("2023-06-30", "2023-09-30", "2023-12-31", "2024-03-31")
    assert fundamentals["ttm"]["basis"] == "four_quarters" and fundamentals["ttm"]["revenue"] == pytest.approx(sum(quarters[end]["totalRevenue"] for end in last_four))
    assert quarters["2023-09-30"]["totalRevenue"] == float(original["value"]) * 1.5  # the amendment known at T; the restatement after it never read
    assert quarters["2023-09-30"][pit.AS_FILED_AVAILABILITY]["documents"] == [f"{ISSUERS['AAA']}-2023-09-30", "amended-by-T"]
    assert quarters["2023-09-30"]["filing_date"] == "2024-06-03"  # available once every fact of the row was: the amendment's day
    bridge = front.valuation_asfiled.as_of_fundamentals(database, ISSUERS["AAA"], T)  # the front's own as-of inputs at the same T
    assert bridge["period_end"] == "2024-03-31" and fundamentals["ttm"]["revenue"] == pytest.approx(bridge["ttm"]["revenue"])
    assert fundamentals["ttm"]["net_income"] == pytest.approx(bridge["ttm"]["net_income"])
    assert fundamentals["cash_flow_ttm"]["operating_cash_flow"] == pytest.approx(bridge["ttm"]["operating_cash_flow"])
    assert fundamentals["balance"]["cash"] == bridge["balance"]["cash"] and fundamentals["balance"]["debt"] == pytest.approx(bridge["derived"]["total_debt"])
    assert amended.resolver.per_symbol["AAA"]["chewie"] != base.resolver.per_symbol["AAA"]["chewie"]  # the amended revenue reaches the trailing growth


def test_coverage_decides_the_basis_never_t_and_strict_mode_reads_covered_names_only(front: Any) -> None:
    database = _ready()
    _file_payload(front, database, "AAA", _consistent_payload("AAA"))
    strict = _compute(database, statements="vintages")
    assert strict.resolver.not_evaluable == {s: "statement_vintages_missing" for s in SYMBOLS if s != "AAA"} and set(strict.results) == {"AAA"}
    # a covered name whose every acceptance is after T is not evaluable — never the provider's statements — and says so by name (a shallow
    # backfill shrinks the grid visibly), with the coverage depth in the summary
    late = _database()
    _publish_prices(late)
    _publish_sources(late)
    _file_payload(front, late, "AAA", _consistent_payload("AAA"))
    for row in late._statement_vintages:  # type: ignore[attr-defined]
        row["accepted_at"] = _accepted("2025-01-06")
    computation = _compute(late)
    assert computation.resolver.not_evaluable == {"AAA": "statement_vintages_none_accepted_by_T"}
    assert computation.summary()["statements"]["basis"] == {"provider_payload": 5, "statement_vintages": 1}
    assert computation.summary()["statements"]["coverage"] == {"covered": 1, "covered_in_catalogue": 1, "covered_without_rows_by_T": 1}


def test_year_to_date_facts_become_discrete_quarters_the_q4_is_the_year_minus_nine_months_and_no_gap_is_bridged(front: Any) -> None:
    """A real filer's 10-Qs: the cash flow is year-to-date only and no Q4 report exists. Q2/Q3/Q4 come from the front's
    discrete quarters (6M − 3M, 9M − 6M, FY − 9M), a reported three-month figure wins over a year-to-date one, the TTM needs
    four CONSECUTIVE quarters and the latest balance is the fiscal-year end's between the annual report and the next 10-Q."""
    database = _database()

    def quarter(doc: str, day: str, end: date, revenue: float, ytd_revenue: float | None, ytd_cash: float, equity: float) -> None:
        start = date(end.year, 1, 1)
        facts: list[Fact] = [(OPERATING_CASH, ytd_cash, end, start), (EQUITY, equity, end, None), (SHARES, 1_000.0, end + timedelta(days=20), None)]
        if revenue:
            facts.append((REVENUE, revenue, end, _quarter_start(end)))
        if ytd_revenue is not None:
            facts.append((REVENUE, ytd_revenue, end, start))
        _file(front, database, "AAA", doc, _accepted(day), facts, form="10-K" if end.month == 12 else "10-Q")

    quarter("q1-25", "2025-05-01", date(2025, 3, 31), 10, None, 5, 6.0)
    quarter("q2-25", "2025-08-01", date(2025, 6, 30), 20, 30, 12, 6.5)  # the 6-month column under the same period end: never summed as a quarter
    quarter("q3-25", "2025-11-01", date(2025, 9, 30), 30, 60, 21, 7.0)
    quarter("fy-25", "2026-02-20", date(2025, 12, 31), 0, 100, 32, 8.0)  # the annual report: no Q4 figure, only the year
    quarter("q1-26", "2026-05-01", date(2026, 3, 31), 15, None, 6, 9.0)
    quarter("q2-26", "2026-08-01", date(2026, 6, 30), 25, 40, 14, 10.0)
    late, detail = _as_filed(front, database, "AAA", as_of=datetime(2026, 8, 31, 18, 0, tzinfo=NEW_YORK))
    assert late["ttm"]["basis"] == "four_quarters" and late["ttm"]["revenue"] == pytest.approx(30 + 40 + 15 + 25)  # Q3'25 + (100 − 60) + Q1'26 + Q2'26
    assert late["cash_flow_ttm"]["operating_cash_flow"] == pytest.approx((21 - 12) + (32 - 21) + 6 + (14 - 6))
    assert detail["quarters_derived"] == 1 + 4  # revenue: the Q4; operating cash: Q2'25, Q3'25, Q4'25, Q2'26
    q4 = detail["payload"]["Financials"]["Income_Statement"]["quarterly"]["2025-12-31"]
    assert q4[pit.AS_FILED_AVAILABILITY]["derived"] == "year_to_date_difference" and q4[pit.AS_FILED_AVAILABILITY]["documents"] == ["fy-25", "q3-25"]
    assert q4[pit.AS_FILED_AVAILABILITY]["available_at"] == _accepted("2026-02-20").astimezone(UTC).isoformat()  # the latest of the two acceptances
    between, _detail = _as_filed(front, database, "AAA", as_of=datetime(2026, 3, 15, 18, 0, tzinfo=NEW_YORK))
    assert between["ttm"]["basis"] == "four_quarters" and between["ttm"]["revenue"] == pytest.approx(100)  # Q1–Q3 + the derived Q4: the year
    assert between["balance"]["period_end"] == "2025-12-31" and between["balance"]["equity"] == 8.0 and between["shares"] == 1_000.0
    before, _detail = _as_filed(front, database, "AAA", as_of=datetime(2026, 2, 19, 18, 0, tzinfo=NEW_YORK))  # before the annual report: three quarters
    assert before["ttm"]["basis"] is None and before["balance"]["period_end"] == "2025-09-30"  # are not a year — no TTM, no hole bridged
    # without the year's revenue no Q4 exists: four quarters around the hole (Q2'25, Q3'25, Q1'26, Q2'26) are never a TTM, counted
    database._statement_vintages[:] = [row for row in database._statement_vintages  # type: ignore[attr-defined]
                                       if not (row["doc_id"] == "fy-25" and row["concept"] == REVENUE)]
    holed, _detail = _as_filed(front, database, "AAA", as_of=datetime(2026, 8, 31, 18, 0, tzinfo=NEW_YORK))
    assert holed["ttm"]["basis"] is None and holed["excluded"]["Income_Statement.quarterly:ttm_quarters_not_consecutive"] == 1


def test_as_filed_date_checks_hold_and_the_filing_date_is_the_acceptance_day_in_the_market_zone(front: Any) -> None:
    database = _database()
    # an acceptance at 23:00 New York is 03:00Z the NEXT day: at T = 23:30 New York the same day it is available, dated by the market's day
    _file(front, database, "AAA", "late-evening", _accepted("2024-05-15", wall_time(23, 0)), [(REVENUE, 10.0, date(2024, 3, 31), date(2024, 1, 1))])
    seen, detail = _as_filed(front, database, "AAA", as_of=datetime(2024, 5, 15, 23, 30, tzinfo=NEW_YORK))
    assert detail["payload"]["Financials"]["Income_Statement"]["quarterly"]["2024-03-31"]["filing_date"] == "2024-05-15"
    assert seen["fundamentals_as_of"] == "2024-03-31" and not [key for key in seen["excluded"] if key.startswith("Income_Statement")]
    unseen, _detail = _as_filed(front, database, "AAA", as_of=datetime(2024, 5, 15, 22, 59, tzinfo=NEW_YORK))  # a minute before: the store's cut
    assert unseen["fundamentals_as_of"] is None
    # a balance dated AFTER the acceptance that reports it cannot have been filed: refused and counted, never the newest balance
    _file(front, database, "AAA", "impossible", _accepted("2024-05-20"), [(EQUITY, 1e15, date(2024, 6, 30), None), (EQUITY, 5.0, date(2024, 3, 31), None)])
    checked, _detail = _as_filed(front, database, "AAA", as_of=datetime(2024, 7, 15, 18, 0, tzinfo=NEW_YORK))
    assert checked["excluded"]["Balance_Sheet.quarterly:filing_before_period_end"] == 1 and checked["balance"] == {
        "equity": 5.0, "debt": None, "cash": None, "shares": None, "net_debt": 0.0, "period_end": "2024-03-31"}
    # the same rule for an as-filed row of any market: the regulator's acceptance is evidence there too (B3 rows have no reader yet)
    sao_paulo = ZoneInfo("America/Sao_Paulo")
    def b3_row(end: date, accepted: datetime, revenue: float) -> dict[str, Any]:
        row = pit._as_filed_entry(end, {"totalRevenue": revenue, "netIncome": revenue / 10}, [{"doc_id": f"cvm-{end}", "accepted_at": accepted}], market="B3")
        assert row is not None
        return row
    early, sound = b3_row(date(2024, 3, 31), datetime(2024, 3, 20, 19, 0, tzinfo=sao_paulo), 1e15), b3_row(date(2023, 12, 31), datetime(2024, 2, 9, 19, 0, tzinfo=sao_paulo), 10.0)
    b3 = pit.pit_fundamentals({"Financials": {"Income_Statement": {"quarterly": {"2024-03-31": early, "2023-12-31": sound}}}}, market="B3", economic_date=date(2024, 6, 14))
    assert b3["fundamentals_as_of"] == "2023-12-31" and b3["hypotheses"] == []  # evidence, not the +90 d hypothesis of the provider's B3 payload
    assert {key: count for key, count in b3["excluded"].items() if key.startswith("Income_Statement")} == {"Income_Statement.quarterly:filing_before_period_end": 1}


def test_a_store_that_returns_a_fact_after_t_or_without_a_zone_never_reaches_the_reconstruction(front: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    database = _ready()
    _file_payload(front, database, "AAA", _consistent_payload("AAA"))
    honest = _compute(database)
    _file(front, database, "AAA", "after-T", _accepted("2024-07-01"), [(REVENUE, 1e15, date(2024, 3, 31), date(2024, 1, 1))], form="10-Q/A")
    store = front.statement_vintages.StatementVintageStore
    read = store.vintages

    def uncut(self: Any, market: str, issuer_key: str, *, accepted_at_or_before: Any = None, concepts: Any = None, source: Any = None) -> list[dict[str, Any]]:
        rows = read(self, market, issuer_key, concepts=concepts, source=source)  # the cut forgotten: every acceptance
        return rows + [{**rows[0], "doc_id": "naive", "accepted_at": rows[0]["accepted_at"].replace(tzinfo=None)}]

    monkeypatch.setattr(store, "vintages", uncut)
    leaky = _compute(database)
    assert leaky.results == honest.results and leaky.run_key == honest.run_key  # dropped before the reconstruction: the same run
    assert leaky.resolver.excluded["statement_vintages:fact_after_T_returned_by_the_store"] == 1
    assert leaky.resolver.excluded["statement_vintages:fact_without_a_zoned_acceptance"] == 1


def test_the_table_covering_none_of_the_catalogue_is_a_refusal_but_names_of_the_sibling_exchange_are_not(front: Any) -> None:
    database = _ready()
    _file(front, database, "AAA", "suffixed", _accepted("2024-05-15"), [(REVENUE, 10.0, date(2024, 3, 31), date(2024, 1, 1))])
    database._statement_filings[0]["symbols"] = ["AAA.US"]  # type: ignore[attr-defined]  # a provider suffix the catalogue lacks
    with pytest.raises(pit.PitRerunInputError, match=r"covers 1 name\(s\) and none of the NASDAQ catalogue's 6"):
        _compute(database)
    with pytest.raises(pit.PitRerunInputError, match="none of the NASDAQ catalogue's"):
        _compute(database, statements="vintages")
    assert _compute(database, statements="provider").summary()["statements"]["basis"] == {"provider_payload": 6}
    # an SEC issuer is stored under "US": a name of the NYSE catalogue covered while this NASDAQ run covers none is no format drift
    database._statement_filings[0]["symbols"] = ["ZZZ"]  # type: ignore[attr-defined]
    database.save_analysis_snapshot("valuation_universe", "NYSE_UNIVERSE", "mv-cat", {}, {"rows": [{"symbol": "ZZZ", "sector": SECTOR}]}, VINTAGE_AT)
    sibling = _compute(database)
    assert sibling.run_key == _compute(database, statements="provider").run_key  # no NASDAQ name covered: the provider run
    assert sibling.summary()["statements"]["coverage"] == {"covered": 1, "covered_in_catalogue": 0, "covered_without_rows_by_T": 0}


def test_b3_facts_have_no_reader_yet_and_are_a_refusal_never_read_through_the_sec_ladder(front: Any) -> None:
    database = _database()
    reader = pit.AsFiledReader(database)
    store = front.statement_vintages.StatementVintageStore(database)
    assert reader.present() and reader.coverage("B3") == {} and reader.coverage("NASDAQ") == {}
    store.insert_vintages("B3", "00000000000100", [{"market": "B3", "issuer_key": "00000000000100", "source": "cvm_dados_abertos", "doc_id": "1", "form": "ITR",
                                                    "period_start": date(2024, 1, 1), "period_end": date(2024, 3, 31), "concept": "cvm:dre_con:3.01:Receita",
                                                    "unit": "BRL", "value": 10, "filed_date": date(2024, 5, 10),
                                                    "accepted_at": datetime(2024, 5, 10, 23, 59, 59, tzinfo=ZoneInfo("America/Sao_Paulo"))}])
    with pytest.raises(pit.PitRerunInputError, match=r"holds B3 \(CVM\) facts and no reader maps CVM accounts"):
        reader.coverage("B3")
    assert reader.coverage("NASDAQ") == {}  # the SEC side is untouched


def test_a_balance_dates_share_count_is_the_cover_page_of_its_own_document_never_a_later_comparatives_day(front: Any) -> None:
    """As filed, the latest acceptance by T picks the next annual report's COMPARATIVE of an older balance: its equity is in
    dollars, but the share count of that date is the cover page of the year's own report — in the unit of the day IT was
    reported. A 10-K/A filed after a split with a post-split count is that count's report day."""
    database = _database()
    _publish_prices(database, bars=_split_bars("2024-02-01", start=date(2022, 6, 1)), start=date(2022, 6, 1))
    _publish_sources(database)
    consistent = _consistent_payload("AAA")
    _republish_payload(database, "AAA", consistent)
    _file_payload(front, database, "AAA", consistent)  # FY2022 10-K accepted 2023-02-14 (pre-split count); FY2023 10-K 2024-02-14 (after the split)
    fy2022 = consistent["Financials"]["Balance_Sheet"]["yearly"]["2022-12-31"]
    _file(front, database, "AAA", f"{ISSUERS['AAA']}-2023-12-31", _accepted("2024-02-14"), [(EQUITY, fy2022["totalStockholderEquity"], date(2022, 12, 31), None)],
          form="10-K")  # the comparative of the FY2022 balance in the FY2023 annual report, accepted after the split
    original = _compute(database, statements="vintages")
    ratios = {r["fiscal_year_end"] for r in original.resolver.per_symbol["AAA"]["ratios_annual"]}
    assert "2022-12-31" in ratios and "2023-12-31" not in ratios  # FY2022: its own count, reported 2023-02-14; FY2023's count reported after the split
    _file(front, database, "AAA", "fy-22-amended", _accepted("2024-03-01"), [(EQUITY, fy2022["totalStockholderEquity"], date(2022, 12, 31), None),
                                                                          (SHARES, 10_000_000.0, date(2024, 2, 20), None)], form="10-K/A")
    amended = _compute(database, statements="vintages")
    assert "2022-12-31" not in {r["fiscal_year_end"] for r in amended.resolver.per_symbol["AAA"]["ratios_annual"]}  # a post-split count of FY2022
    assert amended.resolver.excluded["fiscal_year:capital_event_between_price_and_shares_report"] == original.resolver.excluded[
        "fiscal_year:capital_event_between_price_and_shares_report"] + 1


def test_four_provider_quarters_around_a_gap_are_never_a_ttm_and_the_growth_prior_is_the_year_right_before() -> None:
    """As filed there is no Q4 report: four quarters around the hole once passed for a year (80 for a true 100). In a provider-shaped
    payload the TTM needs consecutive quarters too, and the prior period of the growth is the year RIGHT BEFORE the TTM."""
    # the same hole in a provider-shaped payload (no Q4 row): never four_quarters (once 20 + 30 + 15 + 25 = 90), the fiscal year instead, counted
    def provider_row(end: str, revenue: float, filed: str) -> dict[str, Any]:
        return {"date": end, "filing_date": filed, "totalRevenue": revenue, "netIncome": revenue / 10}
    holed = {"Financials": {"Income_Statement": {
        "quarterly": {"2025-03-31": provider_row("2025-03-31", 10, "2025-05-01"), "2025-06-30": provider_row("2025-06-30", 20, "2025-08-01"),
                      "2025-09-30": provider_row("2025-09-30", 30, "2025-11-01"), "2026-03-31": provider_row("2026-03-31", 15, "2026-05-01"),
                      "2026-06-30": provider_row("2026-06-30", 25, "2026-08-01")},
        "yearly": {"2025-12-31": provider_row("2025-12-31", 100, "2026-02-20")}}}}
    provider = pit.pit_fundamentals(holed, market="NASDAQ", economic_date=date(2026, 8, 31))
    assert provider["ttm"]["basis"] == "latest_fiscal_year" and provider["ttm"]["revenue"] == 100
    assert provider["excluded"]["Income_Statement.quarterly:ttm_quarters_not_consecutive"] == 1
    # the prior period of the growth is the year RIGHT BEFORE the TTM: eight consecutive quarters, else never four_quarters
    nine = pit.pit_fundamentals(_payload("AAA"), market="NASDAQ", economic_date=date(2024, 6, 14))
    assert nine["ttm"]["basis"] == "four_quarters" and nine["revenue_growth"] is not None
    gapped = _payload("AAA")
    del gapped["Financials"]["Income_Statement"]["quarterly"]["2023-03-31"]  # 2022Q1–Q4 stay consecutive, but a year before 2023Q2, not right before it
    growth = pit.pit_fundamentals(gapped, market="NASDAQ", economic_date=date(2024, 6, 14))
    fy2022 = gapped["Financials"]["Income_Statement"]["yearly"]["2022-12-31"]["totalRevenue"]
    assert growth["ttm"] == nine["ttm"] and growth["revenue_growth"] == pytest.approx(growth["ttm"]["revenue"] / fy2022 - 1)  # previous_fiscal_year, no bridge


def _split_bars(split_on: str, *, start: date = date(2023, 6, 1)) -> dict[str, list[dict]]:
    """Clean bars from ``start`` with AAA's as-traded close × 10 before ``split_on`` (a 10:1 split; the adjusted series continuous)."""
    sessions = _sessions(start.isoformat(), "2026-09-10")
    bars = {f"{symbol}.US": _bars_for(symbol, sessions, base=100.0 + 10 * i) for i, symbol in enumerate(SYMBOLS)}
    bars["AAA.US"] = [{**bar, "close": round(bar["close"] * 10, 4)} if bar["date"] < split_on else bar for bar in bars["AAA.US"]]
    return bars


def _republish_payload(database: Database, symbol: str, payload: dict[str, Any]) -> None:
    database.save_analysis_snapshot(pit.SOURCE_ANALYSIS_TYPE, pit.source_entity_key("NASDAQ", pit.PROVIDER_EODHD, symbol), "mv-src",
                                    {"symbol": symbol, "fetched_at": VINTAGE_AT.isoformat(), "payload_sha256": official.canonical_sha256(payload)},
                                    {"payload": payload, "payload_sha256": official.canonical_sha256(payload)}, VINTAGE_AT + timedelta(minutes=1))


def test_a_fiscal_year_never_pairs_its_price_with_a_share_count_of_another_unit() -> None:
    """The reviewer's repro: a 10:1 split on 2024-02-01, the Q1'24 balance post-split (10 M). Once, a fiscal-year balance
    without a count borrowed the CURRENT one and FY2023 came out 10× (P/E 4244 for 424), unrefused."""
    def run(fiscal_shares: bool, *, split_on: str = "2024-02-01") -> pit.PitComputation:
        database = _database()
        _publish_prices(database, bars=_split_bars(split_on))
        _publish_sources(database)
        payload = _payload("AAA")
        payload["Financials"]["Balance_Sheet"]["quarterly"]["2024-03-31"]["commonStockSharesOutstanding"] = 10_000_000.0
        for row in payload["Financials"]["Balance_Sheet"]["yearly"].values():
            if not fiscal_shares:
                row.pop("commonStockSharesOutstanding")
        payload["outstandingShares"] = {"annual": {}, "quarterly": {}}
        _republish_payload(database, "AAA", payload)
        return _compute(database, statements="provider")
    borrowed, reported = run(False), run(True)
    for computation in (borrowed, reported):  # the split precedes the current count's period end: the name is evaluated at T
        assert "AAA" in computation.resolver.per_symbol and "2023-12-31" not in {r["fiscal_year_end"] for r in computation.resolver.per_symbol["AAA"]["ratios_annual"]}
    assert borrowed.resolver.excluded["fiscal_year:no_price_or_shares"] >= 1  # no count of its own: dropped, never the current one
    # FY2023's count was reported on 2024-02-14 (filed 45 d after the year end), AFTER the split of 2024-02-01: the year's close (2023-12-29,
    # pre-split) and its count may be in two units — dropped, counted (conservative: a filer usually restates a count for a split before issuance)
    assert reported.resolver.excluded["fiscal_year:capital_event_between_price_and_shares_report"] == 1
    # a split AFTER the report (2024-02-20) and before the current period end: FY2023 keeps its own, as-reported count and its traded close
    kept = run(True, split_on="2024-02-20")
    fy2023 = next(r for r in kept.resolver.per_symbol["AAA"]["key_metrics_annual"] if r["fiscal_year_end"] == "2023-12-31")
    close, _session = kept.resolver.prices.price_at("AAA", on=date(2023, 12, 31))
    assert fy2023["market_cap"] == pytest.approx(close * 1_000_000.0) and kept.resolver.excluded["fiscal_year:capital_event_between_price_and_shares_report"] == 0


def test_an_invalid_bar_on_the_event_session_never_hides_the_capital_event() -> None:
    bars = _split_bars("2024-05-01")  # after the shares' period end (2024-03-31) and before T: the name is refused
    bars["AAA.US"] = [{**bar, "close": 0.0} if bar["date"] == "2024-05-01" else bar for bar in bars["AAA.US"]]  # the event's own bar is invalid
    run = _compute_with_bars(bars)  # the series refuses the row (a close non-positive): no bar that session, the next one carries the event
    assert "2024-05-01" not in run.resolver.prices.bars("AAA") and run.resolver.prices.capital_events("AAA") == ["2024-05-02"]
    assert run.resolver.not_evaluable == {"AAA": "capital_event_between_shares_and_T"}
    assert run.resolver.price_basis_evidence == {"symbols_read": 6, "capital_event_sessions": 1, "symbols_with_capital_events": 1}
    # a STORED invalid bar (the producer would refuse it; the reader keeps it out of valid_sessions all the same) never splits the comparison
    database = _database()
    _publish_prices(database, bars=_split_bars("2024-05-01"))
    prices = _service(database).pin_vintage("NASDAQ", as_of=T, pinned_at=NOW)
    stored = prices.bars("AAA")
    for field in ("close", "adjusted_close"):
        prices._bars["AAA"] = {**stored, "2024-05-01": {**stored["2024-05-01"], field: 0.0}}
        prices._capital_events.pop("AAA", None)
        assert prices.capital_events("AAA") == ["2024-05-02"], field  # the last valid bar (04-30) against the next valid one (05-02)
    prices._bars["AAA"], _ = stored, prices._capital_events.pop("AAA")
    assert prices.capital_events("AAA") == ["2024-05-01"]


class _FakeResult:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.rows = rows

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self.rows)


class _FakeConnection:
    """Answers the store's SQL by a substring; records every statement with its parameters (no PostgreSQL in the suite)."""

    def __init__(self, answers: dict[str, list[tuple[Any, ...]]]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, Any]] = []

    def execute(self, sql: str, params: Any = None) -> _FakeResult:
        self.calls.append((" ".join(sql.split()), params))
        for key, rows in self.answers.items():
            if key in sql:
                return _FakeResult(rows)
        raise AssertionError(f"unexpected SQL: {sql}")


def _postgres_double(answers: dict[str, list[tuple[Any, ...]]]) -> tuple[Database, _FakeConnection]:
    database = _database()
    database.database_url = "postgresql://never-connected"
    fake = _FakeConnection(answers)

    @contextmanager
    def connection() -> Iterator[_FakeConnection]:
        yield fake

    setattr(database, "connection", connection)
    return database, fake


def test_the_postgresql_reader_checks_both_tables_and_the_store_cuts_at_t_in_its_own_query(front: Any) -> None:
    absent, fake = _postgres_double({"to_regclass": [(None,)]})
    assert pit.AsFiledReader(absent).present() is False and fake.calls == [("SELECT to_regclass(%s)::text", ("statement_vintages",))]
    columns = [(column, "timestamp with time zone" if column == "accepted_at" else "text")
               for column in sorted({column for required in pit.AS_FILED_COLUMNS.values() for column in required})]
    drifted, _ = _postgres_double({"to_regclass": [("statement_vintages",)], "information_schema": [c for c in columns if c[0] not in ("concept", "symbols")]})
    with pytest.raises(pit.PitRerunInputError, match=r"statement_vintages lacks the columns the as-filed reader relies on \['concept'\]"):
        pit.AsFiledReader(drifted).present()
    wall_clock, _ = _postgres_double({"to_regclass": [("statement_vintages",)],
                                      "information_schema": [(c, "timestamp without time zone" if c == "accepted_at" else t) for c, t in columns]})
    with pytest.raises(pit.PitRerunInputError, match="not a timestamp with time zone"):
        pit.AsFiledReader(wall_clock).present()
    accepted = datetime(2024, 5, 1, 20, 30, tzinfo=UTC)
    fact = ("7", "US", ISSUERS["AAA"], "sec_xbrl_companyfacts", "0000000100-24-000001", 1, "10-Q", 2024, "Q1", date(2024, 1, 1), date(2024, 3, 31),
            REVENUE, "USD", Decimal("10"), date(2024, 5, 1), accepted, accepted, True, "0" * 64)  # the store's column order
    ready, fake = _postgres_double({"to_regclass": [("statement_vintages",)], "information_schema": columns,
                                    "DISTINCT ON (symbol)": [("aaa ", ISSUERS["AAA"]), ("BBB", "0000009999")], "DISTINCT issuer_key": [(ISSUERS["AAA"],)],
                                    "accepted_at <= %s": [fact]})
    reader = pit.AsFiledReader(ready)
    assert reader.present() is True and reader.coverage("NYSE") == {"AAA": ISSUERS["AAA"]}  # BBB's issuer has no fact: not covered
    facts = reader.facts(ISSUERS["AAA"], as_of=T.astimezone(NEW_YORK), refused=Counter())
    assert [(row["concept"], row["value"], row["accepted_at"]) for row in facts] == [(REVENUE, Decimal("10"), accepted)]
    sql, params = fake.calls[-1]
    assert "FROM statement_vintages" in sql and "accepted_at <= %s" in sql and params == ["US", ISSUERS["AAA"], T, "sec_xbrl_companyfacts"]
    assert params[2].utcoffset() == timedelta(0)  # the cut at T, in UTC, inside the store's own query


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
