# Day D Massive Stage 1 foundation

**Status:** owner-authorized foundation; capture and official replay remain disabled

Massive (formerly Polygon.io) Stocks Advanced is the independent SIP source for
the Day D replay. It does not replace EODHD in live production. Its role is to
audit trades, NBBO quotes, minute bars and corporate actions without asking the
same provider that generated the live signal to certify itself.

The owner authorization is machine-readable in
[`stage1_authorization.json`](./stage1_authorization.json). It supersedes only
the Stage 0 prohibition on purchasing Polygon/Massive. Raw capture, bulk
downloads, official replay and production trading changes remain unauthorized.

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
```

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

After this foundation is reviewed and merged, credentials may be installed on
the server and a plan-only probe may measure exact object sizes. Those measured
sizes feed the numeric T0 disk/CPU/I/O thresholds. No historical file is
downloaded until that six-hands gate is frozen.
