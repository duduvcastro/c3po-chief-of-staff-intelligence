# Pré-registro — Ensemble de valuation, backtest ponto-no-tempo US (`PREREG_VALUATION_ENSEMBLE_PIT_US_V1`, rev 2)

**Estado:** rascunho **rev 2**, 31/10/2026 (Fable). A rev 1 foi assinada pelo dono em 27/10/2026 às 09:59 BRT (recibo 6442500464; bytes `712b4c171c4d059a31156eba8f7a9624f1195083309471e89e0519271d2e5471`, commit `8b02ba0fbf715a9abb421eea6f00238aad5ef38d`), e a grade dela não pode terminar (§8). Nenhum relatório não-`VOID` leu rótulos: a leitura exige o manifesto completo do ensemble (§4, `ensemble_manifest_not_complete`), a grade da rev 1 nunca o completou e o preflight da PR #527 não lê rótulos. Por isso esta revisão é permitida. Ela fica vinculante como a rev 1: o `sha256` dos bytes deste arquivo, no commit de `main` que a introduz, é publicado num recibo no canal técnico, com a **assinatura do dono**, **antes da primeira corrida da nova época**. Depois do hash, qualquer mudança é uma nova revisão, permitida só enquanto nenhum relatório não-`VOID` tiver lido rótulos.

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
- **Demonstrações congeladas por seção (rev 2):** cada seção lê o store as-filed cortado no instante em que o rev 3 persistiu a sua corrida V3 irmã. Esse é o **corte de gravação** da seção.
  - **O instante:** a coluna `published_at` de `analysis_snapshots` no snapshot V3 cujo `cycle_id` o manifesto do rev 3 lista para a seção.
    - A coluna é NOT NULL. Um instante ausente, ilegível ou sem fuso recusa a seção (`ensemble_statements_cut_missing`).
    - Uma reexecução idempotente do rev 3 mantém o instante da primeira persistência, o mesmo das referências gravadas.
  - **O corte de gravação:** só entram as linhas de `statement_vintages` e de `statement_filings` com `first_seen_at` menor ou igual a esse instante.
    - As duas tabelas só aceitam inserção, por gatilho.
    - `first_seen_at` é o `now()` do banco no **início** da transação que inseriu a linha. Isso vale porque o único escritor, `statement_vintages.py` (no pino), usa o valor padrão da coluna; o esquema não o impõe.
  - **Sobre o store cortado,** valem as regras do leitor do rev 3:
    - o mapa símbolo → emissor, pela aceitação mais recente entre os documentos gravados até o corte de gravação;
    - a cobertura: um emissor com algum fato gravado até o corte de gravação;
    - os fatos aceitos até `T` e gravados até o corte de gravação.
  - **Comparação nome a nome:** vale para as ações admitidas, as Stocks do catálogo pinado com insumos na triagem do rev 3 em `T` (as chaves de `outputs.screen`), selecionadas ou não.
    - **Referência do rev 3:** a que as duas corridas irmãs (V3 e TP servido) gravam iguais para o nome. Uma divergência entre as irmãs recusa a seção antes de qualquer nome (`rev3_siblings_statement_references_mismatch`, como na rev 1). Por construção, toda ação admitida tem referência: a triagem do rev 3 só guarda os nomes cujos insumos resolveram em `T`, e no modo `--statements vintages` resolver exigia cobertura e gravava a referência.
    - **A seção é recusada (`statements_table_not_stable`) quando:**
      - a referência recalculada difere da que o rev 3 gravou;
      - um nome com referência do rev 3 não tem cobertura no corte de gravação;
      - entre os documentos do símbolo gravados até o corte de gravação, a aceitação mais recente é de dois ou mais emissores. Não há desempate.
    - **Dois casos que a construção do rev 3 não produz** seguem a rev 1: um nome com cobertura e sem referência recusa a seção (`rev3_statement_source_reference_missing_or_mismatched`); um nome sem referência e sem cobertura é não avaliável (`statement_vintages_missing`).
    - Uma recusa nunca é aceita.
  - **Evidência:** a regra é contrafactual e **não reconstrói** o que o rev 3 leu, que segue **desconhecido**. Mesmo assim, ela reproduz o que o rev 3 gravou, segundo o preflight só de leitura da PR #527 (run 41232203835 sobre a `main` `535a74aa`, 31/10/2026, comentário 6547910888):
    - nas **534 seções** do manifesto e nas **135.276** checagens por nome, sem nenhum dos casos de recusa por nome acima;
    - a leitura sem corte reproduz 518 seções; as 16 mais recentes, NASDAQ e NYSE de 2026-07-29 a 2026-09-17, são recusadas.
  - **Prontidão:** o preflight não é arquivo do instrumento. Antes da assinatura do pino, a checagem pinada tem de reproduzir as 534 seções numa corrida só de leitura (§6).
