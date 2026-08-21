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
        "Múltiplos de Lucro + EV/EBITDA",
        "Fluxo de Caixa Descontado",
        "Blend Ajustado ao Risco",
        "Momentum de Lucro",
        "Qualidade & Fluxo de Caixa",
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


def test_insider_net_signal_reflects_buy_sell_balance_and_sample_confidence(tmp_path) -> None:
    """Root-caused 2026-08-20: Tatooine Updates insider data (CVM VLMO / Finnhub
    Form 4) was fully ingested but never read back into any scoring formula.
    """
    service = service_for(tmp_path)

    assert service._insider_net_signal(None) == 0.0
    assert service._insider_net_signal({"buy_count": 0, "sell_count": 0, "total_count": 0}) == 0.0

    all_buys_thin_sample = service._insider_net_signal({"buy_count": 1, "sell_count": 0, "total_count": 1})
    all_buys_full_sample = service._insider_net_signal({"buy_count": 4, "sell_count": 0, "total_count": 4})
    all_sells_full_sample = service._insider_net_signal({"buy_count": 0, "sell_count": 4, "total_count": 4})

    assert 0 < all_buys_thin_sample < all_buys_full_sample
    assert all_buys_full_sample == pytest.approx(1.0)
    assert all_sells_full_sample == pytest.approx(-1.0)


def test_institutional_conviction_signal_reflects_accumulation_vs_distribution(tmp_path) -> None:
    """FMP Ultimate Phase 2 (2026-08-20): same role as
    _insider_net_signal but for 13F institutional positioning instead of
    company insiders."""
    service = service_for(tmp_path)

    assert service._institutional_conviction_signal(None) == 0.0
    assert service._institutional_conviction_signal({
        "new_positions": 0, "increased_positions": 0, "reduced_positions": 0, "closed_positions": 0,
    }) == 0.0

    thin_accumulation = service._institutional_conviction_signal(
        {"new_positions": 10, "increased_positions": 0, "reduced_positions": 0, "closed_positions": 0}
    )
    full_accumulation = service._institutional_conviction_signal(
        {"new_positions": 30, "increased_positions": 20, "reduced_positions": 0, "closed_positions": 0}
    )
    full_distribution = service._institutional_conviction_signal(
        {"new_positions": 0, "increased_positions": 0, "reduced_positions": 30, "closed_positions": 20}
    )

    assert 0 < thin_accumulation < full_accumulation
    assert full_accumulation == pytest.approx(1.0)
    assert full_distribution == pytest.approx(-1.0)


def test_fmp_institutional_data_and_batch_skip_the_network_call_without_a_configured_token(tmp_path) -> None:
    service = service_for(tmp_path)
    assert service.settings.fmp_api_token == ""

    assert service._fmp_institutional_data("JPM") is None
    assert service._fmp_institutional_batch(["JPM", "AAPL"]) == {}
    assert service._fmp_institutional_batch([]) == {}


def test_grades_momentum_signal_reflects_upgrade_vs_downgrade_balance(tmp_path) -> None:
    """Root-caused 2026-08-20 (data-source audit): FmpClient.recent_grades()
    shipped in Phase 1 with real broker/date/action data -- exactly what
    motivated the whole day's TP-consensus investigation -- but was never
    wired into any signal. Same -1..1/confidence-scaled shape as the
    insider and institutional signals; "maintain" actions carry no
    directional information and are ignored."""
    service = service_for(tmp_path)

    assert service._grades_momentum_signal(None) == 0.0
    assert service._grades_momentum_signal([{"action": "maintain"}, {"action": "maintain"}]) == 0.0

    thin_upgrades = service._grades_momentum_signal([{"action": "upgrade"}])
    full_upgrades = service._grades_momentum_signal([{"action": "upgrade"}] * 5)
    full_downgrades = service._grades_momentum_signal([{"action": "downgrade"}] * 5)

    assert 0 < thin_upgrades < full_upgrades
    assert full_upgrades == pytest.approx(1.0)
    assert full_downgrades == pytest.approx(-1.0)


