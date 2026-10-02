# K2a — catalog initialisation of the bar journal (supervisor operation 4b): design

Offline work only. Nothing here was run on the host, pushed or bound. Built on the frozen HOSTOPS02 core, generation
`4c24c5cf…d0d6` (seal `c13ce685…2f9f`), which this operation does not modify. Status: built by its author, reviewed
twice on 2026-10-02 (one review of the host side, one of purity and authentication), and repaired by its author after
those reviews (section 13 says what each finding changed). The repaired bytes have been read by nobody but their
author; the Linux job has never run.

Abbreviations. `README:n` = line n of `c3po/deployment/massive-supervisor/README.md` at dd4ec4bb (sha256 `644c6211…61c5`).
`APP/<file>:n` = `c3po/backend/app/<file>` at dd4ec4bb. `CORE/<file>:n` = `hostops02/core/<file>`. `PLAN` = the master
plan, revision 2. `SCOUT` = `scout-supervisor.md`. `op.py` = this operation's own part (functions are named, not
numbered: the lines moved with the repair). `F1`…`F13` = the findings of the two reviews, in the order of section 13.

## 1. What it is

One source, `catalog_init.py`, operation `GO_WRITE_HOSTOPS02_CATALOG_INIT_01`, writes allowed, activation not allowed,
date class `WRITE_WEEKEND` (2026-10-02, -03, -04 UTC: it ends Sunday 20:59:59 BRT; the plan's hard stop for A9 is
Sunday 19:00). Two signed modes run the **same bytes** (PLAN rows A6 and A9, §3.1 item 3):

| Mode | Journal root | Docker CLI configuration directory | Epoch string | Success outcome |
|---|---|---|---|---|
| `REAL` | the root operation 2 created, signed row by row with its identity: a leaf of `/var/lib/c3po-bar` that is not the state root (`/var/lib/c3po-bar/journal` under placement A) | the unit's own, `/etc/c3po-bar/docker-cli`, signed row by row, empty before and after | the constant `EPOCH_COMPILED` = `R2D2-V2-SHADOW-2026-10-05` (`APP/r2d2_v2_epoch_assembler.py:9`); a request cannot sign another | `CATALOG_READY_VERIFIED` |
| `REHEARSAL` | a throwaway directory **this run creates** (`mkdir`, 0700) in `/var/lib`: `/var/lib/c3po-bar-rehearsal-<label>`; the real root is only read | a second throwaway **this run creates** beside the first: `/var/lib/c3po-bar-rehearsal-<label>.docker-cli`; the unit's directory is only read and is given to no docker command | a signed string of the grammar `R2D2-V2-DIAG-[A-Za-z0-9_-]{1,80}` | `REHEARSAL_CATALOG_READY_VERIFIED` |

**Why the rehearsal creates its own root (the smallest honest design).** PLAN row A6 is "CR + WF" and CORE.md §11
gives K2a the files part "for the throwaway root of REHEARSAL". The alternative, a throwaway created by an earlier
hostops01 provisioning request, costs one more owner signature and one more dispatch, would have to end by Sunday
20:59, and would put a second leaf beside the real root in `/var/lib/c3po-bar`. The rehearsal also walks the **real**
root read-only and requires it to be what `REAL` will require (signed identity, root:root 0700, empty, same device as
`/var/lib`): what would refuse A9 is found at A6, where it costs a rehearsal signature and not the real one.

**Why the rehearsal gives docker a directory of its own (F1).** The first builds ran the three docker commands of a
rehearsal under the unit's real `/etc/c3po-bar/docker-cli`. They would have been the first docker commands ever run
under that directory on this host, and whether the CLI of the host writes anything into an empty `DOCKER_CONFIG` has
never been observed (K2A-U2). Had it written, the damage would have been done at A6, in production: nothing in either
family removes an entry there, every later run of these bytes refuses on it, and the gate readback reports
`DOCKER_CONFIG_NOT_EMPTY`. So a rehearsal now creates a second directory, root:root 0700 and empty like the unit's,
and every docker command of the rehearsal gets that one. What the CLI leaves there is found by the rehearsal (after
the two reads, and again after the run) and costs a throwaway. The first docker command under the unit's directory is
then the first read of A9, after the host itself has shown that this CLI leaves nothing. PLAN row A6 says "a failure
is a finding; production untouched": that is now a property of the bytes, tested for every ending of a rehearsal
(`tests/test_review_findings.py`, F1).

The price is the order of a rehearsal. The directory for docker must exist before the first docker command, so in
REHEARSAL the two reads come after the first `mkdir`, and what they find is a PARTIAL that leaves that one empty
directory instead of a refusal that leaves nothing. REAL is unchanged: its host calls are, call for call, those of
the bytes that were reviewed (121 calls of a complete run, compared by command before and after the repair).

**The layout floor (F8).** Which directory is a journal root is not left to the rows a request signs. The operation
part carries the layout of the reviewed family (hostops01 `parts/layout.py`) as constants, and they are in the signed
scope: the docker CLI configuration directory of both modes is `/etc/c3po-bar/docker-cli` and no other; a journal
root (REAL), and the real root a rehearsal reads, is a directory directly in `/var/lib/c3po-bar` and never
`/var/lib/c3po-bar/supervisor`; a rehearsal creates in `/var/lib` and nowhere else, so its throwaways are siblings of
the private parent and can never lie inside it, inside the configuration tree or inside the engine's. A request
bound to another directory is refused from its bytes, by the dispatcher, before any claim. A new leaf after a burnt
root (`/var/lib/c3po-bar/<new name>`, PLAN row C1) is a journal root; placement B (a leaf of the data volume) was
already impossible with these bytes, because every signed component must be root-owned.

The two success outcomes differ so that a rehearsal receipt can never be filed as the receipt of operation 4b; the
GO template therefore carries a null `success_criterion` (`SUCCESS_IN_TEMPLATE=False`) and the binder writes
`success_of(plan)`.

