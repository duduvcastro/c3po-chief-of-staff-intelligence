"""L12-HOST v3.1: (1) the core gates built from signed sections (or absent = None, so the R6 core refuses with
REAL_ADAPTER_UNAVAILABLE), and (2) the EXTENDED family: the shell's own finite executor for the steps the R6 core
vocabulary/budget cannot carry, under a CLOSED step table per lane (l12host_runtime.EXTENDED_TABLE). Loaded by
l12host_runtime from pinned bytes; no action on import.

Closed kinds:
  RUNNER        (UP) components, sources, bind, preflight, acquire, execute, stage: one runner04 container each,
                fixed command shape, K9_EXT_STEP_V3 decoder; dependencies fixed by the table.
  CAPTURE       (DOWN) capture_launch: capacity chain (M3 -> J -> CAPACITY_MONDAY originals) and BEFORE_CAPTURE_LAUNCH
                (bounded readback r1) before the container; K9_STEP_V1 decode; AFTER_CAPTURE after it.
  SESSION_START (DOWN, B3) the ONLY reader start: in ONE claim, after the dependency and capacity gates, the declared
                supervisor start (recorded by an O_EXCL xpre marker before its transport); the READY wait, read-only,
                finite, inside the same claim; the full RECHECK (authority, identity, dependencies, capacity chain);
                BEFORE_FIRST_READER (ready/catalog/manifest/calendar/close/window through the bounded readback); a fresh
                ALLOW; the reader start only while the exact ready.json is still present; the hold through the signed
                first-cycle instant; AFTER_FIRST_CYCLE. There is no PRE_OPEN reader start in v3, and the OPS launcher,
                started after open-90s with READY present, enters SESSION only after these gates (CONTRACT section 5).
                v3.1: in the same claim, BEFORE the xpre marker, the ready file must be ABSENT (a leftover is a HOLD
                with no effect); the identity of the reader's env files is pinned at the claim and re-checked before
                the reader; the acknowledged supervisor must still be running with the same MainPID before the reader
                start (worker and engine) and through the hold (engine).
  READY_CHECK   (DOWN, v3.1) ready_check: an EARLY read-only observation that the ready file is absent (no effect, no
                dependency): a leftover is reported hours before the session start so a person can clear it.

EXTENDED rules (same discipline as the core, never a core COMPLETE):
  - the start marker (runtime) and then xclaim-<key> are created O_EXCL + fsync BEFORE any gate: the step is
    consumed from that instant, whatever follows (refusal, crash, deadline). No retry, no second logical attempt.
  - a session-leader worker (own group) runs every gate and the pinned effect engine; the parent kills the whole group
    at min(ceiling, not_after) (lifeline watchdog in the group if the parent dies) and reaps it.
  - xterm-<key> (O_EXCL) records the terminal; COMPLETE only for an original decoded by its signed ABI decoder.
  - a state read is DURABLE or it is a HOLD: claim + terminal + envelope present, canonical and mutually bound.
  - docker containers outlive a killed CLI client: every CONTAINER row carries an inner `timeout -s KILL` that is
    <= the declared ceiling; a started UNIT outlives the step by design (reader/supervisor) and is never restarted.
"""
import base64
import os
import selectors
import signal
import struct
import time
from datetime import datetime, timedelta, timezone

EXTENDED_RESULT_SCHEMA = "L12HOST_EXTENDED_RESULT_V3"
CLAIM_SCHEMA = "L12HOST_EXTENDED_CLAIM_V3"
TERMINAL_SCHEMA = "L12HOST_EXTENDED_TERMINAL_V3"
PRE_EFFECT_SCHEMA = "L12HOST_EXTENDED_PRE_EFFECT_V3"
MAX_PACKET = 400000
CLEANUP_SECONDS = 1.0
PACKET_KEYS = {"status", "code", "effect_calls", "pre_effect", "original_b64", "original_completed_at", "result_class"}
STATUSES = ("EXTENDED_COMPLETE", "EXTENDED_REFUSED_CONSUMED", "EXTENDED_UNCERTAIN_CONSUMED")


RT = None   # the running l12host_runtime module, injected by its Family loader (never imported by name)


def _rt():
    if RT is None:
        raise ValueError("RUNTIME_MODULE_NOT_INJECTED")
    return RT


