#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

APP_DIR=/opt/chief-of-staff-digital
EVIDENCE_ROOT="$APP_DIR/outputs/evidence/r2d2-resume-2026-08-26"
POLICY_EPOCH=policy-a-resume-2026-08-26
OPERATOR=Dudu
REASON='Six-hands evidence-collection resume on 26/08 under unchanged Policy A; EHC fill reconciled; entry score adapter active'
ADAPTER_VERSION=R2D2-ENTRY-SCORE-ADAPTER-v1

started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
run_id=$(date -u +%Y%m%dT%H%M%SZ)
run_dir="$EVIDENCE_ROOT/$run_id"
mkdir -p "$run_dir"
run_log="$run_dir/run.log"

exec 9>/var/lock/r2d2-resume-2026-08-26.lock
if ! flock -n 9; then
  printf '%s\n' 'Another R2D2 resume process holds the lock.' >&2
  exit 75
fi

exec > >(tee -a "$run_log") 2>&1

finish() {
  status=$?
  finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  python3 - "$run_dir/result.json" "$status" "$started_at" "$finished_at" <<'PY'
import json
import sys
from pathlib import Path

path, status, started_at, finished_at = sys.argv[1:]
payload = {
    "status": "succeeded" if int(status) == 0 else "failed",
    "exit_code": int(status),
    "started_at": started_at,
    "finished_at": finished_at,
}
temporary = Path(f"{path}.tmp")
temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
temporary.replace(path)
PY
  find "$run_dir" -maxdepth 1 -type f ! -name SHA256SUMS -print0 \
    | sort -z \
    | xargs -0 -r sha256sum > "$run_dir/SHA256SUMS"
  exit "$status"
}
trap finish EXIT

cd "$APP_DIR"
compose=(docker compose --env-file .env -f c3po/compose.yml)

