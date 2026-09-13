#!/usr/bin/env python3
"""Initialize stable admission files before starting the new application build."""
import os
import stat
import sys
from pathlib import Path


def initialize(root):
    directory = root / "runtime/security/maintenance"
    directory.mkdir(parents=True, exist_ok=True)
    if directory.is_symlink():
        raise RuntimeError("Invalid maintenance directory")
    os.chmod(directory, 0o755)
    os.chown(directory, 0, 0)
    for name in ("admission.lock", "work.lock"):
        fd = os.open(directory / name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o644)
        try:
            value = os.fstat(fd)
            if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
                raise RuntimeError("Invalid maintenance lock")
            os.fchmod(fd, 0o644)
            os.fchown(fd, 0, 0)
        finally:
            os.close(fd)


if __name__ == "__main__":
    initialize(Path(sys.argv[1]))
