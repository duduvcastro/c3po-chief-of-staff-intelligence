# K6b — capacity switch (`GO_WRITE_HOSTOPS02_CAPACITY_SWITCH_01`) — design, revision 2

**Revision 2 (2026-10-05 UTC), after Codex decisions 1 and 6 (#429 5985748037); section 14 says what changed.** K6b is
now assembled from its OWN core generation, `../core-k6b` (generation `4bb3b3babd292096893fceb335cb4fb8f85fd4c38117e30d779da8669d26c10e`,
seal in `../core-k6b/CORE_SHA256SUMS`): the token family's core (non-dumpable process, its CORE.md §14) plus, in
`assemble.py`, `IN_PLACE_EDIT_EXCEPTION`, the exact exception to the core's rule 4 for this source's row `edit_env`
(CORE.md §15). A first rev-2 core built on the 2026-10-02 core (`eccc557b…`) was superseded before any seal and is kept
aside as `../core-k6b.superseded-eccc557b`. **Rule 4 ("nothing that exists is overwritten") is NOT preserved by
K6b**: it edits `<deploy>/.env` in place. Revision 1 (sealed `456de9c3…`) is kept beside as `../k6b.rev1-456de9c3`;
every hash of it is void for use. Where the sections below still say "frozen core" for the parts, read: the parts of
`core-k6b`, byte-identical to the 2026-10-02 core.

Offline work only. Nothing here was run on the host, pushed, bound or signed. No docker exists on the workstation: every
command shape below ran on the emulation of the frozen core (`core/tests/hostemu.py`, extended by subclassing in
`tests/k6b.py`) and nowhere else, except the editor's own script, which ran for real under both interpreters against
real files (`tests/test_editor_native.py`). Hashes are in `SHA256SUMS`, taken by command.

Abbreviations. `MNT` = `c3po/deployment/capacity-mount/README.md` at dd4ec4bb (S/opsart copy, byte-identical to the
release tree, sha256 `1acd72b1…474b`). `CHK` = its `check_compose_render.py` (`a2b468cd…f5e`). `K6a` =
`W/hostops02-sealed/activate` (seal `91366f44…ad`, source `cc054389…5c44`). `PLAN` = MASTER_PLAN rev 2. `A2` = the
five-session authority draft rev 3. `C-13` = the Codex line accepted 04/10 ("every later compose command … uses K6a's
file list and compares the override with the hash in M3's receipt first"). `CORE` = the frozen core, generation
`4c24c5cf…d0d6`, seal `73fb546b…c9b1` (copied byte for byte to `../core`, verified by `shasum -c`).

Contents: 1 what it does · 2 why an editor container · 3 what the owner signs · 4 refusals · 5 effects, readback,
partials · 6 the 60 seconds · 7 crash points · 8 command shapes: proven and UNPROVEN · 9 deviations from the core's
rules · 10 open questions for Codex · 11 how it was tested · 12 what was not built.

---

## 1. What it does

One source, four signed modes, one request per mode and per use. `WRITES_ALLOWED=True`, `ACTIVATION_ALLOWED=False`
(no systemd unit; a compose recreate is not an activation, CORE 8.2), `DATE_CLASS='WRITE_SESSIONS'` (2026-10-05 to
2026-10-10 UTC), gate at most 900 s. Parts: core, runner, docker, parents, files (umask and constants only: nothing
is created), lock — K6a's set.

| Mode | MNT | Plan row | Block before → after | A2 band (BRT / UTC) |
|---|---|---|---|---|
| `MOUNT` | step 1 | B4 | none → `MOUNT_SOURCE` | Mon–Thu 17:38–20:30 (20:38–23:30Z), market closed, never between M2p and M3r-2 |
| `ENABLE` | step 3 | M4 | `MOUNT_SOURCE` → all five | same band, after B4c (PROBE LOAD) |
| `DISABLE_FAST` | Disable, fast | C4 | all five → all but `REQUIRED` | Mon–Fri 05:00–20:30 (08:00–23:30Z), when the worker loops |
| `DISABLE_FULL` | Disable, full | X2 | any of {mount; mount+3; all five} → none | Fri 17:38–18:58 (20:38–21:58Z) |

"The block" is the trailing block of capacity lines of the host `.env`, in this fixed order:

```
C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE=<tree host path>            (compose interpolation only, compose.yml:169)
C3PO_R2D2_V2_CAPACITY_CONFIG_FILE=/c3po-capacity/config/<name>
C3PO_R2D2_V2_CAPACITY_CONFIG_SHA=<sha256 of the static config>
C3PO_R2D2_V2_CAPACITY_VETO_MODE=DISPATCH_AND_DERIVATION_ONLY
C3PO_R2D2_V2_CAPACITY_REQUIRED=true                            (last: the fast disable cuts exactly this line)
```

Every value follows from a signed member or is a constant (`capacity_values`). The order is ours: MNT appends the four
settings with `REQUIRED` first; putting it last makes the fast disable a cut of the last line, and every edit of this
source an append to the end or a cut of the end (section 2).

Effects, all under the deployment lock, in this order:

| # | Effect | How |
|---|---|---|
| E1 | the edit of `.env`: append the lines the mode adds, or cut the lines it removes | ONE attached container of the signed backend image (`edit_env` row, class QUICK 8 s): `run --rm -i --pull never --init --user 1000:1000 --network none --read-only --cap-drop ALL --security-opt no-new-privileges --mount type=bind,source=<deploy>/.env,target=/c3po-env/.env <image ID> python -I -B -`, `--name hostops02-k6b-<go16>` (so that a container that outlives its killed CLI is found by name), the pinned editor script plus one line with the signed spec on standard input |
| E1′ | its own signed effect (`effects.withdrawal`, plan member `withdrawal_authorized`): only if authorized, only when the run stops BEFORE the recreate was started, after an E1 the editor confirmed (exit 0, `ENV_EDIT_DONE`) and the host read back, and only while the lock file is still the one held: the inverse edit, by the same row, under the name `…-withdraw`, with one signed stdin hash per possible block found. Never after the recreate was started, whatever it did (no inferred rollback) | MNT step 1: "If config or the check fails, nothing was recreated. Delete the line appended above" |
| E2 | ONE recreate of `r2d2-worker` | K6a's row word for word: `docker compose --project-name c3po --env-file <deploy>/.env -f <deploy>/c3po/compose.yml -f <override of M3> up -d --no-deps --no-build --pull never --force-recreate r2d2-worker`, `C3PO_BUILD_SHA=<revision>` |

Between E1 and E2: the render from the files (K6a's `render_files` row, same file list) must give the worker the mount,
the capacity names of the block after, K6a's four names and the build revision (`service_of`), and must pass CHK's rule
(`render_errors`, ported; equivalence to CHK's own `check()` on 32 renders is a test). The capacity tree is read for
MOUNT and ENABLE (four root:root 0700 directories, the static config root:root 0600 with the signed hash) and never
written. Nothing else: no `docker exec`, no shell, no systemctl, no pull, no build, no second recreate.

## 2. Why an editor container, and what it may do

The frozen core has no primitive that changes an existing file (CORE 6.5: exclusive creation only; rule 4: "nothing
that exists is overwritten"), and K6b's whole purpose is to change `.env` (PLAN row B4 kind ENV; MNT). A new core
generation was ruled out. What remains inside the core is an `EFFECT` container run (`container_effect`, CORE 6.3), as
K2a used for the catalog. Choices:

- **As the owner of `.env`, never as root.** MNT: "Run … as the owner of `.env`, never with `sudo` on `.env`" (a root
  `sed -i` replaces the file with a root-owned one). A container of uid 0 with `--cap-drop ALL` could not write a
  0600 file of uid 1000 anyway (no `CAP_DAC_OVERRIDE`). The row's prefix is the core's `RUN_PREFIX` with the user
  alone changed to `1000:1000` (pinned by a test); the precheck refuses unless `.env` is uid 1000, gid 1000, 0600, one
  link (`ENV_FILE_NOT_EDITABLE_BY_THE_EDITOR`). **Assumption to confirm from a receipt:** the deploy account is
  1000:1000 and `.env` is 0600 (hostemu's world says so; MNT step 1 prints it with `stat -c '%U:%G %a'`).
- **In place, same inode.** The script opens `/c3po-env/.env` `O_RDWR|O_NOFOLLOW`, checks regular, one link, owner,
  mode and size ≤ 1 MiB, reads it, computes the new bytes by the rule below, checks again right before writing that
  size, mtime, inode and bytes are those it read (`ENV_FILE_CHANGED_DURING_THE_EDIT`, tested natively with another
  writer injected between the read and the write), and either writes the appended bytes at
  the old end with one `pwrite` (a short write is cut back and reported `ENV_SHORT_WRITE_WITHDRAWN`) or makes one
  `ftruncate` (a cut is one system call: the file is either before or after), then `fsync`. The host-side readback
  (section 5) is the verification.
  Owner, group, mode and inode never change (tests on real files).
- **The rule (the same in the script, in `edited_env()` and in the emulation; a differential test runs all three on
  22 cases):** the file is empty or ends with a newline; every line that compose's dotenv parser could read as a
  capacity setting (`[ \t]*(export[ \t]+)?C3PO_R2D2_V2_CAPACITY_…`) is among the trailing lines; that trailing block
  is exactly one of the signed "before" blocks; the result is the rest of the file unchanged plus the signed "after"
  block; the result must be an append or a cut. Anything else is a refusal with nothing written. A commented line is
  not a setting.
- **Nothing of `.env` leaves.** The spec on the editor's standard input holds the signed blocks, the owner and the
  mode — no hash, size or byte of the file. The editor prints one line `{status, code}` with constant codes. The
  source reads `.env` into memory before, under the lock and after each editor run, and compares bytes and identity
  there; no value, digest or size of it reaches a receipt, an argv or a log (a test searches the receipts and every
  argv for the file's hashes, sizes and the canary).
- **A file bind, not a directory.** Only `.env` is writable in the container; the deploy tree is not bound. The core's
  note "bind only directories the run has walked and holds pinned" is about sockets; here a file bind is the narrower
  choice. The run proves before (walk, under the lock) and after (same device and inode) that the file the path names
  is the one it read.

## 3. What the owner signs

`PLAN_KEYS`, every member in the signed request; the authority and the GO carry `effects_of(plan)` literally (a test
pins it member by member for each mode).

| Member | Content | Comes from |
|---|---|---|
| `mode` | `MOUNT`, `ENABLE`, `DISABLE_FAST`, `DISABLE_FULL` | the row of A2 |
| `data_root` | the data volume root (open root of the override's chain; the worker's data bind source) | M3's receipt |
| `capacity` | `{root: rows from '/' of the tree, root-owned all the way, config_name, config_sha256}` | E2's provisioning receipt or PROBE's receipt (rows); B5 (name, hash) |
| `override` | `{directory: rows of K6a's live directory, name, environment: the four values}`; the override's bytes, hash and size are DERIVED (K6a's `override_of`, byte for byte: a test builds K6a's own fixture and compares) | M3's receipt (`effects.files[OVERRIDE]`, `effects.recreate.environment`, `chains.LIVE_PARENT` + `directories[0]`) |
| `worker` | `{image_id}` | M3's receipt |
| `compose` | `{project, env_file, files}`: exactly the deploy layout (`<deploy>/.env`, `<deploy>/<project>/compose.yml`); the override is appended by the source | as K6a |
| `deploy_directory`, `lock` | rows; `{directory rows of <deploy>/runtime/security, wait_seconds ≤ 20}` | M3's receipt `chains` |
| `probe_load_receipt_sha256` | ENABLE: the hash of the PROBE LOAD receipt (B4c) after the mount; null otherwise | PROBE |
| `evidence_boot_id_sha256` | the boot of every row above | the same receipts |

`EVIDENCE_OPERATIONS=('GO_WRITE_HOSTOPS02_ACTIVATE_01',)`: the request must cite M3's receipt (C-13). The code cannot
read a receipt: that the rows, the four values and the override path were copied from it, and that the PROBE LOAD
receipt named for ENABLE is KNOWN_COMPLETE, after B4 and of the same boot, is the binder's check and the co-auditor's.

## 4. Refusals (nothing changed in any of them)

**From the bytes** (`validate_plan`, run by the dispatcher before any claim): `MODE_INVALID`, `EVIDENCE_BOOT_UNBOUND`,
`PATH_INVALID`, `CAPACITY_REQUEST_INVALID`, chain codes (the tree root-owned from `/`, not writable by group or other),
`OVERRIDE_REQUEST_INVALID`, `OVERRIDE_OUTSIDE_DATA_ROOT`, `WORKER_REQUEST_INVALID`, `COMPOSE_REQUEST_INVALID`,
`COMPOSE_PROJECT`/`COMPOSE_FILES`, `COMPOSE_NOT_THE_DEPLOY_LAYOUT`, `PATHS_OVERLAP`, `CAPACITY_TREE_PLACEMENT` (the tree
must lie neither in the data volume — three services reach it read-write there, MNT — nor in the deploy tree — the
next rsync deletes it), `LOCK_REQUEST_INVALID`, `LOCK_NOT_THE_DEPLOYMENT_LOCK`, `LOAD_EVIDENCE_INVALID`,
`ENVIRONMENT_EXPECTATION`, `MOUNT_INVALID`. One test per code (`tests/test_plan.py`).

**On the host, before the first effect** (`phase_reached: PRECHECK`), in order: executor 0:0, umask, boot; deploy tree
walked and held; `.deploy-version`; `.env` (absent, not regular, not 1000:1000 0600 one link, not newline-terminated,
capacity lines not trailing, block not one of the signed ones); the project directory and `compose.yml`; the override
directory walked and held, the override root:root 0600 one link with exactly the derived bytes; MOUNT/ENABLE: the
tree walked and held, `config documents go payload` root:root 0700 on its device, the static config root:root 0600 one
link with the signed hash; the lock directory and file; the worker by name on the signed image, the image's revision
label; its environment (booleans: the four of K6a, the build revision, the five capacity names) and its mounts
(`{{json .Mounts}}`): for MOUNT/ENABLE it must run and be exactly in the state the file's block says, for the disables
this is reported, not judged (they must work on a looping worker, MNT); the render from the files as the block says,
its image resolving to the signed ID; the budget (`BUDGET_CANNOT_HOLD_BOTH_EFFECTS`); the lock (`DEPLOY_LOCK_BUSY`,
`LOCK_NOT_TAKEN_BUDGET`); under it: the lock file still named, no reboot marker, the project, override and lock
directories (and the tree) still reached by name, `.deploy-version`, `.env` (bytes and signature), `compose.yml`, the
override unchanged since the first look, the worker unchanged (MOUNT/ENABLE: ID, start, restarts, running; disables:
ID), the container list consistent, no leftover `<x>_c3po-r2d2-worker-1` (K6a's rule), and the time
(`BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT`). One test per code (`tests/test_precheck.py`, 132 tests).

**At the first effect:** the editor not started, or refusing with the file unchanged (its own code, e.g.
`ENV_CAPACITY_LINES_NOT_TRAILING` when something appended a line after the precheck): REFUSED, `mutating_calls` 1
issued, 1 failed.

## 5. Effects, readback, and what a partial says

1. E1, then `.env` read on the host: the expected bytes on the same object, with the editor's line `ENV_EDIT_DONE` and
   exit 0, settles it as done; the bytes before on the same object as failed (nothing changed); anything else, or an
   unreadable file, as unknown. An editor that did not return (timeout) is unknown whatever is read: its container
   may still run (CORE U10).
2. Under the lock: the lock file still named; the render from the edited files must be the block after (and the same
   image). If not: E1′, settled the same way, and the run ends without a recreate.
3. Right before E2: the project, override and lock directories still reached by name.
4. E2 (only if 34 s are left, core rule), then K6a's readback, each fact on its own: the worker by name, its
   environment, its mounts, every container, `.env` as edited (bytes and identity), `compose.yml` and the override
   unchanged, the lock, the 3 s pause, the second reading.

**KNOWN_COMPLETE** (`CAPACITY_SWITCH_APPLIED_WORKER_RECREATED_AND_VERIFIED`): the recreate returned 0; one container
under the name, new, the old one gone; running, restart count 0, signed image, read twice 3 s apart with the same start;
environment: the names of the block after present and equal, the others absent, K6a's four and the build revision
present and equal; mounts: `/c3po-capacity` the read-only bind of the signed tree (blocks with the mount line) or the
placeholder volume `c3po_c3po_capacity_unprovisioned` (none), and the data root still bound read-write; every other
container as under the lock; `.env` as edited; `compose.yml` and the override unchanged; the lock still the one held.

| Outcome | When | `.env` (`env_file_after`) | Worker |
|---|---|---|---|
| `REFUSED_NOTHING_CHANGED` | precheck, or editor not started, or the editor said `ENV_EDIT_REFUSED` and the file read through the path is unchanged | `UNCHANGED` | untouched |
| `PARTIAL_ENV_EDIT_WITHDRAWN_RECREATE_NOT_STARTED` | `failure_phase` `BEFORE_THE_RECREATE`: a stop after a confirmed edit, before the recreate was started (render after the edit not as signed or over its allowance, a name swapped, the recreate not started), the withdrawal authorized, run and verified | `RESTORED` (bytes and inode as before) | untouched, never asked |
| `PARTIAL_ENV_FILE_EDITED_RECREATE_NOT_STARTED` | `failure_phase` `BEFORE_THE_RECREATE`, no withdrawal: not authorized, the edit not confirmed by the editor, the lock no longer the one held, no time left, or the withdrawal not started or refused with the file still as edited | `EDITED` | untouched, never asked |
| `PARTIAL_ENV_FILE_EDITED_RECREATE_FAILED_WORKER_UNCHANGED` | `failure_phase` `AFTER_THE_RECREATE_STARTED`: the recreate ran and a readback proved the worker the same container, as it was, in an unchanged listing. No withdrawal: no rollback is inferred from a recreate that ran | `EDITED` | proved unchanged (`worker_container_replaced: false`) |
| `PARTIAL_WORKER_RECREATED_NOT_FULLY_VERIFIED` | a new worker, a criterion false or unread | `EDITED` | replaced |
| `PARTIAL_UNCERTAIN_REQUIRES_READBACK` | the editor or the withdrawal did not return or left other bytes; or the recreate is uncertain | `UNKNOWN` or as read | `null` when unknown |
| `PARTIAL_REQUIRES_RECONCILIATION` | the run escaped | — | — |

`PARTIAL_ENV_FILE_EDITED_WORKER_NOT_RECREATED` matters: the new `.env` takes effect at the next recreate of ANY backend
service by anyone (MNT: the next plain `up -d` recreates five). For MOUNT that is the mount only (MNT: no effect
without the flag); for ENABLE it is capacity on at the next recreate; for a disable it is the disable at the next
recreate. After the review it is reached only when the withdrawal could not run or did nothing. Nothing is rolled back beyond E1′; a second request of the same mode is then refused from the file
(`ENV_CAPACITY_BLOCK_NOT_AS_SIGNED`), so the way forward is a request of the next mode, or a recreate request — not
built (section 12).

## 6. The 60 seconds

```
needed  = edit class 8 + recreate class 30 + reserve 4 + render allowance + files 1 + settle 3      (= 49 with a fast render)
render allowance = twice the first render, rounded up, at least 3, at most 15
kept while waiting for the lock = needed + 2;  refused before the lock if needed + 2 >= 60
```

Measured on THIS host by M2p (K11 PRE, 2026-10-04 15:26Z receipt, `items.*.elapsed_ms`): render 192 ms, container
inspect 19–23 ms, image inspect 43 ms, `ps` 50 ms, a container importing the app 2.4 s. With those, about 59.5 s are
left when the lock is asked for and the wait can last about 8 s (K6a: about 17 s): **K6b refuses on a lock held more
than about 8 s**, nothing changed. A first render of 3.3 s or more makes every request refuse
(`LOCK_NOT_TAKEN_BUDGET`; 6 s or more: `BUDGET_CANNOT_HOLD_BOTH_EFFECTS`). Figures in `tests/test_budget.py`
(emulated): Monday-like reads, renders 2 s, editor 2 s, recreate 23 s: complete in 35.9 s; recreate 30 s: complete,
pause taken; lock held throughout: refused after about 3 s of wait with 2 s renders, about 9 s with instant ones; a
render after the edit that takes more than its allowance (1 s over is enough): `RENDER_AFTER_EDIT_OVER_ITS_ALLOWANCE`, the
edit withdrawn (`PARTIAL_ENV_EDIT_WITHDRAWN_WORKER_NOT_RECREATED`); 40 s over: no time for the withdrawal either, the edit
stays and the receipt says so. The render allowance is an estimate (twice the first render), not the class (15 s) that
core rule 4.2 asks for: with the class the run could never fit (8 + 30 + 4 + 15 + 4 = 61 s); deviation 9. The editor itself (no app import, standard library only) should take
well under its 8 s class; never measured.

## 7. Crash points

A death at every host call of a complete run, for each mode (`test_death_at_every_host_call…`: 343 host calls for MOUNT and ENABLE, 306 for the
disables): the host is in one of three states, in order — S0 nothing; S1 `.env` edited, worker old; S2 `.env` edited,
worker new — and the last-resort receipt never contradicts it. The in-between states of an interrupted recreate are
K6a's section 6, unchanged (same row, same engine): a later read must apply K6a's rule; a recreate that leaves no
running worker is not repaired here (K6a decision 17). A death inside E1 cannot leave a torn file on Linux: the append
is one `pwrite` of at most a few hundred bytes and the cut one `ftruncate`; a crash of the machine between `pwrite`
and `fsync` can lose the append (the file is then as before).

## 8. Command shapes: proven and UNPROVEN

| Row | Ran on the host? |
|---|---|
| `image`, `container`, `container_list`, `container_environment` | K6a's rows byte for byte; the first three ran (post-deploy readback, K11); the environment template's construction is K6a's UA-3 |
| `container_mounts` (`container inspect --format '{{json .Mounts}}'`) | **UNPROVEN (UB-1)**: a new fixed template; `.Mounts` is documented docker output; its JSON members `Type Name Source Destination RW` are read; never run by this family |
| `render_files` | K6a's row; renders ran on this host (M2p, 192 ms). **UNPROVEN (UB-2)**: the render of the worker's `/c3po-capacity` volume as a bind with `read_only: true` when `.env` sets the mount, and that env_file values appear in `services.<name>.environment` (MNT says the render "carries the .env values"; CHK's fixtures were read from the compose source, MNT "Not verified") |
| `edit_env` | **UNPROVEN (UB-3)**: `--user 1000:1000` and a FILE bind under `--read-only` never ran anywhere. Precedent: A6 and A9 (K2a) ran `RUN_PREFIX` with a read-write DIRECTORY bind and stdin on this host, KNOWN_COMPLETE (`once-a6-20261003-a`, `once-a9-20261003-a`). That uid 1000 inside equals uid 1000 on the host needs no user-namespace remapping (W1 reads `docker info`) |
| `recreate` | K6a's row word for word. Its first execution on this host is M3 (Monday 05:45–06:00); K6b runs it again only after M3 |

UB-4: `compose up --force-recreate` of a worker in a restart loop (the disables' case) is MNT "never exercised".
UB-5: after ENABLE the worker runs the fatal capacity checks at start-up; two readings 3 s apart may not catch a loop
that starts later. MNT asks for status and restart count twice 60 s apart: that is a later read (W1 bytes, M3r-like),
not this run. UB-6: the Linux job (section 12).

## 9. Deviations from the core's rules and from the brief

1. **Rule 4 is NOT preserved** (CORE rule 4, "nothing that exists is overwritten"): `.env` is changed in place, through an
   `EFFECT` container, append or cut of the trailing capacity block only, every other byte compared. Since revision 2
   this is the exact exception of K6b's own core generation (`../core-k6b`, `IN_PLACE_EDIT_EXCEPTION`, CORE.md §14),
   enforced by its assembler for this row of this source only; no other source may run a container as any user but 0:0.
2. **An `EFFECT` run whose user is not root and whose bind is a file**: the row is in the signed scope; the assembler
   accepts it (rule 5 judges `run --rm`, `--pull never`, no `-v/--mount/--device/--cap-add/--privileged/-d`).
3. **A second editor run (E1′)** that undoes the run's own E1, from the bytes this run wrote, as MNT prescribes. The
   core's analogue is the removal of the run's own temporary.
4. **The `files` part is carried and unused** except `umask`, `FILE_NAME`, `FILES_SCOPE`: the parts list is K6a's.
5. **The ENABLE evidence of the load check** is a plan member (`probe_load_receipt_sha256`), not an
   `EVIDENCE_OPERATIONS` entry, because that constant is per source and the other three modes must not require it.
6. **The order of the block** differs from MNT's (REQUIRED last), so the fast disable is a cut.
7. **K6b runs only after M3.** "The same file list as K6a, override included" needs the override M3 delivers; a MOUNT
   on Sunday (PLAN row B4) is not possible with these bytes. A2 already places B4 on Monday evening and later.
8. **No `linux_root/` job and no native-call test** (section 12): K6a has both.
9. **The render allowance is twice the first render, not the render class** (core rule 4.2): a slower render after the
   edit is a failure that withdraws the edit, never a late recreate.
10. **The disables do not judge what MOUNT and ENABLE refuse on** (deployed revision, override, worker image, image
    label, the render's activation names and image): they report them (`precheck.findings`) so that a pre-signed
    disable still runs in the loops MNT names.

## 10. Open questions for Codex

0. **Decision 6 — not met, open item.** Every bind source and all its ancestors must be root-controlled. The editor's
   bind source is `<deploy>/.env`. As read on this host by M2p (K11 PRE, `GO_READONLY_HOSTOPS02_EPOCH_READBACK_01`,
   `W/once-m2p-20261004-a`, receipt 2026-10-04 15:26Z, rows and `items.deploy_files.compose_inputs[0]`):
   `/` 0:0 0755 · `/opt` 0:0 0755 · **`/opt/chief-of-staff-digital` 1000:1000 0775** (owned by the operational
   account, group-writable) · **`.env` 1000:1000 0600, one link** (owned by the editor's account by design: the edit
   runs as its owner, decision 1). The W1/L/E/A receipts in `W/once-*` print only `/` of that chain. So a non-root
   ancestor exists and the file itself is not root's. K6b reports it (`effects.bind_source_chain`, `all_root_controlled:
   false`; `precheck.bind_source_root_controlled`, read from the walked rows) and does not refuse on it. What would close
   it is a decision, not code here: accept for this one row, or move the edit elsewhere (e.g. a root-owned copy the
   compose project reads), which changes the deploy layout.

1. Rule 4: is an in-place append/cut of `.env` by an `EFFECT` container, with the trailing-block discipline and the
   in-memory comparison, acceptable inside the frozen core, or does it need a new generation (an edit primitive)?
2. The editor as `1000:1000` (constant in the row) and the precheck that `.env` is 1000:1000 0600: confirm the deploy
   account's ids from a receipt (W1 or K11 do not print the owner of `.env` as far as read here).
3. The withdrawal E1′ after every stop following a verified edit while the worker is untouched (MNT's runbook, broadened after the review): keep it, or stop with the file edited?
4. The capacity lines of the block in K6b's order (REQUIRED last) instead of MNT's: acceptable?
5. The fast disable "pre-signed with the enable" (PLAN C#1): a GO window is at most 900 s on one UTC day, so one
   pre-signed request covers one window. How many C4 requests are bound with the M4 request, and for which windows?
6. ENABLE's load-check evidence as a plan member, checked by the binder: acceptable, or should ENABLE be its own source
   with `EVIDENCE_OPERATIONS` naming PROBE?
7. Rows: the live directory's chain comes from M3's receipt (`chains.LIVE_PARENT` + `directories[0]`), the deploy and
   lock chains from the same receipt, the tree's chain from E2's or PROBE's receipt; one `evidence_boot_id_sha256`
   for all. Confirm the binder may assemble a chain from M3's receipt this way.
8. The lock wait ceiling of about 8 s (section 6) against K6a's 17 s.
9. After ENABLE: who reads the worker twice 60 s apart (MNT), and under which GO (a W1 read in the A2 grid)?
10. `PARTIAL_ENV_FILE_EDITED_WORKER_NOT_RECREATED` leaves `.env` ahead of the worker (section 5): accept, or require a
    recreate-only request (not built)?

## 11. How it was tested

| File | What |
|---|---|
| `tests/test_conformance.py` | the core's 121 conformance tests, twice: mode MOUNT and mode DISABLE_FAST (242) |
| `tests/test_capacity_switch.py` | each mode complete: the exact bytes of `.env`, the worker's names and mounts, the exact commands and their order, the editor's spec, no value or digest of `.env` anywhere; the week on one host; disables on a looping worker |
| `tests/test_plan.py` | every refusal from the bytes; every member bound into the effects; `effects_of` pinned literally for each mode; the scope |
| `tests/test_precheck.py` | the host refusals, each with nothing changed; the findings a disable reports instead |
| `tests/test_effects.py` | every way after the precheck: editor not started / refusing / lying / hanging before and after / replacing the file; render after the edit not as signed (withdrawal verified, failed, not started, hanging, other bytes); names swapped before the recreate; recreate not started / failing / timing out; each criterion broken alone; readbacks unavailable; death at every host call, four modes |
| `tests/test_budget.py` | the 60 seconds in figures |
| `tests/test_editor_native.py` | the editor's real script under this interpreter on real files: the same rule as the source and the emulation (22 cases), refusals (mode, links, owner, symlink, absent, directory, fifo, size), a week on one file, the withdrawal |
| `tests/test_static_sources.py` | compose.yml, config.py, MNT and CHK at dd4ec4bb (CHK's own `check()` against ours on 32 renders); K6a's constants, rows and override bytes (K6a's own fixture) |

Revision 2: 550 tests, all passing on Python 3.9.6 and 3.12.14 (with `HOSTOPS02_TEST_RELEASE_TREE` set; without it the
static tests of the release skip), taken from the command output on 2026-10-05 about 01:25Z. Mutation of revision 2:
349 mutants, 349 killed, 0 survivors, 0 errors, none by the time limit, on both interpreters (the records in
`mutation/`). The figures below are those of revision 1 (544 tests, 328 mutants), kept for the history.

Mutation (`mutation/mutants.py`, harness `mutation/mutate.py`, K6a's with its three tables changed and a screening mode
that is never a record): 328 mutants — every operand of every `need()` of the operation's part (generated from its syntax
tree), and by hand every member of `effects_of()`, each constant, the editor's prefix and script, each rule of the
edit, each read, each settlement, each criterion, each outcome, each budget term and each change made after the
review. Result on both interpreters: 328 killed, 0 survivors, 0 errors, none by the time limit
(`mutation/MUTATION_RUN.json`, `mutation/MUTATION_RUN.py312.json`). History, as it happened: the first screens left 46
and then 18 survivors; each was answered by a test or by removing a check another check implies (section 13); two
survivors of the first complete run were tests deselected by the harness because their names or parameter ids
contained "static" (renamed); one mutant (K05) was removed from the list as equivalent, with the reason in the list.
This says the tests answer THIS list, nothing more. The core's inherited mutants were not run against this suite.

## 12. Not built (stated, not hidden)

- **The Linux job** (`linux_root/`): K6a's CI proved its argv on a real engine as root. K6b's three new shapes (UB-1,
  UB-2, UB-3) have no proof anywhere. PLAN: "To be proven in its CI job". Until then the first execution on the host is
  the proof, and a failure there is a refusal (UB-1, UB-2 before the lock) or, for UB-3, a refusal or an uncertain
  edit of `.env`.
- **The native-call test** (the source's own Native on a real tree, K6a's `test_native_calls.py`): the host-side calls
  of K6b are the core's read primitives and K6a's helpers, already exercised natively by K6a; the new piece that
  touches real files, the editor script, is tested natively.
- **The inherited mutants** of the core (K6a's `MUTATION_INHERITED.json`): the core's own record stands.
- **A recreate-only request** and the **reconciliation read** of K6a's section 6.

## 13. What changed after the independent review (2026-10-04, same day)

One adversarial pass by a reviewer who did not write this code (twelve findings, two reproduced on the fixture) and
the first mutation screens. Each change has a test; the payload bytes changed, every earlier hash of this candidate
is void.

| # | Finding | Change |
|---|---|---|
| 1 | the render's image reference resolved only before the lock: a tag moved during the wait recreated the worker onto another image | resolved again under the lock (`RENDER_IMAGE_CHANGED_BEFORE_THE_LOCK`); the static config is read again under the lock |
| 2 | a deploy tree swapped right before the editor: the editor edits the file at the path, the run read the old one and said REFUSED | the tree is proved by name as the last check before the editor, and again before each readback of the editor's result; a path that no longer leads there makes the call unknown (`UNREADABLE`), never a refusal |
| 3 | no withdrawal when the recreate never ran or provably changed nothing: an ENABLE left `REQUIRED=true` for the next recreate by anyone | the withdrawal now follows every stop after a verified edit while the worker is proved untouched and the lock still held |
| 4 | pre-signed disables refused in the README's own loop cases (another package or release sha, a rotated image) | for DISABLE_FAST and DISABLE_FULL: deployed revision, override, worker image, the image's revision label, the render's activation names and image are reported in `precheck.findings`, not judged; the file's block, the editor's image by ID, the lock, the names and the budget still refuse |
| 5 | an editor whose CLI is killed can go on writing after the receipt | the editor runs under a name derived from the GO; the precheck refuses if the name is taken; after an editor that did not return the receipt says whether that name is still listed (`container_left`) |
| 6 | the render allowance is an estimate (core rule 4.2) | kept, stated here as a deviation, and a render after the edit that takes longer than its allowance is a failure (`RENDER_AFTER_EDIT_OVER_ITS_ALLOWANCE`): the edit is withdrawn instead of a late recreate |
| 7 | the editor could overwrite bytes another writer appended between its read and its write | re-check of size, mtime, inode and bytes right before the write |
| 8 | an unchanged file after an editor that did not say it refused was settled as "nothing changed" | only `ENV_EDIT_REFUSED` with the file unchanged is a failure; otherwise unknown (`env_file_after` `UNKNOWN`) |
| 9 | the withdrawal ran after `LOCK_FILE_REPLACED` | not after that code, and only while the lock file is still the one held |
| 10 | the scope statement claimed no value read from the engine reaches an argv | reworded: the render's image reference and the container IDs the engine prints go to docker inspect |
| 11 | the receipt says which signed block `.env` held (a count) | kept, stated in the scope as the one exception (it is a count of lines this source manages, not a value) |
| 12 | the withdrawal's input was not in the signed effects | `effects.withdrawal.stdin_sha256_by_block_found`, one hash per possible block |

Removed as redundant after the mutation screens (each implied by another check, named in the screen): the data root's
own spelling check (validate_chain judges it), `tree != '/'` and the config path's spelling (implied by the grammars),
the append-or-cut check in memory (the signed blocks are prefixes of one another), the identity comparisons between an
lstat and the descriptor read (the metadata judged is now the descriptor's own fstat), the project directory's
identity at open (proved by name under the lock), the editor's own readback (the host-side readback is the
verification).

## 14. Revision 2 (Codex decisions 1 and 6, #429 5985748037)

| Decision | Change |
|---|---|
| 1: own core generation, the exact exception in the contract, do not claim rule 4 | `../core-k6b`: the 2026-10-02 core with `IN_PLACE_EDIT_EXCEPTION` and the uid rule in `assemble.py` (parts byte-identical), CORE.md §14, new tests and mutants `A_X01`–`A_X10`; K6b's conftest, seal and mutation harness point at it; `effects.core_exception` says `rule_4_preserved: false` and names the generation; the scope statement says so |
| 1: the withdrawal its own explicitly signed effect | plan member `withdrawal_authorized` (bool, `WITHDRAWAL_REQUEST_INVALID`); `effects.withdrawal` carries `authorized`, the row, the container name, the stdin hash per possible block (none when not authorized), when and what |
| 1: failure before vs after the recreate, separate states, no inferred rollback | the withdrawal runs only if authorized, only before the recreate was started, only after an edit the editor confirmed (exit 0 and `ENV_EDIT_DONE`) and the host read back, only while the lock is the one held; three partial outcomes (section 5) and `failure_phase` (`BEFORE_THE_EDIT`, `BEFORE_THE_RECREATE`, `AFTER_THE_RECREATE_STARTED`) in every receipt that is not complete |
| 6: bind source and ancestors root-controlled | reported, not met: section 10 item 0 |

Superseded by revision 2: row 3 of section 13 (the withdrawal after every stop with the worker untouched, including a
recreate proved not to have changed anything) — the withdrawal is now limited as above; section 5 holds the states.

### Revision 2, second part: the owner's A2 amendment 1 rev 3 (#429 5986005646), accepted by Codex

The editor reads the bar-key line of `.env` (with the rest of the file) only transiently, in memory protected from core
dumps, and writes no byte it read back except where the file ends: no persistent copy, log, argv or output.
Enforced, as the token program does:

- **The source's own process** (it reads `.env` into memory to compare): `host.not_dumpable()` of the core (prctl
  `PR_SET_DUMPABLE` 0, read back 0 with `PR_GET_DUMPABLE`) is the FIRST host call, before the executor check, the boot,
  the deploy tree or `.env`; otherwise `PROCESS_DUMPABLE_NOT_DISABLED`, refused, nothing opened. `SCOPE.process`,
  `effects.process`, receipt `process.dumpable_disabled`.
- **The editor's process** (in the container): the script makes itself non-dumpable the same way, through ctypes
  (`CDLL(None).prctl(4,0)` then `prctl(3)` must answer 0), BEFORE it opens `/c3po-env/.env`; otherwise
  `EDITOR_DUMPABLE_NOT_DISABLED`, refused, the file never opened. Native tests run the real script with a stand-in prctl
  that refuses an open before both calls; on this workstation (macOS, no prctl) the unmodified script fails closed.
- **Byte-equal**: no byte of the file outside the trailing capacity block is ever written: an append writes after the
  last byte, a cut only shortens (one `pwrite` at the old end, or one `ftruncate`). The rest of the file is never
  rewritten, so it stays byte-equal by construction; the host re-reads and compares it in memory.
- **No copy, log, argv or output**: the spec on the editor's stdin holds signed values only; its one output line holds a
  status and a constant code; the receipt holds no value, digest or size of the file (tests search every receipt and argv).

UNPROVEN: prctl inside the backend image's Python under `--cap-drop ALL --security-opt no-new-privileges` (no capability is
needed to clear one's own dumpable flag; never run on an engine here).

### Paths

No sealed file names a workstation path or user: the static tests read the release tree from `HOSTOPS02_TEST_RELEASE_TREE`
only (skipped without it) and K6a from a path relative to this directory (`HOSTOPS02_TEST_K6A_DIRECTORY` overrides).
