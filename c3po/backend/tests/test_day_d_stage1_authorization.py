import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_stage1_authorization_allows_only_purchase_and_passive_capture() -> None:
    contract = json.loads(
        (ROOT / "docs" / "day_d" / "stage1_authorization.json").read_text(encoding="utf-8")
    )

    assert contract["provider"]["plan"] == "Stocks Advanced"
    assert contract["scope"]["purchase_authorized"] is True
    assert contract["scope"]["bulk_download_authorized"] is False
    assert contract["scope"]["limited_first_byte_download_authorized_after_reviewed_merge"] is True
    assert contract["scope"]["official_252_session_tick_window_authorized"] is False
    assert contract["scope"]["raw_capture_authorized"] is True
    assert contract["scope"]["raw_capture_runtime_default_enabled"] is False
    assert contract["scope"]["raw_capture_scope"] == (
        "passive_eodhd_raw_plus_derived_aggregates_and_t0_resource_telemetry_only"
    )
    assert contract["scope"]["official_replay_authorized"] is False
    assert contract["scope"]["production_trading_change_authorized"] is False
    assert contract["scope"]["qualified_tick_lot_local_deletion_authorized"] is True
    assert contract["scope"]["minute_aggregate_local_deletion_authorized"] is False
    assert contract["supersedes_stage0_prohibition_for"] == [
        "purchase_polygon",
        "enable_raw_capture",
    ]
    assert "enable_raw_capture" not in contract["does_not_supersede_stage0_prohibition_for"]
    assert "run_official_replay" in contract["does_not_supersede_stage0_prohibition_for"]


def test_stage1_authorization_requires_verified_storage_and_ingestion_policy() -> None:
    contract = json.loads(
        (ROOT / "docs" / "day_d" / "stage1_authorization.json").read_text(encoding="utf-8")
    )
    requirements = set(contract["required_before_first_download"])

    assert requirements == {
        "review_and_merge_first_byte_gate_pr",
        "explicitly_enable_C3PO_DAY_D_HISTORICAL_DOWNLOAD_AUTHORIZED_after_reviewed_merge",
    }
    assert set(contract["completed_first_byte_requirements"]) == {
        "dedicated_100_gib_disk_provisioned_mounted_and_verified",
        "backblaze_b2_account_bucket_credentials_and_checksum_roundtrip_verified",
        "massive_ingestion_policy_v1_frozen_after_six_hands_review",
        "campaign_byte_accounting_and_pause_guard_implemented_and_tested",
    }
    assert contract["owner_approvals"]["hybrid_download_and_retention_scope_approved"] is True
    assert contract["secrets_policy"]["credentials_in_chat_forbidden"] is True
