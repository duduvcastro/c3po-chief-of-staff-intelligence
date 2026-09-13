"""Temporarily stop scheduling, never terminate an executing job."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import signal

BOOT_ID = Path("/proc/sys/kernel/random/boot_id")


def process_identity(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except FileNotFoundError:
        return None


def restore(root, run, write):
    path = root / "runtime/security/reboot-schedulers.json"
    if not path.exists():
        return
    receipt = json.loads(path.read_text())
    if receipt.get("restored"):
        return
    if receipt["boot_id"] == BOOT_ID.read_text().strip():
        pid = receipt.get("cron_pid", 0)
        if pid and process_identity(pid) == receipt["cron_start"]:
            os.kill(pid, signal.SIGCONT)
    if receipt["timers"]:
        run(["systemctl", "start", *receipt["timers"]])
    receipt["restored"] = True
    write(path, receipt)


class SchedulingPause:
    def __init__(self, root, run, write):
        self.root, self.run, self.write = root, run, write
        self.keep = False
        self.receipt = None

    def __enter__(self):
        # Snapshot before mutation. Stopping a timer does not stop its service.
        units = self.run(["systemctl", "list-units", "--type=timer", "--state=active",
                          "--no-legend", "--plain"]).splitlines()
        timers = [line.split()[0] for line in units if line.strip()]
        timers = [t for t in timers if t not in ("c3po-security-watchdog.timer", "c3po-security-daily.timer")]
        if any(not re.fullmatch(r"[A-Za-z0-9_.@:-]+\.timer", t) for t in timers):
            raise RuntimeError("Unrecognized scheduler unit")
        pid = int(self.run(["systemctl", "show", "cron.service", "-p", "MainPID", "--value"]) or "0")
        self.receipt = {"timers": timers, "cron_pid": pid, "cron_start": process_identity(pid) if pid else None,
                        "boot_id": BOOT_ID.read_text().strip(), "restored": False}
        self.write(self.root / "runtime/security/reboot-schedulers.json", self.receipt)
        try:
            if timers:
                self.run(["systemctl", "stop", *timers])
            if pid:
                # Only the scheduler's main PID is suspended. Children continue
                # running and retain their cgroup membership until completion.
                fd = os.pidfd_open(pid)
                try:
                    if process_identity(pid) != self.receipt["cron_start"]:
                        raise RuntimeError("Cron identity changed")
                    signal.pidfd_send_signal(fd, signal.SIGSTOP)
                finally:
                    os.close(fd)
            return self
        except BaseException:
            restore(self.root, self.run, self.write)
            raise

    def idle(self):
        assert self.receipt is not None
        for timer in self.receipt["timers"]:
            services = self.run(["systemctl", "show", timer, "-p", "Triggers", "--value"]).split()
            for service in services:
                state = self.run(["systemctl", "show", service, "-p", "ActiveState", "--value"])
                if state in ("active", "activating", "deactivating"):
                    return False
        if self.receipt["cron_pid"]:
            group = self.run(["systemctl", "show", "cron.service", "-p", "ControlGroup", "--value"])
            if not group.startswith("/system.slice/") or ".." in group:
                raise RuntimeError("Unrecognized cron cgroup")
            base = Path("/sys/fs/cgroup") / group.lstrip("/")
            files = list(base.rglob("cgroup.procs"))
            if not files:
                raise RuntimeError("Cannot verify scheduled work")
            processes = {int(v) for file in files for v in file.read_text().split()}
            if processes - {self.receipt["cron_pid"]}:
                return False
        return True

    def __exit__(self, *args):
        if not self.keep:
            restore(self.root, self.run, self.write)
