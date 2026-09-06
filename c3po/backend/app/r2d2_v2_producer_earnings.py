"""R2D2 V2 — earnings producer: conservative exclusion with declared granularity (EMENDA 3, draft under parecer).

Produces `components/<D>/earnings.json` for the causal list of session D (and,
per EMENDA 3 §3.5, for the live names re-queried daily): one `earnings`
component per symbol in the shape proposed by EMENDA 3 §4 for the V2 file port:
`coverage_verified`, `window_start`, `window_end`,
`events[{event_date, granularity, available_at, event_at?}]`, `source_at`,
`available_at`. `event_at` exists only for `INSTANT` events; EODHD never gives
an instant, so this producer emits `BMO`, `AMC` or `DAY` and no instant.

Rule EXCLUSION_RULE_V1 (EMENDA 3 §3; the producer only reports, the contract
decides):

1. sources, with bytes and receipt instants preserved: (a) the provider's
   earnings calendar for the WHOLE market covering [D-1, maturity + 1 session];
   (b) the symbol's earnings history (`Earnings::History`), which also carries
   scheduled reports; (c) the last PUBLISHED report date (non-null actual EPS,
   report date <= D-1);
2. conservative exclusion advice: (i) a calendar event dated in [D, maturity
   date]; (ii) a scheduled report in the history dated in [D, maturity date];
   (iii) cadence: last published + 91 d inside [D - 15 d, maturity + 15 d],
   applied only when no known event falls inside that tolerance window. The
   cadence only excludes, never includes;
3. `coverage_verified` means "sources consulted successfully with evidence
   preserved": calendar non-empty for the market and history present for the
   symbol. Not tracked -> EARNINGS_NOT_TRACKED; query failure ->
   EARNINGS_SOURCE_UNAVAILABLE;
4. granularity rules on the entry day D (BMO published before the 10:00 ET
   decision does not exclude; AMC and DAY exclude) and on the maturity day (AMC
   after the 15:55 ET maturity does not exclude; BMO and DAY exclude).

Coverage of unknown events remains the spec's own event exit (§2.5). OFF by
default; the token never leaves the fetcher.
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
PRODUCER_VERSION = "v2"
RULE_VERSION = "EXCLUSION_RULE_V1"
SCHEMA = "V2_EARNINGS_COMPONENTS_V2"
NEW_YORK = ZoneInfo("America/New_York")
HORIZON_SESSIONS = 10
CADENCE_DAYS = 91
CADENCE_TOLERANCE = timedelta(days=15)
DECISION_TIME = time(10, 0)
MATURITY_LEAD = timedelta(minutes=5)
GRANULARITIES = ("DAY", "BMO", "AMC", "INSTANT")
PROVIDER_GRANULARITY = {"BeforeMarket": "BMO", "AfterMarket": "AMC"}
EXCLUDES = "EXCLUDES"
PUBLISHED_BEFORE_DECISION = "PUBLISHED_BEFORE_DECISION"
AFTER_MATURITY = "AFTER_MATURITY"
OUTSIDE_HORIZON = "OUTSIDE_HORIZON"
REASON_WITHIN = "EARNINGS_WITHIN_HORIZON"
REASON_EXPECTED = "EARNINGS_EXPECTED_WITHIN_HORIZON"
REASON_NOT_TRACKED = "EARNINGS_NOT_TRACKED"
REASON_UNAVAILABLE = "EARNINGS_SOURCE_UNAVAILABLE"
REASONS = (REASON_WITHIN, REASON_EXPECTED, REASON_NOT_TRACKED, REASON_UNAVAILABLE)


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

    @property
    def tolerance_from(self) -> date:
        return self.session_date - CADENCE_TOLERANCE

    @property
    def tolerance_to(self) -> date:
        return self.maturity_date + CADENCE_TOLERANCE


def horizon_for(session_date: date) -> Horizon:
    sessions = horizon_sessions(session_date)
    _, last_close = session_bounds(sessions[-1])
    decision_at = datetime.combine(session_date, DECISION_TIME, NEW_YORK).astimezone(timezone.utc)
    return Horizon(session_date, decision_at, sessions[-1], last_close - MATURITY_LEAD,
                   calendar_from=session_date - timedelta(days=1), calendar_to=next_session_after(sessions[-1]))


def granularity_of(before_after_market: Any) -> str:
    """Provider marker -> declared granularity. Anything unknown is the whole DAY (conservative)."""
    if isinstance(before_after_market, str):
        return PROVIDER_GRANULARITY.get(before_after_market, "DAY")
    return "DAY"


def classify_event(event_date: date, granularity: str, horizon: Horizon, event_at: datetime | None = None) -> str:
    """EMENDA 3 §3.4: how one known event relates to the horizon [decision, maturity]."""
    if granularity not in GRANULARITIES:
        raise ProducerError("GRANULARITY_INVALID")
    if not horizon.session_date <= event_date <= horizon.maturity_date:
        return OUTSIDE_HORIZON
    if granularity == "INSTANT":
        if event_at is None:
            raise ProducerError("INSTANT_WITHOUT_EVENT_AT")
        if event_at < horizon.decision_at:
            return PUBLISHED_BEFORE_DECISION
        if event_at > horizon.maturity_at:
            return AFTER_MATURITY
        return EXCLUDES
    if event_date == horizon.session_date and granularity == "BMO":
        return PUBLISHED_BEFORE_DECISION
    if event_date == horizon.maturity_date and granularity == "AMC":
        return AFTER_MATURITY
    return EXCLUDES


def cadence_expected(last_published: date | None) -> date | None:
    return None if last_published is None else last_published + timedelta(days=CADENCE_DAYS)


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


def _port_event(item: Mapping[str, Any]) -> dict[str, Any]:
    event = {"event_date": item["event_date"], "granularity": item["granularity"], "available_at": item["available_at"]}
    if item["granularity"] == "INSTANT":
        event["event_at"] = item["event_at"]
    return event


def build_component(symbol: str, horizon: Horizon, calendar: Sequence[Mapping[str, Any]], calendar_response: Response,
                    history: Mapping[str, Mapping[str, Any]], history_response: Response, *, now: datetime) -> dict[str, Any]:
    code = f"{symbol}.US"
    known: dict[date, dict[str, Any]] = {}
    for row in calendar:
        report = _date(row.get("report_date"))
        if row.get("code") != code or report is None:
            continue
        granularity = granularity_of(row.get("before_after_market"))
        known[report] = {"event_date": report.isoformat(), "granularity": granularity, "event_at": None,
                         "available_at": _iso(calendar_response.received_at), "provider_marker": row.get("before_after_market"),
                         "source": "calendar", "classification": classify_event(report, granularity, horizon)}
    last_published: date | None = None
    scheduled_in_history: list[str] = []
    for entry in history.values():
        report = _date(entry.get("reportDate"))
        if report is None:
            continue
        if entry.get("epsActual") is not None and report <= horizon.session_date - timedelta(days=1):
            last_published = report if last_published is None or report > last_published else last_published
        if entry.get("epsActual") is None and report >= horizon.session_date and report not in known:
            granularity = granularity_of(entry.get("beforeAfterMarket"))
            known[report] = {"event_date": report.isoformat(), "granularity": granularity, "event_at": None,
                             "available_at": _iso(history_response.received_at), "provider_marker": entry.get("beforeAfterMarket"),
                             "source": "fundamentals_history", "classification": classify_event(report, granularity, horizon)}
            scheduled_in_history.append(report.isoformat())
    ordered = [known[key] for key in sorted(known)]
    in_horizon = [item for item in ordered if item["classification"] != OUTSIDE_HORIZON]
    known_in_tolerance = any(horizon.tolerance_from <= key <= horizon.tolerance_to for key in known)
    expected = cadence_expected(last_published)
    cadence_excludes = (expected is not None and not known_in_tolerance
                        and horizon.tolerance_from <= expected <= horizon.tolerance_to)
    tracked = bool(history)
    reasons: list[str] = []
    if not tracked:
        reasons.append(REASON_NOT_TRACKED)
    if any(item["classification"] == EXCLUDES for item in in_horizon):
        reasons.append(REASON_WITHIN)
    if cadence_excludes:
        reasons.append(REASON_EXPECTED)
    window_end = session_bounds(horizon.maturity_date)[1]
    return {
        "coverage_verified": tracked,
        "window_start": _iso(calendar_response.received_at), "window_end": _iso(window_end),
        "events": [_port_event(item) for item in in_horizon],
        "source_at": _iso(min(calendar_response.received_at, history_response.received_at)),
        "available_at": _iso(max(calendar_response.received_at, history_response.received_at)),
        "producer_note": {"producer": PRODUCER, "version": PRODUCER_VERSION, "rule": RULE_VERSION,
                          "decision_at": _iso(horizon.decision_at), "maturity_at": _iso(horizon.maturity_at),
                          "tolerance_window": [horizon.tolerance_from.isoformat(), horizon.tolerance_to.isoformat()],
                          "last_published_report_date": last_published.isoformat() if last_published else None,
                          "cadence_days": CADENCE_DAYS, "cadence_expected_report_date": expected.isoformat() if expected else None,
                          "cadence_applicable": not known_in_tolerance, "cadence_excludes": cadence_excludes,
                          "known_events": ordered, "scheduled_from_history": scheduled_in_history,
                          "exclusion_advice": bool(reasons), "reasons": reasons,
                          "calendar_payload_sha256": calendar_response.sha256, "history_payload_sha256": history_response.sha256},
    }


def unavailable_component(horizon: Horizon, calendar_response: Response, error: str) -> dict[str, Any]:
    window_end = session_bounds(horizon.maturity_date)[1]
    at = _iso(calendar_response.received_at)
    return {"coverage_verified": False, "window_start": at, "window_end": _iso(window_end), "events": [],
            "source_at": at, "available_at": at,
            "producer_note": {"producer": PRODUCER, "version": PRODUCER_VERSION, "rule": RULE_VERSION,
                              "decision_at": _iso(horizon.decision_at), "maturity_at": _iso(horizon.maturity_at),
                              "exclusion_advice": True, "reasons": [REASON_UNAVAILABLE], "error": error,
                              "calendar_payload_sha256": calendar_response.sha256, "history_payload_sha256": None}}


def produce_earnings(fetch: Fetcher, symbols: Sequence[str], *, session_date: date, output_dir: Path,
                     now: datetime | None = None, live_symbols: Sequence[str] = ()) -> dict[str, Any]:
    clock = now or datetime.now(timezone.utc)
    horizon = horizon_for(session_date)
    calendar_response = fetch("/api/calendar/earnings", {"from": horizon.calendar_from.isoformat(), "to": horizon.calendar_to.isoformat()})
    rows = calendar_rows(calendar_response)
    ordered = list(dict.fromkeys([*symbols, *live_symbols]))
    components: dict[str, dict[str, Any]] = {}
    for symbol in ordered:
        try:
            history_response = fetch(f"/api/fundamentals/{symbol}.US", {"filter": "Earnings::History"})
            components[symbol] = build_component(symbol, horizon, rows, calendar_response, history_entries(history_response),
                                                 history_response, now=clock)
        except ProducerError as error:
            components[symbol] = unavailable_component(horizon, calendar_response, str(error))
    counts = {"symbols": len(ordered), "live_symbols": len(set(live_symbols)),
              "covered": sum(1 for c in components.values() if c["coverage_verified"]),
              "with_events": sum(1 for c in components.values() if c["events"]),
              "exclusion_advice": sum(1 for c in components.values() if c["producer_note"]["exclusion_advice"]),
              **{reason: sum(1 for c in components.values() if reason in c["producer_note"]["reasons"]) for reason in REASONS}}
    document = {"schema": SCHEMA, "session_date": session_date.isoformat(), "rule": RULE_VERSION,
                "amendment": "EMENDA_3_DRAFT_UNDER_PARECER",
                "horizon": {"decision_at": _iso(horizon.decision_at), "maturity_date": horizon.maturity_date.isoformat(),
                            "maturity_at": _iso(horizon.maturity_at),
                            "tolerance_window": [horizon.tolerance_from.isoformat(), horizon.tolerance_to.isoformat()]},
                "calendar": {"from": horizon.calendar_from.isoformat(), "to": horizon.calendar_to.isoformat(),
                             "rows": len(rows), "payload_sha256": calendar_response.sha256, "received_at": _iso(calendar_response.received_at)},
                "granularity_map": {"BeforeMarket": "BMO", "AfterMarket": "AMC", "other": "DAY", "instant": "never from this provider"},
                "produced_at": _iso(clock),
                "live_symbols": sorted(set(live_symbols)),
                "symbols": {symbol: {k: v for k, v in component.items() if k != "producer_note"} for symbol, component in components.items()},
                "notes": {symbol: component["producer_note"] for symbol, component in components.items()},
                "counts": counts}
    digest = write_private(output_dir / "earnings.json", canonical(document))
    return {"session_date": session_date.isoformat(), "counts": counts, "sha256": digest, "output": str(output_dir / "earnings.json")}


def _read_symbols(path: str | None) -> list[str]:
    if not path:
        return []
    return [line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--symbols-file", required=True, help="causal-list symbols, one per line")
    parser.add_argument("--live-symbols-file", help="symbols with live episodes, re-queried daily (EMENDA 3 §3.5)")
    parser.add_argument("--output-dir", required=True, help="components/<D> directory")
    args = parser.parse_args(argv)
    if os.environ.get("C3PO_R2D2_V2_PRODUCERS_ENABLED", "").lower() != "true":
        print('{"status":"OFF","reason":"C3PO_R2D2_V2_PRODUCERS_ENABLED is not true"}')
        return 0
    from .config import get_settings
    settings = get_settings()
    fetch = EodhdFetcher(settings.eodhd_base_url, settings.eodhd_api_token, timeout=settings.market_data_timeout_seconds)
    result = produce_earnings(fetch, _read_symbols(args.symbols_file), session_date=date.fromisoformat(args.session_date),
                              output_dir=Path(args.output_dir), live_symbols=_read_symbols(args.live_symbols_file))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
