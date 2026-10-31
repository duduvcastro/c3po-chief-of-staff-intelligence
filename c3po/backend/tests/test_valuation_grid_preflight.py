from __future__ import annotations

import copy
import io
import json
import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterator

import pytest

from app import valuation_grid_preflight as preflight
from app import valuation_pit_rerun as pit
from app.config import Settings
from app.database import Database
from app.statement_vintages import StatementVintageStore
from app.valuation_ensemble_grid import GridInputError
from tests import asfiled_front
from tests.test_valuation_ensemble_grid import _block_network, _compute, _fixture  # noqa: F401
from tests.test_valuation_pit_rerun import NOW, T as GRID_T

UTC = timezone.utc
T = datetime(2026, 6, 30, 5, 0, tzinfo=UTC)
WRITTEN = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)  # a V3 snapshot's published_at
CONCEPTS = ["us-gaap:Revenues", "us-gaap:NetIncomeLoss", "us-gaap:StockholdersEquity", "dei:EntityCommonStockSharesOutstanding"]


@pytest.fixture
def front() -> Iterator[Any]:
    with asfiled_front.installed() as modules:
        yield modules


def _db() -> Database:
    db = Database(Settings(database_url=""))
    db._statement_filings = []  # type: ignore[attr-defined]
    db._statement_vintages = []  # type: ignore[attr-defined]
    return db


def _add(front, db, *, issuer, doc, symbols, accepted, written, concepts, source=None) -> None:
    """One 10-Q into the real 051 store (memory), its rows then stamped as written at ``written``."""
    sec = front.sec_xbrl
    store = front.statement_vintages.StatementVintageStore(db)
    store.register_filings([{"market": "US", "issuer_key": issuer, "source": sec.FILING_SOURCE, "doc_id": doc, "form": "10-Q",
                             "symbols": symbols, "filed_date": accepted.date(), "accepted_at": accepted, "accepted_source": "sec_header"}])
    end = (accepted - timedelta(days=35)).date()
    rows = []
    for i, concept in enumerate(concepts):
        start = None if concept in ("us-gaap:StockholdersEquity", "dei:EntityCommonStockSharesOutstanding") else end - timedelta(days=90)
        rows.append({"market": "US", "issuer_key": issuer, "source": source or sec.VINTAGE_SOURCE, "doc_id": doc, "form": "10-Q",
                     "period_start": start, "period_end": end, "concept": concept, "unit": sec.CONCEPT_UNITS[concept],
                     "value": Decimal(100 + i + len(doc)), "filed_date": accepted.date(), "accepted_at": accepted})
    if rows:
        store.insert_vintages("US", issuer, rows)
    for row in db._statement_filings + db._statement_vintages:  # type: ignore[attr-defined]
        if row["doc_id"] == doc:
            row["first_seen_at"] = written


def _filtered(db, cut):
    """The store as it stood at ``cut`` (all of it when None)."""
    out = _db()
    keep = (lambda row: True) if cut is None else (lambda row: row["first_seen_at"] <= cut)
    out._statement_filings = [copy.deepcopy(r) for r in db._statement_filings if keep(r)]  # type: ignore[attr-defined]
    out._statement_vintages = [copy.deepcopy(r) for r in db._statement_vintages if keep(r)]  # type: ignore[attr-defined]
    return out


def grid_like(db, section) -> list[str]:
    """The grid's own per-name statements outcome (compute_grid_section) on this store: the oracle."""
    reader = pit.AsFiledReader(db)
    assert reader.present()
    coverage = reader.coverage(section["market"])
    out, raw = [], {}
    for symbol, expected in section["names"]:
        issuer = coverage.get(symbol)
        if not issuer:
            out.append("skipped:rev3_read_it" if expected is not None else "skipped:rev3_neither")
            continue
        if issuer not in raw:
            raw[issuer] = reader.facts(issuer, as_of=section["as_of"], refused=Counter())
        reference = pit.as_filed_payload(raw[issuer], market=section["market"], front=reader.front)[1]
        if expected is None:
            out.append("refused:rev3_reference_missing")
            continue
        differing = [k for k in reference if expected.get(k) != reference.get(k)]
        out.append("match" if not differing else "refused:" + ",".join(differing))
    return out


