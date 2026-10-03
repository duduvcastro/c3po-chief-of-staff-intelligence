#!/bin/sh
# C3 (the TLS probe) on a real engine, on Linux as real root. For a THROWAWAY GitHub-hosted ubuntu-24.04 runner only.
# NEVER the production host and never a self-hosted runner: this builds two images, rewrites /etc/docker/daemon.json
# (the "dns" of the engine) and restarts the Docker daemon twice, inserts and removes six rules (three iptables, three
# ip6tables), runs containers, and binds the ports 53 and 443 of the gateway of the network bridge for stand-in servers.
# It refuses
# unless GitHub says the runner is GitHub-hosted, and unless nothing of this family exists on the machine; it removes
# only what this very run created, and puts daemon.json back as it found it.
# NOT RUN by its author: no Linux and no docker were available offline. The structure of catalog_init's run_catalog.sh.
#
# usage: sh linux_root/run.sh <release checkout>      (from the operation directory hostops02/tls_probe)
#        <release checkout>  a checkout of the release (dd4ec4bb): the files this operation is frozen against are
#                            compared by hash before anything is built
# Run it AFTER the core's job step (sh linux_root/run.sh ../tls_probe ...), which checks the seal, the assembly and the
# suites as root and as user, and switches the engine to the containerd image store; and preferably as the LAST step of
# the job, since it changes the engine's DNS for its own duration.
#
# The provider is never contacted. The probe's container resolves through a stand-in DNS server on the gateway of the
# network bridge (the engine's "dns" points there) and reaches a stand-in TLS server on that gateway; before anything is
# started, six rules (IPv4 and IPv6) reject every connection the network bridge would forward to port 443 or 53 of any
# other address, and their counters are read at the end (they must be 0); a network bridge with IPv6 enabled is refused
# outright. The test authority made here is trusted by one TEST image only (the release's base by digest, the authority
# appended to its default bundle); the sealed source is unchanged.
# The probes' docker CLI runs, as on the host, without DOCKER_CONFIG and without HOME: it takes root's configuration
# directory. That directory is listed (names, types, sizes, modification times, modes; never a content) right before
# and right after probe_shape.py, and must not change (C3-U4 for the runner's CLI).
#
# Output, always written: linux_root/SHAPES.tls_probe.linux-root.json (a stage that did not run leaves a file that says
# NOT_RUN and why). Exit 0 only when every run was made, every expectation of probe_shape.py is met, nothing was
# rejected by the guard, and the engine's configuration was put back.
# Nothing here relies on "set -e": every status is tested where it is produced.
set -u
umask 022
cd "$(dirname "$0")/.." || exit 1
OUT=linux_root/SHAPES.tls_probe.linux-root.json
REVISION=dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858
# The base of the release's own image (c3po/backend/Dockerfile at dd4ec4bb, compared below), by digest.
BASE=python:3.12-alpine3.24@sha256:b64631e04e4920160c50fbe8d8df828f7f35f06f425cb44aa09bca53e708a35a
TRUSTING=c3po/backend:massive-supervisor-ci-trusting
STOCK=c3po/backend:massive-supervisor-ci-stock
DAEMON=/etc/docker/daemon.json
STATUS=0
WORK=
BUILT_TRUSTING=no
BUILT_STOCK=no
SAVED=no
EXISTED=no
GUARD=no
GATEWAY=
say() { printf '\n== %s\n' "$*"; }
failed() { printf 'FAILED: %s\n' "$*" >&2; STATUS=1; }
refuse() { printf 'REFUSED: %s\n' "$*" >&2; exit 1; }
wait_docker() {
    tries=0
    until sudo -n docker info > /dev/null 2>&1; do
        tries=$((tries+1)); [ "$tries" -le 30 ] || return 1; sleep 2
    done
    return 0
}
guard_rule() {   # guard_rule <iptables|ip6tables> -I|-D tcp|udp <port>
    if [ "$3" = tcp ]; then
        sudo -n "$1" -w "$2" FORWARD -i docker0 -p tcp --dport "$4" -m comment --comment hostops02-c3-guard -j REJECT --reject-with tcp-reset
    else
        sudo -n "$1" -w "$2" FORWARD -i docker0 -p udp --dport "$4" -m comment --comment hostops02-c3-guard -j REJECT
    fi
}
guard_set() {   # the six rules on what the network bridge forwards (no other address on 443 or 53, IPv4 and IPv6); stops at the first failure
    for tool in iptables ip6tables; do
        guard_rule "$tool" -I tcp 443 && guard_rule "$tool" -I tcp 53 && guard_rule "$tool" -I udp 53 || return 1
    done
    return 0
}
guard_remove() {   # every rule, each tried whatever the others did
    removed=0
    for tool in iptables ip6tables; do
        for rule in "tcp 443" "tcp 53" "udp 53"; do
            # shellcheck disable=SC2086
            guard_rule "$tool" -D $rule || removed=1
        done
    done
    return "$removed"
}
docker_config_state() {   # one hash of root's docker configuration directory as listed (no content is read); empty when it cannot be listed
    listing=$(sudo -n sh -c 'if [ -e /root/.docker ] || [ -L /root/.docker ]; then find /root/.docker -printf "%P %y %s %T@ %m\n" | LC_ALL=C sort; else echo ABSENT; fi' 2>/dev/null) || listing=
    [ -n "$listing" ] || return 0
    printf '%s\n' "$listing" | sha256sum | cut -d' ' -f1
}
restore() {
    if [ "$SAVED" = yes ]; then
        if [ "$EXISTED" = yes ]; then sudo -n cp "$WORK/daemon.json.saved" "$DAEMON" || failed "daemon.json could not be put back"; else sudo -n rm -f "$DAEMON"; fi
        sudo -n systemctl restart docker && wait_docker || failed "docker did not come back after daemon.json was put back"
        SAVED=no
    fi
}
cleanup() {
    if [ "$GUARD" = yes ]; then guard_remove || failed "a guard rule could not be removed (or was never set)"; GUARD=no; fi
    restore
    if [ "$BUILT_TRUSTING" = yes ]; then sudo -n docker image rm "$TRUSTING" > /dev/null 2>&1; BUILT_TRUSTING=no; fi
    if [ "$BUILT_STOCK" = yes ]; then sudo -n docker image rm "$STOCK" > /dev/null 2>&1; BUILT_STOCK=no; fi
    if [ -n "$WORK" ]; then sudo -n rm -rf "$WORK"; WORK=; fi
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
for path in /etc/c3po-bar /var/lib/c3po-bar /etc/c3po-reader /var/lib/c3po-reader /opt/chief-of-staff-digital /mnt/day-d-data; do
    if [ -e "$path" ] || [ -L "$path" ]; then refuse "$path exists: this is not a throwaway runner"; fi
done
sha256sum -c --quiet SHA256SUMS || refuse "the operation directory is not the sealed one"
/usr/bin/python3 -B ../core/assemble.py --check . || refuse "build/ is not what the frozen core assembles"
command -v openssl > /dev/null || refuse "no openssl program to make the test authority"
sudo -n true || refuse "sudo -n is not available"
sudo -n iptables -w -L FORWARD -n > /dev/null || refuse "iptables is not usable: the guard cannot be set, and no probe is started without it"
sudo -n ip6tables -w -L FORWARD -n > /dev/null || refuse "ip6tables is not usable: the guard cannot be set, and no probe is started without it"
trap cleanup EXIT
trap 'exit 130' INT TERM HUP
rm -f "$OUT"

say "the files of the release this operation is frozen against (the provider host and port, the base of the image)"
( cd "$RELEASE" && sha256sum -c --quiet - ) <<'PINS' || refuse "the checkout is not the release dd4ec4bb for the files of the probe"
644c6211c7351de1dfd17d880842deaf4d5e5b34ea63d23a274c5f4e463461c5  c3po/deployment/massive-supervisor/README.md
2ff62bb69a6868a168f67ec7436e02753cc3b3c62196107d892fc7e490a4dc5b  c3po/backend/app/r2d2_v2_massive_transport.py
508636d0bb9cbc81076dfcfeb49cab03f1762c613b740d4a7391faf1a26e8ebf  c3po/backend/Dockerfile
PINS
grep -Fxq "FROM $BASE" "$RELEASE/c3po/backend/Dockerfile" || refuse "the release's Dockerfile is not built on $BASE"
sed -n 99p "$RELEASE/c3po/backend/app/r2d2_v2_massive_transport.py"
sed -n 580p "$RELEASE/c3po/deployment/massive-supervisor/README.md"

say "the image store must be the containerd snapshotter (the core's job step set it)"
STORE=$(sudo -n docker info --format '{{.Driver}} {{json .DriverStatus}}' 2>/dev/null) || STORE=
case "$STORE" in
    *io.containerd.snapshotter.v1*) : ;;
    *) printf 'NOT_RUN: the image store is not the containerd snapshotter (%s)\n' "$STORE" > "$OUT"; refuse "run the core's linux_root/run.sh first" ;;
