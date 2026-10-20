# Valuation — Decisor V1 (sombra)

Direção do dono de 17/10/2026: o Valuation passa a ser quem decide compra / não-compra. Esta é a V1, **em sombra**:
grava veredictos imutáveis por nome por noite, não muda nenhum número servido, não escreve a seleção oficial e não
toca tabelas, ordens ou posições do R2D2. Código: `backend/app/valuation_decision.py`; migração `db/052_valuation_decisions.sql`.

## Veredicto

| Veredicto | Quando |
|---|---|
| `COMPRA_PERMITIDA` | todos os portões passaram (`reason_codes = ["ALL_GATES_PASSED"]`) |
| `OBSERVAR` | TP confiável, mas sem permissão: sem margem hoje (`PRICE_ABOVE_BUY_IN`, `TP_MARGIN_INSUFFICIENT`), insumo da margem ainda não medido (`E_PROFILE_WARMING_UP`, `E_PROFILE_UNAVAILABLE`, `MARKET_RATE_UNAVAILABLE`), nos EUA TP à espera da reavaliação que um protocolo aceito depois dele disparou (`TP_STALE_AFTER_FILING`) ou pergunta sem resposta (`STALENESS_SOURCE_UNAVAILABLE`, `STALENESS_SOURCE_STALE`), ou resultado anunciado nas próximas N sessões (`EARNINGS_WITHIN_N`, só EUA) ou linha ilegível do calendário sobre o nome sem estimativa (`EARNINGS_CALENDAR_ROW_INVALID`, só EUA) |
| `VETO` | o TP ou seus dados não são confiáveis agora (frescor, qualidade, defeito de dado); lista **todos** os códigos que falharam, inclusive os de OBSERVAR |

**Marcas** (`checks.events.marks`; nunca mudam o veredicto): `EARNINGS_DATE_ESTIMATED`, `EARNINGS_CALENDAR_UNAVAILABLE`,
`CONSENSUS_EPS_CUT_30D`, `NEWS_SENTIMENT_NEGATIVE` (nunca portão, mesmo listado em `event_gates`: `NEVER_GATES`) — e
`EARNINGS_WITHIN_N` / `EARNINGS_CALENDAR_ROW_INVALID` na B3, e `EARNINGS_CALENDAR_ROW_INVALID` ao lado de uma estimativa. Todo registro guarda também o
**contrafactual** `checks.counterfactual.verdict_without_events` (o veredicto com os portões de evento desligados), para um
relatório somente-leitura comparar com e sem o portão.

## Regras

* **TP** = a linha oficial **servida** (`official_rows` / `official_row` por UMA geração): `our_tp`/`buy_in` do registro —
  os internos quando a geração seleciona `official_internal_v1`. O decisor nunca calcula, ajusta ou mistura TP.
* **Margem**: `ask_ou_preço <= buy_in` **e** `TP × (1 − e_profile) >= ask_ou_preço × (1 + h_market)`. Com ask disponível,
  ele é o preço de execução (lado conservador).
  * `e_profile` = erro absoluto **mediano** medido pelo produtor para o `valuation_profile` do nome
    (`valuation_calibration/<M>_POWER_MODEL`, `metrics[perfil].median_absolute_error_percent`, chave nova e apenas
    diagnóstica nos dois screeners — nenhum fator a lê). Base **só preço** nos dois mercados: a B3 já tira o dividendo
    esperado da expectativa; nos EUA a expectativa da métrica é o `upside_percent` (o retorno total esperado soma o
    dividend yield e o realizado é só preço — o fator continua com as amostras dele, nenhum número servido muda). Só vale
    com calibração `active`, horizonte observado em 60–150 dias, perfil com o mínimo de amostras e snapshot com até 7 dias;
    caso contrário, sem permissão.
  * `h_market` = `(1 + taxa) ^ horizonte − 1 + prêmio` (TP de 12 meses; prêmio 0 por padrão). Fonte: a primeira
    **fresca** (≤ 10 dias) da ordem declarada — B3: BCB SGS 432 (observações datadas), depois a Selic do ciclo oficial B3
    (`outputs.macro.selic`); US: T-bill de 13 semanas (pacote do cash-yield do R2D2), depois a 5Y interpolada (pacote
    validado como o V3 valida, com idade medida pela data de observação dos yields, nunca pelo `as_of` do pacote). A Selic
    do ciclo é **sem data**: o ciclo grava só o valor, e o produtor cai na constante do governador quando brapi e BCB
    falham — não dá para distinguir. Ela só conta se o bloco a listar em `undated_rate_sources_admitted` (padrão: vazio),
    e então fica marcada `undated` no registro. Pacotes com hash que não confere, ou observação ainda não disponível no
    relógio da rodada, são ignorados. A fonte usada fica nomeada no registro.
