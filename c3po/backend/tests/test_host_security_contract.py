from __future__ import annotations

import importlib.util
from pathlib import Path
import re

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
HOST_INSTALLER = ROOT / ".github" / "workflows" / "install-host-security-v1.yml"
DAILY_SCAN = ROOT / ".github" / "workflows" / "container-vulnerability-scan.yml"
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
REMEDIATION_DISPATCH = (
    ROOT / ".github" / "scripts" / "c3po_dispatch_remediation.sh"
)
POSITIVE_FIXTURE = (
    ROOT / "c3po" / "security" / "fixtures" / "container-remediation-positive-v1.json"
)
OPS_RUNBOOK = ROOT / "c3po" / "docs" / "OPS_RESILIENCE_RUNBOOK.md"


def _scanner_module():
    spec = importlib.util.spec_from_file_location("c3po_trivy_scan", TRIVY_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(character: str) -> str:
    assert len(character) == 1 and character in "0123456789abcdef"
    return f"sha256:{character * 64}"


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
        "Metadata": {
            "ImageID": "sha256:test",
            "DiffIDs": ["sha256:layer-a", "sha256:layer-b"],
            "RepoDigests": ["repo@sha256:test"],
        },
        "Results": [{
            "Vulnerabilities": [
                {
                    "VulnerabilityID": "CVE-TEST-CRITICAL",
                    "Severity": "CRITICAL",
                    "FixedVersion": "2.0",
                    "PkgName": "critical-lib",
                    "InstalledVersion": "1.0",
                },
                {
                    "VulnerabilityID": "CVE-TEST-1",
                    "Severity": "HIGH",
                    "FixedVersion": "",
                    "PkgName": "sample-lib",
                    "InstalledVersion": "1.0",
                },
                {
                    "VulnerabilityID": "CVE-TEST-HIGH",
                    "Severity": "HIGH",
                    "FixedVersion": "3.0",
                    "PkgName": "high-lib",
                    "InstalledVersion": "2.0",
                },
                {"Severity": "MEDIUM", "FixedVersion": ""},
                {"Severity": "UNKNOWN", "FixedVersion": ""},
            ],
        }],
    }

    image = scanner.normalize_trivy_payload("backend", "c3po/backend:production", payload)

    assert image["by_severity"] == {"critical": 1, "high": 2, "medium": 1, "low": 0}
    assert image["fix_available"] == {"critical": 1, "high": 1, "medium": 0, "low": 0}
    assert image["fixable_high_critical"] == [
        {
            "vulnerability_id": "CVE-TEST-CRITICAL",
            "severity": "critical",
            "package": "critical-lib",
            "installed_version": "1.0",
            "fixed_version": "2.0",
            "target": "unknown",
        },
        {
            "vulnerability_id": "CVE-TEST-HIGH",
            "severity": "high",
            "package": "high-lib",
            "installed_version": "2.0",
            "fixed_version": "3.0",
            "target": "unknown",
        },
    ]
    assert image["unfixed_high_critical"] == [{
        "vulnerability_id": "CVE-TEST-1",
        "severity": "high",
        "package": "sample-lib",
        "installed_version": "1.0",
        "fixed_version": "",
        "target": "unknown",
    }]
    assert image["rootfs_layers"] == ["sha256:layer-a", "sha256:layer-b"]
    assert image["unknown"] == 1
    assert image["finding_total"] == 5
    assert scanner.TRIVY_IMAGE == (
        "aquasec/trivy@sha256:"
        "62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969"
    )
    assert scanner.TRIVY_VERSION == "0.74.0"


