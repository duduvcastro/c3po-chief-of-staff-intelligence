#!/usr/bin/env python3
"""Fixed production exclusions shared by maintenance and post-boot recovery."""
import fcntl
import re
from datetime import datetime
from pathlib import Path

TRIAL_ROOT = Path('/mnt/day-d-data')


def trial_present(now, base=TRIAL_ROOT):
    if not base.exists():
        return False
    # Enumerate explicitly so permission errors cannot masquerade as no trial.
    for path in base.iterdir():
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
