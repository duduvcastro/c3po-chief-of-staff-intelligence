# Massive producer supervision — installation candidate

Offline candidate. Nothing here has been installed, enabled, started, connected to Massive, or approved for live operation.

**Unverified on the host.** Every Docker and systemd behaviour described in this document comes from documentation and from offline tests. None of it has been observed on the production host. The single engine check is the pipeline smoke described under "Offline verification and pending checks", and it runs on the CI runner, not on the host. Statements marked *(unverified)* are the ones a reviewer could not support from the repository at all.

A read-only preflight on 2026-10-01 found nothing provisioned on the host: no `c3po-bar` account, no `/opt/c3po-bar`, `/etc/c3po-bar` or `/var/lib/c3po-bar`, no `c3po-massive` units. `/etc/systemd/system` exists as `root:root` 0755.

## Contract

The supervisor runs **inside a container of the deployed backend image**, started in the foreground by a systemd unit, as **uid 0**. There is no dedicated `c3po-bar` account, no host virtualenv and no source tree under `/opt`. The journal root lives inside the existing data volume, so the producer and the reader can see the same directory through the same container path:

```
host      <C3PO_DAY_D_DATA_MOUNT_SOURCE>/<leaf>      (for example /mnt/day-d-data/r2d2-v2-massive-epoch03)
container /app/day-d-data/<leaf>                     (producer --journal-root; reader journal directory)
```

No owner or mode guard is relaxed. Nothing existing is chowned or chmodded, and no journal is copied, moved or recreated: the catalog binds the device and inode of its root.

## The five operations

The signed epoch order requires the supervisor to be handled as five **distinct, separately authorised operations, one GO each**, in this sequence. A GO for one operation authorises nothing in the next. None of them is performed by this repository, by the deploy pipeline or by a compose service.

### 1. Preflight (read-only)

- **Does:** reads the host state needed to decide the six substitution values and the layout: whether any path of the layout or either unit file already exists, owner and mode of `/etc/systemd/system` and of the data volume root, free bytes on the data volume, `systemctl --version`, the Docker server version, whether the Docker unit is `docker.service`, `docker info` (no user-namespace remapping, no rootless mode), and the image ID of `c3po/backend:production`.
- **Must not:** create, change or delete anything; start, stop, enable or reload anything; read the token or any secret; run a container.
- **Reads back:** the observations themselves, as the receipt.

### 2. Provisioning (directories and configuration)

- **Does:** creates the directories below, each by exclusive creation (refuse if the path exists), all `root:root`, and creates the image retention tag (see "Image pin and lifecycle").

  | Path | Owner | Mode | Content at the end of this operation |
  | --- | --- | --- | --- |
  | `/etc/c3po-bar` = `@HOST_CONFIG_DIR@` | `root:root` | 0700 | the two directories below |
  | `/etc/c3po-bar/manifests` | `root:root` | 0700 | empty |
  | `/etc/c3po-bar/docker-cli` | `root:root` | 0700 | empty, and it stays empty |
  | `<data volume>/<leaf>` = `@HOST_JOURNAL_ROOT@` | `root:root` | 0700 | empty; created new inside the data mount |
  | `/var/lib/c3po-bar` | `root:root` | 0700 | the directory below |
  | `/var/lib/c3po-bar/supervisor` = `@HOST_STATE_ROOT@` | `root:root` | 0700 | empty |

- **Must not:** chown or chmod any existing object, including the data volume root; reuse an existing directory; write the token (the owner does that, see "Token procedure"); write a manifest; install a unit; create anything inside the journal root (the producer creates the catalog, see "Catalog and first-day order"); create an account, a virtualenv or anything under `/opt`.
- **Reads back:** owner, group, mode and emptiness of each created path; owner and mode of the data volume root (recorded, not changed); the retention tag resolving to the intended image ID.

The daily manifest and the token are separate deliveries with their own authority; they are not part of this operation.

### 3. Exclusive unit installation (no activation, no overwrite)

