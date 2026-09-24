"""Bounded direct-insider capture and independent read-only DB comparison.

The host launcher supplies authorization/window/source pins. This module creates
private evidence only: no DB writes, ingestion sync, policy, epoch or activation.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import uuid
import time
from contextlib import AbstractContextManager, contextmanager
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from app.config import Settings, get_settings
from app.database import Database
from app.r2d2_v2_risk_acquisition import HttpReply, RiskAcquirer, SourceReceipt, SourceRequest
from app.r2d2_v2_risk_direct_insider import DirectInsiderAcquirer, assess_direct_insider
from app.r2d2_v2_risk_executor import _open_dir
from app.r2d2_v2_risk_transport import BoundedRiskTransport, RiskTransportError

ConnectionFactory = Callable[[], AbstractContextManager[Any]]
Clock = Callable[[], datetime]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Any) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('RUNNER_CLOCK_INVALID')
    return value


def _utc(value: Any) -> datetime:
    result = _aware(value)
    if result.utcoffset() != timedelta(0):
        raise ValueError('RUNNER_UTC_REQUIRED')
    return result


def _json(value: Any) -> bytes:
    def temporal(item: Any) -> str:
        if isinstance(item, (datetime, date)):
            return item.isoformat()
        raise ValueError('RUNNER_JSON_TYPE_INVALID')
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                       allow_nan=False, default=temporal) + '\n').encode()


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _valid_database_role(value: Any) -> bool:
    return (isinstance(value, str) and bool(value) and value == value.strip()
            and len(value.encode('utf-8')) <= 63
            and all(character.isprintable() for character in value))


class ReadOnlyInsiderDatabaseReader:
    """Production-capable SQL reader; source counts do not establish coverage."""

    ROLE_SQL = """SELECT current_user, session_user,
        NOT (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls),
        NOT EXISTS (SELECT 1 FROM pg_catalog.pg_auth_members WHERE member=r.oid),
        NOT pg_catalog.has_database_privilege(current_user,pg_catalog.current_database(),'CREATE'),
        NOT pg_catalog.has_database_privilege(current_user,pg_catalog.current_database(),'TEMP')
        FROM pg_catalog.pg_roles r WHERE rolname=current_user"""
    ACL_SQL = """SELECT c.relname,
        pg_catalog.has_table_privilege(current_user,c.oid,'SELECT'),
        NOT pg_catalog.has_table_privilege(current_user,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES'),
        NOT pg_catalog.has_any_column_privilege(current_user,c.oid,'INSERT,UPDATE,REFERENCES'),
        NOT pg_catalog.pg_has_role(current_user,c.relowner,'MEMBER'),
        NOT pg_catalog.has_schema_privilege(current_user,n.oid,'CREATE'),
        NOT c.relrowsecurity
        FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind='r' AND c.relname='ir_events'"""

    SQL = """SELECT source_code, external_id, symbol, market, event_type, published_at, raw_metadata
             FROM public.ir_events
             WHERE market = 'US' AND source_code = 'sec'
               AND event_type = 'Insider Transaction' AND symbol = %s
               AND published_at >= %s AND published_at <= %s
             ORDER BY source_code, external_id
             LIMIT %s"""

    def __init__(self, connection_factory: ConnectionFactory, *, clock: Clock = _now,
                 max_rows: int = 100000) -> None:
        if type(max_rows) is not int or not 1 <= max_rows <= 100000:
            raise ValueError('DATABASE_ROW_BUDGET_INVALID')
        self.connection_factory, self.clock, self.max_rows = connection_factory, clock, max_rows

    def __call__(self, symbol: str, cutoff: datetime) -> dict[str, Any]:
        _aware(cutoff)
        if not re.fullmatch(r'[A-Z][A-Z0-9.-]{0,14}', symbol):
            raise ValueError('DATABASE_SYMBOL_INVALID')
        started = _aware(self.clock())
        if started < cutoff:
            raise ValueError('DATABASE_CLOCK_ORDER_INVALID')
        result = None
        try:
            with self.connection_factory() as connection:
                if connection is None or getattr(connection, 'autocommit', None) is not False:
                    raise ValueError('DATABASE_TRANSACTION_REQUIRED')
                connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
                mode = connection.execute('SHOW transaction_read_only').fetchone()
                if mode is None or mode[0] != 'on':
                    raise ValueError('DATABASE_READ_ONLY_NOT_CONFIRMED')
                isolation = connection.execute('SHOW transaction_isolation').fetchone()
                if isolation is None or isolation[0] != 'repeatable read':
                    raise ValueError('DATABASE_ISOLATION_NOT_CONFIRMED')
                connection.execute("SET LOCAL statement_timeout = '15s'")
                role_row = connection.execute(self.ROLE_SQL).fetchone()
                if (not isinstance(role_row, (tuple, list)) or len(role_row) != 6
                        or not _valid_database_role(role_row[0]) or role_row[1] != role_row[0]
                        or not all(value is True for value in role_row[2:])):
                    raise ValueError('DATABASE_RESTRICTED_ROLE_REQUIRED')
                acl_rows = connection.execute(self.ACL_SQL).fetchall()
                if (len(acl_rows) != 1 or len(acl_rows[0]) != 7 or acl_rows[0][0] != 'ir_events'
                        or not all(value is True for value in acl_rows[0][1:])):
                    raise ValueError('DATABASE_SELECT_ONLY_AUTHORITY_REQUIRED')
                database_role = role_row[0]
                transaction_at = connection.execute('SELECT pg_catalog.transaction_timestamp()').fetchone()[0]
                _aware(transaction_at)
                rows = connection.execute(self.SQL, (symbol, cutoff-timedelta(days=180), cutoff, self.max_rows+1)).fetchall()
                if len(rows) > self.max_rows:
                    raise ValueError('DATABASE_ROW_BUDGET_EXHAUSTED')
                events = []
                counts = {'buy_count': 0, 'sell_count': 0, 'total_count': 0}
                keys = set()
                for row in rows:
                    if len(row) != 7:
                        raise ValueError('DATABASE_ROW_INVALID')
                    source, external_id, observed_symbol, market, event_type, published, metadata = row
                    if (source != 'sec' or observed_symbol != symbol or market != 'US' or event_type != 'Insider Transaction'
                            or not isinstance(external_id, str) or not external_id
                            or not cutoff-timedelta(days=180) <= _aware(published) <= cutoff
                            or (source, external_id) in keys):
                        raise ValueError('DATABASE_ROW_BINDING_INVALID')
                    keys.add((source, external_id))
                    metadata = json.loads(metadata) if isinstance(metadata, str) else metadata or {}
                    if not isinstance(metadata, dict):
                        raise ValueError('DATABASE_METADATA_INVALID')
                    direction = Database._insider_transaction_direction(metadata)
                    if direction:
                        counts['buy_count' if direction > 0 else 'sell_count'] += 1
                        counts['total_count'] += 1
                    events.append({'source_code': source, 'external_id': external_id, 'symbol': symbol,
                                   'market': market, 'event_type': event_type, 'published_at': published,
                                   'raw_metadata': metadata})
                completed = _aware(self.clock())
                if completed < started or not cutoff <= transaction_at <= completed:
                    raise ValueError('DATABASE_CLOCK_ORDER_INVALID')
                result = {'schema': 'RISK_INSIDER_DB_READ_ONLY_V1', 'symbol': symbol, 'market': 'US',
                          'query_cutoff_at': cutoff.isoformat(), 'window_start': (cutoff-timedelta(days=180)).isoformat(),
                          'read_started_at': started.isoformat(), 'received_at': completed.isoformat(),
                          'transaction_at': transaction_at.isoformat(), 'transaction_read_only': True,
                          'database_role': database_role, 'session_role': database_role, 'is_superuser': False,
                          'restricted_role_verified': True, 'select_only_verified': True,
                          'role_authority_checks': list(role_row[2:]), 'table_authority_checks': list(acl_rows[0][1:]),
                          'role_query_sha256': _sha(self.ROLE_SQL.encode()), 'acl_query_sha256': _sha(self.ACL_SQL.encode()),
                          'isolation_level': 'REPEATABLE READ', 'query_sha256': _sha(self.SQL.encode()),
                          'row_count': len(rows), 'counts': counts, 'events_sha256': _sha(_json(events)),
                          'events': events, 'coverage_verified': False}
        except Exception:
            # Do not expose driver exceptions or a DSN/provider secret in logs.
            result = None
        if result is None:
            raise ValueError('DATABASE_READ_ONLY_COMPARISON_FAILED') from None
        return result


def runtime_dependencies(*, settings: Settings | None = None,
                         connection_factory: ConnectionFactory | None = None,
                         clock: Clock = _now, max_total_requests: int = 2200,
                         requests_per_minute: int = 60, max_database_rows: int = 100000,
                         timeout_seconds: float = 15, max_body_bytes: int = 16*1024*1024,
                         monotonic: Callable[[], float] = time.monotonic,
                         sleep: Callable[[float], None] = time.sleep,
                         ) -> tuple[Callable[[SourceRequest], HttpReply], ReadOnlyInsiderDatabaseReader]:
    """Resolve existing container credentials and real DB factory, lazily.

    Creating dependencies makes no HTTP/DB call. Never print settings or capture
    frame locals in exception reporting. No DB.initialize/sync is invoked.
    """
    configured = settings if settings is not None else get_settings()
    if connection_factory is None:
        if not configured.r2d2_risk_database_url:
            raise ValueError('RISK_DEDICATED_DATABASE_CONNECTION_REQUIRED')
        @contextmanager
        def dedicated_connection():
            import psycopg
            with psycopg.connect(configured.r2d2_risk_database_url, connect_timeout=15,
                                 options='-c default_transaction_read_only=on') as connection:
                yield connection
        connection_factory = dedicated_connection
    def credential(provider: str) -> str:
        attributes = {'finnhub': 'finnhub_api_token', 'eodhd': 'eodhd_api_token'}
        if provider not in attributes:
            raise ValueError('PROVIDER_NOT_ALLOWED')
        return str(getattr(configured, attributes[provider]))
    transport = BoundedRiskTransport(credential, timeout=timeout_seconds, max_requests=max_total_requests,
                                     requests_per_minute=requests_per_minute, max_body_bytes=max_body_bytes, monotonic=monotonic)
    paced = PacedRiskTransport(transport, limit=min(50, requests_per_minute), monotonic=monotonic, sleep=sleep, before_request=clock)
    return paced, ReadOnlyInsiderDatabaseReader(connection_factory, clock=clock, max_rows=max_database_rows)


class PacedRiskTransport:
    """Pace before the bounded transport; never turn a rate wait into fallback."""
    def __init__(self, transport: Callable[[SourceRequest], HttpReply], *, limit: int = 50,
                 monotonic: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 before_request: Callable[[], Any] = _now) -> None:
        self.transport, self.limit, self.monotonic, self.sleep = transport, limit, monotonic, sleep
        self.before_request = before_request
        self.times: list[float] = []

    def __call__(self, request: SourceRequest) -> HttpReply:
        if request.provider not in ('finnhub', 'eodhd'):
            raise ValueError('RUNNER_PROVIDER_NOT_ALLOWED')
        now = self.monotonic()
        self.times = [stamp for stamp in self.times if now-stamp < 61]
        if len(self.times) >= self.limit:
            self.sleep(max(0, 61-(now-self.times[0])))
            now = self.monotonic()
            self.times = [stamp for stamp in self.times if now-stamp < 61]
            if len(self.times) >= self.limit:
                raise RiskTransportError('PACING_BUDGET_EXHAUSTED')
        self.before_request()
        self.times.append(now)
        return self.transport(request)


class _BatchSpool:
    def __init__(self, path: Path) -> None:
        parent = _open_dir(path.parent)
        self.fd = -1
        try:
            os.mkdir(path.name, 0o700, dir_fd=parent)
            self.fd = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            if stat.S_IMODE(os.fstat(self.fd).st_mode) != 0o700:
                raise ValueError('RUNNER_SPOOL_PERMISSIONS')
            os.fsync(parent)
        except BaseException:
            if self.fd >= 0:
                os.close(self.fd)
                self.fd = -1
            raise
        finally:
            os.close(parent)
        self.files: dict[str, str] = {}

    def put(self, name: str, value: Any) -> dict[str, str]:
        if stat.S_IMODE(os.fstat(self.fd).st_mode) != 0o700:
            raise ValueError('RUNNER_SPOOL_PERMISSIONS')
        body = _json(value)
        temporary = '.partial-' + uuid.uuid4().hex
        linked = False
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
            with os.fdopen(fd, 'wb') as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd, follow_symlinks=False)
            linked = True
            os.unlink(temporary, dir_fd=self.fd)
            os.fsync(self.fd)
        except BaseException:
            if linked:
                os.unlink(name, dir_fd=self.fd)
            raise
        self.files[name] = _sha(body)
        return {'path': name, 'sha256': self.files[name]}

    def verify(self) -> None:
        if stat.S_IMODE(os.fstat(self.fd).st_mode) != 0o700:
            raise ValueError('RUNNER_SPOOL_PERMISSIONS')
        for name, expected in self.files.items():
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.fd)
            with os.fdopen(fd, 'rb') as handle:
                before = os.fstat(handle.fileno())
                digest = hashlib.file_digest(handle, 'sha256').hexdigest()
                after = os.fstat(handle.fileno())
                if (stat.S_IMODE(before.st_mode) != 0o600 or not stat.S_ISREG(before.st_mode)
                        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                        or digest != expected):
                    raise ValueError('RUNNER_SPOOL_INTEGRITY')

    def close(self) -> None:
        os.close(self.fd)


def capture_direct_insider_batch(
    entries: list[dict[str, Any]], *, output_path: Path, namespace: str, session_date: date,
    clock: Clock, transport: Callable[[SourceRequest], HttpReply],
    database_reader: Callable[[str, datetime], dict[str, Any]], fallback_on_failure: bool = True,
    query_cutoff_at: datetime | None = None, max_symbols: int = 550,
    max_total_bytes: int = 256*1024*1024,
    max_total_requests: int = 2200, max_finnhub_requests_per_symbol: int = 128,
    max_eodhd_pages_per_symbol: int = 100, max_duration_seconds: int = 1800,
) -> dict[str, Any]:
    """Capture private receipts and separate DB differences; no DB ingestion.

    Returned entries contain names and remain private. Publish only ``counts``
    and ``manifest_sha256``. Unknown coverage never becomes verified zero.
    """
    day = session_date.isoformat()
    if (namespace not in {'R2D2-V2-DIAG-R4-' + day, 'R2D2-V2-SHADOW-' + day, 'R2D2-V2-DIAG-ENSAIO-' + day}
            or not isinstance(entries, list) or not 1 <= len(entries) <= max_symbols or not 1 <= max_symbols <= 550
            or type(max_total_bytes) is not int or not 1 <= max_total_bytes <= 1024*1024*1024
            or any(not isinstance(entry, dict) for entry in entries)
            or type(max_total_requests) is not int or not 1 <= max_total_requests <= 10000
            or type(max_duration_seconds) is not int or not 1 <= max_duration_seconds <= 3600):
        raise ValueError('RUNNER_SCOPE_OR_BUDGET_INVALID')
    symbols = [entry.get('symbol') for entry in entries]
    if (any(not isinstance(symbol, str) or not re.fullmatch(r'[A-Z][A-Z0-9.-]{0,14}', symbol) for symbol in symbols)
            or len(set(symbols)) != len(symbols) or any(entry.get('market') != 'US' for entry in entries)):
        raise ValueError('RUNNER_SYMBOL_LIST_INVALID')
    for entry in entries:
        identity = entry.get('identity')
        if identity is not None and not isinstance(identity, SourceReceipt):
            raise ValueError('RUNNER_IDENTITY_INVALID')
    started = _utc(clock())
    deadline = started + timedelta(seconds=max_duration_seconds)
    fixed_cutoff = _utc(query_cutoff_at) if query_cutoff_at is not None else started
    if fixed_cutoff > started:
        raise ValueError("RUNNER_CUTOFF_IN_FUTURE")
    total_bytes = 0
    request_count = 0
    budget_exhausted = False
    def guarded_transport(request: SourceRequest) -> HttpReply:
        nonlocal request_count, budget_exhausted, total_bytes
        if request.provider not in ('finnhub', 'eodhd'):
            budget_exhausted = True
            raise ValueError('RUNNER_PROVIDER_NOT_ALLOWED')
        if budget_exhausted or request_count >= max_total_requests or _aware(clock()) > deadline:
            budget_exhausted = True
            raise ValueError('RUNNER_REQUEST_BUDGET_EXHAUSTED')
        request_count += 1
        try:
            reply = transport(request)
            total_bytes += len(reply.body)
            if total_bytes > max_total_bytes or _aware(clock()) > deadline:
                budget_exhausted = True
                raise ValueError("RUNNER_BODY_OR_TIME_BUDGET_EXHAUSTED")
            return reply
        except RiskTransportError as error:
            if 'BUDGET_EXHAUSTED' in str(error):
                budget_exhausted = True
            raise
    acquirer = RiskAcquirer(guarded_transport, clock, max_pages=max_eodhd_pages_per_symbol)
    direct = DirectInsiderAcquirer(acquirer, max_requests=max_finnhub_requests_per_symbol,
                                  fallback_on_failure=fallback_on_failure)
    spool = _BatchSpool(output_path)
    private_entries = []
    counts = {'symbols': len(entries), 'captured': 0, 'coverage_verified': 0, 'coverage_unknown': 0,
              'db_comparable': 0, 'db_equal': 0, 'db_different': 0, 'http_attempts': 0}
    try:
        for index, entry in enumerate(entries):
            observed = _aware(clock())
            cutoff = fixed_cutoff
            if not started <= observed <= deadline:
                raise ValueError('RUNNER_CAPTURE_WINDOW_EXHAUSTED')
            symbol = entry['symbol']
            comparison = database_reader(symbol, cutoff)
            if (comparison.get('symbol') != symbol or comparison.get('market') != 'US'
                    or comparison.get('query_cutoff_at') != cutoff.isoformat()
                    or comparison.get('transaction_read_only') is not True
                    or not _valid_database_role(comparison.get('database_role'))
                    or comparison.get('is_superuser') is not False
                    or comparison.get('session_role') != comparison.get('database_role')
                    or comparison.get('restricted_role_verified') is not True
                    or comparison.get('select_only_verified') is not True):
                raise ValueError('RUNNER_DATABASE_RECEIPT_INVALID')
            db_started = _aware(datetime.fromisoformat(comparison['read_started_at']))
            db_completed = _aware(datetime.fromisoformat(comparison['received_at']))
            db_transaction = _aware(datetime.fromisoformat(comparison['transaction_at']))
            if not cutoff <= db_started <= db_completed <= _aware(clock()) or not cutoff <= db_transaction <= db_completed:
                raise ValueError('RUNNER_DATABASE_CLOCK_INVALID')
            database_ref = spool.put(f'{index:06d}.database.private.json', comparison)
            snapshot = direct.acquire(symbol, cutoff=cutoff, eodhd_identity=entry.get('identity'))
            received = _aware(clock())
            snapshot_ref = spool.put(f'{index:06d}.direct.private.json', snapshot)
            if budget_exhausted or received > deadline or received < cutoff:
                raise ValueError('RUNNER_CAPTURE_BUDGET_EXHAUSTED')
            activity, evidence, diagnostics = assess_direct_insider(snapshot, received_at=received, computed_at=received)
            verified = activity is not None and evidence.coverage_verified
            direct_counts = asdict(activity) if activity is not None else None
            db_counts = comparison.get('counts')
            if (not isinstance(db_counts, dict) or set(db_counts) != {'buy_count', 'sell_count', 'total_count'}
                    or any(type(value) is not int or value < 0 for value in db_counts.values())
                    or db_counts['buy_count'] + db_counts['sell_count'] != db_counts['total_count']):
                raise ValueError('RUNNER_DATABASE_COUNTS_INVALID')
            equal = direct_counts == db_counts if verified else None
            counts['captured'] += 1
            counts['coverage_verified' if verified else 'coverage_unknown'] += 1
            if equal is not None:
                counts['db_comparable'] += 1
                counts['db_equal' if equal else 'db_different'] += 1
            assessment_ref = spool.put(f'{index:06d}.comparison.private.json', {
                'schema': 'RISK_DIRECT_VS_DB_V1', 'symbol': symbol, 'market': 'US',
                'query_cutoff_at': cutoff.isoformat(), 'direct_counts': direct_counts,
                'database_counts': db_counts, 'counts_equal': equal,
                'coverage_verified': verified, 'diagnostics': diagnostics,
                'evidence': asdict(evidence), 'db_receipt': database_ref,
                'direct_snapshot': snapshot_ref, 'database_ingestion_performed': False})
            private_entries.append({'symbol': symbol, 'market': 'US', 'direct_snapshot': snapshot_ref,
                                    'received_at': received.isoformat(), 'db_comparison': assessment_ref,
                                    'database_receipt': database_ref, 'coverage_verified': verified})
        completed = _aware(clock())
        if completed > deadline or completed < started:
            raise ValueError('RUNNER_CAPTURE_WINDOW_EXHAUSTED')
        counts['http_attempts'] = request_count
        manifest = {'schema': 'RISK_DIRECT_BATCH_CAPTURE_V1', 'namespace': namespace,
                    'session_date': day, 'started_at': started.isoformat(), 'completed_at': completed.isoformat(),
                    'counts': counts, 'entries': private_entries, 'files': dict(spool.files),
                    'request_budget': max_total_requests, 'body_bytes': total_bytes,
                    'body_byte_budget': max_total_bytes, 'query_cutoff_at': fixed_cutoff.isoformat(), 'duration_budget_seconds': max_duration_seconds,
                    'phase_pending': len(entries)-counts['captured'], 'database_writes': False,
                    'production_activation': False, 'authorization_granted': False}
        spool.verify()
        manifest_ref = spool.put('MANIFEST.json', manifest)
        return {'entries': private_entries, 'manifest_sha256': manifest_ref['sha256'], 'counts': counts,
                'namespace': namespace, 'session_date': day, 'phase_pending': 0,
                'production_activation': False, 'database_writes': False}
    finally:
        spool.close()
