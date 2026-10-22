"""Decisor V1 — the liveness of the US filings source and the event rules (owner's direction of 2026-10-17, before the
decisor freeze), after the three adversarial reviews of 17/10:

* 053 counts only while the as-filed poll is alive at D: a SUCCESSFUL run with progress that STARTED at or after D − 6 h
  and completed by D − ε (``STALENESS_SOURCE_STALE`` otherwise, judged before the table exists or not);
* ``EARNINGS_WITHIN_N`` never fails open on a bad calendar: partial / garbled / short calendars say nothing, every
  calendar's in-window events gate (the union over [D − 36 h, D − ε] and the latest before), a usable calendar without
  the name's row still gates on the 051 estimate, and each event reaches its REACTION session (AMC or untimed → next);
* the 051 estimate: originals only, seasonal first, else the most recent base;
* ``CONSENSUS_EPS_CUT_30D`` and ``NEWS_SENTIMENT_NEGATIVE`` are marks; the sentiment never enters ``replay_sha256``;
* every read on an insert clock stops at D − ε; a served record published after D − ε is not decided.

Point in time throughout. No network."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from app import valuation_asfiled as asfiled
from app import valuation_decision as decisor
from app import valuation_earnings_calendar as calendar_module
from app import valuation_env
from app.config import Settings
from app.database import Database
from app.investor_relations import InvestorRelationsService
from app.r2d2_v2_earnings_source import EarningsReceipt
from app.sec_xbrl import AsFiledPollResult, SecXbrlIngestor
from app.statement_vintages import StatementVintageStore
from app.valuation_worker import OffhoursPhase, run_worker_iteration
from app.valuation_worker_contract import VALUATION_WORKER_ADVISORY_PHASES, VALUATION_WORKER_OFFHOURS_PHASES, VALUATION_WORKER_PHASES
from tests.test_valuation_decision import CALM, CUT, ROOT, RUN, SESSION, _database, _decide, _night, _run

UTC = timezone.utc
SAO_PAULO = ZoneInfo("America/Sao_Paulo")
RECEIVED = RUN - timedelta(minutes=20)  # the calendar phase, just before the decisor's
WINDOW = ["2026-10-14", "2026-10-15"]  # T = 2026-10-13 (Tue): T+1 Wed, T+2 Thu
EPSILON = timedelta(seconds=decisor.THRESHOLDS.insert_margin_seconds)
FILLER = 120  # a whole-market calendar always carries well over the block's 100 US events


# ------------------------------------------------------------------ fixtures of the test world


def _row(code: str, report_date: str, timing: str | None = "AfterMarket", *, period: str = "2026-09-30", currency: str = "USD") -> dict[str, Any]:
    return {"code": code, "report_date": report_date, "date": period, "before_after_market": timing, "currency": currency, "actual": None,
            "estimate": 1.0, "difference": None, "percent": None}


def _filler(count: int = FILLER) -> list[dict[str, Any]]:
    return [_row(f"FILL{index:03d}.US", "2026-10-28", "BeforeMarket") for index in range(count)]


def _receipt(raw: bytes, received: datetime, start: date, end: date) -> EarningsReceipt:
    return EarningsReceipt(request_symbols=(), request_from=start, request_to=end, request_started_at=received - timedelta(seconds=2),
                           response_received_at=received, available_at=received, http_status=200, body_sha256=hashlib.sha256(raw).hexdigest(),
                           transport_complete=True, content_type="application/json")


def _body(rows: list[Any], start: date, end: date) -> bytes:
    return json.dumps({"type": "Earnings", "description": "Historical and upcoming Earnings", "from": start.isoformat(), "to": end.isoformat(),
                       "earnings": rows}).encode()


def _calendar(database: Database, rows: list[Any], *, received: datetime = RECEIVED, start: date = date(2026, 10, 7), end: date = date(2026, 11, 13),
              filler: int = FILLER) -> str:
    raw = _body([*rows, *_filler(filler)], start, end)
    return calendar_module.record_calendar(database, raw, _receipt(raw, received, start, end))


def _filing(database: Database, symbol: str, doc_id: str, form: str, accepted: datetime, *, items: str = "", period: str | None = "2026-06-30",
            seen: datetime | None = None, issuer: str = "0000999201") -> None:
    StatementVintageStore(database).register_filings([{"market": "US", "issuer_key": issuer, "source": "sec_edgar", "doc_id": doc_id, "form": form,
                                                       "items": items, "symbols": [symbol], "period_of_report": period,
                                                       "filed_date": accepted.date(), "accepted_at": accepted, "accepted_source": "sec_header"}])
    for row in database._statement_filings:  # type: ignore[attr-defined]
        if row["doc_id"] == doc_id:
            row["first_seen_at"] = seen or accepted + timedelta(minutes=10)  # registered by the poll, in the test world


def _ref(form: str, accepted: str, *, period: str | None = None, items: str = "", doc: str = "d") -> dict[str, Any]:
    return {"doc_id": doc, "form": form, "items": items, "accepted_at": accepted, "period_of_report": period}


def _consensus(database: Database, market: str, at: datetime, packets: dict[str, Any]) -> str:
    return database.save_analysis_snapshot("valuation_v2_data", f"{market}_V2_DATA", "mv-1", {"market": market}, {"packets": packets}, at)


def _fy1(eps: float, fiscal: str = "2027-09-30") -> dict[str, Any]:
    return {"fy1_estimate": {"fiscal_year_end": fiscal, "eps_avg": eps}, "forward_estimates": [{"fiscal_year_end": fiscal, "eps_avg": eps},
                                                                                               {"fiscal_year_end": "2028-09-30", "eps_avg": eps * 1.1}]}


def _sentiment(database: Database, symbol: str, published: datetime, *, bearish: float, articles: int) -> None:
    database.save_ir_events([{"source_code": "finnhub", "external_id": f"finnhub-sentiment-{symbol}-{published:%G-W%V}", "company_id": None,
                              "market": "US", "symbol": symbol, "company_name": symbol, "regulator_id": None, "event_type": "News Sentiment", "form": None,
                              "title": "sentiment", "summary": "sentiment", "published_at": published, "published_time_precision": "collected",
                              "reference_date": published.date(), "official_url": None, "document_url": None, "materiality": "low",
                              "valuation_relevant": False, "valuation_status": "informational",
                              "raw_metadata": {"source": "finnhub", "bullish_percent": 100.0 - bearish, "bearish_percent": bearish,
                                               "articles_last_week": articles, "company_news_score": 0.4},
                              "collected_at": published}])


def _poll_run(database: Database, *, started: datetime, completed: datetime, status: str = "succeeded", records: int = 1) -> str:
    run_id = database.begin_ingestion_run("sec_asfiled", "SEC EDGAR as-filed statements", "regulatory_disclosure",
                                         {"operation": "valuation_universe", "failed_issuers": [], "unattributed_failures": 0})  # a complete pass: every issuer observed
    database.finish_ingestion_run(run_id, status, records, 0)
    database._ingestion_runs[run_id].update(started_at=started, completed_at=completed)
    return run_id


def _record(database: Database, market: str, symbol: str) -> dict[str, Any]:
    return database.list_valuation_decisions(market, symbol)[0]


US_CLEAR = {"status": "clear", "source_status": "ok", "filings": []}  # a US name with a live poll and no mark


def _us_row(symbol: str = "AAPL", **extra: Any) -> dict[str, Any]:
    from tests.test_valuation_decision import _row as served_row
    return {**served_row(symbol, tp=130.0, buy_in=105.0, price=100.0, market="NASDAQ"), "official_session_date": SESSION, **extra}


def _calendars(by_code: dict[str, list[dict[str, Any]]], *, received: datetime = RECEIVED, us_events: int = 150, share: float = 0.0,
               start: str = "2026-10-07", end: str = "2026-11-13", snapshot_id: str = "cal-1",
               blocking: dict[str, list[str]] | None = None) -> dict[str, Any]:
    calendar = {"snapshot_id": snapshot_id, "received_at": received.isoformat(), "payload_sha256": "f" * 64, "request_from": start, "request_to": end,
                "by_code": by_code, "blocking_codes": blocking or {}, "us_events": us_events, "rows": us_events, "unattributed_invalid_rows": 0,
                "invalid_share": share}
    return {"recent": [calendar], "older": None}


# ------------------------------------------------------------------ B. the 053 source must be alive at D


@pytest.mark.parametrize(("started", "completed", "status", "records", "fresh"), [
    (None, None, "succeeded", 1, False),  # no poll at all
    (RUN - timedelta(hours=6), RUN - timedelta(hours=5), "succeeded", 1, True),  # started exactly 6 h before: its observations count
    (RUN - timedelta(hours=6, seconds=1), RUN - timedelta(hours=5), "succeeded", 1, False),  # completed recently, but observed 6 h + 1 s ago
    (RUN - timedelta(minutes=30), RUN - EPSILON, "succeeded", 1, True),  # completed exactly ε before the clock
    (RUN - timedelta(minutes=30), RUN - EPSILON + timedelta(seconds=1), "succeeded", 1, False),  # inside the ε margin: a racing commit
    (RUN - timedelta(minutes=30), RUN + timedelta(seconds=1), "succeeded", 1, False),  # finished after D
    (RUN - timedelta(minutes=30), RUN - timedelta(minutes=20), "failed", 1, False),
    (RUN - timedelta(minutes=30), RUN - timedelta(minutes=20), "partial", 1, False),  # throttled by the SEC
    (RUN - timedelta(minutes=30), RUN - timedelta(minutes=20), "succeeded", 0, False),  # no progress: read nothing
])
def test_the_053_marks_count_only_while_the_as_filed_poll_is_alive_at_the_runs_clock(started: datetime | None, completed: datetime | None, status: str,
                                                                                      records: int, fresh: bool) -> None:
    database = _database()
    _night(database, poll=False)
    if started is not None and completed is not None:
        _poll_run(database, started=started, completed=completed, status=status, records=records)
    receipt = _run(database)
    for market in ("NASDAQ", "NYSE"):
        assert (decisor.STALENESS_SOURCE_STALE in receipt["markets"][market]["reasons"]) is (not fresh), market
    assert receipt["markets"]["B3"]["verdicts"] == {"COMPRA_PERMITIDA": 1, "OBSERVAR": 1, "VETO": 0}  # B3: not applicable
    aapl = _record(database, "NASDAQ", "AAPL")
    gate = aapl["checks"]["tp_staleness"]
    if fresh:
        assert aapl["verdict"] == decisor.COMPRA_PERMITIDA and gate["source_status"] == "ok"
        assert gate["trigger_poll"]["started_at"] == started.isoformat() and gate["trigger_poll"]["records_read"] == records  # type: ignore[union-attr]
    else:
        assert aapl["verdict"] == decisor.OBSERVAR and aapl["reason_codes"] == [decisor.STALENESS_SOURCE_STALE] and gate["source_status"] == "stale"


def test_a_poll_inside_the_margin_never_hides_the_live_one_before_it() -> None:
    database = _database()
    _night(database, poll=False)
    _poll_run(database, started=RUN - timedelta(minutes=20), completed=RUN - timedelta(minutes=10))  # live
    _poll_run(database, started=RUN - timedelta(minutes=2), completed=RUN - timedelta(seconds=30))  # racing the run's read: not read at all
    _run(database)
    gate = _record(database, "NASDAQ", "AAPL")["checks"]["tp_staleness"]
    assert gate["source_status"] == "ok" and gate["trigger_poll"]["completed_at"] == (RUN - timedelta(minutes=10)).isoformat()


def test_a_throttled_as_filed_poll_is_recorded_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(valuation_env.ASFILED_ENABLED_ENV, "true")
    settings = Settings(database_url="", auth_cookie_secure=False)
    database = Database(settings)
    service = InvestorRelationsService(settings, database, read_sec_headers=True)
    for throttled, expected in ((True, "partial"), (False, "succeeded")):
        result = AsFiledPollResult(issuers=40, submissions_read=40, filings_registered=1, vintages_written=3, throttled=throttled)
        service._asfiled_ingestor = SimpleNamespace(client=SimpleNamespace(company_tickers=lambda: {}),  # type: ignore[assignment]
                                                    poll=lambda universe, tickers, now, result=result: result)
        service.sync_sec_asfiled()
        latest = max((run for run in database._ingestion_runs.values() if run["source_code"] == "sec_asfiled"), key=lambda run: run["started_at"])
        assert latest["status"] == expected and latest["records_read"] == 40


class _Submissions:
    """An SEC client double: the ticker map, and the submissions of each issuer — or the timeout one of them hits."""

    def __init__(self, tickers: dict[str, str], failing: set[str]) -> None:
        self.tickers, self.failing = tickers, failing

    def company_tickers(self) -> dict[str, str]:
        return dict(self.tickers)

    def submissions(self, cik: str) -> dict[str, Any]:
        if cik in self.failing:
            raise httpx.ReadTimeout("submissions timed out")
        return {"filings": {"recent": {"accessionNumber": []}}}


def test_the_unobserved_issuers_are_read_from_the_passes_own_errors() -> None:
    from app.investor_relations import asfiled_failed_issuers
    errors = ["0000999201: ReadTimeout", "0000999202: SEC throttled the pass (403)", "0000999201: KeyError", "not an issuer: ValueError", "123: short"]
    assert asfiled_failed_issuers(errors) == ["0000999201", "0000999202"] and asfiled_failed_issuers([]) == []


def test_a_poll_covers_only_the_issuers_it_observed(monkeypatch: pytest.MonkeyPatch) -> None:
    # AAPL's submissions time out, KO's are read: the run succeeds with progress (records_read = 1) — it is alive for KO,
    # never for AAPL, whose 053 marks nobody checked in this pass
    monkeypatch.setenv(valuation_env.ASFILED_ENABLED_ENV, "true")
    database = _database()
    _night(database, poll=False)
    _filing(database, "AAPL", "0000999201-26-000011", "10-Q", datetime(2026, 8, 20, 20, 30, tzinfo=UTC), issuer="0000999201")
    _filing(database, "KO", "0000999202-26-000011", "10-Q", datetime(2026, 8, 20, 20, 30, tzinfo=UTC), issuer="0000999202")
    service = InvestorRelationsService(Settings(database_url="", auth_cookie_secure=False), database, read_sec_headers=True)
    client = _Submissions({"AAPL": "0000999201", "KO": "0000999202"}, failing={"0000999201"})
    service._asfiled_ingestor = SecXbrlIngestor(database, client)  # type: ignore[arg-type]
    service.sync_sec_asfiled()
    run = next(run for run in database._ingestion_runs.values() if run["source_code"] == "sec_asfiled")
    assert run["status"] == "succeeded" and run["records_read"] == 1
    assert run["metadata"]["failed_issuers"] == ["0000999201"] and run["metadata"]["issuers"] == 2  # issuer keys only, no symbol
    run.update(started_at=RUN - timedelta(minutes=30), completed_at=RUN - timedelta(minutes=20))  # the pass, in the test world
    _run(database)
    aapl, ko = _record(database, "NASDAQ", "AAPL"), _record(database, "NYSE", "KO")
    assert aapl["verdict"] == decisor.OBSERVAR and aapl["reason_codes"] == [decisor.STALENESS_SOURCE_STALE]
    gate = aapl["checks"]["tp_staleness"]
    assert gate["source_status"] == "stale" and aapl["inputs"]["tp_staleness"]["issuer_observed"] is False
    assert "did not observe the name's issuer" in gate["detail"]
    assert gate["trigger_poll"]["issuers_not_observed"] == 1
    assert decisor.STALENESS_SOURCE_STALE not in ko["reason_codes"] and ko["inputs"]["tp_staleness"]["issuer_observed"] is True
    # a name whose issuer is unknown is not covered by a poll that missed issuers; by a complete one it is
    unknown = decisor.name_staleness({"status": "ok", "known_at": RUN.isoformat(), "pending": {}, "poll_coverage": {"known": True, "failed_issuers": ["0000999201"], "unattributed_failures": 0},
                                      "trigger_poll": aapl["checks"]["tp_staleness"]["trigger_poll"]}, "NASDAQ", "NEWCO")
    assert unknown["source_status"] == "stale" and "issuer is unknown" in unknown["detail"]
    complete = decisor.name_staleness({"status": "ok", "known_at": RUN.isoformat(), "pending": {}, "poll_coverage": {"known": True, "failed_issuers": [], "unattributed_failures": 0},
                                       "trigger_poll": aapl["checks"]["tp_staleness"]["trigger_poll"]}, "NASDAQ", "NEWCO")
    assert complete["source_status"] == "ok"


class _HeaderTimeout(_Submissions):
    """The issuer's submissions list a NEW trigger 10-Q; reading its filing header times out (nothing is registered)."""

    def submissions(self, cik: str) -> dict[str, Any]:
        accepted = datetime.now(timezone.utc) - timedelta(days=1)
        return {"filings": {"recent": {"accessionNumber": [f"{cik}-26-000099"], "form": ["10-Q"], "items": [""], "filingDate": [accepted.date().isoformat()],
                                       "reportDate": ["2026-09-30"], "acceptanceDateTime": [accepted.strftime("%Y-%m-%dT%H:%M:%S.000Z")],
                                       "primaryDocument": ["x.htm"]}}}

    def filing_header(self, cik: str, accession: str) -> dict[str, Any]:
        raise httpx.ReadTimeout("header timed out")

    def companyfacts(self, cik: str) -> dict[str, Any]:
        return {}


