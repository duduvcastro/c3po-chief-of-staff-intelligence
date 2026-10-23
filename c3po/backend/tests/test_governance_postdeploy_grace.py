"""Bounded deploy waits: local files and in-memory ledger, never host or network."""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app.governance_vulnerability import (
    AUTOMATION_REPORT, CONTAINER_REPORT_RELATIVE_PATH, GOVERNANCE_INCIDENT_KEY,
    HOST_OS_REPORT_RELATIVE_PATH, POST_DEPLOY_ANCHORS, POST_DEPLOY_GRACE,
    POST_DEPLOY_ROUTINE_STATUSES, GovernanceVulnerabilityService,
    post_deploy_grace_detail, report_sha256,
)
from tests.test_governance_vulnerability import (
    _GitHub, _Push, _alert, _incident_service, _lane, _root, _write_layer_report,
)

NOW = datetime(2026, 10, 22, 13, 18, tzinfo=timezone.utc)
OLD, NEW = "a" * 40, "b" * 40


def _routine(root: Path, blockers: list[str] | None = None, **changes: Any) -> None:
    waits = ["image_scan_predates_deploy"] if blockers is None else blockers
    started = (NOW - timedelta(minutes=1)).isoformat()
    raw: dict[str, Any] = {
        "schema": "C3PO_SECURITY_AUTOMATION-v1", "generated_at": NOW.isoformat(),
        "status": "waiting_npm_evidence" if "npm_evidence_pending" in waits else "waiting_maintenance_window",
        "healthy": False, "errors": [], "alerts": [], "escalation_errors": [],
        "pending": ["npm_evidence_pending"] if "npm_evidence_pending" in waits else [],
        "healthy_blockers": waits, "deployed_sha": OLD if "deploy_lag" in waits else NEW,
        "main_sha": NEW, "deployed_at": started,
        **{key: started for key in POST_DEPLOY_ANCHORS.values()},
    }
    raw.update(changes)
    _write_layer_report(root / AUTOMATION_REPORT, raw)


def _collect(tmp_path: Path, **changes: Any) -> dict[str, Any]:
    root = _root(tmp_path, NOW)
    _routine(root, **changes)
    return _incident_service(tmp_path, _GitHub()).collect(root, measured_at=NOW)


def _incident(service: GovernanceVulnerabilityService) -> dict[str, Any] | None:
    return service.database.operational_incident_by_key(GOVERNANCE_INCIDENT_KEY)


def test_grace_is_pinned_to_npm_revision_window(monkeypatch: pytest.MonkeyPatch) -> None:
    path = Path(__file__).resolve().parents[3] / "scripts/c3po_security_daily.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("postdeploy_daily_contract", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert POST_DEPLOY_GRACE == module.NPM_REVISION_GRACE == timedelta(hours=3)


@pytest.mark.parametrize("blockers", [
    ["deploy_lag"], ["npm_evidence_pending"], ["image_scan_predates_deploy"],
    ["deploy_lag", "npm_evidence_pending"], ["deploy_lag", "image_scan_predates_deploy"],
    ["npm_evidence_pending", "image_scan_predates_deploy"], list(POST_DEPLOY_ANCHORS),
])
def test_22_october_waits_are_hashed_persisted_without_incident_push_or_escalation(
    tmp_path: Path, blockers: list[str],
) -> None:
    root = _root(tmp_path, NOW)
    _routine(root, blockers)
    service = _incident_service(tmp_path, _GitHub())
    push = _Push()
    service.push_notifications = push  # type: ignore[assignment]
    for at in (NOW, NOW + timedelta(minutes=1)):
        _, report = service.run_supervised(root, now=at)
        assert report["status"] == "attention" and report["post_deploy_grace"]["active"] is True
        assert report["report_sha256"] == report_sha256(report)
        assert service.database.latest_governance_vulnerability_report() == report
        assert _incident(service) is None
    assert push.notifications == [] and service.database.list_operational_incidents() == []


@pytest.mark.parametrize("routine_status", sorted(POST_DEPLOY_ROUTINE_STATUSES))
def test_declared_ordinary_routine_states_qualify(tmp_path: Path, routine_status: str) -> None:
    assert _collect(tmp_path, status=routine_status)["post_deploy_grace"]["active"] is True


@pytest.mark.parametrize("field", ["image_drift_since", "deployed_at"])
@pytest.mark.parametrize(("minutes", "active"), [(179, True), (180, False), (181, False)])
def test_anchor_and_deployment_expire_at_exactly_three_hours(
    tmp_path: Path, field: str, minutes: int, active: bool,
) -> None:
    root = _root(tmp_path, NOW)
    _routine(root, **{field: (NOW - timedelta(minutes=minutes)).isoformat()})
    service = _incident_service(tmp_path, _GitHub())
    _, report = service.run_supervised(root, now=NOW)
    assert report["post_deploy_grace"]["active"] is active
    current = _incident(service)
    if active:
        assert current is None
    else:
        assert current is not None and current["status"] == "open"
        assert "scan pós-deploy das imagens pendente desde" in current["detail"]
        assert report["post_deploy_grace"]["reason"] == "expired"
        assert current["evidence"]["post_deploy_grace"] == report["post_deploy_grace"]
        assert current["evidence"]["escalation"]["escalated"] is False


