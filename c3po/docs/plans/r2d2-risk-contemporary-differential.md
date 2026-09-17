# Contemporary same-input risk differential — offline harness

Fable's replacement for a historical 20-name counterexample is a contemporary
comparison on the first at most 20 US names in the registered D14 causal order.
This harness makes no API requests and opens no real database. Real acquisition
and independent provenance review remain separate. Synthetic tests below do not
stand in for the approved contemporary capture.

`compare_contemporary_sample(sample_bytes, sample_sha256, bundles,
origin_sources)` takes exact preregistration bytes, their hash, an ordered mapping
of symbol to `build_risk_bundle` arguments, and the six original module files as
bytes. Sample schema is `RISK_DIFFERENTIAL_SAMPLE_V1`, with namespace
`R2D2-V2-DIAG-ENSAIO-2026-09-14`, date `2026-09-14`, the registered list hash
`eba757a4953c20d1b25e56c9006265a82c16acbaa1a37d297715d7508a20acb1`, receipt hash
`a47f8d333d9ff15a9a03eafb6289162cf320a808dc4a46e65f63047f9cd5f299`, ordered
`symbols`, factual `selected_at`, and `source_envelope_sha256`. Each provider
request must start on or after the registered selection. The acquisition launcher
must verify the original D14 envelope and first-US selection against the registry;
this harness binds that selection document without independently fetching its
source envelope.

## Independent oracle

The candidate executes `build_risk_bundle`. The oracle separately executes:

1. Original EODHD fundamentals normalization, foreign-listing FX and official
   overlay, directly through their implementation methods (not the candidate's
   prepared values).
2. Original `FmpClient.institutional_positions` and `recent_grades`, with an
   injected in-memory HTTP adapter returning the exact captured response bytes.
   Unexpected requests cannot reach a network and prevent acceptance even when
   the legacy FMP helper would otherwise swallow its exception.
3. Original `Database.save_ir_events` and `insider_transaction_activity` on an
   isolated `Database(Settings(database_url=''))`. Events are seeded through the
   real save path, never by directly assigning `_ir_events`; source/external-ID
   deduplication and the actual origin transaction-direction method therefore run.
4. Actual `OnePagerService._analyze(..., role='producer', shared_valuation=None)`.

All six supplied original module files are checked against bytes pinned to
`6083d742`. FMP, FX and official-overlay runtime files must be byte-identical to
that origin. The relevant database and EODHD methods must have identical ASTs to
origin methods, while complete current file hashes are also recorded. The
OnePager runtime oracle is separately pinned to `1bb009c3` and its file hash;
ORIGIN and ORACLE are never conflated.

The non-FX oracle supplies a labelled auxiliary price of 1.0 because `_analyze`
requires a positive price even though this canonical risk score does not depend
on it. This is a test control, not a market quote. An invariance test compares
risk under prices 0.01 and 10,000. Foreign-listing cases instead require the
actual FX quote and rate already present in the same evidence bundle; their
normalization is not tested with the auxiliary price.

## Acceptance and private report

- At least **10 READY** names, every READY score **exactly equal**, and **zero
  unclassified exceptions** are necessary for mathematical `PASS`.
- Fewer than 10 READY gives `INCONCLUSIVE`, including all-null samples.
- Any READY mismatch or unclassified exception gives `NO_GO`.
- Completed-null assessments retain their diagnostics per component together
  with the legacy oracle score; permissive legacy defaults never create READY.
- Explicit candidate refusal codes are counted separately; arbitrary exceptions,
  including exceptions from the oracle, are unclassified and never printed with
  their raw message.

The full report is private: it contains names, inputs and normalized provider
values. Publish only `aggregate`, the private report hash and source-pin hashes.
`historical_proof`, `capture_provenance_independently_verified`, and
`production_authorized` remain false: a same-input arithmetic PASS neither proves
historical coverage nor authorizes a deployment or operational session.

## Gate rev 2 (Fable disposition 5718883179)

The original ten-READY gate remains in `aggregate.status` for audit continuity.
A separate `arithmetic_gate_rev2` checks exact equality on all twenty normalized
inputs, including None, regardless of coverage. This diagnostic kernel score
is never substituted into risk.json when the adapter returns COMPLETED_NULL.
PASS arithmetic is not coverage authorization, a release seal or operational GO.

