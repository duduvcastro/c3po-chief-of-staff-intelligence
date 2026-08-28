#!/usr/bin/env bash
set -Eeuo pipefail

BASE=/opt/chief-of-staff-digital
COMPOSE=(docker compose --env-file "$BASE/.env" -f "$BASE/c3po/compose.yml")
SESSION_DATE=$(TZ=America/Sao_Paulo date +%F)
RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
EVIDENCE_DIR="$BASE/outputs/evidence/postgres-backup/$SESSION_DATE/$RUN_ID"
TEMP_DIR="/mnt/day-d-data/tmp/postgres-backup/$SESSION_DATE/$RUN_ID"
DUMP_NAME="c3po-postgres-$SESSION_DATE.dump"
DUMP_PATH="$TEMP_DIR/$DUMP_NAME"
LOCK_FILE=/run/lock/c3po-postgres-backup.lock

mkdir -p "$EVIDENCE_DIR" "$TEMP_DIR"
chmod 750 "$EVIDENCE_DIR" "$TEMP_DIR"
exec 9>"$LOCK_FILE"
flock -n 9 || {
  printf 'another postgres backup is already running\n' >&2
  exit 75
}

healthcheck_url=$(awk -F= '
  $1 == "C3PO_HEALTHCHECK_POSTGRES_BACKUP_URL" {
    sub(/^[^=]*=/, ""); print; exit
  }
' "$BASE/.env")

ping_healthcheck() {
  local state=${1:-success}
  local suffix=
  [ -n "$healthcheck_url" ] || return 0
  case "$state" in
    start) suffix=/start ;;
    fail) suffix=/fail ;;
    success) suffix= ;;
    *) return 0 ;;
  esac
  curl --silent --show-error --fail --max-time 10 \
    "${healthcheck_url%/}${suffix}" >/dev/null 2>&1 || true
}

notify_backup_failure() {
  "${COMPOSE[@]}" run --rm -T api python -m app.push_notifications emit \
    --category job_failure \
    --title "Backup do PostgreSQL falhou" \
    --body "O backup offsite não foi concluído. Verifique o Storm Troops." \
    --deep-link "/?view=health" \
    --event-key "postgres-backup-failure:$SESSION_DATE" >/dev/null 2>&1 || true
}

cleanup() {
  local exit_code=$?
  rm -f "$DUMP_PATH"
  rmdir "$TEMP_DIR" 2>/dev/null || true
  if [ "$exit_code" -ne 0 ]; then
    ping_healthcheck fail
    notify_backup_failure
  fi
  exit "$exit_code"
}
trap cleanup EXIT

ping_healthcheck start

python3 - "$EVIDENCE_DIR/preflight.json" "$SESSION_DATE" "$RUN_ID" <<'PY'
import json
import pathlib
import sys
from datetime import datetime, timezone

path = pathlib.Path(sys.argv[1])
payload = {
    "schema": "C3PO_POSTGRES_BACKUP_PREFLIGHT-v1",
    "session_date": sys.argv[2],
    "run_id": sys.argv[3],
    "started_at": datetime.now(timezone.utc).isoformat(),
    "database": "c3po",
    "dump_format": "custom",
    "compression": "gzip-level-9",
}
path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
PY

cd "$BASE"
"${COMPOSE[@]}" exec -T db \
  pg_dump -U c3po -d c3po --format=custom --compress=9 \
    --no-owner --no-privileges >"$DUMP_PATH"

test -s "$DUMP_PATH"
"${COMPOSE[@]}" exec -T db pg_restore --list \
  <"$DUMP_PATH" >/dev/null

dump_sha256=$(sha256sum "$DUMP_PATH" | awk '{print $1}')
dump_size=$(stat -c %s "$DUMP_PATH")
python3 - "$EVIDENCE_DIR/dump.json" "$dump_sha256" "$dump_size" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
payload = {
    "schema": "C3PO_POSTGRES_BACKUP_DUMP-v1",
    "file_sha256": sys.argv[2],
    "file_size": int(sys.argv[3]),
    "pg_restore_list_valid": True,
}
path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
PY

"${COMPOSE[@]}" run --rm -T \
  --user "$(id -u):$(id -g)" \
  -v "$TEMP_DIR:/backup:ro" \
  -v "$EVIDENCE_DIR:/evidence" \
  api python -m app.postgres_backup_upload \
    --file "/backup/$DUMP_NAME" \
    --session-date "$SESSION_DATE" \
    --output /evidence/upload.json

python3 - "$EVIDENCE_DIR" "$dump_sha256" <<'PY'
import hashlib
import json
import pathlib
import sys
from datetime import datetime, timezone

root = pathlib.Path(sys.argv[1])
expected_sha = sys.argv[2]
upload = json.loads((root / "upload.json").read_text(encoding="utf-8"))
if upload.get("file_sha256") != expected_sha:
    raise SystemExit("upload evidence does not match the local dump SHA-256")
result = {
    "schema": "C3PO_POSTGRES_BACKUP_RESULT-v1",
    "status": "succeeded",
    "completed_at": datetime.now(timezone.utc).isoformat(),
    "dump_sha256": expected_sha,
    "upload_count": len(upload.get("uploads") or []),
    "uploads": upload.get("uploads") or [],
}
canonical = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
result["self_sha256"] = hashlib.sha256(canonical).hexdigest()
(root / "result.json").write_text(
    json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
)
PY

(
  cd "$EVIDENCE_DIR"
  sha256sum preflight.json dump.json upload.json result.json >SHA256SUMS
  chmod 640 preflight.json dump.json upload.json result.json SHA256SUMS
)

ping_healthcheck success
