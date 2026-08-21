# R2D2 committee: Phase 0 specification

Status: **draft for methodological sign-off; no production-capital behavior**  
Specification version: `COMMITTEE-PHASE0-v0.1`  
Created: 2026-08-21

## Purpose

Replace reactive modification of one intraday entry route with a governed
committee of immutable, independently testable hypotheses. The committee has
four separate layers:

1. **Ranker** -- orders symbols by expected opportunity at a point in time.
2. **Setup** -- owns entry, invalidation, stop, target and expiration rules.
3. **Bandit** -- allocates capital among already-qualified setup versions.
4. **Risk** -- enforces portfolio, correlation, loss and execution constraints.

No layer may silently perform another layer's job. Every decision shown in the
dashboard must identify the contribution of each layer.

## Immutable setup lifecycle

Each material rule change creates a new setup version and an empty live
posterior. Versions progress through:

`draft -> replay_eligible -> live_shadow -> capital_limited -> capital_active`

Exceptional states are `suspended` and `retired`. Promotion from
`live_shadow` is never automatic. Fifty closed live-shadow trades only make a
version eligible for review; they do not prove positive expectancy.

Replay may initialize a weak prior equivalent to at most 10-15 observations.
Replay alone can never authorize capital. A change from approximated VPOC to
tick-derived VPOC is a material change (`S2-v1` to `S2-v2`) and does not inherit
the earlier posterior.

## Shared execution contract

All setups use the same point-in-time execution simulator:

- Decision time and data `as_of` are stored independently.
- Entry is filled from the first eligible quote/bar after the signal, never the
  bar that was still forming when the signal was evaluated.
- Entry and exit slippage and fees match the paper ledger's market-specific
  formulas.
- `raw_r_multiple` is persisted without clipping.
- `posterior_r_multiple` is derived at posterior-update time only and clipped
  initially to `[-3R, +5R]`.
- MFE and MAE are persisted without clipping.
- A signal expires if no valid fill occurs within its setup-defined window.
- Simultaneous signals for the same symbol are stored separately but the risk
  layer prevents duplicate economic exposure.

The following identifiers are mandatory on every result: setup version,
source commit, dataset version, feature schema version, cost model version,
clock version and run mode.

## Official clock

- Time zone: `America/New_York`, with exchange-calendar DST handling.
- Regular US session: 09:30:00-16:00:00 ET on valid exchange sessions.
- New capital entries: no later than 15:50:00 ET.
- Risk monitoring: through 16:00:00 ET.
- End-of-day behavior remains owned by the production risk policy, not by an
  individual setup.
- Early closes must come from an exchange calendar, never a hardcoded 16:00.

## Anti-lookahead rules

- Features may use only observations with `event_at <= decision_at` and that
  were received by `decision_at`.
- A completed bar becomes available only after its close timestamp.
- Previous-session levels use the version available before the current open.
- Cross-sectional percentiles use only the contemporaneously observable
  universe.
- Corporate actions and fundamentals must be point-in-time versions.
- Walk-forward folds split by session date. Random row splits are forbidden.
- Training labels are purged/embargoed across overlapping forward horizons.

## Setup hypotheses

These rules are the proposed `v1` contracts. Thresholds remain frozen once a
version enters `replay_eligible`; changing one creates a new version.

### S1-v1: institutional opening momentum

Hypothesis: unusually strong, broad and liquid first-half-hour demand has
continuation value later in the same session.

- Universe: eligible US common stocks and ETFs with valid live data.
- Observation window: 09:30-10:00 ET.
- Long candidate: positive 30-minute return, above session VWAP, opening return
  in the top decile of the contemporaneous eligible universe, relative volume
  at least 1.5, and no material stale-data flag.
- Entry window: 10:00-11:00 ET, first pullback that holds VWAP and resumes above
  the prior five-minute high. Do not buy the 10:00 close mechanically.
- Extension guard: entry no more than 1 ATR above VWAP.
- Initial stop: below VWAP or pullback low, whichever is closer while preserving
  at least the shared minimum executable risk distance.
- Exit: 2R target or existing Chandelier policy; signal expires at 11:00 ET.

### S2-v1: previous-session value-area rejection (approximated)

Hypothesis: rejection after auctioning beyond the previous session's value
area predicts rotation back toward value.

- Build a 70% previous-session value area from one-minute OHLCV by assigning
  volume to deterministic price bins. This is explicitly approximate.
