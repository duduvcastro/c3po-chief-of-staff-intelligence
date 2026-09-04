#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "C3PO_CONTAINER_VULNERABILITY_REPORT-v2"
TRIVY_VERSION = "0.74.0"
TRIVY_IMAGE = (
    "aquasec/trivy@sha256:"
    "62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969"
)
SEVERITIES = ("critical", "high", "medium", "low")


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def report_sha256(report: dict[str, Any]) -> str:
    payload = {key: value for key, value in report.items() if key != "report_sha256"}
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def normalize_trivy_payload(label: str, reference: str, payload: dict[str, Any]) -> dict[str, Any]:
    counts = {severity: 0 for severity in SEVERITIES}
    fix_available = {severity: 0 for severity in SEVERITIES}
    fixable_findings: list[dict[str, str]] = []
    fixable_high_critical: list[dict[str, str]] = []
    unfixed_high_critical: list[dict[str, str]] = []
    unknown = 0
    for result in payload.get("Results") or []:
        for vulnerability in result.get("Vulnerabilities") or []:
            severity = str(vulnerability.get("Severity") or "unknown").strip().lower()
            fixed_version = str(vulnerability.get("FixedVersion") or "").strip()
            if severity in counts:
                counts[severity] += 1
                if fixed_version:
                    fix_available[severity] += 1
                    finding = {
                        "vulnerability_id": str(
                            vulnerability.get("VulnerabilityID") or "unknown"
                        ).strip(),
                        "severity": severity,
                        "package": str(
                            vulnerability.get("PkgName") or "unknown"
                        ).strip(),
                        "installed_version": str(
                            vulnerability.get("InstalledVersion") or "unknown"
                        ).strip(),
                        "fixed_version": fixed_version,
                        "target": str(result.get("Target") or "unknown").strip(),
                    }
                    fixable_findings.append(finding)
                    if severity in {"critical", "high"}:
                        fixable_high_critical.append(finding)
                elif severity in {"critical", "high"}:
                    unfixed_high_critical.append({
                        "vulnerability_id": str(vulnerability.get("VulnerabilityID") or "unknown"),
                        "severity": severity,
                        "package": str(vulnerability.get("PkgName") or "unknown"),
                        "installed_version": str(vulnerability.get("InstalledVersion") or "unknown"),
                        "target": str(result.get("Target") or "unknown"),
                    })
            else:
                unknown += 1
    metadata = payload.get("Metadata") or {}
    return {
        "label": label,
        "reference": reference,
        "artifact_name": str(payload.get("ArtifactName") or reference),
        "image_id": str(metadata.get("ImageID") or ""),
        "repo_digests": sorted(str(item) for item in metadata.get("RepoDigests") or []),
        "by_severity": counts,
        "fix_available": fix_available,
        "fixable_findings": sorted(
            fixable_findings,
            key=lambda finding: (
                SEVERITIES.index(finding["severity"]),
                finding["vulnerability_id"],
                finding["package"],
                finding["target"],
            ),
        ),
        "fixable_high_critical": sorted(
            fixable_high_critical,
            key=lambda finding: (
                SEVERITIES.index(finding["severity"]),
                finding["vulnerability_id"],
                finding["package"],
                finding["target"],
            ),
        ),
        "unfixed_high_critical": sorted(
            unfixed_high_critical,
            key=lambda finding: (
                finding["severity"],
                finding["vulnerability_id"],
                finding["package"],
                finding["target"],
            ),
        ),
        "unknown": unknown,
        "finding_total": sum(counts.values()) + unknown,
    }


def scan_image(label: str, reference: str, work: Path) -> dict[str, Any]:
    raw_path = work / f"{label}.json"
    cache_path = work / "cache"
    cache_path.mkdir(exist_ok=True)
    docker_socket_group = Path("/var/run/docker.sock").stat().st_gid
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--group-add",
            str(docker_socket_group),
            "--volume",
            "/var/run/docker.sock:/var/run/docker.sock",
            "--volume",
            f"{work}:/reports",
            "--volume",
            f"{cache_path}:/tmp/trivy-cache",
            TRIVY_IMAGE,
            "image",
            "--cache-dir",
            "/tmp/trivy-cache",
            "--format",
            "json",
            "--output",
            f"/reports/{raw_path.name}",
            "--scanners",
            "vuln",
            "--exit-code",
            "0",
            reference,
        ],
        check=True,
        timeout=900,
    )
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Trivy output is not a JSON object")
    return normalize_trivy_payload(label, reference, payload)


