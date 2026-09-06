# EXIT_POLICY_STUDY_V1_1 — EMENDA 2

**Objeto**: (a) extensão do estudo, como estrato separado, à coorte da época 2 (`policy-a-resume`,
entradas a partir de 2026-08-26T13:30:24.983322Z); (b) conciliação do rótulo de metodologia exigido
pelo runner congelado com o registro vigente do experimento.
**Spec emendada**: `c3po/docs/EXIT_POLICY_STUDY_V1_1.md`, sha256
`21882372220d55aa01c0a23b9288d75788d25b1187c01b4954e0c500ec0216a2`.
**Emenda 1 (vigente, inalterada)**: `c3po/docs/EXIT_POLICY_STUDY_V1_1_AMENDMENT_1.md`, sha256
`3001ed9eba15d684f7dcd74d91a940e7603ae4d5a342b53655b2fd1e9250bfc8`.
**Entregável 0 (vigente, inalterado)**: sha256
`ae83428ac0444329efc7405e06078c144b575a0909699e15b16ce5a26de20098`.
**Natureza**: emenda de coorte e de contrato de proveniência. Nenhuma hipótese, política, overlay,
custo, parâmetro, estimador, seed, gate ou regra de decisão é alterada.

## 1. Motivação factual (evidência hasheada)

1. A execução somente leitura de 2026-09-06T02:39:36Z sobre a época 2 terminou
   `BLOCKED_METHODOLOGY_MISMATCH` **antes** de G1/G2/G3 e de qualquer overlay
   (`painel-i-execution.public.json`, sha256
   `fe4fa90402cf72d19d607346d587786a8241d5344d17313d4c55fedc0d975105`; `painel-i.md`, sha256
   `e1994a59e895fd6c59a4b3a6656582e87050ef37bc9c9937d36b8cc7a2db9017`; pacote
   `pos-p6-20260906/SHA256SUMS`, sha256
   `fe7f1d2fb2c0a471f7cb6de027aefb6f1101d2f4813640135afc30d7c77fe75d`). O runner
   `c3po/backend/app/r2d2_exit_policy_study.py` na revisão
   `cd6683b1f2ee24fc2d5573554b67648a4746b299` (sha256
   `be281dfe4abb13cd304313f58b6c877c006dcbcc15e553393e7429190869bf3e`) fixa
   `FROZEN_METHODOLOGY = "R2D2-HYBRID-V27-15M-LIQUIDITY-FLOOR"` (linha 44) e bloqueia qualquer outro
   valor (linha 666). O registro do experimento informa
   `R2D2-HYBRID-V28-DERIVED-PORTFOLIO-CAPACITY`.
