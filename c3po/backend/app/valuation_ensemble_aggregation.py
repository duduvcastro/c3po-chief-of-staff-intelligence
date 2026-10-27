"""Six explicit variants; the consensus is one equally weighted source, never an anchor."""
from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any

from .valuation_ensemble_inputs import NotEvaluable, number
from .valuation_ensemble_models import ModelValue


PRIMARY_VARIANT = "median_with_consensus"
GRID_PRIMARY_VARIANT = "minmax_trimmed_mean_with_consensus"
MIN_MODELS = 3
GRID_VARIANT_IDS = tuple(f"{method}_{suffix}" for suffix in ("without_consensus", "with_consensus")
                         for method in ("mean", "median", "trimmed_mean_20", "minmax_trimmed_mean"))


def aggregate_variants(models: tuple[ModelValue, ...], consensus: float | None) -> dict[str, Any]:
    ids = [x.model for x in models]
    if len(ids) != len(set(ids)):
        raise NotEvaluable("duplicate_model_identity")
    values = []
    for model in models:
        if model.status == "evaluated":
            value = number(model.value, model.model)
            if value <= 0:
                raise NotEvaluable("model_value_not_positive")
            values.append(value)
        elif model.status != "not_evaluable" or model.value is not None or not model.reason:
            raise NotEvaluable("inconsistent_model_result")
    if consensus is not None and number(consensus, "consensus") <= 0:
        raise NotEvaluable("consensus_not_positive")
    variants = {}
    for with_consensus in (False, True):
        suffix = "with_consensus" if with_consensus else "without_consensus"
        sample = sorted(values + ([float(consensus)] if with_consensus and consensus is not None else []))
        reason = "consensus_unavailable" if with_consensus and consensus is None else "no_fundamental_model" if not values else None
        for method in ("mean", "median", "trimmed_mean_20"):
            # Construction convention: floor(20% * n) observations removed from EACH tail.
            # For n<5 that removes zero; receipt makes this visible for review before prereg.
            k = len(sample) // 5 if method == "trimmed_mean_20" else 0
            retained = sample[k:len(sample)-k] if k else sample
            value = None
            if reason is None:
                if method == "median":
                    middle = len(retained) // 2
                    value = retained[middle] if len(retained) % 2 else retained[middle-1] / 2 + retained[middle] / 2
                else:
                    value = math.fsum(x / len(retained) for x in retained)
            variants[f"{method}_{suffix}"] = {"status": "not_evaluable" if reason else "evaluated", "reason": reason,
                "value": value, "fundamental_models": len(values), "consensus_included": with_consensus and consensus is not None,
                "sample_size": len(sample), "trimmed_each_tail": k, "retained_count": len(retained)}
    return {"primary": PRIMARY_VARIANT, "variants": variants, "models": [asdict(x) for x in models],
            "construction_policy": {"model_weight": "one_equal_weight_per_evaluable_model",
                                    "consensus_weight": "one_additional_source_equal_to_one_model",
                                    "trimmed_mean_20": "floor(n*0.20)_from_each_tail",
                                    "missing_consensus": "with_consensus_variants_not_evaluable",
                                    "signed_prereg": False, "horizon_selected": False}}


def aggregate_grid_variants(models: tuple[ModelValue, ...], consensus: float | None, *,
                            consensus_reason: str | None = None) -> dict[str, Any]:
    """The eight variants of the signed rev1 protocol; separate from construction shadow.

    MIN_MODELS counts values before trimming, including the single consensus value.
    A missing consensus leaves the with-consensus variant on fundamental values only,
    with the missingness published. Exactly one observation is removed at each tail by
    minmax, even when several observations share that minimum or maximum.
    """
    if len({model.model for model in models}) != len(models):
        raise NotEvaluable("duplicate_model_identity")
    values: list[float] = []
    for model in models:
        if model.status == "evaluated":
            try:
                value = number(model.value, model.model)
            except OverflowError as exc:
                raise NotEvaluable(f"invalid_number:{model.model}") from exc
            if value <= 0:
                raise NotEvaluable("model_value_not_positive")
            values.append(value)
        elif model.status != "not_evaluable" or model.value is not None or not model.reason:
            raise NotEvaluable("inconsistent_model_result")
    if consensus is not None:
        try:
            consensus = number(consensus, "consensus")
        except OverflowError as exc:
            raise NotEvaluable("invalid_number:consensus") from exc
        if consensus <= 0:
            raise NotEvaluable("consensus_not_positive")
        if consensus_reason is not None:
            raise NotEvaluable("evaluated_consensus_has_missing_reason")
    elif consensus_reason is None:
        consensus_reason = "unavailable"
    if consensus_reason is not None and (not isinstance(consensus_reason, str) or not consensus_reason):
        raise NotEvaluable("invalid_consensus_missing_reason")
    variants: dict[str, Any] = {}
    for with_consensus in (False, True):
        suffix = "with_consensus" if with_consensus else "without_consensus"
        included = with_consensus and consensus is not None
        sample = sorted(values + ([consensus] if included and consensus is not None else []))
        reason = "ensemble_fewer_than_min_models" if len(sample) < MIN_MODELS else None
        for method in ("mean", "median", "trimmed_mean_20", "minmax_trimmed_mean"):
            k = 1 if method == "minmax_trimmed_mean" and len(sample) >= MIN_MODELS else len(sample) // 5 if method == "trimmed_mean_20" else 0
            retained = sample[k:len(sample)-k] if k else sample
            value = None
            if reason is None:
                if method == "median":
                    middle = len(retained) // 2
                    value = retained[middle] if len(retained) % 2 else retained[middle-1] / 2 + retained[middle] / 2
                else:
                    value = math.fsum(x / len(retained) for x in retained)
            variants[f"{method}_{suffix}"] = {
                "status": "not_evaluable" if reason else "evaluated", "reason": reason, "value": value,
                "fundamental_models": len(values), "consensus_included": included,
                "consensus_reason": f"consensus:{consensus_reason}" if with_consensus and consensus is None else None,
                "sample_size": len(sample), "trimmed_each_tail": k, "retained_count": len(retained),
            }
    return {"primary": GRID_PRIMARY_VARIANT, "variants": variants, "models": [asdict(model) for model in models],
            "grid_aggregation_policy": {"minimum_values_before_trimming": MIN_MODELS,
                "model_weight": "one_equal_weight_per_evaluable_model",
                "consensus_weight": "one_additional_source_equal_to_one_model",
                "minmax_trimmed_mean": "exactly_one_observation_from_each_tail",
                "trimmed_mean_20": "floor(n*0.20)_from_each_tail",
                "missing_consensus": "use_fundamental_models_only_and_count_reason"}}
