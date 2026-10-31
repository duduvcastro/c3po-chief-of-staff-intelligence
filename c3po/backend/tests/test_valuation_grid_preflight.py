from __future__ import annotations

import copy
import io
import json
import random
import sys
import time
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
    """The expected totals, independently: the grid's own outcome on the store filtered at each cut — lo, hi, and for the
    scan EVERY write instant of the store between them (a superset of the module's cuts: between two writes nothing moves)."""
    order = sorted(range(len(sections)), key=lambda i: sections[i]["written"])
    lows = {}
    for rank, index in enumerate(order):
        hi = sections[index]["written"]
        previous = sections[order[rank - 1]]["written"] if rank else None
        lows[index] = max(hi - preflight.WINDOW, previous) if previous is not None else hi - preflight.WINDOW
    instants = sorted({row["first_seen_at"] for row in db._statement_filings + db._statement_vintages})  # type: ignore[attr-defined]
    totals = {}
    for basis in ("now", "cut_hi", "cut_lo"):
        counts: Counter[str] = Counter()
        refused, uncertain, deviating = [], [], []
        for index, section in enumerate(sections):
            cut = {"now": None, "cut_hi": section["written"], "cut_lo": lows[index]}[basis]
            results = grid_like(_filtered(db, cut), section)
            counts.update(results)
            label = "%s %s" % (section["market"], section["session"])
            if any(r.startswith("refused:") for r in results):
                refused.append(label)
            elif "ambiguous_map" in results:
                uncertain.append(label)
            elif "skipped:rev3_read_it" in results:
                deviating.append(label)
        totals[basis] = {"refused": refused, "uncertain": uncertain, "deviating": deviating, "names": dict(sorted(counts.items()))}
    counts = Counter()
    no_cut, some_cut = [], []
    for index, section in enumerate(sections):
        lo, hi = lows[index], section["written"]
        at = [grid_like(_filtered(db, cut), section) for cut in [lo, hi] + [i for i in instants if lo < i < hi]]
        good = [[(r[position] == "match") if expected is not None else (r[position] == "skipped:rev3_neither") for r in at]
                for position, (_, expected) in enumerate(section["names"])]
        results = ["every_cut" if all(g) else "some_cut" if any(g) else "no_cut" for g in good]
        counts.update(results)
        label = "%s %s" % (section["market"], section["session"])
        if all(result == "every_cut" for result in results):
            continue
        if any(all(g[k] for g in good) for k in range(len(at))):  # one cut reproducing every name of the section
            some_cut.append(label)
        else:
            no_cut.append(label)
    totals["cut_scan"] = {"no_cut": no_cut, "some_cut": some_cut, "names": dict(sorted(counts.items()))}
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
    for basis in ("now", "cut_hi", "cut_lo"):
        got = {key: result[basis][key] for key in ("refused", "uncertain", "deviating", "names")}
        assert got == expected[basis], (basis, got, expected[basis])
    got = {key: result["cut_scan"][key] for key in ("no_cut", "some_cut", "names")}
    assert got == expected["cut_scan"], (got, expected["cut_scan"])


def test_a_fact_of_another_source_covers_the_issuer_as_the_grid_does(front, monkeypatch) -> None:
    db = _db()
    _add(front, db, issuer="9", doc="Q-1", symbols=["QQQ"], accepted=T - timedelta(days=40), written=WRITTEN - timedelta(days=9),
         concepts=["us-gaap:Revenues"], source="another_us_source")
    expected = _reference(db, "QQQ", None)
    assert expected is not None and expected["facts"] == 0  # covered, no fact of the reader's source
    section = {"market": "NASDAQ", "session": "2026-06-29", "as_of": T, "written": WRITTEN, "names": [("QQQ", expected)]}
    assert grid_like(_filtered(db, None), section) == ["match"]
    assert _run(monkeypatch, db, [section])["now"]["names"] == {"match": 1}


