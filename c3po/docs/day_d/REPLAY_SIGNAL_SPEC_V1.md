# Day D official replay signal specification v1

Status: **frozen when this pull request is merged after six-hands review**

Machine contract:
[`replay_signal_spec_v1.json`](replay_signal_spec_v1.json)

Governing contract: [`stage0_contract.json`](stage0_contract.json)

This document freezes the signal, feature, risk-sizing and point-in-time
universe rules for the official `S3-v1` and `S5-v1` replay. It changes no
production behavior, authorizes no capital and contains no replay engine.

The later harness pull request must implement this contract exactly. It will
separately freeze eligible observations, latency, fills, costs, halt/reopening
behavior, corporate-action ledger accounting and the synthetic-truth CI gate.

## Version boundary

| Component | Frozen version |
|---|---|
| Contract | `DAY-D-SIGNAL-UNIVERSE-v1` |
| Features | `DAY-D-FEATURES-v1` |
| Universe | `DAY-D-UNIVERSE-v1` |
| Continuation setup | `S3-v1` |
| Mean-reversion setup | `S5-v1` |
| Risk policy | `DAY-D-RISK-v1` |

A material change to any rule below creates a new version and a new evidence
history. It may not rewrite an existing run.

## Causal clock

- Exchange calendar and time zone: `America/New_York`.
- Only the regular session is eligible.
- A one-minute bar represents `[minute_start, minute_end)` and is unavailable
  before `minute_end`.
- A decision may use only inputs whose `event_at` and `available_at` are no
  later than `decision_at`.
- The signal bar cannot fill itself. Entry activation starts strictly after the
  signal decision.
- A correction received later cannot rewrite what an earlier decision knew.

These are data-model invariants, not optional validation warnings.

## Point-in-time universe

Each session receives one immutable D-1 manifest:

1. Select 60 unique issuers from `XNAS` and `XNYS`; add `QQQ` only as a
   non-tradeable benchmark.
2. Include US domestic operating-company common stock and US equity REIT common
   stock.
3. Exclude ADR/ADS, foreign ordinary shares, ETF/ETN/funds, preferred shares,
   warrants, units, rights, SPAC shells, closed-end funds and OTC securities.
4. Require an official D-1 close of at least USD 3 and exactly 20 completed
   eligible sessions for ranking.
5. For each session, compute dollar volume as the point-in-time split-adjusted
   official close multiplied by point-in-time split-adjusted regular-session
   volume.
6. Rank by the median of those 20 observations, descending, then normalized
   ticker ascending.
7. If several share classes belong to one issuer, keep the class with the
   greatest median dollar volume; break a tie by normalized ticker.
8. Include a delisted symbol when it was active as of D-1. Never use a future
   corporate action, adjustment or symbol mapping.
9. Before 09:25 ET, a selection may be replaced only for a delisting, merger,
   cancellation or retired point-in-time symbol mapping effective before the
   regular open. Walk down the already-frozen D-1 ranking. Missing bars or
   quotes, provider outages, halts, low volume and price moves do not authorize
   replacement. No D information may recompute the rank.
10. If fewer than 60 valid issuers remain, run with fewer and emit
    `universe_shortfall`.

The manifest records selection inputs, rank, issuer identity, substitutions,
`data_as_of` and the universe version.

## Shared features

### Completed one-minute bar

Only eligible regular-session trades contribute. OHLCV is formed from first,
maximum, minimum and last eligible prices plus summed eligible size. An empty
minute is missing; it is not forward-filled and cannot trigger a signal.

### VWAP

VWAP resets each session and uses completed bars only:

`typical_price = (high + low + close) / 3`

`VWAP_t = sum(typical_price_i * volume_i) / sum(volume_i), i <= t`

VWAP is unavailable while cumulative volume is zero.

### RVOL

`RVOL_t` is current-session cumulative volume through the latest completed
minute divided by the median cumulative volume through the same minute over the
prior 20 eligible sessions. The current session is excluded and at least 15
historical same-minute observations are required.

### ATR

ATR is Wilder ATR(14) over completed one-minute true ranges:

`TR_t = max(high-low, abs(high-prev_close), abs(low-prev_close))`

The first current-session bar uses the official D-1 close as `prev_close`. The
seed is the simple mean of the first 14 completed true ranges; subsequent
values use `(previous_ATR * 13 + current_TR) / 14`. ATR is unavailable before
14 completed bars.

## Shared risk and sizing

- Risk budget: 0.15% of current virtual NAV at entry, converted to dollars and
  frozen for the trade's lifetime.
- Maximum five simultaneous positions, aggregate initial stop risk of 0.75% of
  NAV, no leverage and no duplicate symbol across setups.
- Position notional may not exceed 20% of NAV.
- Quantity may not exceed 1% of the volume in the prior five completed
  one-minute bars.
- Minimum stop distance per share:
  `max(0.5 * entry_ATR, point-model full spread, 2 * minimum_tick)`.
