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

Two further steps sit inside that sequence and are **not** covered by any of the five GOs:

- the **owner's token delivery**, between operations 2 and 4 (see "Token procedure");
- the **catalog initialisation** (4b), which writes inside the journal root and has **its own authorisation and receipt**. It must be complete before the first `prepare-capacity-day` of the epoch. Whether the order counts it as a sixth operation or as an addendum to one of the five, and at which point of the sequence it runs, is for the signatories; this document only requires that it is authorised separately and receipted, and recommends a position.

Recommended sequence: 1 preflight → 2 provisioning (with the retention tag) → **4b catalog initialisation** → owner token delivery → 3 exclusive unit installation → 4 readback → 5 activation.

"4b" is a name, not a position: it is kept because the repository tests and other documents refer to it, and its section stays after operation 4 below. The recommendation is to run it **right after operation 2**, before operation 3 renders the units with that journal leaf. It needs only what operation 2 leaves behind (the empty journal root, the empty docker CLI configuration directory and the image ID of the retention tag) and the epoch string, and an outcome other than `CATALOG_READY` means a new directory (see operation 4b). Run there, a failed 4b costs a new directory and a new 4b authorisation: the replacement leaf is created exclusively, `root:root` 0700 and empty, under its own authorisation (operation 2 is not repeated as written, because it refuses the paths it has already created); the two journal-root substitution values, `@HOST_JOURNAL_ROOT@` and `@CONTAINER_JOURNAL_ROOT@`, change with it; and the abandoned directory is left in place, because nothing described here deletes a journal root or anything inside one. Run after operations 3 and 4, a failed 4b also leaves installed units that name a leaf which will not be used: the unit files are removed under a separate authorisation, operation 3 is run again with the new leaf, and operation 4 is repeated.

### 1. Preflight (read-only)

- **Does:** reads the host state needed to decide the six substitution values and the layout: whether any path of the layout or either unit file already exists, owner and mode of `/etc/systemd/system` and of the data volume root, free bytes on the data volume, `systemctl --version`, the Docker server version, whether the Docker unit is `docker.service`, `docker info` (no user-namespace remapping, no rootless mode, and the init binary it reports, see "Activation gate"), and the image ID of `c3po/backend:production`. An image ID read before the deploy of the merged revision is an observation only: the ID that is rendered is the one read after that deploy (see "Image pin and lifecycle").
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

- **Must not:** chown or chmod any existing object, including the data volume root; reuse an existing directory; write the token (the owner does that, see "Token procedure"); write a manifest; install a unit; create anything inside the journal root (operation 4b does that, under its own authorisation); create an account, a virtualenv or anything under `/opt`.
- **Reads back:** owner, group, mode and emptiness of each created path; owner and mode of the data volume root (recorded, not changed); the retention tag resolving to the intended image ID.

The daily manifest and the token are separate deliveries with their own authority; they are not part of this operation.

### Owner token delivery (between operations 2 and 4)

The owner places the token after operation 2 has created `/etc/c3po-bar` and before operation 4 reads its metadata, following "Token procedure". It is not one of the operator's operations and no GO of the sequence covers it. **Operation 4 fails closed if the token is absent**: no readback, no activation.

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
  - owner, group and mode of every path of the layout and of the data volume root;
  - the token, **metadata only**: uid, gid, mode, link count, and the statement "size within 1–4096" (true or false). The size itself is not recorded, because it discloses the token length. If the token is absent the readback fails closed;
  - the catalog, when operation 4b has already run (the recommended order): the journal root holds exactly `epoch.json` and `maintenance.lock`, `root:root` 0600, and the 4b receipt is on record;
  - the image ID resolves locally (`docker image inspect --format '{{.Id}}' <ID>`) and the retention tag resolves to the same ID;
  - the init binary: `docker info --format '{{.InitBinary}}'` and the path, owner and mode of the `docker-init` executable on the host (the unit uses `--init`);
  - `systemctl is-enabled c3po-massive.timer` shows `disabled`, and neither unit is active;
  - free space on the journal filesystem (see "Activation gate");
  - `systemctl --version` (at least 240, for `Type=exec`), the Docker server version (at least 20.10, for `--pull never`), and that the Docker unit is `docker.service` (`systemctl is-active docker.service`).

### 4b. Catalog initialisation (own authorisation, before the first prepare-capacity-day)

- **Does:** one run of the pinned image, described exactly under "Catalog initialisation": creates `maintenance.lock` and `epoch.json` in the empty journal root, binding the epoch string of the signed release and the device and inode of the directory.
- **Must not:** run with any other mount, with a network, or with a script whose SHA-256 differs from the one in the authorisation; take the epoch from anything but the signed release body; run on a root that holds anything other than a catalog already bound to the same epoch; be repeated as a way to "fix" a root (a wrong binding is permanent, the recovery is a new directory under a new authorisation).
- **Reads back:** the single JSON line printed by the script (the receipt), the names, owner and mode of the two files in the root, and the epoch of the receipt compared by command with the `epoch` field of the release bytes.
- **When:** recommended right after operation 2 and before operation 3 (see the sequence above), in any case before the first `prepare-capacity-day`. The signatories decide.
- **If the creating run does not end in `CATALOG_READY`** — a `CATALOG_REFUSED` line, no line at all, a container killed part-way — that directory is not used again: the recovery is a **new directory under a new authorisation**, never a second run on the same root. "Catalog initialisation" explains why a partial root cannot be repaired.

### 5. Activation

- **Does:** `systemctl enable --now c3po-massive.timer` — the **timer only**. The service is started by the timer. It is then followed by `systemctl reset-failed c3po-massive.service` (see below).
- **Must not:** enable or start `c3po-massive.service` directly; happen before the activation gate below is satisfied; be implied by operation 3, 4 or 4b; **be performed inside the session window** (from 60 seconds before the XNYS open until the close).
- **Reads back:** `systemctl is-enabled` and `is-active` of the timer, the next elapse time, the single refusal line of the immediate start, and the state of the service after `reset-failed`.

Activation has its own authorisation. Installing the units is not activation.

**What `enable --now` does at once.** The timer carries `OnBootSec=30s`. On a host that has been up for more than 30 seconds that trigger is already in the past, so activating the timer starts the service immediately *(documented systemd behaviour, not observed on the host)*:

- **outside the window** (the required case): the supervisor refuses before reading any file — one `DATA_GAP` line with `SUPERVISOR_WINDOW` (or `SUPERVISOR_SESSION` on a non-session day), exit 78, no claim, no token read, no connection. The unit is left failed and one of the six starts of the eight-hour interval is used. `systemctl reset-failed c3po-massive.service` is the expected next step, not an alternative: it clears the failed state and the start counter, so the 09:29 start has all six.
- **inside the window, with that day's manifest and the token in place:** it is a **real attempt** — claim 1 is taken, the token is read and the provider connection is opened. That is a session start decided by the clock of whoever typed the command, which is why activation inside the window is forbidden.
- **inside the window, without the manifest:** exit 78 (`SUPERVISOR_FILE_UNAVAILABLE`), no claim.

## Token procedure

