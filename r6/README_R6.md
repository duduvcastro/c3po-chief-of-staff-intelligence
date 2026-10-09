# L12 R6 — candidato offline

Este pacote fecha as rotas de retomada e finalização do protocolo L12 e acrescenta a faixa `CAPACITY_MONDAY` e a espera limitada por READY. Não instala, assina, opera ou certifica o servidor. Cada operação real continua a exigir seus documentos, programas, verificadores, configuração e provas próprios.

`OuterLimiter.run(batch, operation)` é a entrada de execução do núcleo. A CLAIM durável nasce no pai antes do fork e antes de qualquer callback; um nonce privado do worker, ligado à CLAIM e ao compromisso da reserva, só permite um despacho durável `O_EXCL`. O worker pertence à sessão/grupo do supervisor e ao thread original. O limite absoluto inclui todos os callbacks e o transporte, com relógios UTC e monotônico nativos. A perda do pai ou do worker e o limite vencido conservam o consumo. O runner interno precisa usar `INHERITED_OUTER_GROUP`; ele não chama a entrada do núcleo novamente.

`FiniteBatch.run_reserved` público sempre recusa sem efeito ou mutação. `DurableLedger.observe_reservation` é somente leitura para a família J: confere cadeia, CLAIM, REQUEST/BOUND, marcador e compromisso inteiro, sem devolver nonce ou permitir um despacho. Nenhuma recusa deste candidato autoriza retry ou J2/J3. A casca/instalação real também deve cumprir a escolha D1 de nenhuma nova tentativa na segunda, inclusive quando um lock impede a primeira reserva durável.

R6 exige uma capacidade privada distinta para finalizar. Ela nasce no pai antes da CLAIM e permanece no PID/thread que a criou. `finish` aceita somente o esquema OUTER ou a recusa local correspondentes; `finish_family` aceita somente o envelope J e sua capacidade `J_FAMILY`. A família J não cria COMPLETE do núcleo. O nonce do pai nunca integra documentos, resultados, recibos ou o ledger — só seu hash e identidade de dono na CLAIM. As provas são criadas com permissão exata `0600`, independentemente do umask.

Uma dependência operacional agora exige a CLAIM OUTER atual, os hashes dos nonces do worker e do pai, a identidade do dono, o despacho durável e o terminal OUTER validado com recibo original exato. Um COMPLETE legado forjado permanece conservado como consumo/readback; não libera dependência. Um terminal anterior incerto continua `UNCERTAIN_CONSUMED` com `recovery_required=true`, mesmo com bytes duráveis; o resultado preserva o código e a contagem de efeitos anteriores. Um REQUEST/BOUND estrangeiro não recebe fechamento exato.

Zero bytes, prova parcial ou cadeia truncada continuam HOLD global, sem apagar, reinicializar ou adotar esses bytes. `_recover` pode registrar conservadoramente um órfão que tenha prova válida e completa como UNCERTAIN; isso não repara nem repete o efeito. O orçamento de finalização é separado do orçamento de execução (padrão 5 s, limite 30 s), para lock e compromisso após a limpeza do grupo. Uma falha de finalização mantém `recovery_required=true` e o diagnóstico interno.

`CAPACITY_MONDAY` contém somente `capacity_activate`, com autoridade própria. Seus recibos M3 e J reais da segunda são verificados pelo callback obrigatório `capacity_dependencies(bundle, request, task, now)`. A regra independente de domingo fixa os seletores de fonte, contexto, operação, REQUEST/BOUND e derivação; não inventa hashes de recibos futuros. Para os leitores/capturas posteriores, a mesma verificação exige também o original real de `capacity_activate` em sua faixa distinta, antes do efeito. Os requisitos antigos de recibos iniciais antes do REQUEST e de dependências do mesmo REQUEST/BOUND continuam vigentes.

`Services.ready_wait(bundle, request, task, now)` é obrigatório para `reader_cycle`, dentro da CLAIM e antes das releituras de dependência, runtime e veto. O módulo próprio só espera a ausência de READY por uma janela/regra finita; bytes presentes divergentes recusam. Depois da espera o núcleo relê a prova e obtém o veto fresco, sem guardar um ALLOW antigo durante a espera. O gate de imagem final volta a verificar READY antes do efeito SESSION. A interposição física na transição interna do launcher ainda exige o programa próprio: o gate anterior ao processo sozinho não intercepta essa transição.

Os módulos de capacidade, READY, verificador carregado e decoder K9 são cópias exatas da integração C6 R1. O modo REAL exige callbacks carregados de fonte pinada e a autoridade independente da regra; não há verificadores default. O decoder K9 exige aprovação externa e vínculo dos REQUEST/GO/BOUND e da fase atual, com relógios nativos. Os 27 casos próprios desses módulos permanecem em seu pacote de origem; não são repetidos ou transplantados para esta prova do núcleo.

## Prova incluída

`CURRENT_TEST_SELECTION.json` contém a única seleção requerida atual: 52 métodos de fixtures do núcleo/outer, executados sobre os hashes finais em `R6_CURRENT_REQUIRED_RESULT.json`. A seleção foi revisada após as mudanças em CLAIM, finalização, Services e dependência; os resultados anteriores 50/d709 e os candidatos fechados são históricos, não prova da fonte final. Nenhuma suíte antiga R3/Fable49/C6/Gate foi importada. Todos os documentos, relógios alterados em testes, callbacks, efeitos e recibos das fixtures são SINTÉTICOS.

Execute em uma cópia extraída gravável do arquivo, porque as fixtures criam diretórios temporários ali:

```text
python3 -I -B run_required_tests.py
```

O comando valida os hashes dos programas e fixtures e a contagem antes de executar. A prova local incluída usa Darwin/Python 3.9.6. Linux próprio da seleção final e a prova física permanecem pendentes. O readback do arquivo confere todos os membros, hashes e AST; ele não repete a suíte.

## Limites concretos mantidos

Nonce e privacidade de métodos Python são um protocolo dentro de um supervisor confiável e pinado, não um sandbox contra código hostil naquele interpretador ou um ator privilegiado do mesmo UID. ModuleType/callback/source carregados não são atestação de isolamento físico ou da semântica do verificador. Namespace, ABI, proveniência, autoridade e runtime reais precisam de seus próprios originais.

`killpg` cobre descendentes retidos no grupo. Docker/systemd/daemons ou descendentes que escapam da sessão precisam de confinamento e orçamento próprios; este candidato não certifica seu término. `fsync` e outras primitivas bloqueadas no kernel não viram hard realtime por um guard Python. O ledger no mesmo disco detecta divergências de provas retidas, mas não uma reversão integral daquele disco; não se impõe testemunha externa retirada pela D1.

Ainda faltam a casca/registry/installer real usando esta entrada e fontes finais, a regra/verificação REAL de CAPACITY_MONDAY e o programa/configuração AfterJ, o runner04/ABI K9 real aprovado, o controle SESSION real, o hook factual Sunday `before_effect` no transporte, os documentos/Assinos/GO originais próprios, a prova Linux própria e as margens/confinamento/runtime físicos. Nenhum mock ou teste cria GO, prova host ou garantia de entrada na segunda.
