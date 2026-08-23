# Day D Massive Stage 1 foundation

**Status:** first-byte and passive live capture authorized; official replay remains disabled

Massive (formerly Polygon.io) Stocks Advanced is the independent SIP source for
the Day D replay. It does not replace EODHD in live production. Its role is to
audit trades, NBBO quotes, minute bars and corporate actions without asking the
same provider that generated the live signal to certify itself.

The owner authorization is machine-readable in
[`stage1_authorization.json`](./stage1_authorization.json). It supersedes the
Stage 0 prohibitions on purchasing Polygon/Massive and enabling passive EODHD
microstructure capture. Capture remains off by default until the reviewed
readiness merge and controlled worker restart. Bulk downloads beyond the
limited first-byte scope, official replay and production trading changes remain
unauthorized.

## Provider surfaces

- REST: `https://api.massive.com`, authenticated by API token.
- Flat Files: S3-compatible `https://files.massive.com`, bucket `flatfiles`,
  authenticated by a separate access key and secret.
- SIP stocks paths: `us_stocks_sip/trades_v1`, `quotes_v1`,
  `minute_aggs_v1`, and `day_aggs_v1`.
- Flat Files are unadjusted. The official dataset must bind point-in-time
  splits, dividends and other corporate actions before replay.

## Safety boundary

The new archive command is plan-only unless `--download` is provided. A
download then remains blocked unless the local disk has enough room for every
remote object plus the configured reserve. Files are written to a unique
temporary part, flushed, checked against the advertised byte count and moved
atomically into place. Existing files are reused only when their size matches;
they are never overwritten. Every batch receives a SHA-256 manifest and is
explicitly marked `official_replay_ready: false`.

Before publication, a downloaded object is re-checked remotely. A changed
ETag or byte count quarantines the local file instead of publishing it. A
single-writer filesystem lock prevents two operators from downloading into the
same spool concurrently, and abandoned `.part` files are moved into immutable
quarantine before the next approved run.

No application service invokes this command automatically. The API container
has a persistent `/app/day-d-data` volume solely so an explicitly approved
operator run survives container replacement.

## Configuration

```ini
MASSIVE_API_TOKEN=
C3PO_MASSIVE_PLAN=stocks-advanced
C3PO_MASSIVE_FLAT_FILES_ACCESS_KEY=
C3PO_MASSIVE_FLAT_FILES_SECRET_KEY=
C3PO_DAY_D_DATASET_ROOT=/app/day-d-data
C3PO_DAY_D_DATASET_MIN_FREE_DISK_GB=20
C3PO_DAY_D_DATA_MOUNT_SOURCE=/mnt/day-d-data
```

`C3PO_DAY_D_DATA_MOUNT_SOURCE` changes only the host-side Compose source. The
container path remains `/app/day-d-data`, so the application contract does not
depend on a host device name. Local development may omit the variable and keeps
the `c3po_day_d_data` named volume.

The REST token and S3 credentials must never be copied into Git, logs, issue
text or chat.

## Explicit operator flow

Read-only plan:

```bash
python -m app.day_d_replay.massive_archive \
  --session-date 2026-08-21 \
  --dataset trades \
  --dataset quotes
```

Approved download, only after T0 and retention review:

```bash
python -m app.day_d_replay.massive_archive \
  --session-date 2026-08-21 \
  --dataset trades \
  --dataset quotes \
  --download
```

## Next gate

Credentials are installed and the complete plan-only T0 sweep is documented in
[`MASSIVE_T0_CAPACITY_SWEEP.md`](./MASSIVE_T0_CAPACITY_SWEEP.md). No historical
file is downloaded until the dedicated data disk, retention destination and
numeric thresholds are approved and frozen by the six hands.
