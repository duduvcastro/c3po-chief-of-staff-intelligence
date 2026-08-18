import statistics
from datetime import datetime, timedelta, timezone

import pytest

from app.config import Settings
from app.database import Database
from app.foreign_listings import normalize_foreign_fundamentals, policy_for
from app.market_data.service import MarketDataService
from app.market_data.http import MarketDataRequestError
from app.one_pager import OnePagerGenerationError, OnePagerService
from app.valuation_policy import METHODOLOGY_VERSION


def service_for(tmp_path):
    settings = Settings(
        brapi_token="brapi-test",
        eodhd_api_token="eodhd-test",
        one_pager_output_dir=tmp_path,
        auth_cookie_secure=False,
    )
    database = Database(settings)
    return OnePagerService(settings, database, MarketDataService(settings, database), output_dir=tmp_path)


def sample_analysis(service):
    return service._analyze(
        "MSFT",
        "US",
        {
            "price": 500.0,
            "currency": "USD",
            "change_percent": 1.25,
            "as_of": datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc),
        },
        {
            "companyName": "Microsoft Corporation",
            "sector": "Technology",
            "marketCap": 3_700_000_000_000,
            "trailingPE": 31.0,
            "forwardPE": 27.0,
            "enterpriseToEbitda": 22.0,
            "pegRatio": 1.8,
            "trailingEps": 16.0,
            "forwardEps": 18.5,
            "bookValue": 42.0,
            "sharesOutstanding": 7_430_000_000,
            "freeCashflow": 92_000_000_000,
            "ebitda": 150_000_000_000,
            "totalDebt": 80_000_000_000,
            "totalCash": 90_000_000_000,
            "targetMeanPrice": 610.0,
            "numberOfAnalystOpinions": 48,
            "analystRatings": {
                "strongBuy": 12,
                "buy": 18,
                "hold": 15,
                "sell": 2,
                "strongSell": 1,
            },
            "returnOnEquity": 0.34,
            "profitMargins": 0.36,
            "revenueGrowthAnnual": 0.15,
            "earningsGrowthAnnual": 0.17,
            "beta": 0.95,
        },
    )


def test_symbol_normalization_supports_b3_and_us(tmp_path) -> None:
    service = service_for(tmp_path)

    assert service._normalize_symbol(" prnr3.sa ") == ("PRNR3", "B3")
    assert service._normalize_symbol("amzn") == ("AMZN", "US")
    with pytest.raises(OnePagerGenerationError):
        service._normalize_symbol("AMZN; rm -rf")


def test_resolve_us_exchange_cross_references_screener_universes(tmp_path) -> None:
    """Ben Kenobi Records classifies by exchange (B3/NASDAQ/NYSE), but One Pager
    itself only knows the binary B3/US split -- this resolver fills the gap by
    checking which bulk US screener universe (already computed, no extra API
    calls) the symbol showed up in most recently."""
    service = service_for(tmp_path)
    methodology_id = service.database.ensure_methodology_version("us-screener", 1, {}, "test")
    now = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
    service.database.save_analysis_snapshot(
        "valuation_universe", "NASDAQ_UNIVERSE", methodology_id,
        {"market": "NASDAQ"}, {"rows": [{"symbol": "AAPL"}]}, now,
    )
    service.database.save_analysis_snapshot(
        "valuation_universe", "NYSE_UNIVERSE", methodology_id,
        {"market": "NYSE"}, {"rows": [{"symbol": "JPM"}]}, now,
    )

    assert service._resolve_us_exchange("aapl") == "NASDAQ"
    assert service._resolve_us_exchange("JPM") == "NYSE"
    assert service._resolve_us_exchange("UNKNOWN") == "US"


def test_b3_quote_falls_back_to_eodhd_when_brapi_rejects_a_unit(tmp_path) -> None:
    service = service_for(tmp_path)

    class Quote:
        provider = "eodhd"
        symbol = "IGTI11"

    calls = []

    def fetch_quotes(provider, symbols, *, persist=True):
        calls.append((provider, symbols, persist))
        if provider == "brapi":
            raise MarketDataRequestError("404 Not Found")
        return [Quote()]

    service.market_data.fetch_quotes = fetch_quotes

    quote = service._fetch_quote("IGTI11", "B3")

    assert quote.provider == "eodhd"
    assert calls == [
        ("brapi", ["IGTI11"], True),
        ("eodhd", ["IGTI11.SA"], True),
    ]


