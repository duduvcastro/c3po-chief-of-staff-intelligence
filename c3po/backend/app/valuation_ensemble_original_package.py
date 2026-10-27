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
from .valuation_ensemble_capture import read_capture_receipt
from .valuation_ensemble_originals import (MAX_BYTES, SourceBytes, extract_cvm_archive, extract_sec_header, extract_sec_instance)
from .valuation_ensemble_original_store import OriginalEvidenceStore, ingest_supplied_original


@dataclass(frozen=True)
class CaptureReference:
    run_key: str
    payload_sha256: str


@dataclass(frozen=True)
class OriginalItem:
    artifact_id: str
    artifact: SourceBytes
    header_id: str | None=None
    document_ids: tuple[str,...] | None=None
    capture: CaptureReference | None=None


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
        allowed=required|{"header_id","document_ids","capture_run_key","capture_payload_sha256"}
        if not isinstance(item,dict) or not required<=set(item) or not set(item)<=allowed:
            raise NotEvaluable("original_package_artifact_fields_not_supported_no_trust_flags")
        name=item["local_file"]
        if not isinstance(name,str) or not name or name in {".",".."} or "/" in name or "\\" in name:
            raise NotEvaluable("original_package_requires_adjacent_regular_filenames")
        artifact=SourceBytes(item["kind"],item["source_url"],_instant(item["captured_at"]),item["expected_sha256"],_read(path.parent/name,MAX_BYTES))
        documents=item.get("document_ids")
        if documents is not None and (not isinstance(documents,list) or not documents or any(not isinstance(x,str) or not x.strip() for x in documents)):
            raise NotEvaluable("original_package_document_ids_invalid")
        if ("capture_run_key" in item)!=("capture_payload_sha256" in item):
            raise NotEvaluable("original_package_capture_reference_pair_required")
        capture=CaptureReference(item["capture_run_key"],item["capture_payload_sha256"]) if "capture_run_key" in item else None
        items.append(OriginalItem(item["artifact_id"],artifact,item.get("header_id"),tuple(documents) if documents is not None else None,capture))
    result=OriginalPackage(tuple(items));validate_original_package(result)
    return result


