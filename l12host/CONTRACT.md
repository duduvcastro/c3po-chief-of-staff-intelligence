# L12-HOST v3.1: contract

Finite, server-side executor for the epoch-04 lots of ORDEM_EPOCA_04 rev M3 (`70cb947f…`). It is driven only by signed
REQUEST data. It is a Fable shell around the Codex cores, vendored byte for byte. This document gives no GO, no
installation and no host certification. Every FIXTURE in this family is synthetic, and the host refuses FIXTURE.

## 0. What changed from v3 (v3 adversarial review, 0 blockers, 5 should-fix, 7 low/disclose)

v3.1 copies the sealed v3 tree forward (`fable-l12host-v3-20261009`, top seal `64c37cf2…`, family `e694194c…`) and
changes only the shell, the tests, the proof, the specs and this contract. Every vendored Codex file is byte-identical
(the 15 pins of `verify_family.py`).

| v3 finding | v3.1 |
|---|---|
| **1** unit grammar: any `*.service` in Requires/Wants/After; any Environment | `Wants`/`Requires`/`After` admit ONLY the reference values (`network-online.target`; `docker.service`; `network-online.target docker.service`), at most once each (`UNIT_DEPENDENCY_INVALID`); `Environment` is exactly once and only `DOCKER_CONFIG=<layout docker_config>` (`UNIT_ENVIRONMENT_INVALID`: no LD_PRELOAD, DOCKER_HOST, DOCKER_CONTEXT...). `validate_session_start` pins the WHOLE reader and supervisor rows: `session_unit_rows` rebuilds the exact exec words and property list (reference order, Restart=no, the dropped keys absent) from eight variables (host data/journal/capacity/reader-config/supervisor-state/supervisor-config folders, image, network) and the signed rows must be equal (`SESSION_READER_UNIT_NOT_PINNED`, `SUPERVISOR_UNIT_NOT_PINNED`); physical mode pins the folders to the epoch-04 ones (`SESSION_UNIT_PATHS_NOT_EPOCH04`). The reviewer's probe (supervisor copy with `Wants=c3po-reader.service`) is refused at bind in physical mode (test `test_f1_session_start_unit_rows_are_pinned_whole`). |
| **2** a leftover `ready.json` satisfies the READY wait | In the SAME claim, after the fresh ALLOW and BEFORE the `xpre` marker, the ready path must NOT exist (any type): otherwise `READY_LEFTOVER_PRESENT_BEFORE_SUPERVISOR`, HOLD, no effect (`effect_calls` 0, no xpre). The engine repeats it at the supervisor's transport (`READY_PRESENT_AT_SUPERVISOR_START`). New EARLY read-only step `ready_check` (closed DOWN table, kind READY_CHECK, decoder `READY_ABSENT_V3`, no effect, no dependency; the session start never depends on it): DOWN draft slot **R0 = 09:30:00 BRT (12:30:00Z)**, a leftover is reported (`READY_LEFTOVER_PRESENT`, RESULT exit 2) ~1 h before the 10:29:02 session start so a person can clear it. Trade-off for Codex (9.2). |
| **3** time-of-day-dependent spacing test | `Review.test_slot_spacing_dependency_order_and_minutes_are_checked` binds a lot on FIXED instants (Sat 10/10 11:38:00 BRT + 155 s steps, dependent at +40 s, too-close at +10 s), fixed prepared/owner times, never the wall clock. |
| **4** mount policy | Physical: the L12 root is pinned to `/var/lib/c3po-l12host-e04` (`L12_ROOT_NOT_EPOCH04`, validate_authority and `prepare`). All modes: a mount of a PARENT of the L12 root, the veto folder or the docker-config folder is refused (`MOUNT_PARENT_OF_PROTECTED_FORBIDDEN`), the docker-config folder itself too (`MOUNT_DOCKER_CONFIG_FORBIDDEN`). `/etc` is mountable only under `/etc/c3po-reader-e04/launcher` and `/etc/c3po-reader-e04/supervisor` (read-only); `/etc/c3po-reader-e04` itself (it holds `secret.env`, `pins.env`, `activation.env`) is never mountable, its env files reach ONLY the session reader as `--env-file` (`READER_SECRET_ENV_OUTSIDE_THE_READER`), and the supervisor's mounts never contain them (`UNIT_MOUNT_EXPOSES_READER_SECRET`). |
| **5** supervisor liveness not rechecked | Worker: after BEFORE_FIRST_READER the acknowledged supervisor (its LAUNCH_ACK MainPID) must still be running once with that MainPID (`SUPERVISOR_NOT_RUNNING_BEFORE_READER`). Engine (20-word argv, new `--expect-supervisor-mainpid`): at the reader's transport (`SUPERVISOR_NOT_RUNNING_AT_READER_START`) and on every poll of the hold; the reader ACK (`L12HOST_UNIT_LAUNCH_ACK_V31`) records `supervisor {unit, main_pid, polls, running_through_hold}` and the decoder requires it true (`SUPERVISOR_NOT_RUNNING_THROUGH_HOLD`). Codex ruling requested on the semantics (9.2). |
| **6** session window not bound to open − 90 s | Bind: `open − 90 s <= session_start.not_before` and `not_after <= open + 6 h 50` (the Codex reader gate's own window rule), with `open` = the signed gate scope's `session_open`; physical mode pins `session_open` to `2026-10-12T13:30:00Z` (`SESSION_OPEN_NOT_THE_MONDAY_ONE`, `SESSION_START_WINDOW_BEFORE_OPEN_MINUS_90S`). The DOWN draft: window `[13:28:30Z, 13:36:30Z)` passes. |
| **7** K9 image_id and unit env-file paths unpinned | K9: the signed step-set request (`k9/K9_04_STEP_SET_REQUEST.json`, already pinned by every plan) names `image {id, revision, package_sha256}`; every plan's code revision and package must equal it (`K9_REQUEST_IMAGE_UNBOUND`) and every K9 row's `image_id` must be that id (`K9_IMAGE_NOT_THE_REQUEST_ONE`); the env files are EXACTLY the network class's ones under the secrets root (PROVIDER: provider.env; DATABASE_AND_PROVIDER: provider.env, risk-db.env; DATABASE/NONE: none; `K9_ENV_FILES_NOT_THE_CLASS_ONES`). The capture image must equal the gate scope's image (`CAPTURE_IMAGE_NOT_THE_SCOPE_ONE`); the session units too (`SESSION_UNIT_IMAGE_NOT_THE_SCOPE_ONE`). Unit env files: paths pinned by the whole-row pin (reader: `<reader config>/{secret,pins,activation}.env`, supervisor: none) and their IDENTITY (lstat 9-tuple, never opened) is pinned at the claim and re-checked before the supervisor and before the reader (`UNIT_ENV_FILE_IDENTITY_CHANGED`). No env file under the L12 root, the veto or the docker-config folder (`ENV_FILE_PATH_FORBIDDEN`). |
| **8** UP core rows without slack | Bind rule for every effect: `effect floor + gate allowance(s) + 30 s <= budget/ceiling` (`EFFECT_LATENESS_SLACK_BELOW_30S`, `EFFECT_LATENESS_SLACK_SECONDS`). UP rows: inner KILL = `min(generator KILL, budget − 65)`: every UP K9 row reaches its effect up to 45 s after its instant (table 9.3). |
| **9** Linux proof narrower than its docstring | The proof now runs a REAL-mode DOWN lot on the epoch-04 paths with a PHYSICAL Shell, its R0 and S1 slots fired by REAL systemd timers (slot services): the engine starts the supervisor and the reader unit copies from inside the timer-run slot service with its veto / ready-absent / supervisor-alive / ready-present gates; the fake supervisor container writes `ready.json` 6 s after it starts; plus three engine refusals with nothing started. Four Monday-only substitutions in `tests/proof_slot_driver.py` (9.4). |
| **10** which W seal Saturday signs | The staged family is now the WHOLE sealed family (tests/ included) in the kit and the proof; Saturday's W signs `seal_sha256 = sha256(l12host/SHA256SUMS)` of THIS delivery (value in the delivery report); the proof checks that its W seal equals it (`w_seal_is_the_delivered_family_seal`). |
| **11** image `timeout` not checked | `install_l12host.py image-check --layout --image` = HOST READBACK **HR-1** (9.5). Code reading of the image checkout `de96aee9`: `FROM python:3.12-alpine3.24@sha256:b64631e0…`, nothing removes busybox, whose `timeout [-s SIG] SECS PROG` applet is the expected `timeout`; not a certification. |
| **12** real supervisor READY timing not measured | Still not measured (9.6). |

## 1. What changed from v2 (v2 adversarial NO-GO, 4 blockers + 14 should-fix)

| v2 finding | v3 |
|---|---|
| **B1** procfs `boot_id` reports `st_size` 0 → `INPUT_FILE_CHANGED` | `read_boot_id` reads ONLY the fixed `/proc/sys/kernel/random/boot_id`: procfs mounted at `/proc` (mountinfo), regular file owned by root, read to EOF, ≤ 128 bytes, exact lowercase UUID + LF; `st_size` ignored only here. The exact bytes are pinned (`boot_id_sha256`), never normalized; `BOOT_CHANGED` still refuses on every recheck. The generic `read_at` is unchanged. Tests: size-0 emulation (portable) and a Linux-only real procfs test; the Linux proof reads the real file as root. |
| **B2** `install` / `install-derived` always `RUNTIME_NOT_INSTALLED_COPY`; lot left consumed | The installer never judges the host with its staged import. The INSTALLED runtime does, in a bounded subprocess (`<python> -I -S -B <root>/src/l12host_runtime.py preview-stage | preview | derived-check`, 120 s, one canonical `L12HOST_PREVIEW_V3` line ≤ 64 KiB, exact lot/REQUEST/BOUND/AUTHORITY/RUNTIME/mode/slot fields). `preview-stage` runs BEFORE the first write (remeasure, family from the installed src, every signed byte and the whole shell ABI in physical mode, identity). After the copy, `preview` of the installed lot; a refusal there is `PREVIEW_AFTER_COPY_HOLD` (no timer; nothing deleted or retried). `install-derived`: `derived-check` of the candidate file, O_EXCL write, `derived-check --installed`. The physical guard is unchanged. The Linux proof installs in PHYSICAL mode as root, the timers fire and the installed runtime COMPLETEs the slots. |
| **B3** `reader_bound` could start the OPS launcher, which enters SESSION by itself | Design decision (section 5): the reader is started ONLY ONCE, late, after READY, inside one claim. There is NO PRE_OPEN reader start in v3: `reader_bound`, `reader_cycle`, `policy_read`, `capture_*` are not core operations of v3 (`OPERATION_OR_DECODER_NOT_EXPRESSIBLE_V3`); `UNIT_START` exists only in the `session_start` extended step (`UNIT_START_ONLY_IN_THE_SESSION_START_STEP`, engine `UNIT_START_OUTSIDE_SESSION_START`); the engine starts the reader only while the exact verified `ready.json` is present (`READY_NOT_PRESENT_AT_READER_START`). |
| **B4** unit copies keep `Restart=on-failure` | The grammar admits exactly one `Restart=no`; `RestartSec`, `RestartPreventExitStatus`, `StartLimitIntervalSec`, `StartLimitBurst`, `OnFailure` are refused. `unit-row` derives the copy and REPORTS the change (`changed: [["Restart","on-failure","no"]]`, `dropped: [...]`); the reference bytes are untouched. The LAUNCH_ACK requires the effective `Restart=no` and `NRestarts=0`; the Linux proof reads both from real systemd. |
| S1 EXTENDED family open | Closed table per lane (`EXTENDED_TABLE`): UP `components, sources, bind, preflight, acquire, execute, stage` (kind RUNNER), DOWN `session_start` (SESSION_START) and `capture_launch` (CAPTURE). Each step has a fixed effect kind, decoder kind, command shape (K9: `python -I /c3po-k9-tools/k9_runner04-<FULL sha>.py --plan /c3po-k9-day/plans/<op>.json --plan-sha256 <sha>`; reader and supervisor: fixed words) and exact `requires`. The session start depends on its gate chain (J COMPLETE, post COMPLETE, the M3→J→CAPACITY_MONDAY originals). Nothing outside the table binds. |
| S2 cross-lot order unchecked | `cross_lot_check` at install, before the first write, over every installed lot: 30 s spacing; J after M3's end + 30 s; an exclusion window `[J1 − 30 s, J end + 30 s]` where no other slot of any lot may run; CAPACITY_MONDAY after J's end + 30 s; session start and capture after CAPACITY's end + 30 s; DOWN `post` after the end of the UP chain + 30 s. |
| S3 mount policy loose | Denylist in every mode (system roots, docker/containerd/postgresql/mysql data, `/etc` except `/etc/c3po-reader-e04`, the L12 root, a writable veto folder or reader config). Physical allowlist (`epoch04_mount_violation`): read-only = epoch-04 K9 / source / journal / supervisor-state / capacity / reader-config roots, `/mnt/day-d-data`, the secret roots, the veto folder; writable = the K9 day, the source root, the journal, the supervisor state. Secret roots never writable. |
| S4 capacity source copied from the selector | `LinkedReceipt.source_sha256` = the producing lot's signed effect source (`files[effects[role].source]`); the gate compares it with the signed selector. |
| S5 J4 `finite_batch` pin free | `j4.programs.finite_batch` must equal the ledger core `809a816d…` (`J4_FINITE_BATCH_NOT_THE_LEDGER_CORE`). |
| S6 three paths unguarded | Physical: `gate.journal_directory` = `/var/lib/c3po-bar/journal-e04`; `capacity.config_path` under `/var/lib/c3po-capacity-e04/config/`; `ready.ready_path` = `/var/lib/c3po-bar/journal-e04/session_date=2026-10-12/ready.json`. |
| S7 workflow 3.9 unproven; macOS ctime | The workflow pins `actions/setup-python@83679a89…` (v6.1.0) for 3.9 and 3.12 and checks the pushed tree against the top-level `SHA256SUMS`. The kit runs every fake binary once (`--warm`) before any measurement. |
| 8 brittle Linux step 3 | The unit proof uses a fake docker that keeps the unit running; properties are read while active. |
| 9 LAUNCH_ACK reads as COMPLETE | RESULTs carry `result_class`. A LAUNCH_ACK is only an ingredient of `SESSION_START_FIRST_CYCLE_HELD`, whose decoder also requires the hold and the pinned external verifier of the real first SESSION cycle. |
| 10 refused J1 hands J to J2 | The start marker is written BEFORE the slot-window / minute check. A late, early or forbidden-minute start is `REFUSED_CONSUMED_START` (exit 2) and every later alternative is `REFUSED_START_CONSUMED`. |
| 11 budget floor ignored pre-effect time | Floor = effect floor + 15 s gate allowance (+ READY wait, units and hold for the session start; + two C6 phases for the capture). At BEFORE_EFFECT the remaining deadline must still cover the effect floor (`BUDGET_REMAINING_BELOW_EFFECT_FLOOR`). |
| 12 unit without `--network` | `--network` is required in a unit and is never host/bridge/default/container. |
| 13 host programs re-check | Stated in section 8: the M1–M3 and capacity programs (Codex/Fable programs, not the shell) must re-check veto and minute before any container start they make. |
| 14 push hygiene | The delivered directory holds only `.github/`, `l12host/`, `evidence/`, `SHA256SUMS`; the workflow fails if the pushed tree differs from the seal. |

Codex inputs integrated: K9 prove receipt r1 (adapter `f84d55b8…`, `prove → prove_launch`); grid delta r1
(generator `2b08ee13…`, silences end at :45:59); image bounded readback r1 (`image_path_adapter 99148f80…`,
`bounded_readback 2a3c1ca9…`, `bounded_image_capacity_gate ade4c4b0…`) for every C6 phase read; J4 codec note (a stored
J original is re-decoded structurally and proven by the durable OUTER terminal; the live J verifier is not re-run
outside J's window); B3 reviews (supervisor is a declared, recorded effect; READY wait read-only inside the same
reservation; wait→recheck→FIRST_SESSION in the bounded executor; the late route needs its own plan and a human act).

## 2. Lots (signed REQUEST data → effects)

| Lot | Core lane / family | Operations |
|---|---|---|
| **W** | installer `prepare` | root 0700, children, runtime family 0400, empty ledger 0600; veto and docker-cli dirs pre-created by INSTALL_TREE04. |
| **UP** (Sat 10/10) | `UPSTREAM_P`: `prove`, `collect`, `commit_result`, `publish_launch` (K9 CONTAINER → `K9_STEP_V1`) | EXTENDED RUNNER steps `components … stage` (`K9_EXT_STEP_V3`). `lots/UP.SPEC.json`. |
| **BOOTSTRAP_MONDAY** | `install_release`, `readback`, `activate` (HOST_PROGRAM → EXTERNAL_V1) | as v2. |
| **DOWN** (signed Sun 11/10 ≤ 21:45 BRT) | `DOWNSTREAM_AFTER_E6`: `e6` (READBACK), `admission_manifest` J1/J2/J3 (J4 hot worker → `HOT_J_V1`), `post` (CHAIN_READBACK of the UP chain) | EXTENDED `ready_check` (v3.1, R0 09:30 BRT, read-only), `session_start` (B3) and `capture_launch` (K9 capture). `lots/DOWN.SPEC.DRAFT.json`. |
| **CAPACITY_MONDAY** | `capacity_activate` (HOST_PROGRAM, R6 `CapacityMondayGate`) | after J's end. |

### AUTHORITY V3 (pinned by REQUEST.authority_sha256)

```
schema L12HOST_AUTHORITY_V3, lot, lane, mode, layout (L12HOST_LAYOUT_V3), veto, delegated_named_selectors,
dependencies, effects, decoders, files (≤64), external, imports, slots,
k9 null | {runner_source, request, go, plans {runner_op: k9/<op>.json}, networks {PROVIDER, DATABASE,
           DATABASE_AND_PROVIDER}, secrets_root}                       (REQUEST parameters: networks = D-NET,
                                                                       secrets_root = decision pending Codex)
extended null | {steps: [{step, not_before, not_after, ceiling_seconds ≤ 4800, requires, effect, decoder,
                          pre_effect (session_start only), hold_until (session_start only)}]}
bootstrap, gate null | {scope, journal_directory, snapshot_reader, snapshot_verifier,
                        readback {rule, rule_verifier, readback_verifier}},
capacity null | {mode, lots, sources, verifiers, config_path}, ready null | {...}, j4 null | {...}
```

K9 rows are fully derived from the signed plan: runner name with the full sha, plan path and sha, container name
`c3po-k9-e04-20261012-<op>`, network = `k9.networks[plan.network_class]` (`none` for NONE; `bridge` legal only there),
env exactly `C3PO_R2D2_V2_PRODUCERS_ENABLED=true` and `C3PO_BUILD_SHA=<plan code_revision>`, env files only
`<secrets_root>/{provider,risk-db}.env`, mounts only tools (ro) / day / day receipts / source / emitter (ro, from the
secrets root), receipt `<day>/receipts/<op>.RECEIPT.json`, KILL ≤ run_not_after − start − 5 s, first slot = the plan's
start. The K9 decoder row is derived too (provenance = sha of the effect row; phase window = task/step window). Right
before the effect the host copies of the runner and the plan must be byte-equal to the signed files.

## 3. Effects (closed table, `l12host_effect.py`)

CONTAINER (`docker run --rm --pull never --init --user 0:0 --read-only --cap-drop ALL --security-opt
no-new-privileges --restart no --pids-limit 512 … IMAGE timeout -s KILL <n> python …`, ATTACHED only); UNIT_START
(session start only: SUPERVISOR pre-effect, SESSION_READER effect with READY presence and the hold); READBACK;
CHAIN_READBACK; HOST_PROGRAM (stdin program = pinned lot file; J: one derived-registry token). Engine argv has 20 words
(v3.1: `--expect-ready-sha256`, `--expect-supervisor-mainpid` last; only the reader carries both). `status` turns
UNCERTAIN only once the transport may have started.

## 4. Decoders (closed, `l12host_decode.py`)

`K9_STEP_V1` (vendored adapter, derived Approval rule) · `K9_EXT_STEP_V3` (same byte ABI for the runner steps; verifier
mandatory) · `HOT_J_V1` (live verifier at J; structural + OUTER terminal for stored reads) · `SESSION_START_V3` (record
schema `L12HOST_SESSION_START_V31`, reader ACK with the supervisor) · `READBACK_V3` · `CHAIN_READBACK_V3` · `EXTERNAL_V1`
· `READY_ABSENT_V3` (v3.1, `ready_check`).

## 5. B3: the single late reader start (design decision)

One DOWN slot at **10:29:02 BRT (13:29:02Z)**, step window `[13:28:30Z, 13:36:30Z)` (the C6 SESSION gate requires
`not_before ≥ open − 90 s`), ceiling 420 s, in ONE extended claim (start marker + `xclaim`):

1. dependencies (J and post COMPLETE, decoded and proven by the ledger) and the capacity chain (M3 → J → CAPACITY_MONDAY
   actual originals, order, final config) — the composition of `CapacityMondayGate`'s checks for the step window;
2. fresh double ALLOW + BEFORE_EFFECT; v3.1: the ready path ABSENT (else HOLD, no effect) and the reader env files'
   identity unchanged; `xpre-<key>` (O_EXCL) RECORDS the supervisor start; the supervisor unit copy starts (declared
   pre-effect, LAUNCH_ACK, Restart=no; the engine re-checks the ready path absent at the transport);
3. the READY wait, read-only, finite (`ReadyWaitGate` semantics for the step: only a verified absence waits; a present
   divergent file fails at once; deadline `min(48 s, 13:29:50Z exclusive, step)`); a READY appearing at or after
   13:29:50Z is a HOLD, no session, no new attempt;
4. RECHECK: lot bytes/authority/owner/window, identity, dependencies, capacity chain;
5. BEFORE_FIRST_READER through the bounded readback r1 (rule + REAL verifier bindings + read authority approved before the
   snapshot callback; snapshot verifier; bounded decode; journal root; `reader_gate`: ready, catalog, manifest,
   calendar, close, window) with the snapshot's `ready.json` equal to the one the wait verified;
6. v3.1: env-file identities unchanged; the acknowledged supervisor still running with its MainPID; fresh double ALLOW +
   BEFORE_EFFECT (veto current, minute, remaining budget); the engine starts the reader unit only while the supervisor
   is alive and the same `ready.json` is present;
7. hold until **13:30:30Z** (open + 30 s): the reader stays running, same MainPID, no restart, and (v3.1) the supervisor
   too, on every poll;
8. decode `SESSION_START_V3` + pinned verifier of the real first SESSION cycle; AFTER_FIRST_CYCLE.

The OPS launcher (`reader_launcher.py`, Codex note: PRE_OPEN only before open − 90 s) is started after 13:28:30Z with
READY present, so it skips PRE_OPEN and its internal switch to SESSION happens right after the gates above, which ran
immediately before the effect. No reader process exists before step 6; nothing starts a reader anywhere else. This is
an explicit deviation from the order's table line "leitor, partida PRE_OPEN 10:01 BRT": the DOWN question text states
it, and the owner's Assino of that REQUEST is the human act that selects it (Codex B3 addendum). The PRE_OPEN read-only
evidence at 10:01 is not kept as a receipt of a launch. The capture (10:52 BRT) is the K9 runner04 `capture_launch` as
an EXTENDED CAPTURE step after `session_start` and `post`, with the capacity chain and BEFORE_CAPTURE_LAUNCH before it
and AFTER_CAPTURE after it. Gates of the DOWN extended steps are a Fable composition of the Codex pieces (the vendored
classes bind to core tasks that v3 does not have): Codex reviews this composition.

## 6. Results and exit codes

`results/<LOT>.<SLOT>.json` (O_EXCL): `L12HOST_SLOT_RESULT_V3` with `start_marker`, `status`, `code`, `result_class`,
`effect_calls` (extended: 0..2), `recovery_required`, the full `outer` or `extended` dict (with `pre_effect`), and the
private callback `diagnostics`. Exit 0: `ORIGINAL_COMPLETE_OBSERVED_CANDIDATE` / `EXTENDED_COMPLETE`; 3:
`REFUSED_NO_EFFECT` (nothing consumed) or `REFUSED_START_CONSUMED`; 2: everything else (consumed). Preview commands:
exit 0 PASS, 3 refusal.

## 7. Refusal codes added in v3 (selection)

`BOOT_ID_PROCFS_UNAVAILABLE`, `BOOT_ID_NOT_REGULAR_ROOT`, `BOOT_ID_FORMAT_INVALID`, `PREVIEW_REFUSED_<code>`,
`PREVIEW_OUTPUT_FRAMING`, `PREVIEW_AFTER_COPY_HOLD`, `REFUSED_CONSUMED_START`, `OPERATION_OR_DECODER_NOT_EXPRESSIBLE_V3`,
`UNIT_START_ONLY_IN_THE_SESSION_START_STEP`, `UNIT_START_OUTSIDE_SESSION_START`, `UNIT_RESTART_MUST_BE_NO`,
`UNIT_DOCKER_NETWORK_INVALID`, `EXTENDED_STEP_NOT_IN_CLOSED_TABLE`, `EXTENDED_REQUIRES_NOT_THE_CHAIN`,
`K9_COMMAND_NOT_FIXED_SHAPE`, `K9_NETWORK_NOT_THE_CLASS_ONE`, `K9_ENV_NOT_FIXED`, `K9_MOUNTS_NOT_CLOSED`,
`K9_HOST_PLAN_NOT_THE_SIGNED_ONE`, `K9_DECODER_ROW_NOT_DERIVED`, `SLOT_INSIDE_J_EXCLUSION_WINDOW`, `J_BEFORE_M3_END`,
`CAPACITY_BEFORE_J_END`, `READER_OR_CAPTURE_BEFORE_CAPACITY_END`, `POST_BEFORE_UP_CHAIN_END`,
`MOUNT_SOURCE_NOT_ALLOWLISTED`, `MOUNT_VETO_WRITABLE_FORBIDDEN`, `MOUNT_L12_ROOT_FORBIDDEN`,
`MOUNT_SECRETS_WRITABLE_FORBIDDEN`, `CAPACITY_PRODUCER_SOURCE_UNSIGNED`, `J4_FINITE_BATCH_NOT_THE_LEDGER_CORE`,
`GATE_JOURNAL_NOT_EPOCH04`, `CAPACITY_CONFIG_NOT_EPOCH04`, `READY_PATH_NOT_EPOCH04`, `BUDGET_REMAINING_BELOW_EFFECT_FLOOR`,
`READY_WAIT_DEADLINE`, `READY_WAIT_ORIGINAL_DIVERGENT`, `READY_NOT_THE_WAITED_ONE`, `READY_NOT_PRESENT_AT_READER_START`,
`SESSION_START_NOT_HELD`, `LAUNCH_ACK_UNIT_NOT_RUNNING_ONCE`. v3.1: `UNIT_DEPENDENCY_INVALID`, `UNIT_ENVIRONMENT_INVALID`,
`SESSION_READER_UNIT_NOT_PINNED`, `SUPERVISOR_UNIT_NOT_PINNED`, `SESSION_UNIT_MOUNTS_NOT_PINNED`,
`SESSION_UNIT_PATHS_NOT_EPOCH04`, `UNIT_MOUNT_EXPOSES_READER_SECRET`, `SESSION_UNIT_IMAGE_NOT_THE_SCOPE_ONE`,
`READY_LEFTOVER_PRESENT`, `READY_LEFTOVER_PRESENT_BEFORE_SUPERVISOR`, `READY_PRESENT_AT_SUPERVISOR_START`,
`L12_ROOT_NOT_EPOCH04`, `MOUNT_PARENT_OF_PROTECTED_FORBIDDEN`, `MOUNT_DOCKER_CONFIG_FORBIDDEN`, `ENV_FILE_PATH_FORBIDDEN`,
`READER_SECRET_ENV_OUTSIDE_THE_READER`, `SUPERVISOR_NOT_RUNNING_BEFORE_READER`, `SUPERVISOR_NOT_RUNNING_AT_READER_START`,
`SUPERVISOR_NOT_RUNNING_THROUGH_HOLD`, `EFFECT_ARGV_NOT_FOR_THIS_EFFECT`, `SESSION_OPEN_NOT_THE_MONDAY_ONE`,
`SESSION_START_WINDOW_BEFORE_OPEN_MINUS_90S`, `K9_REQUEST_IMAGE_UNBOUND`, `K9_IMAGE_NOT_THE_REQUEST_ONE`,
`K9_ENV_FILES_NOT_THE_CLASS_ONES`, `CAPTURE_IMAGE_NOT_THE_SCOPE_ONE`, `UNIT_ENV_FILE_IDENTITY_CHANGED`,
`EFFECT_LATENESS_SLACK_BELOW_30S`, `IMAGE_TIMEOUT_CHECK_FAILED` (HR-1).

## 8. Limits stated, not certified

- The DOWN extended gates compose Codex's pure C6 predicates, the bounded readback decoder and the capacity rule for a
  step window; the vendored gate classes themselves are not used there (they require core tasks). Codex review needed.
- Dependency rule: a dependent starts at or after `min(not_after, last alternative + 60 s + budget)` of its dependency
  (the F-E grid chains exactly at the window end). A dependency that COMPLETEs in its last ~10 s could leave its terminal
  unwritten for a dependent that starts at that instant; the runner stops itself at run_not_after − 60 s.
- Process-group kill covers descendants in the group; a docker container is bounded by its inner `timeout -s KILL` and
  `--rm`; a started unit outlives the step by design and is never restarted. A veto created after the reader starts
  does not stop it.
- Host programs (M1–M3, CAPACITY_MONDAY, J4) get the veto and minute checks at spawn; any container start they make
  later (the worker recreate) must re-check inside the program.
- Same trust boundary as R6: pinned trusted Python, not a sandbox; same-disk ledger; a reboot or an unattended upgrade
  invalidates the pinned boot id and binaries (hold updates until 16/10).

## 9. v3.1 disclosures, rulings requested, host readback items

### 9.1 What Saturday's W signs
The W REQUEST pins `seal_sha256` = SHA-256 of the staged `l12host/SHA256SUMS`. Saturday stages this delivery's
`l12host/` exactly (tests/ included), so the W signs **sha256(l12host/SHA256SUMS) of v3.1** (the family seal stated in
the delivery report). The kit and the Linux proof stage the same whole family; the proof's W seal must equal the pushed
`l12host/SHA256SUMS` hash. Any later change of any family byte changes that seal and needs a new W.

### 9.2 Codex rulings requested (in addition to the v3 list, which stands)
1. **Leftover ready (finding 2).** A ready file present before the supervisor start is a HOLD of the whole session start
   (no reader that day unless a human act); the alternative (delete/rename it inside the claim) was rejected because the
   shell never deletes evidence. The early R0 check gives ~1 h to clear a leftover by hand. Accept or rule otherwise.
2. **Supervisor death (finding 5).** Before the reader: HOLD with the supervisor started (`effect_calls` 1, recovery
   required, the reader never starts). During the hold: the reader is already running; the step ends
   EXTENDED_UNCERTAIN_CONSUMED (no COMPLETE, recovery required) and the reader is NOT stopped by the shell (the shell
   never stops a unit). Rule whether the reader must be stopped in that case (a new effect) or left to the human.
3. **Slack vs the runner's DEADLINE receipt (finding 8, table 9.3).** Codex's generator sets a LAUNCH step's KILL to
   budget − 35 so the runner (which stops itself at run_not_after − 60 = start + budget − 90) has < 55 s for its
   DEADLINE receipt. v3.1's KILL = budget − 65 keeps 30 s slack for gate latency but leaves the runner 25 s + the
   effect lateness after its own stop. Alternative not implemented: keep budget − 35 and clamp the KILL at the transport
   to `deadline − 20 − now` (engine change, needs the deadline in the argv). Choose one.
4. **Whole-row pin (finding 1).** The pinned shape is the reviewed references verbatim (`--pids-limit 512`,
   `--stop-timeout 25`, `TimeoutStartSec=60s`, `/app` workdir, the three ExecConditions, both ExecStartPre lines). Any
   change in the references needs a new family.
5. The K9 request's `image` block is the image pin (finding 7): confirm the Saturday regeneration keeps it.

### 9.3 Budget floor vs effect lateness (UP, `lots/UP.SPEC.json`; `build_specs.py validate` prints it)
`effect floor = KILL + 20 s` (docker margin); BEFORE_EFFECT refuses (and consumes) when `deadline − now < floor`, with
`deadline = min(start + budget, not_after) = instant + budget` on the F-E grid. So **max effect lateness = budget −
floor** (from the slot instant to BEFORE_EFFECT: timer accuracy 1 s + interpreter start + shell + core gates + runner
stages), and **slack beyond the 15 s gate allowance = budget − floor − 15 ≥ 30 s** (bind rule).

| row | budget | KILL (generator → v3.1) | floor | max lateness | slack |
|---|---|---|---|---|---|
| prove, commit_result, publish_launch | 600 | 565 → 535 | 555 | 45 s | 30 s |
| collect | 900 | 865 → 835 | 855 | 45 s | 30 s |
| components | 2400 | 2365 → 2335 | 2355 | 45 s | 30 s |
| sources | 4500 | 4465 → 4435 | 4455 | 45 s | 30 s |
| bind (ATTACHED 30 s) | 120 | 35 (unchanged) | 55 | 65 s | 50 s |
| preflight | 300 | 265 → 235 | 255 | 45 s | 30 s |
| acquire | 4200 | 4165 → 4135 | 4155 | 45 s | 30 s |
| execute | 1200 | 1165 → 1135 | 1155 | 45 s | 30 s |
| stage (ATTACHED 15 s) | 120 | 20 (unchanged) | 40 | 80 s | 65 s |
| DOWN capture (ceiling 750, plan 690) | 750 | 655 (unchanged) | 675 (+30 s C6 phases) | 45 s | 30 s |
| DOWN session_start (ceiling 420) | 420 | units 100 + READY 48 + 100 + hold 88 + 45 | 381 | — | 39 s |

Gate latency on the host is NOT measured (HR-3).

### 9.4 The Linux proof's substitutions (finding 9)
`tests/proof_slot_driver.py` is the timer-run slot command of the proof's DOWN lot; it loads the INSTALLED runtime
(physical Shell) and substitutes only: the open constant (the proof's synthetic open instead of 13:30:00Z Monday), the
capacity chain (Monday originals), the C6 phases (only READY_NOT_THE_WAITED_ONE kept for BEFORE_FIRST_READER) and the
J/post dependencies (J needs the Codex J4 hot worker in its Monday window). The DOWN lot is copied into the root the way
the installer's first write does (the installer's physical preview would refuse a non-Monday open, which the proof
checks: `down_physical_refuses_a_non_monday_open`). The UP lot is installed by the real installer. The proof has not
run yet (push and run are open item 1).

### 9.5 Host readback items (none run; each needs its own authorization)
- **HR-1 image `timeout`** (finding 11): `python3 -I -B install_l12host.py image-check --layout <layout.json> --image
  sha256:bf37cec9…` as root before Saturday's P1 (14:26Z): two network-less, read-only, mount-less containers of the
  pinned image; PASS = `IMAGE_TIMEOUT_KILL_PRESENT` (`timeout -s KILL 10 python -I -c pass` exit 0; `timeout -s KILL 2`
  around a 30 s sleep exit 137 in < 15 s). Any other result is a HOLD of every K9 row.
- **HR-2 epoch-04 paths** for the pinned shapes: `/var/lib/c3po-l12host-e04` absent before W; `/etc/c3po-reader-e04/
  {secret,pins,activation}.env` root 0600 nlink 1; `/etc/c3po-reader-e04/launcher` and `/supervisor` root 0700, the
  supervisor folder holding no copy of the reader's env files; `/var/lib/c3po-bar/journal-e04/session_date=2026-10-12/
  ready.json` ABSENT on Monday morning (R0 reports it).
- **HR-3 gate latency**: the time from a slot instant to its BEFORE_EFFECT on the host (from the RESULT `started_at` and
  the engine `transport_at`) on Saturday's first slots; must stay well under 45 s.

### 9.6 Still not measured or proven
- Whether the real Massive supervisor writes `ready.json` before 13:29:50Z (~45 s after its start); the producer's code
  (`r2d2_v2_massive_sessions.py` mark_ready, atomic rename) publishes it at session initialisation; timing unmeasured.
- The Monday positive paths (BOOT, CAP, capacity chain, C6 phases, capture) need the Monday clock.
- Host updates must be held until 16/10 (pinned boot id and binaries).
