# Dormant real-PostgreSQL integration cases

These cases are **prepared, not executed**. Local preparation runs only Python
syntax/type checks and synthetic tests of the descriptor/import guards. It does
not connect, SQL-parse, install DDL or demonstrate real PostgreSQL behavior.

`postgresql_contract_cases.py` deliberately matches neither normal pytest file
pattern. Even explicit selection skips before opening a connection if the review
descriptor option is absent. Nothing imports it from `app/`; Docker's normal
`COPY backend/app ./app` does not package a new production committer.

## Exact external preconditions

A future separately authorized run needs an externally prepared local disposable
PostgreSQL cluster. This suite creates no cluster, database, role, password,
membership, grant, ownership handoff or base migration schema.

1. A fresh database named `c3po_fu_review_<32 hex>` on an explicit Unix socket in
   a private `/tmp` directory, with its actual port and cluster system identifier
   verified externally. TCP/default hosts and ordinary database names are refused.
2. A unique externally recorded UUID and matching database comment
   `c3po-full-universe-disposable-review:<UUID>`. The authenticated schema admin
   must be able to read `pg_control_system()`; other actor connections must match
   the same verified server start time. Every connection checks database, real
   session/current identity, Unix transport and marker before fixture writes.
3. The original canonical base schema, prepared externally from the repository's
   existing migrations, with **zero rows** in `analysis_snapshots`, predictions
   and selection and no existing `c3po_full_universe` schema. Do not run a normal
   API/worker bootstrap against this fixture or clear an existing populated DB.
4. Proposed roles `c3po_full_universe_owner` (NOLOGIN) and distinct authenticated
   `c3po`, `c3po_full_universe_publisher`, `c3po_full_universe_operator`, without
   superuser/create-role/create-db/bypass-RLS privileges or forbidden memberships.
   These are **required test roles, not observed live roles**. Actual role flags
   and canonical table ownership are checked. A separate real schema-admin
   identity is required; no admin name is guessed.
5. Canonical tables already owned by the proposed isolated owner. The legacy
   role needs ordinary SELECT/INSERT/UPDATE/DELETE on snapshots in this test
   fixture, so tests exercise conditional triggers rather than merely missing
   DML grants. The actual schema admin needs the reviewed installation/fixture
   privileges. This is not a proposed blind privilege change to the live system.
6. A private descriptor copied from `plan.pending.json`, filled with those real
   facts and the exact reviewed dormant DDL SHA256. The supplied template is
   intentionally invalid. Passwords are separate `FU_PG_REVIEW_*` environment
   references; no DSN, normal `PG*`, `.pgpass` or `C3PO_DATABASE_URL` fallback is
   used. The descriptor is a regular private file, not a symlink.
   Ambient `PG*` variables must be absent before any driver import/connection;
   they are rejected rather than silently inherited. Publisher sessions must
   actually report READ COMMITTED; no default isolation is guessed or overridden.

Those facts do not currently exist in this task's evidence. Missing prerequisites
fail before setup instead of creating roles, making up ownership or reporting a
passing integration. The suite intentionally does not DROP/TRUNCATE or clean up
the database afterward: retain it for inspection, then use a newly provisioned
disposable database for another invocation.

## Explicit future invocation, not performed now

From `backend/`, an authorized operator with the external prerequisites could
select the otherwise dormant file explicitly:

```sh
python -m pytest pg_contract_review/postgresql_contract_cases.py \
  --full-universe-pg-plan /private/tmp/verified-disposable-review.json
```

This command is documentation of a future test, not an installation instruction
for the current host. The suite would install the exact hash-bound review DDL
**only inside that guarded disposable database**. Installation really fences
legacy writers there; it is not harmless metadata. No real-world epoch, capacity
receipt, scientific look or Fable GO is supplied by a test fixture.

## Prepared real cases and their boundaries

One ordered test runs these phases, so an earlier test cannot consume the
missing-epoch/MVCC preconditions and cause later phases to be silently skipped:

- Seed three synthetic canonical cycles and stage rows through real canonical
  serialization. No provider, consensus study or backtest is run.
- Open a real legacy repeatable-read snapshot before fence installation and
  epoch creation. Its later canonical INSERT must still be fenced.
- Verify absent and expired readiness deny the publisher while legacy INSERT,
  canonical snapshot UPDATE/DELETE and role assumption remain blocked.
- Verify distinct authenticated principals, schema/table grants, and inability
  of the app role to replace the owned append-only function. That last expected
  denial demonstrates the still-pending startup/migration compatibility gate;
  it is not proof of a working application rollout after a role handoff.
- Preserve ordinary application INSERT/UPDATE/DELETE in the unrelated PIT,
  source, stage and US One Pager namespaces. A synthetic PIT prediction with a
  canonical source exercises the actual snapshot-FK namespace distinction.
- Add explicitly synthetic readiness fixtures and exercise the public
  `force_rollback=True` rehearsal with no persisted cohort/generation.
- Insert the complete three-market cohort, then attempt the foreign-market
  direct-INSERT witness under the real publisher login, bypassing only Python's
  data check, not authentication. PostgreSQL itself must reject the wrong
  market/cycle binding while native counts remain intact. Invalid/null fields
  must also be rejected.
- Inject failures after registration, the first snapshot and a complete
  candidate; verify the real transaction leaves no candidate rows or successor.
- Use independent publisher sessions to test NOWAIT lock exclusion and reader
  visibility. A **test-only fixture transaction commits synthetic rows** in the
  disposable DB, then stale predecessor replay must fail. This does not enable
  `app.listed_universe_pg.commit_publication()`, which still always denies.

Future execution will be one pytest integration test containing those explicit
phases; phase descriptions are not additional test counts. Until it is actually
run, none of the cases proves SQL syntax, grants, triggers, concurrency or MVCC.
Local synthetic guard tests must never be relabelled PostgreSQL results. Even a
future passing disposable test would not attest live role facts, measured
capacity, a production cutover, Fable review or PIT release.
