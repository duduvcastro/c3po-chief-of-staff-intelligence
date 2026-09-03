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
PRODUCTION_RUNTIME_SCOPE = "production_runtime"
PRODUCTION_IMAGE_LABELS = ("backend", "web", "database")


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
    fixable_high_critical: list[dict[str, str]] = []
    unfixed_high_critical: list[dict[str, str]] = []
    unknown = 0
    for result in payload.get("Results") or []:
        for vulnerability in result.get("Vulnerabilities") or []:
            severity = str(vulnerability.get("Severity") or "unknown").lower()
            fixed_version = str(vulnerability.get("FixedVersion") or "").strip()
            if severity in counts:
                counts[severity] += 1
                if fixed_version:
                    fix_available[severity] += 1
                    if severity in {"critical", "high"}:
                        fixable_high_critical.append({
                            "vulnerability_id": str(
                                vulnerability.get("VulnerabilityID") or "unknown"
                            ),
                            "severity": severity,
                            "package": str(vulnerability.get("PkgName") or "unknown"),
                            "installed_version": str(
                                vulnerability.get("InstalledVersion") or "unknown"
                            ),
                            "fixed_version": fixed_version,
                            "target": str(result.get("Target") or "unknown"),
                        })
                elif severity in {"critical", "high"}:
                    unfixed_high_critical.append({
                        "vulnerability_id": str(vulnerability.get("VulnerabilityID") or "unknown"),
                        "severity": severity,
                        "package": str(vulnerability.get("PkgName") or "unknown"),
                        "installed_version": str(vulnerability.get("InstalledVersion") or "unknown"),
                        "fixed_version": fixed_version,
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
        "rootfs_layers": [str(item) for item in metadata.get("DiffIDs") or []],
        "repo_digests": sorted(str(item) for item in metadata.get("RepoDigests") or []),
        "by_severity": counts,
        "fix_available": fix_available,
        "fixable_high_critical": sorted(
            fixable_high_critical,
            key=lambda finding: (
                finding["severity"],
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
        if label in origins:
            raise ValueError(f"duplicate origin label: {label}")
        image_ref, image_id, rootfs = parts
        rootfs_layers = rootfs.split(",")
        if not all(rootfs_layers):
            raise ValueError(f"invalid origin specification: {spec}")
        origins[label] = {
            "image_ref": image_ref,
            "image_id": image_id,
            "rootfs_layers": rootfs_layers,
        }
    return origins


def archive_config_image_ids(
    manifest: Any,
    requested_refs: list[tuple[str, str]],
) -> dict[str, str]:
    if not isinstance(manifest, list):
        raise ValueError("Docker archive manifest must be a list")
    entries: dict[str, dict[str, Any]] = {}
    for item in manifest:
        if not isinstance(item, dict):
            raise ValueError("Docker archive manifest entries must be objects")
        repo_tags = item.get("RepoTags") or []
        if not isinstance(repo_tags, list):
            raise ValueError("Docker archive RepoTags must be a list")
        for tag in repo_tags:
            if not isinstance(tag, str) or not tag:
                raise ValueError("Docker archive RepoTags must be non-empty strings")
            if tag in entries:
                raise ValueError(f"duplicate Docker archive RepoTag: {tag}")
            entries[tag] = item

    requested_labels: set[str] = set()
    requested_images: set[str] = set()
    result: dict[str, str] = {}
    for label, reference in requested_refs:
        if not label or label in requested_labels:
            raise ValueError(f"duplicate requested image label: {label}")
        if not reference or reference in requested_images:
            raise ValueError(f"duplicate requested image reference: {reference}")
        requested_labels.add(label)
        requested_images.add(reference)
        item = entries.get(reference)
        if item is None:
            raise ValueError(f"Docker archive is missing {reference}")
        config = item.get("Config")
        digest = ""
        if isinstance(config, str):
            if "/" not in config and config.endswith(".json"):
                # Classic Docker image store archive.
                digest = config.removesuffix(".json")
            elif config.startswith("blobs/sha256/") and config.count("/") == 2:
                # Docker's containerd image store emits an OCI-style config path.
                digest = config.removeprefix("blobs/sha256/")
        if (
            len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError(f"Docker archive config digest is invalid for {reference}")
        result[label] = f"sha256:{digest}"
    return result


def verify_origin_identity(
    image: dict[str, Any],
    origin: dict[str, Any],
) -> None:
    label = str(image.get("label") or "unknown")
    # The production containerd store exposes a manifest digest while the
    # runner Docker store and Trivy expose a config digest. Ordered DiffIDs are
    # the cross-store content identity; both digest namespaces remain recorded.
    if image.get("rootfs_layers") != origin["rootfs_layers"]:
        raise RuntimeError(f"scanned ordered RootFS does not match live origin for {label}")


def build_report(
    image_specs: list[str],
    *,
    scope: str,
    revision: str,
    dead_man_configured: bool = False,
    origin_specs: list[str] | None = None,
    transport_sha256: str | None = None,
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
        if any(existing_label == label for existing_label, _ in parsed_specs):
            raise ValueError(f"duplicate image label: {label}")
        parsed_specs.append((label, reference))
    origins = parse_origin_specs(origin_specs or [])
    if transport_sha256 is not None and (
        len(transport_sha256) != 64
        or any(character not in "0123456789abcdef" for character in transport_sha256)
    ):
        raise ValueError("transport sha256 is not lowercase hexadecimal")
    scanned_labels = {label for label, _ in parsed_specs}
    unknown_origins = sorted(set(origins) - scanned_labels)
    if unknown_origins:
        raise ValueError(f"origin labels without a scanned image: {unknown_origins}")
    if scope == PRODUCTION_RUNTIME_SCOPE:
        required_labels = set(PRODUCTION_IMAGE_LABELS)
        if scanned_labels != required_labels:
            raise ValueError(
                "production runtime scan requires exactly backend, web and database images"
            )
        missing_origins = sorted(required_labels - set(origins))
        if missing_origins:
            raise ValueError(f"production image labels without an origin: {missing_origins}")
        if transport_sha256 is None:
            raise ValueError("production runtime scan requires a verified transport sha256")
    with tempfile.TemporaryDirectory(prefix="c3po-trivy-") as temporary:
        work = Path(temporary)
        for label, reference in parsed_specs:
            try:
                image = scan_image(label, reference, work)
            except Exception as exc:
                errors.append({"label": label, "error": f"{type(exc).__name__}: {exc}"})
            else:
                image["origin"] = origins.get(label)
                if image["origin"] is not None:
                    try:
                        verify_origin_identity(image, image["origin"])
                    except Exception as exc:
                        errors.append({"label": label, "error": f"{type(exc).__name__}: {exc}"})
                        continue
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
        "source_transport": {
            "kind": "verified_docker_archive" if transport_sha256 else "local_docker_store",
            "sha256": transport_sha256,
        },
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
    parser.add_argument("--transport-sha256")
    args = parser.parse_args()
    report = build_report(
        args.images,
        scope=args.scope,
        revision=args.revision,
        dead_man_configured=args.dead_man_configured,
        origin_specs=args.origins,
        transport_sha256=args.transport_sha256,
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
