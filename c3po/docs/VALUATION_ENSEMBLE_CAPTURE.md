# Explicit official-transport seam

`app.valuation_ensemble_capture` prepares a bounded capture API. Nothing calls it from
an import, settings file, existing producer, scheduler, shadow caller or command line.
This construction increment executes **synthetic transports only**. It performs no
real SEC/CVM capture, discovery, backfill, database/host operation, grade or promotion.

An operator must supply a `CaptureRequest`, every `CaptureLimits` field, an explicit
transport, clock, private `OriginalEvidenceStore` and actual operator User-Agent before
calling `OfficialCaptureClient.capture`. Missing/invalid identity or limits fail before
transport. No personal contact, contracted capacity, environment token or default quota
is inferred. A nonblank User-Agent is a syntactic prerequisite, not proof of its owner's
identity or the required aggregate traffic coordination.

## Transport and limits

The opt-in `HTTPSOfficialTransport` uses the standard library's CA/hostname-verifying
TLS context, TLS 1.2 or later, direct HTTPS connections and GET only. It sends the supplied
User-Agent, `Accept-Encoding: identity` and `Accept: */*`; it has no cookie, credential,
proxy, insecure-context or automatic-redirect option. Only the exact supported SEC
archive header/native-instance and CVM ITR/DFP archive URI shapes are accepted. Unsafe
credentials, query/fragment strings, ports, encoded paths and alternate hosts are refused.
The default platform CA trust configuration still needs operational review; a TLS
observation is not independent authentication of the captured scientific source.

Redirects are handled by the client, with the same allowlist and document identity
checked at each hop. SEC issuer-path CIK and accession must remain stable; the accession
prefix need not equal the issuer CIK because a submitting agent can supply the filing.
CVM archive type/year remain stable. Each hop spends the same request budget. Redirect
limits, loops, a pending local interval and changed/unsafe identities produce concrete
refusals. There is no internal sleep or automatic retry; a fast redirect can require an
external scheduling decision. These redirect restrictions are engineering choices,
not a claimed official guarantee about redirect behavior.

All limits are explicit: request count, minimum interval, response/body-byte totals,
socket timeout, observed elapsed time and redirects. Response streams are bounded reads;
up to one extra body byte can be observed to detect a violated byte bound, and its prefix
digest/length are retained. Declared size, actual size, duplicate selected headers,
unsupported encoding, empty bodies and optional expected-digest mismatches are checked.
Non-200 responses, `Retry-After`, transport failures and clock inconsistencies are recorded
without silently retrying. Persistence errors propagate rather than becoming source refusals.

Elapsed checks and per-operation socket timeouts can reject a late observation. They
**do not demonstrate a hard total wall deadline across DNS, TLS, headers and body**.
Receipts state this limit explicitly. Real duration, network byte overhead, capacity,
multi-process coordination and runtime failure behavior are unmeasured here.

The [SEC access guidance](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)
asks automated clients to declare identification/contact in their User-Agent and gives
a maximum of 10 requests per second. Its [security policy](https://www.sec.gov/about/privacy-information)
applies that ceiling to the user across machines. The client refuses a SEC interval below
0.1 seconds, but its in-memory lifetime limiter cannot attest the user's aggregate traffic
or available quota. It must not be used to claim ten requests per second are available.

The [CVM portal terms](https://dados.cvm.gov.br/about) reserve access/concurrency controls.
No numerical request quota or CVM-specific User-Agent format was established from the
consulted documentation. A conservative local limit is an operator policy, not a CVM
entitlement. The [ITR](https://dados.cvm.gov.br/dataset/cia_aberta-doc-itr) and
[DFP](https://dados.cvm.gov.br/dataset/cia_aberta-doc-dfp) descriptions include updates and
resubmissions; the current archive is not evidence that its contents existed at an earlier T.

## Private observations, not origin flags

Each explicit attempt gets an immutable private receipt, including refused attempts.
It records validated requested/redirect/final URIs, HTTP statuses, request/finish and
complete-body receipt clocks, elapsed observations, allowed normalized metadata, actual
body/prefix SHA-256 and length, limits, lifetime counters and implementation hashes.
HTTP Date/Last-Modified are labeled metadata only. They cannot backdate a capture or prove
historical publication. `body_received_at` is distinct from the official document's
acceptance clock later extracted by the original parser.

Only complete accepted bodies receive private binary objects. The receipt is 0600 in a
0700 store; binary objects have the same existing digest, ownership and immutable-write
checks as supplied originals. `read_capture_receipt` verifies the private receipt/object
link, byte length/digest, clock ordering and closed gates. Identical replayed observations
verify an existing immutable receipt. Reopening a JSON receipt does not reperform TLS or
authenticate a source.

`status=captured` means only a complete bounded HTTP-200 body with consistent transport
metadata. `original_layout_status=not_validated_transport_bytes_only` remains explicit:
even a challenge page returned with status 200 still needs the separate original parser,
which refuses it. Captured bytes are never passed into a financial model automatically.

Raw User-Agent/contact, arbitrary headers, cookies, exception messages and body contents
are absent from the receipt. ETags and the observed peer certificate are hashed; selected
HTTP dates/content type and TLS version/cipher remain explicit. No secret is read from
the environment. The actual bytes remain solely in private binary objects.

Injected transport results are labeled as such. Even the concrete client's result keeps
`origin_authentication=transport_observation_requires_independent_review` and historical
admissibility, buy permission and served-change gates false. An offline package, URL,
digest, schema field or supplied flag cannot promote origin. A later genuine execution
would attest only what this client observed, subject to transport/runtime review.

## Specific seam to review with Fable before real capture

Provide the genuine operator identification/contact for SEC, the reviewed aggregate
request/concurrency coordinator across users/processes/machines, local byte/time/request
budgets, an explicit official document URI set and private receipt retention location.
Review platform TLS/DNS/proxy assumptions, timeout/deadline behavior, redirects and source
licensing/attribution. CVM quota/capacity remains unspecified; annual archives can exceed
the original parser's 64 MiB object bound. No full archive coverage is claimed.

This transport evidence still does not supply historical symbol/issuer/class validity,
class rights/per-share allocation, corporate-action coverage intervals or a reviewed
financial classification policy. Those proof gates remain separate and closed. The served
producer is unchanged; owner PREREG signature/horizon on 29 October and grade no earlier
than 30 October remain prerequisites for the new study.
