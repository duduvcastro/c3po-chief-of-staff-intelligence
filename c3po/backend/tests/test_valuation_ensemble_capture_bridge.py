"""Offline bridge of synthetic capture evidence into exact consumed observations."""
from dataclasses import replace
from datetime import datetime, timedelta
import json
from pathlib import Path

import pytest

from app.valuation_ensemble_adapters import BundleSources, _jsonable
from app.valuation_ensemble_capture import CaptureRequest, OfficialCaptureClient, read_capture_receipt
from app.valuation_ensemble_caller import main, run_shadow_cross_section
from app.valuation_ensemble_inputs import NotEvaluable, canonical_hash
from app.valuation_ensemble_original_package import CaptureReference, OriginalItem, OriginalPackage, load_original_package
from app.valuation_ensemble_original_store import OriginalEvidenceStore
from app.valuation_ensemble_persistence import FileReceiptStore
from test_valuation_ensemble_adapters import premises
from test_valuation_ensemble_capture import Clock, Transport, Response, CONTACT, limits
from test_valuation_ensemble_original_package import sec_case, _write_package


@pytest.fixture(autouse=True)
def forbid_real_https_connections(monkeypatch):
    def fail(*args,**kwargs):pytest.fail("bridge tests must never open an HTTPS connection")
    monkeypatch.setattr("app.valuation_ensemble_capture.http.client.HTTPSConnection",fail)


def captured_package(tmp_path,*,capture_store=None,headers=()):
    bundle,package,request=sec_case();clock=Clock()
    transport=Transport([Response(item.artifact.payload,headers=headers) for item in package.items],clock)
    client=OfficialCaptureClient(transport,limits(max_response_bytes=16384,max_total_body_bytes=32768),user_agent=CONTACT,clock=clock)
    captures=capture_store or OriginalEvidenceStore(tmp_path/"captures");items=[]
    for item in package.items:
        result=client.capture(CaptureRequest(item.artifact.kind,item.artifact.source_url),captures)
        receipt=read_capture_receipt(captures,result["run_key"])
        artifact=replace(item.artifact,captured_at=datetime.fromisoformat(receipt["body_received_at"]))
        items.append(replace(item,artifact=artifact,capture=CaptureReference(result["run_key"],result["payload_sha256"])))
    return bundle,OriginalPackage(tuple(items)),request,captures


def run_case(tmp_path,bundle,package,request,captures,*,store=None,originals=None,sources=None):
    store=store or FileReceiptStore(tmp_path/"receipts");originals=originals or OriginalEvidenceStore(tmp_path/"originals")
    result=run_shadow_cross_section(sources or BundleSources(bundle),(request,replace(request,symbol="MISSING")),premises(),store,
        reader_kind="offline_export",original_package=package,original_store=originals,capture_store=captures)
    saved=store.read(result["run_key"]);companies=[store.read(x["run_key"]) for x in saved["company_receipts"]]
    company=next(x for x in companies if x["adaptation"]["symbol"]==request.symbol)
    return result,saved,company,store,originals


def replace_instance_reference(package,reference):
    return OriginalPackage(tuple(replace(x,capture=reference) if x.artifact.kind=="sec_xbrl_instance" else x for x in package.items))


def test_capture_refs_follow_consumed_rows_documents_ttm_fields_and_models_without_promoting_origin(tmp_path):
    bundle,package,request,captures=captured_package(tmp_path)
    result,saved,company,_,_=run_case(tmp_path,bundle,package,request,captures)
    metric=saved["input_inventory"]["models"]["capitalized_operating_cash_flow"]
    assert metric["requested"]==2 and metric["computable"]==metric["all_required_capture_links_verified"]==1
    assert metric["admissible"]==result["admissible_model_observations"]==0
    field=company["original_reconciliation"]["fields"]["operating_cash_flow_ttm"]
    assert len(field["canonical_row_ids"])==4 and field["all_capture_links_verified"]
    cell=company["input_audit"]["models"]["capitalized_operating_cash_flow"]["original_evidence"]
    assert cell["capture_references"]["operating_cash_flow_ttm"]==field["capture_references"]
    for row in company["original_reconciliation"]["row_ledger"]:
        assert row["original"]["capture_linked_content_equal"]
        for ref in row["original"]["capture_references"]:
            for link in (ref["capture"],ref["header_capture"]):
                if link is not None:
                    assert link["recorded_transport_execution"]=="injected_transport_not_source_authentication"
                    assert link["body_received_at"].startswith("2026-10-26")
                    assert not link["historical_admissibility"]
    assert not company["historical_admissibility"]["admissible"]


