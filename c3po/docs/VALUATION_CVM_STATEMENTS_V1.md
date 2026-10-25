# Valuation — demonstrações completas da CVM (B3) e overlay campo a campo, V1

Frente "B3 completo" do Valuation como decisor de compra (direção do dono de 17/10/2026: demonstrações como
arquivadas, SEC XBRL para os EUA e CVM para a B3). Código: `app/cvm_fundamentals.py` (extrator, seção
"Complete statements"), `app/official_statements.py` (persistência e overlay), `app/cvm_statement_vintages.py`
(safras), `InvestorRelationsService.sync_cvm_statements` e a cadência em `app/ir_worker.py`.

## O que muda

- **Fontes.** ITR do ano corrente e do anterior, DFP dos dois anos anteriores (Dados Abertos da CVM,
  `CIA_ABERTA/DOC/{ITR,DFP}/DADOS`). Uma 404 (ano sem pacote ainda) é tolerada; os períodos que a corrida não viu
  ficam da snapshot anterior.
- **Demonstrações.** DRE (resultado), DVA (depreciação, amortização e exaustão, `7.04.01`), DFC pelo método
  indireto ou direto (caixa operacional `6.01`; capex = soma das linhas de investimento `6.02.xx` de aquisição/adição
  de imobilizado e intangível, nunca venda, resgate ou investimento em controlada), BPA/BPP e composição do capital.
- **Consolidado, ou individual quando não há consolidado.** Por emissor e pacote: quem aparece em qualquer arquivo
  `_con` nunca é lido dos `_ind`. No probe real do ITR 2026 são 222 emissores só com individual.
- **Contas por código E descrição.** Num banco `3.05` é resultado antes dos tributos e `2.02.01` são depósitos; o
  mapeamento legado por código os registra como EBIT e dívida. Aqui um campo cuja conta falta, ou que duas contas
  disputam, fica de fora — nunca é adivinhado. Banco e seguradora não têm receita, EBIT, EBITDA nem dívida neste
  leitor; o provedor continua a fonte desses campos.
- **Trimestres.** Linhas acumuladas do ano civil são diferenciadas (Q1 = acumulado; Qn = acumulado(n) −
  acumulado(n−1)); **Q4 = DFP do ano − nove meses do ITR**. Sem o acumulado anterior, só a linha trimestral avulsa
  (quando existe) preenche o trimestre — nunca uma diferença de seis meses rotulada como trimestre. Exercícios que
  não começam em 1º de janeiro ficam de fora, como no leitor legado.
- **Como arquivado.** Para cada período vence o documento do próprio período (DT_REFER = fim do período) sobre o
  comparativo de um documento posterior (possivelmente reapresentado), depois a maior versão. `periodDocuments`
  registra documento, versão e `receivedOn` (DT_RECEB) de cada período; `published_at` é o recebimento do documento
  do `as_of`, no **fim desse dia em São Paulo** (a CVM publica uma data, não um instante; o mesmo critério do
  `accepted_at` das safras). Recebimento desconhecido fica `null`: nunca o relógio da coleta e nunca herdado de outro
  documento — quando o `as_of` avança, ou a mesma data vem numa versão nova, `published_at` e `source_url` são os do
  documento novo, mesmo nulos; só a mesma versão do mesmo documento conserva o recebimento já visto.
- **EBITDA = EBIT (DRE, resultado antes do resultado financeiro e dos tributos) + D&A (DVA)**, só quando os dois
  existem no trimestre. Conferido no probe real: UNIP6 2T26 dá 386,2 mi (release: 386 mi).
- **Patrimônio.** `totalEquity` = PL consolidado; `totalStockholderEquity` = PL − participação de não
  controladores (semântica do EODHD; o leitor legado usava o PL com minoritários).

## Defeito do overlay e a correção

`official_fundamentals.apply_official_fundamentals` troca a linha trimestral do provedor pela oficial **inteira** e
soma o campo nas quatro linhas mais novas que o tenham. A linha do ITR não tem EBITDA: com dois trimestres oficiais
e dois do provedor, o EBITDA TTM cai à metade e o EV/EBITDA dobra (teste
`test_legacy_overlay_halves_ttm_ebitda_and_doubles_ev_ebitda_and_stays_pinned`).

