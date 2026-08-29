#!/usr/bin/env bash
set -u

action=${1:-}
url=${C3PO_HEALTHCHECK_UNATTENDED_UPGRADES_URL:-}

[ -n "$url" ] || exit 0

case "$action" in
  start)
    target="${url%/}/start"
    ;;
  success)
    target="${url%/}"
    ;;
  fail)
    target="${url%/}/fail"
    ;;
  *)
    exit 0
    ;;
esac

curl --fail --silent --max-time 5 --output /dev/null "$target" \
  >/dev/null 2>&1 || true
exit 0
