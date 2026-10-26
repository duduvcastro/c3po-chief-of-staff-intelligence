# Source bytes, extraction and bounded original-content binding

This increment provides an offline byte-ingestion API. It performs no capture, connection,
collection, backfill, grid, return-label computation, source selection or promotion.
`SourceBytes` requires an explicit supported kind, HTTPS source URL, zoned capture clock,
expected SHA-256 and immutable bytes. A digest check and an official-looking URL verify
integrity and the claimed URI shape; **they do not authenticate where supplied bytes
came from**. Every manifest retains `origin_authentication=unverified_supplied_bytes`
and historical admissibility remains false. There is no trust/admissible boolean argument.

## What is actually extracted

- A SEC header must name one unambiguous CIK, accession and acceptance clock. The URL
  path must match that CIK/accession; its SHA-256 must match the raw UTF-8 bytes. Capture
  and SEC acceptance remain distinct clocks. A reported four-digit SIC code is preserved
  as a raw classification field; no industry/financial taxonomy is chosen from it.
- A SEC native XBRL instance must be under the same CIK/accession URL path as the
  separately supplied header bytes. Context entity CIKs must agree. Periods, explicit
  dimension QNames, class-specific values, lexical values, units and original-fact hashes
  remain separate. `TradingSymbol`, `Security12bTitle` and `SecurityExchangeName` form
  a complete tuple only when all three are in the same context. A symbol/class reported
  in a filing context is not a complete historical validity interval, action history or
  economic per-share allocation.
- A CVM ITR/DFP ZIP preserves its index CNPJ, ID_DOC, version, reference date, receipt
  date and the existing conservative receipt-day-end availability clock. Entry/row
  hashes bind account codes/descriptions, consolidated or individual scope, periods,
  known currency scale, original values and ordinary/preferred/total issued/treasury
  counts. The requested document ID set may restrict extraction. Revisions remain
  separate document versions. No ticker is obtained from a current issuer map.

The [SEC XBRL Guide](https://www.sec.gov/files/edgar/filer-information/specifications/xbrl-guide-2024-07-08.pdf),
sections 3.2.3–3.2.4, documents dimensional share counts and same-context securities facts.
The [official CVM ITR](https://dados.cvm.gov.br/dataset/cia_aberta-doc-itr) and
[DFP](https://dados.cvm.gov.br/dataset/cia_aberta-doc-dfp) descriptions identify statement,
capital-composition and document-download content; their archives can include later
resubmissions. Source layouts are also checked against the existing canonical ingestion
contracts, which this increment does not change.

## Binding and persistence

`bind_canonical_rows` first verifies a fact's canonical row hash, then compares the listed
identity, document/version/form/filed/accepted, concept, unit, period and numeric-value
fields to a unique extracted occurrence. Filing binding also compares the original header
hash where available. The binding receipt lists checked and unproven row fields. Detection-
time symbols, fiscal metadata and capture timestamps are not silently certified by a
matching economic value. Invalid rows are counted as unbound without erasing valid matches.

An unclassed canonical SEC share count is not matched by summing 900 and 100 from two
original class contexts. Dimensional, typed or unsupported scenario content is retained
but cannot masquerade as a dimensionless fact. Likewise, a current ticker suffix, provider
profile, adjusted/close ratio or absent action row never becomes class/basis proof.

`ingest_supplied_original` parses actual supplied bytes before writing any object. A SEC
instance requires actual header bytes rather than a header digest. `OriginalEvidenceStore`
keeps 0600 binary objects under their digest in a private 0700 directory, with atomic link,
file/directory fsync, collision integrity checks and immutable content-derived manifests.
The manifest references parser/dependency hashes, source/capture details, extracted rows,
bindings and remaining proof gates. Retries and concurrent identical ingestions reuse the
same object/manifest; existing corrupt objects are refused rather than overwritten.

Supported extraction is deliberately bounded: native UTF-8 XBRL XML only, without inline
HTML transformations, remote taxonomy/schema resolution, DTDs or entities. Prefix rebinding
and ambiguous contexts are refused. ZIPs use the existing flat Latin-1 semicolon CSV layout,
dot-decimal numbers and explicit known currency scales. No missing amount or scale becomes
zero or one. Limits are 64 MiB per supplied object/entry, 256 MiB ZIP expansion, 1000 members,
250000 XML elements, 128 levels and the existing 16 MiB manifest limit. These are parser bounds,
not an attestation that annual archives or historical coverage fit them. Document-scoped
extraction is available; no full archive collection was run.

## Minimum specific package to review with Fable

For one US issuer/accession, request the complete SEC header bytes, the native XBRL
instance from that accession, exact source/final URLs, expected content digests, capture
clock and independently verifiable official retrieval provenance. Include the original
taxonomy/member/rights documents when a custom class or security description requires
interpretation. A header or instance hash alone is insufficient origin authentication.

For one B3 document, request the original CVM ITR/DFP archive bytes, year/type, exact CNPJ,
ID_DOC, version/reference date and source/capture/digest provenance. The document index,
account and capital-composition entries must be retained together. The adapter can bind
these contents, but ON/PN totals alone do not map a quoted ticker or unit to its allocation.

The remaining instrument package needs actual official SEC/CVM evidence for historical
symbol/issuer/class validity, class rights or unit/depositary composition and the relevant
corporate actions with effective and availability clocks. It must establish the interval
reconciling statement shares and the quoted instrument, including a justified coverage
claim before concluding that there were no intervening actions. Current metadata cannot
fill this gap. If the allowed official documents do not contain it, keep that source
contract pending for Fable; do not add an external financial feed or invent a mapping.

Only extraction and integrity mechanics are exercised with synthetic fixtures here.
No real original, official transport, historical coverage, classification policy or per-
share basis is attested. All prior gates, owner PREREG signature/horizon on 29 October,
grade no earlier than 30 October and the unchanged served source remain in force.
