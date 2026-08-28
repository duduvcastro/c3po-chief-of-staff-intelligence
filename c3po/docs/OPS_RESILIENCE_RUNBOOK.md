# RESILIENCE_OPS_V1 Runbook

Operational companion to the canonical relay document with SHA-256
`88fdf9b7d6866b471efe9728fae303e1cf9a38a2d632c13537bcb1812e3b31c1`.
This runbook does not grant signatures or alter that document.

## Factual baseline

The read-only production audit on 2026-08-27 found:

- PostgreSQL database size: `2,395,020,311` bytes (`2,284 MB`).
- No PostgreSQL dump timer, service, cron entry, or dump artifact on the host.
- The configured Backblaze bucket contained zero PostgreSQL-like objects.

The database therefore had no offsite backup before this implementation.

## Offsite storage contract

Use a dedicated Amazon S3 general-purpose bucket in `us-east-1`:

- Block all public access.
- Enable S3 Versioning before the first object.
- Use default SSE-S3 encryption.
- Daily prefix: `c3po-postgres/daily/`; retain 35 days.
- Monthly prefix: `c3po-postgres/monthly/`; retain 366 days.
- Transition both prefixes to S3 Glacier Flexible Retrieval after two days.
- Configure current and noncurrent lifecycle expiration explicitly.

The host credential has only `s3:PutObject` on
`arn:aws:s3:::<bucket>/c3po-postgres/*`. It has no list, get, delete,
version-delete, lifecycle, bucket-policy, or bucket-management permission.
Object keys include the dump SHA-256 and uploads use `If-None-Match: *`.

The monthly restore workflow uses a different GitHub environment credential
with `s3:GetObject` only on the same prefix. It has no write or delete access.

## Backup execution

`c3po-postgres-backup.timer` runs every day at 04:00
`America/Sao_Paulo` and is persistent. The service:

1. creates a PostgreSQL custom-format compressed dump;
2. rejects an empty or 5 GiB-or-larger archive;
3. validates the archive with `pg_restore --list` before upload;
4. computes SHA-256 and uploads a content-addressed object;
5. writes `preflight.json`, `dump.json`, `upload.json`, `result.json`, and
   `SHA256SUMS` under `outputs/evidence/postgres-backup/`;
6. removes the local dump in all exit paths.

The server credential cannot verify or restore the remote object by design.
Upload response, version ID, object key, local hash, and size are preserved as
evidence. Restoration is independently verified outside the server.

## Restore drill

The GitHub workflow `Monthly PostgreSQL offsite restore drill` runs on the first
day of each month at 10:00 UTC and is also manually dispatchable. It downloads
the latest immutable object, verifies SHA-256, restores into an isolated
PostgreSQL 16 container, and requires all five critical tables:

- `analysis_snapshots`
- `r2d2_experiments`
- `r2d2_trades`
- `r2d2_entry_score_observations`
- `r2d2_cash_yield_ledger`

The drill writes immutable evidence both as a GitHub artifact and under
`outputs/evidence/postgres-restore-drill/` on the production host.

## Dead-man checks

Healthchecks.io Hobbyist monitors these jobs without receiving logs or job
payloads:

- valuation off-hours worker;
- cash-yield phase;
- code census;
- governance and vulnerability attestation;
- PostgreSQL backup;
- monthly PostgreSQL restore drill.

Each integration sends `/start`, base success, or `/fail`. A ping failure is
logged but never changes the monitored job result. The schedules and grace
periods configured in the Healthchecks console are:

| Check | Schedule | Grace period |
| --- | --- | --- |
| Valuation worker | daily | 2 hours |
| Cash yield | daily | 4 hours |
| Code census | daily | 1 hour |
| Governance & vulnerabilities | daily at 02:15 BRT | 2 hours |
| PostgreSQL backup | daily | 2 hours |
| Restore drill | `0 10 1 * *` UTC | 2 hours |

Any console change to these values must update this runbook and the deployment
evidence in the same audited change.

### Mandatory check arming

A newly created Healthchecks check is not operational evidence until it has
received its first successful ping. The provider's `New` state does not start
dead-man alerting, so an unarmed check is invisible silence rather than a
working monitor.

For every new or replaced check:

1. create it with the audited schedule, grace period, and integration;
2. install its ping URL only through the approved secret path;
3. send one supervised success ping from the configured production or GitHub
   environment, without printing the URL or job payload;
4. refresh the Healthchecks console and verify that the check is no longer
   `New`, has a factual `Last Ping`, and retains the expected integration;
5. only then declare that dead-man check armed and trust missed-ping alerts.

An HTTP `200` from the ping call is necessary but not sufficient: the console
state and `Last Ping` are the authoritative arming evidence.

## Sentry

Sentry Developer is default-off when `C3PO_SENTRY_DSN` is empty. When enabled:

- only the official `sentry.io` SaaS DSN is accepted;
- `send_default_pii=false`;
- query strings, cookies, request environment, user context, authorization,
  tokens, secrets, passwords, session identifiers, and DSNs are removed;
- local variables and traces are disabled;
- events carry the deployed build SHA and service name.

API and worker containers must be recreated after the DSN is installed.

## Storm Troops controls

Storm Troops exposes the three resilience services without treating mere
configuration as operational evidence:

- `PostgreSQL offsite backup` is healthy only when the latest daily package has
  a valid `SHA256SUMS`, a valid report self-hash, a reconciled upload to the
  configured S3 bucket, is at most 30 hours old, and a successful restore drill
  is at most 35 days old. It becomes attention during the documented grace
  windows and offline for invalid or materially stale evidence. The API never
  tries to list or read S3 with the intentionally write-only host credential.
- `Healthchecks.io` requires all six dead-man checks to be configured and the
  SaaS endpoint to be reachable. Ping URLs are never displayed, logged, or used
  by the dashboard probe because probing them would fabricate job success.
- `Sentry` requires an official `sentry.io` DSN and a reachable SaaS status
  endpoint. The card proves configuration and provider availability; error
  delivery remains observable in the Sentry project and its alert policy.

## Governance and vulnerability monitor

At or after 02:15 `America/Sao_Paulo`, the server-usage worker performs one
read-only GitHub attestation per day. It records only open Dependabot counts by
severity and the live branch-protection fields defined by
`c3po/docs/GOVERNANCE_VULNERABILITY_BASELINE_V1.json`; alert titles, CVEs,
package names, and secret values are never persisted. The daily report is
append-only, self-hashed, and retried no more often than every 30 minutes after
a failed attempt.

The production token is stored only as `C3PO_GITHUB_GOVERNANCE_TOKEN` in the
sealed `.env`. It requires read access to Dependabot alerts and repository
administration metadata, and no write permission. A baseline change requires a
reviewed PR. `enforce_admins=false` remains expected only while the daily report
publisher still depends on direct push; its reason is part of the baseline.

The monthly restore check URL remains only in the GitHub `production`
environment. The production host stores a boolean attestation that the sixth
check was present during the audited installer run, never the secret ping URL.

## Deployment order

1. Create the S3 bucket, lifecycle, writer, and restore-reader credentials.
2. Create the Healthchecks project/checks and Sentry project/alert.
3. Store every credential as a GitHub `production` environment secret.
4. Merge only after independent audit.
5. Let the normal production pipeline deploy the audited commit.
6. Dispatch `Install RESILIENCE_OPS_V1 in production` for that exact commit.
7. Run `c3po-postgres-backup.service` once under supervision.
8. Dispatch the restore drill and validate both evidence packages.
9. Only then declare the backup control operational.
