# R2D2 V2 — ESQUELETO DE ESPECIFICAÇÃO (V0 rev 3, com os comentários do Codex 5560149112 incorporados; não é contrato congelado)

**Por quê uma V2:** a v1 foi refutada por decisão do dono (ato de 06/09/2026, breaker acionado às 12:08 BRT). O que foi medido em três semanas de paper: p(net₀+1R antes de −1R) em torno de 46 % nas 8 sessões do M1 (leitura interina), episódio mediano que nunca fica positivo líquido (MFE mediano −0,11 %), 60–75 % dos stops em menos de 30 minutos, e nenhuma política de saída intradiária com melhora mensurável (épocas 1 e 2, piloto). O stop por ATR diário com posição multi-dia (D') reduziu a perda pontual com incerteza ampla e cauda pesada: motiva uma hipótese, não demonstra causalidade.

**Princípio:** a V2 não é um ajuste da v1. Ela troca as três coisas que a evidência aponta: **seleção/qualidade da entrada**, **geometria do stop** e **horizonte**. Infra, ledger, fricção modelada, gates G1/G2/G3, bootstrap por sessão, relay e auditoria cruzada são reaproveitados. **A v1 não é reaberta para alimentar nada** (A3(a) escolhida; não há baseline v1 concorrente).

## 1. Dados já disponíveis (inventário do Codex sobre o M1, época 2)

- Presentes em **268/268** entradas: `composite_score`, `fundamental_score`, `technical_score`, `risk_score` (finitos no BUY), stop, ATR intradiário, VWAP/EMA8, rota, timestamp da cotação. Regime QQQ: 235/268. Fontes causais do adapter: 262/268.
- Presença não é poder discriminante nem dispersão. Liquidez, spread e rank exigem inventário específico. `risk_score` não é distância de buy-in; ATR intradiário não é ATR Wilder diário D−1.
- População, fronteira, corte, hashes e exclusões: os do M1 (268 → 264 medições → 244 resolvidas + 20 censuradas). Os arquivos locais só têm agregados: quartis × outcomes exigem nova projeção dos dados persistidos, após protocolo e runner auditados.

## 2. Análises pré-registradas sobre dados já coletados (antes de qualquer shadow)

Protocolo detalhado em `R2D2_V2_PROTOCOLO_ANALISE_1_2026-09-06.md`. Resumo:

1. **Passo 1 — inventário dos inputs, sem outcomes:** cobertura, valores distintos, empates, timestamps e cortes de quartil (nearest-rank; empates ficam juntos; cortes repetidos não forçam quatro células) para `composite_score` e os três sub-scores. Scores atuais, backfill e substituição de campos ausentes ficam fora.
2. **Passo 2 — pergunta primária exploratória:** `composite_score` **Q4 − Q1** em p(net₀+1R antes de net₀−1R), mantendo o R do BUY histórico, as quatro categorias, custos e censura do estimador do `ENTRY_QUALITY_STUDY_V1`; contrastes pareados por sessão, seed 20260824, 10.000 réplicas. Sub-scores em três tabelas secundárias; nenhuma combinação arbitrária. Oito sessões continuam PILOTO; nada disso altera o endpoint primário da spec V1 assinada.
3. **Passo 3 — seleção e congelamento de UMA política candidata completa** (filtro de entrada + stop + horizonte + sizing + regras de saída + calendário) antes do shadow. Um LCB marginal escolhido entre scores × quartis × parâmetros não certifica o filtro: a V2 carrega um orçamento de erro explícito entre candidatos, endpoints e leituras.

## 3. Hipóteses a pré-registrar (ajustadas)

| # | Hipótese | Métrica pré-registrada | Regra de abandono (nome explícito: **falha de certificação**, não refutação estatística) |
|---|---|---|---|
| H1 | O filtro de entrada congelado tem p(net₀+1R antes de −1R) com LCB 98,75 % > 50 % | população/estimador do `ENTRY_QUALITY_STUDY_V1`, bootstrap por sessão, seed 20260824 | `V2_CERTIFICATION_FAILED_H1` se LCB ≤ 50 % na 15.ª sessão de shadow |
| H2 | Stop por volatilidade diária (ATR(14) Wilder, D−1, múltiplo fixado) reduz stops de ruído **a risco monetário equivalente** | % de stops < 30 min; MAE/MFE líquidos; perdas e gaps por episódio, comparados a risco por posição igual | `V2_CERTIFICATION_FAILED_H2` se a redução não aparecer a risco equivalente ou se a cauda de gaps exceder o orçamento |
| H3 | Horizonte multi-dia (N sessões fixado) com saída por regra fechada tem expectância líquida por episódio ≥ 0 | expectância líquida por episódio e por sessão; DD; trilha virtual determinística | `V2_CERTIFICATION_FAILED_H3` se UCB 98,75 % da expectância < 0 na leitura decisória |
| H4 | O menor giro compensa o carrego overnight | custo total/NAV; distribuição de gaps de abertura na coorte | cauda de gap acima do orçamento de risco |

## 4. O que a V2 precisa fixar antes de congelar (concreto, não faixas)

1. **Universo e liquidez:** piso de liquidez (manter 15 M/dia ou subir), spread máximo, exclusões (earnings, eventos).
2. **Filtro de entrada:** definido pelo resultado do §2, um só; sem busca posterior.
3. **Stop e sizing:** múltiplo do ATR(14) Wilder diário D−1 (candidato inicial 1,5, de D'); risco por posição em fração de NAV; tamanho derivado do stop; limites por nome/mercado/exposição herdados da V28.
4. **Horizonte e saídas:** N sessões; saída por stop, alvo em múltiplos de R, tempo, e fechamento em evento; sem gestão intradiária discricionária.
5. **Mercados e sessão:** NASDAQ/NYSE no regular; B3 fora (feed atrasado).
6. **Overnight:** orçamento de risco por gap, exclusão antes de earnings, limite de exposição líquida overnight.
7. **Custos:** o mesmo modelo de fricção do paper (taxas e slippage por mercado).

## 5. Integração do shadow da V2 (achado do Codex)

- `r2d2.py:2815` retorna quando `entries_paused` é verdadeiro, **antes** do scan e da gravação de candidatos/adapter; e `r2d2_shadow_candidate_worker.py` só calcula outcomes de sessões pendentes, não gera candidatos. Logo, reaproveitar o worker sozinho não inicia a coleta da V2.
- Desenho: **gerador/registro próprios da V2**, com `policy_epoch` e versão separados (`R2D2-V2-SHADOW-…`), sem BUY, sem rotação, sem tocar posições ou ordens; trilha virtual determinística da carteira multi-dia (candidatos maturam N sessões); outcomes por barreira ±R medidos em barras pelo mesmo motor.
- Provas obrigatórias antes do "no ar": v1 pausada continua pausada; candidatos V2 novos gravados com epoch/versão próprios; nenhuma posição/ordem alterada; testes e auditoria cruzada.

## 6. Método (o que não muda)

- Pré-registro a seis mãos com hash; spec congelada; emendas só por rito.
- Shadow prospectivo primeiro; **≥ 15 sessões** mais a maturação dos últimos candidatos (N sessões) antes de qualquer paper com posição.
- Gates G1/G2/G3; contabilidade ao centavo; fricção modelada idêntica.
- Critério de morte próprio (M1/M2/M3 adaptados, com nomes de falha de certificação) pré-registrado antes da primeira sessão.
- Sem pooling com a v1; a v1 é evidência histórica.

## 7. Calendário (acelerado por ordem do dono: "colocar a V2 para funcionar o quanto antes")

- **06–07/09:** protocolo da análise 1 auditado (esta versão); Codex implementa o runner somente leitura da projeção (inventário dos inputs → passo 1 publicado; passo 2 só após o passo 1 auditado); Fable audita.
- **08–09/09:** resultados dos passos 1–2; mesa fixa o §4; spec V2 V1 congelada a seis mãos com a política candidata única.
- **09–11/09:** gerador/registro V2 implementado com auditoria cruzada (§5); deploy fora do pregão; shadow começa na primeira sessão após o deploy, **se os gates fecharem**.
- **≥ 15 sessões + maturação N:** leitura decisória; só então paper com posição.

## 8. Assinaturas

Documento de trabalho. Passa a spec quando as três partes assinarem uma versão congelada com hash.
