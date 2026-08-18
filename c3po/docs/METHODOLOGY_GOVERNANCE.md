# R2D2 methodology change governance

## The rule

**No change to a constant in `app/r2d2_strategy.py` -- entry thresholds,
exit-cascade percentages, position-sizing coefficients, `METHODOLOGY_VERSION`
-- ships without a walk-forward backtest result attached to the pull
request.** No exceptions for "obviously correct" fixes reacting to a bad
session; those are exactly the changes this rule exists to slow down.

## Why this exists

The jump from V14 to V15 to V16 of the R2D2 methodology was, in every
case, a same-day reaction to a single bad trading session, applied
straight to the module-level constants with no backtest against
historical data and no train/test split. That is the textbook shape of
overfitting to recent noise: a rule change that looks obviously correct
right after a loss can just as easily be fitting one bad afternoon,
indistinguishable from a real edge until it's checked against more than
that one afternoon. See `c3po/docs/BACKTEST.md` for the harness this
produced (`app/backtest.py`, `app/r2d2_strategy.py`) precisely so that
check is possible before a change ships, not after.

## Minimum evidence bar before proposing a constant change

1. **Minimum sample.** At least 15 distinct trading days and 30 closed
   trades in the data the change is evaluated against. Fewer than that,
   the honest answer is "not enough evidence yet" -- not a smaller
   change, not a compromise threshold, just wait for more data. Check
   this with `backtest_data.coverage_summary()` before doing anything
   else.
2. **Walk-forward, not full-sample.** Run `backtest.split_walk_forward`
   and report the **held-out test fold's** metrics, not the full-sample
   number. A change that only looks good with every day pooled together
   is exactly the overfitting risk in the paragraph above.
3. **State the counterfactual.** Report the OLD constant's walk-forward
   result on the *same* data next to the NEW one. "This is better" only
   means something next to what it's replacing, measured the same way.
4. **One change at a time.** If a PR changes more than one constant,
   the walk-forward result can't tell you which one did anything -- split
   it into separate PRs, or justify why they're coupled.

## What to attach to the pull request

- The train/test summary for both the old and new value (win rate,
  profit factor, max drawdown, total return -- `BacktestReport.summary()`
  already returns all four).
- The sample size and date range that produced it
  (`coverage_summary()` again).
- A one-paragraph rationale: what evidence motivated looking at this
  constant in the first place (a bad session is a fine reason to *look*,
  it's just not a fine reason to *ship* on its own).
- A version bump: append a row to the changelog below and bump
  `METHODOLOGY_VERSION` in `r2d2_strategy.py` in the same PR.

## Changelog

| Version | Date | Change | Evidence | Rationale |
|---|---|---|---|---|
| V14 | (undocumented -- predates this file) | -- | none on record | -- |
| V15 | (undocumented -- predates this file) | -- | none on record | -- |
| V16-ASYMMETRIC-DEFENSE | (undocumented -- predates this file) | -- | none on record | -- |

Past versions are listed as a gap, not backfilled with invented
rationale -- if the original reasoning is recoverable (commit messages,
chat logs, whoever made the call), add it here; otherwise leave it
marked undocumented rather than fabricate a walk-forward result that was
never run.

## Investigated, not changed

Questions someone will ask again -- check here before re-running the
analysis from scratch. These are preliminary findings below the evidence
bar above, logged so they inform the next real attempt instead of being
forgotten.

**2026-08-18 -- hard stop (`max_position_loss_percent`), tighter vs. current.**
A tighter stop (-0.50%, vs. the live -0.90% -- note the live value already
differs from the -0.65% code default, itself undocumented) was proposed.
Checked with a technical-only backtest (neutral placeholder fundamentals,
real 60-day 5-minute Yahoo Finance data for symbols R2D2 traded/considered
on 2026-08-17, `split_walk_forward` 3 folds): -0.50% did not beat -0.90%
on 2 of 3 held-out test folds, and lost on full-sample total return too.
A follow-up sweep (0.40% to 1.65%) found average out-of-sample return
improving *monotonically as the stop widens* across that whole range --
the opposite direction from what was proposed, and probably reflecting a
tight stop getting chopped by ordinary noise more than a real edge.
**Not acted on**: the sweep never found a plateau (untested past 1.65%),
used 20 symbols over one 60-day window with no real fundamentals, and a
wider stop trades a better average outcome for larger single-trade tail
risk that this backtest doesn't price in. Conclusion for now: neither
direction has real evidence behind it -- wait for real R2D2 trade history
(`backtest_data.py` once the sample clears METHODOLOGY_GOVERNANCE's
minimum) before touching this constant either way.
