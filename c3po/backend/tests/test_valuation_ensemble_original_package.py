"""End-to-end offline original reconciliation. Synthetic bytes, no real coverage."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from datetime import timedelta
import json
import os
from pathlib import Path

import pytest

from app.statement_vintages import vintage_row_hash
from app.valuation_ensemble_adapters import BundleSources, CompanyRequest, _jsonable
from app.valuation_ensemble_caller import main, run_shadow_cross_section
from app.valuation_ensemble_inputs import NotEvaluable
from app.valuation_ensemble_originals import extract_cvm_archive, extract_sec_instance
from app.valuation_ensemble_original_store import OriginalEvidenceStore
from app.valuation_ensemble_original_package import OriginalItem, OriginalPackage, load_original_package
from app.valuation_ensemble_persistence import FileReceiptStore
from test_valuation_ensemble_adapters import T, premises, series
from test_valuation_ensemble_originals import header, instance, artifact, cvm_package, sec_filing, CVM_URL


def sec_case():
    extra=[]
    for index,(start,end) in enumerate((("2020-04-01","2020-06-30"),("2020-07-01","2020-09-30"),("2020-10-01","2020-12-31"))):
        extra.append(f'<xbrli:context id="q{index}"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000999001</xbrli:identifier></xbrli:entity>'
            f'<xbrli:period><xbrli:startDate>{start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate></xbrli:period></xbrli:context>')
    extra.append('<xbrli:context id="unclassed"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000999001</xbrli:identifier></xbrli:entity>'
        '<xbrli:period><xbrli:instant>2021-04-25</xbrli:instant></xbrli:period></xbrli:context>')
    for context in ("q0","q1","q2","duration"):
        extra.append(f'<us-gaap:NetCashProvidedByUsedInOperatingActivities contextRef="{context}" unitRef="USD" decimals="0">5</us-gaap:NetCashProvidedByUsedInOperatingActivities>')
    extra.append('<dei:EntityCommonStockSharesOutstanding contextRef="unclassed" unitRef="shares" decimals="0">1000</dei:EntityCommonStockSharesOutstanding>')
    h=header();x=instance(lambda s:s.replace('</xbrli:xbrl>',"".join(extra)+'</xbrli:xbrl>'))
    extracted=extract_sec_instance(x,h);rows=[]
    for fact in extracted["facts"]:
        if not fact["numeric"] or fact["context"]["dimensions"]:continue
        row={"market":"US","issuer_key":extracted["issuer_key"],"doc_id":extracted["doc_id"],"document_version":1,
            "source":"sec_xbrl_companyfacts","form":extracted["form"],"filed_date":extracted["filed_date"],"accepted_at":extracted["accepted_at"],
            "concept":fact["concept"],"unit":fact["unit"],"value":Decimal(fact["value"]),
            "period_start":fact["context"]["period_start"],"period_end":fact["context"]["period_end"]}
        row["row_hash"]=vintage_row_hash(row);rows.append(row)
    filing=sec_filing();filing["symbols"]=["XYZ"]
    b={"schema":"VALUATION-ENSEMBLE-SOURCE-EXPORT-v1","filings":[filing],"facts":rows,
       "price_series":{"NASDAQ:XYZ":series()},"consensus_snapshots":{}}
    package=OriginalPackage((OriginalItem("header",h),OriginalItem("instance",x,"header")))
    return b,package,CompanyRequest("NASDAQ","XYZ",T,"declared-common")


def run_case(tmp_path,b,package,requests,*,sources=None):
    store=FileReceiptStore(tmp_path/"receipts");originals=OriginalEvidenceStore(tmp_path/"originals")
    result=run_shadow_cross_section(sources or BundleSources(b),tuple(requests),premises(),store,
        reader_kind="offline_export",original_package=package,original_store=originals)
    saved=store.read(result["run_key"])
    companies=[store.read(x["run_key"]) for x in saved["company_receipts"]]
    return store,originals,result,saved,companies


def test_complete_original_content_is_reconciled_by_line_document_field_and_model_without_admissibility(tmp_path):
    b,package,request=sec_case()
    _,originals,result,saved,companies=run_case(tmp_path,b,package,(request,replace(request,symbol="MISSING")))
    company=next(x for x in companies if x["adaptation"]["symbol"]=="XYZ")
    reconciliation=company["original_reconciliation"]
    assert reconciliation["observed_fact_rows"]==6
    assert all(x["original"]["checked_content_equal"] for x in reconciliation["row_ledger"])
    assert all(x["original"]["checked_content_equal"] for x in reconciliation["document_ledger"])
    assert len(reconciliation["fields"]["operating_cash_flow_ttm"]["canonical_row_ids"])==4
    metric=saved["input_inventory"]["models"]["capitalized_operating_cash_flow"]
    assert metric["requested"]==2 and metric["computable"]==1
    assert metric["all_required_input_bytes_available"]==1 and metric["all_required_checked_content_equal"]==1
    assert metric["admissible"]==0 and result["admissible_model_observations"]==0
    assert "original_document_authentication:supplied_package_has_no_authenticated_official_origin" in company["historical_admissibility"]["blocking_proofs"]
    for entry in saved["original_package"]["artifacts"]:
        manifest=originals.read_manifest(entry["manifest_run_key"])
        assert manifest["payload_sha256"]==entry["manifest_payload_sha256"]
        assert not manifest["historical_admissibility"]


def test_divergent_canonical_value_keeps_bytes_present_but_fails_content_completeness(tmp_path):
    b,package,request=sec_case()
    row=next(x for x in b["facts"] if x["concept"]=="us-gaap:NetCashProvidedByUsedInOperatingActivities")
    row["value"]=Decimal(6);row["row_hash"]=vintage_row_hash(row)
    _,_,_,saved,companies=run_case(tmp_path,b,package,(request,))
    metric=saved["input_inventory"]["models"]["capitalized_operating_cash_flow"]
    assert metric["computable"]==1 and metric["all_required_input_bytes_available"]==1
    assert metric["all_required_checked_content_equal"]==0 and metric["admissible"]==0
    unequal=[x for x in companies[0]["original_reconciliation"]["row_ledger"] if not x["original"]["checked_content_equal"]]
    assert len(unequal)==1 and unequal[0]["original"]["bytes_available"]


def test_corrupt_original_is_a_counted_refusal_and_does_not_drop_requested_companies(tmp_path):
    b,package,request=sec_case();h,x=package.items
    package=OriginalPackage((h,replace(x,artifact=replace(x.artifact,expected_sha256="0"*64))))
    _,_,_,saved,companies=run_case(tmp_path,b,package,(request,replace(request,symbol="MISSING")))
    assert saved["original_package"]["artifact_refusals"]=={"original_bytes_digest_mismatch":1}
    metric=saved["input_inventory"]["models"]["capitalized_operating_cash_flow"]
    assert metric["requested"]==2 and metric["computable"]==1
    assert metric["all_required_input_bytes_available"]==0 and metric["admissible"]==0
    assert companies[0]["input_audit"]["models"]["capitalized_operating_cash_flow"]["required_facts"]


def test_conflicting_document_roles_cannot_choose_the_favorable_original(tmp_path):
    b,package,request=sec_case();h,x=package.items
    changed=x.artifact.payload.replace(b'>5</us-gaap:NetCash',b'>50</us-gaap:NetCash')
    bad=artifact("sec_xbrl_instance",x.artifact.source_url,changed)
    package=OriginalPackage((*package.items,OriginalItem("other_instance",bad,"header")))
    _,_,_,saved,_=run_case(tmp_path,b,package,(request,))
    assert saved["original_package"]["artifact_refusals"]=={"original_document_role_ambiguous":2}
    metric=saved["input_inventory"]["models"]["capitalized_operating_cash_flow"]
    assert metric["computable"]==1 and metric["all_required_checked_content_equal"]==0


def test_different_refused_bytes_have_distinct_receipts_even_with_the_same_declared_digest(tmp_path):
    b,package,request=sec_case();h,x=package.items
    bad=OriginalPackage((h,replace(x,artifact=replace(x.artifact,expected_sha256="0"*64))))
    store,originals,first,first_saved,_=run_case(tmp_path,b,bad,(request,))
    changed=x.artifact.payload+b"\n"
    other=OriginalPackage((h,replace(x,artifact=replace(x.artifact,payload=changed,expected_sha256="0"*64))))
    second=run_shadow_cross_section(BundleSources(b),(request,),premises(),store,reader_kind="offline_export",
        original_package=other,original_store=originals)
    saved=store.read(second["run_key"])
    assert first["run_key"]!=second["run_key"]
    before=next(x for x in first_saved["original_package"]["artifacts"] if x["status"]=="refused")
    after=next(x for x in saved["original_package"]["artifacts"] if x["status"]=="refused")
    assert before["actual_supplied_sha256"]!=after["actual_supplied_sha256"]
    assert before["reason"]==after["reason"]=="original_bytes_digest_mismatch"


def test_reconciliation_uses_observed_reader_copies_not_a_later_source_reread(tmp_path):
    b,package,request=sec_case()
    class ChangingSources(BundleSources):
        calls=0
        def facts(self,*args):
            self.calls+=1
            return super().facts(*args)
        def price_series(self,*args):
            for row in self.bundle["facts"]:row["value"]=Decimal(999)
            return super().price_series(*args)
    sources=ChangingSources(b)
    _,_,_,saved,companies=run_case(tmp_path,b,package,(request,),sources=sources)
    assert sources.calls==1 and all(x["value"]==999 for x in b["facts"])
    assert saved["input_inventory"]["models"]["capitalized_operating_cash_flow"]["all_required_checked_content_equal"]==1
    ledger=companies[0]["original_reconciliation"]["row_ledger"]
    assert any(x["canonical_row"]["value"]=="5" for x in ledger)


def test_price_refusal_preserves_factual_byte_and_content_reconciliation(tmp_path):
    b,package,request=sec_case();b["price_series"]["NASDAQ:XYZ"]={"status":"no_vintage"}
    _,_,_,saved,_=run_case(tmp_path,b,package,(request,))
    metric=saved["input_inventory"]["models"]["capitalized_operating_cash_flow"]
    assert metric["computable"]==0 and metric["all_required_checked_content_equal"]==1
    assert metric["missing_or_ineligible_facts"]=={} and metric["unobserved_facts"]=={}


def test_future_registry_version_cannot_poison_content_of_the_document_version_used_at_T(tmp_path):
    b,package,request=sec_case();future=deepcopy(b["filings"][0])
    future["document_version"]=2;future["accepted_at"]=T+timedelta(days=1)
    b["filings"].append(future)
    _,_,_,saved,companies=run_case(tmp_path,b,package,(request,))
    assert saved["input_inventory"]["models"]["capitalized_operating_cash_flow"]["all_required_checked_content_equal"]==1
    ledger=companies[0]["original_reconciliation"]["document_ledger"]
    assert len(ledger)==2 and any(not x["original"]["checked_content_equal"] for x in ledger)


def test_cvm_combined_share_field_requires_both_original_capital_components(tmp_path):
    p=cvm_package();doc=p.index[0]["ID_DOC"];raw=artifact("cvm_archive",CVM_URL,p.payload())
    extracted=extract_cvm_archive(raw,document_ids=(doc,));filing=deepcopy(extracted["documents"][0])
    filing.update(market="B3",source="cvm_dados_abertos",symbols=["XYZ"])
    facts=[]
    for value in extracted["facts"]:
        row={key:value[key] for key in ("issuer_key","doc_id","document_version","form","filed_date","accepted_at","concept","unit","value","period_start","period_end")}
        row.update(market="B3",source="cvm_dados_abertos");row["row_hash"]=vintage_row_hash(row);facts.append(row)
    b={"schema":"VALUATION-ENSEMBLE-SOURCE-EXPORT-v1","filings":[filing],"facts":facts,
       "price_series":{"B3:XYZ":series("B3")},"consensus_snapshots":{}}
    package=OriginalPackage((OriginalItem("cvm",raw,document_ids=(doc,)),))
    _,_,_,saved,companies=run_case(tmp_path,b,package,(CompanyRequest("B3","XYZ",T,"declared-basis"),))
    shares=companies[0]["original_reconciliation"]["fields"]["shares"]
    assert len(shares["canonical_row_ids"])==2 and shares["all_checked_content_equal"]
    assert saved["input_inventory"]["models"]["price_book"]["all_required_checked_content_equal"]==1
    assert saved["input_inventory"]["models"]["price_book"]["admissible"]==0


def test_original_package_and_cross_section_replay_are_immutable_and_order_independent(tmp_path):
    b,package,request=sec_case();store,originals,first,_,_=run_case(tmp_path,b,package,(request,))
    bytes_before=Path(first["receipt_path"]).read_bytes();objects_before={p.name:p.read_bytes() for p in originals.objects.iterdir()}
    second=run_shadow_cross_section(BundleSources(b),(request,),premises(),store,reader_kind="offline_export",
        original_package=OriginalPackage(tuple(reversed(package.items))),original_store=originals)
    assert first["run_key"]==second["run_key"] and not second["created"]
    assert Path(first["receipt_path"]).read_bytes()==bytes_before
    assert objects_before=={p.name:p.read_bytes() for p in originals.objects.iterdir()}


def _write_package(tmp_path,package):
    specs=[]
    for item in package.items:
        filename=item.artifact_id+".bin";(tmp_path/filename).write_bytes(item.artifact.payload)
        spec={"artifact_id":item.artifact_id,"kind":item.artifact.kind,"source_url":item.artifact.source_url,
            "captured_at":item.artifact.captured_at.isoformat(),"expected_sha256":item.artifact.expected_sha256,"local_file":filename}
        if item.header_id is not None:spec["header_id"]=item.header_id
        if item.document_ids is not None:spec["document_ids"]=list(item.document_ids)
        specs.append(spec)
    path=tmp_path/"package.json";path.write_text(json.dumps({"schema":"VALUATION-ENSEMBLE-ORIGINAL-PACKAGE-v1","artifacts":specs}))
    return path


def test_cli_explicit_package_reconciles_and_rejects_trust_flags_or_path_traversal(tmp_path,capsys):
    b,package,request=sec_case();path=_write_package(tmp_path,package)
    files={"source-export":b,"requests":{"schema":"VALUATION-ENSEMBLE-CROSS-SECTION-REQUEST-v1",
        "requests":[{"market":request.market,"symbol":request.symbol,"as_of":request.as_of.isoformat(),"basis_id":request.basis_id}]},
        "premises":{"policy_id":"fixture-design","scalars":{"cost_of_equity":.1}}};args=[]
    for flag,value in files.items():
        p=tmp_path/(flag+".json");p.write_text(json.dumps(_jsonable(value)));args += ["--"+flag,str(p)]
    args += ["--receipt-directory",str(tmp_path/"receipts"),"--original-package",str(path),"--original-receipt-directory",str(tmp_path/"originals")]
    assert main(args)==0
    output=capsys.readouterr().out;result=json.loads(output)
    assert "XYZ" not in output and str(tmp_path) not in output and result["admissible_model_observations"]==0
    spec=json.loads(path.read_text());spec["artifacts"][0]["origin_authenticated"]=True;path.write_text(json.dumps(spec))
    assert main(args)==2
    assert json.loads(capsys.readouterr().out)["reason"]=="original_package_artifact_fields_not_supported_no_trust_flags"
    spec["artifacts"][0].pop("origin_authenticated");spec["artifacts"][0]["local_file"]="../outside.bin";path.write_text(json.dumps(spec))
    with pytest.raises(NotEvaluable,match="adjacent_regular_filenames"):load_original_package(path)


def test_explicit_package_requires_its_own_store_and_duplicate_ids_fail_before_reading(tmp_path):
    b,package,request=sec_case()
    class NoRead:
        def __getattr__(self,name):pytest.fail("unexpected read: "+name)
    store=FileReceiptStore(tmp_path/"receipts")
    with pytest.raises(NotEvaluable,match="required_together"):
        run_shadow_cross_section(NoRead(),(request,),premises(),store,reader_kind="offline_export",original_package=package)
    originals=OriginalEvidenceStore(tmp_path/"originals");duplicate=OriginalPackage((package.items[0],package.items[0]))
    with pytest.raises(NotEvaluable,match="artifact_ids_missing_or_duplicate"):
        run_shadow_cross_section(NoRead(),(request,),premises(),store,reader_kind="offline_export",original_package=duplicate,original_store=originals)
    assert not list(store.directory.glob("*.json")) and not list(originals.objects.iterdir())


def test_package_loader_refuses_nonregular_payloads_without_waiting_on_a_fifo(tmp_path):
    _,package,_=sec_case();path=_write_package(tmp_path,package)
    target=tmp_path/"header.bin";target.unlink();os.mkfifo(target)
    with pytest.raises(NotEvaluable,match="requires_regular_files"):load_original_package(path)
