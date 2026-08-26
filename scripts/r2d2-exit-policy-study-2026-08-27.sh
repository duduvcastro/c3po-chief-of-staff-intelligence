#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

APP_DIR=/opt/chief-of-staff-digital
HOST_RUN_DIR=/mnt/day-d-data/evidence/r2d2-exit-policy-study-v1-1/2026-08-27
CONTAINER_RUN_DIR=/app/day-d-data/evidence/r2d2-exit-policy-study-v1-1/2026-08-27
SPEC=/legacy/c3po/docs/EXIT_POLICY_STUDY_V1_1.md
AMENDMENT=/legacy/c3po/docs/EXIT_POLICY_STUDY_V1_1_AMENDMENT_1.md
DELIVERABLE=/legacy/c3po/docs/EXIT_POLICY_STUDY_V1_1_DELIVERABLE_0.md
INPUT_CUTOFF_AT=2026-08-25T13:30:15.948946+00:00
EXPECTED_LEDGER_SHA256=51f616bc377329f242d5340eae25b24cecf5be7532f9a89e4e45ec5d67dbb316
EXPECTED_MINUTE_MANIFEST_SHA256=c615d27f297ed80f030c1c95318401d197a58b0d2f906f41746666e62539ba9f
EXPECTED_LEDGER_ROWS=783
EXPECTED_EPISODES=375
PLAN="$HOST_RUN_DIR/plan.json"
REPORT="$HOST_RUN_DIR/report.json"

started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
mkdir -p "$HOST_RUN_DIR"
run_log="$HOST_RUN_DIR/run.log"

exec 9>/var/lock/r2d2-exit-policy-study-2026-08-27.lock
if ! flock -n 9; then
  printf '%s\n' 'Another exit-policy study process holds the lock.' >&2
  exit 75
fi

exec > >(tee -a "$run_log") 2>&1

finish() {
  status=$?
  finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  python3 - "$HOST_RUN_DIR/result.json" "$status" "$started_at" "$finished_at" <<'PY'
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
  find "$HOST_RUN_DIR" -maxdepth 1 -type f ! -name SHA256SUMS -print0 \
    | sort -z \
    | xargs -0 -r sha256sum > "$HOST_RUN_DIR/SHA256SUMS"
  exit "$status"
}
trap finish EXIT

