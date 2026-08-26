# EXIT_POLICY_STUDY_V1_1 — EMENDA 1

**Objeto**: substituição da cláusula de "compatibilidade OHLC" do gate vinculante.
**Spec emendada**: `c3po/docs/EXIT_POLICY_STUDY_V1_1.md`, sha256 `21882372220d55aa01c0a23b9288d75788d25b1187c01b4954e0c500ec0216a2`.
**Natureza**: emenda de validação de dados. Nenhuma hipótese, painel, estimador, seed, coorte ou regra de estratégia é alterada.

## 1. Motivação factual (evidência hasheada)

A execução de 26/08/2026 00:15 BRT terminou `BLOCKED_BY_BINDING_GATE` com 406 falhas
`ohlc_compatibility` (report sha256 `204db88dc020b023750a1df3021611f3f91875fd4798f45dd78a9c9f6f5101ef`,
self-hash `934e3b93…`). Os probes read-only de 26/08 (sha256 `864b494e4f3798504e46aeef7da19e45690c7656676fa6ce6e96ca481e9c124c`
e `a104292b552f8631df9bcfbc2c727ac605222703be0ba2f1b434be382a898cf7`) decompõem as 406:

- **278** — o gate testava o FILL SINTÉTICO (sinal × (1±10bps de slippage modelada)) contra o range
  real negociado; o sinal estava dentro da barra. Defeito da cláusula congelada, não dos dados.
- **35** — sinal contido em barra 2–9 minutos ANTES de `quote_as_of` (idade de captura subestimada;
  alimenta o workstream de instrumentação `provider_ts`).
- **89** — divergência residual entre provedores ≤ 25 bps da borda (mediana 6,34 bps, p95 21,4 bps),
  com coerência direcional de 87% com o lado da estratégia: assinatura de efeito de seleção
  (execuções concentradas em extremos locais) somada a semânticas distintas de condições de negócio
  entre o trade tick EODHD e o agregado de minuto Massive. Barras finas rejeitadas como causa
  (0 barras ≤3 negócios; mediana 45,5 negócios).
- **4** — breaches de 25,6 a 49,3 bps, em 4 episódios (`NASDAQ:LIFE`, `NYSE:BVN` ×2, `NYSE:PJT`):
  incompatibilidade genuína, tratada pelo §2.G3.

A cláusula original reprovava 48–76% dos fills por sessão — não distinguia corrupção de
funcionamento normal do mercado consolidado. **Contenção exata entre tick de um provedor e OHLC de
outro não é invariante válido.**

## 2. Texto normativo substituto

Onde a spec exige, no gate vinculante, que o preço de fill esteja contido no range [low, high] da
barra de minuto compatível (±1 min), passa a valer:

**G1 — Reconciliação exata de ledger e fricção (INALTERADA, vinculante).** Reconciliação contábil
ao centavo e verificação aritmética `fill = signal × (1 ± slippage_modelada)` com tolerância 1e-7.
Zero tolerância. Qualquer falha bloqueia o estudo.

**G2 — Compatibilidade de mercado entre provedores (substitui a contenção exata).** O teste usa o
`signal_price_local` (trade tick persistido), nunca o fill sintético (já coberto por G1). Cada fill
é classificado, nesta ordem:
1. `contained` — sinal dentro de [low, high] de barra candidata nas janelas originais
   (±1 min de `executed_at` ou de `quote_as_of`);
2. `clock_extended` — sinal contido em barra na janela [−10 min, +1 min] de `quote_as_of`;
3. `tolerance_band` — breach ≤ **25 bps** da borda mais próxima das janelas originais;
4. `violation` — todo o resto.

Classes 1–3 são compatíveis e NÃO censuram; o report publica contagens por classe e por sessão.
**Origem declarada do 25 bps**: calibrado no p95 da divergência residual medida em 26/08
(21,4–23,2 bps, probe `864b494e…`). Calibrar o limiar de sanidade na divergência observada é
legítimo porque a contenção nunca foi insumo de inferência dos painéis; o poder do gate é
preservado por G1 (exato) e pelo teto de G3.

**G3 — Censura nominal e teto sistêmico (vinculante).** Episódio com ≥1 fill `violation` é
**coverage-censored**: excluído dos DOIS painéis, contado e listado nominalmente no report. O
estudo permanece BLOQUEADO se episódios censurados por violação excederem **5% dos episódios
construídos** (hoje: 4/375 = 1,07%) ou se G1 falhar. Acima do teto, nenhuma interpretação de
painel é permitida.

## 3. Supersessão expressa

Esta emenda supersede EXCLUSIVAMENTE a exigência de contenção exata do fill no gate
`ohlc_compatibility` da V1.1. Permanecem em vigor, sem alteração: reconciliação ao centavo,
janelas de construção de episódios, seed/bootstrap (20260824/10k), coortes, censuras já definidas,
precedência intrabar, horizonte de 10 sessões, e a regra "gate falhou → não interpretar painel".

## 4. Execução

1. Codex implementa G2/G3 no runner (`r2d2_exit_policy_engine.py`), com testes que pinem as
   contagens desta decomposição (278/35/89/4) contra os insumos congelados de 26/08;
2. PR auditada pelo Fable antes do merge;
3. Re-run na próxima janela 00:15 BRT com os MESMOS insumos congelados (ledger sha `51f616bc…`,
   manifest de minutos sha `c615d27f…`, seed inalterada); resultado esperado: gate PASS com
   4 episódios censurados declarados; painéis computam;
4. Artefatos completos no relay; nenhuma interpretação antes do report com gate PASS.

## 5. Assinaturas (seis mãos)

- **Fable** (autor da cláusula original e desta emenda): ASSINADO — 26/08/2026.
- **Codex**: ASSINADO — 26/08/2026; GO técnico concedido sobre esta redação.
- **Dudu**: ASSINADO — 26/08/2026; de acordo registrado literalmente como "Eu tou de acordo".

Com as três assinaturas, esta emenda substitui a cláusula expressamente identificada acima. A
implementação e qualquer re-run continuam sujeitos, respectivamente, à auditoria da PR pelo Fable
e à janela off-hours já congelada.
