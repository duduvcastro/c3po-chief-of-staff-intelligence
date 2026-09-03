from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REGISTRY_RELATIVE_PATH = Path("c3po/security/cve-acceptances.json")
SIGNED_SPEC_SHA256 = (
    "6a9dc31489959c0b5d4bcf7792e59ce6f6b2e7706802e8d2b0db9ac2e09cfd35"
)
MAX_REVIEW_PERIOD = timedelta(days=30)
SEVERITIES = ("critical", "high", "medium", "low")
ACCEPTABLE_SEVERITIES = {"critical", "high"}
CANONICAL_ACCEPTANCE_HANDS = {"dudu", "fable", "codex"}
JUSTIFICATION_MINIMUM = re.compile(
    r"(?:sem\s+fixedversion\s+upstream|"
    r"sem\s+severidade\s+atribu[ií]da\s+pelo\s+cat[aá]logo)"
    r"\s+em\s+\d{2}/\d{2}(?:/\d{4})?",
    re.IGNORECASE,
)
ENTRY_REQUIRED_FIELDS = {
    "vulnerability_id",
    "package",
    "image",
    "target",
    "installed_version",
    "justificativa",
    "accepted_by",
    "accepted_at",
    "review_at",
    "entry_sha256",
}
ENTRY_OPTIONAL_FIELDS = {"archived_at"}


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def acceptance_entry_sha256(entry: dict[str, Any]) -> str:
    payload = {key: value for key, value in entry.items() if key != "entry_sha256"}
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _parse_utc_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"CVE acceptance {field} is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError(f"CVE acceptance {field} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise RuntimeError(f"CVE acceptance {field} must be UTC")
    return parsed.astimezone(timezone.utc)


def _required_text(entry: dict[str, Any], field: str) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"CVE acceptance {field} is invalid")
    return value.strip()


def _validate_entry(entry: Any) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise RuntimeError("CVE acceptance registry entry is not an object")
    fields = set(entry)
    if not ENTRY_REQUIRED_FIELDS.issubset(fields):
        missing = sorted(ENTRY_REQUIRED_FIELDS - fields)
        raise RuntimeError(
            f"CVE acceptance registry entry is missing fields: {', '.join(missing)}"
        )
    unexpected = fields - ENTRY_REQUIRED_FIELDS - ENTRY_OPTIONAL_FIELDS
    if unexpected:
        raise RuntimeError(
            "CVE acceptance registry entry has unsupported fields: "
            f"{', '.join(sorted(unexpected))}"
        )
    for field in (
        "vulnerability_id",
        "package",
        "image",
        "target",
        "installed_version",
        "justificativa",
    ):
        _required_text(entry, field)
    if not JUSTIFICATION_MINIMUM.search(str(entry["justificativa"])):
        raise RuntimeError(
            "CVE acceptance justificativa lacks the required upstream/date basis"
        )
    accepted_by = entry.get("accepted_by")
    if (
        not isinstance(accepted_by, list)
        or len(accepted_by) != 3
        or any(not isinstance(name, str) or not name.strip() for name in accepted_by)
        or {name.strip().casefold() for name in accepted_by}
        != CANONICAL_ACCEPTANCE_HANDS
    ):
        raise RuntimeError(
            "CVE acceptance accepted_by must name Dudu, Fable and Codex"
        )
    accepted_at = _parse_utc_timestamp(entry.get("accepted_at"), "accepted_at")
    review_at = _parse_utc_timestamp(entry.get("review_at"), "review_at")
    if review_at <= accepted_at:
        raise RuntimeError("CVE acceptance review_at must be after accepted_at")
    if review_at - accepted_at > MAX_REVIEW_PERIOD:
        raise RuntimeError("CVE acceptance review_at exceeds 30 days")
    if "archived_at" in entry:
        archived_at = _parse_utc_timestamp(entry.get("archived_at"), "archived_at")
        if archived_at < accepted_at:
            raise RuntimeError("CVE acceptance archived_at predates accepted_at")
    observed_hash = entry.get("entry_sha256")
    if (
        not isinstance(observed_hash, str)
        or len(observed_hash) != 64
        or any(character not in "0123456789abcdef" for character in observed_hash)
        or observed_hash != acceptance_entry_sha256(entry)
    ):
        raise RuntimeError("CVE acceptance entry_sha256 is invalid")
    return dict(entry)