* **Frescor (VETO)**: `tp_stale` marcado na linha; sessão do TP mais de 1 sessão atrás da última sessão completa;
  fundamentos mais velhos que um trimestre + 45 dias (92 + 45 = 137 dias) ou sem data; preço que andou mais de X % desde o
  corte (preço do registro do TP) ou sem preço; preço **não observado depois do fechamento da última sessão completa**
  (`PRICE_SESSION_STALE`). O preço do próprio corte é da sessão do TP: com o TP 1 sessão atrás (tolerado), a sessão que
  faltou nunca foi observada e o movimento leria 0 %. Vale um ciclo de universo publicado depois daquele fechamento
  (mesmo que a geração mantenha o ciclo antigo) ou uma cotação fresca.
* **Qualidade (VETO)**: não validado (`tp_validation_status` quando o produtor emite — B3 —, senão `signal_quality` — US);
  dispersão de métodos acima do limite ou desconhecida; confiança abaixo do limite ou desconhecida; qualquer marca de
  defeito de dado (`data_defect`, `data_defects`).
* **Reavaliação após protocolo (OBSERVAR; só EUA)**: a migração 053 (`valuation_tp_staleness`, frente as-filed) marca o
  TP oficial dos EUA contra os protocolos da SEC (10-Q/10-K e emendas, 8-K 2.02). O decisor a lê **uma vez por rodada,
  no relógio da rodada** (`valuation_staleness.us_staleness_at`; o leitor fica fora de `valuation_asfiled.py`, arquivo produtor que o backtest PIT dos EUA fixa por hash): só marcas com `recorded_at` ≤ relógio **e**, no
  PostgreSQL, `created_at` ≤ relógio (inseridas até ali); por par (protocolo, símbolo) vale o estado mais recente entre
  elas (empate de `recorded_at`, que o gatilho nunca grava, resolve para o mais estrito). Par cujo último estado é
  `stale` → `TP_STALE_AFTER_FILING`, e o registro nomeia o(s) protocolo(s) (id da marca 053, accession, formulário,
  itens, aceitação, `recorded_at`, motivo, `expected_period_end`). `cleared` e `untracked` não bloqueiam. Um `cleared`
  gravado depois do relógio nunca volta para uma noite anterior: o replay da noite decide o mesmo. Tabela ausente
  (053 não aplicada; `to_regclass` nulo) → `STALENESS_SOURCE_UNAVAILABLE` em **todo** nome dos EUA: falha fechada,
  como todo insumo não medido de uma permissão (`E_PROFILE_UNAVAILABLE`, `MARKET_RATE_UNAVAILABLE`); erro de leitura
  derruba a rodada, como qualquer outra leitura do decisor. **B3: não se aplica** (`not_applicable`; a 053 só marca os
  EUA) — e linha servida para mercado dos EUA nunca é `not_applicable` (falha fechada). OBSERVAR, não VETO (decisão da
  coordenação de 17/10): TP desatualizado por protocolo é "ainda não sabemos", não opinião negativa — ele espera o corte
  que o reavalia. **Assimetria declarada com `TP_STALE_FLAG`**, que continua VETO: aquela é a marca do próprio produtor
  na linha (o produtor declara a linha não confiável, sem reavaliação agendada), na família de frescor junto com
  `TP_SESSION_STALE` e `FUNDAMENTALS_STALE`, e o teste da família a trata como veto; esta é uma inferência nossa com
  resolução conhecida (o próximo corte).
  * **Vivacidade da fonte** (julgada **primeiro**): tabela vazia não é evidência enquanto ninguém olha. A 053 só conta com
    uma execução do poll as-filed (`ingestion_runs`, fonte `sec_asfiled`, `InvestorRelationsService.sync_sec_asfiled`)
    **bem-sucedida e com progresso** (`records_read` > 0; um passe que a SEC limitou é gravado `partial` e não conta),
    **iniciada** em D − 6 h ou depois (o que ela observou tem no máximo 6 h: `staleness_poll_max_age_hours`) e
    **concluída** até D − ε. Execução ainda rodando, concluída dentro da margem ou depois, falha, parcial ou sem progresso
    não é lida. Sem ela, **todo** nome dos EUA sai `STALENESS_SOURCE_STALE` (falha fechada; distinto de
    `STALENESS_SOURCE_UNAVAILABLE`) **exista a tabela ou não** — a tabela ausente lê como vazia, então uma noite de antes
    da 053 se reproduz igual depois que ela chega; um nome com marca pendente leva os dois códigos. Com poll vivo e sem
    tabela: `STALENESS_SOURCE_UNAVAILABLE`. O registro nomeia o poll em que confiou (`trigger_poll`: fonte, id, linhas
    lidas, início, conclusão, emissores não observados).
  * **Cobertura por emissor** (revisão do Codex de 19/10): o poll grava nos metadados da execução os emissores que não
    conseguiu observar (`failed_issuers`, só CIKs — nenhum símbolo), lidos dos erros por emissor que o passe já devolve
    (`"<cik>: <erro>"`; `sec_xbrl.py` é produtor congelado e não muda). Um poll vivo cobre um nome **só se observou o
    emissor dele** (o emissor vem dos filings da 051 conhecidos em D): emissor em `failed_issuers` → o nome sai
    `STALENESS_SOURCE_STALE`; nome de emissor desconhecido, quando o poll perdeu algum emissor → também. Ex.: timeout nas
    submissions de um emissor e leitura do outro dão execução `succeeded` com progresso — viva para o segundo, nunca
    para o primeiro (`issuer_observed` na procedência).