def test_rows_written_inside_rev3s_compute_window_leave_a_cut_inside_it_that_reproduces(front, monkeypatch) -> None:
    """Pre-review of 83d351d1 (P1): rev3 read before it persisted; a row written between the two is inside the hi cut
    only: the rule at hi refuses, the scan finds "some_cut" (a cut inside the window reproduces)."""
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
    assert result["cut_scan"]["names"] == {"some_cut": 2} and result["cut_scan"]["some_cut"] == ["NASDAQ 2026-06-29"]
    assert result["cut_hi"]["refused"] == ["NASDAQ 2026-06-29"] and result["cut_lo"]["stable_sections"] == 1
    assert result["now"]["refused"] == ["NASDAQ 2026-06-29"]  # the grid's read refuses


def test_two_writes_straddling_rev3s_read_leave_a_cut_between_them(front, monkeypatch) -> None:
    """Pre-review of 07f644ea (P1): both ends of the window refuse (with the same keys), a cut between them reproduces."""
    db = _db()
    read = WRITTEN - timedelta(minutes=8)
    _add(front, db, issuer="1", doc="X-0", symbols=["XXX"], accepted=T - timedelta(days=200), written=read - timedelta(days=3), concepts=CONCEPTS[:2])
    _add(front, db, issuer="1", doc="X-1", symbols=["XXX"], accepted=T - timedelta(days=100), written=read - timedelta(minutes=3), concepts=CONCEPTS[:2])
    _add(front, db, issuer="1", doc="X-2", symbols=["XXX"], accepted=T - timedelta(days=50), written=read + timedelta(minutes=3), concepts=CONCEPTS[:2])
    rev3 = _reference(db, "XXX", read)
    assert _reference(db, "XXX", WRITTEN - preflight.WINDOW) != rev3 and _reference(db, "XXX", WRITTEN) != rev3
    result = _run(monkeypatch, db, [{"market": "NASDAQ", "session": "2026-06-29", "as_of": T, "written": WRITTEN, "names": [("XXX", rev3)]}])
    assert result["cut_scan"]["names"] == {"some_cut": 1} and result["cut_scan"]["no_cut"] == []
    assert result["cut_hi"]["refused_sections"] == 1 and result["cut_lo"]["refused_sections"] == 1


def test_a_reference_no_cut_reproduces_is_no_cut(front, monkeypatch) -> None:
    """Pre-review of 07f644ea (P1): rev3's reference matches the store at no cut and a row inside the window changes other
    keys at hi: the ends differ, yet no cut reproduces — "no_cut", never "some_cut"."""
    db = _db()
    read = WRITTEN - timedelta(minutes=8)
    _add(front, db, issuer="1", doc="D-0", symbols=["DDD"], accepted=T - timedelta(days=200), written=read - timedelta(days=3), concepts=CONCEPTS[:2])
    _add(front, db, issuer="1", doc="D-1", symbols=["DDD"], accepted=T - timedelta(days=50), written=read + timedelta(minutes=3), concepts=CONCEPTS[:2])
    rev3 = dict(_reference(db, "DDD", read), statements_sha256="f" * 64)
    result = _run(monkeypatch, db, [{"market": "NASDAQ", "session": "2026-06-29", "as_of": T, "written": WRITTEN, "names": [("DDD", rev3)]}])
    assert result["cut_scan"]["no_cut"] == ["NASDAQ 2026-06-29"] and result["cut_scan"]["some_cut"] == []


READ = WRITTEN - timedelta(minutes=8)  # rev3's read, inside [lo = hi - WINDOW, hi]
OLD = READ - timedelta(days=3)


def _verdict(monkeypatch, db, symbol, rev3):
    section = {"market": "NASDAQ", "session": "2026-06-29", "as_of": T, "written": WRITTEN, "names": [(symbol, rev3)]}
    return _run(monkeypatch, db, [section])["cut_scan"]["names"]


