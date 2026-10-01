# Massive producer supervision — installation candidate

Offline candidate. Nothing here has been installed, enabled, started, connected to Massive, or approved for live operation. The Docker and systemd behaviour described below comes from documentation and offline tests; none of it has been observed on the production host. The single engine check is the pipeline smoke described under "Offline verification".

## Contract

The supervisor runs **inside a container of the deployed backend image**, started in the foreground by a systemd unit, as **uid 0** — the same effective uid as the reader (the backend services run as root because neither the image nor compose selects another user). There is no dedicated `c3po-bar` account, no host virtualenv and no source tree under `/opt`. The journal root lives inside the existing data volume, so the producer and the reader see the same directory through the same container path:

```
host      <C3PO_DAY_D_DATA_MOUNT_SOURCE>/<leaf>      (for example /mnt/day-d-data/r2d2-v2-massive-epoch03)
container /app/day-d-data/<leaf>                     (producer --journal-root and reader C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR)
```

No owner or mode guard is relaxed. Nothing existing is chowned or chmodded, and no journal is copied, moved or recreated: the catalog binds the device and inode of its root.

## Template placeholders

`c3po-massive.service` is a template. The installer performs exactly six textual substitutions and must refuse if any `@…@` survives. `c3po-massive.timer` has no placeholder.

| Placeholder | Meaning | Example |
| --- | --- | --- |
| `@IMAGE_ID@` | Image ID of the deployed backend image, `sha256:` plus 64 hex. Never a tag. | `sha256:0123…cdef` |
| `@HOST_JOURNAL_ROOT@` | Host path of the dedicated journal root, inside the data volume. | `/mnt/day-d-data/r2d2-v2-massive-epoch03` |
| `@CONTAINER_JOURNAL_ROOT@` | The same directory as seen by producer and reader. Two occurrences. | `/app/day-d-data/r2d2-v2-massive-epoch03` |
| `@HOST_STATE_ROOT@` | Host path of the attempt/claim journal. | `/var/lib/c3po-bar/supervisor` |
| `@HOST_CONFIG_DIR@` | Host configuration directory. Three occurrences: `RequiresMountsFor`, `DOCKER_CONFIG`, the read-only mount. | `/etc/c3po-bar` |
| `@NETWORK@` | Docker network of the container, chosen from the host rehearsal. | `bridge` |

Why each option is there:

- `--pull never` and the image **ID**: the unit can never fetch or follow a moving tag. A deploy or rollback does not change what runs. The ID must be anchored by a retention tag (below) or pruning deletes it.
- `--rm` and the fixed `--name c3po-massive`: one container at most, removed on exit; a leftover name makes the next start fail instead of running twice.
- `--user 0:0`: equal to the reader's uid; every guard compares against the effective uid.
- `--read-only` with `--tmpfs /tmp` (256 MiB, `noexec,nosuid,nodev`): the only writable paths are the two read-write binds.
- `--cap-drop ALL`, `--security-opt no-new-privileges`, `--pids-limit 512`: root in the container owns its files and needs no capability to read or write them.
- No `--init`: Python is PID 1 and installs its own SIGTERM handler, so `docker stop` reaches the orderly shutdown directly.
- No environment at all (`-e`, `--env-file`, `TZ`, `C3PO_*`): the container receives only the image defaults. The token is a file.
- Three `--mount type=bind` entries, never `-v`: `--mount` refuses a missing source instead of creating a root-owned directory.
- `--stop-timeout 25` and `docker stop -t 25`, below `TimeoutStopSec=30s`.
- `Environment=DOCKER_CONFIG=@HOST_CONFIG_DIR@/docker-cli` applies to the docker CLI only: an empty root-owned directory, so root's contexts, proxies and credential helpers cannot leak in. `DOCKER_HOST` is not set (default socket).

Never add: `--init`, `--restart`, `-d`, `-t`, `-i`, `-e`/`--env`/`--env-file`, `-v`/`--volume`, `--privileged`, `--cap-add`, `--cidfile`, `--pid`, `--ipc`, a mount of the Docker socket, a tag reference such as `c3po/backend:production` or `:rollback`, a forced removal (`rm -f`, `--force`), `User=`/`Group=`. The repository tests pin the argument list and reject each of these.

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

## Filesystem layout

All objects are `root:root`. New directories are created exclusively (refuse if they exist).

