"""Synthetic-only receipts; the positive verifier is a test double, not a feed."""
import ast
import base64
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

from app.r2d2_v2_earnings_source import (
    COVERAGE_SCOPE, CoverageEvidence, EarningsInputError, EarningsReceipt,
    assess_earnings_coverage, parse_earnings_response,
)

START = datetime(2026, 9, 8, 13, 59, 57, tzinfo=timezone.utc)
RECEIVED = START + timedelta(seconds=1)
AVAILABLE = RECEIVED + timedelta(seconds=1)
DECISION = AVAILABLE + timedelta(seconds=1)
MATURITY = datetime(2026, 9, 21, 19, 55, tzinfo=timezone.utc)
SECRET = "PRIVATE_DO_NOT_PRINT_abc123"


def encoded(value):
    return json.dumps(value, separators=(",", ":")).encode()


def response(rows=(), **extra):
    return {"type": "Earnings", "from": "2026-09-08", "to": "2026-09-21", "earnings": list(rows), **extra}


def event(**extra):
    return {"code": "TEST.US", "report_date": "2026-09-15", "date": "2026-06-30",
            "before_after_market": "AfterMarket", "currency": "USD", "actual": None,
            "estimate": 1.2, "difference": 0, "percent": None, **extra}


def observe(body=None, *, raw=None, **receipt_changes):
    raw = encoded(response() if body is None else body) if raw is None else raw
    receipt = EarningsReceipt(("TEST.US",), date(2026, 9, 8), date(2026, 9, 21), START, RECEIVED,
        AVAILABLE, 200, hashlib.sha256(raw).hexdigest(), True, "application/json")
    return parse_earnings_response(raw, replace(receipt, **receipt_changes))


def evidence(observation, **changes):
    # These references have no external authority; only positive tests install a stub.
    return replace(CoverageEvidence("synthetic-attestation", "synthetic-independent-issuer", "a" * 64, "b" * 64,
        observation.receipt.body_sha256, observation.receipt_sha256, "TEST.US", DECISION, MATURITY,
        START, AVAILABLE, COVERAGE_SCOPE), **changes)


def assess(observation, **changes):
    return assess_earnings_coverage(observation, symbol="TEST.US", decision_at=DECISION,
                                   maturity_at=MATURITY, **changes)


def test_http_200_empty_is_observation_not_negative_coverage():
    observation = observe()
    assert observation.parse_status == "OBSERVED" and observation.events == ()
    assessment = assess(observation)
    assert assessment.feed_coverage == "UNKNOWN"
    assert set(assessment.diagnostics) == {"COVERAGE_EVIDENCE_MISSING", "COVERAGE_VERIFIER_MISSING"}
    assert not assessment.port_temporal_fields_complete
    assert observation.public_summary()["feed_coverage"] == "UNKNOWN"


def test_self_supplied_reference_and_hash_do_not_verify_coverage():
    observation = observe()
    assessment = assess(observation, evidence=evidence(observation))
    assert assessment.feed_coverage == "UNKNOWN"
    assert assessment.diagnostics == ("COVERAGE_VERIFIER_MISSING",)


def test_independent_hook_receives_full_binding_and_empty_verified_is_not_readiness():
    observation = observe()
    calls = []
    def verifier(proof, expected):
        calls.append((proof, expected))
        return True
    proof = evidence(observation)
    assessment = assess(observation, evidence=proof, verifier=verifier)
    assert assessment.feed_coverage == "VERIFIED" and assessment.port_temporal_fields_complete
    assert len(calls) == 1 and calls[0][0] == proof
    expected = calls[0][1]
    assert (expected.symbol, expected.request_symbols) == ("TEST.US", ("TEST.US",))
    assert (expected.request_from, expected.request_to) == (date(2026, 9, 8), date(2026, 9, 21))
    assert (expected.decision_at, expected.maturity_at) == (DECISION, MATURITY)
    assert (expected.response_received_at, expected.observation_available_at) == (RECEIVED, AVAILABLE)
    assert expected.observation_body_sha256 == hashlib.sha256(observation.raw_body).hexdigest()
    assert expected.observation_receipt_sha256 == observation.receipt_sha256
    assert assessment.public_summary()["production_ready"] is False
    assert assessment.public_summary()["port_payload_emitted"] is False


