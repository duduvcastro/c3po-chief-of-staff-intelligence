# K4 mode E0 — the epoch's roots under /var/lib/c3po and the K9 runner (HOSTOPS02, once per epoch) — revision 4

Offline work only. Nothing here was run on the host, pushed, bound or reviewed by anyone but its author. Hashes and counts are in `VALIDATION.json` and `SHA256SUMS`, written by `seal.py`; the figures below were measured by command on 2026-10-04 (section 11 reproduces them).
Built on the frozen core, generation `4c24c5cf…d0d6` (`../core`, a symbolic link to `W/hostops02-sealed/core`; read, never edited). Pattern: `W/hostops02-sealed/install_release` (K10).

**Revision 4 implements Codex decision 6 (#429 comment 5985748037):** the bind sources sit under a chain controlled by root alone; the uid-1000 data volume is no longer acceptable for the source root. The source root is now `/var/lib/c3po/r2d2-v2-source-20261005`, a sibling of the K9 root, on the same chain (`/`, `/var`, `/var/lib`, then `/var/lib/c3po`), with no open root anywhere, gid 0 and no setgid on every row, root:root 0700, on the filesystem of the one 200 GiB floor. Every use of `/mnt/day-d-data` is gone: the second chain, the mount-point check, the maintenance-pin check (it lived on the data volume) and the 1 MiB floor of the data volume. Earlier revisions are kept unchanged beside this directory: `../k4_e0.rev1-0da395b3/` (both roots on the data volume), `../k4_e0.rev2-394f1b27/` (Codex N-8: K9 tree under `/var/lib/c3po`), `../k4_e0.rev3-b53772e6/` (review of revision 2: 200 GiB floor, device of an existing `/var/lib/c3po`, scratch outside, carried mutants listed). What revisions 2 and 3 established is kept here unless this section says otherwise.

Abbreviations. `PLAN` = `W/fable-epoch03-masterplan-20261002/MASTER_PLAN.md`. `K9N` = `W/fable-k9-interface-20261003-rev2/K9_INTERFACE_NOTE.md` (`ab5159be…596c`). `A2` = `W/fable-a2-draft-20261003-rev3/A2_AUTORIDADE_CINCO_SESSOES.md`. `N8` = `W/codex-n8-placement-20261004.txt` (`d30f7f90…2c53`). `D6` = Codex decision 6, #429 comment 5985748037 (as relayed by the coordinator; its text was not read here). `K10` = `W/hostops02-sealed/install_release`.

---

## 0. What it is, in one paragraph

One run, before the first daily phases of the epoch, under `/var/lib` — whose signed chain `/` → `/var` → `/var/lib` must be controlled by root alone (validated with no open root: every component uid 0, gid 0, not writable by group or other, not setgid; walked without following a link) — creates **`/var/lib/c3po` only if it is absent** (if present it must be a root:root directory on the filesystem of `/var/lib`, not a link, not writable by group or other, not setgid; it is opened `O_NOFOLLOW`, held and used unchanged, its identity recorded), and in it the epoch's **source root** `r2d2-v2-source-20261005` and the **K9 root** `r2d2-v2-k9-20261005` with `tools`, `days`, `claims`, `secrets`; in `tools` the **content-addressed runner file** `k9_runner-<sha256>.py` (0600) holding exactly the bytes the request carries. Every new directory is root:root 0700. Nothing is created unless that filesystem has 214,748,364,800 bytes (200 GiB) available. Exclusive creation, fsync, readback by descriptor inside the run; everything is looked at before the first creation; no process, no secret, no container. Both roots must be absent: a second run is refused.

## 1. What the sources of truth ask, and where each answer lives

| Ask | Source | Here |
|---|---|---|
| "E0 — The epoch's source root, private, uid 0, once — before the first phases" | PLAN:220 | the source root 0700 root:root; `SOURCE_ROOT_PRESENT` |
| "K4 … Exclusive creation, fsync, readback by descriptor" | PLAN:330 | the core's `files.create_directory` / `create_file`, `readback_file` / `readback_directory` |
| "K4's E0 mode extended to the K9 tree and the runner" | K9N 6.1 item 7 | the K9 root, its four directories, the runner |
| Mounts `T`, `Dd`, `Src`, `Em` | K9N 3.1 | `tools` (bound ro at `/c3po-k9-tools`), `days`, `secrets`, the source root (`Src`) |
| K9 tree under `/var/lib/c3po`, root-only chain, no open root, no links; absent parent created only by an explicitly signed effect | N8 | `parent` rows validated with `open_root=None` and `root_controlled`; the conditional `c3po_directory` rule (both branches signed) |
| Bind sources under a root-only chain; source root beside the K9 root; no open root anywhere; gid 0 and no setgid on every row | D6 | the same chain and the same held `/var/lib/c3po` for both roots; `CHAIN_NOT_ROOT_CONTROLLED` (gid ≠ 0 or setgid on any row); no data-volume path in the part (tested) |
| 200 GiB on the filesystem that holds `days/`; one floor covers both roots | Codex (rev 2 review), D6 | `FREE_SPACE_BELOW_FLOOR`, `fstatvfs` on the held `/var/lib/c3po` or `/var/lib` |
| The probe snippet | K9N 3.3 (stdin of K9R) | not delivered by E0 |
| Band Mon 05/10 – Thu 08/10, 17:38–20:30 BRT | A2:278 | binder and signer (section 8, deviation 1) |

## 2. Placement (decided by Codex: N8 and D6)

```
VAR_LIB='/var/lib'   C3PO_NAME='c3po'
SOURCE_ROOT_NAME='r2d2-v2-source-20261005'   -> /var/lib/c3po/r2d2-v2-source-20261005
K9_ROOT_NAME='r2d2-v2-k9-20261005'           -> /var/lib/c3po/r2d2-v2-k9-20261005
```

Five lines of `op.py`'s placement block; every other path derives from them (tested: each literal occurs once, and `day-d-data`, `DATA_VOLUME` and `MAINTENANCE_PIN` occur nowhere in the part). K9R, K3-K9, K9W, K8/K12 and the reader's `C3PO_R2D2_V2_SHADOW_SOURCE_DIR` must use the same paths (N8).

Consequences the reviewers should see:
- **Who reads the source root.** Revision 1 placed it on the data volume because the compose worker binds that volume at `/app/day-d-data`. Under `/var/lib/c3po` it is reachable only through a bind that names it (K9 containers bind it as `Src`, K9N 3.1); the reader's own launch (K13) must bind it too. That is K13's and K9's design, not E0's (Q-8).
- **No pin witness.** The maintenance pin was the witness that what root creates in the data volume root is root:root. Under `/var/lib` nothing needs a witness: every created directory is proved 0:0 by the core after its `mkdir` (`CREATED_METADATA_MISMATCH` otherwise), and the chain itself must be gid 0.
- **ACLs are not read** (as in revisions 2–3): the core has no extended-attribute call; the authorized host read must prove "nenhuma ACL não privilegiada" (Q-1).
- **A run that died after creating only `/var/lib/c3po`** leaves neither root; a new request with the same bytes then finds `/var/lib/c3po` present (root:root 0700) and completes (tested on the emulation and with a real process death). Any later state holds a root and is refused.

## 3. Effects, in order

Every mutating call goes through the core's `mutate()`. Emulated run with `/var/lib/c3po` absent: 333 host calls, 181 looks at the clock, 11 mutating calls, 17 fsyncs; present: 322, 178, 10, 15.

| # | Call | In | Then |
|---|---|---|---|
| — | `umask(0o077)` | the process | after the executor identity is known |
| 1 | **only if absent:** `mkdir("c3po", 0o700)` | held descriptor of the pinned `/var/lib` (after `verify`) | open (no link followed), fstat, lstat, list (empty), fsync it, fsync `/var/lib`. If present: no call; it was opened `O_NOFOLLOW` in the precheck and is held |
| 2 | `mkdir("r2d2-v2-source-20261005", 0o700)` | held `/var/lib/c3po` (verified: its identity, then `/var/lib` walked again from `/`) | the same; fsync `/var/lib/c3po` |
| 3 | `mkdir("r2d2-v2-k9-20261005", 0o700)` | held `/var/lib/c3po` | the same |
| 4–7 | `mkdir("tools"|"days"|"claims"|"secrets", 0o700)` | held K9 root (verified through the whole chain) | the same |
| 8–11 | exclusive temporary, write, link to `k9_runner-<sha256>.py`, unlink of the temporary | `tools` | K10's file sequence |
| — | readback | | the runner's bytes; every created directory resolved again from `/` to the descriptor held (root:root 0700, exact entry count: c3po 2 if created, source 0, K9 4, tools 1, others 0); an existing `/var/lib/c3po` verified unchanged; the chain walked again |

Nothing that exists is overwritten, renamed, chmodded, chowned, truncated or removed, except the temporary of this run. An existing `/var/lib/c3po` gains exactly two entries and is otherwise untouched (tested with a foreign entry in it).

## 4. Refusals

### 4.1 From the bytes (`validate_plan`; also the dispatcher's local check)

| Code | When |
|---|---|
| `CHAIN_ROW_INVALID` | `parent` is not one six-integer row each for `/`, `/var`, `/var/lib` (rows of the data volume, of `/var/lib/c3po` or of `/mnt` included) |
| `CHAIN_ROW_UNSAFE` | any row not uid 0, or writable by group or other (a sticky world-writable `/var/lib` included) |
| `PARENT_SETGID` | `/var/lib` setgid |
| `CHAIN_NOT_ROOT_CONTROLLED` | any row with a group other than 0, or setgid on `/` or `/var` |
| `EVIDENCE_BOOT_UNBOUND` | no boot identifier hash |
| `RUNNER_PLAN_INVALID`, `RUNNER_PATH_NOT_CONTENT_ADDRESSED`, `RUNNER_BYTES_NOT_THE_SIGNED_HASH` | the runner member (≤ 40,960 bytes; path `/var/lib/c3po/r2d2-v2-k9-20261005/tools/k9_runner-<sha256>.py`) |

### 4.2 On the host, before the first effect (REFUSED, PRECHECK; nothing created)

`EXECUTOR_IDENTITY` → `EVIDENCE_FROM_EARLIER_BOOT` / `BOOT_ID_INVALID` → the walk of the chain (`PARENT_*`, `NOATIME_UNAVAILABLE`) → `/var/lib/c3po` by `lstat` through the held `/var/lib`: absent (then neither root can exist), or present and then `C3PO_DIRECTORY_NOT_A_DIRECTORY`, `C3PO_DIRECTORY_NOT_ROOT_OWNED`, `C3PO_DIRECTORY_WRITABLE_BY_GROUP_OR_OTHER`, `C3PO_DIRECTORY_SETGID`, `C3PO_DIRECTORY_ON_ANOTHER_FILESYSTEM`, opened `O_NOFOLLOW` and compared with the `lstat` (`C3PO_DIRECTORY_CHANGED_DURING_PRECHECK`), then `SOURCE_ROOT_PRESENT` and `K9_ROOT_PRESENT` looked up in the held directory → `FREE_SPACE_BELOW_FLOOR` (200 GiB, `fstatvfs` on the held `/var/lib/c3po` or `/var/lib`), `STATVFS_INVALID` → `BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT`. The gate is asked before each lookup and before the open.

### 4.3 After the precheck

REFUSED only while nothing succeeded and nothing is uncertain (a failure at the first `mkdir`); otherwise PARTIAL with the ledger of every directory and of the runner; the first directory that is not `CREATED_DURABLE` stops the run. The receipt always carries `c3po_directory` (`state` ABSENT/PRESENT, null only when the run stopped before looking; `found` with device and inode; `created`) and, in `precheck`, `free_bytes` and `free_bytes_measured_on`. Exit 0 and `EPOCH_ROOTS_CREATED_RUNNER_DELIVERED_READ_BACK` only when every creation succeeded and every readback passed.

## 5. Crash points

States in order: A nothing → **B1 `/var/lib/c3po`** (only when it was absent) → B2 source root → B3 K9 root → B4 tools → B5 days → B6 claims → B7 secrets → C temporary → D linked → E delivered. Proved on the emulation for a death at every host call in both cases (`/var/lib/c3po` absent: 333 points; present: 322), for an expiry or a reversed clock at every look at the clock, and with a real process death at nine points on a real filesystem. B1 can be completed by a new request (section 2); every later state holds a root and is refused (`SOURCE_ROOT_PRESENT`, or `K9_ROOT_PRESENT` when only the source root was removed); a PARTIAL or UNCERTAIN E0 past B1 is redone under new names.

## 6. Time and size

Payload 60 s, watchdog 80 s, transport 270 s; window ≤ 900 s on one UTC day of 10-05 … 10-10; 15 s reserved before the first creation; no wait, lock or process. Runner ≤ 40,960 bytes: the bound request with a 40,960-byte runner measured 60,626 bytes (limit 65,536; tested with ≥ 2,048 to spare). Complete receipts: 7,983 bytes (`/var/lib/c3po` absent), 7,829 (present).

## 7. What is signed

`SCOPE`: operation, dates, statement, core generation, flags, epoch, the placement (`/var/lib`, `/var/lib/c3po`, both roots, `open_root` null), the `c3po_directory` rule with both branches, the six always-created directories, the runner's directory/name/mode/limit/container directory, the floor and where it is measured, `FILES_SCOPE`, evidence, reads, `processes_started: 0`, `never`, limits. Authority and GO carry `effects_of(plan)`: the chain (`chain_effects`), `open_root` null, the `c3po_directory` rule, every directory, the runner (path, hash, size, 0600, 0:0, one link, container path), the floor, the evidence boot, five false flags. The signed effects do not depend on the state of `/var/lib/c3po` (tested); the receipt says which branch ran.

## 8. Deviations from the pattern (K10)

1. `WRITE_SESSIONS` with no day bound of its own (the conformance suite requires every day of the class); A2's band is the binder's and signer's.
2. No New York day; no maintenance pin (revision 4: it was on the data volume).
3. Two mutation lists (own, carried), not five; no `binding/` tools.
4. `tests/native_support.py` byte-identical to K10's (its data-volume device shift is now unused by the runs); `tests/native_child.py` adapted; `tests/test_native.py` adds `/var/lib` (0755) to K10's tree.
5. The family lies beside a `core` symlink in `W/fable-k4e0-20261004/`; scratch in `../k4_e0.work` (`seal.py` refuses `WORK_INSIDE`).
6. A conditional effect for `/var/lib/c3po`: `create_directory` when absent; when present the operation part opens it through `host.open` (open flags only, CORE rule 4) and holds it as a core `Pinned` child.
7. `root_controlled` checks only gid 0 and no setgid; uid 0 and no group/other write are refused first by `validate_chain` without an open root.
8. `tests/native_space.py` raises `f_bavail` to the 200 GiB floor only on a machine that has less (a CI runner), and records it; one native test runs without it. Not substituted on this workstation.

## 9. Proven, emulated, unproven

- **Real on the workstation** (`tests/test_native.py`, real `fstatvfs`, no substitution): seven real `mkdir` and the file sequence by `dir_fd`, exact flags and modes, every fsync a real `os.fsync` (17), no path under `/mnt` ever touched; an existing 0755 `/var/lib/c3po` used unchanged; real refusals for a `/var/lib/c3po` that is group-writable, setgid, a link or a file, a group-writable or linked `/var/lib`, present roots; three real races; a real process death at nine points; `Native.identity()` the real effective uid and gid.
- **Emulated only:** device numbers, uid 0, every errno and every death point.
- **Unproven (set 3, not the author's): the Linux-root CI job** (`core/linux_root/run.sh` with this directory). As root on Linux, `test_native_run_records_where_it_ran_for_the_linux_proof` asserts seven `0:0:0700` directories and a `0:0:0600:1` file.
- **Unproven: the host.** `/var/lib/c3po` was never observed; the rows of `/`, `/var`, `/var/lib`, their ACLs and the free space of their filesystem must come from an authorized read of the same boot.

## 10. Open questions

| # | Question | Proposal | Who |
|---|---|---|---|
| Q-1 | Evidence: which authorized read signs the rows of `/`, `/var`, `/var/lib`, the state of `/var/lib/c3po`, no unprivileged ACL, and the space? The source requires only a `GO_READONLY_HOSTOPS_PRECHECK_01` receipt | the binder cites a read that shows them; if W1 does not, `EVIDENCE_OPERATIONS` must name that read (new payload) | Codex, binder |
| Q-2 | Space during the week | E0 enforces 200 GiB once; consumption (sources about 40 GiB a night per E28) is the TREE read's and K9W's | K9W author |
| Q-3 | No recovery from a PARTIAL E0 past B1 (no removal in the family) | accept, or a spare E0' with other names | Codex |
| Q-4 | A corrected runner after E0 needs a K4 RUNNER mode | not built | Codex |
| Q-5 | The binder must compare `runner.sha256` with the K9 `runner_sha256` constant | binder rev 4 | Fable |
| Q-6 | Runner size ≤ 40,960 bytes | measure when the runner exists | Fable |
| Q-7 | Pin the state of `/var/lib/c3po` instead of the conditional rule? | built as specified | Codex |
| Q-8 | The reader (K13) and every consumer of `C3PO_R2D2_V2_SHADOW_SOURCE_DIR` must bind `/var/lib/c3po/r2d2-v2-source-20261005`; the compose worker no longer sees it through the data-volume bind | K13 / K9 design | K13 author, Codex |

## 11. Reproduce

```
cd W/fable-k4e0-20261004/k4_e0
shasum -a 256 -c SHA256SUMS && /usr/bin/python3 -B seal.py check
/usr/bin/python3 -B ../core/assemble.py --check .
/usr/bin/python3 -B -m pytest -p no:cacheprovider -q tests          # and W/night23-test-venv/bin/python
/usr/bin/python3 -B mutation/mutate.py check
HOSTOPS_MUTATION_PYTHON=<python> HOSTOPS_MUTATION_RECORD=<record> /usr/bin/python3 -B mutation/mutate.py run
HOSTOPS_MUTATION_LIST=carried /usr/bin/python3 -B mutation/mutate.py run
```

## 12. Carried core mutants not killed by this family's tests

The carried list applies the core's own 318 rows for the parts this source carries (core, parents, files) to this source and runs this family's tests (information only). Every one of them is killed by the core's own suite (`core/mutation/MUTATION_RUN*.json`, zero survivors on both interpreters). Revision 4: 278 killed, 40 not killed. They are revision 3's 34 (same reasons, listed in `../k4_e0.rev3-b53772e6/DESIGN.md` section 12 and summarised below) plus six that revision 4 made unreachable or untested by removing the data volume:

| Rows | Why not killed here | Killed by |
|---|---|---|
| `P01_any_owner_accepted_outside_an_open_root`, `P02_world_writable_directory_accepted_inside_an_open_root`, `P03_sticky_bit_does_not_excuse`, `P04_group_writable_counted_as_world_writable` (new in revision 4) | they change `row_accepted()` only when an `open_root` is given; revision 4 passes `open_root=None` everywhere (Codex D6), so the code they change never runs for E0 | core suite |
| `E19_mount_point_always_the_root`, `E19b_mount_point_one_component_too_high` (new in revision 4) | on E0's path: `chain_effects()` reports `mount_point_by_device_change` of the signed chain in the effects. The emulated host has `/`, `/var` and `/var/lib` on one filesystem, where the answer is `/` either way; only a host where `/var` or `/var/lib` is its own mount tells them apart. Not answered by a new test in this revision, to avoid a further full mutation rerun on the loaded workstation; one emulated test with `/var/lib` on its own device would kill both | core suite |
| `E12`, `E13` (`descend`), `P13`, `P14`, `P15` (`stat_signature`) | never called by E0 | core suite |
| `E11` (probe through a symbolic-link component) | `readback_directory` fails either way (`READBACK_MISMATCH`) | core suite |
| `T08`, `T09`, `T10` | equivalent for E0 (no normal return with an uncertain call and nothing succeeded; a pending call is uncertain; a row-pinned parent's fresh walk compares the same signed row). `T09` and `T10` are also the core's two recorded redundant mutants | core suite |
| `K03`, `K09`, `K12`, `K27` | `ACTIVATION_ALLOWED` is False in E0 | core suite |
| `K14` | one evidence operation: `all` and `any` coincide | core suite |
| `K18`, `K19`, `K20`, `K22`, `K23` | other date classes; pinned by the deselected `static` conformance test | core suite |
| `K25` | `strict()` called only with its default limit | core suite |
| `P06`, `P07`, `P08` | constants: `receives_entry=True`, `open_root=None` | core suite |
| `F01`, `F03`, `F26` (mode checks), `F02`, `F06`, `F08`, `F09` (paths), `F04`, `F05` (size), `F07` (`go16`), `F10` (one file) | E0 passes only constant modes, constant or content-addressed paths validated by `runner_of`, a runner of 1 to 40,960 bytes, `go16` from the GO hash, and one file | core suite |
