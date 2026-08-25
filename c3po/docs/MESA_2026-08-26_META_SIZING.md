# Mesa de 26/08 - Memorando meta x sizing

**Status:** insumo de decisão; não altera estratégia, risco, sizing ou mandato.

## Correção de unidades

O repositório não contém uma meta vigente de `+0,15% do NAV por sessão`. As grandezas hoje registradas são diferentes:

- **Meta de produto:** `+0,5%` de retorno líquido geométrico por sessão, medido no horizonte completo. É ambição de produto, nunca quota diária.
- **Mandato Day D:** `0,15% do NAV` de risco por trade e `0,15R/sessão` como piso econômico. Nenhum dos dois é uma meta diária de `+0,15% do NAV`.
- **Política A atualmente executada pelo R2D2:** orçamento de risco de `0,02% do NAV` por trade, com alocação dinâmica normalmente entre `2,00%` e `3,08%` do NAV para stops de `1,50%` a `0,65%`.

Misturar esses números produziria uma régua incoerente antes mesmo de medir desempenho.

## Aritmética de exposição

Se `T` é a meta sobre NAV e `E` é a exposição média, o retorno exigido sobre o capital aplicado é `T / E`.

| Exposição média | Para entregar +0,50% do NAV | Hipótese prospectiva de +0,15% do NAV |
|---:|---:|---:|
| 15,00% | +3,33% | +1,00% |
| 17,68% | +2,83% | +0,85% |
| 25,00% | +2,00% | +0,60% |
| 50,00% | +1,00% | +0,30% |

A sessão de 24/08 registrou exposição média de **17,68%**, inicial de **14,73%** e máxima de **41,01%**. Portanto, a equivalência factual da meta congelada de `+0,5% do NAV` naquele perfil é aproximadamente **+2,83% sobre o capital aplicado por sessão**.

## Três opções para a época 2

### A. Medir também sobre o capital aplicado

Manter a meta de NAV congelada e publicar uma métrica companheira:

`return_on_deployed_capital = P&L orgânico da sessão / exposição média ponderada pelo tempo`.

Publicar junto a exposição média, máxima e o tempo com caixa. Isso separa qualidade das decisões de utilização do capital sem reescrever o objetivo histórico.

### B. Buscar maior exposição com mais posições

Para exposição média de 25%, a alocação atual de 2,00%-3,08% exigiria aproximadamente **9 a 13 posições simultâneas**. Para 50%, seriam **17 a 25 posições**; o limite atual de 20 só comportaria 50% se a posição média fosse ao menos 2,5% e existissem candidatos qualificados.

Esta opção não é apenas uma mudança de métrica. Ela altera simultaneidade, correlação, utilização de caixa e comportamento do portfólio. Precisa de proposta prospectiva e decisão a seis mãos; os gates de entrada não podem ser enfraquecidos para preencher vagas.

### C. Revisar a meta de NAV

Uma meta prospectiva de `+0,15% do NAV` equivaleria a cerca de `+0,85%` sobre o capital aplicado no perfil de 24/08. A revisão é permitida apenas de forma prospectiva e versionada; resultados anteriores permanecem julgados pelo mandato vigente em sua época.

## Recomendação para a mesa

Adotar **A por cinco sessões da época 2**:

1. manter `+0,5% do NAV` como ambição de horizonte, sem transformá-la em quota diária;
2. publicar retorno orgânico sobre exposição média ponderada pelo tempo, exposição média/máxima e caixa médio;
3. não aumentar posições nem revisar a meta no Dia 1;
4. reabrir B ou C apenas na leitura interina da 5ª sessão, com dados da nova época e sem reclassificar o passado.

Essa escolha muda como a mesa lê sucesso, não como o R2D2 opera.

## Fontes factuais

- `c3po/docs/R2D2_COMMITTEE_PHASE_0.md`
- `c3po/docs/day_d/STAGE_0_ECONOMICS.md`
- `c3po/backend/app/r2d2_strategy.py`
- `outputs/evidence/R2D2_SESSION_DIAGNOSTIC_2026-08-24.md`
