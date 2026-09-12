#!/usr/bin/env python3
"""Recover the security timers and verify post-boot application health."""
from __future__ import annotations

import json
import argparse
from datetime import datetime, timezone
import fcntl

from c3po_security_daily import ROOT, HOLD, command, healthy_host, load_evidence, write_report
from c3po_security_reboot import boot_receipt
from c3po_security_guard import recovery_allowed

TIMERS = ("c3po-security-daily.timer", "c3po-security-watchdog.timer",
          "c3po-host-security-snapshot.timer", "apt-daily-upgrade.timer")


def check(root, now, *, run=command, health=healthy_host, write=write_report, hold=HOLD):
    report = {"schema": "C3PO_SECURITY_WATCHDOG-v1", "generated_at": now.isoformat(),
              "healthy": False, "repairs": [], "errors": []}
    if hold.exists():
        report["status"] = "explicit_maintenance_hold"
        return report
    for timer in TIMERS:
        if run(["systemctl", "show", timer, "-p", "UnitFileState", "--value"]) != "enabled":
            run(["systemctl", "enable", timer])
            report["repairs"].append("enabled:" + timer)
        if run(["systemctl", "show", timer, "-p", "ActiveState", "--value"]) != "active":
            run(["systemctl", "start", timer])
            report["repairs"].append("started:" + timer)
    try:
        evidence = load_evidence(root / "runtime/security/security-automation-report.json", now, 1.5)
        if evidence.get("status") == "failed":
            raise ValueError("last_cycle_failed")
    except (OSError, ValueError, KeyError):
        run(["systemctl", "start", "--no-block", "c3po-security-daily.service"])
        report["repairs"].append("requested_security_cycle")
    reboot = boot_receipt(root, write, health, now)
    report["reboot"] = reboot
    if reboot and reboot.get("state") == "verifying" and recovery_allowed(now, hold):
        # Restart only the required app services; never revive intentionally paused workers.
        with (root / "runtime/security/deployment.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Start existing containers only: preserve their exact images, settings and IDs.
            run(["docker", "compose", "--env-file", str(root / ".env"), "-f", str(root / "c3po/compose.yml"),
                 "start", "db", "api", "web"])
        report["repairs"].append("recovered_required_services")
        report["reboot"] = boot_receipt(root, write, health, now)
    if report["reboot"] and report["reboot"].get("state") in ("failed", "verifying"):
        report["errors"].append("postboot_verification_pending_or_failed")
    report["healthy"] = not report["errors"] and not report["repairs"]
    report["status"] = "verified" if report["healthy"] else "repairing" if not report["errors"] else "failed"
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-daily", action="store_true")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    try:
        report = check(ROOT, now)
        if args.verify_daily and report["status"] != "explicit_maintenance_hold":
            evidence = load_evidence(ROOT / "runtime/security/security-automation-report.json", now, 1.5)
            if (evidence.get("last_dispatch_date") != now.date().isoformat()
                    or evidence.get("status") == "failed" or evidence.get("errors")):
                report["healthy"] = False
                report["status"] = "failed"
                report["errors"].append("daily_security_execution_not_verified")
    except Exception as exc:
        report = {"schema": "C3PO_SECURITY_WATCHDOG-v1", "generated_at": now.isoformat(),
                  "healthy": False, "status": "failed", "errors": [type(exc).__name__]}
    write_report(ROOT / "runtime/security/security-watchdog-report.json", report)
    print(json.dumps({"status": report["status"], "healthy": report["healthy"]}))
    if report["status"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
