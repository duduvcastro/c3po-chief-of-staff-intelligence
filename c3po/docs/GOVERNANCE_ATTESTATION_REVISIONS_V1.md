# GOVERNANCE_ATTESTATION_REVISIONS_V1

## Decision

Governance attestations are append-only revisions. More than one attestation may be
generated for the same Sao Paulo session date; the Storm Troops card reads the
latest revision and never rewrites or deletes an earlier report.

## Contract

- Identity is `(session_date, revision)`, with revisions starting at 1.
- Every revision is self-hashed and records the prior revision hash in
  `supersedes_report_sha256`.
- The existing database trigger continues to reject updates and deletes.
- The daily 02:15 BRT runner remains the automatic source.
- An owner-only `Atualizar agora` command may create another factual revision.
- The command returns hashes and metadata only; credentials and alert details are
  never returned or persisted.

## Acceptance

- Two runs on one date produce two immutable rows and the second points to the
  first hash.
- System health renders the newest revision.
- A non-owner cannot invoke the manual command.
- Existing daily scheduling and dead-man behavior remain unchanged.

## Signatures

- Dudu: ordered in the Codex chat on 2026-08-29.
- Codex: technical GO and implementation on 2026-08-29.
- Fable: pending PR audit; merge is forbidden before approval.
