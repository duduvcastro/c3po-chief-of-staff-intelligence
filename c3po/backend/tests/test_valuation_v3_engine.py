from datetime import date, datetime, time, timedelta, timezone
from math import exp
from statistics import median

import pytest

from app.valuation_v2_engine import ValuationV2Engine, _winsorized_median
from app.valuation_v3_engine import ValuationV3Engine, ValuationV3InputError
from app.valuation_v3_macro import canonical_payload_sha256


TODAY = date(2026, 8, 23)


def _curve(rate3: float = 0.04, rate10: float = 0.05) -> dict:
    observed = date(2026, 8, 21)
    package = {
        "schema_version": "VALUATION-V3-MACRO-v1",
        "engine_version": 3,
        "source": "EODHD Government Bonds",
        "as_of": TODAY.isoformat(),
        "fetched_at": datetime(2026, 8, 23, tzinfo=timezone.utc).isoformat(),
        "formula": "r3y + (2/7) * (r10y - r3y)",
        "points": [
            {
                "symbol": "US3Y.GBOND",
                "tenor_years": 3,
                "observation_date": observed.isoformat(),
                "annual_rate": rate3,
                "available_at": datetime.combine(
                    observed + timedelta(days=1), time.min, tzinfo=timezone.utc
                ).isoformat(),
                "source": "EODHD Government Bonds",
            },
            {
                "symbol": "US10Y.GBOND",
                "tenor_years": 10,
                "observation_date": observed.isoformat(),
                "annual_rate": rate10,
                "available_at": datetime.combine(
                    observed + timedelta(days=1), time.min, tzinfo=timezone.utc
                ).isoformat(),
                "source": "EODHD Government Bonds",
            },
        ],
        "interpolated_5y_rate": rate3 + (2 / 7) * (rate10 - rate3),
    }
    package["payload_sha256"] = canonical_payload_sha256(package)
    return package


def _selic_package(yearly_rates: dict[int, float]) -> dict:
    observations = []
    for year, rate in sorted(yearly_rates.items()):
        observed = date(year, 1, 1)
        observations.append({
            "observation_date": observed.isoformat(),
            "annual_rate": rate,
            "available_at": datetime.combine(
                observed + timedelta(days=1), time.min, tzinfo=timezone.utc
            ).isoformat(),
        })
    package = {
        "schema_version": "VALUATION-V3-MACRO-v1",
        "engine_version": 3,
        "source": "Banco Central do Brasil SGS 432",
        "series": "SGS 432",
        "as_of": TODAY.isoformat(),
        "fetched_at": datetime(2026, 8, 23, tzinfo=timezone.utc).isoformat(),
        "observations": observations,
    }
    package["payload_sha256"] = canonical_payload_sha256(package)
    return package


def _packet(**overrides) -> dict:
    base = {
        "analyst_estimates_annual": [
            {
                "fiscal_year_end": "2026-12-31",
                "eps_avg": 10.0,
                "ebitda_avg": 20e9,
                "revenue_avg": 100e9,
                "analysts_eps": 18,
            },
            {
                "fiscal_year_end": "2027-12-31",
                "eps_avg": 11.0,
                "ebitda_avg": 21.5e9,
                "revenue_avg": 108e9,
                "analysts_eps": 15,
            },
        ],
        "ratios_annual": [
            {
                "fiscal_year_end": f"{year}-12-31",
                "pe": 10.0 + (year - 2016),
                "ev_ebitda": 7.0 + (year - 2016) * 0.2,
                "price_to_book": 1.5 + (year - 2016) * 0.1,
                "roe": 0.18,
            }
            for year in range(2016, 2026)
        ],
        "key_metrics_annual": [
            {
                "fiscal_year_end": f"{year}-12-31",
                "eps": 8.0 + (year - 2016) * 0.1,
                "market_cap": 190e9,
                "enterprise_value": 220e9,
            }
            for year in range(2016, 2026)
        ],
    }
    base.update(overrides)
    return base


def _row(**overrides) -> dict:
    base = {
        "symbol": "ACME",
        "price": 150.0,
        "market_cap": 190e9,
        "valuation_profile": "general",
        "sector": "Industrials",
        "beta": 1.0,
        "public_consensus_tp": 170.0,
        "analyst_count": 12,
        "eps": 10.0,
        "book_value": 70.0,
    }
    base.update(overrides)
    return base


