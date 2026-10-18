"""The SEC contact and pace, and the switches of the as-filed and decisor fronts — read from the environment, NOT
``Settings``.

``config.py`` is hashed into the R2D2 V2 implementation package (``r2d2_v2_earnings_package.PACKAGE_FILES``): a field
added there changes ``implementation_package_sha``, so the signed release, the shadow collector
(``COLLECTOR_IMPLEMENTATION_PACKAGE_MISMATCH``), the capacity bootstrap (``CAPACITY_CONFIG_PACKAGE``) and the live
policy refuse a build that is otherwise unchanged for R2D2. These values are therefore read here, at call time, as the
CVM statements front (``official_statements``) and the R2D2 V2 producers read theirs. Docker's ``env_file`` puts the
host's values in the process environment; every process reads the same names it would have read through ``Settings``.

| variable | default | read by |
|---|---|---|
| ``C3PO_SEC_CONTACT`` | empty (no SEC header or as-filed call) | ``sec_xbrl.SecXbrlClient`` (User-Agent) |
| ``C3PO_SEC_MAX_REQUESTS_PER_SECOND`` | 2.5 (0 < rate ≤ 8) | the per-process SEC limiter |
| ``C3PO_VALUATION_ASFILED_ENABLED`` | off | IR worker poll, IR valuation trigger, nightly cut, US producer shadow hook |
| ``C3PO_VALUATION_ASFILED_BACKFILL_ISSUERS_PER_POLL`` | 10 (0 to 200) | the as-filed poll's backfill |
| ``C3PO_VALUATION_DECISOR_SHADOW`` | off | the decisor's nightly phase, its writes and the phase health |

A value that does not parse falls back to the default (a switch: off); a number outside its range is clamped into it.
The contact is never logged or put in a ``repr``.
"""
from __future__ import annotations

import math
import os

SEC_CONTACT_ENV = "C3PO_SEC_CONTACT"
SEC_MAX_REQUESTS_PER_SECOND_ENV = "C3PO_SEC_MAX_REQUESTS_PER_SECOND"
ASFILED_ENABLED_ENV = "C3PO_VALUATION_ASFILED_ENABLED"
ASFILED_BACKFILL_ENV = "C3PO_VALUATION_ASFILED_BACKFILL_ISSUERS_PER_POLL"
DECISOR_SHADOW_ENV = "C3PO_VALUATION_DECISOR_SHADOW"
ENVIRONMENT_NAMES: tuple[str, ...] = (SEC_CONTACT_ENV, SEC_MAX_REQUESTS_PER_SECOND_ENV, ASFILED_ENABLED_ENV, ASFILED_BACKFILL_ENV, DECISOR_SHADOW_ENV)

# SEC fair access is at most 8 requests/second from the HOST and three processes call EDGAR (the API — One Pager and
# /investor-relations/sync —, the Investor Relations worker and the nightly valuation worker): 3 × 2.5 = 7.5 ≤ 8.
SEC_MAX_REQUESTS_PER_SECOND_DEFAULT = 2.5
SEC_MAX_REQUESTS_PER_SECOND_CEILING = 8.0
ASFILED_BACKFILL_DEFAULT = 10
ASFILED_BACKFILL_RANGE = (0, 200)
_TRUE = frozenset({"1", "true", "t", "yes", "y", "on"})  # the spellings pydantic reads as true; anything else is off


def _switch(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE


def sec_contact() -> str:
    """The SEC fair-access contact configured on the host (never committed), stripped; empty when not configured."""
    return os.environ.get(SEC_CONTACT_ENV, "").strip()


def sec_max_requests_per_second() -> float:
    """The per-process SEC pace: the default when unset, unparseable, not finite or not positive; at most 8/s."""
    try:
        rate = float(os.environ.get(SEC_MAX_REQUESTS_PER_SECOND_ENV, "").strip() or SEC_MAX_REQUESTS_PER_SECOND_DEFAULT)
    except ValueError:
        return SEC_MAX_REQUESTS_PER_SECOND_DEFAULT
    if not math.isfinite(rate) or rate <= 0:
        return SEC_MAX_REQUESTS_PER_SECOND_DEFAULT
    return min(rate, SEC_MAX_REQUESTS_PER_SECOND_CEILING)


def asfiled_enabled() -> bool:
    """Valuation as-filed (owner 2026-10-17): SEC XBRL statement vintages, new-filing detection for the US valuation
    universe, the as-of bridge with its shadow reconciliation and the US revaluation trigger. Off by default: nothing is
    fetched and no served number changes."""
    return _switch(ASFILED_ENABLED_ENV)


def asfiled_backfill_issuers_per_poll() -> int:
    """Issuers per as-filed poll whose newest original 10-Q/10-K has no stored fact (backfill and gap repair)."""
    low, high = ASFILED_BACKFILL_RANGE
    try:
        count = int(os.environ.get(ASFILED_BACKFILL_ENV, "").strip() or ASFILED_BACKFILL_DEFAULT)
    except ValueError:
        return ASFILED_BACKFILL_DEFAULT
    return min(max(count, low), high)


def decisor_shadow_enabled() -> bool:
    """Valuation Decisor V1 (migration 052): off by default; the nightly shadow phase records verdicts only when the mesa
    enables it."""
    return _switch(DECISOR_SHADOW_ENV)
