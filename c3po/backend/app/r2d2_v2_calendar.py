"""Official XNYS sessions (also US Nasdaq regular calendar), never weekdays."""
from __future__ import annotations

from datetime import date, datetime, time
from functools import lru_cache
from zoneinfo import ZoneInfo

from .r2d2_v2_store import digest, utc

NEW_YORK = ZoneInfo("America/New_York")


class ShadowCalendar:
    def __init__(self):
        import exchange_calendars
        self.calendar = exchange_calendars.get_calendar("XNYS")
        self.version = exchange_calendars.__version__

    def is_session(self, day: date) -> bool:
        return bool(self.calendar.is_session(day.isoformat()))

    @lru_cache(maxsize=160)
    def details(self, day: date) -> dict:
        cal = self.calendar
        session = cal.date_to_session(day.isoformat(), direction="none")
        previous = cal.previous_session(session)
        prior = tuple(t.date() for t in cal.sessions_window(previous, -61))
        horizon = tuple(t.date() for t in cal.sessions_window(session, 10))
        result = {"session": day, "previous_sessions": prior, "horizon_sessions": horizon,
                  "open": utc(cal.session_open(session).to_pydatetime()),
                  "close": utc(cal.session_close(session).to_pydatetime()),
                  "horizon_close": utc(cal.session_close(horizon[-1].isoformat()).to_pydatetime()),
                  "capture_open": utc(datetime.combine(day, time(10), NEW_YORK)),
                  "capture_close": utc(datetime.combine(day, time(10, 1), NEW_YORK))}
        result["sha256"] = digest({k: [v.isoformat() for v in value] if isinstance(value, tuple)
                                   else value.isoformat() for k, value in result.items()})
        return result

    def sessions(self, first: date, count: int) -> tuple[date, ...]:
        session = self.calendar.date_to_session(first.isoformat(), direction="none")
        return tuple(t.date() for t in self.calendar.sessions_window(session, count))

    def regular(self, at: datetime, *, end: datetime | None = None) -> bool:
        at = utc(at)
        day = at.astimezone(NEW_YORK).date()
        if not self.is_session(day):
            return False
        detail = self.details(day)
        return detail["open"] <= at <= (utc(end) if end else at) <= detail["close"]