def test_quote_failure_uses_a_user_facing_error_without_internal_urls(tmp_path) -> None:
    service = service_for(tmp_path)

    def fetch_quotes(provider, symbols, *, persist=True):
        raise MarketDataRequestError(f"404 for https://provider.invalid/{symbols[0]}")

    service.market_data.fetch_quotes = fetch_quotes

    with pytest.raises(OnePagerGenerationError) as raised:
        service._fetch_quote("IGTI11", "B3")

    assert "Brapi e na EODHD" in str(raised.value)
    assert "https://" not in str(raised.value)


def test_latest_fundamental_period_uses_financial_statements(tmp_path) -> None:
    service = service_for(tmp_path)
    assert service._latest_fundamental_period({
        "updated_at": "2026-08-06",
        "quarterlyIncome": [{"date": "2026-06-30"}, {"date": "2026-03-31"}],
        "quarterlyCashFlow": [{"date": "2026-06-30"}],
    }) == "2026-06-30"


def test_pending_official_result_is_non_blocking_context(tmp_path) -> None:
    service = service_for(tmp_path)
    service.database.register_ir_securities([{
        "market": "B3", "symbol": "TEST3", "company_name": "Companhia Teste",
        "name_key": "COMPANHIA TESTE", "regulator_id": "123", "exchange": "B3",
    }])
    company = service.database.list_ir_companies("B3")[0]
    service.database.save_ir_events([{
        "source_code": "ri", "external_id": "test3-2t26", "company_id": company["id"],
        "market": "B3", "symbol": "TEST3", "company_name": company["company_name"],
        "regulator_id": "123", "event_type": "Financial Results", "form": "RI",
        "title": "Resultados 2T26", "summary": "Release oficial",
        "published_at": datetime(2026, 8, 6, tzinfo=timezone.utc),
        "published_time_precision": "date", "reference_date": datetime(2026, 6, 30).date(),
        "official_url": "https://ri.example.com", "document_url": "https://ri.example.com/2t26.pdf",
        "materiality": "high", "valuation_relevant": True, "valuation_status": "pending_review",
        "raw_metadata": {}, "collected_at": datetime(2026, 8, 6, tzinfo=timezone.utc),
    }])

    context = service._official_disclosure_context("TEST3", "B3", "2026-03-31")

    assert context["status"] == "pending_review"
    assert context["title"] == "Resultados 2T26"
    assert context["fundamentals_period"] == "2026-03-31"


def test_analysis_and_pdf_are_deterministic_and_persisted(tmp_path) -> None:
    service = service_for(tmp_path)
    analysis = sample_analysis(service)
    assert list(analysis["methods"]) == [
        "Goldman Sachs",
        "Morgan Stanley",
        "Bridgewater",
        "JPMorgan",
        "BlackRock",
    ]
    assert analysis["analyst_count"] == 48
    assert analysis["analyst_buy"] == 30
    assert analysis["analyst_hold"] == 15
    assert analysis["analyst_sell"] == 3
    start = datetime(2025, 8, 5, tzinfo=timezone.utc)
    history = [
        {
            "date": (start + timedelta(days=round(index * 365 / 260))).date().isoformat(),
            "close": 400 + index * 0.3,
        }
        for index in range(261)
    ]

    report = service._write_report(analysis, history)

    assert report.symbol == "MSFT"
    assert report.methodology_version == METHODOLOGY_VERSION
    assert report.method_count == 5
    assert report.c3po_tp > 0
    assert report.buy_in < report.c3po_tp
    assert (tmp_path / report.filename).read_bytes().startswith(b"%PDF")
    assert (datetime.fromisoformat(history[-1]["date"]) - datetime.fromisoformat(history[0]["date"])).days == 365
    assert service.list_reports()[0].filename == report.filename


