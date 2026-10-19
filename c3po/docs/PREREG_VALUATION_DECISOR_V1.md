# Pré-registro — Decisor de Valuation V1: acurácia realizada das fontes oficiais de TP (`PREREG_VALUATION_DECISOR_V1`, rev 2)

**Estado:** rascunho rev 2 para hash, 17/10/2026. Torna-se vinculante quando o `sha256` dos **bytes deste arquivo**, no commit que o introduz, for publicado num recibo no canal técnico — recibo que **cita esse commit** — **antes de qualquer leitura da partição de holdout** (§6). Depois do hash, nada aqui muda: qualquer alteração é uma **nova revisão**, com novo hash e — salvo a revisão aditiva do §6.5 — **novo `H0`** (o holdout recomeça). A rev 1 (commit `184d4e2`) nunca foi hasheada: recebeu NO-GO na auditoria de 17/10/2026; o que mudou e por quê está no §16.

**Contexto:** direção do dono de 17/10/2026 — o Valuation passa a ser o **decisor de compra/não compra**; demonstrações trimestrais como arquivadas (SEC XBRL para US, CVM para B3), Radar e todas as métricas definidas; cronograma comprimido em duas semanas. Este documento fixa **como se mede se o decisor acerta**, antes de olhar para os dados que vão julgá-lo.

**Instrumento:** `c3po/backend/app/valuation_accuracy_report.py` (schema do recibo `VALUATION-ACCURACY-REPORT-v1`; testes `tests/test_valuation_accuracy_report.py`), executado em produção somente-leitura pelo workflow `.github/workflows/valuation-readonly-report.yml`. O instrumento **reutiliza** o painel §7.3 (`VALUATION_PANEL_7_3.md`, `valuation_panel.py`): admissibilidade, coorte viva, rótulo, verificação de base, atrito. O código que produz os números está **vinculado** a este documento (§10, §17). Este pré-registro **não substitui** o PROMO-2 do painel (h = 126 contra o consenso); são perguntas diferentes.

## 1. Pergunta e objeto

1. **O upside servido à noite ordena os retornos executáveis seguintes?** (IC de postos sobre o retorno com entrada no fecho de `T + 1` — a pergunta primária: sem sinal de ordenação aproveitável não há decisor.)
2. **A lista de compra rende mais que o universo?** (COMPRA_PERMITIDA × universo — a pergunta do decisor.)
3. **O nível do TP erra menos que o passeio aleatório e que o consenso?** (log-MSE — descritivo nesta revisão.)

**Objeto medido:** os registros imutáveis de previsão `valuation_predictions` das duas fontes oficiais — `official_blend_v1` (TP com consenso, Passo 0) e `official_internal_v1` (TP interno, consenso fora, Passo 1) — **como foram servidos em cada noite**, qualquer que seja a versão de metodologia (`source_version`, contada no recibo por versão). Mudanças do produtor (frente XBRL/CVM, Radar, metodologia do TP) fazem parte do objeto; o que reinicia o holdout são mudanças **deste protocolo**, do **código vinculado** (§17) ou da **fonte decisória** depois do prazo cego (§6.3).