def test_fmp_recent_grades_data_and_batch_skip_the_network_call_without_a_configured_token(tmp_path) -> None:
    service = service_for(tmp_path)
    assert service.settings.fmp_api_token == ""

    assert service._fmp_recent_grades_data("JPM") == []
    assert service._fmp_recent_grades_batch(["JPM", "AAPL"]) == {}
    assert service._fmp_recent_grades_batch([]) == {}


def test_sentiment_confidence_adjustment_is_bounded_and_scaled_by_coverage(tmp_path) -> None:
    service = service_for(tmp_path)

    assert service._sentiment_confidence_adjustment(None) == 0.0
    assert service._sentiment_confidence_adjustment({"bullish_percent": 80.0}) == 0.0

    thin_bullish = service._sentiment_confidence_adjustment(
        {"bullish_percent": 100.0, "bearish_percent": 0.0, "articles_last_week": 1},
    )
    full_bullish = service._sentiment_confidence_adjustment(
        {"bullish_percent": 100.0, "bearish_percent": 0.0, "articles_last_week": 10},
    )
    full_bearish = service._sentiment_confidence_adjustment(
        {"bullish_percent": 0.0, "bearish_percent": 100.0, "articles_last_week": 10},
    )

    assert 0 < thin_bullish < full_bullish
    assert full_bullish == pytest.approx(5.0)
    assert full_bearish == pytest.approx(-5.0)


def test_analyze_lowers_risk_and_raises_confidence_on_bullish_insider_and_news_signal(tmp_path) -> None:
    """End-to-end: heavy insider buying should measurably lower risk_score
    (governance signal), and strongly bullish, well-covered news sentiment
    should measurably raise confidence -- both bounded, neither swamping the
    rest of each formula."""
    service = service_for(tmp_path)
    baseline = sample_analysis(service)

    bullish = service._analyze(
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
            "analystRatings": {"strongBuy": 12, "buy": 18, "hold": 15, "sell": 2, "strongSell": 1},
            "returnOnEquity": 0.34,
            "profitMargins": 0.36,
            "revenueGrowthAnnual": 0.15,
            "earningsGrowthAnnual": 0.17,
            "beta": 0.95,
        },
        insider_activity={"buy_count": 5, "sell_count": 0, "total_count": 5},
        news_sentiment={"bullish_percent": 90.0, "bearish_percent": 10.0, "articles_last_week": 12},
    )

    assert bullish["risk_score"] < baseline["risk_score"]
    assert bullish["confidence"] > baseline["confidence"]
    # Bounded: a maximally bullish signal still can't move risk more than the
    # documented swing, or push confidence past the formula's own ceiling.
    assert baseline["risk_score"] - bullish["risk_score"] <= 8.0
    assert bullish["confidence"] <= 94


def test_analyze_lowers_risk_on_institutional_accumulation(tmp_path) -> None:
    """FMP Ultimate Phase 2: end-to-end, heavy institutional accumulation
    (13F new/increased positions outweighing reduced/closed) should
    measurably lower risk_score, same role as the insider-buying signal,
    bounded by INSTITUTIONAL_RISK_MAX_SWING."""
    service = service_for(tmp_path)
    baseline = sample_analysis(service)

    accumulating = service._analyze(
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
            "analystRatings": {"strongBuy": 12, "buy": 18, "hold": 15, "sell": 2, "strongSell": 1},
            "returnOnEquity": 0.34,
            "profitMargins": 0.36,
            "revenueGrowthAnnual": 0.15,
            "earningsGrowthAnnual": 0.17,
            "beta": 0.95,
        },
        institutional_positions={
            "new_positions": 200, "increased_positions": 300,
            "reduced_positions": 20, "closed_positions": 10,
        },
    )

    assert accumulating["risk_score"] < baseline["risk_score"]
    assert baseline["risk_score"] - accumulating["risk_score"] <= 8.0


