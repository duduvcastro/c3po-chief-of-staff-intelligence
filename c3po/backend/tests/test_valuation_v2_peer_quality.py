from datetime import datetime, timedelta, timezone

import pytest

from app.config import get_settings
from app.database import Database
from app.valuation_v2_data import DATA_SCHEMA_VERSION as TARGET_DATA_SCHEMA_VERSION
from app.valuation_v2_peer_quality import (
    ANALYSIS_TYPE,
    ValuationV2PeerQualityService,
)


class StubHttp:
    def __init__(self, results: dict[str, object]) -> None:
        self.results = results
        self.calls: list[tuple[str, dict]] = []

    def get_json(self, url, *, params=None, headers=None):
        request = dict(params or {})
        self.calls.append((url, request))
        for fragment, payload in self.results.items():
            if fragment in url:
                return payload(request) if callable(payload) else payload
        return []


def _future_fy(years: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=365 * years)).date().isoformat()


def _past_fy(years: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=365 * years)).date().isoformat()


def _save_snapshot(
    database: Database,
    analysis_type: str,
    entity_key: str,
    *,
    inputs: dict,
    outputs: dict,
) -> str:
    methodology_id = database.ensure_methodology_version(
        f"test_{analysis_type}", 1, {}, "test"
    )
    return database.save_analysis_snapshot(
        analysis_type,
        entity_key,
        methodology_id,
        inputs,
        outputs,
        datetime.now(timezone.utc),
    )


def _target_packet(*, roe: float | None = 0.20) -> dict:
    return {
        "symbol": "PETR4",
        "provider_symbol": "PETR4.SA",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "peers": [
            {"symbol": symbol, "canonical_symbol": symbol.removesuffix(".SA")}
            for symbol in ("BRAV3.SA", "PRIO3.SA", "RECV3.SA", "VBBR3.SA")
        ] + [{"symbol": "BRAV3", "canonical_symbol": "BRAV3"}],
        "analyst_estimates_annual": [
            {"fiscal_year_end": _future_fy(1), "revenue_avg": 100.0},
            {"fiscal_year_end": _future_fy(2), "revenue_avg": 108.0},
        ],
        "key_metrics_annual": [
            {"fiscal_year_end": _past_fy(), "roe": roe},
        ],
    }


def _seed_b3(
    database: Database,
    *,
    target_schema: str = TARGET_DATA_SCHEMA_VERSION,
    target_roe: float | None = 0.20,
) -> None:
    packet = _target_packet(roe=target_roe)
    _save_snapshot(
        database,
        "valuation_v2_data",
        "B3_V2_DATA",
        inputs={"data_schema_version": target_schema},
        outputs={"packets": {"PETR4": packet}},
    )
    peer_items = []
    for index, symbol in enumerate(("BRAV3", "PRIO3", "RECV3", "VBBR3"), start=1):
        peer_items.append({
            "symbol": symbol,
            "multiples": {
                "forward_pe": 6.0 + index,
                "pe": 7.0 + index,
                "ev_ebitda": 4.0 + index,
                "price_to_book": 0.8 + index * 0.1,
            },
            "profitability": {"roe_percent": 10.0 + index},
            "growth": {"revenue_growth_percent": 2.0 + index},
        })
    _save_snapshot(
        database,
        "chewie_fundamentals",
        "B3_FUNDAMENTALS",
        inputs={"market": "B3"},
        outputs={"items": peer_items, "universe_size": len(peer_items)},
    )
    _save_snapshot(
        database,
        "valuation_universe",
        "B3_UNIVERSE",
        inputs={},
        outputs={
            "rows": [{
                "symbol": "PETR4",
                "valuation_profile": "general",
                "forward_pe": 6.5,
                "pe": 7.0,
                "ev_ebitda": 4.5,
                "price_to_book": 1.0,
            }]
        },
    )


def _quality_http(*, estimates_error: bool = False) -> StubHttp:
    def estimates(_params):
        if estimates_error:
            raise RuntimeError("estimates unavailable")
        return [
            {"date": _future_fy(1), "revenueAvg": 100.0},
            {"date": _future_fy(2), "revenueAvg": 110.0},
        ]

    return StubHttp({
        "analyst-estimates": estimates,
        "key-metrics": [{"date": _past_fy(), "returnOnEquity": 0.18}],
    })