def test_trivy_v074_diffids_are_the_ordered_cross_store_identity() -> None:
    scanner = _scanner_module()
    config_image_id = _sha256("a")
    runtime_image_id = _sha256("b")
    rootfs_layers = [_sha256("c"), _sha256("d")]
    image = scanner.normalize_trivy_payload(
        "database",
        "c3po/database:production-scan",
        {
            "Metadata": {
                "ImageID": config_image_id,
                "DiffIDs": rootfs_layers,
            },
            "Results": [],
        },
    )
    live_origin = {
        "image_ref": "c3po/database:production",
        "image_id": runtime_image_id,
        "config_image_id": config_image_id,
        "rootfs_layers": rootfs_layers,
    }

    scanner.verify_origin_identity(image, live_origin)
    assert image["image_id"] != live_origin["image_id"]
    with pytest.raises(RuntimeError, match="scanned ordered RootFS"):
        scanner.verify_origin_identity(
            image,
            {**live_origin, "rootfs_layers": list(reversed(rootfs_layers))},
        )
    with pytest.raises(RuntimeError, match="Trivy config image ID"):
        scanner.verify_origin_identity(
            {**image, "image_id": ""},
            live_origin,
        )


def test_docker_archive_manifest_config_ids_are_unique_and_fail_closed() -> None:
    scanner = _scanner_module()
    backend_config = "a" * 64
    web_config = "b" * 64
    database_config = "c" * 64
    manifest = [
        {"Config": f"{backend_config}.json", "RepoTags": ["c3po/backend:production"]},
        {"Config": f"{web_config}.json", "RepoTags": ["c3po/web:production"]},
        {
            "Config": f"blobs/sha256/{database_config}",
            "RepoTags": ["c3po/database:production"],
        },
    ]

    assert scanner.archive_config_image_ids(
        manifest,
        [
            ("backend", "c3po/backend:production"),
            ("web", "c3po/web:production"),
            ("database", "c3po/database:production"),
        ],
    ) == {
        "backend": f"sha256:{backend_config}",
        "web": f"sha256:{web_config}",
        "database": f"sha256:{database_config}",
    }

    with pytest.raises(ValueError, match="duplicate Docker archive RepoTag"):
        scanner.archive_config_image_ids(
            manifest + [{"Config": f"{'c' * 64}.json", "RepoTags": ["c3po/web:production"]}],
            [("backend", "c3po/backend:production")],
        )
    with pytest.raises(ValueError, match="duplicate requested image reference"):
        scanner.archive_config_image_ids(
            manifest,
            [
                ("backend", "c3po/backend:production"),
                ("backend-copy", "c3po/backend:production"),
            ],
        )
    with pytest.raises(ValueError, match="config digest is invalid"):
        scanner.archive_config_image_ids(
            [{"Config": "../bad.json", "RepoTags": ["c3po/backend:production"]}],
            [("backend", "c3po/backend:production")],
        )
    with pytest.raises(ValueError, match="config digest is invalid"):
        scanner.archive_config_image_ids(
            [
                {
                    "Config": f"blobs/sha256/../{'d' * 64}",
                    "RepoTags": ["c3po/backend:production"],
                }
            ],
            [("backend", "c3po/backend:production")],
        )
    with pytest.raises(ValueError, match="config digest is invalid"):
        scanner.archive_config_image_ids(
            [
                {
                    "Config": f"blobs/sha512/{'d' * 64}",
                    "RepoTags": ["c3po/backend:production"],
                }
            ],
            [("backend", "c3po/backend:production")],
        )
    with pytest.raises(ValueError, match="manifest must be a list"):
        scanner.archive_config_image_ids({}, [("backend", "c3po/backend:production")])


