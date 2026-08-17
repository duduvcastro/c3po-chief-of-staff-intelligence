import logging
import time
from datetime import datetime, time as wall_time, timedelta
from zoneinfo import ZoneInfo

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
        stream=EodhdRealtimeStream(settings.eodhd_api_token),
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

        sleep_seconds = max(30, int((next_midnight(datetime.now(SAO_PAULO)) - datetime.now(SAO_PAULO)).total_seconds()))
        logger.info("Next full valuation cycle at %s", next_midnight(datetime.now(SAO_PAULO)).isoformat())
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()
