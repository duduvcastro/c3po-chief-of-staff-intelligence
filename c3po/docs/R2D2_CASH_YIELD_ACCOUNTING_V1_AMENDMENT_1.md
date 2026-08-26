# R2D2_CASH_YIELD_ACCOUNTING_V1 - Emenda 1 (para auditoria)

**Objeto:** corrigir a validade temporal do accrual sintetico de caixa para cobrir toda a vida do experimento R2D2, sem alterar estrategia, risco ou snapshots historicos.

**Origem temporal:** a data inicial passa a ser `r2d2_experiments.start_date` (`2026-08-17` no experimento vigente), e nao uma data fixa de ativacao do recurso. O primeiro fechamento final do experimento fornece a primeira base factual de caixa. O primeiro lancamento pertence a sessao final seguinte, usando o intervalo entre esses dois fechamentos. Nao se inventa saldo, taxa ou rendimento anterior ao nascimento do experimento.

**Backfill:** o runner percorre todas as sessoes finais elegiveis sem lancamento, da mais antiga para a mais recente. Cada lancamento continua novo, append-only, idempotente, causal e identificado por hash. Nenhum snapshot antigo e reescrito.

**Substituicao expressa:** esta emenda substitui exclusivamente a clausula **"Backfill e validade temporal"** da V1 para o accrual sintetico de caixa. A regra geral registrada naquela clausula permanece como precedente obrigatorio para futuros congelamentos e nao e revogada.

**Isolamento preservado:** `interest_income` permanece fora de NAV operacional, sizing, risco, entradas, learning loop, estudos, expectancia, M2 e M3. A mudanca afeta somente `ACCOUNTING TOTAL` e sua exibicao.

**Versao:** metodologia `r2d2_cash_yield_accounting` v2 e schema `R2D2-CASH-YIELD-v2`.

**Assinaturas:** Dudu - aprovado por instrucao explicita em 25/08/2026 ("considerar o Cash Yield no NAV desde o inicio do 1o dia de operacao e corrigir isso") - OK; Codex - OK; Fable - auditoria pendente.
