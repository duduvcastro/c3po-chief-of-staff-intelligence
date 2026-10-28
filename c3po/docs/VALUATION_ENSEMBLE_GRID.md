# Ensemble: cálculo de uma seção da grade

Este caminho implementa o cálculo direto autorizado para o protocolo assinado
`PREREG_VALUATION_ENSEMBLE_PIT_US_V1`, sem ler rótulos. É distinto do caminho de
originais autenticados: os pacotes SEC/CVM não são requisito deste modo. Isso não
converte um hash, símbolo, setor ou convenção de base em prova histórica nova.

## API e fronteira de execução

`valuation_ensemble_grid.compute_grid_section(database, *, market, as_of, prices,
v3_snapshot, served_snapshot, implementation, seed=20261026, vintages=None,
volume_basis, before_read=None)` calcula **uma** seção `(bolsa,T)`.

- `database` é um leitor canônico explicitamente fornecido; não se cria conexão,
  cliente, configuração ou transporte por importação ou valor padrão.
- `prices` é `valuation_pit_rerun.PinnedPrices`, resolvido na mesma publicação do
  irmão V3. A safra, bolsa, `T`, sessão e conteúdo declarado têm de coincidir.
- Os snapshots completos dos irmãos V3 e TP servido são os da mesma bolsa e `T`,
  com `statements=vintages`. Manifestos, catálogo, curva, referências das
  demonstrações e triagem são comparados antes do cálculo.
- `implementation` contém os hashes explícitos do instrumento. O executor deve
  validar o pino, assinatura e ordem **antes** de chamar esta função. A seção
  declara `instrument_binding_enforced_here=false`; ela não substitui essa guarda.
- `volume_basis` é obrigatório e vem de `rev3_manifest.volume_basis.decision`.
  Não é escolhido a partir dos resultados do ensemble.
- `before_read`, quando fornecido pelo executor, é chamado antes **e depois** de
  cada operação de leitura de snapshot, cobertura/fatos as-filed ou preços. Uma
  expiração propaga a exceção e interrompe o consumo; não vira falta de um modelo.

Não há parâmetro de rótulos, treinamento, grade real automática, publicação,
persistência, promoção ou CLI neste módulo. Um executor/relatório operacional é
outra camada. Fixtures em memória não demonstram capacidade de execução no host.

## Fontes e igualdade com os irmãos

O catálogo é lido pelo ID já resolvido no irmão V3. Seu conteúdo admitido é
recalculado com `admitted_catalogue` e comparado ao hash do manifesto. O catálogo
atual pinado e seus campos `sector/industry/valuation_profile/security_type` são a
convenção declarada do rev3; não são classificados como setor histórico oficial.

`AsFiledReader` aplica `accepted_at<=T`; os fatos canônicos e seus hashes são
checados novamente. `as_filed_payload` recompõe a referência que o irmão V3 leu:
contagem, substituições e hash das demonstrações devem coincidir. Alteração de
fatos elegíveis recusa a seção (`statements_table_not_stable`); uma aceitação
posterior a `T` não entra no cálculo. Campos adicionais só podem vir dos mesmos
fatos já presentes, sem nova coleta. Seu digest canônico entra na identidade do
contexto. O executor continua responsável por manter a tabela estável no trecho.

Cada nível de preço é `close(D)`; uma falta de fechamento exato recusa o nome.
Os retornos ajustados do leitor só alimentam beta/proxy e as convenções de
triagem do rev3. Uma publicação retrospectiva não é renomeada como captura em
`T`. O filtro de evento de capital entre o período das ações e `T` é preservado.
A contagem do cover segue a seleção de documento do rev3, inclusive a convenção
de soma de classes: a seção declara que não autentica classe, escopo ou ações
corporativas. Não existe fallback para `outstandingShares` corrente neste modo.

O Tesouro vem do ID que os dois irmãos usaram. O hash da história e o pacote
3Y/10Y reduzido em `T` são verificados; não há taxa macro atual ou fallback fixo.
O consenso vem das linhas **brutas** do snapshot FMP referenciado pelo V3, via
`grid_consensus_at`: média das últimas metas elegíveis por casa, mesma janela e
moeda do leitor congelado, mínimo três casas. A mediana é apenas descritiva.
Mediana mais contagem nunca são usadas para recuperar a média. Sem consenso,
as quatro variantes com consenso usam só os modelos e publicam a razão.

O TP do irmão servido só aparece em `served_tp`, como comparador. Nenhum TP ou
modelo previamente calculado no snapshot V3 entra nos 16 kernels.

## Fatos e premissas explícitas

