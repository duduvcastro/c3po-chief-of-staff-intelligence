"""R2D2 V2 — earnings producer: conservative exclusion with declared granularity (EMENDA 3 rev 3, draft under parecer).

Produces `components/<D>/earnings.json` for the causal list of session D and, per
EMENDA 3 §3.5, for the live names re-queried in the daily round: one `earnings`
component per symbol in the shape proposed by EMENDA 3 §4 for the V2 file port:

    coverage_verified, window_start, window_end,
    events[{event_date, granularity, available_at, event_at?}],
    source_at, available_at,
    policy  {rule, amendment, amendment_sha, producer, version}      (discriminator)
    evidence{last published report, cadence expectation, tolerance window,
             known events with classification, queried windows, payload hashes,
             validation errors}                                       (facts)
    exclusion{excluded, reasons}                                      (producer verdict)

The contract recomputes the rule from `evidence` and compares it with
`exclusion`; the legacy reader (events with `event_at`, six keys) refuses this
component by schema as a concluded invalid response, never as legacy coverage.

Rule EXCLUSION_RULE_V1 (EMENDA 3 rev 3 §3):

1. three evidences per symbol, validated (schema, types, dates, clocks), bytes
   and receipts preserved: (a) the provider's whole-market earnings calendar for
   [D - 15 d, maturity + 15 d]; (b) the symbol's earnings history with scheduled
   reports; (c) the last PUBLISHED report date (non-null actual EPS, valid report
   date <= D - 1). Missing (c) -> EARNINGS_LAST_REPORT_UNKNOWN; invalid entries ->
   EARNINGS_EVIDENCE_INVALID; no history -> EARNINGS_NOT_TRACKED; query failure ->
   EARNINGS_SOURCE_UNAVAILABLE. `coverage_verified` is true only with the three.
2. exclusion: (i)/(ii) a known event (calendar or scheduled history) whose
   granularity classification intersects [decision 10:00 ET of D, maturity]:
   any DAY/BMO/AMC dated in [D, maturity date] intersects (no entry-day or
   maturity-day exception); INSTANT by instant; (iii) cadence: last published +
   91 d inside [D - 15 d, maturity + 15 d], applied only when no known event
   falls inside that window. Cadence only excludes. Conflicting sources: the
   conservative union.
3. no instant is ever invented: the provider gives DAY/BMO/AMC, never INSTANT.

The producer decides nothing; it reports facts and its own verdict. OFF by
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
PRODUCER_VERSION = "v3"
RULE_VERSION = "EXCLUSION_RULE_V1"
AMENDMENT = "EMENDA_3_REV3_DRAFT_UNDER_PARECER"
AMENDMENT_SHA: str | None = None  # pinned by the release once the three signatures exist
SCHEMA = "V2_EARNINGS_COMPONENTS_V2"
NEW_YORK = ZoneInfo("America/New_York")
HORIZON_SESSIONS = 10
CADENCE_DAYS = 91
CADENCE_TOLERANCE = timedelta(days=15)
DECISION_TIME = time(10, 0)
MATURITY_LEAD = timedelta(minutes=5)
ROUND_TARGET = "18:00 America/New_York after the official close"
GRANULARITIES = ("DAY", "BMO", "AMC", "INSTANT")
PROVIDER_GRANULARITY = {"BeforeMarket": "BMO", "AfterMarket": "AMC"}
COMPONENT_KEYS = frozenset({"coverage_verified", "window_start", "window_end", "events", "source_at", "available_at", "policy", "evidence", "exclusion"})
EXCLUDES = "EXCLUDES"
PUBLISHED_BEFORE_DECISION = "PUBLISHED_BEFORE_DECISION"
AFTER_MATURITY = "AFTER_MATURITY"
OUTSIDE_HORIZON = "OUTSIDE_HORIZON"
REASON_WITHIN = "EARNINGS_WITHIN_HORIZON"
REASON_EXPECTED = "EARNINGS_EXPECTED_WITHIN_HORIZON"
REASON_NOT_TRACKED = "EARNINGS_NOT_TRACKED"
REASON_LAST_UNKNOWN = "EARNINGS_LAST_REPORT_UNKNOWN"
REASON_EVIDENCE_INVALID = "EARNINGS_EVIDENCE_INVALID"
REASON_UNAVAILABLE = "EARNINGS_SOURCE_UNAVAILABLE"
REASONS = (REASON_WITHIN, REASON_EXPECTED, REASON_NOT_TRACKED, REASON_LAST_UNKNOWN, REASON_EVIDENCE_INVALID, REASON_UNAVAILABLE)


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


def horizon_for(session_date: date, *, live_lookback: tuple[date, date] | None = None) -> Horizon:
    """Decision at 10:00 ET of D; maturity = official close of the 10th session minus five minutes.

    The calendar query covers the whole tolerance window [D-15 d, maturity+15 d] and, in the daily
    round, also the live episodes' lookback [earliest live admission, latest live maturity + 15 d].
    """
    sessions = horizon_sessions(session_date)
    _, last_close = session_bounds(sessions[-1])
    decision_at = datetime.combine(session_date, DECISION_TIME, NEW_YORK).astimezone(timezone.utc)
    maturity_date = sessions[-1]
    calendar_from, calendar_to = session_date - CADENCE_TOLERANCE, maturity_date + CADENCE_TOLERANCE
    if live_lookback is not None:
        earliest, latest = live_lookback
        if earliest > latest:
            raise ProducerError("LIVE_LOOKBACK_INVALID")
        calendar_from, calendar_to = min(calendar_from, earliest), max(calendar_to, latest + CADENCE_TOLERANCE)
    return Horizon(session_date, decision_at, maturity_date, last_close - MATURITY_LEAD, calendar_from=calendar_from, calendar_to=calendar_to)


def granularity_of(before_after_market: Any) -> str:
    """Provider marker -> declared granularity. Anything unknown is the whole DAY (conservative)."""
    if isinstance(before_after_market, str):
        return PROVIDER_GRANULARITY.get(before_after_market, "DAY")
    return "DAY"


def classify_event(event_date: date, granularity: str, horizon: Horizon, event_at: datetime | None = None) -> str:
    """EMENDA 3 rev 3 §3.4: any DAY/BMO/AMC dated inside [D, maturity date] intersects the horizon; INSTANT by instant."""
    if granularity not in GRANULARITIES:
        raise ProducerError("GRANULARITY_INVALID")
    if not horizon.session_date <= event_date <= horizon.maturity_date:
        return OUTSIDE_HORIZON
    if granularity == "INSTANT":
        if event_at is None or event_at.tzinfo is None:
            raise ProducerError("INSTANT_WITHOUT_EVENT_AT")
        if event_at < horizon.decision_at:
            return PUBLISHED_BEFORE_DECISION
        if event_at > horizon.maturity_at:
            return AFTER_MATURITY
    return EXCLUDES


def cadence_expected(last_published: date | None) -> date | None:
    return None if last_published is None else last_published + timedelta(days=CADENCE_DAYS)


def _date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value[:10])
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value[:10] else None


def _actual(value: Any) -> float | None:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        return None
    return float(value)


def calendar_rows(response: Response) -> list[dict[str, Any]]:
    payload = response.json()
    rows = payload.get("earnings") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not rows:
        raise ProducerError("CALENDAR_EMPTY_OR_INVALID")
    return [row for row in rows if isinstance(row, dict)]


def history_entries(response: Response) -> dict[str, Any]:
    """Every entry of the provider's history, unfiltered: validation happens in `build_component` and is recorded."""
    payload = response.json()
    return dict(payload) if isinstance(payload, dict) else {}


