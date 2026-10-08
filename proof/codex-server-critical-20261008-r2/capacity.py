"""F3 V2: new epoch documentary producer and actual K8 result verifier.

build_documents produces BOUND_FOR_REVIEW_ONLY, never capacity VERIFIED.
verify_day requires every original input, chain, set, actual K8 result and review.
Historical October 5--9 authorities/calendars cannot be date-substituted here.
"""
from datetime import date, timedelta
from common import canonical, context, digest, fields, hash_value, instant, need, sha, strict

CHAIN = ("CODEX", "FABLE", "DUDU", "ACT_B", "B_CODEX", "B_FABLE", "B_DUDU")
SETS = ("primary", "contingency_1", "contingency_2")
PHASES = ("admission", "bar_manifest", "quote_refresh", "quote_capture")
INPUTS = ("CONTRACT.json", "template.raw", "go_admission_record.raw", "go_bar_manifest_record.raw",
          "publication_bar_manifest.raw", "go_admission.raw", "go_bar_manifest.raw", "capacity_config-primary.raw",
          "capacity_config-contingency_1.raw", "capacity_config-contingency_2.raw", "veto_view-primary.raw",
          "veto_view-contingency_1.raw", "veto_view-contingency_2.raw")
SET_ROLES = ("contract", "template", "go_admission_record", "go_bar_manifest_record", "publication_bar_manifest",
             "go_admission", "go_bar_manifest", "capacity_config", "veto_view", "request", "dispatch_go")
RULE = "OPEN_FIRST_THEN_EXISTING_CAUSAL_ORDER_V1_PROPOSED"


def issued(raw, kind):
    """New originals use the same explicit documentary wrapper as the old format.

    Only ISSUED typed JSON is accepted. Review copies/DRAFT and legacy signatures
    lacking their own new epoch are deliberately not normalized as authority.
    """
    value = fields(strict(raw), ("schema", "kind", "state", "body"), "CAP_DOCUMENT_FIELDS")
    need(value["schema"] == "R2D2_DOCUMENTARY_EVIDENCE_V1" and value["kind"] == kind
         and value["state"] == "ISSUED" and type(value["body"]) is dict, "CAP_DOCUMENT_UNISSUED")
    need(raw == canonical(value), "CAP_DOCUMENT_NOT_CANONICAL")
    return value["body"]


def same_scope(body, ctx, sessions):
    need(body.get("epoch") == ctx["epoch"] and body.get("first_session") == sessions[0]
         and body.get("authorized_sessions") == sessions and ctx["session"] in sessions, "CAP_DOCUMENT_SCOPE")


def owner_evidence(body):
    evidence = fields(body["owner_evidence"], ("verbatim", "channel", "signed_at_utc", "request_sha256", "question_sha256"), "CAP_OWNER_FIELDS")
    need(evidence["verbatim"] == "Assino" and evidence["channel"] == "REGISTRO_PELA_FABLE", "CAP_OWNER_LITERAL")
    sha(evidence["request_sha256"]); sha(evidence["question_sha256"])
    signed = instant(evidence["signed_at_utc"])
    return signed


