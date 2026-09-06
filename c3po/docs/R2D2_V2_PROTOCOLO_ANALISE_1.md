# R2D2 V2 — PROTOCOLO DA ANÁLISE 1 (pré-registro, revisão 2, após o NO-GO do Codex 5560285462 à V0)

**Objeto:** primeira análise pré-registrada sobre dados já coletados, para orientar o filtro de entrada da V2. Não altera o `ENTRY_QUALITY_STUDY_V1` nem o seu endpoint primário; é exploratória, PILOTO (8 sessões), e produz insumo para a mesa, não veredito. Nada aqui certifica seleção; a certificação da V2 é o shadow prospectivo, independente desta análise.

## 1. População, fonte dos insumos e compromissos (congelados)

- **População:** BUYs orgânicos da época `policy-a-resume-2026-08-26`, `executed_at` **≥ 2026-08-26T13:30:24.983322Z (inclusivo)** e **< 2026-09-06T03:00:00Z (exclusivo)**; `correction` e `operator_wind_down` excluídos, como no M1. **268 BUYs**; hash canônico do conjunto **`4a4f0a325d99aefd2237a5ca38bf705dc1debadfc01d7a5cdf78a063b072f550`** (recibo M1), reconferido na captura. O hash `1b748ad3…b937` pertence ao ledger completo do estudo de saída, com outro corte e escopo, e **não** é referência deste protocolo.
- **Fonte dos scores:** `r2d2_trades.decision_snapshot.{composite_score, fundamental_score, technical_score, risk_score}` no BUY, exatamente como o motor do M1 (finitos em 268/268). O adapter/`candidate_context` é evidência temporal complementar, com outros nomes de campo, e **não substitui** a fonte primária; **sem fallback silencioso** entre fontes; entrada sem o campo na fonte primária fica fora da célula e é contada.
- **R do BUY:** o stop persistido no BUY histórico (mesma definição do M1).
- **Referências seladas:** índice M1 `7ba30061de62f55d07adc1c015db70688129ea354dda6b18afbe0d58c22a8937`; JSON M1 `6d69a2ad4874ca040b172c8e198dd24309d368585046b59c0f8a431a0f3c0b0a`; conjunto histórico de preços do M1: 14 arquivos, 371.378.961 bytes (hashes do recibo M1, reconferidos byte a byte antes do passo 2).
- Nenhum backfill, nenhum score recalculado com código atual, nenhuma substituição de campo ausente.

## 2. Passo 1 — inventário dos inputs dos 268 BUYs (sem outcomes)

Para cada um dos quatro scores, sobre os **268** BUYs: cobertura (n finito), n de valores distintos, empates, timestamp da observação, distribuição por sessão de entrada (America/New_York) e os cortes de quartil. Saída pública só com agregados (contagens, cortes, distribuições), sem símbolos nem identificadores. **Cortes, joins e hashes são selados no recibo do passo 1 e permanecem congelados no passo 2.** Publicado e auditado antes do passo 2.

**Fórmula dos quartis (nearest-rank):** com n valores finitos ordenados de forma crescente x₍₁₎ ≤ … ≤ x₍ₙ₎, o corte do quantil p é x₍⌈p·n⌉₎, p ∈ {0,25; 0,50; 0,75}. Células: Q1 = valores ≤ corte₀,₂₅; Q2 = (corte₀,₂₅; corte₀,₅₀]; Q3 = (corte₀,₅₀; corte₀,₇₅]; Q4 = > corte₀,₇₅. Empates ficam na mesma célula pela regra acima; se dois cortes coincidirem, as células intermediárias colapsam e o colapso é publicado; **não se força quatro células**.

## 3. Passo 2 — reconstrução das medições e contrastes (com outcomes)

