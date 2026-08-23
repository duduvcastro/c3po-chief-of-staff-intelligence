# Valuation Engine V3 - Especificacao para congelamento

**Status:** proposta docs-only para auditoria · **Motor atual:** V2 em shadow ·
**Motor proposto:** V3 em shadow separado · **Referencia normativa:**
[`VALUATION_V2_BLUEPRINT_V1.md`](./VALUATION_V2_BLUEPRINT_V1.md), especialmente
P1-P6 e §5 · **Data-base da medicao:** 23/08/2026

Esta especificacao define o V3 antes de qualquer implementacao. Ela nao autoriza
codigo, troca de TP oficial, mudanca de consumidor ou recalibracao de banda. A
implementacao so pode comecar depois da auditoria e do congelamento a seis maos.

---

## 1. Escopo fechado

| Item da fila do blueprint | Decisao V3 | Motivo |
|---|---|---|
| 1. Comps ajustados por ROE/crescimento | **Entra** | A medicao mostrou o padrao "barato vs. peers" em CHTR, PDD, CPB, BIDU, NVO e HPQ. O V2 usa a mediana crua mesmo quando a empresa ocupa outra posicao de qualidade dentro do grupo. |
| 2. Historico B3 condicionado a juros | **Entra** | `own_history` domina RECV3, GOAU4, INTB3, SAPR4 e LIGT3; o vies interno B3 ficou em -15,18% mesmo depois da correcao da curva no DCF. |
| 3. Reverse DCF composto | **Fica para V4** | Ainda nao existe serie acumulada de `growth_gap` que identifique um horizonte `k`. Escolher `k` agora reintroduziria um numero livre e violaria P2/P3. |
| 4. Feed de Treasury US | **Entra** | Remove o fallback fixo de 4,2% e torna o custo de equity observavel, datado e reproduzivel. E uma correcao de insumo, nao uma calibracao contra o consenso. |
| 5. Peso de consenso | **Fica para V4** | Uma unica noite nao identifica novos pesos. O shrink atual continua apenas como politica herdada e nao pode ser usado para fazer a regua interna parecer melhor. |

O V3 preserva sem alteracao: modelos existentes, regra de meio de ciclo,
intervalo do solver do reverse DCF `[-25%, +40%]`, limites individuais de TP
`[0,35x, 3,00x]` do preco, confiabilidades basicas, agregacao, bandas P4 de
15%/30%, pesos de consenso 20%/25%/35%/50%, bear/bull, consumidores e TP
oficial.

---

## 2. Mudanca V3.1 - comps ajustados por qualidade observada

### 2.1 Escopo economico

O ajuste se aplica somente a multiplos vindos de **peers reais** para perfis
`general`, `growth` e `quality`:

- P/E forward ou trailing usado por `earnings_power`;
- EV/EBITDA e P/B usados por `peer_comps`.

Ele nao se aplica a mediana setorial, historico proprio, `financial`, `cyclical`,
`utilities` ou `real_estate`. Financeiras ja possuem P/B-vs-ROE proprio;
ciclicas continuam integralmente protegidas pela regra de lucro de meio de
ciclo; receita forward nao e proxy adequada de qualidade para utilities/REITs.

### 2.2 Dados e amostra

Para cada empresa-alvo `i` e metrica `m`, a base de qualidade segue uma ladder
fechada, sem misturar fontes na mesma regressao:

1. **`fmp_forward`**: ROE anual mais recente em `key_metrics_annual`
   (campo bruto FMP `returnOnEquity`) e receitas FY1
   e FY2 positivas em `analyst_estimates_annual`, tanto para o alvo quanto para
   pelo menos quatro peers;
2. **`chewie_trailing`**: ROE e crescimento anual de receita do mesmo snapshot
   persistido `chewie_fundamentals`, para o alvo e pelo menos quatro peers;
3. **indisponivel**: preserva a mediana V2 sem ajuste.

