"""The as-filed statements frozen per section (PREREG_VALUATION_ENSEMBLE_PIT_US_V1 rev 2 §2).

Each section of the new epoch reads the as-filed store cut at its V3 snapshot's ``published_at``: only the rows of
``statement_vintages`` and ``statement_filings`` whose ``first_seen_at`` is at or before the cut (both tables only take
inserts; ``first_seen_at`` is the database's ``now()`` at the inserting transaction's start). On that cut store the rev3
reader's rules hold: the symbol -> issuer map takes the latest acceptance among the documents written by the cut (a tie
between two issuers, which the store's SQL leaves arbitrary, goes to the larger doc_id: deterministic, and any
difference from rev3 is refused by the grid's comparison), an issuer is covered once a fact of any source was written by
the cut, and the facts are the reader's own (accepted at or before T, the reader's checks) written by the cut.

A counterfactual rule, not rev3's historical read (unknown): the read-only preflight of #527 (run 41232203835) showed it
reproduces rev3's references in all 534 sections; the grid still compares every reference and refuses a difference.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Callable

from . import valuation_pit_rerun as pit
from .valuation_ensemble_inputs import utc


class FrozenIndex:
    """What every section's cut reads, loaded once (a chunk): each symbol's registered documents (written, accepted,
    doc_id, issuer) and each issuer's first write of a fact of any source."""

    def __init__(self, filings: dict[str, list[tuple[datetime, datetime, str, str]]], first_write: dict[str, datetime]):
        self.filings = filings
        self.first_write = first_write

    @classmethod
    def load(cls, database: Any) -> "FrozenIndex":
        front, why = pit.as_filed_front()
        if front is None:
            raise ValueError("ensemble_frozen_statements_front_missing")
        store = front.StatementVintageStore(database)
        filings: dict[str, list[tuple[datetime, datetime, str, str]]] = {}
        for row in store.filings(front.MARKET, source=front.FILING_SOURCE):
            for symbol in row.get("symbols") or ():
                filings.setdefault(str(symbol).upper().strip(), []).append(
                    (utc(row["first_seen_at"]), utc(row["accepted_at"]), str(row["doc_id"]), str(row["issuer_key"])))
        return cls(filings, _first_writes(database, front.MARKET))

    def issuer_at(self, symbol: str, cut: datetime) -> str | None:
        """The issuer the store's symbol map names over the documents written by ``cut``: the latest acceptance, then the
        larger doc_id."""
        best: tuple[datetime, str] | None = None
        issuer: str | None = None
        for written, accepted, doc_id, owner in self.filings.get(symbol, ()):
            if written <= cut and (best is None or (accepted, doc_id) > best):
                best, issuer = (accepted, doc_id), owner
        return issuer


def _first_writes(database: Any, market: str) -> dict[str, datetime]:
    """issuer -> the first ``first_seen_at`` of any of its facts (any source): ``issuers_with_vintages`` at a cut."""
    if not database.database_url:
        first: dict[str, datetime] = {}
        for row in getattr(database, "_statement_vintages", []):
            if row["market"] == market:
                seen = utc(row["first_seen_at"])
                if row["issuer_key"] not in first or seen < first[row["issuer_key"]]:
                    first[row["issuer_key"]] = seen
        return first
    with database.connection() as connection:
        rows = connection.execute("SELECT issuer_key, MIN(first_seen_at) FROM statement_vintages WHERE market = %s GROUP BY issuer_key",
                                  (market,)).fetchall()
    return {str(row[0]): utc(row[1]) for row in rows}


class FrozenAsFiledReader(pit.AsFiledReader):
    """``valuation_pit_rerun.AsFiledReader`` on the store cut at ``written_until`` (rev 2 §2). ``index`` is the chunk's
    FrozenIndex, or a callable that loads it the first time a section reads the store (shared by the chunk's sections)."""

    def __init__(self, database: Any, *, written_until: datetime, index: "FrozenIndex | Callable[[], FrozenIndex]") -> None:
        super().__init__(database)
        if not isinstance(written_until, datetime) or written_until.utcoffset() is None:
            raise ValueError("ensemble_statements_cut_missing")
        self.written_until = utc(written_until)
        self._index = index

    @property
    def index(self) -> FrozenIndex:
        if not isinstance(self._index, FrozenIndex):
            self._index = self._index()
        return self._index

    def coverage(self, market: str) -> dict[str, str]:
        if not self.present():
            return {}
        if market == "B3":
            return super().coverage(market)  # the reader's own refusal of CVM facts, or nothing
        out: dict[str, str] = {}
        for symbol in self.index.filings:
            issuer = self.index.issuer_at(symbol, self.written_until)
            first = self.index.first_write.get(issuer) if issuer else None
            if issuer and first is not None and first <= self.written_until:
                out[symbol] = issuer
        return out

    def facts(self, issuer_key: str, *, as_of: datetime, refused: Counter[str]) -> list[dict[str, Any]]:
        kept: list[dict[str, Any]] = []
        for row in super().facts(issuer_key, as_of=as_of, refused=refused):
            seen = row.get("first_seen_at")
            if not isinstance(seen, datetime) or seen.utcoffset() is None:
                refused["statement_vintages:fact_without_a_zoned_write"] += 1
            elif utc(seen) <= self.written_until:
                kept.append(row)
        return kept
