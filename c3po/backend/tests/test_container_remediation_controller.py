from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCANNER_PATH = ROOT / "scripts" / "c3po_trivy_scan.py"
CONTROLLER_PATH = ROOT / "scripts" / "c3po_container_remediation.py"
DISPATCH_PATH = ROOT / ".github" / "scripts" / "c3po_dispatch_remediation.sh"
POSITIVE_FIXTURE_PATH = (
    ROOT / "c3po" / "security" / "fixtures" / "container-remediation-positive-v1.json"
)


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _modules() -> tuple[ModuleType, ModuleType]:
    scanner = _load_module("c3po_trivy_scan", SCANNER_PATH)
    controller = _load_module("c3po_container_remediation", CONTROLLER_PATH)
    return scanner, controller


def _report(
    scanner: ModuleType,
    *,
    critical: int = 1,
    high: int = 1,
    medium: int = 0,
    low: int = 0,
) -> dict[str, Any]:
    findings = []
    counts = {
        "critical": critical,
        "high": high,
        "medium": medium,
        "low": low,
    }
    for severity, count in counts.items():
        for index in range(count):
            findings.append({
                "vulnerability_id": f"CVE-{severity.upper()}-{index}",
                "severity": severity,
                "package": f"{severity}-lib",
                "installed_version": "1.0",
                "fixed_version": "2.0",
                "target": "debian",
            })
    report = {
        "schema": scanner.SCHEMA,
        "generated_at": "2026-08-30T22:00:00+00:00",
        "scan_status": "complete",
        "scope": "production_runtime",
        "source_revision": "a" * 40,
        "dead_man_configured": True,
        "scanner": {"name": "Trivy"},
        "images": [{
            "label": "backend",
            "fix_available": dict(counts),
            "fixable_findings": [dict(finding) for finding in findings],
            "fixable_high_critical": [
                dict(finding)
                for finding in findings
                if finding["severity"] in {"critical", "high"}
            ],
        }],
        "by_severity": dict(counts),
        "fix_available": dict(counts),
        "unknown": 0,
        "finding_total": sum(counts.values()),
        "errors": [],
    }
    report["report_sha256"] = scanner.report_sha256(report)
    return report


def test_controller_builds_a_deduplicable_trigger_and_actionable_pr_body() -> None:
    scanner, controller = _modules()
    report = _report(scanner, medium=1, low=1)

    counts, findings = controller.validate_report(report)
    trigger = controller.build_trigger(
        report,
        counts=counts,
        findings=findings,
        run_url="https://github.com/duduvcastro/c3po/actions/runs/123",
        artifact_name="c3po-production-container-vulnerabilities-123",
    )
    body = controller.render_pr_body(trigger)

    assert trigger["schema"] == controller.TRIGGER_SCHEMA
    assert trigger["finding_total"] == 4
    assert len(trigger["remediation_key"]) == 64
    assert trigger["report_sha256"] == report["report_sha256"]
    assert controller.PR_MARKER in body
    assert "CVE-CRITICAL-0" in body
    assert "CVE-HIGH-0" in body
    assert "CVE-MEDIUM-0" in body
    assert "CVE-LOW-0" in body
    assert "Medium fixável: **1**" in body
    assert "Low fixável: **1**" in body
    assert controller.render_pr_title(counts, dry_run=False) == (
        "Remediate 1 critical, 1 high, 1 medium and 1 low container findings"
    )
    assert trigger["remediation_key"] in body
    assert "Não há auto-merge" in body
    assert "Fable audita" in body
    assert "Dudu autoriza" in body


