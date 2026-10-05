# K9W — the write program of the delegated daily phases (HOSTOPS02): design, revision 2

**Revision 2 (2026-10-04): Codex's decision 6 (#429 comment 5985748037)** rejects the residual source-root swap of revision 1 (K9W-R1) and changes the placement: `source_root` = `/var/lib/c3po/r2d2-v2-source-20261005`, under the same root-only chain as the K9 tree (no open root anywhere, every component uid 0, gid 0, not writable by group or other, no setgid; the leaf 0:0 0700), on the filesystem of `days/`. Every bind source and all its ancestors are root-controlled, or the run refuses: from the bytes (`validate_plan`: the five chains with no open root, gid 0, no setgid, leaves 0:0 0700, `SOURCE_ROOT_NOT_ON_THE_FILESYSTEM_OF_DAYS` from the signed devices) and on the host (the chains walked against the signed rows; the source root held on days/' device; before any effect every bind source of the step held and itself uid 0, gid 0, not group/other-writable, not setgid, on days/' device — `MOUNT_SOURCE_NOT_ROOT_CONTROLLED`). No other account can rename or replace a directory a container binds, so the swap is closed by placement; the re-proof of the mounts around start stays as defence in depth. Revision 1 is kept sealed beside this directory as `../k9_phase_step.rev1-165330a6` (its SUMMARY as `../SUMMARY.rev1-165330a6.md`). The placement object is K9R rev 4's byte for byte (`source_open_root` null; `decision_6`; `september_open_root` for K3-K9 only). The runner hash is compiled once (`K9W_RUNNER_SHA256` = `563a4797ab2a7ef4c02a1c1937061a2644420b69bdcc2dca842cd1efd7fb7690`, runner rev 2, 40,618 bytes) and `constants.runner_sha256` must equal it (`RUNNER_NOT_THE_COMPILED_ONE`); a new runner is a one-line change and a reseal.

Offline work only. Nothing here was run on the host, pushed, bound or dispatched. Every hash is taken by command (`SHA256SUMS`, `../SUMMARY.md`).
Built on the frozen core generation `4c24c5cf…d0d6` (`CORE_SHA256SUMS` `73fb546b…`; reached through the link `../core` → `../hostops02-sealed/core`, never edited; no new generation).
Specified by `K9_INTERFACE_NOTE.md` revision 2 (`ab5159be…596c`) sections 1 (F5, F10, F13, F14), 2, 3.1–3.3, 4.1–4.3, 5; placement by Codex's N-8 decision (`W/codex-n8-placement-20261004.txt`, `d30f7f90…2c53`) amended by decision 6 (source root); Codex's #429 answers N-1 (DIAG-R4 namespace), N-3 (no `--rm`, removal rule, removal-only), N-9 (the risk GO derived from the signed bind); the ACL-by-mode and the space floor (200 GiB = `f_bavail*f_frsize` of `fstatvfs` on `days/`). Contracts shared with the read program K9R (`W/fable-k9r-20261004/k9_phase_read`, DESIGN.md §5, rev 3 in progress) and with the runner (`W/fable-k9runner-20261004/k9_runner.py`, sha256 `b5950b99188c84266fc1c440c72b10b4b1fda353e1bf592f448bcdb2c54efc40`, 39,972 bytes; its DESIGN.md §1 and §6).

`W` = the work tree that holds this family's parent directory (`../..` from here; the tests find the external inputs there and skip cleanly when they are absent); `NOTE` = the K9 note; `D` = the session the eve prepares; `Dd` = `<k9_root>/days/<D>`.

## 1. What it is

One writing source (`WRITES_ALLOWED=True`, `ACTIVATION_ALLOWED=False`), date class `WRITE_SESSIONS` (2026-10-05…10 UTC), gate ≤ 900 s, parts `core runner docker parents files`, `EVIDENCE_OPERATIONS=('GO_READONLY_HOSTOPS02_K9_PHASE_READ_01',)` (the TREE receipt the rows come from). One request = one of the twelve WRITE operations of `K9_OPERATIONS.json`; the mode follows the operation:

