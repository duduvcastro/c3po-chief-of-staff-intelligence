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

The ensemble switch (built before the PIT grid reports, merged only after its PASS and the owner's acceptance): a THIRD official
source, ``official_ensemble_v1`` — the SAME producer cycles, the record ``tp`` being the row's ``ensemble_tp``. The owner-facing
decisions (28/10/2026) live in ONE place, ``ENSEMBLE_POLICY``: (a) B3 stays on its internal TP; (b) the ensemble buy-in is the
internal buy-in's rule applied to the ensemble TP (``official_ensemble_buy_in_v1``: ``official_buy_in_v1`` over the one TP, with
the internal entry hurdle ``official_entry_discount_v1`` of the same row); (c) the valuation covers EVERY US name: a stock of
NASDAQ/NYSE that the nightly live producer (``valuation_live_ensemble``) evaluated with ``origin = "ensemble"`` in a fresh
snapshot takes the ensemble's primary TP, whether or not it is in the PIT-tested population — the producer's ``pit_tested`` flag
travels on the row (``ensemble_pit_tested``) so the screens label the untested names and no buy permission is granted on them
(``valuation_official.ensemble_untested``; ``require_pit_tested = True`` would restrict the TP itself to the tested names). Every
other row (B3, ETFs, a name the producer could not evaluate, a missing or stale snapshot) carries its internal TP and internal view
unchanged (``ensemble_fallback_view``, ``ensemble_origin = "fallback_internal:<reason>"``). ``ensemble_consensus_weight_v1`` is
the weight the consensus carries inside the primary (one equal-weight value of a min/max-trimmed mean), the record's
``consensus_weight_percent``.
"""
from __future__ import annotations

import copy
import statistics
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

ENGINE_VERSION = "official_blend_v1"
SOURCE_BLEND = ENGINE_VERSION  # Passo 0: the internal TP blended with the consensus
SOURCE_INTERNAL = "official_internal_v1"  # Passo 1: the internal TP alone (consensus_weight = 0), consensus persisted beside
SOURCE_ENSEMBLE = "official_ensemble_v1"  # the ensemble's primary TP for the US tested population, the internal TP elsewhere (ENSEMBLE_POLICY)
OFFICIAL_SOURCES: tuple[str, ...] = (SOURCE_BLEND, SOURCE_INTERNAL, SOURCE_ENSEMBLE)
ENSEMBLE_FALLBACK_PREFIX = "fallback_internal:"  # ensemble_origin of a row that carries its internal TP: "fallback_internal:<reason>"
ENSEMBLE_ORIGIN = "ensemble"  # ensemble_origin of a row that carries the ensemble's primary TP (the live producer's own origin label)
ENSEMBLE_MIRRORED_FIELDS: tuple[str, ...] = (  # internal_<field> → ensemble_<field> on a fallback row: the internal TP and its whole view
    "tp", "buy_in", "buy_in_models", "bear_tp", "bull_tp", "upside_percent", "price_vs_buy_in_percent", "expected_total_return_percent",
    "convergence_weight", "score", "tp_validation_status", "tp_validation_reasons", "status",
)


@dataclass(frozen=True)
class EnsemblePolicy:
    """The owner-facing decisions of the ensemble switch, as defaults in ONE place (the producers and the receipt read them
    from ``ENSEMBLE_POLICY``; a test pins the live-producer constants they mirror)."""
    markets: tuple[str, ...] = ("NASDAQ", "NYSE")  # (a)/(c) the ensemble serves the US only: B3 always carries its internal TP
    security_types: tuple[str, ...] = ("Stock",)  # ETFs carry their internal TP (the live producer does not evaluate them)
    require_pit_tested: bool = False  # (c) owner 28/10: every evaluated US name takes the ensemble TP; True → only pit_tested names (the rest fall back)
    live_analysis_type: str = "valuation_ensemble_live"  # = valuation_live_ensemble.ANALYSIS_TYPE (pinned by test)
    live_schema: str = "VALUATION-ENSEMBLE-LIVE-v2"  # = valuation_live_ensemble.SCHEMA
    primary_variant: str = "minmax_trimmed_mean_with_consensus"  # = valuation_live_ensemble.PRIMARY (the signed grid's primary)
    max_snapshot_age: timedelta = timedelta(hours=96)  # older than this at the build → every name falls back (a weekend and a holiday fit)
    buy_in_rule: str = "official_buy_in_v1((ensemble_tp,), official_entry_discount_v1('US', risk_score, valuation_confidence), ensemble_tp)"  # (b)

    def receipt(self) -> dict[str, Any]:
        """The policy as the before/after receipt names it (JSON-ready, deterministic)."""
        return {"markets": list(self.markets), "security_types": list(self.security_types), "require_pit_tested": self.require_pit_tested,
                "untested_buy_permitted": False, "live_analysis_type": self.live_analysis_type,
                "live_schema": self.live_schema, "primary_variant": self.primary_variant,
                "max_snapshot_age_hours": self.max_snapshot_age.total_seconds() / 3600, "buy_in_rule": self.buy_in_rule,
                "origin": ENSEMBLE_ORIGIN, "fallback_prefix": ENSEMBLE_FALLBACK_PREFIX}


ENSEMBLE_POLICY = EnsemblePolicy()


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


def official_ensemble_buy_in_v1(ensemble_tp: float, entry_discount: float) -> float:
    """(b) The ensemble buy-in: the internal buy-in's rule — ``official_buy_in_v1`` (the mean of the TP values discounted by
    the entry hurdle, capped at 90 % of the TP) — applied to the ONE ensemble TP, with the entry hurdle the producer applies to
    the internal TP of the same row (``official_entry_discount_v1``). Over one value the mean of the discounts is the discount
    of the TP, exactly as the internal buy-in is the discount of the internal method mean: ``min(tp / (1 + d), 0.90 × tp)``."""
    return official_buy_in_v1((float(ensemble_tp),), entry_discount, float(ensemble_tp))


def ensemble_consensus_weight_v1(model_values: Iterable[float], consensus: float | None) -> float:
    """The weight the consensus carries inside the ensemble's primary (``minmax_trimmed_mean_with_consensus`` of the signed
    grid: the evaluated model values and the consensus as ONE more equal-weight value, sorted, exactly one value removed at
    each tail, the mean of the rest). The aggregation sorts ``values + [consensus]`` stably, so among equal values the
    consensus comes last: its position is the count of model values ``≤`` it. Retained (not the first nor the last) → ``1 /
    retained``; trimmed, or no consensus → 0. Called only for an evaluated primary (≥ 3 values before trimming); a test pins it
    to ``valuation_ensemble_aggregation.aggregate_grid_variants``."""
    values = [float(value) for value in model_values]
    if consensus is None:
        return 0.0
    size = len(values) + 1
    if size < 3:
        raise ValueError("an evaluated primary has at least three values before trimming")
    position = sum(value <= float(consensus) for value in values)
    return 1.0 / (size - 2) if 1 <= position <= size - 2 else 0.0


def ensemble_fallback_view(row: Mapping[str, Any], reason: str) -> dict[str, Any]:
    """(a) The ensemble fields of a row OUTSIDE the tested population (B3, an ETF, a name the live producer did not evaluate, a
    missing or stale snapshot): its internal TP and its whole internal view, copied — ``ensemble_<field>`` = ``internal_<field>``
    for every ``ENSEMBLE_MIRRORED_FIELDS`` field the row carries — the internal record's consensus weight (0) and ``ensemble_origin
    = "fallback_internal:<reason>"`` (``ensemble_pit_tested`` null: the TP served is not the ensemble's). The ensemble record of such
    a row is the internal record's numbers, bit for bit."""
    view = {f"ensemble_{field}": copy.deepcopy(row[f"internal_{field}"]) for field in ENSEMBLE_MIRRORED_FIELDS if f"internal_{field}" in row}
    view.update({"ensemble_consensus_weight_percent": 0.0, "ensemble_origin": ENSEMBLE_FALLBACK_PREFIX + str(reason), "ensemble_pit_tested": None})
    return view