def _port_event(item: Mapping[str, Any]) -> dict[str, Any]:
    event = {"event_date": item["event_date"], "granularity": item["granularity"], "available_at": item["available_at"]}
    if item["granularity"] == "INSTANT":
        event["event_at"] = item["event_at"]
    return event


def build_component(symbol: str, horizon: Horizon, calendar: Sequence[Mapping[str, Any]], calendar_response: Response,
                    history: Mapping[str, Any], history_response: Response, *, now: datetime) -> dict[str, Any]:
    code = f"{symbol}.US"
    invalid: list[dict[str, Any]] = []
    known: dict[date, dict[str, Any]] = {}
    for index, row in enumerate(calendar):
        if row.get("code") != code:
            continue
        report = _date(row.get("report_date"))
        if report is None:
            invalid.append({"source": "calendar", "index": index, "reason": "REPORT_DATE_UNREADABLE"})
            continue
        granularity = granularity_of(row.get("before_after_market"))
        known.setdefault(report, {"event_date": report.isoformat(), "granularity": granularity, "event_at": None,
                                  "available_at": _iso(calendar_response.received_at), "provider_marker": row.get("before_after_market"),
                                  "source": "calendar", "classification": classify_event(report, granularity, horizon)})
        if known[report]["granularity"] != granularity:  # conflicting sources: the conservative union keeps the whole DAY
            known[report].update(granularity="DAY", classification=classify_event(report, "DAY", horizon), provider_marker="CONFLICT")
    last_published: date | None = None
    scheduled_in_history: list[str] = []
    tracked = bool(history)
    for key, entry in history.items():
        if not isinstance(entry, dict):
            invalid.append({"source": "history", "key": str(key), "reason": "ENTRY_NOT_OBJECT"})
            continue
        report = _date(entry.get("reportDate"))
        if report is None:
            invalid.append({"source": "history", "key": str(key), "reason": "REPORT_DATE_UNREADABLE"})
            continue
        raw_actual = entry.get("epsActual")
        actual = _actual(raw_actual)
        if raw_actual is not None and actual is None:
            invalid.append({"source": "history", "key": str(key), "reason": "EPS_ACTUAL_NOT_A_NUMBER"})
            continue
        if actual is not None and report <= horizon.session_date - timedelta(days=1):
            last_published = report if last_published is None or report > last_published else last_published
        if actual is None and report >= horizon.session_date:
            granularity = granularity_of(entry.get("beforeAfterMarket"))
            if report not in known:
                known[report] = {"event_date": report.isoformat(), "granularity": granularity, "event_at": None,
                                 "available_at": _iso(history_response.received_at), "provider_marker": entry.get("beforeAfterMarket"),
                                 "source": "fundamentals_history", "classification": classify_event(report, granularity, horizon)}
                scheduled_in_history.append(report.isoformat())
            elif known[report]["granularity"] != granularity:
                known[report].update(granularity="DAY", classification=classify_event(report, "DAY", horizon), provider_marker="CONFLICT")
    ordered = [known[key] for key in sorted(known)]
    in_horizon = [item for item in ordered if item["classification"] != OUTSIDE_HORIZON]
    known_in_tolerance = any(horizon.tolerance_from <= key <= horizon.tolerance_to for key in known)
    expected = cadence_expected(last_published)
    cadence_applicable = not known_in_tolerance
    cadence_excludes = expected is not None and cadence_applicable and horizon.tolerance_from <= expected <= horizon.tolerance_to
    reasons: list[str] = []
    if not tracked:
        reasons.append(REASON_NOT_TRACKED)
    elif last_published is None:
        reasons.append(REASON_LAST_UNKNOWN)
    if invalid:
        reasons.append(REASON_EVIDENCE_INVALID)
    if any(item["classification"] == EXCLUDES for item in in_horizon):
        reasons.append(REASON_WITHIN)
    if cadence_excludes:
        reasons.append(REASON_EXPECTED)
    covered = tracked and last_published is not None and not invalid
    window_end = session_bounds(horizon.maturity_date)[1]
    return {
        "coverage_verified": covered,
        "window_start": _iso(calendar_response.received_at), "window_end": _iso(window_end),
        "events": [_port_event(item) for item in in_horizon],
        "source_at": _iso(min(calendar_response.received_at, history_response.received_at)),
        "available_at": _iso(max(calendar_response.received_at, history_response.received_at)),
        "policy": {"rule": RULE_VERSION, "amendment": AMENDMENT, "amendment_sha": AMENDMENT_SHA, "producer": PRODUCER, "version": PRODUCER_VERSION},
        "evidence": {"decision_at": _iso(horizon.decision_at), "maturity_date": horizon.maturity_date.isoformat(), "maturity_at": _iso(horizon.maturity_at),
                     "tolerance_window": [horizon.tolerance_from.isoformat(), horizon.tolerance_to.isoformat()],
                     "calendar_window": [horizon.calendar_from.isoformat(), horizon.calendar_to.isoformat()],
                     "last_published_report_date": last_published.isoformat() if last_published else None,
                     "cadence_days": CADENCE_DAYS, "cadence_expected_report_date": expected.isoformat() if expected else None,
                     "cadence_applicable": cadence_applicable, "cadence_excludes": cadence_excludes,
                     "known_events": ordered, "scheduled_from_history": scheduled_in_history, "history_entries": len(history),
                     "invalid_entries": invalid, "tracked": tracked,
                     "calendar_payload_sha256": calendar_response.sha256, "history_payload_sha256": history_response.sha256},
        "exclusion": {"excluded": bool(reasons), "reasons": reasons},
    }


