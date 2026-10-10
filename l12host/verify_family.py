"""Read-only SHA256SUMS verifier of the L12-HOST v3.2 family. Does not execute operation code.

Also checks every vendored Codex file against its published SHA-256 (VENDOR_PINS):
  L-12 R6 package c048449e... : core finite_batch 809a816d, outer_limiter b845f824, bounded_runner f06a4b69,
                                capacity_monday_gate ebe04ca6, verification_binding 78f4309d, image_capacity_gate 58a6104e;
  K9 prove receipt r1         : k9_receipt_adapter f84d55b8 (R6 ed89a071 + the prove -> prove_launch alias);
  image bounded readback r1   : image_path_adapter 99148f80, bounded_readback 2a3c1ca9, bounded_image_capacity_gate ade4c4b0;
  J4 hot-image10 r1           : j4_hot_worker 0edb64f4 (the only J program on the host);
  K9 grid delta r1 (Codex)    : lots/k9tools/gen_k9_plans04.py 2b08ee13, superseded by the lots patch v3.4 (L-01:
                                closed grid choice C/D, DRAFT3_REJECTED refused by `plans`; Codex P4 ruling) 66af6c9e;
                                track F-E runner lots/k9tools/k9_runner04.py e9be2b30;
  reviewed unit references    : reference/c3po-reader.service 8d2ff7a9, reference/c3po-massive.service 9e7de1c6.
"""
import ast
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
VENDOR_PINS = {
    "vendor/finite_batch.py": "809a816d4179ee889531bfc2d270e193508f0d1a31d7a30a48159151f80dbeec",
    "vendor/outer_limiter.py": "b845f824e1986a9101015016f94caa2eabcc91ec5c4e3fc77d728a9b4cac9b6e",
    "vendor/bounded_runner.py": "f06a4b697336ded17264ee2178b27ee02c26b4689bccf1795eac16645a18fda3",
    "vendor/capacity_monday_gate.py": "ebe04ca62c8b75ba0b2ed3444a14503e9f44c4b6937de3cf544d55f76142fc53",
    "vendor/verification_binding.py": "78f4309d9713ea1c718d5635e5eed0dc71335c9b7cb7c82149185e868fc23c86",
    "vendor/image_capacity_gate.py": "58a6104e8d1efcab2199d388ffe17e602abf315304449dd1be5178f57f7c12ec",
    "vendor/k9_receipt_adapter.py": "f84d55b8903895a318f566271b1c33934189b8299afedec1e42ca569c3455a9a",
    "vendor/image_path_adapter.py": "99148f808ea4049c631b57dffb5f0f7b02c668d880ed6826077b70336efc0934",
    "vendor/bounded_readback.py": "2a3c1ca90f233332b8579125238d4787c72694915ab81d4dbf85d9c288a7450e",
    "vendor/bounded_image_capacity_gate.py": "ade4c4b00bda8bed20c241ad6b97391c0b8d1764daa8f964b22705af8ea4415c",
    "vendor/j4_hot_worker.py": "0edb64f45b8a4e31e64aa274e778566106e3549d7e8fe2ab8d746dd1b751d8fa",
    "lots/k9tools/gen_k9_plans04.py": "66af6c9e3b85215a1d5c44c91ef588dbc7e94d04aa96300fcc979684416e51cf",
    "lots/k9tools/k9_runner04.py": "e9be2b301397586a35f592cae3a23a5bfa3e7fdc5b9d27996c590e4303be081a",
    "reference/c3po-reader.service": "8d2ff7a91b94e39b8c7a0e91fae34b16dbc9d55f7af407b8464486a9bd064fab",
    "reference/c3po-massive.service": "9e7de1c6eaf937e5b1fc9540986fdbdf2a2f821a9c57b944f9534a605d07f04a",
}


def verify(root=ROOT):
    root = Path(root)
    sums = (root / "SHA256SUMS").read_bytes()
    records = {}
    for line in sums.decode("ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._/=-]+)", line)
        if not (match and match[2] not in records and ".." not in Path(match[2]).parts):
            raise SystemExit("SEAL_LINE_INVALID")
        records[match[2]] = match[1]
    present = {p.relative_to(root).as_posix() for p in root.rglob("*")
               if (p.is_file() or p.is_symlink()) and p.name != "SHA256SUMS" and "__pycache__" not in p.parts}
    if set(records) != present:
        raise SystemExit("SEAL_FILE_SET_MISMATCH")
    for name, digest in records.items():
        path = root / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise SystemExit("SEAL_BYTES_MISMATCH")
    for name, digest in VENDOR_PINS.items():
        if records.get(name) != digest:
            raise SystemExit("VENDOR_PIN_MISMATCH")
    for name in records:
        if name.endswith(".py"):
            ast.parse((root / name).read_bytes())
    return {"schema": "L12HOST_SEAL_VERIFICATION_V32", "status": "SEAL_EXACT", "files": len(records),
            "seal_sha256": hashlib.sha256(sums).hexdigest(), "vendor_pins": len(VENDOR_PINS),
            "operation_executed": False}


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
