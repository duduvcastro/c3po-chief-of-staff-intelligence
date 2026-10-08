"""C34/C35 real family adapter. No historical roots, dates, claims or GO reused.

PERSIST writes the exact K12_PERSISTED_WRITER_RECEIPT_V1 wire shape, with the
new epoch supplied by its bound context. Docker transport is injected by F6;
tests use an emulated engine. There is no arbitrary command or retry API.
"""
import base64
import re
from datetime import timedelta

from common import Hold, canonical, context, digest, fields, instant, linked_receipt, need, sha, strict

PERSIST_SCHEMA = "K12_PERSISTED_WRITER_RECEIPT_V1"
PERSIST_KEYS = {"schema", "epoch", "day", "window", "window_slot", "container_id", "container_name",
                "launch_request_sha256", "capacity_request_sha256", "persist_request_sha256", "image_id",
                "exit_code", "oom_killed", "started_at", "finished_at", "stdout_b64", "stdout_sha256", "stdout_bytes"}
WRITER_SCHEMA = "R2D2_V2_BAR_MANIFEST_WRITER_RECEIPT_V1"
WRITER_CODES = {"PUBLISHED_VERIFIED": (0,), "ALREADY_PUBLISHED_VERIFIED": (0,), "MATCH_VERIFIED": (0,),
                "PREFLIGHT_OK": (0,), "ABSENT": (3,), "REFUSED": (3,), "UNVERIFIED": (1,),
                "PUBLISHED_UNVERIFIED": (1, 3)}
INSPECT_FORMAT = ('{"id":{{json .Id}},"name":{{json .Name}},"image_id":{{json .Image}},'
                  '"state":{{json .State.Status}},"running":{{json .State.Running}},'
                  '"exit_code":{{json .State.ExitCode}},"oom_killed":{{json .State.OOMKilled}},'
                  '"started_at":{{json .State.StartedAt}},"finished_at":{{json .State.FinishedAt}},'
                  '"request_label":{{json (index .Config.Labels "c3po.k12.request_sha256")}},'
                  '"capacity_label":{{json (index .Config.Labels "c3po.k12.capacity_request_sha256")}},'
                  '"read_only_root":{{json .HostConfig.ReadonlyRootfs}},'
                  '"auto_remove":{{json .HostConfig.AutoRemove}},"restart_policy":{{json .HostConfig.RestartPolicy.Name}}}')
INSPECT_KEYS = {"id", "name", "image_id", "state", "running", "exit_code", "oom_killed", "started_at",
                "finished_at", "request_label", "capacity_label", "read_only_root", "auto_remove", "restart_policy",
                "cmd", "network_mode", "mounts"}
INSPECT_FORMAT = INSPECT_FORMAT[:-1] + (',"cmd":{{json .Config.Cmd}},"network_mode":{{json .HostConfig.NetworkMode}},'
                                      '"mounts":{{json .Mounts}}}')
WRITER_KEYS = {"schema", "status", "code", "session", "mode", "epoch", "owner_uid", "release_sha256",
               "capacity_config_sha256", "package_sha256", "build_sha", "capacity_veto_mode", "massive_bars_enabled",
               "cutoff_at", "stale_temporaries", "repaired_temporaries", "prepare_status", "waited_seconds", "view",
               "go_sha256", "go_mode", "template_sha256", "window", "binding_sha256", "symbol_count",
               "manifest_sha256", "published_at", "file", "checks", "windows"}


