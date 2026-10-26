"""Explicit offline original package and source-observation reconciliation.

Package/manifests are supplied evidence, never source authentication. No network or
DB is opened; missing/refused artifacts remain visible without dropping companies.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping, Sequence

from .valuation_ensemble_adapters import AdaptedCompany, Sources, _instant, _jsonable
from .valuation_ensemble_inputs import NotEvaluable, canonical_hash
from .valuation_ensemble_originals import (MAX_BYTES, SourceBytes, extract_cvm_archive, extract_sec_header, extract_sec_instance)
from .valuation_ensemble_original_store import OriginalEvidenceStore, ingest_supplied_original


@dataclass(frozen=True)
class OriginalItem:
    artifact_id: str
    artifact: SourceBytes
    header_id: str | None=None
    document_ids: tuple[str,...] | None=None


@dataclass(frozen=True)
class OriginalPackage:
    items: tuple[OriginalItem,...]


class ObservedSources:
    """Record immutable copies of exactly the reader results used by one adaptation."""
    def __init__(self, sources: Sources) -> None:
        self.sources=sources
        self.filing_rows: list[Mapping[str,Any]]=[]
        self.fact_rows: list[Mapping[str,Any]] | None=None

    def filings(self, market: str) -> Sequence[Mapping[str,Any]]:
        self.filing_rows=deepcopy(list(self.sources.filings(market)))
        return self.filing_rows

    def facts(self, market: str, issuer: str, as_of: Any) -> Sequence[Mapping[str,Any]]:
        self.fact_rows=deepcopy(list(self.sources.facts(market,issuer,as_of)))
        return self.fact_rows

    def price_series(self, market: str, symbol: str, as_of: Any) -> Mapping[str,Any]:
        return deepcopy(self.sources.price_series(market,symbol,as_of))

    def consensus_snapshot(self, market: str, symbol: str) -> Mapping[str,Any] | None:
        return deepcopy(self.sources.consensus_snapshot(market,symbol))


def _read(path: Path, limit: int) -> bytes:
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):raise NotEvaluable("original_package_requires_regular_files")
        with os.fdopen(fd,"rb",closefd=False) as handle:raw=handle.read(limit+1)
        if len(raw)>limit:raise NotEvaluable("original_package_file_too_large")
        return raw
    finally:os.close(fd)


def load_original_package(path: str | Path) -> OriginalPackage:
    path=Path(path).absolute()
    packet=json.loads(_read(path,16*1024*1024))
    if not isinstance(packet,dict) or set(packet)!={"schema","artifacts"} or packet["schema"]!="VALUATION-ENSEMBLE-ORIGINAL-PACKAGE-v1":
        raise NotEvaluable("unsupported_original_package_schema_or_fields")
    if not isinstance(packet["artifacts"],list) or not packet["artifacts"]:
        raise NotEvaluable("explicit_original_artifacts_required")
    items=[]
    for item in packet["artifacts"]:
        required={"artifact_id","kind","source_url","captured_at","expected_sha256","local_file"}
        allowed=required|{"header_id","document_ids"}
        if not isinstance(item,dict) or not required<=set(item) or not set(item)<=allowed:
            raise NotEvaluable("original_package_artifact_fields_not_supported_no_trust_flags")
        name=item["local_file"]
        if not isinstance(name,str) or not name or name in {".",".."} or "/" in name or "\\" in name:
            raise NotEvaluable("original_package_requires_adjacent_regular_filenames")
        artifact=SourceBytes(item["kind"],item["source_url"],_instant(item["captured_at"]),item["expected_sha256"],_read(path.parent/name,MAX_BYTES))
        documents=item.get("document_ids")
        if documents is not None and (not isinstance(documents,list) or not documents or any(not isinstance(x,str) or not x.strip() for x in documents)):
            raise NotEvaluable("original_package_document_ids_invalid")
        items.append(OriginalItem(item["artifact_id"],artifact,item.get("header_id"),tuple(documents) if documents is not None else None))
    result=OriginalPackage(tuple(items));validate_original_package(result)
    return result


def validate_original_package(package: OriginalPackage) -> None:
    ids=[x.artifact_id for x in package.items]
    if not ids or any(not isinstance(x,str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}",x) for x in ids) or len(ids)!=len(set(ids)):
        raise NotEvaluable("original_package_artifact_ids_missing_or_duplicate")
    for item in package.items:
        if item.artifact.kind not in {"sec_header","sec_xbrl_instance","cvm_archive"}:
            raise NotEvaluable("unsupported_original_kind")
        if item.document_ids is not None and (not isinstance(item.document_ids,tuple) or not item.document_ids
                or any(not isinstance(x,str) or not x.strip() for x in item.document_ids)
                or len(item.document_ids)!=len(set(item.document_ids))):
            raise NotEvaluable("original_package_document_ids_invalid")
        if item.artifact.kind=="sec_xbrl_instance":
            if item.header_id not in ids or item.document_ids is not None:
                raise NotEvaluable("original_package_instance_header_reference_invalid")
        elif item.header_id is not None:
            raise NotEvaluable("original_package_unexpected_header_reference")
        if item.artifact.kind!="cvm_archive" and item.document_ids is not None:
            raise NotEvaluable("original_package_document_selection_only_for_CVM")


def row_id(kind: str, row: Mapping[str,Any]) -> str:
    return canonical_hash({"kind":kind,"row":_jsonable(row)})


def _item_identity(item: OriginalItem) -> dict[str,Any]:
    payload=item.artifact.payload
    actual=hashlib.sha256(payload).hexdigest() if isinstance(payload,bytes) else None
    claimed={"artifact_id":item.artifact_id,"kind":str(item.artifact.kind),"source_url":str(item.artifact.source_url),
        "captured_at":str(item.artifact.captured_at),"expected_sha256":str(item.artifact.expected_sha256),
        "actual_supplied_sha256":actual,"header_id":item.header_id,"document_ids":item.document_ids}
    return {"metadata_and_bytes_input_sha256":canonical_hash(claimed),"actual_supplied_sha256":actual,
        "expected_sha256":str(item.artifact.expected_sha256),"supplied_byte_count":len(payload) if isinstance(payload,bytes) else None,
        "header_id":item.header_id}


def ingest_original_package(package: OriginalPackage, observations: Sequence[ObservedSources], store: OriginalEvidenceStore) -> dict[str,Any]:
    validate_original_package(package)
    by_id={x.artifact_id:x for x in package.items};prepared={};failures={}
    for name,item in sorted(by_id.items()):
        try:
            if item.artifact.kind=="sec_header":out=extract_sec_header(item.artifact)
            elif item.artifact.kind=="sec_xbrl_instance":
                header=by_id.get(item.header_id or "")
                if header is None or header.artifact.kind!="sec_header":raise NotEvaluable("original_package_header_kind_invalid")
                out=extract_sec_instance(item.artifact,header.artifact)
            elif item.artifact.kind=="cvm_archive":out=extract_cvm_archive(item.artifact,document_ids=item.document_ids)
            else:raise NotEvaluable("unsupported_original_kind")
            prepared[name]=out
        except (ValueError,TypeError,KeyError) as exc:
            failures[name]=str(exc) if isinstance(exc,NotEvaluable) else "original_bytes_or_layout_invalid"
    roles: dict[tuple[Any,...],list[str]]={}
    for name,out in prepared.items():
        for doc in out.get("documents",[out]):
            roles.setdefault((out["kind"],doc["issuer_key"],doc["doc_id"],doc["document_version"]),[]).append(name)
    for names in roles.values():
        if len(names)>1:
            for name in names:failures[name]="original_document_role_ambiguous"
    for name,item in by_id.items():
        if item.header_id in failures:failures[name]="original_header_dependency_refused"
    source_rows={kind:{} for kind in ("filing","fact")}
    for observed in observations:
        for kind,rows in (("filing",observed.filing_rows),("fact",observed.fact_rows or [])):
            for row in rows:source_rows[kind][row_id(kind,row)]=row
    receipts=[]
    for name,item in sorted(by_id.items()):
        if name in failures:
            receipts.append({"artifact_id":name,"kind":item.artifact.kind,"status":"refused","reason":failures[name],**_item_identity(item)})
            continue
        out=prepared[name];documents=out.get("documents",[out]);doc_ids={x["doc_id"] for x in documents}
        market="B3" if item.artifact.kind=="cvm_archive" else "US"
        rows={kind:[(identity,row) for identity,row in sorted(source_rows[kind].items()) if row.get("market")==market and str(row.get("doc_id")) in doc_ids]
              for kind in ("filing","fact")}
        if item.artifact.kind=="sec_header":rows["fact"]=[]
        header=by_id[item.header_id].artifact if item.header_id is not None else None
        result=ingest_supplied_original(item.artifact,store,header=header,document_ids=item.document_ids,
            filings=[x[1] for x in rows["filing"]],facts=[x[1] for x in rows["fact"]])
        manifest=store.read_manifest(result["run_key"])
        if manifest is None:raise NotEvaluable("persisted_original_manifest_not_found")
        ordered=[(kind,identity) for kind in ("filing","fact") for identity,_ in rows[kind]]
        bound=[{"type":kind,"canonical_row_id":identity,**binding} for (kind,identity),binding in zip(ordered,manifest["canonical_binding"]["rows"])]
        receipts.append({"artifact_id":name,"kind":item.artifact.kind,"status":"ingested","reason":None,
            **_item_identity(item),
            "manifest_run_key":result["run_key"],"manifest_payload_sha256":result["payload_sha256"],
            "object_sha256":manifest["object_sha256"],"origin_authentication":"unverified_supplied_bytes",
            "documents":[{key:doc[key] for key in ("issuer_key","doc_id","document_version","accepted_at")} for doc in documents],"bound_rows":bound})
    return {"schema":"VALUATION-ENSEMBLE-ORIGINAL-PACKAGE-INGESTION-v1","status":"processed",
        "artifacts":receipts,"artifact_refusals":dict(sorted(Counter(x["reason"] for x in receipts if x["status"]=="refused").items())),
        "origin_authentication":"unverified_supplied_bytes","historical_admissibility":False}


def _original_status(kind: str, identity: str, package: Mapping[str,Any]) -> dict[str,Any]:
    matched=[];available=[];reasons=[]
    for artifact in package.get("artifacts",[]):
        for binding in artifact.get("bound_rows",[]):
            if binding["type"]==kind and binding["canonical_row_id"]==identity:
                reference={"manifest_run_key":artifact["manifest_run_key"],"manifest_payload_sha256":artifact["manifest_payload_sha256"],
                           "object_sha256":artifact["object_sha256"]}
                available.append(reference)
                if binding["status"]=="content_matched":matched.append(reference)
                elif binding.get("reason"):reasons.append(binding["reason"])
    return {"bytes_available":bool(available),"checked_content_equal":bool(matched),"manifest_references":available,
        "reason":None if matched else ";".join(sorted(set(reasons))) if reasons else
            "original_package_not_supplied" if package["status"]=="not_supplied" else "no_usable_original_for_observed_canonical_row",
        "origin_authentication":"unverified_supplied_bytes" if available else "not_available","historical_admissibility":False}


def _references(value: Mapping[str,Any]) -> list[Mapping[str,Any]]:
    refs=list(value.get("rows",[]))
    for component in value.get("components",[]):refs.extend(_references(component))
    return refs


def _document_key(row: Mapping[str,Any]) -> dict[str,Any]:
    try:accepted=_instant(row.get("accepted_at")).isoformat()
    except (ValueError,TypeError):accepted=str(row.get("accepted_at"))
    return {"issuer_key":str(row.get("issuer_key")),"doc_id":str(row.get("doc_id")),
            "document_version":_jsonable(row.get("document_version",1)),"accepted_at":accepted}


def reconcile_company_originals(adapted: AdaptedCompany, observed: ObservedSources, package: Mapping[str,Any]) -> dict[str,Any]:
    from .statement_vintages import vintage_row_hash
    derivations=adapted.provenance.get("fact_derivations",{})
    references={name:_references(value) for name,value in derivations.items()}
    ledger=[]
    for row in observed.fact_rows or []:
        identity=row_id("fact",row);fields=[]
        try:
            valid=row.get("row_hash")==vintage_row_hash(row)
            if valid:
                for name,refs in references.items():
                    if any(row.get("row_hash")==ref.get("row_hash") and str(row.get("doc_id"))==ref["doc_id"]
                        and str(row.get("concept"))==ref["concept"] and _instant(row["accepted_at"])==_instant(ref["accepted_at"])
                        and _jsonable(row.get("period_start"))==ref["period_start"] and _jsonable(row.get("period_end"))==ref["period_end"] for ref in refs):
                        fields.append(name)
        except (ValueError,TypeError,KeyError):valid=False
        key=_document_key(row)
        ledger.append({"canonical_row_id":identity,"row_hash":row.get("row_hash"),"doc_id":str(row.get("doc_id")),
            "document_key":key,"document_key_id":canonical_hash(key),
            "concept":row.get("concept"),"canonical_row":_jsonable(row),"canonical_hash_valid":valid,"used_by_fields":sorted(fields),
            "original":_original_status("fact",identity,package)})
    issuer=adapted.provenance.get("issuer_id");used_docs={x["doc_id"] for x in ledger if x["used_by_fields"]}
    documents=[]
    usage: dict[str,set[str]]={}
    for line in ledger:usage.setdefault(line["document_key_id"],set()).update(line["used_by_fields"])
    for row in observed.filing_rows:
        if str(row.get("issuer_key"))==issuer or str(row.get("doc_id")) in used_docs:
            identity=row_id("filing",row)
            key=_document_key(row);key_id=canonical_hash(key)
            documents.append({"canonical_row_id":identity,"doc_id":str(row.get("doc_id")),
                "document_key":key,"document_key_id":key_id,"used_by_fields":sorted(usage.get(key_id,set())),
                "canonical_row":_jsonable(row),"original":_original_status("filing",identity,package)})
    fields={}
    for field in sorted(derivations):
        lines=[x for x in ledger if field in x["used_by_fields"]];doc_ids={x["doc_id"] for x in lines}
        keys={x["document_key_id"] for x in lines};docs=[x for x in documents if x["document_key_id"] in keys]
        observed_keys={x["document_key_id"] for x in docs}
        fields[field]={"canonical_row_ids":sorted(x["canonical_row_id"] for x in lines),"document_ids":sorted(doc_ids),
            "document_key_ids":sorted(keys),
            "all_original_bytes_available":bool(lines) and keys<=observed_keys
                and all(x["original"]["bytes_available"] for x in lines+docs),
            "all_checked_content_equal":bool(lines) and keys<=observed_keys
                and all(x["original"]["checked_content_equal"] for x in lines+docs),"historical_admissibility":False}
    return {"schema":"VALUATION-ENSEMBLE-COMPANY-ORIGINAL-RECONCILIATION-v1","package_status":package["status"],
        "fact_stage_observed":observed.fact_rows is not None,"observed_fact_rows":len(observed.fact_rows or []),
        "row_ledger":sorted(ledger,key=lambda x:x["canonical_row_id"]),"document_ledger":sorted(documents,key=lambda x:x["canonical_row_id"]),
        "fields":fields,"package_refusals":package.get("artifact_refusals",{}),
        "origin_authentication":"unverified_supplied_bytes","historical_admissibility":False}
