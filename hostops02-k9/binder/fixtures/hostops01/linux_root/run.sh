#!/bin/sh
# HOSTOPS01 on Linux as real root. For a THROWAWAY GitHub-hosted ubuntu-24.04 runner only (ext4, Python 3.12,
# systemd 255, Docker). NEVER the production host and never a self-hosted runner: this runs the whole suite as uid 0,
# rewrites /etc/docker/daemon.json and restarts the Docker daemon, pulls an image, adds two image tags, installs two
# throwaway unit files named c3po-massive.* and reloads the manager. It refuses unless GitHub says the runner is
# GitHub-hosted, and unless nothing of the supervisor exists on the machine.
# NOT RUN by the author of this candidate: no Linux, no docker and no systemd were available offline.
#
# What it closes when it has run and exited 0: CONTRACT section 16 "still unproven", items L1 to L6.
# Output, always written, in linux_root/: TESTS.linux-root.xml TESTS.linux-user.xml SHAPES.linux-root.json
# VERIFY.linux-root.txt (a stage that did not run leaves a file that says NOT_RUN and why).
# Exit 0 only when: the seal holds before and after; the suite passes as root and as the runner's user; the image
# store is the containerd snapshotter before anything is pulled; every shape ran; every expectation of shapes.py is
# met. Every stage runs whatever the earlier ones did, so one run shows everything; the status is kept and returned.
# Nothing here relies on "set -e": every status is tested where it is produced.
set -u
umask 022
cd "$(dirname "$0")/.." || exit 1
OUT=linux_root
UNITS=/etc/systemd/system
STATUS=0
INSTALLED=no
WORK=
say() { printf '\n== %s\n' "$*"; }
failed() { printf 'FAILED: %s\n' "$*" >&2; STATUS=1; }
refuse() { printf 'REFUSED: %s\n' "$*" >&2; exit 1; }
not_run() { [ -s "$1" ] || printf 'NOT_RUN: %s\n' "$2" > "$1"; }

cleanup() {
    if [ "$INSTALLED" = yes ]; then
        sudo -n rm -f "$UNITS/c3po-massive.service" "$UNITS/c3po-massive.timer"   # the two files this script installed
        sudo -n systemctl daemon-reload
        INSTALLED=no
    fi
    if [ -n "$WORK" ]; then rm -rf "$WORK"; WORK=; fi
    # what the root stages wrote inside the checkout belongs to the runner's user again
    sudo -n chown "$(id -u):$(id -g)" "$OUT"/TESTS.linux-root.xml 2>/dev/null
    return 0
}

# ---- 0. where this is allowed to run. Until every line below has passed, nothing is done and sudo is not called.
[ "$(uname -s)" = Linux ] || refuse "Linux only"
[ "${HOSTOPS_THROWAWAY_RUNNER:-}" = yes ] || refuse "HOSTOPS_THROWAWAY_RUNNER=yes is required"
[ "${GITHUB_ACTIONS:-}" = true ] || refuse "a GitHub Actions job is required"
[ "${RUNNER_ENVIRONMENT:-}" = github-hosted ] || refuse "a GitHub-hosted runner is required (RUNNER_ENVIRONMENT=${RUNNER_ENVIRONMENT:-unset})"
[ "$(id -u)" != 0 ] || refuse "start as the runner's ordinary user; root is taken with sudo -n where it is needed"
for path in "$UNITS/c3po-massive.service" "$UNITS/c3po-massive.timer" /etc/c3po-bar /var/lib/c3po-bar /etc/c3po-reader /var/lib/c3po-reader; do
    if [ -e "$path" ] || [ -L "$path" ]; then refuse "$path exists: this is not a throwaway runner"; fi
done
sha256sum -c --quiet SHA256SUMS || refuse "the candidate is not the sealed one"
sudo -n true || refuse "sudo -n is not available"
trap cleanup EXIT
trap 'exit 130' INT TERM HUP
say "seal verified: $(sha256sum SHA256SUMS | cut -d' ' -f1) ($(wc -l < SHA256SUMS) files)"
# The dispatcher refuses a runtime file that group or other can write; a checkout made under umask 002 has such files.
# Modes only: no byte of the sealed candidate changes (the seal is verified again at the end).
chmod -R go-w . || refuse "the modes of the checkout cannot be set"
rm -f "$OUT"/TESTS.linux-root.xml "$OUT"/TESTS.linux-user.xml "$OUT"/SHAPES.linux-root.json "$OUT"/VERIFY.linux-root.txt
WORK=$(mktemp -d) || refuse "no temporary directory"

# ---- pytest of the distribution for /usr/bin/python3, the interpreter the remote command names (no pip: PEP 668)
say "python3-pytest"
sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends python3-pytest > "$WORK/apt.log" 2>&1 \
    || { sudo -n apt-get update -q >> "$WORK/apt.log" 2>&1
         sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends python3-pytest >> "$WORK/apt.log" 2>&1; } \
    || { tail -n 40 "$WORK/apt.log"; refuse "python3-pytest cannot be installed"; }
/usr/bin/python3 -B -m pytest --version || refuse "pytest is not importable by /usr/bin/python3"
sudo -n /usr/bin/python3 -B -m pytest --version || refuse "pytest is not importable by /usr/bin/python3 as root"
/usr/bin/python3 -V; uname -sr; findmnt -n -o FSTYPE,TARGET -T /tmp; findmnt -n -o FSTYPE,TARGET -T .

