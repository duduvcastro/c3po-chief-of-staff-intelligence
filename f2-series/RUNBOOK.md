# F2-SERIES rev 3 — passo a passo da Fable (nada aqui foi executado)

Horas para o dono em BRT. UTC só no canal técnico. Slots: 21:26, 21:56, 22:26, 22:56, 23:26, 23:56 (08/10) e 00:26, 00:56 (09/10) BRT = 00:26Z…03:56Z de 09/10. Slot sem margem de 180 s na instalação, ou não posterior ao registro do Assino, **não é instalado nem recuperado depois**. Sem catch-up, retry ou mínimo prometido.

Variáveis (Mac): `F2=/Users/eduardocastro/Documents/Codex/2026-09-04/va/work/fable-f2-series-20261008-rev3`, `PRIV=/Users/eduardocastro/Documents/Codex/2026-09-04/va/work/fable-f2-series-20261008-private` (0700; `ELIGIBLE_SET.json` com símbolos — **não publicar**). Hashes sempre por comando (`shasum -a 256`), nunca à mão.

## Prazos de hoje (08/10, BRT) — caminho crítico
| Passo | Alvo | Limite duro |
|---|---|---|
| 1. Prova Linux (push no ramo de prova, tentativa 1) | 19:50 | — |
| 2. Revisão Codex da família rev 3 + prova | 20:10 | — |
| 3. Assino da Emenda 7 (registro original `DUDU_AMENDMENT_SIGNATURE_V1`) | 20:20 | antes do `prepare` |
| 4. `prepare` + 5. `measure` no host | 20:35 | — |
| 6. `bind measurement` / `amendment` | 20:40 | — |
| 7. Revisão Codex dos bytes medidos → `review.json` | 20:55 | — |
| 8. `bind request` + pergunta publicada ao dono | 21:00 | — |
| 9. Assino do REQUEST | 21:05 | **21:45** (registro posterior = recusa; dono dorme às 22:00) |
| 10. `bind bound` + 11. `install` + 12. readback | 21:20 | `install` ≥ 180 s antes de cada slot (21:23 para o 21:26) |
Atraso em qualquer linha = avisar o dono na hora; slots perdidos não voltam.

## 0. Conferir bytes (Mac)
`python3 -I -S -B $F2/verify_family.py` → `SEAL_EXACT`. `python3 -I -S -B $F2/test_series.py` → `"ok": true` (66 testes).

## 1. Prova Linux própria (ramo descartável, sem segredo)
Ramo `ops/f2-series-proof-20261008` a partir da main; copiar o diretório para `f2-series/` e `linux-proof.yml` para `.github/workflows/f2-series-proof.yml` (bytes idênticos). Sem `ELIGIBLE_SET.json` nem nada do `$PRIV`. Push pela Fable, tentativa 1. Devolver head/tree, run id, tentativa, conclusão, SHA256 do workflow, artefato `F2_OWN_LINUX_FIXTURE_PROOF` (id/digest/ZIP) com `SEAL_RESULT.json`, `TEST_RESULT.json`, `TEST_NAMES.txt`, `CRYPTO_RESULT.json` (`pinned_symlink_refused` novo), `SEAL_RESULT_AFTER.json`. Prova sintética: não certifica servidor, chave real nem provedor.

## 2. Revisão do Codex (família)
SHA256SUMS rev 3, resultados da prova, `ELIGIBLE_SET.json` por hash + proveniência (`b24ffe6fca52408d4330875d11eeff1e0535114c57ce74fdedcb505e8c8acda3`, 5.784, coorte própria F1 ≠ P). Sem GO de família, HOLD.

## 3. Assino da Emenda 7
O dono assina o documento da Emenda 7; a Fable grava o **arquivo original** do registro (`DUDU_AMENDMENT_SIGNATURE_V1`, amendment `A2_EMENDA_07`, answer literal `Assino a emenda 7 da A2`, `signed_at_utc`) em `$PRIV/in-amendment/amendment-original.json` e **nunca o reescreve** (o pin é o SHA256 desses bytes exatos). `config.json` canônico: `{"schema":"F2_LEAF_CONFIG_V1","amendment7_sha256":<sha do documento>,"amendment7_signature_sha256":<shasum -a 256 amendment-original.json>}`. Autoriza só a fase A (`prepare`/`measure`).

