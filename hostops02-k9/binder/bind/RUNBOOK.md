# RUNBOOK — bind_once.py: vinculação e despacho único das famílias "once"

Documento do operador (Fable). Vale para W1 (revisão 3), HOSTOPS01 (precheck, provision, install_units, readback),
HOSTOPS02 (K2a catalog_init, K10 install_release, K11 epoch_readback, K6a activate: seção 10) e para as fontes futuras
que reusarem o núcleo do HOSTOPS01. O binder **nunca despacha**: as duas fases do dispatcher
(`prepare` e `resume`) são rodadas à mão, por este runbook. **O bloco 9 (resume) é o único que contata o servidor,
roda uma vez e nunca é repetido.**

## 0. Regras que valem para todos os blocos

- Um bloco por vez. Ler o `exit=` impresso e o JSON antes de seguir. `set -e` não vale neste shell: os blocos
  decidem por `if` e por `&&` e conferem o código de saída.
- Todo bloco começa com `L=<label>; if source .../runbook_env.zsh; then`, porque o estado do shell não persiste. O
  `source` liga `noclobber`: nenhuma saída salva é sobrescrita. Trocar `<label>` pelo rótulo da execução (o mesmo
  do arquivo de parâmetros), por exemplo `w1-20261002-a`. No zsh, sempre `"${VAR}"` com chaves.
- Um bloco que só pode rodar uma vez, quando repetido, imprime `JÁ FEITO: ...` e mostra os valores já gravados;
  não roda o passo de novo e não imprime `exit=`.
- Nenhum hash é copiado à mão: todo hash vem de uma saída salva, por `pick.py` ou por um comando do bloco.
- O binder nunca imprime o alvo SSH, o caminho da chave nem o do known-hosts, e nunca abre esses dois arquivos (só
  `lstat`). Não imprimir à mão (`cat`) `DISPATCH.BOUND.json`, o GO nem o payload final no canal: os três contêm o alvo.
- Recusa do binder: um objeto JSON (impresso em várias linhas) com `"status": "REFUSED"` e `"code"`, exit 2, nunca
  traceback. O campo `created_by_this_run` diz se a execução recusada já tinha criado algo; se tinha, parar, não
  mexer, não repetir no mesmo diretório, relatar.
- Nada sob o diretório vinculado é editado, movido, tem modo trocado ou é apagado para "fazer passar". Um byte
  mudado é outro hash e outra assinatura. Nenhum diretório é criado dentro dele (o binder recusa um conjunto com
  qualquer diretório além de `templates` e `.dispatch-root`: `BOUND_SET_HOLDS_A_DIRECTORY_THAT_IS_NOT_ITS_OWN`).
- Horas para o dono em BRT; no canal, UTC. Antes de todo pedido ao dono: banner no Mac e push no telefone.
- Não editar `bind_once.py` nem `ACCEPTED_SEALS.json` entre o prepare e o sign de uma execução: o hash dos dois está
  na folha que o dono assina, e o sign recusa (`BINDER_CHANGED_SINCE_PREPARE`). Um conjunto já assinado só é
  conferido (`check`, `status`, citação como evidência) por bytes do binder que ainda construam os mesmos documentos
  e a mesma pergunta: não mudar o texto das perguntas nem a construção entre o precheck real e o readback.

### Onde fica o diretório vinculado (decidir antes do bloco 1)

A raiz de uso único (`.dispatch-root`) entra no GO assinado com caminho, device e inode, e os cinco blobs entram na
configuração com o caminho do diretório em que foram vinculados.

- **Nunca rodar o dispatcher a partir de uma cópia.** O `check` e o `publish-proof` de uma cópia recusam
  (`BOUND_SET_RELOCATED_OR_CLAIM_ROOT_CHANGED`), mas o `dispatch_once.py` da cópia, enquanto o diretório original
  existir, lê os blobs e usa a raiz de uso único **nos caminhos originais**: prepara e reivindica lá, e o recibo cai
  lá. O uso único é mantido, mas o que foi consumido está no original, não na cópia.
- O `status` de uma cópia: se a própria cópia guarda uma tentativa terminada (cópia de arquivo, feita depois do
  resume), confere os bytes da cópia; senão lê a raiz **original** nomeada na folha, quando ela ainda existe com a
  identidade assinada (`claim_root_read: ORIGINAL_NAMED_ON_THE_SHEET`); se o original sumiu, responde
  `RELOCATED_COPY_STATE_NOT_KNOWN` e não afirma que nada foi consumido.
- **(A) assinatura e despacho na mesma sentada:** `OUT` no scratchpad (`${RUN}/bound`) e cópia para o diretório
  durável no bloco 11. É o padrão do bloco 1a.
- **(B) assinatura de véspera, ou qualquer intervalo de horas entre o sign e o resume:** criar `OUT` já no diretório
  durável (`OUT=${W}/once-<label>/bound` no `run.env`). `/private/tmp` é limpo de arquivos parados há 3 dias e some
  num reinício do Mac. O bloco 11 então só copia as saídas dos passos e confere.

## 1. Fatos fixos

| O quê | Valor |
|---|---|
| Binder | `S/bind/bind_once.py`; manifesto `S/bind/SHA256SUMS` (conferir no bloco 0) |
| Selos aceitos (`ACCEPTED_SEALS.json`) | W1PREFLIGHT01 rev 3 `108b74ca92c0ad32c37d462c7d4cea77074f874022e8e18b89d116f696783347`; HOSTOPS01 rev 3 `5609b334ea1b35932626ef7048a5958be16f4b3c769eafe73eb9d0d676e171c1`; HOSTOPS02 (seção 10; os selos enviados ao Codex em 02/10 21:12 BRT, `NOTE_FOR_CODEX_TIER0.md`, com a prova Linux verde 37080926250): catalog_init `1ccaf83dbc3e901d476efe92d877cbee678caf29d2103008a694c155ea09b0f5`, install_release `2705134655d7e580f389a7b32178e18b22d8ca75f2d5b206de3c90483fb84b82`, epoch_readback `b1a810fea1e695ba3ef25f7dc839136bbb0c9995f89eef777bc2f93215703c1f`, activate `91366f446d977fac1e0d0fb6d88c2fa8d98c02ef084b0d4098ebb0467a352bad`, todos com o núcleo congelado `73fb546b9758718924b73200b48b7c0582a156a60da200ff83f4ca66e9e5c9b1` (geração `4c24c5cfe4d6c70ce8aa57c61b070255dd67850be6697b8a0f58f95f6663d0d6`). Os selos substituídos (K2a `8b2bced3…`, K6a `3f0eea45…`, núcleo `c13ce685…`, cujo job Linux 37073034731 falhou dois testes) não são mais aceitos |
| Cópia durável do tier HOSTOPS02 | `W/fable-hostops02-tier0-20261002-r2` (todo arquivo com o hash selado; é a fonte `HOSTOPS02_SOURCE` da cópia selada, seção 10.1) |
| Família W1 | `S/w1preflight/candidate`, operação `GO_READONLY_W1PREFLIGHT_01`, datas UTC 2026-10-02..2026-10-10. Os bytes selados não limitam o comprimento da janela (aceitam o dia UTC inteiro); **o binder recusa janela do W1 maior que 3600 s** (`WINDOW_OVER_THE_READ_CAP`), no prepare e toda vez que o conjunto é aberto |
| Família HOSTOPS01 | `S/hostops01/candidate`; `GO_READONLY_HOSTOPS_PRECHECK_01` e `GO_READONLY_SUPERVISOR_READBACK_01` (datas 10-02..10-05, portão ≤ 3600 s); `GO_WRITE_SUPERVISOR_READER_PROVISION_01` e `GO_WRITE_UNITS_EXCLUSIVE_INSTALL_01` (datas 10-02..10-04, portão ≤ 900 s) |
| Referência de transporte | `DISPATCH.BOUND.json` de um conjunto **executado** (o `exit.json` dele prova uma tentativa única bem-sucedida daquela configuração). Padrão do `runbook_env.zsh`: o do HOSTFACTS01 em `W/hostfacts01-fable-20261002/bound/` (durável). O do POSTDEPLOY rev5 de hoje também serve, mas mora no scratchpad |
| Vínculo do servidor esperado | `226f6148fe3550a0b997a3693aad8c4571d961477bbaeb85a40ac1109a32e9d2` (o mesmo das execuções de 01/10 e 02/10) |
| Pin do comando esperado | `6719e5233041002cdf899dad8dd5f7ba4363a6a3ecca93486bf687a2b680dce2` (o que rodou em 02/10; o binder recusa outro: `COMMAND_PIN_NOT_THE_EXECUTED_ONE`) |
| Uma janela | inteira num dia UTC: nunca atravessa 21:00 BRT. Último início = fim − 80 s |
| Modelo de assinatura | Uma resposta literal `Assino` do dono por folha: `IND`, `EVE` e `PRE` (declarado em `signature_model`). Leitura em grade (`GRID`) e assinatura semanal (`WEEK`) não têm resposta própria do dono e **não estão implementadas**: o prepare recusa (`SIGNATURE_MODEL_NOT_IMPLEMENTED`), nos dois modos |

## 2. O arquivo de parâmetros

Um JSON por execução. Chaves comuns: `schema`, `operation`, `label`, `signature_model`, `not_before`, `not_after`
(UTC, segundos inteiros, `Z`); opcional `purpose_pt` (entra na pergunta ao dono como "Finalidade").
O alvo, a chave, o known-hosts, o vínculo do servidor e o pin do comando **não** entram aqui: vêm da referência de
transporte, lida pelo binder. O conjunto de nove datas do W1 vem de `DATES` da fonte selada e do membro `dates` do
template, nunca de um número de linha.

### W1 (exato)

```json
{
  "schema": "BIND_ONCE_PARAMETERS_V1",
  "operation": "GO_READONLY_W1PREFLIGHT_01",
  "label": "w1-20261002-a",
  "signature_model": "IND",
  "not_before": "2026-10-02T19:00:00Z",
  "not_after": "2026-10-02T20:00:00Z",
  "candidates": {"release_directories": [], "capacity_roots": []},
  "purpose_pt": "Primeira leitura W1 depois do deploy: reinício pendente, trava de manutenção, discos, redes e diretórios."
}
```

| Chave | De onde vem |
|---|---|
| `operation` | constante da família (CONTRACT.txt, linha 2) |
| `label` | escolha do operador; nomeia `DUDU_<LABEL>_AUTHORITY.json`, `DUDU_<LABEL>_GO.json` e o diretório da tentativa `<label>-once`. Um label por leitura. Tem de ser o `<label>` dos blocos (o bloco 1b confere) |
| `signature_model` | `IND` (resposta individual), `EVE` (de véspera) ou `PRE` (antecipada): nos três o dono responde `Assino` a esta folha. `GRID` e `WEEK` são recusados |
| `not_before`, `not_after` | a janela que o dono vai assinar: **no máximo 3600 s** no W1, num só dia UTC. O binder mostra o início e o fim em BRT na folha e na pergunta; o W1 exige a janela igual nos seis lugares, e o binder a escreve nos seis |
| `candidates` | vazios no W1 (decisão 2 do contrato). Para leituras posteriores: até 4 nomes de diretório de release e até 3 caminhos de árvore de capacidade, da folha de sábado. Os nomes entram no request; a folha e a pergunta mostram só as contagens |
| `purpose_pt` | texto livre do operador: **uma linha**, 20 a 1500 caracteres imprimíveis, sem a palavra de assinatura e sem sequência de 64 hex (`PARAMETERS_FREE_TEXT`). O mesmo vale para `owner_summary_pt` |

### HOSTOPS01 (núcleo): `plan`, `evidence` e, nas gravações, `review`

```json
{
  "schema": "BIND_ONCE_PARAMETERS_V1",
  "operation": "GO_READONLY_HOSTOPS_PRECHECK_01",
  "label": "s1-20261003-a",
  "signature_model": "IND",
  "not_before": "2026-10-03T12:10:00Z",
  "not_after": "2026-10-03T13:00:00Z",
  "plan": {"groups": ["SUPERVISOR", "JOURNAL_LEAF", "READER", "CAPACITY"], "journal_placement": "A",
           "data_volume_path": "<da folha>", "journal_leaf": "journal", "existing_journal_leaves": [],
           "capacity": {"root_path": "<da folha>", "receipt_directory_path": "<da folha>"},
           "unit_names": ["c3po-massive.service", "c3po-massive.timer"], "image_reference": "c3po/backend:production"},
  "evidence": []
}
```

- `plan` leva exatamente as chaves próprias da operação (`PLAN_KEYS` da fonte); as comuns (schema, status, phase,
  scope, window, host binding, max_seconds) são do binder. Chave a mais ou a menos: `PLAN_KEYS_MISMATCH`.
- `evidence`: lista de recibos citados. **Num pedido REAL cada item é
  `{"role", "operation", "bound": "<diretório vinculado da execução que gerou o recibo>"}`**: o `OUT` daquela
  execução ou a cópia dele no diretório durável. O binder confere o conjunto como o `status` confere (assinado pelo
  dono, modo REAL; `exit.json` vincula a config, o request, o GO e a saída guardada; stderr vazio; recibo com esquema,
  vínculos e selo certos) e lê o recibo de lá. Arquivo solto (`"receipt_file"`) só vale em ensaio
  (`EVIDENCE_OF_A_REAL_REQUEST_MUST_BE_A_BOUND_SET`). Nunca se digita hash de recibo: o que entra no request é o
  selo (`metadata_sha256`) recalculado.
- O que o binder exige de todo recibo citado, antes de pedir a assinatura:
  - a operação dele é a citada e existe **nesta família selada** (`EVIDENCE_RECEIPT_OPERATION`,
    `EVIDENCE_SET_OF_ANOTHER_OPERATION`, `EVIDENCE_OPERATION_NOT_IN_THIS_FAMILY`), o esquema é o `RECEIPT_SCHEMA` da
    fonte dessa operação (`EVIDENCE_RECEIPT_SCHEMA`) e o `payload_sha256` dele é o hash dessa fonte selada
    (`EVIDENCE_RECEIPT_OF_OTHER_BYTES`). O recibo do HOSTFACTS01 não pode ser citado: nenhuma linha dele é assinada por uma
    gravação (contrato, seção 11);
  - o vínculo do servidor dele é o do conjunto que está sendo vinculado (`EVIDENCE_RECEIPT_OF_ANOTHER_HOST`): um
    recibo de ensaio ou de fixture não entra num pedido real, nem o contrário
    (`EVIDENCE_SET_OF_THE_OTHER_MODE`, `EVIDENCE_SET_OF_ANOTHER_SEAL`);
  - o resultado é o de sucesso da operação (precheck: `PRECHECK_ALL_OBSERVED`). Um recibo parcial só entra com
    `"accept_not_complete": true` no item (`EVIDENCE_RECEIPT_NOT_COMPLETE`), e então a folha e a pergunta ao dono
    dizem `NÃO COMPLETO, aceito por parâmetro`.
- Valor copiado de recibo: em qualquer ponto do `plan`, `{"$from": {"evidence": "PRECHECK", "pointer": "/items/chains/ETC/rows"}}`
  é trocado pelo valor daquele ponto do recibo citado. A folha lista cada cópia (`plan_values_copied_from_receipts`).
- **Digitado ou copiado, o valor tem de ser o do recibo** (seção 11 do contrato; tabela `PLAN_SOURCES` do binder;
  a folha lista em `plan_values_equal_to_the_cited_receipts`). Cada membro abaixo, quando não é nulo, exige
  exatamente **um** recibo citado daquela operação (`PLAN_VALUE_WITHOUT_ITS_SINGLE_CITED_RECEIPT`) e tem de ser igual
  ao valor dele (`PLAN_VALUE_NOT_THE_ONE_OF_THE_CITED_RECEIPT`); prechecks citados de boots diferentes são recusados
  (`CITED_PRECHECKS_OF_DIFFERENT_BOOTS`):

  | Operação | Membro do `plan` | Recibo | Ponteiro |
  |---|---|---|---|
  | provision | `chains.<NOME>` | precheck | `/items/chains/<NOME>/rows` |
  | provision | `evidence_boot_id_sha256` | precheck | `/items/boot/boot_id_sha256` |
  | provision | `retention_tag.image_id` | precheck | `/items/image/id` |
  | install | `unit_directory` | precheck | `/items/chains/UNIT_DIRECTORY/rows` |
  | install | `evidence_boot_id_sha256` | precheck | `/items/boot/boot_id_sha256` |
  | readback | `provision.receipt_sha256` | provision | `/metadata_sha256` |
  | readback | `install.receipt_sha256`, `install.outcome` | install | `/metadata_sha256`, `/outcome` |
  | readback | `evidence_boot_id_sha256` | precheck | `/items/boot/boot_id_sha256` |
  | readback | `unit_directory` | precheck | `/items/chains/UNIT_DIRECTORY/rows` |

  Os outros valores que a seção 11 tira de recibos (layout, linhas do volume de dados, identidades das unidades) não
  estão nessa tabela: copiá-los por ponteiro e conferi-los em `EFFECTS.json`.
