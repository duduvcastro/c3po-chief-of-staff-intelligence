#!/bin/sh
# HOSTOPS02 proof job, last part: the command shapes of the tier 0 operations with the BACKEND IMAGE BUILT FROM THIS
# CHECKOUT by the repository's own Dockerfile, as the pipeline builds it (c3po-pipeline.yml at the release: docker build
# --file c3po/backend/Dockerfile --build-arg C3PO_SECURITY_REBUILD=<sha256 of the trigger file> --label
# org.opencontainers.image.revision=<revision> --tag <reference> c3po), under the containerd image store.
#
# For a THROWAWAY GitHub-hosted ubuntu-24.04 runner only. NEVER the production host and never a self-hosted runner: this
# builds an image, creates containers and one compose project, CREATES the layout of supervisor operation 2 at its real
# paths (/etc/c3po-bar/docker-cli, /var/lib/c3po-bar/journal) and REMOVES it again, and writes under /srv. It refuses
# unless GitHub says the runner is GitHub-hosted and unless nothing of this family exists on the machine; it removes only
# what this very run created. NOT RUN by its author: no Linux and no docker were available offline.
#
# usage: sh proof/release_image.sh <release checkout>      (from hostops02/, or from anywhere: it changes to it)
#        <release checkout>  the checkout of this branch: its c3po/ must be the tree of the release dd4ec4bb
# Run it AFTER the core's job step (core/linux_root/run.sh), which switches the engine to the containerd image store.
# The sealed scripts of the operations stay the gates their contracts name; they use stand-in images. This script runs
# the sealed shape scripts again, unchanged, with the image of the release, and adds two shapes of its own:
#   1. the image: built, labelled with the revision, no pip in it (the pipeline's own smoke)
#   2. K2a  catalog_init/linux_root/catalog_shape.py: REHEARSAL, REAL, REAL again, with the pinned script of the README
#   3. K11  epoch_readback/linux_root/shapes_k11.py: the engine shapes (its stand-in package bound over /app)
#   4. K11  proof/release_verify_shape.py: Release.verify of the image's OWN application on synthetic release bytes
#   5. K11 and K6a  proof/release_compose_render.py: the compose file of the release rendered by both sources' helpers
#   6. K6a  activate/linux_root/shapes.py: the whole operation on a throwaway project, one recreate with the override file
# Output, always written, in proof/out/: IMAGE.release-image.txt and one JSON file per shape script (a stage that did not
# run leaves a file that says NOT_RUN and why). Exit 0 only when every stage ran and every expectation is met. Every stage
# runs whatever the earlier ones did; the status is kept and returned.
# Nothing here relies on "set -e": every status is tested where it is produced.
set -u
umask 022
cd "$(dirname "$0")/.." || exit 1
FAMILY=$(pwd)
OUT=proof/out
REVISION=dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858
C3PO_TREE=058a83e92aae5cb052ca74bf8a56d4667c5cfc08     # git rev-parse dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858:c3po, the build context
REFERENCE=c3po/backend:hostops02-ci-release
PROJECT=hostops02rel
REHEARSAL=/var/lib/c3po-bar-rehearsal-ci
STATUS=0
BUILT=no
LAYOUT=no
UP=no
LOG=
WORK_K11=
WORK_VERIFY=
WORK_RENDER=
WORK_K6A=
say() { printf '\n== %s\n' "$*"; }
failed() { printf 'FAILED: %s\n' "$*" >&2; STATUS=1; }
refuse() { printf 'REFUSED: %s\n' "$*" >&2; exit 1; }
not_run() { [ -s "$1" ] || printf 'NOT_RUN: %s\n' "$2" > "$1"; }
remove_work() {   # only a directory this run made under /srv with mktemp
    case "$1" in /srv/hostops02-*) sudo -n rm -rf "$1" ;; esac
}
cleanup() {
    if [ "$UP" = yes ]; then
        sudo -n docker compose --project-name "$PROJECT" --env-file "$WORK_K6A/deploy/.env" -f "$WORK_K6A/deploy/$PROJECT/compose.yml" down --timeout 2 > /dev/null 2>&1
        for id in $(sudo -n docker ps -aq --filter "label=com.docker.compose.project=$PROJECT" 2>/dev/null); do sudo -n docker rm -f "$id" > /dev/null 2>&1; done
        sudo -n docker rm -f "0123456789ab_${PROJECT}-r2d2-worker-1" > /dev/null 2>&1
        UP=no
    fi
    # only what this run created: LAYOUT is set after this run's own exclusive mkdir of both parents succeeded
    if [ "$LAYOUT" = yes ]; then sudo -n rm -rf /etc/c3po-bar /var/lib/c3po-bar "$REHEARSAL" "$REHEARSAL.docker-cli"; LAYOUT=no; fi
    remove_work "$WORK_K11"; WORK_K11=
    remove_work "$WORK_VERIFY"; WORK_VERIFY=
    remove_work "$WORK_RENDER"; WORK_RENDER=
    remove_work "$WORK_K6A"; WORK_K6A=
    if [ "$BUILT" = yes ]; then sudo -n docker image rm "$REFERENCE" > /dev/null 2>&1; BUILT=no; fi
    if [ -n "$LOG" ]; then rm -f "$LOG"; LOG=; fi
    sudo -n chown -R "$(id -u):$(id -g)" "$OUT" 2>/dev/null
    return 0
}