def test_a_failed_filing_header_never_reads_as_an_observed_issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(valuation_env.ASFILED_ENABLED_ENV, "true")
    database = _database()
    _night(database, poll=False)
    _filing(database, "AAPL", "0000999201-26-000011", "10-Q", datetime(2026, 8, 20, 20, 30, tzinfo=UTC), issuer="0000999201")
    _filing(database, "KO", "0000999202-26-000011", "10-Q", datetime(2026, 8, 20, 20, 30, tzinfo=UTC), issuer="0000999202")
    service = InvestorRelationsService(Settings(database_url="", auth_cookie_secure=False), database, read_sec_headers=True)
    service._asfiled_ingestor = SecXbrlIngestor(database, _HeaderTimeout({"AAPL": "0000999201"}, failing=set()))  # type: ignore[arg-type]
    monkeypatch.setattr("app.investor_relations.us_valuation_universe", lambda db: {"AAPL": "NASDAQ"})
    service.sync_sec_asfiled()
    run = next(run for run in database._ingestion_runs.values() if run["source_code"] == "sec_asfiled")
    assert run["status"] == "succeeded" and run["metadata"]["failed_issuers"] == ["0000999201"]  # named by the watched client
    assert run["metadata"]["header_failures"] == 1 and run["metadata"]["unattributed_failures"] == 0
    run.update(started_at=RUN - timedelta(minutes=30), completed_at=RUN - timedelta(minutes=20))
    _run(database)
    aapl, ko = _record(database, "NASDAQ", "AAPL"), _record(database, "NYSE", "KO")
    assert aapl["reason_codes"] == [decisor.STALENESS_SOURCE_STALE] and "did not observe the name's issuer" in aapl["checks"]["tp_staleness"]["detail"]
    assert decisor.STALENESS_SOURCE_STALE not in ko["reason_codes"]


class _HeaderWithoutDate(_HeaderTimeout):
    """The header reads, but neither it nor the submissions carry a filed date: register_filing counts a header failure
    without raising — nobody can name the issuer from the pass, so the whole pass covers no name."""

    def submissions(self, cik: str) -> dict[str, Any]:
        payload = super().submissions(cik)
        payload["filings"]["recent"]["filingDate"] = [None]
        return payload

    def filing_header(self, cik: str, accession: str) -> dict[str, Any]:
        return {"accepted_at": datetime.now(timezone.utc) - timedelta(days=1), "filed_date": None, "form": "10-Q"}


def test_a_header_failure_nobody_can_attribute_covers_no_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(valuation_env.ASFILED_ENABLED_ENV, "true")
    database = _database()
    service = InvestorRelationsService(Settings(database_url="", auth_cookie_secure=False), database, read_sec_headers=True)
    service._asfiled_ingestor = SecXbrlIngestor(database, _HeaderWithoutDate({"AAPL": "0000999201"}, failing=set()))  # type: ignore[arg-type]
    monkeypatch.setattr("app.investor_relations.us_valuation_universe", lambda db: {"AAPL": "NASDAQ"})
    service.sync_sec_asfiled()
    run = next(run for run in database._ingestion_runs.values() if run["source_code"] == "sec_asfiled")
    assert run["metadata"]["header_failures"] == 1 and run["metadata"]["unattributed_failures"] == 1 and run["metadata"]["failed_issuers"] == []


