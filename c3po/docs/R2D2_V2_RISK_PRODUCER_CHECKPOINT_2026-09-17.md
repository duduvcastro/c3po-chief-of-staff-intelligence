# Risk producer — evolving checkpoint, not a deployable release

Owner priority: implement now, seeking the earliest valid operating session.
Base: `1bb009c3d029ba8a74143bb22381a68bc1e86634`.
No changes to the approved D18 package, production, policies or databases.

## B1R2 audit disposition (17 Sep)

- B1R2-1: symbol argument validated then uppercased, matching the origin;
  invalid symbols raise instead of silently yielding zero.
- B1R2-2: repeated `(source_code, external_id)` raises; the differential test
  seeds via `save_ir_events`, including an upsert, before reading the population.
  JSON-string metadata is decoded as in the SQL path. Distinct Finnhub/EODHD
  external IDs for the same filing remain distinct, as in the origin: no new
  cross-provider deduplication is claimed.
- B1R2-3: quarterly selection now follows descending provider KEYS, first eight,
  then the first four valid object rows, with `date or key`. Duplicate-period
  coverage guard applies only to the selected four, not the global history.
  Explicit remaining coverage guard: malformed/future statement dates and
  duplicate selected periods are refused, although the permissive original
  arithmetic can sum them. This is not a claim of identical eligibility.
- B1R2-4: analyst dates require literal YYYY-MM-DD, malformed dates are skipped
  and do not reject the issuer. Future records remain a causal refusal.
- B1R2-5: institutional identity explicitly accepts uppercased ticker and integral
  numeric year/quarter strings; fractions are refused, never truncated.
- B1R2-6: fundamentals appends `.US` only without a dot; B3 market/SA suffix are
  refused before transport. Producer must turn unsupported market into NULL.
- Insider coverage still requires a factual 180-day ingestion receipt; the
  existing 90-day Finnhub ingestion does not prove it. No ingestion was changed.

144 targeted tests pass in this revision. B1 closure remains for Fable's review;
the entire producer and historical gate are still incomplete.

## Implemented and locally verified

- Injectable bounded acquisition of EODHD fundamentals and paginated Form 4,
  FMP grades and institutional quarter summary. Exact bytes and receipt clocks;
  exception text is not copied to receipts. These receipts are private.
- A missing next-page indicator, invalid/cross-symbol link, failed page or page
  budget is incomplete, not an empty success. Pagination exhaustion alone does
  not prove covered population. No acquisition result asserts READY.
- Candidate normalization rejects missing/nonfinite numeric fields, fractional
  counts, wrong institutional symbol/quarter, future analyst records,
  incomplete quarterly statements and mixed statement currencies. RC-4 analyst
  deduplication uses (date, gradingCompany, action); no fiscal-day TTL is added.
- RC-2 ratio heuristic and canonical database-event insider counting implemented
  with differential tests. Raw Form4 helper renamed diagnostic-only. Eight
  origin files pinned by exact git bytes, including investor_relations ingestion.
- 134 tests pass (acquisition, normalization, existing risk kernel/adapter).
  Backend Pyright: zero errors/warnings. No real provider calls in this check.

## Still required; this checkpoint must not be connected to production

1. Finish extracting the complete upstream normalization from pinned `6083d742`, including
   database insider deduplication/direction and published_at semantics. Merely
   counting Form 4 rows is NOT established equivalent. The original database
   total counts only accepted directional events, not every filing/transaction.
2. `_ratio` (`abs(value)>2` divides by 100) is now implemented. Finish financial fallback
   chains, debt versus net debt, and zero-valued EBITDA fallbacks explicitly.
   Candidate helpers do not yet implement the four fundamental risk inputs.
   Four-quarter completeness is the owner's accepted RC-4 coverage guard, not
   permission to change the original arithmetic or claim untested equivalence.
3. Implement issuer/window coverage evidence, source clocks and audited
   freshness; wire all seven components to the existing pure adapter. An HTTP
   200 with `[]` is not enough to establish that the issuer is covered.
4. Add bounded authenticated transport, private immutable spool, byte-verified
   source pins and executor manifest. No transport is installed by this patch.
5. Run the requested 20-name historical M1 differential check privately, with
   actual archived input provenance. Synthetic tests cannot replace this gate.
6. Adversarial source/code review, integration/CI, approved deployment window,
   acquisition/readback and certification before an operating session.

## Schedule reconciliation

The existing Friday capture is 10:59:30 BRT for a useful 11:00–11:01 cut.
It cannot establish eligibility for a 10:30 opening. Wednesday's ten-name proof
does not establish Friday's list/capacity. D18 checks container IDs and env hashes
through capture; deploying a producer before then needs a successor package,
new baseline and independent GO, not an in-place edit to the approved package.

Codex requested a joint actionable schedule by 15:00 BRT on Sep 17, comment
5718070497. Fable's disposition 5718122041 proposes a later certified session;
that estimate is not a guaranteed delivery or an authorization to waive gates.
The owner's request already establishes immediate priority: no duplicate owner
assent is needed merely to develop and review this code. Separate deployment
and session evidence remains necessary.

Provider references (retrieved 2026-09-17):
- https://eodhd.com/financial-apis/insider-transactions-api
- https://site.financialmodelingprep.com/developer/docs/stable/grades
- https://site.financialmodelingprep.com/developer/docs/stable/positions-summary
