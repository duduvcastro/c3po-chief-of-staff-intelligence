# R2D2 V2 — Rodada ao vivo de earnings (18:00 NY): runbook do produtor (F385-8)

Estado: passo 2 do F385-8 na PR #385 (branch `fable/v2-data-producers`). Nada aqui ativa coleta: os produtores
ficam OFF por padrão (`C3PO_R2D2_V2_PRODUCERS_ENABLED`), nenhuma rodada real corre antes das três assinaturas,
do rito de prontidão e da release do coletor. Este documento descreve o procedimento; a autorização é da mesa.

## 1. O que a rodada faz

1. Lê o inventário de episódios vivos do coletor (registros `ledger.research` com `status = OPEN`, os dois braços,
   exatamente os episódios a que o coletor aplica `EARNINGS` / `EARNINGS_OBSERVATION_FAILED`), pelo mesmo store do
   worker (`r2d2_v2_shadow_epochs`, hash do estado conferido), ou de um arquivo JSON explícito.
2. Consulta o provedor **só para os nomes vivos** (`produce_earnings` com a lista causal vazia, `live_symbols` e
   `live_lookback` = [menor `opened_at`, maior `maturity_at`] em datas NY; o produtor alarga a consulta do
   calendário em 15 dias após a maturidade).
3. Relê o documento gravado, confere o sha256 e o entrega ao emissor (`r2d2_v2_round_emitter`): recibo retido da
   rodada (`round_id` = sha256 do núcleo), uma janela por instrumento, um envelope por fato conhecido dentro da
   janela (inclusive fatos anteriores à sessão da rodada, vindos de `evidence.known_events`), ou um
   `EARNINGS_OBSERVATION_FAILED` por instrumento indisponível/inválido/não consultado; validação de cada envelope
   **antes** da publicação; publicação atômica; quarentena do que foi recusado.
4. Grava o recibo de execução (`rounds/<sessão>.<round_id>.run.json`) que vincula inventário (hash dos bytes),
   documento (sha256) e recibo da rodada.

## 2. Agenda

- Uma execução por sessão oficial XNYS, às **18:05 America/New_York**, por timer externo no host do produtor
  (`TZ=America/New_York`, cron `5 18 * * 1-5`). Nunca pelo worker do coletor.
- O runner recusa antes das 18:00 NY e no fechamento oficial ou antes dele (em fecho antecipado a regra das 18:00
  prevalece); recusa data que não é sessão (feriado, fim de semana: não há rodada).
- Sessão pretendida: `--session-date auto` = data NY do instante de início. Execução atrasada depois da
  meia-noite NY: `--session-date <sessão pretendida>` (a rodada mantém a sessão pretendida e o recibo real; o
  coletor aceita `round_received_at` posterior, desde que ≥ 18:00 NY da sessão e > fechamento oficial).
- Segunda rodada para a mesma sessão só com `--repeat` (recomeço após falha parcial). Os fatos mantêm
  `earnings_event_id` e `revision_sha256`; só o `round_id` e os `event_id` mudam; o recibo de execução lista as
  rodadas anteriores.

```
C3PO_R2D2_V2_PRODUCERS_ENABLED=true python -m app.r2d2_v2_round_runner --epoch <época> [--root <raiz>] [--session-date auto|AAAA-MM-DD] [--repeat]
```

## 3. Saídas (tudo privado: diretórios 0700, arquivos 0600, sob a raiz que o coletor lê)

| Caminho | Conteúdo |
|---|---|
| `events/<event_id>.<self_sha256>.json` | a fita que o coletor lê (`V2_SHADOW_SOURCE_EVENT_V2`) |
| `rounds/<sessão>.<round_id>.json` | recibo retido da rodada (`V2_EARNINGS_ROUND_RECEIPT_V1`), com a lista do que foi publicado e quarentenado |
| `rounds/<sessão>.<round_id>.run.json` | recibo de execução (`V2_EARNINGS_ROUND_RUN_V1`): inventário, documento, rodada, rodadas anteriores |
| `documents/<sessão>/round-<início>/earnings.json` | documento do produtor (`V2_EARNINGS_COMPONENTS_V2`) que originou a rodada |
| `quarantine/<sessão>/<event_id>.<sha256>.json` | envelopes recusados pela validação prévia (`V2_EARNINGS_ROUND_QUARANTINE_V1`, com o código) |
| `quarantine/<sessão>/<arquivo>.purge.json` | recibo assinado de remoção (`V2_EARNINGS_QUARANTINE_PURGE_V1`) |

O coletor lê apenas `events/` e ignora nomes iniciados por `.`; `rounds/`, `documents/` e `quarantine/` nunca
entram na fita (provado no teste de integração com a `FileShadowSource` real).

## 4. Procedimento de quarentena

Um único arquivo inválido em `events/` faz o coletor descartar a fita inteira; por isso o emissor valida antes de
publicar e o que falha vai para a quarentena. A quarentena é evidência, não lixo.

