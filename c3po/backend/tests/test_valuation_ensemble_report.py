"""Synthetic signed-ensemble statistics and no-label preflight witnesses."""
from __future__ import annotations

import copy
import math
from typing import Any

import pytest

from app import valuation_accuracy_report as accuracy
from app import valuation_ensemble_report as report
from app import valuation_ensemble_pin as instrument_pin
from app import valuation_ensemble_grid as grid
from app.valuation_ensemble_inputs import canonical_hash
from app.valuation_ensemble_aggregation import aggregate_grid_variants
from app.valuation_ensemble_models import MODEL_IDS, ModelValue
from app.valuation_ensemble_pin import InstrumentBinding, PIN_SCHEMA, PREREG_COMMIT, PROTOCOL_CONSTANTS


def variants(value: float, *, count: int = 3) -> dict[str, Any]:
    return aggregate_grid_variants(tuple(ModelValue(name, value, "evaluated") for name in MODEL_IDS[:count]), None)["variants"]


def row(i: int, *, target: float = 12.0, served: float | None = 11.0, realized: float | None = 0.1) -> dict[str, Any]:
    return {"market": "NASDAQ", "symbol": f"S{i:03d}", "session_date": "2025-01-02", "price": 10.0,
            "served_tp": served, "variants": variants(target), "return": realized, "return_executable": i / 1000,
            "return_eligible": True, "executable_eligible": True, "screened": True,
            "models": [{"model": name, "value": target if i >= 13 else None,
                        "status": "evaluated" if i >= 13 else "not_evaluable",
                        "reason": None if i >= 13 else "missing_fact:capex_ttm"} for i, name in enumerate(MODEL_IDS)]}


def blocks(value: float | None, *, n: int = 9, p: float | None = 0.01, p_less: float | None = 0.99) -> dict[str, Any]:
    return {"estimate": value, "blocks": n, "p_greater": p, "p_less": p_less}


def good() -> dict[str, Any]:
    return {str(h): {"ic_executable": {"blocks": blocks(0.05)}, "decile_spread_executable": {"blocks": blocks(0.01)},
                     "delta_ic": {"blocks": blocks(0.01)}, "delta_error": {"blocks": blocks(0.02)},
                     "halves": {"first": {"estimate": 0.04}, "second": {"estimate": 0.05}},
                     "attrition_executable": {"eligible": 100, "rate": 0.15}} for h in (126, 252)}


GOOD_COVERAGE = {"records_share": 0.6, "screened_names_median": 150}


def test_signed_decision_requires_precision_and_ranking_both_horizons() -> None:
    cells = good()
    assert report.verdict(cells, coverage=GOOD_COVERAGE)["status"] == "PASS"
    assert report.verdict(cells, coverage=GOOD_COVERAGE)["promotion_authorized_by_result"] is True
    cases = [("126", "delta_error", "estimate", 0, "precision_delta_error_126_not_positive"),
             ("126", "delta_error", "p_greater", 0.051, "precision_delta_error_126_not_significant"),
             ("252", "delta_error", "estimate", 0, "precision_delta_error_252_not_positive"),
             ("252", "ic_executable", "estimate", 0, "ic_252_not_positive"),
             ("126", "delta_ic", "estimate", 0, "paired_delta_ic_126_not_positive"),
             ("126", "ic_executable", "estimate", 0.0199, "ic_126_below_minimum"),
             ("126", "ic_executable", "p_greater", None, "ic_126_not_significant"),
             ("126", "decile_spread_executable", "estimate", 0, "spread_126_not_positive")]
    for h, metric, field, value, reason in cases:
        changed = copy.deepcopy(cells)
        changed[h][metric]["blocks"][field] = value
        result = report.verdict(changed, coverage=GOOD_COVERAGE)
        assert result["status"] == "FAIL" and result["reasons"] == [reason]
    changed = copy.deepcopy(cells)
    changed["126"]["halves"]["second"]["estimate"] = 0
    assert report.verdict(changed, coverage=GOOD_COVERAGE)["reasons"] == ["second_half_ic_not_positive"]


