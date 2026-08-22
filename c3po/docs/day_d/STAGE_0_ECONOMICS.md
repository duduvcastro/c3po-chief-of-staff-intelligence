# Day D Stage 0 economics

Status: **owner inputs recorded; R-normalized threshold pending**  
Source: [`economic_mandate.json`](economic_mandate.json)

## Owner mandate

- Reference capital: USD 1,000,000.
- Twelve-month net-return target: 100%.
- Twelve-month net-profit target: USD 1,000,000.
- Maximum drawdown: 8% peak-to-trough, without calendar reset.
- Recurring data/infrastructure budget: at most USD 1,000 per month.
- Baseline new Capex: USD 3,000.
- Capex above USD 3,000 is possible only after an incremental investment memo
  and explicit owner approval.

Existing purchases are sunk costs and do not count as new Capex. Any existing
subscription that continues during the experiment does count toward the USD
1,000 monthly forward-cost ceiling.

## Preliminary translation

Using 252 sessions only as a planning assumption:

- maximum planned forward cost in year one: USD 15,000;
- gross trading contribution required to leave USD 1,000,000 net:
  USD 1,015,000;
- simple average gross contribution required: USD 4,027.78 per session;
- compounded net return required: approximately 0.2754% per session; and
- return-to-drawdown target: 12.5.

The final session count comes from the exchange calendar starting on the first
unburned session after the hashed pre-registration. Actual spend replaces the
maximum budget in the final NPV, but feasibility uses the maximum to avoid
making the target easier by silently assuming that approved capacity is free.

## Why `theta_econ` is not yet an R value

The scientific estimand is net R per session. The owner mandate currently
defines a dollar threshold:

`theta_econ_usd_per_session ~= USD 4,027.78`

Conversion requires the fixed dollar-risk budget `B`:

`theta_econ_r_per_session = theta_econ_usd_per_session / B`

Illustrative translations, not approved risk settings:

| Fixed risk per trade | Percent of USD 1M | Required gross R/session |
|---:|---:|---:|
| USD 300 | 0.03% | 13.426R |
| USD 500 | 0.05% | 8.056R |
| USD 1,000 | 0.10% | 4.028R |
| USD 2,000 | 0.20% | 2.014R |
| USD 2,500 | 0.25% | 1.611R |

This table exposes the central Stage 0 trade-off. Increasing `B` makes the
economic target smaller in R units but consumes the 8% drawdown budget faster.
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
honestly if the 100% target and 8% drawdown limit cannot coexist with adequate
statistical power in the planned horizon.
