# Pré-registro — Ensemble de valuation, backtest ponto-no-tempo US (`PREREG_VALUATION_ENSEMBLE_PIT_US_V1`, rev 2)

**Estado:** rascunho **rev 2**, 31/10/2026 (Fable). A rev 1 foi assinada pelo dono em 27/10/2026 às 09:59 BRT (recibo 6442500464; bytes `712b4c171c4d059a31156eba8f7a9624f1195083309471e89e0519271d2e5471`, commit `8b02ba0fbf715a9abb421eea6f00238aad5ef38d`), e a grade dela não pode terminar (§8). Nenhum relatório não-`VOID` leu rótulos, então esta revisão é permitida. Ela fica vinculante como a rev 1: o `sha256` dos bytes deste arquivo, no commit de `main` que a introduz, é publicado num recibo no canal técnico, com a **assinatura do dono**, **antes da primeira corrida da nova época**. Depois do hash, qualquer mudança é uma nova revisão, permitida só enquanto nenhum relatório não-`VOID` tiver lido rótulos.

**Contexto (dono, 26/10/2026):**
- A grade do TP servido reprovou (`served_internal_tp` FAIL: IC executável 0,0167 em `h = 21`).
- O dono decidiu medir um **ensemble**: 16 modelos calculados das demonstrações oficiais (SEC/CVM) e do preço, mais o consenso dos analistas como **uma fonte a mais, nunca âncora**, em três agregações (média, mediana e média aparada a 20%), cada uma com e sem consenso.
- A primária pré-registrada é a **média sem o maior e sem o menor, com consenso** (`minmax_trimmed_mean_with_consensus`). O dono decidiu às 21:3x de 26/10: "fica na media sem o maior e sem o menor". Antes era a mediana com consenso.
- **Horizonte, decidido pelo dono às 21:0x de 26/10:** 6 meses decide e 12 meses é obrigatório.
- **Precisão (dono, 21:1x de 26/10):** "Ser maior não basta, tem q ser mais preciso"; "quero o mais preciso". O critério central é a **precisão**: o novo TP tem de errar **menos que o TP atual** o preço que a ação de fato atingiu. Ordenar melhor continua obrigatório e não basta.
- **Prazo do dono:** "precisamos adiantar isso"; leitura alvo na quarta 28/10.

**Herança:** tudo o que este documento não muda segue `PREREG_VALUATION_PIT_BACKTEST_US_V1` rev 3, que é a referência das seções citadas como "rev 3 §n":
- mercado, catálogo pinado, triagem PIT, demonstrações `--statements vintages` e safra de preços de 120 meses (§2);
- grade de instantes e relógio de `T` (§3);
- definições de upside, retorno executável `rx(h)` e corte dos rótulos (§4);
- métricas M1x/M2x e descritivas (§5);
- erros-padrão em blocos (§6);
- atrito, cobertura e integridade (§9);
- validade de uma leitura (§10);
- limitações (§11);
- recibo (§12);
- vínculo do código (§15).

## 1. Pergunta e objeto

1. **Pergunta primária:** a **média sem o maior e sem o menor, com consenso** do ensemble, calculada ponto-no-tempo em cada `T` da grade sobre os **mesmos insumos PIT** da reexecução do rev 3, é **mais precisa que o TP servido** (reexecutado sobre os mesmos `T` e nomes)? Isto é, ela erra menos o preço que cada ação de fato atingiu em 6 meses (`h = 126` sessões), com confiança estatística, e em 12 meses?
   - Além disso, o seu upside `u = tp / price − 1` **ordena** os retornos executáveis dos 6 meses seguintes no corte transversal triado dos EUA?