`official_statements.apply_official_statements` (overlay campo a campo):

1. a linha oficial sobrescreve só os campos que traz; os demais campos do provedor no mesmo período ficam;
2. todo TTM exige **quatro trimestres consecutivos que tenham o campo**; senão o valor do provedor permanece (e as
   razões derivadas dele não são recalculadas);
3. capex TTM soma tamanhos (CVM e releases arquivam negativo, linhas do provedor podem vir positivas);
4. uma só fonte oficial por símbolo: **as demonstrações completas sempre que o símbolo as tiver**; o legado (também
   campo a campo) só para símbolo sem demonstrações completas. Nunca uma mistura de linhas das duas, para que os
   valores de banco do leitor legado não voltem; as `official_metrics` do legado (p.ex. EBITDA ajustado de um release)
   são mantidas sob as das demonstrações. O sync legado relê o ITR a cada 30 min e a coleta completa roda a cada 24 h:
   se o legado vencesse quando um trimestre à frente, a cada ITR novo um banco passaria a servir `3.05` como EBIT,
   depósitos como dívida e PL com minoritários até a coleta seguinte (EV, ROE e P/VPA oscilando). O atraso custa
   frescor, não correção: demonstrações mais antigas que o trimestre do provedor deixam o provedor no lugar. Para
   encurtar o atraso na temporada de resultados, `C3PO_CVM_STATEMENTS_INTERVAL_HOURS` desce até 6.

**`official_fundamentals.py` não muda.** O diferencial de risco do R2D2 V2 fixa os bytes do arquivo
(`r2d2_v2_risk_differential.ORIGIN_PINS`, `ORIGIN_AUXILIARY_CHANGED`) e `r2d2_v2_risk_bundle` usa a função: alterar o
arquivo quebraria a prova e mudaria os insumos de risco do R2D2. Pelo mesmo motivo nada aqui toca `one_pager.py`
(fixado por `ORACLE_ONE_PAGER_SHA256`): **o One Pager continua no overlay legado.** O decisor deve chamar
`apply_official_statements_map` diretamente.

**Antes de ligar `C3PO_VALUATION_CVM_FIELDWISE_OVERLAY_ENABLED`.** Com a chave ligada, o screener B3 serve o overlay
campo a campo e o One Pager (e o `r2d2_v2_risk_bundle`) seguem no legado: o mesmo símbolo sai com EV/EBITDA diferente
nas duas telas (no caso sintético do teste, 2,68 no screener e 5,5 no One Pager). A chave só deve ser ligada depois de
uma destas decisões do dono: (a) repin do One Pager (`ORIGIN_PINS`/`ORACLE_ONE_PAGER_SHA256`) para ele chamar
`apply_official_statements_map`, ou (b) o One Pager deixar de exibir EV/EBITDA e TTM do overlay e o decisor ser a
única leitura. O `r2d2_v2_risk_bundle` fica no legado por desenho (insumo fixado do R2D2 V2) até uma nova versão do
diferencial de risco.

## Chaves (variáveis de ambiente, não `Settings`)

`config.py` entra no hash do pacote de implementação do R2D2 V2 (`r2d2_v2_earnings_package.PACKAGE_FILES`); uma linha
nova ali muda o `implementation_package_sha` amarrado à release e à configuração de capacidade. As chaves são lidas
do ambiente, como as dos produtores do R2D2 V2 (`C3PO_R2D2_V2_PRODUCERS_ENABLED`):

| variável | padrão | efeito |
|---|---|---|
| `C3PO_VALUATION_CVM_FIELDWISE_OVERLAY_ENABLED` | desligada | o screener B3 serve o overlay campo a campo (`B3ScreenerService._eodhd_fundamentals_with_receipts`); só `true` liga |
| `C3PO_VALUATION_CVM_FIELDWISE_OVERLAY_SHADOW` | desligada | o ciclo noturno B3 calcula também a variante campo a campo, ao lado da servida, e grava uma snapshot agregada por ciclo (`app/valuation_env.py`; ver Rollout) |
| `C3PO_CVM_STATEMENTS_CAPTURE_ENABLED` | ligada | o IR worker coleta as demonstrações completas (tipo `official_statements`, lido só pelo overlay acima) e captura safras |
| `C3PO_CVM_STATEMENTS_INTERVAL_HOURS` | 24 (6 a 336) | espaçamento das coletas; conta a partir do último sucesso, sobrevive a reinícios |

