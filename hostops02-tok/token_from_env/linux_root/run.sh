#!/bin/sh
# The token placement on Linux as real root, on a real filesystem. For a THROWAWAY GitHub-hosted ubuntu-24.04 runner
# only. NEVER the production host and never a self-hosted runner: this runs the suites as uid 0, CREATES /etc/c3po-bar
# (the layout of supervisor operation 2) and a fake deploy tree in /opt, mounts a small tmpfs on /etc/c3po-bar for one
# shape, and REMOVES all of it again. Before the shapes it makes /opt itself root:root 0755, as the production host has
# it (stage 3; the runner image leaves /opt writable by every user), and does not set it back: the runner is discarded.
# Stage 3a sets kernel.core_pattern for a while (to a pipe into a small collector of its own, then to a file path) and
# puts the runner's own value back, whatever happened; it starts and kills child interpreters to see what is dumped.
# No shape needs the network, and no docker command is run as root; the job itself uses the network once, to install
# python3-pytest from the distribution (apt-get, as the core's run.sh does), and runs `docker compose config` as the
# runner's user in stage 4 (nothing pulled, created or started). No value of any provider is used: every token is fake.
# It refuses unless GitHub says the runner is GitHub-hosted, and unless nothing of this family exists on the machine; it
# removes only what this very run created.
# NOT RUN by its author: no Linux and no root were available offline. Revision 2 of this file ran once on a runner
# (run 37150103273); revision 2c adds the /opt step of stage 3, after that run; revision 3 (the process made
# non-dumpable, CONTRACT D9) adds stage 3a and the core copy of the token family beside this directory (../core).
#
# usage: sh linux_root/run.sh      (from the operation directory hostops02-tok/token_from_env; its core is ../core)
# Stages, each run whatever the earlier ones did (the status is kept and returned):
#   1. the seal of this directory and of its core (../core), and build/ is what that core assembles
#   2. the core's suite and this operation's suite as REAL root and as the runner's user (junit files)
#   3a. linux_root/dump_proof.py as root: kernel.core_pattern shown, set to a pipe into a test collector and then to an
#      absolute file path; a dumpable child interpreter killed by SIGQUIT and by SIGSEGV is dumped (the collector or
#      the file receives its memory), the same child after the source's own Native().not_dumpable() dies by the same
#      signals and nothing is dumped; the runner's core_pattern put back and shown again (SHAPES ...dumps file)
#   3. / and /opt shown as found, /opt made root:root 0755 (the production layout) and both shown again; then
#      linux_root/token_shape.py as root: the operation's own run() and Native on the real filesystem (SHAPES file),
#      only when / and /opt are then owned by uid 0 and not writable by group or other; the dumpable attribute of
#      that process before its first run and after it
#   4. linux_root/token_shape.py --compose-agreement as the runner's user: what docker compose makes of every listed
#      file and of 500 generated files the parser accepts (config only; nothing pulled, created or started); a
#      required stage: without docker compose it fails
#   5. the seals again
# Output, always written, in linux_root/: TESTS.core.linux-{root,user}.xml TESTS.token_from_env.linux-{root,user}.xml
# SHAPES.token_from_env.dumps.json SHAPES.token_from_env.linux-root.json SHAPES.token_from_env.compose.json (a stage
# that did not run leaves a file that says NOT_RUN and why). Exit 0 only when every stage passed.
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
/usr/bin/python3 -B ../core/assemble.py --check . || refuse "build/ is not what its core (../core) assembles"
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

# ---- 3a. What the kernel dumps of a crash, before and after the source's protection (revision 3, CONTRACT D9). The
# production host pipes core dumps to a crash collector (its precheck receipt), and RLIMIT_CORE does not stop a pipe.
# dump_proof.py reads the runner's kernel.core_pattern, sets its own (a pipe into a collector in a private temporary
# directory, then a file path there), kills its children, and puts the runner's value back in a finally clause; this
# stage also compares the value before and after and puts it back itself if it differs. It is the runner's value, not
# the production host's.
say "3a. kernel.core_pattern of this runner as found, the dump proof as real root, and kernel.core_pattern again"
PATTERN_BEFORE=$(cat /proc/sys/kernel/core_pattern) || failed "kernel.core_pattern cannot be read"
printf 'kernel.core_pattern before: %s\n' "$PATTERN_BEFORE"
if [ "${HOSTOPS_THROWAWAY_RUNNER:-}" = yes ]; then
    sudo -n env HOSTOPS_THROWAWAY_RUNNER=yes RUNNER_ENVIRONMENT=github-hosted /usr/bin/python3 -I -B linux_root/dump_proof.py > "$OUT/SHAPES.token_from_env.dumps.json"
    DUMPS=$?
    [ "$DUMPS" = 0 ] || failed "dump_proof.py exit $DUMPS (2: a case did not run; 3: an expectation is not met)"
