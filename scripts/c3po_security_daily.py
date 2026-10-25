#!/usr/bin/env python3
"""Host-owned security scheduler with validated updates and maintenance reboot."""
from __future__ import annotations

import argparse
import base64
import fcntl
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import sys
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit

from c3po_dependency_security import ALLOWED, RECEIPT, digest, merge_alerts, normalize_alerts, prepare, validate_candidate
from c3po_container_remediation import validate_report, build_trigger
from c3po_security_reboot import boot_receipt, request_reboot, MARKER
from c3po_security_guard import trial_present

ROOT = Path("/opt/chief-of-staff-digital")
REPO = "duduvcastro/c3po-chief-of-staff-intelligence"
REPO_ID = 1336399383
REPORT = "security-automation-report.json"
HOLD = Path("/etc/c3po/security-maintenance.hold")
CONFIG = Path("/etc/c3po/security-automation.json")
ESCALATION_WORKFLOW = "incident-escalation.yml"
REQUIRED_JOBS = {"Sensitive files", "Secret scan", "Backend tests", "Python type check",
                 "Frontend build", "Security remediation proof"}
CI_APPROVAL_WORKFLOWS = {"c3po-pipeline.yml", "backend-postgres.yml"}
CI_APPROVAL_HISTORY_LIMIT = 100
# Bounded wait, from the first cycle whose npm audit lagged main (at least two
# further hourly cycles); afterwards the lag is an error again.
NPM_REVISION_GRACE = timedelta(hours=3)