* **Eventos** (`event_gates` no bloco diz quais seguram a permissão; todo outro código de evento é marca):
  * **`EARNINGS_WITHIN_N`** (portão → OBSERVAR nos EUA; **marca** na B3): resultado conhecido em D cuja **sessão do
    anúncio ou sessão de reação** cai em [T+1, T+N] (T = última sessão completa, N = 2). Sessão do anúncio = a data, ou a
    próxima sessão quando a data não é sessão; sessão de reação (a que o preço sente) = a mesma para BMO, a **seguinte**
    para AMC ou horário desconhecido (o provedor não marca DAY: sem marca é desconhecido). Por isso um AMC (ou sem
    horário) em T conta: o preço com que a noite decide é o fechamento de T, que ainda não viu o resultado — **risco de
    gap** na abertura de T+1. Um BMO em T já está no fechamento de T.
    * **A regra, exatamente** (revisada em 18/10 após a verificação independente; fecha um caso que falhava aberto):
      * **Calendários lidos**: todos os snapshots (fase `earnings_calendar`, abaixo) **recebidos** em [D − 36 h, D − ε]
        **e** o último recebido **antes** dessa janela (qualquer que seja a idade; os anteriores a ele não são lidos).
      * **PORTÃO** se **qualquer** calendário lido — utilizável ou não, recente ou não — tem um evento do nome cuja sessão
        do anúncio ou de reação cai em [T+1, T+N].
      * Senão, "**nenhum evento**" só pode ser respondido pelo **calendário utilizável mais novo** da janela, e só se ele
        tem uma linha **válida** do nome (fora da janela) **e nenhum** calendário lido tem linha inválida do nome.
        Utilizável: recebido em [D − 36 h, D − ε], ao menos `earnings_calendar_min_us_events` = 100 eventos US dentro da
        janela pedida (menos é calendário parcial — inclusive zero), linhas inválidas **sem dono** ≤
        `earnings_calendar_max_invalid_share` = 5 % das linhas (acima é lixo; linhas inválidas atribuídas a um nome
        valem só para aquele nome) e janela pedida cobrindo [T+1, T+N] (as pontas incluídas).
      * **Em todo outro caso** — nenhum calendário utilizável; o utilizável mais novo **sem linha do nome**; linha
        inválida do nome em **qualquer** calendário lido — a **estimativa da 051** responde: alcança a janela → portão
        (`EARNINGS_DATE_ESTIMATED`); não alcança → sem portão (`EARNINGS_DATE_ESTIMATED`, com o motivo).
      * **Sem estimativa**: se algum calendário lido tem **linha inválida do nome** → **falha fechada**: OBSERVAR com
        `EARNINGS_CALENDAR_ROW_INVALID` (decisão da coordenação de 18/10: uma linha ilegível do provedor sobre o nome é
        um aviso, não prova de que não há evento); senão → sem portão, marca `EARNINGS_CALENDAR_UNAVAILABLE` com o motivo
        (regra de abstenção: falhar aberto é aceitável, e fica registrado).
      * Linha inválida do nome **com** estimativa (dentro ou fora da janela): a estimativa decide e
        `EARNINGS_CALENDAR_ROW_INVALID` fica como **marca**. `EARNINGS_CALENDAR_ROW_INVALID` é o ramo de falha fechada do
        portão de resultados: vale como portão onde `EARNINGS_WITHIN_N` vale (EUA; marca na B3), sem campo novo no bloco,
        e sai no contrafactual `verdict_without_events` junto com ele. O registro guarda cada calendário lido (recusa, se
        lista o nome, se tem linha inválida dele), qual respondeu (`answering`) e `row_invalid`.
    * **Por que 100**: a janela que a fase pede é de 37 dias corridos [hoje − 7, hoje + 30]; mesmo fora de temporada
      (meados de dezembro a meados de janeiro, ou o começo de junho e de setembro) reportam os emissores de ano fiscal fora
      do calendário (~30 % dos ~4.000 operacionais listados nos EUA, 4 resultados por ano cada, espalhados pelos meses) e
      os retardatários de dezembro — da ordem de centenas de anúncios em qualquer janela de 37 dias, várias vezes o piso.
      Abaixo disso a resposta é parcial; a confirmar com os primeiros snapshots reais (`counts.by_exchange.US`).
    * **Estimativa por cadência** (só EUA; filings da 051 **originais** — 8-K com item 2.02, 10-Q, 10-K; emendas `/A`
      nunca —, aceitos até D e **registrados** (`first_seen_at`) até D − ε, nos últimos `earnings_filings_lookback_days` =
      400 dias; a base é sempre a **aceitação** em dia de Nova York, nunca o registro): (1) **sazonal** — o trimestre
      seguinte ao último período protocolado, um ano antes (o período encontrado a até 10 dias de um ano antes): o
      release dele (o primeiro 8-K 2.02 aceito depois do fim daquele trimestre e antes do fim do seguinte; senão o
      próprio 10-Q/10-K) + 364 dias, mantendo o dia da semana; (2) senão o **mais recente** entre o último 8-K 2.02, o
      último 10-Q e o último 10-K: 8-K ou 10-Q → aceitação + 91 dias; 10-K → fim do período + 91 dias + a defasagem do
      último 10-Q do emissor (aceitação − fim do período; sem 10-Q, 45 dias). A data estimada, sem horário, conta pela
      sessão do anúncio ou pela de reação, na janela alargada em 7 dias de cada lado (`earnings_estimate_tolerance_days`).
    * O mercado do portão vem dos fatos do evento, senão de `official_market` da linha; `US` (as duas bolsas) vale como
      NASDAQ/NYSE; sem nenhum dos dois, o portão vale (falha fechada). **B3 só informativa**: a cobertura do calendário EODHD para a B3 não foi verificada (o
      snapshot conta eventos por bolsa em `counts.by_exchange` para a mesa julgar) e não há estimativa CVM equivalente.
  * **`CONSENSUS_EPS_CUT_30D`** (marca): ln(EPS de consenso FY1 no último `valuation_v2_data/<M>_V2_DATA` publicado até
    D − ε ÷ FY1 no último publicado até D − 30 d − ε) < −0,05 (`consensus_eps_cut_log`, `consensus_lookback_days` = 30),
    comparando o **mesmo** ano fiscal (o FY1 de 30 dias atrás procurado na estrutura atual), ou FY1 que virou não
    positivo. Substitui a comparação com "o snapshot da hora do TP": o TP é recortado toda noite, então aquela era uma
    revisão de ~24 h. Ano fiscal que rolou ou EPS passado não positivo → `not_comparable`, sem marca.
  * **`NEWS_SENTIMENT_NEGATIVE`** (marca, **nunca portão**): o sentimento semanal Finnhub (`ir_events`, `News Sentiment`)
    lido em D — a linha com `published_at` ≤ D − ε — com bearish ≥ 60 %, pelo menos 5 artigos na semana do provedor e no
    máximo 8 dias de idade; o valor fica gravado na linha da decisão. **A fonte sobrescreve a linha da semana a cada
    poll** (mantém a primeira publicação e troca os números): um replay depois de um poll da mesma semana lê outros
    números — só o valor gravado na nossa linha guarda o que foi lido, e por isso o sentimento fica **fora** do
    `replay_sha256`. Só EUA (B3 `not_applicable`).
