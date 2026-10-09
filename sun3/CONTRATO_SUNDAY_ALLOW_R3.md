# Gate de veto L12 do domingo R3 — dependências finais explicitamente pinadas

CANDIDATE_SUNDAY_FOLDER_ALLOW_CODEC_ONLY / OPERATION_HOLD. Quatro casos NOVOS de dependências/ABI/mutação passaram, zero falhas/erros. Os14 históricos R1 e os4 task-window R2 não foram executados nesta rodada. Nenhuma autoridade/runtime/pasta do servidor, instalação, assinatura do lote ou efeito operacional foi fornecido. R1/R2 e a ocorrência de redescoberta documentada permanecem preservados.

## Escopo e interface

`FolderSource(spec_raw, authority_raw, decision_raw, owner_raw, spec_sha256=..., binding=..., clock=...)` recebe originais exatos e spec L12_SUNDAY_FOLDER_VETO_SOURCE_V3. Contexto: epoch04, first_session/target_session12/10, factual_day11/10 Nova York, purpose UPSTREAM_P ou E6_SUNDAY. A janela factual inteira precisa caber no domingo de Nova York. Não fabricar DAY12, observed_at de segunda ou view do consumidor da imagem.

UPSTREAM_P aceita somente operações prove/collect/commit_result/publish_launch do lane UPSTREAM_P, trilha P, anterior09/10. E6_SUNDAY aceita somente e6 do lane DOWNSTREAM_AFTER_E6: o plano tem os dois papéis iniciais de resultados completos; os originais reais dos recibos e sua cronologia continuam responsabilidade obrigatória do L12 antes do REQUEST/Assino de E6. Este codec não cria recibo, E6, GO ou assinatura.

O spec fixa a autoridade do veto, do L12, runtime, fonte, verificador e pins necessários, pasta física e todos ancestrais. D1 09de76e5… e seu registro original são conferidos por bytes/hash/escopo, mas não substituem a regra/pacote final assinados do lote. REAL exige UID0/0700 na pasta, clock is veto_emitter.real_clock, e AuthorityBinding cuja função é LoadedVerifier de programa REAL realmente medido por caminho/FD/hash/ancestrais. O programa externo deve aceitar os originais e verificar escopo, regra assinada, runtime/documentos/revogações atuais; não há aprovação padrão ou lambda booleana.

`services.veto_read = source.veto_read` e `services.veto_verify = source.veto_verify`. veto_read(q, task, supplied_now) ignora o horário fornecido para a observação: usa o relógio factual próprio. Confere o plano canônico pelo parser L12 exato e a tarefa pertencente única; lê diretamente a pasta por descritores O_NOFOLLOW, confere antes/depois identidades e alterações, e retorna `finite_batch.VetoView(raw, authority_sha256, ALLOW, observed_at, valid_until)`. Qualquer entrada, inclusive subdiretório/symlink, é veto. Ausência de pasta, troca de inode ou erro não vira ALLOW.

Os bytes originais são L12_SUNDAY_FOLDER_OBSERVATION_V1 com modo FIXTURE ou REAL, contexto factual/target/purpose, hash do spec, raiz eleita, operação, instante factual fracionário e validade ≤5s. Não usam o ABI VETO_VIEW e não dizem ISSUED. FIXTURE continua fixture: o leitor/authority/identity/executor REAL do pacote não podem aceitar seus bytes como fatos reais. Nenhum wrapper operacional/default executor é fornecido.

veto_verify exige o mesmo objeto e bytes originais produzidos pela fonte, contexto plano/tarefa inalterado, autoridade e pasta conferidas agora e relógio depois dos callbacks. Nunca renova observed_at ou valid_until. Uma operação específica não pode pedir nova observação para retry; a seguinte operação distinta e autorizada produz seu próprio original factual. A unicidade física entre processos é o ledger/reserva L12, não a memória deste codec. A morte/recusa do processo não autoriza nova invocação.

