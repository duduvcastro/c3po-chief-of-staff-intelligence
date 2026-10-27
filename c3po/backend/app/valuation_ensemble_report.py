"""The signed ensemble's single-look statistic, with labels behind instrument checks.

Inputs are saved grid records, not the live service or an outcome-selected sample.
This module opens no store, network connection or process. The caller supplies the
pin anchored to the reviewed public signatures and the same pinned label reader.
"""
from __future__ import annotations

import math
import random
import re
import statistics
from collections import Counter
from typing import TYPE_CHECKING, Any, Callable, Mapping, Sequence

from . import valuation_accuracy_report as accuracy
from .valuation_ensemble_aggregation import aggregate_grid_variants
from .valuation_ensemble_inputs import canonical_hash
from .valuation_ensemble_models import MODEL_IDS, ModelValue

if TYPE_CHECKING:
    from .valuation_ensemble_pin import InstrumentBinding


SCHEMA = "VALUATION-ENSEMBLE-PIT-REPORT-v1"
MANIFEST_SCHEMA = "VALUATION-ENSEMBLE-GRID-MANIFEST-v1"
SOURCE = "ensemble_pit"
PRIMARY = "minmax_trimmed_mean_with_consensus"
VARIANTS = tuple(f"{method}_{suffix}" for suffix in ("without_consensus", "with_consensus")
                 for method in ("mean", "median", "trimmed_mean_20", "minmax_trimmed_mean"))
HORIZONS = (21, 63, 126, 252)
PRIMARY_HORIZON = 126
MIN_MODELS = 3
MIN_BLOCKS_126 = 8
IC_MIN = 0.02
ALPHA = 0.05
ATTRITION_CAP_126 = 0.15
COVERAGE_MIN_RECORDS_SHARE = 0.60
COVERAGE_MIN_SCREENED_NAMES = 150
DESIGN_SEED = 20261026
DESIGN_REPS = 20000
PREREG_SHA256 = "712b4c171c4d059a31156eba8f7a9624f1195083309471e89e0519271d2e5471"
REV3_MANIFEST_SHA256 = "73a81bcef1cd93425dfab785ae57c52118ba09493a4b7169e31a0e0b6665f805"


def protocol() -> dict[str, Any]:
    return {"schema": SCHEMA, "source": SOURCE, "primary": PRIMARY, "variants": list(VARIANTS),
            "horizons": list(HORIZONS), "primary_horizon": PRIMARY_HORIZON, "min_models": MIN_MODELS,
            "min_blocks_126": MIN_BLOCKS_126, "ic_min": IC_MIN, "alpha": ALPHA,
            "attrition_cap_126": ATTRITION_CAP_126, "coverage_min_records_share": COVERAGE_MIN_RECORDS_SHARE,
            "coverage_min_screened_names": COVERAGE_MIN_SCREENED_NAMES, "min_names": 10, "min_names_deciles": 30,
            "variance_factor": 1.5, "design_seed": DESIGN_SEED,
            "precision": "median(abs(log1p(r)-h/252*log(tp_served/price))) - median(abs(log1p(r)-h/252*log(tp_ensemble/price)))",
            "paired_ic": "IC_ensemble minus IC_served on the same screened names with both targets and executable returns",
            "label_returns": "precision:D to D+h; ranking:D+1 to D+1+h; same pinned adjusted-price publication",
            "look": "first non-VOID complete-manifest report; only primary decides; secondary variants descriptive"}


def _number(value: Any, *, positive: bool = False) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        result = float(value)
    except (ValueError, OverflowError):
        return None
    if not math.isfinite(result) or (positive and result <= 0):
        return None
    return result


def _digest(value: Any) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) else None


def target_of(row: Mapping[str, Any], variant: str) -> float | None:
    variants = row.get("variants")
    if not isinstance(variants, Mapping):
        return None
    target = variants.get(variant)
    if isinstance(target, Mapping):
        if target.get("status") != "evaluated":
            return None
        target = target.get("value")
    return _number(target, positive=True)


def precision_error(tp: float, price: float, realized_return: float, horizon: int) -> float:
    """Absolute log error; this is neither MSE nor the median of paired differences."""
    if any(_number(x, positive=True) is None for x in (tp, price)) or _number(realized_return) is None or realized_return <= -1:
        raise ValueError("invalid_precision_input")
    if type(horizon) is not int or horizon <= 0:
        raise ValueError("invalid_horizon")
    # Subtract logs: a finite positive target/price may overflow as a ratio.
    return abs(math.log1p(realized_return) - horizon / 252 * (math.log(tp) - math.log(price)))