| Mode | Operations | Effects (in order) | Success outcome (exit 0) |
|---|---|---|---|
| LAUNCH | collect, commit, publish, components, sources, acquire, execute, capture (`*_launch`) | claim → `docker rm` of the previous step's exited container (if the table names one and it exists) → (collect only) `days/<D>` + `plans` `launches` `receipts` → step plan → `docker create` → mounts proved again → `docker start` → launch record | `K9_STEP_LAUNCHED_DETACHED_READ_BACK` |
| ATTACHED | bind, preflight, stage | claim → (stage) `docker rm` → step plan → mounts proved again → one `docker run --rm` → its receipt read back | `K9_STEP_RAN_ATTACHED_RECEIPT_COMPLETE` |
| CLEANUP | capture_cleanup | claim → `docker rm` of the exited capture container | `K9_CONTAINER_REMOVED_READ_BACK` |

Exit 2: `K9_REMOVAL_ONLY_PREDECESSOR_NOT_COMPLETE` (removal-only, section 4), `K9_STEP_RAN_NOT_COMPLETE` (an attached step ran and its receipt is not COMPLETE), `K9_STEP_PARTIAL_REQUIRES_REVIEW` (anything else after the claim). Exit 1 `REFUSED_NOTHING_CHANGED`: nothing was created (no claim). A LAUNCH's exit 0 says the container was launched as built; whether the step itself completed is the RESULT read of K9R.

## 2. Every argv (fixed words of the rows, then the middle K9W's own builder makes)

Rows (`COMMANDS`, in the signed scope):

| Row | Kind / class | Fixed words | Middle |
|---|---|---|---|
| `image` | READ / QUICK | `image inspect --format <core IMAGE_FORMAT>` | the signed image ID |
| `launched` | READ / QUICK | `container inspect --format <K9W_LAUNCHED_FORMAT>` (K9R's `K9_LAUNCHED_FORMAT` byte for byte, tested) | one 64-hex ID |
| `container_list` | READ / QUICK | `ps -a --no-trunc --format <core PS_FORMAT>` | — |
| `create` | EFFECT / QUICK (8 s) | `create --pull never --init --user 0:0 --read-only --cap-drop ALL --security-opt no-new-privileges --restart no` | builder |
| `start` | EFFECT / RUN_SHORT (20 s) | `start` | the ID create printed |
| `remove` | EFFECT / QUICK | `rm` | exactly one 64-hex ID (no `-f`, no `-v`) |
| `attached` | EFFECT / RUN (40 s) | the core's `RUN_PREFIX` (`run --rm -i --pull never --init --user 0:0 --network none --read-only --cap-drop ALL --security-opt no-new-privileges`) | builder |
| `attached_short` | EFFECT / RUN_SHORT | the same | builder |

The builder (`k9w_container_arguments`, NOTE F5) — `--name c3po-k9-<yyyymmdd>-<operation>`, `--label c3po.k9.attempt_key=<attempt key>`, `--label c3po.k9.request_sha256=<this request>`, `--network <class>` (create rows only; `none` for NONE, the signed network names otherwise), `--env-file` per the table, `--env C3PO_R2D2_V2_PRODUCERS_ENABLED=true`, `--env C3PO_BUILD_SHA=dd4ec4bb…`, the table's `--mount`s (the core's `mount_argument`), the signed image ID, then the command. Every word in the core's run grammar, ≤ 64 words (`MAX_ARGUMENTS`; the largest, acquire, is 41). The argvs, as `effects.step.argv` shows them to the signers (`<…>` = run-time values):

