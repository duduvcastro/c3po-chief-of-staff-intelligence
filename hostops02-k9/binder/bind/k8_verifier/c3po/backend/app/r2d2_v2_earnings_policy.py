"""Pure validation of the signed E3 rev3 normalized earnings component.

This verifies internal evidence, clocks and the exclusion rule. Payload hashes
are references to independently retained source bytes, not proof of feed
completeness or of a statement omitted by an upstream producer. No I/O occurs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import json
import re
from typing import Any
from zoneinfo import ZoneInfo

AMENDMENT_SHA256 = "3319407afcd7760668e6ec73bb4686ecb95a38eecf47fc157050899f80a6cc9c"
EARNINGS_AMENDMENT_SHA = AMENDMENT_SHA256
SIGNED_MANIFEST_SHA256 = "1a927ca41df89ccb28a276726626672b7d76a9e828f12e4fc5b126860dbb4e72"
RULE = "EXCLUSION_RULE_V1"
NEW_YORK = ZoneInfo("America/New_York")
COMPONENT_KEYS = frozenset({"coverage_verified", "window_start", "window_end", "events", "source_at", "available_at", "policy", "evidence", "exclusion"})
WITHIN = "EARNINGS_WITHIN_HORIZON"
EXPECTED = "EARNINGS_EXPECTED_WITHIN_HORIZON"
NOT_TRACKED = "EARNINGS_NOT_TRACKED"
LAST_UNKNOWN = "EARNINGS_LAST_REPORT_UNKNOWN"
INVALID = "EARNINGS_EVIDENCE_INVALID"
UNAVAILABLE = "EARNINGS_SOURCE_UNAVAILABLE"
_CLOCK = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_COMMON_EVIDENCE = frozenset({"decision_at", "maturity_date", "maturity_at", "tolerance_window", "calendar_window", "calendar_payload_sha256", "history_payload_sha256", "tracked"})
_NORMAL_EVIDENCE = _COMMON_EVIDENCE | {"last_published_report_date", "cadence_days", "cadence_expected_report_date", "cadence_applicable", "cadence_excludes", "known_events", "scheduled_from_history", "history_entries", "invalid_entries"}


class EarningsPolicyError(ValueError):
    """Controlled code only; never include raw evidence or provider errors."""


@dataclass(frozen=True)
class EarningsPolicyResult:
    valid: bool
    excluded: bool
    reasons: tuple[str, ...]
    diagnostics: tuple[str, ...] = ()


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise EarningsPolicyError(code)


def _object(value: object, code: str) -> dict[str, Any]:
    _require(type(value) is dict, code)
    assert isinstance(value, dict)
    _require(all(type(k) is str for k in value), code)
    return value


def _list(value: object, code: str) -> list[Any]:
    _require(type(value) is list, code)
    assert isinstance(value, list)
    return value


def _day(value: object) -> date:
    _require(type(value) is str, "DATE_INVALID")
    assert isinstance(value, str)
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise EarningsPolicyError("DATE_INVALID") from None
    _require(parsed.isoformat() == value, "DATE_INVALID")
    return parsed


def _clock(value: object) -> datetime:
    _require(type(value) is str and _CLOCK.fullmatch(value) is not None, "CLOCK_INVALID")
    assert isinstance(value, str)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise EarningsPolicyError("CLOCK_INVALID") from None
    _require(parsed.utcoffset() is not None, "CLOCK_INVALID")
    return parsed


def _bounds(opened_at: datetime, maturity_at: datetime) -> tuple[date, date]:
    _require(isinstance(opened_at, datetime) and isinstance(maturity_at, datetime), "HORIZON_INVALID")
    _require(opened_at.utcoffset() is not None and maturity_at.utcoffset() is not None, "HORIZON_INVALID")
    _require(opened_at <= maturity_at, "HORIZON_INVALID")
    return opened_at.astimezone(NEW_YORK).date(), maturity_at.astimezone(NEW_YORK).date()


def _classification(event: dict[str, Any], opened_at: datetime, maturity_at: datetime) -> str:
    first, last = _bounds(opened_at, maturity_at)
    day = _day(event.get("event_date"))
    granularity = event.get("granularity")
    _require(type(granularity) is str and granularity in {"DAY", "BMO", "AMC", "INSTANT"}, "GRANULARITY_INVALID")
    _clock(event.get("available_at"))
    instant = None
    if granularity == "INSTANT":
        instant = _clock(event.get("event_at"))
        _require(instant.astimezone(NEW_YORK).date() == day, "INSTANT_DATE_MISMATCH")
    else:
        _require(event.get("event_at") is None, "COARSE_EVENT_HAS_INSTANT")
    if day < first or day > last:
        return "OUTSIDE_HORIZON"
    if instant is not None and instant < opened_at:
        return "PUBLISHED_BEFORE_DECISION"
    if instant is not None and instant > maturity_at:
        return "AFTER_MATURITY"
    return "EXCLUDES"


def event_intersects(event: object, *, opened_at: datetime, maturity_at: datetime) -> bool:
    """Validate an event and intersect its date/instant with an episode.

    DAY/BMO/AMC include both NY boundary dates. Invalid facts raise a controlled
    EarningsPolicyError; they never mean no intersection. Live callers must
    additionally bind available_at to their factual detection time (which can
    follow admission), and normalize non-session dates per the pinned calendar.
    Extra event-envelope metadata is ignored; the component validator below
    independently checks the precise component event schema.
    """
    try:
        return _classification(_object(event, "EVENT_INVALID"), opened_at, maturity_at) == "EXCLUDES"
    except EarningsPolicyError:
        raise
    except (OverflowError, ValueError):
        raise EarningsPolicyError("DATE_RANGE_INVALID") from None


def _pair(value: object) -> tuple[date, date]:
    items = _list(value, "WINDOW_INVALID")
    _require(len(items) == 2, "WINDOW_INVALID")
    first, last = _day(items[0]), _day(items[1])
    _require(first <= last, "WINDOW_INVALID")
    return first, last


def _digest(value: object) -> None:
    _require(type(value) is str and _HASH.fullmatch(value) is not None, "PAYLOAD_HASH_INVALID")


def _projection(event: dict[str, Any]) -> dict[str, Any]:
    result = {key: event[key] for key in ("event_date", "granularity", "available_at")}
    if event["granularity"] == "INSTANT":
        result["event_at"] = event["event_at"]
    return result


def _multiset(events: list[dict[str, Any]]) -> list[str]:
    return sorted(json.dumps(event, sort_keys=True, separators=(",", ":")) for event in events)


def _verdict(component: dict[str, Any], reasons: list[str], covered: bool) -> None:
    verdict = _object(component.get("exclusion"), "VERDICT_INVALID")
    _require(set(verdict) == {"excluded", "reasons"}, "VERDICT_INVALID")
    declared = _list(verdict.get("reasons"), "VERDICT_INVALID")
    _require(all(type(reason) is str for reason in declared), "VERDICT_INVALID")
    _require(len(set(declared)) == len(declared) and set(declared) == set(reasons), "VERDICT_REASONS_MISMATCH")
    _require(type(verdict.get("excluded")) is bool and verdict["excluded"] == bool(reasons), "VERDICT_EXCLUSION_MISMATCH")
    _require(type(component.get("coverage_verified")) is bool and component["coverage_verified"] == covered, "COVERAGE_MISMATCH")


def _validate(component: object, decision_at: datetime, maturity_at: datetime) -> EarningsPolicyResult:
    first, last = _bounds(decision_at, maturity_at)
    value = _object(component, "COMPONENT_INVALID")
    _require(set(value) == COMPONENT_KEYS, "COMPONENT_KEYS_INVALID")
    policy = _object(value.get("policy"), "POLICY_INVALID")
    _require({"rule", "amendment_sha"} <= set(policy) <= {"rule", "amendment_sha", "amendment", "producer", "version"}, "POLICY_INVALID")
    _require(policy.get("rule") == RULE and policy.get("amendment_sha") == AMENDMENT_SHA256, "POLICY_PIN_MISMATCH")
    for key in ("amendment", "producer", "version"):
        if key in policy:
            _require(type(policy[key]) is str and bool(policy[key]), "POLICY_METADATA_INVALID")
    if "amendment" in policy:
        _require("DRAFT" not in policy["amendment"].upper(), "POLICY_DRAFT_REJECTED")
        _require(policy["amendment"] == "EMENDA_3_REV3", "POLICY_METADATA_INVALID")
    source, available = _clock(value.get("source_at")), _clock(value.get("available_at"))
    start, end = _clock(value.get("window_start")), _clock(value.get("window_end"))
    _require(source <= start <= available <= decision_at and maturity_at <= end, "SOURCE_CLOCK_ORDER_INVALID")
    evidence = _object(value.get("evidence"), "EVIDENCE_INVALID")
    _require(_COMMON_EVIDENCE <= set(evidence), "EVIDENCE_KEYS_INVALID")
    nominal = datetime.combine(first, time(10), NEW_YORK)
    _require(_clock(evidence["decision_at"]) == nominal, "EVIDENCE_NOMINAL_DECISION_MISMATCH")
    _require(nominal <= decision_at < nominal + timedelta(minutes=1), "FACTUAL_DECISION_OUTSIDE_CAPTURE")
    _require(_clock(evidence["maturity_at"]) == maturity_at, "EVIDENCE_HORIZON_MISMATCH")
    _require(_day(evidence["maturity_date"]) == last, "MATURITY_DATE_MISMATCH")
    tolerance = (first - timedelta(days=15), last + timedelta(days=15))
    _require(_pair(evidence["tolerance_window"]) == tolerance, "TOLERANCE_MISMATCH")
    query = _pair(evidence["calendar_window"])
    _require(query[0] <= tolerance[0] and query[1] >= tolerance[1], "CALENDAR_WINDOW_INSUFFICIENT")
    _digest(evidence["calendar_payload_sha256"])
    public = _list(value["events"], "EVENTS_INVALID")
    if "error" in evidence:
        _require(set(evidence) == _COMMON_EVIDENCE | {"error"}, "UNAVAILABLE_EVIDENCE_INVALID")
        _require(type(evidence["error"]) is str and bool(evidence["error"]) and evidence["tracked"] is None and evidence["history_payload_sha256"] is None and not public, "UNAVAILABLE_EVIDENCE_INVALID")
        _verdict(value, [UNAVAILABLE], False)
        return EarningsPolicyResult(False, True, (UNAVAILABLE,))
    _require(set(evidence) == _NORMAL_EVIDENCE, "EVIDENCE_KEYS_INVALID")
    _digest(evidence["history_payload_sha256"])
    count, tracked = evidence["history_entries"], evidence["tracked"]
    _require(type(count) is int and count >= 0 and type(tracked) is bool and tracked == (count > 0), "HISTORY_COUNT_INVALID")
    previous = evidence["last_published_report_date"]
    published = None if previous is None else _day(previous)
    _require(published is None or (tracked and published <= first - timedelta(days=1)), "LAST_PUBLISHED_INVALID")
    invalid = _list(evidence["invalid_entries"], "INVALID_ENTRIES_INVALID")
    for item in invalid:
        record = _object(item, "INVALID_ENTRIES_INVALID")
        _require(record.get("source") in ("calendar", "history") and type(record.get("reason")) is str, "INVALID_ENTRIES_INVALID")
    known = _list(evidence["known_events"], "KNOWN_EVENTS_INVALID")
    projections: list[dict[str, Any]] = []
    known_dates: list[date] = []
    history_dates: set[str] = set()
    within = False
    for raw in known:
        event = _object(raw, "KNOWN_EVENT_INVALID")
        required = {"event_date", "granularity", "available_at", "source", "classification"}
        _require(required <= set(event) <= required | {"event_at", "provider_marker"}, "KNOWN_EVENT_KEYS_INVALID")
        _require(event["source"] in ("calendar", "fundamentals_history"), "KNOWN_EVENT_SOURCE_INVALID")
        _require("provider_marker" not in event or event["provider_marker"] is None or type(event["provider_marker"]) is str, "PROVIDER_MARKER_INVALID")
        day = _day(event["event_date"])
        _require(query[0] <= day <= query[1] or event["source"] == "fundamentals_history", "CALENDAR_EVENT_OUTSIDE_QUERY")
        clock = _clock(event["available_at"])
        _require(source <= clock <= available, "EVENT_CLOCK_ORDER_INVALID")
        classification = _classification(event, nominal, maturity_at)
        _require(event["classification"] == classification, "EVENT_CLASSIFICATION_MISMATCH")
        within |= classification == "EXCLUDES"
        known_dates.append(day)
        if event["source"] == "fundamentals_history":
            history_dates.add(day.isoformat())
        if classification != "OUTSIDE_HORIZON":
            projections.append(_projection(event))
    scheduled = _list(evidence["scheduled_from_history"], "HISTORY_SCHEDULE_INVALID")
    scheduled_dates = [_day(day).isoformat() for day in scheduled]
    _require(len(set(scheduled_dates)) == len(scheduled_dates) and set(scheduled_dates) == history_dates, "HISTORY_SCHEDULE_MISMATCH")
    _require(not history_dates or (tracked and len(history_dates) <= count), "HISTORY_SCHEDULE_COUNT_INVALID")
    _require(published is None or len(history_dates - {published.isoformat()}) + 1 <= count, "HISTORY_FACT_COUNT_INVALID")
    supplied: list[dict[str, Any]] = []
    for raw in public:
        event = _object(raw, "EVENT_INVALID")
        keys = {"event_date", "granularity", "available_at"} | ({"event_at"} if event.get("granularity") == "INSTANT" else set())
        _require(set(event) == keys, "PUBLIC_EVENT_KEYS_INVALID")
        _classification(event, nominal, maturity_at)
        supplied.append(event)
    _require(_multiset(supplied) == _multiset(projections), "PUBLIC_EVENTS_MISMATCH")
    _require(type(evidence["cadence_days"]) is int and evidence["cadence_days"] == 91, "CADENCE_DAYS_INVALID")
    expected = None if published is None else published + timedelta(days=91)
    raw_expected = evidence["cadence_expected_report_date"]
    declared_expected = None if raw_expected is None else _day(raw_expected)
    _require(declared_expected == expected, "CADENCE_DATE_MISMATCH")
    applicable = not any(tolerance[0] <= day <= tolerance[1] for day in known_dates)
    cadence_excludes = expected is not None and applicable and tolerance[0] <= expected <= tolerance[1]
    _require(type(evidence["cadence_applicable"]) is bool and evidence["cadence_applicable"] == applicable, "CADENCE_APPLICABILITY_MISMATCH")
    _require(type(evidence["cadence_excludes"]) is bool and evidence["cadence_excludes"] == cadence_excludes, "CADENCE_VERDICT_MISMATCH")
    reasons: list[str] = []
    if not tracked:
        reasons.append(NOT_TRACKED)
    elif published is None:
        reasons.append(LAST_UNKNOWN)
    if invalid:
        reasons.append(INVALID)
    if within:
        reasons.append(WITHIN)
    if cadence_excludes:
        reasons.append(EXPECTED)
    covered = tracked and published is not None and not invalid
    _verdict(value, reasons, covered)
    return EarningsPolicyResult(covered, bool(reasons), tuple(reasons))


def validate_earnings_component(component: object, *, decision_at: datetime, maturity_at: datetime) -> EarningsPolicyResult:
    """Recompute signed E3 facts and verdict, without trusting coverage_verified.

    Invalid evidence always excludes as DATA. A sound, known exclusion has
    valid=True/excluded=True. All reasons are controlled EARNINGS_* codes;
    neither payloads, identifiers nor raw provider errors enter diagnostics.
    """
    try:
        return _validate(component, decision_at, maturity_at)
    except EarningsPolicyError as error:
        return EarningsPolicyResult(False, True, (INVALID,), (str(error),))
    except (OverflowError, ValueError):
        return EarningsPolicyResult(False, True, (INVALID,), ("DATE_RANGE_INVALID",))
