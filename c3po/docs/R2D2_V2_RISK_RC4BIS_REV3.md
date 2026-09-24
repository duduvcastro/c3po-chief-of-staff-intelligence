# RC4-bis rev 3: EODHD substitute after a verified Finnhub failure

Owner authorized validation of EODHD as the substitute when Finnhub fails.
The Fable disposition is pinned as
`b7a80c08cc600bc1314b49966816575e650e86f8daf6fe801705c31c8ae627be`.
This code does not authorize deployment, ingestion, policy installation or
production changes.

The opt-in constructor is
`DirectInsiderAcquirer(acquirer, fallback_on_failure=True)`. Default false keeps
the original empty-only fallback policy. The existing snapshot schema remains
DIRECT_INSIDER_RC4BIS_V1, with an explicit policy binding:

- fallback_contract_sha256:
  `b569610f24639c5ba54841f2003dceb864331f9d2138fc0f9c31de4949601c63`
- fable_disposition_sha256: the disposition hash above.
- provider_selection: exact selected provider and the independently replayed
  reason, for example FINNHUB_HTTP_403, FINNHUB_SINGLE_DAY_SATURATED,
  FINNHUB_REQUEST_BUDGET_EXHAUSTED, or FINNHUB_EMPTY.

The policy hash is SHA256 of this exact ASCII text (without newline):
`RC4BIS_REV3:Finnhub_attempt_verified;EODHD_on_HTTP_transport_invalid_future_empty_or_truncated;no_union;full_EODHD_coverage;integrity_failure_never_fallback`

Replay first validates the original Finnhub attempt's raw bytes, payload hashes,
clocks and exact request-window tree. Damaged hash, impossible clock, wrong
request, missing tree evidence, absent attempt or arbitrary budget modification
never becomes a provider failure. A budget truncation is provable only when
the recorded request count reaches the declared budget and a tree branch still
needs traversal. Response failure, invalid envelope, future/out-of-window row,
HTTP rejection, single-day saturation and verified empty population may select
EODHD. Partial Finnhub events are discarded, never unioned into the fallback.
Original acquisition diagnostics and all primary receipts remain in the
private snapshot. The selected provider/reason is checked against replay.

EODHD must independently pass complete pagination, symbol identity, strict
filing and transaction dates, no future rows and normalization without dropped
records. Rev 3 requires meta.total and meta.page(offset,limit); total must stay
constant, unique accession_number cardinality must equal total, and page links
must follow the exact offset progression. next=null alone does not prove
completion. A 559/560 result or a 99-record page that jumps the next offset by
100 is UNKNOWN, not repaired by pretending a skipped record was empty. If an
EODHD fallback record is future, the diagnostic is explicitly prefixed
EODHD_FALLBACK_; it is not mislabeled as a Finnhub error.

Budgets remain separate and bounded (default128 Finnhub requests plus at most
100 EODHD pages), recorded as request_limits. Raw bytes stay private. No real
HTTP calls were made while implementing this extension. Synthetic tests cover
HTTP rejection, response invalidity, date failure, both truncation classes,
no-union semantics, empty-only legacy behavior, damaged evidence, unknown
contract, absent attempt, total gaps, duplicates, wrong page metadata and
future fallback records. Actual fallback success is not claimed by these tests.

## Read-only validation on 17 September

The owner's authorization was published in coordination comment 5719255234.
The two failed insider cases from the existing 20-name sample were selected
before any new call. The EODHD-only validation used 11 requests, all HTTP 200,
and 7,236,879 response bytes; no database or host writes occurred.

The original future-date refusal came from EODHD after empty Finnhub, not from
Finnhub or an incorrect runner clock. That issuer also returned 99 filings at
offset 400 with a next offset of 500. The saturated-Finnhub case returned 559
unique filings while declaring meta.total=560 despite ending with next=null.
Both remain UNKNOWN. The old 13 READY / 7 COMPLETED_NULL disposition is
unchanged; this validation does not claim additional coverage or authorize
operation.

Private capture SHA256:
`4266011d90cfa2f59a70fa890f3c0f8e9afb2216fde036a4ca0f83fa62fd3c6c`.
Private combined differential SHA256:
`dc8d11999b1f797f9ea082e301c33ea7b63a98b17578493db9fd4949e75dbd35`.
It preserves the other 18 bundles and the primary receipts of these two cases;
all 20 arithmetic comparisons remain exact, with no unclassified exception.

Existing Finnhub receipts separately establish inclusive date boundaries:
one from=to receipt is nonempty; one nonsaturated multi-day leaf has five
transactions on its to date. Public aggregate SHA256:
`c818bcfe84a0321d606e668421addd036517b965fa2ddddcab8890e2d8a129b6`.
This is observed evidence for the sample, not a provider-wide SLA.

## Adversarial review E-1 through E-3

Deep JSON that the acquisition parser marks JSON_INVALID remains a classified
provider failure during replay; parser recursion does not crash the batch.
The rev3 opt-in requires a UTC query cutoff before making a request and again
on replay. A non-UTC cutoff is a runner/scope error, never a reason to switch
providers. Provider rows outside the requested dates remain a separate invalid
response condition.

The extra EODHD metadata/accession cardinality requirements apply only to rev3
opt-in snapshots. Legacy snapshots retain the prior empty-only selection and
metadata behavior, even when a meta member exists. They do not acquire a new
fallback authorization by replaying under newer code. This compatibility rule
is not a claim that old evidence satisfies the stricter rev3 coverage gate.