```
collect_launch     create … --name c3po-k9-<D>-collect_launch --label c3po.k9.attempt_key=<key> --label c3po.k9.request_sha256=<request> --network bridge
                   --env-file <k9_root>/secrets/provider.env --env C3PO_R2D2_V2_PRODUCERS_ENABLED=true --env C3PO_BUILD_SHA=dd4ec4bb…
                   --mount type=bind,source=<k9_root>/tools,target=/c3po-k9-tools,readonly --mount type=bind,source=<k9_root>/days/<D>,target=/c3po-k9-day
                   <image_id> timeout -s KILL <n> python -I /c3po-k9-tools/k9_runner-<runner_sha256>.py --plan /c3po-k9-day/plans/collect_launch.json --plan-sha256 <plan>
commit_launch      network <DATABASE>, no env file, mounts tools(ro) day(rw) <k9_root>/secrets/emitter→/c3po-k9-emitter(ro); runner command
publish_launch     network <DATABASE>, no env file, mounts tools day <source_root>→/c3po-source(rw) emitter(ro); runner command
components_launch  network bridge, provider.env, mounts tools day source(rw); runner command
sources_launch     network <DATABASE_AND_PROVIDER>, provider.env + risk-db.env, mounts tools day (NOT the source root); runner command
bind               run --rm … (network none) --name/--label/--env as above, mounts tools day; timeout -s KILL 35 python -I …/k9_runner-<sha>.py --plan /c3po-k9-day/plans/bind.json --plan-sha256 <plan>
preflight          run --rm …, mount day; timeout -s KILL 35 python -m app.r2d2_v2_risk_host_executor preflight --manifest /c3po-k9-day/risk/plan/HOST_PLAN.json
                   --manifest-sha256 <HOST_PLAN> --go /c3po-k9-day/risk/plan/GO.json --go-sha256 <GO> --source-root /app --spool-root /c3po-k9-day/risk/spool
acquire_launch     create …, network <DATABASE_AND_PROVIDER>, provider.env + risk-db.env, mount day; the packaged CLI `acquire` as above + --previous-receipt-sha256 <preflight receipt>
execute_launch     create …, network none, mount day; the packaged CLI `execute` + --previous-receipt-sha256 <acquire receipt>
stage              run --rm …, mounts tools(ro), day(RO), day/receipts→/c3po-k9-day/receipts(rw, nested), source(rw); timeout -s KILL 18 … --plan /c3po-k9-day/plans/stage.json …
capture_launch     create …, network bridge, provider.env, mounts tools day source(rw); runner command
capture_cleanup    rm <the ID of launches/capture_launch.json>
```

`<n>` of a LAUNCH = `run_not_after − now at create − 5 s`, capped at `ceiling + 900 s` except for capture (whose `run_not_after` is the fixed 14:03Z), and ≥ 90 s (above the runner's own stop, 60 s before `run_not_after`) (section 8, deviation 3). The packaged CLI runs `python -m` without `-I` (the module needs `/app`, its WORKDIR, on `sys.path`; NOTE 3.1). `python -I` for the runner (as the user and the runner's usage line say; no `-B`: the root is read-only and the runner imports nothing from a writable path).

Step table (compiled; its canonical hash `K9W_STEP_TABLE_SHA256` is the signed `constants.step_table_sha256`, compared): ceilings collect 900, commit 600, publish 600, components 2400, sources 4500, acquire 3600, execute 1200, capture 780 s; attached limits bind 35, preflight 35, stage 18 s; the removal map of NOTE 3.2 (commit→collect, publish→commit, components→publish, sources→components, acquire→sources, execute→acquire, stage→execute, cleanup→capture).

## 3. Order of a run and the budget

1. Pure: the window of D (`k9w_window_of`, section 6.2) — after the executor identity, before anything is observed; umask 0077.
2. Boot = the evidence's (`EVIDENCE_FROM_EARLIER_BOOT`).
3. The five chains walked from `/` against the signed rows and held (`days`, `claims`, `tools`, `secrets`, `source_root`).
4. The claim `<k9_root>/claims/<attempt_key>.claim` absent (`CLAIM_EXISTS`).
5. `days/<D>`: absent, or held and 0:0 0700 on days' device with `plans`, `launches`, `receipts` 0:0 0700 (`DAY_DIRECTORY_NOT_PRIVATE`, `DAY_LAYOUT_INVALID`).
6. `docker ps -a` (one READ).
7. The previous container (section 4).
8. The needs (section 5): collected, never raised.
9. FULL mode only: the image by ID with the revision label; no K9 container running/restarting/paused/removing; the step's own name free.
10. Budget: `gate() ≥ effects_budget(rows still to run) + 4 s` (`BUDGET_INSUFFICIENT`). The 4 s cover the files written between the first effect (the claim) and the last command. Figures: LAUNCH with removal 40+4 = 44 s (16 s left for 1–9), LAUNCH without 36 s, bind/preflight 48 s, stage 36 s, removal-only/cleanup 16 s. Every READ between the first and last effect is replaced by file reads: the readbacks of `rm`, `create` and `start` come after the last command (one `ps -a`, one `launched` inspect).
11. Effects, from here on nothing is a refusal (core rule 4): the claim (exclusive creation, read back) → … (table of section 1).

## 4. The removal rule (NOTE 3.2, N-3) and removal-only

