from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping

import pytest

from app import r2d2_v2_producer_earnings as earn
from app.r2d2_v2_producer_daily import ProducerError, Response

D = date(2026, 9, 8)
MATURITY = date(2026, 9, 21)
RECEIVED = datetime(2026, 9, 5, 1, 0, tzinfo=timezone.utc)
KEYS = {"coverage_verified", "window_start", "window_end", "events", "source_at", "available_at", "policy", "evidence", "exclusion"}


def _resp(payload, at: datetime = RECEIVED, path: str = "/api/x") -> Response:
    return Response(json.dumps(payload).encode(), at, path)


def _calendar(rows):
    return _resp({"type": "Earnings", "description": "", "symbols": "", "earnings": rows}, RECEIVED)


def _history(entries):
    return _resp(entries, RECEIVED + timedelta(seconds=5))


def _build(symbol, calendar, hist, horizon=None):
    horizon = horizon or earn.horizon_for(D)
    return earn.build_component(symbol, horizon, earn.calendar_rows(calendar), calendar, earn.history_entries(hist), hist, now=RECEIVED)


PUBLISHED_FAR = _history({"2026-04-30": {"reportDate": "2026-05-20", "epsActual": 0.5}})  # +91 d = 19/08 < 24/08
OTHER_ONLY = _calendar([{"code": "OTHER.US", "report_date": "2026-09-15", "before_after_market": "BeforeMarket"}])


def test_horizon_and_queried_windows_cover_the_tolerance_and_the_live_lookback() -> None:
    horizon = earn.horizon_for(D)
    assert horizon.session_date == D and horizon.maturity_date == MATURITY  # 10 sessions from 08/09 (Labor Day already past)
    assert horizon.decision_at.astimezone(earn.NEW_YORK).strftime("%H:%M") == "10:00"
    assert horizon.maturity_at.astimezone(earn.NEW_YORK).strftime("%H:%M") == "15:55"
    assert horizon.tolerance_from == date(2026, 8, 24) and horizon.tolerance_to == date(2026, 10, 6)
    assert (horizon.calendar_from, horizon.calendar_to) == (horizon.tolerance_from, horizon.tolerance_to)  # the query supports the ±15 d search
    live = earn.horizon_for(D, live_lookback=(date(2026, 8, 10), date(2026, 9, 30)))
    assert (live.calendar_from, live.calendar_to) == (date(2026, 8, 10), date(2026, 10, 15))
    with pytest.raises(ProducerError, match="SESSION_NOT_OFFICIAL"):
        earn.horizon_for(date(2026, 9, 7))
    with pytest.raises(ProducerError, match="LIVE_LOOKBACK_INVALID"):
        earn.horizon_for(D, live_lookback=(date(2026, 9, 30), date(2026, 8, 10)))


def test_granularity_is_declared_never_an_instant() -> None:
    assert earn.granularity_of("BeforeMarket") == "BMO" and earn.granularity_of("AfterMarket") == "AMC"
    assert earn.granularity_of("None") == "DAY" and earn.granularity_of(None) == "DAY" and earn.granularity_of("weird") == "DAY"
    calendar = _calendar([{"code": "ORCL.US", "report_date": "2026-09-10", "before_after_market": "AfterMarket"}])
    orcl = _build("ORCL", calendar, PUBLISHED_FAR)
    assert orcl["events"] == [{"event_date": "2026-09-10", "granularity": "AMC", "available_at": RECEIVED.isoformat()}]
    assert "event_at" not in orcl["events"][0] and set(orcl) == KEYS


