# Capacity day — admission commit and the daily bar manifest

Offline candidate. Nothing here has been installed, mounted, dispatched or run on a host or in a container.

**Unverified on the host.** Every Docker and host behaviour described in this document comes from documentation, from the code and from offline tests. None of it has been observed on the production host or on any Docker engine. Statements marked *(unverified)* are the ones a reviewer could not support from the repository at all. "Not verified" near the end lists them together.

This directory holds deployment scripts. They are **not part of the pinned implementation package**: nothing under `c3po/backend/app` changes because of them and `implementation_package_sha` does not move. Each script is pinned by SHA-256 in the authorisation of the run that uses it, and it only imports and calls the packaged code of the deployed image.

| File | Role |
| --- | --- |
| `manifest_writer.py` | Runs in a container of the pinned image. Commits the day's capacity binding (`prepare-capacity-day`, through the packaged code) and publishes the supervisor's dated manifest from that binding. This document. |
| `capacity_day_documents.py` | Offline authoring tool for the day's documents (contract, GOs, views, configs). Described in `README.documents.md`, with its own tests; this document covers it only where the writer reads its output. |

## Open decisions

The code is written so that each of these is an argument, a constant or a choice of the dispatch. None of them is closed by this directory.

| # | Decision | How the writer is affected |
| --- | --- | --- |
| D1 | Reader launcher accepted, or worker run directly | Not at all. The writer needs the reader's mounts and environment, whichever process the reader unit starts. |
| D3 | Compose `r2d2-worker` run with capacity required | Not at all. The writer never talks to the compose worker; it reads and writes the same epoch row through the database. |
| D4 | Veto view delivered the evening before, or emitted inside its 10-second window | Both work with the same bytes: `--view-opens-at` parks the process without reading the view file, and a view that is still absent or incomplete when the window opens is retried for `VIEW_GRACE_SECONDS` (5 seconds). |
| D5 | One dispatch = admission and manifest in one process | `--prepare-first`. Without it the writer only publishes from a binding that is already committed. |
| D6 | Number and times of the windows per session | The writer has no window list and **keeps no record of attempts**. Each dispatch names its own view (`--view-opens-at`) and its own capacity config (environment). The only clock constant is the cutoff, open minus 10 minutes. The cap of a primary window plus two contingencies is enforced by the host payload alone (see "Attempts"). |
| D9 | Manifest hash and symbol count kept in a private host receipt | The writer prints them on its one line. Splitting that line into a private and a public receipt is the host payload's job (see "What the host payload does with the line"). |
| D11 | Which document hashes fill the contract bindings and the quote windows | Not at all. The writer accepts whatever contract the packaged validation accepts. |
| D12 | A day with an empty monitored list | The admission is still committed; the manifest is refused with `MANIFEST_SYMBOLS_EMPTY`, in every window and by `--verify-only`. Terminal for the day (see the outcome rule). |
| — | Whether the `bar_manifest` GO must be the delegated form (Act B, 15 minutes of notice) | `--require-go-mode`. Without it the packaged rule applies, which also accepts an individual GO from a listed issuer for this phase. The argument is not in any authored dispatch yet. |

## Mechanism

One capacity-day dispatch per window. The host payload (Codex's side, not in this repository) authenticates its envelope and runs **one container of the pinned image**, which executes `manifest_writer.py`. In that one process:

1. **Pre-flight.** What needs neither the view nor the commit is checked first, before the wait: the clock, the directory (including whether it can be written), the payload contract, the GO files and every document behind them (list below). What can still fail once the binding is committed is listed under "After the commit".
2. **Parking.** The process sleeps until the instant given in `--view-opens-at`. It does not read the view file while it waits.
3. **First gate.** Inside the view, the day's `bar_manifest` GO is verified in full by the packaged documentary authority (Act A and Act B chains, the day's template, the GO and publication records, the pinned veto view), against the plan in the day's payload file.
4. **The temporary.** The private temporary of the publication is created, exclusively and empty. A directory that refuses a new file ends the run here, with nothing committed.
5. **Admission.** Only then `prepare-capacity-day` runs, through the same packaged function the worker's `--prepare-capacity-day` calls, on the same collector the worker builds. It verifies the `admission` GO itself and commits the binding.
6. **Contract equality.** The committed binding is read back and restored; its contract must equal the contract of the payload file.
7. **Publication.** The manifest is written to the temporary, fsynced, and the `bar_manifest` GO is verified again **immediately before `link()`**. Then the temporary name is removed and the file is read back with the supervisor's own reader.

The writer issues no GO, never retries and never replaces a manifest.

### Attempts

The exclusive target file is the durable single-use record of a **successful** publication. **Failed attempts are not recorded by the writer.** The packaged single-use executor (the attempt file that `ConsumerEntrypoints` reserves between two gates) is not used here, so the same `bar_manifest` GO can serve another dispatch after a refused or failed one, until the cutoff. Nothing in the script counts dispatches: the limit of a primary window plus two contingencies is enforced solely by the host payload and its envelope (D6).

### After the commit

Once `prepare` has committed the binding, these can still end the run without a manifest. Each is reported with `prepare_status` and, once the binding was read back, `binding_sha256`:

- the binding committed is not the one of the payload file (`MANIFEST_CONTRACT_DIVERGED`, `MANIFEST_BINDING_SHA_MISMATCH`, `MANIFEST_PREPARE_UNCONFIRMED`), or its read back or restoration fails;
- the list is empty (`MANIFEST_SYMBOLS_EMPTY`, D12) or fails the producer's grammar;
- the view or the GO window closed, or the cutoff passed, before the second gate;
- an operating-system error while writing up to 64 KiB into the temporary, at `fsync` or at `link()` (for example a filesystem that filled up after the pre-flight), or a failed readback.

A directory that is read-only, not writable by the process, or without a free block or inode is **not** in this list: it is refused before the wait, and the temporary is created before `prepare`.

### Manifest bytes

Canonical JSON — sorted keys, compact separators, ASCII, **no trailing newline** — of exactly

```
{"epoch": <release epoch>, "owner_uid": <effective uid, 0 in the container>, "session": "<day>", "symbols": [...]}
```

where `symbols` is `monitored_symbols` of the committed binding, verbatim. The bytes are produced by `DailyCapacityBinding.bar_manifest()` and the store's `canonical()`, and checked against the producer's own grammar before they are written. Their SHA-256 is the value the supervisor writes into claim 1.

The repository tests feed the published file to the real `private_bytes` of `app/r2d2_v2_massive_supervisor.py`, to the real `supervised_attempt` (claim 1 carries the same SHA-256) and to the real `run_session` of the producer, which accepts the manifest and prepares the session with the same list. The provider connection, the token and the free-space floor are replaced in that test.

### Publication

- private temporary `.<day>.json.<16 hex>.tmp`, created exclusively and empty **before `prepare`**, mode set to exactly 0600 whatever the umask; removed on every way out of the run, published or not;
- `fsync` of the file, then `link()` to `<day>.json`, then `unlink()` of the temporary name and `fsync` of the directory;
- `link()` never replaces an existing name: if the name already exists the run compares the bytes instead;
- readback through the supervisor's `private_bytes` (regular file, single link, owner equal to the effective uid, mode 0600, 1 to 65536 bytes), then the supervisor's parse and its two checks (`session`, `owner_uid`).

The writer never overwrites, truncates or deletes a manifest.

## How the script is run

The script is delivered on standard input to an isolated interpreter, or read from a read-only bind mount:

```
python -I -B - <arguments> < manifest_writer.py
python -I -B /<read-only mount>/manifest_writer.py <arguments>
```

`-I` leaves the environment's `PYTHON*` variables, the user site directory and the script's own directory out of the import path; `-B` writes no bytecode. The script therefore adds the application itself: the single constant `APPLICATION_ROOT = '/app'` near the top is the only path it puts on `sys.path`, and it refuses (`MANIFEST_APPLICATION_ROOT`) if the `app` package it imported does not come from that directory. The image installs its dependencies in the interpreter's own site-packages, which `-I` keeps *(read from `backend/Dockerfile`; not run in a container)*.

**The script hash.** SHA-256 of `manifest_writer.py` at this revision:

```
aeda5b12d34a406b0d61e1e4696e3c535e89fa3dc680ce0d3b14bb4d60b1d387
```

A repository test compares this line with the file. The hash that binds a run is the one in its authorisation, not the one printed here: this document is the reference the authorisation is expected to copy, and a difference between the two stops the run until it is explained. The host payload prints `sha256sum manifest_writer.py` and compares it before it starts the container. The script cannot hash itself when it is read from standard input, so its receipt does not carry that hash.

Because the script is outside the package, a defect found after the package is frozen is corrected by a new script hash under a new authorisation, with no new release.

## What the host payload must provide

The container is the reader's container with one more bind. Same image ID, same uid, same network.

**Mounts — exactly three:**

| Host | Container | Mode | Why |
| --- | --- | --- | --- |
| the data volume | `/app/day-d-data` | **read-only** | the release file and the journal catalog, both read by the collector that `--prepare-first` builds. The source directories that collector names are not read by this run |
| the capacity tree | `/c3po-capacity` | **read-only** | capacity config, the documents, payload and go roots. The root identities pinned in the config hash the device and inode of every path component, so the target must be this top-level path |
| `/etc/c3po-bar/manifests` | `/etc/c3po-bar/manifests` | **read-write** | the only writable path |

**Never mount `/etc/c3po-bar` itself.** That directory holds the provider token. With only `manifests` bound, the token is not visible in the container at all. The tests cannot prove what a host payload mounts; the payload's own readback must show the three mounts and nothing else.

Use `--mount type=bind`, never `-v` (a missing source must be an error, not a new root-owned directory), with `--read-only`, `--cap-drop ALL`, `--security-opt no-new-privileges`, `--user 0:0`, `--init`, `--rm`, `--pull never`, the image by ID. Nothing else needs to be writable: the script creates no temporary outside the manifest directory. Whether Docker creates the nested mount target `/etc/c3po-bar/manifests` under a read-only root filesystem was proven for the supervisor's layout on the CI runner only *(unverified on the host)*.

**Environment.** Read by the packaged settings (`app.config`), never by the script:

| Variable | Source | Needed by |
| --- | --- | --- |
| `C3PO_DATABASE_URL` | the reader's `secret.env` | every mode. **Secret.** Never an argument, never printed |
| `C3PO_BUILD_SHA`, `C3PO_R2D2_V2_SHADOW_RELEASE_FILE`, `C3PO_R2D2_V2_SHADOW_RELEASE_SHA`, `C3PO_R2D2_V2_CAPACITY_REQUIRED=true`, `C3PO_R2D2_V2_CAPACITY_VETO_MODE` | the reader's `pins.env` | every mode |
| `C3PO_R2D2_V2_SHADOW_SOURCE_DIR`, `C3PO_R2D2_MICROSTRUCTURE_RAW_DIR`, `C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR` | the reader's `pins.env` | `--prepare-first` (the collector) |
| `C3PO_R2D2_V2_SHADOW_ENABLED=true`, `C3PO_R2D2_V2_MASSIVE_BARS_ENABLED=true` | inline `--env` of the dispatch | every mode / `--prepare-first` |
| `C3PO_R2D2_V2_CAPACITY_CONFIG_FILE`, `C3PO_R2D2_V2_CAPACITY_CONFIG_SHA` | inline `--env` of the dispatch: **the window's own config** | every mode |

`pins.env` carries the reader's static capacity config; the dispatch overrides both capacity variables inline with the config of its window. That an inline `--env` wins over `--env-file` is Docker's documented behaviour *(unverified)*. The receipt proves which one was loaded: `capacity_config_sha256` on the line must equal the hash of the window's config, and `--preflight` prints it without committing anything.

With the master flag off the script refuses before it opens or connects to anything: one line, `MANIFEST_SHADOW_OFF`, exit 3.

**Network.** The compose network on which `db` resolves. The provider is never contacted.

**The container's standard output** is the receipt. Docker's log driver keeps a copy of it under its data directory until `--rm` removes the container; the payload must capture the line itself and must not route it to the journal (see D9).

## Arguments

| Argument | Meaning |
| --- | --- |
| `--day YYYY-MM-DD` | Session date, New York. Required. |
| `--manifest-directory PATH` | Absolute path of the manifest directory in the container. Required except with `--preflight`. Every component must be a real directory (no symbolic link). The leaf must carry no group or other permission bit (0700 as provisioned; the packaged check rejects those bits and nothing else), be owned by the effective uid and, except for `--verify-only`, be writable by the process (`MANIFEST_DIRECTORY_NOT_WRITABLE`). It must not be, contain, or lie inside any directory the configuration names (`MANIFEST_DIRECTORY_OVERLAP`): the capacity config's directory and its roots (the restore-revocation root too, when the config has one), the journal directory, the two source directories and the release file's directory. Containment is otherwise the pinned argument list and the read-only mounts. |
| `--prepare-first` | When the day's binding is not committed yet, commit it in this process (`prepare-capacity-day`). Builds the worker's collector, so it needs the reader's full environment and the journal catalog. Without it a missing binding is `MANIFEST_PREPARE_MISSING`. |
| `--view-opens-at INSTANT` | `observed_at` of the pinned veto view, ISO 8601 **with an offset**. The process parks until that instant and reads the view only then. It must equal the view's own `observed_at` (`MANIFEST_VIEW_ARGUMENT_MISMATCH`). Without it the view must be open when it is read. |
| `--max-wait-seconds N` | Longest parking, 0 to **900**. Default 0: no parking at all. A view that opens later than this is `MANIFEST_VETO_WINDOW_NOT_OPEN`, at once. |
| `--expect-binding-sha SHA` | The binding hash of an already accepted `prepare-capacity-day`. A different committed binding is refused. |
| `--require-go-mode MODE` | `DELEGATED_ACT_B` or `INDIVIDUAL`. A `bar_manifest` GO of another mode is refused before the wait (`MANIFEST_GO_MODE`). Optional; without it the packaged rule decides, and the host payload must compare `go_mode` on the line with its authorisation. Not checked by a run that publishes nothing (`ALREADY_PUBLISHED_VERIFIED`), which reads no GO. |
| `--verify-only` | Readback: compare the existing file with the committed binding. Never writes, never repairs, never waits, needs no GO and no view. Refuses `--prepare-first`, `--view-opens-at`, `--require-go-mode` and a non-zero wait. |
| `--preflight` | Context and static validation only (below). |

There is no late-recovery argument and no help argument: `-h` and `--help` are wrong arguments like any other. Abbreviated argument names are not accepted. A wrong argument is one JSON line with `MANIFEST_ARGUMENTS_INVALID` and exit 3, never argparse's own text.

## The three modes

### Publish (default)

Checks, in this order. **Every one of them precedes `prepare`**; the ones above the line also precede the wait, so a refusal is immediate and leaves the rest of the window to react.