* **Margem de inserção ε** (`insert_margin_seconds` = 60): toda leitura sobre um relógio de inserção — conclusão do poll,
  `created_at` da 053, publicação de um snapshot (calendário, consenso), `first_seen_at` da 051, publicação da linha de
  sentimento e do registro servido — para em D − ε: um commit que corre junto com a leitura da rodada fica fora da
  original **e** de todo replay. Registro servido publicado depois de D − ε não é decidido
  (`tp_published_after_run_instant` no recibo, agregado). As leituras anteriores do decisor (geração, ciclos,
  calibração, pacotes de taxa) continuam em ≤ D.

## Bloco de limiares (a congelar no PREREG)

Todos em `DecisorThresholds` (um único bloco, com hash `thresholds_sha256` gravado em cada registro). Padrões atuais:

| Limiar | Padrão |
|---|---|
| `max_tp_age_sessions` | 1 |
| `fundamentals_quarter_days` + `fundamentals_grace_days` | 92 + 45 |
| `max_price_move_percent` (o X) | 5,0 |
| `max_quote_age_minutes` (cotação de quem chama, só em dry run) | 15 |
| `max_method_dispersion_percent` | 45,0 (o mesmo dos produtores) |
| `min_valuation_confidence` | 70,0 (o mesmo dos produtores) |
| `min_profile_samples` / horizonte | 15 / 60–150 dias |
| `calibration_max_age_days` | 7 |
| `allow_global_error_fallback` | falso |
| fontes de taxa B3 / US | SGS 432 → ciclo B3 / T-bill 13s → 5Y |
| `undated_rate_sources_admitted` | vazio (a Selic do ciclo não conta) |
| `market_rate_max_age_days` | 10 |
| `tp_horizon_years` / `market_premium` | 1,0 / 0,0 |
| `insert_margin_seconds` (ε) | 60 |
| `staleness_poll_source` / `staleness_poll_max_age_hours` | `sec_asfiled` / 6 (início do poll ≥ D − 6 h) |
| `earnings_window_sessions` (N) / `earnings_gate_markets` | 2 / NASDAQ, NYSE (B3 só marca) |
| `earnings_calendar_max_age_hours` | 36 |
| `earnings_calendar_min_us_events` / `earnings_calendar_max_invalid_share` | 100 / 0,05 |
| `earnings_filings_lookback_days` | 400 |
| `earnings_estimate_seasonal_days` / `earnings_estimate_period_match_days` | 364 / 10 |
| `earnings_estimate_offset_days` / `earnings_estimate_default_10q_lag_days` | 91 / 45 |
| `earnings_estimate_tolerance_days` | 7 |
| `consensus_eps_cut_log` / `consensus_lookback_days` | 0,05 / 30 |
| `news_sentiment_bearish_min_percent` / `news_sentiment_min_articles` / `news_sentiment_max_age_days` | 60,0 / 5 / 8 |
| `event_gates` | `EARNINGS_WITHIN_N` (`NEWS_SENTIMENT_NEGATIVE` nunca) |

