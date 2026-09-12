#!/usr/bin/env python3
"""Fixed production exclusions shared by maintenance and post-boot recovery."""
import fcntl
import json
import re
from datetime import datetime
from pathlib import Path

TRIAL_ROOT = Path('/mnt/day-d-data')


def trial_present(now, base=TRIAL_ROOT):
    if not base.exists():
        return False
    marker = base / '.r2d2-v2-pinned'
    if marker.exists() or marker.is_symlink():
        return True
    # Enumerate explicitly so permission errors cannot masquerade as no trial.
    for path in base.iterdir():
        if path.name.startswith('r2d2-v2-release-') and path.suffix == '.json':
            # Installed CERTIFIED releases stay fixed until the session rite
            # archives them outside this active directory. A terminal trade or
            # elapsed date does not prove that the epoch has been retired.
            if path.is_symlink():
                return True
            try:
                release = json.loads(path.read_text())
            except (OSError, ValueError):
                return True
            if not isinstance(release, dict) or release.get('mode') != 'DIAGNOSTIC':
                return True
            if not str(release.get('epoch', '')).startswith('R2D2-V2-DIAG-'):
                return True
        if not path.name.startswith(('.r2d2-v2-trial-', '.r2d2-v2-probe-')):
            continue
        match = re.fullmatch(r'\.r2d2-v2-(?:trial|probe)-(\d{8})(?:-r\d+)?', path.name)
        if path.is_symlink() or not match:
            return True
        trial_date = datetime.strptime(match[1], '%Y%m%d').date()
        if trial_date >= now.date():
            return True
        # Retained historical receipts are not active trials. A held old probe
        # lock still vetoes maintenance; never create or modify a trial file.
        lock = path / 'probe.lock'
        if lock.exists():
            with lock.open('r') as handle:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return True
    return False


def recovery_allowed(now, hold, base=TRIAL_ROOT):
    # Excludes every night (20Z–04Z) and all active-session hours (13Z–21:30Z).
    return 10 <= now.hour < 12 and not hold.exists() and not trial_present(now, base)