## 2. The command, and where each word comes from

README:336–339, verbatim:

```
DOCKER_CONFIG=<HOST_CONFIG_DIR>/docker-cli docker run --rm -i --pull never --init --user 0:0 --network none --read-only \
  --cap-drop ALL --security-opt no-new-privileges \
  --mount type=bind,source=<HOST_JOURNAL_ROOT>,target=<CONTAINER_JOURNAL_ROOT> \
  <IMAGE_ID> python -I -B - <CONTAINER_JOURNAL_ROOT> "$epoch" < catalog-init.py
```

| Piece | In this source | Evidence |
|---|---|---|
| `run --rm -i --pull never --init --user 0:0 --network none --read-only --cap-drop ALL --security-opt no-new-privileges` | the row `catalog_init` = `RUN_PREFIX`, class `RUN` (40 s, 65,536 bytes of output), kind `EFFECT`, standard input | `CORE/parts/docker.py:90–91`; README:336–337. **UNPROVEN on the host** (README:390, :593). On a GitHub runner the pipeline runs the unit's own `docker run --rm --init … --read-only --cap-drop ALL --security-opt no-new-privileges --mount type=bind…` by image ID with no network under `DOCKER_CONFIG=<empty dir>` (`.github/workflows/c3po-pipeline.yml:296–348` at dd4ec4bb): that is another argv (no `-i`, no standard input, three binds) and another engine |
| `--mount type=bind,source=S,target=T` | `run_arguments()` from the signed pair; one bind, read-write, no other mount | `CORE/parts/docker.py:99–120`; README:338, :342, :346 |
| `<IMAGE_ID>` | signed `image_id`, an ID never a reference; before the run `docker image inspect` must print that ID and the signed revision label | `CORE/parts/docker.py:10–18`; README:281 |
| `python -I -B - T "$epoch"` | `run_words()` | README:339, :345 |
| `< catalog-init.py` | the 1040 bytes carried in this source as `CATALOG_SCRIPT_B64`, sha256 `715d7a66…4bb7`, decoded and compared with the pinned hash in `validate_plan` (before any claim) and again in `perform` before the first gate; the request signs the same hash (`script_sha256`) | README:349–375 (the lines 353–373); `op.py`: `CATALOG_SCRIPT_B64`, `script_bytes()` |
| `DOCKER_CONFIG=…/docker-cli` | `docker_config=` of **every** docker command of the run (`docker_config_path()`): in REAL the signed directory of the unit, walked and held, root:root 0700, empty before, after the two reads and after the run; in REHEARSAL the directory the run created for it, held, root:root 0700, empty at the same three points | README:343, :97; the core's fixed environment has no `HOME`, and with `DOCKER_CONFIG` the CLI needs none |
| time limit | 40 s, then SIGKILL of the CLI's process group; the container is left to the engine | `CORE/parts/runner.py:10`, `:81–87`; PLAN K2a; SCOUT §3.3 |

No `--name`: the README writes none (SCOUT §4.1 leaves it to the signatories). Consequence in §6.

The two reads: `docker image inspect --format IMAGE_FORMAT <ID>` (shape proven on the host by HOSTFACTS_01) and
`docker ps -a --no-trunc --format PS_FORMAT` (shape proven by the post-deploy readback of 02/10), both now under
`DOCKER_CONFIG`, which is **UNPROVEN on the host** and which the rehearsal proves under a directory of its own. No precedent payload of this host ever ran `docker run`:
`release-install.py` and the activation of 28/09 used `docker inspect`, `docker exec` and `docker compose`.

## 3. Effects in order

`perform`. P = precheck (nothing has changed, a failure is a REFUSED receipt), E = effect, R = readback.

**Mode REAL** (nothing is created by this process; the host calls are those of the reviewed bytes):

| # | Step | Failure |
|---|---|---|
| 0 | pure: decode the script and compare its hash; first `gate()` | escapes before `started`: REFUSED |
| P1 | effective uid and gid are 0 | `EXECUTOR_IDENTITY` |
| P2 | `umask(0o077)` (process state only) | — |
| P3 | boot identifier hash equals `evidence_boot_id_sha256` | `EVIDENCE_FROM_EARLIER_BOOT` |
| P4 | the unit's docker CLI configuration directory: walked from `/` by `dir_fd`, `O_NOFOLLOW`, held; equals its signed rows (device, inode, owner, group, mode); **zero entries** | `PARENT_MISSING`, `PARENT_SYMLINK_COMPONENT`, `PARENT_NOT_DIRECTORY`, `PARENT_CHANGED_DURING_WALK`, `PARENT_IDENTITY_MISMATCH`, `DOCKER_CONFIG_DIRECTORY_NOT_EMPTY` |
| P5 | journal root: walked, held, equals its signed rows (identity, 0:0, 0700); **zero entries** | the `PARENT_*` codes; `JOURNAL_ROOT_NOT_EMPTY` |
| P6 | the first docker command (nothing of P1–P5 is found after one was started): `docker image inspect` by ID: the ID and the revision label are the signed ones | `IMAGE_ABSENT_OR_UNREADABLE`, `IMAGE_ID_MISMATCH`, `IMAGE_REVISION_MISMATCH`, `IMAGE_METADATA_INVALID`, `BINARY_UNAVAILABLE_OR_UNSAFE`, `COMMAND_TIMEOUT` |
| P7 | `docker ps -a`: the containers that exist before the run | `CONTAINER_LISTING_FAILED`, `CONTAINER_LIST_INVALID` |
| P8 | the last look: every held directory verified again from `/`; the root counted again | `PARENT_REPLACED`; `JOURNAL_ROOT_NOT_EMPTY` |
| P8c | **whatever P6–P8 ended in**, once a docker command was started: the configuration directory is counted again, and the count goes into the receipt (`precheck.docker_config_entries_after_the_reads`). Not empty, or not countable: the run is **not a refusal** (F10) | PARTIAL, root untouched: `DOCKER_CONFIG_DIRECTORY_NOT_EMPTY_AFTER_THE_READS`, `DOCKER_CONFIG_DIRECTORY_NOT_READ_AFTER_THE_READS`; the finding of P6–P8, if there was one, is kept as `precheck.first_finding` |
| P9 | the budget: `gate() >= 44 s`: the last refusal that costs nothing | `BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT` |
| E2 | `container_effect`: the one attached run, the script on standard input | not started (`COMMAND_NOT_STARTED`, `COMMAND_NOT_STARTED_BUDGET`, an expired gate): nothing ran: REFUSED, the root is untouched |
| R1–R4, S | as below | never refuses |

