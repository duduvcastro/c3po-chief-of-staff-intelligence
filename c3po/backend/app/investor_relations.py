from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import re
import unicodedata
import zipfile
from datetime import date, datetime, time, timedelta, timezone
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, cast
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import httpx
from curl_cffi import requests as curl_requests

from . import valuation_env
from .config import Settings
from .cvm_fundamentals import (
    CvmPackage,
    CvmPackageScan,
    extract_cvm_official_statements,
    extract_itr_official_fundamentals,
    scan_cvm_package,
)
from .cvm_statement_vintages import CvmVintageCapture
from .database import Database
from .investor_relations_pdf import InvestorRelationsPdf
from .market_data.eodhd import EodhdClient
from .market_data.finnhub import FinnhubClient
from .market_data.http import JsonHttpClient
from .official_fundamentals import save_official_fundamentals
from .official_statements import save_official_statements
from .sec_xbrl import (
    FILING_SOURCE as SEC_FILING_SOURCE,
    NEW_YORK,
    SecContactMissing,
    SecHeaderError,
    SecThrottled,
    SecXbrlClient,
    SecXbrlIngestor,
    acceptance_from_submissions_json,
    is_sec_host,
    process_rate_limiter,
)
from .statement_vintages import StatementVintageStore
from .valuation_asfiled import us_valuation_universe
from .schemas import (
    InvestorRelationsEvent,
    InvestorRelationsResponse,
    InvestorRelationsSourceHealth,
    InvestorRelationsSyncResponse,
)


logger = logging.getLogger(__name__)

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
# Defect (e), verified 2026-10-17: the submissions JSON `acceptanceDateTime` is NOT true UTC. AAPL 0000320193-26-000018:
# header ACCEPTANCE-DATETIME 20260730163028 (New York) vs JSON 2026-07-31T00:30:28.000Z; 0000320193-26-000005: header
# 20260129163033 vs JSON 2026-01-30T02:30:33Z — the JSON is the true instant PLUS the New York UTC offset. The filing
# header (…/<accession>-index-headers.html, New York wall clock) is the source of truth; the corrected JSON reading
# (sec_xbrl.acceptance_from_submissions_json) is the fallback while a header is not (yet) read, and each event says
# which one it carries. Headers are read through sec_xbrl.SecXbrlClient (contact, fair-access limiter, parser).
SEC_ACCEPTANCE_FROM_HEADER = "filing_header"
SEC_ACCEPTANCE_FROM_SUBMISSIONS = "submissions_json_ny_corrected"
SEC_HEADER_READS_PER_SYNC = 40  # newest first; the rest keep the corrected JSON reading until a later sync reads them
# A header read that fails waits 1 h, then 2 h, 4 h … up to a day before it is tried again, so a header that never
# answers cannot keep one of the newest-first slots on every sync. 403/429 is the SEC throttling: no more header reads
# in that sync at all.
SEC_HEADER_RETRY_BASE = timedelta(hours=1)
SEC_HEADER_RETRY_MAX = timedelta(days=1)
SEC_FORMS = {"8-K", "10-Q", "10-K", "6-K", "20-F", "40-F", "8-K/A", "10-Q/A", "10-K/A", "6-K/A", "20-F/A"}
SEC_FULLTEXT_KEYWORDS = (
    "guidance", "acquisition", "merger", "restatement", "material weakness",
    "impairment", "buyback", "investigation",
)
SEC_FULLTEXT_LOOKBACK_DAYS = 14
SEC_FULLTEXT_CIK_BATCH_SIZE = 40
FINNHUB_INSIDER_LOOKBACK_DAYS = 90
FINNHUB_NEWS_LOOKBACK_DAYS = 7
FINNHUB_NEWS_KEYWORDS = (
    "guidance", "acquisition", "merger", "earnings", "upgrade", "downgrade",
    "lawsuit", "recall", "restructuring", "layoffs", "investigation", "buyback",
)
CVM_INSIDER_MOVEMENT_TYPES = {
    "Compra", "Compra à vista", "Compra à termo",
    "Venda", "Venda à vista", "Venda à termo",
}
RI_KEYWORDS = (
    "resultado", "results", "earnings", "release", "fato relevante", "material fact",
    "comunicado", "guidance", "apresentacao", "presentation", "dividendo", "dividend",
    "aquisicao", "acquisition", "fusao", "merger", "recompra", "buyback",
)
RI_URL_HINTS = ("invest", "relacoes", "investidores", "investors", "ri.", "/ri", "mzgroup", "fatos-relevantes", "resultados")
RI_BLOCKED_HOSTS = (
    "correiobraziliense.com.br", "estadao.com.br", "folha.uol.com.br", "globo.com",
    "ibri.com.br", "mzgroup.com.br", "oglobo.globo.com", "portal.mzgroup.com", "uol.com.br", "valor.com.br", "valor.globo.com",
)
RI_TRUSTED_DOCUMENT_HOSTS = ("api.mziq.com",)
RI_NAVIGATION_TITLES = {
    "central de resultados",
    "earnings center",
    "results center",
}
RI_URL_OVERRIDES = {
    "JHSF3": "https://ri.jhsf.com.br/informacoes-financeiras/central-de-resultados/",
    "PRNR3": "https://ri.priner.com.br/informacoes-aos-investidores/central-de-resultados/",
    "UNIP6": "https://ri.unipar.com/informacoes-aos-investidores/central-de-resultados/",
}
GLOBAL_RI_URL_OVERRIDES = {
    "MHVYF": "https://www.mhi.com/finance/library/result",
}


