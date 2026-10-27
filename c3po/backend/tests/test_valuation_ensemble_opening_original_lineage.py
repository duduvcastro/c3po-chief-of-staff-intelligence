"""RI literal original lineage using synthetic bytes only, never economic proof."""
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
import re
import socket

import pytest

from app.statement_vintages import vintage_row_hash
from app.valuation_ensemble_adapters import BundleSources
from app.valuation_ensemble_caller import run_shadow_cross_section
from app.valuation_ensemble_capture import CaptureRequest, OfficialCaptureClient, read_capture_receipt
from app.valuation_ensemble_original_package import (CaptureReference, OriginalItem, OriginalPackage,
    _opening_literal_pair)
from app.valuation_ensemble_original_store import OriginalEvidenceStore
from app.valuation_ensemble_originals import extract_sec_instance, extract_cvm_archive
from app.valuation_ensemble_persistence import FileReceiptStore
from app.valuation_ensemble_adapters import CompanyRequest
from test_valuation_ensemble_adapters import premises, series, T
from test_valuation_ensemble_beginning_book import DIRECT, YTD
from test_valuation_ensemble_original_package import sec_case
from test_valuation_ensemble_originals import artifact, CVM_URL
from test_valuation_ensemble_capture import Clock, Transport, Response, CONTACT, limits
from cvm_statement_fixtures import Package, INDUSTRY, _flow, _point


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def fail(*args,**kwargs):pytest.fail("no real network in original-lineage fixtures")
    monkeypatch.setattr(socket,"socket",fail);monkeypatch.setattr(socket,"create_connection",fail)


def sec_income_case(spans=DIRECT,*,alias="NetIncomeLoss",duplicate=False):
    bundle,package,target=sec_case();header,item=package.items
    text=re.sub(r'<us-gaap:NetIncomeLoss\b.*?</us-gaap:NetIncomeLoss>',"",item.artifact.payload.decode())
    extra=[]
    for index,(start,end,value) in enumerate(spans):
        name=f"income{index}"
        extra.append(f'<xbrli:context id="{name}"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000999001</xbrli:identifier></xbrli:entity>'
            f'<xbrli:period><xbrli:startDate>{start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate></xbrli:period></xbrli:context>'
            f'<us-gaap:{alias} contextRef="{name}" unitRef="USD" decimals="0">{value}</us-gaap:{alias}>')
    for name,instant,value in (("opening","2020-03-31",80),("closing","2021-03-31",90)):
        extra.append(f'<xbrli:context id="{name}"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000999001</xbrli:identifier></xbrli:entity>'
            f'<xbrli:period><xbrli:instant>{instant}</xbrli:instant></xbrli:period></xbrli:context>'
            f'<us-gaap:StockholdersEquity contextRef="{name}" unitRef="USD" decimals="0">{value}</us-gaap:StockholdersEquity>')
    if duplicate:
        extra.append(extra[-2].replace('id="opening"','id="opening-copy"').replace('contextRef="opening"','contextRef="opening-copy"'))
    original=artifact("sec_xbrl_instance",item.artifact.source_url,text.replace('</xbrli:xbrl>',"".join(extra)+'</xbrli:xbrl>').encode())
    extracted=extract_sec_instance(original,header.artifact);rows=[]
    for value in extracted["facts"]:
        if not value["numeric"] or value["context"]["dimensions"]:continue
        row={"market":"US","issuer_key":extracted["issuer_key"],"doc_id":extracted["doc_id"],"document_version":1,
            "source":"sec_xbrl_companyfacts","form":extracted["form"],"filed_date":extracted["filed_date"],"accepted_at":extracted["accepted_at"],
            "concept":value["concept"],"unit":value["unit"],"value":Decimal(value["value"]),
            "period_start":value["context"]["period_start"],"period_end":value["context"]["period_end"]}
        row["row_hash"]=vintage_row_hash(row);rows.append(row)
    # The source can collapse duplicate raw occurrences to one canonical row.
    bundle["facts"]=list({x["row_hash"]:x for x in rows}.values())
    return bundle,OriginalPackage((header,replace(item,artifact=original))),target