def writer_legacy_line(raw, ctx, capacity_sha, exit_code):
    """Existing writer's exact one-line ABI; config hash binds the capacity request."""
    need(type(raw) is bytes and 0 < len(raw) <= 16384 and raw.endswith(b"\n")
         and len(raw.splitlines()) == 1, "WRITER_ONE_COMPLETE_LINE")
    value = strict(raw, 16384)
    need(type(value) is dict and set(value) <= WRITER_KEYS
         and value.get("schema") == WRITER_SCHEMA and value.get("status") in WRITER_CODES, "WRITER_SCHEMA")
    need(type(exit_code) is int and exit_code in WRITER_CODES[value["status"]], "WRITER_EXIT_STATUS")
    need(value.get("session") == ctx["session"] and value.get("epoch") == ctx["epoch"]
         and value.get("mode") == "PUBLISH" and value.get("release_sha256") == ctx["release_sha256"], "WRITER_CONTEXT")
    need((value.get("code") is None) == (value["status"] in ("PUBLISHED_VERIFIED", "ALREADY_PUBLISHED_VERIFIED",
                                                           "MATCH_VERIFIED", "PREFLIGHT_OK")), "WRITER_CODE_STATUS")
    if value.get("code") is not None:
        need(type(value["code"]) is str and re.fullmatch(r"[A-Z][A-Z0-9_]{1,100}", value["code"]), "WRITER_CODE")
    for key in ("release_sha256", "capacity_config_sha256", "package_sha256", "go_sha256", "template_sha256",
                "binding_sha256", "manifest_sha256"):
        if key in value: sha(value[key])
    if "symbol_count" in value: need(type(value["symbol_count"]) is int and 0 <= value["symbol_count"] <= 550, "WRITER_COUNT")
    if "prepare_status" in value:
        need(value["prepare_status"] in ("ATTEMPTED", "COMMITTED", "ALREADY_COMMITTED", "PRECOMMITTED"), "WRITER_PREPARE")
    return value


def plan(request, launch_raw, capacity_raw, now):
    ctx = context(request["context"])
    fields(request["payload"], ("mode", "window", "window_slot", "view_UTC", "launch_request_sha256",
                              "launch_receipt_sha256", "capacity_request_sha256", "persist_name", "container_id"), "K12_PLAN_FIELDS")
    p = request["payload"]
    need(p["mode"] in ("PERSIST", "STOP", "COLLECT"), "K12_OPERATION_NOT_REGISTERED")
    need(request["operation"] == "F4_K12_" + p["mode"], "K12_OPERATION_MODE")
    need(type(p["window_slot"]) is int and 1 <= p["window_slot"] <= 9, "K12_SLOT")
    need(p["window"] in ("primary", "contingency_1", "contingency_2"), "K12_WINDOW")
    need(p["persist_name"] == "k12-%s-w%s.writer.json" % (ctx["session"], p["window_slot"]), "K12_PERSIST_NAME")
    need(re.fullmatch(r"[0-9a-f]{64}", p["container_id"] or ""), "K12_CONTAINER_ID")
    need(digest(launch_raw) == sha(p["launch_receipt_sha256"])
         and digest(capacity_raw) == sha(p["capacity_request_sha256"]), "K12_ORIGINAL_HASH")
    launch = linked_receipt(launch_raw, ctx, operation="F4_K12_LAUNCH", request_sha256=p["launch_request_sha256"])
    detail = launch["detail"]
    need(detail["container_id"] == p["container_id"] and detail["capacity_request_sha256"] == p["capacity_request_sha256"]
         and detail["window"] == p["window"] and detail["window_slot"] == p["window_slot"]
         and detail["view_UTC"] == p["view_UTC"], "K12_LAUNCH_BINDING")
    cap = strict(capacity_raw)
    need(cap.get("schema") == "R2D2_CAPACITY_DAY_ONCE_REQUEST_V2" and cap.get("context") == ctx
         and cap.get("window") == p["window"] and cap.get("window_slot") == p["window_slot"]
         and cap.get("view_UTC") == p["view_UTC"], "K12_CAPACITY_CONTEXT")
    need(instant(launch["finished_UTC"]) <= now, "K12_FUTURE_LAUNCH")
    need("K12_COLLECT_COMPLETE" not in request["required_gates"], "C34_DEPENDENCY_CYCLE")
    if p["mode"] == "PERSIST":
        need(instant(request["start_UTC"]) >= instant(p["view_UTC"]) + timedelta(seconds=60), "C34_PERSIST_EARLY")
    if p["mode"] == "STOP":
        need(type(request["budget_seconds"]) is int and request["budget_seconds"] >= 28, "C35_BUDGET")
        start = instant(request["start_UTC"])
        latest = min(instant(request["end_UTC"]) - timedelta(seconds=request["budget_seconds"]),
                     instant(p["view_UTC"]) - timedelta(seconds=25))
        need(instant(launch["finished_UTC"]) < start <= now <= latest and latest > start, "C35_NO_POSITIVE_FLOOR")
    return p, cap, detail