A primeira base elegivel vence. Um peer nunca combina ROE FMP com crescimento
Chewie, e peers forward/trailing nunca entram juntos. Assim, a V3.1 usa apenas
dados que ja existem nos snapshots de 23/08; nao cria endpoint nem chamada nova
de provedor. A cobertura faltante aparece no relatorio em vez de ser preenchida.

Na base `fmp_forward`, o crescimento comparavel e:

```text
g_j = revenue_avg_FY2,j / revenue_avg_FY1,j - 1
```

Na base `chewie_trailing`:

```text
g_j = revenue_growth_percent_j / 100
```

Seja `P_m` o conjunto dos peers que possuem, na base vencedora, ROE e `g_j`
finitos e o multiplo `M_j,m` valido nos limites V2 e na mesma base economica
(P/E forward nunca mistura com trailing).

A empresa-alvo precisa dos mesmos dois sinais (`ROE_i`, `g_i`). O ajuste exige
`|P_m| >= MIN_PEER_SAMPLE`, portanto preserva o minimo V2 de 4; se faltar dado,
o V3 usa **exatamente** a mediana V2 nao ajustada e registra o motivo. Nenhum
ativo e removido do A/B por falta do ajuste.

### 2.3 Formula exata

Para uma variavel `x` e `n = |P_m|`, o rank empirico de `z` contra os peers e:

```text
rank_x(z) = (count(x_j < z) + 0,5 * count(x_j = z)) / n
```

Logo, para alvo e peers:

```text
r_roe,k = rank_ROE(ROE_k)
r_g,k   = rank_g(g_k)
q_k     = (r_roe,k + r_g,k) / 2
quartil_k = min(4, floor(4 * q_k) + 1)
```

O quartil e persistido para auditoria, mas **nao recebe premio fixo**. O ajuste
e uma regressao robusta derivada dos proprios peers. Para todos os pares de
peers `a,b` com `q_a != q_b`:

```text
slope_a,b = (ln(M_b,m) - ln(M_a,m)) / (q_b - q_a)
beta_m    = max(0, median(slope_a,b))
q0_m      = median(q_j)
M0_m      = winsorized_median_V2(M_j,m)
Mraw_i,m  = M0_m * exp(beta_m * (q_i - q0_m))
Madj_i,m  = clamp(Mraw_i,m, Q25(M_j,m), Q75(M_j,m))
```

`Q25/Q75` usam interpolacao linear na posicao `(n-1)*p`, a mesma convencao da
funcao de percentil do shadow. Se nao existir slope (todos os `q_j` iguais),
`beta_m = 0`. Se a relacao observada for negativa, o `max(0, ...)` impede que o
modelo fabrique um premio invertido: `Madj` volta a `M0`, sujeito apenas ao IQR.

Consequencias que eliminam o numero livre:

- o ponto neutro e a qualidade mediana dos proprios peers;
- a inclinacao vem integralmente das combinacoes peer-a-peer;
- o ajuste nunca sai do intervalo interquartil observado;
- alvo na qualidade mediana ou amostra sem relacao positiva reproduz o V2;
- nao existe tabela "Q1 = -x%, Q4 = +y%" nem coeficiente manual de ROE/growth.

A confiabilidade nunca aumenta por causa do ajuste:

```text
reliability_v3 = min(
    reliability_v2,
    clamp(n_complete / 8, 0,25, 1,00)
)
```

O `8` e os clamps sao os ja congelados no V2. Dispersao continua sendo a pior
dispersao das metricas usadas. A saida registra `quality_adjustment_status`,
`quality_sample`, `target_roe_rank`, `target_growth_rank`, `target_quality_rank`,
`target_quality_quartile`, `quality_beta`, `unadjusted_multiple`,
`adjusted_multiple`, `quality_basis` e os limites IQR.

### 2.4 Falha atacada e efeito esperado

Ataca nominalmente CHTR, PDD, CPB, BIDU, NVO, HPQ, ACN e outros casos em que a
mediana crua trata uma empresa de qualidade/crescimento diferente como peer
mediano. Nao promete corrigir sozinho CHTR/CPB quando `own_history` continuar
sendo a maior atribuicao; se esses casos nao responderem, isso identifica a
proxima causa sem mover a regua.