Congelamento: o commit que cita o PREREG grava `PREREG_THRESHOLDS_SHA256 = thresholds_sha256()`; a partir daí uma rodada
com qualquer outro bloco é recusada (`ValueError`) e os registros passam a dizer `prereg_frozen = true`. As regras de
evento e a vivacidade da 053 entraram no bloco **antes** do recibo de congelamento (previsto para 24–25/10): o hash do
bloco passou de `172bfda63759e07e2de5c41f55d867de2b996fd4374e8aa485635ae7c988c4ca` (só o 053) para
`bd7b8357a7dcdeb814906602482c520905f90f29df591c9cb4101278ce114a10` (eventos) e, com as correções das três revisões de
17/10, para **`98ee0a62c9951202e7e5d039dc1c15fc4a93e543a2aa97bbbcb94c2f46c822ed`** — fixado literalmente num teste
(`tests/test_valuation_decisor_events.py`) até o congelamento. `PREREG_THRESHOLDS_SHA256` continua `None` (nada congelado
ainda).

## Registros (`valuation_decisions`, migração 052)

Mesma disciplina de `valuation_predictions`: dois relógios (`prediction_instant` = relógio da rodada; `published_at` lido
imediatamente antes do insert, nunca antes — CHECK), sessão do veredicto pelo calendário da bolsa (nunca data civil),
identidade do TP lido (geração, fonte, ciclo, hash da linha, instante), `inputs` com a procedência de cada insumo
(calibração, taxa, preço, campos da linha, marcas 053 e poll em `tp_staleness`, fatos de evento em `events`) +
`inputs_sha256`, `checks` com os números de cada portão (`tp_staleness`: estado, fonte e protocolos; `events`: calendário
ou estimativa, consenso, sentimento, `gates` e `marks`; `counterfactual`), `row_sha256` canônico recomputado por todo
leitor (linha que não confere não é servida). Nenhuma coluna nova: marcas e contrafactual vivem em `checks` (052
inalterada). Append-only (UPDATE/DELETE/TRUNCATE recusados), idempotente por `(run_id, market, symbol)`,
`mode` só `shadow`: veredicto que age exige migração e ordem novas.
Causal: o TP vem da geração **em vigor no relógio da rodada** (`generation_at`, nunca uma posterior — um replay decide o
que aquela noite viu), linha servida com `prediction_instant` depois do relógio não é decidida
(`tp_after_run_instant` no recibo), nem registro publicado depois de D − ε (`tp_published_after_run_instant`), e as
marcas 053, o poll, os calendários, os filings 051, o consenso e o sentimento são os conhecidos no relógio (D − ε nos
relógios de inserção). `replay_sha256(registro)` é o hash do que o veredicto decidiu, sem a identidade da rodada (`id`,
`run_id`, `published_at`) e sem os hashes que a cobrem (`row_sha256`, `inputs_sha256`): rodar de novo a mesma noite no
mesmo relógio dá o mesmo hash, o que quer que tenha sido publicado ou marcado depois — **com uma exceção declarada**: o
sentimento Finnhub (`inputs.events.sentiment`, `checks.events.sentiment` e a marca `NEWS_SENTIMENT_NEGATIVE`) fica fora,
porque a fonte sobrescreve a semana e um replay não vê o valor lido em D; esse valor fica no registro.