def identified(row, p, cap, launch_detail):
    fields(row, INSPECT_KEYS, "K12_INSPECT_FIELDS")
    name = "c3po-k12-%s-w%s" % (cap["context"]["session"], p["window_slot"])
    need(row["id"] == p["container_id"] and row["name"] == "/" + name and row["image_id"] == cap["image_id"]
         and row["request_label"] == p["launch_request_sha256"] and row["capacity_label"] == p["capacity_request_sha256"]
         and row["read_only_root"] is True and row["auto_remove"] is False and row["restart_policy"] == "no",
         "K12_CONTAINER_IDENTITY")
    need(launch_detail["image_id"] == row["image_id"], "K12_LAUNCH_IMAGE")
    need(row["cmd"] == cap["writer_argv"] and row["network_mode"] == cap["network"], "K12_CONTAINER_COMMAND")
    mounts = []
    need(type(row["mounts"]) is list, "K12_CONTAINER_MOUNTS")
    for item in row["mounts"]:
        need(type(item) is dict and item.get("Type") == "bind" and type(item.get("RW")) is bool,
             "K12_CONTAINER_MOUNTS")
        mounts.append({"source": item["Source"], "destination": item["Destination"], "rw": item["RW"]})
    need(sorted(mounts, key=lambda x: x["destination"]) == sorted(cap["mounts"], key=lambda x: x["destination"]),
         "K12_CONTAINER_MOUNTS")
    need(type(row["running"]) is bool and type(row["oom_killed"]) is bool and type(row["exit_code"]) is int,
         "K12_INSPECT_TYPES")
    return row


def inspect(engine, p, cap, launch_detail):
    result = engine.call("inspect", p["container_id"], INSPECT_FORMAT, limit=65536)
    need(result["returncode"] == 0, "K12_INSPECT_REFUSED")
    return identified(strict(result["stdout"], 65536), p, cap, launch_detail)


def persisted(raw, p, cap, ctx):
    body = fields(strict(raw, 32768), PERSIST_KEYS, "K12_PERSISTED_FIELDS")
    expected = {"schema": PERSIST_SCHEMA, "epoch": ctx["epoch"], "day": ctx["session"], "window": p["window"],
                "window_slot": p["window_slot"], "container_id": p["container_id"],
                "container_name": "c3po-k12-%s-w%s" % (ctx["session"], p["window_slot"]),
                "launch_request_sha256": p["launch_request_sha256"], "capacity_request_sha256": p["capacity_request_sha256"],
                "image_id": cap["image_id"]}
    need(all(body[k] == v for k, v in expected.items()), "K12_PERSISTED_BINDING")
    sha(body["persist_request_sha256"])
    need(body["oom_killed"] is False and instant(body["started_at"]) <= instant(body["finished_at"]), "K12_PERSISTED_STATE")
    try: stdout = base64.b64decode(body["stdout_b64"], validate=True)
    except (ValueError, TypeError): raise Hold("K12_PERSISTED_BASE64") from None
    need(type(body["stdout_bytes"]) is int and len(stdout) == body["stdout_bytes"] and digest(stdout) == body["stdout_sha256"], "K12_STDOUT_HASH")
    line = writer_legacy_line(stdout, ctx, p["capacity_request_sha256"], body["exit_code"])
    need(line["capacity_config_sha256"] == cap["capacity_config_sha256"], "K12_WRITER_CONFIG")
    return body, line


