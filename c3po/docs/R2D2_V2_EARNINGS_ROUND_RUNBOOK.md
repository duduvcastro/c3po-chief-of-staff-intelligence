# R2D2 V2 — Rodada ao vivo de earnings (18:00 NY): runbook do produtor (F385-8)

Estado: passo 2 do F385-8 na PR #385 (branch `fable/v2-data-producers`). Nada aqui ativa coleta: os produtores
ficam OFF por padrão (`C3PO_R2D2_V2_PRODUCERS_ENABLED`), nenhuma rodada real corre antes das três assinaturas,
do rito de prontidão e da release do coletor. Este documento descreve o procedimento; a autorização é da mesa.

## 1. O que a rodada faz

1. Lê o inventário de episódios vivos do coletor (registros `ledger.research` com `status = OPEN`, os dois braços,
   exatamente os episódios a que o coletor aplica `EARNINGS` / `EARNINGS_OBSERVATION_FAILED`), pelo mesmo store do
   worker (`r2d2_v2_shadow_epochs`, hash do estado conferido), ou de um arquivo JSON explícito.
2. Consulta o provedor **só para os nomes vivos** (`produce_earnings` com a lista causal vazia, `live_symbols` e
   `live_lookback` = [menor `opened_at`, maior `maturity_at`] em datas NY; o produtor alarga a consulta do
   calendário em 15 dias após a maturidade).
3. Relê o documento gravado, confere o sha256 e o entrega ao emissor (`r2d2_v2_round_emitter`): recibo retido da
   rodada (`round_id` = sha256 do núcleo), uma janela por instrumento, um envelope por fato conhecido dentro da
   janela (inclusive fatos anteriores à sessão da rodada, vindos de `evidence.known_events`), ou um
   `EARNINGS_OBSERVATION_FAILED` por instrumento indisponível/inválido/não consultado; validação de cada envelope
   **antes** da publicação; publicação atômica; quarentena do que foi recusado.
4. Grava o recibo de execução (`rounds/<sessão>.<round_id>.run.json`) que vincula inventário (hash dos bytes),
   documento (sha256) e recibo da rodada.

## 2. Agenda

- Uma execução por sessão oficial XNYS, às **18:05 America/New_York**, por timer externo no host do produtor
  (`TZ=America/New_York`, cron `5 18 * * 1-5`). Nunca pelo worker do coletor.
- O runner recusa antes das 18:00 NY e no fechamento oficial ou antes dele (em fecho antecipado a regra das 18:00
  prevalece); recusa data que não é sessão (feriado, fim de semana: não há rodada).
- Sessão pretendida: `--session-date auto` = data NY do instante de início. Execução atrasada depois da
  meia-noite NY: `--session-date <sessão pretendida>` (a rodada mantém a sessão pretendida e o recibo real; o
  coletor aceita `round_received_at` posterior, desde que ≥ 18:00 NY da sessão e > fechamento oficial).
- Segunda rodada para a mesma sessão só com `--repeat` (recomeço após falha parcial). Os fatos mantêm
  `earnings_event_id` e `revision_sha256`; só o `round_id` e os `event_id` mudam; o recibo de execução lista as
  rodadas anteriores.

```
C3PO_R2D2_V2_PRODUCERS_ENABLED=true python -m app.r2d2_v2_round_runner --epoch <época> [--root <raiz>] [--session-date auto|AAAA-MM-DD] [--repeat]
```

## 3. Saídas (tudo privado: diretórios 0700, arquivos 0600, sob a raiz que o coletor lê)

| Caminho | Conteúdo |
|---|---|
| `events/<event_id>.<self_sha256>.json` | a fita que o coletor lê (`V2_SHADOW_SOURCE_EVENT_V2`) |
| `rounds/<sessão>.<round_id>.json` | recibo retido da rodada (`V2_EARNINGS_ROUND_RECEIPT_V1`), com a lista do que foi publicado e quarentenado |
| `rounds/<sessão>.<round_id>.run.json` | recibo de execução (`V2_EARNINGS_ROUND_RUN_V1`): inventário, documento, rodada, rodadas anteriores |
| `documents/<sessão>/round-<início>/earnings.json` | documento do produtor (`V2_EARNINGS_COMPONENTS_V2`) que originou a rodada |
| `quarantine/<sessão>/<event_id>.<sha256>.json` | envelopes recusados pela validação prévia (`V2_EARNINGS_ROUND_QUARANTINE_V1`, com o código) |
| `quarantine/<sessão>/<arquivo>.purge.json` | recibo assinado de remoção (`V2_EARNINGS_QUARANTINE_PURGE_V1`) |

O coletor lê apenas `events/` e ignora nomes iniciados por `.`; `rounds/`, `documents/` e `quarantine/` nunca
entram na fita (provado no teste de integração com a `FileShadowSource` real).

## 4. Procedimento de quarentena

Um único arquivo inválido em `events/` faz o coletor descartar a fita inteira; por isso o emissor valida antes de
publicar e o que falha vai para a quarentena. A quarentena é evidência, não lixo.

1. **Auditar** (só leitura, permitido com os produtores OFF):
   `python -m app.r2d2_v2_round_runner --audit-quarantine [--root <raiz>]` → uma linha por arquivo com
   sessão, código, `round_id`, `event_id`, instrumento, tipo e sha256 dos bytes; arquivos ilegíveis aparecem como
   `UNREADABLE`; recibos de purga como `PURGE_RECEIPT`.
2. **Classificar** a causa pelo código:
   - defeito do emissor ou do produtor (`ENVELOPE_*`, `PROVENANCE_*`, `REVISION_SHA_MISMATCH`, …) → corrigir o
     código, nova rodada com `--repeat`; o fato correto entra pela nova rodada;
   - relógio do provedor anterior ao início da rodada (`AT_BEFORE_ROUND`) → o fato será observado na rodada
     seguinte; registrar;
   - fato fora da janela (`EVENT_OUTSIDE_WINDOW`) → não é observação dos episódios vivos; registrar.
   **Nunca** mover um arquivo da quarentena para `events/` à mão, nem editar um envelope.
3. **Remover** um arquivo por vez, só de `quarantine/<sessão>/`, com assinatura e motivo:
   `python -m app.r2d2_v2_round_runner --purge-quarantine <sessão> <arquivo> --signed-by <quem> --reason "<motivo>"`.
   O recibo `<arquivo sem .json>.purge.json` (sha256 dos bytes removidos, código, `round_id`, assinante, motivo,
   instante) é gravado **antes** da remoção; caminho com `/`, nome oculto, sessão inválida, arquivo fora da
   quarentena ou symlink são recusados.
4. **Publicar** na PR #348 (canal de auditoria cruzada) o hash do recibo de purga sempre que a quarentena tocar
   uma sessão em curso, e conferir a fita na sessão seguinte (`FileShadowSource.last_event_diagnostics == []`).

## 5. Invariantes

- Nenhuma chamada ao provedor antes das guardas de agenda (18:00 NY, fechamento oficial, sessão válida, rodada
  única por sessão salvo `--repeat`).
- `round_received_at` é o instante real de início da rodada; `round_id` é o hash do que se sabia antes de publicar;
  nada é datado para trás.
- `earnings_event_id = ern:<instrument_key>:<event_date>` é estável entre rodadas; data remarcada = fato novo
  (o provedor não expõe chave de período), declarado como limitação.
- O token do provedor nunca sai do fetcher: não aparece em arquivos, logs, recibos ou mensagens de erro.
- Nada aqui decide admissão, saída ou certificação; o produtor relata fatos e o próprio veredito.
