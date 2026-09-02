#!/usr/bin/env bash
set -euo pipefail

# Execute from a GitHub-hosted runner.  Production only runs psql in the
# already-running database container; no API/service container is created.
: "${C3PO_PRODUCTION_HOST:?C3PO_PRODUCTION_HOST is required}"
: "${C3PO_PRODUCTION_USER:?C3PO_PRODUCTION_USER is required}"
: "${C3PO_SSH_KEY:?C3PO_SSH_KEY is required}"

if [[ $# -ne 1 ]]; then
  echo "usage: $0 OUTPUT_JSON" >&2
  exit 64
fi

output=$1
query=.github/scripts/c3po_interim_m1_server_aggregate.sql
reducer=.github/scripts/c3po_interim_m1_reduce.py

if [[ -e "$output" ]]; then
  echo "refusing to overwrite an existing evidence artifact" >&2
  exit 73
fi
if [[ ! -r "$query" || ! -r "$reducer" ]]; then
  echo "pinned query or reducer is missing" >&2
  exit 66
fi

umask 077
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
source_json="$scratch/server-aggregate.json"

ssh -i "$C3PO_SSH_KEY" \
  "$C3PO_PRODUCTION_USER@$C3PO_PRODUCTION_HOST" \
  "cd /opt/chief-of-staff-digital && \
   docker compose --env-file .env -f c3po/compose.yml exec -T \
     -e 'PGOPTIONS=-c role=pg_read_all_data -c default_transaction_read_only=on -c statement_timeout=120000 -c lock_timeout=5000' \
     db sh -ceu 'exec psql -X --no-psqlrc -qAt -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\"'" \
  < "$query" > "$source_json"

# Exit 3 is intentional when the persisted outcome source has any coverage
# gap.  In that case the reducer prints the exact runner-streaming fallback and
# does not create OUTPUT_JSON.
python3 "$reducer" \
  --input "$source_json" \
  --query "$query" \
  --output "$output"

test -s "$output"
