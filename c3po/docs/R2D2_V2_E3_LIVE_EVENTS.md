# E3 live observation port — implementation for cross-audit

This package implements signed amendment 3 revision 3, SHA256
`3319407afcd7760668e6ec73bb4686ecb95a38eecf47fc157050899f80a6cc9c`.
It ships no producer credentials, provider call, scheduler, approved release,
human consent, or permission to collect, trade, merge or deploy. The new package
requires the separate receipts described in `R2D2_V2_EARNINGS_PACKAGE_V1.md`.

## Observation and announcement are different clocks

The admission policy's signed lower boundary is **10:00 America/New_York**.
`evidence.decision_at` records that nominal boundary. The candidate's factual
clock must be within the capture minute and proves when all inputs were locally
available; it does not move the earnings exclusion boundary. The gate recomputes
the producer's classifications and exclusion against that nominal lower bound
and the independently supplied official maturity. It preserves mismatches as
completed, invalid DATA. See `R2D2_V2_E3_POLICY.md`.

After admission, the live event instead intersects **each episode's original
opened_at and maturity_at**. `DAY`, `BMO` and `AMC` include both NY boundary dates.
`INSTANT` uses the inclusive real episode instants and a matching NY event date.
No source-provided timing classification proves that a report was published.
Non-session event dates use the signed DAY convention in the audited producer;
this pure ledger cannot discover an exchange calendar.

## File event envelope

The outer `V2_SHADOW_SOURCE_EVENT_V2` envelope and its private immutable bytes,
sequence, provenance and hash remain as defined by the existing file port.
The event body keeps `type`, `at`, `available_at`, `session`, `instrument_key`.
`at` is the source's **first local detection**, never the report date or a
backfilled 18:00. The collector archives that body, retains its original
availability as `source_available_at`, and uses its own actual consumption
instant as the ledger's `available_at`. A delayed file never grants earlier
knowledge to the collector.

Both `EARNINGS` and `EARNINGS_OBSERVATION_FAILED` require:

- `earnings_policy_sha`: the exact signed amendment hash above.
- `round_id`: SHA256 reference to the retained immutable round receipt.
- `round_session`: ISO date of the scheduled official session.
- `round_received_at`: actual receipt, at or after that session's 18:00 NY target.
  Late rounds retain their scheduled session. The collector also checks the
  official calendar and that the receipt follows the session's official close.
- `observation_window`: two strict ISO dates of the actual query. Each live
  episode requires its own entry date through maturity date plus 15 calendar
  days. Insufficient coverage marks that episode's observation failed.

`EARNINGS` additionally requires `earnings_event_id`, `revision_sha256`,
`event_date`, `granularity`. `event_at` is required **only for INSTANT**, and
must be absent for coarse events. The semantic revision hash commits to
`earnings_event_id`, event date, granularity and the instant normalized to UTC
(null in the hash material for coarse events); canonical JSON is ASCII, sorted,
compact, finite. This keeps equivalent timezone spellings in one revision.
The source must assign the same event identity across observations. The round
identity remains separate. An identical event revision seen again for the same
episode preserves its first detection even after a durable JSON restart.

`EARNINGS_OBSERVATION_FAILED` instead requires a controlled `reason`, either
`EARNINGS_SOURCE_UNAVAILABLE` or `EARNINGS_EVIDENCE_INVALID`. It does not create a
sale or replace failure with an empty calendar. Open episodes become unobservable
under the existing irreversible data-order rules; subsequent prices do not erase
the missing observation. Closed episodes and their cash never change.

An intersecting new revision creates an EVENT intent at first collector detection.
The first valid regular quote with **both source sides strictly later** than
that intent can supply the hypothetical exit. Quotes already known at detection
do not supply a retrospective exit. Existing barrier and maturity ordering rules
remain in force. A late detection cannot redefine an episode's N10 endpoint.

## Public diagnostics and remaining evidence obligation

The status view aggregates the eight E3 codes by session and arm. Before a DATA
exclusion there is no admitted research arm: its counter uses the same R1 risk
threshold only when the risk score is valid, and otherwise `UNASSIGNED`. This
basis is explicitly labeled and does not enroll excluded candidates in either
arm. Live detection counts use actual admitted episode arms and count distinct
episode/revision pairs on their factual detection sessions.
`earnings_observation_dates` also publishes factual NY dates whose economic
session has not opened yet. A round consumed at 09:00 belongs to today's
observation date, while the ledger can still retain yesterday's processing
session. This does not open an economic session early or backfill yesterday.

The exit diagnostic uses each factual exit-receipt session: EVENT exits divided
by all episodes closed in that session/arm, with an empty denominator represented
by null. Mean detection-to-exit delay uses observed EVENT exits only. No such
fraction measures unseen events, equal exposure, or negative feed completeness.
The inference estimator and accepted CAL-3 calibration are unchanged.

The consumer validates a referenced receipt's structure and event facts; it does
not fetch the referenced provider bytes. The separately audited producer must
retain round bytes, clocks and windows, validate calendar/history/last-published
evidence, preserve the conservative union, emit failed or missing-response rounds,
and demonstrate the actual 18:00 schedule before source readiness is signed.
**No event file is not proof of a successful empty round.** These requirements
remain activation blockers. No timeout, success receipt or error is fabricated
from silence by this implementation.
