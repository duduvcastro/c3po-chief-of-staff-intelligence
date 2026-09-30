# Massive producer supervision — installation candidate

Offline candidate for the Thursday installation review. Nothing here has been installed, enabled, started, connected to Massive, or approved for live operation. The unit paths and dedicated `c3po-bar` account are the proposed contract; the operator must bind them to the approved host, release and account before installation.

## Process and restart contract

The timer requests one start at 09:29 New York time, Monday through Friday, and another 30 seconds after boot. The boot trigger recovers a host that was down at the calendar trigger. The wrapper checks the XNYS calendar (holidays and shortened sessions) and permits starts only from open minus 60 seconds until close. A boot outside that window produces a safe terminal refusal, with no token load or provider connection. The calendar trigger still runs normally on later days; missed calendar timers are not replayed (`Persistent=false`). The producer receives through close plus 91 seconds; no new connection starts after close. A late failure that cannot restart remains an explicit coverage gap.

The wrapper allows one initial attempt and **four retries**, with monotonic waits of **30, 60, 120 and 240 seconds** before retries 1–4. systemd requests restart on failure with a one-second floor; that floor is additional to the wrapper wait. With immediate connection failures, provider attempts occur approximately at 0, 31, 92, 213 and 454 seconds. A two-minute outage therefore leaves later retry opportunities instead of consuming the allowance in 90 seconds. This is bounded recovery, not an assurance of provider availability. Successful STOPPED/SESSION_LIMIT exits are not restarted. Exit 78 is a terminal refusal and suppresses restart.

Exclusive, fsynced per-session claims cap provider attempts at **five across process crashes, reboots and manual restarts**, regardless of `reset-failed`. Claims must not be deleted to replenish allowance. Waiting holds the supervisor lock, checks stop/window each second and reads no token until the delay finishes. A crash or interruption during the wait conservatively consumes that claim. Changing the dated manifest never resets allowance. systemd additionally caps six process starts in eight hours: five attempts plus one process that can emit the final exhausted-budget refusal. This outer guard also bounds crashes before Python reaches its own claim logic.

Manual wrapper invocation obeys the same growing delay and durable cap. Do not install another restart loop or a second timer. Existing journals and all prior session evidence remain intact. Recovery declares interruptions; a restart does not claim continuity or fill sealed gaps. Cooperative local locks do not prove provider-account exclusivity on other hosts; that remains the approved owner's responsibility.

## Required filesystem layout

| Path | Owner:group | Mode and role |
| --- | --- | --- |
| `/opt/c3po-bar` | `root:c3po-bar` | 0750; immutable installation parent, traversable by service group |
| `/opt/c3po-bar/current` and runtime subdirectories | `root:c3po-bar` | 0750 directories; 0640 source files; approved release, no service-user write access |
| `/opt/c3po-bar/venv` | `root:c3po-bar` | 0750 directories and executables, 0640 non-executable files; reviewed Python environment |
| `/etc/c3po-bar` | `c3po-bar:c3po-bar` | **0700** private configuration parent |
| `/etc/c3po-bar/manifests` | `c3po-bar:c3po-bar` | **0700**; dated manifest directory |
| `/etc/c3po-bar/manifests/YYYY-MM-DD.json` | `c3po-bar:c3po-bar` | **0600** regular single-link manifest |
| `/etc/c3po-bar/token` | `c3po-bar:c3po-bar` | **0600** regular single-link token, optionally trailing newline |
| `/var/lib/c3po-bar` | `c3po-bar:c3po-bar` | **0700** private persistent parent |
| `/var/lib/c3po-bar/journal` | `c3po-bar:c3po-bar` | **0700** approved epoch-bound parent; children owned by same uid |
| `/var/lib/c3po-bar/supervisor` | `c3po-bar:c3po-bar` | **0700** separate persistent attempt journal; claims 0600 |