esac
for reference in "$TRUSTING" "$STOCK" c3po/backend:production; do
    if sudo -n docker image inspect "$reference" > /dev/null 2>&1; then refuse "$reference exists: this is not a throwaway runner"; fi
done
sudo -n docker version --format 'docker client {{.Client.Version}} server {{.Server.Version}}'

say "a throwaway authority and two leaves it signed (the provider's name, another name); the keys stay in a private directory"
WORK=$(mktemp -d) || refuse "no work directory"
chmod 700 "$WORK" || refuse "the work directory cannot be made private"
cat > "$WORK/authority.cnf" <<'CONFIG'
[req]
distinguished_name=dn
[dn]
[v3_ca]
basicConstraints=critical,CA:TRUE
keyUsage=critical,keyCertSign,cRLSign
subjectKeyIdentifier=hash
CONFIG
leaf_config() {
    printf '[req]\ndistinguished_name=dn\n[dn]\n[v3_leaf]\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:%s\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid\n' "$1"
}
leaf_config socket.massive.com > "$WORK/leaf.cnf"
leaf_config other.invalid > "$WORK/other.cnf"
CERTS=no
( cd "$WORK" \
  && openssl ecparam -name prime256v1 -genkey -noout -out ca.key \
  && openssl req -x509 -new -key ca.key -sha256 -days 2 -subj '/CN=hostops02 tls probe test authority' -config authority.cnf -extensions v3_ca -out ca.pem \
  && openssl ecparam -name prime256v1 -genkey -noout -out leaf.key \
  && openssl req -new -key leaf.key -subj '/CN=socket.massive.com' -config leaf.cnf -out leaf.csr \
  && openssl x509 -req -in leaf.csr -CA ca.pem -CAkey ca.key -set_serial 2 -sha256 -days 2 -extfile leaf.cnf -extensions v3_leaf -out leaf.pem \
  && openssl ecparam -name prime256v1 -genkey -noout -out other.key \
  && openssl req -new -key other.key -subj '/CN=other.invalid' -config other.cnf -out other.csr \
  && openssl x509 -req -in other.csr -CA ca.pem -CAkey ca.key -set_serial 3 -sha256 -days 2 -extfile other.cnf -extensions v3_leaf -out other.pem ) > /dev/null 2>&1 \
  && CERTS=yes
