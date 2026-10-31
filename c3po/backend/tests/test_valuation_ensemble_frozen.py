from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest

from app import valuation_ensemble_executor as executor
from app.statement_vintages import StatementVintageStore
from app import valuation_pit_rerun as pit
from app.valuation_ensemble_frozen import FrozenAsFiledReader, FrozenIndex, check_section_statements
from app.valuation_ensemble_grid import GridInputError
from app import sec_xbrl
from tests.test_valuation_ensemble_grid import SYMBOLS, T, _compute, _fixture

UTC = timezone.utc


def _late_fact(database, *, accepted, written):
    """A comparative of the fixture's first revenue fact, accepted at ``accepted`` and written at ``written``."""
    original = next(row for row in database._statement_vintages if row["concept"] == "us-gaap:Revenues")
    StatementVintageStore(database).insert_vintages("US", original["issuer_key"], [
        dict(original, doc_id="later-comparative", value=1e9, accepted_at=accepted)])
    for row in database._statement_vintages:
        if row["doc_id"] == "later-comparative":
            row["first_seen_at"] = written


def _frozen(database, cut):
    return FrozenAsFiledReader(database, written_until=cut, index=lambda: FrozenIndex.load(database))


def _check(fixture, reader):
    database, _, v3, sibling = fixture
    return check_section_statements(database, market="NASDAQ", as_of=T, v3_snapshot=v3, served_snapshot=sibling, reader=reader)


def _rev3_read(fixture):
    """The fixture's store written before its V3 sibling persisted, as rev3 read it on the host."""
    database, _, v3, _ = fixture
    cut = executor._written_at(v3)
    for row in database._statement_filings + database._statement_vintages:
        row["first_seen_at"] = min(row["first_seen_at"], cut - timedelta(days=1))
    return cut


def test_a_fact_written_after_rev3_breaks_the_live_read_and_the_frozen_cut_reproduces_rev3() -> None:
    """PREREG rev 2 §2: a fact accepted before T but written after rev3 persisted the section refuses the section on the
    live store (statements_table_not_stable, 30/10); the store cut at the V3 snapshot's published_at reproduces rev3."""
    fixture = _fixture()
    cut = _rev3_read(fixture)
    _late_fact(fixture[0], accepted=T - timedelta(days=1), written=cut + timedelta(days=5))
    with pytest.raises(GridInputError, match="statements_table_not_stable"):
        _compute(fixture)
    with pytest.raises(GridInputError, match="statements_table_not_stable"):
        _check(fixture, pit.AsFiledReader(fixture[0]))
    assert _check(fixture, _frozen(fixture[0], cut)) == {"compared": 6, "not_evaluable": 0}
    section = _compute(fixture, vintages=_frozen(fixture[0], cut))
    assert section["catalogue_stocks"] == 6 and len(section["records"]) == 6


def test_the_frozen_cut_keeps_what_was_written_by_it_and_refuses_a_difference_from_rev3() -> None:
    """A fact written before the cut that rev3 did not see (here: accepted by T and written a minute before the cut, while
    rev3's reference is the one without it) is in the cut: the comparison refuses, never accepts it silently."""
    fixture = _fixture()
    cut = _rev3_read(fixture)
    _late_fact(fixture[0], accepted=T - timedelta(days=1), written=cut - timedelta(minutes=1))
    with pytest.raises(GridInputError, match="statements_table_not_stable"):
        _check(fixture, _frozen(fixture[0], cut))
    with pytest.raises(GridInputError, match="statements_table_not_stable"):
        _compute(fixture, vintages=_frozen(fixture[0], cut))


def test_coverage_and_facts_follow_the_cut() -> None:
    fixture = _fixture()
    database = fixture[0]
    cut = _rev3_read(fixture)
    reader = _frozen(database, cut)
    assert reader.present()
    covered = reader.coverage("NASDAQ")
    issuer = next(iter(covered.values()))
    assert reader.facts(issuer, as_of=T, refused=Counter())
    early = _frozen(database, cut - timedelta(days=30))  # before every write: nothing covered, nothing read
    assert early.present() and early.coverage("NASDAQ") == {} and early.facts(issuer, as_of=T, refused=Counter()) == []


def test_the_symbol_map_at_a_cut_takes_the_latest_acceptance_and_a_tie_names_both_issuers() -> None:
    t = datetime(2026, 10, 20, tzinfo=UTC)
    index = FrozenIndex({"AAA": [(t - timedelta(days=5), t - timedelta(days=10), "1"),
                                 (t + timedelta(days=1), t - timedelta(days=1), "2"),
                                 (t - timedelta(days=4), t - timedelta(days=10), "3"),
                                 (t - timedelta(days=3), t - timedelta(days=20), "4")]}, {})
    assert index.issuers_at("AAA", t) == {"1", "3"}  # "2" written after the cut; "1" and "3" tie on the latest acceptance
    assert index.issuers_at("AAA", t + timedelta(days=2)) == {"2"} and index.issuers_at("BBB", t) == frozenset()
    assert index.issuers_at("AAA", t - timedelta(days=4, hours=12)) == {"1"}  # before "3" and "4" were written


def _filing(database, *, symbol, issuer, accepted, written):
    """A registered document of ``issuer`` detected under ``symbol``, accepted at ``accepted`` and written at ``written``."""
    StatementVintageStore(database).register_filings([{"market": "US", "issuer_key": issuer, "source": sec_xbrl.FILING_SOURCE,
        "doc_id": f"{issuer}:extra", "form": "8-K", "filed_date": accepted.date(), "period_of_report": accepted.date(),
        "accepted_at": accepted, "accepted_source": "synthetic_sec_header", "symbols": [symbol]}])
    for row in database._statement_filings:
        if row["doc_id"] == f"{issuer}:extra":
            row["first_seen_at"] = written


