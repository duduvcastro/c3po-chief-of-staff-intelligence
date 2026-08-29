from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

from .config import Settings
from .database import Database
from .push_notifications import PushNotificationService
from .r2d2_exit_policy_engine import build_episodes
from .r2d2_exit_policy_study import LedgerReader


logger = logging.getLogger("c3po.push_market_alerts")

NEW_YORK = ZoneInfo("America/New_York")
SAO_PAULO = ZoneInfo("America/Sao_Paulo")


class PushMarketAlertsService:
    """Read-only observer for the sell_win and hourly_win_rate push categories.

    Amendment 1 of C3PO_MOBILE_PUSH_V2. Episodes come from the OFFICIAL study
    builder over the real ledger - the same source the panels use - and the
    R2D2 trading worker is never touched. Delivery idempotency lives in the
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
        self._last_hourly_key: str | None = None

    def _closed_episodes_today(self, now: datetime) -> list:
        _experiment, fills = LedgerReader(self.database).read(
            self.settings.r2d2_experiment_code
        )
        episodes, _counts = build_episodes(fills)
        session = now.astimezone(NEW_YORK).date()
        return [
            episode for episode in episodes
            if episode.closed
            and not episode.strategy_excluded
            and episode.closed_at is not None
            and episode.closed_at.astimezone(NEW_YORK).date() == session
        ]

    def _episode_net_usd(self, episode) -> float:
        return sum(
            fill.realized_pnl_usd
            for fill in episode.fills
            if fill.side == "SELL" and fill.realized_pnl_usd is not None
        )

    def _market_is_open(self, now: datetime) -> bool:
        session = now.astimezone(NEW_YORK).date()
        if not self._calendar.is_session(session):
            return False
        open_at = self._calendar.session_open(session)
        close_at = self._calendar.session_close(session)
        return bool(open_at <= now < close_at)

    def run_once(self, now: datetime | None = None) -> None:
        """One 60s tick: emit new sell wins and, on the hour, the win rate."""
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if not self._market_is_open(now):
            return
        episodes = self._closed_episodes_today(now)
        if not episodes:
            return

        for episode in episodes:
            net = self._episode_net_usd(episode)
            if net <= 0:
                continue
            self.push_notifications.notify(
                category="sell_win",
                title="Episódio vencedor",
                body=f"{episode.symbol}: +US$ {net:,.2f} líquidos no episódio encerrado.",
                deep_link="/?view=r2d2",
                event_key=f"sell-win:{episode.id}",
            )

        local = now.astimezone(SAO_PAULO)
        hourly_key = f"{local.date().isoformat()}:{local.hour:02d}"
        # Fire once per full hour, on the first tick at the boundary. A worker
        # (re)started mid-hour stays silent until the next full hour; delivery
        # idempotency by event_key also protects across restarts.
        if self._last_hourly_key != hourly_key and local.minute < 5:
            self._last_hourly_key = hourly_key
            wins = sum(1 for episode in episodes if self._episode_net_usd(episode) > 0)
            total = len(episodes)
            percent = wins / total * 100.0
            self.push_notifications.notify(
                category="hourly_win_rate",
                title="Taxa de acerto da sessão",
                body=f"{wins}W/{total} episódios fechados = {percent:.1f}% até {local:%H:%M}.",
                deep_link="/?view=falcon",
                event_key=f"hourly-win-rate:{hourly_key}",
            )
