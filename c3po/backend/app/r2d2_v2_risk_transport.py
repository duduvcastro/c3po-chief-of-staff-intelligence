"""Restricted risk HTTP transport and private append-only evidence spool.

No credentials occur in SourceRequest, receipts, filenames or diagnostics.
This module does not attest source coverage or authorize production execution.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from app.r2d2_v2_risk_acquisition import HttpReply, SourceReceipt, SourceRequest


class RiskTransportError(RuntimeError):
    """Public diagnostic contains a fixed code, never the underlying exception."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> None:
        raise RiskTransportError("REDIRECT_REJECTED")


class BoundedRiskTransport:
    """Sequential, bounded calls with internal credential resolution.

    Rate exhaustion fails closed instead of sleeping across execution windows.
    The executor owns the overall wall-clock deadline. Instances are not shared
    between threads. The injected opener exists for offline tests only.
    """

    BASES = {"eodhd": "https://eodhd.com", "fmp": "https://financialmodelingprep.com"}

    def __init__(self, credential: Callable[[str], str], *, timeout: float = 15,
                 max_body_bytes: int = 16 * 1024 * 1024, max_requests: int = 2200,
                 requests_per_minute: int = 200,
                 monotonic: Callable[[], float] = time.monotonic,
                 opener: Any = None) -> None:
        if (not 0 < timeout <= 30 or type(max_body_bytes) is not int
                or not 1 <= max_body_bytes <= 16 * 1024 * 1024
                or type(max_requests) is not int or not 1 <= max_requests <= 10000
                or type(requests_per_minute) is not int or not 1 <= requests_per_minute <= 300):
            raise ValueError("TRANSPORT_BUDGET_INVALID")
        self.credential = credential
        self.timeout = timeout
        self.max_body_bytes = max_body_bytes
        self.max_requests = max_requests
        self.requests_per_minute = requests_per_minute
        self.monotonic = monotonic
        self.opener = opener if opener is not None else build_opener(ProxyHandler({}), _NoRedirect())
        self._times: list[float] = []
        self._count = 0

    @staticmethod
    def validate(request: SourceRequest) -> None:
        p = request.parameters
        symbol = r"[A-Z][A-Z0-9.-]{0,14}"
        valid = False
        if request.provider == "eodhd":
            if re.fullmatch(r"/api/v1\.1/fundamentals/(?:" + symbol + r"|[A-Z][A-Z0-9-]{0,14}\.US)", request.path):
                valid = not p
            elif re.fullmatch(r"/api/sec-filings/" + symbol + r"/form4", request.path):
                valid = (set(p) == {"page[offset]", "page[limit]"}
                         and type(p["page[offset]"]) is int and 0 <= int(p["page[offset]"]) <= 10000
                         and type(p["page[limit]"]) is int and p["page[limit]"] == 100)
        elif request.provider == "fmp":
            if request.path == "/stable/grades":
                valid = set(p) == {"symbol"}
            elif request.path == "/stable/institutional-ownership/symbol-positions-summary":
                valid = (set(p) == {"symbol", "year", "quarter"}
                         and type(p["year"]) is int and 2000 <= int(p["year"]) <= 2100
                         and type(p["quarter"]) is int and p["quarter"] in (1, 2, 3, 4))
            valid = valid and isinstance(p.get("symbol"), str) and re.fullmatch(symbol, str(p["symbol"])) is not None
        if not valid:
            raise RiskTransportError("REQUEST_REJECTED")

    def __call__(self, request: SourceRequest) -> HttpReply:
        self.validate(request)
        now = self.monotonic()
        self._times = [t for t in self._times if now - t < 60]
        if self._count >= self.max_requests or len(self._times) >= self.requests_per_minute:
            raise RiskTransportError("REQUEST_BUDGET_EXHAUSTED")
        self._count += 1
        self._times.append(now)
        try:
            token = self.credential(request.provider)
            if not isinstance(token, str) or not token or any(c.isspace() for c in token):
                raise RiskTransportError("CREDENTIAL_UNAVAILABLE")
            parameters = dict(request.parameters)
            parameters["api_token" if request.provider == "eodhd" else "apikey"] = token
            url = self.BASES[request.provider] + request.path + "?" + urlencode(parameters)
            http_request = Request(url, headers={"Accept": "application/json", "Accept-Encoding": "identity"})
            with self.opener.open(http_request, timeout=self.timeout) as response:
                if response.geturl() != url:
                    raise RiskTransportError("REDIRECT_REJECTED")
                status = int(response.status)
                if status != 200:
                    # Provider error bodies may repeat the API key.
                    return HttpReply(status, b"")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise RiskTransportError("ENCODING_REJECTED")
                length = response.headers.get("Content-Length")
                if length is not None and (not str(length).isdigit() or int(length) > self.max_body_bytes):
                    raise RiskTransportError("BODY_BUDGET_EXHAUSTED")
                chunks: list[bytes] = []
                size = 0
                while True:
                    if self.monotonic() - now > self.timeout:
                        raise RiskTransportError("RESPONSE_DEADLINE_EXCEEDED")
                    chunk = response.read1(min(65536, self.max_body_bytes + 1 - size))
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > self.max_body_bytes:
                        raise RiskTransportError("BODY_BUDGET_EXHAUSTED")
                    chunks.append(chunk)
                body = b"".join(chunks)
                # Do not persist a reflected credential, including on HTTP 200.
                if token.encode() in body:
                    raise RiskTransportError("RESPONSE_REJECTED")
                return HttpReply(status, body)
        except HTTPError as error:
            # urllib raises before yielding the response for 4xx/5xx. Preserve
            # only the numeric status; neither its URL nor body is evidence.
            status = error.code
            try:
                error.close()
            except Exception:
                raise RiskTransportError("HTTP_TRANSPORT_FAILED") from None
            if type(status) is not int or not 400 <= status <= 599:
                raise RiskTransportError("HTTP_TRANSPORT_FAILED") from None
            return HttpReply(status, b"")
        except Exception:
            # Suppress exception chaining too: urllib errors include credential URLs.
            raise RiskTransportError("HTTP_TRANSPORT_FAILED") from None


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode()


