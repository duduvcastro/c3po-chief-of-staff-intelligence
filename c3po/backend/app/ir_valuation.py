from __future__ import annotations

import logging
from typing import Any

from .database import Database
from .market_data.b3_screener import B3ScreenerService


logger = logging.getLogger(__name__)


class InvestorRelationsValuationProcessor:
    """Apply new official disclosures to every shared valuation surface."""

    def __init__(self, database: Database, b3_screener: B3ScreenerService) -> None:
        self.database = database
        self.b3_screener = b3_screener

    def process(self, limit: int = 12) -> dict[str, Any]:
        updates = self.database.claim_ir_valuation_updates(limit)
        if not updates:
            return {"claimed": 0, "updated": [], "targeted_only": [], "failed": []}

        b3_updates = [item for item in updates if item["market"] == "B3"]
        other_updates = [item for item in updates if item["market"] != "B3"]
        updated: list[str] = []
        targeted_only: list[str] = []
        failed: list[str] = []
        if b3_updates:
            try:
                result = self.b3_screener.refresh_symbols([item["symbol"] for item in b3_updates])
                failed_symbols = set(result["missing"])
                succeeded = [item for item in b3_updates if item["symbol"] not in failed_symbols]
                failed_updates = [item for item in b3_updates if item["symbol"] in failed_symbols]
                self.database.finish_ir_valuation_updates(
                    succeeded,
                    succeeded=True,
                    incorporate_events=True,
                )
                self.database.finish_ir_valuation_updates(
                    failed_updates,
                    succeeded=False,
                    error="The official event was stored, but the market-data providers did not return a valuation row.",
                )
                updated.extend(result["updated"])
                targeted_only.extend(result["targeted_only"])
                failed.extend(result["missing"])
            except Exception as exc:
                logger.exception("Investor Relations valuation propagation failed")
                self.database.finish_ir_valuation_updates(b3_updates, succeeded=False, error=str(exc))
                failed.extend(item["symbol"] for item in b3_updates)

        # US events are retained for One Pager/SEC freshness. The current shared
        # Candidate and Matrix surfaces are B3-only, so there is no US snapshot to republish.
        self.database.finish_ir_valuation_updates(other_updates, succeeded=True)
        return {
            "claimed": len(updates),
            "updated": sorted(set(updated)),
            "targeted_only": sorted(set(targeted_only)),
            "failed": sorted(set(failed)),
        }
