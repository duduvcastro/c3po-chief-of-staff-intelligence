# Pré-registro — Decisor de Valuation V1: acurácia realizada das fontes oficiais de TP (`PREREG_VALUATION_DECISOR_V1`, rev 1)

**Estado:** rascunho para hash, 17/10/2026. Torna-se vinculante quando o `sha256` dos **bytes deste arquivo**, no commit que o introduz, for publicado num recibo no canal técnico **antes de qualquer leitura da partição de holdout** (§6). Depois do hash, nada aqui muda: qualquer alteração é uma **nova revisão**, com novo hash e — salvo as revisões aditivas do §6.4 — **novo `H0`** (o holdout recomeça).

**Contexto:** direção do dono de 17/10/2026 — o Valuation passa a ser o **decisor de compra/não compra**; demonstrações trimestrais como arquivadas (SEC XBRL para US, CVM para B3), Radar e todas as métricas definidas; cronograma comprimido em duas semanas. Este documento fixa **como se mede se o decisor acerta**, antes de olhar para os dados que vão julgá-lo.

**Instrumento:** `c3po/backend/app/valuation_accuracy_report.py` (schema do recibo `VALUATION-ACCURACY-REPORT-v1`; testes `tests/test_valuation_accuracy_report.py`), executado em produção somente-leitura pelo workflow `.github/workflows/valuation-readonly-report.yml`. O instrumento **reutiliza** o painel §7.3 (`VALUATION_PANEL_7_3.md`, `valuation_panel.py`): admissibilidade, coorte viva, rótulo, verificação de base, atrito. Este pré-registro **não substitui** o PROMO-2 do painel (h = 126 contra o consenso); são perguntas diferentes.

## 1. Pergunta e objeto

1. **O upside servido à noite ordena os retornos seguintes?** (IC de postos — a pergunta primária: sem sinal de ordenação não há decisor.)
2. **A lista de compra rende mais que o universo?** (COMPRA_PERMITIDA × universo — a pergunta do decisor.)
3. **O nível do TP erra menos que o passeio aleatório e que o consenso?** (log-MSE — descritivo nesta revisão.)

**Objeto medido:** os registros imutáveis de previsão `valuation_predictions` das duas fontes oficiais — `official_blend_v1` (TP com consenso, Passo 0) e `official_internal_v1` (TP interno, consenso fora, Passo 1) — **como foram servidos em cada noite**, qualquer que seja a versão de metodologia (`source_version`, contada no recibo por versão). Mudanças do produtor (frente XBRL/CVM, Radar) fazem parte do objeto; o que reinicia o holdout são mudanças **deste protocolo** ou das **regras do decisor** (§6.3).

**Fonte decisória:** a fonte que o decisor V1 lê, declarada no recibo de congelamento do decisor; sem essa declaração até `H0`, a fonte servida pela seleção oficial em `H0` (hoje `official_blend_v1`: a troca para o interno segue travada por `OFFICIAL_TP_REPLACEMENT_AUTHORIZED = False`). A outra fonte é **comparativa**: medida com as mesmas regras, nunca decisória.

## 2. Dados, unidade de observação e mercados

- **Unidade:** `(i, T)` = nome `i`, sessão `T` (a `session_date` do registro: a última sessão concluída do calendário do mercado no `prediction_instant`).
- **Admissibilidade** (idêntica ao painel, `valuation_panel.admissible_records`): `published_at < C` (corte), `tp > 0`, sessão do calendário do mercado, **um registro por `(fonte, nome, sessão)`** (o de menor `published_at`; desempate pela ordem total pré-registrada do painel); registro sem `published_at` é inelegível.
- **Coorte viva** (painel, §2.2 R3 a): só registros publicados até o fecho da sessão seguinte à previsão. Re-execuções tardias são `retrospective` e **nunca** entram nas métricas (contadas em `records.cohort`).
- **Escopo:** só `scope = universe`. Registros direcionados (`targeted`, avaliação sob demanda) são seleção por pedido — fora do corte transversal, contados em `records.scope_live`.
- **Mercados (cada um é uma decisão separada):** `B3` (calendário BVMF, BRL) e `US` = NASDAQ ∪ NYSE (calendário XNYS, USD — um só corte transversal por sessão).
- **Preços:** a série persistida `valuation_price_history/<M>`, lida **somente** pela safra única que o corte vê (`available_before = C`); `close` e `adjusted_close` da mesma safra; retorno total (dividendos creditados). Barra indisponível no corte é rótulo ausente (atrito), **nunca** preço de outra fonte. Zero rede.
- **Verificação de base** (painel): moeda da barra = moeda do registro; `|price − close(T)| / close(T) ≤ TOL_BASIS = 0,02`; sem barra em `T` → `adjustment_unknown`. Falhas são causas de atrito.

