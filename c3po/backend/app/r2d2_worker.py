from __future__ import annotations

import logging
import os
from pathlib import Path
import time
from threading import Event, Thread

from .config import get_settings
from .database import Database
from .investor_relations import InvestorRelationsService
from .market_data.b3_screener import B3ScreenerService
from .market_data.service import MarketDataService
from .market_data.realtime import RealtimeMarketsService
from .market_data.eodhd_stream import EodhdRealtimeStream
from .microstructure_capture import AppendOnlyRawStreamCapture, CompositeRawStreamCapture
from .microstructure_processor import MicrostructureProcessor
from .microstructure_telemetry import MicrostructureResourceTelemetry
from .one_pager import OnePagerService
from .observability import init_sentry
from .r2d2 import R2D2PaperService


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


def _validated_capture_root(capture_root: Path, data_root: Path) -> Path:
    resolved_capture = capture_root.resolve()
    resolved_data = data_root.resolve()
    try:
        resolved_capture.relative_to(resolved_data)
    except ValueError as exc:
        raise RuntimeError(
            "Microstructure capture must use the dedicated Day D data mount"
        ) from exc
    if resolved_capture == resolved_data:
        raise RuntimeError(
            "Microstructure capture must use a child directory of the Day D data mount"
        )
    return resolved_capture


def _risk_monitor_loop(service: R2D2PaperService, stop: Event, interval_seconds: float) -> None:
    interval = max(2.0, min(5.0, interval_seconds))
    logger.info("R2D2 dedicated risk monitor enabled at %.1f-second cadence", interval)
    while not stop.is_set():
        started = time.monotonic()
        try:
            exits = service.run_risk_monitor_cycle()
            logger.debug("R2D2 risk monitor exits=%d", exits)
        except Exception:
            logger.exception("Unhandled R2D2 dedicated risk-monitor error")
        elapsed = time.monotonic() - started
        stop.wait(max(0.0, interval - elapsed))


def _fast_risk_watcher_loop(service: R2D2PaperService, stop: Event, interval_seconds: float) -> None:
    interval = max(0.5, min(2.0, interval_seconds))
    logger.info("R2D2 fast risk watcher enabled at %.1f-second cadence", interval)
    while not stop.is_set():
        started = time.monotonic()
        try:
            exits = service.run_fast_risk_watcher_cycle()
            logger.debug("R2D2 fast risk watcher exits=%d", exits)
        except Exception:
            logger.exception("Unhandled R2D2 fast risk-watcher error")
        elapsed = time.monotonic() - started
        stop.wait(max(0.0, interval - elapsed))


