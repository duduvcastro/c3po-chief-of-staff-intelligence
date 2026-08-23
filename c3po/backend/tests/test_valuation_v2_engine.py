from datetime import date, datetime, timedelta, timezone

from app.config import get_settings
from app.database import Database
from app.valuation_v2_engine import ValuationV2Engine
from app.valuation_v2_shadow import ValuationV2ShadowService


TODAY = date(2026, 8, 23)


def _future_fy(years: int) -> str:
    return date(TODAY.year + years, 12, 31).isoformat()


def _past_fy(years: int) -> str:
    return date(TODAY.year - years, 12, 31).isoformat()


def _packet(**overrides) -> dict:
    base = {
        "peers": [{"symbol": peer} for peer in ("PEERA", "PEERB", "PEERC", "PEERD", "PEERE")],
        "analyst_estimates_annual": [
            {"fiscal_year_end": _future_fy(0), "eps_avg": 10.0, "ebitda_avg": 20e9, "analysts_eps": 18},
            {"fiscal_year_end": _future_fy(1), "eps_avg": 11.0, "ebitda_avg": 21.5e9, "analysts_eps": 15},
        ],
        "ratios_annual": [
            {"fiscal_year_end": _past_fy(offset), "pe": 14.0 + offset, "price_to_book": 2.0,
             "ev_ebitda": 9.0, "roe": 0.18, "dividend_yield": 0.02}
            for offset in range(1, 9)
        ],
        "key_metrics_annual": [
            {"fiscal_year_end": _past_fy(offset), "eps": 8.0 + offset * 0.2,
             "market_cap": 190e9, "enterprise_value": 220e9}
            for offset in range(1, 9)
        ],
    }
    base.update(overrides)
    return base


def _peer_multiples() -> dict[str, dict]:
    return {
        peer: {"pe": 15.0 + index, "forward_pe": 14.0 + index, "ev_ebitda": 9.5 + index * 0.4,
               "price_to_book": 2.2 + index * 0.1, "roe": 0.16 + index * 0.01}
        for index, peer in enumerate(("PEERA", "PEERB", "PEERC", "PEERD", "PEERE"))
    }


def _row(**overrides) -> dict:
    base = {
        "symbol": "ACME",
        "price": 150.0,
        "market_cap": 190e9,
        "sector": "Industrials",
        "valuation_profile": "general",
        "beta": 1.0,
        "public_consensus_tp": 170.0,
        "analyst_count": 12,
        "eps": 10.0,
        "book_value": 70.0,
        "our_tp": 185.0,
        "internal_tp": 210.0,
    }
    base.update(overrides)
    return base


def _engine(**kwargs) -> ValuationV2Engine:
    kwargs.setdefault("market", "US")
    kwargs.setdefault("today", TODAY)
    return ValuationV2Engine(**kwargs)


def test_engine_builds_four_models_with_external_anchors_only():
    result = _engine().evaluate(_row(), _packet(), peer_multiples=_peer_multiples())

    assert result is not None
    assert set(result["models"]) == {"peer_comps", "own_history", "earnings_power", "reverse_dcf"}
    assert result["v2_tp"] > 0
    assert result["models"]["earnings_power"]["fair_pe_source"] == "peers_forward"
    assert result["consensus_weight"] == 0.35
    assert result["consensus_weight_source"] == "v1_policy_pending_v2_3_calibration"
    assert result["risk_free_source"] == "fallback_constant"
    assert result["models"]["reverse_dcf"]["implied_growth"] is not None
    assert result["models"]["reverse_dcf"]["tp"] < result["price"] * 2
    assert result["internal_divergence_vs_consensus"] is not None
    assert result["final_divergence_vs_consensus"] is not None


def test_engine_declares_itself_unable_without_any_anchor():
    result = _engine().evaluate(
        _row(public_consensus_tp=None, analyst_count=0, internal_tp=None),
        {"peers": [], "analyst_estimates_annual": [], "ratios_annual": [], "key_metrics_annual": []},
        peer_multiples={},
    )

    assert result is not None
    assert result["v2_tp"] is None
    assert result["low_conviction"] is True
    assert result["reason"] == "no_model_had_verifiable_anchors"


