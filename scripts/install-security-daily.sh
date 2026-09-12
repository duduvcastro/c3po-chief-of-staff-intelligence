#!/usr/bin/env bash
set -euo pipefail
# Install from a reviewed, deployed checkout. The hold must be explicitly removed
# after validating credentials and reconciling any active trial's pinned baseline.
root=/opt/chief-of-staff-digital
cd "$root"
test -s .deploy-version
test -f scripts/c3po_security_daily.py
systemctl is-enabled apt-daily-upgrade.timer
test -x /usr/local/sbin/c3po-host-security-snapshot
install -d -o root -g root -m 0755 /usr/local/lib/c3po-security /etc/c3po
install -o root -g root -m 0755 scripts/c3po_security_daily.py /usr/local/lib/c3po-security/
install -o root -g root -m 0644 scripts/c3po_dependency_security.py /usr/local/lib/c3po-security/
install -o root -g root -m 0644 scripts/c3po_container_remediation.py scripts/c3po_trivy_scan.py /usr/local/lib/c3po-security/
if [ ! -f /etc/c3po/security-automation.json ]; then
  install -o root -g root -m 0644 ops/security-automation.json /etc/c3po/security-automation.json
  printf '%s\n' 'Initial activation: verify credential permissions and trial baseline before removal.' \
    > /etc/c3po/security-maintenance.hold
fi
install -o root -g root -m 0644 ops/systemd/c3po-security-daily.service /etc/systemd/system/
install -o root -g root -m 0644 ops/systemd/c3po-security-daily.timer /etc/systemd/system/
systemd-analyze verify /etc/systemd/system/c3po-security-daily.service /etc/systemd/system/c3po-security-daily.timer
systemctl daemon-reload
systemctl enable --now c3po-security-daily.timer
systemctl start c3po-security-daily.service
systemctl is-enabled c3po-security-daily.timer
systemctl show c3po-security-daily.timer -p NextElapseUSecRealtime
