# K6a — activate (`GO_WRITE_HOSTOPS02_ACTIVATE_01`) — design

Offline work only. Nothing here was run on the host, pushed or bound. No docker exists on the workstation: every command
shape below ran on the emulation of the core (`core/tests/hostemu.py`) and nowhere else, unless a line says where it ran before.
Counts and hashes are in `VALIDATION.json` and `SHA256SUMS`, taken by command.

This is the candidate as repaired after two independent reviews of 2026-10-02 (one read against the reality of the host,
one for purity of the source). Section 12 says, finding by finding, what was accepted and what changed. The payload
bytes changed, so every hash of the first candidate is void; the copy of that candidate is kept beside this directory.

Abbreviations. `E28` = `…/va/work/r2d2-plan-b-baseline-20260927/rescue-s2-rev-s/night-activation-review-rev1/worker-live-control.bound.py`
(the activation payload that ran on the host on 2026-09-28). `PIPE` = `.github/workflows/c3po-pipeline.yml` at dd4ec4bb.
`APP` = `c3po/backend/app/` at dd4ec4bb. `CORE` = `hostops02/core` (generation `4c24c5cf…d0d6`). `op.py` = this operation's own part.

Contents: 1 what it does · 2 what the owner signs · 3 everything looked at before the first effect, and every refusal ·
4 the effects, their readback, and what a partial says · 5 the 60 seconds · 6 crash points and how a later read tells them apart ·
7 what the in-run readback proves and what only the host can prove · 8 command shapes: proven and UNPROVEN ·
9 what of 2026-09-28 is not ported · 10 open decisions · 11 how it was tested · 12 what changed after the two reviews.

---

## 1. What it does

