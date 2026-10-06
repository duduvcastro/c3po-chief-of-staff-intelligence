# Capacity mount on `r2d2-worker`

Mount support only. The mount does not enable capacity and proves nothing about the planner.
This file grants no authority: every host step below needs its own order and GO.

## What it is

`c3po/compose.yml` gives `r2d2-worker`, and no other service, one extra mount:

    ${C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE:-c3po_capacity_unprovisioned}:/c3po-capacity:ro

- Read-only, top-level target. A capacity root identity hashes the name, device and inode of every
  path component, so a root under `/app/...` would include the container's own overlay.
- `C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE` is read by Compose only, from the host's root `.env`. It is
  not a setting; inside the containers it is ignored.

| Host value | Result |
| --- | --- |
| unset or empty | empty named volume `c3po_c3po_capacity_unprovisioned`, read-only |
| absolute path of an existing directory | read-only bind of that directory |
| absolute path that does not exist | Docker creates it, root-owned and empty, at every start of the container (below). Never do this: the exclusive-creation provisioning then refuses it |
| anything not starting with `/` | a bare word is an undeclared volume and every compose command that loads the file fails (deploy, security controllers, backup); a relative path is created under `c3po/` |

The line is short syntax, so the bind carries `create_host_path` and the engine creates a missing
source as an empty root-owned directory at every start of the container while the variable is set:
`up`, a restart by the restart policy, a daemon restart, a host reboot. Not only at the first `up`.
So:

- provision the tree first, set the variable second;
- do the full disable (below) before the tree is moved, removed or provisioned again, and enable
  again only when the new tree is complete.

(Read in the Compose v2.29.7 and Engine v27.3.1 sources; not exercised.)

The capacity settings are existing `Settings` fields and arrive only through the host `.env`
(`env_file`). The repository never sets them:

    C3PO_R2D2_V2_CAPACITY_REQUIRED=true
    C3PO_R2D2_V2_CAPACITY_CONFIG_FILE=<absolute container path under /c3po-capacity>
    C3PO_R2D2_V2_CAPACITY_CONFIG_SHA=<sha256 of that file>
    C3PO_R2D2_V2_CAPACITY_VETO_MODE=DISPATCH_AND_DERIVATION_ONLY

- Mount without the flag: no effect. The worker opens nothing under `/c3po-capacity`.
- Flag without a valid mount and config: `r2d2-worker` refuses at startup, before Sentry, the
  database, the stream, the V1 paper service and the raw capture, and restarts in a loop.
- The config also pins `C3PO_R2D2_V2_SHADOW_RELEASE_SHA` and the image's implementation package sha.
- The live policy file must stay outside `/c3po-capacity`: the controller writes next to it.

## Host that is not provisioned

No variable set, no tree on the host: the deploy needs nothing. Expected, not yet measured:
`config --quiet` passes, `up` creates one empty Docker volume, the worker gets an empty read-only
`/c3po-capacity`, and no directory is created at any host path. The PR job only renders (`config`
creates nothing), so what `up` creates on a host that is not provisioned is first measured by this
read-back after the first deploy that carries the mount (read-only):

    docker inspect "$(docker compose --env-file .env -f c3po/compose.yml ps -q r2d2-worker)" \
      --format '{{range .Mounts}}{{.Type}} {{.Name}} {{.Source}} {{.Destination}} RW={{.RW}}{{println}}{{end}}'

Expect one line `volume c3po_c3po_capacity_unprovisioned ... /c3po-capacity RW=false`.

## Where the tree lives

The value must be the same host directory that the standalone reader and the capacity-day writer
bind at `/c3po-capacity`, byte for byte; otherwise the pinned root identities differ. The location is
a host decision, recorded in the order. Know what each choice exposes:

- Under the data-volume source: `api`, `r2d2-worker` and `r2d2-shadow-candidate-worker` also reach
  the tree read-write through `/app/day-d-data`; `:ro` here does not protect it from them.
- Under `/opt/chief-of-staff-digital`: visible at `/legacy` and `/host/disk`, and deleted by the next
  deploy (`rsync --delete`) unless it sits in an excluded directory.
- Everything under the bound directory is readable by `r2d2-worker` (uid 0), including a receipt
  directory placed there.

## Enable

Run in `/opt/chief-of-staff-digital` as the owner of `.env`, never with `sudo` on `.env`. Market
closed. Stop at the first command that fails. Each recreate restarts the V1 worker and the raw capture.

    test -s .deploy-version && test -z "$(tail -c1 .env)" && stat -c '%U:%G %a' .env
    exec 9>>runtime/security/deployment.lock && flock -w 120 9 && test ! -e /run/c3po-security/reboot.pending
    compose() { C3PO_BUILD_SHA="$(cat .deploy-version)" docker compose --env-file .env -f c3po/compose.yml "$@"; }

