"""E3 implementation identity and formal release-receipt boundary.

Importing this module performs no I/O. The runtime explicitly hashes its own
installed source files during release verification / collector construction.
The resulting descriptor is not an approval. Receipts below are records pinned
by the operator; their shape and cross-bindings do not prove human authorship or
replace independent audits and publication of the three actual consents.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

EARNINGS_AMENDMENT_SHA = "3319407afcd7760668e6ec73bb4686ecb95a38eecf47fc157050899f80a6cc9c"
EARNINGS_CLOSED_MANIFEST_SHA = "1a927ca41df89ccb28a276726626672b7d76a9e828f12e4fc5b126860dbb4e72"
BASE_SIGNED_MANIFEST_SHA = "eabbe18057b7e5823535dd61e93c5190b33f8c7ac80b9118229b7908f974f4d0"
AMENDMENT_ONE_SHA = "3a25b9929d0c65aa97fe90b9c9cfc7dd904fedde23df884e8e42f199ae2e5ff4"
CONSENT_SCHEMA = "R2D2_V2_EARNINGS_PACKAGE_CONSENT_V1"
RELEASE_SCHEMA = "R2D2_V2_RELEASE_V3"
STATE_SCHEMA = "R2D2_V2_SHADOW_STATE_V3"
EXPORT_SCHEMA = "R2D2_V2_COHORT_EXPORT_V3"
INFERENCE_SCHEMA = "R2D2_V2_INFERENCE_INPUT_V3"
PACKAGE_FILES = (
    "r2d2_v2_earnings_package.py", "r2d2_v2_earnings_policy.py",
    "r2d2_v2_earnings_events.py", "r2d2_v2_contract.py", "r2d2_v2_portfolio.py",
    "r2d2_v2_sources.py", "r2d2_v2_shadow.py", "r2d2_v2_inference_input.py",
    "r2d2_v2_shadow_worker.py", "config.py",
)


def _digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True, allow_nan=False).encode("utf-8")
    return sha256(raw).hexdigest()


def earnings_contract() -> dict[str, Any]:
    """Versioned data-boundary descriptor; it is not a new statistical policy."""
    return {
        "schema": "R2D2_V2_EARNINGS_DATA_CONTRACT_V1",
        "base_signed_manifest_sha": BASE_SIGNED_MANIFEST_SHA,
        "amendment_one_sha": AMENDMENT_ONE_SHA,
        "earnings_amendment_sha": EARNINGS_AMENDMENT_SHA,
        "earnings_closed_manifest_sha": EARNINGS_CLOSED_MANIFEST_SHA,
        "policy_rule": "EXCLUSION_RULE_V1",
        "component_keys": ["available_at", "coverage_verified", "events", "evidence",
                           "exclusion", "policy", "source_at", "window_end", "window_start"],
        "snapshot_envelope_schema": "V2_SHADOW_SOURCE_SNAPSHOT_V2",
        "release_schema": RELEASE_SCHEMA, "state_schema": STATE_SCHEMA,
        "export_schema": EXPORT_SCHEMA, "inference_schema": INFERENCE_SCHEMA,
        "live_event_granularities": ["AMC", "BMO", "DAY", "INSTANT"],
        "admission_exclusion_clock": "nominal 10:00 America/New_York",
        "admission_causal_capture_window": "[10:00,10:01) America/New_York",
        "live_exclusion_clock": "actual episode opened_at",
        "live_event_required_fields": ["earnings_policy_sha", "round_id", "round_session",
            "round_received_at", "observation_window", "earnings_event_id", "revision_sha256",
            "event_date", "granularity"],
        "live_event_at_rule": "required only for INSTANT; key absent for AMC/BMO/DAY",
        "live_revision_instant_encoding": "UTC-normalized semantic instant; raw input retained",
        "round_session_rule": "official target session, independent of actual delayed receipt date",
        "round_receipt_rule": "actual receipt at or after 18:00 New York target and after official close",
        "observation_target": "18:00 America/New_York after each official session close",
        "cohort_sizes": [40, 60], "maturity_session_indices": [49, 69],
        "calibration_protocol": "C3PO-V2-CAL-3", "estimator_algorithm_changed": False,
        "legacy_earnings_component_accepted": False,
        "descriptor_is_authorization": False,
    }


def implementation_contract_sha() -> str:
    return _digest(earnings_contract())


def implementation_package() -> dict[str, Any]:
    """Hash installed bytes explicitly, once at each runtime trust boundary.

    The descriptor includes this module without a hardcoded package digest,
    avoiding self-referential hashing. Documentation/templates are not hashed
    here because the deployed backend image need not contain repo docs.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parent
    return {
        "schema": "R2D2_V2_EARNINGS_IMPLEMENTATION_PACKAGE_V1",
        "status": "DESCRIPTOR_NOT_AUTHORIZATION",
        "contract": earnings_contract(),
        "implementation_contract_sha": implementation_contract_sha(),
        "source_sha256": {name: sha256((root / name).read_bytes()).hexdigest() for name in PACKAGE_FILES},
    }


def implementation_package_sha() -> str:
    return _digest(implementation_package())
