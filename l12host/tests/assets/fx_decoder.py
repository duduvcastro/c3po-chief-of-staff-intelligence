"""SYNTHETIC FIXTURE decoder of FIXTURE_STEP_RECEIPT_V1 (tests only; FIXTURE mode is refused on the host)."""
import json


def decode(raw, role, context, request_sha256, bound_sha256):
    body = json.loads(raw)
    if not (type(body) is dict and body.get("schema") == "FIXTURE_STEP_RECEIPT_V1" and body.get("role") == role
            and body.get("status") == "COMPLETE" and type(body.get("completed_at")) is str):
        raise ValueError("FIXTURE_RECEIPT_NOT_COMPLETE")
    return {"status": "COMPLETE", "completed_at": body["completed_at"]}
