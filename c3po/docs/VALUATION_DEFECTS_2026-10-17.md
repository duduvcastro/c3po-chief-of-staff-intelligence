# Valuation — quatro defeitos que distorciam números servidos (b, c, d, e), 17/10/2026

Direção do dono de 17/10/2026: o Valuation passa a decidir compra/não compra. Os quatro defeitos abaixo foram
aprovados para correção **numa única versão**; eles **mudam números servidos quando o deploy acontecer** (não há flag:
a correção é o comportamento novo). O defeito de overlay/EBITDA da CVM fica com a frente `val-cvm`.

| | Onde | Antes | Depois | O que muda no que é servido |
|---|---|---|---|---|
| (b) | `market_data/us_screener.py` | Hurdle do Power Zone dos EUA = Selic do Brasil + 6 p.p. = **20,0%** | Treasury 10 anos dos EUA (a mesma taxa ao vivo do CAPM, `OnePagerService._us_risk_free_rate`, EODHD GBOND, faixa 2–8%, fallback 4,2%) + os mesmos 6 p.p. ≈ **10–10,5%** com o 10Y em 4–4,5% | `status` (`full_match`/`near_buy`/`watchlist`), Top 10 de NASDAQ/NYSE, linha e quadrantes da matriz, texto dos critérios. TP e buy-in **não** mudam. |
| (c) | `market_data/b3_screener.py` | BCB SGS 432 só pela última posição da lista (vírgula decimal descartada); sem BCB, o governador do COPOM de 05/08/2026 (14%) valia **mesmo vencido** (janela de 50 dias acabou em 24/09) e o Brapi era ignorado | BCB SGS 432 é a fonte primária (linha de **data** mais recente, vírgula lida); governador só dentro da janela; vencido, cede ao Selic ao vivo do Brapi; sem nada melhor, governador marcado `copom_governor_stale`. A fonte vencedora é gravada no snapshot do ciclo (`outputs.selic_provenance`) | Com o BCB respondendo (caso normal), **o número não muda** — só passa a ser rastreável. Com o BCB fora do ar, o Selic deixa de ser 14% fixo: muda WACC, hurdle de upside (Selic + 6) e de entrada (Selic + 2) da B3, logo TP, buy-in e status da B3. |
| (d) | `market_data/us_screener.py` | `consensus_weight_percent` = **35** em toda ação dos EUA com consenso | O peso que `official_blend_v1` de fato aplicou: `consensus_weight_diagnostic` do produtor = 20% + mín(analistas/10; 1) × 15% (20–35%); **0** na ponte da listagem primária e sem cobertura | Peso exibido (Internal x% / Consensus y%) e `consensus_weight_percent` dos registros de predição. O TP **não** muda (o blend já usava o peso real; só o peso gravado estava errado). |
| (e) | `investor_relations.py` | `acceptanceDateTime` do JSON de submissions lido como UTC — fato verificado em 17/10: o JSON é o instante verdadeiro **mais** o offset de Nova York (AAPL 0000320193-26-000018: header 20260730163028 NY, JSON 2026-07-31T00:30:28Z) | O header do arquivamento (`…/<accn>-index-headers.html`, relógio de Nova York) é a fonte da verdade; enquanto não for lido, o JSON é lido com a semântica correta (rótulo − offset NY). Cada evento diz qual leitura carrega (`raw_metadata.acceptance_time_source`: `filing_header` ou `submissions_json_ny_corrected`) | `published_at` dos eventos SEC recua **4 h (EDT) / 5 h (EST)** para o instante real de aceitação: frescor de RI (`latest_ir_event_at`, `ir_status`), ordenação e janela de 14 dias do full-text. Nenhum TP muda diretamente. |

## Notas de operação

- **C3PO_SEC_CONTACT** (novo; só no host, nunca no repositório): o contato de fair access da SEC. Sem ele o header
  **não é lido** (a SEC não é chamada) e o evento fica com a leitura corrigida do JSON, com um aviso no log por
  processo. Com ele, os headers são lidos do mais novo para o mais antigo, no máximo 40 por sincronização, a ≤ 8 req/s, e
  um header já lido é reaproveitado do banco (`Database.stored_sec_acceptances`) — nunca relido, nunca rebaixado à
  leitura do JSON. Se um header divergir da leitura corrigida do JSON, o log avisa que a semântica verificada em 17/10
  deixou de valer.
- **Só o `investor-relations-worker` lê headers** (`InvestorRelationsService(..., read_sec_headers=True)`; um único
  contêiner), então o ritmo de 8 req/s dessas leituras vale para o host inteiro. API, `valuation-worker` e `r2d2-worker`
  só reaproveitam os instantes já gravados. As chamadas SEC que já existiam (`company_tickers`, submissions, full-text)
  continuam sem esse limitador: um limitador compartilhado pelo host fica pendente para antes de a frente XBRL ganhar o
  próprio cliente SEC.
- **Falhas.** Um 403/429 da SEC interrompe as leituras de header daquela sincronização. Um header que falha (erro HTTP,
  rede, ou sem `ACCEPTANCE-DATETIME`) espera 1 h, depois 2 h, 4 h… até no máximo 1 dia antes de nova tentativa. Assim
  ele não ocupa toda vez uma das 40 vagas. Essa espera fica em memória e zera quando o worker reinicia. O passo inteiro
  é best-effort: se falhar, `sync_sec` segue e grava os eventos de insider que o R2D2 lê. A divergência de `sync_sec` em
  relação à origem pinada do R2D2 está anotada em `r2d2-risk-source/DIVERGENCES.md`.
- Os eventos SEC já gravados nos últimos 365 dias são corrigidos na próxima sincronização (o upsert por accession
  reescreve `published_at`); o header vai substituindo a leitura do JSON em lotes de 40.
- Ciclos dos EUA publicados antes do deploy não têm o hurdle gravado nas linhas: até o próximo ciclo noturno, critérios
  e matriz usam o 10Y atual, enquanto o `status` dessas linhas ainda é o do hurdle antigo (20%). Some no primeiro ciclo
  novo; nada é recalculado retroativamente (registros imutáveis).
- Conferência pós-deploy: `outputs.selic_provenance.source` do próximo `valuation_universe/B3_UNIVERSE`
  (`bcb_sgs_432` esperado); `criteria.tp_upside` de NASDAQ/NYSE começando por `C3PO TP upside >= US 10Y Treasury`;
  `consensus_weight_percent` dos EUA entre 20 e 35 (0 na ponte); `raw_metadata.acceptance_time_source` dos eventos SEC.
- Reversão: reverter o commit. Os registros de predição gravados enquanto a versão esteve no ar continuam válidos e
  imutáveis (carregam o status e o peso com que foram feitos).

Testes: `tests/test_us_screener.py` (b, d — inclusive no produtor real do One Pager), `tests/test_market_data.py` (c),
`tests/test_investor_relations.py` (e). Todos falham no código anterior e passam neste.
