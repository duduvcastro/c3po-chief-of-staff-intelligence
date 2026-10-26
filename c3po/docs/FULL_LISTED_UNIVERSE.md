# Official inventory for Dark Side and Last Jedi

Human authorization: 26 October 2026, coordinated and reviewed by Fable in #429.
The foundation and second increment provide an inventory/read model, an opt-in
resumable canonical producer stage and a restrictive Decisor consumer. They do
not claim completion of production rollout or permission to deploy.

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
- The API copies real `official_rows` and applies the canonical `item_stamp`
  adapter, preserving the TP and immutable row without confusing `generation_id`
  with its API spelling `official_generation_id`. A real in-memory Database
  regression covers this integration; the foundation alone lacked that stamp.
- A buy permission requires a guarded Decisor decision, a current population for
  the same market and source version, and a trusted verifier's artifact attestation.
  A declared PASS and correctly shaped report/PREREG hashes alone are insufficient.
  No real verifier or population is installed by this change. The default is to
  deny buying, including structurally valid PASS members. FAIL, VOID, missing or
  expired evidence, a changed digest or an outside name cannot grant permission.

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

## Resumable canonical producer stage

`python -m app.listed_universe_worker --catalogue <manifest.json> --checkpoint
<private-directory> --policy <operator-policy.json>` defaults to a plan without
provider reads or checkpoint/database writes. `--run` explicitly enables input
collection and canonical valuation; `--stage-records` additionally appends the
completed cohort's canonical prediction records to `full_universe_stage`.

The policy must provide an aware `deadline`, an explicit quota `window`, allocated
provider `limits` and a `rate_card` mapping host/path prefixes to provider billing
units. There are no guessed quota defaults. A quota reservation is durable before
each HTTP request; uncertain or failed reads still consume it. A 403/429 persists
a hold. Bounded per-name retries, `--max-batches` and the collection deadline stop
the run without relabelling unread names as missing data. A new quota window is
an explicit operator input. Limits are allocations for one checkpoint: concurrent
markets must receive disjoint account-budget allocations after shared-worker use
is measured; this ledger does not claim to enforce an account-wide quota.

Every non-ETF inventory identity receives an outcome. Missing inputs, bounded
failures and pending classifications are retained with reasons. Provider aliases
must use the market's suffix, be explicitly supplied for punctuation share classes
and remain bijective against the complete inventory, including implicit aliases.
The code does not guess that `BRK.B` means a different provider identity.

Inputs are cached separately per name and verified on resume. Context is built
once over the complete collected market, so batch boundaries do not change peer
medians. The adapter calls the existing `USScreeningService._analyze_stock` and
`OnePagerService._analyze(role="producer")`, or B3 `_prepare_rows` with operational
minimum screening disabled and existing input/quality checks retained. Brapi's
legacy quote fallback and the canonical adjusted-close EODHD history fallback are
preserved. B3 issuer-consensus reconciliation uses the full collected reference
cohort. Cached context pins calibration and B3 IR/insider reads and valuation cut.

The run identity includes hashes of every application Python source, an
irreversible Settings fingerprint and the effective CVM overlay policy. No raw
settings or credentials enter receipts. A different code/policy/catalogue cannot
resume the same run. Checkpoint and artifact files are private, locked, hashed and
atomically synced. Cached contexts also work after starting a fresh process.

The stage uses a real snapshot foreign key and `prediction_from_row` for both
canonical sources. Its publication clock is the first actual snapshot insert;
retries reuse a confirmed insert, never a clock reserved before a failed insert.
It does **not** save `valuation_universe`, call generation activation or change a
served TP. API reads continue to use only the selected canonical generation.
Promotion of a complete expanded generation and scheduling remain release work.

## Restrictive Decisor consumer

`python -m app.listed_universe_decision` runs the original shadow Decisor over
the actual selected canonical generation through a read-only adapter. Its insert
is captured in memory, never written to the original decision table. `--record`
explicitly stores only separate `full_universe_decisions` snapshots; default is
dry capture. The adapter neither selects a stage nor operates a money path.

Each original record stays intact and hashed. The additional population gate can
only restrict its verdict. The API rechecks the decision session, canonical TP,
source version, causal scope, digest, membership and expiry before displaying a
permission. Stored attestations/JSON flags are insufficient: every permission read
must invoke a trusted server-injected verifier again. Such a verifier must check
the actual report/PREREG artifact bytes and pins and return the explicit binding
contract; none is implemented, configured or exposed as a CLI flag here. Synthetic
test verifiers are not scientific evidence and never install a real scope.

The backend Dockerfile copies `backend/app` into the image, including these new
modules. Frozen scientific `PACKAGE_FILES` needs no deployment-list change and is
unchanged. No worker activation, schedule or production promotion has occurred.

## Remaining work before full-universe release

1. Review exact instrument scope with Fable, especially B3 depositary receipts,
   funds, ETF receipts and unknown specifications. Preserve their inventory audit;
   never silently classify an unknown security as a buy-eligible stock.
2. Review and measure the opt-in complete producer on a permitted operational
   window, then review explicit publication/scheduling of a complete expanded
   generation. Staging is implemented; production promotion is not. No absent TP
   is fabricated and local synthetic tests do not attest a live complete build.
3. Keep buying denied until an explicitly reviewed verifier has checked the
   scientific artifacts and installed a valid evidence-backed population. The
   current PIT FAIL cannot be turned into a buy scope by a JSON declaration.
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
