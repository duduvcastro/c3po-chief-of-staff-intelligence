from __future__ import annotations

import importlib.util
import sys
import types
from contextlib import contextmanager
from datetime import date, datetime, time
from decimal import Decimal

import pytest

from app.config import Settings
from app.cvm_fundamentals import SAO_PAULO, CvmPackage, scan_cvm_package
from app.cvm_statement_vintages import ACCEPTED_SOURCE, SOURCE, CvmVintageCapture
from app.database import Database
from cvm_statement_fixtures import INDUSTRY, ISSUERS, build_packages

YEAR = 2026


class FakeStore:
    """The 051 store's surface this adapter relies on: filings(), register_filings(), insert_vintages()."""

    instances: list["FakeStore"] = []

    def __init__(self, database) -> None:
        self.database = database
        self.registered: list[dict] = []
        self.facts: list[dict] = []
        self.fail_inserts = False
        FakeStore.instances.append(self)

    def filings(self, market, *, source=None, **_):
        return [row for row in self.registered if row["market"] == market and (source is None or row["source"] == source)]

    def register_filings(self, filings):
        self.registered.extend(filings)
        return len(filings)

    def insert_vintages(self, market, issuer_key, rows):
        if self.fail_inserts:
            raise RuntimeError("insert refused")
        assert all(row["market"] == market and row["issuer_key"] == issuer_key for row in rows)
        self.facts.extend(rows)
        return {"attempted": len(rows), "written": len(rows), "first_publications": 0, "out_of_order": 0}


@pytest.fixture
def fake_store(monkeypatch):
    module = types.ModuleType("fake_statement_vintages")
    module.StatementVintageStore = FakeStore  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fake_statement_vintages", module)
    monkeypatch.setattr("app.cvm_statement_vintages.STORE_MODULE", "fake_statement_vintages")
    FakeStore.instances.clear()
    return FakeStore


def capture_packages(capture: CvmVintageCapture, *, drop_index_of=None) -> None:
    packages = build_packages(YEAR)
    if drop_index_of is not None:
        packages[drop_index_of].index = []
    for key in (("dfp", YEAR - 1), ("itr", YEAR - 1), ("itr", YEAR)):
        package = packages[key]
        scan_cvm_package(CvmPackage(key[0], key[1], package.payload(), "https://example.invalid"), ISSUERS, vintage_sink=capture.write)
        capture.finish_package()


def memory_database(tmp_path) -> Database:
    return Database(Settings(database_url="", migrations_dir=tmp_path))


