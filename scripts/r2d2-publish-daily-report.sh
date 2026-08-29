#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/opt/chief-of-staff-digital
REPORT_DIR=/opt/r2d2-reports
EXPORT_DATE="$(date -u +%Y-%m-%d)"
BRANCH="daily-export/$EXPORT_DATE"

"$APP_DIR/scripts/r2d2-export-readonly.sh" > /dev/null
mkdir -p "$REPORT_DIR/latest"

cd "$REPORT_DIR"
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Report repository is not clean; refusing to publish." >&2
  exit 1
fi
git fetch origin main
git switch main
git merge --ff-only origin/main
if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
  echo "Publication branch $BRANCH already exists; refusing to overwrite it." >&2
  exit 1
fi
git switch -C "$BRANCH" origin/main
cp /tmp/r2d2_export/*.csv "$REPORT_DIR/latest/"
git add latest/

if git diff --cached --quiet; then
  echo "No changes to publish today."
  git switch main
  exit 0
fi

git -c user.name="R2D2 daily export" \
  -c user.email="r2d2-export@c3po.local" \
  commit -m "Daily export $EXPORT_DATE"
git push --set-upstream origin "$BRANCH"
git switch main
echo "Published $BRANCH; the reports repository will validate and merge its PR."
