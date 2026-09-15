# O5 — logs persistentes dos serviços operacionais (journald)

**Origem:** mesa de 04/09/2026 (ratificação do dono: "autorizo 1, 2 e 3"), item O5 do parecer
`PARECER_STOP_M1M3_2026-09-04`. **Fato motivador:** o deploy da #373 (20:32 BRT de 04/09) recriou o
container `c3po-r2d2-worker-1`; com o driver padrão `json-file`, o arquivo de log pertence ao container
e foi removido com ele — a medição M1 (logs do worker de 04/09) ficou sem fonte.

## O que muda
`c3po/compose.yml`: os serviços **`api`, `r2d2-worker`, `r2d2-shadow-candidate-worker` e
`server-usage-worker`** passam a usar `logging.driver: journald` com `tag: "{{.Name}}"`. Nada muda em
`db`, `web` e nos workers de IR/valuation (fora do item ratificado). Nenhuma alteração de código,
política ou configuração de trading.

## Como ler depois
```bash
journalctl CONTAINER_NAME=c3po-r2d2-worker-1 --since '2026-09-08 10:00' --until '2026-09-08 17:30' -o short-iso
```
`docker logs` continua funcionando (o driver journald suporta leitura pelo Docker). Campos úteis:
`CONTAINER_NAME`, `CONTAINER_ID`, `SYSLOG_IDENTIFIER` (= tag).

## Pré-requisitos e limites (honestos)
- **Sobrevive à recriação do container** sempre. **Sobrevive ao reboot do host** só se o journal for
  persistente (`/var/log/journal` existente ou `Storage=persistent`). A migração do tier registra esse
  estado no portão P3 (condição C4); criar o diretório é passo de host, por ordem própria, fora desta PR.
- **Rate limit do journald** (`RateLimitIntervalSec=30s`, `RateLimitBurst=10000` por serviço emissor —
  todos os containers emitem via `docker.service`): uma tempestade de warnings pode ser suprimida;
  a leitura deve procurar `Suppressed N messages` na janela e registrar como lacuna, não como zero.
- **Retenção:** `SystemMaxUse` padrão (10% do FS, teto 4 GB) — suficiente para semanas no host novo.
- O `docker compose up -d` do deploy recria os quatro containers ao aplicar a mudança (como qualquer
  deploy); **rollout só fora de pregão e depois do portão P6 da migração** (condição C2).

## Verificação pós-deploy
```bash
docker inspect --format '{{.HostConfig.LogConfig.Type}}' c3po-r2d2-worker-1
```
Esperado `journald`; em seguida `journalctl -n 5 CONTAINER_NAME=c3po-r2d2-worker-1` mostra linhas novas.

## Assinaturas
- **Dudu:** RATIFICADO — 04/09/2026 (item 2: "autorizo 1, 2 e 3").
- **Fable:** autor da PR — 04/09/2026.
- **Codex:** auditoria pendente (merge após P6, por ordem nominal).
