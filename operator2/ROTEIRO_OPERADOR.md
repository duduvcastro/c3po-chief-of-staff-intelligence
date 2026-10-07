# Complemento operador2 — 07/10/2026

Esta cópia acrescenta os produtores que faltavam. Não altera o arquivo flow2 `5808bdb830b75b4b515d757d7420784f45db6a418870be2d47c630605570ee2b`, o workflow operacional `3413dc4d76fcca5e65e092ed57b6c2b644cf0bc58be1c3ef4fbcdb3b8332012f`, a E5 rev3 assinada `6eecb45632f8679d74dd4d14d8309476cbe7d6953fff52a042c8e473a74c68df` ou a autoridade datada `c0af50a35a90cb226346d775cd8854db1afc681744a8255a383a1d8de45677bc`.

O operador Fable cifra, cria os blobs e publica os controles. Os geradores só leem bytes, conferem vínculos e produzem arquivos novos; não fazem rede, importação do aplicativo, assinatura, prepare ou dispatch. Os quatro comandos anteriores de `operator_records.py` continuam disponíveis. `capsule_data.py` implementa os cinco novos comandos, com hash conferido pelo wrapper.

Use caminhos físicos, sem links, em diretório privado 0700. Os arquivos de entrada devem pertencer ao operador, sem hardlinks e sem escrita de grupo/outros. Saídas novas são exclusivas 0600; uma recusa não autoriza sobrescrever, reiniciar o job ou tentar outra autoridade. No Mac use o caminho físico `/private/tmp`, se optar por temporários.

## Comentário operacional do destinatário

O workflow operacional já publica na #429 um **corpo JSON puro**, sem cercas ou texto adicional. O formato é o objeto abaixo; as descrições entre colchetes são tipos, não valores para publicar:

```text
{
  "schema": "CAPTURE_JOB_PUBLIC_V1",
  "kind": "EPHEMERAL_RECIPIENT",
  "session": "2026-10-08",
  "run_id": [string decimal do GITHUB_RUN_ID real],
  "run_attempt": 1,
  "nonce": [32 hex produzidos pelo próprio job],
  "recipient": [destinatário age1 real da chave efêmera do job],
  "manifest_sha256": "8671e15a46627734dbcc133d59b42b574ffea134548d0cec408bec2177bb5e69",
  "status": "AWAITING_PRIVATE_INPUTS"
}
```

Autor esperado: `github-actions[bot]`, ID **41898282**, `type=Bot`, por `GITHUB_TOKEN`. A identidade da conta foi conferida pela API; o comentário futuro ainda precisa de dois GET iguais, sem edição, e vínculo com o run real. `performed_via_github_app` só pode ser ausente/nulo ou ter `slug=github-actions`. O bot não é resposta humana. Os controles do operador exigem conta `duduvcastro`, ID 313137248, `type=User`, associação OWNER e nenhum app intermediário; isso registra a Fable, não prova criptográfica humana independente.

## Quinta: contexto real antes de qualquer envio

Na preparação da Fable, os 373 blobs de `capture-flow/` devem continuar iguais ao índice `reference/SOURCE_GIT_BLOBS.json`; o workflow operacional deve ser o único em `.github/workflows/`, e a autoridade concreta deve estar em `capture-authority/DATED_AUTHORITY.json`. Não se copia autoridade física do Mac para o runner. O índice tem hash `d726d8e7764dc9cc8da8c8c85fd52f60239a64f81cf5a28e6030592c2e5e8b91`.

Em 08/10, 08:45–08:50 BRT, a Fable salva em seu diretório privado:

- dois GET do comentário EPHEMERAL_RECIPIENT eleito;
- GET de `actions/runs/<run_id>` do mesmo job, tentativa 1, ainda em andamento;
- GET de `git/commits/<head_sha>` e GET da árvore recursiva indicada por `commit.tree.sha`;
- os bytes exatos de DATED_AUTHORITY já fechados.

