# Day D B2 Restore Drill

Status: mandatory before deleting a completed qualification tick lot.

The Backblaze account normally keeps paid downloads capped at US$0/day. A
restore drill is therefore an explicit, audited exception rather than an
implicit assumption that an upload is recoverable.

## Procedure

1. Confirm the immutable lot report contains exactly `trades` and `quotes` for
   one of the twelve frozen qualification sessions. Minute aggregates and
   every unlisted session are outside the deletion authority.
2. Select the **largest raw data object** from the completed offload lot and
   record its key, byte length, local SHA-256, version ID, parent manifest, and
   drill timestamp. Re-downloading only the lot report is a transport smoke
   test and cannot authorize deletion of the lot's local raw data.
3. Temporarily raise the Backblaze paid-download cap to no more than
   **US$0.50/day**.
4. Download that object to a new temporary path. Never overwrite either the
   local source or a prior restore sample.
5. Verify the restored byte length and SHA-256 exactly match the immutable
   source manifest.
6. Remove the temporary restored copy after verification so the drill itself
   cannot consume the spool that it is meant to release.
7. Write an append-only restore report containing the object identity,
   expected and observed bytes/checksums, timestamps, and pass/fail result.
   Failure evidence must also be persisted; a failed download or checksum may
   not disappear merely because the drill raised an exception.
8. Return the paid-download cap to **US$0/day** and write the separate,
   append-only billing-cap-cycle evidence.
9. Local deletion for the lot is allowed only when the upload manifest, lot
   report, raw restore report, cap evidence and a fresh B2 HEAD all pass. The
   fresh HEAD must match ContentLength, metadata SHA-256 and the exact version
   ID in the lot report. Any mismatch blocks deletion and quarantines the lot.

No automated process may raise the billing cap. Local deletion is an explicit,
plan-first operator action and is restricted in code to the RAW `trades` and
`quotes` objects listed by the immutable lot report. It never discovers delete
targets through directory listing or globbing, never deletes metadata or
manifests, and never deletes minute aggregates. A failed lot remains
quarantined until a six-hands review.

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

The legacy report-only restore remains a transport smoke test:

```bash
python -m app.day_d_replay.b2_offload \
  --restore-report /app/day-d-data/provider=backblaze/offload/lot_id=qualification-lot-001/offload-TIMESTAMP.json \
  --restore
```

The qualification RAW drill is plan-first. The first command prints the
largest-object selection and required headroom without downloading. Only the
second form performs the egress drill. It records failures and quarantines the
lot before returning an error.

```bash
python -m app.day_d_replay.b2_offload \
  --raw-drill-report /app/day-d-data/provider=backblaze/offload/lot_id=qualification-YYYY-MM-DD/offload-TIMESTAMP.json

python -m app.day_d_replay.b2_offload \
  --raw-drill-report /app/day-d-data/provider=backblaze/offload/lot_id=qualification-YYYY-MM-DD/offload-TIMESTAMP.json \
  --execute-raw-drill
```

After the operator has returned the provider cap to US$0/day, record the full
cap cycle. The timestamps must enclose the RAW drill; the code does not alter
the provider cap itself.

```bash
python -m app.day_d_replay.b2_offload \
  --record-billing-cap-cycle /app/day-d-data/provider=backblaze/raw-restore-reports/lot_id=qualification-YYYY-MM-DD/raw-restore-TIMESTAMP.json \
  --cap-elevated-at 2026-08-23T12:00:00+00:00 \
  --cap-restored-at 2026-08-23T12:05:00+00:00 \
  --temporary-cap-usd 0.5 \
  --operator Dudu
```

Deletion is also plan-first. Without `--execute-delete-lot`, the command prints
the exact report-derived targets, bytes and evidence chain and changes nothing.

```bash
python -m app.day_d_replay.b2_offload \
  --delete-lot /app/day-d-data/provider=backblaze/offload/lot_id=qualification-YYYY-MM-DD/offload-TIMESTAMP.json \
  --raw-restore-report /app/day-d-data/provider=backblaze/raw-restore-reports/lot_id=qualification-YYYY-MM-DD/raw-restore-TIMESTAMP.json \
  --billing-cap-evidence /app/day-d-data/provider=backblaze/billing-cap-evidence/lot_id=qualification-YYYY-MM-DD/billing-cap-TIMESTAMP.json

python -m app.day_d_replay.b2_offload \
  --delete-lot /app/day-d-data/provider=backblaze/offload/lot_id=qualification-YYYY-MM-DD/offload-TIMESTAMP.json \
  --raw-restore-report /app/day-d-data/provider=backblaze/raw-restore-reports/lot_id=qualification-YYYY-MM-DD/raw-restore-TIMESTAMP.json \
  --billing-cap-evidence /app/day-d-data/provider=backblaze/billing-cap-evidence/lot_id=qualification-YYYY-MM-DD/billing-cap-TIMESTAMP.json \
  --execute-delete-lot
```

After successful deletion the locked B2 object becomes the primary archive for
that RAW lot. The catastrophic fallback is a future Massive re-download,
verified byte-exactly against the ETag, ContentLength and checksums pinned by
the frozen T0 and lot evidence. The local minute-aggregate working set remains
an independent retained copy throughout.
