from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
from pathlib import Path

from app.day_d_replay.massive_campaign import (
    AUTHORIZED_SCOPE_BYTES,
    BASE_AUTHORIZED_SCOPE_BYTES,
    CAMPAIGN_PAUSE_BYTES,
    EXTENSION_MINUTE_SESSIONS,
    EXTENSION_SCOPE_BYTES,
    EXTENSION_SCOPE_REPORT_SHA256,
    MINUTE_AGGREGATE_END,
)


ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs" / "day_d"


def _json(name: str) -> dict:
    return json.loads((DOCS / name).read_text(encoding="utf-8"))


def test_massive_minute_extension_is_exactly_the_verified_head_only_plan() -> None:
    contract = _json("massive_minute_extension_20260903_contract.json")
    plan_path = (
        ROOT
        / "backend"
        / "app"
        / "day_d_replay"
        / "massive_minute_extension_20260903_plan.json"
    )
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    source = contract["source_plan"]
    extension = contract["authorized_extension"]

    observed_report_sha = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    assert observed_report_sha == source["report_sha256"]
    assert observed_report_sha == EXTENSION_SCOPE_REPORT_SHA256
    assert source["workflow_run_id"] == 33_721_558_175
    assert source["workflow_run_attempt"] == 1
    assert source["source_csv_files_downloaded"] == 0
    assert plan["mode"] == "read_only_head_only"
    assert plan["downloaded"] is False
    assert plan["source_csv_files"] == 0
    assert sorted(plan["datasets"]) == ["minute_aggregates"]
    assert plan["campaign"]["partial_sessions"] == []
    assert plan["campaign"]["non_session_weekdays"] == []

    sessions = [row["session_date"] for row in plan["sessions"]]
    assert sessions == extension["sessions"]
    assert {date.fromisoformat(value) for value in sessions} == EXTENSION_MINUTE_SESSIONS
    assert extension["session_count"] == len(sessions) == 8
    assert MINUTE_AGGREGATE_END == date(2026, 9, 2)

    measured_bytes = 0
    for row in plan["sessions"]:
        assert sorted(row["artifacts"]) == ["minute_aggregates"]
        item = row["artifacts"]["minute_aggregates"]
        session_date = row["session_date"]
        assert item["object_key"] == (
            "us_stocks_sip/minute_aggs_v1/"
            f"{session_date[:4]}/{session_date[5:7]}/{session_date}.csv.gz"
        )
        assert item["content_length"] > 0
        assert item["remote_etag"]
        measured_bytes += item["content_length"]
    assert measured_bytes == plan["datasets"]["minute_aggregates"]["sum_bytes"]
    assert measured_bytes == extension["planned_bytes"] == EXTENSION_SCOPE_BYTES


def test_massive_minute_extension_preserves_t0_and_derives_combined_budget() -> None:
    contract = _json("massive_minute_extension_20260903_contract.json")
    combined = contract["combined_campaign"]
    expected_authorized = BASE_AUTHORIZED_SCOPE_BYTES + EXTENSION_SCOPE_BYTES
    expected_pause = int(
        (Decimal(expected_authorized) * Decimal("1.05")).to_integral_value(
            rounding=ROUND_CEILING
        )
    )

    assert combined["base_t0_contract"] == "day_d/massive_t0_contract.json"
    assert combined["base_authorized_scope_bytes"] == BASE_AUTHORIZED_SCOPE_BYTES
    assert combined["extension_authorized_scope_bytes"] == EXTENSION_SCOPE_BYTES
    assert combined["authorized_scope_bytes"] == AUTHORIZED_SCOPE_BYTES == expected_authorized
    assert combined["campaign_pause_bytes"] == CAMPAIGN_PAUSE_BYTES == expected_pause
    assert combined["minute_aggregate_objects"] == 1_263
    assert combined["qualification_tick_objects"] == 24
    assert contract["authorized_extension"]["local_deletion_authorized"] is False
    assert set(contract["explicitly_not_authorized"]) >= {
        "trades_or_quotes_extension",
        "official_replay_admission",
        "production_trading_change",
        "minute_aggregate_deletion",
    }


def test_massive_minute_extension_download_workflow_is_exact_and_reduced() -> None:
    workflow = (
        ROOT.parent / ".github" / "workflows" / "r2d2-massive-minute-extension-download.yml"
    ).read_text(encoding="utf-8")
    runner = (
        ROOT / "backend" / "app" / "day_d_replay" / "massive_extension_download.py"
    ).read_text(encoding="utf-8")
    confirmation = "DOWNLOAD MASSIVE MINUTE EXTENSION 2026-08-24 2026-09-02"

    assert workflow.count(confirmation) >= 2
    assert "C3PO_DAY_D_HISTORICAL_DOWNLOAD_AUTHORIZED=true" in workflow
    assert "python -m app.day_d_replay.massive_extension_download" in workflow
    assert "(FlatFileDataset.MINUTE_AGGREGATES,)" in runner
    assert "FlatFileDataset.TRADES" not in runner
    assert "FlatFileDataset.QUOTES" not in runner
    assert "retention-days: 30" in workflow
    assert "raw_files_returned_to_ci" in workflow
    scp_sources = "\n".join(
        line for line in workflow.splitlines() if "$USER@$HOST:" in line
    )
    assert "source.csv.gz" not in scp_sources
    for session_date in sorted(value.isoformat() for value in EXTENSION_MINUTE_SESSIONS):
        assert session_date in workflow