def load_acceptance_registry(root: Path) -> tuple[list[dict[str, Any]], str]:
    return load_acceptance_registry_file(root / REGISTRY_RELATIVE_PATH)


def load_acceptance_registry_file(path: Path) -> tuple[list[dict[str, Any]], str]:
    """Load and validate one exact registry file without weakening its byte hash."""
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("CVE acceptance registry is unavailable or invalid") from exc
    if not isinstance(payload, list):
        raise RuntimeError("CVE acceptance registry is not a list")
    entries = [_validate_entry(entry) for entry in payload]
    active_identities: set[tuple[str, str, str, str, str]] = set()
    for entry in entries:
        if "archived_at" in entry:
            continue
        identity = (
            str(entry["vulnerability_id"]),
            str(entry["package"]),
            str(entry["image"]),
            str(entry["target"]),
            str(entry["installed_version"]),
        )
        if identity in active_identities:
            raise RuntimeError("CVE acceptance registry has a duplicate active identity")
        active_identities.add(identity)
    return entries, hashlib.sha256(raw).hexdigest()


def archive_acceptances_for_findings(
    entries: list[dict[str, Any]],
    findings: list[dict[str, str]],
    *,
    archived_at: datetime,
) -> tuple[list[dict[str, Any]], int]:
    """Archive exact active entries when a rebuild finding becomes fixable."""
    if archived_at.tzinfo is None or archived_at.utcoffset() is None:
        raise RuntimeError("CVE acceptance archived_at must be timezone-aware")
    archived_utc = archived_at.astimezone(timezone.utc)
    identities = {
        (
            str(finding.get("vulnerability_id") or ""),
            str(finding.get("package") or ""),
            str(finding.get("image") or ""),
            str(finding.get("target") or ""),
            str(finding.get("installed_version") or ""),
        )
        for finding in findings
    }
    if any(not all(identity) for identity in identities):
        raise RuntimeError("CVE acceptance archival finding identity is incomplete")
    result: list[dict[str, Any]] = []
    archived_count = 0
    for original in entries:
        entry = dict(original)
        identity = (
            str(entry["vulnerability_id"]),
            str(entry["package"]),
            str(entry["image"]),
            str(entry["target"]),
            str(entry["installed_version"]),
        )
        if "archived_at" not in entry and identity in identities:
            entry["archived_at"] = archived_utc.isoformat()
            entry["entry_sha256"] = acceptance_entry_sha256(entry)
            archived_count += 1
        result.append(entry)
    return result, archived_count


def _finding_identity(
    image: str,
    finding: dict[str, Any],
) -> tuple[str, str, str, str, str]:
    return (
        str(finding.get("vulnerability_id") or ""),
        str(finding.get("package") or ""),
        image,
        str(finding.get("target") or ""),
        str(finding.get("installed_version") or ""),
    )


def _status_for_counts(
    counts: dict[str, int],
    *,
    unknown: int,
    dead_man_configured: bool,
) -> str:
    if counts["critical"] or counts["high"]:
        return "offline"
    if counts["medium"] or counts["low"] or unknown or not dead_man_configured:
        return "attention"
    return "healthy"


def _incident_status_for_counts(
    counts: dict[str, int],
    *,
    unknown: int,
    dead_man_configured: bool,
) -> str:
    if counts["critical"] or counts["high"]:
        return "offline"
    if unknown or not dead_man_configured:
        return "attention"
    return "healthy"


