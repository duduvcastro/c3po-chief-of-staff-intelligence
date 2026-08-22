# Blueprint Day D v1.2

Status: **signed and authorized for Stage 0 only**  
Date: 2026-08-22  
Owners: Dudu, Codex and Fable  
Machine-readable companion: [`day_d/stage0_contract.json`](day_d/stage0_contract.json)

Signal and universe freeze:
[`day_d/replay_signal_spec_v1.json`](day_d/replay_signal_spec_v1.json)

## Mandate

Day D builds an intelligence that accumulates evidence every session and changes
behavior only at versioned, auditable boundaries. The first generation buys the
cheapest credible verdict on one precise question:

> Do S3-v1 and S5-v1, long-only, with intraday entries and Dudu's conditional
> T-30s/carry policy, have positive net economic edge?

The intraday ledger separately measures whether the signal has value before
overnight exposure. It is diagnostic; the consolidated economic ledger is the
primary estimand for kill and promotion.

This document authorizes specification and research work in Stage 0. It does
not authorize a production strategy change, capital promotion, raw-capture
rollout or provider purchase. A parameter becomes frozen only through its own
six-hands-reviewed Stage 0 contract.

## Construction governance

The project is built jointly in six hands:

- Dudu owns product intent, capital policy and final risk decisions.
- Codex owns implementation grounded in the real repository and production
  infrastructure, and reports verification evidence.
- Fable independently audits statistical validity, leakage, overfitting and
  promotion criteria.

Non-trivial methodology, data, inference, execution and risk decisions return
to this group before implementation. A routine change that preserves an
approved contract remains visible in its pull request.

## Operational clock

- Time zone: `America/New_York`, resolved through an exchange calendar.
- Regular session: 09:30:00 through 16:00:00 ET.
- New entries stop at 15:50:00 ET.
- Open-position risk monitoring runs from 09:30:00 through 16:00:00 ET.
- Early closes come from the exchange calendar; a hardcoded 16:00 close is
  invalid on those sessions.
- The T-30s window begins exactly 30 seconds before that session's official
  close.

## T-30s and conditional carry policy

During the final 30 seconds, the one-second watcher reevaluates the latest
fresh executable bid for every open position. A position is sold when its
estimated net exit P&L is strictly positive, including a position that was
negative when the window opened and turns positive later in the window.

All of the following are mandatory:

- Estimated net P&L includes the actual entry basis and the slippage and fee
  that the exit would incur.
- Weekly-conviction or any other legacy label grants no exemption.
- A simulated sale exists only when the first eligible fill occurs before the
  official close.
- A signal that cannot fill before the close is recorded as
  `late_unfilled_exit`; the position becomes carry.
- Negative positions remain under hard stop, Chandelier and approved defenses
  through the final second. If none fires, they carry overnight.
- Carry has no maximum number of sessions. A carried position exits only by a
  concrete risk/exit rule or by becoming net-positive in a future T-30s window.
- Carry consumes capital and one of the five portfolio slots. That opportunity
  cost is part of the policy being measured, not hidden by the analysis.

The approved implementation model is one-second polling of the latest fresh
tick, not an event-driven claim of processing every provider event. Event-driven
processing is a future, separately versioned upgrade.

## Premarket and next-session protection

Premarket is information only. It may prepare a risk assessment for a carried
position, but it may not create a simulated fill. At 09:30:00 the action is
revalidated against the first eligible fresh regular-session quote. A gap
through the stop fills at that first eligible regular-session price under the
frozen cost/fill model.

Whether the contracted EODHD feed provides usable premarket coverage is an
open data-quality question. FMP and Polygon are candidate supplements if it
does not.

## Accounting contract

The identity is immutable:

`R_consolidated = R_intraday + R_overnight`

For a same-session exit, all entry and exit economics belong to the intraday
ledger and the overnight component is zero. For a carried position, the
official close of the entry session is an internal transfer mark without a
fictitious fee: entry cost remains intraday and the real exit cost belongs to
the overnight component.

Daily consolidated results use NAV-style marking. A session with no new trade
is not zero when an existing carry changes value. It is zero only when there is
neither a transaction nor an open position with a mark change. The Stage 0
workbook freezes the exact equations, corporate-action treatment and
normalization by initial dollar risk.

