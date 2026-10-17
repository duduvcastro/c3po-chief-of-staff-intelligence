from __future__ import annotations

import importlib.util
import logging
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
from cvm_statement_fixtures import INDUSTRY, ISSUERS, SERVICES, build_packages

YEAR = 2026


class FakeStore:
    """The 051 store's surface this adapter relies on: filings(), register_filings(), insert_vintages(). Its rows live
    on the class, as a database outlives a run: every ``open()`` sees what earlier runs wrote. A fact's natural key
    makes a rewrite a no-op, like the real store's."""

    registered: list[dict] = []
    facts: dict[tuple, dict] = {}
    refuse_inserts = 0  # the next N insert calls raise; -1 refuses every call
    insert_calls = 0

    def __init__(self, database) -> None:
        self.database = database

    @classmethod
    def reset(cls) -> None:
        cls.registered = []
        cls.facts = {}
        cls.refuse_inserts = 0
        cls.insert_calls = 0

    def filings(self, market, *, source=None, **_):
        return [row for row in FakeStore.registered if row["market"] == market and (source is None or row["source"] == source)]

    def register_filings(self, filings):
        FakeStore.registered.extend(filings)
        return len(filings)

    def insert_vintages(self, market, issuer_key, rows):
        FakeStore.insert_calls += 1
        if FakeStore.refuse_inserts:
            FakeStore.refuse_inserts -= 1 if FakeStore.refuse_inserts > 0 else 0
            raise RuntimeError("insert refused")
        assert all(row["market"] == market and row["issuer_key"] == issuer_key for row in rows)
        written = 0
        for row in rows:
            key = (row["doc_id"], row["document_version"], row["concept"], row["period_start"], row["period_end"])
            if key not in FakeStore.facts:
                FakeStore.facts[key] = row
                written += 1
        return {"attempted": len(rows), "written": written, "first_publications": 0, "out_of_order": 0}


@pytest.fixture
def fake_store(monkeypatch):
    module = types.ModuleType("fake_statement_vintages")
    module.StatementVintageStore = FakeStore  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fake_statement_vintages", module)
    monkeypatch.setattr("app.cvm_statement_vintages.STORE_MODULE", "fake_statement_vintages")
    FakeStore.reset()
    yield FakeStore
    FakeStore.reset()


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


def documents(store: type[FakeStore]) -> set[tuple[str, int]]:
    return {(row["doc_id"], row["document_version"]) for row in store.registered}


def clean_run(tmp_path, store: type[FakeStore]) -> tuple[set, set]:
    """What one healthy run stores, as the reference a recovered run must reach; the store is emptied afterwards."""
    capture_packages(CvmVintageCapture.open(memory_database(tmp_path)))
    reference = documents(store), set(store.facts)
    store.reset()
    return reference


