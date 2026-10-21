from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from .database import Database


SENSITIVE_EVIDENCE_KEY = re.compile(
    r"(?:token|secret|password|authorization|endpoint|p256dh|auth_key)",
    re.IGNORECASE,
)


def validate_evidence(evidence: dict[str, Any]) -> None:
    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if SENSITIVE_EVIDENCE_KEY.search(str(key)):
                    raise ValueError(f"sensitive incident evidence key rejected: {path}{key}")
                walk(child, f"{path}{key}.")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}{index}.")
    walk(evidence, "")


def evidence_sha256(evidence: dict[str, Any]) -> str:
    raw = json.dumps(
        evidence,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class OperationalIncidentService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def signal(
        self,
        *,
        incident_key: str,
        source: str,
        severity: str,
        title: str,
        detail: str,
        deep_link: str,
        evidence: dict[str, Any],
        at: datetime | None = None,
    ) -> dict[str, Any]:
        validate_evidence(evidence)
        return self.database.record_operational_incident(
            incident_key=incident_key,
            source=source,
            severity=severity,
            title=title,
            detail=detail,
            deep_link=deep_link,
            evidence=evidence,
            evidence_sha256=evidence_sha256(evidence),
            at=at or datetime.now(timezone.utc),
        )

    def acknowledge(self, incident_id: str, actor_email: str) -> dict[str, Any] | None:
        return self.database.transition_operational_incident(
            incident_id=incident_id,
            event_type="acknowledged",
            actor_email=actor_email,
            detail="Incident acknowledged by owner",
            at=datetime.now(timezone.utc),
        )

    def resolve(
        self,
        incident_id: str,
        actor_email: str,
        resolution: str,
    ) -> dict[str, Any] | None:
        return self.database.transition_operational_incident(
            incident_id=incident_id,
            event_type="resolved",
            actor_email=actor_email,
            detail=resolution.strip() or "Incident resolved by owner",
            at=datetime.now(timezone.utc),
        )

    def open_since(self, incident_key: str) -> datetime | None:
        """Start of the current unresolved episode, or None when there is none."""
        return self.database.operational_incident_open_since(incident_key)

    def resolve_key(self, incident_key: str, detail: str) -> dict[str, Any] | None:
        incident = self.database.operational_incident_by_key(incident_key)
        if not incident or incident["status"] == "resolved":
            return incident
        return self.database.transition_operational_incident(
            incident_id=incident["id"],
            event_type="resolved",
            actor_email="system",
            detail=detail,
            at=datetime.now(timezone.utc),
        )

    def set_severity(
        self,
        *,
        incident_key: str,
        severity: str,
        detail: str,
        evidence: dict[str, Any],
        at: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Change an unresolved incident's severity, recorded as an event."""
        validate_evidence(evidence)
        return self.database.set_operational_incident_severity(
            incident_key=incident_key,
            severity=severity,
            detail=detail,
            evidence=evidence,
            evidence_sha256=evidence_sha256(evidence),
            at=at or datetime.now(timezone.utc),
        )

    def resolve_recovered_family(
        self, incident_key: str, *, observed_at: datetime, detail: str,
    ) -> int:
        """Close ``incident_key`` and its per-day siblings ``incident_key:<suffix>``
        when the recovery evidence covers them (nothing newer than ``observed_at``).
        Returns how many incidents were resolved."""
        resolved = 0
        for incident in self.database.list_operational_incidents(limit=1000):
            key = incident["incident_key"]
            if incident["status"] == "resolved" or not (
                key == incident_key or key.startswith(f"{incident_key}:")
            ):
                continue
            result = self.database.transition_operational_incident(
                incident_id=incident["id"], event_type="resolved", actor_email="system",
                detail=detail, at=observed_at, recovered_through=observed_at,
            )
            resolved += bool(result and result["status"] == "resolved")
        return resolved

    def resolve_recovered_prefix(
        self, prefix: str, *, observed_at: datetime, detail: str,
    ) -> None:
        """Close prior dated alerts only when the recovery evidence covers them."""
        for incident in self.database.list_operational_incidents(limit=1000):
            if incident["incident_key"].startswith(prefix) and incident["status"] != "resolved":
                self.database.transition_operational_incident(
                    incident_id=incident["id"], event_type="resolved", actor_email="system",
                    detail=detail, at=datetime.now(timezone.utc),
                    recovered_through=observed_at,
                )
