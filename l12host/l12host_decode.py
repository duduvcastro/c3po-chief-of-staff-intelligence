"""L12-HOST v3.1 receipt ABI decoders. Loaded by l12host_runtime from pinned bytes; no action on import.

An original is accepted only after decoding ITS OWN bytes by the ABI signed for the operation or step (status and time
are extracted from the original, never declared by an operator or a CLI flag) and after the provenance check of that
ABI. The closed tables are:

  core                 prove, collect, commit_result, publish_launch -> K9_STEP_V1 (vendored Codex adapter f84d55b8, with
                       the prove -> prove_launch alias); e6 -> READBACK_V3; admission_manifest -> HOT_J_V1;
                       post -> CHAIN_READBACK_V3; install_release, readback, activate, capacity_activate -> EXTERNAL_V1.
                       reader_bound / reader_cycle / policy_read / capture_* are NOT core operations of v3 (B3).
  extended RUNNER      components, sources, bind, preflight, acquire, execute, stage -> K9_EXT_STEP_V3 (the same
                       K9_STEP_RECEIPT_V1 byte ABI, decoded here from the signed plan and runner literals, plus a
                       mandatory pinned external verifier).
  extended CAPTURE     capture_launch -> K9_STEP_V1 (the vendored adapter; CAPTURED with snapshot + tape).
  extended SESSION     session_start -> SESSION_START_V3 (supervisor LAUNCH_ACK + reader LAUNCH_ACK held through the
                       signed first-cycle instant + the gate sequence) plus a mandatory pinned external verifier of the
                       real first SESSION cycle. A LAUNCH_ACK alone is never COMPLETE. v3.1: the reader ACK carries the
                       acknowledged supervisor (unit, MainPID) observed running through the whole hold.
  extended READY_CHECK ready_check -> READY_ABSENT_V3 (v3.1): the read-only observation that the signed ready path
                       was absent, inside the step window.

The K9 Approval rule is a DERIVED output: the signed decoder row fixes every field except the invocation REQUEST/BOUND
hashes, which come from the actual installed lot. A stored J original (dependency read, long after J's live window) is
re-decoded STRUCTURALLY from the retained process receipt and proven by the durable OUTER terminal; the live J
verifier is not re-run outside J's own window (Codex codec note).
"""
import base64
import json
from datetime import datetime, timedelta, timezone

RT = None   # the running l12host_runtime module, injected by its Family loader
DECODER_KINDS = ("K9_STEP_V1", "K9_EXT_STEP_V3", "HOT_J_V1", "SESSION_START_V3", "READBACK_V3", "CHAIN_READBACK_V3",
                 "EXTERNAL_V1", "READY_ABSENT_V3")
K9_CORE_OPERATIONS = ("prove", "collect", "commit_result", "publish_launch")
CORE_TABLE = {
    "prove": (("CONTAINER",), ("K9_STEP_V1",)),
    "collect": (("CONTAINER",), ("K9_STEP_V1",)),
    "commit_result": (("CONTAINER",), ("K9_STEP_V1",)),
    "publish_launch": (("CONTAINER",), ("K9_STEP_V1",)),
    "e6": (("READBACK",), ("READBACK_V3",)),
    "admission_manifest": (("HOST_PROGRAM",), ("HOT_J_V1",)),
    "post": (("CHAIN_READBACK",), ("CHAIN_READBACK_V3",)),
    "install_release": (("HOST_PROGRAM",), ("EXTERNAL_V1",)),
    "readback": (("HOST_PROGRAM",), ("EXTERNAL_V1",)),
    "activate": (("HOST_PROGRAM",), ("EXTERNAL_V1",)),
    "capacity_activate": (("HOST_PROGRAM",), ("EXTERNAL_V1",)),
}
EXTENDED_TABLE = {"RUNNER": ("CONTAINER", "K9_EXT_STEP_V3"), "CAPTURE": ("CONTAINER", "K9_STEP_V1"),
                  "SESSION_START": ("UNIT_START", "SESSION_START_V3"), "READY_CHECK": (None, "READY_ABSENT_V3")}
