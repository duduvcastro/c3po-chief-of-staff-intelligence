from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.config import Settings
from app.database import Database
from app.r2d2_entry_score_adapter import R2D2EntryScoreAdapter
from app.valuation_v3_macro import canonical_payload_sha256
from app.valuation_v3_shadow import (
    ANALYSIS_TYPE,
    MARKETS,
    ValuationV3ShadowInputError,
    ValuationV3ShadowService,
)


NOW = datetime(2026, 8, 26, 4, 30, tzinfo=timezone.utc)
MACRO_AS_OF = date(2026, 8, 24)


def _database() -> Database:
    return Database(Settings(database_url="", auth_cookie_secure=False))


def _seed(
    database: Database,
    analysis_type: str,
    entity_key: str,
    outputs: dict,
    published_at: datetime,
) -> str:
    methodology_id = database.ensure_methodology_version(
        f"test-{analysis_type}", 1, {}, "V3 shadow test source",
    )
    return database.save_analysis_snapshot(
        analysis_type,
        entity_key,
        methodology_id,
        {"available_at": published_at.isoformat()},
        outputs,
        published_at,
    )


def _row(market: str) -> dict:
    symbol = {"B3": "ACME3", "NASDAQ": "ACME", "NYSE": "ACMEX"}[market]
    return {
        "symbol": symbol,
        "security_type": "Stock",
        "price": 100.0,
        "market_cap": 100_000_000,
        "sector": "Industrials",
        "valuation_profile": "general",
        "beta": 1.0,
        "public_consensus_tp": 115.0,
        "analyst_count": 8,
        "our_tp": 112.0,
        "internal_tp": 120.0,
        "eps": 7.5,
        "book_value": 50.0,
        "pe": 13.3,
        "forward_pe": 12.5,
        "ev_ebitda": 8.0,
        "price_to_book": 2.0,
        "roe": 0.15,
    }


def _packet(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "peers": [],
        "analyst_estimates_annual": [
            {
                "fiscal_year_end": "2026-12-31",
                "eps_avg": 8.0,
                "ebitda_avg": 2_000_000,
                "revenue_avg": 10_000_000,
                "analysts_eps": 8,
            },
            {
                "fiscal_year_end": "2027-12-31",
                "eps_avg": 8.8,
                "ebitda_avg": 2_200_000,
                "revenue_avg": 11_000_000,
                "analysts_eps": 7,
            },
        ],
        "ratios_annual": [
            {
                "fiscal_year_end": f"{year}-12-31",
                "pe": 10.0 + (year - 2019),
                "ev_ebitda": 7.0 + (year - 2019) * 0.1,
                "price_to_book": 1.5 + (year - 2019) * 0.05,
                "roe": 0.15,
            }
            for year in range(2019, 2026)
        ],
        "key_metrics_annual": [
            {
                "fiscal_year_end": f"{year}-12-31",
                "eps": 7.0 + (year - 2019) * 0.1,
                "market_cap": 100_000_000,
                "enterprise_value": 110_000_000,
                "roe": 0.15,
            }
            for year in range(2019, 2026)
        ],
    }


def _selic_package() -> dict:
    fetched_at = datetime(2026, 8, 25, 3, 0, tzinfo=timezone.utc)
    package = {
        "schema_version": "VALUATION-V3-MACRO-v1",
        "engine_version": 3,
        "source": "Banco Central do Brasil SGS 432",
        "series": "SGS 432",
        "as_of": MACRO_AS_OF.isoformat(),
        "fetched_at": fetched_at.isoformat(),
        "observations": [
            {
                "observation_date": f"{year}-01-01",
                "annual_rate": 0.10 + (year % 3) * 0.005,
                "available_at": datetime(
                    year, 1, 2, tzinfo=timezone.utc
                ).isoformat(),
            }
            for year in range(2014, 2027)
        ],
    }
    package["payload_sha256"] = canonical_payload_sha256(package)
    return package


