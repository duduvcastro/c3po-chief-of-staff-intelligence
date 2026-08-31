# ENTRY QUALITY STUDY V1 - POLICY MILESTONES

This append-only companion records live admission changes without altering the
six-hands frozen study contract. Reports must segment observations at each
milestone and must not pool before/after results as one policy.

## 2026-08-31 - derived portfolio capacity v1

- Milestone id: `2026-08-31-derived-portfolio-capacity-v1`.
- Predecessor deployed: PR #345, commit `c2da7fd5ce1f074f0256acce93b3d2eef206fc20`,
  effective at `2026-08-31T19:23:35Z`.
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

