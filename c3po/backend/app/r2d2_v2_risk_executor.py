"""Offline replay of hash-pinned risk inputs; no network, DB or activation.

Manifest clocks are factual input claims, never backdated from this invocation.
Execution attestation records its own clock and does not certify those claims.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import uuid
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from app.r2d2_v2_risk_acquisition import SourceReceipt, SourceRequest
from app.r2d2_v2_risk_bundle import PrivateSnapshot, build_risk_bundle
from app.r2d2_v2_risk_normalization import canonical_symbol
from app.r2d2_v2_risk_transport import BoundedRiskTransport

SCHEMA = "V2_RISK_REPLAY_MANIFEST_V1"
MAX_BYTES = 16 * 1024 * 1024


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _json(body: bytes) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    def invalid(_: str) -> Any:
        raise ValueError("NON_FINITE_JSON")
    return json.loads(body, object_pairs_hook=unique, parse_constant=invalid)


def _bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode()


def _clock(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("CLOCK_INVALID")
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("CLOCK_INVALID")
    return result


def _open_dir(path: Path) -> int:
    absolute = path.absolute()
    fd = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in absolute.parts[1:]:
            if part in {".", ".."}:
                raise ValueError("PATH_INVALID")
            following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = following
        return fd
    except BaseException:
        os.close(fd)
        raise


class _Inputs:
    def __init__(self, directory: Path) -> None:
        self.fd = _open_dir(directory)
        if stat.S_IMODE(os.fstat(self.fd).st_mode) != 0o700:
            os.close(self.fd)
            raise ValueError("INPUT_DIRECTORY_PERMISSIONS")
        self.hashes: dict[str, str] = {}

    def read(self, reference: dict[str, Any]) -> bytes:
        if not isinstance(reference, dict) or set(reference) != {"path", "sha256"}:
            raise ValueError("REFERENCE_INVALID")
        path, expected = reference["path"], reference["sha256"]
        if (not isinstance(path, str) or not path or not isinstance(expected, str)
                or not re.fullmatch(r"[0-9a-f]{64}", expected)):
            raise ValueError("REFERENCE_INVALID")
        parts = PurePosixPath(path).parts
        if PurePosixPath(path).is_absolute() or any(part in {".", ".."} for part in parts):
            raise ValueError("REFERENCE_PATH_INVALID")
        parent = os.dup(self.fd)
        try:
            for part in parts[:-1]:
                following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                os.close(parent)
                parent = following
                if stat.S_IMODE(os.fstat(parent).st_mode) != 0o700:
                    raise ValueError("INPUT_DIRECTORY_PERMISSIONS")
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
            with os.fdopen(fd, "rb") as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode) or stat.S_IMODE(before.st_mode) != 0o600 or before.st_size > MAX_BYTES:
                    raise ValueError("INPUT_FILE_INVALID")
                body = stream.read(MAX_BYTES + 1)
                after = os.fstat(stream.fileno())
                named = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
                def identity(value: os.stat_result) -> tuple[int, ...]:
                    return (value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
                if identity(before) != identity(after) or identity(after) != identity(named):
                    raise ValueError("INPUT_CHANGED_DURING_READ")
                if len(body) > MAX_BYTES or _sha(body) != expected:
                    raise ValueError("INPUT_HASH_INVALID")
            if path in self.hashes and self.hashes[path] != expected:
                raise ValueError("CONFLICTING_REFERENCE")
            self.hashes[path] = expected
            return body
        finally:
            os.close(parent)

    def snapshot(self, spec: dict[str, Any], computed: datetime) -> PrivateSnapshot:
        if set(spec) != {"body", "received_at", "source_id"}:
            raise ValueError("SNAPSHOT_REFERENCE_INVALID")
        received = _clock(spec["received_at"])
        source = spec["source_id"]
        if received > computed or not isinstance(source, str) or not source.strip():
            raise ValueError("SNAPSHOT_CLOCK_OR_SOURCE_INVALID")
        body = self.read(spec["body"])
        _json(body)
        return PrivateSnapshot(body, received, source)

    def receipt(self, spec: dict[str, Any], computed: datetime, *, allow_incomplete: bool = False) -> SourceReceipt:
        if set(spec) != {"receipt", "body"}:
            raise ValueError("HTTP_REFERENCE_INVALID")
        doc = _json(self.read(spec["receipt"]))
        body = self.read(spec["body"])
        request = SourceRequest(doc["request"]["provider"], doc["request"]["path"], doc["request"]["parameters"])
        BoundedRiskTransport.validate(request)
        started, received = _clock(doc["started_at"]), _clock(doc["received_at"])
        if not started <= received <= computed or doc["payload_sha256"] != _sha(body):
            raise ValueError("HTTP_RECEIPT_BINDING_INVALID")
        incomplete = doc.get("diagnostic") is not None or type(doc["status"]) is not int or doc["status"] != 200
        if not incomplete:
            try:
                _json(body)
            except (ValueError, UnicodeDecodeError):
                if not allow_incomplete:
                    raise
                incomplete = True
        if incomplete and not allow_incomplete:
            raise ValueError("HTTP_RECEIPT_NOT_COMPLETE")
        return SourceReceipt(request, started, received, doc["status"], body, _sha(body),
                             "SOURCE_INCOMPLETE" if incomplete else None)


def _publish_new(path: Path, files: dict[str, bytes]) -> None:
    parent = _open_dir(path.parent)
    directory = -1
    try:
        os.mkdir(path.name, 0o700, dir_fd=parent)
        directory = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        if stat.S_IMODE(os.fstat(directory).st_mode) != 0o700:
            raise ValueError("OUTPUT_DIRECTORY_PERMISSIONS")
        for name, body in files.items():
            temporary = ".partial-" + uuid.uuid4().hex
            linked = False
            try:
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
                with os.fdopen(fd, "wb") as handle:
                    handle.write(body)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
                linked = True
                os.unlink(temporary, dir_fd=directory)
                os.fsync(directory)
            except BaseException:
                if linked:
                    os.unlink(name, dir_fd=directory)
                raise
        os.fsync(parent)
    except BaseException:
        if directory >= 0:
            try:
                os.unlink("MANIFEST.json", dir_fd=directory)
            except FileNotFoundError:
                pass
        raise
    finally:
        if directory >= 0:
            os.close(directory)
        os.close(parent)


def execute_private_risk(*, manifest_path: Path, manifest_sha256: str,
                         expected_namespace: str, expected_session_date: date,
                         output_path: Path, execution_at: datetime) -> dict[str, Any]:
    """Replay private evidence into an unconnected, immutable local artifact.

    Calling this function authorizes no production phase. Existing assessment
    clocks must come from a pinned factual receipt, not this execution's clock.
    Returned aggregate contains no instrument names or credentials.
    """
    if execution_at.tzinfo is None or execution_at.utcoffset() is None:
        raise ValueError("EXECUTION_CLOCK_INVALID")
    inputs = _Inputs(manifest_path.parent)
    try:
        doc = _json(inputs.read({"path": manifest_path.name, "sha256": manifest_sha256}))
        day = expected_session_date.isoformat()
        if (doc.get("schema") != SCHEMA or doc.get("namespace") != expected_namespace
                or doc.get("session_date") != day
                or expected_namespace not in {"R2D2-V2-DIAG-R4-" + day, "R2D2-V2-SHADOW-" + day}
                or doc.get("mode") != "OFFLINE_REPLAY"):
            raise ValueError("MANIFEST_BINDING_INVALID")
        if type(doc.get("phase_pending")) is not int or doc["phase_pending"] != 0:
            raise ValueError("PHASE_PENDING")
        decision = _clock(doc["decision_at"])
        if decision > execution_at:
            raise ValueError("DECISION_IN_FUTURE")
        # This is predecessor-byte linkage, not a certification or signed GO.
        admission = inputs.read(doc["admission"])
        _json(admission)
        entries = doc.get("symbols")
        if not isinstance(entries, list) or not 1 <= len(entries) <= 550:
            raise ValueError("SYMBOL_BUDGET_INVALID")
        names = [canonical_symbol(entry["symbol"]) for entry in entries]
        if len(set(names)) != len(names) or any(entry["symbol"] != name for entry, name in zip(entries, names)):
            raise ValueError("SYMBOL_LIST_INVALID")
        output_symbols: dict[str, Any] = {}
        assessments: dict[str, Any] = {}
        counts = {"READY": 0, "COMPLETED_NULL": 0}
        for entry, symbol in zip(entries, names):
            clocks = _json(inputs.read(entry["assessment_clock"]))
            if clocks.get("symbol") != symbol or clocks.get("factual_assessment") is not True:
                raise ValueError("ASSESSMENT_CLOCK_BINDING_INVALID")
            computed, available = _clock(clocks["computed_at"]), _clock(clocks["available_at"])
            if not computed <= available <= decision <= execution_at:
                raise ValueError("ASSESSMENT_CLOCK_ORDER_INVALID")
            if entry["market"] == "B3":
                result = build_risk_bundle(symbol=symbol, market="B3", computed_at=computed,
                                           available_at=available, decision_at=decision)
            else:
                sources = entry["sources"]
                fx = entry.get("fx")
                result = build_risk_bundle(
                    symbol=symbol, market=entry["market"],
                    fundamentals=inputs.receipt(sources["fundamentals"], computed, allow_incomplete=True),
                    grades=inputs.receipt(sources["grades"], computed, allow_incomplete=True),
                    institutional=inputs.receipt(sources["institutional"], computed, allow_incomplete=True),
                    insider_snapshot=inputs.snapshot(sources["insider"], computed),
                    official_snapshot=inputs.snapshot(sources["official"], computed),
                    computed_at=computed, available_at=available, decision_at=decision,
                    fx_rate=fx.get("rate") if fx else None,
                    quote_price=fx.get("quote_price") if fx else None,
                    fx_receipt=inputs.snapshot(fx["receipt"], computed) if fx else None)
            if result["status"] not in counts or result["risk"] is None:
                raise ValueError("ASSESSMENT_INCOMPLETE")
            counts[result["status"]] += 1
            output_symbols[symbol] = result["risk"]
            assessments[symbol] = result
        risk = {"schema": "V2_RISK_COMPONENTS_V1", "session_date": day, "symbols": output_symbols}
        files = {"risk.json": _bytes(risk), "assessments.private.json": _bytes(assessments)}
        aggregate = {
            "schema": "V2_RISK_OFFLINE_REPLAY_EXECUTION_V1", "namespace": expected_namespace,
            "session_date": day, "execution_at": execution_at.isoformat(), "counts": counts,
            "symbol_count": len(names), "input_manifest_sha256": manifest_sha256,
            "readiness": "CONTAINS_READY_SYMBOLS" if counts["READY"] else "NO_READY_SYMBOLS",
            "predecessor_chain_independently_verified": False,
            "admission_sha256": _sha(admission), "historical_provenance_independently_verified": False,
            "production_connected": False, "authorization_granted": False,
            "certification_granted": False,
        }
        files["execution.json"] = _bytes(aggregate)
        manifest = {"schema": "V2_RISK_OFFLINE_OUTPUT_MANIFEST_V1", "files": {name: _sha(body) for name, body in files.items()},
                    "input_references": inputs.hashes, "input_manifest_sha256": manifest_sha256}
        # The complete marker is last; files alone never imply successful execution.
        files["MANIFEST.json"] = _bytes(manifest)
        _publish_new(output_path, files)
        return {**aggregate, "output_manifest_sha256": _sha(files["MANIFEST.json"]), "risk_sha256": _sha(files["risk.json"])}
    finally:
        os.close(inputs.fd)