- **Reconstrução explícita:** não existe tabela individual arquivada dos 264 outcomes do M1 (o arquivo existente é agregado). O passo 2 reconstrói as **264 medições** e os **244 resolvidos + 20 censurados** pelo **motor e gates pinados do `ENTRY_QUALITY_STUDY_V1`**, sobre o mesmo conjunto histórico de preços (14 arquivos, hashes do recibo M1), e reconcilia as quatro exclusões pré-medida (1 violação numérica, 2 sem barra, 1 sem barras futuras). A reconstrução é apresentada como tal, nunca como leitura de outcomes individuais arquivados. Divergência de contagens ou hashes bloqueia.
- **Pergunta primária (única):** Δ = p(Q4) − p(Q1) de `composite_score`, com p = p(net₀+1R antes de net₀−1R), mesmas quatro categorias, custos e censura do estimador do M1, R do BUY histórico. Estimativa pontual e IC 95 % por **bootstrap pareado por sessão**: unidade = sessão de entrada em America/New_York (8 sessões); seed 20260824; 10.000 réplicas; **o mesmo sorteio de sessões é aplicado a todos os braços (Q1, Q4 e, nas secundárias, cada sub-score)**; em cada réplica, p̂(Qk) = resolvidos com upper-first / resolvidos na célula, agregados sobre as sessões sorteadas com reposição. Descritivamente, p por quartil com LCB/UCB 98,75 % unilateral.
- **Réplicas com denominador zero** (nenhum resolvido em Q1 ou Q4 na réplica): a réplica é registrada como `undefined`, **não é tratada como zero nem filtrada por braço**; publica-se a contagem de réplicas indefinidas; o IC é calculado sobre as réplicas definidas e, se estas forem menos de 9.000 (90 %), o contraste é `NOT_ESTIMABLE`.
- **Método do IC:** percentis empíricos 2,5 % e 97,5 % das réplicas definidas (quantil tipo 7 de Hyndman–Fan, o padrão do NumPy), sem correção de viés; pontual = Δ observado nas 8 sessões reais.
- **Célula vazia ou colapsada:** se Q4 ou Q1 do score não existir ou não tiver resolvidos, o contraste é `NOT_ESTIMABLE`; **não se trocam os extremos** por outras células depois de ver os dados.
- **Secundárias (três tabelas):** o mesmo Δ Q4 − Q1 para `fundamental_score`, `technical_score`, `risk_score`, com o mesmo sorteio comum. Nenhuma combinação de scores, nenhum limiar ad hoc, nenhuma busca em grade.
- **Direção e leitura pré-registrada:** a direção do contraste é publicada sempre. IC 95 % inteiramente positivo → `V2_FILTER_CANDIDATE` para a regra explícita "score alto" (Q4-like); IC inteiramente negativo → `V2_FILTER_CANDIDATE_INVERTED` para a regra explícita "score baixo", que só existe se for escrita e assinada como tal — **nenhuma inversão tácita**; IC incluindo zero → `V2_FILTER_NOT_CANDIDATE`. Tudo PILOTO; nada refuta nem certifica.

## 4. Execução e janela

- **Módulo puro + transporte somente leitura** preparados pelo Codex (a partir dos helpers do `ENTRY_QUALITY_STUDY_V1`), entregues ao Fable para auditoria **antes** do passo 1; transação READ ONLY, timeout 30 s, sem chamadas externas, sem escrita; artefatos públicos só com agregados; integral privado se houver identificadores.
- **Janela:** domingo 06/09 ou feriado 07/09 (mercado fechado), ou 00:00–08:00 BRT de dia útil. O runner completo do M1 tem a sua própria trava 00–08 BRT: **reutilizar helpers não é executar aquele runner nem remover a trava**; este protocolo não a altera.
- Ordem: passo 1 → publicação e auditoria → passo 2 → publicação e auditoria → mesa.

## 5. Orçamento de erro e proibições

- Quatro contrastes (1 primário + 3 secundários) em 8 sessões; ICs exploratórios sem correção formal, aceitáveis porque não certificam a seleção e o shadow prospectivo é independente. A certificação da V2 traz o seu próprio orçamento de erro (spec V1).
- Proibido: reabrir a v1; alterar produção; usar scores atuais ou do adapter no lugar dos persistidos em `decision_snapshot`; escolher quartil, score, extremo ou direção depois de ver os outcomes; apresentar a reconstrução do passo 2 como arquivo de outcomes individuais.

## 6. Assinaturas

- Fable (redação, rev 2): 06/09/2026.
- Codex: pendente (auditoria da rev 2 e entrega do módulo/transporte).
- Dudu: ciência.