- **Does:** validates the six values against the grammar in "Substitution grammar"; renders `c3po-massive.service` with exactly the six substitutions; fails if any `@` survives in the rendered text; creates `/etc/systemd/system/c3po-massive.service` (rendered) and `/etc/systemd/system/c3po-massive.timer` (verbatim) by **exclusive creation**, `root:root` 0644, refusing if either file exists; runs `systemctl daemon-reload`.
- **Must not:** overwrite, replace or edit an existing unit file; run `systemctl enable`, `start` or `restart` on either unit; create a drop-in; start a container.
- **Reads back:** the paths, sizes and SHA-256 of the two installed files.

### 4. Readback / conference

- **Does:** reads, and changes nothing.
- **Must not:** read the token content or any digest of it; start anything.
- **Reads back:**
  - bytes and SHA-256 of the rendered `c3po-massive.service` and of the timer, compared with an independent render from the reviewed template;
  - the six values as they appear in the rendered unit;
  - owner, group and mode of every path of the layout, of the token (metadata only) and of the data volume root;
  - the image ID resolves locally (`docker image inspect --format '{{.Id}}' <ID>`) and the retention tag resolves to the same ID;
  - `systemctl is-enabled c3po-massive.timer` shows `disabled`, and neither unit is active;
  - free space on the journal filesystem (see "Activation gate");
  - `systemctl --version` (at least 240, for `Type=exec`), the Docker server version (at least 20.10, for `--pull never`), and that the Docker unit is `docker.service` (`systemctl is-active docker.service`).

### 5. Activation

- **Does:** `systemctl enable --now c3po-massive.timer` — the **timer only**. The service is started by the timer.
- **Must not:** enable or start `c3po-massive.service` directly; happen before the activation gate below is satisfied; be implied by operation 3 or 4.
- **Reads back:** `systemctl is-enabled` and `is-active` of the timer, the next elapse time, and the state of the service (see the `OnBootSec` note under "Operations").

Activation has its own authorisation. Installing the units is not activation.

## Token procedure

- The **owner** places the provider token, through a private channel, as a private file at `/etc/c3po-bar/token`. It never transits the coordination channel, a command line, the environment, a log or a receipt.
- The file is created by **exclusive creation**, mode **0600**, owned by **uid 0**, under `umask 077`. It is a regular file with a single link, 1 to 4096 bytes, holding one line.
- Never write it with `echo`, as a command argument, or as a heredoc in a recorded shell: each of those leaves the value in shell history, a process listing or a transcript. Never export it as an environment variable.
- **Readback is metadata only:** uid, gid, mode, link count and size. Never the content, never a digest of the content, never a line count (that requires reading it).
- Only the authorised supervisor process reads the content, in memory, after the claim and the backoff of each attempt. A token that is empty or spans several lines is therefore detected only after the first claim: it costs one attempt and ends that start in a terminal 78 (`SUPERVISOR_TOKEN`). So does a file with the wrong mode, owner or link count, or a configuration directory with any group/other bit (`SUPERVISOR_PRIVATE_FILE`, or a refusal of the directory).
- **Rotation** is replacing the file between sessions, by the owner, with the same procedure. The supervisor re-reads the file at each attempt; nothing caches it.
- The host `.env` holds a `MASSIVE_API_TOKEN` for other purposes. This unit does **not** use it, and it must not be copied here through the environment. The unit passes no environment to the container.
- The producer CLI has a `--token-env` option. It is **out of scope** of this rite; the unit uses `--token-file` only, and the repository tests reject `--token-env` in the template.

## Template placeholders

`c3po-massive.service` is a template with exactly six placeholders. `c3po-massive.timer` has none.

| Placeholder | Occurrences | Meaning | Example |
| --- | --- | --- | --- |
| `@IMAGE_ID@` | 1 | Image ID of the deployed backend image, read on the host. Never a tag. | `sha256:0123…cdef` |
| `@HOST_JOURNAL_ROOT@` | 2 | Host path of the dedicated journal root, inside the data volume. | `/mnt/day-d-data/r2d2-v2-massive-epoch03` |
| `@CONTAINER_JOURNAL_ROOT@` | 2 | The same directory as seen inside the containers. | `/app/day-d-data/r2d2-v2-massive-epoch03` |
| `@HOST_STATE_ROOT@` | 2 | Host path of the attempt/claim journal. | `/var/lib/c3po-bar/supervisor` |
| `@HOST_CONFIG_DIR@` | 3 | Host configuration directory: `RequiresMountsFor`, `DOCKER_CONFIG`, the read-only mount. | `/etc/c3po-bar` |
| `@NETWORK@` | 1 | Docker network of the container, chosen from the host rehearsal. | `bridge` |

