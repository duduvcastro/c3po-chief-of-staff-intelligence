#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/opt/chief-of-staff-digital
REPORT_DIR=/opt/r2d2-reports

"$APP_DIR/scripts/r2d2-export-readonly.sh" > /dev/null
mkdir -p "$REPORT_DIR/latest"
cp /tmp/r2d2_export/*.csv "$REPORT_DIR/latest/"

cd "$REPORT_DIR"
git add latest/

if git diff --cached --quiet; then
  echo "No changes to publish today."
  exit 0
fi

git -c user.name="R2D2 daily export" \
  -c user.email="r2d2-export@c3po.local" \
  commit -m "Daily export $(date -u +%Y-%m-%d)"
git push origin main