@pytest.mark.parametrize("field", [*POST_DEPLOY_ANCHORS.values(), "deployed_at"])
@pytest.mark.parametrize("bad", [None, 3, {}, [], "", "bad", "2026-10-22T13:18:00", "2026-10-22T13:23:01+00:00"])
def test_required_anchors_missing_naive_malformed_or_future_never_grace(
    tmp_path: Path, field: str, bad: Any,
) -> None:
    blocker = next((k for k, v in POST_DEPLOY_ANCHORS.items() if v == field), "image_scan_predates_deploy")
    report = _collect(tmp_path, blockers=[blocker], **{field: bad})
    assert report["post_deploy_grace"]["active"] is False
    if not isinstance(bad, str):
        assert report["security_automation"][field] is None


def test_clock_skew_tolerance_includes_five_minutes(tmp_path: Path) -> None:
    future = (NOW + timedelta(minutes=5)).isoformat()
    assert _collect(tmp_path, image_drift_since=future, deployed_at=future)["post_deploy_grace"]["active"] is True


@pytest.mark.parametrize("bad", [None, 7, {}, "image_scan_predates_deploy", [], ["image_scan_predates_deploy"] * 2, [7], ["unhealthy_host"]])
def test_missing_wrong_duplicate_or_real_blockers_never_grace(tmp_path: Path, bad: Any) -> None:
    assert _collect(tmp_path, healthy_blockers=bad)["post_deploy_grace"]["active"] is False


@pytest.mark.parametrize("fields", [
    {"pending": ["npm_evidence_pending"]}, {"pending": "npm_evidence_pending"},
    {"pending": ["other"]}, {"pending": [3]}, {"errors": ["failure"]}, {"errors": None},
    {"errors": "bad"}, {"escalation_errors": ["post_failed"]}, {"escalation_errors": "bad"},
    {"status": "maintenance_hold"}, {"status": "observed"}, {"status": "failed"},
    {"status": "blocked_scan_dispatch"}, {"status": "waiting_security_tests"},
    {"status": None}, {"status": {}}, {"status": []},
    {"deployed_sha": None}, {"main_sha": 3}, {"main_sha": "not-a-revision"}, {"deployed_sha": OLD},
])
def test_unexpected_pending_errors_status_or_revision_never_grace(tmp_path: Path, fields: dict[str, Any]) -> None:
    assert _collect(tmp_path, **fields)["post_deploy_grace"]["active"] is False


def test_deploy_lag_requires_distinct_revisions_but_not_a_recent_old_deploy(tmp_path: Path) -> None:
    assert _collect(tmp_path / "old", blockers=["deploy_lag"], deployed_at="2020-01-01T00:00:00+00:00")["post_deploy_grace"]["active"] is True
    assert _collect(tmp_path / "no_lag", blockers=["deploy_lag"], deployed_sha=NEW)["post_deploy_grace"]["active"] is False


@pytest.mark.parametrize("field", ["pending", "escalation_errors"])
@pytest.mark.parametrize("missing", [False, True])
def test_none_or_missing_raw_lists_cannot_be_normalized_into_grace(
    tmp_path: Path, field: str, missing: bool,
) -> None:
    root = _root(tmp_path, NOW)
    _routine(root)
    path = root / AUTOMATION_REPORT
    raw = json.loads(path.read_text())
    if missing:
        raw.pop(field)
    else:
        raw[field] = None
    _write_layer_report(path, raw)
    service = _incident_service(tmp_path, _GitHub())
    _, report = service.run_supervised(root, now=NOW)
    assert report["status"] == "attention"  # Preserve the legacy status rules.
    assert report["security_automation"]["healthy_blockers"] is None
    assert report["post_deploy_grace"]["active"] is False
    assert _incident(service) is not None


@pytest.mark.parametrize("cause", ["dependabot", "governance", "os_update", "reboot", "image_finding", "image_unavailable", "lane", "routine_error", "escalation", "npm", "host"])
def test_real_causes_alongside_waits_open_immediately(tmp_path: Path, cause: str) -> None:
    root = _root(tmp_path, NOW)
    _routine(root, list(POST_DEPLOY_ANCHORS))
    github = _GitHub()
    if cause == "dependabot":
        github = _GitHub([_alert("medium", 1)])
    elif cause == "governance":
        github = _GitHub(enforce_admins=False)
    elif cause == "lane":
        github = _GitHub(lanes=[_lane(901)])
    elif cause in ("os_update", "reboot", "image_finding", "image_unavailable"):
        relative = HOST_OS_REPORT_RELATIVE_PATH if cause in ("os_update", "reboot") else CONTAINER_REPORT_RELATIVE_PATH
        path = root / relative
        raw = json.loads(path.read_text())
        if cause == "os_update":
            raw["updates"]["security_pending"] = 1
        elif cause == "reboot":
            raw["reboot_required"] = True
        elif cause == "image_finding":
            raw["by_severity"]["medium"] = 1
        else:
            raw["scan_status"] = "unavailable"
        _write_layer_report(path, raw)
    elif cause == "routine_error":
        _routine(root, list(POST_DEPLOY_ANCHORS), errors=["scan_dispatch:HTTPError:403"])
    elif cause == "escalation":
        _routine(root, list(POST_DEPLOY_ANCHORS), escalation_errors=["post_failed"])
    elif cause == "npm":
        _routine(root, list(POST_DEPLOY_ANCHORS), alerts=[{"number": "npm:1", "severity": "low", "fixed": False}])
    elif cause == "host":
        _routine(root, [*POST_DEPLOY_ANCHORS, "unhealthy_host"])
    service = _incident_service(tmp_path, github)
    _, report = service.run_supervised(root, now=NOW)
    assert report["post_deploy_grace"]["active"] is False
    current = _incident(service)
    assert current is not None and current["status"] == "open"


