# V2 shadow reader supervision — installation candidate

Offline candidate. Nothing here has been installed, enabled, started, connected to a database, or approved for live operation.

**Unverified on the host.** Every Docker and systemd behaviour described in this document comes from documentation and from offline tests. None of it has been observed on the production host or on any Docker engine: this directory has no pipeline step yet. Statements marked *(unverified)* are the ones a reviewer could not support from the repository at all. The shared rationale (image pin, retention tag, `--init`, the docker CLI configuration directory, the security reboot) is in `../massive-supervisor/README.md` and is not repeated here.

## Open decisions

The files of this directory are written so that each open decision is a file choice, a line of an environment file or a constant, not a code change.

| # | Decision | Default in this directory | Where the switch is |
| --- | --- | --- | --- |
| D1 | Launcher (parent process with the worker as a child) accepted, or the worker run directly | Launcher | `c3po-reader.service` as shipped, or the three unit texts under "Worker-direct fallback (D1)" |
| D3 | Whether the compose `r2d2-worker` runs with capacity required | Unknown; nothing here depends on it | The reader unit carries its own capacity mount and pins. If the answer is yes, the compose mount is a separate change outside this directory |
| D4 | Veto view delivered the evening before, or emitted inside its window | No effect on the launcher or the unit | It reaches the reader only through the hash of its static capacity configuration, a line of `pins.env` |
| D6 | Number of capacity windows per session | No effect | The reader needs the day's binding committed before the open, whichever window commits it (see "Daily contract") |
| D11 | Which document hashes fill the daily contract | No effect | Nothing in this directory reads a contract field |
| L1 | **New, raised by this directory.** Whether `pins.env` carries the launcher's own SHA-256 as a twelfth key | Proposed: yes | The key `C3PO_READER_LAUNCHER_SHA256`; absent or empty means not pinned by the process itself |
| L2 | **New, raised by this directory.** How the launcher bytes reach the container | Read-only bind of `@HOST_CONFIG_DIR@/launcher` | The mount line of the unit. Standard input is possible only without L1 (see "The launcher file") |

The launcher is a deployment script. It is **not** in the image and **not** in the pinned implementation package: adding it there would move the package hash, and with it the release, the consents and every capacity configuration. Its authority is the SHA-256 written in the authorisation that installs it.

## Contract

The reader is one container of the deployed backend image, pinned **by ID**, started in the foreground by `c3po-reader.service`, as **uid 0**, outside compose. It never shares a lifetime with `r2d2-worker` and is never started with `docker exec`.

Inside the container the unit runs the launcher of this directory, mounted read-only:

```
python -I -B /c3po-reader/reader_launcher.py
```

The launcher is a small parent process. It imports three things from the packaged code of the image (`ShadowCalendar`, `SESSIONS`, `get_settings`) and runs the **unmodified** worker as a child process:

```
python -B -m app.r2d2_v2_shadow_worker
```

Nothing is raised into the worker and no worker code runs in the parent. A phase ends by SIGTERM to the child. The worker installs no handler for it, so the kernel ends the process and releases every descriptor and lock it held; the parent waits for it, and sends SIGKILL after 20 seconds. The reader holds nothing a kill can corrupt: the journal index is opened read-only and every transition of the collector is one database transaction.

Nothing in the journal tree, the data volume or the capacity tree is written by this unit: all three mounts are read-only.

**The first cycle of the first start creates the epoch row.** `PostgresShadowStore.atomic` inserts the row of the release's epoch if it does not exist (`r2d2_v2_store.py`, `atomic`), and from then on any other release hash is refused for that epoch (`RELEASE_REQUIRES_NEW_EPOCH`). The activation of this unit is therefore the moment the release hash is bound, unless a `prepare-capacity-day` ran first.

## Daily contract

Times are New York, for a regular session. The launcher takes the open and the close from the packaged exchange calendar, so an early close moves the end; the timer lines are fixed clock times.

| Time | Event |
| --- | --- |
| 04:00:00 (days 2–5), or the activation instant (day 1) | Unit start. `STARTING`, phase `PRE_OPEN`: the worker drains what accumulated since the previous stop |
| 09:28:30 (open − 90 s) | `HANDOVER`: the child is stopped. Nothing polls the catalog |
| 09:29:00 | Producer timer (`c3po-massive.timer`): catalog, session of the day, ready marker |
| marker seen, at the latest 09:29:50 (open − 10 s) | `READY_OBSERVED` or `READY_NOT_OBSERVED`; one second later `STARTING`, phase `SESSION` |
| 09:29:20 | Second timer line. No effect when the unit is active; it is the start of a unit that was not |
| 09:30:00 | Open. The first cycle at or after it needs the day's capacity binding already committed |
| close + 20 min (16:20:00) | `STOPPED`, reason `END_OF_DAY`, exit 0, container removed |

