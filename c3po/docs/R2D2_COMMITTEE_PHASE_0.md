# Day D Stage 0 workbook

Status: **active design work; joint freeze pending; no production behavior**

Workbook version: `DAY-D-STAGE0-v0.2`

Governing blueprint: [`DAY_D_BLUEPRINT_V1_2.md`](DAY_D_BLUEPRINT_V1_2.md)

Machine contract: [`day_d/stage0_contract.json`](day_d/stage0_contract.json)

Founding date: 2026-08-22 (`Day D`)

## Scope boundary

Stage 0 converts the signed blueprint into a complete, testable and
pre-registerable research contract. It may produce documents, deterministic
research utilities, validation tests and simulations over burned data.

It may not:

- alter live entry, exit, sizing, ranking or risk behavior;
- enable raw capture or a new worker feature flag;
- purchase a provider subscription;
- label a setup `replay_eligible`;
- promote capital; or
- claim that the final pre-registration has been frozen.

The existing five-setup committee draft is superseded for Generation 1.
Generation 1 contains only `S3-v1` and `S5-v1`. S5-v1 is bar-based and does not
use CVD. The other setup ideas remain future hypotheses, not silent members of
the current experiment.

## Six-hands governance

- Dudu supplies the economic objective and owns capital/risk policy.
- Codex owns repository-grounded design, implementation and verification.
- Fable audits statistical validity, anti-lookahead and promotion logic.

Every item marked **joint freeze** below requires this review before its status
can change to `frozen`. A pull request is the review surface; merging a Stage 0
document does not itself activate production behavior.

## Owner inputs

The owner inputs were recorded on 2026-08-22. Their canonical machine-readable
record is [`day_d/economic_mandate.json`](day_d/economic_mandate.json), with the
calculation explained in
[`day_d/STAGE_0_ECONOMICS.md`](day_d/STAGE_0_ECONOMICS.md).

### NPV and economic threshold

| Input | Owner value |
|---|---:|
| Reference capital | USD 1,000,000 |
| Trading capital during first 12 months | 100% virtual; USD 0 real exposure |
| Baseline new Capex | USD 3,000; expandable by approved investment memo |
| Maximum recurring monthly data/infrastructure spend | USD 1,000 |
| Net-return target | 0.5% geometric mean across every preregistered exchange session, compounded on virtual NAV |
| Implied 252-session virtual return | Approximately 251.44% |
| Maximum acceptable peak-to-trough drawdown | 8% |
| First-session target-path edge | USD 5,000 at USD 1,000,000 NAV |
| Resulting `theta_econ` in R/session | NAV-dependent; pending fixed dollar-risk budget and full path |

### Written 12-month success definition

Trading success requires a geometric mean net return of at least 0.5% across
every preregistered exchange session in the complete 12-month virtual
experiment, after simulated execution costs, with maximum peak-to-trough
drawdown of 8%, complete reproducibility and no unresolved material
data/execution/ledger audit failure. No-trade sessions count as zero and cannot
be excluded. This is a horizon-level target, never a mandatory daily quota.
Capex and Opex are real product investments reported separately from virtual
trading NAV. A correctly powered `not validated` verdict is a valid research
result but does not satisfy the owner's economic trading-success target.

## Research question and ledgers

Primary question:

> Do S3-v1 and S5-v1, long-only, with intraday entries and conditional T-30s
> carry, have positive net economic edge?

The primary observation is consolidated net R by exchange session. Intraday
and overnight R are diagnostic decompositions. Their lifetime identity is:

`R_consolidated(position) = R_intraday(position) + R_overnight(position)`

### Proposed accounting equations -- joint freeze

For position `p`:

- `q_p`: signed quantity (positive for this long-only experiment).
- `B_p`: fixed initial dollar-risk budget; the denominator for all R components
  of this position for its entire life.
- `C_entry_p`: entry cash outflow including entry fee and simulated entry
  slippage.
- `M_p,d`: split-adjusted official close value, `q_p * close_p,d`.
- `D_p,d`: cash dividends and other point-in-time distributions attributable to
  session `d`.
- `P_exit_p`: real/simulated net proceeds after exit fee and exit slippage.

Same-session exit:

`R_intraday_p = (P_exit_p - C_entry_p + D_p,d) / B_p`

`R_overnight_p = 0`

Carry from entry session `d0`:

`R_intraday_p = (M_p,d0 - C_entry_p + D_p,d0) / B_p`

For each later marked session `d` before exit:

`DeltaR_overnight_p,d = (M_p,d - M_p,d-1 + D_p,d) / B_p`

On the actual exit session `dx`:

`DeltaR_overnight_p,dx = (P_exit_p - M_p,previous_mark + D_p,dx) / B_p`