The previous step's container is identified **only** by its launch record `Dd/launches/<previous>.json` (exact `K9_LAUNCH_RECORD_V1` keys, epoch, D, operation, attempt key, name, 64-hex ID, 0:0 0600 — `PREVIOUS_LAUNCH_RECORD_INVALID`), looked for in `ps -a` by ID (absent: nothing to remove), then inspected by ID with the launched format: name, image ID, both labels as recorded (`PREVIOUS_CONTAINER_NOT_AS_RECORDED`), state `exited` and not running — any other state is `UNCERTAIN_PREVIOUS_RUNNING` (a refusal: nothing is removed, the owner is told). `docker rm <ID>` only then. A container named like the previous step's with no record is never removed (reported). A failed `rm` stops the step (`PREVIOUS_CONTAINER_NOT_REMOVED`, settled by a listing: still listed after a non-zero status = nothing changed); a non-zero status with the container gone also stops a FULL step (`PREVIOUS_CONTAINER_REMOVAL_STATUS_NONZERO`), so no READ is left between effects.

**Withdrawal** (signed, `effects.step.withdrawal_argv`, counted in `containers_removed_at_most`): when a mounted directory is no longer the one held after `create`, the container this run created — never started — is removed by its ID and the step stops (`MOUNT_SOURCE_REPLACED_BEFORE_START`).

**HOLD needs** — `DISK_FREE_BELOW_FLOOR`, `ENV_FILE_NOT_PRIVATE`, `EMITTER_SECRET_NOT_PRIVATE`, `RUNNER_FILE_NOT_AS_REQUIRED` — are states of the host, not of the chain: they are plain refusals (no claim, no removal), so the attempt key is not spent and the same step can run once the condition is gone (Codex: HOLD below the floor).

**Removal-only** (NOTE 3.2): when any other need is not met (section 5) the run, if there is a removable container, makes its claim, removes it, reads the removal back and ends `PARTIAL / K9_REMOVAL_ONLY_PREDECESSOR_NOT_COMPLETE` with `code` = the first unmet need (`REFUSED_PREDECESSOR_NOT_COMPLETE` for a predecessor) and `needs_not_met`; if there is nothing to remove it refuses with that code and changes nothing. Removal-only is a subset of the signed effects (`effects.removal_only` says so).

## 5. Needs, by fixed path (all before the first effect)

