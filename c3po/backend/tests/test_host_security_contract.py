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
APT_HEALTHCHECK_DROPIN = (
    ROOT / "ops" / "systemd" / "apt-daily-upgrade.service.d" / "c3po-healthcheck.conf"
)
APT_HEALTHCHECK_SUCCESS = (
    ROOT / "ops" / "systemd" / "c3po-unattended-upgrades-healthcheck-success.service"
)
APT_HEALTHCHECK_FAILURE = (
    ROOT / "ops" / "systemd" / "c3po-unattended-upgrades-healthcheck-failure.service"
)
HEALTHCHECK_SCRIPT = ROOT / "scripts" / "c3po-healthcheck-ping.sh"
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
    assert "C3PO_HEALTHCHECK_UNATTENDED_UPGRADES_URL" in workflow
    assert "C3PO_HEALTHCHECK_TRIVY_URL" in workflow
    assert "C3PO_HEALTHCHECK_TRIVY_CONFIGURED" in workflow
    assert "C3PO_HEALTHCHECK_UNATTENDED_UPGRADES_CONFIGURED" in workflow
    assert "c3po-host-security.env /etc/c3po/host-security.env" in workflow
    assert "-m 0600" in workflow
    assert "systemctl start apt-daily-upgrade.service" in workflow
    assert "policy['healthcheck_configured'] is True" in workflow
    assert "policy['last_run_at']" in workflow
    assert "systemctl enable --now c3po-host-security-snapshot.timer" in workflow


def test_unattended_upgrades_has_start_success_and_failure_dead_man() -> None:
    dropin = APT_HEALTHCHECK_DROPIN.read_text(encoding="utf-8")
    success = APT_HEALTHCHECK_SUCCESS.read_text(encoding="utf-8")
    failure = APT_HEALTHCHECK_FAILURE.read_text(encoding="utf-8")
    script = HEALTHCHECK_SCRIPT.read_text(encoding="utf-8")

    assert "ExecStartPre=-/usr/local/sbin/c3po-healthcheck-ping start" in dropin
    assert "OnSuccess=c3po-unattended-upgrades-healthcheck-success.service" in dropin
    assert "OnFailure=c3po-unattended-upgrades-healthcheck-failure.service" in dropin
    assert "c3po-healthcheck-ping success" in success
    assert "c3po-healthcheck-ping fail" in failure
    assert "C3PO_HEALTHCHECK_UNATTENDED_UPGRADES_URL" in script
    assert '"${url%/}/start"' in script
    assert '"${url%/}/fail"' in script
    assert "|| true" in script


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
        "62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969"
    )
    assert scanner.TRIVY_VERSION == "0.74.0"


def test_trivy_scans_are_non_blocking_per_build_and_weekly_off_host() -> None:
    pipeline = PIPELINE.read_text(encoding="utf-8")
    weekly = WEEKLY_SCAN.read_text(encoding="utf-8")
    parsed = yaml.safe_load(weekly)

    assert pipeline.count("scripts/c3po_trivy_scan.py") == 2
    assert pipeline.count("continue-on-error: true") >= 4
    assert "--exclude='runtime/'" in pipeline
    assert parsed[True]["schedule"][0]["cron"] == "0 7 * * 0"
    assert 'docker save "$backend_image_ref" "$web_image_ref" "$db_image_ref"' in weekly
    assert "{{.Image}}|{{.Config.Image}}" in weekly
    assert "C3PO_DB_IMAGE_REF" in weekly
    assert "C3PO_ARCHIVE_SHA256" in weekly
    assert 'sha256sum "$RUNNER_TEMP/c3po-production-images.tar.gz"' in weekly
    assert "manifest.json" in weekly
    assert weekly.count("docker image inspect --format '{{.Id}}'") == 6
    assert weekly.count("--runtime-image-id") == 3
    assert '--transport-sha256 "$C3PO_IMAGE_ARCHIVE_SHA256"' in weekly
    assert "Scan the production images off-host" in weekly
    assert "scripts/c3po_trivy_scan.py" in weekly
    assert "C3PO_HEALTHCHECK_TRIVY_URL" in weekly
    assert '"${HEALTHCHECK_URL%/}/start"' in weekly
    assert '"${HEALTHCHECK_URL%/}/fail"' in weekly
    assert "--dead-man-configured" in weekly
    assert "container-production-vulnerability-report.json" in weekly
    assert "sudo install -o root -g ubuntu -m 0644" in weekly


def test_trivy_report_attests_its_own_dead_man_configuration() -> None:
    scanner = _scanner_module()
    scanner.scan_image = lambda label, reference, _work: scanner.normalize_trivy_payload(
        label,
        reference,
        {"ArtifactName": reference, "Metadata": {}, "Results": []},
    )

    report = scanner.build_report(
        ["backend=c3po/backend:production"],
        scope="production_runtime",
        revision="test",
        dead_man_configured=True,
    )

    assert report["scan_status"] == "complete"
    assert report["dead_man_configured"] is True
    assert report["images"][0]["runtime_image_id"] == report["images"][0]["image_id"]
    assert report["source_transport"] == {
        "kind": "local_docker_store",
        "sha256": None,
    }
    assert report["report_sha256"] == scanner.report_sha256(report)


def test_trivy_report_chains_runtime_ids_to_verified_archive() -> None:
    scanner = _scanner_module()
    scanner.scan_image = lambda label, reference, _work: scanner.normalize_trivy_payload(
        label,
        reference,
        {
            "ArtifactName": reference,
            "Metadata": {"ImageID": "sha256:loaded"},
            "Results": [],
        },
    )
    archive_sha256 = "a" * 64

    report = scanner.build_report(
        ["database=postgres:16-alpine"],
        scope="production_runtime",
        revision="test",
        dead_man_configured=True,
        runtime_image_specs=["database=sha256:runtime-manifest"],
        transport_sha256=archive_sha256,
    )

    assert report["schema"] == "C3PO_CONTAINER_VULNERABILITY_REPORT-v2"
    assert report["images"][0]["image_id"] == "sha256:loaded"
    assert report["images"][0]["runtime_image_id"] == "sha256:runtime-manifest"
    assert report["source_transport"] == {
        "kind": "verified_docker_archive",
        "sha256": archive_sha256,
    }
    assert report["report_sha256"] == scanner.report_sha256(report)


def test_trivy_container_does_not_leave_root_owned_runner_cache() -> None:
    source = TRIVY_SCRIPT.read_text(encoding="utf-8")

    assert '"--user"' in source
    assert 'f"{os.getuid()}:{os.getgid()}"' in source
    assert '"--group-add"' in source
    assert 'f"{cache_path}:/tmp/trivy-cache"' in source
    assert '"--cache-dir"' in source
