#!/usr/bin/env bash
set -euo pipefail
# Separate opt-in staging ONLY. Never called by deploy or security installation.
if [ "${1:-}" != --install-only ] || [ "$#" -ne 1 ]; then
  echo 'usage: install-workflow-schedule-recovery.sh --install-only (does not enable/start anything)' >&2
  exit 2
fi
root=/opt/chief-of-staff-digital
cd "$root"
test -s .deploy-version
install -d -o root -g root -m 0755 /usr/local/lib/c3po-workflow-recovery
install -o root -g root -m 0755 scripts/c3po_workflow_schedule_recovery.py /usr/local/lib/c3po-workflow-recovery/
for unit in c3po-workflow-schedule-recovery.service c3po-workflow-schedule-recovery.timer; do
  install -o root -g root -m 0644 "ops/systemd/$unit" /etc/systemd/system/
done
systemd-analyze verify /etc/systemd/system/c3po-workflow-schedule-recovery.{service,timer}
echo 'Staged only. Token provisioning, daemon-reload and timer activation need a separate operational authorization.'
