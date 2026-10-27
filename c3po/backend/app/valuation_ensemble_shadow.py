"""Pure shadow receipt builder. Does not persist, schedule, promote, trade or read labels."""
from __future__ import annotations

from typing import Any

from .valuation_ensemble_aggregation import aggregate_variants
from .valuation_ensemble_inputs import AnalystTarget, CompanyInputs, NotEvaluable, Premises, analyst_consensus, canonical_hash, utc
from .valuation_ensemble_models import evaluate_models


SOURCE = "valuation_ensemble_shadow_v1"
SCHEMA = "VALUATION-ENSEMBLE-SHADOW-CONSTRUCTION-v1"


def _company_receipt(company: CompanyInputs) -> dict[str, Any]:
    facts = {}
    for name, fact in sorted(company.facts.items()):
        facts[name] = {"value": fact.value, "unit": fact.unit, "period_end": fact.period_end.isoformat(),
                       "evidence": fact.evidence.receipt()}
    return {"symbol": company.symbol, "issuer_id": company.issuer_id, "market": company.market, "currency": company.currency,
            "as_of": utc(company.as_of).isoformat(), "basis_id": company.basis_id,
            "price": {"value": company.price.value, "session_date": company.price.session_date.isoformat(),
                      "currency": company.price.currency, "basis_id": company.price.basis_id,
                      "evidence": company.price.evidence.receipt()},
            "sector": company.sector, "sector_evidence": company.sector_evidence.receipt() if company.sector_evidence else None,
            "financial_company": company.financial_company, "facts": facts}


def build_shadow_receipt(company: CompanyInputs, premises: Premises, *, peers: tuple[CompanyInputs, ...] = (),
                         analyst_targets: tuple[AnalystTarget, ...] = ()) -> dict[str, Any]:
    # A malformed packet cannot produce a JSON receipt containing NaN/Infinity. Per-model
    # missingness still applies to well-formed but ineligible/missing official facts.
    inputs = _company_receipt(company)
    peer_inputs = [_company_receipt(x) for x in sorted(peers, key=lambda x: (x.issuer_id, x.market, x.symbol))]
    try:
        canonical_hash([inputs, peer_inputs])
    except (ValueError, TypeError) as exc:
        raise NotEvaluable("non_serializable_input_packet") from exc
    models = evaluate_models(company, premises, peers=peers)
    consensus, consensus_receipt = analyst_consensus(analyst_targets, company)
    receipt = {"schema": SCHEMA, "source": SOURCE, "diagnostic_only": True,
               "served_source_changed": False, "buy_permission": False, "signed_prereg": False,
               "horizon_sessions": None, "as_of": utc(company.as_of).isoformat(),
               "inputs": inputs, "premises": premises.receipt(),
               "peer_inputs_sha256": canonical_hash(peer_inputs),
               "consensus": consensus_receipt, **aggregate_variants(models, consensus)}
    receipt["payload_sha256"] = canonical_hash(receipt)
    return receipt