def test_direct_peer_closure_is_non_recursive_and_pre_ab_report_is_by_metric():
    settings = get_settings().model_copy(update={"fmp_api_token": "token"})
    database = Database(settings)
    _seed_b3(database)
    http = _quality_http()
    service = ValuationV2PeerQualityService(settings, database, http)  # type: ignore[arg-type]

    summary = service.refresh_daily("B3")

    assert summary["targets"] == 1
    assert summary["unique_direct_peers"] == 4
    assert summary["closure_attempted"] == 4
    assert summary["closure_calls_planned"] == 8
    assert summary["closure_calls_attempted"] == 8
    assert summary["endpoint_ok"] == 8
    assert summary["endpoint_empty"] == 0
    assert summary["target_roe_available"] == 1
    assert summary["fmp_forward_peers"] == 4
    assert summary["pre_ab_ready"] is True
    assert set(service.packets("B3")) == {"BRAV3", "PRIO3", "RECV3", "VBBR3"}

    endpoint_calls = [url for url, _params in http.calls]
    assert len(endpoint_calls) == 8
    assert all("stock-peers" not in url and "stable/ratios" not in url for url in endpoint_calls)

    snapshot = database.latest_analysis_snapshot(ANALYSIS_TYPE, "B3_V2_PEER_QUALITY")
    report = snapshot["outputs"]["pre_ab_report"]
    assert service.pre_ab_report("B3") == report
    assert report["pre_ab_ready"] is True
    assert report["gates"] == {
        "target_schema_current": True,
        "target_roe_non_null": True,
        "closure_fully_attempted": True,
        "chewie_snapshot_new_since_rejected_ab": True,
        "fmp_forward_structural_eligibility_nonzero": True,
    }
    assert all(
        counts["fmp_forward"] == 1
        for counts in report["structural_eligibility_by_metric"].values()
    )
    assert report["by_market"]["B3"]["target_with_peer_list"] == 1
    assert report["by_market"]["B3"]["target_with_min_peer_references"] == 1
    assert report["by_market"]["B3"]["target_with_min_peers_attempted"] == 1
    assert report["by_market"]["B3"]["target_with_min_fmp_forward_pairs"] == 1
    assert snapshot["outputs"]["peer_graph"]["PETR4"][0]["provider_symbol"].endswith(".SA")
    assert snapshot["outputs"]["universe_snapshots"]["B3_UNIVERSE"]["id"]
    assert snapshot["outputs"]["guardrails"]["recursive_peer_fetch"] is False


def test_us_collection_is_shared_but_reported_separately_by_exchange():
    settings = get_settings().model_copy(update={"fmp_api_token": "token"})
    database = Database(settings)
    peers_by_market = {
        "NASDAQ": ("PEER1", "PEER2", "PEER3", "PEER4"),
        "NYSE": ("PEER5", "PEER6", "PEER7", "PEER8"),
    }
    target_by_market = {"NASDAQ": "AAPL", "NYSE": "JPM"}
    for market, peer_symbols in peers_by_market.items():
        target = target_by_market[market]
        packet = {
            **_target_packet(),
            "symbol": target,
            "provider_symbol": target,
            "peers": [
                {"symbol": symbol, "canonical_symbol": symbol}
                for symbol in peer_symbols
            ],
        }
        _save_snapshot(
            database,
            "valuation_v2_data",
            f"{market}_V2_DATA",
            inputs={"data_schema_version": TARGET_DATA_SCHEMA_VERSION},
            outputs={"packets": {target: packet}},
        )
        _save_snapshot(
            database,
            "chewie_fundamentals",
            f"{market}_FUNDAMENTALS",
            inputs={"market": market},
            outputs={
                "items": [
                    {
                        "symbol": symbol,
                        "multiples": {
                            "forward_pe": 10.0,
                            "pe": 11.0,
                            "ev_ebitda": 8.0,
                            "price_to_book": 2.0,
                        },
                        "profitability": {"roe_percent": 18.0},
                        "growth": {"revenue_growth_percent": 6.0},
                    }
                    for symbol in peer_symbols
                ]
            },
        )
        _save_snapshot(
            database,
            "valuation_universe",
            f"{market}_UNIVERSE",
            inputs={},
            outputs={
                "rows": [
                    {
                        "symbol": target,
                        "valuation_profile": "general",
                        "forward_pe": 10.0,
                        "pe": 11.0,
                        "ev_ebitda": 8.0,
                        "price_to_book": 2.0,
                    }
                ]
            },
        )

    service = ValuationV2PeerQualityService(  # type: ignore[arg-type]
        settings, database, _quality_http()
    )
    summary = service.refresh_daily("US")
    snapshot = database.latest_analysis_snapshot(ANALYSIS_TYPE, "US_V2_PEER_QUALITY")
    report = snapshot["outputs"]["pre_ab_report"]

    assert summary["closure_attempted"] == 8
    assert summary["closure_calls_planned"] == 16
    assert summary["closure_calls_attempted"] == 16
    assert summary["pre_ab_ready"] is True
    assert set(report["by_market"]) == {"NASDAQ", "NYSE"}
    assert report["target_roe_by_market"] == {"NASDAQ": 1, "NYSE": 1}
    assert report["fmp_forward_eligible_legs_by_market"] == {
        "NASDAQ": 4,
        "NYSE": 4,
    }
    assert all(
        market_report["target_with_min_fmp_forward_pairs"] == 1
        for market_report in report["by_market"].values()
    )