def _reference(db, symbol, cut, as_of=T):
    reader = pit.AsFiledReader(_filtered(db, cut))
    reader.present()
    issuer = reader.coverage("NASDAQ").get(symbol)
    if not issuer:
        return None
    return dict(pit.as_filed_payload(reader.facts(issuer, as_of=as_of, refused=Counter()), market="NASDAQ", front=reader.front)[1])


def _run(monkeypatch, db, sections):
    monkeypatch.setattr(preflight.exe, "_reference_pairs", lambda rev3: [({"i": i}, {}) for i in range(len(sections))])
    monkeypatch.setattr(preflight, "section_plan", lambda d, v3, other, catalogues: sections[v3["i"]])
    return preflight.run(db, {})


def _oracle(db, sections):
    """The expected totals: the grid's outcome on the store filtered at each cut (lo, hi as the module brackets them)."""
    order = sorted(range(len(sections)), key=lambda i: sections[i]["written"])
    cuts = {}
    for rank, index in enumerate(order):
        hi = sections[index]["written"]
        previous = sections[order[rank - 1]]["written"] if rank else None
        cuts[index] = (max(hi - preflight.WINDOW, previous) if previous is not None else hi - preflight.WINDOW, hi)
    totals = {}
    for basis in ("now", "at_rev3"):
        counts: Counter[str] = Counter()
        refused, window, deviating = [], [], []
        for index, section in enumerate(sections):
            if basis == "now":
                results = grid_like(_filtered(db, None), section)
            else:
                lo, hi = (grid_like(_filtered(db, cut), section) for cut in cuts[index])
                results = [a if a == b else "window" for a, b in zip(hi, lo)]
            counts.update(results)
            label = "%s %s" % (section["market"], section["session"])
            if any(r.startswith("refused:") for r in results):
                refused.append(label)
            elif "window" in results:
                window.append(label)
            elif "skipped:rev3_read_it" in results:
                deviating.append(label)
        totals[basis] = {"refused": refused, "window": window, "deviating": deviating, "names": dict(sorted(counts.items()))}
    return totals


def test_the_symbol_map_takes_the_latest_acceptance_within_the_write_cut_and_flags_a_tie() -> None:
    t = datetime(2026, 10, 20, tzinfo=UTC)
    filings = [{"symbols": ["AAA"], "issuer_key": "1", "accepted_at": t - timedelta(days=10), "first_seen_at": t - timedelta(days=5)},
               {"symbols": ["aaa"], "issuer_key": "2", "accepted_at": t - timedelta(days=1), "first_seen_at": t + timedelta(days=1)},
               {"symbols": ["BBB"], "issuer_key": "3", "accepted_at": t, "first_seen_at": t},
               {"symbols": ["BBB"], "issuer_key": "4", "accepted_at": t, "first_seen_at": t}]
    assert preflight.symbol_map(filings, written_until=None) == {"AAA": "2", "BBB": preflight.AMBIGUOUS}
    assert preflight.symbol_map(filings, written_until=t)["AAA"] == "1"


