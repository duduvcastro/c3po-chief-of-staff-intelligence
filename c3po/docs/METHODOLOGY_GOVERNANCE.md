# R2D2 methodology change governance

## The rule

**No change to a constant in `app/r2d2_strategy.py` -- entry thresholds,
exit-cascade percentages, position-sizing coefficients, `METHODOLOGY_VERSION`
-- ships without a walk-forward backtest result attached to the pull
request.** No exceptions for "obviously correct" fixes reacting to a bad
session; those are exactly the changes this rule exists to slow down.

This bar applies to *strategy* constants -- what R2D2 decides to buy/sell
and when. It does not apply to *capacity/throughput* constants in
`app/r2d2.py` (shortlist size, technical-reviews-per-cycle) that don't
change entry/exit logic at all, only how many already-defined candidates
get evaluated per cycle. Those still get logged below with their evidence,
just not gated on a walk-forward result.

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

**2026-08-18 -- profit-lock pullback tolerance (`profit_pullback_percent`),
wider vs. current.** Raised by observing the exits are asymmetric: a
position can drift to -0.90% before the hard stop fires, but once armed
in profit it only tolerates a ~0.20pp give-back from its high-water mark
before locking out. `profit_lock_floor_percent`/`profit_pullback_percent`
were made configurable (`r2d2_strategy.exit_decision`, `backtest.run_backtest`,
both default to the unchanged live values) so this could actually be
tested. Swept pullback in [0.20%, 0.35%, 0.50%, 0.65%, 0.90%] on the same
technical-only setup as the hard-stop investigation above (neutral
fundamentals, real 60-day 5-minute data, 20 symbols, 3-fold walk-forward).
**Result: full-sample and every out-of-sample fold were bit-for-bit
identical across all five values.** Root cause, confirmed by counting exit
reasons on a smaller 3-symbol run: the "Armed profit locked" /
"Weekly-conviction profit locked" branches -- the ones this parameter
actually governs -- fired **zero** times. The dominant profit exit,
"Tactical profit harvested," triggers immediately at the 0.65% trigger
threshold and short-circuits the `exit_decision` cascade before the
peak-then-pullback branch is ever reached; it never fires from a real
peak/give-back sequence in this dataset. **Not acted on -- this is an
inconclusive test, not a negative result.** The mechanism in question is
essentially untested here, not proven safe or unsafe: this technical-only
20-symbol/60-day sample apparently never produces the "ran up well past
the trigger, then gave back ground before the lock lands" pattern the
parameter is meant to guard. A real test needs either historical
fundamentals-driven entries that hold positions longer/further before
harvesting, or -- more reliably -- real R2D2 trade history once enough
"Armed profit locked"/"Weekly-conviction profit locked" exits accumulate
organically (`backtest_data.py`, once the sample clears the minimum
above). The underlying asymmetry concern (harder on the upside than the
downside) is not addressed by this finding either way and should stay
open until a test actually exercises the branch.

## Capacity/throughput changes

**2026-08-18 -- technical-review capacity raised 16->24 (standard) and
24->32 (cash-deployment mode).** Real trade data for 2026-08-18 (`gh`
export via Codex, `operations_today.csv`/`cycles_metadata_today.csv`)
showed: (1) the deep shortlist (`US_STOCK_SHORTLIST_PER_MARKET` +
`US_ETF_SHORTLIST_PER_MARKET` = 350) was saturated at its cap on both
NASDAQ and NYSE for every sampled cycle from 12:41 to 16:49, while
`tradeable_count` kept growing (553->869 NASDAQ, 974->1504 NYSE) --
more eligible candidates existed than the shortlist could even hold;
(2) EODHD usage for the day was ~6,505 estimated credits against the
confirmed 100K/day budget -- budget was not close to a constraint, which
is what blocked this same change when proposed a few days earlier under
a mistaken 500K/day assumption; (3) the portfolio still net-closed 14
more positions than it opened that afternoon (51 buys vs. 65 sells) and
ended the day at only 3 open positions / ~84% cash, well past the
`r2d2_max_cash_percent` trigger that should have put every cycle in the
higher (24, now 32) deployment-mode review limit -- i.e. even the
"aggressive" cap wasn't enough that day.
Only the review cap changed here, not `US_STOCK_SHORTLIST_PER_MARKET`
(still 300) -- the shortlist being saturated doesn't by itself mean
raising it helps, since only the review cap controls how many
shortlisted names get evaluated per cycle regardless of shortlist size.
Revisit the shortlist cap separately if raising the review cap alone
doesn't fix replenishment. One day of data; watch
`r2d2_cycles.metadata` (scan_funnel/eodhd_usage, live since PR #9) over
the next several sessions to confirm this actually helps instead of just
raising cost.
