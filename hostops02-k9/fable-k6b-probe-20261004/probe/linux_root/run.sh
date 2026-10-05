#!/bin/sh
# The capacity probe (steps CALENDAR, IDENT, LOAD) on a real engine, on Linux as real root. For a THROWAWAY GitHub-hosted
# ubuntu-24.04 runner only. NEVER the production host and never a self-hosted runner: this builds the release's backend
# image from a checkout (its requirements come from the package index), creates /var/lib/c3po-capacity, starts a
# detached stand-in container named c3po-r2d2-worker-1 with that tree bound read-only, and runs containers.
# It refuses unless GitHub says the runner is GitHub-hosted, and unless nothing of this family exists on the machine;
# it removes only what this very run created.
# NOT RUN by its author: no Linux and no docker were available offline. The structure of tls_probe's run.sh.
#
# usage: sh linux_root/run.sh <release checkout>      (from the operation directory, beside ../core)
#        <release checkout>  a checkout of the release (dd4ec4bb): the files this operation is frozen against are
#                            compared by hash before anything is built
# Run it AFTER the core's job step (sh ../core/linux_root/run.sh ...), which checks the seal, the assembly and the suites
# as root and as user, installs pytest for /usr/bin/python3 and switches the engine to the containerd image store.
#
# No network is given to any container of the probe (--network none in the source's argv); only the image build
# reaches the package index. The config file written into the tree is NOT a valid static config (one needs the epoch's
# documents): LOAD is expected to reach CapacityConfig and be refused by the config's fields, never to succeed.
#
# Output, always written: linux_root/SHAPES.capacity_probe.linux-root.json (a stage that did not run leaves a file that
# says NOT_RUN and why). Exit 0 only when every run was made, every expectation of probe_shape.py is met and everything
# this run created is gone again.
# Nothing here relies on "set -e": every status is tested where it is produced.
set -u
umask 022
cd "$(dirname "$0")/.." || exit 1
OUT=linux_root/SHAPES.capacity_probe.linux-root.json
REVISION=dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858
TAG=hostops02-capacity-probe-ci:release
TREE=/var/lib/c3po-capacity
WORKER=c3po-r2d2-worker-1
STATUS=0
BUILT=no
MADE_TREE=no
STARTED_WORKER=no
say() { printf '\n== %s\n' "$*"; }
failed() { printf 'FAILED: %s\n' "$*" >&2; STATUS=1; }
refuse() { printf 'REFUSED: %s\n' "$*" >&2; exit 1; }
cleanup() {
    if [ "$STARTED_WORKER" = yes ]; then sudo -n docker rm -f "$WORKER" > /dev/null 2>&1 || failed "the stand-in worker could not be removed"; STARTED_WORKER=no; fi
    if [ "$MADE_TREE" = yes ]; then sudo -n rm -rf "$TREE" || failed "the tree could not be removed"; MADE_TREE=no; fi
    if [ "$BUILT" = yes ]; then sudo -n docker image rm "$TAG" > /dev/null 2>&1; BUILT=no; fi
    sudo -n chown "$(id -u):$(id -g)" "$OUT" 2>/dev/null
    return 0
}

[ "$(uname -s)" = Linux ] || refuse "Linux only"
[ "${HOSTOPS_THROWAWAY_RUNNER:-}" = yes ] || refuse "HOSTOPS_THROWAWAY_RUNNER=yes is required"
[ "${GITHUB_ACTIONS:-}" = true ] || refuse "a GitHub Actions job is required"
[ "${RUNNER_ENVIRONMENT:-}" = github-hosted ] || refuse "a GitHub-hosted runner is required (RUNNER_ENVIRONMENT=${RUNNER_ENVIRONMENT:-unset})"
[ "$(id -u)" != 0 ] || refuse "start as the runner's ordinary user; root is taken with sudo -n where it is needed"
[ "$#" = 1 ] || refuse "usage: sh linux_root/run.sh <release checkout>"
RELEASE=$1
for path in "$TREE" /etc/c3po-reader /var/lib/c3po-reader /opt/chief-of-staff-digital /mnt/day-d-data; do
    if [ -e "$path" ] || [ -L "$path" ]; then refuse "$path exists: this is not a throwaway runner"; fi
done
sha256sum -c --quiet SHA256SUMS || refuse "the operation directory is not the sealed one"
/usr/bin/python3 -B ../core/assemble.py --check . || refuse "build/ is not what the frozen core assembles"
sudo -n true || refuse "sudo -n is not available"
trap cleanup EXIT
trap 'exit 130' INT TERM HUP
rm -f "$OUT"

say "the files of the release this operation is frozen against"
( cd "$RELEASE" && sha256sum -c --quiet - ) <<'PINS' || refuse "the checkout is not the release dd4ec4bb for the files of the probe"
e7e5b48ca890d93b2a5a9d86919f2c6c58e95606f2b0ec62f0afe98e4657163f  c3po/backend/app/r2d2_v2_capacity_anchored.py
9f9887c267af10c5494ec1a4dd2628b05f74f40dd2bae34e340bf81f00575254  c3po/backend/app/r2d2_v2_store.py
8f7a21dc13ba40d2bca26583ffa8598d40ffd4a8fc0a64ae0331c94b1d11e482  c3po/backend/app/r2d2_v2_capacity_bootstrap.py
91619929a513074f2eee01a6bcd78342305e0066e61ac79f2afd087c2e035897  c3po/backend/app/config.py
8ef584e2dd5d0b41d33f06a00926877573c65b5540f450236910e07ba51ee37c  c3po/backend/app/r2d2_v2_epoch_assembler.py
508636d0bb9cbc81076dfcfeb49cab03f1762c613b740d4a7391faf1a26e8ebf  c3po/backend/Dockerfile
fd214c8e36e47cc88f58e947eebf33c959e81c42929c4ecbb9149f87bdbd499e  c3po/compose.yml
PINS

