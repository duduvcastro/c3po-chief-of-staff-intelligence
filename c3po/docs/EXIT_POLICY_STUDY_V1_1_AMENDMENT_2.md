# EXIT_POLICY_STUDY_V1_1 — EMENDA 2 (revisão 2, assinada a seis mãos em 06/09/2026)

**Objeto**: (a) extensão do estudo, como estrato separado, à coorte da época 2 (`policy-a-resume`,
episódios abertos a partir de 2026-08-26T13:30:24.983322Z); (b) conciliação do rótulo de metodologia
exigido pelo runner congelado com o registro vigente do experimento.
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
   01:40 BRT; o run 33470705511 registra o job de produção concluído às 01:47:13 BRT (recibo
   conferido pelo Codex em 5557018281). O serviço grava o rótulo vigente no registro do experimento
   a cada inicialização (UPSERT em `r2d2.py`); o rótulo atual, sozinho, não data a política de cada
   entrada histórica. Pelo recibo de deploy, as sessões de 26 a 31/08 correram sob código rotulado
   V27 e as de 01 a 04/09 sob V28; a continuidade entre deploys (ausência de rollback) não foi
   reconstruída aqui e não é premissa desta emenda.
3. O que a comparação de AST função a função estabelece — e o que não estabelece — entre o commit da
   política congelada `39ff427fd2f1fa0f42141776921a63651508495f` (24/08) e a produção `cd6683b1…`,
   nas revisões 39ff427f → `4401290674d93b5fd07ecc92b6f604b218fab0c0` (25/08, PR #224) → 26db5ff →
   cd6683b1 (script `ast_multi.py`, sha256
   `91f76910a7534d71bcdebd71b4ef9227c4ae6f6e62efc1afd2adf903b31178c0`; saída reproduzida byte a
   byte pelo Codex com Python 3.9.6, sha256
   `d116c4ef525403a9da7608060ffe8e6cd8639cdd90aa3270dfa8969add76965d`; os hashes de `ast.dump`
   dependem da versão do interpretador):
   - **Iguais nas quatro revisões**: os corpos das funções de avaliação de saída de
     `r2d2_strategy.py` (`exit_decision`, `hard_stop_quote_price`, `technical_defense`,
     `estimated_net_exit_pnl_percent`, `target_position_percent`), os 33 bindings desse arquivo
     (constantes e campos de dataclasses, conferidos pelo Codex), os corpos de `_mark_and_exit`,
     `_mark_and_exit_locked`, `_technical_defense`, `_risk_priority`, `run_fast_risk_watcher_cycle`,
     `run_risk_monitor_cycle`, `observe_fast_risk_tick` e `risk_evaluation_lock`, e o modelo de
     fricção da venda (`_sell` → `_paper_exit_execution`: mesmas taxas e mesma aritmética; 144
     cenários sintéticos com payload idêntico, conferidos pelo Codex).
   - **Diferentes, alcançáveis pelos caminhos de saída**: `risk_markets` (janela de risco
     09:40 → 09:30 ET em 4401290; sessões pelo calendário XNYS em cd6683b1), `_seconds_to_us_close`
     (16:00 fixo → fechamento do calendário XNYS em cd6683b1; alimenta a regra EOD e
     `exit_decision(seconds_to_close=...)`), `_rotate_if_better` (guarda de entradas pausadas antes de
     uma rotação que vende), e a âncora do stop inicial (`entry_stop_quote_price`, 25/08, PR #224,
     correção LOW), que nasce na entrada e é consumida pela saída. Não foram reconstruídos os valores
     efetivos de configuração (`.env`/compose) nem a revisão implantada em cada sessão.
   - **Conclusão restrita**: os corpos das funções de avaliação de saída, suas constantes puras e o
     modelo de fricção permanecem iguais nas quatro revisões examinadas. A comparação **não**
     estabelece identidade integral da política operacional de todas as saídas, nem equivalência de
     execução entre as épocas. O estudo da época 2 usa a sequência real A observada no ledger como
     baseline de um estrato próprio, preserva as regras congeladas dos overlays e os gates, sem
     pooling e sem afirmar equivalência de runtime com a época 1. O impacto das diferenças listadas
     sobre os resultados medidos não é atribuído nem excluído por esta emenda.

## 2. Texto normativo

**E2.1 — Coorte da época 2 (estrato separado, seleção por episódio).** Os insumos congelados
continuam sendo todos os fills do experimento até o corte declarado na execução (hash do ledger sobre
esse conjunto, como hoje). Os episódios são construídos flat-to-flat sobre esses insumos e, em
seguida, o estrato retém apenas os episódios cujo primeiro fill (`opened_at`) é
`>= 2026-08-26T13:30:24.983322Z` (instante auditado da retomada `policy-a-resume`). Episódios abertos
antes do instante — inclusive os que atravessam a fronteira — são excluídos do estrato e contados em
`construction.pre_cohort_episodes_excluded`; nunca são censurados em silêncio e nunca abortam a
execução. A cláusula "janela além de 2026-08-21" do §3 da spec lê-se, para este estrato, "janela além
da última sessão de barras disponível" — semântica que o runner já aplica por `latest_bar_session`;
sessões sem barras entram na censura `beyond_bar_cutoff`.

**E2.2 — Rótulos aceitos por estrato.** Sem `cohort_start_at`, o runner mantém o comportamento
anterior byte a byte: relatório e plano com a mesma forma de saída, e o relatório exigindo só
`R2D2-HYBRID-V27-15M-LIQUIDITY-FLOOR` (o plano legado nunca verificou o rótulo e continua sem
verificar). Com `cohort_start_at` igual ao instante de E2.1, aceita-se o conjunto
{`R2D2-HYBRID-V27-15M-LIQUIDITY-FLOOR`, `R2D2-HYBRID-V28-DERIVED-PORTFOLIO-CAPACITY`}. Qualquer
outro rótulo, ou qualquer `cohort_start_at` diferente do instante fixado, bloqueia antes dos gates.
Só no estrato da época 2 o relatório e o plano registram o rótulo observado, o conjunto aceito, o
instante de início, o hash desta emenda e `pooling_across_strata_authorized = false`.

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
(`--expected-ledger-sha256` sobre todos os fills até o corte, conforme E2.1) e manifesto de minutos
por hash (incluindo as sessões diárias de aquecimento do ATR), em 06/09/2026 (domingo, mercado
fechado) ou na janela 00:00–08:00 BRT de 07/09/2026. Fora do timer, pode ser invocada por
`build_report` sob supervisão, porque a restrição horária existe para proteger o pregão; o wrapper
supervisionado exige previamente as três assinaturas, o hash final desta emenda, o head autorizado
após o merge, o corte e os hashes de ledger/minutos. Artefatos completos com SHA no relay e na #348;
nenhuma interpretação antes do gate PASS.

## 3. Supersessão expressa

Esta emenda supersede exclusivamente (i) a limitação da coorte à janela até 2026-08-21, para o
estrato da época 2, e (ii) a exigência de rótulo único no runner, para esse mesmo estrato. Tudo o
mais — spec V1.1, Emenda 1 e Entregável 0 — permanece em vigor sem alteração.

## 4. Implementação

1. Fable propõe a alteração mínima do runner (PR #378): parâmetros `--cohort-start-at` e
   `--amendment-two`, conjunto de rótulos por estrato, seleção do estrato por episódio, evidência no
   relatório e no plano somente para a época 2, com testes que fixam o comportamento fail-closed e a
   forma inalterada das saídas da época 1; o hash deste texto é pinado em `AMENDMENT_TWO_SHA256`.
2. Auditoria cruzada pelo Codex antes do merge (primeira rodada: NO-GO em 5557018281, com os dois
   pontos incorporados nesta revisão 2).
3. Execução conforme E2.5 pelo Codex, sob supervisão.
4. Parecer do Fable ao dono.

## 5. Assinaturas (seis mãos)

- **Fable** (autor desta emenda): ASSINADO — revisão 2, 06/09/2026.
- **Codex**: ASSINADO — revisão 2, 06/09/2026 02:11 BRT; "Codex — EMENDA 2: ASSINADO" na PR #348,
  comentário 5557119303, sobre o texto desta revisão com sha256
  `12aeb2e27ab3d4a65647e677063342e82fbae5a039d45d82a9d3abe6798bf349` (bytes anteriores ao
  preenchimento destas linhas de assinatura), incluindo expressamente a seleção por episódio da
  E2.1 e o hash do ledger histórico até o corte.
- **Dudu**: ASSINADO — 06/09/2026 09:51 BRT; de acordo registrado literalmente como "de acordo" no chat com
  o Fable e lavrado na PR #348, comentário 5559337159.

Com as três assinaturas, esta emenda passa a vigorar sobre a V1.1 e a Emenda 1. A execução E2.5
continua sujeita aos portões do §2 e o merge da PR #378 à reconferência do Codex sobre o commit que
preenche estas linhas e o pin `AMENDMENT_TWO_SHA256`.
