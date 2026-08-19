from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import unicodedata
import zipfile
from datetime import date, datetime, time, timedelta, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import httpx
from curl_cffi import requests as curl_requests

from .config import Settings
from .cvm_fundamentals import extract_itr_official_fundamentals
from .database import Database
from .investor_relations_pdf import InvestorRelationsPdf
from .market_data.finnhub import FinnhubClient
from .official_fundamentals import save_official_fundamentals
from .schemas import (
    InvestorRelationsEvent,
    InvestorRelationsResponse,
    InvestorRelationsSourceHealth,
    InvestorRelationsSyncResponse,
)


SAO_PAULO = ZoneInfo("America/Sao_Paulo")
SEC_FORMS = {"8-K", "10-Q", "10-K", "6-K", "20-F", "40-F", "8-K/A", "10-Q/A", "10-K/A", "6-K/A", "20-F/A"}
SEC_FULLTEXT_KEYWORDS = (
    "guidance", "acquisition", "merger", "restatement", "material weakness",
    "impairment", "buyback", "investigation",
)
SEC_FULLTEXT_LOOKBACK_DAYS = 14
SEC_FULLTEXT_CIK_BATCH_SIZE = 40
FINNHUB_INSIDER_LOOKBACK_DAYS = 90
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
    def __init__(self, settings: Settings, database: Database) -> None:
        self.settings = settings
        self.database = database
        self.pdf = InvestorRelationsPdf(settings.investor_relations_output_dir)
        self.client = httpx.Client(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            headers={"User-Agent": settings.sec_user_agent, "Accept-Encoding": "gzip, deflate"},
        )
        self.finnhub = FinnhubClient(settings.finnhub_base_url, settings.finnhub_api_token, self.client)

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
        selected = ("cvm", "sec", "ri") if source == "all" else (source,)
        read = 0
        written = 0
        states: dict[str, str] = {}
        for code in selected:
            try:
                if code == "cvm":
                    source_read, source_written = self.sync_cvm()
                elif code == "sec":
                    source_read, source_written = self.sync_sec()
                elif code == "ri":
                    source_read, source_written = self.sync_ri()
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
            url = f"{self.settings.cvm_data_base_url.rstrip('/')}/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{year}.zip"
            response = self.client.get(url)
            response.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                filename = next(name for name in archive.namelist() if name.lower().endswith(".csv"))
                text = archive.read(filename).decode("latin-1")
            rows = list(csv.DictReader(io.StringIO(text), delimiter=";"))
            cutoff = datetime.now(SAO_PAULO).date() - timedelta(days=180)
            rows = [row for row in rows if (safe_date(row.get("Data_Entrega")) or date.min) >= cutoff]
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
            written = self.database.save_ir_events(events)
            records_read = len(rows) + len(itr_rows) + len(dfp_rows) + ri_channels_read
            self.database.finish_ingestion_run(run_id, "succeeded", records_read, written)
            return records_read, written
        except Exception as exc:
            self.database.finish_ingestion_run(run_id, "failed", 0, 0, str(exc))
            raise

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
                events.extend(self._finnhub_insider_events(symbol, cik, company, company_name))
            self._enrich_with_sec_fulltext(events)
            written = self.database.save_ir_events(events)
            self.database.finish_ingestion_run(run_id, "succeeded", read, written)
            return read, written
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
        page_text, response_headers = self._fetch_ri_page(str(company["ri_url"]))
        mziq_events = self._mziq_events(company, page_text, collected_at)
        if mziq_events is not None:
            return len(mziq_events), mziq_events

        parser = LinkCollector()
        parser.feed(page_text)
        base_host = urlparse(str(company["ri_url"])).netloc
        published = self._last_modified(response_headers.get("last-modified")) or collected_at
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
                "published_at": published,
                "published_time_precision": "datetime" if response_headers.get("last-modified") else "collected",
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
            published_at = published_at or self._mziq_publication_datetime(document.get("file_published_date")) or collected_at
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
                "published_time_precision": "date",
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
        accepted = datetime.fromisoformat(str(recent["acceptanceDateTime"][index]).replace("Z", "+00:00"))
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
            "raw_metadata": {"accession": accession, "items": items, "is_xbrl": recent.get("isXBRL", [0])[index]},
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

    @staticmethod
    def _last_modified(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = parsedate_to_datetime(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return None

    def _source_health(self) -> list[InvestorRelationsSourceHealth]:
        health = self.database.ir_source_health()
        definitions = {
            "cvm": ("CVM Dados Abertos", "Fatos, comunicados, ITR/DFP and issuer documents"),
            "sec": ("SEC EDGAR", "US filings with real-time EDGAR acceptance timestamps"),
            "ri": ("Issuer RI", "Official issuer pages configured in the watchlist"),
        }
        output = []
        for code, (name, detail) in definitions.items():
            state = health.get(code, {})
            configured = code != "ri" or any(item.get("ri_url") for item in self.database.list_ir_companies())
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
