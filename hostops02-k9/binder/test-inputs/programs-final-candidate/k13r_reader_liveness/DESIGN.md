# K13r — the reader liveness readback (HOSTOPS02): LIVE and STOPPED — revision 2

**Revision 2 (2026-10-04, after an independent read-only review of revision 1, seal `07767877…`).** Section 6 lists each finding and what changed. Revision 1 is kept unchanged at `../work/k13/rev1/k13r_reader_liveness.rev1-07767877/`.

Offline work only. Nothing here ran on the host, was pushed, bound or reviewed by anyone but its author. Hashes and counts are in `VALIDATION.json` and `SHA256SUMS`, written by `seal.py`.
Built on the frozen core, generation `4c24c5cf…d0d6` (`../core`; read, never edited). Patterns: K11 (`epoch_readback`, the observe() loop), the core's `demo_read`.

`RDR` = the reader README of the installation candidate (`c3po/deployment/reader/README.md`), operations 6 (liveness readbacks) and 8 (deactivation readback).

## 0. In one paragraph

`GO_READONLY_HOSTOPS02_K13R_READER_LIVENESS_01`, read-only (`WRITES_ALLOWED=False`, `DATE_CLASS='READ'`, gate ≤ 900 s, `SUCCESS_IN_TEMPLATE=False`), parts core, runner, docker (no files, no parents), tools docker and systemctl, READ rows only. Mode **LIVE** (PLAN M7, A2 V-1/V-2/V-s, after a K13 ACTIVATE or RESTART): the boot, the reader service `active`, the timer `enabled` and `active`, exactly one container named `c3po-reader`, running, of the signed image, its start instant and restart count, its mounts as the engine lists them (exactly the four read-only binds of the installed unit), its main command (`python -I -B /c3po-reader/reader_launcher.py`, with an init process, a read-only root filesystem, user `0:0`), and no reader-like main command in any other running container. Mode **STOPPED** (after K13 DEACTIVATE, X1): timer `disabled` and `inactive`, service `inactive` or `failed`, no `c3po-reader` container, no reader elsewhere. Each item is observed on its own (K11's `observe()`): a failure is that item's `UNAVAILABLE` with a constant code, never an absence; a mismatch is a finding; an expiry stops the run.

## 1. Items

| Item | Command | Findings |
|---|---|---|
| `boot` | read of `/proc/sys/kernel/random/boot_id` | `BOOT_NOT_THE_EVIDENCE` (its hash differs from the signed one) |
| `service` | `systemctl show c3po-reader.service -p Id -p LoadState -p ActiveState -p SubState -p UnitFileState -p FragmentPath -p DropInPaths -p Result -p NRestarts` | `READER_UNIT_NOT_LOADED`, `READER_UNIT_NOT_THE_INSTALLED_FILE`, LIVE `SERVICE_NOT_ACTIVE` (anything but `active`), STOPPED `SERVICE_NOT_STOPPED` (anything but `inactive` or `failed`; `deactivating` is not stopped); facts: Result, NRestarts |
| `timer` | `systemctl show` of the timer with its own list (Id, LoadState, ActiveState, SubState, UnitFileState, FragmentPath, DropInPaths, Result — no NRestarts, which a timer does not have), `systemctl is-enabled c3po-reader.timer` | the two unit findings; LIVE `TIMER_NOT_ENABLED_AND_ACTIVE`; STOPPED `TIMER_NOT_DISABLED_AND_INACTIVE` |
| `containers` | `docker ps -a --no-trunc --format PS_FORMAT` | LIVE `READER_CONTAINER_NOT_RUNNING` (absent or not running); STOPPED `READER_CONTAINER_PRESENT` |
| `container` (LIVE) | `docker container inspect --format CONTAINER_FORMAT c3po-reader` | `READER_CONTAINER_NOT_RUNNING`, `READER_IMAGE_NOT_THE_PIN`; facts: ID, state, start instant, restart count, health. `READER_CONTAINER_CHANGED` (UNAVAILABLE) when the inspected ID is not the listed one |
| `mounts` (LIVE) | `docker container inspect --format '{{json .Mounts}}' <ID>` | `READER_MOUNTS_NOT_THE_FIVE_READ_ONLY_BINDS` (type bind, RW false, the README's four source/destination pairs plus the epoch source root `/var/lib/c3po/r2d2-v2-source-20261005` at the signed `source_target` — Codex decision 6 — nothing else), `READER_MOUNT_WRITABLE`. Only type, source, destination and RW are kept; `not_root_controlled_sources` reports the data volume bind (`/mnt/day-d-data`), which does not meet decision 6 |
| `command` (LIVE) | `docker container inspect --format '{"id","path","args","init":.HostConfig.Init,"read_only":.HostConfig.ReadonlyRootfs,"user":.Config.User}' <ID>` | `READER_COMMAND_NOT_THE_LAUNCHER`, `READER_WITHOUT_INIT`, `READER_ROOT_NOT_READ_ONLY`, `READER_NOT_UID_0`. Only booleans leave |
| `other_readers` | for each other container in running/paused/restarting, `docker container inspect --format '{"id","path","args"}' <ID>` | `READER_PROCESS_ELSEWHERE` (a word naming `app.r2d2_v2_shadow_worker` or `reader_launcher.py`, none naming `--prepare-capacity-day`); the names of such containers are listed, never their command lines |

Outcomes: LIVE `READER_LIVE_ALL_EXPECTATIONS_MET`, STOPPED `READER_STOPPED_ALL_EXPECTATIONS_MET` (exit 0); `READER_NOT_AS_EXPECTED` (exit 2) when every item was observed and one has a finding; `READER_OBSERVATION_INCOMPLETE` (exit 2) when an item is UNAVAILABLE or the run expired; `REFUSED_NOTHING_OBSERVED` (exit 1) only before the first observation (executor not 0:0, expiry before anything).

No template names the environment; `docker inspect` is never printed unformatted (it holds the database URL).

## 2. What RDR operation 6 asks that this core cannot do (NOT observable here)

1. **`docker top`** — a SIGNED GAP, to be accepted explicitly by the owner or Codex before any GO (Q-1): **M7 / V-1 / V-2 cannot see the worker child** (docker-init, the launcher and exactly one `app.r2d2_v2_shadow_worker` child; none between handover and SESSION): `top` is not a reading verb of the frozen assembler and a reading source has no EFFECT rows. Replaced by the main command of the reader container (`.Path`/`.Args`, the launcher) and `.HostConfig.Init` (docker-init present by configuration). **The worker child is not observed**: a launcher whose worker died between restarts is seen as live.
2. **`docker logs`** — the same SIGNED GAP: **M7 cannot see the `STARTING` notice** (the `STARTING` notice with `build_sha`, `release_sha`, `capacity_config_sha`, `launcher_sha256`; no FAILED/REFUSED after it; the first status line): `logs` is not a reading verb of the core either, and `journalctl` is not one of the two tools. Not read. Decision: no log parsing in this revision; the identity of the bytes rests on K13's hashes of pins.env and the launcher before the start, and on the image ID and mounts read here.
3. The epoch row version (a database read; RDR says it is supporting evidence only).
4. "After the end: STOPPED with END_OF_DAY, exit 0": the exit status is not read; STOPPED mode reads unit and container state only.

These are DESIGN gaps to be accepted or closed by Codex (Q-1); closing them needs a new core generation (a reading verb for `top`/`logs`) or another tool.

## 3. Plan

`mode` (LIVE | STOPPED: `MODE_INVALID`), `source_target` (the container target of the source root, `/c3po-<name>`, not one of the four others: `SOURCE_TARGET_INVALID`; copied from `pins.env`), `image_id` (`sha256:<64 hex>`: `IMAGE_ID_INVALID`), `evidence_boot_id_sha256` (`EVIDENCE_BOOT_UNBOUND`). Evidence must cite a `GO_WRITE_HOSTOPS02_K13_READER_SWITCH_01` receipt. The binds, the launcher command, the unit names are constants of the source (the same values as K13's text checks).

## 4. Tests (exact counts in VALIDATION.json)

`test_conformance.py` (121, mode LIVE), `test_k13r.py` (both modes, every finding, every UNAVAILABLE, plan refusals, expiry, a replaced reader, failure/OSError/death at every host call in both modes — never a change, never COMPLETE). No native test: the source makes no filesystem call beyond the boot identifier (the core's `boot_id_sha256`, covered by the core's own native tests). Emulated only: systemctl, docker inspect templates (the core's emulation does not model `.Args`, `.Mounts` members, `.HostConfig.Init`; tests/k13r.py sets them on the emulated objects).

## 5. Open questions for Codex

- Q-1 Accept the gaps of section 2 (no worker-child count, no STARTING notice) for M7/V-1/V-2, or require a later core with a reading `top`/`logs` verb?
- Q-2 Should LIVE accept `activating` for the service in the first readback after M6 (the container start may take seconds)? Currently a finding (`SERVICE_NOT_ACTIVE`), which makes the first read of a pair PARTIAL if it comes too early; the second read two minutes later decides.
- Q-3 `BOOT_NOT_THE_EVIDENCE` is a finding (exit 2), not a refusal: right for a liveness read?

## 6. Review of revision 1 and what revision 2 changed

| # | Finding | Revision 2 |
|---|---|---|
| 1 BLOCKER | the timer was read with the service's property list, including `NRestarts`; a `.timer` has no such property and `systemctl show -p NRestarts` prints nothing for it, so the `timer` item was always UNAVAILABLE and neither mode could ever complete on a real host. The emulated timer carried a NRestarts it does not have, which hid it | `TIMER_PROPERTIES` (no NRestarts) for the timer row and its parse; `unit_values()` takes the list; the emulated timer has no NRestarts (`tests/k13r.py`); a test proves the timer's argv and that both modes complete without it, that an extra property is ignored and a missing one (`Result`) is UNAVAILABLE |
| 5 MINOR | STOPPED accepted `deactivating` | STOPPED requires `inactive` or `failed` (`STOPPED_STATES`); finding renamed `SERVICE_NOT_STOPPED`; tested for active, activating, reloading, deactivating |
| — | the gaps must be stated as signed | section 2: no worker child, no STARTING notice, both to be accepted explicitly (Q-1) |

K13 was checked for the same defect: its property list holds only properties a timer has.

### 6.1 Codex decision 6 (relayed by the coordinator during revision 2)

`W/codex-six-design-decisions-20261004.txt` item 6 (sha256 `4b169599…9c55`, by command): bind sources root-controlled; the source root `/var/lib/c3po/r2d2-v2-source-20261005` becomes a fifth read-only bind. LIVE now expects exactly five binds (the fifth at the signed `source_target`), and reports the data volume source `/mnt/day-d-data` under `not_root_controlled_sources` (and in the effects, `binds_not_root_controlled`): it does not meet the decision; it is neither a finding (it would make every LIVE read fail until the release moves) nor silently accepted. K13r reads no chain: the root-only chains of the sources are K13's precheck. Q-4 (new): Codex/owner to decide the data volume bind (K13 Q-8, K4 Q-K4-8).
