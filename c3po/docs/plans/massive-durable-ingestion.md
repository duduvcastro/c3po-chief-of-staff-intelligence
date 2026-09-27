# Massive durable ingestion — implementation contract (draft)

Status: partially implemented offline, not certified for deployment. The composite source is wired behind a default-off flag; local tests exercise the real collector cycle with MemoryShadowStore, synthetic BAR input and quote/trade readers. Test counts and local timings do not establish production coverage or runtime capacity. Local PostgreSQL tests also exercise the unchanged production store with 550 symbols over ten minutes, transaction termination and exact replay, and off-session reconnect without rehabilitation. Session retention/pruning, operational service, full adversarial review and CI remain incomplete. Implementation modules are included in package bindings.

## Existing transaction boundary

`r2d2_v2_shadow.py` calls `prepare_events(now, cursor, snapshot=..., read_clock=...)` and commits the proposed cursor through `_cycle_with_cursor` in the same store transaction as the event receipts. A subsequent page is requested only after the stored cursor matches the proposed cursor. Preserve this acknowledgement rule. Never acknowledge input in the producer or advance a cursor simply because a source read succeeded.

`SpoolShadowSource` currently reads EODHD quote/trade partitions and shares this cursor with the collector. Do not repurpose its existing `files` cursor as a Massive sequence or replace the quote/trade source. A composite source needs versioned independent positions and a common receipt-time horizon, with deterministic ordering and atomic equal-reception groups. Existing cursors require an explicit validated compatibility path, not silent reset.

## Storage and recovery requirements

Use a bounded segmented append-only journal for Massive frame/receipt references, not one FileShadowSource event file per action-minute. Persist exact raw bytes once before exposing receipt records. Each record binds session, connection generation, monotonic sequence, exact raw hash/size and frame index, event bytes, and receipt time. Local gaps explicitly have no provider raw; they must never be labelled provider bars.

Current evidence storage uses content-addressed files and a SQLite receipt sequence, capped at 512 MiB / 500,000 evidence files and 64 MiB index. Before each new evidence write, available space from the anchored directory descriptor must exceed the payload plus a configurable reserve (candidate default 1 GiB); a failed space query refuses the write. This is a check, not a reservation against concurrent disk use. These caps refuse new input when exhausted; they do not constitute a session-retention policy. Root and evidence directory access is descriptor-anchored and no-follow; the SQLite index is securely precreated private and single-link, with bound root/index identities and checks before connection, before use and before commit. Unsafe persistent sidecars refuse before SQLite opens. SQLite itself still opens by pathname: this is not a custom no-follow VFS and does not protect against arbitrary concurrent filesystem mutation by another process running as the same user.

Maintain durable uniqueness for (session, symbol, minute). Exact repeats produce no new observation. Conflicts preserve the original observation and append a gap; they never overwrite OHLC. Persist the seal before acknowledging a gap. On crash, verify journal continuity and referenced hashes before restoring the index. An incomplete tail is not a complete record. Missing/corrupt referenced evidence stops ingestion; no inferred repair or replay of the provider.

The consumer proposes a contiguous sequence prefix bounded by byte, event and elapsed-time budgets. A snapshot pins the read horizon across pages. On transaction failure, the same prefix must be offered again with identical identities and hashes. Keep exact provider reception times on restart; never retimestamp stale bars to make them fresh. Reconnection starts a new generation, emits loss of continuity, and cannot supply bars for minutes whose beginning was not observed.

## Required proof before integration is claimed

- Producer frame through durable journal, composite source, real collector and journal acknowledgement, spanning more than 90 seconds.
- At least 550 symbols over more than eight minutes (exceeding the legacy 4096-file design), bounded memory/files and measured collector duration within its existing budget.
- Missing minute, connection loss, invalid row and OHLC conflict remain DATA_GAP without retroactive fill.
- Failures after raw commit, receipt commit, source read, and before/after collector commit preserve deterministic retry and do not skip input.
- Restart with valid, truncated, corrupted or mismatched sequence/index evidence fails closed where required.
- Composite quote/trade/bar ordering and receipt-time ties do not regress existing event precedence.
- Disk/memory limits, symlink-resistant path access, single-process ownership and full-disk behavior are explicit and tested.

No production activation, release authorization, fresh baseline or coverage certification is implied by this document.

## Retention planning status

A read-only planner now verifies a bounded journal snapshot and identifies only a contiguous old-session prefix below the supplied committed collector sequence. It retains the last acknowledged receipt for source predecessor validation and keeps any raw frame referenced by retained receipts. Invalid/ahead acknowledgements, reversed sessions, exceeded scan limits and concurrent appends refuse a plan. The caller must obtain the acknowledgement from the durable collector transaction; a proposed cursor is insufficient.

This planner does not delete files or index rows. The index now records a retained sequence floor; stale cursors refuse, retained sequences stay monotonic, and missing metadata refuses rather than resetting. Fixture-only prefix removal tests exercise these semantics. Execution, session rollover, exclusive reader/producer maintenance and interruption recovery remain incomplete. Existing pre-floor indexes require explicit reconciliation; the writer does not silently migrate or reset them. No retention or pruning completion is claimed.

Recovery at a new New York session now has an explicit clock-bound policy: retained earlier sessions are fully verified but do not populate current minute identities or connection continuity. Future/reversed sessions and corrupt earlier evidence refuse. The producer enables this policy at startup; the default standalone recovery API still requires an exact session. This is a startup rollover step, not a complete multi-day service or pruning workflow.

Retention preparation can now observe the committed cursor using the unchanged PostgreSQL store consistent read-only snapshot, verify its matching SOURCE_CURSOR journal record, and bind the requested release. A real local PostgreSQL test passed and proved no state mutation. This observation is not deletion authority: local evidence-to-ACK binding, all-consumer coverage and exclusive maintenance are still required before executing pruning.

A bound retention plan now compares every retained acknowledged local envelope with raw receipt hashes from that same verified PostgreSQL snapshot. A local journal with an equal numeric cursor but different evidence refuses. Two real local PostgreSQL tests passed. The result covers one specified consumer only; all-consumer coverage and exclusive maintenance remain prerequisites, and no pruning executor exists yet.

## Open pruning review findings

Before any pruning executor is enabled, a durable retention session cutoff must also reject re-ingestion of removed receipt identities. The retained sequence floor alone prevents stale readers but would not prevent an exact old receipt from receiving a new sequence after its digest row was deleted. No executor currently exposes this state.

The executor must hold exclusive maintenance against the producer and evidence readers, verify coverage for the explicit complete consumer set, and keep a durable pending-unlink inventory in the same transaction as the new floor. Interrupted file removal must remain detectable and must never turn an unverified or newly referenced frame into a deletion candidate. Free-space counters must be rebuilt after maintenance. These are implementation requirements still pending, not passed review claims.