# ====================================================================== gates from signed sections
class Gates:
    def __init__(self, shell):
        self.s = shell

    # ---------------------------------------------------------- helpers
    def verifier(self, view, name):
        module, identity, source_sha = view.external(name)
        callback = getattr(module, identity, None)
        rt = _rt()
        rt.need(callable(callback), "EXTERNAL_CALLBACK_ABSENT")
        return (self.s.fam.vb.Verifier(view.mode, identity, source_sha, callback, module),
                {"identity": identity, "source_sha256": source_sha})

    def effect_source_sha256(self, view, role):
        """S4: the source of a capacity original is the PRODUCING lot's signed effect source (its pinned program
        file), never the selector it is compared with."""
        rt = _rt()
        row = view.authority["effects"].get(role)
        rt.need(type(row) is dict and row.get("kind") == "HOST_PROGRAM" and row["source"] in view.authority["files"],
                "CAPACITY_PRODUCER_SOURCE_UNSIGNED")
        return view.authority["files"][row["source"]]

    def linked(self, view, role):
        receipt = self.actual(view, role)
        return self.s.fam.cap.LinkedReceipt(receipt.raw, self.effect_source_sha256(view, role), role, tuple(view.context),
                                            "COMPLETE", receipt.completed_at, view.files["request.json"],
                                            view.files["bound.json"])

    def actual(self, view, role):
        """Actual original of `role` produced by `view` (this or another installed lot), decoded by ITS ABI decoder
        and proven by the core ledger's durable OUTER COMPLETE terminal of that lot's REQUEST/BOUND."""
        rt, s, fb = _rt(), self.s, self.s.fam.fb
        key = rt.sha(rt.canonical(list(view.context) + [role]))
        env = rt.read_envelope(s.layout, s.runtime["election"], key)
        rt.need(env["request_sha256"] == view.request_sha256 and env["bound_sha256"] == view.bound_sha256
                and env["role"] == role, "LINKED_ENVELOPE_UNBOUND")
        invocation = fb.Invocation(role, view.context, view.request_sha256, view.bound_sha256,
                                   rt.native_utc() + timedelta(seconds=60), time.monotonic() + 60, ())
        receipt = view.decoders.decode(role, env["original"], invocation, effect_row=view.authority["effects"].get(role),
                                       stored=True)
        ledger = s.ledger
        own = ledger is None
        if own:
            ledger = s.open_ledger()
        try:
            ledger.dependency(view.context + (role,), view.request_sha256, view.bound_sha256, receipt)
        finally:
            if own:
                ledger.close()
        return receipt

    def lot_view(self, lot):
        return self.s.view if lot == self.s.authority["lot"] else self.s.import_view(lot)

    # ---------------------------------------------------------- BOOTSTRAP_MONDAY image GO
    def image_go_read(self, q, task, now):
        s = self.s
        row = s.authority["bootstrap"]["image_go"][task["operation"]]
        return s.fam.fb.ImageGo(s.view.file(row["go"]), s.view.file(row["proposal"]),
                                tuple((label, s.view.file(rel)) for label, rel in row["documents"]))

    def image_go_verify(self):
        s = self.s
        name = s.authority["bootstrap"]["image_go_verifier"]

        def verify(evidence, bundle, q, task, dependencies, now):
            verifier, expected = self.verifier(s.view, name)
            verifier.invoke(expected, s.view.mode, evidence, bundle, q, task, dependencies, now)
        return s.core_codes(verify)

    # ---------------------------------------------------------- CAPACITY_MONDAY cross-lot dependency
    def capacity_rule(self):
        rt, s, fb = _rt(), self.s, self.s.fam.fb
        c = s.authority["capacity"]
        lots = c["lots"]
        views = {name: self.lot_view(lot) for name, lot in lots.items()}
        rt.need(views["m3"].q["lane"] == "BOOTSTRAP_MONDAY" and views["j"].q["lane"] == "DOWNSTREAM_AFTER_E6"
                and views["activation"].q["lane"] == "CAPACITY_MONDAY", "CAPACITY_LOTS_LANES_INVALID")
        for view in views.values():
            rt.need(view.authority["capacity"] == c, "CAPACITY_SECTION_NOT_IDENTICAL_ACROSS_LOTS")
        roles = {"m3": "activate", "j": "admission_manifest", "activation": "capacity_activate"}
        selectors_ = {name: {"source_sha256": c["sources"][name], "request_sha256": views[name].request_sha256,
                             "bound_sha256": views[name].bound_sha256, "role": roles[name],
                             "context": list(views[name].context)} for name in roles}
        consumers = {lane: {"request_sha256": views[n].request_sha256, "bound_sha256": views[n].bound_sha256,
                            "authority_sha256": views[n].q["authority_sha256"]}
                     for lane, n in (("CAPACITY_MONDAY", "activation"), ("DOWNSTREAM_AFTER_E6", "j"))}
        verifiers = {name: self.verifier(s.view, c["verifiers"][name])[1] for name in ("rule", "original", "config")}
        rule = {"schema": "CAPACITY_MONDAY_RULE_CANDIDATE_V1", "mode": c["mode"], "epoch": fb.EPOCH, "day": fb.DAY,
                "authority_sha256": rt.sha(rt.canonical(c)), "selectors": selectors_, "consumers": consumers,
                "verifiers": verifiers}
        return fb.canonical(rule), views

    def capacity_dependencies(self):
        s = self.s
        if s.authority["capacity"] is None:
            return None

        def gate(bundle, q, task, now):
            rt, cap = _rt(), s.fam.cap
            c = s.authority["capacity"]
            rule_raw, views = self.capacity_rule()

            def read_proof(rule_bytes, b, q_, t, current):
                rt.need(rule_bytes == rule_raw, "CAPACITY_RULE_CHANGED")
                m3 = self.linked(views["m3"], "activate")
                j = self.linked(views["j"], "admission_manifest")
                activation = None
                if t["operation"] != "capacity_activate":
                    activation = self.linked(views["activation"], "capacity_activate")
                config_raw = rt.read_path(c["config_path"], rt.LIMIT, rt.Hold)
                return cap.CapacityMondayProof(c["mode"], m3, j, config_raw, rt.sha(config_raw), activation)
            v = {name: self.verifier(s.view, c["verifiers"][name])[0] for name in ("rule", "original", "config")}
            gate_ = cap.CapacityMondayGate(rule_raw, rule_sha256=s.fam.fb.sha(rule_raw), read_proof=read_proof,
                                           verify_rule=v["rule"], verify_original=v["original"], verify_config=v["config"])
            gate_(bundle, q, task, now)
        return s.core_codes(gate)

    def j_config_sha256(self):
        rt, s = _rt(), self.s
        lot = s.authority["capacity"]["lots"]["j"] if s.authority["capacity"] else s.authority["lot"]
        receipt = self.actual(self.lot_view(lot), "admission_manifest")
        writer = s.fam.fb.strict(receipt.raw[:-1] if receipt.raw.endswith(b"\n") else receipt.raw)
        rt.need(rt.pin(writer.get("capacity_config_sha256")), "J_CONFIG_SHA_ABSENT")
        return writer["capacity_config_sha256"]