Single shot, on 2026-10-05 UTC only (`DATE_CLASS='WRITE_FIRST_SESSION'`), gate at most 900 s. `WRITES_ALLOWED=True`,
`ACTIVATION_ALLOWED=False` (no systemd unit is switched; the recreate of a compose service is not an activation in the
family's sense, CORE.md rule 8.2). Parts carried: core, runner, docker, parents, files, lock.

Effects, in this order, all under the deployment lock:

| # | Effect | How | Precedent |
|---|---|---|---|
| E1 | One private directory `<live parent>/<directory_name>`, root:root 0700 | `create_directory` of the core: one `mkdir` by descriptor in the pinned parent, proved, fsynced | `E28:294-295` (`PRIVATE.mkdir(mode=448)`) |
| E2 | The live policy `<directory>/<policy name>`, root:root 0600, the signed bytes | `create_file` index 0: exclusive temporary `.hostops-<go16>-0.partial`, fsync, link (never replaces), proved removal of the temporary | `E28:296-300` (exclusive 0600 file, fsync) |
| E3 | The compose override `<directory>/<override name>`, root:root 0600 | `create_file` index 1. Bytes computed by the source, not signed as bytes: `json.dumps({'services':{'r2d2-worker':{'environment':{4 names}}}},sort_keys=True)`; their hash and size are in the signed effects | `E28:301-302` (`write_new(OVERRIDE, json.dumps(override).encode())`): the same token shape and, as it happens, the same key order |
| E4 | ONE recreate of `r2d2-worker` | `docker compose --project-name <p> --env-file <deploy>/.env -f <deploy>/<p>/compose.yml -f <override> up -d --no-deps --no-build --pull never --force-recreate r2d2-worker`, with `C3PO_BUILD_SHA=<revision>` in the environment of the command, output not captured | `E28:223` (base argv), `E28:303` (`-f OVERRIDE`), `E28:323` (the `up` words), `E28:222` (`C3PO_BUILD_SHA`); file list of the deploy: `PIPE:745-746` |

The four names of the override (`E28:12`; settings `APP/config.py:197-198, 207-208` under `env_prefix="C3PO_"`, `config.py:20`):

| Name | Value (derived, never free) |
|---|---|
| `C3PO_R2D2_V2_LIVE_POLICY_FILE` | container path of the delivered policy: `mount_target` + (policy path − `data_root`) |
| `C3PO_R2D2_V2_LIVE_POLICY_SHA` | sha256 of the signed policy bytes |
| `C3PO_R2D2_V2_SHADOW_RELEASE_FILE` | container path of the installed release |
| `C3PO_R2D2_V2_SHADOW_RELEASE_SHA` | sha256 of the installed release (signed; compared with the bytes on the host) |

Nothing else: no `docker exec`, no shell, no systemctl, no pull, no build, no second recreate, no change of `.env` or of
`compose.yml`, no overwrite, rename, chmod, chown, and no removal except the run's own temporary once its identity is proved.

Side effects, stated in the signed scope: the running worker container is stopped and replaced (what it held in memory is
lost); the new worker writes its own status and journal files into the directory this run created
(`APP/r2d2_v2_live_controller.py:269-325`); the deployment lock is held from before E1 until the last readback, the
3 s pause of section 5 included.

---

## 2. What the owner signs

The request plan (`PLAN_KEYS`), every member in the signed request; the authority and the GO carry `effects_of(plan)` literally.

| Member | Content | Comes from |
|---|---|---|
| `data_root` | host path of the data volume root: the open root of the chains below it AND the source of the worker's bind | read-only receipt (hostfacts/K11 PRE) |
| `live_parent` | rows `{path,device,inode,uid,gid,mode}` from `/` of the existing directory the dated directory is created in (on 2026-09-28: `<data root>/r2d2-v2-live`, `E28:9`) | K11 PRE or a precheck receipt of the same boot |
| `directory_name` | the dated leaf (on 2026-09-28: the date) | decision of the signers |
| `policy` | `{name, content_b64, sha256, bytes}`: the live policy, at most 16384 bytes | the policy approved by hash |
| `override_name` | file name of the override in the same directory | decision of the signers (2026-09-28: `compose.proof.json`) |
| `release` | `{parent (rows), directory_name, file_name, sha256, bytes}`: where K10 installed the release | the release approved by hash; the parent's rows from the same boot. The release directory itself does not exist when this is signed: it is opened by name under the pinned parent |
| `worker` | `{image_id, mount_target}`: the backend image ID and the container path the data root is bound at (`/app/day-d-data`, `c3po/compose.yml:165`) | post-deploy readback / K11 PRE |
| `compose` | `{project, env_file, files}`: constrained to the deploy layout, see below | `PIPE:631, 745-746` |
| `deploy_directory` | rows of the deploy tree root (holds `.env`, `.deploy-version`) | K11 PRE |
| `lock` | `{directory (rows of <deploy>/runtime/security), wait_seconds ≤ 20}` | K11 PRE; `PIPE:635-654` |
| `evidence_boot_id_sha256` | the boot of the receipts the rows come from | the same receipts |

Not free, derived in the source and shown in `effects`: the four values; the override bytes (hash, size); the worker
container name `<project>-r2d2-worker-1`; the lock path `<deploy>/runtime/security/deployment.lock`; the pin path
`<data root>/.r2d2-v2-pinned`; the reboot marker `/run/c3po-security/reboot.pending`.
Code constants, in the signed scope: epoch `R2D2-V2-SHADOW-2026-10-05` (`APP/r2d2_v2_epoch_assembler.py:9`), revision
`dd4ec4bb…e858`, package `b5ce527a…db84`, runtime order `1ad8b90c…9d8e` (`APP/r2d2_v2_live_controller.py:30`), first open
`2026-10-05T13:30:00Z`, last close `2026-10-09T20:00:00Z`, service `r2d2-worker`, the four names, the budget figures.

`effects_of(plan)` — what the signers read without opening the request: operation, epoch, revision, data root; the live
parent (its row, the hash of its chain, the mount point by device change); the directory (path, 0700, `ABSENT`); the two
files (path, sha256, bytes, 0600); of the policy its digest exactly as the assembler of the release computes it
(`digest()` of `APP/r2d2_v2_epoch_assembler.py:24-28`: keys sorted, compact separators, `ensure_ascii=False`: the
`policy_sha` of Act B, also for a policy whose text is not ASCII), window, capacity and release hash; the release (parent, path, sha256, bytes, `…READ_AND_COMPARED_NEVER_WRITTEN`); the recreate (project,
environment file, the exact file list with the override, service, container, image ID, build revision, the four names and
values, the worker's bind, the lock path, wait and chain hash, the deploy directory); what is required (pin, no reboot
marker, deploy version); the boot; `pre_existing_objects_modified: THE_WORKER_CONTAINER_IS_REPLACED`; `activation: false`.

`EVIDENCE_OPERATIONS=('GO_READONLY_HOSTOPS02_EPOCH_READBACK_01',)`: the request must cite at least one receipt of the
epoch readback (K11), whose dry run of the same boot (M2p) reads the four chains this request signs: the live parent,
the release parent, the deploy tree and the lock directory. A request that cites only a precheck of the earlier family,
a host-facts read, a write receipt or any other name is refused from its bytes (`EVIDENCE_OPERATION_MISSING`, met
locally by the dispatcher before any claim: it cannot spend the GO). Other receipts may be cited besides. The code
cannot read the receipt: that the rows were copied from it is the binder's check and the co-auditor's. The price is a
coupling to K11's operation name: if that name changes before the signature, this constant follows and the payload
hash moves. Open decision 1 is closed by this.

---

## 3. Everything looked at before the first effect, and every refusal

Three places a refusal can come from. In all three nothing on the host has changed.

**AUTH** — from the signed bytes alone (`validate_plan`, pure). The dispatcher runs it locally before any claim, so these
never spend the GO; on the host the receipt says `phase_reached: AUTHENTICATION`.

| Code | When |
|---|---|
| the core's authentication codes | pins, schemas, flags, owner, host binding, transport, claim root, `DATE_NOT_IN_SCOPE`, windows, `SCOPE_MISMATCH`, evidence (`EVIDENCE_UNBOUND`; `EVIDENCE_OPERATION_MISSING` when no receipt of K11 is cited), `EFFECTS_BINDING`, `GO_CRITERION` (CORE.md 6.1; unchanged) |
| `PATH_INVALID` | `data_root` is not a clean absolute path, or is `/` |
| `EVIDENCE_BOOT_UNBOUND` | no boot hash |
| `CHAIN_ROW_INVALID`, `CHAIN_ROW_UNSAFE`, `CHAIN_ROW_WORLD_WRITABLE`, `PARENT_SETGID` | one of the four chains (live parent: open root = data root, must not be setgid; release parent: open root = data root; deploy directory and lock directory: open root = the deploy tree) |
| `LIVE_PARENT_OUTSIDE_DATA_ROOT`, `RELEASE_OUTSIDE_DATA_ROOT` | the worker could not see the file through its bind of the data root |
| `DIRECTORY_NAME_INVALID`, `OVERRIDE_NAME_INVALID`, `FILE_PATH_INVALID` | not a plain name; the override named like the policy or like a file the worker writes next to it (`<policy>.…`); a path longer than a clean path (it would otherwise fail after the directory exists) |
| `RELEASE_REQUEST_INVALID`, `WORKER_REQUEST_INVALID`, `COMPOSE_REQUEST_INVALID`, `LOCK_REQUEST_INVALID` | key sets, hashes, sizes, image by ID, wait ≤ 20 |
| `PATHS_OVERLAP` | live directory and release directory inside one another; data root and deploy tree inside one another |
| `POLICY_REQUEST_INVALID`, `POLICY_BYTES_NOT_THE_SIGNED_HASH`, `POLICY_JSON_INVALID` | the policy bytes; `POLICY_JSON_INVALID` also for a text no digest can be computed of (a lone surrogate) |
| `POLICY_SCHEMA`, `POLICY_IDENTITY`, `POLICY_RUNTIME_ORDER`, `POLICY_PACKAGE`, `POLICY_REVISION`, `POLICY_CAPACITY`, `POLICY_RECERTIFICATION`, `POLICY_WINDOW`, `POLICY_NOT_EPOCH_WIDE` | what the controller will require at every step (`read_policy`, `APP/r2d2_v2_live_controller.py:39-57, 87`) and what the assembler will require of the same policy (`validate_policy`, `APP/r2d2_v2_epoch_assembler.py:64-79`): schema, mode LIVE, epoch, `release_sha` = the signed release hash, order, package, revision, capacity 1..550, the two receipt hashes, a UTC window of at most 90 days that covers first open to last close |
| `POLICY_WINDOW_DOES_NOT_COVER_THE_GO` | the policy is not valid yet when this run's window opens (the worker would answer `LIVE_POLICY_OUTSIDE_WINDOW`) |
| `COMPOSE_PROJECT`, `COMPOSE_FILES`, `COMPOSE_NOT_THE_DEPLOY_LAYOUT` | the file list is not exactly the deploy's: `<deploy>/.env` and the one file `<deploy>/<project>/compose.yml` (`PIPE:745-746`) |
| `LOCK_NOT_THE_DEPLOYMENT_LOCK` | the lock directory is not `<deploy>/runtime/security` (`PIPE:635, 653`): a lock nobody else takes excludes nobody |
| `ENVIRONMENT_EXPECTATION` | a value does not fit the grammar of the boolean template (256 characters of `[A-Za-z0-9_./:@+=-]`) |

**PRECHECK** — on the host, in this order; `phase_reached: PRECHECK`; the GO is spent, nothing changed, no creating call
was issued, no effect command was started, the lock is released if it was taken.

| # | What is looked at | Codes |
|---|---|---|
| 1 | executor is 0:0; umask 077 (process only); boot = the evidence's | `EXECUTOR_IDENTITY`, `EVIDENCE_FROM_EARLIER_BOOT`, `BOOT_ID_INVALID` |
| 2 | live parent walked from `/` by descriptor, no link followed, every row equal to the signed one; held | `PARENT_MISSING`, `PARENT_SYMLINK_COMPONENT`, `PARENT_NOT_DIRECTORY`, `PARENT_CHANGED_DURING_WALK`, `PARENT_IDENTITY_MISMATCH`, `PARENT_UNREADABLE`, `NOATIME_UNAVAILABLE` |
| 3 | the dated directory does not exist, whatever it would be | `DESTINATION_PRESENT` |
| 4 | the maintenance pin is a regular file in the data root (`E28:203-205`; guard of the security controller) | `MAINTENANCE_PIN_ABSENT` |
| 5 | the release: parent walked and held; the release directory by name under it, not through a link, root:root 0700 on the parent's device; the file a regular file, root:root 0600, one link; its bytes read (≤ 65536) and compared with the signed size and hash | chain codes; `RELEASE_NOT_INSTALLED`, `RELEASE_DIRECTORY_NOT_AS_INSTALLED`, `RELEASE_FILE_NOT_AS_INSTALLED`, `RELEASE_HASH_MISMATCH`, `FILE_TOO_LARGE`, `FILE_CHANGED_DURING_READ` |
| 6 | deploy tree walked and held; `.deploy-version` says the revision (`E28:199`; `PIPE:766`); the environment file is a regular file: its signature and the hash of its bytes are taken into memory. The same for the compose file: the project directory `<deploy>/<project>` opened by name under the held deploy tree, never through a link, and held; `compose.yml` in it a regular file of at most 1 MiB, its signature and hash taken into memory BEFORE the first render is made from it. Its text is never judged (the render is); no value, digest or size of either file leaves the run | chain codes; `DEPLOY_VERSION_ABSENT`, `DEPLOY_VERSION_NOT_REGULAR`, `DEPLOY_VERSION_MISMATCH`, `ENV_FILE_ABSENT`, `ENV_FILE_NOT_REGULAR`, `COMPOSE_FILE_ABSENT`, `COMPOSE_DIRECTORY_NOT_A_DIRECTORY`, `COMPOSE_FILE_NOT_REGULAR`, `FILE_TOO_LARGE` |
| 7 | lock directory walked and held; the lock file opened read-only (never created) | chain codes; `LOCK_FILE_ABSENT`, `LOCK_FILE_NOT_REGULAR`, `LOCK_FILE_REPLACED` |
| 8 | the worker by name: running, on the signed image | `BINARY_UNAVAILABLE_OR_UNSAFE`, `COMMAND_*`, `CONTAINER_METADATA_INVALID`, `WORKER_NOT_RUNNING`, `WORKER_IMAGE_NOT_THE_SIGNED_ONE` |
| 9 | the image by ID: present, revision label = the epoch's revision | `IMAGE_ABSENT_OR_UNREADABLE`, `IMAGE_METADATA_INVALID`, `IMAGE_REVISION_MISMATCH` |
| 10 | the worker's environment through the boolean template: `C3PO_BUILD_SHA` present and equal; none of the four names present (`E28:210-211, 225`) | `ENVIRONMENT_METADATA_INVALID`, `WORKER_BUILD_REVISION`, `WORKER_ALREADY_CARRIES_THE_KEYS` |
| 11 | the render with the override on standard input, timed (`E28:283-284`): build revision, the four values, the image reference a plain reference, the two files reached through exactly one volume: the bind of the data root at the signed target, not read-only, not shadowed (`E28:163-175` did this from `docker inspect`). The two paths of a volume are compared in one spelling: a trailing or doubled slash or a `.` component in what compose prints (the source comes from the host's `.env`) names the same directory; `..`, a relative path or anything that is not text does not | `COMPOSE_RENDER_INVALID`, `COMPOSE_SERVICE_INVALID`, `RENDER_BUILD_REVISION`, `RENDER_ENVIRONMENT_MISMATCH`, `RENDER_IMAGE_INVALID`, `RENDER_VOLUMES_INVALID`, `WORKER_MOUNT_NOT_AS_SIGNED`, `COMMAND_OUTPUT_LIMIT` |
| 12 | the image reference of the render resolves to the signed image ID (`E28:285-288`) | `RENDER_IMAGE_UNRESOLVED`, `RENDER_IMAGE_CHANGED` |
| 13 | **the lock**: exclusive, non-blocking, again every 0.25 s for at most the signed seconds and never past the point where section 5's figure would no longer be left; then the name still shows the file held | `LOCK_NOT_TAKEN_BUDGET`, `DEPLOY_LOCK_BUSY`, `LOCK_UNAVAILABLE`, `LOCK_FILE_REPLACED` |
| 14 | under the lock: no security reboot pending (`PIPE:655-658`) | `REBOOT_STATE_UNAVAILABLE`, `SECURITY_REBOOT_PENDING` |
| 15 | under the lock, first: the three directories that are held and that no creating call proves again are still reached by their names (the core's `Pinned.verify`: the signed chain walked again from `/`, the name looked at again in its parent): the release directory under its parent, the project directory under the deploy tree, the lock directory. Then, read again and compared with the first look: `.deploy-version`; the environment file and the compose file (signature and bytes); the release (signature and bytes); the worker (ID, start instant, restart count, still running) | `RELEASE_DIRECTORY_REPLACED`, `DEPLOY_TREE_REPLACED`, `LOCK_DIRECTORY_REPLACED`; `DEPLOY_VERSION_*`, `ENV_FILE_CHANGED_BEFORE_THE_LOCK`, `COMPOSE_FILE_CHANGED_BEFORE_THE_LOCK`, `RELEASE_CHANGED_BEFORE_THE_LOCK`, `WORKER_CHANGED_BEFORE_THE_LOCK` |
| 16 | under the lock: every container (`ps -a`), the baseline for "only the worker was recreated"; exactly one container carries the worker's name, the one inspected; NO container carries a temporary name of the worker's (`<anything>_<worker container>`: what an interrupted recreate of the service leaves, section 6) | `CONTAINER_LIST_INVALID`, `CONTAINER_LIST_INCONSISTENT`, `WORKER_SERVICE_LEFTOVER_CONTAINER` |
| 17 | under the lock: room on the filesystem of the live parent for a non-root writer: at least 1 MiB (the floor of install_release) and, where the filesystem counts inodes (`f_files` above 0), at least 8. Both figures go into the receipt (`precheck.free_bytes`, `precheck.free_inodes`) | `DATA_VOLUME_FREE_SPACE_BELOW_FLOOR`, `DATA_VOLUME_FREE_INODES_BELOW_FLOOR`, `STATVFS_INVALID` |
| 18 | the time: what section 5 needs must be left | `BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT` |
| any | the window or a clock; an OS error; anything else | `GO_EXPIRED`, `CLOCK_REVERSED`, `PRECHECK_OS_ERROR`, `PRECHECK_FAILED` |

**FIRST CREATION** — `phase_reached: EFFECTS`, still REFUSED: the `mkdir` itself failed and nothing was created
(`FILESYSTEM_READ_ONLY`, `FILESYSTEM_FULL`, `FILESYSTEM_ACCESS_DENIED`, `FILESYSTEM_ERROR`,
`DESTINATION_APPEARED_AFTER_PRECHECK`, `PARENT_REPLACED`, `GO_EXPIRED`). `mutating_calls` then says issued 1, failed 1.

A run is REFUSED only while no mutating call succeeded and none is uncertain (`state.clean()`); tested for every host call
failing in four ways (conformance) and for a death at every host call (section 6).

Three things each of these rows answers, that the first candidate left to a partial after the first creation:

- **A leftover of an interrupted recreate (row 16).** With a second container of the service present, `compose up`
  removes or replaces one of the two (scale 1), so the listing cannot stay as it was: the run would end
  `PARTIAL_WORKER_RECREATED_NOT_FULLY_VERIFIED` (`OTHER_CONTAINERS_CHANGED`) with the worker already replaced, or worse
  if compose stumbles over the name. Any earlier interrupted recreate leaves one: the capacity mount of Sunday (B4), a
  primary M3 that ended uncertain. It is knowable under the lock, so it is refused there. The test is by name
  (`endswith('_'+<worker container>)`), the only thing the listing of this family carries; a one-off container of the
  service (`…-run-<hash>`), a second replica or a container of another project does not match.
- **A project that changed between the first render and the lock (rows 6, 15).** The render is repeated only after E3
  (from the delivered file). What stands for it before E1: the render has exactly two inputs besides the build
  revision of the command, the compose file and the environment file (`c3po/compose.yml` at the release names no
  other file: `env_file: ../.env`, no `include`, no `extends`), and both are compared under the lock with what they
  were before the first render. A deploy that ends while this run waits for the lock is therefore a refusal with
  nothing changed (`COMPOSE_FILE_CHANGED_BEFORE_THE_LOCK`, `ENV_FILE_CHANGED_BEFORE_THE_LOCK` or
  `DEPLOY_VERSION_MISMATCH`). What remains for the render from the files to find after E3 is a change made WHILE this
  run holds the lock, by something that does not take it: the deploy job and the security controller do.
- **A directory swapped by name (row 15).** The data root belongs to the operational account: it can rename the
  release directory away and put another under the name. Every read through the descriptor held would still find the
  signed bytes while the path written into the worker's environment held others. The names are proved again under
  the lock (refusal), right before the recreate (objects-only partial) and after it (criterion). The live parent is
  proved again by every creating call of the core.

---

## 4. The effects, their readback, and what a partial says

After E1 nothing refuses. The steps, and where each stops:

1. E1 directory → must be `CREATED_DURABLE`.
2. E2 policy, E3 override → each must be `INSTALLED_DURABLE`; a failure before the final name exists withdraws the run's own temporary (core `files`).
3. Readback of both files by descriptor (same inode, one link, 0:0 0600, bytes equal; each readback first proves the directory and its pinned parent again), then of the directory (path from `/` leads to the descriptor held, 0:0 0700, exactly two entries).
4. Still under the lock: the lock file is still the one held; the render again, now from the delivered file (`E28:304`), judged like the first; its image reference equal to the first render's; then, as the last thing before E4, the release directory, the project directory (with the deploy tree) and the lock directory are still reached by their names (`RELEASE_DIRECTORY_REPLACED`, `DEPLOY_TREE_REPLACED`, `LOCK_DIRECTORY_REPLACED`: objects only, the worker untouched).
5. E4, started only if 30 s + 4 s are left (core rule 4.1).
6. Everything read after E4, each fact on its own (a failed read leaves its fact `null` and its code in `recreate.unavailable`; it never hides another):
   first reading of the worker by name → its environment (five names, booleans) → every container → the environment file →
   the compose file → the release → the two files and the directory again → the lock file → **a fixed pause of 3 s**
   (only if 3 + 2 s are left) → second reading of the same container by ID, which must still carry the worker's name →
   the worker's status file, if it exists (informational).
   Each file is read through the descriptor of its directory only after that directory is proved to be the one its path
   still shows; a directory that is not is the fact `false`, and its file is not read again.

**KNOWN_COMPLETE** (`ACTIVATE_WORKER_RECREATED_AND_VERIFIED`) needs every criterion (they are in the signed scope, `SUCCESS_CRITERIA`):

| Criterion | Code when it is false |
|---|---|
| the command returned 0 | `RECREATE_RETURNED_NONZERO` (or the runner's code: `COMMAND_TIMEOUT`, …) |
| exactly one container carries the worker's name, the one inspected | `WORKER_NOT_FOUND_AFTER_RECREATE` |
| it is not the container that was there before | `WORKER_NOT_RECREATED` |
| the old container exists under no name | `OLD_CONTAINER_STILL_PRESENT` |
| running, state `running` | `WORKER_NOT_RUNNING_AFTER_RECREATE` |
| restart count 0 | `WORKER_RESTARTED_AFTER_RECREATE` |
| on the signed image | `WORKER_IMAGE_CHANGED` |
| the four names and `C3PO_BUILD_SHA` present and equal, compared inside the template (no value printed) | `ENVIRONMENT_NOT_AS_SIGNED` |
| every other container listed with the ID and name it had under the lock; none appeared | `OTHER_CONTAINERS_CHANGED` |
| the environment file: the deploy tree still reached by its name; same signature, same bytes (hash kept in memory) | `ENV_FILE_CHANGED` |
| the compose file: the project directory still reached by its name; same signature, same bytes | `COMPOSE_FILE_CHANGED` |
| the release: its directory still reached by its name; the same object with the signed bytes | `RELEASE_CHANGED` |
| the two files and the directory as delivered | `FILES_NOT_AS_DELIVERED` |
| the lock file still the one held, in the lock directory still reached by its name | `LOCK_FILE_REPLACED` |
| the pause was taken | `SECOND_CHECK_NOT_APART` |
| second reading: same container, same start instant, running, restart count 0 | `WORKER_CHANGED_BETWEEN_THE_TWO_CHECKS` |
| (a criterion that could not be read) | `READBACK_UNAVAILABLE` |

Reported and not judged: the state of other containers (`others_states_unchanged`), the number of entries of the
directory after the recreate, the worker's status file (`worker_status: {present, status, readiness}`), and four counts
that say WHAT of the listing differs when `others_unchanged` is false, by name (names are unique in an engine):
`others_appeared` (a name that was not listed under the lock), `others_gone` (a name that no longer is),
`others_same_name_new_id` (a name with another ID: a container that was recreated) and `service_leftovers` (containers
under a temporary name of the worker's, section 6). All zero exactly when `others_unchanged` is true.

**`OTHER_CONTAINERS_CHANGED` is judged against `docker ps -a` over the 15 to 20 s of the run**, so a short-lived
container of anything else on the engine turns a correct activation into
`PARTIAL_WORKER_RECREATED_NOT_FULLY_VERIFIED`. The counts tell the two cases apart without another read:
`others_appeared` or `others_gone` 1 with `others_same_name_new_id` 0 and `service_leftovers` 0 is an unrelated
container that came or went; `others_same_name_new_id` above 0 is a service that was recreated; `service_leftovers`
above 0 is the recreate itself that did not finish. Known sources on this host, none of which is scheduled on
05:45–06:00 or 06:26–06:41 BRT: K11's own `hostops02-k11-<go16>` container of M2 (removed on exit, 30 s alarm); a legacy cron in the
repository (`work/chief-of-staff-cron` at dd4ec4bb: `CRON_TZ=America/Sao_Paulo`, `0 7,13,19 * * *`, `docker compose run
--rm morning-summary`), whose installation on the host is not established by any receipt; the nightly backup
(`ops/systemd/c3po-postgres-backup.timer`: 04:00 BRT, `Persistent=true`), whose upload runs EVERY night in a one-off
`compose run --rm … api` container (`scripts/c3po-postgres-backup.sh:110`) and whose failure notification runs in
another (`:43`): how long it takes on this host is in no receipt, so M0 (05:00) and M2 must show no one-off container
of the project; the supervisor unit (`docker run --rm`, 09:29 New York = 10:29 BRT on weekdays and boot + 30 s, only
after B11). For the runbook (no byte of this source):
M3 is dispatched only after M2's receipt is in hand and not within 60 s of it; M0 and M2 must show no
`hostops02-k11-*` container; 07:00, 13:00 and 19:00 BRT (and the duration of that job) join the minutes to avoid of
every operation that judges the container list; W1 or M0 reads whether that cron is installed. Open decision 19.
`LIVE_EPOCH_NOT_FOUND` is what the controller says while no epoch row exists (`APP/r2d2_v2_live_controller.py:208-210`);
it is expected, it is not a failure, and no status makes the run partial.

**KNOWN_PARTIAL**: three outcomes of a run that returned its own receipt, one of a run that escaped, one of a reduced receipt. `recreate.state`, `worker_container_replaced` and the ledger say which effects exist.

| outcome | `recreate.state` | Meaning | The worker |
|---|---|---|---|
| `PARTIAL_OBJECTS_LEFT_WORKER_NOT_RECREATED` | `NOT_STARTED` | The directory, and whatever files the ledger names, exist. The recreate command was never started (a file step failed; a readback failed; the render from the files failed or differed; the command could not be started; the budget no longer held it: `COMMAND_NOT_STARTED_BUDGET`) | untouched by this run: `worker_container_replaced: false` |
| same | `NOT_RECREATED` | The files exist. The command returned and a readback proved the worker is the same container (an unchanged listing of IDs and names), still running, with the same start instant and restart count (`RECREATE_FAILED_CONTAINER_UNCHANGED`, `RECREATE_RETURNED_ZERO_CONTAINER_UNCHANGED`). The call is settled as failed-nothing-changed | proved unchanged |
| `PARTIAL_WORKER_RECREATED_NOT_FULLY_VERIFIED` | `RECREATED_VERIFIED_ONCE` | A new worker container exists and every criterion held at the first reading; the second reading was not three seconds apart (no time left for the pause) or could not be made | replaced; activated as far as one reading shows |
| same | `RECREATED_NOT_VERIFIED` | A new worker container exists and at least one criterion is false or unread, or the command did not return although the container was replaced (`COMMAND_TIMEOUT`) | replaced: `worker_container_replaced: true`; `recreate.facts` says what holds |
| `PARTIAL_RECREATE_UNCERTAIN_REQUIRES_READBACK` | `UNCERTAIN` | The command was started; the worker is not known to be new (it is the old container but changed, or absent, or unreadable), or the command timed out before anything was seen to change. Never called "nothing changed" | `worker_container_replaced: null` |
| `PARTIAL_REQUIRES_RECONCILIATION` | — | The run escaped (`RUN_ESCAPED_STATE_UNKNOWN`): only `mutating_calls` is known. Section 6 | unknown |
| `RECEIPT_REDUCED_STATE_REQUIRES_READBACK` | as it was | the receipt did not fit 60000 bytes and was reduced; never complete | as it was |

Nothing is rolled back in any of them: the directory and the files stay (no source of this family removes them), so a
second run with the same `directory_name` refuses with `DESTINATION_PRESENT`.

---

## 5. The 60 seconds

Limits: payload 60 s from authenticated entry, dispatcher watchdog 80 s, transport 270 s. Classes of the core: a docker
read 8 s, a render 15 s, the recreate 30 s; an effect is not started unless its class + 4 s are left.

```
needed  = 30 (recreate class) + 4 (reserve after it) + render allowance + 1 (files) + 3 (pause)
render allowance = twice what the first render took, rounded up, at least 3 s, at most 15 s
kept while waiting for the lock = needed + 2 (the reads made again under it)
```

| Moment | Rule | If not |
|---|---|---|
| before the lock is asked for | more than `kept` must be left | `LOCK_NOT_TAKEN_BUDGET` — refusal, nothing changed, the lock not even asked for |
| while it is busy | waited for `min(signed seconds, left − kept)` | `DEPLOY_LOCK_BUSY` — refusal, nothing changed |
| after the reads under the lock, before E1 | at least `needed` must be left | `BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT` — refusal, nothing changed, lock released |
| when E4 starts | at least 34 s must be left (core) | `COMMAND_NOT_STARTED_BUDGET` — **partial**, objects only, worker untouched. Reached only when the render from the files took more than its allowance |
| before the pause | at least 5 s must be left | no pause; the second reading is made at once; `SECOND_CHECK_NOT_APART`, `RECREATED_VERIFIED_ONCE` |

In figures (tests/test_budget.py; emulated clock):

| Case | Result |
|---|---|
| reads 0.3 s each, renders 2 s, recreate 23 s | complete in 33.0 s; allowance 5, needed 43, kept 45; 56.8 s left when the lock is asked for |
| the same, recreate 30 s (its whole class) | complete in 40.0 s, pause taken |
| lock held throughout, nothing slow | refused after 17 s of wait (60 − 43), not the signed 20 |
| lock held throughout, Monday-like reads | refused after 11.5 s of wait (56.8 − 45) |
| five reads of 4 s before the lock | refused, `LOCK_NOT_TAKEN_BUDGET` (40 s left, 49 kept) |
| a GO with 20 s of its window left | refused, `LOCK_NOT_TAKEN_BUDGET` |
| first render 5 s, render from the files 9 s, recreate 23 s | complete (allowance 11) |
| render from the files 30 s after a first render of 0 s | partial, objects only, `COMMAND_NOT_STARTED_BUDGET` |

**The full 20 s of lock wait cannot be honoured** with the frozen 30 s class: 60 − 43 = 17 s is the ceiling, about 12 s
after a Monday-like precheck. The signed `wait_seconds` is an upper bound. At the planned minute (05:50 BRT; controller cycle at
HH:10–25, watchdog at HH:05 and HH:35) nobody is expected to hold the lock. Open decision 9.

With commands that take the same time each time they run, whatever that time and however long the lock is held, a run
either refuses with nothing changed or completes (144 combinations, `test_no_ordinary_slowness_makes_a_partial`).

**What the recreate alone should take.** The production worker is `python -m app.r2d2_worker` as PID 1 of its
container, with no SIGTERM handler, no init process and no `stop_grace_period` (`c3po/compose.yml:138-176` at dd4ec4bb;
no signal handler in `APP/r2d2_worker.py`: the only handlers of the tree are in the two `r2d2_v2_massive_*` modules). A
PID 1 without a handler is not stopped by SIGTERM, so the engine waits its whole stop timeout (10 s) and then kills.
The recreate is create, a 10 s stop, remove, rename, start: about 11 to 13 s, consistent with the 23 s of the whole
activation of 2026-09-28. The whole run is then about 20 to 25 s of the 60. An estimate, not a measurement: the Linux
job measures it on a worker stopped the same way (section 8, UA-5), and the receipt of Monday will carry it.
None of the checks added by the repair starts a command: they are file and directory calls.

The receipt carries the three durations nobody has measured on this host: `budget.first_render_milliseconds`,
`budget.render_from_the_files_milliseconds` and `recreate.milliseconds` (the recreate command alone), with what was left
at each decision (`budget.left_*`). A clock that fails makes a timing `null`; a timing never decides.

The pause: one `host.pause(3)`, the `time.sleep` of the lock part, between two readings. It is not a wait for a state (it
is taken once, for a constant time, whatever is read) and it is in the signed scope (`budget.settle_seconds`); CORE.md
rule 9 forbids sleeps other than the lock's, so it needs the co-auditor's reading. Open decision 7.

---

## 6. Crash points, and how a later read tells them apart

A process that dies writes no receipt: the transport files the run UNCERTAIN (or the last-resort handler of `run()` says
`RUN_ESCAPED_STATE_UNKNOWN`). What is on the host is then one of nine states, in this order, or, when the death falls
inside the recreate on a real engine, one of the in-between states further below; a later death never leaves an
earlier state (tested: the process is killed at each host call of a complete run in turn, 514 in the emulation, and the
host is then read with read primitives only, `tests/test_crash_points.py`; the emulated recreate is atomic, so the
in-between states are injected).

`go16` = first 16 hex of the GO hash; the two temporaries are `<directory>/.hostops-<go16>-0.partial` (policy) and `…-1.partial` (override).
These nine are the states of the FILES, with the worker either wholly old or wholly new. What the engine can leave in
between is below the table.

| State | Directory | Policy temp | Policy | Override temp | Override | Worker | Died |
|---|---|---|---|---|---|---|---|
| S0 nothing | absent | | | | | old, running, none of the four names | anywhere before the `mkdir` took effect |
| S1 | present, empty | absent | absent | absent | absent | old | after E1 |
| S2 | present | present | absent | absent | absent | old | while the policy is written |
| S3 | present | present | present (same inode: 2 links) | absent | absent | old | between link and removal |
| S4 | present | absent | present | absent | absent | old | after E2 |
| S5 | present | absent | present | present | absent | old | while the override is written |
| S6 | present | absent | present | present | present (2 links) | old | between link and removal |
| S7 | present | absent | present | absent | present | old, running, none of the four names, **and no other container of the service** | after E3, before the engine was asked for anything |
| S8 | present | absent | present | absent | present | **new**, running, the four names present and equal, the old one gone, **and no other container of the service** | after the engine finished the recreate |

**States a recreate interrupted INSIDE the engine leaves, between S7 and S8.** `compose up --force-recreate` of one
service is five calls to the engine, and compose has made them in two orders. Which one the compose plugin of this host
uses is NOT established: the source of compose could not be read offline, and no payload ever interrupted a recreate
on an engine (CORE.md U9; the Linux job now records the order of the runner's compose, section 8). Both are covered.
`<old12>` = the first 12 hex of the ID of the container being replaced.

| Order | Calls | What one container is called meanwhile |
|---|---|---|
| NEW FIRST (compose v2 as its `recreateContainer` is recalled today) | create the NEW container as `<old12>_<worker>` → stop the old one (here the whole 10 s) → remove it → rename the new one to `<worker>` → start it | the NEW container carries the temporary name |
| OLD FIRST (compose v1, early v2) | stop the old one → rename it to `<old12>_<worker>` → create the new one as `<worker>` → start it → remove the old one | the OLD container carries the temporary name |

| State | Under the worker's name | Under the temporary name | A running worker? | The run's own receipt |
|---|---|---|---|---|
| N1 new created, old untouched | OLD, running, none of the four names | new, `created` | **yes, the old one** | `UNCERTAIN`, `service_leftovers` 1 |
| N2 old stopped | OLD, exited | new, `created` | no | `UNCERTAIN`, `service_leftovers` 1 |
| N3 old removed | nothing | new, `created` | no | `UNCERTAIN`, `service_leftovers` 1 |
| N4 new renamed, not started | NEW, `created`, the four names | nothing | no | `RECREATED_NOT_VERIFIED` |
| O1 old stopped | OLD, exited | nothing | no | `UNCERTAIN` |
| O2 old renamed | nothing | OLD, exited | no | `UNCERTAIN`, `service_leftovers` 1 |
| O3 new created, not started | NEW, `created`, the four names | OLD, exited | no | `RECREATED_NOT_VERIFIED`, `service_leftovers` 1 |
| O4 new started, old not removed | NEW, running, the four names | OLD, exited | **yes, the new one** | `RECREATED_NOT_VERIFIED`, `old_container_gone` false, `service_leftovers` 1 |

With the order NEW FIRST, N1 lasts as long as the stop: about 10 of the 12 seconds of the recreate. **N1 is the state
the first candidate's rule took for S7**: the worker's name shows the old ID, running, with none of the four names.
Only the listing tells it apart. In six of the eight states no worker runs (the engine finishes a stop it has begun
even when the client is killed; whether it does is one of the things the Linux job records), and the compose worker is
also the V1 worker: open decision 17.

**The rule of a later read.** What it needs, and nothing more (all are rows of this family's tables and core helpers;
none prints a value): `probe` of the directory and of the four names in it; `docker ps -a`, the WHOLE listing;
`container inspect` of the ID under the worker's name (running, restart count, start instant); the boolean
environment template with the four signed names and values. From them:

1. S0 to S7 ("the worker is the old one, untouched") may be declared only when ALL hold: exactly one container carries
   the worker's name; it is the old ID, running, restart count as before, none of the four names present; **no
   container name ends with `_<worker>`** (the source's own `leftovers()`); and, where the IDs listed before the run are
   known (this run's receipt has only the worker's; a read of the same boot made before the dispatch, M0, has them
   all), **no ID appeared**.
2. S8 ("recreated and activated") only when: exactly one container carries the name; a new ID, running, restart
   count 0; the four names present and equal; no container name ends with `_<worker>`; the old ID is listed under no
   name.
3. Anything else is an in-between state of the table above, or something nobody foresaw. It is reported as it is and
   taken to the owner: never called S7, never called S8, and never answered by a second dispatch.

`tests/test_crash_points.py` holds the rule (`later_read`) and injects the eight states at the `compose up` call,
each ended by a timeout, by a non-zero return and by the death of the run: none is read as one of the nine states,
and the receipt of the run, when one exists, carries `service_leftovers`. A later request of this source on a host in
N1 is refused before any effect (`WORKER_SERVICE_LEFTOVER_CONTAINER`).

**What M3r is allowed to conclude.** M3r reads with the W1 bytes: the worker by name, running, restart count 0. That
alone cannot tell N1 from S7, nor a worker recreated by this run from one recreated by something else. M3r may say
"a container under the worker's name runs with restart count 0, twice". It may say "activate completed" only together
with a KNOWN_COMPLETE receipt of M3, and "activate did not happen, the worker is untouched" only together with a
receipt of M3 that says REFUSED, or `recreate.state` `NOT_STARTED` or `NOT_RECREATED`. After an UNCERTAIN, a lost
receipt or a death, M3r settles nothing: the read of the rule above does.

**Specification of the reconciliation read** (open decision 14; not built): a read-only source of this family, in the
same boot, that carries the rule above literally: the five probes, the whole `ps -a` judged with `leftovers()`, the
inspect and the boolean template, the old ID taken from the receipt of M3 (`precheck.worker.id`) or, without one, from
the listing of M0; its outcome one of S0…S8 or `IN_BETWEEN_STATE_REPORTED`, never a guess. K11 and M0 must show
"a container under a temporary name of the worker's exists" already on Sunday and at 05:00 on Monday, so that
a leftover is found with margin and not by the refusal of M3: open decision 18 (those are other operations' bytes).

A run that returned its receipt names the same state (`test_the_receipt_of_each_partial_names_the_same_state…`):
ledger rows `TEMPORARY_ONLY` = S2/S5, `LINKED_TEMPORARY_PRESENT` = S3/S6, `INSTALLED_DURABLE` ×1 = S4, ×2 with
`recreate.state` `NOT_STARTED`/`NOT_RECREATED` = S7, `RECREATED_VERIFIED` = S8, `RECREATED_VERIFIED_ONCE` or
`RECREATED_NOT_VERIFIED` = a new container under the worker's name (S8, N4, O3 or O4: `recreate.facts` says which),
`UNCERTAIN` = S7, S8 or one of N1, N2, N3, O1, O2: read.

---

## 7. What the in-run readback proves, and what only the host can prove

Proved inside the run, when the receipt is KNOWN_COMPLETE:

- the directory and the two files exist as signed (identity by descriptor, owner, mode, one link, bytes), before the recreate and again after it;
- the installed release had the signed bytes before the lock and under it, and its directory was reached by its name under the pinned parent under the lock, right before the recreate and after it; after the recreate it is still the same object with the same bytes;
- the render compose made from the two files gave the worker the four signed values, the epoch's build revision, the running image, and the data root bound at the signed target;
- one `compose up` returned 0; the container that carries the worker's name is a new one, on the signed image, running with restart count 0 at two readings three seconds apart with the same start instant; the old one is gone;
- its effective environment carries the four names and the build revision with the signed values (compared inside the docker template: only booleans reached this process);
- every other container has the ID and name it had under the lock; none appeared;
- `.env` and `<project>/compose.yml` are the same objects with the same bytes as before the first render was made, and their directories are still reached by their names; `.deploy-version` said the revision before and under the lock;
- the lock was held from before E1 to the last readback, and the lock file was the named one throughout.

Not proved by this run — a later read, or nothing in this family:

1. **That the worker stays up.** Two readings three seconds apart catch a container that dies at once. A worker that crashes after ten seconds of start-up (schema initialisation under the advisory lock, a bad capacity configuration) is seen by M3r (06:05 and 06:50), not here.
2. **What the application does with the pins.** No `docker exec`: nothing is asked of the application. The status file is read if it already exists (the controller may not have written it yet, four seconds after the start), and is reported, not judged. That the controller accepted the policy and the release (`LIVE_EPOCH_NOT_FOUND`, and not `LIVE_POLICY_*` or `LIVE_RELEASE_MISMATCH`) is for the P0 policy read.
3. **That nothing else of the worker's environment changed.** The recreate renders `.env` and `compose.yml` again: any change made to them since the worker was last created takes effect now. On 2026-09-28 the payload compared the whole environment before and after in memory (`E28:177-182, 339-340`); this family may not read an environment (CORE.md rule 6: a fixed template never names it). What stands in its place: `.deploy-version` and the worker's `C3PO_BUILD_SHA` are the epoch's revision; `.env` did not change during the run; M0 says nothing changed since Sunday. Open decision 6.
4. **That the release is a valid release.** Only its hash is compared. `Release.verify` is K10's and K11's.
5. **Durability across a power loss** beyond the fsyncs of the core's file part; that the engine persisted the new container.
6. **The intermediate states of an interrupted `compose up`** (section 6): told apart by the rule there, never by this run.
8. **Between the last proof of a name and the command.** The three directories are proved by name as the last thing before `compose up` is started; a swap in the instant between that proof and the moment compose opens its files is not excluded by anything a process can do. It is seen after the recreate (the criteria `RELEASE_CHANGED`, `COMPOSE_FILE_CHANGED`), in a receipt that is then not complete.
9. **A change of the project made while this run holds the lock by something that does not take it.** Before E1 only the two inputs of the render are compared, not the render itself; the render from the files finds it after E3, as an objects-only partial (section 3).
7. **Anything about a real engine**: section 8.

---

## 8. Command shapes: proven and UNPROVEN

Seven rows in the signed table. "Ran on the host" means: by an earlier payload, not by these bytes.

| Row | Argv after the trusted `/usr/bin/docker` | Ran on the host? |
|---|---|---|
| `container` | `container inspect --format <CONTAINER_FORMAT> <name or ID>` | yes: post-deploy readback rev4/rev5 (`disk_readonly.py:170, 201`), byte-identical template |
| `container_list` | `ps -a --no-trunc --format <PS_FORMAT>` | yes: `disk_readonly.py:263, 306` |
| `image` | `image inspect --format <IMAGE_FORMAT> <ID or reference>` | yes: hostops01's reviewed template |
| `container_environment` | `container inspect --format <presence-and-equality template> <ID>` | **UNPROVEN (UA-3)**: its constructs ran (post-deploy flags template); this composition, with five names, did not |
| `render` | `compose --project-name c3po --env-file <deploy>/.env -f <deploy>/c3po/compose.yml -f - config --format json`, override on standard input, `C3PO_BUILD_SHA` set | words: yes (`E28:223, 284`). Environment: **UNPROVEN (UA-1)** |
| `render_files` | the same with `-f <override file>` instead of `-f -` | words: yes (`E28:303-304`). Environment: UA-1 |
| `recreate` | `compose --project-name c3po --env-file … -f …/compose.yml -f <override file> up -d --no-deps --no-build --pull never --force-recreate r2d2-worker` | words: yes, word for word (`E28:223, 303, 323`; pinned by `test_static_the_command_words_are_the_ones_that_ran_on_2026_09_28`). Environment: UA-1. Duration alone: UA-5 |

UNPROVEN, each to be closed by the CI job (`linux_root/run.sh`, on a GitHub runner's engine: UA-1 to UA-6, UA-8, UA-9,
UA-11, UA-12; UA-7 and UA-10 are observed there, not closed) and, for the production host, by the Sunday dry run of K11 where
it uses the same core helper:

| # | What | Why it matters for the single shot |
|---|---|---|
| **UA-1** | `docker compose` started as root with the family's fixed environment: `PATH=/usr/bin:/bin`, `LANG=C`, `LC_ALL=C`, `C3PO_BUILD_SHA`, and **no `HOME`** (CORE.md U4). The run of 2026-09-28 inherited the environment of its process. **A partial precedent exists on this host**: the hourly security controller and its watchdog run `docker compose --env-file <deploy>/.env -f <deploy>/c3po/compose.yml ps -q …` through `subprocess.run` with the inherited environment of a system unit that has no `User=` (so no `HOME` under systemd 255) and `ProtectHome=true` (`ops/systemd/c3po-security-daily.service`, `c3po-security-watchdog.service`; `scripts/c3po_security_daily.py:39-43, 106-109` at dd4ec4bb; timers at HH:10 and at HH:05, HH:35). That exercises the discovery of the compose plugin, the start of the CLI, the load of the project from the same `.env` and `compose.yml` and the connection to the engine, all without `HOME` (the CLI falls back to the passwd entry for its configuration directory). The receipt that confirms the controller ran healthy in this boot is W1's `security_controller` section and M0. What stays unproven is narrower: `PATH=/usr/bin:/bin` exactly, `-f -`, `config --format json`, and `up` itself | for the two renders: if the compose plugin is found only through `$HOME/.docker/cli-plugins`, the first render fails: `COMMAND_FAILED`, a refusal before any effect — and the epoch does not start. K11 PRE on Sunday settles that on the host with the same helper. **For `up` nothing settles it before Monday**: K11 only renders. A `compose up` that fails without `HOME` after the two files exist is `RECREATE_FAILED_CONTAINER_UNCHANGED` or worse, on the one shot. The only proofs available are the CI job (a GitHub runner's compose version) and, on the host, the first `compose up` of any operation of this core (the capacity mount of Sunday, if it runs) or a rehearsal on a throwaway project under its own GO. **This is the largest open risk of this operation; it is the core's constant (`COMMAND_ENVIRONMENT`), not something this part can change.** |
| **UA-2** | what `config --format json` says of the worker's bind: `services.r2d2-worker.volumes[]` with `type`, `source`, `target`, optional `read_only` (the compose long form), and how it spells the source it takes from `.env`. No earlier payload read this member; 2026-09-28 read `docker inspect` `.Mounts` (`E28:163-175`), which this family cannot (a fixed template only) | a different shape is `RENDER_VOLUMES_INVALID` or `WORKER_MOUNT_NOT_AS_SIGNED`: a refusal before any effect. No precedent: **mark for the CI job and for K11 PRE**, whose candidate reads the same member and compares the source as printed (`data_volume_bind.bind_of_the_signed_source`): a `false` there with a source that differs only in spelling is still accepted here |
| **UA-3** | the environment template of the core (CORE.md U3) with five names: on the old container (four absent) and on the new one (five present and equal) | a template error is `COMMAND_FAILED` before any effect; after the recreate it is `READBACK_UNAVAILABLE`: a partial with the worker already replaced |
| **UA-4** | `flock(LOCK_EX|LOCK_NB)` on `deployment.lock` through an `O_RDONLY` descriptor, as root, against the pipeline's `flock -w 120` on a descriptor opened for appending (`PIPE:653-654`) (CORE.md U5) | Linux locks any open mode; never run on Linux by this family |
| **UA-5** | how long `compose up --force-recreate r2d2-worker` alone takes, against 30 s. Estimate: about 11 to 13 s (create, the engine's whole 10 s stop of a PID 1 that has no SIGTERM handler, remove, rename, start; section 5), the whole run about 20 to 25 s. The Linux job now stops its worker the same way and requires the recreate to have waited the whole stop timeout, so its `recreate.milliseconds` is a figure of the right kind. The 23 s of 2026-09-28 (`intent.json` 06:45:19 → `exit.json` 06:45:42) is the WHOLE activation: three `docker exec` in the worker (the third a collector cycle), two `psql` in the database container, three full inspects of every container, four image inspects, two renders, the recreate and the status wait (`E28:206-369`). The recreate itself includes the stop of the old container (up to the 10 s default grace if the worker does not handle SIGTERM) | a recreate that exceeds 30 s is killed with its process group and the run is `UNCERTAIN` or `RECREATED_NOT_VERIFIED` |
| **UA-6** | duration and size of `compose config --format json` on this host against 15 s and 1 MiB (CORE.md U6) | `COMMAND_TIMEOUT` / `COMMAND_OUTPUT_LIMIT` before any effect; a slow second render is the one budget partial of section 5 |
| **UA-7** | what the kill of the process group reaches when `compose up` times out, and what an interrupted recreate leaves (CORE.md U9) | section 6; K6a's own recreate was never interrupted on an engine. The Linux job OBSERVES it on a third service: a recreate started as the core's runner starts a command, its group killed after 3 s (inside the stop), the containers of that service listed during the stop, right after the kill and 12 s later. An exit 0 of the job says the look fell inside the stop and shows one of the two orders; it does not close this item |
| **UA-10** | which order the compose plugin OF THIS HOST makes the calls of a recreate in (section 6), and whether the engine finishes a stop whose client was killed | decides which in-between states can occur and for how long the old worker still runs. Not established for the host by anything: the Linux job shows it for the runner's compose version only. The later-read rule and the precheck hold for both orders |
| **UA-11** | what `compose up --force-recreate` does when two containers of the service exist (scale 1): removes one, replaces one, or fails on the name | no longer relied on: such a host is refused before any effect (`WORKER_SERVICE_LEFTOVER_CONTAINER`). The Linux job proves the refusal on a real engine with a container created under that name |
| **UA-12** | `fstatvfs` of the live parent as root on the data volume: `f_bavail`, `f_frsize`, `f_files`, `f_favail` | the same call ran on this host for the free-space figures of the earlier reads (hostfacts; K10 and K11 use the core's `free_bytes`). A filesystem that reports no inode count is judged by its bytes alone |
| **UA-8** | this operation's own host calls as real root on Linux: `open(name, O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_NOATIME, dir_fd=…)` of the release directory, the reads of `.env` and `.deploy-version` with `O_NONBLOCK|O_NOATIME`, `probe` below `/run` | real on macOS as an ordinary user (tests/test_native_calls.py); the kernel's `O_NOATIME` on a file root does not own (`.env`, uid 1000) is allowed for root only: on Linux as root in the CI job |
| **UA-9** | the worker's container name `<project>-r2d2-worker-1` and that `--force-recreate` leaves exactly one container of that name and removes the old one | observed name: hostfacts; the recreate of 2026-09-28 checked the same by name (`E28:324-335`) |

Not unproven, but an assumption a receipt should confirm before the signature: the live parent and the release parent are
in the data root and the worker binds the data root read-write at `/app/day-d-data`; a directory created by root in that
parent is root:root with group 0 (no setgid, no group inheritance) — the same note as CORE.md section 11 for K10.

---

## 9. What of 2026-09-28 is not ported, and why

| 2026-09-28 (`E28`) | Here |
|---|---|
| request carried a container baseline and a capacity observation at most 900 s old (`:75-85, 238-258`) | nothing that exists only on Monday is in the signed bytes: the worker is read at run time and compared with itself under the lock; the plan signs the image ID, not container IDs |
| `docker exec` in the worker: controller hash, package hash, `Release.verify` (`:213-216, 270-274`) | no `docker exec`. The release is compared by hash; the image by ID and revision label; `Release.verify` in a fresh container is K10/K11 |
| `docker exec` in the database: V1 paused, open positions, the epoch row (`:218-221, 348-353`) | not done: no epoch row exists yet, and a database read is another operation (DBR) |
| one collector cycle by `docker exec` after the recreate (`:345-347`) | not done: the capacity-mount README forbids starting a V2 worker with `docker exec`; the reader does it |
| wait up to 120 s for `SUBSCRIPTION_REQUESTED` (`:354-369`) | not done: the 60 s budget, and without an epoch row the controller answers `LIVE_EPOCH_NOT_FOUND`. The status file is read once, if present, and reported |
| whole environment compared before and after, in memory (`:177-182, 339-340`) | section 7 item 3 |
| `.env` hashed, the hash printed in the receipt (`:210, 331, 376`) | hashed in memory, compared, never printed (rule 6) |
| `docker inspect` of every container, whole JSON (`:35-37`) | `ps -a` and two fixed templates; nothing of an environment is printed |
| `recreate.started.json`, `baseline.after-recreation.json`, `activate.receipt.json` written next to the policy (`:318-322, 373-377`) | no marker files: the receipt and the ledger say it, and section 6 tells the states apart without them. Fewer effects, fewer crash points |
| refuses when `/etc/c3po/security-maintenance.hold` exists (`:201`) | not checked (open decision 5); the maintenance pin and the reboot marker are |
| disk reserve of 40 GiB on the data volume (`:259`) | a floor, not a reserve: 1 MiB and 8 inodes for a non-root writer on the filesystem of the live parent, under the lock, before the first creation (the floor of install_release). The operational reserve of the data volume is M2's signed `data_volume_free_bytes`, minutes earlier |
| no lock | the deployment lock, as the deploy job takes it (`PIPE:653-654`), and the reboot marker under it (`PIPE:655-658`) |
| override named `compose.proof.json` | the name is signed (`override_name`) |

---

## 10. Open decisions

For the owner (O) or the co-auditor (C). None but the first is settled by this build.

1. (C) **Evidence.** CLOSED by the repair: `EVIDENCE_OPERATIONS=('GO_READONLY_HOSTOPS02_EPOCH_READBACK_01',)`. The request must cite a receipt of K11. What remains for the co-auditor: that the bound request cites the K11 PRE receipt the rows were actually copied from (the code cannot read a receipt), and the coupling: if K11's operation name changes before the signature, this constant follows and the payload hash moves.
2. (O, C) **Which receipts let the epoch start.** KNOWN_COMPLETE does. `PARTIAL_WORKER_RECREATED_NOT_FULLY_VERIFIED` with `RECREATED_VERIFIED_ONCE` means the worker is activated and was read once; with M3r clean, is that "activate completed" in the sense of the order? As built, nothing but KNOWN_COMPLETE claims it.
3. (O) **The spare (M3′).** After any partial the directory exists, so a second request with the same `directory_name` refuses. If the spare may be used after `PARTIAL_OBJECTS_LEFT_WORKER_NOT_RECREATED` (worker untouched), it must be bound with another `directory_name`; the plan's rule is "only if the primary was never dispatched".
4. (C) **Where the override lives.** In the data volume, next to the policy, as on 2026-09-28: the worker (root in its container, read-write bind) can write that directory. Every later compose command of any operation must use the same file list and should compare the override with the hash in this receipt first.
5. (O, C) **The hold file** (`/etc/c3po/security-maintenance.hold`): 2026-09-28 refused when it existed; this source does not look. M0 reads it.
6. (C) **The rest of the environment** (section 7 item 3). K11's candidate renders the project with and without the override on Sunday and reports whether the override changes anything but the four names (in memory, a boolean): that covers what the override adds, not a drift of `.env` since the worker was created. A comparison by compose's own configuration hash (`config --hash` against the container's `com.docker.compose.config-hash` label) would close that without printing a value; it is a shape that never ran anywhere and was not built.
7. (C) **The 3 s pause** against CORE.md rule 9.
8. (C) **The policy checks from the bytes**, in particular the two instants `2026-10-05T13:30:00Z` and `2026-10-09T20:00:00Z` (not computed with the calendar library here) and UTC-only instants.
9. (O) **Lock wait**: at most 17 s, about 12 s in practice, not 20 (section 5).
10. (C) **`ACTIVATION_ALLOWED=False`** for this operation (family rule as written).
11. (C) **Other containers' states** are reported, not judged; IDs and names are judged.
12. (C) **The worker's status** is reported, not judged; a status such as `LIVE_POLICY_HASH_MISMATCH` in a complete receipt is a finding for the owner.
13. (O) **The settle of `M3r`**: the two later reads remain necessary (section 7 item 1).
14. (C) **The reconciliation read** of section 6 is not built. Its rule and its specification are now written there, for both orders of a recreate; until it exists the rule is applied by hand from W1-family reads, and M3r may conclude only what section 6 allows.
15. (C) **Coupling with K10**: this source expects the release at `<pinned parent>/<directory>/<file>` inside the data root, the directory root:root 0700 on the parent's device, the file root:root 0600 with one link. K10's candidate, as read on 2026-10-02, installs exactly that (`create_directory` 0700 and `create_file` 0600 of the core, at `<data volume>/r2d2-v2-release-20261005/release.CERTIFIED.json`, at most 32768 bytes); if it changes, the plan members follow, and the two expectations of mode and owner are constants of this source.
16. (O, C) **A deploy after the activation** renders without the override and removes the four names from the worker (`PIPE:746` names one file). The order forbids a deploy during the epoch; nothing in this source can prevent one.
17. (O) **No way back is built.** Nothing is repaired or rolled back. If the recreate leaves no running worker (`UNCERTAIN`, or a new container that does not run), bringing a worker back is another write under its own GO; the engine's `restart: unless-stopped` restarts a container that exits, not one that was never started. The compose worker is also the V1 worker.
18. (C) **K11 and M0 must say whether a container under a temporary name of the worker's exists** (`<anything>_c3po-r2d2-worker-1`): Sunday's dry run and Monday's 05:00 snapshot then show a leftover of the capacity mount (B4 runs AFTER K11 PRE, with the same 30 s kill) with margin, instead of M3 refusing on it. Those are other operations' bytes; nothing here changes them. As read on 2026-10-02: K11's candidate, in repair the same day, reports `containers.worker_service_leftovers` with the same test by name and raises the finding `WORKER_SERVICE_LEFTOVER_CONTAINER`; the first candidate of K11 reported counts by state and `worker_listed` only. The W1 bytes (M0, M3r) count the containers of each service of the project by compose label: a `count` of `r2d2-worker` other than 1 is a leftover of either order. To confirm against the bytes that are finally signed; B4's own receipt and a read AFTER B4 are what covers Sunday afternoon.
19. (O, C) **The legacy cron** (`work/chief-of-staff-cron`: 07:00, 13:00, 19:00 BRT, `docker compose run --rm`): whether it is installed on the host is in no receipt. If it is, its minutes join the minutes to avoid of every operation that judges the container list (section 4).
20. (O, C) **A refusal that did not exist in the first candidate** can now end the epoch: a leftover container of the service, less than 1 MiB or 8 inodes on the data volume, a compose file that is not a regular file in a real directory, a directory swapped by name. Each is knowable before Monday: K11 PRE reports the compose inputs as regular files and the free space; open decision 18 covers the leftover.

---

## 11. How it was tested

Counts, interpreter versions and the state of the mutation records are in `VALIDATION.json` (written by `validate.py` from
what the commands printed). What the suite holds:

| File | What |
|---|---|
| `tests/test_conformance.py` | the 121 tests of the core's conformance suite on this operation: authentication, windows, date class at both layers, envelope, dispatcher, launcher, transport, the unbound payload under `python3 -I -B -`, every host call failing once in four ways |
| `tests/test_activate.py` | the complete run: the literal effects, what is on the host afterwards, the order of everything that changes it, the exact argv, standard input and variables of the thirteen commands, no value of an environment anywhere, the worker's status file |
| `tests/test_plan.py` | every refusal from the bytes, one case per code and per way of reaching it; effects binding for every signed member |
| `tests/test_precheck.py` | hostile filesystem states (links, owners, modes, devices, an object in the way, foreign content, a fifo), a worker, image or project that is not as signed, hostile answers of the docker CLI, what changes between the first look and the lock (the compose file, a deploy that changed the project, each held directory swapped by name), a container under a temporary name of the worker's, a data volume without room, an executor that is not root (nothing is called, not even the umask): each REFUSED with nothing changed |
| `tests/test_effects.py` | every failure after the precheck: the first creation, the directory, each step of each file (every fsync of it), the render from the files, a held directory swapped by name right before the recreate, the recreate refused, failed, timed out before and after its effect, each criterion broken alone, the counts of what changed among the other containers, a second reading of a container that no longer carries the worker's name, unreadable readbacks, the window ending mid-run, process death |
| `tests/test_budget.py` | the 60 seconds in figures (section 5) |
| `tests/test_crash_points.py` | death at every host call of a complete run; the nine states; what a later read sees; the eight in-between states of a recreate interrupted inside the engine, in both orders, each ended three ways: none is read as one of the nine; a later request on a host in the first of them is refused |
| `tests/test_native_calls.py` | the source's own unmodified Native on a real temporary tree (real `mkdir`, `open`, `link`, `unlink`, `fsync`, `flock`, sleep; real links, fifos and hard links), with the docker CLI alone emulated |
| `tests/test_linux_root.py` | the Linux job's scripts parse, refuse outside a throwaway runner, and are coherent with the source on the emulation; how the job reads the order of an interrupted recreate from the rows of a service |
| `tests/test_static_sources.py` | the names, constants and command words against the release tree at dd4ec4bb and the payload of 2026-09-28 (skipped without their locations); the assembler's digest of a policy; that the compose file names no other file than the environment file; that the production worker has no SIGTERM handler, no init and no `stop_grace_period`, as the Linux job models it; that `EVIDENCE_OPERATIONS` is the operation name in K11's own source when it lies beside this directory |

Mutation (`mutation/mutants.py`): one mutant per operand of every `need()` of the operation's part (generated from its
syntax tree: no refusal can be added without its mutants), and by hand one per member of `effects_of()`, per constant, per
row of the command table, per criterion, per settlement of the recreate call, per outcome, per budget term. An interrupted first
trial showed 22 survivors among its first 94 mutants, the first complete trial 33, the next 2: each was either a check that
a second check implies (removed from the code) or was answered by a test. The list of the first candidate had zero
survivors on both interpreters. It was then shown to be incomplete, as the core's history said it would be: the purity
review ran 70 mutants of its own and four survived on both interpreters (a file left installed and not durable
accepted; the second reading made without the worker's name; the release directory held without its name under the
parent; the executor checked after the umask). Each is now a row of this list with a test that kills it, and the repair
added one row per guard it introduced. The counts of the repaired list are in `VALIDATION.json`: zero survivors on
both interpreters, no kill by the time limit. This says the tests answer THIS list, and nothing more.

The reviewers' own tools were run again against the repaired build, from a work directory outside this one. Of the
purity review's 70 mutants 64 still apply (six anchors moved with the repair; each has a row of the same meaning in
this list) and all 64 are killed on both interpreters. Its sweep (every host call of a complete run failing once in
seven ways: 514 calls, 3,598 runs per interpreter) was run with the digest of the compose file added to what must not
appear: no value, no byte and no digest of the environment file or of the compose file in any receipt, no refusal that
changed anything, no receipt that says the worker untouched when it was replaced. Its one remaining observation is a
defect of the core, in section 12. The host review's two experiments now stop where they said the first candidate was
wrong: state N1 is no longer read as S7, and a host with a leftover is refused.

`MUTATION_INHERITED.json` runs the rows of the core's own list that apply to this build against this operation's suite,
for information: a survivor there is a guarantee of the core that this operation's tests do not exercise (the files part's
internals, the real-process runner, helpers this operation never calls), and the core's own record kills it. One row of
the core's list does not do what its name says in any built source: `R36_effect_that_returned_settled_as_done_without_a_readback`
has an anchor that ends in a blank line, which `effect()` no longer has once the runner part stands between its marker
lines, so the replacement lands in `container_run` of the docker part (a `NameError` there). The mutation it names, applied
by hand to `effect()` in this build, is killed by this suite (the counts of mutating calls).

Not tested anywhere: a real docker engine, compose, Linux, uid 0 (section 8).

---

## 12. What changed after the two reviews (2026-10-02)

Twelve findings, each verified by command before anything was changed (the reviewers' own scripts were run against the
first candidate and against this one). All twelve were accepted. The frozen core was not touched. The first candidate
is kept beside this directory as `activate.pre-repair-<first 8 hex of its SHA256SUMS>`.

| # | Finding | Severity | What changed | Payload bytes |
|---|---|---|---|---|
| 1 | The crash-point table and the later-read rule assumed the old order of a compose recreate; with the order compose v2 uses today the first in-between state (old worker running, new one `created` under `<old12>_<worker>`) was read as S7 | MAJOR | section 6 rewritten for both orders, eight in-between states, the rule of a later read, what M3r may conclude, the specification of the reconciliation read; `tests/test_crash_points.py` injects all eight, three endings each; the receipt now carries `service_leftovers` | yes (a count in `recreate.facts`) |
| 2 | A leftover container of the service under a temporary name was not refused: the run would have ended PARTIAL after replacing the worker | MAJOR | precheck 16: `WORKER_SERVICE_LEFTOVER_CONTAINER`, before any effect; tests for five leftovers, for five names that only resemble the worker's, and for a later request on a host in state N1 | yes |
| 3 | The CI project stopped its worker in 1 s and no shape interrupted a recreate | MINOR | `linux_root/shapes.py`: the worker and a third service are stopped as the production worker is; the recreate must have waited the engine's whole stop timeout; a shape creates a container under the temporary name and expects the refusal; a shape interrupts a recreate of the third service inside the stop and records the order. `WORKFLOW.steps.txt` no longer says an exit 0 closes UA-7 | no |
| 4 | `OTHER_CONTAINERS_CHANGED` did not say what changed | MINOR | `others_appeared`, `others_gone`, `others_same_name_new_id` in `recreate.facts`; the known sources and the runbook rules in section 4 | yes (counts) |
| 5 | No free-space floor before E1 | MINOR | precheck 17: 1 MiB and, where inodes are counted, 8, on the filesystem of the live parent | yes |
| 6 | UA-1 "no precedent" and UA-5 "open" were less precise than the repository allows | MINOR | section 8: the security controller as partial precedent; the 11 to 13 s estimate and its basis in sections 5 and 8 | no |
| 7 | The release directory, the deploy tree and the lock directory were held and never proved again by path: a release directory swapped by name gave KNOWN_COMPLETE over other bytes | MINOR | the three are proved by name under the lock (refusal), right before the recreate (objects-only partial) and after it; the release is read again after the recreate (`RELEASE_CHANGED`) | yes |
| 8 | A project changed between the first render and the lock was found only after E3 | MINOR | the compose file is held like the environment file: signature and hash before the first render, compared under the lock (`COMPOSE_FILE_CHANGED_BEFORE_THE_LOCK`) and after the recreate (`COMPOSE_FILE_CHANGED`) | yes |
| 9 | The signed scope statement said "No value of any environment is printed or stored" | MINOR | reworded to what the code guarantees: no value READ from a container, the render or the environment file; the four signed values and the build revision are named as carried. `CONTRACT.txt` section 5 follows | yes (`SCOPE_STATEMENT`, `SCOPE_SHA256`) |
| 10 | Any operation name satisfied the evidence | MINOR | `EVIDENCE_OPERATIONS` names K11 | yes |
| 11 | Four of the reviewer's 70 mutants survived | MINOR | four tests and four rows (`Q21`, `R42`, `H48`, `P33`); `H48` is killed by the tests of finding 7 | no |
| 12 | The policy digest in the effects was not the assembler's for a text that is not ASCII | MINOR | `policy_digest()`: `ensure_ascii=False`, as `APP/r2d2_v2_epoch_assembler.py:24-28`; a text that cannot be encoded is refused from the bytes | yes |

What the repair did NOT do, and why:

- **It did not repeat the render under the lock before E1.** That would have closed the last case of finding 8 (a
  change under the lock by something that does not take it) at the price of a third `compose config` in the budget
  (the lock wait would fall from 17 s to about 14 s) and of another command that can time out before any effect. The
  two inputs of the render are compared instead.
- **It did not change K11, the W1 bytes or the plan.** What they should report (open decisions 18 and 19) and what the
  runbook should say (section 4) is written here for the binder and the co-auditor.
- **It did not look at the compose source.** The order of a recreate on this host stays unproven (UA-10); both orders
  are handled.

A defect of the frozen core, found by the purity reviewer's sweep and present in the first candidate as well; reported,
not repaired here (the core is sealed): in `create_directory` (`core/parts/files.py`) the descriptor of the directory
just created is opened and then handed to `Pinned(...)`, whose constructor makes an `fstat`. If that one call fails,
the descriptor is in no table and nobody closes it: the run ends with one directory descriptor open (seven of the
3,598 runs of the sweep, all at that call). Nothing on the host is affected: the receipt is right
(`CREATED_STAT_FAILED`, an objects-only partial, the lock released) and the kernel closes the descriptor when the
process ends, a moment later. The statement "no descriptor is left" of the tests holds for every other path.

Observed while verifying, outside the twelve findings and not changed: the start instant of the worker printed by
`docker inspect` goes into the receipt as it is (`precheck.worker.started_at`, at most 64 characters, the core's
bound); a hostile engine could put any text of that length there. It is not an environment value and not a secret of
the host; a stricter grammar belongs to the core's `container_facts`.