def model(order, policy, calendar, release, chain, ctx):
    context(ctx)
    need(order["schema"] == "SERVER_EPOCH_ORDER_V2" and order["epoch"] == ctx["epoch"]
         and order["capacity"] == 550 and type(order["capacity"]) is int and order["rule"] == RULE,
         "CAP_NEW_ORDER")
    sessions = order["authorized_sessions"]
    need(type(sessions) is list and sessions and sessions == sorted(set(sessions))
         and all(type(d) is str and date.fromisoformat(d).isoformat() == d and d >= "2026-10-12" for d in sessions)
         and ctx["session"] in sessions, "CAP_SESSIONS")
    need(calendar["schema"] == "PINNED_SESSION_CALENDAR_V2" and calendar["epoch"] == ctx["epoch"]
         and set(calendar["sessions"]) == set(sessions), "CAP_CALENDAR_SCOPE")
    sha(calendar["origin_sha256"])
    for day, session in calendar["sessions"].items():
        need(instant(session["open_UTC"]) < instant(session["close_UTC"])
             and instant(session["open_UTC"]).date().isoformat() == day, "CAP_CALENDAR_CLOCK")
    need(order["calendar_sha256"] == hash_value(calendar), "CAP_CALENDAR_PIN")
    need(policy["schema"] == "SERVER_CAPACITY_POLICY_V2" and policy["epoch"] == ctx["epoch"]
         and policy["capacity"] == 550 and policy["rule"] == RULE and policy["automatic_retry"] is False,
         "CAP_POLICY")
    need(policy["order_sha256"] == hash_value(order) and policy["release_sha256"] == ctx["release_sha256"]
         and policy["calendar_sha256"] == hash_value(calendar), "CAP_POLICY_PINS")
    need(instant(policy["valid_from_UTC"]) <= instant(calendar["sessions"][sessions[0]]["open_UTC"])
         and instant(policy["valid_until_UTC"]) >= instant(calendar["sessions"][sessions[-1]]["close_UTC"]), "CAP_POLICY_TIME")
    need(release["schema"] == "SERVER_RELEASE_RECERTIFIED_V2" and release["epoch"] == ctx["epoch"]
         and release["release_sha256"] == ctx["release_sha256"] and release["package_sha256"] == policy["package_sha256"],
         "CAP_RELEASE")
    sha(release["package_sha256"])
    need(set(release["receipts"]) == {"M1", "M2", "M3", "WIND_DOWN_28", "INPUT_RECEIPTS"}, "CAP_RECERTIFICATION_SET")
    for pin in release["receipts"].values(): sha(pin)
    need(type(chain) is dict and set(chain) == set(CHAIN), "CAP_CHAIN_SET")
    pins = {label: digest(raw) for label, raw in chain.items()}
    need(len(set(pins.values())) == len(CHAIN), "CAP_CHAIN_NOT_DISTINCT")
    records = {label: issued(raw, "ACT_B" if label == "ACT_B" else "APPROVAL") for label, raw in chain.items()}
    previous = None
    for role in ("CODEX", "FABLE", "DUDU"):
        row = records[role]; same_scope(row, ctx, sessions)
        need(row["role"] == role and row["decision"] == "APPROVED" and row["previous_sha"] == previous
             and row["document_sha256"] == hash_value(order), "CAP_ACT_A_CHAIN")
        if role == "DUDU": owner_evidence(row)
        previous = pins[role]
    act = records["ACT_B"]; same_scope(act, ctx, sessions)
    need(act["status"] == "ACCEPTED" and act["chain_head"] == pins["DUDU"] and act["order_sha"] == hash_value(order)
         and act["policy_sha"] == hash_value(policy) and act["capacity"] == 550 and act["cut_rule"] == RULE
         and act["automatic_retry"] is False, "CAP_ACT_B_BINDING")
    need(act["causal_order"] == {"primary": "ADV_DESC", "tie_break": "SYMBOL_ASC", "cut": "TAIL_NEW_ONLY"}, "CAP_CAUSAL_RULE")
    need(set(act["act_a_scope_map"]) == {"CODEX", "FABLE", "DUDU"}, "CAP_ACT_A_MAP")
    for role in ("CODEX", "FABLE", "DUDU"):
        row = act["act_a_scope_map"][role]; same_scope(row, ctx, sessions)
        need(row["signature_sha"] == pins[role] and row["document_sha256"] == hash_value(order), "CAP_ACT_A_MAP_PIN")
    previous = None
    for role in ("CODEX", "FABLE", "DUDU"):
        row = records["B_" + role]; same_scope(row, ctx, sessions)
        need(row["role"] == role and row["decision"] == "APPROVED" and row["previous_sha"] == previous
             and row["body_sha"] == pins["ACT_B"] and row["act_a_head"] == pins["DUDU"], "CAP_ACT_B_CHAIN")
        if role == "DUDU": owner_evidence(row)
        previous = pins["B_" + role]
    return sessions, records, pins


