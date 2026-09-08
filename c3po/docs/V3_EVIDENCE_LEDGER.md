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
| 8 | pendente ~1/09 | H3 do estudo de entrada: os decis do composite canônico separam retorno forward? (condição 8 da spec: insumo declarado do business case V3) + eixos por sub-score. | runner #257, leitura 5ª sessão | SE o composite não separa: o argumento central do V3 ganha baseline quantificado, e os eixos dizem qual sub-score trocar primeiro. A linha mais importante deste ledger. | LIDO_OFFLINE_INSUFICIENTE(07/09/2026): dado produzido offline pelo runner congelado (revisão `c61a8fee`, delta contra main = pin do ledger) sobre a população fechada (643 BUYs; época corrente 264 em 8 sessões) — H3 INSUFFICIENT_SAMPLE pelos mínimos amostrais pré-registrados (8/15 sessões, 25/30 decididas na barreira por célula; inatingíveis com a v1 morta): amostra insuficiente para confirmar ou refutar H3; leitura descritiva com direções mistas nos extremos (p̂ 0,56 no decil inferior vs 0,48 no superior; +60 min −0,306 % vs −0,259 %) e sem ordenação monotônica observada nos decis do composite nem dos sub-scores; sem conclusão de separação, equivalência ou ausência de efeito. Evidência: leitura rev 3 `6bd83624…` (rev 2 `ad0c85e4…`, rev 1 `85c35a49…`), report `f6bce4ae…`, manifest `2301f17d…`, reprodução independente do Codex (5570751303); recibo do dono `e3b436bd…` |
| 9 | 28/08 | TP canônico dos one-pagers = média aritmética simples de cinco estimadores correlacionados, que reutilizam em combinações distintas os mesmos anchors primitivos (dcf/enterprise/earnings/book) — pesos implícitos e sobreposição não calibrada. Constatado pelo Dudu em painel real (TP 107,13 = média exata ao centavo); precisão da redação: auditoria Codex. | one_pager.py:551-589 (`statistics.mean` + anchors compartilhados) | O trono que o V3 disputa é uma média simples de componentes sobrepostos; se o V3 reprovar no gate, "pesos por erro histórico + controle/desduplicação da sobreposição de componentes" é o item 1 do mandado V3.2. | ABERTO |
| 10 | 07/09 | Leitura do gate V3 (13 noites de shadow, 26/08→07/09, streak 13, soak_eligible desde 04/09): gates de promoção (p50 ≤ 15 % / p90 ≤ 30 % internos) REPROVADOS em 39/39 mercados-noites e em todos os perfis com n ≥ 10, pela leitura dos percentis arquivados nos snapshots (07/09: B3 19,4 %/47,9 %; NASDAQ 33,8 %/66,8 %; NYSE 24,1 %/57,7 %); viés mediano negativo em todos; V3 ≈ V2 na régua interna (p90 melhora 1–5 p.p.) — comparação descritiva com datas e universos distintos, sem ganho causal pareado demonstrado. Macro reutilizada de 24/08 (`macro_as_of`) nas 13 noites segundo o extrato; identidade dos pacotes macro comprovada nas 12 primeiras noites; G3 normativo aberto. Decisão do dono de 07/09 registrada por Fable ("de acordo com as 4 decisoes"): shadow mantido, sem promoção. Conferência integral da 13ª noite ASSINADA pelo Codex em 07/09 (`f912a1f2…`, 4.206/4.206 relações, com ressalva documental: V3.2 `applied` em 95 de 102 ativos B3) → fechamento a seis mãos da leitura concluído com ressalva (manifesto `MANIFESTO_V3_GATE_2026-09-07.json`); G3 (validade normativa da macro) permanece aberto. | leitura `07417723…` (final, 13 noites) / conferência Codex 12 noites `471f955a…` / deliberação `fe2f86a3…` / recibo do dono `97ef0daa…` / assinatura Fable `eebc4c97…` | Mandado V3.2 aberto (spec própria; rascunho rev 1 `33ae0839…` em revisão do Codex, rev 2 em preparação): pesos por erro realizado + desduplicação (#9), re-execução B3 (#4), não-engate do V3.1 no B3 (`not_peer_anchor` 84/306), beta negativo zerado nos EUA (116/73), política de renovação macro do shadow. Travas consumer/TP mantidas. | ABERTO |

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
