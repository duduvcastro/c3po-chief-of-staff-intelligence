# F2-SERIES — passo a passo da Fable (nada aqui foi executado)

Horas para o dono em BRT. UTC só no canal técnico. Slots: 21:26, 21:56, 22:26, 22:56, 23:26, 23:56 (08/10) e 00:26, 00:56 (09/10) BRT = 00:26Z…03:56Z de 09/10. Slot sem margem de 180 s na hora da instalação **não é instalado nem recuperado depois**.

Variáveis usadas abaixo (Mac): `F2=/Users/eduardocastro/Documents/Codex/2026-09-04/va/work/fable-f2-series-20261008`, `PRIV=/Users/eduardocastro/Documents/Codex/2026-09-04/va/work/fable-f2-series-20261008-private` (0700; contém `ELIGIBLE_SET.json` com símbolos — **não publicar**).

## 0. Conferir bytes
`python3 -I -S -B $F2/verify_family.py` → `SEAL_EXACT`. `python3 -I -S -B $F2/test_series.py` → `"ok": true`.

## 1. Prova Linux própria (ramo descartável, sem segredo)
1. Ramo `ops/f2-series-proof-20261008` a partir da main; copiar o diretório inteiro para `f2-series/` e `linux-proof.yml` para `.github/workflows/f2-series-proof.yml` (bytes idênticos). Não incluir `ELIGIBLE_SET.json` nem nada do `$PRIV`.
2. Push pela Fable (Codex não faz push). Tentativa 1 apenas. Devolver: head/tree, run id, tentativa, conclusão, SHA256 do workflow, artefato `F2_OWN_LINUX_FIXTURE_PROOF` (id/digest/ZIP) com `SEAL_RESULT.json`, `TEST_RESULT.json`, `TEST_NAMES.txt`, `CRYPTO_RESULT.json`, `SEAL_RESULT_AFTER.json`.
3. A prova é sintética (provedor, relógio, chave age efêmera). Não certifica o servidor nem a chave real.

## 2. Revisão do Codex
Entregar ao Codex: SHA256SUMS, resultados da prova, `ELIGIBLE_SET.json` **por hash + proveniência** (`b24ffe6fca52408d4330875d11eeff1e0535114c57ce74fdedcb505e8c8acda3`, 5.784 nomes; arquivo privado só se o Codex pedir e por canal privado) e a lista de dúvidas do relatório. Sem aceite escrito da substituição do conjunto elegível (CONTRACT, "Elegíveis"), HOLD. O parecer vira `review.json` canônico:
`{"schema":"F2_CODEX_REVIEW_V1","verdict":"ACCEPTED_OWN_BYTES_LINUX","source_sha256":<series_runtime.py>,"seal_sha256":<SHA256SUMS>,"eligible_set_sha256":"b24ffe6f…","linux_result_sha256":<hash do ZIP/resultado>,"review_record_sha256":<hash do parecer>}`.

## 3. Vínculo à Emenda 7
`config.json` canônico: `{"schema":"F2_LEAF_CONFIG_V1","amendment7_sha256":<hash da Emenda 7>,"amendment7_signature_sha256":<hash do registro de assinatura>}`. Hashes por comando (`shasum -a 256`), nunca à mão.

## 4. Folha e pergunta
```
mkdir -m 700 $PRIV/in-request && cp config.json review.json $PRIV/ELIGIBLE_SET.json $PRIV/in-request/
python3 -I -S -B $F2/bind_series.py request --inputs $PRIV/in-request --out $PRIV/request-out
```
Imprime o SHA256 do REQUEST; gera `OWNER_QUESTION.txt`. A Fable apresenta a pergunta exata ao dono (antes das 22:00) e registra a resposta real em `owner.json`:
`{"schema":"F2_OWNER_SIGNATURE_V1","request_sha256":…,"question_sha256":…,"answer":"Assino","recorded_at_utc":…,"channel":"REGISTRO_PELA_FABLE"}`. Ausência/NÃO/outra resposta = HOLD.

## 5. BOUND
```
mkdir -m 700 $PRIV/in-bound && cp $PRIV/request-out/REQUEST.json $PRIV/request-out/review.json owner.json $PRIV/in-bound/
python3 -I -S -B $F2/bind_series.py bound --inputs $PRIV/in-bound --out $PRIV/bound-out
```
Imprime `BOUND_SHA`. REQUEST/BOUND imutáveis após Assino.

