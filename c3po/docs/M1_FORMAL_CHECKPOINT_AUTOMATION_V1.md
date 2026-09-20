# M1 formal checkpoints — public source contract V1

**Status:** preparation-only; no scheduler, credential, private retention or
breaker mutation is installed by this contract.

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

The 20-session calculation requires the complete, self-hashed 15-session
artifact carrying `M1_CONTINUE_TO_20`; a label string is never sufficient. The
reader recomputes the exact 15-session prefix from the 20-session inputs and
requires equality of label, population, bounds, gate, source-evidence hashes
and frozen-contract hashes. A backfill, snapshot drift or source change in the
first 15 sessions therefore fails closed instead of letting a stale marker arm
session 20. The whole enumerator hash is the sole excluded field because that
file legitimately grows; its selected prefix remains bound by dates and all
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

## Deliberately deferred private half

A separate audited change in the private evidence repository must provide:

- the remote schedule and deduplication markers;
- production secrets in a protected environment;
- private 30-day artifact retention and expiry wake-up;
- idempotent publication of the resulting marker.

Until that separate change is audited, merged and configured,
`schedule_implemented=false` and `private_retention_implemented=false` remain
literal in every payload produced here.  Destruction of transient snapshots is
also an orchestration responsibility; the public contract guarantees that no
raw row or identifier is **published**, not that a future runner already
destroyed its inputs.
