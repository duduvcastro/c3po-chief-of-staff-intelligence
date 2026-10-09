# F2-SERIES variante 09/10 (sexta) — passo a passo da Fable (nada aqui foi executado)

Derivada EXATAMENTE da rev 3.3 (`fable-f2-series-20261008-rev3_3`, SHA256SUMS `f077c293…`, intocada); mudanças em CONTRACT.md, seção "Variante 09/10". Horas para o dono em BRT; UTC só no canal técnico. Slots: 19:26, 19:56, 20:26, 20:56, 21:26, 21:56, 22:26, 22:56, 23:26, 23:56 (09/10) e 00:26, 00:56 (10/10) BRT = 22:26Z de 09/10 … 03:56Z de 10/10. Slot sem margem de 180 s na instalação, ou não estritamente posterior ao registro do Assino do REQUEST, **não é instalado nem recuperado depois**. Sem catch-up, retry ou mínimo prometido. Objetivo da sexta: o último FAIL antes do primeiro PASS — os slots 19:26 e 19:56 são a razão da variante.

Variáveis (Mac): `F2=/Users/eduardocastro/Documents/Codex/2026-09-04/va/work/fable-f2-series-20261009`, `PRIV=/Users/eduardocastro/Documents/Codex/2026-09-04/va/work/fable-f2-series-20261009-private` (criar 0700; `ELIGIBLE_SET.json` copiado do privado de quinta, `fable-f2-series-20261008-private`, e conferido por comando = `b24ffe6fca52408d4330875d11eeff1e0535114c57ce74fdedcb505e8c8acda3` — tem símbolos, **não publicar**). Hashes sempre por comando (`shasum -a 256`), nunca à mão. Cadeias com `&&` (o `set -e` não vale nesta sessão).

## Prazos de sexta (09/10, BRT) — caminho crítico
| Passo | Alvo | Limite duro |
|---|---|---|
| 1. Prova Linux (push no ramo `ops/f2-series-proof-20261009`, tentativa 1) | 08:30 | — |
| 2. Revisão Codex da família 09/10 + prova | 09:30 | antes do passo 3 (o documento assinado cita o selo; selo novo = nova assinatura) |
| 3. Assino da autorização `AUTORIZACAO_MEDICAO_F2_20261009` (de manhã; registro original `DUDU_AMENDMENT_SIGNATURE_V1`) | 10:00 | antes do `prepare` (o `prepare` recusa sem efeito se o relógio não for posterior); dono só a partir de 07:00; o código aceita até 21:45 |
| 4. `prepare` + 5. `measure` (fase A, host) | 10:30 | — sem reboot do host daqui até 00:56 de 10/10 (o boot_id é pin; reboot = HOLD de todos os slots) |
| 6. `bind measurement` / `amendment` | 10:45 | — |
| 7. Revisão Codex dos bytes medidos → `review.json` | 14:00 | — |
| 8. `bind request` + pergunta publicada ao dono | 17:30 | — |
| 9. Assino do REQUEST | 18:30 | **21:45** (registro posterior = recusa; dono dorme às 22:00). Para o 19:26 o registro tem de ser anterior a 19:26 e o `install` tem de terminar até **19:23** |
| 10. `bind bound` + 11. `install` + 12. readback | 19:00 | `install` ≥ 180 s antes de cada slot: **19:23:00** para o 19:26, 19:53 para o 19:56, …; Assino às 21:45 ainda pega 21:56 se o `install` sair até 21:53 |
Atraso em qualquer linha = avisar o dono na hora; slots perdidos não voltam. Cada 30 min de atraso no Assino do REQUEST tira um slot do início da série, que é a parte que interessa.

## 0. Conferir bytes (Mac)
`python3 -I -S -B $F2/verify_family.py` → `SEAL_EXACT`. `python3 -I -S -B $F2/test_series.py` → `"ok": true` (79 testes).

## 1. Prova Linux própria (ramo descartável, sem segredo)
Ramo `ops/f2-series-proof-20261009` a partir da main; copiar o diretório para `f2-series/` e `linux-proof.yml` para `.github/workflows/f2-series-proof.yml` (bytes idênticos). Sem `ELIGIBLE_SET.json` nem nada do `$PRIV`. Push pela Fable, tentativa 1. Devolver head/tree, run id, tentativa, conclusão, SHA256 do workflow, artefato `F2_OWN_LINUX_FIXTURE_PROOF` (id/digest/ZIP) com `SEAL_RESULT.json`, `TEST_RESULT.json` (79), `TEST_NAMES.txt`, `CRYPTO_RESULT.json` (slot `1926`), `SEAL_RESULT_AFTER.json`. Prova sintética: não certifica servidor, chave real nem provedor.

