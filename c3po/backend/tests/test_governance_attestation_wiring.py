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
    assert service._cache is None

    third = service.snapshot()
    assert third is not first and len(refreshes) == 2
    assert refreshes[1].tzinfo is timezone.utc


def test_a_reader_interleaved_with_invalidate_never_gets_none() -> None:
    # C390-1: freshness and payload come from one immutable entry; an invalidate landing between the
    # freshness test and the read of a concurrent GET cannot turn the response into None.
    import threading

    settings = SimpleNamespace(system_health_probe_timeout_seconds=1)
    service = SystemHealthService(settings, None, None, None, None, None, cache_seconds=60)
    service._refresh_snapshot = lambda now: SimpleNamespace(generated_at=now)  # type: ignore[method-assign]
    service.snapshot()
    original = service._cached

    def interleaved():  # the reader took its entry; the invalidation lands right after
        entry = original()
        service.invalidate()
        return entry

    service._cached = interleaved  # type: ignore[method-assign]
    assert service.snapshot() is not None
    service._cached = original  # type: ignore[method-assign]
    # brute force: readers and invalidators racing for real
    failures: list[str] = []
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            if service.snapshot() is None:
                failures.append("None")

    def invalidator() -> None:
        while not stop.is_set():
            service.invalidate()

    threads = [threading.Thread(target=reader) for _ in range(4)] + [threading.Thread(target=invalidator) for _ in range(2)]
    for thread in threads:
        thread.start()
    threading.Event().wait(0.5)
    stop.set()
    for thread in threads:
        thread.join(timeout=5)
    assert failures == []


def test_a_refresh_in_flight_cannot_republish_a_snapshot_that_predates_an_invalidation() -> None:
    # C390-3 (Codex 5574978039): a refresh captures revision 1 -> the attestation persists revision 2 and invalidates
    # -> the old refresh finishes. It must NOT put revision 1 back as fresh: the next GET recomputes and sees revision 2.
    import threading

    settings = SimpleNamespace(system_health_probe_timeout_seconds=1)
    service = SystemHealthService(settings, None, None, None, None, None, cache_seconds=60)
    revision = {"value": 1}
    started, release = threading.Event(), threading.Event()

    def _refresh(now: datetime):
        current = revision["value"]  # the world as the probes saw it
        started.set()
        release.wait(5)
        return SimpleNamespace(generated_at=now, revision=current)

    service._refresh_snapshot = _refresh  # type: ignore[method-assign]
    results: list[SimpleNamespace] = []
    reader = threading.Thread(target=lambda: results.append(service.snapshot()))
    reader.start()
    assert started.wait(5)
    revision["value"] = 2  # the supervised attestation persisted revision 2 ...
    service.invalidate()  # ... and the route invalidated the cache while the old refresh is still running
    release.set()
    reader.join(5)
    assert results[0].revision == 1  # the caller of the old refresh gets what it computed ...
    assert service._cache is None  # ... but the stale snapshot is never cached
    assert service.snapshot().revision == 2  # the next GET recomputes
    # control: with no invalidation in between, a refresh is cached normally
    assert service._cache is not None and service._cache[1].revision == 2
    started.clear()
    release.set()
    assert service.snapshot(force=True).revision == 2 and service._cache is not None


def test_attestation_route_invalidates_even_when_the_run_raises_after_persisting(monkeypatch: pytest.MonkeyPatch) -> None:
    # C390-2: run_supervised persists the revision before it may still raise (e.g. an unverifiable lane query);
    # the cache must be invalidated on that path too, and the original error must propagate.
    calls = {"invalidate": 0}

    class _Governance:
        def run_supervised(self, root):
            raise RuntimeError("remediation lane query is not verifiable")

    class _SystemHealth:
        def invalidate(self) -> None:
            calls["invalidate"] += 1

    monkeypatch.setattr(app_main, "require_owner", lambda request: None)
    monkeypatch.setattr(app_main, "governance_vulnerability", _Governance())
    monkeypatch.setattr(app_main, "system_health", _SystemHealth())
    with pytest.raises(RuntimeError, match="not verifiable"):
        app_main.run_governance_attestation(request=object())
    assert calls["invalidate"] == 1
    # and when the owner check fails nothing is invalidated (no authorized run happened)
    calls["invalidate"] = 0

    def _refuse(request):
        raise PermissionError("owner only")

    monkeypatch.setattr(app_main, "require_owner", _refuse)
    with pytest.raises(PermissionError):
        app_main.run_governance_attestation(request=object())
    assert calls["invalidate"] == 0
