from __future__ import annotations

import base64
import importlib.util
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from app.r2d2_v2_earnings_package import PACKAGE_FILES


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / ".github" / "scripts"
SCRIPT_PATH = SCRIPTS / "c3po_security_merge_window.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "security-merge-window.yml"
DOC_PATH = ROOT / "c3po" / "docs" / "DAILY_SECURITY_MAINTENANCE.md"
REPOSITORY = "duduvcastro/c3po-chief-of-staff-intelligence"
RUN_URL = f"https://github.com/{REPOSITORY}/actions/runs/999"
# Tuesday 20/10/2026 18:05 BRT (21:05 UTC; New York 17:05 EDT): inside the window.
OPEN = datetime(2026, 10, 20, 21, 5, tzinfo=timezone.utc)
MAIN = "a" * 40


def _load() -> ModuleType:
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("c3po_security_merge_window", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["c3po_security_merge_window"] = module
    spec.loader.exec_module(module)
    return module


mw = _load()


# ------------------------------------------------------------------------------- fixtures
def _message(name: str, version: str, update: str = "version-update:semver-patch") -> str:
    return (f"Bump {name} from 1.2.3 to {version} in /c3po/frontend\n\nBumps [{name}](https://example.invalid) from 1.2.3 to {version}.\n\n"
            f"---\nupdated-dependencies:\n- dependency-name: {name}\n  dependency-version: {version}\n"
            f"  dependency-type: indirect\n  update-type: {update}\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\n")


def _dependabot_pull(number: int, *, name: str = "left-pad", old: str = "1.2.3", new: str = "1.2.4",
                     sha: str | None = None, created: str = "2026-10-08T10:00:00Z") -> dict[str, Any]:
    return {
        "number": number, "title": f"Bump {name} from {old} to {new} in /c3po/frontend", "body": "",
        "user": {"login": "dependabot[bot]"}, "draft": False, "labels": [], "created_at": created,
        "base": {"ref": "main"},
        "head": {"ref": f"dependabot/npm_and_yarn/c3po/frontend/{name}-{new}", "sha": sha or f"{number:040d}",
                 "repo": {"full_name": REPOSITORY}},
    }


def _lane_pull(number: int, *, sha: str | None = None) -> dict[str, Any]:
    return {
        "number": number, "title": "Remediate fixable container findings", "body": "",
        "user": {"login": "github-actions[bot]"}, "draft": False, "labels": [], "created_at": "2026-10-09T10:00:00Z",
        "base": {"ref": "main"},
        "head": {"ref": "automation/container-security-rebuild-abc", "sha": sha or f"{number:040d}",
                 "repo": {"full_name": REPOSITORY}},
    }


def _alert(name: str = "left-pad", patched: str = "1.2.4", manifest: str = "c3po/frontend/pnpm-lock.yaml") -> dict[str, Any]:
    return {"state": "open", "dependency": {"package": {"ecosystem": "npm", "name": name}, "manifest_path": manifest},
            "security_vulnerability": {"first_patched_version": {"identifier": patched}},
            "security_advisory": {"ghsa_id": "GHSA-cfgh-2345-vwxq"}}


def _commit(message: str, *, login: str = "dependabot[bot]", parents: int = 1) -> dict[str, Any]:
    return {"author": {"login": login}, "parents": [{}] * parents, "commit": {"message": message}}


def _green(sha: str, *, proof: bool = False, extra: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    names = list(mw.REQUIRED_CHECKS) + (["Security remediation proof"] if proof else [])
    return [{"id": index + 1, "name": name, "status": "completed", "conclusion": "success", "head_sha": sha}
            for index, name in enumerate(names)] + (extra or [])


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class FakeGitHub:
    """Routes the REST paths the script uses; strict mode: a merge moves main and makes the others BEHIND."""

    def __init__(self) -> None:
        self.pulls: list[dict[str, Any]] = []
        self.details: dict[int, dict[str, Any]] = {}
        self.files: dict[int, list[dict[str, Any]]] = {}
        self.commits: dict[int, list[dict[str, Any]]] = {}
        self.alerts: list[dict[str, Any]] | int = []
        self.checks: dict[str, list[dict[str, Any]]] = {}
        self.active: dict[str, int] = {}
        self.pipeline_runs: list[dict[str, Any]] = []
        self.jobs: dict[int, list[dict[str, Any]]] = {}
        self.main = MAIN
        self.writes: list[tuple[str, str, Any]] = []
        self.comments: list[dict[str, Any]] = []
        self.channel = {"state": "open", "locked": False, "comments": 10}
        self.trigger: dict[str, Any] = {"schema": mw.CONTAINER_TRIGGER_SCHEMA, "dry_run": False, "remediation_key": "e" * 64}
        self.deploy_conclusion = "success"
        self.validation_turns_green = True
        self._ids = 1000

    def add(self, pull: dict[str, Any], *, state: str = "clean", files: list[dict[str, Any]] | None = None,
            commits: list[dict[str, Any]] | None = None, checks: list[dict[str, Any]] | None = None) -> None:
        self.pulls.append(pull)
        self.details[pull["number"]] = {**pull, "state": "open", "mergeable": True, "mergeable_state": state}
        lane = pull["head"]["ref"].startswith("automation/")
        self.files[pull["number"]] = files if files is not None else [
            {"filename": mw.CONTAINER_TRIGGER if lane else "c3po/frontend/pnpm-lock.yaml", "status": "modified"}]
        self.commits[pull["number"]] = commits if commits is not None else [_commit(_message("left-pad", "1.2.4"))]
        self.checks[pull["head"]["sha"]] = checks if checks is not None else _green(pull["head"]["sha"], proof=lane)

    def _next(self) -> int:
        self._ids += 1
        return self._ids

    def request(self, method: str, path: str, body: Any = None) -> Any:
        if method != "GET":
            self.writes.append((method, path, body))
        if method == "GET" and path == "/git/ref/heads/main":
            return {"object": {"sha": self.main}}
        if method == "GET" and (match := re.fullmatch(r"/pulls/(\d+)", path)):
            return self.details[int(match.group(1))]
        if method == "GET" and path.startswith("/contents/"):
            return {"content": base64.b64encode(json.dumps(self.trigger).encode()).decode()}
        if method == "GET" and re.fullmatch(r"/issues/\d+", path):
            return self.channel
        if method == "PUT" and (match := re.fullmatch(r"/pulls/(\d+)/merge", path)):
            number = int(match.group(1))
            detail = self.details[number]
            if detail["mergeable_state"] != "clean" or body["sha"] != detail["head"]["sha"]:
                raise mw.ApiError(method, path, 405)
            detail["state"] = "closed"
            self.main = f"{self._next():040x}"
            for other, item in self.details.items():
                if other != number and item["state"] == "open" and item["mergeable_state"] == "clean":
                    item["mergeable_state"] = "behind"
            return {"merged": True}
        if method == "PUT" and (match := re.fullmatch(r"/pulls/(\d+)/update-branch", path)):
            detail = self.details[int(match.group(1))]
            if body["expected_head_sha"] != detail["head"]["sha"]:
                raise mw.ApiError(method, path, 422)
            detail["head"] = {**detail["head"], "sha": f"{self._next():040x}"}
            detail["mergeable_state"] = "blocked"
            return {"message": "Updating pull request branch."}
        if method == "POST" and path == f"/actions/workflows/{mw.PIPELINE}/dispatches":
            sha, deploy = body["inputs"]["ref"], body["inputs"]["deploy"] == "true"
            run_id = self._next()
            self.pipeline_runs.append({"id": run_id, "head_sha": sha, "event": "workflow_dispatch", "status": "completed",
                                       "conclusion": "success"})
            self.jobs[run_id] = [{"name": "Deploy production", "conclusion": self.deploy_conclusion if deploy else "skipped"}]
            if not deploy and self.validation_turns_green:
                lane = body["inputs"]["remediation"] == "true"
                self.checks[sha] = _green(sha, proof=lane)
                for detail in self.details.values():
                    if detail["head"]["sha"] == sha:
                        detail["mergeable_state"] = "clean"
            return None
        raise AssertionError(f"unexpected request {method} {path}")

    def pages(self, path: str, key: str | None = None) -> list[Any]:
        if path.startswith("/pulls?"):
            return [pull for pull in self.pulls if self.details[pull["number"]]["state"] == "open"]
        if (match := re.fullmatch(r"/pulls/(\d+)/files\?.*", path)):
            return self.files[int(match.group(1))]
        if (match := re.fullmatch(r"/pulls/(\d+)/commits\?.*", path)):
            return self.commits[int(match.group(1))]
        if path.startswith("/dependabot/alerts"):
            if isinstance(self.alerts, int):
                raise mw.ApiError("GET", path, self.alerts)
            return self.alerts
        if (match := re.fullmatch(r"/commits/([0-9a-f]+)/check-runs\?.*", path)):
            return self.checks.get(match.group(1), [])
        if (match := re.fullmatch(r"/actions/workflows/([\w.-]+)/runs\?status=(\w+)&.*", path)):
            return [{}] * self.active.get(match.group(1), 0) if match.group(2) == "in_progress" else []
        if (match := re.fullmatch(rf"/actions/workflows/{re.escape(mw.PIPELINE)}/runs\?(.*)", path)):
            query = dict(part.split("=", 1) for part in match.group(1).split("&"))
            return [run for run in self.pipeline_runs if run["head_sha"] == query.get("head_sha")
                    and ("event" not in query or run["event"] == query["event"])]
        if (match := re.fullmatch(r"/actions/runs/(\d+)/jobs\?.*", path)):
            return self.jobs.get(int(match.group(1)), [])
        if path.startswith("/issues/"):
            return self.comments
        raise AssertionError(f"unexpected listing {path}")

    def deployed(self, sha: str) -> None:
        run_id = self._next()
        self.pipeline_runs.append({"id": run_id, "head_sha": sha, "event": "push", "status": "completed", "conclusion": "success"})
        self.jobs[run_id] = [{"name": "Deploy production", "conclusion": "success"}]


def _window(api: FakeGitHub, clock: Clock, *, live: bool = True, max_merges: int = 3) -> Any:
    return mw.MergeWindow(api, repository=REPOSITORY, live=live, max_merges=max_merges, clock=clock, sleep=clock.sleep,
                          poll_seconds=60)


def _actions(report: Any) -> dict[int, tuple[str, str]]:
    return {outcome.candidate.number: (outcome.action, outcome.reason) for outcome in report.outcomes}


# --------------------------------------------------------------------------------- the clock
@pytest.mark.parametrize(("utc", "expected"), [
    (datetime(2026, 10, 20, 21, 5), None),                     # Tue 18:05 BRT, 17:05 EDT
    (datetime(2026, 10, 20, 20, 0), "pregão B3/EUA"),          # Tue 17:00 BRT
    (datetime(2026, 10, 20, 13, 0), "pregão B3/EUA"),          # Tue 10:00 BRT
    (datetime(2026, 10, 20, 11, 30), None),                    # Tue 08:30 BRT
    (datetime(2026, 10, 20, 11, 0), "ciclo noturno"),          # Tue 08:00 BRT
    (datetime(2026, 10, 21, 2, 40), "ciclo noturno"),          # Tue 23:40 BRT
    (datetime(2026, 10, 21, 2, 0), "o deploy de até 45 min"),  # Tue 23:00 BRT: the deploy would reach 23:30
    (datetime(2026, 11, 3, 21, 0), "pregão dos EUA"),          # Tue 18:00 BRT = 16:00 EST (US winter time)
    (datetime(2026, 11, 3, 21, 20), None),                     # 16:20 EST
    (datetime(2026, 10, 24, 15, 0), None),                     # Saturday 12:00 BRT: no session
    (datetime(2026, 10, 20, 12, 30), "o deploy de até 45 min"),  # Tue 09:30 BRT: the deploy would reach 10:00
])
def test_window_clock(utc: datetime, expected: str | None) -> None:
    problem = mw.window_problem(utc.replace(tzinfo=timezone.utc))
    if expected is None:
        assert problem is None
    else:
        assert problem is not None and expected in problem


def test_next_open_is_bounded() -> None:
    winter = datetime(2026, 11, 3, 21, 0, tzinfo=timezone.utc)
    assert mw.next_open(winter, timedelta(minutes=30)) == datetime(2026, 11, 3, 21, 15, tzinfo=timezone.utc)
    assert mw.next_open(datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc), timedelta(minutes=30)) is None


# ------------------------------------------------------------------------------- selection
@pytest.mark.parametrize(("old", "new", "kind"), [
    ("1.2.3", "1.2.4", "patch"), ("1.2.3", "1.3.0", "minor"), ("1.2.3", "2.0.0", "major"),
    ("0.4.1", "0.5.0", "major"), ("0.0.3", "0.0.4", "major"), ("0.4.1", "0.4.2", "patch"),
    ("1.2.3", "1.2.3", None), ("1.2.4", "1.2.3", None), ("1.2.3", "1.2.4-rc.1", None), ("v2.31", "v2.32", "minor"),
])
def test_bump_kind(old: str, new: str, kind: str | None) -> None:
    assert mw.bump_kind(old, new) == kind


def _classify(pull: dict[str, Any], *, files: list[dict[str, Any]] | None = None, commits: list[dict[str, Any]] | None = None,
              alerts: list[dict[str, Any]] | None = None) -> Any:
    return mw.classify_dependabot(
        pull, files if files is not None else [{"filename": "c3po/frontend/pnpm-lock.yaml", "status": "modified"}],
        commits if commits is not None else [_commit(_message("left-pad", "1.2.4"))],
        [_alert()] if alerts is None else alerts, REPOSITORY)


def test_a_security_patch_on_the_lockfile_is_eligible() -> None:
    candidate = _classify(_dependabot_pull(447))
    assert candidate.eligible and candidate.security
    assert "left-pad 1.2.3→1.2.4 (patch, GHSA-cfgh-2345-vwxq)" in candidate.detail


def test_only_security_updates_are_selected() -> None:
    no_alert = _classify(_dependabot_pull(447), alerts=[])
    assert not no_alert.eligible and not no_alert.security and no_alert.reason == "atualização de versão sem alerta de segurança"
    not_fixed = _classify(_dependabot_pull(447), alerts=[_alert(patched="1.2.5")])
    assert not not_fixed.eligible
    other_manifest = _classify(_dependabot_pull(447), alerts=[_alert(manifest="c3po/backend/requirements.txt")])
    assert not other_manifest.eligible
    closed = _alert()
    closed["state"] = "dismissed"
    assert not _classify(_dependabot_pull(447), alerts=[closed]).eligible
    unreadable = mw.classify_dependabot(_dependabot_pull(447), [{"filename": "c3po/frontend/pnpm-lock.yaml", "status": "modified"}],
                                        [_commit(_message("left-pad", "1.2.4"))], None, REPOSITORY)
    assert not unreadable.eligible and "ilegíveis" in unreadable.reason


def test_major_bumps_are_refused_even_when_declared_minor() -> None:
    major = _classify(_dependabot_pull(447, new="2.0.0"),
                      commits=[_commit(_message("left-pad", "2.0.0", "version-update:semver-minor"))], alerts=[_alert(patched="2.0.0")])
    assert not major.eligible and major.security and "salto major" in major.reason
    zero_minor = _classify(_dependabot_pull(447, old="0.4.1", new="0.5.0"),
                           commits=[_commit(_message("left-pad", "0.5.0", "version-update:semver-minor"))], alerts=[_alert(patched="0.5.0")])
    assert not zero_minor.eligible and "salto major" in zero_minor.reason


def test_python_names_are_normalized_and_minor_is_accepted() -> None:
    pull = _dependabot_pull(450, name="python_multipart", old="0.9.1", new="0.9.4")
    pull["title"] = "Bump python-multipart from 1.2.3 to 1.3.0 in /c3po/backend"
    candidate = _classify(pull, files=[{"filename": "c3po/backend/requirements.txt", "status": "modified"}],
                          commits=[_commit(_message("Python_Multipart", "1.3.0", "version-update:semver-minor"))],
                          alerts=[_alert(name="python-multipart", patched="1.2.9", manifest="c3po/backend/requirements.txt")])
    assert candidate.eligible, candidate.reason


@pytest.mark.parametrize(("path", "reason"), [
    (".github/workflows/c3po-pipeline.yml", "workflow"),
    ("c3po/backend/Dockerfile", "Dockerfile"),
    ("c3po/frontend/Dockerfile.web", "Dockerfile"),
    ("c3po/compose.yml", "Dockerfile/compose"),
    ("c3po/backend/app/config.py", "código do app"),
    ("c3po/backend/app/valuation_pit_served.py", "código do app"),
    ("c3po/docs/PREREG_VALUATION_DECISOR_V1.md", "documento"),
    ("c3po/frontend/src/main.tsx", "fora da lista permitida"),
])
def test_files_outside_the_manifest_allowlist_are_refused(path: str, reason: str) -> None:
    candidate = _classify(_dependabot_pull(447), files=[{"filename": "c3po/frontend/pnpm-lock.yaml", "status": "modified"},
                                                        {"filename": path, "status": "modified"}])
    assert not candidate.eligible and reason in candidate.reason


def test_the_allowlist_never_reaches_frozen_or_package_files() -> None:
    for name in PACKAGE_FILES:
        path = f"c3po/backend/app/{name}"
        assert path not in mw.MANIFEST_ALLOWLIST
        problem = mw.files_problem([{"filename": path, "status": "modified"}], mw.MANIFEST_ALLOWLIST)
        assert problem is not None and "PACKAGE_FILES" in problem
    assert all(not path.startswith(("c3po/backend/app/", ".github/", "c3po/docs/")) for path in mw.MANIFEST_ALLOWLIST)
    assert "requirements.txt" not in PACKAGE_FILES and not any(name.endswith((".txt", ".json", ".yaml")) for name in PACKAGE_FILES)
    added = mw.files_problem([{"filename": "c3po/frontend/package.json", "status": "added"}], mw.MANIFEST_ALLOWLIST)
    assert added is not None and "só modificação" in added


def test_foreign_commits_or_branches_are_refused() -> None:
    foreign = _classify(_dependabot_pull(447), commits=[_commit(_message("left-pad", "1.2.4")), _commit("tweak", login="someone")])
    assert not foreign.eligible and "commits" in foreign.reason
    merged_main = _classify(_dependabot_pull(447), commits=[_commit(_message("left-pad", "1.2.4")),
                                                            _commit("Merge branch 'main'", login="web-flow", parents=2)])
    assert merged_main.eligible
    fork = _dependabot_pull(447)
    fork["head"]["repo"]["full_name"] = "someone/fork"
    assert not _classify(fork).eligible


def test_the_container_lane_needs_only_the_trigger_and_a_real_trigger() -> None:
    files = [{"filename": mw.CONTAINER_TRIGGER, "status": "modified"}]
    trigger = {"schema": mw.CONTAINER_TRIGGER_SCHEMA, "dry_run": False, "remediation_key": "e" * 64}
    assert mw.classify_container(_lane_pull(446), files, trigger, REPOSITORY).eligible
    assert not mw.classify_container(_lane_pull(446), files, {**trigger, "dry_run": True}, REPOSITORY).eligible
    extra = files + [{"filename": "c3po/backend/Dockerfile", "status": "modified"}]
    assert "Dockerfile" in mw.classify_container(_lane_pull(446), extra, trigger, REPOSITORY).reason
    human = _lane_pull(446)
    human["user"]["login"] = "someone"
    assert not mw.classify_container(human, files, trigger, REPOSITORY).eligible


def test_checks_must_be_green_on_the_exact_head() -> None:
    assert mw.checks_verdict(_green("s"), mw.REQUIRED_CHECKS)[0] is True
    missing = _green("s")[1:]
    assert mw.checks_verdict(missing, mw.REQUIRED_CHECKS)[:2] == (False, False)
    rerun_red = _green("s") + [{"id": 99, "name": "Backend tests", "status": "completed", "conclusion": "failure"}]
    green, settled, reason = mw.checks_verdict(rerun_red, mw.REQUIRED_CHECKS)
    assert (green, settled) == (False, True) and "Backend tests" in reason
    other_red = _green("s", extra=[{"id": 50, "name": "Some other check", "status": "completed", "conclusion": "failure"}])
    assert mw.checks_verdict(other_red, mw.REQUIRED_CHECKS)[0] is False
    skipped_deploy = _green("s", extra=[{"id": 51, "name": "Deploy production", "status": "completed", "conclusion": "skipped"}])
    assert mw.checks_verdict(skipped_deploy, mw.REQUIRED_CHECKS)[0] is True
    assert mw.checks_verdict(_green("s"), mw.REQUIRED_CHECKS + (mw.PROOF_CHECK,))[0] is False


def test_metadata_parser_reads_grouped_updates() -> None:
    message = ("Bump the npm_and_yarn group\n\n---\nupdated-dependencies:\n- dependency-name: a\n  dependency-version: 1.0.1\n"
               "  update-type: version-update:semver-patch\n- dependency-name: \"b\"\n  dependency-version: 2.1.0\n...\n")
    assert mw.parse_updated_dependencies(message) == [
        {"dependency-name": "a", "dependency-version": "1.0.1", "update-type": "version-update:semver-patch"},
        {"dependency-name": "b", "dependency-version": "2.1.0"},
    ]
    assert mw.previous_versions("Bump the group", "Updates `a` from 1.0.0 to 1.0.1\nUpdates `b` from 2.0.9 to 2.1.0.\n") == {
        "a": ("1.0.0", "1.0.1"), "b": ("2.0.9", "2.1.0")}


# --------------------------------------------------------------------------------- the run
def test_merges_a_clean_green_security_pr_and_dispatches_one_deploy() -> None:
    api, clock = FakeGitHub(), Clock(OPEN)
    api.deployed(MAIN)
    api.alerts = [_alert()]
    api.add(_dependabot_pull(447))
    report = _window(api, clock).run()

    assert _actions(report) == {447: ("merged", f"squash do head {'0' * 7}")}
    merges = [write for write in api.writes if write[1].endswith("/merge")]
    assert merges == [("PUT", "/pulls/447/merge", {"sha": f"{447:040d}", "merge_method": "squash"})]
    dispatches = [write[2] for write in api.writes if write[1].endswith("/dispatches")]
    assert dispatches == [{"ref": "main", "inputs": {"ref": api.main, "deploy": "true", "remediation": "false"}}]
    assert report.deploy.startswith(f"concluído para `{api.main[:7]}`")


def test_dry_run_writes_nothing() -> None:
    api, clock = FakeGitHub(), Clock(OPEN)
    api.deployed(MAIN)
    api.alerts = [_alert()]
    api.add(_dependabot_pull(447))
    api.add(_dependabot_pull(448, sha="8" * 40), state="behind")
    report = _window(api, clock, live=False).run()
    assert api.writes == []
    assert _actions(report) == {447: ("would-merge", "seria mesclada (squash)"),
                                448: ("would-update", "atrás da main: seria atualizada e validada")}
    assert not report.worth_posting()


def test_closed_window_skips_every_candidate_and_never_writes() -> None:
    api, clock = FakeGitHub(), Clock(datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc))  # 12:00 BRT
    api.deployed(MAIN)
    api.alerts = [_alert()]
    api.add(_dependabot_pull(447))
    report = _window(api, clock).run()
    assert api.writes == []
    assert report.gate is not None and "pregão B3/EUA" in report.gate
    assert _actions(report)[447][0] == "skipped"
    assert clock.now == datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)  # no wait: the window is hours away


