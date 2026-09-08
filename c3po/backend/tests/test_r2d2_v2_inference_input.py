"""Synthetic signed-boundary cases; no estimator, observed outcomes or I/O."""
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json

import pytest

from app.r2d2_v2_inference_input import (
    AMENDMENT_SHA, MANIFEST_SHA, SESSION_FIELDS, InferenceInputError,
    adapt_collector_export, validate_cohort_prefix,
)
from app.r2d2_v2_earnings_package import (
    EARNINGS_AMENDMENT_SHA, EARNINGS_CLOSED_MANIFEST_SHA, EXPORT_SCHEMA,
    implementation_contract_sha,
)


def seal(value):
    body = {k: v for k, v in value.items() if k != "sha256"}
    # allow_nan here deliberately permits malformed synthetic payloads.
    value["sha256"] = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                                ensure_ascii=True).encode()).hexdigest()
    return value


def export(size=40):
    # This boundary consumes an already attested calendar, not an exchange API.
    schedule = [(date(2026, 1, 1) + timedelta(days=n)).isoformat() for n in range(69)]
    rows = []
    for n in range(size):
        empty = n % 10 == 0
        def arm(upper, lower):
            return {"upper_first": upper, "lower_first": lower, "ambiguous": 0 if empty else 2,
                    "time_or_event_exit": 0 if empty else 3, "unobservable": 0,
                    "episodes": 0 if empty else upper + lower + 5, "pending": 0}
        rows.append({"schema_version": "R2D2_V2_SESSION_STATISTICS_v1",
                     "session_date": schedule[n], "programmed_session_index": n + 1,
                     "arms": {"ELIGIBLE": arm(0 if empty else n + 1, 0 if empty else 7),
                              "CONTROL": arm(0 if empty else 3, 0 if empty else n + 2)},
                     "portfolio_pnl_usd_sum": 0 if empty else (-1)**n * (n + .25),
                     "portfolio_episode_count": 0 if empty else 2,
                     "portfolio_pnl_indeterminate_count": 0, "finalized": True,
                     "data_gate_unknown": False, "capture_coverage_unknown": False,
                     "terminal_veto": False, "observed_execution_certified": False})
    return seal({"schema": EXPORT_SCHEMA, "epoch": "synthetic-epoch",
                 "manifest_sha": MANIFEST_SHA, "signed_manifest_sha": MANIFEST_SHA,
                 "earnings_amendment_sha": EARNINGS_AMENDMENT_SHA,
                 "earnings_closed_manifest_sha": EARNINGS_CLOSED_MANIFEST_SHA,
                 "implementation_contract_sha": implementation_contract_sha(),
                 "implementation_package_sha": "d" * 64,
                 "amendment_sha": AMENDMENT_SHA, "release_sha": "a" * 64,
                 "readiness_sha": "b" * 64, "code_revision": "c" * 40,
                 "cohort_size": size, "calendar_version": "SYNTHETIC-CALENDAR",
                 "maturity_session": schedule[size + 8], "maturity_session_index": size + 9,
                 "programmed_sessions": schedule, "sessions_completed": size + 9,
                 "sessions": rows, "data_gate_unknown": False, "terminal_veto": False,
                 "statistical_verdict": "NOT_COMPUTED"})


@pytest.mark.parametrize("size", [40, 60])
def test_nine_exact_fields_and_fixed_ten_session_batches_preserve_empty_slots(size):
    source = export(size)
    initial = deepcopy(source)
    adapted = adapt_collector_export(source)
    assert source == initial
    rows = adapted.to_session_rows()
    assert len(rows) == size and all(tuple(row) == SESSION_FIELDS for row in rows)
    assert rows[0] == dict.fromkeys(SESSION_FIELDS, 0)
    assert rows[1] == {"upper_e": 2, "lower_e": 7, "upper_c": 3, "lower_c": 3,
                       "pnl_sum_usd": -1.25, "pnl_count": 2, "unobservable_e": 0,
                       "unobservable_c": 0, "indeterminate_pnl": 0}
    payload = adapted.to_dict()
    assert payload["maturity_session_index"] == size + 9
    assert payload["statistical_verdict"] == "NOT_COMPUTED"
    assert len(payload["batches"]) == size // 10
    for b, batch in enumerate(payload["batches"]):
        assert batch["first_programmed_session_index"] == 10*b + 1
        assert batch["last_programmed_session_index"] == 10*b + 10
        assert batch["session_dates"] == source["programmed_sessions"][10*b:10*b + 10]
        assert batch["statistics"]["upper_e"] == sum(n + 1 for n in range(10*b + 1, 10*b + 10))
        assert batch["statistics"]["pnl_count"] == 18
    assert "theta" not in payload and "lcb" not in payload
    json.dumps(payload, allow_nan=False)
    source["sessions"][1]["arms"]["ELIGIBLE"]["upper_first"] = 500
    rows[1]["upper_e"] = 900
    assert adapted.to_session_rows()[1]["upper_e"] == 2


