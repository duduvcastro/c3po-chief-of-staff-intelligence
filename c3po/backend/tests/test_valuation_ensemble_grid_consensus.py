"""RAW snapshot selection matches the frozen eligibility reader, with a new mean."""
from datetime import datetime, timedelta, timezone
from itertools import permutations
import math

import pytest

from app import valuation_pit_rerun as pit
from app.valuation_ensemble_grid_consensus import grid_consensus_at
from app.valuation_ensemble_inputs import NotEvaluable, canonical_hash


T = datetime(2021, 7, 1, 4, tzinfo=timezone.utc)


def row(house, target, *, published=None, currency="USD", **updates):
    return {"analystCompany": house, "priceTarget": target,
            "publishedDate": published or (T-timedelta(days=1)).isoformat(), "currency": currency, **updates}


def evaluate(rows, **kwargs):
    return grid_consensus_at(rows, as_of=T, currency="USD", snapshot_id="pinned-V3-snapshot", **kwargs)


def test_mean_uses_raw_last_house_values_and_publishes_median_descriptive_only():
    rows = [row("A", 10), row("B", 20), row("C", 90)]
    value, receipt = evaluate(rows)
    assert value == 40 and receipt["public_consensus_tp"] == 20
    assert receipt["analyst_count"] == 3 and receipt["snapshot_id"] == "pinned-V3-snapshot"
    assert receipt["consensus_published_at"] == (T-timedelta(days=1)).isoformat()
    assert receipt["horizon"] == "N/D" and receipt["published_date_zone"] == "naive_is_UTC"
    assert receipt["members"][0]["raw_row_sha256"] == canonical_hash(rows[0])


def test_median_and_count_cannot_reconstruct_mean():
    left = evaluate([row("A", 10), row("B", 20), row("C", 90)])
    right = evaluate([row("A", 19), row("B", 20), row("C", 21)])
    assert left[1]["public_consensus_tp"] == right[1]["public_consensus_tp"] == 20
    assert left[1]["analyst_count"] == right[1]["analyst_count"] == 3
    assert left[0] == 40 and right[0] == 20


def test_latest_eligible_target_per_house_not_newest_future_or_duplicate_votes():
    rows = [row("A", 999, published=(T-timedelta(days=2)).isoformat()), row("A", 10),
            row("A", 1000, published=(T+timedelta(seconds=1)).isoformat()), row("B", 20), row("C", 30)]
    for sample in permutations(rows):
        value, receipt = evaluate(sample)
        assert value == 20 and receipt["analyst_count"] == 3
        assert receipt["refused"]["published_after_T"] == 1
        assert [member["target"] for member in receipt["members"]] == [10, 20, 30]


def test_cutoff_is_open_at_ninety_days_and_closed_at_T_naive_rows_are_UTC():
    rows = [row("old", 1000, published=(T-timedelta(days=90)).isoformat()),
            row("A", 10, published=(T-timedelta(days=90)+timedelta(microseconds=1)).isoformat()),
            row("B", 20, published=T.replace(tzinfo=None).isoformat()),
            row("C", 30, published=T.isoformat()),
            row("future", 1000, published=(T+timedelta(microseconds=1)).isoformat())]
    value, receipt = evaluate(rows)
    assert value == 20
    assert receipt["consensus_published_at"] == T.isoformat()
    assert receipt["refused"] == {"older_than_window": 1, "published_after_T": 1}


def test_explicit_currency_and_three_distinct_houses_are_required():
    rows = [row("A", 10), row("B", 20), row("C", 30, currency=None), row("D", 40, currency="BRL")]
    value, receipt = evaluate(rows)
    assert value is None and receipt["reason"] == "houses_below_minimum"
    assert receipt["analyst_count"] == 2
    assert receipt["refused"] == {"currency_field_missing": 1, "currency_mismatch": 1, "houses_below_minimum": 1}
    rows.append(row("C", 30, currency=" usd "))
    assert evaluate(rows)[0] == 20


def test_missing_snapshot_and_B3_publish_counted_reason_without_substituting_other_sources():
    value, receipt = grid_consensus_at(None, as_of=T, currency="USD", snapshot_id=None)
    assert value is None and receipt["reason"] == "targets_snapshot_missing"
    value, receipt = grid_consensus_at([row("A", 10)], as_of=T, currency="BRL", snapshot_id="x", market="B3")
    assert value is None and receipt["reason"] == "not_covered_for_B3"


def test_frozen_reader_house_aliases_and_same_clock_first_row_tie_are_preserved():
    rows = [row("A", 10), row("A", 100), row("B", 20), row("C", 30)]
    # Frozen consensus_at keeps first at an equal clock, not a new tie policy.
    value, receipt = evaluate(rows)
    assert value == 20 and receipt["public_consensus_tp"] == pit.consensus_at(rows, as_of=T, currency="USD")[0]["consensus_tp"]
    assert receipt["members"][0]["row_index"] == 0
    aliases = [{"analystName": "A", "priceTarget": 10, "publishedDate": T.isoformat(), "currency": "USD"},
               {"newsPublisher": "B", "priceTarget": 20, "publishedDate": T.isoformat(), "currency": "USD"}, row("C", 30)]
    assert evaluate(aliases)[0] == 20


@pytest.mark.parametrize("target", [0, -1, math.inf, math.nan, "not-a-number", 10**400])
def test_bad_targets_keep_original_reader_refusals_and_do_not_fill(target):
    rows = [row("A", 10), row("B", 20), row("bad", target)]
    assert evaluate(rows)[0] is None
    assert evaluate(rows)[1]["refused"] == pit.consensus_at(rows, as_of=T, currency="USD")[1]


def test_non_objects_unparseable_dates_are_counted_and_not_read_as_targets():
    rows = [None, row("bad", 40, published="invalid"), row("A", 10), row("B", 20), row("C", 30)]
    value, receipt = evaluate(rows)
    assert value == 20 and receipt["refused"] == {"not_an_object": 1, "published_date_unparseable": 1}


def test_large_finite_targets_average_without_overflow_and_invalid_T_does_not_silently_assume_zone():
    assert evaluate([row("A", 1e308), row("B", 1e308), row("C", 1e308)])[0] == 1e308
    with pytest.raises(NotEvaluable, match="instant_without_timezone"):
        grid_consensus_at([], as_of=T.replace(tzinfo=None), currency="USD", snapshot_id="x")
