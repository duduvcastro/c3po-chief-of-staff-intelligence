"""Read-only preflight of the Valuation ensemble grid's statements (owner 31/10/2026, the new epoch: "Sim, começar").

The grid (PREREG_VALUATION_ENSEMBLE_PIT_US_V1) recomputes, in every section (exchange, T), each admitted Stock's as-filed
reference (``valuation_pit_rerun.as_filed_payload`` over the facts accepted at or before T) and refuses the section,
``statements_table_not_stable``, unless it equals the reference the signed rev3 run recorded. On 30/10 a section refused
for good: a fact accepted before its T was written after rev3 read the store, and the grid cannot complete. Codex
(6537212289): excluding sections is NO-GO; a new epoch with its own protocol may change the statements basis.

This counts, for every section of the rev3 manifest (stdin), whether each reference recomputes to rev3's under COUNTERFACTUAL
cuts of the store — the facts and filings whose ``first_seen_at`` is at or before a cut (both tables only take inserts).
``first_seen_at`` is the database's ``now()`` at insert: the inserting TRANSACTION'S START, not its commit, so no cut is the
store a past reader saw (a transaction that began before a read and committed after it has an earlier ``first_seen_at``
than the read, yet was invisible to it; Codex 6544583420). What rev3 actually read is UNKNOWN here; the cuts are rules a
new epoch could adopt, and whether each reproduces rev3's references is what the grid would check under that rule:
  now       no cut: the store as it is, the grid's own read (``AsFiledReader.coverage``/``facts``, its comparison);
  cut_hi    ``first_seen_at <= published_at`` of the V3 snapshot — the candidate rule of a new epoch;
  cut_lo    ``first_seen_at <=`` the later of the previous section's ``published_at`` (rev3 ran its sections one after the
            other) and ``published_at`` minus WINDOW;
  cut_scan  every name at lo, at hi and at every write instant in between of its symbol's filings and its issuers' facts:
            "every_cut" (each cut reproduces what rev3 recorded: its reference matched, or neither read), "some_cut" (a
            rule placing the cut inside the window could reproduce it), "no_cut" (no ``first_seen_at`` cut there does — a
            fact, a remap, an ambiguous map, or a visibility no cut represents: not a proven historical refusal). A section
            is "some_cut" only when ONE instant reproduces all its names at once (a rule cuts the whole section).
Per admitted Stock (a catalogue Stock in rev3's screen) under now, cut_hi and cut_lo: "match"; "refused:<keys>" (covered,
the reference differs: the grid refuses the section); "refused:rev3_reference_missing" (covered, rev3 has no reference
both siblings agree on: the grid refuses); "skipped:rev3_read_it" (not covered, but rev3 read it: the grid skips it, the
inputs deviate from rev3's); "skipped:rev3_neither"; "ambiguous_map" (two filings of the same acceptance map the symbol to
different issuers: the grid's SQL picks one arbitrarily). A section is refused, else uncertain (an ambiguous map), else
deviating, else stable; under cut_scan it is no_cut, else some_cut, else every_cut. The section checks that do not read
the store (the siblings' pairing, the catalogue's hash) are the grid's, not repeated here; a section whose rev3 snapshots
cannot be read is "unreadable".

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

BASES = ("now", "cut_hi", "cut_lo")
WINDOW = timedelta(minutes=60)  # cut_lo's assumption: rev3 read a section's facts at most this long before persisting it
_CODE = re.compile(r"[a-z0-9_]{1,80}")
AMBIGUOUS = object()


def _utc(value: Any) -> datetime:
    instant = grid._instant(value)
    if instant is None:
        raise ValueError("preflight_instant_missing")
    return instant


def filing_index(filings: Iterable[Mapping[str, Any]]) -> dict[str, list[tuple[datetime, datetime, str]]]:
    """symbol (as ``AsFiledReader.coverage`` looks it up) → its filings (written, accepted, issuer)."""
    index: dict[str, list[tuple[datetime, datetime, str]]] = {}
    for row in filings:
        for symbol in row.get("symbols") or ():
            index.setdefault(str(symbol).upper().strip(), []).append(
                (_utc(row["first_seen_at"]), _utc(row["accepted_at"]), str(row["issuer_key"])))
    return index


def map_at(entries: Iterable[tuple[datetime, datetime, str]], cut: datetime | None) -> Any:
    """The issuer ``StatementVintageStore.symbol_issuers`` maps a symbol to over the filings written by ``cut`` (all when
    None): the latest acceptance wins, a tie between two issuers is AMBIGUOUS (the SQL's ``DISTINCT ON`` is arbitrary)."""
    best: datetime | None = None
    issuers: set[str] = set()
    for written, accepted, issuer in entries:
        if cut is not None and written > cut:
            continue
        if best is None or accepted > best:
            best, issuers = accepted, {issuer}
        elif accepted == best:
            issuers.add(issuer)
    if best is None:
        return None
    return next(iter(issuers)) if len(issuers) == 1 else AMBIGUOUS


def symbol_map(filings: Iterable[Mapping[str, Any]], *, written_until: datetime | None) -> dict[str, Any]:
    """symbol → issuer (or AMBIGUOUS) over the filings written at or before ``written_until`` (all when None)."""
    mapped = {symbol: map_at(entries, written_until) for symbol, entries in filing_index(filings).items()}
    return {symbol: issuer for symbol, issuer in mapped.items() if issuer is not None}


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


def _consistent(result: str, expected: Mapping[str, Any] | None) -> bool:
    """A cut reproduces what rev3 saw of a name: its reference matched, or neither read it."""
    return result == "match" if expected is not None else result == "skipped:rev3_neither"


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
    unreadable: list[tuple[str, str]] = []
    for v3_entry, served_entry in pairs:
        try:
            sections.append(section_plan(database, v3_entry, served_entry, catalogues))
        except ValueError as error:  # GridInputError too: a rev3 snapshot the grid would refuse as well, counted, not fatal
            code = str(error) if _CODE.fullmatch(str(error)) else type(error).__name__
            unreadable.append(("%s %s" % (v3_entry.get("market"), v3_entry.get("session_date")), code))
    ordered = sorted(range(len(sections)), key=lambda i: sections[i]["written"])
    for rank, index in enumerate(ordered):  # rev3 ran its sections one after the other
        hi = sections[index]["written"]
        previous = sections[ordered[rank - 1]]["written"] if rank else None
        sections[index]["lo"] = max(hi - WINDOW, previous) if previous is not None else hi - WINDOW
    earliest = min((section["lo"] for section in sections), default=None)
    index_of = filing_index(store.filings(front.MARKET, source=front.FILING_SOURCE))

    def mapped_at(symbol: str, cut: datetime | None) -> Any:
        return map_at(index_of.get(symbol, ()), cut)

    # pass 1: every issuer a name maps to at lo, at hi or at a filing written in between (the map changes only there),
    # and the write instants of each such issuer's facts (any source) after the earliest lo — the cuts a window can hold
    def filing_cuts(section: Mapping[str, Any], symbol: str) -> set[datetime]:
        return {written for written, _, _ in index_of.get(symbol, ()) if section["lo"] < written < section["written"]}
    issuers: set[str] = set()
    for section in sections:
        for symbol, _ in section["names"]:
            for cut in {None, section["lo"], section["written"], *filing_cuts(section, symbol)}:
                issuer = mapped_at(symbol, cut)
                if isinstance(issuer, str):
                    issuers.add(issuer)
    late: dict[str, list[datetime]] = {}
    for issuer in sorted(issuers):
        instants = [_utc(row["first_seen_at"]) for row in store.vintages(front.MARKET, issuer)]
        late[issuer] = sorted({instant for instant in instants if earliest is not None and instant > earliest})
    # every (section, name) at each of its cuts: now (None), lo, hi and the write instants strictly between them
    cuts: dict[tuple[int, int], dict[str, datetime | None]] = {}
    uses: dict[str, list[tuple[int, int, str]]] = {}
    outcome: dict[tuple[int, int, str], str] = {}
    for index, section in enumerate(sections):
        lo, hi = section["lo"], section["written"]
        for position, (symbol, _) in enumerate(section["names"]):
            between = filing_cuts(section, symbol)
            for cut in {lo, hi, *between}:
                issuer = mapped_at(symbol, cut)
                if isinstance(issuer, str):
                    between.update(instant for instant in late.get(issuer, ()) if lo < instant < hi)
            named: dict[str, datetime | None] = {"now": None, "lo": lo, "hi": hi}
            named.update({"c%d" % k: instant for k, instant in enumerate(sorted(between))})
            cuts[(index, position)] = named
            for name, cut in named.items():
                issuer = mapped_at(symbol, cut)
                if issuer is AMBIGUOUS:
                    outcome[(index, position, name)] = "ambiguous_map"
                elif issuer:
                    uses.setdefault(str(issuer), []).append((index, position, name))
                else:
                    outcome[(index, position, name)] = "uncovered"
    # pass 2: each issuer's facts once, every use of it at its own cut
    for issuer, issuer_uses in sorted(uses.items()):
        rows = store.vintages(front.MARKET, issuer)  # every fact of every source, oldest acceptance first
        seen_any = [_utc(row["first_seen_at"]) for row in rows]  # coverage: a fact of ANY source (issuers_with_vintages)
        facts = [row for row in rows if row["source"] == front.VINTAGE_SOURCE]  # what the reader reads
        accepted = [_utc(row["accepted_at"]) for row in facts]
        seen = [_utc(row["first_seen_at"]) for row in facts]
        if accepted != sorted(accepted):
            raise ValueError("preflight_store_order_unexpected")
        first_written = min(seen_any) if seen_any else None
        later = [i for i, instant in enumerate(seen) if earliest is not None and instant > earliest]
        references: dict[tuple[int, tuple[int, ...]], dict[str, Any]] = {}
        for index, position, name in issuer_uses:
            section, written = sections[index], cuts[(index, position)][name]
            if first_written is None or (written is not None and first_written > written):
                outcome[(index, position, name)] = "uncovered"
                continue
            end = bisect.bisect_right(accepted, section["as_of"])
            excluded = () if written is None else tuple(i for i in later if i < end and seen[i] > written)
            key = (end, excluded)
            if key not in references:
                skip = set(excluded)
                references[key] = pit.as_filed_payload([facts[i] for i in range(end) if i not in skip],
                                                       market=section["market"], front=front)[1]
            expected, reference = section["names"][position][1], references[key]
            if expected is None:
                outcome[(index, position, name)] = "refused:rev3_reference_missing"
                continue
            differing = [field for field in reference if expected.get(field) != reference.get(field)]  # the grid's comparison
            outcome[(index, position, name)] = "match" if not differing else "refused:" + ",".join(differing)

    def result_of(index: int, position: int, name: str) -> str:
        found = outcome.get((index, position, name), "uncovered")
        if found == "uncovered":  # the grid skips the name; it deviates from rev3 when rev3 had read it
            return "skipped:rev3_read_it" if sections[index]["names"][position][1] is not None else "skipped:rev3_neither"
        return found

    def timeline(index: int, position: int) -> list[tuple[datetime, bool]]:
        """A name's cuts in time order, each with whether it reproduces what rev3 recorded (between two of them nothing
        about the name changes)."""
        expected = sections[index]["names"][position][1]
        named = cuts[(index, position)]
        return sorted((instant, _consistent(result_of(index, position, name), expected))
                      for name, instant in named.items() if name != "now" and instant is not None)

    def consistent_at(line: list[tuple[datetime, bool]], instant: datetime) -> bool:
        return line[bisect.bisect_right([at for at, _ in line], instant) - 1][1]  # every line starts at the section's lo

    codes = Counter(code for _, code in unreadable)
    totals: dict[str, Any] = {"sections": len(sections) + len(unreadable), "names": sum(len(s["names"]) for s in sections),
                              "unreadable_sections": len(unreadable), "unreadable_reasons": dict(sorted(codes.items())),
                              "first_rev3_write": min(s["written"] for s in sections).isoformat() if sections else None,
                              "last_rev3_write": max(s["written"] for s in sections).isoformat() if sections else None}
    for basis in BASES:
        counts: Counter[str] = Counter()
        groups: dict[str, list[str]] = {"refused": [], "uncertain": [], "deviating": []}
        for index, section in enumerate(sections):
            name = {"now": "now", "cut_hi": "hi", "cut_lo": "lo"}[basis]
            results = [result_of(index, position, name) for position in range(len(section["names"]))]
            counts.update(results)
            if any(result.startswith("refused:") for result in results):
                groups["refused"].append(_label(section))
            elif "ambiguous_map" in results:
                groups["uncertain"].append(_label(section))
            elif "skipped:rev3_read_it" in results:
                groups["deviating"].append(_label(section))
        totals[basis] = {"stable_sections": len(sections) - sum(len(group) for group in groups.values()),
                         "refused_sections": len(groups["refused"]), "uncertain_sections": len(groups["uncertain"]),
                         "deviating_sections": len(groups["deviating"]),
                         "first_refused": groups["refused"][0] if groups["refused"] else None, **groups,
                         "unreadable": [label for label, _ in unreadable], "names": dict(sorted(counts.items()))}
    scan: Counter[str] = Counter()
    by_scan: dict[str, list[str]] = {"no_cut": [], "some_cut": []}
    for index, section in enumerate(sections):
        lines = [timeline(index, position) for position in range(len(section["names"]))]
        results = ["every_cut" if all(ok for _, ok in line) else "some_cut" if any(ok for _, ok in line) else "no_cut" for line in lines]
        scan.update(results)
        # a rule cuts the WHOLE section at one instant: "some_cut" only when one instant reproduces every name at once
        # (pre-review of 2a2b35be P2: each name with its own cut is no section's rule)
        instants = sorted({instant for line in lines for instant, _ in line})
        if all(result == "every_cut" for result in results):
            continue
        if any(all(consistent_at(line, instant) for line in lines) for instant in instants):
            by_scan["some_cut"].append(_label(section))
        else:
            by_scan["no_cut"].append(_label(section))
    totals["cut_scan"] = {"every_cut_sections": len(sections) - len(by_scan["no_cut"]) - len(by_scan["some_cut"]),
                          "some_cut_sections": len(by_scan["some_cut"]), "no_cut_sections": len(by_scan["no_cut"]), **by_scan,
                          "unreadable": [label for label, _ in unreadable], "names": dict(sorted(scan.items()))}
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