Every ancestor must be a real, traversable directory without a symlink or an untrusted writable component. System ancestors such as `/etc`, `/opt`, `/var` and `/var/lib` retain their root-owned host policy; do not chmod shared system directories to 0700. `current` is a real release directory, not a symlink. Root-owned installation files are read-only to the service; `ProtectSystem=strict` adds a runtime read-only boundary for configuration and code. The two `/var/lib/c3po-bar` child directories are the only persistent writable paths granted to the service.

The manifest uses the existing `run_session` schema. `owner_uid` must equal the actual numeric uid of `c3po-bar`; no uid is copied from another environment. Keep token bytes out of environment files, unit text, CLI arguments, logs and review receipts. This wrapper reads the file privately into memory and does not use the producer CLI's token environment option.

Terminal refusal receipts retain `reason=SUPERVISOR_REFUSED` and add a safe `code`. Codes distinguish `SUPERVISOR_WINDOW`, `SUPERVISOR_SESSION`, `SUPERVISOR_ATTEMPTS_EXHAUSTED`, `SUPERVISOR_MANIFEST_CHANGED`, `SUPERVISOR_CLAIM_INVALID`, `SUPERVISOR_PRIVATE_FILE`, `SUPERVISOR_FILE_CHANGED`, `SUPERVISOR_TOKEN`, `SUPERVISOR_MONOTONIC`, and `SUPERVISOR_FILE_UNAVAILABLE`. Producer/lock failures may expose only a constant code already defined in the reviewed producer modules. All other errors become `SUPERVISOR_UNVERIFIED`; raw exception text, paths and credentials are never copied into notices. BACKOFF receipts record attempt number and wait seconds. Route these fixed codes to the approved alert destination.

## Installation sequence for the authorized operator

1. Bind and approve the host/account, exact release, Python environment, epoch journal and daily universe. Confirm a single provider connection owner, disk/index budget and entitlement. Preserve all existing epoch data.
2. Provision the dedicated account and directories with the metadata above. Provision the approved token through the private secret channel; do not paste it into a shell command or installation receipt.
3. Place these two units in the approved systemd unit directory. Validate them using the installed systemd version's `systemd-analyze verify`; this repository's offline tests do not prove that host's compatibility. Confirm XNYS timezone resolution, hardening permissions and venv accessibility.
4. After separate activation authorization, reload the service manager and enable/start only the timer. Installation of this package is not that authorization. A same-session manual start consumes one of the five attempts.
5. Verify the unit configuration, timer's next trigger and structured receipts. Route journal events `DATA_GAP`, `FAILED`, start-limit exhaustion and service failure to the approved alert destination. An alert destination has not been invented or configured by this candidate.

SIGTERM requests orderly shutdown. systemd allows 30 seconds before terminating the service group; a forced stop consumes its attempt and the next recovery treats it as a gap. Do not infer clean coverage from exit 0 or a service-manager healthy state. Retain ATTEMPT, STARTING, budget and terminal stdout records through the approved journal retention policy. Keep receipt redaction and visibility restricted to the operational owner.

## Clock behavior

Authentication/liveness/runtime deadlines already use monotonic time. The producer now injects that clock into minute scheduling and anchors the daily end deadline to elapsed time at startup. A 5 ms UTC rollback neither crashes the scheduler nor extends the session runtime. A minute expires only after both its monotonic elapsed deadline and market UTC deadline have passed. Provider timestamps and actual received/available timestamps are never rewritten. Larger UTC corrections can delay evidence; no fabricated timestamp or completeness assertion compensates for that.

## Offline verification and pending checks

Tests exercise rollback by 5 ms, monotonic reversal, forward UTC jump, exact daily stop, five persisted failures followed by zero-connection refusal, changed manifest refusal, unsafe token metadata/types, window refusal and successful exit behavior. Existing producer/transport/service/scheduler regression suites run with injected clocks and sockets. Focused type checking covers all four changed/new runtime modules. Native systemd loading, alert delivery and real provider/host behavior are deliberately untested until separately authorized.