def test_dcf_value_uses_capm_discount_rate_for_us_and_flat_rate_elsewhere(tmp_path) -> None:
    """Root-caused 2026-08-20 (TP methodology audit): the US DCF used one
    fixed 10.5% discount rate for every stock regardless of risk, unlike
    B3's per-security beta/Selic-derived WACC. Now a real CAPM-style rate
    for US: risk_free + beta * equity_risk_premium -- a higher-beta
    (riskier) stock gets a lower DCF TP than a lower-beta one with
    identical cash flows, and a higher risk-free rate also lowers it. B3
    keeps its own flat rate, untouched by beta/risk_free_rate.
    """
    service = service_for(tmp_path)
    common = dict(
        free_cashflow=10_000_000_000.0, shares=1_000_000_000.0,
        growth=0.08, market="US", price=100.0, fallback_eps=5.0,
    )

    low_beta_tp = service._dcf_value(**common, beta=0.8, risk_free_rate=0.04)
    high_beta_tp = service._dcf_value(**common, beta=1.6, risk_free_rate=0.04)
    higher_rate_tp = service._dcf_value(**common, beta=0.8, risk_free_rate=0.06)

    assert high_beta_tp < low_beta_tp
    assert higher_rate_tp < low_beta_tp

    b3_common = {**common, "market": "B3"}
    b3_tp_a = service._dcf_value(**b3_common, beta=0.8, risk_free_rate=0.04)
    b3_tp_b = service._dcf_value(**b3_common, beta=1.6, risk_free_rate=0.09)
    assert b3_tp_a == b3_tp_b


def test_dcf_value_falls_back_to_a_fixed_rate_without_a_threaded_risk_free_rate(tmp_path) -> None:
    """_analyze/_dcf_value must stay network-free and deterministic by
    default (risk_free_rate is fetched once by the caller, not inside the
    pure valuation function) -- omitting it should use the documented
    fallback constant, not raise or silently use 0.
    """
    from app.one_pager import US_RISK_FREE_FALLBACK_RATE

    service = service_for(tmp_path)
    common = dict(
        free_cashflow=10_000_000_000.0, shares=1_000_000_000.0,
        growth=0.08, market="US", price=100.0, fallback_eps=5.0, beta=1.0,
    )

    without_rate = service._dcf_value(**common)
    with_fallback_rate_explicit = service._dcf_value(**common, risk_free_rate=US_RISK_FREE_FALLBACK_RATE)

    assert without_rate == with_fallback_rate_explicit


def test_us_risk_free_rate_caches_and_falls_back_when_the_feed_is_unavailable(tmp_path) -> None:
    service = service_for(tmp_path)

    first = service._us_risk_free_rate()
    service._us_risk_free_cache = (
        service._us_risk_free_cache[0], 0.099,
    )
    second = service._us_risk_free_rate()

    assert 0.02 <= first <= 0.08
    assert second == 0.099  # cache hit, no re-fetch


def test_fmp_consensus_data_and_batch_skip_the_network_call_without_a_configured_token(tmp_path) -> None:
    service = service_for(tmp_path)
    assert service.settings.fmp_api_token == ""

    assert service._fmp_consensus_data("JPM") == (None, None)
    assert service._fmp_consensus_batch(["JPM", "AAPL"]) == {}
    assert service._fmp_consensus_batch([]) == {}


def test_valuation_profile_does_not_pool_banks_with_diversified_financials() -> None:
    """Root-caused 2026-08-20 (production incident): the bare "financial"
    keyword matched EODHD's sector name for the whole Financial Services
    sector, so JPMorgan's peer-median basket got averaged in with Visa/
    Mastercard (Credit Services), CME/Nasdaq (Financial Data & Stock
    Exchanges), and BlackRock (Asset Management) -- high-multiple
    diversified financials, not banks -- pushing bank TPs away from
    consensus for every bank/insurer in the US universe once this went
    live in production. "bank"/"insurance" alone already catch every real
    bank and insurer (their EODHD industry values are literally
    "Banks-...", "Insurance-..."), so the broader "financial" term was
    pure risk with no coverage benefit.
    """
    assert OnePagerService._valuation_profile("Financial Services", "Banks-Diversified") == "financial"
    assert OnePagerService._valuation_profile("Financial Services", "Insurance-Life") == "financial"
    assert OnePagerService._valuation_profile("Financial Services", "Credit Services") != "financial"
    assert OnePagerService._valuation_profile("Financial Services", "Financial Data & Stock Exchanges") != "financial"
    assert OnePagerService._valuation_profile("Financial Services", "Asset Management") != "financial"


