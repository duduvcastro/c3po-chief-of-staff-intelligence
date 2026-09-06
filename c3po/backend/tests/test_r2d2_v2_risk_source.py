from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.r2d2_v2_risk_source import (
    COMPONENTS, ORIGIN_ONE_PAGER_SHA256, CanonicalRiskInputs, ComponentEvidence,
    InsiderActivity, InstitutionalPositions, adapt_canonical_risk,
    canonical_risk_score, grades_momentum_signal, insider_net_signal,
    institutional_conviction_signal,
)

NOW = datetime(2026, 9, 8, 14, 0, 5, tzinfo=timezone.utc)
COMPUTED = NOW - timedelta(days=1)
AVAILABLE = COMPUTED + timedelta(seconds=1)


def inputs():
    return CanonicalRiskInputs(1.12, 2.15, -.125, -123.0,
                               InsiderActivity(4, 1, 3), InstitutionalPositions(12, 20, 4, 5),
                               ("upgrade", "downgrade", "maintain", "upgrade"))


def evidence():
    return {name: ComponentEvidence(True, True, "synthetic:" + name, "fixture-v1", "a" * 64,
                                    COMPUTED - timedelta(days=2), COMPUTED - timedelta(seconds=1),
                                    "Synthetic normalized input; population/window attested by fixture")
            for name in COMPONENTS}


def adapt(values=None, proofs=None, **kwargs):
    return adapt_canonical_risk(values or inputs(), proofs or evidence(),
                                computed_at=kwargs.pop("computed_at", COMPUTED),
                                available_at=kwargs.pop("available_at", AVAILABLE),
                                decision_at=kwargs.pop("decision_at", NOW), **kwargs)


def legacy_service():
    # Differential oracle is the actual original method, not a copied formula.
    # Bypass construction: no Settings, Database, providers or ingestion objects.
    from app.one_pager import OnePagerService
    return object.__new__(OnePagerService)


def legacy_risk(values):
    fundamentals = {"companyName": "Synthetic", "sector": "Technology",
                    "beta": values.beta, "earningsGrowthAnnual": values.earnings_growth,
                    "freeCashflow": values.free_cashflow}
    if values.debt_to_ebitda is not None:
        fundamentals.update(ebitda=100.0, totalDebt=abs(values.debt_to_ebitda) * 100)
        if values.debt_to_ebitda < 0:
            fundamentals["quarterlyIncome"] = [{"ebitda": -100.0}]
    return legacy_service()._analyze(
        "SYNTH", "US", {"price": 100.0, "as_of": COMPUTED}, fundamentals,
        insider_activity=asdict(values.insider_activity) if values.insider_activity is not None else None,
        institutional_positions=asdict(values.institutional_positions) if values.institutional_positions is not None else None,
        recent_grades=[{"action": a} for a in values.recent_grade_actions] if values.recent_grade_actions is not None else None,
    )["risk_score"]


@pytest.mark.parametrize("beta,debt,growth,fcf", [
    (None, None, None, None), (.01, 0.0, .2, 0.0), (.85, 1.5, 0.0, 1.0),
    (1.12, 2.15, -.125, -123.0), (5.0, 10.0, -1.0, -1.0),
    (.5166666666666667, .35714285714285715, -.01, -1e-12),
    (1.8916666666666666, 4.928571428571429, -16 / 38, 1e-12),
    (1.0, -2.5, -.2, -100.0),
])
@pytest.mark.parametrize("signals", ["absent", "empty", "mixed", "bullish", "bearish"])
def test_differential_against_actual_one_pager(beta, debt, growth, fcf, signals):
    variants = {
        "absent": (None, None, None),
        "empty": (InsiderActivity(0, 0, 0), InstitutionalPositions(0, 0, 0, 0), ()),
        "mixed": (InsiderActivity(7, 2, 4), InstitutionalPositions(3, 7, 8, 2), ("upgrade", "downgrade", "maintain")),
        "bullish": (InsiderActivity(4, 4, 0), InstitutionalPositions(20, 30, 0, 0), ("upgrade",) * 5),
        "bearish": (InsiderActivity(4, 0, 4), InstitutionalPositions(0, 0, 20, 30), ("downgrade",) * 5),
    }
    values = CanonicalRiskInputs(beta, debt, growth, fcf, *variants[signals])
    assert canonical_risk_score(values) == legacy_risk(values)


