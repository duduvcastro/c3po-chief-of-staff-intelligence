# Estudo de Qualidade de Entrada — Spec V1 (congelada)

**Status:** congelada a seis mãos em 25/08/2026 · incorpora integralmente as dez condições do Codex e a Emenda 1 · co-assinada por Codex, Fable e Dudu · **Escopo:** pesquisa read-only (exceto item 9: PR do adapter, auditada em separado, default-off) · **Toca produção:** nada além da observabilidade e do estado auditado de retomada autorizados pela Emenda 1 · **APIs do adapter:** zero · **Origem:** diagnóstico de 24/08/2026 — 41/59 perdas nunca líquidas-positivas (74% dos dólares perdidos). Formulação do dono: *"nosso maior problema é o que compramos, por que compramos e a que preço compramos."*

## Emenda 1 — retomada de 26/08/2026

A implementação e ativação do `entry_score_adapter` (§9) fica antecipada para a retomada de entradas de 26/08/2026, precedendo o runner do estudo de saída. Nada mais se move: parâmetros, eixos, hipóteses, gates estatísticos e a ordem dos demais itens permanecem congelados.

- `policy_epoch` = `policy-a-resume-2026-08-26`;
- `policy_version` da política A inalterada;
- risco cheio: política A integral, incluindo interações de portfólio;
- resume plan-first, atômico e auditado com `operator=Dudu` e razão `Six-hands evidence-collection resume on 26/08 under unchanged Policy A; EHC fill reconciled; entry score adapter active`;
- sessões novas contam imediatamente para o baseline A e o estudo de entrada;
- shadow de política de saída desafiante só conta a partir da candidata instrumentada.

Nenhuma regra muda na retomada. A política A vigente permanece intocada.

**Assinaturas da Emenda 1:** Codex ✓ · Fable ✓ · Dudu ✓.

---

## 1. Pergunta congelada

As entradas do R2D2 têm edge positivo líquido de fricção — e em qual dos três eixos (o quê / quando-por quê / a que preço) o edge vive ou morre?

O estudo responde com número e **não autoriza mudança nenhuma**. Alteração de gates, universo, sizing ou horário é mudança de estratégia versionada, a seis mãos, depois. O piloto pode NOMEAR candidatos a filtro; **nenhum filtro entra na retomada sem shadow prospectivo de 15 sessões**.

## 2. Coorte e dados

- **Entradas**: todos os BUYs orgânicos do início do experimento até a pausa (último: PRI, 24/08 16:26 BRT). Excluídos: `correction` e `operator_wind_down`.
- **Inputs point-in-time**: os persistidos no BUY row (composite/fundamental/técnico/risco canônicos, stop, preços, reasons). **Proibido** V2/V3 retroativo (auditoria temporal de 24/08: não existe série honesta).
- **Caminhos de preço**: trade bars de 1 minuto — Day D minute aggregates (sessões ≤ 21/08, sha256 verificados) e, para 24/08, **uma única passagem streaming pelos 338.491 RAW trades (~88,7 MB) agregando OHLC de 1 minuto com a MESMA semântica dos aggregates Massive** (condição 4). Sem rodar o processador; sem reler quotes; **quotes/midpoint nunca se misturam com trade bars**. Nota declarada: o diagnóstico de 24/08 usou midpoints de quotes; o estudo usa trade bars uniformes em todas as sessões — diferenças pequenas de pico são esperadas e não retificam o diagnóstico.
- **Sessão sem fonte de barras** → entradas censuradas e contadas.

## 3. Gate de cobertura — publicado ANTES de qualquer resultado (condição 1)

Tabela por sessão × mercado × **policy epoch** (época de política; a recalibragem de 20/08 divide o histórico) com cobertura de: stop persistido, rota de entrada, scores, ATR, VWAP/EMA8 do papel, quote age, preço futuro (barras pós-entrada) e QQQ. **Campo ausente torna apenas aquela dimensão indisponível — sem empréstimo, sem reconstrução, sem proxy posterior.**

## 4. Medidas por entrada — independentes da política de saída

Tudo computado do preço de entrada em diante, ignorando o cascade. **Sem lookahead (condição 5): a barra parcial da entrada é excluída; cada horizonte usa o último bar completamente encerrado antes do instante-alvo; `entrada + horizonte` além do fechamento → horizonte CENSURADO** (nunca substituído pelo close).

1. **Endpoint primário: retorno líquido a +60 minutos.** Secundários: +15, +30, +120 min e close da sessão (condição 10);
2. **MFE/MAE intra-sessão** sobre trade bars: pico líquido, vale líquido, minutos-até-pico;
3. **p(atingir net₀+1R antes de net₀−1R)**: barreiras simétricas **em P&L líquido, centradas no nível líquido inicial da posição** (net₀), com R = distância do stop persistido no BUY. Sob martingale o nulo é **exatamente 50%**; desvio mede drift puro de entrada, fricção cancelada por construção. Ambos os lados tocados na mesma barra → contra a entrada (conservador).
4. **Custos exatos do código (condição 6)**: base de custo = BUY persistido (slippage já embutida no fill — **não subtrair `slippage_usd` de novo**); valor líquido de saída hipotética = helper de saída do código (`_paper_exit_execution`).

## 5. Os três eixos (dimensões congeladas)

