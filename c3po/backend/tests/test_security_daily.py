from __future__ import annotations

import importlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
deps = importlib.import_module("c3po_dependency_security")
daily = importlib.import_module("c3po_security_daily")


def files():
    return {"c3po/frontend/package.json": '{"dependencies":{"next":"15.5.22"},"scripts":{"build":"next build"}}\n',
            "c3po/frontend/pnpm-workspace.yaml": "packages:\n  - .\noverrides:\n  sharp: 0.35.0\nallowBuilds:\n  sharp: true\n",
            "c3po/frontend/pnpm-lock.yaml": "lockfileVersion: '9.0'\n",
            "c3po/backend/requirements.txt": "httpx>=0.28,<1\ncryptography>=50,<51\n"}


def alert(**changes):
    return {"number": 44, "advisory": "GHSA-rgj7-g3m4-5g8c", "severity": "high",
            "ecosystem": "npm", "package": "sharp", "manifest": "c3po/frontend/pnpm-lock.yaml",
            "fixed": "0.35.4", **changes}


def test_sharp_fix_changes_override_preserves_scripts_and_no_other_manifests():
    base = files()
    output, applied, blocked = deps.prepare(base, [alert()])
    assert applied == [alert()] and blocked == []
    assert output["c3po/frontend/pnpm-workspace.yaml"] == base["c3po/frontend/pnpm-workspace.yaml"].replace("0.35.0", "0.35.4")
    assert output["c3po/frontend/package.json"] == base["c3po/frontend/package.json"]


@pytest.mark.parametrize("fixed", [None, "1.0.0", "0.36.0", "0.35.4-beta", "$(cat secret)"])
def test_unavailable_or_incompatible_fix_never_mutates(fixed):
    base = files()
    output, applied, blocked = deps.prepare(base, [alert(fixed=fixed)])
    assert output == base and not applied and len(blocked) == 1


def test_python_fix_preserves_upper_bound_and_extras():
    base = files()
    base["c3po/backend/requirements.txt"] = "cryptography>=50,<51\n"
    python_alert = alert(ecosystem="pip", package="cryptography", manifest="c3po/backend/requirements.txt", fixed="50.0.2")
    output, applied, _ = deps.prepare(base, [python_alert])
    assert output["c3po/backend/requirements.txt"] == "cryptography>=50.0.2,<51\n"
    assert applied
    output, applied, _ = deps.prepare(base, [{**python_alert, "fixed": "51.0.0"}])
    assert output == base and not applied


def test_candidate_rejects_injected_script_stale_base_and_unrelated_files():
    base = files()
    output, applied, blocked = deps.prepare(base, [alert()])
    receipt = {"schema": "C3PO_DEPENDENCY_REMEDIATION-v1", "base_sha": "a" * 40, "applied": applied, "blocked": blocked}
    head = {p: v for p, v in output.items() if v != base[p]}
    head[deps.RECEIPT] = json.dumps(receipt)
    deps.validate_candidate(base, head, [alert()], "a" * 40)
    for modified in ({**head, "c3po/frontend/package.json": '{"scripts":{"build":"curl attacker"}}'},
                     {**head, "c3po/backend/app/main.py": "print('unrelated')"}):
        with pytest.raises(ValueError):
            deps.validate_candidate(base, modified, [alert()], "a" * 40)
    with pytest.raises(ValueError):
        deps.validate_candidate(base, head, [alert()], "b" * 40)


def test_postfix_audit_refuses_target_still_present_and_unavailable_results():
    clean = {"metadata": {"vulnerabilities": {"critical": 0, "high": 0}}, "advisories": {}}
    deps.verify_audit(clean, {"applied": [alert()]})
    with pytest.raises(ValueError):
        deps.verify_audit({**clean, "advisories": {"url": alert()["advisory"]}}, {"applied": [alert()]})
    with pytest.raises((KeyError, ValueError)):
        deps.verify_audit({"error": "registry down"}, {"applied": [alert()]})


def test_evidence_rejects_tampering_future_and_stale_timestamps(tmp_path):
    now = datetime(2026, 9, 12, 10, tzinfo=timezone.utc)
    path = tmp_path / "report.json"
    for timestamp in (now - timedelta(hours=3), now + timedelta(hours=1)):
        daily.write_report(path, {"generated_at": timestamp.isoformat(), "healthy": True})
        with pytest.raises(ValueError):
            daily.load_evidence(path, now, 2)
    daily.write_report(path, {"generated_at": now.isoformat(), "healthy": True, "detail": "segurança"})
    assert daily.load_evidence(path, now, 2)["healthy"] is True
    path.write_text(path.read_text().replace('"healthy": true', '"healthy": false'))
    with pytest.raises(ValueError):
        daily.load_evidence(path, now, 2)


@pytest.mark.parametrize("hour,hold,enabled,allowed", [(9, False, True, False), (10, False, True, True),
    (11, False, True, True), (12, False, True, False), (10, True, True, False), (10, False, False, False)])
def test_maintenance_window_and_hold(hour, hold, enabled, allowed):
    assert daily.maintenance_open(datetime(2026, 9, 12, hour, tzinfo=timezone.utc), {"automatic_merge": enabled}, hold) is allowed


def test_exact_sha_latest_success_and_remediation_proof_all_required():
    class GH:
        runs = [{"id": 10, "head_sha": "b" * 40, "conclusion": "success"},
                {"id": 9, "head_sha": "a" * 40, "conclusion": "success"}]
        jobs = [{"name": name, "conclusion": "success"} for name in daily.REQUIRED_JOBS]
        def pages(self, path, key):
            return self.jobs if key == "jobs" else self.runs
    gh = GH()
    pr = {"head": {"sha": "a" * 40, "ref": "automation/dependency-security-daily"}}
    assert daily.proof_passed(gh, pr)
    gh.jobs = [job for job in gh.jobs if job["name"] != "Security remediation proof"]
    assert not daily.proof_passed(gh, pr)
    gh.jobs = [{"name": name, "conclusion": "success"} for name in daily.REQUIRED_JOBS]
    gh.runs.append({"id": 11, "head_sha": "a" * 40, "conclusion": "failure"})
    assert not daily.proof_passed(gh, pr)


def test_stale_reports_still_dispatch_recovery_and_do_not_merge(tmp_path, monkeypatch):
    (tmp_path / "runtime/security").mkdir(parents=True)
    (tmp_path / ".deploy-version").write_text("a" * 40)
    monkeypatch.setattr(daily, "HOLD", tmp_path / "hold")
    monkeypatch.setattr(daily, "promote", lambda *args: pytest.fail("must not merge without evidence"))
    monkeypatch.setattr(daily, "boot_receipt", lambda *args, **kwargs: None)
    probes = []
    monkeypatch.setattr(daily, "healthy_host", lambda _: probes.append(1) or True)
    class GH:
        calls = []
        def pages(self, path):
            return []
        def request(self, path, method="GET", body=None):
            if path == "/git/ref/heads/main":
                return {"object": {"sha": "a" * 40}}
            if method == "GET" and path.startswith("/actions/workflows/"):
                return {"workflow_runs": []}
            self.calls.append(path)
    gh = GH()
    report = daily.cycle(tmp_path, gh, datetime(2026, 9, 12, 10, tzinfo=timezone.utc), {"automatic_merge": True}, {})
    assert len(gh.calls) == 2
    assert report["status"] == "blocked_missing_evidence" and report["healthy"] is False
    assert set(report["errors"]) == {"host_evidence_unavailable", "image_evidence_unavailable",
                                      "npm_evidence_unavailable", "watchdog_evidence_unavailable"}
    assert report["healthy_blockers"] == ["errors", "os_security_pending", "reboot_required",
                                          "image_findings_or_unavailable"]
    assert probes == [1]
    daily.cycle(tmp_path, gh, datetime(2026, 9, 12, 11, tzinfo=timezone.utc), {"automatic_merge": True}, report)
    assert len(gh.calls) == 2