def validate_acceptance_overlay_payload(production_images: dict[str, Any]) -> None:
    acceptance = production_images.get("acceptance")
    if not isinstance(acceptance, dict) or acceptance.get("enabled") is not True:
        raise RuntimeError("CVE acceptance overlay payload is missing")
    if acceptance.get("signed_spec_sha256") != SIGNED_SPEC_SHA256:
        raise RuntimeError("CVE acceptance overlay signed spec hash is invalid")
    registry = acceptance.get("registry")
    registry_hash = registry.get("sha256") if isinstance(registry, dict) else None
    if (
        not isinstance(registry_hash, str)
        or len(registry_hash) != 64
        or any(character not in "0123456789abcdef" for character in registry_hash)
    ):
        raise RuntimeError("CVE acceptance overlay registry hash is invalid")
    counts = acceptance.get("counts")
    if not isinstance(counts, dict):
        raise RuntimeError("CVE acceptance overlay counters are missing")
    normalized: dict[str, dict[str, Any]] = {}
    for lane in ("raw", "accepted", "pending", "expired"):
        value = counts.get(lane)
        if not isinstance(value, dict):
            raise RuntimeError(f"CVE acceptance overlay {lane} counters are missing")
        by_severity = value.get("by_severity")
        if not isinstance(by_severity, dict):
            raise RuntimeError(f"CVE acceptance overlay {lane} severities are missing")
        normalized_counts: dict[str, int] = {}
        for severity in SEVERITIES:
            count = by_severity.get(severity)
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise RuntimeError(
                    f"CVE acceptance overlay {lane} severities are invalid"
                )
            normalized_counts[severity] = count
        unknown = value.get("unknown")
        total = value.get("total")
        if (
            isinstance(unknown, bool)
            or not isinstance(unknown, int)
            or unknown < 0
            or isinstance(total, bool)
            or not isinstance(total, int)
            or total != sum(normalized_counts.values()) + unknown
        ):
            raise RuntimeError(f"CVE acceptance overlay {lane} total is invalid")
        normalized[lane] = {
            "by_severity": normalized_counts,
            "unknown": unknown,
            "total": total,
        }
    raw = normalized["raw"]
    accepted = normalized["accepted"]
    pending = normalized["pending"]
    expired = normalized["expired"]
    if raw["total"] != production_images.get("finding_total"):
        raise RuntimeError("CVE acceptance overlay raw total changed Trivy evidence")
    if raw["by_severity"] != production_images.get("by_severity"):
        raise RuntimeError("CVE acceptance overlay raw severities changed Trivy evidence")
    if raw["unknown"] != production_images.get("unknown"):
        raise RuntimeError("CVE acceptance overlay raw unknown changed Trivy evidence")
    for severity in SEVERITIES:
        if raw["by_severity"][severity] != (
            accepted["by_severity"][severity] + pending["by_severity"][severity]
        ):
            raise RuntimeError("CVE acceptance overlay severity invariant is invalid")
        if expired["by_severity"][severity] > pending["by_severity"][severity]:
            raise RuntimeError("CVE acceptance overlay expired counters are invalid")
    if raw["unknown"] != accepted["unknown"] + pending["unknown"]:
        raise RuntimeError("CVE acceptance overlay unknown invariant is invalid")
    if raw["total"] != accepted["total"] + pending["total"]:
        raise RuntimeError("CVE acceptance overlay total invariant is invalid")
    findings = acceptance.get("findings")
    if not isinstance(findings, list):
        raise RuntimeError("CVE acceptance overlay findings are missing")
    observed = {
        status: {severity: 0 for severity in ACCEPTABLE_SEVERITIES}
        for status in ("pendente", "aceito", "aceito_vencido")
    }
    for finding in findings:
        if not isinstance(finding, dict):
            raise RuntimeError("CVE acceptance overlay finding is invalid")
        status = finding.get("acceptance_status")
        severity = finding.get("severity")
        if status not in observed or severity not in ACCEPTABLE_SEVERITIES:
            raise RuntimeError("CVE acceptance overlay finding status is invalid")
        observed[str(status)][str(severity)] += 1
    for severity in ACCEPTABLE_SEVERITIES:
        if observed["aceito"][severity] != accepted["by_severity"][severity]:
            raise RuntimeError("CVE acceptance overlay accepted findings are inconsistent")
        if observed["aceito_vencido"][severity] != expired["by_severity"][severity]:
            raise RuntimeError("CVE acceptance overlay expired findings are inconsistent")
        if (
            observed["pendente"][severity]
            + observed["aceito_vencido"][severity]
            != pending["by_severity"][severity]
        ):
            raise RuntimeError("CVE acceptance overlay pending findings are inconsistent")