def test_us_winter_close_waits_inside_the_bound_then_merges() -> None:
    api, clock = FakeGitHub(), Clock(datetime(2026, 11, 3, 21, 0, 30, tzinfo=timezone.utc))  # 16:00 EST
    api.deployed(MAIN)
    api.alerts = [_alert()]
    api.add(_dependabot_pull(447))
    report = _window(api, clock).run()
    assert _actions(report)[447][0] == "merged"
    assert clock.now >= datetime(2026, 11, 3, 21, 15, tzinfo=timezone.utc)


def test_nothing_to_do_never_waits_and_never_posts() -> None:
    api, clock = FakeGitHub(), Clock(datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc))
    api.deployed(MAIN)
    api.active[mw.PIPELINE] = 1
    report = _window(api, clock).run()
    assert (report.gate, report.deploy, report.outcomes) == (None, "não necessário", [])
    assert clock.now == datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc) and api.writes == []
    assert not report.worth_posting()


def test_a_busy_pipeline_is_waited_for_a_bounded_time() -> None:
    api, clock = FakeGitHub(), Clock(OPEN)
    api.deployed(MAIN)
    api.alerts = [_alert()]
    api.active[mw.PIPELINE] = 1
    api.add(_dependabot_pull(447))
    report = _window(api, clock).run()
    assert report.gate == "pipeline de produção ocupado além da espera limitada" and api.writes == []
    assert timedelta(minutes=20) <= clock.now - OPEN <= timedelta(minutes=21)