def validate_original_package(package: OriginalPackage) -> None:
    ids=[x.artifact_id for x in package.items]
    if not ids or any(not isinstance(x,str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}",x) for x in ids) or len(ids)!=len(set(ids)):
        raise NotEvaluable("original_package_artifact_ids_missing_or_duplicate")
    for item in package.items:
        if item.capture is not None and (not isinstance(item.capture,CaptureReference)
                or any(not isinstance(x,str) or not re.fullmatch(r"[0-9a-f]{64}",x) for x in (item.capture.run_key,item.capture.payload_sha256))):
            raise NotEvaluable("original_package_capture_reference_invalid")
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


def validate_capture_store(package: OriginalPackage, store: OriginalEvidenceStore | None) -> None:
    if any(x.capture is not None for x in package.items)!=(store is not None):
        raise NotEvaluable("capture_references_and_explicit_private_store_required_together")


def row_id(kind: str, row: Mapping[str,Any]) -> str:
    return canonical_hash({"kind":kind,"row":_jsonable(row)})


def _item_identity(item: OriginalItem) -> dict[str,Any]:
    payload=item.artifact.payload
    actual=hashlib.sha256(payload).hexdigest() if isinstance(payload,bytes) else None
    claimed={"artifact_id":item.artifact_id,"kind":str(item.artifact.kind),"source_url":str(item.artifact.source_url),
        "captured_at":str(item.artifact.captured_at),"expected_sha256":str(item.artifact.expected_sha256),
        "actual_supplied_sha256":actual,"header_id":item.header_id,"document_ids":item.document_ids,
        "capture_reference":item.capture.__dict__ if item.capture else None}
    return {"metadata_and_bytes_input_sha256":canonical_hash(claimed),"actual_supplied_sha256":actual,
        "expected_sha256":str(item.artifact.expected_sha256),"supplied_byte_count":len(payload) if isinstance(payload,bytes) else None,
        "header_id":item.header_id}


def _capture_link(item: OriginalItem, store: OriginalEvidenceStore | None, link: dict[str,Any]) -> None:
    if item.capture is None:return
    if store is None:raise NotEvaluable("explicit_capture_store_required")
    link.update(status="refused",run_key=item.capture.run_key,payload_sha256=item.capture.payload_sha256)
    try:receipt=read_capture_receipt(store,item.capture.run_key)
    except FileNotFoundError as exc:raise NotEvaluable("capture_reference_object_not_found") from exc
    if receipt is None:raise NotEvaluable("capture_reference_receipt_not_found")
    if receipt["payload_sha256"]!=item.capture.payload_sha256:raise NotEvaluable("capture_reference_payload_mismatch")
    link.update({key:receipt[key] for key in ("kind","requested_uri","final_uri","started_at","body_received_at","finished_at",
        "clock_consistent","observed_body_sha256","observed_body_bytes","body_complete","attempts")})
    link["recorded_transport_execution"]=receipt["transport_execution"]
    link["recorded_capture_status"]=receipt["status"]
    if receipt["status"]!="captured":raise NotEvaluable("capture_reference_refused:"+str(receipt["reason"]))
    if (receipt["kind"]!=item.artifact.kind or receipt["final_uri"]!=item.artifact.source_url
            or _instant(receipt["body_received_at"])!=_instant(item.artifact.captured_at)
            or receipt["observed_body_sha256"]!=item.artifact.expected_sha256):
        raise NotEvaluable("capture_reference_artifact_metadata_mismatch")
    # The existing reader checks the object; compare actual immutable bytes too.
    try:raw=store.read_bytes(receipt["observed_body_sha256"])
    except FileNotFoundError as exc:raise NotEvaluable("capture_reference_object_not_found") from exc
    if raw!=item.artifact.payload:raise NotEvaluable("capture_reference_artifact_bytes_mismatch")
    link.update(status="verified_link",reason=None)


def _documents(out: Mapping[str,Any] | None) -> list[dict[str,Any]]:
    if out is None:return []
    return [{key:doc[key] for key in ("issuer_key","doc_id","document_version","accepted_at")} for doc in out.get("documents",[out])]


def ingest_original_package(package: OriginalPackage, observations: Sequence[ObservedSources], store: OriginalEvidenceStore,
                            *, capture_store: OriginalEvidenceStore | None=None) -> dict[str,Any]:
    validate_original_package(package);validate_capture_store(package,capture_store)
    by_id={x.artifact_id:x for x in package.items};prepared={};failures={};captures={}
    for name,item in sorted(by_id.items()):
        captures[name]={"status":"not_supplied","reason":"capture_reference_not_supplied",
            "origin_authentication":"transport_observation_requires_independent_review","historical_admissibility":False}
        try:
            if item.artifact.kind=="sec_header":out=extract_sec_header(item.artifact)
            elif item.artifact.kind=="sec_xbrl_instance":
                header=by_id.get(item.header_id or "")
                if header is None or header.artifact.kind!="sec_header":raise NotEvaluable("original_package_header_kind_invalid")
                out=extract_sec_instance(item.artifact,header.artifact)
            elif item.artifact.kind=="cvm_archive":out=extract_cvm_archive(item.artifact,document_ids=item.document_ids)
            else:raise NotEvaluable("unsupported_original_kind")
            prepared[name]=out
            _capture_link(item,capture_store,captures[name])
        except (ValueError,TypeError,KeyError) as exc:
            failures[name]=str(exc) if isinstance(exc,NotEvaluable) else "original_bytes_or_layout_invalid"
            if item.capture is not None:captures[name].update(status="refused",reason=failures[name],
                run_key=item.capture.run_key,payload_sha256=item.capture.payload_sha256)
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
        header_capture=captures.get(item.header_id) if item.header_id is not None else None
        capture_provenance={"capture":captures[name],"header_capture":header_capture,
            "all_required_links_verified":captures[name]["status"]=="verified_link" and (header_capture is None or header_capture["status"]=="verified_link"),
            "origin_authentication":"transport_observation_requires_independent_review","historical_admissibility":False}
        if name in failures:
            receipts.append({"artifact_id":name,"kind":item.artifact.kind,"status":"refused","reason":failures[name],
                "documents":_documents(prepared.get(name)),"capture_provenance":capture_provenance,**_item_identity(item)})
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
        # Project only the occurrence already bound in this already-read manifest.
        # A digest shared by two occurrences is still ambiguous, not a selection.
        extraction=manifest["extraction"]
        for binding in bound:
            if binding["type"]!="fact":continue
            matches=[fact for fact in extraction.get("facts",[]) if binding["status"]=="content_matched"
                and fact.get("original_fact_sha256")==binding.get("original_fact_sha256")]
            observation: dict[str,Any]={"status":"unavailable","reason":binding.get("reason") or "bound_original_occurrence_missing",
                "original_fact_sha256":binding.get("original_fact_sha256")}
            if len(matches)>1:observation.update(status="ambiguous",reason="bound_original_occurrence_ambiguous")
            elif len(matches)==1:
                fact=matches[0]
                observation.update(status="observed_unique",reason=None,kind=extraction["kind"],
                    **{key:deepcopy(fact.get(key,extraction.get(key))) for key in
                       ("issuer_key","doc_id","document_version","accepted_at","concept","unit","period_start","period_end",
                        "context_id","context","entry","csv_line","raw_row_sha256","raw_row","decimals","lexical")})
            binding["original_fact_observation"]=observation
        receipts.append({"artifact_id":name,"kind":item.artifact.kind,"status":"ingested","reason":None,
            **_item_identity(item),
            "manifest_run_key":result["run_key"],"manifest_payload_sha256":result["payload_sha256"],
            "object_sha256":manifest["object_sha256"],"origin_authentication":"unverified_supplied_bytes",
            "documents":_documents(out),"bound_rows":bound,"capture_provenance":capture_provenance})
    return {"schema":"VALUATION-ENSEMBLE-ORIGINAL-PACKAGE-INGESTION-v1","status":"processed",
        "artifacts":receipts,"artifact_refusals":dict(sorted(Counter(x["reason"] for x in receipts if x["status"]=="refused").items())),
        "origin_authentication":"unverified_supplied_bytes","historical_admissibility":False}


def _original_status(kind: str, identity: str, package: Mapping[str,Any], row: Mapping[str,Any]) -> dict[str,Any]:
    matched=[];available=[];reasons=[];capture_links=[];capture_matches=[];capture_reasons=[];occurrences=[]
    for artifact in package.get("artifacts",[]):
        if any(_document_key(doc)==_document_key(row) for doc in artifact.get("documents",[])):
            provenance=artifact["capture_provenance"];capture_links.append(provenance)
            for link in (provenance["capture"],provenance["header_capture"]):
                if link is not None and link["status"]!="verified_link":capture_reasons.append(link["reason"])
        for binding in artifact.get("bound_rows",[]):
            if binding["type"]==kind and binding["canonical_row_id"]==identity:
                reference={"manifest_run_key":artifact["manifest_run_key"],"manifest_payload_sha256":artifact["manifest_payload_sha256"],
                           "object_sha256":artifact["object_sha256"],"capture_provenance":artifact["capture_provenance"]}
                available.append(reference)
                if binding["status"]=="content_matched":
                    matched.append(reference)
                    if artifact["capture_provenance"]["all_required_links_verified"]:capture_matches.append(reference)
                elif binding.get("reason"):reasons.append(binding["reason"])
                if kind=="fact":occurrences.append({**reference,"artifact_id":artifact["artifact_id"],
                    "binding_status":binding["status"],"observation":binding["original_fact_observation"]})
    return {"bytes_available":bool(available),"checked_content_equal":bool(matched),"manifest_references":available,
        "bound_original_occurrences":occurrences,
        "capture_linked_content_equal":bool(capture_matches),"capture_references":capture_links,
        "capture_link_reasons":[] if capture_matches else sorted(set(capture_reasons or ["canonical_content_or_capture_link_not_verified"])),
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


def _matches_reference(row: Mapping[str,Any], ref: Mapping[str,Any]) -> bool:
    return (row.get("row_hash")==ref.get("row_hash") and str(row.get("doc_id"))==ref["doc_id"]
        and str(row.get("concept"))==ref["concept"] and _instant(row["accepted_at"])==_instant(ref["accepted_at"])
        and _jsonable(row.get("period_start"))==ref["period_start"] and _jsonable(row.get("period_end"))==ref["period_end"])


def _opening_literal_link(ref: Mapping[str,Any] | None, ledger: Sequence[Mapping[str,Any]]) -> dict[str,Any]:
    """Resolve this RI observation only; partial references never pick a full row."""
    matches={line["canonical_row_id"]:line for line in ledger if ref is not None and line["canonical_hash_valid"]
        and _matches_reference(line["canonical_row"],ref)}
    result: dict[str,Any]={"status":"unavailable","reason":"canonical_reference_not_observed" if ref is None else "canonical_reference_no_full_row_match",
        "canonical_row_ids":sorted(matches),"original_occurrence":None,
        "reference_resolution":"unique_full_observed_row_matching_existing_partial_reference"}
    if len(matches)>1:result.update(status="ambiguous",reason="canonical_reference_matches_multiple_full_rows")
    elif len(matches)==1:
        line=next(iter(matches.values()));occurrences=line["original"]["bound_original_occurrences"]
        result.update(document_key_id=line["document_key_id"],original=line["original"])
        if len(occurrences)>1:result.update(status="ambiguous",reason="multiple_bound_original_occurrence_references")
        elif not occurrences:result["reason"]=line["original"]["reason"] or "bound_original_occurrence_missing"
        else:
            occurrence=occurrences[0];observation=occurrence["observation"]
            result.update(status="observed_unique" if observation["status"]=="observed_unique" else observation["status"],
                reason=observation["reason"],original_occurrence=occurrence)
    return result


def _opening_literal_pair(candidate: Mapping[str,Any], income: Mapping[str,Any]) -> dict[str,Any]:
    """Literal source labels only, with no common/controller/class interpretation."""
    left=(candidate.get("original_occurrence") or {}).get("observation",{})
    right=(income.get("original_occurrence") or {}).get("observation",{})
    available=candidate["status"]==income["status"]=="observed_unique"
    def compare(a: Any,b: Any) -> dict[str,Any]:
        return {"candidate":a,"income":b,"status":"unavailable" if not available or a is None or b is None
                else "literal_equal" if a==b else "literal_mismatch"}
    def scope(value: Mapping[str,Any]) -> str | None:
        parts=str(value.get("concept")).split(":",3)
        return parts[1].rsplit("_",1)[-1] if len(parts)==4 and parts[0]=="cvm" and parts[1].endswith(("_con","_ind")) else None
    return {"issuer":compare(left.get("issuer_key"),right.get("issuer_key")),
        "normalized_unit":compare(left.get("unit"),right.get("unit")),
        "reported_statement_scope_label":compare(scope(left),scope(right)),
        "explicit_dimensions":compare((left.get("context") or {}).get("dimensions"),(right.get("context") or {}).get("dimensions")),
        "typed_dimension_present":compare((left.get("context") or {}).get("typed_dimension_present"),(right.get("context") or {}).get("typed_dimension_present")),
        "unsupported_context_content_present":compare((left.get("context") or {}).get("unsupported_context_content_present"),(right.get("context") or {}).get("unsupported_context_content_present")),
        "reported_concepts":{"candidate":left.get("concept"),"income":right.get("concept"),"equivalence":"not_established_by_alias_selection"},
        "class":{"status":"unattested","reason":"no_reviewed_economic_class_or_attribution_contract"},
        "share_basis":{"status":"unattested","reason":"caller_basis_id_is_not_historical_allocation_or_action_proof"},
        "context_and_document_ids":"document_local_provenance_not_cross_period_equality_tests",
        "scope_class_basis_comparability":"unattested"}


def _opening_literal_observation(opening: Mapping[str,Any], ledger: Sequence[Mapping[str,Any]]) -> dict[str,Any]:
    candidate=_opening_literal_link((opening.get("candidate") or {}).get("row"),ledger)
    window=opening.get("window") or {};terms=[]
    for term in window.get("combined_raw_terms_including_cancellations",[]):
        income=_opening_literal_link(term["row"],ledger)
        occurrences=[{"support_sha256":quarter["support_sha256"],"period_start":quarter["period_start"],"period_end":quarter["period_end"],
            "derived":quarter["derived"],"coefficient":raw["coefficient"]}
            for quarter in window.get("selected_quarters_newest_first",[]) for raw in quarter["terms"] if raw["row"]==term["row"]]
        terms.append({"coefficient":term["coefficient"],"row_reference":term["row"],"selected_quarter_occurrences":occurrences,
            "original_link":income,"literal_observations":_opening_literal_pair(candidate,income)})
    return {"candidate_original_link":candidate,"consumed_income_raw_terms_including_cancellations":terms,
        "scope":"literal_original_observations_only_not_economic_comparability","scope_class_basis_comparability":"unattested",
        "model_fact_emitted":False,"used_in_computation":False,"historical_admissibility":False}


def reconcile_company_originals(adapted: AdaptedCompany, observed: ObservedSources, package: Mapping[str,Any]) -> dict[str,Any]:
    from .statement_vintages import vintage_row_hash
    derivations=adapted.provenance.get("fact_derivations",{})
    references={name:_references(value) for name,value in derivations.items()}
    opening=adapted.provenance.get("beginning_book_observation",{})
    candidate=(opening.get("candidate") or {}).get("row")
    ledger=[]
    for row in observed.fact_rows or []:
        identity=row_id("fact",row);fields=[];observed_for=[]
        try:
            valid=row.get("row_hash")==vintage_row_hash(row)
            if valid:
                for name,refs in references.items():
                    if any(_matches_reference(row,ref) for ref in refs):
                        fields.append(name)
                if candidate is not None and _matches_reference(row,candidate):
                    observed_for.append("residual_income_opening_equity_candidate")
        except (ValueError,TypeError,KeyError):valid=False
        key=_document_key(row)
        ledger.append({"canonical_row_id":identity,"row_hash":row.get("row_hash"),"doc_id":str(row.get("doc_id")),
            "document_key":key,"document_key_id":canonical_hash(key),
            "concept":row.get("concept"),"canonical_row":_jsonable(row),"canonical_hash_valid":valid,"used_by_fields":sorted(fields),
            "observed_for":observed_for,
            "original":_original_status("fact",identity,package,row)})
    issuer=adapted.provenance.get("issuer_id");used_docs={x["doc_id"] for x in ledger if x["used_by_fields"]}
    documents=[]
    usage: dict[str,set[str]]={}
    observation_usage: dict[str,set[str]]={}
    for line in ledger:usage.setdefault(line["document_key_id"],set()).update(line["used_by_fields"])
    for line in ledger:observation_usage.setdefault(line["document_key_id"],set()).update(line["observed_for"])
    for row in observed.filing_rows:
        if str(row.get("issuer_key"))==issuer or str(row.get("doc_id")) in used_docs:
            identity=row_id("filing",row)
            key=_document_key(row);key_id=canonical_hash(key)
            documents.append({"canonical_row_id":identity,"doc_id":str(row.get("doc_id")),
                "document_key":key,"document_key_id":key_id,"used_by_fields":sorted(usage.get(key_id,set())),
                "observed_for":sorted(observation_usage.get(key_id,set())),
                "canonical_row":_jsonable(row),"original":_original_status("filing",identity,package,row)})
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
                and all(x["original"]["checked_content_equal"] for x in lines+docs),
            "all_capture_links_verified":bool(lines) and keys<=observed_keys and all(x["original"]["capture_linked_content_equal"] for x in lines+docs),
            "capture_link_reasons":sorted({reason for x in lines+docs for reason in x["original"]["capture_link_reasons"]}),
            "capture_references":[ref for _,ref in sorted({canonical_hash(ref):ref for x in lines+docs for ref in x["original"]["capture_references"]}.items())],
            "historical_admissibility":False}
    candidate_rows=[{"canonical_row_id":x["canonical_row_id"],"document_key_id":x["document_key_id"],"original":x["original"]}
                    for x in ledger if x["observed_for"]]
    candidate_keys={x["document_key_id"] for x in candidate_rows}
    opening_links={"status":opening.get("status","not_observed"),"reason":opening.get("reason","fact_stage_not_observed"),
        "candidate_row_references":sorted(candidate_rows,key=lambda x:x["canonical_row_id"]),
        "candidate_document_references":[{"canonical_row_id":x["canonical_row_id"],"document_key_id":x["document_key_id"],"original":x["original"]}
            for x in sorted(documents,key=lambda x:x["canonical_row_id"]) if x["document_key_id"] in candidate_keys],
        "literal_original_observation":_opening_literal_observation(opening,ledger),
        "net_income_ttm_dependencies":fields.get("net_income_ttm"),"model_fact_emitted":False,"used_in_computation":False}
    return {"schema":"VALUATION-ENSEMBLE-COMPANY-ORIGINAL-RECONCILIATION-v1","package_status":package["status"],
        "fact_stage_observed":observed.fact_rows is not None,"observed_fact_rows":len(observed.fact_rows or []),
        "row_ledger":sorted(ledger,key=lambda x:x["canonical_row_id"]),"document_ledger":sorted(documents,key=lambda x:x["canonical_row_id"]),
        "fields":fields,"package_refusals":package.get("artifact_refusals",{}),"beginning_book_observation":opening_links,
        "origin_authentication":"unverified_supplied_bytes","historical_admissibility":False}
