# Gate V3 de 4–5/09 — plano de mesa

## Objeto

Primeira leitura do shadow `valuation_v3_shadow` após o mínimo de dez noites consecutivas
bem-sucedidas. Este plano organiza a leitura; não autoriza promoção, consumidor, TP ou mudança
de estratégia.

## Entrada obrigatória

1. Verificar a sequência noturna, completude por mercado, hashes e `soak_eligible`.
2. Ler integralmente o `V3_EVIDENCE_LEDGER` adotado pela mesa, SHA-256
   `bc2f52dbab4041e7af71800efe92e8340a3788a0a163db26beca38b7c31b014a`.
3. Conferir cada linha `ABERTO` ou `AGUARDANDO_DADO` contra sua evidência original.
4. Revisar as `ledger_candidate_lines` emitidas pelos runners desde a última mesa. Candidatos
   não entram automaticamente no ledger.
5. Incorporar como linha #10 apenas após fechamento factual os counters de rejeição do funil de
   28/08, respondendo nominalmente por que o R2D2 não comprou.
6. Reabrir o memorando `meta x sizing` após as cinco sessões previstas: publicar retorno
   orgânico sobre exposição média ponderada pelo tempo, exposição média e máxima, caixa médio e
   tempo em caixa; então decidir entre manter a leitura companheira (A), especificar maior
   exposição (B) ou propor meta prospectiva versionada (C), sem reclassificar o passado.

## Ordem de leitura

1. Integridade e cobertura do shadow.
2. Ledger: fatos, hashes, implicações e pendências.
3. H3 do estudo de entrada e eixos por sub-score, se a amostra pré-registrada estiver madura.
4. Leitura `meta x sizing`: qualidade das decisões versus utilização do capital e capacidade
   financeira efetiva sob os limites assinados.
5. Diagnóstico individual dos casos em que o mecanismo V3 não engatou.
6. Deliberação a seis mãos: manter shadow, especificar V3.x ou abrir rito de promoção atômica.

## Travas

- `consumer_change_authorized=false`.
- `official_tp_replacement_authorized=false`.
- Nenhuma linha candidata, resultado noturno ou leitura exploratória promove código sozinha.
- Divergência de hash, noite incompleta ou dado pendente permanece nomeada; não é preenchida
  por estimativa.
