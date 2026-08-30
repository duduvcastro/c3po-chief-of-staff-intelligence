# R2D2 shadow candidate log V1 runbook

## Contract

- Frozen spec SHA-256: `e200f2e70aae134f6c669b547d4ff7e435b21c0159069df2b89a5f7f7f7ae83b`.
- The trading worker only serializes immutable observations while deciding. Database append
  happens after the entry path and its result is never read by trading.
- The nightly worker imports the signed entry-study compatibility and `measure_entry`
  functions. It has no provider client and makes zero external API calls.
- A first rejected row is retained per symbol/session/policy epoch. A later accepted row is
  additionally retained with its immutable `trade_id`; no row is updated, deleted or
  truncated.

## Runtime

`r2d2-worker` sets `C3PO_R2D2_SHADOW_CANDIDATE_LOG_ENABLED=true` and writes observations to
`r2d2_shadow_candidates`. The isolated `r2d2-shadow-candidate-worker` checks pending sessions
during the 00:00-08:00 BRT window and writes:

```text
/app/day-d-data/evidence/r2d2-shadow-candidate-log-v1/
  session_date=YYYY-MM-DD/
    candidates.jsonl
    report.json
    SHA256SUMS.json
```

The same facts are persisted in `r2d2_shadow_candidate_outcomes` and
`r2d2_shadow_candidate_reports`. All three tables reject `UPDATE` and `DELETE`.

## Supervised checks

Plan without writes:

```bash
docker compose --env-file .env -f c3po/compose.yml run --rm -T \
  r2d2-shadow-candidate-worker \
  python -m app.r2d2_shadow_candidate_outcomes plan --session YYYY-MM-DD
```

Run only after the US session has closed:

```bash
docker compose --env-file .env -f c3po/compose.yml run --rm -T \
  r2d2-shadow-candidate-worker \
  python -m app.r2d2_shadow_candidate_outcomes run \
  --session YYYY-MM-DD \
  --output /app/day-d-data/evidence/r2d2-shadow-candidate-log-v1/session_date=YYYY-MM-DD
```

Verify the immutable package:

```bash
cd /mnt/day-d-data/evidence/r2d2-shadow-candidate-log-v1/session_date=YYYY-MM-DD
sha256sum -c <(python3 - <<'PY'
import json
for name, digest in json.load(open("SHA256SUMS.json")).items():
    print(digest, name)
PY
)
```

## Failure and recovery

- A logger failure may mark only `shadow_candidate_log.status=degraded` in cycle metadata; it
  must not change a decision, trade, position or cycle success.
- `bar_unavailable` is coverage censorship. It is never counted as a numeric violation.
- The three-file package becomes visible only through an atomic directory rename; an
  interrupted staging write stays hidden and cannot masquerade as a completed report.
- If the worker stops after publishing the immutable package but before database registration,
  the next pass verifies every hash and recovers the outcome/report rows from that package.
- No formal interpretation is permitted before five collected sessions. Every
  `ledger_candidate_lines` item is an automatic draft with admission explicitly unauthorized.

## Deployment freeze

Merge and deploy are permitted before Sunday 30 August 2026 at night only after Fable's audit
and all five gates are green. Missing that window moves deployment to 6 September or later;
there is no deployment during the measurement week.