- **O catálogo do readback (B3) e o A9.** O readback e o install_units podem citar o conjunto do A9 (K2a, operação 4b)
  pela família dele: `{"role": "A9", "operation": "GO_WRITE_HOSTOPS02_CATALOG_INIT_01", "bound": "<conjunto do A9>",
  "family": "<HOSTOPS02_COPY>/catalog_init"}` (só essa operação aceita `family` num pedido do HOSTOPS01). O recibo citado
  tem de ser o único do K2a, completo, de modo REAL, `CATALOG_READY_VERIFIED`, do mesmo boot do pedido (o do ensaio A6,
  ou um parcial, é recusado: `CATALOG_4B_RECEIPT_NOT_THE_COMPLETE_REAL_ONE`). No readback, citado o A9, o catálogo vem
  dele e o `image_revision` é comparado com a leitura da etiqueta pelo precheck citado:

  | Membro do `plan` | Recibo | Ponteiro |
  |---|---|---|
  | `catalog.receipt_sha256` | K2a (A9) | `/metadata_sha256` |
  | `catalog.device`, `catalog.inode` | K2a (A9) | `/script_line/device`, `/script_line/inode` |
  | `image_revision` | precheck | `/items/image/revision_label` |

  com `catalog.expected` `INITIALISED` (`CATALOG_EXPECTATION_NOT_THE_CITED_4B`). Um readback REAL que espera o catálogo
  `INITIALISED` sem citar o A9 é recusado (`CATALOG_WITHOUT_THE_CITED_4B_RECEIPT`). O B1 (install_units) cita o A9 para
  registrar a dependência do plano (A9 `KNOWN_COMPLETE` antes do B1; a A1, E3, pede "catálogo real completo"): o binder
  não a exige, a disciplina é do runbook (10.2). Um pedido que não cita o A9 é vinculado exatamente como antes.
- `journal_mount_point` do readback ← `/effects/journal/mount_point_by_device_change` do recibo do provision.
- Regras da seção 12 do contrato que o binder aplica **antes de pedir a assinatura** (a folha as lista em
  `contract_section_12_checks`):
  - passo 3: cada unidade do `plan` (`units[]` do install; `service` e `timer` do readback) é renderizada de novo
    pelo laço de referência do repositório, escrito no binder à parte do renderizador da família, e comparada com
    `rendered_sha256` e `rendered_bytes` assinados (`UNIT_RENDER_NOT_THE_REFERENCE_LOOP`);
  - passo 2b, readback em modo GATE: o piso (`free_space_floor_bytes`) é comparado com
    `items.chains.<cadeia>.bytes_available_to_non_root_f_bavail` do recibo do precheck, sendo `<cadeia>` a que
    `effects.journal.filesystem_named_by_chain` do recibo do provision nomeia; abaixo do piso o binder recusa com
    `FREE_SPACE_BELOW_FLOOR_DO_NOT_ASK_FOR_THE_SIGNATURE` (o readback sairia com 2 e gastaria o GO). Por isso um
    readback GATE cita, em `evidence`, exatamente um recibo do precheck e um do provision
    (`READBACK_FLOOR_EVIDENCE_MISSING`), e o `journal_mount_point` tem de ser o dos efeitos do provision
    (`READBACK_MOUNT_POINT_NOT_THE_PROVISION_ONE`). Os números ficam no request e nos recibos, não na folha.
- **Gravações (`writes_allowed`): `review` é obrigatório** (`REVIEW_OR_WAIVER_MISSING_FOR_A_WRITE`). A decisão do
  dono sobre gravações faz da revisão do Codex uma precondição de cada gravação, salvo dispensa dele para aquela
  operação. O pedido diz qual das duas vale e aponta o documento que a registra:
  `"review": {"kind": "CODEX_REVIEWED", "document_file": "<arquivo com o parecer>"}` ou
  `{"kind": "OWNER_WAIVED", "document_file": "<arquivo da decisão de dispensa>"}`. O binder calcula o sha256 do
  arquivo (nunca digitado), põe na folha e a pergunta ao dono o cita: "Revisão prévia do Codex sobre estes bytes:
  FEITA ..." ou "... DISPENSADA por decisão sua ...". No HOSTOPS01 o binder não lê o conteúdo do documento: conferir
  que ele diz o que o `kind` afirma é do operador. No HOSTOPS02 o binder exige que o documento nomeie os bytes (seção
  2, HOSTOPS02).
- Janela do dono mais longa que o portão (só no núcleo): `gate_not_before` e `gate_not_after` dão a janela do GO e do
  despacho, dentro de `not_before`..`not_after`. A pergunta ao dono mostra as duas. Sem elas, uma janela só, que
  precisa caber no teto da operação (900 s para gravação, 3600 s para leitura).
- O binder calcula `effects_of(plan)` com a fonte da família e grava `EFFECTS.json`: é isso que o dono e o GO
  assinam. Numa gravação a pergunta ao dono **lista cada caminho criado, com o modo** e se é esperado ausente ou
  já existente, e a etiqueta de imagem. **Ler `EFFECTS.json` antes de pedir a assinatura.**
- Operação nova (hostops02) sem texto em `OWNER_TEXT_PT`: trazer `owner_summary_pt` no arquivo de parâmetros, e
  acrescentar o selo novo em `ACCEPTED_SEALS.json` antes do prepare. Uma gravação cujos efeitos o binder não sabe
  listar é recusada (`EFFECTS_NOT_LISTABLE_FOR_THE_OWNER`).

### HOSTOPS02 (K2a, K10, K11, K6a): o que muda no arquivo de parâmetros

Comum às quatro operações (além das chaves do núcleo acima: `plan`, `evidence` e `review`, que nas quatro é obrigatório, o K11
incluído: ele inicia um contêiner e a A1, 4.2, C4, o condiciona a "programa revisto"):

- **`review`**: `{"kind": "CODEX_REVIEWED", "document_file": "<parecer do Codex>"}`. O binder exige que o documento traga, como
  texto, o selo da operação (`SHA256SUMS`) e o programa (a fonte montada ou o payload final não vinculado, os dois do
  `build/ASSEMBLY.json`): um parecer de outros bytes, do build anterior a um reparo ou de um selo substituído é recusado
  (`REVIEW_DOCUMENT_DOES_NOT_NAME_THESE_BYTES`). O veredito escrito no documento é a Fable que lê. Dispensa só como ato do
  próprio dono (A1, seção 8): `{"kind": "OWNER_WAIVED", "document_file": "<registro OWNER_DECISION_V1>"}`, um registro
  feito antes do pedido, com a resposta literal dele, o canal e a hora, que nomeie a operação, o selo e o programa
  (`OWNER_WAIVER_NOT_A_SIGNED_RECORD_FOR_THESE_BYTES`); a pergunta diz "registrada à parte" e "esta assinatura não é a
  dispensa". Nas gravações (K2a, K10, K6a) com `CODEX_REVIEWED` a folha ganha também o portão de envio
  `CODEX_REVIEW_OF_THE_BOUND_SET` (seção 10.4).

- **`--family`** é o diretório da operação **dentro da cópia selada** `${HOSTOPS02_COPY}` (seção 10.1); o núcleo fica ao
  lado, como `../core`. O binder confere o `CORE_SHA256SUMS` (o selo do núcleo aceito), a geração (`assemble.py`), roda
  a conferência do próprio núcleo (`assemble.py --check <operação>`: `BUILD_EQUAL`) e o `ASSEMBLY.json` contra os bytes
  que vai vincular. `work/` e `review-*/` de um diretório de trabalho ficam fora do selo e são só nomeados na folha.
- **Evidência de outra família:** cada item que cita uma operação que não é desta operação leva `"family": "<diretório da
  família selada que a contém>"` (HOSTOPS01: `${HOSTOPS_FAMILY}`; W1: `${W1_FAMILY}`; uma operação HOSTOPS02 irmã:
  `${HOSTOPS02_COPY}/<diretório>`). O selo dessa família tem de estar aceito; o recibo é julgado pela fonte selada dela
  (esquema, `payload_sha256`, vínculo do servidor, selo). Recibo do W1 (sem `operation` nem `outcome`): completo quando o
  status é o de `KNOWN_COMPLETE`. Recibo do K2a ou do K11: completo quando o resultado é o de sucesso **do modo assinado**
  nele (K2a REHEARSAL: `REHEARSAL_CATALOG_READY_VERIFIED`; K11 PRE FULL: `EPOCH_DRY_RUN_PRE_ALL_OBSERVED_ALL_EXPECTATIONS_MET`).
  Num pedido REAL, como antes, todo item é `"bound"` (conjunto vinculado e terminado), nunca `"receipt_file"`.
- **Valores por comando, nunca digitados** — além de `{"$from": {"evidence": ROLE, "pointer": "/..."}}`:
  - `{"$input": NOME, "as": "b64" | "sha256" | "bytes"}`: o conteúdo (base64), o hash ou o tamanho do arquivo de entrada
    `NOME`; `{"$input": NOME, "as": "member", "member": CHAVE}`: um membro de topo do JSON desse arquivo;
  - `{"$source": CONSTANTE}`: uma constante da fonte selada da operação (`CATALOG_SCRIPT_SHA256`, `EPOCH_COMPILED`, `RELEASE_PATH`);
  - `{"$ledger_row": {"evidence": ROLE, "path": P, "key": K}}`: a linha de seis chaves do diretório `P` que o recibo de
    provisão citado criou (`CREATED_DURABLE`, chave `K` do ledger);
  - `{"$concat": [ITEM, ...]}`: listas emendadas (linhas de "/" até a folha).
- **`inputs`**: `{"release": "<arquivo>", "policy": "<arquivo>", "override": "<arquivo>"}`, conforme a operação (K10:
  `release`; K11: `release`, `policy`, `override` no PRE com render; K6a: `policy`, `release`, `override`). O binder lê cada arquivo
  (no máximo 65536 bytes), calcula sha256 e tamanho, põe na folha e a pergunta ao dono mostra os dois. Todo membro que
  carrega bytes, hash ou tamanho de um arquivo de entrada tem de vir dele por `$input`
  (`PLAN_MEMBER_NOT_FROM_ITS_INPUT_FILE`), e todo arquivo dado tem de ser usado (`BIND_INPUT_NOT_USED`).
- **`spare_of`** (K2a, K10, K6a): `{"bound": "<diretório do principal, já assinado>"}`. A reserva tem o mesmo programa,
  os mesmos efeitos (`EFFECTS.json` byte a byte) e uma janela que começa depois do fim do portão do principal; o principal
  não pode ter sido preparado pelo dispatcher. Ver 10.5.
- **`linux_job`** (K2a, K11, K6a): `{"kind": "LINUX_JOB_PASSED", "document_file": "<registro>"}`, sem dispensa (nenhum dos
  dois contratos a admite): obrigatório em REAL no K2a e no K6a. O registro tem de trazer, como texto, o selo da operação,
  o programa (fonte ou payload final não vinculado) e o selo do núcleo (`LINUX_JOB_RECORD_NOT_OF_THESE_BYTES`): o
  `JOB.log` da execução 37080926250 (`W/fable-hostops02-tier0-20261002-r2/linux-root-proof-37080926250/JOB.log`) traz os
  quatro selos, as quatro fontes, os quatro payloads finais e o núcleo. **`linux_proof`** (só K10, obrigatório em REAL, sem dispensa):
  `{"root_junit": "<TESTS.install_release.linux-root.xml>", "user_junit": "<...linux-user.xml>"}`, julgados pela ferramenta
  selada `binding/linux_proof.py` (`LINUX_PROOF_ACCEPTED`).
- **`release_tree`** (só K2a, obrigatório em REAL): uma árvore da release `dd4ec4bb` (por exemplo `git archive dd4ec4bb
  c3po/backend/app c3po/deployment/massive-supervisor | tar -x -C <dir>`): o script assinado tem de ser o do README (entre
  os marcadores `catalog-init-script`) e, em REAL, a época a linha `EPOCH` do `r2d2_v2_epoch_assembler.py`.
- **`rehearsal`** (só K2a, só com `plan.mode` REAL): `{"bound": "<conjunto do A6, terminado>"}`. Opcional: quando o A6 já
  rodou, o recibo dele é conferido no preparo (os mesmos bytes, boot, imagem, script e caminho; pasta do cliente docker vazia;
  `REHEARSAL_RECEIPT_NOT_THE_ONE_A9_NEEDS`) e a pergunta mostra o resultado; sem ele, a pergunta diz que o contrato (seção 5,
  passo 1) põe o ensaio antes da assinatura e que aqui ele é portão do envio. Nunca entra em `evidence`.
- **`siblings_tests`** (só K11): `{"document_file": "<registro>"}`: o registro de uma execução da suíte do K11 ao lado das três
  irmãs com os selos aceitos (contrato K11, seção 8, passo 3), que nomeie como texto o selo do K11 e os três selos aceitos das
  irmãs (o `JOB.log` de 37080926250 serve). Obrigatório em REAL enquanto o `SIBLINGS.txt` selado nomear selos anteriores
  (hoje: catalog_init e activate) (`SIBLINGS_TESTS_NOT_RERUN_FOR_THE_ACCEPTED_SEALS`).
- **`host_evidence_reason_pt`** (só K10): uma linha, quando só um recibo de provisão é citado (o contrato K10, seção 5 (j),
  nomeia A3 e A4); a pergunta mostra o motivo (`RELEASE_HOST_EVIDENCE_A4_NOT_CITED_AND_NO_REASON`).
- `owner_summary_pt` não existe para as quatro: o texto da pergunta é fixo por operação.

Os papéis (`role`) abaixo são os que os modelos usam; os ponteiros `$from` dependem deles.

#### A6 — K2a, ensaio do catálogo (operação em modo REHEARSAL, conjunto REAL)

```json
{
  "schema": "BIND_ONCE_PARAMETERS_V1",
  "operation": "GO_WRITE_HOSTOPS02_CATALOG_INIT_01",
  "label": "a6-20261003-a",
  "signature_model": "IND",
  "not_before": "2026-10-03T19:45:00Z", "not_after": "2026-10-03T23:30:00Z",
  "gate_not_before": "2026-10-03T20:00:00Z", "gate_not_after": "2026-10-03T20:15:00Z",
  "purpose_pt": "Ensaio da inicialização do catálogo em pastas descartáveis de /var/lib, com os mesmos bytes do A9.",
  "plan": {
    "mode": "REHEARSAL",
    "journal_chain": {"$from": {"evidence": "PRECHECK", "pointer": "/items/chains/VAR_LIB/rows"}},
    "throwaway_name": "c3po-bar-rehearsal-20261003a",
    "reference_chain": {"$concat": [{"$from": {"evidence": "PRECHECK", "pointer": "/items/chains/VAR_LIB/rows"}},
                                    [{"$ledger_row": {"evidence": "PROVISION", "path": "/var/lib/c3po-bar", "key": "SUP_STATE_PARENT"}},
                                     {"$ledger_row": {"evidence": "PROVISION", "path": "/var/lib/c3po-bar/journal", "key": "SUP_JOURNAL"}}]]},
    "container_journal_root": "/c3po-bar-journal",
    "docker_config_chain": {"$concat": [{"$from": {"evidence": "PRECHECK", "pointer": "/items/chains/ETC/rows"}},
                                        [{"$ledger_row": {"evidence": "PROVISION", "path": "/etc/c3po-bar", "key": "SUP_CONFIG"}},
                                         {"$ledger_row": {"evidence": "PROVISION", "path": "/etc/c3po-bar/docker-cli", "key": "SUP_DOCKER_CLI"}}]]},
    "image_id": {"$from": {"evidence": "PRECHECK", "pointer": "/items/image/id"}},
    "image_revision": {"$from": {"evidence": "PRECHECK", "pointer": "/items/image/revision_label"}},
    "epoch": "R2D2-V2-DIAG-K2A-REHEARSAL-20261003",
    "script_sha256": {"$source": "CATALOG_SCRIPT_SHA256"},
    "evidence_boot_id_sha256": {"$from": {"evidence": "PRECHECK", "pointer": "/items/boot/boot_id_sha256"}}
  },
  "evidence": [
    {"role": "PRECHECK", "operation": "GO_READONLY_HOSTOPS_PRECHECK_01", "bound": "<conjunto do S1>", "family": "<HOSTOPS_FAMILY>"},
    {"role": "PROVISION", "operation": "GO_WRITE_SUPERVISOR_READER_PROVISION_01", "bound": "<conjunto do A3>", "family": "<HOSTOPS_FAMILY>"}
  ],
  "review": {"kind": "CODEX_REVIEWED", "document_file": "<parecer do Codex sobre estes bytes>"},
  "linux_job": {"kind": "LINUX_JOB_PASSED", "document_file": "<registro do job Linux do núcleo e do K2a>"},
  "release_tree": "<árvore da release dd4ec4bb>"
}
```

| Chave | De onde vem |
|---|---|
| `not_before`/`not_after` | a faixa da linha C1 da A1 (sáb 16:45–20:30 BRT = 19:45–23:30Z), um dia UTC; `gate_*`: a janela curta (≤ 900 s), fixada pela Fable (A1, seção 5) |
| `signature_model` | `IND` (A1 4.2: individual) |
| `plan.mode` | `REHEARSAL` (o ensaio); `throwaway_name`: `c3po-bar-rehearsal-<rótulo>`, decidido na folha (um nome novo por ensaio) |
| `plan.journal_chain` | no ensaio, a cadeia inteira de `/var/lib`: `VAR_LIB` do precheck S1 (por ponteiro) |
| `plan.reference_chain` | a pasta real do journal, só lida: `VAR_LIB` do S1 + as linhas `SUP_STATE_PARENT` e `SUP_JOURNAL` do ledger do A3 (`CREATED_DURABLE`) |
| `plan.docker_config_chain` | `ETC` do S1 + as linhas `SUP_CONFIG` e `SUP_DOCKER_CLI` do ledger do A3 |
| `plan.container_journal_root` | `/c3po-bar-journal` (README, colocação A; decidido na folha) |
| `plan.image_id`, `plan.image_revision` | `items.image.id` e `items.image.revision_label` do S1 (lidos depois do deploy): a revisão é conferida com o recibo, não digitada |
| `plan.epoch` | ensaio: uma época `R2D2-V2-DIAG-...` decidida na folha |
| `plan.script_sha256` | a constante da fonte (`$source`); com `release_tree`, conferida com o README da release |
| `plan.evidence_boot_id_sha256` | `items.boot.boot_id_sha256` do S1 |
| `evidence` | S1 (precheck) e A3 (provisão) do HOSTOPS01, os conjuntos vinculados e terminados, do mesmo boot, completos |
| `review`, `linux_job`, `release_tree` | parecer do Codex (com o selo e o programa no texto); registro do job Linux (com os selos e o programa no texto; sem dispensa); árvore da release (`release_tree` e `linux_job` são obrigatórios em REAL; com `release_tree` o binder confere também o comando docker com as linhas 336–339 do README, palavra por palavra) |