- The **owner** places the provider token, through a private channel, as a private file at `/etc/c3po-bar/token`. It never transits the coordination channel, a command line, the environment, a log or a receipt.
- The file is created by **exclusive creation**, mode **0600**, owned by **uid 0**, under `umask 077`. It is a regular file with a single link, 1 to 4096 bytes, holding one line.
- Never write it with `echo`, as a command argument, or as a heredoc in a recorded shell: each of those leaves the value in shell history, a process listing or a transcript. Never export it as an environment variable. Never open the file in an editor: editors leave swap and backup files in `/etc/c3po-bar`.
- **Readback is metadata only:** uid, gid, mode, link count and whether the size is within 1–4096. Never the content, never a digest of the content, never the size itself (it is the token length), never a line count (that requires reading it).
- Only the authorised supervisor process reads the content, in memory, after the claim and the backoff of each attempt, so a bad token is detected only **after one claim**: it costs one attempt and ends that start in a terminal 78. The code reported depends on the defect (`r2d2_v2_massive_supervisor.py`, `private_bytes` lines 38–55 and the token read at lines 114–115):

  | Defect | Code | Where |
  | --- | --- | --- |
  | zero bytes, more than 4096 bytes, mode other than 0600, another owner, more than one link, not a regular file | `SUPERVISOR_PRIVATE_FILE` | `private_bytes`, lines 45–47 |
  | only whitespace, or more than one line | `SUPERVISOR_TOKEN` | line 115 |
  | bytes that are not UTF-8 | `SUPERVISOR_UNVERIFIED` | the decode at line 114 raises; `refusal_code` falls through, lines 30–34 |
  | missing file, or a symbolic link | `SUPERVISOR_FILE_UNAVAILABLE` | the open at line 42 fails; `refusal_code`, line 33 |
  | configuration directory with any group/other bit | `SOURCE_DIRECTORY_NOT_PRIVATE` | `_open_directory`, line 40, which ends in `_private_directory` (`r2d2_v2_sources.py` line 158); `refusal_code` passes the constant through, line 34 |

  Every row is exit 78 after one claim. A single trailing newline is accepted (the value is stripped).

**Approved recipe (first delivery).** The owner runs this, by hand, in an interactive **bash** root shell that is not being recorded (no `script`, no terminal multiplexer logging, no sudo input/output logging), with the token on the clipboard or typed:

```
unset HISTFILE
set +o history
umask 077
set -o noclobber
IFS= read -rs token_line
[ -n "$token_line" ] && printf '%s\n' "$token_line" > /etc/c3po-bar/token && stat -c '%u %g %a %h' /etc/c3po-bar/token
unset token_line
exit
```

- **Type the lines one at a time; do not paste the block.** `read` takes the next line that arrives on the terminal, so in a pasted block it consumes the line after it as the value. Here that line is the write itself: nothing is written and no `stat` line appears. Only the token is pasted, at the `read`.
- `unset HISTFILE` and `set +o history`: nothing typed in this shell is written to a history file or kept in the history list.
- `umask 077`: the file is created 0600.
- `set -o noclobber`: the `>` redirection creates the file **exclusively**; if `/etc/c3po-bar/token` already exists the command fails and nothing is written.
- `IFS= read -rs token_line`: bash reads one line from the terminal **without echo** (`-s`), without backslash processing (`-r`) and without trimming (`IFS=`). The owner pastes or types the token and presses Enter; nothing appears on the screen.
- `[ -n "$token_line" ] &&`: an empty value writes nothing. Without this guard an Enter with nothing before it would create a one-byte file holding only a newline; that file passes the metadata readback ("size within 1–4096" is true) and is refused only at the 09:29 start, as `SUPERVISOR_TOKEN`, after claim 1. The guard does not catch a value made of spaces; that is still the `SUPERVISOR_TOKEN` row above.
- `printf` is a bash **builtin**: no process is created, so the value never appears in an argument list or a process listing. `token_line` is a shell variable that is never exported, so it is in no environment. It writes exactly one line.
- `&& stat`: uid, gid, mode and link count are printed **only when this shell has just written the file**, expected `0 0 600 1`. After an empty value or a refused exclusive create there is no `stat` line, and that absence is the answer: the line never describes a file that was already there. It deliberately does not print the size.
- `unset token_line` drops the value; `exit` ends the shell.
- If the token was pasted, the clipboard it came from still holds it after `exit`. Clearing it is the owner's step, on the owner's machine; nothing on this host can do it.

The recipe was exercised offline, in bash 3.2 on a pseudo-terminal and with the local `stat` in place of `stat -c`, for the exclusive create, the mode, the empty value and the pasted block. It has not been run on the host, and a shell with bracketed paste may treat a pasted block differently *(unverified)*.

**Rotation.** Exclusive creation refuses an existing path, so rotation is **not** the first-delivery recipe again. Between sessions (never between 09:29 and 16:02 New York time), the owner repeats the recipe with `/etc/c3po-bar/token.new` as the target of the redirection and of `stat` (same directory, still exclusive, still 0600) and, in the same shell, **after the `stat` line has appeared and before `exit`**, runs `command mv -T /etc/c3po-bar/token.new /etc/c3po-bar/token`. Without the `stat` line the `mv` is not run: nothing was written, and the rename would install whatever an earlier attempt left in `token.new`. `command` bypasses an alias: a root shell that aliases `mv` to `mv -i` would stop at an overwrite prompt instead of renaming (whether the host has that alias was not checked). The rename is atomic and stays on one filesystem; the previous token is unlinked by it. The supervisor re-reads the file at each attempt; nothing caches it. A rotation is followed by a metadata readback like the first delivery.

An abandoned `token.new` — a rotation interrupted, or ended without the `mv` — still holds a token value and makes the next rotation's exclusive create fail. The **owner** removes it: it is the owner's secret, and no operation of the operator covers it. The supervisor never opens `token.new` (the unit names `/etc/c3po-bar/token`), so the leftover does not affect a session.

- The host `.env` holds a `MASSIVE_API_TOKEN` for other purposes. This unit does **not** use it, and it must not be copied here through the environment. The unit passes no environment to the container.
- The producer CLI has a `--token-env` option. It is **out of scope** of this rite; the unit uses `--token-file` only, and the repository tests reject `--token-env` in the template.

## Template placeholders

`c3po-massive.service` is a template with exactly six placeholders. `c3po-massive.timer` has none.

| Placeholder | Occurrences | Meaning | Example |
| --- | --- | --- | --- |
| `@IMAGE_ID@` | 2 | Image ID of the deployed backend image, read on the host: the image check and the run. Never a tag. | `sha256:0123…cdef` |
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
- `--init`: PID 1 in the container is `docker-init` (tini), and the supervisor is its child. `docker-init` forwards SIGTERM to the supervisor, reaps children, and exits with the supervisor's own exit status, so 0, 1 and 78 reach systemd unchanged *(documented Docker behaviour, not observed on the host)*. It requires the `docker-init` binary on the host; the activation gate reads it back, and the pipeline smoke runs with it. See "Stop" for what it changes.
- `--restart no`: the container has no restart policy of its own; systemd owns every restart. Written as two words like every other option of the line; it is the same as `--restart=no`, and Docker rejects any other policy together with `--rm`.
- `--user 0:0`: every guard compares against the effective uid, and the reader must have the same one.
- `--read-only` with `--tmpfs /tmp` (256 MiB, `noexec,nosuid,nodev`): the only writable paths are the two read-write binds.
- `--cap-drop ALL`, `--security-opt no-new-privileges`, `--pids-limit 512`: root in the container owns its files and needs no capability to read or write them.
- No environment at all (`-e`, `--env-file`, `TZ`, `C3PO_*`): the container receives only the image defaults. The token is a file.
- Three `--mount type=bind` entries, never `-v`: `--mount` refuses a missing source instead of creating a root-owned directory.
- `--stop-timeout 25` and `docker stop -t 25`, below `TimeoutStopSec=30s`.
- `Environment=DOCKER_CONFIG=@HOST_CONFIG_DIR@/docker-cli` applies to the docker CLI only: an empty root-owned directory, so root's contexts, proxies and credential helpers cannot leak in. `DOCKER_HOST` is not set (default socket). The container sees that directory, empty, through the read-only configuration mount.