say "the image store must be the containerd snapshotter (the core's job step set it)"
STORE=$(sudo -n docker info --format '{{.Driver}} {{json .DriverStatus}}' 2>/dev/null) || STORE=
case "$STORE" in
    *io.containerd.snapshotter.v1*) : ;;
    *) printf 'NOT_RUN: the image store is not the containerd snapshotter (%s)\n' "$STORE" > "$OUT"; refuse "run the core's linux_root/run.sh first" ;;
esac
if sudo -n docker image inspect "$TAG" > /dev/null 2>&1; then refuse "$TAG exists: this is not a throwaway runner"; fi
if sudo -n docker container inspect "$WORKER" > /dev/null 2>&1; then refuse "$WORKER exists: this is not a throwaway runner"; fi
sudo -n docker version --format 'docker client {{.Client.Version}} server {{.Server.Version}}'

say "the release's backend image, built from the checkout with the release's own Dockerfile, labelled with its revision"
IMAGE=
if sudo -n docker build -q --label "org.opencontainers.image.revision=$REVISION" -t "$TAG" -f "$RELEASE/c3po/backend/Dockerfile" "$RELEASE/c3po" > /dev/null; then
    BUILT=yes
    IMAGE=$(sudo -n docker image inspect --format '{{.Id}}' "$TAG" 2>/dev/null) || IMAGE=
fi
case "$IMAGE" in sha256:*) printf 'image %s\n' "$IMAGE" ;; *) IMAGE=; failed "the release image could not be built" ;; esac

CI_RELEASE=$(printf '%s' 'hostops02 capacity probe ci release sha' | sha256sum | cut -d' ' -f1) || CI_RELEASE=
CONFIG_SHA=
if [ -n "$IMAGE" ]; then
    say "the capacity tree: root:root 0700, four private children, a config file 0600 (not a valid static config)"
    if sudo -n mkdir -m 0700 "$TREE"; then
        MADE_TREE=yes
        for name in config documents go payload; do sudo -n mkdir -m 0700 "$TREE/$name" || failed "$TREE/$name could not be made"; done
        printf '{"schema":"R2D2_CAPACITY_BOOTSTRAP_V3","synthetic":"a static config of the tests, never authoritative"}\n' \
            | sudo -n sh -c "umask 077 && cat > $TREE/config/week.static.capacity.json" || failed "the config file could not be written"
        CONFIG_SHA=$(sudo -n sha256sum "$TREE/config/week.static.capacity.json" | cut -d' ' -f1) || CONFIG_SHA=
        sudo -n stat -c '%n %U:%G %a %h' "$TREE" "$TREE"/* "$TREE/config/week.static.capacity.json"
    else
        failed "$TREE could not be made"
    fi
    case "$CONFIG_SHA" in [0-9a-f]*) : ;; *) CONFIG_SHA=; failed "no hash of the config file" ;; esac
fi

if [ -n "$CONFIG_SHA" ]; then
    say "a stand-in worker: the release image, detached, the tree bound read-only at /c3po-capacity (B4's shape), the release pin and the mount source in its environment"
    if sudo -n docker run -d --name "$WORKER" --pull never --read-only --network none --cap-drop ALL --security-opt no-new-privileges \
        -e "C3PO_R2D2_V2_SHADOW_RELEASE_SHA=$CI_RELEASE" -e "C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE=$TREE" \
        --mount "type=bind,source=$TREE,target=/c3po-capacity,readonly" "$IMAGE" python -I -B -c 'import time; time.sleep(900)' > /dev/null; then
        STARTED_WORKER=yes
    else
        failed "the stand-in worker could not be started"; CONFIG_SHA=
    fi
fi

if [ -n "$CONFIG_SHA" ]; then
    say "CALENDAR, IDENT and LOAD with the operation's own perform and Native"
    sudo -n env HOSTOPS_THROWAWAY_RUNNER=yes RUNNER_ENVIRONMENT=github-hosted /usr/bin/python3 -I -B linux_root/probe_shape.py "$IMAGE" "$CONFIG_SHA" > "$OUT"
    SHAPE=$?
    [ "$SHAPE" = 0 ] || failed "probe_shape.py exit $SHAPE (2: a run was not made; 3: an expectation is not met)"
    sudo -n docker ps -a --format '{{.Names}} {{.State}}'
fi
[ -s "$OUT" ] || printf 'NOT_RUN: no image, no tree or no stand-in worker\n' > "$OUT"

cleanup
say "nothing of this run is left"
if [ -e "$TREE" ] || [ -L "$TREE" ]; then failed "$TREE is still there"; fi
if sudo -n docker container inspect "$WORKER" > /dev/null 2>&1; then failed "$WORKER is still there"; fi
LEFT=$(sudo -n docker ps -a --format '{{.Names}}' 2>/dev/null | grep -c '^hostops02-probe-') || LEFT=0
[ "$LEFT" = 0 ] || failed "a container of the probe is still listed"
say "seal after the run"
sha256sum -c --quiet SHA256SUMS || failed "a file of the sealed operation directory changed during the run"
sha256sum "$OUT"; cat "$OUT"
say "exit status $STATUS"
exit "$STATUS"
