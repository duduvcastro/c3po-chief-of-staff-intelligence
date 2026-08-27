# V3_EVIDENCE_LEDGER — retroalimentação do motor, com prova

**Criado:** 28/08/2026 · **Regra:** append-only; cada achado quantitativo do laboratório vira uma
linha aqui com evidência hasheada e implicação declarada, ou não deveria ter sido produzido.
**Consumidor:** a mesa do gate V3 (primeira leitura 4–5/09) e toda mesa de promoção subsequente.
**Status possíveis:** ABERTO → INCORPORADO_EM(versão) | REFUTADO(evidência) | SUPERSEDIDO(linha).

| # | Data | Fato medido | Evidência (sha256) | Implicação para o V3 | Status |
|---|------|-------------|--------------------|-----------------------|--------|
| 1 | 27/08 | Painel I: as 4 variantes de take-profit precoce perdem MAIS que a política A (B' significativamente pior, IC95 [−16,73;−2,28]/episódio). Saída NÃO é a alavanca. | report `0c9e0587…` / arquivo `fb4605b2…` | 100% do esforço de melhoria pertence à SELEÇÃO — o domínio do valuation. Nenhum recurso de V3.x deve ir para lógica de saída. | ABERTO |
| 2 | 27/08 | Painel II (exploratório): D_PRIME é a única política positiva (+US$ 20.796, win 89,9%, holds ~19h) sobre os mesmos episódios em que tudo intradiário perde. | idem #1 | Valuation prevê semanas; a v1 opera minutos. Hipótese de estratégia V3-driven com holding multi-dia, a propor via shadow após piloto maduro (≥15 sessões). | ABERTO |
| 3 | 26–27/08 | Gap A_MINUTE (−20,5k) vs A real (−39,1k): a execução viva custou ~US$ 18,6k além da réplica mecânica das mesmas regras. | idem #1 | O custo não está só em QUAIS regras, mas em COMO o maquinário intradia as executa. Investigação própria antes de atribuir tudo ao score. | ABERTO |
| 4 | 27/08 | Loader CVM somava linha trimestral como acumulada (dupla subtração do 1T); crescimento B3 do V3 consumiu o dado contaminado (PETR +42,31% corrigido etc.). | PR #261, metodologia v2 | Insumo de crescimento B3 corrigido; re-execução dos resultados históricos B3 do V3 pendente de decisão da mesa. | ABERTO |
| 5 | 27/08 | Tape probe: 78,3% dos desvios de gate eram negócios reais com condições fora do high/low; 18 ticks sem suporte no tape (fantasmas) nomeados; banda de 25 bps com lastro medido. | report `aeff080a…` / vetores #266 | Qualidade de tick é risco de INPUT para qualquer motor: workstream provider_ts com 18 casos-teste; validação de tick pré-decisão é candidata a gate futuro. | ABERTO |
| 6 | 24/08 (diagnóstico) + época 2 | 74% dos dólares perdidos vieram de entradas que nunca ficaram líquidas-positivas; época 2 repete o padrão: rajada num dia (49 episódios, 20,4%), seca nos seguintes. | dump `65c5ef9a…` / closeout `4187ac06…` | O funil de candidatos é o gargalo: ou o score aprova errado, ou rejeita tudo. Counters de rejeição por razão = insumo direto do V3. | ABERTO |
| 7 | 28/08 | Rota provisória full-exchange: ZERO disparos em 425 episódios orgânicos. O funil largo é letra morta. | probe H3 `09f9dff9…` | O V3 só precisa vencer no universo canônico (~700); a pergunta "o que o universo deixa de fora" exige o shadow-candidate log (instrumento futuro, spec própria). | ABERTO |
| 8 | pendente ~1/09 | H3 do estudo de entrada: os decis do composite canônico separam retorno forward? (condição 8 da spec: insumo declarado do business case V3) + eixos por sub-score. | runner #257, leitura 5ª sessão | SE o composite não separa: o argumento central do V3 ganha baseline quantificado, e os eixos dizem qual sub-score trocar primeiro. A linha mais importante deste ledger. | AGUARDANDO_DADO |

## O ciclo de retroalimentação, como está e onde aperta

**Já automático (toda noite, sem mão humana):** adapter grava cada decisão com causalidade →
estudos rodam nas janelas off-hours → gates classificam com semântica assinada → counters do
kill criterion acumulam → shadow V3 compara contra o canônico → evidência hasheada no relay.

**Automático a construir (proposta):** (a) cada report de estudo emite automaticamente linhas
candidatas a este ledger (rascunho mecânico; entrada efetiva com aprovação da mesa); (b) o
gate V3 de 4–5/09 lê este ledger como pauta obrigatória; (c) leituras interinas agendadas
emitem o rascunho da proposta de promoção/refutação quando os ICs cruzarem os limiares.

**Deliberadamente humano (e provado certo pelo item #1):** a assinatura que muda política.
Auto-ajuste sem gate teria adotado a política B com os dados do dia 1 — e perdido mais.
A máquina aprende sozinha; ela só não se PROMOVE sozinha.

## Assinaturas de adoção

- **Fable:** ASSINADO — 28/08/2026 (autor; reconhece que este ledger deveria existir desde 25/08).
- **Dudu:** pendente.
- **Codex:** pendente.