class StepGates(Gates):
    """The gate set of the DOWN extended steps. The vendored R6/C6 gate classes bind to core tasks (task in
    plan['tasks'] with operation reader_cycle/capture_launch); v3 has no such core task (B3), so these are the SAME
    checks composed for the step's own signed window: CapacityMondayGate's original/order/config rules, the bounded
    readback r1 decoder plus the pure C6 phase predicates, and ReadyWaitGate's finite read-only wait. Codex reviews
    this composition (CONTRACT section 5)."""

    def task_like(self, step):
        return {"operation": step["step"], "not_before": step["not_before"], "not_after": step["not_after"],
                "budget_seconds": step["ceiling_seconds"]}

    def guard(self, task):
        rt = _rt()
        now = rt.native_utc()
        rt.need(rt.stamp(task["not_before"], rt.Hold) <= now < rt.stamp(task["not_after"], rt.Hold), "STEP_GATE_WINDOW_CLOSED")
        return now

    def capacity_chain(self, task):
        rt, s, fb, cap = _rt(), self.s, self.s.fam.fb, self.s.fam.cap
        c = s.authority["capacity"]
        rule_raw, views = self.capacity_rule()
        rule = fb.strict(rule_raw)
        consumer = rule["consumers"]["DOWNSTREAM_AFTER_E6"]
        rt.need(consumer == {"request_sha256": s.request_sha256, "bound_sha256": s.bound_sha256,
                             "authority_sha256": s.q["authority_sha256"]}, "CAPACITY_CHAIN_CONSUMER_UNBOUND")
        v = {name: self.verifier(s.view, c["verifiers"][name]) for name in ("rule", "original", "config")}
        now = self.guard(task)
        v["rule"][0].invoke(v["rule"][1], c["mode"], rule_raw, s.bundle, s.q, task, now)
        items = {"m3": self.linked(views["m3"], "activate"), "j": self.linked(views["j"], "admission_manifest"),
                 "activation": self.linked(views["activation"], "capacity_activate")}
        now = self.guard(task)
        for name, item in items.items():
            selector = rule["selectors"][name]
            rt.need(item.status == "COMPLETE" and item.source_sha256 == selector["source_sha256"]
                    and item.role == selector["role"] and item.context == tuple(selector["context"])
                    and fb.sha(item.request_raw) == selector["request_sha256"]
                    and fb.sha(item.bound_raw) == selector["bound_sha256"], "CAPACITY_MONDAY_SOURCE_OR_BOUND_CHANGED")
            rt.need(fb.instant("2026-10-12T04:00:00Z") <= fb.instant(item.completed_at) <= now,
                    "CAPACITY_MONDAY_RECEIPT_CLOCK")
            v["original"][0].invoke(v["original"][1], c["mode"], item, selector, rule_raw, s.bundle, s.q, task, now)
        rt.need(fb.instant(items["m3"].completed_at) <= fb.instant(items["j"].completed_at)
                <= fb.instant(items["activation"].completed_at), "CAPACITY_MONDAY_ORDER")
        config_raw = rt.read_path(c["config_path"], rt.LIMIT, rt.Hold)
        j = fb.strict(items["j"].raw[:-1] if items["j"].raw.endswith(b"\n") else items["j"].raw)
        rt.need(j.get("schema") == "R2D2_V2_BAR_MANIFEST_WRITER_RECEIPT_V1" and j.get("status") == "PUBLISHED_VERIFIED"
                and j.get("mode") == "PUBLISH" and j.get("code") is None and j.get("epoch") == fb.EPOCH
                and j.get("session") == fb.DAY and j.get("capacity_config_sha256") == fb.sha(config_raw)
                and j.get("massive_bars_enabled") is True
                and fb.instant(j.get("published_at")) == fb.instant(items["j"].completed_at),
                "CAPACITY_MONDAY_J_FINAL_CONFIG_UNBOUND")
        proof = cap.CapacityMondayProof(c["mode"], items["m3"], items["j"], config_raw, fb.sha(config_raw),
                                        items["activation"])
        v["config"][0].invoke(v["config"][1], c["mode"], proof, rule_raw, s.bundle, s.q, task, self.guard(task))
        return fb.sha(config_raw)

    def scope(self):
        rt, s = _rt(), self.s
        g = s.authority["gate"]
        sc = g["scope"]
        rt.need(type(sc) is dict and set(sc) == {"build_sha", "image_id", "document_order_sha256", "release_sha256",
                                                "package_sha256", "calendar_pin_sha256", "runtime_authority_sha256",
                                                "owner_uid", "manifest_directory", "session_open", "not_before",
                                                "not_after", "view_opens_at", "require_go_mode"},
                "GATE_SCOPE_SECTION_INVALID")
        times = {k: rt.stamp(sc[k], rt.Hold) for k in ("session_open", "not_before", "not_after", "view_opens_at")}
        return s.fam.image.Scope(sc["build_sha"], sc["image_id"], sc["document_order_sha256"], sc["release_sha256"],
                                 sc["package_sha256"], self.j_config_sha256(), sc["calendar_pin_sha256"],
                                 sc["runtime_authority_sha256"], s.q["authority_sha256"], sc["owner_uid"],
                                 sc["manifest_directory"], times["session_open"], times["not_before"], times["not_after"],
                                 times["view_opens_at"], sc["require_go_mode"])

    def image_phase(self, phase, task, ready_sha256=None):
        """Codex bounded readback r1 (bounded_image_capacity_gate ade4c4b0) for the step's window: rule + both REAL
        verifier bindings + read authority approved BEFORE the snapshot callback; snapshot verifier; bounded decode;
        journal root; the pure C6 phase predicate. For BEFORE_FIRST_READER the snapshot's ready.json must be the
        exact one this claim's READY wait verified."""
        rt, s = _rt(), self.s
        fb, image, bounded, bgate, gatemod = s.fam.fb, s.fam.image, s.fam.bounded, s.fam.bgate, s.fam.gate
        g = s.authority["gate"]
        allowed = {"session_start": ("BEFORE_FIRST_READER", "AFTER_FIRST_CYCLE"),
                   "capture_launch": ("BEFORE_CAPTURE_LAUNCH", "AFTER_CAPTURE")}
        rt.need(phase in allowed.get(task["operation"], ()), "IMAGE_GATE_PHASE_NOT_THE_STEP_ONE")
        scope = self.scope()
        rt.need(scope.epoch == s.q["epoch"] == fb.EPOCH and scope.day == s.q["session"] == fb.DAY
                and scope.finite_authority_sha256 == s.q["authority_sha256"], "IMAGE_GATE_SCOPE_CHANGED")
        rule_raw = s.view.file(g["readback"]["rule"])
        rule_v, _ = self.verifier(s.view, g["readback"]["rule_verifier"])
        readback_v, _ = self.verifier(s.view, g["readback"]["readback_verifier"])
        decoder = bounded.BoundedReadbackDecoder(rule_raw, fb.sha(rule_raw), rule_v, readback_v,
                                                 request_sha256=s.request_sha256, bound_sha256=s.bound_sha256,
                                                 read_authority_raw=s.view.files["authority.json"], mode=s.view.mode)
        reader_m, reader_id, _ = s.view.external(g["snapshot_reader"])
        verify_m, verify_id, _ = s.view.external(g["snapshot_verifier"])
        snapshot_read, snapshot_verify = getattr(reader_m, reader_id, None), getattr(verify_m, verify_id, None)
        timing = gatemod._TimeBudget(task)
        current = timing.check()
        decoder.authorize(scope, phase, now=current, plan=s.q, task=task)
        current = timing.check()
        rt.need(callable(snapshot_read), "REAL_IMAGE_SNAPSHOT_READER_UNAVAILABLE")
        snapshot = snapshot_read(scope, phase, current)
        current = timing.check()
        rt.need(type(snapshot) is bgate.BoundedSnapshot, "BOUNDED_IMAGE_SNAPSHOT_REQUIRED")
        rt.need(type(snapshot.readback_raw) is bytes and 0 < len(snapshot.readback_raw) <= bounded.WIRE_LIMIT,
                "BOUNDED_IMAGE_SNAPSHOT_SIZE_LIMIT")
        current = timing.observe(snapshot.observed_at)
        fb.accepted(snapshot_verify, snapshot, scope, phase, current, s.q, task)
        current = timing.check()
        try:
            decoded = decoder.decode(snapshot.readback_raw, scope, phase, now=current, plan=s.q, task=task)
            rt.need(decoded.observed_at == fb.instant(snapshot.observed_at), "BOUNDED_OBSERVATION_CHANGED")
            current = timing.check()
            receipt = image.strict_json(snapshot.receipt_raw)
            image.journal_root_gate(scope, snapshot.epoch_catalog, snapshot.journal_root,
                                    settings_journal_directory=snapshot.settings_journal_directory,
                                    expected_journal_directory=g["journal_directory"])
            args = scope, receipt, decoded.row, decoded.journal, snapshot.manifest
            nb, na = fb.instant(task["not_before"]), fb.instant(task["not_after"])
            if phase == "BEFORE_FIRST_READER":
                rt.need(snapshot.ready is not None and snapshot.session_manifest is not None
                        and snapshot.session_root is not None, "IMAGE_SESSION_EVIDENCE_MISSING")
                rt.need(rt.pin(ready_sha256) and fb.sha(snapshot.ready.raw) == ready_sha256, "READY_NOT_THE_WAITED_ONE")
                rt.need(snapshot.calendar_pin_sha256 == scope.calendar_pin_sha256 and snapshot.session_close is not None,
                        "IMAGE_CALENDAR_CLOSE_UNBOUND")
                image.reader_gate(*args, snapshot.ready, snapshot.session_manifest, snapshot.session_root, now=current,
                                  not_before=nb, not_after=na, session_close=fb.instant(snapshot.session_close))
            elif phase == "AFTER_FIRST_CYCLE":
                image.after_first_cycle_gate(*args, now=current)
            elif phase == "BEFORE_CAPTURE_LAUNCH":
                image.capture_launch_gate(*args, now=current, not_before=nb, not_after=na)
            else:
                image.after_capture_gate(*args, now=current)
        except image.Hold as error:
            raise rt.Hold(str(error)) from None
        timing.check()

    def ready_wait(self, task):
        """ReadyWaitGate 5bbef9a6 semantics for the step's window: finite, read-only, inside the SAME claim; only a
        verified ABSENCE waits; a present divergent file fails at once; native UTC and monotonic guards; the deadline
        is min(max_wait, the READY rule window, the step window). Returns (raw, observed_at)."""
        rt, s, fb, image = _rt(), self.s, self.s.fam.fb, self.s.fam.image
        r = s.authority["ready"]
        vr, er = self.verifier(s.view, r["verifiers"]["rule"])
        vy, ey = self.verifier(s.view, r["verifiers"]["ready"])
        rule_raw = fb.canonical({"schema": "L12_READY_WAIT_RULE_CANDIDATE_V1", "mode": r["mode"], "epoch": fb.EPOCH,
                                 "day": fb.DAY, "request_sha256": s.request_sha256, "bound_sha256": s.bound_sha256,
                                 "calendar_sha256": r["calendar_sha256"], "not_before": r["not_before"],
                                 "not_after": r["not_after"], "max_wait_seconds": r["max_wait_seconds"],
                                 "poll_seconds": r["poll_seconds"], "verifiers": {"rule": er, "ready": ey}})
        start, mark = rt.native_utc(), time.monotonic()
        last = [start, mark]
        begin = max(fb.instant(task["not_before"]), fb.instant(r["not_before"]))
        end = min(fb.instant(task["not_after"]), fb.instant(r["not_after"]))
        deadline = mark + min(task["budget_seconds"], r["max_wait_seconds"], (end - start).total_seconds())

        def guard():
            current, mono = rt.native_utc(), time.monotonic()
            rt.need(current >= last[0] and mono >= last[1], "READY_WAIT_CLOCK_REGRESSION")
            last[0], last[1] = current, mono
            rt.need(begin <= current < end and mono < deadline, "READY_WAIT_DEADLINE")
            return current
        while True:
            current = guard()
            vr.invoke(er, r["mode"], rule_raw, s.bundle, s.q, task, current)
            current = guard()
            try:
                info = os.lstat(r["ready_path"])
                rt.need(not os.path.islink(r["ready_path"]), "READY_FILE_SYMLINK")
                raw = rt.read_path(r["ready_path"], 65536, rt.Hold)
                evidence = image.FileEvidence(raw, info.st_dev, info.st_ino, info.st_uid, info.st_gid,
                                              info.st_mode & 0o7777, info.st_nlink)
            except FileNotFoundError:
                evidence = None
            current = guard()
            if evidence is not None:
                body = image.strict_json(evidence.raw)
                rt.need(body == {"epoch": fb.EPOCH, "session": fb.DAY}, "READY_WAIT_ORIGINAL_DIVERGENT")
                vy.invoke(ey, r["mode"], evidence, rule_raw, s.bundle, s.q, task, current)
                return evidence.raw, guard()
            guard()
            time.sleep(min(r["poll_seconds"], max(0, deadline - time.monotonic())))


