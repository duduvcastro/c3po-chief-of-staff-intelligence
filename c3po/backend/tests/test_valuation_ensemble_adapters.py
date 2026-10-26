from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os

import pytest

from app.config import get_settings
from app.database import Database
from app.statement_vintages import StatementVintageStore, vintage_row_hash
from app.valuation_price_history import bar_record
from app.valuation_ensemble_adapters import BundleSources, CanonicalSources, CompanyRequest, adapt_company
from app.valuation_ensemble_execution import execute_shadow, main
from app.valuation_ensemble_inputs import NotEvaluable, Premises, canonical_hash
from app.valuation_ensemble_persistence import FileReceiptStore


T = datetime(2021,7,1,4,tzinfo=timezone.utc)
ACCEPTED = datetime(2021,5,1,16,tzinfo=timezone.utc)


def filing(doc="report", *, market="US", accepted=ACCEPTED, issuer="issuer1", symbol="XYZ"):
    if market=="B3":
        accepted=datetime.combine(accepted.astimezone(ZoneInfo("America/Sao_Paulo")).date(),time.max,tzinfo=ZoneInfo("America/Sao_Paulo")).astimezone(timezone.utc)
    return dict(market=market,issuer_key=issuer,source="sec_edgar" if market=="US" else "cvm_dados_abertos",
                doc_id=doc,form="10-K" if market=="US" else "DFP",filed_date=accepted.astimezone(ZoneInfo("America/Sao_Paulo")).date() if market=="B3" else accepted.date(),accepted_at=accepted,
                accepted_source="sec_header" if market=="US" else "cvm_dt_receb_end_of_day",header_sha256="a"*64,symbols=[symbol])


def fact(concept, value, *, start=None, end=date(2021,3,31), doc="report", market="US", issuer="issuer1", accepted=ACCEPTED,unit="USD"):
    if market=="B3":
        accepted=datetime.combine(accepted.astimezone(ZoneInfo("America/Sao_Paulo")).date(),time.max,tzinfo=ZoneInfo("America/Sao_Paulo")).astimezone(timezone.utc)
    row=dict(market=market,issuer_key=issuer,source="sec_xbrl_companyfacts" if market=="US" else "cvm_dados_abertos",
             doc_id=doc,form="10-K" if market=="US" else "DFP",filed_date=accepted.date(),accepted_at=accepted,
             period_start=start,period_end=end,concept=concept,unit=unit,value=value)
    row["row_hash"]=vintage_row_hash(row)
    return row


def series(market="NASDAQ",symbol="XYZ", *, available=T-timedelta(hours=1),captured=T-timedelta(hours=2)):
    row=bar_record(market,symbol,symbol+".US",dict(date="2021-06-30",close=10,adjusted_close=10,volume=1000))
    assert row is not None
    row.update(fetched_at=captured.isoformat())
    return dict(status="ok",publication_id="price-publication",available_at=available.isoformat(),
                fetched_at=captured.isoformat(),first_captured_at=captured.isoformat(),bars={"2021-06-30":row})


def source_bundle():
    rows=[fact("dei:EntityCommonStockSharesOutstanding",10,unit="shares"),
          fact("us-gaap:StockholdersEquity",90),fact("us-gaap:CashAndCashEquivalentsAtCarryingValue",10),
          fact("us-gaap:LongTermDebtNoncurrent",20),fact("us-gaap:DebtCurrent",10)]
    for quarter,(start,end) in enumerate(((date(2020,4,1),date(2020,6,30)),(date(2020,7,1),date(2020,9,30)),
                                          (date(2020,10,1),date(2020,12,31)),(date(2021,1,1),date(2021,3,31)))):
        rows.append(fact("us-gaap:NetIncomeLoss",3+quarter,start=start,end=end))
        rows.append(fact("us-gaap:NetCashProvidedByUsedInOperatingActivities",5,start=start,end=end))
    return dict(schema="VALUATION-ENSEMBLE-SOURCE-EXPORT-v1",filings=[filing()],facts=rows,
                price_series={"NASDAQ:XYZ":series()},consensus_snapshots={})


