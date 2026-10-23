# Autopiloto da grade PIT EUA (`valuation-pit-grid-autopilot.yml`)

Aprovado pelo dono em 20/10/2026 (21:4x BRT): despachar os lotes da grade do `PREREG_VALUATION_PIT_BACKTEST_US_V1` (§14 d)
enquanto o Mac do dono — onde rodam Fable e Codex — está desligado, **só** sob a ordem do dono já assinada (ordem 2,
`ba24f301…`) ou a sua sucessora direta (ordem 3, emitida pela Fable sob a pré-autorização do dono de 22/10/2026 — ver
«Ordem sucessora»). Este documento não altera o pré-registro (congelado) nem o `valuation-pit-backtest.yml`: o autopiloto
só chama o modo `grid` desse workflow, que continua a fazer todas as suas verificações (ordem do dono, janelas, pré-voo no
host, produtor do commit do recibo).

## O que faz

A cada 30 min (`13,43 * * * *`, UTC) um tick lê apenas o que o GitHub já tem — as execuções de `valuation-pit-backtest.yml`,
os jobs e o log de cada lote que falhou depois do último sucesso, o artefato de metadados do último lote com sucesso, as 100
execuções mais recentes do pipeline de produção (`c3po-pipeline.yml`), os comentários recentes do bot
no canal (#429) — e o ficheiro da ordem do dono do checkout, e decide com `.github/scripts/valuation_pit_grid_autopilot.py`:

1. `C3PO_PIT_GRID_AUTOPILOT` diferente de `on` → nada (o tick agendado nem chega a correr o job).
2. Agora depois de `C3PO_PIT_GRID_UNTIL` → nada. Se o último lote com sucesso deixou a grade **incompleta** (e nenhuma
   execução do backtest está em curso), **um** aviso por prazo no canal (`ended:<prazo>`, com os instantes que faltam): um
   `UNTIL` esquecido, ou uma ordem que acaba antes da grade, nunca para a grade em silêncio.
3. Variável inválida ou em desacordo com a ordem do dono (o ficheiro existe, tem o sha256, autoriza `grid`, os mesmos pinos
   como instantes, `recompute_existing=false`, `max_runs ≤ max_runs_cap`) → nada, e **um** aviso por dia (BRT) no canal.
   Depois do `not_after` da ordem → nada (com o mesmo aviso único do item 2), seja qual for o `UNTIL`.
4. Uma execução do backtest (qualquer modo) não concluída, ou criada há menos de 10 min → nada.
5. Nenhum lote com sucesso → o **primeiro lote** (ver «Primeiro lote»). O último lote com sucesso correu sob **outra**
   ordem do dono → nada (`last_chunk_of_another_order`) e **um** aviso por dia (BRT) no canal, salvo se a ordem das
   variáveis for a sucessora direta dessa ordem (ver «Ordem sucessora»): então a grade segue sob ela.
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
   cada fuso (o horário de verão de Nova Iorque é seguido automaticamente). Uma execução do `c3po-pipeline.yml` que possa
   fazer deploy (qualquer evento salvo `pull_request`) ainda não concluída → nada (`deploy_in_progress`); se o mesmo deploy
   segurar a grade **2 h**, **um** aviso no canal (`deploy-wait:<run>`). Motivo: o deploy de produção recria os contêineres
   `api` e `db` (`docker compose up -d`), e o pré-voo do backtest consulta o contêiner `api` e corre o `--host-check`
   **antes** de chegar ao lock de deploy — um lote que comece durante a recriação sai com **12** ou **20**, que não são
   reexecutáveis e **param** o autopiloto (só o lock, depois, dá o 17 reexecutável).
9. Senão → despacha **um** lote: `mode=grid`, `owner_order_sha256`, os dois pinos, `prereg_commit` e `max_runs` das
   variáveis, `recompute_existing=false`, frase `RUN VALUATION PIT BACKTEST`, `--ref main`.

Todo tick a partir da conferência da ordem (item 3) mostra nos detalhes `until` — o fim efetivo do autopiloto, o mais cedo
entre `C3PO_PIT_GRID_UNTIL` e o `not_after` da ordem, em UTC — e, quando o último lote com sucesso correu sob outra ordem,
`successor_of` (o elo foi aceito) ou `successor` (o motivo da recusa). Também com um lote em curso (`run_in_progress`): um
dry-run manual mostra-os a qualquer hora.

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
| `C3PO_PIT_GRID_ORDER_SHA256` | `ba24f301f446bad09d030fdb6c3acf7b3c96f71b792b6e5b6bf4b33cac05f744` (ordem 2) → depois do merge da ordem 3, `7249796f20e4f030fec1f9aee2f9d512349c0827ad456ba5cf5d325fa9ca45e6` (ver «Ordem sucessora») |
| `C3PO_PIT_GRID_PRICE_PIN` | `2026-10-19T18:30:00-03:00` |
| `C3PO_PIT_GRID_CATALOGUE_PIN` | `2026-10-19T18:30:00-03:00` |
| `C3PO_PIT_GRID_PREREG_COMMIT` | `7f147409e5b500b819b2e5151f04290be1950db3` |
| `C3PO_PIT_GRID_MAX_RUNS` | `40` (1–200; nunca acima do `max_runs_cap` 200 da ordem). Ler o valor **real** (`gh variable get C3PO_PIT_GRID_MAX_RUNS`) antes de citar horários: o fim da grade depende dele (ver «Ordem sucessora») |
| `C3PO_PIT_GRID_UNTIL` | `2026-10-23T23:30:00-03:00` (ordem 2) → com a ordem 3, `2026-10-27T23:30:00-03:00` |
| `C3PO_PIT_GRID_AUTOPILOT` | `off` (padrão) → `on` para ligar |

O canal é `C3PO_ESCALATION_ISSUE` (padrão 429), o mesmo do detector de incidentes.

## Permissões e limites

`actions: write` (despachar; também lê as execuções do backtest e do pipeline de produção), `contents: read`, `issues: write` (os comentários). Só o `GITHUB_TOKEN`; nenhum segredo,
nenhum acesso ao host ou ao banco, nenhuma escrita no repositório (o estado é o histórico de execuções). Um
`workflow_dispatch` manual é **dry-run** por padrão (mostra a decisão, e com o autopiloto desligado também o que faria, sem
despachar nem comentar); só age a partir de `main`. O agendamento só existe depois do merge em `main`; se o ambiente
`production` exigir aprovação manual, o lote despachado fica em espera e o autopiloto não despacha outro.


## Primeiro lote (21/10/2026)

Sem nenhum lote de sucesso desta ordem, o autopiloto despacha o **primeiro lote**, limitado a `FIRST_CHUNK_MAX_RUNS` = 10 (§14 d, "start with 10"), e posta um aviso único (`first-chunk`) no canal. Antes, todo lote completado é classificado: uma recusa reexecutável é repetida, e qualquer outra falha para o autopiloto. O operador faz as conferências pós-primeiro-lote (`covered_without_rows_by_T` de 2021, `volume_basis` e o primeiro `manifest_sha256` no canal, custo por data) e desliga o autopiloto se alguma falhar. Motivo: o Mac do operador fica desligado na janela da noite de 21/10, e sem isso a grade perderia a noite.

## Ordem sucessora

O primeiro lote (run 39772674670, 22/10) mediu ~193 s por instante em média, mas **a subir**: 182,5 s no primeiro instante,
204,1 s no décimo (+2,6 s por instante, t ≈ 11; as duas corridas V3 e as servidas sobem; a causa não se sabe fora do host).
Os 257 instantes restantes (≥ 13,8 h de cálculo) não cabem nas janelas dos dias úteis até ao `not_after` da ordem 2 (sex
23/10 23:30 BRT). A **ordem 3** (`7249796f20e4f030fec1f9aee2f9d512349c0827ad456ba5cf5d325fa9ca45e6`), emitida pela Fable com
base na pré-autorização do dono de 22/10/2026 (#429, comentário 6340314970), é a ordem 2 com `not_after` **ter 27/10 23:30
BRT** e `"supersedes": "ba24f301…"`: os mesmos pinos, `modes`, `recompute_existing=false` e `max_runs_cap`. O `not_after` vai
até terça, e não só até domingo, para que um custo que continue a subir não exija uma ordem 4 (merge e deploy) com o Mac
desligado; o `not_after` é um teto, a grade para sozinha quando fica completa. Sáb 24 e dom 25 só têm a janela noturna do
PREREG; seg 26 e ter 27 têm as duas (sessão dos EUA 10:00–17:30 BRT e a noturna). O `valuation-pit-backtest.yml` confere-a
como qualquer ordem (ignora `supersedes` e `note`).

Regra do autopiloto: quando o último lote com sucesso correu sob outra ordem `X`, o tick só segue se a ordem das variáveis
(o ficheiro do checkout, conferido pelo sha256) tiver `"supersedes": X` e o ficheiro de `X` também estiver no checkout
(conferido pelo sha256) com o mesmo `schema` e `prereg`, `grid` nos `modes`, os mesmos dois pinos (como instantes) e
`recompute_existing=false` nas duas. Um elo só: a ordem que `X` substituiu não conta. Senão → nada
(`last_chunk_of_another_order`, o motivo em `details.successor`, e **um** aviso por dia no canal). O resto não muda: os lotes
falhados depois do último sucesso continuam classificados (uma parada sob a ordem 2 continua parada sob a ordem 3, com o
mesmo aviso único `stop:<run>`), as janelas e o primeiro lote. O lote despachado corre sob a ordem das variáveis; todo tick
que passa o elo mostra `successor_of` nos detalhes (paradas, grade completa e lotes em curso incluídos).

### Para passar à ordem 3 (operador)

1. **Merge em `main` durante a sessão dos EUA** (10:00–17:30 BRT, quando nenhum lote corre), de preferência **até ~16:00
   BRT**. O merge dispara o deploy de produção (`c3po-pipeline.yml`: testes, imagens, depois `docker compose up -d`, que
   recria os contêineres `api` e `db`, com o lock de deploy e a verificação de saúde), 15–30+ min depois do merge. O que
   **não** pode coincidir é essa recriação com o **início** de um lote: o pré-voo dele sai com 12/20 antes do lock e o
   autopiloto para. Um deploy que chegue com um lote **em curso** só espera 120 s pelo lock e falha — inofensivo para a grade
   (a ordem 3 é lida dos checkouts do GitHub, nunca do host; os ficheiros do produtor não mudam), mas o deploy fica por
   refazer. Depois deste merge o autopiloto já não despacha enquanto um deploy puder correr (`deploy_in_progress`), o
   deste merge incluído (os ticks seguintes correm o código novo); a sessão dos EUA evita, além disso, que o deploy encontre
   um lote em curso e falhe. Nunca despachar um lote à mão durante um deploy.
2. Esperar o deploy terminar (verde).
3. `C3PO_PIT_GRID_ORDER_SHA256` = `7249796f20e4f030fec1f9aee2f9d512349c0827ad456ba5cf5d325fa9ca45e6` e `C3PO_PIT_GRID_UNTIL`
   = `2026-10-27T23:30:00-03:00`; as outras variáveis não mudam. Ler de volta (`gh variable get`) essas duas e
   `C3PO_PIT_GRID_MAX_RUNS`, e registá-las no #429.
4. Tick manual em dry-run: exigir nos detalhes `successor_of` = `ba24f301…` **e** `until` = `2026-10-28T02:30:00+00:00`
   (ter 27/10 23:30 BRT) — presentes também com um lote em curso (`run_in_progress`) ou dentro da janela (`inside_window`).
   Não basta a ausência de `last_chunk_of_another_order`: `successor` nos detalhes é um elo recusado (com o motivo), e
   `until` = `2026-10-24T02:30:00+00:00` é um `UNTIL` ainda na sexta (a grade pararia sex 23:30, com um aviso `ended:`).
5. Confirmar no host que a retenção das promoções automáticas de segurança (congelamento do §14 do PREREG) cobre a grade
   até ao fim (no máximo ter 27/10) e o relatório.

### Quando acaba (estimativa, 22/10)

Simulação das regras do autopiloto e da grade (ticks :13/:43, 40 min de antecedência, `--stop-before` = próxima janela −
20 min, no máximo 300 min; parada por previsão com 1,5 × o instante mais lento e 1.200 s antes do primeiro instante medido
de **cada** lote — por isso os lotes despachados às 22:43 não calculam nada —; 2 + 1 min por lote; sem recusas):

| Custo por instante | `MAX_RUNS` 200 | `MAX_RUNS` 40 |
|---|---|---|
| constante 193 s | sáb 24/10 ~11:50 BRT | sáb ~13:50 |
| constante 230 s | sáb ~14:40 | sáb ~15:25 |
| sobe 2,6 s/instante dentro de cada lote (volta ao início a cada lote) | sáb ~16:40 | sáb ~15:10 |
| sobe 1,3 s/instante e não volta (metade da subida medida) | dom 25/10 ~10:10 | dom ~10:15 |
| sobe 2,6 s/instante e não volta (a subida medida) | seg 26/10 ~18:00 | seg ~09:30 |

Ao dono, uma **faixa**, nunca uma hora: melhor caso sáb ~12:00 BRT; plausível de sáb à tarde a dom de manhã; se a subida
medida persistir, segunda 26/10 (dentro do `not_after` da ordem 3). Fora do modelo: a reutilização dos instantes já feitos,
que cada lote confere antes de `started` (fora do `elapsed_seconds`), as recusas reexecutáveis e o atraso do cron.

Depois do **lote 2** (o primeiro da noite): ajustar `elapsed_seconds` contra o índice do instante nos `receipts.jsonl` do
artefato, e comparar a duração do passo do host com a soma dos `elapsed_seconds` (o custo de reutilização). Se o primeiro
instante novo voltar a ~183 s, a subida é por processo: `MAX_RUNS` 40 acaba antes. Se ficar em ~205 s ou mais, a subida
persiste: contar com domingo a segunda. Com `MAX_RUNS` 200 o pré-voo exige 6 GiB + 200 × 2 × 10 MiB ≈ 9,9 GiB livres em
`/var/lib/docker` (código 23, que para o autopiloto); o primeiro lote mediu `disk_kb=573840144` (~547 GiB livres), e a grade
escreve ~1,3–2,6 GB (§14 d): folga ampla.
