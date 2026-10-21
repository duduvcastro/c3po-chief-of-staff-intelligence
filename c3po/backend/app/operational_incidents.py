from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections.abc import MutableMapping
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import Settings, get_settings
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


# ------------------------------------------------------------------------------------------------
# Read-only aggregate report (ops-readonly-report.yml): `python -m app.operational_incidents --report-json`.
# AGGREGATES ONLY. Every string it prints comes from a closed vocabulary below: no incident key, title,
# detail, evidence, actor, card name or card detail ever leaves the process (they may name a symbol or a
# person). The runner re-verifies the exact schema before anything is uploaded or posted.
REPORT_SCHEMA = "C3PO-OPS-INCIDENTS-REPORT-v2"  # v2: + stale_running_ingestion
READ_ONLY_PGOPTION = "-c default_transaction_read_only=on"
GOVERNANCE_INCIDENT_KIND = "governance-vulnerability"  # governance_vulnerability.GOVERNANCE_INCIDENT_KEY (no import: cycle)
NOTIFICATION_KINDS = ("job_failure", "disk_threshold")
INCIDENT_KINDS = (GOVERNANCE_INCIDENT_KIND, *(f"notification:{kind}" for kind in NOTIFICATION_KINDS), "other")
INCIDENT_SOURCES = ("governance", "worker", "host", "other")
INCIDENT_SEVERITIES = ("critical", "attention", "other")
ACTIVE_STATUSES = ("open", "acknowledged")
HEALTH_GROUPS = ("governance", "controls")
HEALTH_STATUSES = ("offline", "attention")  # red, amber
# The local (database and evidence-file) cards of system_health, by their fixed English/Portuguese label.
HEALTH_CARDS = {
    "Governança & Vulnerabilidades": "governance_vulnerabilities",
    "Incidentes operacionais": "operational_incidents",
    "Valuation worker phases": "valuation_worker_phases",
    "Valuation V2.1b cycle": "valuation_v2_1b_cycle",
    "V3 pre-A/B gate": "v3_pre_ab_gate",
    "Day D disk reserve": "day_d_disk_reserve",
    "B2 zero-cap evidence": "b2_zero_cap_evidence",
}
HEALTH_CARD_KEYS = (*HEALTH_CARDS.values(), "probe_failed", "unmapped")
INCIDENT_SCAN_LIMIT = 1000
OVER_24H_HOURS = 24.0
STALE_RUNNING_MINUTES = 30
STALE_RUNNING_HORIZON = timedelta(days=7)


def force_read_only_session(environ: MutableMapping[str, str] | None = None) -> str:
    """Every transaction of this process is read-only in PostgreSQL itself (libpq reads PGOPTIONS)."""
    env: MutableMapping[str, str] = os.environ if environ is None else environ
    current = env.get("PGOPTIONS", "").replace(READ_ONLY_PGOPTION, " ").split()
    env["PGOPTIONS"] = " ".join([*current, READ_ONLY_PGOPTION])
    return env["PGOPTIONS"]


def incident_kind(incident_key: str) -> str:
    """A closed vocabulary: the key itself never leaves (a notification key carries a free title)."""
    if incident_key == GOVERNANCE_INCIDENT_KIND:
        return GOVERNANCE_INCIDENT_KIND
    parts = incident_key.split(":", 2)
    if len(parts) >= 2 and parts[0] == "notification" and parts[1] in NOTIFICATION_KINDS:
        return f"notification:{parts[1]}"
    return "other"


def _utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()


def _hours(start: datetime, now: datetime) -> float:
    return round(max(0.0, (now - start).total_seconds()) / 3600, 1)


def incidents_aggregate(database: Database, now: datetime) -> dict[str, Any]:
    incidents = database.list_operational_incidents(limit=INCIDENT_SCAN_LIMIT)
    groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    totals = {"active": 0, "open": 0, "acknowledged": 0, "critical": 0, "over_24h": 0}
    oldest: float | None = None
    for incident in incidents:
        status = incident.get("status")
        if status not in ACTIVE_STATUSES:
            continue
        key = str(incident.get("incident_key") or "")
        source = incident.get("source") if incident.get("source") in INCIDENT_SOURCES else "other"
        severity = incident.get("severity") if incident.get("severity") in INCIDENT_SEVERITIES else "other"
        # the current episode (opened_at keeps the first opening forever, even after resolve/reopen)
        started = _utc(database.operational_incident_open_since(key)) or _utc(incident.get("opened_at")) or now
        last_seen = _utc(incident.get("last_seen_at")) or started
        age = _hours(started, now)
        group = groups.setdefault((incident_kind(key), str(source), str(severity), str(status)), {
            "kind": incident_kind(key), "source": source, "severity": severity, "status": status,
            "count": 0, "over_24h": 0, "oldest_started_at": _iso(started), "oldest_age_hours": age,
            "last_seen_at": _iso(last_seen),
        })
        group["count"] += 1
        group["over_24h"] += age > OVER_24H_HOURS
        if age >= group["oldest_age_hours"]:
            group["oldest_age_hours"], group["oldest_started_at"] = age, _iso(started)
        group["last_seen_at"] = max(group["last_seen_at"], _iso(last_seen))
        totals["active"] += 1
        totals[str(status)] += 1
        totals["critical"] += severity == "critical"
        totals["over_24h"] += age > OVER_24H_HOURS
        oldest = age if oldest is None else max(oldest, age)
    return {
        "scanned": len(incidents),
        "totals": {**totals, "oldest_age_hours": oldest},
        "groups": sorted(groups.values(), key=lambda item: (item["kind"], item["source"], item["severity"], item["status"])),
    }