def test_absent_store_makes_the_capture_a_reported_no_op(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.cvm_statement_vintages.STORE_MODULE", "app.no_such_statement_store")
    capture = CvmVintageCapture.open(memory_database(tmp_path))

    assert capture.status == "store_absent" and not capture.enabled and not capture.degraded
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

    q2 = next(row for row in fake_store.registered if row["doc_id"] == f"itr-{INDUSTRY['code']}-{YEAR}-06-30-2")
    assert q2["source"] == SOURCE and q2["form"] == "ITR" and q2["document_version"] == 2
    assert q2["symbols"] == ["INDS3", "INDS4"]
    assert q2["filed_date"] == date(YEAR, 8, 2)
    # CVM files a receipt DATE: the instant is the end of that day in Sao Paulo, never earlier than the truth
    assert q2["accepted_at"] == datetime.combine(date(YEAR, 8, 2), time.max, tzinfo=SAO_PAULO)
    assert q2["accepted_source"] == ACCEPTED_SOURCE
    assert q2["fiscal_period"] == "Q2" and q2["period_of_report"] == date(YEAR, 6, 30)
    assert next(row for row in fake_store.registered if row["form"] == "DFP")["fiscal_period"] == "FY"

    facts = [row for row in fake_store.facts.values() if row["doc_id"] == q2["doc_id"]]
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
    assert capture.summary() is None and not capture.degraded


def test_filings_wait_for_the_whole_package(tmp_path, fake_store) -> None:
    capture = CvmVintageCapture.open(memory_database(tmp_path))
    package = build_packages(YEAR)[("itr", YEAR)]
    scan_cvm_package(CvmPackage("itr", YEAR, package.payload(), "https://example.invalid"), ISSUERS, vintage_sink=capture.write)

    assert fake_store.facts and not fake_store.registered  # facts written, documents not yet registered
    capture.finish_package()
    assert fake_store.registered


def test_a_new_run_loads_registered_documents_from_the_store_and_skips_them(tmp_path, fake_store) -> None:
    database = memory_database(tmp_path)
    capture_packages(CvmVintageCapture.open(database))
    registered = documents(fake_store)
    calls = fake_store.insert_calls

    again = CvmVintageCapture.open(database)  # nothing injected: open() reads the store
    assert again.known == registered
    capture_packages(again)

    assert fake_store.insert_calls == calls  # no document re-read fact by fact
    assert again.facts_written == again.filings_written == 0
    assert documents(fake_store) == registered and len(fake_store.registered) == len(registered)


def test_a_refused_write_leaves_its_documents_unregistered_and_the_next_run_completes_them(tmp_path, fake_store) -> None:
    reference_documents, reference_facts = clean_run(tmp_path, fake_store)
    database = memory_database(tmp_path)

    fake_store.refuse_inserts = 1  # the first call: the industrial issuer's DFP income statement
    first = CvmVintageCapture.open(database)
    capture_packages(first)

    dfp = (f"dfp-{INDUSTRY['code']}-{YEAR - 1}-12-31-1", 1)
    assert first.unwritten == {dfp}
    assert dfp not in documents(fake_store)  # registered, it would be skipped forever and its original lost
    assert documents(fake_store) == reference_documents - {dfp}
    assert first.degraded
    assert first.summary() == (
        "statement_vintages: 1 write(s) failed, 1 document(s) left unregistered for the next run; first: insert refused"
    )

    second = CvmVintageCapture.open(database)  # the store is healthy again
    assert dfp not in second.known
    capture_packages(second)

    assert documents(fake_store) == reference_documents
    assert set(fake_store.facts) == reference_facts  # every fact of the refused document, none twice
    assert second.filings_written == 1 and second.summary() is None


def test_a_store_refusing_every_write_registers_nothing_and_the_next_run_writes_everything(tmp_path, fake_store) -> None:
    reference_documents, reference_facts = clean_run(tmp_path, fake_store)
    database = memory_database(tmp_path)

    fake_store.refuse_inserts = -1
    first = CvmVintageCapture.open(database)
    capture_packages(first)
    assert not fake_store.registered and not fake_store.facts
    assert first.unwritten == reference_documents and first.degraded

    fake_store.refuse_inserts = 0
    second = CvmVintageCapture.open(database)
    capture_packages(second)
    assert documents(fake_store) == reference_documents and set(fake_store.facts) == reference_facts


def test_a_refused_registration_is_redone_next_run(tmp_path, fake_store, monkeypatch) -> None:
    reference_documents, _ = clean_run(tmp_path, fake_store)
    database = memory_database(tmp_path)

    def refuse(self, filings):
        raise RuntimeError("register refused")

    with monkeypatch.context() as patch:
        patch.setattr(FakeStore, "register_filings", refuse)
        first = CvmVintageCapture.open(database)
        capture_packages(first)
    assert not fake_store.registered and first.degraded
    assert "first: register refused" in (first.summary() or "")

    capture_packages(CvmVintageCapture.open(database))
    assert documents(fake_store) == reference_documents


def test_unindexed_documents_are_reported_not_registered(tmp_path, fake_store) -> None:
    capture = CvmVintageCapture.open(memory_database(tmp_path))
    capture_packages(capture, drop_index_of=("itr", YEAR))

    assert capture.unindexed > 0
    assert not any(row["fiscal_year"] == YEAR and row["form"] == "ITR" for row in fake_store.registered)
    assert not capture.degraded  # nothing refused: the package simply did not say who filed what


def test_sync_marks_a_run_with_refused_vintage_writes_partial_and_the_next_run_succeeds(tmp_path, monkeypatch, fake_store, caplog) -> None:
    from app.investor_relations import SAO_PAULO as IR_SAO_PAULO, InvestorRelationsService, normalize_company_name

    settings = Settings(database_url="", migrations_dir=tmp_path, investor_relations_output_dir=tmp_path / "ir-pdf")
    database = Database(settings)
    ir = InvestorRelationsService(settings, database)
    for company, symbols in ((INDUSTRY, ["INDS3"]), (SERVICES, ["SERV3"])):
        for symbol in symbols:
            database.register_ir_securities([{
                "market": "B3", "symbol": symbol, "company_name": company["name"],
                "name_key": normalize_company_name(company["name"]), "regulator_id": company["code"],
                "tax_id": company["tax_id"], "exchange": "B3",
            }])
    packages = build_packages(datetime.now(IR_SAO_PAULO).year)

    def package(kind, package_year, cutoff):
        fixture = packages.get((kind, package_year))
        url = f"https://example.invalid/{kind}/{package_year}.zip"
        return (fixture.index, fixture.payload(), url) if fixture else ([], b"", url)

    monkeypatch.setattr(ir, "_cvm_structured_package", package)

    def runs() -> list[dict]:
        return sorted(
            (run for run in database._ingestion_runs.values() if run["source_code"] == "cvm_statements"),
            key=lambda run: run["started_at"],
        )

    fake_store.refuse_inserts = -1
    caplog.set_level(logging.ERROR, logger="app.investor_relations")
    ir.sync_cvm_statements()
    refused = runs()[-1]
    assert refused["status"] == "partial"
    assert "document(s) left unregistered for the next run" in refused["error_summary"]
    assert any("CVM statements run" in message for message in caplog.messages)  # an error event, not a quiet summary
    assert not fake_store.registered

    fake_store.refuse_inserts = 0
    ir.sync_cvm_statements()
    recovered = runs()[-1]
    assert recovered["status"] == "succeeded" and recovered["error_summary"] is None
    assert {row["issuer_key"] for row in fake_store.registered} == {INDUSTRY["tax_id"], SERVICES["tax_id"]}


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
    assert again.known == {(row["doc_id"], int(row.get("document_version") or 1)) for row in filings}
    capture_packages(again)
    assert len(store.vintages("B3", INDUSTRY["tax_id"])) == len(facts)
