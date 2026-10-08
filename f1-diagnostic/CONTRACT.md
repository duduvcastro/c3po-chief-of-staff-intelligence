# F1_PROVIDER_DIAGNOSTIC_V1 — contrato de uma leitura

Entrega de fonte e prova local autorizada pelo dono em 08/10/2026. O contrato é próprio da Emenda 6 rev1, SHA256 `03c9dddd2858fde584a6ccb5dd2ad74caac0a366fa03782132a161774c061efd`, e do desenho `5dcbe133d8e52ea339e7e24beefe10951eef7cf55e8c07f076a9bd9585632bae`. A assinatura documental da emenda foi registrada pela Fable no comentário 6064499368; original SHA256 `a46011c1b27c0f16161bbda4fbc38de6e740c888c172c1de5f7540b63b70f58d`. A assinatura da emenda não assina a futura folha.

**SOURCE_DELIVERY_ONLY / OPERATION_HOLD.** A família, o selo, os testes e o workflow não são uma folha real, assinatura, runtime aceito, prova do servidor, prontidão, capacidade, E6 ou GO de entradas. O binder desta família é próprio e limitado à F1; não insere a operação no registry histórico nem transfere seus 118 controles. Nenhum REQUEST/BOUND real de execução é fornecido neste pacote.

## Efeito permitido

Uma tentativa total na época `R2D2-V2-SHADOW-2026-10-05`, operação `GO_READ_PROVIDER_DIAGNOSTIC_EMENDA6_ONCE_01`, pelo executor Linux próprio da Fable. Até dois GETs HTTPS em `eodhd.com:443`: `/api/exchange-symbol-list/US`, sem parâmetro de data, e `/api/eod-bulk-last-day/US`, com `date=2026-10-07`. `fmt=json`, `Accept-Encoding: identity`, sem redirect, fallback, retry ou consultas por símbolo. Falha na primeira resposta interrompe a segunda consulta. Não há mudança de worker, app, policy, cadastro, universo, régua, banco, containers ou estado operacional.

O programa requer todos os registros canônicos e pins completos antes de acessar o provedor. A chave privada age não é entrada: somente o destinatário público da Fable é fixado no programa. O token entra exclusivamente no ambiente `F1_PROVIDER_TOKEN`, não em argumento, arquivo de evidência, recibo público ou ambiente do filho age. A conexão TLS usa a verificação normal de certificado/hostname da stdlib.

## Relógio e orçamento

Datas permitidas: quinta 08/10, dentro de 17:00–18:30 BRT; ou sexta 09/10, dentro de 14:00–17:30. Subjanela própria de 120 a 900 segundos, com início e instante efetivo de partida permitidos pela A2 rev3. A família rejeita HH:10–25 e as margens de 80 segundos anteriores a HH:05, HH:10 e HH:35.

Configuração proposta de quinta: **17:26:00–17:33:39 BRT**, último início **17:31:39**. Não é aprovação para iniciar às 17:15. O gerador oferece, para uma eventual folha própria de sexta, 14:26:00–14:33:39; essa opção não autoriza nem agenda uma segunda tentativa. A folha de quinta deve estar assinada até o prazo humano de 17:00; prazo vencido exige aviso imediato e decisão explícita, sem assinatura retroativa.

Orçamento máximo de execução: 120 segundos desde a validação inicial; até 60 segundos para consultas/análise, até 60 para a cifra, cada consulta com limite total de 15 segundos. Linux usa relógio monotônico e alarmes físicos, além do relógio UTC e do término da folha. Há limites de 32 MiB para registry, 64 MiB para bulk, 128 MiB para o pacote privado e 1 MiB para o BOUND. Limite excedido ou perda do prazo resulta em HOLD e proibição de repetição. Esses são limites de recusa; não garantem que o provedor ou o computador terminarão com sucesso nesse tempo.

## Dados e diagnóstico