## 4. Staging + `prepare` (fase A, host, root; sem BOUND, sem timer)
```
ssh $H 'umask 077; mkdir /var/tmp/f2-stage-20261008'
scp -r $F2 $H:/var/tmp/f2-stage-20261008/f2-series            # só os arquivos do selo
scp $PRIV/ELIGIBLE_SET.json $PRIV/in-amendment/amendment-original.json $PRIV/config.json $H:/var/tmp/f2-stage-20261008/   # rev 3.2: + Emenda 7 (abaixo)
scp <A2_EMENDA_07.rev1.md assinado> $H:/var/tmp/f2-stage-20261008/A2_EMENDA_07.md && ssh $H 'mv /var/tmp/f2-stage-20261008/amendment-original.json /var/tmp/f2-stage-20261008/AMENDMENT7_ORIGINAL.json'
ssh $H 'cd /var/tmp/f2-stage-20261008/f2-series && test -z "$(find . -type l -o -name "*.pyc" -o -name __pycache__)" && sha256sum -c --strict SHA256SUMS && sha256sum ../ELIGIBLE_SET.json'
ssh $H 'sudo -n /usr/bin/python3 -I -S -B /var/tmp/f2-stage-20261008/f2-series/install_series.py prepare --stage /var/tmp/f2-stage-20261008'
```
`prepare` recusa ANTES de criar qualquer raiz se: não root/Linux; selo do staging; `ELIGIBLE_SET` ≠ `b24ffe6f…`; `age` da F1 (`/var/lib/c3po/f1-diagnostic-20261008/age`) ≠ `eb7dd1b5…`; chave `C3PO_EODHD_API_TOKEN` ausente no `provider.env` (valor nunca impresso); raízes já existentes. Depois cria `/var/lib/c3po/f2-series-src-20261008` (0700; família e ELIGIBLE_SET 0400) e `/var/lib/c3po/f2-series-20261008` (0700; `age` 0500; `campaign.ledger` vazio 0600 O_EXCL). Esperado: `PREPARED_NO_TIMER`, `timers: 0`.

## 5. `measure` (host, root, só leitura, saída PRIVADA)
```
ssh $H 'umask 077; sudo -n /usr/bin/python3 -I -S -B /var/lib/c3po/f2-series-src-20261008/f2-series/install_series.py measure' > $PRIV/in-measure/MEASUREMENT_SET.json
```
JSON canônico sem LF (`measurement`/`runtime`/`election`). Não publicar (caminhos, inodes). Não preencher nada com valores do CI, do Mac ou da F1.

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
Imprime o SHA256 do REQUEST; gera `OWNER_QUESTION.txt`. A Fable carimba `question_published_at_utc` (`date -u +%Y-%m-%dT%H:%M:%SZ`) ao publicar a pergunta exata ao dono.

## 9. Assino do REQUEST (até 21:45 BRT)
`owner.json`: `{"schema":"F2_OWNER_SIGNATURE_V1","request_sha256":…,"question_sha256":…,"answer":"Assino","question_published_at_utc":…,"recorded_at_utc":…,"channel":"REGISTRO_PELA_FABLE"}`. Exigido: publicada ≤ registrada ≤ 2026-10-09T00:45:00Z; Emenda 7 assinada ≤ registrada. Só valem slots estritamente posteriores ao registro. Ausência/NÃO/outra resposta = HOLD.

## 10. `bind bound`
```
mkdir -m 700 $PRIV/in-bound && cp $PRIV/request-out/{REQUEST,review,runtime,election,amendment_signature}.json owner.json $PRIV/in-bound/
python3 -I -S -B $F2/bind_series.py bound --inputs $PRIV/in-bound --out $PRIV/bound-out
```
Imprime `BOUND_SHA` (`F2_BOUND_V2`). Imutável após o Assino.

## 11. `install` (fase B, host, root)
```
scp $PRIV/bound-out/BOUND.json $H:/var/tmp/f2-stage-20261008/
ssh $H 'sha256sum /var/tmp/f2-stage-20261008/BOUND.json'
ssh $H 'sudo -n /usr/bin/python3 -I -S -B /var/lib/c3po/f2-series-src-20261008/f2-series/install_series.py install --stage /var/tmp/f2-stage-20261008 --bound-sha256 <BOUND_SHA>'
```
Copia só o BOUND (0400), re-mede, exige igualdade total com runtime/election assinados, roda a prévia com as guardas do runtime (identidades, pins, ledger vazio, sem REVOKED, chave presente) e só então cria um `systemd-run` por slot futuro com margem ≥ 180 s e posterior ao registro do dono, p.ex.:
```
/usr/bin/systemd-run --unit=f2s-20261008-2126 "--description=F2 series slot 2126 (BRT)" "--on-calendar=2026-10-09 00:26:00 UTC" --timer-property=AccuracySec=1s --property=Type=oneshot --property=TimeoutStartSec=170 --property=UMask=0077 --property=NoNewPrivileges=yes --property=PrivateTmp=yes --property=WorkingDirectory=/var/lib/c3po/f2-series-20261008 /usr/bin/python3 -I -S -B /var/lib/c3po/f2-series-src-20261008/f2-series/series_runtime.py run --bound /var/lib/c3po/f2-series-src-20261008/BOUND.json --slot 2126
```
O `install` recusa sem nenhum efeito (`INSTALL_BEFORE_OWNER_RECORD`) se o relógio não for posterior ao registro do Assino. Qualquer diferença: `F2_INSTALL_HOLD_V1`, zero timers. Se o `systemd-run` estourar o tempo ou der erro de SO num slot, o laço para ali e o recibo lista os timers já criados e o slot `UNCERTAIN` (`TIMER_INSTALL_UNCERTAIN`, saída 2); os timers criados **ficam** (cada um é um slot legítimo e assinado) e o readback (§12) decide o estado real; nenhum timer é recriado. Se houver qualquer dúvida sobre um timer não listado, `revoke` (§13). Instalação parcial é consumida: sem repetição automática; o BOUND já copiado impede segundo `install` (`BOUND_ALREADY_INSTALLED`). Não há mais o caminho de recuperação da rev 2 (§10 antigo): nada é removido.

