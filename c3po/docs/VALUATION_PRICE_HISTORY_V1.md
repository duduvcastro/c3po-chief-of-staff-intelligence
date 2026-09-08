# Valuation V3.2 — série de preços persistida (`valuation_price_history/<M>`), implementação rev 2

Referência normativa: spec V3.2 rev 7 (congelada a três, `d31ed90e…`), §2.2 "Série de rótulos" e §9.2; decisão do dono de 07/09/2026 (36 meses de histórico como treino; recibo `093aae44…`). Rev 2 responde aos achados C394-1..5 do Codex (recibo `9577cfd2…`) e aos achados C394-6..11 da pré-revisão adversarial interna (cartão de saúde, filtro de schema na safra, inserção em lote, relógio da safra, duplicatas na resposta, `outside_window`).

## O que é

- **Uma safra por corrida.** Cada corrida (backfill ou noturna) busca a **janela inteira** (36 meses por padrão, `C3PO_VALUATION_PRICE_HISTORY_BACKFILL_MONTHS`) para todo o conjunto de cobertura e deixa **um manifesto** em `analysis_snapshots` (`analysis_type = valuation_price_history`, `entity_key = <M>`, `published_at` = `fetched_at` da corrida). O manifesto grava `started_at` (antes da primeira requisição), `fetched_at` (**depois da última resposta** — o instante em que a safra passou a existir; **obrigatoriamente posterior** ao `fetched_at` do manifesto anterior do mesmo mercado, senão a corrida é recusada sem escrever nada), janela, calendário (nome + versão do `exchange_calendars`), símbolos pedidos/com barras/ausentes, erros do provedor por símbolo, linhas rejeitadas por incompletas, **sessões duplicadas na mesma resposta** (`rows_duplicate_in_response`; a primeira linha vence, a colisão fica registrada), **um hash de série por símbolo** (`series_sha256`), contagem de barras por símbolo, símbolos `unreproducible` e `bars_sha256` (hash do conjunto ordenado dos hashes de série). As barras são inseridas em lotes de 5.000 (`executemany`) dentro da mesma transação do manifesto.
- **Tabela append-only `valuation_price_bars`** (migração `db/049_valuation_price_history.sql`): uma linha por `(mercado, símbolo, sessão, fonte, fetched_at)` com `close` **e** `adjusted_close` (ambos obrigatórios), `volume`, `currency`, `provider_symbol`, `snapshot_id` (manifesto da corrida) e `bar_sha256` = **hash do conteúdo** (sem o relógio). Uma corrida insere **só as barras cujo conteúdo mudou** em relação à última linha da mesma `(mercado, símbolo, sessão, fonte)`; barra igual não custa armazenamento. Nada é atualizado, apagado ou truncado (gatilhos). Manifesto e barras são gravados **na mesma transação** (as barras referenciam o manifesto por FK): ou existem ambos ou nenhum.
- **Fonte única**: EODHD `/api/eod` (`eodhd:/api/eod`) para B3 (`.SA`), NASDAQ e NYSE (`.US`), como o inventário declara; uma chamada por símbolo por corrida, na noturna como no backfill.
- **Cobertura**: universo corrente do mercado ∪ todo símbolo com avaliações no V3 shadow (rótulos por vir) — nunca menos.

## Relógio e leitura (anti-lookahead, §2.2)

Todo leitor recebe `fetched_before` (o corte `C`) e resolve **uma única safra** `S` = manifesto **deste schema** (`VALUATION-PRICE-HISTORY-v2`) com o maior `fetched_at < C` (regra única da spec; um manifesto mais novo de outro schema nunca esconde uma safra compatível de um corte histórico). Para um símbolo, a série servida é "última linha com `fetched_at ≤ fetched_at(S)`" dentro da janela de `S`, **verificada contra o `series_sha256` que `S` gravou** para esse símbolo:

| status | significado |
|---|---|
| `ok` | as linhas reproduzem o hash de `S`; `price_snapshot_id` e `fetched_at` acompanham |
| `no_vintage` | nenhuma safra concluída antes do corte (um corte no meio de uma corrida não a vê) |
| `symbol_not_in_vintage` | `S` não tem série para o símbolo — **não é completado por uma safra anterior** |
| `vintage_unreproducible` | a própria corrida detectou uma sessão que o provedor deixou de devolver (a corrente traria uma linha antiga): declarado no manifesto, recusado |
| `vintage_mismatch` | as linhas armazenadas não reproduzem o hash gravado: recusado |

`label_bar(mercado, símbolo, sessão, h, fetched_before)` localiza a sessão `h` pregões à frente no calendário da bolsa (`exchange_calendars` 4.13.2: XNYS para NASDAQ/NYSE, BVMF para B3 — a spec grafa `XBSP`; errata documental para uma rev futura) e devolve `not_a_session`/`beyond_calendar` (calendário), `not_yet_mature` **enquanto o fecho da sessão alvo (hora da bolsa, não a data civil) não for anterior ao corte**, o status da safra quando ela recusa o símbolo, `outside_window` (a sessão alvo está fora da janela `[from, to]` que a safra pediu — não é "a bolsa não publicou"), `missing_bar` (a bolsa teve sessão, a safra tem o símbolo e a janela cobre a sessão, e não há barra) ou `labelled` com `close`, `adjusted_close`, `bar_sha256`, `fetched_at` e `price_snapshot_id` — nunca um preço de outra fonte.

O backfill de 36 meses é capturado agora (`fetched_at` = instante do backfill), portanto só pacotes cortados **depois** dele o consomem — história para treino, nunca antevisão. Limitação declarada: `fetched_at` é carimbado milissegundos antes do commit da transação; um corte entre os dois é teórico e os pacotes cortam sempre com folga de minutos.

## Operação

- **OFF por padrão.** A fase noturna (`OffhoursPhase("price_history")`) só entra no worker de valuation com `C3PO_VALUATION_PRICE_HISTORY_ENABLED=true`; o cartão de saúde só a espera quando ligada (o prazo de cada fase ligada é derivado das definições ativas, e um sucesso da fase nunca derruba o cartão).
- **Backfill (uma vez, por ordem da mesa):** `python -m app.valuation_price_history --market NASDAQ --backfill` (idem NYSE e B3); `--months` sobrepõe a configuração; `--symbols A,B` restringe a cobertura em ensaios. A saída JSON omite os mapas por símbolo (ficam no manifesto).
- **Não faz:** não calcula erros, pesos ou rótulos além de localizar a barra; não altera V1/V2/V3; não toca no R2D2.

## Testes

`tests/test_valuation_price_history.py`: hash de conteúdo (mesma barra em dois relógios = mesmo hash), dois fechos obrigatórios; cobertura = universo ∪ V3 shadow; corrida = uma safra numa única escrita transacional com hashes por símbolo, dedupe por conteúdo (segunda corrida igual insere zero; desdobramento insere só o que mudou), ausentes/erros/rejeitadas registrados; disponibilidade carimbada após a última resposta (corte dentro da corrida = `no_vintage`; `<` estrito); um corte vê exatamente uma safra (S1 antes, S2 depois, nunca mistura) e um símbolo ausente de S2 é recusado, não completado por S1; linha estranha sob o relógio da safra = `vintage_mismatch`; sessão descartada pelo provedor = `vintage_unreproducible`; relógios como instantes reais (fuso de SP vs UTC) e duplicata no mesmo lote = uma linha (paridade com `ON CONFLICT DO NOTHING`); rótulos no calendário (feriado de 07/09), maturidade pelo fecho (14:05Z e 20:00Z = imaturo; 20:00:01Z = maduro), `missing_bar`/`symbol_not_in_vintage`; janela do backfill e da noturna (mês civil), configuração viva, `BRK.B`, fase dormente e DDL (FK, gatilhos, TRUNCATE).
