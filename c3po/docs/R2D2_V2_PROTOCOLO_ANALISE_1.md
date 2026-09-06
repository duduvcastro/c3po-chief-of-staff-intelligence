# R2D2 V2 — PROTOCOLO DA ANÁLISE 1 (pré-registro; V0 para auditoria do Codex antes de qualquer cruzamento novo)

**Objeto:** primeira análise pré-registrada sobre dados já coletados, para orientar o filtro de entrada da V2. Não altera o `ENTRY_QUALITY_STUDY_V1` nem o seu endpoint primário; é exploratória, PILOTO (8 sessões), e produz insumo para a mesa, não veredito.

## 1. População e insumos (congelados = os do M1 até 05/09)

- Época 2, `policy_epoch = policy-a-resume-2026-08-26`, entradas orgânicas (BUY) de 2026-08-26T13:30:24.983322Z até o corte do M1 de 05/09; exclusões e censuras do M1: 268 BUY → 264 medições (1 violação numérica, 2 sem barra, 1 sem barras futuras) → 244 resolvidas + 20 censuradas de barreira.
- Insumos por entrada: `composite_score`, `fundamental_score`, `technical_score`, `risk_score` no instante do BUY (`candidate_context`/observação do adapter), R do BUY histórico (stop persistido), outcome de barreira net₀ ±1R já calculado pelo M1 (upper-first / lower-first / ambíguo / censurado).
- Hashes: os do pacote `m1-atualizado` (índice `m1-atualizado-SHA256SUMS`) e do ledger completo até o corte (`1b748ad3…b937`), reconferidos na captura. Nenhum backfill, nenhum score recalculado com código atual, nenhuma substituição de campo ausente (entrada sem o campo fica fora da célula, contada).

## 2. Passo 1 — inventário dos inputs (sem outcomes)

Para cada score: cobertura (n com valor finito), n de valores distintos, empates, timestamp da observação, e os cortes de quartil **nearest-rank** sobre as 264 medições (empates ficam na mesma célula; se um corte se repetir, as células colapsam e isso é publicado, sem forçar quatro células). Saída pública: só agregados (contagens, cortes, distribuição por sessão), sem símbolos nem identificadores. **Publicado e auditado antes do passo 2.**

## 3. Passo 2 — pergunta primária e secundárias (com outcomes)

- **Primária (única):** Δ = p(Q4) − p(Q1) de `composite_score`, com p = p(net₀+1R antes de net₀−1R), mesmas quatro categorias, custos e censura do estimador do M1; estimativa pontual e IC 95 % por **bootstrap pareado por sessão** (seed 20260824, 10.000 réplicas, unidade = sessão de entrada em America/New_York). Também p por quartil com LCB/UCB 98,75 % unilateral, apenas descritivo.
- **Secundárias (três tabelas, uma por sub-score):** o mesmo Δ Q4 − Q1 para `fundamental_score`, `technical_score`, `risk_score`. Nenhuma combinação de scores, nenhum limiar ad hoc, nenhuma busca em grade.
- **Leitura pré-registrada:** com 8 sessões, qualquer resultado é PILOTO. O que autoriza: (i) Δ com IC 95 % excluindo zero → o score entra como candidato ao filtro da V2, a ser certificado em shadow; (ii) IC incluindo zero → o score não é candidato por este critério; a mesa pode escolher outro caminho, registrando o motivo. Nada aqui refuta ou certifica; nomes explícitos: `V2_FILTER_CANDIDATE` / `V2_FILTER_NOT_CANDIDATE`.

## 4. Execução

- Runner somente leitura (transação READ ONLY, timeout 30 s), projeção dos dados persistidos do M1, sem chamadas externas, sem escrita; implementado pelo Codex a partir do motor do `ENTRY_QUALITY_STUDY_V1`, auditado pelo Fable antes de rodar; artefatos públicos só com agregados; integral privado se houver identificadores.
- Ordem: passo 1 → publicação e auditoria → passo 2 → publicação e auditoria → mesa.

## 5. Orçamento de erro e o que este protocolo não permite

- Quatro contrastes (1 primário + 3 secundários) em 8 sessões: os IC 95 % são descritivos; não há correção formal porque nada aqui é leitura decisória. A certificação da V2 acontece no shadow, com a política candidata única e o orçamento de erro definido na spec V1.
- Proibido: reabrir a v1, alterar produção, usar scores atuais em vez dos persistidos, escolher o quartil ou o score depois de ver os outcomes.

## 6. Assinaturas

- Fable (redação): 06/09/2026.
- Codex: pendente (auditoria do protocolo e implementação do runner).
- Dudu: ciência.
