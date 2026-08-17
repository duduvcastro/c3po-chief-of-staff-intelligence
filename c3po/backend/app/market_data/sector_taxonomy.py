from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


CANONICAL_SECTORS = {
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Financials",
    "Health Care",
    "Industrials",
    "Information Technology",
    "Materials",
    "Real Estate",
    "Utilities",
}


SECTOR_TAXONOMY_VERSION = 2


@dataclass(frozen=True)
class SectorClassification:
    sector: str
    industry: str
    peer_group: str
    valuation_profile: str
    source: str
    confidence: float
    conflict: bool
    brapi_sector: str
    brapi_subsector: str
    eodhd_sector: str
    eodhd_industry: str
    valuation_profile_source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "sector": self.sector,
            "subsector": self.industry,
            "peer_group": self.peer_group,
            "valuation_profile": self.valuation_profile,
            "sector_source": self.source,
            "sector_confidence": self.confidence,
            "sector_conflict": self.conflict,
            "brapi_sector": self.brapi_sector,
            "brapi_subsector": self.brapi_subsector,
            "eodhd_sector": self.eodhd_sector,
            "eodhd_industry": self.eodhd_industry,
            "valuation_profile_source": self.valuation_profile_source,
        }


# These are business-model corrections for symbols whose broad provider label is
# routinely misleading. They complement provider data; they do not replace it.
SECTOR_OVERRIDES: dict[str, tuple[str, str]] = {
    "B3SA3": ("Financials", "Capital Markets & Exchanges"),
    "B1003": ("Financials", "Asset Management & Fiduciary Services"),
    "BIED3": ("Consumer Discretionary", "Education Services"),
    "GGPS3": ("Industrials", "Business Services"),
    "IGTI3": ("Real Estate", "Shopping Centers"),
    "IGTI4": ("Real Estate", "Shopping Centers"),
    "IGTI11": ("Real Estate", "Shopping Centers"),
    "MILS3": ("Industrials", "Industrial Rentals"),
    "MOVI3": ("Industrials", "Vehicle Rentals"),
    "ORVR3": ("Industrials", "Environmental Services"),
    "ONCO11": ("Health Care", "Health Care Services"),
    "PGMN3": ("Consumer Staples", "Drug Retail"),
    "PRNR3": ("Industrials", "Industrial Services"),
    "RADL3": ("Consumer Staples", "Drug Retail"),
    "RENT3": ("Industrials", "Vehicle Rentals"),
    "RVEE3": ("Consumer Discretionary", "Live Entertainment & Venues"),
    "SAUD3": ("Health Care", "Managed Health Care"),
    "UGPA3": ("Energy", "Fuel Distribution"),
    "VBBR3": ("Energy", "Fuel Distribution"),
    "VSTE3": ("Consumer Discretionary", "Apparel & Fashion Retail"),
    "WEGE3": ("Industrials", "Electrical Equipment"),
}


COMPANY_NAME_OVERRIDES: dict[str, str] = {
    "IGTI3": "Iguatemi S.A.",
    "IGTI4": "Iguatemi S.A.",
    "IGTI11": "Iguatemi S.A.",
}


VALUATION_PROFILE_OVERRIDES: dict[str, tuple[str, str]] = {
    symbol: ("real_estate", "Real Estate Development")
    for symbol in (
        "CURY3", "CYRE3", "DIRR3", "EVEN3", "EZTC3", "GFSA3", "HBOR3", "LAVV3",
        "MDNE3", "MELK3", "MRVE3", "MTRE3", "PDGR3", "PLPL3", "TEND3", "TRIS3", "VIVR3",
    )
}


