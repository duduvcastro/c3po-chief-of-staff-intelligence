# k9_runner.py — the glue of the K9 daily phases (epoch R2D2-V2-SHADOW-2026-10-05): design, revision 2

**Revision 2 (2026-10-05, after the adversarial review of rev 1 `b5950b99…`; rev 1 kept as `k9_runner.rev1-b5950b99.py`,
`src/k9_runner.readable.rev1-b5950b99.py`, `DESIGN.rev1-b5950b99.md`).** M1: every operation now hashes
`/app/app/**/*.py` (RISK_HOST_SOURCE_PINS_V1, standard library only) against the signed `risk_source_pins_sha256`
**before anything is imported from `app`** (`app/__init__.py` included), then the package check as before. M2: every
runner stop (`Stop`, the budget stops included) is a `BaseException`, so `RiskAcquirer._read`'s `except Exception` can
no longer turn `REQUEST_BUDGET`/`BODY_BUDGET`/`PROVIDER_NOT_ALLOWED` into a counted TRANSPORT_FAILED; `BODY_BUDGET` is
also checked before each further request. Minors: (1) the package value is written only if 64-hex, counts are checked
against K9R's `k9_counts` grammar before COMPLETE, the receipt is serialized inside the guarded block; (2) `silence()`
failing → exit 2 with nothing written; a failed fsync/write after the terminal link → the exit code follows the file
on disk; the result line write is guarded; (4) FAILED/DEADLINE carry the counts gathered so far (closed subset);
(6) the deadline test proves a blocking HTTP call is interrupted, and all tests run the file named by its hash;
(7) the file name `k9_runner-<sha256>.py` matching its content is mandatory; (8) stage takes HOST_PLAN/GO hashes from
bind's RECEIPT and accepts the DIAG-R4 namespace only. Documented: §7. Tests carry no workstation path (environment
variables, clean skips).

Offline work only (2026-10-04, Fable). Nothing here was run on a host, in Docker, pushed or dispatched. Hashes are in
`SHA256SUMS` and `SUMMARY.md`, taken by command.

Specified by `K9_INTERFACE_NOTE.md` rev 2 (`ab5159be…`) §1 F1–F14, §3.1 (Glue), §3.3 (rows "runner"), §4.3; the N-8
placement decision (`codex-n8-placement-20261004.txt`: container mount points unchanged); Codex N-1 (risk namespace
`R2D2-V2-DIAG-R4-<D>` with the plain names document); N-9 (bind writes Fable's GO strictly from signed values; the
executor recomputes). File contracts conform to K9R rev 3 `DESIGN.md` §5 and to K9R's tightened grammars as they stand
in `fable-k9r-20261004/k9_phase_read/build/k9_phase_read.py` at test time (count keys
`[a-z][a-z0-9]{0,30}(_[a-z0-9]{1,30}){1,4}`, codes `K9_CONSTANT_CODE`); the tests import that file and apply its own
functions (`k9_outputs_ok`, `k9_counts`, `k9_attempt_key`, `instant`, key sets) to every file the runner writes.

`R` = `c3po/backend/app/` of release dd4ec4bb (package `b5ce527a…`). The image is `python:3.12-alpine3.24`
(`T0/c3po/backend/Dockerfile:4`), so the target is CPython 3.12; the file also compiles on 3.9.6.

## 0. The bytes

| File | Role |
|---|---|
| `src/k9_runner.readable.py` | the reviewed source (two-space indentation, comments, docstrings) |
| `build.py` | removes comments, blank lines, function/class docstrings and whitespace between tokens, one-space indentation; **asserts** the same token sequence (whitespace, comment and docstring tokens aside) and the same AST (`ast.dump`, docstrings removed) as the readable source, and size ≤ 40,960. `python3 build.py check` proves `k9_runner.py` is the rebuild |
| `k9_runner.py` | the content-addressed file E0 delivers as `tools/k9_runner-<sha256>.py` (40,618 bytes) |

Review `src/`; hash `k9_runner.py`. Module level imports only the standard library; all `app.*` imports are inside
functions, after `/app` is put on `sys.path`. No `print`, `subprocess`, `socket`, `eval`/`exec`, no deletion of any file
except its own `.k9-<random>` temporary after the exclusive link.

## 1. Invocation and the step plan (contract for K9W)

```
python -I /c3po-k9-tools/k9_runner-<sha256>.py --plan /c3po-k9-day/plans/<operation>.json --plan-sha256 <hex>
```

Exactly these four argument words. The plan path must be `/c3po-k9-day/plans/<operation>.json` with `<operation>` one of
the eight runner operations; the file is read by descriptor (no link followed, regular, owner = euid, mode without group/
other bits, one link, ≤ 256 KiB), its SHA-256 must equal `--plan-sha256`, and it must be **canonical JSON**
(`sort_keys`, separators `,` `:`, ASCII, no NaN; duplicate keys refused).

**`K9_STEP_PLAN_V1`** — exactly these keys (K9W writes it, 0600, before `create`):