Never add: a `--restart` policy other than `no`, `-d`, `-t`, `-i`, `-e`/`--env`/`--env-file`, `-v`/`--volume`, `--privileged`, `--cap-add`, `--cidfile`, `--pid`, `--ipc`, a mount of the Docker socket, a tag reference such as `c3po/backend:production` or `:rollback`, a forced removal (`rm -f`, `--force`), `User=`/`Group=`. The repository tests pin the argument list and reject each of these.

### Start preconditions

- `ExecStartPre=-/usr/bin/docker rm c3po-massive` removes a stopped leftover of the fixed name. The leading `-` makes its failure (normally `No such container`) harmless.
- `ExecStartPre=/usr/bin/docker image inspect --format {{.Id}} @IMAGE_ID@` has **no** leading `-`: if the pinned image is not present the start fails at this line, with the status of the image check, before any container is created. On success it prints the image ID, one line, to the journal. The braces are literal for systemd: it expands only `%` specifiers and `$` variables, and neither appears in the template (the repository tests pin that, and the pipeline runs this exact line on a real engine).
- `TimeoutStartSec=60s` is the start timeout. It is **not** 60 seconds for the whole start: systemd is expected to arm it again for each command of the start — each of the two precondition commands, then the launch of the docker CLI — rather than share one budget among them *(unverified)*. See "Process and restart contract" for the consequence.

**Accepted risk for this epoch.** A failure of the image check, and a docker exit of 125, 126 or 127, are ordinary failures for systemd: `Restart=on-failure` restarts them after `RestartSec=1s`, with no supervisor backoff, no claim and no receipt, and each one counts towards the six starts of `StartLimitBurst`. Six such failures spend the day's starts in a few seconds. `RestartSec`, the start limit and `RestartPreventExitStatus` are deliberately left as they were. The mitigations are the retention tag (the image cannot be garbage-collected by a deploy), the readback of operation 4 and the activation gate (image, mounts and init binary are checked before activation), and alerting on the `start-limit` result.

## Image pin and lifecycle

**How `@IMAGE_ID@` is obtained.** On the host, after the deploy of the merged revision, by inspection:

```
docker image inspect --format '{{.Id}}' c3po/backend:production
```

With the containerd image store the ID is the manifest digest of the image as loaded on the host. It will **not** equal an ID computed on the CI runner, so it cannot be taken from the pipeline, from a build log or from another machine. The value is read once, validated against `^sha256:[0-9a-f]{64}$`, and used for the retention tag and for the render.

**A missing image is a failed start.** An ID that does not resolve locally fails the image check in `ExecStartPre`, before `docker run` is reached (and `--pull never` would make `docker run` itself exit 125). That consumes one of the six systemd starts, takes **no claim** and emits no receipt; it is restarted after one second like any other failure (see "Start preconditions" and the exit table).

**Which read binds.** The ID that is rendered and tagged is the one read **after the deploy of the merged revision**. An ID noted in an earlier preflight must not be rendered.

**Retention.** Nothing in the unit keeps the image present. The deploy pipeline, at each deploy, removes the `c3po/backend:rollback` tag, tags the image of the running `api` container as `:rollback`, loads the new image as `:production`, and after a healthy deploy runs `docker image prune --force`, which removes only dangling (untagged) images. For an image referenced only by ID this implies:

- after the first later deploy it is still tagged, as `:rollback`;
- at the second later deploy the `:rollback` tag is removed from it. It then has no tag at all. Whether Docker deletes it at that tag removal or at the following prune was not observed on the host *(unverified)*; in either case it does not survive that deploy unless a container still uses it, and every start of the unit after that fails at the image check.

The explicit retention step is a **dedicated tag**, for example `c3po/backend:massive-supervisor-epoch03`, pointing at the pinned ID:

```
docker image tag <IMAGE_ID> c3po/backend:massive-supervisor-<epoch label>
```

- **Who and when:** the authorised operator, in operation 2 (provisioning), after refusing if that tag already exists (`docker image tag` overwrites silently).
- **Readback:** `docker image inspect --format '{{.Id}}' c3po/backend:massive-supervisor-<epoch label>` equals the `@IMAGE_ID@` value; repeated in operation 4.
- The pipeline never touches that tag: it removes only `:rollback` and prunes only untagged images. The tag is never referenced by the unit; the unit keeps the ID.

**Next deploy.** A deploy or a rollback does not change what the unit runs. The old unit keeps running the old image, by ID, until it is re-rendered. Meanwhile the reader may already run a newer image; nothing in this unit detects that.

**Next epoch, or a deliberate image change.** The sequence is repeated under its own authorisations, but operation 2 is **not** repeated as written, because it refuses existing paths. For a later epoch:

- **created new:** only the new journal leaf (`<data volume>/<new leaf>`, exclusive, `root:root` 0700, empty), the new retention tag, and the catalog of the new root (operation 4b with the new epoch);
- **re-rendered:** the unit, with the new image ID and the new leaf. Because operation 3 never overwrites, the previous timer is first disabled and the previous unit files are removed **under a separate authorisation**; only then is operation 3 run again;
- **kept untouched:** the configuration directory with `manifests` and `docker-cli`, the token, and the claims root `/var/lib/c3po-bar/supervisor`. Claims are never removed; they are named by session date, so old ones do not affect later days.

**The switch happens between session days**: after the close of the last day of the old epoch and before the 09:29 start of the first day of the new one. A claim is named by its session date and binds the SHA-256 of that day's manifest (`r2d2_v2_massive_supervisor.py` lines 78 and 83–93), and the manifest carries the epoch. On a day that already has a claim, a manifest of the new epoch is a changed manifest: refused with `SUPERVISOR_MANIFEST_CHANGED` (lines 85–87), exit 78, and the allowance of that day is not reset.

The old retention tag is removed only after the new unit is active and the old one is gone. The old journal root is not deleted by any step described here.

## Catalog and first-day order

**Why a separate initialisation exists.** The order of the first day is circular without it:

- A release that carries `ebar_amendment_sha` **requires** a minute-bar source. `ShadowCollector.__init__` raises `RELEASE_EBAR_SOURCE_REQUIRED` otherwise (`r2d2_v2_shadow.py` lines 369–371), and `CapacityBoundCollector` inherits that constructor (`r2d2_v2_capacity_bound.py` line 186). So for such a release every invocation of `python -m app.r2d2_v2_shadow_worker`, **including `--prepare-capacity-day`**, runs with Massive bars enabled; the collector is built before the argument is handled. Running it with Massive bars disabled is not an option the activation rite can choose: the code refuses.
- With Massive bars enabled, the worker builds `SessionJournalRoot(journal directory, release.epoch)` **without** `create` (`r2d2_v2_shadow_worker.py` lines 55–70). If the root is missing, empty, not private, owned by another uid or bound to another epoch, it refuses with `MASSIVE_SESSION_ROOT_UNVERIFIED` and exits. It creates nothing and does not retry by itself.
- The producer creates the catalog only at its first run (`r2d2_v2_massive_producer.py` line 315, `SessionJournalRoot(root, epoch, create=True)`; `r2d2_v2_massive_sessions.py` lines 198–205). That run needs the dated manifest, and the manifest needs that day's `prepare-capacity-day`.

Hence the catalog is initialised **before the first `prepare-capacity-day`**, by operation 4b. The recommended moment is right after operation 2, before operation 3 renders the units with that leaf (see "The five operations" for what the other order costs); the signatories decide. The application has no catalog-only entry point: the only caller of `SessionJournalRoot(..., create=True)` in `app/` is the producer. Operation 4b therefore follows the project's pattern for one-off host actions: a hash-pinned script, delivered on standard input to an isolated interpreter, used once, with a receipt.

### Catalog initialisation

**The epoch string.** It is the `epoch` field of the signed release body, the same field the reader verifies (`Release.verify`, `r2d2_v2_shadow.py` line 92, validated at line 95). It is **never typed by hand**: it is extracted by command from the release bytes whose SHA-256 is the release hash of the authorisation, for example

```
epoch="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["epoch"])' <release file>)"
```

and the authorisation carries the resulting string so that the receipt can be compared with it. **A wrong epoch binds the root permanently**: `epoch.json` is written once and never rewritten, the reader refuses the root from then on, and the only recovery is a new directory.

**The command.** Same pinned image ID as the unit, only the journal mount, at the same container path as the unit, no network:

```
sha256sum catalog-init.py
DOCKER_CONFIG=<HOST_CONFIG_DIR>/docker-cli docker run --rm -i --pull never --init --user 0:0 --network none --read-only \
  --cap-drop ALL --security-opt no-new-privileges \
  --mount type=bind,source=<HOST_JOURNAL_ROOT>,target=<CONTAINER_JOURNAL_ROOT> \
  <IMAGE_ID> python -I -B - <CONTAINER_JOURNAL_ROOT> "$epoch" < catalog-init.py
```

- `DOCKER_CONFIG=<HOST_CONFIG_DIR>/docker-cli` gives this docker CLI the same empty configuration directory as the unit's (its `Environment=` line; the directory is created in operation 2), so root's contexts, proxies and credential helpers do not apply to this run either. It is a prefix of this one command, for the docker CLI only: it is not exported and it does not reach the container.
- `-i` only connects standard input, which carries the script; there is no terminal.
- `python -I -B -` reads the program from standard input in isolated mode: no environment variables, no user site directory, and neither the current directory nor a script directory on the import path; `-B` writes no bytecode. The script adds `/app` itself, which is where the image keeps the application.
- No state root, no configuration directory, no token, no manifest and no network are available to this container.
- The first command must print the SHA-256 **written in the 4b authorisation**; the run is not started otherwise.

**The reference script.** `catalog-init.py` is exactly the lines between the two markers, each ended by a newline. Its SHA-256 is `715d7a660e7a2c4dd5c11287063726cc971156dd6fefc2365c431c9aee0f4bb7`. A repository test extracts these lines from this document, checks that hash and executes them against the real module. The hash that binds a run is the one in its authorisation, not the one printed here: this document is the reference the authorisation is expected to copy, and a difference between the two stops the run until it is explained.

<!-- catalog-init-script:begin -->
```python
import json, os, sys
sys.path.insert(0, '/app')
try:
    from app.r2d2_v2_massive_sessions import SessionJournalRoot
    from app.r2d2_v2_store import validate_epoch
    root, epoch = sys.argv[1:]
    validate_epoch(epoch)
    before = sorted(os.listdir(root))
    if before and 'epoch.json' not in before:
        raise ValueError('CATALOG_INIT_ROOT_NOT_EMPTY')
    SessionJournalRoot(root, epoch, create=True)
    SessionJournalRoot(root, epoch)
    with open(os.path.join(root, 'epoch.json'), 'rb') as stream:
        catalog = json.loads(stream.read())
    receipt = {'status': 'CATALOG_READY', 'created': not before, 'epoch': catalog['epoch'],
               'device': catalog['device'], 'inode': catalog['inode'], 'entries': sorted(os.listdir(root))}
except Exception as error:
    code = error.args[0] if len(error.args) == 1 and type(error.args[0]) is str else type(error).__name__
    print(json.dumps({'status': 'CATALOG_REFUSED', 'code': code}, sort_keys=True))
    raise SystemExit(1)
print(json.dumps(receipt, sort_keys=True))
```
<!-- catalog-init-script:end -->

**What it does and refuses.**

- **Empty root:** creates `maintenance.lock` and `epoch.json` (both 0600), then opens the root again the way the reader does (without `create`), and prints one line: `status` `CATALOG_READY`, `created` true, the `epoch`, `device` and `inode` read back from `epoch.json`, and the two entry names. Exit 0.
- **Root already bound to the same epoch:** changes nothing and prints the same line with `created` false. Exit 0. The operation is idempotent. On a root where a reader is polling, such a rerun now waits up to 30 seconds for the catalog lock instead of refusing at once (`_wait_exclusive`, `r2d2_v2_massive_sessions.py` lines 157–171 and 188); it is refused, `MASSIVE_MAINTENANCE_BUSY`, only if the lock stays held for the whole wait, and it has changed nothing then either. The first run is not affected: an empty root has no `maintenance.lock`, so no reader can be holding it.
- **Root bound to another epoch:** refused by the module itself, `MASSIVE_SESSION_MANIFEST_CHANGED` (`_immutable`, `r2d2_v2_massive_sessions.py` line 64: an existing `epoch.json` must equal the bytes that would be written). Nothing is changed. Exit 1.
- **Root that is not empty and has no `epoch.json`:** refused by the script before the module is called, `CATALOG_INIT_ROOT_NOT_EMPTY`, so nothing is created. The script is deliberately stricter than the module here: the module alone would create `maintenance.lock` first, tolerate a root that holds only lock files, and refuse a session directory without a catalog (`MASSIVE_SESSION_EPOCH_MISSING`, line 203) or any other name (`MASSIVE_SESSION_LAYOUT`, line 230).
- **An epoch outside the release grammar:** refused, `EPOCH_INVALID` (`validate_epoch`, the check the release verification applies). This catches a string that is not an epoch; it cannot catch a well-formed epoch of another release, which is why the string is extracted and compared by command.
- A refusal prints one line with `status` `CATALOG_REFUSED` and a `code`, and exits 1. The line holds no secret; this container has none.
- **Known wart: a wrong number of arguments.** Anything but exactly the root and the epoch is refused before the root is touched, exit 1, but the `code` is then Python's own message, for example `not enough values to unpack (expected 2, got 1)`, not a constant: the script prints the single string argument of whatever exception it caught. It is left as it is because the script bytes are pinned. The message names no path and no epoch.
- **A creating run that does not end in `CATALOG_READY`** leaves a root that is not used again; the recovery is a new directory under a new authorisation. The catalog open creates `maintenance.lock` first (`journal_access`, `r2d2_v2_massive_maintenance.py` line 26) and then writes `epoch.json` **in place**, not through a temporary file and a rename (`_immutable`, `r2d2_v2_massive_sessions.py` lines 61–75). A run killed between the two leaves a root holding only the lock, which the script refuses from then on as `CATALOG_INIT_ROOT_NOT_EMPTY`. A run killed during the write can leave an empty or incomplete `epoch.json`, which the script and the reader both refuse at every later open (`MASSIVE_SESSION_FILE_UNSAFE` or `MASSIVE_SESSION_MANIFEST_CHANGED` from the script, `MASSIVE_SESSION_ROOT_UNVERIFIED` from the reader). Neither state is repaired by a second run, and nothing described here deletes inside a journal root. The rule is applied to every other refusal of the creating run as well, including those that touched nothing, so that nobody has to judge on the spot which kind it was.