def test_chained_deploys_cannot_extend_first_observation(tmp_path: Path) -> None:
    root = _root(tmp_path, NOW)
    first = NOW - timedelta(hours=3, minutes=1)
    _routine(root, list(POST_DEPLOY_ANCHORS), deploy_lag_since=first.isoformat(),
             deployed_at=NOW.isoformat(), deployed_sha="c" * 40, main_sha="d" * 40)
    service = _incident_service(tmp_path, _GitHub())
    _, report = service.run_supervised(root, now=NOW)
    assert report["post_deploy_grace"]["reason"] == "expired"
    assert report["post_deploy_grace"]["until"] == (first + POST_DEPLOY_GRACE).isoformat()
    assert _incident(service) is not None


@pytest.mark.parametrize("acknowledged", [False, True])
def test_existing_episode_is_never_hidden_resolved_or_lowered(tmp_path: Path, acknowledged: bool) -> None:
    root = _root(tmp_path, NOW)
    _routine(root)
    service = _incident_service(tmp_path, _GitHub())
    incidents = service.operational_incidents
    assert incidents is not None
    incidents.signal(incident_key=GOVERNANCE_INCIDENT_KEY, source="governance", severity="critical",
        title="Existing", detail="Existing", deep_link="/?view=health", evidence={}, at=NOW - timedelta(hours=25))
    current = _incident(service)
    assert current is not None
    if acknowledged:
        service.database.transition_operational_incident(incident_id=current["id"], event_type="acknowledged",
            actor_email="owner@example.invalid", detail="ack", at=NOW - timedelta(hours=24))
    service.run_supervised(root, now=NOW)
    current = _incident(service)
    assert current is not None and current["status"] == ("acknowledged" if acknowledged else "open")
    assert current["severity"] == "critical" and current["evidence"]["post_deploy_grace"]["active"] is True
    assert current["evidence"]["escalation"]["escalated"] is True and "ESCALADO" in current["detail"]


def test_old_routine_keeps_previous_behavior(tmp_path: Path) -> None:
    root = _root(tmp_path, NOW)
    _routine(root)
    path = root / AUTOMATION_REPORT
    raw = json.loads(path.read_text())
    for key in ["healthy_blockers", *POST_DEPLOY_ANCHORS.values(), "deployed_at", "deployed_sha", "main_sha"]:
        raw.pop(key, None)
    _write_layer_report(path, raw)
    service = _incident_service(tmp_path, _GitHub())
    _, report = service.run_supervised(root, now=NOW)
    assert report["post_deploy_grace"]["active"] is False and _incident(service) is not None


def test_card_labels_deployed_revision_not_main_still_waiting(tmp_path: Path) -> None:
    grace = _collect(tmp_path, blockers=["deploy_lag", "npm_evidence_pending"])["post_deploy_grace"]
    assert post_deploy_grace_detail(grace, NOW) == "Pós-deploy aaaaaaa: aguardando deploy e auditoria npm até 13:17 BRT"
    assert post_deploy_grace_detail(grace, datetime.fromisoformat(grace["until"])) is None
    assert post_deploy_grace_detail({**grace, "until": "bad"}, NOW) is None


def test_force_bypasses_success_gates_but_preserves_failure_backoff(tmp_path: Path) -> None:
    at = NOW.replace(hour=4)
    root = _root(tmp_path, at)
    service = _incident_service(tmp_path, _GitHub())
    assert service.run_daily_if_due(root, at) is False
    assert service.run_daily_if_due(root, at, force=True) is True
    assert service.run_daily_if_due(root, at + timedelta(minutes=1)) is False
    assert service.run_daily_if_due(root, at + timedelta(minutes=1), force=True) is True
    original = service.collect
    def failure(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("synthetic read failure")
    service.collect = failure  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="synthetic"):
        service.run_daily_if_due(root, at + timedelta(minutes=2), force=True)
    service.collect = original  # type: ignore[method-assign]
    assert service.run_daily_if_due(root, at + timedelta(minutes=3), force=True) is False
    assert service.run_daily_if_due(root, at + timedelta(minutes=32), force=True) is True