Same order as the deploy: the lock first, the reboot marker second. The reboot controller writes the
marker while it holds the lock, so a marker checked before the lock can be stale. The lock serialises
against the deploy and the reboot controller; release it with `exec 9>&-`, also when the marker
check fails. A manual `up` without `C3PO_BUILD_SHA` gives the worker the build sha `development`.

`.env` is the `env_file` of all six backend services (`api`, `investor-relations-worker`,
`valuation-worker`, `server-usage-worker`, `r2d2-worker`, `r2d2-shadow-candidate-worker`). Every
line appended to it or deleted from it, the mount variable included, changes the config hash of all
six. `up -d --no-deps r2d2-worker` recreates only the worker; the next plain `up -d` (the deploy
runs one) recreates the other five.

### Step 1: mount only (after the tree and the static config are provisioned)

    CAP=<absolute host path of the tree>
    case "$CAP" in /*) true ;; *) false ;; esac \
      && test "$(sudo realpath "$CAP")" = "$CAP" && sudo test -d "$CAP/config" \
      && ! grep -q '^C3PO_R2D2_V2_CAPACITY_' .env \
      && printf 'C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE=%s\n' "$CAP" >> .env
    compose config --quiet
    compose config --format json | python3 c3po/deployment/capacity-mount/check_compose_render.py "bind=$CAP" -
    compose up -d --no-build --no-deps r2d2-worker

If `config` or the check fails, nothing was recreated. Delete the line appended above (the `! grep -q`
guard made sure it is the only one with this name), confirm and stop:

    sed -i '/^C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE=/d' .env
    compose config --quiet

Never display the JSON render: it carries the `.env` values. With a path set the placeholder volume is
unused and Compose leaves it out of the render; the checker expects that. Read back:

- the mounts command above prints `bind  <CAP> /c3po-capacity RW=false`, the source equal to `$CAP`;
- `docker inspect "$(compose ps -q r2d2-worker)" --format '{{.State.Status}} {{.RestartCount}}'` prints `running 0`;
- `compose exec -T r2d2-worker sh -c 'echo "$C3PO_BUILD_SHA"'` equals `.deploy-version`;
- only `r2d2-worker` was recreated.

### Step 2: dry run of the startup checks (flag still absent from `.env`)

    CFG=/c3po-capacity/config/<file>; SHA=<sha256 of the static config>
    compose exec -T -e C3PO_R2D2_V2_CAPACITY_REQUIRED=true -e C3PO_R2D2_V2_CAPACITY_CONFIG_FILE="$CFG" \
      -e C3PO_R2D2_V2_CAPACITY_CONFIG_SHA="$SHA" -e C3PO_R2D2_V2_CAPACITY_VETO_MODE=DISPATCH_AND_DERIVATION_ONLY \
      r2d2-worker python -B -c 'from app.config import Settings; from app.r2d2_v2_capacity_bootstrap import CapacityConfig; c=CapacityConfig(Settings()); print("CAPACITY_STARTUP_OK", sorted(c.roots), c.veto_mode); c.close()'

Add `-e C3PO_R2D2_V2_SHADOW_RELEASE_SHA=<release sha>` while that pin is not yet in `.env`. The dry run
opens read-only and writes nothing. Expected: `CAPACITY_STARTUP_OK ['documents', 'go', 'payload']
DISPATCH_AND_DERIVATION_ONLY`. Anything else (`FileNotFoundError`, `ROOT_NOT_PRIVATE`,
`ROOT_IDENTITY_CHANGED`, `CAPACITY_CONFIG_*`) is a stop: do not set the flag.

### Step 3: the flag (in the activation that writes the release and live-policy pins)

Repeat step 2 first if the worker was recreated or the host rebooted since. `CFG` and `SHA` are the
values step 2 passed; the mount variable must already be in `.env` and none of the four settings:

    test -n "$CFG" && test -n "$SHA" && test -z "$(tail -c1 .env)" \
      && grep -q '^C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE=/' .env \
      && ! grep -q '^C3PO_R2D2_V2_CAPACITY_REQUIRED=' .env \
      && ! grep -q '^C3PO_R2D2_V2_CAPACITY_CONFIG_FILE=' .env \
      && ! grep -q '^C3PO_R2D2_V2_CAPACITY_CONFIG_SHA=' .env \
      && ! grep -q '^C3PO_R2D2_V2_CAPACITY_VETO_MODE=' .env \
      && printf '%s\n' "C3PO_R2D2_V2_CAPACITY_REQUIRED=true" "C3PO_R2D2_V2_CAPACITY_CONFIG_FILE=$CFG" \
        "C3PO_R2D2_V2_CAPACITY_CONFIG_SHA=$SHA" "C3PO_R2D2_V2_CAPACITY_VETO_MODE=DISPATCH_AND_DERIVATION_ONLY" >> .env
    compose config --quiet
    compose up -d --no-build --no-deps r2d2-worker

If `config` fails, nothing was recreated. Delete the four lines, confirm and stop:

    sed -i -E '/^C3PO_R2D2_V2_CAPACITY_(REQUIRED|CONFIG_FILE|CONFIG_SHA|VETO_MODE)=/d' .env
    compose config --quiet

Read back:

    compose exec -T r2d2-worker python -B -c 'from app.config import Settings; s=Settings(); print(s.r2d2_v2_capacity_required, s.r2d2_v2_capacity_config_file, s.r2d2_v2_capacity_config_sha, s.r2d2_v2_capacity_veto_mode)'

- prints `True <CFG> <SHA> DISPATCH_AND_DERIVATION_ONLY`;
- status and restart count, twice 60 s apart: `running 0`; `compose logs --tail 80 r2d2-worker` shows no
  traceback and no `CAPACITY_` or `ROOT_` code;
- `capacity_mode` in the live status file is `OPEN_ONLY_FALLBACK` until the reader has copied the
  day's binding into the session and `BOUND_MONITORED` after. `readiness` stays `NOT_PROVEN`.

## Disable

Both are meant to work while the worker is in a restart loop, and neither writes to the tree.

- Fast (keeps the mount): `sed -i '/^C3PO_R2D2_V2_CAPACITY_REQUIRED=/d' .env`, then `compose config --quiet`
  and `compose up -d --no-build --no-deps r2d2-worker`. The settings one-liner prints `False ...`.
- Full: `sed -i '/^C3PO_R2D2_V2_CAPACITY_/d' .env` (the mount variable shares the prefix), then the same
  two commands. The mounts command shows the placeholder volume again; restart count `0`.

Check owner and mode of `.env` afterwards: the deploy rewrites that file as the deploy user.

## While the variable is set

- Every start of `r2d2-worker` creates the bind source again if it is missing (see "What it is"). A
  tree that is moved or removed while the variable is set comes back as an empty root-owned directory
  at the old path, and the exclusive-creation provisioning then refuses that path.
- Full disable first, then move, remove or provision; enable again only when the tree is complete.

## While the flag is on

- Every restart of `r2d2-worker` (deploy, security reboot, crash, daemon restart) reruns the fatal
  startup checks. A re-provisioned tree (new inodes), a replaced config, a rotated release sha or an
  image with another package sha turns into a restart loop of the whole worker.
- Nothing alerts on that loop: the deploy health gate does not watch `r2d2-worker`. Read its status
  and restart count at every checkpoint. A restarting worker also fails the reboot controller's
  admission check, so security reboots stop.
- Do the full disable before the epoch's pins are removed and the host is rebooted, before any deploy
  that changes the package sha, and before the tree is provisioned again.
- Do not start any V2 worker with `docker exec`: the flag is in the environment of all six backend
  containers and only `r2d2-worker` has the mount.

## Not verified on the host

- Nothing here ran on the host. The PR job renders the three host states with `docker compose config`
  on the runner's engine; the host's Engine and Compose versions are not recorded in the repository.
- Until that job has run, the render shapes the checker accepts come from reading the Compose source
  (fixtures in `c3po/backend/tests/fixtures/compose_capacity_mount`), not from an engine.
- What `up` creates on a host that is not provisioned (one empty volume, no host path): first measured
  by the read-back after the first deploy that carries the mount.
- That the engine creates a missing bind source at every container start, and that a line added to
  `.env` changes the config hash of all six backend services (both read in source only).
- That a recreate which fails at creation leaves the old container running (read in Compose v2.29.7
  source only), and that `up` replaces a container that is in a restart loop (never exercised).
- That device and inode numbers of the tree are equal in `r2d2-worker`, the reader and the writer, and
  stable across a recreate and a reboot. Step 2 is the first measurement. User-namespace remapping
  would also break the owner check.
- The host path of the tree, and whether the release and live-policy pins are in the host `.env`.
- The capacity planner and `CapacityConfig` have no tests in this repository.
