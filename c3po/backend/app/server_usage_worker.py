from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .code_census import CodeCensusService
from .config import get_settings
from .database import Database
from .observability import init_sentry
from .server_usage import ServerUsageCollector


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("c3po.server_usage_worker")


def run_worker() -> None:
    settings = get_settings()
    init_sentry(settings, service_name="server-usage-worker")
    database = Database(settings)
    database.initialize()
    collector = ServerUsageCollector(settings, database)
    code_census = CodeCensusService(settings, database)
    previous = collector.cpu_ticks()
    while True:
        time.sleep(max(15, settings.server_usage_interval_seconds))
        try:
            code_census.run_daily_if_due(Path(settings.server_usage_disk_path))
        except Exception:
            logger.exception("Daily code census failed; next attempt tomorrow")
        current = collector.cpu_ticks()
        sample = collector.sample(previous, current)
        database.save_server_usage_samples([sample])
        database.purge_server_usage_samples(
            datetime.now(timezone.utc) - timedelta(days=max(2, settings.server_usage_retention_days))
        )
        previous = current
        logger.info(
            "Server usage: cpu=%.2f%% disk=%.2f%%",
            sample["cpu_percent"] or 0.0,
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
