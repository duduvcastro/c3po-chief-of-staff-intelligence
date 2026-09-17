# Risk bundle: path A, block 2

`app/r2d2_v2_risk_bundle.py` implements the owner-approved RC-1–5 preparation:
EODHD normalized fundamentals, explicit allowlisted foreign-listing FX bridge,
then the pure official snapshot overlay. The DB snapshot is injected; neither
acquisition, ingestion, DB mutation nor OnePager `generate` is invoked.

Historical origin is 6083d742. EODHD normalization, foreign-listing conversion,
official overlay and the OnePager preparation have the same applicable function
bodies at the current baseline; whole-file origin pins live in SOURCE_PINS.
The helper's nondeterministic `officialFundamentals.appliedAt` is discarded. It
is not a risk input or an evidentiary source clock. The calculation's clocks
are explicitly supplied factual instants and are preserved on replay.

`prepare_path_a` produces normalized fundamentals. `fundamental_candidates`
reproduces `_analyze`: positive beta; declared `abs(growth)>2` conversion;
first-four-row TTM with original fallback precedence; latest balance overrides;
negative EBITDA and negative FCF preserved. Candidate arithmetic can exist when
coverage does not: the risk adapter does not release a score unless all seven
inputs satisfy evidence guards.

`build_risk_bundle` consumes immutable SourceReceipt objects plus private DB
snapshots. `official_snapshot` has symbol, market and `outputs` (including null
for evidenced absence). `insider_snapshot` has symbol, market, events and a
factual `query_cutoff_at` from the DB transaction. Its `sync` contains source
`sync_sec`, symbol, complete, window_start, window_end, completed_at. The 180-day
window ends at the query cutoff, reproducing the original `now` at DB lookup;
it does not slide forward when the same snapshot is scored or read later.
Missing cutoff or incomplete sync coverage returns COMPLETED_NULL. Form 4 is
not used as a replacement for persisted Finnhub/ingestion events.

Seven inputs retain independent evidence. Beta source date is General.UpdatedAt;
growth retains that payload update date (explicit, pending source-date review).
Debt/EBITDA and FCF need four complete, distinct dated quarterly rows with
compatible currency; source date is the latest contributing quarter/balance.
No new freshness TTL or assumed calendar length per quarter is introduced.
Institutional requires a nonempty HTTP-200 response for the canonical quarter
and an explicit row date. Empty is UNKNOWN. Grades HTTP-200 requires nonempty FMP rows with matching symbol identity;
EODHD identity never proves FMP population coverage. The FMP population is
evaluated over 90 days and deduplicated by date/firm/action. Its source date is the newest eligible grade. For empty grades coverage is UNKNOWN and the
contract has no defined source_at: this implementation returns null, never
substitutes an HTTP receipt timestamp. B3 and nonpositive beta remain null.

FX receipts bind symbol, fx_symbol, fx_rate, quote_price, source_at and read
instant to the values supplied. Every private calculation records payload
hashes, overlay presence/application, FX policy and growth conversion. HTTP200
or caller attestations do not independently prove population completeness;
`independently_verified` and `production_connected` remain false.

Validation: numerical differential tests invoke the actual `_analyze` oracle,
including negative EBITDA, ratio boundaries and FCF signs. Other tests cover
seven separate missing-coverage cases, overlay effects, missing insider cutoff,
90-day partial insider coverage, nonpositive beta, tampered bytes and replay.
The historical 20-name input corpus and host executor are separate deliverables;
these synthetic tests are not a historical or live attestation.

Final review additions: institutional quarter and the grades 90-day window use
the factual request `started_at`, never a later decision timestamp. Their cutoffs
are recorded in path_a and replay boundary tests retain the original population.
For an applied official overlay, outer `source_at` and `available_at` are required
factual provenance from the saved source snapshot, with fiscal as_of <= source_at
<= available_at <= DB read <= computation. Unknown or future provenance makes
the financial components uncovered. This does not replace RC4 financial source_at
(the contributing row date); it is an additional causal check on the overlay.
B3 accepts no source arguments and returns an RC5 policy-only COMPLETED_NULL
assessment, without any provider acquisition or fabricated provider receipt.