def test_missing_header_capture_does_not_complete_an_instance_or_ttm_provenance_chain(tmp_path):
    bundle,package,request,captures=captured_package(tmp_path)
    package=OriginalPackage(tuple(replace(x,capture=None) if x.artifact.kind=="sec_header" else x for x in package.items))
    _,saved,company,_,_=run_case(tmp_path,bundle,package,request,captures)
    metric=saved["input_inventory"]["models"]["capitalized_operating_cash_flow"]
    assert metric["all_required_checked_content_equal"]==1 and metric["all_required_capture_links_verified"]==0
    assert any("capture_reference_not_supplied" in reason for reason in metric["missing_or_refused_capture_links"])
    assert not company["original_reconciliation"]["fields"]["operating_cash_flow_ttm"]["all_capture_links_verified"]


def test_refused_complete_body_capture_cannot_reuse_an_object_from_another_successful_capture(tmp_path):
    bundle,package,request,captures=captured_package(tmp_path);instance=package.items[1]
    clock=Clock();client=OfficialCaptureClient(Transport([Response(instance.artifact.payload)],clock),
        limits(max_response_bytes=16384,max_total_body_bytes=32768),user_agent=CONTACT,clock=clock)
    result=client.capture(CaptureRequest(instance.artifact.kind,instance.artifact.source_url,"0"*64),captures)
    refused=read_capture_receipt(captures,result["run_key"])
    assert refused["status"]=="refused" and refused["body_complete"]
    assert captures.read_bytes(refused["observed_body_sha256"])==instance.artifact.payload
    package=replace_instance_reference(package,CaptureReference(result["run_key"],result["payload_sha256"]))
    _,saved,company,_,_=run_case(tmp_path,bundle,package,request,captures)
    reason="capture_reference_refused:capture_expected_digest_mismatch"
    assert saved["original_package"]["artifact_refusals"]=={reason:1}
    metric=saved["input_inventory"]["models"]["capitalized_operating_cash_flow"]
    assert metric["requested"]==2 and metric["computable"]==1 and metric["all_required_capture_links_verified"]==0
    row=next(x for x in company["original_reconciliation"]["row_ledger"] if x["used_by_fields"])
    assert reason in row["original"]["capture_link_reasons"]
    assert any(reason in key for key in metric["missing_or_refused_capture_links"])


@pytest.mark.parametrize("failure,reason",[("payload","capture_reference_payload_mismatch"),
    ("missing_receipt","capture_reference_receipt_not_found"),("corrupt_object","stored_original_bytes_digest_mismatch"),
    ("missing_object","capture_reference_object_not_found"),("capture_clock","capture_reference_artifact_metadata_mismatch")])
def test_divergent_reference_object_or_capture_clock_is_counted_for_the_actual_document_and_rows(tmp_path,failure,reason):
    bundle,package,request,captures=captured_package(tmp_path);instance=package.items[1]
    if failure=="payload":package=replace_instance_reference(package,replace(instance.capture,payload_sha256="0"*64))
    elif failure=="missing_receipt":package=replace_instance_reference(package,replace(instance.capture,run_key="f"*64))
    elif failure in {"corrupt_object","missing_object"}:
        path=captures.objects/(instance.artifact.expected_sha256+".bin")
        if failure=="corrupt_object":path.write_bytes(b"different-content")
        else:path.unlink()
    else:
        package=OriginalPackage((package.items[0],replace(instance,artifact=replace(instance.artifact,captured_at=instance.artifact.captured_at+timedelta(seconds=1)))))
    _,saved,company,_,_=run_case(tmp_path,bundle,package,request,captures)
    assert saved["original_package"]["artifact_refusals"]=={reason:1}
    metric=saved["input_inventory"]["models"]["capitalized_operating_cash_flow"]
    assert metric["requested"]==2 and metric["all_required_capture_links_verified"]==0
    assert any(reason in key for key in metric["missing_or_refused_capture_links"])
    assert any(reason in row["original"]["capture_link_reasons"] for row in company["original_reconciliation"]["row_ledger"])


def test_source_uri_binding_uses_final_uri_instead_of_http_date_or_claimed_source_name(tmp_path):
    bundle,package,request,captures=captured_package(tmp_path);instance=package.items[1]
    other=instance.artifact.source_url.rsplit("/",1)[0]+"/other-native.xml";clock=Clock()
    client=OfficialCaptureClient(Transport([Response(instance.artifact.payload,headers=(("Date","Mon, 03 May 2021 20:30:00 GMT"),))],clock),
        limits(max_response_bytes=16384,max_total_body_bytes=32768),user_agent=CONTACT,clock=clock)
    result=client.capture(CaptureRequest(instance.artifact.kind,other),captures)
    package=replace_instance_reference(package,CaptureReference(result["run_key"],result["payload_sha256"]))
    _,saved,_,_,_=run_case(tmp_path,bundle,package,request,captures)
    assert saved["original_package"]["artifact_refusals"]=={"capture_reference_artifact_metadata_mismatch":1}


@pytest.mark.parametrize("change,reason",[("attempt_clock","capture_receipt_object_or_clock_mismatch"),
    ("origin_flag","capture_receipt_contract_mismatch")])
