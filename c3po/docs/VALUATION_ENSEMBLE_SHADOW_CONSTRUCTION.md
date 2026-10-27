# Valuation ensemble: first construction increment

This is a pure shadow computation library for the owner's 26 October 2026 authorization.
It does not register a served source, persist records, fetch data, schedule a run, dispatch a
workflow, read returns, grant buy permission or select the study's decisory horizon. Fable
reviews the PR before release. The old producers and signed protocols remain unchanged.

The Fable roster contains sixteen fundamental models and one additional analyst-consensus
source. Each model returns a positive per-share value or `not_evaluable` with its actual
reason. No replacement number, live-provider fallback, default rate or default growth path
is supplied. SEC/CVM facts and price observations require document/publication identities,
hashes, units and clocks. These input hashes are *attestations supplied by an adapter*, not a
claim that this library has downloaded and verified the original filings. Official-data
adapters are described in the separate adapter document; historical coverage inventories
and live integration remain subsequent work.

## Formulas and inputs

| Model | Construction formula / explicit dependency |
| --- | --- |
| DCF FCFF | EBIT(1−tax) + D&A − capex − change in non-cash working capital; supplied growth path and terminal growth, discounted at WACC, less debt plus cash |
| DCF FCFE | OCF − capex + net borrowing; supplied growth path and terminal growth, discounted at cost of equity; no second net-debt deduction |
| DDM Gordon / multistage | Official annual dividends per share, supplied growth and cost of equity; a non-dividend payer is not evaluable |
| Residual income | Beginning book equity + capitalized annual income less the cost-of-equity charge on beginning book; supplied stable residual-income growth |
| Earnings power | Normalized EBIT after tax + D&A − maintenance capex, capitalized at WACC; net-debt bridge to equity |
| Capitalized OCF | OCF / cost of equity / shares; a standalone OCF capitalization, with no claim to be free cash flow |
| P/E, EV/EBITDA, EV/EBIT, EV/Sales, P/B, P/OCF | Median eligible peer multiple at the same T, currency and official sector; target excluded; same numerator/denominator bases |
| Sector regression | Leave-one-out sector OLS of log(EV/Sales) on EBIT margin, fitted only in the cross-section at T; singular fits and extrapolation refused |
| NCAV | (Current assets − total liabilities) / shares |
| Tangible book | (Book equity − goodwill − other intangibles *excluding goodwill*) / shares |

The packet must attest that the statements are on the share-class and corporate-action
basis identified by `basis_id`. TTM reduction, normalization, maintenance capex, official
sector mapping, class allocation and tax/rate/growth policy are not fabricated here. Missing
SEC/CVM concepts remain missing. Enterprise-value models refuse financial-company packets.
An upstream adapter must justify the `financial_company` classification.

Financial formulas follow the distinction between cash flows to equity and cash flows to
the firm described in [Aswath Damodaran's valuation notes](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/lectures/val.html).
The formulas and the sector-regression specification are construction choices for Fable's
review; this document is not the new PREREG and does not freeze the future experiment.

Prices and fiscal period ends are checked against T's market civil date, not merely its
UTC date. Peer votes are unique by official issuer identity, so another share class or
exchange listing cannot give the same issuer another vote or supply the target's own price.

## Consensus and six variants

Consensus is the arithmetic mean of the latest eligible target from each analyst house.
Every target must have a positive price, a matching currency, an attested positive horizon,
an availability instant no later than T and a source payload hash. Mixed horizons or
conflicting observations from the same house at the same instant refuse the consensus.
No twelve-month horizon or freshness window is invented. The source's horizon is separate
from the decisory horizon that the owner will choose on 29 October.

The three aggregates are mean, median and trimmed mean, each with and without consensus.
Consensus gets one source vote, equal to one model. The primary remains
`median_with_consensus`; when consensus is unavailable, the three variants bearing its name
are not evaluable. They do not silently become their counterparts without consensus.
The construction convention for the 20% trim removes `floor(n × 0.20)` observations from
**each** tail, recorded in every variant; fewer than five observations remove none.
These missingness, minimum-peer and trimming rules require review before the new protocol.

## Remaining delivery gates

Producer and relevant tests are due 28 October. The separate PREREG is due 29 October for
the owner's signature and horizon choice. The grade starts no earlier than 30 October,
after that signature, exact-head code review and operational readiness. Rates in this
increment are explicit model premises: no additional external rate feed is authorized by
the construction library. The served valuation remains unchanged through the verdict.
No deployment is allowed during PIT grade chunks, and no real money is involved.
