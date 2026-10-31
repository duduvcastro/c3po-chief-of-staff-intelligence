"""The as-filed statements frozen per section (PREREG_VALUATION_ENSEMBLE_PIT_US_V1 rev 2 §2).

Each section of the new epoch reads the as-filed store cut at its V3 snapshot's ``published_at`` (its write cut): only the
rows of ``statement_vintages`` and ``statement_filings`` whose ``first_seen_at`` is at or before the cut (both tables only
take inserts; ``first_seen_at`` is the database's ``now()`` at the inserting transaction's start). On that cut store the
rev3 reader's rules hold: the symbol -> issuer map takes the latest acceptance among the documents written by the cut, an
issuer is covered once a fact of any source was written by the cut, and the facts are the reader's own (accepted at or
before T, the reader's checks) written by the cut. A symbol whose latest acceptance ties between two issuers (the store's
SQL picks one arbitrarily) is not covered: it is ``ambiguous``.

``check_section_statements`` is the section's statements check of rev 2 §2, name by name over its admitted Stocks
(``admitted_names``, then ``compare_reference`` per covered name), run by the executor before ``compute_grid_section``,
whose own comparison (the rev 1 one) still runs on the same facts and agrees. The read-only readiness run before the pin
is signed (``valuation_ensemble_readiness``) runs the same steps. ``valuation_ensemble_grid.py`` stays byte-identical to the
rev 1 pin: the live producer reads it under that owner-signed pin.

A counterfactual rule, not rev3's historical read (unknown): the read-only preflight of #527 (run 41232203835) showed it
reproduces rev3's references in all 534 sections; every section still compares every name and refuses a difference.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping

from . import valuation_pit_rerun as pit
from .valuation_ensemble_inputs import utc


class FrozenIndex:
    """What every section's cut reads, loaded once (a chunk): each symbol's registered documents (written, accepted,
    issuer) and each issuer's first write of a fact of any source."""

    def __init__(self, filings: dict[str, list[tuple[datetime, datetime, str]]], first_write: dict[str, datetime]):
        self.filings = filings
        self.first_write = first_write

    @classmethod
    def load(cls, database: Any) -> "FrozenIndex":
        front, why = pit.as_filed_front()
        if front is None:
            raise ValueError("ensemble_frozen_statements_front_missing")
        store = front.StatementVintageStore(database)
        filings: dict[str, list[tuple[datetime, datetime, str]]] = {}
        for row in store.filings(front.MARKET, source=front.FILING_SOURCE):
            for symbol in row.get("symbols") or ():
                filings.setdefault(str(symbol).upper().strip(), []).append(
                    (utc(row["first_seen_at"]), utc(row["accepted_at"]), str(row["issuer_key"])))
        return cls(filings, _first_writes(database, front.MARKET))

    def issuers_at(self, symbol: str, cut: datetime) -> frozenset[str]:
        """The issuers of the latest acceptance among ``symbol``'s documents written by ``cut``: one is the store's symbol
        map; two or more are a tie the store's SQL breaks arbitrarily (``DISTINCT ON``); none, an unmapped symbol."""
        best: datetime | None = None
        issuers: set[str] = set()
        for written, accepted, owner in self.filings.get(symbol, ()):
            if written > cut:
                continue
            if best is None or accepted > best:
                best, issuers = accepted, {owner}
            elif accepted == best:
                issuers.add(owner)
        return frozenset(issuers)


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


def written_by(rows: Iterable[dict[str, Any]], written_until: datetime, refused: Counter[str]) -> list[dict[str, Any]]:
    """The reader's facts written by the cut: a fact without a zoned ``first_seen_at`` is counted, never read."""
    kept: list[dict[str, Any]] = []
    for row in rows:
        seen = row.get("first_seen_at")
        if not isinstance(seen, datetime) or seen.utcoffset() is None:
            refused["statement_vintages:fact_without_a_zoned_write"] += 1
        elif utc(seen) <= written_until:
            kept.append(row)
    return kept


class FrozenAsFiledReader(pit.AsFiledReader):
    """``valuation_pit_rerun.AsFiledReader`` on the store cut at ``written_until`` (rev 2 §2), for ONE section. ``index``
    is the chunk's FrozenIndex, or a callable that loads it the first time a section reads the store (shared by the
    chunk's sections). An issuer's facts at T are read once for the reader's life: the statements check and the grid's
    own read share the same rows (neither changes them), the reader's refusal counts given to each caller."""

    def __init__(self, database: Any, *, written_until: datetime, index: "FrozenIndex | Callable[[], FrozenIndex]") -> None:
        super().__init__(database)
        if not isinstance(written_until, datetime) or written_until.utcoffset() is None:
            raise ValueError("ensemble_statements_cut_missing")
        self.written_until = utc(written_until)
        self._index = index
        self._read: dict[tuple[str, datetime], tuple[list[dict[str, Any]], Counter[str]]] = {}

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
            issuers = self.index.issuers_at(symbol, self.written_until)
            if len(issuers) == 1:
                (issuer,) = issuers
                first = self.index.first_write.get(issuer)
                if first is not None and first <= self.written_until:
                    out[symbol] = issuer
        return out

    def ambiguous(self, market: str) -> frozenset[str]:
        """The symbols whose latest acceptance written by the cut ties between two issuers: never in ``coverage``."""
        if market == "B3" or not self.present():
            return frozenset()
        return frozenset(symbol for symbol in self.index.filings if len(self.index.issuers_at(symbol, self.written_until)) > 1)

    def facts(self, issuer_key: str, *, as_of: datetime, refused: Counter[str]) -> list[dict[str, Any]]:
        key = (issuer_key, utc(as_of))
        if key not in self._read:
            counted: Counter[str] = Counter()
            self._read[key] = (written_by(super().facts(issuer_key, as_of=as_of, refused=counted), self.written_until, counted), counted)
        kept, counted = self._read[key]
        refused.update(counted)
        return kept


