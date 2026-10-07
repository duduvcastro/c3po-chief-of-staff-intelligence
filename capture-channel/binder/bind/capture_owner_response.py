"""Offline validation of a direct owner comment. Never signs, connects or dispatches.

The caller must obtain both snapshots with authenticated GitHub API GETs. Serialized
API metadata is not a cryptographic proof of a human; the live bridge and its dated
authority must be reviewed separately before this component can authorize anything.
"""
import datetime as dt
import hashlib
import json
import re

REPO = "duduvcastro/c3po-chief-of-staff-intelligence"
ISSUE_URL = "https://api.github.com/repos/" + REPO + "/issues/429"
OWNER_ID = 313137248
OWNER_LOGIN = "duduvcastro"
FIELDS = {"schema", "answer", "session", "run_id", "run_attempt", "nonce", "sheet_sha256"}


class Refused(ValueError):
    pass


def need(value, code):
    if not value:
        raise Refused(code)


def strict(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, "DUPLICATE_OWNER_FIELD")
            out[key] = value
        return out
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(Refused("OWNER_CONSTANT")))
    except (TypeError, json.JSONDecodeError):
        raise Refused("OWNER_BODY_INVALID")


def instant(value):
    need(type(value) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value), "OWNER_TIME_INVALID")
    try:
        return dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise Refused("OWNER_TIME_INVALID")


def validate_context(context):
    need(type(context) is dict and set(context) ==
         {"session", "run_id", "run_attempt", "nonce", "sheet_sha256", "question_created_at",
          "question_body_sha256", "prepared_at_utc", "not_before", "not_after"}, "OWNER_CONTEXT_INVALID")
    need(context["session"] == "2026-10-08", "OWNER_SESSION_SCOPE")
    need(type(context["run_id"]) is str and re.fullmatch(r"[1-9][0-9]{5,19}", context["run_id"]), "OWNER_RUN_INVALID")
    need(type(context["run_attempt"]) is int and context["run_attempt"] == 1, "OWNER_RUN_RETRY_FORBIDDEN")
    for key, pattern in (("nonce", r"[0-9a-f]{32}"), ("sheet_sha256", r"[0-9a-f]{64}"),
                         ("question_body_sha256", r"[0-9a-f]{64}")):
        need(type(context[key]) is str and re.fullmatch(pattern, context[key]), "OWNER_CONTEXT_PIN")
    start, end = instant(context["not_before"]), instant(context["not_after"])
    need(start == instant("2026-10-08T11:50:00Z") and end == instant("2026-10-08T12:30:00Z"), "OWNER_SIGNATURE_BAND")
    prepared, published = instant(context["prepared_at_utc"]), instant(context["question_created_at"])
    need(prepared <= published <= end, "OWNER_QUESTION_ORDER")
    return start, end, published


def validate_owner_response(first, readback, context, observed_at, used_comment_ids=()):
    """Return a readback record, not a signature or operational permission."""
    start, end, question_time = validate_context(context)
    need(type(first) is dict and type(readback) is dict and first == readback, "OWNER_READBACK_CHANGED")
    comment = readback
    cid = comment.get("id")
    need(type(cid) is int and cid > 0 and cid not in used_comment_ids, "OWNER_COMMENT_REPLAY")
    need(comment.get("issue_url") == ISSUE_URL and
         comment.get("url") == ISSUE_URL.rsplit("/issues/", 1)[0] + "/issues/comments/" + str(cid), "OWNER_COMMENT_LOCATION")
    user = comment.get("user")
    need(type(user) is dict and user.get("login") == OWNER_LOGIN and user.get("id") == OWNER_ID and
         type(user.get("id")) is int and user.get("type") == "User", "OWNER_COMMENT_AUTHOR")
    need(comment.get("author_association") == "OWNER" and "performed_via_github_app" in comment and
         comment["performed_via_github_app"] is None,
         "OWNER_FORWARDED_OR_APP_COMMENT")
    created = instant(comment.get("created_at"))
    need(comment.get("updated_at") == comment.get("created_at"), "OWNER_COMMENT_EDITED")
    observed = instant(observed_at)
    need(start <= created <= end and question_time <= created <= observed <= end, "OWNER_SIGNATURE_ORDER_OR_DEADLINE")
    body = comment.get("body")
    need(type(body) is str and len(body.encode()) <= 1024, "OWNER_BODY_INVALID")
    answer = strict(body)
    need(type(answer) is dict and set(answer) == FIELDS and
         answer.get("schema") == "CAPTURE_OWNER_ANSWER_V1" and answer.get("answer") == "Assino", "OWNER_ANSWER_NOT_LITERAL")
    for key in ("session", "run_id", "run_attempt", "nonce", "sheet_sha256"):
        need(type(answer[key]) is type(context[key]) and answer[key] == context[key], "OWNER_ANSWER_CONTEXT_MISMATCH")
    return {"schema": "CAPTURE_OWNER_API_READBACK_V1", "status": "MATCHED_DIRECT_COMMENT_NOT_SIGNED",
            "owner_login": OWNER_LOGIN, "owner_id": OWNER_ID, "comment_id": cid,
            "created_at": comment["created_at"], "observed_at": observed_at,
            "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
            "answer_verbatim": "Assino", "context": dict(context),
            "is_operational_authority": False, "independent_human_crypto_proof": False}