**Receipt and readback.** The printed line is the receipt. The readback adds: `epoch` of the receipt equal to the extracted string, compared by command; the journal root holding exactly `epoch.json` and `maintenance.lock`, `root:root` 0600; and `stat -c '%d %i' <HOST_JOURNAL_ROOT>` on the host. The device and inode seen in the container are expected to equal the host's for a bind mount; that was not observed *(unverified)*, and a difference is a finding to report, not something to correct.

This run has not been executed in a container anywhere; the repository test executes the script text against the real module on a temporary directory.

### Daily order

The same order applies to the first day and to every later day. The differences are that on the first day the catalog comes from operation 4b and no reader is running yet.

1. **The catalog exists**: the journal root holds `epoch.json` bound to the release epoch (operation 4b before the first day, recommended right after operation 2; already there afterwards).
2. **`prepare-capacity-day`** for that day runs in the V2 shadow worker **with Massive bars enabled — it must be**, for the reason above. It derives and commits the capacity binding; building its collector opens the catalog read-only, which is why step 1 comes first.
3. **That day's manifest** is delivered to `/etc/c3po-bar/manifests/`, **before 09:29 New York time** (see "Daily manifest" for a late one).
4. **09:29 New York time: the producer run.** The timer starts the unit; the producer opens the existing catalog, prepares the session directory and publishes the ready marker before it appends anything.
5. **The reader** (the long-running V2 shadow worker). On the first day it is started **after the producer has marked that day's session ready** — `session_date=<day>/ready.json` exists in the journal root — not merely when `epoch.json` exists. From the second day on it is normally already running: without `--once` its loop ends only on an error (`r2d2_v2_shadow_worker.py` lines 155–168), so the reader of the day before is still polling at 09:29. **Exactly one polling reader runs against a journal root.**

About step 5: the code would let the reader start earlier, as soon as the catalog exists, and with operation 4b that is true before 09:29. On the first day, starting it after the ready marker keeps the first start of the epoch free of any reader. On every later day the producer starts across a polling reader, and so does every restart during a session. That is the case the bounded wait is for (see "Known limits"): the producer waits for the lock, a single reader releases it at every sleep, and offline the writer got in within about one page hold (under a second in these runs) under a deep backlog. None of that was observed on the host. What the wait does not cover is **two or more readers** on the same root: their holds can overlap, the lock may never be free, and each attempt can then end past its wait with a claim spent. Whether the reader is stopped overnight, and how a second reader is ruled out when one is replaced, is a **decision of the activation rite**; this document states the condition and the limit.

If the first attempt of the day ends before the session is prepared (low disk, a token refusal), no ready marker exists and the reader has nothing to read for that day until a later attempt succeeds.

## Reader requirements

The reader of the journal is the process `python -m app.r2d2_v2_shadow_worker`. **No compose service launches that module.** The compose service `r2d2-worker` runs `python -m app.r2d2_worker`, which never opens the Massive journal. The V2 shadow worker is launched by the separately authorised activation rite, through the operator executor, so its container, uid, mounts and environment are set by **that launcher**. Editing the host `.env` or recreating a compose service does not configure the reader.

This unit works only if that launcher gives the reader:

- the **same uid** as the producer, uid 0: every guard compares the owner of the root, catalog, session directories and files with the reader's effective uid;
- the journal root at the **same container path** as `@CONTAINER_JOURNAL_ROOT@`, on the same filesystem (the catalog binds device and inode); mounting the data volume at `/app/day-d-data` satisfies this;
- **read access** to the root. The reader writes nothing in the journal tree; it opens the existing `maintenance.lock` read-only for a shared lock. A read-only mount is expected to be sufficient but was not exercised *(unverified)*;
- `C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR` equal to `@CONTAINER_JOURNAL_ROOT@`, **explicitly**. The default is `/app/data/r2d2-v2-massive`; a launcher that omits the variable makes the reader refuse with `MASSIVE_SESSION_ROOT_UNVERIFIED`;
- `C3PO_R2D2_V2_MASSIVE_BARS_ENABLED` enabled for every invocation of an EBAR release, including `--prepare-capacity-day` (see "Daily order").

The launcher's contract must name these values and prove them in its own readback. Nothing in this directory does.

## Process and restart contract

The timer requests one start at 09:29 New York time, Monday through Friday, and another 30 seconds after boot. The boot trigger recovers a host that was down at the calendar trigger. The wrapper checks the XNYS calendar (holidays and shortened sessions) and permits starts only from open minus 60 seconds until close. A start outside that window produces a safe terminal refusal, with no token load or provider connection. Missed calendar timers are not replayed (`Persistent=false`). The producer receives through close plus 91 seconds; no new connection starts after close. A late failure that cannot restart remains an explicit coverage gap.

The wrapper allows one initial attempt and **four retries**, with monotonic waits of **30, 60, 120 and 240 seconds** before retries 1–4. systemd requests restart on failure with a one-second floor, additional to the wrapper wait. With immediate connection failures, provider attempts occur approximately at 0, 31, 92, 213 and 454 seconds, plus the container start of each attempt (estimated 1–3 seconds, unmeasured). Those figures assume that no attempt waits for the catalog lock. Each attempt can be delayed by up to 90 seconds before its connection (three lock waits of at most 30 seconds each, see "Known limits"); if every attempt is delayed that much, the connections come at about 90, 211, 362, 573 and 904 seconds, so the fifth attempt can reach the provider about fifteen minutes after 09:29 instead of seven and a half. The 09:29 start leaves 60 seconds before the open: lock waits that total more than about 55 seconds on the first attempt (60 less the container start and the connection handshake, neither measured) put the authenticated connection after 09:30:00, and the 09:30 minute is then a gap: a bar counts only for a minute that began at or after the connection (`connected_at <= minute`, `r2d2_v2_minute_bars.py` line 140; a bar that arrives for an earlier minute is recorded as `MINUTE_CONNECTION_GAP`). A single wait that **expires** on the first attempt has the same effect on its own: that attempt ends without a connection, and the 30 seconds of the expired wait, the 1 second of `RestartSec` and the 30-second backoff of the second attempt add up to 61 seconds, more than the 60 the start had, before the second attempt has read the token or begun its own lock waits. This is bounded recovery, not an assurance of provider availability. Successful STOPPED/SESSION_LIMIT exits are not restarted. Exit 78 is a terminal refusal and suppresses restart.

