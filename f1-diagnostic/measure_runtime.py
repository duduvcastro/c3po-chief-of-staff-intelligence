"""Fable's own read-only F1 runtime measurement; prints PRIVATE data to stdout.

No directories are created, no tokens read, no provider call, and no signature.
Run only with the operator's own authority. A CI measurement is not the server.
"""
import argparse
import os
from pathlib import Path
import stat
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
import diagnostic_runtime as d


def measure(root, age_path):
    d.need(sys.platform == "linux", "MEASUREMENT_REQUIRES_LINUX")
    rows = []
    for name in d.paths_to_root(root):
        info = os.lstat(name)
        d.need(stat.S_ISDIR(info.st_mode), "MEASUREMENT_PARENT_NOT_DIRECTORY")
        rows.append(d.directory_identity(name, info))
    q = {"private_root": root, "parent_identities": rows, "age_path": age_path, "age_sha256": d.AGE_SHA256}
    held = d.open_private_root(q)
    os.close(held)
    age_fd = d.open_age(q)
    os.close(age_fd)
    here = Path(__file__).resolve().parent
    measurement = {"schema": "F1_RUNTIME_MEASUREMENT_V1", "measured_at_utc": d.iso(datetime.now(timezone.utc)),
                   "platform": sys.platform, "python_version": "%d.%d.%d" % sys.version_info[:3],
                   "python_executable_sha256": d.sha(d.read_regular(str(Path(sys.executable).resolve()), 64 * 1024 * 1024)),
                   "executor_uid": os.geteuid(), "boot_id_sha256": d.sha(d.read_regular("/proc/sys/kernel/random/boot_id", 128)),
                   "source_sha256": d.sha(d.read_regular(str(here / "diagnostic_runtime.py"), 1024 * 1024)),
                   "reference_sha256": d.sha(d.read_regular(str(here / "reference_extract.py"), 65536)),
                   "seal_sha256": d.sha(d.read_regular(str(here / "SHA256SUMS"), 1024 * 1024)),
                   "age_sha256": d.AGE_SHA256, "private_root": root, "parent_identities": rows, "age_path": age_path,
                   "ready_or_GO": False, "owner_signature": False}
    runtime = {key: measurement[key] for key in ("platform", "python_version", "python_executable_sha256", "executor_uid", "boot_id_sha256",
                "source_sha256", "reference_sha256", "seal_sha256", "age_sha256")}
    runtime.update(schema="F1_RUNTIME_IDENTITY_V1", measurement_record_sha256=d.sha(d.canonical(measurement)))
    election = {"schema": "F1_SINGLE_ELECTION_V1", "epoch": d.EPOCH, "operation": d.OPERATION,
                "amendment_sha256": d.AMENDMENT, "private_root": root, "parent_identities": rows, "claim_name": d.CLAIM_NAME}
    return {"measurement": measurement, "runtime": runtime, "election": election}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", required=True)
    parser.add_argument("--age-path", required=True)
    args = parser.parse_args()
    try:
        os.write(1, d.canonical(measure(args.private_root, args.age_path)))
    except BaseException as error:
        os.write(1, d.canonical({"schema": "F1_MEASUREMENT_HOLD_V1", "code": d.safe_code(error), "ready_or_GO": False}) + b"\n")
        raise SystemExit(2)
