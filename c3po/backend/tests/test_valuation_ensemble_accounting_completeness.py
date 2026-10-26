"""Accounting-scope regressions with synthetic canonical rows, no real coverage."""
from copy import deepcopy
from datetime import date
import socket

import pytest

from app.valuation_ensemble_adapters import BundleSources, adapt_company
from app.valuation_ensemble_caller import run_shadow_cross_section
from app.valuation_ensemble_inputs import NotEvaluable
from app.valuation_ensemble_models import evaluate_models
from app.valuation_ensemble_persistence import FileReceiptStore
from test_valuation_ensemble_adapters import source_bundle, fact, request, premises
from test_valuation_ensemble import company as pure_company


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def fail(*args,**kwargs):pytest.fail("no network in accounting fixture tests")
    monkeypatch.setattr(socket,"socket",fail);monkeypatch.setattr(socket,"create_connection",fail)


def debt_witness(*,current_aggregate=None):
    bundle=source_bundle();bundle["facts"]=[row for row in bundle["facts"] if row["concept"]!="us-gaap:DebtCurrent"]
    for concept,value in (("us-gaap:LongTermDebtCurrent",10),("us-gaap:ShortTermBorrowings",5),("us-gaap:CommercialPaper",2)):
        bundle["facts"].append(fact(concept,value))
    if current_aggregate is not None:bundle["facts"].append(fact("us-gaap:DebtCurrent",current_aggregate))
    return bundle


def intangible_witness():
    bundle=source_bundle()
    for concept,value in (("us-gaap:Goodwill",10),("us-gaap:FiniteLivedIntangibleAssetsNet",5),
                          ("us-gaap:IndefiniteLivedIntangibleAssetsExcludingGoodwill",7)):
        bundle["facts"].append(fact(concept,value))
    return bundle


def test_partial_current_debt_witness_is_not_promoted_to_a_complete_aggregate():
    adapted=adapt_company(BundleSources(debt_witness()),request());company=adapted.company
    assert company is not None and "debt" not in company.facts
    assert company.get("long_term_debt_current_reported")==10
    assert company.get("short_term_borrowings_reported")==5 and company.get("commercial_paper_reported")==2
    assert adapted.provenance["refused"]["aggregate_completeness_unattested:debt"]==1
    with pytest.raises(NotEvaluable,match="missing_fact:debt"):company.get("debt")


def test_finite_lived_witness_is_not_promoted_to_all_non_goodwill_intangibles():
    adapted=adapt_company(BundleSources(intangible_witness()),request());company=adapted.company
    assert company is not None and "intangible_assets_excluding_goodwill" not in company.facts
    assert company.get("finite_lived_intangible_assets_net_reported")==5
    assert company.get("indefinite_lived_intangible_assets_excluding_goodwill_reported")==7
    assert adapted.provenance["refused"]["aggregate_completeness_unattested:intangible_assets_excluding_goodwill"]==1
    result=next(x for x in evaluate_models(company,premises()) if x.model=="tangible_book")
    assert result.status=="not_evaluable" and result.reason=="missing_fact:intangible_assets_excluding_goodwill"


def test_explicit_current_aggregate_control_keeps_total35_without_adding_subcomponents_again():
    bundle=debt_witness(current_aggregate=15);bundle["facts"].append(fact("us-gaap:LongTermDebt",30))
    adapted=adapt_company(BundleSources(bundle),request());company=adapted.company
    assert company is not None and company.get("debt")==35
    assert company.get("long_term_debt_reported")==30 and "debt_total" not in company.facts
    refs=adapted.provenance["fact_derivations"]["debt"]["components"]
    assert {row["concept"] for component in refs for row in component["rows"]}=={"us-gaap:DebtCurrent","us-gaap:LongTermDebtNoncurrent"}
    assert "aggregate_completeness_unattested:debt" not in adapted.provenance["refused"]


