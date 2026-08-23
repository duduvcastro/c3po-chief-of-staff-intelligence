# Valuation V2 — Blueprint V1

**Status:** shadow em produção (nenhum consumidor de decisão) · **Motor:** engine v2 · **Assinaturas:** Fable (design/auditoria) + Codex (auditoria cruzada/operação) · **Dono:** Dudu · **Congelado em:** 2026-08-23

Motivação (dono): "nossos valuations ficam muito distantes dos consensos de mercado, pra cima e pra baixo; não confio no modelo atual, e ele impacta o R2D2 no fim do dia."

---

## 1. Princípios congelados

- **P1 — Toda âncora é externa e verificável.** Peers reais (FMP), estimativas de consenso por ano fiscal (FY1/FY2), banda histórica da própria empresa (10 anos de ratios), consenso de preço-alvo com recência.
- **P2 — Nenhum número livre.** Múltiplo justo vem de peers (amostra ≥ 4, winsorizada), mediana setorial ou histórico próprio (≥ 5 anos) — nesta ordem (ladder registrado por ativo). Sem nenhuma âncora, o modelo declara-se incapaz (`low_conviction`), nunca chuta constante.
- **P3 — Reverse DCF, nunca DCF de premissa.** O sinal resolve o crescimento que o preço atual implica e o compara com o crescimento do consenso: `price_equivalent = price × (1+g_consenso)/(1+g_implícito)`, ambos presos ao intervalo do solver [−25%, +40%] — limitado por construção, impossível de explodir. Convenção de 1 ano (subestima gaps persistentes — direção de erro deliberada); `growth_gap` gravado para a calibração decidir variante composta em fronteira de versão.
- **P4 — Divergência vs. consenso é OUTPUT medido, com bandas congeladas.** Régua vinculante: TP INTERNO vs. consenso (medir o final encolhido deixaria o shrink lavar a divergência). Bandas: **> 30%** → `low_conviction` + shrink máximo (50%) para o consenso; **15–30%** → nota com atribuição; sem consenso e sem âncora externa → incapaz por construção. Meta de aprovação do V2: **p50 ≤ 15% e p90 ≤ 30% na régua interna, por mercado e por perfil.** As bandas não se movem para acomodar o modelo.
- **P5 — Calibração empírica contínua.** Peso do blend com consenso hoje herda a política V1 (20–35% por contagem de analistas; 50% em low_conviction) — rotulado `v1_policy_pending_v2_3_calibration`. Recalibração só em fronteira de versão com o shadow acumulado, nunca silenciosa.
- **P6 — Rollout pelo playbook de consumidores.** Shadow → diff de distribuição POR CONSUMIDOR → troca por consumidor a seis mãos, PDF primeiro (risco zero para trading), gates do screener depois, `pretrade_rank` por último. A #129 caiu por big-bang; o V2 não repete.
- **Cíclicos: lucro de meio de ciclo (mediana ≤ 7 anos de EPS histórico) obrigatório** como base de earnings power, histórico-por-P/E e reverse DCF. Pico TTM/NTM **nunca** entra — nem como fallback penalizado. Sem meio de ciclo, esses modelos ficam indisponíveis.

## 2. Arquitetura

```
V2.1 dados (FMP)            V2.2 motor (puro)            V2.3 shadow             V2.4 consumidores
────────────────            ─────────────────            ───────────             ─────────────────
stock-peers          ──►    4 modelos/ativo:      ──►    V1 × V2 lado a   ──►    PDF: faixa shadow
estimates por FY            • comps de peers             lado, réguas            (informacional, ATIVO)
ratios 10a                  • banda histórica            interna+final,          ───────────────────
key-metrics 10a             • earnings power             p50/p90 por             gates screener (BLOQUEADO)
(1×/dia, 01:00–08:00)       • reverse DCF                mercado/perfil          pretrade_rank (BLOQUEADO)
snapshot por mercado        financials: RIM/DDM/         1×/dia + backfill       troca só a seis mãos com
com coverage por âncora     P/B-vs-ROE                   manual                  diff de distribuição
```

- **Módulos:** `valuation_v2_data.py` (V2.1) · `valuation_v2_engine.py` (V2.2, `ENGINE_VERSION`) · `valuation_v2_shadow.py` (V2.3) · faixa no `one_pager_pdf.py` (V2.4, informacional).
- **Peers resolvidos de snapshots persistidos** (universos dos screeners + Chewie full-listing) — o shadow custa zero chamadas de provedor além da curva B3. Peers `.SA` resolvidos por símbolo canônico.
- **Risk-free:** B3 = ponto da curva Tesouro prefixado (Brapi) mais próximo do horizonte de 5 anos do modelo (substitui o desconto flat de 18% do V1, causa-prima do viés B3); US = fallback 4,2% até o shadow ganhar feed de Treasury. ERP 5,5%; clamps de desconto US 6–16% / BR 10–22%; terminal US 3% / BR 5,5%.
- **Anti-dupla-contagem:** P/E pertence ao earnings power (base casada com o basis do múltiplo: forward→NTM ponderado FY1/FY2, trailing→trailing, confiabilidade ≤ 0,7 no trailing); peer comps usa só EV/EBITDA + P/B; earnings power deduplicado contra own-history quando o múltiplo justo veio de lá. Amostra de peers = MÍNIMO das amostras usadas; dispersão = MÁXIMO.