def _refuse_network(*_args: Any, **_kwargs: Any) -> Any:
    raise RuntimeError("the read-only incidents report never reaches the network")


def health_cards(settings: Settings, database: Database, now: datetime) -> dict[str, Any]:
    """Red/amber cards among the LOCAL cards of the health panel (database rows and evidence files only):
    governance, incidents and the Day D/valuation controls. The external probes (and the healthcheck ping)
    are never run here."""
    from .system_health import SystemHealthService  # lazy: system_health → governance_vulnerability → this module

    service = SystemHealthService(settings, database, None, None, None, None, external_get=_refuse_network)
    loaders = {
        "governance": lambda: [service._governance_vulnerability_health(now), service._operational_incident_health(now)],
        "controls": lambda: service._day_d_and_valuation_health(now),
    }
    cards: list[dict[str, str]] = []
    evaluated = 0
    for group in HEALTH_GROUPS:
        for item in service._safe_items(group, loaders[group], now):
            evaluated += 1
            if item.status in HEALTH_STATUSES:
                card = HEALTH_CARDS.get(item.name, "probe_failed" if item.name == group else "unmapped")
                cards.append({"group": group, "card": card, "status": item.status})
    return {"evaluated": evaluated, "cards": sorted(cards, key=lambda item: (item["group"], item["card"], item["status"]))}


def stale_running_ingestion(database: Database, now: datetime) -> dict[str, Any]:
    """Ingestion runs still `running` more than 30 min after they started, within the last 7 days: a count and the
    oldest age only (the source code and the run metadata, which may list symbols, never leave). Older leftovers are
    out of scope so the age stays bounded."""
    cutoff = now - timedelta(minutes=STALE_RUNNING_MINUTES)
    horizon = now - STALE_RUNNING_HORIZON
    if not database.database_url:
        runs = getattr(database, "_ingestion_runs", {}).values()
        started = [_utc(run.get("started_at")) for run in runs if run.get("status") == "running"]
        started = [moment for moment in started if moment is not None and moment >= horizon]
    else:
        with database.connection() as connection:
            rows = connection.execute(
                "SELECT started_at FROM ingestion_runs WHERE status = 'running' AND started_at < %s AND started_at >= %s",
                (cutoff, horizon),
            ).fetchall()
        started = [_utc(row[0]) for row in rows]
    ages = [int((now - moment).total_seconds() // 60) for moment in started if moment is not None and moment < cutoff]
    return {"threshold_minutes": STALE_RUNNING_MINUTES, "count": len(ages), "oldest_age_minutes": max(ages, default=None)}


def report_sha256(report: dict[str, Any]) -> str:
    body = {key: value for key, value in report.items() if key != "report_sha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def incidents_report(settings: Settings, database: Database, now: datetime | None = None) -> dict[str, Any]:
    moment = _utc(now) or datetime.now(timezone.utc)
    build = os.environ.get("C3PO_BUILD_SHA") or ""
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "generated_at": _iso(moment),
        "build_sha": build if re.fullmatch(r"[0-9a-f]{40}", build) else None,
        "incidents": incidents_aggregate(database, moment),
        "health": health_cards(settings, database, moment),
        "stale_running_ingestion": stale_running_ingestion(database, moment),
    }
    report["report_sha256"] = report_sha256(report)
    return report


def main(argv: list[str] | None = None, *, settings: Settings | None = None, database: Database | None = None,
         now: datetime | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only aggregate of open operational incidents and red/amber local "
                                                 "health cards (no keys, titles, details or symbols).")
    parser.add_argument("--report-json", action="store_true", required=True, help="print the aggregate report as one JSON line")
    parser.parse_args(argv)
    force_read_only_session()
    settings = settings or get_settings()
    database = database or Database(settings)
    print(json.dumps(incidents_report(settings, database, now), sort_keys=True, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
