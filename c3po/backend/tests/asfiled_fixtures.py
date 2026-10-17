"""Synthetic SEC EDGAR fixtures for the as-filed front (no network): one calendar-year issuer, SYNT, CIK 0000999001,
with 10-Qs and 10-Ks from Q3 2024 to FY 2025, an 8-K item 2.02, an 8-K without it and an optional 10-Q/A. Every
submissions-JSON acceptanceDateTime is built the way EDGAR serves it (verified 2026-10-17): the true instant PLUS the New
York UTC offset; the filing headers carry the true New York wall clock."""
from __future__ import annotations

import html
import json
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

NEW_YORK = ZoneInfo("America/New_York")
CIK = "0000999001"
SYMBOL = "SYNT"

QUARTERS = {  # quarterly values by calendar year (the fixture's FY = sum of its quarters)
    "revenue": {2024: [85, 88, 90, 97], 2025: [92, 98, 100, 110]},
    "net_income": {2024: [10, 11, 12, 13], 2025: [12, 13, 14, 16]},
    "eps_diluted": {2024: [0.10, 0.11, 0.12, 0.13], 2025: [0.12, 0.13, 0.14, 0.16]},
    "operating_income": {2024: [15, 16, 17, 18], 2025: [17, 18, 19, 21]},
    "d_and_a": {2024: [2, 3, 3, 3], 2025: [3, 3, 3, 4]},
    "operating_cash_flow": {2024: [20, 21, 22, 23], 2025: [22, 23, 24, 26]},
    "capex": {2024: [5, 5, 5, 6], 2025: [6, 6, 6, 7]},
}
CONCEPTS = {
    "revenue": "Revenues",
    "net_income": "NetIncomeLoss",
    "eps_diluted": "EarningsPerShareDiluted",
    "operating_income": "OperatingIncomeLoss",
    "d_and_a": "DepreciationDepletionAndAmortization",
    "operating_cash_flow": "NetCashProvidedByUsedInOperatingActivities",
    "capex": "PaymentsToAcquirePropertyPlantAndEquipment",
}
CASH_FLOW_ONLY_YTD = {"d_and_a", "operating_cash_flow", "capex"}
INSTANTS = {  # balance-sheet values by period end
    "CashAndCashEquivalentsAtCarryingValue": {"2023-12-31": 50, "2024-09-30": 55, "2024-12-31": 60, "2025-03-31": 62, "2025-06-30": 64, "2025-09-30": 66, "2025-12-31": 70},
    "StockholdersEquity": {"2023-12-31": 300, "2024-09-30": 320, "2024-12-31": 330, "2025-03-31": 335, "2025-06-30": 340, "2025-09-30": 345, "2025-12-31": 360},
    "LongTermDebtNoncurrent": {"2023-12-31": 200, "2024-09-30": 195, "2024-12-31": 190, "2025-03-31": 188, "2025-06-30": 186, "2025-09-30": 184, "2025-12-31": 180},
    "LongTermDebtCurrent": {"2023-12-31": 10, "2024-09-30": 10, "2024-12-31": 10, "2025-03-31": 10, "2025-06-30": 10, "2025-09-30": 10, "2025-12-31": 12},
    "CommercialPaper": {"2023-12-31": 5, "2024-09-30": 5, "2024-12-31": 5, "2025-03-31": 5, "2025-06-30": 5, "2025-09-30": 5, "2025-12-31": 6},
}
QUARTER_BOUNDS = {1: ("01-01", "03-31"), 2: ("04-01", "06-30"), 3: ("07-01", "09-30"), 4: ("10-01", "12-31")}


def document(accession: str, form: str, year: int, quarter: int, accepted_ny: str, *, cover: str, filed: str) -> dict[str, Any]:
    return {"accession": accession, "form": form, "year": year, "quarter": quarter, "accepted_ny": accepted_ny, "cover": cover, "filed": filed}


DOCUMENTS = [
    document("0000999001-24-000030", "10-Q", 2024, 3, "20241105163000", cover="2024-10-25", filed="2024-11-05"),
    document("0000999001-25-000005", "10-K", 2024, 4, "20250220163000", cover="2025-02-10", filed="2025-02-20"),
    document("0000999001-25-000012", "10-Q", 2025, 1, "20250505163000", cover="2025-04-25", filed="2025-05-05"),
    document("0000999001-25-000020", "10-Q", 2025, 2, "20250805163000", cover="2025-07-25", filed="2025-08-05"),
    document("0000999001-25-000030", "10-Q", 2025, 3, "20251105163000", cover="2025-10-25", filed="2025-11-05"),
    document("0000999001-26-000005", "10-K", 2025, 4, "20260220163000", cover="2026-02-10", filed="2026-02-20"),
]
EIGHT_K_RESULTS = {"accession": "0000999001-26-000003", "form": "8-K", "items": "2.02,9.01", "accepted_ny": "20260212160500",
                   "filed": "2026-02-12", "report_date": "2026-02-12"}
