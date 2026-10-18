"""Decisor V1 — the liveness of the US filings source and the event rules (owner's direction of 2026-10-17, before the
decisor freeze): 053 marks count only while the as-filed poll is alive at D (``STALENESS_SOURCE_STALE``);
``EARNINGS_WITHIN_N`` withholds a US permission when an announcement known at D falls on sessions [T+1, T+N] (the
EODHD calendar snapshot, else the 051 cadence estimate; B3 informative); ``CONSENSUS_EPS_CUT_SINCE_TP`` and
``NEWS_SENTIMENT_NEGATIVE`` are marks only; every row records ``verdict_without_events``. Point in time throughout: a
snapshot, a run, a filing or a sentiment row from after D never reaches D. No network."""
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

from app import valuation_decision as decisor
from app import valuation_earnings_calendar as calendar_module
from app import valuation_env
from app.config import Settings
from app.database import Database
from app.r2d2_v2_earnings_source import EarningsReceipt
from app.statement_vintages import StatementVintageStore
from app.valuation_worker_contract import VALUATION_WORKER_OFFHOURS_PHASES, VALUATION_WORKER_PHASES
from tests.test_valuation_decision import CALM, CUT, ROOT, RUN, SESSION, _database, _decide, _night, _poll, _run

UTC = timezone.utc
RECEIVED = RUN - timedelta(minutes=20)  # the calendar phase, just before the decisor's
WINDOW = ("2026-10-14", "2026-10-15")  # T = 2026-10-13 (Tue): T+1 Wed, T+2 Thu


# ------------------------------------------------------------------ fixtures of the test world


def _row(code: str, report_date: str, timing: str | None = "AfterMarket", *, period: str = "2026-09-30", currency: str = "USD") -> dict[str, Any]:
    return {"code": code, "report_date": report_date, "date": period, "before_after_market": timing, "currency": currency, "actual": None,
            "estimate": 1.0, "difference": None, "percent": None}


def _receipt(raw: bytes, received: datetime, start: date, end: date, *, status: int = 200, content_type: str = "application/json") -> EarningsReceipt:
    return EarningsReceipt(request_symbols=(), request_from=start, request_to=end, request_started_at=received - timedelta(seconds=2),
                           response_received_at=received, available_at=received, http_status=status, body_sha256=hashlib.sha256(raw).hexdigest(),
                           transport_complete=True, content_type=content_type)


def _body(rows: list[Any], start: date, end: date) -> bytes:
    return json.dumps({"type": "Earnings", "description": "Historical and upcoming Earnings", "from": start.isoformat(), "to": end.isoformat(),
                       "earnings": rows}).encode()


def _calendar(database: Database, rows: list[Any], *, received: datetime = RECEIVED, start: date = date(2026, 10, 7), end: date = date(2026, 11, 13)) -> str:
    raw = _body(rows, start, end)
    return calendar_module.record_calendar(database, raw, _receipt(raw, received, start, end))


def _filing(database: Database, symbol: str, doc_id: str, form: str, accepted: datetime, *, items: str = "", seen: datetime | None = None) -> None:
    StatementVintageStore(database).register_filings([{"market": "US", "issuer_key": "0000999201", "source": "sec_edgar", "doc_id": doc_id, "form": form,
                                                       "items": items, "symbols": [symbol], "period_of_report": "2026-06-30",
                                                       "filed_date": accepted.date(), "accepted_at": accepted, "accepted_source": "sec_header"}])
    for row in database._statement_filings:  # type: ignore[attr-defined]
        if row["doc_id"] == doc_id:
            row["first_seen_at"] = seen or accepted + timedelta(minutes=10)  # registered by the poll, in the test world


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


def _record(database: Database, market: str, symbol: str) -> dict[str, Any]:
    return database.list_valuation_decisions(market, symbol)[0]


# ------------------------------------------------------------------ the 053 source must be alive at D


