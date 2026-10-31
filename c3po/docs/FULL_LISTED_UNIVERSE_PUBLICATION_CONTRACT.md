# Atomic publication: closed preparation and isolated integration

`app.listed_universe_publication` prepares a hash-bound storage read set and
exercises composition in a private copy of the real in-memory Database double.
It has no CLI, PostgreSQL writer, source-switch, production activation or schedule
entry point. `production_preflight()` always denies release. No JSON flag,
ownership callback or receipt can enable it.

## What the integration exercises

Preparation reads the current canonical generation, chain tip, last explicit
order, all three stage snapshots and their dual immutable records through the
existing Database interfaces. It also binds current official cycles, carried
targeted admissions, registered targeted records and their snapshots. A stage ID
from a checkpoint alone is insufficient.

Every non-ETF catalogue name must occur once as valued or not evaluable with a
reason. Missing rows cannot disappear; unclassified instruments cannot become
valued equities. The original prediction, stage publication and catalogue receipt
clocks are checked causally against an explicit freshness limit. Both canonical
source records must reproduce `prediction_from_row` exactly. The new boundary
also recomputes the stored V2 core hash: the frozen `stored_prediction` reader
returns V2 records as stored and verifies legacy V1 hashes, so comparing stored
hash strings alone would not detect an altered V2 value.

The sandbox refuses a PostgreSQL-backed Database, copies the memory tables and
holds its own process-local lock. On a work copy it creates three new official
cycle snapshots, appends both canonical sources, invokes the existing cycle
validator, applies the existing targeted recovery policy, and creates one CAS
successor of exactly the expected predecessor. It preserves the selected source
and methodology version. The original TP/buy-in and prediction instant are
unchanged; the new publication clock and `rerun_of` identify the new availability.
The original Database is never altered. Existing freezes and explicit orders can
refuse composition; this module does not thaw or write an explicit order.

The single assignment of the completed private copy is the sandbox commit.
Failures after any market's writes or even after selection insertion discard the
copy. Readers observe the old or new private database, and concurrent attempts on
one predecessor have one winner. These tests exercise the real canonical reader
and validator contracts. They **do not prove PostgreSQL isolation, production
writer exclusion, measured capacity or operational release**. The sandbox does
not pretend that post-commit served-change capture succeeded.

## Existing storage and writer mechanisms

The source references below are to the unchanged base implementation; no listed
protected file was edited.

| Mechanism | Actual behavior and implication |
| --- | --- |
| `backend/app/database.py:201`, `:3885` | `connection()` opens a connection per call. `save_analysis_snapshot` commits a snapshot, then calls the official recording hook outside that transaction. Three calls cannot publish one atomic cohort. |
| `backend/app/database.py:3974`, `:4221` | Prediction inserts and selection inserts have their own commits. Selection invokes served-change capture after its commit. Reusing these committing APIs inside a supposed transaction is insufficient. |
| `backend/app/valuation_official.py:885`, `:1155` | The persistence hook records dual sources, then automatically composes a generation from the latest valid market cycles. It can combine a new single-market legacy cycle with the other markets already served. |
| `backend/app/valuation_official.py:955`, `backend/db/048_valuation_official_tp.sql` | The expected-predecessor read plus unique predecessor/root indexes prevent two successors of one predecessor. They do not forbid a later legacy successor with smaller coverage. No shared publication advisory lock is used here. |
| `backend/app/valuation_worker.py:439` | Nightly calls B3 `screen(refresh=True)`, then US `refresh_all`; they publish independently. A new worker phase alone does not take ownership. |
| `backend/app/market_data/us_screener.py:104`, `:158`, `:822` | The US service has a local `RLock`, builds NASDAQ and NYSE separately and publishes `valuation_universe` through the common hook. A second process is not excluded. US screen/matrix cache misses can also build. |
| `backend/app/market_data/b3_screener.py:189`, `:359`, `:418`, `:3161` | B3 has local locks. IR `refresh_symbols` can republish the whole cached universe; cold and refresh paths also build. The `_persist_universe` call uses the common auto-activation hook. |
| `backend/app/ir_valuation.py:31` | IR respects an existing freeze before claiming updates, then calls B3 refresh. A freeze is a bounded mesa order, not permanent writer ownership and not authority granted to this work. |
| `backend/app/market_data/b3_screener.py:501` | B3 targeted/on-demand `security_valuation` cycles can change the generation through the same recording/admission path. They must participate in any ownership policy while retaining legitimate targeted admissions. |
| `backend/app/one_pager.py:970`, `backend/app/valuation_official.py:380` | US One Pager persists `one_pager_valuation`; `market_of_entity` does not recognize that namespace, so this specific persistence is not a canonical generation writer. Do not invent an ownership blocker for this unrelated snapshot. US screen/matrix cold builds remain canonical writers. |

The regression `test_real_legacy_writer_can_still_shrink_a_later_generation...`
first composes the expanded three-market generation in isolation, then calls the
unchanged real legacy save/hook on a separate copy. It genuinely produces a later
one-name B3 cycle while retaining the expanded US cycles. The preflight therefore
keeps `legacy_writer_ownership_enforced=false` even when every synthetic stage is
well formed and the isolated atomic composition passes.

## PostgreSQL transaction still required

The future additive storage adapter must own **one connection and one commit**;
the existing per-call committing persistence APIs cannot be its implementation.
Before any read used to decide the composition, it needs a consistent lock order
covering `analysis_snapshots`, `valuation_predictions` and
`valuation_official_selection`. A PostgreSQL table lock that conflicts with
ordinary INSERT's row-exclusive lock can serialize old writers during that
transaction even though they do not request a new advisory lock. The exact lock
mode/order, timeout, isolation behavior, FK interactions, failures and concurrent
writers still need real PostgreSQL tests. No lock SQL is installed by this work.