@pytest.mark.parametrize("condition", ["ready", "stale_host", "hold", "no_reboot"])
def test_dispatch_403_does_not_skip_independent_reboot_or_claim_success(tmp_path, monkeypatch, condition):
    from urllib.error import HTTPError

    now = datetime(2026, 9, 12, 10, tzinfo=timezone.utc)
    (tmp_path / "runtime/security").mkdir(parents=True)
    (tmp_path / ".deploy-version").write_text("a" * 40)
    hold = tmp_path / "hold"
    if condition == "hold":
        hold.touch()
    monkeypatch.setattr(daily, "HOLD", hold)
    monkeypatch.setattr(daily, "MARKER", tmp_path / "marker")
    monkeypatch.setattr(daily, "trial_present", lambda _: False)
    monkeypatch.setattr(daily, "healthy_host", lambda _: True)
    # Isolate scheduling from the separately tested evidence parsers and host
    # reboot implementation. No subprocess, provider or real reboot is invoked.
    monkeypatch.setattr(daily, "boot_receipt", lambda *args, **kwargs: None)
    monkeypatch.setattr(daily, "validate_report", lambda _: None)
    def evidence(path, *args):
        if path.name == "host-os-vulnerability-report.json":
            if condition == "stale_host":
                raise ValueError("stale")
            return {"schema": "C3PO_HOST_OS_VULNERABILITY_REPORT-v1", "updates": {"security_pending": 0},
                    "reboot_required": condition != "no_reboot", "report_sha256": "0" * 64}
        if path.name == "repository-npm-advisories.json":
            return {"schema": "C3PO_NPM_ADVISORIES-v1", "source_revision": "a" * 40, "alerts": []}
        if path.name == "security-watchdog-report.json":
            return {"schema": "C3PO_SECURITY_WATCHDOG-v1", "errors": [], "status": "verified",
                    "generated_at": now.isoformat()}
        return {"report_sha256": "1" * 64, "scan_status": "complete", "errors": [], "finding_total": 0,
                "generated_at": now.isoformat()}
    monkeypatch.setattr(daily, "load_evidence", evidence)
    requests = []
    def reboot(*args, **kwargs):
        requests.append("reboot")
        return "requested"
    monkeypatch.setattr(daily, "request_reboot", reboot)
    monkeypatch.setattr(daily, "promote", lambda *args, **kwargs: pytest.fail("failed dispatch must veto promotion"))
    class GH:
        def pages(self, path):
            return []
        def request(self, path, method="GET", body=None):
            if method == "POST":
                raise HTTPError("https://api.github.com/private", 403, "sensitive response", {}, None)
            if path == "/git/ref/heads/main":
                return {"object": {"sha": "a" * 40}}
            return {"workflow_runs": []}
    report = daily.cycle(tmp_path, GH(), now, {"automatic_merge": True, "automatic_reboot": True}, {})
    assert requests == (["reboot"] if condition == "ready" else [])
    assert "scan_dispatch:HTTPError:403" in report["errors"]
    assert report["healthy"] is False
    assert report["last_dispatch_date"] is None
    assert report["last_dispatched_deploy"] is None
    assert report["last_dispatched_main"] is None
    assert report["pending"] == []
    assert "sensitive response" not in json.dumps(report)
    if condition == "ready":
        assert report["status"] == "reboot_requested"
    if condition == "no_reboot":
        assert report["status"] == "blocked_scan_dispatch"


def test_registry_finds_advisories_before_dependabot_and_deduplicates():
    audit = {"metadata": {"vulnerabilities": {"critical": 1}}, "advisories": {"1": {
        "module_name": "next", "github_advisory_id": "GHSA-2xp9-vwfh-vxw4", "severity": "critical",
        "patched_versions": ">=15.5.24"}}}
    npm = deps.npm_alerts(audit)
    assert npm[0]["fixed"] == "15.5.24"
    merged = deps.merge_alerts([], npm)
    output, applied, blocked = deps.prepare(files(), merged)
    assert json.loads(output["c3po/frontend/package.json"])["dependencies"]["next"] == "15.5.24"
    assert len(applied) == 1 and not blocked
    second = {**npm[0], "advisory": "GHSA-p293-qw3h-jr36", "number": "npm:GHSA-p293-qw3h-jr36"}
    _, applied, blocked = deps.prepare(files(), [*merged, second])
    assert len(applied) == 2 and not blocked
    gh = {**npm[0], "number": 45}
    assert deps.merge_alerts([gh], npm) == [gh]
    with pytest.raises(ValueError):
        deps.npm_alerts({"error": "registry timeout"})


def test_promotion_rechecks_hold_and_never_promotes_without_all_checks(tmp_path, monkeypatch):
    base = files()
    output, applied, blocked = deps.prepare(base, [alert()])
    head = {p: v for p, v in output.items() if base[p] != v}
    head[deps.RECEIPT] = json.dumps({"schema": "C3PO_DEPENDENCY_REMEDIATION-v1", "base_sha": "a" * 40,
                                   "applied": applied, "blocked": blocked})
    class GH:
        merged = []
        def request(self, path, method="GET", body=None):
            if path == "/git/ref/heads/main":
                return {"object": {"sha": "a" * 40}}
            if path == "/branches/main/protection":
                return {"enforce_admins": {"enabled": True}, "required_status_checks": {
                    "strict": True, "contexts": list(daily.REQUIRED_JOBS - {"Security remediation proof"})}}
            if path == "/pulls/1":
                return {"head": {"sha": "b" * 40}, "mergeable_state": "clean"}
            if path.endswith("/merge"):
                self.merged.append(body)
                return {"merged": True}
            raise AssertionError(path)
        def pages(self, path, key=None):
            if path.startswith("/actions/"):
                return []
            if path == "/pulls?state=open&base=main":
                return [{"number": 1, "draft": False, "user": {"login": "github-actions[bot]"},
                         "head": {"sha": "b" * 40, "ref": "automation/dependency-security-daily", "repo": {"full_name": daily.REPO}}}]
            if path == "/pulls/1/files":
                return [{"filename": p, "status": "added" if p == deps.RECEIPT else "modified"} for p in head]
            raise AssertionError(path)
        def file(self, path, sha):
            return base[path] if sha == "a" * 40 else head[path]
    gh = GH()
    monkeypatch.setattr(daily, "proof_passed", lambda *_: True)
    status, _ = daily.promote(gh, [alert()], "a" * 40, {}, may_write=lambda: False)
    assert status == "baseline_changed_or_hold" and not gh.merged
    monkeypatch.setattr(daily, "proof_passed", lambda *_: False)
    assert daily.promote(gh, [alert()], "a" * 40, {}, may_write=lambda: True)[0] == "waiting_security_tests"
    assert not gh.merged
    monkeypatch.setattr(daily, "proof_passed", lambda *_: True)
    assert daily.promote(gh, [alert()], "a" * 40, {}, may_write=lambda: True)[0] == "merged_waiting_deploy_and_rescan"
    assert gh.merged == [{"sha": "b" * 40, "merge_method": "squash"}]


@pytest.mark.parametrize('prefix', ['/repos/' + daily.REPO, '/repositories/' + str(daily.REPO_ID)])
def test_dependabot_uses_cursor_links_and_keeps_short_intermediate_page(prefix):
    gh = daily.GitHub('test-token')
    calls = []
    def read(path, *, with_links=False):
        calls.append(path)
        assert with_links and 'page=' not in path.replace('per_page=', '')
        if len(calls) == 1:
            return [{'number': 1}], '<https://api.github.com' + prefix + '/dependabot/alerts?state=open&per_page=100&after=cursor>; rel="next"'
        return [{'number': 2}], ''
    gh.request = read
    assert gh.pages('/dependabot/alerts?state=open') == [{'number': 1}, {'number': 2}]
    assert 'after=cursor' in calls[1]


@pytest.mark.parametrize('url', ['https://example.com/steal', 'http://api.github.com/repos/' + daily.REPO + '/dependabot/alerts', 'https://api.github.com/repos/other/repo/dependabot/alerts'])
def test_pagination_never_sends_credential_to_other_target(url):
    gh = daily.GitHub('test-token')
    gh.request = lambda *a, **k: ([{'number': 1}], '<' + url + '>; rel="next"')
    with pytest.raises(ValueError, match='pagination target'):
        gh.pages('/dependabot/alerts?state=open')



def _maintenance_ready(tmp_path, monkeypatch, now, *, watchdog_errors=()):
    """A cycle where every security gate is green, so only the escalation channel varies."""
    (tmp_path / "runtime/security").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".deploy-version").write_text("a" * 40)
    monkeypatch.setattr(daily, "HOLD", tmp_path / "hold")
    monkeypatch.setattr(daily, "MARKER", tmp_path / "marker")
    monkeypatch.setattr(daily, "trial_present", lambda _: False)
    monkeypatch.setattr(daily, "healthy_host", lambda _: True)
    monkeypatch.setattr(daily, "boot_receipt", lambda *args, **kwargs: None)
    monkeypatch.setattr(daily, "validate_report", lambda _: None)
    def evidence(path, *args):
        if path.name == "host-os-vulnerability-report.json":
            return {"schema": "C3PO_HOST_OS_VULNERABILITY_REPORT-v1", "updates": {"security_pending": 0},
                    "reboot_required": False, "report_sha256": "0" * 64}
        if path.name == "repository-npm-advisories.json":
            return {"schema": "C3PO_NPM_ADVISORIES-v1", "source_revision": "a" * 40, "alerts": []}
        if path.name == "security-watchdog-report.json":
            if watchdog_errors:
                raise ValueError("Watchdog failed")
            return {"schema": "C3PO_SECURITY_WATCHDOG-v1", "errors": [], "status": "verified",
                    "generated_at": now.isoformat()}
        return {"report_sha256": "1" * 64, "scan_status": "complete", "errors": [], "finding_total": 0,
                "generated_at": now.isoformat()}
    monkeypatch.setattr(daily, "load_evidence", evidence)
    promoted = []
    monkeypatch.setattr(daily, "promote",
                        lambda *args, **kwargs: promoted.append(1) or ("no_validated_candidate", None))
    return promoted


