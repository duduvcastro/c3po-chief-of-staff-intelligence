from __future__ import annotations

import hashlib
import io
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from app.r2d2_v2_risk_acquisition import SourceReceipt, SourceRequest
from app.r2d2_v2_risk_transport import BoundedRiskTransport, PrivateRiskSpool, RiskTransportError


class Response(io.BytesIO):
    def __init__(self, url: str, body: bytes, status: int = 200, headers: dict[str, str] | None = None):
        super().__init__(body)
        self.url, self.status, self.headers = url, status, headers or {}

    def geturl(self) -> str:
        return self.url


class Opener:
    def __init__(self, body: bytes = b'[]', *, redirect: bool = False,
                 headers: dict[str, str] | None = None, status: int = 200):
        self.body, self.redirect, self.headers, self.status = body, redirect, headers, status
        self.calls: list[tuple[str, float]] = []

    def open(self, req, *, timeout):
        self.calls.append((req.full_url, timeout))
        return Response('https://attacker.invalid' if self.redirect else req.full_url,
                        self.body, self.status, self.headers)


def request() -> SourceRequest:
    return SourceRequest('fmp', '/stable/grades', {'symbol': 'TEST'})


def receipt(*, diagnostic: str | None = None) -> SourceReceipt:
    now = datetime(2026, 9, 17, tzinfo=timezone.utc)
    body = b'[]'
    return SourceReceipt(request(), now, now, 200, body, hashlib.sha256(body).hexdigest(), diagnostic)


def test_token_only_added_inside_transport():
    opener = Opener()
    transport = BoundedRiskTransport(lambda _: 'private-token', opener=opener)
    reply = transport(request())
    assert reply.body == b'[]'
    url, timeout = opener.calls[0]
    assert urlsplit(url).netloc == 'financialmodelingprep.com'
    assert parse_qs(urlsplit(url).query) == {'symbol': ['TEST'], 'apikey': ['private-token']}
    assert 'private-token' not in repr(request())
    assert timeout == 15


@pytest.mark.parametrize('bad', [
    SourceRequest('other', '/stable/grades', {'symbol': 'TEST'}),
    SourceRequest('fmp', 'https://evil.invalid', {'symbol': 'TEST'}),
    SourceRequest('fmp', '/stable/grades', {'symbol': '../ABC'}),
    SourceRequest('fmp', '/stable/grades', {'symbol': 'TEST', 'apikey': 'leak'}),
    SourceRequest('eodhd', '/api/sec-filings/TEST/form4', {'page[offset]': -1, 'page[limit]': 100}),
    SourceRequest('fmp', '/stable/institutional-ownership/symbol-positions-summary',
                  {'symbol': 'TEST', 'year': 2026, 'quarter': 5}),
])
def test_invalid_destination_or_parameters_never_resolve_secret(bad):
    def forbidden(_):
        pytest.fail('credential resolver was called')
    with pytest.raises(RiskTransportError, match='REQUEST_REJECTED'):
        BoundedRiskTransport(forbidden)(bad)


@pytest.mark.parametrize('opener', [
    Opener(redirect=True), Opener(b'123456', headers={'Content-Length': '6'}),
    Opener(b'123456'), Opener(headers={'Content-Encoding': 'gzip'}),
    Opener(b'key'),
])
def test_redirect_oversize_encoding_and_reflected_secret_rejected(opener):
    with pytest.raises(RiskTransportError, match='HTTP_TRANSPORT_FAILED') as error:
        BoundedRiskTransport(lambda _: 'key', opener=opener, max_body_bytes=5)(request())
    assert 'key' not in str(error.value)
    assert error.value.__suppress_context__


def test_provider_error_body_never_returned():
    transport = BoundedRiskTransport(lambda _: 'key', opener=Opener(b'key reflected', status=403))
    assert transport(request()).body == b''