def test_an_active_pit_backtest_blocks_merges() -> None:
    api, clock = FakeGitHub(), Clock(OPEN)
    api.deployed(MAIN)
    api.alerts = [_alert()]
    api.active[mw.PIT_BACKTEST] = 1
    api.add(_dependabot_pull(447))
    report = _window(api, clock).run()
    assert api.writes == [] and report.gate == "backtest PIT em execução (segura a trava de deploy)"


def test_cap_and_strict_mode_update_validate_then_merge_sequentially() -> None:
    api, clock = FakeGitHub(), Clock(OPEN)
    api.deployed(MAIN)
    api.alerts = [_alert()]
    for number in (447, 448, 449, 452):
        api.add(_dependabot_pull(number, created=f"2026-10-{number - 440:02d}T10:00:00Z"))
    report = _window(api, clock, max_merges=2).run()

    actions = _actions(report)
    assert [actions[number][0] for number in (447, 448, 449, 452)] == ["merged", "merged", "skipped", "skipped"]
    assert actions[449][1] == actions[452][1] == "limite de 2 merges por run"
    kinds = [(method, path.rsplit("/", 1)[-1]) for method, path, _ in api.writes]
    # 447 merges; 448 became BEHIND: update-branch, validation dispatch (deploy=false), merge; one deploy at the end
    assert kinds == [("PUT", "merge"), ("PUT", "update-branch"), ("POST", "dispatches"), ("PUT", "merge"), ("POST", "dispatches")]
    validation = api.writes[2][2]
    assert validation["ref"] == "dependabot/npm_and_yarn/c3po/frontend/left-pad-1.2.4"
    assert validation["inputs"]["deploy"] == "false" and validation["inputs"]["remediation"] == "false"
    assert api.writes[1][2] == {"expected_head_sha": f"{448:040d}"}
    assert api.writes[4][2]["inputs"]["deploy"] == "true" and api.writes[4][2]["inputs"]["ref"] == api.main