def request(market="NASDAQ"):
    return CompanyRequest(market,"XYZ",T,"issuer1-common-as-traded")


def premises():
    return Premises("fixture-policy",{"cost_of_equity":.1},())


def test_official_sec_adapter_verifies_row_hashes_and_reconstructs_four_quarters():
    adapted=adapt_company(BundleSources(source_bundle()),request())
    assert adapted.company is not None
    assert adapted.company.get("net_income_ttm")==18
    assert adapted.company.get("operating_cash_flow_ttm")==20
    assert adapted.company.get("debt")==30
    assert adapted.company.financial_company is None
    assert adapted.provenance["classification"]=="unattested_no_industrial_default"
    assert adapted.company.facts["net_income_ttm"].evidence.available_at==ACCEPTED
    assert len(adapted.provenance["fact_derivations"]["net_income_ttm"]["rows"])==4


def test_canonical_store_reader_matches_offline_export_without_writes_or_network():
    bundle=source_bundle()
    database=Database(get_settings().model_copy(update={"database_url":None}))
    store=StatementVintageStore(database)
    store.register_filings(bundle["filings"])
    store.insert_vintages("US","issuer1",bundle["facts"])
    class Prices:
        def series(self, market, symbol, *, available_before):
            assert (market,symbol,available_before)==("NASDAQ","XYZ",T)
            return bundle["price_series"]["NASDAQ:XYZ"]
    source=CanonicalSources(store,Prices(),database)
    before=(len(database._statement_filings),len(database._statement_vintages),len(database._analysis_snapshots))
    adapted=adapt_company(source,request())
    assert adapted.company is not None
    assert adapted.company.get("net_income_ttm")==18
    assert before==(len(database._statement_filings),len(database._statement_vintages),len(database._analysis_snapshots))


def test_latest_eligible_restatement_changes_value_but_later_filing_does_not_leak():
    b=source_bundle()
    old=next(x for x in b["facts"] if x["concept"]=="us-gaap:NetIncomeLoss")
    for doc,value,accepted in (("amend",30,T-timedelta(hours=4)),("future",300,T+timedelta(hours=1))):
        b["filings"].append(filing(doc,accepted=accepted))
        b["facts"].append(fact(old["concept"],value,start=old["period_start"],end=old["period_end"],doc=doc,accepted=accepted))
    a=adapt_company(BundleSources(b),request())
    assert a.company.get("net_income_ttm")==45
    assert a.company.facts["net_income_ttm"].evidence.available_at==T-timedelta(hours=4)
    assert a.provenance["refused"]["filing_available_after_T"]==1
    assert a.provenance["refused"]["fact_available_after_T"]==1


@pytest.mark.parametrize("future_change", [
    {"value":999},
    {"issuer_key":"another-issuer"},
    {"source":"provider_guess"},
    {"period_end":date(2022,3,31)},
    {"doc_id":"unregistered-document"},
    {"concept":"us-gaap:UnrelatedFutureConcept"},
])
def test_future_fact_content_cannot_invalidate_eligible_historical_fields(future_change):
    b=source_bundle()
    baseline=adapt_company(BundleSources(deepcopy(b)),request())
    old=next(x for x in b["facts"] if x["concept"]=="us-gaap:NetIncomeLoss")
    accepted=T+timedelta(days=1)
    b["filings"].append(filing("future",accepted=accepted))
    future=fact(old["concept"],300,start=old["period_start"],end=old["period_end"],
                doc="future",accepted=accepted)
    future.update(future_change) # deliberately leave its original content hash
    b["facts"].append(future)
    a=adapt_company(BundleSources(b),request())
    assert a.company is not None
    assert a.company.facts==baseline.company.facts
    assert a.company.get("net_income_ttm")==18
    assert a.provenance["fact_derivations"]==baseline.provenance["fact_derivations"]
    assert a.provenance["refused"]["fact_available_after_T"]==1
    assert "fact_hash_mismatch" not in a.provenance["refused"]