def test_valuation_profile_does_not_pool_electrical_equipment_with_utilities() -> None:
    """Same root cause as the financial-pooling bug above: the bare
    "electric" keyword matched "Electrical Equipment & Parts" (an
    Industrials sub-industry), not just real electric utilities -- whose
    EODHD industry values already say "Utilities-..." and are caught by
    "utility"/"utilities" alone."""
    assert OnePagerService._valuation_profile("Utilities", "Utilities-Regulated Electric") == "utilities"
    assert OnePagerService._valuation_profile("Industrials", "Electrical Equipment & Parts") != "utilities"


def test_us_peer_medians_requires_a_minimum_sample_per_profile(tmp_path) -> None:
    """Root-caused 2026-08-20 (TP methodology audit): fair_pe/fair_ev_ebitda
    used a fixed constant per profile with no live peer comparison, unlike
    B3's sector-median benchmarking. This mirrors B3's minimum-peer-count
    discipline: a profile bucket only gets a live median once it clears
    US_PEER_MEDIAN_MIN_SAMPLE peers, otherwise the caller falls back to the
    documented constants.
    """
    service = service_for(tmp_path)
    technology_funds = {
        f"T{i}": {"sector": "Technology", "industry": "Software", "trailingPE": pe, "enterpriseToEbitda": ev}
        for i, (pe, ev) in enumerate([(20.0, 14.0), (24.0, 16.0), (28.0, 18.0), (32.0, 20.0)])
    }
    thin_financial_funds = {
        "F0": {"sector": "Banks", "industry": "Regional Banks", "trailingPE": 10.0, "enterpriseToEbitda": 8.0},
    }

    medians = service._us_peer_medians({**technology_funds, **thin_financial_funds})

    assert medians["technology"]["pe"] == 26.0
    assert medians["technology"]["ev_ebitda"] == 17.0
    assert "financial" not in medians  # only 1 sample, below US_PEER_MEDIAN_MIN_SAMPLE


def test_us_peer_medians_ignores_implausible_multiples(tmp_path) -> None:
    service = service_for(tmp_path)
    funds = {
        f"T{i}": {"sector": "Technology", "industry": "Software", "trailingPE": pe, "enterpriseToEbitda": 15.0}
        for i, pe in enumerate([20.0, 24.0, 28.0, 32.0])
    }
    funds["OUTLIER"] = {
        "sector": "Technology", "industry": "Software",
        "trailingPE": 500.0, "enterpriseToEbitda": 15.0,  # implausible, must be excluded
    }

    medians = service._us_peer_medians(funds)

    assert medians["technology"]["pe"] == 26.0


def test_us_peer_medians_rejects_a_bucket_too_dispersed_to_be_coherent(tmp_path) -> None:
    """Root-caused 2026-08-20 (production incident): the "financial" keyword
    matched EODHD's whole Financial Services sector name, so JPM's peer
    basket got pooled with high-multiple diversified financials (Visa/
    Mastercard/CME/BlackRock) instead of just banks -- inflating fair_pe for
    every bank in production before this was caught and the taxonomy fixed
    (see test_valuation_profile_does_not_pool_banks_with_diversified_financials).
    This is the general safety net for that same failure mode: even if a
    future taxonomy gap pools two industries with very different multiple
    regimes into one bucket, a peer sample whose quartile spread is too wide
    to be a coherent comparison group gets rejected and falls back to the
    documented constant, instead of quietly producing a distorted median.
    Uses two industries that both fall through to "general" (neither matches
    any _valuation_profile keyword) so the taxonomy fix above doesn't
    already separate them -- isolating the dispersion guard itself.
    """
    service = service_for(tmp_path)
    low_multiple = {
        f"LOW{i}": {"sector": "Communication Services", "industry": "Telecom Services", "trailingPE": pe, "enterpriseToEbitda": 8.0}
        for i, pe in enumerate([9.0, 10.0, 11.0, 12.0])
    }
    high_multiple = {
        f"HIGH{i}": {"sector": "Consumer Cyclical", "industry": "Auto Manufacturers", "trailingPE": pe, "enterpriseToEbitda": 8.0}
        for i, pe in enumerate([28.0, 30.0, 32.0, 34.0])
    }

    medians = service._us_peer_medians({**low_multiple, **high_multiple})

    assert "pe" not in medians.get("general", {})


