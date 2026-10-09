# F2_SERIES_V1 — contrato curto (diferenças em relação à F1)

> **Variante 09/10 (sexta).** Esta cópia deriva EXATAMENTE da rev 3.3 selada (`fable-f2-series-20261008-rev3_3`, SHA256SUMS `f077c293…`, intocada). Onde o texto abaixo cita valores de 08/10 (pregão, slots, cortes, raízes, unidades, operação, época, Emenda 7 da A2), **valem os da seção "Variante 09/10" no fim deste arquivo**; o resto (guardas, B1–B4, régua, orçamentos, conjunto elegível, `age`) é o da rev 3.3 sem mudança.

**SOURCE_DELIVERY_ONLY / OPERATION_HOLD.** Fonte e testes locais. Não é folha, assinatura, runtime aceito, prontidão, capacidade, E6 nem GO. Nada aqui foi executado no servidor ou no provedor. Vínculo documental: Emenda 7 (`amendment7_sha256` + `amendment7_signature_sha256` = sha dos bytes ORIGINAIS da assinatura, que viajam no BOUND e são validados no bind, no install e no runtime — ver Revisão 3). O registro documental não é assinatura criptográfica.

Base: família F1 `codex-f1-provider-diagnostic-20261008-r1` (selo F1 `2b37cbf1…` no recibo; SHA256SUMS F1 listado no RUNBOOK). Reaproveitados sem mudança de bytes: `reference_extract.py` (`e50e2263…`) e `REFERENCE_PROVENANCE.json` (`e8ae6e38…`). Reaproveitados por mecanismo (código adaptado): JSON canônico estrito, `Hold`/código público fixo, caminhada por descritores com O_NOFOLLOW, `age` 1.3.2 (`eb7dd1b5…`) executado por `/proc/self/fd`, destinatário da Fable `age1knek…r8x0`, pacote USTAR em memória + inventário, escrita O_EXCL 0600, SIGALRM + relógio monotônico, leitura `read1` com limites, contagem de presença idêntica à readiness_probe P / F1 (`_distinct`, `_bar` pinados).

| Tema | F1 | F2 |
|---|---|---|
| Família / operação | `F1_PROVIDER_DIAGNOSTIC_V1` / `GO_READ_PROVIDER_DIAGNOSTIC_EMENDA6_ONCE_01` | `F2_SERIES_V1` / `GO_READ_PROVIDER_BULK_SERIES_EMENDA7_20261008` |
| GETs | 2 (lista de símbolos + bulk 07/10) | **1 por slot**: só `/api/eod-bulk-last-day/US?date=2026-10-08&fmt=json`. Lista de símbolos **nunca** chamada. Sem retry/catch-up. |
| Elegíveis | registry ao vivo | **Conjunto FIXO** `ELIGIBLE_SET.json` (5.784 nomes, SHA256 `b24ffe6f…`), pinado no REQUEST; ver "Elegíveis" |
| Régua | 95/100, piso 4.000 (só descritiva) | Mesma: PASS ⇔ `eligible ≥ 4000` e `100·present ≥ 95·eligible` (presença, como a probe P). Usáveis/conflitos são diagnóstico. |
| Janela | 17:26–17:33 BRT, uma tentativa | 8 slots: 21:26, 21:56, 22:26, 22:56, 23:26, 23:56 (08/10) e 00:26, 00:56 (09/10) BRT = 00:26…03:56Z de 09/10 |
| Relógio | janela da folha | Início aceito em [slot−2 s, slot+60 s]; início ≥ 00:58 BRT (03:58Z) recusado; recebimento tem de terminar < 01:00 BRT (04:00Z) |
| Orçamento | 120 s (60 rede + 60 cifra) | 120 s total; rede+análise ≤ 75 s; socket ≤ 30 s; cifra no restante |
| Área privada | raiz eleita única, claim único | Raiz da campanha `/var/lib/c3po/f2-series-20261008` (0700 root); **subdiretório próprio por slot** `<raiz>/<slot>/`; ledger append-only `campaign.ledger` com flock, uma linha por slot; slot já no ledger ou diretório existente = recusa; marcador `REVOKED` = recusa |
| Credencial | env `F1_PROVIDER_TOKEN` (montado por `sed` no ssh) | **Nunca em argv/env/log**: o próprio processo lê `C3PO_EODHD_API_TOKEN` do arquivo `/var/lib/c3po/r2d2-v2-k9-20261005/secrets/provider.env` (regular, nlink 1, dono = euid, sem bits 077, ancestrais seguros) |
| Disparo | ssh manual da Fable | `systemd-run --on-calendar=<UTC exato> --timer-property=AccuracySec=1s`, uma unidade transitória por slot, sem Restart/Persistent; só slots com margem ≥ 180 s |
| Documentos | request, owner, amendment_signature, election, runtime, review | **Rev 3:** request, owner, amendment_signature (bytes ORIGINAIS da Emenda 7), election, runtime, review — mesmo conjunto da F1 |