def execute(request, launch_raw, capacity_raw, *, engine, receipts, manifests, clock, recheck):
    """Called only after the F6 invocation reservation and authorization checks.

    Every uncertain subprocess/write/readback escapes as HOLD with the invocation
    consumed by the controller. Nothing here retries, deletes or resets a claim.
    """
    now = instant(clock()); p, cap, detail = plan(request, launch_raw, capacity_raw, now)
    ctx = request["context"]
    recheck()
    if p["mode"] == "COLLECT":
        if not receipts.exists(p["persist_name"]):
            return {"collection": "PENDING_PERSIST", "terminal": False, "effects": 0}
        body, line = persisted(receipts.read(p["persist_name"], limit=32768, modes=(0o600,)), p, cap, ctx)
        return {"collection": "WRITER_PUBLISHED_BYTES_ONLY" if line["status"] in ("PUBLISHED_VERIFIED", "ALREADY_PUBLISHED_VERIFIED")
                else "TERMINAL_UNVERIFIED", "terminal": True, "persisted_sha256": digest(canonical(body)),
                "writer_status": line["status"], "manifest_verified": False, "effects": 0}
    row = inspect(engine, p, cap, detail)
    if p["mode"] == "PERSIST":
        need(not receipts.exists(p["persist_name"]), "K12_PERSIST_ALREADY_EXISTS")
        need(row["state"] == "exited" and row["running"] is False and row["oom_killed"] is False,
             "K12_CONTAINER_NOT_SETTLED")
        need(instant(row["started_at"]) <= instant(row["finished_at"]) <= instant(clock()), "K12_CONTAINER_TIME")
        recheck()
        output = engine.call("logs", p["container_id"], limit=16384)
        need(output["returncode"] == 0, "K12_LOGS_UNAVAILABLE")
        line = writer_legacy_line(output["stdout"], ctx, p["capacity_request_sha256"], row["exit_code"])
        need(line["capacity_config_sha256"] == cap["capacity_config_sha256"], "K12_WRITER_CONFIG")
        after = inspect(engine, p, cap, detail)
        need(after == row, "K12_CONTAINER_CHANGED_DURING_LOGS")
        body = {"schema": PERSIST_SCHEMA, "epoch": ctx["epoch"], "day": ctx["session"], "window": p["window"],
                "window_slot": p["window_slot"], "container_id": row["id"], "container_name": row["name"][1:],
                "launch_request_sha256": p["launch_request_sha256"], "capacity_request_sha256": p["capacity_request_sha256"],
                "persist_request_sha256": digest(canonical(request)), "image_id": row["image_id"], "exit_code": row["exit_code"],
                "oom_killed": row["oom_killed"], "started_at": row["started_at"], "finished_at": row["finished_at"],
                "stdout_b64": base64.b64encode(output["stdout"]).decode(), "stdout_sha256": digest(output["stdout"]),
                "stdout_bytes": len(output["stdout"])}
        persisted(canonical(body), p, cap, ctx)
        recheck()
        pin = receipts.create(p["persist_name"], canonical(body))
        return {"persisted_sha256": pin, "writer_status": line["status"], "effects": 1}
    need(row["state"] == "running" and row["running"] is True, "K12_STOP_NOT_RUNNING")
    manifests.recheck(); before = manifests.state(ctx["session"])
    recheck()
    plan(request, launch_raw, capacity_raw, instant(clock()))
    result = engine.call("stop", p["container_id"], limit=1024)
    after = inspect(engine, p, cap, detail)
    need(result["returncode"] == 0 and after["id"] == row["id"] and after["state"] == "exited"
         and after["running"] is False, "K12_STOP_UNCERTAIN")
    manifests.recheck(); need(manifests.state(ctx["session"]) == before, "K12_STOP_MANIFEST_CHANGED")
    return {"stopped_container_sha256": digest(row["id"].encode()), "manifest_counts": before, "effects": 1}