`ExecStart` uses backslash continuations; a renderer that needs the argument list joins them (backslash-newline becomes a space) before reading the single `ExecStart` line.

### Substitution grammar

The template contains no `%`, `$`, quote or `;`, so a plain textual substitution is safe **only if the values are equally plain**. A space splits `RequiresMountsFor=` and the argument list; `%` is a systemd specifier; `$` triggers systemd variable expansion; a comma adds a field to `--mount`. The installer must therefore refuse, before rendering:

- for the three host paths (`@HOST_JOURNAL_ROOT@`, `@HOST_STATE_ROOT@`, `@HOST_CONFIG_DIR@`) and for `@CONTAINER_JOURNAL_ROOT@`: any value that does not match `^/[A-Za-z0-9._/-]+$`, and any value with an empty, `.` or `..` component or a trailing slash;
- for `@IMAGE_ID@`: any value that does not match `^sha256:[0-9a-f]{64}$`;
- for `@NETWORK@`: any value outside an explicit allow-list named in the authorisation. The allow-list may hold `bridge` or the name of an existing user-defined network (a name matching `^[A-Za-z0-9][A-Za-z0-9_.-]*$`). `host`, `none` and `container:*` are **forbidden in production**. (`none` is used only by the pipeline smoke, which must not reach the provider.)

It must also refuse when `@CONTAINER_JOURNAL_ROOT@` is not `/app/day-d-data/<leaf>` with the same `<leaf>` as `@HOST_JOURNAL_ROOT@`, when the journal root is not directly inside the data volume, or when the state root or the configuration directory is inside the data volume or inside the journal root.

After substitution the render **must fail if any `@` survives** anywhere in the text.

### Why each option is there

- `--pull never` and the image **ID**: the unit can never fetch an image or follow a moving tag.
- `--rm` and the fixed `--name c3po-massive`: one container at most, removed on exit; a leftover name makes the next start fail instead of running twice.
- `--user 0:0`: every guard compares against the effective uid, and the reader must have the same one.
- `--read-only` with `--tmpfs /tmp` (256 MiB, `noexec,nosuid,nodev`): the only writable paths are the two read-write binds.
- `--cap-drop ALL`, `--security-opt no-new-privileges`, `--pids-limit 512`: root in the container owns its files and needs no capability to read or write them.
- No `--init`: Python is PID 1 and installs its own SIGTERM handler, so `docker stop` reaches the orderly shutdown directly. See "Stop" for the window before the handler exists.
- No environment at all (`-e`, `--env-file`, `TZ`, `C3PO_*`): the container receives only the image defaults. The token is a file.
- Three `--mount type=bind` entries, never `-v`: `--mount` refuses a missing source instead of creating a root-owned directory.
- `--stop-timeout 25` and `docker stop -t 25`, below `TimeoutStopSec=30s`.
- `Environment=DOCKER_CONFIG=@HOST_CONFIG_DIR@/docker-cli` applies to the docker CLI only: an empty root-owned directory, so root's contexts, proxies and credential helpers cannot leak in. `DOCKER_HOST` is not set (default socket). The container sees that directory, empty, through the read-only configuration mount.

Never add: `--init`, `--restart`, `-d`, `-t`, `-i`, `-e`/`--env`/`--env-file`, `-v`/`--volume`, `--privileged`, `--cap-add`, `--cidfile`, `--pid`, `--ipc`, a mount of the Docker socket, a tag reference such as `c3po/backend:production` or `:rollback`, a forced removal (`rm -f`, `--force`), `User=`/`Group=`. The repository tests pin the argument list and reject each of these.

## Image pin and lifecycle

**How `@IMAGE_ID@` is obtained.** On the host, after the deploy of the merged revision, by inspection:

```
docker image inspect --format '{{.Id}}' c3po/backend:production
```

With the containerd image store the ID is the manifest digest of the image as loaded on the host. It will **not** equal an ID computed on the CI runner, so it cannot be taken from the pipeline, from a build log or from another machine. The value is read once, validated against `^sha256:[0-9a-f]{64}$`, and used for the retention tag and for the render.