- **Ingestão as-filed (rev 2):** a ingestão (`C3PO_VALUATION_ASFILED_ENABLED`) e o backfill (`C3PO_VALUATION_ASFILED_BACKFILL_ISSUERS_PER_POLL`) podem estar ligados durante as corridas.
  - **Hoje:** a ingestão está ligada desde 31/10/2026 07:01 BRT, e o backfill está em 0 desde 27/10.
  - **Por que não importa:** toda escrita de agora tem `first_seen_at` depois do último corte de gravação (25/10/2026), então não entra em nenhuma seção.
  - **Saem do instrumento** as duas guardas da rev 1 que serviam à leitura viva:
    - a do workflow da grade, que exigia o backfill em 0 no worker em execução;
    - a espera do driver por uma coleta as-filed em curso (`asfiled_running`, dentro do `operational_guard`), que aguardava até 180 s e então recusava.
  - **Fica a regra do rev 3 §14,** no `operational_guard` que o executor chama antes e depois de cada seção: nenhum worker noturno de valuation e nenhuma ingestão em curso há 30 min ou mais. Uma ingestão assim impede o início de um trecho e interrompe o trecho em curso.
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
   - **recusa de seção do §2 (rev 2):** `statements_table_not_stable`, `rev3_siblings_statement_references_mismatch`, `rev3_statement_source_reference_missing_or_mismatched` e `ensemble_statements_cut_missing`. A seção não entra no manifesto, e o relatório anula por `ensemble_manifest_not_complete`. Aqui o código é a recusa do executor, não o `VOID` homônimo do rev 3 §2.

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
  2. **Pino do instrumento:** antes da **primeira corrida da época**, um recibo **`VALUATION-ENSEMBLE-INSTRUMENT-PIN-v1`** é publicado no canal técnico, com GO técnico do Codex e assinatura do dono. Ele lista:
     - o `prereg_sha256` e o `prereg_commit` deste documento;
     - **o commit de `main`** do instrumento;
     - o `sha256` de **cada arquivo** do instrumento: os módulos `c3po/backend/app/valuation_ensemble_*.py` (com as premissas dos 16 modelos e as 8 agregações), o leitor de consenso (`valuation_pit_rerun.py`), o módulo do relatório, o executor e o seu workflow;
     - as constantes deste documento (§4, §5, §1.3).
- **Garantias do pino:**
  - **um só pino por revisão:** um segundo pino exige nova revisão deste documento. A rev 2 tem o **seu** pino, no mesmo formato. A lista inclui o leitor congelado do §2 e o executor que o entrega a cada seção. O pino da rev 1 (`b77f2400…`, sobre o commit do instrumento `ac440626…`) não vale para a nova época;
  - **o executor recusa** correr se qualquer arquivo listado difere do pino;
  - **o relatório anula** (`VOID`: `ensemble_instrument_not_pinned`, `ensemble_instrument_mismatch:<arquivo>`) se não houver pino ou se o código de qualquer corrida do manifesto diferir dele, **antes de ler rótulos**;
  - assim, duas implementações com o mesmo texto não podem ambas reclamar este pré-registro. A que vale é a do pino, fixada antes dos rótulos.
- **Prontidão (rev 2), antes da assinatura do pino:** uma corrida só de leitura no host, sobre o checkout implantado cujo `instrument_files_sha256` é o do pino (`valuation_ensemble_readiness.py`, workflow `valuation-ensemble-readiness.yml`), aplica a cada uma das 534 seções a checagem pinada do §2.
  - **A checagem:** as mesmas funções que o executor chama antes de cada seção (`valuation_ensemble_frozen`), com o leitor congelado no corte de gravação da seção.
    - Só a leitura muda: os fatos de cada emissor são lidos uma vez e fatiados em cada `T` como a consulta do store os corta.
    - Nada é gravado, e a corrida não é um trecho da época.
  - **O escopo:** o pareamento das irmãs e as demonstrações. Preços, conteúdo do catálogo e Tesouro ficam com o executor, como na rev 1.
  - **A identidade:** a corrida publica o `sha256` canônico dos arquivos do instrumento no checkout implantado, este módulo entre eles, e recusa ler se os módulos em execução diferem dele. O que decide a checagem, a janela e o prazo está nesses arquivos; a conexão ao banco (`config.py`, `database.py`) fica fora, como no executor. O recibo do pino cita o run e esse `sha256`, que tem de ser o dos arquivos que o pino lista.
  - **A publicação:** no canal técnico, só contagens e rótulos de seção (bolsa e sessão), sem símbolos.
  - **A condição:** o pino só é assinado com 534 de 534 seções sem recusa. Com menos, não há GO nem assinatura do pino, e a época não começa. Mudar a regra exige nova revisão.
