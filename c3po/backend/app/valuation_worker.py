import logging
import time
from dataclasses import dataclass
from datetime import datetime, time as wall_time, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from .chewie_fundamentals import ChewieFundamentalsService
from .config import get_settings
from .database import Database
from .investor_relations import InvestorRelationsService
from .market_data.b3_screener import B3ScreenerService
from .market_data.eodhd_stream import EodhdRealtimeStream
from .market_data.realtime import RealtimeMarketsService
from .market_data.service import MarketDataService
from .market_data.us_screener import USScreeningService
from .one_pager import OnePagerService
from .official_fundamentals import ensure_builtin_official_fundamentals
from .valuation_policy import METHODOLOGY_VERSION
from .valuation_v2_data import ValuationV2DataService
from .valuation_v2_peer_quality import ValuationV2PeerQualityService
from .valuation_v2_shadow import ValuationV2ShadowService
from .valuation_worker_contract import (
    VALUATION_WORKER_CANONICAL_PHASE,
    VALUATION_WORKER_PHASES,
    VALUATION_WORKER_SOURCE_TYPE,
)


SAO_PAULO = ZoneInfo("America/Sao_Paulo")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("c3po.valuation_worker")

CANONICAL_RETRY_DELAY = timedelta(minutes=15)
OFFHOURS_RETRY_DELAY = timedelta(minutes=30)
OFFHOURS_START_HOUR = 1
OFFHOURS_END_HOUR = 8


@dataclass(frozen=True)
class OffhoursPhase:
    key: str
    last_completed_at: Callable[[], datetime | None]
    operation: Callable[[], Any]


@dataclass(frozen=True)
class WorkerIterationResult:
    next_wake_at: datetime
    canonical_status: str
    phase_statuses: dict[str, str]


def start_of_today(now: datetime) -> datetime:
    return datetime.combine(now.date(), wall_time.min, tzinfo=SAO_PAULO)


def next_midnight(now: datetime) -> datetime:
    return start_of_today(now) + timedelta(days=1)


def _phase_is_due(last_completed_at: datetime | None, due_at: datetime) -> bool:
    if last_completed_at is None:
        return True
    if last_completed_at.tzinfo is None:
        last_completed_at = last_completed_at.replace(tzinfo=SAO_PAULO)
    return last_completed_at.astimezone(SAO_PAULO) < due_at


def _result_item_count(result: Any) -> int:
    if result is None:
        return 0
    if isinstance(result, (dict, list, tuple, set)):
        return len(result)
    return 1


def _run_recorded_phase(
    database: Database,
    phase_key: str,
    operation: Callable[[], Any],
    *,
    scheduled_for: datetime,
    canonical_status: str,
) -> Any:
    definition = VALUATION_WORKER_PHASES[phase_key]
    metadata = {
        "phase": phase_key,
        "scheduled_for": scheduled_for.isoformat(),
        "timezone": str(SAO_PAULO),
        "canonical_status": canonical_status,
        "uses_persisted_universe_fallback": (
            phase_key != VALUATION_WORKER_CANONICAL_PHASE
            and canonical_status == "failed"
        ),
        "count_semantics": "top_level_result_items",
    }
    run_id = database.begin_ingestion_run(
        definition["code"],
        definition["name"],
        VALUATION_WORKER_SOURCE_TYPE,
        metadata,
    )
    try:
        result = operation()
    except Exception as exc:
        error_summary = f"{type(exc).__name__}: {exc}"[:1000]
        database.finish_ingestion_run(run_id, "failed", 0, 0, error_summary)
        raise
    database.finish_ingestion_run(
        run_id,
        "succeeded",
        0,
        _result_item_count(result),
    )
    return result


def run_worker_iteration(
    database: Database,
    *,
    now: datetime,
    canonical_due: bool,
    canonical_operation: Callable[[], Any],
    offhours_phases: tuple[OffhoursPhase, ...],
) -> WorkerIterationResult:
    canonical_status = "current"
    phase_statuses: dict[str, str] = {}
    wake_targets = [next_midnight(now)]

    if canonical_due:
        try:
            _run_recorded_phase(
                database,
                VALUATION_WORKER_CANONICAL_PHASE,
                canonical_operation,
                scheduled_for=start_of_today(now),
                canonical_status="running",
            )
            canonical_status = "succeeded"
        except Exception:
            canonical_status = "failed"
            logger.exception(
                "Nightly valuation cycle failed; off-hours phases remain independent"
            )
            wake_targets.append(now + CANONICAL_RETRY_DELAY)

    offhours_due_at = start_of_today(now) + timedelta(hours=OFFHOURS_START_HOUR)
    offhours_window_end = start_of_today(now) + timedelta(hours=OFFHOURS_END_HOUR)
    due_phases = [
        phase
        for phase in offhours_phases
        if _phase_is_due(phase.last_completed_at(), offhours_due_at)
    ]

    if now < offhours_due_at:
        if due_phases:
            wake_targets.append(offhours_due_at)
            phase_statuses.update({phase.key: "pending" for phase in due_phases})
    elif now < offhours_window_end:
        retry_required = False
        for phase in due_phases:
            try:
                result = _run_recorded_phase(
                    database,
                    phase.key,
                    phase.operation,
                    scheduled_for=offhours_due_at,
                    canonical_status=canonical_status,
                )
                phase_statuses[phase.key] = "succeeded"
                logger.info(
                    "%s complete: %s",
                    VALUATION_WORKER_PHASES[phase.key]["name"],
                    result,
                )
            except Exception:
                phase_statuses[phase.key] = "failed"
                retry_required = True
                logger.exception(
                    "%s failed; keeping prior evidence and retrying inside the window",
                    VALUATION_WORKER_PHASES[phase.key]["name"],
                )
        retry_at = now + OFFHOURS_RETRY_DELAY
        if retry_required and retry_at < offhours_window_end:
            wake_targets.append(retry_at)
    else:
        phase_statuses.update({phase.key: "outside_window" for phase in due_phases})

    return WorkerIterationResult(
        next_wake_at=min(wake_targets),
        canonical_status=canonical_status,
        phase_statuses=phase_statuses,
    )