def test_the_scan_holds_a_fact_only_write_inside_the_window(front, monkeypatch) -> None:
    """Pre-review of 66ab4c1a: the facts' own write instants are cuts (no filing of the symbol at that instant)."""
    db = _db()
    _add(front, db, issuer="1", doc="A-0", symbols=["AAA"], accepted=T - timedelta(days=200), written=OLD, concepts=CONCEPTS[:2])
    _add(front, db, issuer="1", doc="A-1", symbols=[], accepted=T - timedelta(days=100), written=READ - timedelta(minutes=3), concepts=CONCEPTS[:2])
    _add(front, db, issuer="1", doc="A-2", symbols=[], accepted=T - timedelta(days=50), written=READ + timedelta(minutes=3), concepts=CONCEPTS[:2])
    assert _verdict(monkeypatch, db, "AAA", _reference(db, "AAA", READ)) == {"some_cut": 1}


def test_the_scan_holds_a_filing_only_remap_inside_the_window(front, monkeypatch) -> None:
    db = _db()
    _add(front, db, issuer="1", doc="B-0", symbols=["BBB"], accepted=T - timedelta(days=200), written=OLD, concepts=CONCEPTS[:2])
    _add(front, db, issuer="2", doc="B-9", symbols=[], accepted=T - timedelta(days=150), written=OLD, concepts=CONCEPTS[:1])
    _add(front, db, issuer="2", doc="B-1", symbols=["BBB"], accepted=T - timedelta(days=20), written=READ - timedelta(minutes=3), concepts=[])
    _add(front, db, issuer="1", doc="B-2", symbols=["BBB"], accepted=T - timedelta(days=10), written=READ + timedelta(minutes=3), concepts=[])
    assert _verdict(monkeypatch, db, "BBB", _reference(db, "BBB", READ)) == {"some_cut": 1}


def test_the_scan_holds_a_fact_of_the_issuer_mapped_before_a_remap(front, monkeypatch) -> None:
    db = _db()
    _add(front, db, issuer="1", doc="C-0", symbols=["CCC"], accepted=T - timedelta(days=200), written=OLD, concepts=CONCEPTS[:2])
    _add(front, db, issuer="2", doc="C-9", symbols=[], accepted=T - timedelta(days=150), written=OLD, concepts=CONCEPTS[:1])
    _add(front, db, issuer="1", doc="C-1", symbols=[], accepted=T - timedelta(days=100), written=READ - timedelta(minutes=3), concepts=CONCEPTS[:2])
    _add(front, db, issuer="2", doc="C-2", symbols=["CCC"], accepted=T - timedelta(days=10), written=READ + timedelta(minutes=3), concepts=[])
    assert _verdict(monkeypatch, db, "CCC", _reference(db, "CCC", READ)) == {"some_cut": 1}


def test_a_section_is_some_cut_only_when_one_cut_reproduces_all_its_names(front, monkeypatch) -> None:
    """Pre-review of 2a2b35be (P2): rev3 reads BBB, a BBB fact lands (w2), an AAA fact lands (w1), rev3 reads AAA. Each name
    has a reproducing cut (AAA from w1, BBB before w2), but no single cut reproduces both: a rule cannot, "no_cut"."""
    db = _db()
    old = WRITTEN - timedelta(days=3)
    read_b = WRITTEN - timedelta(minutes=20)
    w2, w1 = read_b + timedelta(minutes=1), read_b + timedelta(minutes=3)
    read_a = w1 + timedelta(minutes=1)
    _add(front, db, issuer="1", doc="A-0", symbols=["AAA"], accepted=T - timedelta(days=200), written=old, concepts=CONCEPTS[:2])
    _add(front, db, issuer="2", doc="B-0", symbols=["BBB"], accepted=T - timedelta(days=200), written=old, concepts=CONCEPTS[:2])
    _add(front, db, issuer="2", doc="B-1", symbols=[], accepted=T - timedelta(days=50), written=w2, concepts=CONCEPTS[:2])
    _add(front, db, issuer="1", doc="A-1", symbols=[], accepted=T - timedelta(days=50), written=w1, concepts=CONCEPTS[:2])
    names = [("AAA", _reference(db, "AAA", read_a)), ("BBB", _reference(db, "BBB", read_b))]
    result = _run(monkeypatch, db, [{"market": "NASDAQ", "session": "2026-06-29", "as_of": T, "written": WRITTEN, "names": names}])
    assert result["cut_scan"]["names"] == {"some_cut": 2}  # each name alone
    assert result["cut_scan"]["no_cut"] == ["NASDAQ 2026-06-29"] and result["cut_scan"]["some_cut"] == []  # the section: none
    names_b = [("AAA", _reference(db, "AAA", read_a)), ("BBB", _reference(db, "BBB", read_a))]  # both read after w1
    result = _run(monkeypatch, db, [{"market": "NASDAQ", "session": "2026-06-29", "as_of": T, "written": WRITTEN, "names": names_b}])
    assert result["cut_scan"]["some_cut"] == ["NASDAQ 2026-06-29"]  # one cut (from w1 on) reproduces both