1. **Auditar** (só leitura, permitido com os produtores OFF):
   `python -m app.r2d2_v2_round_runner --audit-quarantine [--root <raiz>]` → uma linha por arquivo com
   sessão, código, `round_id`, `event_id`, instrumento, tipo e sha256 dos bytes; arquivos ilegíveis aparecem como
   `UNREADABLE`; recibos de purga como `PURGE_RECEIPT`.
2. **Classificar** a causa pelo código:
   - defeito do emissor ou do produtor (`ENVELOPE_*`, `PROVENANCE_*`, `REVISION_SHA_MISMATCH`, …) → corrigir o
     código, nova rodada com `--repeat`; o fato correto entra pela nova rodada;
   - relógio do provedor anterior ao início da rodada (`AT_BEFORE_ROUND`) → o fato será observado na rodada
     seguinte; registrar;
   - fato fora da janela (`EVENT_OUTSIDE_WINDOW`) → não é observação dos episódios vivos; registrar.
   **Nunca** mover um arquivo da quarentena para `events/` à mão, nem editar um envelope.
3. **Remover** um arquivo por vez, só de `quarantine/<sessão>/`, com assinatura e motivo:
   `python -m app.r2d2_v2_round_runner --purge-quarantine <sessão> <arquivo> --signed-by <quem> --reason "<motivo>"`.
   O recibo `<arquivo sem .json>.purge.json` (sha256 dos bytes removidos, código, `round_id`, assinante, motivo,
   instante) é gravado **antes** da remoção; caminho com `/`, nome oculto, sessão inválida, arquivo fora da
   quarentena ou symlink são recusados.
4. **Publicar** na PR #348 (canal de auditoria cruzada) o hash do recibo de purga sempre que a quarentena tocar
   uma sessão em curso, e conferir a fita na sessão seguinte (`FileShadowSource.last_event_diagnostics == []`).

## 4-bis. Commit de rodada, recuperação e exclusão (reparos F385-8-A/B/C/D)