def test_medium_and_low_findings_change_the_shared_lane_deduplication_key() -> None:
    scanner, controller = _modules()
    prefixes = set()
    keys = set()
    for severity in ("high", "medium", "low"):
        requested = {name: 0 for name in scanner.SEVERITIES}
        requested[severity] = 1
        report = _report(
            scanner,
            critical=requested["critical"],
            high=requested["high"],
            medium=requested["medium"],
            low=requested["low"],
        )
        counts, findings = controller.validate_report(report)
        trigger = controller.build_trigger(
            report,
            counts=counts,
            findings=findings,
            run_url="https://github.com/duduvcastro/c3po/actions/runs/123",
            artifact_name="c3po-production-container-vulnerabilities-123",
        )
        prefixes.add(controller.PRODUCTION_LANE_PREFIX)
        keys.add(trigger["remediation_key"])

    assert prefixes == {"automation/container-security-rebuild-"}
    assert len(keys) == 3


def test_controller_accepts_a_zero_fixable_report_without_opening_work() -> None:
    scanner, controller = _modules()
    report = _report(scanner, critical=0, high=0)

    counts, findings = controller.validate_report(report)

    assert counts == {"critical": 0, "high": 0, "medium": 0, "low": 0}
    assert findings == []


@pytest.mark.parametrize("severity", [None, "critical", "high", "medium", "low"])
def test_plan_emits_machine_outputs_and_only_writes_work_when_required(
    tmp_path: Path,
    severity: str | None,
) -> None:
    scanner, controller = _modules()
    requested = {name: 0 for name in scanner.SEVERITIES}
    if severity is not None:
        requested[severity] = 1
    report = _report(
        scanner,
        critical=requested["critical"],
        high=requested["high"],
        medium=requested["medium"],
        low=requested["low"],
    )
    report_path = tmp_path / "report.json"
    trigger_path = tmp_path / "trigger.json"
    body_path = tmp_path / "body.md"
    output_path = tmp_path / "github-output"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = controller.plan(Namespace(
        report=report_path,
        trigger=trigger_path,
        pr_body=body_path,
        run_url="https://github.com/duduvcastro/c3po/actions/runs/123",
        artifact_name="c3po-production-container-vulnerabilities-123",
        github_output=output_path,
    ))

    outputs = dict(
        line.split("=", 1)
        for line in output_path.read_text(encoding="utf-8").splitlines()
    )
    assert result == 0
    required = severity is not None
    assert outputs["required"] == str(required).lower()
    for name in scanner.SEVERITIES:
        assert outputs[name] == str(requested[name])
    assert outputs["pr_title"] == controller.render_pr_title(
        requested,
        dry_run=False,
    )
    assert bool(outputs["remediation_key"]) is required
    assert outputs["lane_prefix"] == controller.PRODUCTION_LANE_PREFIX
    assert outputs["dry_run"] == "false"
    assert trigger_path.exists() is required
    assert body_path.exists() is required


def test_positive_dry_run_fixture_is_sealed_scoped_and_actionable(tmp_path: Path) -> None:
    _, controller = _modules()
    report = controller.load_report(POSITIVE_FIXTURE_PATH)

    counts, findings = controller.validate_positive_dry_run_fixture(
        POSITIVE_FIXTURE_PATH,
        report,
    )

    assert counts == {"critical": 0, "high": 1, "medium": 0, "low": 0}
    assert findings[0]["vulnerability_id"] == "C3PO-DRY-RUN-FIXABLE-001"
    trigger_path = tmp_path / "trigger.json"
    body_path = tmp_path / "body.md"
    output_path = tmp_path / "github-output"
    result = controller.plan_dry_run_positive(Namespace(
        report=POSITIVE_FIXTURE_PATH,
        trigger=trigger_path,
        pr_body=body_path,
        run_url="https://github.com/duduvcastro/c3po/actions/runs/456",
        artifact_name="c3po-controller-dry-run-positive-456",
        github_output=output_path,
    ))

    outputs = dict(
        line.split("=", 1)
        for line in output_path.read_text(encoding="utf-8").splitlines()
    )
    trigger = json.loads(trigger_path.read_text(encoding="utf-8"))
    body = body_path.read_text(encoding="utf-8")
    assert result == 0
    assert outputs["required"] == "true"
    assert outputs["lane_prefix"] == controller.DRY_RUN_LANE_PREFIX
    assert outputs["dry_run"] == "true"
    assert outputs["pr_title"] == (
        "[DRY-RUN] Exercise controller with one synthetic high finding"
    )
    assert trigger["dry_run"] is True
    assert trigger["evidence_scope"] == controller.DRY_RUN_SCOPE
    assert "CONTROLE SINTÉTICO — NÃO É PRODUÇÃO" in body
    assert "nunca deve ser mergeada" in body
    assert "deploy=false" in body
    assert "fixável real" in body


