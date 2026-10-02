#!/bin/sh
# K2a (catalog initialisation) on a real engine, on Linux as real root. For a THROWAWAY GitHub-hosted ubuntu-24.04 runner
# only. NEVER the production host and never a self-hosted runner: this builds an image, creates containers, CREATES the
# layout of supervisor operation 2 at its real paths (/etc/c3po-bar/docker-cli, /var/lib/c3po-bar/journal) and REMOVES
# it again. The operation part accepts no other paths (its layout floor), so the shape runs on the paths of the host.
# It refuses unless GitHub says the runner is GitHub-hosted, and unless nothing of this family exists on the machine;
# it removes only what this very run created.
# NOT RUN by its author: no Linux and no docker were available offline. The structure of the core's linux_root/run.sh.
#
# usage: sh linux_root/run_catalog.sh <release checkout>     (from the operation directory hostops02/catalog_init)
#        <release checkout>  a checkout of the release (dd4ec4bb) that holds c3po/backend/app; its files are compared by
#                            hash with the ones this operation is frozen against before anything is built
# Run it AFTER the core's job step (sh linux_root/run.sh ../catalog_init ...), which checks the seal, the assembly and
# the suites as root and as user, and switches the engine to the containerd image store. This step adds the operation's
# own shape. Output, always written: linux_root/CATALOG_SHAPE.linux-root.json (a stage that did not run leaves a file
# that says NOT_RUN and why). Exit 0 only when every run was made and every expectation of catalog_shape.py is met.
# Nothing here relies on "set -e": every status is tested where it is produced.
set -u
umask 022
cd "$(dirname "$0")/.." || exit 1
OUT=linux_root/CATALOG_SHAPE.linux-root.json
REFERENCE=c3po/backend:hostops02-k2a-ci-probe
REVISION=dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858
# The base of the release's own image (c3po/backend/Dockerfile at dd4ec4bb, compared below), by digest: the throwaway
# image is built on the bytes production is built on.
BASE=python:3.12-alpine3.24@sha256:b64631e04e4920160c50fbe8d8df828f7f35f06f425cb44aa09bca53e708a35a
HOST_DOCKER_CLIENT=29.5.3
REHEARSAL=/var/lib/c3po-bar-rehearsal-ci
STATUS=0
LAYOUT=no
CONTEXT=
BUILT=no
say() { printf '\n== %s\n' "$*"; }
failed() { printf 'FAILED: %s\n' "$*" >&2; STATUS=1; }
refuse() { printf 'REFUSED: %s\n' "$*" >&2; exit 1; }
cleanup() {
    # only what this run created: LAYOUT is set after this run's own exclusive mkdir of both parents succeeded
    if [ "$LAYOUT" = yes ]; then sudo -n rm -rf /etc/c3po-bar /var/lib/c3po-bar "$REHEARSAL" "$REHEARSAL.docker-cli"; LAYOUT=no; fi
    if [ -n "$CONTEXT" ]; then rm -rf "$CONTEXT"; CONTEXT=; fi
    if [ "$BUILT" = yes ]; then sudo -n docker image rm "$REFERENCE" > /dev/null 2>&1; BUILT=no; fi
    sudo -n chown "$(id -u):$(id -g)" "$OUT" 2>/dev/null
    return 0
}

[ "$(uname -s)" = Linux ] || refuse "Linux only"
[ "${HOSTOPS_THROWAWAY_RUNNER:-}" = yes ] || refuse "HOSTOPS_THROWAWAY_RUNNER=yes is required"
[ "${GITHUB_ACTIONS:-}" = true ] || refuse "a GitHub Actions job is required"
[ "${RUNNER_ENVIRONMENT:-}" = github-hosted ] || refuse "a GitHub-hosted runner is required (RUNNER_ENVIRONMENT=${RUNNER_ENVIRONMENT:-unset})"
[ "$(id -u)" != 0 ] || refuse "start as the runner's ordinary user; root is taken with sudo -n where it is needed"
[ "$#" = 1 ] || refuse "usage: sh linux_root/run_catalog.sh <release checkout>"
RELEASE=$1
for path in /etc/c3po-bar /var/lib/c3po-bar /etc/c3po-reader /var/lib/c3po-reader /opt/chief-of-staff-digital /mnt/day-d-data "$REHEARSAL" "$REHEARSAL.docker-cli"; do
    if [ -e "$path" ] || [ -L "$path" ]; then refuse "$path exists: this is not a throwaway runner"; fi
done
sha256sum -c --quiet SHA256SUMS || refuse "the operation directory is not the sealed one"
/usr/bin/python3 -B ../core/assemble.py --check . || refuse "build/ is not what the frozen core assembles"
sudo -n true || refuse "sudo -n is not available"
trap cleanup EXIT
trap 'exit 130' INT TERM HUP
rm -f "$OUT"

say "the files of the release this operation is frozen against"
( cd "$RELEASE" && sha256sum -c --quiet - ) <<'PINS' || refuse "the checkout is not the release dd4ec4bb for the files of the catalog"
644c6211c7351de1dfd17d880842deaf4d5e5b34ea63d23a274c5f4e463461c5  c3po/deployment/massive-supervisor/README.md
c4ffe1c9095a81b0057dc2b7995198f25179015e5af963f137c7b8f7c1605312  c3po/backend/app/r2d2_v2_massive_sessions.py
8946a93939162c33b19575681cb920359181a53bf27dacf3918b5a9d1a2052d9  c3po/backend/app/r2d2_v2_massive_maintenance.py
9f9887c267af10c5494ec1a4dd2628b05f74f40dd2bae34e340bf81f00575254  c3po/backend/app/r2d2_v2_store.py
8ef584e2dd5d0b41d33f06a00926877573c65b5540f450236910e07ba51ee37c  c3po/backend/app/r2d2_v2_epoch_assembler.py
508636d0bb9cbc81076dfcfeb49cab03f1762c613b740d4a7391faf1a26e8ebf  c3po/backend/Dockerfile
PINS
grep -Fxq "FROM $BASE" "$RELEASE/c3po/backend/Dockerfile" || refuse "the release's Dockerfile is not built on $BASE"
if grep -q '^ENTRYPOINT' "$RELEASE/c3po/backend/Dockerfile"; then refuse "the release's image has an entrypoint: the README argv would not start python"; fi

