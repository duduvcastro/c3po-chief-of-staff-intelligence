import logging
import time
from datetime import datetime, time as wall_time, timedelta
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


SAO_PAULO = ZoneInfo("America/Sao_Paulo")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("c3po.valuation_worker")


def start_of_today(now: datetime) -> datetime:
    return datetime.combine(now.date(), wall_time.min, tzinfo=SAO_PAULO)


def next_midnight(now: datetime) -> datetime:
    return start_of_today(now) + timedelta(days=1)


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
        if bootstrap_required or cycle_due:
            try:
                run_nightly(database, investor_relations, screener, us_screener)
            except Exception:
                logger.exception("Nightly valuation cycle failed; retrying in 15 minutes")
                time.sleep(15 * 60)
                continue

        # The Chewie fundamentals and Valuation V2.1 data snapshots refresh
        # once per day at 01:00 Sao Paulo, and ONLY inside the 01:00-08:00
        # pre-market window, so their provider calls never compete with
        # market-time API usage. A worker that comes up mid-day waits for the
        # next 01:00 slot.
        now = datetime.now(SAO_PAULO)
        offhours_due_at = start_of_today(now) + timedelta(hours=1)
        offhours_window_end = start_of_today(now) + timedelta(hours=8)
        chewie_last = chewie.last_refreshed_at()
        chewie_pending = chewie_last is None or chewie_last.astimezone(SAO_PAULO) < offhours_due_at
        v2_last = v2_data.last_refreshed_at()
        v2_pending = v2_last is None or v2_last.astimezone(SAO_PAULO) < offhours_due_at
        if offhours_due_at <= now < offhours_window_end:
            if chewie_pending:
                try:
                    chewie_counts = chewie.refresh_all(budget=settings.chewie_daily_symbol_budget)
                    logger.info("Chewie fundamentals daily snapshot complete: %s", chewie_counts)
                except Exception:
                    logger.exception("Chewie fundamentals snapshot failed; keeping the previous snapshot")
                chewie_pending = False
            if v2_pending:
                try:
                    v2_counts = v2_data.refresh_all()
                    logger.info("Valuation V2.1 data snapshot complete: %s", v2_counts)
                except Exception:
                    logger.exception("Valuation V2.1 data snapshot failed; keeping the previous snapshot")
                v2_pending = False

        now = datetime.now(SAO_PAULO)
        wake_targets = [next_midnight(now)]
        if (chewie_pending or v2_pending) and now < offhours_due_at:
            wake_targets.append(offhours_due_at)
        wake_at = min(wake_targets)
        logger.info("Next valuation-worker wake-up at %s", wake_at.isoformat())
        time.sleep(max(30, int((wake_at - now).total_seconds())))


if __name__ == "__main__":
    main()
