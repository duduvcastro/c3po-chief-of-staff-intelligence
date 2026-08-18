from __future__ import annotations

from app.config import Settings
from app.database import Database
from app.r2d2 import R2D2PaperService


def _settings() -> Settings:
    return Settings(
        database_url="",
        r2d2_start_date="2026-08-17",
        r2d2_checkpoint_days=90,
        r2d2_starting_capital_usd=1_000_000,
    )


def _service() -> R2D2PaperService:
    settings = _settings()
    return R2D2PaperService(settings, Database(settings), None, None, None)  # type: ignore[arg-type]


def test_finish_cycle_persists_scan_funnel_metadata() -> None:
    """The shortlist/review funnel (universe -> eligible -> shortlisted -> reviewed)
    was previously only ever held in an in-memory dict, overwritten every cycle and
    never queryable -- there was no way to check whether the 300/50 shortlist cap or
    the 16-24 technical-review cap were actually excluding good candidates. This
    persists it so the question can be answered from real accumulated data instead
    of guessed at.
    """
    service = _service()
    experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(experiment["id"], ["NASDAQ", "NYSE"])
    funnel = {
        "NASDAQ": {
            "universe_count": 4200, "quoted_count": 4100, "missing_quote_count": 100,
            "tradeable_count": 1800, "stock_count": 1700, "etf_count": 100,
            "deep_shortlist_count": 350,
        },
        "NYSE": {
            "universe_count": 3100, "quoted_count": 3050, "missing_quote_count": 50,
            "tradeable_count": 1200, "stock_count": 1150, "etf_count": 50,
            "deep_shortlist_count": 350,
        },
    }

    service.repo.finish_cycle(cycle_id, "succeeded", 7300, 2, 1, metadata={"scan_funnel": funnel})

    stored = next(row for row in service.repo.memory["cycles"] if row["id"] == cycle_id)
    assert stored["status"] == "succeeded"
    assert stored["metadata"]["scan_funnel"]["NASDAQ"]["deep_shortlist_count"] == 350
    assert stored["metadata"]["scan_funnel"]["NYSE"]["tradeable_count"] == 1200


def test_finish_cycle_defaults_metadata_to_empty_dict_when_not_provided() -> None:
    service = _service()
    experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(experiment["id"], ["NASDAQ"])

    service.repo.finish_cycle(cycle_id, "market_closed", 0, 0, 0)

    stored = next(row for row in service.repo.memory["cycles"] if row["id"] == cycle_id)
    assert stored["metadata"] == {}
