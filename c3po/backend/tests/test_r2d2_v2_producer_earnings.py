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
PORT_KEYS = {"coverage_verified", "window_start", "window_end", "events", "source_at", "available_at"}


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


def test_horizon_is_ten_official_sessions_with_maturity_five_minutes_before_close() -> None:
    horizon = earn.horizon_for(D)
    assert horizon.session_date == D and horizon.maturity_date == MATURITY  # 10 sessions from 08/09 (Labor Day already past)
    assert horizon.decision_at.astimezone(earn.NEW_YORK).strftime("%H:%M") == "10:00"
    assert horizon.maturity_at.astimezone(earn.NEW_YORK).strftime("%H:%M") == "15:55"
    assert horizon.calendar_from == date(2026, 9, 7) and horizon.calendar_to == date(2026, 9, 22)
    assert horizon.tolerance_from == date(2026, 8, 24) and horizon.tolerance_to == date(2026, 10, 6)
    with pytest.raises(ProducerError, match="SESSION_NOT_OFFICIAL"):
        earn.horizon_for(date(2026, 9, 7))


def test_granularity_is_declared_never_an_instant() -> None:
    assert earn.granularity_of("BeforeMarket") == "BMO" and earn.granularity_of("AfterMarket") == "AMC"
    assert earn.granularity_of("None") == "DAY" and earn.granularity_of(None) == "DAY" and earn.granularity_of("weird") == "DAY"
    calendar = _calendar([{"code": "ORCL.US", "report_date": "2026-09-10", "before_after_market": "AfterMarket"}])
    orcl = _build("ORCL", calendar, PUBLISHED_FAR)
    assert orcl["events"] == [{"event_date": "2026-09-10", "granularity": "AMC", "available_at": RECEIVED.isoformat()}]
    assert "event_at" not in orcl["events"][0]


def test_entry_and_maturity_day_rules() -> None:
    horizon = earn.horizon_for(D)
    assert earn.classify_event(D, "BMO", horizon) == "PUBLISHED_BEFORE_DECISION"
    assert earn.classify_event(D, "AMC", horizon) == "EXCLUDES"
    assert earn.classify_event(D, "DAY", horizon) == "EXCLUDES"
    assert earn.classify_event(MATURITY, "AMC", horizon) == "AFTER_MATURITY"
    assert earn.classify_event(MATURITY, "BMO", horizon) == "EXCLUDES"
    assert earn.classify_event(MATURITY, "DAY", horizon) == "EXCLUDES"
    assert earn.classify_event(date(2026, 9, 15), "BMO", horizon) == "EXCLUDES"
    assert earn.classify_event(date(2026, 9, 7), "AMC", horizon) == "OUTSIDE_HORIZON"
    assert earn.classify_event(date(2026, 9, 22), "BMO", horizon) == "OUTSIDE_HORIZON"
    before = horizon.decision_at - timedelta(minutes=1)
    assert earn.classify_event(D, "INSTANT", horizon, before) == "PUBLISHED_BEFORE_DECISION"
    assert earn.classify_event(D, "INSTANT", horizon, horizon.decision_at) == "EXCLUDES"
    assert earn.classify_event(MATURITY, "INSTANT", horizon, horizon.maturity_at) == "EXCLUDES"
    assert earn.classify_event(MATURITY, "INSTANT", horizon, horizon.maturity_at + timedelta(seconds=1)) == "AFTER_MATURITY"
    with pytest.raises(ProducerError, match="INSTANT_WITHOUT_EVENT_AT"):
        earn.classify_event(D, "INSTANT", horizon)
    with pytest.raises(ProducerError, match="GRANULARITY_INVALID"):
        earn.classify_event(D, "HOUR", horizon)


