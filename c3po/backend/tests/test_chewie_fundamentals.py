from datetime import datetime, timezone

from app.chewie_fundamentals import ChewieFundamentalsService
from app.config import get_settings
from app.database import Database


class StubHttp:
    def __init__(self, results: dict[str, dict]) -> None:
        self.results = results
        self.calls: list[str] = []

    def get_json(self, url, *, params=None, headers=None):
        self.calls.append(url)
        for suffix, payload in self.results.items():
            if url.endswith(suffix):
                return payload
        return {}


def _eodhd_payload(**overrides) -> dict:
    base = {
        "General": {"Code": "PETR4", "Name": "Petrobras", "Sector": "Energy", "LogoURL": "/img.png"},
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
        },
        "Valuation": {"TrailingPE": 6.5, "ForwardPE": 6.0, "EnterpriseValueEbitda": 4.2, "PriceBookMRQ": 1.4},
        "SharesStats": {},
        "Technicals": {},
        "AnalystRatings": {},
        "Earnings": {"Trend": {}},
        "Financials": {
            "Balance_Sheet": {"quarterly": {}, "yearly": {}},
            "Cash_Flow": {"quarterly": {}, "yearly": {}},
            "Income_Statement": {"quarterly": {}, "yearly": {}},
        },
    }
    base.update(overrides)
    return base


def _seed_universe(database: Database, market: str, rows: list[dict]) -> None:
    methodology_id = database.ensure_methodology_version(
        "test_universe", 1, {}, "test"
    )
    database.save_analysis_snapshot(
        "valuation_universe",
        f"{market}_UNIVERSE",
        methodology_id,
        {},
        {"rows": rows, "universe_size": len(rows)},
        datetime.now(timezone.utc),
    )


def test_rows_reads_universe_and_shapes_the_four_categories():
    settings = get_settings()
    database = Database(settings)
    _seed_universe(database, "B3", [
        {"symbol": "PETR4", "name": "Petrobras", "sector": "Energy", "security_type": "Stock", "market_cap": 400_000_000_000, "logo_url": None},
        {"symbol": "VIVT3", "name": "Vivo", "sector": "Telecom", "security_type": "ETF", "market_cap": 999, "logo_url": None},
    ])
    http = StubHttp({"fundamentals/PETR4.SA": _eodhd_payload()})
    service = ChewieFundamentalsService(settings, database, http)  # type: ignore[arg-type]

    payload = service.rows("B3")

    assert payload["universe_size"] == 1  # ETF excluded
    assert payload["covered_count"] == 1
    item = payload["items"][0]
    assert item["symbol"] == "PETR4"
    assert item["multiples"]["pe"] == 6.5
    assert item["multiples"]["ev_ebitda"] == 4.2
    assert item["profitability"]["roe_percent"] == 28.0
    assert item["growth"]["revenue_growth_percent"] == 8.0
    assert item["leverage"]["net_debt_to_ebitda"] is None or isinstance(item["leverage"]["net_debt_to_ebitda"], float)


def test_rows_are_cached_until_ttl_or_explicit_refresh():
    settings = get_settings()
    database = Database(settings)
    _seed_universe(database, "NASDAQ", [
        {"symbol": "AAPL", "name": "Apple", "sector": "Tech", "security_type": "Stock", "market_cap": 3_000_000_000_000, "logo_url": None},
    ])
    http = StubHttp({"fundamentals/AAPL.US": _eodhd_payload()})
    service = ChewieFundamentalsService(settings, database, http)  # type: ignore[arg-type]

    service.rows("NASDAQ")
    service.rows("NASDAQ")
    assert len(http.calls) == 1

    service.rows("NASDAQ", refresh=True)
    assert len(http.calls) == 2


def test_rows_cap_the_universe_to_the_top_market_cap_symbols():
    settings = get_settings()
    database = Database(settings)
    rows = [
        {"symbol": f"S{i}", "name": f"Company {i}", "sector": "Tech", "security_type": "Stock", "market_cap": float(i), "logo_url": None}
        for i in range(200)
    ]
    _seed_universe(database, "NYSE", rows)
    http = StubHttp({})
    service = ChewieFundamentalsService(settings, database, http)  # type: ignore[arg-type]

    payload = service.rows("NYSE")

    assert payload["universe_size"] == 200
    assert payload["covered_count"] == 150
    assert payload["items"][0]["symbol"] == "S199"