@dataclass(frozen=True)
class AdmittedName:
    """An admitted Stock of a section: its issuer at the cut (None: not covered) and the references both rev3 runs
    recorded for it (V3 and the served sibling)."""
    symbol: str
    issuer: str | None
    expected: dict[str, Any] | None
    other_expected: dict[str, Any] | None


def admitted_names(database: Any, *, market: str, as_of: datetime, v3_snapshot: Mapping[str, Any],
                   served_snapshot: Mapping[str, Any], reader: pit.AsFiledReader,
                   before_read: Callable[[], None] | None = None) -> list[AdmittedName]:
    """A section's admitted Stocks (the pinned catalogue's Stocks with inputs in rev3's screen), in catalogue order, with
    the issuer the reader maps each to. First the siblings' pairing, as the grid checks it (``paired_source_identity``:
    statement references the two rev3 runs record differently refuse, ``rev3_siblings_statement_references_mismatch``).
    Refused, ``statements_table_not_stable``: a symbol whose latest acceptance ties between two issuers (a
    ``FrozenAsFiledReader``; any other reader shows none, the rev 1 read), and a name rev3 recorded a reference for that
    the store does not cover."""
    from . import valuation_pit_served as served
    from .valuation_ensemble_grid import (GridInputError, _guarded, _mapping, _read_snapshot, _role, _snapshot_manifest,
                                          paired_source_identity)

    cut = utc(as_of)
    paired_source_identity(v3_snapshot, served_snapshot)
    v3 = _snapshot_manifest(v3_snapshot, analysis=pit.ANALYSIS_TYPE, market=market, as_of=cut)
    sibling = _snapshot_manifest(served_snapshot, analysis=served.ANALYSIS_TYPE, market=market, as_of=cut)
    screen_inputs = _mapping(_mapping(v3_snapshot.get("outputs")).get("screen"))
    cat_pin = _mapping(_mapping(v3_snapshot.get("inputs")).get("catalogue_pin"))
    if not cat_pin.get("resolved_snapshot_id"):
        raise GridInputError("rev3_catalogue_pin_missing_or_mismatched")
    catalogue = pit.admitted_catalogue(_read_snapshot(database, str(cat_pin["resolved_snapshot_id"]), analysis=pit.CATALOGUE_ANALYSIS_TYPE,
                                                      entity=f"{market}_UNIVERSE", before_read=before_read))
    if not _guarded(reader.present, before_read):
        raise GridInputError("statement_vintages_unavailable")
    coverage = _guarded(lambda: reader.coverage(market), before_read)
    ambiguous = _guarded(lambda: reader.ambiguous(market), before_read) if isinstance(reader, FrozenAsFiledReader) else frozenset()
    names: list[AdmittedName] = []
    for row in catalogue:
        symbol = str(row["symbol"])
        if row.get("security_type") != "Stock" or symbol not in screen_inputs:
            continue
        name = AdmittedName(symbol, coverage.get(symbol) or None, _role(v3, pit.BASIS_VINTAGES, symbol=symbol),
                            _role(sibling, pit.BASIS_VINTAGES, symbol=symbol))
        if symbol in ambiguous or (name.issuer is None and (name.expected is not None or name.other_expected is not None)):
            raise GridInputError("statements_table_not_stable")
        names.append(name)
    return names


def compare_reference(raw: list[dict[str, Any]], *, name: AdmittedName, market: str, front: Any) -> None:
    """A covered name's reference recomputed from its facts against rev3's: ``rev3_statement_source_reference_missing_or_
    mismatched`` without the reference both siblings agree on, ``statements_table_not_stable`` when it differs (the grid's
    own comparison)."""
    from .valuation_ensemble_grid import GridInputError

    _, reference = pit.as_filed_payload(raw, market=market, front=front)
    expected = name.expected
    if expected is None or name.other_expected is None or expected != name.other_expected:
        raise GridInputError("rev3_statement_source_reference_missing_or_mismatched")
    if any(expected.get(key) != reference.get(key) for key in reference):
        raise GridInputError("statements_table_not_stable")


def check_section_statements(database: Any, *, market: str, as_of: datetime, v3_snapshot: Mapping[str, Any],
                             served_snapshot: Mapping[str, Any], reader: pit.AsFiledReader,
                             before_read: Callable[[], None] | None = None) -> dict[str, int]:
    """PREREG rev 2 §2 over a section's admitted Stocks, before anything is computed: ``admitted_names`` (ties, names
    rev3 read that the store does not cover), then ``compare_reference`` for every covered name, in catalogue order; a
    name neither rev3 nor the store read is counted, not evaluable. Returns the counts (``compared``, ``not_evaluable``)."""
    from .valuation_ensemble_grid import _guarded

    cut = utc(as_of)
    counts: Counter[str] = Counter({"compared": 0, "not_evaluable": 0})
    for name in admitted_names(database, market=market, as_of=cut, v3_snapshot=v3_snapshot, served_snapshot=served_snapshot,
                               reader=reader, before_read=before_read):
        issuer = name.issuer
        if issuer is None:
            counts["not_evaluable"] += 1
            continue
        raw = _guarded(lambda key=issuer: reader.facts(key, as_of=cut, refused=Counter()), before_read)
        compare_reference(raw, name=name, market=market, front=reader.front)
        counts["compared"] += 1
    return dict(counts)