SECTOR_ALIASES = {
    "communication services": "Communication Services",
    "communications": "Communication Services",
    "commercial services": "Industrials",
    "consumer cyclical": "Consumer Discretionary",
    "consumer cyclicals": "Consumer Discretionary",
    "consumer discretionary": "Consumer Discretionary",
    "consumer durables": "Consumer Discretionary",
    "consumer services": "Consumer Discretionary",
    "retail trade": "Consumer Discretionary",
    "consumer defensive": "Consumer Staples",
    "consumer non durables": "Consumer Staples",
    "consumer staples": "Consumer Staples",
    "distribution services": "Industrials",
    "electronic technology": "Information Technology",
    "energy": "Energy",
    "energy minerals": "Energy",
    "finance": "Financials",
    "financial services": "Financials",
    "financials": "Financials",
    "health care": "Health Care",
    "health services": "Health Care",
    "health technology": "Health Care",
    "industrial services": "Industrials",
    "industrials": "Industrials",
    "information technology": "Information Technology",
    "non energy minerals": "Materials",
    "process industries": "Materials",
    "producer manufacturing": "Industrials",
    "real estate": "Real Estate",
    "technology": "Information Technology",
    "technology services": "Information Technology",
    "transportation": "Industrials",
    "utilities": "Utilities",
}


INDUSTRY_RULES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("Real Estate", ("real estate", "reit", "property developer", "property management", "incorporadora", "incorporacao imobiliaria", "empreendimentos imobiliarios"), "Real Estate"),
    ("Financials", ("bank", "banco", "credit services", "consumer finance"), "Banks & Credit"),
    ("Financials", ("insurance", "seguradora", "insurance brokers"), "Insurance"),
    ("Financials", ("asset management", "capital markets", "investment banking", "stock exchange", "securities exchange"), "Capital Markets & Exchanges"),
    ("Utilities", ("electric utility", "electric utilities", "regulated electric", "power distribution", "water utility", "water utilities", "saneamento", "gas utility", "gas utilities"), "Regulated Utilities"),
    ("Energy", ("oil & gas", "oil and gas", "petroleum", "exploration & production", "fuel distribution", "coal"), "Oil, Gas & Fuels"),
    ("Materials", ("steel", "mining", "metal", "aluminum", "iron ore"), "Metals & Mining"),
    ("Materials", ("chemical", "petrochemical", "fertilizer"), "Chemicals"),
    ("Materials", ("pulp", "paper", "forest products", "packaging"), "Pulp, Paper & Packaging"),
    ("Information Technology", ("software", "it services", "internet services", "technology services"), "Software & IT Services"),
    ("Information Technology", ("semiconductor", "electronic component", "technology hardware"), "Technology Hardware"),
    ("Health Care", ("biotech", "biotechnology", "pharmaceutical", "drug manufacturer", "health technology"), "Pharma & Biotechnology"),
    ("Health Care", ("health care services", "healthcare services", "medical care", "diagnostic", "hospital"), "Health Care Services"),
    ("Consumer Staples", ("food", "beverage", "tobacco", "household products", "drug retail"), "Consumer Staples"),
    ("Consumer Discretionary", ("vehicle rental", "apparel", "footwear", "department store", "homebuild", "education"), "Consumer Discretionary"),
    ("Industrials", ("construction & engineering", "construction and engineering", "industrial services", "engineering services"), "Industrial Services"),
    ("Industrials", ("electrical equipment", "machinery", "aerospace", "transportation", "logistics", "environmental services", "environmental facilities services"), "Industrial Manufacturing & Services"),
    ("Communication Services", ("telecom", "wireless", "media", "entertainment", "communication services"), "Telecom & Media"),
)


