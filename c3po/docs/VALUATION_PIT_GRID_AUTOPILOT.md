# Autopiloto da grade PIT EUA (`valuation-pit-grid-autopilot.yml`)

Aprovado pelo dono em 20/10/2026 (21:4x BRT): despachar os lotes da grade do `PREREG_VALUATION_PIT_BACKTEST_US_V1` (§14 d)
enquanto o Mac do dono — onde rodam Fable e Codex — está desligado, **só** sob a ordem do dono já assinada (ordem 2,
`ba24f301…`) ou a sua sucessora direta (ordem 3, emitida pela Fable sob a pré-autorização do dono de 22/10/2026 — ver
«Ordem sucessora»). Este documento não altera o pré-registro (congelado) nem o `valuation-pit-backtest.yml`: o autopiloto
só chama o modo `grid` desse workflow, que continua a fazer todas as suas verificações (ordem do dono, janelas, pré-voo no
host, produtor do commit do recibo).

## O que faz

A cada 30 min (`13,43 * * * *`, UTC) um tick lê apenas o que o GitHub já tem — as execuções de `valuation-pit-backtest.yml`,
os jobs e o log de cada lote que falhou depois do último sucesso, o artefato de metadados do último lote com sucesso, os comentários recentes do bot
no canal (#429) — e o ficheiro da ordem do dono do checkout, e decide com `.github/scripts/valuation_pit_grid_autopilot.py`:

1. `C3PO_PIT_GRID_AUTOPILOT` diferente de `on` → nada (o tick agendado nem chega a correr o job).
2. Agora depois de `C3PO_PIT_GRID_UNTIL` → nada.
3. Variável inválida ou em desacordo com a ordem do dono (o ficheiro existe, tem o sha256, autoriza `grid`, os mesmos pinos
   como instantes, `recompute_existing=false`, `max_runs ≤ max_runs_cap`) → nada, e **um** aviso por dia (BRT) no canal.
   Depois do `not_after` da ordem → nada, seja qual for o `UNTIL`.
4. Uma execução do backtest (qualquer modo) não concluída, ou criada há menos de 10 min → nada.
5. Nenhum lote com sucesso desta ordem → nada: o **primeiro lote é do operador** (§14 d: medir o custo, registar o
   `volume_basis` com o `manifest_sha256` do primeiro lote).
6. O manifesto do último lote com sucesso diz `complete: true` → nada, e **um** comentário no canal
   (`grid complete, manifest_sha256 …`, com o `manifest_run_id` para o `report`).
7. Lotes concluídos **depois do último sucesso** sem sucesso — **cada um** deles é classificado:
   - recusa reexecutável — o passo da janela do backtest, ou código remoto **11** (reinício de segurança pendente; dito no
     canal **uma vez por dia** BRT enquanto se repetir), **17** (lock de deploy), **19** (timer/serviço R2D2/massive), **21**
     (ingestão bloqueante), **25** (sem tempo antes da janela) → o mais recente é reexecutado neste tick;
   - qualquer outra falha em **qualquer** deles (erro de corrida, produtor divergente, erro de dados, cancelamento, código
     ilegível) → **PARADO**: nada é despachado e **um** comentário no canal com o run id e o código de saída (só o agregado;
     o stderr fica privado no host). Uma recusa reexecutável mais nova nunca esconde uma parada mais antiga. A parada dura
     até um lote mais novo terminar com sucesso.
   - **Prazo (código 124):** um lote morto pelo `timeout` do prazo único (10 min antes da janela) **para o autopiloto, de
     propósito** — a grade normalmente para sozinha em `--stop-before`; chegar ao prazo é anomalia a diagnosticar.
8. Dentro de uma janela proibida (09:00–16:30 America/New_York em dias úteis; 23:30 do dia anterior a 08:15
   America/Sao_Paulo) ou a menos de **40 min** do início da próxima → nada. As janelas são as do backtest, em hora local de
   cada fuso (o horário de verão de Nova Iorque é seguido automaticamente).
9. Senão → despacha **um** lote: `mode=grid`, `owner_order_sha256`, os dois pinos, `prereg_commit` e `max_runs` das
   variáveis, `recompute_existing=false`, frase `RUN VALUATION PIT BACKTEST`, `--ref main`.

O código remoto sai da linha agregada que o backtest imprime (`remote exit status: N; …`), lida no log do job; se não houver
um valor único, a falha conta como não reexecutável. Um estado do GitHub ilegível (jobs, log, artefato) faz o tick falhar
(vermelho) sem despachar nada. Cada despacho é **confirmado**: o novo lote tem de aparecer na lista de execuções em até
60 s, senão o tick falha. Um tick que age e falha publica no canal **um** aviso por dia BRT (`autopilot tick failing`, com o
run id do tick).

## Quando ligar (`C3PO_PIT_GRID_AUTOPILOT=on`)

O operador só liga o autopiloto **depois** do primeiro lote, despachado à mão, e das verificações do §14 d sobre ele:

1. `statements_coverage.covered_without_rows_by_T` dos `T` de 2021 pequeno (o lookback SEC chegou a 2016);
2. `volume_basis` (decisão ≠ `undetermined`) e o `manifest_sha256` do primeiro lote registados no canal;
3. custo por data medido (`elapsed_seconds` e `peak_rss_kb` por `T`, incluindo a corrida servida) e compatível com as
   janelas até sexta — senão avisar o dono **no ato** em vez de ligar.

## Regra de parada (§14 d) — o que o operador faz

Os parâmetros **nunca** mudam pelo autopiloto. Depois de uma parada, o operador diagnostica; erro de dados → corrigir e
retomar com os **mesmos** parâmetros. Para retomar, despachar um lote à mão (os mesmos parâmetros): se terminar com sucesso,
o autopiloto volta a andar sozinho. `C3PO_PIT_GRID_AUTOPILOT=off` desliga-o a qualquer momento.

## Variáveis do repositório (Settings → Secrets and variables → Actions → Variables)

| Variável | Valor |
|---|---|
| `C3PO_PIT_GRID_ORDER_SHA256` | `ba24f301f446bad09d030fdb6c3acf7b3c96f71b792b6e5b6bf4b33cac05f744` |
| `C3PO_PIT_GRID_PRICE_PIN` | `2026-10-19T18:30:00-03:00` |
| `C3PO_PIT_GRID_CATALOGUE_PIN` | `2026-10-19T18:30:00-03:00` |
| `C3PO_PIT_GRID_PREREG_COMMIT` | `7f147409e5b500b819b2e5151f04290be1950db3` |
| `C3PO_PIT_GRID_MAX_RUNS` | `40` (1–200; nunca acima do `max_runs_cap` 200 da ordem) |
| `C3PO_PIT_GRID_UNTIL` | `2026-10-23T23:30:00-03:00` |
| `C3PO_PIT_GRID_AUTOPILOT` | `off` (padrão) → `on` para ligar |

O canal é `C3PO_ESCALATION_ISSUE` (padrão 429), o mesmo do detector de incidentes.

## Permissões e limites

`actions: write` (despachar), `contents: read`, `issues: write` (os comentários). Só o `GITHUB_TOKEN`; nenhum segredo,
nenhum acesso ao host ou ao banco, nenhuma escrita no repositório (o estado é o histórico de execuções). Um
`workflow_dispatch` manual é **dry-run** por padrão (mostra a decisão, e com o autopiloto desligado também o que faria, sem
despachar nem comentar); só age a partir de `main`. O agendamento só existe depois do merge em `main`; se o ambiente
`production` exigir aprovação manual, o lote despachado fica em espera e o autopiloto não despacha outro.


## Primeiro lote (21/10/2026)

Sem nenhum lote de sucesso desta ordem, o autopiloto despacha o **primeiro lote**, limitado a `FIRST_CHUNK_MAX_RUNS` = 10 (§14 d, "start with 10"), e posta um aviso único (`first-chunk`) no canal. Antes, todo lote completado é classificado: uma recusa reexecutável é repetida, e qualquer outra falha para o autopiloto. O operador faz as conferências pós-primeiro-lote (`covered_without_rows_by_T` de 2021, `volume_basis` e o primeiro `manifest_sha256` no canal, custo por data) e desliga o autopiloto se alguma falhar. Motivo: o Mac do operador fica desligado na janela da noite de 21/10, e sem isso a grade perderia a noite.

## Ordem sucessora

O primeiro lote (run 39772674670, 22/10) mediu ~193 s por instante: os 257 instantes restantes (~13,8 h de cálculo) não
cabem nas janelas dos dias úteis até ao `not_after` da ordem 2 (sex 23/10 23:30 BRT, ~11,7 h). A **ordem 3**
(`6ad97737b3fe889027012e60b19f301f17924612a2a86c89eddfd21e2a4387ad`), emitida pela Fable com base na pré-autorização do dono
de 22/10/2026 (#429, comentário 6340314970), é a ordem 2 com `not_after` **dom 25/10 23:30 BRT** e
`"supersedes": "ba24f301…"`: os mesmos pinos, `modes`, `recompute_existing=false` e `max_runs_cap`. Sáb 24 e dom 25 só têm a
janela noturna do PREREG. O `valuation-pit-backtest.yml` confere-a como qualquer ordem (ignora `supersedes` e `note`).

Regra do autopiloto: quando o último lote com sucesso correu sob outra ordem `X`, o tick só segue se a ordem das variáveis
(o ficheiro do checkout, conferido pelo sha256) tiver `"supersedes": X` e o ficheiro de `X` também estiver no checkout
(conferido pelo sha256) com o mesmo `schema` e `prereg`, `grid` nos `modes`, os mesmos dois pinos (como instantes) e
`recompute_existing=false` nas duas. Um elo só: a ordem que `X` substituiu não conta. Senão → nada
(`last_chunk_of_another_order`, como antes; o motivo vai em `details.successor`). O resto não muda: os lotes falhados depois
do último sucesso continuam classificados (uma parada sob a ordem 2 continua parada sob a ordem 3, com o mesmo aviso único
`stop:<run>`), as janelas e o primeiro lote. O lote despachado corre sob a ordem das variáveis; cada tick que passa o elo
mostra `successor_of` nos detalhes.

Para passar à ordem 3 (operador, depois do merge em `main`): `C3PO_PIT_GRID_ORDER_SHA256` =
`6ad97737b3fe889027012e60b19f301f17924612a2a86c89eddfd21e2a4387ad` e `C3PO_PIT_GRID_UNTIL` = `2026-10-25T23:30:00-03:00`;
as outras variáveis não mudam. Conferir com um tick manual em dry-run: `successor_of` = `ba24f301…` nos detalhes (fora das
janelas, `next_chunk`), nunca `last_chunk_of_another_order`.