`reference_extract.py` contém 19 nós copiados por bytes da fonte oficial do produtor, SHA256 `00fbb94b1abc873446b1bf50b4d78e042c3f04a225bef24d4cef698edc24c579`; o extrato é `e50e2263ea07a5a31db43f3e2a6cb68dec769ffa1e808d6197f622c78020acd1`. Inclui o normalizador, seus tipos, primeiro registro de símbolo vencedor, `_distinct`, `_number` e `_bar`. A proveniência identifica intervalos, hashes e AST. Não importa nem executa o app oficial. Python 3.12 adiciona campos AST vazios; o verificador remove exclusivamente esses campos vazios na comparação com o AST original 3.9.

Sejam E os símbolos elegíveis pelo normalizador pinado, P os de E presentes em linhas do bulk datadas 07/10 e U os de P com barra utilizável pelo mesmo `_bar`, sem conflito. A saída privada inclui E−P e P−U, símbolo e ponteiros para as linhas cruas, duplicatas, conflitos, linhas ignoradas e razões técnicas comprovadas pelos campos. Preserva `ceil(95% × |E|)` e piso 4.000 como descrição da régua; não avalia nem concede um gate operacional. Ausência do bulk não é causa comercial/provedor comprovada. Horário de download não é atualização semântica do registry.

**Último pregão por símbolo permanece UNKNOWN_NOT_PROVIDED**, porque não há campo com semântica de último pregão certificada nos dois endpoints pinados. Não inferir último pregão de `updated_at`, `last_trade` não certificado, data de download ou data da barra solicitada. Não são feitas consultas históricas adicionais. A nova observação não recupera os nomes dos corpos antigos não retidos e não substitui uma prontidão causal futura.

## Retenção e divulgação

O pacote USTAR é montado em memória: corpos crus recebidos, seus metadados de transporte, registros documentais do vínculo, análise quando completa, falha quando aplicável e inventário de hash/tamanho de cada membro. Se a conexão ou o tamanho interromper a resposta, preserva os bytes efetivamente entregues à biblioteca, marcados parciais; não certifica bytes nunca retornados pela biblioteca. Se a análise exceder o espaço permitido, conserva os corpos recebidos e a falha, sem declarar diagnóstico completo.

Somente `age` Linux 1.3.2, SHA256 `eb7dd1b518f0a307c99cd97782623c5321da049154b04acd2d98d21aa7bc9b2c`, cifrando para `age1knekenhrh79x9xm0ghvhltwg075d33mljhu4y6u9zyz3cweszens2vr8x0`. Execução pelo descritor mantido aberto e rechecado; plaintext somente em stdin, stderr descartado, sem token no filho. Não há gravação plaintext em arquivo pelo programa. A cifra não é assinatura, GO nem recuperação garantida se disco/filho/prazo falhar. O cabeçalho age sozinho não prova destinatário: os bytes pinados/comando e a posterior decifra privada exata pela Fable são as provas pertinentes.

Público: status/código fixo, contagens, horários, hashes, tamanho da cifra e número de GETs. Não publica símbolos, causas privadas, corpos, token, hostname do executor, caminhos internos, parent identities ou exceções livres. `DIAGNOSTIC_COMPLETE_WITH_LAST_TRADE_UNKNOWN` significa somente diagnóstico técnico completo dos dois corpos novos, com limite explícito de último pregão; não READY. Falha é `DIAGNOSTIC_HOLD`.

## Uso único e área privada

Uma eleição canônica, hash registrado/reconciliado antes da folha, determina uma única raiz privada e seus ancestrais: device/inode/uid/gid/mode. A raiz é exclusiva do executor, mode 0700; ancestrais não podem ser graváveis por grupo/outros nem links. O programa caminha por descritores mantidos abertos. O executável age é filho direto da raiz, arquivo regular, sem hardlinks, não gravável por grupo/outros; bytes e identidade são conferidos. Originais, fonte, intérprete, BOOT e selo precisam corresponder aos pins próprios.

