# R2D2_CASH_YIELD_ACCOUNTING_V1 — Accrual Sintético de Caixa (CONGELADA)

**Status:** congelada a seis mãos em 25/08/2026, pré-registrada antes da primeira sessão da época `policy-a-resume-2026-08-26`. **Natureza:** apropriação contábil diária do rendimento do caixa ocioso; não é cupom recebido nem trade. **Escopo:** contabilidade e exibição; zero efeito em estratégia.

**Taxa (série e convenção FIXADAS neste congelamento):** *U.S. Treasury Daily Treasury Bill Rates*, tenor **13 semanas**, campo **Coupon Equivalent** — rendimento sobre o preço de compra, base **365/366** (fonte oficial: home.treasury.gov, Daily Treasury Bill Rates; equivalente à família *investment basis* tipo FRED DGS3MO). **Explicitamente NÃO** o campo Bank Discount (valor de face, base 360; família DTB3). Nenhuma outra série ou tenor sem deliberação a seis mãos — **sem fallback silencioso**. Pacote macro **próprio e versionado** (o pacote V3 congelado exige exatamente US3Y/US10Y e permanece intocado). Causalidade padrão da casa: `available_at ≤ fetched_at`, disponibilidade D+1. Fator diário = `coupon_equivalent × dias_corridos / 365` (366 em ano bissexto).

**Fórmula e intervalo contábil (fixados):** para a sessão `D`, com `P` = sessão americana imediatamente anterior:
- base = **caixa operacional ex-juros no fechamento final de `P`**, com piso em zero (`max(base, 0)`);
- taxa = observação causal de 13 semanas **datada de `P`**;
- dias = **dias corridos entre `P` e `D`**, incluindo fins de semana e feriados;
- o lançamento **pertence a `D`** e só ocorre quando a fonte estiver disponível;
- ausência da fonte mantém o lançamento `pending` — **sem substituir taxa e sem reescrever o primeiro vintage aceito**.

**Persistência:** ledger **append-only e idempotente**, um lançamento por sessão com: `session_date`, saldo-base, taxa, observação-fonte, `available_at`, `fetched_at`, hash canônico e `backfilled_at` quando aplicável.

**Três grandezas explícitas, reconciliando ao centavo:** `MARKED` · `ACCOUNTING EX-INTEREST` · `ACCOUNTING TOTAL`, com a identidade `TOTAL = EX-INTEREST + Σ interest_income` verificada a cada exibição.

**Isolamento (a cláusula que dá força à ideia):** `interest_income` **não entra** em sizing, risco, gates de entrada, learning loop, estudos, expectância, M2 ou M3. O `nav_usd` operacional consumido pelo motor permanece **ex-juros**. **EMENDA 1 ao `V1_KILL_CRITERION`** (docs, uma linha, mesmas três assinaturas): *"`interest_income` não é P&L orgânico para nenhum efeito de M2/M3."*

**Backfill e validade temporal:** as três assinaturas foram dadas em **25/08/2026, antes das 10:30 BRT de 26/08 e antes de qualquer leitura do Dia 1** — portanto o pré-registro é factual e o accrual vale **desde 26/08/2026**, exclusivamente por lançamentos novos, factuais e auditáveis, **zero reescrita de snapshots antigos**. Regra geral registrada: se um congelamento desta natureza ocorresse após qualquer leitura da sessão, o accrual começaria prospectivamente na sessão seguinte, sem backfill.

**Degradação:** fonte ausente ou stale ⇒ accrual `pending` (lançado quando a fonte chegar); **nunca taxa fixa, nunca bloqueia trading**.

**Exibição:** manchete do Daily P&L = **trading orgânico**; sub-linha `Cash yield +US$ X · NAV Δ ±US$ Z`; painel mostra juros da sessão, acumulado da época, taxa e data-fonte, e NAV ex-juros lado a lado.

**Rito:** PR de implementação com auditoria do Fable → ativação pós-deploy. GO de spec não é GO de implementação automática.

**Assinaturas:** Fable ✓ (proposta + 12 condições + 3 precisões finais do Codex incorporadas, 25/08/2026) · Codex ✓ (válido sobre exatamente esta redação, 25/08/2026) · **Dudu — "tou de acordo sim" dado em 25/08/2026 sobre a redação anterior; reconfirmação de uma palavra sobre este texto final pendente** (as 3 precisões fecham escolhas — série 13-semanas/Coupon Equivalent, intervalo contábil, validade temporal — sem alterar o acordado).
