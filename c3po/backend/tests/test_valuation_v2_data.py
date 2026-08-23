from datetime import datetime, timedelta, timezone

import pytest

from app.config import get_settings
from app.database import Database
from app.market_data.fmp import FmpClient
from app.valuation_v2_data import ValuationV2DataService


class StubHttp:
    def __init__(self, results: dict[str, object]) -> None:
        self.results = results
        self.calls: list[tuple[str, dict]] = []

    def get_json(self, url, *, params=None, headers=None):
        self.calls.append((url, dict(params or {})))
        for fragment, payload in self.results.items():
            if fragment in url:
                return payload(params) if callable(payload) else payload
        return []


def _future_fy(years_ahead: int = 1) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=365 * years_ahead)).date().isoformat()


def _past_fy(years_back: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=365 * years_back)).date().isoformat()


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


def _full_fmp_stub() -> dict[str, object]:
    return {
        "stock-peers": [
            {"symbol": "MSFT", "companyName": "Microsoft", "price": 500.0, "mktCap": 3.7e12},
            {"symbol": "GOOGL", "companyName": "Alphabet", "price": 210.0, "mktCap": 2.6e12},
            {"symbol": "META", "companyName": "Meta", "price": 700.0, "mktCap": 1.8e12},
            {"symbol": "NVDA", "companyName": "NVIDIA", "price": 180.0, "mktCap": 4.4e12},
        ],
        "analyst-estimates": [
            {"date": _future_fy(1), "revenueAvg": 450e9, "ebitdaAvg": 150e9, "epsAvg": 8.2,
             "epsLow": 7.1, "epsHigh": 9.0, "numAnalystsRevenue": 22, "numAnalystsEps": 25},
            {"date": _future_fy(2), "revenueAvg": 480e9, "ebitdaAvg": 160e9, "epsAvg": 9.1,
             "numAnalystsRevenue": 18, "numAnalystsEps": 20},
            {"date": _past_fy(1), "revenueAvg": 400e9, "epsAvg": 7.0},
        ],
        "stable/ratios": [
            {"date": _past_fy(offset), "priceToEarningsRatio": 25.0 + offset,
             "priceToBookRatio": 40.0, "enterpriseValueMultiple": 20.0 - offset,
             "returnOnEquity": 1.4, "netProfitMargin": 0.25, "debtToEquityRatio": 1.5,
             "dividendYield": 0.005}
            for offset in range(1, 8)
        ],
        "key-metrics": [
            {"date": _past_fy(offset), "marketCap": 3e12, "returnOnInvestedCapital": 0.45,
             "revenuePerShare": 25.0, "freeCashFlowPerShare": 6.5, "netIncomePerShare": 6.1}
            for offset in range(1, 8)
        ],
    }


def test_fmp_client_parses_the_four_v2_endpoint_families():
    http = StubHttp(_full_fmp_stub())
    client = FmpClient("https://fmp.test", "token", http)  # type: ignore[arg-type]

    packet = client.valuation_v2_packet("AAPL")

    assert [peer["symbol"] for peer in packet["peers"]] == ["MSFT", "GOOGL", "META", "NVDA"]
    estimates = packet["analyst_estimates_annual"]
    assert [row["fiscal_year_end"] for row in estimates] == sorted(
        row["fiscal_year_end"] for row in estimates
    )
    assert next(row for row in estimates if row["eps_avg"] == 8.2)["analysts_eps"] == 25
    assert len(packet["ratios_annual"]) == 7
    assert packet["ratios_annual"][0]["pe"] == 26.0
    assert packet["key_metrics_annual"][0]["roic"] == 0.45
    assert {status["status"] for status in packet["provider_status"].values()} == {"ok"}


def test_fmp_client_supports_the_legacy_peers_list_shape_and_failures():
    http = StubHttp({"stock-peers": [{"symbol": "AAPL", "peersList": ["MSFT", "GOOGL"]}]})
    client = FmpClient("https://fmp.test", "token", http)  # type: ignore[arg-type]
    assert [peer["symbol"] for peer in client.stock_peers("AAPL")] == ["MSFT", "GOOGL"]

    def boom(_params):
        raise RuntimeError("apiKey=secret must never leak")

    failing = FmpClient("https://fmp.test", "token", StubHttp({"stock-peers": boom, "stable/ratios": boom, "analyst-estimates": boom, "key-metrics": boom}))  # type: ignore[arg-type]
    packet = failing.valuation_v2_packet("AAPL")
    assert packet["peers"] == []
    assert packet["ratios_annual"] == []
    assert packet["analyst_estimates_annual"] == []
    assert {status["status"] for status in packet["provider_status"].values()} == {"error"}
    assert "secret" not in str(packet)


