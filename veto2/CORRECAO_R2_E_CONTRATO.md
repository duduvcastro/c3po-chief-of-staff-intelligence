# Emissor veto R2: correção VETO-B1/S1/S2/S3

CANDIDATE_PINNED_VERIFIER_AND_REAL_CLOCK_ONLY / OPERATION_HOLD. Fonte SHA256 f8370c789eebf0d58ec629c474e16c8a3f176facddda39e413a80e5af9c7f5bc. R1 permanece histórica e não deve ser usada para emissão REAL. Doze casos novos de defeito passaram localmente em fixtures, zero falhas/erros; os trinta casos R1 fechados não foram repetidos. Nenhuma observação de segunda, arquivo no servidor, assinatura, consulta operacional, instalação ou prova de latência foi feita.

## Interface

`load_verifier(path, ancestors=tuple((absolute_path, (dev, ino, uid, gid, mode))), identity=..., implementation_sha256=..., mode=..., context=...)` lê descritores de toda a cadeia com O_NOFOLLOW, mede fonte regular exclusiva e hash antes de compilar esses mesmos bytes. REAL exige arquivo e diretório final de dono UID0 sem escrita de grupo/outros. O módulo pinado precisa declarar VERIFIER_MODE e uma função verify_original; bind_context é opcional e precisa ser função do próprio módulo. A identidade, fonte e dependências/contexto desse programa continuam sujeitos à autoridade externa real; carregar bytes não atesta semântica arbitrária.

O emissor REAL aceita apenas um LoadedVerifier registrado por esse carregador, conferido de novo antes e após a verificação, e `clock is real_clock`. Um callable com metadados, lambda True, módulo forjado, função substituída ou relógio fornecido pelo agendador não produz ISSUED. FIXTURE admite callbacks explícitos e sempre produz DRAFT.

O spec V2 acrescenta consumer_config_template_sha256 e consumer_document_pins; `emit_view` exige os bytes originais do template por consumer_template_raw. Todos os document_pins reais do template, inclusive REVOCATIONS, precisam coincidir com a lista e estar no escopo de revogação. O spec também pinna o template. A verificação externa precisa comprovar os documentos efetivos, sua autoridade e revogação vigente; o parser não transforma a coincidência de hashes em aprovação.

O original mantém seu observed_at e valid_until, inclusive frações de segundo. O view_opens_at precisa ser o instante factual original, nunca um horário planejado arredondado. Quando o instante não existe antes do efeito, a autoridade assinada antes dele precisa autorizar explicitamente a regra de derivação para produzir o spec/config real posterior; não pinna SHA futuro. Reinvocar o emissor não renova observação nem prazo.

## Limites e pendências

A saída permanece o ABI VETO_VIEW do consumidor da imagem: epoch/day/order_sha de ACT_B machine-order, validade no máximo 10s, owner_veto falso e revoked_shas conferidos. Não confundir esse digest machine-order com runtime_order_sha ou Markdown DOCUMENT_ORDER_SHA. O dia factual em Nova York precisa ser DAY; uma observação de domingo não é VETO_VIEW de segunda. O lote L12 tem contrato ALLOW distinto, no máximo 5s, próprio de domingo/UPSTREAM_P, ainda fora desta entrega.

Faltam originals finais REAL do spec/template, programa externo verificador com caminho/ancestrais e dependências pinados, autoridade assinada da regra derivada, fonte factual/eleição física, revogações e snapshots reais, vínculo atual ACT_B e machine-order04, pacote/release/runtime e readbacks de instalação. Prova Linux própria destes novos bytes e orçamento físico ≤10s também continuam pendentes. Nenhum callback padrão REAL é fornecido; nenhuma fixture ou booleano pode completar essas pendências.

A configuração finalizadora R3 anteriormente entregue usa o hash R1 do emissor: esta V2 requer adaptação em nova cópia dependente com pin próprio. Não editar finalizador R3 ou selos anteriores para aparentar compatibilidade.