- Long candidate: trades below `VAL`, then closes back inside value with rising
  trade intensity and price above the reclaim bar midpoint.
- Entry: break of reclaim bar high within three completed one-minute bars.
- Stop: below the excursion low.
- First target: VPOC; second target: `VAH` or 2R, whichever is reached first.
- Expiration: 30 minutes after reclaim.

`S2-v2` will use actual trade-by-trade volume at price and starts with a new
posterior.

### S3-v1: opening-range breakout plus VWAP

- Opening range: 09:30-09:45 ET.
- Long trigger: first completed one-minute close above `OR_high`, above VWAP,
  with relative volume at least 1.5.
- Extension guard: price no higher than `OR_high + 0.5 * OR_range`.
- Entry: first subsequent trade/quote above the trigger bar high.
- Stop: nearer valid structural level of `OR_low` or VWAP, subject to the shared
  executable-risk floor.
- Exit: 1.5R partial/2R final or Chandelier according to the frozen exit contract.
- Entry deadline: 11:45 ET.

### S4-v1: Raschke 80-20 reversal, long-only

- Prior session must open in its upper 20% and close in its lower 20%.
- Current session must trade below the prior low, then reclaim it.
- Entry: break above the reclaim bar high within three completed one-minute bars.
- Stop: below the current-session excursion low.
- Target: prior-session midpoint first, then prior close or 2R.
- Signal expires 45 minutes after the first excursion below the prior low.

The short mirror is out of scope while R2D2 remains long-only.

### S5-v1: VWAP mean reversion

- Regime filter: broad market and symbol trend-efficiency below their frozen
  trend thresholds; no material event in the exclusion window.
- Excursion: price at least 1.5 intraday ATR below VWAP.
- Exhaustion: selling intensity stops accelerating and CVD no longer makes a
  confirming low while price does.
- Entry: reclaim of the prior one-minute bar midpoint.
- Stop: below excursion low.
- Target: VWAP; abandon if VWAP is not reached within 45 minutes.
- Entry deadline: 14:30 ET.

## Event filter

FMP material events are initially categorical, not directional sentiment:

- earnings/guidance;
- merger or acquisition;
- material regulatory disclosure;
- dividend/corporate action.

Every setup declares whether an event excludes the symbol or selects an
event-specific regime. LLM sentiment is not an entry score.

## Thompson allocator

- Reward: closed-trade net R-multiple.
- Stored values: unclipped raw R and clipped posterior R.
- Initial posterior family: Normal-Inverse-Gamma.
- Decay: 45 trading-session half-life.
- Replay prior: capped at 10-15 effective observations.
- Live shadow: full statistical weight.
- Shadow signals continue at capital weight zero, including suspended arms.
- Correlation affects aggregate allocation, not each arm's learned reward.
- A v2 allocation layer may apply correlation penalties after independent arm
  performance is established.

## Circuit breakers

Pre-register numerical limits before capital activation. Required breakers:

- per-arm drawdown in R over a fixed number of sessions;
- committee drawdown;
- stale or insufficient data coverage;
- abnormal observed slippage versus the cost model;
- divergence between simulated and paper/live fills;
- operational error or incomplete audit record.

An arm breaker returns that version to `live_shadow`. Re-entry into capital
requires an explicit review; Thompson Sampling cannot override a breaker.

## Supervised ranker research lane

The ranker is not a sixth setup. It consumes point-in-time setup signals,
microstructure, cross-sectional strength, liquidity, event and regime features.

- Start logging operated and non-operated candidates immediately.
- Targets: net returns at 5/15/30/60 minutes, MFE and MAE.
- First models: regularized linear baseline, then LightGBM ranking.
- Validation: purged walk-forward only.
- Shadow comparison: current `pretrade_rank`, simple cross-sectional baselines
  and random/liquidity controls.
- Minimum live logging window before serious promotion review: 60-90 sessions.
- No capital use until it beats the baseline out of sample and then in live shadow.

## Phase 0 exit criteria

- Methodology owners approve the five textual setup contracts.
- One-minute data availability and retention are measured, not assumed.
- Raw trade/quote capture is running with drop/error telemetry.
- Cost, clock, feature and dataset schemas are versioned.
- Replay and live-shadow provenance cannot be mixed silently.
- Promotion and circuit-breaker thresholds are registered before results are viewed.

