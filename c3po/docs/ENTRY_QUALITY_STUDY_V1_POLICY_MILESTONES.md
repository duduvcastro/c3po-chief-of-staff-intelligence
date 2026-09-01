# ENTRY QUALITY STUDY V1 - POLICY MILESTONES

This append-only companion records live admission changes without altering the
six-hands frozen study contract. Reports must segment observations at each
milestone and must not pool before/after results as one policy.

## 2026-08-31 18:14:27 UTC - live review window 550

- Source: PR #344, head `849f7d41941df82e807a3b3e5ea733834239cd2f`,
  merge commit `81b0d1d6016f804f190c7a3fb66e0203a5f36442`.
- `r2d2_ws_max_symbols = 550` simultaneous symbols total, not per market.
- NASDAQ and NYSE share the same global entitlement.
- Open US positions reserve stream slots before analysis candidates.
- Remaining slots keep the existing deterministic cross-market rotation.
- Entry thresholds, sizing, exits and portfolio limits were unchanged.

## 2026-08-31 19:11:00 UTC - persistent entry admission

- Source: PR #345, head `5ac34dd94a785ba0ad84282931d2b6178ef3aa72`,
  merge commit `c2da7fd5ce1f074f0256acce93b3d2eef206fc20`.
- `entry_confirmation_reviews = 2` consecutive reviews on distinct live ticks.
- `max_new_positions_per_scan = 4`, shared by ordinary and rotation BUYs.
- Confirmed names deferred by the scan cap remain eligible for the next scan.
- Worker restart or failed cycle clears pending confirmations fail-closed.
- Cycle metadata records confirmation pending, burst deferred and accepted counts.
- Sizing, stops, exit thresholds and the 20-position ceiling were unchanged.

## Next successful deploy - derived portfolio capacity v1

- Milestone id: `2026-08-31-derived-portfolio-capacity-v1`.
- Source: PR #346, head resolved from the deployed methodology record.
- Confirmation remains two consecutive reviews on distinct live ticks.
- New positions remain capped at four per scan.
- The empirical 20-position ceiling is removed.
- Position count now emerges from the signed limits: 6% per name, 48% per
  market, 95% gross exposure and at least 5% cash.
- The milestone becomes effective with the first successful production deploy
  carrying methodology `R2D2-HYBRID-V28-DERIVED-PORTFOLIO-CAPACITY`.
- Each cycle records the full policy at `entry_admission.capacity_policy`; each
  entry-score observation carries the same object in `candidate_context`.
- Evaluation note: the four-per-scan pacing is intentionally unchanged and is
  reviewed only after multiple live sessions. Removing the count ceiling does
  not authorize burst entries.
