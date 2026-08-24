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
}

VALUATION_WORKER_CANONICAL_PHASE = "canonical"
VALUATION_WORKER_OFFHOURS_PHASES = (
    "chewie",
    "v2_data",
    "shadow",
    "peer_quality",
)
