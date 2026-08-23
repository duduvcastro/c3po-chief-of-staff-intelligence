# Day D B2 Restore Drill

Status: mandatory before deleting any local historical artifact.

The Backblaze account normally keeps paid downloads capped at US$0/day. A
restore drill is therefore an explicit, audited exception rather than an
implicit assumption that an upload is recoverable.

## Procedure

1. Select at least one immutable **raw data object** from the completed offload
   lot and record its key, byte length, local SHA-256, parent manifest, and
   drill timestamp. Re-downloading only the lot report is a transport smoke
   test and cannot authorize deletion of the lot's local raw data.
2. Temporarily raise the Backblaze paid-download cap to no more than
   **US$0.50/day**.
3. Download that object to a new temporary path. Never overwrite either the
   local source or a prior restore sample.
4. Verify the restored byte length and SHA-256 exactly match the immutable
   source manifest.
5. Write an append-only restore report containing the object identity,
   expected and observed bytes/checksums, timestamps, and pass/fail result.
   Failure evidence must also be persisted; a failed download or checksum may
   not disappear merely because the drill raised an exception.
6. Return the paid-download cap to **US$0/day** and record that restoration in
   the report.
7. Local deletion for the lot is allowed only when the upload manifest, remote
   object metadata, and restore report all pass. Any mismatch blocks deletion
   and quarantines the lot for review.

No automated process may raise the billing cap or delete local source data.
Both actions require an explicit operator decision and preserved evidence. A
future local-deletion PR must implement the raw-object drill and durable failure
reporting above before it can request deletion authority.

## Auditable operator commands

The offload command is read-only unless `--offload` is present. It verifies the
local source against its immutable Massive manifest, uploads both objects,
checks remote byte length and SHA-256 metadata, then uploads an immutable lot
report. It never removes local data.

```bash
python -m app.day_d_replay.b2_offload \
  --manifest /app/day-d-data/provider=massive/manifests/session_date=YYYY-MM-DD/manifest-TIMESTAMP.json \
  --lot-id qualification-lot-001 \
  --offload
```

After the operator temporarily raises the paid-download cap, the current restore
command downloads the small immutable lot report to a fresh path and writes
checksum evidence. This validates the basic restore path only. It does not
satisfy the raw-object sampling gate, authorize local deletion, or perform local
deletion. The operator must return the cap to US$0/day and record that fact; a
future deletion implementation must additionally restore and verify at least
one raw object from every affected lot and preserve both passing and failing
drill evidence.

```bash
python -m app.day_d_replay.b2_offload \
  --restore-report /app/day-d-data/provider=backblaze/offload/lot_id=qualification-lot-001/offload-TIMESTAMP.json \
  --restore
```