def test_unattributed_failures_and_unknown_coverage_cover_no_name() -> None:
    from app.investor_relations import asfiled_unparsed_errors
    assert asfiled_unparsed_errors(["0000999201: ReadTimeout", "320193: ReadTimeout", "boom"]) == 2  # a short CIK names no issuer
    for metadata, why in (({"failed_issuers": [], "unattributed_failures": 2}, "2 failure(s) naming no issuer"),
                          ({"operation": "valuation_universe"}, "recorded no coverage"),  # a run from before the deploy
                          ({"failed_issuers": []}, "recorded no coverage")):
        database = _database()
        _night(database, poll=False)
        run_id = _poll_run(database, started=RUN - timedelta(minutes=30), completed=RUN - timedelta(minutes=20))
        database._ingestion_runs[run_id]["metadata"] = metadata
        _run(database)
        for market, symbol in (("NASDAQ", "AAPL"), ("NYSE", "KO")):
            gate = _record(database, market, symbol)["checks"]["tp_staleness"]
            assert gate["source_status"] == "stale" and why in gate["detail"], (metadata, symbol)


def test_a_calendar_receipt_from_the_future_never_defers_the_decisor() -> None:
    database = _database()
    _night(database)
    _calendar(database, [], received=datetime(2030, 1, 1, tzinfo=UTC))
    assert decisor.not_before(database, now=RUN) is None  # a bad clock: logged and ignored
    assert decisor.not_before(database, now=datetime(2030, 1, 1, tzinfo=UTC) - EPSILON) == datetime(2030, 1, 1, tzinfo=UTC) + EPSILON  # the edge


def test_the_decisor_waits_until_the_calendar_it_just_collected_is_readable(monkeypatch: pytest.MonkeyPatch) -> None:
    # the real calendar service and the real phases, one worker clock: the calendar lands at 01:30 BRT and AAPL reports
    # tomorrow before the open; the decisor does not run inside the ε margin (it would decide without that calendar)
    database = _database()
    _night(database)
    world = {"now": RUN}
    body = _body([_row("AAPL.US", "2026-10-14", "BeforeMarket"), *_filler()], date(2026, 10, 7), date(2026, 11, 13))
    service = calendar_module.EarningsCalendarService(
        _settings(), database, clock=lambda: world["now"],
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body, headers={"content-type": "application/json"})))
    phases = (OffhoursPhase("earnings_calendar", service.last_run_at, service.run, max_failures=3),
              OffhoursPhase("decisor_shadow", lambda: decisor.last_run_at(database),
                            lambda: decisor.run_shadow(database, now=world["now"], write=True, enabled=True),
                            not_before=lambda: decisor.not_before(database)))
    local = RUN.astimezone(SAO_PAULO)
    first = run_worker_iteration(database, now=local, canonical_due=False, canonical_operation=lambda: None, offhours_phases=phases)
    assert first.phase_statuses == {"earnings_calendar": "succeeded", "decisor_shadow": "deferred"}
    assert first.next_wake_at == local + EPSILON and database.list_valuation_decisions("NASDAQ", "AAPL") == []  # nothing recorded, not done
    assert decisor.last_run_at(database) is None
    world["now"] = RUN + EPSILON
    second = run_worker_iteration(database, now=local + EPSILON, canonical_due=False, canonical_operation=lambda: None, offhours_phases=phases)
    assert second.phase_statuses == {"decisor_shadow": "succeeded"}
    aapl = _record(database, "NASDAQ", "AAPL")
    assert aapl["reason_codes"] == [decisor.EARNINGS_WITHIN_N] and aapl["checks"]["events"]["earnings"]["calendars"][0]["received_at"] == RUN.isoformat()
    # without the deferral the same run would have decided without the calendar (received inside its margin)
    assert decisor.not_before(_database()) is None


def test_a_stale_poll_keeps_the_marks_known_and_adds_its_own_code() -> None:
    database = _database()
    _night(database, poll=False)
    _poll_run(database, started=RUN - timedelta(hours=8), completed=RUN - timedelta(hours=7))
    asfiled.TpStalenessStore(database).append([{"market": "NASDAQ", "symbol": "AAPL", "issuer_key": "0000999101", "doc_id": "0000999101-26-000007",
                                                "form": "8-K", "items": "2.02", "accepted_at": CUT - timedelta(hours=7), "period_of_report": None,
                                                "state": "stale", "reason": "tp_predates_acceptance", "official_cycle_id": None, "prediction_instant": None,
                                                "fundamentals_as_of": None, "expected_period_end": None, "covers_period": False, "queued_for_cut_at": None,
                                                "recorded_at": CUT - timedelta(hours=6)}])
    _run(database)
    assert _record(database, "NASDAQ", "AAPL")["reason_codes"] == [decisor.TP_STALE_AFTER_FILING, decisor.STALENESS_SOURCE_STALE]


def test_the_poll_is_judged_first_so_a_night_from_before_053_replays_identically() -> None:
    database = _database()
    _night(database, staleness_table=False, poll=False)
    _run(database)  # no table, nobody looking: STALENESS_SOURCE_STALE (not UNAVAILABLE)
    asfiled.TpStalenessStore(database)  # the migration lands after the night...
    _poll_run(database, started=RUN + timedelta(days=1), completed=RUN + timedelta(days=1, minutes=5))  # ...and the poll starts
    _run(database)
    rerun, original = database.list_valuation_decisions("NASDAQ", "AAPL")
    assert original["reason_codes"] == rerun["reason_codes"] == [decisor.STALENESS_SOURCE_STALE]
    assert decisor.replay_sha256(rerun) == decisor.replay_sha256(original)
    # with a live poll and no table the source is what it is: unavailable
    database = _database()
    _night(database, staleness_table=False)
    _run(database)
    assert _record(database, "NASDAQ", "AAPL")["reason_codes"] == [decisor.STALENESS_SOURCE_UNAVAILABLE]


# ------------------------------------------------------------------ A. EARNINGS_WITHIN_N: reaction sessions, the window


@pytest.mark.parametrize(("report_date", "timing", "within"), [
    ("2026-10-14", "BeforeMarket", True),  # T+1, reacts on T+1
    ("2026-10-14", "AfterMarket", True),  # an AMC on T+1 reacts on T+2: both inside
    ("2026-10-15", None, True),  # T+2, untimed: reacts T+2 or T+3
    ("2026-10-15", "AfterMarket", True),  # reported on T+2 (reacts on T+3): the report session is inside
    ("2026-10-13", "AfterMarket", True),  # an AMC on T: the price the night decides on has not seen it — reacts on T+1 (gap risk)
    ("2026-10-13", None, True),  # untimed on T: may be after the close — reacts on T+1
    ("2026-10-13", "BeforeMarket", False),  # a BMO on T: T's close already saw it
    ("2026-10-16", "BeforeMarket", False),  # T+3
    ("2026-10-17", None, False),  # a Saturday reaches Monday 10-19 (T+4)
])
def test_an_announcement_reaching_sessions_t1_to_tn_withholds_the_us_permission(report_date: str, timing: str | None, within: bool) -> None:
    database = _database()
    _night(database)
    _calendar(database, [_row("AAPL.US", report_date, timing), _row("KO.US", "2026-10-28", "BeforeMarket")])
    receipt = _run(database)
    aapl = _record(database, "NASDAQ", "AAPL")
    earnings = aapl["checks"]["events"]["earnings"]
    assert earnings["status"] == "calendar" and earnings["window"] == WINDOW and earnings["within"] is within
    assert earnings["calendars"][0]["refused"] is None and earnings["calendars"][0]["us_events"] == FILLER + 2
    assert aapl["checks"]["counterfactual"]["verdict_without_events"] == decisor.COMPRA_PERMITIDA
    if within:
        assert aapl["verdict"] == decisor.OBSERVAR and aapl["reason_codes"] == [decisor.EARNINGS_WITHIN_N]
        assert receipt["markets"]["NASDAQ"]["reasons"] == {decisor.EARNINGS_WITHIN_N: 1}
    else:
        assert aapl["verdict"] == decisor.COMPRA_PERMITIDA and aapl["checks"]["events"]["marks"] == []


def test_reaction_sessions_follow_the_exchange_calendar() -> None:
    assert decisor.reaction_sessions("NASDAQ", "2026-11-25", "AfterMarket") == ("2026-11-25", "2026-11-27")  # Thanksgiving skipped
    assert decisor.reaction_sessions("NASDAQ", "2026-11-26", "BeforeMarket") == ("2026-11-27", "2026-11-27")  # a holiday reaches the next session
    assert decisor.reaction_sessions("NASDAQ", "2026-11-26", None) == ("2026-11-27", "2026-11-27")
    assert decisor.reaction_sessions("NASDAQ", "2026-10-17", "AfterMarket") == ("2026-10-19", "2026-10-19")  # a Saturday
    assert decisor.reaction_sessions("B3", "2026-10-09", "AfterMarket") == ("2026-10-09", "2026-10-13")  # 10-12 is a B3 holiday
    assert decisor.reaction_sessions("B3", "2026-10-12", "BeforeMarket") == ("2026-10-13", "2026-10-13")


def test_the_window_is_n_sessions_of_the_block() -> None:
    database = _database()
    _night(database)
    _calendar(database, [_row("AAPL.US", "2026-10-16", "BeforeMarket")])  # T+3
    assert decisor.run_shadow(database, now=RUN)["markets"]["NASDAQ"]["verdicts"]["COMPRA_PERMITIDA"] == 1
    wider = replace(decisor.THRESHOLDS, earnings_window_sessions=3)
    assert decisor.run_shadow(database, now=RUN, thresholds=wider)["markets"]["NASDAQ"]["reasons"] == {decisor.EARNINGS_WITHIN_N: 1}
    assert decisor.name_earnings({}, None, "NASDAQ", "AAPL", at=RUN, expected_session=SESSION,
                                 thresholds=replace(decisor.THRESHOLDS, earnings_window_sessions=0))["window"] == []


def test_on_b3_an_announcement_is_a_mark_and_never_withholds_the_permission() -> None:
    database = _database()
    _night(database)
    _calendar(database, [_row("PETR4.SA", "2026-10-14", "AfterMarket", currency="BRL")])
    receipt = _run(database)
    petr = _record(database, "B3", "PETR4")
    assert petr["verdict"] == decisor.COMPRA_PERMITIDA and petr["checks"]["events"]["marks"] == [decisor.EARNINGS_WITHIN_N]
    assert petr["checks"]["events"]["gates"] == []  # VALE3 is not in the calendar and B3 has no estimate: unavailable, said so
    assert receipt["markets"]["B3"]["marks"] == {decisor.EARNINGS_WITHIN_N: 1, decisor.EARNINGS_CALENDAR_UNAVAILABLE: 1}
    assert decisor.latest_verdict(database, "B3", "PETR4", now=datetime(2026, 10, 14, 15, 0, tzinfo=UTC))["marks"] == [decisor.EARNINGS_WITHIN_N]  # type: ignore[index]


