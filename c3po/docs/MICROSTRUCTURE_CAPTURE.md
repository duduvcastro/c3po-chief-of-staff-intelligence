# R2D2 microstructure raw capture foundation

The capture foundation preserves EODHD trade and quote payloads before the
existing five-minute aggregation discards event order and trade size.

Under the signed Day D v1.2 blueprint, Stage 0 may inspect and specify this
component but may not enable it in production. A controlled rollout belongs to
Stage 1 and requires the disk guard plus pre-written numeric T0 acceptance
criteria first.

## Safety properties

- Disabled by default.
- Does not change subscriptions, ranking, entry, exit or risk logic.
- WebSocket processing never waits for disk writes.
- A bounded queue protects worker memory. Overflow is counted and logged rather
  than blocking the market loop.
- Files are append-only NDJSON, partitioned by New York session date and feed.
- Rotation creates a new part; an existing part is never truncated.
- PostgreSQL receives no raw ticks.
- A persistent Docker volume keeps the spool across container replacement.

Each line contains provider/feed metadata, receive time, provider event time and
the exact decoded WebSocket payload in `payload_raw`. The wrapper schema is
versioned independently from future feature schemas.

## Configuration

```ini
C3PO_R2D2_MICROSTRUCTURE_RAW_CAPTURE_ENABLED=false
C3PO_R2D2_MICROSTRUCTURE_RAW_DIR=/app/microstructure-raw
C3PO_R2D2_MICROSTRUCTURE_RAW_QUEUE_SIZE=100000
C3PO_R2D2_MICROSTRUCTURE_RAW_ROTATE_MB=256
C3PO_R2D2_MICROSTRUCTURE_RAW_FLUSH_EVERY=1000
```

Enabling capture requires a separately approved controlled worker restart. The
Stage 1 rollout must verify disk growth, `accepted/written/dropped/write_errors`,
feed continuity, CPU, RSS, iowait and queue lag before enabling long retention.

## Storage lifecycle

The Docker volume is a durable local spool, not the final archive. The next
Phase 0A increment must:

1. close completed session parts;
2. produce checksums and a manifest;
3. upload immutable parts to object storage;
4. verify the remote checksum;
5. compact to Parquet without deleting the original NDJSON until retention
   policy permits it;
6. delete local parts only after verified upload.

Object-storage credentials and bucket policy are deliberately not introduced in
this first PR. Silent local deletion is forbidden.

## Follow-up processor

The second increment joins each trade to the nearest non-stale prior BBO and
falls back to tick rule when no suitable BBO exists. It will emit one/five-second
aggregates containing buy/sell/unknown volume, CVD, trade intensity, size
percentiles, spread and data-quality coverage. Feature snapshots, including
non-operated candidates, will then feed live shadow and the future ranker.
