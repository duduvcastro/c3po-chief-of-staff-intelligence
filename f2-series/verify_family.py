"""Read-only SHA256SUMS and extraction verifier. Does not execute operation code."""
import ast
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
EXPECTED_REFERENCE = "e50e2263ea07a5a31db43f3e2a6cb68dec769ffa1e808d6197f622c78020acd1"


def normalize_ast(tree):
    # Python 3.12 adds empty type_params fields to old syntax. Remove only
    # those empty parser additions to compare the original 3.9 AST fairly.
    for node in ast.walk(tree):
        if hasattr(node, "type_params"):
            assert node.type_params == []
            del node.type_params
    return tree


def verify(root=ROOT):
    root = Path(root)
    sums = (root / "SHA256SUMS").read_bytes()
    records = {}
    for line in sums.decode("ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._/-]+)", line)
        assert match and match[2] not in records and ".." not in Path(match[2]).parts
        records[match[2]] = match[1]
    present = {p.relative_to(root).as_posix() for p in root.rglob("*")
               if p.is_file() and p.name != "SHA256SUMS" and p.suffix != ".pyc" and "__pycache__" not in p.parts}
    assert set(records) == present
    for name, digest in records.items():
        path = root / name
        assert not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == digest
    raw = (root / "reference_extract.py").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_REFERENCE
    provenance = json.loads((root / "REFERENCE_PROVENANCE.json").read_bytes())
    assert provenance["extract_sha256"] == EXPECTED_REFERENCE
    tree = normalize_ast(ast.parse(raw))
    found = {}
    for node in tree.body:
        names = {x.id for x in node.targets if isinstance(x, ast.Name)} if isinstance(node, ast.Assign) else {getattr(node, "name", None)}
        for name in names:
            found[name] = hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
    for row in provenance["selected_nodes"]:
        assert all(found[name] == row["ast_sha256"] for name in row["names"])
    for name in records:
        if name.endswith(".py"):
            ast.parse((root / name).read_bytes())
    return {"schema": "F2_SEAL_VERIFICATION_V1", "status": "SEAL_EXACT", "files": len(records),
            "seal_sha256": hashlib.sha256(sums).hexdigest(), "reference_ast_nodes": len(provenance["selected_nodes"]),
            "operation_executed": False}


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
