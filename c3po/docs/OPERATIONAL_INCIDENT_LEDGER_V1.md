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

## Signatures

- Dudu: ordered in the Codex chat on 2026-08-29.
- Codex: technical GO and implementation on 2026-08-29.
- Fable: pending PR audit; merge is forbidden before approval.
