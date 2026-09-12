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


def _report(scanner: ModuleType, *, critical: int = 1, high: int = 1, medium: int = 0, low: int = 0,
            unrated: int = 0, unrated_fixable: int = 0, with_occurrences: bool = True) -> dict[str, Any]:
    findings = []
    for index in range(critical):
        findings.append({
            "vulnerability_id": f"CVE-CRITICAL-{index}",
            "severity": "critical",
            "package": "critical-lib",
            "installed_version": "1.0",
            "fixed_version": "2.0",
            "target": "debian",
        })
    for index in range(high):
        findings.append({
            "vulnerability_id": f"CVE-HIGH-{index}",
            "severity": "high",
            "package": "high-lib",
            "installed_version": "3.0",
            "fixed_version": "4.0",
            "target": "debian",
        })
    occurrences = list(findings)
    for index in range(medium):
        occurrences.append({"vulnerability_id": f"CVE-MEDIUM-{index}", "severity": "medium", "package": "medium-lib",
                            "installed_version": "5.0", "fixed_version": "5.1", "target": "alpine"})
    for index in range(low):
        occurrences.append({"vulnerability_id": f"CVE-LOW-{index}", "severity": "low", "package": "low-lib",
                            "installed_version": "6.0", "fixed_version": "6.1", "target": "alpine"})
    for index in range(unrated):
        occurrences.append({"vulnerability_id": f"CVE-2026-8{index:04d}", "severity": "unknown", "package": "libcurl",
                            "installed_version": "8.21.0-r0", "fixed_version": "8.22.0-r0" if index < unrated_fixable else "",
                            "target": "alpine"})
    image: dict[str, Any] = {
        "label": "backend",
        "fixable_high_critical": findings,
        "fix_available": {"critical": critical, "high": high, "medium": medium, "low": low},
        "unknown": unrated,
        "unknown_fix_available": unrated_fixable,
    }
    if with_occurrences:
        image["occurrences"] = occurrences
    report = {
        "schema": scanner.SCHEMA,
        "generated_at": "2026-08-30T22:00:00+00:00",
        "scan_status": "complete",
        "scope": "production_runtime",
        "source_revision": "a" * 40,
        "dead_man_configured": True,
        "scanner": {"name": "Trivy"},
        "images": [image],
        "by_severity": {"critical": critical, "high": high, "medium": medium, "low": low},
        "fix_available": {"critical": critical, "high": high, "medium": medium, "low": low},
        "unknown": unrated,
        "finding_total": critical + high + medium + low + unrated,
        "errors": [],
    }
    report["report_sha256"] = scanner.report_sha256(report)
    return report


def test_controller_builds_a_deduplicable_trigger_and_actionable_pr_body() -> None:
    scanner, controller = _modules()
    report = _report(scanner)

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
    assert trigger["finding_total"] == 2
    assert len(trigger["remediation_key"]) == 64
    assert trigger["report_sha256"] == report["report_sha256"]
    assert controller.PR_MARKER in body
    assert "CVE-CRITICAL-0" in body
    assert "CVE-HIGH-0" in body
    assert trigger["remediation_key"] in body
    assert "CI/scan no SHA exato" in body
    assert "ausência de freeze" in body
    assert "exigindo auditoria e autorização nominal" in body


def test_controller_accepts_a_zero_fixable_report_without_opening_work() -> None:
    scanner, controller = _modules()
    report = _report(scanner, critical=0, high=0)

    counts, findings = controller.validate_report(report)

    assert counts == {"critical": 0, "high": 0, "medium": 0, "low": 0, "unknown": 0}
    assert findings == []


@pytest.mark.parametrize("required", [False, True])
def test_plan_emits_machine_outputs_and_only_writes_work_when_required(
    tmp_path: Path,
    required: bool,
) -> None:
    scanner, controller = _modules()
    report = _report(scanner, critical=int(required), high=0)
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
    assert outputs["required"] == str(required).lower()
    assert outputs["critical"] == str(int(required))
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

    assert counts == {"critical": 0, "high": 1, "medium": 0, "low": 0, "unknown": 0}
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


