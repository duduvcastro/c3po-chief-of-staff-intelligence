"""The supervised governance attestation must resolve or signal the operational
incident by its factual result from EVERY entry point (worker, API button, CLI),
and the panel must not keep reading a stale system-health snapshot after it.

Defect (Codex, #348 5573486252): the API instance (main.py) and the CLI built the
service without ``operational_incidents``; a healthy attestation from the panel
button could be persisted while the incident stayed open, and the consolidated
system-health cache (60 s) was not invalidated by the route.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app import main as app_main
from app.governance_vulnerability import GovernanceVulnerabilityService, build_supervised_service
from app.operational_incidents import OperationalIncidentService
from app.system_health import SystemHealthService


def test_api_attestation_service_carries_the_incident_service() -> None:
    # Same object the incident routes use: resolution/signal lands on the same ledger.
    assert app_main.governance_vulnerability.operational_incidents is app_main.operational_incidents
    assert isinstance(app_main.governance_vulnerability.operational_incidents, OperationalIncidentService)


def test_cli_builder_wires_incidents_on_the_same_database() -> None:
    database = SimpleNamespace(name="stub-database")
    service = build_supervised_service(app_main.settings, database)
    assert isinstance(service, GovernanceVulnerabilityService)
    assert isinstance(service.operational_incidents, OperationalIncidentService)
    assert service.operational_incidents.database is database
    assert service.database is database


def test_attestation_route_invalidates_the_system_health_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, int] = {"invalidate": 0, "run": 0}

    class _Governance:
        def run_supervised(self, root):
            calls["run"] += 1
            calls["root"] = root
            return True, {
                "status": "healthy",
                "session_date": "2026-09-07",
                "revision": 6,
                "report_sha256": "a" * 64,
                "generated_at": "2026-09-07T17:30:05+00:00",
            }

    class _SystemHealth:
        def invalidate(self) -> None:
            calls["invalidate"] += 1

    monkeypatch.setattr(app_main, "require_owner", lambda request: None)
    monkeypatch.setattr(app_main, "governance_vulnerability", _Governance())
    monkeypatch.setattr(app_main, "system_health", _SystemHealth())

    payload = app_main.run_governance_attestation(request=object())

    assert calls == {"invalidate": 1, "run": 1, "root": app_main.settings.legacy_root}
    assert payload["status"] == "healthy" and payload["revision"] == 6
    assert payload["report_sha256"] == "a" * 64


def test_system_health_invalidate_forces_a_recomputation() -> None:
    settings = SimpleNamespace(system_health_probe_timeout_seconds=1)
    service = SystemHealthService(settings, None, None, None, None, None, cache_seconds=60)
    refreshes: list[datetime] = []

    def _refresh(now: datetime):
        refreshes.append(now)
        return SimpleNamespace(generated_at=now, sequence=len(refreshes))

    service._refresh_snapshot = _refresh  # type: ignore[method-assign]

    first = service.snapshot()
    second = service.snapshot()
    assert first is second and len(refreshes) == 1  # cached inside the window

    service.invalidate()
    assert service._cached_response is None and service._cached_at is None

    third = service.snapshot()
    assert third is not first and len(refreshes) == 2
    assert refreshes[1].tzinfo is timezone.utc