def normalize_company_name(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    folded = re.sub(r"[^A-Z0-9]+", " ", folded.upper())
    folded = re.sub(r"\b(S A|SA|INC|CORP|CORPORATION|LTD|LTDA|PLC|PFD|ON|PN)\b", " ", folded)
    return re.sub(r"\s+", " ", folded).strip()


_ASFILED_ERROR_ISSUER = re.compile(r"^(\d{10}): ")


def asfiled_failed_issuers(errors: list[str]) -> list[str]:
    """The issuers (10-digit CIKs) an as-filed pass did not observe, read from its per-issuer errors
    (``SecXbrlIngestor.poll`` writes each as ``"<cik>: <error>"``; ``sec_xbrl.py`` itself is a frozen producer file)."""
    return sorted({match.group(1) for error in errors if (match := _ASFILED_ERROR_ISSUER.match(str(error)))})


def asfiled_unparsed_errors(errors: list[str]) -> int:
    """The errors of an as-filed pass that name no issuer: a failure nobody can attribute to a name."""
    return sum(1 for error in errors if not _ASFILED_ERROR_ISSUER.match(str(error)))


class AsFiledHeaderWatch:
    """The as-filed poll's SEC client, watched: every ``filing_header`` that raises records its CIK (the frozen
    ``SecXbrlIngestor.register_filing`` only counts a header failure, without naming the issuer, and registers nothing —
    the issuer then has no 051 row and no 053 mark, so its names must not read as covered). Everything else delegates."""

    _CAUGHT = (httpx.HTTPError, SecHeaderError, ValueError)  # what register_filing swallows into header_failures

    def __init__(self, client: Any) -> None:
        self.client = client
        self.failed: set[str] = set()
        self.caught = 0

    def reset(self) -> None:
        self.failed.clear()
        self.caught = 0

    def filing_header(self, cik: str, accession: str) -> Any:
        try:
            return self.client.filing_header(cik, accession)
        except Exception as error:
            self.failed.add(str(cik))
            self.caught += int(isinstance(error, self._CAUGHT))
            raise

    def __getattr__(self, name: str) -> Any:
        return getattr(self.client, name)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def is_ri_navigation_link(title: str, document_url: str, source_url: str) -> bool:
    def normalized_url(value: str) -> tuple[str, str]:
        parsed = urlparse(value)
        return parsed.netloc.casefold(), parsed.path.rstrip("/").casefold()

    folded_title = unicodedata.normalize("NFKD", clean_text(title)).encode("ascii", "ignore").decode("ascii").casefold()
    return normalized_url(document_url) == normalized_url(source_url) or folded_title in RI_NAVIGATION_TITLES


def safe_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def date_at_midnight(value: str) -> datetime:
    return datetime.combine(date.fromisoformat(value[:10]), time.min, tzinfo=SAO_PAULO)


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href = ""
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        if normalized_tag == "a":
            self._href = next((value or "" for key, value in attrs if key.lower() == "href"), "")
            self._parts = []
            return
        if self._href and normalized_tag in {"img", "svg"}:
            labels = [
                value or ""
                for key, value in attrs
                if key.lower() in {"alt", "title", "aria-label"}
            ]
            self._parts.extend(label for label in labels if label)

    def handle_data(self, data: str) -> None:
        if self._href:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            self.links.append((self._href, clean_text(" ".join(self._parts))))
            self._href = ""
            self._parts = []


class InvestorRelationsService:
    def __init__(self, settings: Settings, database: Database, *, read_sec_headers: bool = False) -> None:
        self.settings = settings
        self.database = database
        self.pdf = InvestorRelationsPdf(settings.investor_relations_output_dir)
        self.client = httpx.Client(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            headers={"User-Agent": settings.sec_user_agent, "Accept-Encoding": "gzip, deflate"},
            event_hooks={"request": [self._sec_fair_access]},
        )
        # Defect (e) and the as-filed front: only the process that passes read_sec_headers=True (the IR worker, a single
        # container) requests filing headers — the sync_sec header step and the as-filed poll, both through one
        # sec_client; every other process (API, valuation and R2D2 workers) reuses the header instants already stored
        # and never calls the SEC for them.
        self.read_sec_headers = read_sec_headers
        self.sec_client: SecXbrlClient | None = None  # built on the first header read (refuses without C3PO_SEC_CONTACT)
        self._sec_header_failures: dict[str, tuple[int, datetime]] = {}  # accession -> (failed reads, next attempt)
        self._sec_contact_warned = False
        self._asfiled_ingestor: SecXbrlIngestor | None = None
        self.finnhub = FinnhubClient(settings.finnhub_base_url, settings.finnhub_api_token, self.client)
        self.eodhd = EodhdClient(
            settings.eodhd_base_url, settings.eodhd_api_token,
            JsonHttpClient(timeout=30.0, max_retries=2, client=self.client),
        )

    def _sec_fair_access(self, request: httpx.Request) -> None:
        """Every SEC request of this client waits on the process-wide fair-access limiter shared with the as-filed
        client (sec_xbrl.process_rate_limiter): one pace per process, whatever path calls EDGAR."""
        if is_sec_host(request.url.host):
            process_rate_limiter(valuation_env.sec_max_requests_per_second()).acquire()

    def _sec_header_client(self) -> SecXbrlClient:
        """The process's one SEC filing-header client (contact in the User-Agent, paced by the process limiter, the
        header parser of app/sec_xbrl.py), shared by the sync_sec header step and the as-filed poll. Raises
        ``SecContactMissing`` without C3PO_SEC_CONTACT: the SEC is never called without a contact."""
        if self.sec_client is None:
            self.sec_client = SecXbrlClient(self.settings)
        return self.sec_client

    def register_b3_universe(self, catalog: list[dict[str, Any]]) -> None:
        companies = []
        for item in catalog:
            symbol = str(item.get("symbol") or "").upper()
            company_name = clean_text(str(item.get("name") or item.get("longName") or symbol))
            if not symbol or re.search(r"[0-9]F$", symbol) or not company_name:
                continue
            companies.append({
                "market": "B3",
                "symbol": symbol,
                "company_name": company_name,
                "name_key": normalize_company_name(company_name),
                "exchange": "B3",
            })
        self.database.register_ir_securities(companies)

    def add_watch(self, symbol: str, market: str, company_name: str = "", ri_url: str | None = None) -> None:
        clean_symbol = symbol.strip().upper().removesuffix(".SA")
        name = clean_text(company_name) or clean_symbol
        self.database.register_ir_securities([{
            "market": market,
            "symbol": clean_symbol,
            "company_name": name,
            "name_key": normalize_company_name(name),
            "exchange": "B3" if market == "B3" else None,
            "ri_url": ri_url,
        }])

    def feed(
        self,
        *,
        limit: int = 100,
        market: str | None = None,
        source: str | None = None,
        event_type: str | None = None,
        query: str | None = None,
        monitored_only: bool = True,
    ) -> InvestorRelationsResponse:
        rows = self.database.list_ir_events(
            limit=limit,
            market=market,
            source=source,
            event_type=event_type,
            query=query,
            monitored_only=monitored_only,
        )
        stats = self.database.ir_overview_stats(monitored_only=monitored_only)
        items = [self._event_model(row) for row in rows]
        return InvestorRelationsResponse(
            generated_at=datetime.now().astimezone(),
            items=items,
            sources=self._source_health(),
            methodology={
                "official_first": "CVM Dados Abertos and SEC EDGAR are authoritative; RI pages are issuer-controlled secondary confirmation.",
                "freshness_gate": "A valuation-relevant filing newer than the model evidence changes the security to Pending Review.",
                "results_rule": "ITR/DFP/10-Q/10-K results are automatically incorporated only when the valuation fundamentals cover the same or a later reporting period.",
                "qualitative_rule": "Material facts, 8-K/6-K and issuer releases remain pending until reviewed; text alone never changes a target price automatically.",
            },
            **stats,
        )

    def sync(self, source: str = "all") -> InvestorRelationsSyncResponse:
        selected = ("cvm", "sec", "ri", "finnhub") if source == "all" else (source,)
        read = 0
        written = 0
        states: dict[str, str] = {}
        for code in selected:
            try:
                if code == "cvm":
                    source_read, source_written = self.sync_cvm()
                elif code == "cvm_statements":
                    source_read, source_written = self.sync_cvm_statements()
                elif code == "sec":
                    source_read, source_written = self.sync_sec()
                elif code == "ri":
                    source_read, source_written = self.sync_ri()
                elif code == "finnhub":
                    source_read, source_written = self.sync_finnhub_news()
                elif code == "sec_asfiled":
                    source_read, source_written = self.sync_sec_asfiled()
                else:
                    raise ValueError(f"Unsupported Investor Relations source: {code}")
                read += source_read
                written += source_written
                states[code] = f"ok · {source_written} records"
            except Exception as exc:
                states[code] = f"error · {exc}"
        return InvestorRelationsSyncResponse(
            generated_at=datetime.now().astimezone(),
            records_read=read,
            records_written=written,
            sources=states,
        )

    def sync_cvm(self) -> tuple[int, int]:
        run_id = self.database.begin_ingestion_run("cvm", "CVM Dados Abertos", "regulatory_disclosure", {"operation": "ipe"})
        try:
            year = datetime.now(SAO_PAULO).year
            cutoff = datetime.now(SAO_PAULO).date() - timedelta(days=180)
            rows, ipe_available = self._cvm_ipe_rows(year, cutoff)
            itr_rows, itr_payload, itr_url = self._cvm_structured_package("itr", year, cutoff)
            dfp_rows, _, _ = self._cvm_structured_package("dfp", year - 1, cutoff)
            self._register_brapi_b3_universe()

            companies: dict[str, dict[str, Any]] = {}
            for row in rows:
                company_name = clean_text(row.get("Nome_Companhia", ""))
                key = normalize_company_name(company_name)
                if key and key not in companies:
                    companies[key] = {
                        "market": "B3",
                        "company_name": company_name,
                        "name_key": key,
                        "regulator_id": clean_text(row.get("Codigo_CVM", "")),
                        "tax_id": clean_text(row.get("CNPJ_Companhia", "")),
                        "exchange": "B3",
                    }
            for row in [*itr_rows, *dfp_rows]:
                company_name = clean_text(row.get("DENOM_CIA", ""))
                key = normalize_company_name(company_name)
                if key and key not in companies:
                    companies[key] = {
                        "market": "B3",
                        "company_name": company_name,
                        "name_key": key,
                        "regulator_id": clean_text(row.get("CD_CVM", "")),
                        "tax_id": clean_text(row.get("CNPJ_CIA", "")),
                        "exchange": "B3",
                    }
            self.database.register_ir_securities(list(companies.values()))
            company_index = {item["name_key"]: item for item in self.database.list_ir_companies("B3")}
            self._enrich_cvm_security_bridges([*itr_rows, *dfp_rows], company_index)
            company_index = {item["name_key"]: item for item in self.database.list_ir_companies("B3")}
            ri_channels_read = self._register_cvm_ri_channels(year, company_index)
            self._register_ri_overrides()
            company_index = {item["name_key"]: item for item in self.database.list_ir_companies("B3")}

            cvm_issuers = self._cvm_overlay_issuers(itr_rows, company_index)
            overlays = extract_itr_official_fundamentals(
                itr_payload,
                year=year,
                issuers=cvm_issuers,
                source_url=itr_url,
            )
            save_official_fundamentals(self.database, overlays)

            collected_at = datetime.now().astimezone()
            events = [self._cvm_event(row, company_index, collected_at) for row in rows]
            events.extend(self._cvm_structured_event(row, company_index, collected_at) for row in [*itr_rows, *dfp_rows])
            events = [event for event in events if event]
            company_by_tax_id = {item["tax_id"]: item for item in company_index.values() if item.get("tax_id")}
            insider_rows = self._cvm_insider_transactions(year, cutoff)
            insider_events = self._cvm_insider_events(insider_rows, company_by_tax_id)
            events.extend(insider_events)
            written = self.database.save_ir_events(events)
            records_read = len(rows) + len(itr_rows) + len(dfp_rows) + ri_channels_read + len(insider_rows)
            warning = None if ipe_available else (
                f"CVM IPE {year} package unavailable (HTTP 404); "
                "continued with current structured CVM sources."
            )
            self.database.finish_ingestion_run(run_id, "succeeded", records_read, written, warning)
            return records_read, written
        except Exception as exc:
            self.database.finish_ingestion_run(run_id, "failed", 0, 0, str(exc))
            raise

    def sync_cvm_statements(self) -> tuple[int, int]:
        """Complete CVM statements of every mapped B3 issuer -- ITR of this and last year, DFP of the two previous
        years: income, D&A (DVA), cash flow, balance and capital, individual only when no consolidated exists --
        saved under their own analysis type (served only through the field-by-field overlay switch), and the
        as-filed vintages of each document. The open-data dumps keep only the latest version of a document, so a
        re-filed original survives only in statement_vintages (a no-op until migration 051 and its store land).
        Packages go oldest first, so the store sees each issuer's filings in acceptance order."""
        run_id = self.database.begin_ingestion_run(
            "cvm_statements",
            "CVM Dados Abertos - demonstrações completas",
            "regulatory_disclosure",
            {"operation": "itr_dfp_statements"},
        )
        try:
            year = datetime.now(SAO_PAULO).year
            companies = self.database.list_ir_companies("B3")
            company_index = {item["name_key"]: item for item in companies}
            company_by_tax_id = {item["tax_id"]: item for item in companies if item.get("tax_id") and item.get("symbols")}
            vintages = CvmVintageCapture.open(self.database)
            scans: list[CvmPackageScan] = []
            issuers: dict[str, dict[str, Any]] = {}
            matches: dict[str, dict[str, Any] | None] = {}  # one name match per CNPJ across the four packages
            records_read = 0
            for document_type, package_year in (("dfp", year - 2), ("itr", year - 1), ("dfp", year - 1), ("itr", year)):
                index_rows, payload, url = self._cvm_structured_package(document_type, package_year, date.min)
                if not payload:
                    continue
                package_issuers = self._cvm_statement_issuers(index_rows, company_index, company_by_tax_id, matches)
                for tax_id, issuer in package_issuers.items():
                    issuers.setdefault(tax_id, issuer)
                records_read += len(index_rows)
                scans.append(scan_cvm_package(
                    CvmPackage(document_type, package_year, payload, url),
                    package_issuers,
                    vintage_sink=vintages.write if vintages.enabled else None,
                ))
                vintages.finish_package()
            overlays = extract_cvm_official_statements(scans, issuers=issuers)
            written = save_official_statements(self.database, overlays)
            warning = vintages.summary()
            if vintages.degraded:  # the store refused writes: a partial run and an error event, not a quiet summary
                logger.error("CVM statements run %s: %s", run_id, warning)
            self.database.finish_ingestion_run(
                run_id, "partial" if vintages.degraded else "succeeded", records_read, written, warning
            )
            return records_read, written
        except Exception as exc:
            self.database.finish_ingestion_run(run_id, "failed", 0, 0, str(exc))
            raise

    def _cvm_statement_issuers(
        self,
        rows: list[dict[str, str]],
        company_index: dict[str, dict[str, Any]],
        company_by_tax_id: dict[str, dict[str, Any]],
        matches: dict[str, dict[str, Any] | None] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Issuers of a package mapped to listed symbols: by CNPJ first, by name only when the matched company does
        not carry a different CNPJ (a holding and its operating subsidiary often share most of a name)."""
        matches = {} if matches is None else matches
        issuers: dict[str, dict[str, Any]] = {}
        for row in rows:
            tax_id = clean_text(row.get("CNPJ_CIA", ""))
            if not tax_id or tax_id in issuers:
                continue
            company_name = clean_text(row.get("DENOM_CIA", ""))
            if tax_id not in matches:
                company = company_by_tax_id.get(tax_id) or self._match_company(company_name, company_index)
                if not company or not company.get("symbols") or (company.get("tax_id") and company["tax_id"] != tax_id):
                    company = None
                matches[tax_id] = company
            company = matches[tax_id]
            if company is None:
                continue
            issuers[tax_id] = {
                "symbols": company["symbols"],
                "company_name": company_name or company.get("company_name"),
                "regulator_id": clean_text(row.get("CD_CVM", "")) or company.get("regulator_id"),
            }
        return issuers

    def _cvm_insider_transactions(self, year: int, cutoff: date) -> list[dict[str, str]]:
        """Row-level insider buy/sell disclosures -- art. 11 of CVM
        Resolution 44, the direct B3 equivalent of SEC Form 4, and the
        thing that actually answers "does CVM have something like
        Finnhub's insider data" (2026-08-19). Verified live against the
        real dataset: unlike ITR/DFP, the "con" (detail) file already
        carries CNPJ/company name on every row, so this needs no separate
        lookup file the way _cvm_structured_package's callers do.
        """
        url = f"{self.settings.cvm_data_base_url.rstrip('/')}/CIA_ABERTA/DOC/VLMO/DADOS/vlmo_cia_aberta_con_{year}.zip"
        response = self.client.get(url)
        if response.status_code == 404:
            return []
        response.raise_for_status()
        expected = f"vlmo_cia_aberta_con_{year}.csv"
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            filename = next((name for name in archive.namelist() if name.lower() == expected.lower()), None)
            if not filename:
                return []
            text = archive.read(filename).decode("latin-1")
        rows = list(csv.DictReader(io.StringIO(text), delimiter=";"))
        return [
            row for row in rows
            # "Companhia" means the disclosed securities are the reporting
            # company's own shares -- "Controlada"/"Controladora" rows are
            # the insider trading a *related* entity's shares, not this one.
            if row.get("Tipo_Empresa") == "Companhia"
            and row.get("Tipo_Movimentacao") in CVM_INSIDER_MOVEMENT_TYPES
            and (safe_date(row.get("Data_Movimentacao")) or date.min) >= cutoff
        ]

    def _cvm_insider_events(
        self, rows: list[dict[str, str]], company_by_tax_id: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        events = []
        for row in rows:
            tax_id = clean_text(row.get("CNPJ_Companhia", ""))
            company = company_by_tax_id.get(tax_id)
            symbols = company.get("symbols") if company else None
            symbol = symbols[0] if symbols else None
            if not company or not symbol:
                continue
            transaction_date = safe_date(row.get("Data_Movimentacao"))
            if not transaction_date:
                continue
            try:
                quantity = float(row.get("Quantidade") or 0)
            except (TypeError, ValueError):
                quantity = 0.0
            if quantity <= 0:
                continue
            try:
                price = float(row.get("Preco_Unitario") or 0) or None
            except (TypeError, ValueError):
                price = None
            movement = clean_text(row.get("Tipo_Movimentacao", ""))
            action = "compra" if movement.startswith("Compra") else "venda"
            role = clean_text(row.get("Tipo_Cargo", "")) or "Pessoa ligada"
            asset_class = clean_text(row.get("Caracteristica_Valor_Mobiliario", ""))
            key_material = "|".join((
                tax_id, transaction_date.isoformat(), role, movement,
                f"{quantity:.0f}", f"{price or 0:.4f}", asset_class,
            ))
            external_id = f"cvm-insider-{hashlib.sha1(key_material.encode('utf-8')).hexdigest()[:16]}"
            price_note = f" a R$ {price:.2f}/ação" if price else ""
            events.append({
                "source_code": "cvm",
                "external_id": external_id,
                "company_id": company.get("id"),
                "market": "B3",
                "symbol": symbol,
                "company_name": company.get("company_name") or clean_text(row.get("Nome_Companhia", "")),
                "regulator_id": company.get("regulator_id"),
                "event_type": "Insider Transaction",
                "form": "Art. 11 ICVM 44 (VLMO)",
                "title": f"{role}: {action} de {quantity:,.0f} ações".replace(",", "."),
                "summary": (
                    f"{role} realizou {action} de {quantity:,.0f} ações ({asset_class}){price_note} "
                    f"em {transaction_date.isoformat()}."
                ).replace(",", "."),
                "published_at": datetime.combine(transaction_date, time.min, tzinfo=SAO_PAULO),
                "published_time_precision": "date",
                "reference_date": transaction_date,
                "official_url": "https://dados.cvm.gov.br/dataset/cia_aberta-doc-vlmo",
                "document_url": None,
                "materiality": "low",
                "valuation_relevant": False,
                "valuation_status": "informational",
                "raw_metadata": {
                    "source": "cvm_vlmo", "role": role, "movement": movement,
                    "quantity": quantity, "price": price, "asset_class": asset_class,
                },
                "collected_at": datetime.now().astimezone(),
            })
        return events

    def sync_sec(self) -> tuple[int, int]:
        run_id = self.database.begin_ingestion_run("sec", "SEC EDGAR", "regulatory_disclosure", {"operation": "submissions"})
        try:
            existing = {item["symbol"]: item for item in self.database.ir_watch_symbols() if item["market"] == "US"}
            for symbol in self.settings.sec_watchlist:
                if symbol not in existing:
                    self.add_watch(symbol, "US")
            watched = {item["symbol"]: item for item in self.database.ir_watch_symbols() if item["market"] == "US"}

            tickers_response = self.client.get(f"{self.settings.sec_archives_base_url.rstrip('/')}/files/company_tickers.json")
            tickers_response.raise_for_status()
            ticker_rows = tickers_response.json().values()
            ticker_map = {str(item.get("ticker", "")).upper(): item for item in ticker_rows}
            read = 0
            events: list[dict[str, Any]] = []
            cutoff = datetime.now(timezone.utc) - timedelta(days=365)
            for symbol in sorted(watched):
                meta = ticker_map.get(symbol)
                if not meta:
                    continue
                cik = str(meta["cik_str"]).zfill(10)
                company_name = clean_text(str(meta.get("title") or watched[symbol].get("company_name") or symbol))
                self.database.register_ir_securities([{
                    "market": "US", "symbol": symbol, "company_name": company_name,
                    "name_key": normalize_company_name(company_name), "regulator_id": cik,
                    "exchange": watched[symbol].get("exchange"), "ri_url": watched[symbol].get("ri_url"),
                }])
                submission_response = self.client.get(f"{self.settings.sec_data_base_url.rstrip('/')}/submissions/CIK{cik}.json")
                submission_response.raise_for_status()
                payload = submission_response.json()
                investor_website = clean_text(str(payload.get("investorWebsite") or payload.get("website") or "")) or None
                self.database.register_ir_securities([{
                    "market": "US", "symbol": symbol, "company_name": company_name,
                    "name_key": normalize_company_name(company_name), "regulator_id": cik,
                    "exchange": watched[symbol].get("exchange"), "ri_url": investor_website or watched[symbol].get("ri_url"),
                }])
                recent = payload.get("filings", {}).get("recent", {})
                company = self._company_for_symbol("US", symbol)
                forms = recent.get("form", [])
                read += len(forms)
                for index, form in enumerate(forms):
                    if form not in SEC_FORMS:
                        continue
                    event = self._sec_event(payload, recent, index, company, cutoff)
                    if event:
                        events.append(event)
                finnhub_insider_events = self._finnhub_insider_events(symbol, cik, company, company_name)
                events.extend(finnhub_insider_events or self._eodhd_insider_events(symbol, cik, company, company_name))
            self._apply_sec_header_acceptances(events)
            self._enrich_with_sec_fulltext(events)
            # filing events (they carry an acceptance clock) go through the write that keeps a stored filing-header
            # instant atomically (another process may store it after this sync's read); the insider events R2D2 reads
            # keep save_ir_events, unchanged
            filings = [event for event in events if (event.get("raw_metadata") or {}).get("acceptance_time_source")]
            others = [event for event in events if not (event.get("raw_metadata") or {}).get("acceptance_time_source")]
            written = self.database.save_ir_events(others) + self.database.save_sec_filing_events(
                filings, header_source=SEC_ACCEPTANCE_FROM_HEADER,
            )
            self.database.finish_ingestion_run(run_id, "succeeded", read, written)
            return read, written
        except Exception as exc:
            self.database.finish_ingestion_run(run_id, "failed", 0, 0, str(exc))
            raise

    def _apply_sec_header_acceptances(self, events: list[dict[str, Any]]) -> None:
        """Defect (e): give each SEC filing event its EDGAR acceptance instant from the filing header — the source of
        truth. A header instant already known is reused without calling the SEC: one this sync stored on an earlier run
        (``Database.stored_sec_acceptances``), else one the as-filed poll registered (``statement_filings``, migration
        051) — never read twice, never downgraded to the JSON reading. The others are read newest first, at most
        ``SEC_HEADER_READS_PER_SYNC`` per sync, through the process's one SEC header client (``_sec_header_client``:
        fair-access limiter, contact in the User-Agent), only in the process built with ``read_sec_headers=True`` and
        only with ``C3PO_SEC_CONTACT`` configured (the SEC is never called without a contact). An event whose header is
        not read keeps the corrected submissions-JSON instant and says so in ``raw_metadata``. Insider events (also
        ``source_code = "sec"``) carry no acceptance reading and are left alone.
        Best-effort, like the full-text enrichment: any failure here (the stored-instant lookup included) leaves the
        events with the corrected submissions-JSON instant and never fails sync_sec, whose Finnhub/EODHD insider events
        R2D2's risk source reads (RC-4)."""
        try:
            self._read_sec_header_acceptances(events)
        except Exception as exc:
            logger.warning("SEC filing-header acceptance step skipped (%s); the events keep the corrected "
                           "submissions-JSON time", type(exc).__name__)

    def _read_sec_header_acceptances(self, events: list[dict[str, Any]]) -> None:
        filings = [
            event for event in events
            if (event.get("raw_metadata") or {}).get("acceptance_time_source") == SEC_ACCEPTANCE_FROM_SUBMISSIONS
        ]
        if not filings:
            return
        accessions = [str(event["external_id"]) for event in filings]
        stored = self.database.stored_sec_acceptances(accessions, acceptance_source=SEC_ACCEPTANCE_FROM_HEADER)
        registered = self._registered_sec_acceptances([accession for accession in accessions if accession not in stored])
        pending: list[dict[str, Any]] = []
        for event in filings:
            accepted = stored.get(str(event["external_id"])) or registered.get(str(event["external_id"]))
            if accepted is not None:
                self._set_sec_header_acceptance(event, accepted)
            else:
                pending.append(event)
        if not pending or not self.read_sec_headers:
            return
        try:
            reader = self._sec_header_client()
        except SecContactMissing:
            if not self._sec_contact_warned:  # once per process: the IR worker syncs every 15 minutes
                self._sec_contact_warned = True
                logger.warning(
                    "C3PO_SEC_CONTACT is not configured: %d SEC filing(s) keep the corrected submissions-JSON "
                    "acceptance time; their filing headers are not read without an SEC contact.", len(pending),
                )
            return
        now = datetime.now(timezone.utc)
        due = [
            event for event in pending
            if event["external_id"] not in self._sec_header_failures
            or self._sec_header_failures[event["external_id"]][1] <= now
        ]
        semantics_warned = False
        for event in sorted(due, key=lambda item: item["published_at"], reverse=True)[:SEC_HEADER_READS_PER_SYNC]:
            accession = str(event["external_id"])
            try:
                accepted = reader.filing_header(str(event.get("regulator_id") or ""), accession)["accepted_at"]
            except SecThrottled as exc:
                logger.warning("SEC answered %d to filing header %s: no more header reads in this sync",
                               exc.status_code, accession)
                return
            except httpx.HTTPStatusError as exc:
                self._defer_sec_header(accession, now, f"HTTP {exc.response.status_code}")
                continue
            except Exception as exc:  # network, no ACCEPTANCE-DATETIME (SecHeaderError), a header naming another accession
                self._defer_sec_header(accession, now, type(exc).__name__)
                continue
            self._sec_header_failures.pop(accession, None)
            if accepted != event["published_at"] and not semantics_warned:
                semantics_warned = True
                logger.warning(
                    "SEC filing header %s says %s but the corrected submissions JSON says %s — the JSON semantics "
                    "verified on 2026-10-17 no longer hold; events without a header read may be off.",
                    event["external_id"], accepted.isoformat(), event["published_at"].isoformat(),
                )
            self._set_sec_header_acceptance(event, accepted)

    def _registered_sec_acceptances(self, accessions: list[str]) -> dict[str, datetime]:
        """Header instants the as-filed poll already registered (``statement_filings``; filled only behind
        C3PO_VALUATION_ASFILED_ENABLED, every row read from a filing header). Best-effort on its own: a failed lookup
        only means these filings are read (or keep the corrected JSON time) like the others."""
        if not accessions:
            return {}
        try:
            return StatementVintageStore(self.database).filing_acceptances("US", accessions, source=SEC_FILING_SOURCE)
        except Exception as exc:
            logger.warning("As-filed filing registry not read (%s); its header instants are not reused in this sync",
                           type(exc).__name__)
            return {}

    def _defer_sec_header(self, accession: str, now: datetime, reason: str) -> None:
        """A failed header read waits ``SEC_HEADER_RETRY_BASE`` doubled per consecutive failure (at most
        ``SEC_HEADER_RETRY_MAX``); kept in memory, so a worker restart simply tries it again."""
        failures = self._sec_header_failures.get(accession, (0, now))[0] + 1
        delay = min(SEC_HEADER_RETRY_BASE * (2 ** min(failures - 1, 10)), SEC_HEADER_RETRY_MAX)  # bounded exponent
        self._sec_header_failures[accession] = (failures, now + delay)
        logger.info("SEC filing header %s not read (%s, failure %d); it keeps the corrected submissions-JSON time and "
                    "is retried after %s", accession, reason, failures, delay)

    @staticmethod
    def _set_sec_header_acceptance(event: dict[str, Any], accepted: datetime) -> None:
        event["published_at"] = accepted
        metadata = event.setdefault("raw_metadata", {})
        metadata["acceptance_time_source"] = SEC_ACCEPTANCE_FROM_HEADER
        metadata["acceptance_datetime_header"] = accepted.astimezone(NEW_YORK).strftime("%Y%m%d%H%M%S")

    def sync_sec_asfiled(self) -> tuple[int, int]:
        """Valuation as-filed (owner 2026-10-17): the SEC polling extended to the US valuation universe. Every newly
        accepted 10-Q/10-K (and amendments) and 8-K carrying item 2.02 is registered with its filing header's acceptance
        clock, and the issuer's companyfacts are ingested into statement vintages (app/sec_xbrl.py). Off unless
        C3PO_VALUATION_ASFILED_ENABLED, and only in the header-reading process (``read_sec_headers=True``, the Investor
        Relations worker; anywhere else it does nothing); refuses to call the SEC without C3PO_SEC_CONTACT (the run
        fails, naming it). Not part of sync("all"): only the Investor Relations worker polls it, so one process carries
        the heavy pass."""
        if not valuation_env.asfiled_enabled() or not self.read_sec_headers:
            return 0, 0
        run_id = self.database.begin_ingestion_run(
            "sec_asfiled", "SEC EDGAR as-filed statements", "regulatory_disclosure", {"operation": "valuation_universe"},
        )
        try:
            if self._asfiled_ingestor is None:  # kept across polls: it holds the retry state of pending documents
                self._asfiled_ingestor = SecXbrlIngestor(
                    self.database,
                    self._sec_header_client(),
                    backfill_per_poll=valuation_env.asfiled_backfill_issuers_per_poll(),
                )
            ingestor = self._asfiled_ingestor
            if not isinstance(ingestor.client, AsFiledHeaderWatch):
                ingestor.client = AsFiledHeaderWatch(ingestor.client)  # type: ignore[assignment]
            watch = cast(AsFiledHeaderWatch, ingestor.client)
            watch.reset()
            universe = us_valuation_universe(self.database)
            tickers = watch.company_tickers()
            result = ingestor.poll(universe, tickers, now=datetime.now(timezone.utc))
            written = result.filings_registered + result.vintages_written
            warning = None
            if result.errors or result.header_failures or result.json_clock_mismatches:
                warning = (
                    f"{'SEC throttled the pass; ' if result.throttled else ''}"
                    f"{len(result.errors)} issuer errors, {result.header_failures} header failures, "
                    f"{result.json_clock_mismatches} JSON/header clock mismatches: {'; '.join(result.errors[:10])}"
                )
            # the issuers this pass did not observe (CIKs, aggregate; no symbol): the Decisor V1 never counts the poll as
            # covering their names (valuation_decision.name_staleness)
            # unattributed: header failures no watched exception explains (a header read without a filed date) and errors that
            # name no issuer — the decisor then counts the pass as covering no US name at all
            unattributed = max(0, result.header_failures - watch.caught) + asfiled_unparsed_errors(result.errors)
            failed = {*asfiled_failed_issuers(result.errors), *watch.failed}
            # the issuers this pass DID observe (CIKs only): the decisor covers a name only when its issuer is here
            observed = sorted({tickers[symbol.upper()] for symbol in universe if tickers.get(symbol.upper())} - failed)
            self.database.update_ingestion_run_metadata(run_id, {
                "issuers": result.issuers, "failed_issuers": sorted(failed), "observed_issuers": observed,
                "unattributed_failures": unattributed, "header_failures": result.header_failures, "unmapped_symbols": result.unmapped_symbols})
            # a pass the SEC throttled is 'partial' (migration 001 admits it): it did not look at the whole universe, so the
            # Decisor V1 never counts it as the as-filed poll being alive (valuation_decision.name_staleness)
            self.database.finish_ingestion_run(run_id, "partial" if result.throttled else "succeeded", result.submissions_read, written, warning)
            return result.submissions_read, written
        except Exception as exc:
            self.database.finish_ingestion_run(run_id, "failed", 0, 0, str(exc))
            raise

    def _enrich_with_sec_fulltext(self, events: list[dict[str, Any]]) -> None:
        """Cross-reference recently-discovered SEC filings against EDGAR's full-
        text search (https://efts.sec.gov) for high-signal keywords, so a
        generic "Material Filing" title can say what it's actually about --
        submissions already tell us a filing exists, full-text search is the
        only way to know what it's about without downloading and parsing the
        document itself. Scoped to the last SEC_FULLTEXT_LOOKBACK_DAYS only
        (older events aren't worth the extra requests every poll cycle).
        Best-effort: any failure here must never break the submissions-based
        sync it enriches, so events ship unenriched instead of not shipping.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=SEC_FULLTEXT_LOOKBACK_DAYS)
        recent = [event for event in events if event["published_at"] >= cutoff]
        if not recent:
            return
        # EDGAR full-text search matches CIKs by exact stored form (zero-padded to
        # 10 digits) -- an unpadded CIK doesn't error, it just silently matches
        # nothing, confirmed against the live API (2026-08-19), so this is not
        # a defensive no-op.
        ciks = sorted({
            event["regulator_id"].zfill(10) for event in recent if event.get("regulator_id")
        })
        try:
            matches = self._sec_fulltext_matches(ciks, cutoff.date())
        except Exception:
            return
        if not matches:
            return
        for event in recent:
            keywords = matches.get(event["external_id"])
            if not keywords:
                continue
            event["summary"] = f"{event['summary']} | Menções: {', '.join(keywords)}"
            event.setdefault("raw_metadata", {})["fulltext_keywords"] = keywords

    def _sec_fulltext_matches(self, ciks: list[str], since: date) -> dict[str, list[str]]:
        """{accession_no: [matched keyword, ...]} for SEC_FULLTEXT_KEYWORDS found
        in filings by the given CIKs since ``since``, via EDGAR's official full-
        text search API (efts.sec.gov/LATEST/search-index -- free, no API key,
        requires only the same User-Agent header already set on self.client).
        """
        if not ciks:
            return {}
        matches: dict[str, list[str]] = {}
        forms_param = ",".join(sorted(SEC_FORMS))
        start = since.isoformat()
        end = datetime.now(timezone.utc).date().isoformat()
        for batch_start in range(0, len(ciks), SEC_FULLTEXT_CIK_BATCH_SIZE):
            ciks_param = ",".join(ciks[batch_start:batch_start + SEC_FULLTEXT_CIK_BATCH_SIZE])
            for keyword in SEC_FULLTEXT_KEYWORDS:
                response = self.client.get(
                    f"{self.settings.sec_fulltext_base_url.rstrip('/')}/LATEST/search-index",
                    params={
                        "q": f'"{keyword}"', "forms": forms_param, "dateRange": "custom",
                        "startdt": start, "enddt": end, "ciks": ciks_param,
                    },
                )
                response.raise_for_status()
                for hit in response.json().get("hits", {}).get("hits", []):
                    accession = str(hit.get("_id", "")).split(":")[0]
                    if accession:
                        matches.setdefault(accession, []).append(keyword)
        return matches

    def _finnhub_insider_events(
        self, symbol: str, cik: str, company: dict[str, Any] | None, company_name: str,
    ) -> list[dict[str, Any]]:
        """Recent insider buy/sell activity (Finnhub Fundamental-1 plan, US
        market only) as its own ir_events, source_code still "sec" -- this is
        SEC Form 3/4/5-derived data, and keeping the existing source enum
        avoids touching the Literal["cvm","sec","ri"] type shared elsewhere.
        Best-effort: a missing API token or any request failure returns []
        rather than breaking sync_sec()'s submissions-based sync around it.
        """
        if not self.settings.finnhub_api_token:
            return []
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=FINNHUB_INSIDER_LOOKBACK_DAYS)).date()
        try:
            transactions = self.finnhub.insider_transactions(symbol, since=cutoff_date)
        except Exception:
            return []
        events = []
        for transaction in transactions:
            transaction_date = safe_date(transaction.get("transaction_date"))
            if not transaction_date or transaction_date < cutoff_date:
                continue
            insider_name = clean_text(str(transaction.get("insider_name") or ""))
            code = str(transaction.get("transaction_code") or "")
            if not insider_name or not code:
                continue
            share_change = float(transaction.get("share_change") or 0)
            action = "compra" if transaction.get("is_purchase") else "venda" if transaction.get("is_sale") else "movimentação"
            price = transaction.get("price")
            price_note = f" a ${price:,.2f}/ação" if price else ""
            slug = re.sub(r"[^a-z0-9]+", "-", insider_name.lower()).strip("-")
            published_at = datetime.combine(transaction_date, time.min, tzinfo=timezone.utc)
            events.append({
                "source_code": "sec",
                "external_id": f"finnhub-insider-{symbol}-{transaction_date.isoformat()}-{slug}-{code}",
                "company_id": company.get("id") if company else None,
                "market": "US",
                "symbol": symbol,
                "company_name": company_name,
                "regulator_id": cik,
                "event_type": "Insider Transaction",
                "form": "Form 4",
                "title": f"{insider_name}: {action} de {abs(share_change):,.0f} ações",
                "summary": f"{insider_name} ({action}) {abs(share_change):,.0f} ações{price_note} em {transaction_date.isoformat()}.",
                "published_at": published_at,
                "published_time_precision": "date",
                "reference_date": transaction_date,
                "official_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=4",
                "document_url": None,
                "materiality": "low",
                "valuation_relevant": False,
                "valuation_status": "informational",
                "raw_metadata": {"source": "finnhub", **transaction},
                "collected_at": datetime.now().astimezone(),
            })
        return events

    def _eodhd_insider_events(
        self, symbol: str, cik: str, company: dict[str, Any] | None, company_name: str,
    ) -> list[dict[str, Any]]:
        """SEC Form 4 insider activity from EODHD's All-in-one plan --
        called only as a fallback when _finnhub_insider_events() returns
        nothing for this symbol (data-source audit, 2026-08-20: EODHD's
        own insider feed was never used at all, even though it's included
        in the plan we already pay for). Deliberately NOT summed with
        Finnhub's results: both ultimately source the same underlying SEC
        Form 4 filings, so adding both would double-count the same
        real-world transactions in the buy/sell signal. external_id is
        "eodhd-insider-..."-prefixed (vs Finnhub's "finnhub-insider-...")
        so the two never collide in ir_events even for the same filing.
        Best-effort: a missing token or any request failure returns [].
        """
        if not self.settings.eodhd_api_token:
            return []
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=FINNHUB_INSIDER_LOOKBACK_DAYS)).date()
        try:
            transactions = self.eodhd.insider_transactions(symbol, since=cutoff_date)
        except Exception:
            return []
        events = []
        for transaction in transactions:
            transaction_date = safe_date(transaction.get("transaction_date"))
            if not transaction_date or transaction_date < cutoff_date:
                continue
            insider_name = clean_text(str(transaction.get("insider_name") or ""))
            code = str(transaction.get("transaction_code") or "")
            if not insider_name or not code:
                continue
            share_change = float(transaction.get("share_change") or 0)
            action = "compra" if transaction.get("is_purchase") else "venda" if transaction.get("is_sale") else "movimentação"
            price = transaction.get("price")
            price_note = f" a ${price:,.2f}/ação" if price else ""
            slug = re.sub(r"[^a-z0-9]+", "-", insider_name.lower()).strip("-")
            published_at = datetime.combine(transaction_date, time.min, tzinfo=timezone.utc)
            events.append({
                "source_code": "sec",
                "external_id": f"eodhd-insider-{symbol}-{transaction_date.isoformat()}-{slug}-{code}",
                "company_id": company.get("id") if company else None,
                "market": "US",
                "symbol": symbol,
                "company_name": company_name,
                "regulator_id": cik,
                "event_type": "Insider Transaction",
                "form": "Form 4",
                "title": f"{insider_name}: {action} de {abs(share_change):,.0f} ações",
                "summary": f"{insider_name} ({action}) {abs(share_change):,.0f} ações{price_note} em {transaction_date.isoformat()}.",
                "published_at": published_at,
                "published_time_precision": "date",
                "reference_date": transaction_date,
                "official_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=4",
                "document_url": None,
                "materiality": "low",
                "valuation_relevant": False,
                "valuation_status": "informational",
                "raw_metadata": {"source": "eodhd", **transaction},
                "collected_at": datetime.now().astimezone(),
            })
        return events

    def sync_finnhub_news(self) -> tuple[int, int]:
        """News sentiment (one snapshot per company per ISO week) and keyword-
        matched company news for the same watched US companies -- source_code
        "finnhub" (db/020_ir_events_finnhub_source.sql), separate from "sec"
        since this isn't SEC-derived data, unlike insider transactions.
        """
        run_id = self.database.begin_ingestion_run("finnhub", "Finnhub", "market_sentiment", {"operation": "news_and_sentiment"})
        try:
            if not self.settings.finnhub_api_token:
                self.database.finish_ingestion_run(run_id, "succeeded", 0, 0)
                return 0, 0
            watched = {item["symbol"]: item for item in self.database.ir_watch_symbols() if item["market"] == "US"}
            since = (datetime.now(timezone.utc) - timedelta(days=FINNHUB_NEWS_LOOKBACK_DAYS)).date()
            until = datetime.now(timezone.utc).date()
            read = 0
            events: list[dict[str, Any]] = []
            for symbol in sorted(watched):
                company = self._company_for_symbol("US", symbol)
                company_name = clean_text(str(watched[symbol].get("company_name") or symbol))
                events.extend(self._finnhub_sentiment_event(symbol, company, company_name))
                articles = self._finnhub_news_events(symbol, company, company_name, since, until)
                read += len(articles)
                events.extend(articles)
            written = self.database.save_ir_events(events)
            self.database.finish_ingestion_run(run_id, "succeeded", read, written)
            return read, written
        except Exception as exc:
            self.database.finish_ingestion_run(run_id, "failed", 0, 0, str(exc))
            raise

    def _finnhub_sentiment_event(
        self, symbol: str, company: dict[str, Any] | None, company_name: str,
    ) -> list[dict[str, Any]]:
        """One event per company per ISO week (external_id keyed by
        year+week), so polling every 15 minutes doesn't spam the feed with
        near-duplicate snapshots -- save_ir_events upserts on
        (source_code, external_id), so re-running this same week just
        refreshes the one row instead of creating a new one.
        """
        try:
            sentiment = self.finnhub.news_sentiment(symbol)
        except Exception:
            return []
        if not sentiment:
            return []
        now = datetime.now(timezone.utc)
        iso_year, iso_week, _ = now.isocalendar()
        bullish = sentiment["bullish_percent"]
        bearish = sentiment["bearish_percent"]
        return [{
            "source_code": "finnhub",
            "external_id": f"finnhub-sentiment-{symbol}-{iso_year}-W{iso_week:02d}",
            "company_id": company.get("id") if company else None,
            "market": "US",
            "symbol": symbol,
            "company_name": company_name,
            "regulator_id": None,
            "event_type": "News Sentiment",
            "form": None,
            "title": f"Sentimento de notícias: {bullish:.0f}% bullish",
            "summary": (
                f"{bullish:.0f}% bullish / {bearish:.0f}% bearish nos artigos recentes; "
                f"{sentiment['articles_last_week']} artigos na última semana."
            ),
            "published_at": now,
            "published_time_precision": "collected",
            "reference_date": now.date(),
            "official_url": f"https://finnhub.io/quote/{symbol}",
            "document_url": None,
            "materiality": "low",
            "valuation_relevant": False,
            "valuation_status": "informational",
            "raw_metadata": {"source": "finnhub", **sentiment},
            "collected_at": datetime.now().astimezone(),
        }]

    def _finnhub_news_events(
        self, symbol: str, company: dict[str, Any] | None, company_name: str, since: date, until: date,
    ) -> list[dict[str, Any]]:
        """Company news filtered to FINNHUB_NEWS_KEYWORDS -- Finnhub's feed has
        no server-side relevance filter, and ingesting every routine article
        would flood ir_events with noise the whole system is designed to
        avoid (see feed()'s methodology text). Same keyword-gating philosophy
        as _enrich_with_sec_fulltext, just for a different data source.
        """
        try:
            articles = self.finnhub.company_news(symbol, since=since, until=until)
        except Exception:
            return []
        events = []
        for article in articles:
            haystack = f"{article['headline']} {article['summary']}".lower()
            matched = [keyword for keyword in FINNHUB_NEWS_KEYWORDS if keyword in haystack]
            if not matched:
                continue
            summary = (article["summary"] or article["headline"])[:500]
            events.append({
                "source_code": "finnhub",
                "external_id": f"finnhub-news-{article['article_id']}",
                "company_id": company.get("id") if company else None,
                "market": "US",
                "symbol": symbol,
                "company_name": company_name,
                "regulator_id": None,
                "event_type": "News Mention",
                "form": None,
                "title": article["headline"],
                "summary": f"{summary} (menções: {', '.join(matched)})",
                "published_at": article["published_at"],
                "published_time_precision": "datetime",
                "reference_date": article["published_at"].date(),
                "official_url": article["url"] or f"https://finnhub.io/quote/{symbol}",
                "document_url": article["url"],
                "materiality": "low",
                "valuation_relevant": False,
                "valuation_status": "informational",
                "raw_metadata": {"source": "finnhub", "matched_keywords": matched, "article_source": article["source"]},
                "collected_at": datetime.now().astimezone(),
            })
        return events

    def sync_ri(self) -> tuple[int, int]:
        run_id = self.database.begin_ingestion_run("ri", "Issuer Investor Relations", "issuer_relations", {"operation": "official_pages"})
        try:
            self._register_ri_overrides()
            companies = [item for item in self.database.list_ir_companies() if item.get("ri_url")]
            read = 0
            events: list[dict[str, Any]] = []
            collected_at = datetime.now().astimezone()
            for company in companies:
                try:
                    company_read, company_events = self._collect_ri_company(company, collected_at)
                    read += company_read
                    events.extend(company_events)
                except Exception:
                    continue
            written = self.database.save_ir_events(events)
            self.database.finish_ingestion_run(run_id, "succeeded", read, written)
            return read, written
        except Exception as exc:
            self.database.finish_ingestion_run(run_id, "failed", 0, 0, str(exc))
            raise

    def refresh_company(
        self,
        symbol: str,
        market: str,
        *,
        company_name: str = "",
    ) -> dict[str, Any]:
        """Refresh official issuer evidence immediately before a valuation run."""
        clean_symbol = symbol.strip().upper().removesuffix(".SA")
        normalized_market = market.upper()
        if normalized_market == "B3":
            self._register_ri_overrides()
            company = self._company_for_symbol("B3", clean_symbol)
            if not company or not company.get("ri_url"):
                self.sync_cvm()
                self._register_ri_overrides()
                company = self._company_for_symbol("B3", clean_symbol)
        else:
            self.add_watch(
                clean_symbol,
                "US",
                company_name or clean_symbol,
                ri_url=GLOBAL_RI_URL_OVERRIDES.get(clean_symbol),
            )
            self.sync_sec()
            company = self._company_for_symbol("US", clean_symbol)

        if not company:
            self.add_watch(clean_symbol, normalized_market, company_name or clean_symbol)
            company = self._company_for_symbol(normalized_market, clean_symbol)

        collected_at = datetime.now().astimezone()
        records_read = 0
        records_written = 0
        issuer_error = ""
        if company and company.get("ri_url"):
            try:
                records_read, events = self._collect_ri_company(company, collected_at)
                records_written = self.database.save_ir_events(events)
            except Exception as exc:
                issuer_error = str(exc)
        latest = self.database.latest_valuation_ir_events([clean_symbol], normalized_market).get(clean_symbol)
        regulator_url = (
            (latest or {}).get("official_url")
            or ("https://dados.cvm.gov.br/" if normalized_market == "B3" else "https://www.sec.gov/edgar/search/")
        )
        return {
            "symbol": clean_symbol,
            "market": normalized_market,
            "company_name": (company or {}).get("company_name") or company_name or clean_symbol,
            "ri_url": (company or {}).get("ri_url") or regulator_url,
            "checked_at": collected_at,
            "records_read": records_read,
            "records_written": records_written,
            "latest_event": latest,
            "verification_status": "issuer_and_regulator" if (company or {}).get("ri_url") and not issuer_error else "regulator_only",
            "issuer_error": issuer_error,
        }

    def _collect_ri_company(
        self,
        company: dict[str, Any],
        collected_at: datetime,
    ) -> tuple[int, list[dict[str, Any]]]:
        page_text, _ = self._fetch_ri_page(str(company["ri_url"]))
        mziq_events = self._mziq_events(company, page_text, collected_at)
        if mziq_events is not None:
            return len(mziq_events), mziq_events

        parser = LinkCollector()
        parser.feed(page_text)
        base_host = urlparse(str(company["ri_url"])).netloc
        events: list[dict[str, Any]] = []
        read = 0
        for href, title in parser.links:
            read += 1
            absolute = urljoin(str(company["ri_url"]), href)
            document_host = urlparse(absolute).netloc.lower()
            if document_host != base_host and document_host not in RI_TRUSTED_DOCUMENT_HOSTS:
                continue
            if is_ri_navigation_link(title, absolute, str(company["ri_url"])):
                continue
            haystack = f"{title} {href}".casefold()
            if not title or not any(keyword in haystack for keyword in RI_KEYWORDS):
                continue
            event_type, materiality, relevant = self._classify_ri(title)
            symbol = company.get("symbols", [None])[0] if company.get("symbols") else None
            events.append({
                "source_code": "ri",
                "external_id": hashlib.sha256(absolute.encode()).hexdigest(),
                "company_id": company["id"],
                "market": company["market"],
                "symbol": symbol,
                "company_name": company["company_name"],
                "regulator_id": company.get("regulator_id"),
                "event_type": event_type,
                "form": "RI",
                "title": title,
                "summary": "Documento localizado na página oficial de Relações com Investidores da companhia.",
                # The RI page's HTTP Last-Modified header describes when the
                # PAGE was last edited, not when any individual linked
                # document was published -- every link on the page would
                # otherwise inherit one shared, falsely precise timestamp.
                # collected_at (when we found the link) is the only value
                # honestly attributable to each document here.
                "published_at": collected_at,
                "published_time_precision": "collected",
                "reference_date": None,
                "official_url": str(company["ri_url"]),
                "document_url": absolute,
                "materiality": materiality,
                "valuation_relevant": relevant,
                "valuation_status": "pending_review" if relevant else "informational",
                "raw_metadata": {"source_page": company["ri_url"]},
                "collected_at": collected_at,
            })
            if len(events) >= 40:
                break
        return read, events

    def _fetch_ri_page(self, url: str) -> tuple[str, dict[str, str]]:
        try:
            response = self.client.get(url)
            response.raise_for_status()
            return response.text, dict(response.headers)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in {403, 406, 429, 503}:
                raise

        # Several issuer sites use bot protection even though the content is public.
        # curl_cffi reproduces a normal browser TLS fingerprint without running Chromium.
        browser_response = curl_requests.get(
            url,
            impersonate="chrome136",
            timeout=30,
            allow_redirects=True,
            headers={"Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"},
        )
        browser_response.raise_for_status()
        return browser_response.text, dict(browser_response.headers)

    def _register_ri_overrides(self) -> None:
        companies = self.database.list_ir_companies("B3")
        registrations = []
        for symbol, ri_url in RI_URL_OVERRIDES.items():
            company = next((item for item in companies if symbol in item.get("symbols", [])), None)
            if not company:
                continue
            registrations.append({
                "market": "B3",
                "symbol": symbol,
                "company_name": company["company_name"],
                "name_key": company["name_key"],
                "regulator_id": company.get("regulator_id"),
                "tax_id": company.get("tax_id"),
                "exchange": company.get("exchange") or "B3",
                "ri_url": ri_url,
            })
        self.database.register_ir_securities(registrations)

    def _mziq_events(
        self,
        company: dict[str, Any],
        page_text: str,
        collected_at: datetime,
    ) -> list[dict[str, Any]] | None:
        company_match = re.search(r"\b(?:const|var)\s+fmId\s*=\s*['\"]([^'\"]+)", page_text)
        base_match = re.search(r"\b(?:const|var)\s+fmBase\s*=\s*['\"]([^'\"]+)", page_text)
        category_names = self._mziq_category_names(page_text)
        if not company_match or not base_match or not category_names:
            return None

        company_code = company_match.group(1)
        base_url = base_match.group(1).rstrip("/")
        year = datetime.now(SAO_PAULO).year
        response = self.client.post(
            f"{base_url}/company/{company_code}/filter/categories/year/meta",
            json={
                "year": year,
                "categories": category_names,
                "language": "pt_BR",
                "published": True,
            },
        )
        response.raise_for_status()
        documents = response.json().get("data", {}).get("document_metas", [])
        if not isinstance(documents, list):
            return []

        quarter_publication_dates: dict[tuple[int, int], datetime] = {}
        for document in documents:
            if not isinstance(document, dict):
                continue
            doc_year = self._safe_int(document.get("file_year"))
            quarter = self._safe_int(document.get("file_quarter"))
            published_at = self._mziq_publication_datetime(document.get("file_published_date"))
            if doc_year and quarter and published_at:
                key = (doc_year, quarter)
                quarter_publication_dates[key] = max(quarter_publication_dates.get(key, published_at), published_at)

        symbol = company.get("symbols", [None])[0] if company.get("symbols") else None
        events = []
        for document in documents:
            if not isinstance(document, dict):
                continue
            title = clean_text(str(document.get("file_title") or document.get("file_name_original") or ""))
            document_url = clean_text(str(document.get("link_url") or document.get("permalink") or document.get("file_url") or ""))
            if not title or not document_url:
                continue
            haystack = f"{title} {document.get('internal_name') or ''}".casefold()
            if not any(keyword in haystack for keyword in RI_KEYWORDS) and not any(
                token in haystack for token in ("itr", "dfp", "demonstrações financeiras", "demonstracoes financeiras")
            ):
                continue
            doc_year = self._safe_int(document.get("file_year"))
            quarter = self._safe_int(document.get("file_quarter"))
            key = (doc_year, quarter) if doc_year and quarter else None
            published_at = quarter_publication_dates.get(key) if key else None
            published_at = published_at or self._mziq_publication_datetime(document.get("file_published_date"))
            published_time_precision = "date" if published_at else "collected"
            published_at = published_at or collected_at
            reference_date = self._quarter_end(doc_year, quarter) if doc_year and quarter else safe_date(str(document.get("file_date") or ""))
            event_type, materiality, relevant = self._classify_ri(title)
            events.append({
                "source_code": "ri",
                "external_id": f"mziq:{company_code}:{document.get('id') or hashlib.sha256(document_url.encode()).hexdigest()}",
                "company_id": company["id"],
                "market": company["market"],
                "symbol": symbol,
                "company_name": company["company_name"],
                "regulator_id": company.get("regulator_id"),
                "event_type": event_type,
                "form": "RI/MZIQ",
                "title": title,
                "summary": "Documento publicado no canal oficial de Relações com Investidores da companhia.",
                "published_at": published_at,
                "published_time_precision": published_time_precision,
                "reference_date": reference_date,
                "official_url": str(company["ri_url"]),
                "document_url": document_url,
                "materiality": materiality,
                "valuation_relevant": relevant,
                "valuation_status": "pending_review" if relevant else "informational",
                "raw_metadata": {"provider": "MZIQ", **document},
                "collected_at": collected_at,
            })
        return events

    @staticmethod
    def _mziq_category_names(page_text: str) -> list[str]:
        """Read category identifiers from both MZ File Manager script formats."""
        names: list[str] = []
        categories_match = re.search(r"\bvar\s+categories\s*=\s*(\[.*?\]);", page_text, re.DOTALL)
        if categories_match:
            try:
                categories = json.loads(categories_match.group(1))
            except (json.JSONDecodeError, TypeError):
                categories = []
            names.extend(
                clean_text(str(item.get("internal_name") or ""))
                for item in categories
                if isinstance(item, dict) and item.get("internal_name")
            )

        # Newer MZ templates initialize an empty array and append JS objects.
        names.extend(
            clean_text(match)
            for match in re.findall(
                r"categories\.push\s*\(\s*\{.*?\binternal_name\s*:\s*['\"]([^'\"]+)['\"].*?\}\s*\)",
                page_text,
                re.DOTALL,
            )
        )
        return list(dict.fromkeys(name for name in names if name))

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=SAO_PAULO)
        except ValueError:
            return None

    @staticmethod
    def _mziq_publication_datetime(value: Any) -> datetime | None:
        # MZIQ exposes publication as a calendar date encoded at 00:00 UTC.
        # Treating it as an instant moves Brazilian filings to the previous day.
        publication_date = safe_date(str(value or ""))
        return datetime.combine(publication_date, time.min, tzinfo=SAO_PAULO) if publication_date else None

    @staticmethod
    def _quarter_end(year: int, quarter: int) -> date | None:
        if quarter not in {1, 2, 3, 4}:
            return None
        month = quarter * 3
        next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
        return next_month - timedelta(days=1)

    def report(
        self,
        *,
        market: str | None = None,
        source: str | None = None,
        event_type: str | None = None,
        query: str | None = None,
        monitored_only: bool = True,
    ) -> Path:
        response = self.feed(limit=80, market=market, source=source, event_type=event_type, query=query, monitored_only=monitored_only)
        path = self.pdf.render(response)
        self.database.save_ir_report_export(
            path.name,
            len(response.items),
            {"market": market, "source": source, "event_type": event_type, "query": query, "monitored_only": monitored_only},
        )
        return path

    def _register_brapi_b3_universe(self) -> None:
        headers = {"Authorization": f"Bearer {self.settings.brapi_token}"} if self.settings.brapi_token else {}
        try:
            response = self.client.get(
                f"{self.settings.brapi_base_url.rstrip('/')}/api/v2/tickers",
                params={"type": "stock", "subType": "stock", "sortBy": "volume", "sortOrder": "desc", "limit": 350},
                headers=headers,
            )
            response.raise_for_status()
            catalog = [item for item in response.json().get("results", []) if isinstance(item, dict)]
            self.register_b3_universe(catalog)
        except (httpx.HTTPError, ValueError, TypeError):
            # CVM ingestion remains authoritative even if the optional ticker bridge is unavailable.
            return

    def _register_cvm_ri_channels(
        self,
        year: int,
        company_index: dict[str, dict[str, Any]],
    ) -> int:
        url = f"{self.settings.cvm_data_base_url.rstrip('/')}/CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_{year}.zip"
        response = self.client.get(url)
        if response.status_code == 404:
            return 0
        response.raise_for_status()
        expected = f"fca_cia_aberta_canal_divulgacao_{year}.csv"
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            filename = next((name for name in archive.namelist() if name.lower() == expected.lower()), None)
            if not filename:
                return 0
            text = archive.read(filename).decode("latin-1")
        rows = list(csv.DictReader(io.StringIO(text), delimiter=";"))
        selected: dict[str, tuple[int, str, dict[str, Any]]] = {}
        for row in rows:
            channel = clean_text(row.get("Canal_Divulgacao", ""))
            company_name = clean_text(row.get("Nome_Empresarial", ""))
            if not channel.lower().startswith(("http://", "https://")) or not company_name:
                continue
            host = urlparse(channel).netloc.lower().removeprefix("www.")
            if any(host == blocked or host.endswith(f".{blocked}") for blocked in RI_BLOCKED_HOSTS):
                continue
            company = self._match_company(company_name, company_index)
            if not company:
                continue
            lowered = channel.casefold()
            score = sum(3 for hint in RI_URL_HINTS if hint in lowered)
            score += 1 if urlparse(channel).scheme == "https" else 0
            if score < 3:
                continue
            current = selected.get(company["id"])
            if current is None or score > current[0]:
                selected[company["id"]] = (score, channel, company)
        registrations = []
        for _, channel, company in selected.values():
            registrations.append({
                "market": "B3",
                "company_name": company["company_name"],
                "name_key": company["name_key"],
                "regulator_id": company.get("regulator_id"),
                "tax_id": company.get("tax_id"),
                "exchange": "B3",
                "ri_url": channel,
            })
        self.database.register_ir_securities(registrations)
        return len(rows)

    def _cvm_event(
        self,
        row: dict[str, str],
        company_index: dict[str, dict[str, Any]],
        collected_at: datetime,
    ) -> dict[str, Any] | None:
        company_name = clean_text(row.get("Nome_Companhia", ""))
        delivery = safe_date(row.get("Data_Entrega"))
        if not company_name or not delivery:
            return None
        company = self._match_company(company_name, company_index)
        category = clean_text(row.get("Categoria", ""))
        subtype = clean_text(row.get("Tipo", ""))
        subject = clean_text(row.get("Assunto", ""))
        event_type, materiality, relevant = self._classify_cvm(category, subtype)
        title = subject or " · ".join(value for value in (category, subtype) if value) or "Documento CVM"
        external_id = clean_text(row.get("Protocolo_Entrega", "")) or hashlib.sha256(
            f"{row.get('Codigo_CVM')}|{delivery}|{category}|{subtype}|{row.get('Link_Download')}".encode()
        ).hexdigest()
        symbols = company.get("symbols", []) if company else []
        return {
            "source_code": "cvm",
            "external_id": external_id,
            "company_id": company.get("id") if company else None,
            "market": "B3",
            "symbol": symbols[0] if symbols else None,
            "company_name": company_name,
            "regulator_id": clean_text(row.get("Codigo_CVM", "")) or None,
            "event_type": event_type,
            "form": subtype or category,
            "title": title,
            "summary": f"{category}{f' | {subtype}' if subtype else ''}",
            "published_at": date_at_midnight(delivery.isoformat()),
            "published_time_precision": "date",
            "reference_date": safe_date(row.get("Data_Referencia")),
            "official_url": "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/",
            "document_url": clean_text(row.get("Link_Download", "")) or None,
            "materiality": materiality,
            "valuation_relevant": relevant,
            "valuation_status": "pending_review" if relevant else "informational",
            "raw_metadata": row,
            "collected_at": collected_at,
        }

    def _cvm_structured_rows(self, document_type: str, year: int, cutoff: date) -> list[dict[str, str]]:
        rows, _, _ = self._cvm_structured_package(document_type, year, cutoff)
        return rows

    def _cvm_ipe_rows(
        self,
        year: int,
        cutoff: date,
    ) -> tuple[list[dict[str, str]], bool]:
        url = f"{self.settings.cvm_data_base_url.rstrip('/')}/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{year}.zip"
        response = self.client.get(url)
        if response.status_code == 404:
            return [], False
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            filename = next(name for name in archive.namelist() if name.lower().endswith(".csv"))
            text = archive.read(filename).decode("latin-1")
        rows = list(csv.DictReader(io.StringIO(text), delimiter=";"))
        return [
            row
            for row in rows
            if (safe_date(row.get("Data_Entrega")) or date.min) >= cutoff
        ], True

    def _cvm_structured_package(
        self,
        document_type: str,
        year: int,
        cutoff: date,
    ) -> tuple[list[dict[str, str]], bytes, str]:
        upper = document_type.upper()
        url = f"{self.settings.cvm_data_base_url.rstrip('/')}/CIA_ABERTA/DOC/{upper}/DADOS/{document_type}_cia_aberta_{year}.zip"
        response = self.client.get(url)
        if response.status_code == 404:
            return [], b"", url
        response.raise_for_status()
        expected = f"{document_type}_cia_aberta_{year}.csv"
        payload = response.content
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            filename = next((name for name in archive.namelist() if name.lower() == expected.lower()), None)
            if not filename:
                return [], payload, url
            text = archive.read(filename).decode("latin-1")
        rows = list(csv.DictReader(io.StringIO(text), delimiter=";"))
        return [row for row in rows if (safe_date(row.get("DT_RECEB")) or date.min) >= cutoff], payload, url

    def _enrich_cvm_security_bridges(
        self,
        rows: list[dict[str, str]],
        company_index: dict[str, dict[str, Any]],
    ) -> None:
        registrations: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            company_name = clean_text(row.get("DENOM_CIA", ""))
            company = self._match_company(company_name, company_index)
            if not company:
                continue
            for symbol in company.get("symbols", []):
                registrations[(company["id"], symbol)] = {
                    "market": "B3",
                    "symbol": symbol,
                    "company_name": company_name or company["company_name"],
                    "name_key": company["name_key"],
                    "regulator_id": clean_text(row.get("CD_CVM", "")) or company.get("regulator_id"),
                    "tax_id": clean_text(row.get("CNPJ_CIA", "")) or company.get("tax_id"),
                    "exchange": "B3",
                    "ri_url": company.get("ri_url"),
                }
        self.database.register_ir_securities(list(registrations.values()))

    def _cvm_overlay_issuers(
        self,
        rows: list[dict[str, str]],
        company_index: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        issuers: dict[str, dict[str, Any]] = {}
        for row in rows:
            tax_id = clean_text(row.get("CNPJ_CIA", ""))
            company_name = clean_text(row.get("DENOM_CIA", ""))
            received = safe_date(row.get("DT_RECEB"))
            company = self._match_company(company_name, company_index)
            if not tax_id or not received or not company or not company.get("symbols"):
                continue
            published_at = date_at_midnight(received.isoformat())
            prior = issuers.get(tax_id)
            if prior and prior["published_at"] > published_at:
                continue
            issuers[tax_id] = {
                "symbols": company["symbols"],
                "company_name": company_name,
                "regulator_id": clean_text(row.get("CD_CVM", "")) or company.get("regulator_id"),
                "published_at": published_at,
            }
        return issuers

    def _cvm_structured_event(
        self,
        row: dict[str, str],
        company_index: dict[str, dict[str, Any]],
        collected_at: datetime,
    ) -> dict[str, Any] | None:
        company_name = clean_text(row.get("DENOM_CIA", ""))
        delivery = safe_date(row.get("DT_RECEB"))
        document_type = clean_text(row.get("CATEG_DOC", ""))
        if not company_name or not delivery or document_type not in {"ITR", "DFP"}:
            return None
        company = self._match_company(company_name, company_index)
        symbols = company.get("symbols", []) if company else []
        reference_date = safe_date(row.get("DT_REFER"))
        period = reference_date.strftime("%d/%m/%Y") if reference_date else "período não informado"
        document_url = clean_text(row.get("LINK_DOC", "")) or None
        external_id = f"{document_type}:{row.get('ID_DOC')}:{row.get('VERSAO')}"
        return {
            "source_code": "cvm",
            "external_id": external_id,
            "company_id": company.get("id") if company else None,
            "market": "B3",
            "symbol": symbols[0] if symbols else None,
            "company_name": company_name,
            "regulator_id": clean_text(row.get("CD_CVM", "")) or None,
            "event_type": "Financial Results",
            "form": document_type,
            "title": f"{document_type} | reporting period {period}",
            "summary": f"Formal {document_type} filing received by CVM, version {row.get('VERSAO') or '1'}.",
            "published_at": date_at_midnight(delivery.isoformat()),
            "published_time_precision": "date",
            "reference_date": reference_date,
            "official_url": document_url or "https://dados.cvm.gov.br/",
            "document_url": document_url,
            "materiality": "high",
            "valuation_relevant": True,
            "valuation_status": "pending_review",
            "raw_metadata": row,
            "collected_at": collected_at,
        }

    def _sec_event(
        self,
        payload: dict[str, Any],
        recent: dict[str, list[Any]],
        index: int,
        company: dict[str, Any] | None,
        cutoff: datetime,
    ) -> dict[str, Any] | None:
        # the submissions JSON acceptanceDateTime is NOT true UTC (verified 2026-10-17 against the filing headers: it is
        # the real instant plus the New York UTC offset); sync_sec replaces it by the header instant (defect e)
        raw_acceptance = str(recent["acceptanceDateTime"][index])
        accepted = acceptance_from_submissions_json(raw_acceptance)
        if accepted < cutoff:
            return None
        accession = str(recent["accessionNumber"][index])
        form = str(recent["form"][index])
        cik = str(payload.get("cik", "")).lstrip("0") or "0"
        primary = str(recent.get("primaryDocument", [""])[index])
        archive_url = f"{self.settings.sec_archives_base_url.rstrip('/')}/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{primary}"
        event_type, materiality, relevant = self._classify_sec(form)
        description = clean_text(str(recent.get("primaryDocDescription", [""])[index]))
        items = clean_text(str(recent.get("items", [""])[index]))
        company_name = clean_text(str(payload.get("name") or (company or {}).get("company_name") or "SEC issuer"))
        symbol = ((company or {}).get("symbols") or payload.get("tickers") or [None])[0]
        reference_date = safe_date(str(recent.get("reportDate", [""])[index]))
        return {
            "source_code": "sec",
            "external_id": accession,
            "company_id": company.get("id") if company else None,
            "market": "US",
            "symbol": symbol,
            "company_name": company_name,
            "regulator_id": str(payload.get("cik", "")),
            "event_type": event_type,
            "form": form,
            "title": description or f"{form} filing",
            "summary": f"SEC form {form}{f' | Items {items}' if items else ''}",
            "published_at": accepted,
            "published_time_precision": "datetime",
            "reference_date": reference_date,
            "official_url": f"{self.settings.sec_archives_base_url.rstrip('/')}/Archives/edgar/data/{cik}/{accession.replace('-', '')}/",
            "document_url": archive_url,
            "materiality": materiality,
            "valuation_relevant": relevant,
            "valuation_status": "pending_review" if relevant else "informational",
            "raw_metadata": {
                "accession": accession, "items": items, "is_xbrl": recent.get("isXBRL", [0])[index],
                "acceptance_time_source": SEC_ACCEPTANCE_FROM_SUBMISSIONS,
                "acceptance_datetime_json": raw_acceptance,
            },
            "collected_at": datetime.now().astimezone(),
        }

    def _company_for_symbol(self, market: str, symbol: str) -> dict[str, Any] | None:
        return next(
            (company for company in self.database.list_ir_companies(market) if symbol in company.get("symbols", [])),
            None,
        )

    @staticmethod
    def _match_company(company_name: str, index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
        key = normalize_company_name(company_name)
        if key in index:
            return index[key]
        candidates = []
        for candidate_key, company in index.items():
            if not company.get("symbols"):
                continue
            score = SequenceMatcher(None, key, candidate_key).ratio()
            if key in candidate_key or candidate_key in key:
                score = max(score, 0.90)
            candidates.append((score, company))
        if not candidates:
            return None
        score, company = max(candidates, key=lambda item: item[0])
        return company if score >= 0.82 else None

    @staticmethod
    def _classify_cvm(category: str, subtype: str) -> tuple[str, str, bool]:
        text = f"{category} {subtype}".casefold()
        if "fato relevante" in text:
            return "Material Fact", "high", True
        if "dados econômico-financeiros" in text or "demonstrações financeiras" in text or "press-release" in text:
            return "Financial Results", "high", True
        if "comunicado ao mercado" in text:
            relevant = any(word in text for word in ("aquisição", "alienação", "aumento de capital", "cvm", "b3"))
            return "Market Notice", "medium", relevant
        if "aviso aos acionistas" in text or "proventos" in text:
            return "Shareholder Notice", "medium", True
        if "reunião da administração" in text:
            return "Board Decision", "medium", False
        if "assembleia" in text:
            return "Shareholder Meeting", "low", False
        return "Regulatory Filing", "low", False

    @staticmethod
    def _classify_sec(form: str) -> tuple[str, str, bool]:
        normalized = form.removesuffix("/A")
        if normalized in {"10-Q", "10-K", "20-F", "40-F"}:
            return "Financial Results", "high", True
        if normalized in {"8-K", "6-K"}:
            return "Material Filing", "high", True
        return "SEC Filing", "medium", False

    @staticmethod
    def _classify_ri(title: str) -> tuple[str, str, bool]:
        text = title.casefold()
        if any(word in text for word in ("resultado", "results", "earnings", "release", "itr", "dfp", "demonstra")):
            return "Financial Results", "high", True
        if any(word in text for word in ("fato relevante", "material fact", "guidance", "aquisição", "acquisition", "merger")):
            return "Issuer Material Update", "high", True
        return "Issuer Update", "medium", False

    def _source_health(self) -> list[InvestorRelationsSourceHealth]:
        health = self.database.ir_source_health()
        definitions = {
            "cvm": ("CVM Dados Abertos", "Fatos, comunicados, ITR/DFP and issuer documents"),
            "sec": ("SEC EDGAR", "US filings with real-time EDGAR acceptance timestamps"),
            "ri": ("Issuer RI", "Official issuer pages configured in the watchlist"),
            "finnhub": ("Finnhub", "US news sentiment and company news (Fundamental-1 plan)"),
        }
        output = []
        for code, (name, detail) in definitions.items():
            state = health.get(code, {})
            if code == "ri":
                configured = any(item.get("ri_url") for item in self.database.list_ir_companies())
            elif code == "finnhub":
                configured = bool(self.settings.finnhub_api_token)
            else:
                configured = True
            status = "unconfigured" if not configured else "healthy" if state.get("last_status") == "succeeded" else "attention"
            output.append(InvestorRelationsSourceHealth(
                code=code,
                name=name,
                status=status,
                last_success_at=state.get("last_success_at"),
                last_error=state.get("last_error"),
                detail=detail,
            ))
        return output

    @staticmethod
    def _event_model(row: dict[str, Any]) -> InvestorRelationsEvent:
        return InvestorRelationsEvent(
            id=str(row["id"]),
            source=row["source_code"],
            market=row["market"],
            symbol=row.get("symbol"),
            company_name=row["company_name"],
            regulator_id=row.get("regulator_id"),
            event_type=row["event_type"],
            form=row.get("form"),
            title=row["title"],
            summary=row.get("summary", ""),
            published_at=row["published_at"],
            published_time_precision=row.get("published_time_precision", "datetime"),
            reference_date=str(row["reference_date"]) if row.get("reference_date") else None,
            official_url=row["official_url"],
            document_url=row.get("document_url"),
            materiality=row["materiality"],
            valuation_relevant=bool(row.get("valuation_relevant")),
            valuation_status=row["valuation_status"],
            reviewed_at=row.get("reviewed_at"),
            review_note=row.get("review_note", ""),
            collected_at=row["collected_at"],
        )