def test_behind_pr_whose_validation_does_not_finish_stops_until_next_run() -> None:
    api, clock = FakeGitHub(), Clock(OPEN)
    api.deployed(MAIN)
    api.alerts = [_alert()]
    api.validation_turns_green = False
    api.add(_dependabot_pull(448), state="behind")
    report = _window(api, clock).run()
    action, reason = _actions(report)[448]
    assert action == "updated" and "próximo run" in reason
    assert not any(path.endswith("/merge") for _, path, _ in api.writes)
    assert report.deploy == "não necessário"


def test_a_window_that_closes_mid_run_stops_the_remaining_merges() -> None:
    api, clock = FakeGitHub(), Clock(datetime(2026, 10, 21, 1, 40, tzinfo=timezone.utc))  # 22:40 BRT
    api.deployed(MAIN)
    api.alerts = [_alert()]
    api.add(_dependabot_pull(447))
    api.add(_dependabot_pull(448, created="2026-10-09T10:00:00Z"), state="behind")
    original = api.request

    def slow_request(method: str, path: str, body: Any = None) -> Any:
        result = original(method, path, body)
        if path.endswith("/merge"):
            clock.sleep(10 * 60)  # the clock reaches 22:50 BRT: the next deploy would reach 23:30
        return result

    api.request = slow_request  # type: ignore[method-assign]
    report = _window(api, clock).run()
    actions = _actions(report)
    assert actions[447][0] == "merged"
    assert actions[448][0] == "skipped" and "o deploy de até 45 min" in actions[448][1]
    assert "não disparado" in report.deploy  # the deploy also waits for the next run