# ====================================================================== EXTENDED family
def extended_dir_fd(s):
    rt = _rt()
    e = s.runtime["election"]
    return rt.open_chain(e["root_chain"] + [[rt.child(s.layout, "extended"), e["children"]["extended"]]])


def durable_step(s, step):
    """DURABLE state of an extended step or HOLD: claim + terminal + envelope present, canonical, mutually bound."""
    rt = _rt()
    key = rt.sha(rt.canonical(list(s.context) + ["EXTENDED", step]))
    fd = extended_dir_fd(s)
    try:
        claim_raw = rt.read_at(fd, "xclaim-" + key, 65536, rt.Hold)
        term_raw = rt.read_at(fd, "xterm-" + key, 65536, rt.Hold)
    finally:
        os.close(fd)
    claim, term = rt.strict(claim_raw, 65536, rt.Hold), rt.strict(term_raw, 65536, rt.Hold)
    rt.need(claim.get("schema") == CLAIM_SCHEMA and claim.get("attempt_key") == key
            and claim.get("request_sha256") == s.request_sha256 and claim.get("bound_sha256") == s.bound_sha256
            and term.get("schema") == TERMINAL_SCHEMA and term.get("attempt_key") == key
            and term.get("claim_sha256") == rt.sha(claim_raw), "EXTENDED_STATE_NOT_DURABLE")
    rt.need(term.get("status") == "EXTENDED_COMPLETE" and rt.pin(term.get("original_sha256")), "EXTENDED_DEPENDENCY_NOT_COMPLETE")
    env = rt.read_envelope(s.layout, s.runtime["election"], key)
    rt.need(env["original_sha256"] == term["original_sha256"] and env["role"] == step
            and env["request_sha256"] == s.request_sha256 and env["bound_sha256"] == s.bound_sha256,
            "EXTENDED_ENVELOPE_UNBOUND")
    return env, term


