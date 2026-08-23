from __future__ import annotations

from decimal import Decimal, ROUND_CEILING
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _json(name: str) -> dict:
    return json.loads((ROOT / "docs" / "day_d" / name).read_text(encoding="utf-8"))


def test_massive_t0_thresholds_are_derived_from_the_canonical_sweep() -> None:
    contract = _json("massive_t0_contract.json")
    measurement = contract["canonical_measurement"]
    thresholds = contract["thresholds"]

    expected_session_limit = int(
        (Decimal(measurement["maximum_session"]["bytes"]) * Decimal("1.10"))
        .to_integral_value(rounding=ROUND_CEILING)
    )
    expected_campaign_limit = int(
        (Decimal(measurement["all_datasets_planned_bytes"]) * Decimal("1.05"))
        .to_integral_value(rounding=ROUND_CEILING)
    )

    assert contract["status"] == "frozen_by_six_hands"
    assert measurement["source_csv_files_downloaded"] == 0
    assert thresholds["per_session_abort_bytes"] == expected_session_limit
    assert thresholds["local_spool_ceiling_bytes"] == expected_session_limit * 3
    assert thresholds["campaign_pause_bytes"] == expected_campaign_limit
    assert thresholds["spool_plus_reserve_bytes"] <= thresholds["dedicated_data_disk_bytes"]
    assert thresholds["disk_headroom_after_spool_and_reserve_bytes"] == (
        thresholds["dedicated_data_disk_bytes"] - thresholds["spool_plus_reserve_bytes"]
    )
    assert thresholds["per_object_verification"]["metadata_change_action"] == (
        "abort_and_quarantine"
    )


def test_owner_approved_hybrid_retention_without_unlocking_downloads() -> None:
    contract = _json("massive_t0_contract.json")
    retention = contract["retention"]
    approvals = contract["owner_approvals"]

    assert approvals["dedicated_100_gib_lightsail_disk"]["approved"] is True
    assert approvals["hybrid_download_and_retention_scope"]["approved"] is True
    assert approvals["backblaze_b2_object_storage"]["approved"] is True
    assert approvals["backblaze_b2_object_storage"]["monthly_budget_usd"] == 15
    assert retention["minute_aggregates"]["retain_indefinitely"] is True
    assert len(retention["full_ticks"]["qualification_sessions"]) == 12
    assert retention["full_ticks"]["official_replay_window"]["sessions"] == 252
    assert retention["symbol_slices"]["universe_size"] == 61
    assert retention["all_five_year_raw_ticks_archived"] is False
    assert contract["first_byte_gate"]["historical_download_authorized"] is False


def test_ingestion_policy_forbids_silent_clamping_and_accounts_for_every_row() -> None:
    policy = _json("massive_ingestion_policy_v1.json")
    normalization = policy["normalization_policy"]
    counters = policy["counters"]

    assert policy["status"] == "proposed_for_six_hands_review"
    assert normalization["source_price_clamping_allowed"] is False
    assert normalization["source_size_clamping_allowed"] is False
    assert normalization["source_timestamp_clamping_allowed"] is False
    assert normalization["missing_value_imputation_allowed"] is False
    assert normalization["accounting_identity"] == "raw_rows_seen = emitted_rows + dropped_rows"
    assert normalization["unknown_drop_reason_action"] == "fail_dataset_build"
    assert counters["clamped_rows_must_equal"] == 0
    assert counters["imputed_rows_must_equal"] == 0
    assert policy["qualification"]["official_replay_ready_before_review"] is False


def test_stage1_stays_locked_until_infrastructure_and_r1_are_verified() -> None:
    authorization = _json("stage1_authorization.json")
    requirements = set(authorization["required_before_first_download"])

    assert authorization["scope"]["bulk_download_authorized"] is False
    assert authorization["owner_approvals"]["hybrid_download_and_retention_scope_approved"] is True
    assert "dedicated_100_gib_disk_provisioned_mounted_and_verified" in requirements
    assert "backblaze_b2_account_bucket_credentials_and_checksum_roundtrip_verified" in requirements
    assert "massive_ingestion_policy_v1_frozen_after_six_hands_review" in requirements
    assert "campaign_byte_accounting_and_pause_guard_implemented_and_tested" in requirements


def test_compose_can_bind_the_dedicated_disk_without_changing_container_path() -> None:
    compose = (ROOT / "compose.yml").read_text(encoding="utf-8")
    root_env = (ROOT.parent / ".env.example").read_text(encoding="utf-8")

    assert (
        "${C3PO_DAY_D_DATA_MOUNT_SOURCE:-c3po_day_d_data}:/app/day-d-data"
        in compose
    )
    assert "C3PO_DAY_D_DATA_MOUNT_SOURCE=c3po_day_d_data" in root_env
    assert "C3PO_DAY_D_DATA_MOUNT_SOURCE=/mnt/day-d-data" in root_env


def test_production_deploy_uses_the_preserved_root_env_for_compose() -> None:
    pipeline = (ROOT.parent / ".github" / "workflows" / "c3po-pipeline.yml").read_text(
        encoding="utf-8"
    )

    assert pipeline.count("docker compose --env-file .env -f c3po/compose.yml") == 4
    assert "docker compose -f c3po/compose.yml" not in pipeline
