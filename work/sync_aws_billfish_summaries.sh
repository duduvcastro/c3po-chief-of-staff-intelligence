#!/bin/sh
set -u

AWS_HOST="${BILLFISH_AWS_HOST:-18.230.60.255}"
AWS_USER="${BILLFISH_AWS_USER:-ubuntu}"
AWS_PROJECT_DIR="${BILLFISH_AWS_PROJECT_DIR:-/opt/chief-of-staff-digital}"
AWS_KEY_PATH="${BILLFISH_AWS_KEY_PATH:-/Users/eduardocastro/Downloads/LightsailDefaultKey-sa-east-1.pem}"
AWS_SSH_TIMEOUT="${BILLFISH_AWS_SSH_TIMEOUT:-8}"
OUTPUT_DIR="${BILLFISH_OUTPUT_DIR:-outputs}"

if [ -z "$AWS_HOST" ] || [ -z "$AWS_USER" ] || [ ! -f "$AWS_KEY_PATH" ]; then
  echo "AWS Billfish sync skipped; missing host/user/key."
  exit 0
fi

mkdir -p "$OUTPUT_DIR"

tmp_list="$(mktemp)"
ssh -i "$AWS_KEY_PATH" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout="$AWS_SSH_TIMEOUT" \
  "$AWS_USER@$AWS_HOST" "cd $AWS_PROJECT_DIR && ls -1t outputs/*summary-*.txt outputs/resumo-manha-*.txt 2>/dev/null | sed -n '1,4p'" \
  >"$tmp_list" 2>/dev/null || true

remote_files="$(cat "$tmp_list")"
rm -f "$tmp_list"

if [ -z "$remote_files" ]; then
  echo "AWS Billfish sync unavailable; keeping local outputs fallback."
  exit 0
fi

echo "$remote_files" | while IFS= read -r remote_file; do
  [ -n "$remote_file" ] || continue
  base_name="$(basename "$remote_file")"
  scp -i "$AWS_KEY_PATH" -q -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout="$AWS_SSH_TIMEOUT" \
    "$AWS_USER@$AWS_HOST:$AWS_PROJECT_DIR/$remote_file" "$OUTPUT_DIR/$base_name" || true
done

scp -i "$AWS_KEY_PATH" -q -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout="$AWS_SSH_TIMEOUT" \
  "$AWS_USER@$AWS_HOST:$AWS_PROJECT_DIR/outputs/cron.log" "$OUTPUT_DIR/cron.log" 2>/dev/null || true

echo "AWS Billfish sync completed."
