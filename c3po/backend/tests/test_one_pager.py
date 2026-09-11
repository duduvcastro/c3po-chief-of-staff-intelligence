import json
import statistics
from datetime import datetime, timedelta, timezone

import pytest

from app.config import Settings
from app.database import Database
from app.foreign_listings import normalize_foreign_fundamentals, policy_for
from app.market_data.service import MarketDataService
from app.market_data.http import MarketDataRequestError
from app.one_pager import OnePagerGenerationError, OnePagerService
from app.one_pager_pdf import PremiumOnePagerRenderer
from app.schemas import OnePagerReport
from app.valuation_policy import METHODOLOGY_VERSION


def service_for(tmp_path):
    settings = Settings(
        brapi_token="brapi-test",
        eodhd_api_token="eodhd-test",
        one_pager_output_dir=tmp_path,
        auth_cookie_secure=False,
    )
    database = Database(settings)
    service = OnePagerService(settings, database, MarketDataService(settings, database), output_dir=tmp_path)
    with_official(service)  # Passo 0 (V3.2 rev 7 §7-bis): the One Pager never computes a TP; tests inject the official row
    return service


DEFAULT_OFFICIAL_ROW = {"our_tp": 560.0, "buy_in": 470.0, "tp_source": "official_blend_v1",
                        "generation_id": "gen-test", "official_cycle_id": "cycle-test",
                        # the rest of the served record's stamp (F393-6), exactly as `_served` names it
                        "tp_source_version": "v1-test", "official_session_date": "2026-09-04",
                        "prediction_instant": "2026-09-04T21:05:00+00:00",
                        "official_row_sha256": "1a2b3c4d" + "0" * 56}

# analysis/report key -> served row key (the report renames generation_id only)
FULL_STAMP_KEYS = (("tp_source", "tp_source"), ("official_generation_id", "generation_id"),
                   ("official_cycle_id", "official_cycle_id"), ("tp_source_version", "tp_source_version"),
                   ("official_session_date", "official_session_date"), ("prediction_instant", "prediction_instant"),
                   ("official_row_sha256", "official_row_sha256"))


def with_official(service, **overrides):
    """What the official selection would return for any symbol in these tests (see test_valuation_official.py for
    the real resolution path). Returns the row installed."""
    row = {**DEFAULT_OFFICIAL_ROW, **overrides}
    service._official_valuation = lambda symbol, market: dict(row)  # type: ignore[method-assign]
    return row


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
    with_official(service, our_tp=34.149, buy_in=19.522)  # the official producer carries the primary-listing bridge values
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
    assert tuple(analysis["methods"]) == (
        "Múltiplos de Lucro + EV/EBITDA",
        "Fluxo de Caixa Descontado",
        "Blend Ajustado ao Risco",
        "Momentum de Lucro",
        "Qualidade & Fluxo de Caixa",
    )
    assert not {
        "Goldman Sachs",
        "Morgan Stanley",
        "Bridgewater",
        "JPMorgan",
        "BlackRock",
    }.intersection(analysis["methods"])
    assert analysis["method_estimate_registered_on"] == "2026-08-17"
    assert "estimativas internas registradas em 17/08/2026" in analysis["source"]
    assert "Goldman Sachs" in analysis["thesis"][2]

    foreign_policy = fundamentals["foreignListingPolicy"]
    assert "methodTargets" not in foreign_policy
    assert foreign_policy["internalMethodTargetsRegisteredOn"] == "2026-08-17"

    undated_fundamentals = dict(fundamentals)
    undated_policy = dict(foreign_policy)
    undated_policy.pop("internalMethodTargetsRegisteredOn")
    undated_fundamentals["foreignListingPolicy"] = undated_policy
    with pytest.raises(OnePagerGenerationError, match="não têm data de registro válida"):
        service._analyze(
            "MHVYF",
            "US",
            {"price": 26.84, "currency": "USD", "change_percent": -0.56},
            undated_fundamentals,
        )


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

    # the internal framework reacts to live peer medians (diagnostic); the TP shown is the official one in both cases
    assert with_low_peer_pe["internal_framework_tp"] < without_peers["internal_framework_tp"]
    assert with_low_peer_pe["c3po_tp"] == without_peers["c3po_tp"] == DEFAULT_OFFICIAL_ROW["our_tp"]


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
    with_official(service, our_tp=400.0, buy_in=330.0)
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
    assert all(value < 2.0 * quote["price"] for value in result["internal_framework_methods"].values())
    assert result["c3po_tp"] < 1.5 * quote["price"]


