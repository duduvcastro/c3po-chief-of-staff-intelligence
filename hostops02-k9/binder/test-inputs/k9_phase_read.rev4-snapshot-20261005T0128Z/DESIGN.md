# K9R — the read program of the delegated daily phases (HOSTOPS02): design, revision 4

**Revision 4 (2026-10-04): answers to the adversarial review of revision 3 (`32e3ebf3…`, no BLOCKER, three MAJOR).** Revision 3 is kept sealed as `../k9_phase_read.rev3-32e3ebf3`.

- **M1 — the image before the secret-bearing container.** PROBE now reads the signed image ID first (`image`, QUICK ≤ 8 s) and starts the container only when the image is present by that ID with the revision label dd4ec4bb; otherwise `probe` is `PROBE_NOT_STARTED_IMAGE_NOT_AS_SIGNED` and no container exists. The container still has its 44 s: after one QUICK read at most 8 s of the 60 s budget are gone.
- **M2 / M3 — the answer is never COMPLETE or READY beside a finding or a gap.** RESULT: a phase decided COMPLETE becomes `UNCERTAIN / OBSERVATION_INCOMPLETE` when any deciding item could not be observed, and `UNCERTAIN / FINDINGS_BESIDE_THE_STEP` when any finding exists anywhere in the receipt (a source root or a K9 directory not as signed or missing, a directory replaced during the run, another boot, a file not private, …). PROBE: `readiness` is `UNKNOWN` whenever the run stopped, an item could not be observed, or any finding other than `PROVIDER_NOT_READY` exists; READY and NOT_READY therefore only stand alone. This is what CONTRACT section 4 says.
- **Grammars that cannot carry a ticker.** A runner's count keys are lower-case snake case with at least one underscore (`K9_COUNT_KEY`); the packaged executor's count keys are a closed list read from its code (`symbols captured coverage_verified coverage_unknown db_comparable db_equal db_different http_attempts b3_skipped READY COMPLETED_NULL`); a failure code is upper-case snake case with at least one underscore (`K9_CONSTANT_CODE`; the packaged executor's one code without, `INTERRUPTED`, is named); a snippet code is that, or the CamelCase name of a class. Anything else makes the receipt or the line **not of this step** (refused), never copied. Residual: a code such as `BRK_B` has the grammar; tickers carry `-` or `.`, not `_`, in the provider's codes.
- **Step files tied to the launch.** A start marker and a receipt (runner's or packaged) must start at or after the launch record's `created_at` and the container's `StartedAt`, and a receipt must complete at or before the container's `FinishedAt` (docker's nanosecond instants are parsed to microseconds); otherwise not of this step. The packaged receipt must name the SHA-256 of the previous phase's receipt in the same spool (`preflight` for acquire, `acquire` for execute); a FAILED file may name it or null. Consequence: without an inspected container no step file is valid (the native test now shows this; the re-hash of outputs is exercised on the emulation only).
- **Probe limits.** The probe row's fixed words gain `--memory 2g --pids-limit 256` (the core's grammar admits them: they are not `-v`, `--mount`, `--device`, `--cap-add`, `--privileged` or `-d`; the command stays 10 words). Unproven on the host (N-7).
- **Minimum eligible.** The signed readiness rule is `{numerator 95, denominator 100, minimum_eligible 4000}`: READY needs at least 4,000 eligible names (E28's rule had only "more than zero"; the producer's own measurement is 6,001 rows of the selectable classes, `r2d2_v2_producer_daily.py` build_daily_contract; 4,000 is two thirds of it). In the snippet and recomputed on the host.
- **K9 chains as K4-E0 has them.** Every component of a K9 chain (the four of `parent_rows` from the bytes, and every K9 directory in TREE) must also be in group 0 and not setgid (`CHAIN_ROW_NOT_ROOT_GROUP` before any claim; `ROWS_NOT_ACCEPTABLE_TO_THE_K9_REQUESTS` with the component listed in TREE).
- **Codex's decision 6 (#429, comment 5985748037), folded into rev 4.** `source_root` moves to `/var/lib/c3po/r2d2-v2-source-20261005` under the same root-only chain as `k9_root`: no open root, every component uid 0, gid 0, not setgid, not group/other-writable, the directory root:root 0700 (`CHAIN_ROW_UNSAFE` / `CHAIN_ROW_NOT_ROOT_GROUP` before any claim; TREE findings with the component listed). Its filesystem must be the one of `days/` (single floor): `k9_filesystem` gives `SOURCE_ROOT_NOT_ON_THE_FILESYSTEM_OF_DAYS` otherwise (the source root is proved again first). The data volume is now read only for the September secret sources (lstat only, the volume as open root) and by POLICY (the policy and release files install_release and activate put there, read against signed rows). **Consequence to check (not K9R's to fix):** the worker reads `C3PO_R2D2_V2_SHADOW_SOURCE_DIR`; with the source root off the data volume, the worker's compose service needs a read-only bind of `/var/lib/c3po/r2d2-v2-source-20261005` (today it binds only the data volume at `/app/day-d-data`).
- **September secret sources (coordinator's addition to rev 4).** K3-K9 signs the identity of the two September secret sources from a prior read, and TREE is that read: item `september_sources` (section 2.4).
- **Open items** (not changed): (5) `DOCKER_CONFIG` and (7) — section 10.


**Revision 3 (2026-10-04): Codex's decisions in #429 comment 5984327121.** ACL: option (c) of 0.1 below (the mode-mask argument; the coordinator's message calls it "option (a)") accepted as fulfilling N-8, with the wording of 0.1. SPACE: the signed floor is 214,748,364,800 bytes (200 GiB) available on the filesystem that contains `days/`, measured by `fstatvfs` on the open descriptor of `days/` as `f_bavail * f_frsize` (never `f_bfree`); below it the receipt says `hold: true` (finding `DISK_FREE_BELOW_FLOOR`); the source root's capacity is reported separately and never counted toward `days/`. Revision 2 (`acb151d3…`) is kept sealed as `../k9_phase_read.rev2-acb151d3`.

**Revision 2 (2026-10-04): placement per Codex's N-8 decision** (`W/codex-n8-placement-20261004.txt`, sha256 `d30f7f9048af4a39cf4fa7d9f49292ad387a2d41f33bad39816e83d3d1fc2c53`). Revision 1 (`SHA256SUMS` af879843…) is kept sealed beside this directory as `../k9_phase_read.rev1-af879843`; its SUMMARY as `../SUMMARY.rev1-af879843.md`. What changed: section 0 (with 0.1 on ACLs), the TREE read (2.4), sections 8–11.

Offline work only. Nothing here was run on the host, pushed, bound or dispatched. Every hash is taken by command (`SHA256SUMS`, `../SUMMARY.md`).
Built on the frozen core generation `4c24c5cf…d0d6` (seal `CORE_SHA256SUMS` 73fb546b…c9b1, by command; `seal.py check` SEAL_OK. K11 cites `c13ce685…2f9f` for the same generation: the core's `CORE_SHA256SUMS` on disk (dated 2026-10-02 22:52 local) is not the file K11 recorded); the core was not edited (it is reached through the link `../core` → `../hostops02-sealed/core`).
Specified by `K9_INTERFACE_NOTE.md` revision 2 (`ab5159be…596c`, the bytes the Act B build carries in `fable-actb03-20261004/k9/`), sections 1 (F5, F9a, F10), 2, 3.1, 3.3 (`readiness_probe`, `readiness_recheck`, `*_result`, `policy_read`), 4.1–4.3 and 6.

Abbreviations. `W` = `$W`, the epoch's work directory beside this candidate (`../..` of this directory); `S` = `$S`, the scratch directory that holds the release export (given to the tests as `HOSTOPS02_TEST_RELEASE_EXPORT=$S/docs03/recert03/export`). `NOTE` = the K9 note. `R` = `c3po/backend/app/` of the release tree dd4ec4bb (`S/docs03/recert03/export/tree`, the tar `61bf5dd5…7660`). `E28` = `W/r2d2-plan-b-baseline-20260927`. `D` = the session the eve prepares. `Dd` = `<k9_root>/days/<D>`.

---

## 0. PLACEMENT (N-8) — decided by Codex on 2026-10-04 (a location decision, not a GO of these bytes)

Compiled into the sealed bytes (`K9_PLACEMENT` in `op.py`, one place, carrying the decision's sha256); the provider env file is a **fixed word of the probe row**. A request signs the same object (`constants.placement`, compared byte for byte). Any change is a new payload hash and a new review. The K4-E0 and K3-K9 drafts beside this work use the same paths (read by command on 2026-10-04).

| Constant | Value | Rule (the decision) |
|---|---|---|
| `k9_root` | `/var/lib/c3po/r2d2-v2-k9-20261005` | under a chain controlled by root alone: **no open root**, no ancestor owned by uid 1000, none writable by group or other, no link; new directories root:root 0700 |
| `days`, `tools`, `claims`, `secrets`, `secrets/emitter` | `<k9_root>/…` | root:root 0700 |
| `secrets/provider.env`, `secrets/risk-db.env`, `secrets/emitter/password` | `<k9_root>/secrets/…` | root:root 0600 (K9R only lstats them; the probe's `--env-file` word is `/var/lib/c3po/r2d2-v2-k9-20261005/secrets/provider.env`) |
| `tools/k9_runner-<sha256>.py` | | root:root 0600 (E0) |
| `source_root` | `/var/lib/c3po/r2d2-v2-source-20261005` | **decision 6**: the same root-only chain as `k9_root` (no open root, gid 0, no setgid, 0700), on the filesystem of `days/`; signed chain, proved again at each use; divergence or replacement refused (the phase is UNCERTAIN). Before decision 6 it was `/mnt/day-d-data/r2d2-v2-source-20261005` with the volume as open root |
| `/var/lib/c3po` | | never presumed: E0 creates it only if absent, by a signed effect (the K4-E0 draft does so); TREE reads its row |

What enforces it in K9R:

- **From the bytes, before any claim** (`validate_plan`): the four K9 chains of `parent_rows` (days, secrets, tools, claims) must carry `open_root` null and pass the core's `validate_chain` with no open root: every component from `/` owned by uid 0 and not writable by group or other (`CHAIN_ROW_UNSAFE`); days and claims receive entries, so their leaf may not be setgid. The source root's chain carries the data volume as open root (`CHAIN_ROW_WORLD_WRITABLE` still applies below it).
- **On the host, TREE** (section 2.4): the chain `/ → /var → /var/lib → /var/lib/c3po → k9_root → …` walked by descriptor without following a link (a link anywhere is a finding, never followed); ownership, mode and identity (device, inode) of every component in the receipt; `components_not_root_controlled` lists any component that is not root's and closed; the K9 directories exactly 0:0 0700; the K9 tree on one filesystem (no mount inside it) and not on the device of the source root; its mount point by device change; free bytes against the signed floor, free inodes reported.
- **On the host, every later read**: the K9 chains walked against the signed rows (`PARENT_IDENTITY_MISMATCH`: the directory is not held, nothing below it is read); the source root likewise, and proved again before each output it hashes (`PARENT_REPLACED`): a divergence or replacement makes the phase UNCERTAIN, the read's form of a refusal.

### 0.1 ACLs: what K9R can and cannot prove (accepted by Codex, #429 comment 5984327121)

**What it proves, and only that:** no effective access and no write by any ACL entry — not the absence of ACL entries. **Conditioned on a filesystem with POSIX ACL semantics** (Linux ext4/xfs/btrfs and the like), **not NFSv4 or CIFS ACLs**, where the mode bits do not bound the ACL. The core does not expose the filesystem type (its `free_bytes` reads `fstatvfs`, which has no `f_type` in Python's `os.statvfs_result`, and the core has no `statfs` and no mount table): TREE reports `filesystem_type: NOT_EXPOSED_BY_THE_CORE` in `k9_filesystem`, and the POSIX condition stays a reviewer's fact about the host (K9R-U12).


**The frozen core cannot read ACLs.** Its `NativeRead` has no `getxattr`/`listxattr`, and an operation part may make no system call of its own (core rule 4, enforced by the assembler). So K9R **does not prove the absence of an ACL**; that stays **unproven** (K9R-U10). What it does prove, and why it covers the effect that matters:

- On Linux with POSIX ACLs, when an object has an extended ACL the group bits of `st_mode` are the ACL **mask**, and the effective rights of every named user, named group and the owning group are bounded by it.
- TREE requires every K9 directory to be exactly 0700 and every secret file and the runner exactly 0600: group bits 000, so the mask is empty and **no ACL entry grants anything effective** on them.
- Every ancestor must be owned by root and closed to group and other writes: a mask without `w`, so no named entry can write, rename or replace anything in it. A named entry could still be granted read or search on an ancestor (`/var/lib` 0755); that grants no control.
- Not covered: an ACL that exists but grants nothing effective; filesystems whose ACL model is not POSIX.

Proposals to close it (Codex's choice): (a) a later core generation adds one read primitive, `NativeRead.acl_names(fd)` = `os.listxattr(fd)` filtered to `system.posix_acl_access` / `system.posix_acl_default`, and TREE reports "no extended ACL" per component; (b) a host readback runs `getfacl -p --absolute-names` on the chain (a new command row; `getfacl` is not a tool of the core: also a new generation); (c) accept the mode-mask argument above in writing.

## 1. What it is

One reading source (`WRITES_ALLOWED=False`, `ACTIVATION_ALLOWED=False`, date class `READ` 2026-10-02…10, gate at most 3,600 s), parts `core runner docker parents` (no `files`, no `lock`), four signed modes:

| Mode | Operations (K9_OPERATIONS.json, READ) | Reads | Commands | Success outcome (exit 0) |
|---|---|---|---|---|
| RESULT | `collect_result`, `commit_result`, `publish_result`, `components_result`, `sources_result`, `acquire_result`, `execute_result`, `capture_result` | the launch record, the container by ID, the start marker and the one receipt (runner's or packaged), the named outputs hashed again | 1 × `launched` (QUICK) | `K9_PHASE_RESULT_COMPLETE_ALL_OBSERVED` (= `COMPLETE_OUTCOME`) |
| PROBE | `readiness_probe`, `readiness_recheck` | secrets directory and the provider env file (lstat), one attached container running the pinned snippet, the image | 1 × `probe` (RUN, CONTAINER), 1 × `image` (QUICK) | `K9_READINESS_READY_ALL_OBSERVED` |
| POLICY | `policy_read` | the installed policy and release files on the host, the worker's state and five environment names (booleans), the image | `container`, `container_environment`, `image` (QUICK) | `K9_POLICY_AND_WORKER_AS_EXPECTED_ALL_OBSERVED` |
| TREE | none (weekly prerequisite read, NOTE 4.1, 6.2) | rows of every K9 directory and of the source root, the boot, secret-file metadata, the runner's hash, free space | none | `K9_TREE_AS_REQUIRED_ALL_OBSERVED` |

Exit 2 (`OBSERVED_ALL_EXPECTATIONS_NOT_MET`) for a complete observation with findings — **including a phase that FAILED or is UNCERTAIN and a provider that is NOT_READY**; exit 2 (`PARTIAL_OBSERVED`) when an item could not be observed or the run stopped; exit 1 (`REFUSED_NOTHING_OBSERVED`) before any observation. The receipt carries the answer the chain needs at its top level: `phase_result` (COMPLETE / FAILED / UNCERTAIN) and `phase_reason` for RESULT, `readiness` (READY / NOT_READY / UNKNOWN) for PROBE, `boot_id_sha256` for TREE. So nothing downstream can read exit 0 as "go" unless the phase completed or the provider is ready.

Each item is observed on its own (the K11 pattern): a failed observation is `UNAVAILABLE` with a constant code, never an absence; a mismatch is a finding that leaves every other item in the receipt; `GO_EXPIRED`/`CLOCK_REVERSED` stop the run (RESULT then says `UNCERTAIN / RUN_STOPPED`).

## 2. What each mode reads, in order

Common start: executor uid/gid 0 (`EXECUTOR_IDENTITY`), then the window of D (pure, section 7.2), then `boot` (the boot id hashed; RESULT/PROBE/POLICY compare with `evidence_boot_id_sha256`, a mismatch is `EVIDENCE_FROM_EARLIER_BOOT` and the signed rows are then compared without the device; TREE reports `boot_id_sha256`). End: `directories_stable` (every held directory proved again from `/`).

### 2.1 RESULT

| # | Item | How |
|---|---|---|
| 1 | `directory:DAYS`, `directory:SOURCE_ROOT` | `walk_pinned` against the signed `parent_rows`, `O_NOFOLLOW|O_NOATIME` by `dir_fd`; held |
| 2 | `day_directory` | `Dd` = the entry `<D>` of the held days directory: lstat-classified, opened without following, held. Finding `DAY_DIRECTORY_NOT_PRIVATE` unless 0:0 0700 |
| 3 | `launch_record` | `Dd/launches/<launch>.json` (`K9_LAUNCH_RECORD_V1`, section 5): exact keys; epoch, D, launch operation, the launch's attempt key, slot, request and step-plan hashes, 64-hex container ID, the container name `c3po-k9-<yyyymmdd>-<launch>`, `created_at ≤ started_at ≤ run_not_after`, `timeout_seconds` 1–7200. `LAUNCH_RECORD_INVALID`, `LAUNCH_RECORD_NOT_PRIVATE` |
| 4 | `launched_container` | only for a valid record: `docker container inspect --format <K9_LAUNCHED_FORMAT> <ID>`; the line member by member (`LAUNCHED_METADATA_INVALID`); `as_recorded` = name, image ID = the signed `image_id`, label `c3po.k9.attempt_key` = the launch's key, label `c3po.k9.request_sha256` = the record's; `exited` = state `exited` and not running. Findings `LAUNCHED_CONTAINER_NOT_AS_RECORDED`, `LAUNCHED_CONTAINER_NOT_EXITED` |
| 5 | `step_receipts` | runner: `Dd/receipts/<launch>.{STARTED,RECEIPT,FAILED}.json`. Packaged (`acquire_launch`, `execute_launch`): the SHA-256 of `Dd/risk/plan/HOST_PLAN.json` and `GO.json` computed on the host, then `Dd/risk/spool/<HOST_PLAN sha256>/<phase>.{STARTED,RECEIPT,FAILED}.json` (`R/r2d2_v2_risk_host_executor.py:327-389`). Each validated against its contract (section 5); counts copied only in their grammar |
| 6 | `outputs` | only for a valid receipt: runner — every `outputs` key (`day/<path below Dd>` or `source/<path below the source root>`) read again by `dir_fd` without following and hashed, every `aggregates` directory recomputed (section 5); packaged — `acquired/acquired.json` (acquire), `assessment/<manifest>`, `risk-output/MANIFEST.json`, `risk-output/risk.json` (execute). Per-name blobs of sources, acquire and execute are not re-hashed (NOTE 3.3). `OUTPUT_NOT_AS_THE_RECEIPT_SAYS` |

**Phase decision** (`k9_phase_result`, pure, first match wins):

| Condition | phase_result / phase_reason |
|---|---|
| any of items 2–5 not COMPLETE (UNAVAILABLE: inspect failed, i.e. absent or broken; a link; unreadable JSON) | UNCERTAIN / OBSERVATION_INCOMPLETE |
| no `Dd` · no record · invalid record | UNCERTAIN / DAY_DIRECTORY_ABSENT · LAUNCH_RECORD_ABSENT · LAUNCH_RECORD_INVALID |
| container not as recorded · not exited | UNCERTAIN / CONTAINER_NOT_AS_RECORDED · CONTAINER_NOT_EXITED |
| RECEIPT and FAILED both | UNCERTAIN / RECEIPT_AND_FAILED_BOTH_PRESENT |
| a start marker of another step | UNCERTAIN / START_MARKER_NOT_OF_THIS_STEP |
| RECEIPT: invalid · no marker · exit ≠ 0 or OOM · outputs differ | UNCERTAIN / RECEIPT_NOT_OF_THIS_STEP · RECEIPT_WITHOUT_START_MARKER · EXIT_CODE_CONTRADICTS_THE_RECEIPT · OUTPUTS_NOT_AS_THE_RECEIPT_SAYS |
| RECEIPT valid, marker valid, exit 0, not OOM, outputs equal | **COMPLETE** |
| FAILED invalid | UNCERTAIN / FAILED_RECEIPT_NOT_OF_THIS_STEP |
| FAILED with DEADLINE (runner) or UNCERTAIN (packaged) | UNCERTAIN / STEP_REPORTS_DEADLINE_OR_UNCERTAIN |
| FAILED with REFUSED/FAILED (runner) or REFUSED (packaged) | FAILED / STEP_REPORTS_FAILED_OR_REFUSED |
| marker, no receipt | UNCERTAIN / STARTED_WITHOUT_RECEIPT |
| no marker, no receipt, exit 0 | UNCERTAIN / EXIT_ZERO_WITHOUT_RECEIPT |
| no marker, no receipt, exit ≠ 0 | FAILED / EXITED_BEFORE_ITS_START_MARKER (the runner writes its marker before any provider or database call) |

A phase that is not COMPLETE adds the finding `PHASE_RESULT_FAILED` or `PHASE_RESULT_UNCERTAIN`. Metadata findings (non-private files) do not change the phase decision; they make the run exit 2.

### 2.2 PROBE

| # | Item | How |
|---|---|---|
| 1 | `directory:SECRETS` | `walk_pinned` against the signed rows; held |
| 2 | `secret:SECRETS/provider.env` | lstat in the held directory only: type, owner, mode, links. Never opened by this process, never its size or a digest. `SECRET_FILE_ABSENT`, `SECRET_FILE_NOT_PRIVATE` (not a regular 0:0 0600 file with one link) |
| 3 | `probe` | (rev 4: read after item 4, which runs first) started only when item 1 is held, item 2 is the private regular file of root (`PROBE_NOT_STARTED_ENV_FILE_NOT_AS_REQUIRED` otherwise) and item 4 found the signed image ID with the signed revision (`PROBE_NOT_STARTED_IMAGE_NOT_AS_SIGNED` otherwise): no container in either case. The secrets directory is proved again, then `container_run` (section 4). The line is validated member by member and the readiness recomputed from its counts (`PROBE_OUTPUT_INVALID` otherwise). Findings: `PROVIDER_NOT_READY`, `PROBE_SNIPPET_FAILED` (with `snippet_code`), `PROBE_RUN_FAILED`, `PROBE_ENGINE_FAILURE` (125/126/127). A CLI killed by its limit: UNAVAILABLE with `container_may_still_exist: true` |
| 4 | `image` | **first command of the run (rev 4)**: `image_facts` of the signed image ID: present, revision label = dd4ec4bb (`IMAGE_ID_MISMATCH`, `IMAGE_REVISION_MISMATCH`); it gates item 3 |

### 2.3 POLICY

| # | Item | How |
|---|---|---|
| 1 | `directory:POLICY`, `directory:RELEASE` | `walk_pinned` against the signed rows of the directory activate created and of the release directory install_release created (rows from the K11 POST or activate receipts; open root = data volume) |
| 2 | `policy_file` | read by `dir_fd` (≤ 8,192 bytes): SHA-256 = `constants.policy_sha256` (the Act B `policy_sha`), 0:0 0600 one link, `valid_from ≤ now < valid_until` at the instant of the read (`POLICY_SHA_NOT_THE_SIGNED_ONE`, `POLICY_FILE_NOT_PRIVATE`, `POLICY_FILE_ABSENT`, `POLICY_OUTSIDE_ITS_WINDOW`, `POLICY_WINDOW_UNREADABLE`). Nothing of the content leaves |
| 3 | `release_file` | the same (≤ 65,536 bytes) against `constants.release_sha256` |
| 4 | `worker` | `container_facts` of the signed worker container: running, image ID = signed (`WORKER_NOT_RUNNING`, `WORKER_IMAGE_NOT_THE_SIGNED_ONE`); restart count and health reported, not gated |
| 5 | `worker_environment` | `container_environment` (booleans) for five names: `C3PO_R2D2_V2_LIVE_POLICY_FILE` / `_SHA`, `C3PO_R2D2_V2_SHADOW_RELEASE_FILE` / `_SHA` with the values activate wrote (host path → worker path through the data bind), and `C3PO_BUILD_SHA` = dd4ec4bb (`WORKER_LIVE_NAMES_NOT_AS_SIGNED`, `WORKER_BUILD_REVISION_MISMATCH`) |
| 6 | `image` | as PROBE item 4 |

### 2.4 TREE

| # | Item | How |
|---|---|---|
| 1 | `directory:K9_ROOT`, `DAYS`, `TOOLS`, `CLAIMS`, `SECRETS`, `EMITTER`, `SOURCE_ROOT` | `descend` from `/` without following a link (`SYMLINK_COMPONENT`, `PARENT_MISSING` are findings); rows (path, device, inode, uid, gid, mode of every component) **always in the receipt** (`observed_rows`), with `open_root` (null for all of them since decision 6) and `components_not_root_controlled` (every component that is not uid 0 and gid 0, is setgid, or is group/other-writable). Each directory exactly 0:0 0700 (`DIRECTORY_NOT_ROOT_PRIVATE`); the rows acceptable to the K9 requests (`validate_chain` with that open root: `ROWS_NOT_ACCEPTABLE_TO_THE_K9_REQUESTS`); mount point by device change reported for every directory (the data volume's mount point is judged in item 5) |
| 2 | `k9_filesystem` | k9_root, days/ and the source root proved again; every held K9 directory on k9_root's device (`K9_TREE_SPANS_FILESYSTEMS`, with the keys); the source root on the filesystem of days/ (`SOURCE_ROOT_NOT_ON_THE_FILESYSTEM_OF_DAYS`, decision 6; rev 3's `K9_TREE_ON_THE_DEVICE_OF_THE_SOURCE_ROOT` and the separate source capacity are gone); `days_bytes_available` = `f_bavail * f_frsize` of `fstatvfs` on the open descriptor of `days/` against the signed floor 214,748,364,800 (`constants.disk_floor_bytes` must equal the compiled `K9_DISK_FLOOR_BYTES`, else `DISK_FLOOR_NOT_THE_COMPILED_ONE` before any claim); below it `hold: true` and `DISK_FREE_BELOW_FLOOR`; `days_inodes_available`; `source_root_on_the_filesystem_of_days`; `filesystem_type: NOT_EXPOSED_BY_THE_CORE` |
| 3 | `secret:SECRETS/provider.env`, `secret:SECRETS/risk-db.env`, `secret:EMITTER/password` | lstat only (as PROBE item 2) |
| 5 | `september_sources` | the data volume walked from `/` (rows in the receipt; judged with the volume as open root: `DATA_VOLUME_ROWS_NOT_ACCEPTABLE`; its mount point the volume: `DATA_VOLUME_NOT_A_MOUNT_POINT`); then, below it, **by lstat only**, `.r2d2-v2-risk-secrets`, `.r2d2-v2-risk-secrets/risk-database-url`, `.c3po-role-executor-20260908-r2`, `…/secret`, `…/secret/password`: per component `device, inode, uid, gid, mode, mtime_ns, ctime_ns, nlink, is_link` (never a size, a length or a digest; a directory is opened by descriptor without following a link only to reach the next name; the two files are never opened). Findings: `SEPTEMBER_SOURCE_ABSENT`, `SEPTEMBER_SOURCE_IS_A_LINK` (not followed), `SEPTEMBER_SOURCE_ON_ANOTHER_DEVICE` (than the data volume), `SEPTEMBER_DIRECTORY_GROUP_OR_WORLD_WRITABLE`, `SEPTEMBER_SOURCE_NOT_A_DIRECTORY` / `NOT_A_REGULAR_FILE`. K3-K9 signs these values; owner and mode of the files are reported, not gated (the rules on them are K3-K9's) |
| 4 | `runner_file` | `tools/k9_runner-<constants.runner_sha256>.py` read (≤ 4 MiB) and hashed: the signed hash; 0:0 0600 one link (`RUNNER_FILE_ABSENT`, `RUNNER_BYTES_NOT_THE_SIGNED_ONES`, `RUNNER_FILE_NOT_PRIVATE`) |

The binder copies `observed_rows` of DAYS, SOURCE_ROOT, SECRETS, TOOLS, CLAIMS into `parent_rows` (open root null for all five chains, decision 6) and `boot_id_sha256` into `evidence_boot_id_sha256` of every K9 request of the week (tested: a TREE receipt's rows make a RESULT request that authenticates).

## 3. Every fixed word

```
probe (CONTAINER, RUN 40 s, stdin):
  docker run --rm -i --pull never --init --user 0:0 --network bridge --read-only --cap-drop ALL --security-opt no-new-privileges
    --memory 2g --pids-limit 256 --env-file /var/lib/c3po/r2d2-v2-k9-20261005/secrets/provider.env --env C3PO_R2D2_V2_PRODUCERS_ENABLED=true
    --name c3po-k9-<yyyymmdd of D>-<readiness_probe|readiness_recheck> <signed image ID>
    timeout -s KILL 36 python -I -B - <D> <request sha256>            (10 command words; the core allows 16)
  standard input: the pinned snippet (K9_PROBE_SNIPPET, 4,226 bytes, sha256 b4074aa3…8433), nothing else
launched (READ, QUICK): docker container inspect --format <K9_LAUNCHED_FORMAT> <64-hex ID>
  K9_LAUNCHED_FORMAT: name, id, image_id (.Image), state (.State.Status), running, exit_code, oom_killed, started_at,
  finished_at, and the labels c3po.k9.attempt_key / c3po.k9.request_sha256 (index .Config.Labels). Never .Config.Env.
image (READ, QUICK): the core's IMAGE_FORMAT, the signed image ID
container (READ, QUICK): the core's CONTAINER_FORMAT, the signed worker name           (POLICY)
container_environment (READ, QUICK): the core's template, five names, the worker's ID (POLICY)
```

No `docker ps`, no `docker rm`, no `exec`, no bind, no `systemctl`. The probe prefix passes the assembler's rules for an attached run (`run --rm`, `--pull never`, no `-d`, no `-v`/`--mount`/`--device`/`--cap-add` in fixed words).

**The snippet** (in `op.py`; its hash is a signed constant and in the scope). In order: `signal.alarm(34)`; `/app` on `sys.path`; the two arguments in their grammar (`ARGUMENTS_INVALID`); `C3PO_R2D2_V2_PRODUCERS_ENABLED == true` (F9; `PRODUCERS_NOT_ENABLED`); `implementation_package_sha()` = b5ce527a… (`PACKAGE_NOT_THE_CERTIFIED_ONE`) — both before any provider call; `previous_session(D)` and `session_close` from the packaged XNYS calendar and a refusal unless now is after that close (`PREVIOUS_SESSION_NOT_CLOSED`); the packaged `EodhdFetcher(settings.eodhd_base_url, settings.eodhd_api_token, timeout=15.0, retries=0)`; `/api/exchange-symbol-list/US` → the packaged `build_registry`; `/api/eod-bulk-last-day/US?date=<D−1>`; E28's rule (`probe_eligible_ready.py:200-246`, ported line for line: eligible = registry names of `DAILY_ELIGIBLE_TYPES`; present = eligible codes with a row dated D−1; `_distinct` conflicts and `_bar` usability diagnostics only; READY iff eligible > 0 and 100 × present ≥ 95 × eligible). One JSON line: the nine counts, the two payload hashes, `logical_fetch_calls` (2), D, D−1, the request hash echoed, the Python version. A code is the first token of its own refusal or of the producer's `ProducerError` message (e.g. `PROVIDER_REQUEST_FAILED`), otherwise the exception's class name: never a message, a symbol, a URL or a token. Tested against the release's own modules with a stand-in `httpx` (READY, NOT_READY, a failed call not retried, not-closed), and differentially against E28's `evaluate` on the same payloads (equal counts).

## 4. Budgets (60 s per program, core rule 4)

| Mode | Before the first command | Commands | Expected |
|---|---|---|---|
| RESULT | system calls only | 1 QUICK inspect (8 s) | < 3 s with a 30 MB `daily_contract.json` re-hashed (unmeasured on the host) |
| PROBE | system calls only (two walks, one lstat) | `probe` needs `gate() ≥ 40 + 4 s` when it starts (else `COMMAND_NOT_STARTED_BUDGET`, nothing ran), then 1 QUICK | container 10–30 s **unmeasured** (pandas + exchange_calendars import on a read-only root, two HTTPS calls of which the bulk is several MB); the container ends by `timeout -s KILL 36` (and the alarm at 34 s) before the CLI's 40 s |
| POLICY | system calls only | 3 QUICK | < 2 s |
| TREE | — | none | < 1 s |

The window gives ≥ 80 s at the last send (NOTE 5.1 rule 4), so the gate is the 60 s deadline. No sleep, no poll, no retry.

## 5. Contracts this source imposes on K9W and `k9_runner.py` (PROPOSED: neither exists yet)

- **Launch record** `Dd/launches/<launch>.json`, 0:0 0600, JSON object with exactly: `schema` `K9_LAUNCH_RECORD_V1`, `epoch`, `day`, `operation` (the launch), `slot`, `attempt_key` (the launch's Act B key), `request_sha256`, `step_plan_sha256`, `container_id` (64 hex), `container_name` (`c3po-k9-<yyyymmdd>-<launch>`), `created_at`, `started_at` (UTC isoformat), `timeout_seconds` (1–7200). NOTE 4.3 lists the members without `schema`, `epoch`, `day`, `operation`, `attempt_key`.
- **Container labels**: `c3po.k9.attempt_key` = the launch's attempt key, `c3po.k9.request_sha256` = the launch request's hash (NOTE 3.1).
- **Start marker** `Dd/receipts/<launch>.STARTED.json`, 0600: exactly `schema` `K9_STEP_STARTED_V1`, `epoch`, `day`, `phase`, `operation`, `attempt_key`, `step_plan_sha256`, `started_at`.
- **Step receipt** `Dd/receipts/<launch>.RECEIPT.json` (status `COMPLETE`, `code` null) or `.FAILED.json` (status `REFUSED`/`FAILED`/`DEADLINE`, a constant code): exactly `schema` `K9_STEP_RECEIPT_V1` and the members of NOTE 4.3 plus `aggregates`: `status code epoch day phase operation attempt_key step_plan_sha256 started_at completed_at package_sha256 build_sha outputs aggregates counts`. `outputs` ≤ 64 keys `day/<relative path>` or `source/<relative path>` (components `[A-Za-z0-9][A-Za-z0-9._=-]*`, no `..`, ≤ 8 deep) → 64-hex. `aggregates` ≤ 8 keys of the same grammar naming a directory → `{files, sha256}` where sha256 = SHA-256 of the canonical JSON list of the sorted SHA-256 of every regular file directly in it (components' `daily_61`). `counts`: integer values or one nested level, keys `[a-z][a-z0-9_]*` (anything else is not copied; e.g. `produce_instrument_components` returns `incomplete` as a list of symbols, which the runner must turn into a count).
- **Paths and names in receipts**: no symbol anywhere in `outputs` keys (the runner's duty; K9R copies none of the names into its own receipt, only counts and booleans).

## 6. Plan members (12 own + the core's 7)

| Member | RESULT / PROBE / POLICY | TREE |
|---|---|---|
| `mode` | the mode | `TREE` |
| `epoch` | `R2D2-V2-SHADOW-2026-10-05` | same |
| `day` | D ∈ 2026-10-06…09 | null |
| `k9_phase`, `k9_operation` | the Act B phase and operation (the K9 note's `phase`, `operation`: renamed, section 9) | null |
| `slot` | PRIMARY / SPARE | null |
| `attempt_key` | `sha256(canonical([epoch, day, phase, operation]))`, recomputed | null |
| `run_not_after` | RESULT: the launch's run_not_after (UTC isoformat); else null | null |
| `constants` | the week's constants (section 7.1) | same |
| `parent_rows` | `{days, source_root, secrets, tools, claims}` each `{path, rows, open_root}`, path and open root compiled, rows from TREE | null |
| `evidence_boot_id_sha256` | TREE's boot | null |
| `policy_read` | POLICY: `{policy: {directory, file_name}, release: {directory, file_name}, worker: {container, data_source (= the data volume), data_target}}`; else null | null |

Effects (literal in authority and GO, recomputed): operation, mode, epoch, day, k9_phase, k9_operation, slot, attempt_key, run_not_after, constants, parent_rows (chain effects), evidence boot, `reads` (per mode: what is read, the container name, the probe argv with `<request sha256>`, the expected environment of POLICY, the TREE directories and secret files), `writes 0, claims 0, containers_removed 0, containers_run (1 PROBE, else 0), activation false`. Success criterion: the outcome of the signed mode (`GO_CRITERION` otherwise, at both layers).

## 7. Refusals

### 7.1 `validate_plan` (pure; the dispatcher runs it before any claim, so these never spend a GO)
`MODE_INVALID`, `EPOCH_INVALID`, `CONSTANTS_INVALID` (exact keys `k9_interface_note_sha256 act_b_sha256 package_sha256 code_revision release_sha256 policy_sha256 image_id runner_sha256 probe_snippet_sha256 networks step_table_sha256 risk_source_pins_sha256 risk_limits readiness_rule disk_floor_bytes placement`; hashes, image ID, networks `{PROVIDER, DATABASE, DATABASE_AND_PROVIDER}`, the five risk limits, the floor in their grammar), `CONSTANTS_NOT_THE_COMPILED_ONES` (note, package, revision), `PROBE_CONSTANTS_NOT_THE_COMPILED_ONES` (snippet hash, 95/100), `PLACEMENT_NOT_THE_COMPILED_ONE`, `NETWORKS_NOT_THE_COMPILED_ONES` (PROVIDER = `bridge`), `TREE_PLAN_INVALID`, `DAY_INVALID`, `OPERATION_INVALID`, `OPERATION_NOT_OF_THIS_MODE`, `SLOT_INVALID`, `ATTEMPT_KEY_MISMATCH`, `EVIDENCE_BOOT_UNBOUND`, `PARENT_ROWS_INVALID` and the core's `CHAIN_ROW_*`/`PARENT_SETGID` (days, source_root, claims receive entries), `RUN_NOT_AFTER_INVALID`, `POLICY_READ_INVALID`, `POLICY_READ_NOT_THE_DATA_VOLUME`, `POLICY_READ_OUTSIDE_THE_DATA_VOLUME`, the core's `run_arguments` codes for the probe.

### 7.2 `perform`, before the first observation (the GO is spent; nothing is touched)
`EXECUTOR_IDENTITY`; `WINDOW_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY` (window outside [D−1 20:00Z, D 15:00Z]; a probe ending after D 04:00Z; a policy read starting before D 00:00Z); `RUN_NOT_AFTER_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY`; `RESULT_WINDOW_BEFORE_RUN_NOT_AFTER`. They are here and not in `validate_plan` because the core's conformance suite moves one plan's window across all nine READ days and requires authentication to pass; **binder rev 4 must refuse these windows itself** (it checks the grids, NOTE 10.4).

### 7.3 Findings and failed observations
Listed per item in section 2. Failed observations carry the core's constant codes (`COMMAND_FAILED` with the return code, `COMMAND_TIMEOUT`, `COMMAND_NOT_STARTED[_BUDGET]`, `BINARY_UNAVAILABLE_OR_UNSAFE`, `SYMLINK_COMPONENT`, `COMPONENT_NOT_DIRECTORY`, `PATH_CHANGED`, `FILE_*`, `OS_ERROR`, `DIRECTORY_NOT_HELD`, `LAUNCHED_METADATA_INVALID`, `LAUNCH_RECORD_INVALID`, `STEP_RECEIPT_INVALID`, `OUTPUT_REFERENCE_INVALID`, `OUTPUT_BYTES_LIMIT`, `PROBE_OUTPUT_INVALID`, `PROBE_NOT_STARTED_ENV_FILE_NOT_AS_REQUIRED`, `PROBE_RUN_NOT_COMPLETED`, …).

## 8. Proven, emulated, unproven

- **Executed here**: the source's own `Native` with real system calls on a temporary tree (TREE and RESULT; read-only opens, `O_NOFOLLOW`, by `dir_fd`, secret files never opened, nothing created or changed, no process); the snippet's exact bytes under `python -I -B -` against a stand-in package (3.9.6 and 3.12.14) and against the release's own modules with the real XNYS calendar and settings (3.12.14), including the differential against E28.
- **Emulated only**: Docker (inspect with this format, `run` with this prefix, `--env-file`), the host tree, uid 0.
- **Unproven (K9R-U1…U9)**: U1 busybox `timeout -s KILL 36` in the Alpine image (N-7); U2 `--env-file` + `--env` + `--network bridge` under `--read-only --cap-drop ALL` with the CLI's fixed environment (no HOME); U3 `python -I -B -` with two argv words after `-`; U4 the snippet's imports (pydantic-settings, pandas, exchange_calendars, httpx, certifi) on a read-only root with no writable `/tmp`; U5 the probe's duration within 36 s (two calls, the bulk payload's size); U6 `docker container inspect` of an exited, not removed container with `.State.OOMKilled` and `index .Config.Labels` in this CLI version (typed or raw fallback; a missing label prints `""` typed, `null` raw: both accepted); U7 the inspect of an absent container returns non-zero (stderr is discarded by the core: absent and broken are one case, UNCERTAIN); U8 the provider's real payloads with the packaged `build_registry` (only synthetic payloads here); U9 the Linux-root job (`linux_root/` of this family does not exist yet: pending, set 3); U10 the absence of ACLs (section 0.1: the core cannot read them; the mode-mask argument is what is proven); U11 TREE's device findings rest on `st_dev` (a bind mount of the same filesystem cannot be told apart this way, the core's own limit).

## 9. Deviations from the K9 note, and why

1. `phase`/`operation` of NOTE 4.2 are `k9_phase`/`k9_operation`: the core reserves `phase` in every plan (`PLAN_COMMON_KEYS`).
2. The week's constants are one exact object `constants`, with `placement` signed in it; compared with compiled values where K9R depends on them, by grammar elsewhere. K9W may need a different set (open).
3. `parent_rows` carries five chains, adding `claims` (K9W's claim file, NOTE 4.1, needs its rows; NOTE 4.2 lists four).
4. The probe command is `python -I -B -`, not `python -I -`: `-I` implies `-E`, so the image's `PYTHONDONTWRITEBYTECODE` (NOTE 3.1's reason for no `-B`) is ignored; `-B` says it in the argv (harmless on a read-only root; K11's shape).
5. The snippet also arms `signal.alarm(34)` (the busybox `timeout` is unproven, N-7), and checks the producers' switch and the package hash before any call (F9, NOTE 3.1's runner rule).
6. The probe container has a name but no labels: the core's `run_arguments` has no label grammar (a label would need a new core generation).
7. K9R's command table adds `launched` (RESULT's own format) beside the note's `image`, `container`, `container_environment`, `probe`: the core's `container` row has the fixed `CONTAINER_FORMAT` that POLICY needs. The format also reads the two labels and `StartedAt`.
8. Exit 0 only for a COMPLETE phase / READY / policy and worker as expected / tree as required. NOT_READY and FAILED are exit 2 with the answer at the top level (`readiness`, `phase_result`). The note did not fix the exit mapping.
9. The window-of-D checks are in `perform` (a refusal before observation), not in `validate_plan` (section 7.2).
10. TREE observes more than NOTE 4.2 names: k9_root, claims, emitter, the three secret files (lstat), the runner's hash, the floor; and it fixes the expectations (0:0 0700, data volume a mount point).
11. POLICY requires `worker.data_source` = the compiled data volume and also checks `C3PO_BUILD_SHA` and the image's revision label; restart count is reported, not gated.
12. RESULT also validates the start marker and requires it for COMPLETE; reads the packaged spool by hashing `HOST_PLAN.json` on the host.
13. D is limited to 2026-10-06…09 (Monday 05/10 has no K9 list, NOTE 5.5).
15. (rev 3) The floor is a compiled constant (200 GiB) judged on days/'s descriptor; the source root's capacity reported apart; `filesystem_type` reported as not exposed.
14. (rev 2) Placement per Codex's N-8: the K9 tree under `/var/lib/c3po` with no open root; TREE adds `k9_filesystem` (one device, not the source root's device, floor and inodes on k9_root's filesystem — the floor moved there from `days`) and `components_not_root_controlled`; ACLs are not read (0.1).

## 10. Open questions this source depends on

- **N-8 placement**: decided (section 0); floor decided (200 GiB on days/'s filesystem); ACL proof decided (0.1, mode-mask, POSIX filesystems only). The source root is on days/'s filesystem (decision 6): one floor.
- **Contracts of section 5**: K9W and `k9_runner.py` must write exactly these files; nothing exists yet. Any change there changes K9R's bytes.
- **N-1**: RESULT accepts the packaged receipt under `R2D2-V2-DIAG-R4-<D>` or `R2D2-V2-SHADOW-<D>` and reports which (`namespace_form`).
- **N-3 / S1D**: RESULT assumes the launched container is kept (no `--rm`) until it has been read. With `--rm` every RESULT would be UNCERTAIN (inspect fails).
- **N-4**: only PROVIDER = `bridge` is compiled (it is a fixed word of the probe row).
- **N-6**: zero retries and 15 s per call for the probe; 95/100.
- **N-7**: section 8 U1–U6.
- **N-12**: K9R lists no container; a probe container left by a killed CLI is not seen by K9R (it is removed by `--rm` when its process ends, at most 36 s later).
- **N-15**: the snippet is part of K9R's bytes (scope and payload hash); whether it is "the fifth artefact" needing the owner's own act is open.
- **(5) DOCKER_CONFIG (review of rev 3).** K9R starts the docker CLI with the core's fixed environment (`PATH`, `LANG`, `LC_ALL`; no `HOME`, no `DOCKER_CONFIG`), so the CLI's configuration directory is its default for a process without `HOME` (core U4: never run). K11 has a signed, private, empty `DOCKER_CONFIG` (counted before and after) only for a reduced dry run. Proposal: a plan member `docker_config` with the same rule as K11, signed in every K9R request, if Codex wants the CLI pinned to an empty configuration; open.
- **(7) of the review of rev 3.** Its text did not reach this session (the coordinator's message names it as an open item without its content); recorded here so that it is not lost, to be stated by the reviewer.
- **N-16**: RESULT and POLICY only inspect named containers; whether they are exempt from the container rule is Codex's call (K9R does not depend on it).
- **READ claim (NOTE 10.1)**: K9R writes no claim; single use is the dispatcher's `spawn.claim` plus the SPARE rule. The Act B prose and `derive_daily03.py` must say so.
- **Owner's weekly-signature decision** (`DUDU_DECISION_DAILY_WRITES_WEEKLY_SIGNATURE.json`) speaks of daily *write* payloads with days and windows fixed in the signed bytes; K9R is a read and takes its windows from each request (NOTE 4.2). If the owner wants the same for reads, the grid moves into the bytes.
- A collision of the probe's container name with a leftover of an earlier run of the same operation and day is `PROBE_ENGINE_FAILURE` (engine 125); the recheck has another name.
- The provider base URL is the packaged setting (`C3PO_EODHD_BASE_URL` may be set by the env file; K3-K9 decides) and the packaged fetcher follows redirects (E28's own fetcher did not).

## 11. Tests and mutation (figures in `TESTS.*.txt`, `mutation/MUTATION_RUN*.json`)

- Conformance: the core's 121 tests for five fixtures (RESULT runner, RESULT packaged, PROBE, POLICY, TREE): 605; the outcome test restated for the three modes whose success is not `COMPLETE_OUTCOME`. OTHERS: the four sealed siblings (through links beside this directory).
- Plan (`test_plan.py`): every refusal of `validate_plan`, the window refusals in `perform` (nothing touched), effects against independently written literals, the GO criterion per mode at both layers, the attempt key against `actb03_lib.attempt_key` itself (read from the Act B tools by command), the read operations against `K9_OPERATIONS.json` and the note's hash, by command.
- Read (`test_read.py`): every phase reason, every RESULT operation, the packaged files, hostile states (links, FIFOs, directories, wrong metadata, another boot, other rows, expiry), the inspect line member by member, PROBE readiness boundaries (95, 94, 0 eligible, conflicts), every snippet failure, every hostile line, budget, timeout, env-file states, POLICY and TREE findings, privacy (no token, no symbol, no payload, secret files never read).
- Snippet (`test_snippet.py`): the exact bytes, the hash pinned, imports allow-listed, the stand-in on both interpreters, the release's own modules on 3.12 with a stand-in `httpx` (argv of each request recorded: api_token present, fmt json, timeout 15, one call on failure), the differential with E28, the release files equal to the pinned tar's members.
- Native (`test_native.py`): real system calls under an audit hook, TREE and RESULT.
- Mutation (rev 3): 269 single mutants (six new for the floor, F01–F06); rev 2: 263, ten new for N-8 (`G01`–`G10`) and the floor rows repointed; rev 1 had 253 (`mutation/mutants.py`): one per refusal, per effects member, per decision and finding, per line check, per contract check, per fixed word of the probe, per deciding word of the snippet; run on both interpreters, records in `mutation/`. The first run had 14 survivors and one broken mutant; each is answered by a test of `test_read.py` ("answers to the first mutation run") or, for two equivalent checks, by removing the redundant code.