def test_analyze_uses_live_peer_medians_over_the_fallback_constants(tmp_path) -> None:
    service = service_for(tmp_path)
    fundamentals = {
        "companyName": "Test Corp",
        "sector": "Technology",
        "industry": "Software",
        "marketCap": 5_000_000_000,
        "trailingEps": 5.0,
        "forwardEps": 5.5,
        "sharesOutstanding": 500_000_000,
        "beta": 1.0,
    }
    quote = {"price": 100.0, "currency": "USD", "change_percent": 0.5, "as_of": datetime.now(timezone.utc)}

    without_peers = service._analyze("TEST", "US", quote, fundamentals, risk_free_rate=0.04)
    with_low_peer_pe = service._analyze(
        "TEST", "US", quote, fundamentals, risk_free_rate=0.04,
        peer_medians={"technology": {"pe": 8.0, "ev_ebitda": 6.0}},
    )

    assert with_low_peer_pe["c3po_tp"] < without_peers["c3po_tp"]


def test_us_consensus_weight_scales_with_analyst_breadth_and_zeroes_without_coverage() -> None:
    assert OnePagerService._us_consensus_weight(None, 20) == 0.0
    assert OnePagerService._us_consensus_weight(100.0, 0) == 0.0
    assert OnePagerService._us_consensus_weight(100.0, 1) == pytest.approx(0.215)
    assert OnePagerService._us_consensus_weight(100.0, 10) == pytest.approx(0.35)
    assert OnePagerService._us_consensus_weight(100.0, 27) == pytest.approx(0.35)  # clamped, not unbounded


def test_resolve_us_consensus_prefers_the_most_recent_well_supported_fmp_window() -> None:
    """Root-caused 2026-08-20: EODHD's targetMeanPrice carries no update
    date, and its numberOfAnalystOpinions counts EPS estimators, not
    necessarily the analysts behind the price target -- confirmed
    divergent for most of a 50-symbol live sample. FMP Ultimate gives
    broker-level, dated price targets; recency (last month, then quarter)
    is preferred over FMP's own all-time consensus for the same reason
    EODHD's staleness was the problem in the first place.
    """
    fmp_consensus = {"consensus": 373.64, "median": 370.0, "high": 420.0, "low": 305.0}
    fmp_summary_fresh = {"last_month_count": 5, "last_month_avg": 388.33, "last_quarter_count": 12, "last_quarter_avg": 380.0}
    fmp_summary_thin_month = {"last_month_count": 1, "last_month_avg": 500.0, "last_quarter_count": 12, "last_quarter_avg": 380.0}
    fmp_summary_empty = {"last_month_count": 0, "last_month_avg": None, "last_quarter_count": 0, "last_quarter_avg": None}

    assert OnePagerService._resolve_us_consensus(fmp_consensus, fmp_summary_fresh, 350.0, 40) == (388.33, 5, "fmp_last_month")
    assert OnePagerService._resolve_us_consensus(fmp_consensus, fmp_summary_thin_month, 350.0, 40) == (380.0, 12, "fmp_last_quarter")
    assert OnePagerService._resolve_us_consensus(fmp_consensus, fmp_summary_empty, 350.0, 40) == (373.64, 40, "fmp_all_time")
    assert OnePagerService._resolve_us_consensus(None, None, 350.0, 40) == (350.0, 40, "eodhd")
    assert OnePagerService._resolve_us_consensus(None, fmp_summary_empty, 350.0, 40) == (350.0, 40, "eodhd")


def test_analyze_uses_fmp_consensus_over_eodhd_when_available(tmp_path) -> None:
    service = service_for(tmp_path)
    fundamentals = {
        "companyName": "Test Bank", "sector": "Financial Services", "industry": "Banks-Diversified",
        "marketCap": 400_000_000_000, "trailingEps": 18.0, "forwardEps": 19.0,
        "sharesOutstanding": 2_800_000_000, "beta": 1.1, "returnOnEquity": 0.18,
        "targetMeanPrice": 500.0, "numberOfAnalystOpinions": 40,
    }
    quote = {"price": 357.26, "currency": "USD", "change_percent": 0.3, "as_of": datetime.now(timezone.utc)}

    result = service._analyze(
        "TESTBANK", "US", quote, fundamentals, risk_free_rate=0.042,
        fmp_summary={"last_month_count": 5, "last_month_avg": 373.64, "last_quarter_count": 12, "last_quarter_avg": 380.0},
    )

    assert result["consensus_tp"] == pytest.approx(373.64)
    assert result["consensus_source"] == "fmp_last_month"
    assert result["analyst_count"] == 5