## 12. Readback (só leitura)
`ssh $H 'sudo -n /usr/bin/python3 -I -S -B /var/lib/c3po/f2-series-src-20261008/f2-series/install_series.py readback'` → um timer por slot instalado e nenhum outro; AccuracyUSec=1s, Persistent=no, Restart=no; `revoked_marker: false`.

## 13. Revogação
`... install_series.py revoke` → grava `REVOKED` e para os timers. Um serviço já em execução reconfere `REVOKED` imediatamente antes do GET (HOLD sem GET). Nada é apagado.

## 14. Leitura da manhã (09/10, após 07:00 BRT)
Readback + `campaign.ledger` + `<slot>/RESULT.public.json` + `journalctl -u 'f2s-20261008-*' -o cat` (só JSON público). Copiar `<slot>/bulk-series.age` para `$PRIV/`, decifrar pela Fable, conferir `cipher_sha256`/`inventory_sha256`. `series_analyze.py RESULT_*.json` → primeiro PASS, último FAIL anterior, lacunas, regressões. Nenhum resultado é prontidão, capacidade, E6 ou GO.

## Códigos de saída do slot
0 observado (PASS/FAIL); 3 recusa sem efeito (`SLOT_REFUSED_NO_EFFECT`, só `Refusal`); 2 HOLD (inclui exceção inesperada: `slot_consumed: "UNKNOWN"`).

## Revisão 3.1 (após revisão adversarial da rev 3)
- `install` exige relógio posterior ao registro do Assino antes de qualquer efeito (`INSTALL_BEFORE_OWNER_RECORD`).
- Falha do `systemd-run` por slot: laço para, recibo lista timers criados e o `UNCERTAIN`; timers criados ficam; nada recriado.
- `bind request` exige `measurement.json` e recusa se a Emenda 7 foi assinada depois da medição (`MEASUREMENT_BEFORE_AMENDMENT7`).
- Unidades com `LimitCORE=0`.
- `prepare` parcial (falha depois de criar alguma raiz): nada é removido e não há segunda tentativa nesta noite; a série de hoje termina sem leitura e a Fable avisa o dono.

## Revisão 3.2 (B4 do Codex, 6070281169)
- `prepare` passa a exigir no staging: `config.json` (F2_LEAF_CONFIG_V1), `A2_EMENDA_07.md` (sha = amendment7_sha256 e **contendo o selo desta família**) e `AMENDMENT7_ORIGINAL.json` (bytes opacos do Assino; sha = amendment7_signature_sha256; literal "Assino a emenda 7 da A2"; signed_at ≤ 21:45 BRT) e recusa **antes de qualquer raiz** se o relógio não for posterior à assinatura (`PREPARE_BEFORE_AMENDMENT7_SIGNATURE`).
- `prepare` copia os três (0400) para a raiz-fonte e grava `PREPARE_RECEIPT.json` original (0400, O_EXCL) com prepared_at, hashes e signed_at da Emenda 7.
- `measure` inclui o recibo e seu hash na medição (logo no `measurement_record_sha256` do runtime); `bind request` exige Assino < prepare ≤ medição e o mesmo hash do original (`PREPARE_RECEIPT_UNBOUND`).
- Prepare parcial/incerto continua consumido: sem remoção, sem repetição.

## Revisão 3.3 (revisão adversarial da 3.2)
- O documento da Emenda 7 precisa ter **exatamente um** selo no formato rotulado ``selo `<64 hex>` `` e ele precisa ser o desta família; um documento de outra revisão que apenas cite este selo é recusado.
- O recibo de preparação grava também `gate_checked_at_utc` (hora da conferência da assinatura, antes de qualquer efeito); o `bind request` exige signed_at < gate_checked_at ≤ prepared_at ≤ measured_at e confere selo/fonte/elegíveis/age do recibo contra o runtime medido.