def test_trivy_scans_are_non_blocking_and_scheduled_off_host() -> None:
    pipeline = PIPELINE.read_text(encoding="utf-8")
    daily = DAILY_SCAN.read_text(encoding="utf-8")
    remediation_dispatch = REMEDIATION_DISPATCH.read_text(encoding="utf-8")
    parsed = yaml.safe_load(daily)
    jobs = parsed["jobs"]

    assert pipeline.count("scripts/c3po_trivy_scan.py") == 2
    assert pipeline.count("--image database=c3po/database:") == 2
    assert pipeline.count("continue-on-error: true") >= 4
    assert "--exclude='runtime/'" in pipeline
    schedules = [entry["cron"] for entry in parsed[True]["schedule"]]
    assert schedules == ["17 3 * * *", "0 7 * * 0"]
    assert "workflow_dispatch" in parsed[True]
    assert "runs-on: ubuntu-latest" in daily
    assert "Scheduled production image scan" in daily
    assert jobs["scan-production-images"]["permissions"] == {"contents": "read"}
    controller = jobs["remediation-controller"]
    assert "environment" not in controller
    assert controller["permissions"] == {
        "actions": "write",
        "contents": "write",
        "issues": "write",
        "pull-requests": "write",
    }
    controller_source = yaml.safe_dump(controller, sort_keys=False)
    controller_steps = {
        step.get("name"): step
        for step in controller["steps"]
        if step.get("name")
    }
    open_lane_source = controller_steps[
        "Open a rebuild PR and start validation"
    ]["run"]
    assert "c3po_container_remediation.py plan" in controller_source
    assert "gh pr create" in controller_source
    assert "gh pr comment" in controller_source
    assert "REMEDIATION_KEY" in controller_source
    assert "REMEDIATION_BRANCH" in controller_source
    assert "git switch -C" in controller_source
    assert "git push origin" in controller_source
    assert "actions/permissions/workflow" not in controller_source
    assert "can_approve_pull_request_reviews" not in controller_source
    assert "Prove GitHub Actions may create remediation PRs" not in controller_steps
    assert open_lane_source.index('git push origin "$branch"') < open_lane_source.index(
        "gh pr create"
    )
    assert "steps.remediation.outputs.lane_prefix" in controller_source
    assert controller_source.count("c3po_dispatch_remediation.sh") == 2
    assert remediation_dispatch.count("gh workflow run c3po-pipeline.yml") == 1
    assert "deploy=false" in remediation_dispatch
    assert "remediation=true" in remediation_dispatch
    mutation_source = controller_source + remediation_dispatch
    assert "gh pr merge" not in mutation_source
    assert "gh pr review" not in mutation_source
    assert "--auto" not in mutation_source
    lifecycle = jobs["complete-trivy-dead-man"]
    assert lifecycle["needs"] == ["scan-production-images", "remediation-controller"]
    assert lifecycle["environment"] == "production"
    assert 'docker save "$backend_image_ref" "$web_image_ref" "$database_image_ref"' in daily
    compose = yaml.safe_load((ROOT / "c3po" / "compose.yml").read_text(encoding="utf-8"))
    configured_backend_services = {
        name
        for name, service in compose["services"].items()
        if service.get("image") == "c3po/backend:production"
    }
    expected_backend_services = {
        "api",
        "investor-relations-worker",
        "valuation-worker",
        "server-usage-worker",
        "r2d2-worker",
        "r2d2-shadow-candidate-worker",
    }
    assert configured_backend_services == expected_backend_services
    backend_blocks = re.findall(
        r"backend_services=\(\n(?P<services>(?:\s+[a-z0-9-]+\n)+)\s+\)",
        daily,
    )
    assert len(backend_blocks) == 2
    for block in backend_blocks:
        assert {line.strip() for line in block.splitlines()} == configured_backend_services
    assert daily.count(
        "C3PO_EXPORT_ERROR=expected exactly one running container for %s"
    ) == 2
    assert daily.count("C3PO_EXPORT_ERROR=backend runtime identity diverged for %s") == 2
    assert "C3PO_EXPORT_ERROR=runtime identity changed during export for %s" in daily
    assert "C3PO_EXPORT_ERROR=image tag changed during export for %s" in daily
    assert daily.index("docker save") < daily.index("assert_container_unchanged")
    assert "production image export failed before evidence was sealed" in daily
    assert daily.count('for service in "${backend_services[@]}"') == 3
    assert "emit_metadata web web" in daily
    assert "emit_metadata database db" in daily
    for prefix in ("C3PO_BACKEND", "C3PO_WEB", "C3PO_DATABASE"):
        assert f"{prefix}_IMAGE_ID" in daily
        assert f"{prefix}_IMAGE_REF" in daily
        assert f"{prefix}_CONFIG_IMAGE_ID" in daily
        assert f"{prefix}_ROOTFS" in daily
    assert daily.count("docker inspect --format '{{.Image}}'") == 8
    assert daily.count("docker inspect --format '{{.Config.Image}}'") == 8
    assert daily.count("docker image inspect --format '{{.Id}}'") == 8
    assert daily.count("""docker image inspect --format '{{join .RootFS.Layers ","}}'""") == 4
    assert '"$image_ref")" = "$image_id"' in daily
    assert "C3PO_RUNTIME_BACKEND_ID" in daily
    assert "C3PO_RUNTIME_WEB_ID" in daily
    assert "C3PO_RUNTIME_DATABASE_ID" in daily
    assert "C3PO_ARCHIVE_SHA256" in daily
    assert 'sha256sum "$RUNNER_TEMP/c3po-production-images.tar.gz"' in daily
    assert "manifest.json" in daily
    assert "archive_config_image_ids" in daily
    assert "entries = {" not in daily
    assert "C3PO_LOADED_BACKEND_ID" in daily
    assert "C3PO_LOADED_WEB_ID" in daily
    assert "C3PO_LOADED_DATABASE_ID" in daily
    assert "docker rmi" not in daily
    assert daily.count("docker tag") == 1
    assert 'docker tag "$loaded_id" "$scan_ref"' in daily
    assert "loaded $label image identity does not match the live container" in daily
    assert '"$scan_ref")" = "$expected_loaded_id"' in daily
    assert '"$scan_ref")" = "$expected_rootfs"' in daily
    assert "--image backend=c3po/backend:production-scan" in daily
    assert "--image web=c3po/web:production-scan" in daily
    assert "--image database=c3po/database:production-scan" in daily
    assert '--origin "backend=$C3PO_BACKEND_IMAGE_REF|$C3PO_BACKEND_IMAGE_ID|$C3PO_BACKEND_CONFIG_IMAGE_ID|$C3PO_BACKEND_ROOTFS"' in daily
    assert '--origin "web=$C3PO_WEB_IMAGE_REF|$C3PO_WEB_IMAGE_ID|$C3PO_WEB_CONFIG_IMAGE_ID|$C3PO_WEB_ROOTFS"' in daily
    assert '--origin "database=$C3PO_DATABASE_IMAGE_REF|$C3PO_DATABASE_IMAGE_ID|$C3PO_DATABASE_CONFIG_IMAGE_ID|$C3PO_DATABASE_ROOTFS"' in daily
    assert '--transport-sha256 "$C3PO_IMAGE_ARCHIVE_SHA256"' in daily
    assert "Scan the production images off-host" in daily
    assert "scripts/c3po_trivy_scan.py" in daily
    assert "C3PO_HEALTHCHECK_TRIVY_URL" in daily
    assert '"${HEALTHCHECK_URL%/}/start"' in daily
    assert '"${HEALTHCHECK_URL%/}/fail"' in daily
    assert "--dead-man-configured" in daily
    assert "container-production-vulnerability-report.json" in daily
    assert "sudo install -o root -g ubuntu -m 0644" in daily
    assert "needs.remediation-controller.result" in daily