## 2. Revisão do Codex (família)
SHA256SUMS desta variante, resultados da prova, CONTRACT.md "Variante 09/10", `ELIGIBLE_SET.json` por hash + proveniência (o mesmo de quinta: `b24ffe6f…`, 5.784, coorte própria F1 ≠ P). Sem GO de família, HOLD.

## 3. Assino da autorização (manhã)
A Fable redige `AUTORIZACAO_MEDICAO_F2_20261009.md` contendo **exatamente uma** ocorrência rotulada ``selo `<SHA256SUMS desta variante>` `` (hash por `shasum -a 256 $F2/SHA256SUMS`) e nenhuma outra string nesse formato rotulado (outros selos, se citados, sem o rótulo). O dono assina; a Fable grava o **arquivo original** do registro em `$PRIV/in-amendment/amendment-original.json` e **nunca o reescreve** (o pin é o SHA256 desses bytes exatos):
`{"schema":"DUDU_AMENDMENT_SIGNATURE_V1","amendment":"F2_MEDICAO_20261009","revision":1,"document_file":"AUTORIZACAO_MEDICAO_F2_20261009.md","document_sha256":<shasum do .md>,"answer":"Assino a autorização de medição de sexta","signed_at_utc":<date -u +%Y-%m-%dT%H:%M:%SZ>,"channel":…}`.
A resposta é comparada por igualdade exata, em UTF-8 NFC (ç = `c3 a7`, ã = `c3 a3`). Conferência antes de seguir: `python3 -I -S -B -c 'import json,sys,unicodedata as u; a=json.load(open(sys.argv[1],encoding="utf-8"))["answer"]; print(a==u.normalize("NFC",a), a=="Assino a autoriza\u00e7\u00e3o de medi\u00e7\u00e3o de sexta")' $PRIV/in-amendment/amendment-original.json` → `True True`. `config.json` canônico: `{"schema":"F2_LEAF_CONFIG_V1","amendment7_sha256":<sha do .md>,"amendment7_signature_sha256":<shasum -a 256 amendment-original.json>}` (nomes de campo da rev 3.3 mantidos; aqui significam a autorização). Autoriza só a fase A (`prepare`/`measure`). Não é a Emenda 7 da A2: o registro da A2 é recusado (`AMENDMENT_NOT_SIGNED`).

## 4. Staging + `prepare` (fase A, host, root; sem BOUND, sem timer)
```
ssh $H 'umask 077; mkdir /var/tmp/f2-stage-20261009'
scp -r $F2 $H:/var/tmp/f2-stage-20261009/f2-series            # só os arquivos do selo
scp $PRIV/ELIGIBLE_SET.json $PRIV/config.json $H:/var/tmp/f2-stage-20261009/
scp $PRIV/in-amendment/amendment-original.json $H:/var/tmp/f2-stage-20261009/AUTORIZACAO_MEDICAO_ORIGINAL.json
scp $PRIV/AUTORIZACAO_MEDICAO_F2_20261009.md $H:/var/tmp/f2-stage-20261009/AUTORIZACAO_MEDICAO_F2_20261009.md
ssh $H 'cd /var/tmp/f2-stage-20261009/f2-series && test -z "$(find . -type l -o -name "*.pyc" -o -name __pycache__)" && sha256sum -c --strict SHA256SUMS && sha256sum ../ELIGIBLE_SET.json ../config.json ../AUTORIZACAO_MEDICAO_ORIGINAL.json ../AUTORIZACAO_MEDICAO_F2_20261009.md'
ssh $H 'sudo -n /usr/bin/python3 -I -S -B /var/tmp/f2-stage-20261009/f2-series/install_series.py prepare --stage /var/tmp/f2-stage-20261009'
```
`prepare` recusa ANTES de criar qualquer raiz se: não root/Linux; selo do staging; `config.json`/documento/original da autorização inválidos (documento ≠ `amendment7_sha256`, selo rotulado ausente/duplicado/de outra família, original ≠ `amendment7_signature_sha256`, amendment/literal errados, assinado depois de 21:45 BRT, ou relógio não posterior à assinatura); `ELIGIBLE_SET` ≠ `b24ffe6f…`; `age` da F1 (`/var/lib/c3po/f1-diagnostic-20261008/age`) ≠ `eb7dd1b5…`; chave `C3PO_EODHD_API_TOKEN` ausente no `provider.env` (valor nunca impresso); raízes já existentes. Depois cria `/var/lib/c3po/f2-series-src-20261009` (0700; família, ELIGIBLE_SET, config, documento e original da autorização 0400; `PREPARE_RECEIPT.json` 0400) e `/var/lib/c3po/f2-series-20261009` (0700; `age` 0500; `campaign.ledger` vazio 0600 O_EXCL). Esperado: `PREPARED_NO_TIMER`, `timers: 0`. As raízes de quinta (`…-20261008`) não são tocadas. `prepare` parcial (falha depois de criar alguma raiz): nada é removido e não há segunda tentativa hoje; a série de sexta termina sem leitura e a Fable avisa o dono.

