"""Synthetic source bytes in supported layouts; no real originals or coverage claim."""
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import html
import io
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import zipfile

import pytest

from app.statement_vintages import vintage_row_hash
from app.valuation_ensemble_inputs import NotEvaluable
from app.valuation_ensemble_originals import (SourceBytes, bind_canonical_rows, extract_cvm_archive,
    extract_sec_header, extract_sec_instance)
from app.valuation_ensemble_original_store import OriginalEvidenceStore, ingest_supplied_original
from cvm_statement_fixtures import Package, INDUSTRY, _point


CIK="0000999001"
ACC="0000999001-21-000005"
CAPTURE=datetime(2026,10,26,5,tzinfo=timezone.utc)
ACCEPTED=datetime(2021,5,3,20,30,tzinfo=timezone.utc)
HEADER_URL=f"https://www.sec.gov/Archives/edgar/data/999001/{ACC}-index-headers.html"
INSTANCE_URL=f"https://www.sec.gov/Archives/edgar/data/999001/{ACC.replace('-','')}/synthetic-20210331.xml"
CVM_URL="https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr_cia_aberta_2021.zip"


def artifact(kind,url,payload):
    return SourceBytes(kind,url,CAPTURE,hashlib.sha256(payload).hexdigest(),payload)


def header(body_change=""):
    text=f"""<SEC-HEADER>{ACC}.hdr.sgml : 20210503
<ACCEPTANCE-DATETIME>20210503163000
ACCESSION NUMBER: {ACC}
CONFORMED SUBMISSION TYPE: 10-Q
CONFORMED PERIOD OF REPORT: 20210331
FILED AS OF DATE: 20210503
FILER:
    COMPANY DATA:
        CENTRAL INDEX KEY: {CIK}
        STANDARD INDUSTRIAL CLASSIFICATION: SYNTHETIC MANUFACTURING [3999]
{body_change}
</SEC-HEADER>"""
    return artifact("sec_header",HEADER_URL,("<html><pre>"+html.escape(text)+"</pre></html>").encode())


def instance(change=None):
    text=f"""<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
 xmlns:iso4217="http://www.xbrl.org/2003/iso4217" xmlns:dei="http://xbrl.sec.gov/dei/2021q4"
 xmlns:us-gaap="http://fasb.org/us-gaap/2021-01-31" xmlns:syn="https://synthetic.invalid/2021">
 <xbrli:context id="duration"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">{CIK}</xbrli:identifier></xbrli:entity>
  <xbrli:period><xbrli:startDate>2021-01-01</xbrli:startDate><xbrli:endDate>2021-03-31</xbrli:endDate></xbrli:period></xbrli:context>
 <xbrli:context id="classA"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">{CIK}</xbrli:identifier>
  <xbrli:segment><xbrldi:explicitMember dimension="dei:StatementClassOfStockAxis">syn:ClassAMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity>
  <xbrli:period><xbrli:instant>2021-04-25</xbrli:instant></xbrli:period></xbrli:context>
 <xbrli:context id="classB"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">{CIK}</xbrli:identifier>
  <xbrli:segment><xbrldi:explicitMember dimension="dei:StatementClassOfStockAxis">syn:ClassBMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity>
  <xbrli:period><xbrli:instant>2021-04-25</xbrli:instant></xbrli:period></xbrli:context>
 <xbrli:unit id="USD"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
 <xbrli:unit id="shares"><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unit>
 <us-gaap:NetIncomeLoss contextRef="duration" unitRef="USD" decimals="0">18</us-gaap:NetIncomeLoss>
 <dei:EntityCommonStockSharesOutstanding contextRef="classA" unitRef="shares" decimals="0">900</dei:EntityCommonStockSharesOutstanding>
 <dei:EntityCommonStockSharesOutstanding contextRef="classB" unitRef="shares" decimals="0">100</dei:EntityCommonStockSharesOutstanding>
 <dei:TradingSymbol contextRef="classA">SYNA</dei:TradingSymbol><dei:Security12bTitle contextRef="classA">Class A Common Stock</dei:Security12bTitle>
 <dei:SecurityExchangeName contextRef="classA">NASDAQ</dei:SecurityExchangeName>
 <dei:TradingSymbol contextRef="classB">SYNB</dei:TradingSymbol><dei:Security12bTitle contextRef="classB">Class B Common Stock</dei:Security12bTitle>
</xbrli:xbrl>"""
    if change:text=change(text)
    return artifact("sec_xbrl_instance",INSTANCE_URL,text.encode())


