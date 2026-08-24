# Day D Point-in-Time Qualification Universe

**Status:** proposed for six-hands review  
**Scope:** identity manifests for the twelve qualification sessions only

This boundary exists so R1 can slice each whole-market Massive Flat File to a
causal, immutable set of 60 tradeable stocks plus QQQ. It does not authorize
REST trades, REST quotes, the 252-session window, replay, strategy changes or
capital use.

## Narrow provider boundary

The only network path is `GET /v3/reference/tickers`. Each query uses:

- `market=stocks`;
- `active=true`;
- `date=<previous official session>`;
- `order=asc`, `sort=ticker`, `limit=1000`; and
- complete cursor pagination.

Every sanitized canonical page is stored immutably. The universe manifest
records its path, byte size, SHA-256, row count and request URL without the API
key. Request count is evidence metadata and never enters the frozen campaign
byte ledger.

The twelve D/D-1 pairs and their exact 20-session windows are frozen in
`qualification_calendar_v1.json`. This avoids calendar-day subtraction and
also pins the 13:00 ET close on 29 November 2024.

## Deterministic rule

1. Eligibility is point-in-time `market=stocks`, `active=true`, `locale=us`,
   USD, primary exchange `XNAS` or `XNYS`, provider type `CS`, and a non-empty
   CIK. Other provider types therefore exclude ADR/ADS, ETF/ETN/funds,
   preferreds, warrants, units, rights and OTC instruments. The manifest keeps
   the raw provider type and company name beside the internal eligible-class
   mapping, so the assumption remains inspectable rather than disappearing in
   normalization. No supplemental classification endpoint is authorized here.
2. For each eligible ticker, reconstruct each frozen regular session from the
   archived minute aggregates. Session dollar volume is the last regular-
   session close multiplied by the sum of regular-session minute volume.
   That product is invariant when a known split rescales price and volume in
   opposite directions; no future corporate action is used.
3. Require D-1 close at least USD 3 and exactly 20 complete observations.
4. Rank the median of the 20 session-dollar-volume observations descending.
   Break ties by normalized ticker, then raw ticker ascending.
5. Deduplicate issuers by CIK, retaining the highest-ranked share class, and
   select the first 60.
6. Add QQQ as row 61 with role `benchmark`; it is flagged, not ranked and not
   tradeable.

The builder fails closed on missing source metadata, source checksum drift,
missing ranking sessions, an incomplete QQQ window, pagination disorder,
duplicate tickers, fewer than 60 selected issuers or any immutable-evidence
conflict.

## Evidence chain and R1 gate

The manifest binds:

- all reference-page hashes;
- the frozen calendar hash;
- the 20 verified minute-aggregate parents;
- a canonical NDJSON file containing every derived ranking observation;
- the exact rule and exclusion counts; and
- the final 60 + QQQ rows.

R1 no longer accepts a caller-supplied symbol set. It requires this manifest,
verifies its self-hash and linked page/ranking artifacts, checks the session and
61-role structure, and derives `symbols_in_scope` from it. Each R1 file and
session manifest records the universe manifest path and SHA-256.

The operator command is plan-first. Without `--execute`, it performs no network
request and writes nothing. Execution additionally requires
`C3PO_DAY_D_POINT_IN_TIME_REFERENCE_AUTHORIZED=true` and an explicit,
timezone-aware `--captured-at`:

```bash
python -m app.day_d_replay.point_in_time_universe \
  --all-qualification-sessions

python -m app.day_d_replay.point_in_time_universe \
  --all-qualification-sessions \
  --execute \
  --captured-at 2026-08-24T12:00:00Z
```

The flag stays false until this change is reviewed and merged. Generation of
the twelve real manifests, R1, deletion and the next qualification lot remain
blocked until then.
