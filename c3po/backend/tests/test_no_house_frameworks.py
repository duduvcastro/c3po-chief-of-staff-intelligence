"""Owner order of 20/10/2026: the "house frameworks" (Morgan Stanley, JPMorgan, Goldman Sachs, Bridgewater, BlackRock)
must not exist in any valuation model, target price or entry. The B3 entry is the lower of the return-hurdle and the
market-structure entries; no output of a valuation producer, and no valuation surface of the frontend, names a house.

The exceptions are DATA, not criteria: ``app/foreign_listings.py`` registers the real, dated public coverage calls of a
foreign primary listing (e.g. MHVYF / 7011.T), which the One Pager quotes verbatim as third-party coverage, and
``work/us_single_pagers.py`` lists real, dated broker calls (house, target, rating, date) in its coverage table. The
``work/`` scripts (the Chief of Staff morning summary and its single pagers) are scanned too.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from app.market_data.b3_screener import B3ScreenerService
from test_market_data import PETROBRAS_BENCHMARK, _petrobras_row
from test_one_pager import service_for

HOUSES = re.compile(r"morgan\s*stanley|j\.?\s*p\.?\s*morgan|goldman|bridgewater|blackrock", re.IGNORECASE)
BACKEND_APP = Path(__file__).resolve().parents[1] / "app"
FRONTEND_APP = Path(__file__).resolve().parents[2] / "frontend" / "app"
WORK = Path(__file__).resolve().parents[3] / "work"
# Files allowed to name a house, and why. Nothing here is a valuation criterion.
ALLOWED = {
    "foreign_listings.py": "real, dated public coverage calls of a foreign primary listing (third-party data, not a criterion)",
    "one_pager.py": "comments only: the 2026-08-20 rename record and a docstring naming BlackRock as a company in a peer basket",
}
WORK_ALLOWED = {
    "us_single_pagers.py": "real, dated third-party coverage calls quoted in the coverage table (house, target, rating, date)",
}
COVERAGE_QUOTE = re.compile(r'^\s*\{"house": "[^"]+", "target": [0-9.]+, "rating": "[^"]+", "date": "[^"]+", "call_date": "\d{4}-\d{2}-\d{2}"\},$')


def _house_hits(text: str) -> list[str]:
    return sorted({match.group(0) for match in HOUSES.finditer(text)})


def test_b3_valuation_row_names_no_house_and_its_buy_in_is_the_lower_of_hurdle_and_market_structure() -> None:
    macro = {"selic": 0.14, "ipca12m": 0.045}
    service = B3ScreenerService.__new__(B3ScreenerService)
    service._calibration_factors = {}
    for consensus in (True, False):
        row = _petrobras_row() if consensus else {**_petrobras_row(), "public_consensus_tp": None, "analyst_count": 0, "consensus_source_count": 0}
        row.update(B3ScreenerService._cyclical_market_multiples(row))
        service._value_row(row, PETROBRAS_BENCHMARK, macro)
        assert _house_hits(json.dumps(row, default=str)) == []
        for models, buy_in in ((row["buy_in_models"], row["buy_in"]), (row["internal_buy_in_models"], row["internal_buy_in"])):
            assert set(models) == {"Market Structure", "Return Hurdle"}
            assert buy_in == min(models.values()) > 0


def test_us_one_pager_producer_output_names_no_house(tmp_path) -> None:
    analysis = service_for(tmp_path)._analyze(
        "MSFT", "US",
        {"price": 500.0, "currency": "USD", "change_percent": 1.25, "as_of": datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc)},
        {"companyName": "Microsoft Corporation", "sector": "Technology", "marketCap": 3_700_000_000_000, "trailingPE": 31.0, "forwardPE": 27.0,
         "enterpriseToEbitda": 22.0, "pegRatio": 1.8, "trailingEps": 16.0, "forwardEps": 18.5, "bookValue": 42.0, "sharesOutstanding": 7_430_000_000,
         "freeCashflow": 92_000_000_000, "ebitda": 150_000_000_000, "totalDebt": 80_000_000_000, "totalCash": 90_000_000_000,
         "targetMeanPrice": 610.0, "numberOfAnalystOpinions": 48, "returnOnEquity": 0.34, "profitMargins": 0.36, "revenueGrowthAnnual": 0.15,
         "earningsGrowthAnnual": 0.17, "beta": 0.95},
        role="producer",
    )
    assert analysis["methods"] and _house_hits(json.dumps(analysis, default=str)) == []


def test_no_valuation_source_or_frontend_surface_names_a_house() -> None:
    hits: dict[str, list[str]] = {}
    for path in sorted(BACKEND_APP.rglob("*.py")):
        relative = path.relative_to(BACKEND_APP).as_posix()
        if relative in ALLOWED:
            continue
        found = _house_hits(path.read_text(encoding="utf-8"))
        if found:
            hits[f"app/{relative}"] = found
    for path in sorted(FRONTEND_APP.rglob("*.ts*")):
        found = _house_hits(path.read_text(encoding="utf-8"))
        if found:
            hits[f"frontend/app/{path.relative_to(FRONTEND_APP).as_posix()}"] = found
    for path in sorted(WORK.glob("*.py")):
        if path.name in WORK_ALLOWED:
            continue
        found = _house_hits(path.read_text(encoding="utf-8"))
        if found:
            hits[f"work/{path.name}"] = found
    assert hits == {}
    # the allowlisted coverage table quotes a house only as a real, dated third-party call — never a method or a criterion
    for name in WORK_ALLOWED:
        lines = [line for line in (WORK / name).read_text(encoding="utf-8").splitlines() if HOUSES.search(line)]
        assert lines and all(COVERAGE_QUOTE.match(line) for line in lines), name
    # the allowlisted One Pager names a house only in its comments and in one docstring, never in code
    one_pager = (BACKEND_APP / "one_pager.py").read_text(encoding="utf-8")
    assert all(line.lstrip().startswith("#") or "basket with" in line for line in one_pager.splitlines() if HOUSES.search(line))