O ID do commit e o ID da árvore são diferentes na API. O gerador verifica a ligação entre ambos, todos os blobs do índice, o workflow único e a autoridade datada. Não usar um segundo job, restart ou fallback.

```sh
python3 -I -S -B "$OP2/operator_records.py" ephemeral-context \
  --public-readback1 "$PRIVATE/ephemeral.get1.json" \
  --public-readback2 "$PRIVATE/ephemeral.get2.json" \
  --run-readback "$PRIVATE/run.get.json" \
  --commit-readback "$PRIVATE/commit.get.json" \
  --tree-readback "$PRIVATE/tree.get.json" \
  --dated-authority "$PRIVATE/DATED_AUTHORITY.json" \
  --out "$PRIVATE/JOB_CONTEXT.private.json"
```

`OP2` é o caminho físico desta cópia; `PRIVATE` é o diretório privado novo da Fable. O contexto usa o relógio real, sem opção de falsificá-lo. Nada gera RUN_ID, nonce, autoridade ou PASS futuros.

## PRIVATE_INPUTS seq1

São aceitos apenas o arquivo privado já fechado `1580db0b3e72dcb92c2f81ee167ca02a7a28e8b73c1eefc9cecc95bf2bad6cd6` e o inventário `8671e15a46627734dbcc133d59b42b574ffea134548d0cec408bec2177bb5e69` (148 arquivos, 2.228.151 bytes). A Fable cifra **ambos** para o destinatário do contexto real. Chave privada, credenciais, known_hosts e bytes claros ficam locais; nunca em comentários, logs ou blobs públicos.

```sh
RECIPIENT=$(python3 -I -S -B -c 'import json,sys;print(json.load(open(sys.argv[1]))["recipient"])' "$PRIVATE/JOB_CONTEXT.private.json")
age -r "$RECIPIENT" -o "$PRIVATE/inputs.tar.age" "$PRIVATE/PRIVATE_INPUTS.original.tar"
age -r "$RECIPIENT" -o "$PRIVATE/inventory.json.age" "$PRIVATE/INVENTORY.original.json"
python3 -I -S -B "$OP2/operator_records.py" blob-requests \
  --cipher "$PRIVATE/inputs.tar.age" --cipher "$PRIVATE/inventory.json.age" \
  --out "$PRIVATE/private-blob-requests"
```

