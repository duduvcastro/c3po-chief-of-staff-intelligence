"""M1 root-cause probe (Fable v3.2 build, macOS, synthetic, no effect outside BASE dirs it creates and removes).

    python3.12 -I -S -B m1_file_provider_probe.py <family l12host dir> <seconds> <rounds> <bytes> <base> [<base> ...]

For each BASE (created, must not exist): ROUNDS times, 20 new files of BYTES bytes are written and then read
continuously for SECONDS with the runtime's strict reader (l12host_runtime.read_path); counts INPUT_FILE_CHANGED (with
the file and the changed fields the v3.2 runtime now reports) and how many files had their ctime changed after their
creation (there is no other writer in this probe). Also reports kit.file_provider_domain(BASE)."""
import json, os, sys, time
FAM = sys.argv[1]
sys.path.insert(0, FAM + "/tests")
import kit                                   # noqa: E402
rt = kit.rt
seconds, rounds, size = float(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
report = {"schema": "L12HOST_V32_M1_FILE_PROVIDER_PROBE", "python": "%d.%d.%d" % sys.version_info[:3],
          "platform": sys.platform, "seconds_per_round": seconds, "rounds": rounds, "files_per_round": 20,
          "file_bytes": size, "bases": []}
for root in sys.argv[5:]:
    os.makedirs(root, exist_ok=False)
    row = {"base": root, "file_provider_domain": kit.file_provider_domain(root), "strict_reads": 0,
           "input_file_changed": 0, "files_with_ctime_changed_after_creation": 0, "files": 0, "changed_fields": set(),
           "named_example": None}
    for r in range(rounds):
        base = os.path.join(root, "r%d" % r)
        os.makedirs(base)
        paths = []
        for i in range(20):
            p = os.path.join(base, "f%02d.json" % i)
            with open(p, "wb") as f:
                f.write(b"x" * size)
            paths.append((p, os.stat(p).st_ctime_ns))
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            for p, _ in paths:
                try:
                    rt.read_path(p, size + 1, rt.Hold)
                except rt.Hold as error:
                    if str(error) != "INPUT_FILE_CHANGED":
                        raise
                    row["input_file_changed"] += 1
                    row["changed_fields"].add(",".join(error.changed))
                    row["named_example"] = row["named_example"] or os.path.relpath(error.input_file, os.path.realpath(root))
                row["strict_reads"] += 1
        row["files_with_ctime_changed_after_creation"] += sum(1 for p, c in paths if os.stat(p).st_ctime_ns != c)
        row["files"] += len(paths)
        for p, _ in paths:
            os.unlink(p)
        os.rmdir(base)
    os.rmdir(root)
    row["changed_fields"] = sorted(row["changed_fields"])
    report["bases"].append(row)
print(json.dumps(report, indent=1, sort_keys=True))