def template(ctx, order, calendar):
    return {"schema": "CAPACITY_TEMPLATE_V2", "epoch": ctx["epoch"], "day": ctx["session"], "capacity": 550,
            "rule": RULE, "order_sha256": hash_value(order), "calendar_sha256": hash_value(calendar),
            "release_sha256": ctx["release_sha256"], "phases": list(PHASES)}


def build_documents(bundle, *, now):
    """Derive documents only from complete current originals; no future clock/hash slots."""
    ctx = context(bundle["context"])
    order, policy, calendar, release = [strict(bundle[k]) for k in ("order", "policy", "calendar", "release")]
    sessions, records, pins = model(order, policy, calendar, release, bundle["chain"], ctx)
    tmpl = template(ctx, order, calendar); act = records["ACT_B"]
    need(act["template_shas"].get(ctx["session"]) == hash_value(tmpl) and set(act["template_shas"]) == set(sessions),
         "CAP_TEMPLATE_ACT_B")
    windows = fields(bundle["phase_windows"], PHASES, "CAP_PHASE_WINDOWS")
    opened = instant(calendar["sessions"][ctx["session"]]["open_UTC"])
    cutoff = opened - timedelta(minutes=10)
    for phase, window in windows.items():
        fields(window, ("not_before", "not_after"), "CAP_PHASE_WINDOW_FIELDS")
        need(instant(window["not_before"]) < instant(window["not_after"]) < cutoff, "CAP_PHASE_WINDOW_MARGIN")
    publication_raw = bundle["publication"]
    publication = issued(publication_raw, "PUBLICATION")
    need(publication["context"] == ctx and publication["phase"] == "bar_manifest"
         and publication["template_sha256"] == hash_value(tmpl) and publication["role"] == "FABLE", "CAP_PUBLICATION_BINDING")
    published = instant(publication["published_at_UTC"])
    notice = instant(windows["bar_manifest"]["not_before"]) - published
    need(published <= now and timedelta(minutes=15) <= notice <= timedelta(days=4), "CAP_PUBLICATION_NOTICE")
    # These originals must exist now. No hypothetical commit/result hashes.
    commitment = strict(bundle["commitment"])
    need(commitment["schema"] == "CAPACITY_CAUSAL_COMMITMENT_V2" and commitment["context"] == ctx
         and commitment["order_sha256"] == hash_value(order), "CAP_COMMITMENT")
    causal = strict(bundle["causal_list"])
    need(commitment["list_sha256"] == digest(bundle["causal_list"]) and commitment["list_count"] == len(causal)
         and type(causal) is list, "CAP_CAUSAL_LIST")
    # The list is already in the owner's existing causal order: never sort/filter
    # a registry to make capacity/provider pass. Symbols stay private.
    need(all(type(x) is str and 0 < len(x) <= 32 for x in causal) and len(set(causal)) == len(causal), "CAP_CAUSAL_DUPLICATES")
    contract = {"schema": "R2D2_CAPACITY_CONTRACT_V2", "context": ctx, "order": order, "policy": policy,
                "calendar": calendar, "release": release, "template": tmpl, "phase_windows": windows,
                "chain_pins": pins, "commitment_sha256": digest(bundle["commitment"]),
                "list_sha256": digest(bundle["causal_list"]), "list_count": len(causal)}
    inputs = {"CONTRACT.json": canonical(contract), "template.raw": canonical(tmpl),
              "publication_bar_manifest.raw": publication_raw}
    for phase, mode in (("admission", "INDIVIDUAL"), ("bar_manifest", "DELEGATED_ACT_B")):
        raw = bundle["go_" + phase]
        go = strict(raw)
        need(go["schema"] == "CAPACITY_GO_V2" and go["context"] == ctx and go["phase"] == phase and go["mode"] == mode
             and go["decision"] == "GO" and go["template_sha256"] == hash_value(tmpl)
             and go["order_sha256"] == hash_value(order) and go["policy_sha256"] == hash_value(policy)
             and go["phase_window"] == windows[phase] and go["automatic_retry"] is False, "CAP_GO_BINDING")
        if phase == "bar_manifest":
            need(go["act_b_sha256"] == pins["ACT_B"] and go["publication_sha256"] == digest(publication_raw), "CAP_GO_ACT_B")
        record = issued(bundle["go_" + phase + "_record"], "GO")
        need(record["context"] == ctx and record["phase"] == phase and record["go_sha256"] == digest(raw)
             and record["template_sha256"] == hash_value(tmpl) and record["decision"] == "GO" and record["role"] == "FABLE",
             "CAP_GO_RECORD")
        inputs["go_" + phase + ".raw"] = raw; inputs["go_" + phase + "_record.raw"] = bundle["go_" + phase + "_record"]
    sets = {}
    need(set(bundle["set_specs"]) == set(SETS), "CAP_SET_NAMES")
    view_times = []
    for index, name in enumerate(SETS, 1):
        spec = bundle["set_specs"][name]
        fields(spec, ("view_raw", "request_raw", "dispatch_go_raw", "config_raw"), "CAP_SET_SPEC")
        view, req, dispatch, config = [strict(spec[k]) for k in ("view_raw", "request_raw", "dispatch_go_raw", "config_raw")]
        need(view["schema"] == "CAPACITY_VETO_VIEW_V2" and view["context"] == ctx and view["order_sha256"] == hash_value(order)
             and view["owner_veto"] is False and view["revoked_shas"] == [] and view["status"] == "VERIFIED", "CAP_VETO_VIEW")
        observed, until = instant(view["observed_UTC"]), instant(view["valid_until_UTC"])
        need(observed <= now and 0 < (until - observed).total_seconds() <= 10, "CAP_VETO_VIEW_CLOCK")
        need(observed == instant(req["view_UTC"]), "CAP_VETO_REQUEST_VIEW")
        view_times.append(instant(req["view_UTC"]))
        need(req["schema"] == "R2D2_CAPACITY_DAY_ONCE_REQUEST_V2" and req["context"] == ctx and req["window"] == name
             and req["window_slot"] == index and req["cutoff_UTC"] == cutoff.isoformat()
             and instant(req["start_UTC"]) < instant(req["view_UTC"]) < instant(req["end_UTC"]) < cutoff, "CAP_SET_REQUEST")
        need(req["contract_sha256"] == digest(inputs["CONTRACT.json"]) and req["template_sha256"] == hash_value(tmpl), "CAP_REQUEST_CONTRACT")
        need(config["schema"] == "CAPACITY_CONFIG_V2" and config["context"] == ctx and config["window"] == name
             and config["chain_pins"] == pins and config["input_pins"] == {k:digest(v) for k,v in inputs.items()}
             and config["veto_view_sha256"] == digest(spec["view_raw"]), "CAP_CONFIG_PINS")
        need(req["capacity_config_sha256"] == digest(spec["config_raw"]), "CAP_REQUEST_CONFIG")
        need(dispatch["schema"] == "CAPACITY_DISPATCH_GO_V2" and dispatch["context"] == ctx and dispatch["decision"] == "GO"
             and dispatch["request_sha256"] == digest(spec["request_raw"]) and dispatch["automatic_retry"] is False, "CAP_DISPATCH_GO")
        docs = {"contract": inputs["CONTRACT.json"], "template": inputs["template.raw"],
                **{k:inputs[k+".raw"] for k in ("go_admission_record", "go_bar_manifest_record", "publication_bar_manifest", "go_admission", "go_bar_manifest")},
                "capacity_config": spec["config_raw"], "veto_view": spec["view_raw"], "request": spec["request_raw"], "dispatch_go": spec["dispatch_go_raw"]}
        sets[name] = docs
    need(view_times == sorted(set(view_times)) and len(view_times) == 3, "CAP_WINDOWS_DISTINCT")
    for name in SETS:
        inputs["capacity_config-"+name+".raw"] = sets[name]["capacity_config"]
        inputs["veto_view-"+name+".raw"] = sets[name]["veto_view"]
    need(set(inputs) == set(INPUTS), "CAP_THIRTEEN_INPUTS")
    return {"status": "BOUND_FOR_REVIEW_ONLY", "context": ctx, "inputs": inputs, "sets": sets,
            "chain_pins": pins, "operational_GO": False}