def _plain(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _contains(text: str, phrases: tuple[str, ...]) -> bool:
    normalized = f" {_plain(text)} "
    return any(f" {_plain(phrase)} " in normalized for phrase in phrases)


def _canonical_sector(value: Any) -> str | None:
    plain = _plain(value)
    if not plain:
        return None
    if plain in SECTOR_ALIASES:
        return SECTOR_ALIASES[plain]
    for canonical in CANONICAL_SECTORS:
        if plain == _plain(canonical):
            return canonical
    return None


def _industry_classification(text: str) -> tuple[str, str] | None:
    for sector, phrases, peer_group in INDUSTRY_RULES:
        if _contains(text, phrases):
            return sector, peer_group
    return None


def _profile(sector: str, industry: str) -> str:
    if sector == "Financials":
        return "financial"
    if sector == "Real Estate":
        return "real_estate"
    if sector == "Utilities":
        return "utilities"
    if sector in ("Energy", "Materials"):
        return "cyclical"
    if sector == "Information Technology" or _contains(industry, ("biotech", "biotechnology")):
        return "growth"
    return "general"


def canonical_b3_company_name(symbol: str, provider_name: Any) -> str:
    clean_symbol = symbol.upper().removesuffix(".SA").removesuffix("F")
    return COMPANY_NAME_OVERRIDES.get(clean_symbol, str(provider_name or clean_symbol))


def resolve_b3_sector(
    *,
    symbol: str,
    name: str,
    brapi_sector: Any,
    brapi_subsector: Any,
    eodhd: dict[str, Any] | None = None,
) -> SectorClassification:
    eodhd = eodhd or {}
    clean_symbol = symbol.upper().removesuffix(".SA").removesuffix("F")
    raw_brapi_sector = str(brapi_sector or "")
    raw_brapi_subsector = str(brapi_subsector or "")
    raw_eodhd_sector = str(eodhd.get("gicSector") or eodhd.get("sector") or "")
    raw_eodhd_industry = str(
        eodhd.get("gicSubIndustry")
        or eodhd.get("gicIndustry")
        or eodhd.get("industry")
        or ""
    )

    brapi_canonical = _canonical_sector(raw_brapi_sector)
    eodhd_canonical = _canonical_sector(raw_eodhd_sector)
    eodhd_industry_signal = _industry_classification(raw_eodhd_industry)
    brapi_industry_signal = _industry_classification(raw_brapi_subsector)
    name_signal = _industry_classification(name)
    sector_override = SECTOR_OVERRIDES.get(clean_symbol)

    if sector_override:
        sector, peer_group = sector_override
        source = "C3PO reviewed override"
        confidence = 100.0
    elif eodhd_canonical:
        sector = eodhd_canonical
        peer_group = eodhd_industry_signal[1] if eodhd_industry_signal and eodhd_industry_signal[0] == sector else sector
        source = "EODHD GICS" if eodhd.get("gicSector") else "EODHD sector"
        confidence = 98.0 if eodhd.get("gicSector") else 90.0
    elif eodhd_industry_signal:
        sector, peer_group = eodhd_industry_signal
        source = "EODHD industry"
        confidence = 88.0
    elif brapi_industry_signal and (not brapi_canonical or brapi_industry_signal[0] != brapi_canonical):
        sector, peer_group = brapi_industry_signal
        source = "Brapi subsector"
        confidence = 82.0
    elif name_signal and name_signal[0] == "Real Estate" and (not brapi_canonical or name_signal[0] != brapi_canonical):
        sector, peer_group = name_signal
        source = "C3PO business-name inference"
        confidence = 74.0
    elif brapi_canonical:
        sector = brapi_canonical
        peer_group = brapi_industry_signal[1] if brapi_industry_signal and brapi_industry_signal[0] == sector else sector
        source = "Brapi sector"
        confidence = 78.0
    else:
        inferred = _industry_classification(" ".join((raw_brapi_subsector, name)))
        sector, peer_group = inferred or ("Industrials", "Diversified Companies")
        source = "C3PO inferred"
        confidence = 65.0 if inferred else 45.0

    industry = raw_eodhd_industry or raw_brapi_subsector or peer_group
    provider_sectors = [value for value in (brapi_canonical, eodhd_canonical) if value]
    conflict = any(value != sector for value in provider_sectors)
    profile = _profile(sector, industry)
    profile_source = "Canonical sector rules"
    if clean_symbol in VALUATION_PROFILE_OVERRIDES:
        profile, peer_group = VALUATION_PROFILE_OVERRIDES[clean_symbol]
        profile_source = "C3PO reviewed business model"

    return SectorClassification(
        sector=sector,
        industry=industry,
        peer_group=peer_group,
        valuation_profile=profile,
        source=source,
        confidence=confidence,
        conflict=conflict,
        brapi_sector=raw_brapi_sector,
        brapi_subsector=raw_brapi_subsector,
        eodhd_sector=raw_eodhd_sector,
        eodhd_industry=raw_eodhd_industry,
        valuation_profile_source=profile_source,
    )