def test_the_gate_takes_the_rows_market_when_the_events_omit_it_and_fails_closed_without_one() -> None:
    within = {"status": "calendar", "within": True}
    assert _decide(_us_row(), events={"market": "US", "earnings": within})["reason_codes"] == [decisor.EARNINGS_WITHIN_N]  # both US exchanges
    assert _decide(_us_row(official_market="NASDAQ"), staleness=US_CLEAR, events={"earnings": within})["reason_codes"] == [decisor.EARNINGS_WITHIN_N]
    assert _decide(_us_row(), events={"earnings": within})["reason_codes"] == [decisor.EARNINGS_WITHIN_N]  # nobody named the market
    assert _decide(_us_row(official_market="B3"), events={"earnings": within})["verdict"] == decisor.COMPRA_PERMITIDA  # B3: a mark


def test_a_share_class_is_found_under_the_providers_spelling() -> None:
    calendars = _calendars({"BRK-B.US": [{"code": "BRK-B.US", "report_date": "2026-10-14", "timing": "BeforeMarket", "fiscal_period_end": "2026-09-30"}]})
    earnings = decisor.name_earnings(calendars, None, "NYSE", "BRK.B", at=RUN, expected_session=SESSION)
    assert earnings["status"] == "calendar" and earnings["within"] is True and earnings["events"][0]["code"] == "BRK-B.US"


# ------------------------------------------------------------------ A. a bad calendar never says "no event"


@pytest.mark.parametrize(("filler", "listed", "extra", "why"), [
    (0, False, [], "partial: 0 US events"),  # an empty calendar (zero US events)
    (98, True, [], "partial: 99 US events"),  # under the floor of 100: 98 filler + KO
    (FILLER, True, ["garbage"] * 8, "garbled"),  # 8 unattributed invalid rows of 129 (6.2 % > 5 %)
])
def test_an_empty_partial_or_garbled_calendar_says_nothing_and_the_estimate_answers(filler: int, listed: bool, extra: list[Any], why: str) -> None:
    database = _database()
    _night(database)
    _calendar(database, [*([_row("KO.US", "2026-10-28")] if listed else []), *extra], filler=filler)
    _filing(database, "AAPL", "0000999201-26-000001", "10-Q", datetime(2026, 7, 15, 20, 30, tzinfo=UTC))  # + 91 d = 10-14 (T+1)
    _run(database)
    aapl, ko = _record(database, "NASDAQ", "AAPL"), _record(database, "NYSE", "KO")
    earnings = aapl["checks"]["events"]["earnings"]
    assert earnings["status"] == "estimated" and why in earnings["detail"] and earnings["calendars"][0]["refused"].startswith(why.split(":")[0])
    assert aapl["reason_codes"] == [decisor.EARNINGS_WITHIN_N] and aapl["checks"]["events"]["marks"] == [decisor.EARNINGS_DATE_ESTIMATED]
    # KO is listed out of the window, but that calendar cannot answer, and KO has no 051 filing: no gate, said so
    assert ko["checks"]["events"]["earnings"]["status"] == "unavailable" and ko["checks"]["events"]["marks"] == [decisor.EARNINGS_CALENDAR_UNAVAILABLE]


OUT_OF_WINDOW = {"AAPL.US": [{"code": "AAPL.US", "report_date": "2026-10-29", "timing": "BeforeMarket", "fiscal_period_end": "2026-09-30"}]}


def _status(calendars: dict[str, Any]) -> str:
    return str(decisor.name_earnings(calendars, None, "NASDAQ", "AAPL", at=RUN, expected_session=SESSION)["status"])


def test_the_usability_limits_of_a_calendar_are_exact() -> None:
    assert _status(_calendars(OUT_OF_WINDOW, share=0.05)) == "calendar"  # the share limit is inclusive...
    assert _status(_calendars(OUT_OF_WINDOW, share=0.0501)) == "unavailable"  # ...and strict above it
    assert _status(_calendars(OUT_OF_WINDOW, us_events=100)) == "calendar"
    assert _status(_calendars(OUT_OF_WINDOW, us_events=99)) == "unavailable"
    # coverage: the request window must include T+1 and T+N, its own ends included
    assert _status(_calendars(OUT_OF_WINDOW, start="2026-10-14")) == "calendar"
    assert _status(_calendars(OUT_OF_WINDOW, end="2026-10-15")) == "calendar"
    short = decisor.name_earnings(_calendars(OUT_OF_WINDOW, end="2026-10-14"), None, "NASDAQ", "AAPL", at=RUN, expected_session=SESSION)
    assert short["status"] == "unavailable" and "does not cover sessions T+1..T+N" in short["calendars"][0]["refused"]
    assert _status(_calendars(OUT_OF_WINDOW, start="2026-10-15")) == "unavailable"


def test_a_calendar_is_judged_by_its_us_events_inside_its_request_window_and_its_unattributed_rows() -> None:
    def parsed(**outputs: Any) -> dict[str, Any]:
        result = calendar_module._parsed({"id": "s", "published_at": RUN, "outputs": {"schema": calendar_module.SCHEMA,
                                                                                         "request": {"from": "2026-10-07", "to": "2026-11-13"}, **outputs}})
        assert result is not None
        return result

    outside = [{"code": f"X{index}.US", "report_date": "2026-12-01"} for index in range(150)]  # US, outside the request window
    brazil = [{"code": f"Y{index}.SA", "report_date": "2026-10-20"} for index in range(150)]  # inside, not US
    inside = [{"code": f"Z{index}.US", "report_date": date_} for index, date_ in enumerate(["2026-10-07", "2026-11-13", "2026-10-20"])]
    assert parsed(events=[*outside, *brazil, *inside], rows=303)["us_events"] == 3  # only US events inside the window, its ends included
    # the share counts UNATTRIBUTED invalid rows only: names with an invalid row are judged one by one
    attributed = parsed(events=inside, rows=200, invalid_rows=100, unattributed_invalid_rows=0, blocking_codes={"Q.US": ["DATE_INVALID"]})
    assert attributed["invalid_share"] == 0.0
    assert parsed(events=inside, rows=100, invalid_rows=10, unattributed_invalid_rows=6)["invalid_share"] == 0.06
    assert parsed(events=[], rows=0)["invalid_share"] == 1.0  # an empty calendar is all doubt


def test_a_stale_calendars_in_window_event_still_gates_but_its_silence_says_nothing() -> None:
    database = _database()
    _night(database)
    _calendar(database, [_row("AAPL.US", "2026-10-14", "BeforeMarket")], received=RUN - timedelta(hours=36, seconds=1))
    _run(database)
    aapl, ko = _record(database, "NASDAQ", "AAPL"), _record(database, "NYSE", "KO")
    assert aapl["reason_codes"] == [decisor.EARNINGS_WITHIN_N] and aapl["checks"]["events"]["earnings"]["status"] == "calendar"
    refused = ko["checks"]["events"]["earnings"]["calendars"][0]["refused"]
    assert "more than 36 h" in refused and ko["checks"]["events"]["earnings"]["status"] == "unavailable"
    # the edge: received exactly 36 h before, it may still say "no event"
    database = _database()
    _night(database)
    _calendar(database, [_row("KO.US", "2026-10-28")], received=RUN - timedelta(hours=36))
    _run(database)
    assert _record(database, "NYSE", "KO")["checks"]["events"]["earnings"]["status"] == "calendar"


def test_the_union_of_the_windows_calendars_gates_on_any_of_them() -> None:
    database = _database()
    _night(database)
    _calendar(database, [_row("AAPL.US", "2026-10-14", "BeforeMarket")], received=RUN - timedelta(hours=20))  # lists AAPL on T+1
    _calendar(database, [_row("KO.US", "2026-10-28", "BeforeMarket")], received=RUN - timedelta(hours=1))  # the latest omits it
    _run(database)
    aapl = _record(database, "NASDAQ", "AAPL")
    assert aapl["reason_codes"] == [decisor.EARNINGS_WITHIN_N] and len(aapl["checks"]["events"]["earnings"]["calendars"]) == 2


INVALID_AAPL = {**_row("AAPL.US", "2026-10-14"), "report_date": "2026-10-14T00:00"}  # a row of the name the parser refuses
JULY_RELEASE = ("AAPL", "0000999201-26-000001", "8-K", datetime(2026, 7, 15, 20, 30, tzinfo=UTC))  # + 91 d = 10-14 (T+1)


def _aapl_after(*calendars: tuple[list[Any], datetime], estimate: bool = False) -> dict[str, Any]:
    database = _database()
    _night(database)
    for rows, received in calendars:
        _calendar(database, rows, received=received)
    if estimate:
        _filing(database, *JULY_RELEASE, items="2.02")
    _run(database)
    return _record(database, "NASDAQ", "AAPL")


