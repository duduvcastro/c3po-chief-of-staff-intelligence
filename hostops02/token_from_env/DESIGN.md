# HOSTOPS02 — token placement from the deploy environment file (`token_from_env`), revision 2

Offline work only. Nothing here was run on the host, pushed, or bound. Every hash named here was taken by command; where
this text and `build/ASSEMBLY.json`, `SHA256SUMS` or the mutation records differ, the files prevail. Revision 2 answers
the security review and the conformance review of revision 1 (seal `91ccd6b1…`, commit `0f306b7e`); CONTRACT.txt
section 11 maps every finding to what changed or why it did not.

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
   environment file `.env` in it (regular, one link, not world-writable, owned by root or by the owner of the deploy
   directory, at most 65536 bytes, unchanged while read), the parse of that file, the time left, and the configuration
   directory proved again from `/`;
2. creates `token` **exclusively** relative to the held descriptor of `/etc/c3po-bar`
   (`O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC`, mode 0600 under umask 0077), writes the value and one newline,
   fsyncs the file, checks its metadata through the descriptor, fsyncs the directory;
3. reads the file back: the directory proved again from `/`, the name opened again without following a link, the same
   inode, uid 0, gid 0, mode 0600, one link, size within 1–4096, and the bytes equal to what was written (compared in
   memory);
4. if any step after the creation fails, removes the file **it created**, and only while the name still shows the inode
   it holds with one link (section 6; a declared exception to rule 4 of the core).

It never reads the environment of a process (`os.environ` is not named), never runs `docker` (no `inspect`, no `exec`,
no runner part at all), starts no process, opens no socket, never overwrites, renames, chmods, chowns or truncates
anything, and never touches a token file that exists (a refusal before any effect). The value never reaches an argv, an
environment variable, a log, a receipt or an exception: the receipt carries listed codes, booleans and identity rows
only — never the value, a digest of it, its length or a line count.

What this source departs from, all of it covered by the owner's decision and put to the co-auditor (CONTRACT D6): the
README places the token by hand and this program places it; the program reads the content of `.env` and reads back the
content of the token file, once each and in memory, where ORD:25 says only the supervisor reads the content; and the
first sentence of README line 207 ("This unit does **not** use it") stops being true once the token file holds the
`.env` key.

## 2. Class, dates, window, evidence

- `WRITES_ALLOWED=True`, `ACTIVATION_ALLOWED=False` (no unit is switched).
- The core has no date class of exactly two days. The source names `WRITE_WEEKEND` (2026-10-02, 03, 04: the dispatcher
  carries that literal) and narrows it in `validate_plan` to `TOKEN_DAYS=('2026-10-03','2026-10-04')`: a window on
  2026-10-02 is refused `WINDOW_NOT_ON_A_TOKEN_DAY` by the source and, before any claim, by the dispatcher's local
  authentication. The conformance test of the date scope is replaced by one that asserts exactly this.
- `MAX_GATE_SPAN_SECONDS=900`.
- **When the file must exist.** The Sunday read L5 of the A1 (`once-l5-20261004-a`, already bound: window
  2026-10-04 11:15–12:15 UTC, 08:15–09:15 BRT, sent in any case) reads the token's metadata. The window of this run is
  therefore bound to end **no later than 2026-10-04T11:15:00Z**, and on 2026-10-03 UTC when it can (CONTRACT section 4).
  That instant is a rule of the binding, not a refusal of the source (CONTRACT D10): a placement after it is still one
  Monday's first claim can use, and only the owner decides it.
- Evidence: `GO_READONLY_HOSTOPS_PRECHECK_01` (the boot and the `/etc` rows) and
  `GO_WRITE_SUPERVISOR_READER_PROVISION_01` (supervisor operation 2: the ledger row `SUP_CONFIG`, the identity of
  `/etc/c3po-bar`).

## 3. The plan (three keys) and where each comes from