def run_case(tmp_path,bundle,package,target,*,captures=None,sources=None,sink=None):
    store=FileReceiptStore(tmp_path/"receipts");sink=sink or OriginalEvidenceStore(tmp_path/"originals")
    result=run_shadow_cross_section(sources or BundleSources(bundle),(target,replace(target,symbol="MISSING")),premises(),store,
        reader_kind="offline_export",original_package=package,original_store=sink if package else None,capture_store=captures)
    saved=store.read(result["run_key"])
    company=next(store.read(x["run_key"]) for x in saved["company_receipts"] if x["symbol"]==target.symbol)
    literal=company["original_reconciliation"]["beginning_book_observation"]["literal_original_observation"]
    assert all(x["requested"]==2 and x["admissible"]==0 for x in saved["input_inventory"]["models"].values())
    assert "book_equity_beginning" not in company["computation"]["inputs"]["facts"]
    assert not literal["model_fact_emitted"] and not literal["used_in_computation"] and not literal["historical_admissibility"]
    assert literal["scope_class_basis_comparability"]=="unattested"
    return saved,company,literal


@pytest.mark.parametrize("spans,expected,raw_count,canceled",[(DIRECT,18,4,0),(YTD,43,5,2)])
def test_direct_and_derived_terms_link_actual_originals_including_cancellations(tmp_path,spans,expected,raw_count,canceled):
    bundle,package,target=sec_income_case(spans)
    saved,company,literal=run_case(tmp_path,bundle,package,target)
    candidate=literal["candidate_original_link"];terms=literal["consumed_income_raw_terms_including_cancellations"]
    assert candidate["status"]=="observed_unique" and len(terms)==raw_count
    assert sum(x["coefficient"]==0 for x in terms)==canceled
    assert company["computation"]["inputs"]["facts"]["net_income_ttm"]["value"]==expected
    for term in terms:
        link=term["original_link"];assert link["status"]=="observed_unique" and term["selected_quarter_occurrences"]
        occurrence=link["original_occurrence"];assert occurrence["artifact_id"]=="instance"
        assert occurrence["observation"]["original_fact_sha256"] and occurrence["manifest_payload_sha256"] and occurrence["object_sha256"]
        axes=term["literal_observations"]
        assert axes["issuer"]["status"]==axes["normalized_unit"]["status"]==axes["explicit_dimensions"]["status"]=="literal_equal"
        assert axes["reported_statement_scope_label"]["status"]=="unavailable"
        assert axes["class"]["status"]==axes["share_basis"]["status"]==axes["scope_class_basis_comparability"]=="unattested"
        assert occurrence["observation"]["context_id"]!=candidate["original_occurrence"]["observation"]["context_id"]
    metric=saved["input_inventory"]["models"]["residual_income"]
    assert metric["opening_original_link_statuses"]=={"observed_unique":1,"unavailable":1}
    assert metric["income_raw_term_denominator_including_cancellations"]==raw_count
    assert metric["income_raw_term_original_link_statuses"]=={"observed_unique":raw_count}
    assert metric["beginning_book_facts_consumed"]==0


@pytest.mark.parametrize("where",["candidate","canceled_income"])
@pytest.mark.parametrize("metadata",[{"symbols":["CURRENT-ONLY"]},{"first_seen_at":"2021-05-03T20:30:00+00:00"},{"id":77}])
def test_partial_reference_never_selects_one_of_two_distinct_full_rows(tmp_path,where,metadata):
    bundle,package,target=sec_income_case(YTD)
    source=next(x for x in bundle["facts"] if x["concept"]==("us-gaap:StockholdersEquity" if where=="candidate" else "us-gaap:NetIncomeLoss")
        and x["period_end"]==("2020-03-31" if where=="candidate" else "2020-06-30"))
    duplicate={**source,**metadata};assert duplicate["row_hash"]==vintage_row_hash(duplicate)
    bundle["facts"].append(duplicate)
    _,_,literal=run_case(tmp_path,bundle,package,target)
    link=literal["candidate_original_link"] if where=="candidate" else next(x["original_link"] for x in
        literal["consumed_income_raw_terms_including_cancellations"] if x["coefficient"]==0 and x["row_reference"]["period_end"]=="2020-06-30")
    assert link["status"]=="ambiguous" and link["reason"]=="canonical_reference_matches_multiple_full_rows"
    assert len(link["canonical_row_ids"])==2 and link["original_occurrence"] is None


