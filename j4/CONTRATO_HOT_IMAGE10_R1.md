# J4 / WARM IMAGE10 — contrato do candidato R1

Escopo: código offline próprio para a admissão e publicação do manifesto de 12/10, pela imagem e pela autoridade reais da época 04. A seleção corresponde ao regime quente IMAGE10 da ordem revM3. Não substitui IMAGE10 por PROCESS5 e não concede GO, assinatura, instalação, produção ou certificação física. O único `authority_bridge` fornecido neste pacote é FIXTURE e é recusado em REAL. O caminho REAL está implementado e depende dos originais e do programa de ponte próprios enumerados abaixo.

## Processo e consumo

O ator autorizado escolhe um programa Python isolado, sua fonte e `argv` fixos no registro de comandos do supervisor externo. O entrypoint recebe somente quatro argumentos DATA: `--registry-record-base64`, o base64 do registro canônico `{path,sha256,ancestors}`, `--mode`, `REAL`. A fonte de `hot_worker.py` é entregue pelo mecanismo de execução escolhido e pinado pelo supervisor, por exemplo stdin para Python isolado; nenhum callback, objeto Python, relógio, código arbitrário, variável de ambiente ou recibo COMPLETE vem do chamador.

Antes do carregamento já devem existir o CLAIM e o dispatch durável do supervisor externo R6. O escopo externo é exatamente `[epoch04,2026-10-12,2026-10-09,P,admission_manifest]`; não contém nome de slot e não muda com REQUEST ou BOUND. Trocar BOUND para essa mesma operação não cria J2. O carregamento e a validação dos bytes antecedem a família interna, mas não o consumo externo. A família interna J diária é consumida antes do bootstrap, do aquecimento, das verificações factuais e de qualquer efeito. Uma recusa, morte, timeout ou resultado incerto permanece consumido, sem tentativa automática posterior.

O segredo de terminal J_FAMILY nasce antes do CLAIM interno, fica privado no mesmo PID/thread e só termina o registro daquela família. Esse terminal não é ORIGINAL_COMPLETE do núcleo e não pode servir como dependência operacional. O supervisor externo conserva seus próprios nonce, recibos, dispatch, deadline, grupo, kill e reap; não recebe o segredo J.

## Registry e originais

O registry é JSON ASCII canônico sem LF, com schema `R2D2_HOT_IMAGE10_REGISTRY_CANDIDATE_V1`, mode REAL, protocol `WARM_IMAGE10_ACTUAL_OBSERVATION`, época 04, sessão 12, janela exata da tarefa J, ledger físico, escopo externo, autoridade e origem factual geral. Ele contém dez programas: hot_runtime, hot_worker, hot_watchdog, finite_batch, folder_veto, veto_emitter, config_finalizer, consumer_codec, j_slot e authority_bridge. Cada registro tem caminho absoluto, SHA256 e a cadeia real de identidades de ancestrais. Todos os descritores e bytes são presos antes de executar a ponte.

Contém dezesseis originais byte exatos: request, bound, owner, authority, runtime, rule, folder_spec, folder_authority, decision, folder_owner, config_base, template, veto_base, config_authority, act_b e machine_order. Os bytes da ordem de máquina usam sua ABI histórica canônica sem LF; não confundir o SHA dessa ordem / ACT_B com o pin runtime `1ad8…` nem com o hash do Markdown assinado. Os documentos JSON dos codecs que exigem LF mantêm essa ABI própria.

O registry é uma saída derivada posterior ao REQUEST/BOUND, pela regra autorizada, pois contém os hashes desses originais. Não exigir o hash do registry dentro dos mesmos REQUEST/BOUND: isso criaria um ciclo. A seleção estática da regra, dos programas, dos documentos e da forma de derivação deve ser aprovada antes da assinatura; o ator produz e confere os bytes e o hash reais do registry antes de executá-lo. A autoridade da ponte confere exatamente essa derivação e os originais completos, não uma afirmação booleana do chamador.

REAL exige euid 0, arquivos regulares próprios sem hardlink nem escrita de grupo/outros, raiz eleita 0700 e identidades estáveis de nomes e FDs. A identidade exclui apenas atime de leitura. A ponte deve conferir também o fecho de dependências de seus próprios imports e da imagem; os dez hashes do registry não atestam sozinhos o pacote instalado, o Python, o layout, a identidade DB ou a autoridade física.

## Ponte REAL própria

O programa de ponte, pinado e carregado dentro do filho, declara `BRIDGE_MODE='REAL'` e quatro funções próprias:

- `bootstrap(registry_raw, StaticInputs, modules)` retorna `RuntimeBindings`: SlotAuthority e FolderAuthority REAL realmente carregadas; verificador de configuração e LoadedVerifier iguais à fonte aprovada; ImageBinding carregada pelo `load_image` exato; settings base próprios. Não faz prepare, admissão, manifesto ou mudança no worker.
- `authorize(registry_raw, StaticInputs, phase, now)` verifica atos A/B/dono, REQUEST/BOUND/cadeia, regra derivada, fontes/namespace/runtime/release/package/calendário, janelas, revogações e os limites dessa fase. Retorna None somente quando aceitos; True não é atestação.
- `general_read(registry_raw, StaticInputs, now)` lê de fato a fonte autorizada e retorna o envelope geral canônico completo com instante nativo real, finalidade J, sessão 12, origem, autoridade, todos os pins requeridos e revogações. Não copia nem renova um instante antigo.
- `general_verify(registry_raw, StaticInputs, envelope_raw, now)` confere independentemente a origem factual, sua observação, os bytes e a autoridade atual, sem aceitar uma marca REAL ou um callback booleano como prova. Retorna None ou recusa.