| Path | Mode | Role |
| --- | --- | --- |
| `<data volume>` (`C3PO_DAY_D_DATA_MOUNT_SOURCE`) | existing, **not modified** | Already mounted at `/app/day-d-data` in the backend services. |
| `<data volume>/<leaf>` = `@HOST_JOURNAL_ROOT@` | **0700**, new and empty | Dedicated journal root of one epoch. Holds only `epoch.json`, `maintenance.lock`, `producer.lock`, `session_date=YYYY-MM-DD/`. Never a filesystem root; nothing else may be placed inside it. |
| `/var/lib/c3po-bar` | **0700** | Private parent, outside every compose mount. |
| `/var/lib/c3po-bar/supervisor` = `@HOST_STATE_ROOT@` | **0700**, contents 0600 | Claims and `producer.lock`. Outside the journal root and outside the data volume. |
| `/etc/c3po-bar` = `@HOST_CONFIG_DIR@` | **0700** | Mounted read-only **as a directory** in the supervisor container only. |
| `/etc/c3po-bar/docker-cli` | **0700**, empty, stays empty | `DOCKER_CONFIG` of the unit's docker CLI. |
| `/etc/c3po-bar/manifests` | **0700** | Dated manifest directory. |
| `/etc/c3po-bar/manifests/YYYY-MM-DD.json` | exactly **0600**, regular, single link, at most 65536 bytes | One manifest per session date. |
| `/etc/c3po-bar/token` | exactly **0600**, regular, single link, 1–4096 bytes, one line | Provider token. Never in the environment, the unit, arguments, logs or receipts; never under the data volume. |

The state root nested in the journal root is refused by the producer (`MASSIVE_SERVICE_STORAGE_UNVERIFIED`, exit 1). A foreign entry in the journal root makes every reader poll refuse. The journal root with any group/other bit, or owned by another uid, is refused by producer and reader alike.

## Daily manifest

The manifest has exactly the keys `epoch`, `session`, `symbols`, `owner_uid`. `owner_uid` is the JSON integer `0`. `epoch` equals the signed release epoch. There is **one manifest per session date**, and it can only be written after that day's `prepare-capacity-day`, because the symbols are that day's committed capacity binding. It must be in place before 09:29 New York time. A missing manifest inside the window is a terminal 78 for that start, with no claim. Once the first claim binds the manifest's SHA-256 its bytes are frozen for the day; a change is refused and never resets allowance.

## Order for the first day

1. Create the journal root, state root and configuration directories (new, empty, `root:root` 0700).
2. **Catalog pre-init**: one authorised, receipted run of the same image ID as uid 0 with only the journal mount and no network, creating the catalog (`SessionJournalRoot(root, epoch, create=True)`). The epoch string is read from the signed release, never typed: a wrong epoch binds the root permanently and the only recovery is a new directory. Afterwards the root holds exactly `epoch.json` and `maintenance.lock`, both 0600. The step is idempotent with the producer.
3. Set the reader keys in the host `.env` (`C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR` equal to the container journal root, and the enable flag per the activation plan) and recreate the reader. A reader started on an empty 0700 root refuses with `MASSIVE_SESSION_ROOT_UNVERIFIED`, which is why step 2 comes first.
4. `prepare-capacity-day`, then that day's manifest.
5. 09:29 New York time: the timer starts the unit.

Verify the token metadata (uid 0, gid 0, exactly 0600, single link, single line, parent 0700) at readback before activation. The supervisor checks the token only **after** the first claim and backoff, so a misprovisioned token or a configuration directory with group/other bits costs one attempt and ends in a terminal 78.

## Stop

`systemctl stop` runs `docker stop -t 25`: SIGTERM to the supervisor, which closes the socket and exits 0 after its storage scans. `TimeoutStopSec=30s` applies to each stop command separately; with a hung Docker daemon the worst case is about three such periods (around 90 seconds). Do not promise 30 seconds in total. A forced kill consumes the attempt (137) and the next recovery treats it as a gap. It may also leave a hot `sequence.sqlite3-journal` in the session directory, which the read-only reader cannot roll back and therefore refuses; recovery is an authorised read-write open as uid 0 with the same image, never a deletion.

## Operations

- Operate only through `systemctl`. An out-of-band `docker stop` or `docker restart` of `c3po-massive` ends the unit as a success with no restart.
- The journal stream is not pure JSON. Docker prints the container name on stop, and `No such container` from `ExecStartPre` and from the stop commands once the container is gone (once after a failed exit, twice after a clean one). Parsers must match the JSON status fields, not assume every line parses.
- Do not infer clean coverage from exit 0 or a healthy unit state. Route `DATA_GAP`, `FAILED`, `start-limit` and `dependency` to the approved alert destination; none is configured by this candidate.
- If the docker CLI is killed while the container lives, the next start fails on the name (125) until the stop commands and the asynchronous removal finish: two or three starts. A container stuck in a dead or removal-in-progress state defeats the non-forced `docker rm`; an operator removes it manually after confirming it is not running, then runs `systemctl reset-failed c3po-massive.service`. The unit never forces a removal.
- `OnBootSec=30s` fires immediately when the timer is activated more than 30 seconds after boot. That start ends in 78 outside the window, leaves the unit failed and uses one of the six starts if it happens within eight hours of 09:29. Activate earlier, or run `systemctl reset-failed c3po-massive.service` after activation.
- An explicit `systemctl restart docker` stops and restarts this unit through `Requires=`: outside the window that is a 78 and a consumed start, inside it a new claim and a short gap. Hold Docker package upgrades and avoid Docker restarts during sessions; a daemon crash is unproven.
- A retention tag pointing at `@IMAGE_ID@` must exist before the next deploy; otherwise the image is deleted two deploys later. The unit still references the ID.
- Do not add a compose service, a restart policy or a second loop or timer for the producer.

