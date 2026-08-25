# R2D2 Exit Policy Study V1.1 - Entregavel 0

**Status:** pronto para auditoria do Fable. Nenhuma simulacao de politica alternativa foi executada.

## 0. Travas e evidencia

- Spec congelada: `c3po/docs/EXIT_POLICY_STUDY_V1_1.md`, SHA-256
  `21882372220d55aa01c0a23b9288d75788d25b1187c01b4954e0c500ec0216a2`.
- Politica de producao extraida no commit congelado
  `39ff427fd2f1fa0f42141776921a63651508495f` (merge da PR #211).
- Metodologia declarada nesse commit:
  `R2D2-HYBRID-V27-15M-LIQUIDITY-FLOOR`.
- Ledger usado nos casos nomeados: export de 782 linhas, SHA-256
  `a66e3efacbd0677dc50c146c760d79ea45a9b0161d91ee6bcaae78e0a058fa54`.
- MFE de 24/08: SHA-256
  `65c5ef9ab68fa996dcedcabe36a32c8dd7cf19f4207de7aaeb7538a06623366a`.
- Decomposicao de 21/08: [CSV por episodio](evidence/R2D2_REALIZED_EPISODES_2026-08-21.csv),
  SHA-256 `1a5cf48fabdbf285f515521fe38a45737e1bcb7353281d5c18fab82c6d844901`.

Os dados historicos nao foram reescritos. As duas correcoes de veracidade desta
entrega ficam explicitamente separadas da extracao da politica congelada:

1. o texto do mandato passa a descrever a trava de reentrada que o codigo ja
   executava;
2. o stop tecnico inicial passa a ser recalculado sobre a mesma cotacao fresca
   usada para o fill. Esta segunda mudanca corrige o defeito factual revelado
   por LOW; ela nao muda retroativamente o que ocorreu em 24/08.

## 1. Vereditos dos casos nomeados

| Caso | Veredito factual |
| --- | --- |
| LOW, 24/08 | O nivel `218.2634` nao era chandelier. Era o stop tecnico calculado sobre uma cotacao anterior de `219.14`, mantido depois que o BUY atualizou o sinal para `218.39`. Isso deixou apenas 5,80 bps entre a cotacao fresca e o stop. Defeito de modelagem no fill confirmado e corrigido nesta entrega. |
| EHC, 24/08 | Nao houve fill de `122.19` contra quote de `121.73`. O sinal foi `122.185` e o fill `122.307185`, exatamente +10 bps. `121.73` era a coluna **Stop**. Nao ha defeito de fill; EHC apenas compartilha o defeito menor de base temporal do stop corrigido com LOW. |
| `-US$ 39.981,68`, 21/08 | O valor nao e o realizado do ledger. E um valor de snapshot/fixture historica. O ledger canonico fecha em `-US$ 10.374,558379`, ou `-US$ 10.374,56` arredondado. Nao existe decomposicao honesta de `-US$ 39.981,68` por episodio. |
| CROX, 24/08 | O cascade executou a regra 19: reducao de 50% apos `defense_streak=7`; na revisao posterior, a regra 6 vendeu o restante por deterioracao persistente. O comportamento esta integralmente explicado abaixo. |

## 2. Semantica de preco, mark e liquido

### 2.1 Custos na entrada US

No BUY de NASDAQ/NYSE:

```text
fill = signal_quote * (1 + 0.0010)
fee = gross_fill * 0.0004
average_cost = (gross_fill + fee) / quantity
```

Logo, para uma cotacao `P`:

```text
average_cost / P = 1.0010 * 1.0004 = 1.0014004
mark inicial = P / average_cost - 1 = -0.139844162%
```

Esse e o `-0,1400%` exibido: 10 bps de slippage de entrada mais 4 bps de fee,
com o pequeno termo composto de 0,004 bp. O fill, a fee e a inclusao da fee no
`average_cost` estao em
[`r2d2.py:L3269-L3279`](https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/blob/39ff427fd2f1fa0f42141776921a63651508495f/c3po/backend/app/r2d2.py#L3269-L3279),
e a persistencia do custo medio em
[`r2d2.py:L625-L635`](https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/blob/39ff427fd2f1fa0f42141776921a63651508495f/c3po/backend/app/r2d2.py#L625-L635).

### 2.2 Mark e liquido realizavel

- `mark_pct = quote / average_cost - 1`: inclui a perna de entrada ja paga,
  mas ainda nao a friccao da venda.
- `net_pct = quote * (1 - 0.0010) * (1 - 0.0004) / average_cost - 1`:
  inclui somente a perna de saida ainda nao paga.

A funcao documenta expressamente que subtrair o round trip inteiro novamente
duplicaria a entrada:
[`r2d2_strategy.py:L98-L130`](https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/blob/39ff427fd2f1fa0f42141776921a63651508495f/c3po/backend/app/r2d2_strategy.py#L98-L130).
O SELL real usa os mesmos 10 bps + 4 bps em
[`r2d2.py:L3339-L3364`](https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/blob/39ff427fd2f1fa0f42141776921a63651508495f/c3po/backend/app/r2d2.py#L3339-L3364).

Na cotacao inicial, o liquido realizavel e aproximadamente `-0.279608%`: a
entrada ja esta dentro do custo medio e a funcao acrescenta uma unica perna de
saida. O teste `test_entry_cost_is_counted_once_in_average_cost_and_once_on_exit`
pina os dois numeros e recusa a subtracao duplicada de 28 bps.

## 3. Precedencia completa da politica vigente

### 3.0 Matriz de parametros congelados

| Parametro | Valor no commit congelado |
| --- | ---: |
| risco por trade para sizing | 0,02% do NAV |
| hard loss base / teto ATR-adjusted | 0,65% / 1,50% liquido |
| soft loss base / teto ATR-adjusted | 0,25% / 0,70% liquido |
| hold minimo organico / hold minimo de rotacao | 5 min / 10 min |
| failed entry | 3 min, -0,30% liquido, 3/5 votos |
| small-gain protection | +0,30% liquido, 3/5 votos, 2 reviews |
| trigger minimo de lucro | max(0,65%, 1R da posicao) |
| weekly harvest | 70% da quantidade |
| EOD | ultimos 30 s e somente `net>0` |
| stagnation | 180 min, `net<0,50%`, tecnico `<45` |
| slippage/fee por perna US | 0,10% / 0,04% |
| round trip declarado / edge intraday minimo | 0,28% / 0,55% |
| quote maxima para BUY | 90 s |
| tick maximo do watcher / ATR maximo do watcher | 10 s / 30 s |
| grace de quote atrasada / trust bound | 3 min / 30 min |
| cooldown regular de reentrada | 8 min |
| horizonte terminal obrigatorio | nenhum; checkpoint de 90 dias nao termina o experimento |

Constantes da estrategia:
[`r2d2_strategy.py:L35-L76`](https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/blob/39ff427fd2f1fa0f42141776921a63651508495f/c3po/backend/app/r2d2_strategy.py#L35-L76).
Defaults operacionais:
[`config.py:L143-L170`](https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/blob/39ff427fd2f1fa0f42141776921a63651508495f/c3po/backend/app/config.py#L143-L170).

### 3.1 Concorrencia e cadencias

Ha tres avaliadores de risco, todos serializados pelo mesmo
`risk_evaluation_lock`. Entre threads nao existe prioridade fixa: vence quem
adquire o lock primeiro; depois, cada avaliador respeita sua propria precedencia.
Ao obter o lock, a lista de posicoes e relida para impedir uma segunda venda de
uma posicao ja encerrada.

| Avaliador | Cadencia configurada | Escopo |
| --- | ---: | --- |
| Fast risk watcher | 1 s em producao; clamp de 0,5 a 2 s | Cache do WebSocket, hard stop, EOD positivo e chandelier de dois ticks. |
| Dedicated risk monitor | 3 s em producao; clamp de 2 a 5 s | Cascade tecnico completo. |
| Loop principal | 20 s para risco; scan de entradas a cada 60 s | Cascade completo antes de qualquer scan/rotacao. |

Fontes: loops em
[`r2d2_worker.py:L47-L75`](https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/blob/39ff427fd2f1fa0f42141776921a63651508495f/c3po/backend/app/r2d2_worker.py#L47-L75)
e orquestracao em
[`r2d2_worker.py:L150-L180`](https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/blob/39ff427fd2f1fa0f42141776921a63651508495f/c3po/backend/app/r2d2_worker.py#L150-L180).
Os defaults versionados dos dois monitores eram `false`; a evidencia operacional
de 24/08 confirma que ambos estavam habilitados no ambiente.

### 3.2 Fast risk watcher

Dentro do watcher, a ordem e:

1. exigir tick do stream com idade maxima de 10 s;
2. recusar tick anomalo;
3. vender se `quote <= hard_stop_price_local`;
4. se nao houve hard stop, vender no T-30s apenas quando o liquido estimado for
   estritamente positivo;
5. se ATR estiver ausente ou tiver mais de 30 s, atualizar somente high-water e
   degradar para hard-stop-only;
6. com ATR fresco, atualizar high-water/chandelier e exigir dois ticks frescos
   distintos abaixo do chandelier antes da venda.

O watcher nao calcula VWAP, EMA ou `defense_streak`. Codigo:
[`r2d2.py:L1708-L1887`](https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/blob/39ff427fd2f1fa0f42141776921a63651508495f/c3po/backend/app/r2d2.py#L1708-L1887).

### 3.3 Guardas antes do cascade completo

O risk monitor e o loop principal passam, nesta ordem, por:

1. **B3 retirement:** durante a sessao B3, qualquer posicao legada B3 e vendida;
2. **quote ausente/nao live:** inicia grace de 3 min; depois dela, so usa a
   cotacao atrasada no hard stop se o `as_of` proprio tiver no maximo 30 min;
   dado mais antigo exige revisao manual e nao produz fill;
3. **anomaly guard:** marca `validating quote` e nao age no primeiro tick
   suspeito;
4. **snapshot tecnico:** falha degrada para `stale`/`unavailable`; nao transforma
   dado velho em sinal tecnico live;
5. calculo de high-water, ATR, votos, defesa, weekly conviction e chamada do
   cascade puro.

Fontes:
[`r2d2.py:L1908-L2130`](https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/blob/39ff427fd2f1fa0f42141776921a63651508495f/c3po/backend/app/r2d2.py#L1908-L2130).

### 3.4 Cascade organico, em ordem estrita

O primeiro item verdadeiro vence. A implementacao congelada esta em
[`r2d2_strategy.py:L614-L829`](https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/blob/39ff427fd2f1fa0f42141776921a63651508495f/c3po/backend/app/r2d2_strategy.py#L614-L829).

| # | Regra e condicao |
| ---: | --- |
| 1 | **Immediate hard stop:** `net <= -effective_max_loss`, onde `effective=max(0,65%, min(1,50%, 2*ATR%))`. Saida total. |
| 2 | **EOD positive:** de T-30s ate 16:00 ET, `net > 0`. Saida total, inclusive weekly conviction. Posicao negativa nao e liquidada apenas pelo relogio. |
| 3 | **Failed entry:** `held>=3 min`, `net<=-0,30%` e pelo menos 3/5 votos: abaixo de VWAP, abaixo de EMA8, momentum 15m negativo, momentum 30m negativo, MACD fraco. |
| 4 | **Critical defense:** defesa critica (`score>=82` ou breakdown com fluxo vendedor e RVOL suficiente). |
| 5 | **Confirmed defense:** `held>=5 min`, defesa live `score>=72`, `defense_streak>=2`. |
| 6 | **Persisted after reduction:** `held>=5 min`, ja houve reducao, defesa live `score>=58`, `defense_streak>=3`. Vende o restante. |
| 7 | **Defensive loss:** `net<=-soft_threshold`, defesa live `score>=45`, `streak>=2`; `soft=max(0,25%, min(0,70%, 0,4*ATR%))`. |
| 8 | **Adaptive stop:** quote abaixo do maior stop calculado, defesa live `score>=45`, duas confirmacoes. |
| 9 | **Weekly lock antes da primeira colheita:** weekly conviction, pico >=1R e pullback para a banda de lock. Saida total. |
| 10 | **Weekly harvest:** weekly conviction, `net>=1R`; realiza exatamente 70%, uma vez. |
| 11 | **Weekly remainder lock:** depois da colheita, pico >=1R e pullback para a banda. Saida do restante. |
| 12 | **Tactical 1R:** sem weekly conviction, `held>=5 min`, `net>=max(0,65%, effective_max_loss)`. Saida total. |
| 13 | **Armed profit lock:** sem weekly conviction, pico >=1R e pullback para a banda. |
| 14 | **Early tactical:** `held>=5 min`, `net>=0,75%`, pelo menos um voto bearish e tecnico `<60`. |
| 15 | **Momentum reversal harvest:** `held>=5 min`, `net>=2,50%`, pelo menos tres votos bearish. |
| 16 | **Early profit:** `held>=5 min`, `net>=1,00%`, pelo menos dois votos bearish e tecnico `<55`. |
| 17 | **Small-gain protection:** `net>=0,30%`, pelo menos 3/5 sinais de timing revertidos, `gain_protection_streak>=2`; sem minimo de tempo. |
| 18 | **Trend breakdown:** `held>=5 min`, tecnico `<32`, pelo menos quatro votos bearish. |
| 19 | **Progressive technical-defense reduction:** `held>=5 min`, `net<1R`, nenhuma reducao anterior, defesa live `score>=55`, `defense_streak>=2`; vende exatamente 50%. |
| 20 | **Stagnation:** `held>=180 min`, `net<0,50%`, tecnico `<45`. Saida total. |

Se nenhuma venda dispara, o estado visual segue a ordem: `stop armed`,
`defense reduction armed`, `technical defense watch`, `weekly conviction hold`,
`profit protected`, `profit armed`, `hold`.

### 3.5 Saidas fora do cascade

- **Opportunity-cost rotation:** so durante scan de entrada, carteira cheia,
  incumbent com pelo menos 10 min, sem weekly conviction, candidato aprovado e
  vantagem minima de 6 pontos; vende o incumbent antes do BUY substituto.
  [`r2d2.py:L3129-L3197`](https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/blob/39ff427fd2f1fa0f42141776921a63651508495f/c3po/backend/app/r2d2.py#L3129-L3197).
- **Operator wind-down/correction:** caminhos administrativos, nao regras
  organicas. Entram na contabilidade conforme seu contrato e sao excluidos das
  metricas de estrategia.
- **Horizonte:** nao existe liquidacao obrigatoria por idade maxima. O checkpoint
  de 90 dias nao encerra o experimento; a unica regra temporal organica e a
  stagnation de 180 min, que tambem exige `net<0,50%` e tecnico `<45`.

## 4. Indicadores e defesa tecnica

Os indicadores usam barras de 5 minutos e exigem ao menos 35 barras. As
definicoes estao em
[`r2d2_strategy.py:L154-L310`](https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/blob/39ff427fd2f1fa0f42141776921a63651508495f/c3po/backend/app/r2d2_strategy.py#L154-L310).

- **EMA8/20/50:** semente no primeiro close e atualizacao
  `ema += (close-ema)*2/(period+1)`.
- **VWAP:** media do preco tipico `(high+low+close)/3`, ponderada por volume,
  somente nas barras da sessao corrente; sem volume, media dos closes.
- **ATR(14):** media de 14 true ranges, cada um sendo o maximo entre
  `high-low`, `abs(high-prev_close)` e `abs(low-prev_close)`.
- **failed breakout:** o high das ultimas seis barras supera o high das barras
  mais antigas da janela de 21, mas o ultimo close volta abaixo desse high e o
  momentum de 15 min fica negativo.

O score de defesa soma os seguintes pesos
([`r2d2_strategy.py:L326-L396`](https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/blob/39ff427fd2f1fa0f42141776921a63651508495f/c3po/backend/app/r2d2_strategy.py#L326-L396)):

| Evidencia | Peso |
| --- | ---: |
| preco abaixo de VWAP / abaixo de EMA8 | 6 / 6 |
| EMA8 abaixo de EMA20 / EMA20 abaixo de EMA50 | 10 / 8 |
| EMA8 caindo / EMA20 caindo / regime bearish | 6 / 6 / 8 |
| breakdown / failed breakout / lower lows | 22 / 16 / 14 |
| MACD enfraquecendo | 8 |
| momentum 15m / 30m / 60m negativo | 4 / 6 / 6 |
| RSI<38 / distribuicao / selloff em RVOL alto | 4 / 9 / 8 |
| OBV caindo / volume vendedor dominante | 4 / 6 |
| drawdown >=0,75 ATR / >=1,25 ATR | 4 / 5 |
| underperformance <=-0,50 / <=-1,00 p.p. | 4 / 4 |

Se o snapshot e live, `defense_streak` sobe quando score>=45; caso contrario,
cai apenas um ponto ate zero. Portanto, o texto `after N reviews` representa o
contador persistido, nao necessariamente N leituras consecutivas sem uma unica
interrupcao. Severidade: exit em critica ou score>=72; reduce >=55; watch >=40.

## 5. Stop: formacao e evolucao

### 5.1 Stop tecnico inicial congelado

Na confirmacao tecnica:

```text
distance = min(price*0,65%, max(ATR*0,45, price*0,40%))
entry_stop = price - distance
```

Fonte congelada:
[`r2d2.py:L2540-L2623`](https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/blob/39ff427fd2f1fa0f42141776921a63651508495f/c3po/backend/app/r2d2.py#L2540-L2623).
No BUY, o codigo atualizava a cotacao antes do fill, mas fazia
`max(stop_tecnico_antigo, hard_stop_cost_aware)` sem recalcular o primeiro termo:
[`r2d2.py:L3198-L3297`](https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/blob/39ff427fd2f1fa0f42141776921a63651508495f/c3po/backend/app/r2d2.py#L3198-L3297).

### 5.2 Stop durante a posicao

No cascade completo, o nivel usado e o maximo entre:

1. stop persistido;
2. chandelier `high_water - 2,5*ATR`, com ATR minimo de `0,40%` do preco;
3. hard stop cost-aware que realiza no maximo o limite liquido ATR-adjusted;
4. locks de pico: com pico liquido >=1%, piso `average_cost*1,003`; >=4%,
   piso `average_cost*1,015` e trailing mais largo; >=8%, piso
   `average_cost*1,04` e trailing mais curto.

Fontes:
[`r2d2_strategy.py:L632-L688`](https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/blob/39ff427fd2f1fa0f42141776921a63651508495f/c3po/backend/app/r2d2_strategy.py#L632-L688).

## 6. Casos nomeados

### 6.1 LOW, 24/08 11:34 BRT

Ledger:

- BUY `979a14fa-dde8-4761-bf45-8b57ee4c5a2c`;
- cotacao tecnica anterior inferida exatamente do stop: `218.26344/0.996 = 219.14`;
- cotacao fresca usada na entrada: `218.39` as 13:56:00.142Z;
- fill: `218.60839`, exatamente +10 bps;
- fee: `US$ 11.755010`; custo medio: `218.695833353`;
- high-water factual: `219.815`; pico liquido `+0.3711%`;
- SELL `04d37903-a6c7-46b-9e70-d35706664f0d`, realizado
  `-US$ 107.037613`.

Reason completo:

> Fast risk watcher hard_stop exit at mark -0.22%, estimated net -0.36% on fresh tick 2026-08-24T14:34:35.078000+00:00; level 218.2634.

O nivel nao veio do high-water: `219.14*0.996 = 218.26344`. O BUY refrescou o
sinal para `218.39`, mas manteve o stop calculado antes. O buffer factual foi
`(218.39-218.26344)/218.39 = 5,80 bps`; arredondado visualmente, parecia cerca
de 8 bps. O watcher vendeu corretamente contra o nivel que recebeu; o defeito
estava na formacao do nivel.

**Remediacao:** `entry_stop_quote_price` centraliza a formula. `_buy` agora a
reexecuta sobre a cotacao de fill e so depois compara com o hard stop
cost-aware. Para LOW, o termo tecnico seria `217.51644`, o hard stop liquido
`217.57883`, e o nivel final `217.57883`, preservando aproximadamente 37,14 bps
entre a cotacao fresca e o stop e o limite liquido de -0,65%.

### 6.2 EHC, 24/08 11:48 BRT

Ledger:

- BUY `dcc8d3a5-8208-4a5b-b556-186b5aa862e0`;
- sinal `122.185` as 14:46:48.520Z;
- fill `122.307185 = 122.185*1.001`;
- fee `US$ 11.747361`; custo medio `122.356107876`;
- stop persistido `121.731168116`;
- SELL `1f3bfde0-2d1d-43f6-83e0-5eca90c2f235`, realizado
  `-US$ 221.224051`.

**Veredito obrigatorio:** nenhuma das tres hipoteses descreve a diferenca de
`122.19` para `121.73`, porque `121.73` nao era cotacao. Era o valor da coluna
**Stop**; o estado textual ao lado era `awaiting live quote`. O layout congelado
declara a coluna Stop em
[`page.tsx:L3522`](https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/blob/39ff427fd2f1fa0f42141776921a63651508495f/c3po/frontend/app/page.tsx#L3522)
e renderiza `stop_price_local` em
[`page.tsx:L3545`](https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/blob/39ff427fd2f1fa0f42141776921a63651508495f/c3po/frontend/app/page.tsx#L3545).
Nao ha staleness de tela nem defasagem de fonte demonstrada no preco de fill, e
nao ha defeito no modelo de fill: os 10 bps sao exatos. O stop de EHC foi
calculado sobre base anterior de aproximadamente `122.22005`; essa pequena
inconsistencia e da mesma classe de LOW e fica coberta pela remediacao.

### 6.3 O suposto `-US$ 39.981,68` de 21/08

O numero aparece na fixture da regressao de NAV como valor historico de
snapshot. A consulta do ledger canonico encontrou:

- 117 episodios fechados;
- 129 pernas SELL;
- soma nao arredondada `-US$ 10.374,558379`;
- valor contabil arredondado `-US$ 10.374,56`.

A diferenca para `-US$ 39.981,68` e `-US$ 29.607,121621` e nao corresponde a
episodios do ledger. A fixture agora preserva o snapshot errado de proposito,
mas usa a serie factual de SELLs para provar que a trilha contabil ignora o
snapshot marcado. A decomposicao com simbolo, nome, timestamps, pernas e P&L de
cada episodio esta no CSV de evidencia. As linhas exibidas individualmente a
centavos somam `-US$ 10.374,49`; a diferenca de US$ 0,07 para o total contabil e
somente arredondamento independente de 117 valores, nao discrepancia de ledger.

### 6.4 CROX, 24/08

- BUY: sinal `124.47`, fill `124.59447`, custo medio `124.644307788`;
- high-water `125.64`, pico liquido `+0.6577%`;
- 12:01 BRT: print em hold, mark aproximadamente `+0.666%`;
- 12:18:50 BRT: 105,63 de 211,26 acoes vendidas, exatamente 50%, P&L
  `-US$ 25.738118`;
- 12:21:43 BRT: 105,63 restantes vendidas, P&L `-US$ 4.114276`;
- total: `-US$ 29.852394`.

Primeiro reason:

> Progressive technical-defense reduction: 50% of the position released at mark -0.06%, estimated net -0.20% after 7 reviews; price below VWAP; price below EMA8; failed breakout.

A defesa ficou actionable com score>=55 e contador>=2, abaixo de 1R, depois do
hold minimo, sem reducao anterior: regra 19. Ela sempre vende 50% uma unica vez
e grava `defense_reductions=1`. Na avaliacao posterior, a regra 6 aparece antes
da regra 19 e, com score>=58 e contador>=3, vende todo o restante. Nao existe
sequencia 50% -> 25% -> 12,5%.

O contador 7 foi alimentado apenas pelos avaliadores do cascade completo
(dedicated monitor/main loop); o watcher de 1 s nao conta reviews. O estado
`hold` no print nao demonstrava que a defesa estava desarmada: o painel mostrava
somente o `decision_state`, enquanto o contador persistido ja crescia. A PR #211
passou a expor esse estado tecnico, sem alterar a decisao.

## 7. Drift do mandato

O commit congelado dizia:

```text
full_exit_reentry_policy = blocked until the next Sao Paulo trading date
```

Mas `loss_exit_on_session` bloqueava somente SELL com P&L `<=0`, no mesmo dia de
Sao Paulo, excluindo corrections e operator wind-down; profit exits continuavam
elegiveis depois do cooldown regular. Codigo congelado:
[`r2d2.py:L1056-L1090`](https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/blob/39ff427fd2f1fa0f42141776921a63651508495f/c3po/backend/app/r2d2.py#L1056-L1090).

O texto passa a ser:

```text
loss exits block same-symbol re-entry for the rest of the Sao Paulo session;
profit exits remain subject only to the regular cooldown
```

E uma correcao documental do mandato; a regra executavel nao muda.

## 8. Criterio de pronto

Os quatro casos nomeados estao explicados por evidencia e codigo:

- LOW: nivel e defeito de base temporal identificados, com regressao e fix;
- EHC: sinal/fill/stop reconciliados e veredito obrigatorio emitido;
- 21/08: premissa falsa isolada e ledger real decomposto por episodio;
- CROX: duas pernas, contadores, indicadores, fracao e precedencia explicados.

O Entregavel 0 esta pronto para auditoria. O runner do estudo continua bloqueado
ate a aprovacao explicita deste documento e das correcoes associadas.
