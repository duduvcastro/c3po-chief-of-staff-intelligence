#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from c3po_trivy_scan import SCHEMA as REPORT_SCHEMA
from c3po_trivy_scan import SEVERITIES as FIXABLE_SEVERITIES
from c3po_trivy_scan import report_sha256


TRIGGER_SCHEMA = "C3PO_CONTAINER_REMEDIATION_TRIGGER-v1"
HIGH_CRITICAL = ("critical", "high")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PR_MARKER = "<!-- c3po-container-remediation -->"
PRODUCTION_LANE_PREFIX = "automation/container-security-rebuild-"
DRY_RUN_LANE_PREFIX = "automation/controller-positive-dry-run-"
DRY_RUN_SCOPE = "controller_dry_run"
DRY_RUN_FIXTURE_ID = "container-remediation-positive-v1"
DRY_RUN_FIXTURE_SHA256 = (
    "249a8bfec3dd4baee1572a3dba260f601ed77d806ecbafa6c8fc9066cef47f2d"
)


class ReportValidationError(RuntimeError):
    pass


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReportValidationError(f"{field} must be a non-negative integer")
    return value


def load_report(path: Path) -> dict[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportValidationError(f"cannot read normalized report: {exc}") from exc
    if not isinstance(report, dict):
        raise ReportValidationError("normalized report must be a JSON object")
    return report


def validate_report(
    report: dict[str, Any],
    *,
    expected_scope: str = "production_runtime",
    require_dead_man: bool = True,
) -> tuple[dict[str, int], list[dict[str, str]]]:
    observed_hash = report.get("report_sha256")
    if not isinstance(observed_hash, str) or not HASH_PATTERN.fullmatch(observed_hash):
        raise ReportValidationError("report_sha256 must be a lowercase SHA-256")
    if observed_hash != report_sha256(report):
        raise ReportValidationError("normalized report self-hash mismatch")
    if report.get("schema") != REPORT_SCHEMA:
        raise ReportValidationError("unsupported normalized report schema")
    if report.get("scope") != expected_scope:
        raise ReportValidationError(
            f"remediation controller expected scope {expected_scope}"
        )
    if report.get("scan_status") != "complete" or report.get("errors") != []:
        raise ReportValidationError("production scan is not complete and error-free")
    if require_dead_man and report.get("dead_man_configured") is not True:
        raise ReportValidationError("production scan did not attest its dead-man")

    raw_counts = report.get("fix_available")
    if not isinstance(raw_counts, dict):
        raise ReportValidationError("fix_available must be an object")
    counts: dict[str, int] = {
        severity: _nonnegative_int(raw_counts.get(severity), f"fix_available.{severity}")
        for severity in FIXABLE_SEVERITIES
    }

    images = report.get("images")
    if not isinstance(images, list):
        raise ReportValidationError("images must be a list")
    findings: list[dict[str, str]] = []
    aggregate_image_counts = {severity: 0 for severity in FIXABLE_SEVERITIES}
    seen_labels: set[str] = set()
    required_fields = (
        "vulnerability_id",
        "severity",
        "package",
        "installed_version",
        "fixed_version",
        "target",
    )
    for image in images:
        if not isinstance(image, dict):
            raise ReportValidationError("each image entry must be an object")
        label = image.get("label")
        if not isinstance(label, str) or not label or label in seen_labels:
            raise ReportValidationError("image labels must be non-empty and unique")
        seen_labels.add(label)
        raw_image_counts = image.get("fix_available")
        if not isinstance(raw_image_counts, dict):
            raise ReportValidationError(f"image {label} is missing fix_available counts")
        image_counts = {
            severity: _nonnegative_int(
                raw_image_counts.get(severity),
                f"image {label} fix_available.{severity}",
            )
            for severity in FIXABLE_SEVERITIES
        }
        for severity in FIXABLE_SEVERITIES:
            aggregate_image_counts[severity] += image_counts[severity]

        raw_findings = image.get("fixable_findings")
        if not isinstance(raw_findings, list):
            raise ReportValidationError(
                f"image {label} is missing fixable_findings evidence"
            )
        image_findings: list[dict[str, str]] = []
        for raw_finding in raw_findings:
            if not isinstance(raw_finding, dict):
                raise ReportValidationError("fixable finding must be an object")
            finding: dict[str, str] = {"image": label}
            for field in required_fields:
                value = raw_finding.get(field)
                if not isinstance(value, str) or not value.strip():
                    raise ReportValidationError(
                        f"fixable finding {field} must be a non-empty string"
                    )
                finding[field] = value.strip()
            if finding["severity"] not in FIXABLE_SEVERITIES:
                raise ReportValidationError(
                    "fixable finding severity must be critical, high, medium or low"
                )
            image_findings.append(finding)

        image_detail_counts = {
            severity: sum(
                1 for finding in image_findings if finding["severity"] == severity
            )
            for severity in FIXABLE_SEVERITIES
        }
        if image_detail_counts != image_counts:
            raise ReportValidationError(
                f"image {label} fixable detail/count mismatch: "
                f"details={image_detail_counts}, totals={image_counts}"
            )

        raw_high_critical = image.get("fixable_high_critical")
        if not isinstance(raw_high_critical, list):
            raise ReportValidationError(
                f"image {label} is missing fixable_high_critical compatibility evidence"
            )
        expected_high_critical = [
            {field: finding[field] for field in required_fields}
            for finding in image_findings
            if finding["severity"] in HIGH_CRITICAL
        ]
        if raw_high_critical != expected_high_critical:
            raise ReportValidationError(
                f"image {label} fixable_high_critical projection mismatch"
            )
        findings.extend(image_findings)

    if aggregate_image_counts != counts:
        raise ReportValidationError(
            "top-level/image fixable count mismatch: "
            f"images={aggregate_image_counts}, totals={counts}"
        )
    detail_counts: dict[str, int] = {
        severity: sum(1 for finding in findings if finding["severity"] == severity)
        for severity in FIXABLE_SEVERITIES
    }
    if detail_counts != counts:
        raise ReportValidationError(
            f"fixable detail/count mismatch: details={detail_counts}, totals={counts}"
        )
    findings.sort(
        key=lambda finding: (
            FIXABLE_SEVERITIES.index(finding["severity"]),
            finding["vulnerability_id"],
            finding["image"],
            finding["package"],
            finding["target"],
        )
    )
    return counts, findings


def validate_positive_dry_run_fixture(
    path: Path,
    report: dict[str, Any],
) -> tuple[dict[str, int], list[dict[str, str]]]:
    try:
        raw_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ReportValidationError(f"cannot seal dry-run fixture: {exc}") from exc
    if raw_hash != DRY_RUN_FIXTURE_SHA256:
        raise ReportValidationError("positive dry-run fixture seal mismatch")
    if report.get("fixture_id") != DRY_RUN_FIXTURE_ID:
        raise ReportValidationError("unexpected positive dry-run fixture id")
    if report.get("dead_man_configured") is not False:
        raise ReportValidationError("dry-run fixture must not attest a production dead-man")
    counts, findings = validate_report(
        report,
        expected_scope=DRY_RUN_SCOPE,
        require_dead_man=False,
    )
    if counts != {"critical": 0, "high": 1, "medium": 0, "low": 0} or findings != [{
        "image": "controller-positive-control",
        "vulnerability_id": "C3PO-DRY-RUN-FIXABLE-001",
        "severity": "high",
        "package": "c3po-positive-control",
        "installed_version": "1",
        "fixed_version": "2",
        "target": "synthetic-controller-fixture",
    }]:
        raise ReportValidationError("positive dry-run fixture payload is not the pinned control")
    return counts, findings


def build_trigger(
    report: dict[str, Any],
    *,
    counts: dict[str, int],
    findings: list[dict[str, str]],
    run_url: str,
    artifact_name: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    generated_at = report.get("generated_at")
    source_revision = report.get("source_revision")
    if not isinstance(generated_at, str) or not generated_at:
        raise ReportValidationError("generated_at must be a non-empty string")
    if not isinstance(source_revision, str) or not source_revision:
        raise ReportValidationError("source_revision must be a non-empty string")
    if not run_url.startswith("https://github.com/"):
        raise ReportValidationError("run_url must be an HTTPS GitHub URL")
    if not artifact_name:
        raise ReportValidationError("artifact_name must not be empty")
    remediation_key = hashlib.sha256(
        json.dumps(
            {"fix_available": counts, "findings": findings},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "schema": TRIGGER_SCHEMA,
        "remediation_key": remediation_key,
        "generated_at": generated_at,
        "source_revision": source_revision,
        "report_sha256": report["report_sha256"],
        "run_url": run_url,
        "artifact_name": artifact_name,
        "dry_run": dry_run,
        "evidence_scope": report["scope"],
        "fix_available": counts,
        "finding_total": sum(counts.values()),
        "findings": findings,
    }


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_pr_body(trigger: dict[str, Any]) -> str:
    counts = trigger["fix_available"]
    findings = trigger["findings"]
    dry_run = trigger.get("dry_run") is True
    lines = [
        PR_MARKER,
        (
            "## CONTROLE SINTÉTICO — NÃO É PRODUÇÃO"
            if dry_run
            else "## Remediação automática de imagens"
        ),
        "",
        (
            "Esta PR-fixture exercita a máquina de estados do controlador com uma "
            "ocorrência sintética selada. Não representa um achado de produção."
            if dry_run
            else "O controlador remoto detectou uma `FixedVersion` no scan completo das imagens "
        ),
        (
            "Ela nunca deve ser mergeada e será fechada após a execução supervisionada."
            if dry_run
            else "em produção e abriu esta PR sem depender de workstation ou Codex desktop."
        ),
        "",
        f"- Critical fixável: **{counts['critical']}**",
        f"- High fixável: **{counts['high']}**",
        f"- Medium fixável: **{counts['medium']}**",
        f"- Low fixável: **{counts['low']}**",
        f"- Report self-hash: `{trigger['report_sha256']}`",
        f"- Chave de deduplicação: `{trigger['remediation_key']}`",
        f"- [Workflow de origem]({trigger['run_url']})",
        f"- Artefato: `{trigger['artifact_name']}`",
        f"- Escopo da evidência: `{trigger['evidence_scope']}`",
        "",
        "| Imagem | Severidade | CVE | Pacote | Instalada | FixedVersion |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for finding in findings[:100]:
        lines.append(
            "| "
            + " | ".join(
                _cell(finding[field])
                for field in (
                    "image",
                    "severity",
                    "vulnerability_id",
                    "package",
                    "installed_version",
                    "fixed_version",
                )
            )
            + " |"
        )
    if len(findings) > 100:
        lines.extend(["", f"Mais {len(findings) - 100} ocorrências constam no artefato."])
    lines.extend(["", "### Rito obrigatório", ""])
    if dry_run:
        lines.extend([
            "O commit existe somente para forçar o rebuild e validar o controlador. "
            "A PR-fixture não pode ser mergeada. A validação usa `deploy=false`.",
            "Fable audita a evidência e Dudu supervisiona o encerramento sem merge.",
            "",
            "Se `verify-zero` ficar vermelho na Fase B, isso indica um achado fixável real "
            "nas imagens atuais; não é defeito do harness e exige remediação normal.",
            "",
        ])
    else:
        lines.extend([
            "O commit inicial apenas força rebuild integral a partir das bases pinadas e dos ",
            "repositórios oficiais. Se o scan da PR não zerar todos os achados fixáveis, Codex ajusta ",
            "pacotes ou digests nesta mesma PR. Fable audita a evidência final. Dudu autoriza ",
            "o merge. **Não há auto-merge nem deploy antes desses portões.**",
            "",
            "Após o deploy, o scan de produção deve ser reexecutado e o atestado deve consumir ",
            "o novo report.",
            "",
        ])
    return "\n".join(lines)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _append_github_outputs(path: Path, outputs: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for key, value in outputs.items():
            handle.write(f"{key}={value}\n")


def _plan(args: argparse.Namespace, *, dry_run: bool) -> int:
    report = load_report(args.report)
    if dry_run:
        counts, findings = validate_positive_dry_run_fixture(args.report, report)
        lane_prefix = DRY_RUN_LANE_PREFIX
    else:
        counts, findings = validate_report(report)
        lane_prefix = PRODUCTION_LANE_PREFIX
    required = sum(counts.values()) > 0
    remediation_key = ""
    if required:
        trigger = build_trigger(
            report,
            counts=counts,
            findings=findings,
            run_url=args.run_url,
            artifact_name=args.artifact_name,
            dry_run=dry_run,
        )
        remediation_key = trigger["remediation_key"]
        _write_json(args.trigger, trigger)
        args.pr_body.write_text(render_pr_body(trigger), encoding="utf-8")
    outputs = {
        "required": "true" if required else "false",
        "report_sha256": str(report["report_sha256"]),
        "remediation_key": remediation_key,
        "lane_prefix": lane_prefix,
        "dry_run": "true" if dry_run else "false",
    }
    outputs.update({severity: str(counts[severity]) for severity in FIXABLE_SEVERITIES})
    _append_github_outputs(args.github_output, outputs)
    print(json.dumps({"required": required, "fix_available": counts}, sort_keys=True))
    return 0


def plan(args: argparse.Namespace) -> int:
    return _plan(args, dry_run=False)


def plan_dry_run_positive(args: argparse.Namespace) -> int:
    return _plan(args, dry_run=True)


def verify_zero(args: argparse.Namespace) -> int:
    report = load_report(args.report)
    counts, _ = validate_report(
        report,
        expected_scope="pull_request_build",
        require_dead_man=False,
    )
    print(json.dumps({"fix_available": counts}, sort_keys=True))
    if sum(counts.values()) > 0:
        raise ReportValidationError(
            f"remediation still has fixable findings: {counts}"
        )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate production Trivy evidence and control remediation PRs"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--report", type=Path, required=True)
    plan_parser.add_argument("--trigger", type=Path, required=True)
    plan_parser.add_argument("--pr-body", type=Path, required=True)
    plan_parser.add_argument("--run-url", required=True)
    plan_parser.add_argument("--artifact-name", required=True)
    plan_parser.add_argument("--github-output", type=Path, required=True)
    plan_parser.set_defaults(handler=plan)

    dry_run_parser = subparsers.add_parser("plan-dry-run-positive")
    dry_run_parser.add_argument("--report", type=Path, required=True)
    dry_run_parser.add_argument("--trigger", type=Path, required=True)
    dry_run_parser.add_argument("--pr-body", type=Path, required=True)
    dry_run_parser.add_argument("--run-url", required=True)
    dry_run_parser.add_argument("--artifact-name", required=True)
    dry_run_parser.add_argument("--github-output", type=Path, required=True)
    dry_run_parser.set_defaults(handler=plan_dry_run_positive)

    verify_parser = subparsers.add_parser("verify-zero")
    verify_parser.add_argument("--report", type=Path, required=True)
    verify_parser.set_defaults(handler=verify_zero)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        code = args.handler(args)
    except ReportValidationError as exc:
        raise SystemExit(f"fail-closed: {exc}") from exc
    raise SystemExit(code)


if __name__ == "__main__":
    main()