def test_an_ambiguous_map_is_counted_and_makes_the_section_uncertain(front, monkeypatch) -> None:
    db = _db()
    accepted = T - timedelta(days=60)
    _add(front, db, issuer="1", doc="M-1", symbols=["MMM"], accepted=accepted, written=WRITTEN - timedelta(days=3), concepts=["us-gaap:Revenues"])
    _add(front, db, issuer="2", doc="M-2", symbols=["MMM"], accepted=accepted, written=WRITTEN - timedelta(days=3), concepts=["us-gaap:Revenues"])
    result = _run(monkeypatch, db, [{"market": "NASDAQ", "session": "2026-06-29", "as_of": T, "written": WRITTEN,
                                     "names": [("MMM", {"facts": 1})]}])
    for basis in ("now", "cut_hi", "cut_lo"):
        assert result[basis]["names"] == {"ambiguous_map": 1} and result[basis]["uncertain"] == ["NASDAQ 2026-06-29"]
    assert result["cut_scan"]["names"] == {"no_cut": 1}  # an ambiguous map reproduces nothing


def test_a_transaction_that_began_before_the_cut_is_no_cut_never_a_proven_refusal(front, monkeypatch) -> None:
    """Codex 6544583420 (P2): an ingestion begins at lo - 1 s (its first_seen_at), rev3 reads at lo + 1 s without seeing it,
    the ingestion commits at lo + 2 s. Every cut at or after lo holds it: the rules refuse (they would not reproduce rev3)
    and the scan says "no_cut" — what rev3 saw is unknown, so nothing calls it a historical refusal."""
    db = _db()
    lo = WRITTEN - preflight.WINDOW
    _add(front, db, issuer="1", doc="T-0", symbols=["TTT"], accepted=T - timedelta(days=200), written=lo - timedelta(days=2), concepts=CONCEPTS[:2])
    rev3 = _reference(db, "TTT", lo - timedelta(seconds=2))  # what rev3 saw: one document
    _add(front, db, issuer="1", doc="T-1", symbols=["TTT"], accepted=T - timedelta(days=50), written=lo - timedelta(seconds=1), concepts=CONCEPTS[:2])
    result = _run(monkeypatch, db, [{"market": "NASDAQ", "session": "2026-06-29", "as_of": T, "written": WRITTEN, "names": [("TTT", rev3)]}])
    assert result["cut_hi"]["refused_sections"] == 1 and result["cut_lo"]["refused_sections"] == 1
    assert result["cut_scan"]["names"] == {"no_cut": 1} and "refused" not in result["cut_scan"]


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
    assert result["unreadable_reasons"] == {"rev3_sibling_manifest_hash_mismatch": 1}
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
    assert result["now"]["stable_sections"] == 1 and result["cut_hi"]["stable_sections"] == 1, result
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
    assert result["now"]["refused_sections"] == 1 and result["cut_hi"]["stable_sections"] == 1, result
    assert result["cut_scan"]["every_cut_sections"] == 1


SATURDAY = datetime(2026, 10, 31, 16, 0, tzinfo=UTC).timestamp()  # 13:00 Sao Paulo, 12:00 New York on a Saturday


