from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from types import MappingProxyType


QUALIFICATION_TICK_DATASETS = frozenset({"trades", "quotes"})
QUALIFICATION_SESSION_DATES = frozenset({
    date(2022, 6, 13),
    date(2024, 8, 5),
    date(2024, 9, 18),
    date(2024, 12, 24),
    date(2025, 3, 21),
    date(2025, 6, 20),
    date(2025, 6, 27),
    date(2025, 9, 19),
    date(2025, 11, 28),
    date(2026, 8, 19),
    date(2026, 8, 20),
    date(2026, 8, 21),
})

QUALIFICATION_CALENDAR_VERSION = "DAY-D-XNYS-QUALIFICATION-CALENDAR-v1"
QUALIFICATION_CALENDAR_PATH = Path(__file__).with_name(
    "qualification_calendar_v1.json"
)


def _load_qualification_calendar() -> dict:
    payload = json.loads(QUALIFICATION_CALENDAR_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != QUALIFICATION_CALENDAR_VERSION:
        raise RuntimeError("qualification calendar schema mismatch")
    sessions = payload.get("sessions")
    if not isinstance(sessions, dict) or set(sessions) != {
        session.isoformat() for session in QUALIFICATION_SESSION_DATES
    }:
        raise RuntimeError("qualification calendar coverage mismatch")
    return payload


QUALIFICATION_CALENDAR = _load_qualification_calendar()
QUALIFICATION_PREVIOUS_SESSION_DATES = MappingProxyType({
    date.fromisoformat(session): date.fromisoformat(row["previous_session_date"])
    for session, row in QUALIFICATION_CALENDAR["sessions"].items()
})
QUALIFICATION_RANKING_SESSION_DATES = MappingProxyType({
    date.fromisoformat(session): tuple(
        date.fromisoformat(value) for value in row["ranking_session_dates"]
    )
    for session, row in QUALIFICATION_CALENDAR["sessions"].items()
})
QUALIFICATION_RANKING_EARLY_CLOSES = MappingProxyType({
    date.fromisoformat(session): value
    for session, value in QUALIFICATION_CALENDAR["early_closes_et"].items()
})


def is_complete_qualification_tick_lot(
    *,
    session_dates: set[date],
    datasets: set[str],
) -> bool:
    return (
        len(session_dates) == 1
        and session_dates <= QUALIFICATION_SESSION_DATES
        and datasets == QUALIFICATION_TICK_DATASETS
    )
