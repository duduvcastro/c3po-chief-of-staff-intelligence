# Day D Stage 0 economics

Status: **economic and risk contract frozen for paper research**

Source: [`economic_mandate.json`](economic_mandate.json)

## Owner mandate

- Reference virtual capital: USD 1,000,000.
- Trading capital: entirely virtual for the first 12 months; no real trading
  capital is exposed during the research horizon.
- Net-return target: 0.5% geometric mean across every preregistered exchange
  session, compounded on current virtual NAV and measured over the complete
  horizon. A no-trade session counts as 0%; negative and no-trade sessions
  cannot be removed from the denominator.
- The target is not a mandatory daily quota. The system must never manufacture
  trades, weaken gates or increase risk merely to reach 0.5% on a particular
  day.
- Maximum drawdown: 8% peak-to-trough on consolidated daily NAV, without a
  calendar reset.
- Recurring data/infrastructure budget: at most USD 1,000 per month.
- Baseline new Capex: USD 3,000. A higher amount requires an incremental case
  and explicit owner approval.

Existing purchases are sunk costs and do not count as new Capex. Existing
subscriptions that continue during the experiment count toward the USD 1,000
monthly forward-cost ceiling. Capex and Opex are real product investments in a
separate project-economics ledger; the trading portfolio remains virtual.

The 0.5% target may be lowered later only through a prospective, versioned
owner decision. Historical results remain judged against the mandate active
when they were generated.

## Frozen risk contract

Every new trade receives an initial risk budget equal to **0.15% of current
virtual NAV at entry**. At the USD 1,000,000 reference NAV this is USD 1,500.
There is no fixed dollar cap during paper research. Once assigned, that dollar
`1R` denominator remains fixed for the lifetime of the trade so its outcome is
auditable even as portfolio NAV changes.

The book may hold at most five simultaneous positions. The maximum aggregate
initial stop risk is therefore 0.75% of current NAV, or USD 7,500 at the
reference NAV. Approximately 53.33 individual full-R losses, or 10.67 sessions
where all five positions lose a full R, consume the 8% drawdown allowance.
Actual path risk and breakers are calibrated in Stage 2. Risk must be
recalibrated before any real capital is considered.

## Two different thresholds

The product ambition and the economic kill threshold are deliberately
separate.

### `theta_meta`: product target, no kill authority

Because both target and risk scale with current NAV:

`theta_meta = 0.005 / 0.0015 = 3.333333R per session`

This is stationary in R units. It remains an ambitious product target and can
never force trading, weaken a gate or kill an arm at C1/C2. At roughly four
closed trades per session it would require about 0.83R net expectancy per
trade, so failure to reach it at an interim checkpoint is not itself a
statistical rejection.

### `theta_kill`: binding economic floor

The frozen economic floor is **0.15R per session**, binding at C1/C2 under the
optimistic cost model. Its planning decomposition at initial NAV is:

- operating costs: `(USD 15,000 / 252) / USD 1,500 = 0.0396825R/session`;
- opportunity-cost budget: `0.15R - 0.0396825R = 0.1103175R/session`;
- benchmark: the US 3-month Treasury bill.

The benchmark rate itself is snapshotted and frozen on the final
preregistration hash date. The current planning translation of the rounded
opportunity component is 4.17% annualized. It is not represented as a live
market quote. Later benchmark changes require a prospective, versioned
amendment; the frozen 0.15R total is not silently rewritten.

## Closed-trade quality

Every trade has two outcome classifications:

1. **Exact ledger sign:** positive, negative or exactly flat from realized net
   P&L after entry and exit slippage and fees. No epsilon is applied.
2. **Robust classification:** win, loss or tie after applying
   `epsilon_trade = max(exit half-spread * quantity, USD 0.01 * quantity)`.
   This epsilon represents fill-measurement uncertainty, not round-trip cost.

Robust ties are reported separately and excluded from the robust win-rate
denominator. The session-block-bootstrap lower confidence bound for robust win
rate must be strictly greater than 50% only at the final 12-month verdict. C1
and C2 values are diagnostic. Exact ledger counts remain visible throughout.

Payoff ratio 1.3-1.5 and profit factor at least 1.5 are desired product ranges,
reported with confidence intervals at C1, C2 and the final verdict. They are
not binding gates. Expectancy, geometric return, robust win rate and drawdown
retain their own meanings.

## Planning translation

Using 252 sessions only as a planning assumption:

- maximum planned forward cost in year one: USD 15,000;
- target terminal virtual NAV: approximately USD 3,514,370.64;
- target virtual trading profit: approximately USD 2,514,370.64;
- implied 252-session net return: approximately 251.44%; and
- separate project-economic surplus after maximum forward costs:
  approximately USD 2,499,370.64.

These figures describe the path implied by the product target. They are not
daily quotas and do not authorize forced trading.

## Remaining statistical gate

Stage 2 must validate, by path simulation, that the combined
futility + damage + placebo rule kills the zero-edge setup class in at least
80% of worlds. An arm survives only if all three blades pass; placebo requires
`p <= 0.05` and `delta >= 0.10R`. The analytic independence approximation is
useful for review but is not binding because arm dependence and carry must be
modeled from frozen replay data.
