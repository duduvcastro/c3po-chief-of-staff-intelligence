# M1 formal checkpoints — public source contract V1

**Status:** scheduler and transfer implementation prepared but dormant. No
credential, GitHub App, signing key, integration pin or enable switch is
installed by this change; the default path performs no production read and no
external write. Breaker mutation remains outside the contract.

## Authority and frozen inputs

This contract implements only item 5 of
`MESA_2026-09-04_POSICOES_PRE_REGISTRADAS`:

> schedule the formal readings of the 15th and 20th sessions as automatic
> executions; the interim reading was analysis-only and a kill-criterion
> reading must not depend on human memory.

The exact signed relay document is pinned by SHA-256:

`b846371a89f9d5b3ec4ccadd8ac4cc470be89a24444cf992604dad072541658f`

The statistical contract remains the already signed material:

- `V1_KILL_CRITERION.md`:
  `b2ea9f1ebf5de12fe9cdebae4ed84b7af4e3bc6379100b495f1d5819ff80c799`;
- `ENTRY_QUALITY_STUDY_V1.md`:
  `63cdb045a69dfe31246e82fa64e00dd1f9e0357897259a0d420ad81d0957a41e`;
- policy epoch: `policy-a-resume-2026-08-26`;
- bootstrap: session-level, seed `20260824`, 10,000 iterations;
- reference probability: 50%; formal one-sided confidence level: 98.75%.

No parameter is re-estimated or selected from the result.

## Formal clock

The clock is the number of distinct sessions represented in the frozen M1
measurement population, not calendar days, scheduler wakes, raw BUY dates or
H3 decile coverage.  A session with BUY rows but no admissible M1 measurement
does not advance that clock.

The enumerator returns all organic BUY-session dates since the policy-epoch
boundary in chronological order.  It excludes the current New York date until
18:00 America/New_York, so a partial session cannot enter a checkpoint.  The
formal reducer then chooses the smallest chronological source prefix whose M1
summary contains exactly 15 or 20 measured sessions.  A late scheduler still
reconstructs the exact checkpoint; it never substitutes the 16th, 17th or 21st
session reading.

The six-session canonical interim run established the initial clock:

`2026-08-26`, `2026-08-27`, `2026-08-28`, `2026-08-31`, `2026-09-01`,
`2026-09-02`.

If every following US trading session produces an admissible M1 measurement,
the earliest calendar estimates are 16 September for session 15 and 23
September for session 20. These are estimates only; the measured-session
clock, not either date, triggers a formal read.

## Reader boundary

`c3po_m1_session_snapshot.py` is byte-identical to the successfully exercised
read-only reader, SHA-256
`3fe89fd60e7b544571eb45dfc478abc5ffcc08d448bcff4aab5dbd143b4d83f3`.
Its invocation contract is:

- use the already-running API container; never create a second API instance;
- one session per process, sequentially;
- PostgreSQL role `pg_read_all_data`;
- `default_transaction_read_only=on`;
- statement timeout 120 seconds and lock timeout 5 seconds;
- named server cursors with `fetchmany(128)`;
- host-memory preflight, `nice -n 10` and a 384 MiB virtual-memory ceiling;
- transient snapshots destroyed after reduction.

The snapshot and reducer fail closed on missing price coverage, policy-epoch
drift, application-source drift, query-source drift, duplicate sessions,
duplicate entries, malformed hashes or a failed consistency gate.

The formal CLI also rejects more than 512 snapshot files, any snapshot above
4 MiB, more than 32 MiB of snapshots in aggregate, a baseline above 8 MiB or a
session enumeration above 64 KiB. These ceilings bound the retained Python
objects well below the runner's 384 MiB process ceiling; hitting one is an
explicit review condition, never permission to stream or omit part of the
formal prefix.

The gate and current-epoch replacement semantics reuse factual baseline run
`33022905030`, report self-hash
`23ede14e5d76cdd70bd1df58fcde62ad9445291eacae4872174b835ac4b94756`.
The formal reducer replaces every recomputed current-epoch session exactly as
the successful interim reducer did; it does not silently change the global
entry-consistency gate into a current-epoch-only gate.

The public GitHub artifact holding that factual baseline currently expires at
`2026-09-25T23:31:04Z`. Even in the best calendar case the 20th measured
session is only expected around 23 September, and the measured-session clock
can legitimately lag. A cron alone is therefore insufficient. The private
half must preserve and authenticate this exact baseline, or install another
audited canonical source, before the public artifact expires. Missing,
expired or self-hash-mismatched baseline evidence fails closed; it is never
reconstructed from an unpinned report.