def _send(fd, payload, canonical):
    raw = canonical(payload)
    framed = struct.pack("!I", len(raw)) + raw
    offset = 0
    while offset < len(framed):
        offset += os.write(fd, framed[offset:])


def dependencies(s, step):
    rt, fb = _rt(), s.fam.fb
    for kind, dep in step["requires"]:
        inv = fb.Invocation(dep, s.context, s.request_sha256, s.bound_sha256,
                            rt.native_utc() + timedelta(seconds=60), time.monotonic() + 60, ())
        if kind == "core":
            dkey = rt.sha(rt.canonical(list(s.context) + [dep]))
            env = rt.read_envelope(s.layout, s.runtime["election"], dkey)
            rt.need(env["request_sha256"] == s.request_sha256 and env["bound_sha256"] == s.bound_sha256,
                    "EXTENDED_CORE_DEPENDENCY_OTHER_BOUND")
            receipt = s.view.decoders.decode(dep, env["original"], inv, effect_row=s.authority["effects"][dep], stored=True)
            ledger = s.open_ledger()
            try:
                ledger.dependency(s.context + (dep,), s.request_sha256, s.bound_sha256, receipt)
            finally:
                ledger.close()
        else:
            env, term = durable_step(s, dep)
            again = s.view.decoders.decode(dep, env["original"], inv, extended=True,
                                           effect_row=s.view.extended_effect(dep), stored=True)
            rt.need(rt.sha(again.raw) == term["original_sha256"], "EXTENDED_DEPENDENCY_REDECODE_MISMATCH")


def engine(s, target_kind, name, key, veto, ready_sha=None, supervisor_pid=None):
    rt, fx = _rt(), s.fam.fx
    argv = fx.engine_argv(s.lot_dir, target_kind, name, s.q["authority_sha256"], s.request_sha256, key,
                          rt.sha(veto.raw), rt.iso(veto.valid_until), ready_sha, supervisor_pid)
    return fx.run(argv)


READY_ABSENT_SCHEMA = "L12HOST_READY_ABSENT_V31"


def ready_absent_now(s):
    """v3.1: the signed ready path does not exist (any type). Read-only (lstat)."""
    rt = _rt()
    path = s.authority["ready"]["ready_path"]
    try:
        os.lstat(path)
    except FileNotFoundError:
        return path
    except OSError:
        raise rt.Hold("READY_LEFTOVER_PRESENT") from None
    raise rt.Hold("READY_LEFTOVER_PRESENT")


def env_file_identities(s, step):
    """v3.1 (finding 7): the identity of every env file of the session units, by lstat only (never opened): pinned at
    the claim and re-checked before the reader start, so a swapped secret file is a HOLD."""
    rt, fx = _rt(), s.fam.fx
    rows = []
    for row in (step["pre_effect"], step["effect"]):
        for path in fx.row_env_files(row, s.layout):
            try:
                info = os.lstat(path)
            except OSError:
                raise rt.Hold("UNIT_ENV_FILE_UNAVAILABLE") from None
            rows.append([path, rt.file_identity9(info)])
    return rows