def test_container_lane_merges_only_with_the_proof_on_the_exact_head() -> None:
    api, clock = FakeGitHub(), Clock(OPEN)
    api.deployed(MAIN)
    api.add(_lane_pull(446), checks=_green(f"{446:040d}"))  # no Security remediation proof
    report = _window(api, clock).run()
    assert _actions(report)[446][0] == "skipped" and mw.PROOF_CHECK in _actions(report)[446][1]
    assert api.writes == []

    api2 = FakeGitHub()
    api2.deployed(MAIN)
    api2.add(_lane_pull(446))
    assert _actions(_window(api2, Clock(OPEN)).run())[446][0] == "merged"


def test_failed_deploy_of_main_is_retried_by_the_next_run() -> None:
    api, clock = FakeGitHub(), Clock(OPEN)
    run_id = 77
    api.pipeline_runs.append({"id": run_id, "head_sha": MAIN, "event": "push", "status": "completed", "conclusion": "failure"})
    api.jobs[run_id] = [{"name": "Deploy production", "conclusion": "failure"}]  # 120 s lock timeout
    report = _window(api, clock).run()
    assert [write[2]["inputs"] for write in api.writes] == [{"ref": MAIN, "deploy": "true", "remediation": "false"}]
    assert report.deploy.startswith(f"concluído para `{MAIN[:7]}` (main sem deploy concluído: failed)")
    assert report.worth_posting()