## Efeito permitido por slot

Recusa sem efeito (exit 3, nenhuma escrita, zero GET) se: slot desconhecido, fora de [slot−2 s, slot+60 s], ≥ 00:58 BRT, documentos/assinatura/revisão/elegíveis/fonte/selo inválidos, token indisponível, raiz não exclusiva, `age` divergente, `REVOKED`, ledger ocupado, slot já reclamado. Depois do claim, o slot está consumido: qualquer falha é `SLOT_HOLD` (exit 2) com cifra e recibo quando possível; nunca há segunda tentativa do mesmo slot.

Escritas permitidas, somente sob a raiz da campanha: `campaign.ledger` (append), `<slot>/` (mkdir 0700), `<slot>/slot.claim`, `<slot>/bulk-series.age`, `<slot>/RESULT.public.json` (todos 0600, O_EXCL).

Privado (cifrado): `bulk.raw` (corpo cru), `bulk-receipt.json` (horários, status, content-type, hash — sem URL/token), `analysis.json` (ausentes E−P, presentes inutilizáveis P−U com ponteiros), request/owner/review, `inventory.json`; ou `failure.json`.

Público (`F2_PUBLIC_SLOT_RESULT_V1`): slot, horário UTC agendado, início, início/fim do GET (UTC), status HTTP, hash/tamanho do corpo, contagens, PASS/FAIL, hashes de request/elegíveis/fonte/selo/inventário/cifra, número de GETs. Sem símbolos, token, caminhos internos ou exceção livre.

## Elegíveis

A readiness_probe P do G19 (`GO_READONLY_HOSTOPS02_K9_PHASE_READ_01`, rodada 07/10 22:26Z, snippet `a46e7609…`) **não guarda conjunto**: ela chama a lista de símbolos ao vivo dentro do container, aplica `build_registry` + `DAILY_ELIGIBLE_TYPES` e imprime só contagens e o hash do corpo (`bccacd2d…`, 5.782 elegíveis). O corpo não foi retido e a probe não lê nem grava banco. O produtor diário (`r2d2_v2_producer_daily.py`, main `0086dc8e`) grava `registry.json` (`V2_CAUSAL_REGISTRY_V1`) como documento de porta quando um collect roda; se houver um no servidor, seria de outra leitura, não da P, e não foi verificado (sem acesso ao servidor nesta entrega). Portanto o conjunto "original da P" é irrecuperável.

O conjunto fixo usado é o mais próximo disponível pela **mesma régua e mesmo normalizador**: o corpo cru da lista de símbolos retido pela F1 (`registry.raw` `74ac3250…`, recebido 2026-10-08T20:26:32Z, cifra F1 `2ca5366f…`, inventário `29a2eed7…`), normalizado por `bind_series.py eligible` com o `build_registry` pinado (`e50e2263…`) e os tipos `COMMON_STOCK`/`COMMON_STOCK_ADR`. Resultado: 5.784 nomes = contagem pública da F1; diferença de +2 em relação aos 5.782 da P (já registrada pelo Codex na revisão F1). Conferência local: o analisador F2 aplicado ao bulk F1 (07/10) reproduz exatamente as contagens públicas da F1 (5.679 presentes, 5.677 usáveis, 105 ausentes, 2 inutilizáveis, mínimo 5.495, 44.583 linhas). **Esta substituição precisa de aceite explícito do Codex.**

## Revisão 2 (08/10, após revisão adversarial)
- **B1 corrigido:** nenhuma escrita por nome fora de descritor de slot. Falha antes do `mkdir` do slot (ex.: `age` ilegível, I/O do ledger) = recusa sem efeito de slot; falha depois do `mkdir` = `SLOT_HOLD`/`SLOT_CLAIM_UNCERTAIN`, sem recibo e sem nenhum arquivo fora da raiz. `WorkingDirectory` das unidades = raiz da campanha (defesa extra).
- **Instalador:** prévia com as guardas reais do runtime antes dos timers (raiz, `age`, `provider.env` com a chave presente, sem imprimir valor); código 2 se algum timer falhar ou nenhum for instalado; conferência `sha256sum -c` do staging antes do `sudo`; caminho de recuperação de instalação parcial sem timers (RUNBOOK §10).
- Testes: 30 (dois novos falham na revisão 1 e passam na 2).