def test_analyze_pulls_the_final_tp_toward_a_well_covered_consensus(tmp_path) -> None:
    """Root-caused 2026-08-20 (production incident): JPM's blended TP came
    out $625.49 against a real 27-analyst consensus of $374.57 (67% too
    high). Real analyst consensus now gets an explicit final blend (20-35%,
    scaled by analyst coverage) after the internal model. It must not also
    enter the five internal methods, otherwise the same external evidence is
    counted twice in c3po_tp and the downstream R2D2 pre-trade rank.
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

    # Valuation V3.2 rev 7 (P1/P2): the consensus never enters the TP shown — it remains a diagnostic weight — and the
    # internal framework is unchanged by it; the TP is the official one in both cases.
    assert with_consensus["internal_framework_methods"] == pytest.approx(without_consensus["internal_framework_methods"])
    assert with_consensus["consensus_weight_diagnostic"] == pytest.approx(service._us_consensus_weight(374.57, 27))
    assert with_consensus["consensus_weight_diagnostic"] > 0 and without_consensus["consensus_weight_diagnostic"] == 0
    assert with_consensus["c3po_tp"] == without_consensus["c3po_tp"] == DEFAULT_OFFICIAL_ROW["our_tp"]
    assert with_consensus["tp_source"] == "official_blend_v1" and with_consensus["official_generation_id"] == "gen-test"
    # F393-6: the full stamp of the served record, not only producer/generation
    for analysis_key, row_key in FULL_STAMP_KEYS:
        assert with_consensus[analysis_key] == DEFAULT_OFFICIAL_ROW[row_key]


def test_consensus_does_not_leak_into_internal_methods_without_fundamentals(tmp_path) -> None:
    service = service_for(tmp_path)
    quote = {"price": 100.0, "currency": "USD", "change_percent": 0.0, "as_of": datetime.now(timezone.utc)}
    fundamentals = {
        "companyName": "Sparse Coverage Inc",
        "sector": "Financial Services",
        "industry": "Banks-Diversified",
    }

    without_consensus = service._analyze("SPARSE", "US", quote, fundamentals)
    with_consensus = service._analyze(
        "SPARSE",
        "US",
        quote,
        {**fundamentals, "targetMeanPrice": 140.0, "numberOfAnalystOpinions": 10},
    )

    assert with_consensus["internal_framework_methods"] == pytest.approx(without_consensus["internal_framework_methods"])
    assert with_consensus["internal_framework_tp"] == pytest.approx(without_consensus["internal_framework_tp"])
    assert with_consensus["c3po_tp"] == DEFAULT_OFFICIAL_ROW["our_tp"]  # the consensus never enters the TP (rev 7, P1)


def test_v2_shadow_band_renders_without_replacing_the_official_tp(tmp_path) -> None:
    service = service_for(tmp_path)
    analysis = sample_analysis(service)
    analysis["v2_shadow"] = {
        "v2_tp": 512.34,
        "v2_upside_percent": 8.7,
        "internal_divergence_vs_consensus": 0.121,
        "final_divergence_vs_consensus": 0.079,
        "model_count": 4,
        "attribution_model": "reverse_dcf",
        "low_conviction": False,
    }
    start = datetime(2025, 8, 5, tzinfo=timezone.utc)
    history = [
        {
            "date": (start + timedelta(days=round(index * 365 / 260))).date().isoformat(),
            "close": 400 + index * 0.3,
        }
        for index in range(261)
    ]

    report = service._write_report(analysis, history)

    assert (tmp_path / report.filename).read_bytes().startswith(b"%PDF")
    # The official TP is still the V1 engine's -- the shadow is informational.
    assert report.c3po_tp == pytest.approx(analysis["c3po_tp"], rel=1e-3)


def test_valuation_v2_shadow_lookup_reads_the_persisted_snapshot(tmp_path) -> None:
    service = service_for(tmp_path)
    methodology_id = service.database.ensure_methodology_version("v2_shadow_test", 1, {}, "test")
    service.database.save_analysis_snapshot(
        "valuation_v2_shadow",
        "NASDAQ_V2_SHADOW",
        methodology_id,
        {},
        {"results": {"MSFT": {"v2_tp": 501.0, "low_conviction": False}}},
        datetime.now(timezone.utc),
    )
    service.database.save_analysis_snapshot(
        "valuation_v2_shadow",
        "B3_V2_SHADOW",
        methodology_id,
        {},
        {"results": {"MSFT": {"v2_tp": 99.0, "low_conviction": True}}},
        datetime.now(timezone.utc),
    )

    assert service._valuation_v2_shadow("msft", "US") == {
        "v2_tp": 501.0, "low_conviction": False
    }
    assert service._valuation_v2_shadow("msft", "B3") == {
        "v2_tp": 99.0, "low_conviction": True
    }
    assert service._valuation_v2_shadow("UNKNOWN", "US") is None


def test_generate_refuses_without_an_official_tp_and_never_computes_one(tmp_path) -> None:
    # Valuation V3.2 rev 7 §7-bis (Passo 0): without an official row there is no One Pager — no local blend, no fallback.
    service = service_for(tmp_path)
    service._official_valuation = lambda symbol, market: None  # type: ignore[method-assign]
    with pytest.raises(OnePagerGenerationError, match="TP oficial"):
        sample_analysis(service)


def test_report_json_and_pdf_carry_the_full_official_stamp(tmp_path) -> None:
    """F393-6 (V3.2 rev 7 §7-bis, I-TP3): the session, the record's instant, the record hash and the producer version
    of the served number must not be lost between the official selection and the One Pager's JSON, sidecar and PDF."""
    service = service_for(tmp_path)
    analysis = sample_analysis(service)
    for analysis_key, row_key in FULL_STAMP_KEYS:
        assert analysis[analysis_key] == DEFAULT_OFFICIAL_ROW[row_key]

    rendered: list[dict] = []
    original_render = service._render_pdf

    def capture_render(path, data, history, generated_at):
        rendered.append(dict(data))
        original_render(path, data, history, generated_at)

    service._render_pdf = capture_render  # type: ignore[method-assign]
    history = [{"date": (datetime(2025, 8, 5, tzinfo=timezone.utc) + timedelta(days=round(index * 365 / 260))).date().isoformat(),
                "close": 400 + index * 0.3} for index in range(261)]

    report = service._write_report(analysis, history)

    # the dict the PDF renderer receives carries the whole stamp...
    assert len(rendered) == 1
    for analysis_key, row_key in FULL_STAMP_KEYS:
        assert rendered[0][analysis_key] == DEFAULT_OFFICIAL_ROW[row_key]
    # ...the report (the API's JSON) too...
    assert report.tp_source == "official_blend_v1" and report.official_generation_id == "gen-test"
    assert report.official_cycle_id == "cycle-test" and report.tp_source_version == "v1-test"
    assert report.official_session_date == "2026-09-04"
    assert report.prediction_instant == datetime(2026, 9, 4, 21, 5, tzinfo=timezone.utc)
    assert report.official_row_sha256 == DEFAULT_OFFICIAL_ROW["official_row_sha256"]
    # ...and the persisted sidecar next to the PDF round-trips it
    sidecar = (tmp_path / report.filename).with_suffix(".json").read_text(encoding="utf-8")
    persisted = json.loads(sidecar)
    for key in ("tp_source", "official_generation_id", "official_cycle_id", "tp_source_version",
                "official_session_date", "official_row_sha256"):
        assert persisted[key] == getattr(report, key)
    assert OnePagerReport.model_validate_json(sidecar).prediction_instant == report.prediction_instant
    # the PDF's NOSSO TP line shows the session and the record hash prefix on the same line as producer/generation
    label = PremiumOnePagerRenderer._official_stamp_label(rendered[0])
    assert "official_blend_v1 · ger. gen-test · sessão 2026-09-04 · reg. 1a2b3c4d" in label
    assert "\n" not in label