def test_known_events_drive_exclusion_advice_by_granularity() -> None:
    calendar = _calendar([{"code": "AAA.US", "report_date": "2026-09-08", "before_after_market": "BeforeMarket"},
                          {"code": "BBB.US", "report_date": "2026-09-21", "before_after_market": "AfterMarket"},
                          {"code": "CCC.US", "report_date": "2026-09-08", "before_after_market": "None"},
                          {"code": "DDD.US", "report_date": "2026-09-30", "before_after_market": "BeforeMarket"}])
    aaa = _build("AAA", calendar, PUBLISHED_FAR)  # BMO on D: published before the decision, listed, no exclusion
    assert aaa["coverage_verified"] is True and len(aaa["events"]) == 1
    assert aaa["producer_note"]["exclusion_advice"] is False and aaa["producer_note"]["reasons"] == []
    bbb = _build("BBB", calendar, PUBLISHED_FAR)  # AMC on the maturity day: after maturity, listed, no exclusion
    assert bbb["events"][0]["granularity"] == "AMC" and bbb["producer_note"]["reasons"] == []
    ccc = _build("CCC", calendar, PUBLISHED_FAR)  # whole DAY on D: excludes
    assert ccc["events"][0]["granularity"] == "DAY" and ccc["producer_note"]["reasons"] == ["EARNINGS_WITHIN_HORIZON"]
    ddd = _build("DDD", calendar, PUBLISHED_FAR)  # outside the horizon: not listed, cadence not applicable (known event in tolerance)
    assert ddd["events"] == [] and ddd["producer_note"]["reasons"] == [] and ddd["producer_note"]["cadence_applicable"] is False
    assert set(aaa) == PORT_KEYS | {"producer_note"}


def test_cadence_only_excludes_and_yields_to_known_events() -> None:
    calendar = _calendar([{"code": "OTHER.US", "report_date": "2026-09-15", "before_after_market": "BeforeMarket"},
                          {"code": "EEE.US", "report_date": "2026-09-08", "before_after_market": "BeforeMarket"}])
    # last published 20/06 + 91 d = 19/09 inside [24/08, 06/10] and no known event -> expected within horizon
    hist = _history({"2026-05-31": {"reportDate": "2026-06-20", "epsActual": 1.0}})
    fff = _build("FFF", calendar, hist)
    assert fff["coverage_verified"] is True and fff["events"] == []
    assert fff["producer_note"]["reasons"] == ["EARNINGS_EXPECTED_WITHIN_HORIZON"]
    assert fff["producer_note"]["cadence_expected_report_date"] == "2026-09-19" and fff["producer_note"]["cadence_excludes"] is True
    # expected before the window (19/08) or after it (14/10) -> no exclusion
    assert _build("GGG", calendar, PUBLISHED_FAR)["producer_note"]["reasons"] == []
    late = _history({"2026-06-30": {"reportDate": "2026-07-15", "epsActual": 1.0}})
    assert _build("HHH", calendar, late)["producer_note"]["reasons"] == []
    # the same cadence, but a known BMO already published on D governs: no re-exclusion
    eee = _build("EEE", calendar, hist)
    assert eee["producer_note"]["cadence_applicable"] is False and eee["producer_note"]["reasons"] == []
    # no published report (new listing) -> cadence has nothing to say
    fresh = _history({"2026-08-31": {"reportDate": "2026-11-20", "epsActual": None}})
    iii = _build("III", calendar, fresh)
    assert iii["producer_note"]["cadence_expected_report_date"] is None and iii["producer_note"]["reasons"] == []
    # a published report inside the horizon window cannot count as "last published" (must be <= D-1)
    future = _history({"2026-08-31": {"reportDate": "2026-09-10", "epsActual": 2.0}})
    jjj = _build("JJJ", calendar, future)
    assert jjj["producer_note"]["last_published_report_date"] is None


def test_coverage_means_sources_consulted_with_evidence() -> None:
    calendar = _calendar([{"code": "OTHER.US", "report_date": "2026-09-15", "before_after_market": "BeforeMarket"}])
    kkk = _build("KKK", calendar, PUBLISHED_FAR)
    assert kkk["coverage_verified"] is True and kkk["producer_note"]["exclusion_advice"] is False
    assert kkk["producer_note"]["calendar_payload_sha256"] == calendar.sha256
    assert datetime.fromisoformat(kkk["window_start"]) == RECEIVED
    assert datetime.fromisoformat(kkk["window_end"]) >= earn.horizon_for(D).maturity_at
    assert datetime.fromisoformat(kkk["available_at"]) == RECEIVED + timedelta(seconds=5)
    untracked = _build("LLL", calendar, _history({}))
    assert untracked["coverage_verified"] is False and untracked["producer_note"]["reasons"] == ["EARNINGS_NOT_TRACKED"]
    unavailable = earn.unavailable_component(earn.horizon_for(D), calendar, "HTTP_502")
    assert unavailable["coverage_verified"] is False and unavailable["events"] == []
    assert unavailable["producer_note"]["reasons"] == ["EARNINGS_SOURCE_UNAVAILABLE"] and unavailable["producer_note"]["error"] == "HTTP_502"
    assert set(unavailable) == PORT_KEYS | {"producer_note"}