| Key | Value | Checked |
|---|---|---|
| `schema` | `K9_STEP_PLAN_V1` | identity |
| `epoch` | `R2D2-V2-SHADOW-2026-10-05` | identity |
| `day` | D, one of 2026-10-06 … 2026-10-09 (compiled, as K9R) | identity |
| `k9_phase`, `k9_operation` | Act B phase and operation (K9R's names; `phase` is reserved by the core) | identity; operation = the plan file's name; phase = the compiled phase of the operation |
| `attempt_key` | `sha256(json.dumps([epoch, day, phase, operation], separators=(',',':'), ensure_ascii=True))` (`actb03_lib.attempt_key`) | identity, recomputed |
| `slot` | `PRIMARY` / `SPARE` | grammar |
| `request_sha256`, `go_sha256` | 64-hex | grammar; bind copies `request_sha256` into the GO |
| `run_not_after` | UTC ISO instant (`Z` or `+00:00`) | see §2 |
| `constants` | exactly `package_sha256` (= b5ce527a…), `code_revision` (= dd4ec4bb…), `risk_limits` (= E28's five: 550 / 2200 / 16777216 / 1073741824 / 3600), `disk_floor_bytes` (= 214748364800) — compared with compiled values; `act_b_sha256`, `release_sha256`, `policy_sha256`, `runner_sha256`, `risk_source_pins_sha256` — 64-hex | `runner_sha256` must equal the SHA-256 of the runner's own file (and the hash in its file name) |
| `network_class` | the operation's class (table §3) | equal |
| `database` | `{"host":"db","port":5432,"dbname":"c3po","role":"c3po_v2_causal_emitter"}` for commit/publish, else `null` | equal |
| `risk` | bind only: `{namespace, cutoff_at, phase_windows, owner_order_text, owner_order_sha256}`; else `null` | §3 bind |
| `step_row` | a JSON object (the step table row; opaque to the runner, bound by the plan hash) | object |

Identity failures (plan unreadable, hash, not canonical, schema/epoch/day/operation/phase/attempt key) **write nothing**
(exit 2): without a valid identity no file K9R could attribute to the step can be written. Every other refusal is a
`FAILED.json`.

## 2. Common sequence (every operation)

1. Entry clock `t0` = container clock at `main()` entry (it is the `started_at` of both files; K9W writes
   `created_at` before `docker create`, so `t0` is after it). All output to fd 1/2 is redirected to `/dev/null`;
   logging disabled; exception hooks silenced (docker logs stay on host disk until removal: nothing secret goes there).
2. Plan identity (above) → else exit 2.
3. `/c3po-k9-day` must be a private directory (euid, 0700); `receipts/` is opened (or created 0700) and must be private.
   If `<op>.STARTED.json`, `.RECEIPT.json` or `.FAILED.json` already exists (any type, a link included) → **exit 3,
   nothing written**.
4. **`receipts/<op>.STARTED.json`** (`K9_STEP_STARTED_V1`: `schema epoch day phase operation attempt_key
   step_plan_sha256 started_at`) by exclusive creation: private temporary, fsync, `link()` to the name (fails if it
   exists → exit 3), unlink temporary, fsync directory. 0600. **Before any provider or database call.**
5. **Source pins first (M1):** `constants.risk_source_pins_sha256` must be 64-hex (`PLAN_INVALID`); the runner computes
   `canonical({"schema":"RISK_HOST_SOURCE_PINS_V1","files":{"app/<rel>.py": sha256}}) + "\n"` over
   `Path('/app/app').rglob('*.py')` (the executor's `_source_pins` set) with the standard library only, and refuses
   `SOURCE_PINS_NOT_THE_SIGNED_ONES` unless its SHA-256 is the signed value (`faaa35a7…52bb` for dd4ec4bb). This covers
   every module any operation imports (emitter, causal files/list, producers, risk_*, market_data, `app/__init__.py`),
   and nothing from `app` has been imported yet (the receipt then carries package zeros). Then `/app` on `sys.path`;
   `implementation_package_sha()` (`R/r2d2_v2_earnings_package.py:133`) computed (written only if 64-hex); ≠ b5ce527a…
   → `REFUSED PACKAGE_NOT_THE_CERTIFIED_ONE` (import failure: `PACKAGE_UNAVAILABLE`). Then the full plan validation
   (§1), including the mandatory file name `k9_runner-<sha256>.py` whose content hashes to that name and to
   `constants.runner_sha256` (`RUNNER_NOT_THE_SIGNED_ONE`); `C3PO_BUILD_SHA` = dd4ec4bb… else
   `BUILD_SHA_NOT_THE_PINNED_ONE`.
6. Deadline. LAUNCH operations stop themselves at `stop = run_not_after − 60 s` (K9W's in-container `timeout -s KILL`
   fires at ≈ `run_not_after − 5 s`, so the runner has ≥ 55 s to write its DEADLINE receipt). ATTACHED `bind`/`stage`:
   `stop = min(run_not_after, t0 + 30 s / 15 s)` (their in-container limits are 35 s / 18 s). `now ≥ stop` at this point
   → `REFUSED RUN_NOT_AFTER_PASSED`. A `SIGALRM` timer at `stop` raises a `BaseException` (`Deadline`, not catchable by the
   release code's `except Exception`), and every provider/database call is preceded and followed by the same check.
   Every other runner stop (`Stop`) is also a `BaseException` (M2), so no stop raised inside a release-code callback
   (the paced transport, the connection factory, the clock) can be swallowed.
7. The operation (§3). After it returns, the timer is disarmed and the clock checked again.
8. Exactly one terminal file, by the same exclusive creation, canonical JSON, 0600:
   `receipts/<op>.RECEIPT.json` (status `COMPLETE`, `code` null) or `receipts/<op>.FAILED.json` (status `REFUSED`,
   `FAILED` or `DEADLINE`, a constant code; `outputs` and `aggregates` empty; `counts` = what was counted before the stop
   — `logical_fetch_calls` (collect, components), `http_attempts`/`http_kib`/`bytes_written_kib` (sources), or the
   operation's full counts if they were already computed (capture) — always a subset of the operation's closed set, `{}`
   if not in K9R's grammar). Keys exactly (`K9_STEP_RECEIPT_V1`): `schema status code epoch day phase operation attempt_key
   step_plan_sha256 started_at completed_at package_sha256 build_sha outputs aggregates counts`. `package_sha256` is the
   value computed in the container (zeros if not computed or not 64-hex), `build_sha` dd4ec4bb… if `C3PO_BUILD_SHA` is
   exactly that, else `""`: a FAILED of a wrong image (or refused before the package was computed) is therefore read by
   K9R as not of this step (UNCERTAIN), never COMPLETE. Before writing a RECEIPT the runner checks its own outputs and
   counts against K9R's grammar and serializes it inside the guarded block (`RECEIPT_GRAMMAR`; any failure there is a
   FAILED receipt, not a crash).
9. ATTACHED operations (`bind`, `stage`) also print the terminal file's exact bytes plus `\n` as their **one result
   line** on the original stdout (K9W's attached rows read it). LAUNCH operations print nothing.
10. Exit: 0 COMPLETE; 1 a FAILED file was written; 2 nothing written (including `silence()` failing); 3 a step file
    existed, or the terminal file is not on disk with the runner's bytes (K9R: STARTED_WITHOUT_RECEIPT → UNCERTAIN). If
    the exclusive link succeeded but the directory fsync then failed, the file is re-read: equal bytes → the exit code
    of its status. A failure printing the attached result line never changes the exit code.

`outputs` keys are `day/<path below /c3po-k9-day>` or `source/<path below /c3po-source>`; no key contains a symbol
(per-name files are only ever counted or aggregated). Every value is the SHA-256 of the file as re-read from disk by
the runner after writing (what K9R will hash).

## 3. Per operation

Network class / mounts / env as NOTE §3.3. "Pred" = the predecessor's runner RECEIPT read by fixed path: exact keys,
schema, COMPLETE, code null, epoch, day, operation, phase, recomputed attempt key, package and build constants; a
`FAILED.json` of that predecessor present → refused. "Pred bytes" = a file named in a predecessor's `outputs`, re-read
and hashed: absent → `PREDECESSOR_OUTPUT_ABSENT`, different → `PREDECESSOR_OUTPUT_CHANGED`.

### collect_launch (causal_list; PROVIDER; T, Dd; provider.env)
- Calls `produce_causal_inputs(fetch, session_date=D, output_dir=/c3po-k9-day/inputs)` (`R/r2d2_v2_producer_daily.py:555`),
  `fetch` = the packaged `EodhdFetcher(settings.eodhd_base_url, settings.eodhd_api_token,
  timeout=settings.market_data_timeout_seconds)` (retries 2 by default, F2), counted, deadline-bound.
- Needs: `C3PO_R2D2_V2_PRODUCERS_ENABLED=true` (`PRODUCERS_NOT_ENABLED`); `inputs/` absent (created 0700 exclusively,
  `OUTPUT_ALREADY_PRESENT`).
- Outputs: `day/inputs/{registry.json, registry.receipt.json, daily_contract.json, daily_contract.receipt.json}`
  (each equal to the hash the producer returned, else `OUTPUT_CHANGED`).
- Counts: `registry_symbols complete_bars bar_conflicts logical_fetch_calls`; `registry_counts{provider_rows kept_rows
  skipped_exchange skipped_symbol duplicate_rows}`; `daily_counts{daily_symbols complete_bars bar_conflicts
  fallback_symbols fallback_bars_filled fallback_symbols_unresolved symbols_with_unreadable_splits
  unattributable_split_rows}`. No call-count equality stop (N-6).

### commit_launch (causal_list; DATABASE; T, Dd, Em; no env file)
- Pred `collect_launch`; pred bytes of `day/inputs/registry.json` and `daily_contract.json`.
- `now < 00:00 New York of D − 10 min` (= 00:50 BRT of D) else `COMMIT_AFTER_ITS_LATEST_START`.
- `causal/commitment.private.json` and `causal/build_audit_receipt.json` absent (`OUTPUT_ALREADY_PRESENT`).
- Connection factory (E28 `tonight_native.py:16-27`): `psycopg.pq.version() ≥ 160000` (`LIBPQ16_REQUIRED`); refused if
  the environment holds any `PG*` name, `C3PO_CAUSAL_EMITTER_DSN`, `C3PO_DATABASE_URL` or `C3PO_R2D2_RISK_DATABASE_URL`
  (`EMITTER_ENVIRONMENT_NOT_CLEAN`); password from `/c3po-k9-emitter/password` (private regular file of euid, one link,
  ≤ 1 KiB, one optional trailing newline, printable ASCII without space, else `INPUT_FILE_NOT_PRIVATE` /
  `EMITTER_PASSWORD_INVALID`); `psycopg.connect(host='db', port=5432, dbname='c3po', user='c3po_v2_causal_emitter',
  password=…, require_auth='scram-sha-256', options='', autocommit=False, connect_timeout=10)`; each connection checks
  `(current_database, current_user, session_user, session_replication_role) = ('c3po', role, role, 'origin')`
  (`EMITTER_IDENTITY_MISMATCH`). The emitter checks its own restrictions on every connection (`causal_emitter.py:79-128`).
- Calls `PostgresCausalListEmitter(factory, ShadowCalendar(), enabled=True).build(epoch=EPOCH, day=D, registry_bytes,
  daily_bytes)` (`:213-251`; confirmation inside). Checks the returned commitment's epoch, session and input hashes.
- Outputs: `day/causal/commitment.private.json` = `canonical(commitment)` as build returned it (its SHA-256 is the
  emitter's `commitment_sha256`; K8 reads it by fixed path), `day/causal/build_audit_receipt.json` =
  `canonical(audit_receipt)` (its SHA-256 = `audit_receipt_sha256`). `list_sha256`, `n_cut`, `built_at`, `cutoff_at`,
  `decision_at` are inside the hashed commitment file.
- Counts: `n_cut commit_confirmed`; `commitment_counts{registry_rows filtered_symbols liquidity_passed selected_symbols}`;
  `exclusion_reasons{data_ineligible classification_excluded close_below_5 adv_below_15000000 n_cut_excluded
  not_in_causal_list other_reasons}`; `list_coverage{coverage_numerator coverage_denominator}`.

### publish_launch (causal_list; DATABASE; T, Dd, Src rw, Em; no env file)
- Pred `commit_launch`; pred bytes of the commitment file. `/c3po-source` must be private.
- `relay/` created 0700; `.publish(epoch, D, sink=FileRelaySink(/c3po-k9-day/relay))` (`:253-303`); the envelope's
  commitment must be byte-equal to the committed file (`COMMITMENT_CHANGED`); `write_private_envelope(/c3po-source, env)`
  (`causal_files.py:141-153`); database clock; `FileShadowSource(/c3po-source, causal_receipt_verifier=
  ConfirmedCausalReceiptVerifier(factory)).causal_list(EPOCH, D, clock, ShadowCalendar())` must be `AVAILABLE`, no
  diagnostics, same commitment hash (`CAUSAL_READBACK_REFUSED`); names 1–550, unique, symbol grammar (`LIST_INVALID`).
- Writes `control/symbols.txt` (names, one per line, trailing newline) and `causal/publication_receipt.json`
  (`canonical(publication_receipt)`), exclusive or identical (`OUTPUT_CONFLICT`).
- Outputs: those two, `source/causal_list/<EPOCH>/<D>.json`, `day/relay/causal_publications/<EPOCH>/<D>.json`.
- Counts: `selected_count readback_available channel_relay`.

### components_launch (components; PROVIDER; T, Dd, Src rw; provider.env)
- Producers switch; pred `commit_launch` and `publish_launch`; pred bytes of the commitment and of `symbols.txt`; the
  names must equal the commitment's `list` (`LIST_NOT_THE_COMMITTED_ONE`); `inputs/registry.json` must hash to the
  commitment's `registry_sha256` (`REGISTRY_NOT_THE_COMMITTED_ONE`); `components/<D>/` created exclusively.
- Writes `components/<D>/registry.json` (the committed bytes); `produce_instrument_components(fetch, names,
  session_date=D, output_dir=/c3po-source/components/<D>)` (`:585-600`); `produce_earnings(fetch, names,
  session_date=D, output_dir=…)` without `live_symbols` (`producer_earnings.py:314-351`).
- Outputs: `source/components/<D>/registry.json`, `…/earnings.json`; aggregate `source/components/<D>/daily_61` =
  `{files, sha256 of the canonical JSON list of the sorted SHA-256 of every regular file}` (K9R's rule), checked equal
  to the producer's returned hashes and to the number of names.
- Counts: `daily_components{component_symbols incomplete_components}`; `earnings_counts{earnings_symbols live_symbols
  covered_symbols with_events excluded_symbols earnings_within_horizon earnings_expected_within_horizon
  earnings_not_tracked earnings_last_report_unknown earnings_evidence_invalid earnings_source_unavailable}`;
  `logical_fetch_calls`.

### sources_launch (sources; DATABASE_AND_PROVIDER; T, Dd; provider.env, risk-db.env)
Port of E28 `bound-package-rev3/operations/sources.py` `acquire()` + `official_reader()`, without E28's plan/GO/owner
documents (authority is the Act B order; N-13) and without its maintenance pin.
- Pred `publish_launch`; names from `symbols.txt` (pred bytes) in E28's grammar `[A-Z][A-Z0-9.-]{0,14}`, not `.SA`.
- `fstatvfs(/c3po-k9-day)`: `f_bavail × f_frsize ≥ 214748364800` else `DISK_FREE_BELOW_FLOOR`.
- `risk/` (0700), `risk/plan/` and `risk/plan/sources/` created exclusively (`OUTPUT_ALREADY_PRESENT`).
- Official reader: DSN from `C3PO_R2D2_RISK_DATABASE_URL` (`RESTRICTED_DSN_REQUIRED`); `psycopg.connect(dsn,
  connect_timeout=15, options='-c default_transaction_read_only=on')`, `REPEATABLE READ READ ONLY`, 15 s statement
  timeout; `ReadOnlyInsiderDatabaseReader.ROLE_SQL` must give role `c3po_v2_risk_reader` restricted
  (`ROLE_NOT_RESTRICTED`), `ACL_SQL` on `ir_events` and `analysis_snapshots` (`ACL_NOT_RESTRICTED`), read-only
  repeatable read confirmed (`TRANSACTION_NOT_READONLY_REPEATABLE`); the latest `official_fundamentals` snapshot per
  `US:<name>`, published ≤ the database clock.
- Providers: `RiskAcquirer` (`R/r2d2_v2_risk_acquisition.py:74`) over `BoundedRiskTransport(credentials {eodhd, fmp},
  max_requests=2000, requests_per_minute=60, timeout=15)` (`R/r2d2_v2_risk_transport.py:36`), paced 50 per 61 s, ≤ 2,000
  requests, ≤ 1 GiB of bodies (`REQUEST_BUDGET`, `BODY_BUDGET` — also checked before each further request —,
  `PROVIDER_NOT_ALLOWED`; all `BaseException`, M2: the loop stops at the first, tested with lowered limits:
  5 requests → exactly 5 HTTP calls; 10 bytes → exactly 1); per name fundamentals, grades,
  institutional of `FmpClient.latest_reportable_13f_quarter(today)` (`R/market_data/fmp.py:267`).
- Writes (directories 0700, files 0600, ≤ 1 GiB in all, `SPOOL_BUDGET`), straight into the risk plan directory (F14):
  `sources/database.READONLY.json`, `sources/%04d.official.json`, `sources/%04d.<method>.body`,
  `sources/%04d.<method>.receipt.json` (index-named: no symbol in any file name), `sources/census.json`,
  `sources/timings.json`, `risk-input-names.private.json` = `{namespace: R2D2-V2-DIAG-R4-<D>, session_date: D,
  symbols: [names]}` (N-1, the packaged `admission` field; not an admission in ORD:16's sense, N-14), and
  `replay.private.json` (`V2_RISK_REPLAY_MANIFEST_V1`, namespace DIAG-R4, `phase_pending` 0, `admission` = the names
  document's reference, entries in list order with `official`/`fundamentals`/`grades`/`institutional` references relative
  to `risk/plan/`).
- Outputs: `day/risk/plan/{replay.private.json, risk-input-names.private.json, sources/census.json,
  sources/timings.json, sources/database.READONLY.json}` (per-name blobs are re-read by hash by the packaged executor).
- Counts: `list_symbols complete_symbols failed_symbols http_attempts http_kib bytes_written_kib database_rows
  database_readonly role_verified elapsed_seconds`; `fundamentals_fetch`, `grades_fetch`, `institutional_fetch` each
  `{fetch_ok http_failed transport_failed body_rejected json_invalid other_failure}`.

### bind (risk; NONE; T, Dd; ATTACHED, 30 s)
- `plan.risk.namespace` = `R2D2-V2-DIAG-R4-<D>` (`NAMESPACE_NOT_THE_DECIDED_ONE`, N-1).
- `phase_windows` exactly preflight/acquire/execute each `{not_before, not_after}`, `not_before < not_after`;
  `cutoff_at ≤` acquire's and execute's `not_before`; every instant in `[D−1 00:00Z, D 13:30Z]` (`RISK_WINDOWS_INVALID`).
  The binder fixes the grid values (NOTE §5.3/5.4); the executor checks `cutoff_at ≤ now` and the windows itself.
- `owner_order_text` (ASCII) hashes to `owner_order_sha256` (`OWNER_ORDER_NOT_THE_SIGNED_BYTES`); parsed, it has
  `schema R2D2_V2_RISK_HOST_ORDER_V1`, `scope = {namespace, session_date: D, cutoff_at: plan.risk.cutoff_at (the same
  string), phases: [preflight, acquire, execute]}` and the three actions (`OWNER_ORDER_SCOPE_MISMATCH`) — exactly what
  `risk_host_executor.py:163-166` requires. `OWNER_ORDER.json` is written with these exact bytes.
- Pred `sources_launch` and `publish_launch`; pred bytes of the replay and names document; replay namespace/session/
  `phase_pending`/admission reference and `[(symbol, US)]` = the published names in order (`REPLAY_NOT_OF_THIS_LIST`);
  names document = `{namespace, session_date, symbols}` exactly (`NAMES_DOCUMENT_NOT_OF_THIS_LIST`).
- `SOURCE_PINS.json` = the pins bytes computed and checked at step 5 of §2 (canonical JSON + `\n` of
  `{"schema":"RISK_HOST_SOURCE_PINS_V1","files":{"app/<rel>.py":sha256}}` over every `/app/app/**/*.py`); then the
  packaged `_source_pins(/app, pins)` closure check. **Value for dd4ec4bb,
  computed offline from the tar's 190 members and from the export tree (equal):
  `faaa35a7905076231f1847616c600968193c69ce064b6bd1db9cdbd6b77852bb`.**
- `list.private.json` = `{namespace, session_date, symbols: [{symbol, market: US}]}`.
- `HOST_PLAN.json` (`R2D2_V2_RISK_HOST_PLAN_V1`): namespace, session_date, cutoff_at, phase_windows (the signed values),
  `limits` = E28's five, `runtime_source_root` `/app`, `spool_root` `/c3po-k9-day/risk/spool`, references
  `source_pins`, `owner_order`, `list`, `admission` (the names document), `replay_manifest`, and
  `sources_receipt_sha256` (the sources RECEIPT bytes).
- `GO.json` (Fable's `R2D2_V2_RISK_HOST_GO_V1`, N-9): `verdict GO`, `scope RISK_ARTIFACT_ONLY`, `issuer FABLE`,
  `binding` = `{manifest_sha256 (HOST_PLAN bytes), owner_order_sha256, source_pins_sha256, list_sha256,
  admission_sha256, namespace, session_date, cutoff_at, phases, phase_windows}` — exactly the object
  `risk_host_executor.py:167-172` recomputes — plus `k9_bind_request_sha256` (= plan `request_sha256`) and
  `k9_attempt_key`. Every value is a signed bind value or a hash of bytes bind wrote; nothing from the evening's runtime
  except the sources/publish receipts' files, checked above.
- Writes the five files exclusively (`OUTPUT_ALREADY_PRESENT` if any, or `risk/spool`, exists), then `risk/spool/`
  (0700). Clones nothing (F14).
- Outputs: `day/risk/plan/{HOST_PLAN.json, GO.json, OWNER_ORDER.json, SOURCE_PINS.json, list.private.json,
  replay.private.json, risk-input-names.private.json}`. K9W takes the plan and GO hashes for preflight from here.
- Counts: `list_symbols source_pins_files`.
- Not done in bind (time): the packaged `_validate` re-read of every blob; preflight does it 9 minutes later.

### stage (risk; NONE; T, Dd ro, Src rw; ATTACHED, 15 s) — standard library plus the package check only
- Pred `publish_launch` (names) and pred `bind`: `risk/plan/HOST_PLAN.json` and `GO.json` are pred bytes of bind's
  RECEIPT (`PREDECESSOR_OUTPUT_CHANGED` if they differ from what bind wrote); `m = sha256(HOST_PLAN)`;
  `risk/spool/<m>/execute.FAILED.json` absent; `execute.RECEIPT.json` (`R2D2_V2_RISK_HOST_PHASE_RECEIPT_V1`, phase
  execute, COMPLETE, manifest = m, GO = sha256(GO.json), session D, namespace **`R2D2-V2-DIAG-R4-<D>` only**, N-1) —
  else `PREDECESSOR_NOT_COMPLETE`.
- `risk-output/MANIFEST.json` and `risk.json` re-hashed against `output_manifest_sha256`/`risk_sha256` and the manifest's
  own entry (`RISK_OUTPUT_NOT_AS_THE_RECEIPT_SAYS`); `risk.json` is `V2_RISK_COMPONENTS_V1` of D whose names = the
  published list (`RISK_NAMES_NOT_THE_LIST`).
- Exclusive-creates `components/<D>/risk.json` (creating `components/<D>/` 0700 if absent; `OUTPUT_ALREADY_PRESENT`).
- Outputs: `source/components/<D>/risk.json` (= `risk_sha256`). Counts: `list_symbols risk_staged ready_symbols
  completed_null`.
- **Mount contract (deviation from NOTE 3.3):** the note mounts Dd read-only for stage, but the runner's receipts live
  in `Dd/receipts`. K9W must add a fourth mount: `<k9_root>/days/<D>/receipts` → `/c3po-k9-day/receipts` **rw** over the
  read-only Dd (the runner opens `receipts/` before trying to create it). The alternative is Dd rw for stage.

### capture_launch (capture; PROVIDER; T, Dd, Src rw; provider.env)
- Producers switch (the packaged `main` would otherwise print `OFF` and return 0); pred `publish_launch` of the eve and
  pred bytes of `source/causal_list/<EPOCH>/<D>.json` (components and risk may be absent: they publish as PENDING).
- Calls the packaged `r2d2_v2_producer_snapshot.main(['--epoch', EPOCH, '--session-date', D, '--root',
  '/c3po-source'])` (`:461-495`) with its stdout captured in memory; its one summary line parsed.
  `rc ≠ 0` or status ≠ `CAPTURED` → `FAILED CAPTURE_NOT_CAPTURED` (with counts); a closed window →
  `CAPTURE_WINDOW_ALREADY_CLOSED`.
- Outputs: `source/snapshot.json` (the last publication), `source/tape/<D>.us-quote.ndjson`.
- Counts: `capture_complete consumer_failed snapshot_publications quoted_symbols list_symbols`;
  `rejected_ticks{payload_error not_json not_object symbol_not_listed tick_clock_invalid tick_in_future tick_regresses
  other_reason}`; `component_diagnostics{daily_component_absent daily_document_invalid daily_component_invalid
  risk_component_absent risk_document_invalid risk_component_invalid earnings_component_absent earnings_document_invalid
  earnings_component_invalid registry_row_absent other_diagnostic}`.
- Deadline: `run_not_after` 14:03:00Z → stop 14:02:00Z, after the window's 14:01:00Z close.

## 4. Closed sets (for K9R's allow-lists)

**Count keys per operation**: exactly the sets listed under "Counts" in §3 (every listed key is always present; an
integer 0..10^7; one nested level only where shown). Producer code-keyed dictionaries are mapped to the listed lower-case
names, everything else summed into the `other_*` key — no provider string, path or symbol can become a key. The same
sets are `EXPECTED_COUNTS` in `tests/test_runner.py`, asserted on every COMPLETE receipt and checked against K9R's
`K9_COUNT_KEY`.

**Failure codes** (`code` of a FAILED file) — the union of:
- the runner's own (60): `ACL_NOT_RESTRICTED AGGREGATE_NOT_REGULAR BODY_BUDGET BUILD_SHA_NOT_THE_PINNED_ONE
  CAPTURE_NOT_CAPTURED CAPTURE_SUMMARY_INVALID CAUSAL_READBACK_REFUSED COMMITMENT_CHANGED COMMITMENT_NOT_OF_THIS_STEP
  COMMIT_AFTER_ITS_LATEST_START CONSTANTS_NOT_THE_COMPILED_ONES DATABASE_NOT_OF_THIS_OPERATION DIRECTORY_NOT_PRIVATE
  DISK_FREE_BELOW_FLOOR EMITTER_ENVIRONMENT_NOT_CLEAN EMITTER_IDENTITY_MISMATCH EMITTER_PASSWORD_INVALID INPUT_CHANGED
  INPUT_FILE_INVALID INPUT_FILE_NOT_PRIVATE LIBPQ16_REQUIRED LIST_INVALID LIST_NOT_THE_COMMITTED_ONE
  NAMESPACE_NOT_THE_DECIDED_ONE NAMES_DOCUMENT_NOT_OF_THIS_LIST NETWORK_CLASS_NOT_OF_THIS_OPERATION OUTPUT_ALREADY_PRESENT
  OUTPUT_CHANGED OUTPUT_CONFLICT OWNER_ORDER_INVALID OWNER_ORDER_NOT_THE_SIGNED_BYTES OWNER_ORDER_SCOPE_MISMATCH
  PACKAGE_NOT_THE_CERTIFIED_ONE PACKAGE_UNAVAILABLE PATH_INVALID PLAN_INVALID PREDECESSOR_NOT_COMPLETE
  PREDECESSOR_OUTPUT_ABSENT PREDECESSOR_OUTPUT_CHANGED PRODUCERS_NOT_ENABLED PROVIDER_NOT_ALLOWED RECEIPT_COUNT
  RECEIPT_GRAMMAR REGISTRY_NOT_THE_COMMITTED_ONE REPLAY_NOT_OF_THIS_LIST REQUEST_BUDGET RESTRICTED_DSN_REQUIRED
  RISK_NAMES_NOT_THE_LIST RISK_OUTPUT_NOT_AS_THE_RECEIPT_SAYS RISK_WINDOWS_INVALID ROLE_NOT_RESTRICTED
  RUNNER_NOT_THE_SIGNED_ONE RUN_NOT_AFTER_PASSED SOURCE_INTEGRITY SOURCE_PINS_NOT_THE_SIGNED_ONES SPOOL_BUDGET
  TRANSACTION_NOT_READONLY_REPEATABLE` (`ARGUMENTS_INVALID`, `PLAN_HASH_MISMATCH`, `PLAN_IDENTITY_INVALID` exist in the
  source but never reach a file: exit 2);
- `RUN_NOT_AFTER_REACHED` (status `DEADLINE`);
- release codes passed through when an exception's first `:`-token is exactly one of `PASS` (76, in the source:
  producer, emitter, causal list/files, calendar, source-pin, transport-budget codes, e.g. `PROVIDER_REQUEST_FAILED`,
  `PREVIOUS_SESSION_NOT_CLOSED`, `CAUSAL_SLOT_INPUT_CONFLICT`, `CAUSAL_PUBLICATION_LATE`, `CAPTURE_WINDOW_ALREADY_CLOSED`);
- five categories for anything else: `PRODUCER_FAILED` (ProducerError), `CAUSAL_INTEGRITY_FAILED`
  (ShadowIntegrityError), `SOURCE_UNAVAILABLE`, `DATABASE_FAILURE` (any psycopg exception), `FILESYSTEM_FAILURE`
  (OSError), `UNCLASSIFIED_FAILURE`. No exception text, class name, URL or symbol is ever written.
Every code matches K9R's `K9_CONSTANT_CODE` (tested).

## 5. What is proven, emulated, unproven

- **Executed here** against the release's own modules (export of dd4ec4bb, CPython 3.12.14 venv with the release's
  libraries): the whole eve and morning chain collect → commit → publish → components → sources → bind → **packaged
  preflight, acquire, execute** (`run_host_phase`, the CLI's function, with the real `runtime_dependencies`) → stage →
  capture (packaged `main`, real asyncio loop), all COMPLETE; the packaged executor accepted bind's HOST_PLAN, GO, owner
  order, pins, list, admission and replay. Every refusal of §3, deadline (provider loop and capture), package mismatch and
  absence, build mismatch, exclusive-create collisions (STARTED/RECEIPT/FAILED present, a link at the marker),
  non-private receipts directory, plan identity refusals (nothing written). Rev 2 adds: the source-pins refusal for six
  operations with a byte changed in the emitter (package zeros in the receipt: nothing imported from `app`; no provider,
  database or HTTP call), the package check on a tree whose pins are signed, the runner file name/content rule, a
  40-second provider call interrupted by the deadline (run ends in < 20 s, one call, `logical_fetch_calls: 1` kept),
  the loop deadline keeping its counts, both budget stops ending the sources loop, stage refusing a GO changed after
  bind, a missing bind receipt and the SHADOW namespace. **96 tests**, `TESTS.py312.txt`; every run executes the file
  under its hash name. The tests read `K9_RELEASE_TREE` (the export's `c3po/backend`), `K9_TEST_PYTHON`,
  `K9_TEST_WORK` (sandboxes, outside this directory) and `K9R_ASSEMBLED`; without the release tree they skip.
- **Emulated** (stand-ins, `tests/harness.py`): the EODHD REST API (`httpx.get`; the real httpx transports are replaced by
  a function that fails the test), the database (a JSON file behind a `psycopg` stand-in that answers the emitter's and the
  readers' exact statements), the EODHD/FMP/Finnhub HTTPS opener of `BoundedRiskTransport`, the us-quote websocket, the
  clock (a shifted `datetime.now`), Docker, mounts, uid 0, the stage read-only mount.
- **Unproven**: K9-R1 the container itself (busybox `timeout`, `--read-only`, `--cap-drop ALL`, no writable `/tmp`:
  the runner writes no temporary outside its mounts; the release code's own imports on a read-only root are unproven,
  N-7); K9-R2 libpq ≥ 16 in the image's psycopg binary (refused otherwise); K9-R3 the real role, ACLs, triggers and
  password of `c3po_v2_causal_emitter` and `c3po_v2_risk_reader`; K9-R4 provider payloads at real size (the 30 MB daily
  contract, 550 names: durations of E28's F12 are the only figures) and the 2,000-request/1 GiB budgets under the 75-min
  ceiling; K9-R5 that the image's `/app/app` equals the tar (bind refuses otherwise: `SOURCE_PINS_NOT_THE_SIGNED_ONES`);
  K9-R6 the nested rw `receipts` mount for stage (§3); K9-R7 a deadline that fires while the collect fallback's thread
  pool is inside an HTTP call: the pool's shutdown waits for in-flight calls (≤ 3 × 15 s plus back-off), possibly past
  K9W's KILL → STARTED without receipt → K9R UNCERTAIN (same outcome class as DEADLINE); K9-R8 the Linux-root job.

## 6. Contracts this file imposes on others

1. K9W writes `K9_STEP_PLAN_V1` exactly as §1 and passes `--plan-sha256`; gives each operation its env files/mounts per
   NOTE §3.3 (commit/publish: **no** env file — a DSN there is refused); `--env C3PO_BUILD_SHA=dd4ec4bb…` and
   `--env C3PO_R2D2_V2_PRODUCERS_ENABLED=true` on every runner container.
2. `run_not_after` in every step plan: LAUNCH = the note's value (window end + ceiling; capture 14:03:00Z); ATTACHED = any
   instant ≥ the send (the runner caps bind at 30 s and stage at 15 s anyway).
3. For bind and stage K9W reads the one stdout line (the terminal receipt bytes); absence = exit 2/3 (nothing or no
   terminal file written).
4. Stage: the rw `receipts` mount over the ro Dd (§3).
5. K9W passes preflight `--manifest-sha256`/`--go-sha256` from bind's RECEIPT `outputs` (`day/risk/plan/HOST_PLAN.json`,
   `…/GO.json`).
6. The binder signs `constants.risk_source_pins_sha256 = faaa35a7…52bb` and, for bind, `risk` built from the grid
   (cutoff/windows) with the owner order's exact bytes on the sheet.
7. K9R's RESULT already reads these files; its allow-lists may take §4 verbatim.

## 7. Documented, not changed (review items 3, 5, 9, 10)

- **(3) Timeouts per phase.** collect/components/capture-free fetches: the packaged `EodhdFetcher` with the settings'
  15 s per HTTP call and 2 retries with 0.5 s / 1 s back-off, so one logical call can last ≈ 46.5 s; collect's fallback
  uses up to 8 threads. Sources: `BoundedRiskTransport` 15 s per call (its own read deadline), no retry, pacing sleeps
  up to 61 s. Emitter: `connect_timeout=10` per connection, no statement timeout (the emitter's own transactions);
  restricted reader: `connect_timeout=15`, `statement_timeout 15s`. Capture: the packaged websocket loop (10 s
  authorization wait, 1 s receive slices). Every one of these is bounded overall only by the runner's deadline (§2.6).
- **(5) Write semantics of the release code the runner calls.** `write_private` (producers: `inputs/*`, `daily_61/*`,
  `earnings.json`, `snapshot.json`) writes a private temporary and `os.replace`s it: **not exclusive**, it overwrites;
  the runner therefore creates `inputs/` and `components/<D>/` exclusively first so nothing pre-existing can be
  overwritten. A crash can leave a `.<name>.tmp` file, which K9R's aggregate of `daily_61` would see (not a regular
  output → OUTPUT_NOT_AS_THE_RECEIPT_SAYS). `_atomic_bytes` (relay, envelope) links exclusively and accepts identical
  bytes (idempotent). The snapshot is replaced about once a second until 10:01 New York; the tape is appended
  (`O_APPEND`, not exclusive). The packaged risk executor writes its spool by exclusive link.
- **(9) Link/unlink window of the runner's own files.** `put()` writes `.k9-<random>`, links it to the final name, then
  unlinks the temporary: between link and unlink the final file has two links. A crash in that window leaves the
  temporary in `receipts/` and the final file with `st_nlink == 2`; K9R's `k9_private` then reports
  `STEP_FILE_NOT_PRIVATE` (a metadata finding: exit 2, the phase decision unchanged). The file's bytes are complete
  either way (written and fsynced before the link).
- **(10)** The review message named an item 10 among those to document but did not describe it; it is not addressed
  here.