Predicao pre-registrada no snapshot de 23/08:

| Mercado | Direcao esperada na regua interna | Magnitude de triagem |
|---|---|---|
| B3 | Neutra a leve melhora; o efeito principal vem da V3.2 | p50 0 a -2 p.p.; p90 0 a -5 p.p. |
| NASDAQ | Reducao, concentrada na cauda "barato vs. peers" | p50 -3 a -8 p.p.; p90 -10 a -25 p.p. |
| NYSE | Reducao, concentrada em NVO/HPQ/ACN/FIS/GPN | p50 -2 a -6 p.p.; p90 -8 a -20 p.p. |

Esses intervalos sao previsoes, nao gates novos. Resultado fora deles e
reportado, nunca usado para alterar formula ou banda dentro da mesma versao.
Como controle contra melhora cosmetica, o vies mediano assinado tambem e
vinculante ao diagnostico: no baseline ele e -23,91% no NASDAQ e -17,84% no
NYSE; espera-se movimento em direcao a zero, respectivamente de +3 a +8 p.p. e
+2 a +6 p.p., nao apenas compressao da cauda positiva.

### 2.5 Testes que pinam a semantica

1. Amostra sintetica com slope conhecido recupera `beta`, `Madj` e quartil
   byte a byte.
2. Permutar a ordem dos peers nao altera nenhum resultado.
3. Alvo no `q0` e slope zero reproduzem a mediana V2.
4. Relacao negativa entre qualidade e multiplo nao gera premio/penalidade.
5. Predicao extrema fica presa a Q25/Q75 e depois aos bounds V2 da metrica.
6. Forward e trailing jamais entram na mesma regressao.
7. A ladder prefere `fmp_forward`, usa `chewie_trailing` apenas como coorte
   completa e nunca mistura campos das duas fontes.
8. Menos de 4 peers completos ou alvo incompleto cai no V2 sem excluir ativo.
9. Confiabilidade V3 nunca supera V2.
10. `financial`, `cyclical`, `utilities` e `real_estate` permanecem bit-a-bit V2.
11. O caso B3 `.SA` usa simbolo canonico e nao perde peers.

---

## 3. Mudanca V3.2 - historico B3 condicionado ao regime de Selic

### 3.1 Escolha unica

O V3 escolhe **janela condicionada ao regime**. Nao combina shrink setorial nem
ponderacao de recencia. A variavel de regime e a **meta Selic oficial**, serie
SGS 432 do Banco Central do Brasil.

Justificativa: o problema medido e uma banda historica de multiplos formada em
regimes de custo de capital diferentes. A Selic possui serie oficial longa,
reproduzivel e com cobertura para as datas fiscais. A curva prefixada de 5 anos
continua sendo o insumo de duration do DCF atual; ela nao possui hoje a mesma
serie historica persistida para os dez anos de cada multiplo. Misturar as duas
funcoes criaria um novo ponto de falha sem melhorar a identificacao do regime.

### 3.2 Formula exata

Para cada observacao anual de multiplo `M_t` com data fiscal `d_t`, e para a
data de avaliacao `T`, defina a Selic de regime como a mediana das observacoes
diarias oficiais no ano terminado na respectiva data:

```text
S_t = median(Selic_d), para d em [d_t - 365 dias, d_t]
S_T = median(Selic_d), para d em [T   - 365 dias, T]
distance_t = abs(S_t - S_T)
```

`Selic_d` e o ultimo valor oficial vigente em cada dia civil `d` (carry-forward
da decisao do Copom ate a proxima observacao, que e a semantica da meta, nao
imputacao estatistica). Nao ha backfill anterior a primeira observacao recebida.

Para cada metrica historica (P/E, EV/EBITDA, P/B) separadamente:

1. manter apenas observacoes validas nos bounds V2 e com `S_t` disponivel;
2. ordenar por `(distance_t asc, fiscal_year_end desc)`;
3. selecionar exatamente as primeiras `MIN_HISTORY_YEARS = 5`;
4. calcular `fair_multiple = winsorized_median_V2` sobre as cinco selecionadas.

