from __future__ import annotations

import argparse
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .code_census import CodeCensusService
from .maintenance_gate import job, startup_job
from .config import get_settings
from .database import Database
from .governance_vulnerability import AUTOMATION_REPORT, GovernanceVulnerabilityService, report_sha256
from .operational_incidents import OperationalIncidentService
from .observability import init_sentry
from .push_notifications import PushNotificationService
from .push_market_alerts import PushMarketAlertsService
from .server_usage import ServerUsageCollector


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("c3po.server_usage_worker")
SAO_PAULO = ZoneInfo("America/Sao_Paulo")
ROUTINE_SETTLE_DELAY = timedelta(minutes=1)
OBSERVED_REPORT_WAIT = timedelta(minutes=10)


def _aware_instant(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None


class GovernanceRefresh:
    """Re-attest changed routine evidence after it settles, and an expiring grace.

    The ordinary daily/hourly scheduler keeps its state and failure backoff. A
    valid preliminary ``observed`` report gets ten minutes to be finalized; an
    invalid or unreadable report is never mistaken for that temporary state.
    """

    def __init__(self, service: GovernanceVulnerabilityService) -> None:
        self.service = service
        self._fingerprint: str | None = None
        self._change_due: datetime | None = None
        self._handled_until: datetime | None = None
        self._observation_retry_at: datetime | None = None

    @staticmethod
    def _routine(root: Path) -> tuple[str | None, dict[str, Any] | None]:
        try:
            raw = (root / AUTOMATION_REPORT).read_bytes()
        except FileNotFoundError:
            return None, None
        except OSError as error:
            return f"unreadable:{type(error).__name__}", None
        fingerprint = hashlib.sha256(raw).hexdigest()
        try:
            report = json.loads(raw)
        except (ValueError, UnicodeError):
            return fingerprint, None
        if (not isinstance(report, dict) or report.get("schema") != "C3PO_SECURITY_AUTOMATION-v1"
                or report.get("report_sha256") != report_sha256(report)):
            return fingerprint, None
        return fingerprint, report

    def run_if_due(self, root: Path, *, now: datetime | None = None) -> bool:
        measured_at = now or datetime.now(timezone.utc)
        fingerprint, routine = self._routine(root)
        if fingerprint != self._fingerprint:
            self._fingerprint = fingerprint
            self._change_due = measured_at + ROUTINE_SETTLE_DELAY
            self._observation_retry_at = None

        observed_until = None
        if routine is not None and routine.get("status") == "observed":
            generated = _aware_instant(routine.get("generated_at"))
            if generated is not None:
                observed_until = generated + OBSERVED_REPORT_WAIT
        fresh_observation = (observed_until is not None and measured_at < observed_until
                             and observed_until <= measured_at + OBSERVED_REPORT_WAIT + timedelta(minutes=5))
        if fresh_observation and self._observation_retry_at is not None and measured_at < self._observation_retry_at:
            return False

        latest = self.service.database.latest_governance_vulnerability_report()
        attested = latest if isinstance(latest, dict) and latest.get("report_sha256") == report_sha256(latest) else {}
        if attested and routine is not None:
            automation = attested.get("security_automation")
            if isinstance(automation, dict) and automation.get("report_sha256") == routine.get("report_sha256"):
                # A real issue may already be signalled while the routine is
                # preliminary. Reconcile that state when its ten minutes end.
                self._change_due = observed_until if automation.get("observation_pending") is True else None
        grace = attested.get("post_deploy_grace")
        until = _aware_instant(grace.get("until")) if isinstance(grace, dict) and grace.get("active") is True else None
        expired = until is not None and measured_at >= until and until != self._handled_until

        if self._change_due is not None and measured_at < self._change_due and not expired:
            return False
        changed = self._change_due is not None
        inserted = self.service.run_daily_if_due(root, now=measured_at, force=changed or expired)
        if inserted:
            self._change_due = observed_until if fresh_observation else None
            self._observation_retry_at = None
            if expired:
                self._handled_until = until
        elif fresh_observation:
            # A provisional read is neither success nor failure. Retry at most
            # once a minute; the service retains any genuine failure backoff.
            assert observed_until is not None
            self._observation_retry_at = min(measured_at + ROUTINE_SETTLE_DELAY, observed_until)
        return inserted


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
    with startup_job():
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
        governance_refresh = GovernanceRefresh(governance_vulnerability)
        market_alerts = PushMarketAlertsService(settings, database, push_notifications)
        previous = collector.cpu_ticks()
    sample_interval = max(15, settings.server_usage_interval_seconds)
    next_sample_at = time.monotonic() + sample_interval
    while True:
        time.sleep(max(0, min(60, next_sample_at - time.monotonic())))
        with job() as admitted:
            if not admitted:
                time.sleep(5)
                continue
            try:
                governance_refresh.run_if_due(
                    Path(settings.server_usage_disk_path)
                )
            except Exception:
                logger.exception(
                    "Daily governance and vulnerability check failed; retry remains fail-closed"
                )
            if time.monotonic() < next_sample_at:
                continue  # the short wake only re-attests governance; other work keeps its configured cadence
            try:
                code_census.run_daily_if_due(Path(settings.server_usage_disk_path))
            except Exception:
                logger.exception("Daily code census failed; next attempt tomorrow")
            try:
                market_alerts.run_once()
            except Exception:
                logger.exception("Push market alerts tick failed; retrying next tick")
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
            next_sample_at = time.monotonic() + sample_interval


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
