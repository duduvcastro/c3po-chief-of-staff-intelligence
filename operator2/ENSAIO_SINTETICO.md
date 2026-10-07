# Ensaio operador2 da Fable — até 18:30 BRT de 07/10

Este é um **ensaio novo dos produtores ausentes e da troca operador/job**. O ensaio de canal anterior já fechado não precisa ser repetido. São usados três blobs cifrados de fixtures inofensivas, dois controles sintéticos e uma chave efêmera do próprio job. Nenhuma entrada privada real, chave de host, segredo de deploy, SSH, aplicativo/core, prepare, assinatura humana ou dispatch participa.

Fable copia os arquivos do DELIVERY_MANIFEST deste complemento para `operator2/` de uma cópia isolada e põe somente `operator2-rehearsal.yml` em `.github/workflows/operator2-rehearsal.yml`. O branch exclusivo é `ops/capture-operator2-rehearsal-20261007`. A Fable faz o push e elege a primeira tentativa real. Não rodar o workflow operacional nem outros workflows nessa cópia. Conferir o head e os bytes com o manifesto publicado; a conclusão do ensaio não transfere PASS para a VM de quinta.

O job recusa outra data/tentativa. Primeiro confere os hashes/AST do complemento e roda os **27 métodos novos dos produtores + 7 do isolamento/CLI** em Linux. Publica `OPERATOR2_NEW_DATA_PROOF` contendo somente os dois RESULT.public.json. Depois instala age 1.3.2 dos bytes oficiais fixados no workflow e publica o destinatário sintético na #429. Espera os dois controles por no máximo 20 minutos ou até 18:30 BRT, o que ocorrer primeiro. Começar com tempo para essa troca; o limite não autoriza reinício.

O comentário esperado usa autor `github-actions[bot]`/41898282/Bot. Seu corpo JSON tem schema `CAPTURE_OPERATOR_REHEARSAL_PUBLIC_V1`, kind `EPHEMERAL_RECIPIENT`, session `2026-10-07`, run_id real, run_attempt 1, nonce real, scope `SYNTHETIC_NO_OPERATIONAL_AUTHORITY`, recipient real e status `AWAITING_SYNTHETIC_INPUTS`. **Não é o schema operacional**; nenhum controle deste ensaio é aceito pelo receptor de quinta.

No diretório privado novo da Fable, gerar as fixtures e salvar dois GET iguais do comentário sintético e o GET do run em andamento:

```sh
python3 -I -S -B "$OP2/rehearsal_channel.py" fixtures --out "$PRIVATE/fixtures"
python3 -I -S -B "$OP2/rehearsal_channel.py" context \
  --public-readback1 "$PRIVATE/rehearsal.get1.json" \
  --public-readback2 "$PRIVATE/rehearsal.get2.json" \
  --run-readback "$PRIVATE/rehearsal-run.get.json" \
  --out "$PRIVATE/REHEARSAL_CONTEXT.json"
RECIPIENT=$(python3 -I -S -B -c 'import json,sys;print(json.load(open(sys.argv[1]))["recipient"])' "$PRIVATE/REHEARSAL_CONTEXT.json")
age -r "$RECIPIENT" -o "$PRIVATE/inputs.age" "$PRIVATE/fixtures/INPUTS.fixture.tar"
age -r "$RECIPIENT" -o "$PRIVATE/inventory.age" "$PRIVATE/fixtures/INVENTORY.fixture.json"
age -r "$RECIPIENT" -o "$PRIVATE/night.age" "$PRIVATE/fixtures/NIGHT.fixture.tar"
python3 -I -S -B "$OP2/operator_records.py" blob-requests \
  --cipher "$PRIVATE/inputs.age" --cipher "$PRIVATE/inventory.age" \
  --cipher "$PRIVATE/night.age" --out "$PRIVATE/rehearsal-blobs"
```

Fable cria os três Git blobs com os requests BLOB1/BLOB2/BLOB3 e salva cada GET real. Só cifra é publicada. Em seguida gera dois controles, publica cada request uma vez na #429 e lê cada comentário de volta:

```sh
python3 -I -S -B "$OP2/rehearsal_channel.py" control --kind PRIVATE_INPUTS \
  --context "$PRIVATE/REHEARSAL_CONTEXT.json" \
  --cipher "$PRIVATE/inputs.age" --blob-readback "$PRIVATE/inputs-blob.get.json" \
  --manifest "$PRIVATE/fixtures/INVENTORY.fixture.json" \
  --inventory-cipher "$PRIVATE/inventory.age" \
  --inventory-blob-readback "$PRIVATE/inventory-blob.get.json" \
  --out "$PRIVATE/REHEARSAL_PRIVATE.seq1.request.json"
python3 -I -S -B "$OP2/rehearsal_channel.py" control --kind NIGHT_GATES \
  --context "$PRIVATE/REHEARSAL_CONTEXT.json" \
  --cipher "$PRIVATE/night.age" --blob-readback "$PRIVATE/night-blob.get.json" \
  --manifest "$PRIVATE/fixtures/NIGHT_MANIFEST.fixture.json" \
  --out "$PRIVATE/REHEARSAL_NIGHT.seq1.request.json"
```

Ambos são `CAPTURE_OPERATOR_REHEARSAL_CONTROL_V1`, session 07/10 e scope sintético. Conta do operador exigida: duduvcastro/313137248/User/OWNER, sem app e sem edição. Corpo canônico, mesmo RUN_ID/tentativa/nonce; controles duplicados recusados. Não copiar esses controles para a quinta.

O job confere os SHA Git/SHA256 das cifras, decifra com sua chave efêmera e aceita somente os bytes exatos das fixtures fixas. Publica `PASS_SYNTHETIC_OPERATOR_EXCHANGE_ONLY`, 3 blobs/2 controles/0 chamadas de host/0 perguntas ao dono/operational_READY=false. O artefato `OPERATOR2_SYNTHETIC_CHANNEL_RESULT` contém somente CHANNEL_RESULT.public.json; chaves e bytes claros não são exportados.

Fable entrega na #429: run_id/head/tentativa, IDs e hashes dos dois controles, comentário RESULT, IDs dos artefatos e SHA256 dos ZIPs. A reconciliação Codex confere esses bytes/API e fecha apenas esse novo escopo sintético/Linux. A identidade física, os recibos noturnos e as quatro folhas próprias do job de quinta continuam exigidos. Se houver falha, trazer o erro concreto; nenhum retry ou GO é criado por este roteiro.
