#!/usr/bin/env python3
"""Host-owned security scheduler with validated updates and maintenance reboot."""
from __future__ import annotations

import argparse
import base64
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
import sys
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from c3po_dependency_security import ALLOWED, RECEIPT, digest, merge_alerts, normalize_alerts, prepare, validate_candidate
from c3po_container_remediation import validate_report, build_trigger
from c3po_security_reboot import boot_receipt, request_reboot, MARKER
from c3po_security_guard import trial_present

ROOT = Path("/opt/chief-of-staff-digital")
REPO = "duduvcastro/c3po-chief-of-staff-intelligence"
REPORT = "security-automation-report.json"
HOLD = Path("/etc/c3po/security-maintenance.hold")
CONFIG = Path("/etc/c3po/security-automation.json")
REQUIRED_JOBS = {"Sensitive files", "Secret scan", "Backend tests", "Python type check",
                 "Frontend build", "Security remediation proof"}


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

    def request(self, path, method="GET", body=None):
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
        with build_opener(NoRedirect).open(request, timeout=20) as response:
            data = response.read()
        return json.loads(data) if data else None

    def pages(self, path, key=None):
        items = []
        for page in range(1, 21):
            data = self.request(path + ("&" if "?" in path else "?") + f"per_page=100&page={page}")
            chunk = data[key] if key else data
            if not isinstance(chunk, list):
                raise ValueError("Invalid paginated GitHub response")
            items.extend(chunk)
            if len(chunk) < 100:
                return items
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
    # Leave fifteen minutes for boot and recovery before the window closes.
    return maintenance_open(now, config, hold) and now.hour * 60 + now.minute < 705


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


def proof_passed(gh, pr):
    runs = gh.pages("/actions/workflows/c3po-pipeline.yml/runs?event=workflow_dispatch&branch="
                    + pr["head"]["ref"], "workflow_runs")
    exact = sorted((run for run in runs if run["head_sha"] == pr["head"]["sha"]),
                   key=lambda run: run["id"], reverse=True)
    if not exact or exact[0]["conclusion"] != "success":
        return False
    jobs = gh.pages(f"/actions/runs/{exact[0]['id']}/jobs", "jobs")
    return REQUIRED_JOBS <= {job["name"] for job in jobs if job["conclusion"] == "success"}


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
        dependency = pr["head"]["ref"].startswith("automation/dependency-security-")
        container = pr["head"]["ref"].startswith("automation/container-security-rebuild-")
        if (not (dependency or container) or pr["draft"]
                or pr["head"]["repo"]["full_name"] != REPO or pr["user"]["login"] != "github-actions[bot]"):
            continue
        changed = gh.pages(f"/pulls/{pr['number']}/files")
        allowed = ALLOWED if dependency else {"c3po/security/container-rebuild-trigger.json"}
        if any(f["filename"] not in allowed or f["status"] not in ("modified", "added") for f in changed):
            continue
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
                    raise ValueError("Container candidate no longer matches live findings")
        except ValueError:
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
    deployed = (root / ".deploy-version").read_text().strip()
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
    try:
        npm = load_evidence(directory / "repository-npm-advisories.json", now, 26)
        if npm["schema"] != "C3PO_NPM_ADVISORIES-v1" or npm["source_revision"] != main_sha:
            raise ValueError("npm audit does not describe current main")
        alerts = merge_alerts(alerts, npm["alerts"])
    except (ValueError, KeyError, OSError):
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
              "last_dispatch_date": previous.get("last_dispatch_date"),
              "last_dispatched_deploy": previous.get("last_dispatched_deploy"), "status": "observed"}
    report["automatic_reboot"] = config.get("automatic_reboot") is True
    report["reboot"] = reboot
    try:
        watchdog = load_evidence(directory / "security-watchdog-report.json", now, 1)
        if watchdog.get("schema") != "C3PO_SECURITY_WATCHDOG-v1" or watchdog.get("errors"):
            raise ValueError("Watchdog failed")
        report["watchdog"] = {"status": watchdog["status"], "generated_at": watchdog["generated_at"]}
    except (OSError, ValueError, KeyError):
        evidence_errors.append("watchdog_evidence_unavailable")
    # Publish inventory before starting its consumer. A crash cannot masquerade as success.
    write_report(directory / REPORT, report)
    today = now.date().isoformat()
    if now.hour >= 10 and (previous.get("last_dispatch_date") != today
                           or previous.get("last_dispatched_deploy") != deployed):
        gh.request("/actions/workflows/dependency-security.yml/dispatches", "POST", {"ref": "main"})
        gh.request("/actions/workflows/container-vulnerability-scan.yml/dispatches", "POST",
                   {"ref": "main", "inputs": {"controller_dry_run_phase": "none"}})
        report["last_dispatch_date"] = today
        report["last_dispatched_deploy"] = deployed
    if HOLD.exists():
        report["status"] = "maintenance_hold"
    elif MARKER.exists():
        report["status"] = "reboot_requested"
    elif not maintenance_open(now, config, False):
        report["status"] = "waiting_maintenance_window"
    elif evidence_errors:
        report["status"] = "blocked_missing_evidence"
    elif not healthy_host(root):
        report["status"] = "blocked_unhealthy_host"
    else:
        may_write = lambda: maintenance_open(datetime.now(timezone.utc), config, HOLD.exists()) and healthy_host(root)
        # Finish already installed OS updates before starting another application deploy.
        if report["reboot_required"] is True and deployed == main_sha:
            report["reboot_action"] = request_reboot(root, gh, config, now, command=command,
                healthy=healthy_host, write=write_report,
                allowed=lambda: reboot_window_open(datetime.now(timezone.utc), config, HOLD.exists()))
            report["status"] = "reboot_" + report["reboot_action"]
        else:
            report["status"], report["pull_request"] = promote(
                gh, alerts, deployed, images, may_write=may_write)
    # No "resolved" state until fresh scanners and application health prove it.
    report["healthy"] = (deployed == main_sha and not evidence_errors and not alerts and report["security_pending"] == 0
                         and report["reboot_required"] is False and images.get("scan_status") == "complete"
                         and images.get("errors") == [] and images.get("finding_total") == 0
                         and datetime.fromisoformat(images["generated_at"]).timestamp() >= (root / ".deploy-version").stat().st_mtime
                         and healthy_host(root))
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
            report = {**previous, "schema": "C3PO_SECURITY_AUTOMATION-v1", "generated_at": now.isoformat(),
                      "healthy": False, "status": "failed",
                      "errors": [type(exc).__name__ + (f":{exc.code}" if isinstance(exc, HTTPError) else "")]}
            write_report(path, report)
            raise SystemExit("Security automation failed; see sanitized report") from None
        write_report(path, report)
        print(json.dumps({"status": report["status"], "healthy": report["healthy"]}))


if __name__ == "__main__":
    main()
