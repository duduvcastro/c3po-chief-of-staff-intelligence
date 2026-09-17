# Offline risk replay executor — block 3 component

`execute_private_risk` does **not** call HTTP, read a database, execute a host
command, install a policy, alter an epoch or certify a release. It takes an
explicitly pinned private manifest and previously acquired evidence, runs the
Path A bundle adapter, and writes a new local private artifact. This is useful
for offline counterexamples and preparing integration. It is not the historical
20-name proof by itself.

## Call and manifest

Arguments: `manifest_path`, exact original-byte `manifest_sha256`,
`expected_namespace`, `expected_session_date` (Python date), `output_path` (must
not exist), and factual `execution_at` (timezone-aware). The input directory and
all referenced subdirectories must be `0700`; manifest and input files `0600`.
References are relative `{path, sha256}` objects within that directory. Symlinks,
traversal, changed files, duplicate JSON keys and nonfinite JSON are refused.
Each file is bounded at 16 MiB, read once with matching descriptor metadata
before/after, and checked against the pinned original-byte hash.

Manifest schema `V2_RISK_REPLAY_MANIFEST_V1`:

- `mode`: exactly `OFFLINE_REPLAY`.
- `namespace`: `R2D2-V2-DIAG-R4-YYYY-MM-DD` or
  `R2D2-V2-SHADOW-YYYY-MM-DD`; exact agreement with the caller and `session_date`.
  SHADOW is permitted only as the name of an offline artifact, never activation.
- `phase_pending`: integer zero; `decision_at`: factual ISO timestamp no later
  than execution. No pending-phase or future decision can be completed here.
- `admission`: private reference to JSON predecessor bytes. This binds the
  predecessor hash but does not parse its variable implementation-specific
  schema or attest that admission was authorized. The integration launcher must
  validate its receipt chain, identities, list membership and authorization.
- `symbols`: nonempty unique list, at most 550, each with canonical `symbol`,
  `market`, `assessment_clock` reference, `sources`, and optional `fx`.
- Each assessment clock document has `symbol`, factual `computed_at`,
  `available_at`, and explicit `factual_assessment: true`. These are supplied
  provenance claims, not independently established historical facts. They must
  obey computed <= available <= decision <= execution. The executor never
  fabricates old assessment timestamps from its current run time.
- `sources.fundamentals`, `.grades` and `.institutional`: `{receipt: reference,
  body: reference}`. Receipt JSON is the private transport receipt shape:
  request/provider/path/parameters, started_at, received_at, status,
  payload_sha256, diagnostic. All source bodies and clocks are rechecked;
  failed/absent receipts prevent the entire execution from completing.
- `sources.insider` and `.official`: `{body: reference, received_at, source_id}`.
  Body shape is the Path A adapter's PrivateSnapshot contract. These must be
  factual consistent-transaction snapshots; the executor cannot independently
  prove that a supplied snapshot was actually taken from the production DB.
- Optional `fx`: `rate`, `quote_price`, `receipt` (same private snapshot shape).
  The adapter owns FX input binding and currency/coverage validation.

## Outputs and completion

The new directory is `0700`, all output files `0600`. File publication uses
exclusive creation and linking, no overwrite, and fsync. `MANIFEST.json` is
written last and hashes every output plus the input references; absence of that
marker means execution did not complete. Interrupted directories are not reused.
The caller must reconcile and choose a new run after an interruption.

- `risk.json`: `V2_RISK_COMPONENTS_V1`, `session_date`, and `symbols` mapping to
  `{value, producer, source_at, available_at}`. Clocks are preserved from the
  factual assessment receipt. COMPLETED_NULL is retained with null value and
  diagnostic detail in the assessment; it is never silently upgraded to READY.
- `assessments.private.json`: complete per-symbol inputs, coverage and diagnostics.
- `execution.json`: aggregate counts, hashes, separate execution timestamp and
  explicit false flags for production connection, certification, authorization
  and independent historical provenance verification.
- `MANIFEST.json`: private inventory and hashes. Input paths can contain names,
  so this file remains private as well; publish its hash and aggregate execution
  counts, never private inputs or nominal details.

Fixture tests are synthetic. A historical 20-name proof still requires real,
causally acquired, independently audited original receipts; matching synthetic
scores is not evidence that historical provider coverage existed. This component
does not replace the pending authenticated acquisition runner, DB transaction
launcher, production manifest consent or historical proof.

For B3, RC-5 yields an explicit COMPLETED_NULL assessment with factual assessment
clocks and no HTTP or database source requirement; no synthetic provider receipts
are created. US still requires all five source classes. An all-null output says
`readiness=NO_READY_SYMBOLS`; an artifact containing evaluated READY values says
`CONTAINS_READY_SYMBOLS`, never that the release or production phase is certified.
`predecessor_chain_independently_verified=false` remains explicit until the outer
launcher independently validates the admission chain.
