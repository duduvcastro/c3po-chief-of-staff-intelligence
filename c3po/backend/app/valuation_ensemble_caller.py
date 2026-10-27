"""Explicit production-shaped shadow caller using injected, already existing readers.

One requested cross-section at one T, with a durable construction/input inventory.
No default DB/client, connection factory, refresh, labels, grid, report or scheduling.
Nothing emitted here is historically admissible until missing original/instrument/
class/action evidence has an independently reviewed source adapter.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from .valuation_ensemble_adapters import CanonicalSources, BundleSources, CompanyRequest, Sources, _instant, adapt_company
from .valuation_ensemble_audit import audit_company, summarize_audits
from .valuation_ensemble_execution import _load, implementation_files
from .valuation_ensemble_inputs import NotEvaluable, Premises, canonical_hash, utc
from .valuation_ensemble_persistence import FileReceiptStore
from .valuation_ensemble_original_package import (ObservedSources, OriginalPackage, ingest_original_package,
    load_original_package, reconcile_company_originals, validate_original_package, validate_capture_store)
from .valuation_ensemble_original_store import OriginalEvidenceStore
from .valuation_ensemble_shadow import SOURCE, build_shadow_receipt


def _persist(receipt: dict[str,Any], store: FileReceiptStore) -> dict[str,Any]:
    receipt["run_key"] = canonical_hash(receipt)
    receipt["payload_sha256"] = canonical_hash(receipt)
    path,created = store.put(receipt)
    return {"run_key":receipt["run_key"],"payload_sha256":receipt["payload_sha256"],
            "created":created,"receipt_path":str(path)}


def run_shadow_cross_section(sources: Sources, requests: tuple[CompanyRequest,...], premises: Premises,
                             store: FileReceiptStore, *, reader_kind: str, original_package: OriginalPackage | None=None,
                             original_store: OriginalEvidenceStore | None=None,
                             capture_store: OriginalEvidenceStore | None=None) -> dict[str,Any]:
    if reader_kind not in {"canonical_readers","offline_export"}:
        raise NotEvaluable("unsupported_shadow_reader_kind")
    if (original_package is None)!=(original_store is None):
        raise NotEvaluable("original_package_and_explicit_private_store_required_together")
    if original_package is not None:
        validate_original_package(original_package);validate_capture_store(original_package,capture_store)
    elif capture_store is not None:raise NotEvaluable("capture_store_requires_original_package_references")
    if not requests:
        raise NotEvaluable("explicit_company_requests_required")
    if len({utc(x.as_of) for x in requests})!=1:
        raise NotEvaluable("one_cross_section_T_required_no_grid")
    identities=[(x.market,x.symbol) for x in requests]
    if len(identities)!=len(set(identities)):
        raise NotEvaluable("duplicate_company_request")
    premises.receipt() # validate all supplied assumptions before reading a source or persisting
    ordered=sorted(requests,key=lambda x:(x.market,x.symbol))
    observations=[ObservedSources(sources) for _ in ordered]
    adapted=[adapt_company(observed,request) for observed,request in zip(observations,ordered)]
    package_evidence={"status":"not_supplied","artifacts":[],"artifact_refusals":{},"historical_admissibility":False}
    if original_package is not None and original_store is not None:
        package_evidence=ingest_original_package(original_package,observations,original_store,capture_store=capture_store)
    implementation=implementation_files()
    references,audits=[],[]
    for request,item,observed in zip(ordered,adapted,observations):
        computation=None
        if item.company is not None:
            peers=tuple(x.company for x in adapted if x is not item and x.company is not None)
            computation=build_shadow_receipt(item.company,premises,peers=peers,analyst_targets=item.analyst_targets)
        originals=reconcile_company_originals(item,observed,package_evidence)
        audit=audit_company(item,computation,premises,originals=originals)
        audits.append(audit)
        receipt={"schema":"VALUATION-ENSEMBLE-SHADOW-CALLER-COMPANY-v1","source":SOURCE,
            "diagnostic_only":True,"served_source_changed":False,"buy_permission":False,
            "signed_prereg":False,"horizon_sessions":None,"reader_kind":reader_kind,
            "status":"computed" if computation else "not_evaluable","historical_admissibility":audit["admissibility"],
            "adaptation":item.provenance,"premises":premises.receipt(),"implementation_files":implementation,
            "computation":computation,"input_audit":audit,"original_reconciliation":originals}
        stored=_persist(receipt,store)
        references.append({"market":request.market,"symbol":request.symbol,
            "run_key":stored["run_key"],"payload_sha256":stored["payload_sha256"],"status":receipt["status"]})
    metrics=summarize_audits(audits)
    receipt={"schema":"VALUATION-ENSEMBLE-SHADOW-CROSS-SECTION-v1","source":SOURCE,
        "diagnostic_only":True,"served_source_changed":False,"buy_permission":False,"signed_prereg":False,"horizon_sessions":None,
        "reader_kind":reader_kind,"as_of":utc(ordered[0].as_of).isoformat(),"status":"historical_admissibility_blocked",
        "requests":[{"market":x.market,"symbol":x.symbol,"as_of":utc(x.as_of).isoformat(),"basis_id":x.basis_id} for x in ordered],
        "company_receipts":references,"input_inventory":metrics,"premises":premises.receipt(),"implementation_files":implementation,
        "original_package":package_evidence,
        "missing_source_contracts":[
            "canonical readers do not expose original SEC headers/CVM archive bytes for reauthentication",
            "filing symbols are detection-time associations, not a historical symbol-issuer-class validity interval",
            "SEC stored share counts collapse classes; CVM class totals do not map a ticker/unit to those classes",
            "price bars and adjusted-close ratios do not attest corporate actions or a consistent share basis",
            "no historical official sector/financial classification contract is available to these readers",
        ]}
    stored=_persist(receipt,store)
    return {**stored,"status":receipt["status"],"requested_companies":metrics["requested_companies"],
            "admissible_model_observations":sum(x["admissible"] for x in metrics["models"].values())}


def run_from_canonical_readers(statement_store: Any, price_reader: Any, database: Any,
                               requests: tuple[CompanyRequest,...], premises: Premises,
                               store: FileReceiptStore, *, original_package: OriginalPackage | None=None,
                               original_store: OriginalEvidenceStore | None=None,
                               capture_store: OriginalEvidenceStore | None=None) -> dict[str,Any]:
    """Caller owns already-open reader handles. This function constructs no DB/client.

    Only StatementVintageStore.filings/vintages, PriceHistoryService.series and
    Database.latest_analysis_snapshot are used. No fetch/backfill/write method is called.
    The sole sink is the explicitly supplied private FileReceiptStore.
    """
    return run_shadow_cross_section(CanonicalSources(statement_store,price_reader,database),requests,premises,store,
                                    reader_kind="canonical_readers",original_package=original_package,original_store=original_store,capture_store=capture_store)


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-export",required=True)
    parser.add_argument("--requests",required=True)
    parser.add_argument("--premises",required=True)
    parser.add_argument("--receipt-directory",required=True)
    parser.add_argument("--original-package",help="Explicit offline adjacent-file package; no source capture")
    parser.add_argument("--original-receipt-directory",help="Explicit private byte-object/manifest sink")
    parser.add_argument("--capture-receipt-directory",help="Explicit existing private capture receipts/objects; never executes capture")
    args=parser.parse_args(argv)
    try:
        if bool(args.original_package)!=bool(args.original_receipt_directory):
            raise NotEvaluable("original_package_and_explicit_private_store_required_together")
        packet,design=_load(args.requests),_load(args.premises)
        if packet.get("schema")!="VALUATION-ENSEMBLE-CROSS-SECTION-REQUEST-v1":
            raise NotEvaluable("unsupported_cross_section_request_schema")
        if set(packet)!={"schema","requests"} or any(set(x)!={"market","symbol","as_of","basis_id"} for x in packet["requests"]):
            raise NotEvaluable("only_explicit_company_requests_no_study_or_grid_inputs")
        requests=tuple(CompanyRequest(x["market"],x["symbol"],_instant(x["as_of"]),x["basis_id"]) for x in packet["requests"])
        premises=Premises(design["policy_id"],design.get("scalars",{}),tuple(design.get("annual_growth_path",())),design.get("minimum_peers",3))
        original_package=load_original_package(args.original_package) if args.original_package else None
        result=run_shadow_cross_section(BundleSources(_load(args.source_export)),requests,premises,
            FileReceiptStore(args.receipt_directory),reader_kind="offline_export",original_package=original_package,
            original_store=OriginalEvidenceStore(args.original_receipt_directory) if args.original_receipt_directory else None,
            capture_store=OriginalEvidenceStore(args.capture_receipt_directory) if args.capture_receipt_directory else None)
        print(json.dumps({key:value for key,value in result.items() if key!="receipt_path"},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError) as exc:
        print(json.dumps({"status":"refused","reason":str(exc) if isinstance(exc,NotEvaluable) else type(exc).__name__},sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
