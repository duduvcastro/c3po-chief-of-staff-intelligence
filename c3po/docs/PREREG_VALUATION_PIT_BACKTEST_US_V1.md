# Pré-registro — Backtest ponto-no-tempo US do TP interno V3.2 (`PREREG_VALUATION_PIT_BACKTEST_US_V1`, rev 1)

**Estado:** rascunho rev 1 para hash, 17/10/2026. Torna-se vinculante quando o `sha256` dos **bytes deste arquivo**, no commit que o introduz, for publicado num recibo no canal técnico — recibo que **cita esse commit** — **antes da primeira corrida da grade** (§3) e, portanto, antes de qualquer leitura de rótulo (só o relatório lê rótulos). Depois do hash, nada aqui muda: qualquer alteração é uma **nova revisão**, com novo hash, permitida apenas enquanto nenhum relatório tiver sido executado sobre uma grade completa (§7.4).

**Contexto:** cronograma comprimido do dono — veredito PASS/FAIL do backtest US na **sexta 23/10/2026**. O decisor de compra lê o TP do Valuation (`VALUATION_DECISOR_V1.md`); o `PREREG_VALUATION_DECISOR_V1` mede a acurácia **servida ao vivo** a partir de `H0` e não dá resposta decisória antes de 2027. Este documento mede outra coisa: o mesmo motor **reexecutado no passado**, ponto no tempo, sobre demonstrações como arquivadas na SEC. Não substitui nem antecipa o holdout do decisor; não muda número servido; não troca a fonte oficial.

**Instrumento:** `c3po/backend/app/valuation_pit_backtest_report.py` (recibo `VALUATION-PIT-BACKTEST-REPORT-v1`; testes `tests/test_valuation_pit_backtest_report.py`), sobre o manifesto da grade escrito por `c3po/backend/app/valuation_pit_grid.py` (`VALUATION-PIT-GRID-MANIFEST-v1`; testes `tests/test_valuation_pit_grid.py`), executados no host pelo workflow `.github/workflows/valuation-pit-backtest.yml` (testes `tests/test_valuation_pit_backtest_workflow.py`). O relatório **reutiliza por import** o relatório de acurácia (`valuation_accuracy_report`: `horizon_report`, `point`, atrito executável, blocos do §5, t de Student, vínculo de código), o painel §7.3 (`valuation_panel`: admissibilidade, observação, verificação de base, rótulo), a série de preços (`valuation_price_history.label_bar`) e as duas regras do painel PIT (`valuation_pit_panel`: corrida superada, horizonte `N/D`). O código que produz os números está vinculado a este documento (§15).

## 1. Pergunta e objeto

1. **Pergunta:** o upside `u = tp / price − 1` do **TP interno V3.2** (motor V3 rev 7, **sem consenso dentro**), reexecutado ponto-no-tempo por `valuation_pit_rerun` a partir das demonstrações **como arquivadas** na SEC (`--statements vintages`, migração 051), **ordena os retornos executáveis seguintes** no corte transversal dos EUA?
2. **Objeto medido:** os registros `valuation_predictions` da fonte `v3_2_shadow` das corridas `valuation_pit_rerun` listadas no manifesto da grade (§3), e só delas. `tp = v3_internal_tp × fator de calibração` (nesta árvore sempre `absent_at_T` → 1,0).
3. **Produtor:** o motor e o reexecutor do **commit citado no recibo de hash** — os cinco ficheiros cujo `sha256` cada corrida grava no seu manifesto (`engine.implementation_file_sha256`: `valuation_v3_engine.py`, `valuation_v3_inputs.py`, `valuation_v3_macro.py`, `valuation_v3_shadow.py`, `valuation_pit_rerun.py`). A grade inteira tem **um só produtor** (o relatório anula uma grade com dois) e o workflow confere esses hashes contra os ficheiros do commit do recibo (§10). Uma correção do produtor **antes** da grade exige nova revisão deste documento (novo hash) antes de a grade começar; **depois** de iniciada, a grade inteira é refeita sob uma nova revisão.

## 2. Mercado, universo e dados

