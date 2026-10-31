"""Read-only preflight of the Valuation ensemble grid's statements (owner 31/10/2026, the new epoch: "Sim, começar").

The grid (PREREG_VALUATION_ENSEMBLE_PIT_US_V1) recomputes, in every section (exchange, T), each admitted Stock's as-filed
reference (``valuation_pit_rerun.as_filed_payload`` over the facts accepted at or before T) and refuses the section,
``statements_table_not_stable``, unless it equals the reference the signed rev3 run recorded. On 30/10 a section refused
for good: a fact accepted before its T was written after rev3 read the store, and the grid cannot complete. Codex
(6537212289): excluding sections is NO-GO; a new epoch with its own protocol may change the statements basis.

This counts, for every section of the rev3 manifest (stdin), whether each reference recomputes to rev3's:
  now       the store as it is (the grid's own read);
  at_rev3   the store as it stood when rev3 persisted that section: the facts and the filings whose ``first_seen_at``
            (the database's clock at insert; both tables only take inserts) is at or before the V3 snapshot's
            ``published_at`` — the frozen basis a new epoch could read without copying the tables.
Per admitted Stock (a catalogue Stock in rev3's screen) and basis: "match"; "refused:<keys>" (covered, the reference
differs: the grid refuses the section, statements_table_not_stable); "refused:rev3_reference_missing" (covered, rev3 has
no reference both siblings agree on: the grid refuses); "skipped:rev3_read_it" (not covered, but rev3 read it: the grid
skips it and the inputs deviate from rev3's); "skipped:rev3_neither". A section is refused, else deviating, else stable.

Counts only (the repository is public): no symbol, issuer, value or error text; sections by their market and session.

    docker compose exec -T -e PGOPTIONS='-c default_transaction_read_only=on' api python -m app.valuation_grid_preflight < rev3.json
"""
from __future__ import annotations

import argparse
import bisect
import json
import sys
from collections import Counter
from datetime import datetime
from typing import Any, Iterable, Mapping

from . import valuation_ensemble_executor as exe
from . import valuation_ensemble_grid as grid
from . import valuation_pit_rerun as pit
from . import valuation_pit_served as served
from .valuation_ensemble_driver import read_rev3

BASES = ("now", "at_rev3")
REFERENCE_KEYS = ("facts", "facts_superseded_by_T", "rows", "quarters_derived", "statements_sha256")


def _utc(value: Any) -> datetime:
    instant = grid._instant(value)
    if instant is None:
        raise ValueError("preflight_instant_missing")
    return instant


def symbol_map(filings: Iterable[Mapping[str, Any]], *, written_until: datetime | None) -> dict[str, str]:
    """symbol → issuer as ``StatementVintageStore.symbol_issuers`` maps it (the latest acceptance wins), over the filings
    written at or before ``written_until`` (all of them when None)."""
    mapped: dict[str, tuple[datetime, str]] = {}
    for row in filings:
        if written_until is not None and _utc(row["first_seen_at"]) > written_until:
            continue
        accepted = _utc(row["accepted_at"])
        for symbol in row.get("symbols") or ():
            key = str(symbol).strip().upper()
            if key not in mapped or accepted >= mapped[key][0]:
                mapped[key] = (accepted, str(row["issuer_key"]))
    return {symbol: issuer for symbol, (_, issuer) in mapped.items()}