#### A9 — K2a, catálogo real (operação em modo REAL) e A9' (reserva de domingo)

Igual ao A6, com: `"label": "a9-20261003-a"`; faixa sáb 17:15–20:30 BRT (20:15–23:30Z) e portão curto; e no `plan`:

```json
    "mode": "REAL",
    "journal_chain": {"$concat": [{"$from": {"evidence": "PRECHECK", "pointer": "/items/chains/VAR_LIB/rows"}},
                                  [{"$ledger_row": {"evidence": "PROVISION", "path": "/var/lib/c3po-bar", "key": "SUP_STATE_PARENT"}},
                                   {"$ledger_row": {"evidence": "PROVISION", "path": "/var/lib/c3po-bar/journal", "key": "SUP_JOURNAL"}}]]},
    "throwaway_name": null,
    "reference_chain": null,
    "epoch": {"$source": "EPOCH_COMPILED"},
```

Se o A6 já terminou quando o A9 é preparado: `"rehearsal": {"bound": "<conjunto do A6>"}` (a pergunta mostra o recibo dele).
A9' (reserva, dom 04/10 08:30–19:00 BRT = 11:30–22:00Z): os mesmos `plan` e `evidence`, outro `label` (`a9r-20261004-a`), a
sua faixa e o seu portão, e `"spare_of": {"bound": "<conjunto do A9, já assinado>"}` (uma reserva só por principal). Antes do
envio do A9 (e do A9'), `check --gates` com `{"rehearsal": {"bound": "<conjunto do A6>", "family": "<K2a>"}, "grid_read":
{"bound": "<leitura W1 do mesmo boot, minutos antes>", "family": "<W1_FAMILY>"}, "codex_review": {...}}` (10.4). Num C1 (pasta
nova depois de um 4b que falhou), a evidência cita também a provisão C1, e as duas linhas do journal vêm do ledger que tem
aquele caminho.

#### K11 PRE (M2p) — releitura da época, modo PRE, perfil FULL

```json
{
  "schema": "BIND_ONCE_PARAMETERS_V1",
  "operation": "GO_READONLY_HOSTOPS02_EPOCH_READBACK_01",
  "label": "m2p-20261004-a",
  "signature_model": "IND",
  "not_before": "2026-10-04T15:15:00Z", "not_after": "2026-10-04T16:15:00Z",
  "inputs": {"release": "<release.CERTIFIED.json aprovada>", "policy": "<policy.json aprovada>", "override": "<override do K6a>"},
  "plan": {
    "mode": "PRE", "dry_run": "FULL",
    "evidence_boot_id_sha256": {"$from": {"evidence": "PRECHECK", "pointer": "/items/boot/boot_id_sha256"}},
    "revision": {"$input": "release", "as": "member", "member": "code_revision"},
    "package_sha256": {"$input": "release", "as": "member", "member": "implementation_package_sha"},
    "image": {"reference": "c3po/backend:production", "image_id": {"$from": {"evidence": "PRECHECK", "pointer": "/items/image/id"}}},
    "worker": {"container": "c3po-r2d2-worker-1", "environment": true, "data_source": "/mnt/day-d-data", "data_target": "/app/day-d-data"},
    "release": {"sha256": {"$input": "release", "as": "sha256"}, "bytes": {"$input": "release", "as": "bytes"}, "content_b64": {"$input": "release", "as": "b64"},
                "parent": {"path": "/mnt/day-d-data", "rows": {"$from": {"evidence": "PRECHECK", "pointer": "/items/chains/DATA_VOLUME/rows"}}, "open_root": "/mnt/day-d-data"},
                "directory_name": "r2d2-v2-release-20261005", "file_name": "release.CERTIFIED.json", "container_target": null, "directory_entries": null},
    "live": {"parent": {"path": "/mnt/day-d-data/r2d2-v2-live", "rows": null, "open_root": "/mnt/day-d-data"}, "directory_name": "2026-10-05"},
    "policy": {"sha256": {"$input": "policy", "as": "sha256"}, "bytes": {"$input": "policy", "as": "bytes"}, "content_b64": {"$input": "policy", "as": "b64"},
               "valid_at": ["<início do portão do M3>", "<início do portão do M3'>", "2026-10-05T13:30:00+00:00", "2026-10-09T19:59:59+00:00"]},
    "render": {"project": "c3po", "env_file": "<deploy>/.env", "files": ["<deploy>/c3po/compose.yml"],
               "override_b64": {"$input": "override", "as": "b64"}, "override_sha256": {"$input": "override", "as": "sha256"},
               "override_bytes": {"$input": "override", "as": "bytes"}},
    "limits": {"render_ms": 3000, "quick_ms": 1500, "data_volume_free_bytes": 1048576, "data_volume_free_inodes": 8},
    "deploy": {"tree": {"path": "<deploy>", "rows": null, "open_root": "<deploy>"},
               "lock_directory": {"path": "<deploy>/runtime/security", "rows": null, "open_root": "<deploy>"},
               "lock_name": "deployment.lock", "version_name": ".deploy-version"},
    "units": [], "journal": null, "docker_config": null, "rows_in_receipt": true,
    "bind_probe": {"directory": {"path": "<uma pasta privada com um arquivo 0600, de um recibo deste boot>", "rows": null, "open_root": "/mnt/day-d-data"},
                   "file_name": "<o arquivo>", "container_target": "/c3po-bind-probe"}
  },
  "evidence": [{"role": "PRECHECK", "operation": "GO_READONLY_HOSTOPS_PRECHECK_01", "bound": "<conjunto do S1>", "family": "<HOSTOPS_FAMILY>"}],
  "review": {"kind": "CODEX_REVIEWED", "document_file": "<parecer do Codex sobre estes bytes>"},
  "siblings_tests": {"document_file": "<JOB.log da execução 37080926250>"},
  "linux_job": {"kind": "LINUX_JOB_PASSED", "document_file": "<JOB.log da execução 37080926250>"}
}
```

| Chave | De onde vem |
|---|---|
| janela | a faixa da linha C4 da A1 (dom 12:15–13:15 BRT), ≤ 3600 s, fora dos minutos :05–:07, :10–:25, :35–:37 do envio |
| `revision`, `package_sha256` | da release (por `$input ... member`); a revisão é conferida com a etiqueta da imagem que o S1 leu |
| `image.image_id` | o S1 (`items.image.id`); `image.reference`: `c3po/backend:production` |
| `worker` | o trabalhador e o bind do volume de dados como a leitura pós-deploy os leu (`c3po/compose.yml:165`) |
| `release.*` | bytes, hash e tamanho do arquivo de entrada; `parent.rows` do S1 (`DATA_VOLUME`); nome da pasta e do arquivo: as constantes do K10 (o binder confere com a fonte selada do K10 ao lado) |
| `live` | a pasta-mãe que o K6a vai usar (`rows` nulo no PRE: só observada; o K6a copia do recibo deste PRE) |
| `policy.valid_at` | os inícios dos portões do M3 e do M3', a primeira abertura e um segundo antes do último fechamento (o K6a confere que o início do seu portão está aqui) |
| `render` | o mesmo projeto e os mesmos arquivos que o K6a vai usar; o override pelo arquivo de entrada: os bytes que o K6a escreve (`json.dumps` com `sort_keys`; o K6a compara o hash com o deste recibo) |
| `limits` | 3000 e 1500 ms; `data_volume_free_bytes`/`inodes`: os pisos do K10 e do K6a (o binder confere com as fontes irmãs) |
| `deploy`, `bind_probe` | `<deploy>`: a árvore do deploy da leitura pós-deploy; linhas nulas (observadas) ou de um recibo deste boot que as tenha |
| `evidence` | o S1 (ou um recibo de leitura deste boot); o binder exige um recibo que diga o boot, e as linhas assinadas iguais às de um recibo citado. Citando também uma leitura W1 do mesmo boot (`"family": "<W1_FAMILY>"`), o binder confere com ela o trabalhador (nome, imagem pelo ID e pela referência, montagem `data_source` em `data_target`): `WORKER_OR_IMAGE_NOT_THE_ONES_OF_THE_CITED_READ` |
| `review`, `siblings_tests`, `linux_job` | o parecer do Codex (obrigatório); o registro da suíte do K11 ao lado das irmãs aceitas (obrigatório em REAL enquanto o `SIBLINGS.txt` nomear selos anteriores); o job Linux (opcional) |

#### M1 — K10, instalação da release (e M1', a reserva)

```json
{
  "schema": "BIND_ONCE_PARAMETERS_V1",
  "operation": "GO_WRITE_HOSTOPS02_INSTALL_RELEASE_01",
  "label": "m1-20261005-a",
  "signature_model": "PRE",
  "not_before": "2026-10-05T08:26:00Z", "not_after": "2026-10-05T08:41:00Z",
  "inputs": {"release": "<release.CERTIFIED.json aprovada, a mesma do M2p>"},
  "plan": {
    "parent": {"$from": {"evidence": "S1_PRECHECK", "pointer": "/items/chains/DATA_VOLUME/rows"}},
    "evidence_boot_id_sha256": {"$from": {"evidence": "S1_PRECHECK", "pointer": "/items/boot/boot_id_sha256"}},
    "release": {"path": {"$source": "RELEASE_PATH"}, "content_b64": {"$input": "release", "as": "b64"},
                "sha256": {"$input": "release", "as": "sha256"}, "bytes": {"$input": "release", "as": "bytes"}}
  },
  "evidence": [
    {"role": "S1_PRECHECK", "operation": "GO_READONLY_HOSTOPS_PRECHECK_01", "bound": "<conjunto do S1>", "family": "<HOSTOPS_FAMILY>"},
    {"role": "A3_PROVISION", "operation": "GO_WRITE_SUPERVISOR_READER_PROVISION_01", "bound": "<conjunto do A3>", "family": "<HOSTOPS_FAMILY>"},
    {"role": "B1_INSTALL", "operation": "GO_WRITE_UNITS_EXCLUSIVE_INSTALL_01", "bound": "<conjunto do B1>", "family": "<HOSTOPS_FAMILY>"},
    {"role": "SUNDAY_W1", "operation": "GO_READONLY_W1PREFLIGHT_01", "bound": "<leitura W1 de domingo, nomeando r2d2-v2-release-20261005>", "family": "<W1_FAMILY>"},
    {"role": "M2P", "operation": "GO_READONLY_HOSTOPS02_EPOCH_READBACK_01", "bound": "<conjunto do M2p>", "family": "<HOSTOPS02_COPY>/epoch_readback"},
    {"role": "A4_PROVISION", "operation": "GO_WRITE_SUPERVISOR_READER_PROVISION_01", "bound": "<conjunto do A4>", "family": "<HOSTOPS_FAMILY>"}
  ],
  "review": {"kind": "CODEX_REVIEWED", "document_file": "<parecer do Codex sobre estes bytes>"},
  "linux_proof": {"root_junit": "<TESTS.install_release.linux-root.xml>", "user_junit": "<TESTS.install_release.linux-user.xml>"}
}
```

| Chave | De onde vem |
|---|---|
| janela | M1 05:26–05:41 BRT (08:26–08:41Z); M1' 05:42–05:57 (08:42–08:57Z), só 2026-10-05, a partir de 04:00Z |
| `signature_model` | `PRE` (contra-assinatura de domingo) |
| `plan.parent`, `plan.evidence_boot_id_sha256` | o S1 (cadeia `DATA_VOLUME`, boot): seção 5 do contrato; comparados por comando com a leitura de domingo pela ferramenta `predispatch.py` |
| `plan.release` | o arquivo de entrada, julgado pela ferramenta selada `binding/release_fields.py` com as três expectativas tiradas do recibo do M2p (`effects.release.sha256`, `effects.revision`, `effects.package_sha256`) e do `DEPLOYED` dela; `path` é a constante da fonte |
| `evidence` | S1; A3, A4 e B1 (evidência (j) das chamadas de criação; um que não esteja completo aparece na pergunta, com o texto do contrato; sem o A4, `host_evidence_reason_pt` diz por quê); a leitura W1 de domingo (conjunto vinculado: a ferramenta lê request, recibo e `exit.json`); o M2p completo, perfil FULL, do mesmo boot |
| `linux_proof` | os dois junit do job Linux (`sh linux_root/run.sh ../install_release` num runner descartável): obrigatório em REAL |
| M1' | os mesmos `plan`, `evidence`, `inputs`, `review`, `linux_proof`; outro `label` (`m1r-20261005-a`), a sua janela e `"spare_of": {"bound": "<conjunto do M1, já assinado>"}` |

No prepare o binder roda o portão de domingo (`predispatch.py --step prepare --role primary` sobre a leitura W1 citada):
só `M0_IS_OF_THE_SAME_DAY_AND_NOT_OLDER_THAN_AN_HOUR` pode falhar (num prepare do próprio dia, nenhuma).

#### K11 POST (M2) — releitura da primeira sessão

Igual ao M2p (com `review` e `siblings_tests`), com: `"label": "m2-20261005-a"`; janela 05:38–06:25 BRT (08:38–09:25Z): começa
depois do recibo do M1 e termina antes do portão do M3' (que começa 06:26), para servir também depois de um M1' (05:42–05:57);
o M3 (05:45–06:00) só é enviado com o recibo completo do M2 em mãos (portão `readback_post`), de modo que os dois nunca
correm juntos; `"inputs": {"release": ..., "policy": ...}` (sem override); e no `plan`: `"mode": "POST"`, `"dry_run": null`,
`release.content_b64: null`, `release.container_target: "/c3po-epoch-release"`, `release.directory_entries: 1`,
`"render": null`, `"limits": null`, `"bind_probe": null`, e as linhas de `live.parent`, `deploy.tree` e
`deploy.lock_directory` copiadas do M2p: `{"$from": {"evidence": "M2P", "pointer": "/items/directory:LIVE_PARENT/observed_rows"}}`
(e `DEPLOY_TREE`, `LOCK_DIRECTORY`). `evidence`: o S1 e `{"role": "M2P", "operation": "GO_READONLY_HOSTOPS02_EPOCH_READBACK_01",
"bound": "<conjunto do M2p>"}` (mesma família: sem `family`). Portão de envio: o recibo completo do M1 (ou M1') com estes
bytes: `{"install": {"bound": "<conjunto do M1>", "family": "<HOSTOPS02_COPY>/install_release"}}`.

#### M3 — K6a, ativação (e M3', a reserva)

```json
{
  "schema": "BIND_ONCE_PARAMETERS_V1",
  "operation": "GO_WRITE_HOSTOPS02_ACTIVATE_01",
  "label": "m3-20261005-a",
  "signature_model": "PRE",
  "not_before": "2026-10-05T08:45:00Z", "not_after": "2026-10-05T09:00:00Z",
  "inputs": {"policy": "<policy.json aprovada, a do M2p>", "release": "<release aprovada, a do M2p>", "override": "<o override que o M2p renderizou>"},
  "plan": {
    "data_root": {"$from": {"evidence": "M2P", "pointer": "/effects/worker/data_source"}},
    "live_parent": {"$from": {"evidence": "M2P", "pointer": "/items/directory:LIVE_PARENT/observed_rows"}},
    "directory_name": "2026-10-05",
    "policy": {"name": "policy.json", "content_b64": {"$input": "policy", "as": "b64"}, "sha256": {"$input": "policy", "as": "sha256"},
               "bytes": {"$input": "policy", "as": "bytes"}},
    "override_name": "compose.override.json",
    "release": {"parent": {"$from": {"evidence": "M2P", "pointer": "/items/directory:RELEASE_PARENT/observed_rows"}},
                "directory_name": "r2d2-v2-release-20261005", "file_name": "release.CERTIFIED.json",
                "sha256": {"$input": "release", "as": "sha256"}, "bytes": {"$input": "release", "as": "bytes"}},
    "worker": {"image_id": {"$from": {"evidence": "M2P", "pointer": "/effects/image/image_id"}},
               "mount_target": {"$from": {"evidence": "M2P", "pointer": "/effects/worker/data_target"}}},
    "compose": {"project": {"$from": {"evidence": "M2P", "pointer": "/effects/render/project"}},
                "env_file": {"$from": {"evidence": "M2P", "pointer": "/effects/render/env_file"}},
                "files": {"$from": {"evidence": "M2P", "pointer": "/effects/render/files"}}},
    "deploy_directory": {"$from": {"evidence": "M2P", "pointer": "/items/directory:DEPLOY_TREE/observed_rows"}},
    "lock": {"directory": {"$from": {"evidence": "M2P", "pointer": "/items/directory:LOCK_DIRECTORY/observed_rows"}}, "wait_seconds": 20},
    "evidence_boot_id_sha256": {"$from": {"evidence": "M2P", "pointer": "/effects/evidence_boot_id_sha256"}}
  },
  "evidence": [{"role": "M2P", "operation": "GO_READONLY_HOSTOPS02_EPOCH_READBACK_01", "bound": "<conjunto do M2p>", "family": "<HOSTOPS02_COPY>/epoch_readback"}],
  "review": {"kind": "CODEX_REVIEWED", "document_file": "<parecer do Codex sobre estes bytes>"},
  "linux_job": {"kind": "LINUX_JOB_PASSED", "document_file": "<registro do job Linux do K6a, com SHAPES.activate.linux-root.json>"}
}
```

| Chave | De onde vem |
|---|---|
| janela | M3 05:45–06:00 BRT; M3' 06:26–06:41 (não 06:35–06:37): o início do portão tem de estar em `policy.valid_at` do M2p (`POLICY_NOT_VERIFIED_AT_THIS_GATE`) |
| `plan` (linhas, boot, imagem, bind, compose, hashes) | do recibo do M2p (PRE FULL, `rows_in_receipt` verdadeiro), por ponteiro: tabela `PLAN_SOURCES` do binder; política e release: arquivos de entrada (hash e tamanho iguais aos do M2p) |
| `directory_name`, `override_name`, `lock.wait_seconds` | decididos na folha |
| `inputs.override` | o arquivo do override que o M2p renderizou: não entra no pedido (a fonte deriva os bytes), mas o binder exige que seja byte a byte o que este pedido escreve (`OVERRIDE_FILE_NOT_THE_ONE_ACTIVATE_WRITES`) e a pergunta mostra o hash |
| conferências independentes | o binder recalcula, sem o código da fonte, os quatro valores, os bytes do override (`json.dumps` com `sort_keys`) e o digest da política (`sort_keys`, `separators=(',',':')`, `ensure_ascii=False`) e compara com `EFFECTS.json`; o override tem de ser o que o M2p renderizou (hash) |
| M3' | os mesmos `plan`, `evidence`, `inputs`, `review`, `linux_job`; outro `label` (`m3r-20261005-a`), a sua janela, `"spare_of": {"bound": "<conjunto do M3, já assinado>"}` |

Portão de envio do M3 (e do M3'): `{"readback_post": {"bound": "<conjunto do M2>", "family": "<HOSTOPS02_COPY>/epoch_readback"}}`.

## 3. Sequência de uma execução real

<!-- bloco: verificar -->
```zsh
L=<label>; if source "${BIND_CANDIDATE_ROOT:?}/bind/runbook_env.zsh"; then
  cd "${B}" && shasum -a 256 -c SHA256SUMS && shasum -a 256 SHA256SUMS \
   && cd "${W1_FAMILY}" && shasum -a 256 -c SHA256SUMS && shasum -a 256 SHA256SUMS \
   && cd "${HOSTOPS_FAMILY}" && shasum -a 256 -c SHA256SUMS | grep -vc ': OK$' ; shasum -a 256 "${HOSTOPS_FAMILY}/SHA256SUMS" ; date -u +%Y-%m-%dT%H:%M:%SZ
