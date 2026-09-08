"""Pure CANONICAL_ONLY risk kernel and unconnected evidence adapter.

No service, provider, database, filesystem or clock access. Coverage flags and
timestamps are producer attestations, not independent proof of their truth.
The permissive mathematical kernel is intentionally separate from READY.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, cast

PRODUCER = "CANONICAL_ONLY_V1"
VERSION = "1.0.0"
ORIGIN_REVISION = "6083d7420746434426a11134b8edf0ba4b60b6b0"
ORIGIN_ONE_PAGER_SHA256 = "caf9169c70cc39fb761fd39d19ed12718bc558aff54da88985e8d70942cd3ee5"  # re-pinned with Passo 0 (producer/consumer roles); the differential test proves the risk branch unchanged
COMPONENTS = ("beta", "debt_to_ebitda", "earnings_growth", "free_cashflow",
              "insider_activity", "institutional_positions", "recent_grade_actions")


@dataclass(frozen=True)
class InsiderActivity:
    total_count: int
    buy_count: int
    sell_count: int


@dataclass(frozen=True)
class InstitutionalPositions:
    new_positions: int
    increased_positions: int
    reduced_positions: int
    closed_positions: int


@dataclass(frozen=True)
class CanonicalRiskInputs:
    """Normalized inputs at the original risk block, not raw fundamentals.

    Growth and debt/EBITDA are ratios; FCF is signed; beta is positive.
    Negative TTM EBITDA can yield a negative debt/EBITDA in the original.
Upstream normalization/TTM selection needs its own causal evidence. None keeps
the original kernel's arithmetic but NEVER qualifies the adapter as READY.
"""
    beta: float | None
    debt_to_ebitda: float | None
    earnings_growth: float | None
    free_cashflow: float | None
    insider_activity: InsiderActivity | None
    institutional_positions: InstitutionalPositions | None
    recent_grade_actions: tuple[str, ...] | None


@dataclass(frozen=True)
class ComponentEvidence:
    """Attestation from a future audited producer, including negative coverage.

For example, verified zero insider activity is not the same as an unavailable
feed. coverage_description identifies the population/window and normalization;
it is not interpreted as proof, or as a new risk TTL, by this pure module.
"""
    response_complete: bool
    coverage_verified: bool
    source_id: str
    source_version: str
    payload_sha256: str
    source_at: datetime | None
    available_at: datetime | None
    coverage_description: str


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def _finite(value: object) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(cast(float, value))
    except OverflowError:
        return False


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _validate_inputs(inputs: CanonicalRiskInputs) -> None:
    _require(type(inputs) is CanonicalRiskInputs, "INPUT_TYPE_INVALID")
    for name in COMPONENTS[:4]:
        value = getattr(inputs, name)
        _require(value is None or _finite(value), "NUMBER_INVALID_" + name.upper())
    _require(inputs.beta is None or inputs.beta > 0, "BETA_NOT_NORMALIZED")
    for name, expected in (("insider_activity", InsiderActivity),
                           ("institutional_positions", InstitutionalPositions)):
        counts = getattr(inputs, name)
        if counts is None:
            continue
        _require(type(counts) is expected, "COUNTS_TYPE_INVALID_" + name.upper())
        _require(all(type(v) is int and v >= 0 and _finite(v) for v in asdict(counts).values()),
                 "COUNTS_INVALID_" + name.upper())
    insider = inputs.insider_activity
    if insider is not None:
        _require(insider.buy_count + insider.sell_count <= insider.total_count, "INSIDER_COUNTS_INCONSISTENT")
    positions = inputs.institutional_positions
    if positions is not None:
        _require(_finite(sum(asdict(positions).values())), "INSTITUTIONAL_TOTAL_INVALID")
    actions = inputs.recent_grade_actions
    _require(actions is None or (type(actions) is tuple and all(type(a) is str and a.strip() for a in actions)),
             "GRADES_INVALID")


def insider_net_signal(activity: InsiderActivity | None) -> float:
    if activity is None or activity.total_count <= 0:
        return 0.0
    net_ratio = (activity.buy_count - activity.sell_count) / activity.total_count
    return net_ratio * min(1.0, activity.total_count / 4)


def institutional_conviction_signal(positions: InstitutionalPositions | None) -> float:
    if positions is None:
        return 0.0
    bullish = positions.new_positions + positions.increased_positions
    bearish = positions.reduced_positions + positions.closed_positions
    total = bullish + bearish
    if total <= 0:
        return 0.0
    return (bullish - bearish) / total * min(1.0, total / 50)


def grades_momentum_signal(actions: tuple[str, ...] | None) -> float:
    if not actions:
        return 0.0
    upgrades = sum(1 for action in actions if action == "upgrade")
    downgrades = sum(1 for action in actions if action == "downgrade")
    total = upgrades + downgrades
    if total <= 0:
        return 0.0
    return (upgrades - downgrades) / total * min(1.0, total / 5)


def canonical_risk_score(inputs: CanonicalRiskInputs) -> float:
    """Same arithmetic/order as OnePager._analyze:531–546, on valid inputs.

