"""SEC EDGAR as filed (Valuation as-filed, owner 2026-10-17): clocks, the fair-access client, companyfacts → vintages,
quarters, the append-only store and the poll over the US valuation universe. No network: httpx.MockTransport fixtures."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from app import sec_xbrl
from app.config import Settings
from app.database import Database
from app.sec_xbrl import (
    SecContactMissing,
    SecHeaderError,
    SecRateLimiter,
    SecXbrlClient,
    SecXbrlIngestor,
    acceptance_from_header,
    acceptance_from_submissions_json,
    companyfacts_vintages,
    discrete_quarters,
    duration_months,
    is_trigger_filing,
    parse_filing_header,
    recent_filings,
    trailing_quarters,
)
from app.statement_vintages import StatementVintageStore, vintage_row_hash

from tests import asfiled_fixtures as fx

DB_DIR = Path(__file__).resolve().parents[2] / "db"
UTC = timezone.utc


class NoWaitLimiter(SecRateLimiter):
    def __init__(self) -> None:
        super().__init__(8.0, clock=lambda: 0.0, sleep=lambda seconds: None)
        self.acquired = 0

    def acquire(self) -> None:
        self.acquired += 1


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"database_url": "", "sec_contact": "contact-placeholder.invalid", "valuation_asfiled_enabled": True}
    values.update(overrides)
    return Settings(**values)


def _client(fake: fx.EdgarFake, **overrides: Any) -> SecXbrlClient:
    return SecXbrlClient(_settings(**overrides), http=httpx.Client(transport=fake.transport()), limiter=NoWaitLimiter())


# -- clocks ------------------------------------------------------------------------------------------------------------

def test_the_submissions_json_clock_is_the_true_instant_plus_the_new_york_offset() -> None:
    # VERIFIED 2026-10-17 on AAPL: header ACCEPTANCE-DATETIME (New York) vs submissions JSON acceptanceDateTime
    assert acceptance_from_submissions_json("2026-07-31T00:30:28.000Z") == acceptance_from_header("20260730163028")
    assert acceptance_from_submissions_json("2026-01-30T02:30:33Z") == acceptance_from_header("20260129163033")
    assert acceptance_from_header("20260730163028") == datetime(2026, 7, 30, 20, 30, 28, tzinfo=UTC)  # 16:30:28 EDT
    assert acceptance_from_header("20260129163033") == datetime(2026, 1, 29, 21, 30, 33, tzinfo=UTC)  # 16:30:33 EST
    # the week after each DST switch keeps the offset of the instant itself
    assert acceptance_from_submissions_json(fx.submissions_json_clock("20251105163000")) == fx.true_instant("20251105163000")
    assert acceptance_from_submissions_json(fx.submissions_json_clock("20260310163000")) == fx.true_instant("20260310163000")
    with pytest.raises(SecHeaderError):
        acceptance_from_header("2026-07-30 16:30:28")


def test_the_filing_header_is_parsed_from_the_escaped_sgml_page() -> None:
    page = fx.header_html("0000999001-26-000003", form="8-K", accepted_ny="20260212160500", period="2026-02-12", filed="2026-02-12",
                          items=("Results of Operations and Financial Condition", "Financial Statements and Exhibits"))
    header = parse_filing_header(page)
    assert header["accepted_at"] == datetime(2026, 2, 12, 21, 5, tzinfo=UTC)
    assert header["acceptance_raw"] == "20260212160500" and header["accession"] == "0000999001-26-000003" and header["form"] == "8-K"
    assert header["period_of_report"] == date(2026, 2, 12) and header["filed_date"] == date(2026, 2, 12)
    assert header["item_information"] == ["Results of Operations and Financial Condition", "Financial Statements and Exhibits"]
    assert len(header["header_sha256"]) == 64
    with pytest.raises(SecHeaderError):
        parse_filing_header("<html><pre>ACCESSION NUMBER: 1</pre></html>")


def test_recent_filings_keep_the_raw_json_clock_and_its_correction() -> None:
    filings = {filing["accession"]: filing for filing in recent_filings(fx.submissions())}
    eight_k = filings[fx.EIGHT_K_RESULTS["accession"]]
    assert eight_k["items"] == ["2.02", "9.01"] and eight_k["form"] == "8-K"
    assert eight_k["json_accepted_raw"] == fx.submissions_json_clock("20260212160500")
    assert eight_k["accepted_at_json"] == fx.true_instant("20260212160500")
    assert is_trigger_filing("8-K", eight_k["items"]) and not is_trigger_filing("8-K", ["5.02"])
    assert is_trigger_filing("10-Q", []) and is_trigger_filing("10-K/A", []) and not is_trigger_filing("S-8", [])


# -- the client --------------------------------------------------------------------------------------------------------

def test_the_client_refuses_to_exist_without_the_sec_contact() -> None:
    with pytest.raises(SecContactMissing, match="C3PO_SEC_CONTACT"):
        SecXbrlClient(_settings(sec_contact="   "))
    assert Settings().sec_contact == "" and Settings().valuation_asfiled_enabled is False  # nothing ships enabled or with a contact
    assert "sec_contact" not in repr(_settings())  # the contact never lands in a settings repr/log


def test_the_client_sends_the_contact_user_agent_and_only_calls_the_sec() -> None:
    fake = fx.EdgarFake()
    client = _client(fake)
    assert client.company_tickers() == {"SYNT": fx.CIK, "OTHR": "0000999002"}
    assert client.submissions("999001")["cik"] == fx.CIK
    assert client.companyfacts("0000999002") == {}  # 404: no XBRL facts
    header = client.filing_header(fx.CIK, "0000999001-26-000005")
    assert header["accepted_at"] == fx.true_instant("20260220163000")
    assert fake.paths()[-1] == "/Archives/edgar/data/999001/000099900126000005/0000999001-26-000005-index-headers.html"
    assert {request.headers["User-Agent"] for request in fake.requests} == {"C3PO Chief of Staff Intelligence contact-placeholder.invalid"}
    assert client.limiter.acquired == len(fake.requests) == client.requests  # type: ignore[attr-defined]
    with pytest.raises(ValueError, match="only calls the SEC"):
        client._get("https://example.com/files/company_tickers.json")


def test_the_limiter_spaces_request_starts_and_never_exceeds_eight_per_second() -> None:
    now = [100.0]
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    limiter = SecRateLimiter(50.0, clock=lambda: now[0], sleep=sleep)
    assert limiter.rate == 8.0  # capped at the fair-access ceiling
    starts = []
    for _ in range(9):
        limiter.acquire()
        starts.append(now[0])
    assert all(abs((later - earlier) - 0.125) < 1e-9 for earlier, later in zip(starts, starts[1:]))
    assert sum(1 for start in starts if start < starts[0] + 1.0) == 8  # a one-second window holds eight starts
    slow = SecRateLimiter(4.0, clock=lambda: now[0], sleep=sleep)
    assert slow.rate == 4.0
    with pytest.raises(ValueError):
        SecRateLimiter(0.0)


def test_the_process_limiter_is_shared_and_only_ever_lowered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sec_xbrl, "_PROCESS_LIMITER", None)
    first = sec_xbrl.process_rate_limiter(6.0)
    assert sec_xbrl.process_rate_limiter(8.0) is first and first.rate == 6.0
    assert sec_xbrl.process_rate_limiter(3.0) is first and first.rate == 3.0
    assert sec_xbrl.is_sec_host("data.sec.gov") and sec_xbrl.is_sec_host("www.sec.gov") and not sec_xbrl.is_sec_host("sec.gov.example.com")


# -- companyfacts → vintages -------------------------------------------------------------------------------------------

def test_companyfacts_become_one_row_per_document_fact_with_classes_summed() -> None:
    rows, stats = companyfacts_vintages(fx.companyfacts(), issuer_key=fx.CIK, since=date(2020, 1, 1))
    assert stats["other_forms"] == 1 and stats["classes_summed"] == 1 and stats["conflicting"] == 0 and stats["malformed"] == 0
    assert {row["form"] for row in rows} == {"10-Q", "10-K"} and {row["source"] for row in rows} == {"sec_xbrl_companyfacts"}
    fy25 = [row for row in rows if row["doc_id"] == "0000999001-26-000005"]
    shares = [row for row in fy25 if row["concept"] == "dei:EntityCommonStockSharesOutstanding"]
    assert len(shares) == 1 and shares[0]["value"] == Decimal(1000) and shares[0]["unit"] == "shares" and shares[0]["period_start"] is None
    revenue = {(row["period_start"], row["period_end"]): row["value"] for row in fy25 if row["concept"] == "us-gaap:Revenues"}
    assert revenue == {(date(2025, 1, 1), date(2025, 12, 31)): Decimal(400), (date(2024, 1, 1), date(2024, 12, 31)): Decimal(360)}
    assert all(row["fiscal_year"] == 2025 and row["fiscal_period"] == "FY" and row["document_version"] == 1 for row in fy25)
    eps = [row for row in rows if row["concept"] == "us-gaap:EarningsPerShareDiluted"]
    assert eps and {row["unit"] for row in eps} == {"USD/shares"}
    recent, recent_stats = companyfacts_vintages(fx.companyfacts(), issuer_key=fx.CIK, since=date(2025, 1, 1))
    assert recent_stats["before_lookback"] > 0 and min(row["period_end"] for row in recent) >= date(2025, 1, 1)


def test_conflicting_values_of_one_fact_inside_a_document_are_dropped_not_guessed() -> None:
    payload = fx.companyfacts()
    revenues = payload["facts"]["us-gaap"]["Revenues"]["units"]["USD"]
    duplicate = dict(next(item for item in revenues if item["accn"] == "0000999001-25-000030" and item.get("start") == "2025-07-01"))
    revenues.append(dict(duplicate))  # an identical repeat collapses
    rows, stats = companyfacts_vintages(payload, issuer_key=fx.CIK, since=date(2020, 1, 1))
    assert stats["conflicting"] == 0
    assert sum(1 for row in rows if row["doc_id"] == "0000999001-25-000030" and row["concept"] == "us-gaap:Revenues" and row["period_start"] == date(2025, 7, 1)) == 1
    revenues.append({**duplicate, "val": 999})
    rows, stats = companyfacts_vintages(payload, issuer_key=fx.CIK, since=date(2020, 1, 1))
    assert stats["conflicting"] == 1
    assert not any(row["doc_id"] == "0000999001-25-000030" and row["concept"] == "us-gaap:Revenues" and row["period_start"] == date(2025, 7, 1) for row in rows)


# -- quarters ----------------------------------------------------------------------------------------------------------

def _facts(*items: tuple[str, str, float]) -> dict[tuple[date, date], dict[str, Any]]:
    return {(date.fromisoformat(start), date.fromisoformat(end)): {"value": value} for start, end, value in items}


def test_year_to_date_facts_become_quarters_and_q4_is_fy_minus_nine_months() -> None:
    quarters = discrete_quarters(_facts(
        ("2025-01-01", "2025-03-31", 92), ("2025-01-01", "2025-06-30", 190), ("2025-01-01", "2025-09-30", 290),
        ("2025-01-01", "2025-12-31", 400), ("2025-07-01", "2025-09-30", 100),
    ))
    assert {key: (entry["value"], entry["derived"]) for key, entry in quarters.items()} == {
        (date(2025, 1, 1), date(2025, 3, 31)): (92.0, False),
        (date(2025, 4, 1), date(2025, 6, 30)): (98.0, True),  # 6M − 3M
        (date(2025, 7, 1), date(2025, 9, 30)): (100.0, False),  # reported wins over 9M − 6M
        (date(2025, 10, 1), date(2025, 12, 31)): (110.0, True),  # Q4 = FY − 9M
    }
    assert duration_months(date(2024, 9, 29), date(2025, 9, 27)) == 12  # a 52-week fiscal year
    assert duration_months(date(2025, 1, 1), date(2025, 2, 28)) is None
    chain = trailing_quarters(quarters)
    assert [key[1] for key in chain] == [date(2025, 12, 31), date(2025, 9, 30), date(2025, 6, 30), date(2025, 3, 31)]


def test_a_broken_quarter_chain_is_never_bridged() -> None:
    quarters = discrete_quarters(_facts(("2025-01-01", "2025-03-31", 1), ("2025-07-01", "2025-09-30", 3), ("2025-10-01", "2025-12-31", 4)))
    assert trailing_quarters(quarters, 3) == []
    assert len(trailing_quarters(quarters, 2)) == 2


# -- the store ---------------------------------------------------------------------------------------------------------

def _vintage(doc_id: str, accepted: datetime, value: float, *, start: str = "2025-07-01", end: str = "2025-09-30") -> dict[str, Any]:
    return {"market": "US", "issuer_key": fx.CIK, "source": "sec_xbrl_companyfacts", "doc_id": doc_id, "form": "10-Q", "fiscal_year": 2025,
            "fiscal_period": "Q3", "period_start": start, "period_end": end, "concept": "us-gaap:Revenues", "unit": "USD", "value": value,
            "filed_date": accepted.date(), "accepted_at": accepted}


def test_the_first_publication_is_kept_and_later_documents_are_new_rows() -> None:
    database = Database(_settings())
    store = StatementVintageStore(database)
    first = datetime(2025, 11, 5, 21, 30, tzinfo=UTC)
    counts = store.insert_vintages("US", fx.CIK, [_vintage("A-1", first, 100)])
    assert counts == {"attempted": 1, "written": 1, "first_publications": 1, "out_of_order": 0}
    later = store.insert_vintages("US", fx.CIK, [_vintage("B-2", first + timedelta(days=120), 101), _vintage("A-1", first, 100)])
    assert later["written"] == 1 and later["first_publications"] == 0  # the re-sent A-1 row is a no-op, B-2 is not first
    rows = store.vintages("US", fx.CIK)
    assert [(row["doc_id"], row["value"], row["is_first_publication"]) for row in rows] == [("A-1", Decimal(100), True), ("B-2", Decimal(101), False)]
    assert all(row["row_hash"] == vintage_row_hash(row) for row in rows)
    assert store.vintages("US", fx.CIK, accepted_at_or_before=first + timedelta(days=1)) == rows[:1]  # point in time
    early = store.insert_vintages("US", fx.CIK, [_vintage("Z-0", first - timedelta(days=1), 99)])
    assert early == {"attempted": 1, "written": 1, "first_publications": 1, "out_of_order": 1}  # stored, counted, never hidden


def test_the_store_refuses_naive_clocks_foreign_issuers_and_inverted_periods() -> None:
    store = StatementVintageStore(Database(_settings()))
    with pytest.raises(ValueError, match="naive"):
        store.insert_vintages("US", fx.CIK, [_vintage("A-1", datetime(2025, 11, 5, 16, 30), 100)])
    with pytest.raises(ValueError, match="another issuer"):
        store.insert_vintages("US", "0000000001", [_vintage("A-1", datetime(2025, 11, 5, 21, 30, tzinfo=UTC), 100)])
    with pytest.raises(ValueError, match="starts after it ends"):
        store.insert_vintages("US", fx.CIK, [_vintage("A-1", datetime(2025, 11, 5, 21, 30, tzinfo=UTC), 100, start="2025-10-01")])
    with pytest.raises(ValueError, match="lacks accepted_source"):
        store.register_filings([{"market": "US", "issuer_key": fx.CIK, "source": "sec_edgar", "doc_id": "A-1", "form": "10-Q",
                                 "filed_date": "2025-11-05", "accepted_at": datetime(2025, 11, 5, 21, 30, tzinfo=UTC)}])
    assert store.vintages("US", fx.CIK) == []


def test_the_postgresql_writer_takes_the_issuer_lock_first_and_inserts_on_the_natural_key() -> None:
    log: list[tuple[str, Any]] = []

    class Result:
        def __init__(self, rows: list[tuple] | None = None) -> None:
            self.rows = rows or []

        def fetchall(self) -> list[tuple]:
            return self.rows

    class Cursor:
        rowcount = 0

        def executemany(self, sql: str, params: list[tuple]) -> None:
            log.append((" ".join(sql.split()), len(params)))
            self.rowcount = len(params)

        def __enter__(self) -> "Cursor":
            return self

        def __exit__(self, *args: Any) -> None:
            return None

    class Connection:
        def execute(self, sql: str, params: tuple = ()) -> Result:
            log.append((" ".join(sql.split()), params))
            if "FROM statement_vintages" in sql:  # one earlier publication of the same fact is already stored
                return Result([("US", fx.CIK, "sec_xbrl_companyfacts", "us-gaap:Revenues", "USD", date(2025, 7, 1), date(2025, 9, 30), "A-1", 1,
                                datetime(2025, 11, 5, 21, 30, tzinfo=UTC))])
            return Result()

        def cursor(self) -> Cursor:
            return Cursor()

        def commit(self) -> None:
            log.append(("COMMIT", None))

    from contextlib import contextmanager

    database = Database(_settings())
    database.database_url = "postgresql://fake"

    @contextmanager
    def connection():
        yield Connection()

    database.connection = connection  # type: ignore[method-assign]
    counts = StatementVintageStore(database).insert_vintages("US", fx.CIK, [_vintage("B-2", datetime(2026, 3, 10, 20, 30, tzinfo=UTC), 101)])
    assert log[0] == ("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"statement_vintages:US:{fx.CIK}",))
    assert "ON CONFLICT ON CONSTRAINT statement_vintages_natural_key DO NOTHING" in log[2][0] and log[2][1] == 1
    assert log[-1] == ("COMMIT", None) and counts["first_publications"] == 0 and counts["written"] == 1


def test_migration_051_is_append_only_idempotent_and_keys_instants_once() -> None:
    sql = (DB_DIR / "051_statement_vintages.sql").read_text(encoding="utf-8")
    for table in ("statement_filings", "statement_vintages"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
        assert f"BEFORE UPDATE OR DELETE ON {table}" in sql and f"BEFORE TRUNCATE ON {table}" in sql
        assert f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}" in sql
    assert "UNIQUE NULLS NOT DISTINCT\n        (market, issuer_key, source, doc_id, document_version, concept, unit, period_start, period_end)" in sql
    assert "CONSTRAINT statement_filings_natural_key UNIQUE (market, source, doc_id, document_version)" in sql
    for column in ("accepted_at TIMESTAMPTZ NOT NULL", "first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()", "is_first_publication BOOLEAN NOT NULL",
                   "row_hash TEXT NOT NULL CHECK (row_hash ~ '^[0-9a-f]{64}$')", "fiscal_year INTEGER", "fiscal_period TEXT", "filed_date DATE NOT NULL"):
        assert column in sql
    assert "DROP TABLE" not in sql and "ALTER TABLE" not in sql and "DELETE FROM" not in sql
    assert max(len(line) for line in sql.splitlines()) <= 127


# -- the poll ----------------------------------------------------------------------------------------------------------

def _poll_once(database: Database, fake: fx.EdgarFake, now: datetime, ingestor: SecXbrlIngestor | None = None) -> tuple[SecXbrlIngestor, Any]:
    ingestor = ingestor or SecXbrlIngestor(database, _client(fake), backfill_per_poll=5)
    result = ingestor.poll({"SYNT": "NASDAQ", "NOPE": "NYSE"}, ingestor.client.company_tickers(), now=now)
    return ingestor, result


def test_the_poll_registers_new_filings_with_the_header_clock_and_backfills_vintages() -> None:
    database = Database(_settings())
    fake = fx.EdgarFake()
    now = datetime(2026, 2, 21, 0, 0, tzinfo=UTC)
    ingestor, result = _poll_once(database, fake, now)
    assert result.unmapped_symbols == 1 and result.issuers == 1 and result.errors == []
    assert result.trigger_filings == 2  # the 10-K and the 8-K item 2.02 of the last ten days; the 8-K 5.02 is not one
    assert result.issuers_backfilled == 1 and result.header_failures == 0 and result.json_clock_mismatches == 0
    assert result.vintages_written > 0 and result.deferred_documents == 0
    store = StatementVintageStore(database)
    filings = {row["doc_id"]: row for row in store.filings("US")}
    assert set(filings) == {doc["accession"] for doc in fx.DOCUMENTS} | {fx.EIGHT_K_RESULTS["accession"]}
    ten_k = filings["0000999001-26-000005"]
    assert ten_k["accepted_at"] == fx.true_instant("20260220163000") and ten_k["accepted_source"] == "sec_header"
    assert ten_k["json_accepted_raw"] == fx.submissions_json_clock("20260220163000") and ten_k["symbols"] == ["SYNT"]
    assert ten_k["period_of_report"] == date(2025, 12, 31) and filings[fx.EIGHT_K_RESULTS["accession"]]["items"] == "2.02,9.01"
    assert store.symbol_issuers("US") == {"SYNT": fx.CIK}
    header_requests = [path for path in fake.paths() if path.endswith("-index-headers.html")]
    assert len(header_requests) == 7 and len(set(header_requests)) == 7  # each accession's header read once
    vintages = store.vintages("US", fx.CIK)
    assert {utc_row["accepted_at"] for utc_row in vintages} <= {row["accepted_at"] for row in filings.values()}
    q3_2024 = [row for row in vintages if row["concept"] == "us-gaap:Revenues" and row["period_start"] == date(2024, 7, 1)]
    assert [(row["doc_id"], row["is_first_publication"]) for row in q3_2024] == [("0000999001-24-000030", True), ("0000999001-25-000030", False)]

    requests_before = len(fake.requests)
    _, again = _poll_once(database, fake, now, ingestor)
    assert again.filings_registered == 0 and again.vintages_written == 0 and again.issuers_ingested == 0
    assert len(fake.requests) - requests_before == 2  # the ticker file and the submissions: nothing else is re-read


def test_a_header_failure_defers_that_document_and_every_later_one() -> None:
    database = Database(_settings())
    fake = fx.EdgarFake(failing_headers={"0000999001-25-000012"})  # the Q1 2025 10-Q
    _, result = _poll_once(database, fake, datetime(2026, 2, 21, tzinfo=UTC))
    assert result.header_failures == 1 and result.deferred_documents == 4  # Q1, Q2, Q3 2025 and FY 2025 wait
    stored = StatementVintageStore(database).documents_with_vintages("US", fx.CIK)
    assert stored == {"0000999001-24-000030", "0000999001-25-000005"}  # only the documents before the gap


def test_a_fair_access_refusal_stops_the_whole_pass_at_once() -> None:
    database = Database(_settings())
    fake = fx.EdgarFake(throttled_paths={f"/submissions/CIK{fx.CIK}.json"})
    ingestor = SecXbrlIngestor(database, _client(fake), backfill_per_poll=5)
    result = ingestor.poll({"SYNT": "NASDAQ", "OTHR": "NYSE"}, {"SYNT": fx.CIK, "OTHR": "0000999002"}, now=datetime(2026, 2, 21, tzinfo=UTC))
    assert result.throttled is True and len(result.errors) == 1 and "HTTP 429" in result.errors[0]
    assert fake.paths() == [f"/submissions/CIK{fx.CIK}.json"]  # OTHR (sorted after SYNT's CIK) is never asked
    header_throttled = fx.EdgarFake(throttled_paths={"/Archives/edgar/data/999001/000099900126000005/0000999001-26-000005-index-headers.html"})
    stopped = SecXbrlIngestor(Database(_settings()), _client(header_throttled)).poll({"SYNT": "NASDAQ"}, {"SYNT": fx.CIK}, now=datetime(2026, 2, 21, tzinfo=UTC))
    assert stopped.throttled is True and stopped.header_failures == 0 and stopped.vintages_written == 0  # never counted as a mere header failure


def test_a_json_clock_that_disagrees_with_the_header_is_counted_and_the_header_wins() -> None:
    database = Database(_settings())
    naive_digits = lambda accepted_ny: datetime.strptime(accepted_ny, "%Y%m%d%H%M%S").strftime("%Y-%m-%dT%H:%M:%S.000Z")  # noqa: E731
    _, result = _poll_once(database, fx.EdgarFake(json_clock=naive_digits), datetime(2026, 2, 21, tzinfo=UTC))
    assert result.json_clock_mismatches == result.filings_registered == 7
    accepted = StatementVintageStore(database).filing_acceptances("US", ["0000999001-26-000005"])
    assert accepted == {"0000999001-26-000005": fx.true_instant("20260220163000")}


def test_a_restatement_is_a_new_vintage_and_the_original_stays_first() -> None:
    database = Database(_settings())
    ingestor, _ = _poll_once(database, fx.EdgarFake(), datetime(2026, 2, 21, tzinfo=UTC))
    restated = fx.EdgarFake(include_restatement=True)
    ingestor.client = _client(restated)
    _, result = _poll_once(database, restated, datetime(2026, 3, 11, tzinfo=UTC), ingestor)
    assert result.filings_registered == 1 and result.vintages_written == 2 and result.first_publications == 0
    rows = [row for row in StatementVintageStore(database).vintages("US", fx.CIK)
            if row["concept"] == "us-gaap:Revenues" and row["period_start"] == date(2025, 7, 1)]
    assert [(row["doc_id"], row["value"], row["is_first_publication"]) for row in rows] == [
        ("0000999001-25-000030", Decimal(100), True), ("0000999001-26-000008", Decimal(fx.RESTATED_Q3_REVENUE), False),
    ]


def test_a_document_companyfacts_has_not_processed_yet_is_retried_after_the_backoff() -> None:
    database = Database(_settings())
    fake = fx.EdgarFake()
    ingestor, _ = _poll_once(database, fake, datetime(2026, 2, 21, tzinfo=UTC))
    late = fx.EdgarFake(include_restatement=True)
    original = late.handle

    def without_restatement_facts(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/api/xbrl/companyfacts/"):
            late.requests.append(request)
            return httpx.Response(200, json=fx.companyfacts())  # the 10-Q/A is accepted, its facts not in companyfacts yet
        return original(request)

    late.handle = without_restatement_facts  # type: ignore[method-assign]
    ingestor.client = _client(late)
    now = datetime(2026, 3, 11, tzinfo=UTC)
    _, first = _poll_once(database, late, now, ingestor)
    assert first.filings_registered == 1 and first.vintages_written == 0
    facts_calls = lambda: sum(1 for path in late.paths() if path.startswith("/api/xbrl/companyfacts/"))  # noqa: E731
    assert facts_calls() == 1
    _poll_once(database, late, now + timedelta(minutes=15), ingestor)
    assert facts_calls() == 1  # inside the backoff: not re-downloaded
    late.handle = original  # type: ignore[method-assign]
    _, retried = _poll_once(database, late, now + sec_xbrl.PENDING_RETRY + timedelta(minutes=1), ingestor)
    assert retried.vintages_written == 2 and facts_calls() == 2
