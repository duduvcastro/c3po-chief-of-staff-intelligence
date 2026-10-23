# OPERATIONAL_INCIDENT_LEDGER_V1

## Decision

Operational failures have one central lifecycle in Storm Troops. The ledger records
the opening signal, owner acknowledgement, resolution evidence, and any later
reopening without rewriting prior events.

## Contract

- Stable `incident_key` groups repeated observations of the same condition.
- State is derived from append-only events: `open`, `acknowledged`, `resolved`.
- Identical observations are idempotent; changed evidence creates an `observed`
  event and a post-resolution signal creates `reopened`.
- Evidence is structured and hashed. Secrets, endpoints, tokens, and raw external
  payloads are forbidden.
- All authenticated users may read; only the owner may acknowledge or resolve.
- Resolution requires a factual note of at least three characters.
- Governance/vulnerability attestations, critical job failures, and disk-threshold
  signals are wired producers. Other workers join through the same service without
  changing this contract.

## Acceptance

- The complete lifecycle remains queryable after resolution.
- Repeated identical signals do not inflate history.
- Storm Troops names active and critical counts and exposes owner actions.
- A healthy governance attestation resolves its prior incident mechanically.

## Post-deploy governance waits

`post_deploy_grace` is part of the hashed governance attestation. It can defer
only a new `governance-vulnerability` signal for an otherwise healthy, explicitly
declared wait for deployment, npm evidence or the post-deploy image scan. The
earliest first-observation/deployment deadline bounds the wait to three hours;
chained merges and deploys do not restart it. Missing, malformed or legacy
evidence grants no grace. Real findings, errors, unhealthy components and the
deadline itself use the normal incident path, with Portuguese blocker causes.

The health card stays amber and names the deployed revision, pending work and
deadline. A grace never resolves an incident, lowers severity or hides an open or
acknowledged episode. A deferred opening produces no push or escalation; those
mechanisms remain unchanged for a signal that is actually due.

The `server-usage-worker` re-attests about one minute after the routine evidence
changes and at the grace deadline, using the same supervised incident lifecycle
and failure backoff. It does not use provisional values from a valid `observed`
report younger than ten minutes. If the other five layers are healthy, it waits
for finalization, including at the deadline, retrying at most once per minute.
A real cause in another layer is signalled immediately: the attestation keeps
only the routine's schema, hash and timestamp, explicitly marked preliminary,
without treating unfinished fields as a routine failure. It rechecks the routine
when that observation reaches ten minutes or a final report arrives.
The normal hourly attestations remain, and the other worker tasks keep their
configured cadence. An old routine report without explicit blockers retains the
previous incident behavior, so the rollout may itself cause one final transient
episode. This does not change owner acknowledgement or resolution permissions.

## Signatures

- Dudu: ordered in the Codex chat on 2026-08-29.
- Codex: technical GO and implementation on 2026-08-29.
- Fable: pending PR audit; merge is forbidden before approval.
