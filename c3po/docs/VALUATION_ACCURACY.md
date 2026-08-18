# C3PO valuation accuracy harness

## Why this exists

R2D2's entry decision blends a technical score with a fundamental score
that ultimately traces back to the canonical C3PO valuation methodology
-- the target prices shown to users as Dark Side (screening matrix),
Last Jedi (the validated opportunity set) and Ben Kenobi Records (the
permanent audit trail of every valuation change). No part of the
codebase checked, before this file, whether those target prices actually
track what happens to the real price afterward. A target price that
*looks* rigorous (a full methodology, a confidence score, official
disclosures reconciled nightly) can still be systematically wrong in a
consistent direction, or -- just as importantly -- can be well-calibrated
in aggregate but its confidence score can carry no real information (a
90%-confidence call hitting no more often than a 50%-confidence one).
Neither failure mode is visible without checking calls against outcomes,
which is what this harness does.

## What was added

- `app/valuation_accuracy.py` -- pure computation, zero bundled market
  data. Turns `valuation_change_records` rows (every time a target price
  changed for a symbol, with the price at that moment -- this is exactly
  what Ben Kenobi Records already stores) into graded outcomes at
  configurable horizons (default 30/60/90 days): hit rate (did price
  actually reach the target), direction-correct rate (did it at least
  move the called way), mean error versus the predicted return, and
  calibration broken out by confidence bucket.
- `tests/test_valuation_accuracy.py` -- unit tests for the grading logic
  (horizon gating, hit/direction/error math for both bullish and bearish
  calls, calibration bucketing).
- `scripts/r2d2-export-readonly.sh` now also exports `valuation_calls.csv`
  (read-only, same `\copy` pattern as the R2D2 exports) so this can be
  run against real data without new database access.

## Known gap: needs a real price source, same as backtest.py

`valuation_accuracy.py` ships with no market data, on purpose -- see
`evaluate_calls`'s `price_lookup` parameter. Wire in EODHD (production's
own source) or another real historical-price feed the same way
`work/run_r2d2_backtest.py` does for the R2D2 backtest, so the grading is
against real subsequent prices, not synthetic ones.

## Minimum evidence bar -- same discipline as METHODOLOGY_GOVERNANCE.md

Before concluding anything from an accuracy report ("Dark Side is well
calibrated," "confidence scores are meaningless," "US calls are worse
than B3 calls"), check `coverage_summary()`:

- **At least 30 graded outcomes at a given horizon** before reporting a
  hit rate for that horizon at all. Fewer than that, say so explicitly
  instead of publishing a percentage that looks precise and isn't.
- **At least 3 distinct symbols per confidence bucket** before comparing
  buckets in `calibration_by_confidence` -- one lucky or unlucky call in
  a thin bucket swings the bucket's hit rate by double digits.
- Report the date range covered alongside any number -- a report that
  only covers one market regime (e.g. everything graded during a broad
  rally) will look better calibrated than the methodology actually is.

This mirrors `METHODOLOGY_GOVERNANCE.md`'s rule for R2D2's trading
constants: a metric without a stated sample size is not evidence, it's a
single number dressed up as one.

## What this does NOT do

- It does not distinguish a target price that was *revised* (a new call
  superseding an old one before the horizon arrived) from one that was
  simply never re-evaluated. A symbol with frequent revisions will have
  many short-horizon calls graded against each other's often-overlapping
  price windows; that's expected, not a bug, but read the `changed_at`
  spacing before treating every row as an independent bet.
- It grades US and B3 calls with the same logic but does not adjust for
  currency, liquidity, or the fact that B3 is no longer part of R2D2's
  live execution mandate -- filter by `market` before comparing the two.