# ---- 0. where this is allowed to run. Until every line below has passed, nothing is done outside proof/out and sudo is not called.
[ "$(uname -s)" = Linux ] || refuse "Linux only"
[ "${HOSTOPS_THROWAWAY_RUNNER:-}" = yes ] || refuse "HOSTOPS_THROWAWAY_RUNNER=yes is required"
[ "${GITHUB_ACTIONS:-}" = true ] || refuse "a GitHub Actions job is required"
[ "${RUNNER_ENVIRONMENT:-}" = github-hosted ] || refuse "a GitHub-hosted runner is required (RUNNER_ENVIRONMENT=${RUNNER_ENVIRONMENT:-unset})"
[ "$(id -u)" != 0 ] || refuse "start as the runner's ordinary user; root is taken with sudo -n where it is needed"
[ "$#" = 1 ] || refuse "usage: sh proof/release_image.sh <release checkout>"
RELEASE=$1
for path in /etc/c3po-bar /var/lib/c3po-bar /etc/c3po-reader /var/lib/c3po-reader /opt/chief-of-staff-digital /mnt/day-d-data /run/c3po-security "$REHEARSAL" "$REHEARSAL.docker-cli"; do
    if [ -e "$path" ] || [ -L "$path" ]; then refuse "$path exists: this is not a throwaway runner"; fi
done
mkdir -p "$OUT" || refuse "no output directory"
/usr/bin/python3 -I -B proof/seals.py > /dev/null
SEALS=$?
[ "$SEALS" = 0 ] || [ "$SEALS" = 3 ] || refuse "a seal does not hold (run proof/seals.py for the checks)"
sudo -n true || refuse "sudo -n is not available"
trap cleanup EXIT
trap 'exit 130' INT TERM HUP
say "seals verified: core $(sha256sum core/CORE_SHA256SUMS | cut -d' ' -f1), proof $(sha256sum proof/PROOF_SHA256SUMS | cut -d' ' -f1)"
# The dispatcher refuses a runtime file that group or other can write. Modes only: no sealed byte changes.
chmod -R go-w core catalog_init install_release epoch_readback activate 2> /dev/null || printf 'note: not every mode of the checkout could be set\n'
[ "$SEALS" = 0 ] || failed "a file is present in a sealed directory that its seal does not list (every sealed byte is the sealed one; proof/seals.py names it)"
rm -f "$OUT"/IMAGE.release-image.txt "$OUT"/CATALOG_SHAPE.release-image.linux-root.json "$OUT"/SHAPES.k11.release-image.linux-root.json \
      "$OUT"/RELEASE_VERIFY.release-image.linux-root.json "$OUT"/COMPOSE_RENDER.release.linux-root.json "$OUT"/SHAPES.activate.release-image.linux-root.json
ROOT_PYTHON="sudo -n env HOSTOPS_THROWAWAY_RUNNER=yes RUNNER_ENVIRONMENT=github-hosted /usr/bin/python3"