def section_plan(database: Any, v3_entry: Mapping[str, Any], served_entry: Mapping[str, Any],
                 catalogues: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """One section's T, its rev3 write instant and the (symbol, rev3 reference) pairs the grid compares there: Stocks of
    the pinned catalogue that rev3 admitted to its screen and gave a statements reference (the same pair in both siblings)."""
    market, cut = str(v3_entry["market"]), _utc(v3_entry["as_of"])
    v3_snapshot, served_snapshot = exe._snapshot(database, v3_entry), exe._snapshot(database, served_entry)
    v3 = grid._snapshot_manifest(v3_snapshot, analysis=pit.ANALYSIS_TYPE, market=market, as_of=cut)
    sibling = grid._snapshot_manifest(served_snapshot, analysis=served.ANALYSIS_TYPE, market=market, as_of=cut)
    screen = grid._mapping(grid._mapping(v3_snapshot.get("outputs")).get("screen"))
    cat_id = str(grid._mapping(grid._mapping(v3_snapshot.get("inputs")).get("catalogue_pin")).get("resolved_snapshot_id") or "")
    if not cat_id:
        raise ValueError("preflight_catalogue_pin_missing")
    if cat_id not in catalogues:
        catalogues[cat_id] = pit.admitted_catalogue(grid._read_snapshot(database, cat_id, analysis=pit.CATALOGUE_ANALYSIS_TYPE,
                                                                        entity=f"{market}_UNIVERSE"))
    names: list[tuple[str, dict[str, Any] | None]] = []
    for row in catalogues[cat_id]:
        symbol = str(row["symbol"])
        if row.get("security_type") != "Stock" or symbol not in screen:
            continue
        expected, other = grid._role(v3, pit.BASIS_VINTAGES, symbol=symbol), grid._role(sibling, pit.BASIS_VINTAGES, symbol=symbol)
        names.append((symbol, expected if expected is not None and expected == other else None))
    return {"market": market, "session": str(v3_entry["session_date"]), "as_of": cut,
            "written": _utc(v3_snapshot["published_at"]), "names": names}


def run(database: Any, rev3: Mapping[str, Any]) -> dict[str, Any]:
    pairs = exe._reference_pairs(rev3)  # the complete, signed rev3 manifest (its digest) or a refusal
    front, _ = pit.as_filed_front()
    if front is None:
        raise ValueError("preflight_as_filed_front_missing")
    if not pit.AsFiledReader(database).present():
        raise ValueError("preflight_statement_vintages_unavailable")
    store = front.StatementVintageStore(database)
    catalogues: dict[str, list[dict[str, Any]]] = {}
    sections = [section_plan(database, v3_entry, served_entry, catalogues) for v3_entry, served_entry in pairs]
    filings = store.filings(front.MARKET, source=front.FILING_SOURCE)
    now_map = symbol_map(filings, written_until=None)
    earliest_write = min((section["written"] for section in sections), default=None)
    # who each (section, name) reads under each basis: the issuer the symbol map of that basis names (the grid's lookup)
    wanted: dict[str, list[tuple[int, int, str]]] = {}
    absent: dict[tuple[int, int, str], str] = {}
    for index, section in enumerate(sections):
        at_map = symbol_map(filings, written_until=section["written"])
        for position, (symbol, _) in enumerate(section["names"]):
            for basis, mapping in (("now", now_map), ("at_rev3", at_map)):
                issuer = mapping.get(symbol)
                if issuer:
                    wanted.setdefault(issuer, []).append((index, position, basis))
                else:
                    absent[(index, position, basis)] = "unmapped"
    outcome: dict[tuple[int, int, str], str] = {}
    for issuer, uses in sorted(wanted.items()):
        rows = store.vintages(front.MARKET, issuer, source=front.VINTAGE_SOURCE)  # every fact, oldest acceptance first
        accepted = [_utc(row["accepted_at"]) for row in rows]
        seen = [_utc(row["first_seen_at"]) for row in rows]
        if accepted != sorted(accepted):
            raise ValueError("preflight_store_order_unexpected")
        first_written = min(seen) if seen else None
        late = [i for i, instant in enumerate(seen) if earliest_write is not None and instant > earliest_write]
        references: dict[tuple[int, tuple[int, ...]], dict[str, Any]] = {}
        for index, position, basis in uses:
            section = sections[index]
            written = section["written"] if basis == "at_rev3" else None
            if first_written is None or (written is not None and first_written > written):
                outcome[(index, position, basis)] = "uncovered"  # no fact of the issuer in the store of that basis
                continue
            end = bisect.bisect_right(accepted, section["as_of"])
            excluded = () if written is None else tuple(i for i in late if i < end and seen[i] > written)
            key = (end, excluded)
            if key not in references:
                skip = set(excluded)
                references[key] = pit.as_filed_payload([rows[i] for i in range(end) if i not in skip],
                                                       market=section["market"], front=front)[1]
            expected = section["names"][position][1]
            if expected is None:
                outcome[(index, position, basis)] = "refused:rev3_reference_missing"
                continue
            differing = [name for name in REFERENCE_KEYS if expected.get(name) != references[key].get(name)]
            outcome[(index, position, basis)] = "match" if not differing else "refused:" + ",".join(differing)
    totals: dict[str, Any] = {"sections": len(sections), "names": sum(len(s["names"]) for s in sections),
                              "first_rev3_write": earliest_write.isoformat() if earliest_write else None,
                              "last_rev3_write": max(s["written"] for s in sections).isoformat() if sections else None}
    for basis in BASES:
        counts: Counter[str] = Counter()
        refused: list[str] = []
        deviating: list[str] = []
        for index, section in enumerate(sections):
            results = []
            for position, (_, expected) in enumerate(section["names"]):
                result = outcome.get((index, position, basis)) or absent.get((index, position, basis), "unmapped")
                if result in ("unmapped", "uncovered"):  # the grid skips the name; it deviates when rev3 had read it
                    result = "skipped:rev3_read_it" if expected is not None else "skipped:rev3_neither"
                results.append(result)
            counts.update(results)
            label = "%s %s" % (section["market"], section["session"])
            if any(result.startswith("refused:") for result in results):
                refused.append(label)
            elif any(result == "skipped:rev3_read_it" for result in results):
                deviating.append(label)
        totals[basis] = {"stable_sections": len(sections) - len(refused) - len(deviating),
                         "refused_sections": len(refused), "deviating_sections": len(deviating),
                         "first_refused": refused[0] if refused else None, "refused": refused, "deviating": deviating,
                         "names": dict(sorted(counts.items()))}
    return totals


def main(argv: list[str] | None = None, *, database: Any = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only preflight of the ensemble grid's statements (rev3 manifest on stdin); "
                                                 "counts only, never a symbol.")
    parser.parse_args(argv)
    from .valuation_accuracy_report import force_read_only_session

    force_read_only_session()
    if database is None:
        from .config import get_settings
        from .database import Database
        database = Database(get_settings())
    try:
        result = run(database, read_rev3(sys.stdin.buffer))
    except Exception as error:  # noqa: BLE001 - the type alone: a message could carry a name
        print(json.dumps({"kind": "refused", "reason": type(error).__name__ if not isinstance(error, ValueError) else str(error)[:80]},
                         sort_keys=True))
        return 2
    print(json.dumps({"kind": "preflight", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
