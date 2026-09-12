#!/usr/bin/env bash
set -euo pipefail
# Reviewed files from the deployed release. Preserve every explicit hold.
root=/opt/chief-of-staff-digital
cd "$root"
test -s .deploy-version
test -x /usr/local/sbin/c3po-host-security-snapshot
install -d -o root -g root -m 0755 /usr/local/lib/c3po-security
mkdir -p /etc/c3po runtime/security
if [ ! -e runtime/security/deployment.lock ]; then
  install -o ubuntu -g ubuntu -m 0644 /dev/null runtime/security/deployment.lock
fi
install -o root -g root -m 0755 scripts/c3po_security_daily.py scripts/c3po_security_watchdog.py /usr/local/lib/c3po-security/
install -o root -g root -m 0644 scripts/c3po_dependency_security.py scripts/c3po_security_reboot.py scripts/c3po_security_guard.py scripts/c3po_container_remediation.py scripts/c3po_trivy_scan.py /usr/local/lib/c3po-security/
if [ ! -f /etc/c3po/security-automation.json ]; then
  # Hold bootstrap before policy/timers; noclobber preserves operator holds.
  ( umask 077; set -o noclobber; printf '%s\n' 'bootstrap: pending post-install acceptance' > /etc/c3po/security-maintenance.hold ) 2>/dev/null || test -e /etc/c3po/security-maintenance.hold
  install -o root -g root -m 0644 ops/security-automation.json /etc/c3po/security-automation.json
fi
for unit in c3po-security-daily.service c3po-security-daily.timer c3po-security-watchdog.service c3po-security-watchdog.timer; do
  install -o root -g root -m 0644 "ops/systemd/$unit" /etc/systemd/system/
done
systemd-analyze verify /etc/systemd/system/c3po-security-{daily,watchdog}.{service,timer}
systemctl daemon-reload
systemctl enable --now c3po-security-daily.timer c3po-security-watchdog.timer
systemctl start --no-block c3po-security-watchdog.service
systemctl is-enabled c3po-security-daily.timer c3po-security-watchdog.timer
systemctl show c3po-security-daily.timer -p NextElapseUSecRealtime