def _main(argv_deadline, **kwargs):
    return preflight.main(["--deadline-at", str(int(argv_deadline))], clock=kwargs.pop("clock", lambda: SATURDAY),
                          on_expiry=kwargs.pop("on_expiry", lambda: None), **kwargs)


def test_the_command_prints_counts_only_and_refuses_an_unsigned_manifest(front, monkeypatch, capsys) -> None:
    monkeypatch.setattr(preflight.sys, "stdin", type("Stdin", (), {"buffer": io.BytesIO(b'{"complete": false}')})())
    assert _main(SATURDAY + 3600, database=_db()) == 2
    assert json.loads(capsys.readouterr().out) == {"kind": "refused", "reason": "ensemble_reference_manifest_not_the_complete_signed_rev3"}

    def leaky(database, rev3):
        raise ValueError("issuer 0000320193 has no AAPL facts")  # a message that is no code: only the type is printed
    monkeypatch.setattr(preflight, "run", leaky)
    monkeypatch.setattr(preflight.sys, "stdin", type("Stdin", (), {"buffer": io.BytesIO(b"{}")})())
    assert _main(SATURDAY + 3600, database=_db()) == 2
    assert json.loads(capsys.readouterr().out) == {"kind": "refused", "reason": "ValueError"}


def test_the_windows_are_the_grids() -> None:
    def at(y, mo, d, h, mi, zone):
        return datetime(y, mo, d, h, mi, tzinfo=zone)
    ny, sp = preflight.NEW_YORK, preflight.SAO_PAULO
    assert preflight.inside_a_window(at(2026, 11, 2, 9, 0, ny)) and not preflight.inside_a_window(at(2026, 11, 2, 8, 59, ny))
    assert preflight.inside_a_window(at(2026, 11, 2, 16, 29, ny)) and not preflight.inside_a_window(at(2026, 11, 2, 16, 30, ny))
    assert not preflight.inside_a_window(at(2026, 10, 31, 10, 0, ny))  # a Saturday morning in New York
    assert preflight.inside_a_window(at(2026, 10, 31, 23, 30, sp)) and preflight.inside_a_window(at(2026, 11, 1, 8, 14, sp))
    assert not preflight.inside_a_window(at(2026, 11, 1, 8, 15, sp)) and not preflight.inside_a_window(at(2026, 10, 31, 23, 29, sp))


def test_the_process_checks_its_own_start_against_the_original_deadline_and_the_windows(front, monkeypatch, capsys) -> None:
    """Codex 6545709465 (P2-2): a compose exec that waited 35 min hands the container a stale duration. The module itself
    reads the clock when it starts: inside a window it refuses (27), under 10 min left of the ORIGINAL deadline it refuses
    (25), otherwise it arms its own end at that deadline, before any read."""
    monday_0905 = datetime(2026, 11, 2, 14, 5, tzinfo=UTC).timestamp()  # 09:05 New York
    assert _main(monday_0905 + 3600, database=_db(), clock=lambda: monday_0905) == 27
    assert json.loads(capsys.readouterr().out) == {"kind": "refused", "reason": "inside_a_window"}
    assert _main(SATURDAY + 599, database=_db()) == 25
    assert json.loads(capsys.readouterr().out) == {"kind": "refused", "reason": "deadline_too_close"}
    armed = []
    monkeypatch.setattr(preflight, "arm_deadline", lambda seconds, on_expiry: armed.append(seconds))
    monkeypatch.setattr(preflight, "run", lambda database, rev3: {"sections": 0})
    monkeypatch.setattr(preflight.sys, "stdin", type("Stdin", (), {"buffer": io.BytesIO(b"{}")})())
    assert _main(SATURDAY + 1200, database=_db()) == 0 and armed == [1200]