@pytest.mark.parametrize(("poll_at", "status", "fresh"), [
    (None, "succeeded", False),  # no poll at all
    (RUN - timedelta(hours=6, seconds=1), "succeeded", False),  # older than 6 h
    (RUN - timedelta(hours=6), "succeeded", True),  # exactly 6 h: still evidence
    (RUN - timedelta(minutes=30), "succeeded", True),
    (RUN + timedelta(seconds=1), "succeeded", False),  # finished after D: never read by D
    (RUN - timedelta(minutes=30), "failed", False),  # a failed poll is no evidence
])
def test_the_053_marks_count_only_while_the_as_filed_poll_is_alive_at_the_runs_clock(poll_at: datetime | None, status: str, fresh: bool) -> None:
    database = _database()
    _night(database, poll=False)
    if poll_at is not None:
        _poll(database, poll_at, status=status)
    receipt = _run(database)
    for market in ("NASDAQ", "NYSE"):
        reasons = receipt["markets"][market]["reasons"]
        assert (decisor.STALENESS_SOURCE_STALE in reasons) is (not fresh), (market, reasons)
    assert receipt["markets"]["B3"]["verdicts"] == {"COMPRA_PERMITIDA": 1, "OBSERVAR": 1, "VETO": 0}  # B3: not applicable
    aapl = _record(database, "NASDAQ", "AAPL")
    gate = aapl["checks"]["tp_staleness"]
    if fresh:
        assert aapl["verdict"] == decisor.COMPRA_PERMITIDA and gate["source_status"] == "ok"
    else:
        assert aapl["verdict"] == decisor.OBSERVAR and aapl["reason_codes"] == [decisor.STALENESS_SOURCE_STALE] and gate["source_status"] == "stale"
    if poll_at is not None and status == "succeeded" and poll_at <= RUN:  # the poll the record relied on, named
        assert gate["trigger_poll"]["completed_at"] == poll_at.isoformat() and gate["trigger_poll"]["source_code"] == "sec_asfiled"
    else:  # a poll finished after the clock, or a failed one, is not read at all
        assert gate["trigger_poll"] is None


def test_a_stale_poll_keeps_the_marks_known_and_adds_its_own_code() -> None:
    database = _database()
    _night(database, poll=False)
    _poll(database, RUN - timedelta(hours=8))
    from app import valuation_asfiled as asfiled
    asfiled.TpStalenessStore(database).append([{"market": "NASDAQ", "symbol": "AAPL", "issuer_key": "0000999101", "doc_id": "0000999101-26-000007",
                                                "form": "8-K", "items": "2.02", "accepted_at": CUT - timedelta(hours=7), "period_of_report": None,
                                                "state": "stale", "reason": "tp_predates_acceptance", "official_cycle_id": None, "prediction_instant": None,
                                                "fundamentals_as_of": None, "expected_period_end": None, "covers_period": False, "queued_for_cut_at": None,
                                                "recorded_at": CUT - timedelta(hours=6)}])
    _run(database)
    assert _record(database, "NASDAQ", "AAPL")["reason_codes"] == [decisor.TP_STALE_AFTER_FILING, decisor.STALENESS_SOURCE_STALE]


def test_the_postgresql_poll_reader_is_causal_by_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    pg = Database(Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False, database_url="postgresql://configured"))
    statements: list[tuple[str, Any]] = []

    class Recording:
        def execute(self, query: str, params: Any = None) -> "Recording":
            statements.append((" ".join(query.split()), params))
            return self

        def fetchone(self) -> Any:
            return None

        def fetchall(self) -> list[Any]:
            return []

    @contextmanager
    def fake_connection() -> Any:
        yield Recording()

    monkeypatch.setattr(pg, "connection", fake_connection)
    assert pg.ingestion_run_completed_at_or_before("sec_asfiled", RUN) is None
    query, params = statements[-1]
    assert "source.code = %s AND run.status = %s AND run.completed_at IS NOT NULL AND run.completed_at <= %s" in query
    assert "ORDER BY run.completed_at DESC LIMIT 1" in query and params == ("sec_asfiled", "succeeded", RUN)
    assert pg.news_sentiment_at(["aapl"], RUN) == {}
    query, params = statements[-1]
    assert "symbol = ANY(%s) AND published_at <= %s" in query and params == ("US", ["AAPL"], RUN)
    assert pg.v2_forward_eps_at_or_before("NASDAQ", ["AAPL"], RUN) is None
    query, params = statements[-1]
    assert "snapshot.published_at <= %s" in query and "'fy1_estimate', packet.value->'fy1_estimate'" in query and params == (["AAPL"], "NASDAQ_V2_DATA", RUN)


# ------------------------------------------------------------------ EARNINGS_WITHIN_N


