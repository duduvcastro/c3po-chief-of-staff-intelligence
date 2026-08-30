from __future__ import annotations

import importlib.util
import json
import sys
from argparse import Namespace
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCANNER_PATH = ROOT / "scripts" / "c3po_trivy_scan.py"
CONTROLLER_PATH = ROOT / "scripts" / "c3po_container_remediation.py"


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


def _report(scanner: ModuleType, *, critical: int = 1, high: int = 1) -> dict[str, Any]:
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
            "fixable_high_critical": findings,
        }],
        "by_severity": {"critical": critical, "high": high, "medium": 0, "low": 0},
        "fix_available": {"critical": critical, "high": high, "medium": 0, "low": 0},
        "unknown": 0,
        "finding_total": critical + high,
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
    assert "Não há auto-merge" in body
    assert "Fable audita" in body
    assert "Dudu autoriza" in body


def test_controller_accepts_a_zero_fixable_report_without_opening_work() -> None:
    scanner, controller = _modules()
    report = _report(scanner, critical=0, high=0)

    counts, findings = controller.validate_report(report)

    assert counts == {"critical": 0, "high": 0}
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
    assert trigger_path.exists() is required
    assert body_path.exists() is required


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

    assert counts == {"critical": 0, "high": 0}
    assert findings == []


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
