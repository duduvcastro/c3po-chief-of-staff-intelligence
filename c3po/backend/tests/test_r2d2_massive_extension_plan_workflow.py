from __future__ import annotations

import ast
from pathlib import Path


def test_massive_extension_plan_is_exact_head_only_and_auditable() -> None:
    root = Path(__file__).resolve().parents[3]
    workflow = (
        root / ".github" / "workflows" / "r2d2-massive-extension-plan.yml"
    ).read_text(encoding="utf-8")

    assert "PLAN MASSIVE MINUTE EXTENSION 2026-08-24 2026-09-02" in workflow
    assert "python -m app.day_d_replay.massive_plan_sweep" in workflow
    assert "--start-date 2026-08-24" in workflow
    assert "--end-date 2026-09-02" in workflow
    assert workflow.count("--dataset minute_aggregates") == 1
    assert "--no-deps --user \"$host_identity\"" in workflow
    assert "--download" not in workflow
    assert "source.csv" not in workflow
    assert 'report.get("downloaded") is not False' in workflow
    assert 'report.get("source_csv_files") != 0' in workflow
    assert 'campaign.get("complete_sessions") != len(expected_sessions)' in workflow
    assert 'campaign.get("partial_sessions")' in workflow
    assert 'campaign.get("non_session_weekdays")' in workflow
    assert "observed_sessions != expected_sessions" in workflow
    assert 'sorted(report.get("datasets", {})) != ["minute_aggregates"]' in workflow
    assert "manifest_sha256" in workflow
    assert "extension plan manifest self-hash mismatch" in workflow
    assert "extension plan report hash mismatch" in workflow
    assert "sha256sum -c SHA256SUMS" in workflow
    assert "retention-days: 30" in workflow
    assert "gh pr comment 348" in workflow


def test_massive_extension_plan_pins_all_eight_required_sessions() -> None:
    root = Path(__file__).resolve().parents[3]
    workflow = (
        root / ".github" / "workflows" / "r2d2-massive-extension-plan.yml"
    ).read_text(encoding="utf-8")
    expected = (
        "2026-08-24",
        "2026-08-25",
        "2026-08-26",
        "2026-08-27",
        "2026-08-28",
        "2026-08-31",
        "2026-09-01",
        "2026-09-02",
    )
    session_block = workflow.split("expected_sessions = [", 1)[1].split("]", 1)[0]
    observed = tuple(ast.literal_eval(f"[{session_block}]"))
    assert observed == expected
