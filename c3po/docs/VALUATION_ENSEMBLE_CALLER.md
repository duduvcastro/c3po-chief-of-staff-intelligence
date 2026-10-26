# Explicit shadow caller and factual input inventory

`run_from_canonical_readers(statement_store, price_reader, database, requests, premises,
store)` is the callable entry for an application that already owns those reader handles.
It constructs no client/database, opens no connection and calls no refresh, collection,
backfill, valuation-table writer, schedule or served-source selector. Importing it performs
none of those actions. Its sole writer is the explicitly supplied private receipt sink.
There is no production scheduling or connection enabled by this increment.

The caller evaluates one explicitly requested cross-section at one T. Different T values
are rejected: this is not a grid, return-label computation or study report. It adapts each
requested company once, uses the same requested cross-section as the candidate peer pool,
then applies the existing kernel checks. Failed company adaptations remain in every model's
denominator. No company is silently replaced, filled or dropped to make coverage look better.

Each immutable company receipt includes its original adapter provenance, construction
results, all required field/design-premise availability, kernel refusals, and independent
historical-admissibility gates. The cross-section receipt references those objects and
counts actual computability, missing/ineligible inputs, missing design assumptions and
blocking proofs for all sixteen models. A field marked available here has passed the
source/unit/time/finite-number check; model-specific economic constraints are still applied
by its kernel and recorded separately. A later price refusal does not erase already
validated facts. A fact stage that was not reached is counted separately as `not_observed`,
never as proof that the required facts are missing. Actual source-adaptation refusal
reasons remain visible alongside model computability. This inventory describes only the requested inputs.
Offline fixture results do not attest real historical coverage.

## The gates that remain closed

Computable arithmetic is not an admissible historical observation. Both this caller and
the earlier one-company execution receipt expose an explicit `not_admissible` result.
No CLI flag can waive it. All model/variant admissible counts remain zero because the
available canonical reader contracts lack the following proofs:

| Required proof | Existing contract | Concrete missing evidence |
| --- | --- | --- |
| Original-document authentication | `statement_vintages.py` persists document metadata and header hash; `sec_xbrl.py` returns parsed header fields | Original SEC header/CVM archive bytes and authenticated retrieval provenance are not exposed by these readers |
| Historical symbol, issuer and class mapping | `statement_filings.symbols` is a detection-time association; SEC polling attaches the supplied current ticker map to old documents | Official instrument identity with actual historical validity, availability and original-document linkage |
| Per-share allocation | SEC companyfacts processing sums differing DEI share counts across classes; CVM retains ordinary/preferred/total counts | Symbol-to-class or units allocation, rights, denominator scope and consistent issuer/equity attribution |
| Corporate-action basis | Price rows bind symbol/session/close/adjusted-close/hash and capture/publication | Official action identity, terms, effective/availability clocks and an evidenced interval that reconciles statement shares and the quoted instrument |
| Official historical classification | No sector/SIC/classification field in the canonical filing/fact projection | Official historical classification and a reviewed model-applicability taxonomy |

The SEC acceptance clock proves filing availability, not historical ticker validity.
Likewise, a self-computed hash, current provider profile, ticker suffix, adjusted-close
ratio or default Industrials classification cannot supply these missing proofs. Existing
sector/display heuristics are not imported. A future evidence adapter must bind original
official content to the issuer/instrument, source identity, availability and applicable
interval, reject ambiguity, and preserve later capture as a separate clock. No arbitrary
`SEC`/`CVM` source label or caller-created status boolean is accepted as that adapter.

This increment deliberately records that contract as pending rather than creating an
unverifiable attestation interface. It advances the caller and factual audit while real
source/original coverage is coordinated with Fable. It does not claim all models are ready
for a study. Normalization, maintenance-capex choices and genuinely eligible consensus/
price coverage also remain explicit dependencies, without new feeds or rate assumptions.

## Offline entry point

`python -m app.valuation_ensemble_caller` requires `--source-export`, `--requests`,
`--premises` and `--receipt-directory`. The requests object has exactly schema
`VALUATION-ENSEMBLE-CROSS-SECTION-REQUEST-v1` and a `requests` list. Each item has exactly
`market`, `symbol`, zoned `as_of` and the declared `basis_id`. Duplicate instruments,
different T values, extra study inputs or an attempt to waive admissibility are refused.
The existing private, atomic, idempotent sink is reused. Company inputs stay private;
stdout contains hashes, aggregate counts/status and no instrument names or local paths.

No horizon is selected. The owner's separate PREREG signature/horizon on 29 October,
grade no earlier than 30 October, Fable review and the unchanged served source remain
required. There is no live money operation or deployment during PIT grid chunks.
