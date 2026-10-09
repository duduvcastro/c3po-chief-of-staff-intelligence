# Codec puro J4 → writer original → dependência J

Este complemento decodifica o stdout integral de J4 quente IMAGE10 R1 e conserva o receipt original do `manifest_writer`. Não lança processo, importa a aplicação, lê o host, emite autoridade, assina, instala ou tenta novamente. O único modo dos ensaios incluídos é **FIXTURE**. Não foi construída uma ponte REAL nem um verificador operacional.

API:

```python
adapter = J4ReceiptAdapter(binding, approval=approval,
                          verify_approval=approved_verifier,
                          verify_original=original_verifier)
decoded = adapter.decode(stdout_raw, invocation, config_raw=actual_config_raw)
# decoded.writer_raw: os bytes completos originais com LF.
# decoded.linked_receipt: LinkedReceipt para CapacityMondayProof.j.
# decoded.core_receipt: Receipt admissão com stdout integral, não terminal de ledger.
```

`Binding` recebe o registry **realmente derivado**, REQUEST, BOUND e quatro fontes exatas (`hot_worker`, `hot_runtime`, `j_slot`, `manifest_writer`). `Approval` recebe a regra de aprovação externa, seu hash previamente conferido e os bytes da regra que autoriza a derivação do registry. A nova ABI `J4_APPROVED_DECODER_RULE_CANDIDATE_V1` está expressa em `RULE_KEYS`: modo/contexto, quatro fontes fixas, seletor explícito da origem J, REQUEST/BOUND, regra de derivação, janela e identidades/pins dos dois verificadores. Nenhuma regra REAL preenchida foi emitida aqui.

O seletor `linked_source_sha256` deve vir da aprovação e coincidir com o seletor J da regra `CapacityMondayGate`: permite a fonte de entrada `hot_worker` ou a fonte de execução `j_slot`, ambas pinadas. Nunca infere fonte a partir do hash do decoder, do writer ou do registry derivado. O hash do registry actual é conferido separadamente; não entra como hash futuro na regra assinada. Registry é derivado depois do REQUEST/BOUND pela regra previamente aprovada, e não se exige que seu hash esteja dentro desses mesmos documentos.

Os dois `Verifier` são obrigatórios, sem callback padrão, sem bool de aprovação. `verify_approval.invoke` recebe `(approval,binding,invocation,now)`. `verify_original.invoke` recebe `(stdout_raw,binding,approval,invocation,actual_config_raw,now,process,writer,general_raw)`. Em REAL, devem ser funções do módulo já carregado e aprovado pelo supervisor, com identidade e pin independentes da saída. A origem da aprovação, os originais do dono/autoridade, derivação permitida, namespace físico e origem/readback do stdout permanecem deveres concretos desses verificadores.

O verificador original precisa confrontar: comando/registro de transporte aprovado, entrada protegida e seus FDs/ancestrais, fontes e imports reais da imagem, identidade/process group e dispatch atual R6, REQUEST/BOUND/GO, família J consumida e terminal efetivamente comprometido, observação factual original da pasta, vistas gerais efetivamente usadas antes de cada efeito, revogações, calendário/cutoff reais, config final derivado e seus document pins, binding/manifesto/DB/readbacks. Um terminal J privado `COMPLETE`, JSON autoconsistente ou `Verifier` que retorna `None` por padrão não satisfaz essa verificação. `Verifier` confere protocolo do módulo/função/hash; não isola Python/root hostis, nem protege contra alteração deliberada de globals/code pelo próprio supervisor.

O parser exige stdout canônico exato com um LF e não extrai JSON de logs. Conserva `writer_receipt_base64` completo e SHA com seu LF. Exige SlotResult `COMPLETE/J_IMAGE_MANIFEST_COMPLETE`, modo exato, exit **int** 0 e flags `operational_GO=False/actual_installation_certified=False`. REFUSED, UNCERTAIN, família com terminal incerto, ACK, ALREADY/PUBLISHED_UNVERIFIED ou hashes sem bytes não produzem saída normalizada. Reconciliam-se config/manifesto, símbolo≤550, arquivo privado/nlink, IMAGE10, janela/cutoff, contexto e REQUEST/BOUND. A visão geral final pode ter sido renovada após o link; o codec não a apresenta como prova da visão usada antes do efeito. Essa cadeia factual é exigida do verificador de originais.

`published_at` UTC do writer é preservado como `completed_at` nos dois views. `CapacityMondayGate` conserva a ordem M3≤J≤activation e confirma o SHA do config actual; o codec não fabrica tempos, M3 ou activation. O `core_receipt` conserva o stdout integral para o verificador próprio do núcleo; não grava `ORIGINAL_COMPLETE`, não escreve o ledger e não converte o terminal privado J em terminal/dependência durável do R6. O núcleo/OuterLimiter precisam aceitar, conferir e comprometer seu próprio receipt antes de um consumidor usá-lo.

Relógios nativos UTC e monotônico guardam entrada, parsers, callbacks e saída. Injeção de clock é recusada. Callback bloqueado continua sob o limite físico do OuterLimiter R6; o codec puro não interrompe sozinho uma função C bloqueada. Cada documento/stdout tem teto de 1 MiB, como o protocolo fechado; o runner deve fixar seus caps antes da execução. Arquivos/originais não são relidos ou medidos por este componente.

Dependências copiadas byte-exatas: core R6 `809a816d…`, `capacity_monday_gate` `ebe04ca6…`, `verification_binding` `78f4309d…`. A fonte do codec e este namespace completo precisam estar pinados no runtime/registro instalados; os quatro pins da regra não representam, sozinhos, um executor imutável. As quatro fontes em `sources/` são apenas material de comparação/hash, nunca importadas/executadas pelos testes. Não é preciso localizar pastas irmãs para executar a seleção nova.

Prova local final: após o novo guarda Monday e o peer independente, a raiz autorizou UMA seleção dos **41 métodos próprios na fonte final `72f7dcaa…`**; `RESULT_FINAL_41.json` e `NEW_FINAL_TESTS.log` registram 41 PASS / 0 falhas / 0 erros / 0 pulados. Nenhuma suíte J4, R6, gate, app ou componente antigo foi executada. São fixtures puras, incluindo modo/terminal incerto, bool/int, framing/LF, fonte/REQUEST/BOUND/registry/config, callbacks tardios, UTC/monotônico/Monday e GENERAL renovado depois do link. Não certificam transporte ou capacidade reais.

Os passos intermediários permanecem separados: 26 métodos novos na fonte `fd88a9e0…`, quatro de fase/símbolos em `5ebb3701…`, quatro de framing em `d56b1d08…`, sete de modo/terminal/tempo em `72f7dcaa…`; uma fixture com LF afetado foi rechecada isoladamente. `TEST_EXECUTION_RECORD.json` distingue essas execuções e a autorização da seleção final. As fontes intermediárias preservadas como texto não são executadas. O driver `run_required.py` permite à Fable produzir nova prova Linux própria do pacote final com código de saída não zero se qualquer teste falhar ou se a contagem divergir de 41. Essa prova Linux própria continua pendente.

Pendentes: aprovação concreta desta ABI/seletores, regra e registros reais antes do efeito, bridge/verificadores REAL da casca, binding de comando/registro e stdout protegidos, runtime/installer/raízes, transporte próprio, provas físicas da imagem e Linux próprio desta nova seleção. Isso não declara GO, Assino, READY/SESSION, capacidade/DB ou entradas de papel.
