from __future__ import annotations


VALUATION_WORKER_SOURCE_TYPE = "valuation_worker"

VALUATION_WORKER_PHASES: dict[str, dict[str, str]] = {
    "canonical": {
        "code": "valuation-worker-canonical",
        "name": "Valuation canonical cycle",
    },
    "chewie": {
        "code": "valuation-worker-chewie",
        "name": "Chewie fundamentals cycle",
    },
    "v2_data": {
        "code": "valuation-worker-v2-data",
        "name": "Valuation V2.1 data cycle",
    },
    "shadow": {
        "code": "valuation-worker-v2-shadow",
        "name": "Valuation V2 shadow cycle",
    },
    "peer_quality": {
        "code": "valuation-worker-peer-quality",
        "name": "Valuation V2.1b peer-quality cycle",
    },
    "v3_shadow": {
        "code": "valuation-worker-v3-shadow",
        "name": "Valuation V3 shadow cycle",
    },
    "cash_yield": {
        "code": "valuation-worker-r2d2-cash-yield",
        "name": "R2D2 cash-yield accounting cycle",
    },
    "price_history": {
        "code": "valuation-worker-price-history",
        "name": "Valuation V3.2 price series cycle",
    },
    "earnings_calendar": {
        "code": "valuation-worker-earnings-calendar",
        "name": "Valuation earnings calendar cycle",
    },
    "decisor_shadow": {
        "code": "valuation-worker-decisor-shadow",
        "name": "Valuation decisor V1 shadow cycle",
    },
    "ensemble_live": {
        "code": "valuation-worker-ensemble-live",
        "name": "Valuation ensemble live producer cycle",
    },
}

VALUATION_WORKER_CANONICAL_PHASE = "canonical"
# phases whose failure never pages (no job_failure push, no failed worker check) and never turns the health card offline:
# their consumers tolerate their absence (the Decisor V1 falls back to the 051 estimate when the calendar is missing; the live
# ensemble producer has no consumer until the signed grid passes and the owner switches)
VALUATION_WORKER_ADVISORY_PHASES = ("earnings_calendar", "ensemble_live")
VALUATION_WORKER_OFFHOURS_PHASES = (
    "chewie",
    "v2_data",
    "shadow",
    "peer_quality",
    "v3_shadow",
    "cash_yield",
)
