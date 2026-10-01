from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from argparse import Namespace
from datetime import datetime, timedelta, timezone
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



CLOSE_STALE_PATH = ROOT / ".github" / "scripts" / "c3po_close_stale_lanes.sh"
SCAN_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "container-vulnerability-scan.yml"
LANE_RUN_URL = "https://github.com/duduvcastro/c3po/actions/runs/777"
TRIGGER_FILE = "c3po/security/container-rebuild-trigger.json"


def _lane_trigger(scanner: ModuleType, controller: ModuleType, **kwargs: Any) -> dict[str, Any]:
    report = _report(scanner, **kwargs)
    counts, findings = controller.validate_report(report)
    return controller.build_trigger(
        report, counts=counts, findings=findings,
        run_url="https://github.com/duduvcastro/c3po/actions/runs/123",
        artifact_name="c3po-production-container-vulnerabilities-123",
    )


def _fresh_clean_report(scanner: ModuleType, *, unfixed_ids: tuple[str, ...] = (),
                        age: timedelta = timedelta(hours=1),
                        backend_occurrences: bool = True) -> dict[str, Any]:
    """Zero fixable findings; the backend image still reports an unrelated unfixed
    occurrence (a real scan of that image is not empty)."""
    report = _report(scanner, critical=0, high=0)
    report["generated_at"] = (datetime.now(timezone.utc) - age).isoformat()
    image = report["images"][0]
    if backend_occurrences:
        image["occurrences"].append({"vulnerability_id": "CVE-UNRELATED-1", "severity": "low",
                                     "package": "other-lib", "installed_version": "1",
                                     "fixed_version": "", "target": "debian"})
    for vulnerability_id in unfixed_ids:
        image["occurrences"].append({"vulnerability_id": vulnerability_id, "severity": "high",
                                     "package": "high-lib", "installed_version": "3.0",
                                     "fixed_version": "", "target": "debian"})
    image["image_id"] = "sha256:" + "b" * 64
    image["finding_total"] = len(image["occurrences"])
    report["by_severity"]["high"] = len(unfixed_ids)
    report["by_severity"]["low"] = int(backend_occurrences)
    report["finding_total"] = len(image["occurrences"])
    report["report_sha256"] = scanner.report_sha256(report)
    return report


def _bot_metadata(**overrides: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "files": [{"path": TRIGGER_FILE, "changeType": "MODIFIED", "additions": 3, "deletions": 3}],
        "commits": [{"oid": "a" * 40, "authors": [{"login": "github-actions[bot]",
                                                  "name": "github-actions[bot]"}]}],
        "comments": [{"author": {"login": "github-actions"}, "body": "evidence"}],
    }
    metadata.update(overrides)
    return metadata


def test_stale_lane_closes_only_when_every_lane_finding_left_a_clean_fresh_scan() -> None:
    scanner, controller = _modules()
    trigger = _lane_trigger(scanner, controller, critical=0, high=1)
    fresh = _fresh_clean_report(scanner)

    close, reason, resolved = controller.stale_lane_decision(fresh, trigger)
    assert close is True, reason
    assert resolved == ["CVE-HIGH-0"]

    body = controller.render_stale_lane_comment(fresh, trigger, resolved, run_url=LANE_RUN_URL)
    assert body.splitlines()[0] == (
        f"<!-- c3po-container-remediation-stale-close:{fresh['report_sha256']} -->"
    )
    assert "[`777`](" + LANE_RUN_URL + ")" in body
    assert f"Report self-hash: `{fresh['report_sha256']}`" in body
    assert "critical 0, high 0, medium 0, low 0, sem classificação 0" in body
    assert f"`{trigger['remediation_key']}`" in body
    assert "`CVE-HIGH-0`" in body
    assert "reversível" in body


def test_a_fully_clean_rebuilt_image_with_zero_occurrences_still_closes_the_lane() -> None:
    # Real shape of 30/09/2026: backend, web and database all had zero occurrences.
    scanner, controller = _modules()
    trigger = _lane_trigger(scanner, controller, critical=0, high=1)
    fresh = _fresh_clean_report(scanner, backend_occurrences=False)
    assert fresh["images"][0]["occurrences"] == []

    close, reason, resolved = controller.stale_lane_decision(fresh, trigger)

    assert close is True, reason
    assert resolved == ["CVE-HIGH-0"]