def test_hold_label_and_non_security_prs_are_reported_but_untouched() -> None:
    api, clock = FakeGitHub(), Clock(OPEN)
    api.deployed(MAIN)
    api.alerts = [_alert()]
    held = _dependabot_pull(447)
    held["labels"] = [{"name": mw.HOLD_LABEL}]
    api.add(held)
    plain = _dependabot_pull(451, name="other-lib")
    api.add(plain, commits=[_commit(_message("other-lib", "1.2.4"))])
    report = _window(api, clock).run()
    assert api.writes == []
    assert _actions(report) == {447: ("skipped", f"rótulo {mw.HOLD_LABEL}")}
    body = mw.render(report, run_url=RUN_URL, now=clock.now)
    assert "Fora do escopo (sem sinal de segurança): #451" in body


def test_summary_format_and_one_comment_per_brt_day(tmp_path: Path) -> None:
    api, clock = FakeGitHub(), Clock(OPEN)
    api.deployed(MAIN)
    api.alerts = [_alert()]
    api.add(_dependabot_pull(447))
    hostile = _dependabot_pull(453, name="x", new="3.0.0")
    api.add(hostile, commits=[_commit(_message("x", "3.0.0", "version-update:semver-major"))])
    api.alerts.append(_alert(name="x", patched="3.0.0"))
    output, body = tmp_path / "out", tmp_path / "body.md"
    args = ["--repository", REPOSITORY, "--channel-issue", "429", "--run-url", RUN_URL, "--mode", "live",
            "--body", str(body), "--github-output", str(output)]

    assert mw.main(args, api=api, clock=clock, sleep=clock.sleep) == 0
    text = body.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "<!-- c3po-security-merge-window:2026-10-20 -->"
    assert lines[1] == "## Janela de merge de segurança — 20/10/2026 18:05 BRT"
    assert "- Mescladas (squash):" in text and "#447 (dependabot) — left-pad 1.2.3→1.2.4 (patch, GHSA-cfgh-2345-vwxq)" in text
    assert "- Não mescladas:" in text and "#453" in text and "salto major" in text
    assert "- Deploy de produção: concluído para" in text
    assert text.count("<!--") == 1 and "@" not in text
    assert output.read_text(encoding="utf-8") == "post=true\nmerged=1\n"

    # the same BRT day: a second run does not post again
    api.comments = [{"user": {"login": "github-actions[bot]"}, "body": text}]
    api.add(_dependabot_pull(454, sha="9" * 40), state="dirty")
    body.unlink()
    assert mw.main(args, api=api, clock=clock, sleep=clock.sleep) == 0
    assert not body.exists() and output.read_text(encoding="utf-8").endswith("post=false\nmerged=0\n")


