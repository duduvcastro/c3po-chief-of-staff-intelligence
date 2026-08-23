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


def test_stage1_authorization_requires_t0_and_disk_guard_before_download() -> None:
    contract = json.loads(
        (ROOT / "docs" / "day_d" / "stage1_authorization.json").read_text(encoding="utf-8")
    )
    requirements = set(contract["required_before_first_download"])

    assert "numeric_T0_disk_and_host_capacity_thresholds_frozen" in requirements
    assert "read_only_plan_reports_remote_object_sizes" in requirements
    assert "local_disk_guard_passes" in requirements
    assert contract["secrets_policy"]["credentials_in_chat_forbidden"] is True