def test_void_unmeasured_negative_precedence_and_no_persistence_condition() -> None:
    cells = good()
    voided = report.verdict(cells, coverage=GOOD_COVERAGE, void=["ensemble_instrument_not_pinned"])
    assert voided["status"] == "VOID" and "conditions" not in voided
    assert report.verdict({}, coverage={})["status"] == "VOID"
    negative = copy.deepcopy(cells)
    negative["126"]["ic_executable"]["blocks"]["p_less"] = 0.05
    assert report.verdict(negative, coverage=GOOD_COVERAGE)["status"] == "NEGATIVE"
    negative["126"]["ic_executable"]["blocks"]["blocks"] = 7
    assert report.verdict(negative, coverage=GOOD_COVERAGE)["status"] == "UNMEASURED"
    for coverage in ({"records_share": 0.599, "screened_names_median": 150}, {"records_share": 0.6, "screened_names_median": 149}, {}):
        assert report.verdict(cells, coverage=coverage)["status"] == "UNMEASURED"
    cells["126"]["attrition_executable"]["rate"] = 0.15001
    assert report.verdict(cells, coverage=GOOD_COVERAGE)["status"] == "UNMEASURED"
    assert "persistence" not in report.protocol()


def test_precision_is_difference_of_medians_of_absolute_log_errors() -> None:
    rows = []
    for i, (served_error, ensemble_error) in enumerate([(0, 0), (10, 0), (11, 12)] * 4):
        item = row(i, target=math.exp(ensemble_error), served=math.exp(served_error), realized=0)
        item["price"] = 1.0
        rows.append(item)
    result = report.session_statistics(rows, report.PRIMARY, 252)
    assert result["delta_error"] == pytest.approx(10)
    assert result["median_error_ensemble"] == pytest.approx(0)
    # The median paired difference is zero, and is deliberately NOT the estimand.
    assert sorted([s - e for s, e in [(0, 0), (10, 0), (11, 12)]])[1] == 0
    assert report.precision_error(40, 10, 1, 126) == pytest.approx(0)
    assert report.precision_error(1e308, 1e-308, 0, 126) > 700  # stable logs, no overflowing ratio
    with pytest.raises(ValueError):
        report.precision_error(10, 10, -1, 126)


def test_minimum_names_ties_and_paired_ic_use_statistic_specific_intersection() -> None:
    rows = [row(i, target=10 + i, served=40 - i) for i in range(30)]
    rows[-1]["served_tp"] = None
    result = report.session_statistics(rows, report.PRIMARY, 126)
    assert result["names_executable"] == 30 and result["names_paired_ic"] == 29 and result["names_precision"] == 29
    assert result["ic_executable"] == pytest.approx(1) and result["delta_ic"] == pytest.approx(2)
    assert result["decile_spread_executable"] > 0
    thin = report.session_statistics(rows[:9], report.PRIMARY, 126)
    assert thin["ic_executable"] is None and thin["delta_error"] is None
    assert report.session_statistics(rows[:29], report.PRIMARY, 126)["decile_spread_executable"] is None
    tied = [row(i, target=12, served=11) for i in range(30)]
    assert report.session_statistics(tied, report.PRIMARY, 126)["ic_executable"] is None


def test_close_to_close_and_executable_labels_are_not_interchanged() -> None:
    rows = [row(i, target=10 + i, realized=-i / 100) for i in range(30)]
    result = report.session_statistics(rows, report.PRIMARY, 126)
    assert result["ic_executable"] == 1 and result["ic"] == -1
    for item in rows:
        item["return_executable"] = None
    missing = report.session_statistics(rows, report.PRIMARY, 126)
    assert missing["ic_executable"] is None and missing["delta_error"] is not None


