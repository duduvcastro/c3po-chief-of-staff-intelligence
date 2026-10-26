# Read-only source adapters and private shadow execution

The second construction increment adds adapters over the existing canonical store
interfaces, an offline export reader, and an explicit private receipt sink. It does not
fetch or backfill sources, migrate a database, change a source selector, use a rate feed,
read realized returns, schedule/dispatch a workflow, launch a grade or select a horizon.

## Canonical source contracts

`CanonicalSources(statement_store, price_reader, database)` calls only:

- `StatementVintageStore.filings` and `vintages`, with the official market/source and an
  `accepted_at_or_before=T` cut. The adapter rechecks that cut rather than trusting it blindly.
- `PriceHistoryService.series(..., available_before=T)`, which already verifies its
  publication/manifest/series chain. The adapter also rechecks bar identity, content hash,
  session closure, currency and capture/publication clocks.
- `Database.latest_analysis_snapshot` for the existing hashed-symbol FMP-target source
  key. Source payload hashes and market/symbol/provider identities must agree.

The existing canonical stores remain untouched. Their trusted source-ingestion boundary
still matters: a reproducible row hash does not independently authenticate the original
SEC header or a provider's historical claim. This increment verifies the stored content and
its declared source evidence; it does not redownload or recertify originals.

The diagnostic symbol-to-issuer association uses registry rows accepted by T rather than
the `symbol_issuers` shortcut. **This does not prove historical instrument identity:**
the collector attaches detection-time tickers from its supplied map to earlier filings.
A current ticker association can therefore be projected onto an older accepted document.
Neither the acceptance cut nor a header hash proves when that symbol represented that
issuer, class or unit. Original-document authentication and historical instrument/share/
corporate-action basis remain explicit blocking gates; the adapter's CompanyInputs is
only a construction packet and cannot become an admissible historical observation.
Conflicting registry entries or latest facts are refused deterministically.
SEC acceptance requires the header-based source and a header hash.
CVM acceptance requires the conservative end of its receipt date in São Paulo. A CVM
receipt date is never converted to an earlier intraday availability.

SEC facts map through a separate explicit concept ladder. CVM consolidated accounts use
the existing official-account predicates and conservative additional balance mappings;
individual accounts are not mixed into consolidated ones. Four contiguous quarters are
required for a trailing flow; year-to-date values are quarterized before summation. Missing
quarters are not bridged, absent debt components are not zero, ambiguous accounts are not
guessed, and missing treasury shares are not zero. Provenance keeps every contributing
document, canonical row hash, acceptance and known capture clock, plus the derivation rule.

## Two clocks and the new study

Regulator acceptance is evidence of when an official filing existed, even when its local
capture happened later. Both clocks remain visible in the private receipt.

Prices follow a **strict publication no later than T** rule in this increment. A price
vintage published in 2026 is refused for T in 2021 even if the bar's session is in 2021.
A purported publication before its capture is also refused without independent proof.
The old study's pinned-price exception and pins are not inherited. A future adapter/protocol
may admit genuine independently proven availability in T while keeping a later capture
clock; this implementation does not invent that proof or retrodate the capture.

Consensus is the explicit source exception to the official-statements-plus-price scope.
An old target's own zoned publication, currency, document identity and attested horizon
must be present. Its source snapshot may have been captured later; that capture is separate
metadata. Missing horizon/currency is a counted refusal, with no twelve-month default.
The analyst source horizon never becomes the owner's decisory horizon.

## Offline execution and immutable persistence

`BundleSources` accepts `VALUATION-ENSEMBLE-SOURCE-EXPORT-v1`, an offline export containing
the canonical `filings` and `facts`, reader outputs in `price_series` keyed `MARKET:SYMBOL`,
and optional `consensus_snapshots` under the same key. Canonical hashes must be retained.
It is an export of existing evidence, not a source refresh or synthetic historical coverage.

The entry point is `python -m app.valuation_ensemble_execution` with four explicit inputs:
`--source-export`, `--request`, `--premises` and `--receipt-directory`. The request contains
`market`, `symbol`, zoned `as_of`, the caller's declared `basis_id` and optional peer
requests. Study-horizon, grade and report inputs are refused. The CLI never opens a database
or network connection. It prints aggregate status and hashes; nominal inputs stay in the
private receipt. Fixture CLI tests exercise this entry point without production data.

`execute_shadow` also accepts `CanonicalSources` from a caller with an existing read-only
store/price reader. Connecting and scheduling such a caller is not done here.

`FileReceiptStore` writes only to an explicitly selected private directory, owned by the
user. It fsyncs a 0600 temporary object, links it atomically under a content-derived run
key, and fsyncs the directory. Concurrent identical executions create one object. A retry
verifies the existing object rather than rewriting it. Corruption, a changed payload under
an existing key, symlinks and public directories are refused. A later non-evaluable receipt
has its own key and cannot erase an earlier successful receipt. No production valuation
table receives these objects.

## Scope and remaining work

The only pure-layer contract change is that `financial_company=None` means *unattested*.
The adapters do not assume an industrial company when official sector classification is
missing: enterprise and peer models refuse that missing classification. Equity kernels
can still evaluate admissible official inputs. The prior independent GO on the earlier
pure-layer commit is not a review of this new increment.

The basis identifier remains an explicit caller assertion, not automatically proven
share-class allocation. Before historical use, the source/coverage work must establish
official sector and class mapping, consistent share/corporate-action bases, source-specific
missing concepts, normalization/maintenance-capex policy, and consensus horizon coverage.
This adapter does not fabricate those inputs. Many models may consequently remain
non-evaluable; `computed` means the construction ran, not that every model or the primary
is evaluable. Offline fixtures prove mechanics, not real historical coverage.

Production integration, coverage/capacity receipts, the Fable review, the separate PREREG
for the owner's 29 October signature/horizon, and the grade no earlier than 30 October
remain pending. The served source stays unchanged through the verdict. There is no live
money operation and no deployment during PIT grade chunks.