- **Why the reader is not polling across 09:29.** The producer takes the exclusive catalog lock three times at each start, and a reader that polls while the session is being prepared can report an append in progress. From 09:28:30 until the marker the launcher has no child, so the first producer start of the day meets no reader. The marker is looked at with one `stat`, without the catalog lock.
- **If the marker is not seen by 09:29:50** the notice says `READY_NOT_OBSERVED` and the worker is started anyway. From there the behaviour is the worker's own, unchanged: a session without its marker is skipped while it verifiably holds no receipt (`_readiness`, `r2d2_v2_massive_sessions.py`); anything else found in it, and a catalog lock held by the producer, is reported as `RAW_APPEND_IN_PROGRESS` (`r2d2_v2_massive_session_source.py` line 37), and three consecutive deferred polls add the source gap `RAW_POLL_PERSISTENT_FAILURE` (`r2d2_v2_shadow.py` lines 505–506). The producer waits up to 30 seconds for each of its locks.
- **Not protected:** producer restarts during the session (attempts 2 to 5) happen across a polling reader. Only the producer's bounded lock wait covers them.
- **Capacity.** A cycle before the open does not create the session of the day (`r2d2_v2_shadow.py` lines 614–615), so it cannot write `capacity_admission_blocked` for it, with or without a committed binding. The first cycle at or after the open with no committed binding makes the collector attempt the admission itself (`CapacityLoader.derive`), and a failure there writes the flag, which is sticky for the day. Both statements are repository tests on the real collector; the failure in the test is a missing admission payload, and an admission GO whose window ended before the open is the same path by reading the code. `prepare-capacity-day` may therefore run beside the `PRE_OPEN` phase, and must have committed before 09:30:00.
- **One polling reader per journal root.** This unit is that reader. See "Activation" for how a second one is ruled out.

## The launcher file

`reader_launcher.py` is delivered verbatim to `@HOST_CONFIG_DIR@/launcher/reader_launcher.py` (directory `root:root` 0700, file `root:root` 0600), by exclusive creation, under an authorisation that carries its SHA-256. The unit mounts that directory, and only it, read-only at `/c3po-reader`.

- `python -I` is isolated mode: no `PYTHON*` variable is honoured, there is no user site directory, and neither the working directory nor the script directory is on the import path. The launcher adds the application root itself; it is the constant `APP_ROOT = '/app'` near the top of the file, which is where the image keeps the application. `-B` writes no bytecode.
- The launcher has no configuration file, takes no argument (any argument is refused, `READER_ARGUMENTS`) and has no option. Its configuration is the three environment files.
- Every `STARTING` notice carries `launcher_sha256`, the hash of the file as mounted, computed by the launcher. It is read after the interpreter has loaded the program, so it proves which bytes are in the mount, not which bytes are running; with a read-only mount of a root-owned file the two differ only if the file was replaced between the two reads.
- **Self-pin (L1).** If the environment holds `C3PO_READER_LAUNCHER_SHA256`, the launcher refuses, before anything else, unless that value equals the hash of its own file (`READER_LAUNCHER_PIN`, exit 78). Without the key the launcher runs unpinned and says so (`launcher_pinned` false). The pin is a line of `pins.env`, whose own hash is in the activation GO.
- **Standard input.** `python -I -B - < reader_launcher.py` runs the same program, but it cannot hash itself: `launcher_sha256` is null, and with L1 the start is refused. That form is for a one-off rehearsal without the pin; the unit does not use it and must not get `-i`.

### Phases and child exit

1. Refusals, before any setting is read: the New York date is not in the code's `SESSIONS`, or the exchange calendar does not open that day (`READER_SESSION`); the clock is outside open − 6 h … close + 20 min (`READER_WINDOW`). Then the settings are read: they do not load (`READER_SETTINGS_INVALID`), either flag is not true (`READER_DISABLED`), the journal directory is not absolute (`READER_JOURNAL_DIR`).
2. `PRE_OPEN`, only if the start is before open − 90 s.
3. Handover, marker wait, one second.
4. `SESSION` until close + 20 min.
5. SIGTERM or SIGINT to the parent only sets a flag. The loop reads it every quarter of a second, stops the child, prints `STOPPED` with reason `SIGNAL`, and exits 0.

The child's own end, when the parent did not stop it:

| Child | Meaning | Parent |
| --- | --- | --- |
| exit 0 | the worker printed `OFF`: collection is disabled in its environment | `REFUSED`, `READER_DISABLED`, exit 78 |
| any other exit, or a signal the parent did not send | failure | exactly one `FAILED` notice, exit 1 |

### Notices

Standard output carries one JSON object per line. Every notice has `status` and `at` (UTC). Every notice has `session` (the New York date) except the two that can precede it: the `REFUSED` with `READER_ARGUMENTS` and a `FAILED` of phase `LAUNCHER`.

| `status` | Fields | When |
| --- | --- | --- |
| `REFUSED` | `code`, `restart_allowed` false | terminal refusal, exit 78 |
| `STARTING` | `phase`, `until`, `build_sha`, `release_sha`, `capacity_required`, `capacity_config_sha`, `launcher_sha256`, `launcher_pinned` | before each child is started |
| `HANDOVER` | `child_signal`, `child_exit`, `killed`, the three line counts | the `PRE_OPEN` child was stopped |
| `READY_OBSERVED`, `READY_NOT_OBSERVED` | `waited_seconds` | end of the marker wait |
| `STATUS_WITHHELD` | `phase`, `code` `READER_STATUS_GRAMMAR` | the first status line of a child that did not pass the grammar |
| `STOPPED` | `reason` `END_OF_DAY` or `SIGNAL`, `phase`, and the child fields | exit 0 |
| `FAILED` | `phase`, `child_exit` or `child_signal`, `error`, optional `code` and `errno`, `restart_allowed` true, the three line counts | the child ended by itself with a failure; exit 1 |
| `FAILED`, phase `LAUNCHER` | `error`, optional `code` and `errno`, `restart_allowed` true | the launcher's own failure (an import, the calendar, starting the child); exit 1 |

