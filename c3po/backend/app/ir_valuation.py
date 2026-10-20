from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .database import Database
from .market_data.b3_screener import B3ScreenerService
from .valuation_asfiled import evaluate_us_filings
from .valuation_official import selection_frozen


logger = logging.getLogger(__name__)


class InvestorRelationsValuationProcessor:
    """Apply new official disclosures to every shared valuation surface."""

    def __init__(self, database: Database, b3_screener: B3ScreenerService, *, asfiled_enabled: bool = False) -> None:
        self.database = database
        self.b3_screener = b3_screener
        # Valuation as-filed (owner 2026-10-17, C3PO_VALUATION_ASFILED_ENABLED): the US revaluation trigger
        self.asfiled_enabled = asfiled_enabled

    def process(self, limit: int = 12) -> dict[str, Any]:
        # While the mesa freezes the official selection (Valuation P1, F1) nothing is claimed: a republished B3 universe could
        # not be activated over the frozen head and the mesa's order would then hold it. The queue keeps every update; the
        # first poll after the order (or the freeze's end) applies them. The US as-filed trigger still runs: it only appends
        # staleness marks (migration 053) judged against the head in force and never activates a generation.
        freeze = selection_frozen(self.database)
        if freeze is not None:
            logger.info("Investor Relations valuation propagation deferred: the official selection is frozen until %s", freeze["until"])
            return {"claimed": 0, "updated": [], "targeted_only": [], "failed": [], "deferred_until": freeze["until"], **self._us_revaluation_trigger()}
        updates = self.database.claim_ir_valuation_updates(limit)
        if not updates:
            return {"claimed": 0, "updated": [], "targeted_only": [], "failed": [], **self._us_revaluation_trigger()}

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
            **self._us_revaluation_trigger(),
        }

    def _us_revaluation_trigger(self) -> dict[str, Any]:
        """Valuation as-filed: an accepted 10-Q/10-K or 8-K item 2.02 of the US valuation universe (registered by the SEC
        as-filed poll with its header clock) marks the official US TP stale and queues it for the next nightly cut;
        the cut that revalues it clears the mark (valuation_asfiled.evaluate_us_filings, migration 053). Off by default;
        a failure here never blocks the B3 propagation above."""
        if not self.asfiled_enabled:
            return {}
        try:
            return {"us_revaluation": evaluate_us_filings(self.database, now=datetime.now(timezone.utc))}
        except Exception as exc:
            logger.exception("US as-filed revaluation trigger failed")
            return {"us_revaluation": {"error": type(exc).__name__}}
