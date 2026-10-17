"""CVM documents into the as-filed store of migration 051 (``statement_filings`` + ``statement_vintages``).

The tables and their writer (``app/statement_vintages.StatementVintageStore``) belong to the SEC XBRL front and are
market-agnostic: one filing row per regulator document, one vintage row per fact per document, append-only, with
``is_first_publication`` decided by the store. This adapter only translates CVM open-data rows into that shape and
delegates. Until the store module is merged and its tables exist it is a no-op that says why, so the CVM capture can
ship first and start keeping originals the day 051 lands -- the open-data dumps keep only the latest version of a
document, so a re-filed original survives only here.

Mapping. ``doc_id`` = CVM ``ID_DOC`` (one per delivered version, like an SEC accession), ``document_version`` =
``VERSAO``, ``form`` = ITR/DFP, ``filed_date`` = ``DT_RECEB``. CVM publishes a receipt DATE, not an instant:
``accepted_at`` is the END of that day in Sao Paulo (``accepted_source = cvm_dt_receb_end_of_day``), so a
point-in-time reader never sees a filing before it could have existed. A fact's ``concept`` is
``cvm:<statement>_<scope>:<CD_CONTA>:<DS_CONTA>`` (CVM codes are reused across layouts; the description is what the
filer called the line), ``unit`` BRL (or the filed currency), ``value`` = ``VL_CONTA`` times ``ESCALA_MOEDA``;
balance-sheet facts are instants (no ``period_start``). Capital composition facts are
``cvm:composicao_capital:<column>`` in shares.
"""
from __future__ import annotations

import importlib
import logging
import re
from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any

from .cvm_fundamentals import SAO_PAULO, CvmVintageBatch, _fold
from .database import Database


logger = logging.getLogger(__name__)

SOURCE = "cvm_dados_abertos"
ACCEPTED_SOURCE = "cvm_dt_receb_end_of_day"
STORE_MODULE = "app.statement_vintages"
TABLES = ("statement_filings", "statement_vintages")
SCALES = {"MIL": Decimal(1_000), "MILHAO": Decimal(1_000_000), "MILHOES": Decimal(1_000_000)}
FISCAL_PERIODS = {3: "Q1", 6: "Q2", 9: "Q3"}


class CvmVintageCapture:
    """Hands each batch of raw CVM rows to the 051 store. A document is registered in ``statement_filings`` only after
    its whole package was written, so a run that dies half-way redoes that document next time (the store's natural key
    makes the facts already written a no-op) instead of skipping it forever."""

    def __init__(self, database: Database, status: str, store: Any = None, detail: str | None = None) -> None:
        self.database = database
        self.status = status
        self.store = store
        self.detail = detail
        self.known: set[tuple[str, int]] = set()
        self.pending: dict[tuple[str, int], dict[str, Any]] = {}
        self.facts_written = 0
        self.filings_written = 0
        self.unindexed = 0
        self.failures: list[str] = []

    @classmethod
    def open(cls, database: Database) -> "CvmVintageCapture":
        try:
            module = importlib.import_module(STORE_MODULE)
            store = module.StatementVintageStore(database)
        except (ImportError, AttributeError):
            return cls(database, "store_absent")
        try:
            if database.database_url:
                with database.connection() as connection:
                    for table in TABLES:
                        present = connection.execute("SELECT to_regclass(%s)", (f"public.{table}",)).fetchone()
                        if not present or present[0] is None:
                            return cls(database, "table_absent", detail=table)
            capture = cls(database, "ready", store)
            capture.known = {
                (str(row["doc_id"]), int(row.get("document_version") or 1))
                for row in store.filings("B3", source=SOURCE)
            }
            return capture
        except Exception as exc:  # the capture never takes the statements run down with it
            return cls(database, "unavailable", detail=str(exc))

    @property
    def enabled(self) -> bool:
        return self.status == "ready"

    def write(self, batch: CvmVintageBatch) -> None:
        if not self.enabled:
            return
        facts: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for (tax_id, refer, version), rows in batch.rows.items():
            filing = cvm_filing(batch, tax_id, refer, version)
            if filing is None:
                self.unindexed += 1
                continue
            key = (filing["doc_id"], filing["document_version"])
            if key in self.known:
                continue
            self.pending.setdefault(key, filing)
            facts[tax_id].extend(cvm_facts(batch, filing, rows))
        for tax_id, rows in facts.items():
            if not rows:
                continue
            try:
                counts = self.store.insert_vintages("B3", tax_id, rows)
                self.facts_written += int((counts or {}).get("written") or 0)
            except Exception as exc:
                self._fail(exc)

    def finish_package(self) -> None:
        if not self.enabled or not self.pending:
            return
        try:
            self.filings_written += int(self.store.register_filings(list(self.pending.values())) or 0)
            self.known.update(self.pending)
        except Exception as exc:
            self._fail(exc)
        self.pending = {}

    def summary(self) -> str | None:
        """None when the capture ran clean; otherwise the warning for the ingestion run."""
        if self.enabled and not self.failures:
            return None
        if self.enabled:
            return f"statement_vintages: {len(self.failures)} write(s) failed; first: {self.failures[0]}"
        reason = {
            "store_absent": "store absent (app.statement_vintages, migration 051 front, not merged)",
            "table_absent": f"table {self.detail} absent (migration 051 not applied)",
            "unavailable": f"store unavailable ({self.detail})",
        }.get(self.status, self.status)
        return f"statement_vintages: {reason}; vintage capture skipped"

    def _fail(self, exc: Exception) -> None:
        self.failures.append(str(exc))
        logger.warning("CVM vintage capture failed: %s", exc)