The hashes of `STARTING` are printed only when they have the grammar of a hash (40 or 64 lowercase hexadecimal characters); anything else is printed as null. No path, no environment value and no exception text is ever printed.

### What leaves the child

Both streams of the child end in one pipe that the parent drains. The parent forwards a line to its own standard error only when it is a worker status line **and** passes a grammar; every other line is dropped and only counted.

- **Status line.** The exact shape the worker logs (`r2d2_v2_shadow_worker.py` lines 153 and 164, run as `__main__`): the prefix `INFO:__main__:V2 status ` followed by one JSON object whose `schema` is `R2D2_V2_COLLECTOR_STATUS_V2`.
- **Grammar.** Every string in that object, at any depth, must be a hash, a date or timestamp, a constant code with an underscore (the instrument symbol grammar has none), an epoch name, or one of `CERTIFIED`, `DIAGNOSTIC`, `ELIGIBLE`, `CONTROL`, `UNASSIGNED`; every key must be one of those or a lower-case identifier. A status line with any other string is **withheld**: not forwarded, counted, and announced once per child by `STATUS_WITHHELD`. Numbers are not judged; they are whatever the packaged `public_summary` puts there (counts, fractions, seconds).
- **Tracebacks never reach the journal.** From the last traceback of a child the `FAILED` notice takes the exception class name, the errno name when the text starts with `[Errno N]`, and the text itself only when the class is `ShadowIntegrityError` or `SourceUnavailable` and the text is a constant code with an underscore. A failure with no traceback has no `error` field.
- The counts `status_lines`, `status_withheld` and `dropped_lines` of each child are in the notice that ends it.

## Environment files

The container receives its environment only from three files in `@HOST_CONFIG_DIR@` (proposed `/etc/c3po-reader`, `root:root` 0700). Each is a regular file, `root:root`, mode exactly 0600, one link, created by exclusive creation. They are read by the docker CLI on the host (`--env-file`); none of them is mounted into the container. The unit has no `-e` and no `EnvironmentFile=`.

Docker's file grammar *(documented, not observed on the host's version)*: one `NAME=value` per line, the value taken verbatim to the end of the line (no quotes, no interpolation, no trailing space), lines starting with `#` ignored. **A line holding only a name copies that variable from the docker CLI's own environment**: no such line may be written. Which file wins when a name appears twice was not established *(unverified)*: the writers and the readbacks refuse a name that appears in more than one file.

The names below are the ones the code reads: every attribute the worker and the capacity bootstrap take from the settings object (`r2d2_v2_shadow_worker.py`, `r2d2_v2_capacity_bootstrap.py`) is a field of `app/config.py` with the prefix `C3PO_`. A repository test compares this list with those two modules and with the settings class.

**1. `secret.env`** — written by the provisioning. The only secret. Exactly one line:

```
C3PO_DATABASE_URL=<value>
```

The value is the `C3PO_DATABASE_URL` entry of the running compose service `r2d2-worker`, copied in memory. It is never printed, never an argument, never hashed into a receipt. Readback: uid, gid, mode, link count, "exactly one line" and "the name is `C3PO_DATABASE_URL`" (true or false), and "equal to the `r2d2-worker` entry" (true or false, compared in memory). Never the value, a digest of it, or its length.

**2. `pins.env`** — written when the release hash and the reader's static capacity configuration hash exist. Not secret; its SHA-256 goes into the receipt and into the activation GO. Exactly these names, in this order:

<!-- pins-env:begin -->
```
C3PO_BUILD_SHA=<40 hex: release code_revision, image revision label, .deploy-version>
C3PO_R2D2_V2_SHADOW_RELEASE_FILE=/app/day-d-data/<private directory>/<release file>
C3PO_R2D2_V2_SHADOW_RELEASE_SHA=<64 hex>
C3PO_R2D2_V2_SHADOW_SOURCE_DIR=/app/day-d-data/<source directory>
C3PO_R2D2_MICROSTRUCTURE_RAW_DIR=/app/day-d-data/provider=eodhd/microstructure/raw
C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR=/app/day-d-data/<journal leaf>
C3PO_R2D2_V2_CAPACITY_REQUIRED=true
C3PO_R2D2_V2_CAPACITY_VETO_MODE=DISPATCH_AND_DERIVATION_ONLY
C3PO_R2D2_V2_CAPACITY_CONFIG_FILE=/c3po-capacity/config/<static configuration file>
C3PO_R2D2_V2_CAPACITY_CONFIG_SHA=<64 hex>
C3PO_R2D2_V2_SHADOW_POLL_SECONDS=1.0
C3PO_READER_LAUNCHER_SHA256=<64 hex>
```
<!-- pins-env:end -->

