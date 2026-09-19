"""Auditable artifact-only risk host phases. No activation, deployment or DB writes.

Order and GO bytes bind the complete plan. A phase started without a complete
receipt is uncertain and cannot be replayed. Runtime dependencies are created
only after authority, source pins, predecessor and time-window checks.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import uuid
from typing import Any, Callable, NoReturn

from app.r2d2_v2_risk_bundle import build_risk_bundle
from app.r2d2_v2_risk_executor import _Inputs, _bytes, _clock, _json, _open_dir, _publish_new, execute_private_risk
from app.r2d2_v2_risk_normalization import canonical_symbol

SCHEMA = "R2D2_V2_RISK_HOST_PLAN_V1"
PHASES = ("preflight", "acquire", "execute")


# Fixed vocabulary: exception messages outside this set are never published.
FAILURE_CODES = frozenset("""ACQUIRED_MODE_INVALID ACQUIRED_REFERENCE_INVALID ACQUISITION_BUDGET_INVALID ADMISSION_BINDING_MISMATCH ADMISSION_INVALID ADMISSION_INVENTORY_MISMATCH ADMISSION_INVENTORY_MISSING ASSESSMENT_CLOCK_BINDING_INVALID ASSESSMENT_CLOCK_ORDER_INVALID ASSESSMENT_INCOMPLETE BATCH_INVENTORY_MISMATCH BUFFERED_INPUT_BUDGET_EXHAUSTED CLOCK_INVALID CONFLICTING_REFERENCE CUTOFF_IN_FUTURE DATABASE_CLOCK_ORDER_INVALID DATABASE_ISOLATION_NOT_CONFIRMED DATABASE_METADATA_INVALID DATABASE_READ_ONLY_COMPARISON_FAILED DATABASE_READ_ONLY_NOT_CONFIRMED DATABASE_RESTRICTED_ROLE_REQUIRED DATABASE_ROW_BINDING_INVALID DATABASE_ROW_BUDGET_EXHAUSTED DATABASE_ROW_BUDGET_INVALID DATABASE_ROW_INVALID DATABASE_SELECT_ONLY_AUTHORITY_REQUIRED DATABASE_SYMBOL_INVALID DATABASE_TRANSACTION_REQUIRED DECISION_IN_FUTURE DEPENDENCIES_PARTIAL DUPLICATE_JSON_KEY EXECUTION_CLOCK_INVALID EXECUTION_ROOT_BINDING_MISMATCH GO_BINDING_MISMATCH HOST_MANIFEST_BINDING_INVALID HTTP_RECEIPT_BINDING_INVALID HTTP_RECEIPT_NOT_COMPLETE HTTP_REFERENCE_INVALID INPUT_CHANGED_DURING_READ INPUT_DIRECTORY_PERMISSIONS INPUT_FILE_INVALID INPUT_HASH_INVALID INVENTORY_BUDGET_INVALID INVENTORY_DUPLICATE INVENTORY_INVALID LIST_BINDING_MISMATCH MANIFEST_BINDING_INVALID NONZERO_HASH_REQUIRED NON_FINITE_JSON OUTPUT_DIRECTORY_PERMISSIONS OWNER_ORDER_SCOPE_MISMATCH PATH_INVALID PHASE_INVALID PHASE_OUTSIDE_WINDOW PHASE_PENDING PHASE_WINDOW_EXPIRED PREVIOUS_PHASE_BINDING_INVALID PROVIDER_NOT_ALLOWED REFERENCE_INVALID REFERENCE_PATH_INVALID REPLAY_PREDECESSOR_BINDING_MISMATCH RISK_DEDICATED_DATABASE_CONNECTION_REQUIRED RUNNER_BODY_OR_TIME_BUDGET_EXHAUSTED RUNNER_CAPTURE_BUDGET_EXHAUSTED RUNNER_CAPTURE_WINDOW_EXHAUSTED RUNNER_CLOCK_INVALID RUNNER_CUTOFF_IN_FUTURE RUNNER_DATABASE_CLOCK_INVALID RUNNER_DATABASE_COUNTS_INVALID RUNNER_DATABASE_RECEIPT_INVALID RUNNER_IDENTITY_INVALID RUNNER_JSON_TYPE_INVALID RUNNER_PROVIDER_NOT_ALLOWED RUNNER_REQUEST_BUDGET_EXHAUSTED RUNNER_SCOPE_OR_BUDGET_INVALID RUNNER_SPOOL_INTEGRITY RUNNER_SPOOL_PERMISSIONS RUNNER_SYMBOL_LIST_INVALID RUNNER_UTC_REQUIRED RUNTIME_SOURCE_ROOT_MISMATCH SNAPSHOT_CLOCK_OR_SOURCE_INVALID SNAPSHOT_REFERENCE_INVALID SOURCE_CHANGED SOURCE_NOT_REGULAR SOURCE_PATH_INVALID SOURCE_PIN_CLOSURE_INCOMPLETE SOURCE_PIN_MISMATCH SPOOL_PARENT_PERMISSIONS SPOOL_PERMISSIONS SYMBOL_BUDGET_INVALID SYMBOL_LIST_INVALID UTC_REQUIRED""".split())
FAILURE_CODES |= frozenset("""SYMBOL_INVALID PHASE_ALREADY_COMPLETE PHASE_ALREADY_STARTED
PACING_BUDGET_EXHAUSTED REDIRECT_REJECTED REQUEST_REJECTED REQUEST_DATE_IN_FUTURE
FINNHUB_RATE_BUDGET_EXHAUSTED REQUEST_BUDGET_EXHAUSTED CREDENTIAL_UNAVAILABLE
ENCODING_REJECTED BODY_BUDGET_EXHAUSTED RESPONSE_DEADLINE_EXCEEDED RESPONSE_REJECTED
ARGUMENTS_INVALID""".split())
MAX_BUFFERED_INPUT_BYTES = 512 * 1024 * 1024


class HostPhaseInterrupted(KeyboardInterrupt):
    def __init__(self, result: dict[str,Any]):
        self.result = result


class HostPhaseExited(SystemExit):
    def __init__(self, result: dict[str,Any]):
        super().__init__(3 if result["status"] == "UNCERTAIN" else 2)
        self.result = result


class HostPhaseFailure(ValueError):
    def __init__(self, result: dict[str,Any]):
        super().__init__(result["code"])
        self.result=result
        self.exit_code=3 if result["status"]=="UNCERTAIN" else 2


def _failure_code(error: BaseException) -> str:
    if isinstance(error, KeyboardInterrupt):return "INTERRUPTED"
    if isinstance(error, SystemExit):return "PROCESS_EXIT_INTERRUPTED"
    if isinstance(error, FileExistsError):return "PHASE_ALREADY_EXISTS"
    if isinstance(error, OSError):return "FILESYSTEM_FAILURE"
    candidate=error.args[0] if error.args else None
    if isinstance(candidate,str) and candidate in FAILURE_CODES and re.fullmatch(r"[A-Z0-9_]{1,64}",candidate):return candidate
    return "UNCLASSIFIED_FAILURE"


def _utc(value: datetime) -> datetime:
    offset=value.utcoffset()
    if value.tzinfo is None or offset is None or offset.total_seconds()!=0:
        raise ValueError("UTC_REQUIRED")
    return value


def _buffer(files: dict[str,bytes], name: str, raw: bytes) -> None:
    total=sum(len(body) for key,body in files.items() if key!=name)+len(raw)
    if total>MAX_BUFFERED_INPUT_BYTES:raise ValueError("BUFFERED_INPUT_BUDGET_EXHAUSTED")
    files[name]=raw


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: Any) -> str:
    if not isinstance(value,str) or not re.fullmatch(r"[0-9a-f]{64}",value) or value=="0"*64:
        raise ValueError("NONZERO_HASH_REQUIRED")
    return value


def _read_doc(path: Path, sha: str) -> dict[str,Any]:
    source=_Inputs(path.parent)
    try:return _json(source.read({"path":path.name,"sha256":_digest(sha)}))
    finally:os.close(source.fd)


def _write(path: Path, raw: bytes) -> dict[str,str]:
    """Publish a complete, synced inode exclusively; never expose a partial receipt."""
    parent=_open_dir(path.parent)
    temporary=".receipt-"+uuid.uuid4().hex
    created=False
    try:
        if stat.S_IMODE(os.fstat(parent).st_mode)!=0o700:raise ValueError("SPOOL_PERMISSIONS")
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
        created=True
        with os.fdopen(fd,"wb") as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.link(temporary,path.name,src_dir_fd=parent,dst_dir_fd=parent,follow_symlinks=False)
        os.unlink(temporary,dir_fd=parent);created=False
        os.fsync(parent)
    finally:
        if created:os.unlink(temporary,dir_fd=parent)
        os.close(parent)
    return {"path":path.name,"sha256":_sha(raw)}


def _private_dir(path: Path) -> None:
    parent=_open_dir(path.parent)
    try:
        if stat.S_IMODE(os.fstat(parent).st_mode)!=0o700:raise ValueError("SPOOL_PARENT_PERMISSIONS")
        os.mkdir(path.name,0o700,dir_fd=parent)
        os.fsync(parent)
    finally:os.close(parent)


def _source_pins(root: Path, pins: dict[str,Any]) -> None:
    if root.absolute()!=Path(__file__).absolute().parents[1]:raise ValueError("RUNTIME_SOURCE_ROOT_MISMATCH")
    expected={path.relative_to(root).as_posix() for path in (root/"app").rglob("*.py")}
    if pins.get("schema")!="RISK_HOST_SOURCE_PINS_V1" or set(pins.get("files",{}))!=expected:
        raise ValueError("SOURCE_PIN_CLOSURE_INCOMPLETE")
    for relative,digest in pins["files"].items():
        path=PurePosixPath(relative)
        if path.is_absolute() or any(part in {".",".."} for part in path.parts):raise ValueError("SOURCE_PATH_INVALID")
        parent=_open_dir((root/relative).parent)
        try:
            fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent)
            with os.fdopen(fd,"rb") as stream:
                before=os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode):raise ValueError("SOURCE_NOT_REGULAR")
                raw=stream.read()
                after=os.fstat(stream.fileno())
                if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):raise ValueError("SOURCE_CHANGED")
            if _sha(raw)!=_digest(digest):raise ValueError("SOURCE_PIN_MISMATCH")
        finally:os.close(parent)


def _validate(plan: dict[str,Any], *, digest: str, go: dict[str,Any], inputs: _Inputs,
              phase: str, now: datetime, source_root: Path) -> tuple[dict[str,Any],list[dict[str,str]]]:
    _utc(now)
    _utc(_clock(plan["cutoff_at"]))
    for window in plan["phase_windows"].values():
        _utc(_clock(window["not_before"]));_utc(_clock(window["not_after"]))
    day=plan["session_date"];date.fromisoformat(day)
    namespace=plan["namespace"]
    if plan.get("schema")!=SCHEMA or namespace not in {"R2D2-V2-DIAG-R4-"+day,"R2D2-V2-SHADOW-"+day}:
        raise ValueError("HOST_MANIFEST_BINDING_INVALID")
    if phase not in PHASES or set(plan["phase_windows"])!=set(PHASES):raise ValueError("PHASE_INVALID")
    bounds=plan["phase_windows"][phase]
    if not _clock(bounds["not_before"])<=now<=_clock(bounds["not_after"]):raise ValueError("PHASE_OUTSIDE_WINDOW")
    cutoff=_clock(plan["cutoff_at"])
    if phase!="preflight" and cutoff>now:raise ValueError("CUTOFF_IN_FUTURE")
    pins=_json(inputs.read(plan["source_pins"]));_source_pins(source_root,pins)
    order=_json(inputs.read(plan["owner_order"]))
    scope={"namespace":namespace,"session_date":day,"cutoff_at":plan["cutoff_at"],"phases":list(PHASES)}
    if (order.get("schema")!="R2D2_V2_RISK_HOST_ORDER_V1" or order.get("scope")!=scope
            or order.get("actions")!=["READ_PROVIDERS","READ_DATABASE","WRITE_PRIVATE_RISK_ARTIFACTS"]):
        raise ValueError("OWNER_ORDER_SCOPE_MISMATCH")
    binding={"manifest_sha256":digest,"owner_order_sha256":plan["owner_order"]["sha256"],
             "source_pins_sha256":plan["source_pins"]["sha256"],"list_sha256":plan["list"]["sha256"],
             "admission_sha256":plan["admission"]["sha256"],**scope,"phase_windows":plan["phase_windows"]}
    if (go.get("schema")!="R2D2_V2_RISK_HOST_GO_V1" or go.get("verdict")!="GO"
            or go.get("scope")!="RISK_ARTIFACT_ONLY" or go.get("binding")!=binding):
        raise ValueError("GO_BINDING_MISMATCH")
    inventory=_json(inputs.read(plan["list"]))
    if inventory.get("namespace")!=namespace or inventory.get("session_date")!=day:raise ValueError("LIST_BINDING_MISMATCH")
    entries=inventory.get("symbols")
    if not isinstance(entries,list) or not 1<=len(entries)<=550:raise ValueError("INVENTORY_BUDGET_INVALID")
    if any(set(entry)!={"symbol","market"} or canonical_symbol(entry["symbol"])!=entry["symbol"] or entry["market"] not in {"US","B3"} for entry in entries):
        raise ValueError("INVENTORY_INVALID")
    if len({entry["symbol"] for entry in entries})!=len(entries):raise ValueError("INVENTORY_DUPLICATE")
    admission=_json(inputs.read(plan["admission"]))
    if not isinstance(admission,dict):raise ValueError("ADMISSION_INVALID")
    if namespace.startswith("R2D2-V2-SHADOW-") and admission.get("schema")!="CODEX_CERTIFIED_PHASE_RECEIPT_V1":
        raise ValueError("ADMISSION_BINDING_MISMATCH")
    admitted=admission.get("symbols")
    if admission.get("schema")=="CODEX_CERTIFIED_PHASE_RECEIPT_V1":
        # The successor pins the causal list by bytes, not a top-level names array.
        # Consume its original receipt: never manufacture a replacement admission.
        native=admission.get("native_result")
        causal=native.get("causal_readback") if isinstance(native,dict) else None
        names=[entry["symbol"] for entry in entries]
        counts=admission.get("counts")
        if (admission.get("phase")!="admission" or admission.get("status")!="PASSED"
                or admission.get("namespace")!=namespace or admission.get("session")!=day
                or not isinstance(causal,dict) or causal.get("epoch")!=namespace
                or causal.get("session")!=day or causal.get("status")!="AVAILABLE"
                or causal.get("diagnostics")!=[]
                or type(causal.get("selected_count")) is not int or causal["selected_count"]!=len(names)
                or causal.get("symbols_file_sha256")!=_sha(("\n".join(names)+"\n").encode("ascii"))
                or not isinstance(counts,dict) or type(counts.get("symbols")) is not int
                or counts["symbols"]!=len(names)):
            raise ValueError("ADMISSION_BINDING_MISMATCH")
        admitted_names=set(names)
    elif isinstance(admitted,dict):admitted_names=set(admitted)
    elif isinstance(admitted,list) and all(isinstance(item,str) for item in admitted):admitted_names=set(admitted)
    else:raise ValueError("ADMISSION_INVENTORY_MISSING")
    if admitted_names!={entry["symbol"] for entry in entries}:raise ValueError("ADMISSION_INVENTORY_MISMATCH")
    for key in ("namespace","session_date"):
        if key in admission and admission[key]!=plan[key]:raise ValueError("ADMISSION_BINDING_MISMATCH")
    replay=_json(inputs.read(plan["replay_manifest"]))
    if (replay.get("schema")!="V2_RISK_REPLAY_MANIFEST_V1" or replay.get("namespace")!=namespace
            or replay.get("session_date")!=day or replay.get("phase_pending")!=0
            or replay.get("admission")!=plan["admission"]
            or [{"symbol":entry["symbol"],"market":entry["market"]} for entry in replay["symbols"]]!=entries):
        raise ValueError("REPLAY_PREDECESSOR_BINDING_MISMATCH")
    limits=plan["limits"]
    if (type(limits.get("max_symbols")) is not int or not len(entries)<=limits["max_symbols"]<=550
            or type(limits.get("max_total_requests")) is not int or not 1<=limits["max_total_requests"]<=10000
            or type(limits.get("max_body_bytes")) is not int or not 1<=limits["max_body_bytes"]<=16*1024*1024
            or type(limits.get("max_total_bytes")) is not int or not 1<=limits["max_total_bytes"]<=1024*1024*1024
            or type(limits.get("max_elapsed_seconds")) is not int or not 1<=limits["max_elapsed_seconds"]<=86400):
        raise ValueError("ACQUISITION_BUDGET_INVALID")
    # Read and validate every existing source before any provider call.
    for entry in replay["symbols"]:
        if entry["market"]=="B3":continue
        for key in ("fundamentals","grades","institutional"):inputs.receipt(entry["sources"][key],now,allow_incomplete=True)
        inputs.snapshot(entry["sources"]["official"],now)
        if entry.get("fx"):inputs.snapshot(entry["fx"]["receipt"],now)
    return replay,entries


def _clone(value: Any, source: _Inputs, files: dict[str,bytes]) -> Any:
    if isinstance(value,dict):
        if set(value)=={"path","sha256"}:
            raw=source.read(value);name="blob-"+_sha(raw)+".json";_buffer(files,name,raw)
            return {"path":name,"sha256":_sha(raw)}
        return {key:_clone(item,source,files) for key,item in value.items()}
    if isinstance(value,list):return [_clone(item,source,files) for item in value]
    return value


def _prepare_acquired(replay: dict[str,Any], source: _Inputs, batch: dict[str,Any], batch_root: Path,
                      output: Path) -> dict[str,str]:
    files:dict[str,bytes]={}
    doc=deepcopy(replay)
    doc["mode"]="ACQUIRED_PENDING_ASSESSMENT"
    doc.pop("decision_at",None)
    fetched={entry["symbol"]:entry for entry in batch["entries"]}
    if set(fetched)!={entry["symbol"] for entry in doc["symbols"] if entry["market"]=="US"}:raise ValueError("BATCH_INVENTORY_MISMATCH")
    runner_inputs=_Inputs(batch_root)
    try:
        doc["admission"]=_clone(doc["admission"],source,files)
        for entry in doc["symbols"]:
            entry.pop("assessment_clock",None)
            if entry["market"]=="B3":entry.pop("sources",None);continue
            entry["sources"].pop("insider",None)
            entry["sources"]=_clone(entry["sources"],source,files)
            if entry.get("fx"):entry["fx"]=_clone(entry["fx"],source,files)
            acquired=fetched[entry["symbol"]]
            body=runner_inputs.read(acquired["direct_snapshot"])
            name="insider-"+_sha(body)+".json";_buffer(files,name,body)
            entry["sources"]["insider"]={"body":{"path":name,"sha256":_sha(body)},"received_at":acquired["received_at"],"source_id":"DIRECT_INSIDER_RC4BIS_HOST"}
        _buffer(files,"acquired.json",_bytes(doc))
        _publish_new(output,files)
        return {"path":"acquired.json","sha256":_sha(files["acquired.json"])}
    finally:os.close(runner_inputs.fd)


def _arguments(entry: dict[str,Any], source: _Inputs, at: datetime) -> dict[str,Any]:
    arguments={"symbol":entry["symbol"],"market":entry["market"],"computed_at":at,"available_at":at,"decision_at":at}
    if entry["market"]=="B3":return arguments
    sources=entry["sources"]
    arguments.update({key:source.receipt(sources[key],at,allow_incomplete=True) for key in ("fundamentals","grades","institutional")})
    arguments.update(insider_snapshot=source.snapshot(sources["insider"],at),official_snapshot=source.snapshot(sources["official"],at))
    if entry.get("fx"):
        arguments.update(fx_rate=entry["fx"]["rate"],quote_price=entry["fx"]["quote_price"],fx_receipt=source.snapshot(entry["fx"]["receipt"],at))
    return arguments


def _assess_manifest(acquired: Path, acquired_sha: str, output: Path,
                     clock: Callable[[],datetime]) -> dict[str,str]:
    source=_Inputs(acquired.parent)
    try:
        doc=_json(source.read({"path":acquired.name,"sha256":acquired_sha}))
        if doc.get("mode")!="ACQUIRED_PENDING_ASSESSMENT":raise ValueError("ACQUIRED_MODE_INVALID")
        files:dict[str,bytes]={}
        doc=_clone(doc,source,files)
        _publish_new(output,files)
        copied=_Inputs(output)
        try:
            for index,entry in enumerate(doc["symbols"]):
                assessed=build_risk_bundle(**_arguments(entry,copied,clock()))
                completed=clock()
                _write(output/f"assessment-result-{index}.json",_bytes({"symbol":entry["symbol"],"computed_at":completed.isoformat(),
                    "score":assessed["risk"]["value"] if assessed["risk"] else None,"status":assessed["status"],"calculation":assessed["calculation"]}))
                available=clock()  # Recorded only after actual score receipt is durable.
                entry["assessment_clock"]=_write(output/f"assessment-clock-{index}.json",_bytes({"symbol":entry["symbol"],
                    "factual_assessment":True,"computed_at":completed.isoformat(),"available_at":available.isoformat()}))
            doc["decision_at"]=clock().isoformat();doc["mode"]="OFFLINE_REPLAY"
            return _write(output/"manifest.json",_bytes(doc))
        finally:os.close(copied.fd)
    finally:os.close(source.fd)


def _run_host_phase(*, phase: str, manifest_path: Path, manifest_sha256: str, go_path: Path,
                   go_sha256: str, source_root: Path, spool_root: Path,
                   previous_receipt_sha256: str | None = None,
                   clock: Callable[[],datetime] = lambda:datetime.now(timezone.utc),
                   transport: Any = None, database_reader: Any = None,
                   _failure_state: dict[str,Any]) -> dict[str,Any]:
    now=clock()
    _utc(now)
    _failure_state["safe_clock"]=now.isoformat()
    digest=_digest(manifest_sha256);go_digest=_digest(go_sha256)
    inputs=_Inputs(manifest_path.parent)
    try:
        plan=_json(inputs.read({"path":manifest_path.name,"sha256":digest}))
        go=_read_doc(go_path,go_digest)
        if plan.get("runtime_source_root")!=str(source_root.absolute()) or plan.get("spool_root")!=str(spool_root.absolute()):
            raise ValueError("EXECUTION_ROOT_BINDING_MISMATCH")
        replay,entries=_validate(plan,digest=digest,go=go,inputs=inputs,phase=phase,now=now,source_root=source_root)
        destination=spool_root/digest
        # Inspect prior evidence before attempting a new marker, including preflight.
        if os.path.lexists(destination/(phase+".RECEIPT.json")):
            raise ValueError("PHASE_ALREADY_COMPLETE")
        if os.path.lexists(destination/(phase+".STARTED.json")) or os.path.lexists(destination/(phase+".FAILED.json")):
            raise ValueError("PHASE_ALREADY_STARTED")
        if phase=="preflight":_private_dir(destination)
        directory=_Inputs(destination);os.close(directory.fd)
        previous=None
        if phase!="preflight":
            prior=PHASES[PHASES.index(phase)-1]
            previous=_read_doc(destination/(prior+".RECEIPT.json"),_digest(previous_receipt_sha256))
            if (previous.get("phase")!=prior or previous.get("status")!="COMPLETE" or previous.get("manifest_sha256")!=digest
                    or previous.get("go_sha256")!=go_digest or _clock(previous["completed_at"])>now):
                raise ValueError("PREVIOUS_PHASE_BINDING_INVALID")
        _failure_state.update(destination=destination,phase=phase,manifest_sha256=digest,go_sha256=go_digest,
            previous_receipt_sha256=previous_receipt_sha256,marker_write_attempted=True)
        started_ref=_write(destination/(phase+".STARTED.json"),_bytes({"phase":phase,"manifest_sha256":digest,"go_sha256":go_digest,"started_at":now.isoformat()}))
        _failure_state["started"]=True
        _failure_state["started_marker_sha256"]=started_ref["sha256"]
        outputs:dict[str,Any]={}
        last_clock=now
        def guarded_clock()->datetime:
            nonlocal last_clock
            value=_utc(clock())
            if (not last_clock<=value or (value-now).total_seconds()>plan["limits"]["max_elapsed_seconds"]
                    or not _clock(plan["phase_windows"][phase]["not_before"])<=value<=_clock(plan["phase_windows"][phase]["not_after"])):
                raise ValueError("PHASE_WINDOW_EXPIRED")
            last_clock=value
            _failure_state["safe_clock"]=value.isoformat()
            return value
        if phase=="acquire":
            from app.r2d2_v2_risk_runner import capture_direct_insider_batch, runtime_dependencies
            batch_entries=[]
            for entry in replay["symbols"]:
                if entry["market"]=="B3":continue
                identity=inputs.receipt(entry["sources"]["fundamentals"],now,allow_incomplete=True)
                batch_entries.append({"symbol":entry["symbol"],"market":entry["market"],"identity":identity if identity.diagnostic is None else None})
            if batch_entries:
                if transport is None or database_reader is None:
                    if transport is not None or database_reader is not None:raise ValueError("DEPENDENCIES_PARTIAL")
                    transport,database_reader=runtime_dependencies(max_total_requests=plan["limits"]["max_total_requests"],
                        max_body_bytes=plan["limits"]["max_body_bytes"],clock=guarded_clock)
                batch=capture_direct_insider_batch(batch_entries,output_path=destination/"capture",namespace=plan["namespace"],
                    session_date=date.fromisoformat(plan["session_date"]),clock=guarded_clock,transport=transport,database_reader=database_reader,
                    fallback_on_failure=True,max_symbols=plan["limits"]["max_symbols"],max_total_requests=plan["limits"]["max_total_requests"],
                    max_total_bytes=plan["limits"]["max_total_bytes"],query_cutoff_at=_clock(plan["cutoff_at"]),
                        max_duration_seconds=min(3600,plan["limits"]["max_elapsed_seconds"]))
            else:
                skip=_bytes({"schema":"RISK_HOST_B3_SKIP_V1","symbols":len(entries),"http_attempts":0})
                _publish_new(destination/"capture",{"MANIFEST.json":skip})
                batch={"entries":[],"manifest_sha256":_sha(skip),"counts":{"symbols":len(entries),"b3_skipped":len(entries),"http_attempts":0}}
            acquired=_prepare_acquired(replay,inputs,batch,destination/"capture",destination/"acquired")
            outputs={"batch_manifest_sha256":batch["manifest_sha256"],"acquired_manifest":acquired,"counts":batch["counts"]}
        elif phase=="execute":
            assert previous is not None
            acquired=previous["outputs"]["acquired_manifest"]
            if acquired.get("path")!="acquired.json":raise ValueError("ACQUIRED_REFERENCE_INVALID")
            manifest=_assess_manifest(destination/"acquired"/"acquired.json",acquired["sha256"],destination/"assessment",guarded_clock)
            result=execute_private_risk(manifest_path=destination/"assessment"/manifest["path"],manifest_sha256=manifest["sha256"],
                expected_namespace=plan["namespace"],expected_session_date=date.fromisoformat(plan["session_date"]),
                output_path=destination/"risk-output",execution_at=guarded_clock())
            outputs={"assessment_manifest":manifest,**result}
        finished=guarded_clock()
        receipt={"schema":"R2D2_V2_RISK_HOST_PHASE_RECEIPT_V1","phase":phase,"status":"COMPLETE","manifest_sha256":digest,
                 "go_sha256":go_digest,"namespace":plan["namespace"],"session_date":plan["session_date"],"started_at":now.isoformat(),
                 "completed_at":finished.isoformat(),"previous_receipt_sha256":previous_receipt_sha256,"outputs":outputs,
                 "operation_activation":False,"certification_granted":False}
        ref=_write(destination/(phase+".RECEIPT.json"),_bytes(receipt))
        return {"phase":phase,"status":"COMPLETE","receipt_sha256":ref["sha256"],"manifest_sha256":digest,"outputs":outputs}
    finally:os.close(inputs.fd)


def run_host_phase(*, phase: str, manifest_path: Path, manifest_sha256: str, go_path: Path,
                   go_sha256: str, source_root: Path, spool_root: Path,
                   previous_receipt_sha256: str | None = None,
                   clock: Callable[[],datetime] = lambda:datetime.now(timezone.utc),
                   transport: Any = None, database_reader: Any = None) -> dict[str,Any]:
    state:dict[str,Any]={}
    try:
        return _run_host_phase(phase=phase,manifest_path=manifest_path,manifest_sha256=manifest_sha256,
            go_path=go_path,go_sha256=go_sha256,source_root=source_root,spool_root=spool_root,
            previous_receipt_sha256=previous_receipt_sha256,clock=clock,transport=transport,
            database_reader=database_reader,_failure_state=state)
    except (Exception,KeyboardInterrupt,SystemExit) as error:
        uncertain=bool(state.get("marker_write_attempted")) or _failure_code(error)=="PHASE_ALREADY_STARTED"
        result:dict[str,Any]={"phase":phase if phase in PHASES else "INVALID_PHASE",
            "status":"UNCERTAIN" if uncertain else "REFUSED", "code":_failure_code(error),
            "failed_receipt_written":False,"marker_write_attempted":bool(state.get("marker_write_attempted")),
            "started_marker_confirmed":bool(state.get("started"))}
        # Destination is set only after plan/GO/pins/window and predecessor validation.
        # Never invent a destination or write evidence on authority-validation failure.
        if "destination" in state and not (isinstance(error,FileExistsError) and not state.get("started")):
            failed={"schema":"R2D2_V2_RISK_HOST_FAILED_V1",**result,
                "manifest_sha256":state["manifest_sha256"],"go_sha256":state["go_sha256"],
                "previous_receipt_sha256":state.get("previous_receipt_sha256"),
                "started_marker_sha256":state.get("started_marker_sha256"),
                "last_validated_clock_at":state.get("safe_clock"),
                "clock_semantics":"LAST_VALIDATED_OBSERVATION_NOT_FAILURE_TIME"}
            failed.pop("failed_receipt_written",None)
            try:
                ref=_write(state["destination"]/(phase+".FAILED.json"),_bytes(failed))
                result["failed_receipt_written"]=True
                result["failed_receipt_sha256"]=ref["sha256"]
            except (Exception,KeyboardInterrupt,SystemExit):
                result["failed_receipt_write_code"]="FAILED_RECEIPT_NOT_WRITTEN"
        if isinstance(error,KeyboardInterrupt):raise HostPhaseInterrupted(result) from None
        if isinstance(error,SystemExit):raise HostPhaseExited(result) from None
        raise HostPhaseFailure(result) from None


def main() -> int:
    class SafeParser(argparse.ArgumentParser):
        def error(self, message: str) -> NoReturn:
            raise ValueError("ARGUMENTS_INVALID")
    parser=SafeParser(description="Pinned risk artifact phases; no trading activation")
    parser.add_argument("phase",choices=PHASES)
    for name in ("manifest","manifest-sha256","go","go-sha256","source-root","spool-root"):parser.add_argument("--"+name,required=True)
    parser.add_argument("--previous-receipt-sha256")
    try:args=parser.parse_args()
    except ValueError:
        print(json.dumps({"status":"REFUSED","code":"ARGUMENTS_INVALID","failed_receipt_written":False}))
        return 2
    try:
        result=run_host_phase(phase=args.phase,manifest_path=Path(args.manifest),manifest_sha256=args.manifest_sha256,
            go_path=Path(args.go),go_sha256=args.go_sha256,source_root=Path(args.source_root),spool_root=Path(args.spool_root),
            previous_receipt_sha256=args.previous_receipt_sha256)
    except (HostPhaseInterrupted,HostPhaseExited) as failure:
        print(json.dumps(failure.result,sort_keys=True))
        return 3 if failure.result["status"]=="UNCERTAIN" else 2
    except HostPhaseFailure as failure:
        print(json.dumps(failure.result,sort_keys=True))
        return failure.exit_code
    except (Exception,KeyboardInterrupt,SystemExit) as error:
        print(json.dumps({"status":"REFUSED","phase":args.phase,"code":_failure_code(error),"failed_receipt_written":False}))
        return 2
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":raise SystemExit(main())