class _EscalationGH:
    def __init__(self, *, state="active", runs=(), error=None, main="a" * 40, dispatch_error=None,
                 workflow_runs=None):
        self.state, self.runs, self.error = state, list(runs), error
        self.main, self.dispatch_error = main, dispatch_error
        self.workflow_runs = workflow_runs or {}
        self.writes = []
    def pages(self, path):
        return []
    def request(self, path, method="GET", body=None):
        if method != "GET":
            if self.dispatch_error is not None:
                raise self.dispatch_error
            self.writes.append((method, path))
            return None
        if path == "/git/ref/heads/main":
            return {"object": {"sha": self.main}}
        if path.startswith("/actions/workflows/incident-escalation.yml"):
            if self.error is not None:
                raise self.error
            if path == "/actions/workflows/incident-escalation.yml":
                return {"state": self.state}
            assert path.endswith("/runs?per_page=1&branch=main")
            return {"workflow_runs": self.runs}
        for workflow, runs in self.workflow_runs.items():
            if path.startswith(f"/actions/workflows/{workflow}/runs"):
                return {"workflow_runs": runs}
        return {"workflow_runs": []}


def test_failed_escalation_run_never_feeds_errors_nor_blocks_the_watchdog_chain(tmp_path, monkeypatch):
    watchdog = importlib.import_module("c3po_security_watchdog")
    now = datetime(2026, 9, 12, 10, tzinfo=timezone.utc)
    promoted = _maintenance_ready(tmp_path, monkeypatch, now)
    failed = [{"status": "completed", "conclusion": "failure"}]

    report = daily.cycle(tmp_path, _EscalationGH(runs=failed), now, {"automatic_merge": True}, {})
    baseline = daily.cycle(tmp_path, _EscalationGH(), now, {"automatic_merge": True}, {})

    assert report["errors"] == [] and baseline["errors"] == []
    assert report["escalation_errors"] == ["incident-escalation.yml:failure"]
    assert baseline["escalation_errors"] == []
    assert report["healthy"] == baseline["healthy"]
    assert report["status"] == "no_validated_candidate" and promoted == [1, 1]
    # Chain of 30/09 review: --verify-daily must still verify the day, so the
    # watchdog report stays clean and the next cycle keeps merge/reboot gates open.
    assert watchdog.daily_execution_verified(report, now) is True
    assert watchdog.daily_execution_verified({**report, "errors": ["x"]}, now) is False
    next_cycle = daily.cycle(tmp_path, _EscalationGH(runs=failed), now, {"automatic_merge": True}, report)
    assert next_cycle["status"] == "no_validated_candidate" and promoted == [1, 1, 1]


def test_watchdog_failure_still_blocks_so_the_chain_test_is_meaningful(tmp_path, monkeypatch):
    now = datetime(2026, 9, 12, 10, tzinfo=timezone.utc)
    promoted = _maintenance_ready(tmp_path, monkeypatch, now, watchdog_errors=["daily_security_execution_not_verified"])

    report = daily.cycle(tmp_path, _EscalationGH(), now, {"automatic_merge": True}, {})

    assert report["status"] == "blocked_missing_evidence" and promoted == []


@pytest.mark.parametrize(("gh", "expected", "writes"), [
    (lambda: _EscalationGH(error=HTTPError(
        "https://api.github.com/private?token=secret", 404, "secret body", {}, None)),
     ["incident-escalation.yml:HTTPError:404"], []),
    (lambda: _EscalationGH(error=URLError("secret host")),
     ["incident-escalation.yml:URLError"], []),
    (lambda: _EscalationGH(state="disabled_manually"), ["incident-escalation.yml:state:disabled_manually"], []),
    (lambda: _EscalationGH(state="disabled_inactivity"), [],
     [("PUT", "/actions/workflows/incident-escalation.yml/enable")]),
])
def test_escalation_channel_errors_are_recorded_without_crashing_the_cycle(tmp_path, monkeypatch, gh, expected, writes):
    now = datetime(2026, 9, 12, 10, tzinfo=timezone.utc)
    _maintenance_ready(tmp_path, monkeypatch, now)
    client = gh()

    report = daily.cycle(tmp_path, client, now, {"automatic_merge": True}, {})

    assert report["escalation_errors"] == expected
    assert report["errors"] == []
    assert report["status"] == "no_validated_candidate"
    assert [w for w in client.writes if "incident-escalation" in w[1]] == writes
    assert "secret" not in json.dumps(report)


DEPENDENCY_DISPATCH = ("POST", "/actions/workflows/dependency-security.yml/dispatches")
IMAGE_DISPATCH = ("POST", "/actions/workflows/container-vulnerability-scan.yml/dispatches")


def _audit(revision, **changes):
    return {"schema": "C3PO_NPM_ADVISORIES-v1", "source_revision": revision, "alerts": [], **changes}


def _npm(monkeypatch, audit):
    """Serve this npm audit; every other evidence layer stays as configured."""
    layers = daily.load_evidence
    def evidence(path, *args):
        if path.name == "repository-npm-advisories.json":
            return audit
        return layers(path, *args)
    monkeypatch.setattr(daily, "load_evidence", evidence)


def _deployed_before(tmp_path, now):
    # Image evidence generated at ``now`` postdates the deploy, so in these
    # cycles only the npm state can keep ``healthy`` False.
    stamp = (now - timedelta(hours=1)).timestamp()
    os.utime(tmp_path / ".deploy-version", (stamp, stamp))


def _scanned(tmp_path):
    """The current deploy has already had its post-deploy scans dispatched."""
    marker = tmp_path / ".deploy-version"
    return {"last_dispatched_deploy": marker.read_text().strip(),
            "last_dispatched_deploy_at": datetime.fromtimestamp(marker.stat().st_mtime, timezone.utc).isoformat()}


def test_new_main_npm_lag_is_pending_with_same_cycle_dispatch_even_before_10utc(tmp_path, monkeypatch):
    # 01/10/2026: every new main opened a CRITICAL incident until the next
    # dispatch, which after a night deploy only came at 10 UTC (7-8h later).
    night = datetime(2026, 9, 12, 4, 10, tzinfo=timezone.utc)
    promoted = _maintenance_ready(tmp_path, monkeypatch, night)
    _deployed_before(tmp_path, night)
    _npm(monkeypatch, _audit("b" * 40))
    previous = {"main_sha": "b" * 40, "npm_lag_since": None, "last_dispatched_main": "b" * 40,
                "last_dispatch_date": "2026-09-11", "last_dispatched_deploy": "b" * 40}
    gh = _EscalationGH()

    report = daily.cycle(tmp_path, gh, night, {"automatic_merge": True}, previous)

    assert gh.writes == [DEPENDENCY_DISPATCH, IMAGE_DISPATCH]
    assert report["errors"] == [] and report["pending"] == ["npm_evidence_pending"]
    assert report["status"] == "waiting_npm_evidence" and report["healthy"] is False
    assert report["last_dispatched_main"] == "a" * 40
    assert report["npm_lag_since"] == night.isoformat()
    # The new deploy is scanned now, without consuming the day's 10 UTC scan.
    assert report["last_dispatch_date"] == "2026-09-11" and report["last_dispatched_deploy"] == "a" * 40
    # The inventory published before the dispatch already carries the pending, never the error.
    published = json.loads((tmp_path / "runtime/security" / daily.REPORT).read_text())
    assert published["pending"] == ["npm_evidence_pending"] and published["errors"] == []
    assert promoted == []

    later = night + timedelta(hours=1)
    again = daily.cycle(tmp_path, gh, later, {"automatic_merge": True}, report)
    assert gh.writes == [DEPENDENCY_DISPATCH, IMAGE_DISPATCH]
    assert again["errors"] == [] and again["pending"] == ["npm_evidence_pending"]
    assert again["npm_lag_since"] == night.isoformat()

    _npm(monkeypatch, _audit("a" * 40))
    morning = night.replace(hour=10)
    ready = daily.cycle(tmp_path, gh, morning, {"automatic_merge": True}, again)
    assert gh.writes == [DEPENDENCY_DISPATCH, IMAGE_DISPATCH, DEPENDENCY_DISPATCH, IMAGE_DISPATCH]
    assert ready["errors"] == [] and ready["pending"] == [] and ready["healthy"] is True
    assert ready["npm_lag_since"] is None
    assert ready["last_dispatch_date"] == "2026-09-12" and promoted == [1]


@pytest.mark.parametrize(("elapsed", "pending"), [
    (timedelta(hours=2, minutes=59), True),
    (daily.NPM_REVISION_GRACE, False),
    (timedelta(hours=3, minutes=1), False),
], ids=["2h59", "3h00", "3h01"])
def test_npm_lag_grace_window_boundary(tmp_path, monkeypatch, elapsed, pending):
    now = datetime(2026, 9, 12, 4, 10, tzinfo=timezone.utc)
    _maintenance_ready(tmp_path, monkeypatch, now)
    _npm(monkeypatch, _audit("b" * 40))
    gh = _EscalationGH()
    first = daily.cycle(tmp_path, gh, now, {"automatic_merge": True},
                        {"main_sha": "b" * 40, "last_dispatched_main": "b" * 40, **_scanned(tmp_path)})
    assert first["pending"] == ["npm_evidence_pending"] and first["npm_lag_since"] == now.isoformat()

    report = daily.cycle(tmp_path, gh, now + elapsed, {"automatic_merge": True}, first)

    if pending:
        assert report["pending"] == ["npm_evidence_pending"] and report["errors"] == []
        assert report["status"] == "waiting_npm_evidence"
    else:
        assert report["pending"] == [] and report["errors"] == ["npm_evidence_unavailable"]
        assert report["status"] == "blocked_missing_evidence"
    assert report["healthy"] is False and report["npm_lag_since"] == now.isoformat()
    assert gh.writes == [DEPENDENCY_DISPATCH]