- **Operação:**
  - ordem do dono no formato das ordens da grade (`c3po/ops/owner-orders/<sha>.json`), com `from_session`/`to_session` (#485);
  - **nova época (rev 2):** ordem nova, pino novo e diário novo. Nenhuma seção calculada na época da rev 1 é reaproveitada: elas leram o store vivo, não o corte de gravação do §2. As 534 seções são recalculadas;
  - **a ordem da rev 1** (`08bf11a5…`, válida até 02/11/2026 08:00 BRT) fica revogada com a publicação do recibo do hash desta revisão: nenhum trecho da rev 1 corre depois dela. Quando as constantes da rev 2 chegarem à `main`, o executor recusa essa ordem sozinho, porque ela carrega o `prereg_sha256` e o pino da rev 1. Até lá, a revogação é de procedimento;
  - ingestão e backfill as-filed podem estar ligados, sem as guardas da rev 1 que serviam à leitura viva (§2);
  - autopiloto desligado;
  - sem deploy durante os trechos;
  - pré-checagem do host (`host-check`) com `blocking = 0` antes de cada trecho, a regra do rev 3 §14 repetida no §2. Com a ingestão as-filed ligada, `running` pode passar de 0.
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
- **Base contrafactual das demonstrações (rev 2):** o corte de gravação do §2 é uma regra, não a leitura histórica do rev 3.
  - **Premissa de relógio:** o `published_at` vem do relógio da aplicação, no contêiner `api`, e o `first_seen_at` vem do `now()` do Postgres, no contêiner `db`. Os dois rodam no mesmo host do compose e leem o mesmo relógio do kernel.
  - **Toda linha que o rev 3 viu está no corte:** a transação dela começou antes da leitura, e a leitura veio antes do `published_at`.
  - **O corte pode incluir linhas que o rev 3 não viu,** por dois caminhos:
    - o `published_at` é tomado do relógio da aplicação no `persist` (`valuation_pit_rerun.py`), depois do cálculo da corrida V3, então entra uma linha gravada entre a leitura do rev 3 e esse instante;
    - entra também uma transação que começou antes do instante e terminou depois dele.
  - **O preflight mediu essa janela com dois cortes mais cedo:**
    - `cut_lo`: o mais tarde entre o `published_at` da seção gravada logo antes e 60 min antes do da seção;
    - `cut_scan`: cada instante de gravação entre os dois, de um documento do símbolo ou de um fato dos seus emissores.

    As premissas do `cut_lo` são duas: cada seção foi lida depois de gravada a anterior (lotes em série, no grupo de concorrência `valuation-pit-backtest`), e no máximo 60 min antes da sua gravação. Os dois cortes deram 534 de 534, como o corte de gravação.
  - **Nunca como aceitação:** a referência guarda a contagem dos fatos lidos (`facts`) e o `statements_sha256`. Um fato a mais muda a referência, e um documento a mais que remapeie o símbolo muda o emissor ou a cobertura. Os dois casos aparecem como recusa (§2).

## 8. Revisões

**rev 2 (31/10/2026)**, antes de qualquer leitura de rótulos.

- **Motivo:** a grade da rev 1 não pode terminar.
  - Em 30/10 o lote 41123868230 e a sonda 41152230235 recusaram com `statements_table_not_stable`. A grade calcula as seções em ordem de data e grava cada uma no diário ao concluí-la. A sonda, com uma seção só, recusou a primeira seção ainda fora do diário.
  - Linhas gravadas no store as-filed depois da leitura do rev 3 (fatos aceitos até `T` ou documentos) mudaram as referências de seções recentes. A causa de cada uma não foi medida; as hipóteses são backfill, atraso de ingestão e reprocesso.
  - No store vivo, o preflight da PR #527 achou exatamente 16 seções que não reproduzem, as mais recentes; a primeira é NASDAQ 2026-07-29. As duas tabelas só aceitam inserção, então essas recusas são permanentes.
  - A contagem do diário da rev 1 não foi lida.
  - O Codex (6537212289) julgou NO-GO excluir seções e indicou que só uma nova época, com protocolo próprio, poderia mudar a base das demonstrações.
- **Decisão do dono, 31/10/2026:**
  - ~08:5x BRT: "Sim, começar", a nova época com os balanços congelados;
  - ~16:3x BRT: "pode começar o desenho da nova época do Valuation".
- **O que muda:**
  - cabeçalho e vínculo: o hash desta revisão, assinado pelo dono antes da primeira corrida da época;
  - §2: cada seção lê as demonstrações no seu corte de gravação, com as recusas nome a nome; ingestão e backfill as-filed podem estar ligados, e saem as guardas as-filed da rev 1;
  - §4: as recusas de seção das demonstrações;
  - §6: o pino, a ordem e o diário novos, a prontidão antes do pino, a revogação da ordem da rev 1, a pré-checagem do host sem o backfill pausado e as 534 seções recalculadas;
  - §7: a limitação da base contrafactual.
- **O que não muda:** pergunta, objeto, os 16 modelos, as 8 agregações e a primária, horizontes, estatística, as condições de `PASS`, `FAIL`, `UNMEASURED` e `NEGATIVE`, poder, constantes, fontes, os `T` do manifesto do rev 3 e a leitura única.

**rev 1 (26–27/10/2026):** primeira versão, assinada pelo dono em 27/10/2026 (recibo 6442500464).
