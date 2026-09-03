# CVE acceptance lane V1

This implementation is pinned to the signed specification
`CVE_ACCEPTANCE_LANE_V1` with SHA-256
`6a9dc31489959c0b5d4bcf7792e59ce6f6b2e7706802e8d2b0db9ac2e09cfd35`.
The versioned registry is `c3po/security/cve-acceptances.json`.

## Rollout guard

`C3PO_CVE_ACCEPTANCE_LANE_ENABLED` defaults to `false`. While it is off, the
governance v2 payload, card counters and critical-push signature retain the
pre-lane behavior. All attestation entrypoints now inject the already existing
incident ledger consistently; that reliability correction does not apply an
acceptance or change raw/pending counts. Enabling the overlay is a separate
post-gate production decision; this change does not enable it in any compose
file or environment.

The initial registry is deliberately empty. Nominal acceptance of the current
production findings must arrive in a separate PR with a specific justification
and three named hands for every occurrence.

## Registry contract

The registry is a JSON list. Every active entry has exactly these fields:

- `vulnerability_id`, `package`, `image`, `target`, `installed_version`;
- `justificativa` (non-empty and specific to the item);
- `accepted_by` (exactly the canonical three hands Dudu, Fable and Codex,
  compared after whitespace/case normalization);
- `accepted_at` and `review_at` (timezone-aware UTC timestamps, with
  `accepted_at < review_at <= accepted_at + 30 days`);
- `entry_sha256`, the lowercase SHA-256 of canonical JSON for the entry after
  removing `entry_sha256`.

An archived entry additionally has `archived_at`; it stays in the registry but
does not match a live occurrence. Unsupported fields, malformed timestamps,
invalid hashes, duplicate active identities and active entries absent from the
raw report fail the attestation closed. The SHA-256 of the exact registry bytes
is carried in the self-hashed governance attestation.

Registry changes happen only through the repository review path. There is no
HTTP write route and no runtime auto-accept path.

## Overlay and expiry

When the flag is enabled, the additive governance attestation schema is
`C3PO_GOVERNANCE_VULNERABILITY_REPORT-v3`; the default-off path continues to
emit the legacy v2 payload. The source
`C3PO_CONTAINER_VULNERABILITY_REPORT-v2` is never rewritten. Its
`report_sha256`, `finding_total`, `by_severity`, image data and remediation
controller input remain raw Trivy evidence. The governance report adds a
separate acceptance object with raw, accepted, pending and expired counters plus
per-occurrence statuses `pendente`, `aceito` or `aceito_vencido`.

Only a non-expired, entry-hashed, exact match on vulnerability, package, image,
target and installed version subtracts from pending. Accepted findings always
render amber and the card keeps both the actionable pending count and the raw
Trivy total visible. The governance incident uses pending counts. At the exact
UTC `review_at`, the occurrence becomes `aceito_vencido`, counts as pending,
and the next remote governance run opens or reopens the append-only central
incident with the expired entry hash in its evidence.

A newly published `FixedVersion` also ends the acceptance effect immediately:
the occurrence returns to pending while retaining the entry hash as evidence.
The remote remediation controller writes the matching `archived_at` and
recomputed entry hash into the same rebuild PR, so the registry cannot remain
active after the finding disappears from the post-deploy raw report. Synthetic
controller dry-runs never mutate the registry.

Pending critical/high occurrences drive the vulnerability incident. Medium/low
remain visible in the presentation counters but do not keep this incident open;
unidentified findings remain actionable attention because they cannot be joined
safely, and missing dead-man evidence also remains attention.

## Unknown/TEMP limitation

The current raw Trivy v2 contract retains identities only for detailed
critical/high findings. Findings without a catalog severity are intentionally
preserved only as the aggregate `unknown` counter. Because an aggregate cannot
be joined safely to a signed identity, UNKNOWN/TEMP findings remain pending and
cannot be accepted by V1. The implementation does not fabricate identities or
subtract aggregate counts. Supporting them requires a separately reviewed,
additive raw-evidence contract; it is not claimed by this rollout.