EIGHT_K_OTHER = {"accession": "0000999001-26-000004", "form": "8-K", "items": "5.02", "accepted_ny": "20260213090000",
                 "filed": "2026-02-13", "report_date": "2026-02-13"}
RESTATEMENT = document("0000999001-26-000008", "10-Q/A", 2025, 3, "20260310163000", cover="2026-03-01", filed="2026-03-10")
RESTATED_Q3_REVENUE = 101
SHARE_CLASSES_FY2025 = (900, 100)  # the FY 2025 10-K reports its cover-page share count per class


def true_instant(accepted_ny: str) -> datetime:
    return datetime.strptime(accepted_ny, "%Y%m%d%H%M%S").replace(tzinfo=NEW_YORK).astimezone(timezone.utc)


def submissions_json_clock(accepted_ny: str) -> str:
    """What EDGAR's submissions JSON shows: the true instant plus the New York offset, labelled Z."""
    local = datetime.strptime(accepted_ny, "%Y%m%d%H%M%S").replace(tzinfo=NEW_YORK)
    offset = local.utcoffset()
    assert offset is not None
    shown = local.astimezone(timezone.utc) - offset  # offset is negative: subtracting it ADDS the hours
    return shown.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _period(year: int, quarter: int) -> tuple[str, str]:
    start, end = QUARTER_BOUNDS[quarter]
    return f"{year}-{start}", f"{year}-{end}"


def _fact(start: str | None, end: str, value: Any, doc: dict[str, Any]) -> dict[str, Any]:
    fact = {"end": end, "val": value, "accn": doc["accession"], "fy": doc["year"], "fp": "FY" if doc["form"].startswith("10-K") else f"Q{doc['quarter']}",
            "form": doc["form"], "filed": doc["filed"]}
    if start is not None:
        fact["start"] = start
    return fact


def _round(value: float) -> float | int:
    rounded = round(value, 4)
    return int(rounded) if float(rounded).is_integer() else rounded


