#!/bin/bash
# S1 bisect: which property of the reader's transient unit does real systemd 255 refuse? Synthetic only.
set -u
OUT=/tmp/s1bisect; mkdir -p $OUT
D=/usr/local/lib/s1bisect; mkdir -p $D
cat > $D/docker <<'EOD'
#!/bin/sh
if [ "$1" = run ]; then exec /bin/sleep 600; fi
exit 0
EOD
chmod 755 $D/docker
mkdir -p /mnt/day-d-data /var/lib/c3po-bar/journal-e04 /var/lib/c3po-capacity-e04 /etc/c3po-reader-e04/launcher /var/lib/s1bisect/docker-cli
for f in secret pins activation; do echo X=1 > /etc/c3po-reader-e04/$f.env; chmod 600 /etc/c3po-reader-e04/$f.env; done
{ systemctl --version | head -1; findmnt /mnt; findmnt -T /mnt/day-d-data; systemctl show mnt.mount -p Requires,Wants,After,ActiveState,LoadState; } > $OUT/env.txt 2>&1
COMMON=(--description=bisect --property=Wants=network-online.target --property=Requires=docker.service --property=After="network-online.target docker.service" --property=Type=exec --property=Environment=DOCKER_CONFIG=/var/lib/s1bisect/docker-cli)
COND=(--property="ExecCondition=/usr/bin/test -f /etc/c3po-reader-e04/secret.env" --property="ExecCondition=/usr/bin/test -f /etc/c3po-reader-e04/pins.env" --property="ExecCondition=/usr/bin/test -f /etc/c3po-reader-e04/activation.env")
RMF_FULL=(--property="RequiresMountsFor=/mnt/day-d-data /var/lib/c3po-bar/journal-e04 /var/lib/c3po-capacity-e04 /etc/c3po-reader-e04")
RMF_NOMNT=(--property="RequiresMountsFor=/var/lib/c3po-bar/journal-e04 /var/lib/c3po-capacity-e04 /etc/c3po-reader-e04")
TAIL=(--property="ExecStartPre=-$D/docker rm X" --property="ExecStartPre=$D/docker image inspect --format {{.Id}} sha256:ab" --property="ExecStop=-$D/docker stop -t 25 X" --property="ExecStopPost=-$D/docker stop -t 25 X" --property=Restart=no --property=TimeoutStartSec=60s --property=TimeoutStopSec=30s --property=KillMode=control-group --property=UMask=0077 --property=NoNewPrivileges=true --property=StandardOutput=journal --property=StandardError=journal)
run() { name=$1; shift; echo "== $name" >> $OUT/results.txt; /usr/bin/systemd-run --unit=$name "$@" $D/docker run --rm x > $OUT/$name.out 2> $OUT/$name.err; rc=$?; echo "rc=$rc stderr=$(tr '\n' ' ' < $OUT/$name.err)" >> $OUT/results.txt; sleep 3; systemctl show $name.service -p LoadState,ActiveState,SubState,Result,ExecMainStatus >> $OUT/results.txt 2>&1; journalctl -u $name.service --no-pager -n 30 > $OUT/$name.journal 2>&1; systemctl stop $name.service 2>/dev/null; systemctl reset-failed $name.service 2>/dev/null; }
run b-full "${COMMON[@]}" "${RMF_FULL[@]}" "${COND[@]}" "${TAIL[@]}"
run b-nocond "${COMMON[@]}" "${RMF_FULL[@]}" "${TAIL[@]}"
run b-nomnt "${COMMON[@]}" "${RMF_NOMNT[@]}" "${COND[@]}" "${TAIL[@]}"
run b-neither "${COMMON[@]}" "${RMF_NOMNT[@]}" "${TAIL[@]}"
run b-cond1 "${COMMON[@]}" --property="ExecCondition=/usr/bin/test -f /etc/c3po-reader-e04/secret.env" "${TAIL[@]}"
run b-condex "${COMMON[@]}" --property="ExecConditionEx=/usr/bin/test -f /etc/c3po-reader-e04/secret.env" "${TAIL[@]}"
run b-rmf-mnt-only "${COMMON[@]}" --property="RequiresMountsFor=/mnt/day-d-data" "${TAIL[@]}"
journalctl --no-pager -n 200 > $OUT/journal_tail.txt 2>&1
cat $OUT/env.txt $OUT/results.txt