def test_b3_one_pager_uses_shared_candidate_and_matrix_valuation(tmp_path) -> None:
    service = service_for(tmp_path)
    shared = {
        "our_tp": 42.0,
        "internal_tp": 39.0,
        "public_consensus_tp": 45.0,
        "analyst_count": 8,
        "buy_in": 31.5,
        "risk_score": 33.0,
        "operating_quality": 76.0,
        "valuation_confidence": 84.0,
        "method_dispersion_percent": 12.0,
        "methods": {
            "dcf": 38.0,
            "earnings": 43.0,
            "enterprise": 40.0,
            "book": 35.0,
            "consensus": 45.0,
        },
    }
    analysis = service._analyze(
        "TEST3",
        "B3",
        {"price": 30.0, "currency": "BRL", "change_percent": 0.5},
        {
            "companyName": "Companhia Teste",
            "sector": "Industrials",
            "forwardEps": 3.0,
            "trailingEps": 2.8,
            "bookValue": 15.0,
            "sharesOutstanding": 100_000_000,
            "ebitda": 500_000_000,
            "freeCashflow": 200_000_000,
            "totalDebt": 300_000_000,
            "totalCash": 100_000_000,
        },
        shared_valuation=shared,
    )

    assert analysis["c3po_tp"] == 42.0
    assert analysis["buy_in"] == 31.5
    assert analysis["risk_score"] == 33.0
    assert analysis["confidence"] == 84.0
    assert analysis["methodology_version"] == METHODOLOGY_VERSION
    assert f"v{METHODOLOGY_VERSION}" in analysis["source"]
    assert statistics.mean(analysis["methods"].values()) == pytest.approx(42.0)


def test_mhvyf_uses_primary_listing_currency_and_public_coverage(tmp_path) -> None:
    service = service_for(tmp_path)
    policy = policy_for("MHVYF")
    assert policy is not None
    fundamentals = normalize_foreign_fundamentals(
        {
            "companyName": "Mitsubishi Heavy Industries Ltd.",
            "sector": "Industrials",
            "industry": "Specialty Industrial Machinery",
            "sharesOutstanding": 3_360_209_340,
            "forwardPE": 29.7619,
            "trailingPE": 59.6667,
            "enterpriseToEbitda": 34.1489,
            "pegRatio": 1.6506,
            "bookValue": 5.9289,
            "returnOnEquity": 0.1475,
            "profitMargins": 0.0776,
            "operatingMargins": 0.1063,
            "revenueGrowthAnnual": 0.155,
            "earningsGrowthAnnual": 0.973,
            "beta": 0.369,
            "ebitda": 693_468_987_392,
            "freeCashflow": 250_315_618_000,
            "totalCash": 1_671_905_291_000,
            "totalDebt": 294_624_855_000,
            "quarterlyIncome": [
                {"date": "2026-06-30", "totalRevenue": 1_185_566_939_000, "operatingIncome": 125_980_318_000, "netIncome": 133_707_034_000, "ebitda": 153_304_281_000},
                {"date": "2026-03-31", "totalRevenue": 1_657_560_151_000, "operatingIncome": 182_387_848_000, "netIncome": 121_895_464_000, "ebitda": 253_814_628_000},
                {"date": "2025-12-31", "totalRevenue": 1_100_000_000_000, "operatingIncome": 100_000_000_000, "netIncome": 80_000_000_000, "ebitda": 150_000_000_000},
                {"date": "2025-09-30", "totalRevenue": 1_000_000_000_000, "operatingIncome": 90_000_000_000, "netIncome": 70_000_000_000, "ebitda": 140_000_000_000},
            ],
            "quarterlyCashFlow": [{"date": "2026-06-30", "freeCashFlow": 250_315_618_000}],
            "quarterlyBalance": [{"date": "2026-06-30", "cash": 1_671_905_291_000, "shortLongTermDebtTotal": 847_647_456_000}],
        },
        policy=policy,
        fx_rate=159.305,
        quote_price=26.84,
    )

    analysis = service._analyze(
        "MHVYF",
        "US",
        {"price": 26.84, "currency": "USD", "change_percent": -0.56},
        fundamentals,
    )

    assert fundamentals["quarterlyIncome"][0]["totalRevenue"] == pytest.approx(1_185_566_939_000 / 159.305)
    assert analysis["consensus_tp"] == pytest.approx(33.414, rel=1e-3)
    assert analysis["analyst_count"] == 16
    assert analysis["c3po_tp"] == pytest.approx(34.149, rel=1e-3)
    assert analysis["buy_in"] == pytest.approx(19.522, rel=1e-3)
    assert analysis["c3po_tp"] > analysis["price"]
    assert "Goldman Sachs" in analysis["thesis"][2]