| Need | Code |
|---|---|
| collect: `days/<D>` absent; others: present | `DAY_DIRECTORY_EXISTS` / `DAY_DIRECTORY_ABSENT` |
| runner predecessor COMPLETE: `plans/<p>.json` present (its hash computed), launch record (LAUNCH) with that plan hash, `receipts/<p>.STARTED.json` and `.RECEIPT.json` present, no `.FAILED.json`, both 0:0 0600, exact `K9_STEP_STARTED_V1`/`K9_STEP_RECEIPT_V1` keys and identity (epoch, D, phase, operation, attempt key, step plan hash), status COMPLETE, code null, package b5ce527a…, build dd4ec4bb…, `started ≤ completed ≤ now`, outputs/aggregates grammar, counts in constant snake keys (K9R rev 3's grammar); for the container this step removes: exit 0, not OOM | `REFUSED_PREDECESSOR_NOT_COMPLETE` |
| packaged predecessor COMPLETE: `risk/plan/HOST_PLAN.json` and `GO.json` hashed on the host, `risk/spool/<HOST_PLAN sha>/<phase>.STARTED/RECEIPT.json`, no FAILED, bound to that plan and GO, namespace `R2D2-V2-DIAG-R4-<D>`, session D, no activation, no certification; exit 0 of the removed container | `REFUSED_PREDECESSOR_NOT_COMPLETE` |
| destinations absent: commit `causal`; publish `relay`, `control`; components `source/components/<D>`; sources `risk`; bind the five plan documents and `risk/spool`; acquire/execute their spool files; preflight `spool/<manifest>`; stage `source/components/<D>/risk.json` | `DESTINATION_EXISTS` |
| inputs present: bind `risk/plan`, preflight `risk/spool`, stage `source/components/<D>` | `INPUT_DIRECTORY_ABSENT` |
| components, sources: `control/symbols.txt` hash = the publish receipt's | `SYMBOLS_NOT_AS_PUBLISHED` |
| preflight: HOST_PLAN/GO hashes = the bind receipt's outputs | `RISK_PLAN_NOT_AS_BOUND` |
| preflight/acquire/execute: now inside the plan's `phase_windows[phase]` | `RISK_PHASE_WINDOW_NOT_OPEN` |
| env files of the step: lstat only, regular, 0:0 0600, one link (never opened) | `ENV_FILE_NOT_PRIVATE` |
| commit, publish: `secrets/emitter` 0:0 0700, `password` regular 0:0 0600 (lstat) | `EMITTER_SECRET_NOT_PRIVATE` |
| runner steps: `tools/k9_runner-<runner_sha256>.py` regular 0:0 0600 (lstat; its bytes are TREE's) | `RUNNER_FILE_NOT_AS_REQUIRED` |
| `f_bavail*f_frsize` of `fstatvfs(days/)` ≥ 214,748,364,800 (HOLD below) | `DISK_FREE_BELOW_FLOOR` |

## 6. Refusals

### 6.1 `validate_plan` (pure; the dispatcher runs it before any claim)
`MODE_INVALID`, `EPOCH_INVALID`, `CONSTANTS_INVALID` (the 16 keys K9R signs; hashes, image ID, networks grammar, readiness rule grammar), `CONSTANTS_NOT_THE_COMPILED_ONES` (note, package, revision), `PLACEMENT_NOT_THE_COMPILED_ONE`, `STEP_TABLE_NOT_THE_COMPILED_ONE`, `NETWORKS_NOT_THE_COMPILED_ONES` (PROVIDER = `bridge`; `none`, `host` never), `RISK_LIMITS_NOT_THE_COMPILED_ONES` (E28's five, canonical), `DISK_FLOOR_NOT_THE_COMPILED_ONE`, `DAY_INVALID` (06…09), `OPERATION_INVALID`, `OPERATION_NOT_OF_THIS_MODE`, `SLOT_INVALID`, `ATTEMPT_KEY_MISMATCH` (`sha256(canonical([epoch, D, phase, operation]))`; tested against `actb03_lib.attempt_key`), `EVIDENCE_BOOT_UNBOUND`, `PARENT_ROWS_INVALID`, the core's `CHAIN_ROW_*`/`PARENT_SETGID` (days, claims, source_root receive entries), `CHAIN_ROW_GROUP_OR_SETGID` (gid 0 and no setgid on every component of the five chains; no open root), `SOURCE_ROOT_NOT_ON_THE_FILESYSTEM_OF_DAYS`, `CHAIN_LEAF_NOT_ROOT_PRIVATE` (every chain's leaf 0:0 0700), `RUN_NOT_AFTER_INVALID` (LAUNCH: UTC isoformat; capture = 14:03:00Z of D; ATTACHED/CLEANUP: null), `BIND_INVALID`, `BIND_NAMESPACE_NOT_THE_COMPILED_ONE`, `BIND_WINDOWS_INVALID`, `BIND_ORDER_NOT_ASCII`, `BIND_ORDER_NOT_THE_DETERMINED_BYTES`, `BIND_ORDER_SHA256_MISMATCH`; the argv builder's own codes.

### 6.2 `perform`, before anything is observed (a refusal; the GO is spent)
`EXECUTOR_IDENTITY`; `WINDOW_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY` ([D−1 20:00Z, D 15:00Z]); `WINDOW_NOT_OF_THE_STEP_CLASS` (BEFORE_OPEN ends ≤ D 13:30Z; capture starts ≥ 13:30Z); `CLEANUP_BEFORE_CAPTURE_RUN_NOT_AFTER`; `RUN_NOT_AFTER_NOT_WINDOW_END_PLUS_CEILING`; `RUN_NOT_AFTER_OUTSIDE_THE_UTC_DAY` (NOTE 5.1 rule 7); `RUN_NOT_AFTER_AFTER_THE_STEP_LIMIT` (commit ≤ 03:50Z of D, F7); `RUN_NOT_AFTER_TOO_CLOSE` (≥ 155 s left: the 90 s minimum life + 5 s + the 60 s of the run). Here and not in `validate_plan` because the core's conformance suite moves one plan's window across the date class (as K9R). Every WRITE window of both grids of the note (`aux/grid9.json`, G18 and G19, four eves) passes, tested.

### 6.3 Prechecks (refusals, nothing changed)
`EVIDENCE_FROM_EARLIER_BOOT`, `PARENT_*`, `CLAIM_EXISTS`, `DAY_DIRECTORY_NOT_PRIVATE`, `DAY_LAYOUT_INVALID`, `SYMLINK_COMPONENT`, `COMMAND_FAILED` (a listing or the image absent), `PREVIOUS_LAUNCH_RECORD_INVALID`, `PREVIOUS_CONTAINER_NOT_AS_RECORDED`, `UNCERTAIN_PREVIOUS_RUNNING`, `IMAGE_NOT_THE_SIGNED_ONE`, `ANOTHER_K9_CONTAINER_ACTIVE`, `CONTAINER_NAME_IN_USE`, `CLEANUP_NOTHING_TO_REMOVE`, `BUDGET_INSUFFICIENT`, the HOLD needs (`DISK_FREE_BELOW_FLOOR`, `ENV_FILE_NOT_PRIVATE`, `EMITTER_SECRET_NOT_PRIVATE`, `RUNNER_FILE_NOT_AS_REQUIRED`), and any other need's own code when there is nothing to remove (section 5).

### 6.4 After the claim (PARTIAL, exit 2)
`REMOVE_NOT_STARTED`, `COMMAND_TIMEOUT`, `PREVIOUS_CONTAINER_NOT_REMOVED`, `PREVIOUS_CONTAINER_REMOVAL_STATUS_NONZERO`, `ATTACHED_RESULT_LINE_NOT_THE_RECEIPT`, `EFFECT_NOT_SETTLED` (a safety net: never a success with an uncertain effect), `REMOVAL_READBACK_UNAVAILABLE`, `DIRECTORY_NOT_CREATED` and the core's file codes, `CREATE_FAILED`, `START_FAILED`, `RUN_NOT_AFTER_TOO_CLOSE`, `MOUNT_SOURCE_REPLACED_BEFORE_START` (the created container is removed, never started), `MOUNT_SOURCE_REPLACED_AROUND_START`, `MOUNT_SOURCE_REPLACED_AROUND_THE_RUN`, `LAUNCHED_CONTAINER_NOT_AS_BUILT`, `ATTACHED_NOT_STARTED`, `ATTACHED_DID_NOT_RETURN`, `ATTACHED_ENGINE_REFUSED`, `ATTACHED_RECEIPT_NOT_COMPLETE`, `EXIT_CODE_CONTRADICTS_THE_RECEIPT`, the FAILED receipt's own code.

## 7. Files K9W writes and the contracts

- **Claim** `<k9_root>/claims/<attempt_key>.claim`, 0:0 0600, canonical `{epoch, day, phase, operation, slot, request_sha256}` (NOTE 4.1). The key has no slot: one run per attempt, PRIMARY or SPARE. It is the first **effect**, after every read-only check (core rule 3): a refusal leaves no claim; the dispatcher's own `spawn.claim` still makes the request single use (deviation 2).
- **Day directories** (collect only): `Dd`, `Dd/plans`, `Dd/launches`, `Dd/receipts`, 0:0 0700, each read back.
- **Step plan** `Dd/plans/<operation>.json`, 0600, canonical bytes, `K9_STEP_PLAN_V1` **in the runner's schema** (its `PLAN_KEYS`, read on disk): `schema epoch day k9_phase k9_operation slot attempt_key request_sha256 go_sha256 run_not_after constants network_class database risk step_row`; `constants` = `package_sha256 code_revision act_b_sha256 release_sha256 policy_sha256 runner_sha256 risk_source_pins_sha256 risk_limits disk_floor_bytes`; `database` = `{host: db, port: 5432, dbname: c3po, role: c3po_v2_causal_emitter}` for commit and publish, else null; `risk` = the signed bind member for bind (`namespace cutoff_at phase_windows owner_order_text owner_order_sha256`), else null; `step_row` = the compiled row + operation, container name, step table hash. `run_not_after`: the signed one (LAUNCH); window end + 60 s (ATTACHED; the runner's own budget, 30/15 s, is shorter). Every key at every depth is a lower-case constant (tested). Written for the packaged steps too (their launch record needs its hash).
- **Launch record** `Dd/launches/<operation>.json`, 0600, `K9_LAUNCH_RECORD_V1` exactly as K9R reads it: `schema epoch day operation slot attempt_key request_sha256 step_plan_sha256 container_id container_name created_at started_at timeout_seconds` (`created_at ≤ started_at ≤ run_not_after`, 30 ≤ timeout ≤ 7200). Written after `start` returned 0, before the readbacks. Tested end to end: K9R's own sealed bytes read a K9W launch + the runner's two files as `COMPLETE`.
- **Labels** `c3po.k9.attempt_key`, `c3po.k9.request_sha256` on every K9 container, launched and attached.
- **Result line of bind and stage** (runner DESIGN §6 item 3): the runner prints its terminal receipt's bytes as its one stdout line; K9W requires the captured output to be exactly the receipt file's bytes + `\n` for COMPLETE (`ATTACHED_RESULT_LINE_NOT_THE_RECEIPT` otherwise). Preflight's line (the packaged CLI's own JSON) is not judged; its receipt file is.
- **Runner constants** (runner DESIGN §6): `runner_sha256` = `b5950b99…fc40` and `risk_source_pins_sha256` = `faaa35a7905076231f1847616c600968193c69ce064b6bd1db9cdbd6b77852bb` are signed constants of the week (the binder's); K9W checks their grammar, compares the bind receipt's `SOURCE_PINS.json` hash with the signed pins, and never reads the runner's bytes (TREE hashes them). A test reads the runner's own tables (`PLAN_KEYS`, `CONST_KEYS`, `RISK_KEYS`, `DB`, `OPS`) from its delivered bytes by syntax tree and compares them with K9W's step plan, network classes and attached budgets (30/15 s < 35/18 s).
- K9W never writes in the source root; the containers do, where the table mounts it.

## 8. Deviations from the note, and why

1. Plan keys `k9_phase`/`k9_operation` (the core reserves `phase`), as K9R; the runner's step plan uses the same names.
2. The claim is the first effect after all read-only checks (NOTE 4.1 "first creates"): core rule 3 requires everything to be looked at before the first creation; a refusal therefore changes nothing and leaves no claim.
3. LAUNCH timeout = `run_not_after − now − 5 s` (capped at `ceiling + 900 s` except capture; minimum 90 s), not `ceiling + 60 s`: with the note's cap, a launch sent at its window start would be killed up to ~5 min before `run_not_after − 60 s`, the runner's own deadline, so no DEADLINE receipt would be written and RESULT would be UNCERTAIN. `run_not_after = window end + ceiling` is enforced, so the life is still bounded by the window.
4. Stage: `Dd` read-only **plus** `Dd/receipts` read-write nested over it (the note's "Dd ro" leaves the runner no place for its receipts; the runner opens `receipts/` first for that reason). Four mounts.
5. Removal-only applies to every unmet need of the chain (predecessors, destinations, symbols, the risk plan and window), not only predecessors (NOTE 3.3); the HOLD needs (floor, env files, emitter secret, runner file) are refusals instead (section 4), found by the independent review.
6. The space floor holds every FULL step (Codex: HOLD below it), not only sources.
7. The source root (decision 6: `/var/lib/c3po/r2d2-v2-source-20261005`, root-only, on days/' filesystem) is mounted only where the table says (publish, components, stage, capture); every bind source is required root-controlled before any effect, and every mounted directory is still proved again from `/` right before `start` / the attached run and after them (defence in depth).
8. The publish limit (11:00 BRT, F7) is implied by the BEFORE_OPEN window class (13:30Z) and is not a separate check; commit keeps its 03:50Z.
9. `readiness_rule` and `probe_snippet_sha256` are checked by grammar only (K9R compiles them; K9R rev 3 added `minimum_eligible`), so one constants object serves both programs.
10. The rows `container` of NOTE 4.1 is named `launched` (K9R's name and format; the core's `container` row has the fixed `CONTAINER_FORMAT`).
11. `EVIDENCE_OPERATIONS` names K9R (the TREE receipt).

## 9. Proven, emulated, unproven, residual risks

- **Executed here**: the source's own Native with real system calls on a temporary tree (collect, commit, cleanup; the claim, the mkdirs, exclusive temporaries, link/unlink/fsync, O_NOFOLLOW/O_NOATIME walks, no secret opened, nothing else created) — macOS, an ordinary user reported as root. K9R's sealed build reading K9W's launch as COMPLETE.
- **Emulated only**: Docker (`create`, `start`, `rm`, the attached run, inspect with this format), uid 0, the host tree.
- **Unproven (K9W-U1…U8)** — `linux_root/` (run.sh + shapes.py, `--self-test` passes on emulation; NOT RUN) closes U1–U6 on a GitHub runner with python:3.12-alpine: U1 `docker create --pull never` with this middle and `start` of the printed ID; U2 the labels and `State.OOMKilled` read back; U3 busybox `timeout -s KILL` (exit 137); U4 `--env-file` + `--env` under `--read-only --cap-drop ALL`, the env reaching the container; U5 a 0600 root file readable through a ro bind and receipts writable through a rw bind by uid 0 with `--cap-drop ALL`; U6 `docker rm <id>` of an exited container. Not by that job: U7 the nested ro/rw bind of stage and the real image's `/app` (the first eve), U8 the networks `c3po_c3po_internal` and `c3po_db_loopback` and `db` resolution (N-4).
- **K9W-R1 (closed by placement, decision 6)**: revision 1's source root lay on the data volume, whose root is uid 1000's, which could swap it between K9W's proof and docker's bind. It now lies under `/var/lib/c3po` with every bind source and ancestor root-controlled (refused otherwise); no residual is claimed for it.
- **K9W-R2**: ACLs are not read (the core cannot); the mode-mask argument of K9R §0.1 applies (dirs 0700, files 0600 on POSIX-ACL filesystems).
- **K9W-R4** (cosmetic): an attached run refused by the engine (125–127, no step file) is settled "nothing changed" without a read; only `mutating_calls` is affected (the claim already makes it PARTIAL).
- **K9W-R3**: the core kills the docker CLI at a client timeout, not the container; every K9 container has its own `timeout -s KILL`, and a container whose `create` timed out may exist (reported as uncertain).

## 10. Open items

- Codex's written review of these bytes; the Linux-root job (set 3) with this directory.
- K9R rev 4 (decision 6) compiles the same placement object (tested); K9R: the launch record, labels, launched format and counts grammar were matched to its build as read on 2026-10-04 (hash in VALIDATION.json); a test runs K9R's build on K9W's launch. The runner is delivered (`b5950b99…`); a test compares its tables; any later runner is a new hash and a new check.
- Binder rev 4: K9W's plan (`bind` member with `owner_order_text`, the constants object, `parent_rows` from TREE, `run_not_after` = window end + ceiling) and the window checks of section 6.2.
- N-4 network names (signed constants), N-7 (section 9), N-12 (a K9 container left by a step never dispatched).
- The owner's text per K9W operation (binder `HOSTOPS02_TEXT_PT`).

## 11. Tests and mutation

Figures in `VALIDATION.json`, `TESTS.*.txt`, `mutation/MUTATION_RUN*.json`. Conformance: the core's 121 tests × 5 fixtures (collect, commit, bind, preflight, cleanup) with OTHERS = the sealed siblings and K9R. `test_plan.py` (every refusal of 6.1–6.2, the grid, the effects against literal argvs, the GO criterion), `test_step.py` (every operation, the contracts, the K9R end-to-end read, the removal rule, removal-only, every need, engine refusals, budget, every failing effect, the mount re-proof, privacy), `test_native.py` (real system calls), `test_linux_root.py` (the job's self-test and refusals). Mutation (revision 2): own list (`mutation/mutants.py`), figures in VALIDATION.json; revision 1 had 237 single mutants run, 237 killed, 0 survivors, 0 errors on Python 3.9.6 and on 3.12 (records `mutation/MUTATION_RUN.json`, `MUTATION_RUN.py312.json`, pins equal to the sealed files); 6 equivalent mutants are listed with the reason in `EQUIVALENT` and not run. The first passes had 24 survivors (missing tests for: marker identity, the record's plan hash, a symlinked env file, the floor at one byte, the day absent past an incomplete predecessor, every readback failure, a start that took effect with a non-zero status, the readback of the started container's identity and state, the bind and stage outputs, the mount re-proof after an attached run, the effects' chain rows); each is answered by a test of `test_step.py`/`test_plan.py`. The independent review of 2026-10-04 found 8 defects; sections 4, 8 and 9 say what changed (HOLD needs, the signed withdrawal, the capture cap, the 90 s minimum life, a non-zero `rm` stops, the preflight marker) and what stays residual (K9W-R1, K9W-R4).
