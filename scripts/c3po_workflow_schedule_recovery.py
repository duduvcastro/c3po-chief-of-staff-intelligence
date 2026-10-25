#!/usr/bin/env python3
"""Opt-in host safety net for missed GitHub schedules; never run the workloads here.

The hourly timer checks slots aged 20..80 minutes. PIT checks only the most recent
eligible tick, never a backlog. A durable intent is fsynced BEFORE each POST;
uncertain writes are reconciled, never retried blindly. GitHub has no atomic
schedule/dispatch claim: a schedule arriving after the final GET can still race.
Existing workflow concurrency and every PIT guard remain authoritative.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

UTC = timezone.utc
BRT = ZoneInfo("America/Sao_Paulo")
REPO = "duduvcastro/c3po-chief-of-staff-intelligence"
REPO_ID = 1336399383
ISSUE = 429
OPS = "ops-readonly-report.yml"
EXPORT = "decisor-verdict-export.yml"
PIT = "valuation-pit-grid-autopilot.yml"
WORKFLOWS = (OPS, EXPORT, PIT)
MIN_AGE = timedelta(minutes=20)
MAX_AGE = timedelta(minutes=80)
SCHEMA = "C3PO-WORKFLOW-SCHEDULE-RECOVERY-v1"
SLOT_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00Z\Z")
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
STATES = {"dispatch_held", "skipped", "dispatch_intent", "dispatch_unknown", "run_confirmed", "notice_intent", "notice_unknown", "complete"}


class RecoveryError(Exception):
    """Closed failure; only the fixed error code, never an API body, is printed."""


def instant(value: Any) -> datetime:
    if not isinstance(value, str):
        raise RecoveryError("invalid_timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RecoveryError("invalid_timestamp") from error
    if result.tzinfo is None:
        raise RecoveryError("timestamp_without_zone")
    return result.astimezone(UTC)


def stamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise RecoveryError("clock_without_zone")
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class Slot:
    workflow: str
    at: datetime

    @property
    def value(self) -> str:
        return stamp(self.at)

    @property
    def key(self) -> str:
        return f"{self.workflow}:{self.value}"

    @property
    def tag(self) -> str:
        return f"[recovery:{self.value}]"

    @property
    def inputs(self) -> dict[str, str]:
        inputs = {"recovery_slot": self.value}
        if self.workflow == EXPORT:
            # The producer resolves the last CLOSED XNYS session; no host calendar
            # approximation, new dependency, or civil-date subtraction.
            inputs["night"] = ""
        if self.workflow == PIT:
            inputs["dry_run"] = "false"
        return inputs


def slots(now: datetime) -> list[Slot]:
    now = instant(stamp(now))
    found: list[Slot] = []
    local = now.astimezone(BRT)
    for offset in (0, -1):
        day = (local + timedelta(days=offset)).date()
        for hour, minute in ((3, 30), (8, 30)):
            at = datetime(day.year, day.month, day.day, hour, minute, tzinfo=BRT).astimezone(UTC)
            if MIN_AGE <= now - at <= MAX_AGE:
                found.append(Slot(OPS, at))
        if day.weekday() < 5:
            at = datetime(day.year, day.month, day.day, 8, tzinfo=BRT).astimezone(UTC)
            if MIN_AGE <= now - at <= MAX_AGE:
                found.append(Slot(EXPORT, at))
    pit = []
    for offset in range(3):
        hour = (now - timedelta(hours=offset)).replace(minute=0, second=0, microsecond=0)
        for minute in (13, 43):
            at = hour.replace(minute=minute)
            if MIN_AGE <= now - at <= MAX_AGE:
                pit.append(Slot(PIT, at))
    if pit:
        found.append(max(pit, key=lambda value: value.at))
    return found


def validate_slot(workflow: str, value: str) -> Slot:
    if workflow not in WORKFLOWS or SLOT_RE.fullmatch(value) is None:
        raise RecoveryError("invalid_recovery_slot")
    at = instant(value)
    if workflow == PIT:
        valid = at.minute in (13, 43)
    else:
        local = at.astimezone(BRT)
        valid = ((local.hour, local.minute) in ((3, 30), (8, 30)) if workflow == OPS
                 else (local.hour, local.minute) == (8, 0) and local.weekday() < 5)
    if not valid:
        raise RecoveryError("invalid_recovery_slot")
    return Slot(workflow, at)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitHub:
    """Fixed repository/endpoints only, bounded validated Link pagination."""

    def __init__(self, token: str):
        if not token or any(char.isspace() for char in token):
            raise RecoveryError("credential_unavailable")
        self.token = token

    def request(self, path: str, method: str = "GET", body: Any = None, *, links: bool = False) -> Any:
        resource = path.split("?", 1)[0]
        reads = {"/commits/main", f"/issues/{ISSUE}/comments"}
        reads.update(f"/actions/workflows/{name}" + suffix for name in WORKFLOWS for suffix in ("", "/runs"))
        writes = {f"/actions/workflows/{name}/dispatches" for name in WORKFLOWS} | {f"/issues/{ISSUE}/comments"}
        if method not in ("GET", "POST") or resource not in (reads if method == "GET" else writes):
            raise RecoveryError("endpoint_refused")
        req = Request(f"https://api.github.com/repos/{REPO}{path}", method=method,
                      data=None if body is None else json.dumps(body).encode(),
                      headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                               "Content-Type": "application/json", "X-GitHub-Api-Version": "2022-11-28",
                               "User-Agent": "C3PO-Workflow-Schedule-Recovery/1"})
        with build_opener(NoRedirect).open(req, timeout=20) as response:
            data = response.read(8 * 1024 * 1024 + 1)
            if len(data) > 8 * 1024 * 1024:
                raise RecoveryError("api_response_too_large")
            value = json.loads(data) if data else None
            return (value, response.headers.get("Link", "")) if links else value

    def pages(self, path: str, key: str | None = None) -> list[dict[str, Any]]:
        resource = path.split("?", 1)[0]
        allowed = {f"/repos/{REPO}{resource}", f"/repositories/{REPO_ID}{resource}"}
        next_path = path + ("&" if "?" in path else "?") + "per_page=100"
        seen: set[str] = set()
        rows: list[dict[str, Any]] = []
        expected = None
        for _ in range(20):
            if next_path in seen:
                raise RecoveryError("pagination_cycle")
            seen.add(next_path)
            data, link = self.request(next_path, links=True)
            if key is not None:
                if not isinstance(data, dict) or type(data.get("total_count")) is not int or data["total_count"] < 0:
                    raise RecoveryError("invalid_run_listing")
                if expected is None:
                    expected = data["total_count"]
                # GitHub search-filtered run listings are capped at 1,000.
                if data["total_count"] >= 1000:
                    raise RecoveryError("run_listing_capped")
                chunk = data.get(key)
            else:
                chunk = data
            if not isinstance(chunk, list) or not all(isinstance(row, dict) for row in chunk):
                raise RecoveryError("invalid_page")
            rows.extend(chunk)
            matches = re.findall(r'<([^>]+)>;\s*rel="([^"]+)"', link)
            if link and not matches:
                raise RecoveryError("invalid_pagination_link")
            targets = [url for url, rel in matches if rel == "next"]
            if len(targets) > 1:
                raise RecoveryError("invalid_pagination_link")
            if not targets:
                if expected is not None and len(rows) < expected:
                    raise RecoveryError("incomplete_run_listing")
                return rows
            parsed = urlsplit(targets[0])
            if (parsed.scheme != "https" or parsed.netloc != "api.github.com" or parsed.path not in allowed
                    or parsed.fragment or not parsed.query):
                raise RecoveryError("untrusted_pagination_target")
            next_path = resource + "?" + parsed.query
        raise RecoveryError("pagination_limit")


def run_listing(gh: GitHub, slot: Slot, now: datetime) -> list[dict[str, Any]]:
    # Include late schedules/manual recoveries since the target slot, with a
    # bounded 2-day overlap for outstanding (ambiguous) intents after a restart.
    since = min(slot.at, now - timedelta(days=2))
    query = urlencode({"branch": "main", "created": ">=" + stamp(since)})
    rows = gh.pages(f"/actions/workflows/{slot.workflow}/runs?{query}", "workflow_runs")
    seen = set()
    for row in rows:
        if type(row.get("id")) is not int or row["id"] <= 0 or row["id"] in seen:
            raise RecoveryError("invalid_run_identity")
        seen.add(row["id"])
        path = str(row.get("path") or "")
        expected = f".github/workflows/{slot.workflow}"
        if (path != expected and not path.startswith(expected + "@")) or row.get("head_branch") != "main":
            raise RecoveryError("unexpected_run")
        instant(row.get("created_at"))
        if not isinstance(row.get("status"), str) or not isinstance(row.get("display_title"), str):
            raise RecoveryError("invalid_run")
    return rows


def covered(slot: Slot, runs: list[dict[str, Any]], now: datetime) -> bool:
    for run in runs:
        if run.get("status") != "completed":
            return True  # queued/waiting/approval is not a missed schedule
        at, title = instant(run["created_at"]), run["display_title"]
        if run.get("event") not in ("schedule", "workflow_dispatch") or not slot.at <= at <= now:
            continue
        if "[recovery:" in title:
            if slot.tag in title:
                return True
            continue
        if slot.workflow == PIT:
            if at >= slot.at + timedelta(minutes=30):
                continue
            if run["event"] == "workflow_dispatch" and "— act" not in title:
                # A dry-run does not replace an acting schedule; unknown manual
                # inputs are ambiguous and must not invite a second live action.
                if "— dry-run" in title:
                    continue
                raise RecoveryError("ambiguous_manual_tick")
        if slot.workflow == OPS and run["event"] == "schedule" and "[schedule:" in title:
            cron = "30 6 * * *" if slot.at.astimezone(BRT).hour == 3 else "30 11 * * *"
            if f"[schedule:{cron}]" not in title:
                continue
        if slot.workflow == EXPORT and run["event"] == "workflow_dispatch" and "last-completed" not in title:
            raise RecoveryError("ambiguous_export_night")
        return True  # success is deliberately not required: this is no retry engine
    return False


def atomic_write(path: Path, value: Any) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".recovery-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(value, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Ledger:
    """Caller holds the flock for the entire read/decide/write/confirm cycle."""

    def __init__(self, path: Path):
        self.path = path
        if path.is_symlink() or (path.exists() and path.stat().st_size > 8 * 1024 * 1024):
            raise RecoveryError("unsafe_ledger")
        self.data = json.loads(path.read_text()) if path.exists() else {"schema": SCHEMA, "entries": {}}
        if (not isinstance(self.data, dict) or set(self.data) != {"schema", "entries"}
                or self.data["schema"] != SCHEMA or not isinstance(self.data["entries"], dict)
                or len(self.data["entries"]) > 50000):
            raise RecoveryError("invalid_ledger")
        for key, entry in self.entries.items():
            if not isinstance(entry, dict) or entry.get("state") not in STATES:
                raise RecoveryError("invalid_ledger_entry")
            slot = validate_slot(entry.get("workflow"), entry.get("slot"))
            if key != slot.key or SHA_RE.fullmatch(str(entry.get("head_sha"))) is None:
                raise RecoveryError("invalid_ledger_entry")
            instant(entry.get("attempted_at"))
            if type(entry.get("before_id")) is not int or entry["before_id"] < 0:
                raise RecoveryError("invalid_ledger_entry")
            if entry["state"] in {"run_confirmed", "notice_intent", "notice_unknown", "complete"}:
                if type(entry.get("run_id")) is not int or entry["run_id"] <= entry["before_id"]:
                    raise RecoveryError("invalid_ledger_entry")

    @property
    def entries(self) -> dict[str, dict[str, Any]]:
        return self.data["entries"]

    def save(self) -> None:
        atomic_write(self.path, self.data)


def confirm_run(entry: dict[str, Any], slot: Slot, runs: list[dict[str, Any]]) -> bool:
    matching = [run for run in runs if run["id"] > entry["before_id"] and run.get("event") == "workflow_dispatch"
                and slot.tag in run["display_title"] and run.get("head_sha") == entry["head_sha"]
                and instant(run["created_at"]) >= instant(entry["attempted_at"]) - timedelta(seconds=5)]
    if len(matching) > 1:
        raise RecoveryError("multiple_recovery_runs")
    if not matching:
        return False
    entry.update(state="run_confirmed", run_id=matching[0]["id"])
    return True


def notice_body(entry: dict[str, Any], slot: Slot) -> str:
    run_id = entry["run_id"]
    return (f"<!-- c3po-workflow-recovery:{slot.key}:{run_id} -->\n"
            f"Recuperação de agendamento `{slot.workflow}`, slot `{slot.value}`: "
            f"[run {run_id}](https://github.com/{REPO}/actions/runs/{run_id}) confirmado; "
            "despacho de recuperação registrado, resultado do workflow ainda deve ser conferido.")


def publish_notice(gh: GitHub, ledger: Ledger, entry: dict[str, Any], slot: Slot, *, may_write=lambda: True) -> None:
    body = notice_body(entry, slot)
    comments = gh.pages(f"/issues/{ISSUE}/comments?" + urlencode({"since": entry["attempted_at"]}))
    matches = [comment for comment in comments if comment.get("body") == body]
    if len(matches) == 1 and type(matches[0].get("id")) is int:
        entry.update(state="complete", comment_id=matches[0]["id"])
        ledger.save()
        return
    if matches:
        raise RecoveryError("multiple_recovery_notices")
    if entry["state"] in {"notice_intent", "notice_unknown"}:
        raise RecoveryError("notice_outcome_unknown")
    if not may_write():
        return
    entry["state"] = "notice_intent"
    ledger.save()
    if not may_write():
        # We know no POST was attempted; unlike a lost response this can resume.
        entry["state"] = "run_confirmed"
        ledger.save()
        return
    try:
        result = gh.request(f"/issues/{ISSUE}/comments", "POST", {"body": body})
        if not isinstance(result, dict) or type(result.get("id")) is not int or result.get("body") != body:
            raise RecoveryError("notice_not_confirmed")
        # Confirm by a separate complete GET, including after a successful POST.
        comments = gh.pages(f"/issues/{ISSUE}/comments?" + urlencode({"since": entry["attempted_at"]}))
        if not any(comment.get("id") == result["id"] and comment.get("body") == body for comment in comments):
            raise RecoveryError("notice_not_confirmed")
        entry.update(state="complete", comment_id=result["id"])
    except Exception:
        entry["state"] = "notice_unknown"
        ledger.save()
        raise RecoveryError("notice_outcome_unknown") from None
    ledger.save()


def recover(gh: GitHub, ledger: Ledger, now: datetime, *, act: bool = False, sleep=time.sleep, clock=None,
            may_write=lambda: True) -> dict[str, int]:
    now = instant(stamp(now))
    # CLI supplies a live clock; tests can freeze or advance it without sleeps.
    def current() -> datetime:
        return instant(stamp(clock() if clock is not None else now))
    counters = {"covered": 0, "planned": 0, "confirmed": 0, "errors": 0}
    candidates = {slot.key: slot for slot in slots(now)}
    # Reconcile old uncertain writes too; never issue a replacement POST for one.
    for key, entry in ledger.entries.items():
        if entry["state"] not in {"complete", "skipped"}:
            candidates[key] = validate_slot(entry["workflow"], entry["slot"])
    for slot in candidates.values():
        try:
            entry = ledger.entries.get(slot.key)
            if entry and entry["state"] in {"complete", "skipped"}:
                counters["covered"] += 1
                continue
            if entry and entry["state"] == "dispatch_held":
                if not MIN_AGE <= current() - slot.at <= MAX_AGE:
                    if act:
                        entry["state"] = "skipped"
                        ledger.save()
                    counters["covered"] += 1
                    continue
                entry = None  # positively known not sent; may resume within its slot
            runs = run_listing(gh, slot, current())
            if entry is None:
                workflow = gh.request(f"/actions/workflows/{slot.workflow}")
                if not isinstance(workflow, dict) or workflow.get("state") != "active":
                    raise RecoveryError("workflow_not_active")
                if covered(slot, runs, current()):
                    counters["covered"] += 1
                    continue
                if not act:
                    counters["planned"] += 1
                    continue
                main = gh.request("/commits/main")
                if not isinstance(main, dict) or SHA_RE.fullmatch(str(main.get("sha"))) is None:
                    raise RecoveryError("main_revision_unavailable")
                # Last read closes the ordinary race with queued/delayed schedules.
                runs = run_listing(gh, slot, current())
                if covered(slot, runs, current()):
                    counters["covered"] += 1
                    continue
                checked_main = gh.request("/commits/main")
                if not isinstance(checked_main, dict) or checked_main.get("sha") != main["sha"]:
                    raise RecoveryError("main_revision_changed")
                live_now = current()
                if not MIN_AGE <= live_now - slot.at <= MAX_AGE:
                    counters["covered"] += 1  # stale by the end of the reads: do not catch up
                    continue
                if not may_write():
                    counters["covered"] += 1
                    continue
                entry = {"workflow": slot.workflow, "slot": slot.value, "state": "dispatch_intent",
                         "attempted_at": stamp(live_now), "head_sha": main["sha"],
                         "before_id": max((run["id"] for run in runs), default=0)}
                ledger.entries[slot.key] = entry
                ledger.save()  # failure/crash here must precede all external writes
                if not may_write():
                    entry["state"] = "dispatch_held"
                    ledger.save()
                    counters["covered"] += 1
                    continue
                if not MIN_AGE <= current() - slot.at <= MAX_AGE:
                    # fsync can block. This intent is positively known unsent,
                    # so expire it rather than dispatching an aged-out slot.
                    entry["state"] = "skipped"
                    ledger.save()
                    counters["covered"] += 1
                    continue
                try:
                    gh.request(f"/actions/workflows/{slot.workflow}/dispatches", "POST", {"ref": "main", "inputs": slot.inputs})
                except Exception:
                    entry["state"] = "dispatch_unknown"
                    ledger.save()
                # Even a successful HTTP204 is not a run receipt. Poll ≤60s.
                for _ in range(12):
                    sleep(5)
                    if confirm_run(entry, slot, run_listing(gh, slot, current())):
                        ledger.save()
                        break
            elif entry["state"] in {"dispatch_intent", "dispatch_unknown"}:
                if confirm_run(entry, slot, runs):
                    if act:
                        ledger.save()
            if entry["state"] in {"dispatch_intent", "dispatch_unknown"}:
                if act:
                    entry["state"] = "dispatch_unknown"
                    ledger.save()
                raise RecoveryError("dispatch_outcome_unknown")
            counters["confirmed"] += 1
            if act:
                publish_notice(gh, ledger, entry, slot, may_write=may_write)
        except Exception as error:
            counters["errors"] += 1
            code = str(error) if isinstance(error, RecoveryError) else type(error).__name__
            print(f"{slot.workflow}: {code}")
    return counters


def writes_allowed() -> bool:
    return not (Path("/etc/c3po/security-maintenance.hold").exists()
                or Path("/run/c3po-security/reboot.pending").exists())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--act", action="store_true", help="explicitly allow recovery/receipt POSTs (default: plan only)")
    parser.add_argument("--state-dir", type=Path, default=Path("/var/lib/c3po-workflow-schedule-recovery"))
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--validate-slot", nargs=2, metavar=("WORKFLOW", "SLOT"))
    args = parser.parse_args(argv)
    if args.validate_slot is not None:
        try:
            workflow, value = args.validate_slot
            if value:
                validate_slot(workflow, value)
            return 0
        except RecoveryError:
            print("invalid_recovery_slot")
            return 2
    # Explicit operator/security holds also hold the safety net. Never clear one.
    if not writes_allowed():
        print("maintenance_hold")
        return 0
    try:
        token_file = args.token_file
        if token_file is None:
            directory = os.environ.get("CREDENTIALS_DIRECTORY")
            if not directory:
                raise RecoveryError("credential_unavailable")
            token_file = Path(directory) / "github-token"
        if token_file.is_symlink() or not token_file.is_file() or token_file.stat().st_mode & 0o077:
            raise RecoveryError("unsafe_credential_file")
        token = token_file.read_text().strip()
        gh = GitHub(token)
        directory = args.state_dir
        if directory.is_symlink():
            raise RecoveryError("unsafe_state_directory")
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if directory.stat().st_mode & 0o077:
            raise RecoveryError("unsafe_state_directory")
        lock_path = directory / "recovery.lock"
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("recovery_already_running")
                return 0
            ledger = Ledger(directory / "ledger.json")
            result = recover(gh, ledger, datetime.now(UTC), act=args.act, clock=lambda: datetime.now(UTC),
                             may_write=writes_allowed)
            print(json.dumps(result, sort_keys=True))
            return 1 if result["errors"] else 0
    except Exception as error:
        print(str(error) if isinstance(error, RecoveryError) else type(error).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
