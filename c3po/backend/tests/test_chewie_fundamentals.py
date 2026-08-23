from datetime import datetime, timezone
from pathlib import Path

from app.chewie_fundamentals import ChewieFundamentalsService
from app.config import get_settings
from app.database import Database


class StubHttp:
    def __init__(self, results: dict[str, dict | list]) -> None:
        self.results = results
        self.calls: list[str] = []

    def get_json(self, url, *, params=None, headers=None):
        self.calls.append(url)
        for fragment, payload in self.results.items():
            if fragment in url:
                return payload
        return {}


def _eodhd_payload(symbol: str = "AAPL", name: str = "Apple", **overrides) -> dict:
    base = {
        "General": {
            "Code": symbol,
            "Name": name,
            "Sector": "Technology",
            "Industry": "Consumer Electronics",
            "LogoURL": "/img.png",
            "Description": "Consumer electronics company.",
        },
        "Highlights": {
            "MarketCapitalization": 3_000_000_000_000,
            "PERatio": 30.0,
            "ReturnOnEquityTTM": 1.50,
            "ReturnOnAssetsTTM": 0.28,
            "ProfitMargin": 0.25,
            "OperatingMarginTTM": 0.30,
            "QuarterlyRevenueGrowthYOY": 0.05,
            "QuarterlyEarningsGrowthYOY": 0.10,
            "EBITDA": 130_000_000_000,
            "RevenueTTM": 390_000_000_000,
            "DividendYield": 0.005,
            "DilutedEpsTTM": 6.1,
            "WallStreetTargetPrice": 240.0,
        },
        "Valuation": {"TrailingPE": 30.0, "ForwardPE": 27.0, "EnterpriseValueEbitda": 22.0, "PriceBookMRQ": 45.0},
        "SharesStats": {},
        "Technicals": {"52WeekHigh": 250.0, "52WeekLow": 160.0, "50DayMA": 220.0, "200DayMA": 200.0},
        "AnalystRatings": {"Rating": 4.1, "StrongBuy": 6, "Buy": 4, "Hold": 3, "Sell": 1, "StrongSell": 0},
        "Earnings": {"Trend": {}},
        "Financials": {
            "Balance_Sheet": {"quarterly": {}, "yearly": {}},
            "Cash_Flow": {"quarterly": {}, "yearly": {}},
            "Income_Statement": {
                "quarterly": {
                    "2026-06-30": {"date": "2026-06-30", "totalRevenue": 100e9, "netIncome": 25e9, "ebitda": 34e9},
                },
                "yearly": {},
            },
        },
    }
    base.update(overrides)
    return base


def _listing_row(symbol: str, name: str, exchange: str, security_type: str = "Common Stock") -> dict:
    return {"Code": symbol, "Name": name, "Exchange": exchange, "Type": security_type}


def _seed_universe(database: Database, market: str, rows: list[dict]) -> None:
    methodology_id = database.ensure_methodology_version("test_universe", 1, {}, "test")
    database.save_analysis_snapshot(
        "valuation_universe",
        f"{market}_UNIVERSE",
        methodology_id,
        {},
        {"rows": rows, "universe_size": len(rows)},
        datetime.now(timezone.utc),
    )


def _us_stock_row(symbol: str, market_cap: float, **overrides) -> dict:
    row = {
        "symbol": symbol,
        "name": f"Company {symbol}",
        "sector": "Tech",
        "security_type": "Stock",
        "market_cap": market_cap,
        "logo_url": None,
    }
    row.update(overrides)
    return row


def _b3_row(symbol: str, market_cap: float, **overrides) -> dict:
    """Shape of a real B3ScreenerService universe row: no "security_type"
    key at all (the B3 universe is stocks-only by construction), and
    multiples/profitability/leverage already blended from Brapi + EODHD."""
    row = {
        "symbol": symbol,
        "name": f"Empresa {symbol}",
        "sector": "Industrials",
        "market_cap": market_cap,
        "logo_url": None,
        "pe": 8.0,
        "forward_pe": 7.5,
        "ev_ebitda": 5.0,
        "peg": 1.1,
        "price_to_book": 1.3,
        "roe": 0.22,
        "profit_margin": 0.15,
        "ebitda_margin": 0.28,
        "debt_to_equity": 0.9,
        "revenue_growth": 0.07,
        "earnings_growth": 0.12,
        "dividend_yield": 0.06,
        "cash": 5e9,
        "debt": 9e9,
        "ebitda": 4e9,
        "data_source_count": 2,
        "fundamentals_as_of": "2026-06-30",
    }
    row.update(overrides)
    return row