def test_chained_main_moves_never_restart_the_npm_lag_clock(tmp_path, monkeypatch):
    # A regeneration stuck queued/in progress is not a completed failure, so
    # only the clock from the first lag bounds it while main keeps moving.
    start = datetime(2026, 9, 12, 4, 10, tzinfo=timezone.utc)
    _maintenance_ready(tmp_path, monkeypatch, start)
    _npm(monkeypatch, _audit("b" * 40))
    report = {"main_sha": "b" * 40, "last_dispatched_main": "b" * 40, **_scanned(tmp_path)}
    writes = []
    for elapsed, main in ((timedelta(0), "a"), (timedelta(hours=1), "c"), (timedelta(hours=2), "d")):
        gh = _EscalationGH(main=main * 40, workflow_runs={
            "dependency-security.yml": [{"status": "queued", "conclusion": None}]})
        report = daily.cycle(tmp_path, gh, start + elapsed, {"automatic_merge": True}, report)
        writes += gh.writes
        assert report["pending"] == ["npm_evidence_pending"] and report["errors"] == []

    gh = _EscalationGH(main="e" * 40)
    report = daily.cycle(tmp_path, gh, start + timedelta(hours=3, minutes=1), {"automatic_merge": True}, report)
    writes += gh.writes

    assert report["pending"] == [] and report["errors"] == ["npm_evidence_unavailable"]
    assert report["npm_lag_since"] == start.isoformat()
    # Every new main is still re-dispatched; only the clock does not restart.
    assert writes == [DEPENDENCY_DISPATCH] * 4


@pytest.mark.parametrize("anchor", [
    lambda now: (now + timedelta(minutes=5)).isoformat(),
    lambda now: "not-a-time",
    lambda now: now.replace(tzinfo=None).isoformat(),
    lambda now: 1234,
    # Falsy but present: a corrupted anchor, never "absent" (would restart the clock).
    lambda now: "",
    lambda now: False,
    lambda now: 0,
    lambda now: [],
    lambda now: {},
], ids=["future", "garbage", "naive", "not_a_string",
        "empty_string", "false", "zero", "empty_list", "empty_dict"])
def test_future_or_malformed_npm_lag_anchor_fails_closed(tmp_path, monkeypatch, anchor):
    now = datetime(2026, 9, 12, 4, 10, tzinfo=timezone.utc)
    _maintenance_ready(tmp_path, monkeypatch, now)
    _npm(monkeypatch, _audit("b" * 40))
    gh = _EscalationGH()
    previous = {"main_sha": "b" * 40, "last_dispatched_main": "b" * 40, "npm_lag_since": anchor(now)}

    report = daily.cycle(tmp_path, gh, now, {"automatic_merge": True}, previous)

    assert report["pending"] == [] and report["errors"] == ["npm_evidence_unavailable"]
    assert report["status"] == "blocked_missing_evidence" and report["healthy"] is False
    # The corrupted anchor is kept, with its type, not silently reset.
    assert report["npm_lag_since"] == anchor(now) and type(report["npm_lag_since"]) is type(anchor(now))
    # Only an audit of the current main clears the anchor.
    _npm(monkeypatch, _audit("a" * 40))
    recovered = daily.cycle(tmp_path, gh, now + timedelta(hours=1), {"automatic_merge": True}, report)
    assert recovered["errors"] == [] and recovered["pending"] == []
    assert recovered["npm_lag_since"] is None


@pytest.mark.parametrize("state", [{}, {"npm_lag_since": None}], ids=["missing", "none"])
def test_missing_or_none_npm_lag_anchor_starts_the_clock(tmp_path, monkeypatch, state):
    now = datetime(2026, 9, 12, 4, 10, tzinfo=timezone.utc)
    _maintenance_ready(tmp_path, monkeypatch, now)
    _npm(monkeypatch, _audit("b" * 40))

    report = daily.cycle(tmp_path, _EscalationGH(), now, {"automatic_merge": True},
                         {"main_sha": "b" * 40, "last_dispatched_main": "b" * 40, **state})

    assert report["pending"] == ["npm_evidence_pending"] and report["errors"] == []
    assert report["npm_lag_since"] == now.isoformat() and report["healthy"] is False


@pytest.mark.parametrize("stored", ["", False, 0, [], {}, None],
                         ids=["empty_string", "false", "zero", "empty_list", "empty_dict", "none"])
def test_falsy_last_dispatched_main_is_never_a_dispatch_already_issued(tmp_path, monkeypatch, stored):
    now = datetime(2026, 9, 12, 4, 10, tzinfo=timezone.utc)
    _maintenance_ready(tmp_path, monkeypatch, now)
    _npm(monkeypatch, _audit("b" * 40))
    refused = _EscalationGH(dispatch_error=HTTPError("https://api.github.com/private", 403, "body", {}, None))
    previous = {"main_sha": "b" * 40, "last_dispatched_main": stored, **_scanned(tmp_path)}

    report = daily.cycle(tmp_path, refused, now, {"automatic_merge": True}, previous)
    assert report["pending"] == [] and "npm_evidence_unavailable" in report["errors"]

    gh = _EscalationGH()
    report = daily.cycle(tmp_path, gh, now, {"automatic_merge": True}, previous)
    assert gh.writes == [DEPENDENCY_DISPATCH] and report["last_dispatched_main"] == "a" * 40
    assert report["pending"] == ["npm_evidence_pending"]


def test_known_npm_findings_of_the_earlier_audit_stay_visible_while_pending(tmp_path, monkeypatch):
    now = datetime(2026, 9, 12, 4, 10, tzinfo=timezone.utc)
    _maintenance_ready(tmp_path, monkeypatch, now)
    for path, content in files().items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(content)
    high = deps.npm_alerts({"metadata": {"vulnerabilities": {"high": 1}}, "advisories": {"1": {
        "module_name": "next", "github_advisory_id": "GHSA-2xp9-vwfh-vxw4", "severity": "high",
        "patched_versions": ">=15.5.24"}}})
    _npm(monkeypatch, _audit("b" * 40, alerts=high))

    report = daily.cycle(tmp_path, _EscalationGH(), now, {"automatic_merge": True},
                         {"main_sha": "b" * 40, "last_dispatched_main": "b" * 40})

    assert report["pending"] == ["npm_evidence_pending"] and report["errors"] == []
    assert report["alerts"] == high and report["healthy"] is False


def test_failed_dependency_security_run_denies_the_npm_pending(tmp_path, monkeypatch):
    now = datetime(2026, 9, 12, 4, 10, tzinfo=timezone.utc)
    _maintenance_ready(tmp_path, monkeypatch, now)
    _npm(monkeypatch, _audit("b" * 40))
    gh = _EscalationGH(workflow_runs={
        "dependency-security.yml": [{"status": "completed", "conclusion": "failure"}]})

    report = daily.cycle(tmp_path, gh, now, {"automatic_merge": True},
                         {"main_sha": "b" * 40, "last_dispatched_main": "b" * 40, **_scanned(tmp_path)})

    assert report["pending"] == []
    assert report["errors"] == ["dependency-security.yml:failure", "npm_evidence_unavailable"]
    assert report["status"] == "blocked_missing_evidence" and report["healthy"] is False
    assert gh.writes == [DEPENDENCY_DISPATCH]


def test_main_moving_without_deploy_redispatches_dependency_security_only(tmp_path, monkeypatch):
    watchdog = importlib.import_module("c3po_security_watchdog")
    now = datetime(2026, 9, 12, 11, 10, tzinfo=timezone.utc)
    promoted = _maintenance_ready(tmp_path, monkeypatch, now)
    (tmp_path / ".deploy-version").write_text("b" * 40)
    _npm(monkeypatch, _audit("b" * 40))
    previous = {"main_sha": "b" * 40, "last_dispatched_main": "b" * 40,
                "last_dispatch_date": "2026-09-12", **_scanned(tmp_path)}
    gh = _EscalationGH()

    report = daily.cycle(tmp_path, gh, now, {"automatic_merge": True}, previous)

    assert gh.writes == [DEPENDENCY_DISPATCH]
    assert report["pending"] == ["npm_evidence_pending"] and report["errors"] == []
    # Gates stay as closed as with missing evidence: no promotion inside the window.
    assert report["status"] == "waiting_npm_evidence" and promoted == []
    # A pending wait is not a failed day for --verify-daily.
    assert watchdog.daily_execution_verified(report, now) is True