def test_absent_store_makes_the_capture_a_reported_no_op(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.cvm_statement_vintages.STORE_MODULE", "app.no_such_statement_store")
    capture = CvmVintageCapture.open(memory_database(tmp_path))

    assert capture.status == "store_absent" and not capture.enabled
    capture_packages(capture)
    assert capture.summary() == (
        "statement_vintages: store absent (app.statement_vintages, migration 051 front, not merged); vintage capture skipped"
    )


def test_absent_tables_make_the_capture_a_reported_no_op(fake_store) -> None:
    class Connection:
        def execute(self, sql, params=()):
            class Cursor:
                def fetchone(self):
                    return ("statement_filings",) if params == ("public.statement_filings",) else (None,)
            return Cursor()

    class FakeDatabase:
        database_url = "postgresql://fake.invalid/c3po"

        @contextmanager
        def connection(self):
            yield Connection()

    capture = CvmVintageCapture.open(FakeDatabase())  # type: ignore[arg-type]

    assert capture.status == "table_absent"
    assert "table statement_vintages absent (migration 051 not applied)" in (capture.summary() or "")


def test_cvm_documents_become_051_filings_and_facts(tmp_path, fake_store) -> None:
    capture = CvmVintageCapture.open(memory_database(tmp_path))
    assert capture.enabled
    capture_packages(capture)
    store = fake_store.instances[-1]

    q2 = next(row for row in store.registered if row["doc_id"] == f"itr-{INDUSTRY['code']}-{YEAR}-06-30-2")
    assert q2["source"] == SOURCE and q2["form"] == "ITR" and q2["document_version"] == 2
    assert q2["symbols"] == ["INDS3", "INDS4"]
    assert q2["filed_date"] == date(YEAR, 8, 2)
    # CVM files a receipt DATE: the instant is the end of that day in Sao Paulo, never earlier than the truth
    assert q2["accepted_at"] == datetime.combine(date(YEAR, 8, 2), time.max, tzinfo=SAO_PAULO)
    assert q2["accepted_source"] == ACCEPTED_SOURCE
    assert q2["fiscal_period"] == "Q2" and q2["period_of_report"] == date(YEAR, 6, 30)
    assert next(row for row in store.registered if row["form"] == "DFP")["fiscal_period"] == "FY"

    facts = [row for row in store.facts if row["doc_id"] == q2["doc_id"]]
    revenue = next(
        row for row in facts
        if row["concept"] == "cvm:DRE_con:3.01:Receita de Venda de Bens e/ou Serviços" and row["period_start"] == date(YEAR, 1, 1)
    )
    assert revenue["value"] == Decimal(290_000) and revenue["unit"] == "BRL"
    assert revenue["period_end"] == date(YEAR, 6, 30) and revenue["accepted_at"] == q2["accepted_at"]
    cash = next(row for row in facts if row["concept"].startswith("cvm:BPA_con:1.01.01:"))
    assert cash["period_start"] is None and cash["value"] == Decimal(52_000)  # a balance is an instant
    shares = next(row for row in facts if row["concept"] == "cvm:composicao_capital:QT_ACAO_TOTAL_TESOURO")
    assert shares["unit"] == "shares" and shares["value"] == Decimal(10)
    assert capture.summary() is None


def test_known_documents_are_skipped_and_filings_wait_for_the_whole_package(tmp_path, fake_store) -> None:
    database = memory_database(tmp_path)
    first = CvmVintageCapture.open(database)
    packages = build_packages(YEAR)
    package = packages[("itr", YEAR)]
    scan_cvm_package(CvmPackage("itr", YEAR, package.payload(), "https://example.invalid"), ISSUERS, vintage_sink=first.write)
    store = fake_store.instances[-1]
    assert store.facts and not store.registered  # facts written, documents not yet registered
    first.finish_package()
    registered = len(store.registered)
    facts = len(store.facts)

    second = CvmVintageCapture.open(database)
    second.store = store
    second.known = {(row["doc_id"], row["document_version"]) for row in store.registered}
    scan_cvm_package(CvmPackage("itr", YEAR, package.payload(), "https://example.invalid"), ISSUERS, vintage_sink=second.write)
    second.finish_package()

    assert len(store.facts) == facts and len(store.registered) == registered


def test_unindexed_documents_and_store_failures_are_reported_not_raised(tmp_path, fake_store) -> None:
    capture = CvmVintageCapture.open(memory_database(tmp_path))
    capture_packages(capture, drop_index_of=("itr", YEAR))
    assert capture.unindexed > 0
    assert not any(row["fiscal_year"] == YEAR and row["form"] == "ITR" for row in fake_store.instances[-1].registered)

    failing = CvmVintageCapture.open(memory_database(tmp_path))
    fake_store.instances[-1].fail_inserts = True
    capture_packages(failing)
    assert "write(s) failed; first: insert refused" in (failing.summary() or "")


@pytest.mark.skipif(importlib.util.find_spec("app.statement_vintages") is None, reason="migration 051 store not merged yet")
def test_capture_against_the_real_051_store_once_merged(tmp_path) -> None:
    from app.statement_vintages import StatementVintageStore

    database = memory_database(tmp_path)
    capture = CvmVintageCapture.open(database)
    assert capture.enabled
    capture_packages(capture)
    store = StatementVintageStore(database)
    filings = store.filings("B3", source=SOURCE)
    assert any(row["doc_id"] == f"itr-{INDUSTRY['code']}-{YEAR}-06-30-2" for row in filings)
    facts = store.vintages("B3", INDUSTRY["tax_id"])
    assert any(row["concept"].startswith("cvm:DRE_con:3.01:") for row in facts)
    # a comparative re-reported by a later filing is not the first publication of that fact
    comparative = [
        row for row in facts
        if row["concept"].startswith("cvm:DRE_con:3.01:") and row["period_end"] == date(YEAR - 1, 6, 30)
        and row["period_start"] == date(YEAR - 1, 1, 1)
    ]
    assert sorted(row["is_first_publication"] for row in comparative) == [False, True]

    again = CvmVintageCapture.open(database)
    capture_packages(again)
    assert len(store.vintages("B3", INDUSTRY["tax_id"])) == len(facts)
