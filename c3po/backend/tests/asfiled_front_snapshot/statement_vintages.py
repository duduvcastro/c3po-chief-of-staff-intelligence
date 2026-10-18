"""Append-only store of regulator statements as filed (migration 051): the filings registry and the fact vintages.

Market-agnostic on purpose — the US front writes SEC EDGAR accessions and XBRL facts (``app/sec_xbrl.py``); the B3 front
can write CVM documents into the same tables. Two rules every writer inherits from here:

* nothing is rewritten: a fact re-reported by a later document is a new row of that document (ON CONFLICT DO NOTHING
  on the natural key, the tables refuse UPDATE/DELETE/TRUNCATE);
* ``is_first_publication`` is decided at insert time, inside a per-issuer advisory lock, against every stored row of the
  same fact identity ``(market, issuer, source, concept, unit, period)``: a row is first when no row of that identity was
  accepted before it. Writers insert an issuer's documents in acceptance order, so the flag holds; a document that
  arrives AFTER a later-accepted one of the same fact is still stored, counted as ``out_of_order`` and logged — readers
  that need certainty order by ``accepted_at``.

The in-memory double (no ``C3PO_DATABASE_URL``) mirrors the constraints the tables declare, so tests see what
PostgreSQL would accept.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from .database import Database


logger = logging.getLogger(__name__)

MARKETS = ("US", "B3")
FactIdentity = tuple[str, str, str, str, str, str, str]  # (market, issuer, source, concept, unit, period_start or '', period_end)
_FILING_REQUIRED = ("market", "issuer_key", "source", "doc_id", "form", "filed_date", "accepted_at", "accepted_source")
_VINTAGE_REQUIRED = ("market", "issuer_key", "source", "doc_id", "form", "period_end", "concept", "unit", "value", "filed_date", "accepted_at")
_FILING_KEYS = ("id", "market", "issuer_key", "source", "doc_id", "document_version", "form", "items", "symbols", "period_of_report",
                "filed_date", "accepted_at", "accepted_source", "json_accepted_raw", "header_sha256", "first_seen_at")
_VINTAGE_KEYS = ("id", "market", "issuer_key", "source", "doc_id", "document_version", "form", "fiscal_year", "fiscal_period",
                 "period_start", "period_end", "concept", "unit", "value", "filed_date", "accepted_at", "first_seen_at",
                 "is_first_publication", "row_hash")
VINTAGE_BATCH = 5000


def utc_instant(value: Any) -> datetime:
    """The real instant of a clock (UTC), never its text. A naive value is refused: a filing clock without a zone is the
    exact defect this store exists to avoid."""
    instant = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise ValueError(f"naive instant {value!r}: a statement clock must carry its zone")
    return instant.astimezone(timezone.utc)


def as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        raise ValueError(f"{value!r} is an instant, not a date")
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def canonical_value(value: Any) -> str:
    """The NUMERIC text of a fact value: ``Decimal`` normalized, never exponent notation (``100`` not ``1E+2``)."""
    if isinstance(value, bool):
        raise ValueError("a boolean is not a fact value")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{value!r} is not a number") from error
    if not number.is_finite():
        raise ValueError(f"{value!r} is not a finite number")
    text = format(number.normalize(), "f")
    return "0" if text in {"-0", "0"} else text


def vintage_row_hash(row: Mapping[str, Any]) -> str:
    """sha256 of the row's content (the natural key, the document's metadata, the value and the acceptance instant) —
    never of the bookkeeping columns (``id``, ``first_seen_at``, ``is_first_publication``)."""
    core = {
        "market": str(row["market"]),
        "issuer_key": str(row["issuer_key"]),
        "source": str(row["source"]),
        "doc_id": str(row["doc_id"]),
        "document_version": int(row.get("document_version") or 1),
        "form": str(row["form"]),
        "fiscal_year": int(row["fiscal_year"]) if row.get("fiscal_year") is not None else None,
        "fiscal_period": str(row["fiscal_period"]) if row.get("fiscal_period") else None,
        "period_start": _iso(as_date(row.get("period_start"))),
        "period_end": _iso(as_date(row["period_end"])),
        "concept": str(row["concept"]),
        "unit": str(row["unit"]),
        "value": canonical_value(row["value"]),
        "filed_date": _iso(as_date(row["filed_date"])),
        "accepted_at": utc_instant(row["accepted_at"]).isoformat(),
    }
    return hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def fact_identity(row: Mapping[str, Any]) -> FactIdentity:
    start = as_date(row.get("period_start"))
    return (str(row["market"]), str(row["issuer_key"]), str(row["source"]), str(row["concept"]), str(row["unit"]),
            start.isoformat() if start else "", _iso(as_date(row["period_end"])) or "")


def _natural_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (*fact_identity(row), str(row["doc_id"]), int(row.get("document_version") or 1))


class StatementVintageStore:
    """Writers and point-in-time readers of ``statement_filings`` / ``statement_vintages``."""

    def __init__(self, database: Database) -> None:
        self.database = database
        if not hasattr(database, "_statement_filings"):
            database._statement_filings = []  # type: ignore[attr-defined]
        if not hasattr(database, "_statement_vintages"):
            database._statement_vintages = []  # type: ignore[attr-defined]

    # -- filings -------------------------------------------------------------------------------------------------------

    @staticmethod
    def _checked_filing(filing: Mapping[str, Any]) -> dict[str, Any]:
        missing = [key for key in _FILING_REQUIRED if filing.get(key) in (None, "")]
        if missing:
            raise ValueError(f"statement filing {filing.get('doc_id')!r} lacks {', '.join(missing)}")
        if filing["market"] not in MARKETS:
            raise ValueError(f"statement filing {filing['doc_id']!r} has market {filing['market']!r}")
        return {
            "id": str(filing.get("id") or uuid4()),
            "market": str(filing["market"]),
            "issuer_key": str(filing["issuer_key"]),
            "source": str(filing["source"]),
            "doc_id": str(filing["doc_id"]),
            "document_version": int(filing.get("document_version") or 1),
            "form": str(filing["form"]),
            "items": str(filing.get("items") or ""),
            "symbols": sorted({str(symbol).upper() for symbol in filing.get("symbols") or () if symbol}),
            "period_of_report": as_date(filing.get("period_of_report")),
            "filed_date": as_date(filing["filed_date"]),
            "accepted_at": utc_instant(filing["accepted_at"]),
            "accepted_source": str(filing["accepted_source"]),
            "json_accepted_raw": str(filing["json_accepted_raw"]) if filing.get("json_accepted_raw") else None,
            "header_sha256": str(filing["header_sha256"]) if filing.get("header_sha256") else None,
        }

    def register_filings(self, filings: Sequence[Mapping[str, Any]]) -> int:
        """Append the documents not registered yet; a document already registered keeps its first row (its acceptance
        clock never moves)."""
        checked = [self._checked_filing(filing) for filing in filings]
        if not checked:
            return 0
        if not self.database.database_url:
            store: list[dict[str, Any]] = self.database._statement_filings  # type: ignore[attr-defined]
            existing = {(row["market"], row["source"], row["doc_id"], row["document_version"]) for row in store}
            written = 0
            for row in checked:
                key = (row["market"], row["source"], row["doc_id"], row["document_version"])
                if key in existing:
                    continue
                existing.add(key)
                store.append({**row, "first_seen_at": datetime.now(timezone.utc)})
                written += 1
            return written
        written = 0
        with self.database.connection() as connection:
            for row in checked:
                cursor = connection.execute(
                    """
                    INSERT INTO statement_filings
                        (id, market, issuer_key, source, doc_id, document_version, form, items, symbols, period_of_report,
                         filed_date, accepted_at, accepted_source, json_accepted_raw, header_sha256)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT ON CONSTRAINT statement_filings_natural_key DO NOTHING
                    """,
                    (row["id"], row["market"], row["issuer_key"], row["source"], row["doc_id"], row["document_version"], row["form"],
                     row["items"], row["symbols"], row["period_of_report"], row["filed_date"], row["accepted_at"], row["accepted_source"],
                     row["json_accepted_raw"], row["header_sha256"]),
                )
                written += max(0, cursor.rowcount or 0)
            connection.commit()
        return written

    def filings(
        self,
        market: str,
        *,
        source: str | None = None,
        issuer_key: str | None = None,
        doc_ids: Iterable[str] | None = None,
        accepted_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Registered documents, oldest acceptance first."""
        wanted = {str(doc_id) for doc_id in doc_ids} if doc_ids is not None else None
        if wanted is not None and not wanted:
            return []
        since = utc_instant(accepted_since) if accepted_since is not None else None
        if not self.database.database_url:
            rows = [
                dict(row) for row in self.database._statement_filings  # type: ignore[attr-defined]
                if row["market"] == market
                and (source is None or row["source"] == source)
                and (issuer_key is None or row["issuer_key"] == issuer_key)
                and (wanted is None or row["doc_id"] in wanted)
                and (since is None or row["accepted_at"] >= since)
            ]
            return sorted(rows, key=lambda row: (row["accepted_at"], row["doc_id"]))
        clauses = ["market = %s"]
        arguments: list[Any] = [market]
        if source is not None:
            clauses.append("source = %s")
            arguments.append(source)
        if issuer_key is not None:
            clauses.append("issuer_key = %s")
            arguments.append(issuer_key)
        if wanted is not None:
            clauses.append("doc_id = ANY(%s)")
            arguments.append(sorted(wanted))
        if since is not None:
            clauses.append("accepted_at >= %s")
            arguments.append(since)
        with self.database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT id::text, market, issuer_key, source, doc_id, document_version, form, items, symbols, period_of_report,
                       filed_date, accepted_at, accepted_source, json_accepted_raw, header_sha256, first_seen_at
                FROM statement_filings
                WHERE {' AND '.join(clauses)}
                ORDER BY accepted_at, doc_id
                """,
                arguments,
            ).fetchall()
        return [{**dict(zip(_FILING_KEYS, row)), "symbols": list(row[8] or [])} for row in rows]

    def filing_acceptances(self, market: str, doc_ids: Iterable[str], *, source: str | None = None) -> dict[str, datetime]:
        """doc_id → the registered acceptance instant (UTC)."""
        return {row["doc_id"]: utc_instant(row["accepted_at"]) for row in self.filings(market, source=source, doc_ids=doc_ids)}

    def symbol_issuers(self, market: str, *, source: str | None = None) -> dict[str, str]:
        """symbol → issuer_key, from the tickers each registered document was detected under (the latest acceptance wins
        when a ticker moved to another issuer)."""
        if not self.database.database_url:
            output: dict[str, str] = {}
            for row in self.filings(market, source=source):  # oldest first: a later registration overrides
                for symbol in row.get("symbols") or ():
                    output[str(symbol).upper()] = row["issuer_key"]
            return output
        clauses = ["market = %s"]
        arguments: list[Any] = [market]
        if source is not None:
            clauses.append("source = %s")
            arguments.append(source)
        with self.database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT DISTINCT ON (symbol) symbol, issuer_key
                FROM (SELECT unnest(symbols) AS symbol, issuer_key, accepted_at FROM statement_filings
                      WHERE {' AND '.join(clauses)}) AS mapped
                ORDER BY symbol, accepted_at DESC
                """,
                arguments,
            ).fetchall()
        return {str(row[0]).upper(): str(row[1]) for row in rows}

    # -- vintages ------------------------------------------------------------------------------------------------------

    @staticmethod
    def _checked_vintage(row: Mapping[str, Any]) -> dict[str, Any]:
        missing = [key for key in _VINTAGE_REQUIRED if row.get(key) in (None, "")]
        if missing:
            raise ValueError(f"statement vintage {row.get('doc_id')!r} {row.get('concept')!r} lacks {', '.join(missing)}")
        if row["market"] not in MARKETS:
            raise ValueError(f"statement vintage {row['doc_id']!r} has market {row['market']!r}")
        start, end = as_date(row.get("period_start")), as_date(row["period_end"])
        if start is not None and end is not None and start > end:
            raise ValueError(f"statement vintage {row['doc_id']!r} {row['concept']!r} starts after it ends ({start} > {end})")
        checked = {
            "market": str(row["market"]),
            "issuer_key": str(row["issuer_key"]),
            "source": str(row["source"]),
            "doc_id": str(row["doc_id"]),
            "document_version": int(row.get("document_version") or 1),
            "form": str(row["form"]),
            "fiscal_year": int(row["fiscal_year"]) if row.get("fiscal_year") is not None else None,
            "fiscal_period": str(row["fiscal_period"]) if row.get("fiscal_period") else None,
            "period_start": start,
            "period_end": end,
            "concept": str(row["concept"]),
            "unit": str(row["unit"]),
            "value": Decimal(canonical_value(row["value"])),
            "filed_date": as_date(row["filed_date"]),
            "accepted_at": utc_instant(row["accepted_at"]),
        }
        checked["row_hash"] = vintage_row_hash(checked)
        return checked

    def insert_vintages(self, market: str, issuer_key: str, rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
        """Append one issuer's facts, deciding ``is_first_publication`` against every stored row of the same identity.
        Returns ``{"attempted", "written", "first_publications", "out_of_order"}``."""
        checked = [self._checked_vintage(row) for row in rows]
        foreign = [row for row in checked if row["market"] != market or row["issuer_key"] != issuer_key]
        if foreign:
            raise ValueError(f"insert_vintages({market}, {issuer_key}) received {len(foreign)} rows of another issuer")
        counts = {"attempted": len(checked), "written": 0, "first_publications": 0, "out_of_order": 0}
        if not checked:
            return counts
        checked.sort(key=lambda row: (row["accepted_at"], row["doc_id"], row["concept"], _iso(row["period_start"]) or "", row["period_end"]))
        if not self.database.database_url:
            store: list[dict[str, Any]] = self.database._statement_vintages  # type: ignore[attr-defined]
            stored = [row for row in store if row["market"] == market and row["issuer_key"] == issuer_key]
            earliest = self._earliest_by_identity(stored)
            existing_keys = {_natural_key(row) for row in stored}
            for row in self._flagged(checked, earliest, existing_keys, counts):
                store.append({**row, "id": str(uuid4()), "first_seen_at": datetime.now(timezone.utc)})
                counts["written"] += 1
            return counts
        with self.database.connection() as connection:
            # one writer per issuer: the flags are decided against what is stored, so two writers must never interleave
            connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"statement_vintages:{market}:{issuer_key}",))
            concepts = sorted({row["concept"] for row in checked})
            stored_rows = connection.execute(
                """
                SELECT market, issuer_key, source, concept, unit, period_start, period_end, doc_id, document_version, accepted_at
                FROM statement_vintages
                WHERE market = %s AND issuer_key = %s AND concept = ANY(%s)
                """,
                (market, issuer_key, concepts),
            ).fetchall()
            stored = [dict(zip(("market", "issuer_key", "source", "concept", "unit", "period_start", "period_end", "doc_id",
                                "document_version", "accepted_at"), row)) for row in stored_rows]
            earliest = self._earliest_by_identity(stored)
            existing_keys = {_natural_key(row) for row in stored}
            flagged = list(self._flagged(checked, earliest, existing_keys, counts))
            with connection.cursor() as cursor:
                for start in range(0, len(flagged), VINTAGE_BATCH):
                    chunk = flagged[start:start + VINTAGE_BATCH]
                    cursor.executemany(
                        """
                        INSERT INTO statement_vintages
                            (id, market, issuer_key, source, doc_id, document_version, form, fiscal_year, fiscal_period,
                             period_start, period_end, concept, unit, value, filed_date, accepted_at, is_first_publication, row_hash)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT ON CONSTRAINT statement_vintages_natural_key DO NOTHING
                        """,
                        [(str(uuid4()), row["market"], row["issuer_key"], row["source"], row["doc_id"], row["document_version"], row["form"],
                          row["fiscal_year"], row["fiscal_period"], row["period_start"], row["period_end"], row["concept"], row["unit"],
                          row["value"], row["filed_date"], row["accepted_at"], row["is_first_publication"], row["row_hash"])
                         for row in chunk],
                    )
                    counts["written"] += cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
            connection.commit()
        return counts

    @staticmethod
    def _earliest_by_identity(stored: Iterable[Mapping[str, Any]]) -> dict[FactIdentity, datetime]:
        earliest: dict[FactIdentity, datetime] = {}
        for row in stored:
            identity = fact_identity(row)
            accepted = utc_instant(row["accepted_at"])
            if identity not in earliest or accepted < earliest[identity]:
                earliest[identity] = accepted
        return earliest

    @staticmethod
    def _flagged(
        checked: list[dict[str, Any]],
        earliest: dict[FactIdentity, datetime],
        existing_keys: set[tuple[Any, ...]],
        counts: dict[str, int],
    ) -> Iterable[dict[str, Any]]:
        """Rows to write (sorted by acceptance), each with its first-publication flag; a row already stored (same natural
        key) or repeated in the batch is skipped exactly like ON CONFLICT DO NOTHING."""
        for row in checked:
            key = _natural_key(row)
            if key in existing_keys:
                continue
            existing_keys.add(key)
            identity = fact_identity(row)
            prior = earliest.get(identity)
            first = prior is None or row["accepted_at"] < prior
            if first and prior is not None:
                counts["out_of_order"] += 1
                logger.warning("statement_vintages: %s %s %s arrived after a later-accepted publication of the same fact",
                               row["issuer_key"], row["doc_id"], row["concept"])
            if prior is None or row["accepted_at"] < prior:
                earliest[identity] = row["accepted_at"]
            counts["first_publications"] += int(first)
            yield {**row, "is_first_publication": first}

    def vintages(
        self,
        market: str,
        issuer_key: str,
        *,
        accepted_at_or_before: datetime | None = None,
        concepts: Iterable[str] | None = None,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        """One issuer's stored facts, oldest acceptance first, ``value`` as ``Decimal``; ``accepted_at_or_before`` is the
        point-in-time cut (a fact accepted after it does not exist for that reader)."""
        cut = utc_instant(accepted_at_or_before) if accepted_at_or_before is not None else None
        wanted = sorted({str(concept) for concept in concepts}) if concepts is not None else None
        if wanted is not None and not wanted:
            return []
        if not self.database.database_url:
            rows = [
                dict(row) for row in self.database._statement_vintages  # type: ignore[attr-defined]
                if row["market"] == market and row["issuer_key"] == issuer_key
                and (cut is None or row["accepted_at"] <= cut)
                and (wanted is None or row["concept"] in wanted)
                and (source is None or row["source"] == source)
            ]
            return sorted(rows, key=lambda row: (row["accepted_at"], row["doc_id"], row["concept"]))
        clauses = ["market = %s", "issuer_key = %s"]
        arguments: list[Any] = [market, issuer_key]
        if cut is not None:
            clauses.append("accepted_at <= %s")
            arguments.append(cut)
        if wanted is not None:
            clauses.append("concept = ANY(%s)")
            arguments.append(wanted)
        if source is not None:
            clauses.append("source = %s")
            arguments.append(source)
        with self.database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT id::text, market, issuer_key, source, doc_id, document_version, form, fiscal_year, fiscal_period,
                       period_start, period_end, concept, unit, value, filed_date, accepted_at, first_seen_at,
                       is_first_publication, row_hash
                FROM statement_vintages
                WHERE {' AND '.join(clauses)}
                ORDER BY accepted_at, doc_id, concept
                """,
                arguments,
            ).fetchall()
        return [dict(zip(_VINTAGE_KEYS, row)) for row in rows]

    def documents_with_vintages(self, market: str, issuer_key: str) -> set[str]:
        """The doc_ids of one issuer that already have at least one stored fact."""
        if not self.database.database_url:
            return {
                row["doc_id"] for row in self.database._statement_vintages  # type: ignore[attr-defined]
                if row["market"] == market and row["issuer_key"] == issuer_key
            }
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT DISTINCT doc_id FROM statement_vintages WHERE market = %s AND issuer_key = %s",
                (market, issuer_key),
            ).fetchall()
        return {str(row[0]) for row in rows}

    def issuers_with_vintages(self, market: str) -> set[str]:
        if not self.database.database_url:
            return {row["issuer_key"] for row in self.database._statement_vintages if row["market"] == market}  # type: ignore[attr-defined]
        with self.database.connection() as connection:
            rows = connection.execute("SELECT DISTINCT issuer_key FROM statement_vintages WHERE market = %s", (market,)).fetchall()
        return {str(row[0]) for row in rows}
