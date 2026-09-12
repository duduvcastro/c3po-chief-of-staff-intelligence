from __future__ import annotations

import importlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

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
    assert len(report["errors"]) == 3
    daily.cycle(tmp_path, gh, datetime(2026, 9, 12, 11, tzinfo=timezone.utc), {"automatic_merge": True}, report)
    assert len(gh.calls) == 2


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
