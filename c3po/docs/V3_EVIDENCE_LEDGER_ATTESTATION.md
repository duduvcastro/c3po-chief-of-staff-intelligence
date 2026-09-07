# V3_EVIDENCE_LEDGER — atestação de adoção

**Documento canônico:** `c3po/docs/V3_EVIDENCE_LEDGER.md`  
**SHA-256 canônico:** `501ecb1c3b502970a1b70a5e39ca4f36b5624e970ea1e4cf95897ac253339898`

Esta atestação preserva o documento canônico byte a byte e registra apenas os fatos de
assinatura ocorridos depois da sua emissão.

- **Fable:** assinatura já registrada no documento canônico.
- **Dudu:** `De acordo tb` — assinatura dada no chat da mesa que adotou o ledger.
- **Codex:** de acordo técnico após recomputar o SHA-256 canônico e revisar a separação entre
  fato, implicação, rascunho automático e admissão humana no ledger.

## Efeito

O ledger está adotado como pauta obrigatória da primeira leitura do gate V3 de 4–5/09 e das
mesas de promoção posteriores. Linhas candidatas produzidas por runners são rascunhos
mecânicos; inclusão, mudança de status ou consequência de política continuam exigindo mesa.

## Linhas #10 e #8 (proposta de 07/09/2026 na PR #388 — rev 2 documental)

Pin do documento após as linhas #10 e #8 (rev 2): `28848f607ba5395bcaba75c3d165955f86c6036c3a30e1b83b4f9ca9fd94bc40` (anterior admitido
`bc2f52dbab4041e7af71800efe92e8340a3788a0a163db26beca38b7c31b014a`, linha #9 admitida via #282). Os pins intermediários
`ac4184a85581851ae006eb5dd2597658c3be98045914fa73a6c55d07325865ed` (c61a8fee, só #10) e
`88935bc8177c609b46a8f562453e58f67ef334dc1c4433886a335fbe67038079` (830c94fe, #10 + #8 rev 1) foram propostas superadas
desta mesma PR e nunca foram admitidos.

- **Linha #10** registra o veredito da leitura do gate V3 de 07/09 (13 noites; gates REPROVADOS em 39/39 pela leitura dos
  percentis arquivados) e a **decisão do dono de 07/09 registrada por Fable** ("de acordo com as 4 decisoes", recibo
  `97ef0daa…`): shadow mantido, sem promoção, mandado V3.2 aberto. A **conferência integral da 13ª noite (outputs/manifest)
  e o fechamento a seis mãos permanecem pendentes** (o Codex conferiu 12 noites, `471f955a…`). A identidade dos pacotes
  macro reutilizados está comprovada nas 12 primeiras noites e G3 normativo segue aberto; a comparação V3/V2 na régua
  interna é descritiva, com datas e universos distintos, sem ganho causal pareado.
- **Linha #8** passa de AGUARDANDO_DADO a LIDO_OFFLINE_INSUFICIENTE(07/09/2026): dado produzido offline com o runner
  congelado do estudo sobre a população fechada (revisão `c61a8fee`, cujo delta contra main é só o pin do ledger; leitura
  rev 2 `ad0c85e45d51c2d84692488417fff12b23476b3e8da84b12a4584e0aba2c22a6`; report `f6bce4ae…`; reprodução independente do
  Codex, 5570751303, com resultado econômico idêntico). H3 fica INSUFFICIENT_SAMPLE pelos mínimos amostrais pré-registrados
  (8/15 sessões, 25/30 decididas por célula); a leitura descritiva mostra direções mistas e ausência de ordenação
  monotônica, sem conclusão de separação ou de ausência de efeito. Sem mudança de política.

Admissão de ambas por esta PR após parecer do Codex e OK da mesa; nenhuma promoção, mudança de consumidor/TP, deploy ou
coleta decorre delas.
