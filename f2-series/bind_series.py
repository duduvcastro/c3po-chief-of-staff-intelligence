"""Offline data-only builder for F2 (as F1 bind_diagnostic). Never dispatches, signs, fetches or runs crypto.

eligible:    fixed eligible set from the F1 private bundle (decrypted by Fable), pinned bytes.
measurement: split MEASUREMENT_SET.json (private stdout of `install_series.py measure`) into canonical
             measurement.json / runtime.json / election.json (record hash checked).
amendment:   wrap the ORIGINAL Emenda 7 signature file bytes (amendment-original.json, opaque, base64)
             after checking them against config.json (document hash + sha256 of the original bytes).
request:     REQUEST.json + OWNER_QUESTION.txt from config + review + runtime + election +
             amendment_signature + ELIGIBLE_SET + this family's bytes.
bound:       BOUND.json from REQUEST + the real owner record (never generated here) + the context.
"""
import argparse
import io
import os
from pathlib import Path
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import series_runtime as s


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
    s.need(s.sha(members["inventory.json"]) == s.F1_INVENTORY_SHA256, "F1_INVENTORY_MISMATCH")
    s.need(s.sha(members["registry.raw"]) == s.F1_REGISTRY_RAW_SHA256, "F1_REGISTRY_MISMATCH")
    s.need(s.sha(members["registry-receipt.json"]) == s.F1_REGISTRY_RECEIPT_SHA256, "F1_RECEIPT_MISMATCH")
    receipt = s.strict(members["registry-receipt.json"])
    s.need(receipt["code"] is None and receipt["http_status"] == 200 and receipt["body_complete"] is True,
           "F1_RECEIPT_NOT_COMPLETE")
    received = s.stamp(receipt["received_at"])
    registry, _ = ref.build_registry(ref.Response(members["registry.raw"], received, "/api/exchange-symbol-list/US"),
                                     previous_close=s.stamp(s.F1_PREVIOUS_CLOSE))
    symbols = sorted({x["symbol"] for x in registry["instruments"] if x["security_type"] in ref.DAILY_ELIGIBLE_TYPES})
    s.need(len(symbols) == s.ELIGIBLE_COUNT, "F1_ELIGIBLE_COUNT_MISMATCH")
    value = {"schema": "F2_ELIGIBLE_SET_V1", "types": list(ref.DAILY_ELIGIBLE_TYPES), "readiness_rule": s.RULE,
             "provenance": {"origin": "F1_PRIVATE_BUNDLE_REGISTRY_RAW", "f1_cipher_sha256": s.F1_CIPHER_SHA256,
                            "f1_inventory_sha256": s.F1_INVENTORY_SHA256, "registry_raw_sha256": s.F1_REGISTRY_RAW_SHA256,
                            "registry_received_at": receipt["received_at"], "normalizer_reference_sha256": s.REFERENCE,
                            "previous_close": s.F1_PREVIOUS_CLOSE,
                            "readiness_probe_p_registry_sha256_not_retained": "bccacd2ddaaf00e17f1ef82b3fec56df62b9b8b96b507b5cf019db687e315354",
                            "readiness_probe_p_eligible_count": 5782},
             "symbols": symbols}
    return s.canonical(value)


def split_measurement(raw):
    value = s.strict(raw, 4 * 1024 * 1024)
    s.need(set(value) == {"measurement", "runtime", "election"}, "MEASUREMENT_SET_INVALID")
    m, runtime, election = value["measurement"], value["runtime"], value["election"]
    s.need(runtime["measurement_record_sha256"] == s.sha(s.canonical(m)), "MEASUREMENT_PIN_INVALID")
    s.need(m["election"] == election and
           all(runtime[k] == m[k] for k in s.RUNTIME_KEYS - {"schema", "measurement_record_sha256"}),
           "MEASUREMENT_SET_INCONSISTENT")
    return {k: s.canonical(v) for k, v in value.items()}


def amendment_from_original(original_raw, config_raw):
    config = parse_config(config_raw)
    wrapper = s.amendment_wrapper(original_raw)
    s.validate_amendment(wrapper, config)   # document hash and sha256(original bytes) against config
    return s.canonical(wrapper)


def parse_config(config_raw):
    config = s.strict(config_raw)
    s.need(set(config) == {"schema", "amendment7_sha256", "amendment7_signature_sha256"} and
           config["schema"] == "F2_LEAF_CONFIG_V1" and s.pin(config["amendment7_sha256"]) and
           s.pin(config["amendment7_signature_sha256"]), "LEAF_CONFIG_INVALID")
    return config