@pytest.mark.parametrize("seed", range(25))
def test_the_preflight_agrees_with_the_grids_own_read_of_the_store_at_each_cut(front, monkeypatch, seed) -> None:
    """Pre-review of 83d351d1: random stores, a write instant per section, every outcome — against the grid's reader."""
    rng = random.Random(seed)
    db = _db()
    base = datetime(2026, 1, 1, 14, 0, tzinfo=UTC)
    symbols = ["S%d" % i for i in range(8)]
    writes = sorted(base + timedelta(days=200 + rng.randint(0, 30), hours=rng.randint(0, 23)) for _ in range(5))
    n = 0
    for issuer in (str(i) for i in range(6)):
        for k in range(rng.randint(0, 6)):
            n += 1
            # a distinct acceptance per document: a tie is the module's "ambiguous_map" (Postgres picks one arbitrarily, the
            # memory store the later registration) and has its own test
            accepted = base + timedelta(days=rng.choice([10, 40, 70, 100, 130, 160]), hours=rng.randint(0, 3), minutes=n)
            written = rng.choice([base + timedelta(days=170), writes[rng.randrange(5)] + timedelta(minutes=rng.choice([-20, -5, 5])),
                                  base + timedelta(days=260)])
            _add(front, db, issuer=issuer, doc=f"D{issuer}-{k}-{n}", symbols=rng.sample(symbols, rng.randint(0, 2)),
                 accepted=accepted, written=written, concepts=rng.sample(CONCEPTS, rng.randint(0, 3)))
    sections = []
    for i, written in enumerate(writes):
        as_of = base + timedelta(days=rng.choice([20, 55, 85, 115, 150, 190]), hours=5)
        names = []
        for symbol in rng.sample(symbols, rng.randint(1, 6)):
            ref = _reference(db, symbol, written - timedelta(minutes=rng.choice([0, 10])), as_of=as_of)
            if ref is not None and rng.random() < 0.15:
                ref["facts"] += 1
            elif ref is not None and rng.random() < 0.1:
                ref = None
            elif ref is None and rng.random() < 0.3:
                ref = {"facts": 0}
            names.append((symbol, ref))
        sections.append({"market": "NASDAQ", "session": f"2026-{i + 1:02d}-01", "as_of": as_of, "written": written, "names": names})
    result = _run(monkeypatch, db, copy.deepcopy(sections))
    expected = _oracle(db, sections)
    for basis in ("now", "at_rev3"):
        got = {key: result[basis][key] for key in ("refused", "window", "deviating", "names")}
        assert got == expected[basis], (basis, got, expected[basis])


def test_a_fact_of_another_source_covers_the_issuer_as_the_grid_does(front, monkeypatch) -> None:
    db = _db()
    _add(front, db, issuer="9", doc="Q-1", symbols=["QQQ"], accepted=T - timedelta(days=40), written=WRITTEN - timedelta(days=9),
         concepts=["us-gaap:Revenues"], source="another_us_source")
    expected = _reference(db, "QQQ", None)
    assert expected is not None and expected["facts"] == 0  # covered, no fact of the reader's source
    section = {"market": "NASDAQ", "session": "2026-06-29", "as_of": T, "written": WRITTEN, "names": [("QQQ", expected)]}
    assert grid_like(_filtered(db, None), section) == ["match"]
    assert _run(monkeypatch, db, [section])["now"]["names"] == {"match": 1}


def test_rows_written_inside_rev3s_compute_window_are_a_window_never_a_refusal(front, monkeypatch) -> None:
    """Pre-review of 83d351d1 (P1): rev3 read before it persisted; a row written between the two (or a transaction that
    began before the persistence) is inside the hi cut only. Its verdict differs between the cuts: "window"."""
    db = _db()
    read = WRITTEN - timedelta(minutes=12)  # rev3 read the issuer 12 min before it persisted the section
    _add(front, db, issuer="1", doc="A-1", symbols=["AAA"], accepted=T - timedelta(days=60), written=read - timedelta(days=3),
         concepts=["us-gaap:Revenues"])
    _add(front, db, issuer="1", doc="A-0", symbols=["AAA"], accepted=T - timedelta(days=150), written=read + timedelta(minutes=5),
         concepts=["us-gaap:Revenues", "us-gaap:NetIncomeLoss"])
    _add(front, db, issuer="2", doc="B-1", symbols=["BBB"], accepted=T - timedelta(days=60), written=read + timedelta(minutes=5),
         concepts=["us-gaap:Revenues"])  # first covered inside the window: rev3 never read it
    section = {"market": "NASDAQ", "session": "2026-06-29", "as_of": T, "written": WRITTEN,
               "names": [("AAA", _reference(db, "AAA", read)), ("BBB", _reference(db, "BBB", read))]}
    result = _run(monkeypatch, db, [section])
    assert result["at_rev3"]["refused"] == [] and result["at_rev3"]["window"] == ["NASDAQ 2026-06-29"]
    assert result["at_rev3"]["names"] == {"window": 2}
    assert result["now"]["refused"] == ["NASDAQ 2026-06-29"]  # the grid's read refuses