def test_any_calendar_read_gates_and_only_the_newest_usable_one_says_no_event() -> None:
    # P1: the latest calendar before the window lists AAPL in the window; the recent usable one omits it; no estimate
    aapl = _aapl_after(([_row("AAPL.US", "2026-10-14", "BeforeMarket")], RUN - timedelta(hours=40)), ([_row("KO.US", "2026-10-28")], RUN - timedelta(hours=2)))
    assert aapl["reason_codes"] == [decisor.EARNINGS_WITHIN_N] and aapl["checks"]["events"]["earnings"]["status"] == "calendar"
    assert [item["snapshot_id"] for item in aapl["checks"]["events"]["earnings"]["calendars"]] and len(aapl["checks"]["events"]["earnings"]["calendars"]) == 2
    # only the LATEST calendar before the window is read: an even older one is not
    aapl = _aapl_after(([_row("AAPL.US", "2026-10-14", "BeforeMarket")], RUN - timedelta(hours=50)), ([_row("KO.US", "2026-10-28")], RUN - timedelta(hours=40)),
                       ([_row("AAPL.US", "2026-10-29")], RUN - timedelta(hours=2)))
    assert aapl["verdict"] == decisor.COMPRA_PERMITIDA and len(aapl["checks"]["events"]["earnings"]["calendars"]) == 2
    # P2: the newest calendar has an INVALID row of AAPL; an older recent one lists AAPL out of the window — it cannot answer.
    # Without an estimate the unreadable row FAILS CLOSED; with one, the estimate answers and the row is a mark
    for estimate, codes, marks, status in ((False, [decisor.EARNINGS_CALENDAR_ROW_INVALID], [], "row_invalid"),
                                           (True, [decisor.EARNINGS_WITHIN_N], [decisor.EARNINGS_CALENDAR_ROW_INVALID, decisor.EARNINGS_DATE_ESTIMATED],
                                            "estimated")):
        aapl = _aapl_after(([_row("AAPL.US", "2026-10-29")], RUN - timedelta(hours=20)), ([INVALID_AAPL], RUN - timedelta(hours=1)), estimate=estimate)
        earnings = aapl["checks"]["events"]["earnings"]
        assert (aapl["verdict"], aapl["reason_codes"], aapl["checks"]["events"]["marks"], earnings["status"]) == (decisor.OBSERVAR, codes, marks, status)
        assert "an invalid row of the name" in earnings["detail"] and earnings["row_invalid"] is True, estimate
        assert [item["invalid_row_of_name"] for item in earnings["calendars"]] == [False, True]
        assert aapl["checks"]["counterfactual"]["verdict_without_events"] == decisor.COMPRA_PERMITIDA  # an event gate, off in the counterfactual
    # ...and when the estimate says "not within", no gate: the invalid row is recorded as a mark
    database = _database()
    _night(database)
    _calendar(database, [_row("AAPL.US", "2026-10-29")], received=RUN - timedelta(hours=20))
    _calendar(database, [INVALID_AAPL], received=RUN - timedelta(hours=1))
    _filing(database, "AAPL", "0000999201-26-000009", "10-Q", datetime(2026, 8, 20, 20, 30, tzinfo=UTC))  # + 91 d = 11-19: not within
    _run(database)
    aapl = _record(database, "NASDAQ", "AAPL")
    assert aapl["verdict"] == decisor.COMPRA_PERMITIDA and aapl["checks"]["events"]["earnings"]["status"] == "estimated"
    assert aapl["checks"]["events"]["marks"] == [decisor.EARNINGS_CALENDAR_ROW_INVALID, decisor.EARNINGS_DATE_ESTIMATED]
    # on B3 (informative) the fail-closed branch is a mark too
    database = _database()
    _night(database)
    _calendar(database, [{**_row("PETR4.SA", "2026-10-14", currency="BRL"), "report_date": "2026-10-14T00:00"}])
    _run(database)
    petr = _record(database, "B3", "PETR4")
    assert petr["verdict"] == decisor.COMPRA_PERMITIDA and petr["checks"]["events"]["marks"] == [decisor.EARNINGS_CALENDAR_ROW_INVALID]
    assert petr["checks"]["events"]["earnings"]["status"] == "row_invalid"
    # P10: the newest usable calendar has NO row of AAPL; an older one lists it out of the window — the estimate answers
    for estimate, verdict, status in ((True, decisor.OBSERVAR, "estimated"), (False, decisor.COMPRA_PERMITIDA, "unavailable")):
        aapl = _aapl_after(([_row("AAPL.US", "2026-10-29")], RUN - timedelta(hours=20)), ([_row("KO.US", "2026-10-28")], RUN - timedelta(hours=1)),
                           estimate=estimate)
        earnings = aapl["checks"]["events"]["earnings"]
        assert (aapl["verdict"], earnings["status"]) == (verdict, status) and "has no row of the name" in earnings["detail"], estimate
        assert earnings["answering"] is not None
    # an invalid row of the name in the calendar before the window still forbids "no event"
    aapl = _aapl_after(([INVALID_AAPL], RUN - timedelta(hours=40)), ([_row("AAPL.US", "2026-10-29")], RUN - timedelta(hours=1)), estimate=True)
    assert aapl["checks"]["events"]["earnings"]["status"] == "estimated" and aapl["reason_codes"] == [decisor.EARNINGS_WITHIN_N]
    aapl = _aapl_after(([INVALID_AAPL], RUN - timedelta(hours=40)), ([_row("AAPL.US", "2026-10-29")], RUN - timedelta(hours=1)))
    assert aapl["reason_codes"] == [decisor.EARNINGS_CALENDAR_ROW_INVALID]
    # the newest USABLE calendar answers, not the newest one: a later partial calendar says nothing
    aapl = _aapl_after(([_row("AAPL.US", "2026-10-29")], RUN - timedelta(hours=20)), estimate=True)
    assert aapl["checks"]["events"]["earnings"]["status"] == "calendar" and aapl["verdict"] == decisor.COMPRA_PERMITIDA
    database = _database()
    _night(database)
    _calendar(database, [_row("AAPL.US", "2026-10-29")], received=RUN - timedelta(hours=20))
    _calendar(database, [_row("KO.US", "2026-10-28")], received=RUN - timedelta(hours=1), filler=10)  # partial: 11 US events
    _filing(database, *JULY_RELEASE, items="2.02")
    _run(database)
    earnings = _record(database, "NASDAQ", "AAPL")["checks"]["events"]["earnings"]
    assert earnings["status"] == "calendar" and earnings["calendars"][1]["refused"].startswith("partial")
    # a share class's invalid row is found under the provider's spelling too
    blocked = decisor.name_earnings(_calendars({"BRK-B.US": [{"code": "BRK-B.US", "report_date": "2026-10-29", "timing": None}]},
                                               blocking={"BRK-B.US": ["DATE_INVALID"]}), None, "NYSE", "BRK.B", at=RUN, expected_session=SESSION)
    assert blocked["status"] == "row_invalid" and "an invalid row of the name" in blocked["detail"]


def test_a_usable_calendar_without_the_names_row_still_gates_on_the_estimate() -> None:
    database = _database()
    _night(database)
    _calendar(database, [_row("KO.US", "2026-10-28", "BeforeMarket")])  # usable, no AAPL row
    _filing(database, "AAPL", "0000999201-26-000001", "8-K", datetime(2026, 7, 15, 20, 30, tzinfo=UTC), items="2.02")  # + 91 d = 10-14
    _run(database)
    aapl, ko = _record(database, "NASDAQ", "AAPL"), _record(database, "NYSE", "KO")
    assert aapl["checks"]["events"]["earnings"]["status"] == "estimated" and aapl["reason_codes"] == [decisor.EARNINGS_WITHIN_N]
    assert aapl["checks"]["events"]["marks"] == [decisor.EARNINGS_DATE_ESTIMATED]
    assert ko["checks"]["events"]["earnings"]["status"] == "calendar" and ko["checks"]["events"]["marks"] == []  # listed: the calendar answers
    # the calendar listing the name out of the window wins over the estimate
    _calendar(database, [_row("AAPL.US", "2026-10-29", "BeforeMarket")], received=RUN - timedelta(minutes=5))
    assert decisor.run_shadow(database, now=RUN)["markets"]["NASDAQ"]["verdicts"]["COMPRA_PERMITIDA"] == 1


def test_a_calendar_inside_the_margin_or_after_the_clock_is_never_read() -> None:
    for received, read in ((RUN - EPSILON, True), (RUN - EPSILON + timedelta(seconds=1), False), (RUN + timedelta(seconds=1), False)):
        database = _database()
        _night(database)
        _calendar(database, [_row("AAPL.US", "2026-10-14", "BeforeMarket")], received=received)
        _run(database)
        aapl = _record(database, "NASDAQ", "AAPL")
        assert (aapl["reason_codes"] == [decisor.EARNINGS_WITHIN_N]) is read, received
        assert (aapl["checks"]["events"]["earnings"]["calendars"] != []) is read


def test_a_name_with_an_invalid_calendar_row_falls_back_to_its_estimate() -> None:
    database = _database()
    _night(database)
    _calendar(database, [{**_row("AAPL.US", "2026-10-30"), "report_date": "2026-10-30T00:00"}, _row("KO.US", "2026-10-28")])
    _filing(database, "AAPL", "0000999201-26-000001", "8-K", datetime(2026, 7, 16, 20, 30, tzinfo=UTC), items="2.02,9.01")  # + 91 d = 10-15
    _run(database)
    aapl = _record(database, "NASDAQ", "AAPL")
    earnings = aapl["checks"]["events"]["earnings"]
    assert earnings["status"] == "estimated" and "an invalid row of the name" in earnings["detail"] and earnings["estimate"]["estimated_date"] == "2026-10-15"
    assert aapl["reason_codes"] == [decisor.EARNINGS_WITHIN_N]
    assert aapl["checks"]["events"]["marks"] == [decisor.EARNINGS_CALENDAR_ROW_INVALID, decisor.EARNINGS_DATE_ESTIMATED]


# ------------------------------------------------------------------ A. the 051 estimate


def test_the_estimate_is_seasonal_first_from_the_same_quarter_a_year_earlier() -> None:
    filings = [_ref("8-K", "2025-10-23T20:05:00+00:00", items="2.02", doc="q3-25-release"), _ref("10-Q", "2025-11-05T21:00:00+00:00", period="2025-09-30"),
               _ref("8-K", "2026-07-23T20:05:00+00:00", items="2.02"), _ref("10-Q", "2026-08-05T21:00:00+00:00", period="2026-06-30")]
    estimate = decisor.cadence_estimate(filings)
    assert estimate is not None and estimate["rule"] == "seasonal" and estimate["basis"]["doc_id"] == "q3-25-release"
    assert (estimate["prior_period_end"], estimate["upcoming_period_end"], estimate["estimated_date"]) == ("2025-09-30", "2026-09-30", "2026-10-22")
    judged = decisor._estimate_within("NASDAQ", estimate, WINDOW, decisor.THRESHOLDS)
    assert judged["range"] == ["2026-10-07", "2026-10-22"] and judged["within"] is True  # the edge of the widened window
    assert decisor._estimate_within("NASDAQ", {**estimate, "estimated_date": "2026-10-23"}, WINDOW, decisor.THRESHOLDS)["within"] is False
    assert decisor._estimate_within("NASDAQ", {**estimate, "estimated_date": "2026-10-07"}, WINDOW, decisor.THRESHOLDS)["within"] is True
    assert decisor._estimate_within("NASDAQ", {**estimate, "estimated_date": "2026-10-06"}, WINDOW, decisor.THRESHOLDS)["within"] is True  # reacts 10-07
    assert decisor._estimate_within("NASDAQ", {**estimate, "estimated_date": "2026-10-05"}, WINDOW, decisor.THRESHOLDS)["within"] is False
    # without its release, the prior quarter's own 10-Q is the base
    assert decisor.cadence_estimate([item for item in filings if item["doc_id"] != "q3-25-release"])["estimated_date"] == "2026-11-04"  # type: ignore[index]