def test_refresh_daily_covers_the_full_us_exchange_listing_in_budgeted_cohorts():
    settings = get_settings()
    database = Database(settings)
    listing = (
        [_listing_row(f"N{i:03d}", f"Nasdaq Co {i}", "NASDAQ") for i in range(40)]
        + [_listing_row("NYS1", "NYSE Co", "NYSE")]
        + [_listing_row("OTC1", "OTC Co", "PINK")]
        + [_listing_row("ETF1", "Some ETF", "NASDAQ", security_type="ETF")]
    )
    http = StubHttp({"exchange-symbol-list/US": listing, "fundamentals/": _eodhd_payload()})
    service = ChewieFundamentalsService(settings, database, http)  # type: ignore[arg-type]

    first = service.refresh_daily("NASDAQ", budget=35)
    assert first == {"universe": 40, "covered": 35, "refreshed": 35}

    second = service.refresh_daily("NASDAQ", budget=35)
    assert second["universe"] == 40
    assert second["covered"] == 40  # the 5 pending symbols entered after the top-30 refresh

    payload = service.rows("NASDAQ")
    assert payload["universe_size"] == 40
    assert payload["covered_count"] == 40
    assert len(payload["items"]) == 30
    assert payload["items"][0]["refreshed_at"]


def test_us_listing_is_split_by_exchange_and_excludes_funds_and_otc():
    settings = get_settings()
    database = Database(settings)
    listing = [
        _listing_row("AAPL", "Apple", "NASDAQ"),
        _listing_row("KO", "Coca-Cola", "NYSE"),
        _listing_row("SPY", "SPDR S&P 500", "NYSE ARCA", security_type="ETF"),
        _listing_row("PINKY", "Pink Sheet Co", "PINK"),
    ]
    http = StubHttp({"exchange-symbol-list/US": listing, "fundamentals/": _eodhd_payload()})
    service = ChewieFundamentalsService(settings, database, http)  # type: ignore[arg-type]

    assert service.refresh_daily("NASDAQ")["universe"] == 1
    assert service.refresh_daily("NYSE")["universe"] == 1


def test_b3_snapshot_is_read_directly_from_the_brapi_backed_screener_universe_with_no_extra_calls():
    settings = get_settings()
    database = Database(settings)
    _seed_universe(database, "B3", [
        _b3_row("PETR4", 4e11, pe=5.1, forward_pe=4.8, ev_ebitda=3.9, price_to_book=1.2, roe=0.31, dividend_yield=0.12),
        _b3_row("VALE3", 3e11),
    ])
    http = StubHttp({"fundamentals/": _eodhd_payload()})  # would answer if ever called
    service = ChewieFundamentalsService(settings, database, http)  # type: ignore[arg-type]

    counts = service.refresh_daily("B3")
    assert counts == {"universe": 2, "covered": 2, "refreshed": 2}
    assert http.calls == []  # B3 costs zero EODHD credits

    payload = service.rows("B3")
    assert "Brapi" in payload["source"]
    item = payload["items"][0]
    assert item["symbol"] == "PETR4"
    assert item["multiples"]["pe"] == 5.1
    assert item["multiples"]["ev_ebitda"] == 3.9
    assert item["profitability"]["roe_percent"] == 31.0
    assert item["multiples"]["dividend_yield_percent"] == 12.0
    assert item["sources"] == ["Brapi", "EODHD overlay"]
    assert item["leverage"]["total_cash"] == 5e9
    assert item["leverage"]["total_debt"] == 9e9


def test_b3_universe_never_includes_fractional_or_bdr_tickers():
    """The B3 screener universe already excludes fractional-lot ("F"
    suffix) tickers and BDR wrappers of foreign (e.g. Nasdaq) companies --
    Chewie must not reintroduce them by reading from a different source."""
    settings = get_settings()
    database = Database(settings)
    _seed_universe(database, "B3", [
        _b3_row("PETR4", 4e11),
        _b3_row("PETR4F", 1e6),  # a real screener output would never emit this, but assert no special-casing hides bugs
        _b3_row("AAPL34", 2e11, name="Apple Inc"),  # a Nasdaq BDR, if it ever leaked in
    ])
    http = StubHttp({})
    service = ChewieFundamentalsService(settings, database, http)  # type: ignore[arg-type]
    service.refresh_daily("B3")

    symbols = {item["symbol"] for item in service.rows("B3")["items"]}
    # Chewie itself does not filter these -- it trusts the screener universe
    # as-is. This test documents that trust: whatever the universe contains
    # is what is shown, with zero independent listing fetched by Chewie.
    assert symbols == {"PETR4", "PETR4F", "AAPL34"}
    assert http.calls == []