@pytest.mark.parametrize("stdout", ["closed", "full"])
def test_the_process_ends_at_its_deadline_whatever_its_stdout_does(stdout) -> None:
    """Codex 6546328535 (P2-2): the end printed its line first, so a closed stdout raised in the timer's thread and a full
    one blocked it, and the process lived on. It ends with 124 in both cases (a real process, a real pipe)."""
    import fcntl
    import os
    import subprocess
    from pathlib import Path

    read_end, write_end = os.pipe()
    if stdout == "closed":
        os.close(read_end)  # no reader: the line's write fails (EPIPE)
    else:
        flags = fcntl.fcntl(write_end, fcntl.F_GETFL)
        fcntl.fcntl(write_end, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        try:
            while True:  # fill the pipe: the child's blocking write then waits forever
                os.write(write_end, b"x" * 4096)
        except BlockingIOError:
            pass
        fcntl.fcntl(write_end, fcntl.F_SETFL, flags)
    backend = Path(__file__).resolve().parents[1]
    code = "import time; from app import valuation_grid_preflight as p; p.arm_deadline(0.05, p._end_at_the_deadline); time.sleep(30)"
    started = time.monotonic()
    child = subprocess.Popen([sys.executable, "-c", code], cwd=backend, stdout=write_end, stderr=subprocess.DEVNULL)
    os.close(write_end)
    try:
        assert child.wait(timeout=20) == 124 and time.monotonic() - started < 20
    finally:
        if child.poll() is None:
            child.kill()
        if stdout == "full":
            os.close(read_end)


def test_the_deadline_timer_fires_on_its_own_thread() -> None:
    import threading as threads

    fired = threads.Event()
    preflight.arm_deadline(0.05, fired.set)
    assert fired.wait(2.0)


def _workflow_filter() -> str:
    """The printing filter of .github/workflows/valuation-grid-preflight.yml (the python between its <<'PY' and PY)."""
    import yaml
    from pathlib import Path

    workflow = yaml.safe_load((Path(__file__).resolve().parents[3] / ".github/workflows/valuation-grid-preflight.yml").read_text())
    script = next(step["run"] for step in workflow["jobs"]["preflight"]["steps"] if step.get("name") == "Run the preflight on the host (read-only)")
    body = script.split("<<'PY' || filtered=$?\n", 1)[1]
    return body.split("\nPY\n", 1)[0]


def test_the_workflow_prints_the_modules_own_line_whole_and_nothing_of_another_shape(front, monkeypatch, tmp_path) -> None:
    import subprocess

    db = _db()
    _add(front, db, issuer="1", doc="A-1", symbols=["AAA"], accepted=T - timedelta(days=60), written=WRITTEN - timedelta(days=3),
         concepts=["us-gaap:Revenues"])
    _add(front, db, issuer="1", doc="A-2", symbols=["AAA"], accepted=T - timedelta(days=30), written=WRITTEN + timedelta(days=3),
         concepts=["us-gaap:Revenues", "us-gaap:NetIncomeLoss"])
    section = {"market": "NASDAQ", "session": "2026-06-29", "as_of": T, "written": WRITTEN, "names": [("AAA", _reference(db, "AAA", WRITTEN))]}
    line = {"kind": "preflight", **_run(monkeypatch, db, [section])}
    assert any(key.startswith("refused:") for key in line["now"]["names"])
    script = tmp_path / "filter.py"
    script.write_text(_workflow_filter())
    stdout = tmp_path / "stdout.txt"
    stdout.write_text("LAUNCHED 1-1\n" + json.dumps(line, sort_keys=True) + "\n")
    printed = subprocess.run([sys.executable, "-I", str(script), str(stdout)], capture_output=True, text=True, check=True).stdout
    assert json.loads(printed.split("\nresult lines:")[0]) == json.loads(json.dumps(line))
    leaked = dict(line, now=dict(line["now"], refused=["AAPL 2026-06-29"]))  # anything off the module's shape is withheld
    stdout.write_text(json.dumps(leaked) + "\n")
    run = subprocess.run([sys.executable, "-I", str(script), str(stdout)], capture_output=True, text=True)
    assert "AAPL" not in run.stdout and run.returncode != 0