| Key | Content | From |
|---|---|---|
| `config_chain` | rows `/`, `/etc`, `/etc/c3po-bar` (path, device, inode, uid, gid, mode) | `/` and `/etc`: the chain rows of the receipt of operation 2 (`chains.ETC`) or of the precheck of the same boot; `/etc/c3po-bar`: the ledger row `SUP_CONFIG` of operation 2 (`observed.device`, `observed.inode`, uid 0, gid 0, mode 0700) |
| `deploy_directory` | the deploy tree, a clean absolute path | the K6a/K11 contracts (the compose env file is `<deploy>/.env`) |
| `evidence_boot_id_sha256` | 64 hex | the precheck receipt of the same boot |

`validate_plan` refuses from the bytes, before any claim: a chain row not root-owned or writable by group or other
(`CHAIN_ROW_UNSAFE`), a setgid configuration directory (`PARENT_SETGID`), a configuration directory whose gid is not 0
or whose mode is not 0700 (`CONFIG_DIRECTORY_NOT_ROOT_0700`), a deploy directory that is not a clean path or that
contains or lies inside `/etc/c3po-bar` (`DEPLOY_DIRECTORY_INVALID`), an unbound boot (`EVIDENCE_BOOT_UNBOUND`), a
window outside the two days.

The deploy tree's rows and the environment file's owner and mode are in no receipt yet. They are therefore **not**
signed: the run walks them itself (`descend`, `O_NOFOLLOW` at every component) and judges what it read with the family's
rule (`validate_chain(observed, deploy, open_root=deploy)`): every component above the deploy directory root-owned and
**not writable by group or other** (it may be readable: `/opt` at 0755 is accepted), no component writable by any user
without the sticky bit, every component a directory and no link (`DEPLOY_CHAIN_UNSAFE_ABOVE_THE_DEPLOY_DIRECTORY`,
`DEPLOY_CHAIN_WORLD_WRITABLE`, `DEPLOY_CHAIN_SYMLINK`, …). The receipt keeps booleans of that walk only (`deploy_chain`),
never the rows. The environment file must be regular, have **one link** (`ENV_FILE_LINKED`: a hard link elsewhere
would be a second name for these bytes), not be world-writable, and be owned by root or by the owner of the deploy
directory (the deploy pipeline of the release rewrites it as the deploy user, mode 0600). Whether group or other may
read it is reported (`not_readable_by_group_or_other`) and never refuses: it is the exposure as found.

## 4. The environment file: which statements, and why exactly these

The file is the one docker compose reads for every backend service (`c3po/compose.yml` line 32, `env_file: ../.env`;
the deploy runs `docker compose --env-file .env -f c3po/compose.yml`). The value the backend uses is the value compose's
dotenv parser gives the container. The source must take a definition **exactly where compose would**, and refuse
whenever it cannot be sure of that — including under the older parsers a host could still run. No compose binary was
available offline: the rules use the behaviour the reviewers and the author know of compose-go v2 and of the older
godotenv-derived parser, and the Linux proof compares the accepted files with the runner's own `docker compose config`
(section 9). The host's compose version is not in any receipt (section 10).

**Statement boundaries** (`token_definitions`, rules `ENV_RULES`). A file with a carriage return or a NUL byte is refused
whole (CRLF handling differs between versions). Every line must be one of:

