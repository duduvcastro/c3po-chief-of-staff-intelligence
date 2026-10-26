# Full universe: capacity evidence and publication preparation

This increment imports local facts for review. It does not measure a live host,
contact a provider/SEC, install a schedule, publish a generation or grant buying.
Its CLI always returns `publication.production_release_allowed=false`.

## What is measured by the opt-in runtime

New checkpoints retain the actual run UUID, catalogue/source-code/adapter pins,
UTC start/end clocks, measured elapsed time by collection/context/valuation phase,
completed/interrupted invocations and input/row artifact reuse counts. Stage writes
have a separate measured interval and considered/inserted record counts. These are
elapsed operational timings, not CPU time or a live capacity guarantee.

The quota ledger separates:

- `reserved_billable_units`: weighted units reserved durably before a request;
  these are conservative reservations, not an invoice or a request count.
- `reservations`: reservation operations, including a possible crash before GET.
- `http.attempts_started`: recorded immediately before GET; it is not proof that
  a remote server received the request.
- Confirmed responses, status-code counts, transport failures, response byte
  counts and elapsed HTTP time. HTTP 200 does not establish input validity.
- `uncertain_inflight`: an attempt whose outcome was not recorded after a crash.
  Its units stay reserved and incomplete telemetry cannot attest capacity.

Input retries are counted separately from canonical provider fallbacks. Runtime
cache counters cover verified local artifacts, not unobserved provider caching.
Interrupted timings and old checkpoints without telemetry remain unknown. The
importer never replaces missing measurements with zero. A directory retaining
artifacts/quotas but missing its checkpoint cannot silently start a new run.

This producer does not perform a SEC sweep and its normalizer does not establish
complete issuer-to-CIK coverage. `known_ciks_in_inputs` is only a lower bound;
`distinct_sec_ciks` remains unknown until separate genuine mapping/sweep evidence
is supplied. No SEC pace, contact, backfill budget or existing worker parameter
is changed here.

## Read-only import

`inspect_run(catalogue, checkpoint_directory)` acquires a nonblocking shared lock
without creating files. It refuses a currently writing producer, escaped/symlinked
artifact paths, different catalogues, foreign identities, damaged digests,
unreconciled counts, future/noncausal clocks and contradictory telemetry.

The complete inventory must equal valued + not evaluable + remaining names.
Not-evaluable names retain their public reasons. All referenced input, context
and row artifacts are hash-verified. Runtime and stage intervals, HTTP counters,
weighted allocations, phase measurements and dual canonical records reconcile.
The receipt includes every artifact digest and its own integrity digest. These
digests check local bytes; they do not authenticate an external fact's provenance.

The CLI accepts a local JSON map from market to relative `catalogue` and
`checkpoint` paths:

```sh
python -m app.listed_universe_capacity --runs runs.json --policy review-policy.json --bundle evidence-bundle.json
```

Omitting policy/evidence is supported and reports concrete missing gates. The CLI
has no database, network, approval, deployment or scheduling option.

## External factual evidence

A `FULL-UNIVERSE-CAPACITY-BUNDLE-v1` maps each fact kind to a relative JSON path
and SHA256. Each `FULL-UNIVERSE-CAPACITY-FACT-v1` names its kind, validity interval,
typed aggregate values and exact bindings. Bindings include all three catalogue
manifests, deterministic run identities, unique run UUIDs, full run-evidence
digests, application-code pins and reviewed policy digest. Evidence from another
attempt, altered telemetry, a new policy or a changed head cannot be replayed.

Accepted kinds are:

| Kind | Required factual scope |
| --- | --- |
| `provider_budgets` | Contracted billing units and request rate, measured/committed other-worker usage, reserve and disjoint allocations for all three markets. Compare configured run allocations and reserved units with the account budget. The measured interval covers the cohort including stage. Prospective rate enforcement needs explicit review. |
| `host` | Actual memory/RSS peak and coverage, minimum free memory/disk, CPU peak and inclusion of concurrent workers. The measurement interval covers the full cohort including stage. |
| `sec` | Complete issuer/CIK mapping bound by digest, full submissions sweep time, configured/shared request rates, upstream-call coverage and outstanding backfill. A remaining backfill needs an explicitly reviewed budget/forecast, with pending names visible as not evaluable and denied buying. A forecast is not a completed measurement. |
| `operating_window` | Genuine recent counts of PIT running/blocking work and a confirmed deployment window. A report's scientific result is not this operational evidence. |
| `fable_review` | GO for `full_universe_production` on the exact proposed head, with its source comment in #429. |

Raw logs, credentials and unknown payload fields are rejected. Typed fact values
are reported as claims until an independently injected verifier authenticates
their source and returns the exact kind/artifact/bundle/bindings/time contract.
The CLI supplies no such verifier. A stored flag, JSON GO, matching digest, boolean
callback result or synthetic fixture is insufficient. The trusted verifier itself
still needs review and real source evidence; no real verifier is installed here.

Policy thresholds are explicit review inputs; no quota, memory headroom, nightly
duration, freshness horizon or SEC budget is guessed. Structural validation of a
synthetic complete contract only exercises the validator. It never constitutes a
real capacity receipt or permission to publish.

## Future publication and schedule seam

The emitted plan is preparation only. A stage is not an official producer cycle:
`select_generation` refuses its namespace. Conversely,
`Database.save_analysis_snapshot('valuation_universe', ...)` commits and invokes
`record_snapshot`/automatic activation per market. Calling it three times would
allow intermediate generations; it is not an atomic publication mechanism.

Release therefore still needs a reviewed additive storage/publisher transaction:

1. Re-read the genuine current generation, selected source/version, freeze and
   explicit-order guards. Pin the expected predecessor; refuse a changed head,
   hold or active freeze. Do not thaw or reuse the consumed P1 authority.
2. Revalidate the three real stage snapshot FKs and canonical records from the
   Database, all manifests/counts/unavailable reasons and causal freshness. A
   checkpoint's `stage_snapshot_id` alone is not database verification.
3. Persist all three official cycles plus their immutable records without the
   per-market automatic hook, and one same-source generation CAS in the same
   transaction. Preserve session/source/version validation, targeted admissions,
   explicit-order/freeze guards and subsequent cache/served-change capture.
4. Review writer ownership. The current nightly, IR and on-demand paths continue
   to publish legacy cycles. A later capped cycle could replace a larger one;
   adding a new phase alone would not prevent that downgrade or writer races.
5. Only after this transaction and ownership policy exist, review an explicit
   opt-in schedule against measured capacity and a genuine PIT-free window. No
   default phase, cron, timer or production environment value changes here.

This is not permission to call the explicit source-switch command: its accepted
before/after receipt is bound to another composition. The future publisher must
preserve the already-selected source and all automatic-selection guards.

Expanded visibility does not enable new-name buying. The restrictive Decisor
still denies permission without separately verified scientific artifacts and a
valid bound population. The closed BOTH_FAIL study is not a PASS and is not
reopened by this operational preparation.

For PR 27 October and deploy 28 October, the remaining concrete gates are genuine
provider/host/SEC measurements, source-authenticated capacity evidence, Fable's
exact-head review, the atomic publisher and legacy-writer ownership integration,
and a confirmed window outside active PIT chunks. No live evidence is invented to
fill those gates.