def test_scheduled_report_from_history_is_a_known_event_even_when_calendar_lacks_it() -> None:
    calendar = _calendar([{"code": "OTHER.US", "report_date": "2026-09-15", "before_after_market": "BeforeMarket"}])
    hist = _history({"2026-08-31": {"reportDate": "2026-09-16", "beforeAfterMarket": "BeforeMarket", "epsActual": None},
                     "2026-05-31": {"reportDate": "2026-06-16", "epsActual": 2.0}})
    comp = _build("MMM", calendar, hist)
    assert comp["events"] == [{"event_date": "2026-09-16", "granularity": "BMO", "available_at": (RECEIVED + timedelta(seconds=5)).isoformat()}]
    assert comp["producer_note"]["scheduled_from_history"] == ["2026-09-16"]
    assert comp["producer_note"]["reasons"] == ["EARNINGS_WITHIN_HORIZON"] and comp["producer_note"]["cadence_applicable"] is False
    assert comp["producer_note"]["known_events"][0]["source"] == "fundamentals_history"


def test_empty_calendar_is_rejected() -> None:
    with pytest.raises(ProducerError, match="CALENDAR_EMPTY_OR_INVALID"):
        earn.calendar_rows(_calendar([]))


def test_produce_writes_component_file_with_port_shapes(tmp_path: Path) -> None:
    calls = []

    def fetch(path: str, params: Mapping[str, str]) -> Response:
        calls.append((path, dict(params)))
        if path == "/api/calendar/earnings":
            assert "symbols" not in params and params == {"from": "2026-09-07", "to": "2026-09-22"}
            return _calendar([{"code": "AAA.US", "report_date": "2026-09-14", "before_after_market": "None"}])
        if path == "/api/fundamentals/AAA.US":
            return PUBLISHED_FAR
        if path == "/api/fundamentals/BBB.US":
            return _history({"2026-05-31": {"reportDate": "2026-06-20", "epsActual": 1.0}})
        if path == "/api/fundamentals/LIVE.US":
            raise ProducerError("HTTP_502")
        raise AssertionError(path)

    result = earn.produce_earnings(fetch, ["AAA", "BBB", "AAA"], session_date=D, output_dir=tmp_path, now=RECEIVED, live_symbols=["LIVE"])
    assert result["counts"] == {"symbols": 3, "live_symbols": 1, "covered": 2, "with_events": 1, "exclusion_advice": 3,
                                "EARNINGS_WITHIN_HORIZON": 1, "EARNINGS_EXPECTED_WITHIN_HORIZON": 1,
                                "EARNINGS_NOT_TRACKED": 0, "EARNINGS_SOURCE_UNAVAILABLE": 1}
    document = json.loads((tmp_path / "earnings.json").read_bytes())
    assert document["schema"] == "V2_EARNINGS_COMPONENTS_V2" and document["rule"] == "EXCLUSION_RULE_V1"
    assert document["live_symbols"] == ["LIVE"] and document["horizon"]["maturity_date"] == "2026-09-21"
    aaa = document["symbols"]["AAA"]
    assert set(aaa) == PORT_KEYS and aaa["events"] == [{"event_date": "2026-09-14", "granularity": "DAY", "available_at": RECEIVED.isoformat()}]
    assert document["notes"]["BBB"]["reasons"] == ["EARNINGS_EXPECTED_WITHIN_HORIZON"]
    assert document["symbols"]["LIVE"]["coverage_verified"] is False and document["notes"]["LIVE"]["reasons"] == ["EARNINGS_SOURCE_UNAVAILABLE"]
    assert [c[0] for c in calls] == ["/api/calendar/earnings", "/api/fundamentals/AAA.US", "/api/fundamentals/BBB.US", "/api/fundamentals/LIVE.US"]


def test_cli_is_off_by_default(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    monkeypatch.delenv("C3PO_R2D2_V2_PRODUCERS_ENABLED", raising=False)
    symbols = tmp_path / "symbols.txt"
    symbols.write_text("AAA\n")
    assert earn.main(["--session-date", "2026-09-08", "--symbols-file", str(symbols), "--output-dir", str(tmp_path)]) == 0
    assert '"status":"OFF"' in capsys.readouterr().out