def test_the_seasonal_base_edges() -> None:
    latest = _ref("10-Q", "2026-08-05T21:00:00+00:00", period="2026-06-30")  # upcoming quarter 2026-09-30, a year before: 2025-10-01
    # a release accepted ON the prior period's last day (New York) is not that quarter's release: the 10-Q is the base
    on_the_day = [_ref("8-K", "2025-09-30T20:00:00+00:00", items="2.02", doc="same-day"), _ref("10-Q", "2025-11-05T21:00:00+00:00", period="2025-09-30",
                                                                                              doc="q3-25"), latest]
    estimate = decisor.cadence_estimate(on_the_day)
    assert estimate is not None and estimate["rule"] == "seasonal" and estimate["basis"]["doc_id"] == "q3-25"
    # ...and one accepted after the next quarter ended is not either; one the day after the period end is
    late = [_ref("8-K", "2026-01-02T20:00:00+00:00", items="2.02", doc="late"), *on_the_day[1:]]
    assert decisor.cadence_estimate(late)["basis"]["doc_id"] == "q3-25"  # type: ignore[index]
    next_day = [_ref("8-K", "2025-10-01T20:00:00+00:00", items="2.02", doc="next-day"), *on_the_day[1:]]
    assert decisor.cadence_estimate(next_day)["basis"]["doc_id"] == "next-day"  # type: ignore[index]
    # the prior quarter is found within 10 days of a year before (2025-10-01): 2025-09-21 is, 2025-09-20 is not
    for period, rule in (("2025-09-21", "seasonal"), ("2025-09-20", "recent"), ("2025-10-11", "seasonal"), ("2025-10-12", "recent")):
        prior = _ref("10-Q", "2025-11-05T21:00:00+00:00", period=period, doc="prior")
        assert decisor.cadence_estimate([prior, latest])["rule"] == rule, period  # type: ignore[index]


def test_without_a_seasonal_base_the_most_recent_original_filing_answers() -> None:
    old_release, newer_quarter = _ref("8-K", "2025-10-10T20:30:00+00:00", items="2.02"), _ref("10-Q", "2026-07-15T20:30:00+00:00", period="2026-06-30")
    estimate = decisor.cadence_estimate([old_release, newer_quarter])
    assert estimate is not None and (estimate["rule"], estimate["basis"]["form"], estimate["estimated_date"]) == ("recent", "10-Q", "2026-10-14")
    # a 10-K base: its period end + 91 days + the issuer's latest 10-Q filing lag (35 days here; 45 by default)
    quarter, annual = _ref("10-Q", "2025-11-04T21:00:00+00:00", period="2025-09-30", doc="q"), _ref("10-K", "2026-02-25T21:00:00+00:00", period="2025-12-31")
    estimate = decisor.cadence_estimate([quarter, annual])
    assert estimate is not None and (estimate["lag_days"], estimate["lag_basis"], estimate["estimated_date"]) == (35, "q", "2026-05-06")
    assert decisor.cadence_estimate([annual])["estimated_date"] == "2026-05-16"  # type: ignore[index]
    # amendments re-file a period, they announce nothing; an 8-K without item 2.02 is no release
    assert decisor.cadence_estimate([_ref("10-Q/A", "2026-08-01T20:00:00+00:00", period="2026-06-30"), _ref("8-K", "2026-08-02T20:00:00+00:00",
                                                                                                             items="5.02")]) is None
    recent = decisor.cadence_estimate([old_release, newer_quarter])
    assert decisor.cadence_estimate([old_release, newer_quarter, _ref("10-Q/A", "2026-09-30T20:00:00+00:00", period="2026-06-30")]) == recent


def test_the_estimate_counts_new_york_days_and_acceptances_never_registrations() -> None:
    late_evening = [_ref("8-K", "2026-07-17T00:30:00+00:00", items="2.02")]  # 20:30 New York on 07-16
    estimate = decisor.cadence_estimate(late_evening)
    assert estimate is not None and estimate["estimated_date"] == "2026-10-15"  # the UTC day would give 10-16 (T+3)
    tight = replace(decisor.THRESHOLDS, earnings_estimate_tolerance_days=0)
    assert decisor._estimate_within("NASDAQ", estimate, WINDOW, tight)["within"] is True
    assert decisor._estimate_within("NASDAQ", {**estimate, "estimated_date": "2026-10-16"}, WINDOW, tight)["within"] is False
    # a filing backfilled long after its acceptance (but before the night) estimates from its acceptance
    database = _database()
    _night(database)
    _filing(database, "AAPL", "0000999201-26-000003", "10-Q", datetime(2026, 7, 15, 20, 30, tzinfo=UTC), seen=datetime(2026, 10, 1, tzinfo=UTC))
    _filing(database, "KO", "0000999202-26-000003", "10-Q", datetime(2026, 7, 15, 20, 30, tzinfo=UTC), seen=RUN - EPSILON + timedelta(seconds=1))
    _run(database, thresholds=tight)
    aapl, ko = _record(database, "NASDAQ", "AAPL"), _record(database, "NYSE", "KO")
    assert aapl["checks"]["events"]["earnings"]["estimate"]["estimated_date"] == "2026-10-14" and aapl["reason_codes"] == [decisor.EARNINGS_WITHIN_N]
    assert ko["checks"]["events"]["earnings"]["status"] == "unavailable"  # registered inside the margin: not known by the night


def test_the_filings_reader_keeps_originals_known_at_the_clock() -> None:
    database = _database()
    _filing(database, "AAPL", "a-1", "8-K", datetime(2026, 7, 15, 20, 30, tzinfo=UTC), items="2.02")
    _filing(database, "AAPL", "a-2", "8-K/A", datetime(2026, 7, 16, 20, 30, tzinfo=UTC), items="2.02")
    _filing(database, "AAPL", "a-3", "10-Q/A", datetime(2026, 7, 17, 20, 30, tzinfo=UTC))
    _filing(database, "AAPL", "a-4", "8-K", datetime(2026, 7, 18, 20, 30, tzinfo=UTC), items="5.02")
    _filing(database, "AAPL", "a-5", "10-Q", datetime(2025, 8, 1, 20, 30, tzinfo=UTC))  # 439 days before RUN: outside the 400-day lookback
    _filing(database, "AAPL", "a-6", "10-K", RUN + timedelta(hours=1))  # accepted after the clock
    known = calendar_module.filings_known_at(database, RUN, lookback_days=400, margin_seconds=60)
    assert [item["doc_id"] for item in known["by_symbol"]["AAPL"]] == ["a-1"]
    assert [item["doc_id"] for item in calendar_module.filings_known_at(database, RUN, lookback_days=500, margin_seconds=60)["by_symbol"]["AAPL"]] == \
        ["a-5", "a-1"]
    assert calendar_module.filings_known_at(_database(), RUN, lookback_days=400, margin_seconds=60) == {"status": "absent"}


# ------------------------------------------------------------------ D. marks: the 30-day consensus revision and the sentiment


def test_a_consensus_cut_over_thirty_days_is_a_mark_read_point_in_time() -> None:
    database = _database()
    _night(database)
    _consensus(database, "NASDAQ", RUN - timedelta(days=31), {"AAPL": _fy1(6.0)})  # the latest by D − 30 d − ε
    _consensus(database, "NASDAQ", RUN - timedelta(days=29), {"AAPL": _fy1(9.0)})  # inside the 30 days: not "then"
    _consensus(database, "NASDAQ", RUN - timedelta(hours=1), {"AAPL": _fy1(5.5)})  # "now": ln(5.5/6) = −0.087
    _consensus(database, "NASDAQ", RUN - timedelta(seconds=30), {"AAPL": _fy1(1.0)})  # inside the margin: never read
    _consensus(database, "NASDAQ", RUN + timedelta(minutes=1), {"AAPL": _fy1(1.0)})  # after the clock: never read
    _run(database)
    aapl = _record(database, "NASDAQ", "AAPL")
    consensus = aapl["checks"]["events"]["consensus"]
    assert consensus["status"] == "ok" and (consensus["past_eps"], consensus["current_eps"], consensus["cut"]) == (6.0, 5.5, True)
    assert consensus["log_change"] == pytest.approx(-0.0870, abs=1e-4) and consensus["lookback_days"] == 30
    assert aapl["verdict"] == decisor.COMPRA_PERMITIDA and decisor.CONSENSUS_EPS_CUT_30D in aapl["checks"]["events"]["marks"]
    # the edges of the limit (strict), the fiscal year compared, a FY1 that turned non-positive
    for change, cut in ((-0.05, False), (-0.0500001, True), (-0.049, False)):
        assert (decisor.CONSENSUS_EPS_CUT_30D in decisor._event_codes({"consensus": {**consensus, "log_change": change}}, decisor.THRESHOLDS)[0]) is cut
    rolled = decisor.name_consensus({"packets": {"AAPL": _fy1(7.0, fiscal="2028-09-30")}}, {"packets": {"AAPL": _fy1(6.0)}}, "AAPL")
    assert rolled["status"] == "not_comparable"
    turned = decisor.name_consensus({"packets": {"AAPL": _fy1(-0.5)}}, {"packets": {"AAPL": _fy1(6.0)}}, "AAPL")
    assert turned["turned_non_positive"] is True and decisor.CONSENSUS_EPS_CUT_30D in decisor._event_codes({"consensus": turned}, decisor.THRESHOLDS)[0]
    assert decisor.name_consensus(None, {"packets": {}}, "AAPL")["status"] == "unavailable"


def test_a_negative_weekly_sentiment_read_at_the_clock_is_a_mark_with_its_value_recorded() -> None:
    database = _database()
    _night(database)
    _sentiment(database, "AAPL", RUN - timedelta(days=2), bearish=70.0, articles=12)
    _sentiment(database, "KO", RUN - timedelta(seconds=30), bearish=90.0, articles=40)  # inside the margin: never read
    _run(database)
    aapl, ko = _record(database, "NASDAQ", "AAPL"), _record(database, "NYSE", "KO")
    sentiment = aapl["checks"]["events"]["sentiment"]
    assert sentiment["status"] == "ok" and sentiment["bearish_percent"] == 70.0 and sentiment["articles_last_week"] == 12 and sentiment["negative"] is True
    assert aapl["verdict"] == decisor.COMPRA_PERMITIDA and decisor.NEWS_SENTIMENT_NEGATIVE in aapl["checks"]["events"]["marks"]
    assert aapl["inputs"]["events"]["sentiment"]["bearish_percent"] == 70.0  # the only copy of the week's value as read
    assert ko["checks"]["events"]["sentiment"]["status"] == "unavailable"
    assert _record(database, "B3", "PETR4")["checks"]["events"]["sentiment"]["status"] == "not_applicable"
    for change, negative in (({"bearish_percent": 60.0}, True), ({"bearish_percent": 59.99}, False), ({"articles_last_week": 5}, True),
                             ({"articles_last_week": 4}, False), ({"age_days": 8.0}, True), ({"age_days": 8.0001}, False)):
        raised = decisor._event_codes({"sentiment": {**sentiment, **change}}, decisor.THRESHOLDS)[0]
        assert (decisor.NEWS_SENTIMENT_NEGATIVE in raised) is negative, change