## Hook antes do efeito e integração

O núcleo L12 chama outros callbacks depois de veto_verify. Por isso o executor próprio pinado da casca deve chamar `source.before_effect(q, task)` como seu último recheck factual imediatamente antes de cada efeito controlável. before_effect reconfere a pasta e autoridade sobre o MESMO original e TTL, sem renovar; não executa app/host. O REQUEST/autoridade precisam piná-lo como parte da fonte exata da casca/executor. O papel de `services.execute` não é preenchido por este núcleo e não aceita por inferência um callback sem esse controle. Se callbacks posteriores ao recheck demorarem ou criarem veto, recusa; orçamento e hard deadline abrangem todos os callbacks sob OuterLimiter aprovado.

Efeito P longo continua sob seu budget/runner e seus controles próprios; a validade do ALLOW de partida não promete que a pasta permanecerá vazia durante toda a operação. Novas transições/efeitos controláveis exigem rechecks próprios e originais novos autorizados por operação, sem retry/catchup. O envelope deste codec não modifica veto/config do worker e não presume cancelamento automático do processo ativo.

## Pendências

Spec/pacote/regra finais assinados antes do efeito, caminho/identidades físicas reais, autoridade e programa externo verificador REAL/dependências/readbacks, revogações e snapshot runtime atuais, originais completos de plano/BOUND/owner/P/E6, montagem namespace e executor/limitação aprovados ainda precisam ser fornecidos e reconciliados. A source authority precisa verificar precisamente a transformação/contexto destes bytes, não só sua hash. A prova Linux própria destes novos bytes e ensaio físico da casca permanecem ausentes. O veto de segunda J/IMAGE_ADMISSION é módulo/contrato separado com 10s e config derivada posterior; esta observação Sunday não é transferível para ele.

## Correção R2: janela de cada tarefa no relógio factual

O código L12 já guarda a janela da tarefa; este codec passa também a conferi-la com seu relógio factual, independentemente do relógio fornecido pela casca/L12. _scope/before_effect exigem task.not_before ≤ factual_now < task.not_after. Depois de verificar autoridade e ler a pasta, _observe repete essa guarda no relógio pós-callback e limita valid_until à menor entre TTL≤5s, autoridade, source-window e task.not_after. A validade ampla do spec fonte não amplia a tarefa. Um callback que atravessa o fim da janela recusa sem emitir original.


## Correção R3: dependências atuais e ABI L12

O spec V3 contém dependencies exatamente com finite_batch e veto_emitter. Seus hashes precisam estar no conjunto completo de required_pins de revogações. FolderSource confere os bytes reais de cada módulo importado antes da primeira autoridade e antes/depois de cada callback de autoridade: uma mudança durante o callback recusa antes de produzir observação. Não basta um metadado declarando a versão. Runtime/dependências carregadas e identidade do processo continuam parte da verificação externa completa.

finite_batch é vendorizado byte exato R3d1, SHA311c2eaa47a223697324f7386b027b2e83c00926c00e7269fd4cfb9fe1c4fa25. veto_emitter é R2 exato, SHAf8370c789eebf0d58ec629c474e16c8a3f176facddda39e413a80e5af9c7f5bc. O teste novo confirma VetoView da classe real desta dependência e before_effect, a recusa de pin R3c conhecido NO_GO, escopo de revogação completo e mutação dos bytes do módulo em callback. Todas as observações desse ensaio permanecem FIXTURE. Nenhum ensaio do núcleo L12 ou do emissor foi repetido/transplantado.

A migração não promove a prova de task-window R2 para runtime físico: suas guardas permanecem na fonte e foram conferidas por AST/diff, enquanto somente estes quatro vetores novos de delta foram executados aqui. Spec/atos/template/runtime e prova Linux desses bytes finais continuam pendentes. O executor próprio precisa do before_effect final e OuterLimiter com reserva física; chamar FiniteBatch.run diretamente continua fora do contrato.
