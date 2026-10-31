"""Read-only preflight of the Valuation ensemble grid's statements (owner 31/10/2026, the new epoch: "Sim, começar").

The grid (PREREG_VALUATION_ENSEMBLE_PIT_US_V1) recomputes, in every section (exchange, T), each admitted Stock's as-filed
reference (``valuation_pit_rerun.as_filed_payload`` over the facts accepted at or before T) and refuses the section,
``statements_table_not_stable``, unless it equals the reference the signed rev3 run recorded. On 30/10 a section refused
for good: a fact accepted before its T was written after rev3 read the store, and the grid cannot complete. Codex
(6537212289): excluding sections is NO-GO; a new epoch with its own protocol may change the statements basis.

This counts, for every section of the rev3 manifest (stdin), whether each reference recomputes to rev3's:
  now       the store as it is: the grid's own read (``AsFiledReader.coverage``/``facts``, the grid's comparison);
  at_rev3   the store as it stood when rev3 read it for that section — the facts and filings whose ``first_seen_at``
            (the database's ``now()`` at insert: the inserting transaction's START; both tables only take inserts) is at
            or before a cut. rev3 read between its previous section's persistence and this one's (its runs were
            serialised), so two cuts bracket the read: "hi", the V3 snapshot's ``published_at``, and "lo", the later of
            the previous section's ``published_at`` and ``published_at`` minus WINDOW. The same outcome at both cuts is
            the outcome; different ones are "window" (a row written inside rev3's own compute decides it).
Per admitted Stock (a catalogue Stock in rev3's screen) and basis: "match"; "refused:<keys>" (covered, the reference
differs: the grid refuses the section); "refused:rev3_reference_missing" (covered, rev3 has no reference both siblings
agree on: the grid refuses); "skipped:rev3_read_it" (not covered, but rev3 read it: the grid skips it, the inputs deviate
from rev3's); "skipped:rev3_neither"; "ambiguous_map" (two filings of the same acceptance map the symbol to different
issuers: the grid's SQL picks one arbitrarily); "window" (at_rev3 only). A section is refused, else window, else
deviating, else stable. The section checks that do not read the store (the siblings' pairing, the catalogue's hash) are
the grid's, not repeated here; a section whose rev3 snapshots cannot be read is "unreadable".

Counts only (the repository is public): no symbol, issuer, value or error text; sections by their market and session.

    docker compose exec -T -e PGOPTIONS='-c default_transaction_read_only=on' api python -m app.valuation_grid_preflight < rev3.json
"""
from __future__ import annotations

import argparse
import bisect
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping

from . import valuation_ensemble_executor as exe
from . import valuation_ensemble_grid as grid
from . import valuation_pit_rerun as pit
from . import valuation_pit_served as served
from .valuation_ensemble_driver import read_rev3

BASES = ("now", "at_rev3")
WINDOW = timedelta(minutes=15)  # the longest a rev3 section read before its persistence (~300 s each)
_CODE = re.compile(r"[a-z0-9_]{1,80}")
AMBIGUOUS = object()


def _utc(value: Any) -> datetime:
    instant = grid._instant(value)
    if instant is None:
        raise ValueError("preflight_instant_missing")
    return instant


def symbol_map(filings: Iterable[Mapping[str, Any]], *, written_until: datetime | None) -> dict[str, Any]:
    """symbol → issuer as ``StatementVintageStore.symbol_issuers`` maps it (the latest acceptance wins; the SQL's
    ``DISTINCT ON`` is arbitrary on a tie, so a tie between two issuers is AMBIGUOUS), over the filings written at or
    before ``written_until`` (all of them when None); keyed as ``AsFiledReader.coverage`` looks a symbol up."""
    latest: dict[str, tuple[datetime, set[str]]] = {}
    for row in filings:
        if written_until is not None and _utc(row["first_seen_at"]) > written_until:
            continue
        accepted = _utc(row["accepted_at"])
        for symbol in row.get("symbols") or ():
            key = str(symbol).upper()
            if key not in latest or accepted > latest[key][0]:
                latest[key] = (accepted, {str(row["issuer_key"])})
            elif accepted == latest[key][0]:
                latest[key][1].add(str(row["issuer_key"]))
    return {key.strip(): (next(iter(issuers)) if len(issuers) == 1 else AMBIGUOUS) for key, (_, issuers) in latest.items()}