def _upside(tp: float, price: float) -> float | None:
    return _number(tp / price - 1)


def session_statistics(rows: Sequence[Mapping[str, Any]], variant: str, horizon: int) -> dict[str, Any]:
    """Per-session statistics. One row is one screened issuer, with a pre-read label.

    The executable and close-to-close label sets remain separate. Paired statistics
    use the intersection for that statistic; a missing comparator never changes the
    ensemble's own IC sample. ``screened=False`` is excluded by the caller.
    """
    executable: list[tuple[float, float]] = []
    total: list[tuple[float, float]] = []
    paired_ic: list[tuple[float, float, float]] = []
    errors: list[tuple[float, float, float]] = []
    for row in rows:
        price, tp = _number(row.get("price"), positive=True), target_of(row, variant)
        if price is None or tp is None:
            continue
        u = _upside(tp, price)
        served = _number(row.get("served_tp"), positive=True)
        served_u = _upside(served, price) if served is not None else None
        rx, r = _number(row.get("return_executable")), _number(row.get("return"))
        if u is not None and rx is not None and row.get("executable_eligible") is True:
            executable.append((u, rx))
            if served_u is not None:
                paired_ic.append((u, served_u, rx))
        if u is not None and r is not None and r > -1 and row.get("return_eligible") is True:
            total.append((u, r))
        if served is not None and r is not None and r > -1 and row.get("return_eligible") is True:
            errors.append((precision_error(tp, price, r, horizon), precision_error(served, price, r, horizon), abs(math.log1p(r))))
    def rank(values: Sequence[tuple[float, float]]) -> float | None:
        return accuracy.spearman([x[0] for x in values], [x[1] for x in values]) if len(values) >= 10 else None
    ensemble_pair = accuracy.spearman([x[0] for x in paired_ic], [x[2] for x in paired_ic]) if len(paired_ic) >= 10 else None
    served_pair = accuracy.spearman([x[1] for x in paired_ic], [x[2] for x in paired_ic]) if len(paired_ic) >= 10 else None
    median_errors = tuple(statistics.median(x[i] for x in errors) for i in range(3)) if len(errors) >= 10 else (None, None, None)
    e, s, rw = median_errors
    return {"ic_executable": rank(executable), "ic": rank(total),
            "decile_spread_executable": accuracy.decile_spread([x[0] for x in executable], [x[1] for x in executable]) if len(executable) >= 30 else None,
            "delta_ic": ensemble_pair - served_pair if ensemble_pair is not None and served_pair is not None else None,
            "delta_error": s - e if s is not None and e is not None else None,
            "delta_error_random_walk": rw - e if rw is not None and e is not None else None,
            "median_error_ensemble": e, "median_error_served": s, "median_error_random_walk": rw,
            "names_executable": len(executable), "names_total_return": len(total), "names_paired_ic": len(paired_ic), "names_precision": len(errors)}


