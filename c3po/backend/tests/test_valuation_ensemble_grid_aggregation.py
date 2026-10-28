"""Signed rev1 aggregation witnesses; independent from legacy construction shadow."""
from itertools import permutations
import math

import pytest

from app.valuation_ensemble_aggregation import (
    GRID_PRIMARY_VARIANT, GRID_VARIANT_IDS, MIN_MODELS, aggregate_grid_variants, aggregate_variants,
)
from app.valuation_ensemble_inputs import NotEvaluable
from app.valuation_ensemble_models import ModelValue


def models(*values):
    return tuple(ModelValue(f"model_{index}", value, "evaluated") for index, value in enumerate(values))


def test_minmax_discards_exactly_one_observation_in_each_tail_not_twenty_percent():
    result = aggregate_grid_variants(models(1, 2, 3, 4, 5, 6, 7, 8, 100, 1000), 2000)
    assert result["primary"] == GRID_PRIMARY_VARIANT == "minmax_trimmed_mean_with_consensus"
    assert tuple(result["variants"]) == GRID_VARIANT_IDS
    assert len(result["variants"]) == 8
    variants = result["variants"]
    assert variants["minmax_trimmed_mean_without_consensus"]["value"] == pytest.approx(135 / 8)
    assert variants["minmax_trimmed_mean_with_consensus"]["value"] == pytest.approx(1135 / 9)
    assert variants["trimmed_mean_20_without_consensus"]["value"] == pytest.approx(33 / 6)
    assert variants["minmax_trimmed_mean_with_consensus"]["trimmed_each_tail"] == 1
    assert variants["trimmed_mean_20_with_consensus"]["trimmed_each_tail"] == 2


def test_three_values_leave_middle_even_when_consensus_is_extreme():
    assert MIN_MODELS == 3
    result = aggregate_grid_variants(models(10, 20), 1000)
    primary = result["variants"][GRID_PRIMARY_VARIANT]
    assert primary["value"] == 20 and primary["sample_size"] == 3 and primary["retained_count"] == 1
    assert primary["fundamental_models"] == 2 and primary["consensus_included"]
    without = result["variants"]["minmax_trimmed_mean_without_consensus"]
    assert without["reason"] == "ensemble_fewer_than_min_models" and without["value"] is None


@pytest.mark.parametrize("values", [(), (10,), (10, 20)])
def test_all_variants_publish_non_evaluation_when_below_three_values(values):
    result = aggregate_grid_variants(models(*values), None, consensus_reason="houses_below_minimum")
    assert all(item["value"] is None and item["reason"] == "ensemble_fewer_than_min_models"
               for item in result["variants"].values())


def test_missing_consensus_uses_models_in_with_consensus_variants_and_counts_why():
    result = aggregate_grid_variants(models(5, 10, 90), None, consensus_reason="targets_snapshot_missing")
    for method in ("mean", "median", "trimmed_mean_20", "minmax_trimmed_mean"):
        with_c, without = (result["variants"][f"{method}_{suffix}"] for suffix in ("with_consensus", "without_consensus"))
        assert with_c["value"] == without["value"] and with_c["status"] == "evaluated"
        assert not with_c["consensus_included"] and with_c["consensus_reason"] == "consensus:targets_snapshot_missing"
        assert without["consensus_reason"] is None


def test_tied_minimum_and_maximum_remove_one_each_not_all_equal_extremes():
    item = aggregate_grid_variants(models(1, 1, 2, 9, 9), None)["variants"][GRID_PRIMARY_VARIANT]
    assert item["value"] == 4 and item["retained_count"] == 3 and item["trimmed_each_tail"] == 1
    assert aggregate_grid_variants(models(7, 7, 7), None)["variants"][GRID_PRIMARY_VARIANT]["value"] == 7


def test_model_order_does_not_change_values_or_trim_counts():
    samples = models(1, 5, 10, 99)
    outputs = [aggregate_grid_variants(sample, 20)["variants"] for sample in permutations(samples)]
    assert all(output == outputs[0] for output in outputs)


def test_non_evaluated_models_are_counted_but_never_filled_or_turned_into_votes():
    missing = ModelValue("absent", None, "not_evaluable", "missing_fact:debt")
    result = aggregate_grid_variants((*models(10, 20), missing), 30)
    assert len(result["models"]) == 3
    assert result["models"][-1]["reason"] == "missing_fact:debt"
    item = result["variants"][GRID_PRIMARY_VARIANT]
    assert item["sample_size"] == 3 and item["fundamental_models"] == 2 and item["value"] == 20


@pytest.mark.parametrize("bad", [False, True, math.inf, math.nan, -1, 0, 10**400])
def test_invalid_consensus_cannot_increase_the_valid_value_count(bad):
    with pytest.raises(NotEvaluable):
        aggregate_grid_variants(models(10, 20), bad)


def test_inconsistent_results_and_duplicate_models_refuse_the_packet():
    one = models(10)[0]
    with pytest.raises(NotEvaluable, match="duplicate_model_identity"):
        aggregate_grid_variants((one, one), 30)
    with pytest.raises(NotEvaluable, match="inconsistent_model_result"):
        aggregate_grid_variants((ModelValue("bad", 1, "not_evaluable", "missing"),), None)
    with pytest.raises(NotEvaluable, match="evaluated_consensus_has_missing_reason"):
        aggregate_grid_variants(models(10, 20), 30, consensus_reason="missing")


def test_large_finite_values_do_not_overflow_aggregation_and_legacy_policy_stays_separate():
    result = aggregate_grid_variants(models(1e308, 1e308, 1e308), 1e308)
    assert all(item["value"] == 1e308 for item in result["variants"].values())
    legacy = aggregate_variants(models(5, 10, 90), None)
    assert legacy["primary"] == "median_with_consensus" and len(legacy["variants"]) == 6
    assert legacy["variants"]["median_with_consensus"]["reason"] == "consensus_unavailable"