**Mode REHEARSAL** (two directories are created; the reads come after the first):

| # | Step | Failure |
|---|---|---|
| 0, P1–P3 | as REAL | as REAL |
| P4 | the unit's configuration directory, **read only**: walked, held, equals its signed rows, zero entries | as REAL P4 |
| P5b | the real journal root, **read only**: walked, held, equals its signed rows, zero entries. Then `/var/lib`: walked, held, equals its rows. Then the two paths this run will create are proved absent | the `PARENT_*` codes; `REFERENCE_ROOT_NOT_EMPTY`; `DESTINATION_PRESENT` (also when absence could not be established) |
| P5c | the docker binary is the trusted one (root-owned, not writable by others, on a root-owned way): no directory is created for a docker that cannot be started | `BINARY_UNAVAILABLE_OR_UNSAFE` |
| P9 | the budget: `gate() >= 46 s` | `BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT` |
| E0 | `create_directory`: the directory for docker, one `mkdir` 0700 by descriptor in the held `/var/lib`, opened, identity, owner, mode, device and emptiness proved, fsync of it and of the parent | before the `mkdir` succeeded: REFUSED (`DESTINATION_APPEARED_AFTER_PRECHECK`, `FILESYSTEM_*`, `GO_EXPIRED`, `PARENT_REPLACED`); after: PARTIAL (`CREATED_*`, `FSYNC_FAILED`), no docker command is started |
| P6–P8, P8c | the two reads and the last look of REAL, under the directory of E0, which is verified and counted like the others. **From here on a rehearsal cannot refuse**: every code of REAL's P6–P8 is a PARTIAL that leaves the one empty directory of E0 and has touched nothing of production; a call that fails is `READS_OS_ERROR` or `READS_FAILED` | PARTIAL, `root_verdict` `NOT_TO_BE_USED_AGAIN` (the throwaway name is spent) |
| E1 | `create_directory`: the throwaway root, as E0 | PARTIAL; the container is not started |
| E2 | the run, under the directory of E0 | not started: PARTIAL, the two empty directories exist (`COMMAND_NOT_STARTED`, `COMMAND_NOT_STARTED_BUDGET` when the reads took what was left) |
| R1–R4, S | as below | never refuses |

**Both modes, once the container was started:**

| # | Step |
|---|---|
| R1 | the printed line, parsed (pure) |
| R2 | the journal root read back through the descriptor held since P5/E1: names counted, the two catalog names `lstat`ed, `epoch.json` opened without following a link, required to be the file just `lstat`ed, read and compared, the root verified again from `/` |
| R3 | `docker ps -a` again: containers that were not there at P7, told apart by ID |
| R4 | the directory docker was given verified and counted again |
| S | settle: `state.done()` only for a verified run; otherwise `state.unknown()` |

**After E2 has started a process nothing refuses.** A run that returned is never settled as "failed, nothing
changed", even when the readback shows an empty root: the README applies its rule to refusals "that touched nothing"
as well, "so that nobody has to judge on the spot which kind it was" (README:386).

## 4. Verdicts

`COMPLETE` (exit 0) requires **all** of: the CLI returned 0; exactly one JSON line with exactly the six keys,
`status` `CATALOG_READY`, `created` true, `epoch` the signed string, `entries` `["epoch.json","maintenance.lock"]`,
`device` and `inode` integers (`script_line.as_signed`) equal to the root's identity as this process reads it on the host; the root holds exactly those
two names, each a regular file, 0:0, 0600, one link, on the root's device; `epoch.json` equals byte for byte the
canonical JSON of `{"schema":"MASSIVE_SESSION_ROOT_V1","epoch":…,"device":…,"inode":…}` with the host's identity of the
root; the root still is the directory held (identity, owner, mode, path from `/`); no container is listed that was
not there before; the configuration directory is still empty.

Codes after the container was started (`run_failure` and `catalog_failure`, in this order), all PARTIAL (exit 2):

