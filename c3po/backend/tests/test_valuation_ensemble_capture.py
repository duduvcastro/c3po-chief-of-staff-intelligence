"""Synthetic transport only: no SEC/CVM socket, capture, historical coverage or trust."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import ssl
from unittest.mock import Mock

import pytest

from app.valuation_ensemble_capture import (CaptureLimits, CaptureRequest, HTTPSOfficialTransport,
    OfficialCaptureClient, read_capture_receipt)
from app.valuation_ensemble_inputs import NotEvaluable
from app.valuation_ensemble_originals import SourceBytes
from app.valuation_ensemble_original_store import OriginalEvidenceStore, ingest_supplied_original
from test_valuation_ensemble_originals import HEADER_URL, INSTANCE_URL, CVM_URL, header, cvm_package


CONTACT="SyntheticClient fixture-contact@example.invalid"
WALL=datetime(2026,10,26,7,tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def forbid_real_https_connections(monkeypatch):
    def no_socket(*args,**kwargs):pytest.fail("construction tests must never open a real HTTPS connection")
    monkeypatch.setattr("app.valuation_ensemble_capture.http.client.HTTPSConnection",no_socket)


class Clock:
    def __init__(self):self.elapsed=0.;self.wall_adjustment=0.
    def now(self):return WALL+timedelta(seconds=self.elapsed+self.wall_adjustment)
    def monotonic(self):return 100.+self.elapsed
    def advance(self,seconds):self.elapsed+=seconds


class Response:
    def __init__(self, body=b"synthetic-official-bytes", *, status=200, headers=(), clock=None, read_delay=0., failure_after=None):
        self.body=body;self.status=status;self.headers=tuple(headers);self.offset=0;self.closed=False
        self.clock=clock;self.read_delay=read_delay;self.failure_after=failure_after;self.reads=[]
    def read(self,size,timeout):
        self.reads.append((size,timeout))
        if self.clock:self.clock.advance(self.read_delay)
        if self.failure_after is not None and self.offset>=self.failure_after:raise OSError("secret-diagnostic-never-in-receipt")
        end=min(self.offset+size,len(self.body))
        if self.failure_after is not None:end=min(end,self.failure_after)
        chunk=self.body[self.offset:end];self.offset=end;return chunk
    def close(self):self.closed=True


class Transport:
    def __init__(self,responses,clock,latency=.2):self.responses=list(responses);self.clock=clock;self.calls=[];self.latency=latency
    def open(self,uri,user_agent,timeout):
        self.calls.append((uri,user_agent,timeout));self.clock.advance(self.latency)
        response=self.responses.pop(0)
        if isinstance(response,Exception):raise response
        return response


def limits(**changes):
    return replace(CaptureLimits("synthetic-policy",4,.1,1024,4096,2.,10.,2),**changes)


def setup(tmp_path,responses,*,policy=None,user_agent=CONTACT,latency=.2):
    clock=Clock();transport=Transport(responses,clock,latency)
    client=OfficialCaptureClient(transport,policy or limits(),user_agent=user_agent,clock=clock)
    return client,transport,clock,OriginalEvidenceStore(tmp_path/"capture")


def capture(client,store,request=None):
    result=client.capture(request or CaptureRequest("sec_header",HEADER_URL),store)
    receipt=read_capture_receipt(store,result["run_key"])
    assert receipt is not None and receipt["payload_sha256"]==result["payload_sha256"]
    return result,receipt


@pytest.mark.parametrize("kind,uri",[("sec_header",HEADER_URL),("sec_xbrl_instance",INSTANCE_URL),("cvm_archive",CVM_URL)])
def test_capture_records_observed_bytes_and_separate_clocks_without_source_authentication(tmp_path,kind,uri):
    raw=b"synthetic-body";response=Response(raw,headers=(("Content-Length",str(len(raw))),("Date","Mon, 03 May 2021 20:30:00 GMT"),
        ("Last-Modified","Mon, 03 May 2021 19:00:00 GMT"),("ETag","private-opaque-etag"),("Set-Cookie","private-cookie")))
    client,transport,clock,store=setup(tmp_path,[response])
    result,receipt=capture(client,store,CaptureRequest(kind,uri,hashlib.sha256(raw).hexdigest()))
    assert result["status"]=="captured" and receipt["body_complete"] and response.closed
    assert store.read_bytes(receipt["object_sha256"][0])==raw
    assert receipt["observed_body_sha256"]==hashlib.sha256(raw).hexdigest() and receipt["observed_body_bytes"]==len(raw)
    assert receipt["started_at"]==WALL.isoformat() and receipt["finished_at"]==clock.now().isoformat()
    assert receipt["body_received_at"]==clock.now().isoformat()
    assert receipt["attempts"][0]["server_date_metadata_only"].startswith("2021-05-03")
    assert receipt["transport_execution"]=="injected_transport_not_source_authentication"
    assert receipt["original_layout_status"]=="not_validated_transport_bytes_only"
    assert not receipt["historical_admissibility"] and not receipt["operator_identity_or_global_quota_attested"]
    assert not receipt["buy_permission"] and not receipt["served_source_changed"]
    text=json.dumps(receipt)
    assert all(secret not in text for secret in (CONTACT,"private-cookie","private-opaque-etag"))
    assert "tls_observation" not in receipt["attempts"][0]
    assert transport.calls[0][1]==CONTACT and 0<transport.calls[0][2]<=2
    assert all(0<size<=65536 and 0<timeout<=2 for size,timeout in response.reads)
    assert all(p.stat().st_mode&0o777==0o600 for p in store.objects.iterdir())
    assert Path(result["receipt_path"]).stat().st_mode&0o777==0o600


@pytest.mark.parametrize("uri",[
    HEADER_URL.replace("https:","http:"),HEADER_URL.replace("www.sec.gov","www.sec.gov.invalid"),
    HEADER_URL.replace("https://","https://user:secret@"),HEADER_URL+"?token=secret",HEADER_URL+"#secret",
    HEADER_URL.replace("www.sec.gov","www.sec.gov:443"),HEADER_URL.replace("/Archives/","/%41rchives/"),
    HEADER_URL.replace("/Archives/","/../Archives/"),"https://data.sec.gov/api/xbrl/companyfacts/CIK0000999001.json",
    "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/itr_cia_aberta_2021.zip",
])
def test_unsupported_or_credentialed_uri_fails_before_transport_or_receipt(tmp_path,uri):
    client,transport,_,store=setup(tmp_path,[])
    with pytest.raises(NotEvaluable,match="capture_uri_not_supported"):
        client.capture(CaptureRequest("sec_header",uri),store)
    assert not transport.calls and not list(store.manifests.directory.glob("*.json"))


@pytest.mark.parametrize("agent",[None,"","\r\nAuthorization: secret","Contact não ASCII"])
def test_missing_or_malformed_operator_identity_is_closed_without_inventing_contact(tmp_path,agent):
    client,transport,_,store=setup(tmp_path,[],user_agent=agent)
    with pytest.raises(NotEvaluable,match="explicit_operator_user_agent_required"):
        client.capture(CaptureRequest("sec_header",HEADER_URL),store)
    assert not transport.calls


@pytest.mark.parametrize("changes",[{"max_requests":True},{"minimum_interval_seconds":.09},{"max_response_bytes":0},
    {"max_total_body_bytes":0},{"max_redirects":-1},{"timeout_seconds":float("nan")},{"max_elapsed_seconds":0}])
def test_limits_are_required_and_sec_client_floor_cannot_claim_global_quota(tmp_path,changes):
    client,transport,_,store=setup(tmp_path,[],policy=limits(**changes))
    with pytest.raises(NotEvaluable):client.capture(CaptureRequest("sec_header",HEADER_URL),store)
    assert not transport.calls


def test_sec_accession_submitter_prefix_need_not_equal_issuer_path_cik(tmp_path):
    uri=HEADER_URL.replace("0000999001-21-000005","0000888002-21-000005")
    client,_,_,store=setup(tmp_path,[Response()])
    _,receipt=capture(client,store,CaptureRequest("sec_header",uri))
    assert receipt["status"]=="captured" # Content/header identity is a separate parser contract.


def test_manual_same_identity_redirects_reserve_each_request_and_keep_the_chain(tmp_path):
    first=Response(status=302,headers=(("Location","redirected.xml"),))
    second=Response(b"redirected-bytes")
    client,transport,_,store=setup(tmp_path,[first,second])
    _,receipt=capture(client,store,CaptureRequest("sec_xbrl_instance",INSTANCE_URL))
    final=INSTANCE_URL.rsplit("/",1)[0]+"/redirected.xml"
    assert receipt["status"]=="captured" and receipt["final_uri"]==final
    assert [x[0] for x in transport.calls]==[INSTANCE_URL,final] and receipt["client_requests_used"]==2
    assert receipt["attempts"][0]["body_not_read"] and not first.reads
    assert first.closed and second.closed


@pytest.mark.parametrize("target",["https://attacker.invalid/private?secret=hidden","http://www.sec.gov/Archives/nope",
    "https://user:secret@www.sec.gov/Archives/nope",INSTANCE_URL.replace("999001/","999002/"),
    INSTANCE_URL.replace("000099900121000005","000099900121000006")])
def test_redirects_cannot_change_origin_or_document_identity_and_do_not_leak_bad_location(tmp_path,target):
    response=Response(status=302,headers=(("Location",target),))
    client,transport,_,store=setup(tmp_path,[response])
    _,receipt=capture(client,store,CaptureRequest("sec_xbrl_instance",INSTANCE_URL))
    assert receipt["status"]=="refused" and len(transport.calls)==1 and response.closed
    assert "secret" not in json.dumps(receipt) and "attacker.invalid" not in json.dumps(receipt)
    assert not receipt["object_sha256"]


def test_redirect_loop_limit_and_local_interval_each_refuse_without_extra_transport(tmp_path):
    for case,policy,latency,reason in [("limit",limits(max_redirects=0),.2,"capture_redirect_limit"),
            ("interval",limits(),0.,"capture_local_interval_or_cooldown_pending"),
            ("loop",limits(),.2,"capture_redirect_loop")]:
        folder=tmp_path/case;folder.mkdir()
        response=Response(status=302,headers=(("Location",INSTANCE_URL),))
        if case=="interval":response.headers=(("Location","other.xml"),)
        client,transport,_,store=setup(folder,[response],policy=policy,latency=latency)
        _,receipt=capture(client,store,CaptureRequest("sec_xbrl_instance",INSTANCE_URL))
        assert receipt["reason"]==reason and len(transport.calls)==1 and response.closed


@pytest.mark.parametrize("headers,body,reason",[
    ((("Content-Length","-1"),),b"body","capture_content_length_invalid"),
    ((("Content-Length","1025"),),b"body","capture_declared_body_too_large"),
    ((("Content-Length","8"),),b"body","capture_content_length_mismatch"),
    ((("Content-Length","4"),("content-length","4")),b"body","capture_response_header_ambiguous"),
    ((("Content-Encoding","gzip"),),b"body","capture_encoded_body_not_supported"),
    ((("Date","bad\r\nsecret"),),b"body","capture_response_headers_invalid"),
    ((),b"","capture_empty_body"),
])
def test_response_metadata_or_body_mismatch_is_recorded_without_a_success_object(tmp_path,headers,body,reason):
    response=Response(body,headers=headers);client,_,_,store=setup(tmp_path,[response])
    _,receipt=capture(client,store)
    assert receipt["reason"]==reason and receipt["status"]=="refused" and response.closed
    assert not receipt["object_sha256"] and not list(store.objects.iterdir())


@pytest.mark.parametrize("policy,reason,size",[(limits(max_response_bytes=10),"capture_response_byte_limit",11),
    (limits(max_total_body_bytes=7),"capture_total_body_byte_limit",8)])
def test_streaming_budget_records_only_observed_prefix_and_never_persists_oversize_body(tmp_path,policy,reason,size):
    raw=b"x"*20;response=Response(raw);client,_,_,store=setup(tmp_path,[response],policy=policy)
    _,receipt=capture(client,store)
    assert receipt["reason"]==reason and not receipt["body_complete"]
    assert receipt["observed_body_bytes"]==size and receipt["observed_body_sha256"]==hashlib.sha256(raw[:size]).hexdigest()
    assert not list(store.objects.iterdir()) and response.closed


def test_lifetime_request_and_byte_budgets_survive_subsequent_calls_on_same_client(tmp_path):
    client,transport,clock,store=setup(tmp_path,[Response(b"12345")],policy=limits(max_total_body_bytes=5))
    capture(client,store);clock.advance(1)
    _,receipt=capture(client,store)
    assert receipt["reason"]=="capture_total_body_byte_limit" and len(transport.calls)==1
    other=tmp_path/"requests";other.mkdir()
    client,transport,clock,store=setup(other,[Response()],policy=limits(max_requests=1))
    capture(client,store);clock.advance(1)
    _,receipt=capture(client,store)
    assert receipt["reason"]=="capture_request_budget_exhausted" and len(transport.calls)==1


def test_http_throttle_records_cooldown_without_sleep_or_automatic_retry(tmp_path):
    throttled=Response(status=429,headers=(("Retry-After","60"),))
    client,transport,clock,store=setup(tmp_path,[throttled,Response()])
    _,receipt=capture(client,store)
    assert receipt["reason"]=="capture_http_status_429" and receipt["retry_after_seconds"]==60
    _,pending=capture(client,store)
    assert pending["reason"]=="capture_local_interval_or_cooldown_pending" and len(transport.calls)==1
    clock.advance(60)
    _,accepted=capture(client,store)
    assert accepted["status"]=="captured" and len(transport.calls)==2 and throttled.closed


def test_transport_failures_have_static_reasons_and_partial_digest_without_raw_exception(tmp_path):
    client,transport,clock,store=setup(tmp_path,[OSError("password-in-open-exception"),Response(b"abcdef",failure_after=3)])
    _,failed=capture(client,store)
    assert failed["reason"]=="capture_transport_open_failed" and not failed["attempts"][0]["status"]
    clock.advance(1)
    _,partial=capture(client,store)
    assert partial["reason"]=="capture_transport_read_failed" and partial["observed_body_bytes"]==3
    assert partial["observed_body_sha256"]==hashlib.sha256(b"abc").hexdigest() and not partial["body_complete"]
    assert "password-in-open" not in json.dumps(failed) and "secret-diagnostic" not in json.dumps(partial)
    assert not list(store.objects.iterdir()) and len(transport.calls)==2


def test_elapsed_check_after_blocking_read_refuses_body_and_does_not_claim_total_dns_deadline(tmp_path):
    client,_,clock,store=setup(tmp_path,[],policy=limits(max_elapsed_seconds=.5))
    response=Response(b"body",clock=clock,read_delay=.4);client.transport.responses=[response]
    _,receipt=capture(client,store)
    assert receipt["reason"]=="capture_elapsed_limit" and receipt["elapsed_monotonic_seconds"]>=.5
    assert "not_a_proven_total_DNS" in receipt["limits"]["deadline_scope"]
    assert not receipt["object_sha256"] and response.closed


def test_wall_clock_rollback_refuses_capture_without_backdating_bytes(tmp_path):
    client,_,clock,store=setup(tmp_path,[])
    class Rollback(Response):
        def close(self):super().close();clock.wall_adjustment=-100
    client.transport.responses=[Rollback()]
    _,receipt=capture(client,store)
    assert receipt["reason"]=="capture_clock_inconsistent" and not receipt["clock_consistent"]
    assert not receipt["object_sha256"]


def test_expected_digest_checks_integrity_not_origin_and_persistence_failures_still_propagate(tmp_path,monkeypatch):
    client,_,_,store=setup(tmp_path,[Response(b"actual")])
    _,receipt=capture(client,store,CaptureRequest("sec_header",HEADER_URL,"0"*64))
    assert receipt["reason"]=="capture_expected_digest_mismatch" and receipt["body_complete"]
    assert receipt["observed_body_sha256"]==hashlib.sha256(b"actual").hexdigest() and not receipt["object_sha256"]
    folder=tmp_path/"write";folder.mkdir();client,_,_,store=setup(folder,[Response()])
    def failed_write(original):raise OSError("synthetic_disk_failure")
    monkeypatch.setattr(store,"_put_bytes",failed_write)
    with pytest.raises(OSError,match="synthetic_disk_failure"):capture(client,store)


def test_concrete_transport_is_opt_in_and_refuses_nonofficial_uri_without_opening_socket(monkeypatch):
    def no_socket(*args,**kwargs):pytest.fail("no real socket may be opened in construction tests")
    monkeypatch.setattr("app.valuation_ensemble_capture.http.client.HTTPSConnection",no_socket)
    transport=HTTPSOfficialTransport()
    with pytest.raises(NotEvaluable,match="capture_uri_not_supported"):
        transport.open("https://attacker.invalid/private",CONTACT,1)


def test_concrete_https_seam_uses_verified_context_identity_encoding_and_observed_peer_metadata(tmp_path,monkeypatch):
    raw=b"simulated-TLS-response";calls=[]
    socket=Mock(spec=ssl.SSLSocket);socket.getpeercert.return_value=b"synthetic-certificate"
    socket.version.return_value="TLSv1.3";socket.cipher.return_value=("SYNTHETIC_CIPHER","TLSv1.3",256)
    class HTTPBody:
        status=200
        def __init__(self):self.offset=0;self.closed=False
        def getheaders(self):return [("Content-Length",str(len(raw)))]
        def read(self,size):result=raw[self.offset:self.offset+size];self.offset+=len(result);return result
        def close(self):self.closed=True
    body=HTTPBody()
    class Connection:
        sock=socket
        def request(self,*args,**kwargs):calls.append((args,kwargs))
        def getresponse(self):return body
        def close(self):self.closed=True
    connection=Connection()
    def factory(host,**kwargs):
        assert host=="www.sec.gov" and kwargs["port"]==443
        assert kwargs["context"].check_hostname and kwargs["context"].verify_mode==ssl.CERT_REQUIRED
        assert kwargs["context"].minimum_version==ssl.TLSVersion.TLSv1_2
        return connection
    monkeypatch.setattr("app.valuation_ensemble_capture.http.client.HTTPSConnection",factory)
    clock=Clock();client=OfficialCaptureClient(HTTPSOfficialTransport(),limits(),user_agent=CONTACT,clock=clock)
    store=OriginalEvidenceStore(tmp_path/"capture");_,receipt=capture(client,store)
    assert receipt["status"]=="captured" and body.closed and connection.closed
    assert calls[0][0][0]=="GET" and calls[0][1]["headers"]=={"User-Agent":CONTACT,"Accept-Encoding":"identity","Accept":"*/*"}
    tls=receipt["attempts"][0]["tls_observation"]
    assert tls["peer_certificate_sha256"]==hashlib.sha256(b"synthetic-certificate").hexdigest()
    assert tls["version"]=="TLSv1.3" and socket.settimeout.called
    assert receipt["origin_authentication"]=="transport_observation_requires_independent_review"
    assert not receipt["historical_admissibility"] # Mocked TLS exercises code, never proves an actual official origin.


def test_identical_replayed_synthetic_observation_verifies_immutable_private_receipt(tmp_path):
    client,_,_,store=setup(tmp_path,[Response()]);first,receipt=capture(client,store)
    path=Path(first["receipt_path"]);before=path.read_bytes();stamp=path.stat().st_mtime_ns
    clock=Clock();other=OfficialCaptureClient(Transport([Response()],clock),limits(),user_agent=CONTACT,clock=clock)
    second,saved=capture(other,store)
    assert first["run_key"]==second["run_key"] and not second["created"] and receipt==saved
    assert path.read_bytes()==before and path.stat().st_mtime_ns==stamp


def test_reopened_capture_verifies_binary_object_and_refuses_receipt_promoting_origin(tmp_path):
    from app.valuation_ensemble_inputs import canonical_hash
    client,_,_,store=setup(tmp_path,[Response()]);result,receipt=capture(client,store)
    reopened=OriginalEvidenceStore(store.manifests.directory)
    assert read_capture_receipt(reopened,result["run_key"])==receipt
    forged={k:v for k,v in receipt.items() if k not in {"run_key","payload_sha256"}}
    forged["origin_authentication"]="authenticated_by_supplied_flag"
    forged["run_key"]=canonical_hash(forged);forged["payload_sha256"]=canonical_hash(forged)
    reopened.manifests.put(forged)
    with pytest.raises(NotEvaluable,match="capture_receipt_contract_mismatch"):
        read_capture_receipt(reopened,forged["run_key"])
    original=reopened.objects/(receipt["object_sha256"][0]+".bin");original.write_bytes(b"corrupt")
    with pytest.raises(NotEvaluable,match="stored_original_bytes_digest_mismatch"):
        read_capture_receipt(reopened,result["run_key"])


@pytest.mark.parametrize("kind,uri",[("sec_header",HEADER_URL),("cvm_archive",CVM_URL)])
def test_captured_fixture_bytes_need_separate_original_parser_and_keep_origin_gates_closed(tmp_path,kind,uri):
    raw=header().payload if kind=="sec_header" else cvm_package().payload()
    client,_,_,store=setup(tmp_path,[Response(raw)],policy=limits(max_response_bytes=8192,max_total_body_bytes=16384))
    _,receipt=capture(client,store,CaptureRequest(kind,uri))
    supplied=SourceBytes(kind,receipt["final_uri"],datetime.fromisoformat(receipt["body_received_at"]),
        receipt["observed_body_sha256"],store.read_bytes(receipt["object_sha256"][0]))
    parsed=ingest_supplied_original(supplied,store)
    manifest=store.read_manifest(parsed["run_key"])
    assert manifest["origin_authentication"]=="unverified_supplied_bytes" and not manifest["historical_admissibility"]
    assert manifest["extraction"]["artifact"]["captured_at"].startswith("2026-10-26")


def test_http_200_challenge_page_is_only_transport_bytes_and_never_a_valid_original(tmp_path):
    client,_,_,store=setup(tmp_path,[Response(b"<html><h1>Access denied</h1></html>")])
    _,receipt=capture(client,store)
    assert receipt["status"]=="captured" and receipt["original_layout_status"]=="not_validated_transport_bytes_only"
    raw=store.read_bytes(receipt["object_sha256"][0])
    supplied=SourceBytes("sec_header",HEADER_URL,datetime.fromisoformat(receipt["body_received_at"]),hashlib.sha256(raw).hexdigest(),raw)
    with pytest.raises(NotEvaluable):ingest_supplied_original(supplied,store)
