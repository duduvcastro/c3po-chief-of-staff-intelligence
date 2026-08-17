from datetime import datetime
from zoneinfo import ZoneInfo

from app.valuation_worker import next_midnight, start_of_today


SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def test_worker_uses_sao_paulo_midnight() -> None:
    now = datetime(2026, 8, 6, 23, 58, 45, tzinfo=SAO_PAULO)

    assert start_of_today(now) == datetime(2026, 8, 6, 0, 0, tzinfo=SAO_PAULO)
    assert next_midnight(now) == datetime(2026, 8, 7, 0, 0, tzinfo=SAO_PAULO)