def test_npm_lag_without_a_dispatch_for_the_new_main_stays_an_error(tmp_path, monkeypatch):
    now = datetime(2026, 9, 12, 4, 10, tzinfo=timezone.utc)
    _maintenance_ready(tmp_path, monkeypatch, now)
    _npm(monkeypatch, _audit("b" * 40))
    gh = _EscalationGH(dispatch_error=HTTPError("https://api.github.com/private", 403, "secret body", {}, None))

    report = daily.cycle(tmp_path, gh, now, {"automatic_merge": True},
                         {"main_sha": "b" * 40, "last_dispatched_main": "b" * 40})

    assert report["pending"] == []
    assert report["errors"] == ["npm_evidence_unavailable", "scan_dispatch:HTTPError:403"]
    assert report["last_dispatched_main"] == "b" * 40
    assert "secret" not in json.dumps(report)


@pytest.mark.parametrize("audit", [
    _audit("b" * 40, schema="C3PO_NPM_ADVISORIES-v0"),
    _audit("not-a-revision"),
    _audit("b" * 40, alerts=None),
    {"schema": "C3PO_NPM_ADVISORIES-v1", "alerts": []},
])
def test_only_a_well_formed_audit_of_an_earlier_revision_can_be_pending(tmp_path, monkeypatch, audit):
    now = datetime(2026, 9, 12, 4, 10, tzinfo=timezone.utc)
    _maintenance_ready(tmp_path, monkeypatch, now)
    _npm(monkeypatch, audit)
    gh = _EscalationGH()

    report = daily.cycle(tmp_path, gh, now, {"automatic_merge": True},
                         {"main_sha": "b" * 40, "last_dispatched_main": "b" * 40, **_scanned(tmp_path)})

    assert report["pending"] == [] and report["errors"] == ["npm_evidence_unavailable"]
    assert gh.writes == [DEPENDENCY_DISPATCH]


def test_state_file_from_the_previous_version_dispatches_once(tmp_path, monkeypatch):
    now = datetime(2026, 9, 12, 11, 10, tzinfo=timezone.utc)
    _maintenance_ready(tmp_path, monkeypatch, now)
    _npm(monkeypatch, _audit("a" * 40))
    legacy = {"main_sha": "a" * 40, "last_dispatch_date": "2026-09-12", "last_dispatched_deploy": "a" * 40}
    gh = _EscalationGH()

    report = daily.cycle(tmp_path, gh, now, {"automatic_merge": True}, legacy)
    again = daily.cycle(tmp_path, gh, now + timedelta(hours=1), {"automatic_merge": True}, report)

    assert gh.writes == [DEPENDENCY_DISPATCH, IMAGE_DISPATCH]
    assert report["errors"] == [] and report["pending"] == []
    assert report["npm_lag_since"] is None and again["npm_lag_since"] is None
    assert again["last_dispatched_main"] == "a" * 40
    assert again["last_dispatched_deploy_at"] == report["deployed_at"]


def _clean_image(at):
    return {"scan_status": "complete", "errors": [], "finding_total": 0, "generated_at": at.isoformat()}


class _SecurityCycleWorld:
    """Mutable reports and deploy markers; every external operation is a double."""

    def __init__(self, tmp_path, monkeypatch, now):
        _maintenance_ready(tmp_path, monkeypatch, now)
        self.root = tmp_path
        self.main = self.npm_revision = "a" * 40
        self.npm_alerts = []
        self.os_pending = 0
        self.reboot_required = False
        self.image = _clean_image(now)
        self.host_ok = True
        self.probes = 0
        self.deploy("a" * 40, now - timedelta(hours=2))
        monkeypatch.setattr(daily, "load_evidence", self.evidence)
        monkeypatch.setattr(daily, "healthy_host", self.probe)
        monkeypatch.setattr(daily, "request_reboot", lambda *args, **kwargs: "deferred")

    def deploy(self, revision, at):
        marker = self.root / ".deploy-version"
        marker.write_text(revision + "\n")
        os.utime(marker, (at.timestamp(), at.timestamp()))

    def probe(self, _root):
        self.probes += 1
        if isinstance(self.host_ok, Exception):
            raise self.host_ok
        return self.host_ok

    def evidence(self, path, now, *args):
        if path.name == "host-os-vulnerability-report.json":
            return {"schema": "C3PO_HOST_OS_VULNERABILITY_REPORT-v1", "report_sha256": "0" * 64,
                    "updates": {"security_pending": self.os_pending}, "reboot_required": self.reboot_required}
        if path.name == "container-production-vulnerability-report.json":
            if self.image is None:
                raise ValueError("synthetic unavailable report")
            return {"report_sha256": "1" * 64, **self.image}
        if path.name == "repository-npm-advisories.json":
            return _audit(self.npm_revision, alerts=list(self.npm_alerts))
        return {"schema": "C3PO_SECURITY_WATCHDOG-v1", "errors": [], "status": "verified",
                "generated_at": now.isoformat()}

    def previous(self, **changes):
        return {"last_dispatched_main": self.main, **_scanned(self.root), **changes}

    def gh(self, **changes):
        return _EscalationGH(main=self.main, **changes)


def _previous_healthy(report, images, marker_mtime, host_ok):
    """The pre-change conjunction is an independent compatibility oracle."""
    return (report["deployed_sha"] == report["main_sha"] and not report["errors"] and not report["pending"]
            and not report["alerts"] and report["security_pending"] == 0
            and report["reboot_required"] is False and images.get("scan_status") == "complete"
            and images.get("errors") == [] and images.get("finding_total") == 0
            and datetime.fromisoformat(images["generated_at"]).timestamp() >= marker_mtime and host_ok)


@pytest.mark.parametrize("deploy_lag", [False, True])
@pytest.mark.parametrize("npm_pending", [False, True])
@pytest.mark.parametrize("os_pending", [False, True])
@pytest.mark.parametrize("image_state", ["clean", "old", "findings", "unavailable"])
@pytest.mark.parametrize("host_ok", [False, True])
def test_blockers_preserve_every_term_of_the_previous_healthy_gate(
        tmp_path, monkeypatch, deploy_lag, npm_pending, os_pending, image_state, host_ok):
    now = datetime(2026, 10, 22, 4, 10, tzinfo=timezone.utc)
    world = _SecurityCycleWorld(tmp_path, monkeypatch, now)
    world.main = "b" * 40 if deploy_lag else "a" * 40
    world.npm_revision = "c" * 40 if npm_pending else world.main
    world.os_pending = 1 if os_pending else 0
    world.host_ok = host_ok
    if image_state == "old":
        world.image = _clean_image(now - timedelta(hours=3))
    elif image_state == "findings":
        # An old scan with real findings is never classified as a transient drift.
        world.image = {**_clean_image(now - timedelta(hours=3)), "finding_total": 2}
    elif image_state == "unavailable":
        world.image = None
    report = daily.cycle(tmp_path, world.gh(), now, {"automatic_merge": True}, world.previous())
    expected = ((["deploy_lag"] if deploy_lag else [])
                + (["errors"] if image_state == "unavailable" else [])
                + (["npm_evidence_pending"] if npm_pending else [])
                + (["os_security_pending"] if os_pending else [])
                + (["image_scan_predates_deploy"] if image_state == "old" else
                   ["image_findings_or_unavailable"] if image_state in ("findings", "unavailable") else [])
                + ([] if host_ok else ["unhealthy_host"]))
    assert report["healthy_blockers"] == expected
    images = world.image or {}
    assert report["healthy"] is bool(_previous_healthy(
        report, images, (tmp_path / ".deploy-version").stat().st_mtime, host_ok))
    assert report["healthy"] is (expected == []) and world.probes == 1


@pytest.mark.parametrize("blocker", ["errors", "alerts", "reboot_required"])
def test_other_healthy_blockers_are_named_separately(tmp_path, monkeypatch, blocker):
    now = datetime(2026, 10, 22, 4, 10, tzinfo=timezone.utc)
    world = _SecurityCycleWorld(tmp_path, monkeypatch, now)
    runs = {}
    if blocker == "errors":
        runs = {"c3po-pipeline.yml": [{"status": "completed", "conclusion": "failure"}]}
    elif blocker == "alerts":
        for path, content in files().items():
            (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / path).write_text(content)
        world.npm_alerts = [alert(severity="medium")]
    else:
        world.reboot_required = True
    report = daily.cycle(tmp_path, world.gh(workflow_runs=runs), now, {"automatic_merge": True}, world.previous())
    assert report["healthy_blockers"] == [blocker] and report["healthy"] is False


@pytest.mark.parametrize("probe", [False, RuntimeError("synthetic private Docker response")])
def test_pending_never_hides_an_unhealthy_host_or_failed_probe(tmp_path, monkeypatch, probe):
    now = datetime(2026, 10, 22, 13, 10, tzinfo=timezone.utc)
    world = _SecurityCycleWorld(tmp_path, monkeypatch, now)
    world.npm_revision = "b" * 40
    world.host_ok = probe
    report = daily.cycle(tmp_path, world.gh(), now, {"automatic_merge": True}, world.previous())
    assert report["healthy_blockers"] == ["npm_evidence_pending", "unhealthy_host"]
    assert report["status"] == "waiting_npm_evidence" and world.probes == 1
    assert report["healthy"] is False and "private" not in json.dumps(report)


