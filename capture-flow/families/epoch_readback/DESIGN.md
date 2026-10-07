# K11 — epoch readback (HOSTOPS02), modes PRE and POST: design

Offline work only. Nothing here was run on the host, pushed or bound. Every hash is taken by command (SHA256SUMS).
Built on the frozen core generation `4c24c5cf…d0d6` (seal `c13ce685…2f9f`); the core was not edited.

**Revision 2, 02/10 evening: repaired after two reviews (host fidelity and purity).** The bytes before the repair are kept, sealed, in `../epoch_readback.pre-repair-7c698e72` (the first eight hex of its SHA256SUMS). What changed and why: section 13. The reviewers' own files (`review-host/`, `review-purity/`) speak of those earlier bytes; they are left where they were written and are not part of this seal.

Abbreviations. `W` = `/Users/eduardocastro/Documents/Codex/2026-09-04/va/work`. `E28` = `W/r2d2-plan-b-baseline-20260927/rescue-s2-rev-s/night-activation-review-rev1/worker-live-control.bound.py` (the activation of 28/09). `RI` = `W/r2d2-certified-successor-20260923-activation-rev12b/operations/release-install.py`. `PD5` = `W/postdeploy01-rev5-fable-20261002/candidate-F2/disk_readonly.py` (ran on the host on 02/10). `REL:<path>:<line>` = `git show dd4ec4bb:<path>`. `SUP` = `REL:c3po/deployment/massive-supervisor/README.md`. `PIPE` = `REL:.github/workflows/c3po-pipeline.yml`. `APP` = `REL:c3po/backend/app/`. `H01` = the sealed hostops01 candidate, `parts/op_readback.py`. `CORE` = `hostops02/core/CORE.md`.

---

## 1. What it is

One reading source (`WRITES_ALLOWED=False`, `ACTIVATION_ALLOWED=False`, date class `READ`, gate at most 3600 s), two signed modes, and for PRE a signed profile:

| | PRE (M2p, Sunday dry run) | POST (M2, Monday, after install_release) |
|---|---|---|
| Release | the bytes carried in the signed request, on standard input of the container | the installed file, read on the host and, in the container, through one read-only bind of its directory |
| Place of the release on the host | must still be empty (`RELEASE_TARGET_ALREADY_EXISTS` otherwise) | must be what install_release leaves: directory 0:0 0700 with the signed number of entries, file 0:0 0600, one link, bytes equal to the signed hash |
| Place of activate's directory (`live`) | FULL: required. Its parent is walked against the signed rows and held; the name must not exist (`LIVE_DIRECTORY_ALREADY_EXISTS`) | the signers' choice; the same check when signed (activate is still to come) |
| Compose render with the override | required | the signers' choice (`render` may be null) |
| Policy candidate | FULL: required | required |
| Binds of the container | FULL: one existing private directory, read-only (`bind_probe`: the rehearsal of POST's bind, section 3). REDUCED: that, or none | the installed release directory, read-only |
| Limits (`limits`) | FULL: required: milliseconds of a render and of a quick docker read, free bytes and free inodes of the filesystems the writes create in | the signers' choice |
| `docker_config` | REDUCED only | never |
| Success outcome (exit 0) | FULL: `EPOCH_DRY_RUN_PRE_ALL_OBSERVED_ALL_EXPECTATIONS_MET`. REDUCED: `EPOCH_DRY_RUN_PRE_REDUCED_PROFILE_ALL_OBSERVED_ALL_EXPECTATIONS_MET` | `EPOCH_READBACK_POST_ALL_OBSERVED_ALL_EXPECTATIONS_MET` |
| `gates_first_session_readback` | always false | true only with the success outcome |

**The full dry run is the rehearsal of Monday.** `dry_run: "FULL"` is refused from the bytes, before any claim, unless the request signs everything Monday's three runs will meet: the policy, the probe of the bind, the live directory, the limits, the worker's environment, no `docker_config`; the places install_release uses by constant (`/mnt/day-d-data`, `r2d2-v2-release-20261005/release.CERTIFIED.json`, seen in the worker below `/app/day-d-data`); the layout activate derives (`<tree>/.env`, `<tree>/<project>/compose.yml`, `.deploy-version`, `runtime/security/deployment.lock`, container `<project>-r2d2-worker-1`); and an override that is byte for byte the file activate writes. Only the FULL outcome may be read as "M1 and M3 can stand". A request that leaves anything out must say `REDUCED`; it then succeeds under another outcome name, its effects say `rehearses_install_release_and_activate: false`, and a GO for the full outcome is refused (`GO_CRITERION`).

**What the two writes refuse on is a finding here.** install_release and activate are single-shot for the epoch and refuse, before any effect, on a number of host states. Each of those states is a finding of this source, with the predicate of the write itself (section 4b). A dry run that ends KNOWN_COMPLETE in a state on which Monday's write would refuse would be worse than no dry run.

Everything else is the same code in both modes and is driven by the signed plan: what the plan leaves out (`render` and `live` in POST, `limits`, `units`, `journal`, the lock, and in a reduced dry run `policy`, `bind_probe`, `live`, the worker's environment) is not observed, no command is started for it, and the receipt lists it under `items_omitted_by_the_plan`.

`KNOWN_COMPLETE` is reachable before and after provisioning: no item requires anything of the supervisor to exist. A unit that is not installed is `LoadState=not-found` (a fact); a journal root that does not exist is `exists:false` (a fact, a finding only when the request signs a floor).

## 2. What it does on the host, in order

There is no write. "Effects" of this source are its side effects (section 2.2). Order of the observations (each is one item of the receipt, observed on its own):

| # | Item | How | Commands |
|---|---|---|---|
| 0 | executor | `host.identity()==(0,0)`, before anything is looked at | — |
| 1 | `boot` | `/proc/sys/kernel/random/boot_id` hashed and compared with the evidence's | — |
| 2 | `directory:RELEASE_PARENT`, `directory:DEPLOY_TREE`, `directory:LOCK_DIRECTORY`, and `directory:LIVE_PARENT`, `directory:BIND_PROBE` when signed | walked from `/` by `dir_fd`, `O_NOFOLLOW|O_NOATIME`, against the signed rows (`walk_pinned`) or, when the request signs no rows, recorded (`descend`); each is held (`Pinned`) to the end. The release parent and the live parent receive an entry of a write: their observed rows are judged as that write judges its signed rows (no setgid; for the release parent, the data volume a mount point), and rows the write still to come would refuse are a finding. With signed limits, the free bytes and (where the filesystem counts them) the free inodes of each of those two directories' filesystems are compared with the signed floors | — |
| 3 | `release_target` | PRE: one `lstat` of the directory name in the held parent. POST: directory opened by `dir_fd` without following a link, metadata, entry count, the file by `lstat` then `read_regular` (at most 65,536 bytes), bytes compared with the signed hash and size; the directory is held for the bind | — |
| 3b | `live_target` (if signed) | the live parent proved again, then one `lstat` of the signed name in it: nothing may stand where activate will create | — |
| 4 | `docker_config` (if signed) | walked, must be 0:0 0700 and empty; counted | — |
| 5 | **`verify`** | the one container (section 3). **First command of the run**: a `CONTAINER` row is not started with less than its class time + 4 s left (44 s) | `docker run` (class `RUN`, 40 s) |
| 6 | `containers` | `docker ps -a`: counts by state, whether the worker is listed, whether a container named as this run's is still there, how many containers carry a temporary name of the worker (`<hex>_<worker container>`, left by an interrupted recreate: a finding); `command_ms` | `QUICK` |
| 7 | `image` | the signed reference resolves to the signed ID; revision label equals the signed revision; `command_ms` | `QUICK` |
| 8 | `worker` | the worker container: image ID equal to the signed one, running; restart count and health reported; `command_ms` | `QUICK` |
| 9 | `worker_environment` (if signed) | booleans only: `C3PO_BUILD_SHA` equal to the revision, and none of the four live names present, with or without a value (both gated); `command_ms` | `QUICK` |
| 10 | `render` (if signed) | two renders kept in memory: the signed files alone, and the same with the signed override on standard input as `-f -`; compared (section 4); the bind of the data volume judged by activate's rule; `base_ms`, `override_ms` | 2 × `RENDER` (15 s) |
| 11 | `deploy_files` | `.deploy-version` read (at most 128 bytes) and compared with the revision as activate compares it (surrounding white space aside); the environment file and each compose file by `lstat` (type, owner, mode, links; never content or size) | — |
| 12 | `maintenance_pin` | `lstat` of `<data volume>/.r2d2-v2-pinned`: a regular file; in PRE also root:root, as install_release requires | — |
| 13 | `unit:<name>` (each signed unit) | `systemctl show <unit> -p …` (ten properties); compared only with a signed expectation | `QUICK` each |
| 14 | `journal` (if signed) | the journal root: `fstatvfs` on the root itself (`f_bavail*f_frsize`), entry count, presence of the two catalog names by `lstat` | — |
| 15 | `lock` (if signed) | the lock file opened read-only without following a link in the held directory; a shared non-blocking `flock`, released at once: `FREE` or `BUSY` | — |
| 16 | `reboot_pending`, `reboot_required` | `lstat` of `/run/c3po-security/reboot.pending` (a finding when present) and `/run/reboot-required` (reported) | — |
| 17 | `docker_config_after` (if signed) | the directory counted again | — |
| 18 | `directories_stable` | every held directory proved again from `/` | — |

### 2.1 Why the container is first

Core rule 4.1: a `CONTAINER` command is not started unless `gate() >= class + 4 s`. With class `RUN` that is 44 of the 60 seconds. Items 0–4 (3b included) make no command (system calls only, milliseconds), so the container always has its whole class time. Every other command is a `READ` and runs with whatever is left.

### 2.2 Side effects (all declared in the signed scope)

1. One attached `docker run --rm`: the engine creates a container named `hostops02-k11-<first 16 hex of the GO hash>` and removes it when its process ends.
2. A shared, non-blocking `flock` on the deployment lock, released at once. For that instant a non-blocking exclusive request of another process fails; the pipeline's `flock -w 120` (PIPE:654) waits and is not affected.
3. `docker compose config` reads the environment file; its values stay in memory.
4. The values compared with the worker's environment (the revision, two container paths, two hashes) travel in the argv of the docker CLI. None is a secret.
5. `systemctl show` of a unit the manager has not loaded makes the manager load it from disk (H01 said the same of its own `show`).
6. With a signed `docker_config` (a reduced dry run only: activate never sets it), every docker command runs with `DOCKER_CONFIG` set to that directory; it is counted before and after.
7. The Docker CLI executes its plugin binaries to answer `compose`.

## 3. The container (`verify`)

**Argv** (row `verify`, kind `CONTAINER`, class `RUN`):

```
docker run --rm -i --pull never --init --user 0:0 --network none --read-only --cap-drop ALL --security-opt no-new-privileges
  --name hostops02-k11-<go16>
  [--mount type=bind,source=<release parent>/<directory>,target=/c3po-…,readonly]      POST
  [--mount type=bind,source=<signed existing directory>,target=/c3po-…,readonly]       PRE, only with a signed bind_probe
  <signed image ID> python -I -B -
```

- The prefix is the core's `RUN_PREFIX`, which is the catalog argv of SUP:336-339 option for option. No network, read-only root, no capability, image by ID, never a pull. A `CONTAINER` row refuses a bind that is not read-only (core, `MOUNT_NOT_READ_ONLY`).
- `python -I -B -` reads the program from standard input (SUP:345). Standard input is one line `SIGNED_CONTEXT=<literal>` followed by the pinned snippet: the framing PD5:439-442 used on this host (there through `docker exec … /usr/local/bin/python3 -I -B -`).
- The bind target is a single new component below `/` (grammar `/c3po-[a-z0-9][a-z0-9-]{0,40}`), the shape SUP:46 prescribes for the journal; the bind source is a directory this run opened by descriptor, holds, and proves again before and after the run.
- `--name` is this operation's addition to the README argv: it lets the run say exactly whether its own container is still listed afterwards.

**The snippet** (`VERIFY_SNIPPET` in `op.py`, sha256 in the signed scope and in the effects; 67 lines, 4,073 bytes). In order:

1. `signal.alarm(30)` as its first statement, before any import of the application. Python is not PID 1 (`--init`), so the default action applies: the kernel ends the interpreter after 30 s whatever it is doing, the container ends, `--rm` removes it, and the docker CLI returns (status 128+14) ten seconds before its own 40 s limit. A container therefore does not outlive the run unless the engine itself is stuck.
2. `sys.path.insert(0,'/app')` (SUP:345; the image keeps the application in `/app/app`, `REL:c3po/backend/Dockerfile:16,33`).
2b. **Every module of the application is imported at the head of the one `try` block, in every run**: `r2d2_v2_shadow` (verifier, calendar), `r2d2_v2_earnings_package`, `r2d2_v2_epoch_assembler`, `r2d2_v2_store` (the refusal class), `r2d2_v2_shadow_worker` (the worker's reader) and `r2d2_v2_live_controller`, with their own imports (causal audit, raw source, raw events, maintenance gate, live group). A reduced dry run without policy and without probe imports them too: no module the first session needs is imported for the first time on Monday. An import that fails is `VERIFY_SNIPPET_FAILED` with the name of the exception's class.
3. Release bytes: PRE from the context (base64); POST with the worker's own reader `app.r2d2_v2_shadow_worker._release_bytes(<target>/<file>)` (APP `r2d2_v2_shadow_worker.py:29-42`: regular, no group or other bit, at most 65,536 bytes, unchanged during the read).
4. `Release.verify(data, <signed sha>, now=<UTC now>, build_sha=<signed revision>, calendar=ShadowCalendar())` — the call of RI:67-73 and of the worker itself (APP `r2d2_v2_shadow_worker.py:79-80`, `r2d2_v2_shadow.py:72-162`). Then: mode `CERTIFIED`; epoch equal to the signed one **and** to the compiled `EPOCH` (APP `r2d2_v2_epoch_assembler.py:9`); first session likewise (`:10`); `ebar_amendment_sha` bound.
5. `implementation_package_sha()` of the image equal to the signed package hash.
5b. Bind probe (PRE, when signed): the worker's reader on `<target>/<file>` of the probe directory; a boolean and the reader's code. This is the one thing POST does that PRE otherwise never exercises on the host: a read-only bind of a private directory under `--read-only`, read by `_release_bytes`. On Sunday the journal root with its `epoch.json` (root:root 0700 / 0600 after operation 4b) is such a directory; nothing of the file leaves but the boolean.
6. Policy candidate (when signed): the controller's own `read_policy` (APP `r2d2_v2_live_controller.py:39-89`) at the instant of the run (reported) and at every signed instant (gated); and the assembler's `validate_policy` (APP `r2d2_v2_epoch_assembler.py:64-79`). The policy file does not exist on the host before activate, so the one file read inside `read_policy` is replaced by the signed bytes (`controller._release_bytes = lambda path: raw`); every other line of the validator is the deployed one.
7. One JSON line on standard output: booleans, codes, the Python and calendar-library versions, and the request hash echoed. Exit 0 when it reached the end, 1 with `{"status":"FAILED","code":…}` otherwise. **What a code is:** for an exception of the release's own two refusal classes (`ShadowIntegrityError` of `r2d2_v2_store`, `Refused` of `r2d2_v2_epoch_assembler`) its single argument, when that is an upper-case token of at most 80 characters (those arguments are constants of the release code); for every other exception, and for any other argument, the name of the exception's class. Never a message. The host side accepts a code only in the grammar `[A-Za-z_][A-Za-z0-9_]{0,79}` and the calendar version only in a 32-character grammar: a hostile container can put a token of that shape into the private receipt, and nothing else. It has no network, no environment of the worker and no secret to put there.

**What the host side makes of it.** The line is validated member by member (`verify_line`): exact key sets, booleans as booleans, codes in a closed grammar, the request hash, the release source of the signed mode, one verdict per signed instant. Anything else from a run that exited 0 is `VERIFY_OUTPUT_INVALID` (UNAVAILABLE): a hostile or broken container can never produce a verified release.

**No secret can leave**: the container has no network, no environment of the worker, and no bind but the release directory (POST) or the signed probe directory (PRE); the snippet names `os` only for `os.write(1, …)`.

**The probe of the bind (PRE).** Proposed directory, in this order of preference: (1) a private directory on the data volume, the filesystem of Monday's bind: an earlier epoch's release directory, when a receipt of this boot shows it root:root 0700 with a root:root 0600 regular `release.CERTIFIED.json`; (2) the journal root after operation 4b with its `epoch.json` (0600, SUP:379), on the root filesystem. With (2) the residual to state to the owner is that Monday's bind source lies on another filesystem than the one rehearsed. The worker's reader refuses any group or other permission bit: the file's mode is read from a receipt before the request is bound.

## 4. The compose render

Command shape of E28:223 and :283-284, word for word: `docker compose --project-name c3po --env-file <deploy>/.env -f <deploy>/c3po/compose.yml [-f -] config --format json`, `C3PO_BUILD_SHA=<revision>` in the environment (E28:222; PIPE:745 sets the same variable), the override on standard input for `-f -`. **Nothing is written to the host**: this is the honest read-only way, and it is the one the 28/09 payload itself used for its dry check before it wrote the override file.

The override is exactly the four names of E28:12 for the service `r2d2-worker`, and is checked from its bytes before any claim: nothing else in it, the release hash equal to the plan's, the release path equal to the installed path as the worker sees it (data volume bound at `/app/day-d-data`, `REL:c3po/compose.yml:165`), the policy path inside that volume, the policy hash equal to the plan's policy.

At run time, in memory: the four names equal the signed values; `C3PO_BUILD_SHA` equal to the revision; the image reference equal to the signed one (and, from the bytes, not beginning with `-`); every other service and every other top-level member identical in the two renders; the worker identical except for the four names; **the data volume by activate's own rule** (`data_bind_of`, the predicate of activate's `service_of`): the worker's volumes are a list of at most 64 objects each with a target, and the policy file and the release file the override names are each covered by exactly one of them, which is a bind of the signed source at the signed target (both compared after `PurePosixPath` normalisation) and not read-only. `RENDER_VOLUMES_INVALID` and `WORKER_MOUNT_NOT_AS_SIGNED` are findings with activate's own names. With signed limits, either render slower than `render_ms` is `RENDER_SLOWER_THAN_THE_SIGNED_LIMIT`. Reported, not gated: which of the four names the base render already has; the size of the render in canonical bytes.

## 4b. What the two writes refuse on, and where it is found here

| The write refuses, before any effect (GO spent, epoch lost) | Found here as | Mode |
|---|---|---|
| install_release `DESTINATION_PRESENT` | `RELEASE_TARGET_ALREADY_EXISTS` (`release_target`) | PRE |
| install_release `PARENT_*`, `EVIDENCE_FROM_EARLIER_BOOT` | `PARENT_*` on `directory:RELEASE_PARENT`, `EVIDENCE_FROM_EARLIER_BOOT` | both |
| install_release `MAINTENANCE_PIN_ABSENT`, `…_NOT_A_REGULAR_FILE`, `…_NOT_ROOT_OWNED` | `MAINTENANCE_PIN_ABSENT`, `MAINTENANCE_PIN_NOT_REGULAR`, `MAINTENANCE_PIN_NOT_ROOT_OWNED` | absent/regular both; owner PRE (a fact in POST) |
| install_release `DATA_VOLUME_FREE_SPACE_BELOW_FLOOR` | the same name, on `directory:RELEASE_PARENT`, against `limits.data_volume_free_bytes` (bind it to install_release's constant, 1,048,576) | when limits are signed |
| activate `DATA_VOLUME_FREE_SPACE_BELOW_FLOOR`, `DATA_VOLUME_FREE_INODES_BELOW_FLOOR` (on the filesystem of its live parent; inodes where they are counted) | the same names, on `directory:LIVE_PARENT`, against `limits.data_volume_free_bytes` and `limits.data_volume_free_inodes` (activate's constants: 1,048,576 and 8); `free_inodes` is activate's function | when limits are signed |
| activate `WORKER_SERVICE_LEFTOVER_CONTAINER` (a container named `<anything>_<worker container>`: an interrupted recreate) | the same name, on `containers`; a count, never a name | both |
| install_release at its binding: `PARENT_SETGID`, `CHAIN_ROW_*`, `DATA_VOLUME_NOT_A_MOUNT_POINT` | signed rows: the same refusals at this binding. Observed rows: `DIRECTORY_NOT_ACCEPTABLE_TO_THE_WRITE_THAT_FOLLOWS` with the code in `rows_refusal` | PRE (a fact in POST) |
| activate `DESTINATION_PRESENT`, `PARENT_*` of the live parent | `LIVE_DIRECTORY_ALREADY_EXISTS` (`live_target`), `PARENT_*` on `directory:LIVE_PARENT`; rows it would refuse at its binding: as above | whenever `live` is signed |
| activate `WORKER_ALREADY_CARRIES_THE_KEYS` (any of the four names present, even with an empty value; the 28/09 payload refused only non-empty values) | `WORKER_ALREADY_CARRIES_A_LIVE_NAME` | both |
| activate `WORKER_NOT_RUNNING`, `WORKER_IMAGE_NOT_THE_SIGNED_ONE`, `IMAGE_REVISION_MISMATCH`, `WORKER_BUILD_REVISION`, `RENDER_IMAGE_CHANGED` | `WORKER_NOT_RUNNING`, `WORKER_IMAGE_MISMATCH`, `IMAGE_ID_MISMATCH`, `IMAGE_REVISION_MISMATCH`, `WORKER_BUILD_REVISION_MISMATCH`, `RENDER_IMAGE_NOT_THE_SIGNED_REFERENCE` | both |
| activate `RENDER_BUILD_REVISION`, `RENDER_ENVIRONMENT_MISMATCH`, `RENDER_VOLUMES_INVALID`, `WORKER_MOUNT_NOT_AS_SIGNED` | `RENDER_BUILD_REVISION_MISMATCH`, `RENDER_ENVIRONMENT_NOT_AS_SIGNED`, `RENDER_VOLUMES_INVALID`, `WORKER_MOUNT_NOT_AS_SIGNED` | whenever a render is signed |
| activate `DEPLOY_VERSION_*`, `ENV_FILE_*`, `LOCK_FILE_ABSENT`, `SECURITY_REBOOT_PENDING`, `MAINTENANCE_PIN_ABSENT`, `RELEASE_NOT_INSTALLED`, `RELEASE_*_NOT_AS_INSTALLED`, `RELEASE_HASH_MISMATCH` | `DEPLOYED_REVISION_*`, `COMPOSE_INPUT_ABSENT_OR_NOT_REGULAR`, `LOCK_FILE_ABSENT`, `REBOOT_PENDING_MARKER_PRESENT`, `MAINTENANCE_PIN_ABSENT`, `RELEASE_DIRECTORY_*`, `RELEASE_FILE_*` (POST) | both |
| activate `LOCK_NOT_TAKEN_BUDGET`, `BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT` (its reads and its render took too long for the recreate to fit) | `DOCKER_CALL_SLOWER_THAN_THE_SIGNED_LIMIT` on each of the four quick reads, `RENDER_SLOWER_THAN_THE_SIGNED_LIMIT` | when limits are signed |
| activate `DEPLOY_LOCK_BUSY` (after its signed wait) | the state of the lock at the instant of the run is a fact: `FREE` or `BUSY` | — |
| activate at its binding: `POLICY_*` | from the bytes here: `POLICY_SCOPE`, `POLICY_WINDOW`, `POLICY_NOT_CANONICAL`; in the container: the controller's and the assembler's own verdicts | whenever a policy is signed |

`tests/test_siblings.py` puts the same host states to the sibling's own assembled source and to this one, and compares constants, the override bytes and the verdict of the bind rule case by case (section 12). It also holds an **inventory**: every constant code of the two sibling sources (97 of activate, 24 of install_release when this was sealed) with where this source stands to it: FOUND (a state of the host before the write's first effect, found here under the names given, each of which must be a code of this source), BINDING (refused from the bytes of the write's own request), INSTANT (a change between two looks of the write's own run, or its clock), AFTER (the write's effects). A code that appears in a sibling and is not in the inventory fails the suite: a new refusal of a write cannot go unnoticed by its rehearsal.

Three rows above (free inodes, the floor on the live parent, the leftover of a recreate) were added while this repair was under way, because activate's own repair added those refusals; SIBLINGS.txt names the activate bytes they were compared with.

**The limits.** activate makes four quick docker reads and one render before it asks for the lock, two more quick reads under it, and needs `34 + max(3, min(15, int(2 × render) + 1)) + 1 + 3` seconds left before its first effect (two more while it waits for the lock). With every quick read at 1.5 s and the render at 3 s it is left 51 s when it asks for the lock (47 kept) and 48 s before its first effect (45 needed): the proposed pair is `render_ms: 3000, quick_ms: 1500`, which leaves 3 s of slack and up to 4 s of lock wait. `tests/test_siblings.py` runs activate's own source on its own fixture with exactly those costs (it completes) and with twice those costs (it refuses before any effect). Looser limits must be recomputed with that arithmetic before they are signed.

## 5. Refusals, findings, failed observations

### 5.1 Refusals (exit 1, `REFUSED_NOTHING_OBSERVED`): all before the first observation

| When | Codes | Spends the GO? |
|---|---|---|
| Authentication (core), run locally by the dispatcher before any claim and again on the host | `PIN_MISMATCH`, `DOCUMENT_*`, `*_KEYS`, `REQUEST_OR_EXECUTOR_UNBOUND`, `REQUEST_SCOPE`, `AUTHORITY_UNBOUND`, `GO_UNBOUND`, `OWNER_UNBOUND`, `HOST_BINDING`, `GO_TRANSPORT_UNBOUND`, `GO_CLAIM_ROOT_UNBOUND`, `DATE_NOT_IN_SCOPE`, `DATE_WINDOW_MISMATCH`, `WINDOW_*`, `OUTSIDE_GO_WINDOW`, `PLAN_*`, `SCOPE_MISMATCH`, `EVIDENCE_*`, `EFFECTS_BINDING`, `GO_CRITERION` | No when the dispatcher finds it locally (no claim). Yes if it only shows on the host (wrong uid, expired window) |
| `validate_plan` (pure, from the bytes) | `MODE_INVALID`, `EVIDENCE_BOOT_UNBOUND`, `REVISION_OR_PACKAGE_UNBOUND`, `ROWS_FLAG_INVALID`, `DRY_RUN_PROFILE_INVALID`, `IMAGE_PLAN_INVALID`, `WORKER_PLAN_INVALID`, `RELEASE_PLAN_INVALID`, `CHAIN_ROW_INVALID`, `CHAIN_ROW_UNSAFE`, `CHAIN_ROW_WORLD_WRITABLE`, `PARENT_SETGID`, `RELEASE_OUTSIDE_THE_DATA_VOLUME`, `RELEASE_NOT_THE_SIGNED_BYTES`, `RELEASE_INVALID`, `RELEASE_SCOPE`, `LIVE_PLAN_INVALID`, `LIVE_OUTSIDE_THE_DATA_VOLUME`, `LIVE_AND_RELEASE_OVERLAP`, `LIMITS_PLAN_INVALID`, `POLICY_REQUIRED`, `POLICY_PLAN_INVALID`, `POLICY_NOT_THE_SIGNED_BYTES`, `POLICY_INVALID`, `POLICY_NOT_CANONICAL`, `POLICY_SCOPE`, `POLICY_WINDOW`, `DEPLOY_PLAN_INVALID`, `RENDER_REQUIRED`, `RENDER_PLAN_INVALID`, `OVERRIDE_NOT_THE_SIGNED_BYTES`, `OVERRIDE_INVALID`, `COMPOSE_PROJECT`, `COMPOSE_FILES`, `RENDER_OUTSIDE_THE_DEPLOY_TREE`, `OVERRIDE_RELEASE_BINDING`, `OVERRIDE_POLICY_BINDING`, `OVERRIDE_POLICY_NOT_IN_THE_LIVE_DIRECTORY`, `DRY_RUN_NOT_THE_FULL_PROFILE`, `DRY_RUN_NOT_THE_PLACES_OF_INSTALL_RELEASE`, `DRY_RUN_NOT_THE_LAYOUT_OF_ACTIVATE`, `OVERRIDE_NOT_AS_ACTIVATE_WRITES_IT`, `DATA_VOLUME_NOT_A_MOUNT_POINT`, `UNITS_PLAN_INVALID`, `JOURNAL_PLAN_INVALID`, `DOCKER_CONFIG_INVALID`, `DOCKER_CONFIG_ONLY_IN_A_REDUCED_DRY_RUN`, `BIND_PROBE_INVALID`, `MOUNT_INVALID`, `VERIFY_FRAME_TOO_LARGE` | No: the dispatcher refuses before the claim |
| First gate call of `perform` | `GO_EXPIRED`, `CLOCK_REVERSED` | Yes (the claim exists); nothing was touched |
| Executor | `EXECUTOR_IDENTITY` (effective uid or gid not 0) | Yes; nothing was looked at |

From the first observation on nothing refuses: the run reports.

`POLICY_NOT_CANONICAL`: the controller compares the hash of the policy file; the assembler compares the hash of the canonical form of its content (`json.dumps(sort_keys=True, separators=(',',':'), ensure_ascii=False)`, APP `r2d2_v2_epoch_assembler.py`: `canonical`, `digest`, `POLICY_HASH`). One signed hash meets both only when the file is that canonical form byte for byte: a trailing newline is enough to be accepted by the one and refused by the other. This is decidable from the bytes and is refused here before any claim. **activate's `validate_policy` does not carry this refusal** (it signs `content_digest_sha256` in its effects, beside the file hash, and compares neither): a policy that passes here is safe for activate; a policy bound for activate without a PRE first is not checked for it. Reported to the author of K6a (section 13).

### 5.2 Findings (exit 2, `OBSERVED_ALL_EXPECTATIONS_NOT_MET`; every other item stays in the receipt)

`EVIDENCE_FROM_EARLIER_BOOT` · `PARENT_MISSING`, `PARENT_SYMLINK_COMPONENT`, `PARENT_NOT_DIRECTORY`, `PARENT_IDENTITY_MISMATCH` (with `fields_that_differ` as booleans), and without signed rows `SYMLINK_COMPONENT`, `COMPONENT_NOT_DIRECTORY` · `DIRECTORY_NOT_ACCEPTABLE_TO_THE_WRITE_THAT_FOLLOWS` (release parent in PRE, live parent in both), `DATA_VOLUME_FREE_SPACE_BELOW_FLOOR` (with signed limits) · PRE `RELEASE_TARGET_ALREADY_EXISTS` · `LIVE_DIRECTORY_ALREADY_EXISTS` · POST `RELEASE_DIRECTORY_ABSENT`, `RELEASE_DIRECTORY_NOT_A_DIRECTORY`, `RELEASE_DIRECTORY_METADATA`, `RELEASE_DIRECTORY_IS_A_MOUNT_POINT`, `RELEASE_DIRECTORY_ENTRIES`, `RELEASE_FILE_ABSENT`, `RELEASE_FILE_NOT_REGULAR`, `RELEASE_FILE_METADATA`, `RELEASE_FILE_TOO_LARGE`, `RELEASE_FILE_BYTES_MISMATCH` · `DOCKER_CONFIG_NOT_PRIVATE_AND_EMPTY`, `DOCKER_CONFIG_CHANGED_DURING_RUN` · `VERIFY_ENGINE_FAILURE` (docker's 125/126/127), `VERIFY_RUN_FAILED` (any other non-zero status without a readable line, the alarm included), `VERIFY_SNIPPET_FAILED` (with the snippet's code), `PACKAGE_NOT_THE_SIGNED_ONE`, `RELEASE_NOT_READ_IN_THE_CONTAINER`, `RELEASE_BYTES_NOT_THE_SIGNED_ONES`, `RELEASE_NOT_VERIFIED` (with the release code's own code), `RELEASE_SCOPE_NOT_AS_SIGNED`, `POLICY_BYTES_NOT_THE_SIGNED_ONES`, `POLICY_REFUSED_BY_THE_CONTROLLER`, `POLICY_REFUSED_BY_THE_ASSEMBLER`, `BIND_SOURCE_REPLACED_DURING_RUN`, `BIND_PROBE_NOT_READ` · `VERIFY_CONTAINER_LEFT_BEHIND` · `IMAGE_ID_MISMATCH`, `IMAGE_REVISION_MISMATCH` · `WORKER_IMAGE_MISMATCH`, `WORKER_NOT_RUNNING`, `WORKER_BUILD_REVISION_MISMATCH`, `WORKER_ALREADY_CARRIES_A_LIVE_NAME` · `DOCKER_CALL_SLOWER_THAN_THE_SIGNED_LIMIT`, `RENDER_SLOWER_THAN_THE_SIGNED_LIMIT` (with signed limits) · `RENDER_ENVIRONMENT_NOT_AS_SIGNED`, `RENDER_BUILD_REVISION_MISMATCH`, `RENDER_IMAGE_NOT_THE_SIGNED_REFERENCE`, `OVERRIDE_CHANGES_MORE_THAN_THE_WORKER`, `OVERRIDE_CHANGES_MORE_THAN_THE_LIVE_NAMES`, `RENDER_VOLUMES_INVALID`, `WORKER_MOUNT_NOT_AS_SIGNED` · `DEPLOYED_REVISION_MISMATCH`, `DEPLOYED_REVISION_FILE_ABSENT`, `COMPOSE_INPUT_ABSENT_OR_NOT_REGULAR` · `MAINTENANCE_PIN_ABSENT`, `MAINTENANCE_PIN_NOT_REGULAR`, PRE `MAINTENANCE_PIN_NOT_ROOT_OWNED` · `UNIT_STATE_NOT_AS_SIGNED` · `JOURNAL_ROOT_ABSENT`, `FREE_SPACE_BELOW_FLOOR` (both only with a signed floor) · `LOCK_FILE_ABSENT` · `REBOOT_PENDING_MARKER_PRESENT` · `DIRECTORY_REPLACED_DURING_RUN`.

### 5.3 Observations that failed (exit 2, `PARTIAL_OBSERVED`; the item is `UNAVAILABLE` with a constant code, never an absence)

`COMMAND_FAILED` (with the return code), `COMMAND_TIMEOUT`, `COMMAND_OUTPUT_LIMIT`, `COMMAND_NOT_STARTED`, `COMMAND_NOT_STARTED_BUDGET`, `COMMAND_SKIPPED_AFTER_TIMEOUT`, `BINARY_UNAVAILABLE_OR_UNSAFE`, `DOCKER_CONFIG_DIRECTORY_UNAVAILABLE`, `DIRECTORY_NOT_HELD`, `RELEASE_DIRECTORY_NOT_HELD`, `BIND_PROBE_NOT_HELD`, `RELEASE_DIRECTORY_CHANGED_DURING_READ`, `RELEASE_FILE_CHANGED_DURING_READ`, `FILE_CHANGED_DURING_READ`, `FILE_NOT_REGULAR`, `FILE_TOO_LARGE`, `PARENT_REPLACED`, `PARENT_UNREADABLE`, `PARENT_CHANGED_DURING_WALK`, `PATH_CHANGED`, `ENTRY_LIMIT`, `VERIFY_OUTPUT_INVALID`, `WORKER_NOT_OBSERVED`, `IMAGE_METADATA_INVALID`, `CONTAINER_METADATA_INVALID`, `CONTAINER_LIST_INVALID`, `ENVIRONMENT_METADATA_INVALID`, `COMPOSE_RENDER_INVALID`, `COMPOSE_SERVICE_INVALID`, `PROPERTY_OUTPUT_INVALID`, `PROPERTY_LINE_INVALID`, `PROPERTY_VALUE_INVALID`, `PROPERTY_MISSING`, `UNIT_ID_MISMATCH`, `STATVFS_INVALID`, `LOCK_FILE_NOT_REGULAR`, `LOCK_FILE_REPLACED`, `LOCK_UNAVAILABLE`, `SYMLINK_COMPONENT` (through a link nothing is said to be absent), `BOOT_ID_INVALID`, `NOATIME_UNAVAILABLE`, `OS_ERROR` (with the errno), `OBSERVATION_FAILED`.

`GO_EXPIRED` and `CLOCK_REVERSED` stop the run: what was observed stays, nothing is observed afterwards, the receipt's code is the expiry.

The receipt's `code` is the first finding when there is one, otherwise `OBSERVATION_INCOMPLETE`; the outcome says which of the two it is.

**Items that are facts only do not decide.** Three items carry no signed expectation at all: `reboot_required`, a `unit:<name>` signed without an expectation, and `journal` signed without a floor. When one of them cannot be observed its item is `UNAVAILABLE` with its code as above, the receipt lists it under `fact_items_not_observed` (and under `items_not_complete`), and the outcome is decided by the other items: such a run can still end KNOWN_COMPLETE. The success outcomes keep their names; "all observed" is to be read as "every item that carries a signed expectation". Every other item gates and behaves as before. An expiry is never a fact: it stops the run whatever the item. Items that gate and cannot be omitted by the plan: `boot`, the three directories, `release_target`, `verify`, `containers`, `image`, `worker`, `deploy_files`, `maintenance_pin`, `reboot_pending`, `directories_stable`. That residual on Monday's single shot is accepted in writing by the signers of M2 (CONTRACT section 6).

**A receipt reduced for size** is `PARTIAL … PARTIAL_OBSERVED` (the core sets that), and both reduction steps of this source now also set `expectations_met` and `gates_first_session_readback` to false and, when the receipt had no code, the code `RECEIPT_REDUCED_FOR_SIZE`. Measured: a complete POST receipt is about 12,000 bytes, a complete full PRE receipt about 14,000 (17,000 with rows, three units and the journal), against a limit of 60,000.

### 5.4 Reported, never gated (`facts_reported_not_gated` in the scope and in every receipt)

Lock state `FREE`/`BUSY`; `/run/reboot-required`; a unit's state without a signed expectation; a journal root that does not exist and its free space without a signed floor; restart count and health of the worker; whether the policy is inside its window at the instant of the run; Python and calendar-library versions of the image; presence of the two catalog names; the owner of the pin in POST; the milliseconds of every command without signed limits; whether the rows of a directory that receives no entry after this run would be accepted by a write.

## 6. Crash points and how they are told apart

The source changes nothing on the filesystem, so a crash leaves no state there in any case. What can exist after a crash:

| Where the process dies | What exists afterwards | How it is told apart |
|---|---|---|
| Before the container is started (items 0–4) | nothing | no receipt (verdict UNCERTAIN); `docker ps -a` shows no `hostops02-k11-<go16>` |
| Between the engine's create and its start (the CLI killed in that instant) | a container in state `created`: it has no process, so no alarm ever fires and `--rm` never acts. It stays until someone removes it | the same name; `docker ps -a` shows it with state `created` |
| While the container runs (docker CLI attached) | the container may live until its alarm (30 s) and is then removed by `--rm` | its name is derived from the GO hash, which is single-use: a later read (`docker ps -a`, PS format proven) shows that exact name or nothing. Within one minute it is gone unless the engine is stuck |
| CLI killed by the runner (class limit, budget, output limit) | the same | the same run reports it: `verify` is UNAVAILABLE with `container_may_still_exist: true`, and `containers` (the next command) says whether that name is listed (`VERIFY_CONTAINER_LEFT_BEHIND`) |
| After the container | nothing | no receipt; nothing to clean |
| A shared lock held at death | released by the kernel with the descriptor | — |
| Anything escaping `perform` | — | the core's last resort returns `PARTIAL … RUN_ESCAPED_STATE_UNKNOWN`, phase `ESCAPED`; the launcher files an exception that escapes `run()` as UNCERTAIN, never as a refusal |

No source of this family removes a container; a leftover is a finding for the owner, not something this operation repairs. A leftover of the Sunday run (`hostops02-k11-<go16>`, in whatever state) is removed by the owner, by that exact name, before Monday's M0 looks for stray containers; a leftover of M2 is dealt with before M3 is dispatched (CONTRACT section 8, steps 11 and 12).

**Why M3 waits for M2.** activate lists the containers under its lock and requires, after its recreate, that every other container is still listed with the same ID. A container of this source that is listed then and removed by the engine during activate (it lives until the snippet ends: at most the 30 s alarm, plus start and removal) would make activate end PARTIAL (`OTHER_CONTAINERS_CHANGED`) after the worker was already replaced. So M3 is dispatched only with M2's KNOWN_COMPLETE receipt in hand (it carries `verify_container_present: false`); after an UNCERTAIN or timed-out M2, one read that shows no `hostops02-k11-*` container comes first.

## 7. Time budget

Limits that do not move: payload 60 s, dispatcher watchdog 80 s, transport 270 s. Every external command is time-boxed by its class and by the gate.

| Step | Class limit | Expected | Note |
|---|---|---|---|
| items 0–4 (system calls) | — | < 0.2 s | no command before the container |
| `verify` | 40 s (needs 44 s left to start); alarm inside at 30 s | 5–15 s (**unmeasured**: container start, import of the application and of the calendar library, 48 files hashed) | the Sunday run measures it (`items.verify.elapsed_ms`) |
| `containers`, `image`, `worker`, `worker_environment` | 8 s each | < 0.5 s each | proven formats; `command_ms` in the receipt, judged against `limits.quick_ms` |
| `render` | 15 s each, two renders | 1–3 s each (**unmeasured**, U6) | `base_ms`, `override_ms` in the receipt, each judged against `limits.render_ms` |
| `unit:*` | 8 s each | < 0.1 s each | |
| the rest (system calls) | — | < 0.1 s | |
| **Sum, expected** | | **10–25 s** | |

Worst case: the container uses its 30 s alarm; 30 s remain for the reads, of which two renders may take 15 s each. Then the last items expire: the receipt is PARTIAL with `GO_EXPIRED`, keeps everything observed, and nothing waits. A tool that timed out twice is not started again (`COMMAND_SKIPPED_AFTER_TIMEOUT`). There is no sleep, no poll and no retry in this source.

**For Monday (M2 is single-shot):** keep the POST plan short — `render: null` (K6a renders by itself), `limits: null`, `units: []` or units without expectation (facts: they no longer decide when they cannot be read), the journal null or without a floor, `live` signed (two system calls; activate is still to come). Then the run is one container and four quick reads.

## 8. What the owner signs

**Plan members** (18; all in the request, the visible ones repeated in the effects of the authority and the GO):

| Member | Content | Source of the value |
|---|---|---|
| `mode` | `PRE` or `POST` | — |
| `dry_run` | PRE: `FULL` or `REDUCED`. POST: null | the Sunday request is `FULL` |
| `evidence_boot_id_sha256` | boot of the evidence | read-only receipt of the same boot |
| `revision`, `package_sha256` | `dd4ec4bb…e858`, `b5ce527a…db84` | the release; by command |
| `image` | `{reference, image_id}` | post-deploy receipt |
| `worker` | `{container, environment (bool), data_source, data_target}` | post-deploy receipt; `REL:c3po/compose.yml:165` |
| `release` | `{sha256, bytes, content_b64 (PRE) or null, parent {path, rows or null, open_root}, directory_name, file_name, container_target (POST), directory_entries (POST)}` | the signed release; K10's constants and K10's parent rows |
| `live` | null or `{parent {path, rows or null, open_root}, directory_name}` | K6a's request: its `live_parent` rows and `directory_name` |
| `policy` | null or `{sha256, bytes, content_b64, valid_at [1–4 instants]}`; the bytes are the canonical form | the signed policy; the instants are the starts of M3's gates and the first open and last close |
| `render` | null or `{project, env_file, files, override_b64, override_sha256, override_bytes}` | K6a's request; the override bytes are what K6a's `override_of` gives |
| `limits` | null or `{render_ms, quick_ms, data_volume_free_bytes}` | section 4b (3000, 1500) and K10's `FREE_BYTES_FLOOR` (1,048,576) |
| `deploy` | `{tree, lock_directory (each {path, rows or null, open_root}), lock_name or null, version_name}` | receipt of the same boot |
| `units` | list of `{name, expected: null or {LoadState/ActiveState/SubState/UnitFileState: value}}` | the signers |
| `journal` | null or `{path, floor_bytes or null}` | the supervisor's placement |
| `docker_config` | null; a path only in a reduced dry run | activate never sets it |
| `rows_in_receipt` | bool | true on Sunday when the observed rows are to be the evidence of M1 and M3 |
| `bind_probe` | null, or in PRE `{directory {path, rows or null, open_root}, file_name, container_target}` | section 3 |

**Effects** (`effects_of`, literal in authority and GO, recomputed and compared; 28 members): operation, mode, `gates_first_session_readback`, `dry_run`, `rehearses_install_release_and_activate`, epoch, first session, revision, package, image, worker, release (hash, size, host path, path in the worker, source, expected state, entries, parent chain), live (path, expected state, parent chain), verify (snippet hash, image ID, binds, network none, command, alarm), policy (hash, size, instants), render (project, files, override hash, the four intended values), limits, deploy (two chains, lock path, revision file), maintenance pin path, bind probe (chain and file), units, journal, docker_config, rows_in_receipt, evidence boot, `writes: 0`, `containers_run: 1`, `activation: false`.

**Success criterion** of the GO: the outcome of the signed mode and profile (the template carries null). A GO for another outcome is refused (`GO_CRITERION`), locally, before any claim.

**Evidence**: required, no operation name is imposed (the rows may come from the combined preflight, the precheck or an earlier PRE run).

## 9. What the in-run readback proves, and what only the host can prove

**Proven by a KNOWN_COMPLETE receipt (in the run itself):**

- PRE, full profile: the release bytes that will be installed are accepted by the deployed code, in the deployed image, at that instant, with the revision the worker runs; the policy bytes are the canonical form and are accepted by both validators at every signed instant; a read-only bind of a private directory is readable by the worker's reader under `--read-only`; the place of the installation and the place of activate's directory are empty and their parents are the signed directories, with rows the two writes accept; the data volume has the signed free space; the override, in the bytes activate writes, renders to exactly the four intended values, changes nothing else, and leaves the policy and the release reachable through the one signed read-write bind; the running worker carries none of the four names; the two renders and the four quick docker reads answered within the signed milliseconds; the image, the worker and the deployed revision are the signed ones; the lock file exists and can be probed by root on a read-only descriptor; no reboot is pending; the pin is there and is root's.
- POST: the installed file is, byte for byte, the signed release, with the metadata the worker's reader requires, and the deployed reader and verifier accept it through a bind; the policy candidate is accepted by the controller's and the assembler's validators at every signed instant.
- Both: nothing on the filesystem was changed (the source cannot), the held directories were the same at the end.

**Not proven by the run; only the host or a later operation can:**

- That the worker, once recreated, loads the release and the policy: the worker's settings, its database and its own bind are not exercised here. The fresh container has the image's code and none of the worker's environment.
- That `Release.verify` still holds at activation time is implied only as far as the code has no upper time bound on `now` (it has none: APP `r2d2_v2_shadow.py:101-107,151-160`); the policy is checked at the signed instants, not at the real instant of M3.
- The bind of the data volume in the *running* worker (judged in the render only).
- That docker answers on Monday as fast as it did on Sunday: the limits judge the instant of the dry run.
- That the lock is free when activate asks for it.
- That nothing changes between this read and the next write: K10 and K6a walk their own pinned rows.
- Emulated only: every Docker and systemd behaviour (section 10).

## 10. Command shapes: precedent, and what is UNPROVEN

| Shape | Precedent | Status |
|---|---|---|
| `docker image inspect --format <IMAGE_FORMAT> <ref>`; `docker container inspect --format <CONTAINER_FORMAT> <name>`; `docker ps -a --no-trunc --format <PS_FORMAT>` | PD5:170, :263 and the core's byte-identical templates; ran on the host 01/10 and 02/10 under this fixed environment | proven |
| `docker compose --project-name c3po --env-file … -f … [-f -] config --format json`, override on stdin | E28:223, :283-284 (28/09, rc 0) | proven **with the inherited environment of that process**; under the fixed environment without `HOME` it is the core's U4 |
| `docker run --rm -i --pull never --init --user 0:0 --network none --read-only --cap-drop ALL --security-opt no-new-privileges … <image ID> python -I -B -` | SUP:336-339 (README: "has not been executed in a container anywhere", SUP:5, :593) | **UNPROVEN** (core U2); K2a's rehearsal A6 runs the same prefix on Saturday |
| `--name hostops02-k11-<go16>` on that run | none | **UNPROVEN** (K11-U1) |
| `--mount type=bind,source=<private directory>,target=/c3po-…,readonly` with `--read-only`, and the worker's reader on a 0600 file through it | SUP:338 (journal, read-write, target below `/`); SUP:593 says the target below `/` under `--read-only` is not proven anywhere | **UNPROVEN** (K11-U2). Exercised on Sunday only if the PRE request signs `bind_probe`; otherwise the first real run of this shape is Monday's M2. `linux_root/shapes_k11.py` exercises it on a throwaway runner |
| framed standard input `SIGNED_CONTEXT=…\n<snippet>` to `python -I -B -` | PD5:439-442 (`docker exec`, 02/10) | proven for `exec`; for `run` part of U2 |
| `signal.alarm` with the default action ending the interpreter under `--init` | none | **UNPROVEN** (K11-U3). If Python were PID 1 the signal would be ignored; `--init` is in the prefix |
| import of `app.r2d2_v2_shadow`, `…live_controller`, `…epoch_assembler` and `exchange_calendars` with a read-only root, no network, no environment, `-I -B` | RI:67-73 and E28:270-273 imported `Release`/`ShadowCalendar` by `docker exec` in the running worker (writable layer, worker environment) | **UNPROVEN** in a fresh read-only container (K11-U4). Verified offline: the modules import nothing of the settings at module level, and the snippet runs against the release's own modules (tests, 3.12) |
| `container_environment` template (booleans for five names) | PD5:266-275 ran the constructs | core U3 (the composition) |
| `systemctl show <unit> -p Id -p LoadState … -p TriggeredBy` | H01 `op_readback.py:61-62,70` (same argv); to be run by the hostops01 readback on Sunday 10:00 | **UNPROVEN** until that receipt (K11-U5) |
| shared `flock` on `deployment.lock` opened `O_RDONLY` as root | PIPE:653-654 takes it exclusively through a shell descriptor | core U5 |
| size and duration of the render | — | core U6; this operation reports both |
| volumes of a service in `docker compose config --format json` as `{type, source, target, read_only}` | compose documentation; activate reads the same shape with the same rule | **UNPROVEN** (K11-U6). Now a gate, with activate's rule: if compose prints another shape, the Sunday dry run ends with `RENDER_VOLUMES_INVALID` or `WORKER_MOUNT_NOT_AS_SIGNED`, which is exactly what activate would do on Monday. That finding is then a defect of both sources to repair on Sunday, not a state of the host |

The Sunday PRE run, in the full profile, closes U2, U3, U4, U5, U6 of the core and K11-U1, U2 (the full profile signs `bind_probe`), U3 (only as far as no alarm fires), U4, U5, U6 for this host. `linux_root/shapes_k11.py` runs six shapes with this source's own table, helpers and Native on a throwaway Linux runner (a plain Python image with the tests' stand-in package bound at `/app`): the PRE run, the PRE run with the probe of the bind (the container of the full dry run), the POST bind, a file the reader refuses, the alarm on an interpreter that hangs (status 142), `systemctl show`. It was not run: no Linux and no docker offline, and this work may not contact a server; its `--self-test` on the emulation is part of the suite. **It should run, with the core's Linux job, before the Sunday request is bound** (section 14).

## 11. Open decisions

For the owner:

1. **O-3** (master plan): whether this operation's container run counts as a read of the grid or needs an individual answer. The source does not depend on the answer.
2. **`rows_in_receipt`**: with `true` the private receipt carries the observed six-key rows (device, inode) of the directories, the live parent included, so that K11 PRE can serve as the row evidence for M1/M3; with `false` identities are booleans and counts only. activate, as repaired beside this directory, names this operation as the evidence its request must cite: the Sunday request should sign `true`.
3. **The floor** for the journal filesystem on Monday (a number, or none).
4. **The residual on M2** (section 5.3): the items that gate and cannot be left out.

For the co-auditor:

5. **Which directory Sunday's PRE signs as `bind_probe`** (section 3): an earlier release directory on the data volume if a receipt shows one that is private, otherwise the journal root after 4b. The full profile no longer leaves the probe to choice.
6. **The limits** (section 4b): 3000 / 1500 ms and install_release's floor, or other figures recomputed with activate's arithmetic.
7. **Class `RUN` (40 s) with a 30 s alarm**, or `RUN_SHORT` (20 s) with a shorter alarm, after Sunday's measurement. Changing it changes the bytes.
8. **The snippet is part of the source** (pinned by the payload hash and by the scope), not of the request. A defect found on Sunday means new payload bytes and a new review, not only a new request.
9. **The policy's `valid_at`**: proposed as the start of M3's gate, the start of its spare gate, the first open and one second before the last close (at most four).
10. **K6a's `validate_policy` and the canonical form** (section 5.1): whether activate adds the refusal, or M3 is bound only on a policy a full PRE has accepted.

Closed by the repair: `docker_config` is no longer a choice (null in both requests of Monday's path; a path only in a reduced dry run); the cross-refusal with the three sibling operations runs in the suite (`OTHERS` in `tests/test_conformance.py` takes every sibling that stands beside this directory).

## 12. Tests and mutation (figures in SHA256SUMS' neighbours `TESTS.*.txt`, `mutation/MUTATION_RUN*.json`)

- Conformance: the core's 121 tests for each mode (242). One test of the suite compares the outcome with `COMPLETE_OUTCOME`; for PRE it is restated with `success_of(plan)` (a limit of the core's test suite for a source with two success outcomes, not of the payload).
- Plan: every refusal of `validate_plan`, in both modes where it applies; effects equal to an independently written literal; the GO criterion per mode at both layers; no claim for a malformed plan.
- Readback: every finding, every failed observation, hostile filesystem states (links in the chain and at the leaf, wrong owner, group, mode, a second link, a foreign file, an existing target, a FIFO, a replaced directory, a mount point), hostile command answers (42 malformed container lines, garbage, oversize, wrong statuses, hostile systemctl and compose output), timeouts, budget, expiry, death of the process, privacy of the receipt.
- Snippet: the exact bytes executed by a real interpreter against a stand-in package (both interpreters) and against the application modules of dd4ec4bb with the real calendar library (3.12): a synthetic release and policy built with the release code's own constants pass, and the release code's own refusals come through as codes.
- Native: the source's own `Native` with real system calls on a temporary tree, under an audit hook: read-only opens, `O_NOFOLLOW`, by `dir_fd`, the real `flock` sequence, nothing created, modified or removed.
- Linux shapes: `linux_root/shapes_k11.py --self-test` on the emulation (the real job was not run).
- Mutation: one mutant per refusal of `validate_plan`, per member of `effects_of`, per finding and gate of `perform`, per check of the container's line, and the words of the snippet.
- Siblings (`tests/test_siblings.py`, 10 tests): this source against install_release and activate as their assembled sources stand beside it: shared constants; `free_inodes` and the leftover rule; the override bytes; the verdict of the bind rule on 24 renders (activate's `service_of` against `data_bind_of`); the acceptability of observed rows against the sibling's own `validate_chain` and mount-point rule; the revision file; the same host states put to the sibling's own fixture (refused before any effect) and to the full dry run (a finding): 12 states for activate, 4 for install_release; activate's own budget on its own fixture at the proposed limits and at twice those; the inventory of every code of both. In a private copy without siblings (a mutation run) these tests skip.
- The repair added one test per accepted finding and, to the mutation list, one mutant per new refusal, finding, gate and effect, the five survivors of the reviewer's own two lists, and one combined mutant (the second reduction step alone is implied by the first: recorded as redundant, the pair must die).

## 13. The repair of 02/10: sixteen findings of two reviews

Evidence for each verdict was reproduced on the sealed bytes before anything was changed (`review-host/exp_pre_gaps.py` and `exp_real.py`, the reviewer's own mutant lists), and after the repair the same experiment reports a finding for every state it probes.

| # | Finding | Verdict | What changed |
|---|---|---|---|
| 1 | MAJOR: PRE ends KNOWN_COMPLETE in states on which K6a or K10 refuse (live names, pin owner, data bind, free space, slow docker) | ACCEPTED (E1, E2, E4, E4b, E5 reproduced: complete, findings []) | five findings with the writes' own predicates (section 4b); plan member `limits`; `data_bind_of` is activate's rule, proven equal case by case. Extended to what activate's concurrent repair added (free inodes, the floor on the live parent, a leftover of a recreate) and closed with the inventory test |
| 2 | MAJOR: PRE never looks where K6a creates its directory | ACCEPTED (E3 reproduced) | plan member `live`; items `directory:LIVE_PARENT`, `live_target`; the override's policy path must lie directly in that directory |
| 3 | MAJOR: a PRE signed with the defaults leaves the bind, two imports and the policy validation to Monday | ACCEPTED | plan member `dry_run`; the full profile is mandatory for the outcome that counts; the snippet imports reader and controller in every run |
| 4 | MINOR: a policy that is not canonical is found only in the container | ACCEPTED (exp_real reproduced) | `POLICY_NOT_CANONICAL`, from the bytes. The same refusal in K6a is K6a's (reported) |
| 5 | MINOR: a fact that cannot be observed turns POST PARTIAL | ACCEPTED | fact items do not decide; `fact_items_not_observed` |
| 6 | MINOR: `docker_config` presented as a choice K6a does not have | ACCEPTED | `DOCKER_CONFIG_ONLY_IN_A_REDUCED_DRY_RUN` |
| 7 | MINOR: a K11 container listed by K6a and removed during M3 | ACCEPTED (code reading of activate's `read_after`) | no byte: binding steps 11 and 12 of the contract; section 6 |
| 8 | MINOR: a failed docker run reaches the receipt as a return code only | ACCEPTED as a core defect (stderr is discarded by the frozen runner) | no byte here: the elimination a receipt allows is written in the contract (section 6); reported for a later core generation |
| 9 | MINOR: `rows_acceptable_to_a_write` promises more than it checks | ACCEPTED (E6 reproduced) | judged with `receives_entry` and the mount-point rule for the directories that receive an entry; a finding when the write is still to come; signed rows refused at this binding as the write refuses them |
| 10 | MINOR: PRE runs after M1/M3 are countersigned; the Linux jobs never ran | ACCEPTED as schedule and as an open residual | no byte: section 14. The Linux jobs could not be run from here (no docker, no server may be contacted) |
| 11 | MAJOR (binding): POST's bind shape first runs on Monday unless PRE signs `bind_probe` | ACCEPTED | the full profile requires `bind_probe`; `linux_root/shapes_k11.py` gains the container of the full dry run |
| 12 | MINOR: a reduced receipt keeps `expectations_met` and the gate flag true | ACCEPTED (hostile test H1 reproduced) | both reduction steps clear both flags and set a code; a POST reduction test |
| 13 | MINOR: five mutants of the reviewer survive | ACCEPTED | five tests; the five mutants are in the list (S01–S05) and die |
| 14 | MINOR: "constant codes" overclaims | ACCEPTED | the snippet carries an argument only for the release's two refusal classes; the claim is reworded (section 3, item 7) |
| 15 | MINOR: a container created and never started has no alarm | ACCEPTED | no behaviour: section 6, the side-effects text of the scope, the contract |
| 16 | MINOR: cross-refusal only against the demonstration operations | ACCEPTED | `OTHERS` takes the siblings that stand beside this directory |

Beyond the findings, found while repairing: the deployed revision file was compared more strictly here (exactly the revision and one newline, at most 64 bytes) than activate compares it (white space aside, at most 128 bytes): a file activate accepts could have failed Monday's single-shot readback. Now the same comparison, with a differential test.

## 14. What must happen, in order, before Monday (not bytes: the runbook this source needs)

1. Run the core's Linux job and `linux_root/shapes_k11.py` on a throwaway runner as soon as a server may be contacted. If compose needs `HOME` (core U4), that is a new core generation and new bytes for K6a and for this source: it must be known before the owner signs M3.
2. Dispatch the full PRE as soon as the release bytes, the policy bytes and the reviewed K10 and K6a bytes exist, and **before** the sitting at which M1 and M3 are countersigned, so that they are signed on its evidence. The master plan has it after that sitting (12:30 against 12:00): proposed change.
3. If anything changes the host afterwards (L1's B4 edits the environment file and recreates the worker), bind and run a second full PRE after it. A PRE receipt speaks of the instant of its run.
4. Re-run `tests/test_siblings.py` by command after K10 and K6a are sealed, and again after any repair of either.
5. On Monday: M3 only with M2's KNOWN_COMPLETE receipt in hand.