say "the checkout is the release for everything the image is built from"
TREE=$(git -C "$RELEASE" rev-parse HEAD:c3po 2> /dev/null) || TREE=
[ "$TREE" = "$C3PO_TREE" ] || refuse "c3po/ of this checkout is not the tree of the release (found ${TREE:-nothing}, expected $C3PO_TREE)"
CHANGED=$(git -C "$RELEASE" status --porcelain --untracked-files=all -- c3po 2> /dev/null) || refuse "git status of the checkout failed"
[ -z "$CHANGED" ] || refuse "c3po/ of the checkout differs from its commit"
printf 'c3po tree %s; Dockerfile %s\n' "$TREE" "$(sha256sum "$RELEASE/c3po/backend/Dockerfile" | cut -d' ' -f1)"

say "the image store must be the containerd snapshotter (the core's job step set it)"
STORE=$(sudo -n docker info --format '{{.Driver}} {{json .DriverStatus}}' 2> /dev/null) || STORE=
printf 'image store: %s\n' "$STORE"
case "$STORE" in
    *io.containerd.snapshotter.v1*) STORE_OK=yes ;;
    *) STORE_OK=no; failed "the image store is not the containerd snapshotter (run the core's linux_root/run.sh first); nothing is built and no shape is run" ;;
esac

# ---- 1. the image, as the pipeline builds it
IMAGE_ID=
if [ "$STORE_OK" = yes ]; then
    say "the backend image of the release, built from this checkout"
    if sudo -n docker image inspect "$REFERENCE" > /dev/null 2>&1 || sudo -n docker image inspect c3po/backend:production > /dev/null 2>&1; then
        refuse "an image of the production repository exists: this is not a throwaway runner"
    fi
    TOKEN=$(sha256sum "$RELEASE/c3po/security/container-rebuild-trigger.json" | cut -d' ' -f1)
    LOG=$(mktemp) || refuse "no temporary file"
    if [ -n "$TOKEN" ] && sudo -n docker build --file "$RELEASE/c3po/backend/Dockerfile" --build-arg "C3PO_SECURITY_REBUILD=$TOKEN" \
            --label "org.opencontainers.image.revision=$REVISION" --tag "$REFERENCE" "$RELEASE/c3po" > "$LOG" 2>&1; then
        BUILT=yes
        tail -n 12 "$LOG"
        IMAGE_ID=$(sudo -n docker image inspect --format '{{.Id}}' "$REFERENCE") || IMAGE_ID=
    else
        tail -n 80 "$LOG"
    fi
    case "$IMAGE_ID" in
        sha256:*) : ;;
        *) IMAGE_ID=; failed "the backend image could not be built from this checkout" ;;
    esac
