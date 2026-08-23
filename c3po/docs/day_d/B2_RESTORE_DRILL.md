# Day D B2 Restore Drill

Status: mandatory before deleting any local historical artifact.

The Backblaze account normally keeps paid downloads capped at US$0/day. A
restore drill is therefore an explicit, audited exception rather than an
implicit assumption that an upload is recoverable.

## Procedure

1. Select one immutable object from the completed offload lot and record its
   key, byte length, local SHA-256, parent manifest, and drill timestamp.
2. Temporarily raise the Backblaze paid-download cap to no more than
   **US$0.50/day**.
3. Download that object to a new temporary path. Never overwrite either the
   local source or a prior restore sample.
4. Verify the restored byte length and SHA-256 exactly match the immutable
   source manifest.
5. Write an append-only restore report containing the object identity,
   expected and observed bytes/checksums, timestamps, and pass/fail result.
6. Return the paid-download cap to **US$0/day** and record that restoration in
   the report.
7. Local deletion for the lot is allowed only when the upload manifest, remote
   object metadata, and restore report all pass. Any mismatch blocks deletion
   and quarantines the lot for review.

No automated process may raise the billing cap or delete local source data.
Both actions require an explicit operator decision and preserved evidence.