def verify_day(documents, bundle, *, k8_raw, selected_raw, proof_raw, review_raw, current_view_raw, now):
    """Never a status-string verifier: hashes, bindings, actual counts and originals."""
    ctx = documents["context"]; context(ctx)
    pins = {k:digest(v) for k,v in documents["inputs"].items()}
    set_pins = {name:{k:digest(v) for k,v in docs.items()} for name,docs in documents["sets"].items()}
    expected = build_documents(bundle, now=now)
    need(expected == documents, "CAP_DOCUMENTS_CHANGED")
    proof, review, k8, view = [strict(raw) for raw in (proof_raw, review_raw, k8_raw, current_view_raw)]
    need(proof["schema"] == "CAPACITY_OWN_LINUX_PROOF_V2" and proof["source_sha256"] == bundle["verifier_source_sha256"]
         and proof["attempt"] == 1 and proof["failure_count"] == proof["error_count"] == 0 and proof["test_count"] > 0,
         "CAP_LINUX_PROOF")
    sha(proof["source_sha256"]); sha(proof["artifact_sha256"])
    need(review["schema"] == "CAPACITY_OWN_REVIEW_V2" and review["verdict"] == "ACCEPTED_OWN_BYTES"
         and review["context"] == ctx and review["source_sha256"] == proof["source_sha256"]
         and review["proof_sha256"] == digest(proof_raw) and review["inputs"] == pins and review["sets"] == set_pins
         and review["chain_pins"] == documents["chain_pins"], "CAP_REVIEW_ORIGINAL")
    need(k8["schema"] == "K8_CAPACITY_DAY_ACTUAL_RESULT_V2" and k8["context"] == ctx and k8["status"] == "COMPLETE"
         and k8["inputs"] == pins and k8["sets"] == set_pins and k8["chain_pins"] == documents["chain_pins"]
         and k8["verifier_source_sha256"] == proof["source_sha256"]
         and k8["review_sha256"] == digest(review_raw) and k8["contract_sha256"] == pins["CONTRACT.json"], "CAP_K8_ACTUAL_RESULT")
    need(k8["commitment_sha256"] == digest(bundle["commitment"]) and k8["causal_list_sha256"] == digest(bundle["causal_list"]), "CAP_K8_CAUSAL_BINDING")
    counts = fields(k8["counts"], ("open", "new_admitted", "total", "new_cut"), "CAP_K8_COUNTS")
    open_positions = strict(bundle["open_positions"])
    need(type(open_positions) is list and all(type(x) is str and 0 < len(x) <= 32 for x in open_positions)
         and len(set(open_positions)) == len(open_positions) <= 550, "CAP_OPEN_POSITIONS")
    causal = strict(bundle["causal_list"])
    need(not set(open_positions).intersection(causal), "CAP_CAUSAL_INCLUDES_OPEN")
    selected = strict(selected_raw)
    expected_new = causal[:550-len(open_positions)]
    need(selected == {"context": ctx, "open_preserved": open_positions, "new_admitted": expected_new,
                      "new_cut": causal[len(expected_new):]}, "CAP_K8_SELECTED_BYTES")
    need(k8["open_positions_sha256"] == digest(bundle["open_positions"]) and k8["selected_sha256"] == digest(selected_raw), "CAP_K8_OPEN_BINDING")
    need(counts == {"open":len(open_positions), "new_admitted":len(expected_new),
                    "total":len(open_positions)+len(expected_new), "new_cut":len(causal)-len(expected_new)}, "CAP_K8_DERIVED_COUNTS")
    need(all(type(v) is int and v >= 0 for v in counts.values()) and counts["open"] + counts["new_admitted"] == counts["total"]
         and counts["total"] <= 550 and counts["new_admitted"] + counts["new_cut"] == len(strict(bundle["causal_list"]))
         and k8["open_preserved"] is True and k8["causal_order_preserved"] is True, "CAP_K8_CAPACITY_RESULT")
    need(view["schema"] == "CAPACITY_VETO_VIEW_V2" and view["context"] == ctx and view["status"] == "VERIFIED"
         and view["owner_veto"] is False and view["revoked_shas"] == []
         and view["order_sha256"] == hash_value(strict(bundle["order"])), "CAP_CURRENT_AUTHORITY")
    observed, until = instant(view["observed_UTC"]), instant(view["valid_until_UTC"])
    need(observed <= now < until and (now-observed).total_seconds() <= 10, "CAP_CURRENT_AUTHORITY_STALE")
    return {"schema": "CAPACITY_DAY_VERIFIED_REPORT_V2", "context": ctx, "status": "VERIFIED",
            "documentary_authority": "VERIFIED", "capacity_gate_verified": True, "inputs": pins, "sets": set_pins,
            "chain_pins": documents["chain_pins"], "actual_k8_sha256": digest(k8_raw), "proof_sha256": digest(proof_raw),
            "review_sha256": digest(review_raw), "revocation_view_sha256": digest(current_view_raw), "counts": counts,
            "operational_GO": False}


