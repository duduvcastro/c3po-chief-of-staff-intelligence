"""Offline data-only builder for F2. Never dispatches, signs, fetches or runs crypto.

eligible: fixed eligible set from the F1 private bundle (decrypted by Fable), pinned bytes.
request:  REQUEST.json + OWNER_QUESTION.txt from config + review + eligible set + family bytes.
bound:    BOUND.json from REQUEST + the real owner record (never generated here).
"""
import argparse
import io
import os
from pathlib import Path
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import series_runtime as s

# F1 originals (Codex result review codex-f1-result-review-20261008-r1): exact members of the private bundle.
F1_INVENTORY_SHA256 = "29a2eed769584709508b87484c5ee9726ab64c399a28399cbf4d2423072b9bd6"
F1_REGISTRY_RAW_SHA256 = "74ac3250f389dcc7421d0219e7c9eaa82f4407e851d5ceecc1c2cbc3d47c993d"
F1_REGISTRY_RECEIPT_SHA256 = "b8a8e040fd8edcb2b2bc5eb3d5cceb62ef1cbfa897ae7c72700a4b03208226d5"
F1_CIPHER_SHA256 = "2ca5366fe821a0693ba06b928665ba81d13f299cfece4d6da8269232c82744b3"
F1_ELIGIBLE_COUNT = 5784
F1_PREVIOUS_CLOSE = "2026-10-07T20:00:00Z"


def write_new(path, raw):
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def eligible_from_f1_bundle(bundle_raw, ref):
    """Same normalizer (pinned build_registry) and same type filter as readiness_probe P / F1."""
    members = {}
    with tarfile.open(fileobj=io.BytesIO(bundle_raw), mode="r:") as archive:
        for m in archive.getmembers():
            s.need(m.isfile() and m.name not in members, "F1_BUNDLE_INVALID")
            members[m.name] = archive.extractfile(m).read()
    s.need(s.sha(members["inventory.json"]) == F1_INVENTORY_SHA256, "F1_INVENTORY_MISMATCH")
    s.need(s.sha(members["registry.raw"]) == F1_REGISTRY_RAW_SHA256, "F1_REGISTRY_MISMATCH")
    s.need(s.sha(members["registry-receipt.json"]) == F1_REGISTRY_RECEIPT_SHA256, "F1_RECEIPT_MISMATCH")
    receipt = s.strict(members["registry-receipt.json"])
    s.need(receipt["code"] is None and receipt["http_status"] == 200 and receipt["body_complete"] is True,
           "F1_RECEIPT_NOT_COMPLETE")
    received = s.stamp(receipt["received_at"])
    registry, _ = ref.build_registry(ref.Response(members["registry.raw"], received, "/api/exchange-symbol-list/US"),
                                     previous_close=s.stamp(F1_PREVIOUS_CLOSE))
    symbols = sorted({x["symbol"] for x in registry["instruments"] if x["security_type"] in ref.DAILY_ELIGIBLE_TYPES})
    s.need(len(symbols) == F1_ELIGIBLE_COUNT, "F1_ELIGIBLE_COUNT_MISMATCH")
    value = {"schema": "F2_ELIGIBLE_SET_V1", "types": list(ref.DAILY_ELIGIBLE_TYPES), "readiness_rule": s.RULE,
             "provenance": {"origin": "F1_PRIVATE_BUNDLE_REGISTRY_RAW", "f1_cipher_sha256": F1_CIPHER_SHA256,
                            "f1_inventory_sha256": F1_INVENTORY_SHA256, "registry_raw_sha256": F1_REGISTRY_RAW_SHA256,
                            "registry_received_at": receipt["received_at"], "normalizer_reference_sha256": s.REFERENCE,
                            "previous_close": F1_PREVIOUS_CLOSE,
                            "readiness_probe_p_registry_sha256_not_retained": "bccacd2ddaaf00e17f1ef82b3fec56df62b9b8b96b507b5cf019db687e315354",
                            "readiness_probe_p_eligible_count": 5782},
             "symbols": symbols}
    return s.canonical(value)