- The last line is L1. Without it the file has the eleven names the settings read. The settings class ignores names it does not know, so the twelfth disturbs neither the launcher's settings nor the worker's.
- `C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR` is the producer unit's `@CONTAINER_JOURNAL_ROOT@`, read from the installed `c3po-massive.service`, not typed. The default of the settings is another path; without this line the worker refuses with `MASSIVE_SESSION_ROOT_UNVERIFIED`.
- The capacity configuration is one static file for the five sessions. Its directory must itself be a private root (`root:root` 0700): the bootstrap anchors the file's parent directory.
- Value grammar enforced by the writer: paths `^/[A-Za-z0-9._=/-]+$` with no empty, `.` or `..` component; hashes in lower-case hexadecimal of the stated length.
- Must not contain `C3PO_DATABASE_URL`, either flag, a token, or any other name. The live-policy pair is not read by this process.

**3. `activation.env`** — created only by the activation operation. Constant bytes, two lines, each ended by one newline:

<!-- activation-env:begin -->
```
C3PO_R2D2_V2_SHADOW_ENABLED=true
C3PO_R2D2_V2_MASSIVE_BARS_ENABLED=true
```
<!-- activation-env:end -->

SHA-256 `2053f3f6f528ad7dc56d500666ac2cf48f79c3aadd3c98eb35b53ee92eff611b` (a repository test recomputes it from the two lines above). Until this file exists the unit is skipped by its `ExecCondition` lines and no container is created.

## Units

| File | Installed as | Placeholders |
| --- | --- | --- |
| `c3po-reader.service` | `/etc/systemd/system/c3po-reader.service`, rendered | five |
| `c3po-reader.timer` | `/etc/systemd/system/c3po-reader.timer`, verbatim | none |
| `c3po-reader-alert.service` | `/etc/systemd/system/c3po-reader-alert.service`, verbatim | none |

| Placeholder | Occurrences | Meaning | Example |
| --- | --- | --- | --- |
| `@IMAGE_ID@` | 2 | Image ID of the deployed backend image, read on the host after the deploy of the merged revision. Never a tag. The same ID as the producer unit | `sha256:0123…cdef` |
| `@HOST_DATA_ROOT@` | 2 | Mount source of the data volume, the one compose mounts at `/app/day-d-data` | `/mnt/day-d-data` |
| `@HOST_CAPACITY_ROOT@` | 2 | Host directory of the capacity tree, mounted at `/c3po-capacity` | host fact, not chosen yet |
| `@HOST_CONFIG_DIR@` | 9 | Host configuration directory of the reader: `RequiresMountsFor`, `DOCKER_CONFIG`, the three `ExecCondition` lines, the three environment files, the launcher mount | `/etc/c3po-reader` |
| `@NETWORK@` | 1 | The existing compose network on which `db` resolves, read on the host | host fact |

### Substitution grammar

The service template contains no `%`, `$`, quote or `;`, so a plain textual substitution is safe only if the values are equally plain. The installer refuses, before rendering:

- for the three host paths: any value that does not match `^/[A-Za-z0-9._/-]+$`, and any value with an empty, `.` or `..` component or a trailing slash;
- for `@IMAGE_ID@`: any value that does not match `^sha256:[0-9a-f]{64}$`;
- for `@NETWORK@`: any value that is not the name, read on the host, of the existing compose network that reaches `db` (a name matching `^[A-Za-z0-9][A-Za-z0-9_.-]*$`). `host`, `none`, `bridge` and `container:*` are **forbidden in production**. (`none` is for a pipeline smoke only.)

It also refuses when the configuration directory is inside the data volume or inside the capacity tree. After substitution the render **must fail if any `@` survives**.

### Why each option is there

The option set is the producer unit's, with these differences:

- **Three `--env-file` options** and nothing else for the environment. The producer passes none; the reader needs a database URL and its pins.
- **Three read-only binds**, never `-v`. `--mount` refuses a missing source instead of creating it.
  - The data volume at `/app/day-d-data`: the same container path, and the same inode, as the producer's journal root. The reader takes a shared `flock` on `maintenance.lock`, which it opens read-only, and opens the journal index with SQLite `mode=ro`. Whether both work on a read-only bind was not exercised *(unverified)*.
  - The capacity tree at the **top-level** target `/c3po-capacity`. `AnchoredRoot` hashes the device and inode of every path component below `/` (`r2d2_v2_capacity_anchored.py`). A root reached through `/app/...` would include directories of the container's own filesystem, whose identity is not the same in two containers *(inference from the code, not measured)*; a child of `/` that is itself the mount point has only host identities.
  - `@HOST_CONFIG_DIR@/launcher` at `/c3po-reader`. The configuration directory itself is **never** mounted: the environment files and the docker CLI directory stay invisible in the container.
- **`ExecCondition=/usr/bin/test -f`** for each environment file, before the two `ExecStartPre` lines. A condition that exits 1 makes systemd skip the start: the unit is not failed, nothing restarts, no container is created *(documented systemd behaviour, version 243 or later, not observed)*. Without them a missing file is expected to make `docker run` exit 125 *(not observed)*, and the unit would loop on restarts.
- **`RestartSec=5s`, `StartLimitBurst=40` in `StartLimitIntervalSec=8h`, `RestartPreventExitStatus=78`.** The collector treats bars more than 90 seconds late as stale for open positions; one restart has to stay well under a minute, and the container start is unmeasured.
- **`OnFailure=c3po-reader-alert.service`.** See "Failure marker".
- `--stop-timeout 25` and `docker stop -t 25`, below `TimeoutStopSec=30s` and above the 20 seconds the launcher gives its child.