1. arguments; the day is a session of the calendar;
2. the manifest directory is none of the configured directories, holds none and lies inside none (`MANIFEST_DIRECTORY_OVERLAP`);
3. the day equals the New York date of the clock (`MANIFEST_DAY_NOT_TODAY`);
4. the clock, and the declared view instant, are before the cutoff (`MANIFEST_CUTOFF_PASSED`). **From the cutoff on, a publishing run does nothing at all**: no repair, no publication;
5. the epoch row is read; a session copy of the binding that differs from the prepared one is `MANIFEST_BINDING_DIVERGED`;
6. the manifest directory opens, is private, is owned by the effective uid and **can be written** (`MANIFEST_DIRECTORY_NOT_WRITABLE`): `access()` for write and search on the open directory, the filesystem not mounted read-only, a free block and a free inode. This is asked, not tried: nothing is created at this point;
7. leftover temporaries are looked at, read only; the existing file, if any, is read with the supervisor's reader;
8. if the binding is committed: it is restored and the manifest bytes are rebuilt from it. An interrupted publication of **exactly those bytes** is completed (see "Repair"). If the file exists, the bytes are compared and the run ends, `ALREADY_PUBLISHED_VERIFIED` or `MANIFEST_CONFLICT`. No GO file is read, the view is not read and the process does not park;
9. if the binding is not committed: `--prepare-first` is required; an existing file is foreign (`MANIFEST_EXISTING_WITHOUT_BINDING`); the day's payload file is read and its contract validated by the packaged `validate_contract`;
10. the GO files (`admission` only when the binding is not committed, `bar_manifest` always) are present, hold exactly the 13 fields, and are well formed for the day's plan: day, phase, plan hash, order and template hashes, phase window, notice. This is the packaged `validate_go` run with the clock at the GO's own `not_before` and **without authority**; its result is discarded and decides nothing. With `--require-go-mode`, the mode of the `bar_manifest` GO;
11. the Act A and Act B chains verify for the day; the capacity config pins a veto view for the day;
12. the documents behind each GO: first the pinned records load and bind it (`TEMPLATE`, `GO:<phase>`, and `PUBLICATION:<phase>` for a delegated GO; precise codes), then **the packaged `verify_go` itself** runs on a copy of the authority whose veto view is a stand-in open at the GO's own `not_before` (`MANIFEST_GO_DOCUMENTS`). That covers everything the gate will ask of the documents — order hash, template membership and scope, the GO record's scope, role and binding, the Act B and publication hashes in the GO, the publication record, the notice — and leaves out only the real view. Its result is discarded and decides nothing: the gates below ask the real authority with the real view;
13. the GO windows contain the declared view instant (`MANIFEST_GO_WINDOW_VIEW`);

    ---

14. parking until `--view-opens-at`;
15. the pinned view is read: its `observed_at` equals the argument, the clock is inside it, and both GO windows contain it;
16. **first gate**: the `bar_manifest` GO in full (packaged `validate_go` with the real authority and the veto view), inside the GO window and before the cutoff;
17. the private temporary is created, exclusively and empty. An error here is exit 1, `MANIFEST_FILE_UNAVAILABLE`, with no `prepare_status`: nothing was committed.

Then `prepare`, the contract equality, the write, the second gate and `link()`, as under "Mechanism".

When the binding was already committed (a contingency window after a run that committed but did not publish), step 9 and the admission GO are skipped and the plan comes from the committed binding.

### `--verify-only`

Restores the committed binding, rebuilds the manifest bytes and compares them with the file. `MATCH_VERIFIED` (exit 0), `ABSENT` with `MANIFEST_ABSENT` (exit 3), or `MANIFEST_CONFLICT`. It only works on the session date itself (the packaged binding refuses another New York date). A leftover of an interrupted publication is reported as `MANIFEST_PUBLICATION_INTERRUPTED` and left exactly as it is.

### `--preflight`

Builds the same context a dispatch builds and validates everything that needs neither the clock nor the view. Give it the dispatch's own arguments plus `--preflight`; **use `--prepare-first`** so that the collector — release bytes, capacity config, sources, journal catalog — is built exactly as the dispatch will build it.

- **Does:** settings; `Release.verify` on the installed bytes; the capacity config and its pinned roots; the journal catalog (with `--prepare-first`); one read of the epoch row; the Act A and Act B chains for the day; the payload contract; the GO files, their records and the documentary verification without the view (steps 9 to 13 above, statically). With `--manifest-directory` it also checks that directory **without writing**: not a configured directory, private, owned, and writable (step 6). A directory that cannot be written is `MANIFEST_DIRECTORY_NOT_WRITABLE`, not `PREFLIGHT_OK`.
- **Never:** waits, calls `prepare`, writes, repairs, or reads the veto view. `--view-opens-at` is only compared with the GO windows and the cutoff; `--max-wait-seconds` is accepted and ignored.
- **Clock:** "the day is today" and "before the cutoff" are reported as booleans, not enforced, so it can run hours before the first window.
- **Prints:** one line, `PREFLIGHT_OK`, with the pins it loaded (`release_sha256`, `capacity_config_sha256`, `package_sha256`, `build_sha`, `capacity_veto_mode`, `massive_bars_enabled`), a `checks` object of booleans and counts, the two GO windows and the cutoff. No binding hash, no manifest hash, no count.

`--manifest-directory` is optional here so that the run can use the reader unit's layout, which does not mount that directory. Such a run says `directory_checked` false and proves nothing about the writable bind. **Before the primary window of the first session, one `--preflight` has to run in the dispatch's own layout** — the three mounts, with `--manifest-directory` — because nothing else exercises that bind before the dispatch itself. Without it the first check of the directory is step 6 of the primary dispatch: still before the wait and before any commit, but inside the window. Scheduling that run is the host payload's side and is not in this repository.