2. Proveniência do rótulo: `METHODOLOGY_VERSION` passou a V28 no commit
   `26db5ffd38c9f403773e7bd0cf73d123153a4767` ("Derive R2D2 portfolio capacity from risk limits"),
   mergeado em `main` por `7bc70899db6088afcd303b4c490f08d88a2758ce` (PR #346) em 01/09/2026
   01:40 BRT e implantado pelo run 33470705511 (concluído 01:47 BRT). O serviço grava o rótulo
   vigente no registro do experimento a cada inicialização (UPSERT em `r2d2.py`); o rótulo atual,
   sozinho, não data a política de cada entrada histórica. Sessões de 26 a 31/08 correram sob código
   rotulado V27; sessões de 01 a 04/09, sob V28.
3. O que mudou entre o commit da política congelada `39ff427fd2f1fa0f42141776921a63651508495f`
   (24/08) e a produção `cd6683b1…`, por comparação de AST função a função nas revisões
   39ff427f → `4401290674d93b5fd07ecc92b6f604b218fab0c0` (25/08, PR #224) → 26db5ff → cd6683b1
   (script `ast_multi.py`, sha256 `91f76910a7534d71bcdebd71b4ef9227c4ae6f6e62efc1afd2adf903b31178c0`;
   saída, sha256 `d116c4ef525403a9da7608060ffe8e6cd8639cdd90aa3270dfa8969add76965d`; executado pelo
   Fable em 06/09/2026):
   - `r2d2_strategy.py`: `exit_decision`, `hard_stop_quote_price`, `technical_defense`,
     `estimated_net_exit_pnl_percent`, `target_position_percent`, `entry_decision`,
     `compute_technical_snapshot`, `weekly_conviction` e `ema` são **idênticas** nas quatro revisões.
     Única adição: `entry_stop_quote_price` (25/08, PR #224, correção LOW: stop inicial ancorado na
     cotação do fill), anterior ao início da época 2.
   - `r2d2.py`: os caminhos de saída `_mark_and_exit`, `_mark_and_exit_locked`, `_technical_defense`,
     `_risk_priority`, `run_fast_risk_watcher_cycle`, `run_risk_monitor_cycle`,
     `observe_fast_risk_tick` e `risk_evaluation_lock` são **idênticos**. As mudanças concentram-se
     no lado da entrada e do dimensionamento (`_buy`, `_entry_capacity_usd`, `_has_entry_capacity`,
     `_confirm_entry_setup`, `_us_candidates`, guarda de histórico de listagem, shadow de
     candidatos), na contabilidade administrativa (`_paper_exit_execution` extraído sem alterar o
     modelo de fricção; `_trade_is_strategy_excluded`; pausa de entradas; bloqueio de reentrada após
     saída com perda), na captura de fechamento canônico e em telemetria/dashboard.
   - Conclusão: as saídas registradas no ledger da época 2 foram produzidas pela **mesma política de
     saída** congelada; a V28 alterou capacidade e dimensionamento de entrada, não regras de saída.
     A época 2 é, contudo, um regime de entrada/dimensionamento distinto da época 1 e, por isso, um
     estrato separado.

## 2. Texto normativo

**E2.1 — Coorte da época 2 (estrato separado).** Fica autorizado, como estrato próprio, o estudo
dos episódios construídos exclusivamente a partir de fills com
`executed_at >= 2026-08-26T13:30:24.983322Z` (instante auditado da retomada `policy-a-resume`) e
`executed_at <=` corte de insumos declarado na execução. Fills anteriores ao instante não entram.
Se um SELL abrir episódio "from flat" na fronteira, o runner bloqueia (regra já existente do
construtor de episódios) e nada é interpretado. A cláusula "janela além de 2026-08-21" do §3 da
spec lê-se, para este estrato, "janela além da última sessão de barras disponível" — semântica que o
runner já aplica por `latest_bar_session`; sessões sem barras entram na censura `beyond_bar_cutoff`.

**E2.2 — Rótulos aceitos por estrato.** Sem `cohort_start_at`, o runner continua exigindo
`R2D2-HYBRID-V27-15M-LIQUIDITY-FLOOR` (estrato da época 1, comportamento inalterado). Com
`cohort_start_at` igual ao instante de E2.1, aceita-se o conjunto
{`R2D2-HYBRID-V27-15M-LIQUIDITY-FLOOR`, `R2D2-HYBRID-V28-DERIVED-PORTFOLIO-CAPACITY`}. Qualquer
outro rótulo, ou qualquer `cohort_start_at` diferente do instante fixado, bloqueia antes dos gates.
O relatório registra o rótulo observado, o conjunto aceito, o instante de início, o hash desta
emenda e `pooling_across_strata_authorized = false`.

**E2.3 — Sem pooling.** Nenhuma estatística agrega episódios das duas épocas. Comparações entre
A(época 1) e A(época 2) são descritivas e não constituem inferência. A regra PILOTO (< 15 sessões)
e a não-vinculação do Painel II permanecem; para a época 2 há, hoje, no máximo seis sessões com
barras (26/08 a 02/09).

**E2.4 — Inalterado.** Custos e fricção; parâmetros de B/B'/C/C'/D/D'; precedência intrabar;
ativação em N+1; horizonte de 10 sessões; ATR(14) Wilder point-in-time em D−1 (exige as sessões
diárias anteriores já previstas); G1/G2/G3 da Emenda 1; seed 20260824 e 10.000 réplicas; coorte
comum por painel; estimador pareado por sessão em America/New_York; regra "gate falhou → não
interpretar painel".

**E2.5 — Execução.** Uma única execução, somente leitura (transação READ ONLY, timeout ≤ 30 s por
consulta, sem símbolos ou identificadores em saída pública), com ledger congelado por hash
(`--expected-ledger-sha256` sobre os fills selecionados por E2.1) e manifesto de minutos por hash,
em 06/09/2026 (domingo, mercado fechado) ou na janela 00:00–08:00 BRT de 07/09/2026. Fora do timer,
pode ser invocada por `build_report` sob supervisão, porque a restrição horária existe para proteger
o pregão. Artefatos completos com SHA no relay e na #348; nenhuma interpretação antes do gate PASS.

## 3. Supersessão expressa

Esta emenda supersede exclusivamente (i) a limitação da coorte à janela até 2026-08-21, para o
estrato da época 2, e (ii) a exigência de rótulo único no runner, para esse mesmo estrato. Tudo o
mais — spec V1.1, Emenda 1 e Entregável 0 — permanece em vigor sem alteração.

## 4. Implementação

1. Fable propõe a alteração mínima do runner: parâmetros `--cohort-start-at` e `--amendment-two`,
   conjunto de rótulos por estrato, filtro de início nos insumos congelados e evidência no relatório,
   com testes que fixam o comportamento fail-closed; o hash deste texto assinado é pinado em
   `AMENDMENT_TWO_SHA256`.
2. Auditoria cruzada pelo Codex antes do merge.
3. Execução conforme E2.5 pelo Codex, sob supervisão.
4. Parecer do Fable ao dono.

## 5. Assinaturas (seis mãos)

- **Fable** (autor desta emenda): ASSINADO — 06/09/2026.
- **Codex**: pendente.
- **Dudu**: pendente.

Sem as três assinaturas, o estudo permanece BLOQUEADO para a época 2 e a V1.1, com a Emenda 1,
permanece vigente na forma congelada.