**A missing image is a failed start.** With `--pull never`, an ID that does not resolve locally makes `docker run` exit 125. That consumes one of the six systemd starts, takes **no claim** and emits no receipt (see the exit table).

**Retention.** Nothing in the unit keeps the image present. The deploy pipeline, at each deploy, removes the `c3po/backend:rollback` tag, tags the image of the running `api` container as `:rollback`, loads the new image as `:production`, and after a healthy deploy runs `docker image prune --force`, which removes only dangling (untagged) images. For an image referenced only by ID this implies:

- after the first later deploy it is still tagged, as `:rollback`;
- at the second later deploy the `:rollback` tag is removed from it. It then has no tag at all. Whether Docker deletes it at that tag removal or at the following prune was not observed on the host *(unverified)*; in either case it does not survive that deploy unless a container still uses it, and every start of the unit after that is a 125.

The explicit retention step is a **dedicated tag**, for example `c3po/backend:massive-supervisor-epoch03`, pointing at the pinned ID:

```
docker image tag <IMAGE_ID> c3po/backend:massive-supervisor-<epoch label>
```

- **Who and when:** the authorised operator, in operation 2 (provisioning), after refusing if that tag already exists (`docker image tag` overwrites silently).
- **Readback:** `docker image inspect --format '{{.Id}}' c3po/backend:massive-supervisor-<epoch label>` equals the `@IMAGE_ID@` value; repeated in operation 4.
- The pipeline never touches that tag: it removes only `:rollback` and prunes only untagged images. The tag is never referenced by the unit; the unit keeps the ID.

**Next deploy.** A deploy or a rollback does not change what the unit runs. The old unit keeps running the old image, by ID, until it is re-rendered. Meanwhile the reader may already run a newer image; nothing in this unit detects that.

**Next epoch, or a deliberate image change.** A new render (new image ID, and for a new epoch a new journal leaf and a new retention tag) goes through the same five operations under its own authorisation. Because operation 3 never overwrites, the previous timer is first disabled and the previous unit files are removed by a separately authorised step. The old retention tag is removed only after the new unit is active and the old one is gone.

## Catalog and first-day order

There is **no separate catalog initialisation step**. The producer creates the catalog itself on its first run: `_run_session_root` calls `SessionJournalRoot(root, epoch, create=True)`, which creates `maintenance.lock` and writes `epoch.json` in an empty private root, binding the epoch string and the device and inode of the directory. The repository test `test_container_layout_writer_and_reader_agree` runs the producer on an empty root with no prior step.

The epoch written into the catalog is the `epoch` key of **that day's manifest**. It must equal the `epoch` field of the signed release body that the reader verifies. A wrong epoch in the first manifest binds the root permanently: the reader refuses it from then on, and the only recovery is a new directory. Copy the string from the signed release; do not type it.

What the reader does on a root without a catalog: with Massive bars enabled, the V2 shadow worker builds `SessionJournalRoot(journal directory, release.epoch)` without `create`. If the root is missing, empty, not private, owned by another uid or bound to another epoch, the worker refuses at start with `MASSIVE_SESSION_ROOT_UNVERIFIED` and exits. It does not create anything and does not retry by itself. This applies to **every** invocation of that module with Massive bars enabled, including `--prepare-capacity-day`, because the source is built before the argument is handled. With Massive bars disabled the worker touches no Massive directory.

Order for the first day of an epoch:

1. Operations 1 to 4 are complete; the journal root exists, `root:root` 0700, and is empty.
2. `prepare-capacity-day` for that day runs in the V2 shadow worker **with Massive bars disabled**. It derives and commits the capacity binding and does not read the event source. Running it with Massive bars enabled at this point refuses with `MASSIVE_SESSION_ROOT_UNVERIFIED`, because no catalog exists yet. Whether the activation rite permits this invocation with the flag disabled is that rite's decision; it is not settled here.
3. That day's manifest is delivered, before 09:29 New York time.
4. 09:29 New York time: the timer starts the unit. The producer's first run creates and binds the catalog for the epoch, then the session directory.
5. Only after the catalog exists (the journal root holds `epoch.json` with the release epoch) may the reader be started with Massive bars enabled.

On later days the catalog already exists and step 2 may run with Massive bars enabled.