@pytest.mark.parametrize(("report_date", "timing", "within"), [
    ("2026-10-14", "BeforeMarket", True),  # T+1
    ("2026-10-14", "AfterMarket", True),  # an AMC on T+1 counts
    ("2026-10-15", None, True),  # T+2, no timing (the whole DAY)
    ("2026-10-16", "BeforeMarket", False),  # T+3
    ("2026-10-13", "AfterMarket", False),  # T: already announced when the night decides
    ("2026-10-17", None, False),  # a Saturday reaches Monday 10-19 (T+4)
])
def test_an_announcement_on_sessions_t1_to_tn_withholds_the_us_permission(report_date: str, timing: str | None, within: bool) -> None:
    database = _database()
    _night(database)
    _calendar(database, [_row("AAPL.US", report_date, timing), _row("KO.US", "2026-10-28", "BeforeMarket")])
    receipt = _run(database)
    aapl = _record(database, "NASDAQ", "AAPL")
    earnings = aapl["checks"]["events"]["earnings"]
    assert earnings["status"] == "calendar" and earnings["window"] == list(WINDOW) and earnings["within"] is within
    assert earnings["calendar"]["payload_sha256"] and earnings["calendar"]["received_at"] == RECEIVED.isoformat()
    assert aapl["checks"]["counterfactual"]["verdict_without_events"] == decisor.COMPRA_PERMITIDA
    if within:
        assert aapl["verdict"] == decisor.OBSERVAR and aapl["reason_codes"] == [decisor.EARNINGS_WITHIN_N]
        assert receipt["markets"]["NASDAQ"]["reasons"] == {decisor.EARNINGS_WITHIN_N: 1}
        assert receipt["markets"]["NASDAQ"]["verdicts_without_events"]["COMPRA_PERMITIDA"] == 1
    else:
        assert aapl["verdict"] == decisor.COMPRA_PERMITIDA and aapl["checks"]["events"]["marks"] == []


def test_the_window_is_n_sessions_of_the_block() -> None:
    database = _database()
    _night(database)
    _calendar(database, [_row("AAPL.US", "2026-10-16", "BeforeMarket")])  # T+3
    assert decisor.run_shadow(database, now=RUN)["markets"]["NASDAQ"]["verdicts"]["COMPRA_PERMITIDA"] == 1
    wider = replace(decisor.THRESHOLDS, earnings_window_sessions=3)
    assert decisor.run_shadow(database, now=RUN, thresholds=wider)["markets"]["NASDAQ"]["reasons"] == {decisor.EARNINGS_WITHIN_N: 1}
    assert decisor.name_earnings({"status": "absent"}, None, "NASDAQ", "AAPL", at=RUN, expected_session=SESSION,
                                 thresholds=replace(decisor.THRESHOLDS, earnings_window_sessions=0))["window"] == []


def test_on_b3_an_announcement_is_a_mark_and_never_withholds_the_permission() -> None:
    database = _database()
    _night(database)
    _calendar(database, [_row("PETR4.SA", "2026-10-14", "AfterMarket", currency="BRL")])
    receipt = _run(database)
    petr = _record(database, "B3", "PETR4")
    assert petr["verdict"] == decisor.COMPRA_PERMITIDA and petr["checks"]["events"]["marks"] == [decisor.EARNINGS_WITHIN_N]
    assert petr["checks"]["events"]["gates"] == [] and receipt["markets"]["B3"]["marks"] == {decisor.EARNINGS_WITHIN_N: 1}
    assert decisor.latest_verdict(database, "B3", "PETR4", now=datetime(2026, 10, 14, 15, 0, tzinfo=UTC))["marks"] == [decisor.EARNINGS_WITHIN_N]  # type: ignore[index]