def sec_filing():
    return dict(market="US",issuer_key=CIK,doc_id=ACC,document_version=1,source="sec_edgar",form="10-Q",
        filed_date=date(2021,5,3),period_of_report=date(2021,3,31),accepted_at=ACCEPTED,accepted_source="sec_header",
        header_sha256=header().expected_sha256,symbols=["CURRENT-MAP-ONLY"])


def sec_fact(**changes):
    row=dict(market="US",issuer_key=CIK,doc_id=ACC,document_version=1,source="sec_xbrl_companyfacts",form="10-Q",
        filed_date=date(2021,5,3),accepted_at=ACCEPTED,period_start=date(2021,1,1),period_end=date(2021,3,31),
        concept="us-gaap:NetIncomeLoss",unit="USD",value=Decimal(18))
    row.update(changes);row["row_hash"]=vintage_row_hash(row)
    return row


def cvm_package():
    p=Package("itr",2021);p.document(INDUSTRY,"2021-03-31",1,"2021-05-03")
    p.document(INDUSTRY,"2021-03-31",2,"2021-06-01")
    p.add("BPP","con",_point(INDUSTRY,"2021-03-31",1,"ÚLTIMO","2021-03-31",[("2.03","Patrimônio Líquido Consolidado",90)]))
    p.add("BPP","con",_point(INDUSTRY,"2021-03-31",2,"ÚLTIMO","2021-03-31",[("2.03","Patrimônio Líquido Consolidado",150)]))
    p.capital(INDUSTRY,"2021-03-31",1,100,10)
    return p


def test_sec_header_binds_actual_byte_hash_and_acceptance_without_classification_or_origin_claim():
    original=header();out=extract_sec_header(original)
    assert out["issuer_key"]==CIK and out["doc_id"]==ACC
    assert out["accepted_at"]==ACCEPTED.isoformat()
    assert out["artifact"]["captured_at"]==CAPTURE.isoformat()
    assert out["sic"]=={"raw":"SYNTHETIC MANUFACTURING [3999]","code":"3999","classification_policy_applied":False}
    assert out["artifact"]["origin_authentication"]=="unverified_supplied_bytes"
    assert not out["instrument_validity_or_class_or_action_basis_proven"]


@pytest.mark.parametrize("change,reason",[
    ({"payload":b"changed"},"original_bytes_digest_mismatch"),
    ({"source_url":HEADER_URL.replace("www.sec.gov","sec.gov.attacker.invalid")},"original_sec_url_not_supported"),
    ({"source_url":HEADER_URL.replace("999001/","999002/")},"sec_header_url_identity_mismatch"),
    ({"source_url":HEADER_URL+"?next=evil"},"original_source_url_invalid"),
    ({"captured_at":datetime(2026,10,26)},"instant_without_timezone"),
    ({"payload":bytearray(b"bytes")},"original_bytes_size_or_type"),
])
def test_original_artifact_integrity_identity_and_capture_contracts_are_checked(change,reason):
    with pytest.raises(NotEvaluable,match=reason):extract_sec_header(replace(header(),**change))