def armed(s, row, deadline_utc, deadline_mono):
    """Fresh double ALLOW, then BEFORE_EFFECT with the remaining-budget floor, right before the transport."""
    rt = _rt()
    s.effect_preflight(row)
    veto = s.fresh_allow()
    rt.need(rt.native_utc() < deadline_utc and time.monotonic() < deadline_mono, "EXTENDED_DEADLINE")
    s.before_effect(row, deadline_utc)
    return veto


def original_of(rt, out):
    original = base64.b64decode(out["original_b64"], validate=True)
    rt.need(rt.sha(original) == out["original_sha256"], "EFFECT_OUTPUT_INVALID")
    return original


def pre_effect_marker(s, key, step):
    """The declared supervisor start is RECORDED before its transport (Codex B3 review): xpre-<key>, O_EXCL."""
    rt = _rt()
    fd = extended_dir_fd(s)
    try:
        rt.write_new_at(fd, "xpre-" + key, rt.canonical({"schema": PRE_EFFECT_SCHEMA, "attempt_key": key, "step": step,
                                                          "effect": "SUPERVISOR_UNIT_START",
                                                          "request_sha256": s.request_sha256,
                                                          "bound_sha256": s.bound_sha256,
                                                          "at": rt.iso(rt.native_utc())}), 0o400)
    finally:
        os.close(fd)


def step_worker(s, step, key, scope, deadline_utc, deadline_mono):
    """In the session-leader worker. Returns the packet dict (never raises)."""
    rt, fb = _rt(), s.fam.fb
    name = step["step"]
    step_kind = rt.EXTENDED_TABLE[s.q["lane"]][name][0]
    packet = {"status": "EXTENDED_REFUSED_CONSUMED", "code": None, "effect_calls": 0, "pre_effect": None,
              "original_b64": None, "original_completed_at": None, "result_class": None}
    gates = StepGates(s)
    task = gates.task_like(step)
    try:
        now = rt.native_utc()
        rt.need(os.getpid() == os.getpgrp() == os.getsid(0), "EXTENDED_WORKER_SCOPE_INVALID")
        s.authority_check("EXTENDED", name, now)
        s.identity_check()
        rt.need(rt.stamp(s.view.owner["signed_at"], rt.Hold) < rt.stamp(step["not_before"], rt.Hold),
                "OWNER_NOT_BEFORE_EFFECT_WINDOW")
        dependencies(s, step)
        inv = fb.Invocation(name, s.context, s.request_sha256, s.bound_sha256, deadline_utc, deadline_mono, ())
        if step_kind == "RUNNER":
            veto = armed(s, step["effect"], deadline_utc, deadline_mono)
            code, out = engine(s, "EXTENDED", name, key, veto)
            packet["effect_calls"] = 1 if (out.get("transport_at") is not None or out.get("status") == "UNCERTAIN") else 0
            rt.need(code == 0, out.get("code") or "EXTENDED_EFFECT_NOT_DONE")
            original = original_of(rt, out)
            receipt = s.view.decoders.decode(name, original, inv, extended=True, effect_row=step["effect"])
            rt.need(rt.read_path(step["effect"]["receipt"]["path"], s.fam.fx.MAX_ORIGINAL, rt.Hold) == original,
                    "RECEIPT_FILE_MISMATCH")
        elif step_kind == "CAPTURE":
            gates.capacity_chain(task)
            gates.image_phase("BEFORE_CAPTURE_LAUNCH", task)
            veto = armed(s, step["effect"], deadline_utc, deadline_mono)
            code, out = engine(s, "EXTENDED", name, key, veto)
            packet["effect_calls"] = 1 if (out.get("transport_at") is not None or out.get("status") == "UNCERTAIN") else 0
            rt.need(code == 0, out.get("code") or "EXTENDED_EFFECT_NOT_DONE")
            original = original_of(rt, out)
            receipt = s.view.decoders.decode(name, original, inv, extended=True, effect_row=step["effect"])
            rt.need(rt.read_path(step["effect"]["receipt"]["path"], s.fam.fx.MAX_ORIGINAL, rt.Hold) == original,
                    "RECEIPT_FILE_MISMATCH")
            gates.image_phase("AFTER_CAPTURE", task)
        elif step_kind == "READY_CHECK":
            path = ready_absent_now(s)
            original = rt.canonical({"schema": READY_ABSENT_SCHEMA, "step": name, "ready_path_sha256":
                                     rt.sha(path.encode("ascii")), "absent": True,
                                     "observed_at": rt.iso(gates.guard(task)), "operational_GO": False})
            receipt = s.view.decoders.decode(name, original, inv, extended=True, effect_row=None)
        else:
            receipt, original = session_start(s, step, key, task, gates, inv, deadline_utc, deadline_mono, packet)
        rt.need(rt.native_utc() < deadline_utc and time.monotonic() < deadline_mono, "EXTENDED_DEADLINE")
        packet.update(status="EXTENDED_COMPLETE", code=None, original_b64=base64.b64encode(original).decode("ascii"),
                      original_completed_at=rt.iso(receipt.completed_at),
                      result_class=s.fam.dec.result_class(step["decoder"]["kind"]))
    except BaseException as error:
        packet["code"] = rt.safe_code(error)
        packet["status"] = "EXTENDED_UNCERTAIN_CONSUMED" if packet["effect_calls"] else "EXTENDED_REFUSED_CONSUMED"
    return packet