## 3. Definições

```text
a(T)        = adjusted_close(T) / close(T)                      # mesma safra
u(i,T)      = tp / price − 1                                    # upside servido à noite T (tp e price do registro)
r(i,T,h)    = adjusted_close(T + h) / adjusted_close(T) − 1     # retorno total T → T+h (h em sessões do calendário)
rx(i,T,h)   = adjusted_close(T + 1 + h) / adjusted_close(T + 1) − 1   # retorno EXECUTÁVEL: entra no fecho de T+1
P̂(i,T,h)   = price · (tp / price)^(h / 252)                     # TP de 12 meses pro-rata geométrico para h sessões
e_fonte     = ln( P̂ · a(T) ) − ln( adjusted_close(T + h) )
e_PA        = ln( price · a(T) ) − ln( adjusted_close(T + h) )  # passeio aleatório: tp = price
e_consenso  = ln( price · (consensus_tp / price)^(h / 252) · a(T) ) − ln( adjusted_close(T + h) )
```

- `e_consenso` só existe quando o bloco de consenso persistido no registro está `present` (os cinco campos atestados do PROMO-2 c, `published_at ≤ prediction_instant`, moeda do registro) **e** declara horizonte `12m`; senão a observação sai da máscara comum, contada por causa (`absent`, `consensus_unattested:<campo>`, `consensus_after_prediction`, `consensus_currency_mismatch`, `consensus_horizon_not_12m`).
- Em `h = 252` o `e_fonte` é exatamente o log-erro §2.6 do painel; o recibo publica também esse erro do TP **não escalado** em `h` (`log_mse_raw_tp`, diagnóstico).
- **Horizontes:** `h = 21` (primário), `63` e `126` sessões.
- Pesos iguais por nome; retornos brutos (sem custos) em moeda local.

## 4. Métricas (por mercado, fonte, horizonte e partição)

| # | Métrica | Estatística por sessão `T` | Mínimo por sessão | Papel |
|---|---|---|---|---|
| M1 | **IC de postos** | Spearman (postos médios para empates) entre `u` e `r(h)` sobre os nomes de `T` | `MIN_NAMES_PER_SESSION = 10` | **decisória (primária)** |
| M1x | IC executável | Spearman entre `u` e `rx(h)` | 10 nomes com `rx` | condição de PASS (sinal > 0) |
| M2 | **Spread de decis** | média de `r(h)` do decil superior de `u` − decil inferior; decil = `⌊(posto médio − 0,5) · 10 / n⌋` (empatados partilham o decil) | `MIN_NAMES_DECILES = 30` | condição de PASS (sinal > 0) |
| M3 | log-MSE vs passeio aleatório | razão agrupada `Σe_fonte² / Σe_PA²` na partição; por sessão, `média(e_fonte²) − média(e_PA²)` (Diebold–Mariano em blocos) | 1 nome | descritiva (`BETTER` sse razão < 1) |
| M4 | log-MSE vs consenso | idem na máscara comum (consenso presente e 12m): `Σe_fonte² / Σe_consenso²` | 1 nome na máscara | descritiva |
| M5 | **COMPRA_PERMITIDA × universo** | média de `r(h)` dos nomes da lista − média de `r(h)` de todos os nomes de `T` | 10 nomes e ≥ 1 na lista | ver §6.4 (decisória quando a lista do decisor existir) |

- Uma sessão sem a estatística é contada por causa (`below_min_names`, `degenerate` — sem variância de postos —, `no_list`, `no_consensus`), nunca preenchida.
- **M5 nesta revisão:** a lista COMPRA_PERMITIDA do decisor ainda não existe no armazenamento (frente do decisor, migração 052). Até lá o recibo publica o **proxy** `decomposition.status = "full_match"` (a classe de compra do próprio produtor na noite `T`, persistida no registro) com `decisory: false`. Para `official_internal_v1` o proxy é o mesmo `status` do blend (resíduo declarado do P1): o proxy **não distingue as fontes**.

## 5. Erros-padrão em blocos (horizontes sobrepostos)

Retornos de `h` sessões medidos todos os dias se sobrepõem: as estatísticas diárias são autocorrelacionadas até a defasagem `h − 1`. Erro-padrão por **médias de lotes (batch means)**:

1. **Grade:** sessões do calendário do mercado a partir da **âncora** da partição (holdout: a primeira sessão ≥ `H0`; desenvolvimento: a primeira sessão observada na partição), índice `k = 0, 1, 2, …`. Bloco `b` = índices `[b·h, (b+1)·h)`: comprimento **`h` sessões de calendário** (21, 63 ou 126).
2. **Bloco completo:** todas as suas sessões pertencentes à partição já têm o alvo `T + h` fechado antes do corte (para M1x, `T + 1 + h`). Blocos incompletos ficam `blocks_pending` e **não contam**; bloco completo sem nenhuma estatística é `blocks_empty` e não conta. `B` = número de blocos completos com estatística.
3. **Estimativa** = média das médias de bloco (cada bloco pesa igual). `mean_per_session` (todas as sessões medidas, pendentes incluídas) é publicada como leitura, nunca usada no teste.
4. **Erro-padrão:** `se = √1,5 · dp(médias de bloco) / √B` (dp amostral, `B − 1`). O fator **1,5 = 1 + 2ρ₁** com `ρ₁ = 1/4`: sob retornos sobrepostos de `h` sessões (autocorrelação triangular `1 − k/h` da estatística diária), a covariância entre médias de blocos adjacentes de comprimento `h` é `h²/6` contra variância `2h²/3` — correlação 1/4; blocos a duas ou mais distâncias não se sobrepõem.
5. **Teste:** `t = estimativa / se`, **t de Student com `B − 1` graus de liberdade** (implementado no módulo; `p_greater = P(T ≥ t)`, `p_less = P(T ≤ t)`). Com `se = 0` não há teste.
6. **Diagnóstico:** Newey–West (Bartlett, defasagem `h`) sobre a série diária dos blocos completos, posicional — publicado, **nunca decisório**.

## 6. Divisão temporal: desenvolvimento × holdout

1. **`H0`** = o primeiro dia civil **posterior** à data (America/Sao_Paulo) do recibo de hash deste documento. Em cada mercado a âncora do holdout é a primeira sessão do seu calendário em ou após `H0`. (Recibo publicado no sábado 17/10/2026 → `H0 = 2026-10-18`, âncora 19/10/2026 em B3 e US.)
2. **Desenvolvimento** = sessões `T < H0`; **holdout** = sessões `T ≥ H0`. A primeira leitura (a fatia `h = 21` já madura, previsões de setembro e início de outubro) é **desenvolvimento**: verifica o instrumento e calibra expectativas; **não é evidência e não decide nada**. A partição de desenvolvimento nunca tem veredito; a última sessão dela corta o último bloco (`partition_last_index`).
3. **Treino:** qualquer parâmetro do decisor ou deste protocolo que dependa de dados só pode ser fixado com dados de desenvolvimento. Qualquer mudança nas **regras do decisor** (limiares, filtros, fonte lida) ou numa constante do §15 depois do hash → nova revisão, novo hash, **novo `H0`**.
4. **Revisão aditiva (sem reiniciar `H0`):** permitida uma única vez para ligar M5 à lista real do decisor, quando a frente do decisor gravar COMPRA_PERMITIDA. Ela só **acrescenta**: a leitura de M5 a partir da lista gravada, com holdout próprio `H0_lista` = primeiro dia civil posterior ao recibo de congelamento do decisor V1 (≥ `H0`), e a regra do §7 passo 6. Nenhuma outra constante pode mudar nessa revisão.

## 7. Regra de decisão — holdout, `h = 21`, por mercado (na fonte decisória)

Aplicada **nesta ordem** a cada leitura semanal (§8); o recibo carrega o veredito em `results.<mercado>.<fonte>.verdict`:

1. **`UNMEASURED`** — atrito em `h = 21` acima de `ATTRITION_CAP = 0,10` (rótulos indisponíveis ÷ elegíveis), ou nenhuma observação elegível. A leitura **não conta** (não é olhada para nada).
2. **`HARM`** — em **qualquer** horizonte (21, 63, 126) com atrito ≤ 0,10 e `B ≥ MIN_BLOCKS = 5`: IC com `p_less ≤ ALPHA_HARM = 0,025`. (Quando M5 for decisória: o mesmo teste sobre M5 também dispara `HARM`.)
3. **`INSUFFICIENT`** — `B < MIN_BLOCKS = 5` no IC primário (na leitura do prazo final, §8: `INCONCLUSIVE`).
4. **Tipo de leitura:** `FINAL` se `B ≥ FINAL_BLOCKS = 12` **ou** o corte for em/depois de **2027-12-31**; senão `INTERIM`. Alfa (Haybittle–Peto): **0,001** nas interinas, **0,025** na final (unilateral).
5. **`SIGNAL_PASS`** sse, todas: estimativa do IC ≥ **`IC_MIN = 0,02`**; `p_greater ≤ alfa`; estimativa do spread de decis (M2) **> 0**; estimativa do IC executável (M1x) **> 0**. Senão **`CONTINUE`** (interina) ou **`INCONCLUSIVE`** (final), com as razões listadas.
6. **`PASS`** (decisor completo; só depois da revisão aditiva §6.4): `SIGNAL_PASS` **e** M5 com `B ≥ 5` no holdout da lista e estimativa > 0. Nesta revisão M5 não é decisória: o máximo é `SIGNAL_PASS`.