def test_header_refuses_multiple_filer_identities_or_conflicting_acceptance_clocks():
    with pytest.raises(NotEvaluable,match="original_missing_or_ambiguous:CIK"):
        extract_sec_header(header("CENTRAL INDEX KEY: 0000999002"))
    with pytest.raises(NotEvaluable,match="original_missing_or_ambiguous:acceptance"):
        extract_sec_header(header("<ACCEPTANCE-DATETIME>20210504163000"))


def test_native_sec_contexts_and_classes_are_preserved_without_summing_or_cross_joining_cover_tuples():
    out=extract_sec_instance(instance(),header())
    assert out["header_artifact"]["sha256"]==header().expected_sha256
    shares=[x for x in out["facts"] if x["concept"]=="dei:EntityCommonStockSharesOutstanding"]
    assert {x["value"] for x in shares}=={"900","100"}
    assert {x["context_id"] for x in shares}=={"classA","classB"}
    assert all(x["context"]["dimensions"] for x in shares)
    a,b=out["cover_securities"]
    assert a["TradingSymbol"]=="SYNA" and a["complete_same_context_security_tuple"]
    assert b["TradingSymbol"]=="SYNB" and not b["complete_same_context_security_tuple"]
    assert b["SecurityExchangeName"] is None # never borrow A's NASDAQ observation
    assert not out["historical_admissibility"]


@pytest.mark.parametrize("change,reason",[
    (lambda s:s.replace(CIK,"0000999002"),"original_context_identity_missing_conflicting_or_wrong_CIK"),
    (lambda s:s.replace('id="classB"','id="classA"'),"original_context_identity_missing_conflicting_or_wrong_CIK"),
    (lambda s:s.replace('contextRef="duration"','contextRef="absent"'),"original_fact_context_missing_or_nested_content"),
    (lambda s:s.replace("<xbrli:xbrl",'<!DOCTYPE bad [<!ENTITY x SYSTEM "file:///secret">]><xbrli:xbrl',1),"original_xml_dtd_or_entity_not_allowed"),
    (lambda s:s.replace("<xbrli:instant>2021-04-25</xbrli:instant>","<xbrli:instant>2021-04-25</xbrli:instant><xbrli:instant>2020-01-01</xbrli:instant>"),"original_context_period_missing_or_ambiguous"),
    (lambda s:s.replace('unitRef="USD"','unitRef="USD" scale="3"'),"native_instance_numeric_transformation_not_supported"),
])
def test_sec_instance_rejects_ambiguous_identity_contexts_and_external_entities(change,reason):
    with pytest.raises(NotEvaluable,match=reason):extract_sec_instance(instance(change),header())


def test_canonical_sec_rows_bind_only_exact_supported_original_fields_and_never_collapsed_classes():
    out=extract_sec_instance(instance(),header())
    shares=sec_fact(concept="dei:EntityCommonStockSharesOutstanding",value=1000,unit="shares",period_start=None,period_end=date(2021,4,25))
    corrupt=sec_fact();corrupt["value"]=999
    rows=bind_canonical_rows(out,filings=[sec_filing()],facts=[sec_fact(),shares,corrupt,sec_fact(value=19),sec_fact(issuer_key="bad")])
    assert rows["matched"]==2 and rows["not_bound"]==4
    assert rows["rows"][0]["symbols_not_authenticated"]
    assert rows["rows"][2]["status"]=="not_bound" # 900+100 is not an original unclassed1000 fact
    assert rows["rows"][3]["reason"]=="canonical_fact_hash_mismatch"
    assert not rows["historical_admissibility"]
    assert "fiscal_year" in rows["unproven_row_fields"]


def test_non_dimensional_scenario_and_boolean_document_version_cannot_bind_as_plain_facts():
    changed=instance(lambda s:s.replace('</xbrli:endDate></xbrli:period></xbrli:context>',
        '</xbrli:endDate></xbrli:period><xbrli:scenario><syn:UnmodeledScope>subsidiary</syn:UnmodeledScope></xbrli:scenario></xbrli:context>',1))
    out=extract_sec_instance(changed,header())
    assert out["contexts"]["duration"]["unsupported_context_content_present"]
    assert bind_canonical_rows(out,facts=[sec_fact()])["not_bound"]==1
    out=extract_sec_instance(instance(),header());row=sec_fact(document_version=True)
    assert bind_canonical_rows(out,facts=[row])["not_bound"]==1


