# Massive producer supervision — installation candidate

Offline candidate for the Thursday installation review. Nothing here has been installed, enabled, started, connected to Massive, or approved for live operation. The unit paths and dedicated `c3po-bar` account are the proposed contract; the operator must bind them to the approved host, release and account before installation.

## Process and restart contract

The timer requests one start at 09:29 New York time, Monday through Friday. The wrapper additionally checks the XNYS calendar (holidays and shortened sessions) and permits starts only from open minus 60 seconds until close. Missed timers are not replayed (`Persistent=false`). The producer receives through close plus 91 seconds; no new recovery attempt starts after close. A late failure that cannot restart must remain an explicit coverage gap.

systemd restarts failures with a fixed **30-second backoff**, at most **four starts in eight hours**. Successful STOPPED/SESSION_LIMIT exits are not restarted. Exit 78 is a terminal refusal and suppresses restart. The wrapper independently persists at most **four attempt claims per New York session**, holding an exclusive supervisor lock throughout the attempt. This cap survives process crashes, reboots and `reset-failed`; the files must not be deleted to replenish it. An existing attempt consumes allowance even if its process died before connecting. Changed daily manifest bytes refuse rather than resetting the counter. Existing journals and all prior session evidence remain intact. Recovery declares interruptions; restart does not claim continuity or fill sealed gaps.

The backoff is enforced by systemd's monotonic restart timer; the durable per-session counter is enforced by the wrapper. Calling the wrapper manually still consumes the same allowance but does not itself wait 30 seconds. Do not install an additional restart loop or a second timer. Cooperative journal locks prevent duplicate local owners, but provider-account exclusivity across other hosts still requires the approved operational owner.

## Required filesystem layout

| Path | Requirement |
| --- | --- |
| `/opt/c3po-bar/current` | Approved immutable release with `backend/app`; read-only to service user |
| `/opt/c3po-bar/venv/bin/python` | Reviewed Python environment with this release's dependencies |
| `/etc/c3po-bar/manifests/YYYY-MM-DD.json` | Approved dated epoch/session/symbols/owner_uid manifest; owned by service uid, mode 0600 |
| `/etc/c3po-bar/token` | Token only, optionally trailing newline; service uid, regular single-link file, mode 0600 |
| `/var/lib/c3po-bar/journal` | Existing approved epoch-bound parent journal, service uid, mode 0700 |
| `/var/lib/c3po-bar/supervisor` | Separate persistent attempt journal, service uid, mode 0700 |

Use real directories, with no symlink ancestors. The manifest schema is the existing `run_session` schema; its owner_uid must be the actual numeric service uid. Do not reuse the example uid from another environment. Keep token bytes out of environment files, unit text, CLI arguments, logs and review receipts. This entrypoint reads the file privately and injects the token into the producer in memory; it does not use the producer CLI's `--token-env` mechanism.

## Installation sequence for the authorized operator

1. Bind and approve the host/account, exact release, Python environment, epoch journal and daily universe. Confirm a single provider connection owner, disk/index budget and entitlement. Preserve all existing epoch data.
2. Provision the dedicated account and directories with the metadata above. Provision the approved token through the private secret channel; do not paste it into a shell command or installation receipt.
3. Place these two units in the approved systemd unit directory. Validate them using the installed systemd version's `systemd-analyze verify`; this repository's offline tests do not prove that host's compatibility. Confirm XNYS timezone resolution, hardening permissions and venv accessibility.
4. After separate activation authorization, reload the service manager and enable/start only the timer. Installation of this package is not that authorization. A same-session manual start consumes one of the four attempts.
5. Verify the unit configuration, timer's next trigger and structured receipts. Route journal events `DATA_GAP`, `FAILED`, start-limit exhaustion and service failure to the approved alert destination. An alert destination has not been invented or configured by this candidate.

SIGTERM requests orderly shutdown. systemd allows 30 seconds before terminating the service group; a forced stop consumes its attempt and the next recovery treats it as a gap. Do not infer clean coverage from exit 0 or a service-manager healthy state. Retain ATTEMPT, STARTING, budget and terminal stdout records through the approved journal retention policy. Keep receipt redaction and visibility restricted to the operational owner.

## Clock behavior

Authentication/liveness/runtime deadlines already use monotonic time. The producer now injects that clock into minute scheduling and anchors the daily end deadline to elapsed time at startup. A 5 ms UTC rollback neither crashes the scheduler nor extends the session runtime. A minute expires only after both its monotonic elapsed deadline and market UTC deadline have passed. Provider timestamps and actual received/available timestamps are never rewritten. Larger UTC corrections can delay evidence; no fabricated timestamp or completeness assertion compensates for that.

## Offline verification and pending checks

Tests exercise rollback by 5 ms, monotonic reversal, forward UTC jump, exact daily stop, four persisted failures followed by zero-connection refusal, changed manifest refusal, unsafe token metadata/types, window refusal and successful exit behavior. Existing producer/transport/service/scheduler regression suites run with injected clocks and sockets. Focused type checking covers all four changed/new runtime modules. Native systemd loading, alert delivery and real provider/host behavior are deliberately untested until separately authorized.