## Reader requirements

The reader of the journal is the process `python -m app.r2d2_v2_shadow_worker`. **No compose service launches that module.** The compose service `r2d2-worker` runs `python -m app.r2d2_worker`, which never opens the Massive journal. The V2 shadow worker is launched by the separately authorised activation rite, through the operator executor, so its container, uid, mounts and environment are set by **that launcher**. Editing the host `.env` or recreating a compose service does not configure the reader.

This unit works only if that launcher gives the reader:

- the **same uid** as the producer, uid 0: every guard compares the owner of the root, catalog, session directories and files with the reader's effective uid;
- the journal root at the **same container path** as `@CONTAINER_JOURNAL_ROOT@`, on the same filesystem (the catalog binds device and inode); mounting the data volume at `/app/day-d-data` satisfies this;
- **read access** to the root. The reader writes nothing in the journal tree; it opens the existing `maintenance.lock` read-only for a shared lock. A read-only mount is expected to be sufficient but was not exercised *(unverified)*;
- `C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR` equal to `@CONTAINER_JOURNAL_ROOT@`, **explicitly**. The default is `/app/data/r2d2-v2-massive`; a launcher that omits the variable makes the reader refuse with `MASSIVE_SESSION_ROOT_UNVERIFIED`;
- `C3PO_R2D2_V2_MASSIVE_BARS_ENABLED` set only according to the first-day order above.

The launcher's contract must name these values and prove them in its own readback. Nothing in this directory does.

## Process and restart contract

The timer requests one start at 09:29 New York time, Monday through Friday, and another 30 seconds after boot. The boot trigger recovers a host that was down at the calendar trigger. The wrapper checks the XNYS calendar (holidays and shortened sessions) and permits starts only from open minus 60 seconds until close. A start outside that window produces a safe terminal refusal, with no token load or provider connection. Missed calendar timers are not replayed (`Persistent=false`). The producer receives through close plus 91 seconds; no new connection starts after close. A late failure that cannot restart remains an explicit coverage gap.

The wrapper allows one initial attempt and **four retries**, with monotonic waits of **30, 60, 120 and 240 seconds** before retries 1–4. systemd requests restart on failure with a one-second floor, additional to the wrapper wait. With immediate connection failures, provider attempts occur approximately at 0, 31, 92, 213 and 454 seconds, plus the container start of each attempt (estimated 1–3 seconds, unmeasured). This is bounded recovery, not an assurance of provider availability. Successful STOPPED/SESSION_LIMIT exits are not restarted. Exit 78 is a terminal refusal and suppresses restart.

Exclusive, fsynced per-session claims cap provider attempts at **five across process crashes, reboots and manual restarts**, regardless of `reset-failed`. Claims must not be deleted to replenish allowance. Waiting holds the supervisor lock, checks stop/window each second and reads no token until the delay finishes. A crash or interruption during the wait conservatively consumes that claim. Changing the dated manifest never resets allowance. systemd additionally caps six process starts in eight hours: five attempts plus one process that can emit the final exhausted-budget refusal.

Exit statuses seen by systemd:

| Status | Origin | Effect |
| --- | --- | --- |
| 0 | supervisor: STOPPED / SESSION_LIMIT | success, no restart |
| 1 | supervisor: attempt failed | restart; the next process claims the next attempt |
| 78 | supervisor: terminal refusal | no restart for that start |
| 125, 126, 127 | docker: missing image or mount source, daemon unavailable, name conflict, command not runnable | restart; consumes systemd starts, **never claims**, emits **no** receipt |
| 137 | container killed | restart; the interrupted attempt stays consumed |

The 125–137 failures bypass the 30/60/120/240 backoff: six starts can be spent in seconds with no `DATA_GAP` line. `--rm` can also surface a clean 78 as 125 if waiting for the removal fails; that direction is fail-safe for coverage claims but costs a start. Alert on the unit results `start-limit` **and** `dependency`: with `Requires=docker.service`, a Docker service that fails its start leaves this unit with a `dependency` result, no restart and no receipt.

`ExecStartPre` (`docker rm`) runs under the default `TimeoutStartSec` (90 seconds unless the host changed the default). With a hung Docker daemon each start can spend up to that long, ends as a failure with no receipt, and consumes one of the six starts.

