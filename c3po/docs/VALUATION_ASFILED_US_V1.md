# Valuation as-filed — frente EUA (SEC EDGAR XBRL), V1

Direção do dono de 17/10/2026: o Valuation passa a decidir compra/não compra; demonstrações trimestrais **como
protocoladas** (SEC XBRL nos EUA, CVM na B3), Radar e todas as métricas definidas; cronograma comprimido em duas semanas.
Este documento cobre a frente EUA (fonte de registro aprovada pelo dono): vintages, detecção de protocolos novos, a ponte
as-of com reconciliação em sombra e o gatilho de reavaliação dos TPs dos EUA.

**Nada aqui muda número servido.** Tudo roda atrás de `C3PO_VALUATION_ASFILED_ENABLED` (padrão **desligado**): com a
chave desligada nada é buscado na SEC, nenhuma tabela nova é escrita e nenhuma linha servida muda. As únicas mudanças
sem chave são (1) a correção do relógio do JSON de submissions nos eventos SEC de Investor Relations e (2) o
espaçamento das requisições SEC do cliente de Investor Relations pelo limitador do processo (abaixo).

## Relógio de aceitação: o cabeçalho manda

Fato verificado em 17/10/2026 (AAPL): o `acceptanceDateTime` do JSON de submissions **não é UTC verdadeiro** — é o
instante real **mais** o deslocamento UTC de Nova York.

| Acesso | Cabeçalho `ACCEPTANCE-DATETIME` (Nova York) | JSON `acceptanceDateTime` |
|---|---|---|
| 0000320193-26-000018 | 20260730163028 (EDT) | 2026-07-31T00:30:28.000Z |
| 0000320193-26-000005 | 20260129163033 (EST) | 2026-01-30T02:30:33Z |

* Fonte de verdade: `…/Archives/edgar/data/<cik>/<acesso-sem-traços>/<acesso>-index-headers.html`, campo
  `<ACCEPTANCE-DATETIME>` em America/New_York (`sec_xbrl.acceptance_from_header`).
* Onde só existe o JSON, `sec_xbrl.acceptance_from_submissions_json` desfaz o defeito (subtrai o deslocamento em vigor
  no próprio instante) — é a única correção do código; os eventos SEC de IR também a usam. Um só caminho dá aos eventos
  SEC de IR o relógio do cabeçalho (`InvestorRelationsService._apply_sec_header_acceptances`, defeito e de
  `VALUATION_DEFECTS_2026-10-17.md`): o evento nasce com o JSON corrigido (`raw_metadata.acceptance_time_source =
  submissions_json_ny_corrected`, valor bruto em `acceptance_datetime_json`); se o cabeçalho já foi lido — gravado no
  próprio evento por uma sincronização anterior, ou registrado por este poll em `statement_filings` — o instante é
  reaproveitado sem chamar a SEC; senão o worker de IR lê o cabeçalho com o mesmo cliente deste poll
  (`acceptance_time_source = filing_header`, relógio de Nova York em `acceptance_datetime_header`). Nunca rebaixa um
  cabeçalho já lido para o JSON; falha nesse passo nunca derruba `sync_sec`.
* Toda leitura de cabeçalho confere o JSON corrigido; divergência é contada (`json_clock_mismatches` no resultado do
  poll e no aviso da execução `sec_asfiled`) e registrada em log — se a SEC mudar o comportamento, aparece, não desloca
  relógios em silêncio. O JSON bruto fica gravado em `statement_filings.json_accepted_raw` como evidência.

## Acesso justo à SEC

* `C3PO_SEC_CONTACT` (somente no host; nunca no repositório; a única configuração de contato SEC) vai no User-Agent:
  `C3PO Chief of Staff Intelligence <contato>`. Sem ele, `SecXbrlClient` recusa existir (`SecContactMissing`), a
  execução `sec_asfiled` falha nomeando a variável e o passo de cabeçalho de `sync_sec` não lê cabeçalho nenhum (um
  aviso por processo).
