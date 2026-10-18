"""SEC EDGAR as filed (Valuation as-filed, owner's direction 2026-10-17): the US source of record for quarterly statements.

* **The client** (``SecXbrlClient``) never calls the SEC without the contact configured on the host
  (``C3PO_SEC_CONTACT``, sent in the User-Agent) and spaces its requests through one per-process limiter
  (``C3PO_SEC_MAX_REQUESTS_PER_SECOND``, default 2.5/s, never above 8/s). SEC fair access is 8/s for the whole host
  and three processes call EDGAR (API, Investor Relations worker, valuation worker): 3 × 2.5 ≤ 8.
* **The acceptance clock** is the filing header's ``<ACCEPTANCE-DATETIME>`` (``…/<accession>-index-headers.html``),
  America/New_York. The submissions JSON ``acceptanceDateTime`` is NOT true UTC — verified 2026-10-17 on AAPL
  0000320193-26-000018 (header 20260730163028, JSON 2026-07-31T00:30:28Z) and 0000320193-26-000005 (header
  20260129163033, JSON 2026-01-30T02:30:33Z): the JSON value is the true instant PLUS the New York UTC offset.
  ``acceptance_from_submissions_json`` undoes that for the places that only have the JSON; wherever a header is read,
  the header wins and a disagreement with the corrected JSON is counted and logged (the correction is evidence-based,
  so a change on the SEC side shows up instead of silently shifting clocks).
* **companyfacts → statement vintages**: every fact of the concept ladder (``CONCEPT_LADDER``) that a 10-Q/10-K-family
  document reported, one row per (document, concept, unit, period), stamped with that document's header acceptance.
  The first publication of each fact is kept as it was filed (later documents re-reporting it are new rows of their own).
* **Quarters**: ``discrete_quarters`` turns year-to-date durations into quarters (Q2 = 6M − 3M, Q3 = 9M − 6M,
  Q4 = FY − 9M); a reported three-month fact always wins over a derived one.
* **The poll** (``SecXbrlIngestor.poll``), run by ``InvestorRelationsService.sync_sec_asfiled`` in the Investor Relations
  worker's SEC polling loop: for the US valuation universe, register every newly accepted 10-Q/10-K (and amendments)
  and 8-K carrying item 2.02, then ingest the issuer's companyfacts when a statement document is new or still
  pending, when an earlier ingestion deferred documents behind a header that failed (retried with a growing backoff),
  and — a few issuers per poll — when the issuer's newest original 10-Q/10-K has no stored fact (the backfill, and the
  durable repair of a gap whose in-memory retry state a restart lost).

Nothing here changes a served number; the whole path is behind ``C3PO_VALUATION_ASFILED_ENABLED`` (default off).
"""
from __future__ import annotations

import hashlib
import html
import logging
import re
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from .config import Settings
from .database import Database
from .statement_vintages import StatementVintageStore, as_date, utc_instant


logger = logging.getLogger(__name__)

NEW_YORK = ZoneInfo("America/New_York")
MARKET = "US"
FILING_SOURCE = "sec_edgar"
VINTAGE_SOURCE = "sec_xbrl_companyfacts"
ACCEPTED_FROM_HEADER = "sec_header"
SEC_FAIR_ACCESS_MAX_PER_SECOND = 8.0
USER_AGENT_PRODUCT = "C3PO Chief of Staff Intelligence"

STATEMENT_FORMS = frozenset({"10-Q", "10-K", "10-Q/A", "10-K/A", "10-QT", "10-KT", "10-QT/A", "10-KT/A"})
ORIGINAL_STATEMENT_FORMS = frozenset({"10-Q", "10-K", "10-QT", "10-KT"})  # always carry the financial statements in XBRL
RESULTS_FORMS = frozenset({"10-Q", "10-K", "10-Q/A", "10-K/A"})
EARNINGS_RELEASE_FORMS = frozenset({"8-K", "8-K/A"})
EARNINGS_RELEASE_ITEM = "2.02"  # Results of Operations and Financial Condition

VINTAGE_LOOKBACK_DAYS = 6 * 366  # facts whose period ended earlier are not ingested (every publication of a kept fact is)
DETECTION_LOOKBACK_DAYS = 10  # a filing accepted earlier than this is history (companyfacts), not a new-filing event
PENDING_FACTS_DAYS = 3  # a registered statement document whose facts are not in companyfacts yet is retried this long
PENDING_RETRY = timedelta(hours=1)
DEFERRED_RETRY = timedelta(minutes=5)  # documents deferred behind a failed header: the next poll retries them …
DEFERRED_RETRY_MAX = timedelta(hours=6)  # … and every further failure doubles the wait, up to this
NOT_BEFORE = datetime.min.replace(tzinfo=timezone.utc)