class PrivateRiskSpool:
    """Fresh spool only; a partial run cannot be reopened as a successful run.

    Each receipt and byte payload is immutable. ``finalize`` is an explicit
    transport evidence completion marker, never a claim of READY/coverage.
    Failed receipts prevent finalization. All path traversal uses directory FDs.
    """

    def __init__(self, path: Path) -> None:
        path = path.absolute()
        self._fd = -1
        parent_fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in path.parts[1:-1]:
                next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
                os.close(parent_fd)
                parent_fd = next_fd
            os.mkdir(path.name, 0o700, dir_fd=parent_fd)
            self._fd = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
            if stat.S_IMODE(os.fstat(self._fd).st_mode) != 0o700:
                raise ValueError("SPOOL_PERMISSIONS_INVALID")
        finally:
            os.close(parent_fd)
        self._entries: dict[str, str] = {}
        self._failed = False
        self._finalized = False
        self._count = 0

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1

    def _put(self, name: str, body: bytes) -> str:
        temporary = ".partial-" + uuid.uuid4().hex
        linked = False
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self._fd)
            with os.fdopen(fd, "wb") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temporary, name, src_dir_fd=self._fd, dst_dir_fd=self._fd, follow_symlinks=False)
            linked = True
            os.unlink(temporary, dir_fd=self._fd)
            os.fsync(self._fd)
        except BaseException:
            self._failed = True
            if linked:
                # Never leave a completion marker after a failed durability check.
                try:
                    os.unlink(name, dir_fd=self._fd)
                except OSError:
                    pass
            raise
        digest = hashlib.sha256(body).hexdigest()
        self._entries[name] = digest
        return digest

    def append(self, receipt: SourceReceipt) -> str:
        if self._fd < 0 or self._failed or self._finalized:
            raise ValueError("SPOOL_NOT_WRITABLE")
        try:
            BoundedRiskTransport.validate(receipt.request)
            if hashlib.sha256(receipt.body).hexdigest() != receipt.payload_sha256:
                raise ValueError("RECEIPT_HASH_INVALID")
            if (receipt.started_at.tzinfo is None or receipt.received_at.tzinfo is None
                    or receipt.received_at < receipt.started_at):
                raise ValueError("RECEIPT_CLOCK_INVALID")
            name = f"{self._count:06d}"
            self._put(name + ".body", receipt.body)
            document = {
                "request": {"provider": receipt.request.provider, "path": receipt.request.path,
                            "parameters": dict(receipt.request.parameters)},
                "started_at": receipt.started_at.isoformat(), "received_at": receipt.received_at.isoformat(),
                "status": receipt.status, "payload_sha256": receipt.payload_sha256,
                "diagnostic": receipt.diagnostic,
            }
            digest = self._put(name + ".receipt.json", _json_bytes(document))
            self._count += 1
            if receipt.diagnostic is not None or receipt.status != 200:
                self._failed = True
            return digest
        except BaseException:
            self._failed = True
            raise

    def finalize(self) -> str:
        if self._fd < 0 or self._failed or self._finalized or not self._count:
            raise ValueError("SPOOL_NOT_COMPLETE")
        try:
            if stat.S_IMODE(os.fstat(self._fd).st_mode) != 0o700:
                raise ValueError("SPOOL_PERMISSIONS_INVALID")
            for name, expected_sha in self._entries.items():
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self._fd)
                with os.fdopen(fd, "rb") as handle:
                    metadata = os.fstat(handle.fileno())
                    if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
                        raise ValueError("SPOOL_FILE_INVALID")
                    digest = hashlib.sha256()
                    while chunk := handle.read(65536):
                        digest.update(chunk)
                    after = os.fstat(handle.fileno())
                    named = os.stat(name, dir_fd=self._fd, follow_symlinks=False)
                    # Compare metadata on the same descriptor before/after hashing
                    # and the current directory entry, detecting concurrent writes
                    # and pathname replacement during verification.
                    def identity(value: os.stat_result) -> tuple[int, ...]:
                        return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
                                value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
                    if identity(metadata) != identity(after) or identity(after) != identity(named):
                        raise ValueError("SPOOL_CHANGED_DURING_VERIFICATION")
                    if digest.hexdigest() != expected_sha:
                        raise ValueError("SPOOL_HASH_INVALID")
            if stat.S_IMODE(os.fstat(self._fd).st_mode) != 0o700:
                raise ValueError("SPOOL_PERMISSIONS_INVALID")
        except BaseException:
            self._failed = True
            raise
        digest = self._put("MANIFEST.json", _json_bytes({
            "schema_version": 1, "receipt_count": self._count,
            "transport_complete": True, "coverage_verified": False,
            "files": dict(self._entries),
        }))
        self._finalized = True
        return digest
