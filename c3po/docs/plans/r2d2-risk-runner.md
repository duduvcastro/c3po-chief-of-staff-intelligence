# Direct insider capture runner — local preparation only

`capture_direct_insider_batch` captures provider receipts via injected transport and compares independently assessed counts with a separate database reading. It does not synchronize events, write the database, install policy, change epoch, deploy or authorize execution. The host executor must verify pinned manifest, authorization, window and source pins.

Inputs: ordered unique entries `{symbol, market:'US', identity:SourceReceipt|null}` (up to 550), namespace/session date, factual `query_cutoff_at`, new output directory, clock, transport and DB reader. DIAG-R4, DIAG-ENSAIO and SHADOW namespaces must match the date; SHADOW here is artifact preparation, never activation. Omitted cutoff uses batch start, fixed for all entries.

`runtime_dependencies(settings=None, connection_factory=None, clock=..., max_total_requests=..., max_body_bytes=...)` creates lazy real adapters. Existing container settings supply `C3PO_DATABASE_URL`, `C3PO_FINNHUB_API_TOKEN`/`FINNHUB_API_TOKEN`, `C3PO_EODHD_API_TOKEN`/`EODHD_API_TOKEN`. No secret appears in receipts/stdout. Construction makes no network/DB call. HTTP retains TLS/allowlist/timeout/response limits. Pacing is at most 50 requests per 61 seconds (lower if configured), and invokes the supplied host clock/window guard after sleeping immediately before HTTP.

The real reader uses `Database.connection`, sets REPEATABLE READ and READ ONLY as the first transaction statement and verifies both. It sets a 15-second statement timeout and selects bounded US/sec/Insider Transaction rows for each symbol from cutoff minus 180 days through cutoff inclusive. Original DB direction logic computes counts. Differences never trigger ingestion; DB counts do not prove coverage. Transaction/read timestamps must be ordered and no earlier than cutoff. DB failures are sanitized.

Defaults: 2200 total HTTP attempts, 128 Finnhub requests and 100 EODHD pages per symbol, 256 MiB total response bytes, 1800 seconds elapsed, 16 MiB per response and 15 seconds per request. The host manifest should set actual budgets. Global exhaustion blocks later calls and completed manifest, including fallback calls. Pacing consumes elapsed budget; supplied host guard remains authoritative after waiting.

New directory is 0700 with no symlink traversal. Files are 0600, exclusive, published from fsynced temporary bytes without overwrite. Final verification checks modes, hashes and concurrent metadata changes before MANIFEST.json is published last. Failure/interruption may retain private partial files but no completed manifest. Returned entries contain names, relative snapshot/comparison paths and hashes, received_at and coverage flags. Keep these private; publish only counts and manifest hash. `coverage_unknown` is distinct from verified zero. Capture completion is not READY or production GO.

Tests use synthetic fixtures only, not a real contemporary sample.

The same read-only transaction queries `current_user` and `rolsuper` from `pg_catalog.pg_roles` without interpolated parameters. The private receipt records `database_role` and `is_superuser:false`; missing/invalid identity or any non-false superuser result stops before the event query. The batch also rejects injected receipts without this attestation. No credential or role is created/altered by this check.
