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
- monthly PostgreSQL restore drill;
- unattended-upgrades;
- daily Trivy scan of production images, plus a redundant weekly full scan.

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
| Unattended-upgrades | daily via `apt-daily-upgrade.timer` | 4 hours |
| Trivy production images | daily at 00:17 BRT (`17 3 * * *` UTC); redundant Sunday 04:00 BRT (`0 7 * * 0` UTC) | 2 hours |

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
- `Healthchecks.io` requires all eight dead-man checks to be configured and the
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
reviewed PR. The publisher writes to the separate private
`c3po-r2d2-reports` repository,
never to this repository. It pushes a dated `daily-export/YYYY-MM-DD` branch;
that repository validates the five allowed CSV files, records a pull request,
and merges only the validated PR. The C3PO `main` branch therefore requires
`enforce_admins=true`, with no publisher exception in the baseline.

The monthly restore and daily Trivy check URLs remain only in the GitHub
`production` environment. The production host stores boolean attestations that
those checks were present during the audited installer run, never their secret
ping URLs. The unattended-upgrades URL is stored separately as root-only mode
`0600` host configuration and is not passed into application containers.

## Host OS and production image vulnerabilities

`HOST_VULNERABILITY_CONTRACT_V1` extends the daily Governance attestation to
the server. `/usr/local/sbin/c3po-host-security-snapshot` refreshes
`runtime/security/host-os-vulnerability-report.json` every 15 minutes. The apt
contract clears the default unattended origins, permits only security/ESM
security channels, and pins `Automatic-Reboot=false`.

The normal build pipeline scans backend and frontend images with the immutable
Trivy image recorded in `scripts/c3po_trivy_scan.py`. It is deliberately
non-blocking. The daily `Scan production container vulnerabilities` workflow
exports the three images actually running on the host, scans them on a GitHub
runner, and atomically installs only the normalized count report at
`runtime/security/container-production-vulnerability-report.json`. Trivy and
its vulnerability database never consume production CPU or disk.
No workstation, desktop Codex automation, or owner device participates in this
schedule; an offline owner device cannot delay or suppress a scan.
The same complete scan runs again every Sunday at 04:00 BRT as a redundant
weekly checkpoint. After a remediation deployment, operators dispatch this
workflow immediately instead of waiting for either scheduled execution.

After each successful scan, a second GitHub-hosted job validates the report
self-hash, scope, dead-man, detailed `FixedVersion` evidence and aggregate
counts. If Critical or High fixes exist and no remediation lane is already
open, it creates `automation/container-security-rebuild-<report hash>`, changes
the tracked rebuild token, opens one PR and dispatches the five validation gates
with `deploy=false`. The job is intentionally isolated from the production
environment and has no SSH key; conversely, the scan job cannot write to the
repository. An open remediation PR suppresses duplicates by a hash of the
fixable finding set; if genuinely new fixes appear while that PR is open, the
controller updates its rebuild token, appends the evidence and re-dispatches
validation in that same lane instead of opening another.

The generated PR is a work queue, not an approval. It blocks while any fixable
Critical/High remains in its image scan, never auto-merges and never deploys.
Codex adjusts packages or base digests when a plain rebuild is insufficient;
Fable performs the independent audit; Dudu only receives the final merge
authorization request. The dead-man succeeds only after both scan and remote
controller complete, so failure to create or dispatch the PR is observable.
The repository setting that permits Actions-created PRs is a one-time
prerequisite and is checked before mutation. Although GitHub groups create and
approve permission in one setting, this workflow contains no review, approval,
merge or auto-merge command; protected-branch approval remains external.

Both scheduled layers carry their own dead-man evidence. The apt service sends
`start` and a systemd `OnSuccess`/`OnFailure` result around its factual daily
execution. The daily workflow does the same around the off-host scan. Ping
delivery itself is best-effort and cannot change an apt or scan result. A fresh
host snapshot must contain a configured dead-man and an unattended-upgrades
execution no older than 36 hours; the daily report must attest its dead-man
configuration. Missing execution evidence is amber even when vulnerability
counts are zero.

The Governance card labels image results as finding occurrences per image, not
unique CVEs. Missing host evidence after 2 hours or image evidence after 36 hours
is amber, never zero. Repository or image high/critical findings are red and
emit `governance_critical` through the existing best-effort push path.

### Manual reboot procedure

1. Schedule the reboot outside both B3 and US market hours and outside a study,
   backup, restore drill, or cash-yield run.
2. Confirm the latest PostgreSQL backup and restore evidence are healthy, then
   record the deployed revision and `docker compose ps` state.
3. Run `sudo systemctl reboot` from the production shell. There is no automatic
   reboot path in this contract.
4. Reconnect and verify the five application containers, PostgreSQL health,
   `c3po-host-security-snapshot.timer`, and the current `.deploy-version`.
5. Run `sudo systemctl start c3po-host-security-snapshot.service`; verify that
   `reboot_required=false` in the self-hashed report.
6. Run one supervised Governance attestation and confirm the card reflects the
   new host report without weakening any repository or image finding.

Base-image remediation is always a reviewed digest-bump PR. Findings are not
dismissed to turn the card green.

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