## Filesystem layout

All objects are `root:root`. New directories are created exclusively (refuse if they exist).

| Path | Mode | Role |
| --- | --- | --- |
| `<data volume>` (`C3PO_DAY_D_DATA_MOUNT_SOURCE`) | existing, **not modified** | Mounted at `/app/day-d-data` in the backend services. Its owner and mode are recorded at readback. |
| `<data volume>/<leaf>` = `@HOST_JOURNAL_ROOT@` | **0700**, new and empty | Dedicated journal root of one epoch. Holds only `epoch.json`, `maintenance.lock`, `producer.lock`, `session_date=YYYY-MM-DD/`. Never a filesystem root; nothing else may be placed inside it. |
| `/var/lib/c3po-bar` | **0700** | Private parent, outside every compose mount. |
| `/var/lib/c3po-bar/supervisor` = `@HOST_STATE_ROOT@` | **0700**, contents 0600 | Claims and `producer.lock`. Outside the journal root and outside the data volume. |
| `/etc/c3po-bar` = `@HOST_CONFIG_DIR@` | **0700** | Mounted read-only **as a directory** in the supervisor container only. |
| `/etc/c3po-bar/docker-cli` | **0700**, empty, stays empty | `DOCKER_CONFIG` of the unit's docker CLI. |
| `/etc/c3po-bar/manifests` | **0700** | Dated manifest directory. |
| `/etc/c3po-bar/manifests/YYYY-MM-DD.json` | exactly **0600**, regular, single link, at most 65536 bytes | One manifest per session date. |
| `/etc/c3po-bar/token` | exactly **0600**, regular, single link, 1–4096 bytes, one line | Provider token, placed by the owner. Never under the data volume. |
| `/etc/systemd/system/c3po-massive.service`, `.timer` | 0644 | Rendered unit and verbatim timer, created exclusively by operation 3. |

The state root nested in the journal root is refused by the producer (`MASSIVE_SERVICE_STORAGE_UNVERIFIED`, exit 1). A foreign entry in the journal root makes every reader poll refuse. The journal root with any group/other bit, or owned by another uid, is refused by producer and reader alike. Only the journal root itself is checked for privacy; its ancestors are checked only for symbolic links.

## Daily manifest

The manifest has exactly the keys `epoch`, `session`, `symbols`, `owner_uid`. `owner_uid` is the JSON integer `0`. `epoch` equals the signed release epoch. There is **one manifest per session date**, and it can only be written after that day's `prepare-capacity-day`, because the symbols are that day's committed capacity binding. It must be in place before 09:29 New York time. A missing manifest inside the window is a terminal 78 for that start, with no claim. Once the first claim binds the manifest's SHA-256 its bytes are frozen for the day; a change is refused and never resets allowance.

## Stop

`systemctl stop` runs `docker stop -t 25`: SIGTERM to the supervisor, which closes the socket and exits 0 after its storage scans. `TimeoutStopSec=30s` applies to each stop command separately; with a hung Docker daemon the worst case is about three such periods (around 90 seconds). Do not promise 30 seconds in total.

Python is PID 1 in the container, and the kernel ignores a SIGTERM sent to PID 1 while no handler is installed. The supervisor installs its handler in `main()`, after the interpreter has started and the modules are imported. A stop that arrives in that window is ignored: `docker stop` waits the full 25 seconds and then kills the container (137). The unit ends failed, not stopped. No claim exists yet at that point.

A forced kill consumes the attempt (137) and the next recovery treats it as a gap. It may also leave a hot `sequence.sqlite3-journal` in the session directory, which the read-only reader cannot roll back and therefore refuses; recovery is an authorised read-write open as uid 0 with the same image, never a deletion.

## Receipts and retention

The supervisor prints one JSON line per notice on standard output. The unit sends the docker CLI's output to **journald** (`SyslogIdentifier=c3po-massive`); that is the only retained copy, kept for as long as the host's journald retention keeps it. Docker's own log driver holds a second copy of the container output under its data directory until `--rm` removes the container at exit. Neither copy holds a secret. This candidate configures no export, no alert destination and no retention policy.