Com menos de cinco anos mapeados, a formula V2 nao condicionada e preservada e
o resultado recebe `regime_status=insufficient_selic_history`; nao ha Selic
inventada nem perda silenciosa de cobertura. Fora da B3, a banda historica e
bit-a-bit V2.

A saida registra, por metrica: `current_selic_regime`, datas/rates selecionados,
distancias, anos descartados, `unconditioned_multiple`, `conditioned_multiple`,
fonte, `as_of` e hash do pacote macro.

### 3.3 Dados, anti-lookahead e falha atacada

Novo snapshot read-only `valuation_macro_history/B3_SELIC_REGIME`, contendo a
resposta normalizada da SGS 432, `observation_date`, `available_at`, `fetched_at`
e SHA-256 do payload canonico. Nenhuma observacao posterior a `T` participa.
Revisao retroativa do provedor muda o hash e invalida o A/B; nao e aceita
silenciosamente.

Ataca RECV3, GOAU4, INTB3, SAPR4 e LIGT3, todos com maior atribuicao em
`own_history`, e a hipotese de que a mediana crua de dez anos mistura regimes
de juros incompativeis.

Predicao falseavel principal:

```text
vies mediano assinado B3 interno:
V2 = -15,18%  ->  V3 dentro de [-10%, +10%]
```

Predicao secundaria de triagem: p50 absoluto B3 cai de 22,32% para 14%-19% e
p90 de 56,98% para 42%-52%. Se a predicao principal falhar, nao se altera a
janela: registra-se que regime de juros nao explica o residuo e investiga-se a
proxima causa em nova fronteira de versao.

### 3.4 Testes que pinam a semantica

1. Serie sintetica seleciona exatamente os cinco anos de menor distancia.
2. Empate de distancia escolhe o ano fiscal mais recente.
3. Cada metrica seleciona seus proprios anos; ausencia de P/E nao contamina P/B.
4. Nenhuma observacao Selic posterior ao `as_of` e aceita.
5. Menos de cinco anos mapeados reproduz V2 e explicita o fallback.
6. Alterar somente anos de Selic distantes, fora da janela escolhida, nao muda TP.
7. Mercados US permanecem bit-a-bit V2.
8. A saida permite recalcular o multiplo condicionado somente com os campos
   persistidos.

---

## 4. Mudanca V3.3 - curva Treasury US observada

### 4.1 Fonte e formula

O V3 reutiliza os feeds EODHD ja contratados e exibidos no sistema:
`US3Y.GBOND` e `US10Y.GBOND`. Para casar com o horizonte de cinco anos do motor,
interpola linearmente a curva na mesma data de observacao:

```text
r_US_5Y = r_US_3Y + (5 - 3) / (10 - 3) * (r_US_10Y - r_US_3Y)
         = r_US_3Y + (2/7) * (r_US_10Y - r_US_3Y)
cost_of_equity = clamp(r_US_5Y + beta * 5,5%, 6%, 16%)
```

Os dois yields precisam ser finitos, positivos, expressos em taxa anual e ter a
mesma `observation_date`, que deve ser a ultima sessao US concluida em ou antes
do `as_of`. O motor le a curva uma vez por run e usa o mesmo valor em NASDAQ e
NYSE. Nao existe fallback 4,2% no V3: feed ausente, futuro, de datas diferentes
ou incompleto faz o run V3 US falhar fechado e preserva o snapshot V3 anterior.
O V2 e todos os consumidores atuais continuam normalmente.

O snapshot `valuation_macro_rates/US_5Y_INTERPOLATED` persiste os dois pontos,
formula, valor interpolado, datas, `available_at`, fonte e hash canonico.

### 4.2 Falha atacada e efeito esperado

Remove `US_RISK_FREE_FALLBACK = 4,2%`, que nao e observacao datada. Se `r_US_5Y`
for maior que 4,2%, `cost_of_equity` sobe e os TPs de reverse DCF/RIM/DDM caem;
se for menor, ocorre o inverso. Peer comps, own history e earnings power nao
mudam.