- blank (spaces and tabs) or a comment (`#` after spaces and tabs) — every parser skips both;
- a statement: optional spaces/tabs, optional `export` + spaces/tabs (compose strips `^export\s+`), a name of
  `A-Z a-z 0-9 _ . - [ ]` (compose's ASCII name set; a non-ASCII letter compose would accept is refused here),
  optional spaces/tabs, **`=` or `:`** (compose accepts the YAML-style colon), and a value.

**A name without `=` or `:` is refused** (revision 2): compose v2 takes it from its own environment, while an older
parser took the next line as its value — `FOO` followed by `MASSIVE_API_TOKEN=…` defines no token there. Any other
line refuses the whole file (`ENV_FILE_SYNTAX_UNSUPPORTED`).

The **value of another name** must end where every parser ends it. A value that begins with a quote may span lines in
compose; it is accepted only when it closes on the same line at the next quote of the same kind and is followed by
nothing but spaces, tabs and an optional comment — text after a closing quote is a **new statement** for compose
(`A="x" MASSIVE_API_TOKEN=y` defines `MASSIVE_API_TOKEN`). Inside it, revision 2 accepts a backslash before any
character but a backslash or that quote (`"…\n…"` in a PEM-like value): the first quote of its kind then closes the value
in the old parser (which skips a quote preceded by a backslash) and in the new one (which consumes escape pairs) alike.
Two backslashes, or one just before that quote, are where they differ, and are refused. A value that does not begin with
a quote ends at the end of its line in every version; it must not begin with a vertical tab, a form feed or a byte
above 127, because compose trims `\v`, `\f`, U+0085 and U+00A0 before looking for a quote. Values of other names are
otherwise not judged (they may hold spaces, `#`, `$`, quotes or UTF-8).

**Definitions.** A statement whose name equals `MASSIVE_API_TOKEN` or `C3PO_MASSIVE_API_TOKEN` **without regard to case**
is a definition: pydantic-settings matches environment names case-insensitively (`config.py` line 20, no
`case_sensitive`), so `massive_api_token=…` would reach the backend too. Every definition must be the plain form
`NAME=VALUE` — the name in capitals at the start of the line, no `export`, `=` with no space on either side; anything
else is `ENV_TOKEN_DEFINITION_NOT_PLAIN`. The value of a definition is **not** judged by the boundary rules of other
values: it is judged by the grammar alone (below), so whatever it begins with or holds, its only codes are the grammar's
and the disagreement's (revision 2; before, a quote or a non-ASCII first byte gave the syntax code).

**The name anywhere else** (revision 2). No line but a definition and the comments may hold `massive_api_token` in any
case — not inside or around another name (`MASSIVE_API_TOKEN_OLD`, `OLD_MASSIVE_API_TOKEN`), not in a value of another
name (`OTHER=${MASSIVE_API_TOKEN}`, `A=b\tMASSIVE_API_TOKEN=…`): `ENV_TOKEN_NAME_OUTSIDE_A_PLAIN_DEFINITION`. A parser
that ended unquoted values at white space would read a definition in `A=b\tMASSIVE_API_TOKEN=H`; compose does not, and
neither does this source, but the file is refused rather than trusted to be read by compose only. The search lower-cases
ASCII and reads U+212A (the Kelvin sign) as `k`: it is the one character outside ASCII that `str.lower()` turns into an
ASCII letter, so `MASSIVE_API_TOKEN` is the name for pydantic. (A name with it is refused anyway: names are
ASCII.) The value of a definition is not searched: the grammar holds `_` and `=`, and a value that happens to hold the
name is still the value.

Decisions inside these rules:

- **`export` is refused, not handled.** Compose v2 strips it and would give the same value, but `docker run --env-file`
  (the Docker CLI's own parser) does not, and a line written with `export` is a line written for a shell, where quoting and
  expansion differ. Refusing costs nothing on the host; accepting would rest on one parser's behaviour.
- **A quoted value is refused** (`ENV_TOKEN_VALUE_GRAMMAR`): with no backslash and no `$` compose would give the bytes
  between the quotes, but that rests on the escape and expansion rules of the version on the host. The example files of
  the release (`c3po/.env.example` line 40, `.env.example` line 50) and every line of them are the plain form.
- **The colon form, spaces around `=`, a leading space and case variants** are refused for the same reason.

At least one definition is required (`ENV_TOKEN_ABSENT`). **All definitions of both names must be byte-equal**
(`ENV_TOKEN_DEFINITIONS_DISAGREE`): compose keeps the last definition of a name, the backend takes
`C3PO_MASSIVE_API_TOKEN` first when both are present (pydantic `AliasChoices` order); with every definition equal the
question of which one wins does not arise. The same line twice is accepted (harmless; the brief's "exactly one line" is
read as one value). The template line `MASSIVE_API_TOKEN=` left above a filled one is refused as a disagreement:
accepting it would mean deciding which definition the backend uses (CONTRACT D11).

**The value** must match `[A-Za-z0-9._~+/=-]{16,512}` to the end of its line: no quote, space, tab, `#`, `$`,
backslash or byte above 127, so that compose's unquoted handling (inline ` #` comment, right trim, `$` expansion) cannot
change it, and it is one non-empty ASCII line, which is what the supervisor needs after `strip()`
(`r2d2_v2_massive_supervisor.py` lines 114–115). 16 is a floor against placeholders (the provider's keys are 32
characters; it does not stop a long placeholder); 512 keeps the file far below the supervisor's 4096. Every refusal of
the value has the one code `ENV_TOKEN_VALUE_GRAMMAR`, so the code says nothing of the length or the characters.

Offline evidence of these rules (the reviewers' scratch scripts, with ports of the parsers written from memory, not
authoritative; run by the author on revision 2): against a port of compose-go v2, no accepted file gives the backend
another value or no value (150 000 random files, 20 000 generated ones, every listed one); against ports of compose-go
v2 and of the older parser, the same (600 000 random files of the conformance reviewer's pieces). Against a third,
hypothetical parser that ends unquoted values at white space, no accepted file gives another value; some give **no**
value (a value of another name with a space or a no-break space, whose rest that parser would read as a bare name
swallowing the next line). That parser is not compose and is not known to be on the host; refusing every value with a
space would refuse ordinary files.

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
table, `SUPERVISOR_TOKEN`), it would make every later delivery refuse (exclusive creation), and the owner cannot remove
it by hand. So when a step after a successful creation fails — a write error or a write of nothing, an fsync, a
metadata or readback mismatch, a failed readback, or any unexpected exception — the source **removes the file it
created** (`withdraw`), and only when: the name, looked at again in the held directory, shows the device and inode of
the descriptor it holds, and that inode has one link. The removal goes through `mutate()`, the directory is fsynced
after it, and the receipt says `WITHDRAWN` (or `WITHDRAWN_NOT_DURABLE` when that fsync failed).

This is **a declared exception to rule 4 of the core** (CORE.md: nothing is removed "except the temporary of this run
once its identity is proved"): the object removed is the final name, not a temporary. It is signed in the scope
(`exceptions_to_the_core`, and `never`: "removal of anything but the token file this run created"), and the
co-auditor is asked to accept it explicitly (CONTRACT D3). The README (line 205) gives the removal of an abandoned token
file to the owner; this run removes only what it made in the same run, by identity, and never a file it did not create.

It is **never** withdrawn: after the GO expired or the clock went back (no further mutating call is allowed), after the
configuration directory was found replaced (the run stops touching a directory whose path no longer leads to it), when
the name shows another inode or a second link (someone else's object, or a hard link the run did not make). Then the
receipt says `LEFT_UNVERIFIED` with the reason, and `objects_left_by_this_run` is 1. When `fsync_file` is false too, the
file left may be **empty or partial** (an expiry or a clock step between the create and the first write; the death of
the process there): the Sunday metadata readback sees `size_within_1_4096` false for an empty one, and its removal needs
an operation prepared for it (CONTRACT section 6). A run that withdrew its file is still a PARTIAL (a mutating call
succeeded), never a refusal.

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
| `deploy_chain` | booleans: walked without following a link; root-owned and not group- or other-writable above the deploy directory; no component world-writable without sticky |
| `environment_file` | booleans: present, regular, not readable by group or other (reported only), not world-writable, single link, owner root or the deploy directory's, within the size bound, unchanged during read, syntax within the subset, every definition plain, `names_defined` (one boolean per name), definitions agree, value grammar met |
| `precheck` | `token_file_absent`, `seconds_left_before_the_creation` |
| `token_file` | `path state code errno created fsync_file fsync_directory device inode regular uid_0 gid_0 mode_0600 single_link size_within_1_4096 on_the_device_of_the_directory readback_same_inode readback_bytes_equal_what_was_written meets_the_supervisor_file_rules withdrawn withdrawal_code withdrawal_errno fsync_directory_after_withdrawal` |
| `objects_left_by_this_run` | 1 placed or left, 0 nothing, null when the creation itself was uncertain |
| `pre_existing_objects_modified`, `phase_reached`, `readback` | |

**Codes are listed** (revision 2). The core's `code_of()` lets through any `Refused` whose text has the shape of a code
(`[A-Z][A-Z0-9_]{0,79}`). No path of this source builds a `Refused` from file bytes, but a later edit could, and a
token in capitals has that shape. `finish()` therefore maps `code`, `token_file.code` and `token_file.withdrawal_code`
through `RECEIPT_CODES` (every code this run can write, signed in the scope as `receipt_codes`); any other text becomes
`UNLISTED_CODE`. A static test checks the list both ways against the source.

Outcomes: `TOKEN_PLACED_METADATA_VERIFIED` (exit 0), `PARTIAL_SEE_TOKEN_FILE_STATE` (exit 2), `REFUSED_NOTHING_CHANGED`
(exit 1), `RECEIPT_REDUCED_STATE_REQUIRES_READBACK`, `PARTIAL_STATE_UNKNOWN_TOKEN_FILE_MAY_EXIST` (an exception escaped).
`token_file.device`/`inode` identify the file for the Sunday readback; they are metadata of the file, not of the value.

## 8. Secrets in memory, and what a crash would expose

Several **immutable copies** of the value exist while the run lasts, and Python cannot overwrite any of them: the bytes
`read_regular()` read from `.env` (its blocks, and their join), the bytes of the readback, and the interpreter's own
transient objects. Revision 2 removes two of the copies revision 1 made: the parser looks at the lines through a
`memoryview` of the file (the line of a definition is never copied; a line of another name is copied, because it is
lower-cased for the search of the name) and takes the definition's offsets from the match instead of its groups.
`token_content()` builds one `bytearray` (the value and the newline) from a view; the write is made through a
`memoryview` of it, and it is overwritten with zeros in the `finally` of `perform` (`zero`). That is the only buffer
cleared. Memory the copies leave is not cleared by the allocator either (values of up to 512 bytes sit in the small-object
pools). Every refusal is `Refused(<constant code>)`; the parser raises nothing else and no exception carries a byte of
the file (tested: `args`, `repr`, `__cause__`, `__context__`).

**A crash of the interpreter** while the run lasts would hand its whole image — every secret of `.env`, not only the
token — to the kernel's core handler; the precheck receipt L1 shows that handler is a pipe (a crash collector). The run
cannot lower `RLIMIT_CORE` or set `PR_SET_DUMPABLE`: the frozen core forbids the operation part any import beyond its
parts' (`assemble.py`, `IMPORTS_OF`/`OPERATION_IMPORTS`: no `resource`) and any `os` member beyond the open flags, and
the remote command is the core's fixed `sudo -n /usr/bin/python3 -I -B -`. This is a residual risk (CONTRACT D9);
closing it is a core revision (a part that sets the limit before the payload runs), not this operation's.

## 9. Tests, mutation, Linux proof

- `tests/envfiles.py`: the accepted and refused environment files, rule by rule, and a deterministic generator of more
  files of the same kinds (comments, blanks, `export`, colons, spaces, quotes, backslashes, `$`, `#`, UTF-8 around one or
  more plain definitions). Shared by the parser tests and the compose agreement.
- `tests/test_token_from_env.py` (emulated host): the complete run; the refusals before the creation with the tree
  unchanged and no mutating call; the accepted states and the facts of the environment file up to a refusal; every
  failure after the creation (withdrawn, left, uncertain, expiry, death); the listed and refused files; 300 generated
  files; the value of a definition judged by the grammar alone; the plan; the exact effects; the receipt's members; a
  code-shaped refusal raised by the host at three points, reported as `UNLISTED_CODE`. **The receipt does not depend on
  the token**: two runs that differ only in the token, of different lengths and first bytes, give byte-identical
  receipts (complete, withdrawn, refused for presence, for the grammar, for disagreement).
- `tests/test_conformance.py`: the family's 121 tests, one replaced (the date scope).
- `tests/test_native.py`: the source's own `Native` with real system calls on a temporary tree (`oslevel.Substitute`);
  the withdrawal with a real `unlink`; a real second hard link to `.env` refused; and a child interpreter under an audit
  hook whose standard output and error are scanned for every substring of four characters or more of the fake token (and
  the literal `FAKE-TOKEN-FOR-TESTS-0001` whole); its audit events show one open for writing (the create) and no
  process, socket, environment, rename, chmod or removal.
- `tests/test_static_pins.py`: the README lines, the supervisor's `private_bytes` and token read, `config.py`, the
  compose `env_file`, against a tree of dd4ec4bb (hash-pinned); the scope's wording; the list of receipt codes both ways.
- Mutation: every mutant of the operation part killed on Python 3.9.6 and 3.12.14 (`mutation/`); the equivalent
  replacements left out are named in `mutation/mutants.py`.
- `linux_root/run.sh` (throwaway GitHub runner, as root; never run by the author): the core's suite and this one as root
  and as the user, then `token_shape.py` on the real filesystem (the complete run, the access time of the environment
  file unchanged — only the kernel's `O_NOATIME` explains it —, a second run refused, a token of another length giving the
  same receipt, a full tmpfs on `/etc/c3po-bar` at the write with the file withdrawn by identity, six refusals including
  a real second hard link and the name in another value, the literal fake value), then `--compose-agreement`, now a
  **required** stage: every listed file and the first 500 generated files the parser accepts (seed 20261003), each given
  to the runner's `docker compose config`; for each accepted file the value the backend would take (the first of its two
  names present), each of the two names, and no other name equal to one of them for a case-insensitive reader. It fails
  on any disagreement, on a listed accepted file compose refuses, and when compose is not there. The job uses the network
  once, for `apt-get install python3-pytest`, as the core's own `run.sh` does.

## 10. Proven, emulated, unproven

- **Real on the workstation** (macOS, an ordinary user reported as root): the exclusive create relative to a held
  descriptor, fsync of a file and of a directory, the readback by a new open, `lstat` of a link, a second hard link
  refused, the removal by identity.
- **Emulated only**: uid 0 and device numbers, every errno injection, the death of the process.
- **Unproven until the Linux job runs**: real uid 0, the kernel's `O_NOATIME` on the environment file, Linux errno values,
  ENOSPC from a real filesystem; compose's reading of the accepted files on the runner's compose version.
- **Unproven until the host runs it**: the host's `.env` itself (its form, its owner and mode, that it holds the key);
  the host's compose version, which no receipt records (the agreement is shown for the runner's; the older parsers are
  covered only by the offline ports of section 4); that the value in the file is the value the running containers have
  (they read the file at their last recreate; the source cannot ask docker without putting the value in an argv); that
  the key is valid for the provider's websocket stream (nothing before Monday's first claim shows it); the root
  filesystem's behaviour under `/etc/c3po-bar`.
- **Residual, by design**: a core file of a crash (section 8); copies of the value in freed memory (section 8).
