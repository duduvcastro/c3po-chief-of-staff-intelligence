from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest

import app.valuation_v3_ab as ab_module
from app.valuation_v3_ab import (
    AB_AS_OF,
    AB_EVALUATION_DATE,
    FROZEN_SNAPSHOT_REFERENCES,
    ManifestValidationError,
    V2ReproductionError,
    build_manifest,
    canonical_sha256,
    manifest_hash,
    run_ab,
    validate_manifest,
    v2_output_sha256,
    write_immutable_json,
)
from app.valuation_v3_macro import canonical_payload_sha256


ENGINE_COMMIT = "a" * 40
HARNESS_COMMIT = "b" * 40
SELIC_ID = "11111111-1111-1111-1111-111111111111"
CURVE_ID = "22222222-2222-2222-2222-222222222222"


def _snapshot(
    snapshot_id: str,
    analysis_type: str,
    entity_key: str,
    published_at: datetime,
    outputs: dict,
) -> dict:
    return {
        "id": snapshot_id,
        "analysis_type": analysis_type,
        "entity_key": entity_key,
        "methodology_version_id": "33333333-3333-3333-3333-333333333333",
        "inputs": {},
        "outputs": outputs,
        "published_at": published_at,
    }


def _curve() -> dict:
    observed = date(2026, 8, 21)
    package = {
        "schema_version": "VALUATION-V3-MACRO-v1",
        "engine_version": 3,
        "source": "EODHD Government Bonds",
        "as_of": AB_AS_OF.isoformat(),
        "fetched_at": datetime(2026, 8, 23, 20, tzinfo=timezone.utc).isoformat(),
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


def _selic() -> dict:
    package = {
        "schema_version": "VALUATION-V3-MACRO-v1",
        "engine_version": 3,
        "source": "Banco Central do Brasil SGS 432",
        "series": "SGS 432",
        "as_of": AB_AS_OF.isoformat(),
        "fetched_at": datetime(2026, 8, 23, 20, tzinfo=timezone.utc).isoformat(),
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


def _frozen_snapshots() -> dict[str, dict]:
    snapshots: dict[str, dict] = {}
    for reference in FROZEN_SNAPSHOT_REFERENCES:
        outputs: dict = {}
        if reference.role == "universe":
            outputs = {"rows": [_row(reference.market)]}
        elif reference.role == "v2_data":
            row = _row(reference.market)
            outputs = {"packets": {row["symbol"]: _packet(row["symbol"])}}
        elif reference.role == "peer_quality":
            symbol = "PEER3" if reference.market == "B3" else "USPEER"
            outputs = {"packets": {symbol: _packet(symbol)}}
        elif reference.role == "chewie":
            outputs = {"items": []}
        elif reference.role == "v2_shadow":
            outputs = {"results": {}, "summary": {}}
        snapshots[reference.snapshot_id] = _snapshot(
            reference.snapshot_id,
            reference.analysis_type,
            reference.entity_key,
            reference.published_at,
            outputs,
        )
    snapshots[SELIC_ID] = _snapshot(
        SELIC_ID,
        "valuation_macro_history",
        "B3_SELIC_REGIME",
        datetime(2026, 8, 23, 20, 30, tzinfo=timezone.utc),
        _selic(),
    )
    snapshots[CURVE_ID] = _snapshot(
        CURVE_ID,
        "valuation_macro_rates",
        "US_5Y_INTERPOLATED",
        datetime(2026, 8, 23, 20, 31, tzinfo=timezone.utc),
        _curve(),
    )
    return snapshots


def _loader(snapshots: dict[str, dict]):
    return lambda snapshot_id: snapshots.get(snapshot_id)


def _seed_accepted_v2(snapshots: dict[str, dict]) -> None:
    loaded = {
        (reference.role, reference.market): snapshots[reference.snapshot_id]
        for reference in FROZEN_SNAPSHOT_REFERENCES
    }
    for market in ("B3", "NASDAQ", "NYSE"):
        context = ab_module._market_context(market, loaded)  # noqa: SLF001
        outputs = ab_module._v2_outputs_for_rate(  # noqa: SLF001
            market,
            context,
            0.12 if market == "B3" else None,
            evaluation_date=AB_EVALUATION_DATE,
        )
        reference = next(
            item for item in FROZEN_SNAPSHOT_REFERENCES
            if item.role == "v2_shadow" and item.market == market
        )
        snapshots[reference.snapshot_id]["outputs"] = outputs


def test_manifest_pins_every_snapshot_macro_hash_and_engine_file() -> None:
    snapshots = _frozen_snapshots()
    manifest = build_manifest(
        _loader(snapshots),
        selic_snapshot_id=SELIC_ID,
        us_curve_snapshot_id=CURVE_ID,
        engine_commit=ENGINE_COMMIT,
        created_at=datetime(2026, 8, 23, 21, tzinfo=timezone.utc),
    )

    loaded = validate_manifest(manifest, _loader(snapshots))

    assert manifest["manifest_sha256"] == manifest_hash(manifest)
    assert manifest["as_of"] == "2026-08-24"
    assert manifest["evaluation_date"] == "2026-08-25"
    assert len(manifest["snapshots"]) == 16
    assert len(loaded) == 16
    assert manifest["macro_packages"]["selic_macro"]["payload_sha256"] == _selic()[
        "payload_sha256"
    ]
    assert manifest["engines"]["v3"]["engine_version"] == 3
    assert len(manifest["harness"]["file_sha256"]) == 64


def test_market_context_uses_frozen_peer_quality_closure_packets() -> None:
    snapshots = _frozen_snapshots()
    loaded = {
        (reference.role, reference.market): snapshots[reference.snapshot_id]
        for reference in FROZEN_SNAPSHOT_REFERENCES
    }

    b3_context = ab_module._market_context("B3", loaded)  # noqa: SLF001
    us_context = ab_module._market_context("NASDAQ", loaded)  # noqa: SLF001

    assert b3_context["quality_index"]["PEER3"]["fmp_forward"]["roe"] == 0.15
    assert us_context["quality_index"]["USPEER"]["fmp_forward"]["roe"] == 0.15


def test_manifest_rejects_self_hash_snapshot_drift_and_latest_substitution() -> None:
    snapshots = _frozen_snapshots()
    manifest = build_manifest(
        _loader(snapshots),
        selic_snapshot_id=SELIC_ID,
        us_curve_snapshot_id=CURVE_ID,
        engine_commit=ENGINE_COMMIT,
    )
    manifest["expected_counts"]["B3"] = 101
    with pytest.raises(ManifestValidationError, match="self-hash"):
        validate_manifest(manifest, _loader(snapshots))

    manifest["manifest_sha256"] = manifest_hash(manifest)
    with pytest.raises(ManifestValidationError, match="expected counts changed"):
        validate_manifest(manifest, _loader(snapshots))

    manifest = build_manifest(
        _loader(snapshots),
        selic_snapshot_id=SELIC_ID,
        us_curve_snapshot_id=CURVE_ID,
        engine_commit=ENGINE_COMMIT,
    )
    manifest["evaluation_date"] = AB_AS_OF.isoformat()
    manifest["manifest_sha256"] = manifest_hash(manifest)
    with pytest.raises(ManifestValidationError, match="evaluation date mismatch"):
        validate_manifest(manifest, _loader(snapshots))

    manifest = build_manifest(
        _loader(snapshots),
        selic_snapshot_id=SELIC_ID,
        us_curve_snapshot_id=CURVE_ID,
        engine_commit=ENGINE_COMMIT,
    )
    snapshots[FROZEN_SNAPSHOT_REFERENCES[0].snapshot_id]["outputs"]["rows"][0]["price"] = 101
    with pytest.raises(ManifestValidationError, match="snapshot hash mismatch"):
        validate_manifest(manifest, _loader(snapshots))


def test_ab_reproduces_v2_before_running_all_four_stages(monkeypatch) -> None:
    snapshots = _frozen_snapshots()
    _seed_accepted_v2(snapshots)
    monkeypatch.setattr(ab_module, "EXPECTED_COUNTS", {market: 1 for market in ab_module.MARKETS})
    manifest = build_manifest(
        _loader(snapshots),
        selic_snapshot_id=SELIC_ID,
        us_curve_snapshot_id=CURVE_ID,
        engine_commit=ENGINE_COMMIT,
    )

    report = run_ab(
        manifest,
        _loader(snapshots),
        harness_commit=HARNESS_COMMIT,
        generated_at=datetime(2026, 8, 23, 22, tzinfo=timezone.utc),
    )

    assert report["v2_reproduction"]["passed"] is True
    assert report["as_of"] == AB_AS_OF.isoformat()
    assert report["evaluation_date"] == AB_EVALUATION_DATE.isoformat()
    assert set(report["stages"]) == {
        "v2", "v3_1_quality", "v3_1_plus_v3_2", "v3_full"
    }
    assert all(
        report["stages"][stage][market]["evaluated"] == 1
        for stage in report["stages"]
        for market in ab_module.MARKETS
    )
    assert report["official_tp_replacement_authorized"] is False
    assert set(report["stage_deltas"]) == {
        "v2_to_v3_1",
        "v3_1_to_v3_1_plus_v3_2",
        "v3_1_plus_v3_2_to_full",
        "v2_to_full",
    }
    assert len(report["harness_file_sha256"]) == 64
    assert report["report_sha256"] == canonical_sha256({
        key: value for key, value in report.items() if key != "report_sha256"
    })


def test_v2_mismatch_prevents_v3_construction(monkeypatch) -> None:
    snapshots = _frozen_snapshots()
    _seed_accepted_v2(snapshots)
    monkeypatch.setattr(ab_module, "EXPECTED_COUNTS", {market: 1 for market in ab_module.MARKETS})
    manifest = build_manifest(
        _loader(snapshots),
        selic_snapshot_id=SELIC_ID,
        us_curve_snapshot_id=CURVE_ID,
        engine_commit=ENGINE_COMMIT,
    )
    b3_shadow = next(
        item for item in FROZEN_SNAPSHOT_REFERENCES
        if item.role == "v2_shadow" and item.market == "B3"
    )
    snapshots[b3_shadow.snapshot_id]["outputs"]["results"]["ACME3"]["v2_tp"] += 1
    for record in manifest["snapshots"]:
        if record["role"] == "v2_shadow" and record["market"] == "B3":
            record["snapshot_sha256"] = canonical_sha256(
                ab_module._snapshot_payload(snapshots[b3_shadow.snapshot_id])  # noqa: SLF001
            )
    manifest["accepted_v2_shadow_output_sha256"]["B3"] = v2_output_sha256(
        snapshots[b3_shadow.snapshot_id]["outputs"]
    )
    manifest["manifest_sha256"] = manifest_hash(manifest)

    class ForbiddenV3:
        def __init__(self, *args, **kwargs):
            raise AssertionError("V3 must not be constructed before V2 reproduces")

    monkeypatch.setattr(ab_module, "ValuationV3Engine", ForbiddenV3)
    with pytest.raises(V2ReproductionError, match="did not reproduce"):
        run_ab(manifest, _loader(snapshots), harness_commit=HARNESS_COMMIT)


def test_reproduction_uses_the_frozen_evaluation_date() -> None:
    snapshots = _frozen_snapshots()
    loaded = {
        (reference.role, reference.market): snapshots[reference.snapshot_id]
        for reference in FROZEN_SNAPSHOT_REFERENCES
    }
    context = ab_module._market_context("NASDAQ", loaded)  # noqa: SLF001
    accepted = ab_module._v2_outputs_for_rate(  # noqa: SLF001
        "NASDAQ", context, None, evaluation_date=AB_EVALUATION_DATE
    )

    reproduced, _ = ab_module.reproduce_v2(
        "NASDAQ", context, accepted, evaluation_date=AB_EVALUATION_DATE
    )
    assert v2_output_sha256(reproduced) == v2_output_sha256(accepted)
    with pytest.raises(V2ReproductionError, match="did not reproduce"):
        ab_module.reproduce_v2(
            "NASDAQ", context, accepted, evaluation_date=AB_AS_OF
        )


def test_v2_output_hash_normalizes_only_jsonb_signed_zero() -> None:
    assert v2_output_sha256({"value": -0.0}) == v2_output_sha256({"value": 0.0})
    assert v2_output_sha256({"value": -0.0001}) != v2_output_sha256(
        {"value": 0.0001}
    )


def test_immutable_writer_is_idempotent_only_for_identical_bytes(tmp_path: Path) -> None:
    target = tmp_path / "manifest.json"
    write_immutable_json(target, {"a": 1})
    first = target.read_bytes()
    write_immutable_json(target, {"a": 1})
    assert target.read_bytes() == first
    with pytest.raises(FileExistsError, match="Immutable artifact"):
        write_immutable_json(target, {"a": 2})


def test_operator_output_prefers_the_reports_own_hash() -> None:
    assert ab_module._artifact_sha256({  # noqa: SLF001
        "manifest_sha256": "parent",
        "report_sha256": "report",
    }) == "report"
    assert (
        ab_module._artifact_sha256({"manifest_sha256": "manifest"})  # noqa: SLF001
        == "manifest"
    )