def test_search_finds_snapshot_entries_and_resolves_listing_names_live():
    settings = get_settings()
    database = Database(settings)
    listing = [
        _listing_row("KO", "Coca-Cola", "NYSE"),
        _listing_row("KHC", "Kraft Heinz", "NYSE"),
        _listing_row("BRK-B", "Berkshire Hathaway", "NYSE"),
    ]
    http = StubHttp({
        "exchange-symbol-list/US": listing,
        "fundamentals/KO.US": _eodhd_payload("KO", "Coca-Cola"),
        "fundamentals/KHC.US": _eodhd_payload("KHC", "Kraft Heinz"),
        "fundamentals/BRK-B.US": _eodhd_payload("BRK-B", "Berkshire Hathaway"),
    })
    service = ChewieFundamentalsService(settings, database, http)  # type: ignore[arg-type]
    service.refresh_daily("NYSE", budget=2)  # BRK-B stays outside the snapshot

    found = service.search("NYSE", "kraft")
    assert [item["symbol"] for item in found["items"]] == ["KHC"]
    assert found["items"][0]["from_universe"] is True

    fallback = service.search("NYSE", "berkshire")
    assert [item["symbol"] for item in fallback["items"]] == ["BRK-B"]
    assert fallback["items"][0]["from_universe"] is False

    missing = service.search("NYSE", "ZZZZZZZZ")
    assert missing["items"] == []


def test_b3_search_fallback_does_not_use_the_noisy_exchange_listing():
    settings = get_settings()
    database = Database(settings)
    _seed_universe(database, "B3", [_b3_row("PETR4", 4e11)])
    http = StubHttp({"fundamentals/WEGE3.SA": _eodhd_payload("WEGE3", "WEG")})
    service = ChewieFundamentalsService(settings, database, http)  # type: ignore[arg-type]
    service.refresh_daily("B3")

    # A ticker-shaped query outside the universe still resolves by direct
    # EODHD ticker fetch (not a listing scan).
    fallback = service.search("B3", "WEGE3")
    assert [item["symbol"] for item in fallback["items"]] == ["WEGE3"]
    assert not any("exchange-symbol-list" in call for call in http.calls)

    # A free-text company name outside the tracked universe is not resolved
    # for B3 -- there is no listing to search by name against.
    missing = service.search("B3", "some untracked company")
    assert missing["items"] == []


def test_rows_bootstrap_builds_top_30_of_the_tracked_universe_live():
    settings = get_settings()
    database = Database(settings)
    rows = [_us_stock_row(f"B{i:03d}", float(500 - i)) for i in range(40)]
    _seed_universe(database, "NASDAQ", rows)
    http = StubHttp({"fundamentals/": _eodhd_payload()})
    service = ChewieFundamentalsService(settings, database, http)  # type: ignore[arg-type]

    payload = service.rows("NASDAQ")
    assert len(payload["items"]) == 30
    assert "bootstrap" in payload["source"]
    fundamentals_calls = [url for url in http.calls if "fundamentals/" in url]
    assert len(fundamentals_calls) == 30


def test_rows_bootstrap_for_b3_costs_zero_provider_calls():
    settings = get_settings()
    database = Database(settings)
    rows = [_b3_row(f"BBB{i}3", float(500 - i)) for i in range(40)]
    _seed_universe(database, "B3", rows)
    http = StubHttp({})
    service = ChewieFundamentalsService(settings, database, http)  # type: ignore[arg-type]

    payload = service.rows("B3")
    assert len(payload["items"]) == 30
    assert "Brapi" in payload["source"]
    assert http.calls == []


def test_refresh_all_serves_b3_fully_without_touching_the_us_budget():
    settings = get_settings()
    database = Database(settings)
    _seed_universe(database, "B3", [_b3_row(f"BR{i:02d}3", float(10 - i)) for i in range(10)])
    us_listing = (
        [_listing_row(f"N{i:02d}", f"Nasdaq Co {i}", "NASDAQ") for i in range(20)]
        + [_listing_row(f"Y{i:02d}", f"NYSE Co {i}", "NYSE") for i in range(20)]
    )
    http = StubHttp({
        "exchange-symbol-list/US": us_listing,
        "fundamentals/": _eodhd_payload(),
    })
    service = ChewieFundamentalsService(settings, database, http)  # type: ignore[arg-type]

    counts = service.refresh_all(budget=30)

    assert counts["B3"]["refreshed"] == 10
    assert counts["NASDAQ"]["refreshed"] + counts["NYSE"]["refreshed"] == 30
    assert counts["NASDAQ"]["refreshed"] == 15
    assert counts["NYSE"]["refreshed"] == 15


def test_render_report_writes_a_premium_pdf(tmp_path: Path):
    settings = get_settings().model_copy(update={"one_pager_output_dir": tmp_path / "one-pagers"})
    database = Database(settings)
    http = StubHttp({"fundamentals/PETR4.SA": _eodhd_payload("PETR4", "Petrobras")})
    service = ChewieFundamentalsService(settings, database, http)  # type: ignore[arg-type]

    path = service.render_report("B3", "PETR4")

    assert path is not None and path.is_file()
    assert path.read_bytes()[:5] == b"%PDF-"
    assert path.name == "PETR4-B3-fundamentals.pdf"


def test_render_report_returns_none_for_unknown_symbol():
    settings = get_settings()
    database = Database(settings)
    http = StubHttp({})
    service = ChewieFundamentalsService(settings, database, http)  # type: ignore[arg-type]

    assert service.render_report("NASDAQ", "NOPE") is None
    assert service.render_report("NASDAQ", "../evil") is None