@pytest.mark.parametrize("answer", [False, 1, "true", {"verified": True}, None])
def test_hook_requires_literal_true(answer):
    observation = observe()
    result = assess(observation, evidence=evidence(observation), verifier=lambda *_: answer)
    assert result.feed_coverage == "UNKNOWN"
    assert result.diagnostics == ("COVERAGE_EXTERNAL_VERIFICATION_FAILED",)


def test_verifier_error_is_redacted():
    observation = observe()
    def fail(*_):
        raise RuntimeError(SECRET)
    result = assess(observation, evidence=evidence(observation), verifier=fail)
    assert result.diagnostics == ("COVERAGE_EXTERNAL_VERIFIER_ERROR",)
    assert SECRET not in str(result.public_summary()) and SECRET not in repr(result)


@pytest.mark.parametrize("changes,reason", [
    ({"symbol": "OTHER.US"}, "COVERAGE_BINDING_MISMATCH"),
    ({"observation_body_sha256": "c" * 64}, "COVERAGE_BINDING_MISMATCH"),
    ({"observation_receipt_sha256": "c" * 64}, "COVERAGE_BINDING_MISMATCH"),
    ({"scope": "HTTP_BODY_RECEIVED"}, "COVERAGE_BINDING_MISMATCH"),
    ({"contract_sha256": ""}, "COVERAGE_EVIDENCE_INVALID"),
    ({"evidence_sha256": "SELF_ASSERTED"}, "COVERAGE_EVIDENCE_INVALID"),
    ({"window_start": DECISION + timedelta(microseconds=1)}, "COVERAGE_WINDOW_INSUFFICIENT"),
    ({"window_end": MATURITY - timedelta(microseconds=1)}, "COVERAGE_WINDOW_INSUFFICIENT"),
    ({"known_as_of": RECEIVED + timedelta(microseconds=1)}, "COVERAGE_CLOCK_ORDER"),
    ({"published_at": RECEIVED - timedelta(microseconds=1)}, "COVERAGE_CLOCK_ORDER"),
    ({"published_at": DECISION + timedelta(microseconds=1)}, "COVERAGE_CLOCK_ORDER"),
    ({"published_at": DECISION.replace(tzinfo=None)}, "CLOCK_NOT_AWARE"),
])
def test_bad_evidence_cannot_reach_external_verifier(changes, reason):
    observation = observe()
    calls = []
    result = assess(observation, evidence=evidence(observation, **changes), verifier=lambda *_: calls.append(True) or True)
    assert result.feed_coverage == "UNKNOWN" and reason in result.diagnostics and calls == []


@pytest.mark.parametrize("timing", ["BeforeMarket", "AfterMarket", None])
@pytest.mark.parametrize("report_day", ["2026-09-08", "2026-09-15", "2026-09-21"])
def test_date_and_market_timing_never_become_event_at_even_if_coverage_verified(timing, report_day):
    observation = observe(response([event(before_after_market=timing, report_date=report_day)]))
    result = assess(observation, evidence=evidence(observation), verifier=lambda *_: True)
    assert result.feed_coverage == "VERIFIED" and not result.port_temporal_fields_complete
    assert result.diagnostics == ("EVENT_PRECISE_TIME_UNAVAILABLE",)
    row = observation.events[0].to_private_dict()
    assert row["report_date"] == report_day and row["fiscal_period_end"] == "2026-06-30"
    assert row["market_timing"] == timing
    assert all(row[key] is None for key in ("event_at", "timezone", "provider_announced_at", "provider_updated_at", "announcement_status"))


@pytest.mark.parametrize("status", [201, 404, 422, 429, 500])
def test_http_failures_preserve_bytes_privately_never_as_valid_empty(status):
    raw = ("<html>error api_token=" + SECRET + "</html>").encode()
    observation = observe(raw=raw, http_status=status, content_type="text/html")
    assert observation.parse_status == "HTTP_ERROR"
    assert base64.b64decode(observation.to_private_dict()["raw_body_base64"]) == raw
    assert SECRET not in json.dumps(observation.public_summary()) and SECRET not in repr(observation)
    calls = []
    result = assess(observation, evidence=evidence(observation), verifier=lambda *_: calls.append(True) or True)
    assert result.feed_coverage == "UNKNOWN" and not calls


