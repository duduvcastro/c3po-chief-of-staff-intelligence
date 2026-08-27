from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
INSTALLER = ROOT / ".github" / "workflows" / "install-resilience-ops-v1.yml"
RESTORE = ROOT / ".github" / "workflows" / "postgres-backup-restore-drill.yml"
BACKUP_SCRIPT = ROOT / "scripts" / "c3po-postgres-backup.sh"


def test_resilience_installer_is_manual_production_and_secret_driven() -> None:
    workflow = INSTALLER.read_text(encoding="utf-8")
    parsed = yaml.safe_load(workflow)

    assert "workflow_dispatch" in parsed[True]
    assert "schedule" not in parsed[True]
    assert "environment: production" in workflow
    assert "C3PO_POSTGRES_BACKUP_SECRET_ACCESS_KEY" in workflow
    assert "C3PO_SENTRY_DSN" in workflow
    assert "C3PO_HEALTHCHECK_POSTGRES_BACKUP_URL" in workflow
    assert "C3PO_HEALTHCHECK_POSTGRES_RESTORE_URL" in workflow
    assert 'payload["C3PO_HEALTHCHECK_POSTGRES_RESTORE_CONFIGURED"] = "true"' in workflow
    assert "systemctl enable --now c3po-postgres-backup.timer" in workflow
    assert "install -o root -g ubuntu -m 0750" in workflow
    assert "--force-recreate" in workflow
    assert "api investor-relations-worker valuation-worker server-usage-worker r2d2-worker" in workflow


def test_restore_drill_runs_outside_host_and_never_has_write_credentials() -> None:
    workflow = RESTORE.read_text(encoding="utf-8")
    parsed = yaml.safe_load(workflow)

    assert parsed[True]["schedule"][0]["cron"] == "0 10 1 * *"
    assert "C3PO_POSTGRES_RESTORE_ACCESS_KEY_ID" in workflow
    assert "C3PO_POSTGRES_RESTORE_SECRET_ACCESS_KEY" in workflow
    assert "C3PO_POSTGRES_BACKUP_ACCESS_KEY_ID" not in workflow
    assert "s3api get-object" in workflow
    assert "pg_restore --list /tmp/backup.dump" in workflow
    assert "pg_restore -U postgres -d c3po_restore" in workflow
    assert '"backup_size_bytes"' in workflow
    assert '"pg_restore_list_valid"' in workflow
    assert "critical_tables_present" in workflow
    assert "C3PO_HEALTHCHECK_POSTGRES_RESTORE_URL" in workflow


def test_backup_validates_the_dump_from_stdin_without_a_literal_dash() -> None:
    script = BACKUP_SCRIPT.read_text(encoding="utf-8")

    assert 'exec -T db pg_restore --list \\\n  <"$DUMP_PATH"' in script
    assert "pg_restore --list -" not in script
    assert '--user "$(id -u):$(id -g)"' in script
