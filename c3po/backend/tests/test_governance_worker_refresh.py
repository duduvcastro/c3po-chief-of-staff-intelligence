"""Worker follow-ups use the real scheduler, with only the attestation mocked.

All reports are disposable files and the database is the memory double. No
external probe, healthcheck, notification or host operation is executed.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.database import Database
from app.governance_vulnerability import (
    AUTOMATION_REPORT,
    CONTAINER_REPORT_RELATIVE_PATH,
    HOST_OS_REPORT_RELATIVE_PATH,
    GovernanceVulnerabilityService,
    RoutineObservationPending,
    report_sha256,
)
from app.server_usage_worker import GovernanceRefresh
from app import server_usage_worker
from app.operational_incidents import OperationalIncidentService
from tests.test_governance_vulnerability import _GitHub, _Push, _alert, _lane, _root, _service, _write_layer_report


NOW = datetime(2026, 10, 22, 4, 10, tzinfo=timezone.utc)  # before the ordinary 02:15 BRT gate


def _routine(root: Path, at: datetime, *, status: str = "waiting_npm_evidence", valid_hash: bool = True) -> dict[str, Any]:
    report: dict[str, Any] = {"schema": "C3PO_SECURITY_AUTOMATION-v1", "generated_at": at.isoformat(), "status": status}
    report["report_sha256"] = report_sha256(report) if valid_hash else "bad-hash"
    path = root / AUTOMATION_REPORT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report), encoding="utf-8")
    return report


def _worker(monkeypatch: pytest.MonkeyPatch, *, grace_until: datetime | None = None):
    database = Database(Settings(database_url="", auth_cookie_secure=False))
    service = GovernanceVulnerabilityService(Settings(database_url="", auth_cookie_secure=False), database)
    calls: list[datetime] = []

    def attest(root: Path, *, now: datetime, defer_observed: bool = False):
        calls.append(now)
        routine = json.loads((root / AUTOMATION_REPORT).read_text())
        if (defer_observed and routine.get("status") == "observed"
                and routine.get("report_sha256") == report_sha256(routine)
                and now - datetime.fromisoformat(routine["generated_at"]) < timedelta(minutes=10)):
            raise RoutineObservationPending("synthetic preliminary observation")
        revision, _ = database.next_governance_vulnerability_revision(now.date())
        report = {
            "session_date": now.date().isoformat(), "revision": revision,
            "generated_at": now.isoformat(), "status": "attention",
            "dependabot": {"open_total": 0}, "governance": {"drift": []},
            "security_automation": {"report_sha256": routine["report_sha256"]},
            "post_deploy_grace": {"active": grace_until is not None and now < grace_until,
                                  "until": grace_until.isoformat() if grace_until else None},
        }
        report["report_sha256"] = report_sha256(report)
        return database.save_governance_vulnerability_report(report), report

    monkeypatch.setattr(service, "run_supervised", attest)
    return GovernanceRefresh(service), service, calls


def test_changed_report_refreshes_after_one_minute_even_after_a_recent_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    worker, service, calls = _worker(monkeypatch)
    _routine(tmp_path, NOW)
    assert service.run_daily_if_due(tmp_path, now=NOW, force=True)
    _routine(tmp_path, NOW + timedelta(seconds=10), status="waiting_pipeline")
    assert not worker.run_if_due(tmp_path, now=NOW + timedelta(seconds=10))
    assert not worker.run_if_due(tmp_path, now=NOW + timedelta(seconds=69))
    assert worker.run_if_due(tmp_path, now=NOW + timedelta(seconds=70))
    assert calls == [NOW, NOW + timedelta(seconds=70)]
    assert not worker.run_if_due(tmp_path, now=NOW + timedelta(minutes=2))


def test_recent_observed_report_never_persists_an_attestation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    worker, service, calls = _worker(monkeypatch)
    _routine(tmp_path, NOW, status="observed")
    for seconds in (0, 60, 599):
        assert not worker.run_if_due(tmp_path, now=NOW + timedelta(seconds=seconds))
    assert service.database.latest_governance_vulnerability_report() is None
    assert calls == [NOW + timedelta(seconds=60), NOW + timedelta(seconds=599)]
    assert worker.run_if_due(tmp_path, now=NOW + timedelta(minutes=10))
    assert calls[-1] == NOW + timedelta(minutes=10)


def test_preliminary_retries_are_bounded_to_one_per_minute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    worker, _, calls = _worker(monkeypatch)
    _routine(tmp_path, NOW, status="observed")
    for seconds in range(0, 151, 15):
        assert not worker.run_if_due(tmp_path, now=NOW + timedelta(seconds=seconds))
    assert calls == [NOW + timedelta(seconds=60), NOW + timedelta(seconds=120)]


def test_final_report_is_refreshed_without_waiting_ten_minutes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    worker, _, calls = _worker(monkeypatch)
    _routine(tmp_path, NOW, status="observed")
    assert not worker.run_if_due(tmp_path, now=NOW)
    _routine(tmp_path, NOW + timedelta(minutes=2), status="healthy")
    assert not worker.run_if_due(tmp_path, now=NOW + timedelta(minutes=2))
    assert worker.run_if_due(tmp_path, now=NOW + timedelta(minutes=3))
    assert calls == [NOW + timedelta(minutes=3)]


def test_invalid_observed_report_does_not_gain_a_ten_minute_hold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    worker, _, calls = _worker(monkeypatch)
    _routine(tmp_path, NOW, status="observed", valid_hash=False)
    assert not worker.run_if_due(tmp_path, now=NOW)
    assert worker.run_if_due(tmp_path, now=NOW + timedelta(minutes=1))
    assert calls == [NOW + timedelta(minutes=1)]


def test_grace_expiry_forces_one_attestation_at_the_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    until = NOW + timedelta(minutes=3)
    worker, service, calls = _worker(monkeypatch, grace_until=until)
    _routine(tmp_path, NOW)
    assert service.run_daily_if_due(tmp_path, now=NOW, force=True)
    assert not worker.run_if_due(tmp_path, now=until - timedelta(seconds=1))
    assert worker.run_if_due(tmp_path, now=until)
    assert not worker.run_if_due(tmp_path, now=until + timedelta(seconds=1))
    assert calls == [NOW, until]
    report = service.database.latest_governance_vulnerability_report()
    assert report is not None and report["post_deploy_grace"]["active"] is False


def test_report_change_at_expiry_does_not_postpone_the_deadline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    until = NOW + timedelta(minutes=3)
    worker, service, calls = _worker(monkeypatch, grace_until=until)
    _routine(tmp_path, NOW)
    assert service.run_daily_if_due(tmp_path, now=NOW, force=True)
    _routine(tmp_path, until, status="waiting_pipeline")
    assert worker.run_if_due(tmp_path, now=until)
    assert calls == [NOW, until]


def test_expiry_still_waits_for_a_recent_preliminary_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    until = NOW + timedelta(minutes=3)
    worker, service, calls = _worker(monkeypatch, grace_until=until)
    _routine(tmp_path, NOW)
    assert service.run_daily_if_due(tmp_path, now=NOW, force=True)
    _routine(tmp_path, until, status="observed")
    assert not worker.run_if_due(tmp_path, now=until)
    assert not worker.run_if_due(tmp_path, now=until + timedelta(minutes=9, seconds=59))
    assert calls == [NOW, until, until + timedelta(minutes=9, seconds=59)]
    assert worker.run_if_due(tmp_path, now=until + timedelta(minutes=10))
    assert calls[-1] == until + timedelta(minutes=10)


def test_changed_evidence_does_not_reset_failed_attempt_backoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    worker, service, calls = _worker(monkeypatch)
    succeeds = service.run_supervised

    def failed(root: Path, *, now: datetime, defer_observed: bool = False):
        raise RuntimeError("synthetic attestation unavailable")

    monkeypatch.setattr(service, "run_supervised", failed)
    _routine(tmp_path, NOW)
    assert not worker.run_if_due(tmp_path, now=NOW)
    with pytest.raises(RuntimeError, match="synthetic"):
        worker.run_if_due(tmp_path, now=NOW + timedelta(minutes=1))
    monkeypatch.setattr(service, "run_supervised", succeeds)
    _routine(tmp_path, NOW + timedelta(minutes=2), status="waiting_pipeline")
    assert not worker.run_if_due(tmp_path, now=NOW + timedelta(minutes=2))
    assert not worker.run_if_due(tmp_path, now=NOW + timedelta(minutes=3))
    assert not worker.run_if_due(tmp_path, now=NOW + timedelta(minutes=30, seconds=59))
    assert worker.run_if_due(tmp_path, now=NOW + timedelta(minutes=31))
    assert calls == [NOW + timedelta(minutes=31)]


def test_short_governance_wakes_preserve_the_configured_sampling_cadence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [0.0]
    governance: list[float] = []
    samples: list[float] = []
    alerts: list[float] = []
    census: list[float] = []

    class StopWorker(Exception):
        pass

    @contextmanager
    def admitted():
        yield True

    def purge(_before):
        if len(samples) == 2:
            raise StopWorker

    def sample(_before, _after):
        samples.append(clock[0])
        return {"cpu_percent": 0.0, "cpu_steal_percent": 0.0, "load_average_1m": 0.0,
                "disk_used_bytes": 1, "disk_total_bytes": 100}

    settings = SimpleNamespace(server_usage_interval_seconds=180, server_usage_disk_path=tmp_path,
                               server_usage_retention_days=7)
    database = SimpleNamespace(initialize=lambda: None, save_server_usage_samples=lambda _rows: None,
                               purge_server_usage_samples=purge)
    monkeypatch.setattr(server_usage_worker, "startup_job", admitted)
    monkeypatch.setattr(server_usage_worker, "job", admitted)
    monkeypatch.setattr(server_usage_worker, "get_settings", lambda: settings)
    monkeypatch.setattr(server_usage_worker, "init_sentry", lambda *_a, **_k: None)
    monkeypatch.setattr(server_usage_worker, "Database", lambda _settings: database)
    monkeypatch.setattr(server_usage_worker, "PushNotificationService", lambda *_a: object())
    monkeypatch.setattr(server_usage_worker, "OperationalIncidentService", lambda *_a: object())
    monkeypatch.setattr(server_usage_worker, "ServerUsageCollector", lambda *_a: SimpleNamespace(cpu_ticks=lambda: {}, sample=sample))
    monkeypatch.setattr(server_usage_worker, "CodeCensusService", lambda *_a: SimpleNamespace(run_daily_if_due=lambda _root: census.append(clock[0])))
    monkeypatch.setattr(server_usage_worker, "PushMarketAlertsService", lambda *_a: SimpleNamespace(run_once=lambda: alerts.append(clock[0])))
    monkeypatch.setattr(server_usage_worker, "GovernanceVulnerabilityService", lambda *_a, **_k: object())
    monkeypatch.setattr(server_usage_worker, "GovernanceRefresh", lambda _service: SimpleNamespace(run_if_due=lambda _root: governance.append(clock[0])))
    monkeypatch.setattr(server_usage_worker.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(server_usage_worker.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    with pytest.raises(StopWorker):
        server_usage_worker.run_worker()
    assert governance == [60, 120, 180, 240, 300, 360]
    assert samples == [180, 360]
    assert census == [180, 360] and alerts == [180, 360]


def test_routine_switching_to_observed_during_collection_is_deferred_without_failure(tmp_path: Path) -> None:
    root = _root(tmp_path, NOW)
    github = _GitHub()
    service = _service(tmp_path, github)
    push = _Push()
    service.push_notifications = push  # type: ignore[assignment]
    service.operational_incidents = OperationalIncidentService(service.database)
    health: list[str] = []
    service.healthcheck.ping = lambda status="success": health.append(status) or True  # type: ignore[method-assign]
    refresh = GovernanceRefresh(service)
    changed = False

    def during_collection(url: str, **kwargs: Any):
        nonlocal changed
        if not changed:
            changed = True
            _routine(root, NOW + timedelta(minutes=1), status="observed")
        return github.get(url, **kwargs)

    service.external_get = during_collection
    assert not refresh.run_if_due(root, now=NOW)
    # The wrapper saw a final report. The first fake GitHub probe replaces it
    # before collect reaches the local-file reader: the real read must defer.
    assert not refresh.run_if_due(root, now=NOW + timedelta(minutes=1))
    assert changed and github.calls
    assert service.database.latest_governance_vulnerability_report() is None
    assert service.database.list_operational_incidents() == [] and push.notifications == []
    assert "fail" not in health

    finalized_at = NOW + timedelta(minutes=1, seconds=1)
    _write_layer_report(root / AUTOMATION_REPORT, {
        "schema": "C3PO_SECURITY_AUTOMATION-v1", "generated_at": finalized_at.isoformat(),
        "status": "verified", "healthy": True, "errors": [], "alerts": [],
    })
    assert not refresh.run_if_due(root, now=finalized_at)
    # A provisional read is neither success nor failure: the reconciled report
    # must be accepted after one minute rather than the 30-minute error backoff.
    assert refresh.run_if_due(root, now=finalized_at + timedelta(minutes=1))
    report = service.database.latest_governance_vulnerability_report()
    assert report is not None and report["status"] == "healthy"
    assert service.database.list_operational_incidents() == [] and push.notifications == []


@pytest.mark.parametrize("layer", ["dependabot", "governance", "operating_system", "production_images", "remediation_lanes"])
def test_real_layer_issue_is_signalled_while_routine_is_preliminary(tmp_path: Path, layer: str) -> None:
    root = _root(tmp_path, NOW)
    github = _GitHub(alerts=[_alert("critical", 1)] if layer == "dependabot" else None,
                     enforce_admins=layer != "governance", lanes=[_lane(1)] if layer == "remediation_lanes" else None)
    if layer in {"operating_system", "production_images"}:
        path = root / (HOST_OS_REPORT_RELATIVE_PATH if layer == "operating_system" else CONTAINER_REPORT_RELATIVE_PATH)
        data = json.loads(path.read_text())
        if layer == "operating_system":
            data["updates"]["security_pending"] = 1
        else:
            data["by_severity"]["critical"] = 1
        _write_layer_report(path, data)
    service = _service(tmp_path, github)
    service.operational_incidents = OperationalIncidentService(service.database)
    push = _Push()
    service.push_notifications = push  # type: ignore[assignment]
    refresh = GovernanceRefresh(service)
    preliminary_at = NOW + timedelta(minutes=1)
    changed = False

    def during_collection(url: str, **kwargs: Any):
        nonlocal changed
        if not changed:
            changed = True
            # These values are provisional and must not even be parsed. The
            # governance case remains well-formed to exercise its 10-minute
            # maturity follow-up with an unchanged routine fingerprint.
            provisional = {"schema": "C3PO_SECURITY_AUTOMATION-v1", "generated_at": preliminary_at.isoformat(),
                           "status": "observed", "healthy": False,
                           "errors": [] if layer == "governance" else "provisional",
                           "pending": [] if layer == "governance" else {"provisional": True},
                           "alerts": [] if layer == "governance" else [None]}
            _write_layer_report(root / AUTOMATION_REPORT, provisional)
        return github.get(url, **kwargs)

    service.external_get = during_collection
    assert not refresh.run_if_due(root, now=NOW)
    assert refresh.run_if_due(root, now=preliminary_at)
    report = service.database.latest_governance_vulnerability_report()
    assert report is not None and report["status"] != "healthy"
    automation = report["security_automation"]
    assert automation["observation_pending"] is True and automation["status"] == "attention"
    assert automation["npm_evidence_attested"] is False
    assert set(automation) == {"schema", "available", "status", "detail", "generated_at", "report_sha256", "observation_pending", "npm_evidence_attested"}
    assert report["post_deploy_grace"]["active"] is False
    incidents = service.database.list_operational_incidents()
    assert len(incidents) == 1 and incidents[0]["source"] == "governance"
    assert any(cause["component"] == layer for cause in incidents[0]["evidence"]["causes"])
    assert not any(cause["component"] == "security_automation" for cause in incidents[0]["evidence"]["causes"])
    assert not any(item.get("category") == "job_failure" for item in push.notifications)
    if layer in {"dependabot", "governance", "production_images"}:
        assert any(item.get("category") == "governance_critical" for item in push.notifications)
    if layer == "remediation_lanes":
        assert any(item.get("category") == "remediation_lane_opened" for item in push.notifications)
    if layer == "governance":
        calls = len(github.calls)
        assert not refresh.run_if_due(root, now=preliminary_at + timedelta(seconds=1))
        assert not refresh.run_if_due(root, now=preliminary_at + timedelta(minutes=9, seconds=59))
        assert len(github.calls) == calls
        assert refresh.run_if_due(root, now=preliminary_at + timedelta(minutes=10))
        mature = service.database.latest_governance_vulnerability_report()
        assert mature is not None and mature["security_automation"].get("observation_pending") is not True
