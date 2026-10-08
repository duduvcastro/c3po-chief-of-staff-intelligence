"""Own Linux physical file guards + genuine age roundtrip of SYNTHETIC evidence.

The recipient, clock, owner records and provider are fixtures. No target server
or real provider is contacted. This result is never an operational acceptance.
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
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import diagnostic_runtime as d
import measure_runtime as m
import test_diagnostic as t


def bound_fixture(root, recipient, original):
    raws = t.signed_fixtures(root)
    runtime, election = original["runtime"], original["election"]
    q = d.strict(raws["request"])
    q.update(private_root=str(root), parent_identities=original["measurement"]["parent_identities"],
             seal_sha256=runtime["seal_sha256"], runtime_sha256=d.sha(d.canonical(runtime)),
             election_sha256=d.sha(d.canonical(election)), recipient=recipient)
    review = d.strict(raws["review"])
    review.update(seal_sha256=q["seal_sha256"], runtime_sha256=q["runtime_sha256"], election_sha256=q["election_sha256"])
    q["review_sha256"] = d.sha(d.canonical(review))
    request = d.canonical(q)
    owner = d.strict(raws["owner"])
    owner.update(request_sha256=d.sha(request), question_sha256=d.sha(d.owner_question(request)))
    raws.update(request=request, runtime=d.canonical(runtime), election=d.canonical(election),
                review=d.canonical(review), owner=d.canonical(owner))
    return raws


def run_proof():
    d.need(sys.platform == "linux", "PROOF_REQUIRES_LINUX")
    age, keygen = sys.argv[1:]
    d.need(d.sha(Path(age).read_bytes()) == d.AGE_SHA256, "PROOF_AGE_WRONG_BYTES")
    d.need(d.sha(Path(keygen).read_bytes()) == "0a0009db842259d6717f7eeb30acb6b90d2a2eb924c6acd0a0db0ca1f1537899",
           "PROOF_KEYGEN_WRONG_BYTES")
    # /tmp is intentionally not accepted by the physical private-root walker.
    # Home ancestors must pass the operation's actual ownership/mode guards.
    with tempfile.TemporaryDirectory(prefix="f1-synthetic-", dir=str(Path.home())) as td:
        root = Path(td);os.chmod(root, 0o700)
        shutil.copyfile(age, root / "age");os.chmod(root / "age", 0o500)
        key = root / "fixture.key"
        subprocess.run([keygen, "-o", str(key)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        recipient = subprocess.check_output([keygen, "-y", str(key)], stderr=subprocess.DEVNULL).decode().strip()
        original = m.measure(str(root), str(root / "age"))
        runtime = original["runtime"]
        raws = bound_fixture(root, recipient, original)
        provider = t.FakeProvider()
        with patch.object(d, "RECIPIENT", recipient):
            result = d.run(raws, provider, clock=lambda: t.NOW, physical=True)
        d.need(result["status"] == "DIAGNOSTIC_COMPLETE_WITH_LAST_TRADE_UNKNOWN", "PROOF_PIPELINE_FAILED")
        clear = subprocess.check_output([age, "-d", "-i", str(key), str(root / d.CIPHER_NAME)], stderr=subprocess.DEVNULL)
        with tarfile.open(fileobj=io.BytesIO(clear)) as archive:
            d.need(archive.extractfile("registry.raw").read() == provider.registry and
                   archive.extractfile("bulk.raw").read() == provider.bulk, "PROOF_RAW_NOT_RETAINED")
            manifest = archive.extractfile("inventory.json").read()
            d.need(d.sha(manifest) == result["inventory_sha256"], "PROOF_INVENTORY_MISMATCH")
            analysis = json.loads(archive.extractfile("analysis.json").read())
            d.need(analysis["counts"] == result["counts"], "PROOF_COUNTS_MISMATCH")
        before = {p.name: d.sha(p.read_bytes()) for p in root.iterdir()}
        again_provider = t.FakeProvider()
        with patch.object(d, "RECIPIENT", recipient):
            again = d.run(raws, again_provider, clock=lambda: t.NOW, physical=True)
        d.need(again["code"] == "ATTEMPT_ALREADY_CONSUMED" and again_provider.calls == 0, "PROOF_REPEAT_NOT_REFUSED")
        d.need(before == {p.name: d.sha(p.read_bytes()) for p in root.iterdir()}, "PROOF_BYTES_CHANGED_ON_REPEAT")
    # A second independent SYNTHETIC fixture reaches both raw byte limits.
    # Padding is valid JSON whitespace, not a claim about all row-count or
    # parser worst cases. No real election/attempt is created or repeated.
    with tempfile.TemporaryDirectory(prefix="f1-budget-synthetic-", dir=str(Path.home())) as td:
        root = Path(td);os.chmod(root, 0o700)
        shutil.copyfile(age, root / "age");os.chmod(root / "age", 0o500)
        key = root / "fixture.key"
        subprocess.run([keygen, "-o", str(key)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        recipient = subprocess.check_output([keygen, "-y", str(key)], stderr=subprocess.DEVNULL).decode().strip()
        original = m.measure(str(root), str(root / "age"))
        raws = bound_fixture(root, recipient, original)
        provider = t.FakeProvider()
        provider.registry += b" " * (d.REGISTRY_LIMIT - len(provider.registry))
        provider.bulk += b" " * (d.BULK_LIMIT - len(provider.bulk))
        began = time.monotonic()
        with patch.object(d, "RECIPIENT", recipient):
            budget_result = d.run(raws, provider, clock=lambda: t.NOW, physical=True)
        budget_elapsed = time.monotonic() - began
        d.need(budget_result["status"] == "DIAGNOSTIC_COMPLETE_WITH_LAST_TRADE_UNKNOWN" and
               budget_elapsed < d.MAX_SECONDS and provider.calls == 2, "PROOF_MAX_RAW_BUDGET_FAILED")
        clear = subprocess.check_output([age, "-d", "-i", str(key), str(root / d.CIPHER_NAME)], stderr=subprocess.DEVNULL)
        with tarfile.open(fileobj=io.BytesIO(clear)) as archive:
            for kind in ("registry", "bulk"):
                member = archive.extractfile(kind + ".raw").read()
                d.need(d.sha(member) == budget_result["raw_hashes"][kind] and
                       len(member) == (d.REGISTRY_LIMIT if kind == "registry" else d.BULK_LIMIT),
                       "PROOF_MAX_RAW_NOT_RETAINED")
    record = {"schema": "F1_LINUX_FIXTURE_CRYPTO_RESULT_V1", "status": "PASS_FIXTURE_ONLY",
              "source_sha256": d.sha(Path(d.__file__).read_bytes()), "reference_sha256": d.REFERENCE,
              "seal_sha256": runtime["seal_sha256"], "age_sha256": d.AGE_SHA256,
              "python": "%d.%d.%d" % sys.version_info[:3], "physical_file_guards_exercised": True,
              "real_age_fixture_roundtrip": True, "cipher_to_Fable_key_proven": False,
              "raw_bytes_exact": True, "one_attempt_repeat_refused": True, "provider_calls_real": 0,
              "target_server_calls": 0, "owner_signatures_real": 0, "operational_acceptance": False}
    record.update(max_raw_byte_fixture={"registry_bytes": d.REGISTRY_LIMIT, "bulk_bytes": d.BULK_LIMIT,
                  "execution_elapsed_seconds": round(budget_elapsed, 6), "counts_small_fixture": True,
                  "all_adversarial_parser_structures_proven": False, "future_provider_latency_guaranteed": False,
                  "full_raw_roundtrip_exact": True})
    os.write(1, d.canonical(record) + b"\n")


if __name__ == "__main__":
    with patch.object(d, "AMENDMENT_SIGNATURE_ORIGINAL", d.sha(t.AMENDMENT_RAW)):
        run_proof()
