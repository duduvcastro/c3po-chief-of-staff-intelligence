#!/bin/sh
# The token placement on Linux as real root, on a real filesystem. For a THROWAWAY GitHub-hosted ubuntu-24.04 runner
# only. NEVER the production host and never a self-hosted runner: this runs the suites as uid 0, CREATES /etc/c3po-bar
# (the layout of supervisor operation 2) and a fake deploy tree in /opt, mounts a small tmpfs on /etc/c3po-bar for one
# shape, and REMOVES all of it again. No shape needs the network, and no docker command is run as root; the job itself
# uses the network once, to install python3-pytest from the distribution (apt-get, as the core's run.sh does), and runs
# `docker compose config` as the runner's user in stage 4 (nothing pulled, created or started). No value of any
# provider is used: every token is fake. It refuses unless GitHub says the runner is GitHub-hosted, and unless nothing
# of this family exists on the machine; it removes only what this very run created.
# NOT RUN by its author: no Linux and no root were available offline.
#
# usage: sh linux_root/run.sh      (from the operation directory hostops02/token_from_env)
# Stages, each run whatever the earlier ones did (the status is kept and returned):
#   1. the seal of this directory and of the core, and build/ is what the frozen core assembles
#   2. the core's suite and this operation's suite as REAL root and as the runner's user (junit files)
#   3. linux_root/token_shape.py as root: the operation's own run() and Native on the real filesystem (SHAPES file)
#   4. linux_root/token_shape.py --compose-agreement as the runner's user: what docker compose makes of every listed
#      file and of 500 generated files the parser accepts (config only; nothing pulled, created or started); a
#      required stage: without docker compose it fails
#   5. the seals again
# Output, always written, in linux_root/: TESTS.core.linux-{root,user}.xml TESTS.token_from_env.linux-{root,user}.xml
# SHAPES.token_from_env.linux-root.json SHAPES.token_from_env.compose.json (a stage that did not run leaves a file that
# says NOT_RUN and why). Exit 0 only when every stage passed.
# Nothing here relies on "set -e": every status is tested where it is produced.
set -u
umask 022
cd "$(dirname "$0")/.." || exit 1
OUT=linux_root
STATUS=0
DEPLOY=/opt/hostops02-token-ci
say() { printf '\n== %s\n' "$*"; }
failed() { printf 'FAILED: %s\n' "$*" >&2; STATUS=1; }
refuse() { printf 'REFUSED: %s\n' "$*" >&2; exit 1; }
not_run() { [ -s "$1" ] || printf 'NOT_RUN: %s\n' "$2" > "$1"; }
cleanup() {
    # token_shape.py removes what it created; this only gives the outputs back to the runner's user
    sudo -n chown "$(id -u):$(id -g)" "$OUT"/TESTS.*.xml "$OUT"/SHAPES.*.json 2>/dev/null
    return 0
}

# ---- 0. where this is allowed to run. Until every line below has passed, nothing is done and sudo is not called.
[ "$(uname -s)" = Linux ] || refuse "Linux only"
[ "${HOSTOPS_THROWAWAY_RUNNER:-}" = yes ] || refuse "HOSTOPS_THROWAWAY_RUNNER=yes is required"
[ "${GITHUB_ACTIONS:-}" = true ] || refuse "a GitHub Actions job is required"
[ "${RUNNER_ENVIRONMENT:-}" = github-hosted ] || refuse "a GitHub-hosted runner is required (RUNNER_ENVIRONMENT=${RUNNER_ENVIRONMENT:-unset})"
[ "$(id -u)" != 0 ] || refuse "start as the runner's ordinary user; root is taken with sudo -n where it is needed"
[ "$#" = 0 ] || refuse "usage: sh linux_root/run.sh"
for path in /etc/c3po-bar /var/lib/c3po-bar /etc/c3po-reader /var/lib/c3po-reader /opt/chief-of-staff-digital /mnt/day-d-data "$DEPLOY"; do
    if [ -e "$path" ] || [ -L "$path" ]; then refuse "$path exists: this is not a throwaway runner"; fi
done
say "1. the seals and the assembly"
sha256sum -c --quiet SHA256SUMS || refuse "the operation directory is not the sealed one"
( cd ../core && sha256sum -c --quiet CORE_SHA256SUMS ) || refuse "the core is not the sealed one"
/usr/bin/python3 -B ../core/assemble.py --check . || refuse "build/ is not what the frozen core assembles"
sudo -n true || refuse "sudo -n is not available"
trap cleanup EXIT
trap 'exit 130' INT TERM HUP
# The dispatcher refuses a runtime file that group or other can write; a checkout made under umask 002 has such files.
# Modes only: no byte of a sealed directory changes (the seals are verified again at the end).
chmod -R go-w . ../core || refuse "the modes of the checkout cannot be set"
rm -f "$OUT"/TESTS.*.xml "$OUT"/SHAPES.*.json

