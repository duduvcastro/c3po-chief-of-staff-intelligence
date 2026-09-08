"""Synthetic E3 receipts for pure-ledger regressions; no provider observations."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.r2d2_v2_earnings_events import EARNINGS_AMENDMENT_SHA, revision_sha256
from app.r2d2_v2_calendar import ShadowCalendar
from app.r2d2_v2_earnings_package import (EARNINGS_CLOSED_MANIFEST_SHA, implementation_contract_sha,
                                        implementation_package_sha)


def package_pins():
    return dict(earnings_amendment_sha=EARNINGS_AMENDMENT_SHA,
        earnings_closed_manifest_sha=EARNINGS_CLOSED_MANIFEST_SHA,
        implementation_contract_sha=implementation_contract_sha(),
        implementation_package_sha=implementation_package_sha())


def observation(event, *, day=None, granularity="INSTANT", instant=None):
    result = dict(event)
    instant = result.pop("earnings_at", instant)
    if day is None and instant is not None:
        day = datetime.fromisoformat(instant.replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York")).date().isoformat()
    ny = ZoneInfo("America/New_York")
    at = datetime.fromisoformat(result["at"].replace("Z", "+00:00"))
    round_day = at.astimezone(ny).date() - timedelta(days=1)
    calendar = ShadowCalendar()
    while not calendar.is_session(round_day):
        round_day -= timedelta(days=1)
    result.update(earnings_policy_sha=EARNINGS_AMENDMENT_SHA,
        round_id="a" * 64, round_session=round_day.isoformat(),
        round_received_at=datetime.combine(round_day, time(18), ny).isoformat(),
        observation_window=["2020-01-01", "2040-01-01"])
    if result["type"] == "EARNINGS":
        result.update(earnings_event_id="synthetic-announcement", event_date=day,
                      granularity=granularity)
        if granularity == "INSTANT":
            result["event_at"] = instant
        result["revision_sha256"] = revision_sha256(result)
    else:
        result["reason"] = "EARNINGS_SOURCE_UNAVAILABLE"
    return result
