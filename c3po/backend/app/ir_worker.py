import logging
import time
from datetime import datetime, timedelta, timezone

from .config import get_settings
from .database import Database
from .investor_relations import InvestorRelationsService
from .ir_valuation import InvestorRelationsValuationProcessor
from .market_data.b3_screener import B3ScreenerService
from .market_data.service import MarketDataService
from .observability import init_sentry


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("c3po.ir_worker")


def main() -> None:
    settings = get_settings()
    init_sentry(settings, service_name="investor-relations-worker")
    database = Database(settings)
    database.initialize()
    service = InvestorRelationsService(settings, database)
    market_data = MarketDataService(settings, database)
    valuation_processor = InvestorRelationsValuationProcessor(
        database,
        B3ScreenerService(settings, database, market_data.http),
    )
    next_cvm = datetime.min.replace(tzinfo=timezone.utc)
    next_ri = datetime.min.replace(tzinfo=timezone.utc)
    while True:
        now = datetime.now(timezone.utc)
        sources = ["sec"]
        if now >= next_cvm:
            sources.insert(0, "cvm")
            next_cvm = now + timedelta(minutes=max(settings.investor_relations_cvm_poll_minutes, 30))
        if now >= next_ri:
            sources.append("ri")
            next_ri = now + timedelta(minutes=max(settings.investor_relations_ri_poll_minutes, 30))
        for source in sources:
            result = service.sync(source)
            logger.info("Investor Relations %s sync: %s", source, result.sources.get(source))
            propagation = valuation_processor.process()
            if propagation["claimed"]:
                logger.info("Investor Relations valuation propagation: %s", propagation)
        time.sleep(max(settings.investor_relations_poll_minutes, 5) * 60)


if __name__ == "__main__":
    main()