def test_zero_denominator_batch_passes_unchanged_for_estimator_to_decide():
    source = export()
    for row in source["sessions"][:10]:
        control = row["arms"]["CONTROL"]
        control["episodes"] -= control["upper_first"] + control["lower_first"]
        control["upper_first"] = control["lower_first"] = 0
    result = adapt_collector_export(seal(source)).to_dict()
    assert len(result["batches"]) == 4
    assert result["batches"][0]["statistics"]["upper_c"] == 0
    assert result["batches"][0]["statistics"]["lower_c"] == 0
    assert result["statistical_verdict"] == "NOT_COMPUTED"


@pytest.mark.parametrize("field", ["finalized", "data_gate_unknown", "capture_coverage_unknown", "terminal_veto"])
@pytest.mark.parametrize("value", [None, 0, 1, "false"])
def test_flags_require_literal_boolean_not_truthiness(field, value):
    source = export()
    source["sessions"][1][field] = value
    with pytest.raises(InferenceInputError):
        adapt_collector_export(seal(source))


@pytest.mark.parametrize("value", [True, False, "1", 1.0, -1, None])
def test_counts_are_native_nonnegative_integers_without_coercion(value):
    source = export()
    source["sessions"][1]["arms"]["ELIGIBLE"]["upper_first"] = value
    with pytest.raises(InferenceInputError, match="INTEGER"):
        adapt_collector_export(seal(source))


@pytest.mark.parametrize("value", [None, True, "0", float("nan"), float("inf"), float("-inf")])
def test_unknown_or_nonfinite_pnl_is_never_zero(value):
    source = export()
    source["sessions"][1]["portfolio_pnl_usd_sum"] = value
    with pytest.raises(InferenceInputError):
        adapt_collector_export(seal(source))


@pytest.mark.parametrize("field", ["upper_first", "lower_first", "unobservable", "ambiguous",
                                    "time_or_event_exit", "episodes", "pending"])
def test_missing_counts_are_not_defaulted(field):
    source = export()
    del source["sessions"][1]["arms"]["CONTROL"][field]
    with pytest.raises(InferenceInputError):
        adapt_collector_export(seal(source))


@pytest.mark.parametrize("field", ["portfolio_pnl_usd_sum", "portfolio_episode_count",
                                    "portfolio_pnl_indeterminate_count"])
def test_missing_portfolio_fields_are_not_defaulted(field):
    source = export()
    del source["sessions"][1][field]
    with pytest.raises(InferenceInputError):
        adapt_collector_export(seal(source))


@pytest.mark.parametrize("change", ["pending", "unobservable", "indeterminate", "null_empty_pnl",
                                     "count_identity", "empty_nonzero_pnl", "portfolio_exceeds_research"])
def test_inconsistent_gate_false_cannot_hide_unknown_or_invalid_denominators(change):
    source = export()
    row = source["sessions"][1]
    arm = row["arms"]["ELIGIBLE"]
    if change in ("pending", "unobservable"):
        arm[change] = 1
        arm["episodes"] += 1
    elif change == "indeterminate":
        row["portfolio_pnl_indeterminate_count"] = 1
    elif change == "count_identity":
        arm["episodes"] += 1
    elif change == "portfolio_exceeds_research":
        row["portfolio_episode_count"] = arm["episodes"] + 1
    else:
        source["sessions"][0]["portfolio_pnl_usd_sum"] = None if change == "null_empty_pnl" else 1
    with pytest.raises(InferenceInputError):
        adapt_collector_export(seal(source))


@pytest.mark.parametrize("change", ["immature", "size_bool", "old_cohort", "omitted_zero_day",
                                     "duplicate_day", "missing_calendar_day", "maturity_index",
                                     "maturity_date", "row_order", "row_index", "prefix_date"])