def unavailable_component(horizon: Horizon, calendar_response: Response, error: str) -> dict[str, Any]:
    window_end = session_bounds(horizon.maturity_date)[1]
    at = _iso(calendar_response.received_at)
    return {"coverage_verified": False, "window_start": at, "window_end": _iso(window_end), "events": [], "source_at": at, "available_at": at,
            "policy": {"rule": RULE_VERSION, "amendment": AMENDMENT, "amendment_sha": AMENDMENT_SHA, "producer": PRODUCER, "version": PRODUCER_VERSION},
            "evidence": {"decision_at": _iso(horizon.decision_at), "maturity_date": horizon.maturity_date.isoformat(), "maturity_at": _iso(horizon.maturity_at),
                         "tolerance_window": [horizon.tolerance_from.isoformat(), horizon.tolerance_to.isoformat()],
                         "calendar_window": [horizon.calendar_from.isoformat(), horizon.calendar_to.isoformat()],
                         "error": error, "calendar_payload_sha256": calendar_response.sha256, "history_payload_sha256": None, "tracked": None},
            "exclusion": {"excluded": True, "reasons": [REASON_UNAVAILABLE]}}


def produce_earnings(fetch: Fetcher, symbols: Sequence[str], *, session_date: date, output_dir: Path, now: datetime | None = None,
                     live_symbols: Sequence[str] = (), live_lookback: tuple[date, date] | None = None) -> dict[str, Any]:
    clock = now or datetime.now(timezone.utc)
    horizon = horizon_for(session_date, live_lookback=live_lookback)
    calendar_response = fetch("/api/calendar/earnings", {"from": horizon.calendar_from.isoformat(), "to": horizon.calendar_to.isoformat()})
    rows = calendar_rows(calendar_response)
    ordered = list(dict.fromkeys([*symbols, *live_symbols]))
    components: dict[str, dict[str, Any]] = {}
    for symbol in ordered:
        try:
            history_response = fetch(f"/api/fundamentals/{symbol}.US", {"filter": "Earnings::History"})
            components[symbol] = build_component(symbol, horizon, rows, calendar_response, history_entries(history_response), history_response, now=clock)
        except ProducerError as error:
            components[symbol] = unavailable_component(horizon, calendar_response, str(error))
        assert set(components[symbol]) == COMPONENT_KEYS
    counts = {"symbols": len(ordered), "live_symbols": len(set(live_symbols)),
              "covered": sum(1 for c in components.values() if c["coverage_verified"]),
              "with_events": sum(1 for c in components.values() if c["events"]),
              "excluded": sum(1 for c in components.values() if c["exclusion"]["excluded"]),
              **{reason: sum(1 for c in components.values() if reason in c["exclusion"]["reasons"]) for reason in REASONS}}
    document = {"schema": SCHEMA, "session_date": session_date.isoformat(), "rule": RULE_VERSION, "amendment": AMENDMENT, "amendment_sha": AMENDMENT_SHA,
                "round": {"target": ROUND_TARGET, "executed_at": _iso(clock), "calendar_window": [horizon.calendar_from.isoformat(), horizon.calendar_to.isoformat()],
                          "live_lookback": [live_lookback[0].isoformat(), live_lookback[1].isoformat()] if live_lookback else None},
                "horizon": {"decision_at": _iso(horizon.decision_at), "maturity_date": horizon.maturity_date.isoformat(), "maturity_at": _iso(horizon.maturity_at),
                            "tolerance_window": [horizon.tolerance_from.isoformat(), horizon.tolerance_to.isoformat()]},
                "calendar": {"from": horizon.calendar_from.isoformat(), "to": horizon.calendar_to.isoformat(),
                             "rows": len(rows), "payload_sha256": calendar_response.sha256, "received_at": _iso(calendar_response.received_at)},
                "granularity_map": {"BeforeMarket": "BMO", "AfterMarket": "AMC", "other": "DAY", "instant": "never from this provider"},
                "live_symbols": sorted(set(live_symbols)),
                "symbols": components,
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
    parser.add_argument("--live-symbols-file", help="symbols with live episodes, re-queried in the daily round (EMENDA 3 §3.5)")
    parser.add_argument("--live-lookback", nargs=2, metavar=("FROM", "TO"), help="earliest live admission date and latest live maturity date (ISO)")
    parser.add_argument("--output-dir", required=True, help="components/<D> directory")
    args = parser.parse_args(argv)
    if os.environ.get("C3PO_R2D2_V2_PRODUCERS_ENABLED", "").lower() != "true":
        print('{"status":"OFF","reason":"C3PO_R2D2_V2_PRODUCERS_ENABLED is not true"}')
        return 0
    from .config import get_settings
    settings = get_settings()
    fetch = EodhdFetcher(settings.eodhd_base_url, settings.eodhd_api_token, timeout=settings.market_data_timeout_seconds)
    lookback = (date.fromisoformat(args.live_lookback[0]), date.fromisoformat(args.live_lookback[1])) if args.live_lookback else None
    result = produce_earnings(fetch, _read_symbols(args.symbols_file), session_date=date.fromisoformat(args.session_date),
                              output_dir=Path(args.output_dir), live_symbols=_read_symbols(args.live_symbols_file), live_lookback=lookback)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
