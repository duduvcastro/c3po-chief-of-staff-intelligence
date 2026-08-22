# Day D frozen risk and preliminary power feasibility

Status: **risk selected for paper research; joint calibration pending Stage 2**

Reproducer: `python -m app.day_d_feasibility`

## Purpose

Record the selected NAV-relative risk policy, keep the product target separate
from the economic kill floor, and expose what the burned analytic assumptions
can and cannot establish. This report does not authorize production behavior
or real capital.

## Frozen paper-risk scenario

| Item | Frozen value |
|---|---:|
| Risk per trade | 0.15% of current virtual NAV at entry |
| Initial `1R` at USD 1M NAV | USD 1,500 |
| Dollar cap during paper | None |
| Maximum simultaneous positions | 5 |
| Maximum aggregate initial stop risk | 0.75% NAV |
| Aggregate initial stop risk at USD 1M | USD 7,500 |
| Individual full-R losses to 8% DD | 53.33 |
| Five-stop sessions to 8% DD | 10.67 |

The dollar value assigned to a trade is fixed for that trade's lifetime. A new
trade uses 0.15% of then-current virtual NAV. This keeps portfolio risk
proportional while preserving an immutable R denominator in the ledger.

## Product target versus kill floor

| Threshold | Value | Authority |
|---|---:|---|
| `theta_meta` | 3.333333R/session | Product target only; no kill authority |
| `theta_kill` | 0.15R/session | Binding economic floor at C1/C2 under optimistic costs |

`theta_meta = 0.5% / 0.15%`. It is stationary because target and risk both
scale with current NAV. Statistical detectability does not establish that this
ambition is attainable.

The `theta_kill` planning decomposition is 0.0396825R/session of annual product
cost and 0.1103175R/session of opportunity-cost budget. The benchmark is the
US 3-month Treasury bill; its rate is frozen on the final preregistration hash
date. The 4.17% annualized figure emitted by the calculator is only the rate
implied by the rounded planning decomposition, not a current market quote.

## Burned analytic screen

The provisional screen retains these assumptions only to make the math
reproducible:

- session volatility: 2.6R;
- checkpoints: 60 and 120 sessions;
- provisional one-sided futility alpha: 5%;
- placebo alpha: 5%, with minimum delta 0.10R;
- two active arms; and
- target joint zero-edge class kill: at least 80%.

The provisional one-sided minimum detectable mean is 0.835R/session at C1 and
0.590R/session at C2. A futility blade alone would kill a zero-edge arm in only
about 11.55% of worlds at C1 and 15.56% at C2. This is intentionally not asked
to carry the whole class-kill requirement.

For review only, assume independent arms, let a placebo pass under H0 with
probability 5%, and give the damage blade no additional kill credit. An arm
survives only if it survives futility and passes placebo. Under those simplifying
assumptions, the combined class-kill probability is approximately:

| Checkpoint | Futility-only kill per arm | Illustrative joint class kill |
|---|---:|---:|
| C1, 60 sessions | 11.55% | 91.35% |
| C2, 120 sessions | 15.56% | 91.73% |

The illustration exceeds 80%, but it is not an acceptance result. Stage 2 must
simulate the complete joint futility + damage + placebo rule with observed arm
dependence, carry serial dependence and frozen costs. Only that simulation can
freeze final N/alpha and certify the required class-kill probability.

## Outcome classification

The exact ledger preserves the sign of realized net P&L without an epsilon.
The robust win-rate analysis separately applies:

`epsilon_trade = max(exit_half_spread * quantity, USD 0.01 * quantity)`

Values inside `[-epsilon, +epsilon]` are robust ties and are excluded from the
robust win-rate denominator. The epsilon measures fill uncertainty; reusing
round-trip cost would penalize the same cost twice. The robust win-rate lower
confidence bound must exceed 50% only in the final 12-month verdict, using
session-block bootstrap. C1/C2 win rates, payoff ratio and profit factor are
diagnostics.

## Known limitations

1. The 2.6R volatility is inherited from burned draft work, not measured from
   the policy-complete S3/S5 book.
2. Checkpoint N and alpha remain provisional until Stage 2.
3. The analytic joint illustration assumes independent arms.
4. It gives no extra kill credit to the damage blade.
5. Carry-induced serial dependence is not represented.
6. The final T-bill rate is unavailable until the preregistration hash date.
7. Detectability of `theta_meta` or `theta_kill` does not prove attainable
   economic edge.

The next sequence remains: contract PR, official S3/S5 replay, five-year
historical distribution, then final preregistration with hash.