* **Só o worker de IR lê cabeçalhos** (`InvestorRelationsService(..., read_sec_headers=True)`): ele guarda um único
  `SecXbrlClient` (`sec_client`) para o passo de cabeçalho de `sync_sec` e para este poll. Fora dele, `sync_sec_asfiled`
  não faz nada (nem com a chave ligada) e `sync_sec` só reaproveita instantes já gravados.
* Um limitador por processo (`sec_xbrl.process_rate_limiter`) espaça o início de cada requisição em 1/taxa; teto
  absoluto 8/s; `C3PO_SEC_MAX_REQUESTS_PER_SECOND` padrão **2,5**, porque o teto de 8/s vale para o host e três
  processos consultam o EDGAR: a API (One Pager sob demanda e `/investor-relations/sync` chamam `sync_sec`), o worker
  de IR e o worker de valuation na virada da noite — 3 × 2,5 = 7,5 ≤ 8 mesmo se os três coincidirem. O cliente httpx de
  Investor Relations passa pelo mesmo limitador (gancho de requisição, só para hosts `*.sec.gov`). O worker do R2D2
  também instancia o serviço de IR, mas não chama o EDGAR (usa só o `market_data.http` do One Pager); se um quarto
  processo passar a chamar, baixar para 2.
* O cliente as-filed só aceita hosts da SEC. Um 403/429 da SEC (`SecThrottled`) encerra o passe na hora — nada de
  seguir pelo resto do universo; o próximo poll recomeça.

## Migração 051 — `statement_filings` e `statement_vintages` (append-only)

* `statement_filings`: um documento por linha (SEC: um acesso; acesso é imutável, emenda é outro acesso `…/A`, por isso
  `document_version = 1`), com `accepted_at` do cabeçalho, `accepted_source = sec_header`, itens do 8-K, símbolos do
  universo mapeados ao emissor na detecção, período do relatório, data de protocolo, hash do cabeçalho.
* `statement_vintages`: um fato por documento — `(market, issuer_key, source, doc_id, document_version, concept, unit,
  period_start, period_end)` é a chave natural (`UNIQUE NULLS NOT DISTINCT`, PostgreSQL 16: fato instantâneo tem
  `period_start` nulo e continua único). `fiscal_year`/`fiscal_period` são o foco fiscal **do documento** como a SEC
  informa; o período do fato é `period_start`/`period_end`. `value NUMERIC`, `filed_date`, `accepted_at`,
  `first_seen_at`, `is_first_publication`, `row_hash` (sha256 do conteúdo, nunca das colunas de contabilidade).
* Append-only: gatilhos recusam UPDATE/DELETE/TRUNCATE. Um fato re-reportado por documento posterior (comparativo,
  reapresentação) é linha nova daquele documento; a primeira publicação nunca é reescrita.
* `is_first_publication` é decidido na inserção, sob trava consultiva por emissor, contra todas as linhas da mesma
  identidade de fato. O ingestor insere os documentos de cada emissor em ordem de aceitação e para no primeiro cabeçalho
  ilegível (ele e os seguintes ficam adiados), então a marca vale; um documento que chegue depois de outro aceito mais
  tarde é gravado, contado (`out_of_order`) e logado.
* Adiamento nunca vira lacuna permanente: um documento só é dado por resolvido quando suas linhas foram gravadas ou
  quando o companyfacts o tem sem nenhum fato da escada (nunca só por constar do companyfacts). O emissor com documentos
  adiados é reingerido no poll seguinte (5 min de espera, dobrando a cada nova falha seguida, teto de 6 h —
  `deferred_retries` no resultado). Como esse estado é da memória do processo, há também o reparo durável: emissor cujo
  10-Q/10-K original mais recente nas submissions não tem fato gravado é reingerido (`gap_ingestions`, pelo mesmo
  orçamento do backfill) — cobre o reinício do worker no meio de um adiamento.
