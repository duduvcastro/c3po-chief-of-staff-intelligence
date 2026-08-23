# Day D Massive T0 capacity sweep

**Status:** T0 frozen from provider metadata only; first historical byte remains blocked

The first complete T0 sweep used S3-compatible `HeadObject` calls only. It did
not download, decompress, slice, or replay any Massive Flat File. The canonical
immutable server report is stored outside Git at:

```text
/app/day-d-data/provider=massive/plans/t0-plan-sweep-20260823T021819.718086Z.json
```

Its SHA-256 is
`3b68d8f70197c6d257fe90e9d8e8360cfc48df123cd4c255c4acde97d9c0ceb2`.
The machine-readable freeze is
[`massive_t0_contract.json`](./massive_t0_contract.json).

That first operator report captured the aggregate distributions and stratified
spot checks. The canonical repository command added by the follow-up change
supersedes it by persisting every complete session, remote object key, byte
count and ETag, so future runs can be recomputed instead of trusted from a
summary.

## Measured campaign

- Range: 2021-08-23 through 2026-08-21.
- Weekday candidates: 1,305.
- Complete trading sessions: 1,255.
- Non-session weekdays: 50.
- Partial sessions: 0.
- Datasets: SIP trades, SIP quotes and minute aggregates.
- Provider metadata requests: 3,915.
- Source CSV files downloaded: 0.

| Dataset | p50 | p95 | Maximum | Five-year total |
|---|---:|---:|---:|---:|
| Trades | 1.438 GiB | 3.113 GiB | 3.947 GiB | 2,128.510 GiB |
| Quotes | 5.304 GiB | 9.944 GiB | 17.963 GiB | 7,297.761 GiB |
| Minute aggregates | 0.018 GiB | 0.026 GiB | 0.029 GiB | 24.084 GiB |
| Trades + quotes | 6.779 GiB | 12.535 GiB | 21.493 GiB | 9,426.271 GiB |
| All three | 6.796 GiB | 12.561 GiB | 21.519 GiB | 9,450.354 GiB |

The largest measured session was 2025-04-07. No session exceeded the
provisional 24 GiB abort threshold. Raw trades and quotes alone total about
9.20 TiB; all requested datasets total about 9.23 TiB.

## Frozen thresholds

These values were frozen by the six-hands review. They do not authorize a
download by themselves.

- Dedicated data-disk reserve: 20 GiB.
- Per-session abort threshold: 25,416,665,942 bytes, equal to the exact
  23,106,059,947-byte maximum multiplied by 1.10 and rounded up.
- Local spool ceiling: 76,249,997,826 bytes, equal to three abort-threshold
  sessions.
- Per-object verification: local bytes must match planned `ContentLength`
  exactly, followed by a remote re-HEAD whose `ContentLength` and ETag must
  still match the plan.
- Campaign backstop: realized bytes above the complete plan by more than 5%
  pause the campaign for six-hands review.

The application disk cannot satisfy these thresholds. The owner approved a
dedicated 100 GiB Lightsail data disk, the hybrid retention scope and Backblaze
B2 with a monthly budget of up to US$15. Provisioning and end-to-end checksum
verification remain required before the first historical byte is downloaded.

## Frozen hybrid retention

- Retain all five years of minute aggregates indefinitely.
- Download full ticks only for the 12 qualification sessions and the 252 most
  recent exchange sessions at the final preregistration hash.
- Retain immutable 61-symbol slices indefinitely, chained to the parent raw
  SHA-256.
- Retain complete raw files for processed sessions until the final verdict plus
  12 months.
- Do not archive the full five-year tick corpus.

## Reproducible command

After the reviewed code is deployed, the canonical read-only sweep is:

```bash
python -m app.day_d_replay.massive_plan_sweep \
  --start-date 2021-08-23 \
  --end-date 2026-08-21 \
  --dataset trades \
  --dataset quotes \
  --dataset minute_aggregates \
  --workers 6
```

This command has no download flag and calls only the archive planner. The
separate archive command remains plan-only unless an operator explicitly adds
`--download`, which is still prohibited by `stage1_authorization.json`.

## Remaining first-byte gates

1. Provision, mount and verify the dedicated 100 GiB data disk.
2. Provision Backblaze B2 and verify an upload/download/checksum round trip.
3. Complete the six-hands review of
   [`massive_ingestion_policy_v1.json`](./massive_ingestion_policy_v1.json).
4. Implement and test campaign-level byte accounting and the +5% pause guard.
