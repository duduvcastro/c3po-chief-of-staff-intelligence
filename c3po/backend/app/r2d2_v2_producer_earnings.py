"""R2D2 V2 — earnings producer with a verifiable coverage rule (EODHD calendar + earnings history).

Produces `components/<D>/earnings.json` for the causal list of session D: one
`earnings` component per symbol in the exact shape of the V2 file port
(`coverage_verified`, `window_start`, `window_end`, `events[{event_at,
available_at}]`, `source_at`, `available_at`).

Coverage rule (proposed by Fable on #348, 06/09/2026; to be signed in the
sources' readiness declaration): `coverage_verified` is true for a symbol and
the horizon [decision at 10:00 ET of D, maturity = official close of the 10th
session minus 5 minutes] only when all of the following hold:

1. the provider's earnings calendar was queried for the WHOLE market (no symbol
   filter) covering [D-1, maturity + 1 session], answered HTTP 200 with a
   non-empty list; raw bytes and the receipt instant are preserved;
2. the provider tracks the symbol's earnings (`Earnings::History` present and
   non-empty in its fundamentals);
3. either a positive event exists inside the horizon (which then makes the
   candidate ineligible by contract), or the negative attestation by cadence
   holds: last PUBLISHED report date (an entry with a non-null actual EPS and
   report date <= D-1) + 60 days > maturity date.

Event instants follow a declared convention, never a claimed publication time:
BeforeMarket = official open of the report date, AfterMarket = official close,
unknown/None = 00:00 New York of the report date (conservative: inside the
horizon whenever the date is). Nothing here decides eligibility; the contract
does. OFF by default; the token never leaves the fetcher.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from .r2d2_v2_producer_daily import EodhdFetcher, Fetcher, ProducerError, Response, canonical, write_private

PRODUCER = "fable-eodhd-earnings"
PRODUCER_VERSION = "v1"
RULE_VERSION = "CADENCE_RULE_V1"
NEW_YORK = ZoneInfo("America/New_York")
HORIZON_SESSIONS = 10
CADENCE_DAYS = 60
DECISION_TIME = time(10, 0)
MATURITY_LEAD = timedelta(minutes=5)
CONVENTIONS = {"BeforeMarket": "OFFICIAL_OPEN", "AfterMarket": "OFFICIAL_CLOSE"}


def _iso(at: datetime) -> str:
    return at.astimezone(timezone.utc).isoformat()


def _calendar():
    import exchange_calendars
    return exchange_calendars.get_calendar("XNYS")


def horizon_sessions(session_date: date) -> tuple[date, ...]:
    calendar = _calendar()
    if not calendar.is_session(session_date.isoformat()):
        raise ProducerError("SESSION_NOT_OFFICIAL")
    window = calendar.sessions_window(session_date.isoformat(), HORIZON_SESSIONS)
    sessions = tuple(stamp.date() for stamp in window)
    if len(sessions) != HORIZON_SESSIONS or sessions[0] != session_date:
        raise ProducerError("HORIZON_WINDOW_INVALID")
    return sessions


def session_bounds(day: date) -> tuple[datetime, datetime]:
    calendar = _calendar()
    return (calendar.session_open(day.isoformat()).to_pydatetime().astimezone(timezone.utc),
            calendar.session_close(day.isoformat()).to_pydatetime().astimezone(timezone.utc))


def next_session_after(day: date) -> date:
    return _calendar().next_session(day.isoformat()).date()


@dataclass(frozen=True)
class Horizon:
    session_date: date
    decision_at: datetime
    maturity_date: date
    maturity_at: datetime
    calendar_from: date
    calendar_to: date


def horizon_for(session_date: date) -> Horizon:
    sessions = horizon_sessions(session_date)
    _, last_close = session_bounds(sessions[-1])
    decision_at = datetime.combine(session_date, DECISION_TIME, NEW_YORK).astimezone(timezone.utc)
    return Horizon(session_date, decision_at, sessions[-1], last_close - MATURITY_LEAD,
                   calendar_from=session_date - timedelta(days=1), calendar_to=next_session_after(sessions[-1]))


def convention_event_at(report_date: date, before_after_market: Any) -> tuple[datetime, str]:
    """Declared convention for the instant of an announcement dated without a precise time."""
    calendar = _calendar()
    is_session = bool(calendar.is_session(report_date.isoformat()))
    if before_after_market == "BeforeMarket":
        if is_session:
            return session_bounds(report_date)[0], "OFFICIAL_OPEN"
        return datetime.combine(report_date, time(9, 30), NEW_YORK).astimezone(timezone.utc), "09:30_NEW_YORK_NON_SESSION"
    if before_after_market == "AfterMarket":
        if is_session:
            return session_bounds(report_date)[1], "OFFICIAL_CLOSE"
        return datetime.combine(report_date, time(16, 0), NEW_YORK).astimezone(timezone.utc), "16:00_NEW_YORK_NON_SESSION"
    return datetime.combine(report_date, time(0, 0), NEW_YORK).astimezone(timezone.utc), "MIDNIGHT_NEW_YORK_UNKNOWN_TIME"


def _date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def calendar_rows(response: Response) -> list[dict[str, Any]]:
    payload = response.json()
    rows = payload.get("earnings") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not rows:
        raise ProducerError("CALENDAR_EMPTY_OR_INVALID")
    return [row for row in rows if isinstance(row, dict)]


def history_entries(response: Response) -> dict[str, dict[str, Any]]:
    payload = response.json()
    if not isinstance(payload, dict):
        return {}
    return {key: value for key, value in payload.items() if isinstance(value, dict)}


def build_component(symbol: str, horizon: Horizon, calendar: Sequence[Mapping[str, Any]], calendar_response: Response,
                    history: Mapping[str, Mapping[str, Any]], history_response: Response, *, now: datetime) -> dict[str, Any]:
    code = f"{symbol}.US"
    events: dict[date, dict[str, Any]] = {}
    for row in calendar:
        report = _date(row.get("report_date"))
        if row.get("code") != code or report is None or not horizon.session_date <= report <= horizon.maturity_date:
            continue
        event_at, convention = convention_event_at(report, row.get("before_after_market"))
        events[report] = {"event_at": _iso(event_at), "available_at": _iso(calendar_response.received_at),
                          "report_date": report.isoformat(), "before_after_market": row.get("before_after_market"),
                          "convention": convention, "source": "calendar"}
    last_published: date | None = None
    scheduled_in_history: list[str] = []
    for entry in history.values():
        report = _date(entry.get("reportDate"))
        if report is None:
            continue
        actual = entry.get("epsActual")
        if actual is not None and report <= horizon.session_date - timedelta(days=1):
            last_published = report if last_published is None or report > last_published else last_published
        if actual is None and horizon.session_date <= report <= horizon.maturity_date and report not in events:
            event_at, convention = convention_event_at(report, entry.get("beforeAfterMarket"))
            events[report] = {"event_at": _iso(event_at), "available_at": _iso(history_response.received_at),
                              "report_date": report.isoformat(), "before_after_market": entry.get("beforeAfterMarket"),
                              "convention": convention, "source": "fundamentals_history"}
            scheduled_in_history.append(report.isoformat())
    cadence_ok = last_published is not None and last_published + timedelta(days=CADENCE_DAYS) > horizon.maturity_date
    tracked = bool(history)
    covered = tracked and (bool(events) or cadence_ok)
    reasons = []
    if not tracked:
        reasons.append("SYMBOL_NOT_TRACKED_BY_PROVIDER")
    if tracked and not events and not cadence_ok:
        reasons.append("NO_EVENT_AND_CADENCE_NOT_ATTESTED")
    window_start = calendar_response.received_at
    window_end = session_bounds(horizon.maturity_date)[1]
    ordered = [events[key] for key in sorted(events)]
    return {
        "coverage_verified": covered,
        "window_start": _iso(window_start), "window_end": _iso(window_end),
        "events": [{"event_at": item["event_at"], "available_at": item["available_at"]} for item in ordered],
        "source_at": _iso(min(calendar_response.received_at, history_response.received_at)),
        "available_at": _iso(max(calendar_response.received_at, history_response.received_at)),
        "producer_note": {"producer": PRODUCER, "version": PRODUCER_VERSION, "rule": RULE_VERSION,
                          "decision_at": _iso(horizon.decision_at), "maturity_at": _iso(horizon.maturity_at),
                          "last_published_report_date": last_published.isoformat() if last_published else None,
                          "cadence_days": CADENCE_DAYS, "cadence_attested": cadence_ok,
                          "event_details": ordered, "scheduled_from_history": scheduled_in_history,
                          "reasons": reasons, "calendar_payload_sha256": calendar_response.sha256,
                          "history_payload_sha256": history_response.sha256},
    }


def produce_earnings(fetch: Fetcher, symbols: Sequence[str], *, session_date: date, output_dir: Path, now: datetime | None = None) -> dict[str, Any]:
    clock = now or datetime.now(timezone.utc)
    horizon = horizon_for(session_date)
    calendar_response = fetch("/api/calendar/earnings", {"from": horizon.calendar_from.isoformat(), "to": horizon.calendar_to.isoformat()})
    rows = calendar_rows(calendar_response)
    components: dict[str, dict[str, Any]] = {}
    covered = 0
    for symbol in symbols:
        history_response = fetch(f"/api/fundamentals/{symbol}.US", {"filter": "Earnings::History"})
        component = build_component(symbol, horizon, rows, calendar_response, history_entries(history_response), history_response, now=clock)
        components[symbol] = component
        covered += int(component["coverage_verified"])
    document = {"schema": "V2_EARNINGS_COMPONENTS_V1", "session_date": session_date.isoformat(), "rule": RULE_VERSION,
                "calendar": {"from": horizon.calendar_from.isoformat(), "to": horizon.calendar_to.isoformat(),
                             "rows": len(rows), "payload_sha256": calendar_response.sha256, "received_at": _iso(calendar_response.received_at)},
                "conventions": {"BeforeMarket": "OFFICIAL_OPEN", "AfterMarket": "OFFICIAL_CLOSE", "unknown": "MIDNIGHT_NEW_YORK_UNKNOWN_TIME"},
                "symbols": {symbol: {k: v for k, v in component.items() if k != "producer_note"} for symbol, component in components.items()},
                "notes": {symbol: component["producer_note"] for symbol, component in components.items()},
                "counts": {"symbols": len(symbols), "covered": covered, "with_events": sum(1 for c in components.values() if c["events"])}}
    digest = write_private(output_dir / "earnings.json", canonical(document))
    return {"session_date": session_date.isoformat(), "symbols": len(symbols), "covered": covered, "sha256": digest, "output": str(output_dir / "earnings.json")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--symbols-file", required=True, help="causal-list symbols, one per line")
    parser.add_argument("--output-dir", required=True, help="components/<D> directory")
    args = parser.parse_args(argv)
    if os.environ.get("C3PO_R2D2_V2_PRODUCERS_ENABLED", "").lower() != "true":
        print('{"status":"OFF","reason":"C3PO_R2D2_V2_PRODUCERS_ENABLED is not true"}')
        return 0
    from .config import get_settings
    settings = get_settings()
    fetch = EodhdFetcher(settings.eodhd_base_url, settings.eodhd_api_token, timeout=settings.market_data_timeout_seconds)
    symbols = [line.strip() for line in Path(args.symbols_file).read_text(encoding="utf-8").splitlines() if line.strip()]
    result = produce_earnings(fetch, symbols, session_date=date.fromisoformat(args.session_date), output_dir=Path(args.output_dir))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
