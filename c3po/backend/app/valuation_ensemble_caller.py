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
from .valuation_ensemble_shadow import SOURCE, build_shadow_receipt


def _persist(receipt: dict[str,Any], store: FileReceiptStore) -> dict[str,Any]:
    receipt["run_key"] = canonical_hash(receipt)
    receipt["payload_sha256"] = canonical_hash(receipt)
    path,created = store.put(receipt)
    return {"run_key":receipt["run_key"],"payload_sha256":receipt["payload_sha256"],
            "created":created,"receipt_path":str(path)}


def run_shadow_cross_section(sources: Sources, requests: tuple[CompanyRequest,...], premises: Premises,
                             store: FileReceiptStore, *, reader_kind: str) -> dict[str,Any]:
    if reader_kind not in {"canonical_readers","offline_export"}:
        raise NotEvaluable("unsupported_shadow_reader_kind")
    if not requests:
        raise NotEvaluable("explicit_company_requests_required")
    if len({utc(x.as_of) for x in requests})!=1:
        raise NotEvaluable("one_cross_section_T_required_no_grid")
    identities=[(x.market,x.symbol) for x in requests]
    if len(identities)!=len(set(identities)):
        raise NotEvaluable("duplicate_company_request")
    premises.receipt() # validate all supplied assumptions before reading a source or persisting
    ordered=sorted(requests,key=lambda x:(x.market,x.symbol))
    adapted=[adapt_company(sources,request) for request in ordered]
    implementation=implementation_files()
    references,audits=[],[]
    for request,item in zip(ordered,adapted):
        computation=None
        if item.company is not None:
            peers=tuple(x.company for x in adapted if x is not item and x.company is not None)
            computation=build_shadow_receipt(item.company,premises,peers=peers,analyst_targets=item.analyst_targets)
        audit=audit_company(item,computation,premises)
        audits.append(audit)
        receipt={"schema":"VALUATION-ENSEMBLE-SHADOW-CALLER-COMPANY-v1","source":SOURCE,
            "diagnostic_only":True,"served_source_changed":False,"buy_permission":False,
            "signed_prereg":False,"horizon_sessions":None,"reader_kind":reader_kind,
            "status":"computed" if computation else "not_evaluable","historical_admissibility":audit["admissibility"],
            "adaptation":item.provenance,"premises":premises.receipt(),"implementation_files":implementation,
            "computation":computation,"input_audit":audit}
        stored=_persist(receipt,store)
        references.append({"market":request.market,"symbol":request.symbol,
            "run_key":stored["run_key"],"payload_sha256":stored["payload_sha256"],"status":receipt["status"]})
    metrics=summarize_audits(audits)
    receipt={"schema":"VALUATION-ENSEMBLE-SHADOW-CROSS-SECTION-v1","source":SOURCE,
        "diagnostic_only":True,"served_source_changed":False,"buy_permission":False,"signed_prereg":False,"horizon_sessions":None,
        "reader_kind":reader_kind,"as_of":utc(ordered[0].as_of).isoformat(),"status":"historical_admissibility_blocked",
        "requests":[{"market":x.market,"symbol":x.symbol,"as_of":utc(x.as_of).isoformat(),"basis_id":x.basis_id} for x in ordered],
        "company_receipts":references,"input_inventory":metrics,"premises":premises.receipt(),"implementation_files":implementation,
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
                               store: FileReceiptStore) -> dict[str,Any]:
    """Caller owns already-open reader handles. This function constructs no DB/client.

    Only StatementVintageStore.filings/vintages, PriceHistoryService.series and
    Database.latest_analysis_snapshot are used. No fetch/backfill/write method is called.
    The sole sink is the explicitly supplied private FileReceiptStore.
    """
    return run_shadow_cross_section(CanonicalSources(statement_store,price_reader,database),requests,premises,store,
                                    reader_kind="canonical_readers")


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-export",required=True)
    parser.add_argument("--requests",required=True)
    parser.add_argument("--premises",required=True)
    parser.add_argument("--receipt-directory",required=True)
    args=parser.parse_args(argv)
    try:
        packet,design=_load(args.requests),_load(args.premises)
        if packet.get("schema")!="VALUATION-ENSEMBLE-CROSS-SECTION-REQUEST-v1":
            raise NotEvaluable("unsupported_cross_section_request_schema")
        if set(packet)!={"schema","requests"} or any(set(x)!={"market","symbol","as_of","basis_id"} for x in packet["requests"]):
            raise NotEvaluable("only_explicit_company_requests_no_study_or_grid_inputs")
        requests=tuple(CompanyRequest(x["market"],x["symbol"],_instant(x["as_of"]),x["basis_id"]) for x in packet["requests"])
        premises=Premises(design["policy_id"],design.get("scalars",{}),tuple(design.get("annual_growth_path",())),design.get("minimum_peers",3))
        result=run_shadow_cross_section(BundleSources(_load(args.source_export)),requests,premises,
            FileReceiptStore(args.receipt_directory),reader_kind="offline_export")
        print(json.dumps({key:value for key,value in result.items() if key!="receipt_path"},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError) as exc:
        print(json.dumps({"status":"refused","reason":str(exc) if isinstance(exc,NotEvaluable) else type(exc).__name__},sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
