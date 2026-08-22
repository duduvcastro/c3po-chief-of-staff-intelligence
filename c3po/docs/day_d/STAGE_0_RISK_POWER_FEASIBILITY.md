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
- Required gross contribution: USD 4,027.78 per session.
- Maximum simultaneous positions: five.
- Burned draft session volatility: 2.6R.
- Checkpoints: 60 and 120 sessions.
- Family alpha: 5%, provisionally divided over six decisions.
- Target power: 80%.
- Class-kill approximation: both arms killed, provisionally independent.

The provisional one-sided minimum detectable mean is 1.086R/session at C1 and
0.768R/session at C2.

## Scenario grid

| Fixed risk/trade | NAV/trade | Five-slot stop risk | Required R/session | Full -1R losses to 8% | Sessions for 80% power | H0 class kill at C2 |
|---:|---:|---:|---:|---:|---:|---:|
| USD 500 | 0.05% | 0.25% | 8.056R | 160.0 | 2 | 100.0% |
| USD 1,000 | 0.10% | 0.50% | 4.028R | 80.0 | 5 | 100.0% |
| USD 1,500 | 0.15% | 0.75% | 2.685R | 53.3 | 10 | 100.0% |
| USD 2,000 | 0.20% | 1.00% | 2.014R | 40.0 | 18 | 100.0% |
| USD 2,500 | 0.25% | 1.25% | 1.611R | 32.0 | 28 | 100.0% |
| USD 3,000 | 0.30% | 1.50% | 1.343R | 26.7 | 40 | 99.9% |
| USD 4,000 | 0.40% | 2.00% | 1.007R | 20.0 | 70 | 93.7% |
| USD 5,000 | 0.50% | 2.50% | 0.806R | 16.0 | 110 | 70.8% |

## Interpretation

Smaller risk budgets make the dollar drawdown safer but require extremely high
R production every session. Their apparent statistical power is not evidence
that S3/S5 can attain that return. It only says such a very large mean would be
easy to distinguish from zero if it existed.

Larger risk budgets reduce the required R/session but consume the 8% drawdown
allowance much faster. At USD 5,000 per trade, five initial stops expose 2.5%
of NAV and sixteen full-R losses consume the complete drawdown allowance. That
scenario also misses the draft requirement of at least 80% probability of
killing both zero-edge arms at C2 under the provisional independence model.

No row is approved. The current evidence supports only a review range, not a
choice. S3/S5 replay must estimate attainable mean R, session sigma, arm
correlation, turnover, costs and carry dependence before the six-hands group
freezes risk.

## Known limitations

1. The 2.6R volatility is inherited from burned draft work, not measured from
   the new S3/S5 policy-complete book.
2. Bonferroni allocation is a conservative placeholder; Stage 2 calibrates the
   full decision family jointly.
3. The class-kill column assumes independent arm statistics.
4. Carry-induced serial dependence is not represented in this analytic screen.
5. The calculation tests detectability, not whether the economic edge is
   achievable.

These limitations are why the report may narrow questions but cannot authorize
risk or capital.
