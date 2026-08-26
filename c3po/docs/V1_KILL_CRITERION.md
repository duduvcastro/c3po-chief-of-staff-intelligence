# Critério de Morte da Estratégia v1 — V4 (final)

**Objeto:** política A na época `policy-a-resume-2026-08-26` em diante. **Amostra:** episódios flat-to-flat da época; `correction` e `operator_wind_down` excluídos; parciais consolidadas por episódio. **Métricas:** sempre líquidas de custos; win rate por EPISÓDIO, nunca por SELL leg. **Nenhum ponto estimado, sozinho, decide nada — só cotas de confiança.**

**EMENDA 1 — isolamento do accrual de caixa:** `interest_income` não é P&L orgânico para nenhum efeito de M2/M3.

**Régua global:** dois critérios de morte × duas leituras decisórias (15ª e 20ª sessões) = quatro testes. Para erro global de 5% sobre qualquer `V1_REFUTED`, **M1 e M2 usam UCB unilateral de 98,75% em cada leitura** (Bonferroni 0,05/4; procedimento conjunto pré-registrado equivalente pode substituir se implementado). Leituras de 5 e 10 sessões são interinas, sem poder de veredito.

**M1 — Edge de entrada ausente** (leituras decisórias): **reutiliza população, definição de `p(net₀±1R)`, tratamento de ambíguos/censurados e bootstrap de sessão congelados do `ENTRY_QUALITY_STUDY_V1`**. Dispara se UCB unilateral de 98,75% de `p` ≤ 50% sobre ≥ 15 sessões. Veredito: `V1_REFUTED`.

**M2 — Expectância negativa** (leituras decisórias): UCB unilateral de 98,75% da expectância líquida por episódio < 0 nas sessões da época. Veredito: `V1_REFUTED`. Alternativa aprovada (pré-registrada, gates próprios, melhora pareada estatisticamente positiva, expectância absoluta não-negativa) **não salva a v1** — habilita apenas sucessão versionada após nova decisão a seis mãos.

**M3 — Trip wire** (qualquer momento): retorno acumulado orgânico da época ≤ −5%, denominador **fixo = NAV contábil de fechamento imediatamente anterior ao início da época**, E UCB unilateral de **95%** do win rate por episódio < 30%, com mínimo de **30 episódios**. Veredito: `TRIPWIRE_PAUSE` — freio operacional, não veredito inferencial; **registra-se que a monitoração repetida não promete erro global de 5%**. Pausa auditada imediata + mesa, que decide entre retomar, emendar por rito, ou antecipar formalmente uma leitura decisória.

**Sequência terminal:** sem refutação na 15ª → **estende sempre à 20ª**. Na 20ª: cotas inferiores unilaterais (no mesmo nível de 98,75%) acima dos limiares nos DOIS critérios (LCB de `p` > 50% E LCB da expectância > 0) → **`V1_NOT_REFUTED_AT_20`** (a v1 segue, época continua); caso contrário → **`INCONCLUSIVE_PAUSE_FOR_REVIEW`** (pausa para mesa, sem morte artificial).

**O que `V1_REFUTED` executa:** o breaker existente (`entries_paused=true`, operador e razão auditados); exits, risco e EOD ativos; sem liquidação automática, sem promoção de alternativa, sem mudança de `status`. Blueprint registra "v1: refutada com número" + as cotas. Nada se apaga.

**Retomada pós-`V1_REFUTED`:** política versionada, novo epoch, nova decisão a seis mãos.

**Assinaturas:** Fable ✓ (proposta e incorporação integral: dez condições + três correções + dois ajustes finais, 25/08) · Codex ✓ (de-acordo sobre esta redação, 25/08) · Dudu ✓ (de-acordo, 25/08).
