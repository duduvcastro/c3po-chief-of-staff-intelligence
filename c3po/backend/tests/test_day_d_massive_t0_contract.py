from __future__ import annotations

from decimal import Decimal, ROUND_CEILING
import json
from pathlib import Path

from app.day_d_replay.qualification_scope import (
    QUALIFICATION_SESSION_DATES,
    QUALIFICATION_TICK_DATASETS,
)


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
        (Decimal(thresholds["authorized_first_byte_scope_bytes"]) * Decimal("1.05"))
        .to_integral_value(rounding=ROUND_CEILING)
    )

    assert contract["status"] == "frozen_by_six_hands"
    assert measurement["source_csv_files_downloaded"] == 0
    assert measurement["minute_aggregates_planned_bytes"] == (
        measurement["all_datasets_planned_bytes"]
        - measurement["trades_and_quotes_planned_bytes"]
    )
    assert thresholds["per_session_abort_bytes"] == expected_session_limit
    assert thresholds["local_spool_ceiling_bytes"] == expected_session_limit * 3
    assert thresholds["authorized_first_byte_scope_bytes"] == 131_006_214_944
    assert thresholds["campaign_pause_bytes"] == expected_campaign_limit
    assert thresholds["full_sweep_bytes_are_not_the_campaign_denominator"] is True
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
    assert approvals["dedicated_100_gib_lightsail_disk"]["container_bind_verified"] is True
    assert approvals["dedicated_100_gib_lightsail_disk"]["disk_guard_measures_path"] == (
        "/app/day-d-data"
    )
    assert approvals["backblaze_b2_object_storage"]["checksum_roundtrip_verified"] is True
    assert approvals["backblaze_b2_object_storage"][
        "object_lock_and_version_retention_verified"
    ] is True
    assert approvals["backblaze_b2_object_storage"][
        "restore_drill_requires_temporary_cap_usd_per_day"
    ] == 0.5
    assert retention["minute_aggregates"]["retain_indefinitely"] is True
    assert len(retention["full_ticks"]["qualification_sessions"]) == 12
    assert {
        item.isoformat() for item in QUALIFICATION_SESSION_DATES
    } == set(retention["full_ticks"]["qualification_sessions"])
    assert QUALIFICATION_TICK_DATASETS == {"trades", "quotes"}
    assert retention["full_ticks"]["official_replay_window"]["sessions"] == 252
    assert retention["symbol_slices"]["universe_size"] == 61
    assert retention["all_five_year_raw_ticks_archived"] is False
    assert contract["first_byte_gate"]["historical_download_authorized"] is False
    deletion = approvals["qualified_tick_lot_local_deletion"]
    assert deletion["approved"] is True
    assert deletion["minute_aggregates_excluded"] is True
    assert deletion["largest_raw_object_restore_required_per_lot"] is True


def test_ingestion_policy_forbids_silent_clamping_and_accounts_for_every_row() -> None:
    policy = _json("massive_ingestion_policy_v1.json")
    normalization = policy["normalization_policy"]
    counters = policy["counters"]

    assert policy["status"] == "frozen_by_six_hands"
    assert normalization["source_price_clamping_allowed"] is False
    assert normalization["source_size_clamping_allowed"] is False
    assert normalization["source_timestamp_clamping_allowed"] is False
    assert normalization["missing_value_imputation_allowed"] is False
    assert normalization["accounting_identity"] == (
        "raw_rows_seen == emitted_rows + dropped_rows + filtered_rows"
    )
    assert normalization["unknown_drop_reason_action"] == (
        "fail_and_quarantine_without_partial_normalized_artifact"
    )
    assert counters["clamped_rows_must_equal"] == 0
    assert counters["imputed_rows_must_equal"] == 0
    assert policy["qualification"]["official_replay_ready_before_review"] is False
    assert policy["qualification"]["quality_drop_rate_thresholds"] == {
        "trades": 0.005,
        "quotes": 0.01,
    }


def test_stage1_stays_locked_until_infrastructure_and_r1_are_verified() -> None:
    authorization = _json("stage1_authorization.json")
    requirements = set(authorization["required_before_first_download"])

    assert authorization["scope"]["bulk_download_authorized"] is False
    assert authorization["owner_approvals"]["hybrid_download_and_retention_scope_approved"] is True
    assert requirements == {
        "review_and_merge_first_byte_gate_pr",
        "explicitly_enable_C3PO_DAY_D_HISTORICAL_DOWNLOAD_AUTHORIZED_after_reviewed_merge",
    }
    assert authorization["scope"]["official_252_session_tick_window_authorized"] is False
    assert authorization["scope"]["limited_first_byte_scope_bytes"] == 131_221_198_632
    assert authorization["scope"]["campaign_pause_bytes"] == 137_782_258_564
    assert authorization["frozen_contracts"]["massive_minute_extension"] == (
        "day_d/massive_minute_extension_20260903_contract.json"
    )
    assert authorization["scope"]["qualified_tick_lot_local_deletion_authorized"] is True
    assert authorization["scope"]["minute_aggregate_local_deletion_authorized"] is False


def test_compose_can_bind_the_dedicated_disk_without_changing_container_path() -> None:
    compose = (ROOT / "compose.yml").read_text(encoding="utf-8")
    root_env = (ROOT.parent / ".env.example").read_text(encoding="utf-8")

    dedicated_mount = (
        "${C3PO_DAY_D_DATA_MOUNT_SOURCE:-c3po_day_d_data}:/app/day-d-data"
    )
    assert compose.count(dedicated_mount) >= 2
    assert "c3po_microstructure_raw:/app/microstructure-raw" not in compose
    assert (
        "C3PO_R2D2_MICROSTRUCTURE_RAW_DIR: "
        "/app/day-d-data/provider=eodhd/microstructure/raw"
    ) in compose
    assert "C3PO_DAY_D_DATA_MOUNT_SOURCE=c3po_day_d_data" in root_env
    assert "C3PO_DAY_D_DATA_MOUNT_SOURCE=/mnt/day-d-data" in root_env


def test_production_deploy_uses_the_preserved_root_env_for_compose() -> None:
    pipeline = (ROOT.parent / ".github" / "workflows" / "c3po-pipeline.yml").read_text(
        encoding="utf-8"
    )

    assert pipeline.count("docker compose --env-file .env -f c3po/compose.yml") >= 4
    assert "docker compose -f c3po/compose.yml" not in pipeline