def _document_facts(doc: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    year, quarter = doc["year"], doc["quarter"]
    facts: dict[str, list[dict[str, Any]]] = {}
    for field, by_year in QUARTERS.items():
        concept = CONCEPTS[field]
        rows = facts.setdefault(concept, [])
        for fact_year in (year, year - 1):
            values = by_year.get(fact_year)
            if not values:
                continue
            if field not in CASH_FLOW_ONLY_YTD and quarter < 4:
                start, end = _period(fact_year, quarter)
                rows.append(_fact(start, end, _round(values[quarter - 1]), doc))
            if quarter > 1 or field in CASH_FLOW_ONLY_YTD:
                rows.append(_fact(f"{fact_year}-01-01", _period(fact_year, quarter)[1], _round(sum(values[:quarter])), doc))
    period_end = _period(year, quarter)[1]
    for concept, by_end in INSTANTS.items():
        rows = facts.setdefault(concept, [])
        for end in (period_end, f"{year - 1}-12-31"):
            if end in by_end:
                rows.append(_fact(None, end, by_end[end], doc))
    return facts


def companyfacts(*, include_restatement: bool = False) -> dict[str, Any]:
    us_gaap: dict[str, Any] = {}
    shares: list[dict[str, Any]] = []
    documents = [*DOCUMENTS, *([RESTATEMENT] if include_restatement else [])]
    for doc in documents:
        if doc is RESTATEMENT:
            facts = {"Revenues": [_fact("2025-07-01", "2025-09-30", RESTATED_Q3_REVENUE, doc),
                                  _fact("2025-01-01", "2025-09-30", 92 + 98 + RESTATED_Q3_REVENUE, doc)]}
        else:
            facts = _document_facts(doc)
        for concept, rows in facts.items():
            unit = "USD/shares" if concept == "EarningsPerShareDiluted" else "USD"
            us_gaap.setdefault(concept, {"label": concept, "units": {unit: []}})["units"][unit].extend(rows)
        if doc is not RESTATEMENT:
            if doc["accession"] == "0000999001-26-000005":
                shares.extend(_fact(None, doc["cover"], value, doc) for value in SHARE_CLASSES_FY2025)
            else:
                shares.append(_fact(None, doc["cover"], 950, doc))
    # a fact of a form outside the 10-Q/10-K family (an S-8 cover) never becomes a vintage
    shares.append({"end": "2025-06-01", "val": 1, "accn": "0000999001-25-000099", "fy": 2025, "fp": "Q2", "form": "S-8", "filed": "2025-06-01"})
    return {"cik": int(CIK), "entityName": "Synthetic Corp", "facts": {
        "us-gaap": us_gaap,
        "dei": {"EntityCommonStockSharesOutstanding": {"label": "Shares", "units": {"shares": shares}}},
    }}


def _filing_rows(include_restatement: bool) -> list[dict[str, Any]]:
    rows = [
        {"accession": doc["accession"], "form": doc["form"], "items": "", "accepted_ny": doc["accepted_ny"], "filed": doc["filed"],
         "report_date": _period(doc["year"], doc["quarter"])[1]}
        for doc in DOCUMENTS
    ]
    rows += [EIGHT_K_RESULTS, EIGHT_K_OTHER]
    if include_restatement:
        rows.append({"accession": RESTATEMENT["accession"], "form": RESTATEMENT["form"], "items": "", "accepted_ny": RESTATEMENT["accepted_ny"],
                     "filed": RESTATEMENT["filed"], "report_date": "2025-09-30"})
    return sorted(rows, key=lambda row: row["accepted_ny"], reverse=True)


def submissions(*, include_restatement: bool = False, json_clock: Any = submissions_json_clock) -> dict[str, Any]:
    rows = _filing_rows(include_restatement)
    return {"cik": CIK, "name": "Synthetic Corp", "tickers": [SYMBOL], "filings": {"recent": {
        "accessionNumber": [row["accession"] for row in rows],
        "form": [row["form"] for row in rows],
        "items": [row["items"] for row in rows],
        "filingDate": [row["filed"] for row in rows],
        "reportDate": [row["report_date"] for row in rows],
        "acceptanceDateTime": [json_clock(row["accepted_ny"]) for row in rows],
        "primaryDocument": [f"{row['accession']}.htm" for row in rows],
        "primaryDocDescription": [row["form"] for row in rows],
        "isXBRL": [1 for _ in rows],
    }}}


def header_html(accession: str, *, form: str, accepted_ny: str, period: str, filed: str, items: tuple[str, ...] = ()) -> str:
    lines = [
        f"<SEC-HEADER>{accession}.hdr.sgml : {filed.replace('-', '')}",
        f"<ACCEPTANCE-DATETIME>{accepted_ny}",
        f"ACCESSION NUMBER:\t\t{accession}",
        f"CONFORMED SUBMISSION TYPE:\t{form}",
        "PUBLIC DOCUMENT COUNT:\t\t7",
        f"CONFORMED PERIOD OF REPORT:\t{period.replace('-', '')}",
        *(f"ITEM INFORMATION:\t\t{item}" for item in items),
        f"FILED AS OF DATE:\t\t{filed.replace('-', '')}",
        f"DATE AS OF CHANGE:\t\t{filed.replace('-', '')}",
        "",
        "FILER:",
        "",
        "\tCOMPANY DATA:\t",
        "\t\tCOMPANY CONFORMED NAME:\t\t\tSYNTHETIC CORP",
        f"\t\tCENTRAL INDEX KEY:\t\t\t{CIK}",
        "</SEC-HEADER>",
    ]
    return "<html><head><title>header</title></head><body><pre>" + html.escape("\n".join(lines)) + "</pre></body></html>"


def headers(*, include_restatement: bool = False) -> dict[str, str]:
    output = {}
    for row in _filing_rows(include_restatement):
        items = ("Results of Operations and Financial Condition", "Financial Statements and Exhibits") if "2.02" in row["items"] else ()
        output[row["accession"]] = header_html(row["accession"], form=row["form"], accepted_ny=row["accepted_ny"], period=row["report_date"],
                                               filed=row["filed"], items=items)
    return output


class EdgarFake:
    """An httpx MockTransport handler serving the fixtures; records every request (URL and User-Agent)."""

    def __init__(self, *, include_restatement: bool = False, json_clock: Any = submissions_json_clock, failing_headers: set[str] | None = None,
                 throttled_paths: set[str] | None = None) -> None:
        self.include_restatement = include_restatement
        self.json_clock = json_clock
        self.failing_headers = set(failing_headers or ())
        self.throttled_paths = set(throttled_paths or ())
        self.requests: list[httpx.Request] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(lambda request: self.handle(request))  # resolved per request: a test may swap the handler

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path in self.throttled_paths:
            return httpx.Response(429)
        if path == "/files/company_tickers.json":
            return httpx.Response(200, json={"0": {"cik_str": int(CIK), "ticker": SYMBOL, "title": "Synthetic Corp"},
                                             "1": {"cik_str": 999002, "ticker": "OTHR", "title": "Other Corp"}})
        if path == f"/submissions/CIK{CIK}.json":
            return httpx.Response(200, content=json.dumps(submissions(include_restatement=self.include_restatement, json_clock=self.json_clock)))
        if path == f"/api/xbrl/companyfacts/CIK{CIK}.json":
            return httpx.Response(200, json=companyfacts(include_restatement=self.include_restatement))
        if path.endswith("-index-headers.html"):
            accession = path.rsplit("/", 1)[-1].removesuffix("-index-headers.html")
            page = headers(include_restatement=self.include_restatement).get(accession)
            if page is None or accession in self.failing_headers:
                return httpx.Response(503 if accession in self.failing_headers else 404)
            return httpx.Response(200, text=page)
        return httpx.Response(404)

    def paths(self) -> list[str]:
        return [request.url.path for request in self.requests]


def as_of(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def day(value: str) -> date:
    return date.fromisoformat(value)
