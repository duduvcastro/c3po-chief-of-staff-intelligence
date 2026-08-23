import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_stage1_authorization_supersedes_only_the_provider_purchase_block() -> None:
    contract = json.loads(
        (ROOT / "docs" / "day_d" / "stage1_authorization.json").read_text(encoding="utf-8")
    )

    assert contract["provider"]["plan"] == "Stocks Advanced"
    assert contract["scope"]["purchase_authorized"] is True
    assert contract["scope"]["bulk_download_authorized"] is False
    assert contract["scope"]["raw_capture_authorized"] is False
    assert contract["scope"]["official_replay_authorized"] is False
    assert contract["scope"]["production_trading_change_authorized"] is False
    assert contract["supersedes_stage0_prohibition_for"] == ["purchase_polygon"]
    assert "enable_raw_capture" in contract["does_not_supersede_stage0_prohibition_for"]


def test_stage1_authorization_requires_verified_storage_and_ingestion_policy() -> None:
    contract = json.loads(
        (ROOT / "docs" / "day_d" / "stage1_authorization.json").read_text(encoding="utf-8")
    )
    requirements = set(contract["required_before_first_download"])

    assert "dedicated_100_gib_disk_provisioned_mounted_and_verified" in requirements
    assert "backblaze_b2_account_bucket_credentials_and_checksum_roundtrip_verified" in requirements
    assert "massive_ingestion_policy_v1_frozen_after_six_hands_review" in requirements
    assert "campaign_byte_accounting_and_pause_guard_implemented_and_tested" in requirements
    assert contract["owner_approvals"]["hybrid_download_and_retention_scope_approved"] is True
    assert contract["secrets_policy"]["credentials_in_chat_forbidden"] is True
