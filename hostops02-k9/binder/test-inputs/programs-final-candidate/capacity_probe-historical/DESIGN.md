# PROBE — the capacity probe of epoch R2D2-V2-SHADOW-2026-10-05 (HOSTOPS02, `GO_READONLY_HOSTOPS02_CAPACITY_PROBE_01`), revision 2

Offline work only: nothing here was run on the host, pushed, bound or signed. Every hash was taken by command
(`shasum -a 256`); where this text and `SHA256SUMS`, `build/ASSEMBLY.json` or the code differ, the files prevail.
One source of the frozen HOSTOPS02 core (generation `4c24c5cf…d0d6`, seal `73fb546b…c9b1`, not modified), steps
**CALENDAR**, **IDENT**, **LOAD**, one request per step. The TLS step of the master plan's PROBE row is the sealed
`tls_probe` (C3) and is not rebuilt here.

Sources of truth read: master plan rows A5, B4/B4c, C#2/C#22 and the PROBE row of section 4; A2 rev 3 section 6-A
(lines 233–246); `capacity-mount/README.md` (MNT) steps 1 and 2; `capacity-day/README.documents.md` lines 85–188 (the
calendar pin); the release at main `dd4ec4bb` (`r2d2_v2_capacity_anchored.py`, `r2d2_v2_store.py`,
`r2d2_v2_capacity_bootstrap.py`, `config.py`, `r2d2_v2_epoch_assembler.py`, `Dockerfile`, `compose.yml`, each pinned by
hash in `tests/test_static_pins.py`); the provisioning request `once-e2-20261003-b` (tree under `/var/lib`).

## 1. Name, class and what the owner signs

| | |
|---|---|
| Operation / phase | `GO_READONLY_HOSTOPS02_CAPACITY_PROBE_01` / `READONLY_CAPACITY_PROBE`; schemas `READONLY_HOSTOPS02_CAPACITY_PROBE_{REQUEST,AUTHORITY,GO,RECEIPT}_V1`, plan `HOSTOPS02_CAPACITY_PROBE_PLAN_V1` |
| Module | `build/capacity_probe.py` (NAME/MODULE `capacity_probe`, STEM `HOSTOPS02_CAPACITY_PROBE`) |
| Parts | `core runner docker parents` (parents for `validate_chain` and `chain_effects`; no `files`, no `lock`) |
| Class | `WRITES_ALLOWED=False`, `ACTIVATION_ALLOWED=False`, `DATE_CLASS='READ'`: every container has read-only binds only (CORE.md 8.1). The class says nothing about the signature: A2 6-A keeps A5 and B4c **individual** by request hash |
| Gate | `MAX_GATE_SPAN_SECONDS=3600` (A2 lines 66, 113: a read has the window of its own line, at most 3600 s) |
| Success | follows the signed step (`SUCCESS_IN_TEMPLATE=False`, the GO template carries null): CALENDAR `CALENDAR_LINE_READ_IN_THE_IMAGE_AS_PINNED`, IDENT `ROOT_IDENTITIES_READ_TWICE_EQUAL_TO_THE_HOST`, LOAD `STATIC_CONFIG_LOADED_WITH_THE_WORKER_BIND` (= `COMPLETE_OUTCOME`) |
| Evidence | `EVIDENCE_REQUIRED=True`, `EVIDENCE_OPERATIONS=()` (open question Q1) |

The plan (`PLAN_KEYS`), every member signed:

| Member | CALENDAR | IDENT | LOAD |
|---|---|---|---|
| `step` | `CALENDAR` | `IDENT` | `LOAD` |
| `image_id` | the backend image by local ID (`sha256:<64>`), never a tag | same | same, and the worker must run it |
| `image_revision` | must be `dd4ec4bb8dab…e858` | same | same |
| `evidence_boot_id_sha256` | the boot of the receipts the rows come from | same | same |
| `capacity` | **null** | `{root_path, parent_rows}`: the host path of the tree (`/var/lib/c3po-capacity`) and the six-key rows of `/`, `/var`, `/var/lib` | same |
| `load` | **null** | **null** | `{config_file, config_sha256, release_sha, mount_receipt_sha256}`: the container path `/c3po-capacity/config/<name>` (B5: `week.static.capacity.json`), its SHA-256, the release sha (`r2d2_v2_shadow_release_sha`), the receipt of K6b's mount |