def test_the_sentiment_is_never_a_gate_and_never_enters_the_replay_hash() -> None:
    database = _database()
    _night(database)
    _sentiment(database, "AAPL", RUN - timedelta(days=2), bearish=70.0, articles=12)
    _run(database)
    _sentiment(database, "AAPL", RUN + timedelta(days=1), bearish=10.0, articles=30)  # the same ISO week, polled after the clock: overwritten
    _run(database)
    rerun, original = database.list_valuation_decisions("NASDAQ", "AAPL")
    values = {rerun["checks"]["events"]["sentiment"]["bearish_percent"], original["checks"]["events"]["sentiment"]["bearish_percent"]}
    assert values == {70.0, 10.0} and rerun["verdict"] == original["verdict"] == decisor.COMPRA_PERMITIDA
    assert decisor.replay_sha256(rerun) == decisor.replay_sha256(original)  # the declared exception: the source cannot be replayed
    # listed as a gate by mistake, it stays a mark
    gated = replace(decisor.THRESHOLDS, event_gates=(decisor.EARNINGS_WITHIN_N, decisor.NEWS_SENTIMENT_NEGATIVE))
    outcome = decisor.decide(_us_row(official_market="NASDAQ"), expected_session=SESSION, tp_sessions_behind=0,
                             price={"price": 100.0, "source": "official_cut", "session": SESSION}, error={"status": "ok", "value": 0.10},
                             rate={"status": "ok", "h_market": 0.04}, staleness={"status": "clear", "source_status": "ok"},
                             events={"earnings": {"status": "calendar"}, "sentiment": original["checks"]["events"]["sentiment"] | {"bearish_percent": 70.0}},
                             thresholds=gated)
    assert outcome["verdict"] == decisor.COMPRA_PERMITIDA and outcome["marks"] == [decisor.NEWS_SENTIMENT_NEGATIVE]


# ------------------------------------------------------------------ C. replay determinism, served records


def test_a_rerun_of_a_night_reproduces_its_decisions_whatever_arrived_after_it() -> None:
    database = _database()
    _night(database)
    _calendar(database, [_row("AAPL.US", "2026-10-15")])
    _consensus(database, "NASDAQ", RUN - timedelta(days=31), {"AAPL": _fy1(6.0)})
    _consensus(database, "NASDAQ", RUN - timedelta(hours=1), {"AAPL": _fy1(5.5)})
    _filing(database, "KO", "0000999202-26-000001", "10-Q", datetime(2026, 7, 15, 20, 30, tzinfo=UTC))
    first = _run(database)
    # after the clock: a calendar moving the date, a consensus restoring it, a new poll, a filing, a sentiment row
    _calendar(database, [_row("AAPL.US", "2026-11-05")], received=RUN + timedelta(minutes=30))
    _consensus(database, "NASDAQ", RUN + timedelta(minutes=40), {"AAPL": _fy1(6.5)})
    _poll_run(database, started=RUN + timedelta(minutes=45), completed=RUN + timedelta(minutes=50))
    _filing(database, "KO", "0000999202-26-000002", "8-K", datetime(2026, 7, 20, 20, 30, tzinfo=UTC), items="2.02", seen=RUN + timedelta(hours=2))
    _sentiment(database, "AAPL", RUN + timedelta(days=7), bearish=95.0, articles=30)
    again = _run(database)
    assert again["run_id"] != first["run_id"]
    for market, symbol in (("NASDAQ", "AAPL"), ("NYSE", "KO"), ("B3", "PETR4")):
        rerun, original = database.list_valuation_decisions(market, symbol)
        assert decisor.replay_sha256(rerun) == decisor.replay_sha256(original) and rerun["inputs_sha256"] == original["inputs_sha256"]
    aapl = _record(database, "NASDAQ", "AAPL")
    assert aapl["reason_codes"] == [decisor.EARNINGS_WITHIN_N] and aapl["checks"]["events"]["marks"] == [decisor.CONSENSUS_EPS_CUT_30D]


def test_a_served_record_published_after_the_clock_is_not_decided(monkeypatch: pytest.MonkeyPatch) -> None:
    database = _database()
    _night(database)
    served_rows = decisor._served_rows

    def republished(db: Any, market: str, generation: Any) -> dict[str, dict[str, Any]]:
        rows = served_rows(db, market, generation)
        if "AAPL" in rows:
            rows["AAPL"]["official_published_at"] = (RUN - EPSILON + timedelta(seconds=1)).isoformat()  # inside the margin
        return rows

    monkeypatch.setattr(decisor, "_served_rows", republished)
    receipt = _run(database)
    assert receipt["markets"]["NASDAQ"]["tp_published_after_run_instant"] == 1 and receipt["markets"]["NASDAQ"]["decided"] == 0
    assert database.list_valuation_decisions("NASDAQ", "AAPL") == [] and len(database.list_valuation_decisions("NYSE", "KO")) == 1

    def at_the_edge(db: Any, market: str, generation: Any) -> dict[str, dict[str, Any]]:
        rows = served_rows(db, market, generation)
        if "AAPL" in rows:
            rows["AAPL"]["official_published_at"] = (RUN - EPSILON).isoformat()  # exactly D − ε: known
        return rows

    monkeypatch.setattr(decisor, "_served_rows", at_the_edge)
    receipt = _run(database)
    assert receipt["markets"]["NASDAQ"]["tp_published_after_run_instant"] == 0 and receipt["markets"]["NASDAQ"]["decided"] == 1


def test_the_counterfactual_keeps_every_code_but_the_event_gates() -> None:
    stale = {"status": "stale", "source_status": "ok", "filings": [{"mark_id": "m", "doc_id": "d"}]}
    outcome = _decide(_us_row(official_market="NASDAQ"), staleness=stale, events={**CALM, "market": "NASDAQ", "earnings": {"status": "calendar", "within": True}})
    assert outcome["reason_codes"] == [decisor.TP_STALE_AFTER_FILING, decisor.EARNINGS_WITHIN_N]
    assert outcome["checks"]["counterfactual"] == {"verdict_without_events": decisor.OBSERVAR, "reason_codes_without_events": [decisor.TP_STALE_AFTER_FILING]}
    vetoed = _decide(_us_row(valuation_confidence=50.0), events={**CALM, "market": "NASDAQ", "earnings": {"status": "calendar", "within": True}})
    assert vetoed["verdict"] == vetoed["verdict_without_events"] == decisor.VETO and vetoed["reason_codes"][-1] == decisor.EARNINGS_WITHIN_N


# ------------------------------------------------------------------ the block


THRESHOLDS_SHA256 = "98ee0a62c9951202e7e5d039dc1c15fc4a93e543a2aa97bbbcb94c2f46c822ed"  # the block until the PREREG freeze (VALUATION_DECISOR_V1.md)


def test_the_block_is_pinned_until_the_freeze_and_every_rule_is_in_it() -> None:
    assert decisor.thresholds_sha256() == THRESHOLDS_SHA256, "the decisor block changed: update the literal AND VALUATION_DECISOR_V1.md"
    assert decisor.PREREG_THRESHOLDS_SHA256 is None  # not frozen yet: the freeze commit pins it
    block = asdict(decisor.THRESHOLDS)
    changed = {"insert_margin_seconds": 30, "staleness_poll_source": "other", "staleness_poll_max_age_hours": 5, "earnings_window_sessions": 3,
               "earnings_gate_markets": ("NASDAQ",), "earnings_calendar_max_age_hours": 24, "earnings_calendar_min_us_events": 50,
               "earnings_calendar_max_invalid_share": 0.1, "earnings_filings_lookback_days": 500, "earnings_estimate_seasonal_days": 365,
               "earnings_estimate_period_match_days": 5, "earnings_estimate_offset_days": 90, "earnings_estimate_default_10q_lag_days": 40,
               "earnings_estimate_tolerance_days": 0, "consensus_eps_cut_log": 0.1, "consensus_lookback_days": 60,
               "news_sentiment_bearish_min_percent": 70.0, "news_sentiment_min_articles": 3, "news_sentiment_max_age_days": 7, "event_gates": ()}
    assert set(changed) <= set(block)
    for field, value in changed.items():
        assert decisor.thresholds_sha256(replace(decisor.THRESHOLDS, **{field: value})) != decisor.thresholds_sha256(), field
    assert set(decisor.EVENT_CODES) == {*decisor.MARK_CODES, decisor.EARNINGS_WITHIN_N, decisor.EARNINGS_CALENDAR_ROW_INVALID}
    codes = (set(decisor.VETO_CODES), set(decisor.OBSERVAR_CODES), set(decisor.MARK_CODES))
    assert not (codes[0] & codes[1] or codes[0] & codes[2] or codes[1] & codes[2])
    no_gates = _decide(_us_row(official_market="NASDAQ"), staleness=US_CLEAR,
                       events={**CALM, "market": "NASDAQ", "earnings": {"status": "calendar", "within": True}})
    assert no_gates["verdict"] == decisor.OBSERVAR
    off = decisor.decide(_us_row(official_market="NASDAQ"), expected_session=SESSION, tp_sessions_behind=0,
                         price={"price": 100.0, "source": "official_cut", "session": SESSION}, error={"status": "ok", "value": 0.10},
                         rate={"status": "ok", "h_market": 0.04}, staleness={"status": "clear", "source_status": "ok"},
                         events={"market": "NASDAQ", "earnings": {"status": "calendar", "within": True}}, thresholds=replace(decisor.THRESHOLDS, event_gates=()))
    assert off["verdict"] == decisor.COMPRA_PERMITIDA and off["marks"] == [decisor.EARNINGS_WITHIN_N]


# ------------------------------------------------------------------ E. the calendar phase


def _settings(**extra: Any) -> Settings:
    return Settings(**{"brapi_token": "brapi-test", "eodhd_api_token": "eodhd-test", "auth_cookie_secure": False, **extra})