def test_boolean_price_cannot_be_coerced_through_a_valid_numeric_bar_hash():
    from app.valuation_price_history import bar_content_sha256
    b=source_bundle();bar=b["price_series"]["NASDAQ:XYZ"]["bars"]["2021-06-30"]
    bar["close"]=1.0;bar["bar_sha256"]=bar_content_sha256(bar)
    numeric_hash=bar["bar_sha256"]
    bar["close"]=True
    assert bar_content_sha256(bar)==numeric_hash # canonical helper normalizes bool
    a=adapt_company(BundleSources(b),request())
    assert a.company is None
    assert a.provenance["reason"]=="invalid_number:price"


def test_unclosed_future_price_bar_cannot_invalidate_the_closed_session_at_T():
    b=source_bundle();baseline=adapt_company(BundleSources(deepcopy(b)),request())
    # Only the economic session is needed to establish that this row is outside T.
    b["price_series"]["NASDAQ:XYZ"]["bars"]["wrong-future-key"]={
        "session_date":"2021-07-01","market":"wrong-market","source":"wrong-source",
        "symbol":"wrong-symbol","fetched_at":"2026-10-26T03:00:00+00:00",
        "bar_sha256":"invalid","close":True,
    }
    a=adapt_company(BundleSources(b),request())
    assert a.company==baseline.company
    assert a.provenance==baseline.provenance


def test_backfilled_capture_clock_does_not_replace_regulator_acceptance_clock():
    b=source_bundle()
    for row in b["facts"]:row["first_seen_at"]="2026-10-26T03:00:00+00:00"
    a=adapt_company(BundleSources(b),request())
    assert a.company.get("net_income_ttm")==18
    ref=a.provenance["fact_derivations"]["net_income_ttm"]["rows"][0]
    assert ref["accepted_at"]==ACCEPTED.isoformat()
    assert ref["captured_at"]=="2026-10-26T03:00:00+00:00"


@pytest.mark.parametrize("change,reason", [
    ({"available_at":"2026-10-26T03:00:00+00:00","fetched_at":"2026-10-26T02:00:00+00:00"},"price_publication_after_T"),
    ({"fetched_at":"2026-10-26T02:00:00+00:00"},"price_publication_precedes_capture_without_independent_proof"),
    ({"status":"manifest_mismatch"},"price_series:manifest_mismatch"),
])
def test_historical_economic_price_is_not_retrodated_from_later_capture(change,reason):
    b=source_bundle();b["price_series"]["NASDAQ:XYZ"].update(change)
    a=adapt_company(BundleSources(b),request())
    assert a.company is None and a.provenance["reason"]==reason


def test_hash_corruption_and_ambiguous_latest_facts_do_not_fall_back_to_older_values():
    for corrupt in (True,False):
        b=source_bundle();old=next(x for x in b["facts"] if x["concept"]=="us-gaap:NetIncomeLoss")
        accepted=T-timedelta(hours=3)
        b["filings"].extend([filing("a",accepted=accepted),filing("b",accepted=accepted)])
        a=fact(old["concept"],30,start=old["period_start"],end=old["period_end"],doc="a",accepted=accepted)
        second=fact(old["concept"],40,start=old["period_start"],end=old["period_end"],doc="b",accepted=accepted)
        if corrupt:a["value"]=999 # its content no longer matches the canonical row hash
        b["facts"].extend([a] if corrupt else [a,second])
        result=adapt_company(BundleSources(b),request())
        assert result.company is not None
        assert "net_income_ttm" not in result.company.facts
        assert result.provenance["refused"]["fact_hash_mismatch" if corrupt else "ambiguous_latest_fact"]==1