@pytest.mark.parametrize(("received", "start", "end", "why"), [
    (RUN + timedelta(seconds=1), date(2026, 10, 7), date(2026, 11, 13), "no calendar snapshot received by the run's clock"),  # after D
    (RUN - timedelta(hours=36, seconds=1), date(2026, 10, 7), date(2026, 11, 13), "calendar received more than 36 h"),  # stale
    (RECEIVED, date(2026, 10, 7), date(2026, 10, 14), "does not cover sessions T+1..T+N"),  # the request ends at T+1
])
def test_a_calendar_after_the_clock_stale_or_short_falls_back_and_never_gates_without_an_estimate(received: datetime, start: date, end: date, why: str) -> None:
    database = _database()
    _night(database)
    _calendar(database, [_row("AAPL.US", "2026-10-14")], received=received, start=start, end=end)
    _run(database)
    aapl = _record(database, "NASDAQ", "AAPL")
    earnings = aapl["checks"]["events"]["earnings"]
    assert earnings["status"] == "unavailable" and why in earnings["detail"] and earnings["within"] is False
    assert aapl["verdict"] == decisor.COMPRA_PERMITIDA and aapl["checks"]["events"]["marks"] == [decisor.EARNINGS_CALENDAR_UNAVAILABLE]


def test_a_name_with_an_invalid_calendar_row_falls_back_to_its_estimate() -> None:
    database = _database()
    _night(database)
    _calendar(database, [{**_row("AAPL.US", "2026-10-30"), "report_date": "2026-10-30T00:00"}, _row("KO.US", "2026-10-28")])
    _filing(database, "AAPL", "0000999201-26-000001", "8-K", datetime(2026, 7, 16, 20, 30, tzinfo=UTC), items="2.02,9.01")  # + 91 d = 10-15
    _run(database)
    aapl = _record(database, "NASDAQ", "AAPL")
    earnings = aapl["checks"]["events"]["earnings"]
    assert earnings["status"] == "estimated" and "invalid row" in earnings["detail"] and earnings["estimate"]["estimated_date"] == "2026-10-15"
    assert aapl["verdict"] == decisor.OBSERVAR and aapl["reason_codes"] == [decisor.EARNINGS_WITHIN_N]
    assert aapl["checks"]["events"]["marks"] == [decisor.EARNINGS_DATE_ESTIMATED]


def test_without_a_calendar_the_051_cadence_estimate_answers_known_at_the_clock() -> None:
    database = _database()
    _night(database)
    # the last earnings release + 91 days falls in the window widened by 7 days: within, marked as an estimate
    _filing(database, "AAPL", "0000999201-26-000001", "8-K", datetime(2026, 7, 10, 20, 30, tzinfo=UTC), items="2.02,9.01")  # → 10-09 ≥ 10-07
    _filing(database, "AAPL", "0000999201-26-000002", "10-Q", datetime(2026, 8, 1, 20, 30, tzinfo=UTC))  # a later 10-Q: the release still wins
    _filing(database, "KO", "0000999202-26-000001", "10-Q", datetime(2026, 7, 4, 14, 0, tzinfo=UTC))  # no release: the statement, → 10-05 (out)
    # a release registered after the clock (a backfill) is never known by it
    _filing(database, "KO", "0000999202-26-000002", "8-K", datetime(2026, 7, 14, 20, 0, tzinfo=UTC), items="2.02", seen=RUN + timedelta(hours=1))
    _run(database)
    aapl, ko = _record(database, "NASDAQ", "AAPL"), _record(database, "NYSE", "KO")
    estimate = aapl["checks"]["events"]["earnings"]["estimate"]
    assert estimate["basis"] == "release" and estimate["filing"]["doc_id"] == "0000999201-26-000001" and estimate["estimated_date"] == "2026-10-09"
    assert estimate["range"] == ["2026-10-07", "2026-10-22"] and aapl["reason_codes"] == [decisor.EARNINGS_WITHIN_N]
    assert aapl["checks"]["events"]["marks"] == [decisor.EARNINGS_DATE_ESTIMATED]
    ko_estimate = ko["checks"]["events"]["earnings"]["estimate"]
    assert ko_estimate["basis"] == "statement" and ko_estimate["estimated_date"] == "2026-10-03" and ko["checks"]["events"]["earnings"]["within"] is False
    assert decisor.EARNINGS_WITHIN_N not in ko["reason_codes"] and ko["checks"]["events"]["marks"] == [decisor.EARNINGS_DATE_ESTIMATED]
    # with no tolerance the same estimate (10-09) is outside [T+1, T+2]
    tight = decisor.run_shadow(database, now=RUN, thresholds=replace(decisor.THRESHOLDS, earnings_estimate_tolerance_days=0))
    assert decisor.EARNINGS_WITHIN_N not in tight["markets"]["NASDAQ"]["reasons"]
    # a calendar that answers wins over the estimate
    _calendar(database, [_row("AAPL.US", "2026-10-29")])
    assert decisor.run_shadow(database, now=RUN)["markets"]["NASDAQ"]["verdicts"]["COMPRA_PERMITIDA"] == 1


