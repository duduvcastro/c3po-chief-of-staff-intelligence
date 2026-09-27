# Massive durable ingestion — implementation contract (draft)

Status: partially implemented offline, not certified for deployment. The composite source is wired behind a default-off flag; local tests exercise the real collector cycle with MemoryShadowStore, synthetic BAR input and quote/trade readers. Test counts and local timings do not establish production coverage or runtime capacity. Session retention/pruning, SQLite path protection, operational service, release bindings and adversarial review remain incomplete.

## Existing transaction boundary

`r2d2_v2_shadow.py` calls `prepare_events(now, cursor, snapshot=..., read_clock=...)` and commits the proposed cursor through `_cycle_with_cursor` in the same store transaction as the event receipts. A subsequent page is requested only after the stored cursor matches the proposed cursor. Preserve this acknowledgement rule. Never acknowledge input in the producer or advance a cursor simply because a source read succeeded.

`SpoolShadowSource` currently reads EODHD quote/trade partitions and shares this cursor with the collector. Do not repurpose its existing `files` cursor as a Massive sequence or replace the quote/trade source. A composite source needs versioned independent positions and a common receipt-time horizon, with deterministic ordering and atomic equal-reception groups. Existing cursors require an explicit validated compatibility path, not silent reset.

## Storage and recovery requirements

Use a bounded segmented append-only journal for Massive frame/receipt references, not one FileShadowSource event file per action-minute. Persist exact raw bytes once before exposing receipt records. Each record binds session, connection generation, monotonic sequence, exact raw hash/size and frame index, event bytes, and receipt time. Local gaps explicitly have no provider raw; they must never be labelled provider bars.

Current evidence storage uses content-addressed files and a SQLite receipt sequence, capped at 512 MiB / 500,000 evidence files and 64 MiB index. Before each new evidence write, available space from the anchored directory descriptor must exceed the payload plus a configurable reserve (candidate default 1 GiB); a failed space query refuses the write. This is a check, not a reservation against concurrent disk use. These caps refuse new input when exhausted; they do not constitute a session-retention policy. Root and evidence directory access is descriptor-anchored and no-follow; the SQLite open path still requires hardening.

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