| Code | Meaning | `root_verdict` |
|---|---|---|
| `COMMAND_TIMEOUT`, `COMMAND_OUTPUT_LIMIT`, `GO_EXPIRED`, `COMMAND_FAILED` | the CLI did not return; the container may still be running | `NOT_TO_BE_USED_AGAIN` |
| `ENGINE_COULD_NOT_RUN_THE_CONTAINER` | docker's own status 125, 126 or 127 **and** anything short of the signed line with a verified readback (the usual case: no line at all, the engine could not run the container) | `NOT_TO_BE_USED_AGAIN` |
| `SCRIPT_OUTPUT_NOT_ONE_LINE` | no line, several lines, not a JSON object (a container killed part-way) | `NOT_TO_BE_USED_AGAIN` |
| `SCRIPT_REFUSED` | a `CATALOG_REFUSED` line; `script_line.refusal_code` carries the script's code when it is a constant, `NOT_A_CONSTANT_CODE` otherwise (README:385) | `NOT_TO_BE_USED_AGAIN` |
| `SCRIPT_FAILED` | another non-zero status | `NOT_TO_BE_USED_AGAIN` |
| `SCRIPT_LINE_NOT_AS_SIGNED` | other keys, `created` not true, another epoch, other entries, identity not integers | `NOT_TO_BE_USED_AGAIN` |
| `CATALOG_IDENTITY_NOT_THE_HOSTS` | the device and inode the container saw are not the host's (README:388: "a finding to report") | `NOT_TO_BE_USED_AGAIN` |
| `CATALOG_READBACK_UNAVAILABLE` | the host readback could not be completed; `catalog.code` says why: `READBACK_OS_ERROR`, `READBACK_FAILED`, `GO_EXPIRED`, `PARENT_REPLACED`, `ENTRY_LIMIT`, `FILE_TOO_LARGE`, `FILE_CHANGED_DURING_READ` | `NOT_TO_BE_USED_AGAIN` |
| `CATALOG_READBACK_MISMATCH` | a third entry, a missing name, a symbolic link, another owner, mode or link count, other bytes in `epoch.json` | `NOT_TO_BE_USED_AGAIN` |
| `ENGINE_STATUS_AFTER_A_VERIFIED_CATALOG` | docker's own status 125, 126 or 127 **after** the script printed the signed line and the host readback verified the catalog (F2). `--rm` can turn a clean exit into 125 when the wait for the removal fails (README:444). The root holds the verified catalog; the status is the finding | `CATALOG_VERIFIED_WITH_FINDINGS` |
| `CONTAINER_LISTING_UNAVAILABLE_AFTER_RUN`, `CONTAINER_PRESENT_THAT_WAS_NOT_THERE_BEFORE` | the catalog is verified; whether a container of this run remains is not established, or a container exists that did not before | `CATALOG_VERIFIED_WITH_FINDINGS` |
| `DOCKER_CONFIG_READBACK_UNAVAILABLE`, `DOCKER_CONFIG_DIRECTORY_NOT_EMPTY_AFTER_RUN` | the catalog is verified; the directory docker was given (REAL: the unit's) is not provably empty any more | `CATALOG_VERIFIED_WITH_FINDINGS` |

A status other than 0 that is not one of docker's three (the script's own 1, a signal) stays `SCRIPT_FAILED` whatever
the line and the disk say: the script exits 0 after its line, so such a status is outside what it does.

Codes of a PARTIAL in which **no container was started**:

| Code | Mode | Meaning | `root_verdict` |
|---|---|---|---|
| `DOCKER_CONFIG_DIRECTORY_NOT_EMPTY_AFTER_THE_READS`, `DOCKER_CONFIG_DIRECTORY_NOT_READ_AFTER_THE_READS` | REAL | the unit's configuration directory holds an entry it did not hold before the two reads ran under it, or could not be counted after them. The journal root is untouched and usable. Nothing of this family empties that directory, and every later run refuses on it at P4 | `UNTOUCHED_NO_CONTAINER_STARTED` |
| the same two; every code of P6–P8; `READS_OS_ERROR`, `READS_FAILED`; `CREATED_*`, `FSYNC_FAILED`; `DESTINATION_APPEARED_AFTER_PRECHECK` and `FILESYSTEM_*` at the second directory; `COMMAND_NOT_STARTED*` | REHEARSAL | a finding of the rehearsal after its first directory existed; production is as it was; `directories` says what exists | `NOT_TO_BE_USED_AGAIN` (the throwaway name) |