## Windows per session

New York time; BRT in parentheses for the week of 2026-10-05 (BRT = New York + 1 hour).

| Window | Start allowed | Veto view | Used when |
| --- | --- | --- | --- |
| Primary | 06:15–06:30 (07:15–07:30) | 06:30:00–06:30:10 (07:30:00) | always |
| Contingency 1 | 07:15–07:30 (08:15–08:30) | 07:30:00–07:30:10 (08:30:00) | primary not verified |
| Contingency 2 | 08:15–08:30 (09:15–09:30) | 08:30:00–08:30:10 (09:30:00) | contingency 1 not verified |
| Cutoff | 09:20 (10:20) | — | from here the writer refuses |

These are the plan's default (D6); the code holds none of them except the cutoff. Each window has its own capacity config, because a config pins one view per day. The start window of 15 minutes is the reason for the 900-second cap. Phase windows of `admission` and `bar_manifest` are authored as 06:15–09:20 New York; a delegated `bar_manifest` GO must be published at least 15 minutes before its window opens.

A later window after a success is harmless: `prepare` is idempotent, publication is exclusive, and the run ends as `ALREADY_PUBLISHED_VERIFIED` without parking. There is no path after the cutoff.

## Receipt

Exactly one JSON line on standard output (sorted keys, compact). Nothing is written to standard error: when the script is the main program it disables log records and warnings, which could carry a connection string or a file name. Counts, hashes, clocks, booleans and constant codes only: **no symbol, no account value, no secret, no path**.

### Status and exit

| `status` | Exit | Meaning |
| --- | --- | --- |
| `PUBLISHED_VERIFIED` | 0 | this run created the file and read it back |
| `ALREADY_PUBLISHED_VERIFIED` | 0 | the file was already there with the same bytes (also when another writer won the name during this run) |
| `MATCH_VERIFIED` | 0 | `--verify-only`: the file equals the committed binding's manifest |
| `PREFLIGHT_OK` | 0 | `--preflight` |
| `ABSENT` | 3 | `--verify-only`: no file. `code` is `MANIFEST_ABSENT` |
| `REFUSED` | 3 | a constant refusal code; nothing was published by this run |
| `UNVERIFIED` | 1 | an input/output, database, import or unclassified error; `code` says which family |
| `PUBLISHED_UNVERIFIED` | 1 or 3 | `link()` succeeded and something after it failed. The name exists. Never treated as success |

`code` is `null` on the four successes. Every other line carries a code, and every code holds an underscore, which the symbol grammar cannot.

### Fields

Fields appear only once the run has earned them.

| Field | Present |
| --- | --- |
| `schema`, `status`, `code`, `session`, `mode` | always (`session` is `null` when the day is not a date; `mode` is `PUBLISH`, `VERIFY_ONLY` or `PREFLIGHT`) |
| `epoch`, `owner_uid`, `release_sha256`, `capacity_config_sha256`, `package_sha256`, `build_sha`, `capacity_veto_mode`, `massive_bars_enabled` | once the context is built |
| `cutoff_at` | once the day is known to be a session |
| `stale_temporaries`, `repaired_temporaries` | once the directory passed its own checks (private, owner, writable) |
| `prepare_status` | `PRECOMMITTED` when the binding was already there; `ATTEMPTED` from the moment `prepare` is called; `COMMITTED` or `ALREADY_COMMITTED` once it returned one of the two |
| `waited_seconds` | after the parking (0.0 when the process did not park) |
| `view` (`observed_at`, `valid_until`) | once the pinned view was read |
| `go_sha256`, `go_mode`, `template_sha256`, `window` | after the first gate |
| `binding_sha256`, `symbol_count`, `manifest_sha256` | **only after the first successful gate**; in a run that publishes nothing, only after the file was found equal to the committed binding's manifest |
| `published_at` | after `link()` |
| `file` (uid, gid, mode, link count, device, inode, "size within the limit") | after the readback |
| `checks`, `windows` | `--preflight` only |

A refusal before the first gate therefore carries no binding hash, no count and no manifest hash.

**Reading `prepare_status` on a line that is not a success:**

- absent: `prepare` was not called. Nothing was committed by this run.
- `ATTEMPTED`: `prepare` was called and did not return a commit status — it raised (a packaged refusal, or a database error that may have come **after** its commit), or returned something unexpected. **The binding may or may not be committed.** No `binding_sha256` is printed. The next window, or `--verify-only`, shows which: `PRECOMMITTED` or `MANIFEST_PREPARE_MISSING`.
- `COMMITTED` or `ALREADY_COMMITTED`: the binding is committed. `binding_sha256` follows once the row was read back and the binding restored; it is absent when that read back failed or did not find the reported binding (`MANIFEST_PREPARE_UNCONFIRMED`).
- `PRECOMMITTED`: the binding was committed before this run.

### Codes

The script's own codes:

| Code | Meaning |
| --- | --- |
| `MANIFEST_ARGUMENTS_INVALID` | wrong or contradictory arguments, a wait above 900, an instant without offset |
| `MANIFEST_DAY_INVALID`, `MANIFEST_DAY_NOT_SESSION`, `MANIFEST_DAY_NOT_TODAY` | the day |
| `MANIFEST_CUTOFF_PASSED` | the clock or the declared view is at or after open minus 10 minutes |
| `MANIFEST_SHADOW_OFF`, `MANIFEST_CAPACITY_REQUIRED`, `PERSISTENT_DATABASE_REQUIRED`, `CAPACITY_CONFIG_REQUIRED` | the environment does not enable the run |
| `MANIFEST_APPLICATION_ROOT`, `MANIFEST_APPLICATION_UNAVAILABLE` | the application is not at `APPLICATION_ROOT`, or cannot be imported |
| `MANIFEST_DIRECTORY_INVALID`, `MANIFEST_DIRECTORY_OWNER` | the manifest directory |
| `MANIFEST_DIRECTORY_OVERLAP` | the manifest directory is, contains, or lies inside a directory the configuration names |
| `MANIFEST_DIRECTORY_NOT_WRITABLE` | the process may not create a file there, the filesystem is mounted read-only, or it has no free block or inode. Refused before the wait; nothing was committed |
| `MANIFEST_EXISTING_UNVERIFIED` | a file at the name that the supervisor's reader refuses (mode, owner, links, size, symbolic link) |
| `MANIFEST_EXISTING_WITHOUT_BINDING` | a file at the name while no binding is committed |
| `MANIFEST_CONFLICT` | a file at the name with other bytes. Never replaced, and never repaired when it has two names |
| `MANIFEST_PUBLICATION_INTERRUPTED` | a second name of the published file is still there: reported by `--verify-only`, and by a publish run when the file is not exactly the shape an interrupted publication leaves (two links, one of them a temporary, mode 0600, own uid) |
| `MANIFEST_PREPARE_MISSING` | no committed binding and no `--prepare-first` |
| `MANIFEST_PREPARE_FAILED`, `MANIFEST_PREPARE_UNCONFIRMED` | `prepare` returned something unexpected, or the row read back does not hold the binding it reported |
| `MANIFEST_BINDING_DIVERGED`, `MANIFEST_BINDING_SHA_MISMATCH`, `MANIFEST_CONTRACT_DIVERGED` | the committed binding is not the expected one; the last one is the contract equality after the commit |
| `MANIFEST_PAYLOAD_MISSING`, `MANIFEST_PAYLOAD_INVALID`, `CAPACITY_INPUT_FIELDS` | the day's payload file |
| `MANIFEST_GO_MISSING`, `MANIFEST_GO_FIELDS`, `MANIFEST_GO_INVALID`, `MANIFEST_PLAN_DAY_PHASE` | a GO file, or the plan it is checked against |
| `MANIFEST_GO_MODE` | `--require-go-mode`: the `bar_manifest` GO has another mode |
| `MANIFEST_GO_RECORD`, `MANIFEST_GO_RECORD_MISSING` | the pinned documentary records behind a GO |
| `MANIFEST_GO_DOCUMENTS` | the packaged `verify_go` refuses the documents behind a GO even with the veto view left out. The packaged function gives no reason; the defect is in the GO's receipts, the GO or publication record, or the template record |
| `MANIFEST_CHAIN_UNVERIFIED` | the Act A or Act B chain failed without a code of its own |
| `MANIFEST_GO_WINDOW_VIEW` | a GO window does not contain the view |
| `CAPACITY_VETO_DAY_UNBOUND` | the capacity config pins no view for the day |
| `MANIFEST_VETO_WINDOW_NOT_OPEN`, `MANIFEST_VETO_WINDOW_MISSED`, `MANIFEST_VETO_VIEW_ABSENT`, `MANIFEST_VIEW_ARGUMENT_MISMATCH`, `MANIFEST_WAIT_CLOCK` | the view and the wait; the last one is a clock that did not advance during the parking |
| `VETO_HASH_MISMATCH`, `ROOT_FILE_POLICY`, `ROOT_FILE_CHANGED` | the view file is still not the pinned bytes when the grace ends |
| `GO_WINDOW_AFTER_AUTHORITY` | the GO window closed while the authority was being checked |
| `MANIFEST_FIELDS`, `MANIFEST_OWNER`, `MANIFEST_EPOCH`, `MANIFEST_SESSION`, `MANIFEST_SYMBOLS`, `MANIFEST_SYMBOLS_EMPTY`, `MANIFEST_ENCODING` | the manifest fails the producer's grammar before it is written |
| `MANIFEST_WRITE_FAILED`, `MANIFEST_READBACK_FAILED` | the temporary or the readback |
| `MANIFEST_FILE_UNAVAILABLE`, `MANIFEST_DATABASE_UNAVAILABLE`, `MANIFEST_UNVERIFIED` | exit 1: an operating-system error, a database driver error, anything else |

Codes of the packaged modules pass through unchanged when they are a single constant with an underscore: `GO_*` and `PHASE_WINDOW_*` (the assembler), `AUTHORITY_UNVERIFIED_OR_VETOED`, `CAPACITY_*` (config, contract, binding), `DOCUMENT_*`, `ROOT_*`, `RELEASE_*`, `SOURCE_DIRECTORY_NOT_PRIVATE`, `MASSIVE_SESSION_ROOT_UNVERIFIED` and others. Any other error text — a message, a path, a key, a connection string — is never copied: it becomes one of the three exit-1 codes.