fi
if [ -n "$IMAGE_ID" ]; then
    LABEL=$(sudo -n docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$REFERENCE") || LABEL=
    [ "$LABEL" = "$REVISION" ] || failed "the image does not carry the revision label of the release"
    {
        printf 'reference %s\nimage_id %s\nrevision_label %s\n' "$REFERENCE" "$IMAGE_ID" "$LABEL"
        printf 'c3po_tree %s\n' "$TREE"
        printf 'dockerfile_sha256 %s\n' "$(sha256sum "$RELEASE/c3po/backend/Dockerfile" | cut -d' ' -f1)"
        printf 'requirements_sha256 %s\n' "$(sha256sum "$RELEASE/c3po/backend/requirements.txt" | cut -d' ' -f1)"
        printf 'rebuild_token %s\n' "$TOKEN"
        sudo -n docker image inspect --format 'architecture {{.Architecture}} os {{.Os}} entrypoint {{json .Config.Entrypoint}} cmd {{json .Config.Cmd}} workdir {{json .Config.WorkingDir}}' "$REFERENCE"
        sudo -n docker version --format 'docker_client {{.Client.Version}} docker_server {{.Server.Version}}'
        printf 'compose %s\n' "$(sudo -n docker compose version --short 2> /dev/null)"
        printf 'image_store %s\n' "$STORE"
        printf 'init_binary %s\n' "$(sudo -n docker info --format '{{.InitBinary}}' 2> /dev/null)"
        printf 'python_in_the_image %s\n' "$(sudo -n docker run --rm --network none --entrypoint python "$REFERENCE" -V 2>&1)"
    } > "$OUT/IMAGE.release-image.txt" || failed "the facts of the image could not be written"
    cat "$OUT/IMAGE.release-image.txt"
    # the pipeline's own check of the runtime image: pip ran at build time and is not in the image
    sudo -n docker run --rm --network none --entrypoint python "$REFERENCE" -B -c \
        'import importlib.util, sys; absent = importlib.util.find_spec("pip") is None; print("pip absent from the runtime image:", absent); sys.exit(0 if absent else 1)' \
        || failed "the runtime image is not the one the pipeline accepts (pip present, or python did not start)"
fi
not_run "$OUT/IMAGE.release-image.txt" "the backend image was not built"

# ---- 2. K2a: the catalog initialisation with the pinned script, in the image of the release
if [ -n "$IMAGE_ID" ]; then
    say "K2a: the layout of supervisor operation 2, placement A (root:root 0700, empty), created exclusively"
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
            say "K2a: REHEARSAL, REAL, and REAL again, with the operation's own perform and Native, in the image of the release"
            $ROOT_PYTHON -I -B catalog_init/linux_root/catalog_shape.py "$IMAGE_ID" "$REVISION" > "$OUT/CATALOG_SHAPE.release-image.linux-root.json"
            SHAPE=$?
            [ "$SHAPE" = 0 ] || failed "catalog_shape.py with the image of the release: exit $SHAPE (2: a run was not made; 3: an expectation is not met)"
            sudo -n docker ps -a --format '{{.Names}} {{.State}}'
            sudo -n ls -lnR /etc/c3po-bar /var/lib/c3po-bar "$REHEARSAL" "$REHEARSAL.docker-cli"
        else
            failed "K2a: the layout could not be completed"
        fi
        sudo -n rm -rf /etc/c3po-bar /var/lib/c3po-bar "$REHEARSAL" "$REHEARSAL.docker-cli"; LAYOUT=no
    else
        failed "K2a: the layout could not be created"
    fi
fi
not_run "$OUT/CATALOG_SHAPE.release-image.linux-root.json" "no image of the release, or no layout"

# ---- 3. K11: the engine shapes of the epoch readback (the sealed script binds its stand-in package over /app)
if [ -n "$IMAGE_ID" ]; then
    say "K11: the engine shapes, in the image of the release (the alarm shape takes thirty seconds)"
    WORK_K11=$(sudo -n mktemp -d /srv/hostops02-k11-XXXXXXXX) || { WORK_K11=; failed "no work directory under /srv"; }
    if [ -n "$WORK_K11" ]; then
        $ROOT_PYTHON -B epoch_readback/linux_root/shapes_k11.py "$IMAGE_ID" "$WORK_K11" > "$OUT/SHAPES.k11.release-image.linux-root.json"
        SHAPE=$?
        [ "$SHAPE" = 0 ] || failed "shapes_k11.py with the image of the release: exit $SHAPE (2: a shape did not run; 3: an expectation is not met)"
    fi
fi
not_run "$OUT/SHAPES.k11.release-image.linux-root.json" "no image of the release, or no work directory"

# ---- 4. K11: Release.verify of the image's own application on synthetic bytes, nothing bound at /app
if [ -n "$IMAGE_ID" ]; then
    say "K11: Release.verify of the release code in fresh containers of its image, on synthetic release bytes"
    WORK_VERIFY=$(sudo -n mktemp -d /srv/hostops02-verify-XXXXXXXX) || { WORK_VERIFY=; failed "no work directory under /srv"; }
    if [ -n "$WORK_VERIFY" ]; then
        $ROOT_PYTHON -I -B proof/release_verify_shape.py "$IMAGE_ID" "$WORK_VERIFY" > "$OUT/RELEASE_VERIFY.release-image.linux-root.json"
        SHAPE=$?
        [ "$SHAPE" = 0 ] || failed "release_verify_shape.py: exit $SHAPE (2: a shape did not run; 3: an expectation is not met)"
    fi
fi
not_run "$OUT/RELEASE_VERIFY.release-image.linux-root.json" "no image of the release, or no work directory"

# ---- 5. K11 and K6a: the compose file of the release, rendered (config creates nothing) in a tree shaped like the deploy tree
if [ "$STORE_OK" = yes ]; then
    say "K11 and K6a: the render of the release's own compose file by the helpers of both sources"
    WORK_RENDER=$(sudo -n mktemp -d /srv/hostops02-render-XXXXXXXX) || { WORK_RENDER=; failed "no work directory under /srv"; }
    if [ -n "$WORK_RENDER" ]; then
        if sudo -n mkdir "$WORK_RENDER/deploy" "$WORK_RENDER/data" \
           && sudo -n cp -R "$RELEASE/c3po" "$WORK_RENDER/deploy/c3po" \
           && printf 'C3PO_DAY_D_DATA_MOUNT_SOURCE=%s/data\n' "$WORK_RENDER" | sudo -n tee "$WORK_RENDER/deploy/.env" > /dev/null \
           && sudo -n chown -R 0:0 "$WORK_RENDER" && sudo -n chmod 0600 "$WORK_RENDER/deploy/.env"; then
            printf 'compose file of the release: %s\n' "$(sudo -n sha256sum "$WORK_RENDER/deploy/c3po/compose.yml" | cut -d' ' -f1)"
            $ROOT_PYTHON -I -B proof/release_compose_render.py "$WORK_RENDER" > "$OUT/COMPOSE_RENDER.release.linux-root.json"
            SHAPE=$?
            [ "$SHAPE" = 0 ] || failed "release_compose_render.py: exit $SHAPE (2: a shape did not run; 3: an expectation is not met)"
        else
            failed "the tree of the render could not be written"
        fi
    fi
fi
not_run "$OUT/COMPOSE_RENDER.release.linux-root.json" "the image store is not the containerd snapshotter, or no work tree"

# ---- 6. K6a: activate end to end on a throwaway project whose three services run the image of the release
if [ -n "$IMAGE_ID" ]; then
    say "K6a: the trees of the throwaway project"
    WORK_K6A=$(sudo -n mktemp -d /srv/hostops02-activate-rel-XXXXXXXX) || { WORK_K6A=; failed "no work directory under /srv"; }
fi
if [ -n "$WORK_K6A" ]; then
    if sudo -n /usr/bin/python3 -I -B activate/linux_root/shapes.py --prepare "$WORK_K6A" "$REFERENCE" "$PROJECT" "$FAMILY/core/tests"; then
        # the deploy, as the pipeline makes it: from the deploy tree, the environment file and the one compose file
        say "K6a: the deploy of the throwaway project"
        UP=yes
        if ( cd "$WORK_K6A/deploy" && sudo -n env "C3PO_BUILD_SHA=$REVISION" docker compose --env-file .env -f "$PROJECT/compose.yml" up -d --no-build ); then
            sudo -n docker ps -a --format '{{.Names}} {{.State}}'
            say "K6a: the shapes, in the image of the release"
            $ROOT_PYTHON -I -B activate/linux_root/shapes.py "$IMAGE_ID" "$WORK_K6A" "$PROJECT" "$FAMILY/core/tests" > "$OUT/SHAPES.activate.release-image.linux-root.json"
            SHAPE=$?
            [ "$SHAPE" = 0 ] || failed "activate shapes.py with the image of the release: exit $SHAPE (2: a shape did not run; 3: an expectation is not met)"
            sudo -n docker ps -a --format '{{.Names}} {{.State}}'
        else
            failed "K6a: the throwaway project could not be started"
        fi
    else
        failed "K6a: the trees could not be written"
    fi
fi
not_run "$OUT/SHAPES.activate.release-image.linux-root.json" "no image of the release, no work tree, or the project did not start"

cleanup
say "seals after the run"
/usr/bin/python3 -I -B proof/seals.py | tail -n 1
/usr/bin/python3 -I -B proof/seals.py > /dev/null || failed "a seal check does not hold after the run (run proof/seals.py for the checks)"
ls -ln "$OUT"
say "exit status $STATUS"
exit "$STATUS"