- If a structural stop is too close, move it downward only enough to meet that
  minimum. Reject if the resulting stop distance exceeds `2.0 * entry_ATR`.
- Risk per share includes point-scenario stop execution economics, not merely
  the distance between two displayed prices.
- Quantity is integer `floor(risk_budget_usd / risk_per_share_usd)`.
- A notional, participation, cash or minimum-quantity breach rejects the signal;
  it does not silently resize it.
- If both setups accept the same symbol, the first accepted signal keeps it and
  the later signal is blocked and logged.

The point-model spread and stop execution economics are inputs of the later
frozen cost/fill contract. The formulas and the rejection behavior are frozen
here.

## S3-v1: ORB plus VWAP continuation

One attempt per symbol per session:

1. Opening range is exactly the 15 completed bars covering `[09:30,09:45)`.
   A missing bar, halt or zero range disables S3 for that symbol that session.
2. The raw event is the first later completed bar with `close > OR_high`.
3. At that bar's end, all gates must hold simultaneously:
   - close above `OR_high`;
   - close above current completed-bar VWAP;
   - RVOL at least 1.5;
   - latest completed QQQ close above its same-definition VWAP, with that QQQ
     bar no more than one minute older than the breakout bar;
   - close no higher than `OR_high + 0.5 * OR_range`; and
   - decision time before 11:45 ET.
4. If that first raw breakout fails any gate, the symbol expires for S3 that
   session. A later breakout cannot rearm it.
5. Entry activates on the first execution-eligible observation strictly after
   the decision and above the breakout-bar high. It expires after three
   completed bars or at 11:45 ET, whichever comes first; a fill must occur
   strictly before that expiry timestamp.
6. Premarket cannot trigger S3. A gap is absorbed into the current session's
   opening range; previous close is not a second trigger.
7. Initial structural stop is `max(OR_low, entry_time_VWAP)`, subject to the
   shared stop floor and maximum.
8. R levels use the trade's frozen risk per share. Sell 50% at 1.5R, rounded
   down to whole shares; a one-share position skips the partial.
9. After the partial fills, the runner exits at the first of 2R, a 2.5-ATR
   Chandelier or a portfolio risk override.
10. The Chandelier uses eligible post-entry trade highs and the latest completed
    one-minute ATR. Its level is monotonic:
    `max(previous_level, high_water - 2.5 * ATR)`.

When several S3 exits share a timestamp, precedence is: initial/hard stop,
Chandelier, 2R target, then T-30s or another portfolio override.

## S5-v1: bar-based VWAP mean reversion

S5-v1 deliberately uses no CVD, order flow or QQQ gate. One attempt is allowed
per symbol per session:

1. Evaluation begins only after ATR is available.
2. Excursion is the first completed bar whose low is at or below
   `VWAP - 1.5 * ATR`.
3. A later completed reclaim bar must close above the midpoint of its
   immediately preceding completed bar and have RVOL at least 1.5.
4. Entry activates on the first execution-eligible observation strictly after
   the decision and above the reclaim-bar high. It expires after three
   completed bars or at 14:30 ET, whichever comes first. A fill must occur
   strictly before that expiry timestamp; no new fill at or after 14:30 ET is
   allowed.
5. Structural stop is one minimum tick below the lowest completed-bar low from
   excursion through reclaim, subject to the shared floor and maximum.
6. Target is the completed-bar VWAP observed at entry fill time and is frozen
   for the trade's lifetime. Signal validity is decided ex ante: decision-time
   VWAP must be strictly above the reclaim-bar high. A later adverse fill above
   the frozen target remains a real trade and exits under the normal rules; it
   is never removed retroactively.
7. Exit at the target or after 45 minutes, whichever comes first, unless a
   stop or portfolio risk override acts earlier.
8. A failed or expired attempt cannot rearm that session.

When several S5 exits share a timestamp, precedence is: initial/hard stop,
frozen VWAP target, 45-minute timeout, then T-30s or another portfolio
override.

## Audit record

Every candidate decision must preserve, at minimum: setup, feature and universe
versions; session and symbol; event, availability and decision timestamps;
feature `as_of`; every gate value and result; rejection/suppression reason;
entry expiry; risk budget; structural and post-floor stops; ATR, VWAP, RVOL and
universe rank.

## Explicitly deferred to the harness contract

The following are not silently decided by this specification:

- fresh quote and execution-eligible observation definitions;
- 500ms base latency, jitter and fragility grid;
- marketable entry fill mechanics;
- two-print stop confirmation and minimum notional;
- halt and reopening fills;
- quintile-by-time-bucket cost table and its scenarios;
- corporate-action, delisting and bankruptcy ledger mechanics; and
- synthetic zero/positive/negative truth as a mandatory CI gate.

Until those items are frozen and implemented, `S3-v1` and `S5-v1` are not
officially replay-eligible and no reported result may be treated as evidence.