* Genérica de propósito: a frente B3 (CVM) pode escrever nas mesmas tabelas (`market = 'B3'`).

## Escada de conceitos e trimestres (`app/sec_xbrl.py`)

| Campo | Conceitos, em prioridade |
|---|---|
| receita | `Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`, `…IncludingAssessedTax`, `SalesRevenueNet`, `RevenuesNetOfInterestExpense` |
| lucro líquido | `NetIncomeLoss`, `ProfitLoss`, `NetIncomeLossAvailableToCommonStockholdersBasic` |
| LPA diluído | `EarningsPerShareDiluted`, `EarningsPerShareBasicAndDiluted` (USD/shares) |
| lucro operacional | `OperatingIncomeLoss` |
| D&A | `DepreciationDepletionAndAmortization`, `DepreciationAndAmortization`, `DepreciationAmortizationAndAccretionNet`, `Depreciation` |
| FCO | `NetCashProvidedByUsedInOperatingActivities`, `…ContinuingOperations` |
| capex | `PaymentsToAcquirePropertyPlantAndEquipment`, `PaymentsToAcquireProductiveAssets` |
| caixa | `CashAndCashEquivalentsAtCarryingValue`, `CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents`, `Cash` |
| dívida | longo prazo não circulante (`LongTermDebtNoncurrent`, `LongTermDebtAndCapitalLeaseObligations`), `LongTermDebt` (inclui parcela circulante), `DebtCurrent`, parcela circulante (`LongTermDebtCurrent`, `LongTermDebtAndCapitalLeaseObligationsCurrent`), curto prazo (`ShortTermBorrowings`, senão `CommercialPaper`) |
| PL | `StockholdersEquity`, `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest` |
| ações em circulação | `dei:EntityCommonStockSharesOutstanding` (por classe → somadas) |

* Só documentos da família 10-Q/10-K (`10-Q`, `10-K`, `…/A`, `…T`); fatos de períodos terminados há mais de seis anos
  não entram (toda publicação de um fato mantido entra).
* Repetição idêntica dentro do documento colapsa; contagem de ações por classe (mesmo documento e data de capa) é
  somada; qualquer outro conflito descarta o fato (contado em `conflicting`), nunca chuta.
* Trimestres (`discrete_quarters`): fato de três meses é trimestre reportado; YTD com mesmo início dá os demais por
  diferença — Q2 = 6M − 3M, Q3 = 9M − 6M, **Q4 = FY − 9M**; reportado sempre vence derivado.
* Dívida total = longo + curto sem dupla contagem (`valuation_asfiled.total_debt`): `DebtCurrent` quando marcado; senão
  parcela circulante + empréstimos de curto prazo (commercial paper só sem total de curto prazo); só `LongTermDebt`
  existente → ele + curto prazo.

## Detecção de protocolos novos (extensão do polling SEC de `investor_relations.py`)

* Universo: as **ações** dos ciclos mais recentes `valuation_universe/NASDAQ_UNIVERSE` e `NYSE_UNIVERSE`
  (`valuation_asfiled.us_valuation_universe`; ETFs não protocolam 10-Q). CIK pelo `company_tickers.json` da própria SEC.
* `InvestorRelationsService.sync_sec_asfiled` (fonte `sec_asfiled`), chamada pelo laço do worker de IR logo depois de
  `sec` quando a chave está ligada; só roda no processo leitor de cabeçalhos (o worker de IR). **Não** faz parte de `sync("all")`, então o ciclo noturno do worker de valuation
  não carrega o passe pesado. Universo não entra em `ir_security_map` (isso transformaria os ~600 nomes em "watched" e
  multiplicaria insider/notícias/full-text a cada 15 min).