def test_units_sources_and_quarter_gaps_stay_missing_without_provider_fallback():
    b=source_bundle()
    b["facts"]=[x for x in b["facts"] if not (x["concept"]=="us-gaap:NetIncomeLoss" and x["period_end"]==date(2020,9,30))]
    cash=next(x for x in b["facts"] if x["concept"]=="us-gaap:CashAndCashEquivalentsAtCarryingValue")
    cash["unit"]="BRL";cash["row_hash"]=vintage_row_hash(cash)
    a=adapt_company(BundleSources(b),request())
    assert "net_income_ttm" not in a.company.facts
    assert "cash" not in a.company.facts
    assert a.provenance["refused"]["four_contiguous_quarters_missing:net_income"]==1
    assert a.provenance["refused"]["unit_mismatch:cash"]==1
    b["filings"][0]["accepted_source"]="provider_guess"
    assert adapt_company(BundleSources(b),request()).company is None


def test_symbol_mapping_uses_filings_at_T_and_refuses_ambiguous_issuers():
    b=source_bundle();b["filings"].append(filing("later",issuer="issuer2",accepted=T+timedelta(days=1)))
    assert adapt_company(BundleSources(b),request()).company.issuer_id=="issuer1"
    b["filings"][-1]["accepted_at"]=ACCEPTED
    a=adapt_company(BundleSources(b),request())
    assert a.company is None and a.provenance["reason"]=="symbol_issuer_ambiguous"


def test_cvm_consolidated_accounts_and_net_capital_share_count_are_point_in_time():
    b=dict(schema="VALUATION-ENSEMBLE-SOURCE-EXPORT-v1",filings=[filing(market="B3")],facts=[],
           price_series={"B3:XYZ":series("B3")},consensus_snapshots={})
    values=(("cvm:BPP_con:2.03:Patrimônio Líquido",90,"BRL"),
            ("cvm:BPA_con:1.01.01:Caixa e Equivalentes de Caixa",10,"BRL"),
            ("cvm:composicao_capital:QT_ACAO_TOTAL_CAP_INTEGR",12,"shares"),
            ("cvm:composicao_capital:QT_ACAO_TOTAL_TESOURO",2,"shares"))
    b["facts"]=[fact(c,v,market="B3",unit=u) for c,v,u in values]
    for start,end in ((date(2020,4,1),date(2020,6,30)),(date(2020,7,1),date(2020,9,30)),(date(2020,10,1),date(2020,12,31)),(date(2021,1,1),date(2021,3,31))):
        b["facts"].append(fact("cvm:DRE_con:3.11.01:Atribuído a Sócios da Empresa Controladora",5,start=start,end=end,market="B3",unit="BRL"))
        b["facts"].append(fact("cvm:DRE_ind:3.11.01:Atribuído a Sócios da Empresa Controladora",1000,start=start,end=end,market="B3",unit="BRL"))
    a=adapt_company(BundleSources(b),request("B3"))
    assert a.company is not None
    assert a.company.get("shares")==10
    assert a.company.get("book_equity")==90
    assert a.company.get("net_income_ttm")==20
    assert a.company.facts["book_equity"].evidence.source=="CVM"


def test_consensus_requires_real_horizon_currency_clock_and_source_content_hash():
    b=source_bundle();payload=[dict(analystCompany="house",priceTarget=12,currency="USD",horizon_sessions=252,
                                  publishedDate=(T-timedelta(days=1)).isoformat(),document_id="consensus1")]
    snapshot=dict(id="snap",published_at="2026-10-26T03:00:00+00:00",analysis_type="valuation_pit_source",
                  entity_key="NASDAQ_FMP_TARGETS_"+hashlib.sha256(b"XYZ").hexdigest()[:16],
                  inputs={"payload_sha256":canonical_hash(payload),"fetched_at":"2026-10-26T03:00:00+00:00",
                          "provider":"fmp","market":"NASDAQ","symbol":"XYZ"},
                  outputs={"payload_sha256":canonical_hash(payload),"payload":payload})
    b["consensus_snapshots"]={"NASDAQ:XYZ":snapshot}
    a=adapt_company(BundleSources(b),request());assert len(a.analyst_targets)==1
    assert a.provenance["consensus_capture"]["captured_at"]=="2026-10-26T03:00:00+00:00"
    assert a.analyst_targets[0].evidence.available_at==T-timedelta(days=1)
    payload[0].pop("horizon_sessions");snapshot["inputs"]["payload_sha256"]=snapshot["outputs"]["payload_sha256"]=canonical_hash(payload)
    assert not adapt_company(BundleSources(b),request()).analyst_targets
    payload[0]["horizon_sessions"]=252
    assert not adapt_company(BundleSources(b),request()).analyst_targets # changed payload under its old hash


