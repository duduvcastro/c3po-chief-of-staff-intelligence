# Relatório do ensemble em modo grade

`app.valuation_ensemble_report` implementa a estatística do pré-registro rev 2,
vinculado ao documento de SHA256
`b786ef8ff21d2b0dbcc2e39bcaec3a984e7a204b8a796d34a84c49ace69db9a9` (a estatística é a da rev 1; a rev 2 muda a base das demonstrações).
Não abre conexões, não captura originais, não altera o preço servido e não promove
uma fonte. O executor fornece leitores somente de leitura para os snapshots e os
rótulos da publicação de preços já pinada.

## Ordem das verificações

`build_report` exige o pino do instrumento e o `InstrumentBinding` obtido do recibo
público revisado e assinado. O JSON do próprio pino não cria essa autoridade. Exige
também `expected_manifest_sha256`, obtido do recibo publicado da grade concluída;
recalcular um hash a partir do documento de entrada não o autentica.

Antes de pedir qualquer rótulo, a função verifica:

1. Pino, assinatura/GO referidos, commit, constantes e bytes de todos os arquivos;
2. Manifesto completo, hash, identidade do manifesto rev 3 e os mesmos instantes;
3. Irmãos V3/TP servido nomeados no rev 3, hashes dos registros e denominadores;
4. Dezesseis identidades de modelos e oito agregações recalculadas dos seus valores;
5. Calendário, índices de maturidade e última posição, vinculados no campo
   `report_calendar` do manifesto publicado;
6. Releitura dos snapshots irmãos por `paired_sources_reader(entry)`, comparando
   identidade dos insumos, publicação de preços, catálogo, as-filed, Tesouro,
   referências do consenso, preço, triagem e TP servido dos registros residentes.

Só depois o `label_reader(record, h)` é chamado, no máximo uma vez por nome,
sessão e horizonte, compartilhando o rótulo entre as oito variantes. Um manifesto
ou pino inválido produz `VOID`, zero chamadas de rótulos e nenhuma estatística.
Uma observação imatura nem chega ao leitor. A elegibilidade do denominador de
atrito vem da maturidade pinada, e não de uma flag fornecida com um rótulo ausente.
Como no rev 3, um nome duplicado entre as duas bolsas é contado e usa somente
NASDAQ, antes de NYSE; a mesma escolha serve para ensemble e comparador. Uma
duplicata dentro da mesma bolsa permanece uma falha de integridade.

O executor deriva `report_calendar` do calendário XNYS e do corte da publicação de
preços pinada. Não se permite mudar o calendário ou a maturidade depois de publicar
o hash. As fixtures reduzidas dos testes são sintéticas, não grades científicas.

## Estatísticas

A primária é `minmax_trimmed_mean_with_consensus`. As outras sete variantes são
descritivas. Todas são publicadas para 21, 63, 126 e 252 sessões.

- Ordenação: Spearman entre `tp/price - 1` e retorno executável de `D+1` a
  `D+1+h`, no mínimo dez nomes; spread de decis exige trinta;
- Precisão: erro absoluto em log contra o retorno ajustado de `D` a `D+h`, com
  previsão `(h/252) * log(tp/price)`;
- Diferença de precisão: **mediana dos erros do TP servido menos mediana dos
  erros do ensemble**, na mesma interseção de nomes. Não é a mediana das diferenças
  individuais e não é MSE;
- Diferença de IC: dois ICs calculados na mesma interseção de nomes;
- Blocos: `h` sessões do calendário desde o início da grade, somente blocos
  completos. Média das médias, `se = sqrt(1.5) * sd / sqrt(B)` e Student com
  `B-1` graus de liberdade. Variância zero não inventa significância;
- Metades: primeiras e últimas `floor(B/2)` médias, omitindo a central se ímpar.

A decisão segue `VOID`, `UNMEASURED`, `NEGATIVE`, `PASS`, `FAIL`. `UNMEASURED`
inclui menos de oito blocos de 126 sessões, atrito acima de 0,15 ou pisos de
cobertura não atendidos. `PASS` exige **todas** as condições assinadas de precisão
e ordenação em 126 e 252 sessões. Não há condição de persistência de 63 sessões
para a decisão em 126 sessões.

`design_table()` usa semente 20261026 e a covariância exata das médias de bloco
do processo gaussiano triangular de 126 sessões. Publica potência da condição 2
isolada e da condição 7 para desvios de precisão observados e efeitos explícitos.
Não apresenta essas probabilidades como potência do `PASS` inteiro, nem muda
limiares com base no desvio observado.

## Alcance

O relatório é determinístico para os mesmos insumos, código e pinos. A primeira
leitura não `VOID` do manifesto completo é a leitura única prevista no protocolo;
o operador deve conservar o recibo e o registro dessa leitura. Um `PASS` registra
que a condição científica de promoção foi atendida, mas este módulo não realiza
a promoção nem modifica serviços.

A comparação dos snapshots protege o caminho de insumos pinados. Não autentica
independentemente os originais SEC/CVM, identidade histórica de classe, eventos
corporativos ou hipóteses herdadas do catálogo. Essa captura e suas provas seguem
na frente paralela, com suas limitações preservadas.
