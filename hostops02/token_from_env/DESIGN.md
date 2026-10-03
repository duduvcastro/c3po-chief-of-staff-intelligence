# HOSTOPS02 — token placement from the deploy environment file (`token_from_env`)

Offline work only. Nothing here was run on the host, pushed, or bound. Every hash named here was taken by command; where
this text and `build/ASSEMBLY.json`, `SHA256SUMS` or the mutation records differ, the files prevail.

| What | Value |
|---|---|
| Operation | `GO_WRITE_HOSTOPS02_TOKEN_FROM_ENV_01`, class WRITE, `WRITE_WEEKEND` narrowed to 2026-10-03 and 2026-10-04 UTC |
| Core | generation `4c24c5cf…d0d6` (`assemble.py`), seal `73fb546b…c9b1` (`CORE_SHA256SUMS`); unchanged |
| Parts carried | `core`, `parents`, `files` (no runner: this source starts no process) |
| Why it exists | owner decision `DUDU_DECISION_TOKEN_BY_PROGRAM.json` (sha256 `739b4964…fcb0`): the provider token of the supervisor is placed by a signed single-use program, from the key already on the server, instead of the manual recipe of the README |

## 1. What the source does, and what it never does

The supervisor of the Massive minute-bar producer reads its provider token from `/etc/c3po-bar/token` (README of
`c3po/deployment/massive-supervisor` at dd4ec4bb, "Token procedure", lines 159–207). The owner cannot run the manual
recipe of that section and decided that a program places the token, using **the same key the server already holds**:
`MASSIVE_API_TOKEN` in the deploy environment file (README line 207; the backend accepts `C3PO_MASSIVE_API_TOKEN` or
`MASSIVE_API_TOKEN`, `c3po/backend/app/config.py` lines 116–118).

The source, in one signed run:

1. looks at everything before any creation: the executor (uid and gid 0), the umask (0077), the boot of the evidence,
   the configuration directory `/etc/c3po-bar` walked from `/` and held (identity signed from the receipt of supervisor
   operation 2), the absence of `token` in it, the deploy directory walked from `/` without following a link, the
   environment file `.env` in it (regular, not world-writable, owned by root or by the owner of the deploy directory,
   at most 65536 bytes, unchanged while read), the parse of that file, the time left, and the configuration directory
   proved again from `/`;
2. creates `token` **exclusively** relative to the held descriptor of `/etc/c3po-bar`
   (`O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC`, mode 0600 under umask 0077), writes the value and one newline,
   fsyncs the file, checks its metadata through the descriptor, fsyncs the directory;
3. reads the file back: the directory proved again from `/`, the name opened again without following a link, the same
   inode, uid 0, gid 0, mode 0600, one link, size within 1–4096, and the bytes equal to what was written (compared in
   memory);
4. if any step after the creation fails, removes the file **it created**, and only while the name still shows the inode
   it holds with one link (section 6).

It never reads the environment of a process (`os.environ` is not named), never runs `docker` (no `inspect`, no `exec`,
no runner part at all), starts no process, opens no socket, never overwrites, renames, chmods, chowns or truncates
anything, and never touches a token file that exists (a refusal before any effect). The value never reaches an argv, an
environment variable, a log, a receipt or an exception: the receipt carries codes, booleans and identity rows only —
never the value, a digest of it, its length or a line count (README line 164, ORD:25).

## 2. Class, dates, window, evidence

- `WRITES_ALLOWED=True`, `ACTIVATION_ALLOWED=False` (no unit is switched).
- The core has no date class of exactly two days. The source names `WRITE_WEEKEND` (2026-10-02, 03, 04: the dispatcher
  carries that literal) and narrows it in `validate_plan` (`op.py:166`) to `TOKEN_DAYS=('2026-10-03','2026-10-04')`
  (`op.py:27`): a window on 2026-10-02 is refused `WINDOW_NOT_ON_A_TOKEN_DAY` by the source and, before any claim, by the
  dispatcher's local authentication. The conformance test of the date scope is replaced by one that asserts exactly
  this (`tests/test_conformance.py`).
- `MAX_GATE_SPAN_SECONDS=900`. The token must exist before Sunday's readback (2026-10-04 09:50 BRT = 12:50 UTC).
- Evidence: `GO_READONLY_HOSTOPS_PRECHECK_01` (the boot and the `/etc` rows) and
  `GO_WRITE_SUPERVISOR_READER_PROVISION_01` (supervisor operation 2: the ledger row `SUP_CONFIG`, the identity of
  `/etc/c3po-bar`).

## 3. The plan (three keys) and where each comes from