[ "$CERTS" = yes ] || failed "the test authority could not be made"

say "two images on the release's base by digest: one that trusts the test authority (TEST ONLY), one as the base is"
IMAGES=no
if [ "$CERTS" = yes ]; then
    mkdir -p "$WORK/trusting" "$WORK/stock" && cp "$WORK/ca.pem" "$WORK/trusting/ca.pem" || failed "no build context"
    printf 'FROM %s\n' "$BASE" > "$WORK/stock/Dockerfile"
    cat > "$WORK/trusting/Dockerfile" <<DOCKERFILE
FROM $BASE
COPY ca.pem /usr/local/share/hostops02-test-authority.pem
RUN python -I -B -c "import os,ssl;p=os.path.realpath(ssl.get_default_verify_paths().openssl_cafile);s=open(p,'ab');s.write(b'\\n'+open('/usr/local/share/hostops02-test-authority.pem','rb').read());s.close();print('test authority appended to',p)"
RUN python -I -B -c "import ssl;names=[dict(item[0] for item in row['subject']).get('commonName') for row in ssl.create_default_context().get_ca_certs()];assert 'hostops02 tls probe test authority' in names,'not trusted'"
DOCKERFILE
    if sudo -n docker build -q --label "org.opencontainers.image.revision=$REVISION" -t "$STOCK" "$WORK/stock" > /dev/null; then BUILT_STOCK=yes; fi
    if sudo -n docker build -q --label "org.opencontainers.image.revision=$REVISION" -t "$TRUSTING" "$WORK/trusting" > /dev/null; then BUILT_TRUSTING=yes; fi
    STOCK_ID=$(sudo -n docker image inspect --format '{{.Id}}' "$STOCK" 2>/dev/null) || STOCK_ID=
    TRUSTING_ID=$(sudo -n docker image inspect --format '{{.Id}}' "$TRUSTING" 2>/dev/null) || TRUSTING_ID=
    case "$STOCK_ID:$TRUSTING_ID" in
        sha256:*:sha256:*)
            [ "$STOCK_ID" != "$TRUSTING_ID" ] || failed "the two images are one"
            printf '{"stock":{"id":"%s","tag":"%s"},"trusting":{"id":"%s","tag":"%s"}}\n' "$STOCK_ID" "$STOCK" "$TRUSTING_ID" "$TRUSTING" > "$WORK/images.json"
            printf 'stock %s\ntrusting %s\n' "$STOCK_ID" "$TRUSTING_ID"; IMAGES=yes ;;
        *) failed "the two images could not be built" ;;
    esac
