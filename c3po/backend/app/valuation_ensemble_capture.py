"""Explicit bounded SEC/CVM capture seam; never called by import or shadow defaults.

An injected transport is test-only evidence. Even the concrete TLS client records
what it observed, not independent authentication, historical availability or rights.
No settings, environment credential, DB, retry, discovery or backfill is consulted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import http.client
import math
from pathlib import Path
import re
import ssl
import threading
import time
from typing import Any, Protocol
from urllib.parse import urljoin, urlsplit

from .valuation_ensemble_inputs import NotEvaluable, canonical_hash, utc
from .valuation_ensemble_originals import MAX_BYTES, SourceBytes
from .valuation_ensemble_original_store import OriginalEvidenceStore


def _uri(kind: str, uri: str) -> tuple[str,...]:
    """Return document identity only for supported canonical, credential-free URIs."""
    if not isinstance(uri,str) or not uri.isascii() or any(ord(c)<=32 or ord(c)==127 for c in uri):
        raise NotEvaluable("capture_uri_not_supported")
    try:
        p=urlsplit(uri);port=p.port
    except ValueError as exc:
        raise NotEvaluable("capture_uri_not_supported") from exc
    if (p.scheme!="https" or port is not None or p.username is not None or p.password is not None
            or p.query or p.fragment or "%" in p.path or "\\" in p.path
            or any(x in {".",".."} for x in p.path.split("/"))):
        raise NotEvaluable("capture_uri_not_supported")
    if p.netloc=="www.sec.gov":
        if kind=="sec_header":
            match=re.fullmatch(r"/Archives/edgar/data/(\d{1,10})/(\d{10}-\d{2}-\d{6})-index-headers\.html",p.path)
            if match:return ("sec_header",str(int(match[1])),match[2].replace("-",""))
        elif kind=="sec_xbrl_instance":
            match=re.fullmatch(r"/Archives/edgar/data/(\d{1,10})/(\d{18})/([A-Za-z0-9_-][A-Za-z0-9._-]*\.xml)",p.path)
            if match:return ("sec_xbrl_instance",str(int(match[1])),match[2])
    elif p.netloc=="dados.cvm.gov.br" and kind=="cvm_archive":
        match=re.fullmatch(r"/dados/CIA_ABERTA/DOC/(ITR|DFP)/DADOS/(itr|dfp)_cia_aberta_(\d{4})\.zip",p.path)
        if match and match[1].lower()==match[2]:return ("cvm_archive",match[1],match[3])
    raise NotEvaluable("capture_uri_not_supported")


@dataclass(frozen=True)
class CaptureRequest:
    kind: str
    uri: str
    expected_sha256: str | None=None

    def check(self) -> tuple[str,...]:
        identity=_uri(self.kind,self.uri)
        if self.expected_sha256 is not None and (not isinstance(self.expected_sha256,str)
                or not re.fullmatch(r"[0-9a-f]{64}",self.expected_sha256)):
            raise NotEvaluable("capture_expected_digest_invalid")
        return identity


@dataclass(frozen=True)
class CaptureLimits:
    policy_id: str
    max_requests: int
    minimum_interval_seconds: float
    max_response_bytes: int
    max_total_body_bytes: int
    timeout_seconds: float
    max_elapsed_seconds: float
    max_redirects: int

    def check(self, kind: str) -> dict[str,Any]:
        integers=(self.max_requests,self.max_response_bytes,self.max_total_body_bytes,self.max_redirects)
        if (not isinstance(self.policy_id,str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}",self.policy_id)
                or any(type(x) is not int for x in integers) or self.max_requests<1
                or not 0<self.max_response_bytes<=MAX_BYTES or self.max_total_body_bytes<1
                or not 0<=self.max_redirects<=10):
            raise NotEvaluable("explicit_capture_limits_invalid")
        for value in (self.minimum_interval_seconds,self.timeout_seconds,self.max_elapsed_seconds):
            if type(value) not in {int,float} or not math.isfinite(value) or value<=0:
                raise NotEvaluable("explicit_capture_limits_invalid")
        if kind.startswith("sec_") and self.minimum_interval_seconds<.1:
            raise NotEvaluable("SEC_client_interval_below_10_requests_per_second_floor")
        return {**self.__dict__,"scope":"this_client_lifetime_only_not_shared_user_or_contract_quota",
            "deadline_scope":"elapsed_checks_and_socket_timeouts_not_a_proven_total_DNS_headers_body_wall_deadline"}


class CaptureClock(Protocol):
    def now(self) -> datetime: ...
    def monotonic(self) -> float: ...


class SystemCaptureClock:
    def now(self) -> datetime:return datetime.now(timezone.utc)
    def monotonic(self) -> float:return time.monotonic()


class CaptureResponse(Protocol):
    status: int
    headers: tuple[tuple[str,str],...]
    def read(self, size: int, timeout: float) -> bytes: ...
    def close(self) -> None: ...


class CaptureTransport(Protocol):
    def open(self, uri: str, user_agent: str, timeout: float) -> CaptureResponse: ...


class _HTTPSResponse:
    def __init__(self, response: http.client.HTTPResponse, connection: http.client.HTTPSConnection,
                 socket: ssl.SSLSocket, tls: dict[str,Any]) -> None:
        self.response=response;self.connection=connection;self.socket=socket;self.tls=tls
        self.status=response.status;self.headers=tuple(response.getheaders())

    def read(self, size: int, timeout: float) -> bytes:
        self.socket.settimeout(timeout)
        return self.response.read(size)
    def close(self) -> None:
        try:self.response.close()
        finally:self.connection.close()


class HTTPSOfficialTransport:
    """Opt-in concrete transport: fixed CA/hostname checks, no proxy or auto redirect.

    Creating the object opens no socket. Only an explicit client.capture() can call
    open(); no command line or environment-driven entry point enables it.
    """
    def open(self, uri: str, user_agent: str, timeout: float) -> CaptureResponse:
        # The transport also refuses arbitrary URLs when called without the client.
        for kind in ("sec_header","sec_xbrl_instance","cvm_archive"):
            try:_uri(kind,uri);break
            except NotEvaluable:continue
        else:raise NotEvaluable("capture_uri_not_supported")
        p=urlsplit(uri)
        context=ssl.create_default_context();context.minimum_version=ssl.TLSVersion.TLSv1_2
        connection=http.client.HTTPSConnection(p.hostname or "",port=443,timeout=timeout,context=context)
        try:
            connection.request("GET",p.path,headers={"User-Agent":user_agent,"Accept-Encoding":"identity","Accept":"*/*"})
            socket=connection.sock
            if not isinstance(socket,ssl.SSLSocket):raise OSError("TLS socket unavailable")
            cert=socket.getpeercert(binary_form=True)
            if not cert:raise OSError("TLS peer certificate unavailable")
            tls={"version":socket.version(),"cipher":socket.cipher(),
                 "peer_certificate_sha256":hashlib.sha256(cert).hexdigest(),
                 "hostname_verification":"stdlib_default_context_required"}
            return _HTTPSResponse(connection.getresponse(),connection,socket,tls)
        except (OSError,http.client.HTTPException):
            connection.close();raise


def _headers(response: CaptureResponse) -> dict[str,str]:
    selected={};allowed={"location","content-length","content-encoding","content-type","date","last-modified","etag","retry-after"}
    for name,value in response.headers:
        if (not isinstance(name,str) or not isinstance(value,str) or len(name)>200 or len(value)>8192
                or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+",name) or "\r" in value or "\n" in value):
            raise NotEvaluable("capture_response_headers_invalid")
        key=name.lower()
        if key in allowed:
            if key in selected:raise NotEvaluable("capture_response_header_ambiguous")
            selected[key]=value.strip()
    return selected


def _http_date(value: str | None) -> str | None:
    if value is None:return None
    try:return utc(parsedate_to_datetime(value)).isoformat()
    except (ValueError,TypeError,OverflowError):return None


def _retry_after(value: str | None, now: datetime) -> float | None:
    if value is None:return None
    if re.fullmatch(r"\d{1,9}",value):return float(value)
    parsed=_http_date(value)
    return max(0.,(datetime.fromisoformat(parsed)-now).total_seconds()) if parsed else None


class OfficialCaptureClient:
    """Explicit lifetime budget. Caller must also coordinate the shared SEC user cap."""
    def __init__(self, transport: CaptureTransport, limits: CaptureLimits, *, user_agent: str | None,
                 clock: CaptureClock) -> None:
        self.transport=transport;self.limits=limits;self.user_agent=user_agent;self.clock=clock
        self.requests_used=0;self.body_bytes_observed=0;self.next_request_at: float | None=None
        self.lock=threading.Lock()

    def _reserve(self, observation: dict[str,Any], start: float) -> float:
        now=self.clock.monotonic();elapsed=now-start
        if not math.isfinite(now) or elapsed<0:raise NotEvaluable("capture_monotonic_clock_invalid")
        if elapsed>=self.limits.max_elapsed_seconds:raise NotEvaluable("capture_elapsed_limit")
        if self.requests_used>=self.limits.max_requests:raise NotEvaluable("capture_request_budget_exhausted")
        if self.body_bytes_observed>=self.limits.max_total_body_bytes:raise NotEvaluable("capture_total_body_byte_limit")
        if self.next_request_at is not None and now<self.next_request_at:
            observation["retry_after_seconds"]=self.next_request_at-now
            raise NotEvaluable("capture_local_interval_or_cooldown_pending")
        self.requests_used+=1;self.next_request_at=now+self.limits.minimum_interval_seconds
        return min(self.limits.timeout_seconds,self.limits.max_elapsed_seconds-elapsed)

    def _receive(self, request: CaptureRequest, identity: tuple[str,...], observation: dict[str,Any], start: float) -> SourceBytes:
        uri=request.uri;visited=set();digest=hashlib.sha256();body=bytearray()
        for hop in range(self.limits.max_redirects+1):
            if uri in visited:raise NotEvaluable("capture_redirect_loop")
            visited.add(uri);timeout=self._reserve(observation,start)
            attempt: dict[str,Any]={"requested_uri":uri,"started_at":utc(self.clock.now()).isoformat(),"status":None}
            observation["attempts"].append(attempt)
            try:response=self.transport.open(uri,self.user_agent or "",timeout)
            except (OSError,http.client.HTTPException) as exc:raise NotEvaluable("capture_transport_open_failed") from exc
            try:
                if type(response.status) is not int or not 100<=response.status<=599:
                    raise NotEvaluable("capture_response_status_invalid")
                attempt["status"]=response.status;headers=_headers(response)
                attempt["server_date_metadata_only"]=_http_date(headers.get("date"))
                attempt["last_modified_metadata_only"]=_http_date(headers.get("last-modified"))
                attempt["etag_sha256"]=hashlib.sha256(headers["etag"].encode("utf-8","surrogatepass")).hexdigest() if "etag" in headers else None
                if type(self.transport) is HTTPSOfficialTransport and type(response) is _HTTPSResponse:
                    attempt["tls_observation"]=response.tls
                if response.status in {301,302,303,307,308}:
                    if hop==self.limits.max_redirects:raise NotEvaluable("capture_redirect_limit")
                    location=headers.get("location")
                    if not location:raise NotEvaluable("capture_redirect_location_missing")
                    target=urljoin(uri,location)
                    if _uri(request.kind,target)!=identity:raise NotEvaluable("capture_redirect_document_identity_changed")
                    attempt["redirect_to_uri"]=target;attempt["body_not_read"]=True;uri=target
                    # No sleep or automatic retry. Every hop reserves the same shared budget.
                    continue
                if response.status!=200:
                    delay=_retry_after(headers.get("retry-after"),utc(self.clock.now()))
                    if delay is not None:
                        observation["retry_after_seconds"]=delay
                        self.next_request_at=max(self.next_request_at or 0.,self.clock.monotonic()+delay)
                    raise NotEvaluable("capture_http_status_"+str(response.status))
                if headers.get("content-encoding","identity").lower()!="identity":
                    raise NotEvaluable("capture_encoded_body_not_supported")
                length=headers.get("content-length");expected_length=None
                if length is not None:
                    if not re.fullmatch(r"\d{1,12}",length):raise NotEvaluable("capture_content_length_invalid")
                    expected_length=int(length);attempt["declared_content_length"]=expected_length
                    if expected_length>self.limits.max_response_bytes:raise NotEvaluable("capture_declared_body_too_large")
                media=headers.get("content-type","").split(";",1)[0].lower()
                attempt["content_type"]=media if re.fullmatch(r"[a-z0-9.+-]+/[a-z0-9.+-]+",media) else None
                while True:
                    elapsed=self.clock.monotonic()-start
                    if elapsed<0 or not math.isfinite(elapsed):raise NotEvaluable("capture_monotonic_clock_invalid")
                    if elapsed>=self.limits.max_elapsed_seconds:raise NotEvaluable("capture_elapsed_limit")
                    room=min(self.limits.max_response_bytes-len(body),self.limits.max_total_body_bytes-self.body_bytes_observed)
                    size=min(65536,max(1,room+1))
                    timeout=min(self.limits.timeout_seconds,self.limits.max_elapsed_seconds-elapsed)
                    try:chunk=response.read(size,timeout)
                    except (OSError,http.client.HTTPException) as exc:raise NotEvaluable("capture_transport_read_failed") from exc
                    if not isinstance(chunk,bytes) or len(chunk)>size:raise NotEvaluable("capture_transport_read_contract_invalid")
                    self.body_bytes_observed+=len(chunk);digest.update(chunk);body.extend(chunk)
                    observation.update(observed_body_bytes=len(body),observed_body_sha256=digest.hexdigest())
                    elapsed=self.clock.monotonic()-start
                    if elapsed<0 or not math.isfinite(elapsed):raise NotEvaluable("capture_monotonic_clock_invalid")
                    if elapsed>=self.limits.max_elapsed_seconds:raise NotEvaluable("capture_elapsed_limit")
                    if len(body)>self.limits.max_response_bytes:raise NotEvaluable("capture_response_byte_limit")
                    if self.body_bytes_observed>self.limits.max_total_body_bytes:raise NotEvaluable("capture_total_body_byte_limit")
                    if not chunk:break
                observation["body_complete"]=True
                received=utc(self.clock.now());observation["body_received_at"]=received.isoformat()
                if expected_length is not None and expected_length!=len(body):raise NotEvaluable("capture_content_length_mismatch")
                if not body:raise NotEvaluable("capture_empty_body")
                if request.expected_sha256 is not None and request.expected_sha256!=digest.hexdigest():
                    raise NotEvaluable("capture_expected_digest_mismatch")
                observation["final_uri"]=uri
                return SourceBytes(request.kind,uri,received,digest.hexdigest(),bytes(body))
            finally:
                try:response.close()
                except (OSError,http.client.HTTPException) as exc:raise NotEvaluable("capture_transport_close_failed") from exc
        raise NotEvaluable("capture_redirect_limit")

    def capture(self, request: CaptureRequest, store: OriginalEvidenceStore) -> dict[str,Any]:
        identity=request.check();limits=self.limits.check(request.kind)
        agent=self.user_agent
        if (not isinstance(agent,str) or not 1<=len(agent)<=512 or not agent.isascii()
                or any(ord(c)<32 or ord(c)==127 for c in agent) or not agent.strip()):
            raise NotEvaluable("explicit_operator_user_agent_required_no_invented_contact")
        with self.lock:
            started=utc(self.clock.now());start=self.clock.monotonic()
            if not math.isfinite(start):raise NotEvaluable("capture_monotonic_clock_invalid")
            observation: dict[str,Any]={"schema":"VALUATION-ENSEMBLE-TRANSPORT-CAPTURE-v1","kind":request.kind,
                "requested_uri":request.uri,"expected_sha256":request.expected_sha256,"final_uri":None,
                "started_at":started.isoformat(),"finished_at":None,"attempts":[],"limits":limits,
                "operator_user_agent_configured":True,"operator_identity_or_global_quota_attested":False,
                "transport_execution":"stdlib_https_client" if type(self.transport) is HTTPSOfficialTransport else "injected_transport_not_source_authentication",
                "origin_authentication":"transport_observation_requires_independent_review",
                "original_layout_status":"not_validated_transport_bytes_only",
                "historical_admissibility":False,"buy_permission":False,"served_source_changed":False,
                "observed_body_bytes":0,"observed_body_sha256":None,"body_complete":False,"body_received_at":None,
                "status":"refused","reason":None,"object_sha256":[],"retry_after_seconds":None}
            original=None
            try:
                original=self._receive(request,identity,observation,start)
                if utc(self.clock.now())<started:raise NotEvaluable("capture_wall_clock_moved_backwards")
                observation.update(status="captured",reason=None)
            except NotEvaluable as exc:observation["reason"]=str(exc);original=None
            finished=utc(self.clock.now());elapsed=self.clock.monotonic()-start
            # Validate the complete observed wall-clock order before persisting
            # bytes; a partial rewind can still finish after the overall start.
            instants=[started,*(datetime.fromisoformat(x["started_at"]) for x in observation["attempts"])]
            if observation["body_received_at"] is not None:
                instants.append(datetime.fromisoformat(observation["body_received_at"]))
            instants.append(finished)
            consistent=(math.isfinite(elapsed) and elapsed>=0
                        and all(left<=right for left,right in zip(instants,instants[1:])))
            if not consistent:
                observation.update(status="refused",reason="capture_clock_inconsistent");original=None
            elif elapsed>=self.limits.max_elapsed_seconds:
                observation.update(status="refused",reason="capture_elapsed_limit");original=None
            observation["finished_at"]=finished.isoformat();observation["clock_consistent"]=consistent
            observation["elapsed_monotonic_seconds"]=elapsed if math.isfinite(elapsed) else None
            observation["client_requests_used"]=self.requests_used
            observation["client_body_bytes_observed"]=self.body_bytes_observed
            # Persistence is outside the parser/transport refusal boundary: failures propagate.
            if original is not None:observation["object_sha256"]=[store._put_bytes(original)]
            observation["implementation_files"]={name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in
                ("valuation_ensemble_capture.py","valuation_ensemble_originals.py","valuation_ensemble_original_store.py",
                 "valuation_ensemble_persistence.py","valuation_ensemble_inputs.py")}
            observation["pending_proofs"]=["independent_official_transport_review","historical_source_availability",
                "instrument_identity_class_rights_and_share_basis","corporate_action_interval","reviewed_classification_policy"]
            observation["run_key"]=canonical_hash(observation);observation["payload_sha256"]=canonical_hash(observation)
            path,created=store.manifests.put(observation)
            return {"run_key":observation["run_key"],"payload_sha256":observation["payload_sha256"],
                "status":observation["status"],"reason":observation["reason"],"created":created,"receipt_path":str(path),
                "historical_admissibility":False}


def read_capture_receipt(store: OriginalEvidenceStore, run_key: str) -> dict[str,Any] | None:
    """Verify the private receipt/object link, without trusting supplied origin claims."""
    receipt=store.manifests.read(run_key)
    if receipt is None:return None
    try:
        if (receipt["schema"]!="VALUATION-ENSEMBLE-TRANSPORT-CAPTURE-v1"
                or receipt["origin_authentication"]!="transport_observation_requires_independent_review"
                or receipt["original_layout_status"]!="not_validated_transport_bytes_only"
                or receipt["historical_admissibility"] is not False or receipt["buy_permission"] is not False
                or receipt["served_source_changed"] is not False
                or receipt["transport_execution"] not in {"stdlib_https_client","injected_transport_not_source_authentication"}):
            raise NotEvaluable("capture_receipt_contract_mismatch")
        if receipt["status"]=="captured":
            received=utc(datetime.fromisoformat(receipt["body_received_at"]))
            instants=[utc(datetime.fromisoformat(receipt["started_at"])),
                *(utc(datetime.fromisoformat(x["started_at"])) for x in receipt["attempts"]),
                received,utc(datetime.fromisoformat(receipt["finished_at"]))]
            if (receipt["object_sha256"]!=[receipt["observed_body_sha256"]] or receipt["body_complete"] is not True
                    or receipt["clock_consistent"] is not True or receipt["reason"] is not None
                    or not all(left<=right for left,right in zip(instants,instants[1:]))
                    or _uri(receipt["kind"],receipt["requested_uri"])!=_uri(receipt["kind"],receipt["final_uri"])):
                raise NotEvaluable("capture_receipt_object_or_clock_mismatch")
        elif receipt["status"]!="refused" or receipt["object_sha256"]!=[]:
            raise NotEvaluable("capture_receipt_status_mismatch")
    except (ValueError,TypeError,KeyError) as exc:
        if isinstance(exc,NotEvaluable):raise
        raise NotEvaluable("capture_receipt_contract_mismatch") from exc
    if receipt["status"]=="captured":
        raw=store.read_bytes(receipt["object_sha256"][0])
        if type(receipt["observed_body_bytes"]) is not int or receipt["observed_body_bytes"]!=len(raw):
            raise NotEvaluable("capture_receipt_object_size_mismatch")
    return receipt