Never add: a `--restart` policy other than `no`, `-d`, `-t`, `-i`, `-e`/`--env`, a fourth `--env-file`, `-v`/`--volume`, `--privileged`, `--cap-add`, `--cidfile`, `--pid`, `--ipc`, `--label`, `--network host`, a mount of the Docker socket, a mount of `@HOST_CONFIG_DIR@` itself, a writable mount, a tag reference such as `c3po/backend:production` or `:rollback`, a forced removal (`rm -f`, `--force`), `User=`/`Group=`, `EnvironmentFile=`, `SuccessExitStatus=`, `RuntimeMaxSec=`, `docker exec`, a compose service, or a second timer or loop for the reader. The repository tests pin the argument list and reject each of these.

### Timer

```
OnBootSec=90s
OnCalendar=Mon..Fri *-*-* 04:00:00 America/New_York
OnCalendar=Mon..Fri *-*-* 09:29:20 America/New_York
```

- 04:00:00 is inside the launcher's window on every session of the epoch (open − 6 h is 03:30:00) and leaves about five and a half hours for a backlog whose size is unmeasured.
- 09:29:20 is 20 seconds after the producer's timer and before the launcher's marker deadline. A unit that is active ignores it *(documented, not observed)*.
- `OnBootSec=90s` recovers a host that was down at a calendar trigger. `Persistent=false`: missed calendar triggers are not replayed.
- The timer fires on every weekday. On a day outside `SESSIONS`, and at a boot outside the window, the launcher refuses with 78; see what that does under "Failure marker".

### Failure marker

`c3po-reader-alert.service` is started by systemd when `c3po-reader.service` enters the failed state. With `Restart=on-failure` that happens when the start limit is reached, and at every exit that does not restart: **every 78 is one** *(documented systemd behaviour, not observed)*. It writes one private file:

```
/var/lib/c3po-reader/failed.<UTC, YYYYMMDDTHHMMSSZ>
```

holding `Result`, `ExecMainCode`, `ExecMainStatus` and `NRestarts` of the reader unit as `systemctl show` prints them. The file is created under `umask 077` with the shell's no-clobber option, so an existing file of the same second is never overwritten (that second run fails and writes nothing). A marker with `ExecMainStatus=78` is a refusal, not a crash; `Result=start-limit-hit` is the unit giving up.

The unit holds one `/bin/sh -c` line. It has no `$` and no double quote; `%%` is systemd's escape for the percent signs of the date format. A repository test runs that shell text with the paths replaced. systemd's own parsing of the line was not observed *(unverified)*. **Nothing forwards the marker.** Where it goes is a host fact; without a destination the daily checkpoints are the only detection.

## Process and restart contract

Exit statuses seen by systemd:

| Status | Origin | Effect |
| --- | --- | --- |
| 0 | launcher: `STOPPED` (`END_OF_DAY` or `SIGNAL`) | success, no restart |
| 1 | launcher: `FAILED` | restart after 5 s |
| 78 | launcher: `REFUSED` | no restart; unit failed; failure marker |
| `ExecCondition` 1 | an environment file is missing | start skipped: not failed, no restart, no marker |
| status of `ExecStartPre` | image check: pinned image absent, or daemon unreachable | start fails before `docker run`; restart; no notice |
| 125, 126, 127 | docker: missing mount source, unreadable environment file, name conflict, command not runnable | restart; no notice |
| 137 | container killed | restart |
| 143 | SIGTERM before the launcher installed its handler | failure; restart unless it was a `systemctl stop` |

- The launcher installs its two handlers as its first statement, before it imports the calendar. A stop that arrives earlier still meets the default disposition (143), as in the producer unit.
- **Every worker failure is exit 1**, whatever its cause. A permanent one (a changed release, a refused catalog, a capacity configuration that does not verify) restarts every five seconds plus the container start, spends the 40 starts in a few minutes, and then stays down with `start-limit-hit`. The `FAILED` notices carry the class and, for the two code-bearing classes, the constant code.
- A restart needs no new authority when every pinned byte is the same: it verifies everything again. A restart during the session goes straight to the marker look and the `SESSION` phase.
- `--rm` can surface a clean exit as 125 if waiting for the removal fails; that direction costs a restart, never a silent stop.

## Operations

Each write below is a separately authorised operation with its own receipt; the executor and the authority of each are in the epoch's plan, not here. None of them is performed by this repository, by the deploy pipeline or by a compose service.

### 1. Provisioning

- **Does:** creates, each by exclusive creation and `root:root`: `/etc/c3po-reader` 0700, `/etc/c3po-reader/docker-cli` 0700 (empty, stays empty), `/etc/c3po-reader/launcher` 0700 (empty at the end of this operation), `/etc/c3po-reader/secret.env` 0600, `/var/lib/c3po-reader` 0700 (empty). The capacity tree is provisioned by its own operation (`../capacity-day/README.md`).
- **Must not:** write `pins.env` or `activation.env`; install a unit or the launcher; start a container; print, pass as an argument or hash the database URL; touch `.env` or compose.
- **Reads back:** owner, group, mode and emptiness of each path; the shape booleans of `secret.env`.

### 2. Unit installation (no activation, no overwrite)