def test_p4_bands_flag_divergence_and_max_shrink():
    # Peers around 30x against consensus far below the model -> big divergence.
    rich_peers = {
        peer: {"forward_pe": 30.0 + index, "ev_ebitda": 20.0, "price_to_book": 6.0, "roe": 0.2}
        for index, peer in enumerate(("PEERA", "PEERB", "PEERC", "PEERD", "PEERE"))
    }
    result = _engine().evaluate(
        _row(public_consensus_tp=120.0),
        _packet(),
        peer_multiples=rich_peers,
    )

    assert result is not None
    assert result["internal_divergence_vs_consensus"] > 0.30
    assert result["divergence_flag"] == "low_conviction_band"
    assert result["low_conviction"] is True
    assert result["consensus_weight"] == 0.50


def test_cyclical_profile_uses_mid_cycle_earnings_not_peak():
    packet = _packet(
        analyst_estimates_annual=[
            {"fiscal_year_end": _future_fy(0), "eps_avg": 30.0, "analysts_eps": 12},  # peak NTM
            {"fiscal_year_end": _future_fy(1), "eps_avg": 31.0, "analysts_eps": 10},
        ],
    )
    result = _engine().evaluate(
        _row(valuation_profile="cyclical"),
        packet,
        peer_multiples=_peer_multiples(),
    )

    assert result is not None
    assert result["models"]["earnings_power"]["earnings_base"] == "mid_cycle_median"
    assert result["models"]["reverse_dcf"]["earnings_base"] == "mid_cycle_median"


def test_financial_profile_swaps_to_rim_ddm_and_pb_vs_roe():
    result = _engine().evaluate(
        _row(
            valuation_profile="financial",
            book_value=95.0,
            roe=0.19,
            dividend_yield=0.045,
            eps=13.0,
        ),
        _packet(),
        peer_multiples=_peer_multiples(),
    )

    assert result is not None
    assert "reverse_dcf" not in result["models"]
    assert "rim" in result["models"]
    assert "ddm" in result["models"]
    assert result["models"]["peer_comps"]["metrics_used"] == ["price_to_book_vs_roe"]


def test_b3_engine_uses_the_provided_curve_not_a_flat_constant():
    provided = _engine(market="B3", risk_free_rate=0.118)
    fallback = _engine(market="B3")

    assert provided.risk_free_source == "provided"
    assert provided.risk_free_rate == 0.118
    assert fallback.risk_free_source == "fallback_constant"
    # cost of equity honors the curve: beta 1 -> rf + ERP, clamped to BR bounds
    result = provided.evaluate(_row(beta=1.0), _packet(), peer_multiples=_peer_multiples())
    assert result is not None
    assert abs(result["cost_of_equity"] - (0.118 + 0.055)) < 1e-9


def test_fair_multiple_ladder_falls_back_to_sector_then_history_never_constants():
    engine = _engine()
    thin_peers = {"PEERA": {"forward_pe": 15.0}}  # below minimum sample

    with_sector = engine.evaluate(
        _row(), _packet(), peer_multiples=thin_peers,
        sector_fair_multiples={"pe": 13.0, "ev_ebitda": 8.0, "price_to_book": 1.9},
    )
    assert with_sector is not None
    assert with_sector["models"]["earnings_power"]["fair_pe_source"] == "sector_trailing_median"

    with_history = engine.evaluate(_row(), _packet(), peer_multiples=thin_peers)
    assert with_history is not None
    assert "earnings_power" not in with_history["models"]
    assert "earnings_power:deduplicated_against_own_history" in with_history["fair_multiple_ladder"]

    bare = engine.evaluate(
        _row(),
        _packet(ratios_annual=[]),
        peer_multiples=thin_peers,
    )
    assert bare is not None
    assert "earnings_power" not in bare["models"]
    assert "pe:unavailable" in bare["fair_multiple_ladder"]