fi
```

Conferir a olho: tudo `OK` no manifesto do binder; W1 `108b74ca…3347` com 15 OK; HOSTOPS01 `5609b334…71c1` e a
contagem de linhas não-OK igual a `0`; a hora UTC.

### Bloco 1a — diretório da execução e parâmetros (uma vez)

<!-- bloco: preparar-run manual -->
```zsh
L=<label>; if source "${BIND_CANDIDATE_ROOT:?}/bind/runbook_env.zsh"; then
  if [[ -e "${RUN}/run.env" ]]; then echo "JÁ FEITO: ${RUN}/run.env existe e não é reescrito. Valores gravados:"; cat "${RUN}/run.env"
  else
    mkdir -p "${RUN}" && chmod 700 "${RUN}" \
     && print -r -- "FAMILY=${W1_FAMILY}
OP=GO_READONLY_W1PREFLIGHT_01
MODE=real
PARAMS=${RUN}/PARAMETERS.json
OUT=${RUN}/bound" > "${RUN}/run.env" && cat "${RUN}/run.env"
  fi
fi
```

Para HOSTOPS01: `FAMILY=${HOSTOPS_FAMILY}` e o `OP` da operação. Para HOSTOPS02: `FAMILY=${HOSTOPS02_COPY}/<diretório da
operação>` (a cópia selada da seção 10.1, nunca o diretório de trabalho), o `OP` da operação e, sempre que a folha nomear
portões de envio (todas as gravações do HOSTOPS02 e o M2), `GATES=${RUN}/GATES.json` (seção 10.4): sem ele os blocos 6 e 9
param (`PARADO`), e o bloco 1b avisa. `RESUME_GATE` não é mais usado: o bloco 9 roda `check --step resume` em todo
conjunto do HOSTOPS02. Para a opção (B): `OUT=${W}/once-<label>/bound`
(e `mkdir -p "${W}/once-<label>"`, modo 700, antes do prepare). Depois escrever `${RUN}/PARAMETERS.json` (seção 2)
com a ferramenta de escrita, e conferir com `cat`. `label` do arquivo = `<label>` dos blocos.

### Bloco 1b — prepare

<!-- bloco: prepare -->
```zsh
L=<label>; if source "${BIND_CANDIDATE_ROOT:?}/bind/runbook_env.zsh"; then
  if [[ -e "${RUN}/prepare.json" ]]; then echo "JÁ FEITO: ${RUN}/prepare.json existe; o prepare não roda de novo. Valores gravados:"
  elif [[ "$(${PY} -B "${PICK}" "${PARAMS}" label)" != "${L}" ]]; then echo "PARADO: o label de PARAMETERS.json não é ${L}; nada foi feito"
  else
    OUTJSON=$(${PY} -B "${BIND}" prepare --family "${FAMILY}" --operation "${OP}" --params "${PARAMS}" --reference "${REFERENCE}" --out "${OUT}" --mode "${MODE}"); RC=$?; echo "exit=${RC}"
    if [[ ${RC} == 0 ]]; then print -r -- "${OUTJSON}" > "${RUN}/prepare.json"; else print -r -- "${OUTJSON}"; fi
  fi
  if [[ -e "${RUN}/prepare.json" ]]; then
    SHEET=$(${PY} -B "${PICK}" "${RUN}/prepare.json" prepare_json_sha256) && is_hash "${SHEET}" && echo "folha ${SHEET}" \
     && [[ "$(${PY} -B "${PICK}" "${RUN}/prepare.json" sheet.label)" == "${L}" ]] && echo "label ${L} confere com a folha" \
     && shasum -a 256 "${OUT}/PREPARE.json" "${OUT}/REQUEST.BOUND.json" "${OUT}/GO_SCOPE.txt" && ls -la "${OUT}" "${OUT}/.dispatch-root" \
     && ${PY} -B -c "import json,sys;s=json.load(open(sys.argv[1]))['sheet'];print(json.dumps({k:s[k] for k in ('mode','operation','family','signature_model','review','request_sha256','source_sha256','scope_sha256','go_scope_sha256','effects_sha256','success_criterion','host_binding_sha256','command_sha256','window','transport_reference','evidence','plan_values_equal_to_the_cited_receipts','provisional_proofs','claim_root_identity')},indent=1,ensure_ascii=False))" "${RUN}/prepare.json"
    G=$(${PY} -B -c "import json,sys;h=json.load(open(sys.argv[1]))['sheet'].get('hostops02');print(' '.join(h['dispatch_gates']) if h else '')" "${RUN}/prepare.json") \
     && [[ -n "${G}" ]] && echo "portões de envio da folha: ${G}" && [[ -z "${GATES}" ]] && echo "ATENÇÃO: o run.env não tem GATES: os blocos 6 e 9 param até ele existir (bloco 1a)"
  fi
fi
```

Conferir a olho:

- `exit=0`; `mode` `REAL`; `family` com o selo da seção 1; `shasum` de `PREPARE.json` igual a `folha`, e o de
  `REQUEST.BOUND.json` igual a `request_sha256`; `label ... confere com a folha`.
- `host_binding_sha256` = `226f6148…e9d2`; `command_sha256` = `6719e523…dce2`.
- `transport_reference`: `kind` `REAL`, `last_use.status` `KNOWN_COMPLETE` ou `KNOWN_PARTIAL`,
  `connection_files` com os dois booleanos `true`.
- `window.brt`: é a janela que vai ser dita ao dono; `latest_start` = fim − 80 s; no W1, `gate_span_seconds` ≤ 3600.
- `provisional_proofs`: as 17 linhas da seção 6 (a fonte e o dispatcher da família aceitaram documentos provisórios
  com esta janela e este transporte, e recusaram as variantes).
- W1: `source_sha256` `7d1df28d…79f8`, `scope_sha256` `d860347b…4b9d`. Núcleo: ler `EFFECTS.json` inteiro; em
  `evidence`, cada recibo com `source` `BOUND_SET`, `complete` `true` (ou a aceitação explícita) e
  `bound_set.mode` `REAL`; numa gravação, `review` com o `kind` e o sha256 do documento certo.
- `.dispatch-root` vazio; nenhum arquivo `*AUTHORITY*`, `*GO*` ou `DISPATCH.BOUND.json` existe ainda.

O prepare roda uma vez por diretório: um segundo recusa com `OUT_EXISTS_OR_PARENT_MISSING`.

Publicar no canal, para objeção do auditor quando o plano pedir (hashes, selo e janela em UTC; nenhum valor do
servidor). O texto de `GO_SCOPE.txt` pode ser anexado à mão: não tem valor do servidor.

<!-- bloco: publicar-pedido rede -->
```zsh
L=<label>; if source "${BIND_CANDIDATE_ROOT:?}/bind/runbook_env.zsh"; then
  if [[ -e "${RUN}/request_publication_url.txt" ]]; then echo "JÁ FEITO: pedido publicado em $(cat "${RUN}/request_publication_url.txt")"
  else
    TS=$(date -u +%Y%m%dT%H%M%SZ) \
     && ${PY} -B -c "import json,sys;p=json.load(open(sys.argv[1]));s=p['sheet'];w=s['window'];f=s['family'];print('%s (%s, %s) request bound, NOT signed: request %s ; source %s ; scope %s ; go scope %s ; sheet %s ; seal %s (%s rev %s) ; window %s .. %s UTC ; gate %s .. %s UTC ; latest start %s ; signature model %s'%(s['operation'],s['label'],s['mode'],s['request_sha256'],s['source_sha256'],s['scope_sha256'],s['go_scope_sha256'],p['prepare_json_sha256'],f['sha256sums_sha256'],f['family'],f['revision'],w['not_before'],w['not_after'],w['gate_not_before'],w['gate_not_after'],w['latest_start'],s['signature_model']))" "${RUN}/prepare.json" > "${RUN}/publish-request.${TS}.md" \
     && cat "${RUN}/publish-request.${TS}.md" \
     && { gh issue comment ${ISSUE} --repo ${REPO} --body-file "${RUN}/publish-request.${TS}.md" > "${RUN}/gh-request.${TS}.out"; echo "gh exit=$? (saída em gh-request.${TS}.out)" }
    URL=$(tail -n 1 "${RUN}/gh-request.${TS}.out" 2>/dev/null)
    is_comment_url "${URL}" && print -r -- "${URL}" > "${RUN}/request_publication_url.txt" && echo "request_publication_url $(cat "${RUN}/request_publication_url.txt")" \
     || echo "request_publication_url.txt NÃO foi escrito por este bloco: procurar o comentário no canal antes de publicar de novo"
  fi
fi
```

### Bloco 2 — a pergunta ao dono

Notificar (banner no Mac e push), depois perguntar pelo AskUserQuestion com **o texto exato de
`${OUT}/OWNER_QUESTION.txt`** (português, horas em BRT, termina em "responda exatamente: Assino"; traz o hash da
folha; numa gravação, a lista do que é criado e a linha da revisão ou da dispensa).

<!-- bloco: pergunta -->
```zsh
L=<label>; if source "${BIND_CANDIDATE_ROOT:?}/bind/runbook_env.zsh"; then
  cat "${OUT}/OWNER_QUESTION.txt"
fi
```

**Só a resposta literal `Assino` é assinatura.** No instante da resposta, rodar o bloco abaixo trocando
`<resposta>` pela resposta do dono, palavra por palavra. Ele grava a hora (por comando) e a resposta **somente**
se ela for a palavra de assinatura; com qualquer outra resposta não grava nada, e o bloco 3 não roda. Se a pergunta
for refeita (a mesma folha) e a nova resposta for `Assino`, rodar o bloco de novo com ela: a hora gravada é a
dessa resposta, nunca a de uma resposta anterior. Nunca passar uma hora ou uma resposta que o dono não deu.

<!-- bloco: resposta -->
```zsh
L=<label>; R='<resposta>'; if source "${BIND_CANDIDATE_ROOT:?}/bind/runbook_env.zsh"; then
  if [[ -e "${RUN}/owner_answer.txt" ]]; then echo "JÁ FEITO: resposta de assinatura já gravada: $(cat "${RUN}/owner_answer.txt") às $(cat "${RUN}/signed_at_utc.txt")"
  elif [[ "${R}" != "${ANSWER_WORD}" ]]; then echo "NÃO É ASSINATURA: a resposta não é literalmente a palavra de assinatura; nada foi gravado e o sign não roda"
  else
    date -u +%Y-%m-%dT%H:%M:%SZ > "${RUN}/signed_at_utc.txt" && print -r -- "${R}" > "${RUN}/owner_answer.txt" \
     && echo "resposta gravada: $(cat "${RUN}/owner_answer.txt") às $(cat "${RUN}/signed_at_utc.txt")"
  fi
fi
```

### Bloco 3 — sign

<!-- bloco: sign -->
```zsh
L=<label>; if source "${BIND_CANDIDATE_ROOT:?}/bind/runbook_env.zsh"; then
  if [[ -e "${RUN}/sign.json" ]]; then echo "JÁ FEITO: ${RUN}/sign.json existe; o sign não roda de novo. Conjunto:"
  elif [[ ! -e "${RUN}/owner_answer.txt" || ! -e "${RUN}/signed_at_utc.txt" ]]; then echo "PARADO: não há resposta de assinatura gravada (bloco da resposta); o sign não roda"
  elif SHEET=$(${PY} -B "${PICK}" "${RUN}/prepare.json" prepare_json_sha256) && SIGNED=$(cat "${RUN}/signed_at_utc.txt") && ANSWER=$(cat "${RUN}/owner_answer.txt") && is_hash "${SHEET}" && is_utc_stamp "${SIGNED}"; then
    OUTJSON=$(${PY} -B "${BIND}" sign --bound "${OUT}" --sheet-sha256 "${SHEET}" --signed-at "${SIGNED}" --owner-answer "${ANSWER}"); RC=$?; echo "exit=${RC}"
    [[ ${RC} == 0 ]] && print -r -- "${OUTJSON}" > "${RUN}/sign.json"
    print -r -- "${OUTJSON}"
  else echo "PARADO: hash da folha ou hora da resposta ilegível; o sign não rodou"
  fi
  [[ -e "${RUN}/sign.json" ]] && cd "${OUT}" && shasum -a 256 -c SHA256SUMS | grep -vc ': OK$' ; ls -la "${OUT}"
fi
```

Conferir a olho: `exit=0`, `status` `BOUND_NOT_DISPATCHED`; `prepare_json_sha256` é a folha que o dono viu;
`signed_at_utc` é a hora gravada e `owner_answer_verbatim` é `Assino`; `authority_name` e `go_name` começam por
`DUDU_`; `command_sha256` e `host_binding_sha256` iguais aos do prepare; contagem de linhas não-OK do `SHA256SUMS`
igual a `0`; `.dispatch-root` ainda vazio. O sign roda uma vez: o segundo recusa com
`BOUND_FILE_SET_OR_ALREADY_SIGNED`. Resposta que não é a palavra literal: `OWNER_ANSWER_IS_NOT_THE_SIGNATURE`,
nada escrito. O sign funciona antes da janela abrir (assinatura de véspera): nada nele depende do relógio estar
dentro dela.

### Bloco 4 — check (validação a seco, não escreve nada)

<!-- bloco: check -->
```zsh
L=<label>; if source "${BIND_CANDIDATE_ROOT:?}/bind/runbook_env.zsh"; then
  GATEARGS=(); if [[ -n "${GATES}" ]]; then GATEARGS=(--gates "${GATES}"); fi
  OUTJSON=$(${PY} -B "${BIND}" check --bound "${OUT}" --family "${FAMILY}" "${GATEARGS[@]}"); RC=$?; echo "exit=${RC}"
  print -r -- "${OUTJSON}" > "${RUN}/check.$(date -u +%Y%m%dT%H%M%SZ).$$.json"; print -r -- "${OUTJSON}"