def test_positive_dry_run_fixture_rejects_tampering_and_production_scope(
    tmp_path: Path,
) -> None:
    scanner, controller = _modules()
    fixture = controller.load_report(POSITIVE_FIXTURE_PATH)
    tampered_path = tmp_path / "tampered.json"
    fixture["images"][0]["fixable_high_critical"][0]["fixed_version"] = "3"
    fixture["report_sha256"] = scanner.report_sha256(fixture)
    tampered_path.write_text(json.dumps(fixture), encoding="utf-8")

    with pytest.raises(controller.ReportValidationError, match="seal mismatch"):
        controller.validate_positive_dry_run_fixture(tampered_path, fixture)

    sealed_fixture = controller.load_report(POSITIVE_FIXTURE_PATH)
    with pytest.raises(controller.ReportValidationError, match="production_runtime"):
        controller.validate_report(sealed_fixture)

    production_report = _report(scanner)
    production_path = tmp_path / "production.json"
    production_path.write_text(json.dumps(production_report), encoding="utf-8")
    with pytest.raises(controller.ReportValidationError, match="seal mismatch"):
        controller.validate_positive_dry_run_fixture(production_path, production_report)


def test_zero_gate_accepts_pull_request_scope_without_a_dead_man(
    tmp_path: Path,
) -> None:
    scanner, controller = _modules()
    report = _report(scanner, critical=0, high=0)
    report["scope"] = "pull_request_build"
    report["dead_man_configured"] = False
    report["report_sha256"] = scanner.report_sha256(report)

    counts, findings = controller.validate_report(
        report,
        expected_scope="pull_request_build",
        require_dead_man=False,
    )

    assert counts == {"critical": 0, "high": 0, "medium": 0, "low": 0}
    assert findings == []

    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    assert controller.verify_zero(Namespace(report=report_path)) == 0


@pytest.mark.parametrize("severity", ["critical", "high", "medium", "low"])
def test_zero_gate_rejects_every_fixable_severity(
    tmp_path: Path,
    severity: str,
) -> None:
    scanner, controller = _modules()
    requested = {name: 0 for name in scanner.SEVERITIES}
    requested[severity] = 1
    report = _report(
        scanner,
        critical=requested["critical"],
        high=requested["high"],
        medium=requested["medium"],
        low=requested["low"],
    )
    report["scope"] = "pull_request_build"
    report["dead_man_configured"] = False
    report["report_sha256"] = scanner.report_sha256(report)
    report_path = tmp_path / f"{severity}.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(controller.ReportValidationError, match="fixable findings"):
        controller.verify_zero(Namespace(report=report_path))


