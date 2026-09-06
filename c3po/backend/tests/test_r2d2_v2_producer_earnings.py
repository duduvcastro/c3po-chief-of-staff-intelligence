from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import r2d2_v2_producer_earnings as earn
from app.r2d2_v2_producer_daily import ProducerError, Response

D = date(2026, 9, 8)
RECEIVED = datetime(2026, 9, 5, 1, 0, tzinfo=timezone.utc)


def _resp(payload, at: datetime = RECEIVED, path: str = "/api/x") -> Response:
    return Response(json.dumps(payload).encode(), at, path)


def test_horizon_is_ten_official_sessions_with_maturity_five_minutes_before_close() -> None:
    horizon = earn.horizon_for(D)
    assert horizon.session_date == D and horizon.maturity_date == date(2026, 9, 21)  # 10 sessions from 08/09 (Labor Day already past)
    assert horizon.decision_at.astimezone(earn.NEW_YORK).strftime("%H:%M") == "10:00"
    assert horizon.maturity_at.astimezone(earn.NEW_YORK).strftime("%H:%M") == "15:55"
    assert horizon.calendar_from == date(2026, 9, 7) and horizon.calendar_to == date(2026, 9, 22)
    with pytest.raises(ProducerError, match="SESSION_NOT_OFFICIAL"):
        earn.horizon_for(date(2026, 9, 7))


def test_event_time_conventions_are_declared_not_invented() -> None:
    at, convention = earn.convention_event_at(date(2026, 9, 10), "BeforeMarket")
    assert convention == "OFFICIAL_OPEN" and at.astimezone(earn.NEW_YORK).strftime("%H:%M") == "09:30"
    at, convention = earn.convention_event_at(date(2026, 9, 10), "AfterMarket")
    assert convention == "OFFICIAL_CLOSE" and at.astimezone(earn.NEW_YORK).strftime("%H:%M") == "16:00"
    at, convention = earn.convention_event_at(date(2026, 9, 10), "None")
    assert convention == "MIDNIGHT_NEW_YORK_UNKNOWN_TIME" and at.astimezone(earn.NEW_YORK).strftime("%H:%M") == "00:00"
    at, convention = earn.convention_event_at(date(2026, 9, 13), "BeforeMarket")  # Sunday
    assert convention == "09:30_NEW_YORK_NON_SESSION"


def _calendar(rows):
    return _resp({"type": "Earnings", "description": "", "symbols": "", "earnings": rows}, RECEIVED)


def _history(entries):
    return _resp(entries, RECEIVED + timedelta(seconds=5))


def test_coverage_requires_calendar_tracking_and_event_or_cadence() -> None:
    horizon = earn.horizon_for(D)
    calendar = _calendar([{"code": "ORCL.US", "report_date": "2026-09-10", "date": "2026-08-31", "before_after_market": "AfterMarket"},
                          {"code": "XYZ.US", "report_date": "2026-09-30", "before_after_market": "BeforeMarket"}])
    rows = earn.calendar_rows(calendar)
    # positive event inside the horizon -> covered (contract will reject the candidate)
    hist = _history({"2026-08-31": {"reportDate": "2026-09-10", "beforeAfterMarket": "AfterMarket", "epsActual": None},
                     "2026-05-31": {"reportDate": "2026-06-11", "epsActual": 1.7}})
    orcl = earn.build_component("ORCL", horizon, rows, calendar, earn.history_entries(hist), hist, now=RECEIVED)
    assert orcl["coverage_verified"] is True and len(orcl["events"]) == 1
    assert datetime.fromisoformat(orcl["events"][0]["event_at"]).astimezone(earn.NEW_YORK).strftime("%Y-%m-%d %H:%M") == "2026-09-10 16:00"
    assert set(orcl) == {"coverage_verified", "window_start", "window_end", "events", "source_at", "available_at", "producer_note"}
    assert set(orcl["events"][0]) == {"event_at", "available_at"}
    assert orcl["producer_note"]["last_published_report_date"] == "2026-06-11" and orcl["producer_note"]["cadence_attested"] is False
    # cadence attestation: last published 2026-08-20 + 60 d = 2026-10-19 > maturity 2026-09-21 -> covered without events
    hist = _history({"2026-07-31": {"reportDate": "2026-08-20", "epsActual": 0.5}})
    aaa = earn.build_component("AAA", horizon, rows, calendar, earn.history_entries(hist), hist, now=RECEIVED)
    assert aaa["coverage_verified"] is True and aaa["events"] == [] and aaa["producer_note"]["cadence_attested"] is True
    # last published too long ago and no event -> not covered
    hist = _history({"2026-03-31": {"reportDate": "2026-05-05", "epsActual": 0.5}})
    bbb = earn.build_component("BBB", horizon, rows, calendar, earn.history_entries(hist), hist, now=RECEIVED)
    assert bbb["coverage_verified"] is False and bbb["producer_note"]["reasons"] == ["NO_EVENT_AND_CADENCE_NOT_ATTESTED"]
    # not tracked by the provider -> not covered
    ccc = earn.build_component("CCC", horizon, rows, calendar, {}, _history({}), now=RECEIVED)
    assert ccc["coverage_verified"] is False and ccc["producer_note"]["reasons"] == ["SYMBOL_NOT_TRACKED_BY_PROVIDER"]
    # event outside the horizon (30/09) does not count as an event; cadence decides
    hist = _history({"2026-06-30": {"reportDate": "2026-07-30", "epsActual": 1.0}})
    xyz = earn.build_component("XYZ", horizon, rows, calendar, earn.history_entries(hist), hist, now=RECEIVED)
    assert xyz["events"] == [] and xyz["coverage_verified"] is True  # 30/07 + 60 d = 28/09 > 21/09
    # window bounds: start = calendar receipt, end = official close of the maturity session (>= maturity)
    assert datetime.fromisoformat(xyz["window_start"]) == RECEIVED
    assert datetime.fromisoformat(xyz["window_end"]) >= horizon.maturity_at


