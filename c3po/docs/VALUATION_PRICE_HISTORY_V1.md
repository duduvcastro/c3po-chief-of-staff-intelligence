# Valuation V3.2 — série de preços persistida (`valuation_price_history/<M>`)

Referência normativa: spec V3.2 rev 7 (congelada a três, `d31ed90e…`), §2.2 "Série de rótulos" e §9.2; decisão do dono de 07/09/2026 (36 meses de histórico como treino; recibo `093aae44…`).

## O que é

- **Tabela append-only `valuation_price_bars`** (migração `db/049_valuation_price_history.sql`): uma linha por `(mercado, símbolo, sessão, fonte, fetched_at)` com `close` **e** `adjusted_close` (ambos obrigatórios), `volume`, `currency`, `provider_symbol`, `snapshot_id` (manifesto da corrida) e `bar_sha256`. Uma nova captura da mesma sessão (ex.: `adjusted_close` reapresentado após desdobramento) é uma **nova linha** com o seu `fetched_at`; nada é atualizado ou apagado (gatilhos).
- **Manifesto por corrida** em `analysis_snapshots` (`analysis_type = valuation_price_history`, `entity_key = <M>`): `price_snapshot_id`, intervalo pedido, símbolos pedidos/com barras/ausentes, erros do provedor por símbolo, primeira/última sessão, `bars_sha256` (hash do conjunto ordenado dos hashes das barras).
- **Fonte única**: EODHD `/api/eod` (`eodhd:/api/eod`) para B3 (`.SA`), NASDAQ e NYSE (`.US`), como o inventário declara.
- **Cobertura**: universo corrente do mercado ∪ todo símbolo com avaliações no V3 shadow (rótulos por vir) — nunca menos.

## Relógio (anti-lookahead, §2.2)

Todo leitor recebe `fetched_before` como parâmetro: para cada sessão vale a **última barra com `fetched_at < fetched_before`**. Um pacote de corte `C` só enxerga barras capturadas antes de `C`; o backfill de 36 meses é capturado agora (`fetched_at` = data do backfill), portanto só pacotes cortados **depois** dele o consomem — história para treino, nunca antevisão. `label_bar(mercado, símbolo, sessão, h, fetched_before)` localiza a sessão `h` pregões à frente no calendário da bolsa (`exchange_calendars`: XNYS para NASDAQ/NYSE, BVMF para B3) e devolve `labelled`, `missing_bar` (a bolsa teve sessão e a série não tem barra), `not_yet_mature` ou `beyond_calendar` — nunca um preço de outra fonte.

## Operação

- **OFF por padrão.** A fase noturna (`OffhoursPhase("price_history")`, últimas 10 sessões da cobertura) só entra no worker de valuation com `C3PO_VALUATION_PRICE_HISTORY_ENABLED=true`; o cartão de saúde só a espera quando ligada.
- **Backfill de 36 meses (uma vez, por ordem da mesa):** `python -m app.valuation_price_history --market NASDAQ --backfill --months 36` (idem NYSE e B3); ≈ 1 chamada por símbolo; saída JSON com o manifesto. `--symbols A,B` restringe a cobertura em ensaios.
- **Não faz:** não calcula erros, pesos ou rótulos além de localizar a barra; não altera V1/V2/V3; não toca no R2D2.

## Testes

`tests/test_valuation_price_history.py`: barra exige os dois fechos e leva o relógio da corrida e o hash; cobertura = universo ∪ V3 shadow; corrida persiste uma vez por relógio (replay do mesmo `fetched_at` não insere; corrida posterior insere nova safra), manifesto, símbolos ausentes e erros do provedor; leitores só veem o que foi capturado antes do corte e a safra mais recente; rótulos no calendário (feriado de 07/09 em NYSE e B3), `missing_bar`/`not_yet_mature`; janela do backfill e fase dormente.
