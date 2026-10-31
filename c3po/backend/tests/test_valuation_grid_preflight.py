from __future__ import annotations

import io
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterator

import pytest

from app import valuation_grid_preflight as preflight
from app import valuation_pit_rerun as pit
from app.config import Settings
from app.database import Database
from tests import asfiled_front

UTC = timezone.utc
REV3_READ = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)  # when rev3 persisted both sections


@pytest.fixture
def front() -> Iterator[Any]:
    with asfiled_front.installed() as modules:
        yield modules


def test_the_symbol_map_takes_the_latest_acceptance_among_the_filings_written_by_the_cut() -> None:
    t = datetime(2026, 10, 20, tzinfo=UTC)
    filings = [{"symbols": ["AAA"], "issuer_key": "1", "accepted_at": t - timedelta(days=10), "first_seen_at": t - timedelta(days=5)},
               {"symbols": ["aaa "], "issuer_key": "2", "accepted_at": t - timedelta(days=1), "first_seen_at": t + timedelta(days=1)}]
    assert preflight.symbol_map(filings, written_until=None) == {"AAA": "2"}
    assert preflight.symbol_map(filings, written_until=t) == {"AAA": "1"}


def _file(front: Any, database: Database, symbol: str, issuer: str, doc_id: str, accepted: datetime, revenue: int,
          period_end: date, written: datetime) -> None:
    """One 10-Q into the real 051 store (memory), then its rows stamped as written at ``written``."""
    store = front.statement_vintages.StatementVintageStore(database)
    sec = front.sec_xbrl
    store.register_filings([{"market": "US", "issuer_key": issuer, "source": sec.FILING_SOURCE, "doc_id": doc_id, "form": "10-Q",
                             "symbols": [symbol], "filed_date": accepted.date(), "accepted_at": accepted, "accepted_source": "sec_header"}])
    concept = "us-gaap:Revenues"
    store.insert_vintages("US", issuer, [{"market": "US", "issuer_key": issuer, "source": sec.VINTAGE_SOURCE, "doc_id": doc_id,
                                          "form": "10-Q", "period_start": period_end - timedelta(days=90), "period_end": period_end,
                                          "concept": concept, "unit": sec.CONCEPT_UNITS[concept], "value": Decimal(revenue),
                                          "filed_date": accepted.date(), "accepted_at": accepted}])
    for row in database._statement_filings + database._statement_vintages:  # type: ignore[attr-defined]
        if row["doc_id"] == doc_id:
            row["first_seen_at"] = written


def test_a_fact_written_after_rev3_refuses_now_and_the_rev3_write_instant_reproduces_it(front, monkeypatch) -> None:
    database = Database(Settings(database_url=""))
    t1, t2 = datetime(2026, 6, 30, 5, 0, tzinfo=UTC), datetime(2026, 9, 30, 5, 0, tzinfo=UTC)
    _file(front, database, "AAA", "1", "A-1", datetime(2026, 5, 5, 20, 0, tzinfo=UTC), 100, date(2026, 3, 31), REV3_READ - timedelta(days=30))
    # accepted before both T but written after rev3 read the store (a late backfill): rev3 never saw it
    _file(front, database, "AAA", "1", "A-2", datetime(2026, 6, 1, 20, 0, tzinfo=UTC), 110, date(2026, 3, 31), REV3_READ + timedelta(days=5))
    _file(front, database, "CCC", "3", "C-1", datetime(2026, 5, 6, 20, 0, tzinfo=UTC), 50, date(2026, 3, 31), REV3_READ - timedelta(days=30))
    as_front = pit.as_filed_front()[0]
    store = front.statement_vintages.StatementVintageStore(database)

    def reference(issuer: str, cut: datetime) -> dict[str, Any]:
        rows = [r for r in store.vintages("US", issuer, source=front.sec_xbrl.VINTAGE_SOURCE)
                if r["accepted_at"] <= cut and r["first_seen_at"] <= REV3_READ]
        return pit.as_filed_payload(rows, market="NASDAQ", front=as_front)[1]
    sections = [{"market": "NASDAQ", "session": "2026-06-29", "as_of": t1, "written": REV3_READ,
                 "names": [("AAA", reference("1", t1)), ("CCC", reference("3", t1)), ("ZZZ", {"facts": 1})]},
                {"market": "NASDAQ", "session": "2026-09-29", "as_of": t2, "written": REV3_READ,
                 "names": [("CCC", reference("3", t2)), ("YYY", None)]}]
    monkeypatch.setattr(preflight.exe, "_reference_pairs", lambda rev3: [({"i": 0}, {}), ({"i": 1}, {})])
    monkeypatch.setattr(preflight, "section_plan", lambda db, v3, other, catalogues: sections[v3["i"]])
    result = preflight.run(database, {})
    assert result["sections"] == 2 and result["names"] == 5
    now, at_rev3 = result["now"], result["at_rev3"]
    # now: AAA reads A-2 too (facts 2 vs rev3's 1) and the section refuses; the other section only lacks names rev3 lacked
    assert now["refused"] == ["NASDAQ 2026-06-29"] and now["stable_sections"] == 1 and now["deviating_sections"] == 0
    assert any(key.startswith("refused:facts") for key in now["names"])
    # at rev3's write instant AAA recomputes; ZZZ, which rev3 read but no filing maps, deviates without refusing
    assert at_rev3["refused"] == [] and at_rev3["deviating"] == ["NASDAQ 2026-06-29"] and at_rev3["stable_sections"] == 1
    assert at_rev3["names"] == {"match": 3, "skipped:rev3_neither": 1, "skipped:rev3_read_it": 1}
    assert result["first_rev3_write"] == result["last_rev3_write"] == REV3_READ.isoformat()


def test_the_command_prints_counts_only_and_refuses_an_unsigned_manifest(front, monkeypatch, capsys) -> None:
    database = Database(Settings(database_url=""))
    monkeypatch.setattr(preflight.sys, "stdin", type("Stdin", (), {"buffer": io.BytesIO(b'{"complete": false}')})())
    assert preflight.main([], database=database) == 2
    printed = json.loads(capsys.readouterr().out)
    assert printed == {"kind": "refused", "reason": "ensemble_reference_manifest_not_the_complete_signed_rev3"}