# The concept ladder: per field, the us-gaap/dei concepts in priority order (the first one reported for a period wins).
# Debt is kept by component — the bridge adds long + short without double counting (see valuation_asfiled.total_debt).
CONCEPT_LADDER: dict[str, tuple[str, ...]] = {
    "revenue": (
        "us-gaap:Revenues",
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax",
        "us-gaap:SalesRevenueNet",
        "us-gaap:RevenuesNetOfInterestExpense",
    ),
    "net_income": ("us-gaap:NetIncomeLoss", "us-gaap:ProfitLoss", "us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic"),
    "eps_diluted": ("us-gaap:EarningsPerShareDiluted", "us-gaap:EarningsPerShareBasicAndDiluted"),
    "operating_income": ("us-gaap:OperatingIncomeLoss",),
    "d_and_a": (
        "us-gaap:DepreciationDepletionAndAmortization",
        "us-gaap:DepreciationAndAmortization",
        "us-gaap:DepreciationAmortizationAndAccretionNet",
        "us-gaap:Depreciation",
    ),
    "operating_cash_flow": (
        "us-gaap:NetCashProvidedByUsedInOperatingActivities",
        "us-gaap:NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    "capex": ("us-gaap:PaymentsToAcquirePropertyPlantAndEquipment", "us-gaap:PaymentsToAcquireProductiveAssets"),
    "cash": (
        "us-gaap:CashAndCashEquivalentsAtCarryingValue",
        "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "us-gaap:Cash",
    ),
    "long_term_debt": ("us-gaap:LongTermDebtNoncurrent", "us-gaap:LongTermDebtAndCapitalLeaseObligations"),
    "long_term_debt_including_current": ("us-gaap:LongTermDebt",),
    "debt_current": ("us-gaap:DebtCurrent",),
    "long_term_debt_current": ("us-gaap:LongTermDebtCurrent", "us-gaap:LongTermDebtAndCapitalLeaseObligationsCurrent"),
    "short_term_borrowings": ("us-gaap:ShortTermBorrowings", "us-gaap:CommercialPaper"),  # commercial paper only when no total is tagged
    "stockholders_equity": (
        "us-gaap:StockholdersEquity",
        "us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
    "shares_outstanding": ("dei:EntityCommonStockSharesOutstanding",),
}
DURATION_FIELDS = frozenset({"revenue", "net_income", "eps_diluted", "operating_income", "d_and_a", "operating_cash_flow", "capex"})
FIELD_UNITS = {"eps_diluted": "USD/shares", "shares_outstanding": "shares"}
CLASS_SUMMED_CONCEPTS = frozenset({"dei:EntityCommonStockSharesOutstanding"})  # one value per share class, same cover date
CONCEPT_UNITS: dict[str, str] = {
    concept: FIELD_UNITS.get(name, "USD") for name, concepts in CONCEPT_LADDER.items() for concept in concepts
}
DURATION_MONTH_DAYS = ((3, 80, 100), (6, 170, 195), (9, 260, 285), (12, 350, 380))  # (months, min, max) of end − start in days
QUARTER_CONTIGUITY_DAYS = 3


class SecContactMissing(RuntimeError):
    """``C3PO_SEC_CONTACT`` is not configured: the as-filed client refuses to call the SEC (fair-access policy)."""


class SecHeaderError(ValueError):
    """A filing header without a parseable ``<ACCEPTANCE-DATETIME>``."""


class SecThrottled(RuntimeError):
    """The SEC answered 403/429 (fair-access refusal): the pass stops at once instead of pressing on with the rest of the
    universe; the next poll starts over."""


# -- clocks ------------------------------------------------------------------------------------------------------------

def acceptance_from_header(value: str) -> datetime:
    """``YYYYMMDDHHMMSS`` in America/New_York (the header's own zone) → the UTC instant."""
    text = str(value).strip()
    if not re.fullmatch(r"\d{14}", text):
        raise SecHeaderError(f"acceptance datetime {value!r} is not YYYYMMDDHHMMSS")
    local = datetime.strptime(text, "%Y%m%d%H%M%S").replace(tzinfo=NEW_YORK)
    return local.astimezone(timezone.utc)


def acceptance_from_submissions_json(value: str) -> datetime:
    """The true UTC instant behind a submissions-JSON ``acceptanceDateTime``.

    The JSON value is the true instant plus the New York UTC offset (4 h under EDT, 5 h under EST — verified 2026-10-17
    against the filing headers, see the module docstring), so the instant is the shown value minus the offset that is in
    force AT the instant: the candidate whose own New York offset matches the hours subtracted. Around a DST switch (a
    Sunday night, EDGAR closed) the value can be ambiguous; the EDT reading is taken first. The header is the source of
    truth — this is for the places that only have the JSON."""
    shown = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    shown = (shown if shown.tzinfo else shown.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    for hours in (4, 5):
        candidate = shown - timedelta(hours=hours)
        if candidate.astimezone(NEW_YORK).utcoffset() == timedelta(hours=-hours):
            return candidate
    return shown - timedelta(hours=5)


def _header_date(value: str | None) -> date | None:
    text = (value or "").strip()
    if not re.fullmatch(r"\d{8}", text):
        return None
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None


def parse_filing_header(text: str) -> dict[str, Any]:
    """The fields of an EDGAR ``-index-headers.html`` page (SGML header, HTML-escaped inside a ``<pre>``)."""
    body = html.unescape(text or "")
    accepted = re.search(r"<ACCEPTANCE-DATETIME>\s*(\d{14})", body)
    if not accepted:
        raise SecHeaderError("filing header has no <ACCEPTANCE-DATETIME>")
    fields: dict[str, list[str]] = {}
    for match in re.finditer(r"^[ \t]*([A-Z][A-Z0-9 \-]*[A-Z0-9]):[ \t]*(.*?)[ \t]*$", body, re.MULTILINE):
        fields.setdefault(match.group(1), []).append(match.group(2))

    def first(name: str) -> str | None:
        values = [value for value in fields.get(name, []) if value]
        return values[0] if values else None

    return {
        "accepted_at": acceptance_from_header(accepted.group(1)),
        "acceptance_raw": accepted.group(1),
        "accession": first("ACCESSION NUMBER"),
        "form": first("CONFORMED SUBMISSION TYPE"),
        "period_of_report": _header_date(first("CONFORMED PERIOD OF REPORT")),
        "filed_date": _header_date(first("FILED AS OF DATE")),
        "item_information": [value for value in fields.get("ITEM INFORMATION", []) if value],
        "header_sha256": hashlib.sha256((text or "").encode("utf-8")).hexdigest(),
    }


# -- filings of a submissions payload ----------------------------------------------------------------------------------

def filing_items(value: Any) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def is_trigger_filing(form: str, items: Iterable[str]) -> bool:
    """A filing that revalues a US target price: a 10-Q/10-K (or amendment), or an 8-K reporting item 2.02."""
    return form in RESULTS_FORMS or (form in EARNINGS_RELEASE_FORMS and EARNINGS_RELEASE_ITEM in set(items))


def recent_filings(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The ``filings.recent`` columns of a submissions payload as one dict per filing, with the JSON acceptance kept
    verbatim and its corrected instant (``accepted_at_json``; ``None`` when the value does not parse)."""
    recent = (payload.get("filings") or {}).get("recent") or {}
    accessions = list(recent.get("accessionNumber") or [])

    def column(name: str, index: int) -> Any:
        values = recent.get(name) or []
        return values[index] if index < len(values) else None

    output: list[dict[str, Any]] = []
    for index, accession in enumerate(accessions):
        raw = column("acceptanceDateTime", index)
        try:
            accepted = acceptance_from_submissions_json(str(raw)) if raw else None
        except ValueError:
            accepted = None
        output.append({
            "accession": str(accession),
            "form": str(column("form", index) or ""),
            "items": filing_items(column("items", index)),
            "filed_date": _iso_date(column("filingDate", index)),
            "report_date": _iso_date(column("reportDate", index)),
            "json_accepted_raw": str(raw) if raw else None,
            "accepted_at_json": accepted,
            "primary_document": str(column("primaryDocument", index) or ""),
        })
    return output


def _iso_date(value: Any) -> date | None:
    try:
        return as_date(value)
    except ValueError:
        return None


# -- companyfacts → vintages -------------------------------------------------------------------------------------------

def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def companyfacts_accessions(payload: Mapping[str, Any]) -> set[str]:
    """Every accession companyfacts already carries a fact of (any concept): a registered document absent from here has
    not been processed by the SEC's XBRL API yet."""
    found: set[str] = set()
    for concepts in (payload.get("facts") or {}).values():
        if not isinstance(concepts, Mapping):
            continue
        for entry in concepts.values():
            for items in ((entry or {}).get("units") or {}).values():
                for item in items or ():
                    if isinstance(item, Mapping) and item.get("accn"):
                        found.add(str(item["accn"]))
    return found


def companyfacts_vintages(payload: Mapping[str, Any], *, issuer_key: str, since: date) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """The ladder facts of a companyfacts payload as vintage rows WITHOUT their acceptance clock (the ingestor stamps it
    from the header registry): one row per (document, concept, unit, period) of a 10-Q/10-K-family document, for periods
    ending on/after ``since``. Repeats of one fact inside a document collapse; a dei share count reported per class
    (same document and cover date, different values) is summed; any other conflict drops the fact (counted)."""
    stats = {"facts": 0, "other_forms": 0, "malformed": 0, "before_lookback": 0, "conflicting": 0, "classes_summed": 0}
    grouped: dict[tuple[str, str, str, date | None, date], dict[str, Any]] = {}
    facts = payload.get("facts") or {}
    for concept, unit in CONCEPT_UNITS.items():
        taxonomy, name = concept.split(":", 1)
        entry = (facts.get(taxonomy) or {}).get(name) if isinstance(facts.get(taxonomy), Mapping) else None
        for item in ((entry or {}).get("units") or {}).get(unit) or ():
            if not isinstance(item, Mapping):
                stats["malformed"] += 1
                continue
            form = str(item.get("form") or "")
            if form not in STATEMENT_FORMS:
                stats["other_forms"] += 1
                continue
            accession = str(item.get("accn") or "")
            value = _decimal(item.get("val"))
            try:
                end, start, filed = as_date(item.get("end")), as_date(item.get("start")), as_date(item.get("filed"))
            except ValueError:
                stats["malformed"] += 1
                continue
            if not accession or end is None or filed is None or value is None or (start is not None and start > end):
                stats["malformed"] += 1
                continue
            if end < since:
                stats["before_lookback"] += 1
                continue
            stats["facts"] += 1
            key = (accession, concept, unit, start, end)
            group = grouped.setdefault(key, {
                "accession": accession, "concept": concept, "unit": unit, "start": start, "end": end, "form": form,
                "filed": filed, "fy": item.get("fy"), "fp": item.get("fp"), "values": set(),
            })
            group["values"].add(value)
    rows: list[dict[str, Any]] = []
    for group in grouped.values():
        values: set[Decimal] = group["values"]
        if len(values) > 1:
            if group["concept"] not in CLASS_SUMMED_CONCEPTS:
                stats["conflicting"] += 1
                continue
            stats["classes_summed"] += 1
        fiscal_year = group["fy"]
        rows.append({
            "market": MARKET,
            "issuer_key": issuer_key,
            "source": VINTAGE_SOURCE,
            "doc_id": group["accession"],
            "document_version": 1,  # an accession is immutable; an amendment is another accession ("…/A")
            "form": group["form"],
            "fiscal_year": int(fiscal_year) if isinstance(fiscal_year, int) and not isinstance(fiscal_year, bool) else None,
            "fiscal_period": str(group["fp"]) if group["fp"] else None,
            "period_start": group["start"],
            "period_end": group["end"],
            "concept": group["concept"],
            "unit": group["unit"],
            "value": sum(values, Decimal(0)),
            "filed_date": group["filed"],
        })
    rows.sort(key=lambda row: (row["filed_date"], row["doc_id"], row["concept"], row["period_end"]))
    return rows, stats


# -- quarters ----------------------------------------------------------------------------------------------------------

def duration_months(start: date, end: date) -> int | None:
    """3, 6, 9 or 12 when ``end − start`` is a (52/53-week tolerant) quarter, half, nine months or year; else None."""
    days = (end - start).days
    for months, low, high in DURATION_MONTH_DAYS:
        if low <= days <= high:
            return months
    return None


def discrete_quarters(durations: Mapping[tuple[date, date], Mapping[str, Any]]) -> dict[tuple[date, date], dict[str, Any]]:
    """``(start, end) → fact`` (each fact a mapping with at least ``value``) → ``(start, end) → quarter``.

    A three-month fact is a reported quarter. Year-to-date facts sharing a start date give the others by difference:
    Q2 = 6M − 3M, Q3 = 9M − 6M and Q4 = FY − 9M (the quarter runs from the day after the shorter period's end to the
    longer one's end). A reported quarter always wins over a derived one of the same period. Each quarter carries
    ``value`` (float), ``derived`` and ``facts`` (the facts it was computed from)."""
    quarters: dict[tuple[date, date], dict[str, Any]] = {}
    by_start: dict[date, list[tuple[int, date, Mapping[str, Any]]]] = {}
    for (start, end), fact in durations.items():
        months = duration_months(start, end)
        if months is None:
            continue
        if months == 3:
            quarters[(start, end)] = {"value": float(fact["value"]), "derived": False, "facts": [fact]}
        by_start.setdefault(start, []).append((months, end, fact))
    for chain in by_start.values():
        chain.sort(key=lambda item: item[1])
        for (shorter_months, shorter_end, shorter), (longer_months, longer_end, longer) in zip(chain, chain[1:]):
            if longer_months - shorter_months != 3:
                continue
            key = (shorter_end + timedelta(days=1), longer_end)
            if any(end == longer_end for _, end in quarters):  # that quarter is already known (reported, or derived once)
                continue
            quarters[key] = {"value": float(longer["value"]) - float(shorter["value"]), "derived": True, "facts": [longer, shorter]}
    return quarters


def trailing_quarters(quarters: Mapping[tuple[date, date], Mapping[str, Any]], count: int = 4) -> list[tuple[date, date]]:
    """The ``count`` most recent CONTIGUOUS quarters ending at the latest one (newest first), or ``[]`` when the chain
    breaks (a missing quarter is never bridged)."""
    if not quarters:
        return []
    remaining = sorted(quarters, key=lambda key: key[1], reverse=True)
    chain = [remaining[0]]
    while len(chain) < count:
        start = chain[-1][0]
        previous = next(
            (key for key in remaining if abs((start - timedelta(days=1) - key[1]).days) <= QUARTER_CONTIGUITY_DAYS and key not in chain),
            None,
        )
        if previous is None:
            return []
        chain.append(previous)
    return chain


# -- the client --------------------------------------------------------------------------------------------------------

class SecRateLimiter:
    """At most ``rate`` request starts per second for every thread of the process: each start is spaced 1/rate apart."""

    def __init__(self, rate: float, *, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> None:
        self._lock = threading.Lock()
        self._clock, self._sleep = clock, sleep
        self._next_start = 0.0
        self.rate = min(float(rate), SEC_FAIR_ACCESS_MAX_PER_SECOND)

    @property
    def rate(self) -> float:
        return self._rate

    @rate.setter
    def rate(self, value: float) -> None:
        if not value > 0:
            raise ValueError("SEC rate must be positive")
        self._rate = min(float(value), SEC_FAIR_ACCESS_MAX_PER_SECOND)
        self._interval = 1.0 / self._rate

    def acquire(self) -> None:
        with self._lock:
            now = self._clock()
            wait = self._next_start - now
            if wait > 0:
                self._sleep(wait)
                now = self._clock()
            self._next_start = max(now, self._next_start) + self._interval


_PROCESS_LIMITER: SecRateLimiter | None = None
_PROCESS_LIMITER_GUARD = threading.Lock()


def process_rate_limiter(rate: float) -> SecRateLimiter:
    """The ONE limiter of this process — every SEC request of the process passes through it (the as-filed client and the
    Investor Relations client alike); a caller asking for a lower rate lowers it, never raises it."""
    global _PROCESS_LIMITER
    with _PROCESS_LIMITER_GUARD:
        limiter = _PROCESS_LIMITER
        if limiter is None:
            limiter = _PROCESS_LIMITER = SecRateLimiter(rate)
        elif rate < limiter.rate:
            limiter.rate = rate
        return limiter


def is_sec_host(host: str) -> bool:
    clean = (host or "").lower().rstrip(".")
    return clean == "sec.gov" or clean.endswith(".sec.gov")


def sec_user_agent(contact: str) -> str:
    clean = (contact or "").strip()
    if not clean:
        raise SecContactMissing("C3PO_SEC_CONTACT is not configured: the as-filed client never calls the SEC without a contact")
    return f"{USER_AGENT_PRODUCT} {clean}"


class SecXbrlClient:
    """data.sec.gov / www.sec.gov reads for the as-filed front: fair-access paced, contact in the User-Agent."""

    def __init__(self, settings: Settings, *, http: httpx.Client | None = None, limiter: SecRateLimiter | None = None) -> None:
        self.user_agent = sec_user_agent(settings.sec_contact)
        self.limiter = limiter or process_rate_limiter(settings.sec_max_requests_per_second)
        self.data_base_url = settings.sec_data_base_url.rstrip("/")
        self.archives_base_url = settings.sec_archives_base_url.rstrip("/")
        self.http = http or httpx.Client(timeout=httpx.Timeout(30.0), follow_redirects=True)
        self.requests = 0

    def _get(self, url: str) -> httpx.Response:
        if not is_sec_host(httpx.URL(url).host):
            raise ValueError(f"the as-filed client only calls the SEC, not {url}")
        self.limiter.acquire()
        self.requests += 1
        response = self.http.get(url, headers={"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"})
        if response.status_code in (403, 429):
            raise SecThrottled(f"SEC refused {httpx.URL(url).path} with HTTP {response.status_code}")
        return response

    def _json(self, url: str, *, missing_ok: bool = False) -> dict[str, Any]:
        response = self._get(url)
        if missing_ok and response.status_code == 404:
            return {}
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def company_tickers(self) -> dict[str, str]:
        """TICKER → 10-digit CIK, from the SEC's own ticker file."""
        payload = self._json(f"{self.archives_base_url}/files/company_tickers.json")
        output: dict[str, str] = {}
        for item in payload.values():
            if not isinstance(item, Mapping) or not item.get("ticker") or item.get("cik_str") in (None, ""):
                continue
            output.setdefault(str(item["ticker"]).strip().upper(), str(item["cik_str"]).zfill(10))
        return output

    def submissions(self, cik: str) -> dict[str, Any]:
        return self._json(f"{self.data_base_url}/submissions/CIK{str(cik).zfill(10)}.json")

    def companyfacts(self, cik: str) -> dict[str, Any]:
        """``{}`` when the issuer has no XBRL facts (404)."""
        return self._json(f"{self.data_base_url}/api/xbrl/companyfacts/CIK{str(cik).zfill(10)}.json", missing_ok=True)

    def filing_header(self, cik: str, accession: str) -> dict[str, Any]:
        folder = f"{int(str(cik))}/{accession.replace('-', '')}"
        response = self._get(f"{self.archives_base_url}/Archives/edgar/data/{folder}/{accession}-index-headers.html")
        response.raise_for_status()
        header = parse_filing_header(response.text)
        if header.get("accession") and header["accession"] != accession:
            raise SecHeaderError(f"header of {accession} names accession {header['accession']}")
        return header


# -- the poll ----------------------------------------------------------------------------------------------------------

@dataclass
class AsFiledPollResult:
    issuers: int = 0
    unmapped_symbols: int = 0
    submissions_read: int = 0
    filings_registered: int = 0
    trigger_filings: int = 0
    header_failures: int = 0
    json_clock_mismatches: int = 0
    issuers_ingested: int = 0
    issuers_backfilled: int = 0
    deferred_retries: int = 0
    gap_ingestions: int = 0
    vintages_written: int = 0
    first_publications: int = 0
    out_of_order: int = 0
    deferred_documents: int = 0
    throttled: bool = False
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {key: (list(value) if isinstance(value, list) else value) for key, value in self.__dict__.items()}


class SecXbrlIngestor:
    """Registers accepted filings (header clock) and ingests companyfacts into statement vintages for one issuer at a
    time. Holds per-process retry state for documents whose facts are not in companyfacts yet and for issuers whose
    documents were deferred behind a failed header; what a restart loses is found again from the store (the newest
    original 10-Q/10-K without a stored fact, see ``_statement_gap``)."""

    def __init__(self, database: Database, client: SecXbrlClient, *, backfill_per_poll: int = 10) -> None:
        self.database = database
        self.client = client
        self.store = StatementVintageStore(database)
        self.backfill_per_poll = backfill_per_poll
        self._retry_after: dict[str, datetime] = {}  # doc_id → not before (facts pending in companyfacts, or deferred)
        self._settled: set[str] = set()  # doc_ids with nothing left to store: their rows are stored, or they have no ladder fact
        self._deferred: dict[str, tuple[int, datetime]] = {}  # issuer → (failed attempts in a row, retry not before)
        self._no_statements: set[str] = set()  # issuers whose companyfacts had no ladder fact at all (backfill not retried)

    def register_filing(self, cik: str, filing: Mapping[str, Any], *, symbols: Iterable[str], result: AsFiledPollResult) -> datetime | None:
        """Read the filing header and register the document with the header's acceptance clock; ``None`` on failure
        (retried on the next poll). A corrected JSON clock that disagrees with the header is counted and logged."""
        accession = str(filing["accession"])
        try:
            header = self.client.filing_header(cik, accession)
        except (httpx.HTTPError, SecHeaderError, ValueError) as error:
            result.header_failures += 1
            logger.warning("sec_xbrl: header of %s (CIK %s) unavailable: %s", accession, cik, type(error).__name__)
            return None
        accepted = header["accepted_at"]
        json_accepted = filing.get("accepted_at_json")
        if isinstance(json_accepted, datetime) and json_accepted != accepted:
            result.json_clock_mismatches += 1
            logger.warning("sec_xbrl: %s corrected submissions clock %s disagrees with the header %s — the header wins",
                           accession, json_accepted.isoformat(), accepted.isoformat())
        filed = header.get("filed_date") or filing.get("filed_date")
        if filed is None:
            result.header_failures += 1
            return None
        self.store.register_filings([{
            "market": MARKET,
            "issuer_key": cik,
            "source": FILING_SOURCE,
            "doc_id": accession,
            "form": header.get("form") or filing.get("form"),
            "items": ",".join(filing.get("items") or ()),
            "symbols": sorted(symbols),
            "period_of_report": header.get("period_of_report") or filing.get("report_date"),
            "filed_date": filed,
            "accepted_at": accepted,
            "accepted_source": ACCEPTED_FROM_HEADER,
            "json_accepted_raw": filing.get("json_accepted_raw"),
            "header_sha256": header.get("header_sha256"),
        }])
        result.filings_registered += 1
        return accepted

    def poll(
        self,
        universe: Mapping[str, str],
        tickers: Mapping[str, str],
        *,
        now: datetime,
        has_vintages: set[str] | None = None,
    ) -> AsFiledPollResult:
        """One pass over the US valuation universe (``symbol → market``) with the SEC ticker map (``TICKER → CIK``)."""
        result = AsFiledPollResult()
        symbols_by_cik: dict[str, set[str]] = {}
        for symbol in universe:
            cik = tickers.get(symbol.upper())
            if not cik:
                result.unmapped_symbols += 1
                continue
            symbols_by_cik.setdefault(cik, set()).add(symbol.upper())
        known_issuers = set(has_vintages) if has_vintages is not None else self.store.issuers_with_vintages(MARKET)
        backfill_budget = self.backfill_per_poll
        detection_cutoff = now - timedelta(days=DETECTION_LOOKBACK_DAYS)
        for cik in sorted(symbols_by_cik):
            symbols = symbols_by_cik[cik]
            result.issuers += 1
            try:
                payload = self.client.submissions(cik)
                result.submissions_read += 1
                filings = recent_filings(payload)
                registered = {row["doc_id"] for row in self.store.filings(MARKET, source=FILING_SOURCE, issuer_key=cik)}
                new_statement = False
                for filing in filings:
                    accepted_json = filing["accepted_at_json"]
                    if not is_trigger_filing(filing["form"], filing["items"]) or accepted_json is None or accepted_json < detection_cutoff:
                        continue
                    result.trigger_filings += 1
                    if filing["accession"] in registered:
                        continue
                    if self.register_filing(cik, filing, symbols=symbols, result=result) is not None:
                        registered.add(filing["accession"])
                        new_statement = new_statement or filing["form"] in STATEMENT_FORMS
                pending = self._pending_documents(cik, now=now)
                first_ingestion = cik not in known_issuers
                deferred = self._deferred.get(cik)
                retry_deferred = deferred is not None and deferred[1] <= now
                gap = (
                    not (new_statement or pending or retry_deferred) and cik not in self._no_statements and backfill_budget > 0
                    and self._statement_gap(cik, filings, now=now, has_vintages=not first_ingestion)
                )
                if new_statement or pending or retry_deferred or gap:
                    if gap:
                        backfill_budget -= 1  # the budget paces backfills and gap repairs only: a new filing or a retry never waits
                    result.issuers_backfilled += int(first_ingestion)
                    result.deferred_retries += int(retry_deferred)
                    result.gap_ingestions += int(gap and not first_ingestion)
                    self.ingest_issuer(cik, symbols, filings=filings, now=now, result=result)
                    known_issuers.add(cik)
            except SecThrottled as error:  # fair access first: the SEC said slow down, so this pass ends here
                result.throttled = True
                result.errors.append(f"{cik}: {error}")
                logger.warning("sec_xbrl: %s — the as-filed pass stops; the next poll starts over", error)
                break
            except Exception as error:  # one issuer never stops the pass; the next poll retries it
                result.errors.append(f"{cik}: {type(error).__name__}")
                logger.warning("sec_xbrl: issuer %s failed in this poll: %s", cik, type(error).__name__)
        return result

    def _pending_documents(self, cik: str, *, now: datetime) -> list[str]:
        """Registered statement documents of the issuer, accepted in the last PENDING_FACTS_DAYS, with no stored fact yet
        and not known to be settled — the ones whose facts companyfacts may still be processing."""
        recent = [
            row for row in self.store.filings(MARKET, source=FILING_SOURCE, issuer_key=cik, accepted_since=now - timedelta(days=PENDING_FACTS_DAYS))
            if row["form"] in STATEMENT_FORMS and row["doc_id"] not in self._settled
        ]
        if not recent:
            return []
        stored = self.store.documents_with_vintages(MARKET, cik)
        return [
            row["doc_id"] for row in recent
            if row["doc_id"] not in stored and self._retry_after.get(row["doc_id"], NOT_BEFORE) <= now
        ]

    def _statement_gap(self, cik: str, filings: Iterable[Mapping[str, Any]], *, now: datetime, has_vintages: bool) -> bool:
        """The issuer's newest original 10-Q/10-K in its submissions has no stored fact, is not settled and is not
        waiting out a retry: it was never ingested (the backfill) or was left behind (documents deferred behind a failed
        header whose in-memory retry state a restart lost). Read from the store, so it survives a restart."""
        statements = [filing for filing in filings if filing["form"] in ORIGINAL_STATEMENT_FORMS and filing["accepted_at_json"] is not None]
        if not statements:
            return False
        newest = str(max(statements, key=lambda filing: (filing["accepted_at_json"], filing["accession"]))["accession"])
        if newest in self._settled or self._retry_after.get(newest, NOT_BEFORE) > now:
            return False
        if has_vintages and newest in self.store.documents_with_vintages(MARKET, cik):
            self._settled.add(newest)  # stored: never asked again in this process
            return False
        return True

    def _defer(self, cik: str, *, now: datetime) -> datetime:
        """Documents of the issuer wait behind a failed header: retry on the next poll, doubling the wait after every
        failure in a row (a header that keeps failing never turns into a companyfacts download per poll)."""
        attempts = self._deferred.get(cik, (0, now))[0] + 1
        retry_at = now + min(DEFERRED_RETRY * 2 ** min(attempts - 1, 8), DEFERRED_RETRY_MAX)
        self._deferred[cik] = (attempts, retry_at)
        return retry_at

    def ingest_issuer(
        self,
        cik: str,
        symbols: Iterable[str],
        *,
        filings: list[dict[str, Any]] | None = None,
        now: datetime,
        result: AsFiledPollResult | None = None,
    ) -> AsFiledPollResult:
        """companyfacts → vintages for one issuer. Documents are stamped in acceptance order with their header clock; the
        first document whose header cannot be read stops the issuer there (it and every later one are deferred: the
        issuer is retried on the next poll, with a growing backoff while the header keeps failing), so first publications
        are always inserted before the documents that re-report them. A document is settled only when its rows are
        stored or companyfacts holds it without any ladder fact — never merely because companyfacts holds it."""
        result = result or AsFiledPollResult()
        payload = self.client.companyfacts(cik)
        processed = companyfacts_accessions(payload)
        rows, _stats = companyfacts_vintages(payload, issuer_key=cik, since=(now - timedelta(days=VINTAGE_LOOKBACK_DAYS)).date())
        by_accession = {filing["accession"]: filing for filing in filings or ()}
        documents: list[str] = []
        for row in rows:  # rows come sorted by filed date: the documents in filing order
            if row["doc_id"] not in documents:
                documents.append(row["doc_id"])
        accepted = self.store.filing_acceptances(MARKET, documents, source=FILING_SOURCE)
        ready: list[str] = []
        for doc_id in documents:
            if doc_id not in accepted:
                form = next(row["form"] for row in rows if row["doc_id"] == doc_id)
                filed = next(row["filed_date"] for row in rows if row["doc_id"] == doc_id)
                filing = by_accession.get(doc_id) or {"accession": doc_id, "form": form, "items": [], "filed_date": filed}
                clock = self.register_filing(cik, filing, symbols=symbols, result=result)
                if clock is None:
                    break
                accepted[doc_id] = clock
            ready.append(doc_id)
        documents_set, ready_set = set(documents), set(ready)
        deferred = documents_set - ready_set
        result.deferred_documents += len(deferred)
        stamped = [{**row, "accepted_at": accepted[row["doc_id"]]} for row in rows if row["doc_id"] in ready_set]
        stamped.sort(key=lambda row: (utc_instant(row["accepted_at"]), row["doc_id"]))
        counts = self.store.insert_vintages(MARKET, cik, stamped)
        result.issuers_ingested += 1
        result.vintages_written += counts["written"]
        result.first_publications += counts["first_publications"]
        result.out_of_order += counts["out_of_order"]
        if not rows:
            self._no_statements.add(cik)
        retry_deferred_at = self._defer(cik, now=now) if deferred else None
        if not deferred:
            self._deferred.pop(cik, None)
        recently_registered = self.store.filings(
            MARKET, source=FILING_SOURCE, issuer_key=cik, accepted_since=now - timedelta(days=PENDING_FACTS_DAYS),
        )
        candidates = {  # the statement documents a later poll asks about: the recently registered ones and the submissions' own
            row["doc_id"] for row in recently_registered if row["form"] in STATEMENT_FORMS
        } | {str(filing["accession"]) for filing in filings or () if filing["form"] in STATEMENT_FORMS}
        for doc_id in candidates | ready_set:
            if doc_id in ready_set or (doc_id in processed and doc_id not in documents_set):
                self._settled.add(doc_id)  # its rows are stored now, or companyfacts holds it without a ladder fact
                self._retry_after.pop(doc_id, None)
            elif doc_id in deferred and retry_deferred_at is not None:
                self._retry_after[doc_id] = retry_deferred_at  # behind a failed header: retried with its issuer
            else:
                self._retry_after[doc_id] = now + PENDING_RETRY  # companyfacts has not processed it yet
        return result