RESULT_CLASSES = {"K9_STEP_V1": "K9_STEP_COMPLETE", "K9_EXT_STEP_V3": "K9_STEP_COMPLETE",
                  "HOT_J_V1": "J_PUBLISHED_VERIFIED", "SESSION_START_V3": "SESSION_START_FIRST_CYCLE_HELD",
                  "READBACK_V3": "READBACK_ALL_MATCH", "CHAIN_READBACK_V3": "CHAIN_ALL_COMPLETE",
                  "EXTERNAL_V1": "EXTERNAL_ORIGINAL_COMPLETE", "READY_ABSENT_V3": "READY_ABSENT_OBSERVED"}
SESSION_SCHEMA = "L12HOST_SESSION_START_V31"
READY_ABSENT_SCHEMA = "L12HOST_READY_ABSENT_V31"
SESSION_GATES = ["DEPENDENCIES", "UNIT_ENV_FILES_PINNED", "CAPACITY_CHAIN", "VETO_ALLOW", "READY_ABSENT_BEFORE_SUPERVISOR",
                 "SUPERVISOR_STARTED", "READY_VERIFIED", "RECHECK", "CAPACITY_CHAIN", "BEFORE_FIRST_READER",
                 "UNIT_ENV_FILES_UNCHANGED", "SUPERVISOR_ALIVE", "VETO_ALLOW", "READY_STILL_PRESENT",
                 "READER_STARTED_HELD_WITH_SUPERVISOR"]
J_PROCESS_SCHEMA = "R2D2_HOT_IMAGE10_PROCESS_RECEIPT_CANDIDATE_V1"
J_WRITER_SCHEMA = "R2D2_V2_BAR_MANIFEST_WRITER_RECEIPT_V1"


class DecodeHold(ValueError):
    pass


def need(ok, code):
    if not ok:
        raise DecodeHold(code)


def result_class(kind):
    return RESULT_CLASSES.get(kind)


