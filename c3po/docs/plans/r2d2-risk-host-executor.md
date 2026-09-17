# Risk producer host executor — block 3

This is the implementation manifest for the artifact-only runner. It is not an execution order, a CERTIFIED release, a policy, or a replacement for the approved D18 package. No commands in this document have been run in production. A concrete plan and independent GO must bind the installed code, inputs, windows and private roots before execution.

## Runtime and authority

The entry point is `app.r2d2_v2_risk_host_executor`, pinned with the repository head. Run inside the existing `c3po-api-1` container, with its configured runtime user and existing environment, from `/app`. The checked-in Dockerfile and Compose do not override `USER`, so their default is root (UID/GID 0); the installed container identity still requires a fresh read before a future execution. The concrete host manifest must record that user's numeric UID/GID and ownership of its mounted private root; the runner does not change users, ownership, mounts or container configuration. All directories traversed by private inputs/outputs are non-symlinks, private roots are 0700, and receipt files are 0600. A separate host launcher must establish the container identity and installed revision before invoking this entry point.

Only these existing container environment keys supply credentials:

| Purpose | Settings key | Existing alias |
| --- | --- | --- |
| Dedicated restricted database connection | `C3PO_R2D2_RISK_DATABASE_URL` | None; never falls back to `C3PO_DATABASE_URL` |
| Finnhub direct insider transport | `C3PO_FINNHUB_API_TOKEN` | `FINNHUB_API_TOKEN` |
| EODHD fallback transport | `C3PO_EODHD_API_TOKEN` | `EODHD_API_TOKEN` |

No credential value is an argument or receipt field. This runner does not fetch new FMP fundamentals: the pinned predecessor supplies fundamentals, grades, institutional, official and optional FX receipts. The transport uses fixed provider hosts/routes with TLS, response-size and elapsed-time limits. The database adapter opens psycopg with the dedicated restricted DSN, verifies a READ ONLY / REPEATABLE READ transaction and effective privileges before reading `public.ir_events`. Its private receipt records the actual role and authority evidence. It refuses superuser/role administration/database creation/replication/RLS bypass, memberships, database CREATE/TEMP, ownership or schema CREATE, missing SELECT, table/column write privileges and RLS that could hide events. It never initializes or synchronizes the database, creates a role or changes privileges. Existing API-owner credentials are not a fallback. Provisioning and verifying this separate credential is a future operational prerequisite, outside this code change and outside D18 prepare.

`SOURCE_PINS.json` uses schema `RISK_HOST_SOURCE_PINS_V1` and a `files` map of relative path to SHA-256 covering **every** `app/**/*.py` file in the actual runtime source root. Missing, extra, modified and symlinked sources are refused. Generate these pins from the selected checkout/image; do not reuse pins from a different head.

## Concrete input plan

The plan schema is `R2D2_V2_RISK_HOST_PLAN_V1`. It binds:

- `namespace`, `session_date`, UTC `cutoff_at`; namespace must be the matching `R2D2-V2-DIAG-R4-<date>` or `R2D2-V2-SHADOW-<date>`.
- Absolute `runtime_source_root` and `spool_root`, checked against the CLI arguments.
- `phase_windows` for `preflight`, `acquire`, `execute`, each with `not_before` and `not_after`.
- Hash/path references to `source_pins`, `owner_order`, `list`, `admission`, and `replay_manifest`; paths are relative to the private plan directory.
- `limits`: `max_symbols`, `max_total_requests`, `max_body_bytes`, `max_total_bytes`, `max_elapsed_seconds`. Runtime ceilings are 550 symbols, 10000 HTTP attempts, 16 MiB per response, 1 GiB total and 86400 seconds per phase; the capture additionally caps elapsed time at 3600 seconds. These are ceilings, not recommended operating budgets.