* Por emissor, a cada poll: submissions → registra todo 10-Q/10-K (e emendas) e 8-K com **item 2.02** aceitos nos
  últimos 10 dias com o relógio do cabeçalho; ingere companyfacts quando há documento de demonstração novo, pendente
  (registrado há ≤ 3 dias e ainda sem fatos — o XBRL da SEC pode atrasar; nova tentativa a cada hora), quando houve
  adiamento por cabeçalho (acima) ou quando o 10-Q/10-K original mais recente do emissor não tem fato gravado (backfill
  e reparo de lacuna, `C3PO_VALUATION_ASFILED_BACKFILL_ISSUERS_PER_POLL`, padrão 10; um protocolo novo ou uma nova
  tentativa nunca espera o orçamento). Um emissor com erro não para o passe.

## Ponte as-of e reconciliação em sombra (`app/valuation_asfiled.py`)

* `as_of_fundamentals(database, issuer_key, as_of)`: só vintages com `accepted_at <= as_of`; por fato, a aceitação mais
  recente até `as_of` (reapresentação conhecida supera a original); TTM = quatro trimestres contíguos terminando no
  último trimestre de receita (lucro, sem receita); saldos na mesma data (ações: a capa mais recente). Saída com TTM,
  saldos e datas, derivados (EBITDA = lucro operacional + D&A; FCL = FCO − capex; dívida total), histórico de 8
  trimestres, proveniência por campo (conceito, acesso, aceitação, primeira publicação, trimestre derivado), `missing`
  e `warnings`.
* LPA diluído não é aditivo. Quando os quatro trimestres são exatamente um ano fiscal, o TTM é o LPA anual reportado
  (exato, sem FY − 9M). Fora disso é a soma dos trimestres, **recusada** (`None`, aviso
  `eps_diluted_share_basis_changed`) quando os documentos por trás deles reportam contagens de ações na capa 1,4× ou
  mais distantes — um desdobramento só reapresenta o LPA nos documentos posteriores a ele, então trimestres de bases
  diferentes nunca são somados. Resíduo: dentro de uma base estável, o Q4 derivado (FY − 9M) segue aproximado quando a
  contagem média muda (recompras), como nos provedores; um desdobramento menor que 1,4× (5:4) não é detectado.
* `record_us_reconciliation`: no build do produtor EUA (`us_screener._build`, só com a chave), compara campo a campo o
  as-filed conhecido no instante em que a EODHD respondeu com os fundamentos EODHD que **aquele** build consumiu
  (receita TTM, lucro TTM, LPA TTM, lucro operacional, D&A, EBITDA, FCO, capex, caixa, dívida, PL, ações); concordância
  ≤ 2 % de diferença relativa. Grava `valuation_asfiled_reconciliation/<M>_ASFILED_RECONCILIATION` (por símbolo e
  resumo por campo). Falha nunca derruba o build; nada volta para as linhas.

## Gatilho de reavaliação dos EUA (migração 053, `valuation_tp_staleness`, append-only)

* `evaluate_us_filings` (processador de IR a cada poll e o corte noturno logo após `us_screener.refresh_all`, ambos só
  com a chave): todo 10-Q/10-K (e emendas) ou 8-K 2.02 registrado nos últimos 10 dias é avaliado uma vez por símbolo
  contra o TP oficial em vigor (uma geração por passe). O período que o TP precisa cobrir (`expected_period_end`) é,
  num 10-Q/10-K, o período protocolado; num 8-K 2.02, o **trimestre anunciado** (`announced_quarter_end`): o último fim
  de trimestre antes do dia da aceitação (Nova York), contado a partir do último período de 10-Q/10-K registrado do
  emissor (três meses para fechamento em fim de mês, treze semanas para ano de 52/53 semanas); sem nenhum registrado
  ainda, o último fim de trimestre civil antes do dia (conservador: para ano fiscal fora do calendário cai depois do fim
  real, então um TP pré-resultado continua marcado; um release mais de um mês após um fechamento fora do calendário pode
  ficar `stale` até o backfill registrar as demonstrações do emissor).
  * `stale` — o TP oficial foi previsto antes da aceitação (`tp_predates_acceptance`) ou seus fundamentos não alcançam
    `expected_period_end` (`fundamentals_predate_period`); `queued_for_cut_at` = próxima meia-noite de São Paulo (o corte
    noturno);
  * `cleared` — um ciclo previsto depois da aceitação **e** cujos fundamentos alcançam `expected_period_end` (7 dias de
    tolerância) está em vigor: `tp_after_acceptance` na primeira avaliação, `revalued_by_cut` depois de um `stale`. Um
    corte qualquer depois de um 8-K 2.02 não basta: na janela entre o release e o 10-Q/10-K (1 a 3 semanas) o TP fica
    `stale` até os fundamentos do provedor trazerem o trimestre anunciado;
  * `untracked` — o símbolo não tinha TP oficial. Não é terminal: dentro da janela de 10 dias o par é reavaliado a cada
    passe, então um TP que entre na geração depois (ex.: ciclo das 00:00 promovido após um protocolo das 16:30) ainda é
    marcado.