## Revisão 3 (08/10, após NO-GO do Codex 6069751930 — B2/B3)
Rev 2 selada e intocada (`fable-f2-series-20261008`, SHA256SUMS `e33335b1…`). Delta:

**B2 — assinaturas no tempo** (`series_runtime.py`)
- Registro do dono `F2_OWNER_SIGNATURE_V1` = {request_sha256, question_sha256, answer "Assino", question_published_at_utc, recorded_at_utc, channel "REGISTRO_PELA_FABLE"}. `validate_documents` exige `question_published_at_utc ≤ recorded_at_utc ≤ 2026-10-09T00:45:00Z` (21:45 BRT) e `signed_at_utc` da Emenda 7 `≤ recorded_at_utc`.
- Assinatura ORIGINAL da Emenda 7 é documento próprio do BOUND (`amendment_signature`): `{"schema":"F2_AMENDMENT7_SIGNATURE_ORIGINAL_V1","original_record_sha256":…,"original_record_base64":…}`. **Pin = SHA256 dos bytes originais exatos do arquivo** (sem recanonicalizar; os bytes viajam em base64). Validação no bind (passos `amendment`, `request`, `bound`), no `install` e no runtime: base64 estrito, sha dos bytes == `REQUEST.amendment7_signature_sha256`, parser estrito (sem chave duplicada/NaN), chaves exatas, schema `DUDU_AMENDMENT_SIGNATURE_V1`, amendment `A2_EMENDA_07`, revision int ≥ 1, `document_sha256 == REQUEST.amendment7_sha256`, answer literal `Assino a emenda 7 da A2`, `signed_at_utc ≤ 21:45 BRT`. Recanonicalizar o original muda o sha e recusa.
- Por slot, no runtime (antes do claim e de novo antes do GET): `recorded_at_utc < horário agendado do slot` (estrito) e `clock() > recorded_at_utc`; senão recusa sem efeito (ou HOLD sem GET se mudar depois do claim). O `install` também só cria timer de slot posterior ao registro.

**B3 — eleição/medição e identidade física (modelo F1)**
- `install_series.py` em duas fases. `prepare` (Emenda 7, sem BOUND): guardas que não dependem das raízes primeiro (selo do staging, `ELIGIBLE_SET` pelo hash fixo `b24ffe6f…`, `age` da F1 pelo `AGE_SHA256`, presença da chave no `provider.env` sem imprimir valor, raízes ausentes), depois SOURCE_ROOT 0700 (família + ELIGIBLE_SET 0400) e CAMPAIGN_ROOT 0700 (`age` 0500 + ledger VAZIO 0600 criado O_EXCL). Nenhum timer. `measure`: só leitura, JSON canônico privado `{measurement, runtime, election}` (plataforma, Python, caminho+sha do executável real, euid, sha do boot_id, sha dos bytes INSTALADOS de series_runtime/SHA256SUMS/reference/ELIGIBLE_SET/age, identidades path/device/inode/uid/gid/mode de todos os ancestrais e das duas raízes + diretório da família, identidade do ledger com size 0 e do `age`). `install` (após Assino): copia só o BOUND (0400, O_EXCL), re-mede e exige igualdade total com runtime (exceto `measurement_record_sha256`) e election do REQUEST, roda a prévia com as guardas do próprio runtime (`Held.check`, ledger vazio, sem REVOKED, chave presente) e só então cria timers. Qualquer diferença: zero timers, `F2_INSTALL_HOLD_V1`.
- `bind_series.py`: passos `measurement` (separa e confere o hash do registro) e `amendment` (embrulha o original e confere contra `config.json`); `request` exige config, review, runtime, election, amendment_signature e ELIGIBLE_SET e grava `runtime_sha256`, `election_sha256` e `eligible_provenance` (registry raw `74ac3250…`, receipt F1, inventário/cifra F1, normalizador `reference_extract.build_registry` `e50e2263…`, tipos, `eligible_set_sha256`, `eligible_count` 5784, bulk_date, régua, calendário UTC, coorte própria F1 ≠ P); `bound` inclui owner e o original da emenda (`F2_BOUND_V2`).
- Runtime: antes do claim E de novo imediatamente antes do GET, `Held.check` reconfere euid, boot_id, versão e executável (caminho+sha), sha dos próprios bytes instalados (fonte, selo, referência — executada a partir dos MESMOS bytes lidos —, ELIGIBLE_SET, `age`), identidade de ancestrais/raízes pelos descritores mantidos (fstat) E por nova caminhada por nome (troca/rename), ledger aberto SEM O_CREAT com dev/inode/uid/gid/mode/nlink iguais ao pin (ausente ou recriado = recusa), relógio de parede vs monotônico (|Δ| > 2 s), cortes de calendário e dono-antes-do-slot, e por último `REVOKED`. Falha depois do claim = `SLOT_HOLD`, zero GET e nenhum processo filho (sem cifra), recibo público pelo descritor do slot.
- Ausência de claim não libera tentativa: o runtime nunca cria o ledger; diretório de slot sem linha no ledger (ledger zerado/recriado ou claim incerto anterior) recusa todo slot seguinte (`LEDGER_SLOT_DIRECTORY_MISMATCH`).