Escritas enumeradas, somente nessa raiz: `emenda6-provider-diagnostic-epoch03.claim`, `provider-diagnostic.age`, `RESULT.public.json`, arquivos mode 0600. O claim `O_EXCL` é anterior a qualquer GET/filho e é compartilhado entre quinta e sexta. Nada é sobrescrito, apagado, desbloqueado ou recuperado automaticamente. Reserva existente, inclusive arquivo incompleto de falha, impede a operação. A Fable registra **qualquer invocação real do CLI**, inclusive recusa antes da reserva por identidade/tempo/documento inválido, como tentativa consumida: ausência de claim não prova ausência de despacho e não concede retry. Nunca escolher outra raiz para contornar o claim. Sem continuidade comprovada da eleição/ledger, HOLD.

## Registros exigidos

`F1_BOUND_V1` é JSON canônico com `documents` contendo request, owner, amendment_signature, election, runtime e review. O builder preserva originais completos no vínculo e calcula hashes; não gera resposta humana ou veredito aceito. Tipos/campos exatos estão nas constantes e validadores da fonte.

1. `F1_AMENDMENT_SIGNATURE_V1`: adaptador data-only do original real pinado e do comentário 6064499368, guardando o original em base64 privado, hash, literal e instante. Não substitui os bytes nem os autentica criptograficamente como assinatura independente.
2. `F1_SINGLE_ELECTION_V1`: raiz/ancestrais reais, operação/época/Emenda 6 e nome fixo do claim. Uma eleição para toda a opção quinta/sexta.
3. `F1_RUNTIME_MEASUREMENT_V1` e `F1_RUNTIME_IDENTITY_V1`: medição Linux própria pela Fable, fonte, extrato, selo, age, versão/hash do executável Python, BOOT, UID e diretórios. A identidade aponta para o hash da medição original. Medição CI é CI, não servidor de produção.
4. `F1_CODEX_REVIEW_V1`: somente após prova Linux própria por head/run/tentativa/artefato e comparação dos mesmos bytes, mais revisão da medição do executor real e eleição. Hashes de resultados e parecer concretos, veredito `ACCEPTED_OWN_BYTES_LINUX_AND_RUNTIME`. Sem placeholders, fixture, veredito autoemitido ou transferência de PASS antigo.
5. `F1_REQUEST_V1`: builder data-only com pins dos quatro registros, fonte/extrato/selo/age, calendário fixo, data/janela e orçamento. Preflight completo sem owner fictício antes de produzir `OWNER_QUESTION.txt`.
6. `F1_OWNER_SIGNATURE_V1`: a Fable registra a resposta humana real da própria pergunta, com hash da pergunta e REQUEST, literal `Assino`, instante e canal aceito. Ausência/NÃO/outra resposta é HOLD. GETs/readbacks reais da pergunta/resposta precisam fechar sem edição. Registros pela Fable são documentais, não criptografia humana independente.

REQUEST e BOUND ficam imutáveis após Assino. Revogo A2 ou Revogo emenda 6 interrompe o ramo: a Fable reconsulta os registros aceitos antes do único despacho, verifica que nenhum deploy/merge/operação concorrente está em andamento, e não inicia fora da folha ou com autoridade consumida. O diagnóstico não tem permissão para alterar a policy nem retirar outras autoridades. A nova imagem relatada pela Fable exige provas/pins atuais dos ramos que dependem dela; esta família executa Python/age próprios, sem importar ou certificar a imagem C3PO.

## Prova e limites

Mac: testes novos e inteiramente sintéticos do programa e builder, sem rede, app, host, crypto real ou assinatura real. Linux: workflow próprio de teste da família exata, os mesmos testes, file guards físicos do CI e roundtrip age com destinatário/chave efêmeros e dados sintéticos. Não toca provedor/host de produção e não usa chaves reais. O resultado distingue esses fatos e não aceita o runtime futuro. Prova Linux, medição real, revisão, folha e assinatura ainda são entregas posteriores da Fable/dono/Codex. Codex não faz push/dispatch, consulta física ou leitura do provedor.