def test_explicit_instance_identity_cannot_disagree_with_the_separately_verified_header():
    bad=instance(lambda s:s.replace('</xbrli:xbrl>',
        '<dei:EntityCentralIndexKey contextRef="duration">0000999002</dei:EntityCentralIndexKey></xbrli:xbrl>'))
    with pytest.raises(NotEvaluable,match="original_instance_header_identity_disagreement:EntityCentralIndexKey"):
        extract_sec_instance(bad,header())


def test_cvm_bytes_preserve_official_document_version_clock_scaling_and_class_counts():
    package=cvm_package();doc=package.index[0]["ID_DOC"]
    out=extract_cvm_archive(artifact("cvm_archive",CVM_URL,package.payload()),document_ids=(doc,))
    assert len(out["documents"])==1 and out["documents"][0]["document_version"]==1
    assert out["documents"][0]["accepted_at"]=="2021-05-04T02:59:59.999999+00:00"
    assert out["artifact"]["captured_at"]==CAPTURE.isoformat()
    equity=next(x for x in out["facts"] if x["concept"].startswith("cvm:BPP_con:2.03:"))
    assert Decimal(equity["value"])==Decimal(90000) and equity["unit"]=="BRL"
    assert "entry" in equity and "raw_row_sha256" in equity
    capital={x["concept"].split(":")[-1]:Decimal(x["value"]) for x in out["facts"] if "composicao_capital" in x["concept"]}
    assert capital["QT_ACAO_ORDIN_CAP_INTEGR"]==100 and capital["QT_ACAO_PREF_CAP_INTEGR"]==0
    assert capital["QT_ACAO_TOTAL_TESOURO"]==10
    assert not out["historical_admissibility"]


def test_cvm_canonical_filing_and_values_bind_to_original_entry_and_row_without_current_ticker_proof():
    package=cvm_package();doc=package.index[0]["ID_DOC"]
    out=extract_cvm_archive(artifact("cvm_archive",CVM_URL,package.payload()),document_ids=(doc,))
    original=out["documents"][0]
    filing={key:original[key] for key in ("issuer_key","doc_id","document_version","form","accepted_at","filed_date","period_of_report","accepted_source")}
    filing.update(market="B3",source="cvm_dados_abertos",symbols=["TICKER-FROM-CURRENT-MAP"])
    raw=next(x for x in out["facts"] if x["concept"].startswith("cvm:BPP_con:2.03:"))
    row={key:raw[key] for key in ("issuer_key","doc_id","document_version","form","accepted_at","filed_date","concept","unit","value","period_start","period_end")}
    row.update(market="B3",source="cvm_dados_abertos");row["row_hash"]=vintage_row_hash(row)
    result=bind_canonical_rows(out,filings=[filing],facts=[row])
    assert result["matched"]==2 and result["not_bound"]==0
    assert result["rows"][0]["symbols_not_authenticated"]


def test_cvm_archive_rejects_ambiguous_document_index_and_unsafe_members():
    package=cvm_package();conflict=deepcopy(package.index[0]);conflict["ID_DOC"]="different-id";package.index.append(conflict)
    with pytest.raises(NotEvaluable,match="original_cvm_document_index_ambiguous"):
        extract_cvm_archive(artifact("cvm_archive",CVM_URL,package.payload()))
    for name in ("../escape.csv","nested/file.csv"):
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,"w") as archive:archive.writestr(name,b"nothing")
        with pytest.raises(NotEvaluable,match="original_archive_member_unsafe_or_duplicate"):
            extract_cvm_archive(artifact("cvm_archive",CVM_URL,buffer.getvalue()))