def test_calendar_membership_and_maturity_cannot_shift_with_data(change):
    source = export()
    if change == "immature":
        source["sessions_completed"] = 48
    elif change == "size_bool":
        source["cohort_size"] = True
    elif change == "old_cohort":
        source["cohort_size"] = 20
    elif change == "omitted_zero_day":
        source["sessions"].pop(0)
    elif change == "duplicate_day":
        source["programmed_sessions"][2] = source["programmed_sessions"][1]
    elif change == "missing_calendar_day":
        source["programmed_sessions"].pop()
    elif change == "maturity_index":
        source["maturity_session_index"] = 50
    elif change == "maturity_date":
        source["maturity_session"] = source["programmed_sessions"][49]
    elif change == "row_order":
        source["sessions"][0], source["sessions"][1] = source["sessions"][1], source["sessions"][0]
    elif change == "row_index":
        source["sessions"][1]["programmed_session_index"] = 1
    else:
        source["sessions"][0]["session_date"] = source["programmed_sessions"][1]
    with pytest.raises(InferenceInputError):
        adapt_collector_export(seal(source))


@pytest.mark.parametrize("field,value", [("manifest_sha", "0"*64), ("amendment_sha", "0"*64),
    ("readiness_sha", None), ("signed_manifest_sha", None), ("code_revision", "short"),
    ("schema", "R2D2_V2_COHORT_EXPORT_V1"), ("schema", "R2D2_V2_COHORT_EXPORT_V2"),
    ("earnings_amendment_sha", None), ("earnings_amendment_sha", "0"*64),
    ("earnings_closed_manifest_sha", "0"*64), ("implementation_contract_sha", "0"*64),
    ("implementation_package_sha", None), ("implementation_package_sha", "placeholder"),
    ("statistical_verdict", "GO"),
    ("terminal_veto", True), ("data_gate_unknown", True), ("data_gate_unknown", None)])
def test_provenance_and_top_level_gate_fail_closed(field, value):
    source = export()
    source[field] = value
    with pytest.raises(InferenceInputError):
        adapt_collector_export(seal(source))


def test_modified_export_requires_new_hash():
    source = export()
    source["sessions_completed"] = 50
    with pytest.raises(InferenceInputError, match="HASH_MISMATCH"):
        adapt_collector_export(source)


def test_sixty_preserves_forty_and_all_categories_not_only_nine_columns():
    first = adapt_collector_export(export(40))
    second = adapt_collector_export(export(60))
    validate_cohort_prefix(first, second)
    changed = export(60)
    arm = changed["sessions"][1]["arms"]["CONTROL"]
    arm["ambiguous"] -= 1
    arm["time_or_event_exit"] += 1
    same_nine = adapt_collector_export(seal(changed))
    assert first.to_session_rows() == same_nine.to_session_rows()[:40]
    with pytest.raises(InferenceInputError, match="PREFIX_CHANGED"):
        validate_cohort_prefix(first, same_nine)
    changed = export(60)
    changed["sessions"][1]["portfolio_pnl_usd_sum"] += .01
    with pytest.raises(InferenceInputError, match="PREFIX_CHANGED"):
        validate_cohort_prefix(first, adapt_collector_export(seal(changed)))


@pytest.mark.parametrize("field,value", [("epoch", "different"), ("release_sha", "d"*64),
                                         ("code_revision", "e"*40), ("calendar_version", "OTHER"),
                                         ("implementation_package_sha", "f"*64)])
def test_same_counts_from_other_epoch_or_build_are_not_a_prefix(field, value):
    changed = export(60)
    changed[field] = value
    with pytest.raises(InferenceInputError, match="IDENTITY_MISMATCH"):
        validate_cohort_prefix(adapt_collector_export(export()), adapt_collector_export(seal(changed)))


def test_earnings_identity_preserved_without_reading_implementation_files(monkeypatch):
    from pathlib import Path
    def forbidden(*args, **kwargs):
        pytest.fail("pure inference adapter attempted file access")
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    source = export()
    adapted = adapt_collector_export(source).to_dict()
    for key in ("earnings_amendment_sha", "earnings_closed_manifest_sha",
                "implementation_contract_sha", "implementation_package_sha"):
        assert adapted[key] == source[key]
    assert adapted["schema"] == "R2D2_V2_INFERENCE_INPUT_V3"
