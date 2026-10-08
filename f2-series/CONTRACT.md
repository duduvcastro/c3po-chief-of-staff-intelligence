# F2_SERIES_V1 — contrato curto (diferenças em relação à F1)

**SOURCE_DELIVERY_ONLY / OPERATION_HOLD.** Fonte e testes locais. Não é folha, assinatura, runtime aceito, prontidão, capacidade, E6 nem GO. Nada aqui foi executado no servidor ou no provedor. Vínculo documental previsto: Emenda 7 (hash entra no REQUEST como `amendment7_sha256` + `amendment7_signature_sha256`; o runtime só confere formato e igualdade ao REQUEST assinado, não autentica a emenda).

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
| Documentos | request, owner, amendment_signature, election, runtime, review | request, owner, review (sem medição/eleição por inode — ver dúvidas no RUNBOOK) |

## Efeito permitido por slot

Recusa sem efeito (exit 3, nenhuma escrita, zero GET) se: slot desconhecido, fora de [slot−2 s, slot+60 s], ≥ 00:58 BRT, documentos/assinatura/revisão/elegíveis/fonte/selo inválidos, token indisponível, raiz não exclusiva, `age` divergente, `REVOKED`, ledger ocupado, slot já reclamado. Depois do claim, o slot está consumido: qualquer falha é `SLOT_HOLD` (exit 2) com cifra e recibo quando possível; nunca há segunda tentativa do mesmo slot.

Escritas permitidas, somente sob a raiz da campanha: `campaign.ledger` (append), `<slot>/` (mkdir 0700), `<slot>/slot.claim`, `<slot>/bulk-series.age`, `<slot>/RESULT.public.json` (todos 0600, O_EXCL).

Privado (cifrado): `bulk.raw` (corpo cru), `bulk-receipt.json` (horários, status, content-type, hash — sem URL/token), `analysis.json` (ausentes E−P, presentes inutilizáveis P−U com ponteiros), request/owner/review, `inventory.json`; ou `failure.json`.

Público (`F2_PUBLIC_SLOT_RESULT_V1`): slot, horário UTC agendado, início, início/fim do GET (UTC), status HTTP, hash/tamanho do corpo, contagens, PASS/FAIL, hashes de request/elegíveis/fonte/selo/inventário/cifra, número de GETs. Sem símbolos, token, caminhos internos ou exceção livre.

## Elegíveis

A readiness_probe P do G19 (`GO_READONLY_HOSTOPS02_K9_PHASE_READ_01`, rodada 07/10 22:26Z, snippet `a46e7609…`) **não guarda conjunto**: ela chama a lista de símbolos ao vivo dentro do container, aplica `build_registry` + `DAILY_ELIGIBLE_TYPES` e imprime só contagens e o hash do corpo (`bccacd2d…`, 5.782 elegíveis). O corpo não foi retido e a probe não lê nem grava banco. O produtor diário (`r2d2_v2_producer_daily.py`, main `0086dc8e`) grava `registry.json` (`V2_CAUSAL_REGISTRY_V1`) como documento de porta quando um collect roda; se houver um no servidor, seria de outra leitura, não da P, e não foi verificado (sem acesso ao servidor nesta entrega). Portanto o conjunto "original da P" é irrecuperável.

O conjunto fixo usado é o mais próximo disponível pela **mesma régua e mesmo normalizador**: o corpo cru da lista de símbolos retido pela F1 (`registry.raw` `74ac3250…`, recebido 2026-10-08T20:26:32Z, cifra F1 `2ca5366f…`, inventário `29a2eed7…`), normalizado por `bind_series.py eligible` com o `build_registry` pinado (`e50e2263…`) e os tipos `COMMON_STOCK`/`COMMON_STOCK_ADR`. Resultado: 5.784 nomes = contagem pública da F1; diferença de +2 em relação aos 5.782 da P (já registrada pelo Codex na revisão F1). Conferência local: o analisador F2 aplicado ao bulk F1 (07/10) reproduz exatamente as contagens públicas da F1 (5.679 presentes, 5.677 usáveis, 105 ausentes, 2 inutilizáveis, mínimo 5.495, 44.583 linhas). **Esta substituição precisa de aceite explícito do Codex.**
