# Divergências do runtime em relação à origem pinada

`SOURCE_PINS.json` e `origin/` continuam sendo o registro histórico da revisão `6083d742` (não são regenerados aqui).
Este arquivo anota cada mudança posterior em uma função pinada, para a trilha do R2D2 não ser pega de surpresa.

## 17/10/2026 — `InvestorRelationsService.sync_sec` (defeito e do Valuation)

- **O que mudou.** `sync_sec` (pinada em `SOURCE_PINS.json`, linha 420 da origem) ganhou uma linha:
  `self._apply_sec_header_acceptances(events)`, antes de `_enrich_with_sec_fulltext`. É a primeira divergência dessa
  função desde a origem. Na integração com a frente as-filed (SEC XBRL) o passo ficou único: além do instante já
  gravado no próprio evento, ele reaproveita o instante que o poll as-filed registrou em `statement_filings`, e as
  leituras de header usam o `SecXbrlClient` do processo; a linha em `sync_sec` é a mesma. `_sec_event`, que `sync_sec` chama e que não é pinada por método, passou a ler o
  `acceptanceDateTime` do JSON de submissions com a semântica verificada em 17/10: o rótulo "UTC" é o instante real
  **mais** o offset de Nova York. Os eventos de arquivamento SEC (10-Q, 8-K…) recuam 4 h (EDT) ou 5 h (EST) em
  `published_at`. O header do arquivamento, quando lido, substitui essa leitura. Detalhes em
  `../VALUATION_DEFECTS_2026-10-17.md`.
- **O que não mudou.** `_finnhub_insider_events`, `_eodhd_insider_events`, `clean_text` e `safe_date`, assim como
  `save_ir_events`, `insider_transaction_activity` e `_insider_transaction_direction` do banco, continuam com AST
  idêntica à origem. `verify_oracle_sources` não cobre `sync_sec` e continua passando. Os eventos de insider
  (`event_type = "Insider Transaction"`, os únicos que `insider_transaction_activity` conta) não passam pelo passo novo:
  o `published_at` deles e a janela de 180 dias do RC-4 ficam iguais.
- **Isolamento de falha.** O passo novo é best-effort, como o enriquecimento por full-text. Qualquer falha, inclusive a
  da consulta ao banco `stored_sec_acceptances` ou ao registro `statement_filings`, só gera um aviso no log. A sincronização segue, e os eventos de
  insider daquela rodada são gravados com a corrida marcada `succeeded`. Teste:
  `test_a_failing_header_step_never_fails_sync_sec_nor_the_insider_events_r2d2_reads`.
- **Rede.** Os headers só são pedidos à SEC pelo processo criado com `read_sec_headers=True`, que é o
  `investor-relations-worker`. O `r2d2-worker`, a API e o `valuation-worker` só reaproveitam o que já está no banco e
  não fazem nenhuma chamada nova à SEC. As chamadas SEC do cliente de IR (submissions, full-text) passam a esperar o
  limitador do processo (`sec_xbrl.process_rate_limiter`); os eventos de insider vêm de Finnhub/EODHD e não passam por
  ele.
- **Quem regenerar os pins para um head novo** deve tratar `sync_sec` como alterada desde `6083d742`.