def command(args):
    # Never return subprocess output in exceptions: Docker/HTTP errors can contain secrets.
    result = subprocess.run(args, capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError("Local command failed: " + args[0])
    return result.stdout.strip()


def github_token(root):
    api = command(["docker", "compose", "--env-file", str(root / ".env"),
                   "-f", str(root / "c3po/compose.yml"), "ps", "-q", "api"])
    if not api or "\n" in api:
        raise RuntimeError("API container identity unavailable")
    return command(["docker", "exec", "-w", "/app", api, "python3", "-B", "-c",
                    "from app.config import get_settings; print(get_settings().github_governance_token or '')"])


class GitHub:
    def __init__(self, token):
        if not token:
            raise RuntimeError("GitHub security automation credential unavailable")
        self.token = token

    def request(self, path, method="GET", body=None, *, with_links=False):
        if not path.startswith("/") or ".." in path:
            raise ValueError("Invalid GitHub endpoint")
        request = Request("https://api.github.com/repos/" + REPO + path,
                          data=json.dumps(body).encode() if body is not None else None,
                          method=method, headers={"Authorization": "Bearer " + self.token,
                          "Accept": "application/vnd.github+json", "Content-Type": "application/json",
                          "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "C3PO-Security-Daily/1"})
        # Only fixed API endpoints; do not follow credential-bearing redirects.
        from urllib.request import HTTPRedirectHandler, build_opener
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        approval_request = method == "POST" and re.fullmatch(r"/actions/runs/[1-9][0-9]*/approve", path) is not None
        with build_opener(NoRedirect).open(request, timeout=20) as response:
            if approval_request and response.status != 201:
                raise ValueError("Unexpected CI approval HTTP status")
            data = response.read()
            if approval_request and data:
                raise ValueError("Unexpected CI approval response body")
            links = response.headers.get("Link", "")
        result = json.loads(data) if data else None
        return (result, links) if with_links else result

    def pages(self, path, key=None):
        items = []
        resource_path = path.split("?")[0]
        endpoints = {"/repos/" + REPO + resource_path, f"/repositories/{REPO_ID}" + resource_path}
        next_path = path + ("&" if "?" in path else "?") + "per_page=100"
        for _ in range(20):
            # Dependabot requires cursor pagination; numbered page= is rejected.
            data, links = self.request(next_path, with_links=True)
            chunk = data[key] if key else data
            if not isinstance(chunk, list):
                raise ValueError("Invalid paginated GitHub response")
            items.extend(chunk)
            next_url = next((url for url, rel in re.findall(r'<([^>]+)>;\s*rel="([^"]+)"', links) if rel == "next"), None)
            if not next_url:
                return items
            parsed = urlsplit(next_url)
            if parsed.scheme != "https" or parsed.netloc != "api.github.com" or parsed.path not in endpoints or parsed.fragment:
                raise ValueError("Untrusted GitHub pagination target")
            next_path = resource_path + "?" + parsed.query
        raise RuntimeError("GitHub pagination limit exceeded")

    def file(self, path, ref):
        return base64.b64decode(self.request(f"/contents/{path}?ref={ref}")["content"]).decode()


def healthy_host(root):
    ids = command(["docker", "compose", "--env-file", str(root / ".env"),
                   "-f", str(root / "c3po/compose.yml"), "ps", "-q", "api", "web", "db"]).splitlines()
    if len(ids) != 3:
        return False
    states = json.loads(command(["docker", "inspect", *ids]))
    if any(not c["State"]["Running"] or c["State"].get("Health", {}).get("Status", "healthy") != "healthy"
           for c in states):
        return False
    db = next(c["Id"] for c in states if c["Config"]["Labels"].get("com.docker.compose.service") == "db")
    if command(["docker", "exec", db, "psql", "-U", "c3po", "-d", "c3po", "-At", "-c", "SELECT 1"]) != "1":
        return False
    with urlopen("http://127.0.0.1:8081/", timeout=10) as response:
        if response.status != 200:
            return False
    try:
        with urlopen("http://127.0.0.1:8000/api/v1/health", timeout=10) as response:
            return response.status == 200 and json.load(response).get("status") == "ok"
    except HTTPError as exc:
        # The existing API protects this endpoint. Verify the expected auth boundary;
        # database availability and web response have been checked independently above.
        return exc.code == 401 and json.load(exc).get("detail") == "Authentication required"


def load_evidence(path, now, max_hours):
    report = json.loads(path.read_text())
    seal = report.pop("report_sha256")
    if digest(report) != seal:
        raise ValueError("Security evidence hash mismatch")
    timestamp = datetime.fromisoformat(report["generated_at"])
    if timestamp.tzinfo is None or not -timedelta(minutes=5) <= now - timestamp <= timedelta(hours=max_hours):
        raise ValueError("Security evidence stale or dated in the future")
    report["report_sha256"] = seal
    return report


def write_report(path, report):
    report = {k: v for k, v in report.items() if k != "report_sha256"}
    report["report_sha256"] = digest(report)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as handle:
        json.dump(report, handle, sort_keys=True, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(handle.name, 0o644)
    os.replace(handle.name, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def maintenance_open(now, config, hold):
    return not hold and config.get("automatic_merge") is True and 10 <= now.hour < 12 and not trial_present(now)


def reboot_window_open(now, config, hold):
    # Reboot is independent of merge scheduling. Keep business-session hours
    # protected; weekends/off-hours require the same atomic drain and trial veto.
    minutes = now.hour * 60 + now.minute
    outside_session = now.weekday() >= 5 or minutes < 13 * 60 or minutes >= 21 * 60 + 30
    return (not hold and config.get("automatic_reboot") is True
            and outside_session and not trial_present(now))


def ensure_workflows(gh, hold):
    for workflow in ("dependency-security.yml", "container-vulnerability-scan.yml", "security-watchdog.yml"):
        path = "/actions/workflows/" + workflow
        state = gh.request(path)["state"]
        # Public-repository scheduled workflows can be disabled for inactivity.
        # Restore that platform suspension; preserve explicit operator suspension.
        if state == "disabled_inactivity" and not hold:
            gh.request(path + "/enable", "PUT")
        elif state != "active" and not hold:
            raise RuntimeError("Security workflow explicitly disabled: " + workflow)


def escalation_workflow_errors(gh, hold):
    """The >24h escalation channel is observability, never a security gate.

    Its state and latest main-branch result are reported only under
    ``escalation_errors``: they never enter ``errors`` (which the watchdog's
    --verify-daily treats as a failed day, which in turn vetoes merge and
    reboot), and no 404, transient HTTP error or malformed payload here can
    stop the cycle. An inactivity suspension is restored like the other
    security workflows; any other non-active state is only reported."""
    path = "/actions/workflows/" + ESCALATION_WORKFLOW
    try:
        state = gh.request(path)["state"]
        if state == "disabled_inactivity" and not hold:
            gh.request(path + "/enable", "PUT")
        elif state != "active":
            return [ESCALATION_WORKFLOW + ":state:" + str(state)]
        runs = gh.request(path + "/runs?per_page=1&branch=main")["workflow_runs"]
        if runs and runs[0]["status"] == "completed" and runs[0]["conclusion"] not in ("success", "skipped"):
            return [ESCALATION_WORKFLOW + ":" + str(runs[0]["conclusion"])]
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        # Never include exception text (URLs or response bodies may carry secrets).
        return [ESCALATION_WORKFLOW + ":" + type(exc).__name__
                + (f":{exc.code}" if isinstance(exc, HTTPError) else "")]
    return []


def proof_passed(gh, pr, *, verify_attempt=False):
    runs = gh.pages("/actions/workflows/c3po-pipeline.yml/runs?event=workflow_dispatch&branch="
                    + pr["head"]["ref"] + "&head_sha=" + pr["head"]["sha"], "workflow_runs")
    exact = sorted((run for run in runs if run["head_sha"] == pr["head"]["sha"]),
                   key=lambda run: run["id"], reverse=True)
    if not exact or exact[0]["conclusion"] != "success":
        return False
    run = exact[0]
    if verify_attempt:
        _approval_identity(run)
        if (run.get("status") != "completed" or run.get("event") != "workflow_dispatch"
                or run.get("head_branch") != pr["head"]["ref"]):
            return False
        jobs_path = f"/actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs"
    else:
        jobs_path = f"/actions/runs/{run['id']}/jobs"
    jobs = gh.pages(jobs_path, "jobs")
    if not REQUIRED_JOBS <= {job["name"] for job in jobs if job["conclusion"] == "success"}:
        return False
    if verify_attempt:
        if any(job.get("run_id") != run["id"] or job.get("head_sha") != pr["head"]["sha"]
               or job.get("status") != "completed" for job in jobs):
            return False
        latest = gh.request(f"/actions/runs/{run['id']}")
        return (_approval_identity(latest) == _approval_identity(run)
                and latest.get("status") == "completed" and latest.get("conclusion") == "success")
    return True


def validated_candidate(gh, pr, main, alerts, images):
    """Share the existing content gates between promotion and CI approval."""
    dependency = pr["head"]["ref"].startswith("automation/dependency-security-")
    container = pr["head"]["ref"].startswith("automation/container-security-rebuild-")
    if (not (dependency or container) or pr["draft"]
            or pr["head"]["repo"]["full_name"] != REPO or pr["user"]["login"] != "github-actions[bot]"):
        return False
    changed = gh.pages(f"/pulls/{pr['number']}/files")
    allowed = ALLOWED if dependency else {"c3po/security/container-rebuild-trigger.json"}
    if not changed or any(f["filename"] not in allowed or f["status"] not in ("modified", "added") for f in changed):
        return False
    head = {f["filename"]: gh.file(f["filename"], pr["head"]["sha"]) for f in changed}
    try:
        if dependency:
            base = {path: gh.file(path, main) for path in ALLOWED - {RECEIPT}}
            validate_candidate(base, head, alerts, main)
        else:
            trigger = json.loads(head["c3po/security/container-rebuild-trigger.json"])
            counts, findings = validate_report(images)
            expected = build_trigger(images, counts=counts, findings=findings,
                                     run_url=trigger["run_url"], artifact_name=trigger["artifact_name"], dry_run=False)
            if (not findings or trigger.get("dry_run") is not False or trigger.get("source_revision") != main
                    or any(trigger.get(key) != expected[key] for key in
                           ("schema", "remediation_key", "evidence_scope", "fix_available", "finding_total", "findings"))):
                return False
    except ValueError:
        return False
    return True


def _approval_pr(pr):
    return (pr.get("state") == "open" and pr.get("draft") is False
            and pr.get("user", {}).get("login") == "github-actions[bot]"
            and pr.get("base", {}).get("ref") == "main"
            and pr.get("base", {}).get("repo", {}).get("id") == REPO_ID
            and pr.get("head", {}).get("repo", {}).get("id") == REPO_ID
            and pr.get("head", {}).get("repo", {}).get("full_name") == REPO
            and re.fullmatch(r"automation/(dependency-security|container-security-rebuild)-[A-Za-z0-9._-]+",
                             str(pr.get("head", {}).get("ref", ""))) is not None
            and re.fullmatch(r"[0-9a-f]{40}", str(pr.get("head", {}).get("sha", ""))) is not None)


def _approval_identity(run):
    run_id, attempt, sha = run.get("id"), run.get("run_attempt"), run.get("head_sha")
    if (type(run_id) is not int or run_id <= 0 or type(attempt) is not int or attempt <= 0
            or re.fullmatch(r"[0-9a-f]{40}", str(sha)) is None):
        raise ValueError("Invalid CI run identity")
    return run_id, attempt, sha


def _requires_approval(run):
    # GitHub's REST filter accepts action_required, but the run is normally
    # status=completed, conclusion=action_required (not status=action_required).
    return run.get("conclusion") == "action_required" or run.get("status") == "action_required"


def _approval_run(gh, run, pr, workflow, *, require_approval=True):
    _approval_identity(run)
    links = run.get("pull_requests")
    matches = (run.get("event") == "pull_request" and (not require_approval or _requires_approval(run))
            and run.get("workflow_id") == workflow["id"]
            and run.get("path") == workflow["path"]
            and run.get("head_sha") == pr["head"]["sha"]
            and run.get("head_branch") == pr["head"]["ref"]
            and run.get("repository", {}).get("id") == REPO_ID
            and run.get("head_repository", {}).get("id") == REPO_ID)
    if not matches or not isinstance(links, list):
        return False
    if not links:
        # Bot-created PR runs may omit pull_requests even when GitHub's commit
        # association identifies the PR. Never infer ownership from branch alone.
        associated = gh.pages(f"/commits/{pr['head']['sha']}/pulls")
        return (len(associated) == 1 and _approval_pr(associated[0])
                and associated[0]["number"] == pr["number"]
                and associated[0]["head"]["sha"] == pr["head"]["sha"]
                and associated[0]["head"]["ref"] == pr["head"]["ref"])
    return (len(links) == 1
            and links[0].get("number") == pr["number"]
            and links[0].get("head", {}).get("sha") == pr["head"]["sha"]
            and links[0].get("head", {}).get("repo", {}).get("id") == REPO_ID
            and links[0].get("base", {}).get("ref") == "main"
            and links[0].get("base", {}).get("repo", {}).get("id") == REPO_ID)


def _replacement_ci_run(gh, run, pr):
    path = run.get("path")
    if not _approval_pr(pr) or path not in {".github/workflows/" + name for name in CI_APPROVAL_WORKFLOWS}:
        return None
    runs = gh.pages("/actions/workflows/" + path.rsplit("/", 1)[1]
                    + "/runs?event=pull_request&branch=" + quote(pr["head"]["ref"], safe="")
                    + "&head_sha=" + pr["head"]["sha"], "workflow_runs")
    newer = [r for r in runs if type(r.get("id")) is int and r["id"] > run["id"]
             and r.get("head_sha") == pr["head"]["sha"]]
    if not newer:
        return None
    latest = gh.request(f"/actions/runs/{max(newer, key=lambda r: r['id'])['id']}")
    if (_approval_run(gh, latest, pr, {"id": run["workflow_id"], "path": path}, require_approval=False)
            and latest.get("status") == "completed"
            and latest.get("conclusion") in ("success", "action_required")):
        return latest["id"]
    return None


def reconcile_ci_approvals(gh, history):
    """Read only: an interrupted/ambiguous POST is never automatically resent."""
    errors, pending = [], []
    for entry in history:
        if entry["state"] in ("observed", "superseded", "retired", "not_sent"):
            continue
        current = gh.request(f"/pulls/{entry['pull_request']}")
        if current.get("number") != entry["pull_request"]:
            raise ValueError("CI approval PR identity changed")
        if current.get("state") == "closed":
            entry.update(state="retired", retired_reason="pull_request_closed")
            continue
        current_sha = current.get("head", {}).get("sha")
        if (re.fullmatch(r"[0-9a-f]{40}", str(current_sha)) is not None
                and current_sha != entry["head_sha"]):
            entry.update(state="retired", retired_reason="head_changed")
            continue
        run = gh.request(f"/actions/runs/{entry['run_id']}")
        run_id, attempt, sha = _approval_identity(run)
        if run_id != entry["run_id"] or sha != entry["head_sha"]:
            raise ValueError("CI approval reconciliation identity changed")
        replacement = _replacement_ci_run(gh, run, current)
        if replacement is not None:
            entry.update(state="retired", retired_reason="newer_run", replacement_run_id=replacement,
                         observed_status=run.get("status"), observed_conclusion=run.get("conclusion"))
            continue
        if attempt > entry["run_attempt"] and _requires_approval(run):
            entry["state"] = "superseded"
        elif attempt < entry["run_attempt"]:
            raise ValueError("CI approval attempt moved backwards")
        elif not _requires_approval(run):
            if run.get("status") not in ("queued", "requested", "pending", "waiting", "in_progress", "completed"):
                raise ValueError("Unknown CI approval outcome")
            entry["observed_status"] = run["status"]
            entry["observed_conclusion"] = run.get("conclusion")
            entry["observed_attempt"] = attempt
            if run["status"] == "completed":
                if run.get("conclusion") != "success":
                    errors.append("ci_approval:run_not_successful")
                else:
                    entry["state"] = "observed" if attempt == entry["run_attempt"] else "superseded"
            else:
                pending.append("ci_approval_pending")
        elif entry["state"] == "accepted":
            pending.append("ci_approval_pending")
        else:
            errors.append("ci_approval:outcome_unconfirmed")
    return errors, pending


def approve_ci(gh, alerts, deployed_sha, images, history, now, checkpoint, may_write=lambda: False,
               *, window_open=lambda: False):
    """At most one narrowly scoped approval request; never merge or dispatch.

    The durable intent precedes POST. A crash or unknown HTTP outcome requires
    GET reconciliation, never a second POST for the same run/attempt/SHA.
    """
    main = gh.request("/git/ref/heads/main")["object"]["sha"]
    if main != deployed_sha:
        return "waiting_main_deploy", None, []
    for pr in gh.pages("/pulls?state=open&base=main"):
        if not _approval_pr(pr) or not validated_candidate(gh, pr, main, alerts, images):
            continue
        for filename in sorted(CI_APPROVAL_WORKFLOWS):
            workflow = gh.request("/actions/workflows/" + filename)
            if (workflow.get("state") != "active" or type(workflow.get("id")) is not int
                    or workflow.get("path") != ".github/workflows/" + filename):
                return "blocked_ci_approval", pr["number"], ["ci_approval:untrusted_workflow"]
            query = ("/actions/workflows/" + filename + "/runs?event=pull_request&status=action_required&branch="
                     + quote(pr["head"]["ref"], safe="") + "&head_sha=" + pr["head"]["sha"])
            for run in gh.pages(query, "workflow_runs"):
                if not _approval_run(gh, run, pr, workflow):
                    continue
                identity = _approval_identity(run)
                receipts = [e for e in history if (e["run_id"], e["run_attempt"], e["head_sha"]) == identity]
                if any(e["state"] in ("retired", "superseded") for e in receipts):
                    continue
                if any(e["state"] != "not_sent" for e in receipts):
                    return "waiting_ci_approval", pr["number"], []
                if not proof_passed(gh, pr, verify_attempt=True):
                    return "waiting_security_tests", pr["number"], []
                current = gh.request(f"/pulls/{pr['number']}")
                if (not _approval_pr(current) or current["head"]["sha"] != pr["head"]["sha"]
                        or current["head"]["ref"] != pr["head"]["ref"]
                        or not validated_candidate(gh, current, main, alerts, images)
                        or not proof_passed(gh, current, verify_attempt=True)):
                    return "waiting_ci_approval", pr["number"], []
                if len(history) >= CI_APPROVAL_HISTORY_LIMIT:
                    return "blocked_ci_approval", pr["number"], ["ci_approval:history_full"]
                history[:] = [e for e in history if (e["run_id"], e["run_attempt"], e["head_sha"]) != identity
                              or e["state"] != "not_sent"]
                entry = {"run_id": identity[0], "run_attempt": identity[1], "head_sha": identity[2],
                         "pull_request": pr["number"], "requested_at": now.isoformat(), "state": "intent",
                         "post_outcome": "unconfirmed"}
                history.append(entry)
                checkpoint()
                # Finish slow proof/health reads before the last mutable PR,
                # run and baseline reads. The final window check has no probe.
                ready = proof_passed(gh, current, verify_attempt=True) and may_write()
                latest = gh.request(f"/actions/runs/{identity[0]}")
                bound = _approval_identity(latest) == identity and _approval_run(gh, latest, pr, workflow)
                baseline = gh.request("/git/ref/heads/main")["object"]["sha"]
                current = gh.request(f"/pulls/{pr['number']}")
                if (not ready or not bound or baseline != main or not _approval_pr(current)
                        or current["head"]["sha"] != identity[2] or current["head"]["ref"] != pr["head"]["ref"]
                        or not window_open()):
                    entry["state"] = "not_sent"
                    checkpoint()
                    return "baseline_changed_or_hold", pr["number"], []
                try:
                    result = gh.request(f"/actions/runs/{identity[0]}/approve", "POST")
                    # The documented 201 has no body. Unexpected payloads are
                    # not evidence that this approval took effect.
                    entry["state"] = "accepted" if result is None else "unknown"
                except (OSError, ValueError, TypeError) as exc:
                    entry["state"] = "unknown"
                    entry["error"] = type(exc).__name__ + (f":{exc.code}" if isinstance(exc, HTTPError) else "")
                entry["post_outcome"] = entry["state"]
                checkpoint()
                errors = [] if entry["state"] == "accepted" else ["ci_approval:outcome_unconfirmed"]
                return "waiting_ci_approval" if not errors else "blocked_ci_approval", pr["number"], errors
    return "idle", None, []


def ci_approval_history(previous):
    stored = previous.get("ci_approval", {}).get("history", [])
    if not isinstance(stored, list) or len(stored) > CI_APPROVAL_HISTORY_LIMIT:
        raise ValueError("Invalid CI approval history")
    history = []
    for entry in stored:
        if (not isinstance(entry, dict) or entry.get("state") not in
                {"intent", "accepted", "unknown", "observed", "superseded", "retired", "not_sent"}
                or type(entry.get("pull_request")) is not int or entry["pull_request"] <= 0):
            raise ValueError("Invalid CI approval receipt")
        _approval_identity({"id": entry.get("run_id"), "run_attempt": entry.get("run_attempt"),
                            "head_sha": entry.get("head_sha")})
        history.append(dict(entry))
    return history


def promote(gh, alerts, deployed_sha, images, may_write=lambda: False):
    main = gh.request("/git/ref/heads/main")["object"]["sha"]
    if deployed_sha != main:
        return "waiting_main_deploy", None
    protection = gh.request("/branches/main/protection")
    required = protection.get("required_status_checks") or {}
    contexts = set(required.get("contexts") or []) | {c["context"] for c in required.get("checks") or []}
    if (protection.get("enforce_admins", {}).get("enabled") is not True
            or required.get("strict") is not True or not REQUIRED_JOBS - {"Security remediation proof"} <= contexts):
        return "blocked_branch_protection", None
    for state in ("queued", "in_progress", "waiting", "requested", "pending"):
        if gh.pages("/actions/workflows/c3po-pipeline.yml/runs?status=" + state, "workflow_runs"):
            return "waiting_pipeline", None
    prs = gh.pages("/pulls?state=open&base=main")
    for pr in prs:
        if not validated_candidate(gh, pr, main, alerts, images):
            continue
        if not proof_passed(gh, pr):
            return "waiting_security_tests", pr["number"]
        # GitHub's strict branch checks remain authoritative; never use an admin bypass.
        detail = gh.request(f"/pulls/{pr['number']}")
        if detail["head"]["sha"] != pr["head"]["sha"] or detail["mergeable_state"] != "clean":
            return "waiting_branch_rules", pr["number"]
        if gh.request("/git/ref/heads/main")["object"]["sha"] != main or not may_write():
            return "baseline_changed_or_hold", pr["number"]
        result = gh.request(f"/pulls/{pr['number']}/merge", "PUT",
                            {"sha": pr["head"]["sha"], "merge_method": "squash"})
        if result.get("merged") is not True:
            raise RuntimeError("Security merge not confirmed")
        # The host PAT merge emits the normal push event. Do NOT dispatch a second deploy.
        return "merged_waiting_deploy_and_rescan", pr["number"]
    return "no_validated_candidate", None


def cycle(root, gh, now, config, previous):
    directory = root / "runtime/security"
    reboot = boot_receipt(root, write_report, healthy_host, now, command=command)
    alerts = normalize_alerts(gh.pages("/dependabot/alerts?state=open"))
    evidence_errors = []
    try:
        os_report = load_evidence(directory / "host-os-vulnerability-report.json", now, 2)
        if (os_report["schema"] != "C3PO_HOST_OS_VULNERABILITY_REPORT-v1"
                or type(os_report["updates"]["security_pending"]) is not int
                or os_report["updates"]["security_pending"] < 0
                or type(os_report["reboot_required"]) is not bool):
            raise ValueError("Invalid host report")
    except (ValueError, KeyError, OSError):
        os_report = {}
        evidence_errors.append("host_evidence_unavailable")
    try:
        images = load_evidence(directory / "container-production-vulnerability-report.json", now, 36)
        validate_report(images)
    except (ValueError, KeyError, OSError, RuntimeError):
        images = {}
        evidence_errors.append("image_evidence_unavailable")
    marker = root / ".deploy-version"
    deployed = marker.read_text().strip()
    marker_mtime = marker.stat().st_mtime
    # A redeploy of the same revision is still a new deploy to scan.
    deployed_at = datetime.fromtimestamp(marker_mtime, timezone.utc).isoformat()
    main_sha = gh.request("/git/ref/heads/main")["object"]["sha"]
    for workflow in ("dependency-security.yml", "container-vulnerability-scan.yml", "c3po-pipeline.yml"):
        # Checking the most recent result prevents a green inventory from hiding a
        # failed repair job. A pending run is recorded as pending, not successful.
        query = f"/actions/workflows/{workflow}/runs?per_page=1"
        if workflow == "c3po-pipeline.yml":
            query += "&event=push&branch=main"
        runs = gh.request(query)["workflow_runs"]
        if runs and runs[0]["status"] == "completed" and runs[0]["conclusion"] not in ("success", "skipped"):
            evidence_errors.append(workflow + ":" + str(runs[0]["conclusion"]))
    escalation_errors = escalation_workflow_errors(gh, HOLD.exists())
    # First cycle whose npm audit did not describe the then-current main. Kept
    # across further main changes and cleared only by an audit of the current
    # main, so a stuck regeneration cannot stay pending by main moving again.
    # Only a missing/None anchor starts the clock: any other stored value,
    # falsy ones included, is validated below and never silently replaced.
    npm_lag_since = previous.get("npm_lag_since")
    if npm_lag_since is None:
        npm_lag_since = now.isoformat()
    # Start each wait at its first observation. Further merges or redeploys
    # never extend it; only recovery clears an anchor. Preserve malformed and
    # falsy stored values too, so the consumer cannot restart their grace.
    deploy_lag_since = previous.get("deploy_lag_since")
    if deployed == main_sha:
        deploy_lag_since = None
    elif deploy_lag_since is None:
        deploy_lag_since = now.isoformat()
    image_drift_since = previous.get("image_drift_since")
    scanned_at = datetime.fromisoformat(images["generated_at"]).timestamp() if images else None
    if scanned_at is not None:
        if scanned_at >= marker_mtime:
            image_drift_since = None
        elif image_drift_since is None:
            image_drift_since = now.isoformat()
    today = now.date().isoformat()
    # Every deploy is scanned at any hour. Only the daily scan consumes the
    # day's verification, so a night deploy cannot replace the 10 UTC scan.
    daily_due = now.hour >= 10 and previous.get("last_dispatch_date") != today
    post_deploy_due = ((previous.get("last_dispatched_deploy"), previous.get("last_dispatched_deploy_at"))
                       != (deployed, deployed_at))
    scan_due = daily_due or post_deploy_due
    revision_due = previous.get("last_dispatched_main") != main_sha
    pending = []
    try:
        npm = load_evidence(directory / "repository-npm-advisories.json", now, 26)
        if npm["schema"] != "C3PO_NPM_ADVISORIES-v1" or not isinstance(npm["alerts"], list):
            raise ValueError("Invalid npm audit")
        if npm["source_revision"] == main_sha:
            npm_lag_since = None
            alerts = merge_alerts(alerts, npm["alerts"])
        else:
            if not isinstance(npm_lag_since, str):
                raise ValueError("Invalid npm lag anchor")
            # A malformed or naive timestamp raises here and fails closed too.
            lag = now - datetime.fromisoformat(npm_lag_since)
            if (not re.fullmatch(r"[0-9a-f]{40}", str(npm["source_revision"]))
                    or not timedelta(0) <= lag < NPM_REVISION_GRACE
                    or any(error.startswith("dependency-security.yml:") for error in evidence_errors)):
                raise ValueError("npm audit does not describe current main")
            # Fresh, sealed audit of an earlier main while the audit of this one
            # is (re)requested below. Never healthy and every gate stays closed.
            # Its known findings stay visible (and keep their severity) meanwhile.
            alerts = merge_alerts(alerts, npm["alerts"])
            pending.append("npm_evidence_pending")
    except (ValueError, KeyError, OSError, TypeError):
        evidence_errors.append("npm_evidence_unavailable")
    blocked = []
    if alerts:
        _, _, blocked = prepare({p: (root / p).read_text() for p in ALLOWED - {RECEIPT}}, alerts)
    report = {"schema": "C3PO_SECURITY_AUTOMATION-v1", "generated_at": now.isoformat(),
              "alerts": alerts, "unresolved": blocked,
              "security_pending": os_report.get("updates", {}).get("security_pending"),
              "reboot_required": os_report.get("reboot_required"), "deployed_sha": deployed, "main_sha": main_sha,
              "host_report_sha256": os_report.get("report_sha256"),
              "image_report_sha256": images.get("report_sha256"), "errors": evidence_errors,
              # Bounded waits: not errors, but never healthy and never open a gate.
              "pending": pending,
              # Observability only: never part of "errors", "healthy" or any gate.
              "escalation_errors": escalation_errors,
              "last_dispatch_date": previous.get("last_dispatch_date"),
              "last_dispatched_deploy": previous.get("last_dispatched_deploy"),
              "last_dispatched_deploy_at": previous.get("last_dispatched_deploy_at"),
              "last_dispatched_main": previous.get("last_dispatched_main"),
              "deployed_at": deployed_at, "deploy_lag_since": deploy_lag_since,
              "image_drift_since": image_drift_since,
              "npm_lag_since": npm_lag_since, "status": "observed"}
    history = ci_approval_history(previous)
    report["ci_approval"] = {"enabled": config.get("automatic_ci_approval") is True,
                             "status": "idle" if config.get("automatic_ci_approval") is True else "disabled",
                             "history": history}
    report["automatic_reboot"] = config.get("automatic_reboot") is True
    report["reboot"] = reboot
    try:
        watchdog = load_evidence(directory / "security-watchdog-report.json", now, 1)
        if watchdog.get("schema") != "C3PO_SECURITY_WATCHDOG-v1" or watchdog.get("errors"):
            raise ValueError("Watchdog failed")
        report["watchdog"] = {"status": watchdog["status"], "generated_at": watchdog["generated_at"]}
    except (OSError, ValueError, KeyError):
        evidence_errors.append("watchdog_evidence_unavailable")
    try:
        approval_errors, approval_pending = reconcile_ci_approvals(gh, history)
        evidence_errors.extend(approval_errors)
        if approval_errors:
            report["ci_approval"]["status"] = "blocked_ci_approval"
        if approval_pending:
            pending.append("ci_approval_pending")
            report["ci_approval"]["status"] = "waiting_ci_approval"
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report["ci_approval"]["status"] = "blocked_ci_approval"
        evidence_errors.append("ci_approval:reconcile:" + type(exc).__name__
                               + (f":{exc.code}" if isinstance(exc, HTTPError) else ""))
    # Publish inventory before starting its consumer. A crash cannot masquerade as success.
    write_report(directory / REPORT, report)
    dispatch_errors = []
    if scan_due or revision_due:
        try:
            gh.request("/actions/workflows/dependency-security.yml/dispatches", "POST", {"ref": "main"})
            report["last_dispatched_main"] = main_sha
            if scan_due:
                gh.request("/actions/workflows/container-vulnerability-scan.yml/dispatches", "POST",
                           {"ref": "main", "inputs": {"controller_dry_run_phase": "none"}})
                if daily_due:
                    report["last_dispatch_date"] = today
                report["last_dispatched_deploy"] = deployed
                report["last_dispatched_deploy_at"] = deployed_at
        except OSError as exc:
            # A failed scan request remains an operational failure, but does not
            # invalidate independent, fresh evidence for an OS reboot. Never
            # include exception text (URLs or response bodies may carry secrets).
            dispatch_errors.append("scan_dispatch:" + type(exc).__name__
                                   + (f":{exc.code}" if isinstance(exc, HTTPError) else ""))
    if "npm_evidence_pending" in pending and report["last_dispatched_main"] != main_sha:
        # No regeneration requested for this main: the mismatch is today's error.
        pending.remove("npm_evidence_pending")
        evidence_errors.append("npm_evidence_unavailable")
    # Check even when another blocker already closes the gates: a down host
    # must remain visible alongside a transient wait. Never expose probe errors.
    try:
        host_ok = healthy_host(root) is True
    except Exception:
        host_ok = False
    if HOLD.exists():
        report["status"] = "maintenance_hold"
    elif MARKER.exists():
        report["status"] = "reboot_requested"
    elif evidence_errors:
        report["status"] = "blocked_missing_evidence"
    elif pending:
        # Same gates as missing evidence (no promotion, no reboot), not an error.
        report["status"] = "waiting_ci_approval" if "ci_approval_pending" in pending else "waiting_npm_evidence"
    elif not host_ok:
        report["status"] = "blocked_unhealthy_host"
    elif report["reboot_required"] is True and deployed == main_sha:
        report["reboot_action"] = request_reboot(root, gh, config, now, command=command,
            healthy=healthy_host, write=write_report,
            allowed=lambda: reboot_window_open(datetime.now(timezone.utc), config, HOLD.exists()))
        report["status"] = "reboot_" + report["reboot_action"]
    elif not maintenance_open(now, config, False):
        report["status"] = "waiting_maintenance_window"
    elif dispatch_errors:
        report["status"] = "blocked_scan_dispatch"
    else:
        # The probe can take time: check the clock/hold/trial after it, so a
        # probe begun before noon cannot open a write after the window closes.
        may_write = lambda: (healthy_host(root) is True and not MARKER.exists()
                             and maintenance_open(datetime.now(timezone.utc), config, HOLD.exists()))
        approval_status = "idle"
        if report["ci_approval"]["enabled"]:
            approval_status, report["pull_request"], approval_errors = approve_ci(
                gh, alerts, deployed, images, history, now,
                lambda: write_report(directory / REPORT, report), may_write=may_write,
                window_open=lambda: (not MARKER.exists()
                    and maintenance_open(datetime.now(timezone.utc), config, HOLD.exists())))
            report["ci_approval"]["status"] = approval_status
            evidence_errors.extend(approval_errors)
        if approval_status == "idle":
            report["status"], report["pull_request"] = promote(
                gh, alerts, deployed, images, may_write=may_write)
        else:
            report["status"] = approval_status
            if not approval_errors:
                pending.append("ci_approval_pending")
    report["errors"] = evidence_errors + dispatch_errors
    # No "resolved" state until fresh scanners and application health prove it.
    blockers = []
    if deployed != main_sha:
        blockers.append("deploy_lag")
    if report["errors"]:
        blockers.append("errors")
    blockers.extend(pending)
    if alerts:
        blockers.append("alerts")
    if report["security_pending"] != 0:
        blockers.append("os_security_pending")
    if report["reboot_required"] is not False:
        blockers.append("reboot_required")
    if not (images.get("scan_status") == "complete" and images.get("errors") == []
            and images.get("finding_total") == 0):
        blockers.append("image_findings_or_unavailable")
    elif scanned_at is None or scanned_at < marker_mtime:
        blockers.append("image_scan_predates_deploy")
    if not host_ok:
        blockers.append("unhealthy_host")
    report["healthy_blockers"] = blockers
    report["healthy"] = not blockers
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--observe", action="store_true", help="Collect only; never dispatch or merge")
    parser.add_argument("--import-npm", action="store_true", help="Import public npm findings from CI stdin")
    args = parser.parse_args()
    directory = args.root / "runtime/security"
    directory.mkdir(parents=True, exist_ok=True)
    if args.observe:
        gh = GitHub(github_token(args.root))
        print(json.dumps({"alerts": normalize_alerts(gh.pages("/dependabot/alerts?state=open"))}))
        return
    if args.import_npm:
        report = json.load(sys.stdin)
        seal = report.pop("report_sha256")
        if report.get("schema") != "C3PO_NPM_ADVISORIES-v1" or digest(report) != seal:
            raise SystemExit("Invalid npm report")
        write_report(directory / "repository-npm-advisories.json", report)
        return
    with (directory / "security-automation.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = directory / REPORT
        previous = json.loads(path.read_text()) if path.exists() else {}
        now = datetime.now(timezone.utc)
        try:
            gh = GitHub(github_token(args.root))
            config = json.loads(CONFIG.read_text())
            ensure_workflows(gh, HOLD.exists())
            report = cycle(args.root, gh, now, config, previous)
        except Exception as exc:
            # A POST intent may already have been committed by this cycle.
            # Preserve it on any later failure so a restart cannot resend it.
            journal = json.loads(path.read_text()) if path.exists() else previous
            report = {**previous, "schema": "C3PO_SECURITY_AUTOMATION-v1", "generated_at": now.isoformat(),
                      "healthy": False, "healthy_blockers": ["routine_failed"], "status": "failed", "pending": [],
                      "errors": [type(exc).__name__ + (f":{exc.code}" if isinstance(exc, HTTPError) else "")]}
            if "ci_approval" in journal:
                report["ci_approval"] = journal["ci_approval"]
            write_report(path, report)
            raise SystemExit("Security automation failed; see sanitized report") from None
        write_report(path, report)
        print(json.dumps({"status": report["status"], "healthy": report["healthy"]}))


if __name__ == "__main__":
    main()
