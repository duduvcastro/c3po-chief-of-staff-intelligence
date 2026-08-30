from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .code_census import CodeCensusService
from .config import get_settings
from .database import Database
from .governance_vulnerability import GovernanceVulnerabilityService
from .operational_incidents import OperationalIncidentService
from .observability import init_sentry
from .push_notifications import PushNotificationService
from .push_market_alerts import PushMarketAlertsService
from .server_usage import ServerUsageCollector


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("c3po.server_usage_worker")
SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def notify_disk_threshold(
    push_notifications: PushNotificationService,
    sample: dict[str, Any],
) -> dict[str, Any] | None:
    total_bytes = int(sample.get("disk_total_bytes") or 0)
    used_bytes = int(sample.get("disk_used_bytes") or 0)
    if total_bytes <= 0:
        return None
    disk_percent = used_bytes / total_bytes * 100
    if disk_percent <= 80.0:
        return None
    collected_at = sample.get("collected_at")
    event_at = collected_at if isinstance(collected_at, datetime) else datetime.now(timezone.utc)
    local_date = event_at.astimezone(SAO_PAULO).date().isoformat()
    server_id = str(sample.get("server_id") or "unknown")
    return push_notifications.notify(
        category="disk_threshold",
        title="Disco requer atenção",
        body=f"{disk_percent:.1f}% da capacidade do servidor está em uso.",
        deep_link="/?view=serverusage",
        event_key=f"disk-threshold:{server_id}:{local_date}",
    )


def run_worker() -> None:
    settings = get_settings()
    init_sentry(settings, service_name="server-usage-worker")
    database = Database(settings)
    database.initialize()
    push_notifications = PushNotificationService(settings, database)
    operational_incidents = OperationalIncidentService(database)
    collector = ServerUsageCollector(settings, database)
    code_census = CodeCensusService(settings, database, push_notifications)
    governance_vulnerability = GovernanceVulnerabilityService(
        settings,
        database,
        push_notifications=push_notifications,
        operational_incidents=operational_incidents,
    )
    market_alerts = PushMarketAlertsService(settings, database, push_notifications)
    previous = collector.cpu_ticks()
    while True:
        time.sleep(max(15, settings.server_usage_interval_seconds))
        try:
            code_census.run_daily_if_due(Path(settings.server_usage_disk_path))
        except Exception:
            logger.exception("Daily code census failed; next attempt tomorrow")
        try:
            market_alerts.run_once()
        except Exception:
            logger.exception("Push market alerts tick failed; retrying next tick")
        try:
            governance_vulnerability.run_daily_if_due(
                Path(settings.server_usage_disk_path)
            )
        except Exception:
            logger.exception(
                "Daily governance and vulnerability check failed; retry remains fail-closed"
            )
        current = collector.cpu_ticks()
        sample = collector.sample(previous, current)
        database.save_server_usage_samples([sample])
        notify_disk_threshold(push_notifications, sample)
        database.purge_server_usage_samples(
            datetime.now(timezone.utc) - timedelta(days=max(2, settings.server_usage_retention_days))
        )
        previous = current
        logger.info(
            "Server usage: cpu=%.2f%% steal=%.2f%% load1=%.2f disk=%.2f%%",
            sample["cpu_percent"] or 0.0,
            sample["cpu_steal_percent"] or 0.0,
            sample["load_average_1m"],
            sample["disk_used_bytes"] / sample["disk_total_bytes"] * 100,
        )


def import_sadf(path: Path) -> None:
    settings = get_settings()
    init_sentry(settings, service_name="server-usage-worker")
    database = Database(settings)
    database.initialize()
    count = ServerUsageCollector(settings, database).import_sadf(path.read_text(encoding="utf-8"))
    logger.info("Imported %s sysstat samples from %s", count, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--import-sadf", type=Path)
    args = parser.parse_args()
    if args.import_sadf:
        import_sadf(args.import_sadf)
    else:
        run_worker()


if __name__ == "__main__":
    main()
