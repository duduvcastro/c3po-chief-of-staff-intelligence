#!/bin/sh
# HOSTOPS02 core, and the operations named as arguments, on Linux as real root. For a THROWAWAY GitHub-hosted
# ubuntu-24.04 runner only (ext4, Python 3.12, systemd 255, Docker). NEVER the production host and never a self-hosted
# runner: this runs the suites as uid 0, rewrites /etc/docker/daemon.json and restarts the Docker daemon, pulls an
# image, adds one image tag, runs containers and one compose project. It refuses unless GitHub says the runner is
# GitHub-hosted, and unless nothing of this family exists on the machine.
# NOT RUN by the author of the core: no Linux and no docker were available offline. The same structure as the
# HOSTOPS01 job that passed (linux_root/run.sh of that candidate), with the unit steps removed and the core's shapes.
#
# usage: sh linux_root/run.sh [<operation directory> ...]      (from the core directory; operation directories relative to it)
# What it closes when it has run and exited 0: CORE.md section 10, items U1 to U7, for the core; and, for each
# operation directory given, that its build is the assembly of this core and that its own suite passes as root and
# as the runner's user.
# Output, always written, in linux_root/: TESTS.linux-root.xml TESTS.linux-user.xml SHAPES.linux-root.json, and for each
# operation TESTS.<name>.linux-root.xml and TESTS.<name>.linux-user.xml (a stage that did not run leaves a file that
# says NOT_RUN and why). Exit 0 only when: the seal holds before and after; every suite passes as root and as the
# user; the image store is the containerd snapshotter before anything is pulled; every shape ran; every expectation of
# shapes.py is met. Every stage runs whatever the earlier ones did; the status is kept and returned.
# Nothing here relies on "set -e": every status is tested where it is produced.
set -u
umask 022
cd "$(dirname "$0")/.." || exit 1
OUT=linux_root
STATUS=0
WORK=
PROJECT=hostops02ci
REFERENCE=c3po/backend:hostops02-ci-probe
TAGGED=no
say() { printf '\n== %s\n' "$*"; }
failed() { printf 'FAILED: %s\n' "$*" >&2; STATUS=1; }
refuse() { printf 'REFUSED: %s\n' "$*" >&2; exit 1; }
not_run() { [ -s "$1" ] || printf 'NOT_RUN: %s\n' "$2" > "$1"; }