def test_the_earnings_rule_alone_moves_a_verdict_and_the_counterfactual_says_which() -> None:
    database = _database()
    _night(database)
    _calendar(database, [_row("AAPL.US", "2026-10-15"), _row("KO.US", "2026-10-14")])
    receipt = _run(database)
    ko = _record(database, "NYSE", "KO")  # already OBSERVAR on its margin: the gate adds its code, the counterfactual keeps the margin's
    assert ko["reason_codes"] == ["PRICE_ABOVE_BUY_IN", "TP_MARGIN_INSUFFICIENT", decisor.EARNINGS_WITHIN_N]
    assert ko["checks"]["counterfactual"] == {"verdict_without_events": decisor.OBSERVAR, "reason_codes_without_events": ["PRICE_ABOVE_BUY_IN", "TP_MARGIN_INSUFFICIENT"]}
    assert receipt["markets"]["NASDAQ"]["verdicts"]["OBSERVAR"] == 1 and receipt["markets"]["NASDAQ"]["verdicts_without_events"]["COMPRA_PERMITIDA"] == 1
    # a VETO stays a VETO; its counterfactual too
    vetoed = _decide(_served_us(valuation_confidence=50.0), events={**CALM, "market": "NASDAQ", "earnings": {"status": "calendar", "within": True}})
    assert vetoed["verdict"] == decisor.VETO and vetoed["verdict_without_events"] == decisor.VETO and vetoed["reason_codes"][-1] == decisor.EARNINGS_WITHIN_N


def _served_us(**extra: Any) -> dict[str, Any]:
    from tests.test_valuation_decision import _row as served_row
    return {**served_row("AAPL", tp=130.0, buy_in=105.0, price=100.0, market="NASDAQ"), "official_session_date": SESSION, **extra}


# ------------------------------------------------------------------ marks: consensus cut and negative sentiment


def test_a_consensus_cut_since_the_tp_is_a_mark_read_point_in_time() -> None:
    database = _database()
    _night(database)
    _consensus(database, "NASDAQ", CUT - timedelta(days=1), {"AAPL": _fy1(6.0)})  # the snapshot closest before the TP's publication
    _consensus(database, "NASDAQ", CUT + timedelta(minutes=40), {"AAPL": _fy1(5.5)})  # tonight's, by the run's clock: ln(5.5/6) = −0.087
    _consensus(database, "NASDAQ", RUN + timedelta(minutes=1), {"AAPL": _fy1(9.0)})  # after the clock: never read
    _run(database)
    aapl = _record(database, "NASDAQ", "AAPL")
    consensus = aapl["checks"]["events"]["consensus"]
    assert consensus["status"] == "ok" and consensus["tp_eps"] == 6.0 and consensus["current_eps"] == 5.5 and consensus["cut"] is True
    assert consensus["log_change"] == pytest.approx(-0.0870, abs=1e-4) and consensus["tp_clock"] == (CUT + timedelta(minutes=1)).isoformat()
    assert aapl["verdict"] == decisor.COMPRA_PERMITIDA and decisor.CONSENSUS_EPS_CUT_SINCE_TP in aapl["checks"]["events"]["marks"]
    # a smaller cut is no mark; the same snapshot on both sides is no change; a later FY1 is compared on the TP's fiscal year
    assert not decisor._event_codes({"consensus": {**consensus, "log_change": -0.049}, "earnings": {"status": "calendar"}}, decisor.THRESHOLDS)[0]
    same = decisor.name_consensus({"snapshot_id": "s", "packets": {"AAPL": _fy1(6.0)}}, {"snapshot_id": "s", "packets": {"AAPL": _fy1(6.0)}}, "AAPL", tp_clock=CUT)
    assert same["status"] == "ok" and same["log_change"] == 0.0
    rolled = decisor.name_consensus({"packets": {"AAPL": _fy1(7.0, fiscal="2028-09-30")}}, {"packets": {"AAPL": _fy1(6.0)}}, "AAPL", tp_clock=CUT)
    assert rolled["status"] == "not_comparable"
    turned = decisor.name_consensus({"packets": {"AAPL": _fy1(-0.5)}}, {"packets": {"AAPL": _fy1(6.0)}}, "AAPL", tp_clock=CUT)
    assert turned["turned_non_positive"] is True and decisor._event_codes({"consensus": turned}, decisor.THRESHOLDS)[0][-1] == decisor.CONSENSUS_EPS_CUT_SINCE_TP
    assert decisor.name_consensus(None, {"packets": {}}, "AAPL", tp_clock=CUT)["status"] == "unavailable"