fi
```

Conferir a olho, **antes do bloco 6**: `exit=0`; `verdict` `VALID_WINDOW_OPEN` (ou `VALID_WINDOW_NOT_YET_OPEN`
antes da janela); `a_new_dispatcher_prepare_would_reach_the_claim_and` `CREATE_IT` com a janela aberta;
`documents_are_the_deterministic_construction`, `family_seal_and_templates_rechecked` e
`binder_unchanged_since_prepare` `true`; as 17 provas da seção 6; `final_payload_run_locally_as_this_user` com
`REFUSED` / `REQUEST_OR_EXECUTOR_UNBOUND` e stderr vazio; `attempt_phase` `NOT_PREPARED`; `wrote_nothing` `true`.

| `verdict` | Exit | Significado |
|---|---|---|
| `VALID_WINDOW_NOT_YET_OPEN`, `VALID_WINDOW_OPEN` | 0 | conjunto válido, nada reivindicado ainda |
| `VALID_BUT_PAST_LATEST_START_THE_DISPATCHER_WILL_REFUSE` | 1 | a assinatura não serve mais |
| `VALID_ALREADY_PREPARED` | 1 | o claim já existe (bloco 6 feito): um segundo prepare do dispatcher falharia; seguir para publicação e resume |
| `VALID_GO_SPENT` | 1 | `spawn.claim` existe (tentativa terminada ou de resultado desconhecido): o GO está gasto |
| `VALID_BUT_THE_CLAIM_ROOT_IS_NOT_AS_THE_DISPATCHER_LEAVES_IT` | 1 | conteúdo inesperado na raiz de uso único: parar e relatar |
| `VALID_BUT_DISPATCH_GATES_NOT_MET` | 1 | HOSTOPS02: um portão de envio da folha não foi atendido (ou `GATES` não foi dado): `dispatch_gates.failed` diz qual; não despachar |
| `VALID_BUT_NOW_IS_A_MINUTE_TO_AVOID` | 1 | HOSTOPS02: agora é um minuto a evitar (:05–:07, :10–:25, :35–:37); esperar o próximo minuto utilizável |
| `VALID_RESUME_ALLOWED_BY_THE_GATES`, `VALID_BUT_RESUME_GATES_NOT_MET`, `VALID_BUT_NOTHING_TO_RESUME` | 0, 1, 1 | HOSTOPS02, só com `--step resume` (o bloco 9 roda sozinho): portões, minuto a evitar e último início antes do resume |

As provas `dispatcher_accepts_*` param **antes** da criação exclusiva do claim; depois do bloco 6 elas continuam
dizendo "aceito até o claim", e é o `verdict` (com `window_verdict` e `attempt_phase`) que diz o estado.
O check pode ser repetido à vontade: cada saída vai para um arquivo próprio, com a hora UTC e o número do processo
do shell no nome, de modo que duas no mesmo segundo não colidem (o mesmo vale para o bloco 10).

### Bloco 5 — publicar a âncora

`config_sha256` é a âncora local, passada ao dispatcher independentemente do arquivo.

<!-- bloco: publicar-ancora rede -->
```zsh
L=<label>; if source "${BIND_CANDIDATE_ROOT:?}/bind/runbook_env.zsh"; then
  if [[ -e "${RUN}/anchor_publication_url.txt" ]]; then echo "JÁ FEITO: âncora publicada em $(cat "${RUN}/anchor_publication_url.txt")"
  else
    TS=$(date -u +%Y%m%dT%H%M%SZ) \
     && ${PY} -B -c "import json,sys;s=json.load(open(sys.argv[1]));w=s['window'];print('%s (%s) bound and signed, NOT dispatched: config %s ; payload %s (%d bytes) ; go %s ; authority %s ; request %s ; sheet %s ; signed at %s ; gate %s .. %s UTC ; latest start %s'%(s['operation'],s['mode'],s['config_sha256'],s['payload_sha256'],s['payload_bytes'],s['go_sha256'],s['authority_sha256'],s['request_sha256'],s['prepare_json_sha256'],s['signed_at_utc'],w['gate_not_before'],w['gate_not_after'],w['latest_start']))" "${RUN}/sign.json" > "${RUN}/publish-anchor.${TS}.md" \
     && cat "${RUN}/publish-anchor.${TS}.md" \
     && { gh issue comment ${ISSUE} --repo ${REPO} --body-file "${RUN}/publish-anchor.${TS}.md" > "${RUN}/gh-anchor.${TS}.out"; echo "gh exit=$? (saída em gh-anchor.${TS}.out)" }
    URL=$(tail -n 1 "${RUN}/gh-anchor.${TS}.out" 2>/dev/null)
    is_comment_url "${URL}" && print -r -- "${URL}" > "${RUN}/anchor_publication_url.txt" && echo "anchor_publication_url $(cat "${RUN}/anchor_publication_url.txt")" \
     || echo "anchor_publication_url.txt NÃO foi escrito por este bloco: procurar o comentário no canal antes de publicar de novo"
  fi
fi
```

### Bloco 6 — prepare do dispatcher: UMA vez; sai com 2 por desenho

O sucesso deste passo é exit 2 com `AWAITING_PUBLICATION_NO_SPAWN`. Decidir pelo status impresso, nunca pelo código
de saída (uma recusa também sai com 2).

O dispatcher importa três módulos irmãos pelo nome. O `/usr/bin/python3` deste Mac guarda bytecode fora do
diretório (`~/Library/Caches/com.apple.python/<caminho absoluto>`), e `-B` só impede a gravação: um `.pyc` em cache
com data e tamanho iguais seria executado no lugar da fonte fixada por hash. Por isso o dispatcher roda com
`-X pycache_prefix=<diretório novo, vazio, 0700>` (criado por `mktemp -d` no bloco): sem cache para ler. O bloco
remove o diretório no fim, o que só funciona se ele continuou vazio. O payload enviado não é afetado: é lido por hash.

<!-- bloco: dispatcher-prepare -->
```zsh
L=<label>; if source "${BIND_CANDIDATE_ROOT:?}/bind/runbook_env.zsh"; then
  GATEOK=yes
  if [[ ! -e "${RUN}/dispatch-prepare.json" ]]; then
    H02=$(${PY} -B -c "import json,sys;s=json.load(open(sys.argv[1]));h=s.get('hostops02');print('none' if h is None else ('gates' if h['dispatch_gates'] else 'nogates'))" "${OUT}/PREPARE.json") || H02=unreadable
    if [[ "${H02}" == unreadable ]]; then GATEOK=no; echo "PARADO: PREPARE.json ilegível; o prepare do dispatcher não rodou"
    elif [[ "${H02}" == gates && -z "${GATES}" ]]; then GATEOK=no; echo "PARADO: a folha lista portões de envio e o run.env não tem GATES (bloco 1a); o prepare do dispatcher não rodou"
    elif [[ "${H02}" != none ]]; then
      GATEARGS=(); if [[ -n "${GATES}" ]]; then GATEARGS=(--gates "${GATES}"); fi
      GJSON=$(${PY} -B "${BIND}" check --bound "${OUT}" --family "${FAMILY}" "${GATEARGS[@]}"); echo "check antes do prepare do dispatcher exit=$?"
      print -r -- "${GJSON}" > "${RUN}/check-dispatch.$(date -u +%Y%m%dT%H%M%SZ).$$.json"
      if [[ "${GJSON}" != *'"verdict": "VALID_WINDOW_OPEN"'* ]]; then GATEOK=no; echo "PARADO: o check não deu VALID_WINDOW_OPEN (portão, minuto a evitar, janela ou reserva): o prepare do dispatcher não rodou (ver check-dispatch.*.json)"; fi
    fi
  fi
  if [[ -e "${RUN}/dispatch-prepare.json" ]]; then echo "JÁ FEITO: ${RUN}/dispatch-prepare.json existe; o prepare do dispatcher não roda de novo. Valores gravados:"
  elif [[ "${GATEOK}" != yes ]]; then echo "nada foi preparado: nenhum claim foi criado por este bloco"
  elif CFG=$(${PY} -B "${PICK}" "${RUN}/sign.json" config_sha256) && is_hash "${CFG}" && shasum -a 256 "${OUT}/DISPATCH.BOUND.json" && PYC=$(mktemp -d "${RUN}/pycache-prefix.XXXXXXXX"); then
    OUTJSON=$(${PY} -B -X pycache_prefix="${PYC}" "${OUT}/dispatch_once.py" --config "${OUT}/DISPATCH.BOUND.json" --config-sha256 "${CFG}" --phase prepare); RC=$?; echo "exit=${RC} (2 é o esperado)"; print -r -- "${OUTJSON}"
    rmdir "${PYC}" && echo "prefixo de cache continuou vazio e foi removido"
    [[ "${OUTJSON}" == *'"status": "AWAITING_PUBLICATION_NO_SPAWN"'* ]] && print -r -- "${OUTJSON}" > "${RUN}/dispatch-prepare.json"
  else echo "PARADO: sign.json ilegível ou hash da config inválido; o prepare do dispatcher não rodou"
  fi
  if [[ -e "${RUN}/dispatch-prepare.json" ]]; then
    INTENT=$(${PY} -B "${PICK}" "${RUN}/dispatch-prepare.json" intent_sha256) && is_hash "${INTENT}" && echo "intent ${INTENT}" \
     && shasum -a 256 "${ATTEMPT}/intent.json" && ls -la "${OUT}/.dispatch-root" "${ATTEMPT}"
  fi
fi
```

Conferir a olho: uma linha `{"config_sha256": ..., "go_sha256": ..., "intent_sha256": ..., "retry": false, "status":
"AWAITING_PUBLICATION_NO_SPAWN"}` e `exit=2`; `config_sha256` e `go_sha256` iguais aos do `sign.json`; `shasum` de
`intent.json` igual a `intent`; em `.dispatch-root`, o claim `.go-<go_sha256>.claim` e o diretório `<label>-once`
só com `intent.json`; `prefixo de cache continuou vazio e foi removido`. Este é o primeiro código que abre a chave
e o known-hosts (lê os dois com o hash fixado, antes de qualquer claim). Não contata nada.
`{"status":"REFUSED_OR_UNCERTAIN","code":"DISPATCH_REFUSED"}` com `.dispatch-root` vazio: nada foi consumido
(causas típicas: relógio fora da janela ou depois do último início; chave ou known-hosts com outro hash); entender
a causa, e o prepare pode rodar de novo. Com o claim presente: o GO está gasto para o prepare; não repetir.

### Bloco 7 — publicar o intent e pegar id e hora do comentário

<!-- bloco: publicar-intent rede -->
```zsh
L=<label>; if source "${BIND_CANDIDATE_ROOT:?}/bind/runbook_env.zsh"; then
  if [[ -e "${RUN}/publication_url.txt" ]]; then echo "JÁ FEITO: intent publicado em $(cat "${RUN}/publication_url.txt")"
  else
    CFG=$(${PY} -B "${PICK}" "${RUN}/sign.json" config_sha256) && GO=$(${PY} -B "${PICK}" "${RUN}/sign.json" go_sha256) \
     && INTENT=$(${PY} -B "${PICK}" "${RUN}/dispatch-prepare.json" intent_sha256) && is_hash "${CFG}" && is_hash "${GO}" && is_hash "${INTENT}" \
     && TS=$(date -u +%Y%m%dT%H%M%SZ) \
     && print -r -- "${OP} (${L}) intent published before spawn: intent ${INTENT} ; config ${CFG} ; go ${GO}" > "${RUN}/publish-intent.${TS}.md" \
     && { gh issue comment ${ISSUE} --repo ${REPO} --body-file "${RUN}/publish-intent.${TS}.md" > "${RUN}/gh-intent.${TS}.out"; echo "gh exit=$? (saída em gh-intent.${TS}.out)" }
    URL=$(tail -n 1 "${RUN}/gh-intent.${TS}.out" 2>/dev/null)
    is_comment_url "${URL}" && print -r -- "${URL}" > "${RUN}/publication_url.txt" && echo "publication_url $(cat "${RUN}/publication_url.txt")" \
     || echo "publication_url.txt NÃO foi escrito por este bloco"
  fi
fi
```

Se não foi escrito: não publicar de novo às cegas; procurar primeiro o comentário (a publicação pode ter saído
mesmo com a saída perdida):

<!-- bloco: achar-intent rede -->
```zsh
L=<label>; if source "${BIND_CANDIDATE_ROOT:?}/bind/runbook_env.zsh"; then
  if [[ -e "${RUN}/publication_url.txt" ]]; then echo "JÁ FEITO: intent publicado em $(cat "${RUN}/publication_url.txt")"
  else
    INTENT=$(${PY} -B "${PICK}" "${RUN}/dispatch-prepare.json" intent_sha256) && is_hash "${INTENT}" \
     && SINCE=$(cat "${RUN}/signed_at_utc.txt") && is_utc_stamp "${SINCE}" && TS=$(date -u +%Y%m%dT%H%M%SZ) \
     && { gh api "repos/${REPO}/issues/${ISSUE}/comments?since=${SINCE}&per_page=100" --jq ".[] | select(.body | contains(\"intent ${INTENT}\")) | .html_url" > "${RUN}/gh-intent-find.${TS}.out"; echo "gh exit=$?" }
    N=$(grep -c . "${RUN}/gh-intent-find.${TS}.out" 2>/dev/null); URL=$(head -n 1 "${RUN}/gh-intent-find.${TS}.out" 2>/dev/null)
    [[ "${N}" -ge 1 ]] && is_comment_url "${URL}" && print -r -- "${URL}" > "${RUN}/publication_url.txt" && echo "achados ${N}; publication_url $(cat "${RUN}/publication_url.txt")" \
     || echo "achados ${N:-0}; publication_url.txt NÃO foi escrito por este bloco"
  fi
