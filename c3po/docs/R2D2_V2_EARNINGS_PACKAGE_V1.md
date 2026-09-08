# Pacote de implementação E3 rev3 — identidade e liberação V3

Estado desta entrega: **DRAFT_UNAPPROVED; sem prontidão, consentimentos de implementação ou ativação emitidos**. Os JSON em `r2d2-v2-earnings-package-draft/` são modelos, com campos `null` que o release recusa. A adoção normativa da E3 não é uma assinatura desses novos bytes de implementação.

## Identidade preservada e identidade nova

Os textos/assinaturas anteriores não são reescritos. Continuam identificados:

- Conjunto base: `eabbe18057b7e5823535dd61e93c5190b33f8c7ac80b9118229b7908f974f4d0`.
- E1 rev2: `3a25b9929d0c65aa97fe90b9c9cfc7dd904fedde23df884e8e42f199ae2e5ff4`.
- E3 rev3: `3319407afcd7760668e6ec73bb4686ecb95a38eecf47fc157050899f80a6cc9c`.
- Manifesto normativo E3 fechado: `1a927ca41df89ccb28a276726626672b7d76a9e828f12e4fc5b126860dbb4e72`, sem autorização de ativação por si.

O componente earnings novo tem **exatamente nove chaves**: `coverage_verified`, `window_start`, `window_end`, `events`, `source_at`, `available_at`, `policy`, `evidence`, `exclusion`. O discriminador é `policy.rule=EXCLUSION_RULE_V1` com o SHA exato da E3. O envelope de snapshot permanece `V2_SHADOW_SOURCE_SNAPSHOT_V2`; isso não admite componentes earnings legados. A fronteira de componente, a recomputação de evidência/veredito e o evento vivo com granularidade estão nos módulos policy/events/contract/source; este documento fecha identidade e liberação do conjunto de implementação.

Na admissão, a exclusão usa a decisão nominal das **10:00 de Nova York**, conforme §3.2; o instante factual do coletor confere causalidade e captura dentro de `[10:00,10:01)`. Na observação viva, a janela usa o `opened_at` real do episódio. O evento exige `event_at` somente para `INSTANT`; nas granularidades `AMC`, `BMO` e `DAY` a chave deve estar ausente. O hash de revisão normaliza o instante para UTC, preservando o payload recebido como evidência.

Cada rodada identifica a sessão oficial alvo em `round_session` e o recebimento factual em `round_received_at`. O recebimento deve ocorrer após o fechamento dessa sessão e a partir das 18:00 de Nova York; atraso é permitido e não muda a sessão alvo nem retrodata a observação. O resumo público preserva os quatro pins, contagens por estrato de risco (ou `UNASSIGNED` quando o risco é inválido) e diagnósticos de saída por sessão efetiva da saída. Esses campos não autorizam novas classificações fora da E3 assinada.

`r2d2_v2_earnings_package.earnings_contract()` descreve schemas/política; `implementation_contract_sha()` é seu SHA256 canônico. `implementation_package()` inclui esse contrato e SHA256 dos dez arquivos instalados: o próprio módulo de identidade, policy, events, contract, portfolio, sources, shadow, inference_input, shadow_worker e config. `implementation_package_sha()` sela esse descriptor. Codec: JSON ordenado, compacto, ASCII escapado, sem NaN, UTF-8.

O descriptor não contém um hash hardcoded de si próprio. O próprio arquivo Python é medido como os demais, evitando referência circular. O import não lê arquivos. Release e construção do coletor solicitam explicitamente a medição dos bytes locais; o coletor conserva esse pin durante o processo, sem re-hashear código a cada tick. Imagens/código instalados devem permanecer imutáveis durante o processo. Alteração de fonte muda a identidade e exige novo pacote/rito, não uma substituição silenciosa.

O manifesto JSON em draft é um inventário dos bytes no momento da preparação. Deve ser regenerado e conferido após o freeze final de código, antes de colher os três consentimentos. Sua propriedade `approval_state` continua `DRAFT_UNAPPROVED`; um descriptor com hashes corretos não é aprovação.

## Release e recibos formais

Somente `R2D2_V2_RELEASE_V3` é aceito. Releases V1/V2 não têm fallback. Além dos campos anteriores de revisão, calendário, autorização, CAL-3 e auditorias, são obrigatórios:

O parser rejeita chaves duplicadas em qualquer nível e tokens JSON não finitos, mesmo quando o SHA externo coincide com os bytes recebidos. Um campo duplicado não pode substituir silenciosamente o pin ou a aprovação de uma parte.

| Campo | Conteúdo |
|---|---|
| `earnings_amendment_sha` | E3 rev3 exata |
| `earnings_closed_manifest_sha` | Manifesto normativo E3 fechado exato |
| `implementation_contract_sha` | Descriptor de dados/schema exato do código instalado |
| `implementation_package_sha` | Hash dos bytes do pacote instalado |
| `package_consents` | Exatamente um registro CODEX, um FABLE e um DUDU, todos `approved: true` |

Cada registro em `package_consents` usa `R2D2_V2_EARNINGS_PACKAGE_CONSENT_V1`, com `party`, `approved`, `approved_at`, `receipt_sha`, `receipt_ref`, os quatro pins acima, `code_revision`, `code_audit_sha`, `source_audit_sha` e `readiness_sha`. Todos os bindings coincidem com o release; nomes de partes, booleans falsos/textuais, pins vazios e recibos de outro pacote não bastam. A aprovação de cada consentimento não pode ser posterior à aprovação do release; em CERTIFIED não pode anteceder a declaração de prontidão vinculada.

**Fronteira formal, sem simular autenticação:** o operador confere a autoria, os bytes publicados e as referências dos três recibos reais. O código valida formato, pins e vínculos dentro do arquivo de release cujo SHA dos bytes foi fixado pelo operador. Não busca recibos na rede, não autentica autores criptograficamente e não substitui os pareceres. Nenhuma assinatura foi copiada do manifesto normativo E3 como se aprovasse implementação.

Os arquivos `consent-*.template.json` são documentos de consentimento ainda incompletos, sem seu próprio hash. Depois de efetivamente emitido/publicado cada documento, o operador calcula o SHA dos **bytes desse arquivo** e cria sua projeção no release, acrescentando `receipt_sha`/`receipt_ref`. Esses metadados não integram o documento que hasheiam: não há auto-hash circular. Os exemplos de testes são explicitamente sintéticos e não autorizam nada.

DIAGNOSTIC continua sem ledger, outcomes ou relógio certificador, mas também exige identificação e consentimentos para o pacote novo. Referências de auditoria/prontidão nesse modo podem documentar uma autorização somente diagnóstica; não equivalem aos gates adicionais de CERTIFIED. CERTIFIED conserva CAL-3 ACCEPTED, as duas assinaturas das fontes e os relógios de prontidão/deploy. A primeira sessão é a primeira abertura oficial estritamente posterior à declaração `readiness_at`; publicação/aprovação tardias não deslocam essa sessão.

## Persistência, exportação e inferência

O estado passa a `R2D2_V2_SHADOW_STATE_V3`, o export a `R2D2_V2_COHORT_EXPORT_V3` e o adapter a `R2D2_V2_INFERENCE_INPUT_V3`. Estado e export carregam os quatro pins E3/pacote junto com base/E1, release, revisão e prontidão. O coletor rejeita construtor sem identidade, estado antigo ou troca dos pins/modo/release/revisão no ciclo. Nova liberação exige época nova pelas travas de store existentes; dados antigos permanecem auditáveis, sem reclassificação em E3.

O adapter de inferência permanece puro: **não lê código nem faz I/O**. Valida E3/manifesto/contrato exatos, exige um SHA de pacote e conserva-o. A identidade dos bytes instalados foi conferida na fronteira Release/coletor; aqui não se inventa essa prova. O prefixo 40→60 exige igualdade dos quatro pins e dos demais identificadores, além de igualdade das linhas completas já prevista.

Nove campos do estimador, batches de dez sessões, coortes 40/60 e maturação 49/69 não mudam. Não se recalculou calibração e não se alterou o algoritmo do estimador. CAL-3 não prova completude de feed. A população/desfechos passam pelas exclusões e pela observação E3 assinadas; o hash desse contrato acompanha o dado.

## Sequência ainda pendente

Freeze do código → manifesto com hashes finais → auditorias cruzadas do código e fontes → prontidão documentada → três consentimentos sobre o mesmo pacote/prontidão → release V3 e ordem aplicável → execução na primeira sessão previamente declarada. Esses passos não são executados ou aprovados pelos modelos desta PR. OFF continua o padrão.