## Fase noturna

`valuation_worker`, fase `decisor_shadow`, **desligada por padrão** (`C3PO_VALUATION_DECISOR_SHADOW=true` liga). Roda por
último entre as fases off-hours (depois do corte oficial e de toda fase existente; nunca atrasa uma delas). A noite está
feita quando a última rodada decidiu sobre a geração em vigor: uma geração ativada depois, dentro da janela (retry do
canônico), é decidida de novo. O recibo da rodada é agregado (contagens por mercado, veredicto e código, cotações
recusadas, estado da fonte 053 em `tp_staleness_source`, estado do calendário, contagem de marcas e
`verdicts_without_events`) — não nomeia símbolo nem protocolo. CLI:
`python -m app.valuation_decision --dry-run` (nada gravado), `--run` (recusado com a
flag desligada), `--verdict MERCADO:SÍMBOLO`. **Espera o calendário ficar legível** (revisão do Codex de 19/10): a fase só roda a partir do recebimento do
calendário mais novo + ε (`valuation_decision.not_before`) — um calendário recebido dentro da margem ficaria fora da
leitura da rodada logo depois da fase `earnings_calendar`. Antes disso a fase responde "ainda não" (`deferred`): nada
roda, nada é gravado, a noite não é marcada como feita e o worker acorda nesse instante.

`run_shadow` é **dry run por padrão**; grava só com `write=True` **e** a flag ligada (quem quer que chame — senão
`ValueError`). A flag é lida do ambiente do processo (`app/valuation_env.py`, não `Settings`: `config.py` entra no hash do
pacote do R2D2 V2); `run_shadow(enabled=…)` a fixa só para quem chama explicitamente (testes). Rodada com cotações de quem chama (`quotes`) é sempre dry run: nada intradiário substitui os veredictos
noturnos que o laboratório lê. Cotação sem `as_of` legível, com `as_of` depois do relógio da rodada ou mais velha que
`max_quote_age_minutes` é recusada (`quote_refused` na procedência) e a fonte noturna responde.