def test_rehashed_supplied_receipt_cannot_waive_observation_clock_or_origin_contract(tmp_path,change,reason):
    bundle,package,request,captures=captured_package(tmp_path);instance=package.items[1]
    receipt=read_capture_receipt(captures,instance.capture.run_key)
    forged={k:v for k,v in receipt.items() if k not in {"run_key","payload_sha256"}}
    if change=="attempt_clock":forged["attempts"][0]["started_at"]=(datetime.fromisoformat(forged["finished_at"])+timedelta(seconds=1)).isoformat()
    else:forged["origin_authentication"]="authenticated_by_supplied_flag"
    forged["run_key"]=canonical_hash(forged);forged["payload_sha256"]=canonical_hash(forged);captures.manifests.put(forged)
    package=replace_instance_reference(package,CaptureReference(forged["run_key"],forged["payload_sha256"]))
    _,saved,_,_,_=run_case(tmp_path,bundle,package,request,captures)
    assert saved["original_package"]["artifact_refusals"]=={reason:1}
    assert all(x["admissible"]==0 for x in saved["input_inventory"]["models"].values())


def test_same_bytes_from_distinct_capture_observations_get_distinct_cross_section_receipts(tmp_path):
    bundle,first,request,captures=captured_package(tmp_path,headers=(("ETag","first"),))
    result,saved,_,store,originals=run_case(tmp_path,bundle,first,request,captures)
    _,other,_,_=captured_package(tmp_path,capture_store=captures,headers=(("ETag","second"),))
    assert all(x.artifact==y.artifact for x,y in zip(first.items,other.items))
    second,second_saved,_,_,_=run_case(tmp_path,bundle,other,request,captures,store=store,originals=originals)
    assert result["run_key"]!=second["run_key"]
    left=saved["original_package"]["artifacts"];right=second_saved["original_package"]["artifacts"]
    assert all(x["metadata_and_bytes_input_sha256"]!=y["metadata_and_bytes_input_sha256"] for x,y in zip(left,right))
    replay=run_shadow_cross_section(BundleSources(bundle),(replace(request,symbol="MISSING"),request),premises(),store,
        reader_kind="offline_export",original_package=OriginalPackage(tuple(reversed(other.items))),original_store=originals,capture_store=captures)
    assert replay["run_key"]==second["run_key"] and not replay["created"]


def test_capture_store_is_explicit_before_canonical_reads_and_persistence_failures_propagate(tmp_path,monkeypatch):
    bundle,package,request,captures=captured_package(tmp_path)
    class NoRead:
        def __getattr__(self,name):pytest.fail("unexpected canonical read: "+name)
    store=FileReceiptStore(tmp_path/"receipts");originals=OriginalEvidenceStore(tmp_path/"originals")
    with pytest.raises(NotEvaluable,match="capture_references_and_explicit_private_store_required_together"):
        run_shadow_cross_section(NoRead(),(request,),premises(),store,reader_kind="offline_export",original_package=package,original_store=originals)
    def disk_failure(original):raise OSError("synthetic_disk_failure")
    monkeypatch.setattr(originals,"_put_bytes",disk_failure)
    with pytest.raises(OSError,match="synthetic_disk_failure"):
        run_case(tmp_path,bundle,package,request,captures,store=store,originals=originals)


def test_cli_opt_in_capture_directory_links_existing_offline_receipts_without_capture(tmp_path,capsys):
    bundle,package,request,captures=captured_package(tmp_path);path=_write_package(tmp_path,package)
    packet=json.loads(path.read_text())
    for value,item in zip(packet["artifacts"],package.items):
        value.update(capture_run_key=item.capture.run_key,capture_payload_sha256=item.capture.payload_sha256)
    path.write_text(json.dumps(packet));args=[]
    inputs={"source-export":bundle,"requests":{"schema":"VALUATION-ENSEMBLE-CROSS-SECTION-REQUEST-v1",
        "requests":[{"market":request.market,"symbol":request.symbol,"as_of":request.as_of.isoformat(),"basis_id":request.basis_id}]},
        "premises":{"policy_id":"synthetic-policy","scalars":{"cost_of_equity":.1}}}
    for flag,value in inputs.items():
        file=tmp_path/(flag+".json");file.write_text(json.dumps(_jsonable(value)));args.extend(("--"+flag,str(file)))
    args.extend(("--receipt-directory",str(tmp_path/"receipts"),"--original-package",str(path),"--original-receipt-directory",str(tmp_path/"originals"),
        "--capture-receipt-directory",str(captures.manifests.directory)))
    assert main(args)==0
    stdout=capsys.readouterr().out
    assert CONTACT not in stdout and str(tmp_path) not in stdout and request.symbol not in stdout
    packet["artifacts"][0].pop("capture_payload_sha256");path.write_text(json.dumps(packet))
    with pytest.raises(NotEvaluable,match="capture_reference_pair_required"):load_original_package(path)