def test_blocks_use_calendar_anchor_maturity_and_empty_grid_sessions() -> None:
    rows = []
    index = {f"2025-{i:04d}": i for i in range(253)}
    for ix in (0, 125, 130, 250):
        for i in range(10):
            item = row(i, target=10 + i)
            item["session_date"] = f"2025-{ix:04d}"
            rows.append(item)
    result = report.horizon_statistics(rows, report.PRIMARY, 126, index_of=index,
                                       mature_through={126: 200, 127: 200}, partition_last=252,
                                       grid_sessions=["2025-0000", "2025-0125", "2025-0130", "2025-0250", "2025-0005"])
    assert result["ic_executable"]["blocks"]["blocks"] == 1
    assert result["ic_executable"]["blocks"]["blocks_pending"] == 1
    assert result["names_per_session"]["n"] == 5 and result["names_per_session"]["min"] == 0
    assert result["ic_executable"]["blocks"]["p_greater"] is None
    assert report._means([(0, 0.1), (126, 0.2)], 126, 200, 200) == [(0, 0.1), (1, 0.2)]


def test_batch_test_is_inherited_student_t_with_sqrt_one_point_five() -> None:
    points = [(i * 126, v) for i, v in enumerate([0.1, 0.3, 0.2, 0.4])]
    means = report._means(points, 126, 503, 503)
    values = [value for _, value in means]
    result = accuracy.batch_means_test(values)
    se = math.sqrt(1.5) * math.sqrt(sum((x - .25) ** 2 for x in values) / 3) / 2
    assert result["se"] == pytest.approx(se) and result["df"] == 3
    assert result["p_greater"] == pytest.approx(accuracy.student_t_sf(.25 / se, 3))
    assert accuracy.batch_means_test([.05] * 9)["p_greater"] is None


def test_exact_covariance_and_reproducible_condition_only_design() -> None:
    cov = report.block_covariance(grid_indices=[0, 1, 2, 3], mature_through=3, partition_last=3, horizon=2)
    assert cov == [[.75, .125], [.125, .75]]
    design = report.design_table(reps=5000, delta_error_sd=.05)
    assert design["complete_blocks"] == 9 and design["df"] == 8
    assert design["critical_t"] == pytest.approx(1.859548, abs=1e-6)
    assert [x["power"] for x in design["condition_2_only"]] == pytest.approx([.413, .247, .180], abs=.025)
    assert design == report.design_table(reps=5000, delta_error_sd=.05)
    assert design["full_PASS_power"] is None and design["condition_7_only"] is not None
    assert design["condition_7_only"][-1]["power"] > design["condition_7_only"][0]["power"]


