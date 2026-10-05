#!/bin/sh
# K6a (activate) on a real engine, as real root on Linux. For a THROWAWAY GitHub-hosted ubuntu-24.04 runner only, in the
# job of the core (core/linux_root/run.sh ../activate), AFTER that script: it has verified the seal of the core, run
# this operation's suite as root and as the runner's user, and switched the engine to the containerd image store.
# NEVER the production host and never a self-hosted runner: this builds one image, creates one compose project with
# three containers under /srv, and runs the assembled source against it as uid 0. One shape creates and removes a
# fourth container by name, and the last one interrupts a recreate of the third service (shapes.py). It refuses unless GitHub says the
# runner is GitHub-hosted and unless nothing of this family exists on the machine.
# NOT RUN by its author: no Linux and no docker were available offline.
#
# usage: sh linux_root/run.sh        (from the operation directory, or from anywhere: it changes to it)
# Output, always written: linux_root/SHAPES.activate.linux-root.json (a stage that did not run leaves a file that says
# NOT_RUN and why). Exit 0 only when: the seal of the operation and of the core hold before and after; the build is the
# assembly of the core; the image store is the containerd snapshotter; every shape ran; every expectation of
# shapes.py is met. Nothing here relies on "set -e": every status is tested where it is produced.
set -u
umask 022
cd "$(dirname "$0")/.." || exit 1
CORE=${HOSTOPS02_CORE_DIRECTORY:-../core}
OUT=linux_root
STATUS=0
WORK=
UP=no
PROJECT=hostops02ci
REFERENCE=c3po/backend:hostops02-ci-activate
REVISION=dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858
BUILT=no
say() { printf '\n== %s\n' "$*"; }
failed() { printf 'FAILED: %s\n' "$*" >&2; STATUS=1; }
refuse() { printf 'REFUSED: %s\n' "$*" >&2; exit 1; }
not_run() { [ -s "$1" ] || printf 'NOT_RUN: %s\n' "$2" > "$1"; }

cleanup() {
    if [ "$UP" = yes ]; then
        # the one compose project of this job, with both file lists (the override exists after a complete shape)
        sudo -n docker compose --project-name "$PROJECT" --env-file "$WORK/deploy/.env" -f "$WORK/deploy/$PROJECT/compose.yml" down --timeout 2 > /dev/null 2>&1
        # what an interrupted recreate or an interrupted shape may have left: every container of the project by label, and the one created by name
        for id in $(sudo -n docker ps -aq --filter "label=com.docker.compose.project=$PROJECT" 2>/dev/null); do sudo -n docker rm -f "$id" > /dev/null 2>&1; done
        sudo -n docker rm -f "0123456789ab_${PROJECT}-r2d2-worker-1" > /dev/null 2>&1
        UP=no
    fi
    if [ -n "$WORK" ]; then sudo -n rm -rf "$WORK"; WORK=; fi
    if [ "$BUILT" = yes ]; then sudo -n docker image rm "$REFERENCE" > /dev/null 2>&1; BUILT=no; fi
    sudo -n chown "$(id -u):$(id -g)" "$OUT/SHAPES.activate.linux-root.json" 2>/dev/null
    return 0
}

# ---- 0. where this is allowed to run. Until every line below has passed, nothing is done and sudo is not called.
[ "$(uname -s)" = Linux ] || refuse "Linux only"
[ "${HOSTOPS_THROWAWAY_RUNNER:-}" = yes ] || refuse "HOSTOPS_THROWAWAY_RUNNER=yes is required"
[ "${GITHUB_ACTIONS:-}" = true ] || refuse "a GitHub Actions job is required"
[ "${RUNNER_ENVIRONMENT:-}" = github-hosted ] || refuse "a GitHub-hosted runner is required (RUNNER_ENVIRONMENT=${RUNNER_ENVIRONMENT:-unset})"
[ "$(id -u)" != 0 ] || refuse "start as the runner's ordinary user; root is taken with sudo -n where it is needed"
for path in /etc/c3po-bar /var/lib/c3po-bar /etc/c3po-reader /var/lib/c3po-reader /opt/chief-of-staff-digital /mnt/day-d-data /run/c3po-security; do
    if [ -e "$path" ] || [ -L "$path" ]; then refuse "$path exists: this is not a throwaway runner"; fi