M3 e M4 (log-MSE) são **descritivos** nesta revisão: publicados com razão, rótulo `BETTER`/`NOT_BETTER` e Diebold–Mariano em blocos, **nunca** entram no veredito (o nível de um TP de 12 meses pro-rata é outra pergunta que a ordenação).

## 8. Regra de parada e cadência

- **Leituras decisórias:** semanais, com corte `C` = **sábado 12:00 America/Sao_Paulo** (`--as-of` com fuso), pelo workflow `valuation-readonly-report.yml` a partir da imagem implantada, com `--holdout-start H0` e `--prereg` apontando para este arquivo implantado. Uma execução fora da cadência pode ser feita para conferir o instrumento, mas o seu veredito **não vale** para decisão.
- **Parar com dano:** `HARM` em qualquer leitura → fim do protocolo para aquele mercado e fonte; recomendação à mesa: suspender COMPRA_PERMITIDA daquela fonte naquele mercado (a mesa decide; o protocolo não liga nem desliga nada). O limiar de dano é deliberadamente menos exigente que o de sucesso (assimetria de segurança: um falso alarme custa uma suspensão revisável; um dano não detectado custa dinheiro).
- **Parar com sucesso:** `SIGNAL_PASS` (ou `PASS`, §7.6) numa leitura interina (alfa 0,001) ou na final (alfa 0,025) → confirmação; o recibo continua sendo publicado como monitoramento, sem novo veredito.
- **Parar sem conclusão:** leitura final (`B ≥ 12` ou corte ≥ 2027-12-31) sem `SIGNAL_PASS`/`HARM` → `INCONCLUSIVE`; o protocolo termina. Continuar exige uma nova revisão (V2) com novo holdout.
- **Leituras `UNMEASURED`** não contam como leitura (nem gastam alfa); três consecutivas exigem incidente aberto (dado, não decisor).

## 9. Multiplicidade

- Duas decisões independentes (B3, US), na **fonte decisória** apenas; sem correção entre mercados (decisões operacionais separadas, declarado). A fonte comparativa, os horizontes 63/126 (exceto para `HARM`) e a partição de desenvolvimento nunca decidem.
- Leituras múltiplas: controladas por Haybittle–Peto (interinas a 0,001) e pelo número limitado de leituras finais (uma).

## 10. Atrito, dados faltantes e integridade

- Atrito por causa (painel): `no_vintage`, `manifest_mismatch`, `symbol_not_in_vintage`, `vintage_unreproducible`, `bar_hash_mismatch`, `vintage_mismatch`, `outside_window`, `missing_bar`, `label_unavailable:*`. `not_yet_mature` fica **fora** do denominador. Teto 0,10 por partição e horizonte.
- Os registros são ponto-no-tempo (sem viés de sobrevivência na amostra); um nome deslistado vira `missing_bar` → atrito, o que pode favorecer a fonte se as saídas forem perdedoras: por isso o teto e a publicação por causa.
- **Validade de uma leitura decisória:** recibo produzido pelo workflow (artefato com `payload_sha256` recalculado), `payload.prereg_sha256` igual ao hash publicado deste documento, `payload.holdout_start = H0`, `payload.protocol` igual às constantes do §15. Qualquer divergência anula a leitura.

## 11. O que este documento não decide

- Não bloqueia nem libera o uso operacional do decisor, não muda número servido, não vira trava, não substitui o PROMO-2 do painel §7.3 (h = 126 contra o consenso) nem a troca blend → interno (P1).
- Não mede valor econômico líquido: retornos brutos, sem custos de execução (bid/ask) nem dimensionamento. O valor líquido do decisor é outra medição, com outro pré-registro.

## 12. Recibo (`VALUATION-ACCURACY-REPORT-v1`)