@pytest.mark.parametrize("raw,reason", [
    (b'{"type":"Earnings",', "JSON_MALFORMED"),
    (b'\xff', "JSON_MALFORMED"),
    (b'[]', "RESPONSE_NOT_OBJECT"),
    (b'{"type":"Earnings","earnings":[],"earnings":[]}', "JSON_DUPLICATE_KEY"),
    (b'{"type":"Earnings","earnings":NaN}', "JSON_NONFINITE"),
    (b'{"type":"Earnings","earnings":[],"coverage_verified":true}', "RESPONSE_FIELDS_INVALID"),
])
def test_malformed_response_is_not_coverage(raw, reason):
    observation = observe(raw=raw)
    assert observation.parse_status == "INVALID_BODY" and observation.diagnostics == (reason,)
    assert assess(observation).feed_coverage == "UNKNOWN"


@pytest.mark.parametrize("row,reason", [
    (event(actual=True), "EVENT_NUMBER_INVALID"),
    (event(actual="1.2"), "EVENT_NUMBER_INVALID"),
    (event(actual=float("inf")), "JSON_NONFINITE"),
    (event(before_after_market="cancelled"), "EVENT_TIMING_INVALID"),
    (event(before_after_market=[]), "EVENT_TIMING_INVALID"),
    (event(code="TEST"), "EVENT_SYMBOL_INVALID"),
    (event(report_date="20260915"), "DATE_NOT_CANONICAL"),
    (event(report_date="2026-09-15T16:00:00Z"), "DATE_INVALID"),
    (event(report_date="2026-02-30"), "DATE_INVALID"),
    (event(currency=True), "EVENT_CURRENCY_INVALID"),
    (event(updated_at="2026-09-08T13:00:00Z"), "EVENT_FIELDS_INVALID"),
])
def test_event_schema_drift_invalid_types_and_dates_are_preserved_as_data_failure(row, reason):
    observation = observe(response([row]))
    assert observation.parse_status == "INVALID_BODY" and reason in observation.diagnostics
    assert json.loads(observation.raw_body)["earnings"][0] == row


def test_actual_null_is_not_announced_and_disappearance_is_not_cancellation():
    previous = observe(response([event(actual=None)]))
    current = observe()
    assert previous.events[0].to_private_dict()["announcement_status"] is None
    assert current.events == () and assess(current).feed_coverage == "UNKNOWN"
    assert len(previous.events) == 1  # immutable old observation is not revised


def test_duplicate_rows_are_retained_and_block_not_silently_deduplicated():
    observation = observe(response([event(), event()]))
    assert len(observation.events) == 2
    assert observation.diagnostics == ("EVENT_DUPLICATE_FISCAL_PERIOD",)
    assert assess(observation, evidence=evidence(observation), verifier=lambda *_: True).feed_coverage == "UNKNOWN"


@pytest.mark.parametrize("body,reason", [
    (response([event(code="OTHER.US")]), "EVENT_UNREQUESTED_SYMBOL"),
    (response([event(report_date="2026-09-22")]), "EVENT_OUTSIDE_REQUEST_WINDOW"),
    (response([], **{"to": "2026-09-20"}), "RESPONSE_WINDOW_MISMATCH"),
    (response([], symbols="OTHER.US"), "RESPONSE_SYMBOLS_MISMATCH"),
    (response([], symbols="TEST.US,TEST.US"), "RESPONSE_SYMBOLS_MISMATCH"),
])
def test_symbol_and_date_window_discrepancies_are_explicit(body, reason):
    observation = observe(body)
    assert reason in observation.diagnostics
    assert assess(observation, evidence=evidence(observation), verifier=lambda *_: True).feed_coverage == "UNKNOWN"


def test_multi_symbol_absence_does_not_inherit_other_symbols_coverage():
    observation = observe(response([event(code="OTHER.US")]), request_symbols=("TEST.US", "OTHER.US"))
    assert observation.parse_status == "OBSERVED"
    result = assess(observation, evidence=evidence(observation, symbol="OTHER.US"), verifier=lambda *_: True)
    assert result.observed_event_count == 0 and result.feed_coverage == "UNKNOWN"
    assert "COVERAGE_BINDING_MISMATCH" in result.diagnostics


