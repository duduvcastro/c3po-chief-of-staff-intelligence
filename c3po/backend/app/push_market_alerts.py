from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

from .config import Settings
from .database import Database
from .push_notifications import PushNotificationService
from .r2d2 import R2D2Repository


logger = logging.getLogger("c3po.push_market_alerts")

NEW_YORK = ZoneInfo("America/New_York")
SAO_PAULO = ZoneInfo("America/Sao_Paulo")
SELL_WIN_CLOSE_GRACE = timedelta(minutes=30)


class PushMarketAlertsService:
    """Read-only observer for the sell_win and hourly_win_rate push categories.

    Amendment 1 of C3PO_MOBILE_PUSH_V2, corrected per the Codex audit of
    PR #297: every number comes from the SAME walk the Falcon panel uses -
    R2D2Repository.episode_summary / _episode_summary_from_trades - so flats,
    corrections and wind-downs are treated identically by construction. The
    R2D2 trading worker is never imported. Delivery idempotency lives in the
    push layer's event_key, so restarts never duplicate a notification.
    """

    def __init__(
        self,
        settings: Settings,
        database: Database,
        push_notifications: PushNotificationService,
    ) -> None:
        self.settings = settings
        self.database = database
        self.push_notifications = push_notifications
        self._calendar = xcals.get_calendar("XNYS")
        self._experiment_id: str | None = None
        # A process born mid-hour owns no hour boundary: seed the guard with
        # the current slot so the first hourly push only fires at the NEXT
        # full hour (Codex audit, finding 3).
        self._last_hourly_key = self._hourly_key(datetime.now(timezone.utc))

    @staticmethod
    def _hourly_key(now: datetime) -> str:
        local = now.astimezone(SAO_PAULO)
        return f"{local.date().isoformat()}:{local.hour:02d}"

    def _session_window(self, now: datetime) -> tuple[datetime, datetime] | None:
        session = now.astimezone(NEW_YORK).date()
        if not self._calendar.is_session(session):
            return None
        return (
            self._calendar.session_open(session),
            self._calendar.session_close(session),
        )

    def _experiment(self) -> str | None:
        if self._experiment_id is None:
            # Pure read only: an observer must never run the initialization
            # upsert. An absent experiment simply keeps every alert silent
            # (Codex audit, finding 4).
            experiment = R2D2Repository(self.database).experiment(
                self.settings.r2d2_experiment_code
            )
            self._experiment_id = str(experiment["id"]) if experiment else None
        return self._experiment_id

    def _panel_summary(self, now: datetime) -> dict[str, Any] | None:
        experiment_id = self._experiment()
        if not experiment_id:
            return None
        session_date = now.astimezone(SAO_PAULO).date()
        return R2D2Repository(self.database).episode_summary(
            experiment_id, session_date
        )

    def run_once(self, now: datetime | None = None) -> None:
        """One 60s tick, using the panel's own episode walk as single source."""
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        window = self._session_window(now)
        if window is None:
            return
        open_at, close_at = window
        market_open = bool(open_at <= now < close_at)
        # sell_win must survive the closing bell: episodes observed by the
        # first ticks after 20:00Z still notify (Codex audit, finding 2).
        in_sell_window = bool(open_at <= now < close_at + SELL_WIN_CLOSE_GRACE)
        if not in_sell_window:
            return

        summary = self._panel_summary(now)
        if not summary:
            return

        for detail in summary.get("closed_episode_details", []):
            net = float(detail.get("net_realized_pnl_usd") or 0.0)
            if net <= 0:
                continue
            self.push_notifications.notify(
                category="sell_win",
                title="Episódio vencedor",
                body=(
                    f"{detail['symbol']}: +US$ {net:,.2f} líquidos "
                    "no episódio encerrado."
                ),
                deep_link="/?view=r2d2",
                event_key=f"sell-win:{detail['episode_id']}",
            )

        if not market_open:
            return
        hourly_key = self._hourly_key(now)
        if self._last_hourly_key == hourly_key:
            return
        self._last_hourly_key = hourly_key
        decided = int(summary.get("decided_episodes") or 0)
        if decided <= 0:
            return
        wins = int(summary.get("positive_episodes") or 0)
        percent = float(summary.get("win_rate_percent") or 0.0)
        local = now.astimezone(SAO_PAULO)
        self.push_notifications.notify(
            category="hourly_win_rate",
            title="Taxa de acerto acumulada do dia",
            body=(
                f"Acumulado do pregão: {wins}W/{decided} episódios decididos "
                f"= {percent:.1f}% "
                f"até {local:%H:%M}."
            ),
            deep_link="/?view=falcon",
            event_key=f"hourly-win-rate:{hourly_key}",
        )