def fixture(monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any], InstrumentBinding, dict[str, str]]:
    names = ["valuation_ensemble_grid.py", "valuation_ensemble_grid_consensus.py", "valuation_ensemble_report.py",
             "valuation_ensemble_executor.py", "valuation_ensemble_pin.py", "valuation_pit_rerun.py", "valuation_accuracy_report.py", "valuation-ensemble-grid.yml"]
    files = {(f".github/workflows/{name}" if name.endswith(".yml") else f"c3po/backend/app/{name}"): canonical_hash(name) for name in names}
    pin = {"schema": PIN_SCHEMA, "prereg_commit": PREREG_COMMIT, "prereg_sha256": report.PREREG_SHA256,
           "instrument_commit": "1" * 40, "owner_signature_comment_id": 1, "technical_GO_comment_id": 2,
           "published_at": "2026-10-27T13:00:00Z", "files": files, "constants": PROTOCOL_CONSTANTS}
    binding = InstrumentBinding(canonical_hash(pin), PREREG_COMMIT, "1" * 40, 1, 2)
    rows = [{**row(i, target=10 + i), "source": report.SOURCE, "run_key": "synthetic-run"} for i in range(12)]
    rev3 = {"schema": "VALUATION-PIT-GRID-MANIFEST-v1", "complete": True,
            "volume_basis": {"decision": "as_traded"},
            "grid": [{"market": "NASDAQ", "session_date": "2025-01-02", "as_of": "2025-01-03T04:00:00Z", "run_key": "synthetic-v3"}],
            "served_grid": [{"market": "NASDAQ", "session_date": "2025-01-02", "as_of": "2025-01-03T04:00:00Z", "run_key": "synthetic-served"}]}
    rev3["manifest_sha256"] = report.manifest_sha256(rev3)
    monkeypatch.setattr(report, "REV3_MANIFEST_SHA256", rev3["manifest_sha256"])  # only synthetic fixtures, never a runtime flag
    monkeypatch.setattr(instrument_pin, "REV3_MANIFEST_SHA256", rev3["manifest_sha256"])
    entry = {**rev3["grid"][0], "run_key": "synthetic-run", "records_sha256": canonical_hash(rows), "catalogue_stocks": 12,
             "v3_run_key": "synthetic-v3", "served_run_key": "synthetic-served",
             "input_pins": {"v3_run_key": "synthetic-v3", "served_run_key": "synthetic-served"},
             "instrument_commit": binding.instrument_commit, "instrument_pin_sha256": binding.expected_pin_sha256,
             "implementation_files": files, "started_at": "2026-10-27T13:01:00Z"}
    manifest = {"schema": report.MANIFEST_SCHEMA, "source": report.SOURCE, "complete": True,
                "rev3_manifest_sha256": rev3["manifest_sha256"], "prereg_sha256": report.PREREG_SHA256,
                "instrument_pin_sha256": binding.expected_pin_sha256, "entries": [entry],
                "report_calendar": {"index_of": {"2025-01-02": 0}, "mature_through": {}, "partition_last": 0}}
    manifest["manifest_sha256"] = report.manifest_sha256(manifest)
    # This suite isolates the report's phase order. The grid helper's concrete
    # snapshot/price/target checks are exercised by its own synthetic reader suite.
    expected_source_pins = copy.deepcopy(entry["input_pins"])
    monkeypatch.setattr(grid, "paired_source_identity", lambda v3, served: dict(expected_source_pins), raising=False)
    monkeypatch.setattr(grid, "validate_record_pair", lambda records, v3, served, **kw: [], raising=False)
    return manifest, rows, rev3, pin, binding, files


