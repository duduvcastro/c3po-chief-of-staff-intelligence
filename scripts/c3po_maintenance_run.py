#!/usr/bin/env python3
"""Hold a work lease for a scheduled SSH command, including its stdin stream."""
import subprocess
import sys
from pathlib import Path
from maintenance_gate import admit, MaintenanceBusy


def main():
    if len(sys.argv) < 2:
        raise SystemExit("A command is required")
    try:
        lease = admit(Path("/opt/chief-of-staff-digital/runtime/security/maintenance"))
    except (MaintenanceBusy, OSError, ValueError):
        raise SystemExit("Maintenance admission unavailable; retry after recovery") from None
    with lease:
        raise SystemExit(subprocess.run(sys.argv[1:]).returncode)


if __name__ == "__main__":
    main()
