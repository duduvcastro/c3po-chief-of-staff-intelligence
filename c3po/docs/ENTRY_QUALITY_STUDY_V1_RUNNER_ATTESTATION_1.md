# ENTRY_QUALITY_STUDY_V1 - Atestacao 1 do runner

**Data:** 26/08/2026  
**Spec referenciada:** `c3po/docs/ENTRY_QUALITY_STUDY_V1.md`  
**SHA-256 da spec:** `63cdb045a69dfe31246e82fa64e00dd1f9e0357897259a0d420ad81d0957a41e`

Esta atestacao congela exclusivamente quatro lacunas operacionais do runner. Ela nao altera
hipoteses, endpoints, custos, bootstrap, estrategia ou governanca da spec.

## 1. Populacao e leitura do M1

- O relatorio cobre a historia completa de BUYs organicos prevista na spec.
- Resultados sao sempre estratificados por `policy_epoch`; resultados de epocas distintas
  nunca sao combinados em um estimador decisorio.
- O M1 do criterio de morte consome exclusivamente a epoca vigente
  `policy-a-resume-2026-08-26`.

## 2. Minimo para H1-H4

- O relogio minimo e de 15 sessoes distintas no escopo da hipotese.
- Cada celula comparada precisa de pelo menos 30 episodios decididos.
- Uma celula abaixo do piso produz `INSUFFICIENT_SAMPLE` apenas para a hipotese afetada;
  nao contamina as demais.

## 3. Horizonte de p(net0 +/- 1R)

- O primeiro toque e procurado ate o fechamento da mesma sessao regular da entrada.
- Nenhum toque ate o fechamento classifica a entrada como `censored`.
- A fracao censurada e publicada por estrato.
- Estrato com censura acima de 20% recebe `REVIEW_REQUIRED`; nenhuma correcao ou mudanca
  automatica e permitida. Qualquer revisao exige nova emenda assinada.

## 4. Tabela de epocas

- A tabela e derivada de deploys auditaveis.
- Cada intervalo registra `effective_from` factual e o commit efetivamente implantado.
- Mudancas intradiarias de 20/08 nao podem ser condensadas em uma unica epoca.

## Assinaturas

- **Fable:** de acordo em 26/08/2026.
- **Codex:** GO tecnico em 26/08/2026 para exatamente esta redacao.
- **Dudu:** de acordo em 26/08/2026.