@pytest.mark.parametrize("case", ["still_present_unfixed", "fixable_elsewhere", "dry_run",
                                  "wrong_schema", "no_findings", "not_newer", "older_than_6h",
                                  "future_dated", "lane_image_missing", "lane_image_unidentified",
                                  "lane_image_inconsistent"])
def test_stale_lane_is_kept_open_on_any_doubt(case: str) -> None:
    scanner, controller = _modules()
    trigger = _lane_trigger(scanner, controller, critical=0, high=1)
    fresh = _fresh_clean_report(scanner)
    if case == "still_present_unfixed":
        fresh = _fresh_clean_report(scanner, unfixed_ids=("CVE-HIGH-0",))
    elif case == "fixable_elsewhere":
        fresh = _report(scanner, critical=0, high=0, low=1)
        fresh["generated_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        fresh["report_sha256"] = scanner.report_sha256(fresh)
    elif case == "dry_run":
        trigger["dry_run"] = True
    elif case == "wrong_schema":
        trigger["schema"] = "SOMETHING-ELSE"
    elif case == "no_findings":
        trigger["findings"] = []
    elif case == "not_newer":
        trigger["generated_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    elif case == "older_than_6h":
        # A re-run of an old workflow run must never close a lane.
        fresh = _fresh_clean_report(scanner, age=timedelta(hours=6, minutes=1))
    elif case == "future_dated":
        fresh = _fresh_clean_report(scanner, age=-timedelta(hours=1))
    elif case == "lane_image_missing":
        trigger["findings"][0]["image"] = "web"
    elif case == "lane_image_unidentified":
        fresh["images"][0]["image_id"] = ""
        fresh["report_sha256"] = scanner.report_sha256(fresh)
    else:
        fresh["images"][0]["finding_total"] = 5
        fresh["report_sha256"] = scanner.report_sha256(fresh)

    close, reason, resolved = controller.stale_lane_decision(fresh, trigger)

    assert close is False
    assert reason
    assert resolved == []


def test_stale_lane_fails_closed_on_an_incomplete_fresh_scan() -> None:
    scanner, controller = _modules()
    trigger = _lane_trigger(scanner, controller, critical=0, high=1)
    fresh = _fresh_clean_report(scanner)
    fresh["scan_status"] = "error"
    fresh["report_sha256"] = scanner.report_sha256(fresh)

    with pytest.raises(controller.ReportValidationError, match="not complete"):
        controller.stale_lane_decision(fresh, trigger)


def test_only_machine_owned_lanes_may_be_closed() -> None:
    _, controller = _modules()
    human = {"login": "duduvcastro", "name": "Eduardo"}
    bot = {"login": "github-actions[bot]"}

    assert controller.lane_ownership_problem(_bot_metadata()) is None
    assert controller.lane_ownership_problem(_bot_metadata(
        files=[{"path": TRIGGER_FILE, "changeType": "ADDED"}])) is None
    for metadata in (
        _bot_metadata(files=[{"path": TRIGGER_FILE, "changeType": "MODIFIED"},
                             {"path": "c3po/backend/Dockerfile", "changeType": "MODIFIED"}]),
        _bot_metadata(files=[{"path": "c3po/backend/Dockerfile", "changeType": "MODIFIED"}]),
        _bot_metadata(files=[{"path": TRIGGER_FILE, "changeType": "DELETED"}]),
        _bot_metadata(commits=[{"authors": [bot]}, {"authors": [human]}]),
        _bot_metadata(commits=[{"authors": [bot, human]}]),
        _bot_metadata(commits=[]),
        _bot_metadata(comments=[{"body": "<!-- c3po-container-remediation-stale-close:abc -->\nx"}]),
        _bot_metadata(comments=None),
        [],
    ):
        assert controller.lane_ownership_problem(metadata)


def _write_cli_inputs(tmp_path: Path, report: dict[str, Any], trigger: dict[str, Any],
                      metadata: dict[str, Any]) -> Namespace:
    paths = {name: tmp_path / f"{name}.json" for name in ("report", "trigger", "metadata")}
    for name, payload in (("report", report), ("trigger", trigger), ("metadata", metadata)):
        paths[name].write_text(json.dumps(payload), encoding="utf-8")
    return Namespace(report=paths["report"], trigger=paths["trigger"], pr_metadata=paths["metadata"],
                     run_url=LANE_RUN_URL, comment=tmp_path / "comment.md", now=None)


def test_stale_lane_cli_refuses_a_human_touched_lane(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    scanner, controller = _modules()
    args = _write_cli_inputs(
        tmp_path, _fresh_clean_report(scanner), _lane_trigger(scanner, controller, critical=0, high=1),
        _bot_metadata(commits=[{"authors": [{"login": "duduvcastro"}]}]),
    )

    assert controller.stale_lane(args) == 0
    decision = json.loads(capsys.readouterr().out)
    assert decision["close"] is False and "human-owned" in decision["reason"]
    assert not args.comment.exists()


def _run_close_stale(tmp_path: Path, *, report: dict[str, Any], trigger: dict[str, Any] | None,
                     metadata: dict[str, Any] | None = None, extra_lane: bool = False,
                     fail_close: str = "",
                     prefix: str = "automation/container-security-rebuild-") -> tuple[subprocess.CompletedProcess[str], str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    trigger_path = tmp_path / "lane-trigger.json"
    if trigger is not None:
        trigger_path.write_text(json.dumps(trigger), encoding="utf-8")
    lanes = [
        {"number": 423, "headRefName": "automation/container-security-rebuild-5c26f660271f-1",
         "baseRefName": "main", "isCrossRepository": False},
        {"number": 500, "headRefName": "automation/controller-positive-dry-run-x-1",
         "baseRefName": "main", "isCrossRepository": False},
        {"number": 501, "headRefName": "automation/container-security-rebuild-fork-1",
         "baseRefName": "main", "isCrossRepository": True},
    ]
    if extra_lane:
        lanes.append({"number": 424, "headRefName": "automation/container-security-rebuild-abc-2",
                      "baseRefName": "main", "isCrossRepository": False})
    (tmp_path / "lanes.json").write_text(json.dumps(lanes), encoding="utf-8")
    (tmp_path / "metadata.json").write_text(json.dumps(metadata or _bot_metadata()), encoding="utf-8")
    (fake_bin / "gh").write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$GH_LOG"
case "$1 $2" in
  "pr list") cat "$FAKE_DIR/lanes.json" ;;
  "pr view") cat "$FAKE_DIR/metadata.json" ;;
  "pr close") if [ "$3" = "$FAIL_CLOSE" ]; then exit 1; fi ;;
  "pr comment") while [ "$#" -gt 0 ]; do
      if [ "$1" = "--body-file" ]; then cp "$2" "$FAKE_DIR/posted.md"; fi; shift; done ;;
  *) echo "unexpected gh command: $*" >&2; exit 1 ;;