def test_chained_merges_and_same_sha_redeploys_do_not_restart_postdeploy_anchors(tmp_path, monkeypatch):
    day = datetime(2026, 10, 22, tzinfo=timezone.utc)
    world = _SecurityCycleWorld(tmp_path, monkeypatch, day)
    world.image = _clean_image(day - timedelta(minutes=20))
    world.deploy("a" * 40, day - timedelta(hours=5))
    report = world.previous(last_dispatch_date="2026-10-21")

    def cycle(hour):
        nonlocal report
        world.npm_revision = world.main
        gh = world.gh()
        report = daily.cycle(tmp_path, gh, day.replace(hour=hour, minute=10), {"automatic_merge": True}, report)
        return gh.writes

    world.main = "b" * 40
    assert cycle(0) == [DEPENDENCY_DISPATCH]
    lag = report["deploy_lag_since"]
    world.main = "c" * 40
    assert cycle(1) == [DEPENDENCY_DISPATCH]
    assert report["deploy_lag_since"] == lag == day.replace(minute=10).isoformat()
    world.deploy("c" * 40, day.replace(hour=1, minute=50))
    assert cycle(2) == [DEPENDENCY_DISPATCH, IMAGE_DISPATCH]
    drift = report["image_drift_since"]
    assert report["deploy_lag_since"] is None and drift == day.replace(hour=2, minute=10).isoformat()
    world.deploy("c" * 40, day.replace(hour=2, minute=55))
    assert cycle(3) == [DEPENDENCY_DISPATCH, IMAGE_DISPATCH]
    assert report["image_drift_since"] == drift
    assert report["deployed_at"] == day.replace(hour=2, minute=55).isoformat()
    assert report["last_dispatched_deploy_at"] == report["deployed_at"]
    world.image = _clean_image(day.replace(hour=3, minute=30))
    assert cycle(4) == []
    assert report["image_drift_since"] is None and report["deploy_lag_since"] is None
    assert report["healthy"] is True and report["healthy_blockers"] == []
    assert report["last_dispatch_date"] == "2026-10-21"


@pytest.mark.parametrize("field", ["deploy_lag_since", "image_drift_since"])
@pytest.mark.parametrize("stored", [None, "", False, 0, [], {}, "invalid", "2026-10-22T03:10:00", "2099-01-01T00:00:00+00:00"])
def test_only_missing_or_none_postdeploy_anchors_start_a_new_clock(tmp_path, monkeypatch, field, stored):
    now = datetime(2026, 10, 22, 4, 10, tzinfo=timezone.utc)
    world = _SecurityCycleWorld(tmp_path, monkeypatch, now)
    if field == "deploy_lag_since":
        world.main = world.npm_revision = "b" * 40
    else:
        world.image = _clean_image(now - timedelta(hours=3))
    report = daily.cycle(tmp_path, world.gh(), now, {"automatic_merge": True}, world.previous(**{field: stored}))
    expected = now.isoformat() if stored is None else stored
    assert report[field] == expected and type(report[field]) is type(expected)


def test_night_deploy_scan_does_not_replace_the_10utc_daily_verification(tmp_path, monkeypatch):
    watchdog = importlib.import_module("c3po_security_watchdog")
    day = datetime(2026, 10, 22, tzinfo=timezone.utc)
    world = _SecurityCycleWorld(tmp_path, monkeypatch, day.replace(hour=3))
    world.image = _clean_image(day.replace(hour=3, minute=35))
    report = world.previous(last_dispatch_date="2026-10-21")
    world.main = world.npm_revision = "b" * 40
    world.deploy("b" * 40, day.replace(hour=4))
    scans, verified = [], []
    for hour in range(4, 12):
        now = day.replace(hour=hour, minute=10)
        gh = world.gh()
        report = daily.cycle(tmp_path, gh, now, {"automatic_merge": True}, report)
        if IMAGE_DISPATCH in gh.writes:
            scans.append(hour)
            world.image = _clean_image(now + timedelta(minutes=20))
        if watchdog.daily_execution_verified(report, now):
            verified.append(hour)
    assert scans == [4, 10] and verified == [10, 11]
    assert report["last_dispatch_date"] == "2026-10-22"


def test_failed_cycle_replaces_transient_blockers_but_preserves_anchors(tmp_path, monkeypatch):
    directory = tmp_path / "runtime/security"
    directory.mkdir(parents=True)
    previous = {"status": "waiting_maintenance_window", "healthy": False, "errors": [], "pending": [],
                "healthy_blockers": ["image_scan_predates_deploy"], "image_drift_since": "2026-10-22T13:17:05+00:00",
                "deploy_lag_since": None, "npm_lag_since": None, "deployed_at": "2026-10-22T13:17:00+00:00",
                "last_dispatched_deploy": "a" * 40, "last_dispatched_deploy_at": "2026-10-22T13:17:00+00:00"}
    daily.write_report(directory / daily.REPORT, previous)
    monkeypatch.setattr(sys, "argv", ["c3po_security_daily.py", "--root", str(tmp_path)])
    def unavailable(_root):
        raise RuntimeError("synthetic private Docker response")
    monkeypatch.setattr(daily, "github_token", unavailable)
    with pytest.raises(SystemExit):
        daily.main()
    failed = json.loads((directory / daily.REPORT).read_text())
    assert failed["healthy"] is False and failed["status"] == "failed"
    assert failed["healthy_blockers"] == ["routine_failed"] and failed["errors"] == ["RuntimeError"]
    assert "private" not in json.dumps(failed)
    for key in ("image_drift_since", "deploy_lag_since", "npm_lag_since", "deployed_at",
                "last_dispatched_deploy", "last_dispatched_deploy_at"):
        assert failed[key] == previous[key]


class _ApprovalGH:
    """Representative bot run: completed/action_required and empty PR links."""

    def __init__(self):
        self.main, self.sha = "a" * 40, "b" * 40
        self.base = files()
        output, applied, blocked = deps.prepare(self.base, [alert()])
        self.head = {p: v for p, v in output.items() if self.base[p] != v}
        self.head[deps.RECEIPT] = json.dumps({"schema": "C3PO_DEPENDENCY_REMEDIATION-v1",
            "base_sha": self.main, "applied": applied, "blocked": blocked})
        self.changed = [{"filename": p, "status": "added" if p == deps.RECEIPT else "modified"} for p in self.head]
        self.pr = {"number": 17, "state": "open", "draft": False, "user": {"login": "github-actions[bot]"},
            "head": {"sha": self.sha, "ref": "automation/dependency-security-daily",
                     "repo": {"id": daily.REPO_ID, "full_name": daily.REPO}},
            "base": {"ref": "main", "repo": {"id": daily.REPO_ID}}}
        self.associations = None
        self.run = {"id": 100, "run_attempt": 1, "head_sha": self.sha,
            "head_branch": self.pr["head"]["ref"], "event": "pull_request", "workflow_id": 55,
            "path": ".github/workflows/c3po-pipeline.yml", "status": "completed", "conclusion": "action_required",
            "repository": {"id": daily.REPO_ID}, "head_repository": {"id": daily.REPO_ID}, "pull_requests": []}
        self.proofs = [{"id": 90, "run_attempt": 1, "head_sha": self.sha, "event": "workflow_dispatch",
                        "head_branch": self.pr["head"]["ref"], "status": "completed", "conclusion": "success"}]
        self.extra_runs = []
        self.jobs = [{"name": name, "conclusion": "success", "status": "completed", "run_id": 90,
                      "head_sha": self.sha} for name in daily.REQUIRED_JOBS]
        self.writes, self.reads = [], []
        self.post_error = self.post_result = None
        self.on_read = lambda _path: None

    def clone(self, value):
        return json.loads(json.dumps(value))

    def request(self, path, method="GET", body=None):
        if method != "GET":
            assert method == "POST" and body is None
            assert path in {f"/actions/runs/{run['id']}/approve" for run in [self.run, *self.extra_runs]}
            self.writes.append((method, path))
            if self.post_error:
                raise self.post_error
            return self.post_result
        self.reads.append(path)
        self.on_read(path)
        if path == "/git/ref/heads/main":
            return {"object": {"sha": self.main}}
        if path == "/pulls/17":
            return self.clone(self.pr)
        if path == "/actions/runs/100":
            return self.clone(self.run)
        for run in self.proofs + self.extra_runs:
            if path == f"/actions/runs/{run['id']}":
                return self.clone(run)
        for number, filename in enumerate(sorted(daily.CI_APPROVAL_WORKFLOWS), 54):
            if path == "/actions/workflows/" + filename:
                return {"id": number, "path": ".github/workflows/" + filename, "state": "active"}
        raise AssertionError(path)

    def pages(self, path, key=None):
        if path == "/pulls?state=open&base=main":
            return [self.clone(self.pr)]
        if path == "/pulls/17/files":
            return self.clone(self.changed)
        if path == f"/commits/{self.sha}/pulls":
            return self.clone([self.pr] if self.associations is None else self.associations)
        if "event=workflow_dispatch" in path:
            return self.clone(self.proofs)
        if path == "/actions/runs/90/attempts/1/jobs":
            return self.clone(self.jobs)
        if path.startswith("/actions/workflows/") and "event=pull_request" in path:
            runs = [self.run, *self.extra_runs]
            if "status=action_required" in path:
                runs = [run for run in runs if daily._requires_approval(run)]
            return self.clone(runs) if "/" + self.run["path"].rsplit("/", 1)[1] + "/" in path else []
        raise AssertionError(path)

    def file(self, path, sha):
        return self.base[path] if sha == "a" * 40 else self.head[path]

    def approve(self, history, checkpoint=lambda: None, may_write=lambda: True, window_open=lambda: True):
        return daily.approve_ci(self, [alert()], "a" * 40, {}, history,
                                datetime(2026, 10, 24, 10, tzinfo=timezone.utc), checkpoint, may_write,
                                window_open=window_open)