**Fonte decisória:** a fonte que o decisor V1 lê, declarada no recibo de congelamento do decisor V1 **publicado antes do prazo cego** = o fecho da primeira sessão em que algum alvo do holdout amadurece, em qualquer mercado (a âncora + 21 sessões do calendário que amadurece primeiro; com `H0 = 2026-10-18`: o fecho de **17/11/2026** no XNYS). Até esse instante nenhum retorno do holdout existe, então a escolha não pode usar o resultado que vai julgá-la. Sem essa declaração no prazo, a fonte decisória é a servida pela seleção oficial em `H0` (hoje `official_blend_v1`: a troca para o interno segue travada por `OFFICIAL_TP_REPLACEMENT_AUTHORIZED = False`). A outra fonte é **comparativa**: medida com as mesmas regras, nunca decisória.

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
rx(i,T,h)   = adjusted_close(T + 1 + h) / adjusted_close(T + 1) − 1   # retorno EXECUTÁVEL (decisório): entra no fecho de T+1
r(i,T,h)    = adjusted_close(T + h) / adjusted_close(T) − 1     # retorno total T → T+h (descritivo)
P̂(i,T,h)   = price · (tp / price)^(h / 252)                     # TP de 12 meses pro-rata geométrico para h sessões
e_fonte     = ln( P̂ · a(T) ) − ln( adjusted_close(T + h) )
e_PA        = ln( price · a(T) ) − ln( adjusted_close(T + h) )  # passeio aleatório: tp = price
e_consenso  = ln( price · (consensus_tp / price)^(h / 252) · a(T) ) − ln( adjusted_close(T + h) )
```

- **Por que o retorno executável decide:** o ciclo noturno roda entre 01:00 e 08:00 BRT, depois do fecho de `T`; um TP pode já reagir a um arquivamento pós-fecho ou a um evento do Radar, e a coorte viva aceita registros publicados até o fecho de `T + 1`. O retorno `r` começa no fecho de `T` e "vê" a reação do dia seguinte; `rx` começa no fecho de `T + 1`, depois de tudo o que a noite podia saber. Toda condição do veredito lê `rx`; `r` é publicado como leitura.
- `rx` existe quando **os dois** rótulos do par (`T + 1` e `T + 1 + h`) estão presentes com a base verificada; `r` e os erros-log exigem o rótulo em `T + h`. Os dois são medidos independentemente.
- `e_consenso` só existe quando o bloco de consenso persistido no registro está `present` (os cinco campos atestados do PROMO-2 c, `published_at ≤ prediction_instant`, moeda do registro) **e** declara horizonte `12m`; senão a observação sai da máscara comum, contada por causa (`absent`, `consensus_unattested:<campo>`, `consensus_after_prediction`, `consensus_currency_mismatch`, `consensus_horizon_not_12m`).
- Em `h = 252` o `e_fonte` é exatamente o log-erro §2.6 do painel; o recibo publica também esse erro do TP **não escalado** em `h` (`log_mse_raw_tp`, diagnóstico).
- **Horizontes:** `h = 21` (primário, o único decisório), `63` e `126` sessões (descritivos).
- Pesos iguais por nome; retornos brutos (sem custos) em moeda local.

## 4. Métricas (por mercado, fonte, horizonte e partição)

| # | Métrica (campo do recibo) | Estatística por sessão `T` | Mínimo por sessão | Papel |
|---|---|---|---|---|
| M1x | **IC executável** (`ic_executable`) | Spearman (postos médios para empates) entre `u` e `rx(h)` sobre os nomes de `T` com `rx` | `MIN_NAMES_PER_SESSION = 10` | **decisória (primária)** em `h = 21` |
| M2x | Spread de decis executável (`decile_spread_executable`) | média de `rx(h)` do decil superior de `u` − decil inferior; decil = `⌊(posto médio − 0,5) · 10 / n⌋` (empatados partilham o decil) | `MIN_NAMES_DECILES = 30` | condição de PASS (estimativa > 0) |
| M1 | IC de postos (`ic`) | Spearman entre `u` e `r(h)` | 10 nomes com `r` | descritiva |
| M2 | Spread de decis (`decile_spread`) | idem M2x sobre `r(h)` | 30 nomes com `r` | descritiva |
| M3 | log-MSE vs passeio aleatório (`log_mse_vs_random_walk`) | razão agrupada `Σe_fonte² / Σe_PA²` na partição; por sessão, `média(e_fonte²) − média(e_PA²)` (Diebold–Mariano em blocos) | 1 nome | descritiva (`BETTER` sse razão < 1) |
| M4 | log-MSE vs consenso (`log_mse_vs_consensus`) | idem na máscara comum (consenso presente e 12m): `Σe_fonte² / Σe_consenso²` | 1 nome na máscara | descritiva |
| M5x / M5 | COMPRA_PERMITIDA × universo (`buy_list_excess_executable` / `buy_list_excess`) | média do retorno (`rx` / `r`) dos nomes da lista − média de todos os nomes de `T` | 10 nomes e ≥ 1 na lista | ver §6.5 (M5x decisória quando a lista do decisor existir) |

- Uma sessão sem a estatística é contada por causa (`below_min_names`, `degenerate` — sem variância de postos —, `no_list`, `no_label`, `no_consensus`), nunca preenchida.
- **M5 nesta revisão:** a lista COMPRA_PERMITIDA do decisor ainda não existe no armazenamento (frente do decisor, migração 052). Até lá o recibo publica o **proxy** `decomposition.status = "full_match"` (a classe de compra do próprio produtor na noite `T`, persistida no registro) com `decisory: false`. Para `official_internal_v1` o proxy é o mesmo `status` do blend (resíduo declarado do P1): o proxy **não distingue as fontes**.

## 5. Erros-padrão em blocos (horizontes sobrepostos)

Retornos de `h` sessões medidos todos os dias se sobrepõem: as estatísticas diárias são autocorrelacionadas até a defasagem `h − 1`. Erro-padrão por **médias de lotes (batch means)**:

1. **Grade:** sessões do calendário do mercado a partir da **âncora** da partição (holdout: a primeira sessão ≥ `H0`; desenvolvimento: a primeira sessão observada na partição), índice `k = 0, 1, 2, …`. Bloco `b` = índices `[b·h, (b+1)·h)`: comprimento **`h` sessões de calendário** (21, 63 ou 126).
2. **Bloco completo:** todas as suas sessões pertencentes à partição já têm o alvo fechado antes do corte — `T + h` para as estatísticas de `r`, **`T + 1 + h`** para as de `rx` (o recibo publica o índice em `mature_through_index`). Blocos incompletos ficam `blocks_pending` e **não contam**; bloco completo sem nenhuma estatística é `blocks_empty` e não conta. `B` = número de blocos completos com estatística.
3. **Estimativa** = média das médias de bloco (cada bloco pesa igual). `mean_per_session` (todas as sessões medidas, pendentes incluídas) é publicada como leitura, nunca usada no teste.
4. **Erro-padrão:** `se = √1,5 · dp(médias de bloco) / √B` (dp amostral, `B − 1`). O fator **1,5 = 1 + 2ρ₁** com `ρ₁ = 1/4`: sob retornos sobrepostos de `h` sessões (autocorrelação triangular `1 − k/h` da estatística diária), a covariância entre médias de blocos adjacentes de comprimento `h` é `h²/6` contra variância `2h²/3` — correlação 1/4; blocos a duas ou mais distâncias não se sobrepõem.
5. **Teste:** `t = estimativa / se`, **t de Student com `B − 1` graus de liberdade** (implementado no módulo; `p_greater = P(T ≥ t)`, `p_less = P(T ≤ t)`). Com `se = 0` não há teste.
6. **Diagnóstico:** Newey–West (Bartlett, defasagem `h`) sobre a série diária dos blocos completos, posicional — publicado, **nunca decisório**.

## 6. Divisão temporal, treino e congelamentos

1. **`H0`** = o primeiro dia civil **posterior** à data (America/Sao_Paulo) do recibo de hash deste documento. Em cada mercado a âncora do holdout é a primeira sessão do seu calendário em ou após `H0`. (Recibo publicado no sábado 17/10/2026 → `H0 = 2026-10-18`, âncora 19/10/2026 em B3 e US. Recibo mais tarde → `H0` mais tarde; as datas do §13 andam junto.)
2. **Desenvolvimento** = sessões `T < H0`; **holdout** = sessões `T ≥ H0`. A primeira leitura (a fatia `h = 21` já madura, previsões de setembro e início de outubro) é **desenvolvimento**: verifica o instrumento e calibra expectativas — em particular o desvio-padrão por sessão do IC executável que o §9-bis usa —; **não é evidência e não decide nada**. A partição de desenvolvimento nunca tem veredito; a última sessão dela corta o último bloco (`partition_last_index`).
3. **O que reinicia `H0` (nova revisão, novo hash):** qualquer constante do §15; qualquer pin do §17 (o código que calcula os números: admissibilidade, coorte, base, atrito, blocos, veredito, leitores do armazenamento); a fonte decisória depois do prazo cego do §1. **O que não reinicia `H0`:** as regras do decisor — limiares, filtros, a forma da lista —, porque o teste do IC mede a ordenação do upside da **fonte** sobre o universo inteiro e não lê nenhuma regra do decisor; elas só afetam M5x, que tem relógio próprio (§6.5). Também não reiniciam: mudanças do produtor (objeto, §1) e o congelamento do decisor V1 em si. Assim, o decisor que a frente da migração 052 está construindo **não move `H0`**, desde que declare a fonte que lê antes do prazo cego.
4. **Treino:** qualquer parâmetro do decisor ou deste protocolo que dependa de dados só pode ser fixado com dados de desenvolvimento (ou, para a fonte, antes do prazo cego).
5. **Revisão aditiva (sem reiniciar `H0`):** permitida uma única vez para ligar M5x à lista real do decisor, quando a frente do decisor gravar COMPRA_PERMITIDA. Ela só **acrescenta**: a leitura de M5x a partir da lista gravada, com holdout próprio `H0_lista` = primeiro dia civil posterior ao recibo de congelamento do decisor V1 (≥ `H0`), e a regra do §7 passo 7. Nenhuma outra constante pode mudar nessa revisão. Uma mudança das regras do decisor depois do seu congelamento reinicia **só** `H0_lista`.

## 7. Regra de decisão — holdout, `h = 21`, IC executável, por mercado (na fonte decisória)

Aplicada **nesta ordem** a cada leitura semanal (§8); o recibo carrega o veredito em `results.<mercado>.<fonte>.verdict` (com `statistic = ic_executable`):

1. **`NOT_YET_MATURE`** — nenhum alvo de saída `T + 1 + 21` do holdout fechou antes do corte. Não é leitura: não conta, não gasta alfa, não abre incidente. É o estado esperado nas primeiras semanas depois de `H0` (§13).
2. **`UNMEASURED`** — alvos já amadureceram mas não há observação elegível (o produtor não publicou), ou o atrito do par executável em `h = 21` passa de `ATTRITION_CAP = 0,10` (rótulos indisponíveis ÷ elegíveis, §10). A leitura **não conta**.
3. **`HARM`** — `B ≥ MIN_BLOCKS = 5` e `p_less ≤ ALPHA_HARM = 0,025` no IC executável (por olhada, sem correção: a taxa cumulativa está declarada no §9 e no §9-bis). (Depois do §6.5: o mesmo teste sobre M5x também dispara `HARM`.)
4. **`INSUFFICIENT`** — `B < MIN_BLOCKS = 5` (na leitura do prazo final, §8: `INCONCLUSIVE`).
5. **Tipo de leitura:** `FINAL` se `B ≥ FINAL_BLOCKS = 24` **ou** o corte for em/depois de **2029-01-31**; senão `INTERIM`. Alfa unilateral: **0,003** em cada leitura interina, **0,04** na final — tamanho total ≈ 0,05 sob o modelo do §5 (§9-bis).
6. **`SIGNAL_PASS`** sse, todas: estimativa do IC executável ≥ **`IC_MIN = 0,02`**; seu `p_greater ≤ alfa`; estimativa do spread de decis executável (M2x) **> 0**. Senão **`CONTINUE`** (interina) ou **`INCONCLUSIVE`** (final), com as razões listadas.
7. **`PASS`** (decisor completo; só depois da revisão aditiva §6.5): `SIGNAL_PASS` **e** M5x com `B ≥ 5` no holdout da lista e estimativa > 0. Nesta revisão M5 não é decisória: o máximo é `SIGNAL_PASS`.

Fora do veredito, sempre: M1, M2 (o retorno `T → T+h`), M3 e M4 (log-MSE — o nível de um TP de 12 meses pro-rata é outra pergunta que a ordenação) e os horizontes 63 e 126. A rev 1 dizia que 63/126 serviam para `HARM`; com âncora em 19/10/2026 cinco blocos completos só amadurecem em ~abril/2028 (63) e ~outubro/2029 (126) — o de 126 depois do fim do protocolo —, então a afirmação foi retirada: são leituras, não alarmes. Dois estados não vêm da regra: `VOID` (código não vinculado, §10) e `NO_HOLDOUT` (execução sem `H0`, só desenvolvimento).

## 8. Regra de parada e cadência

- **Leituras decisórias:** semanais, com corte `C` = **sábado 12:00 America/Sao_Paulo** (`--as-of` com fuso), pelo workflow `valuation-readonly-report.yml` a partir da imagem implantada, com `--holdout-start H0` e `--prereg` apontando para este arquivo implantado. Uma **olhada** é uma leitura cujo `B` é novo (com o mesmo `B` a estatística é a mesma). Um sábado perdido pode ser lido depois com o mesmo corte (o armazenamento é só-acréscimo e a safra é a que o corte via). Uma execução fora da cadência pode ser feita para conferir o instrumento, mas o seu veredito **não vale** para decisão.
- **Parar com dano:** `HARM` em qualquer leitura → fim do protocolo para aquele mercado e fonte; recomendação à mesa: suspender COMPRA_PERMITIDA daquela fonte naquele mercado (a mesa decide; o protocolo não liga nem desliga nada). O limiar de dano é deliberadamente menos exigente que o de sucesso (assimetria de segurança: um falso alarme custa uma suspensão revisável; um dano não detectado custa dinheiro) — o preço está declarado no §9.
- **Parar com sucesso:** `SIGNAL_PASS` (ou `PASS`, §7.7) numa leitura interina (alfa 0,003) ou na final (alfa 0,04) → confirmação; o recibo continua sendo publicado como monitoramento, sem novo veredito.
- **Parar sem conclusão:** leitura final (`B ≥ 24` ou corte ≥ 2029-01-31) sem `SIGNAL_PASS`/`HARM` → `INCONCLUSIVE`; o protocolo termina. Continuar exige uma nova revisão (V2) com novo holdout.
- **`NOT_YET_MATURE`** nunca conta. **`UNMEASURED`** não conta como leitura (nem gasta alfa); três consecutivas exigem incidente aberto (dado, não decisor).

## 9. Multiplicidade

- Duas decisões independentes (B3, US), na **fonte decisória** apenas; sem correção entre mercados (decisões operacionais separadas, declarado). A fonte comparativa, os horizontes 63/126, as métricas descritivas e a partição de desenvolvimento nunca decidem.
- **Olhadas de sucesso:** alfa 0,003 em cada olhada interina (`B = 5 … 23`) e 0,04 na final (`B = 24`): o tamanho total simulado é ≈ 0,05 (§9-bis). Não é Haybittle–Peto clássico (que gastaria 0,001 por olhada): o alfa interino foi aumentado para que um sinal útil possa ser confirmado antes de dois anos, e o final reduzido para manter o total.
- **Olhadas de dano:** `ALPHA_HARM = 0,025` em cada olhada (`B = 5 … 24`), **sem correção**. Sob IC verdadeiro 0 a taxa cumulativa de `HARM` é ≈ **10,7 %** (não 2,5 %); sob IC +0,02 ela é ≤ 3,8 % e sob IC ≥ +0,03 ≤ 2,0 % (dp ≤ 0,12) — um sinal útil quase nunca é interrompido; um sinal nulo é suspenso por engano em cerca de uma de cada dez execuções, o que a assimetria do §8 aceita. Com M5x decisória (§6.5) há um segundo alarme com a mesma taxa sob a sua hipótese nula.

## 9-bis. Poder e efeito mínimo detectável

**Modelo** (o mesmo do §5): o IC executável diário é `IC + dp · N_t`, com `N_t` a soma móvel normalizada de `h = 21` normais independentes (variância 1, autocorrelação triangular `1 − k/h`); blocos de 21 sessões; olhadas em `B = 5 … 24` na ordem do §7 (HARM antes do sucesso; `IC_MIN` sobre a estimativa). `dp` é o desvio-padrão por sessão do IC executável ao longo do tempo (amostragem + variação do sinal); só a amostragem, com `n` nomes por sessão, dá ≈ `1/√(n − 1)` — 0,045 com 500 nomes, 0,058 com 300, 0,10 com 100 — e a variação do sinal soma a isso; por isso a tabela vai de 0,06 a 0,12. Nem o atrito nem a condição do spread (M2x > 0) estão no modelo: as probabilidades de sucesso são **limites superiores**. Reprodutível: `design_table()` do módulo, `DESIGN_SEED = 20261017`, `DESIGN_REPS = 20000` caminhos por célula.

Probabilidade, ao fim do protocolo, de `SIGNAL_PASS` (total · só em olhada interina) e de `HARM`, em %:

| `dp` \ IC | −0,05 | −0,03 | 0 | +0,02 | +0,03 | +0,05 | +0,08 |
|---|---|---|---|---|---|---|---|
| 0,06 | 0,0 · 0,0 · H 98,7 | 0,0 · 0,0 · H 77,6 | 4,6 · 2,0 · H 10,7 | 43,7 · 18,7 · H 1,1 | 74,1 · 40,8 · H 0,4 | 98,6 · 87,5 · H 0,0 | 100,0 · 99,9 · H 0,0 |
| 0,08 | 0,0 · 0,0 · H 90,3 | 0,1 · 0,1 · H 58,6 | 5,1 · 2,0 · H 10,7 | 30,5 · 11,6 · H 2,0 | 53,3 · 23,4 · H 0,8 | 89,6 · 61,1 · H 0,1 | 99,9 · 96,6 · H 0,0 |
| 0,10 | 0,0 · 0,0 · H 77,6 | 0,3 · 0,2 · H 46,3 | 5,1 · 2,0 · H 10,7 | 22,8 · 8,3 · H 3,0 | 39,5 · 15,6 · H 1,5 | 75,2 · 40,8 · H 0,4 | 98,1 · 84,6 · H 0,0 |
| 0,12 | 0,1 · 0,1 · H 65,5 | 0,4 · 0,3 · H 38,2 | 5,1 · 2,0 · H 10,7 | 18,4 · 6,6 · H 3,8 | 30,5 · 11,6 · H 2,0 | 60,9 · 28,7 · H 0,6 | 92,7 · 67,5 · H 0,1 |

**IC executável mínimo detectável com 80 % de poder** (`SIGNAL_PASS` até o fim do protocolo): `dp` 0,06 → **0,033**; `dp` 0,08 → **0,043**; `dp` 0,10 → **0,054**; `dp` 0,12 → **0,064**.

Leitura honesta: com `dp` entre 0,08 e 0,10 o protocolo detecta, com 80 %, ICs a partir de ≈ 0,045–0,055; com `dp` 0,12 — o provável num mercado de poucos nomes por sessão, como a B3 — a partir de ≈ 0,065. `IC_MIN = 0,02` é um **piso econômico** sobre a estimativa, não o efeito detectável: um IC verdadeiro entre 0,02 e o efeito mínimo detectável **provavelmente termina `INCONCLUSIVE`** — declarado antes de olhar. A leitura de desenvolvimento (§6.2) mede o `dp` real; ela pode mostrar que a linha certa da tabela é outra, mas **não muda nenhuma constante** sem nova revisão antes do hash.

**Por que 24 blocos (§16):** com o desenho da rev 1 (12 blocos, alfa 0,001/0,025) e `dp` 0,10 a probabilidade de sucesso era 17,1 % com IC 0,03 e 37,6 % com IC 0,05 (efeito mínimo detectável 0,087) — um sinal útil quase certamente terminaria inconclusivo em ~novembro/2027, a repetição do desenho H1/H3 sem poder. **Alternativa não adotada** (decisão da mesa, se quiser, **antes do hash**): manter um ano (12 blocos) com alfa final 0,10 — tamanho total ≈ 10,6 %, efeito mínimo detectável 0,050 (`dp` 0,08) / 0,062 (`dp` 0,10): um ano a menos ao preço de dobrar a taxa de falso positivo.

## 10. Atrito, dados faltantes e integridade

- **Atrito decisório** (`attrition_executable`): denominador = observações cujo alvo de saída `T + 1 + h` fechou antes do corte; indisponível = falta qualquer rótulo do par (a causa da saída; senão `entry:<causa>`). Causas (painel): `no_vintage`, `manifest_mismatch`, `symbol_not_in_vintage`, `vintage_unreproducible`, `bar_hash_mismatch`, `vintage_mismatch`, `outside_window`, `missing_bar`, `label_unavailable:*`. `not_yet_mature` fica **fora** do denominador. Teto 0,10. O atrito de `r` em cada horizonte (`attrition`) é publicado como leitura.
- Os registros são ponto-no-tempo (sem viés de sobrevivência na amostra); um nome deslistado vira `missing_bar` → atrito, o que pode favorecer a fonte se as saídas forem perdedoras: por isso o teto e a publicação por causa.
- **Validade de uma leitura decisória** — todas, senão a leitura é **nula**:
  1. recibo produzido pelo workflow (artefato com `payload_sha256` recalculado);
  2. `payload.prereg_sha256` igual ao hash publicado deste documento, e o arquivo implantado igual byte a byte ao da revisão do workflow;
  3. `payload.holdout_start = H0`; `payload.protocol` igual às constantes do §15;
  4. **código vinculado:** `payload.code.files` e `payload.code.objects` iguais, nome a nome e hash a hash, aos pins do §17, e `payload.code_binding.status = BOUND` (sem isso o próprio recibo marca todo veredito como `VOID`);
  5. `payload.code.build_sha` é um commit (40 hex). Ele é **registrado, não fixado**: todo deploy de qualquer frente muda a revisão implantada e um commit não pode conter o próprio sha; o que fixa o código são os hashes do §17, e o recibo de hash cita o commit deste arquivo.
- O workflow **recusa publicar** (falha antes do upload) qualquer recibo que viole 1, 2, 4 ou 5. As versões de `exchange_calendars` e do Python vão em `payload.code` como registro, sem pin (limitação, §14).

## 11. O que este documento não decide

- Não bloqueia nem libera o uso operacional do decisor, não muda número servido, não vira trava, não substitui o PROMO-2 do painel §7.3 (h = 126 contra o consenso) nem a troca blend → interno (P1).
- Não mede valor econômico líquido: retornos brutos, sem custos de execução (bid/ask) nem dimensionamento. O valor líquido do decisor é outra medição, com outro pré-registro.

## 12. Recibo (`VALUATION-ACCURACY-REPORT-v1`)

```text
{ "schema", "payload": { "schema", "protocol": {constantes do §15, "gate": false}, "cut", "window", "holdout_start", "prereg_sha256",
                         "code": {files: {caminho: sha256}, objects: {nome: sha256}, exchange_calendars, python, build_sha},
                         "code_binding": {status: BOUND|MISMATCH|UNBOUND, pinned, reasons},
                         "market_groups": ["B3", "US"], "sources": [...],
                         "results": { <mercado>: { <fonte>: {
                             "records": {read, admissible, refused, cohort, scope_live, source_versions_live_universe},
                             "vintages": {<bolsa>: cabeçalho da safra}, "last_closed_session",
                             "partitions": { "development"|"holdout": { anchor, first_session, last_session, observations, sessions, partition_last_index,
                                 "horizons": { "21"|"63"|"126": { eligible, ineligible, labelled, attrition, attrition_executable,
                                     observations, observations_executable, ic, ic_executable, decile_spread, decile_spread_executable,
                                     buy_list_excess, buy_list_excess_executable, log_mse_vs_random_walk, log_mse_vs_consensus, log_mse_raw_tp } } } },
                             "verdict": {status, statistic, look, alpha, reasons, blocks, blocks_pending, ic_estimate, ic_p_greater, ic_p_less,
                                         buy_list_decisory: false, gate: false} } } } },
  "payload_sha256": sha256 canônico do payload,
  "provenance": {generated_at} }      # fora do payload: o payload é função de (corte, armazenamento, parâmetros, código)
