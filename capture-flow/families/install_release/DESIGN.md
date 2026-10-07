# K10 — install_release (HOSTOPS02, tier 0, Monday 2026-10-05, SINGLE SHOT)

Offline work only. Nothing here was run on the host, pushed or bound. Hashes and counts are in `VALIDATION.json` and `SHA256SUMS`, written by `seal.py` from the files and the runs.
Built on the frozen core, generation `4c24c5cf…d0d6` (`../core`, seal `c13ce685…2f9f`). The core was not edited.

**Revision 2, after the review of 2026-10-02 (two lenses: purity/authentication, host).** No payload byte changed: `op.py`, `spec.py` and `build/` are the reviewed bytes. What changed is around them: three bind-time tools that refuse mechanically what the first revision left to a reading by hand (`binding/release_fields.py`, `binding/linux_proof.py`, `binding/predispatch.py`), the tests the reviewers' mutants showed to be missing, two more mutation lists, the seal, and the two documents. Section 12 lists every finding and what answers it.

Abbreviations. `REL:<path>:<line>` = `git show dd4ec4bb:<path>` of the release. `P23` = `…/va/work/r2d2-certified-successor-20260923-activation-rev12b/operations/release-install.py` (sha256 7468f26a…, executed 23/09). `P28` = `…/va/work/r2d2-plan-b-baseline-20260927/bound-package-rev3/operations/release-install.py` (14580b9f…, executed 28/09 06:15:16–06:15:19Z, return code 0: `…/rescue-s2-rev-s/night-policy-prerequisites-rev1/install-execution-once/{intent,exit}.json`). `A28` = `…/rescue-s2-rev-s/night-activation-review-rev1/worker-live-control.bound.py` (2abc6388…, the activation of 28/09). `CORE` = `../core/CORE.md`.

---

## 0. What it is, in one paragraph

One private directory and one file in it. The directory is `/mnt/day-d-data/r2d2-v2-release-20261005` (root:root 0700), created in the pinned root of the data volume; the file is `release.CERTIFIED.json` (root:root 0600), holding exactly the release bytes the request carries, whose SHA-256 and size the request signs. Everything is looked at before the first creation. The source starts no process (it does not carry the runner or the docker part: `PARTS=['core','parents','files']`), takes no lock, waits for nothing, activates nothing and recreates nothing. It does not ask the application whether the release verifies: that is the epoch readback (K11, PRE on Sunday with the real bytes and POST on Monday), under its own GO.

Why no container run here (decision D-1, section 10): on the single shot every check that can fail for a reason unrelated to the write is a way to lose the epoch. `Release.verify` depends on the instant only through `approved_at <= now` and `readiness_publication_at <= now` (REL:c3po/backend/app/r2d2_v2_shadow.py:106,157), so Sunday's K11 PRE run on the same bytes and the same image answers the question with 16 hours of margin, and Monday's K11 POST answers it on the installed file. An attached container in K10 would add the docker binary, the engine, U2 and U4 of the core to the one dispatch that cannot be repeated, and would prove nothing that those two reads do not.

## 1. Where the application looks, and why this path

| Fact | Evidence |
|---|---|
| The worker reads the release from the file named by `C3PO_R2D2_V2_SHADOW_RELEASE_FILE` and pins it by `C3PO_R2D2_V2_SHADOW_RELEASE_SHA` | REL:c3po/backend/app/config.py:20 (prefix `C3PO_`), :207-208; REL:c3po/backend/app/r2d2_v2_shadow_worker.py:77-80 |
| The reader requires: no link followed, a regular file, no group or other permission bit, at most 65,536 bytes, unchanged while read; the hash is checked again every cycle | REL:…/r2d2_v2_shadow_worker.py:29-42 (`_release_bytes`), :45-52 (`recheck_release`) |
| `Release.verify`: file hash = pin; one JSON object without duplicate keys or non-finite numbers; schema `R2D2_V2_RELEASE_V3`; epoch namespace; `code_revision == build_sha`; three consents; readiness clocks | REL:…/r2d2_v2_shadow.py:72-162; schema name REL:…/r2d2_v2_earnings_package.py:21 |
| Epoch and first session of this release | REL:…/r2d2_v2_epoch_assembler.py:9-11 (`R2D2-V2-SHADOW-2026-10-05`, `2026-10-05`) |
| The data volume is bound at `/app/day-d-data` in `r2d2-worker`; the service has no `user:` and the image no `USER`, so the worker is root in its container | REL:c3po/compose.yml:138-176 (:165 the bind); REL:c3po/backend/Dockerfile (no `USER` line) |
| On this host that bind's source is `/mnt/day-d-data`; the activation of 28/09 required exactly that and mapped host path to container path by replacing the prefix | A28:163-175 (`verified_mount_path`), :262 (the release path it accepted) |
| Layout of the two installs that ran on this host: `<volume>/r2d2-v2-release-<YYYYMMDD>/release.CERTIFIED.json`, directory 0700, file 0600 by exclusive creation, both made by root | P23:11-12,86-92,127-134; P28:11-12,87-93,130-137 |
| The security guard holds the routine for a root-level entry named `r2d2-v2-release-*` **with the suffix `.json`**; a directory of that name is not such an entry. The pin is what holds the routine | REL:scripts/c3po_security_guard.py:15-17 (pin), :19-33 (release clause); tested against the guard's own bytes (`tests/test_native.py`, the guard test) |
| The maintenance pin: `/mnt/day-d-data/.r2d2-v2-pinned` | REL:scripts/c3po_security_guard.py:9,15; required by the install of 28/09 (P28:14,126-127) and by the activation (A28:203-205) |