def request_value(config_raw, review_raw, runtime_raw, election_raw, eligible_raw, source_raw, seal_raw):
    """Unvalidated REQUEST dict (tests use it to build deliberately wrong requests)."""
    config = parse_config(config_raw)
    eligible = s.strict(eligible_raw, s.ELIGIBLE_LIMIT)
    count = len(eligible["symbols"])
    return {"schema": "F2_REQUEST_V2", "family": s.FAMILY, "operation": s.OPERATION, "epoch": s.EPOCH,
            "bulk_date": s.BULK_DAY, "session_close": s.SESSION_CLOSE, "slots": s.SLOTS,
            "early_seconds": s.EARLY_SECONDS, "late_seconds": s.LATE_SECONDS, "start_cutoff": s.START_CUTOFF,
            "receive_cutoff": s.RECEIVE_CUTOFF, "owner_deadline": s.OWNER_DEADLINE,
            "clock_skew_seconds": s.CLOCK_SKEW_SECONDS, "max_seconds": s.MAX_SECONDS,
            "network_seconds": s.NETWORK_SECONDS, "socket_seconds": s.SOCKET_SECONDS,
            "logical_fetch_limit_per_slot": 1, "retry_limit": 0, "recipient": s.RECIPIENT, "age_sha256": s.AGE_SHA256,
            "campaign_root": s.CAMPAIGN_ROOT, "source_root": s.SOURCE_ROOT, "family_dir": s.FAMILY_DIR,
            "provider_env_path": s.PROVIDER_ENV_PATH, "provider_env_key": s.PROVIDER_ENV_KEY,
            "source_sha256": s.sha(source_raw), "seal_sha256": s.sha(seal_raw), "reference_sha256": s.REFERENCE,
            "eligible_set_sha256": s.sha(eligible_raw), "eligible_count": count,
            "eligible_provenance": s.eligible_provenance(s.sha(eligible_raw), count), "readiness_rule": s.RULE,
            "amendment7_sha256": config["amendment7_sha256"],
            "amendment7_signature_sha256": config["amendment7_signature_sha256"],
            "runtime_sha256": s.sha(runtime_raw), "election_sha256": s.sha(election_raw), "review_sha256": s.sha(review_raw)}


def request_from_inputs(config_raw, review_raw, runtime_raw, election_raw, signature_raw, eligible_raw,
                        source_raw, seal_raw):
    q = request_value(config_raw, review_raw, runtime_raw, election_raw, eligible_raw, source_raw, seal_raw)
    raw = s.canonical(q)
    s.validate_context({"request": raw, "review": review_raw, "runtime": runtime_raw, "election": election_raw,
                        "amendment_signature": signature_raw})
    s.validate_eligible(eligible_raw, q)
    return raw


def read(path, limit=4 * 1024 * 1024):
    return s.read_path(str(Path(path).resolve()), limit, physical=False)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=("eligible", "measurement", "amendment", "request", "bound"))
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
    elif a.command == "measurement":
        parts = split_measurement(read(inp / "MEASUREMENT_SET.json"))
        out.mkdir(mode=0o700)
        for k, v in parts.items():
            write_new(out / (k + ".json"), v)
        print("runtime", s.sha(parts["runtime"]), "election", s.sha(parts["election"]))
    elif a.command == "amendment":
        raw = amendment_from_original(read(inp / "amendment-original.json", 65536), read(inp / "config.json"))
        out.mkdir(mode=0o700)
        write_new(out / "amendment_signature.json", raw)
        print(s.sha(raw))
    elif a.command == "request":
        raw = {k: read(inp / (k + ".json")) for k in
               ("config", "review", "runtime", "election", "amendment_signature", "ELIGIBLE_SET")}
        request = request_from_inputs(raw["config"], raw["review"], raw["runtime"], raw["election"],
                                      raw["amendment_signature"], raw["ELIGIBLE_SET"],
                                      (here / "series_runtime.py").read_bytes(), (here / "SHA256SUMS").read_bytes())
        out.mkdir(mode=0o700)
        write_new(out / "REQUEST.json", request)
        write_new(out / "OWNER_QUESTION.txt", s.owner_question(request))
        for k in ("review", "runtime", "election", "amendment_signature"):
            write_new(out / (k + ".json"), raw[k])
        print(s.sha(request))
    else:
        raw = {k: read(inp / (("REQUEST" if k == "request" else k) + ".json"))
               for k in sorted(s.BOUND_DOCUMENTS)}
        s.validate_documents(raw)
        bound = s.canonical({"schema": "F2_BOUND_V2", "documents": {k: s.strict(v) for k, v in raw.items()}})
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