**Fase `earnings_calendar`** (`valuation_earnings_calendar.py`): **desligada por padrão**
(`C3PO_VALUATION_EARNINGS_CALENDAR_ENABLED=true` liga; ambiente, não `Settings`), roda antes de `decisor_shadow`. Faz UMA
chamada EODHD `/api/calendar/earnings` para a janela de mercado inteira [hoje − 7 d, hoje + 30 d] (sem lista de
símbolos), em **streaming** com teto de bytes (o `MAX_BODY_BYTES` do parser, 64 MiB) e prazo total de 180 s, valida com o
parser do R2D2 V2 (`r2d2_v2_earnings_source.parse_earnings_response`, importado, não modificado, fora do pacote de
fingerprint do R2D2 V2) e grava um snapshot append-only `valuation_earnings_calendar/EODHD_EARNINGS_CALENDAR` (tabela de
snapshots existente, sem migração nova) datado pelo `received_at`, com o SHA-256 do corpo, os eventos analisados
(código, data, período fiscal, BMO/AMC) e as contagens de linhas (`rows`, `invalid_rows`, `unattributed_invalid_rows`). O
corpo em si não é guardado. Resposta não 200, tipo não JSON, corpo inválido, acima do teto ou fora do prazo não grava
nada; nenhum erro carrega a URL (ela leva o token). A fase é **consultiva** (`VALUATION_WORKER_ADVISORY_PHASES`): falha
não dispara push `job_failure` nem marca falha no check do worker, e no painel de saúde aparece como **atenção**, nunca
offline (falhou, ainda não rodou no ciclo, ou ficou presa em `running` — morta no meio do download); tenta no máximo **3 vezes por noite** (`MAX_FAILURES_PER_NIGHT`) e espera
a noite seguinte. `last_run_at` lê só o relógio do último snapshot. A fase `decisor_shadow` mantém o comportamento de
antes (falha avisa).

**Como ligar** (deploy): as variáveis de repositório `C3PO_VALUATION_DECISOR_SHADOW` e
`C3PO_VALUATION_EARNINGS_CALENDAR_ENABLED` (valores exatamente `true` ou `false`) são escritas no `.env` do host pelo passo
"Stage host env settings (push notifications, valuation as-filed)" do `c3po-pipeline.yml` no **próximo deploy**; valor
fora de `^(true|false)$` derruba o deploy antes de qualquer escrita. **Apagar a variável não desliga**: valor vazio não
escreve nada e o `.env` do host mantém o que tinha — para desligar, defina `false` e faça deploy.

## Leitura pelo laboratório do R2D2

`latest_verdicts(database, mercado, símbolos, now=…)` / `latest_verdict(...)`: o laboratório **nomeia** os símbolos que
pergunta (`B3`, `NASDAQ`, `NYSE` ou `US`); nada enumera os nomes permitidos e não há rota HTTP. Cada resposta traz o
veredicto, os códigos, o TP lido e sua identidade, e `current` = `session_current` (decidido para a última sessão
completa em `now`) **e** `tp_served` (a geração em vigor em `now` ainda serve, para o símbolo, a mesma linha — mesmo
`tp_row_sha256` — que o veredicto leu: admissão dirigida de outro nome mantém; troca de fonte ou rollback não). Veredicto
que não é current sai com `effective_verdict = VETO` e `effective_reason_codes` com o motivo (`VERDICT_NOT_CURRENT`,
`VERDICT_TP_NOT_SERVED`): nenhuma permissão sobrevive à sua noite nem ao seu TP. A resposta traz também `marks` (as
marcas do registro), sem efeito no veredicto.

## Pendências declaradas

* Os limiares acima são propostas até o PREREG.
* `e_profile` só existe depois que os produtores gravarem a métrica nova na calibração (próximo ciclo após o deploy);
  até lá, todo nome fica sem permissão (`E_PROFILE_UNAVAILABLE`).
* **Decisão do PREREG sobre `e_profile`**: a métrica é o erro de RETORNO em ~90 dias (|realizado − esperado no período|),
  não um erro do TP em 12 meses, e é aplicada como desconto sobre um TP de 12 meses. O PREREG decide se aceita esse proxy,
  se o escala para o horizonte do TP ou se pede uma métrica de erro de TP (por exemplo, da frente de acurácia).
* **Taxa da B3**: com o bloco padrão, o `h_market` da B3 depende do pacote SGS 432 (`valuation_macro_history/B3_SELIC_REGIME`)
  com observação de até 10 dias — hoje esse pacote é atualizado pelo operador (`python -m app.valuation_v3_macro`), não
  por fase noturna. Sem ele, todo nome B3 fica `OBSERVAR` (`MARKET_RATE_UNAVAILABLE`). O PREREG escolhe: atualização
  noturna do pacote no servidor, o produtor B3 passar a gravar a data de observação da Selic, ou admitir a Selic sem data
  do ciclo (`undated_rate_sources_admitted`) sabendo do risco da constante.
