"""Explicit split-only quantity basis for the personal portfolio, not market feeds.

AMZN starts split-adjusted trading on 2022-06-06 (SEC 2022-03-09 8-K).
The owner's historical quantities may already use post-split units. Never use
adjusted_close here: provider adjustments can also include cash dividends.
"""
from datetime import date
from decimal import Decimal

# Owner confirmed only historical AMZN quantities are restated (2026-09-26).
# Fable review: issue #348, comment 5842083445. No other symbol is inferred.
OWNER_CONFIRMED_RESTATED = frozenset({"AMZN"})

AMZN_SPLIT_DAY = date(2022, 6, 6)
AMZN_FACTOR = Decimal(20)


def historical_price(symbol, observed, close, events, adjusted_symbols):
    if symbol != "AMZN":
        return close
    # Current-day valuation does not call this function. Post-split history
    # already has the right units regardless of the historical declaration.
    if observed >= AMZN_SPLIT_DAY:
        return close
    explicit = [e for e in events if e["symbol"] == symbol and e["kind"] == "split"
                and str(e["effective_date"]) == AMZN_SPLIT_DAY.isoformat()]
    if symbol in adjusted_symbols:
        if explicit:
            raise ValueError("Conflicting split quantity bases")
        return close / AMZN_FACTOR
    # Original-unit ledgers require the matching corporate action. Otherwise
    # the basis is unknown: suppress the historical result instead of guessing.
    if len(explicit) != 1 or Decimal(str(explicit[0]["quantity"])) / Decimal(str(explicit[0].get("split_denominator", "1"))) != AMZN_FACTOR:
        raise ValueError("Historical AMZN quantity basis requires confirmation")
    return close