def test_remediation_dispatch_marker_is_written_only_after_dispatch_acceptance() -> None:
    daily = DAILY_SCAN.read_text(encoding="utf-8")
    dispatch = REMEDIATION_DISPATCH.read_text(encoding="utf-8")

    assert "key_present" in daily
    assert "marker_present" in daily
    assert 'evidence_marker="Chave de deduplicação: \\`$REMEDIATION_KEY\\`"' in daily
    assert "c3po-container-remediation-dispatch:$REMEDIATION_KEY" in daily
    assert "Evidence exists without a dispatch marker; resuming validation only" in daily
    assert "c3po-container-remediation-dispatch:$remediation_key" in dispatch
    assert "databaseId,headSha,url" in dispatch
    assert 'if [ -z "$dispatch_info" ]' in dispatch
    assert dispatch.index("gh workflow run c3po-pipeline.yml") < dispatch.index(
        'gh pr comment "$pr_number"'
    )


def test_remediation_refresh_and_lane_discovery_are_fail_closed_and_idempotent() -> None:
    daily = DAILY_SCAN.read_text(encoding="utf-8")

    assert "lane_count=$(jq 'length'" in daily
    assert 'if [ "$lane_count" -gt 1 ]' in daily
    assert "Multiple open container remediation lanes are forbidden" in daily
    assert "baseRefName,isCrossRepository" in daily
    assert "--app github-actions" in daily
    assert '"$base_branch" != "main"' in daily
    assert '"$cross_repository" != "false"' in daily
    assert '"$controller_matches" -ne 1' in daily
    assert "must target main, be same-repository, and be authored by github-actions[bot]" in daily
    assert "git diff --staged --quiet" in daily
    assert '|| git commit -m "Refresh container security remediation evidence"' in daily
    assert 'git push origin "HEAD:$REMEDIATION_BRANCH"' in daily