sp_date=$(TZ=America/Sao_Paulo date +%F)
sp_time=$(TZ=America/Sao_Paulo date +%H%M)
sp_minutes=$((10#${sp_time:0:2} * 60 + 10#${sp_time:2:2}))
if [[ "$sp_date" != 2026-08-27 || "$sp_minutes" -lt 15 || "$sp_minutes" -ge 480 ]]; then
  printf 'Refusing outside the authorized run window: date=%s time=%s\n' "$sp_date" "$sp_time"
  exit 10
fi

if ! mountpoint -q /mnt/day-d-data; then
  printf '%s\n' '/mnt/day-d-data is not a mount point.'
  exit 11
fi
free_bytes=$(df -B1 --output=avail /mnt/day-d-data | tail -n 1 | tr -d ' ')
if (( free_bytes < 21474836480 )); then
  printf 'Dedicated disk reserve is below 20 GiB: %s bytes\n' "$free_bytes"
  exit 12
fi
if [[ ! -r "$PLAN" ]]; then
  printf 'Approved plan is missing: %s\n' "$PLAN"
  exit 13
fi

cd "$APP_DIR"
compose=(docker compose --env-file .env -f c3po/compose.yml)
runner_contract=(
  --spec "$SPEC"
  --amendment-one "$AMENDMENT"
  --deliverable-zero "$DELIVERABLE"
  --input-cutoff-at "$INPUT_CUTOFF_AT"
  --expected-ledger-sha256 "$EXPECTED_LEDGER_SHA256"
  --expected-minute-manifest-sha256 "$EXPECTED_MINUTE_MANIFEST_SHA256"
)

api_id=$("${compose[@]}" ps -q api)
db_id=$("${compose[@]}" ps -q db)
if [[ -z "$api_id" || "$(docker inspect -f '{{.State.Status}}' "$api_id")" != running ]]; then
  printf '%s\n' 'api is not running.'
  exit 14
fi
if [[ -z "$db_id" || "$(docker inspect -f '{{.State.Health.Status}}' "$db_id")" != healthy ]]; then
  printf '%s\n' 'db is not healthy.'
  exit 15
fi

plan_at_run_tmp="$HOST_RUN_DIR/plan-at-run.json.tmp"
"${compose[@]}" run --rm -T api python -m app.r2d2_exit_policy_study plan \
  "${runner_contract[@]}" > "$plan_at_run_tmp"
if ! cmp -s "$PLAN" "$plan_at_run_tmp"; then
  mv "$plan_at_run_tmp" "$HOST_RUN_DIR/plan-at-run-mismatch.json"
  printf '%s\n' 'The factual frozen-input plan changed after approval; refusing to run.'
  exit 16
fi
mv "$plan_at_run_tmp" "$HOST_RUN_DIR/plan-at-run.json"
chmod 0444 "$HOST_RUN_DIR/plan-at-run.json"

summary_tmp="$HOST_RUN_DIR/run-summary.json.tmp"
set +e
"${compose[@]}" run --rm -T api python -m app.r2d2_exit_policy_study run \
  "${runner_contract[@]}" \
  --output "$CONTAINER_RUN_DIR/report.json" \
  > "$summary_tmp"
runner_exit_code=$?
set -e
mv "$summary_tmp" "$HOST_RUN_DIR/run-summary.json"
if [[ "$runner_exit_code" -ne 0 && "$runner_exit_code" -ne 2 ]]; then
  printf 'Runner failed before publishing a factual report: exit=%s\n' "$runner_exit_code"
  exit 17
fi
if [[ ! -s "$REPORT" ]]; then
  printf '%s\n' 'Runner did not publish report.json.'
  exit 18
fi

postflight_tmp="$HOST_RUN_DIR/postflight.json.tmp"
if ! "${compose[@]}" run --rm -T api python - \
  "$CONTAINER_RUN_DIR/report.json" \
  "$runner_exit_code" \
  "$INPUT_CUTOFF_AT" \
  "$EXPECTED_LEDGER_SHA256" \
  "$EXPECTED_MINUTE_MANIFEST_SHA256" \
  "$EXPECTED_LEDGER_ROWS" \
  "$EXPECTED_EPISODES" \
  > "$postflight_tmp" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

from app.r2d2_exit_policy_study import (
    AMENDMENT_ONE_SHA256,
    DELIVERABLE_ZERO_SHA256,
    REPORT_SCHEMA_VERSION,
    SPEC_SHA256,
    _report_hash,
)

(
    path,
    runner_exit_code_raw,
    input_cutoff_at,
    expected_ledger_sha256,
    expected_minute_manifest_sha256,
    expected_ledger_rows_raw,
    expected_episodes_raw,
) = sys.argv[1:]
runner_exit_code = int(runner_exit_code_raw)
expected_ledger_rows = int(expected_ledger_rows_raw)
expected_episodes = int(expected_episodes_raw)
report = json.loads(Path(path).read_text(encoding="utf-8"))
gate = report.get("binding_consistency_gate") or {}
compatibility = gate.get("market_compatibility") or {}
inputs = report.get("inputs") or {}
ledger = inputs.get("ledger") or {}
cohort = report.get("cohort") or {}
contract = report.get("frozen_contract") or {}
decomposition = compatibility.get("original_failure_decomposition") or {}
expected_decomposition = {
    "synthetic_fill_vs_signal": 278,
    "clock_extended": 35,
    "tolerance_band": 89,
    "violation": 4,
}
checks = {
    "schema_v2": report.get("schema_version") == REPORT_SCHEMA_VERSION,
    "self_hash": report.get("report_sha256") == _report_hash(report),
    "spec_hash": (contract.get("spec") or {}).get("sha256") == SPEC_SHA256,
    "amendment_hash": (
        (contract.get("amendment_one") or {}).get("sha256") == AMENDMENT_ONE_SHA256
    ),
    "deliverable_hash": (
        (contract.get("deliverable_zero") or {}).get("sha256") == DELIVERABLE_ZERO_SHA256
    ),
    "read_only": report.get("governance", {}).get("read_only") is True,
    "zero_external_api_calls": report.get("governance", {}).get("external_api_calls") == 0,
    "strategy_change_locked": (
        report.get("governance", {}).get("strategy_change_authorized") is False
    ),
    "runner_exit_zero": runner_exit_code == 0,
    "analysis_interpretable": report.get("analysis_interpretable") is True,
    "binding_gate_passed": gate.get("passed") is True,
    "ledger_rows": ledger.get("row_count") == expected_ledger_rows,
    "ledger_hash": ledger.get("canonical_json_sha256") == expected_ledger_sha256,
    "ledger_expected_hash": ledger.get("expected_sha256") == expected_ledger_sha256,
    "ledger_hash_verified": ledger.get("frozen_hash_verified") is True,
    "ledger_cutoff": ledger.get("input_cutoff_at") == input_cutoff_at,
    "ledger_last_row": ledger.get("last_executed_at") == input_cutoff_at,
    "minute_manifest_hash": (
        inputs.get("minute_aggregate_manifest_sha256")
        == expected_minute_manifest_sha256
    ),
    "minute_manifest_expected_hash": (
        inputs.get("expected_minute_aggregate_manifest_sha256")
        == expected_minute_manifest_sha256
    ),
    "minute_manifest_hash_verified": (
        inputs.get("minute_aggregate_manifest_hash_verified") is True
    ),
    "constructed_episodes": cohort.get("constructed_episode_count") == expected_episodes,
    "market_compatibility_threshold": compatibility.get("threshold_passed") is True,
    "frozen_probe_decomposition": decomposition == expected_decomposition,
    "four_coverage_censored_episodes": (
        compatibility.get("coverage_censored_episode_count") == 4
    ),
}
failed = sorted(name for name, passed in checks.items() if not passed)
payload = {
    "report_sha256": report.get("report_sha256"),
    "runner_exit_code": runner_exit_code,
    "binding_gate_passed": gate.get("passed") is True,
    "binding_gate_failure_count": len(gate.get("failures") or []),
    "analysis_interpretable": report.get("analysis_interpretable") is True,
    "classification": report.get("classification"),
    "frozen_inputs": {
        "input_cutoff_at": ledger.get("input_cutoff_at"),
        "ledger_rows": ledger.get("row_count"),
        "ledger_sha256": ledger.get("canonical_json_sha256"),
        "minute_manifest_sha256": inputs.get("minute_aggregate_manifest_sha256"),
    },
    "market_compatibility": {
        "counts": compatibility.get("counts"),
        "original_failure_decomposition": decomposition,
        "coverage_censored_episode_count": compatibility.get(
            "coverage_censored_episode_count"
        ),
        "coverage_censored_percent": compatibility.get("coverage_censored_percent"),
        "threshold_passed": compatibility.get("threshold_passed"),
        "violation_fills": compatibility.get("violation_fills"),
    },
    "censoring": {
        "construction": cohort.get("construction"),
        "base": cohort.get("base_censoring"),
        "coverage": cohort.get("coverage_censoring"),
        "panel_i": cohort.get("panel_i_censoring"),
        "panel_ii": cohort.get("panel_ii_censoring"),
        "excursions": (report.get("real_episode_excursions") or {}).get(
            "censored_episode_count"
        ),
    },
    "checks": checks,
    "postflight_ok": not failed,
    "failed_checks": failed,
}
print(json.dumps(payload, sort_keys=True))
raise SystemExit(0 if not failed else 2)
PY
then
  mv "$postflight_tmp" "$HOST_RUN_DIR/postflight.json"
  printf '%s\n' 'Report was published, but frozen-input postflight validation failed.'
  exit 19
fi
mv "$postflight_tmp" "$HOST_RUN_DIR/postflight.json"
chmod 0444 "$PLAN" "$REPORT" "$HOST_RUN_DIR/run-summary.json" "$HOST_RUN_DIR/postflight.json"

printf 'Exit-policy study rerun completed and validated. evidence=%s\n' "$HOST_RUN_DIR"
