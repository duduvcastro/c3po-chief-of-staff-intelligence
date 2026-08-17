from app.market_data.b3_screener import B3ScreenerService
from app.market_data.sector_taxonomy import canonical_b3_company_name, resolve_b3_sector


def test_reviewed_business_models_override_misleading_provider_labels() -> None:
    drug_retail = resolve_b3_sector(
        symbol="RADL3",
        name="Raia Drogasil SA",
        brapi_sector="Retail Trade",
        brapi_subsector="",
        eodhd={},
    )
    industrial_services = resolve_b3_sector(
        symbol="GGPS3",
        name="GPS Participacoes e Empreendimentos SA",
        brapi_sector="Commercial Services",
        brapi_subsector="",
        eodhd={},
    )

    assert drug_retail.sector == "Consumer Staples"
    assert drug_retail.valuation_profile == "general"
    assert industrial_services.sector == "Industrials"
    assert industrial_services.valuation_profile == "general"


def test_iguatemi_provider_metadata_is_corrected_to_official_b3_identity() -> None:
    classification = resolve_b3_sector(
        symbol="IGTI11",
        name="Jereissati Participacoes S.A.",
        brapi_sector="Industrials",
        brapi_subsector="Diversified Companies",
        eodhd={"sector": "Industrials", "industry": "Industrial Services"},
    )

    assert canonical_b3_company_name("IGTI11", "Jereissati Participacoes S.A.") == "Iguatemi S.A."
    assert classification.sector == "Real Estate"
    assert classification.peer_group == "Shopping Centers"
    assert classification.valuation_profile == "real_estate"
    assert classification.source == "C3PO reviewed override"


def test_eodhd_gics_and_industry_take_precedence_over_broad_brapi_sector() -> None:
    classification = resolve_b3_sector(
        symbol="TEST3",
        name="Companhia Teste SA",
        brapi_sector="Finance",
        brapi_subsector="",
        eodhd={
            "gicSector": "Real Estate",
            "gicSubIndustry": "Real Estate Development",
            "sector": "Financial Services",
            "industry": "Real Estate—Development",
        },
    )

    assert classification.sector == "Real Estate"
    assert classification.peer_group == "Real Estate"
    assert classification.valuation_profile == "real_estate"
    assert classification.source == "EODHD GICS"
    assert classification.conflict is True


def test_sector_medians_prefer_sufficiently_populated_peer_groups() -> None:
    rows = [
        {
            "valuation_profile": "general",
            "sector": "Industrials",
            "peer_group": "Industrial Services",
            "pe": value,
            "ev_ebitda": value / 2,
            "price_to_book": 1.5,
            "roe": 0.15,
            "earnings_growth": 0.08,
            "profit_margin": 0.10,
            "ebitda_margin": 0.18,
        }
        for value in (8.0, 10.0, 12.0, 14.0)
    ]
    rows.append({
        **rows[0],
        "sector": "Consumer Discretionary",
        "peer_group": "Vehicle Rentals",
        "pe": 30.0,
    })

    medians = B3ScreenerService._sector_medians(rows)

    assert medians["peer:Industrial Services"]["pe"] == 11.0
    assert "peer:Vehicle Rentals" not in medians
    assert medians["profile:general"]["pe"] == 12.0


def test_homebuilder_keeps_gics_sector_but_uses_real_estate_valuation() -> None:
    classification = resolve_b3_sector(
        symbol="CYRE3",
        name="Cyrela Brazil Realty SA",
        brapi_sector="Finance",
        brapi_subsector="Incorporacoes",
        eodhd={
            "gicSector": "Consumer Discretionary",
            "gicSubIndustry": "Homebuilding",
        },
    )

    assert classification.sector == "Consumer Discretionary"
    assert classification.peer_group == "Real Estate Development"
    assert classification.valuation_profile == "real_estate"
    assert classification.valuation_profile_source == "C3PO reviewed business model"


def test_reviewed_provider_only_issuers_use_verified_business_sectors() -> None:
    cases = {
        "VSTE3": ("Consumer Discretionary", "Apparel & Fashion Retail"),
        "RVEE3": ("Consumer Discretionary", "Live Entertainment & Venues"),
        "SAUD3": ("Health Care", "Managed Health Care"),
        "ONCO11": ("Health Care", "Health Care Services"),
        "BIED3": ("Consumer Discretionary", "Education Services"),
        "B1003": ("Financials", "Asset Management & Fiduciary Services"),
    }

    for symbol, expected in cases.items():
        classification = resolve_b3_sector(
            symbol=symbol,
            name=symbol,
            brapi_sector="Miscellaneous",
            brapi_subsector="",
            eodhd={},
        )

        assert (classification.sector, classification.peer_group) == expected
        assert classification.source == "C3PO reviewed override"
        assert classification.confidence == 100.0
