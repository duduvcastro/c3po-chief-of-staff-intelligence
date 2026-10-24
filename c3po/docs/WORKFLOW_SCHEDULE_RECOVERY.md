# Missed workflow schedules

This is a separate, opt-in host safety net. Shipping this code does not install,
enable or start it. The existing deployment and security installers do not call
`scripts/install-workflow-schedule-recovery.sh`.

The hourly timer samples at minute 03 UTC. It tolerates the first 20 minutes after
a slot, then considers slots aged 20–80 minutes. Timer/runner/network jitter can
add delay; this is not an exactly 20-minute recovery guarantee. Old slots are not
replayed after a long outage. Only the latest eligible PIT tick is considered,
so an hourly check does not replay a backlog of half-hourly ticks.

| Workflow | Slots | Recovery inputs |
|---|---|---|
| `ops-readonly-report.yml` | Daily 03:30 and 08:30 America/Sao_Paulo | `recovery_slot` only |
| `decisor-verdict-export.yml` | Monday–Friday 08:00 America/Sao_Paulo | `night=""`, `recovery_slot` |
| `valuation-pit-grid-autopilot.yml` | Minute 13 and 43 of every UTC hour | `dry_run="false"`, `recovery_slot` |

An empty export night is the existing `last-completed` contract. The producer's
XNYS calendar resolves the last closed NYSE session, including holidays and
Monday→Friday. The host never guesses it by subtracting a civil day. Export
does not gain a weekend schedule. Ops runs daily; PIT ticks may run on weekends,
but the autopilot's existing order, `on`, expiry, active-run, failure-stop,
window and deployment guards still decide whether a chunk can start. This
feature does not approve PIT release, change parameters, dispatch the backtest
directly or fix previously published PIT findings. All dispatches target `main`.

The optional `recovery_slot` has a strict UTC slot format and is visible in the
run name. Workflows validate it without a token or API access. Ops uses it for
the original scheduled-slot comment marker. No workflow permissions change.
Ordinary scheduled and manual behavior is preserved.

## Durable behavior and failure handling

The service locks its private state directory for the entire cycle. A ledger
intent is atomically written and fsynced **before** each dispatch or comment
POST. Run and comment reads follow validated pagination; malformed, capped,
incomplete or unavailable collections fail closed. A queued, waiting,
in-progress or already completed run prevents recovery. A failed run counts as
having run: the safety net is not a workflow retry engine. PIT manual dry-runs
do not count as acting ticks. An unidentifiable manual export/tick stops that
slot's recovery rather than guessing the inputs.

After dispatch the service confirms a newly listed `workflow_dispatch` run on
`main`, with the exact recovery tag and observed main SHA, within 60 seconds.
The one-line receipt in #429 names the original UTC slot and confirmed run.
It records dispatch, never workflow success or PIT admission. Receipt posting
is separately confirmed by a complete GET. A lost response, timeout, crash,
changed main SHA or failed confirmation leaves a durable uncertain outcome;
later cycles only reconcile it. They never issue another POST blindly. An
uncertain run or receipt needs operator investigation if it never appears.
Do not delete/reset the ledger to clear that state without checking GitHub.

A second complete run listing immediately before POST catches an arriving
schedule. GitHub offers no atomic schedule/dispatch claim or idempotency key:
a delayed schedule arriving **after** that GET can still race the recovery.
Existing workflow concurrency serializes executions but cannot promise exactly
one execution. This ledger guarantees at most one recovery attempt per slot,
not exactly one execution of a GitHub schedule. No cancellation is attempted.
The existing PIT guards remain necessary for a late tick.

## Future operator installation

Only under separate operational authorization, stage the reviewed checkout with
`scripts/install-workflow-schedule-recovery.sh --install-only`. It copies the
script/units and verifies their syntax; it does not reload systemd, enable/start
timers, provision credentials or change the current deployment installer.
Provision `/etc/c3po/workflow-recovery.token` separately (root-owned 0600), using
the existing approved GitHub identity/scope for Actions read/write, contents
read and issue 429 comments. Do not broaden token privileges for this feature.
`LoadCredential` supplies it at runtime; the script never reads application
configuration, environment secrets, Docker or SQL. The state directory is
`/var/lib/c3po-workflow-schedule-recovery` (0700; ledger 0600).

Activation (`daemon-reload`, timer enable/start) is an operator step under that
separate authorization; neither staging nor a deploy activates recovery.
Maintenance/reboot hold files suppress the service, and explicitly disabled
GitHub workflows remain disabled. A manual script invocation defaults to plan
only; `--act` is required for POSTs. A missing/unreadable credential, unsafe
file mode or invalid ledger fails closed. No credential or raw GitHub body is
printed. This change has only simulated local validation, no host acceptance.
