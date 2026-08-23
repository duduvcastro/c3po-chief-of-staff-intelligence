from datetime import date

from app.valuation_v3_inputs import (
    attach_quality_to_multiples,
    build_quality_index,
    canonical_symbol,
    chewie_trailing_quality,
    fmp_forward_quality,
)


AS_OF = date(2026, 8, 23)


def test_fmp_forward_quality_requires_roe_and_two_positive_forward_revenues():
    packet = {
        "ratios_annual": [
            {"fiscal_year_end": "2025-12-31", "roe": 0.18},
            {"fiscal_year_end": "2024-12-31", "roe": 0.15},
        ],
        "analyst_estimates_annual": [
            {"fiscal_year_end": "2026-12-31", "revenue_avg": 100.0},
            {"fiscal_year_end": "2027-12-31", "revenue_avg": 115.0},
        ],
    }

    result = fmp_forward_quality(packet, as_of=AS_OF)

    assert result is not None
    assert result["roe"] == 0.18
    assert abs(result["revenue_growth"] - 0.15) < 1e-12
    assert fmp_forward_quality(
        {**packet, "analyst_estimates_annual": packet["analyst_estimates_annual"][:1]},
        as_of=AS_OF,
    ) is None


def test_chewie_quality_never_borrows_a_missing_field_from_fmp():
    complete = {
        "profitability": {"roe_percent": 20.0},
        "growth": {"revenue_growth_percent": 8.0},
    }
    partial = {
        "profitability": {"roe_percent": 20.0},
        "growth": {"revenue_growth_percent": None},
    }

    assert chewie_trailing_quality(complete) == {
        "roe": 0.2,
        "revenue_growth": 0.08,
        "source": "chewie_trailing",
        "fundamentals_as_of": None,
    }
    assert chewie_trailing_quality(partial) is None


def test_quality_index_resolves_b3_dot_sa_and_preserves_separate_bases():
    packets = {
        "PETR4": {
            "ratios_annual": [{"fiscal_year_end": "2025-12-31", "roe": 0.25}],
            "analyst_estimates_annual": [
                {"fiscal_year_end": "2026-12-31", "revenue_avg": 500.0},
                {"fiscal_year_end": "2027-12-31", "revenue_avg": 525.0},
            ],
        }
    }
    chewie = [{
        "symbol": "PETR4.SA",
        "profitability": {"roe_percent": 22.0},
        "growth": {"revenue_growth_percent": 3.0},
    }]

    index = build_quality_index(packets, chewie, as_of=AS_OF)
    attached = attach_quality_to_multiples(
        {"PETR4.SA": {"forward_pe": 5.0}}, index
    )

    assert canonical_symbol("petr4.sa") == "PETR4"
    assert set(index["PETR4"]) == {"fmp_forward", "chewie_trailing"}
    assert attached["PETR4"]["quality"] == index["PETR4"]
    assert attached["PETR4"]["forward_pe"] == 5.0


def test_quality_index_is_deterministic_when_provider_aliases_coexist():
    packet = {
        "ratios_annual": [{"fiscal_year_end": "2025-12-31", "roe": 0.20}],
        "analyst_estimates_annual": [
            {"fiscal_year_end": "2026-12-31", "revenue_avg": 100.0},
            {"fiscal_year_end": "2027-12-31", "revenue_avg": 110.0},
        ],
    }
    aliases = {"PETR4.SA": {**packet, "ignored": True}, "PETR4": packet}

    first = build_quality_index(aliases, [], as_of=AS_OF)
    second = build_quality_index(dict(reversed(list(aliases.items()))), [], as_of=AS_OF)

    assert first == second