def test_symbols_echo_without_dates_is_accepted_but_does_not_prove_window():
    observation = observe({"type": "Earnings", "symbols": "TEST.US", "earnings": []})
    assert observation.parse_status == "OBSERVED" and assess(observation).feed_coverage == "UNKNOWN"


def test_no_symbol_filter_can_be_assessed_only_with_per_symbol_external_evidence():
    observation = observe(request_symbols=())
    assert assess(observation).feed_coverage == "UNKNOWN"
    assert assess(observation, evidence=evidence(observation), verifier=lambda *_: True).feed_coverage == "VERIFIED"


def test_later_receipt_or_historical_backfill_cannot_enter_past_decision():
    observation = observe(available_at=DECISION + timedelta(microseconds=1))
    calls = []
    result = assess(observation, evidence=evidence(observation), verifier=lambda *_: calls.append(True) or True)
    assert "OBSERVATION_NOT_CAUSAL" in result.diagnostics and not calls
    assert result.feed_coverage == "UNKNOWN"


@pytest.mark.parametrize("changes,reason", [
    ({"request_from": date(2026, 9, 22)}, "REQUEST_WINDOW_INVALID"),
    ({"request_from": START}, "REQUEST_WINDOW_INVALID"),
    ({"request_symbols": ("TEST.US", "TEST.US")}, "REQUEST_SYMBOLS_INVALID"),
    ({"request_symbols": ["TEST.US"]}, "REQUEST_SYMBOLS_INVALID"),
    ({"http_status": True}, "HTTP_STATUS_INVALID"),
    ({"transport_complete": 1}, "TRANSPORT_COMPLETE_INVALID"),
    ({"body_sha256": "a" * 64}, "BODY_HASH_MISMATCH"),
    ({"request_started_at": DECISION}, "RECEIPT_CLOCK_ORDER"),
    ({"response_received_at": RECEIVED.replace(tzinfo=None)}, "CLOCK_NOT_AWARE"),
    ({"available_at": START}, "RECEIPT_CLOCK_ORDER"),
])
def test_invalid_receipts_raise_only_controlled_codes(changes, reason):
    with pytest.raises(EarningsInputError, match="^" + reason + "$"):
        observe(**changes)


def test_incomplete_transport_and_wrong_content_type_block():
    assert observe(transport_complete=False).parse_status == "INCOMPLETE_TRANSPORT"
    assert observe(content_type="text/html").diagnostics == ("CONTENT_TYPE_NOT_JSON",)
    assert observe(content_type="Application/JSON; charset=utf-8").parse_status == "OBSERVED"


def test_timezone_offsets_preserved_by_instant_not_treated_as_event_times():
    offset = timezone(timedelta(hours=-4))
    observation = observe(request_started_at=START.astimezone(offset), response_received_at=RECEIVED.astimezone(offset),
                          available_at=AVAILABLE.astimezone(offset))
    assert observation.public_summary()["response_received_at"] == RECEIVED.isoformat()
    assert not observation.events


def test_parser_preserves_entire_body_bytes_without_output_or_nominal_public_data(capsys):
    raw = b'  {"type":"Earnings", "description":"' + SECRET.encode() + b'", "earnings":[]}\n'
    observation = observe(raw=raw)
    assert observation.raw_body == raw
    assert base64.b64decode(observation.to_private_dict()["raw_body_base64"]) == raw
    public = json.dumps(observation.public_summary())
    assert SECRET not in public and "TEST.US" not in public
    assert capsys.readouterr() == ("", "")
    with pytest.raises(FrozenInstanceError):
        observation.parse_status = "FORGED"


def test_per_symbol_assessment_does_not_rescan_complete_body(monkeypatch):
    from app import r2d2_v2_earnings_source as module
    observation = observe()
    original = module._sha
    def reject_body_rehash(data):
        assert data is not observation.raw_body
        return original(data)
    monkeypatch.setattr(module, "_sha", reject_body_rehash)
    for _ in range(3):
        assert assess(observation).feed_coverage == "UNKNOWN"


def test_module_has_only_standard_library_imports_and_no_io_primitives():
    from app import r2d2_v2_earnings_source as module
    tree = ast.parse(Path(module.__file__).read_text())
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imports |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert imports <= {"__future__", "base64", "dataclasses", "datetime", "hashlib", "json", "math", "re", "typing"}
    calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not calls & {"open", "print", "exec", "eval", "compile", "__import__"}