The sum telescopes to actual net lifetime economics without a fictitious fee at
an internal close mark. Splits, symbol changes, mergers, delistings, halts and
cash/stock distributions require explicit point-in-time transformations before
the ledger can freeze.

A session with no new trade still receives carry mark changes. It is zero only
when there is no transaction and no open position with a value/distribution
change.

The official-close ledger is primary because that is the signed policy. Every
checkpoint additionally reports a liquidation-value sensitivity for unresolved
positions using the best qualified executable price and estimated exit costs;
the sensitivity never rewrites the official ledger.

### Flat-at-close counterfactual

`flat-at-close` is a separate stateful portfolio replay. Its earlier exits free
capital and slots, so all later candidate selection, fills and exposure must be
replayed under that book's own state. Repricing only the operational book's
selected trades is invalid.

## Official clock and position lifecycle

- Calendar/time zone: exchange calendar in `America/New_York`.
- Regular open: 09:30:00 ET.
- New-entry cutoff: 15:50:00 ET.
- Risk monitoring: 09:30:00 through the official close.
- T-30s starts 30 seconds before the calendar-provided official close.
- T-30s implementation contract: one-second polling of the latest fresh tick.
- T-30s sale condition: `estimated_net_exit_pnl_pct > 0` using a qualified fresh
  executable bid and the same fill/cost formula as the ledger.
- Fill must occur before the official close. Otherwise log
  `late_unfilled_exit` and carry.
- Negative positions remain protected until the close and have no maximum carry
  duration.
- Premarket is informational. A prepared action is revalidated against the
  first eligible fresh regular-session quote; no premarket fill is simulated.

### Lifecycle cases to freeze

The execution contract must include deterministic treatment for:

- no quote, stale quote, crossed/locked quote and missing quote size;
- opening gap through a hard stop;
- volatility halt and reopening auction;
- exchange early close;
- split, dividend, merger, ticker change, delisting and bankruptcy;
- a T-30s signal whose network/worker latency crosses the official close; and
- an unresolved carry at C1/C2.

## Deterministic universe proposal -- joint freeze

Each session selects 60 US common stocks using only D-1 information. QQQ is a
benchmark and market gate; it is not one of the 60 and is not traded by the
Generation 1 experimental book.

Proposed v1 rule:

1. Exchanges: Nasdaq and NYSE regular listings.
2. Security type: operating-company common stock; exclude ETF, ETN, fund,
   preferred, warrant, unit, right, SPAC shell and OTC security.
3. Point-in-time price at D-1 close: at least USD 3.
4. Require twenty completed eligible sessions ending at D-1.
5. For each session, dollar volume is split-adjusted close times split-adjusted
   regular-session volume.
6. Rank by the median of those twenty session dollar volumes, descending.
7. Tie-break by normalized ticker, ascending.
8. If a selected symbol is not tradeable on D, walk deterministically down the
   D-1 ranking; never recompute with D information.
9. Corporate actions use only the mapping known by D-1.

Changing these rules creates a new universe version and dataset version.

## Setup proposals -- joint freeze

The rules below are recommendations for the six-hands review. Until frozen,
neither setup is `replay_eligible`.

### Shared bar definitions

- Frequency: completed one-minute regular-session bars.
- Bar VWAP proxy: cumulative `typical_price * volume / cumulative_volume`, where
  `typical_price = (high + low + close) / 3`.
- RVOL: cumulative regular-session volume through the latest completed minute,
  divided by median cumulative volume through the same minute over the prior
  twenty eligible sessions; require at least fifteen historical observations.
- ATR: Wilder ATR(14) over completed one-minute bars, seeded with the previous
  regular-session close.
- Any future tick-derived VWAP, CVD or volume-at-price variant is a new setup or
  feature version and cannot silently replace these bar definitions.
- Shared executable-risk floor: **pending the frozen cost model and NPV**.

### S3-v1: ORB plus VWAP continuation

1. Opening range uses bars covering `[09:30, 09:45)`.
2. Trigger is the first completed one-minute close above `OR_high`, above the
   current bar VWAP proxy, with RVOL at least 1.5.
3. QQQ must be above its own same-definition VWAP at trigger time.
4. Trigger close must be no higher than `OR_high + 0.5 * OR_range`.
5. Entry uses the first eligible quote/trade strictly after trigger decision
   time and above trigger-bar high.
6. If the first breakout close violates the extension guard, the setup does not
   chase a later re-entry that session.
7. Initial structural stop is the higher of `OR_low` and entry-time VWAP. If
   that distance is below the shared executable-risk floor, move the stop down
   only enough to meet the floor; if that violates the setup's maximum risk,
   reject the signal.
