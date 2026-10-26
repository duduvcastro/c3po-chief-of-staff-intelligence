# Explicit original packages in the shadow caller

The cross-section caller can now ingest an explicitly supplied offline original package
and reconcile it with the exact canonical reader results used in the same execution.
It does not fetch, collect, connect, backfill, read labels or launch a grid. The original
bytes, source content equality, computability and historical admissibility are separate
statuses. Matching supplied bytes never authenticates their official origin.

## Entry points and package shape

`run_shadow_cross_section` and `run_from_canonical_readers` accept optional
`original_package: OriginalPackage` and `original_store: OriginalEvidenceStore` together.
There is no implicit byte store or source connection. The existing source-reader handles
remain caller supplied; their filing/fact results are copied when first returned for each
company's adaptation. The reconciliation does not reread or replace those observations
with a later source value.

The offline CLI `python -m app.valuation_ensemble_caller` adds the paired arguments
`--original-package` and `--original-receipt-directory`. The existing four arguments are
unchanged. Package ingestion is optional; without it, byte availability remains missing
and all requested companies still appear in the model denominators.

The package JSON has exactly `schema=VALUATION-ENSEMBLE-ORIGINAL-PACKAGE-v1` and an
`artifacts` list. Each item requires:

| Field | Meaning |
| --- | --- |
| `artifact_id` | Unique lower-case identifier, letters/digits/underscore/hyphen, at most 64 characters |
| `kind` | `sec_header`, `sec_xbrl_instance` or `cvm_archive` |
| `source_url` | The supported claimed official HTTPS URI; this is not origin authentication |
| `captured_at` | Explicit zoned capture instant, kept separate from regulator availability |
| `expected_sha256` | Expected digest checked against the actual supplied bytes |
| `local_file` | A simple filename adjacent to the package JSON, opened without following a final symlink |
| `header_id` | Required only for a SEC instance; references its separately supplied header item |
| `document_ids` | Optional nonempty list selecting CVM document IDs |

The package cannot contain a trust, admissible or source-authenticated boolean. Unknown
fields, duplicate IDs, invalid dependency references and paths outside adjacent simple
filenames are configuration refusals. JSON or local-file errors also refuse the call.
These errors are distinct from a readable artifact whose digest/layout fails validation:
that artifact receives a concrete refusal in an otherwise complete inventory.

## Reconciliation and receipts

Every valid artifact is extracted and persisted by the previously reviewed byte/manifest
ingestion API. Header bytes are mandatory for SEC instances. Manifests are read back with
binary-object digest verification. Ambiguous duplicate document roles are refused
together, including affected header dependencies; the caller cannot choose whichever
original favors a canonical value. Other valid artifacts can still be reconciled.

The cross-section receipt records all ingested/refused artifact IDs, reasons, document
identities, object digests and manifest run/payload hashes.

Refused artifacts also retain the actual supplied byte digest and a digest binding the
claimed metadata/dependencies to those bytes. Different refused inputs cannot share a
receipt merely because they have the same failed expected digest and refusal reason.

Its company receipts keep:

- A private ledger of every observed fact row, its canonical row ID/hash, original source
  content, fields that actually used it, byte availability and checked content equality.
- Relevant canonical filing rows and their document bindings. Detection-time symbols
  remain explicitly unproven rather than turning into historical instrument identity.
- Field dependency chains, including all raw quarters behind TTM/YTD derivations and both
  sides of combined CVM share/debt/liability fields. Completeness requires every observed
  contributing row and its document binding, not just one successful row.
  Document keys include issuer, version and acceptance, so a later registry version with
  the same document ID cannot invalidate the version actually used in T.
- Model-level counts for all required input bytes and all required checked content.
  A refused company remains in the denominator. A fact stage not reached remains
  `not_observed`, and a later price refusal does not erase an earlier factual match.

Raw source values and local artifacts remain in private receipts/stores. CLI stdout stays
limited to hashes and aggregate status/counts. Retries with unchanged inputs are immutable
and independent of package/request ordering. The existing object/manifest size bounds
remain enforced; nothing is silently truncated to make coverage appear complete.

## The remaining proof seam

`all_required_checked_content_equal` means the listed canonical content agrees with
supported supplied originals. It does not certify source transport, a complete taxonomy,
historical symbol/issuer/class validity, economic per-share allocation, corporate-action
coverage or model applicability. The historical-admissibility gate remains structurally
closed even when all byte/content counters are complete. Source refusals are reported
alongside those counters, never converted into authenticated origin by a manifest flag.

The concrete original and instrument package to review with Fable remains described in
[VALUATION_ENSEMBLE_ORIGINALS.md](VALUATION_ENSEMBLE_ORIGINALS.md). A future reviewed source-
authentication and historical instrument adapter is required before any admissibility
promotion. This integration chooses no scientific horizon, taxonomy, rates or protocol.
The owner's separate 29 October PREREG signature/horizon, grid no earlier than 30 October,
Fable review and the unchanged served source remain required.