def request_from_inputs(config_raw, review_raw, eligible_raw, source_raw, seal_raw):
    config = s.strict(config_raw)
    s.need(set(config) == {"schema", "amendment7_sha256", "amendment7_signature_sha256"} and
           config["schema"] == "F2_LEAF_CONFIG_V1", "LEAF_CONFIG_INVALID")
    eligible = s.strict(eligible_raw, s.ELIGIBLE_LIMIT)
    q = {"schema": "F2_REQUEST_V1", "family": s.FAMILY, "operation": s.OPERATION, "epoch": s.EPOCH,
         "bulk_date": s.BULK_DAY, "session_close": s.SESSION_CLOSE, "slots": s.SLOTS,
         "early_seconds": s.EARLY_SECONDS, "late_seconds": s.LATE_SECONDS, "start_cutoff": s.START_CUTOFF,
         "receive_cutoff": s.RECEIVE_CUTOFF, "max_seconds": s.MAX_SECONDS, "network_seconds": s.NETWORK_SECONDS,
         "socket_seconds": s.SOCKET_SECONDS, "logical_fetch_limit_per_slot": 1, "retry_limit": 0,
         "recipient": s.RECIPIENT, "age_sha256": s.AGE_SHA256, "campaign_root": s.CAMPAIGN_ROOT,
         "source_root": s.SOURCE_ROOT, "provider_env_path": s.PROVIDER_ENV_PATH, "provider_env_key": s.PROVIDER_ENV_KEY,
         "source_sha256": s.sha(source_raw), "seal_sha256": s.sha(seal_raw), "reference_sha256": s.REFERENCE,
         "eligible_set_sha256": s.sha(eligible_raw), "eligible_count": len(eligible["symbols"]),
         "readiness_rule": s.RULE, "amendment7_sha256": config["amendment7_sha256"],
         "amendment7_signature_sha256": config["amendment7_signature_sha256"], "review_sha256": s.sha(review_raw)}
    s.validate_request(q)
    s.validate_eligible(eligible_raw, q)
    return s.canonical(q)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("eligible", "request", "bound"))
    p.add_argument("--inputs", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    inp, out = Path(a.inputs), Path(a.out)
    s.need(not out.exists(), "OUTPUT_ALREADY_EXISTS")
    here = Path(__file__).resolve().parent
    if a.command == "eligible":
        bundle = s.read_path(str((inp / "payload.bin").resolve()), s.PRIVATE_LIMIT, physical=False)
        raw = eligible_from_f1_bundle(bundle, s.load_reference(physical=False))
        out.mkdir(mode=0o700)
        write_new(out / "ELIGIBLE_SET.json", raw)
        print(s.sha(raw), len(s.strict(raw, s.ELIGIBLE_LIMIT)["symbols"]))
    elif a.command == "request":
        raw = {k: s.read_path(str((inp / (k + ".json")).resolve()), s.ELIGIBLE_LIMIT, physical=False)
               for k in ("config", "review", "ELIGIBLE_SET")}
        request = request_from_inputs(raw["config"], raw["review"], raw["ELIGIBLE_SET"],
                                      (here / "series_runtime.py").read_bytes(), (here / "SHA256SUMS").read_bytes())
        out.mkdir(mode=0o700)
        write_new(out / "REQUEST.json", request)
        write_new(out / "OWNER_QUESTION.txt", s.owner_question(request))
        write_new(out / "review.json", raw["review"])
        print(s.sha(request))
    else:
        raw = {k: s.read_path(str((inp / (("REQUEST" if k == "request" else k) + ".json")).resolve()), 1024 * 1024,
                              physical=False) for k in ("request", "owner", "review")}
        s.validate_documents(raw)
        bound = s.canonical({"schema": "F2_BOUND_V1", "documents": {k: s.strict(v) for k, v in raw.items()}})
        out.mkdir(mode=0o700)
        write_new(out / "BOUND.json", bound)
        print(s.sha(bound))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except s.Hold as e:
        print(s.safe_code(e))
        raise SystemExit(2)
