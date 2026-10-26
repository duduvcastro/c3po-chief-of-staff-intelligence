# Dormant PostgreSQL ownership and rollback adapter

This increment is prepared for review, not deployment. No PostgreSQL connection,
container, role, credential, grant, DDL, ownership epoch, generation or schedule
was created or changed. Public production commit remains structurally closed.

## Transaction adapter

`app.listed_universe_pg` opens no connection and has no CLI. `rehearse` accepts
one fresh idle connection; nested transactions are refused. Its one outer
Psycopg transaction explicitly uses `force_rollback=True` and a rollback sentinel.
It never commits. `commit_publication()` always raises; no approval flag or
callback enables it.

READ COMMITTED is required by the adapter and SQL lock helper, so a long-lived
repeatable-read snapshot cannot reuse an old readiness epoch. Checking isolation
is a database transaction property, not an ownership GUC/flag.

The prepared write path acquires the dormant schema's consistent table-lock
helper, checks the genuine authenticated `session_user` and `current_user`, and
reads the protected epoch and server clock. All inherited Database reads bind to
that same connection. The three inherited persistence APIs that commit on their
own are explicitly refused by the read view.

Compilation reuses the canonical stage/read-set validators and isolated
composition. It registers the cohort, appends three official snapshots, appends
both canonical source records, re-reads their transaction-local storage values
and hashes, and inserts one selection chained on the exact predecessor. Numeric
parameters use the existing Decimal conversion. `supersedes_id` names each
market's actual latest published snapshot, which may be newer than the cycle the
selection carried. The activation clock is re-read from the server after the
record writes and checks; a prepared receipt's old clock is not reused.

Every failure unwinds the same outer transaction. Rehearsal also rolls back a
complete successful candidate. It neither runs nor reports post-commit served
capture/cache work. A production committer and that post-commit protocol remain
unimplemented.

Local tests use genuine canonical compilation and connection doubles that
record SQL and model rollback. They exercise call order, bound reads, refusal of
per-market commits, projection corruption, clock recession and phase failures.
**They do not parse or execute PL/pgSQL, authenticate live roles, or establish
PostgreSQL locking, trigger/grant behavior or concurrency.** No PostgreSQL parser
or server was available/used in this task. Real database validation remains a
release gate, not a property inferred from SQL text or doubles.

## Dormant SQL artifact

`deployment/full-universe/ownership.review.sql` is outside `db/`, has no numeric
prefix and is not registered anywhere. The unchanged real migration enumerator
was exercised with fake execution to confirm it never loads this file.

The SQL is an explicit future installation candidate, with these boundaries:

- It creates no roles or passwords. It first requires reviewed, existing roles
  and isolated table ownership. The names are a proposed role contract, not
  claims about live roles. The configured `c3po` application principal must not
  be a superuser, own the canonical tables or inherit the isolated roles.
- The NOLOGIN owner controls the private schema. Publisher/operator are distinct
  authenticated principals. `SET ROLE`, `activated_by`, JSON `explicit` or a GUC
  cannot substitute for that principal boundary.
- Trigger functions use `SECURITY INVOKER` so the canonical writer's identity is
  preserved. Narrow `SECURITY DEFINER` helpers only read whether fencing exists
  or acquire table locks; the publisher gets no UPDATE/DELETE/TRUNCATE just to
  lock a table. Their search paths and table names are fixed.
- The artifact is dormant because it is uninstalled and outside the loader.
  **Installing it would immediately fence legacy canonical writers**, not merely
  add harmless metadata. The installed fence is constant, independent of epoch
  visibility under MVCC. Otherwise an older transaction could miss a first epoch
  and incorrectly keep writing. Installation must therefore be an ordered
  cutover after all startup/IR/targeted/operator compatibility is ready; none is
  authorized or performed here.
- Installation inserts no readiness epoch. Missing or expired readiness stops
  the publisher while the installed fence remains. Appending a real epoch
  requires the same canonical lock protocol and genuine verified evidence; no
  enablement function or caller flag is provided. A SHA256 alone is not evidence.
- Canonical universe/targeted snapshot INSERTs, their prediction INSERTs and
  selection INSERTs are fenced. Canonical snapshot UPDATE/DELETE is also denied,
  including attempts to change its namespace. Existing prediction/selection
  append-only triggers remain unchanged.