Com a primeira chave desligada nenhum número servido muda. A coleta grava em `analysis_snapshots`
(`analysis_type = official_statements`, uma snapshot por símbolo só quando algo mudou; append-only).

## Correção ponta a ponta (verificação de 19/10/2026)

Testes em `tests/test_valuation_cvm_overlay_shadow.py` (arquivos sintéticos da CVM no layout real, `cvm_statement_fixtures.py`).

- **Precedência por campo.** CVM consolidado > CVM individual (só para emissor sem nenhum consolidado; escopo por
  emissor, nunca misturado entre campos) > EODHD. A linha oficial sobrescreve só os campos que traz no mesmo período; o
  campo que a CVM não traz fica o do EODHD. Banco/seguradora: receita, EBIT, EBITDA e dívida ficam do provedor.
- **Trava de recebimento (uma trava, não uma leitura no ponto do tempo).** `official_overlays(..., as_of=)` lê a
  **última** snapshot — nunca a que vigorava num instante passado — e a recusa se foi gravada depois do corte ou se
  **qualquer** documento que contribuiu para ela só fica disponível depois do corte: toda versão de ITR/DFP de cada
  período (DRE, DVA, DFC, balanço e o acumulado anterior contra o qual o trimestre foi diferenciado;
  `periodDocuments[*].contributing`). Disponível = **fim do dia de recebimento** (`DT_RECEB`) em São Paulo, a convenção
  do produtor (`published_at`, `accepted_at` das safras). Recusada a última, vale a anterior que a trava admitir (até 3),
  para o símbolo não voltar às linhas do legado pelo resto do dia; senão o legado, recusado do mesmo jeito pelo seu
  `published_at`; senão o provedor. Recebimento desconhecido não recusa. No ciclo noturno nada é descartado (documentos
  do dia ficam disponíveis à meia-noite); contado na sombra (`receipt_guard_excluded`).
- **EBITDA.** EBIT (DRE) + |D&A| (DVA `7.04.01`) por trimestre; TTM só com quatro trimestres consecutivos que tenham o
  campo. No mesmo pacote sintético, o legado serve 60 mil (dois trimestres do provedor: a metade) e o campo a campo serve
  134 mil (quatro trimestres CVM), com o EV/EBITDA recalculado.
- **Unidades.** `VL_CONTA` × escala: `MIL` × 1.000, `MILHAO`/`MILHOES` × 1.000.000, `UNIDADE` × 1; só `MOEDA = REAL`. O
  mesmo trimestre arquivado em `MIL` e em `UNIDADE` dá os mesmos reais — a unidade do EODHD. A composição do capital não
  tem coluna de escala (quantidade de ações): ações CVM a 100× ou mais das do EODHD são ignoradas (fica o EODHD) e
  contadas (`shares_scale_skipped`); o screener já troca por ações implícitas (valor de mercado ÷ preço) quando a pista
  diverge mais de 30 %.
- **Documentos reapresentados.** Nova `VERSAO` do mesmo documento vence a anterior (no extrator e na snapshot que o
  overlay lê, na coleta seguinte, com o seu próprio `receivedOn`); o documento do próprio período vence o comparativo
  reapresentado de um documento posterior (como arquivado).

**Defeitos encontrados e corrigidos (nenhum arquivo congelado tocado):**

1. **Trimestre servido como ano (fluxo de caixa).** O `freeCashflow`/`operatingCashflow` de topo do EODHD é o do
   **último trimestre** (`eodhd._latest_statement`), e com qualquer overlay o screener lê esses campos do payload
   sobreposto em vez do TTM da Brapi. O overlay campo a campo deixava esse trimestre no lugar, servido como TTM (FCF ÷ 4
   no DCF e no yield) — sem janela completa e também quando o overlay não se aplica (sem overlay, ou mais antigo que o
   provedor). Agora, em todos os casos: janela completa só de trimestres CVM; ou uma janela que use trimestres do
   provedor, só se a série do provedor passar a trava abaixo; ou o TTM do próprio provedor que passe a trava; senão o
   campo fica de fora (o nome pode então cair no portão de FCF positivo — a sombra conta em `names.only_before`).