## 3. Baseline V2.0 (medição read-only, 23/08/2026 — régua interna V1)

| Mercado | p50 | p90 | Viés mediano assinado |
|---|---|---|---|
| B3 | 26,80% | 48,36% | −23,90% |
| NASDAQ | 24,04% | 58,05% | −8,55% |
| NYSE | 23,69% | 76,03% | +7,18% |

Top-20 divergências: todas para cima, 16/20 puxadas por Momentum de Lucro + Qualidade/FCF (vetor único do V1), dominadas por cíclicos. Casos acompanhados: HPQ 312%, CPB 213%, MPC 185%, CF 172%, CMCSA 176% (interno V1 na medição do shadow).

## 4. Primeira medição do shadow (23/08/2026 — engine v2, 693 ativos / 670 com consenso)

| Mercado | Interno V1→V2 p50/p90 | Final V1→V2 p50/p90 |
|---|---|---|
| B3 | 37,63/70,35% → **22,32/56,98%** | 28,64/49,85% → **12,29/28,49%** ✅ |
| NASDAQ | 35,07/81,84% → **33,66/73,29%** | 24,10/59,69% → 17,68/36,64% |
| NYSE | 32,24/106,01% → **24,60/58,48%** | 23,71/76,06% → 15,38/29,23% |
| **Total** | 34,26/87,01% → **27,98/63,52%** | 24,20/66,04% → **15,87/31,76%** |

**Veredito (co-assinado Fable+Codex): melhora real e material; REPROVADO na régua interna nos 3 mercados → V2 segue proibido de substituir o TP oficial.** 529/693 em low_conviction (o TP final é majoritariamente consenso encolhido — por isso o final não conta para aprovação).

- **Predição B3 (curva do Tesouro)**: viés interno −34,48% → **−15,18%** (final −7,70%). Parcialmente confirmada — a curva explica ~19 p.p.; resíduo fora da banda prevista → investigação devida (ver §5).
- **Vitórias confirmadas**: os 5 acompanhados comprimiram todos; **CF 172% → 5,9%** (meio de ciclo funcionou); MSFT com P4 interno 1,8%.
- **Padrões de falha**: B3 dominada por `own_history` (RECV3 158%, GOAU4 111%, INTB3 105%); EUA por "barato vs. peers" (CHTR 145%, PDD 138%, CPB 135%, BIDU 130%, NVO 138%, HPQ 116%).

## 5. Fila do engine v3 (mudanças SÓ em fronteira de versão, com re-medição completa)

1. **Comps ajustados por quartil de ROE/crescimento** — estava na spec congelada e ficou fora do v2; a medição apontou exatamente para ele (padrão "barato vs. peers" nos EUA).
2. **Âncora histórica B3 condicionada a regime de juros** — hipótese registrada: mediana crua de 10 anos ancora ao regime de Selic alta e puxa TPs para baixo (resíduo de −15 p.p. do viés). Candidatos: janela condicionada a regime, shrink para mediana setorial, ponderação de recência. Decisão com dado de calibração.
3. **Reverse DCF composto** (`ratio^k` com k calibrado) — se o `growth_gap` acumulado do shadow justificar.
4. **Feed de Treasury US** no shadow (substituir o fallback 4,2%).
5. **Recalibração do peso de consenso (P5)** com a série do shadow.

## 6. Governança e estado

- **Bloqueados:** troca do TP oficial em QUALQUER consumidor; recalibração silenciosa; afrouxamento de bandas.
- **Ativo:** shadow 1×/dia (janela 01:00–08:00, após V2.1) + faixa informacional no One Pager (lookup por mercado, nunca falha o PDF, rótulo "não substitui o TP oficial").
- **Watchlist permanente:** HPQ, CPB, MPC, CF, CMCSA (baseline) + top-5 internos por mercado da medição de 23/08.
- **Critério de avanço para V2.4:** régua interna ≤ 15%/30% por mercado E perfil no shadow acumulado → troca por consumidor (PDF primeiro), a seis mãos, com diff de distribuição por consumidor.
- **Trilha de PRs:** #195 (dados) · #196 (motor+shadow, auditoria cruzada 866ec45) · #197 (faixa PDF, 8752a5e) · #198 (redação de URLs em logs). Snapshots: `valuation_v2_data`, `valuation_v2_shadow` (métodologia versionada; `ENGINE_VERSION` no resultado).

*Histórico: a metodologia real de #128/#129 (DCF/RIM/DDM/Comps com scores de confiabilidade) foi revertida por big-bang em 21/08; o V2 recuperou RIM/DDM/low_conviction dela dentro do playbook de consumidores. Este blueprint é V1; qualquer alteração de princípio ou banda exige nova versão deste arquivo, a seis mãos.*