else
    failed "HOSTOPS_THROWAWAY_RUNNER is not yes: the dump proof is NOT run"
fi
not_run "$OUT/SHAPES.token_from_env.dumps.json" "dump_proof.py wrote nothing"
PATTERN_AFTER=$(cat /proc/sys/kernel/core_pattern) || failed "kernel.core_pattern cannot be read again"
printf 'kernel.core_pattern after:  %s\n' "$PATTERN_AFTER"
if [ "$PATTERN_AFTER" != "$PATTERN_BEFORE" ]; then
    failed "kernel.core_pattern was not put back by dump_proof.py"
    printf '%s\n' "$PATTERN_BEFORE" | sudo -n tee /proc/sys/kernel/core_pattern > /dev/null || failed "kernel.core_pattern cannot be put back"
    printf 'kernel.core_pattern put back by this stage: %s\n' "$(cat /proc/sys/kernel/core_pattern)"
fi

# ---- 3, first: what lies above the fake deploy tree, made what the production host has (revision 2c of the operation).
# The program walks "/", /opt and the deploy directory and refuses unless every component ABOVE the deploy directory is
# owned by uid 0 and not writable by group or other (the core's row_root_safe and row_accepted, parts/core.py and
# parts/parents.py), with DEPLOY_CHAIN_UNSAFE_ABOVE_THE_DEPLOY_DIRECTORY. That is by design and is not relaxed here. The runner image makes /opt
# writable by every user (its tool cache lives below it), so on the runner every shape was refused at PRECHECK (run
# 37150103273, revision 2); the production deploy directory is /opt/chief-of-staff-digital, below a standard /opt of
# root:root 0755. On this throwaway runner only (stage 0 has already refused anything else), / and /opt are shown as
# found, /opt alone is made root:root 0755 (not recursive: nothing below it changes; "/" is never touched), both are
# shown again, and the shapes run only when both then meet the program's own rule; otherwise the stage fails and the
# shapes are not run. The refusal itself stays proved: of a world-writable deploy directory by a shape below, of a
# group-writable or foreign-owned /opt by the suites of stage 2 (emulated, and by real system calls).
root_safe() {   # root_safe <path>: owned by uid 0 and no write bit for group or other, the program's rule
    owner=$(stat -c %u "$1") && mode=$(stat -c %a "$1") || return 1
    case "$owner" in ''|*[!0-9]*) return 1 ;; esac
    case "$mode" in ''|*[!0-7]*) return 1 ;; esac
    [ "$owner" = 0 ] && [ $(( 0$mode & 022 )) = 0 ]
}
say "3. / and /opt as found, then as the production host has them (owned by uid 0, not writable by group or other)"
ABOVE=refused
if [ "${HOSTOPS_THROWAWAY_RUNNER:-}" = yes ]; then
    for path in / /opt; do printf 'as found: '; stat -c '%n uid %u gid %g mode %a' "$path" || failed "stat $path"; done
    { sudo -n chown 0:0 /opt && sudo -n chmod 0755 /opt; } || failed "/opt cannot be made root:root 0755"
    for path in / /opt; do printf 'as set:   '; stat -c '%n uid %u gid %g mode %a' "$path" || failed "stat $path"; done
    ABOVE=safe
    for path in / /opt; do
        root_safe "$path" || { ABOVE=refused; failed "$path is still not owned by uid 0 without write for group or other: the program would refuse every shape, and the shapes are NOT run"; }
    done
else
    failed "HOSTOPS_THROWAWAY_RUNNER is not yes: /opt is not changed, and the shapes are NOT run"
fi

say "3. the shapes as real root on the real filesystem (the layout and the fake deploy tree are created and removed by the script)"
if [ "$ABOVE" = safe ]; then
    sudo -n env HOSTOPS_THROWAWAY_RUNNER=yes RUNNER_ENVIRONMENT=github-hosted /usr/bin/python3 -I -B linux_root/token_shape.py "$(id -u)" > "$OUT/SHAPES.token_from_env.linux-root.json"
    SHAPES=$?
    [ "$SHAPES" = 0 ] || failed "token_shape.py exit $SHAPES (2: a shape did not run; 3: an expectation is not met)"
    not_run "$OUT/SHAPES.token_from_env.linux-root.json" "token_shape.py wrote nothing"
else
    not_run "$OUT/SHAPES.token_from_env.linux-root.json" "/ or /opt is not owned by uid 0 without write for group or other (the production layout): the shapes were not run"
fi
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
