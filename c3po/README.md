# C3PO | Chief of Staff Intelligence

C3PO is the private operational layer built on top of the existing Chief of
Staff Digital automations. It does not replace the Morning, Lunch and Night
Summary jobs during the migration.

## Architecture

- `frontend/`: Next.js application exported as static files.
- `backend/`: FastAPI API and legacy adapters.
- `db/`: PostgreSQL schema and versioned migrations.
- `compose.yml`: opt-in local/production-like stack.
- `docs/`: architecture decisions and migration notes.

The first vertical slice reads the latest legacy summary, exposes normalized
data through the API and renders the operational Command Center. PostgreSQL is
used for durable observations, methodology versions, feedback and audit data.
Production access is passwordless: C3PO emails a single-use login code only to
addresses authorized by the owner in **Death Star**. Each profile has an
explicit module allowlist, enforced both in navigation and by the data API.
Each member also has API-enforced action capabilities: mandatory read access,
optional One Pager generation and optional deletion inside enabled modules.
All other mutations remain restricted to the protected owner.
Suspending or deleting a profile immediately revokes its existing sessions.
The configured `C3PO_AUTH_EMAIL` is the protected owner and cannot be removed.

The market-data foundation supports Brapi for B3 and EODHD for US/global
coverage. Provider health is visible in Automation Health. Quotes are
normalized and stored as idempotent observations with provider, market time,
collection time, quality score and ingestion-run audit data.

## Day D research program

The signed Day D v1.2 blueprint and its Stage 0 workbook are the governing
documents for the next R2D2 research generation:

- [`docs/DAY_D_BLUEPRINT_V1_2.md`](docs/DAY_D_BLUEPRINT_V1_2.md)
- [`docs/R2D2_COMMITTEE_PHASE_0.md`](docs/R2D2_COMMITTEE_PHASE_0.md)
- [`docs/day_d/stage0_contract.json`](docs/day_d/stage0_contract.json)

Stage 0 is specification and burned-data research only. It does not authorize
changes to production trading behavior or capital use.

## Market data credentials

Set credentials in the root `.env`; never commit tokens:

```bash
BRAPI_TOKEN=...
C3PO_BRAPI_PLAN=pro
EODHD_API_TOKEN=...
C3PO_EODHD_PLAN=all-in-one
```

After restarting the API, validate each provider with a small request:

```bash
curl -b c3po-cookie.txt -H 'Content-Type: application/json' \
  -d '{"provider":"brapi","symbols":["PETR4","VALE3"]}' \
  'https://YOUR_C3PO_HOST/api/v1/market-data/sync'

curl -b c3po-cookie.txt -H 'Content-Type: application/json' \
  -d '{"provider":"eodhd","symbols":["MSFT","AMZN"]}' \
  'https://YOUR_C3PO_HOST/api/v1/market-data/sync'
```

Successful calls create ingestion runs and update Automation Health. The API
accepts at most 20 symbols per interactive request; scheduled collectors will
batch larger universes separately.

## Local development

Backend:

```bash
cd c3po/backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
C3PO_LEGACY_ROOT=../.. uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd c3po/frontend
pnpm install
NEXT_PUBLIC_C3PO_API_URL=http://localhost:8000 pnpm dev
```

Open `http://localhost:3000`.

## Docker

```bash
cd c3po
docker compose up --build
```

The web application is exposed at `http://localhost:8081` and the API at
`http://localhost:8000`.

## Safety boundary

The C3PO services mount the legacy workspace read-only. No C3PO endpoint moves
email, sends WhatsApp messages, places trades or changes the existing summary
schedules. Action endpoints will require explicit policies and audit records
before they are enabled.