def test_positive_controller_dry_run_is_manual_isolated_and_two_phase() -> None:
    daily = DAILY_SCAN.read_text(encoding="utf-8")
    fixture = POSITIVE_FIXTURE.read_text(encoding="utf-8")
    runbook = OPS_RUNBOOK.read_text(encoding="utf-8")
    parsed = yaml.safe_load(daily)
    inputs = parsed[True]["workflow_dispatch"]["inputs"]
    jobs = parsed["jobs"]

    assert inputs["controller_dry_run_phase"]["options"] == [
        "none",
        "interrupt-before-dispatch",
        "resume",
    ]
    assert inputs["controller_dry_run_phase"]["default"] == "none"
    fixture_job = jobs["controller-positive-dry-run-fixture"]
    assert "environment" not in fixture_job
    assert fixture_job["permissions"] == {"contents": "read"}
    fixture_source = yaml.safe_dump(fixture_job, sort_keys=False)
    confirmation_source = next(
        step["run"]
        for step in fixture_job["steps"]
        if step.get("name") == "Validate the supervised dry-run request"
    )
    fixture_checkout = next(
        step
        for step in fixture_job["steps"]
        if step.get("uses") == "actions/checkout@v6"
    )
    assert "github.event_name == 'workflow_dispatch'" in fixture_job["if"]
    assert "refs/heads/main" in fixture_source
    assert fixture_checkout["with"]["ref"] == "${{ github.sha }}"
    assert '[ "$DRY_RUN_CONFIRMATION" != "C3PO-CONTROLLER-POSITIVE-DRY-RUN" ]' in confirmation_source
    assert 'echo "$DRY_RUN_CONFIRMATION"' not in confirmation_source
    assert "C3PO_AWS_SSH_KEY" not in fixture_source
    assert "C3PO_HEALTHCHECK_TRIVY_URL" not in fixture_source
    assert "environment: production" not in fixture_source
    assert "c3po-controller-dry-run-positive-${{ github.run_id }}" in fixture_source

    controller = jobs["remediation-controller"]
    assert controller["needs"] == [
        "scan-production-images",
        "controller-positive-dry-run-fixture",
    ]
    controller_source = yaml.safe_dump(controller, sort_keys=False)
    open_lane_source = next(
        step["run"]
        for step in controller["steps"]
        if step.get("name") == "Open a rebuild PR and start validation"
    )
    assert "plan-dry-run-positive" in controller_source
    assert "automation/controller-positive-dry-run-" not in controller_source
    assert "LANE_PREFIX" in controller_source
    assert "startsWith($prefix)" not in controller_source
    assert "startswith($prefix)" in controller_source
    assert "Dry-run interrupt phase requires no existing dry-run lane" in daily
    assert "Dry-run resume phase requires one existing dry-run lane" in daily
    assert "Dry-run resume requires exactly one recorded Phase A interruption run" in daily
    assert 'contains($marker) and contains("/actions/runs/")' in daily
    assert "c3po-controller-dry-run-interruption:" in open_lane_source
    assert "FASE A — interrupção controlada antes do dispatch" in open_lane_source
    assert open_lane_source.index('gh pr comment "$created_pr"') < open_lane_source.index(
        "Intentional dry-run interruption recorded"
    )
    assert "C3PO_AWS_SSH_KEY" not in controller_source
    assert "C3PO_HEALTHCHECK_TRIVY_URL" not in controller_source

    production_if = jobs["scan-production-images"]["if"]
    lifecycle_if = jobs["complete-trivy-dead-man"]["if"]
    assert "controller_dry_run_phase == 'none'" in production_if
    assert "controller_dry_run_phase == 'none'" in lifecycle_if
    assert parsed["concurrency"]["group"] == "c3po-production-container-scan"

    assert '"scope": "controller_dry_run"' in fixture
    assert '"dead_man_configured": false' in fixture
    assert '"fixture_id": "container-remediation-positive-v1"' in fixture
    assert '"high": 1' in fixture
    assert "Supervised positive controller dry-run" in runbook
    assert "real** fixable Critical/High finding" in runbook
    assert "Never weaken or bypass `verify-zero`" in runbook