def test_canonical_consensus_lookup_uses_the_existing_hashed_symbol_key():
    class DatabaseDouble:
        def latest_analysis_snapshot(self,kind,key):
            assert kind=="valuation_pit_source"
            assert key=="NASDAQ_FMP_TARGETS_"+hashlib.sha256(b"XYZ").hexdigest()[:16]
            return None
    assert CanonicalSources(None,None,DatabaseDouble()).consensus_snapshot("NASDAQ","XYZ") is None


def test_durable_execution_is_idempotent_private_and_unchanged_after_reopen(tmp_path):
    directory=tmp_path/"receipts"
    source=BundleSources(source_bundle());store=FileReceiptStore(directory)
    first=execute_shadow(source,request(),premises(),store)
    path=Path(first["receipt_path"]);before=path.read_bytes();stat_before=path.stat()
    second=execute_shadow(source,request(),premises(),FileReceiptStore(directory))
    assert first["created"] and not second["created"]
    assert first["run_key"]==second["run_key"] and path.read_bytes()==before
    assert path.stat().st_mtime_ns==stat_before.st_mtime_ns
    assert path.stat().st_mode&0o777==0o600
    saved=store.read(first["run_key"])
    assert saved["horizon_sessions"] is None and not saved["buy_permission"] and not saved["served_source_changed"]
    assert saved["computation"]["variants"]["median_with_consensus"]["status"]=="not_evaluable"
    assert saved["computation"]["models"][0]["reason"]=="financial_classification_unattested"


def test_concurrent_same_run_commits_one_object_and_integrity_tampering_refuses(tmp_path):
    store=FileReceiptStore(tmp_path/"receipts");s=BundleSources(source_bundle())
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(lambda _:execute_shadow(s,request(),premises(),store),range(3)))
    assert sum(x["created"] for x in results)==1
    assert len(list(store.directory.glob("*.json")))==1
    path=Path(results[0]["receipt_path"]);data=json.loads(path.read_text());data["status"]="tampered";path.write_text(json.dumps(data))
    with pytest.raises(NotEvaluable,match="stored_receipt_integrity_failure"):
        execute_shadow(s,request(),premises(),store)


def test_refusal_receipt_is_durable_and_does_not_erase_an_earlier_success(tmp_path):
    store=FileReceiptStore(tmp_path/"receipts");b=source_bundle()
    first=execute_shadow(BundleSources(b),request(),premises(),store)
    b["price_series"]["NASDAQ:XYZ"]["available_at"]="2026-10-26T03:00:00+00:00"
    refused=execute_shadow(BundleSources(b),request(),premises(),store)
    assert refused["status"]=="not_evaluable" and refused["run_key"]!=first["run_key"]
    assert store.read(first["run_key"])["status"]=="computed"


def test_cli_offline_export_persists_only_private_artifact_and_rejects_horizon(tmp_path,capsys):
    from app.valuation_ensemble_adapters import _jsonable
    files={"source-export":source_bundle(),"request":dict(market="NASDAQ",symbol="XYZ",as_of=T.isoformat(),basis_id="common-as-traded"),
           "premises":dict(policy_id="fixture-policy",scalars={"cost_of_equity":.1})}
    args=[]
    for flag,value in files.items():
        path=tmp_path/(flag+".json");path.write_text(json.dumps(_jsonable(value)));args += ["--"+flag,str(path)]
    args += ["--receipt-directory",str(tmp_path/"receipts")]
    assert main(args)==0
    output=json.loads(capsys.readouterr().out);assert output["status"]=="computed" and "XYZ" not in json.dumps(output)
    path=tmp_path/"request.json";value=json.loads(path.read_text());value["horizon_sessions"]=21;path.write_text(json.dumps(value))
    assert main(args)==2
    assert json.loads(capsys.readouterr().out)["reason"]=="study_or_grid_inputs_not_allowed_in_shadow_construction"