O objetivo e auditabilidade, nao fechar o gap por calibracao. Magnitude esperada
na regua interna: menos de 1 p.p. no p50 e menos de 3 p.p. no p90 de NASDAQ e
NYSE para deslocamentos usuais da curva; B3 permanece inalterada.

### 4.3 Testes que pinam a semantica

1. Curva sintetica 3Y/10Y recupera exatamente a interpolacao `2/7`.
2. Datas diferentes, observacao futura ou ponto ausente falham fechado.
3. Nenhum resultado V3 US contem `fallback_constant` ou 4,2% implicito.
4. Subir ambos os pontos, sem tocar nos demais inputs, nao eleva TP de
   reverse DCF/RIM/DDM.
5. NASDAQ e NYSE do mesmo run carregam valor e hash identicos.
6. Falha da curva preserva o ultimo snapshot V3 e nao afeta V2/consumidores.

---

## 5. A/B deterministico de 23/08

### 5.1 Inputs congelados

O A/B usa os mesmos 693 ativos (100 B3, 294 NASDAQ, 299 NYSE), sem reconsultar
preco, consenso, universo ou fundamentals. IDs de producao que formaram a
medicao aceita:

| Tipo | Mercado | Snapshot ID | `published_at` UTC |
|---|---|---|---|
| `valuation_universe` | B3 | `fafc3cb7-e134-4145-8d48-104efec4d0bb` | 2026-08-23 03:02:01.735588 |
| `valuation_universe` | NASDAQ | `105c391b-e97a-4bc7-9147-275e2ea19210` | 2026-08-22 03:05:59.859601 |
| `valuation_universe` | NYSE | `497f6881-aa09-4e9b-bb3b-8296c06188af` | 2026-08-22 03:08:08.206357 |
| `valuation_v2_data` | B3 | `597a521b-85f1-476c-ab89-a1b2281f7d06` | 2026-08-23 20:01:49.336367 |
| `valuation_v2_data` | NASDAQ | `453f3e3c-26a0-4356-930d-7897cf63e273` | 2026-08-23 20:02:50.959346 |
| `valuation_v2_data` | NYSE | `9aeefef0-99f0-48b5-b3b0-1a0806c12b34` | 2026-08-23 20:03:54.422841 |
| `chewie_fundamentals` | B3 | `e86f90da-8dc3-4291-8645-25d5c30c246e` | 2026-08-23 06:33:25.317650 |
| `chewie_fundamentals` | NASDAQ | `b969e458-5184-426e-8ffb-4c1c1ac469f4` | 2026-08-23 06:35:07.041436 |
| `chewie_fundamentals` | NYSE | `bc45ee83-be9c-4cb3-8ec0-73468eb29811` | 2026-08-23 06:36:15.194761 |
| `valuation_v2_shadow` | B3 | `076f4ba5-5819-4be8-acf2-97d4b04bbcf9` | 2026-08-23 20:10:19.264617 |
| `valuation_v2_shadow` | NASDAQ | `7fbe53b0-5808-4057-b6f7-ed8f7c5a28c9` | 2026-08-23 20:10:19.819307 |
| `valuation_v2_shadow` | NYSE | `0af1538b-efb9-4e5b-a60e-26382aaecc35` | 2026-08-23 20:10:20.396467 |

Baselines que a reexecucao V2 precisa recuperar:

| Mercado | p50/p90 interno | Vies mediano assinado | p50 interno por perfil |
|---|---|---|---|
| B3 | 22,32% / 56,98% | -15,18% | growth 59,29%; general 16,44%; cyclical 22,76%; financial 48,75%; utilities 29,36%; real_estate 25,17% |
| NASDAQ | 33,66% / 73,29% | -23,91% | growth 38,20%; general 25,34%; cyclical 38,92%; financial 43,55%; utilities 14,78%; real_estate 32,56% |
| NYSE | 24,60% / 58,48% | -17,84% | growth 31,55%; general 18,32%; cyclical 30,65%; financial 35,81%; utilities 12,66%; real_estate 27,78% |