- **Does:** validates the five values against the grammar; renders `c3po-reader.service`; fails if any `@` survives; creates by exclusive creation, `root:root`: the three unit files 0644 and `/etc/c3po-reader/launcher/reader_launcher.py` 0600 with bytes whose SHA-256 is the one in the authorisation; runs `systemctl daemon-reload`.
- **Must not:** overwrite or edit an existing file; enable or start anything; create a drop-in.
- **Reads back:** path, size and SHA-256 of the four files, the rendered unit compared with an independent render; `systemctl is-enabled c3po-reader.timer` shows `disabled`; a `systemctl start c3po-reader.service` at this point is skipped by the conditions (optional, recorded; it proves that the activation file is the switch).

### 3. Pins

- **Does:** creates `/etc/c3po-reader/pins.env` by exclusive creation.
- **Guards:** every value passes the grammar; the journal leaf equals the leaf of the installed producer unit; the capacity configuration hash equals the SHA-256 of the delivered file; with L1, the launcher hash equals the SHA-256 of the installed launcher.
- **Reads back:** metadata and SHA-256 of the file. That hash goes into the activation GO.

### 4. Activation

The activation is the reader launch. It is the same payload for any date in `SESSIONS`: if it refuses or is late on the first session, it is valid on the next.

- **Window:** from open − 6 h of a session to its close. A launch after 09:28:30 New York is allowed and the receipt marks it `LATE`.
- **Guards, all before any write:** the New York date is in `SESSIONS`; the three unit files and the launcher have the hashes of the GO; `pins.env` has the hash of the GO; `secret.env` has its shape; the installed release bytes hash to the pin of `pins.env`; `epoch.json` in the journal directory is bound to the release epoch and to the directory's device and inode; the image ID resolves; no container named `c3po-reader` exists; and a `docker top` of every running container shows no process whose command line names `app.r2d2_v2_shadow_worker` or `reader_launcher.py`. The one exception to the last two is the reconcile case below. That scan finds a reader started by `docker exec`, which a scan of container commands does not. A process carrying `--prepare-capacity-day`, or a capacity-day script of `../capacity-day`, is not a reader.
- **Does, in this order:** writes and syncs a receipt `UNCERTAIN`; creates `/etc/c3po-reader/activation.env` exclusively with the two constant lines; `systemctl enable c3po-reader.timer`; `systemctl start c3po-reader.timer`; `systemctl start c3po-reader.service`; writes the receipt `RETURNED_REQUIRES_LIVENESS_READBACK` with the unit state, the container ID and start time, and the hashes and metadata of the files. Never an environment value.
- **Reconcile:** an `activation.env` that already exists **with the constant hash** is accepted, and the operation completes the enable and the two starts instead of refusing on its own guard. If the unit is already active, its own `c3po-reader` container and the two processes in it are the reader being reconciled, not a second one; the starts then change nothing and the receipt says so. Any other content of `activation.env` is a refusal.
- **Must not:** `docker exec` into any container; `docker run` by hand; recreate or restart a compose service; edit `.env` or compose; retry on an uncertain outcome.
- **What it authorises afterwards without a new GO:** the timer's start on each session of `SESSIONS`, and the unit's own restarts, with the same pinned bytes. Anything that changes a pinned byte is a new GO.

`systemctl start c3po-reader.timer` on a host that has been up for more than 90 seconds starts the service at once through `OnBootSec` *(documented systemd behaviour, not observed)*; the explicit service start that follows is then a no-op. Here that immediate start is the intended launch, which is why the activation has a window.

### 5. Pins replacement

Not pre-authorised: its own GO, naming both hashes.

- **Preconditions:** `c3po-reader.service` inactive and `c3po-reader.timer` stopped.
- **Does:** renames `pins.env` to `pins.env.superseded-<UTC stamp>` (refusing if that name exists), then creates the new `pins.env` by exclusive creation. Between the two steps the unit cannot start: its condition on `pins.env` skips it.
- **Reads back:** metadata and SHA-256 of both files. Starting the timer and the service again is an activation in reconcile mode, under a GO that names the new hash.

### 6. Liveness readbacks

Read-only. Two after an activation, two minutes apart; then the daily checkpoints of the plan.

- **Identity:** one container named `c3po-reader`, its image ID equal to the pin, its start time; `docker top` showing `docker-init`, the launcher and exactly one `app.r2d2_v2_shadow_worker` child (none between the handover and the `SESSION` start).
- **Notices:** the `STARTING` line with `build_sha`, `release_sha`, `capacity_config_sha` and `launcher_sha256` equal to the values of the GO; no `FAILED` and no `REFUSED` after it.
- **Polling:** the first worker status line, or `STATUS_WITHHELD`, after the `STARTING` line.
- **The epoch row version is supporting evidence only.** An empty poll does not rewrite the row or increment its version (`r2d2_v2_store.py` lines 69–71), and the worker logs a status line only when the public status changed (`r2d2_v2_shadow_worker.py` lines 163–165). A healthy reader with nothing to drain is therefore silent and leaves the version unchanged; two readbacks with the same version do not prove a dead reader. A version that advanced does prove a live one.
- **After the open (09:35):** `HANDOVER`, `READY_OBSERVED`, `STARTING` with phase `SESSION`. **After the end (16:25):** `STOPPED` with `END_OF_DAY`, exit 0, container absent.
- `docker inspect` output is never copied into a receipt: it holds the database URL.