@pytest.mark.parametrize("route",["no_package","duplicate_original","bad_digest","duplicate_artifact","missing_canceled_original"])
def test_missing_ambiguous_or_refused_originals_remain_explicit_without_dropping_companies(tmp_path,route):
    bundle,package,target=sec_income_case(YTD,duplicate=route=="duplicate_original")
    if route=="no_package":package=None
    elif route=="bad_digest":package=OriginalPackage((package.items[0],replace(package.items[1],artifact=replace(package.items[1].artifact,expected_sha256="0"*64))))
    elif route=="duplicate_artifact":package=OriginalPackage((*package.items,replace(package.items[1],artifact_id="instance-copy")))
    elif route=="missing_canceled_original":
        item=package.items[1];payload=re.sub(rb'<us-gaap:NetIncomeLoss contextRef="income1".*?</us-gaap:NetIncomeLoss>',b"",item.artifact.payload)
        package=OriginalPackage((package.items[0],replace(item,artifact=artifact(item.artifact.kind,item.artifact.source_url,payload))))
    saved,company,literal=run_case(tmp_path,bundle,package,target)
    assert company["computation"]["inputs"]["facts"]["net_income_ttm"]["value"]==43
    link=literal["candidate_original_link"] if route!="missing_canceled_original" else next(x["original_link"] for x in
        literal["consumed_income_raw_terms_including_cancellations"] if x["coefficient"]==0 and x["row_reference"]["period_end"]=="2020-06-30")
    assert link["status"]=="unavailable" and link["reason"]
    assert not link.get("original_occurrence") or link["original_occurrence"]["observation"]["status"]=="unavailable"
    assert saved["input_inventory"]["models"]["residual_income"]["income_raw_term_denominator_including_cancellations"]==5


@pytest.mark.parametrize("alias",["NetIncomeLossAvailableToCommonStockholdersBasic","ProfitLoss"])
def test_selected_income_alias_is_visible_but_never_attests_scope_equivalence(tmp_path,alias):
    bundle,package,target=sec_income_case(alias=alias)
    _,_,literal=run_case(tmp_path,bundle,package,target)
    assert len(literal["consumed_income_raw_terms_including_cancellations"])==4
    for term in literal["consumed_income_raw_terms_including_cancellations"]:
        concepts=term["literal_observations"]["reported_concepts"]
        assert concepts["income"]=="us-gaap:"+alias and concepts["candidate"]=="us-gaap:StockholdersEquity"
        assert concepts["equivalence"]=="not_established_by_alias_selection"


def test_cvm_literal_con_label_and_raw_account_identity_do_not_prove_controller_equity_scope(tmp_path):
    package=Package("itr",2021);package.document(INDUSTRY,"2021-03-31",1,"2021-05-03")
    for start,end,value in DIRECT:package.add("DRE","con",_flow(INDUSTRY,"2021-03-31",1,"ÚLTIMO",start,end,
        [("3.11.01","Atribuído a Sócios da Empresa Controladora",value)]))
    for end,value in (("2020-03-31",80),("2021-03-31",90)):
        package.add("BPP","con",_point(INDUSTRY,"2021-03-31",1,"ÚLTIMO",end,[("2.03","Patrimônio Líquido Consolidado",value)]))
    package.capital(INDUSTRY,"2021-03-31",1,100,10)
    original=artifact("cvm_archive",CVM_URL,package.payload());extracted=extract_cvm_archive(original);filings=[];rows=[]
    for doc in extracted["documents"]:
        filings.append({"market":"B3","source":"cvm_dados_abertos","symbols":["XYZ3"],"accepted_source":"cvm_dt_receb_end_of_day",**doc})
    for value in extracted["facts"]:
        row={key:value[key] for key in ("issuer_key","doc_id","document_version","form","filed_date","accepted_at","concept","unit","period_start","period_end","value")}
        row.update(market="B3",source="cvm_dados_abertos");row["row_hash"]=vintage_row_hash(row);rows.append(row)
    bundle={"schema":"VALUATION-ENSEMBLE-SOURCE-EXPORT-v1","filings":filings,"facts":rows,"price_series":{"B3:XYZ3":series("B3","XYZ3")},"consensus_snapshots":{}}
    target=CompanyRequest("B3","XYZ3",T,"caller-declared")
    _,_,literal=run_case(tmp_path,bundle,OriginalPackage((OriginalItem("cvm",original),)),target)
    assert len(literal["consumed_income_raw_terms_including_cancellations"])==4
    for term in literal["consumed_income_raw_terms_including_cancellations"]:
        axes=term["literal_observations"];assert axes["reported_statement_scope_label"]=={"candidate":"con","income":"con","status":"literal_equal"}
        value=term["original_link"]["original_occurrence"]["observation"]
        assert value["entry"].endswith("DRE_con_2021.csv") and value["raw_row_sha256"] and value["raw_row"]["CD_CONTA"]=="3.11.01"
        assert axes["scope_class_basis_comparability"]=="unattested"