def test_ci_approval_uses_exact_dispatch_attempt_and_journals_bodyless_acceptance():
    gh, history, snapshots = _ApprovalGH(), [], []
    def checkpoint():
        snapshots.append(gh.clone(history))
        if history[-1]["state"] == "intent":
            assert not gh.writes
    assert gh.approve(history, checkpoint) == ("waiting_ci_approval", 17, [])
    assert gh.writes == [("POST", "/actions/runs/100/approve")]
    assert [s[-1]["state"] for s in snapshots] == ["intent", "accepted"]
    assert history[-1]["run_attempt"] == 1 and history[-1]["head_sha"] == gh.sha
    assert gh.reads.count("/actions/runs/90") == 3
    assert gh.approve(history) == ("waiting_ci_approval", 17, [])
    assert len(gh.writes) == 1


@pytest.mark.parametrize("problem", ["human", "fork", "draft", "closed", "base", "prefix", "extra_file",
    "renamed", "injected_content", "ambiguous_pr", "wrong_event", "wrong_workflow", "wrong_sha", "wrong_branch",
    "wrong_repo", "proof_failure", "proof_skipped", "proof_missing_job", "proof_old_sha", "proof_new_failure"])
def test_ci_approval_rejects_untrusted_candidates_and_incomplete_proofs(problem):
    gh = _ApprovalGH()
    if problem == "human": gh.pr["user"]["login"] = "operator"
    elif problem == "fork": gh.pr["head"]["repo"]["id"] = 1
    elif problem == "draft": gh.pr["draft"] = True
    elif problem == "closed": gh.pr["state"] = "closed"
    elif problem == "base": gh.pr["base"]["ref"] = "other"
    elif problem == "prefix": gh.pr["head"]["ref"] = "automation/controller-positive-dry-run-fixture"
    elif problem == "extra_file": gh.changed.append({"filename": ".github/workflows/evil.yml", "status": "added"})
    elif problem == "renamed": gh.changed[0]["status"] = "renamed"
    elif problem == "injected_content":
        gh.changed.append({"filename": "c3po/frontend/package.json", "status": "modified"})
        gh.head["c3po/frontend/package.json"] = '{"scripts":{"build":"curl attacker"}}'
    elif problem == "ambiguous_pr": gh.associations = [gh.pr, gh.pr]
    elif problem == "wrong_event": gh.run["event"] = "pull_request_target"
    elif problem == "wrong_workflow": gh.run["workflow_id"] = 999
    elif problem == "wrong_sha": gh.run["head_sha"] = "c" * 40
    elif problem == "wrong_branch": gh.run["head_branch"] = "main"
    elif problem == "wrong_repo": gh.run["head_repository"]["id"] = 1
    elif problem == "proof_failure": gh.proofs[0]["conclusion"] = "failure"
    elif problem == "proof_skipped": gh.proofs[0]["conclusion"] = "skipped"
    elif problem == "proof_missing_job": gh.jobs.pop()
    elif problem == "proof_old_sha": gh.proofs[0]["head_sha"] = "c" * 40
    elif problem == "proof_new_failure": gh.proofs.append({**gh.proofs[0], "id": 91, "conclusion": "failure"})
    status, _, _ = gh.approve([])
    assert status in ("idle", "waiting_security_tests")
    assert not gh.writes


@pytest.mark.parametrize("change", ["main", "head", "attempt", "proof", "files", "hold"])
def test_ci_approval_rechecks_after_durable_intent_and_never_writes_on_drift(change):
    gh, history = _ApprovalGH(), []
    def checkpoint():
        if history[-1]["state"] != "intent": return
        if change == "main": gh.main = "c" * 40
        elif change == "head": gh.pr["head"]["sha"] = "c" * 40
        elif change == "attempt": gh.run["run_attempt"] = 2
        elif change == "proof": gh.proofs[0]["conclusion"] = "failure"
    if change == "files":
        reads = []
        def on_read(path):
            if path != "/pulls/17": return
            reads.append(path)
            if len(reads) == 1:
                gh.changed.append({"filename": "unrelated.py", "status": "added"})
        gh.on_read = on_read
    status, _, _ = gh.approve(history, checkpoint, may_write=lambda: change != "hold")
    assert status in ("waiting_ci_approval", "baseline_changed_or_hold") and not gh.writes


@pytest.mark.parametrize("outcome", ["403", "404", "timeout", "unexpected_body"])
def test_ci_approval_unknown_post_never_resends_or_claims_success(outcome):
    gh, history = _ApprovalGH(), []
    if outcome in ("403", "404"):
        gh.post_error = HTTPError("https://private.invalid/token", int(outcome), "private response", None, None)
    elif outcome == "timeout": gh.post_error = URLError("private response with token")
    else: gh.post_result = {"message": "not documented acceptance"}
    assert gh.approve(history)[0] == "blocked_ci_approval"
    assert history[-1]["state"] == "unknown" and "private" not in json.dumps(history)
    assert daily.reconcile_ci_approvals(gh, history) == (["ci_approval:outcome_unconfirmed"], [])
    gh.approve(history)
    assert len(gh.writes) == 1
    gh.run.update(run_attempt=2, status="in_progress", conclusion=None)
    assert daily.reconcile_ci_approvals(gh, history) == ([], ["ci_approval_pending"])
    gh.run.update(status="completed", conclusion="success")
    assert daily.reconcile_ci_approvals(gh, history) == ([], [])
    assert history[-1]["state"] == "superseded"


def test_ci_approval_crash_after_intent_is_reconciled_without_resending():
    gh, history = _ApprovalGH(), []
    with pytest.raises(KeyboardInterrupt):
        gh.approve(history, checkpoint=lambda: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert history[-1]["state"] == "intent" and not gh.writes
    assert daily.reconcile_ci_approvals(gh, history)[0] == ["ci_approval:outcome_unconfirmed"]
    gh.approve(history)
    assert not gh.writes


@pytest.mark.parametrize("configured", [None, False, "true", 1])
def test_ci_approval_requires_literal_opt_in_and_preserves_promotion(tmp_path, monkeypatch, configured):
    now = datetime(2026, 10, 24, 10, tzinfo=timezone.utc)
    world = _SecurityCycleWorld(tmp_path, monkeypatch, now)
    monkeypatch.setattr(daily, "approve_ci", lambda *a, **k: pytest.fail("approval was not opted in"))
    config = {"automatic_merge": True}
    if configured is not None: config["automatic_ci_approval"] = configured
    report = daily.cycle(tmp_path, world.gh(), now, config, world.previous())
    assert report["ci_approval"]["enabled"] is False
    assert report["status"] == "no_validated_candidate" and report["healthy"] is True


@pytest.mark.parametrize("blocker", ["hold", "trial", "host", "window", "merge_disabled"])
def test_ci_approval_opt_in_preserves_existing_maintenance_gates(tmp_path, monkeypatch, blocker):
    now = datetime(2026, 10, 24, 12 if blocker == "window" else 10, tzinfo=timezone.utc)
    world = _SecurityCycleWorld(tmp_path, monkeypatch, now)
    if blocker == "hold": (tmp_path / "hold").touch()
    elif blocker == "trial": monkeypatch.setattr(daily, "trial_present", lambda _: True)
    elif blocker == "host": world.host_ok = False
    monkeypatch.setattr(daily, "approve_ci", lambda *a, **k: pytest.fail("blocked approval"))
    report = daily.cycle(tmp_path, world.gh(), now,
        {"automatic_merge": blocker != "merge_disabled", "automatic_ci_approval": True}, world.previous())
    assert report["ci_approval"]["history"] == []


def test_ci_approval_acceptance_is_pending_never_healthy_or_same_cycle_merge(tmp_path, monkeypatch):
    now = datetime(2026, 10, 24, 10, tzinfo=timezone.utc)
    world = _SecurityCycleWorld(tmp_path, monkeypatch, now)
    def approve(*args, **kwargs):
        return "waiting_ci_approval", 17, []
    monkeypatch.setattr(daily, "approve_ci", approve)
    monkeypatch.setattr(daily, "promote", lambda *a, **k: pytest.fail("same-cycle merge path"))
    report = daily.cycle(tmp_path, world.gh(), now,
        {"automatic_merge": True, "automatic_ci_approval": True}, world.previous())
    assert report["status"] == "waiting_ci_approval" and report["healthy"] is False
    assert report["pending"] == ["ci_approval_pending"] and report["healthy_blockers"] == ["ci_approval_pending"]


def test_ci_approval_checks_window_after_health_probe(tmp_path, monkeypatch):
    now = datetime(2026, 10, 24, 11, 59, 59, tzinfo=timezone.utc)
    world = _SecurityCycleWorld(tmp_path, monkeypatch, now)
    clock = [now]
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return clock[0]
    monkeypatch.setattr(daily, "datetime", Clock)
    probes = []
    def probe(_):
        probes.append(1)
        if len(probes) > 1: clock[0] = now + timedelta(seconds=2)
        return True
    monkeypatch.setattr(daily, "healthy_host", probe)
    def approve(*args, **kwargs):
        assert kwargs["may_write"]() is False
        return "baseline_changed_or_hold", 17, []
    monkeypatch.setattr(daily, "approve_ci", approve)
    report = daily.cycle(tmp_path, world.gh(), now,
        {"automatic_merge": True, "automatic_ci_approval": True}, world.previous())
    assert report["status"] == "baseline_changed_or_hold"


@pytest.mark.parametrize("status,body", [(201, b""), (201, b"null"), (201, b" "),
                                         (200, b""), (202, b""), (204, b"")])
def test_ci_approval_http_contract_requires_bodyless_201(monkeypatch, status, body):
    import urllib.request
    class Response:
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self): return body
    response = Response()
    response.status = status
    class Opener:
        def open(self, request, timeout):
            assert request.full_url == "https://api.github.com/repos/" + daily.REPO + "/actions/runs/100/approve"
            assert request.method == "POST" and request.data is None
            return response
    monkeypatch.setattr(urllib.request, "build_opener", lambda *_: Opener())
    gh = daily.GitHub("synthetic-test-token")
    if status == 201 and not body:
        assert gh.request("/actions/runs/100/approve", "POST") is None
    else:
        with pytest.raises(ValueError, match="Unexpected CI approval"):
            gh.request("/actions/runs/100/approve", "POST")


