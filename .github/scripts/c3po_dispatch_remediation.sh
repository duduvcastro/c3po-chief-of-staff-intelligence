#!/usr/bin/env bash
set -euo pipefail

branch=${1:?remediation branch is required}
remediation_key=${2:?remediation key is required}
pr_number=${3:?pull request number is required}

if [[ ! "$branch" =~ ^automation/container-security-rebuild-[a-zA-Z0-9._-]+$ ]]; then
  echo "invalid remediation branch: $branch" >&2
  exit 1
fi
if [[ ! "$remediation_key" =~ ^[0-9a-f]{64}$ ]]; then
  echo "invalid remediation key" >&2
  exit 1
fi
if [[ ! "$pr_number" =~ ^[0-9]+$ ]]; then
  echo "invalid pull request number: $pr_number" >&2
  exit 1
fi

expected_sha=$(git rev-parse HEAD)
previous_run_id=$(gh run list \
  --repo "$GITHUB_REPOSITORY" \
  --workflow c3po-pipeline.yml \
  --branch "$branch" \
  --event workflow_dispatch \
  --limit 1 \
  --json databaseId \
  --jq '.[0].databaseId // 0')

gh workflow run c3po-pipeline.yml \
  --repo "$GITHUB_REPOSITORY" \
  --ref "$branch" \
  -f "ref=$branch" \
  -f deploy=false \
  -f remediation=true

dispatch_info=""
for _attempt in 1 2 3 4 5 6 7 8 9 10; do
  dispatch_info=$(gh run list \
    --repo "$GITHUB_REPOSITORY" \
    --workflow c3po-pipeline.yml \
    --branch "$branch" \
    --event workflow_dispatch \
    --limit 20 \
    --json databaseId,headSha,url \
    | jq -r \
      --arg sha "$expected_sha" \
      --argjson previous "$previous_run_id" \
      '[.[] | select(.headSha == $sha and .databaseId > $previous)]
       | sort_by(.databaseId)
       | last
       | if . == null then "" else "\(.databaseId)|\(.url)" end')
  if [ -n "$dispatch_info" ]; then
    break
  fi
  sleep 2
done

if [ -z "$dispatch_info" ]; then
  echo "dispatch was accepted but its workflow run could not be identified" >&2
  exit 1
fi
IFS='|' read -r dispatch_run_id dispatch_run_url <<< "$dispatch_info"
if [[ ! "$dispatch_run_id" =~ ^[0-9]+$ ]] \
  || [[ ! "$dispatch_run_url" =~ ^https://github.com/ ]]; then
  echo "invalid dispatched workflow identity: $dispatch_info" >&2
  exit 1
fi

marker_file="$RUNNER_TEMP/container-remediation-dispatch-marker.md"
printf '%s\n\nDispatch de validação aceito: [run `%s`](%s), remediation `%s`.\n' \
  "<!-- c3po-container-remediation-dispatch:$remediation_key -->" \
  "$dispatch_run_id" \
  "$dispatch_run_url" \
  "$remediation_key" \
  > "$marker_file"
gh pr comment "$pr_number" \
  --repo "$GITHUB_REPOSITORY" \
  --body-file "$marker_file"

echo "::notice::Validation dispatch accepted as run $dispatch_run_id"