This excludes shared_valuation overrides and both other V1 risk families.
Calling this kernel alone is not a coverage or data-readiness decision.
"""
    _validate_inputs(inputs)
    risk_score = 32.0
    if inputs.beta is not None:
        risk_score += _clamp((inputs.beta - 0.85) * 24, -8, 25)
    if inputs.debt_to_ebitda is not None:
        risk_score += _clamp((inputs.debt_to_ebitda - 1.5) * 7, -8, 24)
    if inputs.earnings_growth is not None and inputs.earnings_growth < 0:
        risk_score += min(16, abs(inputs.earnings_growth) * 38)
    if inputs.free_cashflow is not None and inputs.free_cashflow < 0:
        risk_score += 9
    risk_score -= insider_net_signal(inputs.insider_activity) * 8.0
    risk_score -= institutional_conviction_signal(inputs.institutional_positions) * 8.0
    risk_score -= grades_momentum_signal(inputs.recent_grade_actions) * 6.0
    return _clamp(risk_score, 15, 90)


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _sha(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def adapt_canonical_risk(
    inputs: CanonicalRiskInputs,
    evidence: Mapping[str, ComponentEvidence],
    *,
    computed_at: datetime | None,
    available_at: datetime | None,
    decision_at: datetime,
) -> dict[str, Any]:
    """Assess one unconnected producer response; never acquire or publish it.

Clocks are factual attestations supplied by the future executor. computed_at
is completion of this score assessment, including a completed-null assessment;
available_at is its actual publication/availability. Calling this function
again must preserve both clocks for the same assessment. decision_at alone
can advance. An available response with unknown coverage stays completed-null.
"""
    _validate_inputs(inputs)
    _require(_aware(decision_at), "DECISION_CLOCK_INVALID")
    _require(isinstance(evidence, Mapping) and set(evidence) == set(COMPONENTS), "EVIDENCE_COMPONENTS_INVALID")
    for value in (computed_at, available_at):
        _require(value is None or _aware(value), "ASSESSMENT_CLOCK_INVALID")
    if computed_at is not None and available_at is not None:
        _require(computed_at <= available_at, "ASSESSMENT_CLOCK_ORDER_INVALID")
    diagnostics: list[str] = []
    complete = computed_at is not None and available_at is not None and available_at <= decision_at
    if not complete:
        diagnostics.append("ASSESSMENT_NOT_AVAILABLE")
    for name in COMPONENTS:
        item = evidence[name]
        _require(type(item) is ComponentEvidence, "EVIDENCE_TYPE_INVALID")
        _require(type(item.response_complete) is bool and type(item.coverage_verified) is bool,
                 "EVIDENCE_FLAGS_INVALID")
        for clock in (item.source_at, item.available_at):
            _require(clock is None or _aware(clock), "COMPONENT_CLOCK_INVALID_" + name.upper())
        if not item.response_complete or (item.available_at is not None and item.available_at > decision_at):
            complete = False
            diagnostics.append("RESPONSE_INCOMPLETE_" + name.upper())
        if not item.coverage_verified:
            diagnostics.append("COVERAGE_UNKNOWN_" + name.upper())
        if getattr(inputs, name) is None:
            diagnostics.append("VALUE_NULL_" + name.upper())
        if not all(type(v) is str and v.strip() for v in (item.source_id, item.source_version, item.coverage_description)):
            diagnostics.append("PROVENANCE_MISSING_" + name.upper())
        if not isinstance(item.payload_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", item.payload_sha256):
            diagnostics.append("PAYLOAD_HASH_INVALID_" + name.upper())
        if item.source_at is None or item.available_at is None or computed_at is None:
            diagnostics.append("COMPONENT_CLOCK_MISSING_" + name.upper())
        elif not item.source_at <= item.available_at <= computed_at:
            diagnostics.append("COMPONENT_NOT_CAUSAL_" + name.upper())
    status = "INCOMPLETE" if not complete else "COMPLETED_NULL" if diagnostics else "READY"
    value = canonical_risk_score(inputs) if status == "READY" else None
    # This private evidence receipt contains the normalized inputs; the future
    # publisher must apply its own access control. No instrument identifier here.
    calculation = _json_value({
        "producer": PRODUCER, "version": VERSION, "origin_revision": ORIGIN_REVISION,
        "origin_one_pager_sha256": ORIGIN_ONE_PAGER_SHA256,
        "inputs": asdict(inputs), "evidence": {name: asdict(evidence[name]) for name in COMPONENTS},
        "computed_at": computed_at, "available_at": available_at,
    })
    result: dict[str, Any] = {
        "schema": "V2_CANONICAL_RISK_SOURCE_V1", "producer": PRODUCER, "version": VERSION,
        "status": status, "response_complete": complete, "data_available": status == "READY",
        "diagnostics": diagnostics, "decision_at": _json_value(decision_at),
        "risk": None if not complete else {"value": value, "producer": PRODUCER,
                                             "source_at": _json_value(computed_at),
                                             "available_at": _json_value(available_at)},
        "coverage": {"verified": all(evidence[n].coverage_verified for n in COMPONENTS),
                     "independently_verified": False},
        "calculation": calculation, "calculation_sha256": _sha(calculation),
        "ttl_policy": "NOT_DEFINED_BY_THIS_ADAPTER", "production_connected": False,
    }
    result["self_sha256"] = _sha(result)
    return result
