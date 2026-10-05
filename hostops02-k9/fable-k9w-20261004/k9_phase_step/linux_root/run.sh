#!/bin/sh
# K9W (k9_phase_step) on a real engine, as real root on Linux. For a THROWAWAY GitHub-hosted ubuntu-24.04 runner only, in
# the job of the core (core/linux_root/run.sh ../k9_phase_step), AFTER that script: it has verified the seal of the core,
# run this operation's suite as root and as the runner's user, and switched the engine to the containerd image store.
# NEVER the production host and never a self-hosted runner: this builds one image (python:3.12-alpine with the revision
# label), creates /var/lib/c3po with the K9 tree and the source root of the compiled placement, two docker networks and
# containers (shapes.py). It refuses unless GitHub says the runner is GitHub-hosted and unless nothing of this family
# exists on the machine. NOT RUN by its author: no Linux and no docker were available offline.
#
# usage: sh linux_root/run.sh        (from the operation directory, or from anywhere: it changes to it)
# Output, always written: linux_root/SHAPES.k9_phase_step.linux-root.json (a stage that did not run leaves a file that
# says NOT_RUN and why). Exit 0 only when: the seal of the operation and of the core hold before and after; the build is
# the assembly of the core; every shape ran; every expectation of shapes.py is met. Nothing here relies on "set -e":
# every status is tested where it is produced.
set -u
umask 022
cd "$(dirname "$0")/.." || exit 1
CORE=${HOSTOPS02_CORE_DIRECTORY:-../core}
OUT=linux_root/SHAPES.k9_phase_step.linux-root.json
STATUS=0
REFERENCE=c3po/backend:hostops02-ci-k9w
REVISION=dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858
BUILT=no
say() { printf '\n== %s\n' "$*"; }
failed() { printf 'FAILED: %s\n' "$*" >&2; STATUS=1; }
refuse() { printf 'REFUSED: %s\n' "$*" >&2; exit 1; }
not_run() { [ -s "$1" ] || printf 'NOT_RUN: %s\n' "$2" > "$1"; }

cleanup() {
    for id in $(sudo -n docker ps -aq --filter "name=c3po-k9-" 2>/dev/null); do sudo -n docker rm -f "$id" > /dev/null 2>&1; done
    sudo -n docker network rm k9ci_internal k9ci_loopback > /dev/null 2>&1
    if [ "$BUILT" = yes ]; then sudo -n docker image rm "$REFERENCE" > /dev/null 2>&1; BUILT=no; fi
    sudo -n rm -rf /var/lib/c3po
    sudo -n chown "$(id -u):$(id -g)" "$OUT" 2>/dev/null
    return 0
}

# ---- 0. where this is allowed to run. Until every line below has passed, nothing is done and sudo is not called.
[ "$(uname -s)" = Linux ] || refuse "Linux only"
[ "${HOSTOPS_THROWAWAY_RUNNER:-}" = yes ] || refuse "HOSTOPS_THROWAWAY_RUNNER=yes is required"
[ "${GITHUB_ACTIONS:-}" = true ] || refuse "a GitHub Actions job is required"
[ "${RUNNER_ENVIRONMENT:-}" = github-hosted ] || refuse "a GitHub-hosted runner is required (RUNNER_ENVIRONMENT=${RUNNER_ENVIRONMENT:-unset})"
[ "$(id -u)" != 0 ] || refuse "start as the runner's ordinary user; root is taken with sudo -n where it is needed"
for path in /var/lib/c3po /mnt/day-d-data /opt/chief-of-staff-digital; do
    if [ -e "$path" ] || [ -L "$path" ]; then refuse "$path exists: this is not a throwaway runner"; fi
done
sha256sum -c --quiet SHA256SUMS || refuse "the operation is not the sealed one"
( cd "$CORE" && sha256sum -c --quiet CORE_SHA256SUMS ) || refuse "the core is not the sealed one"
sudo -n true || refuse "sudo -n is not available"
trap cleanup EXIT
trap 'exit 130' INT TERM HUP
say "seals verified: operation $(sha256sum SHA256SUMS | cut -d' ' -f1), core $(sha256sum "$CORE/CORE_SHA256SUMS" | cut -d' ' -f1)"
rm -f "$OUT"
/usr/bin/python3 -B "$CORE/assemble.py" --check . || failed "build/ is not what assemble.py writes"

# ---- 1. an Alpine image with python, busybox timeout and the revision label
say "the image"
IMAGE_ID=
BASE=
for candidate in python:3.12-alpine public.ecr.aws/docker/library/python:3.12-alpine; do
    if sudo -n docker pull -q "$candidate" > /dev/null; then BASE=$candidate; break; fi
done
if [ -n "$BASE" ] && printf 'FROM %s\n' "$BASE" | sudo -n docker build -q --label "org.opencontainers.image.revision=$REVISION" --tag "$REFERENCE" - > /dev/null; then
    BUILT=yes
    IMAGE_ID=$(sudo -n docker image inspect --format '{{.Id}}' "$REFERENCE") || IMAGE_ID=
fi
case "$IMAGE_ID" in
    sha256:*) printf 'image: %s with the revision label as %s, ID %s\n' "$BASE" "$REFERENCE" "$IMAGE_ID" ;;
    *) IMAGE_ID=; failed "no image with the revision label could be built" ;;
esac

# ---- 2. the shapes
if [ -n "$IMAGE_ID" ]; then
    say "the shapes"
    sudo -n env HOSTOPS_THROWAWAY_RUNNER=yes RUNNER_ENVIRONMENT=github-hosted /usr/bin/python3 -B linux_root/shapes.py "$IMAGE_ID" > "$OUT"
    SHAPES=$?
    [ "$SHAPES" = 0 ] || failed "shapes.py exit $SHAPES (2: a shape did not run; 3: an expectation is not met)"
    sudo -n docker ps -a --format '{{.Names}} {{.State}}'
fi
not_run "$OUT" "no image could be built"

cleanup
say "seals after the run"
sha256sum -c --quiet SHA256SUMS || failed "a file of the sealed operation changed during the run"
( cd "$CORE" && sha256sum -c --quiet CORE_SHA256SUMS ) || failed "a file of the sealed core changed during the run"
say "exit status $STATUS"
exit "$STATUS"
