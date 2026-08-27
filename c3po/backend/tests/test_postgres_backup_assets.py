from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "c3po-postgres-backup.sh"
SERVICE = ROOT / "ops" / "systemd" / "c3po-postgres-backup.service"
TIMER = ROOT / "ops" / "systemd" / "c3po-postgres-backup.timer"
RUNBOOK = ROOT / "c3po" / "docs" / "OPS_RESILIENCE_RUNBOOK.md"


def test_backup_timer_is_server_side_daily_and_persistent() -> None:
    timer = TIMER.read_text(encoding="utf-8")
    service = SERVICE.read_text(encoding="utf-8")

    assert "OnCalendar=*-*-* 04:00:00 America/Sao_Paulo" in timer
    assert "Persistent=true" in timer
    assert "Unit=c3po-postgres-backup.service" in timer
    assert "ExecStart=/usr/local/sbin/c3po-postgres-backup" in service
    assert "RequiresMountsFor=/mnt/day-d-data" in service
    assert "Nice=10" in service
    assert "IOSchedulingPriority=7" in service


def test_backup_validates_before_content_addressed_upload_and_cleans_dump() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert "pg_dump -U c3po -d c3po --format=custom" in script
    assert "pg_restore --list -" in script
    assert script.index("pg_restore --list -") < script.index("app.postgres_backup_upload")
    assert "dump_sha256=$(sha256sum" in script
    assert 'rm -f "$DUMP_PATH"' in script
    assert "C3PO_HEALTHCHECK_POSTGRES_BACKUP_URL" in script
    assert "ping_healthcheck fail" in script
    assert "SHA256SUMS" in script


def test_runbook_records_offsite_and_restore_contracts() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")

    assert "2,395,020,311" in runbook
    assert "s3:PutObject" in runbook
    assert "s3:GetObject" in runbook
    assert "35 days" in runbook
    assert "366 days" in runbook
    assert "pg_restore --list" in runbook
