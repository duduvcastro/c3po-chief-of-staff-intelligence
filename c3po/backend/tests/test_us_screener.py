from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.database import Database
from app.market_data.us_screener import USScreeningService


class DummyRealtime:
    http = object()


class DummyOnePagers:
    def _analyze(self, symbol, market, quote, fundamentals, history):
        return {
            "c3po_tp": 145.0,
            "consensus_tp": 150.0,
            "analyst_count": 12,
            "buy_in": 94.0,
            "confidence": 82.0,
            "risk_score": 29.0,
            "dispersion": 12.0,
            "methods": {
                "Goldman Sachs": 140.0,
                "Morgan Stanley": 146.0,
                "Bridgewater": 138.0,
                "JPMorgan": 149.0,
                "BlackRock": 152.0,
            },
            "thesis": ["Durable growth and cash generation support the valuation."],
            "risks": ["Execution and multiple compression remain the principal risks."],
        }


def service() -> USScreeningService:
    settings = Settings(eodhd_api_token="test", auth_cookie_secure=False)
    return USScreeningService(settings, Database(settings), DummyRealtime(), DummyOnePagers())


def rising_history(days: int = 260):
    start = datetime(2025, 8, 1, tzinfo=timezone.utc)
    return [
        {"date": (start + timedelta(days=index)).date().isoformat(), "close": 80 + index * 0.08, "volume": 2_000_000}
        for index in range(days)
    ]


def test_stock_analysis_uses_canonical_five_method_output() -> None:
    result = service()._analyze_stock(
        "NASDAQ",
        {
            "symbol": "TEST",
            "name": "Test Corp",
            "price": 100.0,
            "change_percent": 1.2,
            "volume": 3_000_000,
            "as_of": datetime.now(timezone.utc),
        },
        {
            "companyName": "Test Corp",
            "sector": "Technology",
            "industry": "Software",
            "marketCap": 5_000_000_000,
            "returnOnEquity": 0.24,
            "profitMargins": 0.18,
            "dividendYield": 0.01,
        },
        rising_history(),
        300_000_000,
    )

    assert result["security_type"] == "Stock"
    assert result["our_tp"] == 145.0
    assert result["signal_quality"] == "validated"
    assert result["valuation_method_count"] == 6


def test_etf_analysis_uses_fund_evidence_instead_of_corporate_dcf() -> None:
    result = service()._analyze_etf(
        "NYSE",
        {
            "symbol": "TESTETF",
            "name": "Test ETF",
            "price": 100.0,
            "change_percent": 0.4,
            "volume": 4_000_000,
            "as_of": datetime.now(timezone.utc),
        },
        {
            "companyName": "Test ETF",
            "isETF": True,
            "etfCategory": "Large Blend",
            "etfTotalAssets": 8_000_000_000,
            "etfNetExpenseRatio": 0.001,
            "etfHoldingsCount": 500,
            "etfExpectedReturn3Y": 0.12,
        },
        rising_history(),
        400_000_000,
    )

    assert result["security_type"] == "ETF"
    assert result["valuation_profile"] == "general"
    assert result["internal_method_count"] == 5
    assert "Asset allocation" in result["buy_in_models"]
    assert result["public_consensus_tp"] is None


def test_spcx_never_uses_etf_screening_path() -> None:
    assert service()._is_etf({"Code": "SPCX", "Type": "ETF"}) is False


def test_candidate_ranking_combines_stocks_and_etfs_by_tp_upside() -> None:
    screener = service()
    stock = screener._analyze_stock(
        "NASDAQ",
        {
            "symbol": "STOCK",
            "name": "Stock Corp",
            "price": 100.0,
            "change_percent": 1.2,
            "volume": 3_000_000,
            "as_of": datetime.now(timezone.utc),
        },
        {
            "companyName": "Stock Corp",
            "sector": "Technology",
            "industry": "Software",
            "marketCap": 5_000_000_000,
            "returnOnEquity": 0.24,
            "profitMargins": 0.18,
        },
        rising_history(),
        300_000_000,
    )
    etf = screener._analyze_etf(
        "NASDAQ",
        {
            "symbol": "ETFONE",
            "name": "ETF One",
            "price": 100.0,
            "change_percent": 0.4,
            "volume": 4_000_000,
            "as_of": datetime.now(timezone.utc),
        },
        {
            "companyName": "ETF One",
            "isETF": True,
            "etfCategory": "Large Blend",
            "etfTotalAssets": 8_000_000_000,
            "etfNetExpenseRatio": 0.001,
            "etfHoldingsCount": 500,
            "etfExpectedReturn3Y": 0.12,
        },
        rising_history(),
        400_000_000,
    )
    stock["status"] = "full_match"
    etf["status"] = "full_match"
    screener._rows["NASDAQ"] = [etf, stock]
    screener._basis_at["NASDAQ"] = datetime.now(timezone.utc)

    response = screener._candidate_response("NASDAQ")

    assert [item.security_type for item in response.items] == ["Stock", "ETF"]
    assert response.items[0].upside_percent > response.items[1].upside_percent