def test_pdf_stamp_label_degrades_when_the_stamp_is_absent() -> None:
    label = PremiumOnePagerRenderer._official_stamp_label({"upside_percent": 12.0})
    assert label == "+12.0% upside · sem fonte oficial · ger. - · sessão - · reg. -"
    assert PremiumOnePagerRenderer._official_stamp_lines({"upside_percent": 12.0}) == ("+12.0% upside", "sem fonte oficial · ger. -", "sessão - · reg. -")


def test_pdf_official_stamp_is_drawn_in_lines_that_fit_the_summary_column(tmp_path, monkeypatch) -> None:
    """F393-6 (rev 5): the one-line stamp measured 142 pt in the 82 pt NOSSO TP column. The PDF now draws it as three
    short lines at one size; every line actually drawn on the canvas is measured (``stringWidth``) against the width
    the band hands the layout, and a producer name that cannot fit even at the minimum size is cut with an ellipsis."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas as pdf_canvas

    from app.one_pager_pdf import STAMP_FONT, STAMP_FONT_MAX, STAMP_FONT_MIN, STAMP_LINES

    service = service_for(tmp_path)
    analysis = sample_analysis(service)
    band_widths: list[float] = []
    original_band = PremiumOnePagerRenderer._valuation_summary_band

    def spy_band(self, pdf, x, y, w, h, data):
        band_widths.append(w)
        return original_band(self, pdf, x, y, w, h, data)

    drawn: list[tuple[str, str, float]] = []
    original_draw = pdf_canvas.Canvas.drawCentredString

    def spy_draw(self, x, y, text, *args, **kwargs):
        drawn.append((text, self._fontname, self._fontsize))
        return original_draw(self, x, y, text, *args, **kwargs)

    monkeypatch.setattr(PremiumOnePagerRenderer, "_valuation_summary_band", spy_band)
    monkeypatch.setattr(pdf_canvas.Canvas, "drawCentredString", spy_draw)
    history = [{"date": (datetime(2025, 8, 5, tzinfo=timezone.utc) + timedelta(days=round(index * 365 / 260))).date().isoformat(),
                "close": 400 + index * 0.3} for index in range(261)]

    service._write_report(analysis, history)

    # the band was drawn once, at the width the page geometry gives it; one column is a third of it
    assert len(band_widths) == 1
    slot = band_widths[0] / 3
    assert slot == pytest.approx(PremiumOnePagerRenderer.summary_slot_width())
    assert slot < 90  # the column the auditor measured (82 pt)
    width = slot - 6  # what the band hands the layout
    lines = PremiumOnePagerRenderer._official_stamp_lines(analysis)
    assert len(lines) == STAMP_LINES
    assert lines[1] == "official_blend_v1 · ger. gen-test" and lines[2] == "sessão 2026-09-04 · reg. 1a2b3c4d"
    # the one-line label of rev 4 does not fit the column even at the minimum size — hence the lines
    assert stringWidth(PremiumOnePagerRenderer._official_stamp_label(analysis), STAMP_FONT, STAMP_FONT_MIN) > width
    # every stamp line actually drawn on the canvas fits the column, at one legible size, nothing clipped
    drawn_stamp = [(text, font, size) for text, font, size in drawn if text in lines]
    assert [text for text, _, _ in drawn_stamp] == list(lines)
    assert {font for _, font, _ in drawn_stamp} == {STAMP_FONT} and len({size for _, _, size in drawn_stamp}) == 1
    for text, font, size in drawn_stamp:
        assert STAMP_FONT_MIN <= size <= STAMP_FONT_MAX
        assert stringWidth(text, font, size) <= width
    # a producer name that cannot fit at the minimum size is cut with an ellipsis rather than drawn past the column
    overflow = PremiumOnePagerRenderer._official_stamp_lines({**analysis, "tp_source": "x" * 80})
    clipped = PremiumOnePagerRenderer._stamp_layout(overflow, width)
    assert clipped[1][1] == STAMP_FONT_MIN and clipped[1][0].endswith("…")
    assert all(stringWidth(text, STAMP_FONT, size) <= width for text, size in clipped)


def test_the_engine_mirror_of_the_producers_entry_hurdle_reproduces_its_buy_in_bit_for_bit(tmp_path) -> None:
    """Passo 1: the US screener derives the internal buy-in with ``official_entry_discount_v1`` — the literal mirror of
    the entry hurdle the pinned One Pager applies in producer role. Proved on the producer itself: the engine's
    ``official_buy_in_v1(methods, mirror(risk, confidence), c3po_tp)`` IS ``analysis["buy_in"]``, with a real consensus in
    the blend (weight > 0), so the internal buy-in is the same rule applied to the internal TP."""
    from app.valuation_official_engine import official_blend_v1, official_buy_in_v1, official_entry_discount_v1

    service = service_for(tmp_path)
    analysis = service._analyze(
        "MSFT", "US",
        {"price": 500.0, "currency": "USD", "change_percent": 1.25, "as_of": datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc)},
        {"companyName": "Microsoft Corporation", "sector": "Technology", "marketCap": 3_700_000_000_000, "trailingPE": 31.0, "forwardPE": 27.0,
         "enterpriseToEbitda": 22.0, "pegRatio": 1.8, "trailingEps": 16.0, "forwardEps": 18.5, "bookValue": 42.0, "sharesOutstanding": 7_430_000_000,
         "freeCashflow": 92_000_000_000, "ebitda": 150_000_000_000, "totalDebt": 80_000_000_000, "totalCash": 90_000_000_000,
         "targetMeanPrice": 610.0, "numberOfAnalystOpinions": 48, "returnOnEquity": 0.34, "profitMargins": 0.36, "revenueGrowthAnnual": 0.15,
         "earningsGrowthAnnual": 0.17, "beta": 0.95},
        role="producer",
    )
    assert analysis["analysis_role"] == "producer" and analysis["consensus_tp"] and analysis["consensus_weight_diagnostic"] > 0
    internal_tp = statistics.mean(analysis["methods"].values())
    assert analysis["internal_framework_tp"] == internal_tp and analysis["c3po_tp"] == official_blend_v1(internal_tp, analysis["consensus_tp"], analysis["consensus_weight_diagnostic"])
    assert analysis["c3po_tp"] != internal_tp  # the consensus is inside the blend: the internal buy-in cannot be read off the row without the rule
    discount = official_entry_discount_v1("US", analysis["risk_score"], analysis["confidence"])
    assert discount == 0.12 + analysis["risk_score"] / 100 * 0.11 + (100 - analysis["confidence"]) / 100 * 0.06
    assert official_buy_in_v1(analysis["methods"].values(), discount, analysis["c3po_tp"]) == analysis["buy_in"]  # exact, not approx
    internal_buy_in = official_buy_in_v1(analysis["methods"].values(), discount, internal_tp)
    assert internal_buy_in == statistics.mean(value / (1 + discount) for value in analysis["methods"].values())  # the 90 % cap never binds: discount ≥ 0.14 > 1/9
    assert 0 < internal_buy_in < internal_tp
    # a fact of the producer's rule, not a shortcut: the discounted method mean does not depend on the TP, so the internal buy-in
    # equals the blend's whenever the blend's 90 % cap does not bind (here), and is HIGHER than the blend's when it does —
    # a consensus pulling the blend far below the method mean caps the blend buy-in, never the internal one
    assert internal_buy_in == analysis["buy_in"]
    capped_blend = official_buy_in_v1(analysis["methods"].values(), discount, internal_tp * 0.5)
    assert capped_blend == internal_tp * 0.5 * 0.90 < internal_buy_in
    assert official_entry_discount_v1("B3", 50.0, 80.0) == 0.20 + 0.5 * 0.11 + 0.2 * 0.06


def test_producer_role_stamps_explicit_none_for_the_full_stamp(tmp_path) -> None:
    # The producer branch (the screeners' engine) is what BECOMES the record: it carries no served stamp, explicitly.
    service = service_for(tmp_path)
    analysis = service._analyze(
        "MSFT", "US",
        {"price": 500.0, "currency": "USD", "change_percent": 1.25, "as_of": datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc)},
        {"companyName": "Microsoft Corporation", "sector": "Technology", "trailingEps": 16.0, "forwardEps": 18.5,
         "bookValue": 42.0, "sharesOutstanding": 7_430_000_000, "freeCashflow": 92_000_000_000, "ebitda": 150_000_000_000},
        role="producer",
    )
    assert analysis["analysis_role"] == "producer"
    for analysis_key, _ in FULL_STAMP_KEYS:
        assert analysis_key in analysis and analysis[analysis_key] is None



def test_pdf_summary_band_value_never_overlaps_the_stamp_and_single_line_columns_keep_their_size(tmp_path, monkeypatch) -> None:
    """X7 (rev 5): the NOSSO TP value (8.6 pt at y+15.5) overlapped the first stamp line (4.2 pt at y+11.2) by 0.5 pt —
    Helvetica ascent 718 / descent -207 per 1000 em. Every baseline actually drawn on the canvas is captured: the
    value's descender bottom stays ≥ 0.5 pt above the first stamp line's ascender top, the label above the value, the
    last line inside the band; the one-line columns (CONSENSO, BUY-IN) keep their 4.6 pt cap, the stamp its 4.2 pt."""
    from reportlab.pdfgen import canvas as pdf_canvas

    from app.one_pager_pdf import (
        STAMP_FONT, STAMP_FONT_MAX, STAMP_LEADING, STAMP_LINES, SUBTEXT_FONT_MAX, SUMMARY_VALUE_FONT,
    )

    ascent, descent = 0.718, 0.207  # Helvetica / Helvetica-Bold, per 1 pt of size
    service = service_for(tmp_path)
    analysis = sample_analysis(service)
    band: dict[str, float] = {}
    original_band = PremiumOnePagerRenderer._valuation_summary_band

    def spy_band(self, pdf, x, y, w, h, data):
        band.update({"x": x, "y": y, "w": w, "h": h})
        return original_band(self, pdf, x, y, w, h, data)

    drawn: list[tuple[str, str, float, float]] = []
    original_draw = pdf_canvas.Canvas.drawCentredString

    def spy_draw(self, x, y, text, *args, **kwargs):
        drawn.append((text, self._fontname, self._fontsize, y))
        return original_draw(self, x, y, text, *args, **kwargs)

    monkeypatch.setattr(PremiumOnePagerRenderer, "_valuation_summary_band", spy_band)
    monkeypatch.setattr(pdf_canvas.Canvas, "drawCentredString", spy_draw)
    history = [{"date": (datetime(2025, 8, 5, tzinfo=timezone.utc) + timedelta(days=round(index * 365 / 260))).date().isoformat(),
                "close": 400 + index * 0.3} for index in range(261)]

    service._write_report(analysis, history)

    y0, h = band["y"], band["h"]
    lines = PremiumOnePagerRenderer._official_stamp_lines(analysis)
    value_text = PremiumOnePagerRenderer._money(analysis["c3po_tp"], analysis["currency"])
    label = next(item for item in drawn if item[0] == "NOSSO TP")
    value = next(item for item in drawn if item[0] == value_text and item[1] == "Helvetica-Bold" and item[2] == SUMMARY_VALUE_FONT)
    stamp = [item for item in drawn if item[0] in lines]
    assert [item[0] for item in stamp] == list(lines) and len(stamp) == STAMP_LINES
    first, last = stamp[0], stamp[-1]
    assert first[1] == STAMP_FONT and first[2] <= STAMP_FONT_MAX
    value_bottom = value[3] - descent * value[2]
    first_stamp_top = first[3] + ascent * first[2]
    assert value_bottom - first_stamp_top >= 0.5, (value_bottom, first_stamp_top)  # the value never touches the stamp
    assert label[3] - descent * label[2] > value[3] + ascent * value[2]  # the label sits above the value
    assert last[3] - descent * last[2] > y0 and label[3] + ascent * label[2] < y0 + h  # the whole column is inside the band
    assert first[3] - last[3] == pytest.approx((STAMP_LINES - 1) * STAMP_LEADING)
    # the one-line columns keep the legible 4.6 pt cap — per column, not the stamp's 4.2 pt for everyone
    consensus = next(item for item in drawn if item[0] == PremiumOnePagerRenderer._consensus_provenance_label(analysis))
    buy_in = next(item for item in drawn if item[0] == "entrada disciplinada")
    assert buy_in[2] == SUBTEXT_FONT_MAX and STAMP_FONT_MAX < consensus[2] <= SUBTEXT_FONT_MAX
    assert PremiumOnePagerRenderer.summary_column_max_font(lines) == STAMP_FONT_MAX
    assert PremiumOnePagerRenderer.summary_column_max_font(("entrada disciplinada",)) == SUBTEXT_FONT_MAX
    width = band["w"] / 3 - 6
    assert PremiumOnePagerRenderer._stamp_layout(("entrada disciplinada",), width, max_size=SUBTEXT_FONT_MAX) == [("entrada disciplinada", SUBTEXT_FONT_MAX)]
    assert PremiumOnePagerRenderer._stamp_layout(lines, width)[0][1] <= STAMP_FONT_MAX
    # a one-line column's text sits in the same vertical area, centred: above the band's bottom and below the value
    assert buy_in[3] - descent * buy_in[2] > y0 and buy_in[3] + ascent * buy_in[2] < value_bottom