def paired_sources(_entry: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    return {"synthetic": "v3"}, {"synthetic": "served"}


def test_every_integrity_failure_precedes_the_first_label(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest, rows, rev3, pin, binding, files = fixture(monkeypatch)
    def no_labels(_row: Any, _h: int) -> Any:
        raise AssertionError("An invalid report read labels")
    cases = [("pin", None), ("file", {**files, names_key(files): "f" * 64}), ("manifest", {**manifest, "complete": False}),
             ("record", [{**rows[0], "price": 999}, *rows[1:]]), ("rev3", {**rev3, "complete": False})]
    for kind, value in cases:
        result = report.build_report(value if kind == "manifest" else manifest, value if kind == "record" else rows,
            rev3_manifest=value if kind == "rev3" else rev3, pin=value if kind == "pin" else pin,
            binding=binding, file_hashes=value if kind == "file" else files, label_reader=no_labels,
            index_of={"2025-01-02": 0}, mature_through={h: 0 for h in (21, 22, 63, 64, 126, 127, 252, 253)}, partition_last=0, expected_manifest_sha256=manifest["manifest_sha256"], paired_sources_reader=paired_sources)
        payload = result["payload"]
        assert payload["verdict"]["status"] == "VOID" and payload["labels_read"] == 0
        assert payload["variants"] is None and payload["design"] is None


def names_key(files: dict[str, str]) -> str:
    return next(iter(files))


def test_valid_report_reads_once_per_name_horizon_not_per_variant_and_counts_missing_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest, rows, rev3, pin, binding, files = fixture(monkeypatch)
    manifest["report_calendar"]["mature_through"] = {str(h): 0 for h in (21, 22, 63, 64, 126, 127, 252, 253)}
    manifest["manifest_sha256"] = report.manifest_sha256(manifest)
    calls = []
    def labels(item: Any, h: int) -> dict[str, Any]:
        calls.append((item["symbol"], h))
        # These misleading eligibility flags cannot hide attrition after a mature cut.
        return {"return": .1, "return_executable": None, "executable_eligible": False, "reason": "missing_exit"}
    result = report.build_report(manifest, rows, rev3_manifest=rev3, pin=pin, binding=binding, file_hashes=files,
                                 label_reader=labels, index_of={"2025-01-02": 0},
                                 mature_through={h: 0 for h in (21, 22, 63, 64, 126, 127, 252, 253)}, partition_last=0, expected_manifest_sha256=manifest["manifest_sha256"], paired_sources_reader=paired_sources)
    payload = result["payload"]
    assert len(calls) == 12 * 4 == payload["labels_read"]
    assert len(payload["variants"]) == 8 and payload["verdict"]["status"] == "UNMEASURED"
    primary = payload["variants"][report.PRIMARY]["horizons"]["126"]
    assert primary["attrition_executable"] == {"eligible": 12, "unavailable": 12, "rate": 1.0, "by_cause": {"missing_exit": 12}}
    assert payload["model_non_evaluations"]["dcf_fcff:missing_fact:capex_ttm"] == 12
    assert len(payload["model_non_evaluations"]) == 13
    assert payload["valid_value_count_distribution"] == {"3": 12}
    assert result["payload_sha256"] == canonical_hash(payload)


def test_immature_labels_are_never_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest, rows, rev3, pin, binding, files = fixture(monkeypatch)
    def no_labels(_row: Any, _h: int) -> Any:
        raise AssertionError("Read an immature label")
    result = report.build_report(manifest, rows, rev3_manifest=rev3, pin=pin, binding=binding, file_hashes=files,
                                 label_reader=no_labels, index_of={"2025-01-02": 0}, mature_through={}, partition_last=0, expected_manifest_sha256=manifest["manifest_sha256"], paired_sources_reader=paired_sources)
    assert result["payload"]["labels_read"] == 0
    assert result["payload"]["verdict"]["status"] == "UNMEASURED"


@pytest.mark.parametrize("mutation", ["duplicate", "min_models", "grid", "records_hash", "catalogue", "calendar", "models_missing", "models_duplicate", "aggregate_changed"])
def test_structural_metadata_changes_void_before_labels(monkeypatch: pytest.MonkeyPatch, mutation: str) -> None:
    manifest, rows, rev3, pin, binding, files = fixture(monkeypatch)
    index = {"2025-01-02": 0}
    if mutation == "duplicate":
        rows.append(copy.deepcopy(rows[0]))
    elif mutation == "min_models":
        rows[0]["variants"] = variants(10, count=2)
    elif mutation == "grid":
        manifest["entries"][0]["as_of"] = "2025-01-04T04:00:00Z"
    elif mutation == "records_hash":
        manifest["entries"][0]["records_sha256"] = "0" * 64
    elif mutation == "catalogue":
        manifest["entries"][0]["catalogue_stocks"] = 1
    elif mutation == "calendar":
        index = {"2025-01-02": 1}
    elif mutation == "models_missing":
        rows[0]["models"].pop()
        manifest["entries"][0]["records_sha256"] = canonical_hash(rows)
    elif mutation == "models_duplicate":
        rows[0]["models"][1] = copy.deepcopy(rows[0]["models"][0])
        manifest["entries"][0]["records_sha256"] = canonical_hash(rows)
    else:
        rows[0]["variants"][report.PRIMARY]["value"] = 999
        manifest["entries"][0]["records_sha256"] = canonical_hash(rows)
    manifest["manifest_sha256"] = report.manifest_sha256(manifest)
    def no_labels(_row: Any, _h: int) -> Any:
        raise AssertionError("Read labels after invalid metadata")
    result = report.build_report(manifest, rows, rev3_manifest=rev3, pin=pin, binding=binding, file_hashes=files,
                                 label_reader=no_labels, index_of=index, mature_through={}, partition_last=0, expected_manifest_sha256=manifest["manifest_sha256"], paired_sources_reader=paired_sources)
    assert result["payload"]["verdict"]["status"] == "VOID" and result["payload"]["labels_read"] == 0


@pytest.mark.parametrize("key,value", [("pin", []), ("manifest", []), ("manifest", {"manifest_sha256": math.nan}),
                                      ("rev3_manifest", None), ("records", [None]), ("records", "bad"),
                                      ("index_of", []), ("mature_through", []), ("mature_through", {126: 0}),
                                      ("binding", {}), ("file_hashes", []), ("paired_sources_reader", None),
                                      ("expected_manifest_sha256", None), ("expected_manifest_sha256", "f" * 64)])
def test_malformed_top_level_packets_are_sanitized_void_without_labels(monkeypatch: pytest.MonkeyPatch, key: str, value: Any) -> None:
    manifest, rows, rev3, pin, binding, files = fixture(monkeypatch)
    def no_labels(_row: Any, _h: int) -> Any:
        raise AssertionError("Malformed input read labels")
    args = {"manifest": manifest, "records": rows, "rev3_manifest": rev3, "pin": pin, "binding": binding,
            "file_hashes": files, "label_reader": no_labels, "index_of": {"2025-01-02": 0}, "mature_through": {}, "partition_last": 0, "expected_manifest_sha256": manifest["manifest_sha256"], "paired_sources_reader": paired_sources}
    args[key] = value
    result = report.build_report(**args)
    assert result["payload"]["verdict"]["status"] == "VOID" and result["payload"]["labels_read"] == 0
    assert result["payload_sha256"] == canonical_hash(result["payload"])


@pytest.mark.parametrize("failure", ["source_pins", "sibling_key", "missing_snapshot", "record_pair", "source_read_error"])
def test_actual_source_phase_mismatch_precedes_all_labels(monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    manifest, rows, rev3, pin, binding, files = fixture(monkeypatch)
    events: list[str] = []
    if failure == "source_pins":
        manifest["entries"][0]["input_pins"]["treasury_snapshot"] = "forged"
    elif failure == "sibling_key":
        manifest["entries"][0]["served_run_key"] = "different-sibling"
    elif failure == "record_pair":
        monkeypatch.setattr(grid, "validate_record_pair", lambda *args, **kwargs: ["served_target_mismatch"])
    manifest["manifest_sha256"] = report.manifest_sha256(manifest)
    def source_reader(entry: Any) -> Any:
        events.append("source")
        if failure == "missing_snapshot":
            return None, None
        if failure == "source_read_error":
            raise OSError("synthetic reader unavailable")
        return paired_sources(entry)
    def no_labels(_row: Any, _h: int) -> Any:
        events.append("label")
        raise AssertionError("Mismatching actual sibling metadata read labels")
    result = report.build_report(manifest, rows, rev3_manifest=rev3, pin=pin, binding=binding, file_hashes=files,
        label_reader=no_labels, index_of={"2025-01-02": 0}, mature_through={}, partition_last=0,
        expected_manifest_sha256=manifest["manifest_sha256"], paired_sources_reader=source_reader)
    assert result["payload"]["verdict"]["status"] == "VOID" and result["payload"]["labels_read"] == 0
    assert "label" not in events
    assert events == ([] if failure == "sibling_key" else ["source"])


def test_invalid_pin_does_not_read_even_source_snapshots(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest, rows, rev3, _pin, binding, files = fixture(monkeypatch)
    def forbidden(*args: Any) -> Any:
        raise AssertionError("Invalid pin reached a data reader")
    result = report.build_report(manifest, rows, rev3_manifest=rev3, pin=None, binding=binding, file_hashes=files,
        label_reader=forbidden, index_of={"2025-01-02": 0}, mature_through={}, partition_last=0,
        expected_manifest_sha256=manifest["manifest_sha256"], paired_sources_reader=forbidden)
    assert result["payload"]["verdict"]["status"] == "VOID" and result["payload"]["labels_read"] == 0