`effects_of(plan)` (what authority and GO carry, recomputed and compared): operation, step, success outcome, the bands of
the step and their source, the image (ID, revision, "by ID never a tag"), every container (its name with
`<first 16 hex of the GO sha256>`, the exact docker argv, the binds, network none, no environment file, no
DOCKER_CONFIG, the SHA-256 and size of its standard input and of the pinned script, its time limit and alarm), the
capacity (root path, `chain_effects` of the parent rows, the four children, "root:root 0700", the target), for LOAD the
config path, config hash, release hash, the mount receipt `{operation: GO_WRITE_HOSTOPS02_CAPACITY_SWITCH_01,
receipt_sha256}`, veto mode, worker name and the expected line; for CALENDAR the expected line (epoch, package,
document order); the boot of the evidence; writes 0, removes [], activation false, containers_run.

## 2. Day, band, gate

`DATE_CLASS='READ'` (10-02..10-10) at the dispatcher; the source narrows it in `validate_plan` (so at both layers, before
any claim) to the bands of its step, A2 rev 3 section 6-A:

| Step | Bands (UTC) | Codes |
|---|---|---|
| CALENDAR, IDENT (A5) | Sun 2026-10-04 16:26–23:30; Mon 10-05 … Thu 10-08 20:38–23:30 | `STEP_DAY_NOT_IN_SCOPE`, `STEP_WINDOW_OUTSIDE_THE_BAND` |
| LOAD (B4c) | Mon 10-05 … Thu 10-08 20:38–23:30 ("the same band, after B4"; B4 has no Sunday band) | same |

Every band lies on one UTC day (none crosses 21:00 BRT). Tests: every day of the class and every band edge to the second,
at the source and through the dispatcher's prepare (`tests/test_conformance.py`, the replaced date-scope test).

## 3. The steps