def test_automated_remediation_validation_never_deploys_before_approval() -> None:
    pipeline = PIPELINE.read_text(encoding="utf-8")
    parsed = yaml.safe_load(pipeline)
    dispatch = parsed[True]["workflow_dispatch"]["inputs"]

    assert dispatch["deploy"]["default"] is True
    assert dispatch["remediation"]["default"] is False
    assert "inputs.deploy" in parsed["jobs"]["deploy-production"]["if"]
    assert "c3po_container_remediation.py verify-zero" in pipeline
    assert "automation/container-security-rebuild-" in pipeline
    assert "automation/controller-positive-dry-run-" in pipeline
    assert pipeline.count("C3PO_SECURITY_REBUILD=$C3PO_SECURITY_REBUILD") == 6


def test_trivy_report_attests_its_own_dead_man_configuration() -> None:
    scanner = _scanner_module()
    scanner.scan_image = lambda label, reference, _work: scanner.normalize_trivy_payload(
        label,
        reference,
        {"ArtifactName": reference, "Metadata": {}, "Results": []},
    )

    report = scanner.build_report(
        ["backend=c3po/backend:production"],
        scope="unit_test",
        revision="test",
        dead_man_configured=True,
    )

    assert report["scan_status"] == "complete"
    assert report["dead_man_configured"] is True
    assert report["report_sha256"] == scanner.report_sha256(report)


def test_trivy_report_carries_all_production_origin_identities() -> None:
    scanner = _scanner_module()
    origins = {
        "backend": {
            "image_ref": "c3po/backend:production",
            "image_id": _sha256("1"),
            "config_image_id": _sha256("2"),
            "rootfs_layers": [_sha256("3"), _sha256("4")],
        },
        "web": {
            "image_ref": "c3po/web:production",
            "image_id": _sha256("5"),
            "config_image_id": _sha256("6"),
            "rootfs_layers": [_sha256("7")],
        },
        "database": {
            "image_ref": "c3po/database:production",
            "image_id": _sha256("8"),
            "config_image_id": _sha256("9"),
            "rootfs_layers": [_sha256("a"), _sha256("b")],
        },
    }

    def scan(label: str, reference: str, _work: Path) -> dict[str, object]:
        origin = origins[label]
        return scanner.normalize_trivy_payload(
            label,
            reference,
            {
                "ArtifactName": reference,
                "Metadata": {
                    "ImageID": origin["config_image_id"],
                    "DiffIDs": origin["rootfs_layers"],
                },
                "Results": [],
            },
        )

    scanner.scan_image = scan

    report = scanner.build_report(
        [
            "backend=c3po/backend:production-scan",
            "web=c3po/web:production-scan",
            "database=c3po/database:production-scan",
        ],
        scope="production_runtime",
        revision="test",
        dead_man_configured=True,
        origin_specs=[
            (
                f"{label}={origin['image_ref']}|{origin['image_id']}|"
                f"{origin['config_image_id']}|"
                f"{','.join(origin['rootfs_layers'])}"
            )
            for label, origin in origins.items()
        ],
        transport_sha256="a" * 64,
    )

    by_label = {image["label"]: image for image in report["images"]}
    assert set(by_label) == {"backend", "web", "database"}
    for label, origin in origins.items():
        assert by_label[label]["origin"] == origin
        assert by_label[label]["image_id"] == origin["config_image_id"]
        assert by_label[label]["image_id"] != origin["image_id"]
        assert by_label[label]["rootfs_layers"] == origin["rootfs_layers"]
    assert report["source_transport"] == {
        "kind": "verified_docker_archive",
        "sha256": "a" * 64,
    }
    assert report["report_sha256"] == scanner.report_sha256(report)


