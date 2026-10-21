# C3PO | Chief of Staff Intelligence

Private intelligence platform and the legacy Chief of Staff Intelligence automation
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

## Ponte de veredictos do Decisor para o laboratório do R2D2 (cifrada)

A partir de segunda 26/10 o modo medição do R2D2 (virtual, no repositório **privado** `c3po-r2d2-lab`) entra só nos nomes
que o Decisor do Valuation marcou `COMPRA_PERMITIDA` na noite anterior ao pregão, e mede o mesmo dia **sem** o portão, lado
a lado. Este repositório é **público** (qualquer um baixa os artefatos), então a lista de veredictos nunca sai do servidor
em claro:

* `python -m app.valuation_decision --export-verdicts --night <AAAA-MM-DD|last-completed> --recipient-public-key <base64>`
  (sessão PostgreSQL somente-leitura; `c3po/backend/app/valuation_verdict_export.py`) lê os veredictos dos EUA (NASDAQ, NYSE) da
  noite — a sessão NYSE para a qual o decisor decidiu, a última rodada publicada até a abertura seguinte — e imprime **só**
  um envelope cifrado: X25519 efêmero → HKDF-SHA256 → AES-256-GCM, com o cabeçalho em claro autenticado. Em claro: noite,
  instante e rodada da decisão, hash dos limiares, contagens (sem símbolo) e o sha256 do texto (que leva um `blinding`
  aleatório). Recusa (um código, sem símbolo) noite sem decisões, sessão ainda aberta, registro que não confere e noite
  incompleta (a geração em vigor não é a que a rodada decidiu).
* `.github/workflows/decisor-verdict-export.yml`: dias úteis às 11:00 UTC (08:00 BRT) e sob demanda; executa no container
  `api` do servidor como o `valuation-readonly-report.yml` (ssh → `docker compose exec -T`, `PGOPTIONS` somente-leitura),
  confere no runner o **esquema exato** do envelope (nenhum campo pode levar o texto) e publica o artefato
  `decisor-verdicts-<noite>` (envelope + metadados + SHA256SUMS, 30 dias).
* A chave pública fica na **variável** `C3PO_R2D2_LAB_VERDICT_PUBKEY` deste repositório; a privada só existe como **segredo**
  `C3PO_R2D2_LAB_VERDICT_KEY` do laboratório.

**Comando único do dono** (no Terminal do Mac; a chave privada vai direto do Python para o `gh secret set` pelo stdin, nunca
aparece na tela nem em arquivo; o Fable nunca a vê):

```bash
(
  set -o pipefail
  PY=/usr/bin/python3
  { "$PY" -c 'import cryptography' 2>/dev/null || "$PY" -m pip install --user --quiet cryptography; } &&
  PUBFILE=$(mktemp) &&
  "$PY" -c 'import sys,base64;from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey as K;from cryptography.hazmat.primitives import serialization as s;k=K.generate();open(sys.argv[1],"w").write(base64.b64encode(k.public_key().public_bytes(s.Encoding.Raw,s.PublicFormat.Raw)).decode());sys.stdout.write(base64.b64encode(k.private_bytes(s.Encoding.Raw,s.PrivateFormat.Raw,s.NoEncryption())).decode())' "$PUBFILE" \
    | gh secret set C3PO_R2D2_LAB_VERDICT_KEY -R duduvcastro/c3po-r2d2-lab &&
  PUB=$(cat "$PUBFILE") && [ ${#PUB} -eq 44 ] &&
  gh variable set C3PO_R2D2_LAB_VERDICT_PUBKEY -R duduvcastro/c3po-chief-of-staff-intelligence --body "$PUB" &&
  echo "OK: chave privada gravada só como segredo do laboratório; chave pública $PUB"
  rm -f "$PUBFILE"
)
```

Rodar de novo troca o par de chaves (os envelopes antigos deixam de abrir no laboratório). O lado do laboratório está no
README do `c3po-r2d2-lab` ("Portão do Valuation").