def test_cyclical_models_are_unavailable_without_mid_cycle_earnings():
    packet = _packet(key_metrics_annual=[])

    result = _engine().evaluate(
        _row(valuation_profile="cyclical"),
        packet,
        peer_multiples=_peer_multiples(),
    )

    assert result is not None
    assert "earnings_power" not in result["models"]
    assert "reverse_dcf" not in result["models"]
    assert not (
        result["models"].get("own_history", {}).get("earnings_base")
        == "ntm_fy_weighted"
    )


def test_ntm_eps_and_ebitda_share_the_same_fy1_fy2_weighting():
    engine = _engine()
    estimates = [
        {
            "fiscal_year_end": _future_fy(0),
            "eps_avg": 10.0,
            "ebitda_avg": 100.0,
            "analysts_eps": 8,
        },
        {
            "fiscal_year_end": _future_fy(1),
            "eps_avg": 20.0,
            "ebitda_avg": 200.0,
            "analysts_eps": 7,
        },
    ]

    inputs = engine._inputs(  # noqa: SLF001 - regression over the frozen convention
        _row(), _packet(analyst_estimates_annual=estimates), 150.0
    )
    fraction = inputs["fy1_fraction"]

    assert inputs["ntm_eps"] == 10.0 * fraction + 20.0 * (1 - fraction)
    assert inputs["ntm_ebitda"] == 100.0 * fraction + 200.0 * (1 - fraction)


def test_forward_and_trailing_peer_pe_are_not_mixed_into_one_sample():
    mixed_peers = {
        "A": {"forward_pe": 10.0},
        "B": {"forward_pe": 11.0},
        "C": {"forward_pe": 12.0},
        "D": {"pe": 20.0},
        "E": {"pe": 21.0},
    }

    fair, source, basis = _engine()._fair_multiple(  # noqa: SLF001
        "pe", _packet(), mixed_peers, None
    )

    assert fair is not None
    assert source == "own_history"
    assert basis == "trailing"


def test_pe_only_peer_anchor_is_not_counted_twice():
    pe_only = {
        peer: {"forward_pe": 14.0 + index}
        for index, peer in enumerate(("PEERA", "PEERB", "PEERC", "PEERD", "PEERE"))
    }

    result = _engine().evaluate(_row(), _packet(), peer_multiples=pe_only)

    assert result is not None
    assert "earnings_power" in result["models"]
    assert "peer_comps" not in result["models"]


def test_reverse_dcf_is_bounded_growth_signal_not_forward_intrinsic_value():
    result = _engine().evaluate(
        _row(price=100.0, public_consensus_tp=110.0),
        _packet(),
        peer_multiples=_peer_multiples(),
    )

    assert result is not None
    reverse = result["models"]["reverse_dcf"]
    assert 0.55 * result["price"] <= reverse["tp"] <= 1.81 * result["price"]
    assert "growth_gap" in reverse
    assert "growth_ratio_price_equivalent" in reverse


def _seed_snapshot(database: Database, analysis_type: str, entity: str, outputs: dict) -> None:
    methodology_id = database.ensure_methodology_version("test_seed", 1, {}, "test")
    database.save_analysis_snapshot(
        analysis_type, entity, methodology_id, {}, outputs, datetime.now(timezone.utc),
    )