## Formal bounds and labels

Both central and conservative estimators are published.  The signed M1 trigger
uses the central estimator.

At session 15:

- central UCB 98.75% `<= 0.50` → `M1_REFUTED_AT_15`;
- otherwise → `M1_CONTINUE_TO_20`.

At session 20:

- central UCB 98.75% `<= 0.50` → `M1_REFUTED_AT_20`;
- otherwise, central LCB 98.75% `> 0.50` →
  `M1_POSITIVE_BOUND_AT_20`;
- otherwise → `M1_INCONCLUSIVE_AT_20`.

The 20-session calculation requires an authenticated private marker for a
canonical 15-session artifact carrying `M1_CONTINUE_TO_20`; a label string is
never sufficient. The public reader recomputes the exact 15-session prefix
from the 20-session inputs, verifies the recomputation's own self-hash and
requires its stable checkpoint binding to equal that marker. The resulting 20
payload records the private canonical 15 artifact hash, not the fresh
recomputation's time-dependent hash. The private store independently compares
the 20 payload against the complete canonical 15 artifact retained in Actions.
A backfill, snapshot drift or source change in the first 15 sessions therefore
fails closed instead of letting a stale marker arm session 20. The whole
enumerator hash is the sole excluded binding field because that file
legitimately grows; its selected prefix remains bound by dates and all
per-session hashes. A refutation at 15 is terminal for this reader.

The private half must authenticate and deduplicate the submitted 15-session
artifact against its canonical record. The public reader independently proves
integrity and semantic equivalence, but does not claim that an arbitrary file
came from the private evidence repository.

`M1_POSITIVE_BOUND_AT_20` is deliberately not
`V1_NOT_REFUTED_AT_20`: that V1 terminal label also requires the signed M2
condition.  This source contract performs no breaker DML and no policy change.

## Publication boundary

The formal payload contains only:

- checkpoint and population counts;
- barrier-category counts;
- central and conservative UCB/LCB 98.75%;
- reduced per-session counts and hashes;
- frozen-contract hashes and governance flags.

Entry identifiers, raw measurements, symbols, positions and trade rows are
prohibited structurally.  Every payload carries a canonical SHA-256 self-hash.

## Remote runner and activation boundary

`.github/workflows/m1-formal-checkpoint.yml` wakes daily at 23:37 UTC, after
18:00 America/New_York in both daylight and standard time. A supervised manual
wake requires the exact phrase `RUN M1 FORMAL CHECKPOINT READ` from `main`.
Both paths run in the protected `production` environment. GitHub cron has no
strict start-time SLA; a late run still reconstructs the exact measured-session
prefix rather than shifting the checkpoint. Source sessions are read in
chronological order and the reader invokes the same `select_exact_prefix`
semantics after every snapshot; it stops as soon as measured session 15 or 20
is reached. The complete enumeration remains bound for methodology/hash
purposes, but no later snapshot is read after the checkpoint boundary.

The workflow is inert unless all of the following are installed in a separate,
audited integration step:

- variable `C3PO_M1_FORMAL_AUTOMATION_ENABLED=true`;
- variables `C3PO_M1_AUTHORIZED_PUBLIC_HEAD_SHA` and
  `C3PO_M1_AUTHORIZED_FORMAL_SOURCE_SHA256`;
- existing production transport secrets `C3PO_AWS_HOST`, `C3PO_AWS_USER`,
  `C3PO_AWS_SSH_KEY` and `C3PO_AWS_KNOWN_HOSTS`;
- repository-scoped GitHub App secrets `C3PO_M1_TRANSFER_APP_ID` and
  `C3PO_M1_TRANSFER_APP_PRIVATE_KEY`;
- dedicated Ed25519 secret `C3PO_M1_FORMAL_SIGNING_KEY`;
- remote dead-man URL secret `C3PO_HEALTHCHECK_M1_FORMAL_URL`.

There is no PAT. The GitHub App installation token is limited to the private
evidence repository and requests only Actions/write and Contents/write. The
signing key is a different key. Missing variables, secrets, private workflow,
private pin, signer allowlist or pre-seeded state fail closed before any
production read or evidence upload.
The scheduled workflow's own `github.workflow_sha`, not only the checked-out
tree, must equal the authorized public head. Updating the workflow without an
explicitly updated audited pin therefore fails before the remote read.