**Revisão adversarial (não bloqueante) incorporada:** prévia do token antes de criar raízes; docstring do instalador corrigida; RUNBOOK com guarda bloqueante de staging; `main()`: só `Refusal` vira `SLOT_REFUSED_NO_EFFECT`/exit 3, qualquer outra exceção vira `SLOT_HOLD` exit 2 com `slot_consumed`/`logical_fetch_calls` = `"UNKNOWN"`, e falha do `os.write` final não muda o código.

Mantido da rev 2: B1, `WorkingDirectory`, códigos de saída 0/2/3, `sha256sum -c` antes do sudo, régua, slots, orçamentos, um GET por slot.

Testes: 66 (stdlib, sintéticos). Prova Linux nova necessária (workflow sem mudança de forma).

## Revisão 3.1
Fecha o achado bloqueante da revisão adversarial da rev 3 (B2 no `install`: Assino precisa preceder a cópia do BOUND e os timers) e quatro não bloqueantes (falha por slot do `systemd-run` relatada como UNCERTAIN sem esconder timers; ordem Emenda 7 ≤ medição verificada no `bind request`; `LimitCORE=0`; política escrita para `prepare`/`install` parciais). 69 testes; os três novos e o de argv falham na rev 3 e passam na 3.1.

## Revisão 3.2
Fecha B4 (6070281169): a autoridade da fase A é conferida pelo próprio `prepare` antes do primeiro efeito (original opaco da Emenda 7, documento com o selo desta família, config, assinatura anterior ao relógio), com recibo original de preparação vinculado à medição e conferido no `bind request`. 72 testes.

## Revisão 3.3
Fecha o bloqueante da revisão adversarial da 3.2 (selo da família conferido por ocorrência única rotulada, não por substring) e três melhorias (gate_checked_at no recibo; recibo × runtime no bind; testes de measure sem recibo e de original divergente). 73 testes.

## Variante 09/10
Sexta 09/10, derivada EXATAMENTE da rev 3.3 selada (`fable-f2-series-20261008-rev3_3`, SHA256SUMS `f077c293…`; base não alterada). Motivo: na quinta o primeiro slot (21:26 BRT) já passou a régua (5.531 presentes / mínimo 5.495 na coorte fixa de 5.784); sexta começa às 19:26 BRT para achar o último FAIL antes do primeiro PASS. **SOURCE_DELIVERY_ONLY / OPERATION_HOLD**: nada executado no servidor nem no provedor. Mudanças, e só estas:

**1. Pregão/bulk.** `BULK_DAY = "2026-10-09"`; `SESSION_CLOSE = "2026-10-09T20:00:00Z"` (16:00 ET de sexta, EDT = UTC−4). Semântica idêntica à rev 3.3, conferida no código: `SESSION_CLOSE` só aparece (a) no campo `session_close` do REQUEST, exigido igual à constante em `validate_request`, e (b) em `analyze`, que exige `received_at > SESSION_CLOSE` antes de contar barras (pré-condição declarada do `_bar` pinado). `BULK_DAY` é o `date=` do único GET, o filtro `row["date"] == BULK_DAY` e a sessão passada ao `_bar`. Linhas do bulk de 08/10 não contam na sexta (teste novo).

