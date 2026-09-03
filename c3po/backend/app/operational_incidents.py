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

    def resolve_key(
        self,
        incident_key: str,
        detail: str,
        *,
        at: datetime | None = None,
    ) -> dict[str, Any] | None:
        incident = self.database.operational_incident_by_key(incident_key)
        if not incident or incident["status"] == "resolved":
            return incident
        return self.database.transition_operational_incident(
            incident_id=incident["id"],
            event_type="resolved",
            actor_email="system",
            detail=detail,
            at=at or datetime.now(timezone.utc),
        )