def _quality_peers(*, beta: float = 2.0, reverse: bool = False) -> dict[str, dict]:
    peers = {}
    for index, symbol in enumerate(("A", "B", "C", "D", "E")):
        quality_rank = (index + 0.5) / 5
        # Keep every synthetic multiple inside the frozen V2 validity bounds;
        # otherwise the lowest peer is correctly removed before rank fitting.
        multiple = exp(1 + beta * ((4 - index + 0.5) / 5 if reverse else quality_rank))
        quality = {
            "roe": 0.10 + index * 0.02,
            "revenue_growth": 0.01 + index * 0.02,
        }
        peers[symbol] = {
            "pe": multiple,
            "forward_pe": multiple,
            "ev_ebitda": multiple,
            "price_to_book": multiple,
            "roe": quality["roe"],
            "quality": {
                "fmp_forward": quality,
                "chewie_trailing": quality,
            },
        }
    return peers


def _target_quality(index: int = 2, *, only: str | None = None) -> dict:
    quality = {
        "roe": 0.10 + index * 0.02,
        "revenue_growth": 0.01 + index * 0.02,
    }
    if only:
        return {only: quality}
    return {"fmp_forward": quality, "chewie_trailing": quality}


def _us_engine(**kwargs) -> ValuationV3Engine:
    kwargs.setdefault("market", "US")
    kwargs.setdefault("today", TODAY)
    kwargs.setdefault("us_curve_package", _curve())
    return ValuationV3Engine(**kwargs)


def _b3_engine(**kwargs) -> ValuationV3Engine:
    kwargs.setdefault("market", "B3")
    kwargs.setdefault("today", TODAY)
    kwargs.setdefault("risk_free_rate", 0.12)
    kwargs.setdefault("selic_package", _selic_package({
        2014: 0.16,
        2015: 0.15,
        2016: 0.14,
        2017: 0.13,
        2018: 0.12,
        2019: 0.11,
        2020: 0.105,
        2021: 0.101,
        2022: 0.099,
        2023: 0.102,
        2024: 0.098,
        2025: 0.10,
        2026: 0.10,
    }))
    return ValuationV3Engine(**kwargs)


def test_theil_sen_quality_adjustment_recovers_known_slope_and_neutral_point():
    peers = _quality_peers(beta=2.0)
    unadjusted = median(peer["forward_pe"] for peer in peers.values())

    adjusted, audit = _us_engine()._quality_adjusted_multiple(  # noqa: SLF001
        metric="pe",
        multiple_field="forward_pe",
        unadjusted=unadjusted,
        peers=peers,
        target_quality=_target_quality(2),
    )

    assert audit["quality_adjustment_status"] == "applied"
    assert audit["quality_beta"] == pytest.approx(2.0)
    assert audit["target_quality_quartile"] == 3
    assert adjusted == pytest.approx(unadjusted)


def test_quality_adjustment_is_permutation_invariant_and_iqr_bounded():
    peers = _quality_peers(beta=3.0)
    unadjusted = median(peer["forward_pe"] for peer in peers.values())
    engine = _us_engine()

    first = engine._quality_adjusted_multiple(  # noqa: SLF001
        metric="pe", multiple_field="forward_pe", unadjusted=unadjusted,
        peers=peers, target_quality={
            "fmp_forward": {"roe": 1.0, "revenue_growth": 1.0}
        },
    )
    second = engine._quality_adjusted_multiple(  # noqa: SLF001
        metric="pe", multiple_field="forward_pe", unadjusted=unadjusted,
        peers=dict(reversed(list(peers.items()))), target_quality={
            "fmp_forward": {"roe": 1.0, "revenue_growth": 1.0}
        },
    )

    assert first == second
    assert first[0] == pytest.approx(first[1]["iqr_high"], abs=1e-6)


def test_negative_quality_relation_is_zeroed_and_visible():
    peers = _quality_peers(beta=2.0, reverse=True)
    unadjusted = median(peer["forward_pe"] for peer in peers.values())

    adjusted, audit = _us_engine()._quality_adjusted_multiple(  # noqa: SLF001
        metric="pe", multiple_field="forward_pe", unadjusted=unadjusted,
        peers=peers, target_quality=_target_quality(4),
    )

    assert audit["quality_beta"] == 0
    assert audit["quality_beta_zeroed_negative"] is True
    assert adjusted == pytest.approx(unadjusted)


