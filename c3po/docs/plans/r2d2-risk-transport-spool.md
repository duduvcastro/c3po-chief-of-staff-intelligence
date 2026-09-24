# Risk transport and private evidence spool — block 3 component

This is an offline-tested building block, not a completed producer, deployment
or certification. It does not read settings automatically or make calls at
import. The executor supplies the credential resolver from its existing private
settings; the resolver receives only `eodhd` or `fmp`. Credentials never belong in
`SourceRequest`, CLI arguments, receipts or published manifests.

## Transport

`BoundedRiskTransport` accepts only fixed HTTPS provider hosts, fixed endpoint
families and a strict parameter schema: EODHD fundamentals, diagnostic Form 4,
FMP grades and institutional positions summary. The Form 4 endpoint remains
**diagnostic** and does not substitute the origin's `ir_events` insider source.
Proxy environment configuration and redirects are disabled. Requests use JSON
and identity encoding. Credentials are injected immediately before the call.
Provider errors return no response body; unexpected failures produce a fixed
code without chained URLs. Successful bodies reflecting the credential are
rejected before persistence.

Defaults: 15-second socket timeout, 15-second response-read deadline checked
between bounded reads, 16 MiB per body, 2,200 calls per instance and 200 calls in
any rolling minute. All ceilings are configurable downward; hard upper bounds
are enforced. There are no retries or sleeps. Rate exhaustion fails closed so an
executor cannot sleep through a protected window. The instance is sequential,
not thread-safe. The executor must additionally enforce its overall invocation
window and a provider-plan-specific rate lower than the local ceiling whenever
required. A blocking socket read can finish up to one socket-timeout interval
after the response deadline; use process supervision for a strict wall-clock
cutoff. Offline tests inject an opener; production uses the built-in opener only.

An HTTP 200 is not evidence of issuer/window/population completeness. Acquisition
and normalization remain responsible for payload shape, provenance and coverage.

## Spool

`PrivateRiskSpool(Path(...))` creates a **new** run directory with mode `0700`.
Its parent must already exist. Every path component is opened with `O_NOFOLLOW`;
existing runs and symlinks are refused. Payload and receipt files use `0600`,
exclusive temporary files, fsync and exclusive hard-link publication. Private
receipts include symbols and request parameters; publish only aggregate counts
and hashes, never these private bodies or nominal receipt contents.

Each receipt includes original byte SHA-256 and factual acquisition timestamps.
The spool rechecks hashes and file type/permissions before publishing its final
`MANIFEST.json`, which hashes each original payload and receipt. Finalization is
explicit, requires at least one successful receipt, and is prohibited after a
failed receipt, append error or interruption. An interrupted spool cannot be
reopened; reconcile it separately instead of retrying into the same directory.
Close the spool in `finally`. `transport_complete=true` only means the supplied
transport receipts were stored; `coverage_verified` is always false. It does not
assert all symbols or all endpoints were requested. The executor must compare
its predetermined request inventory against these receipts before asserting
complete collection.

Tests cover secret isolation, URL/parameter rejection, redirects, compressed and
oversized bodies, credential reflection, error sanitization, rate/total budgets,
read deadline, file permissions, byte hashes, duplicate runs, symlink attacks,
failed/interrupted writes, changed bytes and failed manifest durability.

Still outside this component: authenticated production execution, full request
inventory/manifest, origin database read in a consistent transaction, risk
normalization, the private historical 20-name counterexample, operational
coverage acceptance, and permission to install or activate anything.

### Review hardening

Real urllib `HTTPError` responses preserve only their numeric 4xx/5xx status in
`SourceReceipt` (including 403/404); response bodies, URLs and provider messages
are discarded. A normalized 15-character unqualified symbol plus the `.US`
suffix is accepted for fundamentals; FMP symbols remain limited to 15 characters.

Before sealing, the spool checks its directory mode again and compares each
file's device, inode, mode, owner, link count, size, mtime and ctime before and
after hashing on the same open descriptor, then compares that descriptor with
the current named directory entry. Concurrent rewrites and replacements detected
during verification prevent a completion manifest. This is append-only behavior
of this writer, not OS-enforced immutability against another process running as
the same Unix user. A same-user mutation after verification remains possible;
consumers must verify manifest hashes when loading, and the executor must retain
exclusive run ownership.

### Fable T-1–T-4 and explicit TLS

The sanitized transport exception is now raised **outside** the exception
handler, after clearing this call frame's token, URL, parameters, HTTP request,
response and body temporaries. Its `__context__` and `__cause__` are null, including
urllib non-redirect 3xx failures. This is deliberately not described as erasing
credentials from the whole process: the external settings/resolver legitimately
owns its credential, and injected test objects may retain their own state.
Production error reporting must continue to exclude frame locals.

Spool diagnostics must be null or match `[A-Z][A-Z0-9_]{0,127}`; free text is
rejected before a file is written. Receipt clocks use the same `_aware` check as
the acquirer, including a non-null UTC offset. Failed construction closes its
opened descriptor and attempts to remove only the newly created empty run
directory; existing directories are never recursively deleted. TLS now receives
an explicit `ssl.create_default_context()` with certificate and hostname checks.

### RC-4bis Finnhub authorization extension

The owner authorized the direct Finnhub path in comment 5718952304. The transport
now admits a **third** fixed HTTPS host, `https://finnhub.io`, and only
`/api/v1/stock/insider-transactions` with exact `symbol`, `from`, `to` keys. Dates
must be strict calendar `YYYY-MM-DD`, ordered, and span at most 180 elapsed days
(181 inclusive calendar dates); `to` cannot be after today's UTC date. Symbols
retain the same uppercase 15-character constraint. Its `token` query credential
is resolved internally. No other Finnhub endpoint is enabled.

Finnhub additionally has a hard rolling **60 requests/minute** ceiling, even if
the caller's global budget permits 300. A smaller caller budget also applies.
There is no retry/sleep. The separate acquisition adapter must establish complete
coverage through the provider's 100-record ceiling and its bounded window
splitting; HTTP success here does not assert coverage. EODHD and FMP requests
retain their previous shapes and credential keys.