def test_trivy_production_origins_fail_closed_when_missing_duplicate_or_mismatched() -> None:
    scanner = _scanner_module()
    image_specs = [
        "backend=c3po/backend:production-scan",
        "web=c3po/web:production-scan",
        "database=c3po/database:production-scan",
    ]
    config_ids = {
        "backend": _sha256("2"),
        "web": _sha256("4"),
        "database": _sha256("6"),
    }
    rootfs_layers = {
        "backend": _sha256("3"),
        "web": _sha256("5"),
        "database": _sha256("7"),
    }
    complete_origins = [
        (
            f"{label}=c3po/{label}:production|{_sha256(runtime)}|"
            f"{config_ids[label]}|{rootfs_layers[label]}"
        )
        for label, runtime in (("backend", "1"), ("web", "3"), ("database", "5"))
    ]

    with pytest.raises(ValueError, match="production image labels without an origin"):
        scanner.build_report(
            image_specs,
            scope="production_runtime",
            revision="test",
            origin_specs=complete_origins[:-1],
        )

    with pytest.raises(ValueError, match="duplicate origin label: backend"):
        scanner.parse_origin_specs([complete_origins[0], complete_origins[0]])

    with pytest.raises(ValueError, match="origin labels without a scanned image"):
        scanner.build_report(
            ["backend=c3po/backend:production"],
            scope="unit_test",
            revision="test",
            origin_specs=[
                f"database=ref|{_sha256('1')}|{_sha256('2')}|{_sha256('3')}"
            ],
        )

    with pytest.raises(ValueError, match="invalid origin specification"):
        scanner.parse_origin_specs(["database=ref|id-sem-rootfs"])

    with pytest.raises(ValueError, match="requires exactly backend, web and database"):
        scanner.build_report(
            image_specs[:-1],
            scope="production_runtime",
            revision="test",
            origin_specs=complete_origins[:-1],
        )

    with pytest.raises(ValueError, match="requires a verified transport sha256"):
        scanner.build_report(
            image_specs,
            scope="production_runtime",
            revision="test",
            origin_specs=complete_origins,
        )

    with pytest.raises(ValueError, match="transport sha256 is not lowercase hexadecimal"):
        scanner.build_report(
            image_specs,
            scope="production_runtime",
            revision="test",
            origin_specs=complete_origins,
            transport_sha256="not-a-sha256",
        )

    def mismatched_scan(label: str, reference: str, _work: Path) -> dict[str, object]:
        return scanner.normalize_trivy_payload(
            label,
            reference,
            {
                "Metadata": {
                    "ImageID": config_ids[label],
                    "DiffIDs": [_sha256("f")],
                },
                "Results": [],
            },
        )

    scanner.scan_image = mismatched_scan
    report = scanner.build_report(
        image_specs,
        scope="production_runtime",
        revision="test",
        origin_specs=complete_origins,
        transport_sha256="b" * 64,
    )
    assert report["scan_status"] == "error"
    assert report["images"] == []
    assert len(report["errors"]) == 3
    assert all(
        "scanned ordered RootFS does not match live origin" in row["error"]
        for row in report["errors"]
    )
    assert report["by_severity"] == {"critical": 0, "high": 0, "medium": 0, "low": 0}
    assert report["finding_total"] == 0
    assert report["report_sha256"] == scanner.report_sha256(report)

    def missing_id_scan(label: str, reference: str, _work: Path) -> dict[str, object]:
        return scanner.normalize_trivy_payload(
            label,
            reference,
            {
                "Metadata": {"DiffIDs": [rootfs_layers[label]]},
                "Results": [],
            },
        )

    scanner.scan_image = missing_id_scan
    report = scanner.build_report(
        image_specs,
        scope="production_runtime",
        revision="test",
        origin_specs=complete_origins,
        transport_sha256="c" * 64,
    )
    assert report["scan_status"] == "error"
    assert len(report["errors"]) == 3
    assert all("Trivy config image ID does not match archive" in row["error"] for row in report["errors"])


