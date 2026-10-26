"""Offline caller mechanics; these fixtures are not real historical coverage."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import importlib
import json
from pathlib import Path

import pytest

from app.config import get_settings
from app.database import Database
from app.statement_vintages import StatementVintageStore
from app.valuation_price_history import bar_record
from app.valuation_ensemble_adapters import BundleSources, _jsonable
from app.valuation_ensemble_caller import main, run_from_canonical_readers, run_shadow_cross_section
from app.valuation_ensemble_execution import execute_shadow
from app.valuation_ensemble_inputs import NotEvaluable
from app.valuation_ensemble_models import MODEL_IDS
from app.valuation_ensemble_persistence import FileReceiptStore
from test_valuation_ensemble_adapters import source_bundle, request, premises, T


def run_bundle(tmp_path, b=None, requests=None):
    store=FileReceiptStore(tmp_path/"receipts")
    result=run_shadow_cross_section(BundleSources(b or source_bundle()),requests or (request(),),premises(),store,
                                    reader_kind="offline_export")
    return store,result,store.read(result["run_key"])


def test_canonical_caller_uses_existing_readers_only_and_keeps_refusals_in_denominators(tmp_path):
    b=source_bundle();database=Database(get_settings().model_copy(update={"database_url":None}))
    statements=StatementVintageStore(database)
    statements.register_filings(b["filings"]);statements.insert_vintages("US","issuer1",b["facts"])
    calls=[]
    class Statements:
        def filings(self,*args,**kwargs):
            calls.append("filings");return statements.filings(*args,**kwargs)
        def vintages(self,*args,**kwargs):
            calls.append("vintages");return statements.vintages(*args,**kwargs)
    class Prices:
        def series(self,market,symbol,*,available_before):
            calls.append("series");assert available_before==T
            return b["price_series"].get(f"{market}:{symbol}",{"status":"no_vintage"})
    class Snapshots:
        def latest_analysis_snapshot(self,*args):
            calls.append("snapshot");return None
    before=(len(database._statement_filings),len(database._statement_vintages),len(database._analysis_snapshots))
    store=FileReceiptStore(tmp_path/"receipts")
    result=run_from_canonical_readers(Statements(),Prices(),Snapshots(),
        (request(),replace(request(),symbol="MISSING")),premises(),store)
    saved=store.read(result["run_key"]);metrics=saved["input_inventory"]
    assert result["status"]=="historical_admissibility_blocked"
    assert result["requested_companies"]==2 and result["admissible_model_observations"]==0
    assert set(metrics["models"])==set(MODEL_IDS)
    assert all(x["requested"]==2 and x["admissible"]==0 for x in metrics["models"].values())
    assert metrics["models"]["capitalized_operating_cash_flow"]["computable"]==1
    assert metrics["models"]["capitalized_operating_cash_flow"]["kernel_refusals"]=={"source_adaptation:official_symbol_issuer_unattested":1}
    assert not metrics["historical_coverage_attested"]
    assert sorted(calls)==sorted(["filings","filings","vintages","series","snapshot"])
    assert before==(len(database._statement_filings),len(database._statement_vintages),len(database._analysis_snapshots))


def test_missingness_inventories_all_inputs_not_only_the_first_kernel_refusal(tmp_path):
    _,_,saved=run_bundle(tmp_path)
    metrics=saved["input_inventory"]["models"]
    assert metrics["dcf_fcff"]["kernel_refusals"]=={"financial_classification_unattested":1}
    assert metrics["dcf_fcff"]["missing_or_ineligible_facts"]=={
        "capex_ttm:missing_fact:capex_ttm":1,
        "change_working_capital_ttm:missing_fact:change_working_capital_ttm":1,
        "d_and_a_ttm:missing_fact:d_and_a_ttm":1,
        "operating_income_ttm:missing_fact:operating_income_ttm":1,
    }
    assert metrics["dcf_fcff"]["missing_design_premises"]=={
        "tax_rate:missing_premise:tax_rate":1,"terminal_growth:missing_premise:terminal_growth":1,
        "wacc:missing_premise:wacc":1,
    }


def test_price_refusal_does_not_turn_validated_official_facts_into_missing_inputs(tmp_path):
    b=source_bundle();b["price_series"]["NASDAQ:XYZ"]={"status":"no_vintage"}
    store,_,saved=run_bundle(tmp_path,b)
    company=store.read(saved["company_receipts"][0]["run_key"])
    assert company["status"]=="not_evaluable"
    assert {"operating_cash_flow_ttm","shares"}<=set(company["adaptation"]["facts_available"])
    cell=company["input_audit"]["models"]["capitalized_operating_cash_flow"]
    assert all(x["status"]=="available" for x in cell["required_facts"].values())
    metric=saved["input_inventory"]["models"]["capitalized_operating_cash_flow"]
    assert metric["missing_or_ineligible_facts"]=={}
    assert metric["unobserved_facts"]=={}
    assert not metric["computable"] and not metric["admissible"]
    assert metric["kernel_refusals"]=={"source_adaptation:price_series:no_vintage":1}


def test_unreached_fact_stage_is_unobserved_rather_than_falsely_missing(tmp_path):
    store,_,saved=run_bundle(tmp_path,requests=(replace(request(),symbol="MISSING"),))
    company=store.read(saved["company_receipts"][0]["run_key"])
    assert "facts_available" not in company["adaptation"]
    cell=company["input_audit"]["models"]["capitalized_operating_cash_flow"]
    assert all(x["status"]=="not_observed" for x in cell["required_facts"].values())
    metric=saved["input_inventory"]["models"]["capitalized_operating_cash_flow"]
    assert metric["missing_or_ineligible_facts"]=={}
    assert metric["unobserved_facts"]=={
        "operating_cash_flow_ttm:source_adaptation:official_symbol_issuer_unattested":1,
        "shares:source_adaptation:official_symbol_issuer_unattested":1,
    }
    assert metric["requested"]==1 and not metric["computable"] and not metric["admissible"]


def test_detection_time_reused_ticker_is_never_historical_instrument_or_class_proof(tmp_path):
    b=source_bundle();row=b["filings"][0]
    row.update(symbols=["REUSED"],first_seen_at="2026-10-26T03:00:00+00:00",
               historical_symbol_valid_from="2020-01-01",security_class="common",sector="Industrials")
    prices=b["price_series"].pop("NASDAQ:XYZ")
    bar=bar_record("NASDAQ","REUSED","REUSED.US",dict(date="2021-06-30",close=10,adjusted_close=10,volume=1000))
    bar["fetched_at"]=prices["fetched_at"];prices["bars"]={"2021-06-30":bar}
    b["price_series"]["NASDAQ:REUSED"]=prices
    store,result,saved=run_bundle(tmp_path,b,(replace(request(),symbol="REUSED"),))
    company=store.read(saved["company_receipts"][0]["run_key"])
    # Arithmetic can run on the declared association, but acceptance/hash/current
    # symbol metadata cannot prove that the reused ticker identified this issuer in T.
    assert company["status"]=="computed"
    assert company["computation"]["inputs"]["issuer_id"]=="issuer1"
    assert company["computation"]["inputs"]["sector"]==""
    assert company["historical_admissibility"]["admissible"] is False
    assert "instrument_identity:filing_symbols_are_detection_time_associations" in company["historical_admissibility"]["blocking_proofs"]
    assert all(not x["admissible"] for x in company["input_audit"]["models"].values())
    assert result["admissible_model_observations"]==0


def test_earlier_one_company_entry_point_also_exposes_nonwaivable_historical_gate(tmp_path):
    store=FileReceiptStore(tmp_path/"receipts")
    result=execute_shadow(BundleSources(source_bundle()),request(),premises(),store)
    receipt=store.read(result["run_key"])
    assert receipt["status"]=="computed"
    assert receipt["historical_admissibility"]["status"]=="not_admissible"
    assert receipt["historical_admissibility"]["acceptance_cut_is_not_historical_instrument_proof"]
    assert len(receipt["historical_admissibility"]["blocking_proofs"])==4


def test_cross_section_replay_order_is_deterministic_and_immutable(tmp_path):
    requests=(request(),replace(request(),symbol="MISSING"))
    store,first,saved=run_bundle(tmp_path,requests=requests)
    original=Path(first["receipt_path"]).read_bytes();stamp=Path(first["receipt_path"]).stat().st_mtime_ns
    second=run_shadow_cross_section(BundleSources(source_bundle()),tuple(reversed(requests)),premises(),
                                    FileReceiptStore(store.directory),reader_kind="offline_export")
    assert first["run_key"]==second["run_key"] and not second["created"]
    assert Path(first["receipt_path"]).read_bytes()==original
    assert Path(first["receipt_path"]).stat().st_mtime_ns==stamp
    assert len(list(store.directory.glob("*.json")))==3 # two companies plus one inventory


@pytest.mark.parametrize("requests,reason",[
    ((),"explicit_company_requests_required"),
    ((request(),request()),"duplicate_company_request"),
    ((request(),replace(request(),as_of=T+timedelta(days=1))),"one_cross_section_T_required_no_grid"),
])
def test_cross_section_scope_refused_before_reading_or_persisting(requests,reason):
    class NoRead:
        def __getattr__(self,name):
            pytest.fail("unexpected source read: "+name)
    class NoWrite:
        def put(self,*args):
            pytest.fail("unexpected persistence")
    with pytest.raises(NotEvaluable,match=reason):
        run_shadow_cross_section(NoRead(),requests,premises(),NoWrite(),reader_kind="offline_export")


def test_import_and_reload_never_construct_a_database_or_price_client(monkeypatch):
    import app.valuation_ensemble_caller as caller
    import app.valuation_price_history as history
    def forbidden(*args,**kwargs):
        pytest.fail("caller import constructed an operational dependency")
    monkeypatch.setattr(Database,"__init__",forbidden)
    monkeypatch.setattr(history.PriceHistoryService,"__init__",forbidden)
    assert importlib.reload(caller).run_from_canonical_readers is not None


def test_offline_cross_section_cli_has_no_names_in_stdout_and_cannot_waive_gates(tmp_path,capsys):
    files={"source-export":source_bundle(),"requests":{"schema":"VALUATION-ENSEMBLE-CROSS-SECTION-REQUEST-v1",
        "requests":[dict(market="NASDAQ",symbol="XYZ",as_of=T.isoformat(),basis_id="declared-common")]},
        "premises":{"policy_id":"fixture-design","scalars":{"cost_of_equity":.1}}}
    args=[]
    for flag,value in files.items():
        path=tmp_path/(flag+".json");path.write_text(json.dumps(_jsonable(value)));args += ["--"+flag,str(path)]
    args += ["--receipt-directory",str(tmp_path/"receipts")]
    assert main(args)==0
    output=capsys.readouterr().out;result=json.loads(output)
    assert result["status"]=="historical_admissibility_blocked" and result["admissible_model_observations"]==0
    assert "XYZ" not in output and str(tmp_path) not in output
    packet=files["requests"];packet["requests"][0]["historically_admissible"]=True
    (tmp_path/"requests.json").write_text(json.dumps(packet))
    assert main(args)==2
    assert json.loads(capsys.readouterr().out)["reason"]=="only_explicit_company_requests_no_study_or_grid_inputs"