So the constants of the source are: `DATA_VOLUME=/mnt/day-d-data`, `RELEASE_DIRECTORY_NAME=r2d2-v2-release-20261005`, `RELEASE_FILE_NAME=release.CERTIFIED.json`, and the path the activation will put into the override is `/app/day-d-data/r2d2-v2-release-20261005/release.CERTIFIED.json` (reported in the effects and in the receipt; this source cannot see the container's mounts, section 8).

Not carried over from P23/P28, and where the check went:
- **the comparison of `code_revision` with the deployed revision as a constant of the payload** (P23:9,113; P28:9,122, inside the `RELEASE_SCOPE` refusal, before any write). K10's source judges `code_revision` and `implementation_package_sha` by grammar only: it would install any well-formed release of this epoch, and a release cut for another revision would end as KNOWN_COMPLETE, fail K11 POST, and leave a directory nothing in the family removes. The first revision did not list this omission. The refusal is now made **at binding, mechanically**: `binding/release_fields.py` requires the three expectations as arguments (the hash K11 PRE verified, the deployed revision, the package), compares them in code with the file and with the revision and package this directory was built for, and refuses the fixture of this directory by its marker. Nothing is bound without it (CONTRACT section 6, step 4). Constants in `op.py` would be the stronger form; they are a new payload hash and would need a test fixture that the deployed application accepts, which is a hazard of its own (decision D-11).
- the verification by `docker exec` in the running worker (the family has no `docker exec`; D-1);

Also not carried over, on purpose: the `install.started.json` marker (the states of section 5 are told apart without it, and a second file is a second thing that can be half-written); `os.path.ismount` (replaced by the signed rows: the data volume root must show another device than its parent, and the walk compares the device); `pathlib` calls that follow links.

## 2. Effects, in order

Every mutating call goes through the core's `mutate()` (gate, count, call). The run of the emulation makes 110 host calls, 64 looks at the clock, 5 mutating calls and 5 fsyncs.

| # | Call | On | Note |
|---|---|---|---|
| — | `umask(0o077)` | the process | after the executor identity is known; not a host effect |
| 1 | `mkdir("r2d2-v2-release-20261005", 0o700)` by the held descriptor of the pinned volume root | the data volume root | after `parent.verify` (the chain walked again); EEXIST is not an overwrite: `DESTINATION_APPEARED_AFTER_PRECHECK`, nothing changed |
| | open the new directory (no link followed), fstat, lstat of the name, list (must be empty), `fsync(directory)`, `fsync(volume root)` | | identity, root:root, 0700, the device of its parent, zero entries; anything else leaves it in place, labelled |
| 2 | exclusive create of `.hostops-<go16>-0.partial`, 0600, `O_WRONLY\|O_CREAT\|O_EXCL\|O_NOFOLLOW\|O_CLOEXEC`, by the directory's descriptor | the new directory | `go16` = first 16 hex of the GO hash |
| 3 | `write` of the release bytes (one call for up to 32,768 bytes; repeated while the kernel writes less) | the temporary | then `fsync(file)`, fstat: regular, one link, 0:0, 0600, the signed size, the directory's device |
| 4 | `link(temporary, "release.CERTIFIED.json")` in the same directory, no link followed | the new directory | after the directory is verified again and the temporary looked at again by name. A link never replaces: EEXIST leaves what is there. **Only complete, fsynced bytes ever stand under the final name** |
| | `fsync(directory)` | | |
| 5 | `unlink(temporary)` once the name still shows the inode of the descriptor held | the new directory | then `fsync(directory)`, fstat: one link |
| — | readback (section 7) | | reads only |

Nothing that exists is overwritten, renamed, chmodded, chowned, truncated or removed, except the temporary of this run. On the workstation, with real system calls, a whole run takes 2 to 10 ms.

## 3. Refusals

### 3.1 From the bytes, before any claim (the dispatcher runs `authenticate()` locally; none of these can spend the GO)

The family's own: pins, document keys, canonical bytes, schemas, operation, phase, `writes_allowed` true, `activation_allowed` false, owner, host binding, transport binding, claim root, `DATE_NOT_IN_SCOPE` (the date class is `WRITE_FIRST_SESSION`: 2026-10-05 UTC only, at both layers), `DATE_WINDOW_MISMATCH`, `WINDOW_SPAN` (at most 900 s), `EVIDENCE_UNBOUND`, `EVIDENCE_OPERATION_MISSING` (the request must name a `GO_READONLY_HOSTOPS_PRECHECK_01` receipt), `EFFECTS_BINDING`, `GO_CRITERION`.

K10's own (`validate_plan`), all pure:

| Code | When |
|---|---|
| `CHAIN_ROW_INVALID` | `parent` is not exactly one six-integer row for `/`, `/mnt`, `/mnt/day-d-data` |
| `CHAIN_ROW_UNSAFE` | `/` or `/mnt` not root-owned or writable by group or other |
| `CHAIN_ROW_WORLD_WRITABLE` | the volume root writable by everyone without the sticky bit |
| `PARENT_SETGID` | the volume root setgid (the kernel would hand its group to what is created there) |
| `DATA_VOLUME_NOT_A_MOUNT_POINT` | the signed rows do not show another device at the volume root than at `/mnt` (an unmounted volume is an empty directory of the root filesystem) |
| `EVIDENCE_BOOT_UNBOUND` | no boot identifier hash |
| `RELEASE_PLAN_INVALID` | the `release` member is not `{path, content_b64, sha256, bytes}`, or hash/size out of grammar, or more than 32,768 bytes |
| `RELEASE_PATH_NOT_THE_SIGNED_CONSTANT` | `release.path` is not the constant path of the source |
| `RELEASE_BYTES_NOT_THE_SIGNED_HASH` | not strict base64, or the decoded bytes differ from the signed size or SHA-256 |
| `RELEASE_NOT_JSON` | not one JSON object, a duplicate key, a non-finite number (the application's own rule, REL:…/r2d2_v2_shadow.py:44-54,78) |
| `RELEASE_NOT_A_CERTIFIED_V3_RELEASE` | schema is not `R2D2_V2_RELEASE_V3` or mode is not `CERTIFIED` |
| `RELEASE_EPOCH_NOT_THIS_EPOCH` | `epoch` is not exactly `R2D2-V2-SHADOW-2026-10-05` |
| `RELEASE_FIRST_SESSION_NOT_THIS_EPOCH` | `first_session` is not `2026-10-05` |
| `RELEASE_FIELDS_INVALID` | `code_revision` is not 40 lower-case hex, `implementation_package_sha` not a hash, `approved_at` not an instant-like text (they are shown to the signers in the effects; the grammar is the application's) |
| `WINDOW_NOT_ON_THE_FIRST_SESSION_DAY_IN_NEW_YORK` | the request window begins before 2026-10-05T04:00:00Z (Monday 00:00 in New York, 01:00 BRT) or ends after 2026-10-06T04:00:00Z |

The New York day is two UTC instants in the source: New York is on daylight time (UTC−4) until 2026-11-01, and an operation part may import nothing but `base64` (no `zoneinfo`). A test compares the two instants with the zone database.

### 3.2 On the host, before the first effect (status REFUSED, `phase_reached` PRECHECK; nothing was created)

In this order (the pin and the destination are looked up by name through the held descriptor of the pinned volume root, not by `probe()` as CORE section 11 suggests: that ties both to the very directory that will receive the entry and needs no second walk):

| # | Code | What is looked at |
|---|---|---|
| 1 | `EXECUTOR_IDENTITY` | effective uid and gid 0; nothing else has been looked at |
| 2 | `NOT_THE_FIRST_SESSION_DAY_IN_NEW_YORK` | the run's own clock, 04:00Z ≤ now < 04:00Z of the next day (the window already implies it; the run does not rely on that) |
| 3 | `EVIDENCE_FROM_EARLIER_BOOT`, `BOOT_ID_INVALID` | `/proc/sys/kernel/random/boot_id` against the signed hash |
| 4 | `PARENT_MISSING`, `PARENT_SYMLINK_COMPONENT`, `PARENT_NOT_DIRECTORY`, `PARENT_CHANGED_DURING_WALK`, `PARENT_IDENTITY_MISMATCH`, `NOATIME_UNAVAILABLE` | `/`, `/mnt`, `/mnt/day-d-data` opened by descriptor without following a link; device, inode, uid, gid and mode of each equal to the signed row. A volume that is not mounted has another device and inode: `PARENT_IDENTITY_MISMATCH` |
| 5 | `MAINTENANCE_PIN_ABSENT`, `MAINTENANCE_PIN_NOT_A_REGULAR_FILE`, `MAINTENANCE_PIN_NOT_ROOT_OWNED` | one `lstat` of `.r2d2-v2-pinned` through the held descriptor of the volume root. The pin is also the witness that what root creates in this directory is root:root (an entry root made there on 25/09): with group inheritance it would not be 0:0, and the new directory would be refused after its creation |
| 6 | `DESTINATION_PRESENT` | one `lstat` of `r2d2-v2-release-20261005` through the same descriptor: any kind of entry, a dangling link included; the receipt says what was found |
| 7 | `DATA_VOLUME_FREE_SPACE_BELOW_FLOOR`, `STATVFS_INVALID` | `fstatvfs` on the held descriptor: at least 1 MiB available to a non-root writer |
| 8 | `BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT` | at least 15 s left of the payload budget and of the GO window |
| — | `GO_EXPIRED`, `CLOCK_REVERSED`, `PRECHECK_OS_ERROR`, `PRECHECK_FAILED` | an expiry, or a failed read, anywhere above |

### 3.3 After the precheck (`phase_reached` EFFECTS)

REFUSED only while no mutating call succeeded and none is uncertain; otherwise PARTIAL.

| Code | First effect done? | Status | What is on the host |
|---|---|---|---|
| `PARENT_REPLACED`, `GO_EXPIRED` before the mkdir | no | REFUSED | nothing |
| `DESTINATION_APPEARED_AFTER_PRECHECK` (mkdir EEXIST), `FILESYSTEM_READ_ONLY`, `FILESYSTEM_FULL`, `FILESYSTEM_ACCESS_DENIED`, `FILESYSTEM_ERROR` (the mkdir itself failed) | no (the call changed nothing) | REFUSED | nothing of this run |
| `CREATED_OPEN_FAILED`, `CREATED_STAT_FAILED`, `CREATED_NAME_REPLACED`, `CREATED_LIST_FAILED` | yes | PARTIAL | the directory, unverified |
| `CREATED_METADATA_MISMATCH` (directory) | yes | PARTIAL | the directory, not root:root 0700 on the parent's device; left as it is |
| `CREATED_NOT_EMPTY` | yes | PARTIAL | the directory with a foreign entry |
| `FSYNC_FAILED` (directory or volume root) | yes | PARTIAL | the directory, not known durable |
| `PARENT_REPLACED` after the mkdir | yes | PARTIAL | the directory (or what took its name) |
| `TEMPORARY_NAME_OCCUPIED`, `FILESYSTEM_*` at the creation of the temporary | yes | PARTIAL | the empty directory |
| `FILESYSTEM_*`, `WRITE_INCOMPLETE`, `FSYNC_FAILED`, `CREATED_STAT_FAILED`, `CREATED_METADATA_MISMATCH` while the temporary is written | yes | PARTIAL | the empty directory when the temporary was withdrawn (ledger `NOT_CREATED`, `temporary_removed` true); otherwise the temporary too (`TEMPORARY_ONLY`) |
| `TEMPORARY_REPLACED`, `PARENT_REPLACED`, `GO_EXPIRED` before the link | yes | PARTIAL | directory and temporary (`TEMPORARY_ONLY`) |
| `DESTINATION_APPEARED_AFTER_PRECHECK` (link EEXIST) | yes | PARTIAL | the directory and what appeared; the temporary withdrawn |
| `FSYNC_FAILED` after the link, `TEMPORARY_REMOVAL_FAILED`, `TEMPORARY_REPLACED` at the removal | yes | PARTIAL | directory, final name with complete bytes, temporary (`LINKED_TEMPORARY_PRESENT`) |
| `FSYNC_FAILED` after the removal, `CREATED_METADATA_MISMATCH` (links ≠ 1) | yes | PARTIAL | directory and final name (`INSTALLED_NOT_DURABLE`) |
| `READBACK_HASH_MISMATCH`, `READBACK_UNAVAILABLE`, `FILE_CHANGED_DURING_READ`, `FILE_NOT_REGULAR`, `READBACK_MISMATCH`, `PARENT_REPLACED`, `GO_EXPIRED` in the readback | yes | PARTIAL | directory and final name (`INSTALLED_DURABLE` in the ledger; `installed` is null: the run does not say the release is installed) |
| `RUN_ESCAPED_STATE_UNKNOWN` | unknown | PARTIAL (outcome `PARTIAL_REQUIRES_RECONCILIATION`) | one of the states of section 5 |

Exit 0 and `RELEASE_INSTALLED_BYTES_READ_BACK_NOT_ACTIVATED` exist for one case only: all five mutating calls succeeded, the ledger says `INSTALLED_DURABLE`, and the three readbacks passed.

## 4. Hostile states that are tested

Before the precheck: a symbolic link, a file or nothing at `/mnt` or at the volume root; another inode, owner, group, mode or device of any component (the unmounted volume); a component swapped between its lstat and its open; the pin absent, a link, a directory, a fifo, owned by another uid or gid; the destination present as an empty directory, a directory with foreign content, a file with the right bytes, a link (dangling or not), a fifo; a full volume; a platform without `O_NOATIME`.
After the precheck: the destination appearing before the mkdir; the mkdir refused with each errno; the parent changed before the mkdir; a created directory with another group (inheritance), with another owner and group together, with another owner alone, with another mode (four of them, setgid included) or on another device; the mode, owner or group of the created directory changed before the link and again after it; a creating call that took effect and then raised something that is not an OSError (four kinds, a refusal included); a foreign entry in the new directory; the new directory replaced between the mkdir and its proof, after its creation, and while the temporary is written; the temporary's name occupied; a write that fails, makes no progress or writes less than asked; a temporary with another group, another owner alone, another device, another size (it grew between the write and its proof) or a second link; an expiry and a clock that steps back once while the file is written (nothing is looked at or removed after a refusal of the gate); the temporary swapped before the link and before its removal; the final name appearing before the link; every fsync failing; the installed file tampered, truncated, replaced by a copy or by a link, removed, chmodded, chowned, linked a second time, changed while it is read back or read short; the directory gaining an entry, another mode, or being swapped; the volume root changing at the end.
Two states no kernel produces are tested on the emulation only so that their checks cannot be removed unnoticed, and the tests say so: a descriptor of an exclusive creation that is not a regular file, and a held directory that stops being one.
With real system calls (`tests/test_native.py`): the refusals on a real tree, two real races (a directory at the mkdir, a file at the link), a volume the user cannot write, and a real process death at five points.
The first revision said here "a created directory with another group, owner or device"; its test changed owner and group together, and a mutant that dropped the owner check alone survived. The sentence above is what the tests do now (`tests/test_effects_guards.py`).

## 5. Crash points, and how a later read tells them apart

If the process dies (or SSH is cut and the payload is killed), there is no receipt and the dispatcher files UNCERTAIN. What exists is then one of five states, each visible with `lstat` and a listing of one directory, and they are reached in this order only:

| State | `/mnt/day-d-data/r2d2-v2-release-20261005` | Begins at | Read as |
|---|---|---|---|
| A | absent | — | nothing happened |
| B | a directory root:root 0700, empty | `mkdir` | directory only |
| C | holds only `.hostops-<go16>-0.partial` (0600, one link, a prefix of the bytes, possibly all of them) | exclusive create | no release under the final name |
| D | holds the temporary and `release.CERTIFIED.json`: one inode, two links, the complete bytes | `link` | the release is complete; the temporary was not removed |
| E | holds only `release.CERTIFIED.json`, one link, the complete bytes | `unlink` | the release is in place (whether the last fsync and the readback happened is not visible: a read of the bytes against the signed hash settles it) |

Proved for every one of the 110 host calls of the emulation (the process dies at call n, n = 1 … 110: the tree is in one of the five states, they only move forward, the final name never holds anything but the complete bytes), for an expiry or a reversed clock at every look at the clock, and with a real process death (`os._exit`) at five points on a real filesystem. The same five states are what a PARTIAL receipt reports in its ledger (`NOT_ATTEMPTED`/`NOT_CREATED`, `TEMPORARY_ONLY`, `LINKED_TEMPORARY_PRESENT`, `INSTALLED_NOT_DURABLE`, `INSTALLED_DURABLE`) and in `objects_left_by_this_run` (0, 1, 2, 3, 2).

There is no second attempt. A second request finds the directory and refuses with `DESTINATION_PRESENT`; nothing of a partial run is repaired or removed (the family has no removal operation). By the signed order a refusal or an uncertain result on Monday means the epoch does not start.

**Three of these states hold the signed bytes under the final name** (D; E when the last fsync or the link count failed; E when only the readback or the last parent check did not finish). The application's reader accepts all three (REL:…/r2d2_v2_shadow_worker.py:29-42 checks a regular file, no group or other bit, size and stability; neither the link count nor the directory entries). The gates built for Monday do not: K11 POST raises `RELEASE_DIRECTORY_ENTRIES` and `RELEASE_FILE_METADATA` for state D (two entries, two links), and K6a requires one link (`RELEASE_FILE_NOT_AS_INSTALLED`), and the family has no removal of the temporary (C2 is unbuilt). So state D ends the epoch by construction for a release that is in place. The precedents wrote the final name directly and had no such state; the price of never showing incomplete bytes under the final name is this window (one directory fsync and one unlink, microseconds, or an EIO on a directory fsync). What each state means for ORD:7 is decision D-6, widened to all three; CONTRACT section 4 has the table and the reading that holds until it is answered.

## 6. Time budget

| Limit | Value |
|---|---|
| payload budget (`MAX_SECONDS`) / dispatcher watchdog / transport | 60 s / 80 s / 270 s |
| GO window | at most 900 s, wholly on 2026-10-05 UTC and on the New York day (from 04:00Z) |
| reserved before the first effect (`WRITE_ALLOWANCE_SECONDS`) | 15 s: with less left the run refuses and nothing was created |
| what the run needs | about 110 system calls, 5 of them fsync; 2 to 10 ms on the workstation; the install of 28/09 took 3.8 s end to end on the host, SSH, sudo and a `docker exec` included |
| waits, retries, sleeps, locks, processes | none |

The only calls that can take long are the five fsyncs under heavy disk load. One that outlasts the budget is not interrupted (the kernel call has no timeout); the next look at the clock ends the run as PARTIAL with `GO_EXPIRED`, in one of the states of section 5. M1 is resumed no earlier than 05:28:00 BRT by the dispatching machine's clock (its window opens at 05:26:00), after the controller cycle (HH:10–25) and before the watchdog minutes (HH:35–37) that its window (05:26–05:41) also covers; this source takes no lock, starts nothing and is not affected by the deployment lock.

Why not 05:27: the dispatcher admits the dispatch by the Mac's clock and the payload authenticates by the host's. A host clock behind the Mac's by more than the time elapsed since `not_before` answers `OUTSIDE_GO_WINDOW`: a KNOWN_REFUSAL at phase AUTHENTICATION, which spends the signature and, by ORD:7, the epoch. Sunday's dry validation cannot show a skew that exists on Monday. `binding/predispatch.py` measures the skew at the end of M0 (the host's clock in M0's receipt against the Mac's clock in M0's exit record), refuses above 30 s, and at the step `resume` refuses before `not_before` + 120 s.

## 7. What the owner signs, and what the in-run readback proves

**Signed by hash (request → authority → GO), per request:**

| Field | Content |
|---|---|
| `payload_sha256`, `scope_sha256` | these bytes and their scope: the constants of sections 1 and 3 (epoch, first session, New York day, paths, limits), the core generation, "processes started: 0" |
| `date`, `not_before`, `not_after` | 2026-10-05; a window of at most 900 s |
| `evidence` | the receipts the rows were copied from; one of them a `GO_READONLY_HOSTOPS_PRECHECK_01` receipt |
| `plan.parent` | the three rows of `/`, `/mnt`, `/mnt/day-d-data` (device, inode, uid, gid, mode), from a read-only receipt of the same boot |
| `plan.evidence_boot_id_sha256` | the boot of that receipt |
| `plan.release` | `path` (the constant), `content_b64` (the release bytes, embedded), `sha256`, `bytes` |

**Literal in the authority and in the GO (`effects`), recomputed by the code from the plan:** the operation; the volume root's row, the hash of its chain and its mount point; the directory (path, 0700, 0:0, expected absent); the file (path, SHA-256, size, 0600, 0:0, one link); what the release says of itself (schema, mode, epoch, first session, `code_revision`, `implementation_package_sha`, `approved_at`); the path of the file inside the worker; the pin requirement; the New York day; the boot; and four constants: no existing object modified, no activation, no container recreated, no process started.

The release bytes are not known when the source is sealed. They are a bind-time input: `binding/release_fields.py <release file>` prints the `release` member (bytes embedded, hash and size computed), judged by the source's own `release_of()` and `release_facts()`, so a release the tool accepts is one `validate_plan` accepts.

**What the readback inside the run proves** (only then is the run complete):
1. the final name, opened again through the directory's descriptor without following a link, is the inode this run created, a regular file, root:root 0600, one link, and its bytes equal the signed bytes (read between two fstat calls that agree);
2. the path `/mnt/day-d-data/r2d2-v2-release-20261005`, resolved again from `/` without following a link, leads to the directory this run holds: root:root 0700, exactly one entry;
3. the three parents are still what was signed.
These are the conditions of the worker's reader (regular, no group or other bit, at most 65,536 bytes). With a checkout of the release, a test goes one step further: the file a real run wrote on a real filesystem is read by the application's own `_release_bytes` and verified by its own `Release.verify`.

## 8. What only the host can prove

1. That `/mnt/day-d-data` is the source of the worker's bind at `/app/day-d-data` on Monday (this source starts no docker command). On record: the HOSTFACTS receipt and A28:163-175. K11 and K6a read the mounts.
2. That root in the worker's container reads a 0600 file in a 0700 directory, both root-owned (no user-namespace remapping). On record: the same layout, owner and modes worked on 23/09 and 28/09.
3. That the application accepts the release at that instant in the deployed image: K11 PRE (Sunday) and POST (Monday).
4. That an entry root creates in the volume root is root:root on the volume's device (no group inheritance). In-run witness: the pin's owner. The first proof is the mkdir itself; a mismatch is PARTIAL with the directory left in place.
5. That the filesystem of the data volume supports a hard link inside one directory and fsync on a directory descriptor opened read-only with `O_NOATIME`. The earlier installs proved mkdir, exclusive create and directory fsync there (P28:22-25,89,130-137) but wrote the final name directly: **`linkat` and `unlinkat` have not been executed on that filesystem by any payload** (section 9). What can be read before Monday: the type of that filesystem, its read-write state and its free inodes are in every W1 receipt (`sections.data_volume.mount.filesystem_type`, `.mount.read_write`, `.filesystem.read_only`, `.filesystem.f_favail`), and `binding/predispatch.py` refuses a type without hard links.
5b. That there is a free inode. The core's `free_bytes()` reads blocks only; with no inode left the mkdir fails (refused, nothing changed, epoch lost), with exactly one the mkdir succeeds and the temporary cannot be created (PARTIAL with the empty directory, the constant path burnt). The inode table of an ext filesystem is fixed at mkfs. Not looked at by the payload (the core is frozen); looked at by the Monday gate and at binding (W1's `f_favail`).
6. Durability across a power loss: five fsyncs are issued and their return checked; nothing can prove more.
7. The fsync latency of that disk at 05:27 BRT.
8. What the operational account does afterwards. The volume root belongs to it (uid 1000 in the signed row), so it can rename the directory root created there. During the run that is seen (`PARENT_REPLACED`, `CREATED_NAME_REPLACED`, `READBACK_MISMATCH`); after the run only a read sees it. It cannot read or change the file (0600 in a 0700 directory, both root's).

## 9. Shapes: proven, emulated, UNPROVEN

K10 has no command row: no docker, no systemctl, no compose. Its shapes are system calls and one path.

| Shape | Status | Precedent |
|---|---|---|
| launcher under `sudo -n /usr/bin/python3 -I -B -`; the walk by `dir_fd` with `O_NOFOLLOW\|O_NOATIME` on `/`, `/mnt`, the volume root; `fstatvfs` on the held descriptor; `/proc/sys/kernel/random/boot_id` | proven on the host (other bytes of the family) | CORE section 10; HOSTFACTS receipt |
| path `<volume>/r2d2-v2-release-<YYYYMMDD>/release.CERTIFIED.json`, directory 0700, file 0600, root-owned, read by the worker through `/app/day-d-data` | proven on the host | P23, P28, A28:262-276 |
| `mkdir(…, 0o700)` in the volume root; exclusive `O_CREAT\|O_EXCL\|O_NOFOLLOW` create 0600; `fsync` of a directory descriptor | proven on the host by path (P28:22-25,89,130); **by `dir_fd`: UNPROVEN on the host** until hostops01's receipts exist: A3 and A4 (provision) make `mkdir` by `dir_fd`, the `O_NOATIME` open of the new directory and the two directory fsyncs; B1 (install_units) makes the exclusive create, the write, the file fsync, `linkat`, `unlinkat` and the directory fsyncs with the bytes the core's `files` part was derived from (`../core/DELTA/files.create_file.diff`: arguments only). B1 writes in the unit directory, on the root filesystem, never on the data volume | CONTRACT section 5, check (j) |
| `lstat` of the pin and of the destination by the descriptor of the volume root | UNPROVEN on the host (P28:127 used `Path.is_file()`) | — |
| **U-K10-1** `linkat(temporary → final)` and `unlinkat(temporary)` inside the new directory of the data volume | **UNPROVEN anywhere on this host's data volume.** Real on the workstation (APFS). Narrowed, not closed, by: the Linux job (ext4, real root); B1's receipt (the same two calls as root on this host, on the root filesystem); a W1 receipt that names the data volume's filesystem type as one with hard links | none found: P23/P28 wrote the final name directly |
| **U-K10-2** the mutating path of the core's `files` part as real root on Linux/ext4 (U1 of the core: these bytes differ from HOSTOPS01's by arguments only, and HOSTOPS01's passed) | UNPROVEN until the core's Linux job runs with this directory as argument. **A gate now, not a note:** `binding/linux_proof.py` reads the job's two junit files and accepts only a run of the whole suite of this seal in which every creating test ran as uid 0 on ext4 under Python 3.12 with the kernel's `O_NOATIME`; nothing is bound before it does | `../core/linux_root/run.sh ../install_release` |
| **U-K10-3** root-created entries in the volume root are 0:0 on the volume's device (no `grpid`, no ACL default that changes the mode) | UNPROVEN except by the witness (pin 0:0 0600; a directory root had created in the volume root was required to be uid 0 on 28/09 and passed, A28:101-113) | read-only receipt before signing |
| **U-K10-4** the assembled source under the host's `/usr/bin/python3` (3.12 by the core's note); tested here on 3.9.6 and 3.12.14 | UNPROVEN on the host's build | Sunday dry validation is offline; the first run is Monday |
| docker CLI, compose, containers, systemctl | not used | — |

What the CI proof must exercise for K10: the suite of this directory as real root and as an ordinary user on ubuntu-24.04 (the native tests then run `mkdirat`/`openat`/`linkat`/`unlinkat`/`fsync` on ext4 with the kernel's `O_NOATIME`, Linux errno values and uid 0). No shape of `shapes.py` is needed: there is no argv.

How the job's result becomes checkable: `tests/test_native.py::test_native_run_records_where_it_ran_for_the_linux_proof` makes one real install and writes into the junit file, as properties of its test case, where it ran (effective uid and gid, platform, Python, whether `O_NOATIME` is the kernel's flag, the filesystem type from the process's mount table, owner, group, mode and link count of what was created as the unpatched `os` module reads them) and on what (the payload hash and the hash of `SHA256SUMS`). `binding/linux_proof.py` compares them with this directory as it is. A run on the workstation is refused by the same tool (a test proves it on whatever machine the suite runs).

## 10. Open decisions

- **D-1 (co-auditor, then owner).** No `Release.verify` inside K10; K11 PRE and POST carry it. The precedents verified before writing (P28:54-86, called at :128). If the signers want it in K10, that is a new source with the runner and docker parts and their unproven shapes.
- **D-2 (Saturday sheet, C#7).** The path is a constant of the source: `/mnt/day-d-data/r2d2-v2-release-20261005/release.CERTIFIED.json`. Another path is a new payload hash (the core is not touched).
- **D-3 (co-auditor).** The evidence the code requires by name is hostops01's OP_PRECHECK (S1, chain DATA_VOLUME). If the rows are to come from K11 PRE instead, the constant changes before sealing.
- **D-4 (owner).** The pin must be a regular file owned by root:root. Stricter than the guard (which accepts any existing name) and equal to P28 for the type. The binder checks the pin's row in Sunday's receipt before asking for the signature.
- **D-5.** No `install.started.json`. Nothing downstream (K11, K6a, X5) may expect it.
- **D-6 (owner and co-auditor), widened by the review.** Every KNOWN_PARTIAL in which the final name holds the signed bytes: state D (`LINKED_TEMPORARY_PRESENT`), state E not durable (`INSTALLED_NOT_DURABLE`), state E with a late failure (`INSTALLED_DURABLE`, readback or last parent check not finished). Does the epoch start after K11 POST verifies the file, or is each "uncertain" in the sense of ORD:7? For state D the answer needs more than a reading: K11 POST and K6a as built refuse two links and two entries, so either the loss is accepted, or the removal of this run's own temporary (C2) is built and pre-bound as a contingency, or K11 and K6a accept the second link when it is the temporary of M1's own GO. To be answered before Sunday's signature; until then the strict reading holds (CONTRACT section 4).
- **D-7.** The spare M1′ is a second request over the same payload hash; usable only if M1 was never dispatched (Q-R). If both were dispatched, the second refuses with `DESTINATION_PRESENT` and changes nothing.
- **D-8.** Limits as constants: release at most 32,768 bytes (release 28 was 5,194), free-space floor 1 MiB, 15 s before the first effect.
- **D-9.** Who pushes the throwaway branch that runs the Linux job with `OPERATIONS="../install_release"` (a GitHub write; not done here).
- **D-10.** The filesystem type of the data volume (hard links) from a read-only receipt before the signature (U-K10-1). Answered by a field, no longer open as a question of where to read it: `sections.data_volume.mount.filesystem_type` of any W1 receipt; checked by `binding/predispatch.py`.
- **D-11 (co-auditor; new, found by the review).** The source does not compare `code_revision` and `implementation_package_sha` with the deployed values (both precedents did, as payload constants). The comparison is made at binding by `binding/release_fields.py`, with required expectations and the two values this directory was built for; K11 PRE verifies the same bytes in the deployed image on Sunday. Is the bind-time refusal enough, or must the two values become constants of `op.py` (a new payload hash, a new review, and a fixture question)?
- **D-12 (owner; new).** The Monday gate: on `DO_NOT_DISPATCH` neither M1 nor M1′ is prepared, and the way out is a new OP_PRECHECK receipt, a new binding and a new signature between 05:00 and 07:00. Is the owner's line on the sheet that he will sign such a re-bound request by hash that morning?

## 11. Core defects

None that blocks K10, and none worked around: the core is frozen and was not edited. Observations for the core's author; items 4 to 8 came out of the review:
1. `CORE.md` section 11 lists `runner` and `docker` among K10's parts. K10 needs neither; `assemble.py` builds `['core','parents','files']` and the conformance suite passes on a source without `COMMANDS` (121 tests).
2. `tests/hostemu.py`: `FakeHost.open` looks the node up before it calls the hook, `lstat` after. A test that swaps a name "at the open" swaps nothing; K10's tests act at the preceding `lstat` or in the gate.
3. The core's launcher mutants are named `X01`…`X04`; an operation's own rows must avoid the prefix (K10 uses `W`). Three dispatcher rows of the core's list (`D02`, `D71`, `D72`) are anchored on the date literal of the demonstration operations and do not apply to another date class; K10 carries their equivalents (`D02k`, `D71k`–`D73k`).
4. `tests/conformance.py`, the test of single use (`test_prepare_does_not_spawn_then_resume_once_and_the_go_is_single_use`, line 630): the second `resume` is given `family.never` as its transport and is expected to raise `FileExistsError`. When the spawn marker is not written (mutant: the `write('spawn.claim', …)` line removed), `never` IS called, its `AssertionError` is swallowed by the dispatcher's own `except Exception`, and the expected `FileExistsError` then comes from `stdout.private.json` of the first resume. The test passes although the payload was offered to the transport twice. K10 pins single use with a counting transport (`tests/test_dispatch_guards.py`); every other operation on the core inherits the weak test.
5. The same suite leaves these dispatcher and launcher guards unpinned for an operation (each survived as a mutant of K10's generated files): `FINAL_BUNDLE_BYTES`, `INNER_WINDOW` (both halves), `INNER_BINDINGS`, `PREFLIGHT_BUDGET`, the claim read at `resume`, the intent compared with the expected one, the receipt bound to the payload hash, `COMMAND_PIN` and the key and known-hosts pins before the claim, `STDIN_SOURCE_PIN`. K10 carries its own tests; they belong in the conformance suite.
6. `parts/parents.py`, `free_bytes()`: blocks only (`f_bavail*f_frsize`). A write operation that creates entries cannot refuse on an exhausted inode table before its first effect; it finds out at the mkdir or, worse, at the second creation. A `free_inodes()` beside it would let an operation refuse in the precheck.
7. `parts/core.py`, `mutate()`: "an OSError raised by the call itself means that call changed nothing". A Refused raised inside the action (no Native does it; a test double can) is caught by the files part as a refusal of the gate and its ledger row says `NOT_ATTEMPTED`, while the call may have taken effect. Only `Effects.clean()` counting the unsettled call keeps the receipt from saying REFUSED_NOTHING_CHANGED; the core's own mutant of `clean()` (T08) is not killed by a test of that path in an operation's suite. K10 has one now.
8. `parts/files.py`, the guards `stat.S_ISREG` on the descriptor of an exclusive creation and `found['type']=='dir'` in `readback_directory`: both are checks of states no kernel produces. They cost nothing and K10 pins them on the emulation; the core's notes could say that they are defensive, so that a reviewer does not look for the scenario.

## 12. The review of 2026-10-02 and what answers each finding

Fifteen findings from two reviewers; three of them are the same point seen twice (the seal and the review directories; the pin's group in K10 against K11; the revision check). All were accepted, four with a correction of a detail. No payload byte changed.

| # | Finding | Answer |
|---|---|---|
| 1 (MAJOR) | No byte of K10 has run its mutating path on Linux, as real root or on the host; the Linux job is a note | `binding/linux_proof.py` and the recording test: the job's result is a gate of the binding (CONTRACT 6, step 2). Host evidence named per receipt in CONTRACT 5 (j). Corrected detail: A3 and A4 make no exclusive creation (mkdir and fsync only), and B1's link and unlink are on the root filesystem, so they narrow U-K10-1 and do not close it |
| 2 (MAJOR) | No Monday gate: M1 would be dispatched into a refusal M0 had shown | `binding/predispatch.py` (each check names the refusal it predicts), CONTRACT 6 steps 12, 14 and 15. Corrected detail: M0 CAN show the destination by its exact name (a W1 request signs release directory candidates) and the rows of `/` and `/mnt` (W1's `ancestors`); what it cannot show is the boot identifier, which is inferred |
| 3 | Mac clock against host clock | measured at the end of M0, 30 s; `resume` not before `not_before` + 120 s (the same tool, step `resume`) |
| 4, 14 | K10 requires the pin root:root; K11 PRE and the pin's creator judged the uid only | the Monday gate and the Sunday run of the same tool judge type, uid and gid; CONTRACT 5 (a). K11 is another directory: reported to its author |
| 5 | free inodes are not looked at | corrected detail: a source does read them (W1's `filesystem.f_favail`, the bytes of M0). The gate requires 1024, on Sunday and on Monday; CONTRACT 5 (h); core observation 6 |
| 6 | D-6 covers one of three states; state D cannot pass K11 POST and K6a | D-6 widened; CONTRACT 4 has the table and the strict reading until answered |
| 7, 11 | `seal.py check` broke on the reviewers' own directories | directories named `review-*` are outside the seal; the mutation copies leave them out |
| 8 | nothing stops M1′ after M1 | the gate's role `spare` refuses when the primary's claim exists; CONTRACT 6 step 15 |
| 9, 10 (MAJOR) | `code_revision` and the package judged by grammar only | `binding/release_fields.py` with three required expectations, the two values of this directory, the fixture's marker; D-11; section 1 above |
| 12 | 27 of the reviewer's 60 mutants survived the suite | the reviewer's tests are in the suite, the 60 mutants are a list of this directory (`mutation/review.py`): 58 killed, 2 equivalent with reasons. Corrected detail: of the seven the reviewer named equivalent, five are not (F07, F09, F11, F12, and the core's T08 here) and are killed |
| 13 | cross-operation refusal tested against two demonstration operations only | `tests/test_purity.py`, and `OTHERS` of the conformance suite, take sibling operations and earlier families from the caller; the seal records one run with them, apart |
| 15 | two sentences stronger than the tests | corrected in section 4 above and in CONTRACT section 9 |
