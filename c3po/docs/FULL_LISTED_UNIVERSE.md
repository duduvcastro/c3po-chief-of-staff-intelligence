# Official inventory for Dark Side and Last Jedi

Human authorization: 26 October 2026, coordinated and reviewed by Fable in #429.
This first increment is an inventory/read-model foundation. It does not claim
completion of the full valuation rollout or permission to deploy.

## Behavior in this increment

- Parse the complete official Nasdaq Trader directories and B3 daily Títulos
  Negociáveis file. Require completion footer/trailer and preserve source URL,
  source date, receipt time, raw SHA256, manifest SHA256 and reconciliation counts.
- Keep every in-scope listing, including a name with no quote or canonical TP.
  Missing values remain null, with an explicit `not_evaluable` reason.
- Show price, market cap and liquidity minima as badges and optional UI filters.
  Their values do not remove inventory entries or replace a decisor gate.
- Expose the same read model under the existing candidates and matrix-power
  permission prefixes. Both new UI panels read the immutable canonical TP record;
  neither computes a separate TP or silently falls back to a capped vendor list.
- Pagination is a display convenience: every matching inventory row is reachable.
  There is no logical 300/350-name cap.
- ETF producer/selection code is untouched. Ambiguous non-ETF directory entries
  and B3 cash instruments with an unfamiliar specification remain visible as
  `listing_classification_pending`, with no buy permission. Company-name words
  such as "Bond" or an ADS's "right to receive" never exclude a listing.
  This matters because B3 `CI` includes ETFs and other funds; it is insufficient
  to infer an ETF/equity distinction from ticker suffix `11` or from `CI` alone.
- A buy-scope read model requires an existing decisor permission AND a separately
  recorded, unexpired PASS population for the same market and TP source version.
  No scope is installed by this change. FAIL, VOID, missing evidence, a changed
  population digest or an outside name cannot grant permission.

The existing Top 10 ranking and plotted legacy selection remain available. The
new inventory panel is additive while full production and capacity are reviewed.

## Official sources

- [Nasdaq Trader directory definitions](https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs)
  describe `nasdaqlisted.txt` and `otherlisted.txt`. NYSE is exchange `N`; Arca and
  American are not relabelled NYSE. File creation time is recorded by the parser.
- [B3 daily Títulos Negociáveis download and layout](https://bvmf.bmfbovespa.com.br/cias-listadas/Titulos-Negociaveis/BuscaTitulosNegociaveis.aspx?idioma=pt-br)
  provide the 220-byte company/security records, cash-market code, ISIN and trailer.

Current official inventories are prospective operational inputs. They are not a
substitute for a historical PIT listing universe and do not change a preregistered
research sample or consume a scientific look.

## Capture and storage

Parsing a supplied official file is the default; it writes no database record:

```sh
python -m app.listed_universe_capture --market NASDAQ --input nasdaqlisted.txt
python -m app.listed_universe_capture --market NYSE --input otherlisted.txt
python -m app.listed_universe_capture --market B3 --input Titulos_Negociaveis.zip
```

`--download` explicitly retrieves the fixed official origin. `--record` explicitly
records only the `official_listing_catalogue/<market>` analysis snapshot. It does
not refresh a producer, publish an official TP generation, install a buy scope,
enable a timer or dispatch a workflow. The new route performs reads only and
reports inventory unavailable until a manifest has been captured.

No production capture schedule has been installed or activated by this increment.

## Remaining work before full-universe release

1. Review exact instrument scope with Fable, especially B3 depositary receipts,
   funds, ETF receipts and unknown specifications. Preserve their inventory audit;
   never silently classify an unknown security as a buy-eligible stock.
2. Add the full-size producer orchestration using unchanged canonical methods in
   a separate runtime path. Remove operational screening exclusions there while
   leaving the 72 protected files and old research producer pins unchanged.
   This increment displays an unavailable canonical TP for a name not yet built;
   it does not fabricate a TP or claim that all names have been valued.
3. Wire the evidence-backed population restriction into any expanded production
   decisor consumer before publishing the larger canonical generation. The new
   read-model permission is deliberately restrictive, but it does not replace
   the frozen decisor implementation or its historical experiment.
4. Complete the factual capacity receipt below, including quota headroom shared
   with other workers. If a night cannot fit, obtain Fable's review of a rotation
   or two-part cycle that accounts for every name and its freshness.
5. Tests/PR by 27 October; Fable review before anything goes live. Planned deploy
   28 October only outside active PIT grid chunks. No real-money operation.

## Capacity receipt requirements

An official inventory count is not a capacity measurement. The checked-in
`full-listed-universe-capacity.pending.json` records what remains unmeasured.

- Provider plans: contracted EODHD/FMP/Finnhub request and billing-unit limits,
  per-second/minute/day constraints, other-worker use, headroom and measurement
  interval. Count requests and weighted quota separately.
- Night: market/phase duration, cache misses, retries/throttling, payload bytes,
  actual universe and distinct CIK counts, finish time relative to market hours.
- Host: CPU/steal/load, memory/RSS peaks, free memory, disk/DB growth and concurrent
  PIT work. Existing `server_usage` collects CPU/load/disk, not RAM/RSS.
- SEC: a poll reads submissions for every distinct mapped CIK. The backfill
  budget limits gap repair, not the submissions sweep. Measure sweep time plus
  header/companyfacts cost and freshness before proposing a new issuers-per-poll
  value. Keep the shared fair-access limiter and stop on throttling.

For orientation only, the current US nightly call graph performs approximately
`2*N` EODHD requests (fundamentals + histories) and `4*N` FMP requests when configured
(consensus, summary, institutional positions, grades), before retries or auxiliary
routes. These are call counts, not contracted billing costs. For `U=6000` distinct
CIKs at the code's default `2.5/s`, submissions alone require at least 40 minutes;
at the code ceiling `8/s`, at least 12.5 minutes. Neither example attests the actual
configured rate, current quotas, live host resources or completion time.
