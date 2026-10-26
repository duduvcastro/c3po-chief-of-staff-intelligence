"""Construction missingness and historical-admissibility inventory; no realized labels.

Computable financial arithmetic is distinct from a historically admissible observation.
The existing canonical readers cannot prove original-document authentication, historical
instrument identity, share-class allocation or corporate-action basis. No caller flag,
source label, acceptance cut or self-computed hash can waive those missing proofs.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from .valuation_ensemble_adapters import AdaptedCompany
from .valuation_ensemble_inputs import NotEvaluable, Premises
from .valuation_ensemble_models import MODEL_IDS


# Inventory of inputs the current kernels actually consume. Missingness checks every
# required item, rather than treating the first kernel refusal as a complete inventory.
FACTS = {
    "dcf_fcff": ("operating_income_ttm","d_and_a_ttm","capex_ttm","change_working_capital_ttm","debt","cash","shares"),
    "dcf_fcfe": ("operating_cash_flow_ttm","capex_ttm","net_borrowing_ttm","shares"),
    "ddm_gordon": ("dividends_ttm","shares"),
    "ddm_multistage": ("dividends_ttm","shares"),
    "residual_income": ("book_equity_beginning","net_income_ttm","shares"),
    "earnings_power": ("normalized_operating_income","d_and_a_ttm","maintenance_capex","debt","cash","shares"),
    "capitalized_operating_cash_flow": ("operating_cash_flow_ttm","shares"),
    "pe": ("net_income_ttm","shares"),
    "ev_ebitda": ("operating_income_ttm","d_and_a_ttm","debt","cash","shares"),
    "ev_ebit": ("operating_income_ttm","debt","cash","shares"),
    "ev_sales": ("revenue_ttm","debt","cash","shares"),
    "price_book": ("book_equity","shares"),
    "price_operating_cash_flow": ("operating_cash_flow_ttm","shares"),
    "sector_regression": ("revenue_ttm","operating_income_ttm","debt","cash","shares"),
    "ncav": ("current_assets","total_liabilities","shares"),
    "tangible_book": ("book_equity","goodwill","intangible_assets_excluding_goodwill","shares"),
}
PREMISES = {
    "dcf_fcff": ("tax_rate","wacc","terminal_growth"),
    "dcf_fcfe": ("cost_of_equity","terminal_growth"),
    "ddm_gordon": ("cost_of_equity","terminal_growth"),
    "ddm_multistage": ("cost_of_equity","terminal_growth"),
    "residual_income": ("cost_of_equity","terminal_growth"),
    "earnings_power": ("tax_rate","wacc"),
    "capitalized_operating_cash_flow": ("cost_of_equity",),
}
ENTERPRISE = {"dcf_fcff","earnings_power","ev_ebitda","ev_ebit","ev_sales","sector_regression"}
PEER_MODELS = {"pe","ev_ebitda","ev_ebit","ev_sales","price_book","price_operating_cash_flow","sector_regression"}
GROWTH_PATH = {"dcf_fcff","dcf_fcfe","ddm_multistage"}
CORE_GATES = ("original_document_authentication","instrument_identity","share_basis","corporate_action_basis")


def historical_admissibility(adapted: AdaptedCompany) -> dict[str,Any]:
    # These readers expose metadata/hashes and detection-time symbol associations,
    # not independently authenticated originals or historical class/action proofs.
    # Keep the denial structural until a reviewed original-evidence adapter exists.
    gates = adapted.provenance["historical_proof_gates"]
    blocked = [f"{name}:{gates[name]['reason']}" for name in CORE_GATES]
    if adapted.company is None:
        blocked.append("source_adaptation:"+adapted.provenance["reason"])
    return {"status":"not_admissible","admissible":False,"blocking_proofs":blocked,
            "proof_adapter":"canonical_metadata_only_no_original_evidence_adapter",
            "acceptance_cut_is_not_historical_instrument_proof":True}


def audit_company(adapted: AdaptedCompany, computation: Mapping[str,Any] | None,
                  premises: Premises) -> dict[str,Any]:
    c = adapted.company
    admissibility = historical_admissibility(adapted)
    values = {row["model"]:row for row in computation["models"]} if computation else {}
    model_cells = {}
    for model in MODEL_IDS:
        facts, design, dependencies = {}, {}, []
        for field in FACTS[model]:
            try:
                if c is None:
                    raise NotEvaluable("source_adaptation_refused")
                c.get(field)
                facts[field] = {"status":"available"}
            except NotEvaluable as exc:
                facts[field] = {"status":"missing_or_ineligible","reason":str(exc)}
        for name in PREMISES.get(model,()):
            try:
                premises.get(name)
                design[name] = {"status":"supplied_design_premise"}
            except NotEvaluable as exc:
                design[name] = {"status":"missing_or_invalid","reason":str(exc)}
        if model in GROWTH_PATH and not premises.annual_growth_path:
            dependencies.append("explicit_growth_path_missing")
        if model in ENTERPRISE and (c is None or c.financial_company is None):
            dependencies.append("official_financial_classification_unattested")
        if model in PEER_MODELS:
            try:
                if c is None:
                    raise NotEvaluable("source_adaptation_refused")
                c.sector_at_T()
            except NotEvaluable as exc:
                dependencies.append("official_sector:"+str(exc))
            dependencies.append("peer_pool_must_satisfy_kernel_same_T_currency_sector_issuer_checks")
        result = values.get(model,{"status":"not_evaluable","reason":"source_adaptation_refused"})
        model_cells[model] = {"computable":result["status"]=="evaluated",
            "kernel_status":result["status"],"kernel_reason":result.get("reason"),
            "admissible":False,"required_facts":facts,"required_design_premises":design,
            "other_dependencies":dependencies,"blocking_proofs":admissibility["blocking_proofs"]}
    return {"schema":"VALUATION-ENSEMBLE-INPUT-AUDIT-v1","scope":"requested_cross_section_only_no_historical_coverage_claim",
        "admissibility":admissibility,"models":model_cells,
        "variants":{key:{"computable":value["status"]=="evaluated","kernel_reason":value.get("reason"),"admissible":False}
                    for key,value in (computation["variants"].items() if computation else ())}}


def summarize_audits(audits: list[Mapping[str,Any]]) -> dict[str,Any]:
    metrics = {}
    for model in MODEL_IDS:
        cells = [audit["models"][model] for audit in audits]
        facts, design, kernel = Counter(), Counter(), Counter()
        for cell in cells:
            if cell["kernel_reason"]:
                kernel[cell["kernel_reason"]] += 1
            for field,value in cell["required_facts"].items():
                if value["status"]!="available":
                    facts[field+":"+value["reason"]] += 1
            for name,value in cell["required_design_premises"].items():
                if value["status"]!="supplied_design_premise":
                    design[name+":"+value["reason"]] += 1
        metrics[model] = {"requested":len(cells),"computable":sum(x["computable"] for x in cells),
            "admissible":sum(x["admissible"] for x in cells),"kernel_refusals":dict(sorted(kernel.items())),
            "missing_or_ineligible_facts":dict(sorted(facts.items())),"missing_design_premises":dict(sorted(design.items()))}
    proof_counts = Counter(reason for audit in audits for reason in audit["admissibility"]["blocking_proofs"])
    return {"requested_companies":len(audits),"models":metrics,
        "blocking_proof_counts":dict(sorted(proof_counts.items())),"historical_coverage_attested":False,
        "computed_is_not_admissible":True,"denominator":"all_explicitly_requested_companies_including_adaptation_refusals"}