Essas funções são código da fonte pinada do filho, não funções transportadas pelo pai. A ponte faz suas verificações documentais pelo canal Fable aceito; não se impõe nova assinatura criptográfica humana nem testemunha externa. O próprio servidor/root eleito por D1 é suportado. O processo executa código aprovado e confiável; não é sandbox contra Python hostil ou root malicioso dentro desse processo. A prova da ponte e dos seus imports permanece necessária.

## Relógios, aquecimento e efeitos

O aquecimento ocorre dentro da tentativa autorizada, antes de T: carrega a imagem e as dependências exatas de `context(prepare_first=True)`, sem preparar capacidade antes do veto real. A observação factual geral ocorre novamente depois do aquecimento. Seu gate AGE<=5 s é separado da view da imagem e pode ser reobservado de fato antes de um efeito; isso jamais muda T da imagem.

Antes de T aquece um processo watchdog separado, sem ponte factual nem callbacks da imagem. A observação da pasta vazia fixa um único T nativo e um prazo até T+10 s, limitado também pela janela factual e externa. A marca monotônica é projetada naquele T original antes dos callbacks seguintes: todo tempo posterior conta. O watchdog recebe esse único T por pipe privado e mata o grupo quando termina o prazo, mesmo com C ou IO nativo bloqueado no interpretador. O SIGALRM Python é apenas guarda secundária.

O watchdog cobre os descendentes que permanecem no grupo eleito. Não é confinamento de root que escape do grupo; o runtime/ator aprovados não podem fazê-lo. A prova de PID/PG/SID, namespace/FDs, pipes, fonte Python e kill/reap no Linux real cabe à Fable. O supervisor externo mantém sua guarda independente de tempo e coleta.

Depois dos callbacks lentos e imediatamente antes de cada escrita de staging, prepare e gate de link, o guard composto relê a pasta pelos FDs presos e só então confere o relógio nativo geral e IMAGE10, sem callback entre esses dois passos e o próximo efeito. `stage_file` usa O_EXCL, modo 0600 e guarda separada antes de open, fchmod, cada write e cada fsync; não apaga nem substitui arquivos. A releitura finita não oferece atomicidade contra uma inserção concorrente após o último syscall de observação; a autoridade e a prova física devem manter essa fronteira explícita.

A emissão usa somente a observação atual e o programa carregado. O finalizador compara as bases estáticas pinadas, a derivação autorizada e `final.document_pins==template.document_pins`. Só `veto_views[12]` recebe o arquivo/hash da view efetivamente emitida. Não há hash futuro, renovação de freshness, falso OWNER ou edição dos documentos assinados. O settings resultante aplica shadow=True/capacity_required=True somente ao novo processo J, sem mudar ambiente nem worker ativo.

A execução chama o `execute` original da imagem com prepare_first, GO individual e max_wait=0. Só PUBLISHED_VERIFIED completo é aceito; ALREADY é recusado. O recibo original completo do writer é preservado em bytes/base64 com binding, config, GO, view, window, published_at e manifest hash; hashes não substituem os originais reais. A cópia de sessions.capacity_binding só existe depois da captura correspondente, não é exigida como se já existisse antes da admissão.

## Evidência e pendências de ativação

A saída própria é `R2D2_HOT_IMAGE10_PROCESS_RECEIPT_CANDIDATE_V1`: registry/REQUEST/BOUND reais, PID/grupo/pai, warm_at, T/prazo, último envelope geral original e SlotResult com recibo original da imagem. Um verificador externo próprio precisa reconciliar essa origem, o processo eleito, os arquivos resultantes e o ledger antes de promover qualquer dependência do lote. `actual_installation_certified` e `operational_GO` permanecem False neste produtor; não se fabricam recibos operacionais com base no parecer.

Ainda faltam: fonte REAL da ponte e seu fecho/parecer; REQUEST/BOUND/owner e atos próprios com a regra derivada; registry real e instalação/readback dos arquivos/raízes/FDs; runtime R0b/release/package/config/DB físicos após a imagem final; integração do registro de comandos externo e verificador próprio da saída; prova Linux própria deste J4 e prova física de aquecimento, factual geral, T, config, prepare+link e readbacks dentro dos dez segundos. O pacote não promete que o orçamento será suficiente e não constitui entrada de segunda ou GO. Se esses bytes/provas faltarem, REAL recusa ou permanece HOLD.

## Verificação offline própria

A seleção NOVA de J4 tem 33 métodos, 0 falhas e 0 erros na fonte final. Inclui origem/FD/função alterada, callbacks booleanos, fato ausente/antigo/futuro/revogado, day/opcode incorretos, renovação de T recusada, capacidade privada de terminal, delta único da configuração, sessão FIXTURE recusada em REAL, pasta com veto inserido depois da autorização, recibo original completo e processo watchdog independente matando somente seu grupo fixture bloqueado em C. Não executa app/DB/host de produção nem repete as suites fechadas J2/J3/R6/Veto-process R1. Logs intermediários de defeitos e vetores corrigidos estão preservados; só FINAL_NEW_J4_TEST_LOG é o resultado da seleção atual.
