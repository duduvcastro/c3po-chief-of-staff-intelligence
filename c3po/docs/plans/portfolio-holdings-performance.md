# My Portfolio: holdings and performance

Status: implementation prepared for review; no production changes.

Owner confirmed total acquisition cost (not average cost), current day/month/year plus closed months/years, and entry of prior purchases/sales.

## Confirmed scope

- Each existing security gets a holding editor below its quote: quantity and acquisition cost in its own currency; support fractional shares.
- Persist holdings on the server under the existing portfolio access rules. Quote refresh must never reset an unsaved form.
- Each row shows position value, acquisition basis, unrealized P/L amount and percentage in its native currency.
- A box above the rows shows consolidated position value, acquisition basis and summed unrealized P/L in USD. Convert BRL only in this box, using a positive, timestamped BRL-per-USD rate and division. Show FX source/time and incomplete coverage; never silently treat a missing quote/rate as zero.
- Day performance and closed month/year performance require a separate historical valuation and holdings record. Current holding quantities must not be applied retroactively to fabricate historical personal returns.
- Arithmetic uses decimal amounts; percentages are weighted by value, never a mean of security percentages. Missing cost differs from zero cost; zero basis has no defined return percentage.
- Unrealized P/L excludes sold-position realized results, dividends and fees unless separately recorded. The UI must label the actual measure.

## Implemented behavior

Position entries are dated absolute balances, not inferred purchases. A correction inside a period makes that period unavailable unless replaced with the actual transactions. Buy/sell events reconstruct quantities and weighted-average basis; fees are included; split factors preserve total basis; dividends are entered explicitly. UUID requests are idempotent, conflicting retries fail, and cancellations keep a tombstone. PostgreSQL writes serialize and replay the whole ledger before committing, including backdated changes. Watchlist deletion does not erase economic history.

The account refreshes every 60 seconds while the page is visible; a calculation timestamp is shown. Quote rows retain their existing faster cadence. Inputs preserve unsaved drafts. Only the owner may write or cancel records, even if a member has ordinary delete capability. The historical reconstruction works from recorded events and provider daily bars, without requiring the browser to be open at market close; no new worker or timer is installed.

The migration is `050_portfolio_ledger.sql`, not applied in production. Tests cover the in-memory mirror and HTTP boundary; a real PostgreSQL migration/readback remains a deployment gate.

## Performance methodology

The tracked portfolio is a securities-only sleeve; no implicit retained cash balance. Purchase gross cost plus fees is an external inflow, sale net proceeds and net dividends are external outflows. Period profit = closing market value minus opening market value minus net flows, converted using FX at each boundary/flow date. Unrealized consolidated profit instead equals the sum of native unrealized profits converted at current FX; it is not cumulative realized USD profit or tax P/L.

Percentages use Modified Dietz: profit divided by opening value plus day-weighted flows. Flows are assumed at end of day. This is an estimate (especially for large flows); a nonpositive denominator has no percentage. No claim of exact time-weighted or GIPS-compliant performance is made. A first recorded purchase establishes inception from zero; a dated position balance does not establish earlier history. Full results depend on complete user-entered transactions and corporate actions.

References:
- https://www.gipsstandards.org/standards/gips-standards-for-firms/gips-standards-handbook-for-firms/
- https://eodhd.com/financial-apis/api-for-historical-data-and-volumes

Historical OHLC uses raw close (neither split nor dividend adjusted), consistent with explicitly entered split/dividend events. Expected session closes come from the relevant exchange calendar; missing exact expected closes return N/D. FX uses the last prior observation, at most four days old. Current FX must be at most 30 minutes old while FX is open, or 72 hours over the weekend, with no future timestamps. Unconfigured watchlist securities are listed explicitly as excluded from the subtotal.

## Repository integration located

- app/database.py: realtime_portfolio persists watchlist metadata only; no holdings/cost fields.
- app/market_data/realtime.py: portfolio_snapshot builds quoted rows, with reference validation and stale handling.
- app/schemas.py: RealtimePortfolioItem/Response; additive holding and aggregate types needed.
- app/main.py: portfolio routes; use existing authentication and edit capability checks.
- frontend/app/page.tsx: MyRealtimePortfolio owns the watchlist editor and rows.
- frontend/app/globals.css: responsive portfolio grid.
- db: next migration number must be reconciled with main before submission; do not apply schema changes during D18.

## Historical correctness requirements

Persist holding changes with effective dates, preserving removed holdings in history. Capture closing prices and dated FX without depending on the browser remaining open. Separate transfers/purchases/sales from market return. A baseline supplied today cannot prove prior-month or prior-year portfolio performance. Missing historical coverage must remain unavailable with an explanation, not a fabricated zero. Calendar-period results require both boundaries and complete flow/holding information; incomplete onboarding periods are labelled explicitly.

## Required verification

- Fractional quantity, zero/missing basis, zero position, invalid/negative/nonfinite inputs.
- Mixed USD/BRL portfolio: quote values stay native, consolidated conversion direction correct; portfolio percent value-weighted.
- Missing/stale asset or FX cannot silently inflate/deflate a supposedly complete total.
- Add/edit/remove and concurrent edits persist consistently; repeated writes do not duplicate events.
- Read-only profiles cannot edit holdings; authorized editor can; CSRF/session rules preserved.
- Quote polling does not overwrite drafts; save/error feedback and mobile layout.
- Cash flow alone does not count as gain, closed-period boundaries and no retroactive current-quantity reconstruction.

Separate branch codex/portfolio-holdings-performance-20260917 from main 1bb009c3. Independent of #413. Fable review and a deployment window preserving D18 required before production.
