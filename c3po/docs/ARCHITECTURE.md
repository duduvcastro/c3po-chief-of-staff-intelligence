# C3PO architecture

## Current system audit

The legacy application is a mature batch pipeline centered on
`work/morning_summary.py` (more than 11,000 lines). It already owns:

- Exchange email and calendar retrieval through EWS;
- BTG Billfish and brokerage-note attachment parsing;
- Pluggy/Open Finance collection and webhook ingestion;
- WhatsApp Web unread-message capture;
- market, weather, news and sports collection;
- candidate-stock screening and five-model valuation;
- HTML/PDF generation and email delivery;
- scheduled Morning, Lunch and Night Summary execution.

The AWS deployment uses Docker Compose, Caddy, a persistent WhatsApp session
and a lightweight Pluggy webhook service. The batch behavior remains the source
of truth while C3PO is introduced.

## Incremental target

```text
Data sources -> ingestion adapters -> normalized observations -> PostgreSQL
                                                    |             |
Legacy summaries -----------------------------------+             |
                                                                  v
                                               FastAPI read model/API
                                                                  |
                                                                  v
                                                  Next.js static frontend
```

### Design decisions

1. **Strangler migration**: C3PO reads legacy outputs first. Each source moves
   behind a dedicated adapter only after parity checks.
2. **Static frontend**: Next.js is exported at build time. This avoids a Node
   runtime on the 2 GB Lightsail instance.
3. **PostgreSQL first**: observations, methodology versions, feedback and
   audit records are durable from the beginning.
4. **No Redis in phase one**: PostgreSQL advisory locks and the existing cron
   are enough for one user and a small number of jobs.
5. **Immutable analysis snapshots**: a published valuation never changes in
   place. New inputs create a new snapshot linked to a methodology version.
6. **Explicit provenance**: every metric has an `as_of`, `collected_at`, source,
   quality score and optional raw-payload reference.
7. **Actions are gated**: the first release is read-only. Any future email,
   message or financial action must produce an audit event and follow an
   explicit confirmation policy.
8. **Passwordless private access**: only Death Star allowlisted emails receive
   a six-digit code valid for ten minutes. Codes are single-use, rate-limited
   and never stored in plaintext; authenticated sessions use Secure, HttpOnly,
   SameSite cookies with a twelve-hour lifetime. Per-module authorization is
   evaluated server-side on every API request, and the configured owner account
   is immutable.

## Migration phases

### Phase 1 - Foundation

- Command Center backed by the latest legacy report;
- integration health and report history;
- PostgreSQL schema, ingestion runs and feedback;
- responsive web shell and source freshness indicators.

### Phase 2 - Financial intelligence

- direct Brapi and EODHD adapters (quote foundation implemented);
- normalized securities, quotes, fundamentals and analyst estimates;
- portfolio and Open Finance history;
- versioned Candidate Stocks and One Pager snapshots.

### Market data adapter contract

Both providers produce the same normalized quote model. Provider-specific
symbols remain in `provider_symbol`, while `symbol` is the canonical security
key used by C3PO. Each collection creates an `ingestion_runs` row and each
quote is upserted into `observations` as `quote_snapshot`. A configured
provider remains in `attention` until at least one real collection succeeds.

The next adapter increment adds fundamentals, estimates and universe discovery
without changing the quote or provenance contracts.

### Phase 3 - Executive workflow

- Exchange and calendar read models;
- WhatsApp inbox triage;
- decision queue, follow-ups and alerts;
- action policies and approval ledger.

### Phase 4 - Learning layer

- explicit feedback and outcome tracking;
- methodology comparison and drift reports;
- source-quality scoring and anomaly detection;
- retrieval over historical decisions and company events.
