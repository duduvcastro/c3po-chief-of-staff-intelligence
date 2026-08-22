# Day D preliminary risk and power feasibility

Status: **analytic screen over burned assumptions; no scenario selected**  
Reproducer: `python -m app.day_d_feasibility`

## Purpose

Translate the owner's economic mandate into comparable fixed-risk scenarios
before any risk value is frozen. This is a feasibility screen, not the final
joint simulation and not a recommendation to change production.

## Provisional assumptions

- Reference capital: USD 1,000,000.
- Maximum drawdown: 8%.
- Required geometric net return: 0.5% of current virtual NAV per session.
- First-session target-path contribution at USD 1,000,000 NAV: USD 5,000.
- Last-session target-path contribution after 251 sessions at target: USD
  17,484.43.
- Maximum simultaneous positions: five.
- Burned draft session volatility: 2.6R.
- Checkpoints: 60 and 120 sessions.
- Family alpha: 5%, provisionally divided over six decisions.
- Target power: 80%.
- Class-kill approximation: both arms killed, provisionally independent.

The provisional one-sided minimum detectable mean is 1.086R/session at C1 and
0.768R/session at C2.

## Scenario grid

| Fixed risk/trade | NAV/trade | Five-slot stop risk | Target R at start | Target R in last session | Full -1R losses to 8% | Sessions for 80% power at start |
|---:|---:|---:|---:|---:|---:|---:|
| USD 500 | 0.05% | 0.25% | 10.000R | 34.969R | 160.0 | 1 |
| USD 1,000 | 0.10% | 0.50% | 5.000R | 17.484R | 80.0 | 3 |
| USD 1,500 | 0.15% | 0.75% | 3.333R | 11.656R | 53.3 | 7 |
| USD 2,000 | 0.20% | 1.00% | 2.500R | 8.742R | 40.0 | 12 |
| USD 2,500 | 0.25% | 1.25% | 2.000R | 6.994R | 32.0 | 18 |
| USD 3,000 | 0.30% | 1.50% | 1.667R | 5.828R | 26.7 | 26 |
| USD 4,000 | 0.40% | 2.00% | 1.250R | 4.371R | 20.0 | 46 |
| USD 5,000 | 0.50% | 2.50% | 1.000R | 3.497R | 16.0 | 71 |

## Interpretation

Smaller risk budgets make the dollar drawdown safer but require extremely high
R production every session. The requirement is also non-stationary under fixed
dollar risk: it rises as virtual NAV compounds. Apparent statistical power at
the starting NAV is not evidence that S3/S5 can attain or sustain that return.
It only says such a very large mean would be easy to distinguish from zero if
it existed.

Larger risk budgets reduce the required R/session but consume the 8% drawdown
allowance much faster. At USD 5,000 per trade, five initial stops expose 2.5%
of NAV and sixteen full-R losses consume the complete drawdown allowance.

No row is approved. The current evidence supports only a review range, not a
choice. S3/S5 replay must estimate attainable mean R, session sigma, arm
correlation, turnover, costs, carry dependence and the full compounding path
before the six-hands group freezes risk.

## Known limitations

1. The 2.6R volatility is inherited from burned draft work, not measured from
   the new S3/S5 policy-complete book.
2. Bonferroni allocation is a conservative placeholder; Stage 2 calibrates the
   full decision family jointly.
3. The class-kill column assumes independent arm statistics.
4. Carry-induced serial dependence is not represented in this analytic screen.
5. The calculation tests detectability, not whether the economic edge is
   achievable.
6. Power is shown at the reference NAV only; a fixed-dollar risk budget makes
   the target R/session increase as NAV compounds.

These limitations are why the report may narrow questions but cannot authorize
risk or capital.
