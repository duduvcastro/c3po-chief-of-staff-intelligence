# Session index isolation candidate — 29 September 2026

Status: offline implementation candidate with focused local tests; not deployed
and not approved as complete. Exact-head persistent collector and capacity gates
remain required.

The newly requested index per session is additional work beyond the implemented
P2.4 gap/session attribution fix. The legacy flat adapter opens one SQLite journal path, emits the fixed
`massive-am-journal-v1` source ID and acknowledges one scalar `massive_sequence`.
The enabled worker now selects an epoch-bound session catalog and a versioned
per-session cursor. Flat roots and scalar cursors are refused by this new reader;
no implicit migration or cursor reset is implemented.

## Implemented candidate contract

1. The catalog uses an epoch-bound parent directory containing strict `session_date=YYYY-MM-DD`
   children. Each child contains its own evidence, SQLite index and producer
   lock. Its immutable manifest is bound to epoch, session and approved symbol-list
   (stored canonical sorted symbols). A repeated start may reopen the same manifest; a changed same-session
   list must fail. Do not rename, delete or silently adopt the old flat root.
2. Scope producer recovery to its child journal and session. Enforce index and
   evidence caps independently in every child. Preserve every prior child.
   Measure parent filesystem free space before connecting (at least 50 GiB),
   plus aggregate retained bytes and current-session bytes for budget receipts.
3. Add a session-aware reader rather than changing the existing scalar adapter
   in place. Its versioned cursor maps session to acknowledged local sequence;
   its snapshot pins the discovered session set and each journal's high-water
   mark. Require every cursor-referenced session to remain present. Newly
   created sessions appear only in the next snapshot. Bound directory count,
   opened files, receipts and bytes per page.
4. Qualify envelope source IDs with epoch/session so each local sequence has its
   own continuity domain. Keep receipt clocks and payload identity unchanged;
   recompute the envelope hash using the new source identity. Preserve source
   receipts and cursor in the same collector transaction. No cursor reset is
   inferred from a path or calendar rollover.
5. Drain older unacknowledged receipts causally while admitting the new session
   journal. Preserve the conservative raw quote horizon for incomplete receipt
   groups. The composite proof keys already contain session; they must not
   resolve a different session's barrier. Discovery of an old append must not
   be skipped merely because its former high-water mark was acknowledged.
6. Bind the worker's configured parent to the release epoch. A fresh epoch may
   start with the new adapter; an old scalar cursor requires an explicit
   migration contract or fail-closed refusal. Update ACK extraction to expose
   per-session acknowledgements. Any single-journal retention planner must
   require an explicit matching session; no deletion is part of this work.

The child cursor and frozen snapshot use the exact shape
`{"version":2,"epoch":"…","sessions":{"YYYY-MM-DD":local_sequence}}`.
The outer composite cursor remains version 2. The worker reads the configured
journal directory as the parent catalog and binds it to `release.epoch`.
Manifest device/inode bindings reject an ordinary copied or replaced parent or
session directory after restart. Filesystem relocation therefore requires a
separate explicit migration; it is never inferred by the reader.

A `ready.json` marker is published only after the child SQLite schema verifies.
Until publication the reader reports the existing transient append diagnostic
and preserves its cursor. The producer publishes readiness before recovery and
before any provider connection.

## Acceptance evidence

- Two and three consecutive synthetic sessions with different daily lists and
  overlapping portfolio holdings; each index starts at 1 independently.
- A committed old-session backlog is never replayed, and an uncommitted backlog
  remains offered after new-session creation and process restart.
- Transaction rollback leaves every session cursor unchanged. Corruption,
  missing/replaced session directories and a wrong epoch/manifest refuse input.
- A snapshot remains stable when a new session appears; subsequent polling
  discovers it without source sequence gaps or duplicate receipt IDs.
- A split group exceeding 4096 receipts keeps quotes held until its tail is
  consumed, including near a session boundary.
- Per-session capacity exhaustion refuses that session without touching old
  evidence. Aggregate free-space refusal occurs before provider connection.
- Persistent PostgreSQL collector proof binds session cursors, BAR/gap evidence
  and portfolio state; local SQLite-only tests are insufficient to claim this.
- Re-run exact-head package, replay/restart and consumer regression gates.

## Remaining proof and dependencies

Reader/cursor identity, producer manifests, worker binding and ACK extraction
are implemented as an offline candidate. A ready marker separates session
manifest creation from publishing a fully initialized SQLite schema. Focused
local tests include two daily symbol lists, stable snapshots, delayed old-session
appends, local sequence resets with distinct source identities, a 4100-receipt
group, malformed cursors and transactional SQLite consumer rollback/restart.

Exact-head PostgreSQL/integrated proof, full-session capacity evidence and
review remain separate required gates. Local tests do not grant activation.

No activation authority is implied by this document or its local test results.
The earlier gap/session attribution fix alone did not provide physical isolation;
the new parent/session catalog and versioned reader provide the candidate path.