def test_exceptions_do_not_expose_url_or_credential():
    class Broken:
        def open(self, *args, **kwargs):
            raise RuntimeError('https://provider?apikey=private-token')
    with pytest.raises(RiskTransportError) as error:
        BoundedRiskTransport(lambda _: 'private-token', opener=Broken())(request())
    assert str(error.value) == 'HTTP_TRANSPORT_FAILED'
    assert error.value.__suppress_context__


def test_rate_and_total_request_budgets():
    clock = [0.0]
    opener = Opener()
    transport = BoundedRiskTransport(lambda _: 'key', opener=opener,
                                     max_requests=2, requests_per_minute=1, monotonic=lambda: clock[0])
    transport(request())
    with pytest.raises(RiskTransportError, match='REQUEST_BUDGET_EXHAUSTED'):
        transport(request())
    clock[0] = 61
    transport(request())
    clock[0] = 122
    with pytest.raises(RiskTransportError, match='REQUEST_BUDGET_EXHAUSTED'):
        transport(request())
    assert len(opener.calls) == 2


def test_slow_response_deadline():
    times = iter([0.0, 0.0, 31.0])
    with pytest.raises(RiskTransportError):
        BoundedRiskTransport(lambda _: 'key', opener=Opener(b'[]'), monotonic=lambda: next(times))(request())


def test_spool_hashes_permissions_and_immutable_manifest(tmp_path: Path):
    path = tmp_path / 'run'
    spool = PrivateRiskSpool(path)
    try:
        spool.append(receipt())
        digest = spool.finalize()
        assert stat.S_IMODE(path.stat().st_mode) == 0o700
        manifest_bytes = (path / 'MANIFEST.json').read_bytes()
        assert hashlib.sha256(manifest_bytes).hexdigest() == digest
        manifest = json.loads(manifest_bytes)
        assert manifest['coverage_verified'] is False
        for name, sha in manifest['files'].items():
            assert hashlib.sha256((path / name).read_bytes()).hexdigest() == sha
            assert stat.S_IMODE((path / name).stat().st_mode) == 0o600
        with pytest.raises(ValueError):
            spool.append(receipt())
        with pytest.raises(ValueError):
            spool.finalize()
    finally:
        spool.close()
    with pytest.raises(FileExistsError):
        PrivateRiskSpool(path)


def test_failed_receipt_and_interrupted_run_have_no_success_manifest(tmp_path: Path):
    path = tmp_path / 'run'
    spool = PrivateRiskSpool(path)
    try:
        spool.append(receipt(diagnostic='TRANSPORT_FAILED'))
        with pytest.raises(ValueError, match='SPOOL_NOT_COMPLETE'):
            spool.finalize()
    finally:
        spool.close()
    assert not (path / 'MANIFEST.json').exists()


def test_symlink_parent_rejected(tmp_path: Path):
    (tmp_path / 'link').symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(OSError):
        PrivateRiskSpool(tmp_path / 'link' / 'run')
    assert not (tmp_path / 'run').exists()


def test_symlink_receipt_target_never_followed(tmp_path: Path):
    target = tmp_path / 'target'
    target.write_bytes(b'untouched')
    path = tmp_path / 'run'
    spool = PrivateRiskSpool(path)
    try:
        (path / '000000.body').symlink_to(target)
        with pytest.raises(FileExistsError):
            spool.append(receipt())
        with pytest.raises(ValueError):
            spool.finalize()
        assert target.read_bytes() == b'untouched'
    finally:
        spool.close()


def test_write_failure_prevents_completion(tmp_path: Path, monkeypatch):
    path = tmp_path / 'run'
    spool = PrivateRiskSpool(path)
    def broken(*args, **kwargs):
        raise OSError('disk failure')
    monkeypatch.setattr(os, 'fsync', broken)
    try:
        with pytest.raises(OSError):
            spool.append(receipt())
        with pytest.raises(ValueError):
            spool.finalize()
        assert not (path / 'MANIFEST.json').exists()
    finally:
        spool.close()