Os kernels existentes são chamados diretamente. Cada nome tem sempre 16 resultados:
valor positivo finito ou motivo de não avaliação. Nomes não admitidos nos inputs
de triagem V3 ou que não são ações continuam no ledger, com recusas explícitas.

- Fluxos usam o ladder oficial, os quartos discretos e a continuidade do rev3;
  na falta de quatro quartos, existe o fallback declarado para o último ano
  fiscal completo. Os períodos e fatos consumidos constam das derivações.
- Dívida exige `DebtCurrent + LongTermDebtNoncurrent`, ambos presentes e na mesma
  data. `LongTermDebtCurrent`, `ShortTermBorrowings` e `CommercialPaper` parciais
  não substituem o agregado; ausência não é zero.
- Intangíveis excluindo goodwill exigem o agregado explícito, ou o total
  incluindo goodwill menos goodwill na mesma data. Finite-lived isolado não é
  convertido em todos os intangíveis.
- `book_equity_beginning` só usa a data exatamente anterior ao início do suporte
  NI de quatro quartos, quando o caminho de termos assinados é único e exato.
  Nunca se escolhe um saldo próximo, nem 365 dias antes. A comparabilidade aqui é
  a convenção canônica issuer/USD do modo grade; não autenticação de originais.
- Variação de capital de giro exige os dois saldos nas fronteiras exatas desse
  período: `(ativo circulante-caixa)-(passivo circulante-dívida corrente)`.
- Empréstimo líquido exige os três fluxos completos: emissão longa menos
  amortização longa mais emissão/amortização curta líquida, com mesmo término.
- Normalização e manutenção são **proxies de desenho**, não fatos reportados
  com esses nomes: medianas de cinco anos fiscais comuns de lucro operacional
  e capex reportado. As derivações preservam esse rótulo.
- Imposto é despesa de imposto/resultado antes do imposto positivo, em períodos
  iguais, entre 0 e 1. Sem par válido não há preenchimento ou clamp.
- `ke=clamp(r5y(T)+beta(T)*0.055,0.06,0.16)`, a política CAPM US congelada da V3.
  Beta é refeito no proxy do leitor com retornos até `T`; beta ausente não vira 1.
- WACC usa os pesos `E=close(D)*ações`, `D=dívida reportada`, com custo da dívida
  proxy `juros TTM/D` após imposto. `D=0` explicitamente reportado dá `WACC=ke`.
- Crescimento terminal 0.03 é convenção de desenho US da V3. O caminho explícito
  de cinco anos parte da variação entre dois anos fiscais de receita observados
  e consecutivos e converge linearmente à convenção. Sem história não se inventa
  caminho. Não há crescimento de EPS de analistas ou reverse-DCF implícito.
- Múltiplos/regressão usam a seção disponível do mesmo setor atual pinado,
  moeda, `T` e classificação financeira, deixando o próprio issuer de fora.
  Perfil ausente/desconhecido não é declarado não financeiro.

As oito variantes vêm de `aggregate_grid_variants`, com mínimo três **valores**
incluindo o consenso quando presente; primária `minmax_trimmed_mean_with_consensus`.

## Saída, auditoria e identidade

A seção devolve `source=ensemble_pit`, `records` ordenados por símbolo,
`records_sha256`, `run_key`, `context_identity`, `input_pins`, `implementation`,
`seed`, `catalogue_stocks` e ledger. O denominador de cada modelo é o catálogo
completo; o denominador de cobertura de ações fica separado. Um ETF permanece
como linha recusada e não infla o número de ações avaliáveis.

`run_key` é o hash do **contexto de entradas**, conhecido antes dos modelos: `T`,
pinos dos irmãos, implementação, política, seed, base de volume e digest dos
fatos canônicos. Não depende dos valores dos modelos ou de `records_sha256`.
Cada linha já nasce com esse contexto. `payload_sha256` identifica a saída.

`paired_source_identity(v3_snapshot, served_snapshot)` reconstrói os pinos dos
snapshots reais: IDs/runkeys, classificação, fatos/referências, metas brutas,
curva, triagem e identidades dos registros servidos. O resultado é exatamente
`section.input_pins`. `validate_record_pair(records, v3_snapshot, served_snapshot,
volume_basis=...)` verifica, antes de labels, catálogo completo/hash, símbolos,
preço, triagem, TP servido, sessão e vínculo ao par. O relatório deve obter os
snapshots via leitor confiável, não aceitar apenas um JSON que afirma seu hash.

As fixtures usam `Database` em memória, `StatementVintageStore`, `AsFiledReader`
e `PinnedPrices` reais, com transporte sintético e bloqueio de rede. Não atestam
dados reais, cobertura real, admissibilidade histórica de originais ou resultado
científico. A revisão independente e o pino do instrumento continuam separados.
