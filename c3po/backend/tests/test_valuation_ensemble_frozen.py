from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest

from app import valuation_ensemble_executor as executor
from app.statement_vintages import StatementVintageStore
from app.valuation_ensemble_frozen import FrozenAsFiledReader, FrozenIndex
from app.valuation_ensemble_grid import GridInputError
from tests.test_valuation_ensemble_grid import T, _compute, _fixture

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
    section = _compute(fixture, vintages=_frozen(fixture[0], cut))
    assert section["catalogue_stocks"] == 6 and len(section["records"]) == 6


def test_the_frozen_cut_keeps_what_was_written_by_it_and_refuses_a_difference_from_rev3() -> None:
    """A fact written before the cut that rev3 did not see (here: accepted by T and written a minute before the cut, while
    rev3's reference is the one without it) is in the cut: the comparison refuses, never accepts it silently."""
    fixture = _fixture()
    cut = _rev3_read(fixture)
    _late_fact(fixture[0], accepted=T - timedelta(days=1), written=cut - timedelta(minutes=1))
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


def test_the_symbol_map_at_a_cut_takes_the_latest_acceptance_then_the_larger_document() -> None:
    t = datetime(2026, 10, 20, tzinfo=UTC)
    index = FrozenIndex({"AAA": [(t - timedelta(days=5), t - timedelta(days=10), "D-1", "1"),
                                 (t + timedelta(days=1), t - timedelta(days=1), "D-2", "2"),
                                 (t - timedelta(days=4), t - timedelta(days=10), "D-3", "3")]}, {})
    assert index.issuer_at("AAA", t) == "3"  # D-2 written after the cut; D-1 and D-3 tie on acceptance: the larger doc_id
    assert index.issuer_at("AAA", t + timedelta(days=2)) == "2" and index.issuer_at("BBB", t) is None


@pytest.mark.parametrize("published", [None, "", "not a time", "2026-10-23T12:00:00", datetime(2026, 10, 23, 12, 0)])
def test_a_section_without_a_zoned_persistence_instant_is_refused(published) -> None:
    snapshot = {} if published is None else {"published_at": published}
    with pytest.raises(ValueError, match="ensemble_statements_cut_missing"):
        executor._written_at(snapshot)
    with pytest.raises(ValueError, match="ensemble_statements_cut_missing"):
        FrozenAsFiledReader(None, written_until=published if isinstance(published, datetime) else None, index=lambda: None)  # type: ignore[arg-type]
    assert executor._written_at({"published_at": "2026-10-23T12:00:00Z"}) == datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