The `flat-at-close` comparison is a separate policy-complete replay book. It
must reproduce the capital and slot availability created by its own exits; it
cannot be calculated by merely replacing the exit price on trades selected by
the carry book.

## Experimental book

Generation 1 contains only:

- `S3-v1`: opening-range breakout plus VWAP continuation.
- `S5-v1`: bar-based VWAP mean reversion without CVD.

Both setups receive equal experimental weight. Thompson Sampling is disabled.
At entry, risk is 0.15% of current virtual NAV; that resulting dollar budget is
then fixed for the trade's lifetime. Simultaneous exposure is capped at five
positions and duplicate economic exposure to the same symbol is blocked.
Weekly conviction does not alter entry, sizing or exit in this experimental
book.

The deterministic daily universe is 60 US common stocks plus QQQ, constructed
using only information available by D-1. The exact security filters, twenty-
session median dollar-volume calculation and deterministic tie/substitution
rules are frozen in
[`day_d/replay_signal_spec_v1.json`](day_d/replay_signal_spec_v1.json).

Changing a material setup rule creates a new setup version with a new evidence
history. S5-v2 may use qualified tick-derived CVD in the future; it does not
inherit the S5-v1 posterior or results.

## Evidence and checkpoints

- Unit: consolidated net R by exchange session, including daily carry marks.
- Checkpoints: C1 after 60 sessions and C2 after 120 sessions.
- Burn-in: 30 sessions for the single pre-registered variance update.
- No inferential decision outside a checkpoint.
- `UB >= theta` means only `retained`; it is not evidence of positive edge.
- Positive evidence requires a lower-bound rule and an economic threshold,
  selected and frozen before unburned results are viewed.
- C2 failure means "not validated within the pre-registered horizon and
  power," never proof that no edge exists in all possible strategies.
- Multiplicity across checkpoints, arms and the class verdict is calibrated
  jointly.
- Raw R is retained. Clipping, if used for a future allocator, never rewrites
  the scientific ledger.

Unlimited carry introduces serial dependence between daily marks. The final
pre-registration therefore may not rely on an unadjusted iid t-test. Stage 0
must specify a dependence-aware primary procedure or simulation-calibrated
critical values; weekly block bootstrap remains a required sensitivity.

At the final pre-registration hash, the observed annual US three-month Treasury
bill rate is converted to R/session as `(annual_rate_decimal / 252) / 0.0015`.
The binding floor is reconciled once as
`max(0.15R, operating_cost_R_per_session + benchmark_rate_R_per_session)`.
The source, rate, timestamp, converted component and final result are all part
of the hash.

## Data and validation gates

- EODHD WebSocket is unqualified until independently compared with Polygon.
- Polygon Stocks Advanced is the proposed one-month Stage 1 purchase for five
  years of point-in-time minute data plus independent trade/quote reference.
- Raw capture remains disabled until the Stage 1 disk guard and numeric T0
  acceptance criteria are in place.
- T0/T1/T4/T5 acceptance thresholds are written before their results are
  observed.
- Point-in-time universe reconstruction, completed-bar rules, purging and
  embargo are mandatory anti-lookahead controls.
- `T-30s + conditional carry` and `flat-at-close` are replayed as independent,
  path-dependent portfolios in Stage 1.

## Stage order

1. **Stage 0, paper:** NPV, `theta_meta` and `theta_kill`; Dudu's written
   12-month success definition; preliminary power feasibility; frozen S3/S5,
   universe, clock, fills, costs, ledgers and numeric data gates; draft
   pre-registration.
2. **Stage 1, phenomenon:** disk guard, five measured capture sessions,
   independent Polygon reference and historical veto experiments.
3. **Stage 2, skeleton:** production-quality spool, replay engine, synthetic
   truth tests, final joint calibration and hashed final pre-registration.
4. **Stage 3, collection:** approximately six months of policy-complete live
   shadow with checkpoints at 60 and 120 sessions.
5. **Stage 4, conditional:** capital promotion, ranker, additional setups,
   Thompson allocator and future data sources only if their gates approve.

## Signatures

- Dudu: owner decisions recorded.
- Fable: approved.
- Codex: approved for Stage 0 on 2026-08-22.

The signature does not authorize later stages. Each later stage requires its
own objective gate and explicit approval.