```text
{ "schema", "payload": { "schema", "protocol": {constantes do §15, "gate": false}, "cut", "window", "holdout_start", "prereg_sha256",
                         "market_groups": ["B3", "US"], "sources": [...],
                         "results": { <mercado>: { <fonte>: {
                             "records": {read, admissible, refused, cohort, scope_live, source_versions_live_universe},
                             "vintages": {<bolsa>: cabeçalho da safra}, "last_closed_session",
                             "partitions": { "development"|"holdout": { anchor, first_session, last_session, observations, sessions, partition_last_index,
                                 "horizons": { "21"|"63"|"126": { eligible, ineligible, labelled, attrition, observations,
                                     ic, ic_executable, decile_spread, buy_list_excess, log_mse_vs_random_walk, log_mse_vs_consensus, log_mse_raw_tp } } } },
                             "verdict": {status, look, alpha, reasons, blocks, ic_estimate, ic_p_greater, buy_list_decisory: false, gate: false} } } } },
  "payload_sha256": sha256 canônico do payload,
  "provenance": {module_sha256, build_sha, generated_at} }      # fora do payload: o payload é função de (corte, armazenamento, parâmetros)
```

Cada bloco estatístico: `{block_length, blocks, blocks_pending, blocks_empty, sessions, mean_per_session, estimate, se, t, df, p_greater, p_less, variance_factor, newey_west}`. **Nenhum símbolo** no recibo; só agregados. O processo força sessão PostgreSQL somente-leitura (`PGOPTIONS=-c default_transaction_read_only=on`) e só alcança quatro leitores do armazenamento.

## 13. Expectativa honesta de prazo

Com `H0 = 2026-10-18` (âncora 19/10/2026), blocos de 21 sessões e `MIN_BLOCKS = 5`: o 5.º bloco completo do holdout fecha na sessão 105 (US 19/03/2027; B3 24/03/2027) e amadurece em ~20/04/2027 (US) / ~26/04/2027 (B3) — **o primeiro veredito possível**. A leitura final por blocos (`B = 12`, 252 sessões) amadurece em ~17/11/2027 (US) / ~24/11/2027 (B3); o prazo final de 31/12/2027 cobre lacunas do produtor. Em `h = 63`, 5 blocos só em ~abril/2028; em `h = 126`, ~outubro/2029 — esses horizontes servem, neste protocolo, para `HARM`. **Em duas semanas nenhum resultado decisório é possível**: o que se entrega em duas semanas é o instrumento, a leitura de desenvolvimento e o hash deste documento antes do holdout.

## 14. Limitações declaradas

- **`T → T+h` inclui o pós-fecho de `T`:** o TP é produzido à noite e pode já incorporar um arquivamento divulgado depois do fecho (o retorno T→T+h então "vê" a reação do dia seguinte). Por isso M1x (entrada no fecho de `T + 1`) é condição obrigatória de `SIGNAL_PASS`.
- **Pro-rata geométrico** de um alvo de 12 meses é convenção deste protocolo, não afirmação do produtor; por isso M3/M4 são descritivos.
- **Modelo de sobreposição** (`ρ₁ = 1/4`): sinais persistentes e fatores de mercado podem ter memória mais longa; Newey–West é publicado ao lado para mostrar a discrepância, sem trocar a regra.
- **Corte transversal variável:** o universo muda de noite para noite; pesos iguais; mercados US agregados (NASDAQ ∪ NYSE).
- **Proxy de lista** igual para as duas fontes (o `status` do produtor é a visão blend — resíduo do P1).

## 15. Constantes (espelho exato do código; todas dentro do payload hasheado)

`SCHEMA_VERSION = VALUATION-ACCURACY-REPORT-v1`; `PREREG = PREREG_VALUATION_DECISOR_V1`; `MARKET_GROUPS = {B3: [B3], US: [NASDAQ, NYSE]}`; `HORIZONS = (21, 63, 126)`; `PRIMARY_HORIZON` h = 21; `EXECUTION_LAG_SESSIONS = 1`; `TP_HORIZON_SESSIONS = 252`; `CONSENSUS_HORIZON = 12m`; `SCOPE = universe`; `MIN_NAMES_PER_SESSION = 10`; `MIN_NAMES_DECILES = 30`; `DECILES = 10`; `BUY_LIST = proxy:decomposition.status=full_match` (`decisory = false`); `ATTRITION_CAP = 0,10`; `MIN_BLOCKS = 5`; `FINAL_BLOCKS = 12`; `FINAL_DEADLINE = 2027-12-31`; bloco = `h` sessões de calendário, só completos; `ADJACENT_BLOCK_VARIANCE_FACTOR = 1,5`; `ALPHA_INTERIM = 0,001`; `ALPHA_FINAL = 0,025`; `ALPHA_HARM = 0,025`; `IC_MIN = 0,02`; `TOL_BASIS = 0,02` e `LABEL_CONVENTION = total_return:adjusted_close` (do painel); calendários `BVMF`/`XNYS` + versão do `exchange_calendars`.