say "the docker client of this runner against the client of the host ($HOST_DOCKER_CLIENT)"
CLIENT=$(sudo -n docker version --format '{{.Client.Version}}' 2>/dev/null) || CLIENT=unknown
if [ "$CLIENT" = "$HOST_DOCKER_CLIENT" ]; then printf 'CLIENT_VERSION_EQUAL %s\n' "$CLIENT"
else printf 'CLIENT_VERSION_DIFFERS runner %s, host %s: what this job shows of the docker CLI under an empty DOCKER_CONFIG (K2A-U2) is shown for %s only; on the host the rehearsal shows it, under a directory of its own\n' "$CLIENT" "$HOST_DOCKER_CLIENT" "$CLIENT"
fi

say "the image store must be the containerd snapshotter (the core's job step set it)"
STORE=$(sudo -n docker info --format '{{.Driver}} {{json .DriverStatus}}' 2>/dev/null) || STORE=
case "$STORE" in
    *io.containerd.snapshotter.v1*) : ;;
    *) printf 'NOT_RUN: the image store is not the containerd snapshotter (%s)\n' "$STORE" > "$OUT"; refuse "run the core's linux_root/run.sh first" ;;
esac
if sudo -n docker image inspect "$REFERENCE" > /dev/null 2>&1 || sudo -n docker image inspect c3po/backend:production > /dev/null 2>&1; then
    refuse "an image of the production repository exists: this is not a throwaway runner"
fi

# The production image is that base with tzdata, the dependencies of requirements.txt and the application at /app/app,
# no entrypoint (c3po/backend/Dockerfile at dd4ec4bb). The throwaway image is the same base, by digest, with tzdata and
# the application and nothing else: no dependency of requirements.txt is installed, because the catalog script imports
# only modules of the standard library and of the application (the build fails here if that is not so). What stays
# for the rehearsal on the host is the production image itself (K2A-U4): its dependencies and its duration.
say "a throwaway image: the base of the release by digest, tzdata, and the application modules of the release at /app/app"
CONTEXT=$(mktemp -d) || refuse "no build context"
cp -R "$RELEASE/c3po/backend/app" "$CONTEXT/app" || refuse "the application modules cannot be copied"
printf 'FROM %s\nRUN apk add --no-cache tzdata\nWORKDIR /app\nCOPY app /app/app\nRUN python -I -B -c "import sys; sys.path.insert(0, \\"/app\\"); import app.r2d2_v2_massive_sessions, app.r2d2_v2_store"\n' "$BASE" > "$CONTEXT/Dockerfile"
IMAGE_ID=
if sudo -n docker build -q --label "org.opencontainers.image.revision=$REVISION" -t "$REFERENCE" "$CONTEXT" > /dev/null; then
    BUILT=yes
    IMAGE_ID=$(sudo -n docker image inspect --format '{{.Id}}' "$REFERENCE") || IMAGE_ID=
fi
case "$IMAGE_ID" in
    sha256:*) printf 'image: %s, ID %s\n' "$REFERENCE" "$IMAGE_ID" ;;
    *) IMAGE_ID=; failed "the throwaway image could not be built ($BASE with tzdata and the modules of the release)" ;;
esac

if [ -n "$IMAGE_ID" ]; then
    say "the layout of supervisor operation 2, placement A (root:root 0700, empty), created exclusively"
    # os.mkdir fails on a name that exists: the first two are the parents this run removes again, and LAYOUT says so
    if sudo -n /usr/bin/python3 -I -B - <<'TREE'
import os
os.umask(0o077)
for path in ('/etc/c3po-bar','/var/lib/c3po-bar'):os.mkdir(path,0o700)
TREE
    then
        LAYOUT=yes
        if sudo -n /usr/bin/python3 -I -B - <<'TREE'
import os
os.umask(0o077)
for path in ('/etc/c3po-bar/docker-cli','/var/lib/c3po-bar/supervisor','/var/lib/c3po-bar/journal'):os.mkdir(path,0o700)
TREE
        then
            say "K2a: REHEARSAL, REAL, and REAL again, with the operation's own perform and Native"
            sudo -n env HOSTOPS_THROWAWAY_RUNNER=yes RUNNER_ENVIRONMENT=github-hosted /usr/bin/python3 -I -B linux_root/catalog_shape.py "$IMAGE_ID" "$REVISION" > "$OUT"
            SHAPE=$?
            [ "$SHAPE" = 0 ] || failed "catalog_shape.py exit $SHAPE (2: a run was not made; 3: an expectation is not met)"
            sudo -n docker ps -a --format '{{.Names}} {{.State}}'
            sudo -n ls -lnR /etc/c3po-bar /var/lib/c3po-bar "$REHEARSAL" "$REHEARSAL.docker-cli"
        else
            failed "the layout could not be completed"
        fi
    else
        failed "the layout could not be created"
    fi
fi
[ -s "$OUT" ] || printf 'NOT_RUN: no throwaway image or no layout\n' > "$OUT"

cleanup
say "seal after the run"
sha256sum -c --quiet SHA256SUMS || failed "a file of the sealed operation directory changed during the run"
sha256sum "$OUT"; cat "$OUT"
say "exit status $STATUS"
exit "$STATUS"
