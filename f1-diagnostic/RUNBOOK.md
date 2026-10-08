# F1 — sequência da Fable e provas a devolver

Este roteiro descreve ações futuras da Fable. Não executa nenhum job, assinatura, host ou diagnóstico. O pacote recebido é fonte fechada; conferir arquivo/SHA256SUMS e conservar os originais. Se qualquer passo faltar ou o prazo vencer, publicar o requisito específico e HOLD imediatamente.

## Prova Linux própria, primeiro

1. Fable confere os bytes do arquivo, extrai o único diretório `f1-diagnostic/`, preserva todos os membros e instala a cópia exata de `linux-proof.yml` em `.github/workflows/f1-provider-diagnostic-proof.yml` no ramo `ops/f1-provider-diagnostic-proof-20261008`. Codex não faz push ou dispatch.
2. O workflow por push, tentativa 1, usa somente fontes públicas pinadas, fixtures e segredo efêmero de fixture; não usa token do provedor, SSH, app, SQL, Docker, root real, chave da Fable ou pergunta ao dono. Seus artefatos contêm somente resultados de teste/selo e nomes dos testes. Nunca incluir fixture.key ou diretório privado do CI.
3. Devolver head/commit/tree, ID do run, tentativa, estado, workflow SHA256, artefato único/ID/digest/API, ZIP original e membros dos resultados. Codex compara cada fonte + workflow e resultados/escopos. Testes de cifra do CI não certificam uma cifra para a chave real da Fable nem o servidor futuro. Não repetir um ensaio fechado sem falha concreta ou novos bytes.

## Preparação do executor próprio — sem folha fictícia

4. A Fable escolhe o executor Linux realmente autorizado e área privada exclusiva fora de ancestrais graváveis por grupo/outros. O uso de servidor cabe somente no escopo privado da Emenda 6; nenhuma mutação de worker/SQL/container ou criação de autoridade para F2–F6. Respeitar exclusão de deploy/merge/operação simultânea. A eleição, raiz e ledger nunca mudam para permitir outra tentativa.
5. Instalar a fonte/selo recebidos e age Linux pinado no executor por autoridade própria. Não preencher BOOT/UID/paths/fonte com valores do CI, do Mac, de quinta cancelada ou da imagem anterior. O programa não importa o app C3PO; seu runtime é Python/age próprios. Devolver a medição completa e os pins necessários, privada, sem hostname/caminhos públicos.
6. Medição: `python3 -I -S -B measure_runtime.py --private-root <RAIZ_PRIVADA> --age-path <AGE_PRIVADO>` produz JSON canônico **privado** em stdout, sem LF. Redirecionar para `MEASUREMENT_SET.json` sob umask077 em área própria. Não rodar esse comando em log público, nem chamá-lo como Codex/heartbeat. Ele lê metadados/bytes e não cria diretórios, token, assinatura ou contato com o provedor.
7. `bind_diagnostic.py measurement --inputs <INPUTS> --out <MEDICAO_NOVA>` separa measurement/runtime/election canônicos mantendo os hashes. O original medido permanece retido. Devolver esses bytes ao Codex para revisão junto com a prova Linux própria. Sem revisão escrita exata, não há pergunta da folha.
8. A assinatura original da Emenda 6, pinada no contrato, é colocada privadamente como `amendment-original.json`. `bind_diagnostic.py amendment --inputs <INPUTS> --out <EMENDA_NOVA>` valida os bytes e gera somente o adaptador com original completo. Não produz uma resposta ou assinatura nova.

## Folha e assinatura antes da única leitura

9. `bind_diagnostic.py config --inputs <MEDICAO_NOVA> --out <CONFIG_NOVO> --execution-date 2026-10-08` produz a janela proposta 17:26:00–17:33:39 BRT usando o age_path da medição. O dia é explícito. A opção 2026-10-09 oferece 14:26:00–14:33:39, somente se nenhuma tentativa real de quinta ocorreu e com novo REQUEST/Assino próprio. Não torna sexta um retry nem cria disponibilidade do dono.
10. Inputs canônicos privados: config.json, election.json, runtime.json, review.json e amendment_signature.json. O review.json vem do parecer aceito real, não de edição de fixture/flag. `bind_diagnostic.py request --inputs <INPUTS> --out <FOLHA_NOVA>` verifica todos esses registros e cria REQUEST.json/OWNER_QUESTION.txt e cópias dos inputs. Nenhuma pergunta se input/assinatura da emenda/prova/runtime/revisão estiver ausente ou inválido.
11. Fable apresenta a pergunta exata ao dono e registra a resposta real. Publicar apenas pergunta com hashes/janela, sem inputs privados. Conservar preparado/POST/GET1/GET2 e literal/instante. O registro owner.json deve ter schema F1_OWNER_SIGNATURE_V1, request_sha256, question_sha256, answer, recorded_at_utc, channel. Somente literal Assino da própria pergunta, canal REGISTRO_PELA_FABLE. Ausência/NÃO/outra resposta é HOLD; não rodar gerador de resposta Assino automática. Prazo humano de hoje: 17:00; avisar na hora se faltar.
12. Copiar esses originais para INPUTS de vínculo, com REQUEST.json e owner.json. `bind_diagnostic.py bound --inputs <INPUTS> --out <BOUND_NOVO>` gera BOUND.json e cópias exatas, sem executar programa/host/crypto. Codex confere vínculo/folha/resposta por bytes e readbacks. Não alterar REQUEST, BOUND ou qualquer pin depois de Assino. Nenhum selo/artefato/recibo futuro é placeholder substituível após assinatura.

## Despacho e coleta da Fable

13. Antes de iniciar: confirmar autoridade vigente/sem Revogo, exclusão mútua e fim dos deploys; eleição/ledger/claim próprios contínuos; fonte/selo/reference/Python/age/BOOT/UID/área medidos e aceitos; todos os gates documentais e humanos completos. Retirar a opção de folha não usada por registro próprio, sem apagar históricos ou fabricar ausência de despacho.
14. A Fable registra o único despacho real no ledger/coordenação, inclusive eventual recusa/resultado incerto. Só então, na janela e antes do último início 17:31:39: `python3 -I -S -B diagnostic_runtime.py --bound <BOUND_PRIVADO>`, token em ambiente privado. Não encaminhar token em argv nem em log. Invocação real recusada também não permite nova invocação; zero GETs no recibo ou ausência de claim não são permissão de retry.
15. Preservar claim, cifra e RESULT.public.json, inclusive incompletos/HOLD. Não apagar, recifrar, reenviar consulta, usar nova raiz ou fazer fallback de host. Se transporte/cifra/arquivo/prazo for incerto, HOLD; uma segunda leitura sexta é vedada.
16. Devolver recibo público por preparado=POST=GET1=GET2, cifra original privada com hash/tamanho, e originais privados decifrados pela Fable apenas quando autorizada para fazê-lo. Comparar inventory.json e cada corpo/membro contra o mesmo recibo/cifra. Somente depois os símbolos/razões técnicas entram na revisão privada F2. Público continua sem nomes/caminhos/segredos.

## Fechamento esperado

Sucesso: dois corpos novos exatos e privados, listas técnicas E−P/P−U, contagens, last_trade UNKNOWN explícito e prova da mesma cifra/manifesto. Ainda provider/capacidade/E6/entradas HOLD. Falha: código/status, bytes parciais quando disponíveis, tentativa consumida e zero retry. O diagnóstico não é gate causal da noite de domingo para segunda. F2–F6 exigem seus próprios programas/contratos/época/autoridades/pins/provas; não copiar a folha F1 ou Emenda 6 para eles.