def test_literal_mismatch_does_not_require_equal_document_or_context_identifiers():
    def link(**fields):return {"status":"observed_unique","original_occurrence":{"observation":fields}}
    left=link(issuer_key="A",unit="USD",concept="cvm:BPP_con:2.03:PL",context_id="opening",doc_id="old")
    right=link(issuer_key="B",unit="BRL",concept="cvm:DRE_ind:3.11:NI",context_id="duration",doc_id="new")
    result=_opening_literal_pair(left,right)
    assert all(result[axis]["status"]=="literal_mismatch" for axis in ("issuer","normalized_unit","reported_statement_scope_label"))
    assert result["explicit_dimensions"]["status"]=="unavailable" and result["scope_class_basis_comparability"]=="unattested"


def test_existing_source_snapshot_and_manifest_read_counts_are_preserved(tmp_path):
    bundle,package,target=sec_income_case()
    class CountingSources(BundleSources):
        calls=0
        def facts(self,*args):self.calls+=1;return super().facts(*args)
        def price_series(self,*args):
            for row in self.bundle["facts"]:row["symbols"]=["MUTATED-AFTER-READ"]
            return super().price_series(*args)
    class CountingStore(OriginalEvidenceStore):
        reads=0
        def read_manifest(self,*args):self.reads+=1;return super().read_manifest(*args)
    sources=CountingSources(bundle);sink=CountingStore(tmp_path/"originals")
    _,company,literal=run_case(tmp_path,bundle,package,target,sources=sources,sink=sink)
    assert sources.calls==1 and sink.reads==2
    assert literal["candidate_original_link"]["status"]=="observed_unique"
    assert not any("symbols" in row["canonical_row"] for row in company["original_reconciliation"]["row_ledger"])


@pytest.mark.parametrize("refuse",[False,True])
def test_injected_and_refused_capture_evidence_stays_specific_to_bound_original(tmp_path,refuse):
    bundle,package,target=sec_income_case();captures=OriginalEvidenceStore(tmp_path/"captures");clock=Clock()
    client=OfficialCaptureClient(Transport([Response(x.artifact.payload) for x in package.items],clock),
        limits(max_response_bytes=32768,max_total_body_bytes=65536),user_agent=CONTACT,clock=clock)
    items=[]
    for item in package.items:
        captured=client.capture(CaptureRequest(item.artifact.kind,item.artifact.source_url,"0"*64 if refuse and item.artifact.kind=="sec_xbrl_instance" else None),captures)
        receipt=read_capture_receipt(captures,captured["run_key"])
        items.append(replace(item,artifact=replace(item.artifact,captured_at=datetime.fromisoformat(receipt["body_received_at"])),
            capture=CaptureReference(captured["run_key"],captured["payload_sha256"])))
    _,_,literal=run_case(tmp_path,bundle,OriginalPackage(tuple(items)),target,captures=captures)
    link=literal["candidate_original_link"]
    if refuse:assert link["status"]=="unavailable"
    else:
        assert link["status"]=="observed_unique"
        provenance=link["original_occurrence"]["capture_provenance"]
        assert provenance["all_required_links_verified"]
        assert provenance["capture"]["recorded_transport_execution"]=="injected_transport_not_source_authentication"


def test_new_observation_never_suppresses_persistence_failures(tmp_path,monkeypatch):
    bundle,package,target=sec_income_case();store=FileReceiptStore(tmp_path/"receipts")
    def fail(*args):raise OSError("synthetic persistence failure")
    monkeypatch.setattr(store,"put",fail)
    with pytest.raises(OSError,match="synthetic persistence failure"):
        run_shadow_cross_section(BundleSources(bundle),(target,),premises(),store,reader_kind="offline_export",
            original_package=package,original_store=OriginalEvidenceStore(tmp_path/"originals"))
