# C3PO | Chief of Staff Intelligence

Private intelligence platform and the legacy Chief of Staff Digital automation
that produces the Morning, Lunch and Night Summaries.

## Repository layout

- `c3po/`: web application, FastAPI backend, PostgreSQL migrations and workers.
- `work/`: legacy summary, Exchange, Pluggy and PDF automation scripts.
- `docker-compose.yml`: legacy summary services.
- `c3po/compose.yml`: C3PO production stack.
- `.github/workflows/`: validation and production deployment pipeline.

## Development

Backend:

```bash
cd c3po/backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pytest
```

Frontend:

```bash
cd c3po/frontend
corepack enable
pnpm install --frozen-lockfile
pnpm build
```

Never commit `.env`, API tokens, bank data, email exports, reports, generated
PDFs, database files or SSH keys. See [`docs/GITHUB_FLOW.md`](docs/GITHUB_FLOW.md)
for the release process.
