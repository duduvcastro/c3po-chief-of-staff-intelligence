# AWS phase 1 deployment

The C3PO stack is opt-in and does not replace the legacy Compose project.

## Pre-flight

1. Keep the current summary containers and cron unchanged.
2. Keep the shared environment at `/opt/chief-of-staff-digital/.env`.
3. Generate a long random `C3PO_DB_PASSWORD`.
4. Generate a random `C3PO_AUTH_SECRET` with at least 32 characters.
5. Set `C3PO_AUTH_REQUIRED=true`; `C3PO_AUTH_EMAIL` becomes the protected owner
   that manages the remaining authorized addresses in Death Star.
6. Add a 2 GB swap file before enabling PostgreSQL on the 2 GB instance.
7. Keep PostgreSQL private; do not publish port 5432.

## First start

```bash
cd /opt/chief-of-staff-digital
docker compose -f c3po/compose.yml up -d --build
docker compose ps
curl http://127.0.0.1:8000/api/v1/health
```

The first API startup applies the idempotent initial schema. The legacy project
is mounted read-only at `/legacy`.

## Caddy cutover

After local verification, route the private C3PO hostname to the web service.
The recommended production topology is one public Caddy entry point, with the
API reachable only through the web proxy. Passwordless authentication sends a
six-digit, single-use code through Exchange, stores only its HMAC signature,
and issues a secure HttpOnly session cookie. Only Death Star allowlisted users
receive a code, and module permissions are checked again in FastAPI on every
request. PostgreSQL remains on the isolated internal network; only the API
receives an outbound interface for Exchange.

## Upgrade threshold

Move from 2 GB to 4 GB when one of these conditions is observed:

- sustained memory usage above 75%;
- an OOM event during PDF/Chromium execution;
- API p95 latency above 750 ms during a summary run;
- PostgreSQL cache hit ratio below 95% after the history tables are populated.

Do not introduce Redis or a managed database until workload measurements show a
real need.