def test_refresh_daily_persists_packets_with_anchor_coverage_accounting():
    settings = get_settings().model_copy(update={"fmp_api_token": "token"})
    database = Database(settings)
    _seed_universe(database, "NASDAQ", [
        {"symbol": "AAPL", "security_type": "Stock", "market_cap": 3e12},
        {"symbol": "SOME_ETF", "security_type": "ETF", "market_cap": 1e11},
    ])
    http = StubHttp(_full_fmp_stub())
    service = ValuationV2DataService(settings, database, http)  # type: ignore[arg-type]

    counts = service.refresh_daily("NASDAQ")

    assert counts == {
        "universe": 1,
        "attempted": 1,
        "covered": 1,
        "all_anchors": 1,
        "provider_error_symbols": 0,
    }
    packet = service.packets("NASDAQ")["AAPL"]
    coverage = packet["coverage"]
    assert coverage["peers_ok"] is True and coverage["peer_count"] == 4
    assert coverage["estimates_ok"] is True and coverage["forward_fiscal_years"] == 2
    assert packet["fy1_estimate"]["fiscal_year_end"] < packet["fy2_estimate"]["fiscal_year_end"]
    assert coverage["history_ok"] is True and coverage["history_years"] == 7
    summary = service.coverage_summary("NASDAQ")
    assert summary == {
        "universe": 1,
        "attempted": 1,
        "covered": 1,
        "uncovered": 0,
        "provider_complete": 1,
        "provider_error_symbols": 0,
        "endpoint_errors": 0,
        "endpoint_responses": 4,
        "peers_ok": 1,
        "estimates_ok": 1,
        "history_ok": 1,
        "all_anchors": 1,
    }


def test_b3_symbols_use_the_sa_suffix_and_keep_local_symbol_keys():
    settings = get_settings().model_copy(update={"fmp_api_token": "token"})
    database = Database(settings)
    _seed_universe(database, "B3", [{"symbol": "PETR4", "market_cap": 4e11}])
    http = StubHttp(_full_fmp_stub())
    service = ValuationV2DataService(settings, database, http)  # type: ignore[arg-type]

    service.refresh_daily("B3")

    peer_calls = [params for url, params in http.calls if "stock-peers" in url]
    assert peer_calls and peer_calls[0]["symbol"] == "PETR4.SA"
    packet = service.packets("B3")["PETR4"]
    assert packet["provider_symbol"] == "PETR4.SA"
    assert packet["symbol"] == "PETR4"


def test_b3_peer_symbols_preserve_provider_and_canonical_forms():
    http = StubHttp({
        "stock-peers": [
            {"symbol": "BRAV3.SA", "companyName": "Brava Energia"},
            {"symbol": "PRIO3.SA", "companyName": "PRIO"},
        ],
    })
    client = FmpClient("https://fmp.test", "token", http)  # type: ignore[arg-type]

    peers = client.stock_peers("PETR4.SA")

    assert [(peer["symbol"], peer["canonical_symbol"]) for peer in peers] == [
        ("BRAV3.SA", "BRAV3"),
        ("PRIO3.SA", "PRIO3"),
    ]


