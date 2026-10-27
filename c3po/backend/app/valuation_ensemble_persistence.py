"""An explicit private artifact sink, isolated from all production valuation tables.

Receipts are committed by linking a fully fsynced private temporary file under the
content-derived run key. A retry verifies the immutable object instead of rewriting it.
No database schema, existing writer or served-source registry is changed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Mapping

from .valuation_ensemble_inputs import NotEvaluable, canonical_hash


def encoded_receipt(receipt: Mapping[str,Any]) -> bytes:
    return (json.dumps(receipt,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)+"\n").encode()


def _valid_identity(receipt: Mapping[str,Any]) -> bool:
    core={k:v for k,v in receipt.items() if k not in {"run_key","payload_sha256"}}
    payload={k:v for k,v in receipt.items() if k!="payload_sha256"}
    return receipt.get("run_key")==canonical_hash(core) and receipt.get("payload_sha256")==canonical_hash(payload)


class FileReceiptStore:
    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory).absolute()
        self.directory.mkdir(mode=0o700,parents=False,exist_ok=True)
        info = self.directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise NotEvaluable("receipt_directory_must_be_private_owned_directory")

    def _path(self, run_key: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}",run_key):
            raise NotEvaluable("invalid_run_key")
        return self.directory/(run_key+".json")

    def read(self, run_key: str) -> dict[str,Any] | None:
        path = self._path(run_key)
        try:
            fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        except FileNotFoundError:
            return None
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
                raise NotEvaluable("receipt_file_not_private_regular_owned_file")
            with os.fdopen(fd,"rb",closefd=False) as handle:
                raw = handle.read(16*1024*1024+1)
            if len(raw)>16*1024*1024:
                raise NotEvaluable("receipt_too_large")
            value = json.loads(raw)
            if not isinstance(value,dict) or value.get("run_key") != run_key or not _valid_identity(value):
                raise NotEvaluable("stored_receipt_integrity_failure")
            return value
        finally:
            os.close(fd)

    def put(self, receipt: Mapping[str,Any]) -> tuple[Path,bool]:
        run_key = str(receipt.get("run_key") or "")
        path = self._path(run_key)
        if not _valid_identity(receipt):
            raise NotEvaluable("receipt_payload_hash_mismatch")
        raw = encoded_receipt(receipt)
        if len(raw)>16*1024*1024:
            raise NotEvaluable("receipt_too_large")
        fd,name = tempfile.mkstemp(prefix=".ensemble-",suffix=".tmp",dir=self.directory)
        temporary = Path(name)
        try:
            with os.fdopen(fd,"wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            created = True
            try:
                os.link(temporary,path,follow_symlinks=False)
            except FileExistsError:
                created = False
                existing = self.read(run_key)
                if existing != dict(receipt):
                    raise NotEvaluable("run_key_collision_or_incomplete_receipt")
            directory_fd = os.open(self.directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return path,created
        finally:
            temporary.unlink(missing_ok=True)