- Ordinary application writes in `valuation_pit_rerun`, `valuation_pit_served`,
  `valuation_pit_source`, `full_universe_stage`, `one_pager_valuation` and other
  unrelated namespaces remain outside this fence. Prediction INSERT scope is
  determined from its actual snapshot FK, not the source name alone: PIT records
  can legitimately carry a canonical source without being served cycles.
- A cohort registration binds its real backend/transaction/authenticated user,
  three stage FKs, manifests, cycles and predecessor. Canonical INSERT checks
  preserve stage rows/reasons and source record values; selection checks the
  current head, selected source/version, records and existing freeze/order.
- New targeted publication and verified operator-order adapters are not supplied
  yet. They are denied explicitly, even for the dedicated operator. Merely
  granting that role INSERT is not an accepted freeze/switch/rollback order.
  Those compatibility routes must exist and be reviewed **before** installing
  the fence, not only before adding a readiness epoch.

The DDL was not installed or SQL-parsed. These are intended invariants subject
to real PostgreSQL/privilege tests, not a live ownership attestation.

Independent review found a concrete gap in the initial prediction fence: a B3
record could point to the NASDAQ cycle of the same cohort while preserving B3
stage values, and native per-market counts would ignore that extra record. The
revised DDL requires the exact market-to-cycle-to-stage FK binding, validates the
cycle/stage namespace and market, and rejects foreign-market records during
selection. Missing/invalid markets and null/missing bindings are refused. The
adapter also checks this binding before any cohort DML. A synthetic fixture
preserves the independent witness and exercises that adapter rejection with all
native records still present. This regression does not execute the SQL fence;
the equivalent direct-INSERT PostgreSQL test remains required.

## Startup/migration compatibility is a concrete pending gate

Observed source: `backend/app/database.py:211–224` opens the configured
`database_url` connection, re-executes every top-level numeric SQL migration and
commits on each initialization. API startup (`main.py:233`), the valuation worker
(`valuation_worker.py:486`) and IR worker (`ir_worker.py:35`) call it.
`db/048_valuation_official_tp.sql:69–83` creates/replaces the append-only function
and drops/creates its triggers on every such pass.

Giving those tables/functions an isolated owner while the application keeps
reapplying owner-only DDL can therefore break startup unless migration ownership
and execution are separated or another reviewed compatible mechanism exists.
This is a source-level integration consequence, **not an observed failure on the
current host**. Live superuser status, memberships, grants, object owners and
actual migration execution identities are unknown. No ownership transfer,
privilege workaround or frozen-file change is attempted here. An additive
solution remains possible; the 72-file freeze does not prove impossibility.

## Writer error/queue and operator compatibility

`legacy_write_disposition` returns a sanitized routing contract from actual
SQLSTATE fields. It never consumes raw logs, performs queue updates, reports
success, retries automatically or falls back to another producer. Lock/CAS
conflicts require a fresh head/window; ownership/readiness/corruption and missing
adapter errors require facts or integration review. No existing caller is wired
to this contract yet.

This distinction matters for IR: `ir_valuation.py:70–73` catches a refresh error
and calls `finish_ir_valuation_updates(succeeded=False)`. The current Database
implementation (`database.py:3155–3180`, `:3213`) increments attempts, requeues
until three failures, then sets `failed`. Fencing alone would consume retries
and could terminally fail legitimate queued updates. A reviewed deferral path
must preserve the update/event as pending without marking it incorporated or
inventing a targeted fallback. It is not implemented by returning this contract.

US One Pager's `one_pager_valuation` persistence is not a canonical selection
writer. US screen/matrix cold builds and B3 full/IR/targeted builds are. Future
routing must preserve that distinction. A fenced cache build may expose a stale
or unavailable current generation explicitly; it must never compute a substitute
served TP. Verified mesa freeze/rollback/source orders need their own genuine
guarded route. None of the consumed P1 authority is restored by a new role name.

Remaining gates: real roles/grants/owners and migration-startup design; real
PostgreSQL DDL/round-trip/concurrency/rollback tests; safe IR/targeted/cache and
verified operator integration; an ordered fence installation and readiness epoch; measured authenticated
provider/host/SEC capacity, exact-head Fable GO and a genuine PIT-free window;
and actual post-commit capture/cache validation. The scientific BOTH_FAIL stays
closed and new-name buying remains independently default-deny.