def _latest_acceptance(database, symbol):
    return max(row["accepted_at"] for row in database._statement_filings if symbol in (row.get("symbols") or ()))


def test_a_tie_between_two_issuers_at_the_cut_refuses_the_section() -> None:
    """PREREG rev 2 §2: the store's SQL breaks a tie on the latest acceptance arbitrarily, so an admitted symbol whose
    latest acceptance written by the cut ties between two issuers refuses the section; it is neither covered nor read."""
    fixture = _fixture()
    database = fixture[0]
    cut = _rev3_read(fixture)
    symbol = SYMBOLS[0]
    _filing(database, symbol=symbol, issuer="9999999999", accepted=_latest_acceptance(database, symbol), written=cut - timedelta(hours=1))
    reader = _frozen(database, cut)
    assert symbol in reader.ambiguous("NASDAQ") and symbol not in reader.coverage("NASDAQ")
    with pytest.raises(GridInputError, match="statements_table_not_stable"):
        _check(fixture, reader)
    # the rev 1 grid alone would skip the name as not evaluable: the executor runs the check before it
    assert len(_compute(fixture, vintages=_frozen(database, cut))["records"]) == 6
    later = _frozen(database, cut - timedelta(hours=2))  # the tying document written after this cut: no tie there
    assert symbol not in later.ambiguous("NASDAQ") and _check(fixture, later) == {"compared": 6, "not_evaluable": 0}


def test_a_name_rev3_read_that_the_cut_does_not_cover_refuses_the_section_on_both_reads() -> None:
    """A later document remaps an admitted symbol to an issuer without facts: the store no longer covers a name rev3
    recorded a reference for. The section is refused (the rev 1 grid skipped it as not evaluable), under the cut and on
    the live store alike; before the remap was written, the cut reproduces rev3."""
    fixture = _fixture()
    database = fixture[0]
    cut = _rev3_read(fixture)
    symbol = SYMBOLS[0]
    _filing(database, symbol=symbol, issuer="9999999999", accepted=_latest_acceptance(database, symbol) + timedelta(days=1),
            written=cut - timedelta(hours=1))
    assert symbol not in _frozen(database, cut).coverage("NASDAQ") and symbol not in _frozen(database, cut).ambiguous("NASDAQ")
    with pytest.raises(GridInputError, match="statements_table_not_stable"):
        _check(fixture, _frozen(database, cut))
    with pytest.raises(GridInputError, match="statements_table_not_stable"):
        _check(fixture, pit.AsFiledReader(database))
    # the rev 1 grid alone would skip the name as not evaluable: the executor runs the check before it
    assert _compute(fixture, vintages=_frozen(database, cut))["catalogue_stocks"] == 6
    assert _check(fixture, _frozen(database, cut - timedelta(hours=2))) == {"compared": 6, "not_evaluable": 0}


@pytest.mark.parametrize("published", [None, "", "not a time", "2026-10-23T12:00:00", datetime(2026, 10, 23, 12, 0)])
def test_a_section_without_a_zoned_persistence_instant_is_refused(published) -> None:
    snapshot = {} if published is None else {"published_at": published}
    with pytest.raises(ValueError, match="ensemble_statements_cut_missing"):
        executor._written_at(snapshot)
    with pytest.raises(ValueError, match="ensemble_statements_cut_missing"):
        FrozenAsFiledReader(None, written_until=published if isinstance(published, datetime) else None, index=lambda: None)  # type: ignore[arg-type]
    assert executor._written_at({"published_at": "2026-10-23T12:00:00Z"}) == datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


def test_the_section_check_and_the_grid_share_one_read_of_each_issuer() -> None:
    """The executor runs the rev 2 check, then the grid, on ONE reader per section: each issuer's facts at T are read from
    the store once and both get the same rows; the reader's refusal counts reach every caller."""
    fixture = _fixture()
    database = fixture[0]
    cut = _rev3_read(fixture)
    reader = _frozen(database, cut)
    assert reader.present()
    reads: list[str] = []
    original = reader._store.vintages

    def counted(market, issuer_key, **kwargs):
        reads.append(issuer_key)
        return original(market, issuer_key, **kwargs)
    reader._store.vintages = counted  # type: ignore[method-assign]
    assert _check(fixture, reader) == {"compared": 6, "not_evaluable": 0}
    assert len(_compute(fixture, vintages=reader)["records"]) == 6
    assert sorted(reads) == sorted(set(reads)) and len(reads) == 6
    issuer = reads[0]
    first, second = Counter[str](), Counter[str]()
    rows = reader.facts(issuer, as_of=T, refused=first)
    assert reader.facts(issuer, as_of=T, refused=second) is rows and first == second and len(reads) == 6
    for row in database._statement_vintages:  # a fact without a zoned write is counted for every caller, never read
        if row["issuer_key"] == issuer:
            row["first_seen_at"] = row["first_seen_at"].replace(tzinfo=None)
            break
    fresh, again = Counter[str](), Counter[str]()
    late = _frozen(database, cut)
    assert late.present()
    kept = late.facts(issuer, as_of=T, refused=fresh)
    assert late.facts(issuer, as_of=T, refused=again) is kept and len(kept) == len(rows) - 1
    assert fresh == again == Counter({"statement_vintages:fact_without_a_zoned_write": 1})
