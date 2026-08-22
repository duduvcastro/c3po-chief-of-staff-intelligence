# Day D Official Replay Harness v1

**Status:** frozen on merge after six-hands review
**Scope:** research only; no production behavior and no capital authorization

The machine-readable contract is
[`replay_harness_contract_v1.json`](./replay_harness_contract_v1.json). This
document maps that contract to the implementation that Fable will audit.

## Fail-closed boundary

`DayDReplayHarness.run()` is available only for synthetic development runs.
An official manifest must call `run_fragility_matrix()`. The official entrypoint
refuses to emit a result unless all of the following are present and hash-bound:

- the signal and harness contracts;
- the dataset manifest and per-file checksums;
- a D-1 point-in-time universe for every session;
- the audited fee schedule and causal spread table;
- passed T1, T4 and T5 gates;
- a synthetic-truth report produced by the same Git commit;
- the preregistration hash and deterministic seed; and
- a corporate-action coverage manifest for every replay session.

A missing item raises `OfficialReplayBlocked` before market data is replayed.
The preregistration hash is checked against the supplied artifact bytes; a
well-formed but invented digest is not sufficient.

## Audit order

### 1. Anti-lookahead

- Every bar, print, quote, halt, universe observation and corporate action has
  both market time and availability time where applicable.
- A one-minute bar becomes usable only at or after its close.
- S3 and S5 decisions wait for the latest availability timestamp of every
  contributing bar, including QQQ.
- The signal bar cannot activate its own fill.
- The universe ignores corrections received after the official D-1 close.
- Cost cells must end strictly before replay session D.
- Every prior RVOL curve is bound to a symbol, historical session and
  availability timestamp; current-session, future or late curves are rejected.
- D-1 and T5 closes carry session, event time, availability time and source
  identity instead of entering the engine as untraceable scalar prices.

### 2. Fills

- Point latency is deterministic 500ms with integer jitter in `[-250, +250]`.
- The latency clock starts only at `available_at`, when the trigger is actually
  observable to the strategy; exchange `event_at` is retained for audit but
  never grants the replay an earlier decision.
- The mandatory matrix also runs fixed 0ms, 250ms, 1s and 2s latency.
- Marketable orders use a qualified non-crossed BBO when it is causally fresh;
  otherwise they use the frozen conservative trade fallback.
- Stops require two distinct prints at least 100ms apart, within 1s, with at
  least US$5,000 combined notional. A recovery print resets confirmation.
- Nothing fills during a halt. A resting stop crossed on reopening fills from
  the first reopening print, never from the obsolete pre-halt stop level.

### 3. Costs

- Half-spread cells are indexed by frozen D-1 liquidity quintile and an
  exchange-calendar time bucket.
- A spread cell also has an availability timestamp and cannot be selected if
  it was computed after the replay session opened.
- A sparse cell may fall back only to the same quintile's prior-session `ALL`
  cell. There is no cross-quintile fallback.
- Optimistic, point and pessimistic scenarios use p25, p50 and `2 * p50`.
- Broker, SEC Section 31 and FINRA TAF values come from a versioned fee
  schedule with source, effective time, capture time and content hash.
- An official report contains 30 policy-complete results: two books
  (`operational` and `flat_at_close`), five latency scenarios and three cost
  scenarios. An isolated official scenario cannot be emitted.

### 4. D-1 universe

- Exactly the frozen security classes and XNAS/XNYS listings are eligible.
- Ranking uses 20 complete sessions of point-in-time median dollar volume.
- Issuers are deduplicated deterministically before the top 60 is selected.
- Only permanent administrative unavailability known by 09:25 ET can trigger
  deterministic substitution. Missing bars, quotes, halts and provider outages
  never alter the frozen membership.

### 5. Synthetic truth

CI runs negative (-0.5R), zero (0R) and positive (+0.5R) worlds for both
S3-v1 and S5-v1 through the actual `DayDReplayHarness`: completed-bar signal,
activation, fill, sizing, policy-complete synthetic book close and the same
un-clipped R ledger used by replay. It also checks future-data mutation,
same-bar rejection, latency ordering, cost monotonicity, NAV-scale invariance
and preservation of a raw +7R tail. An official manifest accepts that report
only when its commit and contract hashes match the replay.

The same-commit artifact is generated explicitly, with no wall-clock default:

```bash
python -m app.day_d_replay.synthetic_gate \
  --git-commit "$GIT_COMMIT" \
  --measured-at "$MEASURED_AT_ISO8601" \
  --output artifacts/day_d/synthetic-truth.json
```

The writer uses an atomic replacement. A failed gate exits nonzero and can
never satisfy `validate_official_readiness()`.

## Ledger and carry

The trade risk budget is frozen at entry. A carried position is marked at the
entry-session official close without a fictitious fee. Actual exit costs belong
to the overnight component, and the engine asserts:

`R_consolidated = R_intraday + R_overnight`

Splits, dividends, symbol changes, cash/stock mergers and zero-recovery
delistings are modeled as point-in-time events. Fractional transformations
without cash-in-lieu terms invalidate the run rather than inventing a value.
Raw R, MFE and MAE are never clipped in storage.

## Entry audit

Every generated S3/S5 signal produces one `ReplayEntryAudit`. The record joins
the D-1 universe rank, causal feature timestamp, every setup gate, expiry,
structural and post-floor stops, risk budget, quantity, trial fill, final fill
and final acceptance or rejection reason. Preparation, sizing, participation,
cash and portfolio-cap rejections therefore remain reconstructable even when
no position exists in the trade ledger.

## Deliberate non-actions

This package is not imported by the live R2D2 worker, has no API route, starts
no process, reads no production database and places no order. This change does
not execute the five-year replay. T0/T1/T4/T5 acceptance values, the final
preregistration hash and the immutable dataset are still separate gates.