Terminal refusal receipts retain `reason=SUPERVISOR_REFUSED` and add a safe `code`: `SUPERVISOR_WINDOW`, `SUPERVISOR_SESSION`, `SUPERVISOR_ATTEMPTS_EXHAUSTED`, `SUPERVISOR_MANIFEST`, `SUPERVISOR_MANIFEST_CHANGED`, `SUPERVISOR_CLAIM_INVALID`, `SUPERVISOR_PRIVATE_FILE`, `SUPERVISOR_FILE_CHANGED`, `SUPERVISOR_TOKEN`, `SUPERVISOR_MONOTONIC`, `SUPERVISOR_FILE_UNAVAILABLE`, or a constant code already defined in the reviewed producer modules. All other errors become `SUPERVISOR_UNVERIFIED`; raw exception text, paths and credentials are never copied into notices. BACKOFF receipts record attempt number and wait seconds.

## Limits

- With uid 0 on both sides, the owner guards no longer distinguish the producer from the other root containers that mount the whole data volume read-write (api, r2d2-worker, shadow-candidate). They prove "root wrote this", not "the producer wrote this". The token and the claims stay outside the data volume for that reason.
- The 50 GiB free-space floor is measured on the data volume and is exit 1, not 78: below it every attempt of the day is spent.
- The producer takes the catalog lock without waiting while the reader holds a shared lock for each poll. Contention is `MASSIVE_MAINTENANCE_BUSY` and costs one claim. This predates the container layout.
- The security reboot controller sees the running supervisor container as unknown workload. Schedule reboots outside 09:29–16:02 New York time.
- A change of the data disk's device number across a reboot makes both sides refuse the root; there is no in-code recovery.
- Cooperative local locks do not prove provider-account exclusivity on other hosts; that remains the owner's responsibility.

## Clock behavior

Authentication/liveness/runtime deadlines use monotonic time. The producer injects that clock into minute scheduling and anchors the daily end deadline to elapsed time at startup. A 5 ms UTC rollback neither crashes the scheduler nor extends the session runtime. A minute expires only after both its monotonic elapsed deadline and market UTC deadline have passed. Provider timestamps and actual received/available timestamps are never rewritten. Larger UTC corrections can delay evidence; no fabricated timestamp or completeness assertion compensates for that.

## Activation gate

Installing the units is not activation. Before the timer is enabled, one rehearsal of the rendered unit against a throwaway journal root, state root, configuration directory and unit name must show:

1. `systemctl stop` ends the main process with exit 0 in under 25 seconds, `STOPPED` in the journal, no leftover container.
2. A TLS connection to `socket.massive.com:443` succeeds from `@NETWORK@`, without a token.
3. `systemd-analyze verify` passes on the installed systemd version.
4. `docker info` shows neither user-namespace remapping nor rootless mode.
5. The pipeline smoke command returns 78 on the host with the pinned `sha256:` ID.
6. A second container sees the same device and inode for the throwaway root, and a lock held in one container is visible in the other.

## Offline verification and pending checks

Repository tests pin the unit text and its argument list, reject the forbidden options, render the template with sample values and check the paths against the compose data mount, and run the real supervisor, producer and reader on a temporary tree with the container layout: writer and reader agree on uid and path, the reader leaves the tree untouched, a different owner, a non-private root, a foreign entry, a nested state root, a foreign manifest owner and an exposed token directory are all refused, and the catalog pre-init is required and idempotent.

The pipeline renders `ExecStart` from this template and runs it against the validation image on the runner's Docker with three root-owned 0700 binds, the image by ID and no network. It requires exit 78, exactly one `DATA_GAP` line, no claim, no journal object and no leftover container. That proves the option set, mount-target creation under a read-only root filesystem, imports under the capability/pid/tmpfs limits, the ID reference with `--pull never`, and propagation of 78 through `--rm`.

Not proven anywhere yet: stop and SIGTERM as PID 1, egress, DNS and CA trust from `@NETWORK@`, ID resolution under the host's image store, behaviour of an empty `DOCKER_CONFIG` directory on the host, the stop bound with many retained sessions, alert delivery, and real provider behaviour. `RequiresMountsFor` is inert if systemd has no mount unit for the data volume. These stay pending until the rehearsal above is separately authorized.
