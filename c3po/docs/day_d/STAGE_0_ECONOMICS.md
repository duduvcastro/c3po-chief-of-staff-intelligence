# Day D Stage 0 economics

Status: **owner inputs recorded; R-normalized threshold pending**  
Source: [`economic_mandate.json`](economic_mandate.json)

## Owner mandate

- Reference capital: USD 1,000,000.
- Trading capital: entirely virtual for the first 12 months; no real trading
  capital is exposed during this research horizon.
- Net-return target: 0.5% geometric mean across every preregistered exchange
  session, compounded on current virtual NAV and measured over the complete
  horizon. A no-trade session counts as 0%; negative and no-trade sessions
  cannot be removed from the denominator.
- The target is not a mandatory daily quota. The system must never manufacture
  trades, weaken gates or increase risk merely to reach 0.5% on a particular
  day.
- Maximum drawdown: 8% peak-to-trough, without calendar reset.
- Recurring data/infrastructure budget: at most USD 1,000 per month.
- Baseline new Capex: USD 3,000.
- Capex above USD 3,000 is possible only after an incremental investment memo
  and explicit owner approval.

Existing purchases are sunk costs and do not count as new Capex. Any existing
subscription that continues during the experiment does count toward the USD
1,000 monthly forward-cost ceiling. Capex and Opex are real investments in the
product. They are tracked in the project-economics ledger, while the trading
portfolio remains virtual.

## Preliminary translation

Using 252 sessions only as a planning assumption:

- maximum planned forward cost in year one: USD 15,000;
- target terminal virtual NAV: approximately USD 3,514,370.64;
- target virtual trading profit: approximately USD 2,514,370.64;
- implied 252-session net return: approximately 251.44%;
- separate project-economic surplus after the maximum USD 15,000 forward
  product cost: approximately USD 2,499,370.64;
- first-session target-path contribution: USD 5,000.00;
- last-session target-path contribution: approximately USD 17,484.43;
- equivalent simple average virtual profit: approximately USD 9,977.66 per
  session; and
- return-to-drawdown target: approximately 31.43.

The first-session, last-session and simple-average figures only describe the
mathematical path that earns exactly 0.5% every session. They are not daily
quotas and do not authorize forced trading.

The final session count comes from the exchange calendar starting on the first
unburned session after the hashed pre-registration. Actual spend replaces the
maximum budget in the final NPV, but feasibility uses the maximum to avoid
making the target easier by silently assuming that approved capacity is free.

## Why `theta_econ` is not a fixed dollar or R value yet

The scientific estimand is net R per session. The owner mandate now defines a
NAV-relative threshold:

`geometric_net_return_per_session >= 0.5%`

At the USD 1,000,000 reference NAV, the first-session path equivalent is USD
5,000. If the exact target path is achieved, the final session starts near USD
3,496,886.21 and its path equivalent is approximately USD 17,484.43.

Conversion therefore requires both the fixed dollar-risk budget `B` and the
NAV path:

`theta_econ_r_per_session(t) = 0.005 * NAV(t) / B`

Illustrative first-session translations, not approved risk settings:

| Fixed risk per trade | Percent of USD 1M | First-session target R |
|---:|---:|---:|
| USD 300 | 0.03% | 16.667R |
| USD 500 | 0.05% | 10.000R |
| USD 1,000 | 0.10% | 5.000R |
| USD 2,000 | 0.20% | 2.500R |
| USD 2,500 | 0.25% | 2.000R |

This table exposes the central Stage 0 trade-off. Increasing `B` makes the
economic target smaller in R units but consumes the 8% drawdown budget faster.
Keeping `B` fixed while NAV compounds also makes the required R/session grow
through the year. Stage 0 must test that non-stationary requirement explicitly;
it cannot use the first-session USD 5,000 as a constant annual threshold.
The six-hands review must select `B`, session breakers and committee breakers
together. No row is a recommendation and none changes production.

## Additional Capex rule

The USD 3,000 figure is a baseline, not a blind ceiling. A proposal above it
must state before purchase:

1. the incremental capability or quantified risk reduction;
2. the expected effect on data quality, power, execution or economic result;
3. the least expensive credible alternative;
4. the break-even condition; and
5. the objective failure/cancellation gate.

The owner then decides. A claim that a more expensive source is simply
"better" is insufficient.

## Next calculation

After fixed dollar risk is jointly frozen, Stage 0 runs the preliminary joint
`theta/N/alpha` feasibility analysis over burned data. The report must show
honestly if the 0.5% geometric daily target and 8% drawdown limit cannot coexist
with adequate statistical power in the planned horizon.