def test_changed_receipt_is_not_sealed(tmp_path: Path):
    path = tmp_path / 'run'
    spool = PrivateRiskSpool(path)
    try:
        spool.append(receipt())
        (path / '000000.body').write_bytes(b'changed')
        with pytest.raises(ValueError, match='SPOOL_HASH_INVALID'):
            spool.finalize()
        assert not (path / 'MANIFEST.json').exists()
    finally:
        spool.close()


def test_directory_fsync_failure_does_not_leave_manifest(tmp_path: Path, monkeypatch):
    path = tmp_path / 'run'
    spool = PrivateRiskSpool(path)
    try:
        spool.append(receipt())
        original = os.fsync
        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError('directory durability failed')
            original(fd)
        monkeypatch.setattr(os, 'fsync', fail_directory)
        with pytest.raises(OSError):
            spool.finalize()
        assert not (path / 'MANIFEST.json').exists()
    finally:
        spool.close()


@pytest.mark.parametrize('status', [403, 404, 429, 503])
def test_real_urllib_http_error_preserves_only_status_in_receipt(status):
    from urllib.error import HTTPError
    from app.r2d2_v2_risk_acquisition import RiskAcquirer
    class Reject:
        def open(self, *args, **kwargs):
            raise HTTPError('https://provider/?apikey=private-token', status,
                            'private-token', {}, io.BytesIO(b'private-token'))
    now = datetime(2026, 9, 17, tzinfo=timezone.utc)
    acquired = RiskAcquirer(BoundedRiskTransport(lambda _: 'private-token', opener=Reject()), lambda: now).grades('TEST')
    stored = acquired.receipts[0]
    assert stored.status == status
    assert stored.diagnostic == 'HTTP_FAILED'
    assert stored.body == b''
    assert 'private-token' not in repr(stored)


def test_long_fundamentals_symbol_suffix_but_fmp_limit_unchanged():
    from app.r2d2_v2_risk_acquisition import RiskAcquirer
    now = datetime(2026, 9, 17, tzinfo=timezone.utc)
    transport = BoundedRiskTransport(lambda _: 'private-token', opener=Opener())
    acquired = RiskAcquirer(transport, lambda: now).fundamentals('ABCDEFGHIJKLMNO')
    assert acquired.receipts[0].request.path.endswith('/ABCDEFGHIJKLMNO.US')
    assert acquired.receipts[0].status == 200
    with pytest.raises(RiskTransportError, match='REQUEST_REJECTED'):
        transport(SourceRequest('fmp', '/stable/grades', {'symbol': 'ABCDEFGHIJKLMNOP'}))


def test_spool_directory_permissions_rechecked_at_finalize(tmp_path: Path):
    path = tmp_path / 'run'
    spool = PrivateRiskSpool(path)
    try:
        spool.append(receipt())
        path.chmod(0o755)
        with pytest.raises(ValueError, match='SPOOL_PERMISSIONS_INVALID'):
            spool.finalize()
        assert not (path / 'MANIFEST.json').exists()
    finally:
        spool.close()


def test_spool_concurrent_rewrite_detected_by_same_fd_metadata(tmp_path: Path, monkeypatch):
    path = tmp_path / 'run'
    spool = PrivateRiskSpool(path)
    try:
        spool.append(receipt())
        original = os.fstat
        regular_calls = [0]
        def rewrite_during_read(fd):
            metadata = original(fd)
            if stat.S_ISREG(metadata.st_mode):
                regular_calls[0] += 1
                if regular_calls[0] == 2:
                    # Same bytes but modified metadata: even a restore of the
                    # expected bytes during verification cannot silently pass.
                    with (path / '000000.body').open('wb') as file:
                        file.write(b'[]')
                    os.utime(path / '000000.body', ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1000000))
                    metadata = original(fd)
            return metadata
        monkeypatch.setattr(os, 'fstat', rewrite_during_read)
        with pytest.raises(ValueError, match='SPOOL_CHANGED_DURING_VERIFICATION'):
            spool.finalize()
        assert not (path / 'MANIFEST.json').exists()
    finally:
        spool.close()