def session_start(s, step, key, task, gates, inv, deadline_utc, deadline_mono, packet):
    """B3, one claim: gates -> declared supervisor start -> READY wait -> RECHECK -> BEFORE_FIRST_READER -> reader start
    while READY is present -> hold through the first-cycle instant -> decode -> AFTER_FIRST_CYCLE."""
    rt, fb, fx = _rt(), s.fam.fb, s.fam.fx
    name = step["step"]
    sup_unit = step["pre_effect"]["unit"]["name"]
    identities = env_file_identities(s, step)
    gates.capacity_chain(task)
    veto = armed(s, step["pre_effect"], deadline_utc, deadline_mono)
    # v3.1 (finding 2): a ready file that exists BEFORE this supervisor starts is a leftover: HOLD, no effect.
    try:
        ready_absent_now(s)
    except rt.Hold:
        raise rt.Hold("READY_LEFTOVER_PRESENT_BEFORE_SUPERVISOR") from None
    rt.need(env_file_identities(s, step) == identities, "UNIT_ENV_FILE_IDENTITY_CHANGED")
    pre_effect_marker(s, key, name)
    packet["pre_effect"] = {"marker": "WRITTEN", "status": "STARTING"}
    code, out = engine(s, "EXTENDED_PRE", name, key, veto)
    if out.get("transport_at") is not None or out.get("status") == "UNCERTAIN":
        packet["effect_calls"] = 1
    packet["pre_effect"] = {"marker": "WRITTEN", "status": "TRANSPORT_DONE" if code == 0 else "NOT_DONE",
                            "code": out.get("code"), "original_sha256": out.get("original_sha256")}
    rt.need(code == 0, out.get("code") or "SUPERVISOR_START_NOT_DONE")
    supervisor_ack = original_of(rt, out)
    sup_doc = s.view.decoders.ack(supervisor_ack, "SUPERVISOR", sup_unit, False)
    sup_pid = sup_doc["properties"]["MainPID"]
    ready_raw, ready_at = gates.ready_wait(task)
    ready_sha = rt.sha(ready_raw)
    # RECHECK after the wait: bytes/authority/owner/window, identity, dependencies, capacity chain.
    s.authority_check("EXTENDED", name, rt.native_utc())
    s.identity_check()
    dependencies(s, step)
    gates.capacity_chain(task)
    gates.image_phase("BEFORE_FIRST_READER", task, ready_sha)
    rt.need(env_file_identities(s, step) == identities, "UNIT_ENV_FILE_IDENTITY_CHANGED")
    # v3.1 (finding 5): the acknowledged supervisor is still running, same MainPID, before the reader (the engine
    # re-checks it at the transport and through the hold).
    try:
        fx.supervisor_alive(s.layout, list(fx.CHILD_ENV_BASE), sup_unit, sup_pid, deadline_utc)
    except fx.Hold:
        raise rt.Hold("SUPERVISOR_NOT_RUNNING_BEFORE_READER") from None
    veto = armed(s, step["effect"], deadline_utc, deadline_mono)
    code, out = engine(s, "EXTENDED", name, key, veto, ready_sha, sup_pid)
    if out.get("transport_at") is not None or out.get("status") == "UNCERTAIN":
        packet["effect_calls"] = 2
    rt.need(code == 0, out.get("code") or "READER_START_NOT_DONE")
    reader_ack = original_of(rt, out)
    record = rt.canonical({"schema": s.fam.dec.SESSION_SCHEMA,
                           "result_class": s.fam.dec.RESULT_CLASSES["SESSION_START_V3"], "step": name,
                           "supervisor_ack_b64": base64.b64encode(supervisor_ack).decode("ascii"),
                           "supervisor_ack_sha256": rt.sha(supervisor_ack),
                           "reader_ack_b64": base64.b64encode(reader_ack).decode("ascii"),
                           "reader_ack_sha256": rt.sha(reader_ack), "ready_sha256": ready_sha,
                           "ready_observed_at": rt.iso(ready_at), "gates": list(s.fam.dec.SESSION_GATES),
                           "hold_until": step["hold_until"], "observed_at": rt.iso(rt.native_utc()),
                           "operational_GO": False})
    receipt = s.view.decoders.decode(name, record, inv, extended=True, effect_row=step["effect"])
    gates.image_phase("AFTER_FIRST_CYCLE", task)
    return receipt, record


