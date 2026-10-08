"""H16 V2: a specific prior authorization, actual night receipts, one fixed reader.

The signed request selects actual receipt roles and their producers, not invented
future receipt hashes. It neither changes E6's ABI nor creates an overnight owner
question. The controller supplies originals and reserves the attempt first.
"""
from datetime import timedelta, timezone
from common import canonical, context, digest, fields, instant, linked_receipt, need, sha

BRT = timezone(timedelta(hours=-3))


def authorize(request, question, owner, authority, gates, now):
    ctx = context(request["context"])
    need(request["schema"] == "SERVER_FAMILY_REQUEST_V2" and request["operation"] == "F5_H16_READ", "H16_REQUEST_MODEL")
    fields(request["payload"], ("reader_id", "reader_source_sha256", "receipt_selectors", "max_lateness_seconds"), "H16_PAYLOAD")
    p = request["payload"]
    need(authority["schema"] == "H16_MODEL_AUTHORITY_V2" and authority["context"] == ctx
         and authority["request_sha256"] == digest(canonical(request)), "H16_AUTHORITY_BINDING")
    need(authority["reader_id"] == p["reader_id"] and authority["reader_source_sha256"] == sha(p["reader_source_sha256"])
         and authority["model_review_sha256"] == request["pins"]["model_review_sha256"], "H16_MODEL_REVIEW")
    sha(authority["model_review_sha256"])
    need(authority["required_selectors_sha256"] == digest(canonical(p["receipt_selectors"])), "H16_SELECTORS_AUTHORITY")
    req_sha = digest(canonical(request))
    need(question["schema"] == "SERVER_OWNER_QUESTION_V2" and owner["schema"] == "SERVER_OWNER_RESPONSE_V2"
         and question["request_sha256"] == owner["request_sha256"] == req_sha, "H16_QUESTION_REQUEST")
    need(owner["question_sha256"] == digest(canonical(question)) and owner["literal"] == "Assino"
         and owner["channel"] == "REGISTRO_PELA_FABLE", "H16_OWNER_LITERAL")
    signed, published = instant(owner["signed_at_UTC"]), instant(question["published_UTC"])
    start, end = instant(request["start_UTC"]), instant(request["end_UTC"])
    # Strict deadline is 21:45, not the last instant before 22:00.
    local = signed.astimezone(BRT)
    need(7 <= local.hour and (local.hour, local.minute, local.second, local.microsecond) <= (21, 45, 0, 0), "H16_OWNER_OFFLINE_OR_LATE")
    need(published <= signed < start <= now < end, "H16_SIGNATURE_OR_WINDOW")
    need(start.astimezone(BRT).date().isoformat() == ctx["session"] and start.astimezone(BRT).hour == 6,
         "H16_MORNING_SLOT")
    need(signed.astimezone(BRT).date() < start.astimezone(BRT).date(), "H16_SIGNATURE_NOT_PRIOR_NIGHT")
    need(type(p["max_lateness_seconds"]) is int and 0 <= p["max_lateness_seconds"] <= 5
         and (now - start).total_seconds() <= p["max_lateness_seconds"], "H16_NO_CATCHUP")
    need(type(request["budget_seconds"]) is int and 0 < request["budget_seconds"] <= 120
         and now + timedelta(seconds=request["budget_seconds"]) < end, "H16_BUDGET")
    selectors = p["receipt_selectors"]
    need(type(selectors) is dict and set(selectors) == set(request["required_gates"]) == set(gates)
         and {"commit_result", "publish_launch", "CAPACITY_DAY", "K12_FINAL"} <= set(selectors), "H16_GATE_SET")
    receipts = {}
    for role, selector in selectors.items():
        fields(selector, ("context", "operation", "producer_sha256", "earliest_UTC", "latest_UTC", "max_age_seconds"), "H16_SELECTOR_FIELDS")
        gate_ctx = context(selector["context"])
        need(all(gate_ctx[k] == ctx[k] for k in ("model", "epoch", "session", "release_sha256")), "H16_GATE_EPOCH_SESSION")
        sha(selector["producer_sha256"])
        need(type(selector["max_age_seconds"]) is int and 0 < selector["max_age_seconds"] <= 18 * 3600, "H16_GATE_MAX_AGE")
        raw = gates[role]
        receipt = linked_receipt(raw, gate_ctx, operation=selector["operation"])
        need(receipt["producer_sha256"] == selector["producer_sha256"], "H16_GATE_PRODUCER")
        finished = instant(receipt["finished_UTC"])
        need(instant(selector["earliest_UTC"]) <= finished <= instant(selector["latest_UTC"]) <= start
             and 0 <= (now - finished).total_seconds() <= selector["max_age_seconds"], "H16_GATE_TIME")
        detail = receipt["detail"]
        if role == "CAPACITY_DAY":
            need(detail["status"] == detail["documentary_authority"] == "VERIFIED"
                 and detail["capacity_gate_verified"] is True, "H16_CAPACITY_NOT_VERIFIED")
        if role == "K12_FINAL":
            need(detail["collection"] == "VERIFIED" and detail["manifest_verified"] is True, "H16_K12_NOT_FINAL")
        receipts[role] = digest(raw)
    return {"request_sha256": req_sha, "actual_receipts": receipts,
            "reader_id": p["reader_id"], "reader_source_sha256": p["reader_source_sha256"],
            "new_owner_question": False, "historical_IND_reused": False}


def execute(request, question, owner, authority, gates, *, clock, recheck, reader):
    binding = authorize(request, question, owner, authority, gates, instant(clock()))
    recheck()
    need(reader.reader_id == binding["reader_id"] and reader.source_sha256 == binding["reader_source_sha256"], "H16_READER_UNBOUND")
    # The registry chooses one fixed reader ABI/argv. No arbitrary shell, query,
    # signature, provider request or activation fallback is accepted here.
    result = reader.read_once(request, binding)
    recheck()
    need(result["schema"] == "H16_READER_RESULT_V2" and result["status"] == "COMPLETE"
         and result["context"] == request["context"] and result["request_sha256"] == binding["request_sha256"]
         and result["actual_receipts"] == binding["actual_receipts"], "H16_READER_RESULT")
    need(type(result["checks"]) is dict and result["checks"] and all(v is True for v in result["checks"].values()),
         "H16_READER_CHECKS")
    need(instant(clock()) < instant(request["end_UTC"]), "H16_END_CUT")
    return {"reader_result_sha256": digest(canonical(result)), "actual_receipts": binding["actual_receipts"],
            "check_count": len(result["checks"]), "owner_question_sent": False}