def test_current_oracle_hash_pinned_and_module_has_no_app_or_io_imports():
    app = Path(__file__).parents[1] / "app"
    assert hashlib.sha256((app / "one_pager.py").read_bytes()).hexdigest() == ORIGIN_ONE_PAGER_SHA256
    tree = ast.parse((app / "r2d2_v2_risk_source.py").read_text())
    allowed = {"__future__", "hashlib", "json", "math", "re", "dataclasses", "datetime", "typing"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name in allowed for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.module in allowed and node.level == 0


@pytest.mark.parametrize("count", [0, 1, 3, 4, 5, 49, 50, 51])
def test_helper_thin_sample_weights_match_current_helpers(count):
    old = legacy_service()
    insider = InsiderActivity(count, count, 0)
    positions = InstitutionalPositions(0, 0, count, 0)
    actions = ("upgrade",) * count + ("maintain", "initiate")
    assert insider_net_signal(insider) == old._insider_net_signal(asdict(insider))
    assert institutional_conviction_signal(positions) == old._institutional_conviction_signal(asdict(positions))
    assert grades_momentum_signal(actions) == old._grades_momentum_signal([{"action": a} for a in actions])


def test_ready_is_full_precision_and_receipt_is_reproducible_private_json():
    values = replace(inputs(), beta=1.1234567)
    result = adapt(values)
    assert result["status"] == "READY" and result["data_available"] is True
    assert result["risk"]["value"] == canonical_risk_score(values)
    assert result["risk"]["value"] != round(result["risk"]["value"], 2)
    assert result["coverage"] == {"verified": True, "independently_verified": False}
    assert result["production_connected"] is False
    digest = result.pop("self_sha256")
    assert hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                                    allow_nan=False).encode()).hexdigest() == digest


@pytest.mark.parametrize("component", COMPONENTS)
def test_completed_null_never_uses_permissive_kernel_default(component):
    values = replace(inputs(), **{component: None})
    assert isinstance(canonical_risk_score(values), float)
    result = adapt(values)
    assert result["status"] == "COMPLETED_NULL" and result["response_complete"] is True
    assert result["risk"]["value"] is None and result["data_available"] is False
    assert "VALUE_NULL_" + component.upper() in result["diagnostics"]


@pytest.mark.parametrize("component", COMPONENTS)
def test_unknown_coverage_is_not_negative_coverage(component):
    proofs = evidence()
    proofs[component] = replace(proofs[component], coverage_verified=False)
    result = adapt(proofs=proofs)
    assert result["status"] == "COMPLETED_NULL" and result["risk"]["value"] is None
    assert "COVERAGE_UNKNOWN_" + component.upper() in result["diagnostics"]


def test_verified_empty_signals_are_zero_but_unknown_is_not_ready():
    values = replace(inputs(), insider_activity=InsiderActivity(0, 0, 0),
                     institutional_positions=InstitutionalPositions(0, 0, 0, 0), recent_grade_actions=())
    assert adapt(values)["status"] == "READY"
    proofs = evidence()
    proofs["recent_grade_actions"] = replace(proofs["recent_grade_actions"], coverage_verified=False)
    assert adapt(values, proofs)["status"] == "COMPLETED_NULL"


def test_missing_response_does_not_become_completed_null():
    proofs = evidence()
    proofs["beta"] = replace(proofs["beta"], response_complete=False, available_at=None)
    result = adapt(proofs=proofs)
    assert result["status"] == "INCOMPLETE" and result["response_complete"] is False
    assert result["risk"] is None


