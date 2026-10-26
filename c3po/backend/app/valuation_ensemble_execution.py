"""One-company shadow execution from existing canonical readers or an offline export.

CLI execution reads only explicit files and writes only an explicit private receipt
directory. It does not connect to a host/database, fetch sources, choose a horizon,
read labels, launch a grid, trade, schedule or alter what is served.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .valuation_ensemble_adapters import BundleSources, CompanyRequest, Sources, _instant, adapt_company
from .valuation_ensemble_inputs import NotEvaluable, Premises, canonical_hash
from .valuation_ensemble_persistence import FileReceiptStore
from .valuation_ensemble_shadow import SOURCE, build_shadow_receipt


IMPLEMENTATION_FILES = ("valuation_ensemble_inputs.py","valuation_ensemble_models.py","valuation_ensemble_aggregation.py",
    "valuation_ensemble_shadow.py","valuation_ensemble_adapters.py","valuation_ensemble_persistence.py","valuation_ensemble_execution.py",
    "statement_vintages.py","valuation_price_history.py","sec_xbrl.py","cvm_fundamentals.py")


def implementation_files() -> dict[str,str]:
    root = Path(__file__).parent
    return {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in IMPLEMENTATION_FILES}


def execute_shadow(sources: Sources, request: CompanyRequest, premises: Premises, store: FileReceiptStore,
                   *, peer_requests: tuple[CompanyRequest,...] = ()) -> dict[str,Any]:
    adapted = adapt_company(sources,request)
    peers = [adapt_company(sources,x) for x in sorted(peer_requests,key=lambda x:(x.market,x.symbol))]
    computation = None
    if adapted.company is not None:
        computation = build_shadow_receipt(adapted.company,premises,
            peers=tuple(x.company for x in peers if x.company is not None),analyst_targets=adapted.analyst_targets)
    receipt = {"schema":"VALUATION-ENSEMBLE-SHADOW-EXECUTION-v1","source":SOURCE,
        "diagnostic_only":True,"served_source_changed":False,"buy_permission":False,"signed_prereg":False,"horizon_sessions":None,
        "status":"computed" if computation else "not_evaluable","adaptation":adapted.provenance,
        "peer_adaptations":[x.provenance for x in peers],"premises":premises.receipt(),"implementation_files":implementation_files(),
        "computation":computation}
    receipt["run_key"] = canonical_hash(receipt)
    receipt["payload_sha256"] = canonical_hash(receipt)
    path,created = store.put(receipt)
    return {"run_key":receipt["run_key"],"payload_sha256":receipt["payload_sha256"],"status":receipt["status"],
            "created":created,"receipt_path":str(path)}


def _load(path: str) -> Any:
    fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        with os.fdopen(fd,"rb",closefd=False) as handle:
            raw = handle.read(16*1024*1024+1)
        if len(raw)>16*1024*1024:
            raise NotEvaluable("source_export_too_large")
        return json.loads(raw)
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-export",required=True)
    parser.add_argument("--request",required=True,help="market,symbol,as_of,basis_id and optional peers; no horizon")
    parser.add_argument("--premises",required=True)
    parser.add_argument("--receipt-directory",required=True)
    args = parser.parse_args(argv)
    try:
        raw_request,raw_premises = _load(args.request),_load(args.premises)
        if any(key in raw_request for key in ("horizon","horizon_sessions","grid","report")):
            raise NotEvaluable("study_or_grid_inputs_not_allowed_in_shadow_construction")
        def request(value: dict[str,Any]) -> CompanyRequest:
            return CompanyRequest(value["market"],value["symbol"],_instant(value["as_of"]),value["basis_id"])
        premises = Premises(raw_premises["policy_id"],raw_premises.get("scalars",{}),
                            tuple(raw_premises.get("annual_growth_path",())),raw_premises.get("minimum_peers",3))
        result = execute_shadow(BundleSources(_load(args.source_export)),request(raw_request),premises,
                                FileReceiptStore(args.receipt_directory),
                                peer_requests=tuple(request(x) for x in raw_request.get("peers",[])))
        print(json.dumps({key:result[key] for key in ("run_key","payload_sha256","status","created")},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError) as exc:
        # No raw source payloads, symbols, local paths or exception traces on stdout.
        print(json.dumps({"status":"refused","reason":str(exc) if isinstance(exc,NotEvaluable) else type(exc).__name__},sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