Antes do primeiro A/B, um manifest imutavel registra esses IDs, SHA-256 do JSON
canonico (`sort_keys`, UTF-8, sem espacos), os pacotes macro B3/US e o commit dos
dois motores. Qualquer hash divergente invalida o run; nao se substitui snapshot
por "mais recente".

### 5.2 Execucao e relatorio obrigatorio

O mesmo harness chama V2 e V3 puros com os mesmos inputs. O V2 precisa reproduzir
byte a byte os resultados aceitos acima antes que qualquer numero V3 exista.
Contagem por mercado deve permanecer 100/294/299; diferenca e falha do A/B.

O relatorio traz, para V2 e V3:

- divergencia interna p50/p90 e vies mediano assinado por mercado e perfil;
- divergencia final p50/p90 apenas como leitura de produto;
- contagem/taxa de `low_conviction`, modelos disponiveis e fallbacks V3.1/V3.2;
- atribuicao da maior divergencia e cobertura dos novos dados;
- decomposicao isolada V2 -> V3.1 -> V3.1+V3.2 -> V3 completo, para nao
  atribuir a uma mudanca o efeito de outra;
- diff completo da watchlist abaixo, sem selecionar vencedores depois do fato.

Watchlist congelada (os papeis repetidos preservam seus dois papeis de auditoria):

- baseline: HPQ, CPB, MPC, CF, CMCSA;
- B3 top-5: RECV3, GOAU4, INTB3, SAPR4, LIGT3;
- NASDAQ top-5: CHTR, PDD, CPB, BIDU, ADBE;
- NYSE top-5: NVO, HPQ, ACN, FIS, GPN.

---

## 6. Shadow vivo e gates

Depois do A/B aprovado, `ENGINE_VERSION = 3` roda em trilha propria
(`valuation_v3_shadow`), lado a lado com o V2. Nao sobrescreve snapshots V2 e
nao e lido pela faixa atual do PDF.

So existe medicao viva elegivel depois de **10 noites consecutivas bem-sucedidas**
com os tres mercados, curva US valida e contagem de ativos explicada. Uma noite
falha reinicia a sequencia operacional, mas os resultados validos anteriores
permanecem auditaveis. Isso e soak operacional, nao permissao de promocao.

O reporte acumulado repete todas as metricas do A/B, incluindo amostra por
perfil, watchlist completa e taxa de low conviction. A queda dos 529/693 (76%)
so conta quando vier de modelos/ancoras melhores; bandas e shrink nao mudam.

Gates de promocao continuam exatamente os do blueprint:

```text
divergencia interna p50 <= 15%
divergencia interna p90 <= 30%
em cada mercado E em cada perfil observado
```

Passar o gate apenas abre a discussao de troca por consumidor, na ordem PDF ->
screener -> `pretrade_rank`, cada uma com diff proprio e decisao a seis maos.
Nao autoriza troca automatica.

---

## 7. Invariantes e criterios de revisao

1. V2 permanece importavel e bit-a-bit identico.
2. V3 nao e importado por One Pager oficial, screeners, R2D2 ou qualquer rota
   de decisao.
3. Bandas P4, pesos de consenso e TP oficial nao mudam.
4. Todo dado novo possui `source`, `observation_date`, `available_at`,
   `fetched_at` e hash; nenhum input futuro entra.
5. Falta de dado degrada de forma explicita; nunca cria constante de fair value.
6. Formulas, bounds e fallbacks desta spec sao testes de regressao obrigatorios.
7. Resultado inesperado nao altera parametro dentro do V3: gera diagnostico e,
   se necessario, proposta V4.

## 8. Processo autorizado apos congelamento

1. Auditoria Fable desta spec docs-only.
2. Congelamento a seis maos, sem editar formula durante implementacao.
3. PR de dados/macro + motor V3 + testes, ainda sem consumidor.
4. Auditoria cruzada do codigo contra esta spec.
5. A/B congelado de 23/08 e relatorio assinado.
6. Shadow vivo minimo de 10 noites e veredito a seis maos.

Nada neste documento autoriza producao decisoria ou capital real.