The ordered list contains `{symbol, market}` entries. Its namespace/date, exact symbol set in admission and ordered entries in the replay predecessor must agree. Existing sources must validate before provider access. The cutoff must have UTC offset zero, verified before preflight creates a phase directory and before the runner reads the database. It is fixed for the entire batch; acquisition/receipt clocks remain factual and are never backdated to it.

The owner order uses `R2D2_V2_RISK_HOST_ORDER_V1`, scope containing namespace/date/cutoff and the three phases, with actions exactly `READ_PROVIDERS`, `READ_DATABASE`, `WRITE_PRIVATE_RISK_ARTIFACTS`. The detached GO uses `R2D2_V2_RISK_HOST_GO_V1`, verdict `GO`, scope `RISK_ARTIFACT_ONLY`; its binding includes the plan/order/source-pins/list/admission hashes, scope and phase windows. Both files are rechecked by bytes. Synthetic orders/GO in tests are not operational authority. Completed certification is not required to produce its risk input; this authority cannot activate a session.

## Invocation and phase order

The following uses shell variables populated from the audited concrete plan. It is a command template, not a current authorization:

```sh
docker exec --workdir /app c3po-api-1 python -B -m app.r2d2_v2_risk_host_executor preflight \
  --manifest "$RISK_PLAN_PATH" --manifest-sha256 "$RISK_PLAN_SHA256" \
  --go "$RISK_GO_PATH" --go-sha256 "$RISK_GO_SHA256" \
  --source-root /app --spool-root "$RISK_PRIVATE_ROOT"
```

Invoke the same command with `acquire`, then `execute`, adding `--previous-receipt-sha256` with the immediately preceding completed receipt hash. No invocation adds secrets to arguments. The configured container user must already have access to the mounted 0700 root. Input relay/source-spool paths are the private plan directory and hash-bound predecessor references; no public relay or new mount is created by this module.

1. **Preflight:** verifies plan/GO/order/source pins/windows/list/admission/predecessor, creates a new `<spool_root>/<plan_sha256>` directory and a completed receipt. It makes no provider or database call.
2. **Acquire:** revalidates inputs and predecessor receipt. For each US symbol, captures the database comparison and direct Finnhub receipts, selecting complete EODHD fallback only under RC4bis rev3. Per-symbol counts are private. B3 produces a skip record without constructing credentials or opening HTTP/DB. Capture completion does not mean coverage is complete.
3. **Execute:** assesses captured immutable inputs, records actual computation and durable availability times, and invokes the offline risk executor. Produces `risk.json` with explicit NULLs for incomplete inputs. It does not turn an incomplete input into zero or certify a release.

## Receipts and failure handling

Every phase creates `<phase>.STARTED.json` exclusively, then `<phase>.RECEIPT.json` only on success. Receipt chain binds plan/GO and preceding receipt hash. A caught failure after the marker attempt creates an exclusive, durable `<phase>.FAILED.json` when storage permits, carrying a fixed allowlisted code, plan/GO/predecessor binding and the last validated clock (explicitly not the failure time). Unknown exception text, paths and credentials are never reflected. The CLI prints a filtered code matching `[A-Z0-9_]{1,64}` and the failure receipt hash when written.

Exit status is **0** for completed, **2** for refusal before a marker attempt, and **3** for uncertain work after it. Interruptions inside a phase are sanitized and follow the same rules. A repeated phase cannot overwrite any old marker, successful receipt or failure receipt. If storage prevents the failure receipt, stdout explicitly reports that it was not written; it does not claim durability. SIGKILL, power loss and storage loss cannot be handled by Python and may leave only STARTED.

If a marker exists without completion, **do not replay**. Reconcile STARTED, FAILED (if present), predecessor hashes and private partial artifacts by read-only inspection, then obtain a disposition. Never convert FAILED into COMPLETE or remove a marker to retry. No automatic retry or operational reconciliation execution is implemented.

Expected private outputs beneath `<spool_root>/<plan_sha256>`:

| Phase | Output |
| --- | --- |
| preflight | `preflight.STARTED.json`, `preflight.RECEIPT.json` |
| acquire | `capture/` per-symbol provider, database and comparison files; `capture/MANIFEST.json`; `acquired/acquired.json`; phase markers/receipt |
| execute | `assessment/` copied inputs, actual assessment results/clocks and `manifest.json`; `risk-output/risk.json`, assessments, execution receipt and final manifest; phase markers/receipt |

Cloned input bodies have an aggregate 512 MiB ceiling per clone set; exceeding it refuses with `BUFFERED_INPUT_BUDGET_EXHAUSTED`. This is bounded buffered I/O, not streaming: capture/acquired/assessment may retain separate copies, and space for those copies is an operational prerequisite. Per-file limits still apply.

Final capture/output manifests follow durable files and hash verification. Names, source bodies and per-symbol comparisons stay private. CLI stdout carries only phase/status, fixed refusal code, counts and hashes; publish those aggregate receipts to the coordination channel. An empty/unknown provider result is not coverage, database counts are not evidence of provider completeness, and a failed global budget cannot be bypassed by fallback.

## Evidence and limits

The offline CLI E2E executes all three real phases, real filesystem/spool, real runner, fake HTTP and fake read-only database connection. It checks a non-null synthetic result, receipt chaining, factual clocks, private permissions and absence of names/secrets in stdout. Refusals cover GO/hash/source pins/admission/window/budgets, uncertain replay, durable filtered failure receipts, distinct refusal/uncertainty exits, interruption, aggregate clone budget, non-UTC cutoff, and B3 without credentials. Runner tests separately cover paging, pacing, global limits and database transaction mode.

Not covered by those tests: live provider completeness, production credential entitlement and availability/ACL of the dedicated restricted DSN, the installed container/source pins, mounted path ownership, current real admission/list, a new authorized host acquisition, completed certification, or an operating session. The separate contemporary 20-symbol evidence remains a read-only differential sample; its 13 READY / 7 NULL outcome must not be presented as complete coverage. No merge, deploy, policy, epoch or worker mutation belongs to this executor.

## Successor admission handoff (R8-10)

The host plan and replay manifest must pin the original bytes of the successor's
`receipts/admission.result.json`. A `CODEX_CERTIFIED_PHASE_RECEIPT_V1` receipt is
accepted only for phase `admission`, status `PASSED`, exact namespace/session,
and an `AVAILABLE` causal readback with no diagnostics. Its selected count,
receipt count and ordered `symbols.txt` SHA256 must agree with the host plan's
private list. There is no synthetic replacement receipt with a top-level symbols
array. Legacy artifact admissions keep their prior contract. Recognized successor
receipts always use the stricter branch, even if a `symbols` field is also present.
This verifies the pinned predecessor's format and identity; the owner's order and
Fable GO must still bind its actual bytes and the independently accepted chain.

After `preflight -> acquire -> execute` all return COMPLETE with linked receipts,
the handoff input is `<spool>/<plan-sha>/assessment/manifest.json`, with the hash
in `execute.RECEIPT.json.outputs.assessment_manifest`. Never stage
`acquired/acquired.json`: it has no factual assessment yet. The successor's
`stage-risk-inputs` validates this same admission hash and ordered list, then its
`risk` phase consumes the accepted stage. All clocks and source bytes survive the
handoff unchanged. This documentation does not authorize any host invocation.

The existing implementation performs three pure score calculations: the factual
assessment (which records durable availability), the host's replay verification,
and the successor's replay verification. Only acquisition calls the provider and
read-only database. The proposed R8-10 disposition retains this explicit
redundancy for independent replay at the publication boundary, subject to Fable's
review; it does not introduce another acquisition, change assessment times, or
publish the host's intermediate risk artifact as a certified component. Only the
successor's own risk receipt can extend its chain. Offline tests compare risk and
assessment bytes across the two replay outputs. Runtime and capacity for a full
real list are not established by the synthetic tests.