def test_a_tp_record_published_after_the_clock_never_lets_a_later_consensus_in(monkeypatch: pytest.MonkeyPatch) -> None:
    # a record published after the run's clock (a bootstrap of old cycles) is read at the clock, never at its own publication
    database = _database()
    _night(database)
    served_rows = decisor._served_rows

    def republished(db: Any, market: str, generation: Any) -> dict[str, dict[str, Any]]:
        rows = served_rows(db, market, generation)
        if "AAPL" in rows:
            rows["AAPL"]["official_published_at"] = (RUN + timedelta(hours=1)).isoformat()
        return rows

    monkeypatch.setattr(decisor, "_served_rows", republished)
    _consensus(database, "NASDAQ", CUT + timedelta(minutes=40), {"AAPL": _fy1(5.5)})
    _consensus(database, "NASDAQ", RUN + timedelta(minutes=30), {"AAPL": _fy1(9.0)})  # after the clock
    _run(database)
    consensus = _record(database, "NASDAQ", "AAPL")["checks"]["events"]["consensus"]
    assert consensus["tp_clock"] == RUN.isoformat() and consensus["tp_eps"] == consensus["current_eps"] == 5.5 and consensus["cut"] is False


def test_a_negative_weekly_sentiment_read_at_the_clock_is_a_mark_with_its_value_recorded() -> None:
    database = _database()
    _night(database)
    _sentiment(database, "AAPL", RUN - timedelta(days=2), bearish=70.0, articles=12)
    _sentiment(database, "KO", RUN + timedelta(minutes=5), bearish=90.0, articles=40)  # published after the clock: never read
    _run(database)
    aapl, ko = _record(database, "NASDAQ", "AAPL"), _record(database, "NYSE", "KO")
    sentiment = aapl["checks"]["events"]["sentiment"]
    assert sentiment["status"] == "ok" and sentiment["bearish_percent"] == 70.0 and sentiment["articles_last_week"] == 12 and sentiment["negative"] is True
    assert sentiment["published_at"] == (RUN - timedelta(days=2)).isoformat() and sentiment["external_id"].startswith("finnhub-sentiment-AAPL-")
    assert aapl["verdict"] == decisor.COMPRA_PERMITIDA and decisor.NEWS_SENTIMENT_NEGATIVE in aapl["checks"]["events"]["marks"]
    assert aapl["inputs"]["events"]["sentiment"]["bearish_percent"] == 70.0  # the only reproducible copy of the week's value
    assert ko["checks"]["events"]["sentiment"]["status"] == "unavailable" and decisor.NEWS_SENTIMENT_NEGATIVE not in ko["checks"]["events"]["marks"]
    assert _record(database, "B3", "PETR4")["checks"]["events"]["sentiment"]["status"] == "not_applicable"
    for change in ({"bearish_percent": 59.9}, {"articles_last_week": 4}, {"age_days": 8.01}):
        assert decisor.NEWS_SENTIMENT_NEGATIVE not in decisor._event_codes({"sentiment": {**sentiment, **change}}, decisor.THRESHOLDS)[0], change


# ------------------------------------------------------------------ re-runs, the block, the phase


