#!/usr/bin/env python3
"""Serialized maintenance reboot with durable receipt and bounded retries."""
from __future__ import annotations

import fcntl
import json
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATE = "security-reboot-state.json"
MARKER = Path("/run/c3po-security/reboot.pending")
BOOT_ID = Path("/proc/sys/kernel/random/boot_id")
REQUIRED = Path("/var/run/reboot-required")
DPKG_LOCKS = (Path("/var/lib/dpkg/lock-frontend"), Path("/var/lib/dpkg/lock"))


def container_receipt(containers):
    return [{"id": c["Id"], "name": c["Name"], "image": c["Image"], "started_at": c["State"]["StartedAt"]}
            for c in containers]


def boot_receipt(root, write, healthy, now, command=None):
    path = root / "runtime/security" / STATE
    if not path.exists():
        return None
    state = json.loads(path.read_text())
    if state.get("state") not in ("requested", "verifying"):
        return state
    if state["boot_id"] == BOOT_ID.read_text().strip():
        if now - datetime.fromisoformat(state["requested_at"]) > timedelta(minutes=15):
            state.update(state="failed", error="reboot_did_not_happen")
            MARKER.unlink(missing_ok=True)
            write(path, state)
        return state
    try:
        ok = healthy(root) and not REQUIRED.exists()
    except Exception:
        ok = False
    state.update(state="verified" if ok else "verifying", verified_at=now.isoformat() if ok else None,
                 current_boot_id=BOOT_ID.read_text().strip())
    if ok and command:
        ids = command(["docker", "compose", "--env-file", str(root / ".env"), "-f", str(root / "c3po/compose.yml"), "ps", "-q"]).splitlines()
        state["after"] = {"revision": (root / ".deploy-version").read_text().strip(),
                          "containers": container_receipt(json.loads(command(["docker", "inspect", *ids])))}
    write(path, state)
    return state


def request_reboot(root, gh, config, now, *, command, healthy, write, allowed):
    if not REQUIRED.exists() or config.get("automatic_reboot") is not True:
        return "not_needed_or_disabled"
    path = root / "runtime/security" / STATE
    boot_id = BOOT_ID.read_text().strip()
    if path.exists():
        previous = json.loads(path.read_text())
        # At most one request per day. A failed reboot must not become a reboot loop.
        if now - datetime.fromisoformat(previous["requested_at"]) < timedelta(hours=24):
            return "cooldown"
    if not allowed() or not healthy(root):
        return "deferred"
    for status in ("queued", "in_progress", "waiting", "requested", "pending"):
        if gh.pages("/actions/workflows/c3po-pipeline.yml/runs?status=" + status, "workflow_runs"):
            return "waiting_pipeline"
    for unit in ("apt-daily.service", "apt-daily-upgrade.service"):
        if command(["systemctl", "show", unit, "-p", "ActiveState", "--value"]) in ("active", "activating"):
            return "waiting_packages"
    # No arbitrary SQL or imported application initialization: just observe active work.
    db = command(["docker", "compose", "--env-file", str(root / ".env"), "-f", str(root / "c3po/compose.yml"), "ps", "-q", "db"])
    busy = command(["docker", "exec", db, "psql", "-U", "c3po", "-d", "c3po", "-At", "-c",
                    "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND state IS DISTINCT FROM 'idle'"])
    if busy != "0":
        return "waiting_database_work"
    ids = command(["docker", "compose", "--env-file", str(root / ".env"), "-f", str(root / "c3po/compose.yml"), "ps", "-q"]).splitlines()
    containers = json.loads(command(["docker", "inspect", *ids]))
    # A record older than EVERY current project container cannot represent a
    # still-running process in those containers. Preserve the historical rows.
    oldest_start = min(datetime.fromisoformat(c["State"]["StartedAt"].replace("Z", "+00:00"))
                       for c in containers if c["State"]["Running"])
    cutoff = oldest_start.isoformat()
    busy = command(["docker", "exec", db, "psql", "-U", "c3po", "-d", "c3po", "-At", "-c",
                    "SELECT count(*) FROM ingestion_runs WHERE status='running' AND started_at >= '" + cutoff + "'::timestamptz"])
    if busy != "0":
        return "waiting_ingestion_work"
    with ExitStack() as stack:
        try:
            deploy_lock = stack.enter_context((root / "runtime/security/deployment.lock").open("a"))
            fcntl.flock(deploy_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for lock_path in DPKG_LOCKS:
                handle = stack.enter_context(lock_path.open("r+"))
                fcntl.lockf(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, PermissionError):
            return "waiting_packages_or_deploy"
        # Recheck the actual clock/hold after all potentially slow preflight calls.
        if not allowed():
            return "deferred"
        state = {"schema": "C3PO_SECURITY_REBOOT-v1", "state": "requested", "boot_id": boot_id,
                 "requested_at": datetime.now(timezone.utc).isoformat(), "reason": "security_updates_require_reboot",
                 "before": {"revision": (root / ".deploy-version").read_text().strip(),
                            "containers": container_receipt(containers)}}
        write(path, state)
        MARKER.parent.mkdir(parents=True, exist_ok=True)
        MARKER.write_text(boot_id + "\n")
        try:
            command(["systemctl", "reboot", "--no-block"])
        except Exception:
            state.update(state="failed", error="reboot_request_failed")
            write(path, state)
            MARKER.unlink(missing_ok=True)
            raise
    return "requested"
