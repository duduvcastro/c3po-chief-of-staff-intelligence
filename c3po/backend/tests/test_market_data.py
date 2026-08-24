from datetime import date, datetime, timedelta, timezone

import pytest

from app.config import Settings
from app.database import Database
from app.market_data.brapi import BrapiClient
from app.market_data.b3_screener import DISCLOSURE_GOVERNANCE_MAX_SWING, MIN_MARKET_CAP, B3ScreenerService
from app.market_data.sector_taxonomy import SECTOR_TAXONOMY_VERSION
from app.market_data.eodhd import EodhdClient
from app.market_data.eodhd_stream import EodhdStreamQuote
from app.market_data.http import MarketDataRequestError
from app.market_data.live_markets import MARKET_SPECS as LIVE_MARKET_SPECS
from app.market_data.live_markets import LiveMarketsService, MarketSpec
from app.market_data.realtime import RealtimeMarketsService
from app.market_data.service import MarketDataService
from app.schemas import LiveMarketItem, NormalizedQuote
from app.valuation_policy import METHODOLOGY_VERSION


class StubHttp:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_json(self, url, *, params=None, headers=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        return self.payload


def test_b3_screening_market_cap_floor_is_750_million() -> None:
    assert MIN_MARKET_CAP == 750_000_000


def test_sector_taxonomy_version_invalidates_stale_targeted_valuations() -> None:
    assert SECTOR_TAXONOMY_VERSION == 2


def test_on_demand_valuation_is_not_blocked_by_screening_quality_gate() -> None:
    now = datetime(2026, 8, 15, 12, tzinfo=timezone.utc)
    settings = Settings(brapi_token="configured", auth_cookie_secure=False)
    service = B3ScreenerService(settings, Database(settings), StubHttp({}))  # type: ignore[arg-type]
    quote = NormalizedQuote(
        provider="brapi",
        symbol="TEST3",
        provider_symbol="TEST3",
        exchange="B3",
        currency="BRL",
        price=10.0,
        volume=1_000_000,
        market_cap=1_000_000_000,
        as_of=now,
        collected_at=now,
        quality_score=94,
    )
    catalog = [{
        "symbol": "TEST3",
        "name": "Companhia Imobiliaria Teste",
        "sector": "Real Estate",
        "subsector": "Real Estate Development",
    }]
    statistics = {"TEST3": {
        "marketCap": 1_000_000_000,
        "sharesOutstanding": 100_000_000,
        "trailingPE": 10.0,
        "forwardPE": 8.33,
        "trailingEps": 1.0,
        "forwardEps": 1.2,
        "priceToBook": 1.25,
        "bookValue": 8.0,
        "beta": 0.85,
        "dividendYield": 0.04,
    }}
    financial = {"TEST3": {
        "returnOnEquity": 0.05,
        "profitMargins": 0.12,
        "earningsGrowthAnnual": 0.08,
        "freeCashflow": 90_000_000,
        "operatingCashflow": 120_000_000,
        "ebitda": 180_000_000,
        "totalRevenue": 900_000_000,
        "totalCash": 150_000_000,
        "totalDebt": 300_000_000,
        "targetMeanPrice": 14.0,
        "numberOfAnalystOpinions": 5,
    }}
    history = {"TEST3": {
        "history_days": 90,
        "adtv_90d": 10_000_000,
        "volatility_90d": 0.25,
        "support_60d": 9.0,
        "median_20d": 9.8,
        "low_20d": 9.2,
        "last_close": 10.0,
    }}
    macro = {"selic": 0.14, "ipca12m": 0.045}

    screened = service._prepare_rows(
        catalog, {"TEST3": quote}, statistics, financial, history, macro,
    )
    on_demand = service._prepare_rows(
        catalog,
        {"TEST3": quote},
        statistics,
        financial,
        history,
        macro,
        enforce_screening_gates=False,
        enforce_quality_gate=False,
    )

    assert screened == []
    assert len(on_demand) == 1
    assert on_demand[0]["fundamental_quality_status"] == "review_required"
    assert "ROE below the screening quality threshold" in on_demand[0]["fundamental_quality_reasons"]
    assert on_demand[0]["our_tp"] > 0
    assert on_demand[0]["buy_in"] > 0
    assert on_demand[0]["internal_method_count"] >= 3


def test_on_demand_valuation_does_not_require_screening_liquidity_or_history() -> None:
    now = datetime(2026, 8, 15, 12, tzinfo=timezone.utc)
    settings = Settings(brapi_token="configured", auth_cookie_secure=False)
    service = B3ScreenerService(settings, Database(settings), StubHttp({}))  # type: ignore[arg-type]
    quote = NormalizedQuote(
        provider="brapi",
        symbol="TEST4",
        provider_symbol="TEST4",
        exchange="B3",
        currency="BRL",
        price=5.0,
        volume=10_000,
        market_cap=None,
        as_of=now,
        collected_at=now,
        quality_score=90,
    )
    catalog = [{"symbol": "TEST4", "name": "Companhia Teste", "sector": "Utilities"}]
    statistics = {"TEST4": {
        "sharesOutstanding": 100_000_000,
        "trailingPE": 7.0,
        "forwardPE": 6.25,
        "trailingEps": 0.71,
        "forwardEps": 0.8,
        "priceToBook": 0.9,
        "bookValue": 5.55,
        "beta": 0.7,
        "dividendYield": 0.06,
    }}
    financial = {"TEST4": {
        "returnOnEquity": 0.14,
        "profitMargins": 0.15,
        "earningsGrowthAnnual": 0.06,
        "freeCashflow": 70_000_000,
        "operatingCashflow": 100_000_000,
        "ebitda": 140_000_000,
        "totalRevenue": 700_000_000,
        "totalCash": 80_000_000,
        "totalDebt": 180_000_000,
        "targetMeanPrice": 7.0,
        "numberOfAnalystOpinions": 4,
    }}
    rows = service._prepare_rows(
        catalog,
        {"TEST4": quote},
        statistics,
        financial,
        {"TEST4": {}},
        {"selic": 0.14, "ipca12m": 0.045},
        enforce_screening_gates=False,
        enforce_quality_gate=False,
    )

    assert len(rows) == 1
    assert rows[0]["market_cap"] == 500_000_000
    assert rows[0]["our_tp"] > 0


def test_cyclical_margin_profile_uses_eight_quarter_company_history() -> None:
    fundamentals = {
        "quarterlyIncome": [
            {
                "date": f"202{year}-{month:02d}-30",
                "totalRevenue": revenue,
                "netIncome": net_income,
                "ebitda": ebitda,
            }
            for year, month, revenue, net_income, ebitda in (
                (6, 6, 1_500, 125, 395),
                (6, 3, 1_240, 37, 159),
                (5, 12, 1_240, -5, 149),
                (5, 9, 1_261, 109, 260),
                (5, 6, 1_274, 233, 393),
                (5, 3, 1_369, 151, 365),
                (4, 12, 1_635, 292, 604),
                (4, 9, 1_377, 119, 342),
            )
        ],
        "quarterlyCashFlow": [
            {"date": date_value, "freeCashFlow": free_cash_flow}
            for date_value, free_cash_flow in (
                ("2026-06-30", 87),
                ("2026-03-30", 18),
                ("2025-12-30", -131),
                ("2025-09-30", -39),
                ("2025-06-30", 264),
                ("2025-03-30", -147),
                ("2024-12-30", 170),
                ("2024-09-30", 96),
            )
        ],
    }

    profile = B3ScreenerService._cyclical_margin_profile(fundamentals)

    assert profile["cycle_observation_count"] == 8
    assert profile["cycle_profit_margin"] == pytest.approx(0.0913, abs=0.001)
    assert profile["cycle_ebitda_margin"] == pytest.approx(0.251, abs=0.002)
    assert profile["cycle_fcf_margin"] == pytest.approx(0.033, abs=0.002)


def test_cyclical_method_weights_exclude_spot_and_dividend_anchors() -> None:
    weights = B3ScreenerService._method_weights("cyclical")

    assert weights == {
        "dcf": 0.15,
        "cycle_enterprise": 0.40,
        "cycle_earnings": 0.35,
        "book": 0.10,
    }
    assert "earnings" not in weights
    assert "enterprise" not in weights
    assert "dividend" not in weights


def test_cyclical_market_multiples_use_normalized_denominators() -> None:
    multiples = B3ScreenerService._cyclical_market_multiples({
        "market_cap": 570_300_000_000,
        "price": 42.09,
        "shares": 12_888_733_000,
        "revenue": 424_807_000_000,
        "cycle_profit_margin": 0.2267081,
        "cycle_ebitda_margin": 0.45,
        "cash": 53_764_000_000,
        "debt": 366_533_000_000,
    })

    assert multiples["cycle_implied_pe"] == pytest.approx(5.63, abs=0.02)
    assert multiples["cycle_implied_ev_ebitda"] == pytest.approx(4.62, abs=0.02)


def test_cyclical_target_multiples_ignore_incompatible_spot_ttm_multiples() -> None:
    target_pe, target_ev = B3ScreenerService._cyclical_target_multiples(
        {"roe": 0.209, "pe": 17.86, "ev_ebitda": 7.50},
        {
            "roe": 0.052,
            "pe": 17.86,
            "forward_pe": 4.81,
            "ev_ebitda": 7.50,
            "cycle_pe": 6.75,
            "cycle_ev_ebitda": 4.62,
        },
        growth=-0.08,
        risk_penalty=0.0,
    )

    assert target_pe == pytest.approx(6.96, abs=0.03)
    assert target_ev == pytest.approx(4.51, abs=0.03)
    assert target_pe < 8.0
    assert target_ev < 5.0


def test_official_issuer_consensus_overrides_narrower_provider_coverage() -> None:
    rows = [{
        "symbol": "PETR4",
        "price": 42.09,
        "public_consensus_tp": 56.2923,
        "analyst_count": 6,
        "consensus_source_count": 2,
    }]

    B3ScreenerService._apply_official_consensus(rows)

    assert rows[0]["public_consensus_tp"] == 52.93
    assert rows[0]["analyst_count"] == 12
    assert rows[0]["consensus_origin_source"] == "Petrobras RI"
    assert rows[0]["consensus_as_of"] == "2026-05-13"


def test_petrobras_like_valuation_converges_after_cyclical_reconciliation() -> None:
    row = {
        "symbol": "PETR4", "issuer": "PETR", "name": "Petrobras PN",
        "sector": "Energy", "peer_group": "Oil, Gas & Fuels", "valuation_profile": "cyclical",
        "price": 42.09, "market_cap": 570_317_536_822.0, "shares": 12_888_733_000.0,
        "revenue": 424_807_000_000.0, "cash": 53_764_000_000.0, "debt": 366_533_000_000.0,
        "roe": 0.209, "profit_margin": 0.2371, "ebitda_margin": 0.2875,
        "cycle_profit_margin": 0.2267, "cycle_ebitda_margin": 0.45, "cycle_fcf_margin": 0.1919,
        "revenue_growth": -0.6152, "earnings_growth": -0.2578, "beta": 0.3588,
        "debt_to_equity": 0.7607, "fcf": 97_272_987_000.0,
        "operating_cashflow": 205_642_509_000.0, "ebitda": 122_153_000_000.0,
        "book_value": 35.2658, "price_to_book": 1.1935, "dividend_yield": 0.071,
        "volatility_90d": 0.2563, "support_60d": 39.1425, "median_20d": 42.045,
        "low_20d": 40.87, "last_close": 42.09, "completeness": 1.0, "quote_quality": 94,
        "source_agreement_percent": 64.66, "source_comparison_count": 6, "data_source_count": 2,
        "fundamentals_as_of": date.today().isoformat(), "public_consensus_tp": 52.93,
        "analyst_count": 12, "consensus_source_count": 2, "consensus_origin_symbol": "PETR4",
        "pe": 5.71, "forward_pe": 3.63, "ev_ebitda": 7.27,
    }
    row.update(B3ScreenerService._cyclical_market_multiples(row))
    benchmark = {"peer:Oil, Gas & Fuels": {
        "pe": 17.86, "forward_pe": 4.81, "ev_ebitda": 7.50,
        "cycle_pe": 6.75, "cycle_ev_ebitda": 4.62, "price_to_book": 1.19,
        "roe": 0.052, "growth": 0.164, "profit_margin": 0.098, "ebitda_margin": 0.288,
    }}
    service = B3ScreenerService.__new__(B3ScreenerService)
    service._calibration_factors = {}

    service._value_row(row, benchmark, {"selic": 0.14, "ipca12m": 0.045})

    assert 45.0 <= row["our_tp"] <= 55.0
    assert row["methods"]["cycle_enterprise"] < 55.0
    assert row["methods"]["cycle_earnings"] < 60.0
    assert row["tp_validation_status"] == "validated"
    assert row["method_dispersion_percent"] < 45.0


class RoutingStubHttp:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get_json(self, url, *, params=None, headers=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        for needle, payload in self.routes.items():
            if needle in url:
                return payload
        raise AssertionError(f"Unexpected URL: {url}")


class StubRealtimeStream:
    def __init__(self, quotes):
        self.quotes = quotes
        self.groups = {}

    def set_group(self, name, symbols, *, priority=50):
        self.groups[name] = {"symbols": symbols, "priority": priority}

    def quote(self, symbol):
        return self.quotes.get(symbol)


def test_brapi_normalizes_quote_snapshot() -> None:
    http = StubHttp({
        "results": [{
            "requestedSymbol": "ITUB4",
            "symbol": "ITUB4",
            "data": {
                "currency": "BRL",
                "regularMarketPrice": 41.12,
                "regularMarketChange": 0.42,
                "regularMarketChangePercent": 1.03,
                "regularMarketOpen": 40.7,
                "regularMarketDayLow": 40.55,
                "regularMarketDayHigh": 41.35,
                "regularMarketPreviousClose": 40.7,
                "regularMarketVolume": 12345678,
                "marketCap": 401000000000,
                "regularMarketTime": "2026-08-04T20:31:30.000Z",
            },
        }]
    })
    client = BrapiClient("https://brapi.dev", "secret", http)  # type: ignore[arg-type]

    quote = client.quotes(["ITUB4.SA"])[0]

    assert quote.symbol == "ITUB4"
    assert quote.price == 41.12
    assert quote.change_percent == 1.03
    assert quote.currency == "BRL"
    assert quote.as_of == datetime(2026, 8, 4, 20, 31, 30, tzinfo=timezone.utc)
    assert quote.quality_score == 94
    assert http.calls[0]["params"] == {"symbols": "ITUB4"}
    assert http.calls[0]["headers"] == {"Authorization": "Bearer secret"}


def test_brapi_quote_falls_back_to_classic_endpoint() -> None:
    class V2UnavailableHttp(StubHttp):
        def get_json(self, url, *, params=None, headers=None):
            self.calls.append({"url": url, "params": params, "headers": headers})
            if "/api/v2/stocks/quote" in url:
                raise MarketDataRequestError("404 Not Found")
            return {
                "results": [{
                    "symbol": "PETR4",
                    "currency": "BRL",
                    "regularMarketPrice": 41.90,
                }]
            }

    http = V2UnavailableHttp({})
    client = BrapiClient("https://brapi.dev", "secret", http)  # type: ignore[arg-type]

    quotes = client.quotes(["PETR4"])

    assert quotes[0].price == 41.90
    assert http.calls[0]["url"].endswith("/api/v2/stocks/quote")
    assert http.calls[1]["url"].endswith("/api/quote/PETR4")


def test_eodhd_normalizes_multiple_quotes() -> None:
    http = StubHttp([
        {"code": "MSFT.US", "timestamp": 1785859200, "open": 520, "high": 525, "low": 518, "close": 523, "volume": 10, "previousClose": 519, "change": 4, "change_p": 0.77},
        {"code": "AMZN.US", "timestamp": 1785859200, "close": 230, "change_p": -0.25},
    ])
    client = EodhdClient("https://eodhd.com", "secret", http)  # type: ignore[arg-type]

    quotes = client.quotes(["MSFT", "AMZN.US"])

    assert [quote.symbol for quote in quotes] == ["MSFT", "AMZN"]
    assert quotes[0].exchange == "US"
    assert quotes[1].change_percent == -0.25
    assert http.calls[0]["params"]["s"] == "AMZN.US"


def test_eodhd_quotes_skips_a_bad_record_without_losing_the_rest_of_the_batch() -> None:
    """Confirmed live against the real API (2026-08-19): SSEC.INDX came back
    HTTP 200 with "close"/"change_p"/"timestamp" all the literal string "NA"
    instead of a real quote or an error status, while N225.INDX and
    GDAXI.INDX in the same batch returned valid data. The old plain list
    comprehension let that one record's require_price ValueError abort the
    whole batch, silently dropping Nikkei/DAX along with Shanghai."""
    http = StubHttp([
        {"code": "N225.INDX", "timestamp": 1785859200, "close": 66008.9688, "change_p": -4.6392},
        {"code": "SSEC.INDX", "timestamp": "NA", "close": "NA", "change_p": "NA"},
        {"code": "GDAXI.INDX", "timestamp": 1785859200, "close": 26128.3594, "change_p": -0.7983},
    ])
    client = EodhdClient("https://eodhd.com", "secret", http)  # type: ignore[arg-type]

    quotes = client.quotes(["N225.INDX", "SSEC.INDX", "GDAXI.INDX"])

    assert [quote.symbol for quote in quotes] == ["N225", "GDAXI"]


def test_eodhd_normalizes_b3_fundamentals() -> None:
    payload = {
        "General": {"Code": "PETR4", "UpdatedAt": "2026-08-04"},
        "Highlights": {
            "MarketCapitalization": 500_000_000_000,
            "WallStreetTargetPrice": 45.0,
            "PEGRatio": 1.2,
            "RevenueTTM": 450_000_000_000,
        },
        "Valuation": {"TrailingPE": 7.5, "ForwardPE": 6.8, "EnterpriseValueEbitda": 4.2},
        "Earnings": {"Trend": {"Annual": {"2027": {"earningsEstimateNumberOfAnalysts": 14}}}},
        "Financials": {},
    }

    result = EodhdClient._normalize_fundamentals(payload)

    assert result["provider_symbol"] == "PETR4"
    assert result["forwardPE"] == 6.8
    assert result["targetMeanPrice"] == 45.0
    assert result["numberOfAnalystOpinions"] == 14


def test_eodhd_keeps_spcx_as_common_stock_despite_stale_etf_metadata() -> None:
    result = EodhdClient._normalize_fundamentals({
        "General": {
            "Code": "SPCX",
            "Name": "SPAC and New Issue ETF",
            "Type": "ETF",
        },
        "ETF_Data": {"Category": "Legacy provider record"},
        "Financials": {},
    })

    assert result["companyName"] == "Space Exploration Technologies Corp. Class A Common Stock"
    assert result["securityType"] == "Stock"
    assert result["isETF"] is False


def test_eodhd_expands_relative_company_logo_url() -> None:
    result = EodhdClient._normalize_fundamentals({
        "General": {"Code": "AAPL", "LogoURL": "/img/logos/US/aapl.png"},
        "Financials": {},
    })

    assert result["logoUrl"] == "https://eodhd.com/img/logos/US/aapl.png"


def test_eodhd_uses_reporting_period_instead_of_metadata_update() -> None:
    payload = {
        "General": {"Code": "UNIP6", "UpdatedAt": "2026-08-06"},
        "Highlights": {"MostRecentQuarter": "2026-06-30"},
        "Financials": {
            "Income_Statement": {"quarterly": {
                "2026-06-30": {"date": "2026-06-30", "totalRevenue": "100"},
                "2026-03-31": {"date": "2026-03-31", "totalRevenue": "90"},
            }},
        },
    }

    result = EodhdClient._normalize_fundamentals(payload)

    assert result["updated_at"] == "2026-08-06"
    assert result["financialsAsOf"] == "2026-06-30"


def test_eodhd_discards_provider_sentinel_dates() -> None:
    result = EodhdClient._normalize_fundamentals({
        "General": {"Code": "TEST3", "UpdatedAt": "0000-00-00"},
        "Highlights": {"MostRecentQuarter": "0000-00-00"},
        "Financials": {},
    })

    assert result["updated_at"] is None
    assert result["financialsAsOf"] is None


def test_analysis_snapshots_support_latest_and_historical_lookup(tmp_path) -> None:
    settings = Settings(database_url="", migrations_dir=tmp_path)
    database = Database(settings)
    methodology_id = database.ensure_methodology_version("test", 1, {}, "test")
    first = datetime(2026, 1, 1, tzinfo=timezone.utc)
    second = datetime(2026, 4, 1, tzinfo=timezone.utc)
    database.save_analysis_snapshot("valuation_universe", "B3_UNIVERSE", methodology_id, {}, {"version": 1}, first)
    database.save_analysis_snapshot("valuation_universe", "B3_UNIVERSE", methodology_id, {}, {"version": 2}, second)

    latest = database.latest_analysis_snapshot("valuation_universe", "B3_UNIVERSE")
    historical = database.analysis_snapshot_at_or_before(
        "valuation_universe",
        "B3_UNIVERSE",
        datetime(2026, 2, 1, tzinfo=timezone.utc),
    )

    assert latest and latest["outputs"]["version"] == 2
    assert historical and historical["outputs"]["version"] == 1


def test_valuation_calibration_uses_mature_price_return_samples(tmp_path) -> None:
    settings = Settings(database_url="", migrations_dir=tmp_path)
    database = Database(settings)
    service = B3ScreenerService(settings, database, StubHttp({}))  # type: ignore[arg-type]
    methodology_id = database.ensure_methodology_version("test", 1, {}, "test")
    generated_at = datetime(2026, 8, 1, tzinfo=timezone.utc)
    prior_rows = [
        {
            "symbol": f"T{index:03d}3",
            "price": 100.0,
            "expected_total_return_percent": 15.0,
            "expected_dividend": 5.0,
            "valuation_profile": "general",
        }
        for index in range(40)
    ]
    current_rows = [
        {"symbol": row["symbol"], "price": 110.0, "valuation_profile": "general"}
        for row in prior_rows
    ]
    database.save_analysis_snapshot(
        "valuation_universe",
        "B3_UNIVERSE",
        methodology_id,
        {},
        {"rows": prior_rows},
        generated_at - timedelta(days=90),
    )

    service._persist_calibration(methodology_id, generated_at, current_rows)
    calibration = database.latest_analysis_snapshot("valuation_calibration", "B3_POWER_MODEL")

    assert calibration and calibration["outputs"]["status"] == "active"
    assert 1.0 < calibration["outputs"]["factors"]["global"] <= 1.05
    assert calibration["outputs"]["metrics"]["global"]["samples"] == 40


def test_eodhd_history_keeps_volume_for_b3_fallback() -> None:
    http = StubHttp([
        {"date": "2026-08-05", "adjusted_close": 21.5, "volume": 1_500_000},
        {"date": "2026-08-04", "close": 21.0, "volume": 1_200_000},
    ])
    client = EodhdClient("https://eodhd.com", "secret", http)  # type: ignore[arg-type]

    history = client.history("TEST3", exchange="SA", days=120)

    assert history[0] == {"date": "2026-08-05", "close": 21.5, "volume": 1_500_000}
    assert http.calls[0]["url"].endswith("/api/eod/TEST3.SA")


def test_source_confirmation_rewards_independent_agreement() -> None:
    close, close_count = B3ScreenerService._source_confirmation_score(
        {"market_cap": 100.0, "pe": 10.0, "forward_pe": 9.0},
        {"market_cap": 102.0, "pe": 10.5, "forward_pe": 9.5},
    )
    divergent, divergent_count = B3ScreenerService._source_confirmation_score(
        {"market_cap": 100.0, "pe": 10.0, "forward_pe": 9.0},
        {"market_cap": 180.0, "pe": 22.0, "forward_pe": 20.0},
    )
    missing, missing_count = B3ScreenerService._source_confirmation_score(
        {"market_cap": 100.0},
        {},
    )

    assert close_count == divergent_count == 3
    assert close > divergent
    assert missing == 30.0
    assert missing_count == 0


def test_target_price_validation_rejects_model_consensus_divergence() -> None:
    row = {
        "price": 20.0,
        "analyst_count": 8,
        "data_source_count": 2,
        "source_comparison_count": 5,
        "source_agreement_percent": 90.0,
        "fundamentals_as_of": date.today().isoformat(),
        "ir_status": "pending_review",
    }
    methods = {"dcf": 30.0, "enterprise": 31.0, "earnings": 29.0, "consensus": 30.0}

    validated = B3ScreenerService._validate_target_price(
        row=row,
        methods=methods,
        internal_tp=30.0,
        consensus_tp=30.0,
        our_tp=30.0,
        valuation_confidence=85.0,
        method_dispersion=10.0,
    )
    divergent = B3ScreenerService._validate_target_price(
        row=row,
        methods=methods,
        internal_tp=60.0,
        consensus_tp=25.0,
        our_tp=50.0,
        valuation_confidence=85.0,
        method_dispersion=10.0,
    )

    assert validated["status"] == "validated"
    assert validated["score"] >= 65
    assert all("CVM" not in reason and "disclosure" not in reason for reason in validated["reasons"])
    assert divergent["status"] == "review_required"
    assert "Internal model is too far from public consensus" in divergent["reasons"]


def test_provider_health_distinguishes_unconfigured_and_ready() -> None:
    settings = Settings(
        brapi_token="configured",
        brapi_plan="pro",
        eodhd_api_token="",
        auth_cookie_secure=False,
    )
    service = MarketDataService(settings, Database(settings), http=StubHttp({}))  # type: ignore[arg-type]

    health = service.health()

    assert health[0].status == "attention"
    assert health[0].plan == "pro"
    assert health[1].status == "unconfigured"


def test_live_markets_normalizes_public_chart_quote() -> None:
    http = StubHttp({
        "chart": {
            "result": [{
                "meta": {
                    "currency": "USD",
                    "exchangeName": "CME",
                    "regularMarketPrice": 6500.0,
                    "previousClose": 6450.0,
                    "regularMarketOpen": 6460.0,
                    "regularMarketDayLow": 6440.0,
                    "regularMarketDayHigh": 6520.0,
                    "regularMarketTime": 1785859200,
                    "marketState": "REGULAR",
                }
            }],
            "error": None,
        }
    })
    service = LiveMarketsService(Settings(auth_cookie_secure=False), http)  # type: ignore[arg-type]

    item = service._fetch_yahoo(MarketSpec("Future Index", "S&P 500 Fut.", "S&P", "ES=F", "USD"))

    assert item.price == 6500.0
    assert round(item.change_percent or 0, 2) == 0.78
    assert item.status == "delayed"
    assert item.delay_minutes == 5
    assert item.provider == "Yahoo Finance"
    assert http.calls[0]["params"] == {"range": "1d", "interval": "5m"}


def test_live_markets_separates_spot_and_future_index_groups() -> None:
    spot_indices = {
        spec.symbol: spec.provider_symbol
        for spec in LIVE_MARKET_SPECS
        if spec.group == "Index"
    }
    future_symbols = {
        spec.symbol
        for spec in LIVE_MARKET_SPECS
        if spec.group == "Future Index"
    }

    assert spot_indices == {
        "IBOV": "^BVSP",
        "NASDAQ": "^IXIC",
        "NYSE": "^NYA",
    }
    assert {"S&P 500 Fut.", "Nasdaq Fut.", "US3Y", "US10Y"} <= future_symbols


def test_live_markets_refreshes_spot_indices_on_three_second_channel() -> None:
    http = StubHttp({
        "chart": {
            "result": [{
                "meta": {
                    "currency": "USD",
                    "exchangeName": "INDEX",
                    "regularMarketPrice": 100.0,
                    "previousClose": 99.0,
                    "regularMarketTime": 1785859200,
                    "marketState": "REGULAR",
                }
            }],
            "error": None,
        }
    })
    service = LiveMarketsService(Settings(auth_cookie_secure=False), http)  # type: ignore[arg-type]

    first = service.index_snapshot()
    second = service.index_snapshot()

    assert first.refresh_seconds == 3
    assert [item.symbol for item in first.items] == ["IBOV", "NASDAQ", "NYSE"]
    assert first.items[0].price == 100.0
    assert second.generated_at == first.generated_at
    assert len(http.calls) == 3


def test_spcx_is_registered_as_spacex_common_stock() -> None:
    spcx = next(spec for spec in LIVE_MARKET_SPECS if spec.symbol == "SPCX")

    assert spcx.name == "Space Exploration Technologies Corp. Class A Common Stock"
    assert "ETF" not in spcx.name.upper()
    assert spcx.eodhd_symbol == "SPCX.US"


def test_live_markets_prefers_eodhd_for_us_portfolio_quotes() -> None:
    http = StubHttp([{
        "code": "AMZN.US",
        "timestamp": 1785859200,
        "open": 225.0,
        "high": 232.0,
        "low": 224.0,
        "close": 230.0,
        "previousClose": 228.0,
        "change": 2.0,
        "change_p": 0.88,
    }])
    settings = Settings(
        eodhd_api_token="configured",
        eodhd_plan="all-in-one",
        auth_cookie_secure=False,
    )
    service = LiveMarketsService(settings, http)  # type: ignore[arg-type]
    spec = MarketSpec("Portfolio", "AMZN", "Amazon", "AMZN", "USD", "eodhd", "AMZN.US")

    item = service._fetch_eodhd([spec])[0]

    assert item.provider == "EODHD All-In-One"
    assert item.provider_symbol == "AMZN.US"
    assert item.price == 230.0
    assert item.previous_close == 228.0
    assert item.delay_minutes == 15
    assert http.calls[0]["url"].endswith("/api/real-time/AMZN.US")


def test_nikkei_dax_shanghai_stayed_on_yahoo() -> None:
    """EODHD's .INDX symbols were tried for these three (2026-08-19) to fix
    Yahoo's multi-hour-stale prints, then reverted the same day: EODHD's
    .INDX responses don't include a currency field, so Nikkei/DAX displayed
    as USD instead of JPY/EUR (see _normalize's "USD" fallback in eodhd.py).
    Regression test so this doesn't get silently re-migrated without also
    fixing the currency gap first."""
    by_symbol = {spec.symbol: spec for spec in LIVE_MARKET_SPECS if spec.group == "Future Index"}

    assert by_symbol["Nikkei"].provider == "yahoo"
    assert by_symbol["DAX"].provider == "yahoo"
    assert by_symbol["Shanghai"].provider == "yahoo"


class SequenceHttp:
    """Returns responses/raises in call order -- StubHttp always returns the
    same fixed payload, which can't simulate one suffix batch failing while
    another succeeds (the exact scenario _fetch_eodhd's per-suffix isolation
    is meant to handle)."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def get_json(self, url, *, params=None, headers=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_fetch_eodhd_isolates_a_failing_suffix_batch_from_the_others() -> None:
    """A bad/unsupported symbol in one suffix's batch (e.g. an .INDX code
    EODHD doesn't actually carry) must not lose every other suffix's
    already-fetched quotes -- regression test for the try/except added
    alongside the .INDX suffix (2026-08-19)."""
    http = SequenceHttp([
        [{
            "code": "AMZN.US", "timestamp": 1785859200, "open": 225.0, "high": 232.0,
            "low": 224.0, "close": 230.0, "previousClose": 228.0, "change": 2.0, "change_p": 0.88,
        }],
        MarketDataRequestError("EODHD did not recognize SSEC.INDX"),
    ])
    settings = Settings(eodhd_api_token="configured", eodhd_plan="all-in-one", auth_cookie_secure=False)
    service = LiveMarketsService(settings, http)  # type: ignore[arg-type]
    specs = [
        MarketSpec("Portfolio", "AMZN", "Amazon", "AMZN", "USD", "eodhd", "AMZN.US"),
        MarketSpec("Future Index", "Shanghai", "Shanghai Composite", "000001.SS", "CNY", "eodhd", "SSEC.INDX"),
    ]

    items = service._fetch_eodhd(specs)

    assert [item.symbol for item in items] == ["AMZN"]
    assert len(http.calls) == 2


def test_live_markets_reads_treasury_yields_from_eodhd_government_bonds() -> None:
    http = StubHttp([
        {"date": "2026-08-13", "close": 3.711},
        {"date": "2026-08-14", "close": 3.742},
    ])
    settings = Settings(eodhd_api_token="configured", auth_cookie_secure=False)
    service = LiveMarketsService(settings, http)  # type: ignore[arg-type]
    spec = MarketSpec(
        "Future Index",
        "US3Y",
        "US 3-Year Treasury Yield",
        "US3Y.GBOND",
        "%",
        "eodhd_bond",
        "US3Y.GBOND",
    )

    now = datetime(2026, 8, 16, 12, tzinfo=timezone.utc)
    item = service._bond_snapshot([spec], now)[0]
    cached = service._bond_snapshot([spec], now + timedelta(minutes=5))[0]

    assert item.provider == "EODHD Government Bonds"
    assert item.provider_symbol == "US3Y.GBOND"
    assert item.price == 3.742
    assert item.previous_close == 3.711
    assert round(item.change_percent or 0, 2) == 0.84
    assert item.currency == "%"
    assert item.status == "closed"
    assert cached.price == item.price
    assert len(http.calls) == 1
    assert http.calls[0]["url"].endswith("/api/eod/US3Y.GBOND")


def test_live_markets_overlays_eodhd_websocket_trade() -> None:
    baseline_time = datetime(2026, 8, 15, 12, tzinfo=timezone.utc)
    stream = StubRealtimeStream({
        "AMZN": EodhdStreamQuote(
            symbol="AMZN",
            price=231.5,
            as_of=baseline_time + timedelta(seconds=10),
            market_state="open",
        )
    })
    service = LiveMarketsService(
        Settings(eodhd_api_token="configured", auth_cookie_secure=False),
        StubHttp({}),
        stream=stream,  # type: ignore[arg-type]
    )
    spec = MarketSpec("Portfolio", "AMZN", "Amazon", "AMZN", "USD", "eodhd", "AMZN.US")
    baseline = LiveMarketItem(
        group="Portfolio",
        symbol="AMZN",
        name="Amazon",
        provider_symbol="AMZN.US",
        provider="EODHD All-In-One",
        exchange="US",
        currency="USD",
        price=230.0,
        previous_close=228.0,
        market_state="REGULAR",
        status="delayed",
        delay_minutes=15,
        as_of=baseline_time,
        collected_at=baseline_time,
        quality_score=88,
    )

    item = service._apply_eodhd_stream(spec, baseline)

    assert item.provider == "EODHD Real-Time WebSocket"
    assert item.price == 231.5
    assert item.status == "live"
    assert item.delay_minutes == 0
    assert round(item.change_percent or 0, 2) == 1.54


def test_realtime_b3_ranks_each_board_from_full_quote_list() -> None:
    symbols = ("TESA3", "TESA4", "TESA5", "TESA6", "TESA11", "TESB3", "TESB11", "TESC3")
    rows = [
        {"stock": symbol, "name": f"Empresa {index}", "close": 10 + index, "change": index - 3, "volume": 10_000 * index}
        for index, symbol in enumerate(symbols, start=1)
    ] + [
        {"stock": "TESC3F", "name": "Lote fracionário", "close": 99, "change": 99, "volume": 99_000},
    ]
    http = RoutingStubHttp({
        "/api/quote/list": {"stocks": rows},
        "/v8/finance/chart/": {"chart": {"result": [{"meta": {
            "regularMarketPrice": 140000,
            "previousClose": 139000,
            "regularMarketTime": 1785859200,
            "marketState": "REGULAR",
            "currency": "BRL",
        }}]}},
    })
    settings = Settings(brapi_token="configured", auth_cookie_secure=False)
    service = RealtimeMarketsService(settings, Database(settings), http)  # type: ignore[arg-type]

    response = service.snapshot("b3")

    assert response.market == "B3"
    assert response.universe_size == 8
    assert [item.change_percent for item in response.gainers] == [5, 4, 3, 2, 1]
    assert [item.change_percent for item in response.losers] == [-2, -1, 0, 1, 2]
    assert response.volume_leaders[0].symbol == "TESC3"
    assert response.cash_leaders[0].cash_volume == 18 * 80_000
    assert http.calls[1]["params"]["limit"] == 2000


def test_realtime_us_separates_nasdaq_and_nyse_common_stocks() -> None:
    timestamp = 1785859200
    catalog = []
    quotes = []
    for exchange, prefix in (("NASDAQ", "NAS"), ("NYSE", "NYS")):
        for index in range(1, 8):
            symbol = f"{prefix}{index}"
            catalog.append({"Code": symbol, "Name": f"{exchange} Company {index}", "Exchange": exchange, "Type": "Common Stock", "Currency": "USD"})
            quotes.append({"code": f"{symbol}.US", "timestamp": timestamp, "close": 20 + index, "change_p": index - 4, "volume": index * 10_000})
    catalog.append({"Code": "QQQ", "Name": "ETF", "Exchange": "NASDAQ", "Type": "ETF", "Currency": "USD"})
    quotes.append({"code": "QQQ.US", "timestamp": timestamp, "close": 500, "change_p": 10, "volume": 99_000_000})
    http = RoutingStubHttp({
        "/api/exchange-symbol-list/US": catalog,
        "/api/real-time/AAPL.US": quotes,
        "/v8/finance/chart/": {"chart": {"result": [{"meta": {
            "regularMarketPrice": 22000,
            "previousClose": 21800,
            "regularMarketTime": timestamp,
            "marketState": "REGULAR",
            "currency": "USD",
        }}]}},
    })
    settings = Settings(eodhd_api_token="configured", auth_cookie_secure=False)
    service = RealtimeMarketsService(settings, Database(settings), http)  # type: ignore[arg-type]

    nasdaq = service.snapshot("nasdaq")
    nyse = service.snapshot("nyse")

    assert nasdaq.universe_size == nyse.universe_size == 7
    assert all(item.symbol.startswith("NAS") for item in nasdaq.gainers)
    assert all(item.symbol.startswith("NYS") for item in nyse.gainers)
    assert "QQQ" not in {item.symbol for item in nasdaq.volume_leaders}
    assert nasdaq.gainers[0].change_percent == 3
    assert nyse.losers[0].change_percent == -3
    assert len([call for call in http.calls if "/api/real-time/AAPL.US" in call["url"]]) == 1


def test_realtime_us_investable_universe_includes_nasdaq_and_nyse_arca_etfs() -> None:
    timestamp = 1785859200
    catalog = [
        {"Code": "MSFT", "Name": "Microsoft", "Exchange": "NASDAQ", "Type": "Common Stock", "Currency": "USD"},
        {"Code": "QQQ", "Name": "Invesco QQQ Trust", "Exchange": "NASDAQ", "Type": "ETF", "Currency": "USD"},
        {"Code": "IBM", "Name": "IBM", "Exchange": "NYSE", "Type": "Common Stock", "Currency": "USD"},
        {"Code": "VOO", "Name": "Vanguard S&P 500 ETF", "Exchange": "NYSE ARCA", "Type": "ETF", "Currency": "USD"},
    ]
    quotes = [
        {"code": f"{symbol}.US", "timestamp": timestamp, "close": price, "change_p": 0.5, "volume": 1_000_000}
        for symbol, price in (("MSFT", 500), ("QQQ", 590), ("IBM", 250), ("VOO", 610))
    ]
    http = RoutingStubHttp({
        "/api/exchange-symbol-list/US": catalog,
        "/api/real-time/AAPL.US": quotes,
    })
    settings = Settings(eodhd_api_token="configured", auth_cookie_secure=False)
    service = RealtimeMarketsService(settings, Database(settings), http)  # type: ignore[arg-type]
    now = datetime.fromtimestamp(timestamp, tz=timezone.utc)

    nasdaq = service._us_investable_rows("NASDAQ", now)
    nyse = service._us_investable_rows("NYSE", now)

    assert {item.symbol for item in nasdaq} == {"MSFT", "QQQ"}
    assert {item.symbol for item in nyse} == {"IBM", "VOO"}


def test_realtime_us_overlays_visible_rows_with_websocket_trade() -> None:
    timestamp = 1785859200
    catalog = [{"Code": "MSFT", "Name": "Microsoft", "Exchange": "NASDAQ", "Type": "Common Stock", "Currency": "USD"}]
    quotes = [{"code": "MSFT.US", "timestamp": timestamp, "close": 105, "previousClose": 50, "change_p": 5, "volume": 1_000_000}]
    http = RoutingStubHttp({
        "/api/exchange-symbol-list/US": catalog,
        "/api/real-time/AAPL.US": quotes,
        "/v8/finance/chart/": {"chart": {"result": [{"meta": {
            "regularMarketPrice": 22000,
            "previousClose": 21800,
            "regularMarketTime": timestamp,
            "marketState": "REGULAR",
            "currency": "USD",
        }}]}},
    })
    stream = StubRealtimeStream({"MSFT": EodhdStreamQuote(
        symbol="MSFT",
        price=110,
        as_of=datetime.fromtimestamp(timestamp + 60, tz=timezone.utc),
        market_state="open",
    )})
    settings = Settings(eodhd_api_token="configured", auth_cookie_secure=False)
    service = RealtimeMarketsService(settings, Database(settings), http, stream=stream)  # type: ignore[arg-type]

    response = service.snapshot("nasdaq")

    assert response.gainers[0].price == 110
    assert response.gainers[0].change_percent == pytest.approx(10)
    assert response.gainers[0].status == "live"
    assert response.gainers[0].delay_minutes == 0
    assert response.refresh_seconds == 3
    assert "real-time WebSocket" in response.source
    assert stream.groups["market:NASDAQ"]["symbols"] == ["MSFT"]

    stream.quotes["MSFT"] = EodhdStreamQuote(
        symbol="MSFT",
        price=200,
        as_of=datetime.fromtimestamp(timestamp + 120, tz=timezone.utc),
        market_state="open",
    )
    guarded = service.snapshot("nasdaq")
    assert guarded.gainers[0].price == 105
    assert guarded.gainers[0].status == "delayed"


def test_realtime_portfolio_persists_validated_symbols_and_reuses_quotes() -> None:
    http = RoutingStubHttp({
        "/api/quote/list": {"stocks": [
            {"stock": "PETR4", "name": "Petrobras", "close": 42.0, "change": 1.2, "volume": 20_000_000},
        ]},
    })
    settings = Settings(brapi_token="configured", auth_cookie_secure=False)
    database = Database(settings)
    service = RealtimeMarketsService(settings, database, http)  # type: ignore[arg-type]

    added = service.add_portfolio_symbol("petr4.sa")

    assert added.item_count == 1
    assert added.items[0].symbol == "PETR4"
    assert added.items[0].market == "B3"
    assert added.items[0].price == 42.0
    assert len([call for call in http.calls if "/api/quote/list" in call["url"]]) == 1

    removed = service.delete_portfolio_symbol("PETR4")
    assert removed.item_count == 0
    assert database.list_realtime_portfolio() == []


def test_realtime_portfolio_intraday_uses_latest_b3_session_only() -> None:
    previous_session = int(datetime(2026, 8, 13, 13, 0, tzinfo=timezone.utc).timestamp())
    session_open = int(datetime(2026, 8, 14, 13, 0, tzinfo=timezone.utc).timestamp())
    session_later = int(datetime(2026, 8, 14, 15, 0, tzinfo=timezone.utc).timestamp())
    http = RoutingStubHttp({
        "/api/v2/stocks/historical": {"results": [{"symbol": "PRNR3", "data": {
            "historicalDataPrice": [
                {"date": previous_session, "open": 15.0, "high": 15.4, "low": 14.9, "close": 15.2, "volume": 30_000},
                {"date": session_open, "open": 16.0, "high": 16.2, "low": 15.9, "close": 16.1, "volume": 42_000},
                {"date": session_later, "open": 16.1, "high": 16.8, "low": 16.0, "close": 16.7, "volume": 55_000},
            ],
        }}]},
    })
    settings = Settings(brapi_token="configured", auth_cookie_secure=False)
    database = Database(settings)
    database.add_realtime_portfolio("PRNR3", "Priner Serviços Industriais", "B3")
    service = RealtimeMarketsService(settings, database, http)  # type: ignore[arg-type]

    response = service.portfolio_intraday("prnr3")

    assert response.symbol == "PRNR3"
    assert response.session_date == "2026-08-14"
    assert len(response.points) == 2
    assert response.open == 16.0
    assert response.current == 16.7
    assert response.high == 16.8
    assert response.low == 15.9
    assert response.change_percent == pytest.approx(4.375)
    assert http.calls[0]["params"]["interval"] == "5m"


def test_realtime_portfolio_intraday_uses_eodhd_for_us_stock() -> None:
    first = int(datetime(2026, 8, 14, 14, 30, tzinfo=timezone.utc).timestamp())
    last = int(datetime(2026, 8, 14, 19, 55, tzinfo=timezone.utc).timestamp())
    http = RoutingStubHttp({
        "/api/intraday/AMZN.US": [
            {"timestamp": first, "open": 224.0, "high": 225.0, "low": 223.6, "close": 224.8, "volume": 120_000},
            {"timestamp": last, "open": 224.8, "high": 229.0, "low": 224.5, "close": 228.4, "volume": 180_000},
        ],
    })
    settings = Settings(eodhd_api_token="configured", auth_cookie_secure=False)
    database = Database(settings)
    database.add_realtime_portfolio("AMZN", "Amazon.com Inc", "NASDAQ")
    service = RealtimeMarketsService(settings, database, http)  # type: ignore[arg-type]

    response = service.portfolio_intraday("AMZN")

    assert response.market == "NASDAQ"
    assert response.currency == "USD"
    assert response.current == 228.4
    assert response.source == "EODHD Intraday 5m"
    assert len(response.points) == 2
    assert "/api/intraday/AMZN.US" in http.calls[0]["url"]


def test_global_intraday_supports_b3_symbol_outside_my_portfolio() -> None:
    first = int(datetime(2026, 8, 14, 13, 0, tzinfo=timezone.utc).timestamp())
    last = int(datetime(2026, 8, 14, 15, 0, tzinfo=timezone.utc).timestamp())
    http = RoutingStubHttp({
        "/api/v2/stocks/historical": {"results": [{"symbol": "WEGE3", "data": {
            "historicalDataPrice": [
                {"date": first, "open": 40.0, "high": 40.5, "low": 39.8, "close": 40.2, "volume": 30_000},
                {"date": last, "open": 40.2, "high": 41.4, "low": 40.0, "close": 41.1, "volume": 42_000},
            ],
        }}]},
    })
    settings = Settings(brapi_token="configured", auth_cookie_secure=False)
    service = RealtimeMarketsService(settings, Database(settings), http)  # type: ignore[arg-type]

    response = service.instrument_intraday("WEGE3", market="B3", name="WEG")

    assert response.symbol == "WEGE3"
    assert response.name == "WEG"
    assert response.market == "B3"
    assert response.current == 41.1
    assert not service.database.list_realtime_portfolio()


def test_global_intraday_uses_brapi_for_fixed_b3_portfolio_symbol() -> None:
    first = int(datetime(2026, 8, 14, 13, 0, tzinfo=timezone.utc).timestamp())
    last = int(datetime(2026, 8, 14, 15, 0, tzinfo=timezone.utc).timestamp())
    http = RoutingStubHttp({
        "/api/v2/stocks/historical": {"results": [{"symbol": "PRNR3", "data": {
            "historicalDataPrice": [
                {"date": first, "open": 14.0, "high": 14.5, "low": 13.8, "close": 14.2, "volume": 30_000},
                {"date": last, "open": 14.2, "high": 15.4, "low": 14.0, "close": 15.1, "volume": 42_000},
            ],
        }}]},
    })
    settings = Settings(brapi_token="configured", auth_cookie_secure=False)
    service = RealtimeMarketsService(settings, Database(settings), http)  # type: ignore[arg-type]

    response = service.instrument_intraday("PRNR3", market="B3", name="Priner")

    assert response.symbol == "PRNR3"
    assert response.market == "B3"
    assert response.current == 15.1
    assert response.source == "Brapi Pro Intraday"
    assert "/api/v2/stocks/historical" in http.calls[0]["url"]


def test_global_intraday_resolves_master_luke_index_symbol() -> None:
    first = int(datetime(2026, 8, 14, 13, 0, tzinfo=timezone.utc).timestamp())
    last = int(datetime(2026, 8, 14, 15, 0, tzinfo=timezone.utc).timestamp())
    http = RoutingStubHttp({
        "/v8/finance/chart/ES%3DF": {"chart": {"result": [{
            "meta": {"currency": "USD", "exchangeTimezoneName": "America/New_York"},
            "timestamp": [first, last],
            "indicators": {"quote": [{
                "open": [6400.0, 6410.0], "high": [6420.0, 6440.0],
                "low": [6390.0, 6405.0], "close": [6410.0, 6435.0], "volume": [10_000, 12_000],
            }]},
        }]}},
    })
    settings = Settings(auth_cookie_secure=False)
    service = RealtimeMarketsService(settings, Database(settings), http)  # type: ignore[arg-type]

    response = service.instrument_intraday("S&P 500 Fut.", market="Future Index")

    assert response.market == "Future Index"
    assert response.name == "S&P 500 E-mini Futures"
    assert response.current == 6435.0
    assert response.source == "Yahoo Finance Intraday 5m"


@pytest.mark.parametrize(("symbol", "provider_symbol"), [
    ("US3Y", "US3Y.GBOND"),
    ("US10Y", "US10Y.GBOND"),
])
def test_global_hover_uses_eodhd_daily_history_for_treasury_yields(
    symbol: str,
    provider_symbol: str,
) -> None:
    http = RoutingStubHttp({
        f"/api/eod/{provider_symbol}": [
            {"date": "2026-08-13", "close": 3.711},
            {"date": "2026-08-14", "close": 3.742},
        ],
    })
    settings = Settings(eodhd_api_token="configured", auth_cookie_secure=False)
    service = RealtimeMarketsService(settings, Database(settings), http)  # type: ignore[arg-type]

    response = service.instrument_intraday(symbol, market="Indices")

    assert response.symbol == symbol
    assert response.series_kind == "daily"
    assert response.interval_minutes == 1440
    assert response.current == 3.742
    assert response.open == 3.711
    assert len(response.points) == 2
    assert response.source == "EODHD Government Bonds · Official daily closes"
    assert http.calls[0]["url"].endswith(f"/api/eod/{provider_symbol}")
    assert "yahoo" not in http.calls[0]["url"]


def test_realtime_portfolio_accepts_b3_etf_missing_from_stock_list() -> None:
    http = RoutingStubHttp({
        "/api/quote/list": {"stocks": []},
        "/api/v2/stocks/quote": {"results": [{
            "symbol": "BOVA11",
            "currency": "BRL",
            "regularMarketPrice": 142.50,
            "regularMarketPreviousClose": 140.00,
            "regularMarketVolume": 4_000_000,
        }]},
    })
    settings = Settings(brapi_token="configured", auth_cookie_secure=False)
    service = RealtimeMarketsService(settings, Database(settings), http)  # type: ignore[arg-type]

    added = service.add_portfolio_symbol("bova11")

    assert added.item_count == 1
    assert added.items[0].symbol == "BOVA11"
    assert added.items[0].market == "B3"
    assert added.items[0].price == 142.50
    assert added.items[0].change_percent == pytest.approx(1.7857, rel=1e-3)
    assert len([call for call in http.calls if "/api/v2/stocks/quote" in call["url"]]) == 1


def test_realtime_portfolio_accepts_nasdaq_and_nyse_arca_etfs() -> None:
    timestamp = 1785859200
    catalog = [
        {"Code": "QQQ", "Name": "Invesco QQQ Trust", "Exchange": "NASDAQ", "Type": "ETF", "Currency": "USD"},
        {"Code": "VOO", "Name": "Vanguard S&P 500 ETF", "Exchange": "NYSE ARCA", "Type": "ETF", "Currency": "USD"},
    ]
    quotes = [
        {"code": "QQQ.US", "timestamp": timestamp, "close": 590, "change_p": 1.1, "volume": 42_000_000},
        {"code": "VOO.US", "timestamp": timestamp, "close": 610, "change_p": -0.2, "volume": 7_000_000},
    ]
    http = RoutingStubHttp({
        "/api/exchange-symbol-list/US": catalog,
        "/api/real-time/AAPL.US": quotes,
    })
    settings = Settings(eodhd_api_token="configured", auth_cookie_secure=False)
    service = RealtimeMarketsService(settings, Database(settings), http)  # type: ignore[arg-type]

    service.add_portfolio_symbol("QQQ")
    added = service.add_portfolio_symbol("VOO")

    assert added.item_count == 2
    assert {(item.symbol, item.market) for item in added.items} == {("QQQ", "NASDAQ"), ("VOO", "NYSE")}
    assert {item.name for item in added.items} == {"Invesco QQQ Trust", "Vanguard S&P 500 ETF"}


def test_realtime_portfolio_replaces_ancient_bulk_quote_with_direct_quote() -> None:
    now = datetime.now(timezone.utc)
    stale_timestamp = int((now - timedelta(days=120)).timestamp())
    current_timestamp = int((now - timedelta(minutes=15)).timestamp())
    catalog = [{
        "Code": "SPCX",
        "Name": "Space Exploration Technologies Corp. Class A Common Stock",
        "Exchange": "NASDAQ",
        "Type": "Common Stock",
        "Currency": "USD",
    }]
    http = RoutingStubHttp({
        "/api/exchange-symbol-list/US": catalog,
        "/api/real-time/AAPL.US": [{
            "code": "SPCX.US",
            "timestamp": stale_timestamp,
            "close": 21.98,
            "change_p": 4.78,
            "volume": 0,
        }],
        "/api/real-time/SPCX.US": {
            "code": "SPCX.US",
            "timestamp": current_timestamp,
            "close": 143.34,
            "change_p": -1.9763,
            "volume": 83_583_757,
        },
    })
    settings = Settings(eodhd_api_token="configured", auth_cookie_secure=False)
    service = RealtimeMarketsService(settings, Database(settings), http)  # type: ignore[arg-type]

    added = service.add_portfolio_symbol("SPCX")

    assert added.item_count == 1
    assert added.items[0].price == 143.34
    assert added.items[0].change_percent == -1.9763
    assert added.items[0].status == "delayed"
    assert any("/api/real-time/SPCX.US" in call["url"] for call in http.calls)


def test_realtime_portfolio_accepts_otc_common_stock() -> None:
    timestamp = 1786720920
    catalog = [
        {
            "Code": "MHVYF",
            "Name": "Mitsubishi Heavy Industries Ltd.",
            "Exchange": "PINK",
            "Type": "Common Stock",
            "Currency": "USD",
        },
    ]
    quotes = [
        {
            "code": "MHVYF.US",
            "timestamp": timestamp,
            "close": 26.84,
            "previousClose": 26.99,
            "change_p": -0.5558,
            "volume": 200,
        },
    ]
    http = RoutingStubHttp({
        "/api/exchange-symbol-list/US": catalog,
        "/api/real-time/AAPL.US": quotes,
    })
    settings = Settings(eodhd_api_token="configured", auth_cookie_secure=False)
    service = RealtimeMarketsService(settings, Database(settings), http)  # type: ignore[arg-type]

    search = service.search_portfolio_symbols("mhvy")
    added = service.add_portfolio_symbol("MHVYF")

    assert search.item_count == 1
    assert search.items[0].symbol == "MHVYF"
    assert search.items[0].market == "OTC"
    assert search.items[0].exchange == "PINK"
    assert added.item_count == 1
    assert added.items[0].symbol == "MHVYF"
    assert added.items[0].name == "Mitsubishi Heavy Industries Ltd."
    assert added.items[0].market == "OTC"
    assert added.items[0].price == 26.84


def test_realtime_portfolio_search_suggests_stocks_and_etfs_by_ticker_or_name() -> None:
    catalog = [
        {"Code": "MSFT", "Name": "Microsoft Corporation", "Exchange": "NASDAQ", "Type": "Common Stock", "Currency": "USD"},
        {"Code": "VOO", "Name": "Vanguard S&P 500 ETF", "Exchange": "NYSE ARCA", "Type": "ETF", "Currency": "USD"},
    ]
    http = RoutingStubHttp({
        "/api/quote/list": {"stocks": [
            {"stock": "VALE3", "name": "Vale S.A.", "close": 64.2, "change": 0.8, "volume": 12_000_000},
            {"stock": "BOVA11", "name": "iShares Ibovespa ETF", "close": 142.5, "change": 0.3, "volume": 4_000_000},
        ]},
        "/api/exchange-symbol-list/US": catalog,
    })
    settings = Settings(brapi_token="configured", eodhd_api_token="configured", auth_cookie_secure=False)
    database = Database(settings)
    database.add_realtime_portfolio("VOO", "Vanguard S&P 500 ETF", "NYSE")
    service = RealtimeMarketsService(settings, database, http)  # type: ignore[arg-type]

    ticker_result = service.search_portfolio_symbols("vo")
    name_result = service.search_portfolio_symbols("micro")
    b3_result = service.search_portfolio_symbols("bov")

    assert ticker_result.items[0].symbol == "VOO"
    assert ticker_result.items[0].security_type == "ETF"
    assert ticker_result.items[0].already_tracked is True
    assert name_result.items[0].symbol == "MSFT"
    assert b3_result.items[0].symbol == "BOVA11"
    assert b3_result.items[0].market == "B3"
    assert ticker_result.sources == ["Brapi Pro", "EODHD"]


def test_realtime_portfolio_search_uses_c3po_registry_when_providers_are_unavailable() -> None:
    settings = Settings(auth_cookie_secure=False)
    database = Database(settings)
    database.register_ir_securities([
        {
            "market": "B3", "symbol": "PRNR3", "company_name": "Priner Serviços Industriais",
            "name_key": "PRINER SERVICOS INDUSTRIAIS", "exchange": "B3",
        },
        {
            "market": "US", "symbol": "MSFT", "company_name": "Microsoft Corporation",
            "name_key": "MICROSOFT CORPORATION", "exchange": "NASDAQ",
        },
    ])
    service = RealtimeMarketsService(settings, database, StubHttp({}))  # type: ignore[arg-type]

    b3_result = service.search_portfolio_symbols("pri")
    us_result = service.search_portfolio_symbols("micro")

    assert b3_result.items[0].symbol == "PRNR3"
    assert b3_result.items[0].market == "B3"
    assert us_result.items[0].symbol == "MSFT"
    assert us_result.items[0].market == "NASDAQ"
    assert b3_result.sources == ["C3PO issuer registry"]
    assert b3_result.errors == ["B3: RuntimeError", "US: RuntimeError"]


def test_service_records_successful_ingestion() -> None:
    settings = Settings(brapi_token="configured", eodhd_api_token="configured", auth_cookie_secure=False)
    database = Database(settings)
    http = StubHttp({"results": [{"symbol": "VALE3", "regularMarketPrice": 70.0}]})
    service = MarketDataService(settings, database, http=http)  # type: ignore[arg-type]

    quotes = service.fetch_quotes("brapi", ["VALE3"])
    health = service.health()[0]

    assert quotes[0].symbol == "VALE3"
    assert health.status == "healthy"
    assert isinstance(health.last_success_at, datetime)
    assert health.last_success_at.tzinfo is not None


def test_health_probe_records_eodhd_success_and_respects_cooldown() -> None:
    settings = Settings(brapi_token="", eodhd_api_token="configured", auth_cookie_secure=False)
    database = Database(settings)
    http = StubHttp({"code": "AAPL.US", "close": 230.0, "timestamp": 1_786_900_000})
    service = MarketDataService(settings, database, http=http)  # type: ignore[arg-type]

    first = service.probe_health()
    second = service.probe_health()

    eodhd = next(item for item in first if item.code == "eodhd")
    assert eodhd.status == "healthy"
    assert isinstance(eodhd.last_success_at, datetime)
    assert len(http.calls) == 1
    assert next(item for item in second if item.code == "eodhd").status == "healthy"


def test_b3_screener_returns_power_zone_candidates_ranked_by_tp_upside() -> None:
    now = datetime(2026, 8, 4, 20, 45, tzinfo=timezone.utc)
    symbols = [f"{chr(65 + index)}AAA3" for index in range(12)]
    catalog = {
        "results": [
            {
                "symbol": symbol,
                "name": f"Empresa {index}",
                "longName": f"Empresa Teste {index}",
                "sector": "Technology Services" if index % 2 else "Utilities",
                "subsector": "Teste",
                "logoUrl": f"https://icons.example/{symbol}.svg",
            }
            for index, symbol in enumerate(symbols)
        ]
    }
    settings = Settings(brapi_token="configured", auth_cookie_secure=False)
    service = B3ScreenerService(settings, Database(settings), StubHttp(catalog))  # type: ignore[arg-type]
    quotes = {
        symbol: NormalizedQuote(
            provider="brapi",
            symbol=symbol,
            provider_symbol=symbol,
            exchange="B3",
            currency="BRL",
            price=2 + index / 10,
            change_percent=index / 10,
            volume=2_000_000 + index * 100_000,
            market_cap=2_000_000_000 + index * 50_000_000,
            as_of=now,
            collected_at=now,
            quality_score=94,
        )
        for index, symbol in enumerate(symbols)
    }
    statistics_payload = {
        symbol: {
            "trailingPE": 5.0 + index,
            "forwardPE": 4.5 + index,
            "enterpriseToEbitda": 4.0 + index / 2,
            "pegRatio": 0.5 + index / 10,
            "priceToBook": 0.8 + index / 10,
            "beta": 0.8 + index / 20,
            "sharesOutstanding": 100_000_000,
            "trailingEps": 2.0 + index / 10,
            "bookValue": 8.0 + index / 10,
            "marketCap": 2_000_000_000 + index * 50_000_000,
        }
        for index, symbol in enumerate(symbols)
    }
    financial_payload = {
        symbol: {
            "returnOnEquity": 0.14 + index / 100,
            "profitMargins": 0.10 + index / 200,
            "ebitdaMargins": 0.18,
            "revenueGrowthAnnual": 0.05 + index / 200,
            "earningsGrowthAnnual": 0.06 + index / 150,
            "freeCashflow": 170_000_000 + index * 1_000_000,
            "operatingCashflow": 210_000_000 + index * 1_000_000,
            "ebitda": 200_000_000 + index * 2_000_000,
            "totalCash": 250_000_000,
            "totalDebt": 300_000_000,
            "debtToEquity": 0.8,
            "targetMeanPrice": 6.0 + index / 10,
            "numberOfAnalystOpinions": 8,
        }
        for index, symbol in enumerate(symbols)
    }
    service._quotes = lambda _: quotes  # type: ignore[method-assign]
    service._fundamental_map = lambda endpoint, _: statistics_payload if endpoint == "statistics" else financial_payload  # type: ignore[method-assign]
    service._eodhd_fundamental_map = lambda requested: {
        symbol: {
            "marketCap": 2_000_000_000 + index * 50_000_000,
            "trailingPE": 5.0 + index,
            "forwardPE": 4.5 + index,
            "enterpriseToEbitda": 4.0 + index / 2,
            "pegRatio": 0.5 + index / 10,
            "priceToBook": 0.8 + index / 10,
            "trailingEps": 2.0 + index / 10,
            "forwardEps": (2 + index / 10) / (4.5 + index),
            "bookValue": 8.0 + index / 10,
            "returnOnEquity": 0.14 + index / 100,
            "profitMargins": 0.10 + index / 200,
            "revenueGrowthAnnual": 0.05 + index / 200,
            "earningsGrowthAnnual": 0.06 + index / 150,
            "ebitda": 200_000_000 + index * 2_000_000,
            "targetMeanPrice": 6.0 + index / 10,
            "numberOfAnalystOpinions": 8,
            "updated_at": date.today().isoformat(),
        }
        for index, symbol in enumerate(symbols)
        if symbol in requested
    }  # type: ignore[method-assign]
    service._historical_map = lambda _: {
        symbol: {
            "adtv_90d": 25_000_000 + index * 1_000_000,
            "history_days": 63.0,
            "volatility_90d": 0.32 - index / 100,
            "support_60d": 1.90 + index / 10,
            "median_20d": 2.00 + index / 10,
            "low_20d": 1.85 + index / 10,
            "last_close": 2.00 + index / 10,
        }
        for index, symbol in enumerate(symbols)
    }  # type: ignore[method-assign]
    service._macro_context = lambda: {"selic": 0.12, "ipca12m": 0.045}  # type: ignore[method-assign]

    response = service.screen(refresh=True)
    assert response.universe_size == 12
    assert response.eligible_count == 12
    assert len(response.items) <= 10

    for index, row in enumerate(service._matrix_rows[:5]):
        row.update({
                "status": "full_match",
                "upside_percent": 50.0 - index,
                "expected_total_return_percent": 5.0 if index == 0 else 90.0 - index,
            "risk_score": 10.0 + index,
            "score": 95.0 - index,
            "valuation_confidence": 80.0,
            "method_dispersion_percent": 20.0,
            "price_vs_buy_in_percent": 0.0,
            "tp_validation_status": "validated",
            "tp_validation_score": 85.0,
            "tp_validation_reasons": [],
            "consensus_gap_percent": 10.0,
            "valuation_method_count": 5,
            "internal_method_count": 4,
        })
    ranked_items, _, risk_cutoff = service._rank(service._matrix_rows[:5], {"selic": 0.12})
    assert [item.rank for item in ranked_items] == list(range(1, len(ranked_items) + 1))
    assert [item.upside_percent for item in ranked_items] == sorted(
        [item.upside_percent for item in ranked_items], reverse=True
    )
    assert all(item.our_tp > 0 and item.buy_in > 0 for item in ranked_items)
    assert all(item.pe is not None and item.ev_ebitda is not None and item.peg is not None for item in ranked_items)
    assert all(item.status == "full_match" for item in ranked_items)
    assert all(item.upside_percent >= 18 for item in ranked_items)
    assert any(item.expected_total_return_percent < 18 for item in ranked_items)
    assert all(item.valuation_confidence >= 70 for item in ranked_items)
    assert all(item.method_dispersion_percent <= 45 for item in ranked_items)
    assert all(item.risk_score < risk_cutoff for item in ranked_items)
    assert all(item.average_daily_value_90d and item.average_daily_value_90d >= 5_000_000 for item in ranked_items)
    assert response.methodology_version == METHODOLOGY_VERSION
    assert all(row["buy_in"] <= row["buy_in_models"]["Market Structure"] for row in service._matrix_rows)
    assert response.criteria["universe"].startswith("350 liquid B3 stocks")
    assert "Selic + 6 p.p." in response.criteria["tp_upside"]
    weights = service._score_weights({"selic": 0.12})
    assert weights == {"tp_upside": 0.35, "inverse_risk": 0.25, "quality": 0.15, "confidence": 0.15, "entry": 0.10}
    assert round(sum(weights.values()), 10) == 1.0

    consensus_rows = [row for row in service._matrix_rows if row.get("public_consensus_tp")]
    assert consensus_rows
    for row in consensus_rows:
        consensus_weight = service._consensus_weight(row)
        assert row["consensus_weight_percent"] == pytest.approx(consensus_weight * 100)
        expected_blend = row["internal_tp"] * (1 - consensus_weight) + row["public_consensus_tp"] * consensus_weight
        assert abs(row["our_tp"] - expected_blend) < 1e-8

    provisional_row = service._matrix_rows[5]
    provisional_row.update({
        "tp_validation_status": "review_required",
        "tp_validation_score": 58.0,
        "tp_validation_reasons": ["Insufficient public analyst consensus"],
        "valuation_confidence": 65.0,
        "method_dispersion_percent": 35.0,
        "data_source_count": 2,
        "source_comparison_count": 3,
        "source_agreement_percent": 72.0,
        "fundamentals_as_of": date.today().isoformat(),
        "internal_method_count": 3,
    })
    provisional_ranked, _, _ = service._rank([provisional_row], {"selic": 0.12})
    assert provisional_ranked == []

    matrix = service.matrix()
    assert matrix.methodology_name == response.methodology
    assert matrix.methodology_version == response.methodology_version
    assert matrix.universe_size == 12
    assert matrix.source_eligible_count == 12
    assert 0 < matrix.item_count <= matrix.source_eligible_count
    assert matrix.tp_upside_cutoff_percent == 18.0
    assert matrix.quote_refresh_seconds == 60
    assert all(0 <= item.risk_score <= 100 for item in matrix.items)
    assert matrix.validated_count >= 1
    assert matrix.provisional_count >= 1
    assert matrix.validated_count + matrix.provisional_count == matrix.item_count
    assert any(item.signal_quality == "provisional" for item in matrix.items)
    assert all(item.tp_validation_score >= 65 for item in matrix.items if item.signal_quality == "validated")
    assert all(item.method_dispersion_percent >= 0 for item in matrix.items)
    assert all(0 <= item.x_percent <= 100 and 0 <= item.y_percent <= 100 for item in matrix.items)
    assert all(
        service._quadrant(item.upside_percent, item.risk_score, 18.0, risk_cutoff)
        == "high_return_low_risk"
        for item in ranked_items
    )


def test_provisional_matrix_signal_requires_two_source_evidence() -> None:
    row = {
        "price": 20.0,
        "our_tp": 30.0,
        "buy_in": 18.0,
        "internal_method_count": 3,
        "valuation_confidence": 62.0,
        "method_dispersion_percent": 40.0,
        "data_source_count": 2,
        "source_comparison_count": 3,
        "source_agreement_percent": 68.0,
        "fundamentals_as_of": date.today().isoformat(),
    }

    eligible, reasons = B3ScreenerService._provisional_eligibility(row)
    one_source, one_source_reasons = B3ScreenerService._provisional_eligibility({**row, "data_source_count": 1})

    assert eligible is True
    assert reasons == []
    assert one_source is False
    assert "A second fundamental source is unavailable" in one_source_reasons


def test_cvm_first_pending_review_never_blocks_matrix_eligibility() -> None:
    row = {
        "price": 20.0,
        "our_tp": 30.0,
        "buy_in": 18.0,
        "internal_method_count": 3,
        "valuation_confidence": 62.0,
        "method_dispersion_percent": 40.0,
        "data_source_count": 2,
        "source_comparison_count": 3,
        "source_agreement_percent": 68.0,
        "fundamentals_as_of": date.today().isoformat(),
        "ir_status": "pending_review",
    }

    eligible, reasons = B3ScreenerService._provisional_eligibility(row)

    assert eligible is True
    assert reasons == []


def test_provisional_fundamentals_follow_quarterly_reporting_cadence() -> None:
    base = {
        "price": 20.0,
        "our_tp": 30.0,
        "buy_in": 18.0,
        "internal_method_count": 3,
        "valuation_confidence": 62.0,
        "method_dispersion_percent": 40.0,
        "data_source_count": 2,
        "source_comparison_count": 3,
        "source_agreement_percent": 68.0,
    }

    quarterly, quarterly_reasons = B3ScreenerService._provisional_eligibility({
        **base,
        "fundamentals_as_of": (date.today() - timedelta(days=170)).isoformat(),
    })
    obsolete, obsolete_reasons = B3ScreenerService._provisional_eligibility({
        **base,
        "fundamentals_as_of": (date.today() - timedelta(days=300)).isoformat(),
    })

    assert quarterly is True
    assert quarterly_reasons == []
    assert obsolete is False
    assert any("270 days" in reason for reason in obsolete_reasons)


def test_selic_uses_new_copom_decision_while_bcb_series_is_stale() -> None:
    announced = B3ScreenerService._effective_selic(
        provider_value=0.1425,
        bcb_value=0.1425,
        bcb_as_of=date(2026, 6, 18),
        now=datetime(2026, 8, 5, 21, 31, tzinfo=timezone.utc),
    )
    refreshed = B3ScreenerService._effective_selic(
        provider_value=0.1425,
        bcb_value=0.14,
        bcb_as_of=date(2026, 8, 6),
        now=datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc),
    )

    assert announced == 0.14
    assert refreshed == 0.14
    assert B3ScreenerService._tp_upside_cutoff_percent({"selic": announced}) == pytest.approx(20.0)


def test_effective_selic_warns_when_the_copom_governor_is_long_past_due(caplog: pytest.LogCaptureFixture) -> None:
    """Root-caused 2026-08-20 (B3 TP audit): the hardcoded LATEST_COPOM_SELIC
    governor requires a manual bump after each COPOM meeting; nothing
    previously surfaced when BCB stayed silent for far longer than a COPOM
    cycle, so a missed update would go unnoticed indefinitely."""
    with caplog.at_level("WARNING", logger="app.market_data.b3_screener"):
        B3ScreenerService._effective_selic(
            provider_value=None,
            bcb_value=None,
            bcb_as_of=None,
            now=datetime(2026, 10, 15, tzinfo=timezone.utc),
        )
    assert "Selic governor" in caplog.text


def test_effective_selic_does_not_warn_shortly_after_the_copom_decision(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING", logger="app.market_data.b3_screener"):
        result = B3ScreenerService._effective_selic(
            provider_value=None,
            bcb_value=None,
            bcb_as_of=None,
            now=datetime(2026, 8, 10, tzinfo=timezone.utc),
        )
    assert result == 0.14
    assert "Selic governor" not in caplog.text


def test_check_selic_against_market_yield_warns_on_a_large_divergence(caplog: pytest.LogCaptureFixture) -> None:
    """Data-source audit (2026-08-20): Brapi Pro's Tesouro Direto endpoints
    were never used at all, even though they're included in the plan we
    already pay for. Used as a divergence cross-check against the Selic-
    derived risk-free rate -- purely informational, catches the exact
    "feed silently goes stale/wrong" failure mode this session spent all
    day chasing elsewhere in Selic/peer-median/consensus code.
    """
    settings = Settings(brapi_token="configured", auth_cookie_secure=False)
    http = StubHttp({
        "results": [{
            "symbol": "tesouro-prefixado-01012037", "bondType": "Tesouro Prefixado",
            "indexer": "prefixado", "maturityDate": "2037-01-01", "durationDays": 4000,
            "buyRate": 0.13, "sellRate": 0.135,
        }],
    })
    service = B3ScreenerService(settings, Database(settings), http)  # type: ignore[arg-type]

    with caplog.at_level("WARNING", logger="app.market_data.b3_screener"):
        service._check_selic_against_market_yield(0.02)  # far below the observed 13.5% market yield

    assert "diverges" in caplog.text


def test_check_selic_against_market_yield_is_silent_on_a_normal_term_spread(caplog: pytest.LogCaptureFixture) -> None:
    settings = Settings(brapi_token="configured", auth_cookie_secure=False)
    http = StubHttp({
        "results": [{
            "symbol": "tesouro-prefixado-01012037", "bondType": "Tesouro Prefixado",
            "indexer": "prefixado", "maturityDate": "2037-01-01", "durationDays": 4000,
            "buyRate": 0.13, "sellRate": 0.135,
        }],
    })
    service = B3ScreenerService(settings, Database(settings), http)  # type: ignore[arg-type]

    with caplog.at_level("WARNING", logger="app.market_data.b3_screener"):
        service._check_selic_against_market_yield(0.14)  # a plausible term spread vs. the 13.5% observed yield

    assert "diverges" not in caplog.text


def test_check_selic_cross_check_normalizes_percentage_point_bond_rates(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = Settings(brapi_token="configured", auth_cookie_secure=False)
    http = StubHttp({
        "results": [{
            "symbol": "tesouro-prefixado-01012037",
            "bondType": "Tesouro Prefixado",
            "indexer": "prefixado",
            "maturityDate": "2037-01-01",
            "durationDays": 4000,
            "buyRate": 14.79,
            "sellRate": 14.81,
        }],
    })
    service = B3ScreenerService(settings, Database(settings), http)  # type: ignore[arg-type]

    with caplog.at_level("WARNING", logger="app.market_data.b3_screener"):
        service._check_selic_against_market_yield(0.14)

    assert "diverges" not in caplog.text
    assert "1481" not in caplog.text


def test_disclosure_risk_signal_scales_by_materiality_and_zeroes_when_current() -> None:
    """Root-caused 2026-08-20 (B3 TP audit): disclosure materiality was
    computed and persisted per filing but never fed into governance_risk —
    a high-materiality pending disclosure scored identically to a routine
    low-materiality one."""
    assert B3ScreenerService._disclosure_risk_signal("current", "high") == 0.0
    assert B3ScreenerService._disclosure_risk_signal("unavailable", "high") == 0.0
    assert B3ScreenerService._disclosure_risk_signal("pending_review", "high") == 1.0
    assert B3ScreenerService._disclosure_risk_signal("pending_review", "medium") == 0.5
    assert B3ScreenerService._disclosure_risk_signal("pending_review", "low") == 0.2
    assert B3ScreenerService._disclosure_risk_signal("pending_review", None) == 0.5


def test_matrix_risk_score_rises_with_a_high_materiality_pending_disclosure() -> None:
    base_row = {
        "valuation_profile": "general",
        "beta": 1.0,
        "volatility_90d": 0.30,
        "debt_to_equity": 1.0,
        "earnings_growth": 0.10,
        "profit_margin": 0.12,
        "adtv_90d": 20_000_000,
        "insider_net_signal": 0.0,
    }
    quiet = B3ScreenerService._matrix_risk_score({**base_row, "pending_disclosure_risk": 0.0})
    material = B3ScreenerService._matrix_risk_score({**base_row, "pending_disclosure_risk": 1.0})
    assert material > quiet
    assert material - quiet == pytest.approx(DISCLOSURE_GOVERNANCE_MAX_SWING * 0.10)


def test_expected_12m_return_does_not_assume_immediate_full_convergence():
    raw_valuation_gap = (70 / 100 - 1) * 100
    expected_return = B3ScreenerService._expected_12m_return(
        price=100,
        target_price=70,
        expected_dividend=2,
        sustainable_growth=0.05,
        convergence_years=5,
    )
    faster_convergence = B3ScreenerService._expected_12m_return(
        price=100,
        target_price=70,
        expected_dividend=2,
        sustainable_growth=0.05,
        convergence_years=3,
    )

    assert raw_valuation_gap == pytest.approx(-30)
    assert 0 < expected_return < 10
    assert expected_return > faster_convergence


def test_convergence_weight_increases_with_evidence():
    provisional = B3ScreenerService._convergence_weight(55, 65, 0)
    validated = B3ScreenerService._convergence_weight(80, 15, 0)
    consensus_confirmed = B3ScreenerService._convergence_weight(80, 15, 20)

    assert provisional < validated < consensus_confirmed


def test_quality_compounder_profile_uses_durable_growth_through_a_soft_quarter():
    durable = {
        "valuation_profile": "general",
        "roe": 0.30,
        "profit_margin": 0.15,
        "ebitda_margin": 0.20,
        "debt_to_equity": 0.50,
        "revenue_growth": -0.006,
        "earnings_growth": -0.021,
        "revenue_cagr_5y": 0.14,
        "earnings_cagr_5y": 0.18,
        "annual_growth_observation_count": 6,
        "fcf_raw": 100.0,
    }
    temporary = {**durable, "earnings_growth": -0.20}
    assert B3ScreenerService._refine_valuation_profile(durable) == "quality_compounder"
    assert B3ScreenerService._refine_valuation_profile(temporary) == "general"


def test_annual_growth_profile_calculates_multi_year_cagr():
    fundamentals = {
        "annualIncome": [
            {"date": "2025-12-31", "totalRevenue": 200.0, "netIncome": 40.0},
            {"date": "2024-12-31", "totalRevenue": 175.0, "netIncome": 34.0},
            {"date": "2023-12-31", "totalRevenue": 150.0, "netIncome": 28.0},
            {"date": "2022-12-31", "totalRevenue": 125.0, "netIncome": 22.0},
            {"date": "2021-12-31", "totalRevenue": 100.0, "netIncome": 20.0},
        ]
    }

    profile = B3ScreenerService._annual_growth_profile(fundamentals)

    assert profile["annual_growth_observation_count"] == 5
    assert profile["revenue_cagr_5y"] == pytest.approx(2 ** 0.25 - 1)
    assert profile["earnings_cagr_5y"] == pytest.approx(2 ** 0.25 - 1)


def test_consensus_is_reconciled_across_b3_share_classes_and_units():
    rows = [
        {
            "symbol": "SAPR3", "issuer": "SAPR", "price": 7.55,
            "brapi_consensus_tp": None, "brapi_analysts": 0,
            "eodhd_consensus_tp": None, "eodhd_analysts": 0,
        },
        {
            "symbol": "SAPR4", "issuer": "SAPR", "price": 6.87,
            "brapi_consensus_tp": None, "brapi_analysts": 0,
            "eodhd_consensus_tp": 30.50, "eodhd_analysts": 6,
        },
        {
            "symbol": "SAPR11", "issuer": "SAPR", "price": 34.81,
            "brapi_consensus_tp": None, "brapi_analysts": 0,
            "eodhd_consensus_tp": 42.1573, "eodhd_analysts": 9,
        },
    ]

    B3ScreenerService._reconcile_issuer_consensus(rows)

    expected_ratio = 42.1573 / 34.81
    assert rows[1]["public_consensus_tp"] == pytest.approx(6.87 * expected_ratio)
    assert rows[1]["consensus_origin_symbol"] == "SAPR11"
    assert rows[1]["analyst_count"] == 9
    assert rows[1]["public_consensus_tp"] < 10
    assert rows[0]["public_consensus_tp"] == pytest.approx(7.55 * expected_ratio)


def test_targeted_valuation_looks_up_the_issuer_unit_for_public_consensus() -> None:
    assert B3ScreenerService._targeted_consensus_reference_symbols("IGTI3") == ["IGTI11"]
    assert B3ScreenerService._targeted_consensus_reference_symbols("IGTI4") == ["IGTI11"]
    assert B3ScreenerService._targeted_consensus_reference_symbols("SAPR4") == ["SAPR11"]
    assert B3ScreenerService._targeted_consensus_reference_symbols("IGTI11") == []


def test_targeted_catalog_normalizes_fractional_unit_to_standard_ticker() -> None:
    catalog = B3ScreenerService._targeted_catalog(
        [{
            "symbol": "IGTI11F",
            "longName": "Iguatemi SA Units Cons of 1 Sh + 2 Pfd Shs",
            "subType": "stock",
        }],
        "IGTI11",
    )

    assert len(catalog) == 1
    assert catalog[0]["symbol"] == "IGTI11"
    assert catalog[0]["longName"].startswith("Iguatemi")


def test_targeted_catalog_does_not_alias_an_unrelated_fractional_ticker() -> None:
    assert B3ScreenerService._targeted_catalog(
        [{"symbol": "ITUB4F"}],
        "IGTI11",
    ) == []


def test_targeted_catalog_prefers_standard_ticker_over_fractional_listing() -> None:
    catalog = B3ScreenerService._targeted_catalog(
        [
            {"symbol": "IGTI11F", "name": "Fractional"},
            {"symbol": "IGTI11", "name": "Standard"},
        ],
        "IGTI11",
    )

    assert catalog == [{"symbol": "IGTI11", "name": "Standard"}]


def test_dividend_yield_reconciliation_rejects_implausible_secondary_value():
    assert B3ScreenerService._reconcile_dividend_yield(0.02, 0.2818) == pytest.approx(0.02)
    assert B3ScreenerService._reconcile_dividend_yield(0.04, 0.042) == pytest.approx(0.0408)


def test_forward_pe_requires_eps_support_for_extreme_compression():
    assert B3ScreenerService._validated_forward_pe(1.60, 10.10, 0, 7.55) is None
    implied_eps = 7.55 / 1.60
    assert B3ScreenerService._validated_forward_pe(1.60, 10.10, implied_eps, 7.55) == pytest.approx(1.60)


def test_shared_valuation_is_invalidated_by_a_new_official_event(tmp_path, monkeypatch):
    settings = Settings(database_url="", migrations_dir=tmp_path)
    database = Database(settings)
    database.register_ir_securities([{
        "market": "B3", "symbol": "TEST3", "company_name": "Companhia Teste",
        "name_key": "COMPANHIA TESTE", "exchange": "B3",
    }])
    company = database.list_ir_companies("B3")[0]
    basis_at = datetime(2026, 8, 14, 10, tzinfo=timezone.utc)
    published_at = basis_at + timedelta(hours=1)
    database.save_ir_events([{
        "source_code": "cvm", "external_id": "test3-new-result", "company_id": company["id"],
        "market": "B3", "symbol": "TEST3", "company_name": company["company_name"],
        "event_type": "Financial Results", "title": "Resultados 2T26", "summary": "Official filing",
        "published_at": published_at, "published_time_precision": "datetime",
        "reference_date": date(2026, 6, 30), "official_url": "https://dados.cvm.gov.br/",
        "document_url": None, "materiality": "high", "valuation_relevant": True,
        "valuation_status": "pending_review", "raw_metadata": {}, "collected_at": published_at,
    }])
    screener = B3ScreenerService(settings, database, StubHttp({}))
    screener._matrix_rows = [{"symbol": "TEST3", "our_tp": 10.0}]
    screener._matrix_basis_at = basis_at

    def refresh(symbols):
        assert symbols == ["TEST3"]
        screener._matrix_rows = [{"symbol": "TEST3", "our_tp": 12.0}]
        return {"updated": ["TEST3"], "targeted_only": [], "missing": []}

    monkeypatch.setattr(screener, "refresh_symbols", refresh)

    assert screener.valuation_for("TEST3", build_if_missing=True)["our_tp"] == 12.0


def test_ir_refresh_preserves_matrix_row_when_provider_is_temporarily_incomplete(tmp_path, monkeypatch):
    settings = Settings(database_url="", migrations_dir=tmp_path)
    database = Database(settings)
    database.register_ir_securities([{
        "market": "B3", "symbol": "TEST3", "company_name": "Companhia Teste",
        "name_key": "COMPANHIA TESTE", "exchange": "B3",
    }])
    company = database.list_ir_companies("B3")[0]
    published_at = datetime(2026, 8, 14, 12, tzinfo=timezone.utc)
    database.save_ir_events([{
        "source_code": "cvm", "external_id": "test3-material-fact", "company_id": company["id"],
        "market": "B3", "symbol": "TEST3", "company_name": company["company_name"],
        "event_type": "Material Fact", "title": "Fato relevante", "summary": "Official filing",
        "published_at": published_at, "published_time_precision": "datetime",
        "reference_date": None, "official_url": "https://dados.cvm.gov.br/",
        "document_url": None, "materiality": "high", "valuation_relevant": True,
        "valuation_status": "pending_review", "raw_metadata": {}, "collected_at": published_at,
    }])
    screener = B3ScreenerService(settings, database, StubHttp({}))
    screener._matrix_rows = [{
        "symbol": "TEST3", "our_tp": 10.0, "fundamentals_as_of": "2026-03-31",
        "ir_status": "current", "latest_ir_event_at": None, "latest_ir_event_type": None,
    }]
    screener._matrix_universe_size = 1
    monkeypatch.setattr(screener, "_build_targeted_valuation", lambda symbol: None)
    monkeypatch.setattr(screener, "_candidate_response", lambda *args: object())
    monkeypatch.setattr(screener, "_persist_snapshot", lambda *args: None)

    result = screener.refresh_symbols(["TEST3"])

    assert result == {"updated": [], "targeted_only": ["TEST3"], "missing": []}
    assert screener._matrix_rows[0]["our_tp"] == 10.0
    assert screener._matrix_rows[0]["ir_status"] == "pending_review"
    assert screener._matrix_rows[0]["latest_ir_event_type"] == "Material Fact"