def test_any_known_event_dated_inside_the_horizon_intersects_it() -> None:
    horizon = earn.horizon_for(D)
    for granularity in ("BMO", "AMC", "DAY"):
        assert earn.classify_event(D, granularity, horizon) == "EXCLUDES"  # no entry-day exception (EMENDA 3 rev 3 §3.4)
        assert earn.classify_event(MATURITY, granularity, horizon) == "EXCLUDES"  # no maturity-day exception
        assert earn.classify_event(date(2026, 9, 15), granularity, horizon) == "EXCLUDES"
        assert earn.classify_event(date(2026, 9, 12), granularity, horizon) == "EXCLUDES"  # Saturday inside the range: DAY convention, no instant
    assert earn.classify_event(date(2026, 9, 7), "AMC", horizon) == "OUTSIDE_HORIZON"
    assert earn.classify_event(date(2026, 9, 22), "BMO", horizon) == "OUTSIDE_HORIZON"
    assert earn.classify_event(D, "INSTANT", horizon, horizon.decision_at - timedelta(minutes=1)) == "PUBLISHED_BEFORE_DECISION"
    assert earn.classify_event(D, "INSTANT", horizon, horizon.decision_at) == "EXCLUDES"
    assert earn.classify_event(MATURITY, "INSTANT", horizon, horizon.maturity_at) == "EXCLUDES"
    assert earn.classify_event(MATURITY, "INSTANT", horizon, horizon.maturity_at + timedelta(seconds=1)) == "AFTER_MATURITY"
    with pytest.raises(ProducerError, match="INSTANT_WITHOUT_EVENT_AT"):
        earn.classify_event(D, "INSTANT", horizon)
    with pytest.raises(ProducerError, match="INSTANT_WITHOUT_EVENT_AT"):
        earn.classify_event(D, "INSTANT", horizon, datetime(2026, 9, 8, 12, 0))  # naive
    with pytest.raises(ProducerError, match="GRANULARITY_INVALID"):
        earn.classify_event(D, "HOUR", horizon)


def test_known_events_exclude_and_outside_events_only_silence_the_cadence() -> None:
    calendar = _calendar([{"code": "AAA.US", "report_date": "2026-09-08", "before_after_market": "BeforeMarket"},
                          {"code": "BBB.US", "report_date": "2026-09-21", "before_after_market": "AfterMarket"},
                          {"code": "CCC.US", "report_date": "2026-09-08", "before_after_market": "None"},
                          {"code": "DDD.US", "report_date": "2026-09-30", "before_after_market": "BeforeMarket"}])
    for symbol in ("AAA", "BBB", "CCC"):
        component = _build(symbol, calendar, PUBLISHED_FAR)
        assert component["coverage_verified"] is True and len(component["events"]) == 1
        assert component["exclusion"] == {"excluded": True, "reasons": ["EARNINGS_WITHIN_HORIZON"]}
    ddd = _build("DDD", calendar, PUBLISHED_FAR)  # outside the horizon: not listed; a known event in the tolerance window silences the cadence
    assert ddd["events"] == [] and ddd["exclusion"] == {"excluded": False, "reasons": []} and ddd["evidence"]["cadence_applicable"] is False
    assert ddd["evidence"]["known_events"][0]["classification"] == "OUTSIDE_HORIZON"


def test_cadence_only_excludes_and_yields_to_known_events() -> None:
    calendar = _calendar([{"code": "OTHER.US", "report_date": "2026-09-15", "before_after_market": "BeforeMarket"},
                          {"code": "EEE.US", "report_date": "2026-09-08", "before_after_market": "BeforeMarket"}])
    hist = _history({"2026-05-31": {"reportDate": "2026-06-20", "epsActual": 1.0}})  # 20/06 + 91 d = 19/09 inside [24/08, 06/10]
    fff = _build("FFF", calendar, hist)
    assert fff["coverage_verified"] is True and fff["events"] == []
    assert fff["exclusion"] == {"excluded": True, "reasons": ["EARNINGS_EXPECTED_WITHIN_HORIZON"]}
    assert fff["evidence"]["cadence_expected_report_date"] == "2026-09-19" and fff["evidence"]["cadence_excludes"] is True
    assert _build("GGG", calendar, PUBLISHED_FAR)["exclusion"]["excluded"] is False  # expected 19/08: before the window
    late = _history({"2026-06-30": {"reportDate": "2026-07-15", "epsActual": 1.0}})
    assert _build("HHH", calendar, late)["exclusion"]["excluded"] is False  # expected 14/10: after the window
    eee = _build("EEE", calendar, hist)  # a known BMO on D governs: WITHIN, and the cadence is not applied on top
    assert eee["evidence"]["cadence_applicable"] is False and eee["exclusion"]["reasons"] == ["EARNINGS_WITHIN_HORIZON"]