def apply_acceptance_overlay(
    production_images: dict[str, Any],
    entries: list[dict[str, Any]],
    *,
    registry_sha256: str,
    measured_at: datetime,
) -> dict[str, Any]:
    """Return a governance-only overlay without mutating the raw Trivy projection."""
    if production_images.get("available") is not True:
        raise RuntimeError("CVE acceptance overlay requires a verifiable Trivy report")
    measured_utc = measured_at.astimezone(timezone.utc)
    raw_counts_value = production_images.get("by_severity")
    if not isinstance(raw_counts_value, dict):
        raise RuntimeError("CVE acceptance overlay has no raw severity counters")
    raw_counts: dict[str, int] = {}
    for severity in SEVERITIES:
        value = raw_counts_value.get(severity)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RuntimeError("CVE acceptance overlay raw counters are invalid")
        raw_counts[severity] = value
    unknown = production_images.get("unknown")
    if isinstance(unknown, bool) or not isinstance(unknown, int) or unknown < 0:
        raise RuntimeError("CVE acceptance overlay unknown counter is invalid")
    raw_total = production_images.get("finding_total")
    if (
        isinstance(raw_total, bool)
        or not isinstance(raw_total, int)
        or raw_total != sum(raw_counts.values()) + unknown
    ):
        raise RuntimeError("CVE acceptance overlay raw total is inconsistent")

    active_entries = [entry for entry in entries if "archived_at" not in entry]
    entries_by_identity = {
        (
            str(entry["vulnerability_id"]),
            str(entry["package"]),
            str(entry["image"]),
            str(entry["target"]),
            str(entry["installed_version"]),
        ): entry
        for entry in active_entries
    }
    matched_hashes: set[str] = set()
    findings: list[dict[str, Any]] = []
    accepted_counts = {severity: 0 for severity in SEVERITIES}
    expired_counts = {severity: 0 for severity in SEVERITIES}
    detailed_counts = {severity: 0 for severity in ACCEPTABLE_SEVERITIES}

    raw_images = production_images.get("images")
    if not isinstance(raw_images, list):
        raise RuntimeError("CVE acceptance overlay has no image evidence")
    if production_images.get("image_count") != len(raw_images):
        raise RuntimeError("CVE acceptance overlay image count is inconsistent")
    seen_images: set[str] = set()
    for image_value in raw_images:
        if not isinstance(image_value, dict):
            raise RuntimeError("CVE acceptance overlay image evidence is invalid")
        image = str(image_value.get("label") or "")
        if not image:
            raise RuntimeError("CVE acceptance overlay image label is invalid")
        if image in seen_images:
            raise RuntimeError("CVE acceptance overlay image label is duplicated")
        seen_images.add(image)
        for finding_field, fixable in (
            ("fixable_high_critical", True),
            ("unfixed_high_critical", False),
        ):
            detailed = image_value.get(finding_field) or []
            if not isinstance(detailed, list):
                raise RuntimeError("CVE acceptance overlay findings are invalid")
            for finding_value in detailed:
                if not isinstance(finding_value, dict):
                    raise RuntimeError("CVE acceptance overlay finding is invalid")
                severity = str(finding_value.get("severity") or "")
                if severity not in ACCEPTABLE_SEVERITIES:
                    raise RuntimeError(
                        "CVE acceptance overlay finding severity is invalid"
                    )
                detailed_counts[severity] += 1
                fixed_version = str(
                    finding_value.get("fixed_version") or ""
                ).strip()
                if fixable != bool(fixed_version):
                    raise RuntimeError(
                        "CVE acceptance overlay fixability evidence is inconsistent"
                    )
                identity = _finding_identity(image, finding_value)
                if not all(identity):
                    raise RuntimeError(
                        "CVE acceptance overlay finding identity is incomplete"
                    )
                entry = entries_by_identity.get(identity)
                acceptance_status = "pendente"
                review_at: str | None = None
                entry_hash: str | None = None
                if entry is not None:
                    entry_hash = str(entry["entry_sha256"])
                    if entry_hash in matched_hashes:
                        raise RuntimeError(
                            "CVE acceptance entry matches more than one raw occurrence"
                        )
                    matched_hashes.add(entry_hash)
                    accepted = _parse_utc_timestamp(
                        entry["accepted_at"], "accepted_at"
                    )
                    if accepted > measured_utc:
                        raise RuntimeError("CVE acceptance accepted_at is in the future")
                    review = _parse_utc_timestamp(entry["review_at"], "review_at")
                    review_at = review.isoformat()
                    if fixable:
                        # A newly published FixedVersion ends the risk-acceptance
                        # effect immediately. The signed registry entry remains
                        # attached for traceability, but the finding is actionable
                        # until the controller archives it in the rebuild PR.
                        acceptance_status = "pendente"
                    elif measured_utc >= review:
                        acceptance_status = "aceito_vencido"
                        expired_counts[severity] += 1
                    else:
                        acceptance_status = "aceito"
                        accepted_counts[severity] += 1
                findings.append({
                    "vulnerability_id": identity[0],
                    "package": identity[1],
                    "image": identity[2],
                    "target": identity[3],
                    "installed_version": identity[4],
                    "fixed_version": fixed_version,
                    "severity": severity,
                    "acceptance_status": acceptance_status,
                    "entry_sha256": entry_hash,
                    "review_at": review_at,
                })

    if any(
        detailed_counts[severity] != raw_counts[severity]
        for severity in ACCEPTABLE_SEVERITIES
    ):
        raise RuntimeError(
            "CVE acceptance overlay detailed critical/high counts are inconsistent"
        )

    unmatched = {
        str(entry["entry_sha256"])
        for entry in active_entries
    } - matched_hashes
    if unmatched:
        raise RuntimeError("CVE acceptance registry has active entries absent from raw report")
    pending_counts = {
        severity: raw_counts[severity] - accepted_counts[severity]
        for severity in SEVERITIES
    }
    if any(value < 0 for value in pending_counts.values()):
        raise RuntimeError("CVE acceptance counters exceed raw Trivy counters")
    accepted_total = sum(accepted_counts.values())
    pending_total = raw_total - accepted_total
    nearest_review = min(
        (
            str(finding["review_at"])
            for finding in findings
            if finding["acceptance_status"] == "aceito"
        ),
        default=None,
    )
    pending_status = _status_for_counts(
        pending_counts,
        unknown=unknown,
        dead_man_configured=production_images.get("dead_man_configured") is True,
    )
    presentation_status = (
        "attention" if accepted_total and pending_status == "healthy" else pending_status
    )
    incident_status = _incident_status_for_counts(
        pending_counts,
        unknown=unknown,
        dead_man_configured=production_images.get("dead_man_configured") is True,
    )
    result = deepcopy(production_images)
    result["status"] = presentation_status
    result["acceptance"] = {
        "enabled": True,
        "signed_spec_sha256": SIGNED_SPEC_SHA256,
        "registry": {
            "path": REGISTRY_RELATIVE_PATH.as_posix(),
            "sha256": registry_sha256,
            "entries": len(entries),
            "active_entries": len(active_entries),
            "archived_entries": len(entries) - len(active_entries),
        },
        "counts": {
            "raw": {
                "total": raw_total,
                "by_severity": raw_counts,
                "unknown": unknown,
            },
            "accepted": {
                "total": accepted_total,
                "by_severity": accepted_counts,
                "unknown": 0,
            },
            "pending": {
                "total": pending_total,
                "by_severity": pending_counts,
                "unknown": unknown,
            },
            "expired": {
                "total": sum(expired_counts.values()),
                "by_severity": expired_counts,
                "unknown": 0,
            },
        },
        "nearest_review_at": nearest_review,
        "findings": sorted(
            findings,
            key=lambda finding: (
                str(finding["image"]),
                str(finding["severity"]),
                str(finding["vulnerability_id"]),
                str(finding["package"]),
                str(finding["target"]),
            ),
        ),
        "incident_status": incident_status,
    }
    validate_acceptance_overlay_payload(result)
    return result
