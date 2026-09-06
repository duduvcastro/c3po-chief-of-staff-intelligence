# R2D2 V2 — REGRA CANDIDATA R1 (teto de risco na admissão), revisão 2 após as objeções do Codex 5560672127 (rascunho para assinatura a seis mãos; não é política congelada)

**Origem:** análise 1 da V2, passo 2 (06/09/2026, PILOTO, 8 sessões, 264 medições reconstruídas = M1; público `e276be50…`). Contraste pré-registrado secundário do `risk_score`: p(net₀+1R antes de −1R) = 52,5 % no quartil mais baixo (Q1) contra 33,9 % no mais alto (Q4); Δ Q4 − Q1 = −0,187, IC 95 % [−0,332; −0,050] → `V2_FILTER_CANDIDATE_INVERTED`. Pelo protocolo (§3), uma regra invertida só existe se for escrita e assinada; nada aqui certifica.

## 1. Fatos do código (corrigidos pelo Codex; a semântica completa das origens do `risk_score` será entregue por ele)

- `risk_score`: escala 0–100, **maior = mais risco**. Na v1, as duas rotas de BUY exigem `risk_score <= 55` (`r2d2_strategy.py:480/531`) e retornam BUY antes da leitura de `policy['max_risk_score']` (linha 568), que só compõe motivos de REJECT. **`max_risk_score = 48` (faixa 40–52) não é um segundo teto efetivo das rotas de BUY.** A v1 está pausada; isto não pede conserto operacional dela.
- Composto de **entrada**: `round(0.55*fundamental + 0.30*technical + 0.15*entry, 3)`, com `entry = clamp(100 − 5*max(buy_in_distance, 0), 0, 100)` (`r2d2.py:4733–4735`, chamado em 4164). Não há termo de risco direto nessa fórmula; **não se afirma independência**, porque algumas origens do fundamental incluem risco. (O `0,48/0,52` é o `live_composite` de posição/saída, linha 3658.)

## 2. O que o piloto mostrou e o que não mostrou

- Mostrou: contraste **Q4 versus Q1** do `risk_score` com IC 95 % fora de zero, na direção "mais risco → pior", em 8 sessões, sem correção pelos quatro contrastes.
- Não mostrou: o efeito de um teto em c75 (isto é, **Q1+Q2+Q3 versus Q4**). R1 é uma **nova hipótese prospectiva motivada pelo piloto**, não o efeito já demonstrado; não há nova busca nos mesmos dados para escolher outro limiar.
- `NOT_CANDIDATE` para composite, technical e fundamental significa que o contraste pré-registrado **não evidenciou separação neste piloto**; não prova ausência geral de poder discriminante (`technical` foi estimável com 10.000 réplicas definidas).

## 3. Regra candidata R1 (explícita; para certificação em shadow; não altera a v1)

- **R1 — Teto de risco na admissão da V2:** candidato elegível somente se `risk_score <= 44.10596901963097` (valor integral do corte c75 selado no passo 1; `44,106` é apresentação arredondada e **não** é o comparador), avaliado no instante da decisão sobre o mesmo campo persistido no snapshot; ausente ou não finito → **inelegível e contado**.
- **Hipótese pré-registrada de R1 (prospectiva):** na população de candidatos **antes** do filtro, com a **mesma geometria de R** (stop persistido) nos dois braços, p(+1R antes de −1R) dos **elegíveis** é maior que a dos **excluídos** por R1.
- **Regra de aprovação da certificação (a congelar na spec V1):** shadow prospectivo ≥ 15 sessões, mais maturação dos últimos candidatos; contraste elegíveis − excluídos com sorteio comum por sessão (seed 20260824, 10.000 réplicas), aprovado se o **LCB 98,75 % unilateral do contraste > 0**; orçamento de leituras pré-fixado (uma leitura decisória na 15.ª sessão e, sem aprovação, extensão única à 20.ª); réplicas indefinidas contadas como no protocolo; falha nomeada `V2_CERTIFICATION_FAILED_R1`. O LCB de p nos elegíveis, isolado, é **H1** (edge absoluto) e **não** certifica a vantagem relativa de R1; são leituras distintas com orçamentos distintos.
- **Sem ajuste posterior:** o limiar não é re-otimizado sobre os mesmos dados; outro limiar exige novo pré-registro.