| Eixo | Cortes |
|---|---|
| **O QUÊ** (seleção) | Edge por decil do composite canônico point-in-time **e por sub-score isolado** (fundamental 55% / técnico 30% / distância de buy-in 15% — condição 8: H3 testa o composite canônico, NÃO "o valor do V3"); por classe de ATR persistido. Liquidez bruta: **indisponível retrospectivamente** (condição 7) — dimensão marcada ausente; o adapter passa a registrá-la. |
| **QUANDO** (timing/regime) | Edge por hora de entrada (BRT); por **regime congelado (condição 2)**: QQQ único benchmark V1, sem breadth — no instante da entrada, só barras concluídas: `trend_up` = QQQ acima do VWAP da sessão E da EMA8; `fade` = abaixo de ambos; `mixed` = demais. EMA8 sobre 5-minute bars anteriores ao `decision_at`; VWAP só da sessão regular acumulada. QQQ ausente no RAW de 24/08 → regime da sessão AUSENTE, sem substituto. Por **rota de entrada (condição 3)**: campo estruturado `decision_snapshot.entry_decision_reasons` (duas frases canônicas — r2d2_strategy.py:460, r2d2.py:3498); `reason` livre só como fallback versionado; não reconhecido → `unclassified`, contado. |
| **A QUE PREÇO** (nível) | Edge por distância do preço de entrada ao VWAP e à EMA8 **do próprio papel** na entrada; por quote age no fill. **Fill-vs-signal NÃO mede chase** (≈ +10 bps fixos por construção — condição 7): dimensão removida do eixo retrospectivo. |

## 6. Hipóteses pré-registradas (a testar, não a assumir)

- **H1**: entradas 12h-15h BRT têm edge pior que 10h-12h (normalizado por oportunidade);
- **H2**: entradas em regime `fade` (QQQ abaixo de VWAP e EMA8) têm edge negativo;
- **H3**: decis do **composite canônico** não separam retorno forward (se confirmada: o score que pesa na compra não diferencia — insumo do business case V3, sem afirmar nada sobre V3);
- **H4 (reescrita, condição 7)**: entradas com preço esticado acima de VWAP/EMA8 do papel além de limiar congelado têm edge pior.

Endpoint primário decide; secundários são descritivos. IC 95% por **bootstrap de sessão com seed e iterações congelados: seed = 20260824, 10.000 iterações** (condição 10). Resultados sempre separados por `valuation_basis` e policy epoch.

## 7. Classificação piloto e disciplina

- < 15 sessões: **PILOTO** — alimenta a mesa; nomeia candidatos a filtro; **nenhum filtro entra sem shadow prospectivo de 15 sessões** (condição 10);
- Parâmetros congelados; proibido ajuste pós-resultado; sensibilidade só em fronteira nova;
- Censura, truncamentos proibidos, exclusões e n por célula: tudo contado; relatório imutável e hasheado; sha256 dos inputs listados.

## 8. Saídas do relatório

1. Gate de cobertura (§3) — publicado primeiro;
2. Tabela de edge por eixo/célula (endpoint primário + secundários, MFE/MAE, p(net₀±1R)) com IC;
3. Veredicto de H1–H4;
4. **Número-síntese**: p(net₀+1R antes de net₀−1R) global — **nulo = 50% exato**; se ≤ 50%, a porta de entrada não tem edge na moldura simétrica (insumo direto do critério de morte da v1);
5. Ranking das células piores (candidatas a filtro → shadow) e melhores (onde o edge mora, se existir).

## 9. Perna prospectiva — `entry_score_adapter` (condição 9, verbatim)

- Flag **`C3PO_R2D2_ENTRY_SCORE_ADAPTER_ENABLED=false` por padrão**; append-only; **zero API; zero execução de engine; zero influência em ordenação ou decisão**;
- Para cada candidato AVALIADO no ciclo: registrar IDs/hashes e `published_at`/`available_at` das fontes JÁ persistidas (canônico; V2/V2.1b; V3 quando existir stream nightly — **o A/B NÃO conta como stream V3 disponível**), com `published_at ≤ decision_at` e `available_at ≤ decision_at`;
- Registra também o que o retrospectivo não tem: liquidez bruta, spread quando persistido;
- Comparação prospectiva V2/V3: por **upside e percentil de ranking dentro do mesmo ciclo** — sem fabricar composite equivalente (condição 8);
- Falha do adapter **não bloqueia trading**; gera degradação visível e lacuna irrecuperável (sem backfill);
- PR pequena com teste, auditada pelo Fable, ativada junto com a retomada.

## 10. Execução e papéis

- **Ordem com a Emenda 1: Entregável 0 → adapter + epoch + retomada → runner do estudo de saída → este estudo.** A ordem relativa dos itens fora da antecipação do adapter permanece inalterada.
- Runner: Codex, off-hours, read-only, sem competir com captura, backfill ou A/B-2. Auditoria do runner contra esta spec: Fable, antes de rodar. Leitura: a seis mãos.

---

**Assinaturas da Spec V1.**
**Fable** — co-assinada em 25/08/2026; dez condições do Codex incorporadas integralmente; formalização registrada: barreiras do item 4.3 centradas em net₀ para o nulo de 50% ser exato.
**Codex** — de acordo em 25/08/2026; condições 1–10 incorporadas acima.
**Dudu** — de acordo em 25/08/2026; spec congelada a seis mãos, com a Emenda 1 assinada acima.
