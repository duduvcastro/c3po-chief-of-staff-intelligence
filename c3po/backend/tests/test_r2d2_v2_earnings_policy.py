"""Synthetic normalized evidence only: no source fetch or producer execution."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime, time, timedelta, timezone
import json
from zoneinfo import ZoneInfo

import pytest

from app.r2d2_v2_earnings_policy import (
    AMENDMENT_SHA256, EXPECTED, INVALID, LAST_UNKNOWN, NOT_TRACKED, RULE,
    UNAVAILABLE, WITHIN, EarningsPolicyError, event_intersects,
    validate_earnings_component,
)

NY = ZoneInfo("America/New_York")
DECISION = datetime(2026, 9, 8, 10, tzinfo=NY)
MATURITY = datetime(2026, 9, 21, 15, 55, tzinfo=NY)


def component(*, decision_at=DECISION, maturity_at=MATURITY, available_at=None):
    """Reusable valid synthetic fixture; hashes stand for synthetic source bytes."""
    available_at = decision_at - timedelta(minutes=2) if available_at is None else available_at
    first, last = decision_at.astimezone(NY).date(), maturity_at.astimezone(NY).date()
    published = first - timedelta(days=200)
    tolerance = [(first - timedelta(days=15)).isoformat(), (last + timedelta(days=15)).isoformat()]
    return {
        "coverage_verified": True, "window_start": available_at.isoformat(),
        "window_end": (maturity_at + timedelta(minutes=5)).isoformat(), "events": [],
        "source_at": available_at.isoformat(), "available_at": available_at.isoformat(),
        "policy": {"rule": RULE, "amendment_sha": AMENDMENT_SHA256,
                   "amendment": "EMENDA_3_REV3", "producer": "synthetic", "version": "test"},
        "evidence": {
            "decision_at": datetime.combine(first, time(10), NY).isoformat(), "maturity_date": last.isoformat(),
            "maturity_at": maturity_at.isoformat(), "tolerance_window": tolerance,
            "calendar_window": tolerance[:], "last_published_report_date": published.isoformat(),
            "cadence_days": 91, "cadence_expected_report_date": (published + timedelta(days=91)).isoformat(),
            "cadence_applicable": True, "cadence_excludes": False, "known_events": [],
            "scheduled_from_history": [], "history_entries": 1, "invalid_entries": [],
            "tracked": True, "calendar_payload_sha256": "a" * 64,
            "history_payload_sha256": "b" * 64,
        },
        "exclusion": {"excluded": False, "reasons": []},
    }


def event(day, granularity="DAY", *, instant=None, source="calendar", classification="EXCLUDES"):
    return {"event_date": day, "granularity": granularity, "event_at": instant,
            "available_at": (DECISION - timedelta(minutes=2)).isoformat(),
            "source": source, "provider_marker": None, "classification": classification}


def put_events(value, *events, within=True, applicable=False):
    value["evidence"]["known_events"] = list(events)
    value["evidence"]["scheduled_from_history"] = sorted({e["event_date"] for e in events if e["source"] == "fundamentals_history"})
    value["evidence"]["cadence_applicable"] = applicable
    value["events"] = [
        {k: e[k] for k in ("event_date", "granularity", "available_at") + (("event_at",) if e["granularity"] == "INSTANT" else ())}
        for e in events if e["classification"] != "OUTSIDE_HORIZON"
    ]
    value["exclusion"] = {"excluded": within, "reasons": [WITHIN] if within else []}
    return value


def check(value, **kwargs):
    return validate_earnings_component(value, decision_at=kwargs.get("decision_at", DECISION), maturity_at=kwargs.get("maturity_at", MATURITY))


def test_valid_empty_calendar_is_three_facts_not_negative_feed_coverage():
    value = component()
    before = deepcopy(value)
    result = check(value)
    assert result.valid and not result.excluded and result.reasons == ()
    assert value == before
    with pytest.raises(FrozenInstanceError):
        result.valid = False


@pytest.mark.parametrize("granularity", ["DAY", "BMO", "AMC"])
@pytest.mark.parametrize("day", ["2026-09-08", "2026-09-21"])
def test_coarse_both_boundary_days_always_exclude(granularity, day):
    result = check(put_events(component(), event(day, granularity)))
    assert result.valid and result.excluded and result.reasons == (WITHIN,)


@pytest.mark.parametrize(("instant", "classification", "expected"), [
    ("2026-09-08T13:59:59+00:00", "PUBLISHED_BEFORE_DECISION", False),
    ("2026-09-08T14:00:00+00:00", "EXCLUDES", True),
    ("2026-09-21T19:55:00+00:00", "EXCLUDES", True),
    ("2026-09-21T19:55:01+00:00", "AFTER_MATURITY", False),
])
def test_precise_instants_use_inclusive_actual_clocks(instant, classification, expected):
    item = event(datetime.fromisoformat(instant).astimezone(NY).date().isoformat(), "INSTANT", instant=instant, classification=classification)
    result = check(put_events(component(), item, within=expected))
    assert result.valid and result.excluded is expected


def test_conflicting_events_use_union_and_public_projection_preserves_both():
    value = put_events(component(), event("2026-09-08", "INSTANT", instant="2026-09-08T13:59:00Z", classification="PUBLISHED_BEFORE_DECISION"), event("2026-09-08", "DAY", source="fundamentals_history"))
    value["evidence"]["history_entries"] = 2
    assert check(value).reasons == (WITHIN,)
    value["events"].pop()
    assert check(value).diagnostics == ("PUBLIC_EVENTS_MISMATCH",)


def test_multiplicity_not_erased_when_comparing_events():
    item = event("2026-09-08")
    value = put_events(component(), item, deepcopy(item))
    assert check(value).valid
    value["events"].pop()
    assert not check(value).valid


def test_cadence_only_when_no_known_event_in_tolerance():
    value = component()
    ev = value["evidence"]
    ev.update(last_published_report_date="2026-06-09", cadence_expected_report_date="2026-09-08", cadence_excludes=True)
    value["exclusion"] = {"excluded": True, "reasons": [EXPECTED]}
    assert check(value).reasons == (EXPECTED,)
    put_events(value, event("2026-09-07", classification="OUTSIDE_HORIZON"), within=False)
    ev["cadence_excludes"] = False
    assert check(value).valid and not check(value).excluded


@pytest.mark.parametrize("day", ["2026-08-24", "2026-10-06"])
def test_tolerance_includes_its_boundaries(day):
    value = component()
    value["evidence"]["last_published_report_date"] = (datetime.fromisoformat(day).date() - timedelta(days=91)).isoformat()
    value["evidence"]["cadence_expected_report_date"] = day
    value["evidence"]["cadence_excludes"] = True
    value["exclusion"] = {"excluded": True, "reasons": [EXPECTED]}
    assert check(value).reasons == (EXPECTED,)


@pytest.mark.parametrize(("path", "bad"), [
    (("policy", "amendment_sha"), None),
    (("policy", "amendment_sha"), "0" * 64),
    (("policy", "rule"), "EXCLUSION_RULE_V0"),
    (("policy", "amendment"), "EMENDA_3_REV3_DRAFT_UNDER_PARECER"),
    (("policy", "amendment"), "EMENDA_3_REV2"),
    (("evidence", "history_payload_sha256"), None),
    (("evidence", "calendar_payload_sha256"), "a" * 63),
    (("evidence", "last_published_report_date"), "2026-09-08"),
    (("evidence", "last_published_report_date"), "2026-02-30"),
    (("evidence", "last_published_report_date"), "2026-02-01T00:00:00Z"),
    (("evidence", "history_entries"), True),
    (("evidence", "history_entries"), 1.0),
    (("evidence", "history_entries"), -1),
    (("evidence", "tracked"), 1),
    (("evidence", "cadence_days"), 90),
    (("evidence", "cadence_days"), 91.0),
    (("evidence", "cadence_applicable"), False),
    (("evidence", "cadence_excludes"), True),
    (("evidence", "cadence_expected_report_date"), "2026-09-08"),
    (("evidence", "calendar_window"), ["2026-08-25", "2026-10-06"]),
    (("evidence", "tolerance_window"), ["2026-08-23", "2026-10-06"]),
    (("evidence", "decision_at"), "2026-09-08T10:00:37-04:00"),
    (("exclusion", "excluded"), True),
    (("exclusion", "reasons"), [WITHIN]),
    (("coverage_verified",), 1),
    (("coverage_verified",), False),
    (("available_at",), "2026-09-08T10:00:01-04:00"),
    (("source_at",), "2026-09-08T10:00:00"),
])
def test_malformed_or_forged_facts_never_become_eligible(path, bad):
    value = component()
    target = value
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = bad
    result = check(value)
    assert not result.valid and result.excluded and result.reasons == (INVALID,)


@pytest.mark.parametrize("missing", ["history_payload_sha256", "last_published_report_date", "tracked", "invalid_entries", "known_events"])
def test_missing_normalized_evidence_fails_closed(missing):
    value = component()
    del value["evidence"][missing]
    assert check(value).reasons == (INVALID,)


@pytest.mark.parametrize("bad", [None, {}, [], True, {"coverage_verified": True, "events": []}])
def test_legacy_and_nonobjects_rejected(bad):
    assert check(bad).reasons == (INVALID,)


@pytest.mark.parametrize(("tracked", "count", "reason"), [(False, 0, NOT_TRACKED), (True, 1, LAST_UNKNOWN)])
def test_known_data_reasons_preserved(tracked, count, reason):
    value = component()
    value["evidence"].update(tracked=tracked, history_entries=count, last_published_report_date=None, cadence_expected_report_date=None)
    value["coverage_verified"] = False
    value["exclusion"] = {"excluded": True, "reasons": [reason]}
    result = check(value)
    assert not result.valid and result.excluded and result.reasons == (reason,)


def test_invalid_entries_block_and_do_not_export_private_fields():
    value = component()
    value["evidence"]["invalid_entries"] = [{"source": "history", "key": "PRIVATE", "reason": "PRIVATE_PROVIDER_DETAIL"}]
    value["coverage_verified"] = False
    value["exclusion"] = {"excluded": True, "reasons": [INVALID]}
    result = check(value)
    assert result.reasons == (INVALID,)
    assert "PRIVATE" not in repr(result)


def test_unavailable_branch_preserves_reason_and_redacts_raw_error():
    value = component()
    ev = value["evidence"]
    keys = {"decision_at", "maturity_date", "maturity_at", "tolerance_window", "calendar_window", "calendar_payload_sha256", "history_payload_sha256", "tracked"}
    value["evidence"] = {k: ev[k] for k in keys}
    value["evidence"].update(error="PRIVATE_TOKEN=do-not-emit", history_payload_sha256=None, tracked=None)
    value["coverage_verified"] = False
    value["exclusion"] = {"excluded": True, "reasons": [UNAVAILABLE]}
    result = check(value)
    assert not result.valid and result.excluded and result.reasons == (UNAVAILABLE,)
    assert "PRIVATE" not in repr(result)
    value["exclusion"]["excluded"] = False
    assert check(value).reasons == (INVALID,)


@pytest.mark.parametrize(("field", "bad"), [
    ("classification", "OUTSIDE_HORIZON"),
    ("available_at", "2026-09-08T10:00:01-04:00"),
    ("granularity", "BMO_CONFIRMED"),
    ("event_date", "2026-09-08extra"),
    ("event_at", "2026-09-08T13:00:00Z"),
])
def test_known_event_corruption(field, bad):
    value = put_events(component(), event("2026-09-08"))
    value["evidence"]["known_events"][0][field] = bad
    assert check(value).reasons == (INVALID,)


def test_live_event_available_after_admission_needs_detection_check_not_opening_check():
    item = event("2026-09-10")
    item["available_at"] = "2026-09-10T22:00:00Z"
    assert event_intersects(item, opened_at=DECISION, maturity_at=MATURITY)


def test_live_invalid_is_not_false_and_instant_date_is_new_york():
    item = event("2026-09-09", "INSTANT", instant="2026-09-09T01:00:00Z")
    with pytest.raises(EarningsPolicyError, match="INSTANT_DATE_MISMATCH"):
        event_intersects(item, opened_at=DECISION, maturity_at=MATURITY)
    item["event_date"] = "2026-09-08"
    assert event_intersects(item, opened_at=DECISION, maturity_at=MATURITY)


def test_exact_decision_seconds_and_timezone_equivalence():
    later = DECISION + timedelta(seconds=37)
    value = component(decision_at=later)
    assert check(value, decision_at=later.astimezone(timezone.utc)).valid
    assert check(value).valid
    value["evidence"]["decision_at"] = later.isoformat()
    assert check(value, decision_at=later).diagnostics == ("EVIDENCE_NOMINAL_DECISION_MISMATCH",)


def test_admission_uses_signed_nominal_boundary_and_live_episode_uses_real_opening():
    item = event("2026-09-08", "INSTANT", instant="2026-09-08T10:00:20-04:00")
    value = put_events(component(), item)
    assert check(value).reasons == (WITHIN,)
    result = check(value, decision_at=DECISION + timedelta(seconds=37))
    assert result.valid and result.excluded and result.reasons == (WITHIN,)
    assert not event_intersects(item, opened_at=DECISION + timedelta(seconds=37), maturity_at=MATURITY)
    value["evidence"]["known_events"][0]["classification"] = "PUBLISHED_BEFORE_DECISION"
    value["exclusion"] = {"excluded": False, "reasons": []}
    assert check(value, decision_at=DECISION + timedelta(seconds=37)).diagnostics == ("EVENT_CLASSIFICATION_MISMATCH",)


@pytest.mark.parametrize(("offset", "valid"), [(0, True), (59.999999, True), (60, False), (-0.000001, False)])
def test_factual_capture_is_half_open_without_requiring_producer_future_clock(offset, valid):
    result = check(component(), decision_at=DECISION + timedelta(seconds=offset))
    assert result.valid is valid


def test_invalid_horizons_fail_closed():
    assert not check(component(), maturity_at=DECISION - timedelta(seconds=1)).valid
    assert not check(component(), decision_at=DECISION.replace(tzinfo=None)).valid


def test_reason_tuple_contains_only_controlled_public_fields():
    value = component()
    value["evidence"]["tracked"] = "PRIVATE_SYMBOL"
    result = check(value)
    assert "PRIVATE" not in json.dumps(result.__dict__)


def test_history_cannot_claim_two_distinct_records_from_one_entry():
    value = put_events(component(), event("2026-09-10", source="fundamentals_history"))
    assert check(value).diagnostics == ("HISTORY_FACT_COUNT_INVALID",)
    value["evidence"]["history_entries"] = 2
    assert check(value).valid


def test_live_invalid_range_remains_controlled():
    with pytest.raises(EarningsPolicyError, match="DATE_RANGE_INVALID"):
        event_intersects(event("2026-09-08"), opened_at=datetime.min.replace(tzinfo=timezone.utc), maturity_at=MATURITY)