## Repair of an interrupted publication

A process killed between `link()` and `unlink()` leaves the published file with **two names**: `<day>.json` and its temporary. The content is complete and fsynced, but the supervisor's reader refuses a file with two links (`SUPERVISOR_PRIVATE_FILE`), so the 09:29 start would end in 78.

- A **publish run** removes the temporary name only after all of this holds: the day's binding is committed and **restores**; the manifest bytes were rebuilt from it; the file under `<day>.json` is a regular file of the effective uid, mode 0600, with **exactly two links**, the other one being that temporary; and **its bytes are those manifest bytes**. Then the name is removed, the directory fsynced, and the run ends `ALREADY_PUBLISHED_VERIFIED`, with `repaired_temporaries` 1.
- **This is the one write that needs no `bar_manifest` GO.** It reads no GO and no view. It changes no content, but it does change what the supervisor accepts — a two-link file is refused, a one-link file is read — which is why it is done only for a file that already is the committed binding's manifest.
- Any other two-link file is **left exactly as it is**: other bytes are `MANIFEST_CONFLICT`; another mode, a third link or two temporary names are `MANIFEST_PUBLICATION_INTERRUPTED`; a binding that does not restore is refused with its own code. In all of them `repaired_temporaries` is 0 and the supervisor still refuses the file.
- `--verify-only` and `--preflight` **never repair**. They report it (`MANIFEST_PUBLICATION_INTERRUPTED`, or `publication_interrupted` true) and leave both names.
- After the cutoff nothing repairs it.
- A temporary that is **not** a second name of the published file (a run killed before `link()`, or a foreign file of that name shape) is counted in `stale_temporaries` and left alone. It may be empty or hold the list, inside a root-only directory; removing it is a separate authorised action. The supervisor does not look at it.
- With no committed binding nothing is repaired and the run refuses (`MANIFEST_EXISTING_WITHOUT_BINDING`).

A publish run that finds the file already there (`ALREADY_PUBLISHED_VERIFIED`, with or without a repair) also fsyncs the directory before it reports: the run that created the name may have died before its own directory fsync. That changes nothing in the directory. `--verify-only` does not do it.

## What the host payload does with the line

- **Outcome rule.** Any outcome other than `PUBLISHED_VERIFIED` or `ALREADY_PUBLISHED_VERIFIED` — including **no line at all**, a container that was stopped while parked, and a file left with two links — is "not verified" and triggers the next pre-authorised window. There is no fourth publication attempt and no path after the cutoff. Two exceptions:
  - **Empty list (D12).** `MANIFEST_SYMBOLS_EMPTY` with `prepare_status` `COMMITTED`, `ALREADY_COMMITTED` or `PRECOMMITTED` is **terminal for the day**: the admission is committed, there is nothing to publish, and a contingency window would answer the same before parking. No contingency is dispatched. `--verify-only` answers `REFUSED` / `MANIFEST_SYMBOLS_EMPTY` on such a day, not `ABSENT`, and the supervisor ends in 78 at 09:29 for want of a manifest, by design.
  - **Repair after the last window.** If the last pre-authorised window died between `link()` and `unlink()`, the file is complete and correct but has two names, and the supervisor would refuse it terminally. A publish invocation before the cutoff completes it without reading a GO or a view and without parking; it ends `ALREADY_PUBLISHED_VERIFIED` with `repaired_temporaries` 1, or refuses and changes nothing. **That invocation is not a fourth attempt**: it cannot create or change a manifest. The host payload has to pre-authorise it for the case "host readback shows two links after the last window"; whether it does is the payload's side and is not in this repository.
- **Attempts are counted by the payload.** The writer records nothing about a failed or refused dispatch (see "Attempts"), so the cap of three windows exists only in the payload and its envelope.
- **GO mode.** `go_mode` on the line is the mode of the `bar_manifest` GO that was verified. If the authorisation requires the delegated form, either the dispatch passes `--require-go-mode DELEGATED_ACT_B` (refused before the wait) or the payload compares `go_mode` with its authorisation and treats a difference as a failure of the run.
- **`prepare_status` `ATTEMPTED`** on a line that is not a success means the binding may be committed (see "Receipt").
- **Private and public.** `manifest_sha256` and `symbol_count` together are an unsalted commitment to a list from a public universe. They go into the private host receipt (root, 0600, exclusive); the public receipt carries the status, `binding_sha256`, `prepare_status` and booleans.
- **Host readback.** The payload reads `/etc/c3po-bar/manifests/<day>.json` from the host (owner, mode, one link, SHA-256) and compares the hash with the line. `file.device` and `file.inode` are the container's view; they are expected to equal the host's for a bind mount *(unverified)*.
- **`owner_uid` must be 0** on the line. The script writes the effective uid of its process; a container started with another user would publish a manifest the supervisor refuses.
- **The owner's veto** during the notice is exercised by withdrawing the dispatch: the payload stops the parked container. Nothing has been committed or written at that point. A stop delivered through `docker-init` to a process with the default signal disposition is expected to end it without a line *(unverified)*.

## Not verified

Nothing in this list was observed; each item is a host or engine fact, or a measurement nobody has taken.