def test_target_packets_must_be_recollected_with_current_roe_schema():
    settings = get_settings().model_copy(update={"fmp_api_token": "token"})
    database = Database(settings)
    _seed_b3(database, target_schema="VALUATION-V2-DATA-v1")
    http = _quality_http()
    service = ValuationV2PeerQualityService(settings, database, http)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="requires target recollection"):
        service.refresh_daily("B3")

    assert http.calls == []
    assert service.packets("B3") == {}


def test_zero_target_roe_fails_before_spending_peer_calls():
    settings = get_settings().model_copy(update={"fmp_api_token": "token"})
    database = Database(settings)
    _seed_b3(database, target_roe=None)
    http = _quality_http()
    service = ValuationV2PeerQualityService(settings, database, http)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="zero normalized ROE"):
        service.refresh_daily("B3")

    assert http.calls == []


def test_partial_peer_endpoint_failure_preserves_status_and_snapshot():
    settings = get_settings().model_copy(update={"fmp_api_token": "token"})
    database = Database(settings)
    _seed_b3(database)
    service = ValuationV2PeerQualityService(  # type: ignore[arg-type]
        settings, database, _quality_http(estimates_error=True)
    )

    summary = service.refresh_daily("B3")

    assert summary["provider_error_symbols"] == 4
    assert summary["endpoint_errors"] == 4
    assert summary["endpoint_responses"] == 4
    assert summary["endpoint_ok"] == 4
    assert summary["endpoint_empty"] == 0
    assert summary["fmp_forward_peers"] == 0
    assert summary["pre_ab_ready"] is False
    packet = service.packets("B3")["BRAV3"]
    assert packet["provider_status"]["analyst_estimates"]["status"] == "error"
    assert packet["provider_status"]["key_metrics"]["status"] == "ok"


def test_repeated_runs_append_snapshots_and_keep_the_graph_hash_stable():
    settings = get_settings().model_copy(update={"fmp_api_token": "token"})
    database = Database(settings)
    _seed_b3(database)
    service = ValuationV2PeerQualityService(  # type: ignore[arg-type]
        settings, database, _quality_http()
    )

    first = service.refresh_daily("B3")
    first_snapshot = database.latest_analysis_snapshot(ANALYSIS_TYPE, "B3_V2_PEER_QUALITY")
    second = service.refresh_daily("B3")
    second_snapshot = database.latest_analysis_snapshot(ANALYSIS_TYPE, "B3_V2_PEER_QUALITY")

    assert first["graph_sha256"] == second["graph_sha256"]
    assert first_snapshot["id"] != second_snapshot["id"]
    persisted = [
        item for item in database._analysis_snapshots  # noqa: SLF001
        if item.get("analysis_type") == ANALYSIS_TYPE
    ]
    assert len(persisted) == 2
    assert persisted[0]["outputs"]["coverage_summary"]["graph_sha256"] == first["graph_sha256"]
