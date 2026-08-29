#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "C3PO_HOST_OS_VULNERABILITY_REPORT-v1"
DEFAULT_OUTPUT = Path(
    "/opt/chief-of-staff-digital/runtime/security/host-os-vulnerability-report.json"
)


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def report_sha256(report: dict[str, Any]) -> str:
    payload = {key: value for key, value in report.items() if key != "report_sha256"}
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def command(*args: str) -> str:
    return subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout.strip()


def command_status(*args: str) -> tuple[int, str]:
    result = subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.returncode, result.stdout.strip()


def apt_update_counts() -> tuple[int, int, list[str]]:
    import apt  # type: ignore[import-not-found]

    cache = apt.Cache()
    cache.open(None)
    cache.upgrade(dist_upgrade=True)
    upgradable = [package for package in cache if package.is_upgradable]
    security_packages = sorted(
        package.name
        for package in upgradable
        if any(
            str(getattr(origin, "archive", "")).endswith("-security")
            for origin in package.candidate.origins
        )
    )
    return len(upgradable), len(security_packages), security_packages


def apt_policy() -> tuple[list[str], bool, bool]:
    dump = command("apt-config", "dump")
    allowed = []
    automatic_reboot = False
    for line in dump.splitlines():
        if line.startswith((
            "Unattended-Upgrade::Allowed-Origins::",
            "Unattended-Upgrade::Origins-Pattern::",
        )):
            value = line.split('"', 1)[1].rsplit('"', 1)[0]
            allowed.append(value)
        if line.startswith("Unattended-Upgrade::Automatic-Reboot "):
            value = line.split('"', 1)[1].rsplit('"', 1)[0]
            automatic_reboot = value.lower() == "true"
    security_only = bool(allowed) and all("security" in item.lower() for item in allowed)
    return allowed, security_only, automatic_reboot


def os_release() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"')
    return {
        "id": values.get("ID", "unknown"),
        "version_id": values.get("VERSION_ID", "unknown"),
    }


def collect() -> dict[str, Any]:
    all_pending, security_pending, security_packages = apt_update_counts()
    allowed_origins, security_only, automatic_reboot = apt_policy()
    reboot_required_path = Path("/var/run/reboot-required")
    reboot_packages_path = Path("/var/run/reboot-required.pkgs")
    reboot_packages = (
        sorted(set(reboot_packages_path.read_text(encoding="utf-8").splitlines()))
        if reboot_packages_path.is_file()
        else []
    )
    dpkg_status, dpkg_output = command_status(
        "dpkg-query", "-W", "-f=${db:Status-Abbrev}", "unattended-upgrades"
    )
    enabled_status, enabled_output = command_status(
        "systemctl", "is-enabled", "apt-daily-upgrade.timer"
    )
    active_status, active_output = command_status(
        "systemctl", "is-active", "apt-daily-upgrade.timer"
    )
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": os_release(),
        "unattended_upgrades": {
            "installed": dpkg_status == 0 and dpkg_output.startswith("ii"),
            "enabled": enabled_status == 0 and enabled_output == "enabled",
            "active": active_status == 0 and active_output == "active",
            "security_only": security_only,
            "automatic_reboot": automatic_reboot,
            "allowed_origins": allowed_origins,
        },
        "updates": {
            "all_pending": all_pending,
            "security_pending": security_pending,
            "security_packages": security_packages,
        },
        "reboot_required": reboot_required_path.is_file(),
        "reboot_packages": reboot_packages,
    }
    report["report_sha256"] = report_sha256(report)
    return report


def atomic_write(output: Path, report: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=output.parent,
        prefix=f".{output.name}.",
        delete=False,
    ) as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.chmod(temporary, 0o644)
    temporary.replace(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Write the host OS security snapshot")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = collect()
    atomic_write(args.output, report)
    print(json.dumps({
        "security_updates_pending": report["updates"]["security_pending"],
        "reboot_required": report["reboot_required"],
        "report_sha256": report["report_sha256"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