- **Mercado:** `US` = NASDAQ ∪ NYSE, calendário XNYS, USD — **um corte transversal por sessão XNYS**: a união das duas corridas (uma por bolsa) do mesmo `T`. O reexecutor carrega uma bolsa por corrida e **não** carrega a irmã como pares (desvio declarado em `VALUATION_PIT_RERUN.md`); o relatório une as duas. Um símbolo presente nas duas bolsas na mesma sessão conta uma vez (`duplicate_across_exchanges`, contado).
- **Universo:** o **catálogo corrente** de cada bolsa (`valuation_universe/<M>_UNIVERSE`), o mesmo em todo `T` — **viés de sobrevivência declarado** (§11).
- **Demonstrações:** `--statements vintages`: um nome coberto pela tabela `statement_vintages` é reconstruído **só** dos fatos SEC aceitos até `T` (`accepted_at ≤ T`, instante, sem granularidade de dia); os `Financials` do provedor nunca são lidos para ele; um nome **não coberto** é não avaliável (`statement_vintages_missing`) e contado. O lookback da frente SEC sobe para 10 anos (PR #450, ≈ outubro/2016 na ingestão) antes do backfill: sem isso os exercícios iniciais não existem em `T` de 2021.
- **Preços:** **uma** publicação de `valuation_price_history` por bolsa — o **backfill único de 120 meses** (§14 b) —, pinada para a grade inteira por um único `--price-pinned-at` (o instante logo depois das duas publicações do backfill); nível = `close` negociado, retornos = `adjusted_close` (P2-2 de `VALUATION_PIT_RERUN.md`). Os **rótulos** são lidos da **mesma** publicação de cada bolsa (corte = `available_at + 1 µs`, o único que a resolve).
- **Macro EUA:** o snapshot PIT `US_EODHD_TREASURY_HISTORY` (`--fetch`).

### 2-bis. Por que 120 meses de preços (achado de 17/10/2026)

Os rácios por exercício (`ratios_annual`, `key_metrics_annual`) que alimentam os modelos de **história própria** do motor (P/L e P/VPA, chave `own_history`; e o recurso à história própria quando faltam pares) pedem o `close` negociado do último pregão ≤ fim do exercício **da safra pinada**. Com a safra noturna de **36 meses**, qualquer `T` tem no máximo dois ou três exercícios com preço; os modelos exigem `MIN_HISTORY_YEARS = 5` (`valuation_v2_engine.py`): numa reexecução PIT eles ficavam **sempre ausentes**, enquanto ao vivo (histórico longo do provedor) estão ativos — o backtest mediria outro motor. **Correção:** a máquina existente já admite safras longas (`valuation_price_history --backfill --months N`, teto 120): um backfill único de 120 meses, pinado, dá cinco preços de fim de exercício a partir de `GRID_START` (§3), sem fonte nova e sem mudança de código no reexecutor. **Leitura descritiva (nunca decisória):** o recibo publica a parcela dos nomes avaliados, por sessão, cujo motor rodou o modelo `own_history` (`coverage.US.history_model_share_per_session`).

## 3. Grade de instantes `T`

- **Sessões `D`:** de **`GRID_START = 2021-06-01`** (a primeira sessão XNYS em/após essa data; ela tem também ≥ `MIN_PRIOR_SESSIONS = 252` sessões da safra antes de si — nunca vinculante numa safra de 120 meses) até a **última sessão cujo rótulo de saída `T + 1 + 21` fechou antes da publicação pinada** (nas duas bolsas: a interseção), **a cada 5 sessões** (`STEP_SESSIONS = 5`) a partir da primeira.
- **Por que 2021-06-01:** um emissor de ano civil tem, em junho/2021, os exercícios FY2016–FY2020 arquivados (o 10-K de FY2020 aceito até ~março/2021) e com preço de fim de exercício na safra de 120 meses (que começa em ~outubro/2016): **cinco exercícios**, o mínimo dos modelos de história própria. Um `T` anterior correria sem esses modelos (outro motor).
- **Relógio:** `T` = **01:00 America/Sao_Paulo** do dia civil seguinte a `D` (espelha o ciclo noturno que roda depois do fecho); `session_date = D` (conferido por `session_date_of`). Em Nova Iorque esse instante é 00:00 (EDT) do dia seguinte ou 23:00 (EST) de `D`: a data económica do motor (o `today` e os cortes de período) é `D + 1` no horário de verão e `D` no inverno; os fatos SEC são cortados pelo **instante** (`accepted_at ≤ T`).
- **Tamanho esperado:** com o backfill publicado em 18–19/10/2026, **266 instantes** de 2021-06-01 a 2026-09-10 (≈ 1.330 sessões de calendário, **64 blocos de 21**), **532 corridas** (duas por `T`). O `--dry-run` imprime a grade exata para o pino escolhido.
- **Grade pré-registrada ou nada:** o relatório recomputa a grade a partir das publicações pinadas (lidas do armazém, nunca do manifesto) e anula (`VOID`) um manifesto cujo início não é `GRID_START` (`manifest_grid_start_not_prereg`), cujas safras pinadas não deixam a grade começar em `GRID_START` (`grid_start_not_prereg`, p. ex. uma republicação noturna de 36 meses), ou cujas sessões não são exatamente as da grade (sessões em falta ou a mais, sessão sem as duas bolsas, relógio de `T` diferente). O executor (`valuation_pit_grid`) recusa as mesmas condições antes de correr; `--from/--to` só selecionam uma sub-faixa **da** grade (ancorada na primeira sessão), para trabalhar em lotes.
- **Uma safra só:** todo recibo por `T` deve relatar a mesma `price_vintage` (a publicação pinada) — senão o executor para (`GridError`).

## 4. Definições (as do `PREREG_VALUATION_DECISOR_V1` §3)

```text
a(T)        = adjusted_close(T) / close(T)                       # mesma publicação pinada
u(i,T)      = tp / price − 1                                     # upside do registro (tp e price do registro)
rx(i,T,h)   = adjusted_close(T + 1 + h) / adjusted_close(T + 1) − 1   # retorno EXECUTÁVEL (decisório): entra no fecho de T + 1
r(i,T,h)    = adjusted_close(T + h) / adjusted_close(T) − 1      # retorno total T → T+h (descritivo)
P̂(i,T,h)   = price · (tp / price)^(h / 252)
e_fonte     = ln( P̂ · a(T) ) − ln( adjusted_close(T + h) );  e_PA = ln( price · a(T) ) − ln( adjusted_close(T + h) )
```

`T ± k` são sessões XNYS a partir de `D`. Verificação de base do painel: moeda da barra = moeda do registro, `|price − close(D)| / close(D) ≤ 0,02`; sem barra em `D` → `adjustment_unknown` (atrito). Horizontes: `h = 21` (**decisório**), 63 e 126 (descritivos). Pesos iguais por nome; retornos brutos, sem custos.

## 5. Métricas (por horizonte, na união das duas bolsas)

| # | Métrica (campo do recibo) | Estatística por sessão | Mínimo por sessão | Papel |
|---|---|---|---|---|
| M1x | IC executável (`ic_executable`) | Spearman (postos médios) entre `u` e `rx(h)` | `MIN_NAMES_PER_SESSION = 10` | **decisória** em `h = 21` |
| M2x | Spread de decis executável (`decile_spread_executable`) | média de `rx(h)` do decil superior de `u` − inferior | `MIN_NAMES_DECILES = 30` | condição do PASS (estimativa > 0) |
| M1 | IC de postos (`ic`) | Spearman entre `u` e `r(h)` | 10 | descritiva |
| M2 | Spread de decis (`decile_spread`) | idem sobre `r(h)` | 30 | descritiva |
| M3 | log-MSE vs passeio aleatório (`log_mse_vs_random_walk`) | razão agrupada e diferença por sessão | 1 | descritiva |
| M4 | log-MSE vs consenso | — | — | vazia por construção: o consenso PIT tem horizonte `N/D` → `consensus_unattested:horizon` |
| M5 | lista de compra (proxy `status = full_match`) | — | — | vazia por construção: os registros PIT têm `status = retrospective` |

As sessões sem estatística são contadas por causa (`below_min_names`, `degenerate`, …), nunca preenchidas. Metades (§6.4): também para M1, descritivas.

## 6. Erros-padrão em blocos (o §5 do `PREREG_VALUATION_DECISOR_V1`, sobre a grade)

1. **Índice:** sessões do **calendário** XNYS a partir da primeira sessão da grade (`k = 0` em `GRID_START`); bloco `b` = índices `[21·b, 21·(b+1))` — comprimento `h` **sessões de calendário**, exatamente como no §5 do decisor. Com passo 5, um bloco contém 4 ou 5 instantes da grade (padrão 5, 4, 4, 4, 4 a cada 105 sessões).
2. **Bloco completo:** todas as suas sessões que pertencem à grade (até o índice do último `T`, `partition_last_index`) têm o alvo `T + 1 + h` (`T + h` para as estatísticas de `r`) fechado antes do corte dos rótulos (o mais cedo das duas publicações pinadas). Na grade pré-registrada de `h = 21` todos os blocos são completos (§3: o último `T` é escolhido assim). Bloco sem estatística: `blocks_empty`, não conta. `B` = blocos completos com estatística.
3. **Teste:** estimativa = média das médias de bloco; `se = √1,5 · dp(médias de bloco) / √B`; `t = estimativa / se`, **t de Student com `B − 1` graus de liberdade**; `p_greater = P(T ≥ t)`, `p_less = P(T ≤ t)`. **O fator 1,5 com passo 5:** sob o modelo triangular do §5 (autocorrelação `1 − k/21` da estatística diária), amostrando a cada 5 sessões, a correlação entre médias de blocos adjacentes fica entre 0,20 e 0,25 (média 0,24): `1 + 2ρ₁ ≈ 1,48 ≤ 1,5` — o fator do §5 fica, ligeiramente conservador; blocos a duas ou mais distâncias não se sobrepõem. Newey–West é publicado ao lado, descritivo.
4. **Metades:** as primeiras `⌊B/2⌋` e as últimas `⌊B/2⌋` médias de bloco completas, em ordem (com `B` ímpar o bloco do meio fica fora); a estimativa de cada metade = média das suas médias de bloco (o recibo publica também `se`, `t` e `p` de cada metade, descritivos). As médias de bloco das metades são recomputadas pela mesma regra do relatório de acurácia, e o relatório falha se divergirem.

## 7. Regra de decisão — leitura única, `h = 21`, IC executável

1. **`VOID`** — a leitura não vale sob este documento (§9): código não vinculado, manifesto fora dos parâmetros, safra dos rótulos não é a pinada, grade não é a pré-registrada, corrida ausente/superada/divergente/incompleta, dois produtores. Não é veredito.
2. **`UNMEASURED`** — nenhuma observação elegível do par executável, ou o atrito executável em `h = 21` acima de `ATTRITION_CAP = 0,10`.
3. **`NEGATIVE`** — `p_less ≤ ALPHA_NEGATIVE = 0,05` no IC executável (basta haver teste, `B ≥ 2`).
4. **`PASS`** sse, **todas**: `B ≥ MIN_BLOCKS = 12` blocos completos; estimativa do IC executável **≥ `IC_MIN = 0,02`**; `p_greater ≤ ALPHA = 0,05`; estimativa do spread de decis executável (M2x) **> 0**; estimativa do IC executável **> 0 nas duas metades** (§6.4); atrito executável **≤ 0,10**.
5. **`FAIL`** — qualquer outro caso (**não demonstrado**; não prova ausência de sinal), com as condições não cumpridas listadas.

- **Leitura única:** a primeira execução do relatório sobre o manifesto **completo** (`complete: true`), com código vinculado (`BOUND`) e a grade pré-registrada, **é** o veredito. Repetir o relatório sobre o mesmo manifesto e o mesmo armazém reproduz o mesmo payload (a única diferença possível é `code.build_sha`, se o deploy mudou): não é outra olhada. Outro manifesto (outra grade, outra safra) é outra olhada e exige nova revisão. Nenhum relatório roda sobre uma grade incompleta.
- **Fora do veredito, sempre:** M1, M2, M3 (o retorno `T → T+h` e o nível), os horizontes 63 e 126, as metades de M1, a cobertura (§9), o Newey–West.
- **Um `PASS` não liga nada:** não muda número servido, não troca a fonte oficial, não é o holdout do decisor nem o PROMO-2; é uma recomendação à mesa.

## 8. Poder (modelo do §9-bis do decisor, passo 5)

Modelo: IC executável diário `= IC + dp · N_t` (`N_t` a soma móvel normalizada de 21 normais: autocorrelação `1 − k/21`), **amostrado a cada 5 sessões**, blocos de 21 sessões de calendário, a regra do §7 sobre `B` blocos (estimativa ≥ 0,02, `t ≥` crítico de 0,05, as duas metades > 0; `NEGATIVE` se `t ≤ −` crítico). Atrito e a condição M2x não modelados: as probabilidades de PASS são **limites superiores**. Reprodutível: `design_table()` do módulo, `DESIGN_SEED = 20261023`, `DESIGN_REPS = 20000` caminhos (números aleatórios comuns entre células).

Probabilidade de **PASS** (%) — `B = 60` (a grade real tem ≈ 64 blocos):

| `dp` \ IC | −0,03 | 0 | +0,02 | +0,03 | +0,04 | +0,05 | +0,06 | +0,08 |
|---|---|---|---|---|---|---|---|---|
| 0,06 | 0,0 | 0,6 | 50,1 | 90,4 | 99,5 | 100,0 | 100,0 | 100,0 |
| 0,08 | 0,0 | 2,4 | 49,3 | 82,8 | 97,2 | 99,7 | 100,0 | 100,0 |
| 0,10 | 0,0 | 4,5 | 43,1 | 72,2 | 91,2 | 98,1 | 99,7 | 100,0 |
| 0,12 | 0,0 | 4,7 | 34,3 | 58,6 | 80,3 | 93,2 | 98,2 | 99,9 |

`NEGATIVE` sob IC 0: 4,6 % (B = 60); sob IC −0,03: 98,5 / 88,5 / 73,6 / 59,9 % (`dp` 0,06 / 0,08 / 0,10 / 0,12). Com menos blocos (se a grade sair mais curta): `B = 24`, `dp` 0,10 → PASS 24,0 / 40,4 / 59,3 / 75,8 % em IC 0,02 / 0,03 / 0,04 / 0,05; `B = 12`, `dp` 0,10 → 16,2 / 25,5 / 37,1 / 49,8 %.

**Leitura honesta:** com ≈ 64 blocos o teste detecta com 80 % ICs a partir de ≈ 0,025 (`dp` 0,06), ≈ 0,03 (`dp` 0,08), ≈ 0,035 (`dp` 0,10) e ≈ 0,04 (`dp` 0,12). `IC_MIN = 0,02` é um **piso económico sobre a estimativa**: um IC verdadeiro de 0,02 passa só metade das vezes. Só a amostragem, com ~600 nomes por sessão, dá `dp ≈ 1/√599 ≈ 0,04`; a variação do sinal soma a isso — a linha provável fica entre 0,06 e 0,10. O tamanho sob IC 0 fica ≤ 5 % (o piso e as metades só o reduzem).

## 9. Atrito, cobertura e integridade

- **Atrito executável** (`attrition_executable`, decisório): denominador = observações cujo alvo `T + 1 + h` fechou antes do corte dos rótulos; indisponível = falta qualquer rótulo do par (causa da saída; senão `entry:<causa>`). Causas do painel (`missing_bar`, `adjustment_unknown`, `outside_window`, `symbol_not_in_vintage`, …). Teto 0,10.
- **Cobertura (descritiva, nunca decisória)** — `coverage` por bolsa e para `US`, somando os resumos das corridas: nomes do catálogo lidos, avaliados, com TP interno, registrados, **não avaliáveis por razão** (`statement_vintages_missing` = não cobertos, `statement_vintages_none_accepted_by_T`, `fewer_than_90_valid_sessions_at_T`, `capital_event_between_shares_and_T`, …), base das demonstrações, cobertura da tabela (`covered`, `covered_in_catalogue`, `covered_without_rows_by_T`), e a parcela dos avaliados com o modelo `own_history` ativo (total e distribuição por sessão, §2-bis). Os nomes não avaliáveis **não** entram no atrito: são uma seleção, declarada (§11).
- **Integridade (`VOID`, com as razões):** `code_mismatch`/`code_unbound` (§15); `manifest_market_not_US`, `manifest_markets_not_NASDAQ_NYSE`, `manifest_statements_not_vintages`, `manifest_step_not_5`, `manifest_grid_start_not_prereg`; `label_vintage_not_the_pinned_one:<bolsa>`; `no_prereg_grid`, `grid_start_not_prereg`, `grid_sessions_missing`, `grid_sessions_not_prereg`, `grid_sessions_without_both_exchanges`, `grid_t_clock_mismatch`; `runs_missing`, `runs_superseded`, `runs_mismatched` (ciclo, pino, modo das demonstrações ou sessão diferentes do manifesto), `runs_incomplete` (os registros lidos não são exatamente as identidades da corrida), `producer_not_uniform`, `no_current_run`. Um registro `v3_2_shadow` de um `T` da grade cuja corrida não está no manifesto é **recusado** (`run_not_in_manifest`), não anula.

## 10. Validade de uma leitura (o workflow, modo `report`)

O workflow **recusa publicar** (falha antes do upload) um recibo que viole qualquer item: (1) `payload_sha256` recalculado; (2) `payload.prereg_sha256` = `sha256` deste arquivo na revisão do workflow **e** este arquivo idêntico, byte a byte, ao do commit citado no recibo de hash (`prereg_commit`); (3) `payload.code` igual, pin a pin, ao §15, e `code_binding.status = BOUND`; (4) `code.build_sha` é um commit; (5) `payload.manifest.manifest_sha256` = o hash do manifesto publicado no canal (`manifest_sha256`, que o workflow também recalcula do artefato da corrida da grade); (6) **o produtor da grade** (`payload.runs.producer.engine_files`) = os `sha256` dos cinco ficheiros do produtor **no commit citado** (`git show`). Um recibo `VOID` que passe nesses itens é publicado (o instrumento fica visível), sem veredito.

## 11. Limitações declaradas

Herdadas de `VALUATION_PIT_RERUN.md` (§Limitações) e próprias deste backtest:

1. **Olhar à frente de desenho, não de dados:** os parâmetros do motor (rev 7: modelos, pesos, limites, `TP_BOUND_VS_PRICE`, regras de buy-in) foram fixados em 2026, com conhecimento do período 2021–2026; o dado é ponto-no-tempo, o desenho não. Um PASS mede "o motor de 2026 aplicado ao passado", não "um motor que se teria construído então".
2. **Sobrevivência — maior que num backtest de 2 anos:** o universo é o catálogo **corrente**; numa janela de cinco anos ficam de fora os nomes deslistados, falidos, adquiridos ou rebaixados desde 2021, e entram só os que sobreviveram até hoje. O viés é **maior** que numa janela de dois anos e pode deslocar o nível dos retornos e o IC em qualquer direção (o IC mede a ordenação **entre sobreviventes**). Um nome que deixou de negociar dentro da janela vira `missing_bar` → atrito (teto 0,10).
3. **Modelos de história própria com menos anos no início:** nos EUA o modelo `own_history` usa a mediana winsorizada de **todos** os exercícios disponíveis (≥ 5) e pondera a confiabilidade por `anos/10`; num `T` inicial ele vê 5–6 exercícios (a safra de 120 meses e o lookback SEC de 10 anos começam em ~2016) contra até 10 ao vivo (o FMP entrega até 10): mediana de menos anos e confiabilidade menor. (Na B3 o V3.1 escolhe os 5 exercícios mais próximos em regime de Selic entre os disponíveis — num `T` inicial escolheria entre menos anos que ao vivo; a B3 está fora deste backtest.)
4. **Parâmetros de buy-in neutros** (`risk_score = valuation_confidence = 50`): não afetam o TP nem o upside medido.
5. **Beta contra o proxy equiponderado do universo da corrida** (inclui o próprio símbolo), não um índice; **pares só da própria bolsa** (NASDAQ e NYSE separados), desvio do motor ao vivo.
6. **Sem histórico:** estimativas de analistas, qualidade forward, `peer_quality`, notícias, insiders, grades — ausentes e contados; calibração `absent_at_T` (fator 1,0).
7. **Consenso:** horizonte `N/D`, nunca no motor, nunca comparado (M4 vazio); o payload atual da FMP sem `currency` deixa-o ausente.
8. **Demonstrações:** só nomes cobertos pela 051 (os outros: não avaliáveis, uma seleção); sem dividendos na escada da SEC (sem dividend yield); ações da capa do documento; ligação símbolo → emissor corrente; a cobertura da tabela pode crescer durante a grade (backfill da frente as-filed): um `T` reutilizado foi calculado com a tabela do momento em que correu (§14 d).
9. **Preços:** `close` negociado só corroborado pela evidência agregada de eventos de capital; a safra de 120 meses é uma captura de outubro/2026 (ajustes do provedor de hoje), a "safra original" de cada data é `N/D`.
10. **Relógio de `T`:** 01:00 BRT de `D + 1` = 00:00 EDT de `D + 1` (verão) ou 23:00 EST de `D` (inverno): a data económica do motor oscila um dia ao longo do ano; os fatos SEC usam o instante.
11. **Modelos estatísticos:** a sobreposição (`ρ₁ = 1/4`, fator 1,5) e o poder (normal, IC estacionário) são modelos; sinais persistentes e fatores de mercado podem ter memória mais longa — o Newey–West ao lado mostra a discrepância, sem trocar a regra.
12. **Custos:** retornos brutos, sem bid/ask nem dimensionamento: um PASS não é valor económico líquido (o custo no bid/ask é outra medição, com outro pré-registro).

## 12. Recibo (`VALUATION-PIT-BACKTEST-REPORT-v1`)

```text
{ "schema", "payload": { "schema", "protocol": {constantes do §13, "gate": false}, "prereg_sha256",
                         "code": {files, objects, exchange_calendars, python, build_sha}, "code_binding": {status, pinned, reasons},
                         "manifest": {manifest_sha256, schema, market, markets, statements, step_sessions, grid_start, price_pin, entries, complete},
                         "label_vintages": {NASDAQ, NYSE: cabeçalho da publicação}, "label_cut", "records_cut",
                         "bounds": {grid_start, first_eligible, last_eligible, starts_at_grid_start, per_market},
                         "grid": {status, expected_sessions, manifest_sessions, missing, extra, without_both_exchanges, t_clock_mismatches, first_session, last_session},
                         "runs": {entries, status: {current, superseded, missing, mismatched}, mismatch_reasons, incomplete,
                                  producer: {uniform, source_versions, engine_files, engine_identities}},
                         "coverage": {NASDAQ, NYSE, US: {runs, catalogue_names, evaluated, with_internal_tp, records, history_model_active, history_model_share,
                                                         not_evaluable, statements_basis, statements_coverage, …}},
                         "records": {read, refused, observations, cohort}, "anchor", "partition_last_index", "names_per_session",
                         "horizons": {"21"|"63"|"126": horizon_report do relatório de acurácia},
                         "halves": {ic_executable, ic: {blocks, per_half, first, second}},
                         "verdict": {status, statistic, horizon_sessions, look: SINGLE, reasons, blocks, ic_estimate, ic_se, ic_t, ic_df, ic_p_greater, ic_p_less,
                                     decile_spread_executable_estimate, halves, attrition_executable, gate: false} },
  "payload_sha256": sha256 canónico do payload, "provenance": {generated_at} }
```

**Nenhum símbolo** no recibo nem no manifesto; só agregados. O payload é função de (manifesto, armazém, código): o corte dos registros é o último `published_at` das corridas do manifesto + 1 µs; o dos rótulos, o da publicação pinada. O processo força sessão PostgreSQL somente-leitura (`PGOPTIONS=-c default_transaction_read_only=on`) e só alcança cinco leitores do armazém.

**Manifesto da grade (`VALUATION-PIT-GRID-MANIFEST-v1`):** `{schema, market: US, markets: [NASDAQ, NYSE], price_pin: {requested_at, NASDAQ: {publication_id, available_at, bars_sha256, from, to, …}, NYSE: {…}}, statements, step_sessions, grid_start, t_clock, bounds, range, prereg_grid_sessions, grid: [{as_of, session_date, market, run_key, cycle_id, idempotent, reused, supersedes, evaluated, records, not_evaluable, history_model_active}], complete, remaining, stopped, producer: {source_version, engine_files}, owner_order_sha256, manifest_sha256}` — `manifest_sha256` = `sha256` do JSON canónico sem esse campo; escrito com `O_EXCL | O_NOFOLLOW`, modo 0600.

## 13. Constantes (espelho exato do código; todas dentro do payload hasheado)

`SCHEMA_VERSION = VALUATION-PIT-BACKTEST-REPORT-v1`; `MANIFEST_SCHEMA = VALUATION-PIT-GRID-MANIFEST-v1`; `PREREG = PREREG_VALUATION_PIT_BACKTEST_US_V1`; `PREREG_REVISION = 1`; `SOURCE = v3_2_shadow`; `MARKET_GROUP = US`; `MARKETS = (NASDAQ, NYSE)`; calendário `XNYS`; `STATEMENTS = vintages` (`--statements vintages`); `STEP_SESSIONS = 5`; `GRID_START = 2021-06-01`; `MIN_PRIOR_SESSIONS = 252`; `T` = `01:00 America/Sao_Paulo` do dia civil seguinte a `D`; `HORIZONS = (21, 63, 126)`; `PRIMARY_HORIZON` h = 21; `EXECUTION_LAG_SESSIONS = 1`; `DECISORY_STATISTIC = ic_executable`; `TP_HORIZON_SESSIONS = 252`; `MIN_NAMES_PER_SESSION = 10`; `MIN_NAMES_DECILES = 30`; `DECILES = 10`; bloco = `h` sessões de calendário, só completos; `ADJACENT_BLOCK_VARIANCE_FACTOR = 1,5`; `MIN_BLOCKS = 12`; `IC_MIN = 0,02`; `ALPHA = 0,05` (unilateral, `p_greater`); `ALPHA_NEGATIVE = 0,05` (`p_less`); `ATTRITION_CAP = 0,10`; `TOL_BASIS = 0,02` e `LABEL_CONVENTION = total_return:adjusted_close` (do painel); `HISTORY_MODEL = own_history` (leitura); ordem do veredito `VOID → UNMEASURED → NEGATIVE → PASS → FAIL`; leitura única. Desenho (fora do veredito): `DESIGN_SEED = 20261023`, `DESIGN_REPS = 20000`, `DESIGN_SDS = (0,06; 0,08; 0,10; 0,12)`, `DESIGN_BLOCKS = (12, 24, 60)`.

## 14. Operação no host (ordem, o que cada passo escreve, contagens, regra de parada)

Tudo pelo workflow `valuation-pit-backtest.yml` (dispatch, frase `RUN VALUATION PIT BACKTEST`). Os modos que **escrevem** (`price-backfill`, `fetch`, `grid`) exigem `owner_order_sha256` (64 hex, impresso no log e gravado no manifesto); nenhum modo de escrita (nem o `report`) começa dentro da sessão dos EUA (09:00–16:30 America/New_York em dias úteis) nem da fase noturna (00:45–08:15 America/Sao_Paulo); `price-backfill` e `fetch` exigem ≥ 120 min livres antes da próxima janela; cada lote da grade recebe `--stop-before` = início da próxima janela − 20 min (no máximo 300 min). **Conferir também a agenda do R2D2** (temporizadores do host fora dessas janelas): o workflow não a conhece.

a. **`host-check` (somente leitura):** espaço livre (`df -P / /var/lib/docker`), a publicação de preços que um corte agora vê por bolsa (id, `available_at`, janela, símbolos, barras) e a cobertura da tabela as-filed. **Parar** se houver menos de **6 GB** livres no sistema de ficheiros do PostgreSQL.
b. **`price-backfill` (escreve; ordem do dono):** `valuation_price_history --market NASDAQ --backfill --months 120`, depois NYSE, na mesma janela da noite e **antes** da fase noturna seguinte. Escreve uma captura + uma publicação por bolsa e as barras cujo conteúdo mudou (deduplicadas por conteúdo). Volumes estimados: ~2.500 sessões × ~1.200 símbolos ≈ 3,0 M barras na janela, das quais ~0,9 M (36 meses) já gravadas e sem mudança; **~2,1 M linhas novas** (+ as sessões recentes cujo `adjusted_close` o provedor reajustou), ~0,4 kB por linha com índices → **~1 GB**; uma chamada EODHD por símbolo (~1.200). O recibo (reduzido a contagens) dá `publication_id`, `available_at`, `bars`, símbolos sem barras (contagem). **Pino da grade:** `--price-pinned-at` = o `available_at` da publicação NYSE (a segunda) + 1 s, anterior à próxima publicação noturna de qualquer bolsa; conferir no `host-check` seguinte que a janela das duas é ~2016-10 → hoje.
c. **`fetch` (escreve; ordem do dono):** `valuation_pit_rerun --market NASDAQ --fetch` e `--market NYSE --fetch --no-macro` (a curva dos EUA uma vez: `US_EODHD_TREASURY_HISTORY`). Uma leitura por símbolo: fundamentos EODHD (só `outstandingShares` serve com `--statements vintages`, quando a capa não traz as ações) e histórico de alvos FMP (descritivo); ~1.200 + ~2.000 chamadas; ~2.400 snapshots `valuation_pit_source` (~0,1–0,4 GB). Contagens por tipo de falha no recibo.
d. **`grid` em lotes (escreve; ordem do dono)** — **pré-condições:** (i) o lookback SEC de 10 anos (PR #450) mergeado e implantado e o backfill as-filed concluído para o universo: no `dry-run`, `coverage.<bolsa>.covered_in_catalogue` estável em duas leituras com ≥ 1 h de intervalo e ≥ 90 % do catálogo de cada bolsa (critério operacional, fora do veredito); no primeiro lote, `statements_coverage.covered_without_rows_by_T` (o `vintages_coverage` do recibo do reexecutor) dos `T` de 2021 deve ser pequeno — se não for, o lookback não chegou a 2016; (ii) `dry-run` com o pino: `grid.first = 2021-06-01`, `grid.count` = o esperado (≈ 266), `reusable` = 0 na primeira vez. **Execução:** `--max-runs` por lote (começar com 10 para medir o custo: o recibo de cada `T` traz `elapsed_seconds`; a safra de 120 meses faz cada corrida ler ~2.500 barras por nome), repetido até `complete: true`; cada lote **reutiliza** os `T` completos sem recomputar e escreve um manifesto novo (artefato `valuation-pit-backtest-grid-<run_id>`). Escreve, por corrida, um snapshot `valuation_pit_rerun` e os registros `v3_2_shadow` dos nomes avaliados com TP (≈ 532 corridas; registros ≈ soma dos nomes cobertos avaliados — algumas centenas por corrida; **~1,5–3 GB** no total, estimativa). **Publicar no canal** o `manifest_sha256` do manifesto completo antes do relatório.
e. **`report` (somente leitura):** `manifest_run_id` (a corrida do último lote), `manifest_sha256` (o publicado) e `prereg_commit` (o commit do recibo de hash). O workflow baixa o manifesto do artefato, confere o hash, passa-o pelo stdin ao contêiner e verifica o recibo (§10) antes de publicar. Memória: as observações compactas da grade (~150 mil) ocupam ~0,5 GB no processo.

**Regra de parada.** Um lote que falha (status ≠ 0) publica o manifesto do que fez, com `stopped = {reason: error, at, market, error: <tipo>}` (nunca a mensagem; o stderr fica privado). Então: **não** mudar parâmetros (pino, modo, passo, início); diagnosticar (reproduzir no host sob ordem do dono, se preciso); **erro de dados** (snapshot macro em falta, safra) → corrigir e retomar com os mesmos parâmetros (os `T` completos são reutilizados; usar `--recompute-existing` num lote final se dados de entrada mudaram durante a grade); **correção de código do produtor** → nova revisão deste documento antes de qualquer relatório e a grade inteira refeita (novo `source_version`: nunca se misturam produtores — o relatório anula). Se o custo medido no primeiro lote não couber nas janelas até a sexta, avisar o dono **no ato** — uma grade mais rala exige nova revisão (permitida, porque nenhum rótulo terá sido lido). Nunca rodar `report` sobre um manifesto com `complete: false`.

## 15. Código vinculado (pins)

Uma linha por pin: `file <caminho> <sha256 dos bytes>` para os módulos inteiros do instrumento; `object <nome> <sha256>` para objetos de módulos compartilhados (o texto-fonte de funções e métodos; o `repr` de constantes). Gerado por `render_pins()` do módulo do relatório; o teste `test_the_prereg_pins_exactly_the_code_at_head` falha se divergirem. Qualquer diferença entre esta lista e `payload.code` anula a leitura (§9, §10); qualquer mudança nesta lista é nova revisão.

```text
file app/valuation_accuracy_report.py 3388d3221535b768e68a68e8cdec83914e8d3e3084b8a4eb32256366341f040e
file app/valuation_panel.py cfebdd986876bd5d2929a4cda6de335e1634ea60cb10c632fa7dee997f883e16
file app/valuation_pit_backtest_report.py 2a9878679e226c0616f5fd73837e0d1374a567b030741e94861dd10e56189959
file app/valuation_price_history.py df057f2aafd7ca219df11e2979a32cf3965400047a583d33cc00d1a7d64ea011
object app.database.Database._PREDICTION_KEYS a1b0395da4625ce162bd2b4ab7a014a839a3c573db8eabab70b5154c0139f7dd
object app.database.Database._PREDICTION_ORDER a99e4f6d32d49d519be7fc2d7cea83f30cffe27fc9e82c4df86eceaa47d53844
object app.database.Database._PRICE_BAR_KEYS f2f2f280031d8084cb97faf45de313b8035828509583433a538fddc5eb5d6e79
object app.database.Database._prediction_order_key b9d565708b14eabc60757ea54e97024d5d0aaef069525ea2e5ee2bc288479626
object app.database.Database._prediction_record 5eacddae20c000e7f60c6e4390ee4b9a51477bf8cc881a97cf6d9bddc65143a4
object app.database.Database._price_bar_instant 65b5c30adb74f73163bb65ea2e8e069151c978001b37f45562fc0d0377ba1751
object app.database.Database._selection_instant 78f3a0414f03e69eacb4e219dcc0778097841949d98b9e0bcdec774021d7daab
object app.database.Database._stored_prediction 4f94c1515629ab51838b050b0a4a3731b15c3a6b27d8813fa0e634d3b6d5345b
object app.database.Database.analysis_snapshot_by_id 419e05955a09a5a8d41191fbf66b93eca4bec17400f2fe346d922901f38588bd
object app.database.Database.latest_analysis_snapshot_before 6cfb5bd58370d3bc323bcf55d3c3483a718afa21faec838b345b1e62f3a6ffa6
object app.database.Database.latest_analysis_snapshot_by_inputs 6219e6acdf7771d61116668732096c2c033534ac2eff471c4732593c367350e7
object app.database.Database.list_valuation_predictions_in_window dcd7c01634b1ca42df2c4bb33cdeb9467f0ce17429b93250feb1a3641c7757bf
object app.database.Database.price_bars aa6f3b26743eac31ef80de2e03fc7920717471e57d49694214c9cc79faee42f1
object app.valuation_official.CALENDARS d2bd4b223d2104840303e02eb2d6e94072a27cfa3046d279e1c39e4e46ad9932
object app.valuation_official.LEGACY_PREDICTION_SCHEMA d78a6a6366afda59e0073b35b7c31f42b1b7a4b561c2fac5e5e0efa177cd9b1e
object app.valuation_official.PREDICTION_SCHEMA 52fcabc723560d53d79a3dd12264f003f9a6f0acdf85ad2ac52b0bea2262d979
object app.valuation_official.SESSION_ZONES d9182bdbb021b11ed3315d40c64cd7cead50a268501d23752162d24495fcd3e8
object app.valuation_official.SOURCE_V3_2_SHADOW f7825e90e0e185aa6f65e750fdf4f60ec3aaf1a0ebefb2946af35c77b03ababd
object app.valuation_official._calendar 4d1588c5877846190427b196d6b73138a0d2cbbede911dad429c6f51ab4ebfdd
object app.valuation_official._stored_as_legacy b50d7988265736212acfb2ab8681793e0313272c4f771d63249dc4d5bf0d1577
object app.valuation_official._utc a4b3820e106e5fe933a87ad5fa40afb1ad119e13d3f9bb8eb2d4f3e3aa14cb88
object app.valuation_official.canonical_sha256 9e06b7a3bbf652767fd68b08bb6ed4487e43f6daef920ccaa365d4f69283b9f5
object app.valuation_official.session_date_of 8e4ad70ae6dc8deaf6ba50f9150dbefa627e75d330f118479d65d4b5770932e9
object app.valuation_official.stored_prediction a27c33d61a8bc54f8ceb65b92fdca3369e64c2a71665f80e2e989dd7a3756bfb
object app.valuation_pit_panel.PIT_RERUN_ANALYSIS_TYPE 372ccf3b17634466cbadf34564f643040daba4952358c426d7bc1aeb28bd87a3
object app.valuation_pit_panel.UNATTESTED_HORIZONS 42cf2eabaa5358505d74def6b8c0181297a1c25cc8445cb543dee50eb2f9df5f
object app.valuation_pit_panel._as_missing_horizon 21838e6814879fb65d2b9ea677e2b0c31f012b414e9dbf2ce355a240bfb94478
object app.valuation_pit_panel._unattested_horizon 97d03c0c63e91be5b2f3f67ba4067afc6540a8cd9cf7fd82f222eb101cee39e8
object app.valuation_pit_panel.refuse_superseded_runs c10e7b5d497c3418e714aa649e136edd1356e8904a833315ee867bbe0e1b8672
object app.valuation_pit_panel.superseded_run_keys 748d679afbf707c6b7d3429748e25d508937dba14eb3b5ae83c48f01df3d7cf6
```

## 16. Revisões

**rev 1 (17/10/2026)** — primeira versão. Decisões fixadas pelo dono e pela coordenação antes do hash: mercado US, uma seção transversal por sessão XNYS, catálogo corrente; grade a cada 5 sessões desde `GRID_START = 2021-06-01` sobre o backfill de preços de 120 meses pinado (achado de 17/10: com 36 meses o modelo de história própria nunca rodava, §2-bis); `T` = 01:00 BRT do dia seguinte; `--statements vintages`; IC executável em `h = 21` com os blocos do §5 do decisor; leitura única com PASS/NEGATIVE/UNMEASURED/FAIL; limitações declaradas; vínculo de código. Uma fonte de barras mensais chegou a ser considerada e foi **descartada** (a máquina de séries existente já cobre 120 meses).