# ---- L1 the suite as real root: uid 0 without any mapping, the kernel's O_NOATIME, Linux errno values.
# No bytecode and no cache are written, so the only thing root leaves in the checkout is its junit file.
say "L1: the suite as real root"
sudo -n env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B -W error::SyntaxWarning -m pytest -p no:cacheprovider -q -rfEs tests \
     --junitxml "$OUT/TESTS.linux-root.xml" -o junit_family=xunit2 || failed "L1: the suite as real root"
sudo -n chown "$(id -u):$(id -g)" "$OUT"/TESTS.linux-root.xml 2>/dev/null
not_run "$OUT/TESTS.linux-root.xml" "pytest wrote no junit file as root"

# ---- L2 the same suite as the runner's ordinary user (O_NOATIME as the owner of the tree, EACCES of Linux).
say "L2: the suite as the runner's user (uid $(id -u))"
env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B -W error::SyntaxWarning -m pytest -p no:cacheprovider -q -rfEs tests \
     --junitxml "$OUT/TESTS.linux-user.xml" -o junit_family=xunit2 || failed "L2: the suite as the runner's user"
not_run "$OUT/TESTS.linux-user.xml" "pytest wrote no junit file as the user"

# ---- the image store of the production host: the containerd snapshotter, BEFORE any image is pulled.
say "L3: the containerd image store"
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
    printf 'image store: %s\n' "$STORE"
else
    failed "daemon.json could not be written"
fi
case "$STORE" in
    *io.containerd.snapshotter.v1*) STORE_OK=yes ;;
    *) STORE_OK=no; failed "the image store is not the containerd snapshotter; nothing is pulled and no shape is run" ;;
esac

# ---- L3 to L6 the command shapes, with a throwaway image and the two units rendered from the frozen templates.
IMAGE_ID=
if [ "$STORE_OK" = yes ]; then
    say "L3 to L6: a throwaway image under the production reference"
    if sudo -n docker image inspect c3po/backend:production > /dev/null 2>&1; then
        refuse "an image named c3po/backend:production exists: this is not a throwaway runner"
    fi
    BASE=
    for candidate in busybox:latest public.ecr.aws/docker/library/busybox:latest; do
        if sudo -n docker pull -q "$candidate" > /dev/null; then BASE=$candidate; break; fi
    done
    if [ -n "$BASE" ] && sudo -n docker image tag "$BASE" c3po/backend:production; then
        IMAGE_ID=$(sudo -n docker image inspect --format '{{.Id}}' c3po/backend:production) || IMAGE_ID=
    fi
    case "$IMAGE_ID" in
        sha256:*) printf 'image: %s as c3po/backend:production, ID %s\n' "$BASE" "$IMAGE_ID" ;;
        *) IMAGE_ID=; failed "no throwaway image could be pulled and tagged" ;;
    esac
fi

if [ -n "$IMAGE_ID" ]; then
    ROOT_PYTHON="sudo -n env HOSTOPS_THROWAWAY_RUNNER=yes RUNNER_ENVIRONMENT=github-hosted /usr/bin/python3 -I -B"
    say "L5: the manager before the installation, after it without a reload, and after a reload"
    $ROOT_PYTHON linux_root/shapes.py --manager before_installation > "$WORK/manager.jsonl" || failed "the manager's view before the installation"
    if /usr/bin/python3 -I -B - "$IMAGE_ID" > "$WORK/c3po-massive.service" <<'RENDER'
import sys
values={'IMAGE_ID':sys.argv[1],'HOST_JOURNAL_ROOT':'/var/lib/c3po-bar/journal','CONTAINER_JOURNAL_ROOT':'/c3po-bar-journal',
        'HOST_STATE_ROOT':'/var/lib/c3po-bar/supervisor','HOST_CONFIG_DIR':'/etc/c3po-bar','NETWORK':'bridge'}
unit=open('templates/c3po-massive.service',encoding='ascii').read()
for name,value in values.items():unit=unit.replace('@'+name+'@',value)
assert '@' not in unit;sys.stdout.write(unit)
RENDER
    then
        INSTALLED=yes
        if sudo -n install -o root -g root -m 0644 "$WORK/c3po-massive.service" "$UNITS/c3po-massive.service" \
           && sudo -n install -o root -g root -m 0644 templates/c3po-massive.timer "$UNITS/c3po-massive.timer"; then
            $ROOT_PYTHON linux_root/shapes.py --manager installed_no_daemon_reload >> "$WORK/manager.jsonl" || failed "the manager's view before the reload"
            sudo -n systemctl daemon-reload || failed "daemon-reload"
            sudo -n systemd-analyze verify "$UNITS/c3po-massive.service" "$UNITS/c3po-massive.timer" > "$OUT/VERIFY.linux-root.txt" 2>&1
            printf 'exit status of systemd-analyze verify: %s\n' "$?" >> "$OUT/VERIFY.linux-root.txt"
            say "L3 to L6: the shapes"
            $ROOT_PYTHON linux_root/shapes.py "$IMAGE_ID" "$WORK/manager.jsonl" > "$OUT/SHAPES.linux-root.json"
            SHAPES=$?
            [ "$SHAPES" = 0 ] || failed "shapes.py exit $SHAPES (2: a shape did not run; 3: an expectation is not met)"
        else
            failed "the two unit files could not be installed"
        fi
    else
        failed "the service unit could not be rendered"
    fi
fi
not_run "$OUT/SHAPES.linux-root.json" "no throwaway image under the containerd image store, or the units could not be installed"
not_run "$OUT/VERIFY.linux-root.txt" "the units were not installed"

cleanup
sudo -n rm -rf /tmp/hostops-empty-docker-config-* 2>/dev/null
say "seal after the run"
sha256sum -c --quiet SHA256SUMS || failed "a file of the sealed candidate changed during the run"
ls -ln "$OUT"
say "exit status $STATUS"
exit "$STATUS"
