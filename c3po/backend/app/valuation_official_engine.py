"""The official target-price engine of Passo 0 (`tp_source = official_blend_v1`) — the producer's arithmetic, isolated.

These are the exact formulas the official producers (the screeners, through the One Pager framework in PRODUCER role)
use today. They live here so that (1) no consumer module contains TP arithmetic, (2) the CI sweep can name the only
place where a TP may be computed, and (3) Passo 1 (`official_internal_v1`: consensus out) and Passo 3 (removal) are
one-line, audited changes. Nothing here reads or writes storage.

Passo 1 (spec rev 7 §7.5 item 5, §7-bis item 4): a SECOND official source, ``official_internal_v1`` — the SAME producer
cycles, the record ``tp`` being the producer's INTERNAL TP (``consensus_weight = 0``) and its ``buy_in`` derived from
that TP by the producer's own entry rule. ``official_entry_discount_v1`` is the literal mirror of the entry hurdle the
pinned One Pager applies in producer role (``one_pager.py``, pinned by hash — never edited): the US screener uses it to
derive the internal buy-in of a stock; the proof that the mirror is exact is a test on the producer itself.
"""
from __future__ import annotations

import statistics
from typing import Iterable

ENGINE_VERSION = "official_blend_v1"
SOURCE_BLEND = ENGINE_VERSION  # Passo 0: the internal TP blended with the consensus
SOURCE_INTERNAL = "official_internal_v1"  # Passo 1: the internal TP alone (consensus_weight = 0), consensus persisted beside
OFFICIAL_SOURCES: tuple[str, ...] = (SOURCE_BLEND, SOURCE_INTERNAL)


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


def official_entry_discount_v1(market: str, risk_score: float, confidence: float) -> float:
    """The entry hurdle of the One Pager framework in PRODUCER role — mirrored literally from the pinned ``one_pager.py``
    (``required_return + risk_score / 100 * 0.11 + (100 - confidence) / 100 * 0.06``; ``required_return`` 0.12 for US,
    0.20 otherwise). Passo 1 uses it to derive the internal buy-in of a US stock from the internal TP with the SAME rule
    the producer applied to the blend; the constants are duplicated here until Passo 3 removes the producer's copy, and a
    test on the producer proves the mirror reproduces ``analysis["buy_in"]`` bit for bit."""
    required_return = 0.12 if market == "US" else 0.20
    return required_return + float(risk_score) / 100 * 0.11 + (100 - float(confidence)) / 100 * 0.06


def foreign_bridge_tp_v1(method_values: Iterable[float]) -> float:
    """Primary-listing bridge: the registered internal method targets of the foreign listing, averaged."""
    return statistics.mean(float(value) for value in method_values)