def utc(value):
    need(type(value) is str and 0 < len(value) <= 40, "DECODED_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        raise DecodeHold("DECODED_TIME_INVALID") from None
    need(parsed.utcoffset() == timedelta(0), "DECODED_TIME_INVALID")
    return parsed.astimezone(timezone.utc)


def validate_decoder_row(row, operation, effect_kind, *, extended=False, step_kind=None, external=(), files=()):
    """Signed decoder row, checked against the closed tables (no kind outside them, no op without its ABI)."""
    need(type(row) is dict and row.get("kind") in DECODER_KINDS, "DECODER_KIND_INVALID")
    kind = row["kind"]
    if extended:
        need(step_kind in EXTENDED_TABLE and EXTENDED_TABLE[step_kind] == (effect_kind, kind),
             "DECODER_NOT_ALLOWED_FOR_EXTENDED_STEP")
    else:
        need(operation in CORE_TABLE and effect_kind in CORE_TABLE[operation][0]
             and kind in CORE_TABLE[operation][1], "OPERATION_OR_DECODER_NOT_EXPRESSIBLE_V3")
    if kind == "K9_STEP_V1":
        need(set(row) == {"kind", "mode", "runner_source", "step_plan", "k9_request", "k9_go",
                          "provenance_binding_sha256", "phase_not_before", "phase_not_after", "verifiers"}
             and row["mode"] in ("REAL", "FIXTURE")
             and (operation in K9_CORE_OPERATIONS or (extended and operation == "capture_launch"))
             and all(row[k] in files for k in ("runner_source", "step_plan", "k9_request", "k9_go"))
             and type(row["verifiers"]) is dict and set(row["verifiers"]) == {"approval", "original"}
             and all(v in external for v in row["verifiers"].values()), "K9_DECODER_ROW_INVALID")
        utc(row["phase_not_before"])
        utc(row["phase_not_after"])
    elif kind in ("K9_EXT_STEP_V3", "HOT_J_V1", "SESSION_START_V3"):
        need(set(row) == {"kind", "verifier"} and row["verifier"] in external, "VERIFIED_DECODER_ROW_INVALID")
    elif kind in ("READBACK_V3", "CHAIN_READBACK_V3", "READY_ABSENT_V3"):
        need(set(row) == {"kind"}, "READBACK_DECODER_ROW_INVALID")
    else:
        need(set(row) == {"kind", "decoder", "verifier"} and row["decoder"] in external and row["verifier"] in external,
             "EXTERNAL_DECODER_ROW_INVALID")
    return kind


class Decoders:
    """Decoder table of ONE installed lot view (its own REQUEST/BOUND/authority/files/external modules)."""

    def __init__(self, view, fb, k9, vb, fx):
        self.view, self.fb, self.k9, self.vb, self.fx = view, fb, k9, vb, fx

    # -------------------------------------------------------------- helpers
    def verifier(self, name):
        module, identity, source_sha = self.view.external(name)
        callback = getattr(module, identity, None)
        need(callable(callback), "EXTERNAL_CALLBACK_ABSENT")
        v = self.vb.Verifier(self.view.mode, identity, source_sha, callback, module)
        return v, {"identity": identity, "source_sha256": source_sha}

    def receipt(self, raw, role, context, completed_at):
        return self.fb.Receipt(raw, role, tuple(context), "COMPLETE", completed_at)

    def row(self, role, extended=False):
        return self.view.decoder_row(role, extended)

    # -------------------------------------------------------------- dispatch
    def decode(self, role, raw, invocation, *, extended=False, effect_row=None, private_sink=None, stored=False):
        """Returns fb.Receipt(raw_original, role, context, COMPLETE, completed_at) or raises."""
        row = self.row(role, extended)
        kind = row["kind"]
        need(type(raw) is bytes and 0 < len(raw) <= 1024 * 1024, "ORIGINAL_BYTES_INVALID")
        if kind == "HOT_J_V1" and stored:
            key = self.fb.sha(self.fb.canonical(list(invocation.context) + [role]))
            receipt = self.hot_j_decode(role, self.view.private_evidence(key, "process"), invocation, row, None, live=False)
            need(receipt.raw == raw, "HOT_J_STORED_WRITER_MISMATCH")
            return receipt
        if kind == "K9_STEP_V1":
            return self.k9_decode(role, raw, invocation, row)
        if kind == "K9_EXT_STEP_V3":
            return self.k9_ext_decode(role, raw, invocation, row)
        if kind == "HOT_J_V1":
            return self.hot_j_decode(role, raw, invocation, row, private_sink, live=True)
        if kind == "SESSION_START_V3":
            return self.session_decode(role, raw, invocation, row)
        if kind == "READY_ABSENT_V3":
            return self.ready_absent_decode(role, raw, invocation)
        if kind == "READBACK_V3":
            return self.readback_decode(role, raw, invocation, effect_row)
        if kind == "CHAIN_READBACK_V3":
            return self.chain_decode(role, raw, invocation, effect_row)
        return self.external_decode(role, raw, invocation, row)

    # -------------------------------------------------------------- K9 (vendored Codex adapter)
    def k9_rule(self, row):
        fb, view = self.fb, self.view
        verifiers = {}
        for name in ("approval", "original"):
            _, expected = self.verifier(row["verifiers"][name])
            verifiers[name] = expected
        rule = {"schema": "K9_APPROVED_DECODER_RULE_CANDIDATE_V1", "mode": row["mode"], "epoch": fb.EPOCH,
                "day": fb.DAY, "runner_source_sha256": fb.sha(view.file(row["runner_source"])),
                "step_plan_sha256": fb.sha(view.file(row["step_plan"])),
                "provenance_binding_sha256": row["provenance_binding_sha256"],
                "invocation_request_sha256": view.request_sha256, "invocation_bound_sha256": view.bound_sha256,
                "k9_request_sha256": fb.sha(view.file(row["k9_request"])),
                "k9_go_sha256": fb.sha(view.file(row["k9_go"])), "phase_not_before": row["phase_not_before"],
                "phase_not_after": row["phase_not_after"], "verifiers": verifiers}
        return fb.canonical(rule)

    def k9_decode(self, role, raw, invocation, row):
        fb, k9, view = self.fb, self.k9, self.view
        need(row["mode"] == view.mode, "K9_DECODER_MODE_MISMATCH")
        rule_raw = self.k9_rule(row)
        approval = k9.Approval(rule_raw, fb.sha(rule_raw), view.file(row["k9_request"]), view.file(row["k9_go"]))
        runner_raw = view.file(row["runner_source"])
        binding = k9.Binding(role, view.file(row["step_plan"]), runner_raw, fb.sha(runner_raw),
                             row["provenance_binding_sha256"])
        verify_original, _ = self.verifier(row["verifiers"]["original"])
        verify_approval, _ = self.verifier(row["verifiers"]["approval"])
        adapter = k9.K9ReceiptAdapter(binding, verify_original, approval=approval, verify_approval=verify_approval)
        receipt = adapter.decode(raw, invocation)
        need(type(receipt) is fb.Receipt and receipt.raw == raw and receipt.role == role
             and receipt.status == "COMPLETE", "K9_DECODE_RESULT_INVALID")
        return receipt

    def k9_ext_decode(self, step, raw, invocation, row):
        """K9_STEP_RECEIPT_V1 of a runner04 extended step (components ... stage). Same literal/plan/receipt rules as
        the vendored adapter, bound to the step's signed plan, the lot's runner and the step window; then the
        mandatory pinned verifier (origin, file, outputs, REQUEST/BOUND)."""
        fb, k9, view = self.fb, self.k9, self.view
        _, runner_op, _ = RT.EXTENDED_TABLE[view.q["lane"]][step]
        sec = view.authority["k9"]
        need(sec is not None and runner_op is not None, "K9_SECTION_ABSENT")
        plan_raw, runner_raw = view.file(sec["plans"][runner_op]), view.file(sec["runner_source"])
        compiled = k9.compiled_literals(runner_raw)
        need(compiled["EPOCH"] == fb.EPOCH and fb.DAY in compiled["DAYS"] and compiled["RECEIPT_KEYS"] == k9.RECEIPT_KEYS
             and compiled["PLAN_KEYS"] == k9.PLAN_KEYS and compiled["CONST_KEYS"] == k9.CONST_KEYS
             and fb.pin(compiled["PACKAGE"]) and k9.GIT.fullmatch(compiled["REVISION"] or "") is not None,
             "K9_COMPILED_ABI_CHANGED")
        plan = k9.original_json(plan_raw)
        ops = compiled["OPS"]
        need(set(plan) == k9.PLAN_KEYS and plan["schema"] == "K9_STEP_PLAN_V1" and plan["epoch"] == fb.EPOCH
             and plan["day"] == fb.DAY and plan["k9_operation"] == runner_op and runner_op in ops
             and plan["k9_phase"] == ops[runner_op][0] and plan["network_class"] == ops[runner_op][1],
             "K9_STEP_PLAN_UNBOUND")
        key = fb.sha(json.dumps([fb.EPOCH, fb.DAY, plan["k9_phase"], runner_op], separators=(",", ":"),
                                ensure_ascii=True).encode("ascii"))
        constants = plan["constants"]
        need(plan["attempt_key"] == key and plan["request_sha256"] == fb.sha(view.file(sec["request"]))
             and plan["go_sha256"] == fb.sha(view.file(sec["go"])) and type(constants) is dict
             and set(constants) == k9.CONST_KEYS and constants["runner_sha256"] == fb.sha(runner_raw)
             and constants["package_sha256"] == compiled["PACKAGE"] and constants["code_revision"] == compiled["REVISION"]
             and constants["risk_limits"] == compiled["LIMITS"] and constants["disk_floor_bytes"] == compiled["FLOOR"]
             and all(fb.pin(constants[k]) for k in ("act_b_sha256", "release_sha256", "policy_sha256",
                                                    "risk_source_pins_sha256"))
             and plan["database"] is None, "K9_STEP_PLAN_CONSTANTS_CHANGED")
        need(type(invocation) is fb.Invocation and invocation.operation == step
             and invocation.request_sha256 == view.request_sha256 and invocation.bound_sha256 == view.bound_sha256
             and tuple(invocation.context) == tuple(view.context), "K9_INVOCATION_CONTEXT_CHANGED")
        doc = k9.original_json(raw)
        need(type(doc) is dict and set(doc) == k9.RECEIPT_KEYS and doc["schema"] == "K9_STEP_RECEIPT_V1"
             and doc["status"] == "COMPLETE" and doc["code"] is None and doc["epoch"] == fb.EPOCH and doc["day"] == fb.DAY
             and doc["phase"] == plan["k9_phase"] and doc["operation"] == runner_op
             and doc["attempt_key"] == plan["attempt_key"] and doc["step_plan_sha256"] == fb.sha(plan_raw)
             and doc["package_sha256"] == compiled["PACKAGE"] and doc["build_sha"] == compiled["REVISION"],
             "K9_ORIGINAL_NOT_EXACT_COMPLETE")
        step_row = view.step(step)
        now = datetime.now(timezone.utc)
        started, completed = k9.utc(doc["started_at"]), k9.utc(doc["completed_at"])
        need(started <= completed <= now < invocation.deadline_utc and completed < k9.utc(plan["run_not_after"])
             and utc(step_row["not_before"]) <= started and completed < utc(step_row["not_after"]),
             "K9_ORIGINAL_OUTSIDE_STEP_WINDOW")
        outputs, aggregates = doc["outputs"], doc["aggregates"]
        need(type(outputs) is dict and type(aggregates) is dict and len(outputs) <= 64 and len(aggregates) <= 8
             and all(type(k) is str and k9.OUTPUT.fullmatch(k) and "/." not in k for k in list(outputs) + list(aggregates))
             and all(fb.pin(v) for v in outputs.values()) and k9.counts(doc["counts"]), "K9_ORIGINAL_RECEIPT_GRAMMAR")
        verifier, expected = self.verifier(row["verifier"])
        verifier.invoke(expected, view.mode, raw, step, plan_raw, fb.sha(runner_raw), tuple(invocation.context),
                        invocation.request_sha256, invocation.bound_sha256, fb.iso(completed))
        need(doc == k9.original_json(raw) and plan == k9.original_json(view.file(sec["plans"][runner_op])),
             "K9_VERIFIER_CHANGED_ORIGINALS")
        return self.receipt(raw, step, invocation.context, completed)

    # -------------------------------------------------------------- J4 hot process receipt
    def hot_j_decode(self, role, raw, invocation, row, private_sink, *, live):
        fb, view = self.fb, self.view
        need(role == "admission_manifest", "HOT_J_ROLE_INVALID")
        body = raw[:-1] if raw.endswith(b"\n") else raw
        doc = fb.strict(body)
        registry_raw = view.derived("j4_registry.json")   # derived after BOUND, re-checked by its rule at the gate
        scope = list(invocation.context) + ["admission_manifest"]
        need(set(doc) == {"schema", "mode", "protocol", "registry_sha256", "request_sha256", "bound_sha256",
                          "outer_attempt_key", "pid", "parent_pid", "process_group", "warm_at", "image_observed_at",
                          "image_valid_until", "general_observation_base64", "slot_result",
                          "actual_installation_certified", "operational_GO"}
             and doc["schema"] == J_PROCESS_SCHEMA and doc["mode"] == view.mode
             and doc["registry_sha256"] == fb.sha(registry_raw)
             and doc["request_sha256"] == invocation.request_sha256 == view.request_sha256
             and doc["bound_sha256"] == invocation.bound_sha256 == view.bound_sha256
             and doc["outer_attempt_key"] == fb.sha(fb.canonical(scope))
             and doc["operational_GO"] is False and doc["actual_installation_certified"] is False,
             "HOT_J_PROCESS_RECEIPT_UNBOUND")
        slot = doc["slot_result"]
        need(type(slot) is dict and slot.get("status") == "COMPLETE" and slot.get("operational_GO") is False
             and slot.get("mode") == view.mode and type(slot.get("writer_receipt_base64")) is str,
             "HOT_J_SLOT_NOT_COMPLETE")
        writer = base64.b64decode(slot["writer_receipt_base64"], validate=True)
        need(0 < len(writer) <= 256 * 1024 and fb.sha(writer) == slot.get("writer_receipt_sha256"),
             "HOT_J_WRITER_RECEIPT_UNBOUND")
        w = fb.strict(writer[:-1] if writer.endswith(b"\n") else writer)
        need(w.get("schema") == J_WRITER_SCHEMA and w.get("status") == "PUBLISHED_VERIFIED" and w.get("mode") == "PUBLISH"
             and w.get("code") is None and w.get("epoch") == fb.EPOCH and w.get("session") == fb.DAY
             and fb.pin(w.get("capacity_config_sha256")) and w.get("capacity_config_sha256") == slot.get("config_sha256")
             and w.get("massive_bars_enabled") is True, "HOT_J_WRITER_NOT_PUBLISHED_VERIFIED")
        completed = utc(w.get("published_at"))
        if live:
            verifier, expected = self.verifier(row["verifier"])
            verifier.invoke(expected, view.mode, raw, writer, registry_raw, invocation)
        if private_sink is not None:
            private_sink("process", raw)
        return self.receipt(writer, role, invocation.context, completed)

    # -------------------------------------------------------------- the late session start (B3)
    def ack(self, raw, launch_class, unit, held, supervisor=None):
        """LAUNCH_ACK of one unit. v3.1: `supervisor` = (unit, MainPID) for the reader: the ACK must record that
        supervisor, observed running with that MainPID on every poll through the hold."""
        fb = self.fb
        doc = fb.strict(raw)
        props = doc.get("properties")
        need(set(doc) == {"schema", "result_class", "launch_class", "unit", "systemd_run_rc", "properties", "observed_at",
                          "hold_until", "held", "polls", "supervisor", "operational_complete"}
             and doc["schema"] == self.fx.ACK_SCHEMA and doc["result_class"] == "LAUNCH_ACK"
             and doc["operational_complete"] is False and doc["launch_class"] == launch_class and doc["unit"] == unit
             and doc["systemd_run_rc"] == 0 and type(props) is dict and props.get("Id") == unit + ".service"
             and self.fx.running_once(props) and (not held or doc["held"] is True), "LAUNCH_ACK_UNIT_NOT_RUNNING_ONCE")
        sup = doc["supervisor"]
        if supervisor is None:
            need(sup is None, "LAUNCH_ACK_SUPERVISOR_UNEXPECTED")
        else:
            need(type(sup) is dict and set(sup) == {"unit", "main_pid", "polls", "running_through_hold"}
                 and sup["unit"] == supervisor[0] and sup["main_pid"] == supervisor[1]
                 and sup["running_through_hold"] is True and type(sup["polls"]) is int
                 and sup["polls"] >= (doc["polls"] if held else 1), "SUPERVISOR_NOT_RUNNING_THROUGH_HOLD")
        return doc

    def session_decode(self, step, raw, invocation, row):
        fb, view = self.fb, self.view
        s = view.step(step)
        doc = fb.strict(raw)
        need(set(doc) == {"schema", "result_class", "step", "supervisor_ack_b64", "supervisor_ack_sha256",
                          "reader_ack_b64", "reader_ack_sha256", "ready_sha256", "ready_observed_at", "gates",
                          "hold_until", "observed_at", "operational_GO"}
             and doc["schema"] == SESSION_SCHEMA and doc["result_class"] == RESULT_CLASSES["SESSION_START_V3"]
             and doc["step"] == step and doc["gates"] == SESSION_GATES and doc["hold_until"] == s["hold_until"]
             and doc["operational_GO"] is False and fb.pin(doc["ready_sha256"]), "SESSION_START_RECORD_INVALID")
        sup = base64.b64decode(doc["supervisor_ack_b64"], validate=True)
        rdr = base64.b64decode(doc["reader_ack_b64"], validate=True)
        need(fb.sha(sup) == doc["supervisor_ack_sha256"] and fb.sha(rdr) == doc["reader_ack_sha256"],
             "SESSION_START_RECORD_INVALID")
        sup_doc = self.ack(sup, "SUPERVISOR", s["pre_effect"]["unit"]["name"], False)
        reader = self.ack(rdr, "SESSION_READER", s["effect"]["unit"]["name"], True,
                          supervisor=(s["pre_effect"]["unit"]["name"], sup_doc["properties"].get("MainPID")))
        hold, completed = utc(s["hold_until"]), utc(doc["observed_at"])
        ready_at = utc(doc["ready_observed_at"])
        need(reader["hold_until"] == s["hold_until"] and utc(reader["observed_at"]) >= hold
             and utc(s["not_before"]) <= ready_at <= hold <= completed < utc(s["not_after"]), "SESSION_START_NOT_HELD")
        verifier, expected = self.verifier(row["verifier"])
        verifier.invoke(expected, view.mode, raw, step, tuple(invocation.context), invocation.request_sha256,
                        invocation.bound_sha256, fb.iso(completed))
        return self.receipt(raw, step, invocation.context, completed)

    def ready_absent_decode(self, step, raw, invocation):
        fb, view = self.fb, self.view
        s = view.step(step)
        doc = fb.strict(raw)
        ready = view.authority.get("ready")
        need(set(doc) == {"schema", "step", "ready_path_sha256", "absent", "observed_at", "operational_GO"}
             and doc["schema"] == READY_ABSENT_SCHEMA and doc["step"] == step and doc["absent"] is True
             and doc["operational_GO"] is False and type(ready) is dict
             and doc["ready_path_sha256"] == fb.sha(ready["ready_path"].encode("ascii")), "READY_ABSENT_RECORD_INVALID")
        observed = utc(doc["observed_at"])
        need(utc(s["not_before"]) <= observed < utc(s["not_after"]), "READY_ABSENT_OUTSIDE_STEP_WINDOW")
        return self.receipt(raw, step, invocation.context, observed)

    # -------------------------------------------------------------- readbacks
    def readback_decode(self, role, raw, invocation, effect_row):
        fb = self.fb
        doc = fb.strict(raw)
        need(set(doc) == {"schema", "files", "all_match", "observed_at"} and doc["schema"] == "L12HOST_READBACK_V3"
             and doc["all_match"] is True and effect_row is not None and effect_row.get("kind") == "READBACK"
             and [f.get("path") for f in doc["files"]] == [f["path"] for f in effect_row["files"]]
             and all(f.get("match") is True and f.get("sha256") == e["sha256"]
                     for f, e in zip(doc["files"], effect_row["files"])), "READBACK_NOT_ALL_MATCH")
        return self.receipt(raw, role, invocation.context, utc(doc["observed_at"]))

    def chain_decode(self, role, raw, invocation, effect_row):
        fb = self.fb
        need(effect_row is not None and effect_row.get("kind") == "CHAIN_READBACK", "CHAIN_NOT_COMPLETE")
        source = self.view.resolve(effect_row["source_lot"])
        need(source.request_sha256 == effect_row["source_request_sha256"]
             and source.bound_sha256 == effect_row["source_bound_sha256"] and source.context == tuple(invocation.context),
             "CHAIN_SOURCE_LOT_UNBOUND")
        doc = fb.strict(raw)
        need(set(doc) == {"schema", "steps", "observed_at", "all_complete"} and doc["schema"] == "L12HOST_CHAIN_READBACK_V3"
             and doc["all_complete"] is True and [s.get("step") for s in doc["steps"]] == effect_row["steps"],
             "CHAIN_NOT_COMPLETE")
        observed = utc(doc["observed_at"])
        for state in doc["steps"]:
            need(state.get("durable") is True and state.get("status") == "EXTENDED_COMPLETE"
                 and state.get("attempt_key") == fb.sha(fb.canonical(list(invocation.context) + ["EXTENDED", state["step"]]))
                 and utc(state.get("original_completed_at")) <= observed, "CHAIN_STEP_NOT_DURABLE_COMPLETE")
            original = source.extended_original(state["step"], state["original_sha256"])
            check = fb.Invocation(state["step"], invocation.context, source.request_sha256, source.bound_sha256,
                                  invocation.deadline_utc, invocation.deadline_monotonic, ())
            again = source.decoders.decode(state["step"], original, check, extended=True,
                                           effect_row=source.extended_effect(state["step"]), stored=True)
            need(fb.sha(again.raw) == state["original_sha256"]
                 and fb.iso(again.completed_at) == fb.iso(utc(state["original_completed_at"])), "CHAIN_STEP_REDECODE_MISMATCH")
        return self.receipt(raw, role, invocation.context, observed)

    # -------------------------------------------------------------- external pinned ABI module
    def external_decode(self, role, raw, invocation, row):
        fb, view = self.fb, self.view
        module, identity, source_sha = view.external(row["decoder"])
        decode = getattr(module, identity, None)
        need(callable(decode), "EXTERNAL_DECODER_ABSENT")
        if view.mode == "REAL":
            decoder_check = self.vb.Verifier("REAL", identity, source_sha, decode, module)
            decoder_check.validate({"identity": identity, "source_sha256": source_sha}, "REAL")
        out = decode(raw, role, tuple(invocation.context), invocation.request_sha256, invocation.bound_sha256)
        need(type(out) is dict and set(out) == {"status", "completed_at"} and out["status"] == "COMPLETE",
             "EXTERNAL_DECODER_NOT_COMPLETE")
        completed = utc(out["completed_at"])
        verifier, expected = self.verifier(row["verifier"])
        verifier.invoke(expected, view.mode, raw, role, tuple(invocation.context), invocation.request_sha256,
                        invocation.bound_sha256, fb.iso(completed))
        return self.receipt(raw, role, invocation.context, completed)
