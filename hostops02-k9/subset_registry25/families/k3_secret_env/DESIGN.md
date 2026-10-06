# K3 — the reader's `secret.env` (`k3_secret_env`), candidate revision 1

Offline work only (2026-10-04, between 21:20Z and the seal). Nothing here was run on the host, pushed or bound. One
independent adversarial read (a separate agent, read-only, 2026-10-04) found no blocker, three major and several minor
points; section 15 says what changed for each. No co-auditor has reviewed these bytes. Every hash named here was taken by command; where this text and `SHA256SUMS`,
`VALIDATION.json`, `build/ASSEMBLY.json` or a mutation record differ, the files prevail.
`D` = the directory that holds this one (`k3_secret_env`) and its core (`core_k3`); `W` = the parent of `D` (the work
directory of the epoch, where the sibling families lie); `S` = the author's private scratch copy of the sealed HOSTOPS01
candidate (`hostops01/candidate`) and of the reader's deployment files (`opsart/c3po/deployment/reader`). No absolute path
of the workstation is written in this directory.

| What | Value |
|---|---|
| Operation | `GO_WRITE_HOSTOPS02_K3_SECRET_ENV_01`, phase `WRITE_READER_SECRET_ENV_IN_MEMORY`, class WRITE, `WRITE_EPOCH` (2026-10-03 … 10-10 UTC), gate ≤ 900 s, `ACTIVATION_ALLOWED=False` |
| Row | A7 of the epoch plan (`W/fable-epoch03-masterplan-20261002/MASTER_PLAN.md` line 183); MASTER_PLAN K3 (line 331): "exactly to HOC section 8; canary tests; no size, digest or length anywhere" |
| Specification | HOC section 8 (`S/hostops01/candidate/CONTRACT.txt` lines 602–646, "THE secret.env STEP"); reader README (`S/opsart/c3po/deployment/reader/README.md`), "Environment files" item 1 and "Operations" 1 |
| Core | `D/core_k3`: a byte copy (made 21:15Z) of the secrets family's revision (CORE.md section 15), generation `232f4180a940186e86d7599c10c4fac143fcfe3950baa8e853a3910f84f5c1e6` (= sha256 of `assemble.py`; `assemble.py --core` verifies the pins of every part). Read only, never edited. Its own `seal.py check` answers `SEAL_BROKEN` on the copy because `CORE.md` and `mutation/MUTATION_RUN.json` differ from `CORE_SHA256SUMS` (upstream was mid-run when it was copied); every other listed file holds its hash (`seal.py` here checks exactly that) |
| Parts carried | `core runner docker parents files` (the `files` part for `NativeFiles`, `filesystem_code`, `number`; its `create_file` is NOT used: its ledger row carries a hash and a size, CORE.md section 10) |
| Closest family | K3-K9 (`W/fable-k3k9-20261004/k3k9_secrets`): the same core revision, the same structure, the same first step, the same direct exclusive create with withdrawal (D3), the same canary discipline. K3 places ONE name in ONE file |

## 1. What one signed run does, and what it never does

Creates `/etc/c3po-reader/secret.env`, a regular file, root:root 0600, one link, holding exactly one line
`C3PO_DATABASE_URL=<value>\n`, the value copied in memory from the environment of the running container
`c3po-r2d2-worker-1` (compose project `c3po`, service `r2d2-worker`) whose 64-hex ID the request signs.

In order, everything looked at before the creation (a refusal there changes nothing):