### 7. Restart with the same pinned bytes

`systemctl reset-failed c3po-reader.service` followed by `systemctl start c3po-reader.service`, inside the window, then a pair of readbacks. For a unit that reached the start limit or ended in 78 for a reason that has been removed.

### 8. Deactivation

`systemctl disable --now c3po-reader.timer`, then `systemctl stop c3po-reader.service`. No file is deleted. Readback: timer disabled and inactive, unit inactive, container absent, last notice `STOPPED`. Even without it the launcher refuses every day outside `SESSIONS`; each such refusal leaves the unit failed and writes a marker.

## Stop

`systemctl stop` runs `docker stop -t 25`: SIGTERM reaches `docker-init`, which forwards it to the launcher. The handler sets a flag; within a quarter of a second the launcher sends SIGTERM to the worker, waits for it, prints `STOPPED` with reason `SIGNAL` and exits 0. If the worker does not end in 20 seconds the launcher kills it and still exits 0, with `killed` true in the notice.

With `--init` only the launcher receives the signal from `docker-init`; the worker is stopped by the launcher. If the launcher itself is killed, PID 1 of the container exits and the kernel ends every process of the container, the worker included *(documented behaviour of Docker and the kernel, not observed)*.

Offline, on real processes: the parent stopped by SIGTERM exits 0 with the child reaped; a child holding the real shared catalog lock is ended by SIGTERM, and by SIGKILL when it ignores SIGTERM, and the exclusive lock is obtained at the next request. Through `docker-init`, none of it was observed.

## Worker-direct fallback (D1)

If the launcher is not accepted, the same unit runs the worker directly. The installer takes the three texts below from this document (the lines between each pair of markers, each ended by a newline) instead of `c3po-reader.service`; They are installed as `c3po-reader.service` (rendered), `c3po-reader-stop.service` and `c3po-reader-stop.timer` (verbatim). `c3po-reader.timer` and `c3po-reader-alert.service` are unchanged, and the launcher directory and file are not created.

Differences from the shipped unit: no launcher mount; the command is the worker module; `SuccessExitStatus=143`, because the worker has no handler and a stop ends it by SIGTERM; and a second timer that stops the unit at 16:20:00 New York.

<!-- fallback-service:begin -->
```
[Unit]
Description=Day-bounded R2D2 V2 shadow reader
Wants=network-online.target
Requires=docker.service
After=network-online.target docker.service
RequiresMountsFor=@HOST_DATA_ROOT@ @HOST_CAPACITY_ROOT@ @HOST_CONFIG_DIR@
StartLimitIntervalSec=8h
StartLimitBurst=40
OnFailure=c3po-reader-alert.service

[Service]
Type=exec
Environment=DOCKER_CONFIG=@HOST_CONFIG_DIR@/docker-cli
ExecCondition=/usr/bin/test -f @HOST_CONFIG_DIR@/secret.env
ExecCondition=/usr/bin/test -f @HOST_CONFIG_DIR@/pins.env
ExecCondition=/usr/bin/test -f @HOST_CONFIG_DIR@/activation.env
ExecStartPre=-/usr/bin/docker rm c3po-reader
ExecStartPre=/usr/bin/docker image inspect --format {{.Id}} @IMAGE_ID@
ExecStart=/usr/bin/docker run --rm --init --restart no --name c3po-reader --pull never \
  --user 0:0 --workdir /app --network @NETWORK@ \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,nodev,size=256m \
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 512 --stop-timeout 25 \
  --env-file @HOST_CONFIG_DIR@/secret.env \
  --env-file @HOST_CONFIG_DIR@/pins.env \
  --env-file @HOST_CONFIG_DIR@/activation.env \
  --mount type=bind,source=@HOST_DATA_ROOT@,target=/app/day-d-data,readonly \
  --mount type=bind,source=@HOST_CAPACITY_ROOT@,target=/c3po-capacity,readonly \
  @IMAGE_ID@ \
  python -B -m app.r2d2_v2_shadow_worker
ExecStop=-/usr/bin/docker stop -t 25 c3po-reader
ExecStopPost=-/usr/bin/docker stop -t 25 c3po-reader
Restart=on-failure
RestartSec=5s
RestartPreventExitStatus=78
SuccessExitStatus=143
TimeoutStartSec=60s
TimeoutStopSec=30s
KillMode=control-group
UMask=0077
NoNewPrivileges=true
StandardOutput=journal
StandardError=journal
SyslogIdentifier=c3po-reader
```
<!-- fallback-service:end -->

<!-- fallback-stop-service:begin -->
```
[Unit]
Description=End the day of the V2 shadow reader (worker-direct fallback)

[Service]
Type=oneshot
ExecStart=/usr/bin/systemctl stop c3po-reader.service
```
<!-- fallback-stop-service:end -->

<!-- fallback-stop-timer:begin -->
```
[Unit]
Description=Stop the V2 shadow reader after the close (worker-direct fallback)

[Timer]
OnCalendar=Mon..Fri *-*-* 16:20:00 America/New_York
Persistent=false
AccuracySec=1s
Unit=c3po-reader-stop.service

[Install]
WantedBy=timers.target
```
<!-- fallback-stop-timer:end -->

What the fallback loses, all of it stated because none of it can be tested offline:

- **No day gate.** The worker runs whenever it is started: the timer fires on every weekday and after every boot, inside or outside `SESSIONS`, at any hour. Only the deactivation ends that. `pins.env` then has the eleven names; L1 does not apply.
- **No handover and no marker wait.** The reader started at 04:00 is polling at 09:29, on the first day too. The producer's bounded lock wait is the only protection of the first start.
- **No 78.** A worker that prints `OFF` exits 0, which is a success. Every refusal is exit 1 and restarts until the start limit.
- **Raw output.** The worker's status lines and its tracebacks go to the journal unfiltered. A traceback can carry a path or the text of a database error.
- **The stop is a clock time**, not the close: an early close is not followed. A stop ends the container with 143 *(documented `docker-init` behaviour, not observed)*, which the unit counts as success; so is a 143 from any other SIGTERM.
- The stop timer is enabled and started by the activation, and disabled by the deactivation, next to the start timer.

## Known limits

- **First real execution is the first session.** `Release.verify` on the installed bytes, the collector build, the database round trip from this container and the capacity configuration on the mounted tree have never run in this layout.
- **The handover covers one producer start a day.** Restarts of the producer during the session cross a polling reader.
- **A late marker.** After 09:29:50 the reader starts without it; see "Daily contract" for what the worker then records.
- **Supervision is blunt.** Exit 1 for every failure, 40 starts, then down; detection is the failure marker (no destination) and the checkpoints.
- **Liveness cannot be read from the row version alone**; see "Liveness readbacks".
- **Phases follow the wall clock.** A step of the host clock moves the handover and the end with it.
- **The timer lines are fixed clock times.** On an early close the end moves with the calendar, the 04:00:00 start does not. None of the five sessions is an early close.
- **A read-only data mount and `--cap-drop ALL`** require every input of the reader to be readable by uid 0 as its owner: a private object owned by another uid is not readable. A hot SQLite journal left by a killed producer makes the read-only reader refuse.
- **Withheld status lines.** A status line with a string the grammar does not know is not forwarded. That is a loss of detail in the journal, not of data; the grammar is in the launcher and can only change with its hash.
- **The class name of a traceback is printed.** It is an identifier chosen by code, not by data; the text after it is not printed except for the two classes named above.
- **The security reboot waits while this container runs** (04:00 to 16:20 on session days), for the reason the producer's document gives: a container without a compose label makes `admission_coverage` answer false (`scripts/c3po_security_reboot.py` lines 187–205).
- **Secret at rest.** `secret.env` is a second copy of the database URL, and the value is visible through `docker inspect` to anyone with Docker access, as it is for the compose services.
- A change of the data disk's device number across a reboot makes the catalog and the capacity roots refuse; there is no in-code recovery.
- `RequiresMountsFor` is inert if systemd has no mount unit for a path.

## Offline verification and pending checks

Repository tests, in `c3po/backend/tests`:

- `test_r2d2_v2_reader_launcher.py` loads the launcher by path. With a fake clock and scripted children it runs the refusals, the four phases, a stop request in every phase and the child exit mapping, against the real exchange calendar, the real `SESSIONS` and the real settings class. With real processes it runs: a child holding the real shared catalog lock, stopped by SIGTERM and by SIGKILL, with the exclusive lock obtained at the next request; the real worker module as a child with collection off, ending in 78; the launcher as a real process under `python -I`, stopped by a real SIGTERM, exiting 0 with the child reaped (the clock frozen inside the pre-open phase and a sleeping program in place of the worker); the unit's command form on a machine without `/app`. It checks by syntax tree that the signal handler only sets a flag and that nothing of the application is imported when the file is loaded. It feeds the output filter tracebacks, lines with symbol-like tokens and status lines carrying them, and real status lines of the real collector. It runs pre-open cycles of the real capacity-bound collector with no committed binding and checks that nothing is blocked, and that the first cycle at the open is.
- `test_r2d2_v2_reader_unit.py` pins the unit text and its argument list, the three environment files and their condition lines, the forbidden options, the read-only mounts and the top-level targets, the timer lines against the launcher's window and the producer's timer, the restart contract, the alert unit (its shell text is run with the paths replaced), the fallback texts against the shipped unit, and this document's environment names against the settings class and the modules that read them.

Faked in those tests: the clock and the children of the phase tests; the source and the release of the collector in the pre-open test (the collector, the store, the calendar and the capacity loader are the real ones, the store in memory); the paths and the `systemctl` of the alert test.

Not proven anywhere yet: systemd's parsing of the three units, `ExecCondition` and `OnFailure` on the host's systemd version, the timer's two calendar lines and its boot trigger, Docker's reading of the three environment files and which one wins on a repeated name, the mount targets `/c3po-capacity` and `/c3po-reader` under a read-only root filesystem, the launcher under `python -I` in the image, stop and SIGTERM through `docker-init` to the launcher and from it to the worker, exit statuses 0, 1, 78 and 143 through `docker-init` and `--rm`, the container start and import time against `RestartSec`, the shared lock and SQLite `mode=ro` on a read-only bind, the reader's inputs under `--cap-drop ALL`, database reachability from `@NETWORK@`, the identity of a capacity root across containers, the failure marker on the host, and every real input. These stay pending until the rehearsals of the plan are separately authorised.