```

Cada série estatística: `{sessions_measured, sessions_not_measured, mature_through_index, blocks: {block_length, blocks, blocks_pending, blocks_empty, sessions, mean_per_session, estimate, se, t, df, p_greater, p_less, variance_factor, newey_west}}`. Status possíveis do veredito: `NOT_YET_MATURE`, `UNMEASURED`, `HARM`, `INSUFFICIENT`, `SIGNAL_PASS`, `CONTINUE`, `INCONCLUSIVE`, `VOID`, `NO_HOLDOUT`. **Nenhum símbolo** no recibo; só agregados. O processo força sessão PostgreSQL somente-leitura (`PGOPTIONS=-c default_transaction_read_only=on`) e só alcança quatro leitores do armazenamento.

## 13. Expectativa honesta de prazo

Datas com `H0 = 2026-10-18` (âncora 19/10/2026), calculadas com `exchange_calendars`; **não são firmes**: um hash mais tarde move `H0`, e blocos vazios (lacunas do produtor) atrasam `B`.

- **Primeiros sábados (24/10, 31/10, 07/11, 14/11/2026): `NOT_YET_MATURE`.** O primeiro alvo de saída do holdout fecha em 18/11/2026 (US) / 19/11/2026 (B3); a primeira leitura com dados é a de **21/11/2026** (`INSUFFICIENT`, `B = 0`).
- **Primeiro veredito possível** (5.º bloco executável completo): ~**21/04/2027** (US) / ~**27/04/2027** (B3). Nessa data só um sinal muito forte passa (alfa 0,003 com 4 graus de liberdade).
- **Um ano** (`B = 12`): ~18/11/2027 (US) / ~25/11/2027 (B3) — leitura interina, não final.
- **Leitura final** (`B = 24`): ~**17/11/2028** (US) / ~**30/11/2028** (B3); o prazo final de 31/01/2029 cobre lacunas do produtor. Com `H0` uma semana depois (26/10/2026): ~27/11/2028 (US) / ~07/12/2028 (B3).
- **O congelamento do decisor V1 não move nada disso** se declarar a fonte antes do prazo cego (§1, §6.3).
- **Em duas semanas nenhum resultado decisório é possível**: o que se entrega em duas semanas é o instrumento, a leitura de desenvolvimento e o hash deste documento antes do holdout.

## 14. Limitações declaradas

- **Entrada no fecho de `T + 1`:** a coorte viva aceita publicação até o próprio fecho de `T + 1`; um registro publicado nos últimos minutos desse pregão não seria executável naquele fecho na prática. O ciclo noturno publica entre 01:00 e 08:00 BRT, então o caso é excepcional, mas não é excluído por regra.
- **Pro-rata geométrico** de um alvo de 12 meses é convenção deste protocolo, não afirmação do produtor; por isso M3/M4 são descritivos.
- **Modelo de sobreposição** (`ρ₁ = 1/4`) e **modelo de poder** (normal, IC estacionário, autocorrelação triangular): sinais persistentes e fatores de mercado podem ter memória mais longa; Newey–West é publicado ao lado para mostrar a discrepância, sem trocar a regra; o poder real pode ser menor que o da tabela.
- **Corte transversal variável:** o universo muda de noite para noite; pesos iguais; mercados US agregados (NASDAQ ∪ NYSE).
- **Proxy de lista** igual para as duas fontes (o `status` do produtor é a visão blend — resíduo do P1).
- **Vínculo de código por objeto** em `database.py` e `valuation_official.py` (módulos compartilhados com o app e com o produtor): os leitores e o que eles chamam estão no §17; o motor SQL, o driver, `exchange_calendars` e o Python não estão (versões registradas no recibo). Os três módulos do instrumento estão inteiros.

## 15. Constantes (espelho exato do código; todas dentro do payload hasheado)

`SCHEMA_VERSION = VALUATION-ACCURACY-REPORT-v1`; `PREREG = PREREG_VALUATION_DECISOR_V1`; `PREREG_REVISION = 2`; `MARKET_GROUPS = {B3: [B3], US: [NASDAQ, NYSE]}`; `HORIZONS = (21, 63, 126)`; `PRIMARY_HORIZON` h = 21; `EXECUTION_LAG_SESSIONS = 1`; `DECISORY_STATISTIC = ic_executable`; `TP_HORIZON_SESSIONS = 252`; `CONSENSUS_HORIZON = 12m`; `SCOPE = universe`; `MIN_NAMES_PER_SESSION = 10`; `MIN_NAMES_DECILES = 30`; `DECILES = 10`; `BUY_LIST = proxy:decomposition.status=full_match` (`decisory = false`); `ATTRITION_CAP = 0,10` (sobre o par executável); `MIN_BLOCKS = 5`; `FINAL_BLOCKS = 24`; `FINAL_DEADLINE = 2029-01-31`; bloco = `h` sessões de calendário, só completos; `ADJACENT_BLOCK_VARIANCE_FACTOR = 1,5`; `ALPHA_INTERIM = 0,003`; `ALPHA_FINAL = 0,04`; `ALPHA_HARM = 0,025` (por olhada); `IC_MIN = 0,02`; `TOL_BASIS = 0,02` e `LABEL_CONVENTION = total_return:adjusted_close` (do painel); calendários `BVMF`/`XNYS`; `PINNED_FILES` e `PINNED_OBJECTS` = as listas do §17. Desenho (não entra no veredito): `DESIGN_SEED = 20261017`, `DESIGN_REPS = 20000`, `DESIGN_SDS = (0,06; 0,08; 0,10; 0,12)`, `DESIGN_POWER = 0,80`.

## 16. Revisões

**rev 2 (17/10/2026)** — resposta ao NO-GO da auditoria da rev 1 (sete pontos, todos aceitos):

1. *Teste no retorno que vê o pós-fecho:* o veredito passa a ler **só** o retorno executável (`rx`, M1x/M2x); o IC sobre `T → T+h` vira descritivo (§3, §4, §7).
2. *Sem análise de poder:* §9-bis com tabela simulada pelo próprio módulo e efeito mínimo detectável; recalibração para 24 blocos, alfa 0,003/0,04 (§7, §15).
3. *Código não vinculado:* o payload carrega o hash de cada módulo e objeto usado; o §17 os fixa; divergência anula a leitura (`VOID`) e o workflow recusa publicar (§10).
4. *HARM em 63/126 inalcançável:* retirado; HARM só no IC executável em `h = 21` (§7).
5. *HARM repetido sem controle:* taxa cumulativa declarada (≈ 10,7 % sob IC 0) e justificada (§9).
6. *`UNMEASURED` ambíguo:* `NOT_YET_MATURE` é estado próprio, que não conta nem abre incidente (§7.1, §8).
7. *`H0` × congelamento do decisor:* as regras do decisor não entram no teste do IC; a fonte decisória é declarada antes do prazo cego; o congelamento não reinicia `H0` (§1, §6.3).

## 17. Código vinculado (pins)

Uma linha por pin: `file <caminho> <sha256 dos bytes>` para os módulos inteiros do instrumento; `object <nome> <sha256>` para objetos de módulos compartilhados (o texto-fonte de funções e métodos; o `repr` de constantes). Gerado por `render_pins(code_fingerprint())` do módulo. Qualquer diferença entre esta lista e `payload.code` anula a leitura (§10); qualquer mudança nesta lista é nova revisão com novo `H0` (§6.3).

```text
file app/valuation_accuracy_report.py 3388d3221535b768e68a68e8cdec83914e8d3e3084b8a4eb32256366341f040e
file app/valuation_panel.py cfebdd986876bd5d2929a4cda6de335e1634ea60cb10c632fa7dee997f883e16
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
object app.database.Database.list_valuation_predictions_in_window dcd7c01634b1ca42df2c4bb33cdeb9467f0ce17429b93250feb1a3641c7757bf
object app.database.Database.price_bars aa6f3b26743eac31ef80de2e03fc7920717471e57d49694214c9cc79faee42f1
object app.valuation_official.CALENDARS d2bd4b223d2104840303e02eb2d6e94072a27cfa3046d279e1c39e4e46ad9932
object app.valuation_official.LEGACY_PREDICTION_SCHEMA d78a6a6366afda59e0073b35b7c31f42b1b7a4b561c2fac5e5e0efa177cd9b1e
object app.valuation_official.PREDICTION_SCHEMA 52fcabc723560d53d79a3dd12264f003f9a6f0acdf85ad2ac52b0bea2262d979
object app.valuation_official.SESSION_ZONES d9182bdbb021b11ed3315d40c64cd7cead50a268501d23752162d24495fcd3e8
object app.valuation_official._calendar 4d1588c5877846190427b196d6b73138a0d2cbbede911dad429c6f51ab4ebfdd
object app.valuation_official._stored_as_legacy b50d7988265736212acfb2ab8681793e0313272c4f771d63249dc4d5bf0d1577
object app.valuation_official._utc a4b3820e106e5fe933a87ad5fa40afb1ad119e13d3f9bb8eb2d4f3e3aa14cb88
object app.valuation_official.canonical_sha256 9e06b7a3bbf652767fd68b08bb6ed4487e43f6daef920ccaa365d4f69283b9f5
object app.valuation_official.session_date_of 8e4ad70ae6dc8deaf6ba50f9150dbefa627e75d330f118479d65d4b5770932e9
object app.valuation_official.stored_prediction a27c33d61a8bc54f8ceb65b92fdca3369e64c2a71665f80e2e989dd7a3756bfb
```