**2. Slots (12; chaves HHMM BRT no formato da rev 3.3; BRT = UTC−3).**

| Slot | BRT | UTC |
|---|---|---|
| `1926` | 19:26 de 09/10 | `2026-10-09T22:26:00Z` |
| `1956` | 19:56 de 09/10 | `2026-10-09T22:56:00Z` |
| `2026` | 20:26 de 09/10 | `2026-10-09T23:26:00Z` |
| `2056` | 20:56 de 09/10 | `2026-10-09T23:56:00Z` |
| `2126` | 21:26 de 09/10 | `2026-10-10T00:26:00Z` |
| `2156` | 21:56 de 09/10 | `2026-10-10T00:56:00Z` |
| `2226` | 22:26 de 09/10 | `2026-10-10T01:26:00Z` |
| `2256` | 22:56 de 09/10 | `2026-10-10T01:56:00Z` |
| `2326` | 23:26 de 09/10 | `2026-10-10T02:26:00Z` |
| `2356` | 23:56 de 09/10 | `2026-10-10T02:56:00Z` |
| `0026` | 00:26 de 10/10 | `2026-10-10T03:26:00Z` |
| `0056` | 00:56 de 10/10 | `2026-10-10T03:56:00Z` |

Janela por slot [slot−2 s, slot+60 s], margem de 180 s do `install`, ledger, diretório por slot e um GET por slot: iguais. (A chave `2026` é 20:26 BRT; coincide só na grafia com o ano.)

**3. Cortes.** `OWNER_DEADLINE = "2026-10-10T00:45:00Z"` (21:45 BRT de 09/10: registro do Assino do REQUEST e assinatura original da autorização ≤ isso); `START_CUTOFF = "2026-10-10T03:58:00Z"` (início ≥ 00:58 BRT de 10/10 recusado); `RECEIVE_CUTOFF = "2026-10-10T04:00:00Z"` (recebimento termina antes de 01:00 BRT de 10/10). Os códigos públicos `OWNER_SIGNED_AFTER_2145_BRT`, `START_AFTER_CUTOFF_0058_BRT` e `RECEIVED_AFTER_0100_BRT` continuam corretos (mesmos horários BRT).

**4. Autoridade.** Não é mais a Emenda 7 da A2 (a A2 vence sex 20:59). É autorização própria do dono: documento `AUTORIZACAO_MEDICAO_F2_20261009` (staging `AUTORIZACAO_MEDICAO_F2_20261009.md`), registro original `DUDU_AMENDMENT_SIGNATURE_V1` com `amendment` = `F2_MEDICAO_20261009` e `answer` literal `Assino a autorização de medição de sexta` (comparação exata de string, NFC: ç = U+00E7, ã = U+00E3; na fonte como escapes `ç`/`ã`, mantendo os `.py` em ASCII). Constantes: `AMENDMENT7 = "F2_MEDICAO_20261009"`, `AMENDMENT7_ANSWER` = o literal; `install_series.AMENDMENT_DOCUMENT = "AUTORIZACAO_MEDICAO_F2_20261009.md"`, `AMENDMENT_ORIGINAL = "AUTORIZACAO_MEDICAO_ORIGINAL.json"` (cópias 0400 na raiz-fonte com esses nomes).
*Nomes mantidos (decisão, para não mexer em lógica):* campos `amendment7_sha256` / `amendment7_signature_sha256` no config (`F2_LEAF_CONFIG_V1`), no REQUEST, na review e no recibo de preparação (com `amendment7_signed_at_utc`); schema do invólucro `F2_AMENDMENT7_SIGNATURE_ORIGINAL_V1`; documento `amendment_signature` do BOUND; códigos `AMENDMENT_*`, `AMENDMENT7_DOCUMENT_MISMATCH`, `AMENDMENT7_DOES_NOT_NAME_THIS_SEAL`, `PREPARE_BEFORE_AMENDMENT7_SIGNATURE`, `MEASUREMENT_BEFORE_AMENDMENT7`, `OWNER_SIGNED_BEFORE_AMENDMENT`; entrada `amendment-original.json` do `bind amendment`. Nesta variante, "amendment7"/"Emenda 7" nesses identificadores (e nas docstrings de `bind_series.py`, que não mudou) **significa a autorização `AUTORIZACAO_MEDICAO_F2_20261009`**.
Lógica de B2/B4 byte a byte a da rev 3.3: assinatura original (bytes opacos; pin = SHA256 dos bytes) conferida pelo próprio `prepare` antes do primeiro efeito e anterior ao relógio; documento com exatamente um selo rotulado `` selo `<64 hex>` `` igual ao SHA256SUMS desta família; recibo original de preparação com `gate_checked_at_utc`; vínculo medição ↔ recibo no `bind request`; assinatura ≤ registro do dono ≤ 21:45 BRT; registro do dono estritamente antes de cada slot (runtime e `install`). A Emenda 7 da A2 (amendment `A2_EMENDA_07`, literal `Assino a emenda 7 da A2`) agora é recusada (`AMENDMENT_NOT_SIGNED`; testes).
Pergunta ao dono (`owner_question`): mudou só o texto de autoridade e datas — "bulk de " + `BULK_DAY` (era o literal `2026-10-08`), rótulos "Autorizacao de medicao (AUTORIZACAO_MEDICAO_F2_20261009) SHA256" e "Assinatura original da autorizacao SHA256" (eram "Emenda 7 …"), "21:45 BRT de 09/10" e "00:58/01:00 BRT de 10/10". Resposta literal continua `Assino`.

