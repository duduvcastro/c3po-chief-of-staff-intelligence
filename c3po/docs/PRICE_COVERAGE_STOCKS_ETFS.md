# Série de preços: todas as ações e ETFs dos mercados suportados

Pedido do proprietário em 11/09/2026: ampliar os 1.047 símbolos da W3 para
“todas as acoes, ETFs apenas”. O histórico continua com 36 meses. Essa cobertura
é da série de preços; não altera a elegibilidade de recomendações ou ordens.

## Seleção e manutenção

`C3PO_VALUATION_PRICE_HISTORY_SCOPE=stocks_etfs` seleciona o catálogo completo,
tanto no backfill quanto em cada fase noturna. O padrão `monitored` preserva o
comportamento implantado até a ativação coordenada. A flag de habilitação da
fase continua sendo `C3PO_VALUATION_PRICE_HISTORY_ENABLED`.

* B3: catálogo Brapi paginado integralmente, subtipos stock, unit e etf. ON/PN
  estão incluídas; aliases fracionários não duplicam a mesma ação. Exclui BDRs,
  FIIs, outros fundos e índices. EODHD complementa ações/units ausentes da Brapi
  somente com identificação positiva por classe ISIN ACN/CDA/UNT. Tipo ETF do
  EODHD isolado não basta para distinguir ETF doméstico de certificado.
* Nasdaq: Common Stock, Preferred Stock e ETF, sem filtro de liquidez, tamanho,
  preço, ranking ou quantidade. ADRs classificados como ações negociadas nos
  EUA permanecem nesse universo; BDRs brasileiros estão fora.
* NYSE: os mesmos tipos, incluindo as praças Arca e American/AMEX/MKT, registradas
  individualmente no manifesto e agrupadas no mercado lógico NYSE do C3PO.
  Cboe/BATS, OTC e outras bolsas não pertencem a esses três mercados suportados.
* Identidade conflitante entre duplicatas recusa a seleção. Instrumentos sem
  classificação positiva, com moeda incompatível ou fora do escopo são
  contabilizados por motivo. Um ativo da Brapi ausente do catálogo EODHD é
  solicitado e marcado `provider_listed=false`; não se inventam barras.

Falha, página incompleta, total variável ou duplicação durante a paginação
recusam a coleta antes das barras; não há retorno silencioso ao screener. O
catálogo é renovado por dia UTC. Cada captura publica metadados `coverage`,
incluindo política, hash do catálogo, hash e identidades da seleção, exclusões,
legado não selecionado e franquia observada. Credenciais, nomes e dados da conta
não são incluídos. Esses metadados não substituem os hashes das barras/séries.

Uma ação/ETF positivamente classificada na captura anterior publicada continua
solicitada se desaparecer do catálogo, evitando que o recorte encolha a cada
noite. Uma exclusão explícita no catálogo corrente prevalece e fica registrada.
O histórico persistido não é apagado. Isso não equivale a reconstruir o universo
de ativos deslistados dos 36 meses: permanece a limitação de sobrevivência do
catálogo inicial ativo.

## Consumo e escala

Uma janela completa por mercado, uma captura e uma publicação. Não publicar
lotes de símbolos separados: o leitor resolve uma única safra por mercado.
O leitor e as regras de relógio, deduplicação, publicação e fase única continuam
iguais. A detecção de sessões desaparecidas usa índice por símbolo para evitar
varrer todo o mercado para cada ativo.

Antes de cada mercado, o produtor consulta a franquia ordinária e exige saldo
para todas as tentativas configuradas mais reserva de 10.000 chamadas. A cota
extra não entra nessa conta. A cadência é no máximo 240 requisições iniciais por
minuto (reduzida com mais retries); no padrão de dois retries, até 720 tentativas
por minuto deste produtor. Outros serviços usam a mesma conta: reconferir o
consumo ao fechar cada mercado. Não há reserva atômica entre consumidores.

A implementação ainda mantém as barras de um mercado em memória. Inventário
de 11/09: host com ~30 GB disponíveis e ~641 GB livres; dimensionar o pico do
maior mercado antes da execução. Rodar um mercado por vez, nunca paralelizar
backfill com o worker noturno ou deploy. Limite de segurança: 20.000 símbolos
por mercado recusa o run inteiro; não trunca a cobertura. Esses valores de
inventário são evidências históricas, não uma autorização permanente.

## Execução e recibos

1. Encerrar a fila de deploys e fixar a revisão final revisada, imagens, compose,
   `.env`, IDs/StartedAt dos dez contêineres e processos. Verificar worker ocioso,
   nenhuma fase de preços em voo, API sem settings R2D2_V2, V1 pausada e época
   DIAGNOSTIC intacta. Guardar totais e safra publicada anterior de cada mercado.
2. Registrar horário e revisão na #348. Ativar somente o escopo de preços no
   valuation-worker e recriar somente esse contêiner, com readback. Nenhum DDL,
   alteração de outra flag ou operação R2D2 integra esta mudança.
3. Conferir o catálogo/seleção efetivo e o saldo ordinário. Executar a CLI
   existente, um mercado por vez: `python -m app.valuation_price_history --market
   B3 --backfill --months 36` (depois NASDAQ e NYSE), sem `--symbols`, sob o escopo
   novo. Usar supervisor com limite de tempo e recibo privado durável; não repetir
   uma captura incerta antes de reconciliar o banco.
4. Conferir por leitura as duas novas linhas de captura/publicação, os três
   relógios e o denominador selecionado. Recompor cada série usando a última
   versão de cada barra com `fetched_at <= captura`, dentro da janela e removendo
   apenas as sessões recusadas registradas. Conferir hashes de conteúdo, séries,
   totais inseridos/inalterados, ausências, falhas e séries irreproduzíveis. As
   barras W3 continuam no banco; o verificador da primeira safra vazia não serve.
5. Publicar agregados e hashes por mercado; distinguir selecionados, solicitados,
   com barras, vazios/erros, sem classificação e com moeda incompatível. Resposta
   parcial do fornecedor é cobertura parcial, mesmo que a CLI conclua.
6. Readback final: nenhum outro contêiner alterado durante a operação, nenhum
   processo/fase pendente e invariantes R2D2 intactos. Auditoria independente do
   Fable. Na noite seguinte, conferir a mesma política no manifesto e a cobertura.

Sem execução em produção só por existir esta documentação ou uma PR. A ativação
e coleta devem ocorrer na revisão revisada e na janela coordenada com o executor.

Fontes: [Brapi tickers](https://brapi.dev/docs/tickers),
[EODHD catálogos](https://eodhd.com/financial-apis/exchanges-api-list-of-tickers-and-trading-hours),
[EODHD conta](https://eodhd.com/financial-apis/user-api),
[EODHD limites](https://eodhd.com/financial-apis/api-limits).