def test_shadow_service_runs_off_persisted_snapshots_and_summarizes_both_engines():
    settings = get_settings().model_copy(update={"brapi_token": ""})
    database = Database(settings)
    _seed_snapshot(database, "valuation_universe", "NASDAQ_UNIVERSE", {"rows": [
        {"symbol": "ACME", "security_type": "Stock", "price": 150.0, "market_cap": 190e9,
         "sector": "Industrials", "valuation_profile": "general", "beta": 1.0,
         "public_consensus_tp": 170.0, "analyst_count": 12, "our_tp": 180.0,
         "internal_tp": 240.0, "eps": 10.0, "book_value": 70.0,
         "pe": 15.0, "forward_pe": 14.0, "ev_ebitda": 9.0, "price_to_book": 2.1},
    ]})
    _seed_snapshot(database, "valuation_universe", "NYSE_UNIVERSE", {"rows": [
        {"symbol": peer, "security_type": "Stock", "price": 100.0, "market_cap": 5e10,
         "sector": "Industrials", "pe": 15.0 + index, "forward_pe": 14.0 + index,
         "ev_ebitda": 9.5, "price_to_book": 2.2, "roe": 0.17}
        for index, peer in enumerate(("PEERA", "PEERB", "PEERC", "PEERD", "PEERE"))
    ]})
    _seed_snapshot(database, "valuation_v2_data", "NASDAQ_V2_DATA", {"packets": {
        "ACME": _packet(),
    }})
    service = ValuationV2ShadowService(settings, database, http=None)  # type: ignore[arg-type]

    summary = service.run("NASDAQ")

    assert summary["evaluated"] == 1
    assert summary["with_consensus"] == 1
    assert summary["v2_divergence_p50"] is not None
    assert summary["v1_divergence_p50"] is not None
    result = service.result_for("NASDAQ", "ACME")
    assert result is not None
    assert result["peer_multiples_resolved"] == 5
    assert result["v1_final_tp"] == 180.0
    assert result["v1_internal_tp"] == 240.0
    assert summary["comparison_ruler_for_p4"] == "internal_tp_vs_consensus"
    assert summary["v2_divergence_p50"] == summary["v2_internal_divergence_p50"]
    # Each ruler is compared like-for-like; final and internal values never mix.
    assert (
        result["internal_divergence_vs_consensus"]
        < result["v1_internal_divergence_vs_consensus"]
    )
    assert result["final_divergence_vs_consensus"] is not None
    assert result["v1_final_divergence_vs_consensus"] is not None


def test_shadow_resolves_b3_provider_peers_by_canonical_symbol():
    settings = get_settings().model_copy(update={"brapi_token": ""})
    database = Database(settings)
    peers = ("PEER3", "PEER4", "PEER5", "PEER6")
    _seed_snapshot(database, "valuation_universe", "B3_UNIVERSE", {"rows": [
        {
            "symbol": "ACME3", "security_type": "Stock", "price": 20.0,
            "market_cap": 2e9, "sector": "Industrials", "valuation_profile": "general",
            "public_consensus_tp": 24.0, "analyst_count": 5, "our_tp": 23.0,
            "internal_tp": 25.0, "eps": 1.5, "book_value": 8.0,
        },
        *[
            {
                "symbol": peer, "security_type": "Stock", "price": 15.0,
                "market_cap": 1e9, "sector": "Industrials", "forward_pe": 10.0,
                "pe": 11.0, "ev_ebitda": 7.0, "price_to_book": 1.5,
            }
            for peer in peers
        ],
    ]})
    _seed_snapshot(database, "valuation_v2_data", "B3_V2_DATA", {"packets": {
        "ACME3": _packet(peers=[
            {"symbol": f"{peer}.SA", "canonical_symbol": peer} for peer in peers
        ]),
    }})
    service = ValuationV2ShadowService(settings, database, http=None)  # type: ignore[arg-type]

    service.run("B3")

    result = service.result_for("B3", "ACME3")
    assert result is not None
    assert result["peer_multiples_resolved"] == 4


def test_b3_risk_free_uses_curve_point_closest_to_five_year_horizon():
    class FakeHttp:
        def get_json(self, *_args, **_kwargs):
            return {"results": [
                {"symbol": "SHORT", "durationDays": 900, "buyRate": 0.11},
                {
                    "symbol": "MATCH", "durationDays": 1820,
                    "buyRate": 0.125, "sellRate": 0.127,
                },
                {"symbol": "LONG", "durationDays": 4000, "buyRate": 0.14},
            ]}

    settings = get_settings().model_copy(update={"brapi_token": "token"})
    service = ValuationV2ShadowService(settings, Database(settings), FakeHttp())  # type: ignore[arg-type]

    assert service._risk_free("B3") == 0.126  # noqa: SLF001
