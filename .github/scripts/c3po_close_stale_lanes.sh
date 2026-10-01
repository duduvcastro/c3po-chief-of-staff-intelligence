#!/usr/bin/env bash
# Close production container remediation lanes made obsolete by a clean scan.
# Called only after `c3po_container_remediation.py plan` validated this run's
# complete production report and found zero fixable findings. Each lane is
# re-checked against its own trigger evidence and must be machine-owned (only
# the trigger file changed, every commit by github-actions[bot]); any doubt
# keeps the lane open. One lane's failure never stops the others; failures are
# collected and the script exits non-zero at the end.
set -euo pipefail

report=${1:?validated production report is required}
lane_prefix=${2:?lane prefix is required}
run_url=${3:?scan run URL is required}

if [ "$lane_prefix" != "automation/container-security-rebuild-" ]; then
  echo "stale-lane reconciliation only covers production remediation lanes" >&2
  exit 1
fi
if [[ ! "$run_url" =~ ^https://github.com/[^[:space:]]+/actions/runs/[0-9]+$ ]]; then
  echo "invalid scan run URL" >&2
  exit 1
fi
test -f "$report"

lanes=$(gh pr list \
  --repo "$GITHUB_REPOSITORY" \
  --state open \
  --app github-actions \
  --limit 100 \
  --json number,headRefName,baseRefName,isCrossRepository \
  | jq -c --arg prefix "$lane_prefix" \
    '[.[] | select((.headRefName | startswith($prefix))
                   and .baseRefName == "main"
                   and .isCrossRepository == false)]')
rows=()
while IFS= read -r line; do
  rows+=("$line")
done < <(jq -r '.[] | "\(.number)|\(.headRefName)"' <<< "$lanes")
if [ "${#rows[@]}" -eq 0 ]; then
  echo "::notice::No open production remediation lane to reconcile"
  exit 0
fi

errors=()
for row in "${rows[@]}"; do
  IFS='|' read -r number branch <<< "$row"
  if [[ ! "$number" =~ ^[0-9]+$ ]] \
    || [[ ! "$branch" =~ ^automation/container-security-rebuild-[a-zA-Z0-9._-]+$ ]]; then
    errors+=("unexpected lane identity: $row")
    continue
  fi
  metadata="$RUNNER_TEMP/stale-lane-$number-metadata.json"
  trigger="$RUNNER_TEMP/stale-lane-$number-trigger.json"
  comment="$RUNNER_TEMP/stale-lane-$number.md"
  if ! gh pr view "$number" --repo "$GITHUB_REPOSITORY" \
    --json files,commits,comments > "$metadata"; then
    errors+=("#$number: lane metadata not readable")
    continue
  fi
  if ! git fetch --no-tags --quiet origin "refs/heads/$branch" \
    || ! git show "FETCH_HEAD:c3po/security/container-rebuild-trigger.json" > "$trigger"; then
    errors+=("#$number: trigger evidence not readable")
    continue
  fi
  if ! decision=$(python3 scripts/c3po_container_remediation.py stale-lane \
    --report "$report" \
    --trigger "$trigger" \
    --pr-metadata "$metadata" \
    --run-url "$run_url" \
    --comment "$comment"); then
    errors+=("#$number: stale-lane evidence check failed closed")
    continue
  fi
  if [ "$(jq -r '.close' <<< "$decision")" != "true" ]; then
    echo "::notice::Lane #$number kept open: $(jq -r '.reason' <<< "$decision")"
    continue
  fi
  if ! gh pr close "$number" --repo "$GITHUB_REPOSITORY"; then
    errors+=("#$number: close failed")
    continue
  fi
  echo "::notice::Closed stale remediation lane #$number after a clean production scan"
  if ! gh pr comment "$number" --repo "$GITHUB_REPOSITORY" --body-file "$comment"; then
    errors+=("#$number: closed, but the evidence comment failed")
  fi
done

if [ "${#errors[@]}" -gt 0 ]; then
  for error in "${errors[@]}"; do
    echo "::error::Stale-lane reconciliation: $error"
  done
  exit 1
fi