say "python3-pytest of the distribution, for /usr/bin/python3 (the interpreter the remote command names)"
LOG=$(mktemp) || refuse "no temporary file"
sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends python3-pytest > "$LOG" 2>&1 \
    || { sudo -n apt-get update -q >> "$LOG" 2>&1
         sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends python3-pytest >> "$LOG" 2>&1; } \
    || { tail -n 40 "$LOG"; refuse "python3-pytest cannot be installed"; }
rm -f "$LOG"
/usr/bin/python3 -B -m pytest --version || refuse "pytest is not importable by /usr/bin/python3"
/usr/bin/python3 -V; uname -sr; findmnt -n -o FSTYPE,TARGET -T /etc; findmnt -n -o FSTYPE,TARGET -T /opt; findmnt -n -o FSTYPE,OPTIONS -T /opt

suite() {   # suite <directory that holds tests/> <label>: as real root, then as the runner's user
    say "2. the suite of $1 as real root"
    ( cd "$1" && sudo -n env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B -W error::SyntaxWarning -m pytest -p no:cacheprovider -q -rfEs tests \
        --junitxml "$HERE/$OUT/TESTS.$2.linux-root.xml" -o junit_family=xunit2 ) || failed "the suite of $1 as real root"
    sudo -n chown "$(id -u):$(id -g)" "$OUT/TESTS.$2.linux-root.xml" 2>/dev/null
    not_run "$OUT/TESTS.$2.linux-root.xml" "pytest wrote no junit file as root"
    say "2. the suite of $1 as the runner's user (uid $(id -u))"
    ( cd "$1" && env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B -W error::SyntaxWarning -m pytest -p no:cacheprovider -q -rfEs tests \
        --junitxml "$HERE/$OUT/TESTS.$2.linux-user.xml" -o junit_family=xunit2 ) || failed "the suite of $1 as the runner's user"
    not_run "$OUT/TESTS.$2.linux-user.xml" "pytest wrote no junit file as the user"
}
HERE=$(pwd)
suite ../core core
suite . token_from_env

say "3. the shapes as real root on the real filesystem (the layout and the fake deploy tree are created and removed by the script)"
sudo -n env HOSTOPS_THROWAWAY_RUNNER=yes RUNNER_ENVIRONMENT=github-hosted /usr/bin/python3 -I -B linux_root/token_shape.py "$(id -u)" > "$OUT/SHAPES.token_from_env.linux-root.json"
SHAPES=$?
[ "$SHAPES" = 0 ] || failed "token_shape.py exit $SHAPES (2: a shape did not run; 3: an expectation is not met)"
not_run "$OUT/SHAPES.token_from_env.linux-root.json" "token_shape.py wrote nothing"
for path in /etc/c3po-bar "$DEPLOY"; do
    if [ -e "$path" ] || [ -L "$path" ]; then failed "$path is still there after the shapes"; fi
done
if findmnt -n /etc/c3po-bar > /dev/null 2>&1; then failed "a filesystem is still mounted on /etc/c3po-bar"; fi

say "4. what docker compose makes of the same files (as the runner's user; config only)"
if docker compose version > /dev/null 2>&1; then
    docker compose version
    HOSTOPS_THROWAWAY_RUNNER=yes RUNNER_ENVIRONMENT=github-hosted /usr/bin/python3 -I -B linux_root/token_shape.py --compose-agreement > "$OUT/SHAPES.token_from_env.compose.json"
    AGREEMENT=$?
    [ "$AGREEMENT" = 0 ] || failed "token_shape.py --compose-agreement exit $AGREEMENT (2: compose did not run; 3: compose disagrees with the parser on a file the parser accepts, or refuses a listed one)"
else
    printf 'NOT_RUN: docker compose is not available on this runner; the agreement with compose is not shown\n' > "$OUT/SHAPES.token_from_env.compose.json"
    failed "docker compose is not available: the agreement with compose is a required stage"
fi
not_run "$OUT/SHAPES.token_from_env.compose.json" "token_shape.py --compose-agreement wrote nothing"

cleanup
say "5. the seals after the run"
sha256sum -c --quiet SHA256SUMS || failed "a file of the sealed operation directory changed during the run"
( cd ../core && sha256sum -c --quiet CORE_SHA256SUMS ) || failed "a file of the sealed core changed during the run"
ls -ln "$OUT"
say "exit status $STATUS"
exit "$STATUS"