| Key | Content | From |
|---|---|---|
| `config_chain` | rows `/`, `/etc`, `/etc/c3po-bar` (path, device, inode, uid, gid, mode) | `/` and `/etc`: the chain rows of the receipt of operation 2 (`chains.ETC`) or of the precheck of the same boot; `/etc/c3po-bar`: the ledger row `SUP_CONFIG` of operation 2 (`observed.device`, `observed.inode`, uid 0, gid 0, mode 0700) |
| `deploy_directory` | the deploy tree, a clean absolute path | the K6a/K11 contracts (the compose env file is `<deploy>/.env`) |
| `evidence_boot_id_sha256` | 64 hex | the precheck receipt of the same boot |

`validate_plan` (`op.py:159-166`) refuses from the bytes, before any claim: a chain row not root-owned or writable by
group or other (`CHAIN_ROW_UNSAFE`), a setgid configuration directory (`PARENT_SETGID`), a configuration directory whose
gid is not 0 or whose mode is not 0700 (`CONFIG_DIRECTORY_NOT_ROOT_0700`), a deploy directory that is not a clean path or
that contains or lies inside `/etc/c3po-bar` (`DEPLOY_DIRECTORY_INVALID`), an unbound boot (`EVIDENCE_BOOT_UNBOUND`), a
window outside the two days.

The deploy tree's rows and the environment file's owner and mode are in no receipt yet. They are therefore **not**
signed: the run walks them itself (`descend`, `O_NOFOLLOW` at every component) and judges what it read with the family's
rule (`validate_chain(observed, deploy, open_root=deploy)`): every component above the deploy directory root-owned and
closed to group and other, no component writable by any user without the sticky bit, every component a directory and no
link. The receipt keeps booleans of that walk only (`deploy_chain`), never the rows.

## 4. The environment file: which statements, and why exactly these

