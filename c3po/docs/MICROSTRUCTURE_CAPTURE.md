# R2D2 microstructure raw capture foundation

The capture foundation preserves EODHD trade and quote payloads before the
existing five-minute aggregation discards event order and trade size.

The owner has authorized a controlled Stage 1 rollout after this readiness
change is reviewed and merged. Runtime remains disabled by default. Enabling
the single capture flag before the next US open starts only passive evidence,
derived aggregates and resource telemetry; it cannot affect trading decisions.

## Safety properties

- Disabled by default.
- Does not change subscriptions, ranking, entry, exit or risk logic.
- WebSocket processing never waits for disk writes.
- A bounded queue protects worker memory. Overflow is counted and logged rather
  than blocking the market loop.
- Files are append-only NDJSON, partitioned by New York session date and feed.
- Rotation creates a new part; an existing part is never truncated.
- PostgreSQL receives no raw ticks.
- The dedicated Day D mount keeps the spool across container replacement.

Each line contains provider/feed metadata, receive time, provider event time and
the exact decoded WebSocket payload in `payload_raw`. The wrapper schema is
versioned independently from future feature schemas.

## Configuration

```ini
C3PO_R2D2_MICROSTRUCTURE_RAW_CAPTURE_ENABLED=false
C3PO_R2D2_MICROSTRUCTURE_RAW_DIR=/app/day-d-data/provider=eodhd/microstructure/raw
C3PO_R2D2_MICROSTRUCTURE_RAW_QUEUE_SIZE=100000
C3PO_R2D2_MICROSTRUCTURE_RAW_ROTATE_MB=256
C3PO_R2D2_MICROSTRUCTURE_RAW_FLUSH_EVERY=1000
C3PO_R2D2_MICROSTRUCTURE_PROCESSOR_ENABLED=true
C3PO_R2D2_MICROSTRUCTURE_BBO_MAX_AGE_SECONDS=2
C3PO_R2D2_MICROSTRUCTURE_ALLOWED_LATENESS_SECONDS=2
C3PO_R2D2_MICROSTRUCTURE_AGGREGATE_QUEUE_SIZE=100000
C3PO_R2D2_MICROSTRUCTURE_TELEMETRY_ENABLED=true
C3PO_R2D2_MICROSTRUCTURE_TELEMETRY_INTERVAL_SECONDS=1
```

The processor and telemetry are subordinate to raw capture: with raw capture
off, neither starts. Enabling the one raw-capture flag therefore keeps source
evidence, derived aggregates and T0 resource telemetry aligned. The Compose
mount and runtime validation both require the spool to live under the dedicated
`/app/day-d-data` filesystem, with the same 20 GiB reserve as historical data.

Enabling capture requires the approved controlled worker restart. The Stage 1
rollout must verify disk growth, `accepted/written/dropped/write_errors`,
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

## Trade/BBO processor

The passive processor joins each trade to the latest **prior** BBO no more than
two seconds old. EODHD sends trades and BBOs on separate sockets, so this is an
auditable inference rather than an exchange-provided aggressor flag.

The closed classification order is:

1. above/below a fresh midpoint (`bbo_midpoint`);
2. at a fresh midpoint, higher/lower than the prior trade
   (`tick_rule_at_mid`);
3. with no fresh BBO, higher/lower than the prior trade
   (`tick_rule_no_bbo`);
4. unchanged trade inheriting the prior direction (`inherited_tick`);
5. otherwise `unknown`.

One- and five-second append-only aggregates preserve count and volume for every
method, buy/sell/unknown volume, CVD, trade intensity, trade-size moments,
spread mean/min/max, BBO-age mean/max/p50/p95, receive lag and OHLC. Late,
queue-dropped and policy-discarded events are counted in processing-time
buckets. A future BBO is never used, and raw NDJSON remains authoritative.

## One-second T0 telemetry

While capture is enabled, the worker writes one-second append-only observations
under `provider=eodhd/microstructure/telemetry`. Each row includes cgroup-level
CPU and RSS, actual sample gap, disk reserve/free bytes, raw and aggregate queue
depth/capacity/high-water, drop/error counters and trade/quote feed gaps. This
is the acceptance surface for the 09:30-09:35 ET burst during the first week.

Neither aggregates nor telemetry enter ranking, entry, exit or risk logic.