def test_quality_ladder_prefers_forward_then_uses_complete_trailing_cohort():
    peers = _quality_peers()
    engine = _us_engine()
    fair, source, basis, audit = engine._fair_multiple_v3(  # noqa: SLF001
        "pe", _packet(), peers, None, "general", _target_quality(2)
    )
    assert fair is not None
    assert source == "peers_forward"
    assert basis == "forward"
    assert audit["quality_basis"] == "fmp_forward"

    for peer in peers.values():
        peer["quality"].pop("fmp_forward")
    fair, _, _, audit = engine._fair_multiple_v3(  # noqa: SLF001
        "pe", _packet(), peers, None, "general",
        _target_quality(2, only="chewie_trailing"),
    )
    assert fair is not None
    assert audit["quality_basis"] == "chewie_trailing"


def test_incomplete_quality_falls_back_to_v2_and_never_increases_reliability():
    peers = _quality_peers()
    for peer in list(peers.values())[3:]:
        peer["quality"] = {}
    engine = _us_engine()
    unadjusted = median(peer["forward_pe"] for peer in peers.values())

    adjusted, audit = engine._quality_adjusted_multiple(  # noqa: SLF001
        metric="pe", multiple_field="forward_pe", unadjusted=unadjusted,
        peers=peers, target_quality=_target_quality(2),
    )

    assert adjusted == unadjusted
    assert audit["quality_adjustment_status"] == "insufficient_quality_data"

    complete = _quality_peers()
    v2 = ValuationV2Engine(market="US", today=TODAY).evaluate(
        _row(), _packet(), peer_multiples=complete
    )
    v3 = _us_engine().evaluate(
        _row(), _packet(), peer_multiples=complete, target_quality=_target_quality(2)
    )
    assert v2 is not None and v3 is not None
    assert v3["models"]["peer_comps"]["reliability"] <= v2["models"]["peer_comps"]["reliability"]
    assert v3["models"]["earnings_power"]["reliability"] <= v2["models"]["earnings_power"]["reliability"]


def test_peer_comps_metrics_used_lists_only_adjusted_legs_that_survive():
    peers = _quality_peers()
    packet = _packet(key_metrics_annual=[
        {
            "fiscal_year_end": "2025-12-31",
            "eps": 8.0,
            "market_cap": 190e9,
            "enterprise_value": 310e9,
        }
    ])

    result = _us_engine().evaluate(
        _row(), packet, peer_multiples=peers, target_quality=_target_quality(0)
    )

    assert result is not None
    peer_comps = result["models"]["peer_comps"]
    assert set(peer_comps["metrics_used"]) == set(peer_comps["quality_adjustments"])
    assert "price_to_book" in peer_comps["metrics_used"]
    assert "ev_ebitda" not in peer_comps["metrics_used"]


@pytest.mark.parametrize("profile", ["financial", "cyclical", "utilities", "real_estate"])
def test_quality_excluded_profiles_keep_v2_model_outputs(profile: str):
    row = _row(valuation_profile=profile, dividend_yield=0.04, roe=0.18)
    peers = _quality_peers()
    v2 = ValuationV2Engine(market="US", today=TODAY).evaluate(
        row, _packet(), peer_multiples=peers
    )
    v3 = ValuationV3Engine(
        market="US", today=TODAY, enable_treasury=False
    ).evaluate(
        row, _packet(), peer_multiples=peers, target_quality=_target_quality(4)
    )

    assert v2 is not None and v3 is not None
    assert v3["models"] == v2["models"]


def test_selic_conditioning_selects_exactly_five_closest_years_per_metric():
    engine = _b3_engine()

    _fair, pe_audit = engine._condition_history_metric(_packet(), "pe")  # noqa: SLF001
    _fair_pb, pb_audit = engine._condition_history_metric(_packet(), "price_to_book")  # noqa: SLF001

    assert pe_audit["regime_status"] == "applied"
    assert len(pe_audit["selected"]) == 5
    assert len(pb_audit["selected"]) == 5
    assert pe_audit["selected"][0]["fiscal_year_end"] == "2025-12-31"
    assert pe_audit["macro_hash"] == engine.selic_package["payload_sha256"]


def test_selic_metric_windows_are_independent_and_ties_prefer_recent_year():
    ratios = _packet()["ratios_annual"]
    ratios = [
        {**row, "pe": None} if row["fiscal_year_end"] == "2025-12-31" else row
        for row in ratios
    ]
    engine = _b3_engine()

    _, pe_audit = engine._condition_history_metric(  # noqa: SLF001
        _packet(ratios_annual=ratios), "pe"
    )
    _, pb_audit = engine._condition_history_metric(  # noqa: SLF001
        _packet(ratios_annual=ratios), "price_to_book"
    )

    assert "2025-12-31" not in {row["fiscal_year_end"] for row in pe_audit["selected"]}
    assert "2025-12-31" in {row["fiscal_year_end"] for row in pb_audit["selected"]}
    tied = [row for row in pe_audit["selected"] if row["distance"] == pe_audit["selected"][-1]["distance"]]
    assert tied == sorted(tied, key=lambda row: row["fiscal_year_end"], reverse=True)