fi
```

O id do comentário e a hora de criação (`created_at`), pela API:

<!-- bloco: id-e-hora rede -->
```zsh
L=<label>; if source "${BIND_CANDIDATE_ROOT:?}/bind/runbook_env.zsh"; then
  if [[ -e "${RUN}/publication_ref.txt" || -e "${RUN}/published_at_utc.txt" ]]; then echo "JÁ FEITO: publication_ref $(cat "${RUN}/publication_ref.txt") published_at $(cat "${RUN}/published_at_utc.txt")"
  else
    URL=$(cat "${RUN}/publication_url.txt") && is_comment_url "${URL}" && PUBID=${URL##*issuecomment-} && [[ "${PUBID}" =~ '^[0-9]{6,20}$' ]] \
     && TS=$(date -u +%Y%m%dT%H%M%SZ) \
     && { gh api "repos/${REPO}/issues/comments/${PUBID}" --jq .created_at > "${RUN}/gh-created.${TS}.out"; echo "gh exit=$?" }
    AT=$(tail -n 1 "${RUN}/gh-created.${TS}.out" 2>/dev/null)
    is_utc_stamp "${AT}" && print -r -- "${PUBID}" > "${RUN}/publication_ref.txt" && print -r -- "${AT}" > "${RUN}/published_at_utc.txt" \
     && echo "publication_ref $(cat "${RUN}/publication_ref.txt") published_at $(cat "${RUN}/published_at_utc.txt")" \
     || echo "publication_ref.txt / published_at_utc.txt NÃO foram escritos por este bloco"
  fi
fi
```

### Bloco 8 — publish-proof

<!-- bloco: publish-proof -->
```zsh
L=<label>; if source "${BIND_CANDIDATE_ROOT:?}/bind/runbook_env.zsh"; then
  if [[ -e "${RUN}/proof.json" ]]; then echo "JÁ FEITO: ${RUN}/proof.json existe; a prova não é escrita de novo. Valores gravados:"
  elif PUBID=$(cat "${RUN}/publication_ref.txt") && AT=$(cat "${RUN}/published_at_utc.txt") && is_utc_stamp "${AT}"; then
    OUTJSON=$(${PY} -B "${BIND}" publish-proof --bound "${OUT}" --comment-id "${PUBID}" --created-at "${AT}"); RC=$?; echo "exit=${RC}"
    [[ ${RC} == 0 ]] && print -r -- "${OUTJSON}" > "${RUN}/proof.json"
    print -r -- "${OUTJSON}"
  else echo "PARADO: publication_ref.txt ou published_at_utc.txt ausente ou ilegível; a prova não foi escrita"
  fi
  if [[ -e "${RUN}/proof.json" ]]; then
    PSHA=$(${PY} -B "${PICK}" "${RUN}/proof.json" publication_proof_sha256) && is_hash "${PSHA}" && echo "prova ${PSHA}" \
     && shasum -a 256 "${OUT}/PUBLICATION.PROOF.json" && ls -l "${OUT}/PUBLICATION.PROOF.json"
  fi
fi
```

Conferir a olho: `exit=0`, `PROOF_WRITTEN_NOT_DISPATCHED`; `intent_sha256` igual ao do bloco 6; `published_at`
não anterior a `intent_started_at`; arquivo 0600 com o hash impresso. O dispatcher exige
`not_before <= intent.started_at <= published_at <= agora`: por isso se usa a hora de criação do comentário.
A prova nunca é sobrescrita; uma prova corrigida (só antes do resume) leva o nome seguinte: acrescentar
`--name PUBLICATION.PROOF.R2.json`. Publicar o hash da prova no canal:

<!-- bloco: publicar-prova rede -->
```zsh
L=<label>; if source "${BIND_CANDIDATE_ROOT:?}/bind/runbook_env.zsh"; then
  if [[ -e "${RUN}/proof_publication_url.txt" ]]; then echo "JÁ FEITO: hash da prova publicado em $(cat "${RUN}/proof_publication_url.txt")"
  else
    TS=$(date -u +%Y%m%dT%H%M%SZ) \
     && ${PY} -B -c "import json,sys;s=json.load(open(sys.argv[1]));print('%s (%s) publication proof written, resume NOT run: proof %s ; intent %s ; config %s ; go %s ; publication ref %s ; published at %s ; latest start %s'%(s['operation'],s['mode'],s['publication_proof_sha256'],s['intent_sha256'],s['config_sha256'],s['go_sha256'],s['publication_ref'],s['published_at'],s['latest_start']))" "${RUN}/proof.json" > "${RUN}/publish-proof.${TS}.md" \
     && cat "${RUN}/publish-proof.${TS}.md" \
     && { gh issue comment ${ISSUE} --repo ${REPO} --body-file "${RUN}/publish-proof.${TS}.md" > "${RUN}/gh-proof.${TS}.out"; echo "gh exit=$? (saída em gh-proof.${TS}.out)" }
    URL=$(tail -n 1 "${RUN}/gh-proof.${TS}.out" 2>/dev/null)
    is_comment_url "${URL}" && print -r -- "${URL}" > "${RUN}/proof_publication_url.txt" && echo "proof_publication_url $(cat "${RUN}/proof_publication_url.txt")" \
     || echo "proof_publication_url.txt NÃO foi escrito por este bloco: procurar o comentário no canal antes de publicar de novo"
  fi
fi
```

### Bloco 9 — resume: UMA vez; o único passo que contata o servidor

Escolher um momento sem deploy, sem workflow agendado e sem o scan diário (um contêiner que sobe ou cai durante a
leitura dá PARCIAL). Evitar HH:05–07, HH:35–37 e HH:10–25. Tem de começar até `latest_start`. Leva até 80 s (o
watchdog), mais alguns segundos de finalização local. **Rodar com o timeout da ferramenta em 300000 ms (5 min),
em primeiro plano, e não interromper**: o padrão da ferramenta, 120 s, deixa pouca folga, e um bloco cortado no meio
deixa `spawn.claim` sem resultado. O bloco só inicia o resume se `intent.json` existe na tentativa deste label e
`spawn.claim` não existe; usa o mesmo prefixo de cache vazio do bloco 6.

<!-- bloco: resume host -->
```zsh
L=<label>; if source "${BIND_CANDIDATE_ROOT:?}/bind/runbook_env.zsh"; then
  GATEOK=yes
  H02=$(${PY} -B -c "import json,sys;s=json.load(open(sys.argv[1]));h=s.get('hostops02');print('none' if h is None else ('gates' if h['dispatch_gates'] else 'nogates'))" "${OUT}/PREPARE.json") || H02=unreadable
  if [[ "${H02}" == unreadable ]]; then GATEOK=no; echo "PARADO: PREPARE.json ilegível; o resume não roda"
  elif [[ "${H02}" == gates && -z "${GATES}" ]]; then GATEOK=no; echo "PARADO: a folha lista portões de envio e o run.env não tem GATES; o resume não roda"
  elif [[ "${H02}" != none ]]; then
    GATEARGS=(); if [[ -n "${GATES}" ]]; then GATEARGS=(--gates "${GATES}"); fi
    GJSON=$(${PY} -B "${BIND}" check --bound "${OUT}" --family "${FAMILY}" "${GATEARGS[@]}" --step resume); echo "check --step resume exit=$?"
    print -r -- "${GJSON}" > "${RUN}/check-resume.$(date -u +%Y%m%dT%H%M%SZ).$$.json"
    if [[ "${GJSON}" != *'"verdict": "VALID_RESUME_ALLOWED_BY_THE_GATES"'* ]]; then GATEOK=no; echo "PORTÃO ANTES DO RESUME NÃO LIBERADO (portão, minuto a evitar ou último início): o resume não roda (ver check-resume.*.json)"; fi
  fi
  if [[ "${GATEOK}" == yes ]] && CFG=$(${PY} -B "${PICK}" "${RUN}/sign.json" config_sha256) && PSHA=$(${PY} -B "${PICK}" "${RUN}/proof.json" publication_proof_sha256) \
     && PROOF=$(${PY} -B "${PICK}" "${RUN}/proof.json" publication_proof_path) && is_hash "${CFG}" && is_hash "${PSHA}" \
     && [[ -f "${ATTEMPT}/intent.json" && ! -e "${ATTEMPT}/spawn.claim" ]] && PYC=$(mktemp -d "${RUN}/pycache-prefix.XXXXXXXX"); then
    OUTJSON=$(${PY} -B -X pycache_prefix="${PYC}" "${OUT}/dispatch_once.py" --config "${OUT}/DISPATCH.BOUND.json" --config-sha256 "${CFG}" --phase resume --publication-proof "${PROOF}" --publication-proof-sha256 "${PSHA}"); RC=$?; echo "exit=${RC}"; print -r -- "${OUTJSON}"
    print -r -- "${OUTJSON}" > "${RUN}/resume.$(date -u +%Y%m%dT%H%M%SZ).json"; rmdir "${PYC}"
  else echo "RESUME NÃO INICIADO por este bloco: uma guarda falhou (hash ilegível, prova ausente, intent.json ausente ou spawn.claim já existe). Nada foi enviado."
  fi
  ls -la "${ATTEMPT}"
fi
```

| Status impresso | Exit | Significado | GO gasto? |
|---|---|---|---|
| `KNOWN_COMPLETE` | 0 | toda observação feita (leitura) / critério de sucesso atingido (gravação) | sim |
| `KNOWN_PARTIAL` | 2 | **resultado válido, não falha**: o recibo traz o que foi lido ou feito | sim |
| `KNOWN_REFUSAL` | 2 | o payload recusou no servidor antes de observar ou gravar | sim |
| `UNCERTAIN` | 2 | timeout, erro de transporte, stderr não vazio, recibo não vinculado | sim |
| `REFUSED_OR_UNCERTAIN` / `DISPATCH_REFUSED` | 2 | o dispatcher local recusou; se `spawn.claim` existe o GO está gasto, se não existe nenhuma tentativa foi feita | ver `spawn.claim` |

Gravação que terminou em qualquer coisa que não o critério de sucesso: o estado do servidor é estabelecido por uma
leitura (precheck ou readback) com GO próprio, nunca por uma segunda tentativa.

### Bloco 10 — status

<!-- bloco: status -->
```zsh
L=<label>; if source "${BIND_CANDIDATE_ROOT:?}/bind/runbook_env.zsh"; then
  OUTJSON=$(${PY} -B "${BIND}" status --bound "${OUT}"); RC=$?; echo "exit=${RC}"
  print -r -- "${OUTJSON}" > "${RUN}/status.$(date -u +%Y%m%dT%H%M%SZ).$$.json"; print -r -- "${OUTJSON}"
fi
```

`exit=0` só com recibo verificado (COMPLETE ou PARTIAL): `exit.json` bate com os bytes guardados de stdout e
stderr e vincula esta config, este request e este GO; stderr vazio; o recibo tem o esquema da operação, os vínculos
de hash (request, authority, GO, payload, vínculo do servidor) e o selo `metadata_sha256` correto; o status dele
combina com o do transporte. Para o núcleo: `outcome`, `success_criterion_met` e as contagens de chamadas.
O status imprime códigos, contagens e hashes, nunca um valor lido no servidor. Os `findings` do W1 são códigos, mas
dizem como o servidor está: por padrão sai só `findings_count`; `--show-findings` lista os códigos (leitura local;
no canal, só o que o auditor precisar). O conteúdo do recibo fica em `stdout.private.json`, 0600, onde está.
Antes do fim: `NOT_PREPARED`, `PREPARED_AWAITING_PUBLICATION`, `PREPARED_PROOF_WRITTEN_RESUME_NOT_RUN`,
`SPAWN_CLAIMED_NO_RESULT` (tentativa consumida, resultado desconhecido: nunca repetir).
`claim_root_read` diz qual raiz de uso único foi lida (seção 0, "Onde fica o diretório vinculado").

### Bloco 11 — cópia para o diretório durável

<!-- bloco: arquivar -->
```zsh
L=<label>; if source "${BIND_CANDIDATE_ROOT:?}/bind/runbook_env.zsh"; then
  DEST="${ARCHIVE:-${W}}/once-${L}" && NAME=$(basename "${OUT}") && mkdir -p "${DEST}" && chmod 700 "${DEST}" \
   && { [[ "${OUT}" == "${DEST}/${NAME}" ]] || { [[ ! -e "${DEST}/${NAME}" ]] && cp -Rp "${OUT}" "${DEST}/" } } \
   && find "${RUN}" -maxdepth 1 -type f -exec cp -np {} "${DEST}/" \; \
   && cd "${DEST}/${NAME}" && shasum -a 256 -c SHA256SUMS | grep -vc ': OK$' ; diff -r "${OUT}" "${DEST}/${NAME}" && echo "cópia idêntica" ; ${PY} -B "${BIND}" status --bound "${DEST}/${NAME}" | grep -E '"(status|verified|bound_set_is_a_relocated_copy|claim_root_read)"'
fi
```

Conferir a olho: `0` linhas não-OK; `cópia idêntica`; o `status` da cópia com o mesmo `status` e `verified` do bloco
10 e `bound_set_is_a_relocated_copy` `true` (opção A) ou `false` (opção B). Na opção A, depois de um resume
terminado, `claim_root_read` é `OF_THIS_COPY_WHICH_HOLDS_A_FINISHED_ATTEMPT`: são os bytes da cópia que foram
conferidos. Nada é apagado do scratchpad. O conjunto arquivado é o que um pedido posterior cita em `evidence`
(`"bound"`): o original ou a cópia, os dois servem.

## 4. Códigos de saída

| Comando | 0 | 1 | 2 |
|---|---|---|---|
| `bind_once.py prepare / sign / publish-proof / rehearsal-reference / sealed-copy` | feito | — | `REFUSED` |
| `bind_once.py check` | válido, janela aberta ou ainda não aberta, nada reivindicado (e, HOSTOPS02, os portões da folha atendidos); com `--step resume` (K10): `VALID_RESUME_ALLOWED_BY_THE_GATES` | válido, mas este GO não serve para um novo prepare do dispatcher: passou do último início, já preparado ou gasto, ou um portão de envio não atendido | `REFUSED` |
| `bind_once.py status` | recibo verificado | sem recibo verificado (inclui antes do resume) | `REFUSED` |
| `dispatch_once.py --phase prepare` | nunca | nunca | sempre: `AWAITING_PUBLICATION_NO_SPAWN` (sucesso) ou `DISPATCH_REFUSED` |
| `dispatch_once.py --phase resume` | só `KNOWN_COMPLETE` | nunca | `KNOWN_PARTIAL`, `KNOWN_REFUSAL`, `UNCERTAIN`, `DISPATCH_REFUSED` |

## 5. O que nunca se repete nem se toca

1. **resume, depois que `spawn.claim` existe**, qualquer que tenha sido a saída. Nova tentativa = novo request,
   nova folha, nova assinatura, novo diretório.
2. **prepare do dispatcher, depois que o claim existe.**
3. **Nunca rodar ssh, o payload final ou o comando remoto à mão**, nem o transporte fora de
   `dispatch_once.py --phase resume`.
4. **Nunca passar ao sign uma hora ou uma resposta que o dono não deu**, nem o hash de outra folha. Só a palavra
   literal `Assino` é assinatura.
5. **Nunca um conjunto de ensaio para o servidor real**, nem o contrário: o binder recusa nos dois sentidos
   (`REHEARSAL_SET_WITH_REAL_TRANSPORT`, `REAL_SET_WITH_REHEARSAL_TRANSPORT`, `REHEARSAL_DIRECTORY_NAME`,
   `REAL_SET_IN_REHEARSAL_DIRECTORY`, `OWNER_MODE_MISMATCH`), e também nos recibos citados
   (`EVIDENCE_SET_OF_THE_OTHER_MODE`, `EVIDENCE_RECEIPT_OF_ANOTHER_HOST`). Não renomear diretórios para contornar.
6. **Nunca rodar o dispatcher a partir de uma cópia do conjunto**, nem sem o prefixo de cache vazio dos blocos 6 e 9.

## 6. As 17 provas (`provisional_proofs` no prepare, `proofs` no check)

O binder roda o `authenticate()` da própria fonte e o `execute(phase='prepare')` do próprio dispatcher da família,
com relógio injetado, até a criação do claim, exclusive (o `os` do dispatcher levanta uma parada no primeiro
`open` que cria; a chave e o known-hosts são conferidos só por `lstat`). Valores esperados, sempre estes:

| Prova | Valor |
|---|---|
| `source_accepts_at_not_before`, `source_accepts_at_latest_start` | `ACCEPTED` |
| `source_refuses_before_the_window`, `source_refuses_at_not_after` | `OUTSIDE_GO_WINDOW` |
| `source_refuses_this_user` | `REQUEST_OR_EXECUTOR_UNBOUND` |
| `source_refuses_unsigned_authority` | `AUTHORITY_UNBOUND` |
| `source_refuses_unsigned_go` | `GO_UNBOUND` |
| `dispatcher_accepts_at_not_before`, `dispatcher_accepts_at_latest_start` | `ACCEPTED_UP_TO_THE_CLAIM` |
| `dispatcher_refuses_before_the_window`, `dispatcher_refuses_at_not_after` | `DISPATCH_WINDOW` |
| `dispatcher_refuses_after_latest_start` | `WINDOW_WITH_WATCHDOG` |
| `dispatcher_refuses_unsigned_go`, `dispatcher_refuses_the_template_go` | `GO_UNSIGNED` |
| `dispatcher_refuses_unsigned_authority` | `AUTHORITY_UNSIGNED` |
| `dispatcher_refuses_unbound_config` | `DISPATCH_UNBOUND` |
| `dispatcher_refuses_another_payload` | `FINAL_BUNDLE_BYTES` |

Uma prova com outro valor é recusa do binder (`PROOF_FAILED_<NOME>`), antes de pedir a assinatura (prepare) ou antes
de escrever qualquer documento assinado (sign).

## 7. Recusas mais prováveis e o que fazer

| Código | Causa | O que fazer |
|---|---|---|
| `FAMILY_SEAL_NOT_ACCEPTED` | o selo da família não está em `ACCEPTED_SEALS.json` | família nova ou revisão nova: acrescentar o selo por edição deliberada, refazer o manifesto do binder, publicar |
| `FAMILY_HASH`, `FAMILY_FILE_SET` | arquivo da família mudou, sobrou ou falta | não vincular; restaurar a família selada |
| `DATE_NOT_IN_FAMILY_SCOPE` | a data UTC da janela não é da família | janela errada, ou é preciso bytes novos |
| `WINDOW_OVER_THE_READ_CAP` | janela do W1 maior que 3600 s | encurtar a janela; uma leitura por janela de até uma hora |
| `GATE_SPAN_OVER_FAMILY_CAP` | portão maior que 900 s (gravação) ou 3600 s (leitura) | encurtar, ou usar `gate_not_before`/`gate_not_after` |
| `WINDOW_CROSSES_UTC_MIDNIGHT` | a janela atravessa 21:00 BRT | dividir em duas execuções |
| `WINDOW_ALREADY_UNUSABLE` | agora já passou do último início | nova janela; se já estava assinado, nova assinatura |
| `SIGNATURE_MODEL_NOT_IMPLEMENTED` | `signature_model` `GRID` ou `WEEK` | esses modelos não existem aqui; pedir a resposta individual do dono (`IND`) ou esperar o modelo ser construído |
| `PARAMETERS_FREE_TEXT` | `purpose_pt` ou `owner_summary_pt` com quebra de linha, caractere de controle, a palavra de assinatura ou 64 hex | reescrever em uma linha |
| `REVIEW_OR_WAIVER_MISSING_FOR_A_WRITE`, `REVIEW_OR_WAIVER_INVALID`, `REVIEW_OR_WAIVER_DOCUMENT_UNREADABLE` | gravação sem `review`, com `kind` errado ou sem o documento | apontar o parecer do Codex ou a decisão de dispensa do dono |
| `EVIDENCE_OF_A_REAL_REQUEST_MUST_BE_A_BOUND_SET` | pedido real citando arquivo solto | citar o diretório vinculado da execução (`"bound"`) |
| `EVIDENCE_SET_<CÓDIGO>` | o conjunto citado não confere (o código é o que o `status` daria) | conferir o conjunto citado com `status`; não editar nada |
| `EVIDENCE_SET_WITHOUT_A_VERIFIED_RECEIPT` | o conjunto citado não terminou com recibo verificado | citar a execução certa; uma recusa remota ou um resultado incerto não é evidência |
| `EVIDENCE_RECEIPT_OF_ANOTHER_HOST`, `EVIDENCE_SET_OF_THE_OTHER_MODE`, `EVIDENCE_SET_OF_ANOTHER_SEAL`, `EVIDENCE_SET_OF_ANOTHER_OPERATION`, `EVIDENCE_RECEIPT_SCHEMA`, `EVIDENCE_RECEIPT_OPERATION`, `EVIDENCE_RECEIPT_OF_OTHER_BYTES`, `EVIDENCE_OPERATION_NOT_IN_THIS_FAMILY` | o recibo citado não é desta operação, desta família (dos bytes selados dela), deste servidor ou deste modo | citar o recibo certo |
| `EVIDENCE_RECEIPT_NOT_COMPLETE` | recibo citado parcial | refazer a leitura; ou, decidido com o dono, `"accept_not_complete": true` (aparece na pergunta) |
| `PLAN_VALUE_NOT_THE_ONE_OF_THE_CITED_RECEIPT`, `PLAN_VALUE_WITHOUT_ITS_SINGLE_CITED_RECEIPT`, `CITED_PRECHECKS_OF_DIFFERENT_BOOTS` | um valor do plano não é o do recibo citado, ou não há exatamente um recibo daquela operação | copiar por ponteiro do recibo certo; citar um só precheck, o do boot da gravação |
| `FAMILY_REFUSES_THE_REQUEST_<CÓDIGO>` | o `authenticate()` da família recusou o request | o código é o da família (seção 3.4 do contrato do HOSTOPS01, ou a lista do W1); corrigir os parâmetros |
| `SSH_REFERENCE_CHANGED_SINCE_LAST_USE` | chave ou known-hosts mexidos depois do último uso | parar e relatar; não tocar nos arquivos |
| `TRANSPORT_REFERENCE_NOT_AN_EXECUTED_CONFIG` | a referência não é de um conjunto executado (ou foi editada) | apontar `REFERENCE` para um `DISPATCH.BOUND.json` que rodou |
| `SHEET_IS_NOT_THE_ONE_THE_OWNER_SAW` | o hash dado ao sign não é o da folha em disco | conferir `prepare.json`; nunca "consertar" a folha |
| `SHEET_WINDOW_NOT_DERIVED_FROM_ITS_UTC_FIELDS`, `SHEET_FIELD_NOT_DERIVED_FROM_THE_BOUND_FILES`, `OWNER_QUESTION_CHANGED` | a folha ou a pergunta em disco não são as que o prepare escreveu | parar e relatar; novo prepare em outro diretório |
| `OWNER_ANSWER_IS_NOT_THE_SIGNATURE` | a resposta passada ao sign não é a palavra literal | não é assinatura; nada a fazer no sign |
| `BOUND_SET_HOLDS_A_DIRECTORY_THAT_IS_NOT_ITS_OWN` | há um diretório a mais no conjunto (por exemplo `__pycache__`) | parar e relatar; não apagar para "fazer passar": descobrir quem o criou |
| `BINDER_CHANGED_SINCE_PREPARE` | binder ou selos editados depois do prepare | novo prepare, nova folha, nova pergunta |
| `PUBLISHED_BEFORE_THE_INTENT` | `created_at` anterior ao intent | usar a hora de criação do comentário certo |
| `CORE_NOT_FOUND`, `CORE_SEAL_NOT_ACCEPTED`, `CORE_FILE_SET`, `CORE_HASH`, `CORE_SUMS_INVALID`, `CORE_GENERATION_NOT_THE_SOURCES` | HOSTOPS02: o núcleo ao lado da operação não é o selado e aceito | refazer a cópia selada (10.1); núcleo novo = selo novo em `ACCEPTED_SEALS.json` |
| `CORE_ASSEMBLY_CHECK_FAILED`, `ASSEMBLY_RECORD_NOT_THE_BUILD` | o `build/` da operação não é o que o núcleo monta, ou o `ASSEMBLY.json` não descreve os bytes | não vincular; relatar ao autor |
| `EVIDENCE_FAMILY_NOT_AN_ACCEPTED_SEAL`, `EVIDENCE_OPERATION_NOT_IN_THIS_FAMILY` | o item de evidência aponta uma família não aceita, ou falta `family` para uma operação de outra família | corrigir `family` do item |
| `BIND_INPUTS_INVALID`, `BIND_INPUT_UNREADABLE`, `BIND_INPUT_NOT_USED`, `PLAN_INPUT_INVALID`, `PLAN_MEMBER_NOT_FROM_ITS_INPUT_FILE` | arquivo de entrada não previsto, ilegível, sobrando, marcador errado, ou membro digitado | `inputs` e marcadores `$input` como nos modelos |
| `GATE_WINDOW_ONLY_IN_MINUTES_TO_AVOID` | o portão só tem minutos a evitar | outra janela |
| `CATALOG_*`, `PROVISION_LEDGER_ROW_NOT_FOUND`, `RETENTION_TAG_NOT_THE_SIGNED_IMAGE`, `RELEASE_TREE_*`, `SCRIPT_NOT_THE_READMES`, `EPOCH_NOT_THE_RELEASES`, `LINUX_JOB_RECORD_*` | K2a: linhas, etiqueta, árvore da release ou registro do job Linux | conferir os recibos citados e os arquivos dados |
| `RELEASE_EVIDENCE_INCOMPLETE`, `RELEASE_NOT_VERIFIED_BY_A_FULL_PRE`, `RELEASE_PARENT_NOT_THE_ONE_THE_PRE_READ`, `RELEASE_FIELDS_<código>`, `RELEASE_MEMBER_NOT_THE_TOOLS`, `LINUX_PROOF_*`, `RELEASE_SUNDAY_*`, `BINDING_TOOL_MISSING` | K10: evidência (S1, A3, B1, W1, M2p), release, prova Linux ou portão de domingo | o código diz qual; `RELEASE_FIELDS_*` é a recusa da ferramenta `release_fields.py` |
| `READBACK_EVIDENCE_WITHOUT_A_BOOT`, `IMAGE_*`, `PLAN_ROWS_NOT_THE_ROWS_OF_A_CITED_RECEIPT`, `REVISION_NOT_THE_RELEASES`, `SIBLINGS_NOT_THE_SEALED_SIBLINGS`, `RELEASE_PLACE_NOT_THE_SIBLINGS`, `LIMITS_NOT_THE_SIBLINGS_FLOORS` | K11: boot, imagem/revisão, linhas sem recibo, release, irmãs | linhas nulas (observadas) ou copiadas de um recibo citado |
| `ACTIVATE_*`, `LIVE_PARENT_NOT_ACCEPTABLE_TO_A_WRITE`, `POLICY_NOT_VERIFIED_AT_THIS_GATE`, `OVERRIDE_FILE_NOT_THE_ONE_ACTIVATE_WRITES` | K6a: o M2p citado não é o PRE completo com linhas, ou o pedido não é o que ele renderizou, ou o portão não está em `valid_at` | citar o M2p certo; janela no instante verificado |
| `SPARE_*` | reserva: principal não assinado, de outra operação, com outros efeitos, janela antes do fim do principal, raiz sumida, já preparado, ou já tem reserva (`SPARE_ALREADY_BOUND_FOR_THIS_PRIMARY`) | 10.5 |
| `REVIEW_DOCUMENT_DOES_NOT_NAME_THESE_BYTES`, `OWNER_WAIVER_NOT_A_SIGNED_RECORD_FOR_THESE_BYTES`, `REVIEW_OR_WAIVER_MISSING_FOR_A_CONTAINER_RUN` | HOSTOPS02: o parecer não nomeia o selo e o programa destes bytes; a dispensa não é um registro do dono, anterior, destes bytes; o K11 sem `review` | apontar o parecer certo, ou a decisão registrada do dono (seção 2) |
| `LINUX_JOB_RECORD_NOT_OF_THESE_BYTES`, `SIBLINGS_TESTS_*`, `WORKER_OR_IMAGE_NOT_THE_ONES_OF_THE_CITED_READ`, `RELEASE_HOST_EVIDENCE_A4_NOT_CITED_AND_NO_REASON` | registro do job Linux de outros bytes; registro das irmãs ausente (REAL) ou de outros selos; trabalhador ou imagem diferentes da leitura W1 citada; K10 sem o A4 e sem motivo | seção 2 |
| `README_COMMAND_NOT_FOUND`, `DOCKER_ARGUMENTS_NOT_THE_READMES`, `REHEARSAL_RECEIPT_NOT_THE_ONE_A9_NEEDS` | K2a: o README da árvore não tem um bloco de comando legível, ou o comando dos efeitos não é o dele; o A6 dado ao A9 não é destes bytes, deste boot, desta imagem, deste script ou deste caminho, ou não está completo | conferir a árvore e o A6 |
| `CATALOG_WITHOUT_THE_CITED_4B_RECEIPT`, `CATALOG_4B_RECEIPT_NOT_ONE`, `CATALOG_4B_RECEIPT_NOT_THE_COMPLETE_REAL_ONE`, `CATALOG_EXPECTATION_NOT_THE_CITED_4B` | HOSTOPS01 readback/install: catálogo sem o A9 citado (REAL), dois recibos K2a, o recibo do ensaio ou um parcial, ou `NOT_YET` com o A9 citado | seção 2, HOSTOPS01 |
| `SEALED_COPY_SOURCE_HOLDS_A_SUPERSEDED_SEAL` | uma fonte da cópia selada tem um dos cinco diretórios com outro selo | usar só a cópia durável (10.1) |
| `GATES_*`, `STEP_RESUME_NOT_FOR_THIS_OPERATION`, `BINDING_TOOL_NOT_THE_ONE_OF_THE_PREPARE`, `CITED_RECEIPTS_NOT_FOUND_AGAIN` | `check --gates`: arquivo inválido, conjunto sem portões, família ausente, ferramenta mudada, recibos citados movidos | 10.4 |
| `SEALED_COPY_SOURCE_NOT_FOUND`, `SEALED_COPY_FILE_NOT_FOUND` | nenhuma fonte tem a operação, o núcleo ou um arquivo com o hash selado | dar a fonte que ainda tem os bytes selados |

## 8. Ensaio

Os dois comandos, como rodam (caminhos absolutos; o carimbo vem do relógio, por comando):

```zsh
TS=$(date -u +%Y%m%dT%H%M%SZ); S=/offline/optional-references; W=/offline/optional-work
/usr/bin/python3 -B "${S}/bind/rehearse.py" w1 --family "${S}/w1preflight/candidate" --workspace "${S}/bind/rehearsal-w1-${TS}" --real-reference "${W}/hostfacts01-fable-20261002/bound/DISPATCH.BOUND.json"; echo "exit=$?"
/usr/bin/python3 -B "${S}/bind/rehearse.py" precheck --family "${S}/hostops01/candidate" --workspace "${S}/bind/rehearsal-precheck-${TS}"; echo "exit=$?"
/usr/bin/python3 -B "${S}/bind/tests/runbook_blocks.py" "${S}/bind/rehearsal-runbook-${TS}" "${S}/w1preflight/candidate"; echo "exit=$?"
for K in catalog readback release activate; do /usr/bin/python3 -B "${S}/bind/rehearse.py" hostops02-${K} --hostops02 "${W}/fable-hostops02-tier0-20261002-r2" --hostops01 "${S}/hostops01/candidate" --w1 "${S}/w1preflight/candidate" --workspace "${S}/bind/rehearsal-hostops02-${K}-${TS}"; echo "exit=$?"; done
```

Cada ensaio trabalha numa cópia de rascunho da família, com transporte falso (alvo no domínio reservado `.invalid`,
arquivos-marcador no lugar da chave), dono `REHEARSAL_NOT_THE_OWNER`, resposta `REHEARSAL_NO_OWNER_ANSWER` (a
palavra `Assino` é recusada num conjunto de ensaio), e deixa `TRANSCRIPT.json`.
W1: prepare → sign com hora sintética → check → prepare do dispatcher pela linha de comando real, com o prefixo de
cache vazio (exit 2) → check de novo (`VALID_ALREADY_PREPARED`, exit 1) → publish-proof → resume com o transporte
**substituído** pelo arnês local da família (a fonte no servidor emulado de `test_w1_preflight_once.py`; o recibo
passa pelos bytes revisados do transporte com um filho local) → status → check (`VALID_GO_SPENT`).
HOSTOPS02 (`hostops02-catalog`, `-readback`, `-release`, `-activate`): no próprio processo, com relógios injetados nos instantes
do plano (as operações são datadas de 02/10 a 05/10), cópia selada, recibos citados produzidos pelas fontes seladas das
operações citadas nos servidores emulados das suas famílias, e cada conjunto até o recibo verificado: prepare → sign
(marcador) → check (com os portões, inclusive o parecer sintético do conjunto vinculado; e o veredito de um minuto a
evitar) → check antes do prepare do dispatcher (bloco 6) → prepare do dispatcher → publish-proof → check `--step resume`
(bloco 9) → resume com a fonte no servidor emulado da própria operação e a linha passando pelos bytes revisados do
transporte com um filho local → status. A cópia selada vem só da cópia durável (`W/fable-hostops02-tier0-20261002-r2`). Só
`check` e `status` passam também pela linha de comando (relógio real).
Precheck: até o prepare do dispatcher, e para. `--real-reference` só serve para mostrar que o binder recusa um
transporte real num ensaio. O terceiro comando roda literalmente os blocos zsh deste runbook que não são `host`
nem `manual`; os blocos `rede` rodam com um `gh` **falso** (um script do próprio ensaio, no `PATH` só dele, que não
contata nada e devolve uma URL e uma hora no formato que os blocos leem). Todos os blocos, inclusive o do resume,
passam por `zsh -n` (só sintaxe).

## 9. O que só uma execução real prova

- O `resume` pela linha de comando com ssh de verdade, e o recibo de um servidor de verdade. O ensaio nunca inicia
  o ssh.
- Os blocos com `gh` contra o GitHub de verdade (publicação do pedido, da âncora, do intent, da prova; id e
  `created_at`). No ensaio eles rodam com um `gh` falso. O binder não confere que o comentário existe.
- Que a chave e o known-hosts ainda têm os hashes fixados: o binder só faz `lstat`; quem lê é o prepare do
  dispatcher.
- A resposta do dono: o binder grava o que lhe é dito, e só aceita a palavra literal.
- O documento de revisão ou de dispensa: no HOSTOPS01 o binder só calcula o hash dele; no HOSTOPS02 confere que ele nomeia,
  como texto, o selo e o programa destes bytes (e, na dispensa, que é um registro de decisão do dono), mas o veredito escrito
  nele é a Fable que lê.
- Os requests das quatro operações do HOSTOPS01 com recibos reais: os testes vinculam precheck, provision,
  install_units e readback em modo REAL contra uma referência executada **sintética**, cada um citando o conjunto
  vinculado do anterior, e rodam o resume no servidor emulado da própria família; nenhum recibo real de precheck ou
  provision existe ainda. Que as linhas e os identificadores copiados sejam os do servidor no boot da gravação, só
  o precheck real diz.
- Os valores do plano que a tabela `PLAN_SOURCES` não cobre (layout, linhas do volume de dados, identidades das
  unidades, catálogo): o binder não os compara com os recibos.
- Três coisas que a pergunta mostra ao dono vêm do prepare e não são recalculadas pelo `sign` a partir dos arquivos
  do conjunto: o resultado e a completude de cada recibo citado, o sha256 do documento de revisão ou dispensa, e o
  selo da família (este é recalculado pelo `check --family` do bloco 4, antes do bloco 6). A janela, a finalidade, o
  modelo de assinatura, as contagens de candidatos, o tipo de revisão e os hashes de request, fonte, escopo e
  efeitos são recalculados. O bloco 3 só passa ao `sign` o hash que o prepare imprimiu (`prepare.json`): uma folha
  editada depois tem outro hash e é recusada.
- Que a frase de escopo gerada para o GO do W1 (`GO_SCOPE.txt`: moldura fixa em volta de citações do contrato e
  dos `SIDE_EFFECTS` da fonte) é a que o auditor e o dono aceitam: ninguém além do autor a leu.
- Leituras em grade (GRID) e assinatura semanal (WEEK): não existem neste binder.
- HOSTOPS02: que as quatro operações rodem no servidor como nos servidores emulados; os ensaios e os testes usam recibos
  sintéticos (produzidos pelas fontes seladas nos emuladores e ligados ao servidor do ensaio), relógios injetados e, para
  as linhas do volume de dados, os números dos emuladores do HOSTOPS (o emulador do W1 numera os dispositivos de outro
  jeito: o ensaio troca as três linhas antes de selar o recibo de novo). Os junit da prova Linux dos testes são entradas
  de teste, nunca prova. O registro do job Linux do K2a, do K11 e do K6a e o documento de revisão: o binder calcula o hash e
  confere que eles nomeiam estes bytes (seção 2); o conteúdo além disso é da Fable.

## 10. HOSTOPS02 no fim de semana: cópia selada, ordem, portões, o que conferir a olho, limites

### 10.1 A cópia selada (contrato K10, seção 6, passo 1) — uma vez, antes do primeiro prepare

Vincular e despachar só de uma cópia que tem apenas os arquivos que os selos listam. O binder a faz, conferindo cada
arquivo pelo hash selado. A fonte é a cópia durável `${HOSTOPS02_SOURCE}` (`W/fable-hostops02-tier0-20261002-r2`), que
tem todos os arquivos dos selos aceitos com o hash selado: nenhuma outra fonte é necessária.

```text
${PY} -B "${BIND}" sealed-copy --out "${HOSTOPS02_COPY}" --source "${HOSTOPS02_SOURCE}"
```

Conferir a olho: `SEALED_COPY_WRITTEN`; cinco diretórios (`core`, `catalog_init`, `install_release`, `epoch_readback`,
`activate`) com os selos da seção 1; `files_taken_from_a_later_source` vazio em todos. Uma fonte que tenha um desses cinco
diretórios com outro selo (um diretório de trabalho de um selo substituído, por exemplo a cópia de um verificador com o
K6a `3f0eea45…` ou o núcleo `c13ce685…`) é recusada inteira (`SEALED_COPY_SOURCE_HOLDS_A_SUPERSEDED_SEAL`): a cópia nunca é
refeita com bytes de um selo que não é mais aceito. Se o núcleo ou uma operação forem selados de novo, os selos novos
entram em `ACCEPTED_SEALS.json` por edição deliberada (e o manifesto do binder é refeito) antes do primeiro prepare.

### 10.2 A ordem do fim de semana

Cada linha é uma execução com os blocos 1a a 11; a coluna "cita" é o que entra em `evidence` (conjuntos vinculados e
terminados), "portão" o que `check --gates` exige antes dos blocos 6 e 9 (que o rodam sozinhos).

| Ordem | Pedido | Operação | Cita | Portão de envio (`GATES.json`) |
|---|---|---|---|---|
| 1 | A6 (sáb 17:00) | K2a, `plan.mode` REHEARSAL | S1, A3 | `codex_review` |
| 2 | A9 (sáb 17:30) e A9' (reserva, dom 08:30–19:00) | K2a, `plan.mode` REAL | S1, A3 (e `rehearsal` = A6, se já terminou) | `rehearsal` = conjunto do A6; `grid_read` = leitura W1 completa do mesmo boot, minutos antes (≤ 60 min); `codex_review` |
| 3 | B1 (dom 09:30) e B3 (dom 10:00) | HOSTOPS01 install_units, readback GATE | S1, A3, (B1), e o A9 pela família K2a (seção 2) | — |
| 4 | M2p (dom 12:30) | K11 PRE FULL | S1 | — |
| 5 | M1 e M1' (contra-assinados domingo, depois do recibo do M2p; enviados segunda 05:27) | K10 | S1, A3, A4, B1, W1 de domingo, M2p | `m0` = a leitura W1 M0 de segunda (`predispatch.py`), de novo antes do resume; `codex_review` |
| 6 | M2 (seg 05:38–06:25, depois do recibo do M1 ou do M1') | K11 POST | S1, M2p | `install` = conjunto do M1 (ou M1') completo com estes bytes |
| 7 | M3 e M3' (contra-assinados domingo, depois do recibo do M2p) | K6a | M2p | `readback_post` = conjunto do M2 completo, sem contêiner de verificação e sem sobra temporária; `codex_review` |

O prepare do M1 e do M3 só acontece depois do recibo completo do M2p (os dois o citam: `RELEASE_EVIDENCE_INCOMPLETE`,
`ACTIVATE_EVIDENCE_NOT_ONE_FULL_PRE`): a contra-assinatura do dono do M1, M1', M3 e M3' fica DEPOIS do recibo do M2p
(12:30) e da leitura W1 de domingo que o M1 cita, nunca às 12:00. O do M1' depois do sign do M1, o do M3' depois do sign
do M3 (a reserva cita o principal assinado). O M2 pode ser preparado e assinado domingo; o portão dele é avaliado segunda.
Os inícios dos portões do M3 e do M3' entram em `policy.valid_at` do M2p (`POLICY_NOT_VERIFIED_AT_THIS_GATE`).

**Assinaturas individuais que a grade da A1 não cobre (GRID não existe neste binder).** Os portões citam leituras W1 que
têm de ser conjuntos vinculados por este binder, cada um com o seu `Assino` (modelo `IND`, ou `PRE` assinado antes):
L4 (sáb, minutos antes do A9) ou L5 (dom, antes do A9'), o portão `grid_read`; L8 (dom à noite), a leitura W1 de domingo
que o M1 cita no prepare; M0 (seg 05:00), o portão `m0` do M1 (assinatura `PRE` na sentada de domingo). São quatro
toques do dono a mais que o plano não previa: pô-los no plano das sentadas, ou construir GRID sob o hash da A1 assinada.

### 10.3 O que conferir a olho no prepare (além da seção 3)

- Todas: `family` com o selo da operação e `family.core` com `73fb546b…c9b1`/`4c24c5cf…d0d6`; `hostops02.core.assembly_check.answer`
  `BUILD_EQUAL`; `hostops02.core.assembly.source_sha256` igual a `source_sha256`; `hostops02.core.unsealed_directories_skipped`
  vazio (é a cópia selada); `evidence[*].family` a família certa de cada recibo, `complete` verdadeiro; `hostops02.dispatch_gates`
  os da tabela 10.2; `hostops02.bind_inputs` os hashes e tamanhos dos arquivos aprovados (conferir com `shasum -a 256`);
  `review.names_these_bytes` (o documento nomeia o selo e o programa) e, na pergunta, a linha da revisão.
- A6/A9: em `EFFECTS.json` `mode`, `journal_root.path` e `is_the_real_journal_root`, `container.docker_config_variable` (a pasta
  da unidade só no REAL), `creates` (no ensaio, duas pastas em `/var/lib`), `epoch`, `success_outcome`;
  `hostops02.rules.release_tree.docker_arguments_are_the_readmes` (o binder comparou `container.docker_arguments` com as linhas
  336–339 do README, palavra por palavra) e `linux_job`; no A9, `rules.rehearsal_receipt` quando o A6 já terminou.
- M2p/M2: `success_criterion` (PRE: `EPOCH_DRY_RUN_PRE_ALL_OBSERVED_ALL_EXPECTATIONS_MET`; POST:
  `EPOCH_READBACK_POST_ALL_OBSERVED_ALL_EXPECTATIONS_MET`); `rules.rows_signed_from_cited_receipts`; `rules.siblings` (as três
  fontes irmãs com o selo aceito; `recorded_seal_is_the_accepted_seal` falso quer dizer que o `SIBLINGS.txt` do K11 registrou um
  selo anterior da irmã) e `rules.siblings_tests` (o registro da suíte do K11 ao lado das irmãs aceitas: obrigatório em REAL
  nesse caso); `rules.worker_and_image_compared_with` (as leituras W1 com que o trabalhador e a imagem foram conferidos, ou nulo).
- M1/M1': `rules.release_fields.expected_from_the_full_pre` (as três expectativas, do M2p); `rules.sunday_gate.failed` só
  `M0_IS_OF_THE_SAME_DAY_AND_NOT_OLDER_THAN_AN_HOUR`; `rules.host_evidence_complete` (falso: a pergunta traz o aviso do
  contrato) e `rules.provisions_cited` 2 (ou o motivo em `host_evidence_reason_pt`); `rules.linux_proof.decision`
  `LINUX_PROOF_ACCEPTED` e os hashes dos dois junit; `EFFECTS.json` `file.sha256` igual ao da release aprovada; na reserva,
  `hostops02.spare_of` com o rótulo, o pedido e o GO do principal e o caminho do registro da reserva.
- M3/M3': `rules.override_sha256` igual ao `effects.render.override_sha256` do M2p; os quatro valores em
  `EFFECTS.json` `recreate.environment`; `policy.content_digest_sha256` igual ao `policy_sha` do Act B.

### 10.4 Os portões de envio (`check --gates`)

`GATES.json`, escrito à mão com caminhos, sem nenhum hash: `{"schema": "BIND_ONCE_DISPATCH_GATES_V1", <portão>: {"bound":
"<conjunto>", "family": "<família>"}, ...}` com os portões da tabela 10.2, e, nas gravações, `"codex_review": {"document_file":
"<arquivo>", "form": "BOUND_SET" | "CANDIDATE_REVIEW_SUFFICES"}` (A1, seção 8): `BOUND_SET` = o parecer escrito do Codex que
cita o hash deste pedido e o do payload final (os dois aparecem só depois do sign: `sign.json`); `CANDIDATE_REVIEW_SUFFICES` =
o escrito dele de que o parecer sobre os bytes não vinculados basta para esta operação, que tem de nomear a operação, o selo e
o programa (o binder confere os hashes no texto e registra a forma; a frase "basta" é a Fable que lê). Uma gravação com
`review` `OWNER_WAIVED` não tem esse portão. Não existe mais `reboot_pending_order`: com reinício pendente o portão do A9
falha sempre (`K2A_GRID_READ:NO_REBOOT_PENDING`); manter o reinício pendente e inicializar o catálogo é ato próprio do dono,
com leitura escrita do Codex e outra folha (A1, 6.2), fora deste binder. A leitura do portão do A9 tem de ser completa
(`KNOWN_COMPLETE`, seções runtime, data_volume, security_controller e clock `COMPLETE`: `K2A_GRID_READ:COMPLETE_READ`), e o
recibo do A6 tem de ser destes bytes, do mesmo boot, da mesma imagem, do mesmo script e do mesmo caminho no contêiner.

Os blocos 6 e 9 rodam o `check` sozinhos para todo conjunto do HOSTOPS02 e param sem `VALID_WINDOW_OPEN` (bloco 6) ou sem
`VALID_RESUME_ALLOWED_BY_THE_GATES` (bloco 9, `--step resume`); param também quando a folha lista portões e o `run.env` não tem
`GATES`. Um minuto a evitar (:05–:07, :10–:25, :35–:37) é veredito de não-envio: `VALID_BUT_NOW_IS_A_MINUTE_TO_AVOID` (exit 1)
no bloco 6 e `VALID_BUT_RESUME_GATES_NOT_MET` no bloco 9; esperar o minuto seguinte utilizável e rodar o bloco de novo (antes
do bloco 6 nada foi criado). Ler `dispatch_gates.failed`: vazio é o único "pode". Um conjunto de outro modo, de outro
servidor, sem recibo verificado, ou um arquivo solto num conjunto REAL, falham com o código do binder. Para K10 o `check`
precisa de `--family` (roda a ferramenta selada `binding/predispatch.py`, a mesma do prepare) e relê os recibos citados nos
caminhos do `PARAMETERS.json`: não mover os conjuntos citados entre o prepare e o envio. No K10 o `--step resume` só deixa
seguir de `not_before` + 120 s até 15 s antes do último início.

### 10.5 A reserva (A9', M1', M3')

A reserva é um segundo conjunto vinculado, com rótulo, janela e GO próprios, os mesmos bytes e os mesmos efeitos, que nomeia
o principal (`spare_of`). **Uma reserva só por principal**: o prepare da reserva grava, ao lado do diretório do principal,
`<diretório do principal>.SPARE.json` (criação exclusiva); uma segunda reserva do mesmo principal é recusada
(`SPARE_ALREADY_BOUND_FOR_THIS_PRIMARY`), e o portão da reserva exige que esse registro a nomeie
(`SPARE:NOT_THE_REGISTERED_SPARE_OF_ITS_PRIMARY`). Nunca apagar nem mover esse arquivo.

O `check` da reserva só deixa enviar se o principal nunca foi enviado (A1, definição de "despachado"): a raiz de uso único
dele (a da folha, com a identidade assinada) está vazia; ou — só no K2a e no K6a — ele foi só preparado (o claim
`.go-<sha256 do GO do principal>.claim` e a tentativa só com `intent.json`, sem `spawn.claim`) e o último início dele já passou:
o resume do principal é recusado antes do `spawn.claim` (`WINDOW_WITH_WATCHDOG`), então ele não pode mais ser enviado.
Qualquer outro conteúdo (enviado, recusado no servidor, incerto, um claim apagado com a tentativa no lugar) impede a reserva.
**K10 mantém a regra estrita do próprio contrato (passo 15; ferramenta `predispatch.py`, papel `spare`):** qualquer conteúdo da
raiz do principal (o claim nasce no prepare do dispatcher dele, bloco 6, antes da publicação e de qualquer envio) impede a
reserva. Uma raiz do principal movida ou apagada impede a reserva (`SPARE_PRIMARY_CLAIM_ROOT_NOT_FOUND`). A pergunta ao dono
diz qual regra vale. Depois que o claim do principal existe: tirar a configuração e os blobs da reserva do diretório de
despacho (contrato K10, passo 15) — o binder não faz isso.

### 10.6 Limites conhecidos (o binder não cobre; o operador e os signatários sim)

- O dispatcher não olha nenhum portão: os blocos 6 e 9 rodam o `check` antes de chamá-lo e param sem o veredito certo. Rodar
  o `dispatch_once.py` à mão, fora dos blocos, pula os portões: nunca.
- Leitura em grade (GRID) não existe neste binder: as leituras W1 que os portões e o M1 citam têm de ser conjuntos vinculados
  por ele (modelo `IND` ou `PRE`), com assinatura própria (10.2).
- K11: o binder não roda os testes das irmãs; exige (em REAL, quando o `SIBLINGS.txt` nomeia selos anteriores) um registro que
  nomeie os selos aceitos, e confere os hashes do `SIBLINGS.txt` contra as fontes aceitas ao lado. Os limites `render_ms` e
  `quick_ms` são digitados (3000 e 1500, DESIGN 4b) e não são comparados com nada.
- K6a: depois de um M2 incerto ou expirado, o contrato admite o M3 só depois de uma leitura que mostre nenhum contêiner
  `hostops02-k11-*`; o binder só conhece o portão do M2 completo, e recusa: essa exceção é decisão do dono, com outra leitura.
- O conteúdo de um parecer (o veredito, a frase "basta") é a Fable que lê: o binder confere só que o documento nomeia, como
  texto, os hashes destes bytes (ou deste pedido e deste payload final).
- O B1 que cita o A9 registra a dependência; o binder não exige a citação no install_units (só no readback REAL que espera o
  catálogo `INITIALISED`).
- A janela curta do GO (A1, seção 5) é fixada no prepare, dentro da faixa do dono (`gate_not_before`/`gate_not_after`), e
  aparece na pergunta: não é refeita depois da assinatura. O prepare recusa um portão com menos de três minutos utilizáveis
  fora dos minutos a evitar (`GATE_WINDOW_ONLY_IN_MINUTES_TO_AVOID`).

## 11. K9 (revisão 4 do binder): K9R e K9W

Vale só depois que `ACCEPTED_SEALS.json` tiver, por edição deliberada, as três entradas de `ACCEPTED_SEALS.K9-TEMPLATE.json`
(K4-E0, K9R, K9W, com os selos revisados). Editar esse arquivo muda a identidade do binder: toda folha preparada antes recusa no
sign (`BINDER_CHANGED_SINCE_PREPARE`). Editar antes de vincular, nunca entre um prepare e o seu sign. A cópia selada (10.1)
passa a exigir os três diretórios numa das raízes `--source`.

**Ordem.** (1) E0 (K4) e K3-K9 enviados; (2) a leitura TREE (K9R, modo TREE) vinculada citando o recibo da E0: o binder confere
que o executor k9 entregue pela E0 é o `runner_sha256` das constantes; (3) com o recibo TREE completo, as folhas do dia, cada
uma citando esse recibo (papel `TREE`, recomendado) e copiando dele por `$from` as linhas e o boot. Um reinício invalida a TREE.

**Parâmetros de um pedido diário K9** (o resto como na seção 2, núcleo; `review` obrigatório; `owner_summary_pt` proibido, o
texto é fixo por operação K9):

- `k9_grid`: `G18` ou `G19` (NOTE 5.2). `not_before`/`not_after`: exatamente a linha da grade para (dia, operação, vaga); sem
  `gate_not_before`/`gate_not_after` (o portão é a janela).
- `plan.constants`: `{"$from": {"evidence": "TREE", "pointer": "/effects/constants"}}`; `plan.parent_rows.<days|source_root|secrets|tools|claims>.rows`:
  `{"$from": {"evidence": "TREE", "pointer": "/items/directory:<DAYS|SOURCE_ROOT|SECRETS|TOOLS|CLAIMS>/observed_rows"}}`;
  `plan.evidence_boot_id_sha256`: `{"$from": {"evidence": "TREE", "pointer": "/boot_id_sha256"}}`.
- `plan.attempt_key`: sha256 do JSON canônico `[época, dia, fase, operação]` (o binder recalcula). `plan.run_not_after`: o da
  grade em isoformat UTC (`+00:00`): de um `*_result`, o do lançamento que ele lê; de um lançamento K9W, o da sua linha; senão null.
- POLICY (`policy_read`): as linhas das pastas da política e da release por `$from` de recibos citados de K11 POST, K6a ou K10 do
  mesmo boot.
- K9W `bind`: `plan.bind` = `{namespace R2D2-V2-DIAG-R4-<D>, cutoff_at, phase_windows, owner_order_text, owner_order_sha256}`,
  os valores da grade (NOTE 5.3/5.4); `owner_order_text` é o texto ASCII dos bytes canônicos da ordem; o binder refaz os bytes e
  compara (as regras do K9W foram casadas com o selo 165330a6…; um selo novo exige conferir o bloco K9W de `bind_once.py`).
- Colocação (decisão 6 do Codex): a raiz das fontes fica em `/var/lib/c3po/r2d2-v2-source-20261005`; nenhuma cadeia K9 ou K4-E0 tem
  open_root; o binder confere os caminhos de `constants.placement` (bloco PLACEMENT de `bind_once.py`) e recusa bytes selados com
  a colocação N-8 (`K9_CONSTANTS_NOT_THE_COMPILED_ONES`, `K9_PROGRAM_NOT_OF_THIS_PLACEMENT`).
- RESERVA (`slot` `SPARE`): só com `spare_of` apontando o conjunto assinado do PRINCIPAL da mesma operação, dia e grade; o
  `check` da reserva confere que o principal nunca foi enviado (10.5, regra do K2a/K6a: preparado e não enviado depois do último
  início também conta como nunca despachado).

**K4-E0 e K3-K9** (uma vez por época, faixa da E0: 17:38–20:30 BRT de seg 05/10 a qui 08/10). K4-E0: `inputs.runner` = o arquivo
do executor k9 (o binder lê os bytes; `plan.runner.content_b64/sha256/bytes` por `{"$input": "runner", "as": "b64"|"sha256"|"bytes"}`;
`path` = `.../tools/k9_runner-<sha256>.py`), o hash tem de ser o `runner_sha256` da semana (compilado no binder); `parent`
(revisão 4 da K4-E0: as linhas de /, /var, /var/lib) e o boot por `$from` de UMA pré-checagem citada (`/items/chains/VAR_LIB/rows`,
`/items/boot/boot_id_sha256`). K3-K9 (regras provisórias, bloco `K3-K9 PLUG`): cita a E0, a releitura K11 POST e uma leitura TREE do
mesmo boot; `source_rows` por `$from` da TREE, `worker_container_id` por `$from` da POST. Em REAL os dois exigem o registro do job
Linux (`linux_job`).

**O que o binder recusa** está em `DESIGN_REV4.md` (seção 2), um código constante por regra. O que ele não cobre: a revisão de
cada pedido pelo Codex e pela Fable; o K9W não foi vinculado de ponta a ponta nos testes (bloco `K9W PLUG` de `bind_once.py`);
os blocos zsh da seção 3 valem para K9 como para os demais HOSTOPS02.


## Candidata rev 4: K8 e documentos verificados

K8 exige `k8_document_sets`: objeto com exatamente as janelas de `plan.windows`. Cada janela contém `directory` (saída completa de `capacity_day_documents.py day`, com SHA256SUMS e SUMMARY.json) e `chain_directory` (os sete documentos assinados que os pins dessa janela nomeiam). Os bytes são lidos e verificados, copiados para área temporária privada e conferidos novamente pelo verificador offline fixado por hash. Nenhum código do diretório recebido é executado. Cada contrato, registro, GO, config e view precisa ser exatamente o arquivo que a entrega carrega. Cada REQUEST precisa citar o hash do mesmo contrato e config. NOT_CHECKED, saída parcial, janela ausente ou diferente recusam.

Distribuir `k8_verifier/` junto deste binder; o hash de sua listagem fica compilado no binder. O verificador usa o Python que executa o binder, com as dependências de calendário do programa offline. Dependência ausente ou versão incompatível recusa; não habilita uma dispensa. A verificação reconstrói a saída e sua cadeia; os dois hashes dos arquivos de entrada originais permanecem NOT_COMPARED, como declara a ferramenta. Não prova assinatura do dono, recibo do host ou GO.

Não integrar famílias nem substituir ACCEPTED_SEALS a partir desta candidata. Os testes de regras usam cópias locais e selos de fixture expressamente separados; não são aprovação das famílias ou do conjunto real.
