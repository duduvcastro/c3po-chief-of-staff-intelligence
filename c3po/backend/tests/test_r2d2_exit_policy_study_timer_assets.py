from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "r2d2-exit-policy-study-2026-08-27.sh"
SERVICE = ROOT / "ops" / "systemd" / "r2d2-exit-policy-study-2026-08-27.service"
TIMER = ROOT / "ops" / "systemd" / "r2d2-exit-policy-study-2026-08-27.timer"
WORKFLOW = (
    ROOT / ".github" / "workflows" / "install-r2d2-exit-policy-study-2026-08-27.yml"
)

INPUT_CUTOFF_AT = "2026-08-25T13:30:15.948946+00:00"
LEDGER_SHA256 = "51f616bc377329f242d5340eae25b24cecf5be7532f9a89e4e45ec5d67dbb316"
MINUTE_MANIFEST_SHA256 = (
    "c615d27f297ed80f030c1c95318401d197a58b0d2f906f41746666e62539ba9f"
)


def test_one_shot_timer_is_server_side_and_date_locked() -> None:
    timer = TIMER.read_text(encoding="utf-8")
    service = SERVICE.read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")

    assert "OnCalendar=2026-08-27 03:15:00 UTC" in timer
    assert "Persistent=true" in timer
    assert "Unit=r2d2-exit-policy-study-2026-08-27.service" in timer
    assert "ExecStart=/usr/local/sbin/r2d2-exit-policy-study-2026-08-27" in service
    assert "RequiresMountsFor=/mnt/day-d-data" in service
    assert '"$sp_date" != 2026-08-27' in script
    assert '"$sp_minutes" -lt 15' in script
    assert '"$sp_minutes" -ge 480' in script


def test_runner_uses_the_exact_frozen_input_contract_for_plan_and_run() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert f"INPUT_CUTOFF_AT={INPUT_CUTOFF_AT}" in script
    assert f"EXPECTED_LEDGER_SHA256={LEDGER_SHA256}" in script
    assert f"EXPECTED_MINUTE_MANIFEST_SHA256={MINUTE_MANIFEST_SHA256}" in script
    assert "EXPECTED_LEDGER_ROWS=783" in script
    assert "EXPECTED_EPISODES=375" in script
    assert "--amendment-one \"$AMENDMENT\"" in script
    assert script.count('"${runner_contract[@]}"') == 2
    assert "cmp -s \"$PLAN\" \"$plan_at_run_tmp\"" in script
    assert '"frozen_probe_decomposition": decomposition == expected_decomposition' in script
    assert '"four_coverage_censored_episodes"' in script


def test_installer_waits_for_deploy_and_validates_before_arming() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert 'cat .deploy-version 2>/dev/null || true' in workflow
    assert f"INPUT_CUTOFF_AT={INPUT_CUTOFF_AT}" in workflow
    assert f"EXPECTED_LEDGER_SHA256={LEDGER_SHA256}" in workflow
    assert f"EXPECTED_MINUTE_MANIFEST_SHA256={MINUTE_MANIFEST_SHA256}" in workflow
    assert 'plan.get("ledger_rows") == 783' in workflow
    assert 'plan.get("episodes") == 375' in workflow
    assert "ServerAliveInterval=30" in workflow
    assert "ServerAliveCountMax=20" in workflow
    assert 'systemctl enable --now r2d2-exit-policy-study-2026-08-27.timer' in workflow
    assert '[ "$next_elapse_utc" = 2026-08-27T03:15:00Z ]' in workflow