## 5. `measure` (host, root, só leitura, saída PRIVADA)
```
mkdir -m 700 $PRIV/in-measure
ssh $H 'umask 077; sudo -n /usr/bin/python3 -I -S -B /var/lib/c3po/f2-series-src-20261009/f2-series/install_series.py measure' > $PRIV/in-measure/MEASUREMENT_SET.json
```
JSON canônico sem LF (`measurement`/`runtime`/`election`, com o recibo de preparação). Não publicar (caminhos, inodes). Não preencher nada com valores do CI, do Mac, da F1 ou de quinta.

## 6. `bind measurement` e `bind amendment` (Mac)
```
python3 -I -S -B $F2/bind_series.py measurement --inputs $PRIV/in-measure --out $PRIV/measure-out
cp $PRIV/config.json $PRIV/in-amendment/
python3 -I -S -B $F2/bind_series.py amendment --inputs $PRIV/in-amendment --out $PRIV/amendment-out
```

## 7. Revisão do Codex dos bytes medidos → `review.json`
Entregar `runtime.json`/`election.json` (por hash; conteúdo por canal privado se pedido) e `amendment_signature.json`. O parecer vira `review.json` canônico (o REQUEST o exige, por isso vem antes do passo 8):
`{"schema":"F2_CODEX_REVIEW_V2","verdict":"ACCEPTED_OWN_BYTES_LINUX_AND_RUNTIME","source_sha256":…,"seal_sha256":…,"reference_sha256":"e50e2263…","eligible_set_sha256":"b24ffe6f…","runtime_sha256":…,"election_sha256":…,"amendment7_signature_sha256":…,"linux_result_sha256":…,"review_record_sha256":…}`.

## 8. `bind request` e pergunta
```
mkdir -m 700 $PRIV/in-request && cp $PRIV/config.json $PRIV/review.json $PRIV/measure-out/measurement.json $PRIV/measure-out/runtime.json $PRIV/measure-out/election.json $PRIV/amendment-out/amendment_signature.json $PRIV/ELIGIBLE_SET.json $PRIV/in-request/
python3 -I -S -B $F2/bind_series.py request --inputs $PRIV/in-request --out $PRIV/request-out
```
Imprime o SHA256 do REQUEST; gera `OWNER_QUESTION.txt` (bulk de 2026-10-09, autorização `AUTORIZACAO_MEDICAO_F2_20261009`, 12 slots UTC). Exige autorização assinada < conferência do `prepare` ≤ preparação ≤ medição (`MEASUREMENT_BEFORE_AMENDMENT7` / `PREPARE_RECEIPT_UNBOUND`). A Fable carimba `question_published_at_utc` (`date -u +%Y-%m-%dT%H:%M:%SZ`) ao publicar a pergunta exata ao dono.

## 9. Assino do REQUEST (até 21:45 BRT de 09/10)
`owner.json`: `{"schema":"F2_OWNER_SIGNATURE_V1","request_sha256":…,"question_sha256":…,"answer":"Assino","question_published_at_utc":…,"recorded_at_utc":…,"channel":"REGISTRO_PELA_FABLE"}`. Exigido: publicada ≤ registrada ≤ `2026-10-10T00:45:00Z`; autorização assinada ≤ registrada. Só valem slots estritamente posteriores ao registro. Ausência/NÃO/outra resposta = HOLD. Para o 19:26: registro antes de 19:26 com folga para `bind bound` + cópia + `install` até 19:23.

## 10. `bind bound`
```
mkdir -m 700 $PRIV/in-bound && cp $PRIV/request-out/{REQUEST,review,runtime,election,amendment_signature}.json owner.json $PRIV/in-bound/
python3 -I -S -B $F2/bind_series.py bound --inputs $PRIV/in-bound --out $PRIV/bound-out
```
Imprime `BOUND_SHA` (`F2_BOUND_V2`). Imutável após o Assino.