cleanup() {
    if [ -n "$WORK" ]; then
        # the one compose project and whatever this job left of it; nothing else on the runner is touched
        sudo -n docker compose --project-name "$PROJECT" --env-file "$WORK/project/.env" -f "$WORK/project/compose.yml" down --timeout 2 > /dev/null 2>&1
        sudo -n rm -rf "$WORK"; WORK=
    fi
    if [ "$TAGGED" = yes ]; then sudo -n docker image rm "$REFERENCE" > /dev/null 2>&1; TAGGED=no; fi
    sudo -n chown "$(id -u):$(id -g)" "$OUT"/*.xml "$OUT"/SHAPES.linux-root.json 2>/dev/null
    return 0
}

# ---- 0. where this is allowed to run. Until every line below has passed, nothing is done and sudo is not called.
[ "$(uname -s)" = Linux ] || refuse "Linux only"
[ "${HOSTOPS_THROWAWAY_RUNNER:-}" = yes ] || refuse "HOSTOPS_THROWAWAY_RUNNER=yes is required"
[ "${GITHUB_ACTIONS:-}" = true ] || refuse "a GitHub Actions job is required"
[ "${RUNNER_ENVIRONMENT:-}" = github-hosted ] || refuse "a GitHub-hosted runner is required (RUNNER_ENVIRONMENT=${RUNNER_ENVIRONMENT:-unset})"
[ "$(id -u)" != 0 ] || refuse "start as the runner's ordinary user; root is taken with sudo -n where it is needed"
for path in /etc/c3po-bar /var/lib/c3po-bar /etc/c3po-reader /var/lib/c3po-reader /opt/chief-of-staff-digital /mnt/day-d-data; do
    if [ -e "$path" ] || [ -L "$path" ]; then refuse "$path exists: this is not a throwaway runner"; fi
done
sha256sum -c --quiet CORE_SHA256SUMS || refuse "the core is not the sealed one"
sudo -n true || refuse "sudo -n is not available"
trap cleanup EXIT
trap 'exit 130' INT TERM HUP
say "seal verified: $(sha256sum CORE_SHA256SUMS | cut -d' ' -f1) ($(wc -l < CORE_SHA256SUMS) files); generation $(/usr/bin/python3 -B assemble.py --core)"
# The dispatcher refuses a runtime file that group or other can write; a checkout made under umask 002 has such files.
# Modes only: no byte of the sealed core changes (the seal is verified again at the end).
chmod -R go-w . || refuse "the modes of the checkout cannot be set"
for operation in "$@"; do chmod -R go-w "$operation" || refuse "the modes of $operation cannot be set"; done
rm -f "$OUT"/TESTS.*.xml "$OUT"/SHAPES.linux-root.json

# ---- pytest of the distribution for /usr/bin/python3, the interpreter the remote command names (no pip: PEP 668)
say "python3-pytest"
LOG=$(mktemp) || refuse "no temporary file"
sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends python3-pytest > "$LOG" 2>&1 \
    || { sudo -n apt-get update -q >> "$LOG" 2>&1
         sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends python3-pytest >> "$LOG" 2>&1; } \
    || { tail -n 40 "$LOG"; refuse "python3-pytest cannot be installed"; }
rm -f "$LOG"
/usr/bin/python3 -B -m pytest --version || refuse "pytest is not importable by /usr/bin/python3"
sudo -n /usr/bin/python3 -B -m pytest --version || refuse "pytest is not importable by /usr/bin/python3 as root"
/usr/bin/python3 -V; uname -sr; findmnt -n -o FSTYPE,TARGET -T /tmp; findmnt -n -o FSTYPE,TARGET -T .

suite() {   # suite <directory that holds tests/> <label>: as real root, then as the runner's user
    say "U1: the suite of $1 as real root"
    ( cd "$1" && sudo -n env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B -W error::SyntaxWarning -m pytest -p no:cacheprovider -q -rfEs tests \
        --junitxml "$ROOT_OF_CORE/$OUT/TESTS.$2linux-root.xml" -o junit_family=xunit2 ) || failed "the suite of $1 as real root"
    sudo -n chown "$(id -u):$(id -g)" "$OUT/TESTS.$2linux-root.xml" 2>/dev/null
    not_run "$OUT/TESTS.$2linux-root.xml" "pytest wrote no junit file as root"
    say "the suite of $1 as the runner's user (uid $(id -u))"
    ( cd "$1" && env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B -W error::SyntaxWarning -m pytest -p no:cacheprovider -q -rfEs tests \
        --junitxml "$ROOT_OF_CORE/$OUT/TESTS.$2linux-user.xml" -o junit_family=xunit2 ) || failed "the suite of $1 as the runner's user"
    not_run "$OUT/TESTS.$2linux-user.xml" "pytest wrote no junit file as the user"
}
ROOT_OF_CORE=$(pwd)
suite . ""
for operation in "$@"; do
    name=$(basename "$operation")
    say "$name: the build is the assembly of this core"
    /usr/bin/python3 -B assemble.py --check "$operation" || failed "$name: build/ is not what assemble.py writes"
    suite "$operation" "$name."
done

# ---- the image store of the production host: the containerd snapshotter, BEFORE any image is pulled.
say "the containerd image store"
STORE=
if sudo -n /usr/bin/python3 -I -B - <<'DAEMON'
import json,os
path='/etc/docker/daemon.json'
try:
    with open(path,encoding='utf-8') as handle:config=json.load(handle)
except FileNotFoundError:config={}
if type(config) is not dict or type(config.setdefault('features',{})) is not dict:raise SystemExit('daemon.json is not what this script can extend')
config['features']['containerd-snapshotter']=True
os.makedirs('/etc/docker',mode=0o755,exist_ok=True)
with open(path,'w',encoding='utf-8') as handle:handle.write(json.dumps(config,indent=1,sort_keys=True)+'\n')
print('daemon.json keys:',sorted(config),'features:',config['features'])
DAEMON
then
    sudo -n systemctl restart docker || failed "docker did not restart"
    tries=0
    until sudo -n docker info > /dev/null 2>&1; do
        tries=$((tries+1)); [ "$tries" -le 30 ] || break; sleep 2
    done
    STORE=$(sudo -n docker info --format '{{.Driver}} {{json .DriverStatus}}' 2>/dev/null) || STORE=
    sudo -n docker version --format 'docker client {{.Client.Version}} server {{.Server.Version}}'
    sudo -n docker compose version
    printf 'image store: %s\n' "$STORE"
else
    failed "daemon.json could not be written"
fi
case "$STORE" in
    *io.containerd.snapshotter.v1*) STORE_OK=yes ;;
    *) STORE_OK=no; failed "the image store is not the containerd snapshotter; nothing is pulled and no shape is run" ;;
esac

# ---- U2 to U7: the shapes, with a throwaway image that has python and a throwaway compose project.
IMAGE_ID=
if [ "$STORE_OK" = yes ]; then
    say "a throwaway image with python under $REFERENCE"
    if sudo -n docker image inspect "$REFERENCE" > /dev/null 2>&1 || sudo -n docker image inspect c3po/backend:production > /dev/null 2>&1; then
        refuse "an image of the production repository exists: this is not a throwaway runner"
    fi
    BASE=
    for candidate in python:3.12-slim public.ecr.aws/docker/library/python:3.12-slim; do
        if sudo -n docker pull -q "$candidate" > /dev/null; then BASE=$candidate; break; fi
    done
    if [ -n "$BASE" ] && sudo -n docker image tag "$BASE" "$REFERENCE"; then
        TAGGED=yes
        IMAGE_ID=$(sudo -n docker image inspect --format '{{.Id}}' "$REFERENCE") || IMAGE_ID=
    fi
    case "$IMAGE_ID" in
        sha256:*) printf 'image: %s as %s, ID %s\n' "$BASE" "$REFERENCE" "$IMAGE_ID" ;;
        *) IMAGE_ID=; failed "no throwaway image could be pulled and tagged" ;;
    esac
fi
if [ -n "$IMAGE_ID" ]; then
    say "the work tree of the shapes (root:root, private)"
    WORK=$(sudo -n mktemp -d /var/tmp/hostops02-shapes-XXXXXXXX) || { WORK=; failed "no work directory"; }
fi
if [ -n "$WORK" ]; then
    if sudo -n /usr/bin/python3 -I -B - "$WORK" "$REFERENCE" <<'TREE'
import json,os,sys
work,reference=sys.argv[1:3];os.umask(0o077)
for name in ('bound','written','docker-cli','project'):os.mkdir(os.path.join(work,name),0o700)
def put(path,text,mode):
    fd=os.open(os.path.join(work,path),os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode);os.write(fd,text.encode());os.fchmod(fd,mode);os.close(fd)
put('bound/one-file','x\n',0o600)
put('project/.env','MARKER=from-env-file\n',0o600)
put('project/compose.yml','services:\n  r2d2-worker:\n    image: %s\n    command: ["python","-c","import time; time.sleep(3600)"]\n    stop_grace_period: 1s\n'
    '    environment:\n      C3PO_BUILD_SHA: ${C3PO_BUILD_SHA:-development}\n      FROM_ENV_FILE: ${MARKER:-unset}\n'%reference,0o644)
put('project/override.json',json.dumps({'services':{'r2d2-worker':{'environment':{'C3PO_R2D2_V2_LIVE_POLICY_FILE':'/app/day-d-data/live/policy.json',
    'C3PO_R2D2_V2_LIVE_POLICY_SHA':'5'*64}}}},sort_keys=True,separators=(',',':')),0o600)
put('project/deployment.lock','',0o644)
os.chmod(work,0o700)
TREE
    then
        say "U2 to U7: the shapes"
        sudo -n env HOSTOPS_THROWAWAY_RUNNER=yes RUNNER_ENVIRONMENT=github-hosted /usr/bin/python3 -I -B linux_root/shapes.py "$IMAGE_ID" "$WORK" > "$OUT/SHAPES.linux-root.json"
        SHAPES=$?
        [ "$SHAPES" = 0 ] || failed "shapes.py exit $SHAPES (2: a shape did not run; 3: an expectation is not met)"
        sudo -n docker ps -a --format '{{.Names}} {{.State}}'
    else
        failed "the work tree could not be written"
    fi
fi
not_run "$OUT/SHAPES.linux-root.json" "no throwaway image under the containerd image store, or no work tree"

cleanup
say "seal after the run"
sha256sum -c --quiet CORE_SHA256SUMS || failed "a file of the sealed core changed during the run"
ls -ln "$OUT"
say "exit status $STATUS"
exit "$STATUS"
