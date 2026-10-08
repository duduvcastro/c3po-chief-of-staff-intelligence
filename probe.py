import os, stat, pathlib, json
p = pathlib.Path("sample.json"); os.chmod(p, 0o444)
b = p.lstat(); p.read_bytes(); a = p.lstat()
print(json.dumps({"equal_full_stat": b == a, "atime_changed": b.st_atime_ns != a.st_atime_ns,
                  "mtime_same": b.st_mtime_ns == a.st_mtime_ns, "ctime_same": b.st_ctime_ns == a.st_ctime_ns,
                  "second_read_equal": (lambda c: (p.read_bytes(), c == p.lstat())[1])(p.lstat())}))
