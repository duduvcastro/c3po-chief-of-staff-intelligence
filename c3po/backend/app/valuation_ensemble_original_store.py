"""Explicit private byte-object/manifest sink. No capture client or implicit connection."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, Mapping, Sequence

from .valuation_ensemble_inputs import NotEvaluable, canonical_hash
from .valuation_ensemble_originals import (MAX_BYTES, SourceBytes, bind_canonical_rows,
    extract_cvm_archive, extract_sec_header, extract_sec_instance)
from .valuation_ensemble_persistence import FileReceiptStore


class OriginalEvidenceStore:
    def __init__(self, directory: Path | str) -> None:
        self.manifests=FileReceiptStore(directory)
        self.objects=self.manifests.directory/"objects"
        self.objects.mkdir(mode=0o700,exist_ok=True)
        info=self.objects.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077:
            raise NotEvaluable("original_object_directory_not_private_owned")

    def _put_bytes(self, artifact: SourceBytes) -> str:
        digest=artifact.check()["sha256"];target=self.objects/(digest+".bin")
        fd,name=tempfile.mkstemp(prefix=".original-",dir=self.objects)
        try:
            with os.fdopen(fd,"wb") as handle:
                handle.write(artifact.payload);handle.flush();os.fsync(handle.fileno())
            try:
                os.link(name,target,follow_symlinks=False)
            except FileExistsError:
                self.read_bytes(digest)
            directory=os.open(self.objects,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:os.fsync(directory)
            finally:os.close(directory)
        finally:
            Path(name).unlink(missing_ok=True)
        return digest

    def read_bytes(self, digest: str) -> bytes:
        import re
        if not isinstance(digest,str) or not re.fullmatch(r"[0-9a-f]{64}",digest):
            raise NotEvaluable("invalid_original_object_digest")
        fd=os.open(self.objects/(digest+".bin"),os.O_RDONLY|os.O_NOFOLLOW)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600:
                raise NotEvaluable("original_object_not_private_regular_owned")
            with os.fdopen(fd,"rb",closefd=False) as handle:raw=handle.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES or hashlib.sha256(raw).hexdigest()!=digest:
                raise NotEvaluable("stored_original_bytes_digest_mismatch")
            return raw
        finally:os.close(fd)

    def read_manifest(self, run_key: str) -> dict[str,Any] | None:
        manifest=self.manifests.read(run_key)
        if manifest is None:return None
        if (manifest.get("schema")!="VALUATION-ENSEMBLE-SUPPLIED-ORIGINAL-v1"
                or manifest.get("origin_authentication")!="unverified_supplied_bytes"
                or manifest.get("historical_admissibility") is not False):
            raise NotEvaluable("original_manifest_contract_mismatch")
        referenced={manifest["extraction"]["artifact"]["sha256"]}
        if manifest["extraction"].get("header_artifact"):
            referenced.add(manifest["extraction"]["header_artifact"]["sha256"])
        if referenced!=set(manifest["object_sha256"]):
            raise NotEvaluable("original_manifest_object_reference_mismatch")
        for digest in sorted(referenced):self.read_bytes(digest)
        return manifest


def ingest_supplied_original(artifact: SourceBytes, store: OriginalEvidenceStore, *,
                             header: SourceBytes | None=None, filings: Sequence[Mapping[str,Any]]=(),
                             facts: Sequence[Mapping[str,Any]]=(), document_ids: tuple[str,...] | None=None) -> dict[str,Any]:
    """Parse supplied bytes, bind rows, then persist. No origin-authenticated flag input.

    A SEC instance is bound to separately supplied header bytes, not just its digest.
    CVM document_ids can bound extraction to the expressly requested document set.
    """
    if artifact.kind=="sec_header":
        extraction=extract_sec_header(artifact)
    elif artifact.kind=="sec_xbrl_instance":
        if header is None:
            raise NotEvaluable("sec_instance_requires_original_header_bytes")
        extraction=extract_sec_instance(artifact,header)
    elif artifact.kind=="cvm_archive":
        extraction=extract_cvm_archive(artifact,document_ids=document_ids)
    else:
        raise NotEvaluable("unsupported_original_kind")
    binding=bind_canonical_rows(extraction,filings=filings,facts=facts)
    object_digests=[store._put_bytes(artifact)]
    if artifact.kind=="sec_xbrl_instance" and header is not None:
        object_digests.append(store._put_bytes(header))
    manifest={"schema":"VALUATION-ENSEMBLE-SUPPLIED-ORIGINAL-v1","diagnostic_only":True,
        "buy_permission":False,"served_source_changed":False,"horizon_sessions":None,"signed_prereg":False,
        "origin_authentication":"unverified_supplied_bytes","historical_admissibility":False,
        "object_sha256":sorted(set(object_digests)),"extraction":extraction,"canonical_binding":binding,
        "implementation_files":{name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in
            ("valuation_ensemble_originals.py","valuation_ensemble_original_store.py","valuation_ensemble_inputs.py",
             "valuation_ensemble_adapters.py","valuation_ensemble_persistence.py","statement_vintages.py","sec_xbrl.py","cvm_fundamentals.py")},
        "pending_proofs":["independent_authentication_of_official_retrieval","historical_instrument_validity",
            "class_rights_and_per_share_allocation","corporate_action_basis_interval","reviewed_classification_policy"]}
    manifest["run_key"]=canonical_hash(manifest);manifest["payload_sha256"]=canonical_hash(manifest)
    path,created=store.manifests.put(manifest)
    return {"run_key":manifest["run_key"],"payload_sha256":manifest["payload_sha256"],"created":created,
        "manifest_path":str(path),"matched_rows":binding["matched"],"not_bound_rows":binding["not_bound"],
        "historical_admissibility":False,"origin_authentication":"unverified_supplied_bytes"}