## 4. Assinaturas

- Fable (redação, rev 2): 06/09/2026 13:46 BRT.
- Codex: ASSINADO — "DE ACORDO como hipótese candidata prospectiva" (PR #348, comentário 5560762942, 06/09/2026 14:01 BRT), sobre o texto `181127e8…`. **Escopo declarado:** aceita a candidata; **não congela o método de certificação do §3**. Antes da primeira sessão, a spec completa precisa explicitar: (a) scores nativos finitos em [0,100], sem coerção de bool/string; controle = somente risco válido acima do corte; inválidos contados fora dos dois braços; (b) coortes das primeiras 15/20 sessões, leitura só após maturação completa; (c) orçamento conjunto de leituras/endpoints; (d) dependência temporal compatível com o horizonte (reamostrar dias de entrada independentemente não preserva a dependência entre episódios de dias vizinhos com N = 10; seed e 10.000 réplicas não demonstram cobertura). A assinatura da candidata não é GO para coleta/implementação de spec incompleta.
- Dudu: ASSINADO sobre a rev 2 — "tou de acordo" (06/09/2026 13:51 BRT, no chat com o Fable; lavrado na PR #348); assinatura anterior sobre a rev 1 em 06/09/2026 13:28 BRT.

## 5. Adendo — semântica do `risk_score` entregue pelo Codex (5560762942; auditoria `risk-semantics.md` sha256 `d5d94ff5…`, 18/18 contraprovas por AST)

- Índice convencional de risco modelado, **maior = pior**; não é probabilidade calibrada de perda; não há fórmula única para todos os produtores. `clamp(x,a,b) = max(a, min(b, x))`.
- **Ações US (canônico/backfill, `one_pager.py:531–546`):** `clamp(32 + B + D + G + F − 8I − 8J − 6A, 15, 90)`, com B = `clamp((beta − 0,85)·24, −8, 25)`; D = `clamp((dívida/EBITDA − 1,5)·7, −8, 24)`; G = `min(16, |crescimento de lucro|·38)` só para crescimento negativo; F = 9 só para FCF negativo; I/J/A = sinais de insiders/instituições/analistas (acumulação/upgrades reduzem; distribuição/downgrades aumentam; ausência neutra). Há ramo de avaliação compartilhada que pode substituir o score.
- **ETF US:** `clamp(18 + 85·vol + 45·|max_drawdown|, 15, 85)`, vol = desvio populacional dos retornos diários × √252 (0,30 se < 20 retornos).
- **Fallback US provisório:** L = `clamp(48 + 18·log10(max(cash_volume/minimum, 1)), 40, 95)`; risco = `clamp(58 + 1,4·|variação do dia| − 0,18·(L − 50), 38, 70)`; mínimo alcançável 49,9 → **esse ramo nunca passa R1**. A composição histórica por fonte não foi medida.
- **B3:** fora do universo V2; fórmula própria (mercado 25 %, balanço 25 %, lucros 20 %, liquidez 10 %, governança 10 %, macro 10 %), não misturar com a US.
- **Campo correto para R1:** `decision_snapshot.risk_score` de nível superior; **não** `sizing_factors.risk_score` (arredondado a duas casas). A conversão legada aceita alguns tipos inválidos e pode substituir ausência por 55: o contrato novo valida explicitamente e não herda esse comportamento.
- Admissão v1 e composto de entrada conforme §1 (risco pode entrar no fundamental via `_power_score`; sem afirmação de independência).

*Registrado por Fable em 06/09/2026 14:02 BRT. Assinaturas a seis mãos completas sobre a candidata R1 (Fable rev 2; Dudu 5560710126; Codex 5560762942).*