def test_a_rerun_of_a_night_reproduces_its_events_whatever_arrived_after_it() -> None:
    database = _database()
    _night(database)
    _calendar(database, [_row("AAPL.US", "2026-10-15")])
    _consensus(database, "NASDAQ", CUT - timedelta(days=1), {"AAPL": _fy1(6.0)})
    _consensus(database, "NASDAQ", CUT + timedelta(minutes=40), {"AAPL": _fy1(5.5)})
    _sentiment(database, "AAPL", RUN - timedelta(days=2), bearish=70.0, articles=12)
    first = _run(database)
    # after the clock: a calendar that moves the date, a consensus that restores it, a new poll, a new sentiment week
    _calendar(database, [_row("AAPL.US", "2026-11-05")], received=RUN + timedelta(minutes=30))
    _consensus(database, "NASDAQ", RUN + timedelta(minutes=40), {"AAPL": _fy1(6.5)})
    _poll(database, RUN + timedelta(minutes=50))
    _sentiment(database, "AAPL", RUN + timedelta(days=7), bearish=10.0, articles=30)  # next ISO week: a new row, published after D
    again = _run(database)
    assert again["run_id"] != first["run_id"]
    for market, symbol in (("NASDAQ", "AAPL"), ("NYSE", "KO"), ("B3", "PETR4")):
        rerun, original = database.list_valuation_decisions(market, symbol)
        assert decisor.replay_sha256(rerun) == decisor.replay_sha256(original) and rerun["inputs_sha256"] == original["inputs_sha256"]
    aapl = _record(database, "NASDAQ", "AAPL")
    assert aapl["reason_codes"] == [decisor.EARNINGS_WITHIN_N]
    assert set(aapl["checks"]["events"]["marks"]) == {decisor.CONSENSUS_EPS_CUT_SINCE_TP, decisor.NEWS_SENTIMENT_NEGATIVE}


def test_the_sentiment_source_overwrites_its_week_so_only_the_recorded_value_is_reproducible() -> None:
    # the provider's row of an ISO week keeps its first publication and takes every later poll's numbers: a replay of a
    # night after a later poll of the SAME week reads other numbers — the verdict is unchanged (a mark), the record kept
    database = _database()
    _night(database)
    _sentiment(database, "AAPL", RUN - timedelta(days=2), bearish=70.0, articles=12)
    _run(database)
    _sentiment(database, "AAPL", RUN + timedelta(days=1), bearish=10.0, articles=30)  # the same week (42), polled after the clock
    _run(database)
    rerun, original = database.list_valuation_decisions("NASDAQ", "AAPL")
    assert {rerun["checks"]["events"]["sentiment"]["bearish_percent"], original["checks"]["events"]["sentiment"]["bearish_percent"]} == {70.0, 10.0}
    assert rerun["verdict"] == original["verdict"] == decisor.COMPRA_PERMITIDA and decisor.replay_sha256(rerun) != decisor.replay_sha256(original)


def test_every_event_rule_is_in_the_hashed_block() -> None:
    block = asdict(decisor.THRESHOLDS)
    changed = {"staleness_poll_source": "other", "staleness_poll_max_age_hours": 5, "earnings_window_sessions": 3, "earnings_gate_markets": ("NASDAQ",),
               "earnings_calendar_max_age_hours": 24, "earnings_estimate_offset_days": 90, "earnings_estimate_tolerance_days": 0,
               "consensus_eps_cut_log": 0.1, "news_sentiment_bearish_min_percent": 70.0, "news_sentiment_min_articles": 3,
               "news_sentiment_max_age_days": 7, "event_gates": ()}
    assert set(changed) <= set(block)
    for field, value in changed.items():
        assert decisor.thresholds_sha256(replace(decisor.THRESHOLDS, **{field: value})) != decisor.thresholds_sha256(), field
    assert decisor.PREREG_THRESHOLDS_SHA256 is None  # the block is not frozen yet: the freeze commit pins it
    assert set(decisor.EVENT_CODES) == {*decisor.MARK_CODES, decisor.EARNINGS_WITHIN_N}
    codes = (set(decisor.VETO_CODES), set(decisor.OBSERVAR_CODES), set(decisor.MARK_CODES))
    assert not (codes[0] & codes[1] or codes[0] & codes[2] or codes[1] & codes[2])
    # the block decides which event codes gate: none → the earnings code is a mark, the verdict the counterfactual's
    off = _decide(_served_us(), events={**CALM, "market": "NASDAQ", "earnings": {"status": "calendar", "within": True}})
    assert off["verdict"] == decisor.OBSERVAR
    no_gates = decisor.decide(_served_us(), expected_session=SESSION, tp_sessions_behind=0,
                              price={"price": 100.0, "source": "official_cut", "session": SESSION}, error={"status": "ok", "value": 0.10},
                              rate={"status": "ok", "h_market": 0.04}, staleness=decisor.name_staleness(None, "B3", "AAPL"),
                              events={**CALM, "market": "NASDAQ", "earnings": {"status": "calendar", "within": True}},
                              thresholds=replace(decisor.THRESHOLDS, event_gates=()))
    assert no_gates["verdict"] == decisor.COMPRA_PERMITIDA and no_gates["marks"] == [decisor.EARNINGS_WITHIN_N]