ny_date=$(TZ=America/New_York date +%F)
ny_time=$(TZ=America/New_York date +%H%M)
ny_minutes=$((10#${ny_time:0:2} * 60 + 10#${ny_time:2:2}))
if [[ "$ny_date" != 2026-08-26 || "$ny_minutes" -lt 570 || "$ny_minutes" -ge 960 ]]; then
  printf 'Refusing outside the authorized US session: date=%s time=%s\n' "$ny_date" "$ny_time"
  exit 10
fi

worker_id=$("${compose[@]}" ps -q r2d2-worker)
if [[ -z "$worker_id" || "$(docker inspect -f '{{.State.Status}}' "$worker_id")" != running ]]; then
  printf '%s\n' 'r2d2-worker is not running.'
  exit 11
fi

preflight_tmp="$run_dir/preflight.json.tmp"
if ! "${compose[@]}" run --rm -T api python - > "$preflight_tmp" <<'PY'
from __future__ import annotations

import json
from datetime import datetime

from app.config import Settings
from app.database import Database
from app.r2d2 import R2D2Repository
from app.r2d2_entry_score_adapter import ADAPTER_VERSION


def ready(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


settings = Settings()
database = Database(settings)
repository = R2D2Repository(database)
experiment = repository.experiment(settings.r2d2_experiment_code)
blocked = []
positions = []
buys_after_pause = []
if experiment is None:
    blocked.append("experiment_missing")
else:
    positions = repository.positions(experiment["id"])
    pause_at = experiment.get("entries_paused_at")
    trades = repository.trades(experiment["id"], limit=10000)
    buys_after_pause = [
        trade for trade in trades
        if trade.get("side") == "BUY"
        and pause_at is not None
        and trade.get("executed_at") is not None
        and trade["executed_at"] > pause_at
    ]
    if experiment.get("status") != "running":
        blocked.append("experiment_not_running")
    if not bool(experiment.get("entries_paused")):
        blocked.append("entries_not_paused")
    if positions:
        blocked.append("open_positions_present")
    if buys_after_pause:
        blocked.append("buy_after_pause_detected")
if not settings.r2d2_entry_score_adapter_enabled:
    blocked.append("entry_score_adapter_not_configured")

payload = {
    "checked_at": datetime.now().astimezone().isoformat(),
    "experiment_code": settings.r2d2_experiment_code,
    "experiment_status": experiment.get("status") if experiment else None,
    "entries_paused": bool(experiment and experiment.get("entries_paused")),
    "entries_paused_at": ready(experiment.get("entries_paused_at")) if experiment else None,
    "open_position_count": len(positions),
    "open_symbols": sorted(position["symbol"] for position in positions),
    "buy_after_pause_count": len(buys_after_pause),
    "entry_score_adapter_configured": settings.r2d2_entry_score_adapter_enabled,
    "entry_score_adapter_version": ADAPTER_VERSION,
    "resume_ready": not blocked,
    "blocked_reasons": blocked,
}
print(json.dumps(payload, sort_keys=True))
raise SystemExit(0 if not blocked else 2)
PY
then
  mv "$preflight_tmp" "$run_dir/preflight.json"
  printf '%s\n' 'Scheduled resume preflight failed closed.'
  exit 12
fi
mv "$preflight_tmp" "$run_dir/preflight.json"

entry_control=(
  "${compose[@]}" run --rm -T api python -m app.r2d2_entry_control
  --resume
  --policy-epoch "$POLICY_EPOCH"
  --operator "$OPERATOR"
  --reason "$REASON"
)

plan_tmp="$run_dir/plan.json.tmp"
"${entry_control[@]}" > "$plan_tmp"
mv "$plan_tmp" "$run_dir/plan.json"
python3 - "$run_dir/plan.json" "$POLICY_EPOCH" <<'PY'
import json
import sys

path, expected_epoch = sys.argv[1:]
with open(path, encoding="utf-8") as source:
    payload = json.load(source)
checks = {
    "mode": payload.get("mode") == "plan",
    "currently_paused": payload.get("current_entries_paused") is True,
    "requested_active": payload.get("requested_entries_paused") is False,
    "state_change_required": payload.get("state_change_required") is True,
    "resume_ready": payload.get("resume_ready") is True,
    "no_blocked_reasons": payload.get("blocked_reasons") == [],
    "adapter_configured": payload.get("entry_score_adapter", {}).get("configured") is True,
    "policy_epoch": payload.get("requested_policy_epoch") == expected_epoch,
}
failed = sorted(name for name, passed in checks.items() if not passed)
if failed:
    raise SystemExit("Plan validation failed: " + ", ".join(failed))
PY

execute_tmp="$run_dir/execute.json.tmp"
"${entry_control[@]}" --execute > "$execute_tmp"
mv "$execute_tmp" "$run_dir/execute.json"
python3 - "$run_dir/execute.json" "$POLICY_EPOCH" "$ADAPTER_VERSION" <<'PY'
import json
import sys

path, expected_epoch, expected_adapter = sys.argv[1:]
with open(path, encoding="utf-8") as source:
    payload = json.load(source)
checks = {
    "mode": payload.get("mode") == "execute",
    "entries_active": payload.get("entries_paused") is False,
    "policy_epoch": payload.get("policy_epoch") == expected_epoch,
    "adapter_version": payload.get("entry_score_adapter_version") == expected_adapter,
}
failed = sorted(name for name, passed in checks.items() if not passed)
if failed:
    raise SystemExit("Execute validation failed: " + ", ".join(failed))
PY

postflight_tmp="$run_dir/postflight.json.tmp"
if ! "${compose[@]}" run --rm -T api python - > "$postflight_tmp" <<'PY'
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from app.config import Settings
from app.database import Database
from app.r2d2 import R2D2Repository
from app.r2d2_entry_score_adapter import ADAPTER_VERSION

EXPECTED_EPOCH = "policy-a-resume-2026-08-26"
EXPECTED_OPERATOR = "Dudu"
EXPECTED_REASON = "Six-hands evidence-collection resume on 26/08 under unchanged Policy A; EHC fill reconciled; entry score adapter active"

settings = Settings()
database = Database(settings)
repository = R2D2Repository(database)
deadline = time.monotonic() + 240
adapter_cycle = None
experiment = None
while time.monotonic() < deadline:
    experiment = repository.experiment(settings.r2d2_experiment_code)
    if experiment is not None:
        last_cycle = repository.last_cycle(experiment["id"])
        metadata = (last_cycle or {}).get("metadata") or {}
        candidate = metadata.get("entry_score_adapter") if isinstance(metadata, dict) else None
        epoch_started_at = experiment.get("policy_epoch_started_at")
        cycle_started_at = (last_cycle or {}).get("started_at")
        if (
            isinstance(candidate, dict)
            and candidate.get("enabled") is True
            and candidate.get("version") == ADAPTER_VERSION
            and candidate.get("status") == "healthy"
            and candidate.get("policy_epoch") == EXPECTED_EPOCH
            and epoch_started_at is not None
            and cycle_started_at is not None
            and cycle_started_at >= epoch_started_at
        ):
            adapter_cycle = candidate
            break
    time.sleep(10)

events = database.list_audit_events(action="r2d2.entries_resumed", limit=10)
matching_events = [
    event for event in events
    if event.get("actor") == EXPECTED_OPERATOR
    and event.get("detail", {}).get("policy_epoch") == EXPECTED_EPOCH
    and event.get("detail", {}).get("reason") == EXPECTED_REASON
]
blocked = []
if experiment is None:
    blocked.append("experiment_missing")
else:
    if experiment.get("status") != "running":
        blocked.append("experiment_not_running")
    if bool(experiment.get("entries_paused")):
        blocked.append("entries_still_paused")
    if experiment.get("policy_epoch") != EXPECTED_EPOCH:
        blocked.append("policy_epoch_mismatch")
    if experiment.get("entry_score_adapter_version") != ADAPTER_VERSION:
        blocked.append("adapter_version_mismatch")
if not matching_events:
    blocked.append("resume_audit_event_missing")
if adapter_cycle is None:
    blocked.append("adapter_cycle_not_healthy_after_resume")

positions = repository.positions(experiment["id"]) if experiment else []
payload = {
    "checked_at": datetime.now(timezone.utc).isoformat(),
    "experiment_status": experiment.get("status") if experiment else None,
    "entries_paused": bool(experiment and experiment.get("entries_paused")),
    "policy_epoch": experiment.get("policy_epoch") if experiment else None,
    "entry_score_adapter_version": experiment.get("entry_score_adapter_version") if experiment else None,
    "entry_score_adapter_cycle": adapter_cycle,
    "resume_audit_event": matching_events[0] if matching_events else None,
    "open_position_count_after_resume": len(positions),
    "open_symbols_after_resume": sorted(position["symbol"] for position in positions),
    "postflight_ok": not blocked,
    "blocked_reasons": blocked,
}
print(json.dumps(payload, default=str, sort_keys=True))
raise SystemExit(0 if not blocked else 2)
PY
then
  mv "$postflight_tmp" "$run_dir/postflight.json"
  printf '%s\n' 'Resume changed state, but postflight validation did not pass.'
  exit 13
fi
mv "$postflight_tmp" "$run_dir/postflight.json"

printf 'R2D2 resume completed and validated. evidence=%s\n' "$run_dir"