@pytest.mark.parametrize("linked", [True, False])
def test_ci_approval_can_bind_populated_or_empty_pr_association(linked):
    gh = _ApprovalGH()
    if linked:
        gh.run["pull_requests"] = [{"number": gh.pr["number"], "head": gh.pr["head"], "base": gh.pr["base"]}]
        gh.associations = []  # The explicit matching association is sufficient.
    assert gh.approve([])[0] == "waiting_ci_approval" and len(gh.writes) == 1


def test_ci_approval_container_lane_keeps_its_narrow_content_gate(monkeypatch):
    gh = _ApprovalGH()
    branch = "automation/container-security-rebuild-current"
    gh.pr["head"]["ref"] = gh.run["head_branch"] = gh.proofs[0]["head_branch"] = branch
    trigger_path = "c3po/security/container-rebuild-trigger.json"
    trigger = {"schema": "C3PO_CONTAINER_REBUILD_TRIGGER-v1", "dry_run": False, "source_revision": gh.main,
               "run_url": "https://github.com/example/scan", "artifact_name": "scan",
               "remediation_key": "key", "evidence_scope": "production_runtime", "fix_available": {"high": 1},
               "finding_total": 1, "findings": [{"package": "synthetic"}]}
    gh.head = {trigger_path: json.dumps(trigger)}
    gh.changed = [{"filename": trigger_path, "status": "added"}]
    monkeypatch.setattr(daily, "validate_report", lambda _: (trigger["fix_available"], trigger["findings"]))
    monkeypatch.setattr(daily, "build_trigger", lambda *a, **k: trigger)
    assert gh.approve([])[0] == "waiting_ci_approval" and len(gh.writes) == 1
    gh.writes.clear()
    gh.changed.append({"filename": "c3po/backend/requirements.txt", "status": "modified"})
    assert gh.approve([])[0] == "idle" and not gh.writes


@pytest.mark.parametrize("resolved", ["closed", "new_head"])
def test_ci_approval_failed_old_receipt_retires_without_erasing_failure(resolved):
    gh, history = _ApprovalGH(), []
    gh.approve(history)
    gh.run["conclusion"] = "failure"
    assert daily.reconcile_ci_approvals(gh, history) == (["ci_approval:run_not_successful"], [])
    assert history[0]["observed_conclusion"] == "failure"
    if resolved == "closed": gh.pr["state"] = "closed"
    else: gh.pr["head"]["sha"] = "c" * 40
    assert daily.reconcile_ci_approvals(gh, history) == ([], [])
    assert history[0]["state"] == "retired" and history[0]["observed_conclusion"] == "failure"
    assert len(gh.writes) == 1


def test_ci_approval_failed_cycle_preserves_durable_intent(tmp_path, monkeypatch):
    directory = tmp_path / "runtime/security"
    directory.mkdir(parents=True)
    gh, history = _ApprovalGH(), []
    gh.approve(history)
    monkeypatch.setattr(sys, "argv", ["c3po_security_daily.py", "--root", str(tmp_path)])
    monkeypatch.setattr(daily, "github_token", lambda _: "synthetic-token")
    monkeypatch.setattr(daily, "GitHub", lambda _: gh)
    monkeypatch.setattr(daily, "ensure_workflows", lambda *_: None)
    config = tmp_path / "config.json"
    config.write_text("{}")
    monkeypatch.setattr(daily, "CONFIG", config)
    def failed_cycle(*args):
        daily.write_report(directory / daily.REPORT, {"ci_approval": {"history": history}})
        raise RuntimeError("private response")
    monkeypatch.setattr(daily, "cycle", failed_cycle)
    with pytest.raises(SystemExit): daily.main()
    failed = json.loads((directory / daily.REPORT).read_text())
    assert failed["ci_approval"]["history"] == history and failed["healthy"] is False
    assert failed["errors"] == ["RuntimeError"] and "private" not in json.dumps(failed)


def test_ci_approval_history_limit_and_invalid_receipts_fail_closed():
    gh, history = _ApprovalGH(), []
    gh.approve(history)
    with pytest.raises(ValueError): daily.ci_approval_history({"ci_approval": {"history": [{"state": "unknown"}]}})
    history[0]["run_id"] = 1
    history *= daily.CI_APPROVAL_HISTORY_LIMIT
    gh.writes.clear()
    assert gh.approve(history)[2] == ["ci_approval:history_full"]
    assert not gh.writes


@pytest.mark.parametrize("drift", ["head_during_proof", "head_during_health", "window_during_final_reads"])
def test_ci_approval_final_reads_follow_slow_proof_and_health(drift):
    gh, history = _ApprovalGH(), []
    live_window = [True]
    def on_read(path):
        if not history or history[-1]["state"] != "intent": return
        if drift == "head_during_proof" and path == "/actions/runs/90":
            gh.pr["head"]["sha"] = "c" * 40
        if drift == "window_during_final_reads" and path == "/pulls/17":
            live_window[0] = False
    gh.on_read = on_read
    def health():
        if drift == "head_during_health": gh.pr["head"]["sha"] = "c" * 40
        return True
    assert gh.approve(history, may_write=health, window_open=lambda: live_window[0])[0] == "baseline_changed_or_hold"
    assert not gh.writes and history[-1]["state"] == "not_sent"


def test_ci_approval_proof_attempt_change_during_job_reads_is_not_green():
    gh = _ApprovalGH()
    def on_read(path):
        if path == "/actions/runs/90": gh.proofs[0]["run_attempt"] = 2
    gh.on_read = on_read
    assert gh.approve([])[0] == "waiting_security_tests" and not gh.writes


def test_ci_approval_backend_ci_is_allowlisted_but_still_needs_dispatch_proof():
    gh = _ApprovalGH()
    gh.run.update(path=".github/workflows/backend-postgres.yml", workflow_id=54)
    assert gh.approve([])[0] == "waiting_ci_approval" and len(gh.writes) == 1


@pytest.mark.parametrize("conclusion", ["success", "action_required", "failure"])
def test_ci_approval_new_run_same_sha_can_replace_old_failed_receipt(conclusion):
    gh, history = _ApprovalGH(), []
    gh.approve(history)
    gh.run["conclusion"] = "failure"
    gh.extra_runs = [{**gh.clone(gh.run), "id": 101, "conclusion": conclusion}]
    errors, pending = daily.reconcile_ci_approvals(gh, history)
    if conclusion == "failure":
        assert errors == ["ci_approval:run_not_successful"]
        assert history[0]["state"] == "accepted"
    else:
        assert not errors and not pending
        assert history[0]["state"] == "retired" and history[0]["retired_reason"] == "newer_run"
        assert history[0]["replacement_run_id"] == 101
        assert history[0]["observed_conclusion"] == "failure" and history[0]["post_outcome"] == "accepted"
    assert len(gh.writes) == 1


@pytest.mark.parametrize("replacement", ["success", "action_required"])
def test_ci_approval_retired_action_required_run_does_not_block_replacement(replacement):
    gh, history = _ApprovalGH(), []
    gh.approve(history)  # Run100 may still be action_required after this request.
    gh.extra_runs = [{**gh.clone(gh.run), "id": 101, "conclusion": replacement}]
    assert daily.reconcile_ci_approvals(gh, history) == ([], [])
    assert history[0]["state"] == "retired"
    status, _, errors = gh.approve(history)
    assert not errors
    if replacement == "success":
        assert status == "idle" and gh.writes == [("POST", "/actions/runs/100/approve")]
    else:
        assert status == "waiting_ci_approval"
        assert gh.writes == [("POST", "/actions/runs/100/approve"), ("POST", "/actions/runs/101/approve")]