done
sha256sum -c --quiet SHA256SUMS || refuse "the operation is not the sealed one"
( cd "$CORE" && sha256sum -c --quiet CORE_SHA256SUMS ) || refuse "the core is not the sealed one"
sudo -n true || refuse "sudo -n is not available"
trap cleanup EXIT
trap 'exit 130' INT TERM HUP
say "seals verified: operation $(sha256sum SHA256SUMS | cut -d' ' -f1), core $(sha256sum "$CORE/CORE_SHA256SUMS" | cut -d' ' -f1); generation $(/usr/bin/python3 -B "$CORE/assemble.py" --core)"
rm -f "$OUT/SHAPES.activate.linux-root.json"
/usr/bin/python3 -B "$CORE/assemble.py" --check . || failed "build/ is not what assemble.py writes"

# ---- 1. the engine: the containerd image store (the core's job switched it), the compose plugin, an image with the revision label
say "the engine"
STORE=$(sudo -n docker info --format '{{.Driver}} {{json .DriverStatus}}' 2>/dev/null) || STORE=
sudo -n docker version --format 'docker client {{.Client.Version}} server {{.Server.Version}}'
sudo -n docker compose version
printf 'image store: %s\n' "$STORE"
case "$STORE" in
    *io.containerd.snapshotter.v1*) STORE_OK=yes ;;
    *) STORE_OK=no; failed "the image store is not the containerd snapshotter (run the core's linux_root/run.sh first); nothing is built and no shape is run" ;;
esac
IMAGE_ID=
if [ "$STORE_OK" = yes ]; then
    if sudo -n docker image inspect "$REFERENCE" > /dev/null 2>&1 || sudo -n docker image inspect c3po/backend:production > /dev/null 2>&1; then
        refuse "an image of the production repository exists: this is not a throwaway runner"
    fi
    BASE=
    for candidate in python:3.12-slim public.ecr.aws/docker/library/python:3.12-slim; do
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
fi

# ---- 2. the deploy tree and the data root, under /srv (root-owned, not world-writable: the signed chains refuse /tmp and /var/tmp)
if [ -n "$IMAGE_ID" ]; then
    say "the trees"
    WORK=$(sudo -n mktemp -d /srv/hostops02-activate-XXXXXXXX) || { WORK=; failed "no work directory under /srv"; }
fi
if [ -n "$WORK" ]; then
    if sudo -n /usr/bin/python3 -I -B linux_root/shapes.py --prepare "$WORK" "$REFERENCE" "$PROJECT" "$CORE/tests"; then
        # the deploy, as the pipeline makes it: from the deploy tree, the environment file and the one compose file (c3po-pipeline.yml:743-746)
        say "the deploy of the throwaway project"
        if ( cd "$WORK/deploy" && sudo -n env "C3PO_BUILD_SHA=$REVISION" docker compose --env-file .env -f "$PROJECT/compose.yml" up -d --no-build ); then
            UP=yes
            sudo -n docker ps -a --format '{{.Names}} {{.State}}'
            say "the shapes"
            sudo -n env HOSTOPS_THROWAWAY_RUNNER=yes RUNNER_ENVIRONMENT=github-hosted /usr/bin/python3 -I -B linux_root/shapes.py "$IMAGE_ID" "$WORK" "$PROJECT" "$CORE/tests" > "$OUT/SHAPES.activate.linux-root.json"
            SHAPES=$?
            [ "$SHAPES" = 0 ] || failed "shapes.py exit $SHAPES (2: a shape did not run; 3: an expectation is not met)"
            sudo -n docker ps -a --format '{{.Names}} {{.State}}'
        else
            UP=yes
            failed "the throwaway project could not be started"
        fi
    else
        failed "the trees could not be written"
    fi
fi
not_run "$OUT/SHAPES.activate.linux-root.json" "no image under the containerd image store, no work tree, or the project did not start"

cleanup
say "seals after the run"
sha256sum -c --quiet SHA256SUMS || failed "a file of the sealed operation changed during the run"
( cd "$CORE" && sha256sum -c --quiet CORE_SHA256SUMS ) || failed "a file of the sealed core changed during the run"
ls -ln "$OUT"
say "exit status $STATUS"
exit "$STATUS"