## 6. Instalação no servidor (Fable, via ssh, após Assino; mesma via da F1: host Linux, `sudo -n`, `/usr/bin/python3` 3.12.3 do host, root, sem container)
```
# staging (diretório do usuário ssh; o instalador confere todos os hashes)
ssh $H 'umask 077; mkdir /var/tmp/f2-stage-20261008'
scp -r $F2 $H:/var/tmp/f2-stage-20261008/f2-series            # só os 13 arquivos do selo (sem __pycache__)
scp $PRIV/bound-out/BOUND.json $PRIV/ELIGIBLE_SET.json $H:/var/tmp/f2-stage-20261008/
# prévia sem efeito
ssh $H 'sudo -n /usr/bin/python3 -I -S -B /var/tmp/f2-stage-20261008/f2-series/install_series.py plan'
# instalação única
ssh $H 'sudo -n /usr/bin/python3 -I -S -B /var/tmp/f2-stage-20261008/f2-series/install_series.py install --stage /var/tmp/f2-stage-20261008 --bound-sha256 <BOUND_SHA>'
```
O `install` recusa se: não for root/Linux; selo, BOUND, fonte, selo do REQUEST, elegíveis ou `age` da F1 (`/var/lib/c3po/f1-diagnostic-20261008/age`) divergirem; `/var/lib/c3po/f2-series-src-20261008` ou `/var/lib/c3po/f2-series-20261008` já existirem. Cria as duas raízes 0700, copia (0400) família/BOUND/elegíveis, copia `age` (0500) para a raiz da campanha, reconfere e então roda **um** `systemd-run` por slot futuro com margem ≥ 180 s, por exemplo:
```
/usr/bin/systemd-run --unit=f2s-20261008-2126 "--description=F2 series slot 2126 (BRT)" "--on-calendar=2026-10-09 00:26:00 UTC" --timer-property=AccuracySec=1s --property=Type=oneshot --property=TimeoutStartSec=170 --property=UMask=0077 --property=NoNewPrivileges=yes --property=PrivateTmp=yes /usr/bin/python3 -I -S -B /var/lib/c3po/f2-series-src-20261008/f2-series/series_runtime.py run --bound /var/lib/c3po/f2-series-src-20261008/BOUND.json --slot 2126
```
(idem 2156→00:56Z, 2226→01:26Z, 2256→01:56Z, 2326→02:26Z, 2356→02:56Z, 0026→03:26Z, 0056→03:56Z). Sem `Restart`, sem `Persistent` (padrão false), sem `--setenv`; o token não passa por argv/env: o runtime lê `C3PO_EODHD_API_TOKEN` do `provider.env` do K9 diretamente.

## 7. Readback (só leitura)
`ssh $H 'sudo -n /usr/bin/python3 -I -S -B /var/lib/c3po/f2-series-src-20261008/f2-series/install_series.py readback'` → `list-timers` + `systemctl show` de cada timer/serviço (calendário, próximo disparo, AccuracyUSec=1s, Persistent=no, Restart=no) e se existe `REVOKED`. Conferir que existe um timer por slot instalado e nenhum outro.

## 8. Revogação
`ssh $H 'sudo -n /usr/bin/python3 -I -S -B /var/lib/c3po/f2-series-src-20261008/f2-series/install_series.py revoke'` → grava `REVOKED` (o runtime recusa sem efeito) e para todos os timers. Um serviço já em execução termina seu único GET (≤ 120 s). Nada é apagado.

## 9. Leitura da manhã (09/10, após 07:00 BRT)
1. Readback (passo 7) + `sudo -n cat /var/lib/c3po/f2-series-20261008/campaign.ledger` + `sudo -n cat /var/lib/c3po/f2-series-20261008/<slot>/RESULT.public.json` para cada slot + `sudo -n journalctl -u 'f2s-20261008-*' -o cat --no-pager` (só JSON público/códigos).
2. Copiar `<slot>/bulk-series.age` de cada slot para `$PRIV/` e decifrar privadamente pela Fable. Conferir `cipher_sha256`/`inventory_sha256` contra o recibo público.
3. `python3 -I -S -B $F2/series_analyze.py RESULT_2126.json RESULT_2156.json …` → primeiro PASS, último FAIL anterior, lacunas, regressões, tempos. Publicar só o JSON do analisador + hashes (sem símbolos).
4. Nenhum resultado (PASS inclusive) é prontidão, capacidade, E6 ou GO. Remoção dos diretórios só por decisão própria posterior.