def _curve_package() -> dict:
    observed = date(2026, 8, 21)
    fetched_at = datetime(2026, 8, 25, 3, 0, tzinfo=timezone.utc)
    package = {
        "schema_version": "VALUATION-V3-MACRO-v1",
        "engine_version": 3,
        "source": "EODHD Government Bonds",
        "as_of": MACRO_AS_OF.isoformat(),
        "fetched_at": fetched_at.isoformat(),
        "formula": "r3y + (2/7) * (r10y - r3y)",
        "points": [
            {
                "symbol": "US3Y.GBOND",
                "tenor_years": 3,
                "observation_date": observed.isoformat(),
                "annual_rate": 0.04,
                "available_at": datetime.combine(
                    observed + timedelta(days=1), time.min, tzinfo=timezone.utc
                ).isoformat(),
                "source": "EODHD Government Bonds",
            },
            {
                "symbol": "US10Y.GBOND",
                "tenor_years": 10,
                "observation_date": observed.isoformat(),
                "annual_rate": 0.05,
                "available_at": datetime.combine(
                    observed + timedelta(days=1), time.min, tzinfo=timezone.utc
                ).isoformat(),
                "source": "EODHD Government Bonds",
            },
        ],
        "interpolated_5y_rate": 0.04 + (2 / 7) * 0.01,
    }
    package["payload_sha256"] = canonical_payload_sha256(package)
    return package


def _seed_sources(
    database: Database,
    *,
    run_at: datetime = NOW,
    stale_role: tuple[str, str] | None = None,
    omit_role: tuple[str, str] | None = None,
    include_macro: bool = True,
) -> None:
    source_at = run_at - timedelta(minutes=20)
    stale_at = run_at - timedelta(days=1)
    universe_at = run_at - timedelta(days=1, hours=2)

    for market in MARKETS:
        role = ("universe", market)
        if role != omit_role:
            _seed(
                database,
                "valuation_universe",
                f"{market}_UNIVERSE",
                {"rows": [_row(market)]},
                stale_at if role == stale_role else universe_at,
            )

        role = ("v2_data", market)
        if role != omit_role:
            row = _row(market)
            _seed(
                database,
                "valuation_v2_data",
                f"{market}_V2_DATA",
                {"packets": {row["symbol"]: _packet(row["symbol"])}},
                stale_at if role == stale_role else source_at,
            )

        role = ("chewie", market)
        if role != omit_role:
            _seed(
                database,
                "chewie_fundamentals",
                f"{market}_FUNDAMENTALS",
                {"items": []},
                stale_at if role == stale_role else source_at,
            )

        role = ("v2_shadow", market)
        if role != omit_role:
            row = _row(market)
            _seed(
                database,
                "valuation_v2_shadow",
                f"{market}_V2_SHADOW",
                {
                    "results": {
                        row["symbol"]: {
                            "risk_free_rate": 0.1472 if market == "B3" else 0.042,
                            "risk_free_source": (
                                "brapi_tesouro_prefixado_5y"
                                if market == "B3" else "policy_fallback"
                            ),
                        }
                    }
                },
                stale_at if role == stale_role else source_at,
            )

    for peer_market in ("B3", "US"):
        role = ("peer_quality", peer_market)
        if role != omit_role:
            _seed(
                database,
                "valuation_v2_peer_quality",
                f"{peer_market}_V2_PEER_QUALITY",
                {"packets": {}},
                stale_at if role == stale_role else source_at,
            )

    if include_macro:
        if ("selic_macro", "B3") != omit_role:
            _seed(
                database,
                "valuation_macro_history",
                "B3_SELIC_REGIME",
                _selic_package(),
                datetime(2026, 8, 25, 3, 0, tzinfo=timezone.utc),
            )
        if ("treasury_macro", "US") != omit_role:
            _seed(
                database,
                "valuation_macro_rates",
                "US_5Y_INTERPOLATED",
                _curve_package(),
                datetime(2026, 8, 25, 3, 0, tzinfo=timezone.utc),
            )


def _v3_snapshot(database: Database, market: str) -> dict:
    snapshot = database.latest_analysis_snapshot(
        ANALYSIS_TYPE, f"{market}_V3_SHADOW"
    )
    assert snapshot is not None
    return snapshot