Terminal refusal receipts retain `reason=SUPERVISOR_REFUSED` and add a safe `code`: `SUPERVISOR_WINDOW`, `SUPERVISOR_SESSION`, `SUPERVISOR_ATTEMPTS_EXHAUSTED`, `SUPERVISOR_MANIFEST`, `SUPERVISOR_MANIFEST_CHANGED`, `SUPERVISOR_CLAIM_INVALID`, `SUPERVISOR_PRIVATE_FILE`, `SUPERVISOR_FILE_CHANGED`, `SUPERVISOR_TOKEN`, `SUPERVISOR_MONOTONIC`, `SUPERVISOR_FILE_UNAVAILABLE`, or a constant code already defined in the reviewed producer modules. All other errors become `SUPERVISOR_UNVERIFIED`; raw exception text, paths and credentials are never copied into notices. BACKOFF receipts record attempt number and wait seconds.

## Operations

- Operate only through `systemctl`. The effect on the unit of an out-of-band `docker stop` or `docker restart` of `c3po-massive` was not established *(unverified)*; do not use them.
- The journal stream is not pure JSON. Docker prints the container name on stop, and `No such container` from `ExecStartPre` and from the stop commands once the container is gone (once after a failed exit, twice after a clean one). Parsers must match the JSON status fields, not assume every line parses.
- Do not infer clean coverage from exit 0 or a healthy unit state. Route `DATA_GAP`, `FAILED`, `start-limit` and `dependency` to the approved alert destination; none is configured by this candidate.
- If the docker CLI is killed while the container lives, the next start fails on the name (125) until the stop commands and the asynchronous removal finish: two or three starts. A container stuck in a dead or removal-in-progress state defeats the non-forced `docker rm`; an operator removes it manually after confirming it is not running, then runs `systemctl reset-failed c3po-massive.service`. The unit never forces a removal.
- `OnBootSec=30s` fires immediately when the timer is activated more than 30 seconds after boot. That start ends in 78 outside the window, leaves the unit failed and uses one of the six starts if it happens within eight hours of 09:29. Activate earlier, or run `systemctl reset-failed c3po-massive.service` after activation.
- An explicit `systemctl restart docker` stops and restarts this unit through `Requires=`: outside the window that is a 78 and a consumed start, inside it a new claim and a short gap. Hold Docker package upgrades and avoid Docker restarts during sessions; a daemon crash is unproven.
- Schedule host reboots outside 09:29–16:02 New York time. How the security reboot controller classifies the running supervisor container was not established *(unverified)*.
- Do not add a compose service, a restart policy or a second loop or timer for the producer.

## Weaker than the previous native unit

The previous candidate ran the supervisor natively as an unprivileged `c3po-bar` account inside systemd's sandbox. The container form is weaker in these respects:

- The workload is real uid 0 (no user-namespace remapping), not an unprivileged account. A runtime or kernel escape lands as host root.
- `UMask=0077` and `NoNewPrivileges=true` in the unit now apply **only to the docker CLI**. The container runs with umask 0022. Journal, claim and lock privacy relies on the explicit 0600/0700 modes in the code, which the repository tests assert under umask 022.
- `ProtectSystem`, `ProtectHome`, `PrivateTmp`, `ReadOnlyPaths` and `ReadWritePaths` are gone. Their replacements are `--read-only`, `--cap-drop ALL`, `--security-opt no-new-privileges` and the three explicit mounts. These are Docker's controls, not systemd's.
- The unit's main process is the docker CLI, running as root on the host with access to the Docker daemon, outside any sandbox.
- The container is **outside the unit's cgroup**. `KillMode=control-group` kills the CLI, not the container; a killed CLI leaves the container alive until `ExecStopPost` stops it.
- The trust base now includes the Docker daemon and containerd. Anyone with Docker access on the host can enter the running container and read the token.
- With uid 0 on both sides, the owner guards no longer distinguish the producer from the other root containers that mount the whole data volume read-write (api, r2d2-worker, shadow-candidate). They prove "root wrote this", not "the producer wrote this". The token and the claims stay outside the data volume for that reason.

## Known limits

