# ENTRY_QUALITY_STUDY_V1 - Atestacao 2 do runner: semantica de barra ausente

**Data:** 26/08/2026  
**Spec referenciada:** `c3po/docs/ENTRY_QUALITY_STUDY_V1.md`  
**SHA-256 da spec:** `63cdb045a69dfe31246e82fa64e00dd1f9e0357897259a0d420ad81d0957a41e`  
**Texto canonico desta atestacao antes das assinaturas:** `8608203d9cb931a652c3b8194cdfbfd47309a4d2c0e2dc043bf54434f9ffc0e7`

**Evidencia motivadora:** dry-run factual da PR #257, report
`bc685af93273c21fcbc577fa484173d75c230b9b14d9c5eeffabdce86257276f`.
O gate bloqueou 29 de 426 entradas: 3 incompatibilidades numericas
(`PNRG`, `BVN`, `DXST`) e 26 entradas sem barra candidata (15 em 24/08, 9 em
26/08 e 2 em 21/08).

Esta atestacao altera exclusivamente o runner do estudo de entrada. Nao muda a
spec, hipoteses, estimadores, estrategia nem a Emenda 1 do estudo de saida.

## 1. Classe `bar_unavailable`

Se nenhuma barra existir nas janelas originais (mais ou menos 1 minuto de
`executed_at` ou `quote_as_of`) e nenhuma barra existir na janela estendida
de -10 a +1 minuto de `quote_as_of`, a entrada recebe a classe propria
`bar_unavailable`.

- E censura de cobertura, listada nominalmente e contada por sessao.
- Nunca e classificada como incompatibilidade numerica.
- Nao entra no teto de 5% do G3.

## 2. Teto vinculante do G3

O teto de 5% continua incidindo somente sobre incompatibilidades numericas.
Aplicado aos insumos factuais do dry-run, o resultado esperado e 3 de 426,
ou aproximadamente 0,70%, com gate `PASS`. As 26 entradas sem barra candidata
sao censuradas antes das medicoes.

## 3. Revisao de cobertura

O relatorio publica a taxa de `bar_unavailable` por sessao. Sessao acima de
20% recebe `REVIEW_REQUIRED`. Esse estado nao corrige dados, nao muda limiar,
nao bloqueia trading e nao autoriza reexecucao; qualquer revisao exige nova
decisao assinada.

## 4. Imutabilidade

As sessoes RAW existentes permanecem intactas. Um futuro manifest de agregados
pode produzir novo relatorio; relatorios anteriores permanecem imutaveis.

## 5. Isolamento

Esta atestacao vale somente para o runner de entrada. O estudo de saida e seu
timer das 00:15 permanecem inalterados.

## Assinaturas

- **Fable:** de acordo em 26/08/2026, conforme texto canonico no relay.
- **Codex:** GO tecnico em 26/08/2026, apos recomputar o SHA-256 canonico e
  conferir esta redacao.
- **Dudu:** de acordo em 26/08/2026, pela declaracao explicita "Tou de acordo tb".