def _means(points: Sequence[tuple[int, float]], h: int, mature_through: int | None, partition_last: int | None) -> list[tuple[int, float]]:
    last_complete = -1
    if mature_through is not None and mature_through >= 0:
        last_complete = partition_last // h if partition_last is not None and partition_last <= mature_through else (mature_through + 1) // h - 1
    by_block: dict[int, list[float]] = {}
    for index, value in sorted(points):
        if index < 0:
            raise ValueError("session_before_grid_anchor")
        by_block.setdefault(index // h, []).append(value)
    return [(b, math.fsum(v) / len(v)) for b, v in sorted(by_block.items()) if b <= last_complete]


def horizon_statistics(rows: Sequence[Mapping[str, Any]], variant: str, horizon: int, *, index_of: Mapping[str, int],
                       mature_through: Mapping[int, int | None], partition_last: int | None,
                       grid_sessions: Sequence[str] | None = None) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        if row.get("screened") is True:
            grouped.setdefault(str(row["session_date"]), []).append(row)
    sessions = {session: session_statistics(items, variant, horizon) for session, items in sorted(grouped.items())}
    metrics: dict[str, Any] = {}
    names = ("ic_executable", "ic", "decile_spread_executable", "delta_ic", "delta_error", "delta_error_random_walk",
             "median_error_ensemble", "median_error_served", "median_error_random_walk")
    for name in names:
        points = [(index_of[s], float(stats[name])) for s, stats in sessions.items() if stats[name] is not None]
        cut = mature_through.get(horizon + 1 if name in {"ic_executable", "decile_spread_executable", "delta_ic"} else horizon)
        block = accuracy.block_statistics(points, block_length=horizon, mature_through=cut, partition_last=partition_last)
        metrics[name] = {"blocks": block, "mature_through_index": cut,
                         "per_session_sd": statistics.stdev([value for _, value in points]) if len(points) >= 2 else None}
        if name == "ic_executable":
            means = _means(points, horizon, cut, partition_last)
            count = len(means) // 2
            metrics["halves"] = {"first": accuracy.batch_means_test([v for _, v in means[:count]]),
                                 "second": accuracy.batch_means_test([v for _, v in means[-count:]]) if count else accuracy.batch_means_test([]),
                                 "per_half": count}
    eligible = [row for row in rows if row.get("screened") is True and target_of(row, variant) is not None and row.get("executable_eligible") is True]
    missing = [row for row in eligible if _number(row.get("return_executable")) is None]
    metrics["attrition_executable"] = {"eligible": len(eligible), "unavailable": len(missing),
                                        "rate": len(missing) / len(eligible) if eligible else None,
                                        "by_cause": dict(sorted(Counter(str(row.get("reason") or "label_missing") for row in missing).items()))}
    expected = grid_sessions if grid_sessions is not None else [s for s, i in index_of.items() if i % 5 == 0 and (partition_last is None or i <= partition_last)]
    counts = [sessions.get(session, {}).get("names_executable", 0) for session in expected]
    metrics["names_per_session"] = {"n": len(counts), "median": statistics.median(counts) if counts else None,
                                    "min": min(counts) if counts else None, "max": max(counts) if counts else None}
    return metrics


def verdict(horizons: Mapping[str, Mapping[str, Any]], *, coverage: Mapping[str, Any], void: Sequence[str] = ()) -> dict[str, Any]:
    """VOID → UNMEASURED → NEGATIVE → PASS → FAIL, using every signed condition."""
    result: dict[str, Any] = {"status": "VOID", "reasons": list(void), "look": "SINGLE", "primary": PRIMARY,
                              "primary_horizon": 126, "promotion_authorized_by_result": False}
    if void:
        return result
    primary, year = horizons.get("126"), horizons.get("252")
    if primary is None or year is None:
        return {**result, "reasons": ["required_horizon_absent"]}
    ic = primary["ic_executable"]["blocks"]
    attrition = primary["attrition_executable"]
    unmeasured = []
    if not attrition["eligible"]:
        unmeasured.append("no_eligible_observations")
    if attrition["rate"] is None or attrition["rate"] > ATTRITION_CAP_126:
        unmeasured.append("attrition_above_cap_or_unknown")
    if coverage.get("records_share") is None or coverage["records_share"] < COVERAGE_MIN_RECORDS_SHARE:
        unmeasured.append("coverage_records_share_below_floor")
    if coverage.get("screened_names_median") is None or coverage["screened_names_median"] < COVERAGE_MIN_SCREENED_NAMES:
        unmeasured.append("coverage_screened_names_below_floor")
    if ic["blocks"] < MIN_BLOCKS_126:
        unmeasured.append("blocks_below_minimum")
    if unmeasured:
        return {**result, "status": "UNMEASURED", "reasons": unmeasured}
    if ic["p_less"] is not None and ic["p_less"] <= ALPHA:
        return {**result, "status": "NEGATIVE", "reasons": ["ic_executable_significantly_negative"]}
    checks = {
        "ic_126_below_minimum": ic["estimate"] is not None and ic["estimate"] >= IC_MIN,
        "ic_126_not_significant": ic["p_greater"] is not None and ic["p_greater"] <= ALPHA,
        "spread_126_not_positive": _positive(primary["decile_spread_executable"]["blocks"]["estimate"]),
        "first_half_ic_not_positive": _positive(primary["halves"]["first"]["estimate"]),
        "second_half_ic_not_positive": _positive(primary["halves"]["second"]["estimate"]),
        "ic_252_not_positive": _positive(year["ic_executable"]["blocks"]["estimate"]),
        "paired_delta_ic_126_not_positive": _positive(primary["delta_ic"]["blocks"]["estimate"]),
        "precision_delta_error_126_not_positive": _positive(primary["delta_error"]["blocks"]["estimate"]),
        "precision_delta_error_126_not_significant": primary["delta_error"]["blocks"]["p_greater"] is not None and primary["delta_error"]["blocks"]["p_greater"] <= ALPHA,
        "precision_delta_error_252_not_positive": _positive(year["delta_error"]["blocks"]["estimate"]),
    }
    failed = [reason for reason, passed in checks.items() if not passed]
    return {**result, "status": "FAIL" if failed else "PASS", "reasons": failed, "conditions": checks,
            "promotion_authorized_by_result": not failed}


def _positive(value: Any) -> bool:
    checked = _number(value)
    return checked is not None and checked > 0


def _cholesky(matrix: Sequence[Sequence[float]]) -> list[list[float]]:
    n = len(matrix)
    lower = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            residual = matrix[i][j] - math.fsum(lower[i][k] * lower[j][k] for k in range(j))
            lower[i][j] = math.sqrt(max(0.0, residual)) if i == j else residual / lower[j][j]
    return lower


def block_covariance(*, grid_indices: Sequence[int], mature_through: int, partition_last: int | None = None, horizon: int = 126) -> list[list[float]]:
    """Exact covariance of block means for Cov(X_t,X_s)=max(0,1-|t-s|/h)."""
    means = _means([(i, 0.0) for i in grid_indices], horizon, mature_through, partition_last)
    blocks = [[i for i in grid_indices if i // horizon == block] for block, _ in means]
    return [[math.fsum(max(0.0, 1 - abs(i - j) / horizon) for i in a for j in b) / (len(a) * len(b)) for b in blocks] for a in blocks]


def design_table(*, reps: int = DESIGN_REPS, seed: int = DESIGN_SEED, session_sds: Sequence[float] = (0.10, 0.15, 0.20),
                 true_ic: float = 0.05, delta_error_sd: float | None = None, delta_error_effects: Sequence[float] = (0.001, 0.005, 0.01, 0.02, 0.05),
                 grid_indices: Sequence[int] = tuple(range(0, 1331, 5)), mature_through: int = 1133, partition_last: int | None = 1330) -> dict[str, Any]:
    """Power of condition 2 and, if supplied, condition 7. Never full-PASS power.

    Only nine correlated block means are sampled, from their exact covariance;
    this is equivalent to sampling the full overlapping Gaussian session series.
    The realized precision SD changes the descriptive table, never a threshold.
    """
    if type(reps) is not int or reps <= 0 or type(seed) is not int or not grid_indices or any(_number(x, positive=True) is None for x in session_sds):
        raise ValueError("invalid_design_parameters")
    if delta_error_sd is not None and _number(delta_error_sd, positive=True) is None:
        raise ValueError("invalid_precision_sd")
    if _number(true_ic) is None or any(_number(x) is None for x in delta_error_effects):
        raise ValueError("invalid_design_effect")
    cov = block_covariance(grid_indices=grid_indices, mature_through=mature_through, partition_last=partition_last)
    b = len(cov)
    if b < 2:
        raise ValueError("design_needs_two_complete_blocks")
    lower, rng = _cholesky(cov), random.Random(seed)
    critical = accuracy.student_t_isf(ALPHA, b - 1)
    passed = [0] * len(session_sds)
    precision = [0] * len(delta_error_effects)
    for _ in range(reps):
        independent = [rng.gauss(0, 1) for _ in range(b)]
        samples = [math.fsum(lower[i][j] * independent[j] for j in range(i + 1)) for i in range(b)]
        center, sd = statistics.mean(samples), statistics.stdev(samples)
        base_se = math.sqrt(1.5) * sd / math.sqrt(b)
        for i, scale in enumerate(session_sds):
            estimate = true_ic + scale * center
            passed[i] += estimate >= IC_MIN and base_se > 0 and estimate / (scale * base_se) >= critical
        if delta_error_sd is not None:
            for i, effect in enumerate(delta_error_effects):
                estimate = effect + delta_error_sd * center
                precision[i] += estimate > 0 and base_se > 0 and estimate / (delta_error_sd * base_se) >= critical
    return {"seed": seed, "reps": reps, "horizon": 126, "step_sessions": 5, "complete_blocks": b, "df": b - 1,
            "critical_t": critical, "covariance": cov, "model": "exact covariance of complete block means of triangular126-session Gaussian process",
            "condition_2_only": [{"true_ic": true_ic, "session_sd": sd, "power": n / reps} for sd, n in zip(session_sds, passed)],
            "condition_7_only": None if delta_error_sd is None else [{"true_delta_error": effect, "realized_session_sd": delta_error_sd, "power": n / reps} for effect, n in zip(delta_error_effects, precision)],
            "condition_7_reason": "precision_variance_unavailable_or_zero" if delta_error_sd is None else None,
            "full_PASS_power": None, "full_PASS_power_reason": "not_modelled; additional mandatory conditions reduce power"}


def manifest_sha256(manifest: Mapping[str, Any]) -> str:
    return canonical_hash({key: value for key, value in manifest.items() if key != "manifest_sha256"})


def _slot(entry: Mapping[str, Any]) -> tuple[str, str, str]:
    return str(entry.get("market")), str(entry.get("session_date")), str(entry.get("as_of"))


def deduplicate_exchanges(records: Sequence[Mapping[str, Any]]) -> tuple[list[Mapping[str, Any]], int]:
    """Rev3's one exchange per (symbol,D), shared by ensemble and comparator."""
    priority = {"NASDAQ": 0, "NYSE": 1}
    chosen: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in records:
        key = str(row["session_date"]), str(row["symbol"])
        if key not in chosen or priority[str(row["market"])] < priority[str(chosen[key]["market"])]:
            chosen[key] = row
    return [chosen[key] for key in sorted(chosen)], len(records) - len(chosen)


def _manifest_errors(manifest: Mapping[str, Any], rev3: Mapping[str, Any], records: Sequence[Mapping[str, Any]],
                     index_of: Mapping[str, int], mature_through: Mapping[int, int | None], partition_last: int | None) -> list[str]:
    """Metadata and content checks, before calling the outcome reader.

    Matching this lineage hash does not independently authenticate SEC originals;
    original-byte capture is a separate track from this signed grid instrument.
    """
    errors: list[str] = []
    expected_calendar = {"index_of": dict(index_of), "mature_through": {str(h): v for h, v in mature_through.items()},
                         "partition_last": partition_last}
    if manifest.get("report_calendar") != expected_calendar:
        errors.append("ensemble_report_calendar_not_the_published_manifest")
    from .valuation_ensemble_calendar import report_calendar_for
    if report_calendar_for(rev3) != expected_calendar:
        errors.append("ensemble_report_calendar_not_derived_from_rev3")
    if manifest.get("schema") != MANIFEST_SCHEMA or manifest.get("source") != SOURCE:
        errors.append("ensemble_manifest_schema_or_source")
    if manifest.get("complete") is not True or rev3.get("complete") is not True:
        errors.append("ensemble_manifest_not_complete")
    volume = rev3.get("volume_basis")
    if not isinstance(volume, Mapping) or volume.get("decision") not in {"as_traded", "split_adjusted"}:
        errors.append("ensemble_rev3_volume_basis_missing")
    if manifest.get("manifest_sha256") != manifest_sha256(manifest):
        errors.append("ensemble_manifest_hash_mismatch")
    if (rev3.get("manifest_sha256") != manifest_sha256(rev3)
            or manifest.get("rev3_manifest_sha256") != rev3.get("manifest_sha256")
            or rev3.get("manifest_sha256") != REV3_MANIFEST_SHA256):
        errors.append("ensemble_inputs_differ_from_rev3")
    grid, old_grid = manifest.get("entries"), rev3.get("grid")
    if not isinstance(grid, list) or not isinstance(old_grid, list) or not grid or any(not isinstance(x, Mapping) for x in [*grid, *old_grid]):
        return [*errors, "ensemble_sessions_not_rev3_sessions"]
    slots, old_slots = [_slot(x) for x in grid], [_slot(x) for x in old_grid]
    if len(slots) != len(set(slots)) or sorted(slots) != sorted(old_slots):
        errors.append("ensemble_sessions_not_rev3_sessions")
    served_grid = rev3.get("served_grid")
    if not isinstance(served_grid, list) or any(not isinstance(x, Mapping) for x in served_grid):
        errors.append("ensemble_rev3_served_siblings_missing")
        served_grid = []
    v3_by_slot = {_slot(x): str(x.get("run_key")) for x in old_grid}
    served_by_slot = {_slot(x): str(x.get("run_key")) for x in served_grid}
    if len(served_by_slot) != len(served_grid) or set(served_by_slot) != set(v3_by_slot):
        errors.append("ensemble_rev3_served_siblings_missing")
    for entry in grid:
        slot = _slot(entry)
        if entry.get("v3_run_key") != v3_by_slot.get(slot) or entry.get("served_run_key") != served_by_slot.get(slot):
            errors.append("ensemble_rev3_sibling_identity_mismatch")
    grid_sessions = {str(x["session_date"]) for x in grid}
    if not grid_sessions.issubset(index_of) or any(type(v) is not int or v < 0 for v in index_of.values()) or len(set(index_of.values())) != len(index_of):
        errors.append("invalid_calendar_session_index")
    if any(type(h) is not int or (v is not None and (type(v) is not int or v < -1)) for h, v in mature_through.items()):
        errors.append("invalid_label_maturity_index")
    if partition_last is not None and (type(partition_last) is not int or partition_last < 0):
        errors.append("invalid_partition_last_index")
    if any(index_of.get(session, -1) % 5 for session in grid_sessions):
        errors.append("ensemble_grid_not_every_fifth_calendar_session")
    # The complete calendar contains every session, not just every grid instant.
    if index_of and sorted(index_of.values()) != list(range(max(index_of.values()) + 1)):
        errors.append("calendar_index_has_gaps")
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    identities: set[tuple[str, str, str]] = set()
    run_slots = {str(entry.get("run_key")): _slot(entry) for entry in grid}
    if len(run_slots) != len(grid) or any(not key or key == "None" for key in run_slots):
        errors.append("ensemble_duplicate_or_missing_run_identity")
    for row in records:
        key = str(row.get("run_key"))
        slot = run_slots.get(key)
        identity = str(row.get("market")), str(row.get("session_date")), str(row.get("symbol"))
        if identity in identities:
            errors.append("duplicate_symbol_session")
        identities.add(identity)
        if slot is None or slot[:2] != (str(row.get("market")), str(row.get("session_date"))) or row.get("source") != SOURCE:
            errors.append("ensemble_record_not_in_manifest")
        if row.get("market") not in {"NASDAQ", "NYSE"}:
            errors.append("ensemble_record_market_not_US")
        if type(row.get("screened")) is not bool or not row.get("symbol"):
            errors.append("ensemble_invalid_record_identity_or_screen")
        variants = row.get("variants")
        if not isinstance(variants, Mapping) or set(variants) != set(VARIANTS):
            errors.append("ensemble_eight_variants_required")
        else:
            for variant, item in variants.items():
                if not isinstance(item, Mapping) or item.get("status") not in {"evaluated", "not_evaluable"}:
                    errors.append("ensemble_invalid_variant_result")
                    continue
                if item["status"] == "evaluated":
                    if target_of(row, str(variant)) is None or type(item.get("sample_size")) is not int or item["sample_size"] < MIN_MODELS:
                        errors.append("ensemble_evaluated_variant_below_min_models")
                elif item.get("value") is not None or not item.get("reason"):
                    errors.append("ensemble_missing_non_evaluation_reason")
        models = row.get("models")
        if (not isinstance(models, list) or len(models) != len(MODEL_IDS) or any(not isinstance(x, Mapping) for x in models)
                or {x.get("model") for x in models} != set(MODEL_IDS)):
            errors.append("ensemble_sixteen_model_results_required")
        else:
            try:
                model_values = tuple(ModelValue(str(x["model"]), x.get("value"), str(x["status"]), x.get("reason")) for x in models)
                consensus = row.get("consensus") or {}
                if not isinstance(consensus, Mapping):
                    raise ValueError("invalid_consensus")
                consensus_value = consensus.get("value") if consensus.get("status") == "evaluated" else None
                aggregation = aggregate_grid_variants(model_values, consensus_value,
                    consensus_reason=None if consensus_value is not None else str(consensus.get("reason") or "unavailable"))
                if aggregation["variants"] != variants:
                    errors.append("ensemble_aggregation_not_the_model_values")
            except (ValueError, TypeError, KeyError, OverflowError):
                errors.append("ensemble_model_or_consensus_results_invalid")
        grouped.setdefault(key, []).append(row)
    for entry in grid:
        rows = sorted(grouped.get(str(entry.get("run_key")), []), key=lambda row: str(row.get("symbol")))
        if entry.get("records_sha256") != canonical_hash(rows):
            errors.append("ensemble_records_content_mismatch")
        if type(entry.get("catalogue_stocks")) is not int or entry["catalogue_stocks"] < 1 or len(rows) > entry["catalogue_stocks"]:
            errors.append("ensemble_catalogue_denominator_invalid")
    return sorted(set(errors))


def _paired_sources_errors(manifest: Mapping[str, Any], records: Sequence[Mapping[str, Any]],
                           reader: Callable[[Mapping[str, Any]], tuple[Mapping[str, Any], Mapping[str, Any]]],
                           *, volume_basis: str) -> list[str]:
    """Re-read the named siblings and compare actual inputs/outputs before labels.

    The pinned runtime supplies a read-only snapshot reader. It is not a JSON
    success flag. The grid helper validates native manifests, IDs, source pins,
    screen and saved served targets; no price outcome is requested here.
    """
    from .valuation_ensemble_grid import paired_source_identity, validate_record_pair

    errors: list[str] = []
    for entry in manifest["entries"]:
        try:
            v3, served = reader(entry)
            if not isinstance(v3, Mapping) or not isinstance(served, Mapping):
                errors.append("ensemble_rev3_sibling_snapshot_missing")
                continue
            observed = paired_source_identity(v3, served)
            if entry.get("input_pins") != observed:
                errors.append("ensemble_inputs_differ_from_rev3")
            if observed.get("v3_run_key") != entry.get("v3_run_key") or observed.get("served_run_key") != entry.get("served_run_key"):
                errors.append("ensemble_rev3_sibling_identity_mismatch")
            subset = [record for record in records if record.get("run_key") == entry["run_key"]]
            errors.extend(validate_record_pair(subset, v3, served, volume_basis=volume_basis))
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            errors.append("ensemble_rev3_sibling_snapshot_invalid")
    return sorted(set(errors))


def build_report(manifest: Mapping[str, Any], records: Sequence[Mapping[str, Any]], *, rev3_manifest: Mapping[str, Any],
                 pin: Mapping[str, Any] | None, binding: InstrumentBinding, file_hashes: Mapping[str, str],
                 label_reader: Callable[[Mapping[str, Any], int], Mapping[str, Any]], index_of: Mapping[str, int],
                 mature_through: Mapping[int, int | None], partition_last: int | None = None,
                 expected_manifest_sha256: str | None = None,
                 paired_sources_reader: Callable[[Mapping[str, Any]], tuple[Mapping[str, Any], Mapping[str, Any]]] | None = None) -> dict[str, Any]:
    """Run the report's two phases. Invalid metadata/PIN returns VOID with zero labels.

    ``binding`` is the operator's external trust anchor checked against the public
    GO/signature; it must not be synthesized from the untrusted JSON pin. The
    ``expected_manifest_sha256`` must likewise come from the published completed
    run receipt, not be read back from this input document. The caller opens only
    the already-pinned price publication. A label contains
    ``return`` (D→D+h), ``return_executable`` (D+1→D+1+h), their separate boolean
    ``*_eligible`` flags and a missing-label ``reason``. All figures stay absent
    until the entire manifest, file set, signatures and rule binding pass.
    """
    from .valuation_ensemble_pin import InstrumentBinding, validate_instrument_pin, validate_manifest_binding

    errors: list[str] = []
    if not isinstance(manifest, Mapping) or not isinstance(rev3_manifest, Mapping):
        errors.append("ensemble_manifest_or_reference_invalid")
    safe_manifest = manifest if isinstance(manifest, Mapping) else {}
    safe_rev3 = rev3_manifest if isinstance(rev3_manifest, Mapping) else {}
    if _digest(expected_manifest_sha256) is None or safe_manifest.get("manifest_sha256") != expected_manifest_sha256:
        errors.append("ensemble_manifest_not_bound_to_published_receipt")
    rows_valid = isinstance(records, Sequence) and not isinstance(records, (str, bytes)) and all(isinstance(row, Mapping) for row in records)
    if not rows_valid:
        errors.append("ensemble_records_invalid")
    if not isinstance(index_of, Mapping) or not isinstance(mature_through, Mapping):
        errors.append("ensemble_calendar_or_maturity_invalid")
    if pin is not None and not isinstance(pin, Mapping):
        errors.append("ensemble_instrument_pin_invalid")
    if not isinstance(binding, InstrumentBinding) or not isinstance(file_hashes, Mapping):
        errors.append("ensemble_instrument_trust_anchor_invalid")
    if not callable(paired_sources_reader):
        errors.append("ensemble_rev3_sibling_reader_required")
    if not errors:
        errors.extend(validate_instrument_pin(pin, file_hashes=file_hashes, binding=binding))
    try:
        if not errors and pin is not None:
            errors.extend(validate_manifest_binding(manifest, pin, binding))
        if not errors:
            errors.extend(_manifest_errors(manifest, rev3_manifest, records, index_of, mature_through, partition_last))
        if not errors and paired_sources_reader is not None:
            errors.extend(_paired_sources_errors(manifest, records, paired_sources_reader,
                                                  volume_basis=str(rev3_manifest["volume_basis"]["decision"])))
    except (ValueError, TypeError, KeyError, OverflowError):
        errors.append("ensemble_manifest_or_records_invalid")
    base: dict[str, Any] = {"schema": SCHEMA, "protocol": protocol(), "prereg_sha256": PREREG_SHA256,
                            "manifest_sha256": _digest(safe_manifest.get("manifest_sha256")), "rev3_manifest_sha256": _digest(safe_rev3.get("manifest_sha256")),
                            "instrument_pin_sha256": _digest(binding.expected_pin_sha256) if isinstance(binding, InstrumentBinding) and pin is not None else None,
                            "labels_read": 0, "variants": None,
                            "model_non_evaluations": None, "valid_value_count_distribution": None, "design": None,
                            "served_source_changed": False, "real_money": False}
    if errors:
        base["verdict"] = verdict({}, coverage={}, void=sorted(set(errors)))
        return {"schema": SCHEMA, "payload": base, "payload_sha256": canonical_hash(base)}
    original_records = records
    records, duplicate_count = deduplicate_exchanges(records)
    base["refused_records"] = {"duplicate_across_exchanges": duplicate_count} if duplicate_count else {}
    base["raw_records"] = len(original_records)
    base["admissible_records"] = len(records)
    labelled: dict[int, list[dict[str, Any]]] = {h: [] for h in HORIZONS}
    calls = 0
    for row in sorted(records, key=lambda x: (str(x["session_date"]), str(x["market"]), str(x["symbol"]))):
        if not any(target_of(row, variant) is not None for variant in VARIANTS):
            continue
        index = index_of[str(row["session_date"])]
        for h in HORIZONS:
            direct_cut, exec_cut = mature_through.get(h), mature_through.get(h + 1)
            direct_mature, exec_mature = direct_cut is not None and index <= direct_cut, exec_cut is not None and index <= exec_cut
            labels: Mapping[str, Any] = {}
            if direct_mature or exec_mature:
                labels = label_reader(row, h)
                calls += 1
            direct = _number(labels.get("return")) if direct_mature else None
            executable = _number(labels.get("return_executable")) if exec_mature else None
            direct = direct if direct is not None and direct > -1 else None
            executable = executable if executable is not None and executable > -1 else None
            labelled[h].append({**row, "return": direct, "return_executable": executable,
                                "return_eligible": direct_mature,
                                "executable_eligible": exec_mature,
                                "reason": labels.get("reason")})
    catalogue = sum(entry["catalogue_stocks"] for entry in manifest["entries"])
    grid_sessions = sorted({str(entry["session_date"]) for entry in manifest["entries"]})
    variants: dict[str, Any] = {}
    for variant in VARIANTS:
        horizons = {str(h): horizon_statistics(labelled[h], variant, h, index_of=index_of, mature_through=mature_through,
                                              partition_last=partition_last, grid_sessions=grid_sessions) for h in HORIZONS}
        records_share = sum(target_of(row, variant) is not None for row in records) / catalogue if catalogue else None
        coverage = {"records_share": records_share, "screened_names_median": horizons["126"]["names_per_session"]["median"]}
        variants[variant] = {"horizons": horizons, "coverage": coverage, "decisory": variant == PRIMARY}
    base.update({"labels_read": calls, "variants": variants,
                 "verdict": verdict(variants[PRIMARY]["horizons"], coverage=variants[PRIMARY]["coverage"])})
    failures: Counter[str] = Counter()
    counts: Counter[str] = Counter()
    for row in records:
        models = row.get("models") or []
        for model in models:
            if isinstance(model, Mapping) and model.get("status") == "not_evaluable":
                failures[f"{model.get('model')}:{model.get('reason')}"] += 1
        counts[str(row["variants"][PRIMARY].get("sample_size", 0))] += 1
    sd = variants[PRIMARY]["horizons"]["126"]["delta_error"]["per_session_sd"]
    base.update({"model_non_evaluations": dict(sorted(failures.items())), "valid_value_count_distribution": dict(sorted(counts.items())),
                 "design": design_table(delta_error_sd=sd if sd is not None and sd > 0 else None)})
    return {"schema": SCHEMA, "payload": base, "payload_sha256": canonical_hash(base)}
