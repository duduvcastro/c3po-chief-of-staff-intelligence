"""Pure E3 observation receipts; provider scheduling and publication are external.

`at` is the source's first local detection, not the scheduled earnings instant.
The collector retains it and stamps its own factual `available_at` on consumption.
Round identity and event-revision identity are distinct and never date-backfilled.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import re
from typing import Mapping, Any
from zoneinfo import ZoneInfo

from .r2d2_v2_earnings_policy import event_intersects, EarningsPolicyError

EARNINGS_AMENDMENT_SHA = "3319407afcd7760668e6ec73bb4686ecb95a38eecf47fc157050899f80a6cc9c"
NY = ZoneInfo("America/New_York")
ROUND_FIELDS = {"earnings_policy_sha", "round_id", "round_session", "round_received_at", "observation_window"}
EARNINGS_FIELDS = ROUND_FIELDS | {"earnings_event_id", "revision_sha256", "event_date", "granularity"}
FAILURE_FIELDS = ROUND_FIELDS | {"reason"}


def _require(ok: bool) -> None:
    if not ok:
        raise EarningsPolicyError("EARNINGS_OBSERVATION_INVALID")


def _time(value: Any) -> datetime:
    try:
        _require(isinstance(value, str))
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        _require(instant.tzinfo is not None and instant.utcoffset() is not None)
        return instant
    except (TypeError, ValueError, OverflowError):
        raise EarningsPolicyError("EARNINGS_OBSERVATION_INVALID") from None


def _day(value: Any) -> date:
    try:
        _require(isinstance(value, str))
        result = date.fromisoformat(value)
        _require(result.isoformat() == value)
        return result
    except (TypeError, ValueError):
        raise EarningsPolicyError("EARNINGS_OBSERVATION_INVALID") from None


def revision_sha256(event: Mapping[str, Any]) -> str:
    """Same known fact in a later round retains its semantic revision identity."""
    facts = {key: event.get(key) for key in ("earnings_event_id", "event_date", "granularity", "event_at")}
    if facts["event_at"] is not None:
        facts["event_at"] = _time(facts["event_at"]).astimezone(timezone.utc).isoformat()
    return hashlib.sha256(json.dumps(facts, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def validate_observation(event: Mapping[str, Any], *, detected_at: datetime) -> None:
    kind = event.get("type")
    _require(kind in {"EARNINGS", "EARNINGS_OBSERVATION_FAILED"})
    _require(event.get("earnings_policy_sha") == EARNINGS_AMENDMENT_SHA)
    _require(isinstance(event.get("round_id"), str) and re.fullmatch(r"[0-9a-f]{64}", event["round_id"]) is not None)
    received, at, available = (_time(event.get(k)) for k in ("round_received_at", "at", "available_at"))
    _require(received <= at <= available <= detected_at)
    # A delayed scheduled round retains its intended session and real receipt.
    # The collector separately verifies this session's official close/calendar.
    target = datetime.combine(_day(event.get("round_session")), time(18), NY)
    _require(received >= target)
    window = event.get("observation_window")
    _require(isinstance(window, list) and len(window) == 2)
    assert isinstance(window, list)
    _require(_day(window[0]) <= _day(window[1]))
    if kind == "EARNINGS_OBSERVATION_FAILED":
        _require(event.get("reason") in {"EARNINGS_SOURCE_UNAVAILABLE", "EARNINGS_EVIDENCE_INVALID"})
        return
    identity = event.get("earnings_event_id")
    _require(isinstance(identity, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}", identity) is not None)
    # Calls the same strict DAY/BMO/AMC/INSTANT parser as the admission gate.
    event_intersects(event, opened_at=at, maturity_at=at + timedelta(days=1))
    _require(("event_at" in event) == (event.get("granularity") == "INSTANT"))
    _require(event.get("revision_sha256") == revision_sha256(event))
    _require(_day(window[0]) <= _day(event.get("event_date")) <= _day(window[1]))


def window_covers(event: Mapping[str, Any], *, opened_at: datetime, maturity_at: datetime) -> bool:
    window = event["observation_window"]
    return (_day(window[0]) <= opened_at.astimezone(NY).date()
            and _day(window[1]) >= maturity_at.astimezone(NY).date() + timedelta(days=15))
