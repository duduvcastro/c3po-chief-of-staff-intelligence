from datetime import datetime, timezone
from pathlib import Path

from app.chewie_fundamentals import ChewieFundamentalsService
from app.config import get_settings
from app.database import Database


class StubHttp:
    def __init__(self, results: dict[str, dict]) -> None:
        self.results = results
        self.calls: list[str] = []

    def get_json(self, url, *, params=None, headers=None):
        self.calls.append(url)
        for fragment, payload in self.results.items():
            if fragment in url:
                return payload
        return {}


def _eodhd_payload(symbol: str = "PETR4", name: str = "Petrobras", **overrides) -> dict:
    base = {
        "General": {
            "Code": symbol,
            "Name": name,
            "Sector": "Energy",
            "Industry": "Oil & Gas",
            "LogoURL": "/img.png",
            "Description": "Integrated energy company.",
        },
        "Highlights": {
            "MarketCapitalization": 500_000_000_000,
            "PERatio": 6.5,
            "ReturnOnEquityTTM": 0.28,
            "ReturnOnAssetsTTM": 0.12,
            "ProfitMargin": 0.22,
            "OperatingMarginTTM": 0.30,
            "QuarterlyRevenueGrowthYOY": 0.08,
            "QuarterlyEarningsGrowthYOY": 0.15,
            "EBITDA": 200_000_000_000,
            "RevenueTTM": 500_000_000_000,
            "DividendYield": 0.11,
            "DilutedEpsTTM": 7.2,
            "WallStreetTargetPrice": 46.0,
        },
        "Valuation": {"TrailingPE": 6.5, "ForwardPE": 6.0, "EnterpriseValueEbitda": 4.2, "PriceBookMRQ": 1.4},
        "SharesStats": {},
        "Technicals": {"52WeekHigh": 45.0, "52WeekLow": 30.0, "50DayMA": 40.0, "200DayMA": 38.0},
        "AnalystRatings": {"Rating": 4.1, "StrongBuy": 6, "Buy": 4, "Hold": 3, "Sell": 1, "StrongSell": 0},
        "Earnings": {"Trend": {}},
        "Financials": {
            "Balance_Sheet": {"quarterly": {}, "yearly": {}},
            "Cash_Flow": {"quarterly": {}, "yearly": {}},
            "Income_Statement": {
                "quarterly": {
                    "2026-06-30": {"date": "2026-06-30", "totalRevenue": 130e9, "netIncome": 30e9, "ebitda": 55e9},
                    "2026-03-31": {"date": "2026-03-31", "totalRevenue": 120e9, "netIncome": 25e9, "ebitda": 50e9},
                },
                "yearly": {},
            },
        },
    }
    base.update(overrides)
    return base


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


def _stock_row(symbol: str, market_cap: float, **overrides) -> dict:
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


def test_refresh_daily_persists_snapshot_and_rows_show_only_top_30():
    settings = get_settings()
    database = Database(settings)
    rows = [_stock_row(f"S{i:03d}", float(1000 - i)) for i in range(45)]
    _seed_universe(database, "NASDAQ", rows)
    http = StubHttp({"fundamentals/": _eodhd_payload()})
    service = ChewieFundamentalsService(settings, database, http)  # type: ignore[arg-type]

    covered = service.refresh_daily("NASDAQ")
    assert covered == 45
    assert service.has_snapshot("NASDAQ")

    payload = service.rows("NASDAQ")
    assert payload["universe_size"] == 45
    assert payload["covered_count"] == 45
    assert len(payload["items"]) == 30
    assert payload["items"][0]["symbol"] == "S000"


def test_universe_row_blend_takes_precedence_over_raw_provider_values():
    settings = get_settings()
    database = Database(settings)
    _seed_universe(database, "B3", [
        _stock_row("PETR4", 4e11, pe=5.1, forward_pe=4.8, ev_ebitda=3.9, price_to_book=1.2, roe_percent=31.0, dividend_yield=0.12),
    ])
    http = StubHttp({"fundamentals/PETR4.SA": _eodhd_payload()})
    service = ChewieFundamentalsService(settings, database, http)  # type: ignore[arg-type]
    service.refresh_daily("B3")

    item = service.rows("B3")["items"][0]
    assert item["multiples"]["pe"] == 5.1
    assert item["multiples"]["ev_ebitda"] == 3.9
    assert item["profitability"]["roe_percent"] == 31.0
    assert item["multiples"]["dividend_yield_percent"] == 12.0
    assert any("Brapi" in source for source in item["sources"])


def test_search_finds_snapshot_entries_and_falls_back_to_live_lookup():
    settings = get_settings()
    database = Database(settings)
    _seed_universe(database, "NYSE", [
        _stock_row("KO", 2.6e11), _stock_row("KHC", 4e10),
    ])
    http = StubHttp({
        "fundamentals/KO.US": _eodhd_payload("KO", "Coca-Cola"),
        "fundamentals/KHC.US": _eodhd_payload("KHC", "Kraft Heinz"),
        "fundamentals/BRK-B.US": _eodhd_payload("BRK-B", "Berkshire Hathaway"),
    })
    service = ChewieFundamentalsService(settings, database, http)  # type: ignore[arg-type]
    service.refresh_daily("NYSE")

    found = service.search("NYSE", "kraft")
    assert [item["symbol"] for item in found["items"]] == ["KHC"]
    assert found["items"][0]["from_universe"] is True

    fallback = service.search("NYSE", "BRK-B")
    assert [item["symbol"] for item in fallback["items"]] == ["BRK-B"]
    assert fallback["items"][0]["from_universe"] is False

    missing = service.search("NYSE", "ZZZZZZZZ")
    assert missing["items"] == []


def test_rows_bootstrap_builds_top_30_live_before_first_snapshot():
    settings = get_settings()
    database = Database(settings)
    rows = [_stock_row(f"B{i:03d}", float(500 - i)) for i in range(40)]
    _seed_universe(database, "B3", rows)
    http = StubHttp({"fundamentals/": _eodhd_payload()})
    service = ChewieFundamentalsService(settings, database, http)  # type: ignore[arg-type]

    payload = service.rows("B3")
    assert len(payload["items"]) == 30
    assert payload["universe_size"] == 40
    assert "bootstrap" in payload["source"]
    fundamentals_calls = [url for url in http.calls if "fundamentals/" in url]
    assert len(fundamentals_calls) == 30


def test_render_report_writes_a_premium_pdf(tmp_path: Path):
    settings = get_settings().model_copy(update={"one_pager_output_dir": tmp_path / "one-pagers"})
    database = Database(settings)
    _seed_universe(database, "B3", [_stock_row("PETR4", 4e11, pe=5.1)])
    http = StubHttp({"fundamentals/PETR4.SA": _eodhd_payload()})
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
