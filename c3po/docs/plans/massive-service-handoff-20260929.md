# Massive daily producer: offline service candidate

Status: implemented and tested offline; **not installed, connected, deployed or approved for live operation**. This does not establish provider entitlement, account connection exclusivity or 550-symbol delivery coverage.

## Explicit process contract

`app.r2d2_v2_massive_producer` now exposes `run_session` and a module entrypoint. An external supervisor must invoke a single daily process under the chosen OS owner, using the same epoch-bound parent journal root as the approved collector. Each session writes a distinct child index under `session_date=YYYY-MM-DD`; earlier directories remain intact. The service holds a parent producer lock for its lifetime, and the daily producer retains its child producer and maintenance locks. It never reconnects or retries automatically.

Required arguments: `--journal-root ABSOLUTE_DIRECTORY --manifest ABSOLUTE_JSON_FILE`. `--token-env` names the environment variable containing the credential (default `MASSIVE_API_KEY`); the token itself is never a command argument. Secret provisioning belongs to the approved supervisor. The manifest must be a regular file owned by the process uid, must not be writable by group/others, and must be at most 64 KiB. Symlink and FIFO manifests are rejected. Its exact schema is:

```json
{"epoch":"approved-epoch","session":"2026-10-02","symbols":["AAPL","MSFT"],"owner_uid":501}
```

The uid above is only an example. Use the actual approved effective uid and the approved daily list of 1–550 unique symbols. The epoch must match the immutable parent `epoch.json`; the date must match the current New York calendar session. The child `session.json` immutably binds epoch, date and sorted symbol list. Changing that identity on a same-day restart refuses; a later session may publish its own new symbol list. No wildcard or default universe is accepted. The list is copied before loading the secret. Recovery verifies retained evidence; it does not infer continuity from an earlier process.

The session deadline is the official XNYS close plus 91 seconds, including shortened sessions. A run must start before close, with no more than eight hours remaining until that deadline. There is no one-hour default termination: the lower-level connection and producer defaults are eight hours. AM silence no longer triggers the optional application-idle timeout by default: symbols without eligible trades may be silent. The real socket retains ping/pong liveness checks, while scheduler ticks declare each missing minute. A final scheduler tick before STOPPED or SESSION_LIMIT persists the last expired minute even when the deadline is reached exactly. SIGINT/SIGTERM request orderly stop. Exit code 0 means STOPPED or SESSION_LIMIT, not proof of complete data coverage; refusal, idle/auth timeout and failures exit nonzero. Structured stdout reports STARTING and terminal status without exception text or secrets.

A provider minute whose opening predates authentication becomes a durable `MINUTE_CONNECTION_GAP` for that symbol/minute. Its receipt retains the exact received frame hash, size and row index. Successful persistence seals that minute against later filling; the same connection continues to subsequent eligible minutes. Disk failure still stops ingestion.

## Operational inputs still required

- Named process owner and approved host/account; confirm no competing Massive connection outside this cooperative journal lock.
- Approved token provisioning mechanism and account entitlement, without putting the token in logs or arguments.
- Source and daily review/publishing procedure for the dated symbol manifest and approved journal root.
- Installed supervisor/job definition, startup time, alert recipient and explicit restart policy. This change supplies a process contract, not a deployed supervisor.
- Release packaging/CI, full integrated review and separately authorized provider activation.

## Offline evidence

The new `backend/tests/test_r2d2_v2_massive_service.py` covers partial-minute gap/continuity and persistence failure, exception context redaction, a synthetic 6.5-hour transport run, daily manifest and owner validation, calendar deadline, supervisor failure reporting, private manifest loading and unsafe manifest refusal. These tests use injected sockets, clocks and producer callbacks. No provider call is made.

## Session budget gate and measured receipts (Fable5890626597)

No deletion, pruning or rotation is performed by this process. Under the parent producer lock, then the child producer lock, and before constructing the journal or opening a provider connection, the daily service requires at least **50 GiB available** on the journal filesystem, the current child evidence strictly below **512 MiB / 500,000 files**, and that child’s aggregate SQLite index + WAL + SHM + rollback journal strictly below **64 MiB**. These are the current existing evidence/index caps, not an estimated full-session requirement. A measured value exactly at an upper cap refuses; exactly 50 GiB available passes the free-space gate. Existing per-write spool/index safeguards remain in force during the session.

The supervisor receives `BUDGET_START` and `BUDGET_END` receipts carrying session date, actual raw-frame/receipt/index/sidecar byte lengths, total bytes, allocated filesystem blocks converted to bytes, available space and evidence count. End receipts include measured before/after byte deltas and `review_after_sessions: 3`. These are endpoint measurements, not estimated session sizes or peak/transient write-volume measurements. Raw bytes include retained AM frames associated with bars and gap/conflict evidence; they are not claimed to be exclusively valid BAR payloads. Pending evidence files are counted. Review actual receipts after the first three sessions before choosing any revised budget.

On a refused startup, the supervisor receives an explicit `DATA_GAP` with the refusal reason, session and `provider_connected: false`. It is **external operational evidence**, not an entry silently inserted past the full journal's cap. The approved supervisor must durably capture structured stdout/receipts and alert on DATA_GAP/FAILED. An unverified filesystem measurement also refuses startup; an unverified final measurement marks service failure. This process does not install or prove that external capture mechanism.


## Retained session accounting

`RETAINED_BUDGET_START` and `RETAINED_BUDGET_END` measure the entire parent directory, including all retained child indexes/evidence and parent metadata. The 50 GiB free-space gate applies to the parent filesystem and is checked again for the active child. The existing 512 MiB evidence / 64 MiB index limits apply to each child, so preserved prior indexes do not consume a fresh child's index allowance. Aggregate receipts and their deltas remain visible even when retained bytes exceed a single child's cap. Both aggregate and child receipts carry the session date; aggregate receipts also identify the epoch. No previous child is reset, renamed or removed. The legacy `run_producer` API still accepts one flat journal directory; the new `run_session` and CLI require the epoch-bound parent layout. Mixing those layouts refuses.