* Marca `stale` pendente é reconferida a cada passe, qualquer que seja a idade. `stale_us_tps` devolve as pendentes por
  símbolo — o que a frente de decisão (052) deve ler antes de confiar num TP dos EUA.

## Chaves (variáveis de ambiente, não `Settings`)

`config.py` entra no hash do pacote de implementação do R2D2 V2 (`r2d2_v2_earnings_package.PACKAGE_FILES`): um campo
novo ali muda o `implementation_package_sha` amarrado à release, ao coletor sombra
(`COLLECTOR_IMPLEMENTATION_PACKAGE_MISMATCH`) e à configuração de capacidade (`CAPACITY_CONFIG_PACKAGE`). Por isso o
contato e o ritmo da SEC e as chaves desta frente e do decisor são lidos do ambiente, no momento da chamada, por
`app/valuation_env.py` — como as chaves da frente CVM (`official_statements`) e dos produtores do R2D2 V2. O `env_file`
do compose põe os valores do host no ambiente do processo; os nomes são os mesmos.

| variável | padrão | quem lê |
|---|---|---|
| `C3PO_SEC_CONTACT` | vazio (nenhuma chamada de cabeçalho nem as-filed) | `SecXbrlClient` (User-Agent) |
| `C3PO_SEC_MAX_REQUESTS_PER_SECOND` | 2,5 (0 < taxa ≤ 8) | o limitador SEC de cada processo |
| `C3PO_VALUATION_ASFILED_ENABLED` | desligada | poll do worker de IR, gatilho de reavaliação, corte noturno, gancho sombra do produtor EUA |
| `C3PO_VALUATION_ASFILED_BACKFILL_ISSUERS_PER_POLL` | 10 (0 a 200) | backfill do poll as-filed |
| `C3PO_VALUATION_DECISOR_SHADOW` | desligada | fase noturna do decisor, gravação e saúde da fase |

Valor ilegível volta ao padrão (chave: desligada); número fora da faixa é trazido para dentro dela.

## Operação

1. Host: `C3PO_SEC_CONTACT` configurado (contato real, fora do repositório); opcional `C3PO_SEC_MAX_REQUESTS_PER_SECOND`.
2. Ligar `C3PO_VALUATION_ASFILED_ENABLED=true` nos workers de IR e de valuation (e no produtor EUA, mesmo container do
   worker de valuation). O primeiro dia faz o backfill (~30 requisições por emissor, 10 emissores por poll; a 2,5/s
   cada poll leva ~2 min de backfill mais ~4 min das submissions do universo).
3. Conferir: execuções `sec_asfiled` (`ingestion_runs`) sem `json_clock_mismatches`; `statement_vintages` crescendo;
   snapshot de reconciliação por mercado; `valuation_tp_staleness` com marcas.
4. Desligar a chave volta tudo ao comportamento anterior; as tabelas ficam (append-only).