def parse_origin_specs(origin_specs: list[str]) -> dict[str, dict[str, Any]]:
    origins: dict[str, dict[str, Any]] = {}
    for spec in origin_specs:
        if "=" not in spec:
            raise ValueError(f"invalid origin specification: {spec}")
        label, value = spec.split("=", 1)
        parts = value.split("|")
        if not label or len(parts) != 3 or not all(parts):
            raise ValueError(f"invalid origin specification: {spec}")
        image_ref, image_id, rootfs = parts
        origins[label] = {
            "image_ref": image_ref,
            "image_id": image_id,
            "rootfs_layers": rootfs.split(","),
        }
    return origins


def build_report(
    image_specs: list[str],
    *,
    scope: str,
    revision: str,
    dead_man_configured: bool = False,
    origin_specs: list[str] | None = None,
) -> dict[str, Any]:
    images: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    parsed_specs: list[tuple[str, str]] = []
    for spec in image_specs:
        if "=" not in spec:
            raise ValueError(f"invalid image specification: {spec}")
        label, reference = spec.split("=", 1)
        if not label or not reference:
            raise ValueError(f"invalid image specification: {spec}")
        parsed_specs.append((label, reference))
    origins = parse_origin_specs(origin_specs or [])
    unknown_origins = sorted(set(origins) - {label for label, _ in parsed_specs})
    if unknown_origins:
        raise ValueError(f"origin labels without a scanned image: {unknown_origins}")
    with tempfile.TemporaryDirectory(prefix="c3po-trivy-") as temporary:
        work = Path(temporary)
        for label, reference in parsed_specs:
            try:
                image = scan_image(label, reference, work)
            except Exception as exc:
                errors.append({"label": label, "error": f"{type(exc).__name__}: {exc}"})
            else:
                image["origin"] = origins.get(label)
                images.append(image)
    counts = {severity: 0 for severity in SEVERITIES}
    fix_available = {severity: 0 for severity in SEVERITIES}
    for image in images:
        for severity in SEVERITIES:
            counts[severity] += int(image["by_severity"][severity])
            fix_available[severity] += int(image["fix_available"][severity])
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scan_status": "complete" if not errors and len(images) == len(image_specs) else "error",
        "scope": scope,
        "source_revision": revision,
        "dead_man_configured": dead_man_configured,
        "scanner": {
            "name": "Trivy",
            "version": TRIVY_VERSION,
            "image": TRIVY_IMAGE,
        },
        "images": images,
        "by_severity": counts,
        "fix_available": fix_available,
        "unknown": sum(int(image["unknown"]) for image in images),
        "finding_total": sum(counts.values()) + sum(int(image["unknown"]) for image in images),
        "errors": errors,
        "counting_method": (
            "finding occurrences summed per image; the same vulnerability may be "
            "counted in multiple images"
        ),
    }
    report["report_sha256"] = report_sha256(report)
    return report


def atomic_write(output: Path, report: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=output.parent,
        prefix=f".{output.name}.",
        delete=False,
    ) as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.chmod(temporary, 0o644)
    temporary.replace(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan container images with pinned Trivy")
    parser.add_argument("--image", action="append", required=True, dest="images")
    parser.add_argument("--origin", action="append", default=[], dest="origins")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--revision", default="unknown")
    parser.add_argument("--dead-man-configured", action="store_true")
    args = parser.parse_args()
    report = build_report(
        args.images,
        scope=args.scope,
        revision=args.revision,
        dead_man_configured=args.dead_man_configured,
        origin_specs=args.origins,
    )
    atomic_write(args.output, report)
    if report["scan_status"] != "complete" and os.environ.get("GITHUB_ACTIONS") == "true":
        print("::warning::Trivy scan did not complete; the normalized report is fail-closed")
    print(json.dumps({
        "scan_status": report["scan_status"],
        "critical": report["by_severity"]["critical"],
        "high": report["by_severity"]["high"],
        "report_sha256": report["report_sha256"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