def test_unusable_channel_turns_the_run_red(tmp_path: Path) -> None:
    api, clock = FakeGitHub(), Clock(OPEN)
    api.deployed(MAIN)
    api.alerts = [_alert()]
    api.add(_dependabot_pull(447))
    api.channel = {"state": "open", "locked": False, "comments": 2400}
    output = tmp_path / "out"
    code = mw.main(["--repository", REPOSITORY, "--channel-issue", "429", "--run-url", RUN_URL, "--mode", "live",
                    "--body", str(tmp_path / "b.md"), "--github-output", str(output)], api=api, clock=clock, sleep=clock.sleep)
    assert code == 1 and output.read_text(encoding="utf-8").startswith("post=false")


def test_api_errors_never_carry_a_body() -> None:
    error = mw.ApiError("GET", "/dependabot/alerts?state=open&per_page=100", 403)
    assert str(error) == "GitHub API GET /dependabot/alerts returned HTTP 403"
    api, clock = FakeGitHub(), Clock(OPEN)
    api.deployed(MAIN)
    api.alerts = 403
    api.add(_dependabot_pull(447))
    report = _window(api, clock).run()
    assert report.alerts == "alertas Dependabot ilegíveis (HTTP 403)" and api.writes == []


# ------------------------------------------------------------------------------ the workflow
def test_workflow_uses_only_the_token_minimal_permissions_and_no_pr_checkout() -> None:
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    job = workflow["jobs"]["merge-window"]
    assert workflow["permissions"] == {"contents": "read"}
    assert job["permissions"] == {"contents": "write", "pull-requests": "write", "checks": "read",
                                  "vulnerability-alerts": "read", "actions": "write", "issues": "write"}
    assert [entry["cron"] for entry in workflow[True]["schedule"]] == ["0 21 * * 1-5"]
    assert set(workflow[True]) == {"schedule", "workflow_dispatch"}
    assert workflow[True]["workflow_dispatch"]["inputs"]["mode"]["default"] == "dry-run"
    assert "secrets." not in source and "ssh" not in source.lower()  # the triggers are exactly schedule + dispatch (above)
    assert "environment" not in job
    assert job["env"]["MODE"].startswith("${{ (vars.C3PO_SECURITY_MERGE_WINDOW == 'off' && 'dry-run')")
    steps = {step["name"]: step for step in job["steps"]}
    checkout = steps["Check out the merge-window script"]
    assert checkout["with"] == {"persist-credentials": False}
    run = steps["Classify, merge and deploy inside the window"]
    assert run["env"] == {"GH_TOKEN": "${{ github.token }}"} and "--max-merges 3" in run["run"]
    post = steps["Post the daily summary to the Fable-Codex channel"]
    assert post["if"] == "steps.window.outputs.post == 'true'" and 'gh issue comment "$CHANNEL_ISSUE"' in post["run"]
    assert "--admin" not in source and "--force" not in source


def test_the_ops_doc_describes_the_window() -> None:
    doc = DOC_PATH.read_text(encoding="utf-8")
    assert "## Janela de merge de segurança" in doc
    for needle in ("security-merge-window.yml", "C3PO_SECURITY_MERGE_WINDOW", mw.HOLD_LABEL, "23:30", "17:30", "update-branch"):
        assert needle in doc