fi

if [ "$IMAGES" = yes ]; then
    say "the engine's DNS for the network bridge: the gateway of that network, where the stand-in answers"
    GATEWAY=$(sudo -n docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}' 2>/dev/null) || GATEWAY=
    case "$GATEWAY" in
        [0-9]*.[0-9]*.[0-9]*.[0-9]*) printf 'gateway of the network bridge read\n' ;;
        *) GATEWAY=; failed "the gateway of the network bridge could not be read" ;;
    esac
    IPV6=$(sudo -n docker network inspect bridge --format '{{.EnableIPv6}}' 2>/dev/null) || IPV6=
    printf 'IPv6 on the network bridge: %s\n' "${IPV6:-unread}"
    [ "$IPV6" = false ] || { failed "the network bridge has IPv6 enabled, or it could not be read: no probe is started"; GATEWAY=; }
fi
if [ -n "$GATEWAY" ]; then
    # daemon.json is changed only after it was saved; the saved copy is what restore() puts back
    if [ -f "$DAEMON" ]; then
        if sudo -n cp "$DAEMON" "$WORK/daemon.json.saved"; then EXISTED=yes; SAVED=yes; else failed "daemon.json could not be saved: it is not changed and no probe is started"; GATEWAY=; fi
    elif [ -e "$DAEMON" ] || [ -L "$DAEMON" ]; then
        failed "daemon.json is not a regular file: it is not changed and no probe is started"; GATEWAY=
    else
        EXISTED=no; SAVED=yes
    fi
fi
if [ -n "$GATEWAY" ]; then
    if sudo -n /usr/bin/python3 -I -B - "$GATEWAY" <<'DAEMONJSON'