def cvm_filing(batch: CvmVintageBatch, tax_id: str, refer: str, version: int) -> dict[str, Any] | None:
    """The 051 filing of one CVM document version, or None when the package index does not describe it (without
    ``ID_DOC`` and ``DT_RECEB`` there is no identity and no clock to file it under)."""
    index = batch.scan.documents.get((tax_id, refer, version)) or {}
    doc_id = str(index.get("ID_DOC") or "").strip()
    received = _date(index.get("DT_RECEB"))
    if not doc_id or received is None:
        return None
    reference = _date(refer)
    return {
        "market": "B3",
        "issuer_key": tax_id,
        "source": SOURCE,
        "doc_id": doc_id,
        "document_version": max(version, 1),
        "form": batch.scan.document_type,
        "symbols": list((batch.issuers.get(tax_id) or {}).get("symbols") or []),
        "period_of_report": reference,
        "filed_date": received,
        "accepted_at": datetime.combine(received, time.max, tzinfo=SAO_PAULO),
        "accepted_source": ACCEPTED_SOURCE,
        "fiscal_year": reference.year if reference else None,
        "fiscal_period": "FY" if batch.scan.document_type == "DFP" else FISCAL_PERIODS.get(reference.month) if reference else None,
    }


def cvm_facts(batch: CvmVintageBatch, filing: dict[str, Any], rows: list[list[str]]) -> list[dict[str, Any]]:
    document = {
        key: filing[key]
        for key in ("market", "issuer_key", "source", "doc_id", "document_version", "form", "fiscal_year", "fiscal_period",
                    "filed_date", "accepted_at")
    }
    output: list[dict[str, Any]] = []
    for row in rows:
        fields = dict(zip(batch.columns, row))
        if batch.statement == "composicao_capital":
            for column, raw in fields.items():
                value = _decimal(raw)
                if value is not None:
                    output.append({**document, "concept": f"cvm:composicao_capital:{column}", "unit": "shares",
                                   "period_start": None, "period_end": filing["period_of_report"], "value": value})
            continue
        value = _decimal(fields.get("VL_CONTA"))
        end = _date(fields.get("DT_FIM_EXERC"))
        code = fields.get("CD_CONTA", "").strip()
        if value is None or end is None or not code:
            continue
        currency = _fold(fields.get("MOEDA"))
        description = re.sub(r"\s+", " ", fields.get("DS_CONTA", "")).strip()
        output.append({
            **document,
            "concept": f"cvm:{batch.statement}:{code}:{description}",
            "unit": "BRL" if currency in {"", "REAL"} else currency,
            "period_start": _date(fields.get("DT_INI_EXERC")),
            "period_end": end,
            "value": value * SCALES.get(_fold(fields.get("ESCALA_MOEDA")), Decimal(1)),
        })
    return output


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _decimal(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value or "").strip())
    except InvalidOperation:
        return None
    return number if number.is_finite() else None