def test_sink_refuses_symlinks_and_nonprivate_directories(tmp_path):
    public=tmp_path/"public";public.mkdir(mode=0o755)
    with pytest.raises(NotEvaluable,match="private_owned_directory"):
        FileReceiptStore(public)
    target=tmp_path/"target";target.mkdir(mode=0o700);link=tmp_path/"linked";link.symlink_to(target,target_is_directory=True)
    with pytest.raises(NotEvaluable,match="private_owned_directory"):
        FileReceiptStore(link)


def test_conflicting_filing_registry_is_not_order_dependent():
    for reverse in (False,True):
        b=source_bundle();duplicate=deepcopy(b["filings"][0]);duplicate["accepted_at"]+=timedelta(days=1)
        b["filings"].append(duplicate)
        if reverse:b["filings"].reverse()
        a=adapt_company(BundleSources(b),request())
        assert a.company is None and a.provenance["reason"]=="official_symbol_issuer_unattested"
        assert a.provenance["refused"]["ambiguous_filing_registry"]==1


def test_price_row_capture_and_session_identity_cannot_bypass_vintage_clock():
    b=source_bundle();bar=b["price_series"]["NASDAQ:XYZ"]["bars"]["2021-06-30"]
    bar["fetched_at"]="2026-10-26T03:00:00+00:00"
    a=adapt_company(BundleSources(b),request())
    assert a.company is None and a.provenance["reason"]=="price_bar_capture_after_vintage"
    b=source_bundle();b["price_series"]["NASDAQ:XYZ"]["bars"]["wrong-key"]=b["price_series"]["NASDAQ:XYZ"]["bars"].pop("2021-06-30")
    a=adapt_company(BundleSources(b),request())
    assert a.company is None and a.provenance["reason"]=="price_session_key_mismatch"


def test_recomputed_payload_digest_cannot_hide_tampering_under_an_existing_run_key(tmp_path):
    store=FileReceiptStore(tmp_path/"receipts");result=execute_shadow(BundleSources(source_bundle()),request(),premises(),store)
    path=Path(result["receipt_path"]);data=json.loads(path.read_text());data["status"]="tampered"
    data["payload_sha256"]=canonical_hash({k:v for k,v in data.items() if k!="payload_sha256"});path.write_text(json.dumps(data))
    with pytest.raises(NotEvaluable,match="stored_receipt_integrity_failure"):
        store.read(result["run_key"])


def test_ytd_flow_facts_are_quarterized_before_the_contiguous_ttm_sum():
    b=source_bundle();b["facts"]=[x for x in b["facts"] if x["concept"]!="us-gaap:NetIncomeLoss"]
    for start,end,value in ((date(2020,1,1),date(2020,3,31),9),(date(2020,1,1),date(2020,6,30),18),
                            (date(2020,1,1),date(2020,9,30),27),(date(2020,1,1),date(2020,12,31),40),
                            (date(2021,1,1),date(2021,3,31),12)):
        b["facts"].append(fact("us-gaap:NetIncomeLoss",value,start=start,end=end))
    a=adapt_company(BundleSources(b),request())
    assert a.company.get("net_income_ttm")==43 # Q2=9,Q3=9,Q4=13,Q1=12; no YTD double count


def test_cvm_receipt_date_cannot_be_turned_into_an_earlier_intraday_availability():
    b=dict(schema="VALUATION-ENSEMBLE-SOURCE-EXPORT-v1",filings=[filing(market="B3")],facts=[],
           price_series={"B3:XYZ":series("B3")},consensus_snapshots={})
    b["filings"][0]["accepted_at"]-=timedelta(hours=12)
    a=adapt_company(BundleSources(b),request("B3"))
    assert a.company is None
    assert a.provenance["refused"]["cvm_acceptance_not_receipt_day_end"]==1