def section_plan(database: Any, v3_entry: Mapping[str, Any], served_entry: Mapping[str, Any],
                 catalogues: dict[tuple[str, str], list[dict[str, Any]]]) -> dict[str, Any]:
    """One section's T, its rev3 write instant and the (symbol, rev3 reference) pairs the grid compares there: Stocks of
    the pinned catalogue that rev3 admitted to its screen, each with the statements reference both siblings agree on."""
    market, cut = str(v3_entry["market"]), _utc(v3_entry["as_of"])
    v3_snapshot, served_snapshot = exe._snapshot(database, v3_entry), exe._snapshot(database, served_entry)
    v3 = grid._snapshot_manifest(v3_snapshot, analysis=pit.ANALYSIS_TYPE, market=market, as_of=cut)
    sibling = grid._snapshot_manifest(served_snapshot, analysis=served.ANALYSIS_TYPE, market=market, as_of=cut)
    screen = grid._mapping(grid._mapping(v3_snapshot.get("outputs")).get("screen"))
    cat_id = str(grid._mapping(grid._mapping(v3_snapshot.get("inputs")).get("catalogue_pin")).get("resolved_snapshot_id") or "")
    if not cat_id:
        raise ValueError("preflight_catalogue_pin_missing")
    if (market, cat_id) not in catalogues:
        catalogues[(market, cat_id)] = pit.admitted_catalogue(grid._read_snapshot(database, cat_id, analysis=pit.CATALOGUE_ANALYSIS_TYPE,
                                                                                  entity=f"{market}_UNIVERSE"))
    names: list[tuple[str, dict[str, Any] | None]] = []
    for row in catalogues[(market, cat_id)]:
        symbol = str(row["symbol"])
        if row.get("security_type") != "Stock" or symbol not in screen:
            continue
        expected, other = grid._role(v3, pit.BASIS_VINTAGES, symbol=symbol), grid._role(sibling, pit.BASIS_VINTAGES, symbol=symbol)
        names.append((symbol, expected if expected is not None and expected == other else None))
    return {"market": market, "session": str(v3_entry["session_date"]), "as_of": cut,
            "written": _utc(v3_snapshot["published_at"]), "names": names}


def _label(section: Mapping[str, Any]) -> str:
    return "%s %s" % (section["market"], section["session"])


