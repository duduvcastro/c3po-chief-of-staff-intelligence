# Prova portátil do subconjunto do registro 25

Este pacote contém o registro integral de 25 selos, o binder pinado e somente três famílias com seus três núcleos próprios: BOOTSTRAP_IDENTITY, K3-K9 e K3 secret.env. Os 268 arquivos dessas famílias e núcleos mantêm os bytes dos originais. Não é uma cópia das 23 famílias e não prova sealed-copy integral do registro 25.

Execute com um intérprete explícito e uma saída nova, fora deste pacote:

```sh
"$PY" -B "$PACKAGE/prove_subset_registry25.py" --python "$PY" --package "$PACKAGE" --evidence-out "$FRESH_EVIDENCE"
```

A saída deve ter pai existente e ser inédita. O helper cria diretórios 0700 e arquivos 0600. O mesmo buffer da fonte, depois do hash externo, é compilado; as leituras de identidade da fonte e do registro usam os buffers já pinados. Os demais arquivos continuam passando pelas APIs reais do binder.

Os 15 casos verificam a seleção das três famílias no registro integral e o BUILD_EQUAL dos três núcleos. Incluem núcleo trocado, selo antigo genuíno de K3-K9 (consulta de metadados), arquivo alterado, fonte e registro alterados e ausência/ambiguidade da linha BOOT em DTOs negativos derivados em memória. Esses DTOs não são registros aceitos. Os sete controles adicionais verificam os buffers de identidade retidos, os pinos, a cardinalidade e a recusa de saída dentro da entrada.

O binder original escolhe seu próprio filho para a montagem do núcleo; essa escolha é observada separadamente. O helper faz também três montagens com o intérprete passado em --python. O relatório não afirma que todos os filhos usam a mesma versão do processo externo.

A QA local fechou 15 casos e sete controles por Python 3.9.6 e 3.12.14, sem falhas, erros ou omissões. Aqui os três filhos reais do binder usaram o Python do sistema 3.9.6. JUnit e JSON completos estão em qa; TEST_INVENTORY.json fixa os nomes e as contagens. A identidade do host foi retirada apenas do atributo hostname dos JUnit de controles, com hashes originais e publicados em VALIDATION.json. Os streams de montagem e seus avisos/erros foram preservados.

Estas execuções locais não são prova Linux, L1, L2, receita TREE/BOOT/K3 preparada ou autorização de operação. O pacote não executa prepare, sign, check-bound, sealed-copy, transporte, Docker, GO ou comandos no host. A execução Linux deste mesmo pacote continua pendente.