def run_nightly(
    database: Database,
    investor_relations: InvestorRelationsService,
    screener: B3ScreenerService,
    us_screener: USScreeningService,
) -> None:
    started_at = datetime.now(SAO_PAULO)
    logger.info("Starting nightly CVM First valuation cycle at %s", started_at.isoformat())
    ir_result = investor_relations.sync("all")
    logger.info("Official-source refresh: %s", ir_result.sources)
    response = screener.screen(refresh=True)
    logger.info(
        "Nightly valuation complete: basis=%s universe=%s eligible=%s candidates=%s",
        response.generated_at.isoformat(),
        response.universe_size,
        response.eligible_count,
        len(response.items),
    )
    us_counts = us_screener.refresh_all()
    logger.info("US canonical valuation complete: %s", us_counts)


def main() -> None:
    settings = get_settings()
    database = Database(settings)
    database.initialize()
    ensure_builtin_official_fundamentals(database)
    investor_relations = InvestorRelationsService(settings, database)
    market_data = MarketDataService(settings, database)
    screener = B3ScreenerService(settings, database, market_data.http)
    realtime = RealtimeMarketsService(
        settings,
        database,
        market_data.http,
        stream=EodhdRealtimeStream(settings.eodhd_api_token, max_symbols=settings.r2d2_ws_max_symbols),
    )
    one_pagers = OnePagerService(
        settings,
        database,
        market_data,
        b3_screener=screener,
        investor_relations=investor_relations,
    )
    us_screener = USScreeningService(settings, database, realtime, one_pagers)
    one_pagers.set_us_screener(us_screener)
    chewie = ChewieFundamentalsService(settings, database, market_data.http)
    v2_data = ValuationV2DataService(settings, database, market_data.http)
    v2_peer_quality = ValuationV2PeerQualityService(
        settings, database, market_data.http
    )
    v2_shadow = ValuationV2ShadowService(settings, database, market_data.http)

    offhours_phases = (
        OffhoursPhase(
            "chewie",
            chewie.last_refreshed_at,
            lambda: chewie.refresh_all(budget=settings.chewie_daily_symbol_budget),
        ),
        OffhoursPhase("v2_data", v2_data.last_refreshed_at, v2_data.refresh_all),
        OffhoursPhase("shadow", v2_shadow.last_run_at, v2_shadow.run_all),
        OffhoursPhase(
            "peer_quality",
            v2_peer_quality.last_refreshed_at,
            v2_peer_quality.refresh_all,
        ),
    )

    while True:
        now = datetime.now(SAO_PAULO)
        candidate = database.latest_analysis_snapshot("candidate_screen", "B3_TOP_10")
        universe = database.latest_analysis_snapshot("valuation_universe", "B3_UNIVERSE")
        us_snapshots = [
            database.latest_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE")
            for market in ("NASDAQ", "NYSE")
        ]
        latest_at = candidate.get("published_at") if candidate else None
        latest_local = latest_at.astimezone(SAO_PAULO) if latest_at and latest_at.tzinfo else latest_at
        candidate_outputs = candidate.get("outputs") if candidate else None
        universe_inputs = universe.get("inputs") if universe else None
        version_is_current = (
            isinstance(candidate_outputs, dict)
            and candidate_outputs.get("methodology_version") == METHODOLOGY_VERSION
            and isinstance(universe_inputs, dict)
            and universe_inputs.get("methodology_version") == METHODOLOGY_VERSION
        )
        us_versions_current = all(
            snapshot
            and isinstance(snapshot.get("inputs"), dict)
            and snapshot["inputs"].get("methodology_version") == METHODOLOGY_VERSION
            for snapshot in us_snapshots
        )
        bootstrap_required = candidate is None or universe is None or not version_is_current or not us_versions_current
        cycle_due = latest_local is None or latest_local < start_of_today(now)
        result = run_worker_iteration(
            database,
            now=now,
            canonical_due=bootstrap_required or cycle_due,
            canonical_operation=lambda: run_nightly(
                database,
                investor_relations,
                screener,
                us_screener,
            ),
            offhours_phases=offhours_phases,
        )

        now = datetime.now(SAO_PAULO)
        wake_at = result.next_wake_at
        logger.info("Next valuation-worker wake-up at %s", wake_at.isoformat())
        time.sleep(max(30, int((wake_at - now).total_seconds())))


if __name__ == "__main__":
    main()