- The script in a container at all: `python -I -B -` in the image, imports under `--read-only --cap-drop ALL`, the application found at `/app`, exit status through `docker-init` and `--rm`.
- The three mounts on the host; the nested mount target under a read-only root filesystem; that the token directory is invisible with only `manifests` bound; that device and inode of a bind mount equal the host's.
- The capacity tree at `/c3po-capacity` giving the root identities pinned in the config (it depends on device and inode numbers that only the host has).
- Inline `--env` overriding `--env-file`.
- The database: a real PostgreSQL round trip, `prepare-capacity-day` against the real epoch row, behaviour when the connection fails between the commit and the read back. The tests use the package's in-memory store.
- `Release.verify` on the real release bytes and the collector build on the real data volume, read-only.
- **Timing inside the 10-second view.** Gate, `prepare` (one transaction), read back, restore, write, fsync, gate, `link()` were not timed anywhere. Each gate re-reads the pinned documents and the config. If the view expires after the commit the result is a binding without a manifest until the next window; with in-window emission (D4) up to 5 of the 10 seconds can be spent waiting for the view file.
- Container start plus import time, which sizes the lead of the dispatch.
- A view file emitted in-window by Codex's emitter: how it is written. The writer tolerates an absent, incomplete or two-link file for 5 seconds; an emitter that publishes by rename never shows those states.
- `fsync` and `link()` semantics on the host filesystem of `/etc/c3po-bar/manifests`.
- The writability check on the host: that `access()` and `fstatvfs()` on the open directory report a read-only bind mount in the image (Alpine, musl) for uid 0 under `--cap-drop ALL`, and what they report for the filesystem behind `/etc/c3po-bar/manifests`. Offline, a directory of mode 0500 and replaced `fstatvfs` answers stand in for it. A read-only bind that both calls miss is still stopped before `prepare`, by the creation of the temporary.
- A `--preflight` in the dispatch layout with `--manifest-directory`: not scheduled anywhere in this repository.
- A stop while parked, a kill inside the view, and what `--rm` leaves behind.
- The host payload itself, its envelope, its transport limit against a 15-minute parked container, and its receipts: not in this repository.

## Offline verification

`c3po/backend/tests/test_r2d2_v2_manifest_writer_script.py` loads the script by path and points `APPLICATION_ROOT` at the checkout. It runs the real assembler, documentary authority, capacity contract and binding, capacity config on anchored private directories, release verification, supervisor and producer code, on temporary directories, with synthetic documents and synthetic symbols.

What is replaced, and where:

- **Everywhere:** the documents (release, Act A and Act B chains, templates, GOs, views are synthetic, in the real formats), the symbols, and the clock (a test clock that the test's `sleep` advances).
- **Most cases:** the authority is the real `DocumentAuthority` over an in-memory document root with an in-memory veto view, and `prepare` is a stand-in that stores a binding derived by the real `derive_document`.
- **Wiring cases:** the real `CapacityConfig`, `ConfigAuthority` and pinned veto view file on disk; release verification and the database are stubbed.
- **The collector case:** the real `app.config.Settings`, release file and `Release.verify`, `build_collector`, journal catalog, `CapacityBoundCollector`, `CapacityLoader.derive` and `prepare_capacity_day`, driven through `main()`. Replaced: PostgreSQL (the store is the package's `MemoryShadowStore`; the stub database is asserted never to be asked for a connection) and the wall clock inside `CapacityConfig`.
- **The supervisor case:** the real `private_bytes`, `supervised_attempt` and `run_session`. Replaced: the provider connection (raises at the boundary), the token (a synthetic file) and the 50 GiB free-space floor (set to 0).
- **Two subprocess cases** run the script under `python -I -B`, on standard input with only the root constant edited, and by path unedited. They reach the "off" refusal and the "no application" refusal; they do not reach a context.

The tests cover: the bytes and the mode under three umasks; exclusive publication against an existing file, a concurrent writer, a symbolic link and a second link; every pre-flight refusal with `prepare` forbidden; a directory that cannot be written (mode 0500, a read-only or full filesystem as reported by a replaced `fstatvfs`, and a directory that refuses the creation itself) refused by `--preflight` and by three windows in a row with nothing committed, also through the real collector; the empty temporary present when `prepare` is called; a manifest directory equal to, inside or around each configured directory; the order gate → `prepare` → gate → `link()`; the contract equality; a view that expires after the commit and the next window that publishes; `prepare` that commits and then raises; parking, the 900-second cap, a clock that does not advance; a view file absent before the window, half written, then complete; the cutoff, including between the write and the link; the two-link leftover, its repair by a publish run only and only after the bytes were compared, its refusal by the supervisor's reader before the repair, and the two-link files that are never repaired (other bytes, a binding that does not restore, another mode, a third link); six documentary defects with consistent pins refused by `--preflight` and before the wait, five of them also on the real config wiring; that the two stand-ins (no authority, no view) are named in one function each and in no gate; `--require-go-mode`; an empty list in a second window and in the readback; `--verify-only`; `--preflight` writing and committing nothing; the receipt fields at each stage; argument errors, `-h` included, as one line; and, for eight end-to-end scenarios through `main()`, that no sentinel symbol and no part of the database URL appears on standard output, standard error, in a log record or in the receipt. They also pin that the script is outside the package list, that this document carries its hash and names each of its codes.