def test_zero_gate_accepts_pull_request_scope_without_a_dead_man() -> None:
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

    assert counts == {"critical": 0, "high": 0, "medium": 0, "low": 0, "unknown": 0}
    assert findings == []


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
            lambda report: report["images"][0].update({"fixable_high_critical": []}),
            "detail/count mismatch",
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


def test_controller_opens_work_for_medium_low_and_unrated_fixable_findings(tmp_path: Path) -> None:
    # The daily loop acts on every occurrence the distribution already fixed, not only critical/high:
    # medium, low and findings without a public rating yet (CVE reserved, secdb fix shipped).
    scanner, controller = _modules()
    report = _report(scanner, critical=0, high=0, medium=1, low=1, unrated=2, unrated_fixable=1)

    counts, findings = controller.validate_report(report)
    assert counts == {"critical": 0, "high": 0, "medium": 1, "low": 1, "unknown": 1}
    assert [(f["severity"], f["vulnerability_id"], f["fixed_version"]) for f in findings] == [
        ("medium", "CVE-MEDIUM-0", "5.1"), ("low", "CVE-LOW-0", "6.1"), ("unknown", "CVE-2026-80000", "8.22.0-r0")]
    trigger = controller.build_trigger(report, counts=counts, findings=findings,
                                       run_url="https://github.com/duduvcastro/c3po/actions/runs/123",
                                       artifact_name="c3po-production-container-vulnerabilities-123")
    body = controller.render_pr_body(trigger)
    assert trigger["finding_total"] == 3 and "Medium fixável: **1**" in body and "Low fixável: **1**" in body
    assert "Sem classificação pública, mas com correção da distribuição: **1**" in body and "CVE-2026-80000" in body
    output_path = tmp_path / "github-output"
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    assert controller.plan(Namespace(report=report_path, trigger=tmp_path / "trigger.json", pr_body=tmp_path / "body.md",
                                     run_url="https://github.com/duduvcastro/c3po/actions/runs/123",
                                     artifact_name="c3po-production-container-vulnerabilities-123", github_output=output_path)) == 0
    outputs = dict(line.split("=", 1) for line in output_path.read_text(encoding="utf-8").splitlines())
    assert outputs["required"] == "true" and outputs["medium"] == "1" and outputs["low"] == "1" and outputs["unknown"] == "1"
    # an unrated occurrence WITHOUT a fix is not work: nothing to rebuild towards
    report = _report(scanner, critical=0, high=0, unrated=1, unrated_fixable=0)
    counts, findings = controller.validate_report(report)
    assert sum(counts.values()) == 0 and findings == []


def _medium_report(scanner: ModuleType, occurrences: list[dict[str, str]]) -> dict[str, Any]:
    report = _report(scanner, critical=0, high=0)
    image = report["images"][0]
    image["occurrences"] = list(occurrences)
    fixable = sum(1 for occurrence in occurrences if occurrence["fixed_version"])
    image["fix_available"]["medium"] = fixable
    report["by_severity"]["medium"] = len(occurrences)
    report["fix_available"]["medium"] = fixable
    report["finding_total"] = len(occurrences)
    report["report_sha256"] = scanner.report_sha256(report)
    return report