def test_the_calendar_phase_makes_one_streamed_whole_market_call_and_stores_an_append_only_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    database = _database()
    seen: list[httpx.Request] = []
    rows = [_row("AAPL.US", "2026-10-15"), _row("PETR4.SA", "2026-10-20", None, currency="BRL"), _row("BAD", "2026-10-15")]
    body = _body(rows, date(2026, 10, 7), date(2026, 11, 13))

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=body, headers={"content-type": "application/json; charset=utf-8"})

    service = calendar_module.EarningsCalendarService(_settings(), database, transport=httpx.MockTransport(handler), clock=lambda: RECEIVED)
    assert service.last_run_at() is None
    result = service.run()
    assert len(seen) == 1 and seen[0].url.path == calendar_module.ENDPOINT and "symbols" not in seen[0].url.params
    assert (seen[0].url.params["from"], seen[0].url.params["to"], seen[0].url.params["fmt"]) == ("2026-10-07", "2026-11-13", "json")
    assert result["events"] == 2 and result["by_exchange"] == {"SA": 1, "US": 1}
    stored = database.analysis_snapshot_at_or_before(calendar_module.ANALYSIS_TYPE, calendar_module.ENTITY_KEY, RECEIVED)
    assert stored is not None and stored["outputs"]["payload_sha256"] == hashlib.sha256(body).hexdigest()
    assert (stored["outputs"]["rows"], stored["outputs"]["invalid_rows"], stored["outputs"]["unattributed_invalid_rows"]) == (3, 1, 1)
    # last_run_at reads the clock only, never a whole snapshot
    monkeypatch.setattr(database, "latest_analysis_snapshot", lambda *args, **kwargs: pytest.fail("a full snapshot load"))
    assert service.last_run_at() == RECEIVED
    monkeypatch.undo()
    dumped = json.dumps(result)
    assert "eodhd-test" not in dumped and "AAPL" not in dumped
    # an unusable answer stores nothing and fails the attempt, naming no URL
    for status, payload, kind in ((500, b"{}", "application/json"), (200, b"<html>", "text/html"), (200, b'{"type": "Earnings"}', "application/json")):
        failing = calendar_module.EarningsCalendarService(
            _settings(), database, transport=httpx.MockTransport(lambda request, s=status, b=payload, k=kind: httpx.Response(s, content=b, headers={"content-type": k})),
            clock=lambda: RECEIVED + timedelta(hours=1))
        with pytest.raises(calendar_module.EarningsCalendarError) as caught:
            failing.run()
        assert "eodhd-test" not in str(caught.value) and "api_token" not in str(caught.value)
    assert service.last_run_at() == RECEIVED  # nothing new stored
    with pytest.raises(calendar_module.EarningsCalendarError, match="token missing"):
        calendar_module.EarningsCalendarService(_settings(eodhd_api_token=""), database).run()


def test_the_download_has_a_byte_cap_a_deadline_and_never_leaks_the_url() -> None:
    def ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 2048, headers={"content-type": "application/json"})

    with pytest.raises(calendar_module.EarningsCalendarError, match="exceeds 1024 bytes"):
        calendar_module.fetch_calendar("https://provider.invalid", "secret-token", start=date(2026, 10, 7), end=date(2026, 11, 13), timeout=5,
                                       transport=httpx.MockTransport(ok), max_bytes=1024)
    served: list[int] = []

    def slow_stream(request: httpx.Request) -> httpx.Response:
        def chunks() -> Any:
            for index in range(10):
                served.append(index)
                yield b"x" * 10
        return httpx.Response(200, content=chunks(), headers={"content-type": "application/json"})

    clock = iter([0.0, *[100.0 * step for step in range(1, 20)]])  # 100 s per chunk: the deadline (180 s) falls during the second
    with pytest.raises(calendar_module.EarningsCalendarError, match="exceeded 180 s"):
        calendar_module.fetch_calendar("https://provider.invalid", "secret-token", start=date(2026, 10, 7), end=date(2026, 11, 13), timeout=5,
                                       transport=httpx.MockTransport(slow_stream), monotonic=lambda: next(clock))
    assert len(served) < 10  # the download stopped at the deadline, never read to the end
    late = iter([0.0, 100.0, 500.0])  # the only chunk arrives in time; the call as a whole ends past the deadline
    with pytest.raises(calendar_module.EarningsCalendarError, match="exceeded 180 s"):
        calendar_module.fetch_calendar("https://provider.invalid", "secret-token", start=date(2026, 10, 7), end=date(2026, 11, 13), timeout=5,
                                       transport=httpx.MockTransport(ok), monotonic=lambda: next(late))
    for broken in (lambda request: (_ for _ in ()).throw(httpx.ConnectError("down", request=request)),
                   lambda request: (_ for _ in ()).throw(httpx.ReadError("cut", request=request))):
        with pytest.raises(calendar_module.EarningsCalendarError) as caught:
            calendar_module.fetch_calendar("https://provider.invalid", "secret-token", start=date(2026, 10, 7), end=date(2026, 11, 13), timeout=5,
                                           transport=httpx.MockTransport(broken))
        assert "secret-token" not in str(caught.value) and "provider.invalid" not in str(caught.value)
    for base in ("https://pro\x00vider.invalid", "ht!tp://provider.invalid"):  # an invalid URL is a refusal too, without the URL
        with pytest.raises(calendar_module.EarningsCalendarError) as caught:
            calendar_module.fetch_calendar(base, "secret-token", start=date(2026, 10, 7), end=date(2026, 11, 13), timeout=5,
                                           transport=httpx.MockTransport(ok))
        assert "secret-token" not in str(caught.value) and "provider" not in str(caught.value)


class _Ping:
    def __init__(self) -> None:
        self.pings: list[str] = []

    def ping(self, kind: str) -> None:
        self.pings.append(kind)


class _Push:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def notify(self, **kwargs: Any) -> None:
        self.sent.append(kwargs)


def test_the_calendar_phase_never_pages_and_stops_after_three_failed_attempts_a_night() -> None:
    assert VALUATION_WORKER_ADVISORY_PHASES == ("earnings_calendar",)
    database = _database()
    attempts: list[int] = []

    def failing() -> None:
        attempts.append(1)
        raise RuntimeError("provider unavailable")

    phase = OffhoursPhase("earnings_calendar", lambda: None, failing, max_failures=3)
    ping, push = _Ping(), _Push()
    local = RUN.astimezone(SAO_PAULO)  # 01:30 BRT, inside the off-hours window
    statuses = []
    for minutes in (0, 30, 60, 90, 120):
        result = run_worker_iteration(database, now=local + timedelta(minutes=minutes), canonical_due=False, canonical_operation=lambda: None,
                                      offhours_phases=(phase,), healthchecks={"valuation": ping}, push_notifications=push)  # type: ignore[dict-item,arg-type]
        statuses.append(result.phase_statuses["earnings_calendar"])
    assert statuses == ["failed", "failed", "failed", "retry_cap", "retry_cap"] and len(attempts) == 3
    assert ping.pings == [] and push.sent == []  # never paged, never failing the worker's check
    # a failed advisory attempt still wakes the worker to retry inside the window (up to the cap)
    retry = run_worker_iteration(_database(), now=local, canonical_due=False, canonical_operation=lambda: None, offhours_phases=(phase,))
    assert retry.phase_statuses == {"earnings_calendar": "failed"} and retry.next_wake_at == local + timedelta(minutes=30)
    # the next night starts a new count
    next_night = run_worker_iteration(database, now=local + timedelta(days=1), canonical_due=False, canonical_operation=lambda: None,
                                      offhours_phases=(phase,))
    assert next_night.phase_statuses == {"earnings_calendar": "failed"} and len(attempts) == 5
    # the decisor's phase keeps its behaviour: a failure fails the worker's check at once and pages under main's
    # one-incident-per-episode policy (bad97b8): attention on the first failing night, a push from the second
    decisor_phase = OffhoursPhase("decisor_shadow", lambda: None, failing)
    run_worker_iteration(database, now=local, canonical_due=False, canonical_operation=lambda: None, offhours_phases=(decisor_phase,),
                         healthchecks={"valuation": ping}, push_notifications=push)  # type: ignore[dict-item,arg-type]
    assert ping.pings == ["start", "fail"] and push.sent == []
    run_worker_iteration(database, now=local + timedelta(days=1), canonical_due=False, canonical_operation=lambda: None,
                         offhours_phases=(decisor_phase,), healthchecks={"valuation": ping}, push_notifications=push)  # type: ignore[dict-item,arg-type]
    assert len(push.sent) == 1


def test_the_calendar_phase_is_flagged_off_runs_before_the_decisor_and_is_expected_only_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(valuation_env.EARNINGS_CALENDAR_ENV, raising=False)
    assert valuation_env.earnings_calendar_enabled() is False and "valuation_earnings_calendar_enabled" not in Settings.model_fields
    monkeypatch.setenv(valuation_env.EARNINGS_CALENDAR_ENV, "true")
    assert valuation_env.earnings_calendar_enabled() is True
    assert VALUATION_WORKER_PHASES["earnings_calendar"]["code"] == "valuation-worker-earnings-calendar"
    assert "earnings_calendar" not in VALUATION_WORKER_OFFHOURS_PHASES  # flag-gated, like the decisor
    source = (ROOT / "backend" / "app" / "valuation_worker.py").read_text(encoding="utf-8")
    phases = source[source.index("offhours_phases = ("):source.index("while True:")]
    assert phases.index('OffhoursPhase("earnings_calendar"') < phases.index('OffhoursPhase("decisor_shadow"')
    assert "max_failures=EARNINGS_CALENDAR_MAX_FAILURES" in phases and "if valuation_env.earnings_calendar_enabled() else ()" in phases


def test_the_aggregate_us_market_reads_the_xnys_calendar_like_its_exchanges() -> None:
    # name_earnings is called with NASDAQ/NYSE by run_shadow; "US" (the decide() aggregate) must not lose its sessions
    # and silently read every name as "no calendar answer" (verifier, 18/10).
    in_window = _calendars({"AAPL.US": [{"code": "AAPL.US", "report_date": "2026-10-14", "timing": "BeforeMarket"}]})
    for calendars in (in_window, _calendars(OUT_OF_WINDOW)):
        us = decisor.name_earnings(calendars, None, "US", "AAPL", at=RUN, expected_session=SESSION)
        nasdaq = decisor.name_earnings(calendars, None, "NASDAQ", "AAPL", at=RUN, expected_session=SESSION)
        assert us == nasdaq and us["window"]
    assert decisor.name_earnings(in_window, None, "US", "AAPL", at=RUN, expected_session=SESSION)["within"] is True
