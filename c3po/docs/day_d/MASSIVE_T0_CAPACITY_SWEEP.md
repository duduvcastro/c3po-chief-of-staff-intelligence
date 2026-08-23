# Day D Massive T0 capacity sweep

**Status:** measured with provider metadata only; first historical byte remains blocked

The first complete T0 sweep used S3-compatible `HeadObject` calls only. It did
not download, decompress, slice, or replay any Massive Flat File. The immutable
server report is stored outside Git at:

```text
/app/day-d-data/provider=massive/plans/t0-plan-sweep-20260823T015935.279879Z.json
```

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

## Thresholds derived from the sweep

These values are measured proposals for the six-hands T0 freeze. They do not
authorize a download.

- Dedicated data-disk reserve: 20 GiB.
- Per-session abort threshold: 23.671 GiB, equal to 21.519 GiB x 1.10.
- Local spool ceiling: 71.013 GiB, equal to three abort-threshold sessions.
- Per-object verification: local bytes must match planned `ContentLength`
  exactly, followed by a remote re-HEAD whose `ContentLength` and ETag must
  still match the plan.
- Campaign backstop: realized bytes above the complete plan by more than 5%
  pause the campaign for six-hands review.

The application disk cannot satisfy these thresholds. A separate 100 GiB data
disk is the minimum proposed spool, and raw retention requires object storage.
The owner must approve both the disk purchase and the raw-retention scope before
the first historical byte is downloaded.

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

1. Owner approval of the dedicated disk and object-storage retention policy.
2. Six-hands freeze of the numeric thresholds above.
3. Freeze of the dataset drop/clamp counters and policy before dataset build.
4. Reviewed deployment of API-key redaction, post-download re-HEAD, orphan-part
   quarantine and the single-writer download lock.