1. the process made non-dumpable and proved (`prctl(PR_SET_DUMPABLE,0)`, `PR_GET_DUMPABLE`=0; the core's `dumps_disabled`), first call of the run;
2. executor 0:0, umask 0077, boot equal to the evidence's;
3. `/etc/c3po-reader` walked from `/` against the signed rows (no link followed, identity at every step) and held;
4. its names listed in memory: `secret.env` absent (`SECRET_ENV_PRESENT`, with type/uid/gid/mode/links of what is there and nothing else), no name that holds `secret.env` and no name that begins with `.hostops-` (the core file writer's temporaries) (`SECRET_ENV_LEFTOVER_PRESENT`), at most 64 entries (`ENTRY_LIMIT`). Other entries (`docker-cli/`, `launcher/`, `pins.env`, `activation.env`) are allowed: other operations create them and the order of the rows is not fixed. When `pins.env` or `activation.env` is present it must be a regular file of at most 65,536 bytes (`OTHER_ENV_FILE_UNREADABLE`) in which no line defines `C3PO_DATABASE_URL` (`SECRET_KEY_IN_ANOTHER_ENV_FILE`): the README's "the writers and the readbacks refuse a name that appears in more than one file". Those two files are not secret; they are read in memory, a boolean leaves;
5. the worker: `docker ps -a` (exactly one container named `c3po-r2d2-worker-1`, with the signed ID; no other *running* container whose name begins `c3po-r2d2-worker-`), `docker container inspect` (running), one inspect of its two compose labels (project `c3po`, service `r2d2-worker`), then the fixed secret template **twice**, the one entry compared, then `docker ps -a` again (the signed ID still the one running container of the name);
6. at least 15 s left of the 60 s budget, and the directory proved again from `/`.

Then: one `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC` 0600 create of the final name relative to the held
directory, the writes from a `memoryview` of a `bytearray`, fsync, `fstat` (regular, 0:0, 0600, one link, the
directory's device), fsync of the directory, the readback (section 6), and the directory read back (identity again from
`/`, exactly one entry more than before).

Never: overwrite, rename, chmod, chown, truncate, a temporary file; a read of the deploy tree or its `.env`; `docker
exec`, `docker run`, compose, systemctl, a shell; a process other than `docker ps` and `docker container inspect`; a
value, digest, length or size of the value, the line or the file in a receipt, argv, environment of a command, log or
exception; activation; a retry.

## 2. HOC section 8, point by point

| HOC 8 says | Here |
|---|---|
| operation `GO_WRITE_READER_SECRET_ENV_01`, documents `WRITE_HOSTOPS_SECRET_ENV_*_V1`, "the same core" | the HOSTOPS02 grammar: `GO_WRITE_HOSTOPS02_K3_SECRET_ENV_01`, `WRITE_HOSTOPS02_K3_SECRET_ENV_{REQUEST,AUTHORITY,GO,RECEIPT}_V1`, stem `HOSTOPS02_K3_SECRET_ENV`; the HOC phase name `WRITE_READER_SECRET_ENV_IN_MEMORY` is kept. The core is HOSTOPS02's secrets revision (the HOSTOPS01 core has no secret row) |
| target `/etc/c3po-reader/secret.env`, 0600 root:root, through the pinned `/etc/c3po-reader` (rows from the OP_PROVISION ledger) | yes, but **deviation D-8**: the rows come from a read-only receipt of the same boot (the core's rule 8), not from the provisioning's ledger of 10-03; the provisioning is cited as evidence. The rows `/`, `/etc`, `/etc/c3po-reader` are signed (`config_chain`), with no open root: every row uid 0, not writable by group or other (`CHAIN_ROW_UNSAFE`, also sticky 1777), the leaf exactly uid 0, gid 0, mode 0700 (`CONFIG_DIRECTORY_NOT_ROOT_0700`; 0750, 1700, a group ≠ 0 refused), not setgid (`PARENT_SETGID`). The rows must come from a receipt of the same boot (section 4) |
| "by exclusive temporary, fsync, link, removal of the temporary proved by identity" | **deviation D-1**: direct exclusive create of the final name, no temporary (section 6) |
| source: exactly one running container, project c3po, service r2d2-worker, selected with the reviewed HOSTFACTS argv | the container by its signed ID and its compose name, `docker ps -a` with the core's reviewed `PS_FORMAT`, its two labels read by one fixed template (`LABELS_FORMAT`, constructs `index` and `json` that ran on the host), and no other running container whose name begins `c3po-r2d2-worker-` (a second replica, a `compose run` container). **Gap G-1**: a running container that carries the two labels under an unrelated name is not seen (the labels of every container are not read) |
| one new command, the narrowing template, stderr discarded, no fallback that prints the whole environment | the core's fixed row `container_secret_environment` for the one name: `{{range .Config.Env}}{{$p := split . "="}}{{if eq (index $p 0) "C3PO_DATABASE_URL"}}{{json .}}<newline>{{end}}{{end}}`; stderr to `/dev/null` (the runner); no fallback. **Deviation D-2** (the K3-K9 deviation, CORE.md section 15): `{{json .}}` and a literal newline instead of `{{println .}}` — only constructs that ran on the host, and a value holding a newline is printed as `\n` and refused, never read as a second entry |
| accepted byte shape: one entry line plus the inspector's own newline; exactly the entry line and one newline written | the core's parse requires the output to end with the inspector's newline and every line before it to be `"C3PO_DATABASE_URL=…"` (`SECRET_ENVIRONMENT_SHAPE`), the name at most once (`SECRET_ENVIRONMENT_REPEATED`); the emulator prints both newlines (tested: `"…"\n\n`). Exactly `C3PO_DATABASE_URL=<value>\n` is written |
| shape check: key exact, value 1 to 4096 bytes, no NUL, CR or LF; buffer zeroed in a finally | key exact (the template and the parse); value: the core's parse copies only 1–4096 bytes of printable ASCII without a quote or a backslash (anything else is `None`, never a refusal of its own), and this source then requires `[\x21\x23-\x5b\x5d-\x7e]{1,4096}` — **deviation D-3, stricter**: a space, a quote, a backslash, a tab or any byte outside printable ASCII is refused too (`SECRET_VALUE_SHAPE`, nothing changed). Reason: the docker CLI's `--env-file` takes the value verbatim, and a URL holds no space (README: "no quotes, no trailing space"). Every `bytearray` that held the value (both reads, the line, the bytes read back) is zeroed in a `finally` (tested) |
| RLIMIT_CORE 0 and `/proc/self/coredump_filter` 0 before the source command | **deviation D-4**: `prctl(PR_SET_DUMPABLE,0)` read back 0, first of all (the token placement's D9, accepted by the co-auditor; CORE.md section 14). A piped `core_pattern` ignores RLIMIT_CORE; the dumpable attribute stops the kernel before the pattern is formatted |
| NO SIZE ANYWHERE (complete, refusal with a pre-existing file, partial, leftover): type, uid, gid, mode, links and booleans only; never st_size, a block count, a timestamp, a digest or a length | yes (section 8). The operation part never names `st_size`, `st_blocks` or a time member, nor a hash, an encoding or `stat_signature` (syntax-tree test). A pre-existing `secret.env` is described by `{'type','uid','gid','mode_octal','links'}` only — not even `size_is_zero` |
| canary test: the value, any 8-byte substring, base64, hex, MD5, SHA-1, SHA-256 of the value and of the line, the value length, the line length and the file size (one and two newlines) in no receipt of any outcome, no stderr, no exception text, no argv, no command environment and no file but the target | yes, on every run of the emulated suite (every `run()` scans receipt and outside view), in two canary worlds of unusual lengths (value 3217 and 1729 bytes: lengths searched as standalone decimal, hex and octal numbers, and as JSON integers), on the native child's stdout/stderr, on the parse's exception text; receipts of the two worlds are byte-identical for every outcome tested (complete, withdrawn, tampered readback, pre-existing files of different sizes, every shape refusal, absent, repeated). "No file but the target": the native child's audit hook shows exactly one open for writing (`secret.env`) and no other file event |
| mutants: size emitted in the refusal table; template widened; digest or length emitted; written under the final name directly | H01, H02 (size / size_is_zero in the refusal table); H03, H04 and the core's D01 (template widened); H05–H08 (length, digest, a read size that depends on the value, a length key); the fourth is this design (D-1): the list kills every property that makes a direct exclusive create safe instead (`mutants.py` docstring: C13, C14, C16, F06, F07, F10, F20–F24) |
| receipt booleans `single_line, key_matches, value_within_1_4096, size_equals_bytes_written, source_unchanged_during_read` | **deviation D-9, renamed**: `readback_exactly_one_line`, `readback_name_is_the_key`, `value_shape_met` (said only of an accepted value), `all_bytes_written` (the count of bytes the writes returned equals the line's, compared in memory; no size is read from the file), `read_twice_equal`; plus `readback_equal_to_the_worker_entry` (README) |
| `source_unchanged_during_read` compares only the one selected field | yes: the template prints the one entry; the two reads are compared on presence and bytes of that entry only; a change of another entry between the reads is not looked at (tested) |
| open point: PLAN 3.3 "the same hashes" of secret.env in both gates' receipts | not done (no digest anywhere); the receipt carries the identity (device, inode, uid, gid, mode, links) — for the plan authors (Q-7) |
| open point: `/etc` versioned or copied (`/etc/.git`, `/etc/.etckeeper`) | not looked at by this source; in the owner sentence (section 11) and Q-5 |
| open point: a crash can leave the 0600 temporary | there is no temporary; a crash after the create can leave `secret.env` itself, partial, 0600 root:root in the 0700 directory; the next run refuses `SECRET_ENV_PRESENT` and describes it without a size. No removal exists (HOC 9, Q-6) |

## 3. The reader README

"Readback: uid, gid, mode, link count, 'exactly one line' and 'the name is C3PO_DATABASE_URL' (true or false), and
'equal to the r2d2-worker entry' (true or false, compared in memory). Never the value, a digest of it, or its length."

**Decision: the content is read back, in memory, booleans only** (K3-K9 read metadata only; this departs from it, and
follows the README). Reasons: the README is the consumer's contract and asks for those three booleans; HOC 8 asks for
`single_line` and `key_matches`; K3-K9's reason for metadata only was its brief, not a risk. How it is kept from saying
a size: the name is opened again (`O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_NOATIME` by descriptor); its bytes are read **only
after** the new descriptor proved the same inode, regular, 0:0, 0600, one link (a replaced name is never read: tested);
every `read` asks for the same constant `READBACK_REQUEST` = 18 + 4096 + 2 = 4116 bytes (the longest line plus one, so
no argument of a call depends on the value; tested in the emulation and with real reads, and mutant H07); the bytes go
into a `bytearray` that is zeroed; three booleans leave. The cost: one more immutable copy of the line in this process
(the `bytes` `os.read` returns), as non-dumpable as the rest (section 7). "Equal to the r2d2-worker entry" is the line
compared with the line built from the entry read twice in this same run; the worker is not inspected a third time.

## 4. The plan, the evidence, and the worker's ID across M3

| Key | Content | From |
|---|---|---|
| `config_chain` | three rows (path, device, inode, uid, gid, mode): `/`, `/etc`, `/etc/c3po-reader` | a read-only receipt of the same boot that prints them (PROPOSED: the epoch readback); the directory itself was created by `GO_WRITE_SUPERVISOR_READER_PROVISION_01` on 2026-10-03 (E2, KNOWN_COMPLETE; `W/once-e2-20261003-b/PARAMETERS.json`) |
| `worker_container_id` | 64 hex | a read-only receipt of the same boot that names the running worker by ID (K3-K9 used `GO_READONLY_HOSTOPS02_EPOCH_READBACK_01`) |
| `evidence_boot_id_sha256` | 64 hex | the same receipt |

`EVIDENCE_OPERATIONS=('GO_WRITE_SUPERVISOR_READER_PROVISION_01','GO_READONLY_HOSTOPS02_EPOCH_READBACK_01')`: the
request must cite both (the creation of the directory, and the same-boot read of the rows and the ID). Q-1 asks whether
the epoch readback prints `/etc/c3po-reader`'s rows at all.

**The worker is recreated by the activation (M3, Monday 05:50 BRT = 08:50Z on 10-05).** Its ID changes then. A request
bound to the ID before M3 and dispatched after it refuses `WORKER_CONTAINER_MISMATCH` (the listing shows the name with
another ID), nothing changed — tested (`worker_recreated_by_the_activation`). So the binder takes the ID from a receipt
of the same side of M3 as the dispatch. The value itself does not change with M3 (compose builds it from the same
`.env`), so placing `secret.env` before M3 is not stale after it.

## 5. The worker and its one entry

Rules in order, each decided by names and identities first, never by a value: listing (`WORKER_CONTAINER_MISMATCH`,
`WORKER_NOT_THE_ONLY_ONE`), inspect (`WORKER_NOT_RUNNING`: `running` true and state `running` in both the inspect and
the listing; paused or restarting is refused), labels (`WORKER_NOT_THE_COMPOSE_SERVICE`; a malformed answer
`CONTAINER_METADATA_INVALID`), then the entry: absent (`SECRET_ENTRY_ABSENT`), repeated (`SECRET_ENVIRONMENT_REPEATED`,
decided by the name alone), shape (`SECRET_VALUE_SHAPE`), the second read different in presence or bytes
(`WORKER_ENVIRONMENT_CHANGED_DURING_READ`). An output of the secret template over the runner's 65,536-byte class limit
(`COMMAND_OUTPUT_LIMIT`) is reported `SECRET_VALUE_SHAPE`, which it implies for one entry of at most 4096 bytes. The
facts of the entry (`entry_present`, `value_shape_met`) are said only of an accepted value, and `read_twice_equal` only
after the second read, so a refusal says nothing of a value but its constant code (review M1: `entry_present` used to
be set before the shape check, and an output over the runner's limit left it `None` while a smaller bad value set it
`True`: one bit of length. Fixed and tested at 70,000 against 5,000 bytes). An output over the limit at the **second**
read, after an accepted first read, is a change (`WORKER_ENVIRONMENT_CHANGED_DURING_READ`, `read_twice_equal` false),
the same receipt as any other change (tested). Tested: worlds differing only in the value's length or characters (600 and 5000
bytes, quote, backslash, newline, non-ASCII, empty, space) give byte-identical receipts when another cause is present
(labels, a replica, the file present, a repeated name), and every shape fault gives the same receipt.

Names in another case (`c3po_database_url`) and longer names (`C3PO_DATABASE_URL_OLD`) are not the key (tested). The
entry without `=` (the bare name, which the core's parse refuses as `SECRET_ENVIRONMENT_SHAPE`) is reported
`SECRET_VALUE_SHAPE` like an empty value, with the same receipt (review 2; tested); at the second read it is a change.

**Listed again after the reads** (review 2): the inspects name the worker by its 64-hex ID, which the docker CLI also
matches against container names. After the second read `docker ps -a` runs again; the signed ID must still be the one
container of the name, running (`WORKER_CHANGED_DURING_READ`; `same_container_after_the_reads`). A swap between two
listings that is undone before the second is not seen (stated).

## 6. The creation, the readback and the withdrawal (deviations D-1 and D-11)

Directly the final name, no temporary, exactly as K3-K9 and the token placement (the co-auditor accepted it there, D3,
comment 5973246540): a temporary would leave a second copy of the value under another name if the process died between
link and removal, and HOC's own open point says so. The exclusive create never replaces anything (`EEXIST` →
`SECRET_ENV_APPEARED_AFTER_PRECHECK`, state `NOT_CREATED`, the raced file untouched, the run a refusal since nothing
changed).

**The file stays only when the run is complete** (revision after the second independent read; this departs from
K3-K9 and from the token placement's D3 as the co-auditor accepted it, deviation D-11). After the creation, ANY failure —
a failed call, a metadata or content mismatch, a failed directory readback, an expiry of the GO, a clock reversal, a
replaced directory, an exception of another kind — withdraws **the file this run created**: through the held
descriptor of its directory (wherever that directory now is), only while the name there shows the inode this run
holds with one link (`unlink` counted through `mutate`, then fsync of the directory: `WITHDRAWN`). That one removal is
**not stopped by the gate** (`mutate` with a gate that never refuses): an empty or half-written `secret.env` left after
an expiry between the create and the write would block every later attempt (`SECRET_ENV_PRESENT`), and no removal
operation exists; the removal is an `lstat`, an `fstat`, an `unlink` and an `fsync`, microseconds, inside the
payload's own process and long before the dispatcher's 80 s watchdog. The receipt says whether the directory was still
at its signed path when the file was withdrawn (`directory_at_the_signed_path`, proved from `/` with the same ungated
walk), so a file withdrawn from a moved directory is not reported as if it lay at `/etc/c3po-reader`. Never another
object: a name that shows another inode, or a second link, is left (`LEFT_UNVERIFIED`,
`SECRET_ENV_NAME_NOT_THIS_RUNS_FILE`), as is a file whose unlink fails (`SECRET_ENV_WITHDRAWAL_FAILED`) or is uncertain
(`SECRET_ENV_WITHDRAWAL_UNCERTAIN`). A run with a successful mutating call is PARTIAL, never a refusal. So a PARTIAL
leaves `secret.env` only in those three cases, and the receipt names which (Q-6: no removal exists for them).

What the readback checks: section 3. A readback whose bytes differ (another line appended, a byte changed, the file
emptied, more than 4116 bytes) in the same inode is `READBACK_MISMATCH`; the directory readback (proved again from `/`,
then the count) finding any other entry count, a replaced directory or an error is `DIRECTORY_READBACK_MISMATCH`
(`directory_readback` says which); both withdraw the file.

Two limits, stated: (1) between the `lstat` that proves the name still shows this run's inode and the `unlink`, only a
process of root can act in a root:root 0700 directory; such a race is not guarded (as in K3-K9 and the token
placement). (2) The withdrawal after a refusal of the gate is a mutating call made after the GO expired or the clock
went back: the one exception to "nothing after the gate", declared in the signed scope (`exceptions_to_the_core`).

## 7. Secret in memory, core dumps, and the docker CLI

As K3-K9 (its DESIGN section 8), for one entry: the first call of every path that reaches the host is `not_dumpable()`
(tested on every refusal, the complete run, the failures, and with real system calls on the workstation's C library
substitute). The values live in `bytearray`s zeroed in a `finally`; the core's parse zeroes what it made before raising.
The line is allocated once at its final length and filled in place (review: a growing `bytearray` could leave a
freed, unzeroed copy of the value behind). Immutable copies remain until the process ends: the bytes the runner read
from the CLI's output (and the runner's own buffer), the `bytes` of the readback's `os.read`, and the interpreter's
transient objects. The docker CLI processes (`ps` × 2, `inspect` × 4) are
processes of their own (an exec makes them dumpable again); the inspect that prints the entry holds the worker's whole
inspect object, as every `docker container inspect` of it does; a crash of a Go CLI under the default `GOTRACEBACK` writes
no core file (not proven here, Q-3). Residual: copies in freed memory, swap, a kernel dump, root's access to a live
process; and at rest, the value is visible through `docker inspect` to anyone with Docker access (README, "Known limits").

## 8. "No size anywhere": what is covered and what is not an output

Covered, tested: the receipt of every outcome (no member names a size, length, digest, block count or timestamp of the
file; receipts identical across values of different lengths); the argv, the environment, the variables and the standard
input of every command (the template carries no value; the value travels only on the CLI's standard output); every
exception text (constant codes; `listed()` replaces any unlisted code-shaped text by `UNLISTED_CODE`); the native child's
output; the read requests (a constant).

**The one size class that remains** (as K3-K9's m2): the runner refuses an output of the secret template over 65,536
bytes (`COMMAND_OUTPUT_LIMIT`) before the parse sees the names. At the first read that is reported
`SECRET_VALUE_SHAPE`; a value that large is a shape fault anyway, but a *repeated* entry whose copies together exceed
the limit is then reported `SECRET_VALUE_SHAPE` instead of `SECRET_ENVIRONMENT_REPEATED` (pinned by a test). What it
says: the worker's environment holds more than 64 KiB under that name, which a database URL never does.

**A second size class, from the filesystem** (review 2): a `write` that fails with `ENOSPC` (`FILESYSTEM_FULL`) when
the filesystem holding `/etc` has less free space than the line needs says that the line is longer than the space
left; with one free block of 4096 bytes, only lines of 4097 to 4115 bytes (values of 4079 to 4096 bytes) fail. The
source does not look at free space (that would be a size of its own), the root filesystem of this host had 595,212,316,672 bytes
available at HOSTFACTS_01 (`f_bavail` × `f_frsize` as `tests/hostemu.py` copies them), and the file is withdrawn either way; stated, not closed.

Not outputs, stated so that no reviewer has to infer them:
- the `write` system call receives the line's length as its argument (the kernel must); the emulator's log records it,
  and the tests' outside view leaves that one number out on purpose (it is the emulator's record of a kernel argument,
  not something the run prints);
- `mutating_calls` counts one call per `write`: a host that writes short shows more calls (K3-K9's m6), a count of system
  calls, not a size; for a regular file of at most 4115 bytes a short write does not happen in practice;
- `config_directory.entries_before` is the number of names in `/etc/c3po-reader` before the run: not a property of the
  secret;
- the time a run takes is in `clock` (milliseconds); it does not measurably depend on a length of at most 4096 bytes.

## 9. The date class

`WRITE_EPOCH` (2026-10-03 … 10-10 UTC), not `WRITE_SESSIONS`: row A7 is planned on the Sunday (MASTER_PLAN line 30, L1
order "A5, B2, A8, A7, …"), and a Sunday evening before 21:00 BRT is still 10-04 UTC, which `WRITE_SESSIONS` (from 10-05)
does not contain; the same row may slip to the evening of any session day (10-05 … 10-09 BRT, which are 10-05 … 10-10
UTC). `WRITE_EPOCH` covers both and nothing beyond the epoch. A window still lies wholly on one UTC day, at most 900 s.
Tested: complete on 10-04 22:30Z (Sunday 19:30 BRT), 10-05 01:00Z, 10-09 23:00Z; `DATE_NOT_IN_SCOPE` on 10-11.

## 10. Tests, mutation, proven and unproven

- `tests/test_k3_secret_env.py` (emulated host): the complete run and its exact receipt; the directory holding what other operations created; the exact docker argv (HOC's template for one name, the json deviation); the order on the host; every buffer zeroed; receipts independent of the value and its length; a pre-existing `secret.env` of any size described without a size; the directory readback proved from `/` again; the canary worlds on every path; 53 refusals before the creation; the withdrawal after an expiry or a clock reversal at three stages; the second listing with the tree unchanged and no mutating call; accepted variants and bounds; changes between the two reads; the budget at 14/15/12 s left; every failure after the creation (create, write, fsync, fstat, metadata of each kind, a replaced name, a tampered content in seven ways, a replaced directory, a failed read, expiry at two points, an uncertain create, a failed or uncertain unlink, a withdrawal not made durable, short writes, a write of nothing, the directory readback); the other environment files (the key defined in six spellings, accepted contents up to the 65,536-byte bound, unreadable kinds); the plan's refusals; the effects; the evidence; the date class; the secret row's start rule and forged answers; the parse's zeroing; several causes at once.
- `tests/test_native.py`: the source's own `Native` with real system calls on a temporary tree (`oslevel.Substitute`), docker answered by the core's emulated engine (no docker binary ever started): the real create, fsync, readback reads (constant sizes, identical across the two canary worlds), a real withdrawal by `unlink`, a pre-existing file and a symbolic link refused without being followed or opened, a leftover and a replaced directory refused, a C library that fails `prctl` refused before anything is opened; a child interpreter under an audit hook (two canary worlds): exactly one open for writing, no other file, process, environment or socket event, nothing of the value or its lengths in its output.
- `tests/test_conformance.py`: the family's 121 tests, unchanged (siblings added as foreign operations when present, K3-K9 among them). `tests/test_static_pins.py`: identity, constants, scope, receipt codes both ways, no size/time/hash/encoding member named by the operation part, no reflection.
- Mutation (`mutation/`): every mutant of the operation's own list (its part, the HOC mutants, and the core's `dumps_disabled`, template, parse and start rule as it carries them) killed on Python 3.9.6 and 3.12.14; figures in `VALIDATION.json` and the two records.
- **Real on the workstation**: the file system calls above (macOS, an ordinary user reported as root, a marker bit for `O_NOATIME`).
- **Emulated only**: docker (template execution by the core's engine, typed first, raw fallback), uid 0, device numbers, errno injection, process death; `prctl` (macOS has none).
- **Unproven — the Linux-root CI job has NOT been run for this directory**: real uid 0 and `O_NOATIME`; the kernel's `prctl` and what it dumps; the secret template and `LABELS_FORMAT` on the host's docker CLI (U3 of the core: constructs proven, compositions not); the docker CLI's crash behaviour (Q-3); the docker CLI's `--env-file` reading of this line (the reader's own CI).
- **Unproven until the host runs it**: the worker's value and its shape on the host (a space or other refused byte in the real URL would make this a refusal); the rows of `/etc/c3po-reader` as K11 prints them (Q-1).

## 11. The owner's sentence (HOC 8: "the owner signs a different sentence: a second copy of the database URL at rest")

**OPEN — proposed text, NOT signed by anyone:**

> "Autorizo, uma única vez nesta época R2D2-V2-SHADOW-2026-10-05, a operação GO_WRITE_HOSTOPS02_K3_SECRET_ENV_01 a
> criar no servidor uma segunda cópia em repouso da URL do banco de dados de produção (C3PO_DATABASE_URL, que contém a
> senha do papel c3po), no arquivo /etc/c3po-reader/secret.env (root:root 0600), copiada em memória do ambiente do
> contêiner c3po-r2d2-worker-1, para uso exclusivo do leitor V2 shadow. Estou ciente de que o valor fica legível pelo
> root e por quem tem acesso ao Docker, de que /etc pode ser versionado ou copiado por ferramentas do sistema (etckeeper
> ou /etc/.git, se existirem), e de que nenhuma operação desta família remove o arquivo depois."

## 12. Deviations, stated

1. **D-1** From HOC 8: direct exclusive create of the final name, no temporary (section 6); the HOC mutant "written under the final name directly" is the design, and the list kills its safety properties instead.
2. **D-2** From HOC 8: `{{json .}}` + a literal newline instead of `{{println .}}` (CORE.md section 15, K3-K9).
3. **D-3** From HOC 8: a stricter value shape (no space, quote, backslash, control or non-ASCII byte), a refusal with nothing changed.
4. **D-4** From HOC 8: `PR_SET_DUMPABLE` instead of `RLIMIT_CORE` + `coredump_filter`.
5. **D-5** From HOC 8: operation, phase and document names in the HOSTOPS02 grammar; the HOSTOPS02 secrets core, not HOSTOPS01's.
6. **D-6** From K3-K9: the content is read back in memory (booleans), as the README asks (section 3).
7. **D-7** From HOC 8 "selected with the reviewed HOSTFACTS argv": selection by signed ID + name + labels + no other running `c3po-r2d2-worker-*` (G-1).
8. **D-8** From HOC 8 "rows from the OP_PROVISION ledger": rows from a same-boot read-only receipt; the provisioning cited as evidence.
9. **D-9** From HOC 8: the receipt booleans renamed (section 2), none of them a size.
10. **D-10** From the README's "refuse a name that appears in more than one file": applied by this writer to `pins.env` and `activation.env` when present, with a stricter reading (a name with white space around it is taken as a definition).
11. **D-11** From K3-K9 and the token placement's D3 ("never after the expiry of the GO, never after its directory was found replaced"): the file is withdrawn after ANY failure that follows its creation, expiry and a replaced directory included, through the held directory descriptor, by a removal the gate does not stop (section 6).

## 13. Open questions (for Codex and the binder)

- **Q-1** Evidence: does the epoch readback (`GO_READONLY_HOSTOPS02_EPOCH_READBACK_01`, K11 PRE/POST) print the rows of `/`, `/etc`, `/etc/c3po-reader` and the worker's ID? If not, which same-boot read does? May the request cite the provisioning (`GO_WRITE_SUPERVISOR_READER_PROVISION_01`, another family, 10-03) as evidence? A change of either name is a new seal.
- **Q-2** M3: is A7 dispatched before M3 (ID from a pre-M3 receipt) or after (ID from K11 POST)? The source refuses a stale ID either way, nothing changed.
- **Q-3** The docker CLI processes holding the worker's inspect object, started by a non-dumpable process (as K3-K9's Q2): acceptable under D9, or a Linux proof first?
- **Q-4** D-3: accept refusing a space (and the other bytes) in the value? If the host's URL holds one, this source refuses and nothing changes.
- **Q-5** `/etc` versioning: OP_PRECHECK reported `/etc/.git` / `/etc/.etckeeper`; does the owner sentence cover it, or must a read show they are absent first?
- **Q-6** No removal operation exists for what a PARTIAL leaves (`LEFT_UNVERIFIED`), nor for a pre-existing `secret.env`; a second attempt is refused by design.
- **Q-7** PLAN section 3.3 "the same hashes of secret.env in both gates' receipts" contradicts the no-digest rule: the plan authors decide (proposal: device, inode, uid, gid, mode, links as here).
- **Q-8** G-1: is the name-prefix rule for "exactly one running container of the service" enough, or must every running container's labels be read?
- **Q-9** The binder has no rule for this operation; the owner's sentence (section 11) is not signed.
- **Q-10** The core copy's own seal does not hold (two upstream files changed mid-run); is binding against generation `232f4180…` with the parts' pins verified acceptable, or must `core_k3` be re-copied from a sealed upstream first (a rebuild with the same `op.py`/`spec.py` gives the same source bytes only if `assemble.py` is unchanged)?

## 15. The independent read (2026-10-04) and what changed

| # | Finding | Disposition |
|---|---|---|
| M1 | `entry_present` was set before the shape check, and an output over the 64 KiB limit left it `None`: two receipts for the same code, decided by a length | fixed: the facts of the entry are said only of an accepted value; test at 70,000 vs 5,000 bytes |
| M2 | the README's rule "the writers and the readbacks refuse a name that appears in more than one file" was neither applied nor declared | applied (D-10): `pins.env` and `activation.env`, when present, are read in memory and must not define the key; tests and mutants `O*` |
| M3 | evidence stale at the time of the read (a record with five survivors; VALIDATION.json and SHA256SUMS absent) | the read ran while the author was mid-run; F11–F14 are equivalent (named in `mutants.py`), F36 got its test; everything rerun and sealed after these changes |
| m | a repeated entry over 64 KiB is refused by the shape | declared (section 8) and pinned by a test |
| m | an output over the limit at the second read gave a self-contradictory receipt | it is a change now (`read_twice_equal` false), the same receipt as any change; tested |
| m | a non-`OSError` from the fsync after a withdrawal ran the withdrawal twice and misreported the row | `withdraw` catches any exception there (`WITHDRAWN_NOT_DURABLE`, `FSYNC_FAILED`); tested, mutants F09, F38 |
| m | the line grew by `extend` (a freed copy of the value) | allocated once at its final length (section 7) |
| m | the listing's state and the inspect's `Running` flag were not separately tested | two tests (a forged listing; `Running` false with status running) |
| m | the directory readback's code was not tested through `listed()` | test with a code-shaped text at the directory readback |
| m | lstat/unlink race; a file left in a replaced directory is reported under the old path | declared (section 6) |
| m | CONTRACT said a second attempt after a WITHDRAWN partial refuses; the scope's readback text omitted two flags; the scope statement omitted the withdrawal's exceptions | corrected |
| m | the chain rows' source and the renamed booleans were not in the deviation list | D-8, D-9 |

### The second independent read (2026-10-04, relayed by the coordinator): no blocker, no major, five minor points

| # | Finding | Disposition |
|---|---|---|
| 1 | an expiry or a clock reversal between the create and the first write left an empty or partial `secret.env` under the final name, blocking every retry | the file stays only on a complete run: every failure after the create withdraws it, by a removal the gate does not stop (D-11, section 6); tests at three stages × two refusals; mutants F23, F39 |
| 2 | `withdraw()` did not re-check the directory, while a `PARENT_REPLACED` at the readback left a complete secret; the "PARENT_REPLACED off the stop list" equivalence claim was wrong | one rule for all paths (withdraw through the held directory descriptor, `directory_at_the_signed_path` said); the claim removed from `mutants.py`; mutants F22, F40, F41, F42, F43 |
| 3 | the bare name gave `SECRET_ENVIRONMENT_SHAPE`, an empty value `SECRET_VALUE_SHAPE`: one bit | both `SECRET_VALUE_SHAPE` (first read) / a change (second read), one receipt; test; mutant W32 |
| 4 | the inspects are not bound to the ID (the CLI also matches a 64-hex argument against names) | the containers are listed again after the second read (`WORKER_CHANGED_DURING_READ`); tests in four ways; mutants W33–W35 |
| 5 | `ENOSPC` at the write distinguishes lines longer than the free space | declared (section 8) |

## 14. Reproduce (offline)

```
cd D/k3_secret_env
shasum -a 256 -c SHA256SUMS
/usr/bin/python3 -B seal.py check                                  # SEAL_OK
/usr/bin/python3 -B ../core_k3/assemble.py --check .               # BUILD_EQUAL
/usr/bin/python3 -B -m pytest -p no:cacheprovider -q --basetemp ../work/k3/pt39 tests
W/night23-test-venv/bin/python -B -m pytest -p no:cacheprovider -q --basetemp ../work/k3/pt312 tests
/usr/bin/python3 -B mutation/mutate.py run                         # copies under ../work/k3/mut-*; writes mutation/MUTATION_RUN.json
HOSTOPS_MUTATION_PYTHON=W/night23-test-venv/bin/python HOSTOPS_MUTATION_RECORD=MUTATION_RUN.py312.json /usr/bin/python3 -B mutation/mutate.py run
HOSTOPS_SEAL_PYTHON_2=W/night23-test-venv/bin/python /usr/bin/python3 -B seal.py write     # author only
```
