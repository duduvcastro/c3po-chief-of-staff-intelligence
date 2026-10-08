"""Own Linux file guards + genuine age roundtrip of SYNTHETIC F2 evidence (CI only).

Ephemeral recipient/key, fixture provider and clock. No server, provider, token or real key.
Usage: python3 -I -S -B test_linux_crypto.py <age> <age-keygen>
"""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import series_runtime as s
import test_series as t

KEYGEN_SHA256 = "0a0009db842259d6717f7eeb30acb6b90d2a2eb924c6acd0a0db0ca1f1537899"


def run_proof():
    s.need(sys.platform == "linux", "PROOF_REQUIRES_LINUX")
    age, keygen = sys.argv[1:]
    s.need(s.sha(Path(age).read_bytes()) == s.AGE_SHA256, "PROOF_AGE_WRONG_BYTES")
    s.need(s.sha(Path(keygen).read_bytes()) == KEYGEN_SHA256, "PROOF_KEYGEN_WRONG_BYTES")
    checks = {}
    with tempfile.TemporaryDirectory(prefix="f2-synthetic-", dir=str(Path.home())) as td:
        base = Path(td)
        os.chmod(base, 0o700)
        root = base / "campaign"
        root.mkdir(mode=0o700)
        shutil.copyfile(age, root / "age")
        os.chmod(root / "age", 0o500)
        # Physical guards on Linux: exclusive root accepted; group-writable and symlinked roots refused.
        fd = s.open_dir(str(root), exclusive=True, physical=True)
        os.close(fd)
        loose = base / "loose"
        loose.mkdir(mode=0o700)
        os.chmod(loose, 0o770)
        try:
            os.close(s.open_dir(str(loose), exclusive=True, physical=True))
            checks["group_writable_refused"] = False
        except s.Refusal:
            checks["group_writable_refused"] = True
        (base / "link").symlink_to(root)
        try:
            os.close(s.open_dir(str(base / "link"), exclusive=True, physical=True))
            checks["symlink_refused"] = False
        except s.Refusal:
            checks["symlink_refused"] = True
        key = base / "fixture.key"
        subprocess.run([keygen, "-o", str(key)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        recipient = subprocess.check_output([keygen, "-y", str(key)], stderr=subprocess.DEVNULL).decode().strip()
        with patch.object(s, "RECIPIENT", recipient):
            raws, elig = t.documents()
            clock, mono = t.Clock("2026-10-09T00:26:00.300Z"), t.Mono()
            factory = lambda token, monotonic, clock: t.FakeProvider(token, monotonic, clock, body=t.bulk(4100))
            result = s.run(raws, "2126", elig, lambda: "fixture-token", clock=clock, monotonic=mono,
                           cipher=s.cipher_to_fd, provider_factory=factory, physical=False, campaign_root=str(root),
                           reference=s.load_reference(physical=False))
        sealed = (root / "2126" / s.CIPHER_NAME).read_bytes()
        s.need(s.sha(sealed) == result["cipher_sha256"], "PROOF_CIPHER_HASH_MISMATCH")
        plain = subprocess.run([age, "-d", "-i", str(key)], input=sealed, capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(plain), mode="r:") as archive:
            members = {m.name: archive.extractfile(m).read() for m in archive.getmembers()}
        inventory = members["inventory.json"]
        s.need(s.sha(inventory) == result["inventory_sha256"], "PROOF_INVENTORY_MISMATCH")
        analysis = json.loads(members["analysis.json"])
        s.need(analysis["counts"] == result["counts"] and len(analysis["eligible_absent"]) == 100, "PROOF_ANALYSIS_MISMATCH")
        s.need(b"fixture-token" not in plain and b"fixture-token" not in (root / "2126" / s.RECEIPT_NAME).read_bytes(),
               "PROOF_TOKEN_LEAK")
        checks.update(status=result["status"], members=sorted(members), cipher_bytes=len(sealed))
    ok = checks["group_writable_refused"] and checks["symlink_refused"] and checks["status"] == "SLOT_OBSERVED_PASS"
    return {"schema": "F2_LINUX_CRYPTO_PROOF_V1", "ok": bool(ok), "checks": checks, "synthetic_only": True,
            "operational_acceptance": False}


if __name__ == "__main__":
    out = run_proof()
    print(json.dumps(out, sort_keys=True))
    raise SystemExit(0 if out["ok"] else 1)
