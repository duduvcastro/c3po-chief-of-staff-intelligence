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
from typing import Any, Callable

from app.r2d2_v2_risk_bundle import build_risk_bundle
from app.r2d2_v2_risk_executor import _Inputs, _bytes, _clock, _json, _open_dir, _publish_new, execute_private_risk
from app.r2d2_v2_risk_normalization import canonical_symbol

SCHEMA = "R2D2_V2_RISK_HOST_PLAN_V1"
PHASES = ("preflight", "acquire", "execute")


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
    parent=_open_dir(path.parent)
    try:
        if stat.S_IMODE(os.fstat(parent).st_mode)!=0o700:raise ValueError("SPOOL_PERMISSIONS")
        fd=os.open(path.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
        with os.fdopen(fd,"wb") as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.fsync(parent)
    finally:os.close(parent)
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
    admitted=admission.get("symbols")
    if isinstance(admitted,dict):admitted_names=set(admitted)
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
        for key in ("fundamentals","grades","institutional"):inputs.receipt(entry["sources"][key],now)
        inputs.snapshot(entry["sources"]["official"],now)
        if entry.get("fx"):inputs.snapshot(entry["fx"]["receipt"],now)
    return replay,entries


def _clone(value: Any, source: _Inputs, files: dict[str,bytes]) -> Any:
    if isinstance(value,dict):
        if set(value)=={"path","sha256"}:
            raw=source.read(value);name="blob-"+_sha(raw)+".json";files[name]=raw
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
            name="insider-"+_sha(body)+".json";files[name]=body
            entry["sources"]["insider"]={"body":{"path":name,"sha256":_sha(body)},"received_at":acquired["received_at"],"source_id":"DIRECT_INSIDER_RC4BIS_HOST"}
        files["acquired.json"]=_bytes(doc)
        _publish_new(output,files)
        return {"path":"acquired.json","sha256":_sha(files["acquired.json"])}
    finally:os.close(runner_inputs.fd)


def _arguments(entry: dict[str,Any], source: _Inputs, at: datetime) -> dict[str,Any]:
    arguments={"symbol":entry["symbol"],"market":entry["market"],"computed_at":at,"available_at":at,"decision_at":at}
    if entry["market"]=="B3":return arguments
    sources=entry["sources"]
    arguments.update({key:source.receipt(sources[key],at) for key in ("fundamentals","grades","institutional")})
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


def run_host_phase(*, phase: str, manifest_path: Path, manifest_sha256: str, go_path: Path,
                   go_sha256: str, source_root: Path, spool_root: Path,
                   previous_receipt_sha256: str | None = None,
                   clock: Callable[[],datetime] = lambda:datetime.now(timezone.utc),
                   transport: Any = None, database_reader: Any = None) -> dict[str,Any]:
    now=clock()
    if now.tzinfo is None:raise ValueError("CLOCK_INVALID")
    digest=_digest(manifest_sha256);go_digest=_digest(go_sha256)
    inputs=_Inputs(manifest_path.parent)
    try:
        plan=_json(inputs.read({"path":manifest_path.name,"sha256":digest}))
        go=_read_doc(go_path,go_digest)
        if plan.get("runtime_source_root")!=str(source_root.absolute()) or plan.get("spool_root")!=str(spool_root.absolute()):
            raise ValueError("EXECUTION_ROOT_BINDING_MISMATCH")
        replay,entries=_validate(plan,digest=digest,go=go,inputs=inputs,phase=phase,now=now,source_root=source_root)
        destination=spool_root/digest
        if phase=="preflight":_private_dir(destination)
        directory=_Inputs(destination);os.close(directory.fd)
        previous=None
        if phase!="preflight":
            prior=PHASES[PHASES.index(phase)-1]
            previous=_read_doc(destination/(prior+".RECEIPT.json"),_digest(previous_receipt_sha256))
            if (previous.get("phase")!=prior or previous.get("status")!="COMPLETE" or previous.get("manifest_sha256")!=digest
                    or previous.get("go_sha256")!=go_digest or _clock(previous["completed_at"])>now):
                raise ValueError("PREVIOUS_PHASE_BINDING_INVALID")
        _write(destination/(phase+".STARTED.json"),_bytes({"phase":phase,"manifest_sha256":digest,"go_sha256":go_digest,"started_at":now.isoformat()}))
        outputs:dict[str,Any]={}
        last_clock=now
        def guarded_clock()->datetime:
            nonlocal last_clock
            value=clock()
            if (not last_clock<=value or (value-now).total_seconds()>plan["limits"]["max_elapsed_seconds"]
                    or not _clock(plan["phase_windows"][phase]["not_before"])<=value<=_clock(plan["phase_windows"][phase]["not_after"])):
                raise ValueError("PHASE_WINDOW_EXPIRED")
            last_clock=value
            return value
        if phase=="acquire":
            from app.r2d2_v2_risk_runner import capture_direct_insider_batch, runtime_dependencies
            batch_entries=[]
            for entry in replay["symbols"]:
                if entry["market"]=="B3":continue
                identity=inputs.receipt(entry["sources"]["fundamentals"],now)
                batch_entries.append({"symbol":entry["symbol"],"market":entry["market"],"identity":identity})
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


def main() -> int:
    parser=argparse.ArgumentParser(description="Pinned risk artifact phases; no trading activation")
    parser.add_argument("phase",choices=PHASES)
    for name in ("manifest","manifest-sha256","go","go-sha256","source-root","spool-root"):parser.add_argument("--"+name,required=True)
    parser.add_argument("--previous-receipt-sha256")
    args=parser.parse_args()
    try:
        result=run_host_phase(phase=args.phase,manifest_path=Path(args.manifest),manifest_sha256=args.manifest_sha256,
            go_path=Path(args.go),go_sha256=args.go_sha256,source_root=Path(args.source_root),spool_root=Path(args.spool_root),
            previous_receipt_sha256=args.previous_receipt_sha256)
    except Exception:
        print(json.dumps({"status":"REFUSED_OR_UNCERTAIN","phase":args.phase,"detail":"Inspect private phase marker; do not replay"}))
        return 1
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":raise SystemExit(main())