All containers: the core's `RUN_PREFIX` unchanged (`run --rm -i --pull never --init --user 0:0 --network none
--read-only --cap-drop ALL --security-opt no-new-privileges`), `--name hostops02-probe-<step>-<16 hex of the GO>`
(IDENT `-1`, `-2`), `[--mount type=bind,source=<root_path>,target=/c3po-capacity,readonly]`, the image ID,
`python -I -B -`, the bytes on standard input, the core's fixed environment (no HOME, no DOCKER_CONFIG).

**CALENDAR (A5).** No bind. Standard input: `calendar-pin.py` byte for byte (876 bytes, sha256
`5a6066ae2925453a0def335d8f8ac7e802e149b56cf9e61ea3fe8843fe582b5f`, extracted by command from the markers of
README.documents.md and compared in `tests/test_static_pins.py`). Class RUN (40 s). The line must be
`{status: CALENDAR_PIN, epoch, calendar_version, calendar_pin_sha, package_sha, document_order_sha}` with
epoch `R2D2-V2-SHADOW-2026-10-05`, package `b5ce527a…bdb84` and document order `1a5253bf…a118`, each read from the
release by command (the package sha computed by `implementation_package_sha()` of the release tree). The receipt
carries the line's six members. The real script was run against the release's modules on 3.12 (exchange_calendars
4.13.2) and printed exactly these values.

**IDENT (A5).** Precheck walks `/ → /var → /var/lib` by the signed rows (`walk_pinned`, held), then the root by name
(lstat, open with `O_NOFOLLOW|O_DIRECTORY`, fstat equal to the lstat); every entry directly in the root must be a directory (at most 64 entries: `CAPACITY_ROOT_ENTRY_NOT_A_DIRECTORY`, `CAPACITY_ROOT_ENTRY_LIMIT`; a socket or a file is never bound unseen), and its four children `config documents go
payload` the same way, each held (`Pinned`); each must be a directory `root:root 0700`. From the numbers read, the source
computes each identity exactly as AnchoredRoot does inside the container: `sha256(canonical([["c3po-capacity", dev, ino],
[name, dev, ino]]))` (the release's `r2d2_v2_store.digest`; equality proved against the release's own module and against
the real AnchoredRoot in `tests/test_scripts.py`). Then two containers, one after the other (the second only if the
first returned), each with the root bound read-only at `/c3po-capacity`, class RUN_SHORT (20 s). The pinned IDENT script
(1330 bytes, sha256 `0b8b1221…45d1`, alarm 14 s first) imports `app.r2d2_v2_capacity_anchored.AnchoredRoot` from `/app`
and prints `{status: ROOT_IDENTITIES, identities: {config, documents, go, payload}}` or
`{status: ROOT_IDENTITIES_REFUSED, code}` (the ShadowIntegrityError code when it is a constant, else the class name).
Success: both runs valid, equal to each other, and documents, go, payload equal to the host's; the config directory's
identity is compared and reported (`comparison.equal_to_the_host.config`) but not required.

**LOAD (B4c).** Precheck: the tree as IDENT; then the static config ON THE HOST: by name in the held `config`
directory (`read_regular`, no link, at most 4 MiB, AnchoredRoot.read's policy: owner 0, one link, nothing for group and
other), SHA-256 equal to the signed one (bytes stay in memory; the receipt says `sha256_as_signed: true` and the size);
then the worker `c3po-r2d2-worker-1` by name (`container_facts`): running, on the signed image; its mounts by the new
READ row `worker_mounts` (`container inspect --format MOUNTS_FORMAT <worker ID>`: one JSON object, per mount only
`type source destination rw`, never Env or labels): exactly one mount at `/c3po-capacity`, a bind, source equal to the
signed root path, `rw` false; no OTHER mount whose destination lies under `/c3po-capacity/` (`WORKER_MOUNT_INSIDE_THE_CAPACITY_TARGET`) and none whose (absolute) source is the root, below it or an ancestor of it (`WORKER_OTHER_MOUNT_REACHES_THE_TREE`: a `/var/lib` bind at `/app/day-d-data` would make the tree writable through an ancestor); then the worker's settings by the core's `container_environment` template on its ID (booleans only, the compared values are the signed ones): `C3PO_R2D2_V2_SHADOW_RELEASE_SHA` present and equal to the signed release sha (`WORKER_RELEASE_SHA_NOT_AS_SIGNED`), `C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE` present and equal to the signed root (`WORKER_MOUNT_SOURCE_NOT_AS_SIGNED`), and each of `…_CAPACITY_CONFIG_FILE`, `…_CONFIG_SHA`, `…_VETO_MODE`, `…_REQUIRED` absent or equal to the signed path, hash, `DISPATCH_AND_DERIVATION_ONLY`, `true` (`WORKER_CAPACITY_SETTING_NOT_AS_SIGNED`); and, reported and never judged, whether the root's status-change time is later than the worker's `StartedAt` (`root_changed_after_the_worker_started`). Then ONE fresh container with the same bind, class RUN (40 s). Standard input: the pinned
LOAD script (2050 bytes, sha256 `c3019efa…a99c`, alarm 34 s first) and one appended line `run(json.loads('<canonical
JSON of config_file, config_sha256, release_sha>'))` (paths and hashes of a fixed grammar; a quote or a backslash is
refused, `LOAD_VALUES_INVALID`). The script builds `Settings(r2d2_v2_capacity_required=True,
r2d2_v2_capacity_config_file=…, r2d2_v2_capacity_config_sha=…, r2d2_v2_capacity_veto_mode='DISPATCH_AND_DERIVATION_ONLY',
r2d2_v2_shadow_release_sha=…)` (init kwargs; `populate_by_name=True`, proved with the release's own Settings on 3.12),
then `CapacityConfig(settings)`, prints `{status: CAPACITY_STARTUP_OK, roots: sorted(c.roots), veto_mode, identities of
the roots, config_sha256}` (the SHA-256 of the config as `CapacityConfig` reads it again through its own `config_root.read(name)`, not the settings' copy) and closes; on any exception `{status: CAPACITY_STARTUP_REFUSED, code}` and exit 1.
Success: OK, roots exactly `documents go payload`, veto `DISPATCH_AND_DERIVATION_ONLY`, `config_sha256` equal to the signed hash, and
the three identities equal to those computed from the host's numbers. After the container: the worker again (same ID,
running, same image, same restart count) and the held tree again.

## 4. Order of a run and budget

Every step: `identity == (0,0)` first → boot of the evidence → image by ID (revision label) → [tree] → [config file,
worker, mounts] → `ps -a` (names of this GO free) → `gate() >= effects_budget(*rows)` → containers → `ps -a` → [worker]
→ [tree verify]. A refusal up to the budget check has started nothing (exit 1, `REFUSED_NO_CONTAINER_STARTED`).

| Step | Containers | Must be left at the check | Precheck may use | After the last container |
|---|---|---|---|---|
| CALENDAR | 1 × RUN (40 s) | 40 + 4 = **44 s** | ≤ 16 s (two QUICK reads, the boot file) | ≥ 4 s for `ps -a` when the run takes its whole class |
| IDENT | 2 × RUN_SHORT (20 s) | 20 + 20 + 4 = **44 s** | ≤ 16 s | the second run is started only with ≥ 24 s left (core rule 1): a first run that takes its whole 20 s still leaves exactly 24 s (tested at 20 s and 20.01 s) |
| LOAD | 1 × RUN (40 s) | **44 s** | ≤ 16 s (five QUICK reads, the walk, the config read) | ≥ 4 s for `ps -a`, the worker and the tree verify |

RUN (40 s) for CALENDAR and LOAD because they import the application (calendar, pydantic); RUN_SHORT for IDENT so that
two runs fit 60 s (2 × RUN = 84 s cannot). The IDENT and LOAD scripts end their own process by alarm (14 s, 34 s)
before the CLI's limit (20 s, 40 s) minus the reserve; CALENDAR's verbatim bytes have no alarm (Q6). A read that runs out
of time after a container is a finding (`*_UNAVAILABLE_*`), never a refusal.

## 5. Refusals and verdicts

From the bytes (validate_plan, before any claim), in order: `STEP_INVALID`; `STEP_DAY_NOT_IN_SCOPE`,
`STEP_WINDOW_OUTSIDE_THE_BAND`; `EVIDENCE_BOOT_UNBOUND`; `IMAGE_REVISION_NOT_THE_RELEASE`;
`CAPACITY_NOT_OF_THE_STEP` | `CAPACITY_UNBOUND`, `CAPACITY_ROOT_INVALID`, `CHAIN_ROW_INVALID`, `CHAIN_ROW_UNSAFE`;
`LOAD_UNBOUND`, `CONFIG_FILE_INVALID`, `CONFIG_SHA_INVALID`, `RELEASE_SHA_INVALID`, `MOUNT_RECEIPT_UNBOUND`,
`LOAD_HASH_REUSED` | `LOAD_NOT_OF_THE_STEP`; `IMAGE_ID`, `MOUNT_INVALID`, `CONTAINER_TARGET`; then the standard input is
built: `SCRIPT_NOT_THE_PINNED_HASH` (any of the three pinned scripts), `LOAD_VALUES_INVALID`.

Precheck (exit 1, nothing started): `EXECUTOR_IDENTITY`; `EVIDENCE_FROM_EARLIER_BOOT`, `BOOT_ID_INVALID`;
`BINARY_UNAVAILABLE_OR_UNSAFE`, `IMAGE_ABSENT_OR_UNREADABLE`, `IMAGE_METADATA_INVALID`, `JSON_INVALID`,
`IMAGE_ID_MISMATCH`, `IMAGE_REVISION_MISMATCH`; `PARENT_MISSING`, `PARENT_UNREADABLE`, `PARENT_SYMLINK_COMPONENT`,
`PARENT_NOT_DIRECTORY`, `PARENT_CHANGED_DURING_WALK`, `PARENT_IDENTITY_MISMATCH`; `CAPACITY_ROOT_ABSENT`,
`CAPACITY_ROOT_NOT_A_DIRECTORY` (also a link), `CAPACITY_CHANGED_DURING_WALK`, `CAPACITY_ROOT_NOT_PRIVATE`,
`CAPACITY_CHILD_ABSENT`, `CAPACITY_CHILD_NOT_A_DIRECTORY`, `CAPACITY_CHILD_NOT_PRIVATE`; LOAD: `CONFIG_FILE_ABSENT`,
`CONFIG_FILE_UNREADABLE` (a link), `FILE_NOT_REGULAR`, `FILE_TOO_LARGE`, `FILE_CHANGED_DURING_READ`,
`CONFIG_FILE_NOT_PRIVATE`, `CONFIG_FILE_HASH_MISMATCH`, `WORKER_ABSENT_OR_UNREADABLE`, `CONTAINER_METADATA_INVALID`,
`WORKER_NOT_RUNNING`, `WORKER_NOT_ON_THE_SIGNED_IMAGE`, `WORKER_MOUNTS_UNREADABLE`, `WORKER_MOUNTS_INVALID`,
`WORKER_CAPACITY_MOUNT_ABSENT`, `WORKER_CAPACITY_MOUNT_NOT_ONE`, `WORKER_CAPACITY_MOUNT_NOT_A_BIND`,
`WORKER_CAPACITY_MOUNT_OTHER_SOURCE`, `WORKER_CAPACITY_MOUNT_WRITABLE`, `WORKER_MOUNT_INSIDE_THE_CAPACITY_TARGET`, `WORKER_OTHER_MOUNT_REACHES_THE_TREE`, `WORKER_ENVIRONMENT_UNREADABLE`, `ENVIRONMENT_METADATA_INVALID`, `WORKER_RELEASE_SHA_NOT_AS_SIGNED`, `WORKER_MOUNT_SOURCE_NOT_AS_SIGNED`, `WORKER_CAPACITY_SETTING_NOT_AS_SIGNED`; IDENT and LOAD: `CAPACITY_ROOT_ENTRY_NOT_A_DIRECTORY`, `CAPACITY_ROOT_ENTRY_LIMIT`; `CONTAINER_LISTING_FAILED`,
`CONTAINER_LIST_INVALID`, `CONTAINER_NAME_TAKEN`; `BUDGET_INSUFFICIENT_BEFORE_THE_CONTAINER`; anywhere
`COMMAND_TIMEOUT`, `COMMAND_OUTPUT_LIMIT`, `COMMAND_NOT_STARTED`, `GO_EXPIRED`, `CLOCK_REVERSED`, `PRECHECK_OS_ERROR`,
`PRECHECK_FAILED`. Phase `CONTAINER_NOT_STARTED` (exit 1): the first container refused by the runner before a process
existed.

After a container started nothing refuses (exit 2 unless success), first match wins:

| Outcome | Codes |
|---|---|
| `PARTIAL_STEP_RESULT_UNKNOWN` | the run did not return (`COMMAND_TIMEOUT`, `COMMAND_OUTPUT_LIMIT`, `GO_EXPIRED`, `COMMAND_FAILED`); `ENGINE_COULD_NOT_RUN_THE_CONTAINER` (125/126/127, no valid line), `SCRIPT_ENDED_BY_ITS_ALARM` (142), `OUTPUT_NOT_ONE_LINE`, `LINE_NOT_AS_SPECIFIED`, `EXIT_STATUS_NOT_AS_THE_LINE` (an OK line must exit 0, a refusal line 1); IDENT `SECOND_RUN_NOT_STARTED` |
| `STEP_RAN_ANSWER_NOT_AS_EXPECTED` | `CALENDAR_PIN_REFUSED_IN_THE_IMAGE`, `CALENDAR_EPOCH_MISMATCH`, `CALENDAR_PACKAGE_MISMATCH`, `CALENDAR_DOCUMENT_ORDER_MISMATCH`; `ROOT_IDENTITIES_REFUSED_IN_THE_IMAGE`, `IDENTITIES_DIFFER_BETWEEN_THE_TWO_RUNS`, `IDENTITIES_DIFFER_FROM_THE_HOST`; `CAPACITY_STARTUP_REFUSED_IN_THE_IMAGE` (the image's own code is in the line: `ROOT_IDENTITY_CHANGED`, `ROOT_NOT_PRIVATE`, `CAPACITY_CONFIG_*`, `FileNotFoundError`…), `CAPACITY_ROOTS_NOT_THE_THREE`, `CAPACITY_VETO_MODE_NOT_AS_SIGNED`, `CAPACITY_CONFIG_SHA_NOT_EQUAL`, `LOAD_IDENTITIES_DIFFER_FROM_THE_HOST` — a stop (MNT step 2: do not set the flag) |
| `STEP_RAN_EXPECTED_ANSWER_WITH_FINDINGS` | `CONTAINER_LISTING_UNAVAILABLE_AFTER_RUN`, `CONTAINER_OF_THE_STEP_STILL_LISTED`, `CONTAINER_PRESENT_THAT_WAS_NOT_THERE_BEFORE`, `WORKER_UNAVAILABLE_AFTER_THE_STEP`, `WORKER_CHANGED_DURING_THE_STEP`, `CAPACITY_TREE_UNAVAILABLE_AFTER_THE_STEP`, `CAPACITY_TREE_CHANGED_DURING_THE_STEP` |
| `PARTIAL_STATE_UNKNOWN_CONTAINER_MAY_REMAIN` | an escape after the start (the core's envelope) |

## 6. The receipt

Envelope of the core plus: `observed_at step effects clock commands_started mutating_calls (all 0) precheck{image,
capacity{parents_as_signed, root{device, inode, private}, children{name: device, inode, same_device_as_root},
identities}, config_file{regular, private, sha256_as_signed, bytes}, worker{id, started_at, restarts, running,
image_as_signed, mounts (count), capacity_mount{type, source_as_signed, read_only}}, containers_before, names_free}
containers[{name, state, returncode, code, seconds}] lines[{returncode, output_present, one_json_line,
valid, line}] (of an output that is not a valid line nothing but those booleans: no size, no digest, CORE rule 6) host_identities comparison{runs_agree, equal_to_the_host{name: bool}} containers_after{status, code,
before, after, not_there_before, names_present, rows[≤8]} worker_after{status, unchanged, code} tree_after{status,
unchanged, code} step_succeeded writes containers_run phase_reached`. A line is copied only after it met its grammar
(codes, hashes, a version name, booleans); of any other output nothing. No environment value, no text of
an exception, no secret: the identities are hashes of device and inode numbers; device and inode numbers, the worker ID
and the calendar line are host metadata, not secrets. Size ≤ 8 KB in the tests (no reduction is defined:
`REDUCTIONS=[]`).

## 7. Tests (offline)

| File | What |
|---|---|
| `tests/test_conformance.py` | the core's 121-test suite applied three times (one fixture per step = 363), the date-scope test replaced by the bands at both layers, the outcome test restated for CALENDAR and IDENT (as K11 does for PRE) |
| `tests/test_probe.py` | every plan refusal per member, the band edges, the literal effects per step, rows/classes/budget, the mounts template through the emulated CLI, script constants (alarm first, the one write, target, names, veto), every precheck refusal per step, a component replaced between lstat and open, the config file policy, the worker and its mounts, every verdict, every line grammar clause, findings after an expected answer, expiry, escape, no text of a line leaks |
| `tests/test_scripts.py` | the REAL scripts under `python -I -B -`: calendar-pin.py against the release's modules (3.12 env) and without them; IDENT with the release's AnchoredRoot on a real private tree (both interpreters) and its refusals; LOAD with a stub application on every branch, and with the release's own Settings and CapacityConfig up to their first refusals (hash, absent, not private); the digest equality with `r2d2_v2_store`; each script's `/app` insertion; the alarms (14 s, 34 s) |
| `tests/test_native.py` | the source's unmodified Native on a real temporary tree (core oslevel), a real program behind docker: IDENT and LOAD complete with the stub application reading the real numbers, CALENDAR with the real calendar-pin against the release, refusals; every open `O_NOFOLLOW`, no write flag, only `/` absolute |
| `tests/test_static_pins.py` | release files, opsart documents, calendar-pin.py extraction, epoch/order/package from the release, AnchoredRoot/bootstrap/Settings texts, Dockerfile `/app`, compose `:ro` line, the build's core and pins |
| `tests/test_linux_root.py` | `linux_root/probe_shape.py --self-test` on the emulation, its expectations false for each missing or different run, refusal outside a throwaway runner, `run.sh` text |

Result (revision 1): **582 tests, 582 passed** on `/usr/bin/python3` 3.9.6 and on the 3.12.14 environment (`night23-test-venv`),
none skipped (the release export and the deployment documents at hand through `work/`; the 3.12 environment supplies
the release's requirements for the real-module tests on both runs). Mutation: **285 single mutants, 285 killed, 0
survivors, 0 errors, 0 redundant, none by the time limit** on both interpreters (revision 1; revision 2: section 12).

The emulation needed no subclass of `hostemu`: the new inspect template uses only constructs it parses (variable
declared before a range and assigned in it, `if`, `not`, `json`), and the core's `RUN_PREFIX` is used unchanged.

### Mutation

`mutation/mutate.py` is tls_probe's (the core's) with its three tables changed (`SOURCE build/capacity_probe.py`,
`CARRIES op`, `TESTS`/`ORDER test_probe test_scripts test_native test_conformance`: the long conformance suite last, so
that a mutant of a script dies in `test_scripts.py` by its behaviour and not by the time limit). `mutation/mutants.py`:
285 single mutants, no combined one: constants (C), plan validation (V), every member of `effects_of` (E), the precheck
order and every refusal (P), the containers and the receipt (R), every clause of the three line grammars (G), every
branch of the verdict (X), and the scripts (S, each replaced whole with its recomputed pins: IDENT, LOAD and the
verbatim CALENDAR). Two candidates are not listed because they are equivalent by construction (said in mutants.py):
removing `stdin_of()` from `validate_members` (`effects_of` builds the same bytes with the same pin checks inside
`authenticate()` before any claim) and a `clean_path()` beside `CONFIG_FILE` (removed from the code: the grammar admits
no `/` after `config/` and starts with a letter or digit). The first full run had 3 survivors (a test name containing
"static" was deselected; a sorted extra root; a quote that `clean_path` refused first), the second 12 kills by the time
limit (a missing extra-member case; script mutants reached only after the conformance suite): each answered by a test
or by the order above, then both records were made again. Results: `mutation/MUTATION_RUN.json` (3.9) and
`mutation/MUTATION_RUN.py312.json` (3.12); `seal.py check` requires both complete with zero survivors and zero errors
and made against the sealed bytes.

## 8. Proven, emulated, UNPROVEN

**Proven offline here:** the identity algorithm equals the release's (`r2d2_v2_store.digest`, AnchoredRoot on a real
tree); calendar-pin.py prints the pinned epoch, package and order against the release's modules (on this workstation's
exchange_calendars 4.13.2); the release's Settings accepts the five values by name and CapacityConfig refuses by hash,
by absence and by privacy through AnchoredRoot; the source's Native walks and reads the real tree read-only; the runner
gives the exact argv, bytes and environment to a real process.

**Emulated only:** the Docker CLI and engine, the worker's inspect output, device numbers, uid 0.

**UNPROVEN (never executed anywhere; `linux_root/` is written to close the first five on a throwaway runner, NOT RUN):**

- **U-B1** that a read-only bind shows the host's device and inode numbers inside the container, so that IDENT's
  in-container identities equal the host-computed ones (MNT "Not verified": "Step 2 is the first measurement").
  User-namespace remapping would also break the owner check (`ROOT_NOT_PRIVATE`).
- **U-C1/U-C2** calendar-pin.py in the image under `--read-only`, `--network none`, `--cap-drop ALL` (exchange_calendars
  writing no cache), within 40 s; the image's library version and the pinned package.
- **U-L1** the application's import (pydantic, exchange_calendars) under `--read-only` and no network within the 34 s alarm;
  **U-L2** the SUCCESS of LOAD with the real static config: no valid config exists offline (B5 delivers it), the CI job
  only reaches the refusal by the config's fields.
- **U-W1** `MOUNTS_FORMAT` on the host's engine (the `if`/`not` constructs inside a range were not run on this host).
- **U-W2** that `.Mounts[].Source` equals the path written in `.env` byte for byte (the engine may print a resolved path);
  the MNT step 1 compares `realpath` first, and this source refuses any other text (`WORKER_CAPACITY_MOUNT_OTHER_SOURCE`).
- **U-P1** that uid 0 with no capability can open the root-owned 0700 tree through the bind (it is the owner, so no
  `CAP_DAC_OVERRIDE` is needed; reasoned, not run).
- **U10 of the core** a container that outlives its CLI: CALENDAR has no alarm of its own (verbatim bytes).

## 9. Deviations from the core's rules and from the template

None from the core's assembler rules (it builds; `--check` BUILD_EQUAL). Against the template (`tls_probe`) and the brief:
1. `PARTS` adds `parents`; the template carried `core runner docker`.
2. One new READ row, `worker_mounts` (fixed template over `.Mounts`, no `Env`, accepted by assemble's rule 5).
3. `RUN_PREFIX` unchanged: no `--log-driver none` (tls_probe adds it). The lines are not secrets; with a journald or
   syslog default log driver the engine would keep them on the host (Q4).
4. `MAX_GATE_SPAN_SECONDS=3600` (tls_probe 900, under A1's short-window rule; A2 gives reads 3600).
5. No retention tag: the image is read by ID with its revision label only (A5 forbids a tag); LOAD also requires the
   worker to run that same ID.
6. Three conformance fixtures (one per step) instead of one; per-step outcomes as K11's PRE/POST.
7. The config file is read on the host by the source (hash compared in memory), beyond the brief's precondition list.
8. The tree is verified again after the containers; the core's `Pinned.verify` maps an `OSError` of its own reads to
   `PARENT_REPLACED`, so an unreadable tree after the run is reported CHANGED, any other failure UNAVAILABLE.
9. The worker is read again after LOAD (ID, running, image, restart count).
10. Mutation: S-mutants cover the CALENDAR script as well (it is carried byte for byte; a mutant is killed by the runs).

## 10. Open questions for Codex

- **Q1** Evidence: `EVIDENCE_OPERATIONS=()` for the source (one tuple for three steps; requiring K6b's
  `GO_WRITE_HOSTOPS02_CAPACITY_SWITCH_01` would forbid CALENDAR and IDENT before B4). LOAD carries
  `mount_receipt_sha256` as a signed plan member shown in effects; the source cannot check it against the request's
  evidence list (perform does not see the request). Alternative: a second source for LOAD with that evidence operation.
- **Q2** Band of LOAD: read as A2's "a mesma faixa, depois do B4" = B4's band (Mon–Thu 20:38–23:30Z, no Sunday). The brief
  said "B4c same band" after the A5 bands; if a Sunday LOAD is wanted, `B4C_BANDS` changes (one line, new hashes).
- **Q3** Gate 3600 s (read) vs a 900 s short window.
- **Q4** `--log-driver none` for these containers too (a row prefix of their own, as tls_probe did)?
- **Q5** The config directory's identity is reported, not required. Should IDENT require it?
- **Q6** CALENDAR has no alarm (verbatim bytes): a hung import keeps its container until it ends (U10); the receipt says
  whether it is still listed. Prefixing an alarm would change the pinned hash.
- **Q7** IDENT pins the parents by rows but not the root and children by inode: the run establishes them. Should a LOAD
  plan also sign the three identities IDENT printed and compare them (the config pins them anyway)?
- **Q8** LOAD does not refuse a worker with restarts > 0 (only reports them and compares after). Refuse?

## 11. Reproduce

```
python3 -B ../core/assemble.py --check .                 # BUILD_EQUAL
python3 -B seal.py check                                  # SEAL_OK
python3 -B -m pytest -p no:cacheprovider -q tests         # /usr/bin/python3 (3.9) and night23-test-venv (3.12)
python3 -B mutation/mutate.py check | run                 # HOSTOPS_MUTATION_PYTHON, HOSTOPS02_TEST_APP_PYTHON
```
`work/release` and `work/opsart` (not sealed) point at the read-only exports of the release and of the deployment
documents; without them the static and real-module tests skip and say so.

## 12. Revision 2 (after an independent review of LOAD, 2026-10-04)

| # | Finding | Change |
|---|---|---|
| 1 HIGH | LOAD checked only the mount at exactly `/c3po-capacity` | every OTHER worker mount is refused when its destination lies under `/c3po-capacity/` or its absolute source is the root, below it, or an ancestor of it (`/`, `/var`, `/var/lib`…); sources that are not paths (tmpfs) and siblings (`/var/lib/c3po-capacity2`, docker volumes) pass; tested in both orders |
| 2 HIGH (design) | the fresh container is not the worker's mount namespace: a tree re-provisioned after the worker started passes LOAD while the worker would loop | no `/proc` read. Mitigation, reported and not judged: `precheck.worker.root_changed_after_the_worker_started` = the root's `st_ctime_ns` (read on the held descriptor) later than the worker's `StartedAt` (parsed to the nanosecond; `None` when unparsable). A re-provisioned root is a new directory whose ctime is its creation; the root's ctime also moves when an entry of the root is added or removed or its metadata changes, never when a file is delivered into a child. **UNPROVEN (U-N1)** that the worker's own mount namespace holds the same tree: Q9 |
| 3 MEDIUM | the worker's settings were never read | `container_environment` on the worker ID (one more QUICK read; booleans only; the compared values are the signed ones): release pin present AND equal (absent is refused: the worker's own `CapacityConfig` compares `settings.r2d2_v2_shadow_release_sha` with the config's `release_sha`, so with the pin absent setting the flag would loop the worker on `CAPACITY_CONFIG_RELEASE`, while LOAD, which passes the signed sha itself, would succeed; K6a's activation writes it), mount source present and equal to the signed root (K6b's first line; it ties the bound root to K6b's block), the four capacity settings absent or equal (`REQUIRED=true`, veto `DISPATCH_AND_DERIVATION_ONLY`, as `k6b/op.py` `CAPACITY_KEYS`, `VETO_MODE_VALUE`, `REQUIRED_VALUE` write them) |
| 4 LOW | `config_sha_equal` compared the settings' copy with itself | the LOAD script prints `config_sha256` = SHA-256 of `config.config_root.read(config.name)` (read again through AnchoredRoot); the source compares it with the signed hash. LOAD script now 2050 bytes, `c3019efa…a99c` |
| 5 LOW, CORE rule 6 | an output that is not a valid line left its size and SHA-256 in the receipt | only `output_present` and `one_json_line` remain |
| 6 LOW | an entry of the root that is not a directory was bound unchecked; root path not tied | every entry directly in the root must be a directory (at most 64 entries). The root path stays a signed member, not a constant (K6b also signs it from rows): its tie to the mount is the binder's check, and in LOAD the source checks it three times on the host (the worker's bind source, the worker's `C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE`, the walk by the signed parent rows) |

Also: the conformance suite ran again against the final sibling `k6b/build` (`ASSEMBLY.json` sha256
`be934497b239b135f31edf6deee47ed74864a652223b525ccbe3d58cb1d8c0fb` when the suites ran). Tests: 590 on each interpreter,
590 passed. Mutation: 313 single mutants (28 new: W01–W17 mounts and settings, T01–T05 root entries, K01–K05 the ctime
report, X34; five rewritten for the changed code), results in the two records.

New open questions: **Q9** whether LOAD should also require that the root did not change after the worker started (today
reported only), or a read in the worker's own namespace under its own authorisation. **Q10** whether a worker whose release
pin is absent should be accepted before K6a (refused now, reason above).
