"""The official target-price engine of Passo 0 (`tp_source = official_blend_v1`) — the producer's arithmetic, isolated.

These are the exact formulas the official producers (the screeners, through the One Pager framework in PRODUCER role)
use today. They live here so that (1) no consumer module contains TP arithmetic, (2) the CI sweep can name the only
place where a TP may be computed, and (3) Passo 1 (`official_internal_v1`: consensus out) and Passo 3 (removal) are
one-line, audited changes. Nothing here reads or writes storage.
"""
from __future__ import annotations

import statistics
from typing import Iterable

ENGINE_VERSION = "official_blend_v1"


def official_blend_v1(internal_tp: float, consensus: float | None, consensus_weight: float) -> float:
    """The Passo 0 official TP: the internal framework TP blended with a well-covered consensus by ``consensus_weight``
    (0 when there is no usable consensus). Passo 1 sets the weight to 0 for the official source."""
    if consensus is None or consensus_weight <= 0:
        return float(internal_tp)
    return float(internal_tp) * (1 - consensus_weight) + float(consensus) * consensus_weight


def official_buy_in_v1(method_values: Iterable[float], entry_discount: float, tp: float) -> float:
    """Disciplined buy-in: the mean of the framework methods discounted by the entry hurdle, capped at 90 % of the TP."""
    values = [float(value) for value in method_values]
    buy_in = statistics.mean(value / (1 + entry_discount) for value in values)
    return min(buy_in, float(tp) * 0.90)


def foreign_bridge_tp_v1(method_values: Iterable[float]) -> float:
    """Primary-listing bridge: the registered internal method targets of the foreign listing, averaged."""
    return statistics.mean(float(value) for value in method_values)