import json,sys
path='/etc/docker/daemon.json'
try:
    with open(path,encoding='utf-8') as handle:config=json.load(handle)
except FileNotFoundError:config={}
if type(config) is not dict:raise SystemExit('daemon.json is not what this script can extend')
config['dns']=[sys.argv[1]]
with open(path,'w',encoding='utf-8') as handle:handle.write(json.dumps(config,indent=1,sort_keys=True)+'\n')
print('daemon.json keys:',sorted(config))
DAEMONJSON
    then
        sudo -n systemctl restart docker && wait_docker || failed "docker did not restart with the stand-in DNS"
        AFTER=$(sudo -n docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}' 2>/dev/null) || AFTER=
        [ "$AFTER" = "$GATEWAY" ] || { failed "the gateway of the network bridge moved across the restart"; GATEWAY=; }
        STORE=$(sudo -n docker info --format '{{.Driver}} {{json .DriverStatus}}' 2>/dev/null) || STORE=
        case "$STORE" in *io.containerd.snapshotter.v1*) : ;; *) failed "the image store changed across the restart"; GATEWAY= ;; esac
    else
        failed "daemon.json could not be written"; GATEWAY=
    fi
fi
if [ -n "$GATEWAY" ]; then
    say "the guard: what the network bridge forwards to port 443 or 53 of any address, IPv4 or IPv6, is rejected, and counted"
    GUARD=yes
    guard_set || { failed "the guard could not be set: no probe is started"; GATEWAY=; }
fi
if [ -n "$GATEWAY" ]; then
    say "C3: six probes with the operation's own perform and Native, the shape of its container and the alarm"
    CONFIG_BEFORE=$(docker_config_state)
    sudo -n env HOSTOPS_THROWAWAY_RUNNER=yes RUNNER_ENVIRONMENT=github-hosted /usr/bin/python3 -I -B linux_root/probe_shape.py "$WORK" "$GATEWAY" > "$OUT"
    SHAPE=$?
    CONFIG_AFTER=$(docker_config_state)
    [ "$SHAPE" = 0 ] || failed "probe_shape.py exit $SHAPE (2: a run was not made; 3: an expectation is not met)"
    sudo -n docker ps -a --format '{{.Names}} {{.State}}'
    if [ -n "$CONFIG_BEFORE" ] && [ "$CONFIG_BEFORE" = "$CONFIG_AFTER" ]; then
        printf "root's docker configuration directory unchanged by the probes (C3-U4 for this CLI): yes\n"
    else
        printf "root's docker configuration directory unchanged by the probes (C3-U4 for this CLI): no\n"
        failed "the docker CLI, run as the source runs it, changed root's configuration directory"
    fi
    REJECTED4=$(sudo -n iptables -w -L FORWARD -v -n -x | awk '/hostops02-c3-guard/ {sum += $1} END {print sum + 0}')
    REJECTED6=$(sudo -n ip6tables -w -L FORWARD -v -n -x | awk '/hostops02-c3-guard/ {sum += $1} END {print sum + 0}')
    printf 'packets the guard rejected: IPv4 %s, IPv6 %s\n' "${REJECTED4:-unread}" "${REJECTED6:-unread}"
    [ "$REJECTED4" = 0 ] && [ "$REJECTED6" = 0 ] || failed "a container of the network bridge tried to leave the runner on port 443 or 53"
fi
[ -s "$OUT" ] || printf 'NOT_RUN: no images, no stand-in DNS or no guard\n' > "$OUT"

cleanup
say "the engine's configuration after the run"
sudo -n cat "$DAEMON" 2>/dev/null | grep -q '"dns"' && failed "daemon.json still names a DNS server"
say "seal after the run"
sha256sum -c --quiet SHA256SUMS || failed "a file of the sealed operation directory changed during the run"
sha256sum "$OUT"; cat "$OUT"
say "exit status $STATUS"
exit "$STATUS"
