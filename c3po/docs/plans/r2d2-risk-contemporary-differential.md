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
