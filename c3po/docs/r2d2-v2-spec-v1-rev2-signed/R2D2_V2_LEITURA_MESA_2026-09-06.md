# R2D2 V2 — Leitura da mesa (06/09/2026 17:30 BRT) e proposta de EMENDA 1 à spec V1 rev 2

**Autor:** Fable (auditor/executor). **Estado:** leitura técnica + proposta documental para assinatura a seis mãos. Nada aqui executa calibração certificadora, coleta, deploy, paper ou posições. A spec V2 V1 rev 2 (manifesto `01d258903c060660a51ad48e7506903d038b0fa6901142456e06c7858350c359`) continua em `SIGNED_PENDING_CALIBRATION` até a mesa decidir.

## 1. Fatos novos desde as assinaturas (16:40 BRT)

1. **Código do estimador (§5) e do calibrador (anexo B + fechamento) implementado** — PR #381 (commit `0a30ace31df5ff0dcbafd9e0cfba2abb0cbcd5d8`; estimador `3719f54d…`, calibrador `407be445…`, 24 testes `b8950579…`), em auditoria pelo Codex.
2. **Custo medido:** 28 cenários × 2.000 repetições em 22,3 s (10 workers). M = 50.000 nos 28 cenários ≈ 10 min. **M permanece 50.000** (adendo E2).
3. **O candidato assinado reprova o próprio anexo B** (smoke de desenvolvimento, M = 2.000, sementes `C3PO-V2-CAL-1`, método intocado; relatório `evidence-relay/r2d2-v2-calibration/2026-09-06-dev-smoke/calibration_dev_smoke_M2000.json` sha256 `f371eda585e7aeb2a0751b0f40b39a02f195285aaf12cec1e3081378f5395b66`):

   | cenário | FWER (alvo ≤ 5 %) | R1@20 | R1@30 | H1@20 | H1@30 | H3@20 | H3@30 |
   |---|---:|---:|---:|---:|---:|---:|---:|
   | D0_000 (iid) | 15,4 % | 5,4 % | 2,9 % | 4,4 % | 2,3 % | 5,1 % | 3,0 % |
   | D1_000 | 30,4 % | 4,2 % | 2,1 % | 19,4 % | 14,3 % | 16,8 % | 12,9 % |
   | D2_000 | 34,4 % | 9,8 % | 6,6 % | 16,8 % | 10,5 % | 18,1 % | 13,2 % |
   | D2_S4 | 34,9 % | 9,4 % | 7,1 % | 17,4 % | 13,0 % | 17,6 % | 14,1 % |

   Alvo por teste: 0,83 %. Cobertura condicional dos LCBs (nominal 99,17 %): 95–97 % em D0, 80–89 % em D1/D2. Poder conjunto com as três alternativas verdadeiras (D0_111): 14,3 % na coorte 20, 8,7 % na 30. O gate de dados adverso passou (200/200). O laudo formal só nasce da execução autorizada após a auditoria; mas os limites de Clopper–Pearson do smoke já excluem os alvos por margens enormes. **Resultado esperado: `CALIBRATION_FAILED`.**

4. **Fontes de dados (Codex, 5561835978, inventário estático da main `00fbe963`):** não existem no app (a) snapshot causal de bid/ask às 10:00 ET para o universo (o feed `us-quote` do EODHD existe, mas o cache mistura trade/quote, não preserva os dois lados nem timestamps individuais, e a subscrição é limitada a 550 símbolos); (b) contrato diário OHLC de 61 barras/ADV20 (o cliente diário retém date/close/volume, descarta OHLC e pode usar `adjusted_close`); (c) calendário prospectivo de earnings com cobertura verificável. **Consequência contratual: o gerador, obedecendo aos gates do §2, produziria zero elegíveis.** Integrar e validar os produtores é dependência de ativação, além da calibração.

## 2. Diagnóstico: o problema é o desenho, não só o estimador

Exploração (sementes CAL-1, M = 1.000 por cenário, **sem valor certificador**; pacote `evidence-relay/r2d2-v2-calibration/2026-09-06-exploration/`, `SHA256SUMS` no diretório):

- **Desvio-padrão verdadeiro** do estimador da coorte (medido nas trajetórias): em D2 (ρ = 0,7, sobreposição 10, φ = 0,8), `p̂_E` de 20 sessões tem SD **0,21** (D0: 0,027); a média de P&L de 20 episódios tem SD **US$ 58** (iid: US$ 22). Com N = 10 e fator comum de janela 10, 20 sessões contêm ~2 observações efetivas do mercado. Um LCB honesto a 99,17 % de H1 exigiria `p̂ − 2,4 × 0,21 > 0,5`, isto é, `p̂ > 1`. **H1 e H3 não são certificáveis a 1/120 em 20/30 sessões por nenhum método**; alongar para 60 sessões não resolve (SD ≈ 0,12).
- **R1 é contraste pareado** (X compartilhado entre os braços): SD do contraste 0,045 (D2, n = 20) → 0,027 (n = 60). É a única hipótese confirmatória viável no horizonte do calendário.
- Métodos comparados em R1 sob o nulo (falso GO %, alvo 0,83 %) e sob Δ = +0,10 (poder %):

  | coorte | batches de 10 (t_{k−1}), α = 1/120 | D0 nulo | D1 nulo | D2 nulo | D0 Δ=0,10 | D1 Δ=0,10 | D2 Δ=0,10 |
  |---|---|---:|---:|---:|---:|---:|---:|
  | 20 | k = 2 (t_1 = 38,2) | 0,9 | 0,9 | 1,3 | 6,9 | 6,1 | 4,2 |
  | 30 | k = 3 (t_2 = 7,65) | 0,8 | 0,7 | 1,2 | 16,0 | 18,0 | 9,3 |
  | **40** | k = 4 (t_3 = 4,86) | 0,3 | 1,0 | 0,3 | 34,4 | 36,4 | 20,8 |
  | **60** | k = 6 (t_5 = 3,53) | 0,2 | 0,3 | 0,7 | 74,7 | 81,0 | 57,7 |

  Batches de 5 têm mais poder (n = 40: 66/78/61 %) mas são anticonservadores em D2 (1,6–1,7 %: batches adjacentes ficam correlacionados pela janela 10). Com α = 0,025 por leitura (família de duas leituras ≤ 5 %), batches de 10: D2 nulo 2,9 %/2,8 % (n = 40/60; SE Monte Carlo 0,5 %), poder 48 %/86 %. HAC (Newey–West, largura 9, t_{n−1}) e bootstrap L = 1 não controlam (5–10 % em R1; 15–25 % em H1/H3). O bootstrap percentílico assinado tem "poder" alto porque é inválido.