def test_long_term_only_is_reported_evidence_and_never_assumed_to_exhaust_total_debt():
    bundle=source_bundle();bundle["facts"]=[row for row in bundle["facts"] if row["concept"] not in {"us-gaap:DebtCurrent","us-gaap:LongTermDebtNoncurrent"}]
    bundle["facts"].append(fact("us-gaap:LongTermDebt",30))
    adapted=adapt_company(BundleSources(bundle),request())
    assert adapted.company.get("long_term_debt_reported")==30
    assert "debt" not in adapted.company.facts and "debt_total" not in adapted.company.facts
    assert adapted.provenance["fact_derivations"]["long_term_debt_reported"]["rows"][0]["concept"]=="us-gaap:LongTermDebt"


def test_explicit_complete_intangible_kernel_control_remains6_8_without_changing_the_kernel():
    # A deliberate pure-kernel control supplies an already complete amount. It is
    # not a closure rule, origin proof, source-adapter field or real observation.
    company=pure_company(intangible_assets_excluding_goodwill=12)
    result=next(x for x in evaluate_models(company,premises()) if x.model=="tangible_book")
    assert result.status=="evaluated" and result.value==pytest.approx(6.8)


@pytest.mark.parametrize("concept",["us-gaap:FiniteLivedIntangibleAssetsNet","us-gaap:IndefiniteLivedIntangibleAssetsExcludingGoodwill"])
def test_single_intangible_component_does_not_make_missing_sibling_zero(concept):
    bundle=intangible_witness();bundle["facts"]=[row for row in bundle["facts"] if row["concept"] not in {
        "us-gaap:FiniteLivedIntangibleAssetsNet","us-gaap:IndefiniteLivedIntangibleAssetsExcludingGoodwill"} or row["concept"]==concept]
    adapted=adapt_company(BundleSources(bundle),request())
    assert "intangible_assets_excluding_goodwill" not in adapted.company.facts
    assert adapted.provenance["refused"]["aggregate_completeness_unattested:intangible_assets_excluding_goodwill"]==1


def test_component_vintages_still_obey_causal_hash_and_period_checks():
    bundle=debt_witness();future=deepcopy(bundle["facts"][-1]);future["accepted_at"]=request().as_of.replace(year=2022)
    future["value"]=999 # Ineligible future content may not poison eligible component.
    bundle["facts"].append(future)
    adapted=adapt_company(BundleSources(bundle),request())
    assert adapted.company.get("commercial_paper_reported")==2 and "debt" not in adapted.company.facts
    assert adapted.provenance["refused"]["fact_available_after_T"]==1
    # Even valid aggregate limbs at different instants cannot establish full debt.
    other=debt_witness(current_aggregate=15)
    other["facts"]=[row for row in other["facts"] if row["concept"]!="us-gaap:DebtCurrent"]
    other["facts"].append(fact("us-gaap:DebtCurrent",15,end=date(2020,12,31)))
    mismatched=adapt_company(BundleSources(other),request())
    assert "debt" not in mismatched.company.facts
    assert mismatched.provenance["refused"]["period_mismatch:debt"]==1


@pytest.mark.parametrize("case,field,model",[("debt","debt","ev_sales"),
    ("intangible","intangible_assets_excluding_goodwill","tangible_book")])
def test_incomplete_aggregate_is_visible_in_durable_model_audit_without_dropping_a_company(tmp_path,case,field,model):
    from dataclasses import replace
    bundle=debt_witness() if case=="debt" else intangible_witness()
    store=FileReceiptStore(tmp_path/"receipts");target=request()
    result=run_shadow_cross_section(BundleSources(bundle),(target,replace(target,symbol="MISSING")),premises(),store,reader_kind="offline_export")
    saved=store.read(result["run_key"]);metric=saved["input_inventory"]["models"][model]
    assert metric["requested"]==2 and metric["admissible"]==0
    assert any(key.startswith(field+":missing_fact:") for key in metric["missing_or_ineligible_facts"])
    company=next(store.read(ref["run_key"]) for ref in saved["company_receipts"] if ref["symbol"]==target.symbol)
    assert company["adaptation"]["refused"]["aggregate_completeness_unattested:"+field]==1
    assert not company["historical_admissibility"]["admissible"] and not company["served_source_changed"] and not company["buy_permission"]
