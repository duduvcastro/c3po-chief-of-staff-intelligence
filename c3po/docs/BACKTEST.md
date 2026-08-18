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

## Resolved: `r2d2.py` no longer has its own copy of this logic

As of the migration merged 2026-08-17, `R2D2PaperService._technical_defense`,
`_weekly_conviction`, `_ema`, `_entry_decision`, `_target_position_percent`,
and the exit cascade inside `_mark_and_exit` all delegate to
`r2d2_strategy.py`. There is one copy of the decision logic; `r2d2.py` still
locally recomputes the stop-price/telemetry bookkeeping that
`exit_decision` doesn't return (needed to persist `strategy_snapshot` for
the live cache), using the identical formula -- see the comment above that
block in `_mark_and_exit`. `pytest c3po/backend/tests/test_r2d2.py
c3po/backend/tests/test_backtest.py` (196 cases) covers both.

## Resolved: entry backtesting now has real historical fundamentals to draw on

The `r2d2_decisions` table (see `db/016_r2d2_paper_trading.sql`) already
stores `fundamental_score`, `technical_score`, `risk_score`,
`composite_score`, `reasons` and the full `inputs` JSONB (including
`technical_indicators`) for every entry decision, BUY or REJECT -- this
was already true before this doc was corrected, the earlier claim that
"those snapshots don't exist yet" was checked against the code, not the
database. The `r2d2_experiments` row for the live 90-day experiment shows
`start_date = 2026-08-17`, so that's when real per-symbol fundamental
history starts accumulating from a cold start.

`app/backtest_data.py` (added alongside this note) converts a
`decisions_buy.csv`-style export (or any iterable of decision rows) into
the `fundamentals` callable `run_backtest` accepts, so once enough real
trading days exist the entry side stops being technical-only. See that
module's docstring for the minimum-sample guidance before trusting the
result -- a handful of trades on day one is not a backtest input, it's an
anecdote.

## Methodology-change governance

Read `METHODOLOGY_GOVERNANCE.md` before changing any constant in
`r2d2_strategy.py`. Short version: no `METHODOLOGY_VERSION` bump ships
without a `split_walk_forward` result attached, on a minimum sample, with
the out-of-sample fold reported alongside the day that motivated the
change -- this is the rule the V14/V15/V16 jumps skipped, and skipping it
again defeats the entire point of this harness.
