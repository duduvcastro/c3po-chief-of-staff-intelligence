from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
HOST_INSTALLER = ROOT / ".github" / "workflows" / "install-host-security-v1.yml"
WEEKLY_SCAN = ROOT / ".github" / "workflows" / "container-vulnerability-scan.yml"
PIPELINE = ROOT / ".github" / "workflows" / "c3po-pipeline.yml"
APT_POLICY = ROOT / "ops" / "apt" / "52c3po-security-upgrades"
HOST_SERVICE = ROOT / "ops" / "systemd" / "c3po-host-security-snapshot.service"
HOST_TIMER = ROOT / "ops" / "systemd" / "c3po-host-security-snapshot.timer"
TRIVY_SCRIPT = ROOT / "scripts" / "c3po_trivy_scan.py"


def _scanner_module():
    spec = importlib.util.spec_from_file_location("c3po_trivy_scan", TRIVY_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_host_policy_is_security_only_and_never_reboots_automatically() -> None:
    policy = APT_POLICY.read_text(encoding="utf-8")
    service = HOST_SERVICE.read_text(encoding="utf-8")
    timer = HOST_TIMER.read_text(encoding="utf-8")

    assert "#clear Unattended-Upgrade::Allowed-Origins;" in policy
    assert "${distro_codename}-security" in policy
    assert "${distro_codename}\";" not in policy
    assert 'Unattended-Upgrade::Automatic-Reboot "false";' in policy
    assert "ReadWritePaths=/opt/chief-of-staff-digital/runtime/security" in service
    assert "OnUnitActiveSec=15min" in timer
    assert "Persistent=true" in timer


def test_host_installer_is_manual_and_verifies_the_effective_policy() -> None:
    workflow = HOST_INSTALLER.read_text(encoding="utf-8")
    parsed = yaml.safe_load(workflow)

    assert "workflow_dispatch" in parsed[True]
    assert "push" not in parsed[True]
    assert "pull_request" not in parsed[True]
    assert "schedule" not in parsed[True]
    assert "environment: production" in workflow
    assert "policy['security_only'] is True" in workflow
    assert "policy['automatic_reboot'] is False" in workflow
    assert "systemctl enable --now c3po-host-security-snapshot.timer" in workflow


def test_trivy_normalizer_counts_occurrences_and_fixable_findings() -> None:
    scanner = _scanner_module()
    payload = {
        "ArtifactName": "c3po/backend:production",
        "Metadata": {"ImageID": "sha256:test", "RepoDigests": ["repo@sha256:test"]},
        "Results": [{
            "Vulnerabilities": [
                {"Severity": "CRITICAL", "FixedVersion": "2.0"},
                {"Severity": "HIGH", "FixedVersion": ""},
                {"Severity": "HIGH", "FixedVersion": "3.0"},
                {"Severity": "MEDIUM", "FixedVersion": ""},
                {"Severity": "UNKNOWN", "FixedVersion": ""},
            ],
        }],
    }

    image = scanner.normalize_trivy_payload("backend", "c3po/backend:production", payload)

    assert image["by_severity"] == {"critical": 1, "high": 2, "medium": 1, "low": 0}
    assert image["fix_available"] == {"critical": 1, "high": 1, "medium": 0, "low": 0}
    assert image["unknown"] == 1
    assert image["finding_total"] == 5
    assert scanner.TRIVY_IMAGE == (
        "aquasec/trivy@sha256:"
        "6029bc807d46103c5511ad70574c935b683bd3d2d3a6f81a04c3e8f29f857e69"
    )


def test_trivy_scans_are_non_blocking_per_build_and_weekly_off_host() -> None:
    pipeline = PIPELINE.read_text(encoding="utf-8")
    weekly = WEEKLY_SCAN.read_text(encoding="utf-8")
    parsed = yaml.safe_load(weekly)

    assert pipeline.count("scripts/c3po_trivy_scan.py") == 2
    assert pipeline.count("continue-on-error: true") >= 4
    assert "--exclude='runtime/'" in pipeline
    assert parsed[True]["schedule"][0]["cron"] == "0 7 * * 0"
    assert "docker save c3po/backend:production c3po/web:production" in weekly
    assert "Scan the production images off-host" in weekly
    assert "scripts/c3po_trivy_scan.py" in weekly
    assert "container-production-vulnerability-report.json" in weekly
    assert "sudo install -o root -g ubuntu -m 0644" in weekly