Os arquivos BLOB1/BLOB2.request.json contêm somente cifra em base64. A Fable faz um POST para `repos/duduvcastro/c3po-chief-of-staff-intelligence/git/blobs` com cada arquivo e salva a resposta. Depois faz GET de cada `git/blobs/<sha>` e salva **o GET** para os geradores. O SHA do objeto Git tem 40 hex; o SHA256 da cifra tem 64. O gerador confere tamanho, URL, base64, bytes e os dois hashes. A [API oficial de blobs](https://docs.github.com/en/rest/git/blobs) define esse POST/GET; o job só lê os blobs, a Fable os cria com sua permissão própria.

```sh
python3 -I -S -B "$OP2/operator_records.py" private-inputs \
  --context "$PRIVATE/JOB_CONTEXT.private.json" \
  --archive "$PRIVATE/PRIVATE_INPUTS.original.tar" \
  --inventory "$PRIVATE/INVENTORY.original.json" \
  --archive-cipher "$PRIVATE/inputs.tar.age" \
  --inventory-cipher "$PRIVATE/inventory.json.age" \
  --archive-blob-readback "$PRIVATE/inputs-blob.get.json" \
  --inventory-blob-readback "$PRIVATE/inventory-blob.get.json" \
  --out "$PRIVATE/PRIVATE_INPUTS.seq1.request.json"
```

A Fable publica uma única vez esse request na #429 até **08:50 BRT** e confere dois GET iguais ao corpo produzido. Não monta JSON à mão. O corpo tem schema `CAPTURE_JOB_CONTROL_V1`, kind `PRIVATE_INPUTS`, sequence 1, o contexto real e `document_sha256=manifest_sha256=8671e15a…`, com os dois IDs Git e os dois SHA256 das cifras.

O cabeçalho age não prova sozinho o destinatário. A cifra deve ser feita pela Fable para o destinatário real; o job ainda tem de decifrar e conferir os pins dos bytes claros. Uma falha permanece HOLD. Este produtor não substitui a aceitação física, os quatro novos PRE/L1/BOUND, as respostas humanas ou as revisões de quinta.

## Cápsula noturna e NIGHT_GATES seq1

Só depois dos **dois resultados reais** `commit_result` e `publish_launch` completos, da mesma trilha P (PRIMARY) ou S (SPARE), G19/day08/noite/host/BOOT, a Fable aponta para os BOUND originais terminados. Os diretórios PRE sem saída completa são recusados. Nunca completar recibo futuro nem mudar REQUEST/BOUND depois do Assino.

```sh
python3 -I -S -B "$OP2/operator_records.py" night-capsule \
  --commit-bound "$COMMIT_BOUND_REAL" \
  --publish-bound "$PUBLISH_BOUND_REAL" \
  --slot "$SLOT_REAL" --out "$PRIVATE/night-capsule"
```

`SLOT_REAL` é PRIMARY para P ou SPARE para S. O montador lê a árvore estável sem links, confere o conjunto e os pins dos documentos assinados, os cinco arquivos da tentativa terminada e o claim próprio. Exige KNOWN_COMPLETE, retorno 0, stderr vazio, outcomes completos e ordem causal sem recibos futuros. Preserva os bytes originais; gera `NIGHT_GATES.private.tar` USTAR determinístico, `MANIFEST.private.json` canônico e `BUILD.private.json` com `operational_READY=false`. O check é estrutural; o binder físico do job ainda rederiva os documentos/assinaturas e gates a partir dos programas próprios.

Na quinta, com o mesmo destinatário real eleito, a Fable cifra apenas o tar noturno; gera o request de blob; faz POST/GET do blob cifrado; então:

```sh
age -r "$RECIPIENT" -o "$PRIVATE/night.tar.age" "$PRIVATE/night-capsule/NIGHT_GATES.private.tar"
python3 -I -S -B "$OP2/operator_records.py" blob-requests \
  --cipher "$PRIVATE/night.tar.age" --out "$PRIVATE/night-blob-request"
# Fable cria o blob cifrado e salva seu GET real em night-blob.get.json.
python3 -I -S -B "$OP2/operator_records.py" night-gates \
  --context "$PRIVATE/JOB_CONTEXT.private.json" \
  --archive "$PRIVATE/night-capsule/NIGHT_GATES.private.tar" \
  --manifest "$PRIVATE/night-capsule/MANIFEST.private.json" \
  --cipher "$PRIVATE/night.tar.age" --blob-readback "$PRIVATE/night-blob.get.json" \
  --out "$PRIVATE/NIGHT_GATES.seq1.request.json"
```

O gerador reinspeciona os membros/pins do tar e os resultados completos. A Fable publica seq1 uma vez na #429 e confere dois GET. O corpo é `CAPTURE_JOB_CONTROL_V1`/`NIGHT_GATES`, sequence 1, contexto real, `document_sha256=manifest_sha256` do manifesto canônico, `blob_sha` e `ciphertext_sha256`. O cutoff herdado é **10:58:39 BRT**; entregar antes de capture_launch é necessário para evitar HOLD. Não criar controles após esse limite para simular prontidão anterior.

A entrega destes produtores fecha a lacuna de código do operador. Não demonstra recibos noturnos, autoridade operacional, identidade física do job, entrada de quinta ou latência futura. O arquivo flow2/E5 continua imutável. O ensaio separado está em `ENSAIO_SINTETICO.md`.