**5. Raízes, unidades, operação, família, época.** `SOURCE_ROOT = /var/lib/c3po/f2-series-src-20261009`; `CAMPAIGN_ROOT = /var/lib/c3po/f2-series-20261009`; `UNIT_PREFIX = f2s-20261009-`; `OPERATION = GO_READ_PROVIDER_BULK_SERIES_F2_20261009`; `FAMILY = F2_SERIES_20261009_V1` (REQUEST, eleição, resultado público, analisador); `EPOCH = F2-MEDICAO-AUTORIZACAO-2026-10-09` — escopo documental próprio da autorização do dono, não a época A2 nem `R2D2-V2-SHADOW-2026-10-05`. Nenhum documento de 08/10 (REQUEST, BOUND, eleição, medição, recibo) valida aqui: família, operação, época, raízes, slots e cortes diferem. Schemas (`F2_REQUEST_V2`, `F2_BOUND_V2`, `F2_OWNER_SIGNATURE_V1`, `F2_PUBLIC_SLOT_RESULT_V1`, …) mantidos.

**6. Elegíveis e `age`.** Os mesmos de quinta, para comparar: `ELIGIBLE_SET.json` fixo `b24ffe6f…` (5.784, coorte própria F1; proveniência inalterada — `F1_PREVIOUS_CLOSE` 07/10 é da normalização da lista F1, não do pregão medido); `age` 1.3.2 `eb7dd1b5…` copiado pelo `prepare` de `/var/lib/c3po/f1-diagnostic-20261008/age`, como na quinta. Credencial: o mesmo `provider.env`, lido pelo próprio processo.

**7. Nada mais muda.** Guardas, B1–B4, régua 95/100 + piso 4.000, orçamentos 120/75/30 s, janela, `CLOCK_SKEW_SECONDS`, margem 180 s, códigos 0/2/3, `WorkingDirectory`, `LimitCORE=0`. Sem mudança de bytes: `bind_series.py` (`be589b98…`), `series_analyze.py` (`2cb9a13e…`), `verify_family.py` (`bb18fcaa…`), `reference_extract.py` (`e50e2263…`), `REFERENCE_PROVENANCE.json` (`e8ae6e38…`). Testes: carimbos de 08/10 (autorização, prepare, medição, pergunta, Assino, install) movidos para 09/10 (autorização 09:00 BRT, prepare 09:30, medição 18:30/18:40, pergunta 18:58, Assino 19:00, install 19:10) e os dos slots 21:26–00:56 para o dia seguinte (mesmos slots BRT); 8 → 12 timers; analisador nos slots iniciais; os literais da A2 viraram casos de recusa; seis testes novos (`Variant20261009Constants`: 12 slots UTC literais, três cortes, autoridade, raízes, unidades e insumos fixos; `Variant20261009Behaviour`: escopo do REQUEST, cortes do dono e do recebimento, slots iniciais com dono antes do slot, fecho do pregão e linhas de 08/10). 79 testes. `test_linux_crypto.py`: slot `1926` às 22:26:00.300Z, medição 21:30Z. `linux-proof.yml`: ramo `ops/f2-series-proof-20261009` e grupo `f2-series-proof-20261009`, mesma forma. RUNBOOK reescrito para os prazos de sexta. **Prova Linux nova necessária** (selo novo).