When enabled, the runner pings the dead-man `/start` endpoint before any
production read. Its last step, after release/artifact cleanup and transient
destruction, sends success or `/fail` from the final job status. A disabled
workflow is a true no-op: it neither requires nor pings this URL. Thus a missed
cron or failed cleanup is remotely observable without someone inspecting the
Actions page. The enabled marker is emitted before the other protected
configuration checks, so their failures reach `/fail`; a missing or malformed
dead-man URL still makes the job red but cannot notify the endpoint that is
itself absent.

The ordinary CLI remains preparation-only and emits
`schedule_implemented=false`, `private_retention_implemented=false` and
`transient_destruction_implemented=false`. Only the audited workflow invokes
`--orchestrated`, which binds all three flags as `true` into the checkpoint and
its self-hash. This keeps ad-hoc local use from claiming remote controls it did
not execute.

## Minimal private state machine

The private branch `m1-formal-state` is rooted by an orphan commit and every
state transition is a linear commit with at most one parent. Every referenced
tree contains exactly one canonical `state.json`; no checkpoint payload enters
Git. It must be pre-seeded as `PENDING_15` before activation. Its states are:

- `PENDING_15`: exactly empty hashes/expiry; permits the first checkpoint 15;
- `CONTINUE_TO_20`: carries only the canonical 15 artifact hash, stable binding
  and expiry; permits checkpoint 20;
- `TERMINAL_15`: suppresses every later checkpoint-15 re-emission;
- `COMPLETE_20`: suppresses every later formal read;
- `EXPIRED`: a durable tombstone that blocks recomputation and demands review.

An absent branch, extra tree entry, merge commit, malformed state, expired live
marker or tombstone is never treated as `PENDING_15`. The runner does not infer
state from calendar time and never reconstructs a deleted checkpoint.

## Expungeable transfer and retention

No public artifact or private release exists while the measured-session clock
is not ready. For an exact ready checkpoint, the transport sequence is:

1. upload only canonical reduced `checkpoint.json` as a one-day public Actions
   handoff and capture its immutable artifact id/digest;
2. create an empty private draft release through the repository-scoped App and
   capture its release id; its tag is exactly
   `m1-formal-transfer-<source_run_id>-<source_run_attempt>-<public_artifact_id>`;
3. build and sign an envelope binding the release id, public run id/attempt,
   public artifact id, audited source head/hash, checkpoint, stable checkpoint
   binding and payload hashes;
4. attach exactly
   `m1-formal-checkpoint-<15|20>-<artifact_sha256>.zip`, containing only
   `checkpoint.json`, `envelope.json` and `envelope.sig`;
5. dispatch `m1-formal-private-store.yml` and wait for its authenticated run;
6. require the private 30-day Actions artifact and the expected state-machine
   transition before acknowledging success;
7. delete the draft release/tag, delete the public handoff artifact on every
   outcome, and shred baseline, snapshots, recomputation, payload and keys from
   the ephemeral runner.

The dispatch carries the exact confirmation
`STORE FORMAL M1 CHECKPOINT V1` plus `release_id`, `source_run_id`,
`source_run_attempt` and `public_artifact_id`; the signed envelope retains the
corresponding `source_*` field names and `checkpoint_binding_sha256`. Preflight
captures the private `main` SHA, reads its pins at that exact revision, and
accepts the store run only when its `head_sha` is identical. A private workflow
update between preflight and dispatch therefore fails closed and is retried
only by a later scheduled run.

Unlike a deleted Git branch, Actions artifacts and draft release assets have
explicit deletion APIs and observable expiry. The private retention watcher
reconciles its 30-day artifact and writes `EXPIRED` rather than deleting state.
The reduced checkpoint is the only transferred data; raw rows, entry ids,
symbols, positions and credentials never enter either channel.

## Post-audit integration order

1. merge and deploy the audited public source/orchestration and private store;
2. install the GitHub App on only the required repositories with the documented
   permissions;
3. install the dedicated signing key/public allowlist and pin their audited
   hashes plus the exact public head/formal-source hash privately;
4. pre-seed the orphan `m1-formal-state` branch as exact `PENDING_15`;
5. configure the protected public variables/secrets, including the dedicated
   remote dead-man check, while leaving the enable switch off;
6. run contract/preflight verification, then enable the switch under owner
   supervision;
7. observe one not-ready path proving zero artifact/release, and leave policy
   admission human.

The factual baseline deadline of 25 September is unchanged. This automation
does not copy or extend its raw evidence; the private watcher must alert and a
new audited source still needs separate authority if checkpoint 20 has not
completed in time.