def test_scheduled_report_from_history_is_an_event_even_when_calendar_lacks_it() -> None:
    horizon = earn.horizon_for(D)
    calendar = _calendar([{"code": "OTHER.US", "report_date": "2026-09-15", "before_after_market": "BeforeMarket"}])
    hist = _history({"2026-08-31": {"reportDate": "2026-09-16", "beforeAfterMarket": "BeforeMarket", "epsActual": None},
                     "2026-05-31": {"reportDate": "2026-06-16", "epsActual": 2.0}})
    comp = earn.build_component("DDD", horizon, earn.calendar_rows(calendar), calendar, earn.history_entries(hist), hist, now=RECEIVED)
    assert comp["coverage_verified"] is True and len(comp["events"]) == 1
    assert comp["producer_note"]["scheduled_from_history"] == ["2026-09-16"]
    assert comp["producer_note"]["event_details"][0]["convention"] == "OFFICIAL_OPEN"


def test_empty_calendar_is_rejected() -> None:
    with pytest.raises(ProducerError, match="CALENDAR_EMPTY_OR_INVALID"):
        earn.calendar_rows(_calendar([]))


def test_produce_writes_component_file_with_port_shapes(tmp_path: Path) -> None:
    calls = []

    def fetch(path: str, params: dict) -> Response:
        calls.append((path, dict(params)))
        if path == "/api/calendar/earnings":
            assert "symbols" not in params and params == {"from": "2026-09-07", "to": "2026-09-22"}
            return _calendar([{"code": "AAA.US", "report_date": "2026-09-14", "before_after_market": "None"}])
        if path == "/api/fundamentals/AAA.US":
            return _history({"2026-06-30": {"reportDate": "2026-08-01", "epsActual": 1.0}})
        if path == "/api/fundamentals/BBB.US":
            return _history({"2026-03-31": {"reportDate": "2026-04-30", "epsActual": 1.0}})
        raise AssertionError(path)

    result = earn.produce_earnings(fetch, ["AAA", "BBB"], session_date=D, output_dir=tmp_path, now=RECEIVED)
    assert result["symbols"] == 2 and result["covered"] == 1
    document = json.loads((tmp_path / "earnings.json").read_bytes())
    assert document["schema"] == "V2_EARNINGS_COMPONENTS_V1" and document["rule"] == "CADENCE_RULE_V1"
    aaa = document["symbols"]["AAA"]
    assert set(aaa) == {"coverage_verified", "window_start", "window_end", "events", "source_at", "available_at"}
    assert aaa["coverage_verified"] is True and len(aaa["events"]) == 1
    assert datetime.fromisoformat(aaa["events"][0]["event_at"]).astimezone(earn.NEW_YORK).strftime("%H:%M") == "00:00"
    assert document["symbols"]["BBB"]["coverage_verified"] is False
    assert document["notes"]["BBB"]["reasons"] == ["NO_EVENT_AND_CADENCE_NOT_ATTESTED"]
    assert [c[0] for c in calls] == ["/api/calendar/earnings", "/api/fundamentals/AAA.US", "/api/fundamentals/BBB.US"]


def test_cli_is_off_by_default(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    monkeypatch.delenv("C3PO_R2D2_V2_PRODUCERS_ENABLED", raising=False)
    symbols = tmp_path / "symbols.txt"
    symbols.write_text("AAA\n")
    assert earn.main(["--session-date", "2026-09-08", "--symbols-file", str(symbols), "--output-dir", str(tmp_path)]) == 0
    assert '"status":"OFF"' in capsys.readouterr().out