def run(database: Any, rev3: Mapping[str, Any]) -> dict[str, Any]:
    pairs = exe._reference_pairs(rev3)  # the complete, signed rev3 manifest (its digest) or a refusal
    front, _ = pit.as_filed_front()
    if front is None:
        raise ValueError("preflight_as_filed_front_missing")
    if not pit.AsFiledReader(database).present():
        raise ValueError("preflight_statement_vintages_unavailable")
    store = front.StatementVintageStore(database)
    catalogues: dict[tuple[str, str], list[dict[str, Any]]] = {}
    sections: list[dict[str, Any]] = []
    unreadable: list[str] = []
    for v3_entry, served_entry in pairs:
        try:
            sections.append(section_plan(database, v3_entry, served_entry, catalogues))
        except (ValueError, grid.GridInputError) as error:  # a rev3 snapshot the grid would refuse too: counted, not fatal
            code = str(error) if _CODE.fullmatch(str(error)) else type(error).__name__
            unreadable.append("%s %s" % (v3_entry.get("market"), v3_entry.get("session_date")) + "|" + code)
    # the read cuts: hi = this section's persistence, lo = the later of the previous persistence (rev3 ran its sections one
    # after the other) and hi - WINDOW
    ordered = sorted(range(len(sections)), key=lambda i: sections[i]["written"])
    for rank, index in enumerate(ordered):
        hi = sections[index]["written"]
        previous = sections[ordered[rank - 1]]["written"] if rank else None
        sections[index]["cuts"] = {"hi": hi, "lo": max(hi - WINDOW, previous) if previous is not None else hi - WINDOW}
    filings = store.filings(front.MARKET, source=front.FILING_SOURCE)
    now_map = symbol_map(filings, written_until=None)
    earliest = min((section["cuts"]["lo"] for section in sections), default=None)
    # who each (section, name) reads under each cut: the issuer the symbol map of that cut names (the grid's lookup)
    wanted: dict[str, list[tuple[int, int, str]]] = {}
    outcome: dict[tuple[int, int, str], str] = {}
    for index, section in enumerate(sections):
        maps = {"now": now_map, **{cut: symbol_map(filings, written_until=section["cuts"][cut]) for cut in ("hi", "lo")}}
        for position, (symbol, _) in enumerate(section["names"]):
            for cut, mapping in maps.items():
                issuer = mapping.get(symbol)
                if issuer is AMBIGUOUS:
                    outcome[(index, position, cut)] = "ambiguous_map"
                elif issuer:
                    wanted.setdefault(str(issuer), []).append((index, position, cut))
                else:
                    outcome[(index, position, cut)] = "uncovered"
    for issuer, uses in sorted(wanted.items()):
        rows = store.vintages(front.MARKET, issuer)  # every fact of every source, oldest acceptance first
        seen_any = [_utc(row["first_seen_at"]) for row in rows]  # coverage: a fact of ANY source (issuers_with_vintages)
        facts = [row for row in rows if row["source"] == front.VINTAGE_SOURCE]  # what the reader reads
        accepted = [_utc(row["accepted_at"]) for row in facts]
        seen = [_utc(row["first_seen_at"]) for row in facts]
        if accepted != sorted(accepted):
            raise ValueError("preflight_store_order_unexpected")
        first_written = min(seen_any) if seen_any else None
        late = [i for i, instant in enumerate(seen) if earliest is not None and instant > earliest]
        references: dict[tuple[int, tuple[int, ...]], dict[str, Any]] = {}
        for index, position, cut in uses:
            section = sections[index]
            written = section["cuts"][cut] if cut in ("hi", "lo") else None
            if first_written is None or (written is not None and first_written > written):
                outcome[(index, position, cut)] = "uncovered"
                continue
            end = bisect.bisect_right(accepted, section["as_of"])
            excluded = () if written is None else tuple(i for i in late if i < end and seen[i] > written)
            key = (end, excluded)
            if key not in references:
                skip = set(excluded)
                references[key] = pit.as_filed_payload([facts[i] for i in range(end) if i not in skip],
                                                       market=section["market"], front=front)[1]
            expected, reference = section["names"][position][1], references[key]
            if expected is None:
                outcome[(index, position, cut)] = "refused:rev3_reference_missing"
                continue
            differing = [name for name in reference if expected.get(name) != reference.get(name)]  # the grid's comparison
            outcome[(index, position, cut)] = "match" if not differing else "refused:" + ",".join(differing)

    def result_of(index: int, position: int, cut: str) -> str:
        found = outcome.get((index, position, cut), "uncovered")
        if found == "uncovered":  # the grid skips the name; it deviates from rev3 when rev3 had read it
            return "skipped:rev3_read_it" if sections[index]["names"][position][1] is not None else "skipped:rev3_neither"
        return found

    labels = [label.split("|")[0] for label in unreadable]
    totals: dict[str, Any] = {"sections": len(sections) + len(unreadable), "names": sum(len(s["names"]) for s in sections),
                              "unreadable_sections": len(unreadable),
                              "first_rev3_write": min(s["written"] for s in sections).isoformat() if sections else None,
                              "last_rev3_write": max(s["written"] for s in sections).isoformat() if sections else None}
    for basis in BASES:
        counts: Counter[str] = Counter()
        groups: dict[str, list[str]] = {"refused": [], "window": [], "deviating": []}
        for index, section in enumerate(sections):
            results = []
            for position in range(len(section["names"])):
                if basis == "now":
                    results.append(result_of(index, position, "now"))
                else:
                    hi, lo = result_of(index, position, "hi"), result_of(index, position, "lo")
                    results.append(hi if hi == lo else "window")
            counts.update(results)
            if any(result.startswith("refused:") for result in results):
                groups["refused"].append(_label(section))
            elif any(result in ("window", "ambiguous_map") for result in results):
                groups["window"].append(_label(section))
            elif "skipped:rev3_read_it" in results:
                groups["deviating"].append(_label(section))
        totals[basis] = {"stable_sections": len(sections) - sum(len(group) for group in groups.values()),
                         "refused_sections": len(groups["refused"]), "window_sections": len(groups["window"]),
                         "deviating_sections": len(groups["deviating"]),
                         "first_refused": groups["refused"][0] if groups["refused"] else None, **groups,
                         "unreadable": labels, "names": dict(sorted(counts.items()))}
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
    except Exception as error:  # noqa: BLE001 - a code or the type alone: a message could carry a name
        reason = str(error) if isinstance(error, ValueError) and _CODE.fullmatch(str(error)) else type(error).__name__
        print(json.dumps({"kind": "refused", "reason": reason}, sort_keys=True))
        return 2
    print(json.dumps({"kind": "preflight", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