esac
""",
        encoding="utf-8",
    )
    (fake_bin / "git").write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf 'git %s\\n' "$*" >> "$GH_LOG"
case "$1" in
  fetch) exit 0 ;;
  show) test -f "$FAKE_DIR/lane-trigger.json" && cat "$FAKE_DIR/lane-trigger.json" ;;
  *) exit 1 ;;
esac
""",
        encoding="utf-8",
    )
    (fake_bin / "python3").write_text(f'#!/usr/bin/env bash\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
    for tool in ("gh", "git", "python3"):
        (fake_bin / tool).chmod(0o755)
    log_path = tmp_path / "gh.log"
    log_path.touch()
    completed = subprocess.run(
        ["bash", str(CLOSE_STALE_PATH), str(report_path), prefix, LANE_RUN_URL],
        cwd=ROOT,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}",
             "GITHUB_REPOSITORY": "duduvcastro/c3po", "RUNNER_TEMP": str(tmp_path),
             "GH_LOG": str(log_path), "FAKE_DIR": str(tmp_path), "FAIL_CLOSE": fail_close},
        text=True,
        capture_output=True,
    )
    return completed, log_path.read_text(encoding="utf-8")


def test_close_stale_lanes_closes_then_comments_only_on_the_production_lane(tmp_path: Path) -> None:
    scanner, controller = _modules()
    trigger = _lane_trigger(scanner, controller, critical=0, high=1)
    fresh = _fresh_clean_report(scanner)

    completed, log = _run_close_stale(tmp_path, report=fresh, trigger=trigger)

    assert completed.returncode == 0, completed.stderr
    assert "--app github-actions" in log
    assert "pr view 423 --repo duduvcastro/c3po --json files,commits,comments" in log
    assert "git fetch --no-tags --quiet origin refs/heads/automation/container-security-rebuild-5c26f660271f-1" in log
    assert log.index("pr close 423") < log.index("pr comment 423")
    assert "500" not in log.replace("--limit 100", "") and "501" not in log
    assert "Closed stale remediation lane #423" in completed.stdout
    posted = (tmp_path / "posted.md").read_text(encoding="utf-8")
    assert f"c3po-container-remediation-stale-close:{fresh['report_sha256']}" in posted
    assert "gh pr merge" not in CLOSE_STALE_PATH.read_text(encoding="utf-8")