@pytest.mark.parametrize("change", ["source_after_receipt", "receipt_after_compute", "missing_clock"])
def test_completed_response_with_unproven_causality_is_null(change):
    proofs = evidence()
    changes = {"source_after_receipt": {"source_at": COMPUTED},
               "receipt_after_compute": {"available_at": COMPUTED + timedelta(microseconds=1)},
               "missing_clock": {"source_at": None}}
    proofs["beta"] = replace(proofs["beta"], **changes[change])
    result = adapt(proofs=proofs)
    assert result["status"] == "COMPLETED_NULL" and result["risk"]["value"] is None


def test_future_response_cannot_be_represented_as_available_at_decision():
    proofs = evidence()
    proofs["beta"] = replace(proofs["beta"], available_at=NOW + timedelta(seconds=1))
    assert adapt(proofs=proofs)["status"] == "INCOMPLETE"
    assert adapt(computed_at=NOW, available_at=NOW + timedelta(seconds=1))["status"] == "INCOMPLETE"
    assert adapt(computed_at=None, available_at=None)["status"] == "INCOMPLETE"


def test_quote_refresh_or_later_poll_does_not_rejuvenate_risk_clock():
    old = adapt()
    quote_row = {"as_of": NOW, "risk_score": old["risk"]["value"]}
    quote_row["as_of"] = NOW + timedelta(days=30)  # same score, newly observed quote
    new = adapt(decision_at=quote_row["as_of"])
    assert new["risk"] == old["risk"]
    assert new["calculation_sha256"] == old["calculation_sha256"]
    assert new["self_sha256"] != old["self_sha256"]
    assert new["risk"]["source_at"] == COMPUTED.isoformat()
    assert new["ttl_policy"] == "NOT_DEFINED_BY_THIS_ADAPTER"
    assert new["status"] == "READY"  # no invented 10s/24h risk TTL


@pytest.mark.parametrize("value", [True, False, "1.2", float("nan"), float("inf"), float("-inf"), 10**400])
def test_non_native_or_nonfinite_number_fails_closed(value):
    with pytest.raises(ValueError, match="NUMBER_INVALID_BETA"):
        adapt(replace(inputs(), beta=value))


@pytest.mark.parametrize("value", [True, -1, 1.5, "2"])
def test_invalid_counts_fail_closed(value):
    with pytest.raises(ValueError, match="COUNTS_INVALID"):
        adapt(replace(inputs(), insider_activity=InsiderActivity(4, value, 0)))


def test_inconsistent_counts_flags_and_invalid_clocks_fail_closed():
    with pytest.raises(ValueError, match="INSIDER_COUNTS_INCONSISTENT"):
        adapt(replace(inputs(), insider_activity=InsiderActivity(1, 1, 1)))
    proofs = evidence()
    proofs["beta"] = replace(proofs["beta"], coverage_verified="true")
    with pytest.raises(ValueError, match="EVIDENCE_FLAGS_INVALID"):
        adapt(proofs=proofs)
    with pytest.raises(ValueError, match="DECISION_CLOCK_INVALID"):
        adapt(decision_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="ASSESSMENT_CLOCK_ORDER_INVALID"):
        adapt(computed_at=NOW, available_at=COMPUTED)


def test_missing_provenance_and_payload_hash_cannot_be_ready():
    proofs = evidence()
    proofs["beta"] = replace(proofs["beta"], source_version="", payload_sha256="not-a-hash")
    result = adapt(proofs=proofs)
    assert result["status"] == "COMPLETED_NULL"
    assert "PAYLOAD_HASH_INVALID_BETA" in result["diagnostics"]
    assert "PROVENANCE_MISSING_BETA" in result["diagnostics"]


def test_no_silent_drop_or_addition_of_evidence_components():
    for invalid in ({k: v for k, v in evidence().items() if k != "beta"},
                    {**evidence(), "quote": evidence()["beta"]}):
        with pytest.raises(ValueError, match="EVIDENCE_COMPONENTS_INVALID"):
            adapt(proofs=invalid)
