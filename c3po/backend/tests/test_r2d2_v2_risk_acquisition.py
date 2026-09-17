from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from app.r2d2_v2_risk_acquisition import HttpReply, RiskAcquirer


def acquirer(replies, **kwargs):
    seen = []
    tick = iter(datetime(2026, 9, 17, tzinfo=timezone.utc) + timedelta(seconds=i)
                for i in range(1000))
    remaining = iter(replies)

    def transport(request):
        seen.append(request)
        result = next(remaining)
        if isinstance(result, Exception):
            raise result
        return result

    return RiskAcquirer(transport, lambda: next(tick), **kwargs), seen


def page(rows, next_path):
    return HttpReply(200, json.dumps({"data": rows, "links": {"next": next_path}}).encode())


def test_receipt_preserves_actual_bytes_and_factual_clocks():
    raw = b'{ "Technicals" : {"Beta": 1.2} }\n'
    source, seen = acquirer([HttpReply(200, raw)])
    acquisition = source.fundamentals("TEST")
    receipt = acquisition.receipts[0]
    assert receipt.body == raw
    assert receipt.payload_sha256 == hashlib.sha256(raw).hexdigest()
    assert receipt.started_at < receipt.received_at
    assert not acquisition.coverage_verified
    assert seen[0].parameters == {}


def test_partial_insider_pagination_never_becomes_verified_zero():
    source, seen = acquirer([
        page([{"filed_at": "2026-09-16"}],
             "/api/sec-filings/TEST.US/form4?page%5Boffset%5D=1&page%5Blimit%5D=100"),
        RuntimeError("https://provider/?api_token=DO_NOT_DISCLOSE"),
    ])
    result = source.insider("TEST")
    assert not result.traversal_complete
    assert not result.coverage_verified
    assert result.diagnostic == "TRANSPORT_FAILED"
    assert len(result.receipts) == 2
    assert "DO_NOT_DISCLOSE" not in repr(result)
    assert seen[1].parameters["page[offset]"] == 1


def test_explicit_exhaustion_does_not_prove_population_coverage():
    source, _ = acquirer([page([], None)])
    result = source.insider("TEST")
    assert result.traversal_complete
    assert not result.coverage_verified


@pytest.mark.parametrize("next_path", [
    "https://attacker.invalid/api/sec-filings/TEST/form4?page[offset]=1&page[limit]=100",
    "/api/sec-filings/OTHER/form4?page[offset]=1&page[limit]=100",
    "/api/sec-filings/TEST/form4?page[offset]=0&page[limit]=100",
    "/api/sec-filings/TEST/form4?page[offset]=2&page[limit]=100",
    "/api/sec-filings/TEST/form4?page[offset]=1&page[limit]=100&api_token=secret",
])
def test_rejects_cross_symbol_redirect_and_skipped_or_repeated_offset(next_path):
    source, seen = acquirer([page([{}], next_path)])
    result = source.insider("TEST")
    assert result.diagnostic == "FORM4_NEXT_INVALID"
    assert len(seen) == 1


def test_budget_exhaustion_is_incomplete_not_empty_success():
    source, _ = acquirer([page([{}], "/api/sec-filings/TEST/form4?page[offset]=1&page[limit]=100")], max_pages=1)
    assert source.insider("TEST").diagnostic == "PAGE_BUDGET_EXHAUSTED"


@pytest.mark.parametrize("raw", [b'{"x":NaN}', b'{"x":1,"x":2}', b'not-json', b'\xff'])
def test_malformed_json_cannot_pass(raw):
    source, _ = acquirer([HttpReply(200, raw)])
    assert source.grades("TEST").diagnostic == "JSON_INVALID"


def test_http_denial_and_empty_success_are_distinct():
    source, _ = acquirer([HttpReply(403, b'[]'), HttpReply(200, b'[]')])
    assert source.grades("TEST").diagnostic == "HTTP_FAILED"
    empty = source.grades("TEST")
    assert empty.diagnostic is None
    assert not empty.coverage_verified


def test_institutional_request_keeps_exact_quarter():
    source, seen = acquirer([HttpReply(200, b'[]')])
    source.institutional("TEST", year=2026, quarter=2)
    assert seen[0].parameters == {"symbol": "TEST", "year": 2026, "quarter": 2}


def test_page_without_next_is_not_exhaustion():
    source, _ = acquirer([HttpReply(200, b'{"data":[]}')])
    assert source.insider("TEST").diagnostic == "FORM4_NEXT_MISSING"


def test_clock_reversal_refused():
    times = iter([datetime(2026, 9, 17, tzinfo=timezone.utc), datetime(2026, 9, 16, tzinfo=timezone.utc)])
    source = RiskAcquirer(lambda _: HttpReply(200, b'[]'), lambda: next(times))
    with pytest.raises(ValueError, match="CLOCK_INVALID"):
        source.grades("TEST")


def test_size_budget_refused():
    source, _ = acquirer([HttpReply(200, b'[123]')], max_body_bytes=2)
    result = source.grades("TEST")
    assert result.diagnostic == "BODY_REJECTED"
    assert result.receipts[0].body == b''