@pytest.mark.parametrize("dispatch_succeeds", [False, True])
@pytest.mark.parametrize("branch", [
    "automation/container-security-rebuild-test-123",
    "automation/controller-positive-dry-run-test-123",
])
def test_dispatch_helper_records_the_run_marker_only_after_accepted_dispatch(
    tmp_path: Path,
    dispatch_succeeds: bool,
    branch: str,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$GH_LOG"
if [ "$1 $2" = "run list" ]; then
  if [[ "$*" == *"databaseId,headSha,url"* ]]; then
    printf '[{"databaseId":987,"headSha":"%s","url":"https://github.com/duduvcastro/c3po/actions/runs/987"}]\\n' "$EXPECTED_SHA"
  else
    printf '0\\n'
  fi
elif [ "$1 $2" = "workflow run" ]; then
  if [ "$GH_WORKFLOW_RESULT" != "0" ]; then
    exit "$GH_WORKFLOW_RESULT"
  fi
  touch "$GH_DISPATCHED"
elif [ "$1 $2" = "pr comment" ]; then
  test -f "$GH_DISPATCHED"
  while [ "$#" -gt 0 ]; do
    if [ "$1" = "--body-file" ]; then
      cp "$2" "$GH_COMMENT"
      exit 0
    fi
    shift
  done
  exit 1
else
  echo "unexpected gh command: $*" >&2
  exit 1
fi
""",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    log_path = tmp_path / "gh.log"
    marker_path = tmp_path / "marker.md"
    expected_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        check=True,
        capture_output=True,
    ).stdout.strip()
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "GITHUB_REPOSITORY": "duduvcastro/c3po",
        "RUNNER_TEMP": str(tmp_path),
        "GH_LOG": str(log_path),
        "GH_DISPATCHED": str(tmp_path / "dispatched"),
        "GH_COMMENT": str(marker_path),
        "EXPECTED_SHA": expected_sha,
        "GH_WORKFLOW_RESULT": "0" if dispatch_succeeds else "1",
    }
    remediation_key = "a" * 64

    completed = subprocess.run(
        [
            "bash",
            str(DISPATCH_PATH),
            branch,
            remediation_key,
            "42",
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
    )

    commands = log_path.read_text(encoding="utf-8")
    if not dispatch_succeeds:
        assert completed.returncode != 0
        assert "pr comment 42" not in commands
        assert not marker_path.exists()
        return

    assert completed.returncode == 0, completed.stderr
    assert commands.index("workflow run c3po-pipeline.yml") < commands.index("pr comment 42")
    marker = marker_path.read_text(encoding="utf-8")
    assert f"c3po-container-remediation-dispatch:{remediation_key}" in marker
    assert "run `987`" in marker
    assert "https://github.com/duduvcastro/c3po/actions/runs/987" in marker


def test_dispatch_helper_accepts_only_the_real_and_dry_run_lane_prefixes() -> None:
    dispatch = DISPATCH_PATH.read_text(encoding="utf-8")

    assert "container-security-rebuild|controller-positive-dry-run" in dispatch
    assert "^automation/" in dispatch

    completed = subprocess.run(
        ["bash", str(DISPATCH_PATH), "automation/untrusted-lane", "a" * 64, "42"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert completed.returncode != 0
    assert "invalid remediation branch" in completed.stderr


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda report: report.update({"scan_status": "error"}), "not complete"),
        (lambda report: report.update({"scope": "pull_request_build"}), "production_runtime"),
        (lambda report: report.update({"dead_man_configured": False}), "dead-man"),
        (
            lambda report: report["images"][0].update({"fixable_findings": []}),
            "detail/count mismatch",
        ),
        (
            lambda report: report["images"][0].update({"fixable_high_critical": []}),
            "projection mismatch",
        ),
        (
            lambda report: report["fix_available"].update({"medium": 1}),
            "top-level/image fixable count mismatch",
        ),
    ],
)
def test_controller_rejects_incomplete_or_inconsistent_evidence(mutation, message: str) -> None:
    scanner, controller = _modules()
    report = _report(scanner)
    mutation(report)
    report["report_sha256"] = scanner.report_sha256(report)

    with pytest.raises(controller.ReportValidationError, match=message):
        controller.validate_report(report)


def test_controller_rejects_a_self_hash_mismatch() -> None:
    scanner, controller = _modules()
    report = _report(scanner)
    report["fix_available"]["critical"] = 99

    with pytest.raises(controller.ReportValidationError, match="self-hash mismatch"):
        controller.validate_report(report)