def _remediation_key(controller: ModuleType, report: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    counts, findings = controller.validate_report(report)
    trigger = controller.build_trigger(
        report,
        counts=counts,
        findings=findings,
        run_url="https://github.com/duduvcastro/c3po/actions/runs/123",
        artifact_name="c3po-production-container-vulnerabilities-123",
    )
    return trigger["remediation_key"], findings


def test_remediation_key_is_canonical_over_every_identity_field_and_keeps_multiplicity() -> None:
    # Two occurrences of the same CVE/package/target that differ only in installed version
    # (a duplicated package at 1.0 and 1.1, both fixed in 1.2): the key must not depend on the
    # scanner's output order, must change when a version really changes, and must change when
    # the same occurrence is reported once versus twice.
    scanner, controller = _modules()
    first = {"vulnerability_id": "CVE-2026-1", "severity": "medium", "package": "libx",
             "installed_version": "1.0", "fixed_version": "1.2", "target": "alpine"}
    second = dict(first, installed_version="1.1")

    key_forward, findings_forward = _remediation_key(controller, _medium_report(scanner, [first, second]))
    key_reverse, findings_reverse = _remediation_key(controller, _medium_report(scanner, [second, first]))
    assert key_forward == key_reverse
    assert findings_forward == findings_reverse
    assert [finding["installed_version"] for finding in findings_forward] == ["1.0", "1.1"]

    key_other_fix, _ = _remediation_key(controller, _medium_report(scanner, [first, dict(second, fixed_version="1.3")]))
    key_other_installed, _ = _remediation_key(controller, _medium_report(scanner, [first, dict(second, installed_version="1.2")]))
    assert key_other_fix != key_forward
    assert key_other_installed != key_forward

    key_once, findings_once = _remediation_key(controller, _medium_report(scanner, [first]))
    key_twice, findings_twice = _remediation_key(controller, _medium_report(scanner, [first, first]))
    assert key_once != key_twice
    assert len(findings_once) == 1 and len(findings_twice) == 2

    # The same invariance holds across severities: reversing both the critical/high list and
    # the occurrence list of the default fixture yields the same key.
    report = _report(scanner, medium=1, low=1)
    key_default, _ = _remediation_key(controller, report)
    image = report["images"][0]
    image["fixable_high_critical"].reverse()
    image["occurrences"].reverse()
    report["report_sha256"] = scanner.report_sha256(report)
    key_reversed, _ = _remediation_key(controller, report)
    assert key_reversed == key_default


def test_controller_requires_occurrence_evidence_outside_the_sealed_fixture() -> None:
    scanner, controller = _modules()
    report = _report(scanner, with_occurrences=False)
    with pytest.raises(controller.ReportValidationError, match="missing occurrences evidence"):
        controller.validate_report(report)


@pytest.mark.parametrize("mutation, message", [
    (lambda image: image["occurrences"].pop(0), "do not match fixable_high_critical"),
    (lambda image: image["occurrences"].append({"vulnerability_id": "CVE-MEDIUM-9", "severity": "medium", "package": "x",
                                                "installed_version": "1", "fixed_version": "2", "target": "alpine"}), "medium detail/count mismatch"),
    (lambda image: image.update({"unknown_fix_available": 2}), "unrated fixable detail/count mismatch"),
    (lambda image: image.update({"unknown": 3}), "unrated occurrence count mismatch"),
    (lambda image: image["occurrences"].append({"vulnerability_id": "CVE-X", "severity": "weird", "package": "x",
                                                "installed_version": "1", "fixed_version": "", "target": "alpine"}), "not a known level"),
])
def test_controller_rejects_occurrences_inconsistent_with_the_counts(mutation, message: str) -> None:
    scanner, controller = _modules()
    report = _report(scanner, medium=1, unrated=1, unrated_fixable=1)
    mutation(report["images"][0])
    report["report_sha256"] = scanner.report_sha256(report)
    with pytest.raises(controller.ReportValidationError, match=message):
        controller.validate_report(report)


def test_zero_gate_rejects_any_fixable_finding(tmp_path: Path) -> None:
    scanner, controller = _modules()
    report = _report(scanner, critical=0, high=0, low=1)
    report["scope"] = "pull_request_build"
    report["dead_man_configured"] = False
    report["report_sha256"] = scanner.report_sha256(report)
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(controller.ReportValidationError, match="fixable findings"):
        controller.verify_zero(Namespace(report=report_path))