def test_selic_future_observations_are_ignored_and_short_history_is_explicit_fallback():
    package = _selic_package({2024: 0.10, 2025: 0.10, 2026: 0.10, 2027: 0.01})
    engine = _b3_engine(selic_package=package)
    fair, audit = engine._condition_history_metric(_packet(), "pe")  # noqa: SLF001

    expected = _winsorized_median([row["pe"] for row in _packet()["ratios_annual"]])
    assert fair == expected
    assert audit["regime_status"] == "insufficient_selic_history"
    assert date(2027, 1, 1) not in engine._selic_dates  # noqa: SLF001


def test_future_fiscal_ratio_cannot_create_a_b3_history_model():
    ratios = [
        {
            "fiscal_year_end": f"{year}-12-31",
            "pe": 10.0,
            "price_to_book": 1.5,
        }
        for year in (2022, 2023, 2024, 2025, 2027)
    ]
    packet = _packet(ratios_annual=ratios)
    engine = _b3_engine()
    inputs = engine._inputs(_row(), packet, 150.0)  # noqa: SLF001

    result = engine._own_history_tp_v3(  # noqa: SLF001
        packet, inputs, 150.0, profile="general"
    )

    assert result is None


def test_changing_a_discarded_selic_year_does_not_change_conditioned_multiple():
    engine = _b3_engine()
    packet = _packet()
    fair_before, audit = engine._condition_history_metric(packet, "pe")  # noqa: SLF001
    discarded = set(audit["discarded_years"])
    assert discarded
    changed = [
        {**row, "pe": 79.0} if row["fiscal_year_end"] in discarded else row
        for row in packet["ratios_annual"]
    ]

    fair_after, _ = engine._condition_history_metric(  # noqa: SLF001
        _packet(ratios_annual=changed), "pe"
    )

    assert fair_after == fair_before
    assert fair_before == _winsorized_median(
        [float(row["multiple"]) for row in audit["selected"]]
    )


def test_us_market_is_bitwise_v2_when_only_selic_feature_is_enabled():
    peers = _quality_peers()
    v2 = ValuationV2Engine(market="US", today=TODAY).evaluate(
        _row(), _packet(), peer_multiples=peers
    )
    v3 = ValuationV3Engine(
        market="US",
        today=TODAY,
        enable_quality=False,
        enable_selic=True,
        enable_treasury=False,
    ).evaluate(_row(), _packet(), peer_multiples=peers)

    assert v2 is not None and v3 is not None
    assert v3["models"] == v2["models"]


def test_full_us_v3_requires_dated_curve_and_never_reports_fallback_constant():
    with pytest.raises(ValuationV3InputError, match="requires the dated Treasury"):
        ValuationV3Engine(market="US", today=TODAY)

    result = _us_engine(enable_quality=False).evaluate(
        _row(), _packet(), peer_multiples=_quality_peers()
    )

    assert result is not None
    assert result["risk_free_source"] == "eodhd_us5y_interpolated"
    assert result["risk_free_rate"] != 0.042
    assert result["macro_inputs"]["us_curve_hash"] == _curve()["payload_sha256"]


def test_higher_treasury_curve_does_not_raise_reverse_dcf_rim_or_ddm_targets():
    low = _us_engine(us_curve_package=_curve(0.03, 0.04), enable_quality=False)
    high = _us_engine(us_curve_package=_curve(0.07, 0.08), enable_quality=False)
    peers = _quality_peers()

    low_general = low.evaluate(_row(), _packet(), peer_multiples=peers)
    high_general = high.evaluate(_row(), _packet(), peer_multiples=peers)
    financial_row = _row(
        valuation_profile="financial", roe=0.18, book_value=100.0, dividend_yield=0.04
    )
    low_financial = low.evaluate(financial_row, _packet(), peer_multiples=peers)
    high_financial = high.evaluate(financial_row, _packet(), peer_multiples=peers)

    assert low_general and high_general and low_financial and high_financial
    assert high_general["models"]["reverse_dcf"]["tp"] <= low_general["models"]["reverse_dcf"]["tp"]
    for model in ("rim", "ddm"):
        assert high_financial["models"][model]["tp"] <= low_financial["models"][model]["tp"]