- **Free-space floor.** The producer requires 50 GiB free (`MIN_SESSION_FREE_BYTES`, 53687091200 bytes), measured with `fstatvfs` on the journal root's filesystem, which is the data volume. Below it the attempt ends with exit **1**, not 78 (`MASSIVE_SERVICE_LOW_DISK`), before any provider connection. Exit 1 restarts, so all five attempts of the day are burnt. The data volume had about 50.4 GiB free on 2026-10-01: the margin is a few hundred MiB.
- **Lock contention at start.** The producer takes the catalog lock exclusively and without waiting when it starts (catalog open and session preparation); the reader holds a shared lock for the duration of each poll. If the reader holds it at that instant, the attempt ends with exit 1 and `MASSIVE_MAINTENANCE_BUSY`, with no provider connection, and **consumes a claim**. The next attempt follows after the backoff. This predates the container layout and is not fixed here.
- A change of the data disk's device number across a reboot makes both sides refuse the root; there is no in-code recovery.
- Cooperative local locks do not prove provider-account exclusivity on other hosts; that remains the owner's responsibility.
- `RequiresMountsFor` is inert if systemd has no mount unit for the data volume.

## Clock behavior

Authentication/liveness/runtime deadlines use monotonic time. The producer injects that clock into minute scheduling and anchors the daily end deadline to elapsed time at startup. A 5 ms UTC rollback neither crashes the scheduler nor extends the session runtime. A minute expires only after both its monotonic elapsed deadline and market UTC deadline have passed. Provider timestamps and actual received/available timestamps are never rewritten. Larger UTC corrections can delay evidence; no fabricated timestamp or completeness assertion compensates for that.

## Activation gate

Operation 5 is not authorised until both parts below are on record.

**Readback (from operation 4), measured on the host:**

1. The Docker unit is `docker.service` and is active.
2. `systemctl --version` reports at least 240 (`Type=exec`).
3. The Docker server version is at least 20.10 (`--pull never`).
4. Free space on the journal root's filesystem (`df -B1 --output=avail <data volume>`) is above 53687091200 bytes with a margin that covers the expected growth until the next session; at or below the floor every attempt of the day is spent.
5. The image ID resolves locally and the retention tag points at it.
6. Token metadata: uid 0, gid 0, mode exactly 0600, one link, size between 1 and 4096; parent directory 0700.
7. The timer is `disabled` and inactive.

**Rehearsal**, separately authorised, of the rendered unit against a throwaway journal root, state root, configuration directory and unit name:

1. `systemctl stop` ends the main process with exit 0 in under 25 seconds, `STOPPED` in the journal, no leftover container.
2. A TLS connection to `socket.massive.com:443` succeeds from `@NETWORK@`, without a token.
3. `systemd-analyze verify` passes on the installed systemd version.
4. `docker info` shows neither user-namespace remapping nor rootless mode.
5. The pipeline smoke command returns 78 on the host with the pinned `sha256:` ID.
6. A second container sees the same device and inode for the throwaway root, and a lock held in one container is visible in the other.

## Offline verification and pending checks

Repository tests pin the unit text and its argument list, reject the forbidden options, check that the template holds none of the characters that would make a textual render differ from systemd's own parsing, render the template with sample values and check the paths against the backend data mount, and run the real supervisor, producer and reader code on a temporary tree with the container layout: writer and reader agree on uid and path, the reader leaves the tree untouched, the producer creates the catalog on an empty root, the reader refuses an empty root, and a different owner, a non-private root, a foreign entry, a nested state root, a foreign manifest owner and an exposed token directory are all refused. They also pin that this document names the five operations and the substitution grammar.

The pipeline renders `ExecStart` from this template and runs it against the validation image on the runner's Docker with three root-owned 0700 binds, the image by ID and no network. It requires exit 78, exactly one `DATA_GAP` line, no claim, no journal object and no leftover container. That proves the option set, mount-target creation under a read-only root filesystem, imports under the capability/pid/tmpfs limits, the ID reference with `--pull never`, and propagation of 78 through `--rm`. It runs on pull requests and remediation dispatches only, not on the build that produces the deployed image.

Not proven anywhere yet: stop and SIGTERM as PID 1, egress, DNS and CA trust from `@NETWORK@`, ID resolution under the host's image store, deletion or survival of an untagged image across deploys, behaviour of an empty `DOCKER_CONFIG` directory on the host, the reader on a read-only mount, the stop bound with many retained sessions, alert delivery, and real provider behaviour. These stay pending until the rehearsal above is separately authorized.