## 3. O que isso significa para terça 08/09

- **Não há "versão nova no ar" certificável na terça**, por duas razões independentes: (i) o estimador/desenho assinado reprova e exige emenda + validação com sementes novas; (ii) as três fontes de dados exigidas pelo §2 não existem no app — sem elas o gerador registra só `DATA_INELIGIBLE`.
- **O que pode estar no ar na terça, sem ferir o rito:** o gerador shadow V2 do Codex em **modo diagnóstico** (registrar universo observado, tentativas de snapshot, motivos de inelegibilidade, sem episódios nem carteira) — se a PR do Codex for auditada e o deploy sair fora do pregão. Isso mede a cobertura de dados e prova a tubulação, sem iniciar o relógio de coorte.
- O relógio de coorte só começa na primeira sessão com elegíveis reais (fontes integradas e validadas). Com 40/60 sessões de entrada e maturação de 10, as leituras caem ~10 e ~14 semanas depois desse início.

## 4. Proposta de EMENDA 1 à spec V2 V1 rev 2 (para as três assinaturas; texto a redigir após o parecer do Codex)

1. **Família confirmatória = R1 apenas** (`θ = p(elegíveis) − p(controles) > 0`, condicionada aos resolvidos, mesma geometria e mesmo fluxo causal nos dois braços). H1 e H3 passam a **descritivas pré-registradas** (publicadas por coorte com LCB/UCB informativos e contagens; sem poder de certificação); os vetos operacionais permanecem (gap 1 % NAV; NAV ≤ 95 %; gate de dados §3.4).
2. **Coortes = as primeiras 40 e 60 sessões de entrada programadas** (maturação nas sessões 49 e 69); leitura na 60 só sem aprovação na 40; sem terceira leitura; sem GO parcial.
3. **Estimador candidato a validar:** médias por batch de **10 sessões contíguas** (k = 4/6), contraste pareado das razões por batch, LCB unilateral `média − t_{k−1,1−α} × s/√k`; `NOT_ESTIMABLE` se algum batch não tiver denominador positivo em um dos braços; contagens originais e motivos publicados; nada de reamostragem.
4. **α = 1/120 por leitura** (mantido; família de duas leituras ≤ 1/60). Alternativa para a mesa: α = 0,025 por leitura (família ≤ 5 %), com o mesmo critério estrito de Clopper–Pearson — a exploração sugere 2,8–2,9 % sob D2, o que pode reprovar.
5. **Calibração (anexo B rev 2):** mesmas estruturas D0/D1/D2 e stress; trajetórias de 69 sessões; máscaras reduzidas a R1 (nulo 000, alternativa Δ = +0,10, stress S1/S2/S3 e um cenário Δ = −0,10); K recontado no manifesto; **sementes novas `C3PO-V2-CAL-2`** fixadas antes do run; M = 50.000; critérios `upper_MC(erro) ≤ α` e `upper_MC(FWER das duas leituras) ≤ 2α`. As sementes CAL-1 ficam registradas como exploração e não podem certificar.
6. **Fontes de dados (Codex):** contratos explícitos para snapshot 10:00 ET (bid/ask, `source_at`/`available_at`, universo limitado a uma lista causal fixada na véspera dentro do limite de 550 símbolos do provedor), OHLC diário de 61 barras com ADV20 (sem `adjusted_close`), calendário prospectivo de earnings com cobertura verificável (provedor a confirmar); ausência → `DATA_INELIGIBLE` contado. Prontidão das fontes = gate de ativação separado.
7. **Coleta cega:** assim que as fontes existirem e o gerador estiver auditado, a coleta pode começar com ledger privado e **sem publicação de agregados** até a aceitação do laudo de calibração do método emendado, para não perder calendário nem contaminar a escolha do método. A leitura de qualquer coorte continua proibida antes do laudo.

## 5. Pedidos

- **Codex:** auditar #381 e reproduzir o smoke; parecer sobre §4 desta leitura (método, coortes, α, anexo B rev 2); continuar o gerador em modo diagnóstico + contratos de dados; PR para minha auditoria.
- **Dudu:** ciência de que terça não terá coleta certificável; decisão sobre a EMENDA 1 (§4) após o parecer do Codex — assinatura a seis mãos, como sempre.