Under those locks the adapter must re-read the genuine chain head and latest
explicit order, check freeze and exact predecessor, revalidate all stage FKs,
canonical records, catalogue reconciliation/freshness, selected source/version
and targeted admissions, append all three official snapshots and dual records,
and insert one selection using the existing unique chain constraints. Any failed
gate or CAS conflict must roll back the entire cohort, with no automatic rebase
over an unseen order. The final activation clock must be read at the actual
insertion boundary after recording; a prepared receipt's old clock is not a
production clock. Record availability must not precede prediction.

After a confirmed commit the adapter must handle the genuine served-change
capture, cache policy and their receipt. It cannot report capture as successful
because the selection was inserted. The sandbox intentionally leaves this false.

## Ownership is the remaining hard integration boundary

Transaction locks release at commit. A queued or later legacy nightly/IR/cache
miss writer can then append a valid capped cycle and activate a successor. CAS
cannot stop that: it correctly extends the newly published predecessor. A local
mutex, new advisory lock, `owner=true` input, matching hash or injected permissive
callback does not constrain writers that never consult it.

The common enforcement points `Database.save_analysis_snapshot` /
`insert_valuation_official_selection`, `valuation_official` activation/admission,
and the US producer are protected by this task's 72-file freeze. Changing only
the unprotected B3/worker entry point cannot cover all those existing writers.
A reviewed solution must either explicitly authorize changes at the frozen
central boundary, or design and test an additive database-enforced policy that
also constrains existing processes/direct writes. No such database policy,
privileged role, trigger, migration, activation flag or ownership token is
invented or installed here. An additive policy would need genuine schema/role
evidence, atomic enablement, compatibility with legitimate IR/targeted updates,
and a reviewed failure/recovery protocol before release. The 72-file freeze is
therefore not a proof that ownership is impossible: the additive route below
remains a concrete engineering option, pending its own evidence and review.

### Additive database enforcement option to review

This option requires no in-place edits to a frozen Python producer. It is a
design for future local DDL/adapter work, not installed DDL or a claimed gate:

1. Put cohort registrations, ownership epochs and the publication function in a
   separate schema owned by a dedicated non-login role. The application role
   must not own that schema, be a member of the owner role, be a superuser, or
   have rights to replace functions/triggers or mutate the registrations.
   `compose.yml` configures API, IR and valuation workers with the same database
   user name, so process names alone cannot identify an owner. That file is not
   proof of the live role's superuser status. Repository migrations do not
   establish separate publication role boundaries; actual role,
   membership, table ownership and privilege evidence is still missing. Do not
   infer them from a connection string or invent a privileged credential.
2. A reviewed `SECURITY DEFINER` publication function can use that isolated role
   and a fixed protected search path with fully qualified names. Its narrow
   interface would lock/revalidate the genuine cohort, append the three cycles
   and dual records, enforce the expected predecessor and insert the selection
   atomically. Revoke public function execution and review the caller grants.
   A caller's JSON/GUC `owner` claim or `activated_by` string is not authority.
3. Database triggers on universe/targeted snapshot writes and selection writes
   can reject direct legacy writes once installed. The concrete dormant artifact
   uses a constant installed fence; epoch visibility under an old MVCC snapshot
   must not decide whether a legacy writer is allowed. Readiness epochs only
   gate the dedicated publisher. The design must withstand old app processes,
   direct INSERT and queued transactions, not just the new CLI.
4. Do not install the fence as a stand-alone toggle. A future reviewed cutover
   must coordinate the first validated cohort/CAS, readiness and writer ownership
   transition under the same lock protocol. That cutover is not implemented.
   A rejected legacy IR/on-demand write would otherwise fail its current task;
   legitimate targeted updates need a compatible reviewed function/queue route.
   Nightly/cache-miss writers need a reviewed disable/redirect or safe refusal
   behavior, including queue retry and operational health semantics.
5. Existing explicit mesa freeze/rollback/source-order authority must retain a
   separately reviewed operator route. Do not exempt arbitrary application
   writes based on an `explicit` receipt flag; that would also bypass ownership.
   This work neither creates such an operator role nor uses the consumed P1
   authority. Recovery/disablement must itself be ordered and auditable, without
   deleting immutable generations or silently restoring capped writers.

Real PostgreSQL tests must cover trigger/function grants and bypass attempts,
unprivileged direct writes, old-process concurrent INSERT/CAS, atomic enablement,
IR/targeted retry, explicit-order preservation, rollback after each write phase,
and deadlock/timeout recovery. Until the live role facts, local DDL/adapter and
those tests exist, this is a pending additive option, not implemented ownership.
No numeric SQL migration was added: Database.initialize automatically applies
numbered migrations, and silently adding an enforcement mechanism there would
change the served deployment on restart.

The next prepared artifact is now in
`deployment/full-universe/ownership.review.sql`, with a single-connection
rollback-only adapter in `app.listed_universe_pg`. Neither is installed or a
production committer. The principal, migration-startup and writer/IR/operator
compatibility boundaries are detailed in `FULL_LISTED_UNIVERSE_PG_REVIEW.md`.

The remaining release gates are consequently concrete: real PostgreSQL atomic
adapter/concurrency proof; persistent legacy-writer enforcement; source-verified
provider/host/SEC capacity; Fable GO on the exact head; a genuine PIT-free window;
and actual post-commit capture/cache validation. The old BOTH_FAIL study stays
closed. Buying still needs its separate verified scientific population and
default-deny guard. No new look or horizon is chosen by publication preparation.
