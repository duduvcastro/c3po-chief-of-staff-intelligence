#!/bin/sh
set -u

PYTHON_BIN="${PYTHON_BIN:-python3}"

sh work/sync_aws_billfish_summaries.sh

"$PYTHON_BIN" work/whatsapp_web_capture.py capture --timeout "${WHATSAPP_CAPTURE_TIMEOUT:-90}" \
  --output outputs/whatsapp_unread_today.json \
  || echo "WhatsApp capture failed; continuing with existing JSON."

set -- --archive-informative "$@"

"$PYTHON_BIN" work/morning_summary.py --limit "${EMAIL_SCAN_LIMIT:-250}" --whatsapp-json outputs/whatsapp_unread_today.json "$@"