def test_missing_anchors_are_recorded_not_invented():
    settings = get_settings().model_copy(update={"fmp_api_token": "token"})
    database = Database(settings)
    _seed_universe(database, "NYSE", [{"symbol": "TINY", "security_type": "Stock", "market_cap": 1e9}])
    http = StubHttp({
        "stock-peers": [{"symbol": "PEER1"}, {"symbol": "PEER2"}],  # below minimum of 4
        "analyst-estimates": [],
        "stable/ratios": [
            {"date": _past_fy(1), "priceToEarningsRatio": 12.0},
            {"date": _past_fy(2), "priceToEarningsRatio": 11.0},
        ],
        "key-metrics": [],
    })
    service = ValuationV2DataService(settings, database, http)  # type: ignore[arg-type]

    counts = service.refresh_daily("NYSE")

    assert counts["all_anchors"] == 0
    coverage = service.packets("NYSE")["TINY"]["coverage"]
    assert coverage["has_any_data"] is True
    assert coverage["provider_complete"] is True
    assert coverage["provider_error_count"] == 0
    assert coverage["peer_count"] == 2 and coverage["peers_ok"] is False
    assert coverage["forward_fiscal_years"] == 0 and coverage["estimates_ok"] is False
    assert coverage["fy1_available"] is False and coverage["fy2_available"] is False
    assert coverage["history_years"] == 2 and coverage["history_ok"] is False


def test_refresh_is_a_noop_without_fmp_credentials():
    settings = get_settings().model_copy(update={"fmp_api_token": ""})
    database = Database(settings)
    _seed_universe(database, "NASDAQ", [{"symbol": "AAPL", "security_type": "Stock", "market_cap": 3e12}])
    http = StubHttp({})
    service = ValuationV2DataService(settings, database, http)  # type: ignore[arg-type]

    assert service.refresh_daily("NASDAQ") == {
        "universe": 0,
        "attempted": 0,
        "covered": 0,
        "all_anchors": 0,
        "provider_error_symbols": 0,
    }
    assert http.calls == []
    assert service.packets("NASDAQ") == {}


def test_total_provider_outage_does_not_replace_the_last_good_snapshot():
    settings = get_settings().model_copy(update={"fmp_api_token": "token"})
    database = Database(settings)
    _seed_universe(database, "NASDAQ", [
        {"symbol": "AAPL", "security_type": "Stock", "market_cap": 3e12},
    ])
    good = ValuationV2DataService(settings, database, StubHttp(_full_fmp_stub()))  # type: ignore[arg-type]
    good.refresh_daily("NASDAQ")
    previous = good.packets("NASDAQ")

    def boom(_params):
        raise RuntimeError("request URL contains apiKey=must-not-leak")

    outage = ValuationV2DataService(settings, database, StubHttp({
        "stock-peers": boom,
        "analyst-estimates": boom,
        "stable/ratios": boom,
        "key-metrics": boom,
    }))  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="provider outage"):
        outage.refresh_daily("NASDAQ")

    assert outage.packets("NASDAQ") == previous


def test_partial_provider_failure_is_persisted_without_hiding_other_anchors():
    settings = get_settings().model_copy(update={"fmp_api_token": "token"})
    database = Database(settings)
    _seed_universe(database, "NYSE", [
        {"symbol": "JPM", "security_type": "Stock", "market_cap": 8e11},
    ])

    def boom(_params):
        raise RuntimeError("provider unavailable")

    payloads = _full_fmp_stub()
    payloads["stock-peers"] = boom
    service = ValuationV2DataService(settings, database, StubHttp(payloads))  # type: ignore[arg-type]

    counts = service.refresh_daily("NYSE")

    assert counts["covered"] == 1
    assert counts["provider_error_symbols"] == 1
    packet = service.packets("NYSE")["JPM"]
    assert packet["provider_status"]["peers"]["status"] == "error"
    assert packet["provider_status"]["ratios"]["status"] == "ok"
    assert packet["coverage"]["provider_complete"] is False
    assert service.coverage_summary("NYSE")["endpoint_errors"] == 1


def test_numeric_zeroes_are_not_replaced_by_legacy_fallback_fields():
    http = StubHttp({
        "stable/ratios": [{
            "date": _past_fy(1),
            "priceToEarningsRatio": 0,
            "priceEarningsRatio": 99,
            "debtToEquityRatio": 0,
            "debtEquityRatio": 88,
        }],
        "key-metrics": [{
            "date": _past_fy(1),
            "returnOnInvestedCapital": 0,
            "roic": 77,
        }],
    })
    client = FmpClient("https://fmp.test", "token", http)  # type: ignore[arg-type]

    ratios = client.ratios_annual("ZERO")
    metrics = client.key_metrics_annual("ZERO")

    assert ratios[0]["pe"] == 0
    assert ratios[0]["debt_to_equity"] == 0
    assert metrics[0]["roic"] == 0