@pytest.mark.parametrize("case", ["finding_still_present", "human_commit", "extra_file", "reopened_by_human"])
def test_close_stale_lanes_keeps_lanes_open_on_doubt(tmp_path: Path, case: str) -> None:
    scanner, controller = _modules()
    trigger = _lane_trigger(scanner, controller, critical=0, high=1)
    fresh = _fresh_clean_report(scanner)
    metadata = _bot_metadata()
    if case == "finding_still_present":
        fresh = _fresh_clean_report(scanner, unfixed_ids=("CVE-HIGH-0",))
    elif case == "human_commit":
        metadata = _bot_metadata(commits=[{"authors": [{"login": "duduvcastro"}]}])
    elif case == "extra_file":
        metadata = _bot_metadata(files=[{"path": TRIGGER_FILE, "changeType": "MODIFIED"},
                                        {"path": "c3po/frontend/Dockerfile", "changeType": "MODIFIED"}])
    else:
        metadata = _bot_metadata(comments=[{"body": "<!-- c3po-container-remediation-stale-close:old -->"}])

    completed, log = _run_close_stale(tmp_path, report=fresh, trigger=trigger, metadata=metadata)

    assert completed.returncode == 0, completed.stderr
    assert "::notice::Lane #423 kept open" in completed.stdout
    assert "pr comment" not in log
    assert "pr close" not in log


def test_close_stale_lanes_collects_errors_without_abandoning_other_lanes(tmp_path: Path) -> None:
    scanner, controller = _modules()
    completed, log = _run_close_stale(
        tmp_path, report=_fresh_clean_report(scanner),
        trigger=_lane_trigger(scanner, controller, critical=0, high=1),
        extra_lane=True, fail_close="423",
    )

    assert completed.returncode != 0
    assert "::error::Stale-lane reconciliation: #423: close failed" in completed.stdout
    assert "pr comment 423" not in log
    assert "pr close 424" in log and "pr comment 424" in log
    assert "Closed stale remediation lane #424" in completed.stdout


def test_close_stale_lanes_reports_an_unreadable_trigger_as_an_error(tmp_path: Path) -> None:
    scanner, _ = _modules()
    completed, log = _run_close_stale(tmp_path, report=_fresh_clean_report(scanner), trigger=None)

    assert completed.returncode != 0
    assert "#423: trigger evidence not readable" in completed.stdout
    assert "pr close" not in log and "pr comment" not in log


def test_close_stale_lanes_refuses_the_dry_run_lane_prefix(tmp_path: Path) -> None:
    scanner, controller = _modules()
    completed, log = _run_close_stale(
        tmp_path,
        report=_fresh_clean_report(scanner),
        trigger=_lane_trigger(scanner, controller, critical=0, high=1),
        prefix="automation/controller-positive-dry-run-",
    )

    assert completed.returncode != 0
    assert "only covers production remediation lanes" in completed.stderr
    assert log == ""


def test_scan_workflow_reconciles_stale_lanes_only_after_a_validated_clean_plan() -> None:
    import yaml

    workflow = yaml.safe_load(SCAN_WORKFLOW_PATH.read_text(encoding="utf-8"))
    controller_job = workflow["jobs"]["remediation-controller"]
    names = [step.get("name") for step in controller_job["steps"]]
    step = next(
        step for step in controller_job["steps"]
        if step.get("name") == "Close stale remediation lanes after a clean production scan"
    )

    assert names.index("Validate evidence and plan remediation") < names.index(step["name"])
    assert "steps.remediation.outputs.required == 'false'" in step["if"]
    assert "steps.remediation.outputs.dry_run == 'false'" in step["if"]
    assert step["continue-on-error"] is True
    assert step["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert ".github/scripts/c3po_close_stale_lanes.sh" in step["run"]
    assert "production-report/container-production-vulnerability-report.json" in step["run"]
    assert "pull-requests" in controller_job["permissions"]
    assert "needs.scan-production-images.result == 'success'" in controller_job["if"]
