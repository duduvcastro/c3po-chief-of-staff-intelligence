# R2D2 backtest harness

## Why this exists

Code review of the R2D2 methodology (V16-ASYMMETRIC-DEFENSE) found no
statistical validation anywhere in the codebase: every strategy-version
jump (V14 -> V15 -> V16) was a same-day reaction to a single bad session,
applied straight to the module-level constants in `r2d2.py`, with no
backtest against historical data and no train/test split. That is the
textbook shape of overfitting to recent noise, independent of whether any
individual rule change was reasonable on its own.

This harness lets you answer, before the next constant change ships:
*"is this actually better across many days and regimes, or did it just
fix yesterday?"*

## What was added

- `app/r2d2_strategy.py` -- the entry/exit/defense logic, ported
  **verbatim** from `r2d2.py` (`_technical_defense`, `_weekly_conviction`,
  `_entry_decision`, the exit cascade inside `_mark_and_exit`, `_ema`,
  `_target_position_percent`), with zero external dependencies. This is
  what makes the backtest trustworthy: it runs the same math, not a
  reimplementation that could silently diverge.
- `app/backtest.py` -- replays historical 5-minute bars through that
  logic and reports win rate, profit factor, max drawdown, total return,
  and a full trade log. Includes `split_walk_forward` for train/test
  splitting.
- `tests/test_backtest.py` -- unit tests (technical-defense severity
  classification, hard-stop firing, entry rejection reasons, a full
  synthetic backtest run, walk-forward splitting).
- `work/run_r2d2_backtest.py` -- example script wiring real EODHD
  intraday history into the harness.

## Known gap: `r2d2.py` still has its own copy of this logic

`r2d2_strategy.py` is a new module, not yet imported by `r2d2.py`. Until
`r2d2.py` is refactored to call into it instead of its own inline copies,
**there are two copies of the same logic and they can drift** the next
time someone (human or Codex) tweaks a threshold in one place and not the
other. Recommended follow-up, in order:

1. Run `pytest c3po/backend/tests/test_r2d2.py c3po/backend/tests/test_backtest.py`
   to confirm nothing is broken today.
2. Replace the bodies of `R2D2PaperService._technical_defense`,
   `_weekly_conviction`, `_ema`, `_entry_decision`, `_target_position_percent`,
   and the exit cascade in `_mark_and_exit` with thin calls into
   `r2d2_strategy.py`, keeping the method names/signatures the existing
   tests already reference.
3. Re-run both test files. If they still pass, `r2d2_strategy.py` is now
   the single source of truth and the backtest can never drift from
   production again.

## Known gap: entry backtesting needs historical fundamentals

R2D2's entry decision blends a technical score (computed here, fully
faithful) with a fundamental valuation score -- upside, confidence,
risk_score, buy_in_distance -- produced by the separate One Pager
pipeline. This harness accepts those as an optional input
(`fundamentals=` in `run_backtest`); without them it uses a neutral
placeholder, which means:

- **Exit/defense backtesting is fully faithful today** -- hard stop,
  failed-entry exit, technical-defense reduce/exit, profit harvesting
  don't depend on fundamentals in the live code either.
- **Entry backtesting is technical-only** until you can supply historical
  valuation snapshots per symbol/day. If those snapshots don't exist yet,
  the practical path is to start persisting them going forward (the
  `learning_state` table already tracks `sample_days`/`sample_trades`
  outcomes -- the fundamental inputs used for each entry could be stored
  the same way) so a fully faithful entry backtest becomes possible after
  a few months of data.

## Suggested next use of this harness

Bring the V14/V15/V16-style constant changes under the same evidence bar
the `_ensure_daily_learning` loop already enforces for the small entry
parameters (minimum sample size before changing anything, small bounded
steps, versioned rationale). Concretely: before changing
`FAILED_ENTRY_LOSS_PERCENT`, the hard stop, or any other headline
constant, run it through `split_walk_forward` here and require the change
to hold up on the held-out fold, not just the day that motivated it.