def test_a_section_whose_rev3_snapshots_cannot_be_read_is_counted_and_the_others_go_on(front, monkeypatch) -> None:
    db = _db()
    _add(front, db, issuer="1", doc="A-1", symbols=["AAA"], accepted=T - timedelta(days=60), written=WRITTEN - timedelta(days=3),
         concepts=["us-gaap:Revenues"])
    good = {"market": "NASDAQ", "session": "2026-06-29", "as_of": T, "written": WRITTEN, "names": [("AAA", _reference(db, "AAA", WRITTEN))]}

    def plan(database, v3, other, catalogues):
        if v3["i"] == 0:
            raise GridInputError("rev3_sibling_manifest_hash_mismatch")
        return good
    monkeypatch.setattr(preflight.exe, "_reference_pairs",
                        lambda rev3: [({"i": 0, "market": "NYSE", "session_date": "2026-06-29"}, {}), ({"i": 1}, {})])
    monkeypatch.setattr(preflight, "section_plan", plan)
    result = preflight.run(db, {})
    assert result["sections"] == 2 and result["unreadable_sections"] == 1
    assert result["now"]["unreadable"] == ["NYSE 2026-06-29"] and result["now"]["stable_sections"] == 1


def test_section_plan_and_run_agree_with_compute_grid_section_on_its_own_fixture(monkeypatch) -> None:
    """Pre-review of 83d351d1: the real section_plan on the grid's fixture: stable when the grid computes the section,
    refused "now" when a fact by T is added (the grid refuses too), reproduced at rev3's write instant."""
    fixture = _fixture()
    database, prices, v3, served_snapshot = fixture
    _compute(fixture)
    for row in database._statement_filings + database._statement_vintages:  # type: ignore[attr-defined]
        if row["first_seen_at"] > NOW:
            row["first_seen_at"] = NOW - timedelta(days=1)  # written before the V3 sibling persisted
    entries = [({"market": "NASDAQ", "as_of": GRID_T.isoformat(), "session_date": prices.session_date, "cycle_id": snap["id"],
                 "run_key": snap["inputs"]["run_key"]}) for snap in (v3, served_snapshot)]
    monkeypatch.setattr(preflight.exe, "_reference_pairs", lambda rev3: [(entries[0], entries[1])])
    result = preflight.run(database, {})
    assert result["now"]["stable_sections"] == 1 and result["at_rev3"]["stable_sections"] == 1, result
    store = StatementVintageStore(database)
    original = next(row for row in database._statement_vintages if row["concept"] == "us-gaap:Revenues")  # type: ignore[attr-defined]
    store.insert_vintages("US", original["issuer_key"], [dict(original, doc_id="later-comparative", value=1e9,
                                                              accepted_at=GRID_T - timedelta(days=1))])
    with pytest.raises(GridInputError, match="statements_table_not_stable"):
        _compute(fixture)
    for row in database._statement_vintages:  # type: ignore[attr-defined]
        if row["doc_id"] == "later-comparative":
            row["first_seen_at"] = NOW + timedelta(days=1)  # written after the V3 sibling persisted
    result = preflight.run(database, {})
    assert result["now"]["refused_sections"] == 1 and result["at_rev3"]["stable_sections"] == 1, result


def test_the_command_prints_counts_only_and_refuses_an_unsigned_manifest(front, monkeypatch, capsys) -> None:
    monkeypatch.setattr(preflight.sys, "stdin", type("Stdin", (), {"buffer": io.BytesIO(b'{"complete": false}')})())
    assert preflight.main([], database=_db()) == 2
    assert json.loads(capsys.readouterr().out) == {"kind": "refused", "reason": "ensemble_reference_manifest_not_the_complete_signed_rev3"}