- **Commit que o leitor respeita:** antes do primeiro link a rodada grava um journal (`rounds/<sessão>.<round_id>.journal.json`, com o núcleo do recibo e os arquivos planejados com seus temporários) e um **arquivo-guarda** visível em `events/` (`ROUND-COMMIT-<round_id[:16]>.json`, esquema `V2_EARNINGS_ROUND_COMMIT_GUARD_V1`) que **não é um envelope válido**: enquanto ele existir, o leitor devolve zero eventos e um diagnóstico — nunca uma rodada pela metade. Os envelopes são preparados ocultos (`.stage-*.tmp`), linkados um a um, o diretório é sincronizado, temporários e guarda são removidos, o recibo é gravado e o journal apagado.
- **Recuperação:** toda execução começa por `recover_rounds` (também `--recover`, sob a mesma exclusão): um journal sobrevivente é **concluído** a partir dos bytes em staging (recibo `commit = recovered`) ou, se algum temporário se perdeu, **desfeito** (finais da rodada removidos, recibo `commit = rolled_back` com a lista do que faltou). A guarda só sai no fim. Nenhuma rodada nova é publicada enquanto houver journal pendente (`PENDING_ROUND_REQUIRES_RECOVERY`).
- **Capacidade como o leitor conta:** o leitor conta **todas** as entradas de `events/` (staging e guarda incluídos) antes de ignorar o staging; o emissor exige `entradas + 2 × novos + 1 ≤ 4096` antes de qualquer escrita; nome já presente com bytes idênticos não é arquivo novo (reemitir uma rodada custa zero); o recibo registra `new_files` e a contagem efetiva `events_in_tape_after`.
- **Exclusão entre processos:** `rounds/.lock` (flock exclusivo) do início da recuperação ao commit; uma segunda execução é recusada com `ROUND_LOCKED` antes de qualquer chamada ao provedor.
- **Symlinks:** inventário e purga da quarentena só alcançam diretórios e arquivos por descritores abertos com `O_NOFOLLOW` (ancestrais incluídos); um symlink em qualquer ponto aparece como `SESSION_DIRECTORY_REFUSED`/`FILE_REFUSED`/`QUARANTINE_DIRECTORY_REFUSED` e a purga é recusada, sem ler, gravar ou remover fora da quarentena.
- **Bytes truncados na recuperação (A-R1):** um temporário ou final cujo hash não é o planejado nunca é aceito nem mantém a fita refém: a recuperação move o arquivo para `rounds/recovery/<round_id>/` (0700/0600) como evidência, desfaz os finais da rodada atrás da guarda, libera a fita e grava o recibo `commit = rolled_back` com `recovery.corrupt` (esperado × observado, caminho da evidência). A rodada pode ser reemitida.
- **Quarentena antes da fita e recibo já retido (A-R2):** os registros de quarentena são gravados **antes** do journal e da guarda; o journal lista cada um (nome, código, sha256) e a recuperação os confere no disco e os lista no recibo (nunca zera a contagem). Se o recibo retido já existe (crash após o recibo), a recuperação **não o reescreve**: só remove temporários/guarda e o journal (`commit = already_retained`).
- **Leitura integral (D-R1):** todo arquivo que o emissor, o inventário ou a purga leem é lido inteiro, com o tamanho conferido antes e a identidade conferida depois; um arquivo acima do teto (`READ_LIMIT_BYTES`, 64 MiB) é `FILE_TOO_LARGE`: o inventário o marca `FILE_REFUSED` e a purga o recusa e o preserva. Nenhum hash de prefixo.
- **Identidade de rodada usada uma vez (A-R3):** uma identidade cujo recibo retido diz `rolled_back` está **encerrada**: reemiti-la é recusado antes de tocar a fita (`ROUND_IDENTITY_CLOSED`); usa-se um novo instante (nova identidade). Na recuperação, `already_retained` só vale com recibo de commit completo **e** todos os finais presentes e íntegros; caso contrário a tentativa é desfeita atrás da guarda (zero, nunca subconjunto) e recebe um recibo de tentativa próprio (`<sessão>.<round_id>.attempt-<início>.json`), sem reescrever o recibo original.
- **Devolução sem sobrescrita (D-R3):** quando a purga recusa o arquivo reclamado (p.ex. acima do teto), ele volta ao nome visível por `link` sem sobrescrever; se um substituto surgiu sob esse nome, a reclamação fica (`CLAIM_LEFTOVER`) e o substituto é preservado, com o conflito reportado (`…_CLAIM_KEPT:<nome reclamado>`).
- **A-R4 — final inverificável na recuperação é inconsistência, nunca erro sem disposição** (Codex 5576042705): na recuperação, cada final planejado pelo journal é verificado por leitura integral (tamanho ≤ 64 KiB, identidade estável durante a leitura, arquivo regular); qualquer falha de verificação (`FILE_TOO_LARGE`, `FILE_CHANGED_DURING_READ`, `NOT_A_REGULAR_FILE`, erro de E/S) recebe a mesma disposição de um final corrompido: a rodada é desfeita atrás da guarda (zero, nunca subconjunto), os bytes inverificáveis vão para `rounds/recovery/<round_id>/` como evidência, o recibo original permanece intacto, um recibo de tentativa (`<sessão>.<round_id>.attempt-<início>.json`) registra `rolled_back` com `recovery.corrupt[].observed`/`evidence`, e a identidade fica **encerrada** por esse recibo (qualquer recibo `rolled_back` da identidade a encerra). Saída verificável: `--recover` (idempotente: a segunda passagem não encontra journal e não reescreve nada) e depois `--repeat` para uma rodada em novo instante; o leitor passa de `SOURCE_SIZE_LIMIT` (fita recusada inteira) a zero eventos limpos e lê a rodada nova.
- **A-R5 — nunca desfazer em aberto** (Codex 5576362466): uma rodada que já tinha completado (guarda retirada na publicação) e precisa ser desfeita na recuperação (final inverificável, final ausente, identidade encerrada) tem a **guarda rearmada antes** de mover ou remover qualquer final (`_arm_guard`: mesmo nome `ROUND-COMMIT-<round_id[:16]>.json`, com `rearmed_at`), mantida se a recuperação for interrompida nessa fronteira (o leitor continua recusando a fita inteira; a retomada reconhece a evidência já movida sem movê-la de novo) e retirada só quando o desfazer está completo. Contraprovas: leitor logo após a evidência ser preservada, após um crash nessa fronteira e entre cada remoção → zero eventos **com** diagnóstico; retomada → zero limpo; novo instante lido normalmente.
- **Identidade na purga (D-R2):** a purga primeiro **reclama** a entrada do diretório renomeando-a para um nome oculto `.claimed-<uuid>.json` (atômico, desconhecido de qualquer escritor) e só então lê, hasheia, grava o recibo (com o inode reclamado) e remove **esse** inode; um escritor que substitua o nome visível depois da reclamação mantém o seu arquivo. Uma purga que morra entre a reclamação e a remoção deixa a entrada oculta, que o inventário reporta como `CLAIM_LEFTOVER` (renomear de volta à mão, com recibo).

## 5. Invariantes

- Nenhuma chamada ao provedor antes das guardas de agenda (18:00 NY, fechamento oficial, sessão válida, rodada
  única por sessão salvo `--repeat`).
- `round_received_at` é o instante real de início da rodada; `round_id` é o hash do que se sabia antes de publicar;
  nada é datado para trás.
- `earnings_event_id = ern:<instrument_key>:<event_date>` é estável entre rodadas; data remarcada = fato novo
  (o provedor não expõe chave de período), declarado como limitação.
- O token do provedor nunca sai do fetcher: não aparece em arquivos, logs, recibos ou mensagens de erro.
- Nada aqui decide admissão, saída ou certificação; o produtor relata fatos e o próprio veredito.