2. **Trava do fluxo de caixa do provedor.** Se as linhas trimestrais de caixa do EODHD `.SA` forem acumuladas no ano
   (como a DFC da CVM), quatro delas somam 1T + 1S + 9M + ano (prova do revisor: 20/10/40/30 → 100 servidos contra 30
   reais). A série do provedor só é aceita se **não parecer acumulada** (tamanho subindo a cada trimestre dentro do
   exercício e voltando no 1T seguinte) **e**, quando a janela termina no fim do exercício (dezembro), se o TTM bater em
   até 5 % com o anual do próprio provedor (`annualCashFlow` normalizado ou `Financials.Cash_Flow.yearly`). O payload
   normalizado de hoje não traz o anual de caixa (`eodhd.py`, congelado esta semana): janela que termina em dezembro cai
   fora até lá. Cada disparo é contado no recibo (`cash_flow_guard`: `cumulative`, `annual_missing`, `annual_mismatch`,
   por campo × nome). **Conferir um payload `.SA` real na primeira noite da sombra** (as linhas `Cash_Flow.quarterly` são
   trimestres avulsos ou acumulados?) antes de aceitar o recibo.
3. **Trava de recebimento implícita.** O overlay lia a última snapshot sem conferir recebimento nem instante de
   gravação; agora a trava acima é verificada (`official_overlays`), documento por documento.
4. **Ações fora de escala.** Ações CVM a 100× ou mais das do EODHD são ignoradas e contadas (`shares_scale_skipped`).

**Observações (não corrigidas aqui):**

- Com overlay (legado ou campo a campo) o screener passa a ler ROE, margens, D/E, FCF, caixa, dívida, receita e EBITDA
  do payload sobreposto, não da Brapi (`B3ScreenerService._prepare_rows`, ramo `official_fundamentals`). É anterior a
  esta frente; a sombra mede o efeito total, não só o das linhas da CVM.
- Q4 e o TTM misturam um DFP reapresentado com os nove meses originais do ITR quando o emissor reapresenta o ano (limite
  já descrito abaixo); o TTM de dezembro é o DFP exato.
- Sem `Highlights`, o EODHD cai para a receita/EBITDA do último trimestre (`eodhd.py`, congelado esta semana): afeta o
  fallback do provedor, não as linhas da CVM.

## Rollout: sombra → recibo → aceite do dono → ligar

Nada servido muda até o passo 4. Toda chave é variável do repositório (não segredo), validada `^(true|false)$` e gravada
na `.env` do host pelo passo `Stage host env settings` do `c3po-pipeline.yml` no próximo deploy; variável vazia não
grava nada (a `.env` mantém o que tem) — para desligar, defina `false`.