8. Proposed scale-out: sell 50% at 1.5R. The remainder exits at the first of 2R,
   the frozen Chandelier rule or another portfolio-risk override.
9. New entries expire at 11:45 ET.

Items 7-8 remain open until risk floor, maximum risk and Chandelier precedence
are frozen together.

### S5-v1: bar-based VWAP mean reversion

1. No CVD, order-flow or index gate.
2. Excursion begins when a completed bar low reaches at least 1.5 ATR below the
   current VWAP proxy.
3. Reclaim requires a later completed bar to close above the midpoint of its
   immediately preceding completed bar, with RVOL at least 1.5.
4. Entry uses the first eligible quote/trade above the reclaim-bar high within
   the next three completed bars.
5. Stop is one minimum price increment below the excursion low, subject to the
   shared executable-risk floor and maximum risk.
6. Proposed target is the VWAP value frozen at entry; a dynamic moving target is
   deliberately excluded from v1 to keep the contract auditable.
7. Exit if the target is not reached within 45 minutes.
8. New entries expire at 14:30 ET.

## Execution and cost contract -- joint freeze

The final fill contract must use one implementation for replay, live shadow and
paper comparison:

- signal time and feature `as_of` are distinct fields;
- the signal bar cannot fill itself;
- entry and exit use the first eligible observation after decision time;
- quote freshness, minimum size and trade fallback are numerical, not prose;
- fee, SEC/TAF, spread, slippage and latency models are versioned;
- optimistic, point and pessimistic cost scenarios are all reported;
- raw R, MFE and MAE are never clipped in scientific storage; and
- every result carries setup, commit, dataset, feature, cost, clock, universe
  and run-mode versions.

## Inference workstream

The draft values `theta=0.5R/session`, `N=120` and `sigma=2.6` already failed
their own class-kill power requirement and are not defaults.

Stage 0 performs feasibility only, using burned data and owner-supplied
`theta_econ`. Stage 2 performs final calibration with the frozen harness and
observed dependence.

The first analytic screen is recorded in
[`day_d/STAGE_0_RISK_POWER_FEASIBILITY.md`](day_d/STAGE_0_RISK_POWER_FEASIBILITY.md).
It compares fixed-risk scenarios but deliberately selects none; its draft
sigma, Bonferroni split and independent-arm assumption are not final evidence.

Required properties:

- observations are daily consolidated net R, including carry marks;
- C1 and C2 remain fixed at sessions 60 and 120 unless feasibility explicitly
  proves that horizon incompatible with the stated economic objective;
- multiplicity covers both checkpoints, both arms and the class verdict;
- `retained` is not positive evidence;
- approval requires a pre-selected lower-bound rule plus economic threshold and
  a paired-placebo win;
- carry-induced serial dependence is modeled in joint simulation;
- an iid parametric p-value is not authoritative;
- weekly moving-block bootstrap is mandatory sensitivity; and
- all data through August 2026 remains burned forever.

## Numeric data gates to write before measurement

| Gate | Must freeze |
|---|---|
| T0 host capacity | CPU/RSS/iowait ceilings, queue lag/high-water, bytes/s, drop/error maximum and disk reserve |
| T1 trade coverage | matched event/volume tolerance by symbol and session |
| T4 BBO quality | maximum age, bid/ask correspondence, spread and stale coverage |
| T5 bars/close | OHLCV and official-close divergence tolerances |

The numbers are selected before the five live capture sessions are viewed.
Disk free-space guard and automatic capture shutdown are prerequisites to
enabling capture. Manifest, checksum, verified upload and cold storage are
Stage 2 prerequisites to durable retention.

## Stage 0 completion checklist

- [x] Blueprint signed by Dudu, Fable and Codex for Stage 0.
- [x] Authorization boundary represented in a machine-readable contract.
- [x] Generation 1 reduced to S3-v1 and S5-v1; S5-v1 has no CVD.
- [x] T-30s/carry and three-ledger identities made explicit.
- [x] Carry-induced statistical dependence recorded.
- [x] Dudu supplies NPV inputs and written 12-month success definition.
- [x] Preliminary fixed-risk/power scenario grid is reproducible.
- [ ] Six-hands review freezes fixed dollar risk and converts the economic floor into R/session.
- [ ] Six-hands review freezes universe rules.
- [ ] Six-hands review freezes S3/S5 formulas and lifecycle rules.
- [ ] Cost and fill contract is numerical and versioned.
- [ ] T0/T1/T4/T5 numerical gates are frozen before measurement.
- [ ] Preliminary `theta/N/alpha` feasibility report is attached.
- [ ] Draft pre-registration is complete and internally consistent.

Only after every unchecked item is complete may a later pull request propose
changing either setup to `replay_eligible`. Stage 1 still requires a separate
approval.