2. **Objeto medido:** os registros da fonte `ensemble_pit` gravados pelo modo grade do ensemble (`valuation_ensemble`, PR #487) para as corridas listadas no manifesto do ensemble, e só deles. Agregação primária: `minmax_trimmed_mean_with_consensus`: a média dos valores válidos depois de descartar **exatamente um** menor e **um** maior. Com 3 valores, é o do meio. O comparador é a fonte `official_internal_pit` do manifesto do rev 3.
3. **Modelos:**
   - os 16 modelos do código vinculado (§6), cada um com premissas explícitas no código;
   - cada modelo devolve um valor por ação **positivo** ou uma **razão de não avaliação**, contada e nunca preenchida;
   - **Regra do dono (26/10, 21:2x e 21:3x):** os valores que os modelos trouxeram, "tirando o menor e maior para não haver distorções", e então a **média** dos que sobram.
     - Uma ação entra na agregação com **≥ `MIN_MODELS = 3`** valores válidos, o mínimo em que existe um maior e um menor a descartar. Abaixo disso, a ação é não avaliável (`ensemble_fewer_than_min_models`) e é contada; nada é preenchido.
     - O consenso, quando presente, conta como um dos valores da variante com consenso.
     - O recibo publica a distribuição do número de valores por ação e a cobertura resultante.
   - **O consenso (P2-1 do Codex, 6430457023):** o `valuation_pit_served` **não** lê consenso. O leitor vinculado é o de `valuation_pit_rerun`, nas corridas V3 irmãs do manifesto do rev 3: mesma bolsa, mesmo `T`, mesmo snapshot de metas pinado no início da grade.
     - **Elegibilidade:** é a de `valuation_pit_rerun.consensus_at`: a última meta elegível de cada casa com `published_at ≤ T`, `publishedDate` sem fuso lida como UTC (premissa declarada `consensus_published_date_zone`), moeda pelo campo e **≥ 3 casas**.
     - **Valor do consenso no ensemble:** a **média** dessas metas por casa, porque o dono pediu "a média do consenso de todos os analistas". A mediana que o `consensus_at` grava (`public_consensus_tp`) é publicada ao lado, descritiva.
     - **Recibo:** registra, por nome e `T`, `analyst_count`, `consensus_published_at` (a meta mais recente usada) e o id do snapshot de metas.
     - **Sem consenso** (menos de 3 casas, B3, snapshot ausente): a variante com consenso usa só os modelos. A razão é contada (`consensus:<razão>`, as mesmas do `consensus_at`). Trocar o leitor ou o snapshot exige nova revisão;
   - nenhum valor futuro a `T`: demonstrações com `accepted_at ≤ T`, preço `close(D)`, consenso com `as_of ≤ T`.
4. **Agregações secundárias:** a mesma média sem o maior e o menor **sem consenso**; a mediana, a média e a média aparada a 20%, cada uma com e sem consenso. São sempre publicadas e nunca decisórias. Não há correção de multiplicidade porque só a primária decide.

## 2. Universo, dados e grade

- **Mesmo corte e mesmas fontes:** o mesmo corte transversal triado, o mesmo catálogo pinado, a mesma safra de preços, as mesmas demonstrações e a mesma curva do Tesouro **do manifesto do rev 3** (`manifest 73a81bce…`, passada final 40206452777).
- **Grade:** o ensemble é calculado nos **mesmos `T`** desse manifesto. Um `T` sem as duas corridas do rev 3 (TP servido e V3) não entra.
- **Sem republicação:** este documento não reabre a grade do rev 3 nem republica preços.
- **Demonstrações congeladas por seção (rev 2):** cada seção lê o store as-filed cortado no instante em que o rev 3 persistiu a sua corrida V3 irmã.
  - **O corte:** só as linhas de `statement_vintages` e de `statement_filings` com `first_seen_at ≤ published_at` do snapshot V3 da seção. As duas tabelas só aceitam inserção. `first_seen_at` é o `now()` do banco no **início** da transação que inseriu a linha.
  - **Sobre esse store cortado,** valem as regras do leitor do rev 3:
    - o mapa símbolo → emissor, com a aceitação mais recente entre os documentos gravados até o corte;
    - a cobertura: um emissor com algum fato gravado até o corte;
    - os fatos aceitos até `T` e gravados até o corte.
  - **Prova:** é uma regra contrafactual e **não reconstrói** o que o rev 3 leu, que segue **desconhecido**. Mesmo assim, o preflight só de leitura (PR #527, run 41232203835, 31/10/2026) mostrou que ela reproduz as referências do rev 3:
    - nas **534 seções** do manifesto e nas **135.276** checagens por nome;
    - a leitura sem corte reproduz 518; as 16 seções mais recentes, NASDAQ e NYSE de 2026-07-29 a 2026-09-17, recusam.
  - **A comparação continua exigida em toda seção:** a referência do rev 3 contra o recálculo sobre o corte. Uma divergência recusa a seção (`statements_table_not_stable`) e nunca é aceita.
- **Ingestão as-filed (rev 2):** pode seguir ligada durante as corridas, porque uma escrita posterior ao corte de uma seção não entra nela. A guarda do workflow que exige o backfill pausado permanece como defesa.
- **Horizontes:** `h = 126` (decisório), `h = 252` (condição obrigatória) e `h = 21`/`63` (descritivos). Para cada horizonte entram só os `T` cujo alvo `T + 1 + h` fechou antes do corte dos rótulos (rev 3 §6.2). A cauda da grade fica naturalmente de fora em `h = 126` e `h = 252`.

## 3. Estatística por horizonte

- **IC executável por sessão:** Spearman entre `u` e `rx(h)` no corte triado, com no mínimo 10 nomes (rev 3 §5, M1x). **Spread de decis executável** (M2x): mínimo de 30 nomes.
- **Blocos:** como no rev 3 §6, com o bloco = `h` sessões de calendário a partir de `GRID_START`:
  - em `h = 126`, blocos de 126 sessões. A grade tem ≈ 1.330 sessões e, com rótulo fechado em `h = 126`, ≈ 9 blocos completos;
  - estimativa = média das médias de bloco, `se = √1,5 · dp / √B`, t de Student com `B − 1` graus de liberdade. O fator 1,5 vale pelo mesmo argumento do rev 3 §6.3: a autocorrelação triangular `1 − k/h` com amostragem a cada 5 sessões dá correlação ≈ 0,25 entre blocos adjacentes.
- **Metades:** as primeiras e as últimas `⌊B/2⌋` médias de bloco, como no rev 3 §6.4.
- **Diferença pareada contra o TP servido:** em cada sessão, `ΔIC = IC_ensemble − IC_servido`, sobre a **interseção** dos nomes triados com os dois `u` e `rx(h)`. Média por bloco e estimativa como acima.
- **Persistência de 63 sessões:** não se aplica em `h ≥ 126`, porque o bloco já é mais longo que 63.
- **Precisão, o erro de cada TP:**
  - **Previsto:** o caminho do TP até o horizonte, interpolado geometricamente. Em log, `ŷ(h) = (h / 252) · ln(tp / price)`; em `h = 252` o previsto é o próprio TP (o TP é um alvo de 12 meses).
  - **Realizado:** `y(h) = ln(1 + r(h))`, com `r(h)` o retorno de fechamento ajustado do rev 3 §4 entre `D` e `D + h`.
  - **Erro de um nome:** `e = |y(h) − ŷ(h)|`, o erro absoluto em log.
- **Estatística de precisão por sessão:**
  - **Conjunto:** a interseção dos nomes triados com os dois TPs (ensemble primário e TP servido) e com `r(h)` disponível; no mínimo 10 nomes.
  - **Estatística:** `ΔE = mediana(e_servido) − mediana(e_ensemble)`. Positivo = o ensemble erra menos.
  - **Teste:** média por bloco e teste em blocos como acima (`√1,5`, t de Student com `B − 1` graus de liberdade).
- **Descritivo, nunca decisório:** o erro de "preço parado" (`ŷ = 0`, isto é, `e = |y(h)|`) e o `ΔE` de cada agregação secundária contra o TP servido e contra o preço parado.

## 4. Regra de decisão — leitura única

1. **`VOID`:** as causas do rev 3 §9, mais:
   - `ensemble_code_unbound`/`ensemble_code_mismatch`;
   - `ensemble_manifest_not_complete`;
   - `ensemble_sessions_not_rev3_sessions`;
   - `ensemble_inputs_differ_from_rev3` (outra safra, outro catálogo ou outra cobertura as-filed);
   - `statements_table_not_stable` (rev 2: a referência recalculada sobre o corte da seção, §2, difere da do rev 3);
   - `ensemble_statements_cut_missing` (rev 2: o snapshot V3 de uma seção sem `published_at` válido).

   Um `VOID` não lê rótulos.
2. **`UNMEASURED`:** qualquer uma das condições abaixo.
   - Atrito executável em `h = 126` acima de **`ATTRITION_CAP_126 = 0,15`**. É mais alto que os 0,10 de `h = 21` porque, em seis meses, há mais saídas de bolsa; o número é publicado.
   - Cobertura abaixo dos pisos do rev 3 §7.2, aplicados à primária: registros ÷ ações do catálogo **≥ 0,60**, e mediana dos nomes triados com `rx(126)` **≥ 150**.
   - **`B < MIN_BLOCKS_126 = 8`**.
3. **`NEGATIVE`:** `p_less ≤ 0,05` no IC executável da primária em `h = 126`.
4. **`PASS`** se e somente se valem **todas** as condições:
   1. `B ≥ 8` blocos completos de 126 sessões;
   2. estimativa do IC executável em `h = 126` **≥ `IC_MIN = 0,02`**, com **`p_greater ≤ 0,05`**;
   3. spread de decis executável em `h = 126` **> 0**;
   4. estimativa do IC executável **> 0 nas duas metades**;
   5. **condição obrigatória de 12 meses:** estimativa do IC executável em `h = 252` **> 0**;
   6. **ordena melhor que o TP servido:** estimativa da diferença pareada `ΔIC` em `h = 126` **> 0**;
   7. **mais preciso que o TP servido em 6 meses:** estimativa de `ΔE` em `h = 126` **> 0**, com **`p_greater ≤ 0,05`**;
   8. **mais preciso que o TP servido em 12 meses:** estimativa de `ΔE` em `h = 252` **> 0**;
   9. atrito em `h = 126` ≤ 0,15 e pisos de cobertura cumpridos.
5. **`FAIL`:** qualquer outro caso, com as condições não cumpridas listadas. "Não demonstrado" não prova ausência de sinal.

- **Leitura única:** a primeira execução não-`VOID` do relatório sobre o manifesto completo do ensemble, com código vinculado, **é** o veredito. Repetir sobre o mesmo manifesto reproduz o mesmo payload e não é outra olhada. Outro manifesto exige nova revisão (rev 3 §7).
- **O que um `PASS` faz (decisão do dono):** autoriza a promoção da primária a **preço-alvo único de todos os serviços**, com recibo publicado. Um `FAIL` mantém o TP atual, o ensemble segue em sombra e a próxima virada de método vai para a mesa.

## 5. Poder (leitura honesta)

- **Potência da condição 2, corrigida pelo P2-2 do Codex (6430457023):**
  - **Modelo:** com `B ≈ 9` blocos (8 graus de liberdade, t crítico 1,8595), passo 5 e o processo gaussiano triangular de 126 sessões herdado do rev 3.
  - **Resultado:** um IC verdadeiro de 0,05 em `h = 126` passa a condição 2 em **≈ 41 %, 25 % e 18 %** das vezes com `dp` por sessão de 0,10, 0,15 e 0,20.
  - **Fonte:** cálculo do Codex com 100.000 réplicas por covariância exata das médias de bloco; a revisão independente achou 41,3 / 24,7 / 18,0 %.
  - **Alcance:** são probabilidades **só da condição 2**. O PASS completo, com as condições 4 a 8, é **menos** provável.
  - **Leitura honesta:** o desenho tem **pouco poder**; um `FAIL` é o resultado mais provável mesmo com sinal real moderado. O dono decidiu medir assim.
- Abaixo de 0,03, o teste quase não detecta.
- A condição 6 exige ordenar melhor que o TP servido, cujo IC descritivo em `h = 126` na passada final foi **0,050** (`p` 0,057).
- A condição 7 exige erro **significativamente** menor que o do TP servido. Na grade de domingo, o nível do TP servido ficou pior que o preço parado (M3), então há espaço para melhorar. A potência dessa condição é publicada no `design_table()`, com o `dp` realizado de `ΔE`.
- O `dp` realizado por sessão é publicado para situar a leitura e não muda nenhuma constante.
- O código vinculado deve conter `design_table()` que reproduza estes números (`DESIGN_SEED = 20261026`, a mesma grade, covariância exata das médias de bloco) e a potência da condição 7 com o `dp` de `ΔE`. O recibo publica as duas.

## 6. Código, operação e recibo

- **Identidade do instrumento (P2-3 do Codex, 6430457023), vínculo em dois passos:**
  1. **Este documento** fixa as regras e é vinculado pelo hash dos seus bytes, com a assinatura do dono.
  2. **Pino do instrumento:** antes da **primeira corrida** do ensemble na grade, um recibo **`VALUATION-ENSEMBLE-INSTRUMENT-PIN-v1`** é publicado no canal técnico, com GO técnico do Codex e assinatura do dono. Ele lista:
     - o `prereg_sha256` e o `prereg_commit` deste documento;
     - **o commit de `main`** do instrumento;
     - o `sha256` de **cada arquivo** do instrumento: os módulos `c3po/backend/app/valuation_ensemble_*.py` (com as premissas dos 16 modelos e as 8 agregações), o leitor de consenso (`valuation_pit_rerun.py`), o módulo do relatório, o executor e o seu workflow;
     - as constantes deste documento (§4, §5, §1.3).
- **Garantias do pino:**
  - **um só pino por revisão:** um segundo pino exige nova revisão deste documento. A rev 2 tem o **seu** pino, no mesmo formato. A lista inclui o leitor congelado do §2 e o executor que o entrega a cada seção. O pino da rev 1 (`b77f2400…`, commit `ac440626…`) não vale para a nova época;
  - **o executor recusa** correr se qualquer arquivo listado difere do pino;
  - **o relatório anula** (`VOID`: `ensemble_instrument_not_pinned`, `ensemble_instrument_mismatch:<arquivo>`) se não houver pino ou se o código de qualquer corrida do manifesto diferir dele, **antes de ler rótulos**;
  - assim, duas implementações com o mesmo texto não podem ambas reclamar este pré-registro. A que vale é a do pino, fixada antes dos rótulos.
- **Operação:**
  - ordem do dono no formato das ordens da grade (`c3po/ops/owner-orders/<sha>.json`), com `from_session`/`to_session` (#485);
  - **nova época (rev 2):** ordem nova, pino novo e diário novo. Nenhuma seção calculada na época da rev 1 é reaproveitada: elas leram o store vivo, não o corte do §2. As 534 seções são recalculadas;
  - a guarda do backfill as-filed pausado permanece; a ingestão as-filed pode seguir ligada (§2);
  - autopiloto desligado;
  - sem deploy durante os trechos;
  - pré-checagem *running/blocking* do host (`host-check`) zerada antes de cada trecho.
- **Recibo:** `VALUATION-ENSEMBLE-PIT-REPORT-v1`, com:
  - os campos do rev 3 §12 por horizonte;
  - as oito agregações;
  - as diferenças pareadas contra o TP servido (`ΔIC` e `ΔE`) e o erro do preço parado;
  - contagens de não avaliação por modelo e por razão;
  - `prereg_sha256`.

## 7. Limitações declaradas

- **Seleção pelo resultado:** o catálogo de outubro/2026 escolhe os nomes pelo que eles se tornaram (rev 3 §11.2); vale igualmente para o TP servido, o comparador.
- **Poder baixo:** com ≈ 9 blocos em `h = 126` e ≈ 4 períodos independentes em `h = 252`. Um `FAIL` é frequente mesmo com sinal fraco real.
- **Consenso PIT:** o horizonte do consenso PIT não é atestado (rev 3, M4). Ele entra como valor, não como horizonte.
- **Lookback SEC de 10 anos** (rev 3 §2): os modelos de história longa só existem a partir de `GRID_START = 2021-06-01`, como no rev 3.
- **Base contrafactual das demonstrações (rev 2):** o corte do §2 é uma regra, não a leitura histórica do rev 3. Uma transação que começou antes do corte e terminou depois dele entra no corte, mesmo que o rev 3 não a tenha visto. O preflight não achou nenhum caso que mudasse uma referência (534/534). Se houver, ele aparece como recusa da seção, nunca como aceitação silenciosa.

## 8. Revisões

**rev 2 (31/10/2026)**, antes de qualquer leitura de rótulos.

- **Motivo:** a grade da rev 1 não pode terminar.
  - Em 30/10 o lote 41123868230 e a sonda 41152230235 recusaram com `statements_table_not_stable`: fatos aceitos antes do `T` de seções recentes foram gravados no store as-filed depois que o rev 3 o leu (backfill, atrasos, reprocessos).
  - O preflight da PR #527 mostrou 16 seções irreproduzíveis no store vivo; a grade parou em 393 de 534.
  - O Codex (6537212289) julgou NO-GO excluir seções e indicou que só uma nova época, com protocolo próprio, poderia mudar a base das demonstrações.
- **Decisão do dono:**
  - 31/10 ~08:5x BRT: "Sim, começar", a nova época com os balanços congelados;
  - ~16:3x BRT: "pode começar o desenho da nova época do Valuation".
- **O que muda:**
  - §2: as demonstrações de cada seção são congeladas no `published_at` do seu snapshot V3, e a ingestão as-filed pode seguir ligada;
  - §4: as causas de `VOID` das demonstrações;
  - §6: o pino, a ordem e o diário novos, com as 534 seções recalculadas;
  - §7: a limitação da base contrafactual.
- **O que não muda:** pergunta, objeto, os 16 modelos, as 8 agregações e a primária, horizontes, estatística, regra de decisão, poder, constantes, fontes, os `T` do manifesto do rev 3 e a leitura única.

**rev 1 (26–27/10/2026):** primeira versão, assinada pelo dono em 27/10 (recibo 6442500464).