def test_analyze_skips_ev_ebitda_and_dcf_for_the_financial_profile(tmp_path) -> None:
    """Root-caused 2026-08-20 (production incident): live-audited via
    sys.settrace on JPM's real fundamentals, enterprise_tp came out to
    $1,096.77 against a $357.26 price -- because EV/EBITDA-minus-net-debt
    isn't a valid framework for banks. JPM's $1.24T "total debt" is
    overwhelmingly customer deposits and borrowings, the raw material of
    the banking business, not financial leverage -- no real equity
    analyst uses EV/EBITDA to value a bank. dcf_tp ($578.02) was the
    second-largest distortion for the same underlying reason: a bank's
    reported "free cash flow" is dominated by financing/investing
    activity (loan originations, deposit changes), not owner earnings.
    Both are now skipped for the financial profile, using this near-exact
    reproduction of JPM's real inputs.
    """
    service = service_for(tmp_path)
    fundamentals = {
        "companyName": "JPM", "sector": "Financial Services", "industry": "Banks-Diversified",
        "marketCap": 950_000_000_000, "trailingEps": 24.0, "forwardEps": 25.007,
        "sharesOutstanding": 2_658_186_195, "beta": 0.977, "returnOnEquity": 0.1779,
        "profitMargins": 0.3492, "operatingMargins": 0.5039,
        "revenueGrowthAnnual": 0.304, "earningsGrowthAnnual": 0.469,
        "bookValue": 133.007, "ebitda": 93_160_000_000, "totalDebt": 1_237_871_000_000,
        "totalCash": 262_254_800_000, "freeCashflow": 86_115_000_000,
        "targetMeanPrice": 388.33, "numberOfAnalystOpinions": 3,
    }
    quote = {"price": 357.26, "currency": "USD", "change_percent": 0.3, "as_of": datetime.now(timezone.utc)}

    result = service._analyze("JPM", "US", quote, fundamentals, risk_free_rate=0.042)

    # Before this fix, Morgan Stanley (72% dcf_tp weight) alone hit $555+
    # and enterprise-heavy methods blew past $1,000; every method should
    # now be a plausible multiple of price, not 2-3x it.
    assert all(value < 2.0 * quote["price"] for value in result["methods"].values())
    assert result["c3po_tp"] < 1.5 * quote["price"]


def test_analyze_pulls_the_final_tp_toward_a_well_covered_consensus(tmp_path) -> None:
    """Root-caused 2026-08-20 (production incident): JPM's blended TP came
    out $625.49 against a real 27-analyst consensus of $374.57 (67% too
    high) -- because consensus only entered each of the 5 internal
    "methods" (Goldman Sachs/Morgan Stanley/etc, fictional labels for our
    own model, not real bank data) diluted at 10-25% weight, with nothing
    pulling the final number back toward the one real, externally-sourced
    signal we have. Mirrors B3's _consensus_weight: real analyst consensus
    now gets an explicit final blend (20-35%, scaled by analyst coverage),
    applied once after the internal model instead of diluted inside it.
    """
    service = service_for(tmp_path)
    fundamentals = {
        "companyName": "Test Bank",
        "sector": "Financial Services",
        "industry": "Banks-Diversified",
        "marketCap": 400_000_000_000,
        "trailingEps": 18.0,
        "forwardEps": 19.0,
        "sharesOutstanding": 2_800_000_000,
        "beta": 1.1,
        "returnOnEquity": 0.18,
    }
    quote = {"price": 357.26, "currency": "USD", "change_percent": 0.3, "as_of": datetime.now(timezone.utc)}

    without_consensus = service._analyze("TESTBANK", "US", quote, fundamentals, risk_free_rate=0.042)
    with_consensus = service._analyze(
        "TESTBANK", "US", quote,
        {**fundamentals, "targetMeanPrice": 374.57, "numberOfAnalystOpinions": 27},
        risk_free_rate=0.042,
    )

    assert abs(with_consensus["c3po_tp"] - 374.57) < abs(without_consensus["c3po_tp"] - 374.57)
