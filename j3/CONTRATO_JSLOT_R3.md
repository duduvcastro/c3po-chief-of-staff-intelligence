# Integração J3 com reserva R5 — candidato com REAL em HOLD

CANDIDATE_R5_RESERVATION_OBSERVATION_ONLY / EXPLICIT_REAL_PROCESS_HOLD / OPERATION_HOLD. Dez vetores novos locais passaram, zero falhas/erros, sem app real, banco, servidor, instalação, assinatura, push ou prova Linux. J1/J2 e respectivos resultados estão preservados; seus testes fechados não foram executados novamente.

## Reserva e consumo

O core desta pasta é exatamente finite_batch R5, SHA256 879d3abba179b18df6c0d497fc7bce45f4d86e52fa8992c7b9161735969bbb52. J3 substitui a antiga chamada check_reserved por observe_reservation(scope, request_hash, bound_hash, key). A observação confere cadeia/CLAIM/contexto/pins e commit da reserva externa sob lock; retorna somente None ou recusa. Não devolve nonce, não escreve dispatch e não permite executar efeito do core. check_reserved com worker_nonce e despacho exclusivo continua privado ao executor supervisionado do lote.

A observação se repete antes/depois de autorização, antes/depois da observação factual e antes de cada fase que pode preparar, escrever, criar contexto ou publicar. Fechamento ou mudança da reserva externa impede a etapa seguinte. Após início de escrita, recusa fica UNCERTAIN; não apaga artefatos, não renova vista e não tenta outra família.

A família interna (EPOCH04, DAY12, J_ADMISSION_FAMILY_V1) é consumida antes de hash/parse/seleção da regra ou consulta factual. A reserva externa L12 permanece em namespace distinto. J1/J2/J3 não são três oportunidades de admissão: recusa, resultado incerto e COMPLETE consomem a mesma família. Falha da reserva externa não autoriza reset. A observação de reserva não substitui a autoridade do ator nem dispensa o OuterLimiter.

## Seleção explícita dos protocolos

A regra candidata agora é R2D2_EPOCH04_JSLOT_RULE_V3 e acrescenta veto_protocol e process_candidate_pins. Não interprete automaticamente uma regra V2 assinada como V3.

- HISTORICAL_IMAGE10_FIXTURE_ONLY: conserva o caminho técnico J2 para fixtures DRAFT de dez segundos, com fontes históricas exatas do emissor/finalizador e os três consertos já revisados (consumo antes do preâmbulo; PUBLISHED próprio obrigatório; recibo completo original preservado). Só FIXTURE pode alcançar esse ramo nesta cópia.
- ISOLATED_MONDAY5_UNSIGNED_CANDIDATE: indica o novo candidato veto-process R1 e o codec X1 de vista própria até cinco segundos. J3 recusa essa seleção com J_PROCESS_PROTOCOL_NOT_OPERATIONAL. Não trata o fixture worker como emissor REAL, não transforma a vista histórica de dez segundos em outra autoridade e não presume cláusula assinada.

candidate_process é um namespace separado e contém bytes idênticos ao veto-process R1. Seu core R3d1 faz parte das fixtures originais dessa entrega, separado do R5 do J3; não existe substituição silenciosa de ABI. Seus hashes e resultados históricos são referência de origem, não novos ensaios desta cópia. O worker candidato aceita somente FIXTURE, entrega DRAFT/actual_process_attestation=false e não habilita REAL por alteração de marcador.

## REAL e próximos originais

run_slot(mode=REAL) recusa J_REAL_PROCESS_AUTHORITY_UNAVAILABLE antes de chamar verificador, fonte factual, contexto ou escritor, mesmo se receber reserva externa válida, callbacks permissivos ou relógio injetado. A família interna fica consumida. Nenhum objeto Python mutável, hash escolhido pelo caller, PID/nonce bruto ou transcript fixture serve de prova de origem de processo REAL.

A independência exigida é a fronteira de processos/pins/FDs e provas do executor. Registry, supervisor e raízes eleitas podem estar no MESMO servidor/disco/root escolhido pela D1. Esta cópia não impõe outro servidor, testemunha externa persistente antirollback ou assinatura criptográfica humana. O registro documental do dono pelo canal Fable continua aceito; é necessário conferir seus bytes e vínculos exatos, não fabricar um novo tipo de assinatura.

Para habilitar uma NOVA cópia REAL, a Fable precisa entregar os originais do registry/supervisor e instalação medida, identidade/Python/stdlib/dependências/FDs/command/argv efetivos, raiz e autoridade factual da pasta, cláusula de derivação assinada antes do efeito, origem do recibo no processo efetivo e rechecks/readbacks. O programa concreto pode usar o mesmo servidor já eleito: preparar inputs estáticos e processos antes de T; observar factual e verificar autoridade/revogação dentro do processo supervisionado; emitir e finalizar pelos bytes/pins fixos; entregar somente pelo canal privado vinculado à reserva/run; executar contexto original/prepare-first/publicação no mesmo orçamento; recheck antes de prepare e link. Faltam o vínculo e a prova físicos dessa rota, não uma arquitetura em outro host.

Monday até cinco segundos é proposta nova ainda unsigned. A autorização de imagem dez segundos vigente não muda automaticamente. Sunday UPSTREAM_P/E6_SUNDAY permanece outra família de observação com data factual domingo e alvo sessão 12; nunca se converte em VETO_VIEW de Monday por relabeling. O codec X1 não renova observed_at/valid_until e não clampa uma vista dez segundos para simular original cinco segundos.

Sem esses originais não há config REAL, vista ISSUED, worker ativado, admissão de banco ou GO concedidos por J3. As flags shadow_enabled=True/capacity_required=True continuam limitadas ao objeto de settings do processo fixture J, sem mutar ambiente/base/worker ativo. A etapa AFTER_J e os cinco campos efetivos do worker requerem ato e recibos próprios.

## Validação nova

Os dez testes desta revisão verificam: reserva externa observada repetidamente sem dispatch ou nonce; proof externo preservado; pins incorretos recusados e família consumida; retorno booleano não interpretado como permit; fechamento externo dentro da autoridade ou contexto bloqueando a próxima fase; REAL recusado antes de callbacks; seleção candidata cinco segundos sem efeito; seleção ausente recusada; pin do candidato incorreto recusado; namespaces R5 e R3d1/processo separados por hashes reais.

Os helpers são construção de fixtures, com os antigos métodos test_ removidos das cópias de suporte. Nenhuma soma dos 19 casos históricos do candidato processo, dos 12 de J2 ou dos testes do core é apresentada como resultado novo deste pacote.