`root_verdict` and `mode` exist only in receipts that `perform()` produced. There, a REFUSED receipt always carries
`UNTOUCHED_NO_CONTAINER_STARTED` and a complete one `CATALOG_READY_VERIFIED`. The receipts of the core's own envelope
carry neither member: phase `AUTHENTICATION`, phase `BEFORE_ANY_EFFECT`, the `ESCAPED` partial (outcome
`PARTIAL_STATE_UNKNOWN_ROOT_NOT_TO_BE_USED_AGAIN`, the core's last resort after the run was issued) and a receipt
reduced to the minimum. For those, status and outcome decide (F11).

**Reading a failed run (F3).** The core's runner discards the standard error of every command, so a receipt carries
no text of docker. `ENGINE_COULD_NOT_RUN_THE_CONTAINER` with `run.returncode` 125 and an empty `script_line`: the
engine refused the run itself (image, mount source, option, daemon); compare with the shape the Linux job ran
(`linux_root/catalog_shape.py`) and with the unit's smoke test of the pipeline, argument by argument. 126 or 127:
`python` could not be started in the image. `SCRIPT_REFUSED` with `script_line.refusal_code` `NOT_A_CONSTANT_CODE`:
the script printed Python's own message (README:385). The line is deterministic JSON,
`{"code": "<message>", "status": "CATALOG_REFUSED"}` and a newline, and the receipt has its size and SHA-256
(`script_line.bytes`, `script_line.sha256`): hash the candidates offline (`No module named 'app'`,
`No module named 'app.r2d2_v2_massive_sessions'`, the unpack message of README:385) and compare.

## 5. Crash points and how they are told apart

A death of the payload leaves no receipt: the transport files it UNCERTAIN and the signature is spent. What a later
read-only look finds tells the cases apart; the rule for the root follows the README (never a second run on a root
whose creating run did not end in `CATALOG_READY`).

| Death at | Host afterwards (REAL) | Told apart by | Root |
|---|---|---|---|
| P1–P9 | nothing changed; root empty; no container | empty root, the container set unchanged | untouched; but without a receipt nobody can tell it from the next row, so it is treated as that row |
| E2, after the CLI process exists, before the container wrote | root empty; a container may exist for a moment, or stay (state `created`, section 6) | empty root; possibly a container that was not there | not to be used again |
| E2, container between its two files | `maintenance.lock` only | one name | not to be used again (README:386) |
| E2, during or after `epoch.json` | both names; `epoch.json` complete or torn | two names; B3's catalog item cannot be signed without a 4b receipt | not to be used again unless the signatories decide otherwise on a read of the bytes |
| R1–R4 | whatever the container left; complete if it finished | as above | as above |

The script reaches the container whole or not at all: it is 1040 bytes, written in one `write` to a pipe and then
the pipe is closed (`CORE/parts/runner.py:61–72`); the interpreter in the container compiles standard input only at
end of file, so a payload that dies before the write gives the container an empty program, which exits 0 and touches
nothing. A payload that dies after the write does not stop the container: the docker CLI leads its own session and
is not killed by the death of its parent.

REHEARSAL adds states before these, all of them outside production: the directory for docker exists and is empty
(death after E0, or during the reads); both directories exist and are empty (death after E1). A new rehearsal needs a
new name (`DESTINATION_PRESENT` otherwise, for either of the two). The real root and the unit's configuration
directory are never written by a rehearsal, and the unit's directory is never given to one of its docker commands.

With a receipt: REFUSED means no directory was created, no container was started, and the directory docker was
given in the precheck (REAL) was counted empty after the reads or no docker command had been started; PARTIAL always
says in `run`, `script_line`, `catalog`, `containers`, `precheck` and `directories` what was seen.

## 6. A leftover container

The README argv has no `--name`, so a container cannot be attributed to this run by name. The run lists the
containers before (P7) and after (R3) with the proven `ps` shape and reports those that were not there (at most eight
rows: ID, name, state). When the CLI returned, `--rm` has removed the container, and a listed newcomer is either a
remnant or someone else's container; the run is then PARTIAL with the catalog verified. When the CLI was stopped by
the time limit the container may still be running and writing: PARTIAL, root not to be used again. Such a container
carries no compose label: while it **runs** the automatic security reboot answers `waiting_admission_coverage`
(README:508: the controller lists running containers), and nothing of this family removes it.

**How long such a container can live, and the state `created` (F5).** A container that was started cannot run long:
the script's longest wait is the 30 s wait for the catalog lock (`APP/r2d2_v2_massive_sessions.py:157–171`), which
cannot occur on an empty root, and `--rm` removes the container when it exits. So a container that outlived its CLI
is gone within seconds, unless the engine itself is stuck. A CLI killed **between create and start** leaves something
else: a container in state `created` that never runs. `--rm` acts on exit only, so it stays until someone removes
it. It does not hold the security reboot (it is not running), but it is a stray container for every later readback
of the container set (M0), and no payload of either family removes one. R3 lists it among `containers.rows` with
`state` `created`: read that row as "the engine created the container and the CLI was stopped before the start; the
root was never written by it". Its removal is a separate authorisation, which the owner may need before M0.

The deployment lock is not taken (CORE.md §11 gives K2a no lock part): a deploy or a controller action that creates a
container during the run would make a verified run PARTIAL with `CONTAINER_PRESENT_THAT_WAS_NOT_THERE_BEFORE`. The
plan's slots avoid HH:05–07, HH:10–25 and HH:35–37.

## 7. Time budget (payload 60 s, watchdog 80 s, transport 270 s)

| Phase | Limit | Expected |
|---|---|---|
| authentication, P1–P5, P8 | file system calls only | milliseconds |
| P6 `image inspect`, P7 `ps -a` | class `QUICK`, 8 s each, never retried | about 0.1 s each |
| P9 | REAL: after the two reads, refuses unless 44 s are left: the prechecks and the reads have 16 s. REHEARSAL: before the first directory, refuses unless 46 s are left; its reads come afterwards and can only take what is left | — |
| E0, E1 (REHEARSAL) | 2 s allowance for both: two `mkdir`, four `fsync` | milliseconds |
| E2 | not started with less than 40 + 4 s left (`COMMAND_NOT_STARTED_BUDGET`: in REAL a refusal, in REHEARSAL a partial with two empty directories, which is what slow reads of a rehearsal end in); killed at 40 s | 1–3 s to start a container (README:428, unmeasured) plus the imports: a few seconds. The 30 s catalog-lock wait cannot occur: an empty root has no `maintenance.lock` (README:380) |
| R2–R4 | whatever is left, at least the 4 s reserve; `ps -a` is a `QUICK` read | under a second |

Nothing waits, sleeps, polls or retries.

## 8. What the owner signs

Request plan (the seven common members, and):

| Member | REAL | REHEARSAL |
|---|---|---|
| `mode` | `REAL` | `REHEARSAL` |
| `journal_chain` | rows `/` … the journal root itself: root-owned chain, the root 0:0 0700 on its parent's device, **a leaf of `/var/lib/c3po-bar`, not `supervisor`** | rows `/`, `/var`, `/var/lib` and nothing else: the **parent** of the two throwaways, root-owned chain, not setgid |
| `throwaway_name` | null | `c3po-bar-rehearsal-[a-z0-9][a-z0-9-]{0,39}`; the directory for docker is that name with `.docker-cli` |
| `reference_chain` | null | the rows `REAL` would sign for the real journal root (the same floor); its device must equal that of `/var/lib` |
| `container_journal_root` | one new top-level directory, not one of the README's twenty (`/c3po-bar-journal`) | the same |
| `docker_config_chain` | rows `/` … `/etc/c3po-bar/docker-cli` **and no other directory**: 0:0 0700 | the same rows; the directory is only read |
| `image_id`, `image_revision` | the ID read after the deploy; the 40-hex revision label it must carry | the same |
| `epoch` | must equal the compiled constant | a `R2D2-V2-DIAG-…` string |
| `script_sha256` | must equal the pinned hash | the same |
| `evidence_boot_id_sha256` | the boot of the rows | the same |

Evidence must name `GO_READONLY_HOSTOPS_PRECHECK_01` (the chains from `/`) and
`GO_WRITE_SUPERVISOR_READER_PROVISION_01` (the identities of the directories operation 2 created).

`effects_of(plan)`, literal in the authority and in the GO: the mode; the journal root path, whether it is the real
one, what is expected of it and its signed row and chain hash; in a rehearsal the real root's row with "read only";
the unit's configuration directory's row, whether it is given to docker (`given_to_docker`: true in REAL only) and
what is expected of it; in a rehearsal the directory it creates for docker (`rehearsal_docker_config`); the value
of `DOCKER_CONFIG` itself (`container.docker_config_variable`); the image ID and revision; **the whole docker
argv**; the bind; the script's hash and size; the 40 s; the epoch and where it comes from; what this process creates
(in a rehearsal the two paths, in the order of their creation) and what the container creates;
the success outcome; the boot of the evidence; `pre_existing_objects_modified` (true in REAL: the root gains two
entries and is bound for good); `removes: []`.

## 9. What the in-run readback proves, and what only the host can prove

Proved inside the run, on the host, through a descriptor opened before the container existed: the directory the
container wrote into is the signed one (or the one this run created) and still is at its path; it holds exactly the
two names with the metadata the producer and the reader require (`APP/r2d2_v2_massive_maintenance.py:29–31`,
`APP/r2d2_v2_massive_sessions.py:40–42`); `epoch.json` is byte for byte what `_immutable` would write for this epoch
and this directory (`:59`, `:204–205`), so the producer's next `create=True` open and the reader's `_verify`
(`:213–215`) accept it **provided the directory has in their containers the device and inode it has on the host**;
the container reported the same identity. `maintenance.lock` is never opened; of `epoch.json` only size and hash leave.

Not proved by the run: that the reader path accepts the root (the script's second open does that, in the container,
and its line says so); that a container of another image or another bind sees the same device and inode (rehearsal
item 6, README:584); free space; anything about the units. B3 (hostops01 readback) reads the catalog again and signs
`catalog{expected, receipt_sha256, device, inode}` from this receipt: `metadata_sha256`, `script_line.device`,
`script_line.inode` (equal to `journal_root.device/inode` in a complete receipt).

**UNPROVEN shapes (never executed on this host; the CI job and A6 exist to close them):**

| # | Shape | Closed by |
|---|---|---|
| K2A-U1 | the attached `docker run` with the README argv on Docker 29.5.3 with the containerd snapshotter: `-i` and a program on standard input to `python -I -B -`, `--init`, `--read-only` with a bind target directly below `/`, a read-write bind of a 0700 root directory written by uid 0 without capabilities | core job U2 (a python image); `linux_root/catalog_shape.py` (this operation's own argv and readback); A6 on the host |
| K2A-U2 | `docker image inspect`, `docker ps -a` and `docker run` under `DOCKER_CONFIG=<empty root 0700 directory>` with no `HOME`; the CLI writes nothing into that directory | `catalog_shape.py` for the client version of the runner (the job prints whether it is the host's 29.5.3); **A6 on the host, under a directory of its own**: a CLI that writes costs a throwaway, and the unit's directory is first used by A9, after A6 was clean |
| K2A-U3 | device and inode of the bound directory are the same in the container and on the host (README:388 "unverified") | core job U2 expectation; `catalog_shape.py`; A6 |
| K2A-U4 | the pinned script inside the production image: the imports under `-I` with `/app` inserted, the duration against 40 s, exactly one line on standard output | the Linux job for the release's own base image by digest, `python` on its path, no entrypoint and the imports of the script (F6); A6 for the production image itself (its dependencies, its duration) |
| K2A-U5 | after the CLI of a `--rm` run returns, `ps -a` no longer lists the container | `catalog_shape.py`; A6 |
| K2A-U6 | listing a held directory descriptor again after another process added entries (`scandir` on the descriptor), and `fsync` of a directory opened `O_RDONLY\|O_NOATIME`, as root on ext4 | the operation's suite as real root in the core job (real on macOS in `tests/test_native.py`) |
| K2A-U7 | what a 40 s timeout leaves (the container outlives the CLI; core U9, U10) | not closed; by rule PARTIAL |

## 10. Decisions taken here that the signers should confirm

1. A difference between the container's and the host's identity of the root is PARTIAL with the root not to be used
   again (the README says "a finding to report, not something to correct"; B3 would refuse such a root anyway).
2. `CATALOG_VERIFIED_WITH_FINDINGS` exists: the README's criterion for the root is met, the run is still not
   complete. Whether B1 may follow is a reading of the signatories after a read-only look.
3. The rehearsal reads the real root and refuses if it is not empty and as signed; so no rehearsal after A9 with
   these bytes.
4. The throwaway directories and the two files are never removed by this family.
5. The epoch of REAL is a code constant; README:140 wants it taken from the signed release body. PLAN §3.1 item 9
   needs the owner's line. If the release body said otherwise, B3 finds it and the root is burnt.
6. No `--name`, no lock, SIGKILL of the CLI at the limit: as the core and the plan decided.
7. A rehearsal gives docker a directory of its own and creates in `/var/lib` only (F1, F8). A rehearsal that fails
   at a docker read is a PARTIAL that leaves one empty directory; two directories and two files stay after a
   complete one. Nothing of this family removes them.
8. One of docker's own statuses after a verified catalog is `CATALOG_VERIFIED_WITH_FINDINGS`, not a burnt root (F2).
   Whether B1 may follow is the same written reading as for the other findings beside a verified catalog.
9. **The run does not look at the pending reboot or at the maintenance pin (F4).** REAL binds the root to a device
   and an inode for good, and there is no recovery after Sunday 20:59:59 BRT. The condition that makes this safe
   (ORD:23: the reboot taken or kept pending by the owner's own order, the pin in place before 4b) stays a condition
   of the dispatch, not of the bytes, for two reasons: `/var/run` is a symbolic link on the host and the pin lies on
   the data volume, outside every path this plan signs; and whether a pending reboot is taken before 4b or stays
   pending until 09/10 is the owner's order, which a refusal in code would take from him. CONTRACT section 5 step 1
   makes it a gate by command: a grid read of the same boot, taken minutes before the A9 dispatch.
10. Of a refusal of the script a token of the code grammar leaves the container; any other text does not (F13).
    A list of the release's own codes was considered and not taken: it would turn a code the release adds or one
    this list forgot into `NOT_A_CONSTANT_CODE`, which is the less useful receipt, and this container holds nothing
    worth hiding (no secret, no environment file, no network).

## 11. The receipt

Besides the members every source of the core has (schema, operation, status, outcome, code, the five hashes,
`scope_sha256`, `core_sha256`, `effects`, `clock`, `commands_started`, `mutating_calls`, `size_reductions`,
`metadata_sha256`):

| Member | Content |
|---|---|
| `mode`, `phase_reached` | `REAL` or `REHEARSAL`; `AUTHENTICATION`, `PRECHECK`, `EFFECTS`, or the core's `BEFORE_ANY_EFFECT` / `ESCAPED` |
| `root_verdict` | `UNTOUCHED_NO_CONTAINER_STARTED`, `CATALOG_READY_VERIFIED`, `CATALOG_VERIFIED_WITH_FINDINGS`, `NOT_TO_BE_USED_AGAIN` |
| `observed_rows` | the rows of the three chains as this run read them (what a refusal for a differing directory shows) |
| `precheck` | entries of the unit's configuration directory and of the root, the image booleans, the number of containers, `docker_config_entries_after_the_reads` (the directory docker was given, counted again once a read was started; null when it could not be counted; absent when no docker command was started), `first_finding` (the code that the state of that directory outranked); in a rehearsal the entries of the real root and whether each of the two throwaways existed |
| `directories` | REHEARSAL: the ledger rows of the two directories in the order of their creation, `DOCKER_CONFIG` then `JOURNAL_ROOT` (state, observed identity, the two fsyncs) |
| `journal_root` | path, device, inode, `created_by_this_run` (null when the run refused before the effects) |
| `run` | `NOT_STARTED`, `RETURNED` or `DID_NOT_RETURN`; the runner's code; the exit status; the seconds the CLI took |
| `script_line` | exit status, size and hash of the output, whether it was one JSON line, the status, a constant refusal code, `as_signed`, the booleans compared, the device and inode the container printed |
| `catalog` | the host readback: `COMPLETE` or `UNAVAILABLE` with a code, entries, other entries (count only), the two files' type, owner, group, mode, links, size and device equality, `epoch.json`'s size, hash, expected hash and equality, `root_unchanged` |
| `containers` | listed before and after, how many were not there before, at most eight of those rows |
| `docker_config` | after the run: the path of the directory docker was given, whether it is the unit's, entries before (0) and after |
| `objects_left_by_this_run`, `pre_existing_objects_modified` | the directories a rehearsal created, plus the entries found in the root, plus the entries found in the directory docker was given; null when a count could not be taken. Modified: true when the real root or (REAL) the unit's configuration directory gained an entry, null when that is not known, always false in a rehearsal |

No value of an environment, no byte of the script, no name of a foreign entry and no raw text of an exception is
in a receipt; of a refusal of the script, a token of the grammar `[A-Z][A-Z0-9_]{0,79}` is (section 10, item 10). Device and inode numbers and container IDs are: receipts of this family are private documents.

## 12. Tests and mutation

Author's runs after the repair, clock by command 2026-10-02T20:18:39Z. Suite: 386 tests on `/usr/bin/python3` 3.9.6 and on
3.12.14, none failed; none skipped with a tree of the release at hand, 9 skipped without one (377 pass). Per file:
conformance 242 (121 per mode), catalog_init 59, review_findings 39, review_purity 23, native 9, real script 4,
static pins 7, linux_root 3.

- `tests/test_conformance.py`: the family's suite with the bound fixture of each mode. The REHEARSAL class replaces
  one test (the suite compares the outcome with `COMPLETE_OUTCOME`, which is REAL's) by the same assertions with the
  rehearsal's outcome.
- `tests/test_catalog_init.py`: the literal effects of both modes; 141 plan refusals over the two modes (64 and 77),
  the layout floor among them; 81 precheck refusals with nothing changed (47 in REAL, the docker reads among them;
  34 in REHEARSAL, all found on the file system before any docker command); the 15 findings of a docker read in a
  rehearsal, each a PARTIAL that leaves one empty directory and has touched nothing of production; the last look; the
  budget at its boundaries in both modes; not started, timeout before and after the effect, output limit, expiry
  during the run; 125/126/127; 34 hostile lines and 35 hostile states of the root after the run, each in both modes;
  a root replaced at its path; a file exchanged between `lstat` and read; a container killed part-way (no file, the
  lock only, a torn `epoch.json`); a leftover container, a failed listing, a configuration directory that changed;
  the failures of each of the rehearsal's two directories; a death at every host call of both modes; the receipt (no
  script byte, no environment value, size, reductions).
- `tests/test_review_findings.py`: one block per finding that changed a byte (section 13): F1 (for every ending of a
  rehearsal, complete, each read finding, each hostile container, each timeout, a failure or a death at every host
  call: no docker command under the unit's directory, nothing written in production; a CLI that writes into its
  configuration directory is found by the rehearsal in its own); F8 (the reviewer's two cases refused from the
  bytes and by the dispatcher before any claim; every private directory of the emulated host tried as a journal
  root); F2; F10 (a REAL run is never a refusal once the unit's directory changed, with a failure at every host
  call); F12; F9 (the reviewer's six tests, a probe that could not establish absence, an activation flag set in the
  three documents); F13; the proof job's base image and paths; the seal's rule for review directories.
- `tests/test_review_purity.py`: the reviewer's own hostile cases, adapted (its header says how): a fault at every
  host call in four kinds and an expiry at every clock reading in three, each with the two invariants (a refusal
  changed nothing; complete means verified on the host); hostile text from the engine and from the container;
  documents of the other mode; 41 foreign members one at a time; dates and windows; another host.
- `tests/test_native.py`: the source's own `Native` with real system calls on a temporary tree and a real process
  behind docker that runs the pinned script against the application modules of the release in the real directory;
  in REHEARSAL the two real `mkdir` and four `fsync`, and the environment each process was given.
- `tests/test_real_script.py`: the pinned script against the release's modules compared with the model the emulated
  container uses; the release's reader path accepts exactly what the readback verifies.
- `tests/test_static_pins.py`: the README's command and script, the README's layout table against the constants of
  the floor, the compiled epoch, the application's names.

Mutation (`mutation/`, the core's harness with three tables changed): 304 single mutants of the operation's
own part, none combined, none redundant. On both interpreters 304 killed, 0 survivors, 0 errors, none by the
time limit. The list of the first build had 213; the repair rewrote every anchor that moved, dropped the mutants of
the three removed lines, and added what `mutation/mutants.py` says in its header. The reviewer's own 28 mutants, of
which 13 survived the first build's tests, were applied to the repaired source by the author
(`<hostops02>/work/k2a_repair_reviewer_mutants.py`, two anchors adapted to the repaired text): 28 killed, 0 survivors
on both interpreters. The mutants of the carried parts are the core's own 548. This says the tests answer the two
lists, not that the lists are complete; the repaired bytes have had no reviewer yet.

Not run: `linux_root/run_catalog.sh` and the real-engine half of `linux_root/catalog_shape.py` (no Linux, no docker).
The script was changed by the repair and has only been checked with `sh -n` and by a test of its text.

## 13. The reviews of 2026-10-02 and what each finding changed

Two reviews of the sealed first build (seal `b2798311…2a95`, payload source `e6c63789…38cc`): one of the host side,
one of purity and authentication. Each finding was reproduced by the author on the sealed bytes before anything was
changed; all thirteen were accepted. A copy of the first build is kept beside this directory
(`<hostops02>/catalog_init.pre-repair-b2798311`).

| # | Severity | Finding | What changed |
|---|---|---|---|
| F1 | MAJOR | the rehearsal ran its docker commands under the unit's real configuration directory: if the host's CLI writes there, the damage is done at A6 and in production | **bytes**: a rehearsal creates a configuration directory of its own and gives docker that one (section 1). The reads of a rehearsal moved after its first `mkdir`. REAL's host calls are unchanged. The proof job prints the client version of the runner against the host's |
| F2 | MINOR | docker's status 125 after a complete catalog burnt the root | **bytes**: the line and the readback are judged first; a status of docker itself beside a verified catalog is `ENGINE_STATUS_AFTER_A_VERIFIED_CATALOG`, verdict `CATALOG_VERIFIED_WITH_FINDINGS` |
| F3 | MINOR | a failed run is hard to read: docker's error text is discarded, a non-constant refusal is a hash | text: section 4, "Reading a failed run". The discarded standard error is the frozen core's (reported as a core defect); the operation part cannot capture it |
| F4 | MINOR | REAL does not look at the pending reboot or at the pin | text: section 10 item 9 says why not in code; CONTRACT section 5 step 1 makes the grid read a gate of the A9 dispatch |
| F5 | MINOR | a container in state `created` and the bounded life of a started one were not described | text: section 6, CONTRACT 3.7 and 6 |
| F6 | MINOR | the proof job built on an unpinned image | `linux_root/run_catalog.sh`: the base of the release's Dockerfile by digest, compared with that Dockerfile by hash; no entrypoint. The job now creates the layout at its real paths, which the floor requires |
| F7 | MINOR | a file written into a review directory broke the seal | `seal.py`: top-level directories `review-*` are not sealed |
| F8 | MAJOR | which directory is "the real journal root" rested on the signed rows alone; REAL on the state root and a rehearsal inside the true journal root authenticated and completed | **bytes**: the layout floor as constants in the signed scope (section 1). The parent of a rehearsal is fixed to `/var/lib`, which is stricter than the forbidden zones the reviewer proposed. Two refusals that the floor makes unreachable were removed with their mutants (`PATHS_OVERLAP`, `REHEARSAL_ROOT_INSIDE_THE_PARENT_OF_THE_REAL_ROOT`), and `DOCKER_CONFIG_PATH_INVALID` became the equality with the unit's path |
| F9 | MINOR | 13 of the reviewer's 28 mutants survived the first build's tests | tests: the reviewer's six tests and two more; the 13 are in the list; all 28 are killed |
| F10 | MINOR | a refusal at the last look said "nothing changed" although the unit's directory might hold a new entry | **bytes**, further than the review asked: once a docker read was started the directory is counted whatever the reads ended in, the count is in the receipt, and in REAL a directory that is not empty or not countable makes the run a PARTIAL with the root untouched, never a refusal. What docker left counts as left by the run and, in REAL, as a modification of an existing object |
| F11 | MINOR | "every REFUSED receipt carries `root_verdict`" and the list of refusal codes were not exact | text: section 4; CONTRACT 3.4 and 3.5 |
| F12 | MINOR | a descriptor stayed open when the first look at a walked directory failed | **bytes**: `pin_chain()` closes it. The same in `files.create_directory` is the frozen core's (reported as a core defect) |
| F13 | MINOR | "only a constant code leaves" holds up to the grammar | text: section 10 item 10, section 11, CONTRACT 3.7; kept as it is, pinned by a test |

What the repair did not do: it did not touch the frozen core; the dispatcher, the launcher, the transport and the
two delta files in `build/` are byte for byte those of the first build (compared by command); it did not change the
argv, the script, the image checks, the readback of the catalog or the authentication.