def test_nightly_shadow_is_persisted_from_causal_sources_with_zero_provider_calls() -> None:
    database = _database()
    _seed_sources(database)
    service = ValuationV3ShadowService(database)

    result = service.run_all(now=NOW)

    assert set(result) == set(MARKETS)
    cycle_ids = set()
    for market in MARKETS:
        snapshot = _v3_snapshot(database, market)
        outputs = snapshot["outputs"]
        cycle_ids.add(outputs["run"]["cycle_id"])
        assert outputs["run"]["status"] == "complete"
        assert outputs["run"]["operational_streak"] == 1
        assert outputs["run"]["soak_eligible"] is False
        assert outputs["governance"] == {
            "append_only": True,
            "external_api_calls": 0,
            "decision_consumer": False,
            "consumer_change_authorized": False,
            "official_tp_replacement_authorized": False,
        }
        assert outputs["summary"]["asset_count_status"] == "explained"
        assert outputs["summary"]["evaluated"] == 1
        assert outputs["results"][_row(market)["symbol"]]["v3_tp"] > 0
        assert len(outputs["source_manifest"]["snapshots"]) == 16
        universe_reference = next(
            item
            for item in outputs["source_manifest"]["snapshots"]
            if item["role"] == "universe" and item["market"] == market
        )
        assert universe_reference["fresh_for_cycle"] is False
        assert result[market]["idempotent"] is False
    assert len(cycle_ids) == 1
    assert service.last_run_at() == NOW

    snapshot_count = sum(
        item["analysis_type"] == ANALYSIS_TYPE
        for item in database._analysis_snapshots  # noqa: SLF001
    )
    repeated = service.run_all(now=NOW + timedelta(minutes=1))
    assert all(item["idempotent"] is True for item in repeated.values())
    assert sum(
        item["analysis_type"] == ANALYSIS_TYPE
        for item in database._analysis_snapshots  # noqa: SLF001
    ) == snapshot_count


def test_nightly_shadow_fails_closed_on_stale_phase_or_missing_curve() -> None:
    stale_database = _database()
    _seed_sources(stale_database, stale_role=("peer_quality", "US"))

    with pytest.raises(
        ValuationV3ShadowInputError,
        match="stale for this cycle: peer_quality/US",
    ):
        ValuationV3ShadowService(stale_database).run_all(now=NOW)
    assert not any(
        item["analysis_type"] == ANALYSIS_TYPE
        for item in stale_database._analysis_snapshots  # noqa: SLF001
    )

    missing_database = _database()
    _seed_sources(missing_database, omit_role=("treasury_macro", "US"))
    with pytest.raises(
        ValuationV3ShadowInputError,
        match="Missing persisted V3 shadow source: treasury_macro/US",
    ):
        ValuationV3ShadowService(missing_database).run_all(now=NOW)
    assert not any(
        item["analysis_type"] == ANALYSIS_TYPE
        for item in missing_database._analysis_snapshots  # noqa: SLF001
    )


def test_operational_streak_requires_consecutive_complete_nights() -> None:
    database = _database()
    service = ValuationV3ShadowService(database)
    _seed_sources(database, run_at=NOW)
    first = service.run_all(now=NOW)
    assert {item["operational_streak"] for item in first.values()} == {1}

    next_night = NOW + timedelta(days=1)
    _seed_sources(database, run_at=next_night, include_macro=False)
    second = service.run_all(now=next_night)
    assert {item["operational_streak"] for item in second.values()} == {2}

    after_gap = NOW + timedelta(days=3)
    _seed_sources(database, run_at=after_gap, include_macro=False)
    reset = service.run_all(now=after_gap)
    assert {item["operational_streak"] for item in reset.values()} == {1}


def test_entry_score_adapter_consumes_only_the_persisted_v3_shadow_snapshot() -> None:
    database = _database()
    _seed_sources(database)
    service = ValuationV3ShadowService(database)
    service.run_all(now=NOW)
    decision_at = NOW + timedelta(minutes=5)

    telemetry = R2D2EntryScoreAdapter(database).record_cycle(
        experiment_id="11111111-1111-1111-1111-111111111111",
        cycle_id="22222222-2222-2222-2222-222222222222",
        policy_epoch="policy-a-resume-2026-08-26",
        candidates=[{
            "market": "NASDAQ",
            "symbol": "ACME",
            "price": 100.0,
            "quote_as_of": decision_at,
            "quote_status": "live",
            "valuation_basis": "canonical C3PO valuation universe",
            "composite_score": 80,
            "fundamental_score": 82,
            "technical_score": 77,
            "risk_score": 40,
            "pretrade_rank": 81,
            "raw_cash_volume_usd": 42_000_000,
            "spread_bps": 3.0,
            "technical_reviewed": True,
        }],
        decision_at=decision_at,
    )

    observation = R2D2EntryScoreAdapter(database).observations()[0]
    assert telemetry["written"] == 1
    assert observation["source_references"]["v3_shadow"]["status"] == "eligible"
    assert observation["valuation_comparisons"]["v3_shadow"]["upside_percent"] is not None