def selection(bundle):
    """K8 V2 causal cut, with open positions preserved in their original order."""
    ctx = context(bundle["context"])
    opens, causal = strict(bundle["open_positions"]), strict(bundle["causal_list"])
    need(type(opens) is list and type(causal) is list and len(opens) <= 550
         and all(type(x) is str and 0 < len(x) <= 32 for x in opens+causal)
         and len(set(opens)) == len(opens) and len(set(causal)) == len(causal)
         and not set(opens).intersection(causal), "CAP_SELECTION_INPUTS")
    remaining = 550-len(opens)
    return canonical({"context":ctx,"open_preserved":opens,"new_admitted":causal[:remaining],"new_cut":causal[remaining:]})


def prepare_once(bundle, *, proof_raw, review_raw, current_view_raw, output, now, recheck):
    """New protected K8 document-store writer, one elected invocation, no DB fallback.

    A new release consumer must explicitly read this V2 store. The historical DB
    K8 ABI is not changed by this function or by a date replacement.
    """
    documents = build_documents(bundle, now=now)
    selected_raw = selection(bundle)
    selected = strict(selected_raw)
    pins = {k:digest(v) for k,v in documents["inputs"].items()}
    set_pins = {name:{k:digest(v) for k,v in docs.items()} for name,docs in documents["sets"].items()}
    counts = {"open":len(selected["open_preserved"]),"new_admitted":len(selected["new_admitted"]),
              "total":len(selected["open_preserved"])+len(selected["new_admitted"]),"new_cut":len(selected["new_cut"])}
    k8 = {"schema":"K8_CAPACITY_DAY_ACTUAL_RESULT_V2","context":bundle["context"],"status":"COMPLETE",
          "inputs":pins,"sets":set_pins,"chain_pins":documents["chain_pins"],
          "verifier_source_sha256":bundle["verifier_source_sha256"],"review_sha256":digest(review_raw),
          "contract_sha256":pins["CONTRACT.json"],"commitment_sha256":digest(bundle["commitment"]),
          "causal_list_sha256":digest(bundle["causal_list"]),"open_positions_sha256":digest(bundle["open_positions"]),
          "selected_sha256":digest(selected_raw),"counts":counts,"open_preserved":True,"causal_order_preserved":True}
    raw = canonical(k8)
    report = verify_day(documents,bundle,k8_raw=raw,selected_raw=selected_raw,proof_raw=proof_raw,
                        review_raw=review_raw,current_view_raw=current_view_raw,now=now)
    need(not any(output.exists(name) for name in ("CAPACITY_SELECTED.private.json","K8_RESULT.json","CAPACITY_DAY.json")),
         "CAP_ALREADY_PREPARED")
    recheck()
    # Any interrupted/partial sequence is consumed. No remove/resume API exists.
    output.create("CAPACITY_SELECTED.private.json",selected_raw)
    output.create("K8_RESULT.json",raw)
    output.create("CAPACITY_DAY.json",canonical(report))
    return report
