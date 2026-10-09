# Emissor de veto da imagem — núcleo candidato r1

Turno humano de 09/10/2026. Resultado: núcleo puro e interface concreta para transformar uma observação original autenticada em VETO_VIEW da imagem. Não fornece fonte externa, verificador REAL, assinatura, instalação, timer, pin provider, operação host/DB ou GO. O caminho de integração com o CapacityConfig está **PENDING**, e é uma dependência material.

## Interface entregue

`emit_view(spec_raw, observation_raw, authority_raw, observation_sha256, *, spec_sha256, verifier, clock) -> Emission`

Todos os argumentos são obrigatórios. `observation_raw` e `authority_raw` são bytes originais completos; o módulo não os consulta ou inventa. `observation_sha256` vem do pin/original recebido pelo canal autorizado. O pin independente `spec_sha256` precisa preceder a execução e coincidir com o arquivo de especificação. O callback não tem implementação permissiva nem fallback. Exceções retornam somente códigos constantes, sem conteúdo privado.

Spec em JSON canônico com LF, exatamente estes campos:

| Campo | Contrato |
|---|---|
| schema | `R2D2_IMAGE_VETO_EMITTER_SPEC_V1` |
| mode | REAL ou FIXTURE; não há promoção automática |
| context | epoch, first_session, day e order_sha exatos da autoridade da imagem |
| source | identity, implementation_sha256 e observation_format da fonte factual autorizada |
| verifier | identity e implementation_sha256 do callback revisado e pinado |
| authority_sha256 | SHA do original de autoridade completo |
| view_opens_at | instante UTC autorizado para esta observação; não é observação futura antecipada |
| required_pins | lista ordenada e sem duplicatas de todos os pins exigidos pelo escopo da autoridade: documentos, GO, programas/fontes/contexto/runtime aplicáveis. Inclui ao menos ordem, autoridade, fonte e verificador |
| maximum_age_seconds | inteiro positivo até10; nunca renova uma observação |

`VerifierBinding` fixa identidade, hash de implementação, modo e callable `verify_original(observation_raw, authority_raw, spec_raw, now_UTC)`.

O callback retorna exclusivamente `VerifiedObservation`. Ele deve autenticar a origem original; verificar a cadeia e autorização da fonte, contexto/instante/dia/época; comprovar que a autoridade permite emitir no papel documental **FABLE**; conferir seu intervalo real; derivar da autoridade a lista completa de pins a consultar, sem adotar cegamente um subconjunto escolhido pelo chamador; verificar revogação e veto com a observação factual original. Ele devolve esses vínculos, a validade da autoridade, os timestamps originais, o status e as revogações. Declarar `VERIFIED` em um JSON não substitui esse callback nem prova autenticidade.

O núcleo exige autenticidade/autoridade/revogação verificadas literalmente como True; identidade/hash/formato e contexto exatos; autoridade cobrindo **todo** o intervalo da visão; lista de pins derivada da autoridade idêntica à especificação; papel FABLE explicitamente autorizado; status VERIFIED; `observed_at == view_opens_at`; `observed <= now < valid_until`; duração positiva até10s; dia atual em New York igual ao day; ausência de veto do dono e de revogação dos pins críticos. Reconfere relógio e validade depois do callback; relógio voltando ou callback consumindo a janela recusa. UNKNOWN, ausência de original/callback, fonte diferente, bytes alterados, dados futuros/vencidos e revogação nunca geram visão.

## Saída e alcance

A saída é somente bytes, seu hash e os pins de entrada. O Markdown contém exatamente um bloco canônico entre os marcadores da imagem; schema `R2D2_DOCUMENTARY_EVIDENCE_V1`, kind VETO_VIEW e body com exatamente `status`, `role`, `epoch`, `day`, `order_sha`, `observed_at`, `valid_until`, `owner_veto`, `revoked_shas`, `evidence_sha`. `evidence_sha` é o hash do **original factual** recebido. `observed_at` e `valid_until` são copiados byte a byte de seus valores originais; o relógio de execução não os substitui.

FIXTURE sempre produz **DRAFT**, que o parser de revisão pode ler e o PinnedVetoReader real rejeita. Não há verificador REAL neste pacote. REAL só pode produzir ISSUED quando todos os inputs e o callback REAL próprios forem entregues, autenticados, pinados e aceitos externamente; executar teste sintético não cumpre essa condição. `operational_GO` é sempre False.

Reinvocar durante a mesma validade produz os mesmos bytes e hash; reinvocar depois de vencer recusa. Isso não concede nova tentativa a um slot consumido. O lote guarda claims/ledger/rechecks e a identidade física do programa; o núcleo não possui installer ou retry.

## Achado de integração: pin estático não é fonte futura

Foram copiados quatro originais exatos e seus pins no `CONSUMER_PINS.json`:

| Fonte da imagem/deployment | Guarda relevante |
|---|---|
| document_format, `e7c1758e…` | PinnedVetoReader verifica arquivo/hash, ISSUED/VETO_VIEW, role FABLE, epoch/day/order_sha, evidence_sha e intervalo positivo até10s. RenewableVetoReader aceita pin provider obrigatório e também exige cada original imutável próprio |
| capacity_bootstrap, `8f7a21dc…` | ConfigAuthority sempre usa `config.veto`; dispatch/derivation lê `body.veto_views[NYday]` com pin estático. RenewableVetoReader está somente no canal restore de CONTINUOUS. DISPATCH_AND_DERIVATION_ONLY exige restore_revocation=None |
| document_authority, `c75b855d…` | `current` chama o revocation_reader, exige VERIFIED/freshness até10s e ausência de veto/revogação dos document pins |
| manifest_writer, `aeda5b12…` | Context.view_pinned/veto_bounds lê diretamente o mesmo pin estático da config. `_view` exige observed igual à abertura, válida no instante; graça de5s trata entrega do arquivo, não autenticidade ou renovação |

Consequência: **o emissor não pode ser instalado com um SHA de observação Monday inventado em uma configuração assinada Saturday**. Adicionar um arquivo com outro hash ou ligar RenewableVetoReader apenas no canal restore não resolve o despacho/admissão/manifesto. O pacote não afirma que essa integração existe.

Duas rotas candidatas, ainda sem autorização/prova próprias:

1. **Configuração derivada depois do original real:** programa montador pinado e inputs estáticos autorizados antes; Monday, após autenticar o original, gerar uma configuração imutável com seu pin real e hash real, entregando settings/context próprios ao manifest_writer. Preserva os leitores da imagem. Precisa fechar autorização da escrita/montagem, roots/identidade, pin de configuração no ambiente/consumer, readback, que programas usarão essa config, e o orçamento efetivo de uma visão com no máximo10s. Não fixa antecipadamente SHA de output desconhecido.
2. **Wrapper externo de Context:** somente como programa novo pinado, com autoridade própria para compor callbacks de `verify_go`, `verify_binding`, `veto_bounds` e `view_pinned`, e o revocation_reader realmente usado pelos coletores. Todos precisam ler a **mesma** observação original/pin/contexto/autoridade, sem substituir a visão por `_no_view`. Não basta trocar um callback deixando os demais nos arquivos estáticos. Exige revisão de completude, invariantes da CapacityConfig e efeitos do worker/reader; este núcleo não implementa ou certifica esse wrapper.

Qualquer alteração na imagem fora das constantes do PR449 exigiria escopo de PR e autoridade novos; nenhuma dessas propostas é inserida silenciosamente nesse PR.

## Inputs mínimos que ainda faltam

1. ABI e original REAL da fonte factual: quem observa veto/revogações, quais pins o feed cobre, transportes/readbacks, identidade/hash da implementação e como comprova o instante observado.
2. Original da autoridade: hash, cadeia/assinaturas, fonte e verificador autorizados, epoch/first_session/day/order_sha, instante/janela, papel FABLE permitido, intervalo e escopo integral de revogação.
3. Implementação REAL do verificador e seus testes adversariais próprios. O núcleo não fornece função que aceite automaticamente campos sem autenticação.
4. Spec final sem placeholder, fonte/verificador pinados, pin independente do spec e medição/rechecks da identidade física Python/UID/BOOT/fonte/roots antes dos efeitos, sob autoridade própria do lote.
5. Rota de entrega do arquivo/pin original à imagem, montagem ou wrapper completo escolhido, consumidor final e orçamento medido que caiba na validade. Output deve ser publicado de forma imutável e conferido, sob uma escrita autorizada; nenhuma instalação/publicação vem neste módulo.
6. Ledger/claim durável e política global de tentativa única do lote, incluindo morte parcial, entrega incerta, revogação/rollback e restart sem segunda emissão/efeito autorizado automaticamente.

Enquanto esses inputs/integração/provas faltarem: **CANDIDATE_PURE_EMITTER / EXTERNAL_SOURCE_AND_REAL_VERIFIER_PENDING / IMAGE_PIN_INTEGRATION_PENDING / OPERATION_HOLD / SEM_ETA_COMPROVADO**.

## Validação local nova

Os casos sintéticos cobrem payload exato, clocks/validade, alteração de originais/spec/autoridade, verificador obrigatório, identidade/contexto/fonte, revogação integral, veto, erros sem conteúdo privado e nenhuma renovação por reinvocação. O teste de interoperabilidade executa somente as definições AST do parser/veto reader dos bytes pinados, sem importar app/DB/core do projeto. Fixtures são lidas para revisão e recusadas pelo leitor real por DRAFT. Nenhuma suíte fechada foi reexecutada; nenhum host, SQL, Docker, cifra, assinatura, instalação, publicação ou rede foi usado.