## Independent direct-insider oracle after RC-4bis

The harness now accepts `DIRECT_INSIDER_RC4BIS_V1` private snapshots. The separate
`r2d2_v2_risk_direct_oracle` module imports no candidate acquisition, coverage or
event-builder helper. It independently reconstructs Finnhub's window tree using
an iterative stack; saturated parent pages contribute no transactions. It checks
complete child coverage and excludes any unexpected receipts. Leaf rows pass
through the **original** `FinnhubClient._normalize_transaction`.

Only a fully verified empty Finnhub response selects EODHD. EODHD pages undergo
independent receipt, identity, pagination and termination checks, and transactions
pass through the original `EodhdClient._normalize_form4_row`. Simultaneous usable
Finnhub and EODHD data is refused rather than summed. Missing/incomplete coverage
returns a distinct UNKNOWN diagnostic; verified zero remains distinguishable.

Actual `InvestorRelationsService._finnhub_insider_events` or
`_eodhd_insider_events` runs against a recorded transaction stub. A **local copy**
of that function's globals binds its clock to the factual query cutoff and its
lookback to the explicitly approved 180 days. The application module's clock and
90-day default are never patched, including during concurrent tests. The origin
IR method supplies its actual external-ID/name/code/date semantics. The original
in-memory `save_ir_events` then performs real source/external-ID upserts before
the original insider-count query. No production DB ingestion occurs.

Source evidence expands from six to **eight original modules**: Finnhub client
and investor-relations source bytes at `6083d742` are pinned too. Runtime ASTs of
Finnhub normalization, both IR event methods, `clean_text`, `safe_date`, and the
EODHD Form 4 normalizer must equal their original counterparts. The source/oracle
pins remain separate. The arithmetic gate revision added by the root coordinator
is unchanged by this integration.

Additional synthetic tests use manually expected buy/sell counts for duplicate
identities, lookback filtering, saturated-parent exclusion, EODHD precedence,
no-provider-union, verified empty versus missing fallback, and isolation of the
injected clock/window. These tests are not the real 20-name capture.

## Owner-authorized failure fallback, RC-4bis revision 3

The original V1 snapshot shape remains supported. Failure fallback is opt-in,
requiring both normative-contract hash
`b569610f24639c5ba54841f2003dceb864331f9d2138fc0f9c31de4949601c63` and Fable disposition
`b7a80c08cc600bc1314b49966816575e650e86f8daf6fe801705c31c8ae627be`, plus the recorded
provider selection. Without that binding, a Finnhub failure continues to yield
UNKNOWN rather than enabling fallback. Gates and old report files are unchanged.

The independent oracle distinguishes a recorded provider failure from damaged
provenance. HTTP/transport failure, bad response shape, out-of-window/future
records, a saturated single day, or an exhausted registered request budget may
select EODHD under the new contract. A missing attempt, wrong request, altered
hash/clock, unproven error diagnostic, missing non-budget tree receipts or extra
receipts after failure cannot do so. All supplied receipt integrity is checked
before choosing a provider. Partial Finnhub events are discarded completely when
EODHD is selected. A nonempty complete Finnhub population is never unioned with
EODHD.

EODHD must independently pass status/hash/identity/clock checks, exact page
binding, stable integer `meta.total`, matching `meta.page.offset`/`limit`, unique
nonempty `accession_number` identifiers, valid dates, and final received filing
count equal to `meta.total`. `next=null` by itself is insufficient. A gap such as
559 received filings against total 560 remains UNKNOWN; a short page whose next
offset skips a filing remains UNKNOWN. Future transactions in EODHD remain
UNKNOWN even when Finnhub failed. Fallback repairs provider availability only,
not invalid fallback data or damaged evidence.

Synthetic adversarial tests cover failure fallback, day saturation, partial
primary exclusion, old-contract refusal, tampered provenance, incorrect totals,
page offsets, duplicate/missing accessions, future fallback data, and unproven
JSON-failure assertions. The real-sample arithmetic and coverage gates are not
changed by these tests.