def _settings(**extra: Any) -> Settings:
    return Settings(**{"brapi_token": "brapi-test", "eodhd_api_token": "eodhd-test", "auth_cookie_secure": False, **extra})


def test_the_calendar_phase_makes_one_whole_market_call_and_stores_an_append_only_snapshot() -> None:
    database = _database()
    seen: list[httpx.Request] = []
    rows = [_row("AAPL.US", "2026-10-15"), _row("PETR4.SA", "2026-10-20", None, currency="BRL"), _row("BAD", "2026-10-15")]

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        start, end = (date.fromisoformat(request.url.params[key]) for key in ("from", "to"))
        return httpx.Response(200, content=_body(rows, start, end), headers={"content-type": "application/json; charset=utf-8"})

    service = calendar_module.EarningsCalendarService(_settings(), database, transport=httpx.MockTransport(handler), clock=lambda: RECEIVED)
    assert service.last_run_at() is None
    result = service.run()
    assert len(seen) == 1 and seen[0].url.path == calendar_module.ENDPOINT and "symbols" not in seen[0].url.params
    assert (seen[0].url.params["from"], seen[0].url.params["to"], seen[0].url.params["fmt"]) == ("2026-10-07", "2026-11-13", "json")
    assert result["events"] == 2 and result["by_exchange"] == {"SA": 1, "US": 1} and service.last_run_at() == RECEIVED
    stored = database.analysis_snapshot_at_or_before(calendar_module.ANALYSIS_TYPE, calendar_module.ENTITY_KEY, RECEIVED)
    assert stored is not None and stored["outputs"]["payload_sha256"] == hashlib.sha256(_body(rows, date(2026, 10, 7), date(2026, 11, 13))).hexdigest()
    assert stored["outputs"]["unattributed_invalid_rows"] == 1 and stored["outputs"]["parse_status"] == "OBSERVED_WITH_DIAGNOSTICS"
    read = calendar_module.calendar_at(database, RUN)
    assert read["status"] == "ok" and read["by_code"]["AAPL.US"][0]["timing"] == "AfterMarket"
    assert calendar_module.calendar_at(database, RECEIVED - timedelta(seconds=1)) == {"status": "absent"}  # received after: never read
    dumped = json.dumps(result)
    assert "eodhd-test" not in dumped and "AAPL" not in dumped  # the receipt is aggregate and never carries the token
    # an unusable answer stores nothing and fails the phase (it retries inside the window), naming no URL
    for status, body, kind in ((500, b"{}", "application/json"), (200, b"<html>", "text/html"), (200, b'{"type": "Earnings"}', "application/json")):
        failing = calendar_module.EarningsCalendarService(
            _settings(), database, transport=httpx.MockTransport(lambda request, s=status, b=body, k=kind: httpx.Response(s, content=b, headers={"content-type": k})),
            clock=lambda: RECEIVED + timedelta(hours=1))
        with pytest.raises(calendar_module.EarningsCalendarError) as caught:
            failing.run()
        assert "eodhd-test" not in str(caught.value) and "api_token" not in str(caught.value)
    assert service.last_run_at() == RECEIVED  # nothing new stored
    with pytest.raises(calendar_module.EarningsCalendarError, match="token missing"):
        calendar_module.EarningsCalendarService(_settings(eodhd_api_token=""), database).run()

    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    with pytest.raises(calendar_module.EarningsCalendarError, match="ConnectError") as caught:
        calendar_module.EarningsCalendarService(_settings(), database, transport=httpx.MockTransport(broken), clock=lambda: RECEIVED).run()
    assert "eodhd-test" not in str(caught.value)


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
    assert "if valuation_env.earnings_calendar_enabled() else ()" in phases
    health = (ROOT / "backend" / "app" / "system_health.py").read_text(encoding="utf-8")
    assert 'and (phase != "earnings_calendar" or valuation_env.earnings_calendar_enabled())' in health
