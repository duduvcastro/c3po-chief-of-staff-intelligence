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
| `C3PO_VALUATION_CVM_FIELDWISE_OVERLAY_ENABLED` | desligada | o screener B3 serve o overlay campo a campo (`B3ScreenerService._eodhd_fundamentals_with_receipts`) |
| `C3PO_CVM_STATEMENTS_CAPTURE_ENABLED` | ligada | o IR worker coleta as demonstrações completas (tipo `official_statements`, lido só pelo overlay acima) e captura safras |
| `C3PO_CVM_STATEMENTS_INTERVAL_HOURS` | 24 (6 a 336) | espaçamento das coletas; conta a partir do último sucesso, sobrevive a reinícios |

Com a primeira chave desligada nenhum número servido muda. A coleta grava em `analysis_snapshots`
(`analysis_type = official_statements`, uma snapshot por símbolo só quando algo mudou; append-only).

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

## Limites conhecidos

- Exercício social fora do ano civil: DVA/DFC (só acumulados) não são trimestralizados; a DRE só pelos avulsos.
- Uma reclassificação de trimestre anterior feita no acumulado seguinte entra no trimestre seguinte (diferença
  contra o acumulado como arquivado). Ex.: UNIP6 caixa operacional 1T26/2T26 = 299,2/318,6 mi (CVM) contra
  185,2/432,7 mi do release; o semestre (617,8 mi) confere.
- Capex é texto livre na DFC: o classificador pegou 456 de 631 emissores no probe; sem linha classificável não há
  capex nem FCF (o provedor permanece).
- Ações em circulação = total integralizado − tesouraria do documento mais recente até o `as_of`.