def main() -> None:
    settings = get_settings()
    init_sentry(settings, service_name="r2d2-worker")
    database = Database(settings)
    database.initialize()
    market_data = MarketDataService(settings, database)
    raw_capture = None
    processor = None
    telemetry = None
    captures = []
    if settings.r2d2_microstructure_raw_capture_enabled:
        capture_root = _validated_capture_root(
            settings.r2d2_microstructure_raw_dir,
            settings.day_d_dataset_root,
        )
        minimum_free_bytes = int(
            settings.day_d_dataset_min_free_disk_gb * 1024**3
        )
        raw_capture = AppendOnlyRawStreamCapture(
            capture_root,
            queue_size=settings.r2d2_microstructure_raw_queue_size,
            rotate_bytes=settings.r2d2_microstructure_raw_rotate_mb * 1024 * 1024,
            flush_every=settings.r2d2_microstructure_raw_flush_every,
            minimum_free_bytes=minimum_free_bytes,
        )
        captures.append(raw_capture)
        if settings.r2d2_microstructure_processor_enabled:
            processor = MicrostructureProcessor(
                capture_root.parent / "aggregates",
                bbo_max_age_seconds=settings.r2d2_microstructure_bbo_max_age_seconds,
                allowed_lateness_seconds=settings.r2d2_microstructure_allowed_lateness_seconds,
                queue_size=settings.r2d2_microstructure_aggregate_queue_size,
                rotate_bytes=settings.r2d2_microstructure_raw_rotate_mb * 1024 * 1024,
                flush_every=settings.r2d2_microstructure_raw_flush_every,
                minimum_free_bytes=minimum_free_bytes,
            )
            captures.append(processor)
        if settings.r2d2_microstructure_telemetry_enabled:
            telemetry = MicrostructureResourceTelemetry(
                capture_root.parent / "telemetry",
                raw_capture=raw_capture,
                processor=processor,
                interval_seconds=(
                    settings.r2d2_microstructure_telemetry_interval_seconds
                ),
                minimum_free_bytes=minimum_free_bytes,
                service_name=os.getenv("C3PO_SERVICE_NAME", "r2d2-worker"),
            )
    capture_pipeline = CompositeRawStreamCapture(captures) if captures else None
    stream = EodhdRealtimeStream(
        settings.eodhd_api_token,
        max_symbols=settings.r2d2_ws_max_symbols,
        raw_capture=capture_pipeline,
    )
    stream.start()
    if telemetry:
        try:
            telemetry.start()
        except Exception:
            stream.stop()
            raise
    realtime = RealtimeMarketsService(settings, database, market_data.http, stream=stream)
    screener = B3ScreenerService(settings, database, market_data.http)
    investor_relations = InvestorRelationsService(settings, database)
    one_pagers = OnePagerService(
        settings, database, market_data,
        b3_screener=screener,
        investor_relations=investor_relations,
    )
    service = R2D2PaperService(settings, database, realtime, screener, one_pagers)
    risk_service = R2D2PaperService(settings, database, realtime, screener, one_pagers)
    experiment = service.ensure_initialized()
    logger.info(
        "R2D2 continuous paper strategy %s ready from %s; 90-day checkpoint %s; real brokerage execution disabled",
        experiment["code"], experiment["start_date"], experiment["checkpoint_date"],
    )
    last_candidate_scan = 0.0
    risk_stop = Event()
    risk_thread: Thread | None = None
    fast_risk_thread: Thread | None = None
    if settings.r2d2_risk_monitor_enabled:
        risk_thread = Thread(
            target=_risk_monitor_loop,
            args=(risk_service, risk_stop, settings.r2d2_risk_monitor_interval_seconds),
            name="r2d2-risk-monitor",
            daemon=True,
        )
        risk_thread.start()
    else:
        logger.info("R2D2 dedicated risk monitor disabled by feature flag")
    if settings.r2d2_fast_risk_watcher_enabled:
        fast_risk_thread = Thread(
            target=_fast_risk_watcher_loop,
            args=(risk_service, risk_stop, settings.r2d2_fast_risk_watcher_interval_seconds),
            name="r2d2-fast-risk-watcher",
            daemon=True,
        )
        fast_risk_thread.start()
    else:
        logger.info("R2D2 fast risk watcher disabled by feature flag")
    try:
        while True:
            try:
                current = time.monotonic()
                scan_entries = current - last_candidate_scan >= max(20, settings.r2d2_cycle_seconds)
                dashboard = service.run_cycle(scan_entries=scan_entries)
                if scan_entries:
                    last_candidate_scan = current
                logger.info(
                    "R2D2 cycle=%s status=%s nav=%.2f cash=%.2f positions=%d stream=%s",
                    "full" if scan_entries else "risk",
                    dashboard.last_cycle.status if dashboard.last_cycle else "initialized",
                    dashboard.nav_usd, dashboard.cash_usd, dashboard.open_positions, stream.status,
                )
                if scan_entries and raw_capture:
                    capture_stats = raw_capture.stats()
                    logger.info(
                        "R2D2 microstructure raw capture accepted=%d written=%d "
                        "dropped=%d disk_dropped=%d queue=%d/%d high_water=%d errors=%d",
                        capture_stats.accepted,
                        capture_stats.written,
                        capture_stats.dropped,
                        capture_stats.disk_guard_dropped,
                        capture_stats.queue_depth,
                        capture_stats.queue_capacity,
                        capture_stats.queue_high_water,
                        capture_stats.write_errors,
                    )
                if scan_entries and processor:
                    processor_stats = processor.stats()
                    logger.info(
                        "R2D2 microstructure processor accepted=%d processed=%d malformed=%d "
                        "ignored=%d late=%d dropped=%d disk_dropped=%d "
                        "queue=%d/%d high_water=%d aggregates=%d errors=%d",
                        processor_stats.accepted,
                        processor_stats.processed,
                        processor_stats.malformed,
                        processor_stats.ignored,
                        processor_stats.late,
                        processor_stats.dropped,
                        processor_stats.disk_guard_dropped,
                        processor_stats.queue_depth,
                        processor_stats.queue_capacity,
                        processor_stats.queue_high_water,
                        processor_stats.aggregates_written,
                        processor_stats.write_errors,
                    )
            except Exception:
                logger.exception("Unhandled R2D2 worker error")
            time.sleep(20)
    finally:
        risk_stop.set()
        if risk_thread:
            risk_thread.join(timeout=10)
        if fast_risk_thread:
            fast_risk_thread.join(timeout=10)
        stream.stop()
        if telemetry:
            telemetry.stop()


if __name__ == "__main__":
    main()