def test_missing_cvm_index_or_requested_document_is_a_refusal_not_a_guessed_clock():
    p=cvm_package();original=artifact("cvm_archive",CVM_URL,p.payload())
    with pytest.raises(NotEvaluable,match="requested_cvm_original_document_not_found"):
        extract_cvm_archive(original,document_ids=("unknown",))
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,"w") as archive:archive.writestr("other.csv",b"nothing")
    with pytest.raises(NotEvaluable,match="original_cvm_document_index_missing"):
        extract_cvm_archive(artifact("cvm_archive",CVM_URL,buffer.getvalue()))


def test_original_bytes_and_manifest_are_private_durable_idempotent_and_never_origin_authenticated(tmp_path):
    store=OriginalEvidenceStore(tmp_path/"originals")
    result=ingest_supplied_original(instance(),store,header=header(),filings=[sec_filing()],facts=[sec_fact()])
    before=Path(result["manifest_path"]).read_bytes();stamp=Path(result["manifest_path"]).stat().st_mtime_ns
    again=ingest_supplied_original(instance(),OriginalEvidenceStore(store.manifests.directory),header=header(),filings=[sec_filing()],facts=[sec_fact()])
    assert result["run_key"]==again["run_key"] and not again["created"]
    assert Path(result["manifest_path"]).read_bytes()==before and Path(result["manifest_path"]).stat().st_mtime_ns==stamp
    manifest=store.read_manifest(result["run_key"])
    assert manifest["origin_authentication"]=="unverified_supplied_bytes" and not manifest["historical_admissibility"]
    assert not manifest["buy_permission"] and not manifest["served_source_changed"]
    assert store.read_bytes(header().expected_sha256)==header().payload
    assert store.read_bytes(instance().expected_sha256)==instance().payload
    assert all(p.stat().st_mode&0o777==0o600 for p in store.objects.iterdir())


def test_concurrent_ingestion_deduplicates_bytes_and_detects_existing_object_corruption(tmp_path):
    store=OriginalEvidenceStore(tmp_path/"originals")
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(lambda _:ingest_supplied_original(header(),store),range(3)))
    assert sum(x["created"] for x in results)==1 and len(list(store.objects.iterdir()))==1
    target=next(store.objects.iterdir());target.write_bytes(b"corrupt")
    with pytest.raises(NotEvaluable,match="stored_original_bytes_digest_mismatch"):
        store.read_manifest(results[0]["run_key"])
    with pytest.raises(NotEvaluable,match="stored_original_bytes_digest_mismatch"):
        ingest_supplied_original(header(),store)
    assert target.read_bytes()==b"corrupt" # never overwrite under an existing digest


def test_sec_instance_cannot_ingest_from_a_header_digest_or_trust_boolean_only(tmp_path):
    store=OriginalEvidenceStore(tmp_path/"originals")
    with pytest.raises(NotEvaluable,match="sec_instance_requires_original_header_bytes"):
        ingest_supplied_original(instance(),store)
    with pytest.raises(TypeError):
        ingest_supplied_original(header(),store,origin_authenticated=True)
    assert not list(store.objects.iterdir()) and not list(store.manifests.directory.glob("*.json"))


def test_offline_original_ingestion_never_constructs_a_client_or_database(monkeypatch,tmp_path):
    from app.database import Database
    from app.sec_xbrl import SecXbrlClient
    import httpx
    def forbidden(*args,**kwargs):pytest.fail("original ingestion opened an operational dependency")
    monkeypatch.setattr(Database,"__init__",forbidden)
    monkeypatch.setattr(SecXbrlClient,"__init__",forbidden)
    monkeypatch.setattr(httpx.Client,"send",forbidden)
    store=OriginalEvidenceStore(tmp_path/"originals")
    assert not ingest_supplied_original(instance(),store,header=header())["historical_admissibility"]
