# ENTRY_QUALITY_STUDY_V1 - Atestacao 2: postflight factual

**Data:** 26/08/2026  
**Atestacao canonica preservada no relay:** `8608203d9cb931a652c3b8194cdfbfd47309a4d2c0e2dc043bf54434f9ffc0e7`  
**Atestacao consolidada e assinada no repositorio:** `c5cd8f88632bd9c80ab593ec1e60ba9bdecaee6eaf7c54c41cf1c37df0a11c8b`  
**Workflow factual:** `33022905030`  
**Report self-hash:** `23ede14e5d76cdd70bd1df58fcde62ad9445291eacae4872174b835ac4b94756`  
**Manifest self-hash:** `1e1b7c975f44a7fd9c566814ac050fbef4be3e2cc9fce6560990438ce148c3eb`

## Resultado

O dry-run factual terminou `PASS`, `analysis_interpretable=true` e
`classification=INSUFFICIENT_SAMPLE`.

| Classe | Contagem |
| --- | ---: |
| `contained` | 296 |
| `clock_extended` | 32 |
| `tolerance_band` | 85 |
| `bar_unavailable` | 10 |
| `violation` | 3 |

As tres violacoes numericas sao `PNRG` (41,0608 bps), `BVN` (41,5057 bps) e
`DXST` (34,3053 bps). O teto vinculante ficou em `3/426 = 0,704225%`.

As dez censuras de cobertura sao seis em 24/08 e quatro em 26/08. As taxas por
sessao sao, respectivamente, 9,375% e 7,8431%; ambas ficam abaixo do limiar de
20% e recebem `ACCEPTABLE`.

## Previsao falsificada

A previsao assinada dizia que 26 entradas nao tinham barra candidata. O primeiro
postflight mostrou que 16 delas tinham barra apenas na janela estendida. O helper
herdado nao calculava distancia nessa fronteira e devolvia `violation` com
`breach_bps=null`.

O runner foi corrigido para medir a barra estendida mais proxima com os mesmos
25 bps da Emenda 1. As 16 entradas passaram para `tolerance_band`; somente dez
permaneceram `bar_unavailable`. A regra normativa da Atestacao 2 foi preservada:
ausencia real de barra e censura de cobertura, enquanto incompatibilidade
numerica sempre publica uma distancia numerica.

Este postflight registra o desvio factual. Ele nao altera assinaturas, spec,
hipoteses, estrategia, estudo de saida ou timer das 00:15.