def run_step(s, row, key, scope):
    """Parent side: claim first, supervise one session-leader worker under the declared ceiling, terminal."""
    rt = _rt()
    step = s.view.step(row["target"])
    started, mark = rt.native_utc(), time.monotonic()
    out = {"schema": EXTENDED_RESULT_SCHEMA, "step": step["step"], "attempt_key": key, "status": None, "code": None,
           "effect_calls": 0, "pre_effect": None, "result_class": None, "recovery_required": False,
           "ceiling_seconds": step["ceiling_seconds"], "worker_cleanup": "NOT_STARTED", "original_sha256": None,
           "original_completed_at": None, "terminal": None, "completed_at": None, "automatic_retry": False,
           "operational_GO_granted": False}
    claim_raw = rt.canonical({"schema": CLAIM_SCHEMA, "attempt_key": key, "scope": scope, "lot": s.authority["lot"],
                              "slot": row["slot"], "request_sha256": s.request_sha256, "bound_sha256": s.bound_sha256,
                              "ceiling_seconds": step["ceiling_seconds"], "at": rt.iso(started)})
    try:
        fd = extended_dir_fd(s)
        try:
            rt.write_new_at(fd, "xclaim-" + key, claim_raw, 0o400)
        finally:
            os.close(fd)
    except FileExistsError:
        out.update(status="EXTENDED_UNCERTAIN_CONSUMED", code="EXTENDED_CLAIM_ALREADY_PRESENT", recovery_required=True,
                   completed_at=rt.iso(rt.native_utc()))
        return out
    except BaseException as error:
        out.update(status="EXTENDED_UNCERTAIN_CONSUMED", code=rt.safe_code(error), recovery_required=True,
                   completed_at=rt.iso(rt.native_utc()))
        return out
    window_left = (rt.stamp(step["not_after"], rt.Hold) - started).total_seconds()
    budget = min(step["ceiling_seconds"], window_left)
    deadline_mono = mark + budget
    deadline_utc = started + timedelta(seconds=budget)
    packet, pid = None, None
    read_fd = write_fd = life_r = life_w = None
    try:
        rt.need(budget > 0, "EXTENDED_WINDOW_CLOSED")
        read_fd, write_fd = os.pipe()
        life_r, life_w = os.pipe()
        pid = os.fork()
        if pid == 0:
            try:
                os.close(read_fd)
                os.close(life_w)
                os.setsid()
                group = os.getpgrp()
                dog = os.fork()
                if dog == 0:
                    os.close(write_fd)
                    watch = selectors.DefaultSelector()
                    watch.register(life_r, selectors.EVENT_READ)
                    while time.monotonic() < deadline_mono:
                        if watch.select(min(0.05, max(0.0001, deadline_mono - time.monotonic()))):
                            if os.read(life_r, 1) == b"":
                                break
                    try:
                        os.killpg(group, signal.SIGKILL)
                    finally:
                        os._exit(1)
                result = step_worker(s, step, key, scope, deadline_utc, deadline_mono)
                _send(write_fd, result, rt.canonical)
                os.close(write_fd)
                while True:
                    signal.pause()
            finally:
                os._exit(1)
        os.close(write_fd)
        write_fd = None
        os.close(life_r)
        life_r = None
        os.set_blocking(read_fd, False)
        sel = selectors.DefaultSelector()
        sel.register(read_fd, selectors.EVENT_READ)
        data, size = bytearray(), None
        try:
            while size is None or len(data) < size + 4:
                left = deadline_mono - time.monotonic()
                rt.need(left > 0, "EXTENDED_CEILING_REACHED")
                if not sel.select(min(0.05, left)):
                    continue
                piece = os.read(read_fd, 65536)
                rt.need(piece, "EXTENDED_WORKER_LOST")
                data.extend(piece)
                rt.need(len(data) <= MAX_PACKET + 4, "EXTENDED_PACKET_LIMIT")
                if size is None and len(data) >= 4:
                    size = struct.unpack("!I", bytes(data[:4]))[0]
                    rt.need(0 < size <= MAX_PACKET, "EXTENDED_PACKET_LIMIT")
        finally:
            sel.close()
        packet = rt.strict(bytes(data[4:size + 4]), MAX_PACKET, rt.Hold)
        rt.need(set(packet) == PACKET_KEYS and packet["status"] in STATUSES and packet["effect_calls"] in (0, 1, 2),
                "EXTENDED_PACKET_INVALID")
    except BaseException as error:
        packet = {"status": "EXTENDED_UNCERTAIN_CONSUMED", "code": rt.safe_code(error), "effect_calls": None,
                  "pre_effect": None, "original_b64": None, "original_completed_at": None, "result_class": None}
    finally:
        for x in (read_fd, write_fd, life_r, life_w):
            if x is not None:
                try:
                    os.close(x)
                except OSError:
                    pass
        if pid is not None:
            out["worker_cleanup"] = cleanup(pid)
            if out["worker_cleanup"] != "GROUP_KILL_ISSUED_WORKER_REAPED" and packet["status"] == "EXTENDED_COMPLETE":
                packet = dict(packet, status="EXTENDED_UNCERTAIN_CONSUMED", code="EXTENDED_GROUP_CLEANUP_UNCERTAIN")
    out.update(status=packet["status"], code=packet["code"], effect_calls=packet["effect_calls"],
               pre_effect=packet["pre_effect"], original_completed_at=packet["original_completed_at"],
               result_class=packet["result_class"] if packet["status"] == "EXTENDED_COMPLETE" else None)
    try:
        if packet["status"] == "EXTENDED_COMPLETE":
            original = base64.b64decode(packet["original_b64"], validate=True)
            completed = rt.stamp(packet["original_completed_at"], rt.Hold)
            envelope = rt.make_envelope("EXTENDED_EFFECT", key, step["step"], s.context, completed, original,
                                        s.request_sha256, s.bound_sha256)
            e = s.runtime["election"]
            fd = rt.open_chain(e["root_chain"] + [[rt.child(s.layout, "receipts"), e["children"]["receipts"]]])
            try:
                rt.write_new_at(fd, key + ".json", envelope)
            finally:
                os.close(fd)
            out["original_sha256"] = rt.sha(original)
        out["completed_at"] = rt.iso(rt.native_utc())
        term = rt.canonical({"schema": TERMINAL_SCHEMA, "attempt_key": key, "claim_sha256": rt.sha(claim_raw),
                             "status": out["status"], "code": out["code"], "effect_calls": out["effect_calls"],
                             "pre_effect": out["pre_effect"], "original_sha256": out["original_sha256"],
                             "original_completed_at": out["original_completed_at"], "completed_at": out["completed_at"],
                             "worker_cleanup": out["worker_cleanup"], "automatic_retry": False})
        fd = extended_dir_fd(s)
        try:
            rt.write_new_at(fd, "xterm-" + key, term, 0o400)
        finally:
            os.close(fd)
        out["terminal"] = "WRITTEN"
    except BaseException as error:
        out.update(status="EXTENDED_UNCERTAIN_CONSUMED", code="EXTENDED_TERMINAL_UNCERTAIN", terminal="UNCERTAIN",
                   result_class=None)
        out["inner_code"] = rt.safe_code(error)
    out["recovery_required"] = out["status"] == "EXTENDED_UNCERTAIN_CONSUMED"
    if out["completed_at"] is None:
        out["completed_at"] = rt.iso(rt.native_utc())
    return out


def cleanup(pid):
    uncertain = False
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    except PermissionError:
        uncertain = True
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    until = time.monotonic() + CLEANUP_SECONDS
    while time.monotonic() < until:
        try:
            found, _ = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return "UNCERTAIN" if uncertain else "GROUP_KILL_ISSUED_WORKER_REAPED"
        if found == pid:
            return "UNCERTAIN" if uncertain else "GROUP_KILL_ISSUED_WORKER_REAPED"
        time.sleep(0.005)
    return "UNCERTAIN"