* **Portões ainda inertes**: nenhum produtor emite hoje `tp_stale`, `data_defect` ou `data_defects` na linha servida —
  `TP_STALE_FLAG` e `DATA_DEFECT` passam todo nome em produção, e o PREREG não os conta como checagens até um produtor
  gravar a marca. A marca dos EUA veio em outra estrutura (053) e tem leitor causal: `TP_STALE_AFTER_FILING`, com a
  vivacidade do poll (`STALENESS_SOURCE_STALE`) — resolvido em 17/10: a 053 sem poll vivo falha fechada; a classe fica
  OBSERVAR (assimetria com `TP_STALE_FLAG` acima).
* **053 no host**: aplicada **automaticamente** na partida do container — `Database.initialize()` executa toda migração
  numerada de `db/` sob trava consultiva (`IF NOT EXISTS`, idempotente); nenhuma ação manual. `STALENESS_SOURCE_UNAVAILABLE`
  só aparece se a inicialização falhar ou numa janela de deploy.
* **Replay de uma noite anterior à 053 com poll vivo** (resíduo declarado): com o poll vivo e a 053 ainda não aplicada,
  a noite registrou `STALENESS_SOURCE_UNAVAILABLE`; depois que a 053 chega, um replay da mesma noite lê a tabela (vazia
  até D) e registra `clear` — o veredicto e o `replay_sha256` diferem. Só D não diz quando a migração foi aplicada (a
  053 não guarda a própria data de criação), então o leitor não distingue "ausente em D" de "ausente agora". Sem poll
  vivo, as duas leituras coincidem (o poll é julgado primeiro). A 053 é aplicada na partida do container, então a
  janela é a do primeiro deploy com ela.
* **Vivacidade ≠ gatilho**: o poll `sec_asfiled` bem-sucedido prova que os protocolos estão sendo registrados, não que o
  gatilho (`evaluate_us_filings`, no processador de IR e no corte) rodou — uma falha do gatilho é só log, sem execução
  gravada. Se a mesa quiser a prova exata, o gatilho passa a gravar a própria execução e o bloco aponta para ela.
* **Eventos — decisões em aberto para o PREREG/mesa**: (a) o piso de 100 eventos US do calendário (justificado acima,
  a confirmar com os primeiros snapshots reais); (b) a tolerância de 7 dias da estimativa (o produtor de earnings do R2D2
  usa 15; com 0 a estimativa vira ponto); (c) cobertura do calendário na B3 antes de virar portão lá; (d) os limiares de
  sentimento (60 % / 5 artigos / 8 dias) e de consenso (−0,05 em log em 30 dias) são propostas; (e) a regra 10-K
  (período + 91 + defasagem do 10-Q) erra para depois quando o emissor anuncia antes do 10-Q — a regra sazonal, com um
  ano de 051, cobre esse caso.
* **Leitores PostgreSQL**: `tests/test_valuation_decisor_postgres.py` executa as consultas novas (extração JSONB do
  consenso, sentimento, poll, 051, 053 com a margem) num PostgreSQL local descartável
  (`C3PO_VALUATION_DECISOR_TEST_DSN` ou `C3PO_PROVIDER_HEALTH_TEST_DSN`, soquete em `/tmp`); sem DSN, é pulado — a
  integração de 17/10 não tinha um PostgreSQL local para rodá-lo.
* **Resíduos do leitor 053** (declarados): (1) uma passagem do gatilho cuja transação começa antes do relógio da rodada
  e confirma depois da leitura (milissegundos; o gatilho noturno roda antes da fase do decisor, só o poll de IR pode
  coincidir) é vista por um replay e não pela rodada original — o `inputs_sha256` diverge e mostra; (2) um `cleared` é
  terminal no gatilho: um rollback da geração para um TP anterior ao protocolo, depois do `cleared`, não volta a
  marcar o nome (rollback é ato explícito da mesa); (3) marca `stale` pendente de um TP já reavaliado por um corte
  cujo gatilho falhou mantém o nome em OBSERVAR até o próximo passe — erro do lado seguro.
* Preço depois do corte: hoje vem de ciclo de universo publicado depois do fechamento; a série de preços da V3.2
  (`valuation_price_bars`, migração 049, fase desligada por padrão) é a próxima fonte natural de fechamento por sessão.