The file is the one docker compose reads for every backend service (`c3po/compose.yml` line 32, `env_file: ../.env`;
the same file is compose's `--env-file`). The value the backend uses is the value compose's dotenv parser gives the
container. The source therefore must take a definition **exactly where compose would**, and refuse whenever it cannot be
sure of that. No compose binary was available offline; the rules below use only behaviour on which every compose v2
dotenv parser (compose-go, before and after its rewrite of escapes) agrees, and the Linux proof compares the accepted
files with the runner's own `docker compose config` (section 9).

**Statement boundaries** (`op.py:118-138`, rules `ENV_RULES`, `op.py:56-67`). A file with a carriage return or a NUL byte
is refused whole (CRLF handling differs between versions). Every line must be one of:

- blank (spaces and tabs) or a comment (`#` after spaces and tabs) — compose skips both;
- a statement: optional spaces/tabs, optional `export` + spaces/tabs (compose strips `^export\s+`), a name of
  `A-Z a-z 0-9 _ . - [ ]` (compose's ASCII name set; a non-ASCII letter compose would accept is refused here), optional
  spaces/tabs, then nothing (a name compose takes from its own environment) or `=` / `:` (compose accepts the YAML-style
  colon) and a value.

A **value that begins with a quote** may span lines in compose; it is accepted only when it closes on the same line at
the next quote of the same kind, holds no backslash (the old and the new compose-go differ on `\"` and `\\`), and is
followed by nothing but spaces, tabs and an optional comment — text after a closing quote is a **new statement** for
compose (`A="x" MASSIVE_API_TOKEN=y` defines `MASSIVE_API_TOKEN`), so it is refused. An **unquoted value** ends at the end
of its line in every version; it must not begin with a vertical tab, a form feed or a byte above 127, because compose
trims `\v`, `\f`, U+0085 and U+00A0 before looking for a quote. Any other line refuses the whole file
(`ENV_FILE_SYNTAX_UNSUPPORTED`): a boundary that differs from compose's could hide a definition. Lines of other names
are otherwise not judged (their values may hold spaces, `#`, `$`, quotes or UTF-8).

**Definitions.** A statement whose name equals `MASSIVE_API_TOKEN` or `C3PO_MASSIVE_API_TOKEN` **without regard to case**
is a definition: pydantic-settings matches environment names case-insensitively (`config.py` line 20, no
`case_sensitive`), so `massive_api_token=…` would reach the backend too. Every definition must be the plain form
`NAME=VALUE` — the name in capitals at the start of the line, no `export`, `=` with no space on either side; anything
else is `ENV_TOKEN_DEFINITION_NOT_PLAIN` (`op.py:135`). Decisions inside this rule:

- **`export` is refused, not handled.** Compose v2 strips it and would give the same value, but `docker run --env-file`
  (the Docker CLI's own parser) does not, and a line written with `export` is a line written for a shell, where quoting and
  expansion differ. Refusing costs nothing on the host; accepting would rest on one parser's behaviour.
- **A quoted value is refused** (`ENV_TOKEN_VALUE_GRAMMAR`): with no backslash and no `$` compose would give the bytes
  between the quotes, but that rests on the escape and expansion rules of the version on the host, which was not run
  here. The example files of the release (`c3po/.env.example` line 40, `.env.example` line 50) and every line of them
  are the plain form.
- **The colon form, spaces around `=`, a leading space, case variants and the name without a value** are refused for
  the same reason.

At least one definition is required (`ENV_TOKEN_ABSENT`, `op.py:142`). **All definitions of both names must be
byte-equal** (`ENV_TOKEN_DEFINITIONS_DISAGREE`, `op.py:146`): compose keeps the last definition of a name, the backend
takes `C3PO_MASSIVE_API_TOKEN` first when both are present (pydantic `AliasChoices` order); with every definition equal
the question of which one wins does not arise, and a file with the same line twice is still accepted.

**The value** must match `[A-Za-z0-9._~+/=-]{16,512}` to the end of its line (`op.py:48`, `op.py:147`): no quote, space,
tab, `#`, `$`, backslash or byte above 127, so that compose's unquoted handling (inline ` #` comment, right trim, `$`
expansion) cannot change it, and it is one non-empty ASCII line, which is what the supervisor needs after `strip()`
(`r2d2_v2_massive_supervisor.py` lines 114–115). 16 is a floor against placeholders (the provider's keys are 32
characters); 512 keeps the file far below the supervisor's 4096. Every refusal of the value has the one code
`ENV_TOKEN_VALUE_GRAMMAR`, so the code says nothing of the length or the characters.

## 5. The creation (and why not `create_file`)

The core's `create_file` puts the hash and the size of the bytes into its ledger row (CORE.md section 10: "A secret
delivery must not use `create_file`"). The source therefore makes the creation itself with the files part's `Native`
calls, each through `mutate()`: one exclusive create of the final name (`O_EXCL|O_NOFOLLOW`, the semantics of the
README recipe's `set -o noclobber` + `umask 077`), the writes from a `memoryview` of a `bytearray` (short writes
continued, a write of zero bytes is a failure), fsync of the file, `fstat` of the descriptor (regular, uid 0, gid 0,
0600, one link, the size written, the device of the directory), fsync of the directory, then the readback by a new open
of the name. The final name is created directly rather than through a temporary and a link: the README's own recipe
does so, the file is a few dozen bytes written in one call, and a temporary would leave a second file holding the value
in `/etc/c3po-bar` if the process died between the link and its removal.

## 6. A failure after the creation: the withdrawal (the decision, and its limits)

A file left half-written at `/etc/c3po-bar/token` would make the supervisor's first attempt fail after its claim (README
table, `SUPERVISOR_TOKEN`), and it would make every later delivery refuse (exclusive creation). So when a step after a
successful creation fails — a write error or a write of nothing, an fsync, a metadata or readback mismatch, a failed
readback, or any unexpected exception — the source **removes the file it created** (`withdraw`, `op.py:255-277`), and
only when: the name, looked at again in the held directory, shows the device and inode of the descriptor it holds, and
that inode has one link. The removal goes through `mutate()`, the directory is fsynced after it, and the receipt says
`WITHDRAWN` (or `WITHDRAWN_NOT_DURABLE` when that fsync failed). This is the core's rule 4 ("nothing … removed, except the
temporary of this run once its identity is proved") applied to the one object this run created.

It is **never** withdrawn: after the GO expired (no further mutating call is allowed), after the configuration directory
was found replaced (the run stops touching a directory whose path no longer leads to it), when the name shows another
inode or a second link (someone else's object, or a hard link the run did not make). Then the receipt says
`LEFT_UNVERIFIED` with the reason, and `objects_left_by_this_run` is 1. A run that withdrew its file is still a PARTIAL
(a mutating call succeeded), never a refusal.

## 7. The receipt

From `envelope()`/`seal()`: `schema operation status outcome code scope_sha256 core_sha256 activation_performed
daemon_reload_performed secret_bytes_in_receipt ready size_reductions metadata_sha256` and the four document hashes and
`host_binding_sha256`. Then:

| Member | Content |
|---|---|
| `effects` | the literal object the authority and the GO carry |
| `observed_at`, `clock` | the instants of the run |
| `mutating_calls` | issued, succeeded, failed_nothing_changed, uncertain |
| `config_directory` | `rows` (the signed rows of `/etc/c3po-bar` as walked), `pinned` |
| `deploy_chain` | booleans: walked without following a link; root-owned and closed above the deploy directory; no component world-writable without sticky |
| `environment_file` | booleans: present, regular, not world-writable, owner root or the deploy directory's, within the size bound, unchanged during read, syntax within the subset, every definition plain, `names_defined` (one boolean per name), definitions agree, value grammar met |
| `precheck` | `token_file_absent`, `seconds_left_before_the_creation` |
| `token_file` | `path state code errno created fsync_file fsync_directory device inode regular uid_0 gid_0 mode_0600 single_link size_within_1_4096 on_the_device_of_the_directory readback_same_inode readback_bytes_equal_what_was_written meets_the_supervisor_file_rules withdrawn withdrawal_code withdrawal_errno fsync_directory_after_withdrawal` |
| `objects_left_by_this_run` | 1 placed or left, 0 nothing, null when the creation itself was uncertain |
| `pre_existing_objects_modified`, `phase_reached`, `readback` | |

Outcomes: `TOKEN_PLACED_METADATA_VERIFIED` (exit 0), `PARTIAL_SEE_TOKEN_FILE_STATE` (exit 2), `REFUSED_NOTHING_CHANGED`
(exit 1), `RECEIPT_REDUCED_STATE_REQUIRES_READBACK`, `PARTIAL_STATE_UNKNOWN_TOKEN_FILE_MAY_EXIST` (an exception escaped).
`token_file.device`/`inode` identify the file for the Sunday readback; they are metadata of the file, not of the value.

## 8. Secrets in memory

The value exists in the bytes read from the file (immutable; dropped after the parse), in one `bytearray` (the value
and the newline) from which the write is made through a `memoryview`, and in the bytes of the readback (dropped after the
comparison). The `bytearray` is overwritten with zeros in the `finally` of `perform` (`zero`, `op.py:152-156`): best
effort — Python cannot overwrite the immutable buffers the interpreter made. Every refusal is `Refused(<constant code>)`;
the parser raises nothing else and no exception carries a byte of the file (tested: `args`, `repr`, `__cause__`,
`__context__`). The core's emulation asserts `bytes` for `write`; the tests use a subclass that accepts the view
(`tests/tok.py`, `TokenHost`), the real `os.write` takes it as it is (`tests/test_native.py`).

## 9. Tests, mutation, Linux proof

- `tests/test_token_from_env.py` (emulated host): the complete run; 21 refusals before the creation with the tree
  unchanged and no mutating call; the accepted states; every failure after the creation (withdrawn, left, uncertain,
  expiry, death); 11 accepted and 68 refused environment files rule by rule; the plan; the exact effects; the receipt's
  members. **The receipt does not depend on the token**: two runs that differ only in the token, of different lengths,
  give byte-identical receipts (complete, withdrawn, refused for presence, for the grammar, for disagreement).
- `tests/test_conformance.py`: the family's 121 tests, one replaced (the date scope).
- `tests/test_native.py`: the source's own `Native` with real system calls on a temporary tree (`oslevel.Substitute`);
  the withdrawal with a real `unlink`; and a child interpreter under an audit hook whose standard output and error are
  scanned for every substring of four characters or more of the fake token (and the literal `FAKE-TOKEN-FOR-TESTS-0001`
  whole); its audit events show one open for writing (the create) and no process, socket, environment, rename, chmod or
  removal.
- `tests/test_static_pins.py`: the README lines, the supervisor's `private_bytes` and token read, `config.py`, the
  compose `env_file`, against a tree of dd4ec4bb (hash-pinned).
- Mutation: 182 mutants of the operation part, every one killed on Python 3.9.6 and 3.12.14 (`mutation/`); the
  equivalent replacements left out are named in `mutation/mutants.py`.
- `linux_root/run.sh` (throwaway GitHub runner, as root; never run by the author): the core's suite and this one as root
  and as the user, then `token_shape.py` on the real filesystem (the complete run, the access time of the environment
  file unchanged — only the kernel's `O_NOATIME` explains it —, a second run refused, a token of another length giving the
  same receipt, a full tmpfs on `/etc/c3po-bar` at the write with the file withdrawn by identity, four refusals, the
  literal fake value), then `--compose-agreement`: for each file the parser accepts, the value the runner's
  `docker compose config` gives a throwaway service, compared with the parser's.

## 10. Proven, emulated, unproven

- **Real on the workstation** (macOS, an ordinary user reported as root): the exclusive create relative to a held
  descriptor, fsync of a file and of a directory, the readback by a new open, `lstat` of a link, the removal by identity.
- **Emulated only**: uid 0 and device numbers, every errno injection, the death of the process.
- **Unproven until the Linux job runs**: real uid 0, the kernel's `O_NOATIME` on the environment file, Linux errno values,
  ENOSPC from a real filesystem; compose's reading of the accepted files on the runner's compose version.
- **Unproven until the host runs it**: the host's `.env` itself (its form, its owner and mode, that it holds the key), the
  host's compose version (the agreement is shown for the runner's), that the value in the file is the value the running
  containers have (they read the file at their last recreate; the source cannot ask docker without putting the value in
  an argv), the root filesystem's behaviour under `/etc/c3po-bar`.
