import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, time as wall_time, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from . import ingestion_process, valuation_env
from .chewie_fundamentals import ChewieFundamentalsService
from .maintenance_gate import job, startup_job
from .config import Settings, get_settings
from .database import Database
from .investor_relations import InvestorRelationsService
from .market_data.b3_screener import B3ScreenerService
from .market_data.eodhd_stream import EodhdRealtimeStream
from .market_data.http import JsonHttpClient
from .market_data.realtime import RealtimeMarketsService
from .market_data.service import MarketDataService
from .market_data.us_screener import USScreeningService
from .one_pager import OnePagerService
from .official_fundamentals import ensure_builtin_official_fundamentals
from .observability import HealthcheckPing, init_sentry
from .operational_incidents import OperationalIncidentService
from .r2d2_cash_yield import CashYieldDataError, CashYieldPendingData, R2D2CashYieldService
from .push_notifications import PushNotificationService
from .valuation_asfiled import evaluate_us_filings
from .valuation_decision import last_run_at as decision_last_run_at, not_before as decision_not_before, run_shadow as run_decisor_shadow
from .valuation_earnings_calendar import MAX_FAILURES_PER_NIGHT as EARNINGS_CALENDAR_MAX_FAILURES, EarningsCalendarService
from .valuation_policy import METHODOLOGY_VERSION
from .valuation_v2_data import ValuationV2DataService
from .valuation_v2_peer_quality import ValuationV2PeerQualityService
from .valuation_v2_shadow import ValuationV2ShadowService
from .valuation_v3_shadow import ValuationV3ShadowService
from .valuation_price_history import PriceHistoryService
from .valuation_worker_contract import (
    VALUATION_WORKER_ADVISORY_PHASES,
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
CASH_YIELD_PHASE_KEY = "cash_yield"
CASH_YIELD_FAILURE_ACTION = "r2d2.cash_yield.failed"
CASH_YIELD_RECOVERY_ACTION = "r2d2.cash_yield.recovered"
# One incident per phase and failure episode (the key carries no date). Legacy
# per-night keys ``<key>:<YYYY-MM-DD>`` share the prefix and close on recovery.
PHASE_INCIDENT_KEY_PREFIX = "notification:job_failure:valuation-phase-failure:"
# Severity by persistence: a failing night that retries is attention; the incident
# becomes critical on the Nth consecutive failing night, or at once on a data fault.
PHASE_FAILURE_CRITICAL_NIGHTS = 2
# The live ensemble producer's night (valuation_live_ensemble): no attempt STARTS at or after 05:00 BRT and every attempt
# STOPS reading by 05:30 BRT (checked before each step and each provider request, each request bounded as a whole by the
# time left; finished sections may still be written until 05:35), so the maintenance lease and the phase's
# ingestion run are free 30 min before cash_yield's 06:00 window and 2 h 45 before the 08:15 grid window, whose blocking
# check refuses a chunk while a valuation_worker run is `running`; the decisor (window to 08:00) keeps 2 h 30 after it.
# Two failed attempts a night at most (the calendar's retry-cap pattern), then the next night.
ENSEMBLE_LIVE_LAST_START_HOUR = 5
ENSEMBLE_LIVE_DEADLINE = timedelta(hours=5, minutes=30)
ENSEMBLE_LIVE_MAX_FAILURES = 2


@dataclass(frozen=True)
class OffhoursPhase:
    key: str
    last_completed_at: Callable[[], datetime | None]
    operation: Callable[[], Any]
    start_hour: int = OFFHOURS_START_HOUR
    end_hour: int = OFFHOURS_END_HOUR
    max_failures: int | None = None  # failed attempts per scheduled night after which the phase waits for the next one
    not_before: Callable[[], datetime | None] | None = None  # an instant before which the phase must not run yet ("not yet": nothing recorded)
    # the phase's EFFECTIVE clock, read afresh at its admission: an earlier phase of the same pass may have run long, so the
    # pass's opening instant would admit it after its window (unset: the pass's instant, as every other phase)
    clock: Callable[[], datetime] | None = None

    @property
    def advisory(self) -> bool:
        """An advisory phase never pages: its failure neither fails the worker's check nor pushes a job failure."""
        return self.key in VALUATION_WORKER_ADVISORY_PHASES


@dataclass(frozen=True)
class WorkerIterationResult:
    next_wake_at: datetime
    canonical_status: str
    phase_statuses: dict[str, str]


def start_of_today(now: datetime) -> datetime:
    return datetime.combine(now.date(), wall_time.min, tzinfo=SAO_PAULO)


def next_midnight(now: datetime) -> datetime:
    return start_of_today(now) + timedelta(days=1)


def _cash_yield_http_client(settings: Settings) -> JsonHttpClient:
    return JsonHttpClient(
        timeout=settings.r2d2_cash_yield_http_timeout_seconds,
        max_retries=settings.market_data_max_retries,
    )


def _phase_is_due(last_completed_at: datetime | None, due_at: datetime) -> bool:
    if last_completed_at is None:
        return True
    if last_completed_at.tzinfo is None:
        last_completed_at = last_completed_at.replace(tzinfo=SAO_PAULO)
    return last_completed_at.astimezone(SAO_PAULO) < due_at


def ensemble_live_last_run_at(database: Database) -> datetime | None:
    """The live ensemble producer is imported only when its switch schedules the phase: with it off the worker never loads it."""
    from .valuation_live_ensemble import last_run_at

    return last_run_at(database)


def run_ensemble_live(database: Database, settings: Settings, http: JsonHttpClient, *, now: datetime | None = None,
                      clock: Callable[[], datetime] | None = None) -> dict[str, Any]:
    """The ``ensemble_live`` phase: tonight's due time (01:00 America/Sao_Paulo) is the ``since`` of a retry, so an exchange
    already published tonight is skipped and only the missing one is computed again; ``ENSEMBLE_LIVE_DEADLINE`` stops it."""
    from .valuation_live_ensemble import run_nightly

    night = start_of_today((now or datetime.now(SAO_PAULO)).astimezone(SAO_PAULO))
    return run_nightly(database, settings, http, clock=clock, since=night + timedelta(hours=OFFHOURS_START_HOUR),
                       deadline=night + ENSEMBLE_LIVE_DEADLINE)


def ensemble_live_not_before(database: Database, *, now: datetime, decisor_scheduled: bool,
                             decisor_last_run_at: Callable[[], datetime | None],
                             decisor_not_before: Callable[[], datetime | None]) -> datetime | None:
    """The live producer never delays the decisor. The worker defers a phase and goes on with the next ones in the same
    pass, so a decisor deferred for its calendar margin would otherwise wait for the whole live sweep. While the decisor
    is scheduled, still due tonight, deferred (``decisor_not_before``) and not yet attempted since that instant (its
    latest ingestion run), this phase waits until then; the worker wakes, runs the decisor first (it precedes this phase),
    and this phase after it. Read from the decisor's own run record, not from a clock: an earlier phase that ran long in
    the same pass cannot let this one jump ahead. A decisor that is done, not deferred or already attempted never holds it."""
    if not decisor_scheduled:
        return None
    night = start_of_today(now.astimezone(SAO_PAULO))
    if not _phase_is_due(decisor_last_run_at(), night + timedelta(hours=OFFHOURS_START_HOUR)):
        return None
    ready = decisor_not_before()
    if ready is None:
        return None
    code = VALUATION_WORKER_PHASES["decisor_shadow"]["code"]
    attempted = database.ingestion_run_health([code]).get(code, {}).get("started_at")
    if isinstance(attempted, datetime):
        attempted = attempted if attempted.tzinfo is not None else attempted.replace(tzinfo=timezone.utc)
        if attempted >= ready:
            return None
    return max(ready, now + timedelta(seconds=1))


def _result_item_count(result: Any) -> int:
    if result is None:
        return 0
    if isinstance(result, (dict, list, tuple, set)):
        return len(result)
    return 1


def _cash_yield_event_exists(database: Database, action: str, subject_id: str) -> bool:
    return any(
        event.get("subject_id") == subject_id
        for event in database.list_audit_events(action=action, limit=100)
    )


def _record_cash_yield_failure(
    database: Database,
    *,
    scheduled_for: datetime,
    error: Exception,
) -> None:
    subject_id = scheduled_for.date().isoformat()
    if _cash_yield_event_exists(database, CASH_YIELD_FAILURE_ACTION, subject_id):
        return
    database.record_audit_event(
        "valuation-worker",
        CASH_YIELD_FAILURE_ACTION,
        "r2d2_cash_yield_session",
        subject_id,
        {
            "scheduled_for": scheduled_for.isoformat(),
            "retry_interval_minutes": int(OFFHOURS_RETRY_DELAY.total_seconds() / 60),
            "retry_window_end_hour_brt": 10,
            "error": f"{type(error).__name__}: {error}"[:1000],
        },
    )


def _record_cash_yield_recovery(database: Database, *, scheduled_for: datetime) -> None:
    subject_id = scheduled_for.date().isoformat()
    if not _cash_yield_event_exists(database, CASH_YIELD_FAILURE_ACTION, subject_id):
        return
    if _cash_yield_event_exists(database, CASH_YIELD_RECOVERY_ACTION, subject_id):
        return
    database.record_audit_event(
        "valuation-worker",
        CASH_YIELD_RECOVERY_ACTION,
        "r2d2_cash_yield_session",
        subject_id,
        {"scheduled_for": scheduled_for.isoformat()},
    )


def phase_incident_key(phase_key: str) -> str:
    return f"{PHASE_INCIDENT_KEY_PREFIX}{phase_key}"


def _is_data_fault(error: Exception) -> bool:
    """A real data/integrity fault (invalid feed, negative rate, canonical-entry
    mismatch). Expected pending states never reach here: they do not raise."""
    return isinstance(error, CashYieldDataError) and not isinstance(error, CashYieldPendingData)


def phase_failure_severity(*, consecutive_nights: int, data_fault: bool) -> str:
    if data_fault or consecutive_nights >= PHASE_FAILURE_CRITICAL_NIGHTS:
        return "critical"
    return "attention"


def _signal_phase_failure(
    database: Database,
    push_notifications: PushNotificationService | None,
    *,
    phase_key: str,
    night: date,
    error: Exception,
    at: datetime,
) -> dict[str, Any] | None:
    """Record the failing night on the phase's single open incident.

    Retries inside the same night carry identical evidence and add no event; each
    new failing night adds one ``observed`` event, so ``event_count`` tracks the
    nights. The push goes out once per episode, when the incident is critical.
    """
    try:
        incidents = OperationalIncidentService(database)
        key = phase_incident_key(phase_key)
        open_since = incidents.open_since(key)
        first_night = open_since.astimezone(SAO_PAULO).date() if open_since else night
        consecutive_nights = max(1, (night - first_night).days + 1)
        data_fault = _is_data_fault(error)
        severity = phase_failure_severity(
            consecutive_nights=consecutive_nights, data_fault=data_fault,
        )
        name = VALUATION_WORKER_PHASES[phase_key]["name"]
        error_class = type(error).__name__
        evidence = {
            "phase": phase_key,
            "night": night.isoformat(),
            "episode_first_night": first_night.isoformat(),
            "consecutive_nights": consecutive_nights,
            "error_class": error_class,
            "fault": "data" if data_fault else "retryable",
            "severity": severity,
            "critical_after_nights": PHASE_FAILURE_CRITICAL_NIGHTS,
        }
        detail = (
            f"{error_class}: {'data fault' if data_fault else 'off-hours phase will retry'}"
            f" · {consecutive_nights} consecutive night(s) since {first_night.isoformat()}"
        )
        incident = incidents.signal(
            incident_key=key, source="worker", severity=severity, title=f"{name} failed",
            detail=detail, deep_link="/?view=health", evidence=evidence, at=at,
        )
        # Escalate inside an episode (never lower it); a reopened incident starts a
        # new episode, so its severity is derived again instead of inherited.
        if incident.get("severity") != severity and (severity == "critical" or open_since is None):
            incident = incidents.set_severity(
                incident_key=key, severity=severity, detail=f"Severity {severity} · {detail}",
                evidence=evidence, at=at,
            ) or incident
        if severity == "critical" and push_notifications:
            push_notifications.notify(
                category="job_failure",
                title=f"{name} failed",
                body=f"{error_class}: failing for {consecutive_nights} night(s)",
                deep_link="/?view=health",
                event_key=f"valuation-phase-failure:{phase_key}:episode:{first_night.isoformat()}",
                record_incident=False,
            )
        return incident
    except Exception:
        logger.exception("Phase incident recording failed without affecting the worker")
        return None


def _resolve_phase_incident(database: Database, *, phase_key: str, observed_at: datetime) -> int:
    try:
        return OperationalIncidentService(database).resolve_recovered_family(
            phase_incident_key(phase_key),
            observed_at=observed_at,
            detail=f"{VALUATION_WORKER_PHASES[phase_key]['name']} succeeded again; incident closed automatically",
        )
    except Exception:
        logger.exception("Phase incident recovery failed without affecting the worker")
        return 0


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
        if phase_key == CASH_YIELD_PHASE_KEY:
            _record_cash_yield_failure(
                database,
                scheduled_for=scheduled_for,
                error=exc,
            )
        raise
    database.finish_ingestion_run(
        run_id,
        "succeeded",
        0,
        _result_item_count(result),
    )
    if phase_key == CASH_YIELD_PHASE_KEY:
        _record_cash_yield_recovery(database, scheduled_for=scheduled_for)
    return result


def run_worker_iteration(
    database: Database,
    *,
    now: datetime,
    canonical_due: bool,
    canonical_operation: Callable[[], Any],
    offhours_phases: tuple[OffhoursPhase, ...],
    healthchecks: dict[str, HealthcheckPing] | None = None,
    push_notifications: PushNotificationService | None = None,
) -> WorkerIterationResult:
    canonical_status = "current"
    phase_statuses: dict[str, str] = {}
    wake_targets = [next_midnight(now)]
    healthchecks = healthchecks or {}
    worker_healthcheck = healthchecks.get("valuation")
    cash_yield_healthcheck = healthchecks.get(CASH_YIELD_PHASE_KEY)
    attempted_work = False
    failed_work = False

    def start_worker_healthcheck() -> None:
        nonlocal attempted_work
        if attempted_work:
            return
        attempted_work = True
        if worker_healthcheck:
            worker_healthcheck.ping("start")

    if canonical_due:
        start_worker_healthcheck()
        try:
            _run_recorded_phase(
                database,
                VALUATION_WORKER_CANONICAL_PHASE,
                canonical_operation,
                scheduled_for=start_of_today(now),
                canonical_status="running",
            )
            canonical_status = "succeeded"
        except Exception as exc:
            canonical_status = "failed"
            failed_work = True
            logger.exception(
                "Nightly valuation cycle failed; off-hours phases remain independent"
            )
            if push_notifications:
                push_notifications.notify(
                    category="job_failure",
                    title="Valuation worker failed",
                    body=f"{type(exc).__name__}: canonical valuation phase failed",
                    deep_link="/?view=health",
                    event_key=f"valuation-canonical-failure:{start_of_today(now).date()}",
                )
            wake_targets.append(now + CANONICAL_RETRY_DELAY)

    for phase in offhours_phases:
        phase_due_at = start_of_today(now) + timedelta(hours=phase.start_hour)
        phase_window_end = start_of_today(now) + timedelta(hours=phase.end_hour)
        current = phase.clock() if phase.clock is not None else now
        if not _phase_is_due(phase.last_completed_at(), phase_due_at):
            continue
        if current < phase_due_at:
            wake_targets.append(phase_due_at)
            phase_statuses[phase.key] = "pending"
            continue
        if current < phase_window_end:
            if phase.max_failures is not None and database.count_ingestion_runs(
                    VALUATION_WORKER_PHASES[phase.key]["code"], "failed", scheduled_for=phase_due_at.isoformat()) >= phase.max_failures:
                phase_statuses[phase.key] = "retry_cap"  # this night's attempts are spent: the next night tries again
                continue
            ready_at = phase.not_before() if phase.not_before is not None else None
            if ready_at is not None and current < ready_at:  # not yet: nothing run, nothing recorded, the worker wakes at ready_at
                phase_statuses[phase.key] = "deferred"
                wake_targets.append(ready_at)
                continue
            if not phase.advisory:
                start_worker_healthcheck()
            if phase.key == CASH_YIELD_PHASE_KEY and cash_yield_healthcheck:
                cash_yield_healthcheck.ping("start")
            try:
                result = _run_recorded_phase(
                    database,
                    phase.key,
                    phase.operation,
                    scheduled_for=phase_due_at,
                    canonical_status=canonical_status,
                )
                phase_statuses[phase.key] = "succeeded"
                logger.info(
                    "%s complete: %s",
                    VALUATION_WORKER_PHASES[phase.key]["name"],
                    result,
                )
                if phase.key == CASH_YIELD_PHASE_KEY and cash_yield_healthcheck:
                    cash_yield_healthcheck.ping("success")
                _resolve_phase_incident(database, phase_key=phase.key, observed_at=current)
            except Exception as exc:
                phase_statuses[phase.key] = "failed"
                if phase.advisory:  # recorded (its ingestion run), retried inside the window up to its cap, never paged
                    logger.warning("%s failed (advisory, not paged): %s", VALUATION_WORKER_PHASES[phase.key]["name"], type(exc).__name__)
                    retry_at = current + OFFHOURS_RETRY_DELAY
                    if retry_at < phase_window_end:
                        wake_targets.append(retry_at)
                    continue
                failed_work = True
                if phase.key == CASH_YIELD_PHASE_KEY and cash_yield_healthcheck:
                    cash_yield_healthcheck.ping("fail")
                logger.exception(
                    "%s failed; keeping prior evidence and retrying inside the window",
                    VALUATION_WORKER_PHASES[phase.key]["name"],
                )
                _signal_phase_failure(
                    database,
                    push_notifications,
                    phase_key=phase.key,
                    night=phase_due_at.date(),
                    error=exc,
                    at=current,
                )
                retry_at = current + OFFHOURS_RETRY_DELAY
                if retry_at < phase_window_end:
                    wake_targets.append(retry_at)
            continue
        phase_statuses[phase.key] = "outside_window"

    if attempted_work and worker_healthcheck:
        worker_healthcheck.ping("fail" if failed_work else "success")

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
    *,
    asfiled_enabled: bool = False,
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
    if asfiled_enabled:  # Valuation as-filed: this cut revalues the US TPs a filing marked stale; record it (migration 053)
        try:
            logger.info("US as-filed revaluation after the cut: %s", evaluate_us_filings(database))
        except Exception:
            logger.exception("US as-filed revaluation after the cut failed; the IR worker re-checks on its next poll")


def idle_until_wake(seconds: float, stale_sweep: ingestion_process.PeriodicReaper, *,
                    sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> None:
    """The loop's sleep, in naps no longer than the stale-run sweep's interval: between naps the sweep runs when due
    (at most hourly, admitted by the maintenance gate), so a run orphaned for 24 h is cleared while the worker idles."""
    deadline = clock() + seconds
    while (left := deadline - clock()) > 0:
        if stale_sweep.due():
            with job() as admitted:
                if admitted:
                    stale_sweep()
        sleep(min(left, max(5.0, stale_sweep.seconds_until_due())))


def main() -> None:
    with startup_job():
        settings = get_settings()
        init_sentry(settings, service_name="valuation-worker")
        database = Database(settings)
        database.initialize()
        # before any run of this process: the runs a previous process of this worker left 'running' (a deploy) are failed
        ingestion_process.reap_at_startup(database, ingestion_process.VALUATION_WORKER)
        # and, of any role or none, every run 'running' for more than 24 h — now and then hourly while idle (this worker only)
        stale_sweep = ingestion_process.PeriodicReaper(
            lambda: ingestion_process.reap_stale_safely(database, ingestion_process.VALUATION_WORKER))
        stale_sweep()
        push_notifications = PushNotificationService(settings, database)
        ensure_builtin_official_fundamentals(database)
        try:  # V3.2 rev 7 §7-bis Passo 0: records + first generation from the cycles already persisted (idempotent)
            from .valuation_official import bootstrap_official_selection
            bootstrap_official_selection(database)
        except Exception as exc:  # never blocks the worker: the next cycle records and activates by itself
            logger.warning("valuation_official bootstrap failed: %s", type(exc).__name__)
        investor_relations = InvestorRelationsService(settings, database)
        market_data = MarketDataService(settings, database)
        screener = B3ScreenerService(settings, database, market_data.http, nightly_cvm_shadow=True)  # the nightly cycle's producer
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
        v3_shadow = ValuationV3ShadowService(database)
        price_history = PriceHistoryService(settings, database, market_data.http)
        earnings_calendar = EarningsCalendarService(settings, database)
        cash_yield = R2D2CashYieldService(
            settings,
            database,
            _cash_yield_http_client(settings),
        )
        healthchecks = {
            "valuation": HealthcheckPing(settings.healthcheck_valuation_worker_url),
            CASH_YIELD_PHASE_KEY: HealthcheckPing(settings.healthcheck_cash_yield_url),
        }

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
            OffhoursPhase("v3_shadow", v3_shadow.last_run_at, v3_shadow.run_all),
            *((OffhoursPhase("price_history", price_history.last_run_at, price_history.run_all),)
              if settings.valuation_price_history_enabled else ()),  # V3.2 price series (rev 7 §2.2): dormant until the mesa enables it
            *((
                OffhoursPhase(
                    CASH_YIELD_PHASE_KEY,
                    cash_yield.last_run_at,
                    lambda: cash_yield.run_through(datetime.now(SAO_PAULO).date()),
                    start_hour=6,
                    end_hour=10,
                ),
            ) if settings.r2d2_cash_yield_accounting_enabled else ()),
            # Decisor V1 events: ONE EODHD whole-market earnings-calendar call, before the decisor reads it; dormant until the mesa enables it
            *((OffhoursPhase("earnings_calendar", earnings_calendar.last_run_at, earnings_calendar.run, max_failures=EARNINGS_CALENDAR_MAX_FAILURES),)
              if valuation_env.earnings_calendar_enabled() else ()),
            # Decisor V1 (migration 052): LAST, after the official cut and every existing phase — it never delays one; dormant until the mesa enables it
            # ...and only once the newest calendar is older than ε: one received inside the margin would be out of its read
            *((OffhoursPhase("decisor_shadow", lambda: decision_last_run_at(database), lambda: run_decisor_shadow(database, write=True),
                             not_before=lambda: decision_not_before(database)),)
              if valuation_env.decisor_shadow_enabled() else ()),
            # The valuation ensemble's LIVE producer (valuation_live_ensemble): after the price series and, last of all, after every
            # existing phase — it never delays one: it waits for a deferred decisor (ensemble_live_not_before), starts by 05:00 and
            # stops by 05:30 BRT, two attempts a night at most. Advisory (never pages); dormant until the mesa enables it; a retry
            # completes only the exchange still missing tonight
            *((OffhoursPhase("ensemble_live", lambda: ensemble_live_last_run_at(database),
                             lambda: run_ensemble_live(database, settings, market_data.http),
                             end_hour=ENSEMBLE_LIVE_LAST_START_HOUR, max_failures=ENSEMBLE_LIVE_MAX_FAILURES,
                             clock=lambda: datetime.now(SAO_PAULO),  # admitted on the clock of its own turn, never the pass's start
                             not_before=lambda: ensemble_live_not_before(
                                 database, now=datetime.now(SAO_PAULO), decisor_scheduled=valuation_env.decisor_shadow_enabled(),
                                 decisor_last_run_at=lambda: decision_last_run_at(database),
                                 decisor_not_before=lambda: decision_not_before(database))),)
              if valuation_env.ensemble_live_enabled() else ()),
        )

    while True:
        with job() as admitted:
            if not admitted:
                time.sleep(5)
                continue
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
                    asfiled_enabled=valuation_env.asfiled_enabled(),
                ),
                offhours_phases=offhours_phases,
                healthchecks=healthchecks,
                push_notifications=push_notifications,
            )

            now = datetime.now(SAO_PAULO)
            wake_at = result.next_wake_at
            logger.info("Next valuation-worker wake-up at %s", wake_at.isoformat())
        idle_until_wake(max(30, int((wake_at - now).total_seconds())), stale_sweep)


if __name__ == "__main__":
    main()