## 11. `install` (fase B, host, root)
```
scp $PRIV/bound-out/BOUND.json $H:/var/tmp/f2-stage-20261009/
ssh $H 'sha256sum /var/tmp/f2-stage-20261009/BOUND.json'
ssh $H 'sudo -n /usr/bin/python3 -I -S -B /var/lib/c3po/f2-series-src-20261009/f2-series/install_series.py install --stage /var/tmp/f2-stage-20261009 --bound-sha256 <BOUND_SHA>'
```
Recusa sem nenhum efeito (`INSTALL_BEFORE_OWNER_RECORD`) se o relógio não for posterior ao registro do Assino. Copia só o BOUND (0400), re-mede, exige igualdade total com runtime/election assinados, roda a prévia com as guardas do runtime (identidades, pins, ledger vazio, sem REVOKED, chave presente) e só então cria um `systemd-run` por slot futuro com margem ≥ 180 s e posterior ao registro do dono, p.ex. (argv exato do `plan`):
```
/usr/bin/systemd-run --unit=f2s-20261009-1926 "--description=F2 series slot 1926 (BRT)" "--on-calendar=2026-10-09 22:26:00 UTC" --timer-property=AccuracySec=1s --property=Type=oneshot --property=TimeoutStartSec=170 --property=UMask=0077 --property=NoNewPrivileges=yes --property=PrivateTmp=yes --property=WorkingDirectory=/var/lib/c3po/f2-series-20261009 --property=LimitCORE=0 /usr/bin/python3 -I -S -B /var/lib/c3po/f2-series-src-20261009/f2-series/series_runtime.py run --bound /var/lib/c3po/f2-series-src-20261009/BOUND.json --slot 1926
```
Qualquer diferença: `F2_INSTALL_HOLD_V1`, zero timers. Se o `systemd-run` estourar o tempo ou der erro de SO num slot, o laço para ali e o recibo lista os timers já criados e o slot `UNCERTAIN` (`TIMER_INSTALL_UNCERTAIN`, saída 2); os timers criados **ficam** e o readback (§12) decide o estado real; nenhum timer é recriado. Dúvida sobre timer não listado: `revoke` (§13). Instalação parcial é consumida: o BOUND já copiado impede segundo `install` (`BOUND_ALREADY_INSTALLED`). Nada é removido.

## 12. Readback (só leitura)
`ssh $H 'sudo -n /usr/bin/python3 -I -S -B /var/lib/c3po/f2-series-src-20261009/f2-series/install_series.py readback'` → um timer `f2s-20261009-*` por slot instalado e nenhum outro; AccuracyUSec=1s, Persistent=no, Restart=no; `revoked_marker: false`.

## 13. Revogação
`... install_series.py revoke` → grava `REVOKED` em `/var/lib/c3po/f2-series-20261009` e para os timers `f2s-20261009-*`. Um serviço já em execução reconfere `REVOKED` imediatamente antes do GET (HOLD sem GET). Nada é apagado.

## 14. Leitura de sábado (10/10, após 07:00 BRT)
Readback + `campaign.ledger` + `<slot>/RESULT.public.json` + `journalctl -u 'f2s-20261009-*' -o cat` (só JSON público). Copiar `<slot>/bulk-series.age` para `$PRIV/`, decifrar pela Fable, conferir `cipher_sha256`/`inventory_sha256`. `python3 -I -S -B $F2/series_analyze.py RESULT_*.json` → último FAIL antes do primeiro PASS, lacunas, regressões. O analisador aceita só resultados da família `F2_SERIES_20261009_V1`; os de quinta se leem com o analisador da rev 3.3 e se comparam pelos números (mesma coorte `b24ffe6f…`, régua igual). Nenhum resultado é prontidão, capacidade, E6 ou GO.

## Códigos de saída do slot
0 observado (PASS/FAIL); 3 recusa sem efeito (`SLOT_REFUSED_NO_EFFECT`, só `Refusal`); 2 HOLD (inclui exceção inesperada: `slot_consumed: "UNKNOWN"`).

## Herdado da rev 3.1–3.3 (sem mudança de comportamento)
- `install` exige relógio posterior ao registro do Assino antes de qualquer efeito; falha do `systemd-run` por slot para o laço e lista os timers criados; unidades com `LimitCORE=0`.
- `prepare` confere a autoridade da fase A antes do primeiro efeito (original opaco, documento com exatamente um selo rotulado desta família, config, assinatura anterior ao relógio) e grava `PREPARE_RECEIPT.json` original com `gate_checked_at_utc`; `measure` carrega o recibo; `bind request` exige assinatura < conferência ≤ preparação ≤ medição e confere selo/fonte/elegíveis/age do recibo contra o runtime.
- `prepare` parcial/incerto é consumido: sem remoção, sem repetição.
