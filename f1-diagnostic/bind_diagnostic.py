"""Offline data-only leaf builder. Never dispatches, signs, fetches, or runs crypto."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import diagnostic_runtime as d


def write_new(path, raw):
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def request_from_inputs(config_raw, election_raw, runtime_raw, review_raw, signature_raw, source_raw, seal_raw):
    config = d.strict(config_raw)
    need_keys = {"schema", "execution_date", "not_before", "not_after", "age_path"}
    d.need(set(config) == need_keys and config["schema"] == "F1_LEAF_CONFIG_V1", "LEAF_CONFIG_INVALID")
    election, runtime = d.strict(election_raw), d.strict(runtime_raw)
    d.strict(review_raw)
    d.strict(signature_raw)
    q = {"schema": "F1_REQUEST_V1", "operation": d.OPERATION, "epoch": d.EPOCH,
         "execution_date": config["execution_date"], "not_before": config["not_before"], "not_after": config["not_after"],
         "max_seconds": d.MAX_SECONDS, "session_date": d.COMPARISON_SESSION, "bulk_date": d.BULK_DAY,
         "previous_close": d.PREVIOUS_CLOSE, "recipient": d.RECIPIENT,
         "amendment_sha256": d.AMENDMENT, "design_sha256": d.DESIGN, "source_sha256": d.sha(source_raw),
         "reference_sha256": d.REFERENCE, "seal_sha256": d.sha(seal_raw), "election_sha256": d.sha(election_raw),
         "runtime_sha256": d.sha(runtime_raw), "review_sha256": d.sha(review_raw),
         "amendment_signature_sha256": d.sha(signature_raw), "private_root": election["private_root"],
         "parent_identities": election["parent_identities"], "age_path": config["age_path"],
         "age_sha256": d.AGE_SHA256, "budget_seconds": {"network": 60, "cipher": 60},
         "logical_fetch_limit": 2, "retry_limit": 0}
    d.validate_window(q)
    d.need(runtime["source_sha256"] == q["source_sha256"] and runtime["seal_sha256"] == q["seal_sha256"],
           "RUNTIME_OF_OTHER_BYTES")
    result = d.canonical(q)
    d.validate_context({"request": result, "election": election_raw, "runtime": runtime_raw,
                        "review": review_raw, "amendment_signature": signature_raw}, d.stamp(q["not_before"]))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("measurement", "amendment", "config", "request", "bound"))
    p.add_argument("--inputs", required=True, help="Private directory of canonical inputs; no generated evidence.")
    p.add_argument("--out", required=True, help="Fresh private directory on the operator's workstation.")
    p.add_argument("--execution-date", choices=tuple(d.WINDOWS), help="For config only; no date is inferred.")
    a = p.parse_args()
    inp, out = Path(a.inputs), Path(a.out)
    d.need(not out.exists(), "OUTPUT_ALREADY_EXISTS")
    if a.command == "config":
        d.need(a.execution_date is not None, "EXECUTION_DATE_REQUIRED")
        measurement = d.strict(d.read_regular(str(inp / "measurement.json"), 1024 * 1024))
        day = a.execution_date
        hour = "20" if day == "2026-10-08" else "17"
        config = {"schema": "F1_LEAF_CONFIG_V1", "execution_date": day,
                  "not_before": day + "T" + hour + ":26:00Z", "not_after": day + "T" + hour + ":33:39Z",
                  "age_path": measurement["age_path"]}
        out.mkdir(mode=0o700)
        write_new(out / "config.json", d.canonical(config))
    elif a.command == "amendment":
        original = d.read_regular(str(inp / "amendment-original.json"), 65536)
        normalized = d.canonical(d.amendment_record(original))
        out.mkdir(mode=0o700)
        write_new(out / "amendment_signature.json", normalized)
    elif a.command == "measurement":
        value = d.strict(d.read_regular(str(inp / "MEASUREMENT_SET.json"), 1024 * 1024))
        d.need(set(value) == {"measurement", "runtime", "election"}, "MEASUREMENT_SET_INVALID")
        d.need(value["runtime"]["measurement_record_sha256"] == d.sha(d.canonical(value["measurement"])),
               "MEASUREMENT_PIN_INVALID")
        out.mkdir(mode=0o700)
        for k, v in value.items():
            write_new(out / (k + ".json"), d.canonical(v))
    elif a.command == "request":
        names = ("config", "election", "runtime", "review", "amendment_signature")
        raw = {k: d.read_regular(str(inp / (k + ".json")), 1024 * 1024) for k in names}
        request = request_from_inputs(raw["config"], raw["election"], raw["runtime"], raw["review"], raw["amendment_signature"],
                                      d.read_regular(str(Path(__file__).with_name("diagnostic_runtime.py")), 1024 * 1024),
                                      d.read_regular(str(Path(__file__).with_name("SHA256SUMS")), 1024 * 1024))
        out.mkdir(mode=0o700)
        write_new(out / "REQUEST.json", request)
        write_new(out / "OWNER_QUESTION.txt", d.owner_question(request))
        for k in ("election", "runtime", "review", "amendment_signature"):
            write_new(out / (k + ".json"), raw[k])
    else:
        raw = {k: d.read_regular(str(inp / (("REQUEST" if k == "request" else k) + ".json")), 1024 * 1024)
               for k in ("request", "owner", "election", "runtime", "review", "amendment_signature")}
        q = d.strict(raw["request"])
        # Validate at the future window start without contacting any runtime. This
        # cannot certify physical identity or produce authority; those are inputs.
        d.validate_documents(raw, d.stamp(q["not_before"]))
        out.mkdir(mode=0o700)
        write_new(out / "BOUND.json", d.canonical({"schema": "F1_BOUND_V1", "documents": {k: d.strict(v) for k, v in raw.items()}}))
        for k, v in raw.items():
            write_new(out / (k + ".json"), v)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except d.Hold as e:
        print(d.safe_code(e))
        raise SystemExit(2)
