"""New offline contracts; no provider, host, binder, or production execution.

These schemas are candidates. They are not the historical K8/K9 ABI and do not
turn a fixture or an existing source file into a real CAPACITY_DAY.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone


class Hold(ValueError):
    """Only a fixed public code leaves this module; input values stay private."""


def require(condition, code):
    if not condition:
        raise Hold(code)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    def invalid(_):
        raise Hold("INVALID_JSON_NUMBER")
    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)
    except (UnicodeError, json.JSONDecodeError):
        raise Hold("INVALID_JSON") from None


def sha(value):
    require(isinstance(value, str) and
            re.fullmatch(r"[0-9a-f]{64}", value) is not None, "INVALID_HASH")
    return value


def instant(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(result.tzinfo is not None, "NAIVE_TIME")
        return result.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError):
        raise Hold("INVALID_TIME") from None


def count(value):
    require(type(value) is int and value >= 0, "INVALID_COUNT")
    return value


def bulk_series(campaign, observations):
    """Locate an observed FAIL/PASS bracket, never the first absolute crossing.

    Observations must be generated from retained raw bodies by the separately
    pinned normalizer. This analyzer checks their contracts; it does not fetch
    data or recertify that normalizer.
    """
    require(campaign["schema"] == "F2_CAMPAIGN_CANDIDATE_V1", "CAMPAIGN_SCHEMA")
    require(campaign["authority_status"] == "OWN_SIGNED", "CAMPAIGN_UNSIGNED")
    require(campaign["max_sample_seconds"] == 120, "SAMPLE_BUDGET")
    for field in ("registry_sha256", "rule_sha256", "calendar_sha256"):
        sha(campaign[field])
    slots = campaign["slots_UTC"]
    require(0 < len(slots) <= 10 and len(set(slots)) == len(slots), "SLOTS")
    times = [instant(t) for t in slots]
    require(times == sorted(times), "SLOT_ORDER")
    cut = instant(campaign["cut_UTC"])
    require(all(t + timedelta(seconds=120) < cut for t in times), "CUT_MARGIN")
    by_slot = {}
    for obs in observations:
        require(obs["schema"] == "F2_OBSERVATION_CANDIDATE_V1", "OBS_SCHEMA")
        require(obs["slot_UTC"] in slots and obs["slot_UTC"] not in by_slot,
                "DUPLICATE_OR_FOREIGN_SLOT")
        for field in ("campaign_id", "bulk_date", "registry_sha256", "rule_sha256"):
            require(obs[field] == campaign[field], "OBS_CONTEXT")
        by_slot[obs["slot_UTC"]] = obs
    first_pass = None
    previous_fail = None
    regression = False
    gaps = []
    verdicts = []
    for slot in slots:
        obs = by_slot.get(slot)
        if obs is None or obs["status"] != "COMPLETE":
            gaps.append(slot)
            verdicts.append({"slot_UTC": slot, "verdict": "UNKNOWN"})
            continue
        started = instant(obs["started_UTC"])
        received = instant(obs["received_UTC"])
        require(instant(slot) <= started < received < cut, "OBS_TIME")
        require((started - instant(slot)).total_seconds() <= 5, "NO_CATCH_UP")
        require((received - started).total_seconds() <= 120, "OBS_BUDGET")
        require(obs["http_status"] == 200 and obs["body_complete"] is True,
                "OBS_HTTP")
        sha(obs["raw_sha256"])
        eligible, present, usable = [count(obs[k]) for k in ("eligible", "present", "usable")]
        require(eligible == campaign["eligible"] and eligible >= 4000,
                "COHORT_CHANGED")
        require(usable <= present <= eligible, "COUNTS_INCONSISTENT")
        require(count(obs["duplicates"]) == count(obs["conflicts"]) == 0,
                "DUPLICATE_OR_CONFLICT")
        threshold = (eligible * 95 + 99) // 100
        passed = present >= threshold
        if passed and first_pass is None:
            first_pass = received
            bracket_fail = previous_fail
        elif not passed:
            if first_pass is not None:
                regression = True
            previous_fail = received
        verdicts.append({"slot_UTC": slot, "received_UTC": obs["received_UTC"],
                         "verdict": "PASS_THRESHOLD" if passed else "FAIL_THRESHOLD",
                         "present": present, "eligible": eligible, "required": threshold,
                         "raw_sha256": obs["raw_sha256"]})
    return {"schema": "F2_SERIES_REVIEW_CANDIDATE_V1", "observations": verdicts,
            "first_observed_pass_UTC": first_pass.isoformat() if first_pass else None,
            "preceding_observed_fail_UTC": bracket_fail.isoformat()
            if first_pass and bracket_fail else None,
            "regression": regression, "unknown_slots": gaps,
            "stable_observed_suffix": bool(first_pass) and not regression and not gaps,
            "absolute_first_crossing_known": False,
            "coverage_100_percent_certified": False, "operational_GO": False}


E6_INPUTS = ("CONTRACT.json", "template.raw", "go_admission_record.raw",
             "go_bar_manifest_record.raw", "publication_bar_manifest.raw",
             "go_admission.raw", "go_bar_manifest.raw",
             "capacity_config-primary.raw", "capacity_config-contingency_1.raw",
             "capacity_config-contingency_2.raw", "veto_view-primary.raw",
             "veto_view-contingency_1.raw", "veto_view-contingency_2.raw")
CHAIN = ("CODEX", "FABLE", "DUDU", "ACT_B", "B_CODEX", "B_FABLE", "B_DUDU")
SETS = ("primary", "contingency_1", "contingency_2")
SET_DOCUMENTS = ("contract", "template", "go_admission_record", "go_bar_manifest_record",
                 "publication_bar_manifest", "go_admission", "go_bar_manifest",
                 "capacity_config", "veto_view", "request", "dispatch_go",
                 "SUMMARY.json", "SHA256SUMS")


def decision_table(rows):
    require(rows and len({r["id"] for r in rows}) == len(rows), "DECISION_ROWS")
    blockers = []
    for row in rows:
        ready = (row["exists"] is True and row["review"] == "OWN_BYTES_ACCEPTED"
                 and row["proof"] == "OWN_LINUX_ACCEPTED" and row["authority"] == "OWN_VALID")
        if ready:
            sha(row["artifact_sha256"])
        if row["critical"] and not ready:
            blockers.append({"item": row["id"], "when": row.get("when") or "SEM_ETA_COMPROVADO"})
    return {"verdict": "NO_GO" if blockers else "GO_PREPARATION_CONDITIONAL",
            "blockers": blockers, "Sunday_actual_gates_required": True,
            "Monday_entries_guaranteed": False}


def capacity_gate(capacity, receipt_context):
    require(capacity["schema"] == "F3_CAPACITY_GATE_CANDIDATE_V1", "CAPACITY_SCHEMA")
    require(capacity["context"] == receipt_context, "CAPACITY_CONTEXT")
    require(capacity["status"] == capacity["documentary_authority"] == "VERIFIED",
            "CAPACITY_UNVERIFIED")
    require(set(capacity["inputs"]) == set(E6_INPUTS), "CAPACITY_INPUTS")
    require(set(capacity["chain"]) == set(CHAIN), "CAPACITY_CHAIN")
    require(set(capacity["sets"]) == set(SETS), "CAPACITY_SETS")
    for table in (capacity["inputs"], capacity["chain"]):
        for value in table.values():
            sha(value)
    for docs in capacity["sets"].values():
        require(set(docs) == set(SET_DOCUMENTS), "CAPACITY_SET_DOCUMENTS")
        for value in docs.values():
            sha(value)
    require(capacity["own_linux_review"] == "ACCEPTED", "CAPACITY_LINUX_REVIEW")
    # An adapter must independently verify these hashes, document semantics and
    # review originals before supplying this contract. A string alone is no GO.
    return True


def c34_dependencies(persist_request, launch_receipt, collect_request):
    """PERSIST depends on an actual launch, not a future COMPLETE collection."""
    require(launch_receipt["status"] == "COMPLETE", "LAUNCH_NOT_COMPLETE")
    require(persist_request["context"] == launch_receipt["context"] == collect_request["context"],
            "C34_CONTEXT")
    require(persist_request["launch_request_sha256"] == launch_receipt["request_sha256"],
            "C34_LAUNCH_REQUEST")
    sha(launch_receipt["receipt_sha256"])
    require("K12_COLLECT_COMPLETE" not in persist_request["required_roles"], "C34_CYCLE")
    require(instant(persist_request["not_before_UTC"]) >=
            instant(launch_receipt["view_UTC"]) + timedelta(seconds=60), "C34_EARLY")
    return {"persist_allowed_after_own_gates": True,
            "collection_before_persist": "PENDING_PERSIST",
            "collection_final_requires_actual_persist_receipt": True}


def c35_window(stop_request, launch_receipt, now_UTC):
    require(launch_receipt["status"] == "COMPLETE", "STOP_NO_LAUNCH")
    require(stop_request["context"] == launch_receipt["context"], "STOP_CONTEXT")
    require(stop_request["launch_request_sha256"] == launch_receipt["request_sha256"],
            "STOP_PREBOUND_REQUEST")
    require(type(stop_request["budget_seconds"]) is int and stop_request["budget_seconds"] >= 28,
            "STOP_BUDGET")
    start, end, now = map(instant, (stop_request["start_UTC"], stop_request["end_UTC"], now_UTC))
    require(instant(launch_receipt["finished_UTC"]) < start <= now, "STOP_NO_POSITIVE_FLOOR")
    latest = min(end - timedelta(seconds=stop_request["budget_seconds"]),
                 instant(stop_request["view_UTC"]) - timedelta(seconds=25))
    require(now <= latest and latest > start, "STOP_NO_MARGIN")
    return {"latest_start_UTC": latest.isoformat(),
            "remaining_seconds": (latest - now).total_seconds(), "operational_GO": False}


def night_authorization(envelope, question, owner, actual_context, gates, now_UTC):
    """New candidate for H16. Does not reinterpret the historical IND protocol."""
    require(envelope["schema"] == "H16_PREAUTH_CANDIDATE_V1", "H16_SCHEMA")
    require(envelope["context"] == actual_context, "H16_CONTEXT")
    require(question["request_sha256"] == owner["request_sha256"] == digest(canonical(envelope)),
            "H16_REQUEST")
    require(owner["question_sha256"] == digest(canonical(question)), "H16_QUESTION")
    require(owner["literal"] == "Assino" and owner["channel"] == "REGISTRO_PELA_FABLE",
            "H16_OWNER")
    signed, published, now = map(instant, (owner["signed_at_UTC"], question["published_UTC"], now_UTC))
    brt = timezone(timedelta(hours=-3))
    require(7 <= signed.astimezone(brt).hour < 22, "H16_OWNER_UNAVAILABLE")
    require(published <= signed < instant(envelope["start_UTC"]) <= now,
            "H16_SIGNATURE_TIME")
    require(now + timedelta(seconds=envelope["budget_seconds"]) < instant(envelope["end_UTC"]),
            "H16_WINDOW")
    require(envelope["required_gates"] and set(gates) == set(envelope["required_gates"]), "H16_GATES")
    require(all(gates[k]["status"] == "COMPLETE" and gates[k]["context"] == actual_context
                for k in gates), "H16_PREDECESSOR")
    for k in gates:
        sha(gates[k]["receipt_sha256"])
    require(envelope["authority_status"] == "NEW_MODEL_ACCEPTED", "H16_AUTHORITY_PENDING")
    return {"decision": "CANDIDATE_GATES_MET", "new_owner_question_needed": False,
            "old_IND_reused": False, "operational_GO": False}