def test_third_evidence_is_required_and_invalid_evidence_never_counts() -> None:
    # (a) history with only a future scheduled report: no published report -> DATA, not coverage
    fresh = _history({"2026-08-31": {"reportDate": "2026-11-20", "epsActual": None}})
    iii = _build("III", OTHER_ONLY, fresh)
    assert iii["coverage_verified"] is False and iii["exclusion"] == {"excluded": True, "reasons": ["EARNINGS_LAST_REPORT_UNKNOWN"]}
    assert iii["evidence"]["last_published_report_date"] is None and iii["evidence"]["tracked"] is True
    # (b) unreadable report date: invalid evidence, and no last report either
    bad = _history({"2026-05-31": {"reportDate": "bad", "epsActual": None}})
    jjj = _build("JJJ", OTHER_ONLY, bad)
    assert jjj["coverage_verified"] is False and jjj["exclusion"]["reasons"] == ["EARNINGS_LAST_REPORT_UNKNOWN", "EARNINGS_EVIDENCE_INVALID"]
    assert jjj["evidence"]["invalid_entries"] == [{"source": "history", "key": "2026-05-31", "reason": "REPORT_DATE_UNREADABLE"}]
    # (c) a valid last report but one unreadable entry elsewhere: evidence invalid, coverage false, error preserved
    mixed = _history({"2026-04-30": {"reportDate": "2026-05-20", "epsActual": 0.5}, "x": "not-an-object", "2026-07-31": {"reportDate": "2026-08-20", "epsActual": "n/a"}})
    kkk = _build("KKK", OTHER_ONLY, mixed)
    assert kkk["coverage_verified"] is False and kkk["exclusion"]["reasons"] == ["EARNINGS_EVIDENCE_INVALID"]
    assert {e["reason"] for e in kkk["evidence"]["invalid_entries"]} == {"ENTRY_NOT_OBJECT", "EPS_ACTUAL_NOT_A_NUMBER"}
    # (d) a published report inside the horizon cannot be the last published (must be <= D-1)
    future = _history({"2026-08-31": {"reportDate": "2026-09-10", "epsActual": 2.0}})
    assert _build("LLL", OTHER_ONLY, future)["exclusion"]["reasons"] == ["EARNINGS_LAST_REPORT_UNKNOWN"]
    # (e) a calendar row of the symbol with an unreadable date is invalid evidence too
    calendar = _calendar([{"code": "MMM.US", "report_date": "2026-9-9", "before_after_market": "AfterMarket"}])
    mmm = _build("MMM", calendar, PUBLISHED_FAR)
    assert mmm["coverage_verified"] is False and mmm["exclusion"]["reasons"] == ["EARNINGS_EVIDENCE_INVALID"]
    assert mmm["evidence"]["invalid_entries"] == [{"source": "calendar", "index": 0, "reason": "REPORT_DATE_UNREADABLE"}]
    # (f) not tracked at all
    untracked = _build("NNN", OTHER_ONLY, _history({}))
    assert untracked["coverage_verified"] is False and untracked["exclusion"]["reasons"] == ["EARNINGS_NOT_TRACKED"]
    # (g) query failure
    unavailable = earn.unavailable_component(earn.horizon_for(D), OTHER_ONLY, "HTTP_502")
    assert set(unavailable) == KEYS and unavailable["coverage_verified"] is False
    assert unavailable["exclusion"] == {"excluded": True, "reasons": ["EARNINGS_SOURCE_UNAVAILABLE"]} and unavailable["evidence"]["error"] == "HTTP_502"


def test_coverage_means_the_three_evidences_validated_with_receipts() -> None:
    ooo = _build("OOO", OTHER_ONLY, PUBLISHED_FAR)
    assert ooo["coverage_verified"] is True and ooo["exclusion"] == {"excluded": False, "reasons": []}
    assert ooo["policy"] == {"rule": "EXCLUSION_RULE_V1", "amendment": earn.AMENDMENT, "amendment_sha": None, "producer": "fable-eodhd-earnings", "version": "v3"}
    assert ooo["evidence"]["calendar_payload_sha256"] == OTHER_ONLY.sha256 and ooo["evidence"]["history_payload_sha256"] == PUBLISHED_FAR.sha256
    assert ooo["evidence"]["last_published_report_date"] == "2026-05-20" and ooo["evidence"]["calendar_window"] == ["2026-08-24", "2026-10-06"]
    assert datetime.fromisoformat(ooo["window_start"]) == RECEIVED and datetime.fromisoformat(ooo["window_end"]) >= earn.horizon_for(D).maturity_at
    assert datetime.fromisoformat(ooo["available_at"]) == RECEIVED + timedelta(seconds=5)