Exclusive, fsynced per-session claims cap provider attempts at **five across process crashes, reboots and manual restarts**, regardless of `reset-failed`. Claims must not be deleted to replenish allowance. Waiting holds the supervisor lock, checks stop/window each second and reads no token until the delay finishes. A crash or interruption during the wait conservatively consumes that claim. (That is the backoff wait. The producer's waits for the catalog lock come later in the attempt and check neither; see "Stop".) Changing the dated manifest never resets allowance. systemd additionally caps six process starts in eight hours: five attempts plus one process that can emit the final exhausted-budget refusal.

Exit statuses seen by systemd:

| Status | Origin | Effect |
| --- | --- | --- |
| 0 | supervisor: STOPPED / SESSION_LIMIT | success, no restart |
| 1 | supervisor: attempt failed | restart; the next process claims the next attempt |
| 78 | supervisor: terminal refusal | no restart for that start |
| status of `ExecStartPre` | image check: pinned image absent, or daemon unreachable | start fails before `docker run`; restart; consumes systemd starts, **never claims**, emits **no** receipt |
| 125, 126, 127 | docker: missing mount source, daemon unavailable, name conflict, command not runnable; a missing init binary is expected to land here too *(status not established)* | restart; consumes systemd starts, **never claims**, emits **no** receipt |
| 137 | container killed | restart; the interrupted attempt stays consumed |
| 143 | supervisor terminated by SIGTERM before its handler existed (see "Stop") | failure; no claim exists yet |

The image-check and 125–143 failures bypass the 30/60/120/240 backoff: six starts can be spent in seconds with no `DATA_GAP` line (the accepted risk under "Start preconditions"). `--rm` can also surface a clean 78 as 125 if waiting for the removal fails; that direction is fail-safe for coverage claims but costs a start. Alert on the unit results `start-limit` **and** `dependency`: with `Requires=docker.service`, a Docker service that fails its start leaves this unit with a `dependency` result, no restart and no receipt.

Each of the two `ExecStartPre` commands runs under `TimeoutStartSec=60s`, and the timeout is expected to be armed again for each command *(unverified)*. With a slow or hung Docker daemon the start phase can therefore take up to about 120 seconds, not 60 *(unverified)*, before it ends as a failure with no receipt; it consumes one of the six starts. `ExecStopPost` is expected to follow a failed start as well (`ExecStop` is not), under its own timeout, `TimeoutStopSec=30s`, rather than under what is left of the start timeout *(unverified)*.

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

A low-disk refusal (see "Known limits") leaves **only `producer.lock`** in an otherwise empty journal root: the producer creates that lock before it measures free space. That is a valid state for the producer and for operation 4b's code path, but the reader still refuses the root (no catalog), and operation 4b's script refuses it as not empty; this cannot arise in the documented order, where 4b precedes every producer start.

The state root nested in the journal root is refused by the producer (`MASSIVE_SERVICE_STORAGE_UNVERIFIED`, exit 1). A foreign entry in the journal root makes every reader poll refuse. The journal root with any group/other bit, or owned by another uid, is refused by producer and reader alike. Only the journal root itself is checked for privacy; its ancestors are checked only for symbolic links.

## Daily manifest

The manifest has exactly the keys `epoch`, `session`, `symbols`, `owner_uid`. `owner_uid` is the JSON integer `0`. `epoch` equals the signed release epoch. There is **one manifest per session date**, and it can only be written after that day's `prepare-capacity-day`, because the symbols are that day's committed capacity binding. It must be in place before 09:29 New York time. A missing manifest inside the window is a terminal 78 for that start, with no claim. Once the first claim binds the manifest's SHA-256 its bytes are frozen for the day; a change is refused and never resets allowance.

**Late manifest.** If the manifest is not in place at 09:29, that start ends in 78 (`SUPERVISOR_FILE_UNAVAILABLE`) with no claim, and `RestartPreventExitStatus=78` means **nothing retries it**: the timer does not fire again that day. The recovery is a manual `systemctl start c3po-massive.service`, **inside the session window, after the manifest is in place, under its own authorisation** (operation 5 covers the timer only). Cost: the refused 09:29 start took no claim, so the manual start takes claim 1 and all five attempts remain; it has used one of the six systemd starts, so the sixth process, the one that would print `SUPERVISOR_ATTEMPTS_EXHAUSTED`, may instead end as `start-limit` unless `reset-failed` is run first. The minutes between the open and the manual start are a coverage gap that nothing backfills. The same recovery applies to a 78 caused by a bad token, except that the token refusal has already consumed claim 1, so four attempts remain.

## Stop

`systemctl stop` runs `docker stop -t 25`: SIGTERM to the supervisor, which closes the socket and exits 0 after its storage scans. `TimeoutStopSec=30s` applies to each stop command separately; with a hung Docker daemon the worst case is about three such periods (around 90 seconds). Do not promise 30 seconds in total.

With `--init`, PID 1 in the container is `docker-init`, which forwards SIGTERM to the supervisor. The supervisor installs its handler in `main()`, after the interpreter has started and the modules are imported. A stop that arrives before that reaches a Python process with the default disposition, which terminates at once: the container is expected to exit 143 without waiting the 25 seconds, and the unit ends failed, not stopped. No claim exists yet at that point. Without `--init` Python would be PID 1, the kernel would ignore that early SIGTERM, and the stop would wait the full 25 seconds and end in a kill (137). All of this paragraph is documented behaviour of Docker, tini and the kernel; **none of it was observed**, and the rehearsal's stop case is what proves it.

**Exception: a stop during a lock wait.** The producer's three waits for the catalog lock (see "Known limits") do not look at the stop request. The next check is the one just before the connection is opened (`run_connection`, `r2d2_v2_massive_transport.py` line 95), after all three. A stop that arrives while the producer is waiting therefore ends in one of three ways, and only the first is the clean one:

- the lock is obtained and the preparation finishes inside the 25 seconds: `STOPPED`, exit 0, no connection;
- a wait expires inside the 25 seconds: the attempt fails with `MASSIVE_MAINTENANCE_BUSY` and the exit is **1, not 0**;
- the lock stays held and more than 25 seconds of waiting remain (one wait lasts up to 30 seconds, and the three follow each other): Docker kills the container, **137**.

In all three the claim of that attempt is already spent: it is taken before the backoff, and the waits come after it. The first two outcomes were reproduced offline, in process; the third is `docker stop -t 25` doing what it documents and was not observed. After exit 1 or 137 the unit is expected to end failed, not stopped *(unverified)*. "Exit 0 in under 25 seconds" therefore holds only when nothing holds the catalog lock across the stop.

A forced kill consumes the attempt (137) and the next recovery treats it as a gap. It may also leave a hot `sequence.sqlite3-journal` in the session directory, which the read-only reader cannot roll back and therefore refuses; recovery is an authorised read-write open as uid 0 with the same image, never a deletion.

## Receipts and retention

The supervisor prints one JSON line per notice on standard output. The unit sends the docker CLI's output to **journald** (`SyslogIdentifier=c3po-massive`); that is the only retained copy, kept for as long as the host's journald retention keeps it. Docker's own log driver holds a second copy of the container output under its data directory until `--rm` removes the container at exit. Neither copy holds a secret. This candidate configures no export, no alert destination and no retention policy.

Terminal refusal receipts retain `reason=SUPERVISOR_REFUSED` and add a safe `code`: `SUPERVISOR_WINDOW`, `SUPERVISOR_SESSION`, `SUPERVISOR_ATTEMPTS_EXHAUSTED`, `SUPERVISOR_MANIFEST`, `SUPERVISOR_MANIFEST_CHANGED`, `SUPERVISOR_CLAIM_INVALID`, `SUPERVISOR_PRIVATE_FILE`, `SUPERVISOR_FILE_CHANGED`, `SUPERVISOR_TOKEN`, `SUPERVISOR_MONOTONIC`, `SUPERVISOR_FILE_UNAVAILABLE`, or a constant code already defined in the reviewed producer modules. All other errors become `SUPERVISOR_UNVERIFIED`; raw exception text, paths and credentials are never copied into notices. BACKOFF receipts record attempt number and wait seconds.

## Operations

- Operate only through `systemctl`. The effect on the unit of an out-of-band `docker stop` or `docker restart` of `c3po-massive` was not established *(unverified)*; do not use them.
- The journal stream is not pure JSON. The image check prints the image ID at every start, Docker prints the container name on stop, and `No such container` from `ExecStartPre` and from the stop commands once the container is gone (once after a failed exit, twice after a clean one). Parsers must match the JSON status fields, not assume every line parses.
- Do not infer clean coverage from exit 0 or a healthy unit state. Route `DATA_GAP`, `FAILED`, `start-limit` and `dependency` to the approved alert destination; none is configured by this candidate.
- If the docker CLI is killed while the container lives, the next start fails on the name (125) until the stop commands and the asynchronous removal finish: two or three starts. A container stuck in a dead or removal-in-progress state defeats the non-forced `docker rm`; an operator removes it manually after confirming it is not running, then runs `systemctl reset-failed c3po-massive.service`. The unit never forces a removal.
- `OnBootSec=30s` fires immediately when the timer is activated more than 30 seconds after boot. Activation is therefore done outside the session window and followed by `systemctl reset-failed c3po-massive.service`; see operation 5 for what the immediate start does inside and outside the window.
- An explicit `systemctl restart docker` stops and restarts this unit through `Requires=`: outside the window that is a 78 and a consumed start, inside it a new claim and a short gap. Hold Docker package upgrades and avoid Docker restarts during sessions; a daemon crash is unproven.
- Schedule host reboots outside 09:29–16:02 New York time.
- **The automatic security reboot waits while the supervisor container runs.** `scripts/c3po_security_reboot.py`, `admission_coverage` (lines 187–204), lists every running container with `docker ps -q` and returns false for any container whose `com.docker.compose.service` label is not one of the services it knows. The `c3po-massive` container is started by `docker run` and has no such label, so while it runs the controller answers `waiting_admission_coverage` (lines 153–154) and does not request the reboot. Because of `--rm` the container exists only while the unit runs, that is, during session hours; outside them it does not hold a reboot back. The same holds for any other container started outside compose, including the V2 shadow worker of the activation rite and the short-lived container of operation 4b. A pending security reboot therefore cannot complete during a session; check the security report at each readback and let the reboot happen outside the window. This is read from the code; it was not observed on the host.
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

- **Free-space floor.** The producer requires 50 GiB free (`MIN_SESSION_FREE_BYTES`, 53687091200 bytes), measured with `fstatvfs` on the journal root's filesystem, which is the data volume. Below it the attempt ends with exit **1**, not 78 (`MASSIVE_SERVICE_LOW_DISK`), before any provider connection. Exit 1 restarts, and the floor is checked again at **every** attempt (`r2d2_v2_massive_producer.py` lines 304–311), so all five attempts of the day are burnt. A session may itself write up to 512 MiB of evidence (`MAX_SESSION_EVIDENCE_BYTES`) plus 64 MiB of index (`MAX_SESSION_INDEX_BYTES`): **576 MiB (603979776 bytes) per session**. A volume that starts a day barely above the floor can therefore fall below it during that day (attempts 2–5 after a crash) and start the next day below it. The data volume had about 50.4 GiB free on 2026-10-01: that margin is smaller than one session's own budget. The activation gate carries the required number.
- **Lock contention at start.** The producer takes the catalog lock with `LOCK_EX|LOCK_NB` three times at each start: at the catalog open, at the session preparation and at the ready marker (`r2d2_v2_massive_sessions.py` lines 198, 292 and 332). Each of the three **waits a bounded time** for the lock: up to 30 seconds, retrying every 10 ms (`CATALOG_LOCK_WAIT_SECONDS` for the first two, `READY_LOCK_WAIT_SECONDS` for the marker), so one start can be delayed by up to 90 seconds; "Process and restart contract" has the effect on the five attempts and on the 09:30 minute. Only `MASSIVE_MAINTENANCE_BUSY` is retried; every other refusal is immediate.
  - **The reader's side.** The reader takes the shared lock for each page it reads (`prepare_events`, `r2d2_v2_massive_session_source.py` line 34) and releases it when the page is returned. One cycle starts further pages only during its first 0.5 seconds (`MAX_DRAIN_SECONDS`, `r2d2_v2_shadow.py` lines 433–435), and then the worker sleeps `C3PO_R2D2_V2_SHADOW_POLL_SECONDS` (default 1.0 second, allowed 0.25 to 5.0) with the lock free (`r2d2_v2_shadow_worker.py` line 168). How long one read holds the lock was not measured on the host. Offline, on development machines: under one second for a full 4096-event page and about 10 ms or less caught up, both growing with the number of retained ready sessions (with 21 sessions: a full page about 0.7 seconds; caught up, about 30 ms).
  - **One reader.** A single polling reader delays the start instead of failing it: the lock is free at every sleep of the reader and the producer retries every 10 ms. Offline, against one simulated reader (the page read and the sleep, without the database) on a deep backlog, the writer got in within about one page hold (under a second in these runs), at the minimum and at the default interval. From the second day on this is the normal start, because the reader of the day before is still polling at 09:29 (see "Daily order").
  - **Exactly one polling reader may run against a journal root.** Nothing in the code counts readers. With two or more, the shared holds can overlap so that the lock is never free, and the producer can be kept out past the 30 seconds at every attempt. Offline, two such readers at the minimum interval kept the writer out for 15.8 seconds in one of three tries; nothing bounds that below the wait.
  - **When a wait expires.** If the lock stays held for the whole 30 seconds of one wait, the attempt still ends with exit 1 and `MASSIVE_MAINTENANCE_BUSY`, with no provider connection, and **consumes a claim**. The next attempt comes after the supervisor backoff (30, 60, 120 or 240 seconds, by attempt number) plus `RestartSec` and the container start, not after a fixed 30 seconds.
  - **Silence.** Nothing is logged while the producer waits. `RETAINED_BUDGET_START` followed by up to 30 seconds of silence is a lock wait (the catalog open, then the same again for the session preparation); the next line is `BUDGET_START` if the lock was obtained, or `RETAINED_BUDGET_END` and `FAILED` if a wait expired. The wait at the ready marker comes after `BUDGET_START`, where a healthy session is silent too.
  - **Stop.** The waits do not observe a stop request; "Stop" lists the outcomes.
  - **The reverse is unchanged:** a reader that starts while the producer holds the exclusive lock refuses at once with `MASSIVE_SESSION_ROOT_UNVERIFIED` and exits.
  - **A reader that is already polling does not exit.** A read that lands inside one of the producer's exclusive holds returns no events, the single diagnostic `RAW_APPEND_IN_PROGRESS` and the cursor it was given (`prepare_events`, `r2d2_v2_massive_session_source.py` lines 32–40; the composite source passes the diagnostic on with no events and the same cursor, `r2d2_v2_composite_source.py` lines 89–91, and lines 123–124 for its shortened second read). The collector treats that code as transient (`_cycle_with_cursor`, `r2d2_v2_shadow.py` lines 491–509): when every diagnostic of the read is transient it journals `RAW_POLL_DEFERRED` with the number of consecutive deferrals and their codes, applies no event and leaves the cursor where it was, so the same position is read again at the next poll; the rest of the cycle still runs. At the **third consecutive** deferral, and at each one after it, the cycle also carries the source gap `RAW_POLL_PERSISTENT_FAILURE`, with no instrument (lines 505–506). The first read that is not deferred journals `RAW_POLL_RECOVERED` and clears the count (lines 510–512). The refusal `MASSIVE_SESSION_NOT_READY` maps to the same diagnostic (`r2d2_v2_massive_session_source.py` lines 37–38), so the count does not tell the two apart. How long the producer's three exclusive holds last was not measured.
  - **Operational rule (a decision of the activation rite, not enforced by any code):** one polling reader per journal root, never two. On the first day it is started only after the session is marked ready (see "Daily order"). A reader that is replaced is stopped, and seen to have exited, before its successor is started. Nothing above requires a single reader to be paused around a producer start or restart; pausing it anyway remains the rite's choice.
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
4. Free space on the journal root's filesystem (`df -B1 --output=avail <data volume>`) is at least **53687091200 bytes (the 50 GiB floor) plus 603979776 bytes (576 MiB) for each session that will be retained before space is next freed, plus the expected growth of every other writer on the data volume over the same period**. For five sessions and no other growth that is 56706990080 bytes. Below the floor every attempt of the day is spent. Exactly at the floor the code passes: it refuses only when the free bytes are strictly below `MIN_SESSION_FREE_BYTES` (`r2d2_v2_massive_producer.py` lines 103 and 307); the gate asks for more than the floor all the same. The authorisation states the number of sessions and the allowance for other writers; a reading below the resulting number is a refusal, and freeing space is a separate authorised action.
5. The image ID resolves locally and the retention tag points at it.
6. Token metadata: uid 0, gid 0, mode exactly 0600, one link, and "size within 1–4096" true (the size is not recorded); parent directory 0700. An absent token fails the readback.
7. The timer is `disabled` and inactive.
8. The init binary required by `--init`: `docker info --format '{{.InitBinary}}'` names it and the `docker-init` executable exists on the host (path, owner and mode recorded). Which path the daemon resolves was not established *(unverified)*; rehearsal item 5 is the proof that a container actually starts with it.

**Catalog (from operation 4b):** the receipt of the catalog initialisation is on record, the journal root holds exactly `epoch.json` and `maintenance.lock`, and the epoch of the receipt equals the `epoch` field of the signed release.

**Rehearsal**, separately authorised, of the rendered unit against a throwaway journal root, state root, configuration directory and unit name:

1. `systemctl stop` ends the main process with exit 0 in under 25 seconds, `STOPPED` in the journal, no leftover container. This needs a session-day window and a manifest (outside the window the supervisor exits 78 at once and there is nothing to stop), and it reuses the fixed container name, so it cannot overlap an active production unit. It is run with no reader on the throwaway root: a stop that lands in a wait for the catalog lock can end in exit 1 or in 137 instead (see "Stop"), and that case is not part of this item.
2. A TLS connection to `socket.massive.com:443` succeeds from `@NETWORK@`, without a token.
3. `systemd-analyze verify` passes on the installed systemd version.
4. `docker info` shows neither user-namespace remapping nor rootless mode.
5. The pipeline smoke command returns 78 on the host with the pinned `sha256:` ID.
6. A second container sees the same device and inode for the throwaway root, and a lock held in one container is visible in the other.

## Offline verification and pending checks

Repository tests pin the unit text and its argument list, reject the forbidden options, check that the template holds none of the characters that would make a textual render differ from systemd's own parsing, render the template with sample values and check the paths against the backend data mount, and run the real supervisor, producer and reader code on a temporary tree with the container layout: writer and reader agree on uid and path, the reader leaves the tree untouched, the producer creates the catalog on an empty root, the reader refuses an empty root, the catalog-initialisation script of this document (extracted from it, with its SHA-256 checked) creates the catalog, is idempotent, refuses another epoch and a non-empty root, and is then accepted by the reader path, and a different owner, a non-private root, a foreign entry, a nested state root, a foreign manifest owner and an exposed token directory are all refused. They also pin that this document names the operations in order and the substitution grammar. A separate file runs the real catalog, SQLite and lock code for four guard cases (owner mismatch, private root and index, wrong path, read-only reader under shared locks). Another runs real lock contention for the bounded wait: a reader's hold released in time, a hold that outlasts the wait, every other refusal raised at once, and a supervised start across a reader; it pins the 30-second bound against the first retry delay and the worst-case figures of this document against the constants. No test of that file can hang on a wait that never ends: the patched sleep fails past five seconds, the fake clock fails past 64 reads or attempts, and an alarm fails any test still running after 20 seconds.

The pipeline renders the mandatory `ExecStartPre` and `ExecStart` from this template and runs them against the validation image on the runner's Docker with three root-owned 0700 binds, the image by ID and no network. The image check must print the pinned ID and must fail for an ID that does not exist. The run requires exit 78, exactly one `DATA_GAP` line, no claim, no journal object and no leftover container. That proves the option set including `--init` and `--restart no`, mount-target creation under a read-only root filesystem, imports under the capability/pid/tmpfs limits, the ID reference with `--pull never`, and propagation of 78 through `docker-init` and `--rm`. It runs on pull requests and remediation dispatches only, not on the build that produces the deployed image.

Not proven anywhere yet: systemd's own parsing of the unit (including the braces of the image check), stop and SIGTERM through `docker-init`, the catalog initialisation in a container, the token recipe on the host, egress, DNS and CA trust from `@NETWORK@`, ID resolution under the host's image store, deletion or survival of an untagged image across deploys, behaviour of an empty `DOCKER_CONFIG` directory on the host, the reader on a read-only mount, the producer's start across the real polling reader and how long that reader holds the lock, a stop during a lock wait, the stop bound with many retained sessions, alert delivery, and real provider behaviour. These stay pending until the rehearsal above is separately authorized.
