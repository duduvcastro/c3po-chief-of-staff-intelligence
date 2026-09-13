#!/usr/bin/env python3
"""Serialized maintenance reboot with durable receipt and bounded retries."""
from __future__ import annotations

import fcntl
import json
import hashlib
import os
import tempfile
try:
    from maintenance_gate import Drain, MaintenanceBusy
except ModuleNotFoundError:
    from app.maintenance_gate import Drain, MaintenanceBusy
from c3po_security_schedulers import SchedulingPause, restore as restore_schedulers
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


def atomic_marker(path, boot_id):
    """Publish a complete marker, never a temporarily empty/partial UUID."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(boot_id + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o644)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def boot_receipt(root, write, healthy, now, command=None, *, lock_held=False):
    if lock_held:
        return _boot_receipt_locked(root, write, healthy, now, command)
    with (root / "runtime/security/deployment.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            path = root / "runtime/security" / STATE
            return json.loads(path.read_text()) if path.exists() else None
        return _boot_receipt_locked(root, write, healthy, now, command)


def _boot_receipt_locked(root, write, healthy, now, command):
    path = root / "runtime/security" / STATE
    state = json.loads(path.read_text()) if path.exists() else None
    if not state or state.get("state") not in ("requested", "verifying"):
        # The controller may have died after stopping timers but before writing
        # a reboot request. Recover its saved scheduler state in that case too.
        if command:
            restore_schedulers(root, command, write)
        if state and state.get("state") == "verified" and state.get("current_boot_id") == BOOT_ID.read_text().strip():
            MARKER.unlink(missing_ok=True)
            (root / "runtime/security/maintenance/reboot.pending").unlink(missing_ok=True)
        return state
    if state["boot_id"] == BOOT_ID.read_text().strip():
        if now - datetime.fromisoformat(state["requested_at"]) > timedelta(minutes=15):
            state.update(state="failed", error="reboot_did_not_happen")
            MARKER.unlink(missing_ok=True)
            (root / "runtime/security/maintenance/reboot.pending").unlink(missing_ok=True)
            restore_schedulers(root, command, write)
            write(path, state)
        return state
    if command:
        restore_schedulers(root, command, write)
    MARKER.unlink(missing_ok=True)
    (root / "runtime/security/maintenance/reboot.pending").unlink(missing_ok=True)
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
        if gh.pages("/actions/runs?status=" + status, "workflow_runs"):
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
        gate = root / "runtime/security/maintenance"
        try:
            drain = stack.enter_context(Drain(gate))
        except (MaintenanceBusy, FileNotFoundError):
            return "waiting_admission"
        if not drain.try_drained():
            return "waiting_active_jobs"
        if not admission_coverage(root, command):
            return "waiting_admission_coverage"
        pause = stack.enter_context(SchedulingPause(root, command, write))
        if not pause.idle():
            return "waiting_scheduled_jobs"
        # A second database observation is now protected by closed admission and
        # suspended schedulers. Initial idle checks alone never authorize reboot.
        busy = command(["docker", "exec", db, "psql", "-U", "c3po", "-d", "c3po", "-At", "-c",
                        "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND state IS DISTINCT FROM 'idle'"])
        if busy != "0":
            return "waiting_database_work"
        if not allowed():
            return "deferred"
        state = {"schema": "C3PO_SECURITY_REBOOT-v1", "state": "requested", "boot_id": boot_id,
                 "requested_at": datetime.now(timezone.utc).isoformat(), "reason": "security_updates_require_reboot",
                 "admission_closed": True, "scheduled_jobs_idle": True,
                 "before": {"revision": (root / ".deploy-version").read_text().strip(),
                            "containers": container_receipt(containers)}}
        write(path, state)
        try:
            MARKER.parent.mkdir(parents=True, exist_ok=True)
            atomic_marker(MARKER, boot_id)
            atomic_marker(gate / "reboot.pending", boot_id)
            command(["systemctl", "reboot", "--no-block"])
        except Exception:
            state.update(state="failed", error="reboot_request_failed")
            write(path, state)
            MARKER.unlink(missing_ok=True)
            (gate / "reboot.pending").unlink(missing_ok=True)
            raise
        pause.keep = True
    return "requested"


def admission_coverage(root, command):
    """Refuse unknown workloads or any container still on the old protocol."""
    ids = command(["docker", "ps", "-q"]).splitlines()
    if not ids:
        return False
    containers = json.loads(command(["docker", "inspect", *ids]))
    backend = {"api", "investor-relations-worker", "valuation-worker", "server-usage-worker",
               "r2d2-worker", "r2d2-shadow-candidate-worker"}
    found = set()
    source = str(root / "runtime/security/maintenance")
    expected = hashlib.sha256((root / "c3po/backend/app/maintenance_gate.py").read_bytes()).hexdigest()
    revision = (root / ".deploy-version").read_text().strip()
    for container in containers:
        service = container["Config"].get("Labels", {}).get("com.docker.compose.service")
        if service in {"web", "db", "cloudflared"}:
            continue
        if service not in backend | {"pluggy-webhook"} or service in found:
            return False
        found.add(service)
        if service in backend and container["Config"].get("Labels", {}).get("org.opencontainers.image.revision") != revision:
            return False
        if "C3PO_MAINTENANCE_GATE_DIR=/run/c3po-maintenance" not in container["Config"].get("Env", []):
            return False
        if not any(m.get("Source") == source and m.get("Destination") == "/run/c3po-maintenance"
                   and m.get("RW") is False for m in container.get("Mounts", [])):
            return False
        module = "/app/maintenance_gate.py" if service == "pluggy-webhook" else "/app/app/maintenance_gate.py"
        actual = command(["docker", "exec", container["Id"], "sha256sum", module]).split()[0]
        if actual != expected:
            return False
        if service == "pluggy-webhook":
            live = json.loads(command(["docker", "exec", container["Id"], "python3", "-c",
                "import json,urllib.request; print(json.dumps(json.load(urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=5))))"]))
            handler = hashlib.sha256((root / "work/pluggy_webhook.py").read_bytes()).hexdigest()
            if live.get("maintenance_module_sha256") != expected or live.get("maintenance_handler_sha256") != handler:
                return False
        if service == "r2d2-worker":
            # The optional processor has an independent retained queue. Until it
            # implements the same drain protocol, its activation vetoes reboot.
            active = command(["docker", "exec", container["Id"], "python3", "-B", "-c",
                              "from app.config import get_settings; s=get_settings(); print(int(s.r2d2_microstructure_raw_capture_enabled and s.r2d2_microstructure_processor_enabled))"])
            if active != "0":
                return False
    return backend | {"pluggy-webhook"} == found