def test_scheduled_report_from_history_and_conflicting_sources() -> None:
    hist = _history({"2026-08-31": {"reportDate": "2026-09-16", "beforeAfterMarket": "BeforeMarket", "epsActual": None},
                     "2026-05-31": {"reportDate": "2026-06-16", "epsActual": 2.0}})
    comp = _build("PPP", OTHER_ONLY, hist)
    assert comp["events"] == [{"event_date": "2026-09-16", "granularity": "BMO", "available_at": (RECEIVED + timedelta(seconds=5)).isoformat()}]
    assert comp["evidence"]["scheduled_from_history"] == ["2026-09-16"] and comp["exclusion"]["reasons"] == ["EARNINGS_WITHIN_HORIZON"]
    # calendar says AMC, history says BMO for the same date: the conservative union keeps the whole DAY
    calendar = _calendar([{"code": "PPP.US", "report_date": "2026-09-16", "before_after_market": "AfterMarket"}])
    conflict = _build("PPP", calendar, hist)
    assert conflict["events"][0]["granularity"] == "DAY" and conflict["evidence"]["known_events"][0]["provider_marker"] == "CONFLICT"


def test_empty_calendar_is_rejected() -> None:
    with pytest.raises(ProducerError, match="CALENDAR_EMPTY_OR_INVALID"):
        earn.calendar_rows(_calendar([]))


def test_produce_writes_the_round_document_with_port_components(tmp_path: Path) -> None:
    calls = []

    def fetch(path: str, params: Mapping[str, str]) -> Response:
        calls.append((path, dict(params)))
        if path == "/api/calendar/earnings":
            assert "symbols" not in params and params == {"from": "2026-08-10", "to": "2026-10-15"}
            return _calendar([{"code": "AAA.US", "report_date": "2026-09-14", "before_after_market": "None"}])
        if path == "/api/fundamentals/AAA.US":
            return PUBLISHED_FAR
        if path == "/api/fundamentals/BBB.US":
            return _history({"2026-05-31": {"reportDate": "2026-06-20", "epsActual": 1.0}})
        if path == "/api/fundamentals/LIVE.US":
            raise ProducerError("HTTP_502")
        raise AssertionError(path)

    result = earn.produce_earnings(fetch, ["AAA", "BBB", "AAA"], session_date=D, output_dir=tmp_path, now=RECEIVED,
                                   live_symbols=["LIVE"], live_lookback=(date(2026, 8, 10), date(2026, 9, 30)))
    assert result["counts"] == {"symbols": 3, "live_symbols": 1, "covered": 2, "with_events": 1, "excluded": 3,
                                "EARNINGS_WITHIN_HORIZON": 1, "EARNINGS_EXPECTED_WITHIN_HORIZON": 1, "EARNINGS_NOT_TRACKED": 0,
                                "EARNINGS_LAST_REPORT_UNKNOWN": 0, "EARNINGS_EVIDENCE_INVALID": 0, "EARNINGS_SOURCE_UNAVAILABLE": 1}
    document = json.loads((tmp_path / "earnings.json").read_bytes())
    assert document["schema"] == "V2_EARNINGS_COMPONENTS_V2" and document["rule"] == "EXCLUSION_RULE_V1" and document["amendment"] == earn.AMENDMENT
    assert document["round"]["live_lookback"] == ["2026-08-10", "2026-09-30"] and document["round"]["calendar_window"] == ["2026-08-10", "2026-10-15"]
    aaa = document["symbols"]["AAA"]
    assert set(aaa) == KEYS and aaa["events"] == [{"event_date": "2026-09-14", "granularity": "DAY", "available_at": RECEIVED.isoformat()}]
    assert document["symbols"]["BBB"]["exclusion"]["reasons"] == ["EARNINGS_EXPECTED_WITHIN_HORIZON"]
    assert document["symbols"]["LIVE"]["coverage_verified"] is False and document["symbols"]["LIVE"]["exclusion"]["reasons"] == ["EARNINGS_SOURCE_UNAVAILABLE"]
    assert [c[0] for c in calls] == ["/api/calendar/earnings", "/api/fundamentals/AAA.US", "/api/fundamentals/BBB.US", "/api/fundamentals/LIVE.US"]


def test_cli_is_off_by_default(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    monkeypatch.delenv("C3PO_R2D2_V2_PRODUCERS_ENABLED", raising=False)
    symbols = tmp_path / "symbols.txt"
    symbols.write_text("AAA\n")
    assert earn.main(["--session-date", "2026-09-08", "--symbols-file", str(symbols), "--output-dir", str(tmp_path)]) == 0
    assert '"status":"OFF"' in capsys.readouterr().out
