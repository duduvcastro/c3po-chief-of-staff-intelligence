"""SHA256SUMS of a directory: every regular file except SHA256SUMS itself (and no __pycache__), byte-sorted paths,
`<sha256>  <relative path>` lines. Usage: make_sums.py DIR [--write] (prints the bytes' sha256; writes only with --write)."""
import hashlib
from pathlib import Path
import sys

root = Path(sys.argv[1])
names = []
for p in root.rglob("*"):
    rel = p.relative_to(root).as_posix()
    if "__pycache__" in p.parts or p.name == ".DS_Store":
        raise SystemExit("UNEXPECTED_FILE " + rel)
    if p.is_symlink():
        raise SystemExit("SYMLINK " + rel)
    if p.is_file() and rel != "SHA256SUMS":
        names.append(rel)
names.sort(key=lambda s: s.encode("utf-8"))
raw = "".join("%s  %s\n" % (hashlib.sha256((root / n).read_bytes()).hexdigest(), n) for n in names).encode("ascii")
if "--write" in sys.argv[2:]:
    (root / "SHA256SUMS").write_bytes(raw)
print(hashlib.sha256(raw).hexdigest(), len(names))