1. **Sombra.** `C3PO_VALUATION_CVM_FIELDWISE_OVERLAY_SHADOW=true` (e `C3PO_VALUATION_CVM_FIELDWISE_OVERLAY_ENABLED`
   vazia ou `false`); deploy. Só o **ciclo noturno** do `valuation-worker` (`B3ScreenerService(nightly_cvm_shadow=True)`)
   roda a sombra — nunca o build completo frio de outro processo nem o de `refresh_symbols`. O build entrega ao
   `ShadowCapture` os mesmos payloads EODHD que consumiu, no mesmo instante; depois de publicar o ciclo servido, **uma
   chamada** avalia o universo três vezes com o mesmo catálogo, cotações, Brapi, histórico, macro e consenso **e com as
   mesmas leituras do banco e o mesmo instante do passe servido** — eventos de RI, atividade de insiders e o corte,
   gravados uma vez pelo passe servido e reaproveitados nas três variantes (uma escrita do IR worker entre o ciclo e a
   sombra nunca é atribuída à CVM; achado do Codex na #459):
   **antes** (os fundamentos servidos, recalculados ali — o recibo diz quantos batem com as linhas do ciclo publicado em
   TP interno, buy-in interno e status, `before_vs_served`, e em todos, `names.before_matches_served`), **só a correção do fluxo de caixa** (sem linha CVM, para essa correção não ser
   atribuída à CVM) e **depois** (overlay campo a campo). Grava **uma** snapshot `analysis_snapshots`
   (`analysis_type = valuation_cvm_overlay_shadow`, entidade `B3_UNIVERSE`):
   - `aggregate` (sem nenhum símbolo): `n`, mediana e p90 de `variante/referência − 1` e do módulo — TP e buy-in
     internos depois/antes, TP só a correção/antes (`cash_flow_fix_internal_tp`) e depois/só a correção
     (`cvm_rows_internal_tp`); contagem de nomes por campo com origem `cvm`/`eodhd`/`mixed`/`absent`; disparos da trava
     do fluxo de caixa; EBITDA que muda (> 1 %), com a assinatura do defeito da metade no legado e corrigidos; origem do
     overlay (`statements`, `legacy`, `stale` = mais antigo que o provedor e não aplicado, `none`);
     `receipt_guard_excluded`; `shares_scale_skipped`; hash do detalhe privado. `report_sha256` = hash canônico do
     agregado; `producer_build_sha` = `C3PO_BUILD_SHA` do processo que o calculou; `attestation_sha256` = hash do
     agregado com o produtor (o recibo recusa se qualquer um dos dois não recalcular);
   - `private_detail` por símbolo (TP e buy-in internos do ciclo servido, antes, só a correção e depois; EBITDA,
     origens): fica no banco do host, nunca sai.
   O tipo não é ciclo, registro de predição nem selecionável. Qualquer falha é registrada no log e o build segue. Os
   números do agregado são arredondados a 8 casas e nunca `-0,0` (o `numeric` do PostgreSQL não tem zero negativo).
2. **Recibo.** Disparar `valuation-readonly-report.yml` com `report = cvm-before-after`. Lê só leitura
   (`PGOPTIONS default_transaction_read_only=on`, `docker compose exec` no `api` em execução) a última snapshot da
   sombra, recalcula o `report_sha256` e o `attestation_sha256` (têm de bater com os gravados), anexa a identidade da snapshot, a revisão que
   produziu (`producer_build_sha`) e a que leu (`reader_build_sha`), tudo sob `receipt_sha256`. O runner confere as
   chaves exatas de cada bloco (nenhum bloco pode ser indexado por símbolo), os dois hashes e as duas revisões; o resumo
   em português é renderizado por um segundo exec e só é publicado se a revisão que o renderizou for a que leu o recibo.
   Artefato: `valuation-cvm-before-after-<run>` (`report.json`, `summary.md`, `metadata.json`, `SHA256SUMS`).
3. **Aceite do dono.** O dono lê o resumo e aceita citando o `report_sha256`. Pré-condição já descrita acima: decidir
   o One Pager (a) repin para `apply_official_statements_map` ou (b) deixar de exibir EV/EBITDA/TTM do overlay.
4. **Ligar.** `C3PO_VALUATION_CVM_FIELDWISE_OVERLAY_ENABLED=true`; deploy. A sombra pode ficar ligada: antes e depois
   passam a ser o mesmo overlay e o agregado vira uma verificação de identidade (`served_overlay = fieldwise`, zero
   mudanças); ou `C3PO_VALUATION_CVM_FIELDWISE_OVERLAY_SHADOW=false`. Reverter: `ENABLED=false` e deploy.

`C3PO_CVM_STATEMENTS_CAPTURE_ENABLED` (padrão ligada) precisa continuar ligada em todos os passos: sem a coleta não há
demonstrações para a sombra comparar. Não é gravada pelo pipeline (só na `.env` do host, se for preciso desligar).

## Safras (migração 051 da frente XBRL: `statement_filings` + `statement_vintages`)

Os dumps abertos da CVM guardam **só a última versão** de cada documento (no probe do ITR 2026: 59 documentos com
mais de uma versão no índice, nenhum com mais de uma versão nas demonstrações). As tabelas e o escritor
(`app/statement_vintages.StatementVintageStore`) são da frente XBRL e valem para os dois mercados; aqui
`app/cvm_statement_vintages.CvmVintageCapture` só traduz as linhas da CVM e delega:

- **filing** por documento entregue: `doc_id` = `ID_DOC` da CVM (um por versão, como um accession da SEC),
  `document_version` = `VERSAO`, `form` ITR/DFP, `filed_date` = `DT_RECEB`. A CVM publica uma DATA de recebimento,
  não um instante: `accepted_at` = **fim desse dia em São Paulo** (`accepted_source = cvm_dt_receb_end_of_day`), para
  que uma leitura no tempo nunca veja o documento antes de ele existir;
- **fato** por linha: `concept = cvm:<demonstração>_<escopo>:<CD_CONTA>:<DS_CONTA>` (o código se repete entre
  layouts; a descrição é como o emissor chamou a linha), `unit` BRL, `value` = `VL_CONTA` × escala; balanço é
  instante (sem `period_start`); capital em `cvm:composicao_capital:<coluna>`, em ações. Ficam as linhas de nível
  ≤ 2 (todas as contas que o extrator lê), últimas e penúltimas (o comparativo reapresentado é parte do documento);
  as linhas mais profundas (~60% do volume) não.

Pacotes em ordem cronológica (DFP ano−2, ITR ano−1, DFP ano−1, ITR ano), para o store ver os documentos de cada
emissor em ordem de aceitação (`is_first_publication`). Um documento só é registrado em `statement_filings` depois
que o pacote inteiro foi gravado, e **nunca quando qualquer fato dele foi recusado pelo store**: a corrida seguinte
abre a captura com os documentos registrados e os salta, então registrar um documento com fatos faltando perderia o
original para sempre assim que a CVM o substituísse no dump. Uma corrida que morre no meio, ou cujo store recusou uma
escrita, refaz esses documentos inteiros na próxima (a chave natural torna os fatos já gravados um no-op) e nunca os
pula.

**No-op enquanto o store não foi mergeado ou as tabelas não existem**, com o motivo no `error_summary` da corrida
(`ingestion_runs`, fonte `cvm_statements`, status `succeeded`). Escrita recusada pelo store não derruba a corrida
(as demonstrações já foram gravadas), mas a marca **`partial`**, com o número de falhas e de documentos deixados
para a próxima corrida no `error_summary`, e emite um `logger.error` (evento no Sentry), para não ficar só gravada.
O teste de integração com o store real (`test_capture_against_the_real_051_store_once_merged`) é pulado até o merge
e passa a correr sozinho depois; foi exercitado contra o rascunho da frente XBRL de 17/10 e passou.

**Com a frente XBRL no mesmo deploy, a captura deixa de ser no-op no primeiro arranque.** `Database.initialize()`
aplica a 051 em todo processo que sobe, e `C3PO_CVM_STATEMENTS_CAPTURE_ENABLED` vem **ligada**: o primeiro laço do
worker de IR depois do deploy roda `cvm_statements` (nenhuma corrida bem-sucedida → vence já). Essa primeira corrida
é a maior — quatro zips da CVM e todas as linhas de nível ≤ 2 de todo emissor B3 mapeado —, grava linhas B3 em
`statement_filings`/`statement_vintages` que os gatilhos tornam **permanentes** (sem UPDATE, DELETE nem TRUNCATE;
`is_first_publication` fixado na inserção) e atrasa, pelo tempo que levar, a próxima volta de 15 min do SEC/insiders
no mesmo laço. Nenhum número servido muda com o overlay desligado. Se a mesa não aprovou começar a guardar as safras
B3 no deploy, definir `C3PO_CVM_STATEMENTS_CAPTURE_ENABLED=false` no host antes de subir.

## Limites conhecidos

- Exercício social fora do ano civil: DVA/DFC (só acumulados) não são trimestralizados; a DRE só pelos avulsos.
- Uma reclassificação de trimestre anterior feita no acumulado seguinte entra no trimestre seguinte (diferença
  contra o acumulado como arquivado). Ex.: UNIP6 caixa operacional 1T26/2T26 = 299,2/318,6 mi (CVM) contra
  185,2/432,7 mi do release; o semestre (617,8 mi) confere.
- Capex é texto livre na DFC: o classificador pegou 456 de 631 emissores no probe; sem linha classificável não há
  capex nem FCF (o provedor permanece).
- Ações em circulação = total integralizado − tesouraria do documento mais recente até o `as_of`.