def test_provenance_additions_preserve_raw_counts_and_report_self_hash() -> None:
    scanner = _scanner_module()
    identity = {
        "backend": (_sha256("1"), _sha256("2"), _sha256("3")),
        "web": (_sha256("4"), _sha256("5"), _sha256("6")),
        "database": (_sha256("7"), _sha256("8"), _sha256("9")),
    }
    origins = {
        label: (
            f"{label}=c3po/{label}:production|{runtime_id}|{config_id}|{rootfs}"
        )
        for label, (runtime_id, config_id, rootfs) in identity.items()
    }

    def scan(label: str, reference: str, _work: Path) -> dict[str, object]:
        vulnerabilities = []
        if label == "backend":
            vulnerabilities = [
                {
                    "VulnerabilityID": "CVE-UNFIXED",
                    "Severity": "HIGH",
                    "PkgName": "unfixed",
                    "InstalledVersion": "1",
                    "FixedVersion": None,
                },
                {
                    "VulnerabilityID": "CVE-FIXABLE",
                    "Severity": "CRITICAL",
                    "PkgName": "fixable",
                    "InstalledVersion": "1",
                    "FixedVersion": "2",
                },
            ]
        elif label == "web":
            vulnerabilities = [{"VulnerabilityID": "CVE-MEDIUM", "Severity": "MEDIUM"}]
        return scanner.normalize_trivy_payload(
            label,
            reference,
            {
                "Metadata": {
                    "ImageID": identity[label][1],
                    "DiffIDs": [identity[label][2]],
                },
                "Results": [{"Target": label, "Vulnerabilities": vulnerabilities}],
            },
        )

    scanner.scan_image = scan
    report = scanner.build_report(
        [
            "backend=c3po/backend:production-scan",
            "web=c3po/web:production-scan",
            "database=c3po/database:production-scan",
        ],
        scope="production_runtime",
        revision="test",
        origin_specs=list(origins.values()),
        transport_sha256="c" * 64,
    )

    assert report["scan_status"] == "complete"
    assert report["by_severity"] == {"critical": 1, "high": 1, "medium": 1, "low": 0}
    assert report["fix_available"] == {"critical": 1, "high": 0, "medium": 0, "low": 0}
    assert report["unknown"] == 0
    assert report["finding_total"] == 3
    backend = next(image for image in report["images"] if image["label"] == "backend")
    assert backend["finding_total"] == 2
    assert backend["unfixed_high_critical"][0]["fixed_version"] == ""
    assert report["report_sha256"] == scanner.report_sha256(report)


def test_unfixed_high_critical_normalizes_missing_and_empty_fixed_version() -> None:
    scanner = _scanner_module()
    payload = {
        "Metadata": {"ImageID": "sha256:test", "DiffIDs": ["sha256:layer"]},
        "Results": [{
            "Target": "debian",
            "Vulnerabilities": [
                {
                    "VulnerabilityID": "CVE-MISSING",
                    "Severity": "HIGH",
                    "PkgName": "missing",
                    "InstalledVersion": "1",
                },
                {
                    "VulnerabilityID": "CVE-NULL",
                    "Severity": "CRITICAL",
                    "PkgName": "null",
                    "InstalledVersion": "2",
                    "FixedVersion": None,
                },
                {
                    "VulnerabilityID": "CVE-EMPTY",
                    "Severity": "HIGH",
                    "PkgName": "empty",
                    "InstalledVersion": "3",
                    "FixedVersion": "   ",
                },
            ],
        }],
    }

    image = scanner.normalize_trivy_payload("backend", "backend:test", payload)

    assert image["by_severity"] == {"critical": 1, "high": 2, "medium": 0, "low": 0}
    assert image["fix_available"] == {"critical": 0, "high": 0, "medium": 0, "low": 0}
    assert len(image["unfixed_high_critical"]) == 3
    assert {finding["fixed_version"] for finding in image["unfixed_high_critical"]} == {""}
    assert image["finding_total"] == 3


def test_trivy_container_does_not_leave_root_owned_runner_cache() -> None:
    source = TRIVY_SCRIPT.read_text(encoding="utf-8")

    assert '"--user"' in source
    assert 'f"{os.getuid()}:{os.getgid()}"' in source
    assert '"--group-add"' in source
    assert 'f"{cache_path}:/tmp/trivy-cache"' in source
    assert '"--cache-dir"' in source
